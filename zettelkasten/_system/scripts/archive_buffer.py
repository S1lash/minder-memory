#!/usr/bin/env python3
"""Archive + verify + clear a weekly-aggregation candidate buffer.

Mechanical part of `/minder:mem:lint` weekly sub-scans:
- Scan F.3 — `principle-candidates.jsonl`
- Scan C.5 — `people-candidates.jsonl`

Splits the «archive before clear» contract into a standalone, deterministic
script. Per-buffer archive naming uses the buffer filename stem as prefix:

    1. Copy `_system/state/{buffer-stem}.jsonl` to
       `_system/state/lint-context/weekly/{YYYY-WW}-{buffer-stem}-archived.jsonl`.
    2. Read the archive back, compare line count with the live buffer.
    3. Only if counts match: truncate the buffer to zero bytes.
    4. On any mismatch: do NOT clear. Exit with status 2 and a stderr
       message that lint can turn into a `lint-archive-failure`
       CLARIFICATION.

Usage:
    python3 archive_buffer.py [--week YYYY-WW] [--buffer PATH]
                              [--archive-dir PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from _common import configure_std_streams, die, state_dir


BUFFER_FILENAME = "principle-candidates.jsonl"
ARCHIVE_SUBDIR = Path("lint-context") / "weekly"


def iso_week_tag(d: date | None = None) -> str:
    d = d or date.today()
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _count_nonblank_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def archive_and_clear(
    buffer_path: Path,
    archive_path: Path,
    *,
    dry_run: bool = False,
) -> int:
    """Return the number of candidates archived. On verify failure raise."""
    buffer_line_count = _count_nonblank_lines(buffer_path)
    if buffer_line_count == 0:
        return 0

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return buffer_line_count

    # Copy then fsync so the archive is durable before we clear.
    shutil.copyfile(buffer_path, archive_path)
    with archive_path.open("rb") as fh:
        import os as _os
        _os.fsync(fh.fileno())

    archive_line_count = _count_nonblank_lines(archive_path)
    if archive_line_count != buffer_line_count:
        raise RuntimeError(
            f"verify failed: buffer has {buffer_line_count} lines, archive "
            f"has {archive_line_count}. Buffer NOT cleared."
        )

    # Truncate buffer to zero bytes, keep the file.
    buffer_path.write_text("", encoding="utf-8")
    return buffer_line_count


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--week", default=None,
        help="ISO week tag for archive filename (default: current UTC week)",
    )
    parser.add_argument(
        "--buffer", type=Path, default=None,
        help=f"override buffer path (default: _system/state/{BUFFER_FILENAME})",
    )
    parser.add_argument(
        "--archive-dir", type=Path, default=None,
        help="override archive directory (default: _system/state/lint-context/weekly)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print would-archive count without copying or clearing",
    )
    args = parser.parse_args(argv)

    buffer_path = args.buffer or (state_dir() / BUFFER_FILENAME)
    archive_dir = args.archive_dir or (state_dir() / ARCHIVE_SUBDIR)
    week_tag = args.week or iso_week_tag()
    # Derive archive prefix from buffer filename stem so multiple buffers
    # (principle-candidates.jsonl, people-candidates.jsonl, ...) can share
    # the same script without colliding archive filenames.
    buffer_stem = buffer_path.stem  # "principle-candidates" or "people-candidates"
    archive_path = archive_dir / f"{week_tag}-{buffer_stem}-archived.jsonl"

    try:
        n = archive_and_clear(buffer_path, archive_path, dry_run=args.dry_run)
    except RuntimeError as exc:
        # Verify failure — exit 2 so lint knows to raise
        # lint-archive-failure CLARIFICATION; buffer remains untouched.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[dry-run] would archive {n} candidates to {archive_path}")
        return 0

    if n == 0:
        print(f"buffer empty at {buffer_path} — nothing to archive")
        return 0

    print(f"archived {n} candidates → {archive_path} (buffer cleared)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
