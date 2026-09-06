#!/usr/bin/env bash
# migration-kind: structural
# 031-minder-memory-harness-wiring — the product is Minder Memory; re-wire the harness.
#
# minder-memory-rebrand: keep-legacy-tokens — this header names the former names on purpose.
#
# The engine sync that carries this migration renamed every skill
# (`ztn-<name>` → `minder-mem-<name>`, answering to `/minder:mem:<name>`), the
# hot rule (`ztn.md` → `minder-memory.md`), the commands (now under
# `commands/minder/mem/`) and the role agent, and `retire_paths.py` removed the
# old ones from this clone. The harness home under `~/.claude` is outside the
# repository, so the sync cannot reach it: every symlink the installer created
# still points at a name that no longer exists, and the managed block in
# `~/.claude/CLAUDE.md` still imports the old rule file.
#
# `structural`, on the README's one question: continuing past a failure here
# is dangerous — every session would import a dead rule and find no skill under
# either name. So a non-zero exit aborts the update, records nothing, and the
# next update resumes exactly here.
#
# The work is in `_031_harness_wiring.py` (markers, links, installer, remotes,
# digest); this file only declares the kind and delegates. Idempotent: a second
# run finds current markers, no legacy links, an installer that refreshes in
# place and a remote already renamed — and changes nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 "$SCRIPT_DIR/_031_harness_wiring.py" --repo-root "$REPO_ROOT" "$@"
