"""Tests for resolve_session writers (session log + history.jsonl)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import resolve_session as rs  # type: ignore


class _BaseSetup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "zettelkasten"
        (self.base / "_system/state").mkdir(parents=True)
        os.environ["MINDER_MEMORY_BASE"] = str(self.base)

    def tearDown(self) -> None:
        os.environ.pop("MINDER_MEMORY_BASE", None)
        self._tmp.cleanup()


class SessionLogTests(_BaseSetup):
    def test_minimal_auto_session_writes_frontmatter_and_auto_section(self):
        state = rs.new_session(mode="auto", trigger="lint")
        state.items_total = 2
        state.auto_applied.append({
            "type": "wikilink_add",
            "summary": "[[a]] ↔ [[b]]",
            "source_lens": "cross-domain-bridge/2026-05-04",
            "targets": ["2_areas/personal/a.md", "2_areas/work/b.md"],
            "reasoning": "high precedent + clean constitution",
        })
        path = rs.write_session_log(state)
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn(f"session_id: {state.sid}", text)
        self.assertIn("mode: auto", text)
        self.assertIn("trigger: lint", text)
        self.assertIn("items_auto_applied: 1", text)
        self.assertIn("origin: personal", text)
        self.assertIn("is_sensitive: true", text)
        self.assertIn("## Auto-applied", text)
        self.assertIn("[[a]] ↔ [[b]]", text)

    def test_interactive_session_renders_owner_decisions(self):
        state = rs.new_session(mode="interactive", trigger="owner")
        state.owner_decisions.append({
            "type": "hub_stub_create",
            "source_lens": "knowledge-emergence/2026-05-04",
            "proposal": "hub-inner-work over 8 notes",
            "smart_reasoning": "tight cluster, no overlap",
            "decision": "approve",
            "applied_target": "5_meta/mocs/hub-inner-work.md",
            "inferred_pattern": "Owner approves when cluster tight, no overlap",
        })
        state.items_total = 1
        path = rs.write_session_log(state)
        text = path.read_text(encoding="utf-8")
        self.assertIn("items_owner_approved: 1", text)
        self.assertIn("## Owner decisions", text)
        self.assertIn("**Owner action:** approve", text)
        self.assertIn("**Inferred pattern:**", text)

    def test_constitution_veto_renders_when_present(self):
        state = rs.new_session(mode="auto", trigger="lint")
        state.constitution_vetoed.append({
            "type": "hub_stub_create",
            "summary": "hub-Y",
            "veto_reason": "SOUL marks topic as currently being processed",
        })
        path = rs.write_session_log(state)
        text = path.read_text(encoding="utf-8")
        self.assertIn("## Constitution-vetoed", text)
        self.assertIn("Veto reason: SOUL marks", text)


class HistoryJsonlTests(_BaseSetup):
    def test_append_then_read_roundtrip(self):
        entry = {
            "ts": "2026-05-05T10:32:00Z",
            "session_ref": "_system/state/resolve-sessions/2026-05-05-abc.md",
            "class_key": rs.class_key("knowledge-emergence", "hub_stub_create", "medium"),
            "decision": "approve",
            "proposal_summary": "create hub-inner-work from 8 notes",
            "salient_features": {"cluster_tightness": 0.7, "time_span_months": 4},
        }
        rs.append_history(entry)
        rows = rs.read_history()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["class_key"], "knowledge-emergence__hub_stub_create__medium")

    def test_append_rejects_missing_required_field(self):
        with self.assertRaises(ValueError):
            rs.append_history({"ts": "2026-05-05T10:32:00Z"})

    def test_recent_n_truncates(self):
        for i in range(5):
            rs.append_history({
                "ts": f"2026-05-0{i+1}T00:00:00Z",
                "session_ref": "x",
                "class_key": f"k{i}",
                "decision": "approve",
                "proposal_summary": "p",
                "salient_features": {},
            })
        rows = rs.read_history(recent_n=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["class_key"], "k4")

    def test_tolerates_corrupt_line(self):
        rs.append_history({
            "ts": "1", "session_ref": "x", "class_key": "k",
            "decision": "approve", "proposal_summary": "p", "salient_features": {},
        })
        with rs.history_jsonl_path().open("a", encoding="utf-8") as f:
            f.write("not-json\n")
        rs.append_history({
            "ts": "2", "session_ref": "x", "class_key": "k2",
            "decision": "reject", "proposal_summary": "p", "salient_features": {},
        })
        rows = rs.read_history()
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["class_key"] for r in rows], ["k", "k2"])


class ClassKeyTests(unittest.TestCase):
    def test_canonical_format(self):
        self.assertEqual(
            rs.class_key("cross-domain-bridge", "wikilink_add", "high"),
            "cross-domain-bridge__wikilink_add__high",
        )


if __name__ == "__main__":
    unittest.main()
