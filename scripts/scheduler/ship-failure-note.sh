#!/usr/bin/env bash
# Append a one-line failure note to CLARIFICATIONS.md and ship it via
# scripts/scheduler/finalize-tick.sh so the owner sees what went wrong on
# the next interactive resolve session.
#
# Idempotent: ensures the `### Scheduler failures` section exists before
# appending. printf uses `--` end-of-options guard because the appended
# bullet starts with `-` (a leading dash is otherwise parsed as a flag —
# observed failure 2026-05-07T01:06Z).
#
# Local-only fallback. If finalize-tick.sh refuses to commit (e.g. owner
# has non-scheduled commits ahead of origin/main blocking the fold path),
# the note would otherwise vanish into the dirty working tree and remain
# invisible for weeks. To prevent silent note loss, this script falls back
# to a LOCAL commit (no push) tagged `scheduler/failure-local`. The note
# lands in local history; the owner picks it up on their next interactive
# session and `/minder:mem:save` ships it then. Local fallback never force-pushes
# and never amends history.
#
# Usage:
#   bash scripts/scheduler/ship-failure-note.sh "<cause>" <tick-name>
#
# Example:
#   bash scripts/scheduler/ship-failure-note.sh \
#     "lock-check failed: .lint.lock recent" lint-nightly
#
# Exit codes:
#   0 — note appended and shipped (or appended locally as fallback)
#   1 — bad invocation
#   2 — note appended but neither remote nor local commit succeeded
#       (CLARIFICATIONS edit remains in dirty working tree — surfaced to
#       stderr so the parent prompt sees the failure)

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $0 \"<cause>\" <tick-name>" >&2
  exit 1
fi

CAUSE="$1"
TICK="$2"
# The base name is the owner's choice, not a constant — `roles_config`
# discovers it precisely because of that. Deriving it here too is what keeps
# this script from reporting "clear" while a lock sits in a renamed base.
BASE_NAME=""
for d in */; do
    [ -f "$d/_system/scripts/roles_run.py" ] || continue
    [ -n "$BASE_NAME" ] && BASE_NAME="" && break
    BASE_NAME="${d%/}"
done
[ -z "$BASE_NAME" ] && BASE_NAME="zettelkasten"
CLAR="$BASE_NAME/_system/state/CLARIFICATIONS.md"
TS="$(date -u +%Y-%m-%dT%H:%MZ)"

mkdir -p "$(dirname "$CLAR")"
touch "$CLAR"
grep -q '^### Scheduler failures$' "$CLAR" || printf '\n### Scheduler failures\n' >> "$CLAR"
printf -- '- %s scheduler-%s: %s\n' "$TS" "$TICK" "$CAUSE" >> "$CLAR"

if bash scripts/scheduler/finalize-tick.sh "scheduler/failure" "$TICK failed: $CAUSE"; then
  exit 0
fi

echo "ship-failure-note: finalize-tick refused (owner manual work ahead?); falling back to local-only commit" >&2

# Local-only path. Stage just the CLARIFICATIONS edit, commit locally, do
# not push. Owner's next `/minder:mem:save` (or the next scheduler tick once
# their non-scheduled commits are pushed) ships this commit naturally.
if ! git add -- "$CLAR" 2>/dev/null; then
  echo "ship-failure-note: failed to stage CLARIFICATIONS for local fallback" >&2
  exit 2
fi

if git diff --cached --quiet -- "$CLAR"; then
  echo "ship-failure-note: nothing to commit locally (CLARIFICATIONS unchanged in index)" >&2
  exit 2
fi

if ! git commit -m "scheduler/failure-local: $TICK failed: $CAUSE [scheduled]" >/dev/null; then
  echo "ship-failure-note: local commit failed; CLARIFICATIONS note remains in dirty working tree" >&2
  exit 2
fi

echo "ship-failure-note: committed locally (no push) — $(git rev-parse --short HEAD)"
exit 0
