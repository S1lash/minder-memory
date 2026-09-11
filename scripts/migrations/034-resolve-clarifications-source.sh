#!/usr/bin/env bash
# migration-kind: heal
# 034-resolve-clarifications-source — make sure the resolve-clarifications source is registered.
#
# /minder:mem:resolve-clarifications files the knowledge an owner states while
# answering into `_sources/inbox/resolve-clarifications/`; /minder:mem:process reads
# only the folders the registry lists. New clones get the row from the template.
# On an existing clone this checks for it and, when it is missing, asks the agent
# running /minder:mem:update to register it with /minder:mem:source-add — the skill that
# owns the registry. It never writes the registry itself.
#
# `heal`, and non-zero on purpose while the source is missing: exit 0 would record
# `applied` and the check would never come back. `partial` makes the runner retry
# it on every update until the source exists; a row the owner moved to Deprecated
# Sources ends it. Nothing reads or writes the wrong place meanwhile — resolving
# files the knowledge into a clarification until the folder is registered.
#
# The check is `_034_resolve_clarifications_source.py`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 "$SCRIPT_DIR/_034_resolve_clarifications_source.py" --repo-root "$REPO_ROOT" "$@"
