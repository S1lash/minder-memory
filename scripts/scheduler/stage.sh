#!/usr/bin/env bash
# Stage owner-data changes for the current scheduler tick — DOES NOT commit
# or push. The single point that produces a commit is finalize-tick.sh, run
# once at the tail of the scheduler prompt.
#
# Engine paths are NEVER staged. The engine boundary is derived from
# `.engine-manifest.yml` (single source of truth) via the companion helper
# `_classify_paths.py`. If dirty engine paths are detected, an explanatory
# note is appended to CLARIFICATIONS.md (which is itself owner data and
# gets staged) and engine paths are left dirty in the working tree.
#
# A tick may additionally HOLD BACK owner-data paths it has deliberately
# left dirty, by writing them one per line (UTF-8, LF, repo-relative) to
# `.scheduler-state/hold-back` before calling this script. A held-back path
# is skipped and noted the same way engine drift is. Two cases it exists for,
# both from `/minder:mem:roles`, both the same shape — a path the guard deliberately
# left dirty, against a script whose default is to stage every dirty owner
# path:
#   1. a file a role wrote a credential into that the guard could not restore
#      — committing it would put a live secret in history;
#   2. anything a role wrote outside its zone when the check ABORTED
#      (`git_surface` / `unsettled` / `head_moved`), because an abort mutates
#      nothing by design — so without the list, the tick's refusal to touch
#      those paths would end with this script committing and pushing them.
# A hold-back list is consumed once, then removed, so it can never silently
# suppress a later tick's staging.
#
# Idempotent: re-running with no new changes is a no-op. Safe to call
# multiple times within a tick — finalize-tick.sh collapses everything
# into one commit regardless.
#
# Usage:
#   bash scripts/scheduler/stage.sh
#
# Exit codes:
#   0 — staged (or nothing to stage)
#   2 — git operation failed (see stderr)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/../lib/git.sh"
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
HOLD_BACK_FILE=".scheduler-state/hold-back"
TS="$(date -u +%Y-%m-%dT%H:%MZ)"

# `git_status_paths` (scripts/lib/git.sh) owns the two settings this script
# cannot work without — `core.quotepath=false` so a Cyrillic filename is not
# octal-escaped into a string `git add` rejects, and `-uall` so a wholly-new
# directory is listed as its files rather than collapsed into one entry ending
# in `/`. Under the collapsed form both filters below break silently: an engine
# path inside a new directory would be classified by the directory's label, and
# a held-back path inside one could not be excluded at all.
#
# `set -e` aborts on a failing pipeline before a following `$?` test can run, so
# the check has to be part of the assignment itself or the diagnostic is lost and
# the caller sees a bare non-zero exit the header does not document.
if ! CLASSIFIED="$(git_status_paths | python3 "$SCRIPT_DIR/_classify_paths.py")"; then
  echo "stage: path classifier failed" >&2
  exit 2
fi

# Hold-back list: paths a tick deliberately left dirty. Read before
# classification so a held-back path never reaches the index, and consumed
# (removed) here so it cannot suppress a later tick's staging.
HOLD_BACK=""
if [ -f "$HOLD_BACK_FILE" ]; then
  HOLD_BACK="$(cat "$HOLD_BACK_FILE")"
  rm -f "$HOLD_BACK_FILE"
fi

is_held_back() {
  [ -n "$HOLD_BACK" ] || return 1
  while IFS= read -r held; do
    [ -z "$held" ] && continue
    [ "$held" = "$1" ] && return 0
  done <<< "$HOLD_BACK"
  return 1
}

declare -a ENGINE_DIRTY=()
declare -a OWNER_DIRTY=()
declare -a HELD_BACK_SEEN=()
while IFS=$'\t' read -r label path; do
  [ -z "${path:-}" ] && continue
  if is_held_back "$path"; then
    HELD_BACK_SEEN+=("$path")
  elif [ "$label" = "ENGINE" ]; then
    ENGINE_DIRTY+=("$path")
  else
    OWNER_DIRTY+=("$path")
  fi
done <<< "$CLASSIFIED"

if [ ${#HELD_BACK_SEEN[@]} -gt 0 ]; then
  mkdir -p "$(dirname "$CLAR")"
  touch "$CLAR"
  grep -q '^### Scheduler failures$' "$CLAR" || printf '\n### Scheduler failures\n' >> "$CLAR"
  printf -- '- %s scheduler-stage: held back from auto-commit at the tick'"'"'s request: %s\n' \
    "$TS" "${HELD_BACK_SEEN[*]}" >> "$CLAR"
  case " ${OWNER_DIRTY[*]:-} " in
    *" $CLAR "*) ;;
    *) OWNER_DIRTY+=("$CLAR") ;;
  esac
fi

if [ ${#ENGINE_DIRTY[@]} -gt 0 ]; then
  mkdir -p "$(dirname "$CLAR")"
  touch "$CLAR"
  grep -q '^### Scheduler failures$' "$CLAR" || printf '\n### Scheduler failures\n' >> "$CLAR"
  printf -- '- %s scheduler-stage: engine drift skipped from auto-commit: %s\n' \
    "$TS" "${ENGINE_DIRTY[*]}" >> "$CLAR"
  case " ${OWNER_DIRTY[*]:-} " in
    *" $CLAR "*) ;;
    *) OWNER_DIRTY+=("$CLAR") ;;
  esac
fi

if [ ${#OWNER_DIRTY[@]} -eq 0 ]; then
  echo "stage: nothing to stage"
  exit 0
fi

# A path listed by `git status` can be gone by the time `git add` runs — a
# concurrent skill removing a temp file, a guard reverting an untracked write.
# `git add` then fails on that pathspec and takes the WHOLE staging with it,
# so the tick loses its commit over one vanished file. Drop an untracked path
# that no longer exists; keep a tracked one, because there `git add` is how a
# deletion gets staged.
declare -a STAGEABLE=()
for path in "${OWNER_DIRTY[@]}"; do
  if [ -e "$path" ] || git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
    STAGEABLE+=("$path")
  else
    echo "stage: skipping vanished untracked path: $path" >&2
  fi
done

if [ ${#STAGEABLE[@]} -eq 0 ]; then
  echo "stage: nothing to stage"
  exit 0
fi

git add -- "${STAGEABLE[@]}" || exit 2

# Defence-in-depth: re-classify what actually landed in the index. The
# manifest is authoritative; this catches index races where a stat-only
# refresh might let an engine path slip through.
INDEX_CLASSIFIED="$(git_staged_paths | python3 "$SCRIPT_DIR/_classify_paths.py")"
STAGED_ENGINE=()
while IFS=$'\t' read -r label path; do
  [ -z "${path:-}" ] && continue
  [ "$label" = "ENGINE" ] && STAGED_ENGINE+=("$path")
done <<< "$INDEX_CLASSIFIED"
if [ ${#STAGED_ENGINE[@]} -gt 0 ]; then
  echo "stage: aborting — engine path landed in stage despite filter:" >&2
  printf '  %s\n' "${STAGED_ENGINE[@]}" >&2
  git reset HEAD -- "${STAGED_ENGINE[@]}" >/dev/null 2>&1 || true
  exit 2
fi

echo "stage: staged ${#STAGEABLE[@]} owner-data path(s)"
