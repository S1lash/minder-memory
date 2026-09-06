#!/usr/bin/env bash
# The single point that produces a commit + push for a scheduler tick.
# Run once at the tail of every integrations/claude-code/scheduler-prompts/*.md
# tick AFTER the skill body finishes.
#
# Two delivery modes — auto-detected from `.scheduler-state/start-branch`
# (written by pin-main.sh):
#
#   1. LOCAL mode (start branch = `main`, absent, or the `DETACHED` sentinel).
#      The runner has direct push rights to `origin/main`. Single
#      `git push origin main`. Used for local cron / launchd schedulers
#      where the working tree persists between ticks.
#
#   2. ROUTINES mode (start branch = `claude/<random>` or any non-main).
#      Cloud Routines' git proxy refuses push to `main` but accepts push
#      to the sandbox branch. The delivery path is:
#        a. push HEAD to the sandbox branch (proxy-allowed)
#        b. `gh pr create --base main --head <sandbox>`
#        c. `gh pr merge --squash --delete-branch`
#      End state: `main` updated with one squash commit; sandbox branch
#      deleted on origin. The Routines sandbox is ephemeral, so local
#      state after this step does not matter.
#
# Pipeline (both modes):
#   1. Recover from previous partial tick: if local main is ahead of
#      origin/main on commits whose subject contains `[scheduled]`, undo
#      them with `git reset --soft origin/main` so their content folds
#      back into the staging area and gets collapsed into THIS tick's
#      single commit. Owner manual commits (no `[scheduled]` suffix) are
#      preserved untouched — refuse to touch them.
#   2. Stage owner-data (calls stage.sh — idempotent if scheduler already
#      called stage.sh between steps).
#   3. Derive a heuristic commit message from the staged paths.
#   4. Single `git commit`.
#   5. Mode-specific delivery (direct push OR push-to-sandbox + PR-merge).
#
# Audit-trail note on recovery. When previous-tick [scheduled] commits
# are folded into this commit, their subjects are LOST (only the new
# heuristic subject lands in git history). Detailed per-pipeline audit
# trails are independently maintained by the producer skills in append-
# only logs under `_system/state/log_*.md`.
#
# Usage:
#   bash scripts/scheduler/finalize-tick.sh <tag> [override-message]
#
# Arguments:
#   <tag>              — required, prepended as `<tag>: ` (e.g.
#                        `scheduler/process`, `scheduler/lint`,
#                        `scheduler/agent-lens`, `scheduler/failure`)
#   [override-message] — optional, replaces the heuristic body
#
# Final commit subject shape:
#   <tag>: <message-body> [scheduled]
#
# Exit codes:
#   0 — committed + delivered (or no-op: nothing to commit)
#   2 — git or gh operation failed (see stderr)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/../lib/git.sh"

if [ $# -lt 1 ]; then
  echo "usage: $0 <tag> [override-message]" >&2
  exit 2
fi

TAG="$1"
OVERRIDE_MSG="${2:-}"

git fetch origin main --quiet 2>/dev/null || true

AUTHORED_SHAS_FILE=".scheduler-state/authored-shas"
AUTHORED=""
[ -f "$AUTHORED_SHAS_FILE" ] && AUTHORED="$(cat "$AUTHORED_SHAS_FILE")"

# A commit an earlier tick explicitly DISOWNED is never folded, by any tick,
# whatever its subject says. Without this the refusal was single-tick only:
# `/minder:mem:roles` correctly refuses to deliver a commit it did not author and
# exits partial, leaving it in the local repo — and the next tick in the
# nightly chain (lint at 05:00) runs this script with no authored list of its
# own, falls through to subject matching, sees `[scheduled]`, and folds the
# forged commit into its own push. The identity check would then have moved
# the laundering by one tick rather than preventing it.
DISOWNED_SHAS_FILE=".scheduler-state/disowned-shas"
if [ -f "$DISOWNED_SHAS_FILE" ]; then
  DISOWNED_HIT=""
  # `|| [ -n "$dsha" ]` is load-bearing, not defensive noise: `read` returns
  # non-zero on the LAST line when the file has no trailing newline, so a
  # plain `while read` silently drops it. This refusal must fail CLOSED, and a
  # file written by hand — which is exactly what its own recovery instruction
  # tells the owner to do — is the likeliest one to lack that newline.
  while IFS= read -r dsha || [ -n "$dsha" ]; do
    [ -z "$dsha" ] && continue
    if git rev-list origin/main..HEAD 2>/dev/null | grep -qx "$dsha"; then
      DISOWNED_HIT="$dsha"
      break
    fi
  done < "$DISOWNED_SHAS_FILE"
  if [ -n "$DISOWNED_HIT" ]; then
    echo "finalize-tick: refusing to deliver — commit $DISOWNED_HIT was disowned by an earlier tick" >&2
    echo "  It is ahead of origin/main and no tick claims authorship of it." >&2
    echo "  Nothing is rewritten here, and NO pipeline can deliver while this" >&2
    echo "  line stands — every tick reads this list, not just roles." >&2
    echo "  Inspect the commit, then clear it:" >&2
    echo "" >&2
    echo "      git show $DISOWNED_HIT" >&2
    echo "      grep -v $DISOWNED_HIT $DISOWNED_SHAS_FILE > /tmp/ds && mv /tmp/ds $DISOWNED_SHAS_FILE" >&2
    exit 2
  fi
fi

AHEAD_COUNT="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"
if [ "$AHEAD_COUNT" -gt 0 ]; then
  NON_SCHEDULED=0
  declare -a UNLISTED=()
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    sha="${line%% *}"
    subject="${line#* }"
    if [ -n "$AUTHORED" ]; then
      # A tick declared authorship: identity decides, not wording. A role has
      # a shell, so "[scheduled]" in a subject proves nothing.
      printf '%s\n' "$AUTHORED" | grep -qx "$sha" && continue
      UNLISTED+=("$sha ${subject}")
    else
      case "$subject" in
        *"[scheduled]"*) ;;
        *) NON_SCHEDULED=$((NON_SCHEDULED + 1)) ;;
      esac
    fi
  done < <(git log --format='%H %s' origin/main..HEAD 2>/dev/null)

  if [ ${#UNLISTED[@]} -gt 0 ]; then
    echo "finalize-tick: refusing to reset — ${#UNLISTED[@]} commit(s) ahead of origin/main this tick did not author" >&2
    printf '  %s\n' "${UNLISTED[@]}" >&2
    echo "finalize-tick: a [scheduled] subject is not authorship; aborting to preserve history" >&2
    exit 2
  fi

  if [ "$NON_SCHEDULED" -gt 0 ]; then
    echo "finalize-tick: refusing to reset — $NON_SCHEDULED non-scheduled commit(s) ahead of origin/main" >&2
    echo "finalize-tick: owner manual work present; aborting to preserve history" >&2
    exit 2
  fi

  echo "finalize-tick: folding $AHEAD_COUNT previous unpushed [scheduled] commit(s) into this tick"
  git reset --soft origin/main || exit 2
fi

bash "$SCRIPT_DIR/stage.sh" || exit 2

if git diff --cached --quiet; then
  echo "finalize-tick: nothing to commit"
  exit 0
fi

declare -a STAGED=()
while IFS= read -r p; do
  [ -z "$p" ] && continue
  STAGED+=("$p")
done < <(git_staged_paths)

categorize() {
  local p="$1"
  case "$p" in
    zettelkasten/_records/*) echo records ;;
    zettelkasten/_sources/inbox/*) echo sources-inbox ;;
    zettelkasten/_sources/processed/*) echo sources-processed ;;
    zettelkasten/_sources/*) echo sources ;;
    zettelkasten/0_constitution/axiom/*|zettelkasten/0_constitution/principle/*|zettelkasten/0_constitution/rule/*) echo constitution ;;
    zettelkasten/1_projects/*|zettelkasten/2_areas/*|zettelkasten/3_resources/*|zettelkasten/4_archive/*|zettelkasten/6_posts/*) echo knowledge ;;
    zettelkasten/5_meta/mocs/*) echo hubs ;;
    zettelkasten/_system/state/*) echo state ;;
    zettelkasten/_system/views/*) echo views ;;
    zettelkasten/_system/SOUL.md|zettelkasten/_system/TASKS.md|zettelkasten/_system/CALENDAR.md|zettelkasten/_system/POSTS.md) echo system-data ;;
    zettelkasten/_system/registries/*) echo system-data ;;
    *) echo other ;;
  esac
}

count_for() {
  local target="$1" n=0 p
  for p in "${STAGED[@]}"; do
    [ "$(categorize "$p")" = "$target" ] && n=$((n + 1))
  done
  echo "$n"
}

uniq_cats="$(for p in "${STAGED[@]}"; do categorize "$p"; done | sort -u)"
N_CATS="$(printf '%s\n' "$uniq_cats" | grep -c .)"
TOTAL=${#STAGED[@]}

heuristic_message() {
  if [ "$N_CATS" -eq 1 ]; then
    local only_cat="$uniq_cats"
    local n
    n="$(count_for "$only_cat")"
    case "$only_cat" in
      records) echo "$n record(s) updated" ;;
      sources-inbox) echo "inbox: $n file(s) updated" ;;
      sources-processed) echo "sources: $n file(s) moved to processed" ;;
      sources) echo "sources: $n file(s) updated" ;;
      constitution) echo "constitution: $n principle(s) edited" ;;
      knowledge) echo "knowledge: $n note(s) edited" ;;
      hubs) echo "hubs: $n updated" ;;
      state) echo "state: routine update ($n file(s))" ;;
      views) echo "views: regenerated ($n file(s))" ;;
      system-data) echo "system: registries / SOUL updated ($n file(s))" ;;
      other) echo "$n file(s) updated" ;;
    esac
    return
  fi

  local n_records
  n_records="$(count_for records)"
  if [ "$n_records" -gt 0 ]; then
    echo "process batch: $n_records record(s), $((TOTAL - n_records)) supporting file(s)"
    return
  fi

  echo "routine save: $TOTAL file(s) across $N_CATS area(s)"
}

if [ -n "$OVERRIDE_MSG" ]; then
  BODY="$OVERRIDE_MSG"
else
  BODY="$(heuristic_message)"
fi

case "$BODY" in
  "$TAG:"*) MESSAGE="$BODY [scheduled]" ;;
  *) MESSAGE="$TAG: $BODY [scheduled]" ;;
esac

git commit -m "$MESSAGE" || exit 2

# This commit is scheduler-authored too: record it, so a delivery failure
# leaves it foldable by the next tick under the same identity rule.
if [ -n "$AUTHORED" ]; then
  mkdir -p "$(dirname "$AUTHORED_SHAS_FILE")"
  git rev-parse HEAD >> "$AUTHORED_SHAS_FILE"
fi
LOCAL_SHA="$(git rev-parse --short HEAD)"
echo "finalize-tick: committed $LOCAL_SHA — $MESSAGE"

START_BRANCH=""
if [ -f .scheduler-state/start-branch ]; then
  START_BRANCH="$(cat .scheduler-state/start-branch 2>/dev/null || true)"
fi

# LOCAL mode covers everything that is not a real sandbox branch: `main`, an
# absent state file, and the `DETACHED` sentinel. `git_is_branch_name` also
# rejects the literal `HEAD` — a value a pre-fix `pin-main.sh` could persist —
# so a stale state file can never route a tick into ROUTINES mode and make it
# push to a remote branch called `HEAD`.
if ! git_is_branch_name "$START_BRANCH" || [ "$START_BRANCH" = "main" ]; then
  echo "finalize-tick: LOCAL mode (start branch '$START_BRANCH') — direct push to origin/main"
  git push origin main || exit 2
  rm -f "$AUTHORED_SHAS_FILE"
  echo "finalize-tick: delivered to origin/main"
  exit 0
fi

# ROUTINES mode — push to sandbox branch + gh PR + squash merge + delete.
echo "finalize-tick: ROUTINES mode (sandbox branch '$START_BRANCH') — push + PR + squash-merge"

if ! command -v gh >/dev/null 2>&1; then
  echo "finalize-tick: gh CLI not found in PATH; cannot complete Routines-mode delivery" >&2
  echo "finalize-tick: local commit $LOCAL_SHA persists; install gh or push manually" >&2
  exit 2
fi

if ! git push origin "HEAD:$START_BRANCH" 2>&1; then
  echo "finalize-tick: push to sandbox branch '$START_BRANCH' failed" >&2
  echo "finalize-tick: if non-fast-forward, the platform put commits on the sandbox branch unexpectedly" >&2
  exit 2
fi
echo "finalize-tick: pushed $LOCAL_SHA to origin/$START_BRANCH"

PR_BODY="Autonomous scheduler tick. Tag: \`$TAG\`. Generated by finalize-tick.sh. Squash-merge expected."

# Reuse an existing PR if one is already open against this branch; otherwise create.
PR_NUMBER="$(gh pr list --head "$START_BRANCH" --base main --state open --json number --jq '.[0].number' 2>/dev/null || true)"
if [ -z "$PR_NUMBER" ] || [ "$PR_NUMBER" = "null" ]; then
  if ! gh pr create --base main --head "$START_BRANCH" --title "$MESSAGE" --body "$PR_BODY" >/dev/null 2>&1; then
    echo "finalize-tick: gh pr create failed for $START_BRANCH" >&2
    exit 2
  fi
  PR_NUMBER="$(gh pr list --head "$START_BRANCH" --base main --state open --json number --jq '.[0].number' 2>/dev/null || true)"
fi

if [ -z "$PR_NUMBER" ] || [ "$PR_NUMBER" = "null" ]; then
  echo "finalize-tick: could not resolve PR number after creation" >&2
  exit 2
fi
echo "finalize-tick: PR #$PR_NUMBER ready for squash-merge"

set +e
MERGE_OUT="$(gh pr merge "$PR_NUMBER" --squash --delete-branch --subject "$MESSAGE" --body "" 2>&1)"
MERGE_RC=$?
set -e
if [ "$MERGE_RC" -eq 0 ]; then
  rm -f "$AUTHORED_SHAS_FILE"
  echo "finalize-tick: PR #$PR_NUMBER squash-merged into main; sandbox branch deleted"
  exit 0
fi

# Merge may have succeeded but branch deletion failed (platform retains active session ref).
# Treat as soft success in that case.
STATE="$(gh pr view "$PR_NUMBER" --json state --jq .state 2>/dev/null || echo UNKNOWN)"
if [ "$STATE" = "MERGED" ]; then
  rm -f "$AUTHORED_SHAS_FILE"
  echo "finalize-tick: PR #$PR_NUMBER merged but sandbox-branch delete failed; next-tick recovery will clean up"
  echo "$MERGE_OUT" >&2
  exit 0
fi

echo "finalize-tick: gh pr merge failed (state=$STATE)" >&2
echo "$MERGE_OUT" >&2
exit 2
