#!/usr/bin/env bash
# Close a scheduler tick: measure it, deliver it, and record the outcome.
#
# One command instead of two, because every step a model has to remember at
# the end of a long run is a step it can forget — and the step that was being
# forgotten was the delivery itself. The outcome lands in the tick's record
# (`tick_state.py`), which is what the closing guard (`.claude/hooks/tick_guard.py`)
# reads before it lets the run end.
#
# Usage:
#   bash scripts/scheduler/close-tick.sh <tag> [--checkpoint] [--resolve-by-main]
#
#   <tag>              scheduler/process, scheduler/lint, scheduler/agent-lens,
#                      scheduler/roles or scheduler/content
#   --checkpoint       deliver what is done so far and keep the tick open
#                      (process delivers once before maintain, once after)
#   --resolve-by-main  last resort for a conflict the tick could not resolve —
#                      passed by the guard, never by a prompt
#
# Exit codes (finalize-tick.sh's, passed through):
#   0 — delivered (or nothing to deliver); a final close marks the tick closed
#   2 — delivery failed; when gh cannot reach the repository the output carries
#       "gh CLI not found in PATH" and Step 5b of the prompt takes over
#   3 — a conflict needs resolving (Step 5c), then this runs again

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
  echo "usage: $0 <tag> [--checkpoint] [--resolve-by-main]" >&2
  exit 2
fi

TAG="$1"
shift
CHECKPOINT=0
FINALIZE_OPTS=""
for arg in "$@"; do
  case "$arg" in
    --checkpoint) CHECKPOINT=1; FINALIZE_OPTS="$FINALIZE_OPTS --checkpoint" ;;
    --resolve-by-main) FINALIZE_OPTS="$FINALIZE_OPTS --resolve-by-main" ;;
  esac
done

PIPELINE="${TAG#scheduler/}"

# A conflict that stopped a checkpoint is still a checkpoint when it is
# resolved, whichever command the model re-runs: closing the tick there would
# skip maintain and the tick's one telemetry line.
CHECKPOINT_CONFLICT=".scheduler-state/conflict-checkpoint"
if [ -f "$CHECKPOINT_CONFLICT" ] && [ -f .scheduler-state/conflict ] && [ "$CHECKPOINT" -eq 0 ]; then
  echo "close-tick: the open conflict came from the checkpoint; this call completes the checkpoint"
  CHECKPOINT=1
  FINALIZE_OPTS="$FINALIZE_OPTS --checkpoint"
fi

# The odometer runs before the commit that carries its line, and only on the
# final close: a checkpoint is half a tick, and one tick is one line. It never
# fails the tick (`record_tick_telemetry.py` always exits 0).
if [ "$CHECKPOINT" -eq 0 ] && [ ! -f .scheduler-state/conflict ]; then
  python3 "$SCRIPT_DIR/record_tick_telemetry.py" "$PIPELINE" || true
fi

OUT_FILE=".scheduler-state/close-output"
mkdir -p .scheduler-state
# shellcheck disable=SC2086
bash "$SCRIPT_DIR/finalize-tick.sh" $FINALIZE_OPTS "$TAG" > "$OUT_FILE" 2>&1
RC=$?
cat "$OUT_FILE"

case "$RC" in
  0)
    rm -f "$CHECKPOINT_CONFLICT"
    if [ "$CHECKPOINT" -eq 1 ]; then
      python3 "$SCRIPT_DIR/tick_state.py" checkpoint --for "$TAG"
      echo "close-tick: checkpoint delivered; the tick stays open"
    else
      python3 "$SCRIPT_DIR/tick_state.py" set --for "$TAG" closed delivered
      echo "close-tick: tick closed"
    fi
    ;;
  3)
    # finalize-tick.sh already recorded the conflict; remember where it came from
    if [ "$CHECKPOINT" -eq 1 ]; then
      : > "$CHECKPOINT_CONFLICT"
    fi
    ;;
  *)
    if [ "$CHECKPOINT" -eq 1 ]; then
      # The prompt carries on to maintain and the final close delivers all of
      # it, so the tick is still simply open — not failed.
      python3 "$SCRIPT_DIR/tick_state.py" set --for "$TAG" open "checkpoint not delivered (exit $RC)"
    elif grep -q "gh CLI not found in PATH" "$OUT_FILE"; then
      python3 "$SCRIPT_DIR/tick_state.py" set --for "$TAG" needs-mcp
    else
      python3 "$SCRIPT_DIR/tick_state.py" set --for "$TAG" failed "finalize-tick exited $RC"
    fi
    ;;
esac
exit "$RC"
