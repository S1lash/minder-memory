#!/usr/bin/env bash
# Check the cross-skill pipeline locks before a scheduler tick acquires
# its own lock via the skill body. Stale locks (>2h) are removed; recent
# locks abort the tick.
#
# Lock matrix mirrored from zettelkasten/_system/docs/SYSTEM_CONFIG.md
# §«Cross-skill lock contract». All pipeline locks live under
# `_sources/.{name}.lock` (the inbox dir doubles as the lock home for
# every pipeline skill — process / maintain / lint / agent-lens / content /
# roles — plus the resolve session). Each skill reads them all at Step 0 and aborts
# on any present. `.content.lock` matters because `/minder:mem:content --maintain`
# reads CONTENT_MAP.md while `/minder:mem:maintain` (Step 7.8) rewrites it.
#
# Usage:
#   bash scripts/scheduler/lock-check.sh
#
# Exit codes:
#   0 — no recent lock found (safe to proceed)
#   1 — at least one lock is recent; lock names printed to stderr

set -euo pipefail

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
LOCK_DIR="$BASE_NAME/_sources"
NOW_EPOCH="$(date +%s)"
STALE_THRESHOLD_SECONDS=$((2 * 60 * 60))  # 2 hours

LOCKS=(
  "$LOCK_DIR/.processing.lock"
  "$LOCK_DIR/.maintain.lock"
  "$LOCK_DIR/.lint.lock"
  "$LOCK_DIR/.agent-lens.lock"
  "$LOCK_DIR/.content.lock"
  "$LOCK_DIR/.roles.lock"
  "$LOCK_DIR/.resolve.lock"
)

BLOCKED=()
for lock in "${LOCKS[@]}"; do
  [ -e "$lock" ] || continue
  # mtime as epoch seconds. Trying the BSD form then the GNU form IS the
  # portable idiom — neither exists on both platforms.
  # portability-ok: deliberate BSD-then-GNU fallback pair
  if mtime="$(stat -f %m "$lock" 2>/dev/null)"; then
    :
  # portability-ok: the GNU half of the pair above
  elif mtime="$(stat -c %Y "$lock" 2>/dev/null)"; then
    :
  else
    echo "lock-check: cannot stat $lock; treating as stale" >&2
    rm -f "$lock"
    continue
  fi
  age=$((NOW_EPOCH - mtime))
  if [ "$age" -gt "$STALE_THRESHOLD_SECONDS" ]; then
    echo "lock-check: stale lock removed ($lock, age=${age}s)"
    rm -f "$lock"
  else
    BLOCKED+=("$lock (age=${age}s)")
  fi
done

if [ ${#BLOCKED[@]} -gt 0 ]; then
  echo "lock-check: recent locks block this tick:" >&2
  printf -- '  - %s\n' "${BLOCKED[@]}" >&2
  exit 1
fi

echo "lock-check: clear"
