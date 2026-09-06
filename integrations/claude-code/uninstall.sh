#!/usr/bin/env bash
# minder-memory — remove Claude Code integration symlinks.
#
# Removes only symlinks pointing into THIS repo. Untouched: any
# unrelated entries in ~/.claude/{rules,commands,skills,agents}, including
# files backed up by install.sh (those live under ~/.claude/.minder-memory-backup-*).

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

# `commands/minder/` is the ecosystem's namespace directory (a real directory
# shared with sibling products); this product's link is `commands/minder/mem`.
for d in "$CLAUDE_HOME/rules" "$CLAUDE_HOME/commands" "$CLAUDE_HOME/commands/minder" "$CLAUDE_HOME/skills" "$CLAUDE_HOME/agents"; do
  [ -d "$d" ] || continue
  for entry in "$d"/*; do
    remove_if_points_into_repo "$entry"
  done
done

# Strip managed block from ~/.claude/CLAUDE.md (added by install.sh).
CLAUDE_MD="$CLAUDE_HOME/CLAUDE.md"
BEGIN_MARK="<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->"
END_MARK="<!-- MINDER-MEMORY END -->"
if [ -f "$CLAUDE_MD" ] && grep -qF "$BEGIN_MARK" "$CLAUDE_MD"; then
  TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
  BACKUP_DIR="$CLAUDE_HOME/.minder-memory-backup-$TIMESTAMP"
  mkdir -p "$BACKUP_DIR"
  cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md.before-uninstall"
  awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
    $0 == begin { skip = 1; next }
    $0 == end   { skip = 0; next }
    !skip       { print }
  ' "$CLAUDE_MD" > "$CLAUDE_MD.tmp" && mv "$CLAUDE_MD.tmp" "$CLAUDE_MD"
  echo "[uninstall] stripped managed block from $CLAUDE_MD (backup: $BACKUP_DIR)"
fi

echo "[uninstall] done. Backups (if any) preserved at $CLAUDE_HOME/.minder-memory-backup-*"
