#!/usr/bin/env python3
"""Compact the `## Evidence Trail` section of a single constitution note.

Replaces entries OLDER than a cutoff date with one summary entry marked
`[compacted]`. The most recent year is always preserved. The original file
before compaction stays in git history — users can always `git show` to
recover.

This script is invoked AFTER the owner has approved a compaction option in
an `evidence-trail-compact` CLARIFICATION. It does not decide on its own
whether or what to compact; it applies a pre-approved summary.

Usage:
    python3 compact_evidence_trail.py \
        --file 0_constitution/axiom/identity/001-leave-the-place-clearer.md \
        --cutoff 2025-04-20 \
        --summary "2024-04..2025-04 — cited 27 times across 18 decisions; pattern: aligned outcomes on code-review trade-offs" \
        [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from _common import (
    ConstitutionError,
    EVIDENCE_TRAIL_HEADING,
    die,
    find_evidence_trail_bounds,
    frontmatter_closed_before_body,
    parse_file,
    read_frontmatter,
    configure_std_streams,
)


# Extract frontmatter block from raw file text without round-tripping
# through YAML. Preserves original bytes — quoting, comments, spacing,
# key order — so a compact run produces a minimal diff focused only on
# the Evidence Trail section.
_FRONTMATTER_BLOCK_RE = re.compile(
    r"\A(---\r?\n.*?\r?\n---\r?\n)",
    re.DOTALL,
)


def extract_frontmatter_block(raw: str) -> tuple[str, str]:
    """Split raw file text into (frontmatter_block, body_text).

    `frontmatter_block` includes both `---` fences and the newline after
    the closing fence. `body_text` is everything after. Raises if the
    file has no frontmatter.
    """
    m = _FRONTMATTER_BLOCK_RE.match(raw)
    if not m:
        raise ConstitutionError("no frontmatter block found")
    fm_block = m.group(1)
    body_text = raw[m.end():]
    return fm_block, body_text


MIN_PROTECTED_DAYS = 365  # never compact entries newer than this


ENTRY_LINE_PATTERN = None  # lazy-imported below


_ENTRY_RE = re.compile(r"^\s*-\s+\*\*(\d{4}-\d{2}-\d{2})\*\*")


def _parse_entry_date(line: str) -> date | None:
    """Extract ISO date from an Evidence Trail line.

    Recognised shapes:
        - **YYYY-MM-DD** | event | ... — description
    Returns None for lines that are not entries (blank, comment, etc.).
    """
    m = _ENTRY_RE.match(line)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _is_already_compacted(line: str) -> bool:
    return "[compacted]" in line


def compact_section(section: str, cutoff: date, summary_body: str) -> tuple[str, int]:
    """Return (new_section, removed_entry_count).

    `section` is the text between the `## Evidence Trail` heading and the next
    section. Entries with date < cutoff are collapsed into a single
    `[compacted]` entry whose body is `summary_body`.
    Entries >= cutoff are preserved in original order (newest-first).
    """
    lines = section.splitlines()

    kept: list[str] = []
    compacted_count = 0
    # We keep the overall shape: blank lines and non-entry lines pass through,
    # entry lines split by date. Already-compacted summaries are preserved as-is
    # regardless of their date, so we never summarise a summary.
    for line in lines:
        if _is_already_compacted(line):
            kept.append(line)
            continue
        d = _parse_entry_date(line)
        if d is None:
            kept.append(line)
            continue
        if d >= cutoff:
            kept.append(line)
        else:
            compacted_count += 1

    if compacted_count == 0:
        # Nothing to do. Return as-is to signal no-op.
        return section, 0

    # Compose the single compacted summary entry. Use the cutoff as its date
    # so it sorts correctly among kept entries (newest-first).
    summary_line = (
        f"- **{cutoff.isoformat()}** | compacted | "
        f"[compacted] {summary_body.strip()}"
    )

    # Insert the summary at the end of the kept entries (they are newest-first,
    # so summary is the oldest line in the new section — matches chronology).
    # Handle trailing blank lines cleanly.
    while kept and kept[-1].strip() == "":
        kept.pop()
    kept.append(summary_line)
    kept.append("")
    return "\n".join(kept) + "\n", compacted_count


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True,
                        help="target constitution note")
    parser.add_argument("--cutoff", required=True,
                        help="ISO date (YYYY-MM-DD); entries strictly older than this are compacted")
    parser.add_argument("--summary", required=True,
                        help="one-line summary body approved by human (without the [compacted] prefix)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the modified file to stdout without writing")
    args = parser.parse_args(argv)

    try:
        cutoff = date.fromisoformat(args.cutoff)
    except ValueError:
        die(f"--cutoff {args.cutoff!r} is not an ISO date (YYYY-MM-DD)")

    # Safety: never compact inside the protected window.
    earliest_allowed_cutoff = date.today() - timedelta(days=MIN_PROTECTED_DAYS)
    if cutoff > earliest_allowed_cutoff:
        die(
            f"cutoff {cutoff} is inside the protected window "
            f"(no compaction allowed newer than {earliest_allowed_cutoff}, "
            f"i.e. last {MIN_PROTECTED_DAYS} days must be preserved)"
        )

    try:
        principle = parse_file(args.file)
    except ConstitutionError as exc:
        die(str(exc))

    bounds = find_evidence_trail_bounds(principle.body)
    if bounds is None:
        die(f"{args.file}: no `{EVIDENCE_TRAIL_HEADING}` section found")

    start, end = bounds
    section = principle.body[start:end]

    new_section, count = compact_section(section, cutoff, args.summary)
    if count == 0:
        print(f"{args.file}: no entries older than {cutoff} — nothing to compact",
              file=sys.stderr)
        return 0

    # Preserve the original frontmatter bytes exactly — only the body is
    # modified. This keeps the diff minimal and avoids accidental key-order
    # or quoting changes from a YAML re-serialisation.
    raw = args.file.read_text(encoding="utf-8")
    try:
        fm_block, original_body = extract_frontmatter_block(raw)
    except ConstitutionError as exc:
        die(f"{args.file}: {exc}")

    # The body we want to write is the modified one from our splice above.
    # `original_body` and `principle.body` point at the same content but via
    # different parsers; we use principle.body for the splice offsets and
    # stitch together with the frontmatter block preserved byte-for-byte.
    new_body = principle.body[:start] + new_section + principle.body[end:]
    new_full = fm_block + new_body
    if not new_full.endswith("\n"):
        new_full += "\n"

    if args.dry_run:
        sys.stdout.write(new_full)
        print(f"\n[dry-run] would compact {count} entries", file=sys.stderr)
        return 0

    # Atomic write — never leave a partial file on interrupt.
    tmp = args.file.with_suffix(args.file.suffix + ".tmp")
    tmp.write_text(new_full, encoding="utf-8")
    # Defence-in-depth via the canonical fence helpers (single SoT for
    # frontmatter integrity) — never replace the live file with output whose
    # YAML fence no longer closes before the body or no longer parses.
    if not frontmatter_closed_before_body(tmp) or read_frontmatter(tmp) is None:
        tmp.unlink(missing_ok=True)
        die(f"{args.file}: refusing to write — compacted output failed frontmatter integrity check")
    tmp.replace(args.file)
    print(f"compacted {count} entries in {args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
