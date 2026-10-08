#!/usr/bin/env bash
# migration-kind: heal
# 036-hot-context-wiring — one mechanism for what loads into every session.
#
# The installer used to link the engine's global files into
# `~/.claude/rules/`, a directory Claude Code loads on its own, AND import five
# of them from the managed block in `~/.claude/CLAUDE.md`. The sixth, the engine
# doctrine, reached every session on the machine through the directory alone.
# The installer now links the global files into `~/.claude/minder-memory/`,
# which nothing loads by itself, imports each one from the block, leaves the
# doctrine to this repository's `.claude/CLAUDE.md`, and removes the six old
# links. The sync cannot reach `~/.claude`, so this re-runs the installer.
#
# `heal`, on the README's one question: continuing past a failure is not
# dangerous. The installer writes the new wiring before it removes the old, so
# a failed run never leaves sessions loading less than before. A non-zero exit
# is recorded `partial` and the next update tries again.
#
# Idempotent: the installer refreshes in place.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALLER="integrations/claude-code/install.sh"

if [ ! -f "$REPO_ROOT/$INSTALLER" ]; then
  echo "[migration 036] no $INSTALLER in this clone — no harness wiring to refresh"
  exit 0
fi

rc=0
( cd "$REPO_ROOT" && bash "$INSTALLER" ) || rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[migration 036] install.sh exited $rc — the previous wiring is still in place." >&2
  echo "[migration 036] Run it by hand, or let the next update retry:" >&2
  echo "    bash $INSTALLER" >&2
  exit "$rc"
fi
echo "[migration 036] harness wiring refreshed"
