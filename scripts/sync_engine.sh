#!/usr/bin/env bash
# Sync engine paths from upstream/main into this clone.
#
# For friends (and the personal instance) — pulls engine updates that
# the upstream maintainer has shipped, without touching local data
# (records, knowledge, registries, constitution principles, SOUL, etc).
#
# Reads .engine-manifest.yml. For each `engine:` path, fetches the
# upstream version and overwrites the local path. `template:` paths are
# DELIBERATELY skipped — they seed once at clone time and are then
# friend's data. Then two steps that a plain copy cannot express:
# `retire_paths.py` removes what the manifest lists as `retired:` (a sync
# copies what upstream HAS, never what it no longer has), and
# `run_migrations.py` runs the pending chain, honouring each migration's
# declared kind.
#
# This script is the CI / power-user entry point. The default owner path is
# the `/minder:mem:update` skill, which does the same work with a preview and a
# plain-language digest — and which repairs THIS script from upstream before
# reading it, so a clone stuck on an old broken copy can always recover.
#
# Preconditions:
#   - git remote `upstream` configured and reachable
#   - working tree clean (script aborts if dirty in any engine path)
#   - python3 + PyYAML (used to parse the manifest)
#
# Usage:
#   scripts/sync_engine.sh                # fetch + apply
#   scripts/sync_engine.sh --dry-run      # show what would change
#   scripts/sync_engine.sh --remote name  # use a remote other than upstream
#   scripts/sync_engine.sh --self-heal    # repair THIS script from the remote
#                                         # first, then re-run — recovery for a
#                                         # clone whose copy is too broken to
#                                         # sync itself

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# `scripts/lib/git.sh` is sourced AFTER the self-heal below, never here. A clone
# old enough to need recovering predates the library entirely, so sourcing it at
# the top would kill the script on line one — on exactly the clone the recovery
# path exists for.

REMOTE="upstream"
BRANCH="main"
DRY_RUN=0
SELF_HEAL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --self-heal) SELF_HEAL=1 ;;
    --remote) REMOTE="$2"; shift ;;
    --branch) BRANCH="$2"; shift ;;
    --branch=*) BRANCH="${1#--branch=}" ;;
    --remote=*) REMOTE="${1#--remote=}" ;;
    -h|--help)
      sed -n '2,31p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "error: remote '$REMOTE' not configured." >&2
  echo "  add it: git remote add $REMOTE <url-to-minder-memory-skeleton>" >&2
  exit 2
fi

MANIFEST=".engine-manifest.yml"
if [ ! -f "$MANIFEST" ]; then
  echo "error: $MANIFEST not found at repo root" >&2
  exit 2
fi

# Self-heal: land the update machinery from the remote before trusting it.
#
# The machinery ships THROUGH the update, so a clone carrying a broken copy can
# never receive its own repair by the normal path. `git checkout <ref> -- <path>`
# passes no `<ref>:<path>` argument, so it works even where the manifest reader
# below does not. `/minder:mem:update` does this unconditionally; here it is opt-in,
# because a CI run wants the script it was invoked with.
if [ $SELF_HEAL -eq 1 ]; then
  echo "[sync] self-heal: fetching $REMOTE/$BRANCH and restoring scripts/ ..."
  git fetch "$REMOTE" "$BRANCH"
  git checkout "$REMOTE/$BRANCH" -- scripts/
  # A checkout writes what upstream HAS and says nothing about what upstream
  # dropped, so every retired migration and its helpers stay in the tree.
  # `scripts/` then differs from upstream forever and the dirty guard below
  # refuses it on every run — deadlocking the recovery on exactly the clone it
  # exists for. `--diff-filter=A` is the paths present here and absent there
  # (the ref is the diff's OLD side, the working tree its new one).
  # `core.quotepath=false` so a non-ASCII name arrives as itself; `--ignore-unmatch`
  # so an untracked leftover is not an error; never `git rm -f`, which would
  # reach beyond what this loop names.
  git -c core.quotepath=false diff --name-only --diff-filter=A "$REMOTE/$BRANCH" -- scripts/ |
    while IFS= read -r _stale; do
      [ -n "$_stale" ] || continue
      git rm -q --cached --ignore-unmatch -- "$_stale" >/dev/null 2>&1 || true
      rm -f -- "$_stale"
      echo "[sync] self-heal: removed $_stale (upstream no longer ships it)"
    done
  echo "[sync] self-heal: scripts/ restored — re-running the repaired script"
  exec bash "$REPO_ROOT/scripts/sync_engine.sh" --remote "$REMOTE" --branch "$BRANCH"
fi

# Only now — the self-heal above is what puts this file there on an old clone.
if [ ! -f "$SCRIPT_DIR/lib/git.sh" ]; then
  echo "error: $SCRIPT_DIR/lib/git.sh is missing." >&2
  echo "  This clone predates the shared git helpers. Recover with either:" >&2
  echo "      /minder:mem:update" >&2
  echo "      bash scripts/sync_engine.sh --self-heal" >&2
  exit 2
fi
. "$SCRIPT_DIR/lib/git.sh"

VERSION_FILE="integrations/VERSION"
version_before=""
[ -f "$VERSION_FILE" ] && version_before="$(tr -d '\r\n' < "$VERSION_FILE")"

# The migration chain starts at 031; a clone older than the floor takes the
# two-step path `lib/version_floor.py` prints. Only a jump ACROSS the floor is
# refused — updating to the floor release itself is that first step.
FLOOR_BRANCH="$(python3 "$SCRIPT_DIR/lib/version_floor.py" --floor-branch)"
if [ "$BRANCH" != "$FLOOR_BRANCH" ] && ! python3 "$SCRIPT_DIR/lib/version_floor.py" "$version_before"; then
  # Leave the tree as it was found. A self-heal from the current branch has
  # just added files under scripts/ that the floor release does not have; its
  # own sync would refuse the tree as dirty because of them, and the two-step
  # path the refusal prints would never get past its first step.
  git diff --cached --name-only --diff-filter=A -z -- scripts/ | while IFS= read -r -d '' added; do
    git rm -q --cached -- "$added" && rm -f -- "$added"
  done
  # Removing what the self-heal ADDED is only half of «as it was found»: every
  # file it overwrote still carries the newer release, so `scripts/` is dirty
  # and the floor release's own sync refuses the tree — the same dead end, one
  # step further along. Restoring from HEAD puts the clone back where it stood.
  #
  # This file is one of the files being restored. Bash has already read the
  # script it is running, so replacing it mid-run is harmless on POSIX; on Git
  # Bash a write to an open file can fail, and that failure must not turn a
  # refusal into a crash. So a failure here is reported and stepped over: the
  # only file at risk is this one, and the friend is about to run the floor
  # release's copy anyway.
  if ! git checkout HEAD -- scripts/ 2>/dev/null; then
    # One path at a time, through a read loop — never `$( )` word-splitting,
    # which would break on the first path carrying a space.
    git -c core.quotepath=false diff --name-only HEAD -- scripts/ |
      while IFS= read -r _path; do
        [ -n "$_path" ] || continue
        [ "$_path" = "scripts/sync_engine.sh" ] && continue
        git checkout HEAD -- "$_path" 2>/dev/null || true
      done
    echo "note: scripts/sync_engine.sh could not be restored while it is running." >&2
    echo "      Run:  git checkout HEAD -- scripts/sync_engine.sh" >&2
  fi
  exit 2
fi

if ! git ls-remote --exit-code "$REMOTE" "refs/heads/$BRANCH" > /dev/null 2>&1; then
  echo "error: $REMOTE has no branch '$BRANCH'." >&2
  if [ "$BRANCH" = "$FLOOR_BRANCH" ]; then
    echo "  The floor release is published on that branch by the engine maintainer; until it is," >&2
    echo "  a clone below $(python3 "$SCRIPT_DIR/lib/version_floor.py" --min-version) cannot update. Ask them." >&2
  fi
  exit 2
fi
echo "[sync] fetching $REMOTE/$BRANCH ..."
git fetch "$REMOTE" "$BRANCH"

# The engine list comes from the manifest this sync is ABOUT TO APPLY — the
# remote's — never from the clone's copy. The clone's manifest predates the
# update by definition, so a path added upstream would not be walked here and
# would never land, while `retire_paths.py` (which reads the manifest after
# checkout) would already remove its predecessor. The remote copy is read into
# a temp file so a dry run lists the right paths without touching the tree.
UPSTREAM_MANIFEST="$(mktemp "${TMPDIR:-/tmp}/engine-manifest.XXXXXX")"
trap 'rm -f "$UPSTREAM_MANIFEST"' EXIT
if git_ref_read_path "$REMOTE/$BRANCH" "$MANIFEST" > "$UPSTREAM_MANIFEST" && [ -s "$UPSTREAM_MANIFEST" ]; then
  MANIFEST_TO_READ="$UPSTREAM_MANIFEST"
else
  echo "[sync] warning: $MANIFEST not readable from $REMOTE/$BRANCH — using the local copy" >&2
  MANIFEST_TO_READ="$MANIFEST"
fi

# Read engine paths from the manifest.
#
# Portable read loop (not `mapfile` — that is bash 4.0+, and macOS ships
# bash 3.2). The helper emits through `lib.portable.emit_lines`, which forces
# LF: python's text-mode stdout writes CRLF on Git Bash, and a path carrying a
# trailing `\r` fails EVERY `git cat-file` below — which this script would then
# read as "absent upstream" and report success having synced nothing.
ENGINE_PATHS=()
while IFS= read -r _line; do
  [ -n "$_line" ] && ENGINE_PATHS+=("$_line")
done < <(python3 "$SCRIPT_DIR/manifest_paths.py" --section engine --manifest "$MANIFEST_TO_READ")

if [ ${#ENGINE_PATHS[@]} -eq 0 ]; then
  echo "error: no engine paths in $MANIFEST" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Converge `scripts/` DOWNWARDS, before the dirty guard reads it.
#
# The checkout loop below can only copy what upstream HAS; a file upstream has
# since deleted — a retired migration, a helper that moved — simply stays. Then
# `scripts/` differs from upstream in a direction no restore can close, and the
# guard refuses the tree on every run, forever.
#
# It has to run HERE, unconditionally, and NOT inside `--self-heal`. A clone old
# enough to need recovering runs its OWN copy of this script, and that copy's
# self-heal checks `scripts/` out and re-execs the restored script WITHOUT
# passing the flag on. Anything guarded by `--self-heal` in this file is
# therefore unreachable from the only clone that needs it: the repaired script
# arrives at the guard with the stale files still in place. Running it on the
# ordinary path is what makes the recovery reachable at all.
#
# `scripts/` only, because the manifest declares that directory engine wholesale
# — a file there is the engine's, and one upstream no longer ships has no owner
# left. `--diff-filter=A` is «present here, absent there»: the ref is the diff's
# OLD side and the working tree its new one. A dry run changes nothing.
# ---------------------------------------------------------------------------
if [ $DRY_RUN -eq 0 ]; then
  git -c core.quotepath=false diff --name-only --diff-filter=A "$REMOTE/$BRANCH" -- scripts/ |
    while IFS= read -r _stale; do
      [ -n "$_stale" ] || continue
      git rm -q --cached --ignore-unmatch -- "$_stale" >/dev/null 2>&1 || true
      rm -f -- "$_stale"
      echo "  - $_stale (upstream no longer ships it)"
    done
fi

# Abort if any engine path has uncommitted local changes.
#
# The check exists to protect an owner's uncommitted customisation from being
# overwritten. A path whose working tree already MATCHES the remote holds no
# such customisation — there is nothing there to lose — so it is not an abort.
# Without that carve-out the self-heal below deadlocks the script against
# itself: `--self-heal` checks `scripts/` out from the remote, which makes it
# dirty, which the very next run refuses to proceed past.
DIRTY=0
for p in "${ENGINE_PATHS[@]}"; do
  if ! git diff --quiet -- "$p" 2>/dev/null || \
     ! git diff --cached --quiet -- "$p" 2>/dev/null; then
    if git diff --quiet "$REMOTE/$BRANCH" -- "$p" 2>/dev/null; then
      continue  # dirty vs HEAD, identical to upstream — nothing at risk
    fi
    echo "  ! dirty: $p" >&2
    DIRTY=1
  fi
done
if [ $DIRTY -ne 0 ]; then
  echo "error: engine paths have uncommitted changes — commit or stash first." >&2
  echo "  When the dirty path is scripts/, that is the update machinery having repaired itself." >&2
  echo "  Commit scripts/ only (git add scripts && git commit) — your notes must not go into that commit." >&2
  exit 2
fi

if [ $DRY_RUN -eq 1 ]; then
  echo "[sync] dry-run: would overwrite the following paths from $REMOTE/$BRANCH:"
  for p in "${ENGINE_PATHS[@]}"; do
    echo "  - $p"
    git --no-pager diff --stat "$REMOTE/$BRANCH" -- "$p" 2>/dev/null || true
  done
  echo "[sync] (dry-run) done. no changes applied."
  exit 0
fi

# Engine paths whose upstream layout is a real-file directory but whose local
# copy may be a symlink or — on a Windows clone with core.symlinks=false — a
# text file masquerading as a symlink. A plain `git checkout` of the directory
# then aborts with "blocked by existing file" on the file→dir type change. These
# paths carry no owner data, so removing the local copy before checkout is safe
# and lets the real-file tree land cleanly. This is what heals a Windows clone's
# broken `.claude/skills/` on `/minder:mem:update`.
DEREF_CLEAN_PATHS=(".claude/skills")

echo "[sync] checking out engine paths from $REMOTE/$BRANCH ..."
RESOLVED=0
ABSENT=0
for p in "${ENGINE_PATHS[@]}"; do
  # `git_ref_has_path` — never a bare `git cat-file -e "$ref:$p"`. MSYS on Git
  # Bash rewrites a `<ref>:<path>` argument, and every dotfile engine path
  # (.gitignore, .claude/CLAUDE.md, .engine-manifest.yml) fails as an invalid
  # object name under that rewrite.
  if git_ref_has_path "$REMOTE/$BRANCH" "$p"; then
    RESOLVED=$((RESOLVED + 1))
    for clean in "${DEREF_CLEAN_PATHS[@]}"; do
      if [ "$p" = "$clean" ]; then
        rm -rf "$p"
        break
      fi
    done
    git checkout "$REMOTE/$BRANCH" -- "$p"
    echo "  + $p"
  else
    # Path may have been removed upstream — leave local copy alone.
    ABSENT=$((ABSENT + 1))
    echo "  · $p (not in upstream, kept local)"
  fi
done

# ---------------------------------------------------------------------------
# Retirement. The loop above can only copy what upstream HAS; a path upstream
# no longer has is simply never walked, so every file the engine ever removed
# is still sitting on this clone. `retired:` in the manifest is the other half
# of that contract, and it runs on every sync rather than once, so a clone at
# any version converges — including one that has been dark for months.
#
# Deliberately NOT inferred from «absent upstream»: that is equally the shape
# of a botched path list, which is exactly how a bad reader once looked like
# «upstream deleted the entire engine». Only what the manifest names is
# removed, and the helper refuses outright if any of it reaches owner space.
# ---------------------------------------------------------------------------

# A migration that has to reach the remote (031 converges engine paths the
# clone's previous script could not fetch) follows the pair THIS sync was
# invoked with, not a name it guessed.
export ENGINE_SYNC_REMOTE="$REMOTE"
export ENGINE_SYNC_BRANCH="$BRANCH"

if ! python3 "$REPO_ROOT/scripts/retire_paths.py"; then
  echo >&2
  echo "error: retirement refused — see the paths above." >&2
  echo "  Nothing was deleted. Fix the manifest's retired: section and re-run." >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Post-conditions. A sync that resolves nothing is a broken sync, not an
# up-to-date one, and the two are indistinguishable without these checks —
# which is precisely how a Windows clone ran `/minder:mem:update` for weeks while
# applying nothing and exiting 0 every time.
# ---------------------------------------------------------------------------

if [ "$RESOLVED" -eq 0 ]; then
  echo >&2
  echo "error: not one of the ${#ENGINE_PATHS[@]} engine paths was found in $REMOTE/$BRANCH." >&2
  echo "  That is never the shape of an up-to-date clone — upstream would have to have" >&2
  echo "  deleted the entire engine. Something mangled the paths before git saw them." >&2
  echo "  Most likely: a stale copy of this script whose manifest reader emitted CRLF," >&2
  echo "  or MSYS path conversion on Git Bash." >&2
  echo "  Recover with:  /minder:mem:update                       (repairs this script first)" >&2
  echo "             or:  bash scripts/sync_engine.sh --self-heal" >&2
  exit 2
fi

version_after=""
[ -f "$VERSION_FILE" ] && version_after="$(tr -d '\r\n' < "$VERSION_FILE")"
version_upstream="$(git_ref_read_path "$REMOTE/$BRANCH" "$VERSION_FILE" | tr -d '\r\n' || true)"

if [ -n "$version_upstream" ] && [ "$version_after" != "$version_upstream" ]; then
  echo >&2
  echo "error: $VERSION_FILE is '$version_after' after the sync but upstream ships" >&2
  echo "  '$version_upstream'. The checkout did not land what it reported." >&2
  echo "  Nothing has been rolled back; inspect with:  git status" >&2
  exit 2
fi

echo
if [ "$version_before" != "$version_after" ]; then
  echo "[sync] $RESOLVED path(s) updated, $ABSENT absent upstream — engine ${version_before:-?} → ${version_after:-?}"
else
  echo "[sync] $RESOLVED path(s) updated, $ABSENT absent upstream — engine ${version_after:-?} (unchanged)"
fi

echo
echo "[sync] applying migrations (if any) ..."
# The runner owns the ledger and each migration's declared kind: a `structural`
# failure aborts, a `heal` failure is recorded and the update continues. See
# scripts/lib/migrations.py for why a repair of old data must never be able to
# block a future update.
python3 "$SCRIPT_DIR/run_migrations.py" || {
  echo "error: a structural migration failed — see above." >&2
  exit 2
}

echo
echo "[sync] refreshing derived vault docs ..."
# The four files under <vault>/5_meta/help/ are copies of engine docs. They are
# DERIVED: an update that rewrote their sources has to rewrite them too, or the
# vault keeps showing whatever was current when this clone was installed.
#
# It lives HERE rather than in the /minder:mem:update skill because this script is what
# both update paths run — the skill is a wrapper around it, and a friend using
# the CLI directly gets the same convergence. Putting it in the skill only would
# have left the documented power-user path permanently frozen.
#
# Non-fatal: a stale help doc is no reason to fail an otherwise-good update.
if [ -x "$REPO_ROOT/integrations/obsidian/seed.sh" ] || [ -f "$REPO_ROOT/integrations/obsidian/seed.sh" ]; then
  bash "$REPO_ROOT/integrations/obsidian/seed.sh" --refresh-help || \
    echo "[sync] warning: vault help docs not refreshed — re-run: bash integrations/obsidian/seed.sh --refresh-help" >&2
fi

# The commit is not optional housekeeping. Two of the update's own checks —
# «was your credential store touched» and «what did an earlier release rename»
# — are answered by comparing against a commit, so a clone that never commits
# its update leaves them permanently unanswerable. The skill's Step 8 does this
# for the owner; a friend running the script directly was never told, which is
# why the caveat is here rather than in a doc they may not read.
#
# The installer already ran inside migration 031, so this does not ask for it
# again: a step suggested twice is a step somebody performs twice and then
# wonders which one counted.
cat <<EOF

[sync] done. The Claude Code installer ran as part of migration 031 — nothing to re-run.

Review the diff:    git status
Run tests:          (your test suite — engine ships pytest under zettelkasten/_system/scripts/tests/)
Check it:           python3 scripts/check_update.py
                    Proves from your filesystem that the update landed — before you
                    commit it, not after.
Commit it:          git add -A && git commit -m "engine ${version_after:-updated}"
                    Careful: that stages everything, including notes you have open and
                    have not saved. Commit those separately first if you want them apart.

If something looks wrong, revert with:  git restore --staged --worktree .
EOF
