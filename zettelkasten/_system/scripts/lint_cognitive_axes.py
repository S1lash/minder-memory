#!/usr/bin/env python3
"""Minder Memory lint — `cognitive_axes` frontmatter integrity.

Validates the optional `cognitive_axes` field on constitution principles (the
field that powers `5_meta/mocs/hub-cognitive-model.md`):

  - value is a list of strings (not a bare string / mapping / null-with-content)
  - every slug is a member of the axis single-source-of-truth (the
    `<!-- cognitive-axes:begin -->` YAML block in
    `_system/registries/lenses/cognitive-model/prompt.md`) — a typo'd slug never
    reaches the hub (the renderer drops it), so lint surfaces it for correction
  - no duplicate slug within one principle (the renderer dedups on read; lint
    surfaces the source so the frontmatter itself stays clean)
  - sensitivity coherence: if a `scope: sensitive` principle is tagged, the hub
    must be marked `is_sensitive: true` and kept owner-only (`audience_tags: []`)
    — otherwise the model would expose a sensitive principle to a wider audience

The slug SoT and the principle scopes are both READ here; nothing is duplicated.
Output: JSONL on stdout, one event per finding. Exit 0 always (informational —
minder-mem-lint routes findings to CLARIFICATIONs for owner review; no autofix of the
sacred constitution tree).

Usage:
    python3 lint_cognitive_axes.py [--root <path>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import configure_std_streams, constitution_root, iter_principles, read_frontmatter, repo_root
from render_cognitive_model_hub import HubRenderError, load_axes

HUB_REL = "5_meta/mocs/hub-cognitive-model.md"
PROMPT_REL = "_system/registries/lenses/cognitive-model/prompt.md"


def _emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")


def scan(root: Path) -> int:
    """Emit one JSONL event per finding. Returns the finding count."""
    prompt_path = root / PROMPT_REL
    try:
        axes = load_axes(prompt_path)
    except HubRenderError as exc:
        _emit({"scan": "cognitive-axes", "kind": "axis-sot-unreadable",
               "severity": "weak", "detail": str(exc)})
        return 1
    axis_slugs = {a["slug"] for a in axes}

    findings = 0
    sensitive_tagged: list[str] = []
    for p in iter_principles(constitution_root(root)):
        # Only active principles feed the hub (the renderer filters
        # status != active). Validating archived / placeholder / candidate
        # principles would surface noise and false-positive sensitivity
        # mismatches for principles that are not in the hub at all.
        if p.status != "active":
            continue
        raw = p.frontmatter.get("cognitive_axes")
        if raw is None:
            continue
        if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
            _emit({"scan": "cognitive-axes", "kind": "cognitive-axes-malformed",
                   "severity": "weak", "principle_id": p.id,
                   "detail": f"cognitive_axes must be a list of slug strings, got {raw!r}"})
            findings += 1
            continue
        seen: set[str] = set()
        for slug in raw:
            if slug in seen:
                _emit({"scan": "cognitive-axes", "kind": "cognitive-axes-duplicate",
                       "severity": "weak", "principle_id": p.id, "slug": slug,
                       "detail": f"slug {slug!r} listed more than once"})
                findings += 1
                continue
            seen.add(slug)
            if slug not in axis_slugs:
                _emit({"scan": "cognitive-axes", "kind": "cognitive-axes-unknown-slug",
                       "severity": "weak", "principle_id": p.id, "slug": slug,
                       "detail": f"slug {slug!r} not in axis SoT "
                                 f"({sorted(axis_slugs)}); the hub drops it"})
                findings += 1
        if raw and p.scope == "sensitive":
            sensitive_tagged.append(p.id)

    # Sensitivity coherence — only when the hub exists and a sensitive principle
    # is tagged. A wider-than-owner hub that includes a sensitive principle is the
    # leak we guard against.
    if sensitive_tagged:
        hub_path = root / HUB_REL
        parsed = read_frontmatter(hub_path)
        if parsed is not None:
            fm, _ = parsed
            is_sensitive = bool(fm.get("is_sensitive"))
            audience = fm.get("audience_tags") or []
            if not is_sensitive or (isinstance(audience, list) and audience):
                _emit({"scan": "cognitive-axes",
                       "kind": "cognitive-hub-sensitivity-mismatch",
                       "severity": "weak",
                       "sensitive_principles": sensitive_tagged,
                       "hub_is_sensitive": is_sensitive,
                       "hub_audience_tags": audience,
                       "detail": "hub includes a scope:sensitive principle but is "
                                 "not marked is_sensitive:true / owner-only — review "
                                 "before the hub is shared or surfaced"})
                findings += 1
    return findings


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None,
                        help="repo root (default: resolved from MINDER_MEMORY_BASE / file location)")
    args = parser.parse_args(argv)
    root = args.root or repo_root()
    scan(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
