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
#        b. open a PR <sandbox> → main (`gh api`, REST)
#        c. squash-merge it and delete the sandbox branch (`gh api`, REST)
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

# `--resolve-by-main` is the last resort for a conflict the tick could not
# resolve itself: each still-conflicted file takes main's version, the rest of
# the tick is delivered, and the file is named in CLARIFICATIONS. Only the
# closing guard passes it, after the tick had its chance (Step 5c).
RESOLVE_BY_MAIN=0
# `--checkpoint` marks the commit as the first of a tick's two deliveries
# (process, before maintain). The mark is in the subject because that is what
# survives a squash onto main, and `/minder:mem:lint` A.13 reads it: a
# checkpoint carries no telemetry line by design — the tick is measured once,
# at its final close.
CHECKPOINT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --resolve-by-main) RESOLVE_BY_MAIN=1; shift ;;
    --checkpoint) CHECKPOINT=1; shift ;;
    *) break ;;
  esac
done
ORIG_ARGS=("$@")

if [ $# -lt 1 ]; then
  echo "usage: $0 [--resolve-by-main] <tag> [override-message]" >&2
  exit 2
fi

TAG="$1"
OVERRIDE_MSG="${2:-}"

STATE_DIR=".scheduler-state"
CONFLICT_FILE="$STATE_DIR/conflict"
SNAPSHOT_FILE="$STATE_DIR/conflict-snapshot.json"
MESSAGE_FILE="$STATE_DIR/tick-message"

# A network blip or a GitHub hiccup is not a reason to lose a run. Every call
# that leaves this machine gets three tries with a growing pause; what still
# fails after that is a real failure and is reported as one.
retry() {
  local n=0
  until "$@"; do
    n=$((n + 1))
    if [ "$n" -ge 3 ]; then
      return 1
    fi
    sleep $((n * 3))
  done
}

retry git fetch origin main --quiet 2>/dev/null || true

AUTHORED_SHAS_FILE=".scheduler-state/authored-shas"
AUTHORED=""
[ -f "$AUTHORED_SHAS_FILE" ] && AUTHORED="$(cat "$AUTHORED_SHAS_FILE")"

# RESUME: an earlier call stopped on a conflict the tick has now resolved (or
# the guard asks for the last resort). The commit already exists and the merge
# is open; building another commit here would fold the merge itself.
RESUME=0
if [ -f "$CONFLICT_FILE" ] && git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
  RESUME=1
elif [ -f "$CONFLICT_FILE" ]; then
  rm -f "$CONFLICT_FILE"
fi

if [ "$RESUME" -eq 0 ]; then

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

# A deletion a step staged itself with `git rm` is neither on disk nor in the
# index, so stage.sh — which reads the working tree — cannot see it as work and
# never records it, and the rail below then refuses the whole tick over the one
# change it did make. It is recorded here, against HEAD and BEFORE the fold:
# relative to the tick's own commits, a pending index deletion can only be this
# tick's. After the fold the same question would also answer "yes" for every
# deletion inside the folded commits — exactly what the rail exists to judge on
# content, so it must never be asked there.
PENDING_DELETIONS="$(git -c core.quotepath=false diff --cached --diff-filter=D --name-only HEAD 2>/dev/null || true)"
if [ -n "$PENDING_DELETIONS" ]; then
  mkdir -p .scheduler-state
  printf '%s\n' "$PENDING_DELETIONS" >> .scheduler-state/staged-paths
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
  # The fold collapses THIS TICK's commits into one, so it resets to the point
  # those commits branched from — never to `origin/main`. Resetting to a tip that
  # moved while the tick ran keeps the stale index and commits it on top of
  # everything that arrived, which reverts it: a fast-forward push that git has
  # no reason to refuse. Six deliveries erased a day of records each that way.
  FORK_POINT="$(git merge-base HEAD origin/main 2>/dev/null || true)"
  if [ -z "$FORK_POINT" ]; then
    echo "finalize-tick: cannot determine the fork point with origin/main; aborting" >&2
    exit 2
  fi
  # The surface is NOT read from the folded commits. Adding their paths here
  # launders the one case the check exists for: when the stale tree is inside the
  # tick's own commit, "paths my commits contain" authorises exactly what should
  # have been refused. Every step that commits records what it staged — stage.sh
  # here, and the roles skill for its per-role commits — so the surface comes
  # from the record, never from the artifact under suspicion.
  git reset --soft "$FORK_POINT" || exit 2
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

# One line, always. The body is free text from the caller, and a newline in it
# would split the subject into paragraphs a reader of the run identity could be
# made to parse (`scripts/lib/tick_identity.py`).
BODY="$(printf '%s' "$BODY" | tr '\r\n' '  ')"

if [ "$CHECKPOINT" -eq 1 ]; then
  BODY="checkpoint — $BODY"
fi

case "$BODY" in
  "$TAG:"*) MESSAGE="$BODY [scheduled]" ;;
  *) MESSAGE="$TAG: $BODY [scheduled]" ;;
esac

# The identity this delivery declares: the base its tree was built on, and the run
# (`scripts/lib/tick_identity.py` owns the keys and says why the base decides).
# Computed here, before integration, where `HEAD` is still the commit the tick
# worked from — never read from `.scheduler-state`, which outlives runs and would
# hand back yesterday's base.
# Writing it can never fail the delivery: a commit without an identity falls back
# to the recovery tool's older reasoning, a tick that fails loses its work.
IDENTITY=""
if ! IDENTITY="$(python3 "$SCRIPT_DIR/../lib/tick_identity.py" trailers 2>/dev/null)"; then
  IDENTITY=""
fi
if [ -n "$IDENTITY" ]; then
  git commit -m "$MESSAGE" -m "$IDENTITY" || exit 2
else
  echo "finalize-tick: warning — no run identity could be declared; delivering without it" >&2
  git commit -m "$MESSAGE" || exit 2
fi

# This commit is scheduler-authored too: record it, so a delivery failure
# leaves it foldable by the next tick under the same identity rule.
if [ -n "$AUTHORED" ]; then
  mkdir -p "$(dirname "$AUTHORED_SHAS_FILE")"
  git rev-parse HEAD >> "$AUTHORED_SHAS_FILE"
fi
LOCAL_SHA="$(git rev-parse --short HEAD)"
echo "finalize-tick: committed $LOCAL_SHA — $MESSAGE"

fi  # RESUME -eq 0

LOCAL_SHA="$(git rev-parse --short HEAD)"

# Paths whose conflict was settled by taking main's version — named afterwards.
TAKEN_FROM_MAIN=""

# Collapse a finished merge into ONE commit on top of the target, carrying the
# tick's own message (and with it the identity it declared). The delivery stays
# a single squash-shaped change, exactly as a clean rebase would have made it.
collapse_onto() {
  local target="$1"
  if git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    git commit --no-edit -q >/dev/null 2>&1 || git commit --no-edit -q --allow-empty >/dev/null || return 1
  fi
  git reset --soft "$target" || return 1
  if git diff --cached --quiet; then
    echo "finalize-tick: everything this tick changed is already on origin/main"
    return 0
  fi
  git commit -q -F "$MESSAGE_FILE" || return 1
  if [ -n "$AUTHORED" ]; then
    git rev-parse HEAD >> "$AUTHORED_SHAS_FILE"
  fi
  return 0
}

# Settle each still-conflicted path by main's version: main's content when main
# has the file, its absence when it does not.
take_main() {
  local target="$1"; shift
  local f
  for f in "$@"; do
    if git_ref_has_path "$target" "$f"; then
      MSYS_NO_PATHCONV=1 git checkout "$target" -- "$f" >/dev/null 2>&1 || return 1
      git add -- "$f" || return 1
    else
      git rm -q -f --ignore-unmatch -- "$f" >/dev/null 2>&1 || return 1
    fi
    TAKEN_FROM_MAIN="$TAKEN_FROM_MAIN $f"
  done
  return 0
}

# Stage the tick's resolution of each listed path: an edited file is added, a
# file the tick removed is removed. Prints, one per line, the paths that are
# still open — carrying markers, or exactly as they were when the closing step
# stopped. "Untouched" matters because some conflicts carry no markers at all:
# a binary file, or one deleted on one side and edited on the other, sits in
# the tree as one side's version. Reading "no markers" as "resolved" staged that
# side silently — over main.
stage_resolution() {
  local f open
  open="$(python3 "$SCRIPT_DIR/_resolve_conflicts.py" open "$SNAPSHOT_FILE" "$@")" || return 1
  for f in "$@"; do
    if printf '%s\n' "$open" | grep -qxF -- "$f"; then
      printf '%s\n' "$f"
      continue
    fi
    if [ -e "$f" ]; then
      git add -- "$f" || return 1
    else
      git rm -q --ignore-unmatch -- "$f" >/dev/null 2>&1 || return 1
    fi
  done
}

# Read LF-separated paths from stdin into the array LINES. Paths can contain
# spaces (a person's name in a note title), so word splitting is never used.
read_lines() {
  LINES=()
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    if [ -n "$line" ]; then
      LINES+=("$line")
    fi
  done
  return 0
}

stop_for_resolution() {
  local target="$1"; shift
  {
    printf 'target %s\n' "$target"
    printf '%s\n' "$@"
  } > "$CONFLICT_FILE"
  python3 "$SCRIPT_DIR/_resolve_conflicts.py" snapshot "$SNAPSHOT_FILE" "$@" || true
  python3 "$SCRIPT_DIR/tick_state.py" set --for "$TAG" conflict "$*"
  echo "finalize-tick: CONFLICT — these files changed both here and on main since this tick began:" >&2
  printf '  %s\n' "$@" >&2
  echo "finalize-tick: resolve them (Step 5c), then run the closing step again." >&2
  exit 3
}

# Integration. The commit sits on the fork point, so it is behind a tip that
# moved while the tick ran. Main is merged INTO the tick's commit (three-way,
# so a concurrent change inside a file this tick also touched is kept rather
# than reverted), and the result is collapsed back into one commit on top of
# main. Conflicts are settled in three layers, and none of them loses the run:
#   1. both sides only ADDED lines at the same place → both kept, mechanically
#      (`_resolve_conflicts.py`);
#   2. anything else → the tick resolves it itself (Step 5c) and calls again;
#   3. the guard's last resort (`--resolve-by-main`) → main's version for the
#      files still open, the rest delivered, the files named in CLARIFICATIONS.
# Main can move again while that happens, so this repeats until it holds.
ATTEMPT=0
while :; do
  if [ "$RESUME" -eq 1 ]; then
    TARGET="$(sed -n 's/^target //p' "$CONFLICT_FILE" | head -n 1)"
    read_lines < <(sed -n '2,$p' "$CONFLICT_FILE")
    STILL_OUT=""
    # bash 3.2 (macOS) treats an empty "${a[@]}" as unbound under `set -u`.
    if [ ${#LINES[@]} -gt 0 ]; then
      STILL_OUT="$(stage_resolution "${LINES[@]}")" || exit 2
    fi
    read_lines <<< "$STILL_OUT"
    if [ ${#LINES[@]} -gt 0 ]; then
      if [ "$RESOLVE_BY_MAIN" -eq 1 ]; then
        take_main "$TARGET" "${LINES[@]}" || exit 2
      else
        stop_for_resolution "$TARGET" "${LINES[@]}"
      fi
    fi
    collapse_onto "$TARGET" || { echo "finalize-tick: could not complete the merge" >&2; exit 2; }
    rm -f "$CONFLICT_FILE" "$SNAPSHOT_FILE"
    # Only a record waiting on this conflict goes back to open: a tick that
    # already ended through failure handling stays closed.
    python3 "$SCRIPT_DIR/tick_state.py" resolved --for "$TAG"
    # The same line a first call prints after it commits — Step 5b of the
    # prompts keys on it, and reads the PR title from it.
    echo "finalize-tick: committed $(git rev-parse --short HEAD) — $(git log -1 --format=%s HEAD)"
    RESUME=0
    retry git fetch origin main --quiet 2>/dev/null || true
  fi

  if git merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
    break
  fi
  ATTEMPT=$((ATTEMPT + 1))
  if [ "$ATTEMPT" -gt 3 ]; then
    echo "finalize-tick: main kept moving during integration; nothing pushed" >&2
    exit 2
  fi

  TARGET="$(git rev-parse origin/main)"
  echo "finalize-tick: integrating onto origin/main ($(git rev-parse --short "$TARGET"))"
  mkdir -p "$STATE_DIR"
  git log -1 --format=%B HEAD > "$MESSAGE_FILE"
  if git -c merge.conflictStyle=diff3 merge --no-ff --no-commit "$TARGET" >/dev/null 2>&1; then
    collapse_onto "$TARGET" || { echo "finalize-tick: could not complete the merge" >&2; exit 2; }
    retry git fetch origin main --quiet 2>/dev/null || true
    continue
  fi
  if ! git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    echo "finalize-tick: integration could not start a merge; nothing pushed" >&2
    exit 2
  fi
  OPEN="$(python3 "$SCRIPT_DIR/_resolve_conflicts.py" auto)" || {
    git merge --abort >/dev/null 2>&1 || true
    echo "finalize-tick: could not read the conflicts; nothing pushed" >&2
    exit 2
  }
  read_lines <<< "$OPEN"
  if [ ${#LINES[@]} -gt 0 ]; then
    if [ "$RESOLVE_BY_MAIN" -eq 1 ]; then
      take_main "$TARGET" "${LINES[@]}" || exit 2
    else
      stop_for_resolution "$TARGET" "${LINES[@]}"
    fi
  else
    echo "finalize-tick: overlapping additions kept from both sides"
  fi
  collapse_onto "$TARGET" || { echo "finalize-tick: could not complete the merge" >&2; exit 2; }
  retry git fetch origin main --quiet 2>/dev/null || true
done

# When every change the tick made was settled by main's version, nothing of
# its own is left beyond main — but the drop must still be named, so the note
# becomes a commit of its own rather than an amendment of main's.
NOTE_AS_NEW_COMMIT=0
if git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
  if [ -z "$TAKEN_FROM_MAIN" ]; then
    rm -f "$AUTHORED_SHAS_FILE" ".scheduler-state/staged-paths"
    echo "finalize-tick: nothing new to deliver"
    exit 0
  fi
  NOTE_AS_NEW_COMMIT=1
fi

note_in_clarifications() {
  local base_name="" d clar ts
  for d in */; do
    [ -f "$d/_system/scripts/roles_run.py" ] || continue
    [ -n "$base_name" ] && base_name="" && break
    base_name="${d%/}"
  done
  [ -z "$base_name" ] && base_name="zettelkasten"
  clar="$base_name/_system/state/CLARIFICATIONS.md"
  ts="$(date -u +%Y-%m-%dT%H:%MZ)"
  mkdir -p "$(dirname "$clar")"
  touch "$clar"
  grep -q '^### Scheduler failures$' "$clar" || printf '\n### Scheduler failures\n' >> "$clar"
  printf -- '- %s %s: %s\n' "$ts" "$TAG" "$1" >> "$clar"
  git add -- "$clar"
  mkdir -p "$STATE_DIR"
  printf '%s\n' "$clar" >> .scheduler-state/staged-paths
  if [ "$NOTE_AS_NEW_COMMIT" -eq 1 ]; then
    git commit -q -F "$MESSAGE_FILE" || return 1
    NOTE_AS_NEW_COMMIT=0
  else
    git commit -q --amend --no-edit || return 1
  fi
  if [ -n "$AUTHORED" ]; then
    git rev-parse HEAD >> "$AUTHORED_SHAS_FILE"
  fi
}

if [ -n "$TAKEN_FROM_MAIN" ]; then
  note_in_clarifications "conflict with a concurrent run could not be resolved; main's version kept, this run's change to these files dropped:$TAKEN_FROM_MAIN" || exit 2
fi
LOCAL_SHA="$(git rev-parse --short HEAD)"
# A resumed call never built the commit, so its subject comes from the commit.
MESSAGE="${MESSAGE:-$(git log -1 --format=%s HEAD)}"

# The rail: nothing may differ from origin/main except what this tick wrote.
# This is the check that fails loudly if a stale tree ever reaches delivery by
# some other route — the guarantee does not rest on the fold staying correct.
# A refusal drops only what it names: those paths are put back to main's
# version (so nothing the tick never wrote can move), the rest is delivered, and
# the dropped paths are named in CLARIFICATIONS. Dropping is always safe — it
# can only lose this tick's own change to a path, never anyone else's.
REFUSED_FILE="$STATE_DIR/refused-paths"
rm -f "$REFUSED_FILE"
if ! python3 "$SCRIPT_DIR/_delivery_check.py" origin/main ".scheduler-state/staged-paths" "$REFUSED_FILE"; then
  if [ ! -s "$REFUSED_FILE" ]; then
    exit 2
  fi
  REFUSED=""
  while IFS= read -r rp || [ -n "$rp" ]; do
    [ -z "$rp" ] && continue
    if git_ref_has_path origin/main "$rp"; then
      MSYS_NO_PATHCONV=1 git checkout origin/main -- "$rp" >/dev/null 2>&1 || exit 2
    else
      git rm -q --cached --ignore-unmatch -- "$rp" >/dev/null 2>&1 || exit 2
    fi
    REFUSED="$REFUSED $rp"
  done < "$REFUSED_FILE"
  git commit -q --amend --no-edit --allow-empty || exit 2
  note_in_clarifications "delivery check dropped changes this run never recorded making:$REFUSED" || exit 2
  if ! python3 "$SCRIPT_DIR/_delivery_check.py" origin/main ".scheduler-state/staged-paths"; then
    exit 2
  fi
  echo "finalize-tick: dropped$REFUSED; delivering the rest"
  LOCAL_SHA="$(git rev-parse --short HEAD)"
fi

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
  if ! retry git push origin main; then
    # Rejected most often because main moved between integration and push.
    # Integrate again — once — rather than give the run up: the commit is
    # still here, and a second pass folds and merges it like the first.
    if [ -z "${FINALIZE_REINTEGRATED:-}" ] && retry git fetch origin main --quiet 2>/dev/null \
        && ! git merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
      echo "finalize-tick: main moved during delivery; integrating again"
      FLAGS=""
      [ "$RESOLVE_BY_MAIN" -eq 1 ] && FLAGS="$FLAGS --resolve-by-main"
      [ "$CHECKPOINT" -eq 1 ] && FLAGS="$FLAGS --checkpoint"
      # shellcheck disable=SC2086
      FINALIZE_REINTEGRATED=1 exec bash "$0" $FLAGS "${ORIG_ARGS[@]}"
    fi
    exit 2
  fi
  rm -f "$AUTHORED_SHAS_FILE" ".scheduler-state/staged-paths" "$MESSAGE_FILE"
  echo "finalize-tick: delivered to origin/main"
  exit 0
fi

# ROUTINES mode — push to sandbox branch + PR + squash merge + delete.
#
# Every GitHub call goes through `gh api` against the REST endpoints, never
# `gh pr` / `gh auth status`: those run on GraphQL, which the Claude Code
# sandbox proxy refuses with HTTP 403 — and gh reports that refusal as "the
# token in GH_TOKEN is invalid", whatever the token. The proxy authenticates
# REST calls itself, so `gh api` works there as it does anywhere gh is logged in.
echo "finalize-tick: ROUTINES mode (sandbox branch '$START_BRANCH') — push + PR + squash-merge"

if ! command -v gh >/dev/null 2>&1; then
  echo "finalize-tick: gh CLI not found in PATH; cannot complete Routines-mode delivery" >&2
  echo "finalize-tick: local commit $LOCAL_SHA persists; install gh or push manually" >&2
  exit 2
fi

# owner/repo from the origin URL — https, ssh, or a proxy URL all end in it.
REPO_SLUG="$(git remote get-url origin 2>/dev/null | sed -E 's#\.git$##; s#/+$##; s#^.*[:/]([^/:]+/[^/:]+)$#\1#')"
REPO_OWNER="${REPO_SLUG%%/*}"

# A gh that cannot reach the repository — no credentials, a rejected token, no
# such repo — is, for delivery, the same as no gh at all. It is reported with the
# marker the scheduler prompts key their MCP fallback (Step 5b) on, and before
# the sandbox push, which Step 5b performs itself.
gh_reach() { gh api "repos/$REPO_SLUG" --jq .full_name >/dev/null 2>&1; }
if ! retry gh_reach; then
  GH_REPO_OUT="$(gh api "repos/$REPO_SLUG" --jq .full_name 2>&1 || true)"
  echo "finalize-tick: gh cannot reach $REPO_SLUG — handled as gh CLI not found in PATH; cannot complete Routines-mode delivery" >&2
  printf '%s\n' "$GH_REPO_OUT" | sed 's/^/  gh: /' >&2
  echo "finalize-tick: local commit $LOCAL_SHA persists" >&2
  exit 2
fi

# The sandbox branch belongs to this run, and an earlier delivery of the same
# run can still be on it — process's first delivery, or an attempt that failed
# after its push. The commit now is a sibling of that one, not a descendant, so
# a plain push is refused. Replacing exactly what is there (a lease on the sha
# just read) is safe; if the platform refuses even that, the delivery goes out
# on a fresh branch of its own.
DELIVER_BRANCH="$START_BRANCH"
push_sandbox() {
  local remote_sha
  if retry git push origin "HEAD:refs/heads/$DELIVER_BRANCH" 2>&1; then
    return 0
  fi
  remote_sha="$(git ls-remote origin "refs/heads/$DELIVER_BRANCH" 2>/dev/null | cut -f1)"
  if [ -n "$remote_sha" ] && git push --force-with-lease="refs/heads/$DELIVER_BRANCH:$remote_sha" \
      origin "HEAD:refs/heads/$DELIVER_BRANCH" 2>&1; then
    echo "finalize-tick: replaced this run's earlier delivery on origin/$DELIVER_BRANCH"
    return 0
  fi
  DELIVER_BRANCH="$START_BRANCH-$(date -u +%Y%m%d%H%M%S)"
  echo "finalize-tick: delivering on a fresh branch, $DELIVER_BRANCH"
  retry git push origin "HEAD:refs/heads/$DELIVER_BRANCH" 2>&1
}
if ! push_sandbox; then
  echo "finalize-tick: push to sandbox branch '$START_BRANCH' failed" >&2
  exit 2
fi
echo "finalize-tick: pushed $LOCAL_SHA to origin/$DELIVER_BRANCH"

PR_BODY="Autonomous scheduler tick. Tag: \`$TAG\`. Generated by finalize-tick.sh. Squash-merge expected."

open_pr_number() {
  gh api "repos/$REPO_SLUG/pulls?state=open&base=main&head=$REPO_OWNER:$DELIVER_BRANCH" \
    --jq '.[0].number // empty' 2>/dev/null || true
}

# Reuse an existing PR if one is already open against this branch; otherwise create.
PR_NUMBER="$(open_pr_number)"
if [ -z "$PR_NUMBER" ]; then
  # gh's own message is the only place the cause appears — a missing
  # permission, a closed branch — and a tick's transcript is the only log there
  # is. gh never prints the token itself.
  # A create whose answer was lost may still have opened the PR, so every retry
  # looks for it first rather than opening a second one.
  n=0
  while :; do
    if PR_CREATE_OUT="$(gh api -X POST "repos/$REPO_SLUG/pulls" \
        -f base=main -f head="$DELIVER_BRANCH" -f title="$MESSAGE" -f body="$PR_BODY" \
        --jq .number 2>&1)"; then
      PR_NUMBER="$PR_CREATE_OUT"
      break
    fi
    PR_NUMBER="$(open_pr_number)"
    [ -n "$PR_NUMBER" ] && break
    n=$((n + 1))
    if [ "$n" -ge 3 ]; then
      echo "finalize-tick: PR create failed for $DELIVER_BRANCH" >&2
      printf '%s\n' "$PR_CREATE_OUT" | sed 's/^/  gh: /' >&2
      exit 2
    fi
    sleep $((n * 3))
  done
fi

case "$PR_NUMBER" in
  ''|*[!0-9]*)
    echo "finalize-tick: could not resolve PR number after creation" >&2
    exit 2
    ;;
esac
echo "finalize-tick: PR #$PR_NUMBER ready for squash-merge"

# The body is explicit and non-empty on purpose. An empty or absent body lets
# GitHub compose the squash message itself, and that message carries a
# `Co-authored-by` trailer for every commit author other than the merger — the
# sandbox commit's author included, which puts an assistant-authorship mark on
# `main`. The squash also writes a NEW message on `main`, so the run identity
# reaches it only by being handed over here. `tick_identity.py squash-body` owns
# the text, and the prompts' MCP fallback (Step 5b) calls the same command. If it
# cannot run, the subject stands in: never empty, only without the identity.
if ! MERGE_BODY="$(python3 "$SCRIPT_DIR/../lib/tick_identity.py" squash-body 2>/dev/null)" \
    || [ -z "$MERGE_BODY" ]; then
  echo "finalize-tick: warning — squash body could not be derived; the identity stops at the sandbox branch" >&2
  MERGE_BODY="$MESSAGE"
fi

set +e
n=0
while :; do
  MERGE_OUT="$(gh api -X PUT "repos/$REPO_SLUG/pulls/$PR_NUMBER/merge" \
    -f merge_method=squash -f commit_title="$MESSAGE" -f commit_message="$MERGE_BODY" 2>&1)"
  MERGE_RC=$?
  MERGED="$(gh api "repos/$REPO_SLUG/pulls/$PR_NUMBER" --jq .merged 2>/dev/null || echo unknown)"
  if [ "$MERGE_RC" -eq 0 ] || [ "$MERGED" = "true" ]; then
    break
  fi
  n=$((n + 1))
  [ "$n" -ge 3 ] && break
  # GitHub computes mergeability lazily; a fresh PR can answer "not mergeable
  # yet" for a few seconds.
  sleep $((n * 3))
done
set -e

if [ "$MERGE_RC" -eq 0 ] || [ "$MERGED" = "true" ]; then
  rm -f "$AUTHORED_SHAS_FILE" ".scheduler-state/staged-paths"
  # The repository may delete merged head branches itself; asking again is
  # harmless, and a sandbox branch the platform still holds may refuse — the
  # merge has landed either way.
  if ! gh api -X DELETE "repos/$REPO_SLUG/git/refs/heads/$DELIVER_BRANCH" >/dev/null 2>&1; then
    echo "finalize-tick: PR #$PR_NUMBER merged; sandbox branch not deleted here (already gone or retained by the platform)"
  fi
  echo "finalize-tick: PR #$PR_NUMBER squash-merged into main"
  # Continue from the main that now carries this delivery, so a later step of
  # the same tick (process delivers before and after maintain) builds on it
  # instead of on a commit main no longer has.
  if retry git fetch origin main --quiet 2>/dev/null; then
    git reset -q --keep origin/main 2>/dev/null || true
  fi
  rm -f "$MESSAGE_FILE"
  exit 0
fi

echo "finalize-tick: PR merge failed (merged=$MERGED)" >&2
printf '%s\n' "$MERGE_OUT" | sed 's/^/  gh: /' >&2
exit 2
