"""Tests for render_hub_maps.py — ARCH-B derived hub-map renderer."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

# Path setup mirrors other tests
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import render_hub_maps as r  # noqa: E402


def _write_note(path: Path, fm: dict, body: str = "") -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False,
                               allow_unicode=True, width=10000).rstrip("\n")
    path.write_text(f"---\n{yaml_text}\n---\n{body}", encoding="utf-8")


def _run(root: Path, *, hub: str | None = None, apply: bool = False
         ) -> tuple[int, str, str]:
    args = ["--root", str(root)]
    if hub:
        args.extend(["--hub", hub])
    if apply:
        args.append("--apply")
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = r.main(args)
    return rc, out_buf.getvalue(), err_buf.getvalue()


class TestRenderHubMaps(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_obj = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_obj.name)
        # mocs dir
        (self.root / "5_meta" / "mocs").mkdir(parents=True)
        # records dir for member notes
        (self.root / "_records" / "meetings").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp_obj.cleanup()

    def _create_hub(self, slug: str, kind: str = "project",
                    mode: str = "derived",
                    excluded_ids: list[str] | None = None,
                    excluded_reasons: list[str] | None = None,
                    body: str = "") -> Path:
        path = self.root / "5_meta" / "mocs" / f"hub-{slug}.md"
        fm = {
            "id": f"hub-{slug}",
            "title": f"Hub: {slug}",
            "layer": "hub",
            "hub_kind": kind,
            "chronological_map_mode": mode,
            "excluded_from_map": excluded_ids or [],
            "excluded_from_map_reasons": excluded_reasons or [],
            "projects": [slug] if kind == "project" else [],
        }
        _write_note(path, fm, body)
        return path

    def _create_record(self, note_id: str, projects: list[str],
                       created: str = "2026-01-01",
                       title: str | None = None,
                       description: str | None = None,
                       kind: str = "meeting") -> Path:
        path = self.root / "_records" / "meetings" / f"{note_id}.md"
        fm = {
            "id": note_id,
            "title": title or note_id,
            "created": created,
            "layer": "record",
            "kind": kind,
            "projects": projects,
        }
        if description:
            fm["description"] = description
        _write_note(path, fm)
        return path

    def test_basic_render_with_5_records(self) -> None:
        """Single hub, 5 records, default chronological order."""
        self._create_hub("foo")
        for i, date in enumerate(["2026-01-01", "2026-02-01",
                                   "2026-03-01", "2026-04-01",
                                   "2026-05-01"]):
            self._create_record(f"note-{i}", ["foo"], created=date,
                                description=f"summary {i}")

        rc, out, _ = _run(self.root, hub="hub-foo", apply=True)
        self.assertEqual(rc, 0)
        events = [json.loads(l) for l in out.strip().split("\n") if l]
        rec = next(e for e in events if "skipped" not in e
                   and not e.get("summary"))
        self.assertEqual(rec["members"], 5)
        self.assertEqual(rec["visible"], 5)
        self.assertTrue(rec["changed"])

        # Verify body contains all 5 in chronological order
        body = (self.root / "5_meta" / "mocs" / "hub-foo.md").read_text(encoding="utf-8")
        for i in range(5):
            self.assertIn(f"note-{i}", body)
        # Markers present
        self.assertIn("AUTO-GENERATED", body)
        self.assertIn("/AUTO-GENERATED", body)

    def test_exclusion_skips_record_and_renders_table(self) -> None:
        """Excluded records appear in editorial-exclusions table only."""
        self._create_hub("foo",
                         excluded_ids=["note-2"],
                         excluded_reasons=["narrative noise"])
        for i in range(3):
            self._create_record(f"note-{i}", ["foo"],
                                created=f"2026-0{i+1}-01")

        rc, _, _ = _run(self.root, hub="hub-foo", apply=True)
        self.assertEqual(rc, 0)
        body = (self.root / "5_meta" / "mocs" / "hub-foo.md").read_text(encoding="utf-8")
        self.assertIn("note-0", body)
        self.assertIn("note-1", body)
        # note-2 should appear ONLY in excluded section, not the main table
        self.assertIn("Excluded from map (editorial)", body)
        self.assertIn("narrative noise", body)
        # Both note-2 mentions allowed (one in excluded table only)
        self.assertEqual(body.count("[[note-2]]"), 1)

    def test_curated_mode_skipped(self) -> None:
        """chronological_map_mode: curated → no rendering."""
        self._create_hub("foo", mode="curated",
                         body="## Хронологическая карта\n\noriginal text\n")
        self._create_record("note-1", ["foo"], created="2026-01-01")

        rc, out, _ = _run(self.root, hub="hub-foo", apply=True)
        self.assertEqual(rc, 0)
        events = [json.loads(l) for l in out.strip().split("\n") if l]
        skipped = next(e for e in events if e.get("skipped"))
        self.assertIn("mode=curated", skipped["skipped"])
        # Body unchanged
        body = (self.root / "5_meta" / "mocs" / "hub-foo.md").read_text(encoding="utf-8")
        self.assertIn("original text", body)
        self.assertNotIn("AUTO-GENERATED", body)

    def test_idempotency(self) -> None:
        """Re-running on unchanged data yields zero file changes."""
        self._create_hub("foo")
        self._create_record("note-1", ["foo"], created="2026-01-01")

        rc1, _, _ = _run(self.root, hub="hub-foo", apply=True)
        before = (self.root / "5_meta" / "mocs" / "hub-foo.md").read_bytes()
        rc2, out2, _ = _run(self.root, hub="hub-foo", apply=True)
        after = (self.root / "5_meta" / "mocs" / "hub-foo.md").read_bytes()
        self.assertEqual(rc1, 0)
        self.assertEqual(rc2, 0)
        self.assertEqual(before, after, "second apply should be no-op")
        events2 = [json.loads(l) for l in out2.strip().split("\n") if l]
        rec = next(e for e in events2 if not e.get("summary")
                   and not e.get("skipped"))
        self.assertFalse(rec["changed"])

    def test_empty_membership_renders_placeholder(self) -> None:
        """Hub with zero members renders header + «no records» note."""
        self._create_hub("orphan")
        # No records reference orphan
        rc, _, _ = _run(self.root, hub="hub-orphan", apply=True)
        self.assertEqual(rc, 0)
        body = (self.root / "5_meta" / "mocs" / "hub-orphan.md").read_text(encoding="utf-8")
        self.assertIn("AUTO-GENERATED", body)
        self.assertIn("no member records yet", body)

    def test_legacy_section_replaced_on_first_run(self) -> None:
        """Existing «## Хронологическая карта» replaced by AUTO block."""
        legacy_body = (
            "# Header\n\n"
            "## Текущее понимание\n\nsome narrative here\n\n"
            "## Хронологическая карта\n\n"
            "| Дата | Заметка |\n|---|---|\n| 2025-01-01 | old hand-curated |\n\n"
            "## Связанные хабы\n\nlinks here\n"
        )
        self._create_hub("legacy", body=legacy_body)
        self._create_record("note-1", ["legacy"], created="2026-01-01",
                            description="new entry")

        rc, _, _ = _run(self.root, hub="hub-legacy", apply=True)
        self.assertEqual(rc, 0)
        body = (self.root / "5_meta" / "mocs" / "hub-legacy.md").read_text(encoding="utf-8")
        # Pre-section preserved
        self.assertIn("Текущее понимание", body)
        self.assertIn("some narrative here", body)
        # Post-section preserved
        self.assertIn("Связанные хабы", body)
        self.assertIn("links here", body)
        # Legacy hand-curated row removed
        self.assertNotIn("old hand-curated", body)
        # New auto block present
        self.assertIn("AUTO-GENERATED", body)
        self.assertIn("note-1", body)

    def test_summary_fallback_chain(self) -> None:
        """description → title → id fallback for «Что произошло»."""
        self._create_hub("foo")
        # 1. With description
        self._create_record("note-1", ["foo"], created="2026-01-01",
                            description="explicit summary")
        # 2. Without description, with title
        self._create_record("note-2", ["foo"], created="2026-02-01",
                            title="title-only-fallback")
        # 3. Neither — title equals id by helper default; we set title=None
        path = self.root / "_records" / "meetings" / "note-3.md"
        _write_note(path, {
            "id": "note-3",
            "created": "2026-03-01",
            "layer": "record",
            "projects": ["foo"],
        })

        rc, _, _ = _run(self.root, hub="hub-foo", apply=True)
        self.assertEqual(rc, 0)
        body = (self.root / "5_meta" / "mocs" / "hub-foo.md").read_text(encoding="utf-8")
        self.assertIn("explicit summary", body)
        self.assertIn("title-only-fallback", body)
        self.assertIn("note-3", body)


class TestDefaultRoot(unittest.TestCase):
    """The default root must be the base itself.

    `repo_root()` already resolves to the zettelkasten base, so appending
    `zettelkasten` to it pointed one level too deep and every invocation without
    `--root` died on "root does not exist" — a whole mode that no caller could
    use and no test noticed.
    """

    def test_default_root_resolves_to_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "5_meta" / "mocs").mkdir(parents=True)
            (root / "_records" / "meetings").mkdir(parents=True)
            old = os.environ.get("MINDER_MEMORY_BASE")
            os.environ["MINDER_MEMORY_BASE"] = str(root)
            try:
                out_buf, err_buf = io.StringIO(), io.StringIO()
                with redirect_stdout(out_buf), redirect_stderr(err_buf):
                    rc = r.main([])
            finally:
                if old is None:
                    os.environ.pop("MINDER_MEMORY_BASE", None)
                else:
                    os.environ["MINDER_MEMORY_BASE"] = old
            self.assertEqual(rc, 0, err_buf.getvalue())
            self.assertNotIn("root does not exist", err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
