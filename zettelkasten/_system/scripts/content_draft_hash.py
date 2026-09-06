#!/usr/bin/env python3
"""Deterministic content hash of a draft body — the owner-edit guard for
`/minder:mem:content --maintain`.

The draft-maintainer stores `last_auto_hash` in the content ledger after every
write. On the next run it recomputes this hash for each `auto` draft; if it
differs, the owner edited the draft → the maintainer flips it to `owner-editing`
and only flags thereafter (never rewrites). Computing the hash in a tested,
deterministic helper (rather than asking the LLM to hash) is what makes the guard
reliable: same body → same hash, every time, on every machine.

Normalization (so trivial trailing-whitespace / final-newline differences do NOT
look like an owner edit): take the body BELOW the frontmatter, rstrip each line,
join with "\\n", strip the whole. Hash with sha256.

Usage:
    python3 content_draft_hash.py <draft-path>      # prints the hex digest
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

from _common import configure_std_streams  # type: ignore

_FM_SPLIT_RE = re.compile(r"^---\n.*?\n---\n(.*)$", re.DOTALL)


def draft_body(text: str) -> str:
    """Return the body below the frontmatter (or the whole text if none)."""
    m = _FM_SPLIT_RE.match(text)
    return m.group(1) if m else text


def normalize(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.splitlines()).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(draft_body(text)).encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    return content_hash(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        sys.stderr.write("usage: content_draft_hash.py <draft-path>\n")
        return 2
    sys.stdout.write(hash_file(Path(args[0])) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
