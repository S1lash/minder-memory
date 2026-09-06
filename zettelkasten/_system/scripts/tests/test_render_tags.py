"""Tests for render_tags.py — the `tags:` axis census."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import clear_minder_memory_env, make_fixture  # type: ignore
import render_tags as r  # type: ignore


def note(nid: str, tags: list[str]) -> str:
    body = "\n".join(f"- {t}" for t in tags)
    return f"---\nid: {nid}\ntitle: {nid}\ntags:\n{body}\n---\n\n# {nid}\n"


REGISTRY_WITH_MARKERS = f"""# Tag Registry

Owner preamble that must survive every regeneration.

{r.ZONE_START}
stale content
{r.ZONE_END}

---

## Notes

- owner-authored note that must survive
"""


REGISTRY_LEGACY = """# Tag Registry

**Last Updated:** 2026-05-07

Owner preamble that must survive every regeneration.

**Total unique tags:** 999
**Total uses:** 9999

---

## Type (1)

| Tag | Uses |
|---|---:|
| `type/retired` | 72 |

---

## Notes

- owner-authored note that must survive
"""


class RenderTagsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fx = make_fixture(self.tmp)
        self.base = self.fx.base
        self.registries = self.base / "_system" / "registries"
        self.registries.mkdir(parents=True, exist_ok=True)
        self.tags_path = self.registries / "TAGS.md"

    def tearDown(self) -> None:
        clear_minder_memory_env()
        self._tmp.cleanup()

    # -- helpers ---------------------------------------------------------

    def write(self, rel: str, content: str) -> Path:
        p = self.base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def run_render(self, *extra: str) -> int:
        return r.main([
            "--base", str(self.base), "--tags", str(self.tags_path), *extra,
        ])

    def seed_registry(self, content: str = REGISTRY_WITH_MARKERS) -> None:
        self.tags_path.write_text(content, encoding="utf-8")

    # -- counting --------------------------------------------------------

    def test_counts_uses_per_tag_across_knowledge_layer(self) -> None:
        self.write("1_projects/a.md", note("a", ["type/idea", "domain/work"]))
        self.write("2_areas/b.md", note("b", ["type/idea", "org/rbs"]))
        self.write("3_resources/c.md", note("c", ["type/idea"]))
        self.write("4_archive/d.md", note("d", ["domain/work"]))
        self.write("5_meta/mocs/hub-x.md", note("hub-x", ["hub"]))
        self.write("5_skills/minder-mem-process.md", note("s", ["type/skill"]))

        counts, notes = r.collect_tags(self.base)
        self.assertEqual(notes, 6)
        self.assertEqual(counts["type/idea"], 3)
        self.assertEqual(counts["domain/work"], 2)
        self.assertEqual(counts["org/rbs"], 1)
        self.assertEqual(counts["hub"], 1)
        self.assertEqual(counts["type/skill"], 1)

    def test_tag_repeated_in_one_note_counts_once(self) -> None:
        self.write("2_areas/a.md", note("a", ["type/idea", "type/idea"]))
        counts, notes = r.collect_tags(self.base)
        self.assertEqual(counts["type/idea"], 1)
        self.assertEqual(notes, 1)

    def test_tags_are_literal_no_normalisation(self) -> None:
        """Convention drift is surfaced by the census, never merged."""
        self.write("2_areas/a.md", note("a", ["cat/sub"]))
        self.write("2_areas/b.md", note("b", ["cat-sub"]))
        counts, _ = r.collect_tags(self.base)
        self.assertEqual(counts["cat/sub"], 1)
        self.assertEqual(counts["cat-sub"], 1)

    def test_namespace_grouping_and_ordering(self) -> None:
        self.write("2_areas/a.md", note("a", ["type/x", "type/y", "hub"]))
        self.write("2_areas/b.md", note("b", ["type/x", "org/rbs"]))
        counts, _ = r.collect_tags(self.base)
        sections = r.group_by_namespace(counts)

        # Sections: by total uses desc, bare labels always last.
        self.assertEqual([s["namespace"] for s in sections], ["type", "org", None])
        self.assertEqual(sections[-1]["heading"], r.UNCATEGORIZED_HEADING)
        self.assertEqual(sections[0]["heading"], "Type")
        # Rows: uses desc, then name asc.
        self.assertEqual(sections[0]["rows"], [("type/x", 2), ("type/y", 1)])

    # -- scope -----------------------------------------------------------

    def test_excluded_layers_stay_excluded(self) -> None:
        self.write("2_areas/kept.md", note("kept", ["type/kept"]))
        for rel in (
            "_records/meetings/r.md",
            "_sources/inbox/s.md",
            "_system/state/x.md",
            "0_constitution/axiom/a.md",
            "6_posts/p.md",
        ):
            self.write(rel, note("excluded", ["type/excluded"]))

        counts, notes = r.collect_tags(self.base)
        self.assertEqual(notes, 1)
        self.assertIn("type/kept", counts)
        self.assertNotIn("type/excluded", counts)

    def test_engine_template_seeds_excluded(self) -> None:
        self.write("5_meta/mocs/hub-x.md", note("hub-x", ["hub"]))
        self.write("5_meta/mocs/hub-x.template.md", note("hub-x", ["hub"]))
        counts, _ = r.collect_tags(self.base)
        self.assertEqual(counts["hub"], 1)

    def test_symlinked_note_not_double_counted(self) -> None:
        real = self.write("2_areas/a.md", note("a", ["type/idea"]))
        link = self.base / "2_areas" / "a-link.md"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this platform")
        counts, _ = r.collect_tags(self.base)
        self.assertEqual(counts["type/idea"], 1)

    def test_notes_without_tags_are_ignored(self) -> None:
        self.write("2_areas/a.md", "---\nid: a\ntitle: a\n---\n\n# a\n")
        self.write("2_areas/b.md", "no frontmatter at all\n")
        counts, notes = r.collect_tags(self.base)
        self.assertEqual(notes, 0)
        self.assertEqual(len(counts), 0)

    # -- writing ---------------------------------------------------------

    def test_owner_sections_survive_regeneration(self) -> None:
        self.seed_registry()
        self.write("2_areas/a.md", note("a", ["type/idea"]))
        self.assertEqual(self.run_render(), 0)

        text = self.tags_path.read_text(encoding="utf-8")
        self.assertIn("Owner preamble that must survive every regeneration.", text)
        self.assertIn("- owner-authored note that must survive", text)
        self.assertIn("| `type/idea` | 1 |", text)
        self.assertNotIn("stale content", text)

    def test_rerun_is_byte_identical_and_writes_nothing(self) -> None:
        self.seed_registry()
        self.write("2_areas/a.md", note("a", ["type/idea", "org/rbs"]))
        self.assertEqual(self.run_render(), 0)

        first = self.tags_path.read_text(encoding="utf-8")
        mtime = self.tags_path.stat().st_mtime_ns
        self.assertEqual(self.run_render(), 0)
        second = self.tags_path.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        # Unchanged input → no write at all, so even the timestamp line is stable.
        self.assertEqual(mtime, self.tags_path.stat().st_mtime_ns)

    def test_retired_tag_disappears_on_regen(self) -> None:
        self.seed_registry()
        self.write("2_areas/a.md", note("a", ["type/idea"]))
        self.assertEqual(self.run_render(), 0)
        self.assertIn("| `type/idea` | 1 |", self.tags_path.read_text(encoding="utf-8"))

        (self.base / "2_areas" / "a.md").write_text(
            note("a", ["type/other"]), encoding="utf-8")
        self.assertEqual(self.run_render(), 0)
        text = self.tags_path.read_text(encoding="utf-8")
        self.assertNotIn("type/idea", text)
        self.assertIn("| `type/other` | 1 |", text)

    def test_totals_reflect_corpus(self) -> None:
        self.seed_registry()
        self.write("2_areas/a.md", note("a", ["type/idea", "org/rbs"]))
        self.write("2_areas/b.md", note("b", ["type/idea"]))
        self.assertEqual(self.run_render(), 0)
        text = self.tags_path.read_text(encoding="utf-8")
        self.assertIn("**Total unique tags:** 2", text)
        self.assertIn("**Total uses:** 3", text)

    def test_empty_corpus_renders_empty_state(self) -> None:
        self.seed_registry()
        self.assertEqual(self.run_render(), 0)
        text = self.tags_path.read_text(encoding="utf-8")
        self.assertIn("**Total unique tags:** 0", text)
        self.assertIn("_(no tags yet", text)
        self.assertIn("- owner-authored note that must survive", text)

    # -- legacy adoption -------------------------------------------------

    def test_legacy_registry_without_markers_is_adopted(self) -> None:
        self.seed_registry(REGISTRY_LEGACY)
        self.write("2_areas/a.md", note("a", ["type/current"]))
        self.assertEqual(self.run_render(), 0)

        text = self.tags_path.read_text(encoding="utf-8")
        self.assertIn(r.ZONE_START, text)
        self.assertIn(r.ZONE_END, text)
        self.assertIn("Owner preamble that must survive every regeneration.", text)
        self.assertIn("- owner-authored note that must survive", text)
        self.assertIn("| `type/current` | 1 |", text)
        # The stale generated region is gone, totals included.
        self.assertNotIn("type/retired", text)
        self.assertNotIn("**Total unique tags:** 999", text)
        # Adoption is a one-off: the second run is a marker-path no-op.
        self.assertEqual(self.run_render(), 0)
        self.assertEqual(text, self.tags_path.read_text(encoding="utf-8"))

    def test_registry_without_markers_or_anchor_is_skipped(self) -> None:
        self.seed_registry("# Tag Registry\n\nNothing renderable here.\n")
        self.write("2_areas/a.md", note("a", ["type/idea"]))
        self.assertEqual(self.run_render(), 0)
        # Left untouched rather than guessed at.
        self.assertEqual(
            self.tags_path.read_text(encoding="utf-8"),
            "# Tag Registry\n\nNothing renderable here.\n",
        )

    def test_missing_registry_is_skipped_not_crashed(self) -> None:
        self.write("2_areas/a.md", note("a", ["type/idea"]))
        self.assertEqual(self.run_render(), 0)
        self.assertFalse(self.tags_path.exists())

    # -- modes -----------------------------------------------------------

    def test_check_exits_3_when_stale_and_0_when_current(self) -> None:
        self.seed_registry()
        self.write("2_areas/a.md", note("a", ["type/idea"]))
        self.assertEqual(self.run_render("--check"), 3)
        self.assertIn("stale content", self.tags_path.read_text(encoding="utf-8"))
        self.assertEqual(self.run_render(), 0)
        self.assertEqual(self.run_render("--check"), 0)

    def test_dry_run_does_not_write(self) -> None:
        self.seed_registry()
        self.write("2_areas/a.md", note("a", ["type/idea"]))
        before = self.tags_path.read_text(encoding="utf-8")
        self.assertEqual(self.run_render("--dry-run"), 0)
        self.assertEqual(before, self.tags_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
