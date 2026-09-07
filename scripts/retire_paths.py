#!/usr/bin/env python3
"""Remove the engine paths the manifest lists as retired.

A sync copies what upstream HAS. It cannot express what upstream no longer
has: `sync_engine.sh` walks the `engine:` list, and a path that is gone
upstream simply is not walked — so it stays on the clone forever. Dead
modules sit beside live ones, dead tests are still collected by pytest, and a
log written by a subsystem that no longer exists still reads as a log that
stopped updating. Every removal the engine has ever made is still present on
every clone that predates it.

`retired:` is the missing half of the contract. The author lists a path once,
and every sync converges every clone. This runs on each update rather than as
a one-off migration on purpose: a migration reaches only the clones that have
not run it yet, while this reaches any clone at any version, including one
that has been dark for months.

Two properties keep it safe to run unattended:

- **It never leaves engine space.** A retired path that falls under an
  `exclude:` entry — the manifest's own enumeration of owner space — is
  refused, and the refusal is an error rather than a skip, because a path
  listed in the wrong section is an authoring mistake that must be seen. A
  file the OWNER produced is retired by a migration that explains itself, if
  at all; never by a sweep they did not ask for.
- **It only ever deletes what the manifest names.** No globs, no directory
  recursion into anything unlisted, no inference from what upstream lacks.
  «Absent upstream» is not evidence of retirement — it is equally the shape
  of a botched checkout, which is exactly how a bad path list once read as
  «upstream deleted the entire engine».

Exit codes:
- 0 — nothing to do, or the listed paths were removed
- 2 — a retired path falls under `exclude:` (authoring error; nothing deleted)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.manifest import load_manifest, repo_root  # noqa: E402
from lib.portable import configure_stdout  # noqa: E402


def _covered_by(entry: str, relpath: str) -> bool:
    """True when `relpath` falls under one manifest entry.

    Directory entries end in `/` and cover everything beneath them; a file
    entry matches itself only.

    `*/` covers the SUBDIRECTORIES of a directory and not the files sitting
    directly in it — `_system/roles/*/` is owner instance dirs, while
    `_system/roles/_run-frame.md` beside them is engine. Reading the star as a
    plain prefix looks like the cautious choice and is not: it swallows those
    engine files into owner space, and the guard then refuses the whole sweep
    over paths it was built to remove. A guard that over-covers does not fail
    safe, it fails shut.
    """
    entry = entry.strip()
    if not entry:
        return False
    if entry.endswith("*/"):
        prefix = entry[:-2]
        return relpath.startswith(prefix) and "/" in relpath[len(prefix):]
    if entry.endswith("/"):
        return relpath.startswith(entry)
    return relpath == entry


def guard(retired: list, excluded: list) -> list:
    """Retired paths that would reach into owner space. Empty is the good case."""
    return [
        path for path in retired
        if any(_covered_by(entry, path) for entry in excluded)
    ]


def untracked_inside(root: Path, relpath: str) -> list:
    """Files inside a directory that git does not track — the owner's, not ours.

    A retired path names a directory the ENGINE shipped. What the engine put
    there, git tracks. Anything else was put there by the owner, and a recursive
    delete would take it with the module it was sitting beside — silently, in
    the one step of the update whose whole job is deletion. So the directory is
    reported instead, and the owner decides.
    """
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z",
             "--", relpath],
            capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [p.decode("utf-8", "surrogateescape")
            for p in listed.split(b"\0") if p.strip()]


def retire(root: Path, retired: list, dry_run: bool = False) -> tuple:
    """Delete each listed path that exists.

    Returns `(removed, kept)` — `kept` naming every retired directory left in
    place because it holds files the owner put there.
    """
    removed = []
    kept = []
    for relpath in retired:
        target = root / relpath
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_dir() and not target.is_symlink():
            strays = untracked_inside(root, relpath)
            if strays:
                kept.append((relpath, strays))
                continue
        removed.append(relpath)
        if dry_run:
            continue
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    return removed, kept


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="repo root (default: resolved)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be removed, delete nothing")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else repo_root()
    manifest = load_manifest(root)
    retired = [str(p) for p in (manifest.get("retired") or [])]
    excluded = [str(p) for p in (manifest.get("exclude") or [])]

    if not retired:
        print("retire: nothing listed")
        return 0

    trespassing = guard(retired, excluded)
    if trespassing:
        print("retire: refusing to run — these retired paths fall under exclude: "
              "(owner space), which a sweep must never delete:", file=sys.stderr)
        for path in trespassing:
            print(f"  {path}", file=sys.stderr)
        print("  Retire an owner-produced artifact with a migration that says so.",
              file=sys.stderr)
        return 2

    removed, kept = retire(root, retired, dry_run=args.dry_run)
    for path, strays in kept:
        print(f"retire: kept {path} — it holds {len(strays)} file(s) the engine did not put "
              "there, and a recursive delete would take them with it:")
        for stray in strays[:8]:
            print(f"    {stray}")
        print("    Move what you want to keep, then re-run the update.")
    if not removed:
        print(f"retire: clean ({len(retired)} listed, "
              f"{len(kept)} kept for your files, none else present)")
        return 0
    verb = "would remove" if args.dry_run else "removed"
    print(f"retire: {verb} {len(removed)} retired path(s)")
    for path in removed:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
