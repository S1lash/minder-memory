"""Tests for record_decision_run.py — substrate append correctness.

Covers happy-path run + followup, sensitive redaction, mechanical
caller class auto-detect via --from-pipeline, orphan followup
rejection, malformed run_id rejection, optional fields default to
null when absent, failed-status runs accepted with partial fields.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests._fixture import clear_minder_memory_env, make_fixture  # type: ignore
import record_decision_run as et  # type: ignore


VALID_RUN_ID = "2026-05-03T12:34:56Z-abcdef01"
SECOND_RUN_ID = "2026-05-03T13:00:00Z-deadbeef"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(ln)
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _common_run_args(jsonl: Path, run_id: str = VALID_RUN_ID) -> list[str]:
    return [
        "--kind", "run",
        "--run-id", run_id,
        "--jsonl", str(jsonl),
        "--status", "ok",
        "--working-dir", "/tmp/agent-repo",
        "--situation", "test situation about whether to do X",
        "--tree-size", "47",
        "--verdict", "aligned",
        "--citations", '[{"id":"axiom-identity-001","relation":"aligned"}]',
        "--tradeoffs", "[]",
        "--rationale", "test rationale",
        "--no-commit",
    ]


class VerdictEnum(unittest.TestCase):
    """`no-basis` is a distinct verdict, and the enum is what enforces it.

    Downstream skills route the two silences oppositely: `/minder:mem:resolve-
    clarifications` promotes a `no-match` candidate to auto-apply and holds a
    `no-basis` one in the queue. If the enum ever loses `no-basis`, the skill
    that emits it fails closed here rather than silently degrading to the
    verdict that reads an empty constitution as approval.
    """

    def test_no_basis_is_accepted_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            args = _common_run_args(jsonl)
            args[args.index("--verdict") + 1] = "no-basis"
            args[args.index("--tree-size") + 1] = "0"
            args[args.index("--citations") + 1] = "[]"
            rc = et.main(args)
            self.assertEqual(rc, 0)
            entry = _read(jsonl)[0]
            self.assertEqual(entry["verdict"], "no-basis")
            self.assertEqual(entry["tree_size"], 0)
            self.assertEqual(entry["citations"], [])

    def test_no_match_still_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            args = _common_run_args(jsonl)
            args[args.index("--verdict") + 1] = "no-match"
            args[args.index("--citations") + 1] = "[]"
            self.assertEqual(et.main(args), 0)
            self.assertEqual(_read(jsonl)[0]["verdict"], "no-match")

    def test_both_silences_are_expectable_verdicts(self):
        for verdict in ("no-basis", "no-match"):
            with self.subTest(verdict=verdict):
                self.assertIn(verdict, et.EXPECTED_VERDICTS)

    def test_unknown_verdict_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            args = _common_run_args(jsonl)
            args[args.index("--verdict") + 1] = "no-opinion"
            with self.assertRaises(SystemExit):
                et.main(args)


class EmitTelemetryRunMode(unittest.TestCase):
    def test_happy_path_run_writes_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            rc = et.main(_common_run_args(jsonl) + [
                "--intent", "checking before action",
                "--pre-confidence", "low",
                "--expected-verdict", "aligned",
            ])
            self.assertEqual(rc, 0)
            entries = _read(jsonl)
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry["kind"], "run")
            self.assertEqual(entry["run_id"], VALID_RUN_ID)
            self.assertEqual(entry["caller_class"], "judgmental")
            self.assertEqual(entry["status"], "ok")
            self.assertEqual(entry["verdict"], "aligned")
            self.assertEqual(entry["tree_size"], 47)
            self.assertIn("situation_text", entry)
            self.assertIn("rationale", entry)
            self.assertEqual(entry["intent"], "checking before action")
            self.assertEqual(entry["pre_confidence"], "low")
            self.assertEqual(
                entry["situation_hash"],
                hashlib.sha256(
                    "test situation about whether to do X".encode("utf-8")
                ).hexdigest(),
            )
        clear_minder_memory_env()

    def test_optional_self_report_defaults_to_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            et.main(_common_run_args(jsonl))
            entry = _read(jsonl)[0]
            self.assertIsNone(entry["intent"])
            self.assertIsNone(entry["pre_confidence"])
            self.assertIsNone(entry["expected_verdict"])
            self.assertIsNone(entry["from_pipeline"])
        clear_minder_memory_env()

    def test_mechanical_caller_class_via_from_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            et.main(_common_run_args(jsonl) + [
                "--from-pipeline", "/minder:mem:process",
            ])
            entry = _read(jsonl)[0]
            self.assertEqual(entry["caller_class"], "mechanical")
            self.assertEqual(entry["from_pipeline"], "/minder:mem:process")
        clear_minder_memory_env()

    def test_unknown_pipeline_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            with self.assertRaises(SystemExit):
                et.main(_common_run_args(jsonl) + [
                    "--from-pipeline", "/minder:mem:not-a-real-pipeline",
                ])
        clear_minder_memory_env()

    def test_sensitive_omits_text_and_rationale_keeps_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            et.main(_common_run_args(jsonl) + ["--is-sensitive"])
            entry = _read(jsonl)[0]
            self.assertTrue(entry["is_sensitive"])
            self.assertNotIn("situation_text", entry)
            self.assertNotIn("rationale", entry)
            self.assertIn("situation_hash", entry)
            self.assertEqual(entry["verdict"], "aligned")
            self.assertEqual(
                entry["citations"],
                [{"id": "axiom-identity-001", "relation": "aligned"}],
            )
        clear_minder_memory_env()

    def test_malformed_run_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            with self.assertRaises(SystemExit):
                et.main([
                    "--kind", "run",
                    "--run-id", "not-a-valid-id",
                    "--jsonl", str(jsonl),
                    "--status", "ok",
                    "--situation", "x",
                    "--no-commit",
                ])
        clear_minder_memory_env()

    def test_failed_status_run_accepts_missing_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            rc = et.main([
                "--kind", "run",
                "--run-id", VALID_RUN_ID,
                "--jsonl", str(jsonl),
                "--status", "failed_regen",
                "--working-dir", "/tmp/x",
                "--situation", "doomed-situation",
                "--no-commit",
            ])
            self.assertEqual(rc, 0)
            entry = _read(jsonl)[0]
            self.assertEqual(entry["status"], "failed_regen")
            self.assertIsNone(entry["verdict"])
            self.assertEqual(entry["citations"], [])
            self.assertIsNone(entry["tree_size"])
        clear_minder_memory_env()

    def test_situation_text_truncated_to_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            long_situation = "X" * 500
            args = _common_run_args(jsonl)
            args[args.index("--situation") + 1] = long_situation
            et.main(args)
            entry = _read(jsonl)[0]
            self.assertEqual(
                len(entry["situation_text"]),
                et.SITUATION_TEXT_CAP,
            )
            # Hash uses the FULL situation, not truncated.
            self.assertEqual(
                entry["situation_hash"],
                hashlib.sha256(long_situation.encode("utf-8")).hexdigest(),
            )
        clear_minder_memory_env()


class EmitTelemetryFollowupMode(unittest.TestCase):
    def test_followup_appended_with_existing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            et.main(_common_run_args(jsonl))
            rc = et.main([
                "--kind", "followup",
                "--run-id", VALID_RUN_ID,
                "--jsonl", str(jsonl),
                "--post-confidence", "high",
                "--decision-taken", "did the right thing",
                "--human-needed-after", "false",
                "--verdict-resolved", "true",
                "--no-commit",
            ])
            self.assertEqual(rc, 0)
            entries = _read(jsonl)
            self.assertEqual(len(entries), 2)
            f = entries[1]
            self.assertEqual(f["kind"], "followup")
            self.assertEqual(f["run_id"], VALID_RUN_ID)
            self.assertEqual(f["post_confidence"], "high")
            self.assertTrue(f["verdict_resolved"])
            self.assertFalse(f["human_needed_after"])
        clear_minder_memory_env()

    def test_orphan_followup_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            et.main(_common_run_args(jsonl, run_id=VALID_RUN_ID))
            with self.assertRaises(SystemExit):
                et.main([
                    "--kind", "followup",
                    "--run-id", SECOND_RUN_ID,  # never written
                    "--jsonl", str(jsonl),
                    "--post-confidence", "high",
                    "--decision-taken", "x",
                    "--human-needed-after", "false",
                    "--verdict-resolved", "true",
                    "--no-commit",
                ])
        clear_minder_memory_env()

    def test_followup_rejected_when_substrate_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            missing = fx.system / "state" / "check-decision-runs.jsonl"
            with self.assertRaises(SystemExit):
                et.main([
                    "--kind", "followup",
                    "--run-id", VALID_RUN_ID,
                    "--jsonl", str(missing),
                    "--post-confidence", "high",
                    "--decision-taken", "x",
                    "--human-needed-after", "false",
                    "--verdict-resolved", "true",
                    "--no-commit",
                ])
        clear_minder_memory_env()

    def test_followup_inherits_caller_class_for_commit_decision(self):
        # Followup-line commit decision is based on the original run's
        # caller_class, not on the followup invocation itself. Mechanical
        # original → followup commit also skipped.
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            et.main(_common_run_args(jsonl) + [
                "--from-pipeline", "/minder:mem:process",
            ])
            cc = et._lookup_run_caller_class(jsonl, VALID_RUN_ID)
            self.assertEqual(cc, "mechanical")
        clear_minder_memory_env()


class EmitTelemetryAppendOnly(unittest.TestCase):
    def test_multiple_runs_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            jsonl = fx.system / "state" / "check-decision-runs.jsonl"
            run_ids = [
                "2026-05-03T12:00:00Z-aaaaaaaa",
                "2026-05-03T12:00:01Z-bbbbbbbb",
                "2026-05-03T12:00:02Z-cccccccc",
            ]
            for rid in run_ids:
                et.main(_common_run_args(jsonl, run_id=rid))
            entries = _read(jsonl)
            self.assertEqual([e["run_id"] for e in entries], run_ids)


if __name__ == "__main__":
    unittest.main()
