#!/usr/bin/env python3
"""When did each pipeline last run — the one answer, for every reader.

WHY THIS EXISTS

«Is lint still running?» had no owner. Every reader worked it out for itself
from the prose of an append-only log, and the cheap reading — *the last `## `
header in the file* — is wrong, because the logs are not in one order.

`log_lint.md` is the case that cost the most. Its newest entry sits at the TOP
(the file says so, in a marker at line 26: «Entries append BELOW this line,
newest first»), while the last seven entries, written before that convention,
remain at the bottom in ascending order. So the FINAL header in the file is
`2026-06-08` and the newest entry is `2026-07-28`. Anything taking the last
header concluded the pipeline had been dead for fifty days while it was
delivering nightly — and the routine really did stop for twelve days inside
that window, invisibly, because the surface that would have shown it was
already reporting a much older date.

`log_maintenance.md` has the same split, five days wide instead of fifty. It is
the same defect; only the blast radius differed.

WHAT IT DOES

Reads every pipeline log, extracts every run timestamp, and returns the
**maximum** — never the last one in file order. Order-agnostic by construction,
so no log has to be rewritten and no future ordering change can break it.

Four header shapes exist today and all four are real:

    ## 2026-07-28T01:09:09Z | lint | by: minder:mem:lint       log_lint.md
    ## 2026-08-08 — Processing: activitywatch …         log_process.md
    ## 2026-05-01 11:38:00Z — agent-lens run            log_agent_lens.md
    ## 2026-08-08T… or ## 2026-08-08 — …                log_maintenance.md

Roles are not a markdown log at all — each role keeps `log.jsonl`, one object
per executed run — so they are read from there and reported per role.

Usage:
    python3 pipeline_health.py --base <base> [--json] [--now ISO8601]

Exit code is 0 whatever it finds: this reports, it does not judge. A caller
that wants a staleness threshold applies its own.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import configure_std_streams  # noqa: E402

# `## ` + a date, optionally followed by a time (T-separated or space-separated,
# with or without a trailing Z). Everything after that is prose and ignored —
# the shapes differ per log and none of them is a contract.
_HEADER = re.compile(
    r"^##\s+(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)\s*Z?)?",
    re.MULTILINE,
)

# The markdown logs, by the pipeline that owns each one.
LOGS = {
    "process": "log_process.md",
    "maintain": "log_maintenance.md",
    "lint": "log_lint.md",
    "agent-lens": "log_agent_lens.md",
}

ROLES_DIRNAME = "roles"
ROLE_LOG = "log.jsonl"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def timestamps(text: str) -> list:
    """Every run timestamp in a log, as sortable ISO strings.

    A date with no time becomes midnight — comparing dates is what the callers
    ask about, and inventing an hour would be a fact nobody wrote down.
    """
    out = []
    for day, clock in _HEADER.findall(text):
        if clock:
            if len(clock) == 5:
                clock += ":00"
            out.append(f"{day}T{clock}Z")
        else:
            out.append(f"{day}T00:00:00Z")
    return out


def last_run(path: Path) -> dict:
    """The newest run in one log — by MAXIMUM, never by file position.

    The distinction is the whole point of this module. `log_lint.md` holds a
    descending block above an ascending legacy tail, so its last header is
    seven weeks older than its newest entry.
    """
    stamps = timestamps(_read(path))
    if not stamps:
        return {"last_run": None, "entries": 0, "exists": path.is_file()}
    return {
        "last_run": max(stamps),
        "entries": len(stamps),
        "exists": True,
        # Kept because it is the number a naive reader would have got, and
        # seeing the two differ is what makes the defect legible rather than
        # theoretical.
        "last_in_file_order": stamps[-1],
    }


def role_runs(base: Path) -> dict:
    """Last executed run per role, from each role's own `log.jsonl`."""
    root = base / "_system" / ROLES_DIRNAME
    out = {}
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        stamps = []
        for line in _read(d / ROLE_LOG).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            ts = entry.get("ts")
            if isinstance(ts, str) and ts:
                stamps.append(ts)
        out[d.name] = {
            "last_run": max(stamps) if stamps else None,
            "entries": len(stamps),
            "exists": (d / ROLE_LOG).is_file(),
        }
    return out


def _age_days(stamp: str, now: datetime) -> float | None:
    try:
        when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return round((now - when).total_seconds() / 86400, 1)


def report(base: Path, now: datetime) -> dict:
    state = base / "_system" / "state"
    out = {"now": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "pipelines": {}, "roles": {}}
    for name, filename in LOGS.items():
        row = last_run(state / filename)
        if row.get("last_run"):
            row["age_days"] = _age_days(row["last_run"], now)
        out["pipelines"][name] = row
    for rid, row in role_runs(base).items():
        if row.get("last_run"):
            row["age_days"] = _age_days(row["last_run"], now)
        out["roles"][rid] = row
    return out


def render(data: dict) -> str:
    lines = [f"pipeline health as of {data['now']}", ""]
    for name, row in data["pipelines"].items():
        if not row.get("exists"):
            lines.append(f"  {name:<12} no log file")
        elif not row.get("last_run"):
            lines.append(f"  {name:<12} log present, no runs recorded")
        else:
            note = ""
            if row.get("last_in_file_order") and row["last_in_file_order"] != row["last_run"]:
                note = f"  (last line in file says {row['last_in_file_order'][:10]})"
            lines.append(
                f"  {name:<12} {row['last_run'][:16]}  {row['age_days']:>5}d ago"
                f"  {row['entries']} runs{note}"
            )
    for rid, row in data.get("roles", {}).items():
        if row.get("last_run"):
            lines.append(f"  role:{rid:<7} {row['last_run'][:16]}  {row['age_days']:>5}d ago"
                         f"  {row['entries']} runs")
        else:
            lines.append(f"  role:{rid:<7} never run")
    return "\n".join(lines)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", help="ISO8601 UTC, for tests and replay")
    # Owner text reaches stdout here; the platform code page would raise on
    # the first non-ASCII role id or log line under a Windows console.
    configure_std_streams()
    args = ap.parse_args(argv[1:])

    now = (datetime.strptime(args.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))
    data = report(Path(args.base).resolve(), now)
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
