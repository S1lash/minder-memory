#!/usr/bin/env bash
# migration-kind: heal
# 033-own-names-after-the-rename — raise what an earlier rename did to your own names.
#
# minder-memory-rebrand: keep-legacy-tokens — this header names the former form on purpose.
#
# A clone that took the 1.0.0 update had its whole tree renamed by a map that
# could not yet tell the product from its owner: `minder-ztn-<your own tail>` —
# your repository, your clone folder, a host of yours — became
# `minder-memory-<tail>`, a path that does not exist. The damaged line reads
# perfectly well, so nothing else flags it; the only witness is what the same
# file said at the commit before the rename migration ran.
#
# This migration RAISES it and rewrites nothing. Whether the directory on this
# machine still carries the old name, was renamed to match, or never existed
# here is not knowable from the repository, and a guess that went the wrong way
# would turn a visible wrong path into an invisible one. So each finding lands
# as one clarification with both texts beside each other, for the owner.
#
# `heal`: a clone where this never ran is unwarned, not broken — and a notice
# must never be able to block a future update. The kind is load-bearing in the
# other direction too. On a FIRST update there is no committed pre-rename state
# to read: the ledger line is written by the run that applies this migration and
# committed afterwards. Exiting 0 there would record `applied` and retire the
# check on every clone before it ever looked, so it exits non-zero, the runner
# records `partial`, and the next update — with the commit behind it — looks for
# real. `partial` is not a failure here; it is the retry this migration needs.
#
# The work is in `_033_own_names.py`; detection is shared with the post-update
# check (`scripts/check_update.py`), so the two can never disagree. Idempotent:
# a second run finds the same paths already in the queue and appends nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 "$SCRIPT_DIR/_033_own_names.py" --repo-root "$REPO_ROOT" "$@"
