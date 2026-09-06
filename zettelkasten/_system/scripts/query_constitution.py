#!/usr/bin/env python3
"""Query visible constitution principles as JSON.

Consumed by `/minder:mem:check-decision`, `/minder:mem:lint` Scan F, and any future
skill that needs the filtered tree.

Filter layers (all AND'd):
  - `--consumer`    : principle.applies_to must include this value
                      (empty principles with no applies_to pass through)
  - `--domains`     : optional comma-separated domain whitelist
  - `--include-placeholder` : allow status=placeholder (for tests)
  - `--include-archived`    : allow status=archived (for lint health view)

Scope-based narrowing is not currently applied — all three scopes are
visible. The scope field stays on principles for future multi-user
scenarios.

Deterministic, no LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from _common import (
    ALLOWED_DOMAINS,
    ConstitutionError,
    Principle,
    constitution_root,
    die,
    is_visible,
    iter_principles,
    configure_std_streams,
)


def _iso(v):
    """PyYAML returns `date` for `YYYY-MM-DD` values; JSON needs strings."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def principle_to_dict(p: Principle) -> dict:
    fm = p.frontmatter
    return {
        "id": p.id,
        "title": p.title,
        "type": p.type,
        "domain": p.domain,
        "priority_tier": p.priority_tier,
        "core": p.is_core,
        "scope": p.scope,
        "applies_to": p.applies_to,
        "binding": fm.get("binding", "hard"),
        "framing": fm.get("framing", "positive"),
        "confidence": fm.get("confidence", "proven"),
        "status": p.status,
        "last_reviewed": _iso(fm.get("last_reviewed")),
        "last_applied": _iso(fm.get("last_applied")),
        "derived_from": fm.get("derived_from", []) or [],
        "contradicts": fm.get("contradicts", []) or [],
        "statement": p.statement,
        "body": p.body,
        "path": str(p.path.relative_to(constitution_root().parent)),
    }


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--consumer", default="claude-code",
        help="filter by applies_to inclusion (default: claude-code); "
             "pass empty string to skip consumer filter",
    )
    parser.add_argument(
        "--domains", default=None,
        help="comma-separated domain enum subset filter",
    )
    parser.add_argument(
        "--include-placeholder", action="store_true",
        help="include status=placeholder notes (for test fixtures)",
    )
    parser.add_argument(
        "--include-archived", action="store_true",
        help="include status=archived notes",
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="emit compact JSON (no indent)",
    )
    args = parser.parse_args(argv)

    try:
        principles = iter_principles(constitution_root())
    except ConstitutionError as exc:
        die(str(exc))

    requested_domains = None
    if args.domains:
        requested_domains = {d.strip() for d in args.domains.split(",") if d.strip()}
        unknown = requested_domains - ALLOWED_DOMAINS
        if unknown:
            die(f"unknown domains in filter: {sorted(unknown)}")

    allow_statuses: set[str] = set()
    if args.include_placeholder:
        allow_statuses.add("placeholder")
    if args.include_archived:
        allow_statuses.add("archived")

    consumer = args.consumer or None

    visible = []
    for p in principles:
        if not is_visible(p, consumer=consumer, allow_statuses=allow_statuses):
            continue
        if requested_domains and p.domain not in requested_domains:
            continue
        visible.append(principle_to_dict(p))

    indent = None if args.compact else 2
    json.dump(visible, sys.stdout, ensure_ascii=False, indent=indent)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
