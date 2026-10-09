#!/usr/bin/env python3
"""Regenerate `_system/views/constitution-core.md` — harness core view.

Output lives inside the repo. The Claude Code harness reaches it through
`~/.claude/minder-memory/constitution-core.md`, which `install.sh` links here.

Deterministic, no LLM. Filters by `core: true`, `status != placeholder`,
and `applies_to` contains `claude-code`. All scopes (shared / personal /
sensitive) are visible in the single-context model — scope filtering
ships when multi-user scenarios land.

Usage:
    python3 gen_constitution_core.py [--output PATH] [--dry-run]
                                     [--advisory-lines N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import (
    ALL_SCOPES_VISIBLE,
    ConstitutionError,
    Principle,
    constitution_root,
    die,
    is_visible,
    iter_principles,
    now_iso_utc,
    views_dir,
    configure_std_streams,
)


# Soft guidance, not a limit. Harness view that exceeds this logs a warning
# and still ships — quality of content beats artificial length cap.
CORE_VIEW_ADVISORY_LINES = 80


def default_output_path() -> Path:
    """Single harness view file, linked from `~/.claude/minder-memory/` by `install.sh`."""
    return views_dir() / "constitution-core.md"


def select_for_core(principles: list[Principle]) -> list[Principle]:
    """Filter principles for the harness core view."""
    selected: list[Principle] = []
    for p in principles:
        if not p.is_core:
            continue
        if not is_visible(p, consumer="claude-code"):
            continue
        selected.append(p)
    # Axioms first, then principles, then rules. Within each type: by id.
    order = {"axiom": 0, "principle": 1, "rule": 2}
    selected.sort(key=lambda p: (order.get(p.type, 99), p.id))
    return selected


def render_core(
    principles: list[Principle],
    advisory_exceeded: bool,
) -> str:
    lines: list[str] = []
    lines.append("# Constitution core (auto-generated — do not edit)")
    lines.append("")
    lines.append(f"<!-- Generated: {now_iso_utc()} -->")
    lines.append(f"<!-- Source: 0_constitution/ where core=true, "
                 f"status!=placeholder, applies_to includes claude-code, "
                 f"scope in {sorted(ALL_SCOPES_VISIBLE)} -->")
    if advisory_exceeded:
        lines.append(
            f"<!-- NOTE: view exceeds advisory length of "
            f"{CORE_VIEW_ADVISORY_LINES} lines — compression discipline "
            f"(see CONSTITUTION.md §13 invariant #13). -->"
        )
    lines.append("")
    if not principles:
        lines.append("_No core principles active in this context._")
        lines.append("")
        lines.append("For the full tree, invoke `/check-decision`.")
        return "\n".join(lines) + "\n"

    for p in principles:
        lines.append(f"## `{p.id}` — {p.title}")
        lines.append(p.statement)
        lines.append(f"*type: {p.type} · domain: {p.domain} · tier: {p.priority_tier} · scope: {p.scope}*")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("For the full tree — including non-core tier-1 principles, "
                 "rules, and trade-off resolution — invoke `/check-decision`.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None,
                        help="override output path (default: _system/views/constitution-core.md)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print rendered core to stdout without writing")
    parser.add_argument(
        "--advisory-lines", type=int, default=CORE_VIEW_ADVISORY_LINES,
        help=f"advisory soft limit; over-limit logs a warning but still ships "
             f"(default: {CORE_VIEW_ADVISORY_LINES})",
    )
    args = parser.parse_args(argv)

    try:
        principles = iter_principles(constitution_root())
    except ConstitutionError as exc:
        die(str(exc))

    selected = select_for_core(principles)
    probe = render_core(selected, advisory_exceeded=False)
    line_count = probe.count("\n")
    advisory_exceeded = line_count > args.advisory_lines
    content = (
        render_core(selected, advisory_exceeded=True)
        if advisory_exceeded else probe
    )
    if advisory_exceeded:
        print(
            f"warning: rendered core is {line_count} lines, exceeds advisory "
            f"{args.advisory_lines}. Compression discipline — revisit which "
            f"`core: true` notes truly need to be always-on.",
            file=sys.stderr,
        )

    if args.dry_run:
        sys.stdout.write(content)
        return 0

    out_path = args.output or default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(out_path)
    print(f"wrote {out_path} ({len(selected)} core principles, {line_count} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
