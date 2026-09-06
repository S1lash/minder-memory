#!/usr/bin/env python3
"""Render the cognitive-model hub managed zone.

`5_meta/mocs/hub-cognitive-model.md` is the visible, accumulating projection of
«how the owner thinks, as the system models it» — one row per cognitive /
communication axis, with a status (`blank` / `evidenced` / `promoted`), the
promoted principle(s) that evidence it, and anchor records.

This script writes ONLY the content between the hub's managed-zone markers:
    <!-- AUTO-GENERATED: cognitive-model-hub ... -->
    ...
    <!-- END AUTO-GENERATED: cognitive-model-hub -->
Everything outside the markers (frontmatter, title, the owner's prose «portrait»)
is owner-owned and never touched — same contract as SOUL.md's Values zone.

The hub holds NO truth of its own (SoT/DRY): every axis→principle edge is read
from the principle's `cognitive_axes` frontmatter; the axis list (slugs + order +
names) is read from the cognitive-model lens prompt. Change a principle's tag or
archive it, and the next render reflects it. `grep` for a principle body in the
hub is 0 by construction — only `[[id]]` links appear.

Inputs (deterministic, no LLM):
  - Axis SoT       : the `<!-- cognitive-axes:begin -->` YAML block in
                     `_system/registries/lenses/cognitive-model/prompt.md`.
  - Promoted edges : active principles whose `cognitive_axes` lists a known slug.
  - Evidenced edges: `_system/state/principle-candidates.jsonl` lines carrying a
                     `dimension` slug (emitted by the cognitive-model lens) that
                     no promoted principle already covers.

Idempotency: the managed zone is rendered, then compared (timestamp/hash lines
excluded) to what is already on disk. Identical → NO write at all (true no-op, so
`/minder:mem:maintain` run twice produces a byte-identical tree). This is stricter than
render_soul_values, which always rewrites the timestamp.

Usage:
    python3 render_cognitive_model_hub.py [--hub PATH] [--prompt PATH]
                                          [--dry-run] [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from _common import (
    constitution_root,
    iter_principles,
    now_iso_utc,
    registries_dir,
    repo_root,
    state_dir,
    system_dir,
    configure_std_streams,
)

HUB_REL = "5_meta/mocs/hub-cognitive-model.md"
PROMPT_REL = "registries/lenses/cognitive-model/prompt.md"
CANDIDATES_REL = "state/principle-candidates.jsonl"

ZONE_START = (
    "<!-- AUTO-GENERATED: cognitive-model-hub — DO NOT EDIT BETWEEN MARKERS "
    "(maintained by render_cognitive_model_hub.py) -->"
)
ZONE_END = "<!-- END AUTO-GENERATED: cognitive-model-hub -->"

SOURCE_COMMENT = (
    "<!-- Source: 0_constitution/ principles tagged `cognitive_axes` (active) + "
    "agent-lens candidates carrying a `dimension`. "
    "Axis SoT: _system/registries/lenses/cognitive-model/prompt.md -->"
)
HASH_PREFIX = "<!-- Source hash: "
HASH_SUFFIX = " -->"
HASH_RE = re.compile(re.escape(HASH_PREFIX) + r"([0-9a-f]+)" + re.escape(HASH_SUFFIX))
REGEN_PREFIX = "<!-- Last regenerated: "

AXES_BLOCK_RE = re.compile(
    r"<!--\s*cognitive-axes:begin.*?-->\s*```ya?ml\s*\n(.*?)\n```",
    re.DOTALL,
)

STATUS_PROMOTED = "promoted"
STATUS_EVIDENCED = "evidenced"
STATUS_BLANK = "blank"

MAX_ANCHORS = 3


class HubRenderError(Exception):
    """Recoverable render failure — caller skips the step, never crashes."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_axes(prompt_path: Path) -> list[dict]:
    """Parse the canonical axis list (slug + name, in order) from the lens prompt.

    Raises HubRenderError on a missing file or malformed block so the caller can
    skip gracefully — the hub is never half-written from a broken SoT.
    """
    if not prompt_path.exists():
        raise HubRenderError(f"axis SoT not found: {prompt_path}")
    text = prompt_path.read_text(encoding="utf-8")
    m = AXES_BLOCK_RE.search(text)
    if not m:
        raise HubRenderError(
            f"cognitive-axes block not found in {prompt_path} "
            "(expected `<!-- cognitive-axes:begin -->` + a ```yaml block)"
        )
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        raise HubRenderError(f"axis block YAML parse error: {exc}") from exc
    axes = (data or {}).get("axes")
    if not isinstance(axes, list) or not axes:
        raise HubRenderError("axis block has no `axes:` list")
    out: list[dict] = []
    seen: set[str] = set()
    for entry in axes:
        if not isinstance(entry, dict):
            raise HubRenderError("each axis entry must be a mapping")
        slug = entry.get("slug")
        name = entry.get("name")
        if not isinstance(slug, str) or not slug or not isinstance(name, str) or not name:
            raise HubRenderError(f"axis entry missing slug/name: {entry!r}")
        if slug in seen:
            raise HubRenderError(f"duplicate axis slug: {slug}")
        seen.add(slug)
        out.append({"slug": slug, "name": name})
    return out


def _date_str(value) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, str) and value.strip():
        return value.strip()[:10]
    return None


def collect_promoted(
    axis_slugs: set[str], dropped: list[dict] | None = None
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Map axis slug → sorted [principle id] and axis slug → latest evidence date.

    Only `status: active` principles count (archived/placeholder drop out — a
    rolled-back principle stops evidencing its axis automatically, per the
    Archive Contract: the reason lives on the principle, the hub just reflects
    current state). Unknown slugs are skipped; when `dropped` is a list, each is
    appended as `{principle_id, slug}` so the caller can surface it.
    """
    by_axis: dict[str, list[str]] = {}
    dates: dict[str, str] = {}
    for p in iter_principles(constitution_root()):
        if p.status != "active":
            continue
        ev_date = _date_str(p.frontmatter.get("last_reviewed")) or _date_str(
            p.frontmatter.get("created")
        )
        for slug in p.cognitive_axes:
            if slug not in axis_slugs:
                # Unknown slug — drop it (the hub never carries a typo) and
                # record it so the caller can surface it (maintain logs it,
                # lint F.8 raises a CLARIFICATION). Authoritative validation is
                # lint F.8; this is the defensive render-time drop.
                if dropped is not None:
                    dropped.append({"principle_id": p.id, "slug": slug})
                continue
            by_axis.setdefault(slug, []).append(p.id)
            if ev_date and (slug not in dates or ev_date > dates[slug]):
                dates[slug] = ev_date
    for slug in by_axis:
        by_axis[slug].sort()
    return by_axis, dates


def collect_candidates(
    candidates_path: Path, axis_slugs: set[str]
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Map axis slug → sorted anchor record stems and axis slug → latest date,
    from candidate buffer lines that carry a known `dimension` slug.

    Tolerant: missing file / malformed lines / absent dimension are skipped.
    """
    anchors: dict[str, set[str]] = {}
    dates: dict[str, str] = {}
    if not candidates_path.exists():
        return {}, {}
    for line in candidates_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        slug = obj.get("dimension")
        if not isinstance(slug, str) or not slug:
            continue  # no dimension (most non-cognitive candidates) — not a typo
        if slug not in axis_slugs:
            print(
                f"warning: candidate dated {obj.get('date')}: unknown dimension "
                f"slug {slug!r} — not in axis SoT; skipped",
                file=sys.stderr,
            )
            continue
        ref = obj.get("record_ref")
        if isinstance(ref, str) and ref.strip():
            anchors.setdefault(slug, set()).add(Path(ref.strip()).stem)
        cdate = _date_str(obj.get("date"))
        if cdate and (slug not in dates or cdate > dates[slug]):
            dates[slug] = cdate
    return ({k: sorted(v) for k, v in anchors.items()}, dates)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def build_rows(
    axes: list[dict],
    promoted: dict[str, list[str]],
    promoted_dates: dict[str, str],
    cand_anchors: dict[str, list[str]],
    cand_dates: dict[str, str],
) -> list[dict]:
    rows: list[dict] = []
    for axis in axes:
        slug = axis["slug"]
        principle_ids = promoted.get(slug, [])
        has_candidate = slug in cand_anchors or slug in cand_dates
        if principle_ids:
            status = STATUS_PROMOTED
        elif has_candidate:
            status = STATUS_EVIDENCED
        else:
            status = STATUS_BLANK

        links = ", ".join(f"[[{pid}]]" for pid in principle_ids) or "—"
        anchors = cand_anchors.get(slug, [])[:MAX_ANCHORS]
        anchor_cell = ", ".join(f"[[{a}]]" for a in anchors) or "—"
        if status == STATUS_PROMOTED:
            updated = promoted_dates.get(slug) or cand_dates.get(slug) or "—"
        elif status == STATUS_EVIDENCED:
            updated = cand_dates.get(slug) or "—"
        else:
            updated = "—"
        rows.append({
            "name": axis["name"],
            "slug": slug,
            "status": status,
            "links": links,
            "anchors": anchor_cell,
            "updated": updated,
        })
    return rows


def compute_hash(rows: list[dict]) -> str:
    h = hashlib.sha256()
    for r in rows:
        for key in ("slug", "status", "links", "anchors", "updated"):
            h.update(r[key].encode("utf-8"))
            h.update(b"\x00")
        h.update(b"\x01")
    return h.hexdigest()


def render_zone_body(rows: list[dict], source_hash: str) -> str:
    blanks = [r["name"] for r in rows if r["status"] == STATUS_BLANK]
    lines: list[str] = []
    lines.append(SOURCE_COMMENT)
    lines.append(f"{HASH_PREFIX}{source_hash}{HASH_SUFFIX}")
    lines.append(f"{REGEN_PREFIX}{now_iso_utc()} -->")
    lines.append("")
    lines.append("## Оси модели")
    lines.append("")
    lines.append("| Ось | Статус | Принцип(ы) | Якорные записи | Обновлено |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['status']} | {r['links']} | {r['anchors']} | {r['updated']} |"
        )
    lines.append("")
    lines.append("## Пробелы (coverage gaps)")
    lines.append("")
    if blanks:
        lines.append(
            "Оси без данных (линзе `cognitive-model` домайнить дальше): "
            + ", ".join(blanks)
            + "."
        )
    else:
        lines.append(
            f"Все {len(rows)} осей покрыты — линза домайнит на углубление и "
            "уточнение, не на заполнение пустых."
        )
    lines.append("")
    return "\n".join(lines)


def normalise_zone(text: str) -> str:
    """Body content for the idempotency diff — drop the volatile timestamp +
    hash comment lines, strip trailing whitespace, trim trailing blanks."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(REGEN_PREFIX):
            continue
        if stripped.startswith(HASH_PREFIX):
            continue
        out.append(line.rstrip())
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def find_zone(text: str) -> tuple[int, int] | None:
    """(content_start, content_end) between the hub markers, or None."""
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


def splice(hub_text: str, new_body: str) -> str:
    bounds = find_zone(hub_text)
    if bounds is None:
        raise HubRenderError("hub markers missing or malformed")
    start, end = bounds
    if not new_body.endswith("\n"):
        new_body += "\n"
    return hub_text[:start] + new_body + hub_text[end:]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_rows(prompt_path: Path, candidates_path: Path) -> tuple[list[dict], list[dict]]:
    """Axis rows from constitution state alone — no hub file required. Shared by
    the renderer and the `--stats` coverage projection (DRY). Returns
    `(rows, dropped_unknown_slugs)`. Raises HubRenderError if the axis SoT is
    unparseable."""
    axes = load_axes(prompt_path)
    axis_slugs = {a["slug"] for a in axes}
    dropped: list[dict] = []
    promoted, promoted_dates = collect_promoted(axis_slugs, dropped)
    cand_anchors, cand_dates = collect_candidates(candidates_path, axis_slugs)
    rows = build_rows(axes, promoted, promoted_dates, cand_anchors, cand_dates)
    return rows, dropped


def stats(rows: list[dict], dropped: list[dict] | None = None) -> dict:
    """Coverage projection for lint F.4: counts + blank-axis slugs."""
    out = {
        "ok": True,
        "status_counts": {
            s: sum(1 for r in rows if r["status"] == s)
            for s in (STATUS_PROMOTED, STATUS_EVIDENCED, STATUS_BLANK)
        },
        "blank_axes": [r["slug"] for r in rows if r["status"] == STATUS_BLANK],
    }
    if dropped:
        out["dropped_unknown_slugs"] = dropped
    return out


def render(hub_path: Path, prompt_path: Path, candidates_path: Path):
    """Pure-ish compute: returns (rows, dropped, expected_body,
    current_zone_or_None, hub_text_or_None). Raises HubRenderError on
    unrenderable state."""
    rows, dropped = compute_rows(prompt_path, candidates_path)
    source_hash = compute_hash(rows)
    expected_body = render_zone_body(rows, source_hash)

    if not hub_path.exists():
        raise HubRenderError(f"hub not found: {hub_path}")
    hub_text = hub_path.read_text(encoding="utf-8")
    bounds = find_zone(hub_text)
    if bounds is None:
        # File exists but the managed-zone markers were removed (bad hand-edit,
        # or hub recreated without them). We cannot splice — surface as a
        # recoverable skip rather than letting splice() raise later. current_zone
        # is therefore always a real string when render() returns.
        raise HubRenderError("hub markers missing or malformed")
    current_zone = hub_text[bounds[0]:bounds[1]]
    return rows, dropped, expected_body, current_zone, hub_text


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", type=Path, default=None,
                        help=f"override hub path (default: {HUB_REL})")
    parser.add_argument("--prompt", type=Path, default=None,
                        help="override axis-SoT prompt path")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the rendered zone to stdout, do not write")
    parser.add_argument("--check", action="store_true",
                        help="exit 3 if the hub would change; never write")
    parser.add_argument("--stats", action="store_true",
                        help="print coverage stats (counts + blank axes) from "
                             "constitution state and exit 0; never read/write the "
                             "hub file (used by /minder:mem:lint F.4 monthly coverage)")
    args = parser.parse_args(argv)

    base = repo_root()
    hub_path = args.hub or (base / HUB_REL)
    prompt_path = args.prompt or (registries_dir() / "lenses/cognitive-model/prompt.md")
    candidates_path = state_dir() / "principle-candidates.jsonl"

    if args.stats:
        try:
            rows, dropped = compute_rows(prompt_path, candidates_path)
        except HubRenderError as exc:
            print(json.dumps({"ok": False, "reason": str(exc)}))
            return 0
        except Exception as exc:  # noqa: BLE001 — read-only stats must never crash lint
            print(json.dumps({"ok": False,
                              "reason": f"unexpected: {type(exc).__name__}: {exc}"}))
            return 0
        print(json.dumps(stats(rows, dropped)))
        return 0

    try:
        rows, dropped, expected_body, current_zone, hub_text = render(
            hub_path, prompt_path, candidates_path
        )
    except HubRenderError as exc:
        # Best-effort, like the other maintain renderers: surface and skip,
        # never crash the maintain pipeline.
        print(json.dumps({"ok": False, "changed": False, "reason": str(exc)}))
        print(f"cognitive-model-hub: skipped — {exc}", file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 — unattended maintain step must never crash
        # Defensive backstop: an unexpected error (e.g. a SchemaError from a
        # malformed principle, a transient I/O fault) degrades to a skip, not a
        # traceback that aborts the whole maintain run.
        print(json.dumps({
            "ok": False, "changed": False,
            "reason": f"unexpected: {type(exc).__name__}: {exc}",
        }))
        print(f"cognitive-model-hub: skipped — unexpected {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 0

    counts: dict[str, int] = {STATUS_PROMOTED: 0, STATUS_EVIDENCED: 0, STATUS_BLANK: 0}
    for r in rows:
        counts[r["status"]] += 1
    blanks = [r["slug"] for r in rows if r["status"] == STATUS_BLANK]

    # current_zone is always a real string here (render() raises otherwise).
    would_change = normalise_zone(current_zone) != normalise_zone(expected_body)

    if args.dry_run:
        sys.stdout.write(expected_body)
        return 0

    result = {
        "ok": True, "changed": would_change,
        "status_counts": counts, "blank_axes": blanks,
    }
    if dropped:
        result["dropped_unknown_slugs"] = dropped

    if args.check:
        print(json.dumps(result))
        return 3 if would_change else 0

    changed = False
    if would_change:
        new_text = splice(hub_text, expected_body)
        tmp = hub_path.with_suffix(hub_path.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(hub_path)
        changed = True

    result["changed"] = changed
    print(json.dumps(result))
    status = "updated" if changed else "no change"
    drop_note = f", {len(dropped)} unknown slug(s) dropped" if dropped else ""
    print(
        f"wrote {hub_path.name} "
        f"({counts[STATUS_PROMOTED]} promoted, {counts[STATUS_EVIDENCED]} evidenced, "
        f"{counts[STATUS_BLANK]} blank, {status}{drop_note})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
