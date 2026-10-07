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
