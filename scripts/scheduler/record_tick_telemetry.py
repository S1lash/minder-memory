#!/usr/bin/env python3
"""Record one tick's own token consumption, read from its own transcript.

Claude Code writes every API response it receives to a session transcript —
`{projects_root}/{cwd-slug}/{session-id}.jsonl` — with the response's `usage`
block intact, and gives each sub-agent its own file under
`{session-id}/subagents/`. Both exist in a cloud Routines sandbox exactly as
they do locally, and both are written as the run proceeds. So a tick can
measure itself while it is still running, from data the runtime produced
rather than from anything the model believes about itself.

That distinction is the whole point. A model cannot see its own consumption:
the only figure in its context is the remaining budget counter, which knows
nothing about cache reads, nothing about sub-agents, and is not what anyone
means by "what did this tick cost". Any self-reported number would be
invention. This reads the file instead.

**Ticks only.** The scheduler prompts call this; a manual `/minder:mem:process` run
does not, and is not expected to. Nothing here detects or complains about an
un-measured manual run — the tick is the unit being measured, and the lint
backstop scopes itself to `[scheduled]` commits for the same reason.

**Never fails the tick.** Every failure path still writes a line and exits 0.
A tick that dies because its own instrumentation could not find a file would
be a strictly worse system than one with no instrumentation at all, so the
absent measurement is recorded as `status: unmeasured` with the reason, and
the tick proceeds. That also keeps "the measurement broke" distinguishable
from "the tick never ran", which are different failures with different fixes.

**What it cannot see.** Its own final messages: this runs before
`finalize-tick.sh`, so the commit and the closing report are not in the file
yet, and a second commit to add them is forbidden by the single-commit
guarantee. `measured_through` marks the horizon, and the undercount is a
handful of messages out of dozens.

Usage:
  python3 scripts/scheduler/record_tick_telemetry.py <tick>
  python3 scripts/scheduler/record_tick_telemetry.py process --dry-run
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.portable import emit_lines  # noqa: E402

FORMAT_VERSION = "1.0"

# Every countable field the runtime reports, kept whole. The reason for taking
# all of them rather than the two that are interesting today: this file is the
# only place the numbers ever exist. The transcript lives in an ephemeral
# sandbox and is gone minutes after the tick, so a field not captured here is
# not "available later from the source" — it is unrecoverable. Cache writes
# are split by TTL because the two are priced differently, and a cost estimate
# computed months from now cannot recover the split from a merged total.
COUNTERS = (
    "input",
    "output",
    "thinking",
    "cache_write_1h",
    "cache_write_5m",
    "cache_write_total",
    "cache_read",
    "web_search_requests",
    "web_fetch_requests",
)

ROLE_PROMPT_RE = re.compile(r"prompt-([A-Za-z0-9][A-Za-z0-9._-]*)\.md")
SUBAGENT_USAGE_RE = re.compile(r"subagent_tokens:\s*(\d+)")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _zero() -> dict:
    return {k: 0 for k in COUNTERS}


def _add(dst: dict, src: dict) -> None:
    for k in COUNTERS:
        dst[k] += src[k]


def extract_usage(usage: dict) -> dict:
    """Flatten one `usage` block into the counter set.

    `cache_creation_input_tokens` and the `cache_creation` TTL split are both
    read, and both kept: they are normally equal but are produced by different
    parts of the response, and a silent divergence between them is exactly the
    kind of thing worth still having the raw pair for.
    """
    out = _zero()
    out["input"] = usage.get("input_tokens") or 0
    out["output"] = usage.get("output_tokens") or 0
    details = usage.get("output_tokens_details") or {}
    out["thinking"] = details.get("thinking_tokens") or 0
    out["cache_write_total"] = usage.get("cache_creation_input_tokens") or 0
    creation = usage.get("cache_creation") or {}
    out["cache_write_1h"] = creation.get("ephemeral_1h_input_tokens") or 0
    out["cache_write_5m"] = creation.get("ephemeral_5m_input_tokens") or 0
    out["cache_read"] = usage.get("cache_read_input_tokens") or 0
    server = usage.get("server_tool_use") or {}
    out["web_search_requests"] = server.get("web_search_requests") or 0
    out["web_fetch_requests"] = server.get("web_fetch_requests") or 0
    return out


def _iter_json_lines(path: Path):
    """Yield parsed objects, skipping unparseable lines.

    A transcript is being appended to while this reads it, so the final line
    can legitimately be half-written. Skipping is correct; refusing to parse
    the file because its tail is mid-flush would throw away the whole
    measurement over one truncated record.
    """
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                continue


def _first_user_text(path: Path) -> str:
    for entry in _iter_json_lines(path):
        if entry.get("type") != "user":
            continue
        content = entry.get("message", {}).get("content")
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
    return ""


def label_for_subagent(path: Path) -> str:
    """Name a sub-agent transcript by what it actually ran.

    A role's own id is recoverable because `/minder:mem:roles` hands each role an
    assignment file named `prompt-{id}.md`, and that path is the first thing
    in the sub-agent's transcript. The sibling `.meta.json` carries a
    `description` too, but it is free prose the dispatching model wrote
    ("Second run of minder-pm", "Full-corpus backfill run") — close enough to
    an identifier to be tempting and never reliable enough to key on.
    """
    meta_path = path.with_suffix(".meta.json")
    agent_type = ""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        agent_type = str(meta.get("agentType") or "")
    except (OSError, ValueError, TypeError):
        agent_type = ""

    if agent_type == "minder-mem-role":
        match = ROLE_PROMPT_RE.search(_first_user_text(path))
        if match:
            return "role:" + match.group(1)
        return "role:unattributed"
    return "agent:" + (agent_type or "unknown")


def find_transcript(session_id: str, projects_root: Path):
    """Locate this session's transcript without knowing the cwd slug.

    The slug is derived from the working directory, and a tick's cwd differs
    between a sandbox (`/home/user/...`) and a local clone, so it is not
    something this script can compute. The session id is unique, so a glob
    over the projects root finds the file on any host.
    """
    matches = sorted(projects_root.glob("*/" + session_id + ".jsonl"))
    return matches[0] if matches else None


def count_agent_dispatches(main_path: Path) -> int:
    seen = set()
    for entry in _iter_json_lines(main_path):
        content = entry.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Agent":
                seen.add(block.get("id") or len(seen))
    return len(seen)


def collect(session_id: str, projects_root: Path) -> dict:
    main_path = find_transcript(session_id, projects_root)
    if main_path is None:
        return {
            "status": "unmeasured",
            "note": "no transcript for session under " + str(projects_root),
        }

    sub_dir = main_path.parent / session_id / "subagents"
    sub_paths = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []

    # message.id keyed, last write wins: a streamed response is appended once
    # per chunk with the same id and a growing usage block, so counting rows
    # would multiply a single response by its chunk count.
    records: dict[str, tuple[str, dict, str]] = {}
    malformed_files = 0
    # Everything below is present in the transcript and nowhere else once the
    # sandbox is gone. Cache misses matter most: they are the largest single
    # lever on what a tick costs, and the transcript says both why one happened
    # and how many tokens it cost.
    tools: dict[str, int] = {}
    stop_reasons: dict[str, int] = {}
    cache_misses: dict[str, dict] = {}
    tiers: dict[str, int] = {}
    speeds: dict[str, int] = {}
    geos: dict[str, int] = {}
    stamps: list[str] = []

    def note_message(message: dict, usage: dict) -> None:
        reason = message.get("stop_reason")
        if reason:
            stop_reasons[reason] = stop_reasons.get(reason, 0) + 1
        miss = (message.get("diagnostics") or {}).get("cache_miss_reason") or {}
        kind = miss.get("type")
        if kind:
            bucket = cache_misses.setdefault(kind, {"count": 0, "tokens": 0})
            bucket["count"] += 1
            bucket["tokens"] += miss.get("cache_missed_input_tokens") or 0
        for field, sink in (
            ("service_tier", tiers), ("speed", speeds), ("inference_geo", geos)
        ):
            value = usage.get(field)
            if value:
                sink[str(value)] = sink.get(str(value), 0) + 1
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = str(block.get("name") or "unknown")
                    tools[name] = tools.get(name, 0) + 1

    def ingest(path: Path, label: str) -> None:
        for entry in _iter_json_lines(path):
            if entry.get("type") != "assistant":
                continue
            stamp = entry.get("timestamp")
            if stamp:
                stamps.append(str(stamp))
            message = entry.get("message") or {}
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            message_id = message.get("id")
            if not message_id:
                continue
            model = str(message.get("model") or "unknown")
            if message_id not in records:
                # Tallies key off the message, not the chunk: a streamed reply
                # repeats its blocks, and counting each would multiply one tool
                # call by its chunk count.
                note_message(message, usage)
            records[message_id] = (label, extract_usage(usage), model)

    ingest(main_path, "main")
    for path in sub_paths:
        try:
            ingest(path, label_for_subagent(path))
        except OSError:
            malformed_files += 1

    totals = _zero()
    by_agent: dict[str, dict] = {}
    models: dict[str, int] = {}
    for label, usage, model in records.values():
        _add(totals, usage)
        bucket = by_agent.setdefault(
            label, {"agent": label, "api_msgs": 0, "models": {}, **_zero()}
        )
        bucket["api_msgs"] += 1
        # Per-agent as well as per-tick. A roles tick can run each role on a
        # different model, so a tick-level tally answers "how many sonnet
        # messages" but never "which role was on sonnet" — and the second is
        # the question a cost or quality comparison actually asks.
        bucket["models"][model] = bucket["models"].get(model, 0) + 1
        _add(bucket, usage)
        models[model] = models.get(model, 0) + 1

    dispatches = count_agent_dispatches(main_path)
    if dispatches and not sub_paths:
        layout_check = "drift"
    elif len(sub_paths) < dispatches:
        layout_check = "drift"
    else:
        layout_check = "ok"

    result = {
        "status": "measured" if records else "unmeasured",
        "transcript": main_path.name,
        "api_msgs": len(records),
        "first_message": min(stamps) if stamps else None,
        "last_message": max(stamps) if stamps else None,
        "totals": totals,
        "models": models,
        "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
        "stop_reasons": stop_reasons,
        "cache_misses": cache_misses,
        "runtime": {"service_tier": tiers, "speed": speeds, "inference_geo": geos},
        "by_agent": sorted(by_agent.values(), key=lambda b: -b["output"]),
        "subagent_files": len(sub_paths),
        "agent_dispatches": dispatches,
        "layout_check": layout_check,
    }
    if not records:
        result["note"] = "transcript found but no usage-bearing messages yet"
    if malformed_files:
        result["unreadable_subagent_files"] = malformed_files
    return result


def build_line(tick: str, session_id: str, projects_root: Path) -> dict:
    started = _now()
    line = {
        "ts": started,
        "tick": tick,
        "format_version": FORMAT_VERSION,
        "session_id": session_id or None,
    }
    if not session_id:
        line["status"] = "unmeasured"
        line["note"] = "CLAUDE_CODE_SESSION_ID not set"
    else:
        try:
            line.update(collect(session_id, projects_root))
        except Exception as exc:  # noqa: BLE001 - instrumentation never raises upward
            line["status"] = "unmeasured"
            line["note"] = "collector error: " + type(exc).__name__ + ": " + str(exc)[:200]
    line["measured_through"] = _now()
    return line


def append_line(out_path: Path, line: dict) -> bool:
    payload = json.dumps(line, ensure_ascii=False, sort_keys=False)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(payload + "\n")
        return True
    except OSError:
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Optional with a visible default, not required: a required positional
    # makes argparse exit 2 when a prompt is edited badly, and a scheduler
    # prompt treats any non-zero exit from a helper as cause to abandon the
    # tick. An odometer must not be able to do that. `unknown` is deliberately
    # conspicuous in the file — the malformed call is still recorded, it is
    # just recorded instead of being fatal.
    parser.add_argument(
        "tick", nargs="?", default="unknown", help="tick tag, e.g. process / lint / roles"
    )
    parser.add_argument("--base", default=None, help="repo root (default: derived)")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--projects-root", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    # `is None`, not `or`: an explicitly passed empty id means "no session",
    # and falling back to the environment there would silently measure
    # whatever session happens to be running and file it under this tick.
    if args.session_id is None:
        session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    else:
        session_id = args.session_id
    projects_root = Path(
        args.projects_root or (Path.home() / ".claude" / "projects")
    ).expanduser()

    line = build_line(args.tick, session_id, projects_root)

    if args.dry_run:
        emit_lines([json.dumps(line, ensure_ascii=False)])
        return 0

    if args.out:
        out_path = Path(args.out)
    else:
        base = Path(args.base) if args.base else Path(__file__).resolve().parents[2]
        base_name = "zettelkasten"
        for candidate in sorted(base.glob("*/_system/scripts/roles_run.py")):
            base_name = candidate.parents[2].name
            break
        out_path = base / base_name / "_system" / "state" / "tick-telemetry.jsonl"

    written = append_line(out_path, line)
    emit_lines(
        [
            "record-telemetry: {status} tick={tick} msgs={msgs} out={out} written={written}".format(
                status=line.get("status"),
                tick=line.get("tick"),
                msgs=line.get("api_msgs", 0),
                out=out_path,
                written="yes" if written else "no",
            )
        ]
    )
    # Always 0. A scheduler prompt trips failure-handling on any non-zero exit
    # from a helper, and losing a tick's real work because its odometer failed
    # would invert the priorities this script exists to serve.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
