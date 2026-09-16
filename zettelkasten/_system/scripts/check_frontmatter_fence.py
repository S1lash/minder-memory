#!/usr/bin/env python3
"""Check — and optionally repair — the frontmatter fence of written notes.

The one runnable home of the fence-integrity check that `/minder:mem:process`,
`/minder:mem:lint` and `/minder:mem:agent-lens` perform on every LLM-composed
file. The check itself is two `_common` helpers
(`frontmatter_closed_before_body` AND `read_frontmatter`) plus the
deterministic `repair_misplaced_fence`. A skill runs this script rather than
composing those calls inline: a check a model re-writes on every run fails on
the model's own typing mistakes (a `str` where a `Path` was expected, a tuple
read as a dict) instead of on the defect it exists to find.

One status per path:

- `ok` — fence closes before the body and the YAML parses.
- `repaired` — a misplaced fence was relocated (`--repair` only).
- `fence-misplaced` — a `## ` heading sits inside the fence; without
  `--repair` this is the finding, with `--repair` it means the shape was
  ambiguous and nothing was written → `frontmatter-fence-misplaced`.
- `yaml-invalid` — the fence is well-placed but the YAML does not parse, or
  its root is not a mapping → `frontmatter-unfixable-schema`.
- `no-frontmatter` — the file does not open with `---`.
- `missing` — the path is not a readable file.

Exit code: 0 when every path is `ok` or `repaired`, 1 otherwise, 2 on usage.
`no-frontmatter` counts as a failure: every file this check is pointed at is
one the engine wrote with frontmatter.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common  # type: ignore  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from lib.portable import configure_stdin, configure_stdout  # noqa: E402

PASSING = ("ok", "repaired")


def _opens_with_fence(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
    except (OSError, UnicodeDecodeError):
        return False
    return first.rstrip("\r\n").strip() == "---"


def check_path(path: Path, repair: bool) -> str:
    if not path.is_file():
        return "missing"
    if not _opens_with_fence(path):
        return "no-frontmatter"
    if _common.frontmatter_closed_before_body(path):
        return "ok" if _common.read_frontmatter(path) is not None else "yaml-invalid"
    if repair and _common.repair_misplaced_fence(path):
        return "repaired"
    return "fence-misplaced"


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    ap = argparse.ArgumentParser(description="Check the frontmatter fence of notes")
    ap.add_argument("paths", nargs="*", type=Path, help="note files to check")
    ap.add_argument("--stdin", action="store_true",
                    help="also read newline-separated paths from stdin")
    ap.add_argument("--repair", action="store_true",
                    help="relocate an unambiguous misplaced fence in place")
    ap.add_argument("--json", action="store_true", help="one JSON object per line")
    args = ap.parse_args(argv)

    paths = list(args.paths)
    if args.stdin:
        configure_stdin()
        paths.extend(Path(line.strip()) for line in sys.stdin if line.strip())
    if not paths:
        ap.print_usage(sys.stderr)
        return 2

    failed = 0
    for path in paths:
        status = check_path(path, args.repair)
        if status not in PASSING:
            failed += 1
        if args.json:
            print(json.dumps({"path": str(path), "status": status}, ensure_ascii=False))
        else:
            print(f"{status}\t{path}")  # portability-ok: configure_stdout() runs first in main()
    if not args.json:
        print(f"checked {len(paths)}, failing {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
