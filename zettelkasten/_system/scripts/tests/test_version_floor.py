"""The version floor — the oldest engine a clone may update FROM.

`scripts/lib/version_floor.py` is a hard refusal with an exact recovery
command, and the bash sync reads the floor branch from it rather than
restating it. These pin the comparison (a short or pre-release version is not
mis-read), the refusal on a clone with no version at all, and the two flags
the sync relies on.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_LIB = _REPO_ROOT / "scripts" / "lib"
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from lib import version_floor as vf  # noqa: E402


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_LIB / "version_floor.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


class ParseTests(unittest.TestCase):
    def test_short_and_prerelease_forms(self):
        self.assertEqual(vf.parse("0.69"), (0, 69, 0))
        self.assertEqual(vf.parse("1.0.0-rc1"), (1, 0, 0))
        self.assertEqual(vf.parse(" 0.70.2\n"), (0, 70, 2))

    def test_floor_is_inclusive(self):
        self.assertFalse(vf.below_floor("0.69.0"))
        self.assertFalse(vf.below_floor("0.69"))
        self.assertFalse(vf.below_floor("1.0.0"))
        self.assertTrue(vf.below_floor("0.68.9"))
        self.assertTrue(vf.below_floor("0.60.0"))

    def test_garbage_is_a_parse_error_not_a_pass(self):
        with self.assertRaises(ValueError):
            vf.parse("nope")


class CliTests(unittest.TestCase):
    def test_below_the_floor_prints_the_two_step_path(self):
        res = _run("0.60.0")
        self.assertEqual(res.returncode, 3)
        self.assertIn(f"--self-heal --branch {vf.FLOOR_BRANCH}", res.stderr)
        self.assertIn("commit", res.stderr)

    def test_no_version_is_below_the_floor(self):
        res = _run("")
        self.assertEqual(res.returncode, 3)
        self.assertIn("<no VERSION file>", res.stderr)

    def test_at_or_above_the_floor_is_silent(self):
        for version in (vf.MIN_UPDATABLE_VERSION, "1.0.0", "0.69"):
            with self.subTest(version=version):
                res = _run(version)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(res.stderr, "")

    def test_unparseable_is_exit_2(self):
        self.assertEqual(_run("nope").returncode, 2)

    def test_the_flags_the_sync_reads(self):
        self.assertEqual(_run("--floor-branch").stdout.strip(), vf.FLOOR_BRANCH)
        self.assertEqual(_run("--min-version").stdout.strip(), vf.MIN_UPDATABLE_VERSION)

    def test_the_sync_restates_nothing(self):
        text = (_REPO_ROOT / "scripts" / "sync_engine.sh").read_text(encoding="utf-8")
        self.assertNotIn(vf.FLOOR_BRANCH, text, "the floor branch has one home: version_floor.py")
        self.assertIn("--floor-branch", text)


if __name__ == "__main__":
    unittest.main()
