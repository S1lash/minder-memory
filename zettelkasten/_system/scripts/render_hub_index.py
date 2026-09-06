#!/usr/bin/env python3
"""Render the managed zone of `_system/views/HUB_INDEX.md` — the registry of
every hub note on disk.

Deterministic, no LLM. Reads the frontmatter of `5_meta/mocs/hub-*.md` and
writes one row per hub, grouped by `status:`. HUB_INDEX.md is a DERIVED
surface: nothing in the generated zone is a fact of its own, so a hub renamed,
retired or created on disk is reflected on the next run and never hand-kept.

This script writes ONLY the content between the view's managed-zone markers:
    <!-- AUTO-GENERATED: hub-index ... -->
    ...
    <!-- END AUTO-GENERATED: hub-index -->
Everything outside them is owner-owned and never touched — today that is the
`## Cross-link state` section, whose orthogonal-pair table is hand-curated
rationale that no projection of the hub files could reproduce. Same contract
as the TAGS.md census, the SOUL.md Values zone and the cognitive-model hub.

Scope: `5_meta/mocs/*.md`, minus two mechanical exclusions matching
`render_index.py` / `render_tags.py`:

    *.template.md   — engine seeds co-located in a scanned dir (a released
                      skeleton strips the suffix in place), never owner hubs
    symlinks        — a symlinked hub would be listed twice

Per-hub row content comes from that hub's own frontmatter and nowhere else:
`id`, `title` (leading `Hub: ` stripped — the column already says hub),
`hub_kind`, `modified`, `related_notes`, `domains`, `people`. A field the hub
does not carry renders as `—`; the renderer never invents one and never
carries a stale value forward from the index it is replacing.

Grouping: one section per `status:` value. `active`, `dormant` and `resolved`
always render, empty or not — their absence from the index would read as
«none on disk» rather than «none in that state». Any other status found on
disk gets its own section after them, so no hub can fall out of the index;
lint A.6.2 checks exactly that, against this file.

Idempotency: the managed zone is rendered, then compared (timestamp line
excluded) to what is on disk. Identical → NO write at all, so `/minder:mem:maintain`
run twice produces a byte-identical tree.

First run on a base whose HUB_INDEX.md predates the markers adopts the legacy
layout deterministically: everything between the `# Hub Index` heading and the
`## Cross-link state` heading (or EOF) is the generated region, and it is
replaced by the marked zone. Owner sections below survive untouched.

Usage:
    python3 render_hub_index.py [--base PATH] [--output PATH]
                                [--dry-run] [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from _common import (
    configure_std_streams,
    now_iso_utc,
    read_frontmatter,
    repo_root,
    views_dir,
)

HUBS_ROOT = "5_meta/mocs"

ZONE_START = (
    "<!-- AUTO-GENERATED: hub-index — DO NOT EDIT BETWEEN MARKERS "
    "(maintained by render_hub_index.py) -->"
)
ZONE_END = "<!-- END AUTO-GENERATED: hub-index -->"

SOURCE_COMMENT = (
    "<!-- Source: frontmatter of `5_meta/mocs/hub-*.md`. Every column is a "
    "projection of the hub file itself; edit the hub, not this table. -->"
)
REGEN_PREFIX = "<!-- Last regenerated: "

TITLE_HEADING = "# Hub Index"
OWNER_TAIL_HEADING = "## Cross-link state"

# Sections that render whether or not any hub is in that state.
ALWAYS_SECTIONS: tuple[str, ...] = ("active", "dormant", "resolved")

MISSING = "—"

TITLE_PREFIX_RE = re.compile(r"^hub\s*:\s*", re.IGNORECASE)


class HubIndexRenderError(Exception):
    """Recoverable render failure — caller skips the step, never crashes."""


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Hub:
    id: str
    topic: str
    kind: str
    modified: str
    notes: str
    domains: tuple[str, ...]
    people: tuple[str, ...]
    status: str


def _iso_date(value) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, str) and value.strip():
        return value.strip()[:10]
    return ""


def _str_list(fm: dict, key: str) -> tuple[str, ...]:
    raw = fm.get(key)
    if not isinstance(raw, list):
        return ()
    return tuple(
        str(v).strip() for v in raw if isinstance(v, str) and str(v).strip()
    )


def _topic(fm: dict, fallback: str) -> str:
    title = fm.get("title")
    if not isinstance(title, str) or not title.strip():
        return fallback
    return TITLE_PREFIX_RE.sub("", title.strip()).strip() or fallback


def _notes_count(fm: dict) -> str:
    raw = fm.get("related_notes")
    if isinstance(raw, bool):
        return MISSING
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, str) and raw.strip().isdigit():
        return raw.strip()
    return MISSING


def collect_hubs(base: Path) -> list[Hub]:
    """Every hub on disk, sorted by id. Files without frontmatter are skipped
    — an unparseable hub is a lint finding, not a row this renderer invents."""
    out: list[Hub] = []
    root = base / HUBS_ROOT
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.md")):
        if path.is_symlink() or path.name.endswith(".template.md"):
            continue
        parsed = read_frontmatter(path)
        if parsed is None:
            continue
        fm, _body = parsed
        hid = fm.get("id")
        hid = hid.strip() if isinstance(hid, str) and hid.strip() else path.stem
        status = fm.get("status")
        status = (
            status.strip().lower()
            if isinstance(status, str) and status.strip() else "active"
        )
        out.append(Hub(
            id=hid,
            topic=_topic(fm, hid),
            kind=str(fm.get("hub_kind") or MISSING).strip() or MISSING,
            modified=_iso_date(fm.get("modified") or fm.get("created")) or MISSING,
            notes=_notes_count(fm),
            domains=_str_list(fm, "domains"),
            people=_str_list(fm, "people"),
            status=status,
        ))
    return sorted(out, key=lambda h: h.id)


def group_by_status(hubs: list[Hub]) -> list[tuple[str, list[Hub]]]:
    """`(status, hubs)` in render order: the three standing states first —
    always present, empty or not — then any other status found, alphabetical.

    Rows inside a section sort by `modified` descending, then id ascending:
    the freshest hub is the one a reader is looking for, and the order is
    total, so the render is stable across runs on identical input.
    """
    buckets: dict[str, list[Hub]] = {s: [] for s in ALWAYS_SECTIONS}
    for hub in hubs:
        buckets.setdefault(hub.status, []).append(hub)
    extra = sorted(s for s in buckets if s not in ALWAYS_SECTIONS)
    ordered = list(ALWAYS_SECTIONS) + extra
    return [
        (status, sorted(buckets[status], key=lambda h: (h.modified, h.id),
                        reverse=True))
        for status in ordered
    ]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _cell(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else MISSING


def _row(hub: Hub) -> str:
    return (
        f"| [[{hub.id}]] | {hub.topic} | {hub.kind} | {hub.modified} | "
        f"{hub.notes} | {_cell(hub.domains)} | {_cell(hub.people)} |"
    )


def render_zone_body(sections: list[tuple[str, list[Hub]]], total: int) -> str:
    lines: list[str] = [
        SOURCE_COMMENT,
        f"{REGEN_PREFIX}{now_iso_utc()} -->",
        "",
        f"**Hubs on disk:** {total}",
        "",
    ]
    for status, hubs in sections:
        lines.append("---")
        lines.append("")
        lines.append(f"## {status.capitalize()} Hubs ({len(hubs)})")
        lines.append("")
        if not hubs:
            lines.append("_(none)_")
            lines.append("")
            continue
        lines.append("| Hub | Topic | Kind | Updated | Notes | Domains | Key People |")
        lines.append("|---|---|---|---|---:|---|---|")
        for hub in hubs:
            lines.append(_row(hub))
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

    Runs from just after the `# Hub Index` heading to the owner tail heading
    (exclusive), or to EOF when the view has no owner tail. Returns None when
    the heading is absent — the file is then not a HUB_INDEX this renderer
    recognises, and the caller surfaces a skip rather than guessing.
    """
    # `[ \t]*`, never `\s*`: `\s` matches newlines, so a `\s*$` anchor eats the
    # blank line after the heading and the splice lands one line too low.
    m = re.search(r"^" + re.escape(TITLE_HEADING) + r"[ \t]*$", text, re.MULTILINE)
    if m is None:
        return None
    start = m.end()
    if start < len(text) and text[start] == "\n":
        start += 1
    tail = re.search(
        r"^" + re.escape(OWNER_TAIL_HEADING) + r"[ \t]*$", text[start:], re.MULTILINE,
    )
    end = start + tail.start() if tail else len(text)
    return start, end


def splice(view_text: str, new_body: str) -> str:
    """Write the zone into the view, adopting the legacy layout on first run."""
    if not new_body.endswith("\n"):
        new_body += "\n"
    bounds = find_zone(view_text)
    if bounds is not None:
        start, end = bounds
        return view_text[:start] + new_body + view_text[end:]

    legacy = _legacy_bounds(view_text)
    if legacy is None:
        raise HubIndexRenderError(
            f"no managed-zone markers and no `{TITLE_HEADING}` heading — "
            "cannot locate the generated region"
        )
    start, end = legacy
    block = f"\n{ZONE_START}\n{new_body}{ZONE_END}\n"
    tail = view_text[end:]
    if tail.startswith(OWNER_TAIL_HEADING):
        block += "\n---\n\n"
    return view_text[:start] + block + tail


def render(base: Path, out_path: Path):
    """Returns (sections, hubs, expected_body, view_text)."""
    hubs = collect_hubs(base)
    sections = group_by_status(hubs)
    expected_body = render_zone_body(sections, len(hubs))
    if not out_path.exists():
        raise HubIndexRenderError(f"view not found: {out_path}")
    return sections, hubs, expected_body, out_path.read_text(encoding="utf-8")


def _current_zone(view_text: str) -> str | None:
    bounds = find_zone(view_text)
    if bounds is None:
        return None
    return view_text[bounds[0]:bounds[1]]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=None,
                        help="override the zettelkasten root to scan")
    parser.add_argument("--output", type=Path, default=None,
                        help="override view path (default: _system/views/HUB_INDEX.md)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the rendered zone to stdout, do not write")
    parser.add_argument("--check", action="store_true",
                        help="exit 3 if the view would change; never write")
    args = parser.parse_args(argv)

    base = args.base.resolve() if args.base else repo_root()
    out_path = args.output or (views_dir(base) / "HUB_INDEX.md")

    try:
        sections, hubs, expected_body, view_text = render(base, out_path)
    except HubIndexRenderError as exc:
        # Best-effort, like the other maintain renderers: surface and skip,
        # never crash the maintain pipeline.
        print(json.dumps({"ok": False, "changed": False, "reason": str(exc)}))
        print(f"hub-index: skipped — {exc}", file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 — unattended maintain step must never crash
        print(json.dumps({
            "ok": False, "changed": False,
            "reason": f"unexpected: {type(exc).__name__}: {exc}",
        }))
        print(f"hub-index: skipped — unexpected {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 0

    if args.dry_run:
        sys.stdout.write(expected_body)
        return 0

    current = _current_zone(view_text)
    # No markers yet → the legacy region is adopted, which is always a change.
    would_change = (
        current is None
        or normalise_zone(current) != normalise_zone(expected_body)
    )

    result = {
        "ok": True,
        "changed": would_change,
        "hub_count": len(hubs),
        "sections": {status: len(bucket) for status, bucket in sections},
    }

    if args.check:
        print(json.dumps(result))
        return 3 if would_change else 0

    if would_change:
        try:
            new_text = splice(view_text, expected_body)
        except HubIndexRenderError as exc:
            print(json.dumps({"ok": False, "changed": False, "reason": str(exc)}))
            print(f"hub-index: skipped — {exc}", file=sys.stderr)
            return 0
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(out_path)

    print(json.dumps(result))
    print(
        f"wrote {out_path.name} ({len(hubs)} hubs, "
        f"{len([s for s, b in sections if b])} non-empty sections, "
        f"{'updated' if would_change else 'no change'})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
