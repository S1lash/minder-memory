"""Tests for gen_constitution_core.py (single-context model).

All scopes (shared / personal / sensitive) are visible in the harness
view; the `scope` field is preserved on principles as a data marker
for future multi-user scenarios. No runtime scope filter is applied.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import (  # type: ignore
    VALID_NOTE,
    VALID_PERSONAL_NOTE,
    VALID_PLACEHOLDER_CORE,
    VALID_SENSITIVE_NOTE,
    clear_minder_memory_env,
    make_fixture,
)
import gen_constitution_core as g  # type: ignore


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _promote_to_core(note_text: str) -> str:
    return note_text.replace("core: false", "core: true")


class GenCoreTests(unittest.TestCase):
    def test_all_scopes_included_when_core(self):
        """All three scopes appear in the core view when marked core=true."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)  # shared core
            personal_core = _promote_to_core(VALID_PERSONAL_NOTE)
            fx.write_principle("principle/tech/001.md", personal_core)
            sensitive_core = _promote_to_core(VALID_SENSITIVE_NOTE).replace(
                "applies_to: [life-advice]",
                "applies_to: [claude-code, life-advice]",
            )
            fx.write_principle("rule/health/001.md", sensitive_core)
            out = fx.base / "core.md"
            rc = g.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            text = _read(out)
            self.assertIn("axiom-identity-001", text)
            self.assertIn("principle-tech-001", text)
            self.assertIn("rule-health-001", text)
        clear_minder_memory_env()

    def test_applies_to_claude_code_filter(self):
        """Principles whose applies_to does NOT include claude-code must not
        land in the harness view — this is a consumer filter, not a scope
        filter."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            # Core principle but applies_to excludes claude-code
            sensitive_core = _promote_to_core(VALID_SENSITIVE_NOTE)
            # Keep applies_to as [life-advice] — no claude-code
            fx.write_principle("rule/health/001.md", sensitive_core)
            out = fx.base / "core.md"
            rc = g.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            text = _read(out)
            self.assertNotIn("rule-health-001", text)
        clear_minder_memory_env()

    def test_placeholder_core_excluded(self):
        """Placeholder notes never ship (invariant #18)."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/meta/001.md", VALID_PLACEHOLDER_CORE)
            out = fx.base / "core.md"
            rc = g.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            self.assertNotIn("axiom-meta-001", _read(out))
        clear_minder_memory_env()

    def test_advisory_length_warns_but_does_not_fail(self):
        """Over-advisory output must still ship (content never truncated)."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            out = fx.base / "core.md"
            rc = g.main([
                "--output", str(out),
                "--advisory-lines", "1",
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertIn("NOTE: view exceeds advisory", _read(out))
            self.assertIn("If it can be better", _read(out))
        clear_minder_memory_env()

    def test_default_output_is_single_file(self):
        """Single constitution-core.md, no context suffix."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            rc = g.main([])
            self.assertEqual(rc, 0)
            self.assertTrue((fx.system / "views" / "constitution-core.md").exists())
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
