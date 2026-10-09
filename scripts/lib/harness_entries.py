#!/usr/bin/env python3
"""Name the harness entries this clone's installer removes, for a shell caller.

`install.sh` decides what it may remove from `~/.claude/` by asking the ownership
module, not by restating the rule in bash: `lib.ownership` is the one home of
«did the engine ship this harness entry», and the post-update check decides by
the same function — so the check never asks for a re-run that cannot change
anything, and bash never has to resolve a link's spelling on its own.

Output is one path per line, LF-terminated on every platform
(`lib.portable.emit_lines`).

Usage:
  python3 scripts/lib/harness_entries.py --removable-rule-links --home <claude-home> --repo <repo-root>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.ownership import removable_retired_rule_links  # noqa: E402
from lib.portable import emit_lines  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Emit the harness entries this clone's installer removes")
    ap.add_argument("--removable-rule-links", action="store_true", required=True,
                    help="the retired links in <home>/rules/ that point into <repo>")
    ap.add_argument("--home", required=True, type=Path, help="the Claude Code home (CLAUDE_HOME)")
    ap.add_argument("--repo", required=True, type=Path, help="this clone's root")
    args = ap.parse_args(argv)
    emit_lines(str(p) for p in removable_retired_rule_links(args.home, args.repo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
