#!/usr/bin/env python3
"""Deterministic calendar-aggregation reconciler for CALENDAR.md.

The calendar aggregate has the same silent-drop failure mode as TASKS.md (a
"regenerate from all notes" step the autonomous tick downgrades at scale), but
it cannot be reconciled the same way: the CALENDAR.md aggregate carries no stable
``^meeting-id`` (unlike ``^task-id`` in TASKS.md), source events frequently lack
an anchor, and dates are often fuzzy (``~середина 2026-07``, ranges). Keying by
(date, text) would be brittle and produce false positives.

So the check is deliberately COARSE: a note that carries at least one FUTURE
``📅`` line in its BODY but whose ``[[note-id]]`` appears in NO forward-facing
CALENDAR section (Recurring / Upcoming / Deadlines — everything except Past) has
had its events dropped wholesale. Per-event precision is not attempted; a note
with several future events, one of them aggregated, is considered covered.

**Coverage is partial and this is BEST-EFFORT, not a deterministic gate** (unlike
the task reconciler, which works because ``^task-id`` anchors are genuinely
authored). Many calendar events are synthesized from meeting PROSE and never
appear as a ``- 📅`` body line — those have no anchor a script can diff, so a drop
of a prose-only event is invisible here. This catches drops of ``📅``-anchored
events only. The durable protection is the nightly lint scan surfacing what it
CAN see; the in-process check is a best-effort assist, not a guarantee.

Read-only: never writes. ``/minder:mem:process`` Step 4.2 and the weekly lint scan both
call ``--report``; the update migration detects + nudges.

CLI:
  --report [--json] [--today YYYY-MM-DD]

``--today`` overrides the date used to decide "future" (for deterministic tests);
it defaults to the real current date.

Exit status: 0 on success (a backlog is not an error); 2 when the reconciler
itself could not run; 3 on a parser mismatch — forward-facing calendar lines
present but no note-id parsed, which must never be reported as a clean or
fully-orphaned result.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from _common import configure_std_streams  # type: ignore

DEFAULT_ROOTS = ("_records", "1_projects", "2_areas", "3_resources")

# A `- 📅 …` event line in a note body.
#
# Two tiers, because the date string is written by a model following a prose
# spec and the bold wrapper is a convention, not a guarantee. `_EVENT_BOLD_RE`
# takes the bold span when it is there — that span IS the event's own date, and
# preferring it keeps a date mentioned later in the same line (a different
# event, a deadline in the description) from being read as this one's. Without
# a bold span the whole remainder is handed to the date search instead of the
# line being skipped outright, which is what a `$`-shaped assumption would do.
_EVENT_RE = re.compile(r"^\s*- 📅\s+(.+)$")
_EVENT_BOLD_RE = re.compile(r"^\s*- 📅\s+\*\*(.+?)\*\*")
# First YYYY-MM-DD or YYYY-MM anywhere in the (possibly fuzzy) date string.
_DATE_RE = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")
# A `[[note-id]]` or `[[note-id|alias]]` wikilink (alias stripped on use).
_WIKILINK_RE = re.compile(r"\[\[([^\]]+?)\]\]")
_HEADING_RE = re.compile(r"^## (.+?)\s*$")
# Everything before Past is forward-facing.
_PAST_HEADING_RE = re.compile(r"^## Past\b")
# Fenced code block delimiter — `- 📅` inside a ``` example is not a real event.
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def event_date_string(line: str) -> str | None:
    """The date span of a `- 📅` event line, or None when the line is not one.

    Prefers the bold span; falls back to the whole remainder of the line.
    """
    bold = _EVENT_BOLD_RE.match(line)
    if bold:
        return bold.group(1)
    plain = _EVENT_RE.match(line)
    return plain.group(1) if plain else None


def count_event_lines(lines: list[str]) -> int:
    """`- 📅` lines regardless of whether a date parsed — the self-check denominator."""
    return sum(1 for line in lines if _EVENT_RE.match(line))


class ParserMismatch(RuntimeError):
    """The aggregate has forward-facing entries but none yielded a note-id."""


def _first_future_date(date_str: str, today: _dt.date) -> bool:
    """True if the date string's first parseable YYYY-MM(-DD) is >= today.

    Fuzzy / unparseable strings return False — they are never flagged (no
    false positives from `~середина июля` and friends).
    """
    m = _DATE_RE.search(date_str)
    if not m:
        return False
    year, month = int(m.group(1)), int(m.group(2))
    day = int(m.group(3)) if m.group(3) else 1
    try:
        d = _dt.date(year, month, day)
    except ValueError:
        return False
    # A year-month with no day is future only when its month is STRICTLY after
    # the current month — a day-less date in the current month is ambiguous
    # (could be mid-month past), so it is not flagged (conservative, coarse).
    if m.group(3) is None:
        return (year, month) > (today.year, today.month)
    return d >= today


def scan_note_future_event_notes(base: Path, today: _dt.date, roots=DEFAULT_ROOTS) -> set[str]:
    """Note-ids that carry at least one parseable FUTURE ``📅`` event."""
    notes: set[str] = set()
    for root in roots:
        root_dir = base / root
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*.md")):
            if path.name == "README.md":
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            in_fence = False
            for line in lines:
                if _FENCE_RE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                date_str = event_date_string(line)
                if date_str is not None and _first_future_date(date_str, today):
                    notes.add(path.stem)
                    break
    return notes


def calendar_forward_notes(path: Path) -> set[str]:
    """Note-ids wikilinked from any forward-facing CALENDAR section.

    Raises `ParserMismatch` when forward-facing lines plainly contain `[[` and
    none of them yielded a note-id. Zero linked notes over a non-empty calendar
    is not an empty calendar — it is this parser failing to read a format it
    owns, and reporting it as "every future event is an orphan" is how a
    completeness gate returns garbage confidently.
    """
    linked: set[str] = set()
    in_past = False
    forward_with_links = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return linked
    for line in lines:
        if _HEADING_RE.match(line):
            in_past = bool(_PAST_HEADING_RE.match(line))
            continue
        if in_past:
            continue
        if "[[" in line:
            forward_with_links += 1
        for m in _WIKILINK_RE.finditer(line):
            linked.add(m.group(1).split("|")[0].strip())  # drop |alias
    if not linked and forward_with_links:
        raise ParserMismatch(
            f"{path}: {forward_with_links} forward-facing line(s) carry `[[`, "
            "0 note-ids parsed. The calendar is not empty — this parser cannot read it."
        )
    return linked


def reconcile(base: Path, calendar_path: Path, today: _dt.date, roots=DEFAULT_ROOTS) -> dict:
    future_notes = scan_note_future_event_notes(base, today, roots)
    forward_notes = calendar_forward_notes(calendar_path)
    orphans = sorted(future_notes - forward_notes)
    return {
        "future_event_note_count": len(future_notes),
        "calendar_forward_note_count": len(forward_notes),
        "orphan_note_count": len(orphans),
        "orphan_notes": orphans,
        "consistent": len(orphans) == 0,
    }


def _default_calendar_path(base: Path) -> Path:
    return base / "_system" / "CALENDAR.md"


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="zettelkasten base dir")
    parser.add_argument("--calendar", type=Path, default=None, help="CALENDAR.md path")
    parser.add_argument("--report", action="store_true", required=True,
                        help="print reconciliation status (read-only)")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--today", default=None, help="override today (YYYY-MM-DD, for tests)")
    args = parser.parse_args(argv)

    base = args.base
    calendar_path = args.calendar or _default_calendar_path(base)
    if not calendar_path.is_file():
        print(f"error: CALENDAR.md not found at {calendar_path}", file=sys.stderr)
        return 2

    if args.today:
        today = _dt.date.fromisoformat(args.today)
    else:
        today = _dt.date.today()

    try:
        result = reconcile(base, calendar_path, today)
    except ParserMismatch as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"future-event notes: {result['future_event_note_count']} "
              f"| in calendar: {result['calendar_forward_note_count']} "
              f"| orphan notes: {result['orphan_note_count']} "
              f"| consistent: {result['consistent']}")
        for nid in result["orphan_notes"]:
            print(f"  orphan-note [[{nid}]] — has a future 📅 event, absent from CALENDAR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
