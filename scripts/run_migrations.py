#!/usr/bin/env python3
"""Run pending engine migrations, honouring each one's declared kind.

The runner half of the migration contract; the ledger half is
`scripts/lib/migrations.py`, which explains why a kind exists at all. In short:
a best-effort repair of historical data must never be able to block a future
engine update, and under the previous bash loop it could — permanently.

Behaviour:

  * `structural` failure — abort immediately, record nothing. The migration
    re-runs on the next update, exactly as before. Exit 1.
  * `heal` failure — record `partial`, print the failure, keep going. The
    migration is retried next update, so an improved repair shipped later
    reaches the clone by itself. Exit 0 overall.
  * success — record `applied`; never runs again.

Lives in python rather than in `sync_engine.sh` for two reasons: the logic is
identical on every platform without a single bash-3.2 or Git-Bash caveat, and
it is testable. `sync_engine.sh` and the `/minder:mem:update` skill both call this one
entrypoint, so there is a single owner of "what has run here".

Usage:
  python3 scripts/run_migrations.py                 # run everything pending
  python3 scripts/run_migrations.py --dry-run       # list pending + kinds
  python3 scripts/run_migrations.py --json          # machine-readable result
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.migrations import declared_kind, pending, record_attempt  # noqa: E402
from lib.manifest import repo_root  # noqa: E402
from lib.portable import configure_stdout  # noqa: E402

MIGRATIONS_DIRNAME = "scripts/migrations"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(root: Path, migrations_dir: Path, *, dry_run: bool) -> dict:
    todo = pending(root, migrations_dir)
    result: dict = {"ran": [], "failed_heal": [], "aborted_on": None, "pending": len(todo)}

    if not todo:
        return result

    for script in todo:
        kind = declared_kind(script)
        if dry_run:
            result["ran"].append({"name": script.name, "kind": kind, "outcome": "would-run"})
            continue

        # Flush before handing the terminal to a subprocess: python buffers its
        # stdout when it is a pipe, the migration's does not, and without this
        # every label lands after every migration's output — labels that no
        # longer label anything.
        print(f"  > {script.name} [{kind}]", flush=True)
        sys.stderr.flush()
        # `bash <path>`, never the executable bit — Windows checkouts have none.
        try:
            rc = subprocess.run(["bash", str(script)], cwd=str(root)).returncode
        except OSError as exc:
            # No `bash` on PATH is an environment problem, not a migration
            # problem. A traceback here would read as "the migration is broken"
            # and send the owner to the wrong file.
            print(
                f"  ! cannot run migrations: {exc}. `bash` must be on PATH "
                f"(Git Bash on Windows, the system shell elsewhere).",
                file=sys.stderr,
            )
            result["aborted_on"] = {"name": script.name, "kind": kind, "rc": -1}
            return result

        if rc == 0:
            record_attempt(
                root, name=script.name, kind=kind, rc=0, outcome="applied", ts=_now()
            )
            result["ran"].append({"name": script.name, "kind": kind, "outcome": "applied"})
            continue

        if kind == "heal":
            note = (
                "best-effort repair did not fully succeed; the update continued "
                "and this migration will be retried on the next one"
            )
            record_attempt(
                root, name=script.name, kind=kind, rc=rc, outcome="partial", ts=_now(), note=note
            )
            result["ran"].append({"name": script.name, "kind": kind, "outcome": "partial", "rc": rc})
            result["failed_heal"].append(script.name)
            print(
                f"  ! {script.name} exited {rc}. It is a repair of existing data, not a "
                f"change to the engine's shape, so the update continues.",
                file=sys.stderr,
            )
            continue

        # structural: the engine's shape is wrong without it. Abort, record
        # nothing, so the next update retries from exactly here.
        result["aborted_on"] = {"name": script.name, "kind": kind, "rc": rc}
        print(
            f"  ! {script.name} exited {rc} and is structural — aborting the update.\n"
            f"    Nothing after it ran, and it is not recorded, so the next update "
            f"resumes at this migration.",
            file=sys.stderr,
        )
        return result

    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run pending engine migrations")
    ap.add_argument("--dir", default=MIGRATIONS_DIRNAME, help="migrations directory (repo-relative)")
    ap.add_argument("--dry-run", action="store_true", help="list what would run")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = ap.parse_args(argv)

    configure_stdout()
    root = repo_root()
    result = run(root, root / args.dir, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif not result["ran"]:
        print("  (none pending)")

    if result["aborted_on"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
