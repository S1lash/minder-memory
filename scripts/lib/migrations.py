#!/usr/bin/env python3
"""The migration ledger — what ran, and with what outcome.

Why a ledger and not a name list. `sync_engine.sh` used to run each migration
with `bash "$m"` under `set -euo pipefail` and append its name to a flat
`.engine-migrations-applied` file *after* the call. A non-zero exit therefore
aborted the whole update AND left the name unrecorded — so every future
`/minder:mem:update` re-ran the same migration and re-aborted at the same point. A
friend's clone was stuck that way for weeks on `007`, a best-effort repair of
historical data that can legitimately fail to fully succeed.

That inversion is the defect: a repair of old data must never be able to block
a future engine update. Fixing it needs two things this module provides.

**A declared kind.** Each migration states, in a header comment, what its
failure means:

    # migration-kind: structural   — the engine's shape is wrong without it;
                                     failure aborts the update (the old
                                     behaviour, now the explicit minority)
    # migration-kind: heal         — best-effort repair of existing data;
                                     failure is recorded and the update
                                     continues

A migration with no header is read as `structural`, so nothing silently
changes meaning.

**An outcome per attempt.** The ledger is append-only JSONL, one object per
attempt: `name`, `kind`, `rc`, `outcome`, `ts`, `note`. Outcomes:

  - `applied` — succeeded; never runs again.
  - `partial` — a `heal` that failed; the update continued, and it is retried
    on the next update. So an improved repair shipped later picks the clone up
    by itself, and a permanently-unfixable residue costs one printed line per
    update rather than a dead update channel.

A structural failure is deliberately NOT recorded: it aborts, and re-runs next
time, exactly as before.

Backward compatible: a clone carrying the old flat `.engine-migrations-applied`
file has every name in it folded into the ledger on first read, as `applied`.
Nothing is lost and no friend re-runs a migration they already have.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__ = [
    "LEDGER_FILENAME",
    "LEGACY_FILENAME",
    "KINDS",
    "DEFAULT_KIND",
    "declared_kind",
    "load_ledger",
    "record_attempt",
    "pending",
]

LEDGER_FILENAME = ".engine-migrations.jsonl"
LEGACY_FILENAME = ".engine-migrations-applied"

KINDS = ("structural", "heal")
DEFAULT_KIND = "structural"

# Outcomes that mean "do not run this again".
_TERMINAL_OUTCOMES = frozenset({"applied"})

_KIND_RE = re.compile(r"^#\s*migration-kind:\s*([a-z-]+)\s*$", re.MULTILINE)


def declared_kind(script: Path) -> str:
    """The migration's declared kind, defaulting to `structural`.

    Only the header is read — a migration that fails to declare keeps the
    conservative meaning it had before kinds existed.
    """
    try:
        head = script.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return DEFAULT_KIND
    m = _KIND_RE.search(head)
    if not m:
        return DEFAULT_KIND
    kind = m.group(1)
    return kind if kind in KINDS else DEFAULT_KIND


def load_ledger(root: Path) -> dict[str, dict]:
    """Latest attempt per migration name, legacy flat file folded in.

    The legacy entries are seeded FIRST, so a real ledger line for the same
    name always wins — a clone that has both files reads its true history.
    """
    out: dict[str, dict] = {}

    legacy = root / LEGACY_FILENAME
    if legacy.exists():
        for raw in legacy.read_text(encoding="utf-8").splitlines():
            name = raw.strip()
            if name and not name.startswith("#"):
                out[name] = {
                    "name": name,
                    "kind": DEFAULT_KIND,
                    "rc": 0,
                    "outcome": "applied",
                    "ts": None,
                    "note": f"folded from {LEGACY_FILENAME}",
                }

    ledger = root / LEDGER_FILENAME
    if ledger.exists():
        for raw in ledger.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # A corrupt line is skipped, never fatal: a broken ledger must
                # not become a second way for the update channel to jam. Worst
                # case a migration re-runs, and every migration is idempotent.
                continue
            name = entry.get("name")
            if isinstance(name, str) and name:
                out[name] = entry

    return out


def record_attempt(
    root: Path,
    *,
    name: str,
    kind: str,
    rc: int,
    outcome: str,
    ts: str,
    note: str = "",
) -> None:
    """Append one attempt. Append-only: history is never rewritten."""
    entry = {
        "name": name,
        "kind": kind,
        "rc": rc,
        "outcome": outcome,
        "ts": ts,
        "note": note,
    }
    path = root / LEDGER_FILENAME
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def pending(root: Path, migrations_dir: Path) -> list[Path]:
    """Migrations still to run, in filename order.

    A name whose latest outcome is terminal (`applied`) is skipped. A `partial`
    heal is NOT terminal — it is retried, so a later, better repair reaches a
    clone that the earlier one could not finish.
    """
    done = {
        name
        for name, entry in load_ledger(root).items()
        if entry.get("outcome") in _TERMINAL_OUTCOMES
    }
    if not migrations_dir.is_dir():
        return []
    return [
        p
        for p in sorted(migrations_dir.glob("*.sh"))
        if p.name not in done
    ]
