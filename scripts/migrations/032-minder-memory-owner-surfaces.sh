#!/usr/bin/env bash
# migration-kind: heal
# 032-minder-memory-owner-surfaces — every file in the clone says Minder Memory.
#
# The engine sync renames what it ships; everything else in a clone — the
# registries and system files seeded from templates, the Obsidian vault config,
# the README, the owner's notes, records and hubs, the append-only state —
# still says the previous product name and still names the old slash
# commands. This migration runs the engine's one rename map over the whole
# clone (`_032_minder_memory_rebrand.py`), the same map the maintainer ran over
# the authoring base: file names and their wikilinks move together, `id:`
# follows the stem, quoted speech keeps its declined forms readable.
#
# `_sources/` is never touched — a transcript is evidence of what was said.
# A product rename is the one owner-data rewrite the engine performs
# (ADR-029): deterministic, idempotent, reversible through git.
#
# `heal`: a clone where this did not run reads and writes the right places;
# a failure is recorded `partial` and retried on the next update.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ ! -d "$REPO_ROOT/zettelkasten/_system" ]; then
  echo "032: $REPO_ROOT/zettelkasten is not a Minder Memory base (no _system/) — nothing to rename; will retry next update" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/_032_minder_memory_rebrand.py" --root "$REPO_ROOT"
