"""Security tests.

The single-context dogfood model does NOT apply runtime scope narrowing:
all three scopes (shared / personal / sensitive) are visible everywhere.
These tests guard the invariants that still hold:

  S-1. Placeholder-status notes are excluded from every derived surface
       regardless of core / scope / applies_to (invariant #18).
  S-2. The consumer filter (applies_to inclusion) does narrow the harness
       view — a principle without `claude-code` in applies_to must never
       reach `_system/views/constitution-core.md`.
  S-3. The SOUL_VALUES_SCOPES constant is explicit and guarded — if it
       ever changes, the change is loud.
  S-4. ALL_SCOPES_VISIBLE is the exact set {shared, personal, sensitive}
       — adding a fourth scope or dropping one is a conscious act, not
       accidental.

When multi-user scenarios land (sharing to wife / friends, MCP tokens),
this file grows to cover the re-introduced scope filter.
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
import _common as c  # type: ignore
import gen_constitution_core as g  # type: ignore
import render_soul_values as r  # type: ignore


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _promote_to_core(note_text: str) -> str:
    return note_text.replace("core: false", "core: true")


class SecurityInvariants(unittest.TestCase):
    def test_S1_placeholder_never_in_core_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/meta/001.md", VALID_PLACEHOLDER_CORE)
            out = fx.base / "core.md"
            rc = g.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            self.assertNotIn("axiom-meta-001", _read(out))
            self.assertNotIn("Placeholder content never ships.", _read(out))
        clear_minder_memory_env()

    def test_S2_applies_to_filter_excludes_non_claude_code_principles(self):
        """Consumer filter is load-bearing: a core principle without
        `claude-code` in applies_to must not reach harness."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            # Core principle with applies_to that excludes claude-code
            non_cc = _promote_to_core(VALID_SENSITIVE_NOTE)
            # Keep applies_to = [life-advice] — no claude-code entry
            fx.write_principle("rule/health/001.md", non_cc)
            # Sanity: this principle IS visible when consumer filter is off
            ps = c.iter_principles(fx.constitution)
            self.assertTrue(c.is_visible(ps[0], consumer=None))
            self.assertFalse(c.is_visible(ps[0], consumer="claude-code"))
            # And rendered core does not contain it
            out = fx.base / "core.md"
            rc = g.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            self.assertNotIn("rule-health-001", _read(out))
        clear_minder_memory_env()

    def test_S3_soul_values_filter_is_explicit_and_guarded(self):
        """SOUL.Values scope filter is a load-bearing constant. This test
        breaks loudly if it ever changes, so multi-user sharing story
        gets a deliberate code review."""
        expected = {"shared", "personal", "sensitive"}
        self.assertEqual(
            set(r.SOUL_VALUES_SCOPES), expected,
            "SOUL_VALUES_SCOPES changed — verify multi-user sharing "
            "story before merging.",
        )

    def test_S4_all_scopes_visible_constant_is_exactly_three(self):
        """The visible-scope set is explicit: exactly three scopes, no
        fourth. Dropping or adding a scope is a conscious act."""
        self.assertEqual(
            c.ALL_SCOPES_VISIBLE,
            frozenset({"shared", "personal", "sensitive"}),
        )


if __name__ == "__main__":
    unittest.main()
