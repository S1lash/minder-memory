#!/usr/bin/env python3
"""Run the Stage 1 thinker of agent lenses, each in a clean model call.

WHY THIS EXISTS

A lens is an outside view of the owner's base, and the whole value of it is
that the thinker sees only its frame, its own prompt and the owner's data —
not the tick that runs it, not the project's rules, not the other lenses of
the same night. Done inside the tick, the thinker is the tick: one context
that already holds everything else. Dispatched as a subagent, it carries a
large foreign system prompt, the project's CLAUDE.md and a tool belt, and the
cloud runs it in the background, so the tick has to stop and wait.

This script makes the isolation real. Each thinker is its own headless
Claude Code call (`claude -p`): the system prompt is exactly the frame body
for the lens's `input_type`, the user message is the lens folder plus its
self-history hint and one line of run context (lens, date, language), the
only tools are read-only (Read, Glob, Grep), and no settings, MCP servers or
session history are loaded. The call runs on the owner's own Claude Code
login, under the same subscription limits as the tick.

The model is the alias `opus`, never a pinned version, so a newer Opus is
picked up without a change here. A failed call is retried from a clean slate
after a pause (twice; a timeout only once, it is already the expensive
case); a lens whose thinker never answers is an error for that lens, never
for the run. No other model is ever substituted.

WHY START AND WAIT

A cohort of thinkers can take longer than one tool call may last (a command
the runner starts is cut off at ten minutes). So the runner never runs the
work in its own call: `start` launches it as a separate process and returns
at once; `wait` blocks for at most `--max-wait` seconds and returns, and the
runner calls it again until the work is done. The runner stays in its turn
the whole time — nothing is left in the background for it to stop and wait
for.

Usage:
    python3 lens_think.py start --base <zettelkasten dir> [--out DIR] \
        [--parallel N] [--timeout S] [--model ALIAS] [--language NAME] LENS_ID...
        → prints `OUT <dir>` and returns
    python3 lens_think.py wait --out DIR [--max-wait S]
        → exit 0 when done (summary printed), 3 while still running,
          4 if the work died without finishing
    python3 lens_think.py run ...   (same options as start; runs in the foreground)

Writes, per lens, `<out>/<lens-id>.thinker.md` (the thinker's text, verbatim)
and `<out>/results.json` — updated as each lens finishes — with per lens:
`status` (`ok` | `error`), `cause` on error (`assemble` | `spawn` | `timeout`
| `model-error` | `wrong-model` | `unparseable` | `internal`), `error`,
`attempts`, `thinker_model` (the model that wrote most — the CLI's own
housekeeping calls on a lighter model also appear in `models`), token usage
and seconds. `<out>/done` marks the end.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover — PyYAML is a pipeline requirement
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import configure_std_streams  # noqa: E402

MODEL = "opus"
TOOLS = "Read,Glob,Grep"
ATTEMPTS = 3              # the first call and two retries
TIMEOUT_ATTEMPTS = 2      # a timed-out call is retried once
BACKOFF_S = (30, 120)     # pause before the second and the third attempt
TIMEOUT_S = 15 * 60
PARALLEL = 3
MAX_WAIT_S = 540

FRAME = Path("_system") / "registries" / "lenses" / "_frame.md"
LENSES = Path("_system") / "registries" / "lenses"
LENS_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")

VARIANTS = {
    "records": "base-input variant",
    "lens-outputs": "lens-outputs-input variant",
    "multi-source": "multi-source-input variant",
}

HINTS = {
    "fresh-eyes": "Self-history: fresh-eyes. Do not read your own past outputs.",
    "longitudinal": (
        "Self-history: longitudinal. Your past outputs are available at "
        "`_system/agent-lens/{lens}/`; use them as context, not as evidence — "
        "see the lens prompt for guidance. Skip outputs that are superseded by a "
        "later run on the same date — `_system/state/agent-lens-runs.jsonl` "
        "entries with a `supersedes` field point to the prior `run_at` they "
        "replace; the per-day file on disk reflects the latest run only."
    ),
    "lens-decides": (
        "Self-history: lens-decides. Your past outputs are available at "
        "`_system/agent-lens/{lens}/`; the lens prompt says when to read them."
    ),
}


class LensError(Exception):
    """A lens that cannot be assembled — reported for that lens alone."""


# --- assembling the call ------------------------------------------------------


def frame_body(frame_text: str, input_type: str) -> str:
    """The fenced body of the Stage 1 section for this input type, exactly."""
    variant = VARIANTS.get(input_type)
    if not variant:
        raise LensError(f"unknown input_type {input_type!r}")
    heading = f"## Stage 1 — Thinker prompt ({variant})"
    start = frame_text.find(heading)
    if start < 0:
        raise LensError(f"frame has no section {heading!r}")
    rest = frame_text[start + len(heading):]
    nxt = re.search(r"^## ", rest, re.M)
    section = rest[: nxt.start()] if nxt else rest
    fence = re.search(r"^```[^\n]*\n(.*?)^```\s*$", section, re.M | re.S)
    if not fence:
        raise LensError(f"frame section {heading!r} has no fenced body")
    return fence.group(1).rstrip("\n") + "\n"


def lens_meta(text: str) -> dict:
    if not text.startswith("---") or yaml is None:
        return {}
    parts = text.split("---", 2)
    try:
        meta = yaml.safe_load(parts[1]) if len(parts) > 2 else {}
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def prompt_language(prompt_text: str) -> str:
    """A name for the lens prompt's language when it can be told for sure.

    Used only when the runner passes no language. The frame is in English, so
    a thinker told only «the prompt's language» drifts to the frame's.
    Cyrillic is told apart reliably; anything else is left to the general
    instruction rather than guessed.
    """
    body = prompt_text.split("---", 2)[-1] if prompt_text.startswith("---") else prompt_text
    body = re.sub(r"`[^`]*`", " ", body)
    cyrillic = len(re.findall(r"[Ѐ-ӿ]", body))
    latin = len(re.findall(r"[A-Za-z]", body))
    return "Russian" if cyrillic and cyrillic >= 0.3 * (cyrillic + latin) else ""


def assemble(base: Path, lens_id: str, today: str,
             language: str = "") -> tuple[str, str, dict]:
    """(system prompt, user message, lens metadata) for one lens."""
    if not LENS_ID.match(lens_id):
        raise LensError(f"not a lens id: {lens_id!r}")
    folder = base / LENSES / lens_id
    prompt = folder / "prompt.md"
    if not prompt.is_file():
        raise LensError(f"no prompt.md for lens {lens_id!r}")
    frame_path = base / FRAME
    if not frame_path.is_file():
        raise LensError("missing _frame.md")
    prompt_text = prompt.read_text(encoding="utf-8")
    meta = lens_meta(prompt_text)
    system = frame_body(frame_path.read_text(encoding="utf-8"),
                        str(meta.get("input_type", "")))
    stance = str(meta.get("self_history", ""))
    if stance not in HINTS:
        raise LensError(f"lens {lens_id!r} has no valid self_history")
    parts = [prompt_text.rstrip("\n")]
    for extra in sorted(p for p in folder.glob("*.md") if p.name != "prompt.md"):
        parts.append(f"<!-- {extra.name} -->\n" + extra.read_text(encoding="utf-8").rstrip("\n"))
    parts.append(HINTS[stance].format(lens=lens_id))
    if language:
        write_in = f"Write your observations in {language}, the owner's language."
    else:
        guess = prompt_language(prompt_text)
        write_in = ("Write your observations in the language the lens prompt above "
                    "is written in" + (f" — {guess}." if guess else "."))
    parts.append(f"Run context: lens `{lens_id}`, today is {today} (UTC). "
                 "The working directory is the root of the owner's base. " + write_in)
    return system, "\n\n".join(parts) + "\n", meta


# --- one call -----------------------------------------------------------------


def claude_binary() -> str | None:
    return shutil.which("claude")


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop the call and everything it started — `claude` spawns its own
    children, and killing only the direct child leaves them running (and, on
    Windows, holding the pipes a wait would block on)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def call(binary: str, base: Path, system: str, message: str, model: str,
         timeout: float) -> dict:
    """One clean thinker call. Never raises: failures come back as a dict."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8", newline="\n") as handle:
        handle.write(system)
        system_file = handle.name
    cmd = [binary, "-p", "--model", model,
           "--system-prompt-file", system_file,
           "--tools", TOOLS, "--allowedTools", TOOLS,
           "--setting-sources", "", "--strict-mcp-config",
           "--no-session-persistence", "--output-format", "json"]
    started = time.monotonic()
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
             else {"start_new_session": True})
    try:
        try:
            proc = subprocess.Popen(cmd, cwd=str(base), stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace", **group)
        except OSError as exc:
            return {"cause": "spawn", "error": f"could not start claude: {exc}", "seconds": 0}
        try:
            stdout, stderr = proc.communicate(message, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.communicate(timeout=10)
            except Exception:
                pass
            return {"cause": "timeout", "error": f"timeout after {int(timeout)}s",
                    "seconds": round(time.monotonic() - started, 1)}
    finally:
        try:
            os.unlink(system_file)
        except OSError:
            pass
    seconds = round(time.monotonic() - started, 1)
    try:
        data = json.loads(stdout)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        tail = (stderr or stdout or "").strip().splitlines()[-1:] or [""]
        return {"cause": "unparseable", "error": f"exit {proc.returncode}: {tail[0][:200]}",
                "seconds": seconds}
    result = data.get("result")
    if data.get("is_error") or not isinstance(result, str) or not result.strip():
        return {"cause": "model-error", "error": f"model error: {str(result)[:200]}",
                "seconds": seconds}
    usage_by_model = data.get("modelUsage") or {}
    # The CLI makes small housekeeping calls of its own on a lighter model, so
    # more than one model shows up; the thinker is the one that wrote the most.
    thinker = max(usage_by_model, default="",
                  key=lambda m: (usage_by_model[m] or {}).get("outputTokens") or 0)
    if "opus" not in thinker.lower():
        return {"cause": "wrong-model",
                "error": f"thinker ran on {thinker or 'an unreported model'}, not Opus",
                "seconds": seconds}
    return {"text": result, "seconds": seconds, "thinker_model": thinker,
            "models": sorted(usage_by_model),
            "usage": data.get("usage") or {}, "turns": data.get("num_turns")}


# --- one lens -----------------------------------------------------------------


def think(binary: str, base: Path, lens_id: str, out: Path, model: str,
          timeout: float, today: str, language: str = "",
          sleep=time.sleep) -> dict:
    """Assemble and run one lens's thinker. Never raises."""
    record = {"lens_id": lens_id, "status": "error", "attempts": 0}
    try:
        system, message, meta = assemble(base, lens_id, today, language)
    except Exception as exc:  # noqa: BLE001 — one lens never stops the others
        record.update(cause="assemble", error=str(exc) or type(exc).__name__)
        return record
    record["input_type"] = meta.get("input_type")
    record["output_schema"] = meta.get("output_schema") or "standard"
    try:
        timeouts = 0
        for attempt in range(1, ATTEMPTS + 1):
            if attempt > 1:
                sleep(BACKOFF_S[min(attempt - 2, len(BACKOFF_S) - 1)])
            record["attempts"] = attempt
            answer = call(binary, base, system, message, model, timeout)
            if "text" in answer:
                path = out / f"{lens_id}.thinker.md"
                _write_lf(path, answer["text"].rstrip("\n") + "\n")
                record.update(status="ok", output=str(path), seconds=answer["seconds"],
                              thinker_model=answer["thinker_model"], models=answer["models"],
                              usage=answer["usage"], turns=answer["turns"])
                record.pop("error", None)
                record.pop("cause", None)
                return record
            record.update(cause=answer["cause"], error=answer["error"])
            if answer["cause"] == "spawn":
                break
            if answer["cause"] == "timeout":
                timeouts += 1
                if timeouts >= TIMEOUT_ATTEMPTS:
                    break
    except Exception as exc:  # noqa: BLE001
        record.update(status="error", cause="internal", error=str(exc) or type(exc).__name__)
    return record


# --- a cohort -----------------------------------------------------------------


def _write_lf(path: Path, text: str) -> None:
    # Path.write_text takes no `newline` before Python 3.10 (macOS ships 3.9).
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _write_results(out: Path, results: list) -> None:
    tmp = out / "results.json.tmp"
    _write_lf(tmp, json.dumps(results, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, out / "results.json")


def run(args: argparse.Namespace) -> int:
    base = Path(args.base).resolve()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "done").unlink(missing_ok=True)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    lenses = list(dict.fromkeys(args.lenses))   # a lens named twice runs once
    results: list = [{"lens_id": lens, "status": "running"} for lens in lenses]
    lock = threading.Lock()
    _write_results(out, results)
    binary = claude_binary()

    def one(index: int, lens: str) -> None:
        if binary is None:
            record = {"lens_id": lens, "status": "error", "attempts": 0,
                      "cause": "spawn", "error": "claude CLI not found in PATH"}
        else:
            record = think(binary, base, lens, out, args.model, args.timeout,
                           today, args.language)
        with lock:
            results[index] = record
            _write_results(out, results)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        for future in [pool.submit(one, i, lens) for i, lens in enumerate(lenses)]:
            future.result()
    (out / "done").write_text("done\n", encoding="utf-8")
    _summary(results)
    return 0


def _summary(results: list) -> None:
    for r in results:
        if r["status"] == "ok":
            print(f"{r['lens_id']}: ok ({r.get('seconds')}s, {r.get('thinker_model')})")
        else:
            print(f"{r['lens_id']}: {r['status']}"
                  + (f" [{r.get('cause')}] {r.get('error')}" if r.get("error") else ""))


def _alive(pid: int) -> bool:
    if os.name == "nt":
        found = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                               capture_output=True, text=True)
        return str(pid) in (found.stdout or "")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start(args: argparse.Namespace, argv: list[str]) -> int:
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="lens-run-"))
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("done", "results.json"):
        (out / stale).unlink(missing_ok=True)
    rest = [a for a in argv if a != "start"]
    if not args.out:
        rest = ["--out", str(out)] + rest
    detach = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
              if os.name == "nt" else {"start_new_session": True})
    with open(out / "run.log", "w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", *rest],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                **detach)
    (out / "pid").write_text(f"{proc.pid}\n", encoding="utf-8")
    print(f"OUT {out}")
    return 0


def wait(args: argparse.Namespace) -> int:
    out = Path(args.out)
    deadline = time.monotonic() + args.max_wait
    while True:
        if (out / "done").exists():
            _summary(json.loads((out / "results.json").read_text(encoding="utf-8")))
            return 0
        try:
            pid = int((out / "pid").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = 0
        if pid and not _alive(pid):
            time.sleep(1)
            if (out / "done").exists():
                continue
            print("the thinker run died before finishing; results so far:")
            if (out / "results.json").exists():
                _summary(json.loads((out / "results.json").read_text(encoding="utf-8")))
            return 4
        if time.monotonic() >= deadline:
            print("still running — call wait again")
            return 3
        time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "start"):
        p = sub.add_parser(name)
        p.add_argument("--base", required=True, help="the zettelkasten directory")
        p.add_argument("--out", required=(name == "run"),
                       help="where thinker outputs are written (start: a new temp dir)")
        p.add_argument("--parallel", type=int, default=PARALLEL)
        p.add_argument("--timeout", type=float, default=TIMEOUT_S)
        p.add_argument("--model", default=MODEL)
        p.add_argument("--language", default="",
                       help="the owner's language, as the runner established it")
        p.add_argument("lenses", nargs="+")
    w = sub.add_parser("wait")
    w.add_argument("--out", required=True)
    w.add_argument("--max-wait", type=float, default=MAX_WAIT_S)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(argv)
    if args.command == "run":
        return run(args)
    if args.command == "start":
        return start(args, argv)
    return wait(args)


if __name__ == "__main__":
    raise SystemExit(main())
