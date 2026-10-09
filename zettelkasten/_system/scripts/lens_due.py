#!/usr/bin/env python3
"""Decide which agent lenses are due tonight.

WHY THIS EXISTS

Worked out from prose in a model's head, the due rule lets a daily lens run
twice in one day and leaves a weekly lens that failed on its day waiting a
whole week, its finding lost for no reason but a transient error. Decided here, the same rule holds on
every night and every machine, and the runner has nothing to improvise.

THE RULE (canonical prose: `AGENT_LENSES.md` → Cadence semantics)

- A lens with any run today other than `error` (`ok`, `empty`, `rejected`,
  `skipped`) is not due again today.
- Scheduled: `daily` every day; `weekly` and `monthly` on their anchor
  (weekday, or day of the month clamped to 28) unless an `ok`/`empty` run
  happened within the last 3 days — a run made by hand just before the
  anchor is not repeated on it, and a retry that succeeded on its last night
  is never mistaken for the next turn. `biweekly` is the same with 10 days,
  which is what makes it alternate weeks: its cycle follows its last
  `ok`/`empty` run. With no such run ever, the anchor alone decides.
- Retry: a lens that ended `error` on an anchor day within the last two
  days (the thinker never answered — a transient failure), and has had only
  `error` runs since, is due again tonight. A `rejected` run is a verdict on
  the output, not a transient failure; it is never retried early, so the
  auto-pause count is not run up by retries. A daily lens needs no retry.

A lens whose frontmatter cannot be read, or two lens folders declaring the
same `id`, are reported on stderr and left out — the runner's registry
validation raises the CLARIFICATION.

Usage:
    python3 lens_due.py due --base <zettelkasten dir> [--today YYYY-MM-DD]
        → one line per due lens, `<lens-id> <scheduled|retry>`, sorted by
          lens folder name (Step 4 orders the run); nothing when none is due

Only `status: active` lenses are considered. Dates are UTC calendar days,
taken from `run_at`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import configure_std_streams, read_frontmatter  # noqa: E402

LENSES_DIR = Path("_system/registries/lenses")
RUNS = Path("_system/state/agent-lens-runs.jsonl")
RETRY_DAYS = 2
# A good run within this many days suppresses an anchor run. It must exceed
# RETRY_DAYS, or a late retry would be taken for the next turn; biweekly's is
# what makes it skip alternate anchors.
MIN_GAP_DAYS = {"weekly": RETRY_DAYS + 2, "monthly": RETRY_DAYS + 2,
                "biweekly": 14 - RETRY_DAYS - 1}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday")
DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _day(value) -> dt.date | None:
    match = DATED.match(str(value or ""))
    if not match:
        return None
    try:
        return dt.date.fromisoformat(match.group(1))
    except ValueError:
        return None


def load_runs(base: Path) -> dict:
    """lens_id → list of (date, status), in file order."""
    runs: dict = {}
    path = base / RUNS
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return runs
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        day = _day(entry.get("run_at"))
        if day is None or not isinstance(entry.get("lens_id"), str):
            continue
        runs.setdefault(entry["lens_id"], []).append((day, entry.get("status")))
    for history in runs.values():
        history.sort(key=lambda item: item[0])
    return runs


def _on_anchor(cadence: str, anchor, today: dt.date) -> bool:
    if cadence == "monthly":
        try:
            return today.day == min(int(anchor), 28)
        except (TypeError, ValueError):
            return False
    return str(anchor).strip().lower() == WEEKDAYS[today.weekday()]


def _scheduled(cadence: str, anchor, today: dt.date, last_good: dt.date | None) -> bool:
    if cadence == "daily":
        return True
    if cadence not in MIN_GAP_DAYS or not _on_anchor(cadence, anchor, today):
        return False
    return last_good is None or (today - last_good).days >= MIN_GAP_DAYS[cadence]


def why_due(meta: dict, history: list, today: dt.date) -> str | None:
    """`scheduled`, `retry` or None for one lens."""
    past = [(day, status) for day, status in history if day <= today]
    if any(day == today and status != "error" for day, status in past):
        return None
    good = [day for day, status in past if status in ("ok", "empty")]
    last_good = max(good) if good else None
    cadence = str(meta.get("cadence") or "")
    anchor = meta.get("cadence_anchor")
    if _scheduled(cadence, anchor, today, last_good):
        return "scheduled"
    if cadence not in MIN_GAP_DAYS:
        return None
    for back in range(1, RETRY_DAYS + 1):
        failed_on = today - dt.timedelta(days=back)
        if not _on_anchor(cadence, anchor, failed_on):
            continue
        ran_then = any(day == failed_on for day, _ in past)
        since = [status for day, status in past if day >= failed_on]
        if ran_then and all(status == "error" for status in since):
            return "retry"
    return None


def due(base: Path, today: dt.date) -> list:
    runs = load_runs(base)
    lenses = []
    for folder in sorted(p for p in (base / LENSES_DIR).iterdir() if p.is_dir()):
        parsed = read_frontmatter(folder / "prompt.md")
        if not parsed:
            print(f"lens_due: {folder.name}: prompt.md frontmatter unreadable",
                  file=sys.stderr)
            continue
        lenses.append((str(parsed[0].get("id") or folder.name), parsed[0]))
    ids = [lens_id for lens_id, _ in lenses]
    result = []
    for lens_id, meta in lenses:
        if ids.count(lens_id) > 1:
            print(f"lens_due: {lens_id}: id declared by more than one folder",
                  file=sys.stderr)
            continue
        if meta.get("status") != "active":
            continue
        reason = why_due(meta, runs.get(lens_id, []), today)
        if reason:
            result.append((lens_id, reason))
    return result


def main(argv=None) -> int:
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("due")
    command.add_argument("--base", required=True)
    command.add_argument("--today", type=dt.date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    base = Path(args.base).resolve()
    if not (base / LENSES_DIR).is_dir():
        print(f"lens_due: no lens registry at {base / LENSES_DIR}", file=sys.stderr)
        return 2
    today = args.today or dt.datetime.now(dt.timezone.utc).date()
    for lens_id, reason in due(base, today):
        print(f"{lens_id} {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
