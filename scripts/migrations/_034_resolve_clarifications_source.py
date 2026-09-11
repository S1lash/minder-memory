#!/usr/bin/env python3
"""Migration 034's check — is the `resolve-clarifications` source registered?

The migration never writes the owner's registry: registering a source is
`/minder:mem:source-add`'s job. When the row is missing it prints, for the agent
running `/minder:mem:update`, the exact command, and exits non-zero so the runner
records `partial` and the check comes back on every update until the source
exists. A row under Deprecated Sources is the owner's decision and ends the check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.portable import configure_std_streams, read_text_utf8  # noqa: E402

SOURCE_ID = "resolve-clarifications"
REGISTRY = Path("zettelkasten/_system/registries/SOURCES.md")
SECTIONS = ("active", "reserved", "deprecated")
# Identical to the description of the row SOURCES.template.md ships; the suite
# asserts the two register the same row.
DESCRIPTION = ("Knowledge the owner states while resolving clarifications, filed here by "
               "/minder:mem:resolve-clarifications and processed like any source.")
COMMAND = (f"/minder:mem:source-add --id {SOURCE_ID} --family transcript --layout flat-md "
           f"--default-domain auto --status active --description \"{DESCRIPTION}\"")
TAG = "[migration 034]"


def section_of(text: str) -> str | None:
    """The Sources section (`active` / `reserved` / `deprecated`) holding the row, or
    None. Only rows inside a Sources section count — a row quoted elsewhere is not a
    registration."""
    kind = ""
    for line in text.split("\n"):
        line = line.rstrip("\r").lstrip("\ufeff")
        if line.startswith("## "):
            words = line[3:].strip().lower().split()
            kind = words[0] if len(words) == 2 and words[1] == "sources" and words[0] in SECTIONS else ""
            continue
        if kind and line.startswith("|"):
            first = line.strip().strip("|").split("|")[0]
            if first.strip().strip("`").strip().lower() == SOURCE_ID:
                return kind
    return None


def run(root: Path) -> int:
    registry = root / REGISTRY
    if not registry.is_file():
        print(f"{TAG} {REGISTRY.as_posix()} not found — nothing to check")
        return 0
    where = section_of(read_text_utf8(registry))
    if where in ("active", "reserved"):
        print(f"{TAG} the {SOURCE_ID} source is registered")
        return 0
    if where == "deprecated":
        print(f"{TAG} the {SOURCE_ID} source is under Deprecated Sources — left as the owner set it")
        return 0
    print(
        f"{TAG} The `{SOURCE_ID}` source is not registered on this base.\n"
        f"Agent running /minder:mem:update — after the update finishes, run in this session:\n"
        f"  {COMMAND}\n"
        f"It registers the inbox folder /minder:mem:resolve-clarifications files approved knowledge\n"
        f"into; /minder:mem:process then picks that up like any source. Until it exists, resolving\n"
        f"files the knowledge into a clarification instead. This check runs again on every\n"
        f"update until the source is registered.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", required=True, type=Path)
    args = parser.parse_args(argv)
    return run(args.repo_root.resolve())


if __name__ == "__main__":
    sys.exit(main())
