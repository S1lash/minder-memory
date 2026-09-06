#!/usr/bin/env python3
"""Render _system/views/CONTENT_MAP.md — the content pipeline's compact
interface between the cheap deterministic layer and the expensive reasoning
layer (the `content-synthesis` lens).

A pure projection — carries NO state. Regenerable from scratch at any time
from three sources:
- content-flagged knowledge notes (`content_potential` set) in PARA + archive,
- the hubs they belong to (`5_meta/mocs/*.md`; membership = a note's body
  `[[hub-*]]` links in its `## Связи` / Related section),
- POSTS.md `source_notes` (published posts mapped back to their theme).

One compact line per content note so the view stays small at 1000+ notes; the
lens drills into note bodies only for the themes it actually works on.

Canonical writer: `/minder:mem:maintain` (it already owns derived-view regen and runs
after every process batch — guarantees the map is fresh before the weekly lens
reads it). `/minder:mem:content` may trigger an on-demand regen interactively, but
maintain is the source of truth for the regen.

Ripeness (a sortable hint; the lens re-derives from the map each run and never
treats it as authoritative): `convergence × note_count × avg_potential`, where
potential weight high=1.0 / medium=0.5, avg_potential = mean of weights,
convergence = 1 + (# high-potential notes) — so ≥2 high notes signals a strong,
converging cluster. Never zero for a non-empty theme.

Deterministic, idempotent, pure — no LLM. Atomic write via .tmp + rename.

Usage:
    python3 render_content_map.py [--dry-run] [--output <path>] [--base <root>]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import (
    now_iso_utc,
    read_frontmatter,
    repo_root,
    views_dir,
    configure_std_streams,
)


SCOPE_INCLUDE: tuple[str, ...] = (
    "1_projects/",
    "2_areas/",
    "3_resources/",
    "4_archive/",
)

POTENTIAL_WEIGHT = {"high": 1.0, "medium": 0.5}

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def _in_scope(rel: str) -> bool:
    return any(rel.startswith(p) for p in SCOPE_INCLUDE)


def _note_id(fm: dict, path: Path) -> str:
    nid = fm.get("id")
    return nid if isinstance(nid, str) and nid.strip() else path.stem


def _angles(fm: dict) -> list[str]:
    raw = fm.get("content_angle")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [a.strip() for a in raw if isinstance(a, str) and a.strip()]
    return []


def _angle_cell(angles: list[str]) -> str:
    if not angles:
        return "—"
    head = angles[0]
    if len(angles) > 1:
        return f'"{head}" (+{len(angles) - 1})'
    return f'"{head}"'


def _wikilinks(body: str) -> list[str]:
    return [m.strip() for m in _WIKILINK_RE.findall(body)]


def collect_content_notes(base: Path) -> list[dict]:
    """Return one dict per content-flagged note: id, title, type, potential,
    angles, domains, hubs (body [[hub-*]] refs)."""
    notes: list[dict] = []
    for p in base.rglob("*.md"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(base).as_posix()
        except ValueError:
            continue
        if not _in_scope(rel):
            continue
        parsed = read_frontmatter(p)
        if parsed is None:
            continue
        fm, body = parsed
        if fm.get("content_potential") not in POTENTIAL_WEIGHT:
            continue
        links = _wikilinks(body)
        hubs = sorted({ln for ln in links if ln.startswith("hub-")})
        notes.append({
            "id": _note_id(fm, p),
            "title": fm.get("title") or _note_id(fm, p),
            "type": fm.get("content_type") or "—",
            "potential": fm.get("content_potential"),
            "angles": _angles(fm),
            "domains": fm.get("domains") if isinstance(fm.get("domains"), list) else [],
            "hubs": hubs,
        })
    notes.sort(key=lambda n: n["id"])
    return notes


def collect_hubs(base: Path) -> dict[str, dict]:
    """Return {hub_id: {title, related_hubs}} for every hub in 5_meta/mocs/."""
    hubs: dict[str, dict] = {}
    mocs = base / "5_meta" / "mocs"
    if not mocs.is_dir():
        return hubs
    for p in sorted(mocs.glob("*.md")):
        if p.stem.startswith("_"):
            continue
        parsed = read_frontmatter(p)
        if parsed is None:
            continue
        fm, body = parsed
        hub_id = fm.get("id") or p.stem
        related = sorted({
            ln for ln in _wikilinks(body)
            if ln.startswith("hub-") and ln != hub_id
        })
        hubs[hub_id] = {"title": fm.get("title") or hub_id, "related_hubs": related}
    return hubs


def parse_posts_by_note(base: Path) -> dict[str, int]:
    """Return {note_id: published_post_count} from POSTS.md `source_notes`
    (the Published table's last column, `[[note-id]]` wikilinks)."""
    posts_path = base / "_system" / "POSTS.md"
    out: dict[str, int] = {}
    if not posts_path.exists():
        return out
    text = posts_path.read_text(encoding="utf-8")
    # Only the Published table region — between '## Published' and the next '## '.
    m = re.search(r"## Published\b(.*?)(?:\n## |\Z)", text, re.DOTALL)
    region = m.group(1) if m else ""
    for line in region.splitlines():
        if not line.strip().startswith("|"):
            continue
        if "Source Notes" in line or re.match(r"^\|[\s\-|]+\|$", line.strip()):
            continue
        for nid in _wikilinks(line):
            if nid.startswith("hub-"):
                continue
            out[nid] = out.get(nid, 0) + 1
    return out


def ripeness(notes: list[dict]) -> float:
    if not notes:
        return 0.0
    weights = [POTENTIAL_WEIGHT.get(n["potential"], 0.0) for n in notes]
    note_count = len(notes)
    avg_potential = sum(weights) / note_count
    high_count = sum(1 for n in notes if n["potential"] == "high")
    convergence = 1 + high_count
    return round(convergence * note_count * avg_potential, 1)


def _note_line(n: dict) -> str:
    # per-note ripeness on every line so a standalone (theme_id `note:{id}`) is
    # parseable wherever the note appears (theme member OR unclustered); the hub
    # heading carries the THEME ripeness, this carries the single-NOTE ripeness.
    return (f"- [[{n['id']}]] · {n['type']} · {n['potential']} · "
            f"ripeness {ripeness([n])} · {_angle_cell(n['angles'])}")


def render_content_map(base: Path) -> str:
    notes = collect_content_notes(base)
    hubs = collect_hubs(base)
    posts_by_note = parse_posts_by_note(base)

    # hub_id -> list of member content notes (a note in N hubs appears in each)
    by_hub: dict[str, list[dict]] = {}
    unclustered: list[dict] = []
    for n in notes:
        member_hubs = [h for h in n["hubs"] if h in hubs]
        if member_hubs:
            for h in member_hubs:
                by_hub.setdefault(h, []).append(n)
        else:
            unclustered.append(n)

    # posts per hub: a post counts for a hub if any source_note belongs to it
    posts_per_hub: dict[str, int] = {}
    for hub_id, members in by_hub.items():
        posts_per_hub[hub_id] = sum(
            posts_by_note.get(n["id"], 0) for n in members
        )

    theme_rows = []
    for hub_id, members in by_hub.items():
        theme_rows.append({
            "hub_id": hub_id,
            "title": hubs[hub_id]["title"],
            "related": hubs[hub_id]["related_hubs"],
            "notes": members,
            "ripeness": ripeness(members),
            "posts": posts_per_hub.get(hub_id, 0),
        })
    # rank by ripeness desc, then hub_id for stable ordering
    theme_rows.sort(key=lambda t: (-t["ripeness"], t["hub_id"]))

    high_total = sum(1 for n in notes if n["potential"] == "high")
    med_total = sum(1 for n in notes if n["potential"] == "medium")

    lines: list[str] = []
    lines.append("---")
    lines.append("id: content-map")
    lines.append("layer: system")
    lines.append(f"generated: {now_iso_utc()}")
    lines.append("generator: render_content_map.py")
    lines.append(f"content_notes: {len(notes)}")
    lines.append(f"themes: {len(theme_rows)}")
    lines.append(f"unclustered: {len(unclustered)}")
    lines.append("origin: personal")
    lines.append("audience_tags: []")
    lines.append("is_sensitive: false")
    lines.append("---")
    lines.append("")
    lines.append("# Content Map")
    lines.append("")
    lines.append(
        "> Derived view over hubs + content-flagged note frontmatter + "
        "POSTS.md. Regenerated by `/minder:mem:maintain` (canonical writer) after "
        "every process batch. Do not edit by hand — overwritten on next regen.")
    lines.append(">")
    lines.append(
        "> Ripeness = convergence × note_count × avg_potential "
        "(high=1.0, medium=0.5; convergence = 1 + #high). A sortable hint — "
        "the `content-synthesis` lens re-derives it each run, never trusting "
        "this value as authoritative.")
    lines.append("")
    lines.append(
        f"**Content notes:** {len(notes)} "
        f"(high: {high_total}, medium: {med_total}) · "
        f"**Themes:** {len(theme_rows)} · "
        f"**Unclustered:** {len(unclustered)}")
    lines.append("")
    lines.append("## Themes (by ripeness)")
    lines.append("")
    if not theme_rows:
        lines.append("_No hub-linked content notes._")
        lines.append("")
    for t in theme_rows:
        posts_str = (f" · {t['posts']} post(s) published on this theme"
                     if t["posts"] else "")
        lines.append(
            f"### [[{t['hub_id']}]] — {t['title']} · ripeness {t['ripeness']} · "
            f"{len(t['notes'])} note(s){posts_str}")
        if t["related"]:
            lines.append("related hubs: " +
                         ", ".join(f"[[{h}]]" for h in t["related"]))
        lines.append("")
        for n in sorted(t["notes"], key=lambda x: x["id"]):
            lines.append(_note_line(n))
        lines.append("")

    lines.append("## Unclustered content notes (no hub)")
    lines.append("")
    lines.append(
        "_Not yet linked to any hub — fully in view for the lens "
        "(long-tail preserved)._")
    lines.append("")
    if not unclustered:
        lines.append("_None._")
        lines.append("")
    for n in sorted(unclustered, key=lambda x: x["id"]):
        dom = f" · domains:[{', '.join(n['domains'])}]" if n["domains"] else ""
        lines.append(_note_line(n) + dom)
    if unclustered:
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print rendered map to stdout without writing",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="override output path (default: _system/views/CONTENT_MAP.md)",
    )
    parser.add_argument(
        "--base", type=Path, default=None,
        help="repo base (default: repo_root() / MINDER_MEMORY_BASE). Pass for tests.",
    )
    args = parser.parse_args(argv)

    base = (args.base or repo_root()).resolve()
    content = render_content_map(base)

    if args.dry_run:
        sys.stdout.write(content)
        return 0

    out_path = args.output or (views_dir(base) / "CONTENT_MAP.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(out_path)
    themes = content.count("\n### [[")
    print(f"wrote {out_path} ({themes} themes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
