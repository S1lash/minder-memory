#!/usr/bin/env python3
"""What a previous-shape role accumulated between runs, and where it lives.

Read by `roles_previous_plan.py` (which tells the concierge what a parked role
holds) and `roles_previous_selfcheck.py` (which proves the carry-over whole).
One reader, so the two can never disagree about what a role holds.

WHY THIS EXISTS

A role's assignment is what the owner asked for; its state is what the role
learnt. For a role that ran for months, the second is the larger half — a board
of work in flight, a reading of where the project stands, a health verdict per
item, a log of what it decided and why. The previous shape kept it in
`state.md` (a readable projection), `parts/*.json` (the data behind it) and
`decisions.jsonl` (the log).

Without this module the hand-off named those files only as proof that the role
had run, and the conversion plan did not mention them at all. Every byte
survived the move and nothing pointed at it, so the owner re-created the role
from its assignment alone and it woke up with no memory of anything. Data that
is present but unreferenced is lost in every way that matters to the person who
needs it.

WHAT IT DOES NOT DO

It does not copy the content into the plan. The files are the source of truth
and they sit beside it; a second copy would drift from them the moment the
owner edits either, and a ledger has no bound on its size. This reports what is
there, how much of it, and where — precisely enough that neither the owner nor
the concierge can walk past it.

Every path it emits is relative to the parked directory. That is the right base
for the plan, which sits there — and the wrong one for the hand-off, which is
read from the repository root. So the ONE conversion between them lives here as
`repo_path()`, and no caller builds a prefix of its own. A path with two owners
is how the hand-off came to carry `_previous/x/state.md` one line below
`<base>/_system/roles/_previous/x/`: both were plausible, neither resolved, and
each looked right beside the code that wrote it.
"""

from __future__ import annotations

import json
from pathlib import Path

RENDERED = "state.md"
DECISIONS = "decisions.jsonl"
PARTS_DIRNAME = "parts"
# The one home of the parked directory's name.
PARKED_DIRNAME = "_previous"


def repo_path(parked_relative: str, base_name: str) -> str:
    """A path this module emitted, as it resolves from the repository root.

    The hand-off is opened from there — by the owner, and by the test that
    proves every path in it is live.
    """
    return f"{base_name}/_system/roles/{PARKED_DIRNAME}/{parked_relative}"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _holdings(payload: dict) -> list:
    """Every list-of-records the part file holds, biggest first.

    Deliberately generic. The previous shape had several part archetypes and
    each named its content differently — `entries`, `items`, `assessments` —
    and a role could carry one this code has never seen. Keying off the shape
    of the value rather than off a list of known names means an unknown
    archetype is still counted rather than silently reported as empty, which is
    the failure this whole module exists to remove.
    """
    out = []
    for key, value in payload.items():
        if isinstance(value, list) and any(isinstance(v, dict) for v in value):
            out.append({"of": key, "count": len(value)})
    return sorted(out, key=lambda h: (-h["count"], h["of"]))


def _part(path: Path) -> dict:
    try:
        payload = json.loads(_read(path) or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "id": payload.get("part_id") or path.stem,
        "kind": payload.get("archetype") or "",
        "holds": _holdings(payload),
        "path": f"{path.parent.parent.name}/{PARTS_DIRNAME}/{path.name}",
    }


def inventory(role_dir: Path) -> dict:
    """What this role accumulated. Empty-but-present is reported as such.

    `has_memory` is about CONTENT, never about the presence of a file. The
    previous shape wrote `parts/*.json` on a tick that found nothing, with empty
    arrays inside — so "the files exist" answers a different question than "there
    is something here to carry". Keying off existence made an empty role announce
    that it «успела наработать память» and then list nothing, and let the
    self-check wave it through as carried.
    """
    rid = role_dir.name
    rendered = role_dir / RENDERED
    decisions = role_dir / DECISIONS
    parts_dir = role_dir / PARTS_DIRNAME

    parts = []
    if parts_dir.is_dir():
        parts = [_part(p) for p in sorted(parts_dir.glob("*.json"))]

    decided = 0
    if decisions.is_file():
        decided = sum(1 for line in _read(decisions).splitlines() if line.strip())

    records = sum(h["count"] for p in parts for h in p["holds"])
    rendered_chars = len(_read(rendered).strip()) if rendered.is_file() else 0

    return {
        "has_memory": bool(rendered_chars or decided or records),
        "rendered": ({"path": f"{rid}/{RENDERED}",
                      "chars": rendered_chars} if rendered.is_file() else None),
        "parts": parts,
        "decisions": ({"path": f"{rid}/{DECISIONS}",
                       "count": decided} if decisions.is_file() else None),
        "records": records,
        "directory": f"{rid}/",
    }


def summary_ru(inv: dict) -> str:
    """One line, in the owner's language, of what the role had accumulated.

    Empty string when it accumulated nothing — the caller then says «ни разу не
    запускалась» rather than printing a row of zeroes, which reads like a
    defect.
    """
    bits = []
    for part in inv["parts"]:
        for hold in part["holds"]:
            if hold["count"]:
                bits.append(f"{part['id']} — {hold['count']} зап.")
    out = ("по частям: " + ", ".join(bits)) if bits else ""
    if inv["decisions"] and inv["decisions"]["count"]:
        tail = f"решений в журнале — {inv['decisions']['count']}"
        out = f"{out}; {tail}" if out else tail
    return out
