"""The open/closed record of one scheduler tick.

Why this exists. A tick ends only when its closing step has delivered its work,
and the one thing that walked away from that step was the model running it: a
tick finished its skills, wrote a fine report, and ended its turn with nothing
committed — the platform marked the run a success and a whole batch was gone.
A promise in a prompt cannot hold that line. A record the closing step writes,
read by a guard the model cannot talk past (`.claude/hooks/tick_guard.py`), can.

The record lives in `.scheduler-state/tick.json`, which is ignored by git: it
describes this clone's current run and is meaningless anywhere else.

States:
  open           — `pin-main.sh <tag>` started the tick; nothing closed it yet
  conflict       — delivery stopped on a conflict the tick has to resolve
  needs-mcp      — gh cannot reach the repository; delivery belongs to Step 5b
  failed         — delivery failed for another reason; failure handling is due
  closed         — delivered, or ended through failure handling

`session_id` binds the record to the session that opened it, so the guard never
acts on a session that is not running this tick — an owner working in the same
clone, or a later tick reading a record a crashed one left behind.

Usage (every subcommand exits 0 — bookkeeping must never fail a tick — except
`live-for-other`, which answers through its exit status):
  python3 scripts/scheduler/tick_state.py open <tag>
  python3 scripts/scheduler/tick_state.py bind <session-id>
  python3 scripts/scheduler/tick_state.py [--for <tag|name>] set <state> [detail]
  python3 scripts/scheduler/tick_state.py [--for <tag|name>] resolved
  python3 scripts/scheduler/tick_state.py [--for <tag|name>] checkpoint
  python3 scripts/scheduler/tick_state.py live-for-other <tag>
  python3 scripts/scheduler/tick_state.py show

`--for` goes right after the subcommand: `set --for scheduler/lint closed x`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE_FILE = Path(".scheduler-state") / "tick.json"
STATES = ("open", "conflict", "needs-mcp", "failed", "closed")

# A record older than this belongs to a run that is long gone — never to the
# session asking. Generous: the longest tick seen runs about an hour and a half.
STALE_AFTER_S = 8 * 3600
# Binding happens right after `pin-main.sh` returns; a record that waited longer
# than this for its session was not opened by the session now claiming it.
BIND_WINDOW_S = 15 * 60


def _now() -> float:
    return time.time()


def read(root: Path | None = None) -> dict | None:
    path = (root or Path.cwd()) / STATE_FILE
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write(data: dict, root: Path | None = None) -> None:
    path = (root or Path.cwd()) / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename, so a reader never sees half a record.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tick.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    os.replace(tmp, path)


def is_stale(data: dict) -> bool:
    try:
        return _now() - float(data.get("opened_at", 0)) > STALE_AFTER_S
    except (TypeError, ValueError):
        return True


def cmd_open(tag: str) -> None:
    write({"tag": tag, "state": "open", "opened_at": _now(), "session_id": None,
           "nudges": 0, "checkpoints": 0, "detail": ""})


def cmd_bind(session_id: str) -> None:
    data = read()
    if not data or data.get("session_id") or not session_id:
        return
    try:
        if _now() - float(data.get("opened_at", 0)) > BIND_WINDOW_S:
            return
    except (TypeError, ValueError):
        return
    data["session_id"] = session_id
    write(data)


def owns(data: dict, who: str) -> bool:
    """Whether `who` — a tag (`scheduler/lint`) or a tick name (`lint-nightly`) —
    names the pipeline this record belongs to.

    Two ticks of different pipelines can share one local clone, and they share
    this one record file. Every write names its pipeline, and a write for
    another pipeline's record is ignored: one tick closing must never close, or
    reopen, the other's.
    """
    if not who:
        return True
    pipeline = str(data.get("tag", "")).split("/", 1)[-1]
    name = who.split("/", 1)[-1]
    return bool(pipeline) and (name == pipeline or name.startswith(pipeline + "-"))


def cmd_set(state: str, detail: str = "", who: str = "") -> None:
    data = read()
    if not data or state not in STATES or not owns(data, who):
        return
    # A tick that ended stays ended. Nothing reopens it — not a failure note's
    # own delivery, not a resumed conflict — only a new tick's `open`.
    if data.get("state") == "closed" and state != "closed":
        return
    data["state"] = state
    data["detail"] = detail
    if state == "open":
        data["nudges"] = 0
    write(data)


def cmd_resolved(who: str = "") -> None:
    """A conflict was settled: back to open — only from `conflict`."""
    data = read()
    if not data or data.get("state") != "conflict" or not owns(data, who):
        return
    data["state"] = "open"
    data["detail"] = ""
    write(data)


def cmd_checkpoint(who: str = "") -> None:
    data = read()
    if not data or data.get("state") == "closed" or not owns(data, who):
        return
    data["checkpoints"] = int(data.get("checkpoints", 0)) + 1
    data["state"] = "open"
    data["detail"] = ""
    write(data)


def is_live_for_other(tag: str) -> bool:
    """A record of another pipeline that a running session still holds."""
    data = read()
    return bool(data) and data.get("state") != "closed" and not is_stale(data) \
        and bool(data.get("session_id")) and data.get("tag") != tag


def main(argv: list[str]) -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from lib.portable import configure_std_streams  # noqa: PLC0415
        configure_std_streams()
    except Exception:  # noqa: BLE001 — bookkeeping never fails a tick
        pass
    try:
        if not argv:
            return 0
        sub, rest = argv[0], argv[1:]
        # `--for <tag-or-name>` scopes a write to its own pipeline's record.
        who = ""
        if len(rest) >= 2 and rest[0] == "--for":
            who, rest = rest[1], rest[2:]
        if sub == "open" and rest:
            cmd_open(rest[0])
        elif sub == "bind" and rest:
            cmd_bind(rest[0])
        elif sub == "set" and rest:
            cmd_set(rest[0], " ".join(rest[1:]), who)
        elif sub == "resolved":
            cmd_resolved(who)
        elif sub == "checkpoint":
            cmd_checkpoint(who)
        elif sub == "live-for-other" and rest:
            # exit status, not output: 0 when another pipeline's tick is live
            return 0 if is_live_for_other(rest[0]) else 1
        elif sub == "show":
            print(json.dumps(read() or {}, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — bookkeeping never fails a tick
        print(f"tick_state: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
