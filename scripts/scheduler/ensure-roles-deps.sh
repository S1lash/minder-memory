#!/usr/bin/env bash
# Ensure the roles tick can open an encrypted credential store.
#
# The store (`_system/state/secrets.enc.json`) is encrypted with `cryptography`,
# which the engine imports LAZILY: a base with no credentials never needs the
# package and must not be made to care about it. A base WITH credentials cannot
# open the store without it, and every role that declares one then fails.
#
# Why this helper exists rather than a line in the docs telling the owner to
# install it: a Cloud Routines sandbox starts from a fresh clone every run, so
# nothing an owner installs there persists to the next tick. «Install it where
# the tick runs» is unactionable advice in exactly the environment that made the
# store encrypted-and-committed in the first place. Without this, a credentialed
# role works on a laptop and is dead on arrival in the cloud.
#
# It is deliberately narrow:
#   - does NOTHING when the base has no store — the common case pays nothing,
#     and a base without credentials never installs a package it will not use;
#   - does NOTHING when the import already works — an idempotent no-op, so a
#     sandbox that ships the package costs one interpreter start;
#   - installs ONLY when a store exists AND the import fails, and only a
#     VALIDATED spec for the one package the engine declares;
#   - never touches the store, never reads a credential, never prints one, and
#     never sees the key — it only proves the package imports.
#
# A failed install is not fatal here. The tick's own `secrets-open` reports the
# condition through the ordinary `role-secrets-unavailable` path, which names
# the cause and degrades instead of dying: roles needing no credential still
# run. This helper's job is to remove the failure when it can, not to become a
# second place that decides what happens when it cannot.
#
# Usage:
#   bash scripts/scheduler/ensure-roles-deps.sh
#
# Exit codes:
#   0 — nothing needed, or the package is importable (before or after install)
#   2 — more than one Minder Memory base in the repository (which one is meant?)
#       (no base at all is exit 0 — a repo without one has nothing to check)
#   3 — a store exists and the package is still unimportable; the tick will
#       degrade and say so. Advisory: the caller does NOT abort on this.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# The base is discovered, never assumed to be called `zettelkasten` — an owner
# may rename it, and every other scheduler helper resolves it the same way.
BASE=""
for d in "$REPO_ROOT"/*/; do
    [ -f "$d/_system/scripts/roles_run.py" ] || continue
    if [ -n "$BASE" ]; then
        echo "ensure-roles-deps: more than one Minder Memory base in $REPO_ROOT" >&2
        exit 2
    fi
    BASE="${d%/}"
done

if [ -z "$BASE" ]; then
    echo "ensure-roles-deps: no Minder Memory base found; nothing to check"
    exit 0
fi

if [ ! -f "$BASE/_system/state/secrets.enc.json" ]; then
    echo "ensure-roles-deps: no credential store on this base; nothing to install"
    exit 0
fi

# `python3 -c 'import cryptography'` is the whole test. Not a version compare:
# the engine's floor lives in requirements.txt and duplicating it here would be
# a second source of truth that drifts.
if python3 -c 'import cryptography' >/dev/null 2>&1; then
    echo "ensure-roles-deps: cryptography already available"
    exit 0
fi

# Take the pin from requirements.txt so this script never becomes the place the
# version is decided — but VALIDATE it before it reaches pip.
#
# That file is inside the repository, and a repository is a thing a role can end
# up writing to on an abort path. `cryptography @ https://evil/x.whl` satisfies a
# naive "starts with cryptography" test, and pip would fetch and execute it,
# unattended, as the tick. So the accepted shape is exactly a name plus an
# optional PEP-440 version specifier and nothing else: no URL, no `@`, no extras,
# no whitespace, no shell metacharacter. Anything else falls back to the bare
# name, which pip resolves from the configured index.
SPEC="$(python3 "$SCRIPT_DIR/_pick_crypto_spec.py" "$BASE/_system/scripts/requirements.txt")"

echo "ensure-roles-deps: a credential store exists and cryptography is missing; installing $SPEC"
PIP_RC=0
# Bounded, because this is the one place the tick reaches the network with
# nobody watching. Without a timeout a slow or hanging index stalls the whole
# 07:00 run; `--only-binary` keeps it from compiling a C extension on a machine
# that may have no toolchain, which would hang far longer than any download.
PIP_OUT="$(python3 -m pip install --disable-pip-version-check \
    --timeout 30 --retries 2 --only-binary :all: "$SPEC" 2>&1)" || PIP_RC=$?

if [ "$PIP_RC" -ne 0 ]; then
    case "$PIP_OUT" in
        *externally-managed-environment*|*externally*managed*)
            # PEP 668. A stock Linux or Homebrew python refuses to install into
            # the system environment, and it refuses the same way every night.
            # Name which problem this is, so the owner is not left reading
            # `role-secrets-unavailable` and blaming the key.
            echo "ensure-roles-deps: this Python is externally managed (PEP 668), so the tick" >&2
            echo "  cannot install into it. Run the roles tick inside a virtualenv, or install" >&2
            echo "  the package once by hand where the tick actually runs:" >&2
            echo "      python3 -m pip install --user '$SPEC'" >&2
            ;;
        *)
            echo "ensure-roles-deps: install failed — the tick will report role-secrets-unavailable" >&2
            printf '%s\n' "$PIP_OUT" | tail -3 | sed 's/^/  /' >&2
            ;;
    esac
    exit 3
fi

if python3 -c 'import cryptography' >/dev/null 2>&1; then
    echo "ensure-roles-deps: cryptography installed"
    exit 0
fi

echo "ensure-roles-deps: installed but still not importable — the tick will report it" >&2
exit 3
