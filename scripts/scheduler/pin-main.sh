#!/usr/bin/env bash
# Pin the working tree to a fresh `origin/main` before a scheduler tick.
#
# Captures the starting branch (the sandbox branch a Routine clones onto,
# e.g. `claude/admiring-shannon-ETCE3`) into `.scheduler-state/start-branch`
# so finalize-tick.sh can target it for the PR-merge delivery path.
#
# Steps:
#   1. Persist current HEAD branch name (or "DETACHED" if HEAD is detached).
#   2. `git fetch origin main` to refresh remote-tracking ref.
#   3. Branch-specific reconciliation:
#      - Already on main → `git pull --rebase origin main`. Replays any
#        local-only commits on top of origin/main.
#      - On a sandbox / other branch → `git checkout -B main origin/main`.
#
# Sandbox-branch cleanup is delegated to GitHub's "Automatically delete
# head branches" repo setting, which removes each branch immediately
# after its PR is squash-merged. No in-script sweep is needed.
#
# Usage:
#   bash scripts/scheduler/pin-main.sh
#
# Exit codes:
#   0 — on main, HEAD = origin/main (or local commits replayed on top)
#   1 — fetch / checkout / rebase failed (cause printed to stderr)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/../lib/git.sh"

STATE_DIR=".scheduler-state"
mkdir -p "$STATE_DIR"

# `git_current_branch_or` — never `rev-parse --abbrev-ref`, which exits 0 and
# prints the literal string `HEAD` on a detached checkout, so an `|| echo
# DETACHED` fallback never fires. That literal then reaches finalize-tick.sh,
# which reads it as a sandbox branch name and tries to deliver via
# `git push origin HEAD:HEAD` and a PR against a branch called `HEAD`.
START_BRANCH="$(git_current_branch_or DETACHED)"
printf '%s\n' "$START_BRANCH" > "$STATE_DIR/start-branch"
echo "pin-main: start branch = $START_BRANCH"

git fetch origin main || { echo "pin-main: fetch failed" >&2; exit 1; }

# A rebase left behind by a crashed run wedges every git operation after it, and
# the only thing that could have started one in this clone is the scheduler
# itself — no human works here. Clearing it is recovery, not a guess.
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
  echo "pin-main: an interrupted rebase is in progress; aborting it (scheduler-owned clone)" >&2
  git rebase --abort >/dev/null 2>&1 || git rebase --quit >/dev/null 2>&1 || true
fi

if [ "$START_BRANCH" = "main" ]; then
  # Deliberately NOT `git pull --rebase`. Replaying the tick's own unpushed commits
  # rewrites their SHAs, and finalize-tick.sh authorises commits by exact SHA from
  # `.scheduler-state/authored-shas` — so a rebase here turned a tick's own commit
  # into one "this tick did not author", which it then refused to fold, every
  # night, forever. Collapsing those commits belongs to finalize-tick.sh, the only
  # step that knows which SHAs the tick wrote.
  #
  # But the ordinary case still has to move: with no local commits, a tree left at
  # yesterday's tip makes the whole pipeline read stale inbox, state, registries
  # and role memory — and no amount of careful delivery afterwards can undo
  # decisions taken against stale input, or the duplicate processing it causes. So
  # fast-forward when there is nothing of our own to preserve, and only then.
  LOCAL_AHEAD="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"
  if [ "$LOCAL_AHEAD" -eq 0 ]; then
    if git merge --ff-only origin/main >/dev/null 2>&1; then
      echo "pin-main: fast-forwarded main to origin/main"
    else
      echo "pin-main: could not fast-forward to origin/main; the tree may be dirty or diverged" >&2
      exit 1
    fi
  else
    echo "pin-main: $LOCAL_AHEAD local commit(s) present — left intact for finalize-tick to fold"
  fi
else
  git checkout -B main origin/main || { echo "pin-main: checkout failed" >&2; exit 1; }
fi

echo "pin-main: HEAD now $(git rev-parse --short HEAD) on main (origin/main)"
