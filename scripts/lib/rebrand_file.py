#!/usr/bin/env python3
"""Rewrite one file through the rename map, in place.

minder-memory-rebrand: keep-legacy-tokens — this file names the former product
because routing to the map is its whole subject.

Why a script and not a `sed`. The vault seeder has to repoint the dashboard's
name inside `.obsidian/*.json` when a vault arrives carrying the former name.
A blind `s/minder-ztn/minder-memory/g` did that — and also rewrote
`"vaultName": "minder-ztn-иванов"`, the owner's own vault, into a name that
does not exist, in the file Obsidian reads at startup. Shell has no way to ask
«is this name the engine's»; `lib.ownership` does, and the rename map already
consults it. So the seeder calls this instead of writing the rule a second time
in `sed`.

Exits 0 having changed nothing when the map is not present — a retired
migration is not a failure, and the caller has a narrower fallback.

Usage:
  python3 scripts/lib/rebrand_file.py <path> [<path> ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.portable import configure_std_streams  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print("rebrand_file: nothing to rewrite", file=sys.stderr)
        return 2
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))
        from _032_minder_memory_rebrand import rebrand_text  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — the map is a migration and may be retired
        print("rebrand_file: the rename map is not present; nothing rewritten")
        return 0
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new_text = rebrand_text(text)
        if new_text != text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(new_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
