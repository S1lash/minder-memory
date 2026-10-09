#!/usr/bin/env bash
# migration-kind: heal
# 037-converge-clones-and-backups — re-run the installer once more.
#
# The installer now removes the engine's retired links into ANY clone, live or
# deleted, so two clones on one machine converge; it backs up CLAUDE.md only
# when it changes it and keeps the newest such backup. A clone that already ran
# 036 would not run the installer again on its own, so this does.
#
# `heal`: a failed run leaves the wiring exactly as 036 left it — working. A
# non-zero exit is recorded `partial` and the next update tries again.
#
# Idempotent: the installer refreshes in place.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALLER="integrations/claude-code/install.sh"

if [ ! -f "$REPO_ROOT/$INSTALLER" ]; then
  echo "[migration 037] no $INSTALLER in this clone — no harness wiring to refresh"
  exit 0
fi

rc=0
( cd "$REPO_ROOT" && bash "$INSTALLER" ) || rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[migration 037] install.sh exited $rc — the previous wiring is still in place." >&2
  echo "[migration 037] Run it by hand, or let the next update retry:" >&2
  echo "    bash $INSTALLER" >&2
  exit "$rc"
fi
echo "[migration 037] harness wiring refreshed"
