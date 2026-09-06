#!/usr/bin/env bash
# minder-memory — Claude Code integration installer.
#
# Sets up user-level Claude Code discoverability for Minder Memory rules / commands /
# skills under ~/.claude/. Two layers:
#
#   - rules + commands carry the {{MINDER_MEMORY_BASE}} placeholder. The
#     installer renders them into integrations/claude-code/built/ with the
#     placeholder substituted by the absolute path to <repo>/zettelkasten,
#     then symlinks ~/.claude/{rules,commands}/ entries to the rendered
#     files. This path keeps the constitution-capture hook + ambient
#     /minder:mem:capture-candidate / /minder:mem:check-decision reachable from any CWD.
#   - skills use repo-relative `zettelkasten/...` paths in their source
#     and need no rendering. The installer symlinks ~/.claude/skills/minder-mem-*
#     directly to the source under integrations/claude-code/skills/. The
#     committed `.claude/skills/` symlinks at the repo root handle the
#     project-level + cloud-Routines discovery layer — see README.md.
#
# Existing entries that would be overwritten are moved to a timestamped
# backup directory under ~/.claude/.minder-memory-backup-*.
#
# Idempotent: re-running the installer refreshes rendered files and
# replaces stale symlinks. Safe after `git pull` or after moving the repo.

set -euo pipefail

# ---------------------------------------------------------------------------
# Git Bash: make real symlinks possible before anything is linked.
#
# Without `MSYS=winsymlinks:nativestrict`, Git Bash's `ln -s` either writes a
# plain text stub or fails outright — and it fails PARTWAY, leaving a stray
# directory inside ~/.claude/skills/ that the friend then has to delete by hand
# before a retry ("ln: failed to create symbolic link … : Not a directory").
#
# Detecting the platform and re-executing ourselves once with the variable set
# is the whole fix: the friend is never asked to know about an environment
# variable, and the guard is inert everywhere else. `MINDER_MEMORY_SYMLINK_REEXEC`
# makes it strictly once — if the second run still cannot link, the failure is
# real and must surface rather than loop.
# ---------------------------------------------------------------------------
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW* | MSYS* | CYGWIN*)
    case "${MSYS:-}" in
      *winsymlinks:nativestrict*) ;;
      *)
        if [ -z "${MINDER_MEMORY_SYMLINK_REEXEC:-}" ]; then
          printf '[install] %s\n' "Git Bash detected — re-running with MSYS=winsymlinks:nativestrict so symlinks are real"
          MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict" \
          MINDER_MEMORY_SYMLINK_REEXEC=1 \
            exec bash "${BASH_SOURCE[0]}" "$@"
        fi
        printf '[install] %s\n' "warning: MSYS=winsymlinks:nativestrict could not be applied; symlinks may be stubs" >&2
        ;;
    esac
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INTEGR_ROOT="$SCRIPT_DIR"
MINDER_MEMORY_BASE="$REPO_ROOT/zettelkasten"

SRC_RULES="$INTEGR_ROOT/rules"
SRC_COMMANDS="$INTEGR_ROOT/commands"
SRC_SKILLS="$INTEGR_ROOT/skills"

BUILT="$INTEGR_ROOT/built"
BUILT_RULES="$BUILT/rules"
BUILT_COMMANDS="$BUILT/commands"

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
TARGET_RULES="$CLAUDE_HOME/rules"
TARGET_COMMANDS="$CLAUDE_HOME/commands"
TARGET_SKILLS="$CLAUDE_HOME/skills"
TARGET_AGENTS="$CLAUDE_HOME/agents"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$CLAUDE_HOME/.minder-memory-backup-$TIMESTAMP"

log() { printf '[install] %s\n' "$*"; }

render() {
  # render <src-file> <dst-file>
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  sed "s|{{MINDER_MEMORY_BASE}}|$MINDER_MEMORY_BASE|g" "$src" > "$dst"
}

backup_if_exists() {
  # backup_if_exists <path>
  local p="$1"
  [ -e "$p" ] || [ -L "$p" ] || return 0
  # If it is already a symlink to the desired target, nothing to back up.
  if [ -L "$p" ] && [ "$(readlink "$p")" = "$2" ]; then
    return 0
  fi
  mkdir -p "$BACKUP_DIR"
  local rel="${p#$CLAUDE_HOME/}"
  local backup_path="$BACKUP_DIR/$rel"
  mkdir -p "$(dirname "$backup_path")"
  mv "$p" "$backup_path"
  log "backed up: $p -> $backup_path"
}

link() {
  # link <src> <dst>
  #
  # Leaves the destination either fully linked or absent — never half-made.
  # A previous run that could not create real symlinks (Git Bash without
  # `winsymlinks:nativestrict`, guarded at the top of this script) used to leave
  # a stub file or a stray directory behind, and the next run then failed on it
  # with "Not a directory" and stopped mid-loop, growing the residue. Clearing
  # the destination first and verifying the result afterwards removes both
  # halves of that failure.
  local src="$1" dst="$2"
  backup_if_exists "$dst" "$src"
  mkdir -p "$(dirname "$dst")"
  # `backup_if_exists` returns early when `$dst` is already the symlink we
  # want; anything else it moves away. This clears whatever survived either
  # path, so `ln` never lands inside an existing directory.
  if [ -L "$dst" ] || [ -e "$dst" ]; then
    rm -rf "$dst"
  fi
  ln -sfn "$src" "$dst"
  if [ ! -L "$dst" ]; then
    rm -rf "$dst"
    log "error: could not create a real symlink at $dst" >&2
    log "  Your shell wrote a stub instead. On Git Bash, run:" >&2
    log "    MSYS=winsymlinks:nativestrict bash integrations/claude-code/install.sh" >&2
    return 1
  fi
  log "linked: $dst -> $src"
}

log "repo root: $REPO_ROOT"
log "MINDER_MEMORY_BASE: $MINDER_MEMORY_BASE"

# --- Render templated rules + commands into built/ ---
# Skills carry no {{MINDER_MEMORY_BASE}} placeholder (sources use repo-relative
# `zettelkasten/...` paths) — they are NOT rendered into built/ and the
# user-level symlinks below point directly to the source tree.
log "rendering templates into $BUILT"
rm -rf "$BUILT"
mkdir -p "$BUILT_RULES" "$BUILT_COMMANDS"

for f in "$SRC_RULES"/*.md; do
  [ -f "$f" ] || continue
  render "$f" "$BUILT_RULES/$(basename "$f")"
done

# Commands live in a namespace directory (`commands/minder/mem/<name>.md` is how
# Claude Code spells `/minder:mem:<name>`), so they are rendered with their
# relative path kept.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  rel="${f#$SRC_COMMANDS/}"
  render "$f" "$BUILT_COMMANDS/$rel"
done <<COMMANDS
$(find "$SRC_COMMANDS" -type f -name '*.md' | sort)
COMMANDS

# --- Symlinks ~/.claude/ -> rendered files ---
log "creating symlinks under $CLAUDE_HOME"
mkdir -p "$TARGET_RULES" "$TARGET_COMMANDS" "$TARGET_SKILLS" "$TARGET_AGENTS"

# Rules: integration-managed (templated) + zettelkasten-internal (auto-loaded)
for f in "$BUILT_RULES"/*.md; do
  [ -f "$f" ] || continue
  link "$f" "$TARGET_RULES/$(basename "$f")"
done
link "$MINDER_MEMORY_BASE/_system/docs/constitution-capture.md" "$TARGET_RULES/constitution-capture.md"
link "$MINDER_MEMORY_BASE/_system/views/constitution-core.md" "$TARGET_RULES/constitution-core.md"
# Communication baseline — universal presentation spine, hot in every session.
# Owner's calibration layers on top: SOUL → Context for Agents + the long-form playbook.
link "$MINDER_MEMORY_BASE/_system/docs/communication-baseline.md" "$TARGET_RULES/communication-baseline.md"
# Advisory baseline — universal reasoning spine (objective, stance toward third
# parties, criteria, variance). Sibling of the presentation spine above: that one
# governs how an answer is delivered, this one how it is reached. Owner's
# calibration layers on top: their ai-interaction principles + the on-demand
# decision-advisory playbook.
link "$MINDER_MEMORY_BASE/_system/docs/advisory-baseline.md" "$TARGET_RULES/advisory-baseline.md"
# Engine doctrine — operating philosophy auto-loaded in every session.
# Every /minder:mem:* skill reads it; the symlink ensures it flows into ad-hoc
# Claude Code sessions in this repo too (e.g. when owner is debugging
# without invoking a skill).
link "$MINDER_MEMORY_BASE/_system/docs/ENGINE_DOCTRINE.md" "$TARGET_RULES/minder-memory-engine-doctrine.md"

# Commands — one link for the product's namespace directory. `~/.claude/
# commands/minder/` stays a REAL directory: it is the ecosystem's namespace,
# and a sibling product links its own segment beside `mem`. Linking the whole
# `minder/` directory would monopolise it.
COMMANDS_NAMESPACE_DIR="$BUILT_COMMANDS/minder/mem"
if [ -d "$COMMANDS_NAMESPACE_DIR" ]; then
  mkdir -p "$TARGET_COMMANDS/minder"
  link "$COMMANDS_NAMESPACE_DIR" "$TARGET_COMMANDS/minder/mem"
fi

# Skills (entire dir per skill) — symlink directly to source. No render
# step (sources are placeholder-free), so user-level symlinks resolve to
# the same content as project-level `.claude/skills/` symlinks at the
# repo root. Edits to a SKILL.md source are picked up immediately by
# both layers; install.sh re-run is not required after skill edits.
for skill_dir in "$SRC_SKILLS"/*/; do
  [ -d "$skill_dir" ] || continue
  skill_name="$(basename "$skill_dir")"
  link "${skill_dir%/}" "$TARGET_SKILLS/$skill_name"
done

# Agent definitions the engine owns, by NAME — never a directory sweep, because
# `.claude/agents/` is also where the owner drops their own agents and those are
# not ours to link into a global home. Without this, `minder-mem-role` resolves only
# when the session's CWD is inside the repo, so /minder:mem:role:add completes its
# whole interview and then fails its mandatory trial run with `agent-missing`.
if [ -f "$REPO_ROOT/.claude/agents/minder-mem-role.md" ]; then
  link "$REPO_ROOT/.claude/agents/minder-mem-role.md" "$TARGET_AGENTS/minder-mem-role.md"
fi

# Self-heal: a link under the four target directories that points into THIS
# repository and no longer resolves is ours and dead — a rendered file that the
# re-render above no longer produces, a skill or command that moved. Nothing
# fails on a dangling link; the rule or skill simply stops loading, silently,
# so it is removed here rather than left for someone to notice a month later.
# A link that points anywhere else is not ours to touch.
prune_dangling_links() {
  local dir entry target
  for dir in "$TARGET_RULES" "$TARGET_COMMANDS" "$TARGET_COMMANDS/minder" "$TARGET_SKILLS" "$TARGET_AGENTS"; do
    [ -d "$dir" ] || continue
    for entry in "$dir"/* "$dir"/.[!.]*; do
      [ -L "$entry" ] || continue
      [ -e "$entry" ] && continue
      target="$(readlink "$entry")"
      case "$target" in
        "$REPO_ROOT"/*)
          rm -f "$entry"
          log "removed dangling link: $entry -> $target"
          ;;
      esac
    done
  done
}
prune_dangling_links

# Repair project-level `.claude/skills/` at the repo root. Cloud Routines and
# project-CWD sessions load skills from there, not from the user-level links
# above. On a clone where the committed symlinks did not survive (a Windows
# checkout with core.symlinks=false materialises them as text files), this
# heals the layout — symlink where supported, real-file copy as fallback.
ENSURE_SKILLS="$REPO_ROOT/scripts/scheduler/ensure-skills.sh"
if [ -f "$ENSURE_SKILLS" ]; then
  if ( cd "$REPO_ROOT" && bash "$ENSURE_SKILLS" --repair ); then
    log "verified project-level .claude/skills/ resolves"
  else
    log "WARNING: could not repair project-level .claude/skills/ — run 'bash scripts/sync_engine.sh' or re-clone"
  fi
fi

# --- Auto-wire @-imports into ~/.claude/CLAUDE.md ---
# Idempotent: managed block delimited by markers. Re-running install.sh
# rewrites the block in place. uninstall.sh strips it.
CLAUDE_MD="$CLAUDE_HOME/CLAUDE.md"
BEGIN_MARK="<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->"
END_MARK="<!-- MINDER-MEMORY END -->"

managed_block() {
  cat <<BLOCK
$BEGIN_MARK
## Zettelkasten (Minder Memory) — Personal Knowledge Base
- @~/.claude/rules/minder-memory.md

## Constitution Capture — Global Hook
- @~/.claude/rules/constitution-capture.md

## Communication baseline — how to present information
- @~/.claude/rules/communication-baseline.md

## Advisory baseline — how to reason, weigh, and advise
- @~/.claude/rules/advisory-baseline.md

## Constitution — auto-loaded values & principles
- @~/.claude/rules/constitution-core.md
$END_MARK
BLOCK
}

if [ ! -f "$CLAUDE_MD" ]; then
  log "creating $CLAUDE_MD"
  mkdir -p "$CLAUDE_HOME"
  managed_block > "$CLAUDE_MD"
elif grep -qF "$BEGIN_MARK" "$CLAUDE_MD"; then
  log "refreshing managed block in $CLAUDE_MD"
  mkdir -p "$BACKUP_DIR"
  cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md.before-refresh"
  # Splice the new block in via awk getline from a file. A multi-line
  # `-v block="$(managed_block)"` value is rejected by some awk builds
  # (macOS bwk awk: «awk: newline in string»), which silently no-ops the
  # refresh — so the block is read from a file, never from a var.
  # Only the first block found is replaced by the fresh one; any later block
  # (a duplicate an earlier sequence of installs may have left) is dropped.
  managed_block > "$CLAUDE_MD.block"
  if awk -v begin="$BEGIN_MARK" -v end="$END_MARK" -v blockfile="$CLAUDE_MD.block" '
    $0 == begin { if (!done) { while ((getline line < blockfile) > 0) print line; close(blockfile); done = 1 }; skip = 1; next }
    $0 == end   { skip = 0; next }
    !skip       { print }
  ' "$CLAUDE_MD" > "$CLAUDE_MD.tmp"; then
    mv "$CLAUDE_MD.tmp" "$CLAUDE_MD"
  fi
  # Clean temp files unconditionally — even if awk failed above (a failing
  # `awk && mv` under `set -e` would otherwise exit before cleanup).
  rm -f "$CLAUDE_MD.block" "$CLAUDE_MD.tmp"
else
  log "appending managed block to $CLAUDE_MD"
  mkdir -p "$BACKUP_DIR"
  cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md.before-append"
  printf '\n' >> "$CLAUDE_MD"
  managed_block >> "$CLAUDE_MD"
fi

if [ -d "$BACKUP_DIR" ]; then
  log "previous entries backed up to: $BACKUP_DIR"
fi

# --- Obsidian vault seed (idempotent; skipped if .obsidian/ already exists) ---
OBSIDIAN_SEED="$REPO_ROOT/integrations/obsidian/seed.sh"
if [ -x "$OBSIDIAN_SEED" ]; then
  log "running Obsidian vault seeder"
  MINDER_MEMORY_BASE="$MINDER_MEMORY_BASE" "$OBSIDIAN_SEED" || log "obsidian seed failed (non-fatal)"
fi

cat <<EOF

[install] done.

Wired into ~/.claude/CLAUDE.md (managed block):
  - @~/.claude/rules/minder-memory.md                    (search triggers, decision-check discovery)
  - @~/.claude/rules/constitution-capture.md   (global capture hook)
  - @~/.claude/rules/communication-baseline.md (universal presentation spine)
  - @~/.claude/rules/advisory-baseline.md      (universal reasoning spine)
  - @~/.claude/rules/constitution-core.md      (axioms / principles / rules)

Obsidian vault config:
  - Seeded into $MINDER_MEMORY_BASE/.obsidian/ if not already present.
  - Open the vault: Obsidian → Open folder as vault → $MINDER_MEMORY_BASE
  - Start at minder-memory.md (Cmd+O → "minder-memory").
  - Reset to engine defaults later: bash integrations/obsidian/seed.sh --force

Restart Claude Code (open a new session) to pick up the rules.
Re-run this installer any time after a 'git pull' on minder-memory — it is
idempotent and refreshes the managed block in place.

EOF
