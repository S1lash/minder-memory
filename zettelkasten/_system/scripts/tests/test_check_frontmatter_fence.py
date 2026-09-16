"""Tests for check_frontmatter_fence — the runnable fence-integrity check.

Skills call this script rather than composing the `_common` fence helpers in
inline Python, because inline code failed on its own typing (a `str` path, a
tuple read as a dict) before it could check anything. So the tests hold both:
each status is reported for the shape that earns it, and the helpers accept a
plain string path.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import _common as c  # type: ignore
import check_frontmatter_fence as cff  # type: ignore

CLEAN = "---\nid: x\nlayer: knowledge\n---\n\n## Evidence Trail\n\n- a\n"
MISPLACED = "---\nid: x\nlayer: knowledge\n## Evidence Trail\n\n- **2026-05-05** | x\n---\n\nbody\n"
AMBIGUOUS = "---\nid: x\n## Evidence Trail\n\n---\n\ntext\n---\n\nbody\n"
BROKEN_YAML = "---\nid: [unclosed\n---\n\nbody\n"


class CheckFrontmatterFenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _note(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def _run(self, *argv: str) -> tuple[int, list[dict]]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cff.main(["--json", *argv])
        return code, [json.loads(line) for line in out.getvalue().splitlines()]

    def test_statuses_per_shape(self):
        paths = {
            "ok": self._note("clean.md", CLEAN),
            "fence-misplaced": self._note("misplaced.md", MISPLACED),
            "yaml-invalid": self._note("broken.md", BROKEN_YAML),
            "no-frontmatter": self._note("plain.md", "# title\n"),
            "missing": self.dir / "absent.md",
        }
        code, rows = self._run(*(str(p) for p in paths.values()))
        self.assertEqual(code, 1)
        self.assertEqual([r["status"] for r in rows], list(paths))

    def test_check_without_repair_writes_nothing(self):
        p = self._note("misplaced.md", MISPLACED)
        self._run(str(p))
        self.assertEqual(p.read_text(encoding="utf-8"), MISPLACED)

    def test_repair_relocates_unambiguous_fence(self):
        p = self._note("misplaced.md", MISPLACED)
        code, rows = self._run("--repair", str(p))
        self.assertEqual((code, rows[0]["status"]), (0, "repaired"))
        self.assertEqual(self._run(str(p))[1][0]["status"], "ok")

    def test_repair_refuses_ambiguous_shape(self):
        p = self._note("ambiguous.md", AMBIGUOUS)
        code, rows = self._run("--repair", str(p))
        self.assertEqual((code, rows[0]["status"]), (1, "fence-misplaced"))
        self.assertEqual(p.read_text(encoding="utf-8"), AMBIGUOUS)

    def test_all_passing_exits_zero(self):
        self.assertEqual(self._run(str(self._note("clean.md", CLEAN)))[0], 0)

    def test_no_paths_is_usage_error(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cff.main([]), 2)


class FrontmatterHelpersAcceptStrTests(unittest.TestCase):
    """`glob.glob` yields strings; the helpers must not demand a `Path`."""

    def test_string_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = str(Path(tmp) / "clean.md")
            Path(clean).write_text(CLEAN, encoding="utf-8")
            fm, body = c.read_frontmatter(clean)
            self.assertEqual(fm["id"], "x")
            self.assertTrue(c.frontmatter_closed_before_body(clean))
            self.assertTrue(c.repair_misplaced_fence(clean))

            broken = str(Path(tmp) / "misplaced.md")
            Path(broken).write_text(MISPLACED, encoding="utf-8")
            self.assertFalse(c.frontmatter_closed_before_body(broken))
            self.assertTrue(c.repair_misplaced_fence(broken))
            self.assertIsNotNone(c.read_frontmatter(broken))

            out = str(Path(tmp) / "out.md")
            c.write_frontmatter(out, {"id": "y"}, "\nbody\n")
            self.assertEqual(c.read_frontmatter(out)[0], {"id": "y"})


if __name__ == "__main__":
    unittest.main()
