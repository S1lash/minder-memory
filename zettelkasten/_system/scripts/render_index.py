#!/usr/bin/env python3
"""Regenerate `_system/views/INDEX.md` from the knowledge + synthesis +
constitution layers.

Deterministic, no LLM. Reads frontmatter across the base, writes a
content-oriented catalog faceted by PARA + `domains:` + cross-domain +
hubs + constitution. Matches the «navigation surface» role described in
ENGINE_DOCTRINE §1 — reader scans INDEX, drills into the page.

Sources (every active knowledge / synthesis / values entry, one line each):

    1_projects/**/*.md            — Projects facet (excl. README, PROJECTS.md)
    2_areas/**/*.md               — Areas facet (excl. README)
    3_resources/**/*.md           — Resources facet (excl. README, PEOPLE.md)
    4_archive/**/*.md             — Archive (rendered with `[archived]` marker)
    0_constitution/{axiom,principle,rule}/**/*.md
                                  — Constitution (rendered with `tier N`)
    5_meta/mocs/*.md              — Hubs (rendered with inbound count)

Excluded by design (each owns its own pipeline / index / store):

    _records/                     — operational provenance (record layer)
    _sources/, _system/           — raw / system
    6_posts/                      — outbound publishing (own pipeline)
    5_meta/CONCEPT.md, PROCESSING_PRINCIPLES.md, templates/, starter-pack/
                                  — engine docs + scaffolds, not knowledge

Output:
    _system/views/INDEX.md  (atomic write via .tmp + rename)

Usage:
    python3 render_index.py [--dry-run] [--output PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from _common import (
    ALLOWED_DOMAINS,
    constitution_root,
    iter_principles,
    now_iso_utc,
    read_frontmatter,
    repo_root,
    views_dir,
    configure_std_streams,
)


# -----------------------------------------------------------------------------
# Knowledge / archive / hub entries
# -----------------------------------------------------------------------------

KNOWLEDGE_ROOTS: tuple[tuple[str, str], ...] = (
    ("projects", "1_projects"),
    ("areas", "2_areas"),
    ("resources", "3_resources"),
)
ARCHIVE_ROOT = "4_archive"
HUBS_ROOT = "5_meta/mocs"

# README files at PARA roots are scaffolding, not knowledge.
EXCLUDED_FILENAMES: frozenset[str] = frozenset({
    "README.md",
    "PROJECTS.md", "PROJECTS.template.md",
    "PEOPLE.md", "PEOPLE.template.md",
})

# View / log files that must not contribute to inbound counts (would
# self-amplify hub centrality on every regen).
INBOUND_EXCLUDE_DIRS: tuple[str, ...] = (
    "_system/views",
    "_system/state",
)

UNSCOPED_BUCKET = "unscoped"

WIKILINK_RE = re.compile(r"\[\[([^\]\n|#]+?)(?:\|[^\]]*)?(?:#[^\]]*)?\]\]")
SUMMARY_LINE_MAX = 100


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    summary: str
    domains: list[str]
    modified: str  # YYYY-MM-DD
    section: str   # projects / areas / resources / archive / hub / constitution
    extra: dict    # per-section extras (tier, inbound_count, ...)


def _iso_date(value) -> str:
    """Best-effort YYYY-MM-DD extraction from frontmatter date / string."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, str) and value:
        return value[:10]
    return "0000-00-00"


def _first_prose_line(body: str) -> str | None:
    """Return first non-empty, non-heading prose line, trimmed.

    Skips ATX headings (`#`), HTML comments, and empty lines. Preserves
    inline emphasis / wikilinks verbatim — the catalog row is rendered
    plain markdown. Trim at SUMMARY_LINE_MAX chars.
    """
    in_html_comment = False
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("<!--"):
            in_html_comment = True
            if "-->" in line:
                in_html_comment = False
            continue
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue
        if line.startswith("#"):
            continue
        if line.startswith("---"):
            continue
        if len(line) > SUMMARY_LINE_MAX:
            line = line[:SUMMARY_LINE_MAX].rstrip() + "…"
        return line
    return None


def _summary(fm: dict, body: str) -> str:
    """Fallback chain: description → title → first prose line → placeholder."""
    desc = fm.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    title = fm.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    prose = _first_prose_line(body)
    if prose:
        return prose
    return "_(no description)_"


def _entry_id(fm: dict, path: Path) -> str:
    fid = fm.get("id")
    if isinstance(fid, str) and fid.strip():
        return fid.strip()
    return path.stem


def _domains_list(fm: dict) -> list[str]:
    raw = fm.get("domains")
    if isinstance(raw, list):
        return [str(d).strip() for d in raw if isinstance(d, str) and d.strip()]
    return []


def _modified(fm: dict) -> str:
    for key in ("modified", "created"):
        v = fm.get(key)
        s = _iso_date(v)
        if s != "0000-00-00":
            return s
    return "0000-00-00"


def _is_excluded_file(path: Path) -> bool:
    if path.name in EXCLUDED_FILENAMES:
        return True
    # Engine `*.template.md` seeds (e.g. hub-cognitive-model.template.md) may be
    # co-located in a scanned data dir because release_engine strips the suffix
    # in-place; they are engine seeds, not owner notes — never index them.
    if path.name.endswith(".template.md"):
        return True
    if path.is_symlink():
        return True
    return False


def _scan_para(base: Path, rel: str) -> list[Entry]:
    """Scan a PARA root, return knowledge entries."""
    out: list[Entry] = []
    root = base / rel
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.md")):
        if _is_excluded_file(path):
            continue
        parsed = read_frontmatter(path)
        if parsed is None:
            continue
        fm, body = parsed
        out.append(Entry(
            id=_entry_id(fm, path),
            title=str(fm.get("title") or path.stem),
            summary=_summary(fm, body),
            domains=_domains_list(fm),
            modified=_modified(fm),
            section=rel.split("_", 1)[1] if "_" in rel else rel,
            extra={},
        ))
    return out


def _scan_archive(base: Path) -> list[Entry]:
    """Scan 4_archive/ — same shape as PARA, marked separately."""
    out: list[Entry] = []
    root = base / ARCHIVE_ROOT
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.md")):
        if _is_excluded_file(path):
            continue
        parsed = read_frontmatter(path)
        if parsed is None:
            continue
        fm, body = parsed
        out.append(Entry(
            id=_entry_id(fm, path),
            title=str(fm.get("title") or path.stem),
            summary=_summary(fm, body),
            domains=_domains_list(fm),
            modified=_modified(fm),
            section="archive",
            extra={},
        ))
    return out


def _scan_constitution(base: Path) -> list[Entry]:
    """Scan 0_constitution/{axiom,principle,rule}/ via shared parser."""
    try:
        principles = iter_principles(constitution_root(base))
    except Exception as exc:  # ConstitutionError — surface but don't crash
        print(f"warning: constitution scan failed — {exc}; section will be empty",
              file=sys.stderr)
        return []
    out: list[Entry] = []
    for p in principles:
        fm = p.frontmatter
        # Skip placeholders / archived from INDEX surface — surfaced
        # in CONSTITUTION_INDEX with full status detail instead.
        status = fm.get("status", "active")
        if status in ("archived", "placeholder"):
            continue
        # Surface-line discipline: just the title. Statement detail
        # lives in CONSTITUTION_INDEX.md and the principle file itself.
        title = str(fm.get("title") or p.id)
        summary = title
        out.append(Entry(
            id=p.id,
            title=title,
            summary=summary,
            domains=[fm["domain"]] if fm.get("domain") else [],
            modified=_iso_date(fm.get("last_reviewed")
                                or fm.get("created")),
            section="constitution",
            extra={
                "tier": int(fm.get("priority_tier", 0)),
                "type": fm.get("type", ""),
            },
        ))
    return out


def _build_inbound_index(base: Path) -> dict[str, int]:
    """Count `[[id]]` and `[[id|alias]]` references across the base.

    Excludes:
      - the hub file itself when scanning hubs (handled at lookup time)
      - `_system/views/` (avoids the index referencing itself)
      - `_system/state/log_*.md` (audit trail — not real graph edges)
    """
    counts: dict[str, int] = defaultdict(int)
    for path in base.rglob("*.md"):
        rel = path.relative_to(base).as_posix()
        if any(rel.startswith(d + "/") or rel == d for d in INBOUND_EXCLUDE_DIRS):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in WIKILINK_RE.finditer(text):
            target = m.group(1).strip()
            if target:
                counts[target] += 1
    return dict(counts)


def _scan_hubs(base: Path, inbound: dict[str, int]) -> list[Entry]:
    out: list[Entry] = []
    root = base / HUBS_ROOT
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.md")):
        if _is_excluded_file(path):
            continue
        parsed = read_frontmatter(path)
        if parsed is None:
            continue
        fm, body = parsed
        hid = _entry_id(fm, path)
        # Subtract the hub's own self-reference (titles, headings) — we
        # excluded views/state but not the file itself; subtract any
        # self-mentions to keep the centrality signal honest.
        self_count = 0
        try:
            self_count = sum(
                1 for _ in WIKILINK_RE.finditer(path.read_text(encoding="utf-8"))
                if _.group(1).strip() == hid
            )
        except OSError:
            self_count = 0
        total = inbound.get(hid, 0) - self_count
        if total < 0:
            total = 0
        out.append(Entry(
            id=hid,
            title=str(fm.get("title") or path.stem),
            summary=_summary(fm, body),
            domains=_domains_list(fm),
            modified=_modified(fm),
            section="hub",
            extra={"inbound_count": total},
        ))
    return out


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------

def _domains_md(domains: list[str]) -> str:
    return "`[" + ", ".join(domains) + "]`"


def _row_knowledge(e: Entry) -> str:
    return f"- [[{e.id}]] — {e.summary} · {_domains_md(e.domains)} · {e.modified}"


def _row_archive(e: Entry) -> str:
    return (
        f"- [[{e.id}]] — [archived] {e.summary} · "
        f"{_domains_md(e.domains)} · {e.modified}"
    )


def _row_constitution(e: Entry) -> str:
    tier = e.extra.get("tier", 0)
    return (
        f"- [[{e.id}]] — {e.summary} · {_domains_md(e.domains)} · "
        f"tier {tier} · {e.modified}"
    )


def _row_hub(e: Entry) -> str:
    return (
        f"- [[{e.id}]] — {e.summary} · {_domains_md(e.domains)} · "
        f"{e.extra.get('inbound_count', 0)} inbound · upd {e.modified}"
    )


def _row_domain(e: Entry) -> str:
    """One-line entry for the By Domain section.

    Marker prefixes (`[archived]`, `tier N`) are preserved so the facet
    stays informative even when read in isolation.
    """
    if e.section == "archive":
        return f"- [[{e.id}]] — [archived] {e.summary}"
    if e.section == "constitution":
        tier = e.extra.get("tier", 0)
        return f"- [[{e.id}]] — {e.summary} · tier {tier}"
    return f"- [[{e.id}]] — {e.summary}"


def _sort_modified_desc(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda e: (e.modified, e.id), reverse=True)


def _by_domain(entries: list[Entry]) -> dict[str, list[Entry]]:
    """Group catalog-eligible entries by domain.

    Only domains in ALLOWED_DOMAINS contribute to facet headers;
    entries with no domains land under UNSCOPED_BUCKET. Unknown
    domains (drift) are silently skipped — surfaced via lint, not
    INDEX.
    """
    buckets: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        if not e.domains:
            buckets[UNSCOPED_BUCKET].append(e)
            continue
        for d in e.domains:
            if d in ALLOWED_DOMAINS:
                buckets[d].append(e)
    return buckets


def _cross_domain(entries: list[Entry]) -> list[Entry]:
    return [e for e in entries if len([d for d in e.domains if d in ALLOWED_DOMAINS]) >= 2]


def _render_section(title: str, entries: list[Entry], row_fn,
                    *, sort: bool = True) -> list[str]:
    if sort:
        entries = _sort_modified_desc(entries)
    out: list[str] = [f"### {title} — {len(entries)}", ""]
    if not entries:
        out.append("_(empty)_")
        out.append("")
        return out
    for e in entries:
        out.append(row_fn(e))
    out.append("")
    return out


def render_index(base: Path) -> str:
    knowledge: list[Entry] = []
    para_buckets: dict[str, list[Entry]] = {}
    for label, rel in KNOWLEDGE_ROOTS:
        bucket = _scan_para(base, rel)
        para_buckets[label] = bucket
        knowledge.extend(bucket)

    archive = _scan_archive(base)
    constitution = _scan_constitution(base)
    inbound = _build_inbound_index(base)
    hubs = _scan_hubs(base, inbound)

    # By Domain / Cross-domain pull from knowledge + archive + constitution
    # (NOT hubs — hubs have their own section + dedicated HUB_INDEX).
    domain_eligible = knowledge + archive + constitution
    by_domain = _by_domain(domain_eligible)
    cross = _cross_domain(domain_eligible)

    note_count = len(knowledge)
    archive_count = len(archive)
    constitution_count = len(constitution)
    hub_count = len(hubs)
    domain_count = len(set(d for e in domain_eligible for d in e.domains
                           if d in ALLOWED_DOMAINS))

    lines: list[str] = []
    lines.append("---")
    lines.append("id: index")
    lines.append("layer: system")
    lines.append(f"generated: {now_iso_utc()}")
    lines.append("generator: render_index.py")
    lines.append(f"note_count: {note_count}")
    lines.append(f"archive_count: {archive_count}")
    lines.append(f"constitution_count: {constitution_count}")
    lines.append(f"hub_count: {hub_count}")
    lines.append(f"domain_count: {domain_count}")
    lines.append("---")
    lines.append("")
    lines.append("# Wiki Index")
    lines.append("")
    lines.append(
        "Auto-generated by `_system/scripts/render_index.py` (called by "
        "`/minder:mem:bootstrap` Step 5.5, `/minder:mem:maintain` Step 7.6, and "
        "`regen_all.py`). Do not edit by hand — changes are overwritten "
        "on next regen. Surface-line catalog of every entry in the "
        "knowledge, archive, constitution, and synthesis (hub) layers."
    )
    lines.append("")
    lines.append(
        "One line per entry: `[[id]] — summary · [domains] · date`. "
        "Detailed views live in dedicated indexes — drill from here:"
    )
    lines.append("")
    lines.append("- Hubs detail → `HUB_INDEX.md`")
    lines.append("- Constitution detail → `CONSTITUTION_INDEX.md`")
    lines.append("- Live focus snapshot → `CURRENT_CONTEXT.md`")
    lines.append("")
    lines.append(
        "Records (`_records/`) and posts (`6_posts/`) are intentionally "
        "out of scope — provenance and outbound have their own pipelines."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ## By PARA
    lines.append("## By PARA")
    lines.append("")
    para_section_titles = {
        "projects": "Projects (`1_projects/`)",
        "areas": "Areas (`2_areas/`)",
        "resources": "Resources (`3_resources/`)",
    }
    for label, _rel in KNOWLEDGE_ROOTS:
        lines.extend(_render_section(
            para_section_titles[label], para_buckets[label], _row_knowledge,
        ))

    lines.append("---")
    lines.append("")

    # ## Archive
    lines.append("## Archive (`4_archive/`)")
    lines.append("")
    archive_sorted = _sort_modified_desc(archive)
    if not archive_sorted:
        lines.append("_(empty)_")
    else:
        for e in archive_sorted:
            lines.append(_row_archive(e))
    lines.append("")
    lines.append("---")
    lines.append("")

    # ## Constitution
    lines.append("## Constitution (`0_constitution/`)")
    lines.append("")
    if not constitution:
        lines.append("_(empty)_")
        lines.append("")
    else:
        # Group by type (axiom → principle → rule) for readability.
        for type_name in ("axiom", "principle", "rule"):
            bucket = [e for e in constitution if e.extra.get("type") == type_name]
            if not bucket:
                continue
            lines.append(f"### {type_name.capitalize()}s — {len(bucket)}")
            lines.append("")
            for e in sorted(bucket, key=lambda x: (x.extra.get("tier", 9), x.id)):
                lines.append(_row_constitution(e))
            lines.append("")
    lines.append("---")
    lines.append("")

    # ## By Domain
    lines.append("## By Domain")
    lines.append("")
    ordered = sorted(
        by_domain.items(),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )
    for d, bucket in ordered:
        if d == UNSCOPED_BUCKET:
            continue  # render last
        lines.append(f"### {d} ({len(bucket)})")
        for e in _sort_modified_desc(bucket):
            lines.append(_row_domain(e))
        lines.append("")
    if UNSCOPED_BUCKET in by_domain:
        bucket = by_domain[UNSCOPED_BUCKET]
        lines.append(f"### {UNSCOPED_BUCKET} ({len(bucket)})")
        for e in _sort_modified_desc(bucket):
            lines.append(_row_domain(e))
        lines.append("")

    lines.append("---")
    lines.append("")

    # ## Cross-domain
    lines.append(f"## Cross-domain (≥ 2 domains, {len(cross)})")
    lines.append("")
    lines.append(
        "Notes whose `domains:` list contains 2+ canonical values. The "
        "highest-leverage class per engine doctrine §1 — work↔personal "
        "bridges already crystallised in the catalog."
    )
    lines.append("")
    if not cross:
        lines.append("_(no cross-domain notes yet)_")
        lines.append("")
    else:
        for e in _sort_modified_desc(cross):
            lines.append(_row_domain(e) + f" · {_domains_md([d for d in e.domains if d in ALLOWED_DOMAINS])} · {e.modified}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ## Hubs
    lines.append(f"## Hubs (`5_meta/mocs/`) — {hub_count}")
    lines.append("")
    if not hubs:
        lines.append("_(empty)_")
        lines.append("")
    else:
        # Sort by inbound desc, tie-break by modified desc, then id asc.
        # Stable two-pass sort: secondary keys first, then primary.
        hubs_sorted = sorted(hubs, key=lambda e: (e.modified, e.id), reverse=True)
        hubs_sorted = sorted(
            hubs_sorted, key=lambda e: -e.extra.get("inbound_count", 0),
        )
        for e in hubs_sorted:
            lines.append(_row_hub(e))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print rendered index to stdout without writing",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="override output path (default: _system/views/INDEX.md)",
    )
    args = parser.parse_args(argv)

    base = repo_root()
    content = render_index(base)

    if args.dry_run:
        sys.stdout.write(content)
        return 0

    out_path = args.output or (views_dir(base) / "INDEX.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(out_path)
    rows = content.count("\n- [[")
    print(f"wrote {out_path} ({rows} surface rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
