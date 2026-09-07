#!/usr/bin/env python3
"""The oldest engine a clone may update FROM.

The migration chain starts at `031`: the migrations that shaped a base between
older releases and `0.69.0` are not part of the current engine. A clone below
the floor updates to `0.69.0` first (the skeleton keeps that release on the
branch named below), then to the current release — the sync refuses the direct
jump rather than applying an engine whose migrations assume a shape the clone
never reached.

Usage (exit 0 = may update, 3 = below the floor or no version, 2 = unparseable):
  python3 scripts/lib/version_floor.py <version-of-the-clone>
  python3 scripts/lib/version_floor.py --floor-branch   # the branch the first step syncs from
  python3 scripts/lib/version_floor.py --min-version
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.portable import configure_std_streams  # noqa: E402

MIN_UPDATABLE_VERSION = "0.69.0"
FLOOR_BRANCH = "release/0.69.0"


def parse(version: str) -> tuple[int, int, int]:
    """`MAJOR.MINOR.PATCH` as integers; a missing PATCH counts as 0 and a
    pre-release suffix (`1.0.0-rc1`) is ignored for the comparison."""
    core = version.strip().split("-", 1)[0].split("+", 1)[0]
    parts = [int(part) for part in core.split(".")]
    if not 1 <= len(parts) <= 3:
        raise ValueError(version)
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def below_floor(version: str) -> bool:
    return parse(version) < parse(MIN_UPDATABLE_VERSION)


# The two-step path, as ONE block. It is printed by the refusal and quoted by
# `docs/upstream-sync.md`; `test_engine_lib.py` pins the doc equal to this, so a
# friend cannot be handed two different sets of commands for the same journey.
#
# `--self-heal` on BOTH sync steps, and for the same reason each time: the step
# must run the update machinery of the release it is syncing FROM, not whatever
# the clone happens to be carrying. Without it on the last step the clone runs
# the 0.69.0 script it just committed, which finishes with that release's own
# closing text — no self-check, no commit line — and leaves the update
# uncommitted with nothing saying so.
TWO_STEP_COMMANDS: tuple[str, ...] = (
    f"bash scripts/sync_engine.sh --self-heal --branch {FLOOR_BRANCH}   # to the floor release",
    'git add -A && git commit -m "engine 0.69.0"                       # what /minder:mem:update does for you',
    "bash scripts/sync_engine.sh --self-heal                           # then to the current one",
)


def two_step_block() -> str:
    """The three commands, one per line, as both the refusal and the doc show them."""
    return "\n".join(f"    {line}" for line in TWO_STEP_COMMANDS)


def two_step_message(version: str) -> str:
    return (
        f"version_floor: this clone is at {version or '<no VERSION file>'}, below {MIN_UPDATABLE_VERSION}. "
        f"Update to {MIN_UPDATABLE_VERSION} first, in three steps:\n"
        f"{two_step_block()}\n"
        f"`--self-heal` on both sync steps is what puts the machinery of the release "
        f"being synced FROM in place before it runs.\n"
        f"Nothing is wrong with your clone or with the engine's manifest. If the lines "
        f"after this one mention fixing a `retired:` section, they come from the older "
        f"update script this clone still carries — the refusal cannot reach into a "
        f"script it did not write, so it says this instead. Ignore them and follow the "
        f"three steps above."
    )


def version_at_head(repo_root) -> str:
    """The engine version this clone had BEFORE the sync overwrote the file.

    A sync copies `integrations/VERSION` early, so by the time anything in the
    NEW tree runs, the file already says the new number. What the clone was is
    in `HEAD` — it has not committed yet, and it is about to be asked to.
    """
    import subprocess  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415
    shown = subprocess.run(
        ["git", "-C", str(repo_root), "show", "HEAD:integrations/VERSION"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if shown.returncode != 0:
        local = _Path(repo_root) / "integrations/VERSION"
        return local.read_text(encoding="utf-8").strip() if local.is_file() else ""
    return shown.stdout.strip()


def refuse_if_below_floor(repo_root) -> str | None:
    """The two-step message when this clone jumped the floor, else None.

    Called from `retire_paths.py`, which is the FIRST thing a sync executes out
    of the newly-copied tree — and that is the point. A pre-floor clone runs its
    OWN `sync_engine.sh`, so a refusal written only in the new shell script is
    never reached: the old script copies the new engine over itself and carries
    on. Reaching this code AT ALL means a tree carrying it was copied in, and a
    tree carrying it is above the floor by construction — so a clone below the
    floor at HEAD is, by definition, the jump this refuses.
    """
    version = version_at_head(repo_root)
    if not version:
        return None
    try:
        if not below_floor(version):
            return None
    except ValueError:
        return None
    return two_step_message(version)


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "--floor-branch":
        print(FLOOR_BRANCH)
        return 0
    if args and args[0] == "--min-version":
        print(MIN_UPDATABLE_VERSION)
        return 0
    version = args[0].strip() if args else ""
    if not version:
        # A clone with no VERSION file predates the file itself — older than
        # anything the floor admits.
        print(two_step_message(""), file=sys.stderr)
        return 3
    try:
        low = below_floor(version)
    except ValueError:
        print(f"version_floor: cannot parse {version!r}", file=sys.stderr)
        return 2
    if low:
        print(two_step_message(version), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
