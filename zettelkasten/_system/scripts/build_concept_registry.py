#!/usr/bin/env python3
"""Aggregate corpus concept mentions into `_system/registries/CONCEPTS.md`.

Walks `_records/{meetings,observations}/`, PARA folders (`1_projects/`,
`2_areas/`, `3_resources/`, `4_archive/`), and `5_meta/mocs/` for
`concepts:` frontmatter arrays, plus `_system/state/batches/*.json`
manifests for `concepts.upserts[]` type/subtype metadata.

Aggregation per concept name:
- `type`         — first chronological from batches (None if never typed)
- `subtype`      — first chronological from batches
- `first_seen`   — earliest mention date observed
- `last_seen`    — most recent mention date observed
- `mentions`     — total observed mentions across all sources
- `aliases`      — preserved from existing CONCEPTS.md owner edits

Output: `_system/registries/CONCEPTS.md` with a single `## Concepts
(sorted by mentions)` table. The matcher subagent in `/minder:mem:process`
Step 3.4.5 loads the full file (Sonnet handles the context cheaply);
the prior Top/Tail split is gone — it served no purpose once full
loading became the contract.

Idempotent: rebuilds the registry from scratch each invocation; only
the `aliases` column carries over from the prior file.

Emits structured events on stderr (one JSON per line) for
`log_maintenance.md` consumption by `/minder:mem:maintain`. Stdout is reserved
for the diff summary. Stats dict (returned by `build()` and emitted
to stdout / events) carries `total_concepts` and `total_mentions` —
manifest consumers (Minder) read these via the maintain batch
manifest, not from the rendered markdown.

Usage:
    python3 build_concept_registry.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from _common import (
    EMITTED_CONCEPT_TYPES,
    normalize_concept_name,
    read_frontmatter,
    repo_root,
    write_frontmatter,
    configure_std_streams,
)


CORPUS_DIRS: tuple[str, ...] = (
    "_records/meetings",
    "_records/observations",
    "1_projects",
    "2_areas",
    "3_resources",
    "4_archive",
    "5_meta/mocs",
)


DATE_FROM_FILENAME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})[-_]")


@dataclass
class ConceptAgg:
    name: str
    type: str | None = None
    subtype: str | None = None
    type_first_seen: date | None = None  # tie-break date for `type` chronology
    first_seen: date | None = None
    last_seen: date | None = None
    mentions: int = 0
    aliases: list[str] = field(default_factory=list)

    def update_type(self, candidate_type: str | None,
                    candidate_subtype: str | None,
                    when: date | None) -> None:
        """Apply chronological-first-wins rule for type assignment."""
        if not candidate_type:
            return
        # Pinned type from earlier batch wins.
        if self.type_first_seen is not None and when is not None and \
                when >= self.type_first_seen:
            return
        self.type = candidate_type
        self.subtype = candidate_subtype
        if when is not None:
            self.type_first_seen = when

    def observe(self, when: date | None) -> None:
        self.mentions += 1
        if when is None:
            return
        if self.first_seen is None or when < self.first_seen:
            self.first_seen = when
        if self.last_seen is None or when > self.last_seen:
            self.last_seen = when


def _emit_event(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, default=str), file=sys.stderr)


def _date_from_filename(path: Path) -> date | None:
    m = DATE_FROM_FILENAME_RE.match(path.name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _date_from_frontmatter(fm: dict) -> date | None:
    raw = fm.get("date") or fm.get("created") or fm.get("first_seen")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        for fmt_try in (raw[:10],):
            try:
                y, m, d = fmt_try.split("-")
                return date(int(y), int(m), int(d))
            except (ValueError, AttributeError):
                continue
    return None


def _walk_corpus(base: Path) -> Iterable[Path]:
    for sub in CORPUS_DIRS:
        root = base / sub
        if not root.exists():
            continue
        for p in root.rglob("*.md"):
            if p.name.startswith("README"):
                continue
            if "/templates/" in str(p) or "/.template" in p.name:
                continue
            yield p


def _harvest_frontmatter(base: Path,
                         agg: dict[str, ConceptAgg]) -> tuple[int, int]:
    """Walk corpus for `concepts:` arrays. Returns (files_scanned, mentions_seen)."""
    files = 0
    mentions = 0
    for path in _walk_corpus(base):
        files += 1
        result = read_frontmatter(path)
        if result is None:
            continue
        fm, _body = result
        raw = fm.get("concepts")
        if not raw or not isinstance(raw, list):
            continue
        when = _date_from_frontmatter(fm) or _date_from_filename(path)
        for entry in raw:
            name = normalize_concept_name(entry)
            if name is None:
                continue
            mentions += 1
            slot = agg.get(name)
            if slot is None:
                slot = ConceptAgg(name=name)
                agg[name] = slot
            slot.observe(when)
    return files, mentions


def _harvest_batches(base: Path, agg: dict[str, ConceptAgg]) -> int:
    """Walk batches/*.json for type/subtype metadata. Returns batches read."""
    batches_dir = base / "_system" / "state" / "batches"
    if not batches_dir.exists():
        return 0
    read = 0
    for path in sorted(batches_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _emit_event("batch-unparseable", path=str(path))
            continue
        read += 1
        ts = data.get("timestamp")
        when = _parse_batch_timestamp(ts)
        concepts_section = data.get("concepts")
        if not isinstance(concepts_section, dict):
            continue
        upserts = concepts_section.get("upserts")
        if not isinstance(upserts, list):
            continue
        for upsert in upserts:
            if not isinstance(upsert, dict):
                continue
            raw_name = upsert.get("name")
            name = normalize_concept_name(raw_name)
            if name is None:
                continue
            slot = agg.get(name)
            if slot is None:
                slot = ConceptAgg(name=name)
                agg[name] = slot
            ctype = upsert.get("type")
            if ctype not in EMITTED_CONCEPT_TYPES:
                ctype = None
            csub = upsert.get("subtype")
            if not isinstance(csub, str) or not csub:
                csub = None
            slot.update_type(ctype, csub, when)
    return read


def _parse_batch_timestamp(raw) -> date | None:
    if not isinstance(raw, str):
        return None
    head = raw[:10]
    try:
        y, m, d = head.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


# Existing CONCEPTS.md aliases preservation
_CONCEPTS_TABLE_ROW_RE = re.compile(
    r"^\|\s*([a-z0-9_]+)\s*\|"   # name
    r"[^|]*\|"                    # type
    r"[^|]*\|"                    # subtype
    r"[^|]*\|"                    # first_seen
    r"[^|]*\|"                    # last_seen
    r"\s*\d+\s*\|"                # mentions (must be integer — skips header row)
    r"\s*([^|]*?)\s*\|\s*$"       # aliases
)


def _load_existing_aliases(registry_path: Path) -> dict[str, list[str]]:
    if not registry_path.exists():
        return {}
    try:
        text = registry_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = _CONCEPTS_TABLE_ROW_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        aliases_cell = m.group(2).strip()
        if not aliases_cell or aliases_cell == "—":
            continue
        # comma-separated, normalised
        aliases = []
        for alias in aliases_cell.split(","):
            n = normalize_concept_name(alias.strip())
            if n is not None and n != name and n not in aliases:
                aliases.append(n)
        if aliases:
            out[name] = aliases
    return out


def _format_row(c: ConceptAgg) -> str:
    type_ = c.type or "—"
    subtype = c.subtype or "—"
    first = c.first_seen.isoformat() if c.first_seen else "—"
    last = c.last_seen.isoformat() if c.last_seen else "—"
    aliases = ", ".join(c.aliases) if c.aliases else "—"
    return (
        f"| {c.name} | {type_} | {subtype} | "
        f"{first} | {last} | {c.mentions} | {aliases} |"
    )


def render_registry(agg: dict[str, ConceptAgg],
                    today: date | None = None) -> str:
    today = today or date.today()
    sorted_concepts = sorted(
        agg.values(),
        key=lambda c: (-c.mentions, c.name),
    )

    header = (
        "---\n"
        f"last_updated: {today.isoformat()}\n"
        "---\n\n"
        "# Concept Registry — auto-regenerated by /minder:mem:maintain\n\n"
        "> Owner edits ONLY the `aliases` column. Lint applies aliases on\n"
        "> next pass. Other columns are auto-derived; owner edits will be\n"
        "> overwritten on regen.\n\n"
        "Schema: open-graph concept names. The `type` column mirrors\n"
        "Minder's `ConceptType` emit set (16 values; see\n"
        "`CONCEPT_TYPES.md`); `subtype` is free-form metadata; `aliases`\n"
        "is a comma-separated list of older / equivalent names that\n"
        "lint rewrites to this canonical name on the next pass.\n\n"
        "Counts (`total_concepts`, `total_mentions`) live in the\n"
        "`/minder:mem:maintain` batch manifest — derive on demand with\n"
        "`grep -c '^|' CONCEPTS.md` if you need a quick visual count.\n\n"
    )

    table_header = (
        "| name | type | subtype | first_seen | last_seen | mentions | aliases |\n"
        "|---|---|---|---|---|---|---|\n"
    )

    body_section = (
        "## Concepts (sorted by mentions)\n\n"
        f"{table_header}"
        + "\n".join(_format_row(c) for c in sorted_concepts)
        + ("\n" if sorted_concepts else "_(none — registry is empty)_\n")
    )

    return header + body_section


def build(base: Path) -> tuple[dict[str, ConceptAgg], dict]:
    agg: dict[str, ConceptAgg] = {}
    files_scanned, mentions_seen = _harvest_frontmatter(base, agg)
    batches_read = _harvest_batches(base, agg)
    registry_path = base / "_system" / "registries" / "CONCEPTS.md"
    existing_aliases = _load_existing_aliases(registry_path)
    for name, aliases in existing_aliases.items():
        slot = agg.get(name)
        if slot is None:
            # Owner-curated alias for a concept that no longer appears.
            # Preserve the alias row so the rewrite is not lost; mentions=0.
            slot = ConceptAgg(name=name)
            agg[name] = slot
        slot.aliases = aliases

    stats = {
        "files_scanned": files_scanned,
        "mentions_seen": mentions_seen,
        "batches_read": batches_read,
        "total_concepts": len(agg),
        "total_mentions": sum(c.mentions for c in agg.values()),
    }
    return agg, stats


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--root", type=Path, default=None)
    args = p.parse_args(argv)

    base = (args.root or repo_root()).resolve()
    registry_path = base / "_system" / "registries" / "CONCEPTS.md"

    agg, stats = build(base)
    rendered = render_registry(agg)

    prior_size = registry_path.stat().st_size if registry_path.exists() else 0

    if args.dry_run:
        print(f"DRY-RUN: would write {len(rendered)} bytes to {registry_path}")
        print(f"stats: {json.dumps(stats)}")
        return 0

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(rendered, encoding="utf-8")

    _emit_event(
        "concepts-registry-rebuilt",
        path=str(registry_path),
        prior_size=prior_size,
        new_size=len(rendered),
        **stats,
    )
    print(json.dumps({"ok": True, **stats}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
