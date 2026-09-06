"""Tests for the migration ledger and runner.

The defect these pin: `sync_engine.sh` used to run each migration under
`set -e` and record its name only AFTER success, so a failing migration both
aborted the update AND stayed unrecorded — every future `/minder:mem:update` re-ran it
and re-aborted at the same point. A friend's clone was stuck that way for weeks
on `007`, a best-effort repair of historical data that can legitimately fail.

A repair of old data must never be able to block a future engine update. These
tests hold that property, plus the backward compatibility that lets a clone
carrying the old flat marker file keep its history.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib import migrations as m  # noqa: E402
import run_migrations as runner  # noqa: E402


STRUCTURAL = "#!/usr/bin/env bash\n# migration-kind: structural\nexit {rc}\n"
HEAL = "#!/usr/bin/env bash\n# migration-kind: heal\nexit {rc}\n"
UNDECLARED = "#!/usr/bin/env bash\nexit {rc}\n"


def _write(d: Path, name: str, body: str, rc: int = 0) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(body.format(rc=rc))
    return p


class DeclaredKindTests(unittest.TestCase):
    def test_reads_the_header(self, ):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertEqual(m.declared_kind(_write(d, "a.sh", HEAL)), "heal")
            self.assertEqual(m.declared_kind(_write(d, "b.sh", STRUCTURAL)), "structural")

    def test_undeclared_defaults_to_structural(self):
        """Nothing silently changes meaning when a migration omits the header."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = _write(Path(tmp), "c.sh", UNDECLARED)
            self.assertEqual(m.declared_kind(p), "structural")

    def test_unknown_kind_falls_back_to_structural(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = _write(Path(tmp), "d.sh", "#!/usr/bin/env bash\n# migration-kind: vibes\n")
            self.assertEqual(m.declared_kind(p), "structural")

    def test_every_shipped_migration_declares_a_kind(self):
        """A shipped migration with no header is a silent structural default."""
        d = REPO_ROOT / "scripts" / "migrations"
        undeclared = [
            p.name for p in sorted(d.glob("*.sh"))
            if "# migration-kind:" not in p.read_text(encoding="utf-8")[:4000]
        ]
        self.assertEqual(undeclared, [])


class LedgerTests(unittest.TestCase):
    def test_legacy_flat_file_is_folded_in(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / m.LEGACY_FILENAME).write_text("001-a.sh\n002-b.sh\n", encoding="utf-8")
            ledger = m.load_ledger(root)
            self.assertEqual(set(ledger), {"001-a.sh", "002-b.sh"})
            self.assertEqual(ledger["001-a.sh"]["outcome"], "applied")

    def test_real_ledger_line_wins_over_legacy(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / m.LEGACY_FILENAME).write_text("007-x.sh\n", encoding="utf-8")
            m.record_attempt(root, name="007-x.sh", kind="heal", rc=1,
                             outcome="partial", ts="2026-08-07T00:00:00Z")
            self.assertEqual(m.load_ledger(root)["007-x.sh"]["outcome"], "partial")

    def test_corrupt_ledger_line_is_skipped_not_fatal(self):
        """A broken ledger must not become a second way to jam the channel."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / m.LEDGER_FILENAME).write_text(
                'not json\n{"name":"002-b.sh","outcome":"applied"}\n', encoding="utf-8"
            )
            self.assertEqual(set(m.load_ledger(root)), {"002-b.sh"})

    def test_partial_heal_is_retried_applied_is_not(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "migrations"
            _write(d, "001-a.sh", HEAL)
            _write(d, "002-b.sh", HEAL)
            m.record_attempt(root, name="001-a.sh", kind="heal", rc=0,
                             outcome="applied", ts="2026-08-07T00:00:00Z")
            m.record_attempt(root, name="002-b.sh", kind="heal", rc=1,
                             outcome="partial", ts="2026-08-07T00:00:00Z")
            self.assertEqual([p.name for p in m.pending(root, d)], ["002-b.sh"])


class RunnerTests(unittest.TestCase):
    def test_failing_heal_records_partial_and_does_not_block(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "migrations"
            _write(d, "001-heal.sh", HEAL, rc=1)
            _write(d, "002-after.sh", STRUCTURAL, rc=0)

            result = runner.run(root, d, dry_run=False)

            self.assertIsNone(result["aborted_on"], "a heal failure must not abort")
            self.assertEqual(result["failed_heal"], ["001-heal.sh"])
            outcomes = {e["name"]: e["outcome"] for e in result["ran"]}
            self.assertEqual(outcomes["001-heal.sh"], "partial")
            self.assertEqual(outcomes["002-after.sh"], "applied",
                             "migrations after a failed heal must still run")

    def test_failing_structural_aborts_and_records_nothing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "migrations"
            _write(d, "001-struct.sh", STRUCTURAL, rc=1)
            _write(d, "002-after.sh", HEAL, rc=0)

            result = runner.run(root, d, dry_run=False)

            self.assertEqual(result["aborted_on"]["name"], "001-struct.sh")
            self.assertEqual(result["ran"], [], "nothing is recorded on a structural abort")
            # Unrecorded means the next update resumes at exactly this migration.
            self.assertEqual([p.name for p in m.pending(root, d)],
                             ["001-struct.sh", "002-after.sh"])

    def test_a_stuck_heal_never_blocks_a_later_update(self):
        """The whole point: 007's failure mode, replayed across two updates."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "migrations"
            _write(d, "007-heal.sh", HEAL, rc=1)

            first = runner.run(root, d, dry_run=False)
            self.assertIsNone(first["aborted_on"])

            # A newer migration ships later; the stuck heal must not eat it.
            _write(d, "008-new.sh", STRUCTURAL, rc=0)
            second = runner.run(root, d, dry_run=False)
            self.assertIsNone(second["aborted_on"])
            self.assertIn("008-new.sh", {e["name"] for e in second["ran"]})

    def test_dry_run_writes_no_ledger(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "migrations"
            _write(d, "001-a.sh", HEAL)
            runner.run(root, d, dry_run=True)
            self.assertFalse((root / m.LEDGER_FILENAME).exists())

    def test_cli_json_is_parseable(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "run_migrations.py"),
             "--dry-run", "--json"],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertIn("pending", payload)


if __name__ == "__main__":
    unittest.main()
