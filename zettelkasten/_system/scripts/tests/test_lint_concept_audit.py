"""Tests for lint_concept_audit.py — Scan A.7 + Step 1.D.

Coverage:
- concept format autofix (kebab → snake, case; type prefixes kept verbatim)
- concept drop (non-ASCII, type-only)
- audience-tag whitelist enforcement (canonical + extensions)
- audience-tag normalise + drop
- privacy-trio backfill (missing fields)
- type coercion (`is_sensitive`, `origin`)
- idempotence (re-run yields zero events)
- exclusion scope (registries / views / SOUL / templates not touched)
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests._fixture import clear_minder_memory_env  # type: ignore
import lint_concept_audit as la  # type: ignore


def _scaffold(root: Path) -> None:
    """Create the minimum directory structure needed."""
    for sub in (
        "_records/meetings", "_records/observations",
        "1_projects", "2_areas", "3_resources/people",
        "4_archive", "5_meta/mocs", "5_meta/templates",
        "_system/registries", "_system/views",
        "_system/state", "_sources/processed", "0_constitution",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _write_audiences(root: Path, extensions: list[str] | None = None) -> None:
    extensions = extensions or []
    rows = "\n".join(
        f"| {tag} | 2026-05-02 | active | test | — |" for tag in extensions
    )
    (root / "_system" / "registries" / "AUDIENCES.md").write_text(
        "# Audiences\n"
        "<!-- BEGIN extensions -->\n"
        "| Tag | Added | Status | Purpose | Notes |\n"
        "|---|---|---|---|---|\n"
        + (rows + "\n" if rows else "")
        + "<!-- END extensions -->\n",
        encoding="utf-8",
    )


def _write_md(path: Path, frontmatter: str, body: str = "body\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return path


def _run(root: Path, mode: str = "scan") -> list[dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        la.main(["--mode", mode, "--root", str(root)])
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


class ConceptAutofixTests(unittest.TestCase):
    def test_kebab_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            f = _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts:\n  - Office-Move\n'
                'origin: personal\naudience_tags: []\nis_sensitive: false\n',
            )
            events = _run(root, mode="fix")
            ids = {e["fix_id"] for e in events}
            self.assertIn("concept-format-autofix", ids)
            # File rewritten
            text = f.read_text(encoding="utf-8")
            self.assertIn("office_move", text)
            self.assertNotIn("Office-Move", text)
        clear_minder_memory_env()

    def test_non_ascii_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            f = _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts:\n  - тема\n  - delegation_pattern\n'
                'origin: personal\naudience_tags: []\nis_sensitive: false\n',
            )
            events = _run(root, mode="fix")
            ids = {e["fix_id"] for e in events}
            self.assertIn("concept-drop-autofix", ids)
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("тема", text)
            self.assertIn("delegation_pattern", text)
        clear_minder_memory_env()


class AudienceAutofixTests(unittest.TestCase):
    def test_canonical_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts: []\norigin: work\n'
                'audience_tags:\n  - work\n  - professional-network\n'
                'is_sensitive: false\n',
            )
            events = _run(root, mode="fix")
            self.assertEqual(events, [])  # nothing to fix
        clear_minder_memory_env()

    def test_unknown_tag_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)  # no extensions
            f = _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts: []\norigin: work\n'
                'audience_tags:\n  - work\n  - team-platform\n'
                'is_sensitive: false\n',
            )
            events = _run(root, mode="fix")
            ids = [e["fix_id"] for e in events]
            self.assertIn("audience-tag-drop-autofix", ids)
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("team-platform", text)
            self.assertIn("- work", text)
        clear_minder_memory_env()

    def test_extension_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root, extensions=["spouse"])
            _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts: []\norigin: personal\n'
                'audience_tags:\n  - spouse\nis_sensitive: false\n',
            )
            events = _run(root, mode="fix")
            self.assertEqual(events, [])
        clear_minder_memory_env()

    def test_case_normalised_to_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            f = _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts: []\norigin: personal\n'
                'audience_tags:\n  - Family\nis_sensitive: false\n',
            )
            events = _run(root, mode="fix")
            ids = {e["fix_id"] for e in events}
            self.assertIn("audience-tag-normalise-autofix", ids)
            text = f.read_text(encoding="utf-8")
            self.assertIn("- family", text)
            self.assertNotIn("Family", text)
        clear_minder_memory_env()


class PrivacyTrioBackfillTests(unittest.TestCase):
    def test_missing_trio_inserted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            f = _write_md(
                root / "1_projects" / "n.md",
                'id: foo\nlayer: knowledge\ntitle: "Foo"\n',
            )
            events = _run(root, mode="fix")
            ids = {e["fix_id"] for e in events}
            self.assertIn("privacy-trio-backfill-autofix", ids)
            text = f.read_text(encoding="utf-8")
            self.assertIn("origin: personal", text)
            self.assertIn("audience_tags: []", text)
            self.assertIn("is_sensitive: false", text)
        clear_minder_memory_env()

    def test_origin_derived_from_meetings_path(self):
        """Meeting record gets origin=work from path heuristic, not personal default."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            f = _write_md(
                root / "_records" / "meetings" / "20260501-meeting.md",
                'id: m1\nlayer: record\ntitle: "M"\n',
            )
            _run(root, mode="fix")
            text = f.read_text(encoding="utf-8")
            self.assertIn("origin: work", text)
        clear_minder_memory_env()

    def test_origin_derived_from_areas_work_path(self):
        """Note in 2_areas/work/ gets origin=work."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            (root / "2_areas" / "work").mkdir(parents=True, exist_ok=True)
            _write_audiences(root)
            f = _write_md(
                root / "2_areas" / "work" / "n.md",
                'id: w1\nlayer: knowledge\ntitle: "W"\n',
            )
            _run(root, mode="fix")
            text = f.read_text(encoding="utf-8")
            self.assertIn("origin: work", text)
        clear_minder_memory_env()

    def test_origin_personal_default_outside_work_paths(self):
        """Solo-capture paths and unmatched folders fall back to personal."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            f = _write_md(
                root / "_records" / "observations" / "obs.md",
                'id: o1\nlayer: record\ntitle: "O"\n',
            )
            _run(root, mode="fix")
            text = f.read_text(encoding="utf-8")
            self.assertIn("origin: personal", text)
        clear_minder_memory_env()

    def test_origin_coerced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\norigin: bogus\n'
                'audience_tags: []\nis_sensitive: false\n',
            )
            events = _run(root, mode="fix")
            ids = {e["fix_id"] for e in events}
            self.assertIn("origin-coerce-autofix", ids)
        clear_minder_memory_env()

    def test_is_sensitive_string_coerced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\norigin: personal\n'
                'audience_tags: []\nis_sensitive: "true"\n',
            )
            events = _run(root, mode="fix")
            ids = {e["fix_id"] for e in events}
            self.assertIn("is-sensitive-coerce-autofix", ids)
        clear_minder_memory_env()


class ScopeExclusionTests(unittest.TestCase):
    def test_soul_not_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            soul = _write_md(
                root / "_system" / "SOUL.md",
                'name: x\n', body="content\n",
            )
            original = soul.read_text(encoding="utf-8")
            events = _run(root, mode="fix")
            self.assertEqual(events, [])
            self.assertEqual(soul.read_text(encoding="utf-8"), original)
        clear_minder_memory_env()

    def test_template_not_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            tpl = _write_md(
                root / "5_meta" / "templates" / "note-template.md",
                'layer: knowledge\nconcepts:\n  - тема\n',
            )
            original = tpl.read_text(encoding="utf-8")
            events = _run(root, mode="fix")
            self.assertEqual(events, [])
            self.assertEqual(tpl.read_text(encoding="utf-8"), original)
        clear_minder_memory_env()

    def test_constitution_not_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            (root / "0_constitution" / "axiom").mkdir(parents=True, exist_ok=True)
            principle = _write_md(
                root / "0_constitution" / "axiom" / "p.md",
                'id: x\ntitle: x\n', body="text\n",
            )
            original = principle.read_text(encoding="utf-8")
            _run(root, mode="fix")
            self.assertEqual(principle.read_text(encoding="utf-8"), original)
        clear_minder_memory_env()


class IdempotenceTests(unittest.TestCase):
    def test_clean_state_zero_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts:\n  - office_move\n'
                'origin: personal\naudience_tags: []\nis_sensitive: false\n',
            )
            self.assertEqual(_run(root, mode="scan"), [])
            self.assertEqual(_run(root, mode="fix"), [])
        clear_minder_memory_env()

    def test_fix_then_rerun_no_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts:\n  - Office-Move\n'
                'origin: personal\naudience_tags:\n  - Family\n'
                'is_sensitive: "true"\n',
            )
            first = _run(root, mode="fix")
            self.assertGreater(len(first), 0)
            second = _run(root, mode="fix")
            self.assertEqual(second, [])
        clear_minder_memory_env()


class ScanModeNoWriteTests(unittest.TestCase):
    def test_scan_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            f = _write_md(
                root / "1_projects" / "n.md",
                'layer: knowledge\nconcepts:\n  - Office-Move\n'
                'origin: personal\naudience_tags: []\nis_sensitive: false\n',
            )
            original = f.read_text(encoding="utf-8")
            events = _run(root, mode="scan")
            self.assertGreater(len(events), 0)
            self.assertEqual(f.read_text(encoding="utf-8"), original)
        clear_minder_memory_env()


def _write_domains(root: Path, extensions: list[str] | None = None) -> None:
    """Seed DOMAINS.md with optional extensions table rows."""
    extensions = extensions or []
    rows = "\n".join(
        f"| {dom} | 2026-05-02 | active | test | — |" for dom in extensions
    )
    (root / "_system" / "registries" / "DOMAINS.md").write_text(
        "# Domains\n"
        "<!-- BEGIN extensions -->\n"
        "| Domain | Added | Status | Purpose | Notes |\n"
        "|---|---|---|---|---|\n"
        + (rows + "\n" if rows else "")
        + "<!-- END extensions -->\n",
        encoding="utf-8",
    )


class DomainAutofixTests(unittest.TestCase):
    """`fix_domains` pass — Phase 1 deterministic substrate."""

    def test_canonical_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [work, career]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            events = _run(root, mode="scan")
            domain_events = [e for e in events if "domain" in e.get("fix_id", "")]
            self.assertEqual(domain_events, [])
        clear_minder_memory_env()

    def test_unknown_value_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [work, payments, career]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            events = _run(root, mode="scan")
            drops = [
                e for e in events
                if e.get("fix_id") == "domain-drop-autofix"
                and e.get("raw") == "payments"
            ]
            self.assertEqual(len(drops), 1)
            self.assertEqual(drops[0]["reason"], "not-in-whitelist")

    def test_slash_syntax_split_and_filtered(self):
        # `personal/psychology` → `personal` kept (canonical), `psychology`
        # dropped (not in whitelist). `work/process` analogous.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "2_areas" / "n.md",
                "layer: knowledge\ndomains: [personal/psychology, work/process]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            events = _run(root, mode="scan")
            normalises = [
                e for e in events
                if e.get("fix_id") == "domain-normalise-autofix"
            ]
            results = sorted(
                e["result"] if isinstance(e["result"], str)
                else e["result"][0]
                for e in normalises
            )
            self.assertEqual(results, ["personal", "work"])
            drops = [
                e for e in events
                if e.get("fix_id") == "domain-drop-autofix"
            ]
            dropped_parts = sorted(e.get("part") for e in drops)
            self.assertEqual(dropped_parts, ["process", "psychology"])

    def test_slash_both_canonical_kept(self):
        # `work/learning` — both parts canonical → both kept.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [work/learning]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            _run(root, mode="fix")
            content = (root / "1_projects" / "n.md").read_text(encoding="utf-8")
            self.assertIn("- work\n", content)
            self.assertIn("- learning\n", content)
        clear_minder_memory_env()

    def test_case_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [Work, AI-Interaction]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            events = _run(root, mode="scan")
            normalises = sorted(
                e["result"] for e in events
                if e.get("fix_id") == "domain-normalise-autofix"
            )
            self.assertEqual(normalises, ["ai-interaction", "work"])

    def test_extension_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_domains(root, extensions=["gardening"])
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [gardening, junk]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            events = _run(root, mode="scan")
            domain_events = [e for e in events if "domain" in e.get("fix_id", "")]
            # Only "junk" should drop; gardening is in extensions.
            drops = [e for e in domain_events
                     if e.get("fix_id") == "domain-drop-autofix"]
            self.assertEqual(len(drops), 1)
            self.assertEqual(drops[0]["raw"], "junk")

    def test_format_unfixable_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [work, тема]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            events = _run(root, mode="scan")
            drops = [e for e in events
                     if e.get("fix_id") == "domain-drop-autofix"]
            self.assertEqual(len(drops), 1)
            self.assertEqual(drops[0]["reason"], "format-unfixable")

    def test_idempotent_after_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [Work, payments, personal/psychology]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            first = _run(root, mode="fix")
            self.assertGreater(
                len([e for e in first if "domain" in e.get("fix_id", "")]), 0
            )
            second = _run(root, mode="fix")
            self.assertEqual(
                [e for e in second if "domain" in e.get("fix_id", "")], []
            )
        clear_minder_memory_env()

    def test_dedupes_after_normalisation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\ndomains: [Work, work, WORK]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            _run(root, mode="fix")
            content = (root / "1_projects" / "n.md").read_text(encoding="utf-8")
            # Final list should contain a single 'work'.
            self.assertEqual(content.count("- work\n"), 1)


def _write_concepts_registry(root: Path, rows: list[tuple[str, str]]) -> None:
    """Write CONCEPTS.md with rows = [(canonical, alias_csv), ...]."""
    table_rows = "\n".join(
        f"| {name} | — | — | 2026-01-01 | 2026-01-01 | 1 | {aliases} |"
        for name, aliases in rows
    )
    (root / "_system" / "registries" / "CONCEPTS.md").write_text(
        "---\nlast_updated: 2026-05-04\n---\n\n"
        "## Concepts (sorted by mentions)\n\n"
        "| name | type | subtype | first_seen | last_seen | mentions | aliases |\n"
        "|---|---|---|---|---|---|---|\n"
        + table_rows + "\n",
        encoding="utf-8",
    )


class LoadConceptAliasesTests(unittest.TestCase):
    def test_returns_empty_when_registry_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(la.load_concept_aliases(Path(tmp) / "missing.md"), {})

    def test_parses_aliases_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_concepts_registry(root, [
                ("api_v2_design", "api_v2, api2"),
                ("rate_limit", "—"),
                ("latency_budget", "lat_budget"),
            ])
            amap = la.load_concept_aliases(root / "_system/registries/CONCEPTS.md")
            self.assertEqual(amap, {
                "api_v2": "api_v2_design",
                "api2": "api_v2_design",
                "lat_budget": "latency_budget",
            })

    def test_self_alias_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_concepts_registry(root, [
                ("foo_bar", "foo_bar, baz"),
            ])
            amap = la.load_concept_aliases(root / "_system/registries/CONCEPTS.md")
            self.assertEqual(amap, {"baz": "foo_bar"})

    def test_first_canonical_wins_on_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_concepts_registry(root, [
                ("alpha", "shared"),
                ("beta", "shared"),
            ])
            amap = la.load_concept_aliases(root / "_system/registries/CONCEPTS.md")
            self.assertEqual(amap, {"shared": "alpha"})


class ApplyConceptAliasesTests(unittest.TestCase):
    def test_rewrites_old_to_canonical(self):
        fm = {"concepts": ["api_v2", "rate_limit"]}
        new_fm, events = la.apply_concept_aliases(
            fm, {"api_v2": "api_v2_design"}
        )
        self.assertEqual(new_fm["concepts"], ["api_v2_design", "rate_limit"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["fix_id"], "concept-alias-rewrite-autofix")
        self.assertEqual(events[0]["raw"], "api_v2")
        self.assertEqual(events[0]["result"], "api_v2_design")

    def test_dedupes_when_alias_collapses_with_existing(self):
        fm = {"concepts": ["api_v2_design", "api_v2"]}
        new_fm, events = la.apply_concept_aliases(
            fm, {"api_v2": "api_v2_design"}
        )
        self.assertEqual(new_fm["concepts"], ["api_v2_design"])
        self.assertEqual(len(events), 1)

    def test_idempotent_on_canonical_only(self):
        fm = {"concepts": ["api_v2_design"]}
        new_fm, events = la.apply_concept_aliases(
            fm, {"api_v2": "api_v2_design"}
        )
        self.assertEqual(new_fm, fm)
        self.assertEqual(events, [])

    def test_empty_alias_map_no_op(self):
        fm = {"concepts": ["foo", "bar"]}
        new_fm, events = la.apply_concept_aliases(fm, {})
        self.assertEqual(new_fm, fm)
        self.assertEqual(events, [])

    def test_missing_concepts_field_no_op(self):
        new_fm, events = la.apply_concept_aliases({"id": "x"}, {"a": "b"})
        self.assertEqual(new_fm, {"id": "x"})
        self.assertEqual(events, [])


class ApplyAliasesIntegrationTests(unittest.TestCase):
    def test_pipeline_rewrites_then_normalises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_concepts_registry(root, [
                ("api_v2_design", "api_v2, api2"),
            ])
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\n"
                "concepts: [api_v2, api2, latency_budget]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            events = _run(root, mode="fix")
            rewrite = [e for e in events if e["fix_id"] == "concept-alias-rewrite-autofix"]
            self.assertEqual(len(rewrite), 2)
            content = (root / "1_projects" / "n.md").read_text(encoding="utf-8")
            # api_v2 and api2 collapsed into single api_v2_design
            self.assertEqual(content.count("- api_v2_design\n"), 1)
            self.assertNotIn("api_v2\n", content.replace("api_v2_design", "X"))
        clear_minder_memory_env()

    def test_idempotent_after_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_audiences(root)
            _write_concepts_registry(root, [
                ("api_v2_design", "api_v2"),
            ])
            _write_md(
                root / "1_projects" / "n.md",
                "layer: knowledge\nconcepts: [api_v2]\n"
                "origin: personal\naudience_tags: []\nis_sensitive: false\n",
            )
            first = _run(root, mode="fix")
            self.assertGreater(
                len([e for e in first if e["fix_id"] == "concept-alias-rewrite-autofix"]), 0
            )
            second = _run(root, mode="fix")
            self.assertEqual(
                [e for e in second if e["fix_id"] == "concept-alias-rewrite-autofix"], []
            )
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
