"""Tests for build_concept_registry — corpus aggregator + alias preservation."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tests._fixture import clear_minder_memory_env, make_fixture  # type: ignore

import build_concept_registry as bcr  # type: ignore


def _write_md(path: Path, frontmatter: str, body: str = "Body.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")


class HarvestCorpusTests(unittest.TestCase):
    def test_aggregates_concepts_across_records_and_para(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write_md(
                fx.base / "_records/meetings/20260401-meeting-foo.md",
                'id: rec1\ncreated: 2026-04-01\nconcepts:\n  - api_v2_design\n  - rate_limit',
            )
            _write_md(
                fx.base / "_records/meetings/20260403-meeting-bar.md",
                'id: rec2\ncreated: 2026-04-03\nconcepts: [api_v2_design, latency_budget]',
            )
            _write_md(
                fx.base / "1_projects/some-project.md",
                'id: proj1\ncreated: 2026-03-15\nconcepts:\n  - api_v2_design',
            )
            _write_md(
                fx.base / "_records/meetings/README.md",
                "should_be_skipped: true",
            )
            agg, stats = bcr.build(fx.base)
            self.assertEqual(stats["mentions_seen"], 5)
            self.assertEqual(set(agg.keys()), {"api_v2_design", "rate_limit", "latency_budget"})
            api = agg["api_v2_design"]
            self.assertEqual(api.mentions, 3)
            self.assertEqual(api.first_seen, date(2026, 3, 15))
            self.assertEqual(api.last_seen, date(2026, 4, 3))
        clear_minder_memory_env()

    def test_normalises_dirty_concept_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write_md(
                fx.base / "_records/observations/20260405-obs-foo.md",
                'id: obs1\ncreated: 2026-04-05\nconcepts:\n  - "API V2 Design"\n  - "rate-limit"',
            )
            agg, _ = bcr.build(fx.base)
            self.assertIn("api_v2_design", agg)
            self.assertIn("rate_limit", agg)
        clear_minder_memory_env()

    def test_empty_corpus_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            agg, stats = bcr.build(fx.base)
            self.assertEqual(agg, {})
            self.assertEqual(stats["mentions_seen"], 0)
            self.assertEqual(stats["batches_read"], 0)
        clear_minder_memory_env()

    def test_skips_template_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write_md(
                fx.base / "5_meta/templates/note-template.md",
                'concepts:\n  - placeholder_concept',
            )
            agg, _ = bcr.build(fx.base)
            self.assertNotIn("placeholder_concept", agg)
        clear_minder_memory_env()


class HarvestBatchesTests(unittest.TestCase):
    def test_pulls_type_subtype_chronologically(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            batches = fx.base / "_system/state/batches"
            batches.mkdir(parents=True)
            (batches / "20260101-aaa.json").write_text(json.dumps({
                "batch_id": "20260101-aaa",
                "timestamp": "2026-01-01T10:00:00Z",
                "concepts": {"upserts": [
                    {"name": "api_v2_design", "type": "idea", "subtype": "rest"},
                ]},
            }), encoding="utf-8")
            (batches / "20260301-bbb.json").write_text(json.dumps({
                "batch_id": "20260301-bbb",
                "timestamp": "2026-03-01T10:00:00Z",
                "concepts": {"upserts": [
                    {"name": "api_v2_design", "type": "decision", "subtype": "later"},
                ]},
            }), encoding="utf-8")
            _write_md(
                fx.base / "_records/meetings/20260101-meeting.md",
                'created: 2026-01-01\nconcepts: [api_v2_design]',
            )
            agg, _ = bcr.build(fx.base)
            self.assertEqual(agg["api_v2_design"].type, "idea")
            self.assertEqual(agg["api_v2_design"].subtype, "rest")
        clear_minder_memory_env()

    def test_drops_type_outside_emit_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            batches = fx.base / "_system/state/batches"
            batches.mkdir(parents=True)
            (batches / "b.json").write_text(json.dumps({
                "batch_id": "b",
                "timestamp": "2026-01-01T10:00:00Z",
                "concepts": {"upserts": [
                    {"name": "ivan_petrov", "type": "person"},
                    {"name": "acme_payments", "type": "bogus_value"},
                ]},
            }), encoding="utf-8")
            agg, _ = bcr.build(fx.base)
            self.assertIsNone(agg.get("ivan_petrov").type if agg.get("ivan_petrov") else None)
            self.assertIsNone(agg.get("acme_payments").type if agg.get("acme_payments") else None)
        clear_minder_memory_env()

    def test_unparseable_batch_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            batches = fx.base / "_system/state/batches"
            batches.mkdir(parents=True)
            (batches / "bad.json").write_text("not json{", encoding="utf-8")
            agg, stats = bcr.build(fx.base)
            self.assertEqual(stats["batches_read"], 0)
        clear_minder_memory_env()


class AliasPreservationTests(unittest.TestCase):
    def test_aliases_carry_over_from_existing_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            registry = fx.base / "_system/registries/CONCEPTS.md"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                "---\nlast_updated: 2026-05-04\n---\n\n"
                "## Concepts (sorted by mentions)\n\n"
                "| name | type | subtype | first_seen | last_seen | mentions | aliases |\n"
                "|---|---|---|---|---|---|---|\n"
                "| api_v2_design | idea | — | 2026-01-01 | 2026-04-01 | 5 | api_v2, api2 |\n"
            , encoding="utf-8")
            _write_md(
                fx.base / "_records/meetings/20260401-meeting.md",
                'created: 2026-04-01\nconcepts: [api_v2_design]',
            )
            agg, _ = bcr.build(fx.base)
            self.assertEqual(agg["api_v2_design"].aliases, ["api_v2", "api2"])
        clear_minder_memory_env()

    def test_orphan_aliases_kept_with_zero_mentions(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            registry = fx.base / "_system/registries/CONCEPTS.md"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                "## Concepts (sorted by mentions)\n\n"
                "| name | type | subtype | first_seen | last_seen | mentions | aliases |\n"
                "|---|---|---|---|---|---|---|\n"
                "| renamed_concept | idea | — | 2026-01-01 | 2026-01-01 | 0 | old_name |\n"
            , encoding="utf-8")
            agg, _ = bcr.build(fx.base)
            self.assertIn("renamed_concept", agg)
            self.assertEqual(agg["renamed_concept"].mentions, 0)
            self.assertEqual(agg["renamed_concept"].aliases, ["old_name"])
        clear_minder_memory_env()


class RenderTests(unittest.TestCase):
    def test_single_table_sorted_by_mentions_desc(self):
        agg = {
            "popular": bcr.ConceptAgg(name="popular", mentions=150),
            "rare": bcr.ConceptAgg(name="rare", mentions=2),
            "medium": bcr.ConceptAgg(name="medium", mentions=42),
        }
        out = bcr.render_registry(agg, today=date(2026, 5, 1))
        # Single section, no Top/Tail split.
        self.assertIn("## Concepts (sorted by mentions)", out)
        self.assertNotIn("## Top by mentions", out)
        self.assertNotIn("## Tail", out)
        # No counter fields in frontmatter — manifest carries them.
        self.assertNotIn("total_concepts:", out)
        self.assertNotIn("total_mentions:", out)
        self.assertNotIn("top_threshold:", out)
        # Order: popular > medium > rare.
        idx_popular = out.index("| popular |")
        idx_medium = out.index("| medium |")
        idx_rare = out.index("| rare |")
        self.assertLess(idx_popular, idx_medium)
        self.assertLess(idx_medium, idx_rare)

    def test_empty_corpus_renders_placeholder(self):
        out = bcr.render_registry({}, today=date(2026, 5, 1))
        self.assertIn("## Concepts (sorted by mentions)", out)
        self.assertIn("registry is empty", out)
        # Frontmatter still minimal — no counter fields.
        self.assertNotIn("total_concepts:", out)

    def test_stats_dict_still_carries_counts(self):
        # Counters live in the stats dict (consumed by /minder:mem:maintain
        # batch manifest → Minder downstream). Removing them from the
        # rendered markdown is purely a frontmatter cleanup.
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write_md(
                fx.base / "_records/meetings/20260401-meeting.md",
                "created: 2026-04-01\nconcepts: [a, b, a]",
            )
            _, stats = bcr.build(fx.base)
            self.assertIn("total_concepts", stats)
            self.assertIn("total_mentions", stats)
        clear_minder_memory_env()


class IdempotenceTests(unittest.TestCase):
    def test_main_writes_then_re_runs_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write_md(
                fx.base / "_records/meetings/20260401-meeting.md",
                'created: 2026-04-01\nconcepts: [test_concept]',
            )
            self.assertEqual(bcr.main(["--root", str(fx.base)]), 0)
            registry = fx.base / "_system/registries/CONCEPTS.md"
            first = registry.read_text(encoding="utf-8")
            self.assertEqual(bcr.main(["--root", str(fx.base)]), 0)
            second = registry.read_text(encoding="utf-8")
            # Same date semantics — idempotent on identical inputs
            self.assertEqual(first, second)
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
