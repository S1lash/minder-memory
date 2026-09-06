"""Tests for lint_hub_integrity.py.

Covers the default root, which had no test at all: `repo_root()` already
resolves to the zettelkasten base, so appending `zettelkasten` to it pointed one
level too deep and every invocation without `--root` died on "root does not
exist". A whole mode that no caller could use, invisible because nothing
exercised it.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import lint_hub_integrity as lhi  # noqa: E402


def _scaffold(root: Path) -> None:
    (root / "5_meta" / "mocs").mkdir(parents=True, exist_ok=True)
    (root / "_records" / "meetings").mkdir(parents=True, exist_ok=True)


class DefaultRootTests(unittest.TestCase):
    def _run_with_base(self, root: Path, argv: list[str]) -> tuple[int, str, str]:
        old = os.environ.get("MINDER_MEMORY_BASE")
        os.environ["MINDER_MEMORY_BASE"] = str(root)
        out_buf, err_buf = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                rc = lhi.main(argv)
        finally:
            if old is None:
                os.environ.pop("MINDER_MEMORY_BASE", None)
            else:
                os.environ["MINDER_MEMORY_BASE"] = old
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_default_root_resolves_to_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            rc, _, err = self._run_with_base(root, [])
            self.assertEqual(rc, 0, err)
            self.assertNotIn("root does not exist", err)

    def test_explicit_root_still_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            out_buf, err_buf = io.StringIO(), io.StringIO()
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                rc = lhi.main(["--root", str(root)])
            self.assertEqual(rc, 0, err_buf.getvalue())

    def test_missing_root_reports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            out_buf, err_buf = io.StringIO(), io.StringIO()
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                rc = lhi.main(["--root", str(missing)])
            self.assertEqual(rc, 1)
            self.assertIn("root does not exist", err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
