#!/usr/bin/env bash
# minder-memory — Claude Code integration installer.
#
# Sets up user-level Claude Code discoverability for Minder Memory's global
# files, commands and skills under ~/.claude/. Two layers:
#
#   - rules + commands carry the {{MINDER_MEMORY_BASE}} placeholder. The
#     installer renders them into integrations/claude-code/built/ with the
#     placeholder substituted by the absolute path to <repo>/zettelkasten.
#     The global files (HOT_FILES below) are linked into ~/.claude/minder-memory/,
#     a directory Claude Code does NOT load by itself, and each is imported
#     from the managed block in ~/.claude/CLAUDE.md — so the block is the
#     complete list of what the engine puts into every session. This keeps the
#     constitution-capture hook + ambient /minder:mem:capture-candidate /
#     /minder:mem:check-decision reachable from any CWD. The engine doctrine is
#     not among them: it loads only inside the repository, imported by
#     .claude/CLAUDE.md.
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
BUILT_STAGE="$INTEGR_ROOT/built.new"
BUILT_PREVIOUS="$INTEGR_ROOT/built.old"

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
# `rules/` is loaded by Claude Code on its own. Nothing of the engine's belongs
# there; the installer only removes the links an earlier version put in it.
TARGET_RULES="$CLAUDE_HOME/rules"
TARGET_HOT="$CLAUDE_HOME/minder-memory"
TARGET_COMMANDS="$CLAUDE_HOME/commands"
TARGET_SKILLS="$CLAUDE_HOME/skills"
TARGET_AGENTS="$CLAUDE_HOME/agents"

# The global files: one row each — link name | source under the repo | the
# heading it is imported under in the managed block. The links and the block
# are both generated from this table, so the block cannot list a file that is
# not linked, nor link one it does not list. Every rule under
# integrations/claude-code/rules/ needs a row (rendered, it lands in built/rules/).
HOT_FILES="$(cat <<'TABLE'
minder-memory.md|integrations/claude-code/built/rules/minder-memory.md|Zettelkasten (Minder Memory) — Personal Knowledge Base
constitution-capture.md|zettelkasten/_system/docs/constitution-capture.md|Constitution Capture — Global Hook
communication-baseline.md|zettelkasten/_system/docs/communication-baseline.md|Communication baseline — how to present information
advisory-baseline.md|zettelkasten/_system/docs/advisory-baseline.md|Advisory baseline — how to reason, weigh, and advise
constitution-core.md|zettelkasten/_system/views/constitution-core.md|Constitution — auto-loaded values & principles
TABLE
)"

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
#
# Rendered into a staging directory and swapped in only when complete: the
# links of the CURRENT wiring point into built/, so removing it before the
# render finished would leave every session importing a missing rule until
# the next run.
log "rendering templates into $BUILT"
rm -rf "$BUILT_STAGE" "$BUILT_PREVIOUS"
mkdir -p "$BUILT_STAGE/rules" "$BUILT_STAGE/commands"

for f in "$SRC_RULES"/*.md; do
  [ -f "$f" ] || continue
  render "$f" "$BUILT_STAGE/rules/$(basename "$f")"
done

# Commands live in a namespace directory (`commands/minder/mem/<name>.md` is how
# Claude Code spells `/minder:mem:<name>`), so they are rendered with their
# relative path kept.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  rel="${f#$SRC_COMMANDS/}"
  render "$f" "$BUILT_STAGE/commands/$rel"
done <<COMMANDS
$(find "$SRC_COMMANDS" -type f -name '*.md' | sort)
COMMANDS

if [ -d "$BUILT" ]; then
  mv "$BUILT" "$BUILT_PREVIOUS"
fi
mv "$BUILT_STAGE" "$BUILT"
rm -rf "$BUILT_PREVIOUS"

# --- Symlinks ~/.claude/ -> rendered files ---
log "creating symlinks under $CLAUDE_HOME"
mkdir -p "$TARGET_HOT" "$TARGET_COMMANDS" "$TARGET_SKILLS" "$TARGET_AGENTS"

# Global files — linked beside rules/, never into it; the managed block below
# imports each one.
while IFS='|' read -r name source heading; do
  [ -n "$name" ] || continue
  link "$REPO_ROOT/$source" "$TARGET_HOT/$name"
done <<EOF
$HOT_FILES
EOF

# Commands — one link for the product's namespace directory. `~/.claude/
# commands/minder/` stays a REAL directory: it is the ecosystem's namespace,
# and a sibling product links its own segment beside `mem`. Linking the whole
# `minder/` directory would monopolise it.
COMMANDS_NAMESPACE_DIR="$BUILT/commands/minder/mem"
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
  for dir in "$TARGET_RULES" "$TARGET_HOT" "$TARGET_COMMANDS" "$TARGET_COMMANDS/minder" "$TARGET_SKILLS" "$TARGET_AGENTS"; do
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
  local first=1
  printf '%s\n' "$BEGIN_MARK"
  while IFS='|' read -r name source heading; do
    [ -n "$name" ] || continue
    [ "$first" -eq 1 ] || printf '\n'
    first=0
    printf '## %s\n- @~/.claude/minder-memory/%s\n' "$heading" "$name"
  done <<EOF
$HOT_FILES
EOF
  printf '%s\n' "$END_MARK"
}

if [ ! -f "$CLAUDE_MD" ]; then
  log "creating $CLAUDE_MD"
  mkdir -p "$CLAUDE_HOME"
  managed_block > "$CLAUDE_MD"
elif grep -qF "$BEGIN_MARK" "$CLAUDE_MD"; then
  log "refreshing managed block in $CLAUDE_MD"
  # The splice drops everything from BEGIN up to the matching END line. With no
  # END line it would drop the rest of the file — the owner's own instructions
  # included — so the refresh is refused instead.
  if ! tr -d '\r' < "$CLAUDE_MD" | grep -qxF "$END_MARK"; then
    log "error: $CLAUDE_MD has the managed block's BEGIN marker but not its END marker — it is unchanged" >&2
    log "  Restore the line '$END_MARK' after the block, then re-run: bash integrations/claude-code/install.sh" >&2
    exit 1
  fi
  mkdir -p "$BACKUP_DIR"
  cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md.before-refresh"
  # Splice the new block in via awk getline from a file. A multi-line
  # `-v block="$(managed_block)"` value is rejected by some awk builds
  # (macOS bwk awk: «awk: newline in string»), which silently no-ops the
  # refresh — so the block is read from a file, never from a var.
  # Only the first block found is replaced by the fresh one; any later block
  # (a duplicate an earlier sequence of installs may have left) is dropped.
  managed_block > "$CLAUDE_MD.block"
  # Markers are compared without a trailing CR: a file saved by a Windows
  # editor keeps CRLF, and a marker that no longer matches would turn the
  # refresh into a silent no-op.
  if awk -v begin="$BEGIN_MARK" -v end="$END_MARK" -v blockfile="$CLAUDE_MD.block" '
    { line0 = $0; sub(/\r$/, "", line0) }
    line0 == begin { if (!done) { while ((getline line < blockfile) > 0) print line; close(blockfile); done = 1 }; skip = 1; next }
    line0 == end   { skip = 0; next }
    !skip          { print }
  ' "$CLAUDE_MD" > "$CLAUDE_MD.tmp"; then
    # A CLAUDE.md kept in a dotfiles repo is a symlink: write through it, never
    # replace it — `mv` would swap the link for a file and cut it off from that repo.
    if [ -L "$CLAUDE_MD" ]; then
      cat "$CLAUDE_MD.tmp" > "$CLAUDE_MD"
      rm -f "$CLAUDE_MD.tmp"
    else
      mv "$CLAUDE_MD.tmp" "$CLAUDE_MD"
    fi
  else
    # A command in an `if` condition does not trip `set -e`, so the failure is
    # handled here, and it stops the run: the old block still imports the old
    # links, and retiring them below under an unchanged block would leave every
    # session importing files that no longer exist.
    rm -f "$CLAUDE_MD.block" "$CLAUDE_MD.tmp"
    log "error: could not rewrite the managed block in $CLAUDE_MD — it is unchanged" >&2
    log "  re-run: bash integrations/claude-code/install.sh" >&2
    exit 1
  fi
  rm -f "$CLAUDE_MD.block" "$CLAUDE_MD.tmp"
else
  log "appending managed block to $CLAUDE_MD"
  mkdir -p "$BACKUP_DIR"
  cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md.before-append"
  printf '\n' >> "$CLAUDE_MD"
  managed_block >> "$CLAUDE_MD"
fi

# --- Verify the block landed ---
# The old links below may go only once the block imports the new ones: the
# previous block imports the old links, and retiring them under it would leave
# every session importing files that no longer exist.
BLOCK_STATUS=0
block_text="$(tr -d '\r' < "$CLAUDE_MD" | awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
  $0 == begin { inside = 1; next }
  $0 == end   { inside = 0; next }
  inside      { print }
')"
case "$block_text" in
  *"@~/.claude/rules/"*) BLOCK_STATUS=1 ;;
esac
while IFS='|' read -r name source heading; do
  [ -n "$name" ] || continue
  case "$block_text" in
    *"@~/.claude/minder-memory/$name"*) ;;
    *) BLOCK_STATUS=1 ;;
  esac
done <<EOF
$HOT_FILES
EOF
if [ "$BLOCK_STATUS" -ne 0 ]; then
  log "error: the managed block in $CLAUDE_MD does not import exactly the files in ~/.claude/minder-memory/" >&2
  log "  The old links in $TARGET_RULES are left in place. Re-run: bash integrations/claude-code/install.sh" >&2
  exit 1
fi

# --- Retire the links an earlier installer put in rules/ ---
# Last, after the new links and the block are in place: a run that stops before
# this point leaves sessions loading what they loaded before, never a block of
# dead imports. Which entries are ours is decided by `lib.ownership` (asked
# through harness_entries.py, never restated here): a name the engine shipped
# there, a symlink, and a target inside this repository however it is spelled.
# An owner's own file under one of those names, or a link into somewhere else,
# is not ours. Anything this cannot finish makes the run fail, so the migration
# that called it is retried.
RETIRE_STATUS=0
retire_rule_links() {
  local helper="$REPO_ROOT/scripts/lib/harness_entries.py"
  local entries entry status=0
  [ -d "$TARGET_RULES" ] || return 0
  if [ ! -f "$helper" ] ||
     ! entries="$(python3 "$helper" --removable-rule-links --home "$CLAUDE_HOME" --repo "$REPO_ROOT")"; then
    log "error: could not decide which links in $TARGET_RULES are ours — they are left in place" >&2
    log "  Fix python3 / the clone, then re-run: bash integrations/claude-code/install.sh" >&2
    return 1
  fi
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    if rm -f "$entry"; then
      log "removed retired link: $entry"
    else
      log "error: could not remove $entry — it is left in place" >&2
      status=1
    fi
  done <<EOF
$entries
EOF
  return "$status"
}
retire_rule_links || RETIRE_STATUS=$?

if [ -d "$BACKUP_DIR" ]; then
  log "previous entries backed up to: $BACKUP_DIR"
fi

# --- Obsidian vault seed (idempotent; skipped if .obsidian/ already exists) ---
OBSIDIAN_SEED="$REPO_ROOT/integrations/obsidian/seed.sh"
if [ -x "$OBSIDIAN_SEED" ]; then
  log "running Obsidian vault seeder"
  MINDER_MEMORY_BASE="$MINDER_MEMORY_BASE" "$OBSIDIAN_SEED" || log "obsidian seed failed (non-fatal)"
fi

printf '\n[install] done.\n\nWired into ~/.claude/CLAUDE.md (managed block), linked from ~/.claude/minder-memory/:\n'
while IFS='|' read -r name source heading; do
  [ -n "$name" ] || continue
  printf '  - @~/.claude/minder-memory/%s\n' "$name"
done <<EOF
$HOT_FILES
EOF

cat <<EOF

The engine doctrine loads only inside this repository, through .claude/CLAUDE.md.

Obsidian vault config:
  - Seeded into $MINDER_MEMORY_BASE/.obsidian/ if not already present.
  - Open the vault: Obsidian → Open folder as vault → $MINDER_MEMORY_BASE
  - Start at minder-memory.md (Cmd+O → "minder-memory").
  - Reset to engine defaults later: bash integrations/obsidian/seed.sh --force

Restart Claude Code (open a new session) to pick up the rules.
Re-run this installer any time after a 'git pull' on minder-memory — it is
idempotent and refreshes the managed block in place.

EOF

if [ "$RETIRE_STATUS" -ne 0 ]; then
  log "error: the new wiring is in place, but old links remain in $TARGET_RULES (see above)" >&2
  exit "$RETIRE_STATUS"
fi
