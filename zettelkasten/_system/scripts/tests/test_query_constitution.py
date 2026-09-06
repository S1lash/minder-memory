"""Tests for query_constitution.py."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests._fixture import (  # type: ignore
    VALID_NOTE,
    VALID_PERSONAL_NOTE,
    VALID_PLACEHOLDER_CORE,
    VALID_SENSITIVE_NOTE,
    clear_minder_memory_env,
    make_fixture,
)
import query_constitution as q  # type: ignore


def _run(argv: list[str]) -> list[dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = q.main(argv)
    assert rc == 0, f"query failed, argv={argv}"
    return json.loads(buf.getvalue())


class QueryConstitutionTests(unittest.TestCase):
    def test_default_context_returns_all_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_principle("principle/tech/001.md", VALID_PERSONAL_NOTE)
            # Sensitive principle, applies_to includes claude-code
            sensitive_cc = VALID_SENSITIVE_NOTE.replace(
                "applies_to: [life-advice]",
                "applies_to: [claude-code, life-advice]",
            )
            fx.write_principle("rule/health/001.md", sensitive_cc)
            out = _run([])
            ids = {p["id"] for p in out}
            self.assertEqual(
                ids,
                {"axiom-identity-001", "principle-tech-001", "rule-health-001"},
            )
        clear_minder_memory_env()

    def test_consumer_filter_narrows_by_applies_to(self):
        """Consumer filter is the one active narrowing in single-context
        mode."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            # sensitive note whose applies_to is [life-advice] — no claude-code
            fx.write_principle("rule/health/001.md", VALID_SENSITIVE_NOTE)
            out = _run(["--consumer", "claude-code"])
            ids = {p["id"] for p in out}
            self.assertEqual(ids, {"axiom-identity-001"})
        clear_minder_memory_env()

    def test_domain_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_principle("principle/tech/001.md", VALID_PERSONAL_NOTE)
            out = _run(["--domains", "tech"])
            ids = {p["id"] for p in out}
            self.assertEqual(ids, {"principle-tech-001"})
        clear_minder_memory_env()

    def test_placeholder_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/meta/001.md", VALID_PLACEHOLDER_CORE)
            out = _run([])
            self.assertEqual(out, [])
        clear_minder_memory_env()

    def test_placeholder_included_with_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/meta/001.md", VALID_PLACEHOLDER_CORE)
            out = _run(["--include-placeholder"])
            ids = {p["id"] for p in out}
            self.assertEqual(ids, {"axiom-meta-001"})
        clear_minder_memory_env()

    def test_emits_full_body(self):
        """Skill reasoning needs the full body text, not just statement."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            out = _run([])
            self.assertIn("Choose the higher-quality path.", out[0]["body"])
        clear_minder_memory_env()

    def test_unknown_domain_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            with self.assertRaises(SystemExit):
                q.main(["--domains", "bogus"])
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
