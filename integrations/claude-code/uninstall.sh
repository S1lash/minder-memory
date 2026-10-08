#!/usr/bin/env bash
# minder-memory — remove Claude Code integration symlinks.
#
# Removes only symlinks pointing into THIS repo. Untouched: any
# unrelated entries in ~/.claude/{minder-memory,rules,commands,skills,agents},
# including files backed up by install.sh (those live under
# ~/.claude/.minder-memory-backup-*). `minder-memory/` is removed once empty —
# never with its contents.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"

remove_if_points_into_repo() {
  local p="$1"
  if [ -L "$p" ]; then
    local target
    target="$(readlink "$p")"
    case "$target" in
      "$REPO_ROOT"/*)
        rm "$p"
        echo "[uninstall] removed: $p"
        ;;
    esac
  fi
}

# The managed block goes first: while it exists it imports the files linked
# below, so removing them before the block is gone — and then failing on the
# block — would leave every session importing files that no longer exist.
CLAUDE_MD="$CLAUDE_HOME/CLAUDE.md"
BEGIN_MARK="<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->"
END_MARK="<!-- MINDER-MEMORY END -->"
if [ -f "$CLAUDE_MD" ] && grep -qF "$BEGIN_MARK" "$CLAUDE_MD"; then
  if ! tr -d '\r' < "$CLAUDE_MD" | grep -qxF "$END_MARK"; then
    echo "[uninstall] error: $CLAUDE_MD has the block's BEGIN marker but not its END marker — nothing was removed" >&2
    exit 1
  fi
  TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
  BACKUP_DIR="$CLAUDE_HOME/.minder-memory-backup-$TIMESTAMP"
  mkdir -p "$BACKUP_DIR"
  cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md.before-uninstall"
  # Markers compared without a trailing CR, as install.sh does.
  if awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
    { line0 = $0; sub(/\r$/, "", line0) }
    line0 == begin { skip = 1; next }
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
    rm -f "$CLAUDE_MD.tmp"
    echo "[uninstall] error: could not strip the managed block from $CLAUDE_MD — nothing was removed" >&2
    exit 1
  fi
  echo "[uninstall] stripped managed block from $CLAUDE_MD (backup: $BACKUP_DIR)"
fi

# `commands/minder/` is the ecosystem's namespace directory (a real directory
# shared with sibling products); this product's link is `commands/minder/mem`.
for d in "$CLAUDE_HOME/minder-memory" "$CLAUDE_HOME/rules" "$CLAUDE_HOME/commands" "$CLAUDE_HOME/commands/minder" "$CLAUDE_HOME/skills" "$CLAUDE_HOME/agents"; do
  [ -d "$d" ] || continue
  for entry in "$d"/*; do
    remove_if_points_into_repo "$entry"
  done
done

if [ -d "$CLAUDE_HOME/minder-memory" ] && rmdir "$CLAUDE_HOME/minder-memory" 2>/dev/null; then
  echo "[uninstall] removed: $CLAUDE_HOME/minder-memory"
fi

echo "[uninstall] done. Backups (if any) preserved at $CLAUDE_HOME/.minder-memory-backup-*"
