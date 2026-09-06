#!/usr/bin/env python3
"""Minder Memory lint Scan A.7 + Step 1.D backfill — autonomous concept and
audience-tag autofix.

Deterministic Python implementation of the autonomous-pipeline contract:
- concept-name format issues → silent autofix or silent drop via the
  shared `normalize_concept_name` / `normalize_concept_list` helpers
- audience-tag whitelist mismatch → silent drop (engine never coins
  extensions; AUDIENCES.md remains owner-curated)
- privacy-trio missing fields → backfill with conservative defaults
  (`origin: personal`, `audience_tags: []`, `is_sensitive: false`)
- type coercion for `is_sensitive` (→ bool) and `origin` (→ enum)

NEVER raises CLARIFICATIONs; never blocks owner. Idempotent — re-running
on a clean state yields zero events. Same code path serves Scan A.7
(steady state) and Step 1.D one-time backfill on first lint run.

Output: JSONL on stdout, one event per fix. Exit 0 always.

Usage:
    python3 lint_concept_audit.py [--mode scan|fix] [--root <path>]
                                  [--audiences <path>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from _common import (
    ALLOWED_DOMAINS,
    AUDIENCE_CANONICAL,
    expand_domain_entry,
    normalize_audience_tag,
    normalize_concept_list,
    normalize_concept_name,
    parse_extensions_table,
    read_frontmatter,
    repo_root,
    write_frontmatter,
    configure_std_streams,
)


ALLOWED_ORIGINS = frozenset({"personal", "work", "external"})

# Files in scope for trio backfill (must carry `layer:` frontmatter
# in records / knowledge / hub / person / project profiles).
SCOPE_INCLUDE: tuple[str, ...] = (
    "_records/",
    "1_projects/",
    "2_areas/",
    "3_resources/",
    "4_archive/",
    "5_meta/mocs/",
)

# Explicit excludes — owner-curated registries, generated views,
# raw transcripts, audit logs, engine spec under 5_meta/, the
# constitution tree (which has its own schema and skill).
#
# Defence-in-depth: most of these paths are ALREADY out of scope
# because they don't match SCOPE_INCLUDE (e.g. `_system/SOUL.md`,
# `5_meta/CONCEPT.md`). Listing them explicitly here is intentional
# — if SCOPE_INCLUDE later expands (e.g. to scan `_system/` for some
# new lint pass), these owner-curated / generated / spec files MUST
# stay out. Belt and braces.
SCOPE_EXCLUDE: tuple[str, ...] = (
    "_system/registries/",
    "_system/views/",
    "_system/state/",
    "_sources/",
    "_system/SOUL.md",
    "_system/TASKS.md",
    "_system/CALENDAR.md",
    "_system/POSTS.md",
    "5_meta/templates/",
    "5_meta/CONCEPT.md",
    "5_meta/PROCESSING_PRINCIPLES.md",
    "5_meta/starter-pack/",
    "5_skills/",
    "0_constitution/",
)


def parse_audience_extensions(path: Path) -> set[str]:
    """Parse AUDIENCES.md Extensions table.

    Returns the set of active (non-deprecated) extension tags between
    `<!-- BEGIN extensions -->` and `<!-- END extensions -->` markers.
    Tolerant of missing file or malformed table — returns empty set.
    """
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    m = re.search(
        r"<!-- BEGIN extensions -->(.*?)<!-- END extensions -->",
        text, re.DOTALL,
    )
    if not m:
        return set()
    extensions: set[str] = set()
    for line in m.group(1).splitlines():
        if not line.strip().startswith("|"):
            continue
        if "---" in line:  # table separator row
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        tag, _added, status = cells[0], cells[1], cells[2]
        if not tag or tag.lower() == "tag":
            continue
        if tag.startswith("_(") or tag in {"—", "-"}:
            continue
        if status.lower().startswith("deprecated"):
            continue
        extensions.add(tag)
    return extensions


def in_scope(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    for excl in SCOPE_EXCLUDE:
        if rel == excl.rstrip("/") or rel.startswith(excl):
            return False
    for incl in SCOPE_INCLUDE:
        if rel.startswith(incl):
            return True
    return False


def walk_md_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.md"):
        if p.is_file() and in_scope(p, root):
            yield p


_CONCEPTS_TABLE_ROW_RE = re.compile(
    r"^\|\s*([a-z0-9_]+)\s*\|"   # canonical name
    r"[^|]*\|"                    # type
    r"[^|]*\|"                    # subtype
    r"[^|]*\|"                    # first_seen
    r"[^|]*\|"                    # last_seen
    r"\s*\d+\s*\|"                # mentions (digits — skips header row)
    r"\s*([^|]*?)\s*\|\s*$"       # aliases
)


def load_concept_aliases(registry_path: Path) -> dict[str, str]:
    """Read CONCEPTS.md aliases column → {old_name: canonical_name} map.

    Returns empty dict if the file is missing or malformed. Tolerant of
    YAML frontmatter, any section headers, and placeholder rows. Skips
    rows where alias cell is empty / `—`. Section-agnostic — discovery
    is by table shape, not by section header.

    Each canonical name is itself passed through `normalize_concept_name`
    as a defensive measure; same for each alias entry. Self-aliases
    (canonical mentioned among its own aliases) are silently dropped.
    Conflicting maps (alias points to two different canonicals) keep
    the first canonical seen and silently drop subsequent ones — same
    autonomous-resolution policy as the rest of the concept layer.
    """
    if not registry_path.exists():
        return {}
    try:
        text = registry_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _CONCEPTS_TABLE_ROW_RE.match(line)
        if not m:
            continue
        canonical_raw = m.group(1)
        aliases_cell = m.group(2).strip()
        if not aliases_cell or aliases_cell == "—":
            continue
        canonical = normalize_concept_name(canonical_raw)
        if canonical is None:
            continue
        for alias_raw in aliases_cell.split(","):
            alias = normalize_concept_name(alias_raw.strip())
            if alias is None or alias == canonical:
                continue
            if alias in out:
                continue  # first-canonical-wins
            out[alias] = canonical
    return out


def apply_concept_aliases(
    fm: dict, alias_map: dict[str, str]
) -> tuple[dict, list[dict]]:
    """Rewrite `concepts:` entries via alias_map (old → canonical).

    Pure function. Idempotent on the canonical form: if an entry is
    already canonical, no change. Dedup preserved on collisions
    (two aliases pointing to the same canonical → single entry).

    Emits `concept-alias-rewrite-autofix` events per rewrite.
    """
    events: list[dict] = []
    if not alias_map:
        return fm, events
    raw = fm.get("concepts")
    if not isinstance(raw, list):
        return fm, events
    rewritten: list[str] = []
    seen: set[str] = set()
    changed = False
    for entry in raw:
        if not isinstance(entry, str):
            rewritten.append(entry)
            continue
        target = alias_map.get(entry)
        if target is None:
            if entry not in seen:
                seen.add(entry)
                rewritten.append(entry)
            continue
        changed = True
        events.append({
            "fix_id": "concept-alias-rewrite-autofix",
            "field": "concepts",
            "raw": entry,
            "result": target,
        })
        if target not in seen:
            seen.add(target)
            rewritten.append(target)
    if not changed:
        return fm, events
    new_fm = dict(fm)
    new_fm["concepts"] = rewritten
    return new_fm, events


def fix_concepts(fm: dict) -> tuple[dict, list[dict]]:
    """Apply normalize_concept_list to `concepts:` field.

    Emits per-entry events for traceability. List collapses on
    duplicates after normalisation (silent dedup).
    """
    events: list[dict] = []
    raw = fm.get("concepts")
    if raw is None:
        return fm, events
    if isinstance(raw, str):
        raw_list = [raw]
    elif isinstance(raw, list):
        raw_list = list(raw)
    else:
        events.append({
            "fix_id": "concept-drop-autofix",
            "field": "concepts",
            "raw": str(raw),
            "result": None,
            "reason": "invalid type",
        })
        new_fm = dict(fm)
        new_fm["concepts"] = []
        return new_fm, events

    normalised = normalize_concept_list(raw_list)
    if normalised == raw_list:
        return fm, events

    # Per-entry event ledger
    for orig in raw_list:
        if not isinstance(orig, str):
            events.append({
                "fix_id": "concept-drop-autofix",
                "field": "concepts",
                "raw": str(orig),
                "result": None,
                "reason": "non-string entry",
            })
            continue
        n = normalize_concept_name(orig)
        if n is None:
            events.append({
                "fix_id": "concept-drop-autofix",
                "field": "concepts",
                "raw": orig,
                "result": None,
                "reason": "unnormalisable",
            })
        elif n != orig:
            events.append({
                "fix_id": "concept-format-autofix",
                "field": "concepts",
                "raw": orig,
                "result": n,
            })
        # else: passthrough, no event

    new_fm = dict(fm)
    new_fm["concepts"] = normalised
    return new_fm, events


def fix_audience_tags(
    fm: dict, accept_set: set[str]
) -> tuple[dict, list[dict]]:
    """Filter `audience_tags:` to whitelist; normalise where possible."""
    events: list[dict] = []
    raw = fm.get("audience_tags")
    if raw is None:
        return fm, events
    if isinstance(raw, str):
        raw_list = [raw]
    elif isinstance(raw, list):
        raw_list = list(raw)
    else:
        events.append({
            "fix_id": "audience-tag-drop-autofix",
            "field": "audience_tags",
            "raw": str(raw),
            "result": None,
            "reason": "invalid type",
        })
        new_fm = dict(fm)
        new_fm["audience_tags"] = []
        return new_fm, events

    accepted: list[str] = []
    seen: set[str] = set()
    changed = False

    for orig in raw_list:
        if not isinstance(orig, str):
            events.append({
                "fix_id": "audience-tag-drop-autofix",
                "field": "audience_tags",
                "raw": str(orig),
                "result": None,
                "reason": "non-string entry",
            })
            changed = True
            continue
        if orig in accept_set:
            if orig not in seen:
                accepted.append(orig)
                seen.add(orig)
            else:
                changed = True
            continue
        norm = normalize_audience_tag(orig)
        if norm is None:
            events.append({
                "fix_id": "audience-tag-drop-autofix",
                "field": "audience_tags",
                "raw": orig,
                "result": None,
                "reason": "format-unfixable",
            })
            changed = True
            continue
        if norm in accept_set:
            if norm not in seen:
                accepted.append(norm)
                seen.add(norm)
            events.append({
                "fix_id": "audience-tag-normalise-autofix",
                "field": "audience_tags",
                "raw": orig,
                "result": norm,
            })
            changed = True
            continue
        events.append({
            "fix_id": "audience-tag-drop-autofix",
            "field": "audience_tags",
            "raw": orig,
            "result": None,
            "reason": "not-in-whitelist",
        })
        changed = True

    if not changed and accepted == raw_list:
        return fm, events

    new_fm = dict(fm)
    new_fm["audience_tags"] = accepted
    return new_fm, events


def fix_domains(
    fm: dict, accept_set: set[str]
) -> tuple[dict, list[dict]]:
    """Filter `domains:` (plural list on notes / hubs / typed objects) to
    canonical-13 ∪ active extensions; normalise where possible.

    Scope: this pass touches only the plural `domains:` field. The singular
    `domain:` field on constitution principles is parse-time validated by
    `validate_frontmatter` against `ALLOWED_DOMAINS` and never enters lint
    scope (the constitution tree is excluded via SCOPE_EXCLUDE).

    Lint runs the deterministic substrate only. The LLM cascade
    (remap-or-CLARIFICATION for unmappable values) is documented in
    DOMAINS.md and runs in `/minder:mem:process` Step 3.4.5
    (concept-matcher subagent), in both inbox-scan and
    `--reprocess-corpus` modes. Lint never invokes LLM directly.
    """
    events: list[dict] = []
    raw = fm.get("domains")
    if raw is None:
        return fm, events
    if isinstance(raw, str):
        raw_list = [raw]
    elif isinstance(raw, list):
        raw_list = list(raw)
    else:
        events.append({
            "fix_id": "domain-drop-autofix",
            "field": "domains",
            "raw": str(raw),
            "result": None,
            "reason": "invalid type",
        })
        new_fm = dict(fm)
        new_fm["domains"] = []
        return new_fm, events

    accepted: list[str] = []
    seen: set[str] = set()
    changed = False

    for orig in raw_list:
        if not isinstance(orig, str):
            events.append({
                "fix_id": "domain-drop-autofix",
                "field": "domains",
                "raw": str(orig),
                "result": None,
                "reason": "non-string entry",
            })
            changed = True
            continue
        # Fast path: canonical / extension verbatim, no slash → keep as-is.
        if "/" not in orig and orig in accept_set:
            if orig not in seen:
                accepted.append(orig)
                seen.add(orig)
            else:
                changed = True
            continue
        # Expansion path: slash-split + per-part normalise + per-part filter.
        # `work/learning` → both parts kept (both canonical). `work/process`
        # → `work` kept, `process` dropped (not-in-whitelist). `тема` →
        # nothing kept (format-unfixable).
        expanded = expand_domain_entry(orig)
        if not expanded:
            events.append({
                "fix_id": "domain-drop-autofix",
                "field": "domains",
                "raw": orig,
                "result": None,
                "reason": "format-unfixable",
            })
            changed = True
            continue
        any_kept = False
        any_dropped = False
        kept_results: list[str] = []
        for part in expanded:
            if part in accept_set:
                if part not in seen:
                    accepted.append(part)
                    seen.add(part)
                kept_results.append(part)
                any_kept = True
                if part != orig:
                    changed = True
            else:
                events.append({
                    "fix_id": "domain-drop-autofix",
                    "field": "domains",
                    "raw": orig,
                    "result": None,
                    "reason": "not-in-whitelist",
                    "part": part,
                })
                any_dropped = True
                changed = True
        if any_kept and (len(expanded) > 1 or kept_results != [orig]):
            events.append({
                "fix_id": "domain-normalise-autofix",
                "field": "domains",
                "raw": orig,
                "result": kept_results if len(kept_results) > 1
                          else kept_results[0],
            })

    if not changed and accepted == raw_list:
        return fm, events

    new_fm = dict(fm)
    new_fm["domains"] = accepted
    return new_fm, events


def derive_origin_from_path(path: Path | None) -> str:
    """Path-based origin heuristic — deterministic, autonomous-resolution
    qualifying per ENGINE_DOCTRINE §3.1 (algorithm-driven, conservative-safe).

    Multi-person work events → `work`. Solo Plaud / personal folders →
    `personal`. Career thinking lives in `personal` per the spec
    (career = owner's identity work, not work-context). Falls back to
    `personal` when no rule matches.
    """
    if path is None:
        return "personal"
    rel = path.as_posix()
    if "/_records/meetings/" in rel or rel.startswith("_records/meetings/"):
        return "work"
    if "/2_areas/work/" in rel:
        return "work"
    return "personal"


def fix_privacy_trio(fm: dict, path: Path | None = None) -> tuple[dict, list[dict]]:
    """Backfill missing trio fields and coerce types.

    `origin` is derived from path when missing (see `derive_origin_from_path`).
    `audience_tags` defaults to `[]` (owner-only, conservative). `is_sensitive`
    defaults to `False`. Owner reviews via `/minder:mem:lint` summary on first run
    and refines with intelligent assignment if the corpus has rich legacy
    content the path heuristic cannot resolve.
    """
    events: list[dict] = []
    new_fm = dict(fm)
    fields_added: list[str] = []

    if "origin" not in new_fm:
        new_fm["origin"] = derive_origin_from_path(path)
        fields_added.append("origin")
    if "audience_tags" not in new_fm:
        new_fm["audience_tags"] = []
        fields_added.append("audience_tags")
    if "is_sensitive" not in new_fm:
        new_fm["is_sensitive"] = False
        fields_added.append("is_sensitive")

    if fields_added:
        events.append({
            "fix_id": "privacy-trio-backfill-autofix",
            "fields_added": fields_added,
            "origin_source": "path-derived" if "origin" in fields_added else None,
        })

    origin = new_fm.get("origin")
    if origin not in ALLOWED_ORIGINS:
        events.append({
            "fix_id": "origin-coerce-autofix",
            "raw": origin,
            "result": "personal",
        })
        new_fm["origin"] = "personal"

    is_sens = new_fm.get("is_sensitive")
    if not isinstance(is_sens, bool):
        if isinstance(is_sens, str):
            coerced = is_sens.strip().lower() == "true"
        elif isinstance(is_sens, (int, float)) and not isinstance(is_sens, bool):
            coerced = bool(is_sens)
        else:
            coerced = False
        events.append({
            "fix_id": "is-sensitive-coerce-autofix",
            "raw": is_sens,
            "result": coerced,
        })
        new_fm["is_sensitive"] = coerced

    return new_fm, events


def process_file(
    path: Path,
    audience_accept: set[str],
    domain_accept: set[str],
    alias_map: dict[str, str],
    mode: str,
) -> list[dict]:
    parsed = read_frontmatter(path)
    if parsed is None:
        return []
    fm, body = parsed

    # Trio backfill applies only to entities with `layer:` —
    # records / knowledge / hub / person / project. Files in scope
    # but without `layer:` (rare; e.g. PARA README files) are
    # skipped for trio but still get concept/audience autofix if
    # the fields are present.
    has_layer = "layer" in fm

    all_events: list[dict] = []

    # Alias rewrite first — old names → canonical — so subsequent
    # normalisation operates on the canonical surface.
    fm, events = apply_concept_aliases(fm, alias_map)
    all_events.extend(events)

    fm, events = fix_concepts(fm)
    all_events.extend(events)

    fm, events = fix_audience_tags(fm, audience_accept)
    all_events.extend(events)

    fm, events = fix_domains(fm, domain_accept)
    all_events.extend(events)

    if has_layer:
        fm, events = fix_privacy_trio(fm, path)
        all_events.extend(events)

    if all_events and mode == "fix":
        write_frontmatter(path, fm, body)

    for ev in all_events:
        ev["path"] = path.as_posix()

    return all_events


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["scan", "fix"], default="scan",
        help="scan: report events without writing. "
             "fix: apply changes in place.",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="Zettelkasten root (default: from MINDER_MEMORY_BASE / "
             "script-relative resolution). Pass an explicit path for "
             "tests or alternative roots.",
    )
    parser.add_argument(
        "--audiences", type=Path, default=None,
        help="AUDIENCES.md path (default: "
             "{root}/_system/registries/AUDIENCES.md).",
    )
    parser.add_argument(
        "--domains", type=Path, default=None,
        help="DOMAINS.md path (default: "
             "{root}/_system/registries/DOMAINS.md).",
    )
    args = parser.parse_args(argv)

    root = (args.root or repo_root()).resolve()
    audiences_path = args.audiences or (
        root / "_system" / "registries" / "AUDIENCES.md"
    )
    domains_path = args.domains or (
        root / "_system" / "registries" / "DOMAINS.md"
    )

    audience_extensions = parse_audience_extensions(audiences_path)
    # Canonical-conflict guard for audiences is handled by the legacy
    # `parse_audience_extensions` (defined in this module above) which
    # predates the canonical-blacklist parameter — refactor on next
    # touch of audience code paths. AUDIENCE_CANONICAL set is small and
    # the legacy parser already filters table-header noise.
    audience_accept = set(AUDIENCE_CANONICAL) | audience_extensions

    domain_extensions = parse_extensions_table(
        domains_path, canonical_blacklist=ALLOWED_DOMAINS,
    )
    domain_accept = set(ALLOWED_DOMAINS) | domain_extensions

    alias_map = load_concept_aliases(
        root / "_system" / "registries" / "CONCEPTS.md",
    )

    for md in walk_md_files(root):
        events = process_file(
            md, audience_accept, domain_accept, alias_map, args.mode,
        )
        for ev in events:
            sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
