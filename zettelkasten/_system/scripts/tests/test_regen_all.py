"""Tests for regen_all.py — the single orchestrator for derived views."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._fixture import (  # type: ignore
    SOUL_TEMPLATE,
    VALID_NOTE,
    clear_minder_memory_env,
    make_fixture,
)


SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def _run_regen(argv: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, str(SCRIPTS_DIR / "regen_all.py")] + argv
    return subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8")


class RegenAllTests(unittest.TestCase):
    def test_skips_soul_step_when_markers_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_system_file("SOUL.md", "# SOUL\n\nNo markers here.\n")
            result = _run_regen([], env_extra={"MINDER_MEMORY_BASE": str(fx.base)})
            # Exit 0: a base whose SOUL.md has no auto-zone yet is HEALTHY, and
            # every view that could be regenerated was. A distinct code here
            # made every caller checking the status report a failure on a
            # healthy run — the status stops meaning what it says.
            # `--strict-soul` is how a caller that requires the step asks for a
            # failure (covered by the next test).
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("no auto-zone markers", result.stderr)
            # Index + core must still have been produced
            self.assertTrue((fx.system / "views" / "CONSTITUTION_INDEX.md").exists())
            self.assertTrue((fx.system / "views" / "constitution-core.md").exists())
        clear_minder_memory_env()

    def test_strict_soul_fails_when_markers_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_system_file("SOUL.md", "# SOUL\n\nNo markers here.\n")
            result = _run_regen(
                ["--strict-soul"],
                env_extra={"MINDER_MEMORY_BASE": str(fx.base)},
            )
            self.assertNotEqual(result.returncode, 0)
        clear_minder_memory_env()

    def test_full_pipeline_when_markers_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            soul_path = fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            result = _run_regen([], env_extra={"MINDER_MEMORY_BASE": str(fx.base)})
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((fx.system / "views" / "CONSTITUTION_INDEX.md").exists())
            self.assertTrue((fx.system / "views" / "constitution-core.md").exists())
            # SOUL values zone written
            soul_text = soul_path.read_text(encoding="utf-8")
            self.assertIn("If it can be better", soul_text)
        clear_minder_memory_env()

    def test_idempotent_two_runs(self):
        """Second run without source changes must produce byte-identical
        derived views, ignoring dynamic timestamps."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            _run_regen([], env_extra={"MINDER_MEMORY_BASE": str(fx.base)})
            first_index = (fx.system / "views" / "CONSTITUTION_INDEX.md").read_text(encoding="utf-8")
            first_core = (fx.system / "views" / "constitution-core.md").read_text(encoding="utf-8")
            first_soul = (fx.system / "SOUL.md").read_text(encoding="utf-8")

            _run_regen([], env_extra={"MINDER_MEMORY_BASE": str(fx.base)})
            second_index = (fx.system / "views" / "CONSTITUTION_INDEX.md").read_text(encoding="utf-8")
            second_core = (fx.system / "views" / "constitution-core.md").read_text(encoding="utf-8")
            second_soul = (fx.system / "SOUL.md").read_text(encoding="utf-8")

            def strip_ts(s: str) -> str:
                return "\n".join(
                    line for line in s.splitlines()
                    if "Last regenerated:" not in line
                    and "Generated:" not in line
                    and not line.startswith("_Generated:")
                )

            self.assertEqual(strip_ts(first_index), strip_ts(second_index))
            self.assertEqual(strip_ts(first_core), strip_ts(second_core))
            self.assertEqual(strip_ts(first_soul), strip_ts(second_soul))
        clear_minder_memory_env()

    def test_fail_fast_on_malformed_principle(self):
        """Broken frontmatter in step 1 must prevent steps 2 and 3."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle(
                "axiom/identity/001.md",
                "---\nid: wrong-prefix-id\n---\n# bad\n",
            )
            result = _run_regen([], env_extra={"MINDER_MEMORY_BASE": str(fx.base)})
            self.assertNotEqual(result.returncode, 0)
            # Index must not have been produced (step 1 fails)
            self.assertFalse((fx.system / "views" / "CONSTITUTION_INDEX.md").exists())
            # Core also not produced (step 2 never ran)
            self.assertFalse((fx.system / "views" / "constitution-core.md").exists())
        clear_minder_memory_env()

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            result = _run_regen(
                ["--dry-run"],
                env_extra={"MINDER_MEMORY_BASE": str(fx.base)},
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse((fx.system / "views" / "CONSTITUTION_INDEX.md").exists())
            self.assertFalse((fx.system / "views" / "constitution-core.md").exists())
            # SOUL should be unchanged
            self.assertEqual(
                (fx.system / "SOUL.md").read_text(encoding="utf-8"),
                SOUL_TEMPLATE,
            )
        clear_minder_memory_env()

    def test_single_core_file_no_context_suffix(self):
        """Single-context model: `_system/views/constitution-core.md` alone."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_system_file("SOUL.md", SOUL_TEMPLATE)
            _run_regen([], env_extra={"MINDER_MEMORY_BASE": str(fx.base)})
            self.assertTrue((fx.system / "views" / "constitution-core.md").exists())
            # No context-suffixed files should exist
            self.assertFalse((fx.system / "views" / "constitution-core.personal.md").exists())
            self.assertFalse((fx.system / "views" / "constitution-core.work.md").exists())
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
