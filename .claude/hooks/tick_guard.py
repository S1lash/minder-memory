#!/usr/bin/env python3
"""Hold a scheduled run until its work is delivered — then let it go.

Why this exists. A scheduled tick is a model following a prompt to the end,
and the end is the step that commits and delivers the run's work. A model can
walk away before it: one tick finished its skills, wrote a good report, and
ended its turn with nothing committed — the platform recorded a success and
the batch was simply gone. Roughly one tick in four did not land in the two
weeks before this existed. A sentence in a prompt cannot hold that line. The
platform's own end-of-turn check can: this script answers it.

Two events, one file:

  PostToolUse (Bash) — when `scripts/scheduler/pin-main.sh <tag>` has just run,
    bind the tick's record (`scripts/scheduler/tick_state.py`) to this session.
    Only the session that started a tick is ever held by it: an owner working
    in the same clone, or a later run finding a record a crashed one left, is
    never touched.

  Stop — when that session tries to end with the tick still open:
    * while work it started in the background is still running (a subagent,
      a background command, a monitor, an agent it sent a message to), let
      the turn end and do nothing else: that is
      a run waiting to be woken, not a run walking away, and the platform
      wakes it when the work reports back;
    * up to MAX_NUDGES times, refuse and tell it exactly what is left to do;
    * after that, close the tick itself, and let the run end:
        - work finished (no pipeline lock held) → deliver it as the closing
          step would, settling any conflict the tick left open by main's
          version for those files only;
        - work interrupted (a lock still held, so a skill is mid-flight) →
          deliver a failure note and NOTHING of the half-done work: the next
          tick redoes it whole from the inbox, and half of it delivered now is
          what would turn that redo into duplicates.

Fails open, always. Any error here is swallowed and the run is allowed to end:
a broken guard must never be the thing that keeps a session from finishing.
Subagents are not affected — the platform sends them a different event.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

MAX_NUDGES = 2
# One budget for everything the guard runs, inside the 600 s the hook is
# granted in `.claude/settings.json`: a hook the platform kills mid-delivery can
# leave git's index lock behind, which is worse than a delivery not attempted.
BUDGET_S = 560
_DEADLINE = [time.monotonic() + BUDGET_S]
# Background work is trusted for this long after the tick opened. It bounds
# what a late stop means; it cannot wake a run whose work never reports.
BACKGROUND_GRACE_S = 3 * 3600

_NOTICE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
_NOTICE_ID = re.compile(r"<task-id>\s*([^<\s]+)\s*</task-id>")
_NOTICE_STATUS = re.compile(r"<status>\s*([^<\s]+)\s*</status>")
_MARKS = ("isAsync", "backgroundTaskId", "resumedAgentId", "timeoutMs", "task_type",
          "task-notification")
_FINAL = {"completed", "failed", "killed", "stopped", "cancelled", "error", "timeout"}

# Binding needs the session to have RUN pin-main with a tag — not merely to
# mention it (`grep … scheduler/pin-main.sh` would otherwise bind an owner's
# session to a tick it never started).
_PIN_MAIN = re.compile(r"(^|[;&|(]\s*|\bbash\s+|\bsh\s+)\S*scheduler/pin-main\.sh\s+scheduler/[a-z-]+")

PROMPTS = {
    "scheduler/process": "process-scheduled.md",
    "scheduler/lint": "lint-nightly.md",
    "scheduler/agent-lens": "agent-lens-nightly.md",
    "scheduler/roles": "roles-nightly.md",
    "scheduler/content": "content-tick.md",
}


def _configure_streams() -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        from lib.portable import configure_std_streams  # noqa: PLC0415
        configure_std_streams()
    except Exception:
        for stream in (sys.stdin, sys.stdout):
            try:
                stream.reconfigure(encoding="utf-8", newline="\n")
            except (AttributeError, ValueError):
                pass


def _root(payload: dict) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(payload.get("cwd") or ".")


def _tick_state(root: Path):
    sys.path.insert(0, str(root / "scripts" / "scheduler"))
    import tick_state  # noqa: PLC0415
    return tick_state


def _run(root: Path, *cmd: str) -> int:
    """Run a command within what is left of the budget; kill its whole group
    on timeout — git and gh children hold the pipes otherwise, and the wait
    would outlive the budget it was meant to enforce."""
    remaining = _DEADLINE[0] - time.monotonic()
    if remaining < 5:
        return 1
    posix = os.name == "posix"
    try:
        proc = subprocess.Popen(list(cmd), cwd=str(root), stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=posix)
    except Exception:
        return 1
    try:
        return proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        try:
            if posix:
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass
        return 1
    except Exception:
        return 1


def _deliveries(entry: dict) -> list[str]:
    """The completion notices the platform delivered to the session in this entry.

    A notice arrives as a queued command, an attachment or a user message of
    its own, and it is the whole of that message; it is never read out of a
    tool's result, the model's own words or a prompt that quotes one.
    """
    kind = entry.get("type")
    texts: list = []
    if kind == "queue-operation":
        texts = [entry.get("content")]
    elif kind == "attachment":
        texts = [(entry.get("attachment") or {}).get("prompt")]
    elif kind == "user":
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [part.get("text") for part in content
                     if isinstance(part, dict) and part.get("type") == "text"]
    return [text for text in texts
            if isinstance(text, str) and text.lstrip().startswith("<task-notification>")]


def _launched_task(result) -> str:
    """The id of background work a tool result started, or "".

    Each shape is matched exactly, never by a bare id key: a task-list entry
    carries a `taskId` too, and a launch read where there is none would hold
    the guard back from a run that has really stopped. A persistent monitor
    has no end of its own, so it is never something a run waits for.
    """
    if not isinstance(result, dict):
        return ""
    if result.get("isAsync") and isinstance(result.get("agentId"), str):
        return result["agentId"]                    # an agent sent to the background
    if isinstance(result.get("backgroundTaskId"), str):
        return result["backgroundTaskId"]           # a background command
    if isinstance(result.get("resumedAgentId"), str):
        return result["resumedAgentId"]             # a finished agent sent a message
    if isinstance(result.get("taskId"), str) and "timeoutMs" in result \
            and result.get("persistent") is False:
        return result["taskId"]                     # a monitor
    return ""


def _stopped_task(result) -> str:
    """The id of background work a tool result stopped, or "".

    A task the run stops itself never sends a notice; without this its launch
    would read as running for good, and a run that then ends is never woken.
    """
    if not isinstance(result, dict) or "task_type" not in result:
        return ""
    task = result.get("task_id") or result.get("shell_id")
    return task if isinstance(task, str) else ""


def pending_background(transcript: str) -> list[str]:
    """Background work the session started that has not reported back.

    Read from the session's own transcript: a launch is a tool result that
    starts background work (`_launched_task`); its end is a
    `<task-notification>` for that id carrying a final status, or the run
    stopping it itself. A resumed agent launches again, so only an end after
    its latest launch counts — and one notice is delivered as several entries
    (queued, attached, removed), so each notice counts at its first sighting.
    A model that dispatched a subagent and ended its turn to wait for it looks,
    to the Stop event, exactly like one that walked away, and closing the tick
    under a working subagent throws its work away.
    """
    launched: dict[str, int] = {}
    ended: dict[str, int] = {}
    seen: set[str] = set()
    with open(transcript, "r", encoding="utf-8", errors="replace") as handle:
        for n, line in enumerate(handle):
            if not any(mark in line for mark in _MARKS):
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            result = entry.get("toolUseResult")
            task = _launched_task(result)
            if task:
                launched[task] = n
            task = _stopped_task(result)
            if task:
                ended[task] = n
            for text in _deliveries(entry):
                for notice in _NOTICE.findall(text):
                    if notice in seen:
                        continue
                    seen.add(notice)
                    task = _NOTICE_ID.search(notice)
                    status = _NOTICE_STATUS.search(notice)
                    if task and status and status.group(1) in _FINAL:
                        ended[task.group(1)] = n
    return sorted(task for task, n in launched.items() if ended.get(task, -1) < n)


def _waiting_on_background(payload: dict, record: dict) -> list[str]:
    """What the run is waiting for, or [] when its stop is a real stop.

    Waiting is trusted for BACKGROUND_GRACE_S after the tick opened, and only
    while the run itself is alive to be woken: if the work never reports, no
    later Stop arrives, so the grace bounds what a stop much later means rather
    than rescuing a run nothing wakes. The wait is written into the tick's
    record, so a tick that ends in one is visible afterwards.
    """
    try:
        if time.time() - float(record.get("opened_at", 0)) > BACKGROUND_GRACE_S:
            return []
        transcript = payload.get("transcript_path")
        return pending_background(str(transcript)) if transcript else []
    except Exception:
        return []


def _locks_held(root: Path) -> bool:
    """A pipeline lock still present means a skill did not reach its end."""
    for lock in root.glob("*/_sources/.*.lock"):
        if lock.is_file():
            return True
    return False


def _prompt_path(tag: str) -> str:
    name = PROMPTS.get(tag, "")
    return f"integrations/claude-code/scheduler-prompts/{name}" if name else "the scheduler prompt"


def reason_for(record: dict) -> str:
    tag = record.get("tag", "")
    prompt = _prompt_path(tag)
    state = record.get("state", "open")
    close = f"bash scripts/scheduler/close-tick.sh {tag}"
    head = ("This scheduled run is not finished — its work has not been delivered, "
            "and a run that ends now loses it. Do not end your turn yet. ")
    if state == "conflict":
        rerun = close
        after = ""
        if (Path(".scheduler-state") / "conflict-checkpoint").exists():
            rerun = f"{close} --checkpoint"
            after = " Then carry on with Step 4.5 — the tick is not finished."
        return (head + "Delivery stopped on a conflict with a run that landed first. "
                f"Do Step 5c of {prompt}: resolve each file listed in "
                f"`.scheduler-state/conflict` so it keeps what BOTH sides meant, remove "
                f"every conflict marker, then run `{rerun}` again.{after}")
    if state == "needs-mcp":
        return (head + f"gh cannot reach the repository, so delivery is Step 5b of {prompt} "
                "(push to the sandbox branch, then the GitHub connector's create and "
                "merge). Do Step 5b now.")
    if state == "failed":
        detail = record.get("detail") or "delivery failed"
        return (head + f"Delivery failed ({detail}). Run the failure handling of {prompt} "
                "now, so the failure is recorded and shipped.")
    extra = ""
    if tag == "scheduler/process":
        extra = ("If Step 4.5 (`/minder:mem:maintain --no-sync-check`) has not run yet in "
                 "this tick, run it first. ")
    return (head + f"Continue with the remaining steps of {prompt}. {extra}"
            f"The run ends with `{close}` — run it, and only then finish.")


def _delivered_by_mcp(root: Path, record: dict) -> bool:
    """After Step 5b, main carries a commit with this tick's subject.

    Asked of main's history, not of file contents: a later run changing one of
    the same files would make a completed delivery read as missing.
    """
    try:
        subject = subprocess.run(["git", "log", "-1", "--format=%s", "HEAD"], cwd=str(root),
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=20).stdout.strip()
    except Exception:
        return False
    if not subject or _run(root, "git", "fetch", "origin", "main", "--quiet") != 0:
        return False
    since = str(int(float(record.get("opened_at", 0))))
    try:
        landed = subprocess.run(["git", "log", "origin/main", f"--since=@{since}",
                                 "--format=%s"], cwd=str(root), capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=20).stdout.splitlines()
    except Exception:
        return False
    return subject in landed


def auto_close(root: Path, record: dict, ts) -> None:
    tag = record.get("tag", "scheduler/unknown")
    name = tag.split("/", 1)[-1]
    state = record.get("state", "open")
    note = ["bash", "scripts/scheduler/ship-failure-note.sh"]
    if state == "open" and _locks_held(root):
        _run(root, *note, "--note-only",
             "run ended in the middle of its work; the unfinished part was not "
             "delivered and the next run redoes it", name)
        return
    if state in ("open", "conflict"):
        close = ["bash", "scripts/scheduler/close-tick.sh", tag, "--resolve-by-main"]
        rc = _run(root, *close)
        after = ts.read(root) or {}
        if rc == 0 and after.get("state") == "open":
            # That settled a checkpoint; the tick itself is still open. Close
            # it too, so it is measured and delivered once more.
            rc = _run(root, *close)
        if rc != 0:
            _run(root, *note, f"run ended without delivering; the closing guard's own "
                              f"delivery failed too (exit {rc})", name)
        return
    if state == "needs-mcp" and _delivered_by_mcp(root, record):
        ts.cmd_set("closed", "delivered through the connector")
        return
    _run(root, *note, f"run ended without delivering ({record.get('detail') or state})", name)


def on_stop(payload: dict) -> dict | None:
    root = _root(payload)
    if not (root / ".scheduler-state" / "tick.json").exists():
        return None
    os.chdir(root)
    ts = _tick_state(root)
    record = ts.read(root)
    if not record or record.get("state") == "closed" or ts.is_stale(record):
        return None
    if not record.get("session_id") or record.get("session_id") != payload.get("session_id"):
        return None
    if record.get("state") == "needs-mcp" and _delivered_by_mcp(root, record):
        ts.cmd_set("closed", "delivered through the connector")
        return None
    waiting = _waiting_on_background(payload, record)
    if waiting:
        record["waiting_on"] = waiting
        record["waiting_since"] = record.get("waiting_since") or time.time()
        ts.write(record, root)
        return None
    record.pop("waiting_on", None)
    record.pop("waiting_since", None)
    nudges = int(record.get("nudges", 0))
    if nudges < MAX_NUDGES:
        record["nudges"] = nudges + 1
        ts.write(record, root)
        return {"decision": "block", "reason": reason_for(record)}
    auto_close(root, record, ts)
    return None


def on_post_tool_use(payload: dict) -> None:
    if payload.get("tool_name") != "Bash":
        return
    command = str((payload.get("tool_input") or {}).get("command", ""))
    if not _PIN_MAIN.search(command.replace("\\", "/")):
        return
    root = _root(payload)
    if not (root / ".scheduler-state" / "tick.json").exists():
        return
    os.chdir(root)
    _tick_state(root).cmd_bind(str(payload.get("session_id") or ""))


def main() -> int:
    try:
        _configure_streams()
        payload = json.loads(sys.stdin.read() or "{}")
        event = payload.get("hook_event_name", "")
        if event == "PostToolUse":
            on_post_tool_use(payload)
        elif event == "Stop":
            answer = on_stop(payload)
            if answer:
                sys.stdout.write(json.dumps(answer, ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
