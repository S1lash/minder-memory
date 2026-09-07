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

from lib import ownership  # noqa: E402
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


def _engine_ref(root: Path) -> str | None:
    """The ref whose history says what the ENGINE has ever shipped.

    Which remote that is comes from `lib.ownership` — the same answer the
    harness migration uses to decide which remote to repoint. Two answers to
    «whose remote is this» would let one step protect what another deletes.
    `sync_engine.sh` has already fetched it by the time retirement runs.
    """
    remote, branch = ownership.sync_remote_and_branch(root)
    if remote is None:
        return None
    for ref in (f"{remote}/{branch}", "FETCH_HEAD"):
        probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", ref],
                               capture_output=True, text=True)
        if probe.returncode == 0 and probe.stdout.strip():
            return ref
    return None


def _engine_ever_shipped(root: Path, ref: str, relpath: str) -> bool:
    """Did this exact path ever exist in the engine's own history?"""
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-list", "-n", "1", ref, "--", relpath],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return probe.returncode == 0 and bool(probe.stdout.strip())


def owner_files_inside(root: Path, relpath: str) -> tuple:
    """(files the OWNER put in this directory, why we could not tell).

    A retired path names a directory the ENGINE shipped, and the question is
    which files inside it are the engine's. Git-tracked-ness cannot answer it:
    the update tells the owner to `git add -A && git commit`, so a file of
    theirs is untracked on the first sync and tracked on the second — and the
    directory got deleted with their file inside it on the second.

    What settles it is the engine's own history. A path the engine ever shipped
    appears in the sync remote's log; a path it never shipped does not, whoever
    has committed it since. No reachable history means no answer, and no answer
    means keep — the cost of keeping a dead directory is a stale folder, the
    cost of guessing wrong is the owner's file.
    """
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard",
         "-z", "--", relpath],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    inside = [q for q in listed.stdout.split("\0") if q.strip()] if listed.returncode == 0 else []
    for path in (root / relpath).rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel not in inside:
                inside.append(rel)
    if not inside:
        return [], None
    ref = _engine_ref(root)
    if ref is None:
        return sorted(inside), ("no engine history is reachable here, so which files are the "
                                "engine's cannot be answered")
    return sorted(q for q in inside if not _engine_ever_shipped(root, ref, q)), None


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
            strays, unanswerable = owner_files_inside(root, relpath)
            if strays or unanswerable:
                kept.append((relpath, strays, unanswerable))
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
    for path, strays, unanswerable in kept:
        if unanswerable:
            print(f"retire: kept {path} — {unanswerable}. Nothing was deleted.")
            continue
        print(f"retire: kept {path} — it holds {len(strays)} file(s) the engine never "
              "shipped, and a recursive delete would take them with it:")
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
