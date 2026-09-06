#!/usr/bin/env python3
"""Minder Memory lint Scan A.11 — content markup canonicalization.

Heals `content_type` drift and flags missing `content_angle` on knowledge
notes carrying `content_potential`, so a drifted type never silently falls
out of the content pipeline's routing. `/minder:mem:process` Q14 constrains its own
output to the canonical five; this is the post-write gate for existing notes
and any incoming drift (manual edits, older notes, future producers).

Scope: PARA + archive knowledge notes with `content_potential` set (the
routing gate — a drift type on a non-content note is irrelevant).

`CANON_MAP` is the SINGLE source of truth for the drift → canonical mapping.
Two classes:
- synonym (`strong` floor): the declared value is an unambiguous alias for
  exactly one canonical type and canonicalizes deterministically regardless
  of body. Qualifies for the ENGINE_DOCTRINE §3.1 autonomous-resolution
  exception → applied in place (mode=fix) with an Evidence-Trail note. Silent,
  logged, reversible.
- judgment (`weak` floor): the value could map to 2+ canonical types. NEVER
  applied here — emitted with the default target + alternatives for the lint
  LLM verdict layer to route (reviewed apply-with-validate / surfaced
  CLARIFICATION). Owner decides on a genuine judgment call.

Unknown drift value (not in `CANON_MAP`) → emitted, never guessed.
Missing/empty `content_angle` (with content_potential set) → emitted (flag);
the draft-maintainer proposes the hook, never this helper.
Missing/empty `content_type` (with content_potential set) → emitted (flag).

`story` is canonical and never touched.

Output: JSONL on stdout, one event per finding. Exit 0 always.
mode=scan: report only. mode=fix: apply synonym autofixes in place.

Usage:
    python3 lint_content_markup.py [--mode scan|fix] [--root <path>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from _common import (
    find_evidence_trail_bounds,
    read_frontmatter,
    repo_root,
    today_iso,
    configure_std_streams,
)


# The canonical five — `/minder:mem:process` Q14 closed set. `story` included
# (canonical); never a drift target unless a CANON_MAP row points to it.
CANONICAL_FIVE: frozenset[str] = frozenset(
    {"expert", "reflection", "story", "insight", "observation"}
)

# SINGLE SoT for the drift → canonical mapping.
#   floor: "strong" → deterministic synonym, autofix in place.
#          "weak"   → judgment call, emit default + alternatives, never auto-apply.
#   target: the default / synonym canonical type.
#   alternatives: other plausible canonical types (judgment rows only) —
#                 surfaced so the owner can pick a non-default at resolve time.
CANON_MAP: dict[str, dict] = {
    # --- synonym (strong) — the declared value IS the answer ---
    "technical": {"target": "expert", "floor": "strong"},
    "technical-decision": {"target": "expert", "floor": "strong"},
    "practice": {"target": "expert", "floor": "strong"},
    "personal": {"target": "reflection", "floor": "strong"},
    # --- judgment (weak) — could map to 2+ canonical types ---
    "idea": {"target": "insight", "floor": "weak", "alternatives": ["observation"]},
    "decision": {"target": "insight", "floor": "weak", "alternatives": ["expert"]},
    "principle": {"target": "insight", "floor": "weak", "alternatives": ["expert"]},
    "framework": {"target": "insight", "floor": "weak", "alternatives": ["expert"]},
    "product-insight": {
        "target": "insight", "floor": "weak", "alternatives": ["expert"],
    },
}

# PARA + archive — where content-flagged knowledge notes live. Records
# (`_records/`) never carry content_potential; hubs / registries / views /
# state / constitution are out of scope by construction.
SCOPE_INCLUDE: tuple[str, ...] = (
    "1_projects/",
    "2_areas/",
    "3_resources/",
    "4_archive/",
)


def in_scope(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    return any(rel.startswith(incl) for incl in SCOPE_INCLUDE)


def walk_md_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.md"):
        if p.is_file() and in_scope(p, root):
            yield p


def has_content_potential(fm: dict) -> bool:
    """A note is a content candidate when content_potential is high|medium."""
    return fm.get("content_potential") in ("high", "medium")


def is_blank(value) -> bool:
    """content_angle / content_type counts as missing when absent, None,
    empty string, or empty/blank-only list."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len([v for v in value if isinstance(v, str) and v.strip()]) == 0
    return False


def prepend_evidence_trail(body: str, entry: str) -> str:
    """Prepend a dated Evidence-Trail line (most-recent-first), creating the
    `## Evidence Trail` section at the end of the body if absent."""
    line = f"- {entry}\n"
    bounds = find_evidence_trail_bounds(body)
    if bounds is None:
        if body.endswith("\n\n"):
            sep = ""
        elif body.endswith("\n"):
            sep = "\n"
        else:
            sep = "\n\n"
        return f"{body}{sep}## Evidence Trail\n\n{line}"
    start, _end = bounds
    return body[:start] + line + body[start:]


_FM_SPLIT_RE = re.compile(r"^(---\n)(.*?\n)(---\n)(.*)$", re.DOTALL)
_CT_LINE_RE = re.compile(r"^(content_type:[ \t]*)(.*)$", re.MULTILINE)


def _split_frontmatter_text(text: str):
    """(open, frontmatter, close, body) or None — byte-exact, no YAML round-trip."""
    m = _FM_SPLIT_RE.match(text)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3), m.group(4)


def apply_content_type(path: Path, new_type: str, evidence_entry: str) -> bool:
    """Targeted, format-preserving content_type rewrite.

    Changes ONLY the `content_type:` line value (and prepends an Evidence-Trail
    line to the body) — every other byte of the owner's frontmatter is preserved
    verbatim (quote style, list indentation, key order, blank lines). This keeps
    the autofix a minimal intervention instead of re-dumping the whole frontmatter
    through PyYAML. Returns False if the file has no frontmatter or no
    content_type line. Shared by the synonym autofix here and the owner-resolved
    judgment apply path (e.g. /minder:mem:resolve-clarifications, backfill).
    """
    text = path.read_text(encoding="utf-8")
    parts = _split_frontmatter_text(text)
    if parts is None:
        return False
    open_, fm, close, body = parts
    new_fm, n = _CT_LINE_RE.subn(lambda mm: f"{mm.group(1)}{new_type}", fm)
    if n == 0:
        return False
    new_body = prepend_evidence_trail(body, evidence_entry)
    path.write_text(open_ + new_fm + close + new_body, encoding="utf-8")
    return True


_ANGLE_LINE_RE = re.compile(r"^content_angle:[ \t]+(\S.*?)[ \t]*$", re.MULTILINE)
_LIST_INDENT_RE = re.compile(r"^([ \t]+)- ", re.MULTILINE)


def normalize_content_angle_to_list(path: Path) -> bool:
    """Convert a single-string `content_angle:` to a 1-element YAML list,
    preserving the scalar verbatim (quotes included) and matching the note's own
    list indentation. No-op if it is already a list, missing, or a block/anchor
    scalar. Targeted — only the content_angle line is rewritten (+ the one
    inserted list item); every other byte is preserved.
    """
    text = path.read_text(encoding="utf-8")
    parts = _split_frontmatter_text(text)
    if parts is None:
        return False
    open_, fm, close, body = parts
    m = _ANGLE_LINE_RE.search(fm)
    if not m:
        return False  # already a list (line ends after the colon) or absent
    value = m.group(1)
    if value[:1] in "&*>|":  # anchor / alias / block scalar — leave for a human
        return False
    indent_m = _LIST_INDENT_RE.search(fm)
    indent = indent_m.group(1) if indent_m else "  "
    new_fm = fm[:m.start()] + f"content_angle:\n{indent}- {value}" + fm[m.end():]
    path.write_text(open_ + new_fm + close + body, encoding="utf-8")
    return True


def classify_content_type(raw: str) -> dict:
    """Return a routing dict for a non-canonical content_type value.

    kind ∈ {synonym, judgment, unknown}. Pure — no I/O, no body read.
    """
    row = CANON_MAP.get(raw)
    if row is None:
        return {"kind": "unknown", "floor": "weak"}
    if row["floor"] == "strong":
        return {"kind": "synonym", "floor": "strong", "target": row["target"]}
    return {
        "kind": "judgment",
        "floor": "weak",
        "target": row["target"],
        "alternatives": row.get("alternatives", []),
    }


def process_file(path: Path, root: Path, mode: str) -> list[dict]:
    parsed = read_frontmatter(path)
    if parsed is None:
        return []
    fm, body = parsed
    if not has_content_potential(fm):
        return []

    rel = path.relative_to(root).as_posix()
    events: list[dict] = []

    # --- content_type ---
    ctype = fm.get("content_type")
    if is_blank(ctype):
        events.append({
            "kind": "content-type-missing",
            "path": rel,
            "floor": "weak",
            "tier_hint": "surfaced",
            "applied": False,
            "reason": "content_potential set, content_type missing",
        })
    elif isinstance(ctype, str) and ctype not in CANONICAL_FIVE:
        routing = classify_content_type(ctype)
        if routing["kind"] == "synonym":
            target = routing["target"]
            applied = False
            if mode == "fix":
                applied = apply_content_type(
                    path, target,
                    f"{today_iso()}: content_type canonicalized "
                    f"{ctype} → {target} (content-type-canon-autofix)",
                )
                fm = {**fm, "content_type": target}  # keep angle-check consistent
            events.append({
                "kind": "content-type",
                "path": rel,
                "raw": ctype,
                "target": target,
                "floor": "strong",
                "tier_hint": "autofix",
                "applied": applied,
                "reason": "synonym",
            })
        elif routing["kind"] == "judgment":
            events.append({
                "kind": "content-type",
                "path": rel,
                "raw": ctype,
                "target": routing["target"],
                "alternatives": routing["alternatives"],
                "floor": "weak",
                "tier_hint": "clarify",
                "applied": False,
                "reason": "judgment",
            })
        else:  # unknown
            events.append({
                "kind": "content-type-unknown",
                "path": rel,
                "raw": ctype,
                "floor": "weak",
                "tier_hint": "surfaced",
                "applied": False,
                "reason": "not-in-canon-map",
            })

    # --- content_angle ---
    angle = fm.get("content_angle")
    if isinstance(angle, str) and angle.strip():
        # uniform shape: a single string is normalized to a 1-element list
        # (deterministic, strong floor — silent autofix).
        applied = False
        if mode == "fix":
            applied = normalize_content_angle_to_list(path)
        events.append({
            "kind": "content-angle-format",
            "path": rel,
            "floor": "strong",
            "tier_hint": "autofix",
            "applied": applied,
            "reason": "string→list",
        })
    elif is_blank(angle):
        events.append({
            "kind": "content-angle",
            "path": rel,
            "floor": "weak",
            "tier_hint": "surfaced",
            "applied": False,
            "reason": "content_potential set, content_angle missing",
        })
    # else: already a list → uniform, no event

    return events


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["scan", "fix"], default="scan",
        help="scan: report events without writing. fix: apply synonym "
             "autofixes in place.",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="Zettelkasten root (default: from MINDER_MEMORY_BASE / script-relative "
             "resolution). Pass an explicit path for tests.",
    )
    args = parser.parse_args(argv)

    root = (args.root or repo_root()).resolve()

    for md in walk_md_files(root):
        for ev in process_file(md, root, args.mode):
            sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
