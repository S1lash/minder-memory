"""Tests for archive_buffer.py — F.3 archive/verify/clear mechanics."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tests._fixture import clear_minder_memory_env, make_fixture  # type: ignore
import archive_buffer as a  # type: ignore


def _write_buffer(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


class ArchiveBufferTests(unittest.TestCase):
    def test_happy_path_archive_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            buf = fx.system / "state" / "principle-candidates.jsonl"
            _write_buffer(buf, [
                {"session_id": "s1", "situation": "a"},
                {"session_id": "s2", "situation": "b"},
            ])
            arch_dir = fx.system / "lint-context" / "weekly"
            rc = a.main([
                "--buffer", str(buf),
                "--archive-dir", str(arch_dir),
                "--week", "2026-W17",
            ])
            self.assertEqual(rc, 0)
            # Archive exists with right content
            arch_path = arch_dir / "2026-W17-principle-candidates-archived.jsonl"
            self.assertTrue(arch_path.exists())
            lines = [l for l in arch_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)
            # Buffer cleared
            self.assertEqual(buf.read_text(encoding="utf-8"), "")
        clear_minder_memory_env()

    def test_empty_buffer_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            buf = fx.system / "state" / "principle-candidates.jsonl"
            buf.parent.mkdir(parents=True, exist_ok=True)
            buf.write_text("", encoding="utf-8")
            rc = a.main([
                "--buffer", str(buf),
                "--archive-dir", str(fx.system / "lint-context" / "weekly"),
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(buf.read_text(encoding="utf-8"), "")
        clear_minder_memory_env()

    def test_archive_verify_mismatch_preserves_buffer(self):
        """Direct unit test on archive_and_clear: simulate verify mismatch
        by pre-writing a short archive then running a buffer with more
        lines than archive captures."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            buf = fx.system / "state" / "principle-candidates.jsonl"
            _write_buffer(buf, [
                {"session_id": f"s{i}"} for i in range(3)
            ])
            # Monkey-patch _count_nonblank_lines to return a mismatched value
            import archive_buffer as ab
            orig_count = ab._count_nonblank_lines
            call = {"n": 0}
            def fake_count(path):
                call["n"] += 1
                # First call = buffer (3), second call = archive (2)
                return 3 if call["n"] == 1 else 2
            ab._count_nonblank_lines = fake_count
            try:
                arch = fx.system / "weekly-arch.jsonl"
                with self.assertRaises(RuntimeError) as ctx:
                    ab.archive_and_clear(buf, arch)
                self.assertIn("verify failed", str(ctx.exception))
                # Buffer MUST remain intact on verify failure
                self.assertIn("s0", buf.read_text(encoding="utf-8"))
                self.assertIn("s2", buf.read_text(encoding="utf-8"))
            finally:
                ab._count_nonblank_lines = orig_count
        clear_minder_memory_env()

    def test_verify_mismatch_exits_nonzero(self):
        """main() returns 2 on verify failure, buffer remains intact."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            buf = fx.system / "state" / "principle-candidates.jsonl"
            _write_buffer(buf, [{"session_id": "x"}])
            arch_dir = fx.system / "lint-context" / "weekly"

            import archive_buffer as ab
            def boom(*_args, **_kwargs):
                raise RuntimeError("verify failed: simulated")
            orig = ab.archive_and_clear
            ab.archive_and_clear = boom
            try:
                rc = ab.main([
                    "--buffer", str(buf),
                    "--archive-dir", str(arch_dir),
                ])
                self.assertEqual(rc, 2)
                # Buffer untouched
                self.assertIn("x", buf.read_text(encoding="utf-8"))
            finally:
                ab.archive_and_clear = orig
        clear_minder_memory_env()

    def test_iso_week_tag_format(self):
        self.assertRegex(a.iso_week_tag(date(2026, 4, 20)), r"^2026-W\d{2}$")

    def test_dry_run_does_not_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            buf = fx.system / "state" / "principle-candidates.jsonl"
            _write_buffer(buf, [{"session_id": "s1"}])
            rc = a.main([
                "--buffer", str(buf),
                "--archive-dir", str(fx.system / "weekly"),
                "--dry-run",
            ])
            self.assertEqual(rc, 0)
            # Buffer still has the entry
            self.assertIn("s1", buf.read_text(encoding="utf-8"))
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
