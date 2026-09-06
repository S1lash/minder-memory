#!/usr/bin/env bash
# Ensure project-level Minder Memory skills resolve at `.claude/skills/<name>/SKILL.md`.
#
# Skill discovery for Cloud Routines and project-CWD sessions depends on
# `.claude/skills/<name>/SKILL.md` being a READABLE file in the clone. The
# owner's repo keeps these as symlinks into `integrations/claude-code/skills/`
# (native on macOS / Linux, convenient for the dev loop); the public skeleton
# ships them as real files, because git symlinks do NOT survive a Windows
# clone — with `core.symlinks=false` git materialises the symlink blob as a
# text file containing the target path, so `.claude/skills/minder-mem-process` becomes
# a FILE (not a directory) and `.claude/skills/minder-mem-process/SKILL.md` no longer
# exists. The runtime then cannot load the skill and every `/minder:mem:*` slash
# invocation in a scheduler tick fails at the first step.
#
# The canonical set of skills is the directory listing under
# `integrations/claude-code/skills/` — the single source of truth. This
# helper reconciles `.claude/skills/` against it.
#
# Modes:
#   (default) check-only — verify every skill resolves. Exit 0 if all do,
#     3 if any are missing/broken (broken names printed to stderr). Never
#     mutates the working tree.
#   --repair — additionally recreate any missing/broken entry. Prefers a
#     relative symlink (`ln -sfn`); if the filesystem or git refuses
#     symlinks (Windows without developer mode), falls back to copying the
#     skill directory as real files. Idempotent — good entries are left
#     untouched.
#
# Usage:
#   bash scripts/scheduler/ensure-skills.sh            # check only
#   bash scripts/scheduler/ensure-skills.sh --repair   # heal broken entries
#
# Exit codes:
#   0 — all skills resolve (after optional repair)
#   2 — --repair could not fix an entry (source missing / write failed)
#   3 — check-only found broken skills (no --repair requested)

set -euo pipefail

REPAIR=0
if [ "${1:-}" = "--repair" ]; then
  REPAIR=1
fi

SRC_DIR="integrations/claude-code/skills"
DST_DIR=".claude/skills"

if [ ! -d "$SRC_DIR" ]; then
  echo "ensure-skills: source skill dir '$SRC_DIR' not found — wrong CWD or broken clone" >&2
  exit 2
fi

broken=()
repair_failed=()

for src in "$SRC_DIR"/*/; do
  [ -d "$src" ] || continue
  name="$(basename "$src")"
  skill_file="$DST_DIR/$name/SKILL.md"

  # `-r` follows symlinks: a valid symlink to a real file passes; a broken
  # symlink, a missing entry, or a text-file-masquerading-as-symlink (dir
  # path resolves to nothing) all fail.
  if [ -r "$skill_file" ]; then
    continue
  fi

  broken+=("$name")

  if [ "$REPAIR" -ne 1 ]; then
    continue
  fi

  # Remove whatever is in the way (broken symlink, stray text file, partial dir).
  rm -rf "$DST_DIR/$name"
  mkdir -p "$DST_DIR"

  # Prefer a relative symlink (matches the owner-repo convention, lightest).
  if ln -sfn "../../$SRC_DIR/$name" "$DST_DIR/$name" 2>/dev/null && [ -r "$skill_file" ]; then
    continue
  fi

  # Symlink unsupported (Windows) or did not resolve — copy real files.
  rm -rf "$DST_DIR/$name"
  mkdir -p "$DST_DIR/$name"
  if cp -R "$src." "$DST_DIR/$name/" 2>/dev/null && [ -r "$skill_file" ]; then
    continue
  fi

  repair_failed+=("$name")
done

if [ "$REPAIR" -eq 1 ]; then
  if [ "${#repair_failed[@]}" -gt 0 ]; then
    echo "ensure-skills: FAILED to repair ${#repair_failed[@]} skill(s): ${repair_failed[*]}" >&2
    exit 2
  fi
  if [ "${#broken[@]}" -gt 0 ]; then
    echo "ensure-skills: repaired ${#broken[@]} skill(s): ${broken[*]}"
  fi
  exit 0
fi

if [ "${#broken[@]}" -gt 0 ]; then
  echo "ensure-skills: ${#broken[@]} skill(s) not resolvable at $DST_DIR/<name>/SKILL.md: ${broken[*]}" >&2
  echo "ensure-skills: run 'bash scripts/scheduler/ensure-skills.sh --repair', or 'bash scripts/sync_engine.sh' to pull the real-file layout from upstream" >&2
  exit 3
fi

exit 0
