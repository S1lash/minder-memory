"""Tests for lens_action_handlers validation contract.

Phase 1 ships validators only; appliers return `{not_implemented}` when
validation passes. These tests pin the validation behaviour end-to-end
on a synthesised Minder Memory base.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import lens_action_handlers as h  # type: ignore


def _make_base(tmp: Path) -> Path:
    base = tmp / "zettelkasten"
    for sub in (
        "_records/meetings",
        "1_projects",
        "2_areas/personal",
        "2_areas/work",
        "5_meta/mocs",
        "_system/state",
    ):
        (base / sub).mkdir(parents=True)
    # Empty OPEN_THREADS so substring check passes by default.
    (base / "_system/state/OPEN_THREADS.md").write_text("# Open threads\n", encoding="utf-8")
    return base


def _write(base: Path, rel: str, body: str = "stub\n") -> Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class WikilinkAddTests(unittest.TestCase):
    def test_passes_when_both_exist_and_no_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "2_areas/personal/a.md")
            _write(base, "2_areas/work/b.md")
            ok, reason = h.validate_wikilink_add(
                {"note_a": "2_areas/personal/a.md", "note_b": "2_areas/work/b.md"},
                base=base,
            )
            self.assertTrue(ok, reason)

    def test_fails_when_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "2_areas/personal/a.md")
            ok, reason = h.validate_wikilink_add(
                {"note_a": "2_areas/personal/a.md", "note_b": "2_areas/work/missing.md"},
                base=base,
            )
            self.assertFalse(ok)
            self.assertIn("note_b does not exist", reason)

    def test_fails_when_already_bidirectional(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "2_areas/personal/a.md", "links: [[b]]\n")
            _write(base, "2_areas/work/b.md", "links: [[a]]\n")
            ok, reason = h.validate_wikilink_add(
                {"note_a": "2_areas/personal/a.md", "note_b": "2_areas/work/b.md"},
                base=base,
            )
            self.assertFalse(ok)
            self.assertIn("already bidirectional", reason)

    def test_fails_when_same_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "2_areas/personal/a.md")
            ok, _ = h.validate_wikilink_add(
                {"note_a": "2_areas/personal/a.md", "note_b": "2_areas/personal/a.md"},
                base=base,
            )
            self.assertFalse(ok)


class HubStubCreateTests(unittest.TestCase):
    def test_passes_for_new_slug_with_existing_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "2_areas/personal/a.md")
            _write(base, "2_areas/personal/b.md")
            ok, reason = h.validate_hub_stub_create(
                {
                    "suggested_slug": "hub-inner-work",
                    "cited_notes": ["2_areas/personal/a.md", "2_areas/personal/b.md"],
                },
                base=base,
            )
            self.assertTrue(ok, reason)

    def test_fails_when_hub_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "2_areas/personal/a.md")
            _write(base, "5_meta/mocs/hub-existing.md")
            ok, reason = h.validate_hub_stub_create(
                {"suggested_slug": "hub-existing", "cited_notes": ["2_areas/personal/a.md"]},
                base=base,
            )
            self.assertFalse(ok)
            self.assertIn("hub already exists", reason)

    def test_fails_for_bad_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "2_areas/personal/a.md")
            ok, reason = h.validate_hub_stub_create(
                {"suggested_slug": "Hub With Spaces", "cited_notes": ["2_areas/personal/a.md"]},
                base=base,
            )
            self.assertFalse(ok)
            self.assertIn("slug not in lowercase-kebab", reason)

    def test_fails_for_missing_cited_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            ok, reason = h.validate_hub_stub_create(
                {"suggested_slug": "hub-x", "cited_notes": ["2_areas/personal/missing.md"]},
                base=base,
            )
            self.assertFalse(ok)
            self.assertIn("cited note does not exist", reason)


class OpenThreadAddTests(unittest.TestCase):
    def test_passes_for_fresh_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "_records/meetings/m.md")
            ok, reason = h.validate_open_thread_add(
                {
                    "thread_title": "Office relocation decision",
                    "cited_records": ["_records/meetings/m.md"],
                },
                base=base,
            )
            self.assertTrue(ok, reason)

    def test_fails_when_title_already_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "_records/meetings/m.md")
            (base / "_system/state/OPEN_THREADS.md").write_text(
                "## Active\n- Office relocation decision — owner@2026-04-01\n",
                encoding="utf-8",
            )
            ok, reason = h.validate_open_thread_add(
                {
                    "thread_title": "Office relocation decision",
                    "cited_records": ["_records/meetings/m.md"],
                },
                base=base,
            )
            self.assertFalse(ok)
            self.assertIn("already in OPEN_THREADS", reason)


class DecisionUpdateSectionTests(unittest.TestCase):
    def test_passes_when_no_section_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "1_projects/decision-x.md", "# Decision X\n\n## Update 2026-01-01\nold\n")
            ok, reason = h.validate_decision_update_section(
                {"decision_note_path": "1_projects/decision-x.md", "update_reason": "new info"},
                base=base,
            )
            self.assertTrue(ok, reason)

    def test_fails_when_today_section_present(self):
        from datetime import date
        today = date.today().isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            _write(base, "1_projects/decision-x.md", f"# Decision X\n\n## Update {today}\nfresh\n")
            ok, reason = h.validate_decision_update_section(
                {"decision_note_path": "1_projects/decision-x.md", "update_reason": "new info"},
                base=base,
            )
            self.assertFalse(ok)
            self.assertIn("already present", reason)


class DispatchTableTests(unittest.TestCase):
    def test_validators_match_whitelist(self):
        from _common import ACTION_HINT_TYPES  # type: ignore
        self.assertEqual(set(h.VALIDATORS), set(ACTION_HINT_TYPES))
        self.assertEqual(set(h.APPLIERS), set(ACTION_HINT_TYPES))

    def test_applier_returns_validation_failure_when_input_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            # Only one note exists — wikilink validation must fail.
            _write(base, "2_areas/personal/a.md")
            out = h.apply_wikilink_add(
                {"note_a": "2_areas/personal/a.md", "note_b": "2_areas/work/missing.md"},
                source_lens="cross-domain-bridge/2026-05-04",
                base=base,
            )
            self.assertFalse(out["success"])
            self.assertFalse(out["applied"])
            self.assertIn("note_b does not exist", out["reason"])
            self.assertEqual(out["from_lens"], "cross-domain-bridge/2026-05-04")


if __name__ == "__main__":
    unittest.main()
