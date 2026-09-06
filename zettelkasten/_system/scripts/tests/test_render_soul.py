"""Tests for render_soul_values.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import (  # type: ignore
    CLARIFICATIONS_TEMPLATE,
    SOUL_TEMPLATE,
    VALID_NOTE,
    VALID_PERSONAL_NOTE,
    VALID_PLACEHOLDER_CORE,
    VALID_SENSITIVE_NOTE,
    clear_minder_memory_env,
    make_fixture,
)
import render_soul_values as r  # type: ignore


class RenderSoulTests(unittest.TestCase):
    def test_writes_between_markers_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            rc = r.main(["--soul", str(soul_path)])
            self.assertEqual(rc, 0)
            text = soul_path.read_text(encoding="utf-8")
            self.assertIn("Hand-written focus area.", text)
            self.assertIn("Hand-written style area.", text)
            self.assertIn(r.SOUL_MARKER_START, text)
            self.assertIn(r.SOUL_MARKER_END, text)
            self.assertIn("If it can be better", text)
        clear_minder_memory_env()

    def test_sensitive_scope_is_included_in_dogfood(self):
        """Single-user dogfood: SOUL.Values loads all three scopes."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            sensitive_core = VALID_SENSITIVE_NOTE.replace(
                "core: false", "core: true"
            )
            fx.write_principle("rule/health/001.md", sensitive_core)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            rc = r.main(["--soul", str(soul_path)])
            self.assertEqual(rc, 0)
            self.assertIn("work email", soul_path.read_text(encoding="utf-8").lower())
        clear_minder_memory_env()

    def test_placeholder_never_in_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/meta/001.md", VALID_PLACEHOLDER_CORE)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            rc = r.main(["--soul", str(soul_path)])
            self.assertEqual(rc, 0)
            text = soul_path.read_text(encoding="utf-8")
            self.assertNotIn("Placeholder content never ships.", text)
        clear_minder_memory_env()

    def test_missing_markers_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            soul_path = fx.write_system_file(
                "SOUL.md", "# SOUL\n\nNo markers at all.\n"
            )
            with self.assertRaises(SystemExit) as ctx_mgr:
                r.main(["--soul", str(soul_path)])
            self.assertNotEqual(ctx_mgr.exception.code, 0)
        clear_minder_memory_env()

    def test_duplicate_marker_pair_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            double = (
                "# SOUL\n"
                f"{r.SOUL_MARKER_START}\nfirst\n{r.SOUL_MARKER_END}\n"
                f"{r.SOUL_MARKER_START}\nsecond\n{r.SOUL_MARKER_END}\n"
            )
            soul_path = fx.write_system_file("SOUL.md", double)
            with self.assertRaises(SystemExit):
                r.main(["--soul", str(soul_path)])
        clear_minder_memory_env()

    def test_drift_triggers_clarification_when_opted_in(self):
        """Realistic flow: initial render establishes source hash, then user
        hand-edits the auto-zone while leaving source untouched, then
        re-render must detect drift (not refresh)."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            clar_path = fx.write_system_file(
                "CLARIFICATIONS.md", CLARIFICATIONS_TEMPLATE
            )
            # Step 1: initial render — establishes source hash in auto-zone.
            rc = r.main(["--soul", str(soul_path)])
            self.assertEqual(rc, 0)
            # Step 2: user hand-edits the auto-zone body (keeping the markers
            # and the auto-generated source-hash comment intact).
            rendered = soul_path.read_text(encoding="utf-8")
            tampered = rendered.replace(
                "If it can be better, it should be better",
                "HAND EDITED BY USER, NOT GENERATED",
            )
            soul_path.write_text(tampered, encoding="utf-8")
            # Step 3: re-render — source hash unchanged, body differs → drift.
            rc = r.main([
                "--soul", str(soul_path),
                "--write-clarification",
                "--clarifications", str(clar_path),
            ])
            self.assertEqual(rc, 0)
            self.assertIn("soul-manual-edit-to-auto-zone", clar_path.read_text(encoding="utf-8"))
        clear_minder_memory_env()

    def test_source_change_is_not_drift(self):
        """Refreshing after editing a principle under 0_constitution/ must
        NOT be reported as drift, even though the auto-zone content
        changes."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            principle_path = fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            clar_path = fx.write_system_file(
                "CLARIFICATIONS.md", CLARIFICATIONS_TEMPLATE
            )
            # Initial render
            r.main(["--soul", str(soul_path)])
            # Edit the source principle (legit change, not auto-zone hand-edit)
            principle_path.write_text(
                principle_path.read_text(encoding="utf-8").replace(
                    "If it can be better, it should be better",
                    "If it can be better, it must be better",
                ),
                encoding="utf-8",
            )
            # Re-render with clarification logging enabled
            r.main([
                "--soul", str(soul_path),
                "--write-clarification",
                "--clarifications", str(clar_path),
            ])
            # No drift CLARIFICATION should have been written
            self.assertNotIn("soul-manual-edit-to-auto-zone", clar_path.read_text(encoding="utf-8"))
        clear_minder_memory_env()

    def test_trailing_whitespace_is_not_drift(self):
        """Editors that add trailing spaces shouldn't trigger drift."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            # First run: clean render
            r.main(["--soul", str(soul_path)])
            text = soul_path.read_text(encoding="utf-8")
            # Append trailing spaces to a few lines inside the auto-zone
            noisy = "\n".join(
                line + "   " if line.startswith("- **If") else line
                for line in text.splitlines()
            ) + "\n"
            soul_path.write_text(noisy, encoding="utf-8")
            clar_path = fx.write_system_file(
                "CLARIFICATIONS.md", CLARIFICATIONS_TEMPLATE
            )
            r.main([
                "--soul", str(soul_path),
                "--write-clarification",
                "--clarifications", str(clar_path),
            ])
            self.assertNotIn(
                "soul-manual-edit-to-auto-zone",
                clar_path.read_text(encoding="utf-8"),
            )
        clear_minder_memory_env()

    def test_idempotent_when_no_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            r.main(["--soul", str(soul_path)])
            once = soul_path.read_text(encoding="utf-8")
            r.main(["--soul", str(soul_path)])
            twice = soul_path.read_text(encoding="utf-8")
            def strip_ts(s: str) -> str:
                return "\n".join(
                    line for line in s.splitlines()
                    if "Last regenerated:" not in line
                )
            self.assertEqual(strip_ts(once), strip_ts(twice))
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
