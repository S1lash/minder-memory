#!/usr/bin/env python3
"""Deterministic task-aggregation reconciler for TASKS.md.

Splits the deterministic part of task aggregation — finding which note
``- [ ]`` items never reached the ``TASKS.md`` aggregate — from the judgment
part (classifying orphans into Action / Waiting / Delegate). Walking notes and
diffing task-ids is cheap and unbounded; only the orphans it surfaces need LLM
classification. This is the safety net that makes the aggregation silent-drop
recoverable and self-checking: the failure mode is a full "scan ALL notes" that
the autonomous ``/minder:mem:process`` tick quietly downgrades to a per-batch append at
scale, so tasks accumulate un-aggregated (a full-scan regen once recovered 452).

Task identity for the aggregate-presence check is the ``^task-id`` string. The
same id intentionally recurs across a meeting record and its derived knowledge
notes (one logical task, many notes), so an id present anywhere in TASKS.md is
aggregated. Keying by (note, id) would false-flag every derived copy as orphan.

Read-only by design: the reconciler never writes. Orphans are always re-derivable
from the notes, so there is nothing to materialise — ``/minder:mem:process
--reconcile-tasks`` (the classifier) and the weekly lint scan both call ``--report``
and act on the live result. Keeping it read-only also keeps engine migrations off
owner-data (they detect + nudge, never mutate TASKS.md).

CLI:
  --report [--json]   reconciliation status + orphan list (read-only)

Exit status: 0 on success (a backlog is not an error); 2 when the reconciler
itself could not run (bad paths, unreadable TASKS.md); 3 when the aggregate has
open-task lines but none parsed — a parser mismatch, which must never be
reported as a clean or fully-orphaned result.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import configure_std_streams  # type: ignore

# Note roots scanned for tasks. 4_archive is intentionally excluded — an
# archived note's `- [ ]` items must not be resurrected as orphans (mirrors the
# Stale-preservation philosophy: manual review is not overridden).
DEFAULT_ROOTS = ("_records", "1_projects", "2_areas", "3_resources")

# An OPEN task line. `- [x]` (done) is deliberately not matched: completed
# tasks are not orphans.
_OPEN_TASK_RE = re.compile(r"^\s*- \[ \] (.*)$")
# The `^{id}` anchor, ANYWHERE on the line — never pinned to end-of-line.
#
# The line is written by a model following a prose spec, and two real bases
# diverged on where the record reference sits relative to the anchor:
#
#     - [ ] {text} — [[record]] ^task-id
#     - [ ] {text} ^task-id — `record-id`
#
# A regex anchored to `$` matches the first shape and misses the second — and
# because the miss looks exactly like "this base has no tasks", one clone
# reported 100% of its 859 note task-ids as orphans while the completeness gate
# treated that as truth. Both shapes now parse identically.
#
# The leading `(?:^|\s)` keeps an arithmetic `2^10` in task text from reading as
# an anchor: a real anchor is always its own whitespace-separated token.
_TASK_ANCHOR_RE = re.compile(r"(?:^|\s)\^([\w-]+)\b")
_HEADING_RE = re.compile(r"^## (.+?)\s*$")
_STALE_HEADING_RE = re.compile(r"^## Stale\b")
# A fenced code block delimiter (``` or ~~~, any indent) — task-like lines
# inside a fence are documentation examples, not real tasks.
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def parse_task_line(line: str) -> tuple[list[str], str]:
    """`(task_ids, text)` for an open task line, `([], "")` for anything else.

    ALL anchors on the line are returned, not just one. A line carrying two ids
    is a real shape in owner data — one utterance that resolved into two tracked
    tasks — and picking either end of the line silently drops the other, which
    then reads as an orphan forever.

    The text is the line with every anchor token removed, so the same task
    renders identically whichever serialisation a note used.
    """
    m = _OPEN_TASK_RE.match(line)
    if not m:
        return [], ""
    body = m.group(1)
    matches = list(_TASK_ANCHOR_RE.finditer(body))
    if not matches:
        return [], ""
    text = _TASK_ANCHOR_RE.sub(" ", body).strip()
    return [a.group(1) for a in matches], text


def count_open_task_lines(lines: list[str]) -> int:
    """Open-task lines regardless of whether an anchor was found.

    The denominator for the parser self-check: a file full of `- [ ]` lines
    from which zero ids parse is a broken parser, not an empty aggregate.
    """
    return sum(1 for line in lines if _OPEN_TASK_RE.match(line))


class ParserMismatch(RuntimeError):
    """The aggregate has open-task lines but none yielded an id."""


class Orphan:
    __slots__ = ("task_id", "note_id", "text")

    def __init__(self, task_id: str, note_id: str, text: str) -> None:
        self.task_id = task_id
        self.note_id = note_id
        self.text = text

    def as_dict(self) -> dict:
        return {"task_id": self.task_id, "note_id": self.note_id, "text": self.text}


def scan_note_tasks(base: Path, roots=DEFAULT_ROOTS) -> dict[str, Orphan]:
    """Map every open-task ``^task-id`` found in notes to a representative note.

    First occurrence wins for the representative note/text (deterministic by
    sorted path). Multiple notes sharing an id collapse to one entry — that is
    the intended one-task-many-notes shape.
    """
    found: dict[str, Orphan] = {}
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
            note_id = path.stem
            in_fence = False
            for line in lines:
                if _FENCE_RE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue  # a `- [ ]` inside a ``` example is not a real task
                task_ids, text = parse_task_line(line)
                for task_id in task_ids:
                    found.setdefault(task_id, Orphan(task_id, note_id, text))
    return found


def _parse_ids(lines: list[str]) -> tuple[set[str], set[str]]:
    """Split aggregate task-ids into (active, stale) over already-read lines.

    Active = task-ids under any heading before ``## Stale`` (Action / Waiting /
    Delegate / Someday / Personal / Unaggregated). Stale = ids under the
    ``## Stale`` section (owner's manual review — never resurrected).
    """
    active: set[str] = set()
    stale: set[str] = set()
    in_stale = False
    for line in lines:
        if _HEADING_RE.match(line):
            in_stale = bool(_STALE_HEADING_RE.match(line))
            continue
        task_ids, _ = parse_task_line(line)
        (stale if in_stale else active).update(task_ids)
    return active, stale


def parse_tasks_md(path: Path) -> tuple[set[str], set[str]]:
    """Return (active_ids, stale_ids) from TASKS.md on disk.

    Raises `ParserMismatch` when the file plainly HAS open-task lines and none
    of them yielded an id. That state is not an empty aggregate — it is this
    module failing to read a format it is supposed to own, and reporting it as
    "0 aggregated, everything is an orphan" is how a load-bearing completeness
    gate returns garbage confidently. Silence here is the actual defect; the
    regex that caused it was only the occasion.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return set(), set()
    active, stale = _parse_ids(lines)
    if not active and not stale:
        candidates = count_open_task_lines(lines)
        if candidates:
            sample = [ln.strip() for ln in lines if _OPEN_TASK_RE.match(ln)][:3]
            raise ParserMismatch(
                f"{path}: {candidates} open-task line(s) present, 0 task-ids parsed. "
                "The aggregate is not empty — this parser cannot read it. "
                "First lines: " + " | ".join(sample)
            )
    return active, stale


def find_orphans(base: Path, tasks_path: Path, roots=DEFAULT_ROOTS) -> list[Orphan]:
    """Note task-ids present in no active/stale section of TASKS.md, sorted."""
    note_tasks = scan_note_tasks(base, roots)
    active, stale = parse_tasks_md(tasks_path)
    aggregated = active | stale
    return [note_tasks[tid] for tid in sorted(note_tasks) if tid not in aggregated]


def reconcile(base: Path, tasks_path: Path, roots=DEFAULT_ROOTS) -> dict:
    note_tasks = scan_note_tasks(base, roots)
    active, stale = parse_tasks_md(tasks_path)
    aggregated = active | stale
    orphans = [note_tasks[tid] for tid in sorted(note_tasks) if tid not in aggregated]
    # Reverse direction (informational): active aggregate ids no longer present
    # as an open task in any note — completion / deletion candidates.
    note_ids = set(note_tasks)
    dangling = sorted(active - note_ids)
    return {
        "note_task_count": len(note_tasks),
        "active_count": len(active),
        "stale_count": len(stale),
        "orphan_count": len(orphans),
        "orphans": [o.as_dict() for o in orphans],
        "dangling_active_count": len(dangling),
        "dangling_active": dangling,
        "consistent": len(orphans) == 0,
    }


def _default_tasks_path(base: Path) -> Path:
    return base / "_system" / "TASKS.md"


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="zettelkasten base dir")
    parser.add_argument("--tasks", type=Path, default=None, help="TASKS.md path")
    parser.add_argument("--report", action="store_true", required=True,
                        help="print reconciliation status (read-only)")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)

    base = args.base
    tasks_path = args.tasks or _default_tasks_path(base)
    if not tasks_path.is_file():
        print(f"error: TASKS.md not found at {tasks_path}", file=sys.stderr)
        return 2

    try:
        result = reconcile(base, tasks_path)
    except ParserMismatch as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"note tasks: {result['note_task_count']} | active: {result['active_count']} "
              f"| stale: {result['stale_count']} | orphans: {result['orphan_count']} "
              f"| dangling-active: {result['dangling_active_count']} "
              f"| consistent: {result['consistent']}")
        for o in result["orphans"]:
            print(f"  orphan ^{o['task_id']}  [[{o['note_id']}]]  {o['text'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
