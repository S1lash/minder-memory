"""Tests for gen_constitution_index.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import (  # type: ignore
    VALID_NOTE,
    VALID_PERSONAL_NOTE,
    VALID_SENSITIVE_NOTE,
    clear_minder_memory_env,
    make_fixture,
)
import gen_constitution_index as g  # type: ignore


class GenIndexTests(unittest.TestCase):
    def test_empty_tree_renders_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_fixture(Path(tmp))
            rc = g.main(["--dry-run"])
            self.assertEqual(rc, 0)
        clear_minder_memory_env()

    def test_all_three_types_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_principle("principle/tech/001.md", VALID_PERSONAL_NOTE)
            fx.write_principle("rule/health/001.md", VALID_SENSITIVE_NOTE)
            out = fx.base / "_system" / "views" / "CONSTITUTION_INDEX.md"
            rc = g.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("## Axioms", text)
            self.assertIn("## Principles", text)
            self.assertIn("## Rules", text)
            self.assertIn("axiom-identity-001", text)
            self.assertIn("principle-tech-001", text)
            self.assertIn("rule-health-001", text)
            # Stats block
            self.assertIn("**total:** 3", text)
            self.assertIn("**axiom:** 1", text)
            self.assertIn("**core:** 1", text)  # only VALID_NOTE has core:true and status=active
        clear_minder_memory_env()

    def test_deterministic_across_runs(self):
        """Two consecutive runs with same inputs must produce byte-identical
        output except for the timestamp line."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            out = fx.base / "_system" / "views" / "CONSTITUTION_INDEX.md"
            g.main(["--output", str(out)])
            first = out.read_text(encoding="utf-8")
            g.main(["--output", str(out)])
            second = out.read_text(encoding="utf-8")
            # Strip the timestamp line only.
            def strip_ts(s: str) -> str:
                return "\n".join(
                    line for line in s.splitlines()
                    if not line.startswith("_Generated:")
                )
            self.assertEqual(strip_ts(first), strip_ts(second))
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
