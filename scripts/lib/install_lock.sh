# shellcheck shell=bash
# One installer or uninstaller at a time per Claude Code home.
#
# Sourced by integrations/claude-code/install.sh and uninstall.sh. Both rewrite
# the managed block of CLAUDE.md and the links beside it, and the installer
# swaps built/; two runs at once — a manual install while an update runs
# migration 036, or two clones sharing one home — would interleave those writes.
#
# `mkdir` is atomic on every platform the engine supports, so the lock is a
# directory. Its `owner` file holds the holder's pid and a token unique to that
# run; a run releases the lock only while the token is still its own, so it can
# never remove a lock another run has taken since.
#
# Two gaps no portable primitive closes, both failing closed — the run refuses
# and says where the lock is: a run killed in the instant between creating the
# lock and writing its owner leaves a lock with no owner, and a dead holder
# whose pid the system has since reused looks alive. Either way, removing the
# lock directory by hand is the recovery, once no install is running.

minder_lock_pid() {
  # minder_lock_pid <dir> — the pid recorded in <dir>/owner, or nothing
  [ -f "$1/owner" ] || return 0
  sed -n '1s/ .*//p' "$1/owner"
}

minder_lock_alive() {
  # minder_lock_alive <pid> — true when that process exists
  [ -n "$1" ] && kill -0 "$1" 2>/dev/null
}

minder_lock_acquire() {
  # minder_lock_acquire <lock-dir> — 0 when this run holds the lock, 1 when another run does
  MINDER_LOCK_DIR="$1"
  MINDER_LOCK_TOKEN="$$-$(date +%s)-${RANDOM:-0}"
  local attempt holder takeover="$1.takeover"
  for attempt in 1 2 3 4 5 6; do
    if mkdir "$MINDER_LOCK_DIR" 2>/dev/null; then
      printf '%s %s\n' "$$" "$MINDER_LOCK_TOKEN" > "$MINDER_LOCK_DIR/owner"
      return 0
    fi
    holder="$(minder_lock_pid "$MINDER_LOCK_DIR")"
    # No owner yet means a run that has just created the lock: it is live.
    if [ -z "$holder" ] || minder_lock_alive "$holder"; then
      return 1
    fi
    # The holder is gone. Taking its lock over is serialised by a second
    # directory, so of several runs that all saw the same dead holder only one
    # removes it — and that one re-reads the holder first, so a lock a faster
    # run has already re-created is never removed.
    if mkdir "$takeover" 2>/dev/null; then
      printf '%s\n' "$$" > "$takeover/owner"
      if [ "$(minder_lock_pid "$MINDER_LOCK_DIR")" = "$holder" ]; then
        rm -rf "$MINDER_LOCK_DIR"
      fi
      rm -rf "$takeover"
    elif ! minder_lock_alive "$(minder_lock_pid "$takeover")"; then
      # A takeover whose run died between its two steps.
      rm -rf "$takeover"
    else
      sleep 1
    fi
  done
  return 1
}

minder_lock_release() {
  # Removes the lock only while it is still this run's.
  [ -n "${MINDER_LOCK_DIR:-}" ] || return 0
  if [ "$(sed -n '1p' "$MINDER_LOCK_DIR/owner" 2>/dev/null)" = "$$ ${MINDER_LOCK_TOKEN:-}" ]; then
    rm -rf "$MINDER_LOCK_DIR"
  fi
}
