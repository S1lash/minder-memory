#!/usr/bin/env bash
# migration-kind: heal
# 035-recover-reverted-tick-content — give back what a stale scheduler delivery took.
#
# A scheduler tick that ran long folded its commits onto an `origin/main` that
# had moved while it worked, so its single commit reinstated the tick's own
# starting snapshot on top of everything that arrived in between — deleting
# records, notes and unprocessed sources, and rolling back the state files that
# would have said so. The push was a fast-forward, so nothing refused it, and
# because the log entries were reverted in the same commit as the work they
# describe, no content scan can see it afterwards: what is missing is an event,
# not a file. On a clone whose routines ran unattended this repeats nightly.
#
# This migration repairs it, on this clone, from this clone's own history — which
# is the one place the content still exists. The repair is deterministic, additive
# and reversible with a single `git` step; the engine caused the damage, so
# returning it is not a judgment call. What IS a judgment call — a file both sides
# changed in a way no rule resolves — is never guessed: it becomes an assignment
# the agent running `/minder:mem:update` finishes in place, with this base's own
# rules loaded, and only then a clarification if even that cannot settle it.
#
# Writing is gated on a proof, not on a resemblance. An intentional revert leaves
# the same "a path went back to an older version" trace, so the automatic arm
# requires all three of: scheduler provenance, a tree equal to an ancestor's
# everywhere the commit wrote nothing, and the commit's own work sitting on top —
# the last of which a revert cannot have. Everything else is reported and left
# alone.
#
# `heal`: a clone where this never ran holds stale data, not a wrong place, and a
# repair of history must never be able to block a future engine update. It exits
# non-zero while anything is still outstanding, which is what brings it back on
# the next update.
#
# Once it has nothing left to do it is recorded `applied` and never runs again.
# That is deliberate, and it is why the standing watch lives elsewhere:
# `/minder:mem:lint` A.15 raises `scheduler-tick-reverted-content` for anything
# that happens after this migration retires.
#
# Opt out with `MINDER_MEMORY_NO_AUTO_RECOVER=1` — it then only reports.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 "$SCRIPT_DIR/_035_recover_reverted_ticks.py" --repo-root "$REPO_ROOT" "$@"
