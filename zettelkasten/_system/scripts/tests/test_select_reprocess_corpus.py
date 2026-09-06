"""Tests for `select_reprocess_corpus_files` — corpus walk + sort + truncate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import clear_minder_memory_env  # type: ignore
import _common as c  # type: ignore


def _write(path: Path, fm_lines: list[str], body: str = "body\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = "\n".join(fm_lines)
    path.write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")


def _seed(base: Path) -> dict[str, Path]:
    """Seed a minimal corpus across both scopes."""
    files: dict[str, Path] = {}

    # records — chronologically out-of-order on disk
    files["meeting_03"] = base / "_records/meetings/20260415-meeting-c.md"
    _write(files["meeting_03"], ["id: 20260415-meeting-c", "layer: record", "created: 2026-04-15"])

    files["meeting_01"] = base / "_records/meetings/20260101-meeting-a.md"
    _write(files["meeting_01"], ["id: 20260101-meeting-a", "layer: record", "created: 2026-01-01"])

    files["observation_02"] = base / "_records/observations/20260210-observation-b.md"
    _write(files["observation_02"], ["id: 20260210-observation-b", "layer: record", "created: 2026-02-10"])

    # knowledge
    files["knowledge_01"] = base / "1_projects/proj-a/20260105-decision-foo.md"
    _write(files["knowledge_01"], ["id: 20260105-decision-foo", "layer: knowledge", "created: 2026-01-05"])

    files["knowledge_02"] = base / "2_areas/area-b/20260301-insight-bar.md"
    _write(files["knowledge_02"], ["id: 20260301-insight-bar", "layer: knowledge", "created: 2026-03-01"])

    files["knowledge_03"] = base / "3_resources/people/20260601-reflection-baz.md"
    _write(files["knowledge_03"], ["id: 20260601-reflection-baz", "layer: knowledge", "created: 2026-06-01"])

    # excluded artifacts
    # README files (no frontmatter) — must be skipped by walk
    (base / "_records/observations/README.md").write_text(
        "# Observations Layer\n\nNo frontmatter here.\n", encoding="utf-8"
    )
    # 4_archive — never walked even when scope=all
    files["archive_excluded"] = base / "4_archive/old/20250101-archived.md"
    _write(files["archive_excluded"], ["id: 20250101-archived", "layer: knowledge", "created: 2025-01-01"])
    # Wrong layer (e.g. profile, registry, tier2) — must be filtered
    bad_layer = base / "3_resources/people/profile-x.md"
    _write(bad_layer, ["id: profile-x", "layer: profile"])
    # No layer field — must be filtered
    no_layer = base / "1_projects/proj-a/no-layer.md"
    _write(no_layer, ["id: no-layer-x", "created: 2026-01-01"])
    # Filename date-prefix only, no created: → falls back to filename
    files["fallback_filename"] = base / "_records/meetings/20260520-meeting-fallback.md"
    _write(files["fallback_filename"], ["id: 20260520-meeting-fallback", "layer: record"])

    return files


class SelectReprocessCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_minder_memory_env()
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.files = _seed(self.base)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_scope_records_chronological(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="records")
        # meeting_01 (2026-01-01), observation_02 (2026-02-10),
        # meeting_03 (2026-04-15), fallback_filename (2026-05-20 from name)
        self.assertEqual(
            result,
            [
                self.files["meeting_01"],
                self.files["observation_02"],
                self.files["meeting_03"],
                self.files["fallback_filename"],
            ],
        )

    def test_scope_knowledge_chronological(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="knowledge")
        self.assertEqual(
            result,
            [
                self.files["knowledge_01"],
                self.files["knowledge_02"],
                self.files["knowledge_03"],
            ],
        )

    def test_scope_all_merges_chronologically(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="all")
        self.assertEqual(
            result,
            [
                self.files["meeting_01"],       # 2026-01-01
                self.files["knowledge_01"],     # 2026-01-05
                self.files["observation_02"],   # 2026-02-10
                self.files["knowledge_02"],     # 2026-03-01
                self.files["meeting_03"],       # 2026-04-15
                self.files["fallback_filename"],  # 2026-05-20 (filename fallback)
                self.files["knowledge_03"],     # 2026-06-01
            ],
        )

    def test_scope_default_is_all(self) -> None:
        self.assertEqual(
            c.select_reprocess_corpus_files(self.base),
            c.select_reprocess_corpus_files(self.base, scope="all"),
        )

    def test_archive_excluded_even_under_all(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="all")
        self.assertNotIn(self.files["archive_excluded"], result)

    def test_readme_and_wrong_layer_excluded(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="all")
        names = {p.name for p in result}
        self.assertNotIn("README.md", names)
        self.assertNotIn("profile-x.md", names)
        self.assertNotIn("no-layer.md", names)

    def test_limit_truncates_to_first_n(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="all", limit=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(
            result,
            [
                self.files["meeting_01"],
                self.files["knowledge_01"],
                self.files["observation_02"],
            ],
        )

    def test_limit_zero_returns_empty_list(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="all", limit=0)
        self.assertEqual(result, [])

    def test_limit_none_returns_full_list(self) -> None:
        full = c.select_reprocess_corpus_files(self.base, scope="all")
        self.assertEqual(
            c.select_reprocess_corpus_files(self.base, scope="all", limit=None),
            full,
        )

    def test_limit_negative_returns_full_list(self) -> None:
        full = c.select_reprocess_corpus_files(self.base, scope="all")
        self.assertEqual(
            c.select_reprocess_corpus_files(self.base, scope="all", limit=-1),
            full,
        )

    def test_limit_larger_than_corpus_returns_all(self) -> None:
        full = c.select_reprocess_corpus_files(self.base, scope="all")
        self.assertEqual(
            c.select_reprocess_corpus_files(self.base, scope="all", limit=999),
            full,
        )

    def test_limit_with_records_scope(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="records", limit=2)
        self.assertEqual(
            result,
            [
                self.files["meeting_01"],
                self.files["observation_02"],
            ],
        )

    def test_filename_fallback_when_no_created_field(self) -> None:
        result = c.select_reprocess_corpus_files(self.base, scope="records")
        # fallback_filename has no created: but filename starts with 20260520 →
        # it should sort between meeting_03 (2026-04-15) and any later record.
        idx = result.index(self.files["fallback_filename"])
        self.assertEqual(idx, 3)  # last among the 4 records

    def test_unknown_scope_raises(self) -> None:
        with self.assertRaises(ValueError):
            c.select_reprocess_corpus_files(self.base, scope="bogus")

    def test_missing_roots_silently_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_base = Path(tmp)
            # No directories created — walk should return empty list, not raise.
            self.assertEqual(
                c.select_reprocess_corpus_files(empty_base, scope="all"),
                [],
            )

    def test_str_base_accepted(self) -> None:
        # `base` accepts str as well as Path — orchestrators that shell to
        # this helper from non-typed call sites should not have to coerce.
        result_str = c.select_reprocess_corpus_files(str(self.base), scope="records")
        result_path = c.select_reprocess_corpus_files(self.base, scope="records")
        self.assertEqual(result_str, result_path)


if __name__ == "__main__":
    unittest.main()
