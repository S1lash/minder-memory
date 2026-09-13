#!/usr/bin/env bash
# migration-kind: heal
# 034-register-resolve-clarifications-source — ask for the source approved knowledge travels through.
#
# The registry is owner data, so this never writes it. While no table of
# SOURCES.md carries the resolve-clarifications row, it prints the
# /minder:mem:source-add command for the agent running the update and exits
# non-zero, so the next update asks again.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if grep -Eq "^\|[[:space:]]*resolve-clarifications[[:space:]]*\|" "$REPO_ROOT/zettelkasten/_system/registries/SOURCES.md"; then
  echo "[migration 034] source resolve-clarifications is registered"
  exit 0
fi

cat <<'EOF'
[migration 034] The resolve-clarifications source is not registered. Knowledge
approved in /minder:mem:resolve-clarifications reaches /minder:mem:process through
it. Run after this update finishes:

  /minder:mem:source-add --id resolve-clarifications --layout flat-md --description "Knowledge the owner approved in a `/minder:mem:resolve-clarifications` session — one flat file per approved answer, holding the question and the owner's words; `/minder:mem:process` folds it in like any source. Producer and file shape: that skill's Step 6.5."
EOF
exit 1
