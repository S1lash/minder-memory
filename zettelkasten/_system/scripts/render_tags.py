#!/usr/bin/env python3
"""Render the managed zone of `_system/registries/TAGS.md` — a census of the
`tags:` axis across the knowledge layer.

Deterministic, no LLM. Reads `tags:` lists from note frontmatter, groups them
by namespace (`category/value` → `category`), and writes one table per
namespace plus the totals. TAGS.md is a DERIVED surface per the Identity
Contract: the numbers in it are a projection of the corpus, never hand-kept.

This script writes ONLY the content between the registry's managed-zone
markers:
    <!-- AUTO-GENERATED: tag-registry ... -->
    ...
    <!-- END AUTO-GENERATED: tag-registry -->
Everything outside the markers — the preamble with its three-axis table and
the `## Notes` section — is owner-owned and never touched, same contract as
the SOUL.md Values zone and the cognitive-model hub.

Scope (the `## Notes` section of TAGS.md is the spec; this mirrors it):

    every `*.md` under the base EXCEPT the five layers that own their own
    pipelines — `_records/`, `_sources/`, `_system/`, `0_constitution/`,
    `6_posts/`

In practice that is the PARA layers (`1_projects/`, `2_areas/`,
`3_resources/`, `4_archive/`) plus the synthesis layer (`5_meta/mocs/`) and
the engine quick-reference cards (`5_skills/`). Two mechanical exclusions on
top, matching `render_index.py`:

    *.template.md   — engine seeds co-located in a scanned dir (a released
                      skeleton strips the suffix in place), never owner notes
    symlinks        — a symlinked note would be counted twice

Tags are counted as literal labels, exactly as stored. No normalisation, no
canonicalisation: convention drift (`cat/sub` vs `cat-sub`) is tolerated by
design and surfaced by the census rather than silently merged. A tag repeated
inside one note's `tags:` list counts once — a use is a note, not a mention.

Idempotency: the managed zone is rendered, then compared (timestamp line
excluded) to what is on disk. Identical → NO write at all, so a `/minder:mem:maintain`
run twice produces a byte-identical tree.

First run on a base whose TAGS.md predates the markers adopts the legacy
layout deterministically: the region from the `**Total unique tags:**` line up
to the `## Notes` heading is the generated region, and it is replaced by the
marked zone. Preamble and Notes survive untouched.

Usage:
    python3 render_tags.py [--base PATH] [--tags PATH] [--dry-run] [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from _common import (
    configure_std_streams,
    now_iso_utc,
    read_frontmatter,
    registries_dir,
    repo_root,
)

TAGS_REL = "registries/TAGS.md"

# Layers that own their own pipeline / store and never feed the tag census.
EXCLUDED_ROOTS: frozenset[str] = frozenset({
    "_records",
    "_sources",
    "_system",
    "0_constitution",
    "6_posts",
})

ZONE_START = (
    "<!-- AUTO-GENERATED: tag-registry — DO NOT EDIT BETWEEN MARKERS "
    "(maintained by render_tags.py) -->"
)
ZONE_END = "<!-- END AUTO-GENERATED: tag-registry -->"

SOURCE_COMMENT = (
    "<!-- Source: `tags:` frontmatter across the knowledge layer "
    "(everything except `_records/`, `_sources/`, `_system/`, "
    "`0_constitution/`, `6_posts/`). Scope spec: the Notes section below. -->"
)
REGEN_PREFIX = "<!-- Last regenerated: "

TOTALS_ANCHOR = "**Total unique tags:**"
NOTES_HEADING = "## Notes"

UNCATEGORIZED_HEADING = "Uncategorized (no slash)"


class TagRenderError(Exception):
    """Recoverable render failure — caller skips the step, never crashes."""


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------

def _in_scope(rel: str) -> bool:
    top = rel.split("/", 1)[0]
    if top in EXCLUDED_ROOTS:
        return False
    return not rel.endswith(".template.md")


def collect_tags(base: Path) -> tuple[Counter, int]:
    """Count tag uses across in-scope notes. Returns (counter, notes_scanned).

    A note contributes each distinct tag in its `tags:` list once.
    """
    counts: Counter = Counter()
    notes = 0
    for path in sorted(base.rglob("*.md")):
        if path.is_symlink():
            continue
        rel = path.relative_to(base).as_posix()
        if not _in_scope(rel):
            continue
        parsed = read_frontmatter(path)
        if parsed is None:
            continue
        raw = parsed[0].get("tags")
        if not isinstance(raw, list):
            continue
        seen: set[str] = set()
        for item in raw:
            if isinstance(item, str) and item.strip():
                seen.add(item.strip())
        if not seen:
            continue
        notes += 1
        for tag in seen:
            counts[tag] += 1
    return counts, notes


def _namespace(tag: str) -> str | None:
    """Namespace of a tag, or None for a bare label with no slash."""
    head, sep, _ = tag.partition("/")
    if not sep or not head:
        return None
    return head


def group_by_namespace(counts: Counter) -> list[dict]:
    """Namespace buckets, ordered for rendering.

    Sections sort by total uses descending, then namespace ascending; the
    bare-label bucket renders last regardless of size. Inside a section, tags
    sort by uses descending then name ascending. Both orders are total — the
    render is stable across runs on identical input.
    """
    buckets: dict[str | None, list[tuple[str, int]]] = defaultdict(list)
    for tag, n in counts.items():
        buckets[_namespace(tag)].append((tag, n))

    sections: list[dict] = []
    for ns, rows in buckets.items():
        rows.sort(key=lambda kv: (-kv[1], kv[0]))
        sections.append({
            "namespace": ns,
            "heading": UNCATEGORIZED_HEADING if ns is None else ns.capitalize(),
            "rows": rows,
            "uses": sum(n for _, n in rows),
        })
    sections.sort(key=lambda s: (
        s["namespace"] is None,           # bare labels last
        -s["uses"],
        s["namespace"] or "",
    ))
    return sections


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_zone_body(sections: list[dict], unique: int, uses: int) -> str:
    lines: list[str] = [
        SOURCE_COMMENT,
        f"{REGEN_PREFIX}{now_iso_utc()} -->",
        "",
        f"{TOTALS_ANCHOR} {unique}",
        f"**Total uses:** {uses}",
        "",
        "---",
        "",
    ]
    if not sections:
        lines.append("_(no tags yet — populates as `/minder:mem:process` classifies content)_")
        lines.append("")
        return "\n".join(lines)
    for section in sections:
        lines.append(f"## {section['heading']} ({len(section['rows'])})")
        lines.append("")
        lines.append("| Tag | Uses |")
        lines.append("|---|---:|")
        for tag, n in section["rows"]:
            lines.append(f"| `{tag}` | {n} |")
        lines.append("")
    return "\n".join(lines)


def normalise_zone(text: str) -> str:
    """Zone content for the idempotency diff — drop the volatile timestamp
    line, strip trailing whitespace, trim trailing blanks."""
    out: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith(REGEN_PREFIX):
            continue
        out.append(line.rstrip())
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def find_zone(text: str) -> tuple[int, int] | None:
    """(content_start, content_end) between the markers, or None."""
    i_start = text.find(ZONE_START)
    if i_start < 0:
        return None
    line_end = text.find("\n", i_start)
    if line_end < 0:
        return None
    content_start = line_end + 1
    i_end = text.find(ZONE_END, content_start)
    if i_end < 0:
        return None
    return content_start, i_end


def _legacy_bounds(text: str) -> tuple[int, int] | None:
    """(start, end) of the pre-marker generated region.

    Runs from the `**Total unique tags:**` line to the `## Notes` heading
    (exclusive), or to EOF when the file has no Notes section. Returns None
    when the totals anchor is absent — the file is then not a TAGS.md this
    renderer recognises, and the caller surfaces a skip rather than guessing.
    """
    m = re.search(r"^\*\*Total unique tags:\*\*", text, re.MULTILINE)
    if m is None:
        return None
    start = m.start()
    n = re.search(r"^" + re.escape(NOTES_HEADING) + r"\s*$", text[start:], re.MULTILINE)
    end = start + n.start() if n else len(text)
    return start, end


def splice(tags_text: str, new_body: str) -> str:
    """Write the zone into the registry, adopting the legacy layout on first run."""
    if not new_body.endswith("\n"):
        new_body += "\n"
    bounds = find_zone(tags_text)
    if bounds is not None:
        start, end = bounds
        return tags_text[:start] + new_body + tags_text[end:]

    legacy = _legacy_bounds(tags_text)
    if legacy is None:
        raise TagRenderError(
            "no managed-zone markers and no `**Total unique tags:**` anchor — "
            "cannot locate the generated region"
        )
    start, end = legacy
    block = f"{ZONE_START}\n{new_body}{ZONE_END}\n"
    tail = tags_text[end:]
    if tail.startswith(NOTES_HEADING):
        block += "\n---\n\n"
    return tags_text[:start] + block + tail


def render(base: Path, tags_path: Path):
    """Returns (sections, unique, uses, notes, expected_body, tags_text)."""
    counts, notes = collect_tags(base)
    sections = group_by_namespace(counts)
    expected_body = render_zone_body(sections, len(counts), sum(counts.values()))
    if not tags_path.exists():
        raise TagRenderError(f"registry not found: {tags_path}")
    return (
        sections,
        len(counts),
        sum(counts.values()),
        notes,
        expected_body,
        tags_path.read_text(encoding="utf-8"),
    )


def _current_zone(tags_text: str) -> str | None:
    bounds = find_zone(tags_text)
    if bounds is None:
        return None
    return tags_text[bounds[0]:bounds[1]]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=None,
                        help="override the zettelkasten root to scan")
    parser.add_argument("--tags", type=Path, default=None,
                        help=f"override registry path (default: _system/{TAGS_REL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the rendered zone to stdout, do not write")
    parser.add_argument("--check", action="store_true",
                        help="exit 3 if the registry would change; never write")
    args = parser.parse_args(argv)

    base = args.base.resolve() if args.base else repo_root()
    tags_path = args.tags or (registries_dir(base) / "TAGS.md")

    try:
        sections, unique, uses, notes, expected_body, tags_text = render(base, tags_path)
    except TagRenderError as exc:
        # Best-effort, like the other maintain renderers: surface and skip,
        # never crash the maintain pipeline.
        print(json.dumps({"ok": False, "changed": False, "reason": str(exc)}))
        print(f"tag-registry: skipped — {exc}", file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 — unattended maintain step must never crash
        print(json.dumps({
            "ok": False, "changed": False,
            "reason": f"unexpected: {type(exc).__name__}: {exc}",
        }))
        print(f"tag-registry: skipped — unexpected {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 0

    if args.dry_run:
        sys.stdout.write(expected_body)
        return 0

    current = _current_zone(tags_text)
    # No markers yet → the legacy region is adopted, which is always a change.
    would_change = (
        current is None
        or normalise_zone(current) != normalise_zone(expected_body)
    )

    result = {
        "ok": True,
        "changed": would_change,
        "unique_tags": unique,
        "total_uses": uses,
        "namespaces": len(sections),
        "notes_scanned": notes,
    }

    if args.check:
        print(json.dumps(result))
        return 3 if would_change else 0

    if would_change:
        try:
            new_text = splice(tags_text, expected_body)
        except TagRenderError as exc:
            print(json.dumps({"ok": False, "changed": False, "reason": str(exc)}))
            print(f"tag-registry: skipped — {exc}", file=sys.stderr)
            return 0
        tmp = tags_path.with_suffix(tags_path.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(tags_path)

    print(json.dumps(result))
    print(
        f"wrote {tags_path.name} ({unique} unique tags, {uses} uses, "
        f"{len(sections)} namespaces, {notes} notes, "
        f"{'updated' if would_change else 'no change'})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
