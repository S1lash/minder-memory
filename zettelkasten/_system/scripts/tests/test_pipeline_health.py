"""«When did this pipeline last run» must never be the last line of the log.

Every test here pins the same defect from a different side. An append-only log
is not guaranteed to be in any order: `log_lint.md` holds a newest-first block
above an ascending legacy tail, so its FINAL header is seven weeks older than
its newest entry. Anything reading the last header concluded the pipeline had
been dead for fifty days while it delivered nightly — and the twelve days it
really was stopped hid inside that false number, because a surface already
reporting «56 days» cannot show a new outage.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parents[1]
sys.path.insert(0, str(_SCRIPTS))

import pipeline_health  # noqa: E402


# The real shape of log_lint.md: a descending block, then an ascending tail left
# behind when the convention flipped. Reduced to six entries; the trap is the
# same at any size.
MIXED_ORDER = """---
id: log-lint
---

# Lint Log

<!-- Entries append BELOW this line, newest first -->
## 2026-07-28T01:09:09Z | lint | by: minder:mem:lint | batch: lint-20260728-001

### Scans Executed
- clean

## 2026-07-27T01:07:47Z | lint | by: minder:mem:lint | batch: —

## 2026-07-26T01:11:29Z | lint | by: minder:mem:lint | batch: —

## 2026-05-22T01:10:26Z | lint | by: minder:mem:lint | batch: —

## 2026-06-05T01:21:13Z | lint | by: minder:mem:lint | batch: —

## 2026-06-08T01:05:00Z | lint | by: minder:mem:lint | batch: —

### Step 7.5 — resolve-clarifications dispatch
auto-resolve: applied 1, queued 1, vetoed 0.
"""


class MixedOrderLogTests(unittest.TestCase):
    def test_the_newest_entry_is_not_the_last_one_in_the_file(self):
        """The premise. If this ever stops holding, the rest is moot."""
        stamps = pipeline_health.timestamps(MIXED_ORDER)
        self.assertEqual(stamps[-1], "2026-06-08T01:05:00Z")
        self.assertEqual(max(stamps), "2026-07-28T01:09:09Z")
        self.assertNotEqual(stamps[-1], max(stamps))

    def test_last_run_takes_the_maximum(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log_lint.md"
            log.write_text(MIXED_ORDER, encoding="utf-8")
            row = pipeline_health.last_run(log)
            self.assertEqual(row["last_run"], "2026-07-28T01:09:09Z")
            self.assertEqual(row["entries"], 6)
            # Reported precisely so the discrepancy is visible, not silent.
            self.assertEqual(row["last_in_file_order"], "2026-06-08T01:05:00Z")

    def test_reordering_the_file_changes_nothing(self):
        """Order-agnostic by construction — no log has to be rewritten."""
        blocks = MIXED_ORDER.split("\n## ")
        head, entries = blocks[0], blocks[1:]
        shuffled = head + "\n## " + "\n## ".join(reversed(entries))
        self.assertEqual(max(pipeline_health.timestamps(shuffled)),
                         max(pipeline_health.timestamps(MIXED_ORDER)))


class HeaderShapeTests(unittest.TestCase):
    """All four shapes are real and in use; none of them is a contract."""

    CASES = [
        ("## 2026-07-28T01:09:09Z | lint | by: minder:mem:lint", "2026-07-28T01:09:09Z"),
        ("## 2026-08-08 — Processing: activitywatch metric-day", "2026-08-08T00:00:00Z"),
        ("## 2026-05-01 11:38:00Z — agent-lens run", "2026-05-01T11:38:00Z"),
        ("## 2026-08-06T23:10 — maintain", "2026-08-06T23:10:00Z"),
    ]

    def test_every_shape_in_use_is_read(self):
        for header, expected in self.CASES:
            with self.subTest(header=header):
                self.assertEqual(pipeline_health.timestamps(header), [expected])

    def test_prose_that_merely_mentions_a_date_is_not_a_run(self):
        text = "## 2026-07-28T01:09:09Z | lint\n\nfixed 31 records from 2026-06-25.\n"
        self.assertEqual(pipeline_health.timestamps(text), ["2026-07-28T01:09:09Z"])

    def test_a_log_with_no_entries_is_reported_as_such_not_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log_lint.md"
            log.write_text("---\nid: log-lint\n---\n\n# Lint Log\n", encoding="utf-8")
            row = pipeline_health.last_run(log)
            self.assertTrue(row["exists"])
            self.assertIsNone(row["last_run"])

    def test_a_missing_log_is_distinguishable_from_an_empty_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = pipeline_health.last_run(Path(tmp) / "log_lint.md")
            self.assertFalse(row["exists"])
            self.assertIsNone(row["last_run"])


class ReportTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        base = Path(tmp) / "zettelkasten"
        (base / "_system" / "state").mkdir(parents=True)
        (base / "_system" / "state" / "log_lint.md").write_text(MIXED_ORDER, encoding="utf-8")
        (base / "_system" / "state" / "log_process.md").write_text(
            "## 2026-08-08 — Processing: x\n\n## 2026-06-01 — Processing: y\n", encoding="utf-8")
        role = base / "_system" / "roles" / "minder-pm"
        role.mkdir(parents=True)
        (role / "log.jsonl").write_text(
            '{"ts": "2026-08-09T12:12:00Z", "outcome": "ok"}\n'
            '{"ts": "2026-08-08T10:00:00Z", "outcome": "idle"}\n', encoding="utf-8")
        (base / "_system" / "roles" / "_previous").mkdir()
        return base

    def test_report_covers_logs_and_roles_and_ages_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            now = datetime(2026, 8, 10, 9, 0, 0, tzinfo=timezone.utc)
            data = pipeline_health.report(base, now)

            self.assertEqual(data["pipelines"]["lint"]["last_run"], "2026-07-28T01:09:09Z")
            self.assertEqual(data["pipelines"]["lint"]["age_days"], 13.3)
            # The busiest log had the widest gap between the two readings.
            self.assertEqual(data["pipelines"]["process"]["last_run"], "2026-08-08T00:00:00Z")
            self.assertEqual(data["pipelines"]["process"]["last_in_file_order"],
                             "2026-06-01T00:00:00Z")
            self.assertEqual(data["roles"]["minder-pm"]["last_run"], "2026-08-09T12:12:00Z")
            # `_`-prefixed directories are engine files, never roles.
            self.assertNotIn("_previous", data["roles"])

    def test_a_pipeline_with_no_log_at_all_is_still_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            data = pipeline_health.report(base, datetime(2026, 8, 10, tzinfo=timezone.utc))
            self.assertIn("agent-lens", data["pipelines"])
            self.assertFalse(data["pipelines"]["agent-lens"]["exists"])

    def test_render_shows_the_naive_reading_when_it_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            text = pipeline_health.render(
                pipeline_health.report(base, datetime(2026, 8, 10, tzinfo=timezone.utc)))
            self.assertIn("last line in file says 2026-06-08", text)

    def test_cli_json_is_machine_readable_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            proc = subprocess.run(
                [sys.executable, str(_SCRIPTS / "pipeline_health.py"),
                 "--base", str(base), "--json", "--now", "2026-08-10T09:00:00Z"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(data["pipelines"]["lint"]["last_run"], "2026-07-28T01:09:09Z")


class RealBaseTests(unittest.TestCase):
    """The defect as it exists on this repository, not on a fixture."""

    def test_this_bases_lint_log_still_carries_the_trap(self):
        base = _THIS.parents[3]
        log = base / "_system" / "state" / "log_lint.md"
        if not log.is_file():
            self.skipTest("no owner data in this checkout")
        row = pipeline_health.last_run(log)
        if not row["entries"]:
            # The engine SHIPS this file as a header with no rows, so presence
            # is not evidence of runs. Guarding on the file alone made every
            # fresh clone fail this test on day one — found by running the
            # suite inside a built skeleton.
            self.skipTest("log present but carries no runs — nothing to order")
        self.assertIsNotNone(row["last_run"])
        # Not asserting the specific dates — they move. Asserting that the
        # helper does not agree with the naive reading is the durable claim,
        # and it is what every reader before this module got wrong.
        self.assertGreaterEqual(row["last_run"], row["last_in_file_order"])


if __name__ == "__main__":
    unittest.main()
