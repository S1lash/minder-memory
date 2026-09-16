#!/usr/bin/env python3
"""Refuse a delivery that moves a path the tick never wrote.

The guarantee this enforces. A tick's commit may differ from `origin/main` only
on paths the tick itself produced — the ones it staged, plus those carried by the
commits it folded. Any other path that differs is content the delivery would
overwrite without ever having touched it, which is exactly how six scheduler
deliveries erased a day of records each: the tick committed a stale index on top
of a tip that had moved, and the push was a clean fast-forward.

Why the check is on content rather than on path membership. A path-level subset
test passes as soon as a file appears in the staged set, so a stale tree can
erase another tick's hunk inside a file this tick legitimately staged and the
test waves it through. Here every differing path must be in the tick's own
surface, and the surface is read from the tick's own record of what it wrote.

Usage:
  python3 scripts/scheduler/_delivery_check.py <remote-ref> <surface-file>

`<surface-file>` holds one repo-relative path per line (LF, UTF-8) — the union of
what `stage.sh` staged and what the folded commits carried. A missing or empty
surface file means the tick recorded nothing, and then any difference is
unauthorised.

Exit codes:
  0 — every differing path is in the tick's own surface
  2 — at least one is not; the offending paths are printed to stderr
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.portable import configure_std_streams  # noqa: E402


class GitFailed(RuntimeError):
    """A git call this check depends on did not succeed."""


def git(*args: str) -> str:
    """Run git, and refuse to mistake a failure for an empty answer.

    A gate protecting owner data must tell "no differences" apart from "could not
    look". Discarding the exit code here would turn an unreadable reference or a
    missing object into a clean bill of health — the same shape as reading a
    truncated check output as a pass.
    """
    res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise GitFailed(f"git {' '.join(args)} exited {res.returncode}: "
                        f"{res.stderr.strip()[:300]}")
    return res.stdout


def main(argv: list[str]) -> int:
    configure_std_streams()
    if len(argv) < 2:
        print("usage: _delivery_check.py <remote-ref> <surface-file>", file=sys.stderr)
        return 2
    remote_ref, surface_path = argv[0], argv[1]

    surface: set[str] = set()
    path = Path(surface_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            surface = {line.strip() for line in handle if line.strip()}

    try:
        changed = [p for p in git("diff", "--name-only", f"{remote_ref}..HEAD").splitlines()
                   if p]
    except GitFailed as exc:
        print(f"finalize-tick: refusing to push — the delivery check could not inspect "
              f"the difference from {remote_ref}: {exc}", file=sys.stderr)
        return 2
    unauthorised = sorted(p for p in changed if p not in surface)

    if unauthorised:
        print(f"finalize-tick: refusing to push — {len(unauthorised)} path(s) differ from "
              f"{remote_ref} that this tick never wrote:", file=sys.stderr)
        for p in unauthorised[:40]:
            print(f"  {p}", file=sys.stderr)
        if len(unauthorised) > 40:
            print(f"  … and {len(unauthorised) - 40} more", file=sys.stderr)
        print("finalize-tick: this is the shape of a stale-tree delivery; nothing was pushed.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
