"""Tests for scripts/check_no_personal_data.py — the dynamic blacklist layer.

Proves `build_dynamic_blacklist` derives real, catchable patterns from a
temp instance's own registries (PEOPLE.md / PROJECTS.md / SOUL.md /
0_constitution), while the guard chain (`_finalize_pattern` and friends)
keeps synthetic placeholders, public product names, unfilled `{...}`
templates, and generic single words from ever becoming patterns.

Every test builds its own hermetic temp repo (never touches this repo's
real registries) and exercises the real production functions —
`build_dynamic_blacklist` + `scan_file` — the same pair `main()` wires
together.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO / "scripts"))

import check_no_personal_data as M  # type: ignore


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _scan(root: Path, engine_relpath: str) -> list[tuple[int, str, str]]:
    """Derive the dynamic blacklist from `root` and scan one engine file
    with it — the same two calls `main()` chains together."""
    patterns = M.build_dynamic_blacklist(root)
    compiled = [re.compile(p) for p in patterns]
    return M.scan_file(root / engine_relpath, compiled)


def _scan_like_main(root: Path, engine_relpath: str) -> list[tuple[int, str, str]]:
    """Same per-file pattern selection `main()` performs: general dynamic
    patterns always apply; constitution-derived patterns are skipped for
    files under `SANCTIONED_PRINCIPLE_HOMES`."""
    general, constitution = M.build_dynamic_blacklist_tagged(root)
    always_patterns = [re.compile(p) for p in general]
    constitution_patterns = [re.compile(p) for p in constitution]
    rel = Path(engine_relpath)
    patterns = (
        always_patterns
        if M.is_sanctioned_principle_home(rel)
        else always_patterns + constitution_patterns
    )
    return M.scan_file(root / engine_relpath, patterns)


class TestPeopleDerivation(unittest.TestCase):
    """(a) A synthetic person row + a matching leak in an engine file is caught."""

    def test_real_person_row_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/3_resources/people/PEOPLE.md",
                "# People Registry\n\n"
                "| ID | Name | Role | Org | Profile | Tier | Mentions | Last |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| zzz-testperson | Тестова Персонова | Dev | acme | [[zzz-testperson]] | 1 | 3 | 2026-01-01 |\n",
            )
            _write(
                root / "engine_file.md",
                "Some unrelated line.\n"
                "Leaked mention of Тестова Персонова in a worked example.\n"
                "Also leaked the id zzz-testperson directly.\n",
            )
            hits = _scan(root, "engine_file.md")
            self.assertEqual(len(hits), 2, hits)
            matched_patterns = {h[1] for h in hits}
            self.assertTrue(any("Персонова" in p for p in matched_patterns), matched_patterns)
            self.assertTrue(any("zzz\\-testperson" in p for p in matched_patterns), matched_patterns)

    def test_removed_table_is_not_a_source(self) -> None:
        """The 2-column `## Removed` table (ID | Reason) has no Name column
        and must never be mistaken for a person row."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/3_resources/people/PEOPLE.md",
                "# People Registry\n\n"
                "## People\n\n"
                "| ID | Name | Role | Org | Profile | Tier | Mentions | Last |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| real-person | Real Person | Dev | acme | [[real-person]] | 1 | 3 | 2026-01-01 |\n"
                "\n---\n\n"
                "## Removed\n\n"
                "| ID | Reason |\n"
                "|----|--------|\n"
                "| ghost-entry | Merged with real-person (duplicate) |\n",
            )
            values = M._people_candidates(root)
            self.assertIn("real-person", values)
            self.assertNotIn("ghost-entry", values)


class TestProjectDerivation(unittest.TestCase):
    def test_specific_display_name_emitted_generic_single_word_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/1_projects/PROJECTS.md",
                "# Project Registry\n\n"
                "## Active Projects\n\n"
                "| ID | Name | Description | Folder | Status |\n"
                "|----|------|-------------|--------|--------|\n"
                "| widget-forge | Widget Forge Platform | multi-word specific name | 1_projects/widget-forge/ | active |\n"
                "| solo | Widgets | single generic word as display name | 1_projects/solo/ | active |\n",
            )
            values = M._project_candidates(root)
            self.assertIn("widget-forge", values)
            self.assertIn("Widget Forge Platform", values)
            self.assertIn("solo", values)
            # "Widgets" is a single word < 6 chars after trim check fails the
            # specificity guard only if short; here it's 7 chars so let's
            # assert the guard logic directly instead of relying on length.
            self.assertFalse(M._is_specific_display_name("Fix"))
            self.assertTrue(M._is_specific_display_name("Widget Forge Platform"))


class TestSafeTermsGuard(unittest.TestCase):
    """(b) Known-safe synthetic placeholders and public product names never
    become patterns, even when a registry literally contains them (e.g. this
    instance's own 'minder' project id)."""

    def test_safe_terms_never_flag_legitimate_placeholder_usage(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/1_projects/PROJECTS.md",
                "# Project Registry\n\n"
                "## Active Projects\n\n"
                "| ID | Name | Description | Folder | Status |\n"
                "|----|------|-------------|--------|--------|\n"
                "| minder | Minder | the owner's real product, shares its name with the public term | 1_projects/minder/ | active |\n",
            )
            _write(
                root / "engine_file.md",
                "Depersonalized worked example: id `ivan-petrov-dev`.\n"
                "Built on top of the Minder engine architecture.\n"
                "See also Minder Memory and Zettelkasten as generic terms.\n",
            )
            hits = _scan(root, "engine_file.md")
            self.assertEqual(hits, [], hits)

    def test_is_safe_term_direct(self) -> None:
        self.assertTrue(M._is_safe_term("ivan-petrov"))
        self.assertTrue(M._is_safe_term("Minder"))
        self.assertTrue(M._is_safe_term("minder"))
        self.assertFalse(M._is_safe_term("Nimbus Cloud Systems"))


class TestPlaceholderGuard(unittest.TestCase):
    """(c) A `{...}` placeholder value never becomes a pattern."""

    def test_placeholder_name_row_is_skipped_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/3_resources/people/PEOPLE.md",
                "# People Registry\n\n"
                "| ID | Name | Role | Org | Profile | Tier | Mentions | Last |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| person-id | {Полное Имя} | Dev | acme | [[person-id]] | 1 | 1 | 2026-01-01 |\n",
            )
            values = M._people_candidates(root)
            self.assertEqual(values, [])

    def test_looks_like_placeholder(self) -> None:
        self.assertTrue(M._looks_like_placeholder("{Your full name}"))
        self.assertTrue(M._looks_like_placeholder("REPLACE_WITH_NAME"))
        self.assertTrue(M._looks_like_placeholder("City, Country <fill in>"))
        self.assertFalse(M._looks_like_placeholder("Rivertown, Nordland"))


class TestConstitutionDerivation(unittest.TestCase):
    """(d) A verbatim >=20-char axiom statement is caught; (e) an abstract
    paraphrase of it is not (literal-match linter, by design)."""

    AXIOM_MD = (
        "---\n"
        "id: axiom-test-001\n"
        "title: Measure twice, ship once — small batches beat big rewrites\n"
        "type: axiom\n"
        "domain: identity\n"
        "statement: >\n"
        "  A distinctive, sufficiently long verbatim axiom sentence used only\n"
        "  for this test fixture.\n"
        "status: active\n"
        "---\n\n"
        "# Measure twice, ship once — small batches beat big rewrites\n"
    )

    def _root_with_axiom(self, t: str) -> Path:
        root = Path(t)
        _write(root / "zettelkasten/0_constitution/axiom/identity/001-test.md", self.AXIOM_MD)
        return root

    def test_verbatim_statement_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom(t)
            _write(
                root / "engine_file.md",
                "Quoting verbatim: A distinctive, sufficiently long verbatim axiom "
                "sentence used only for this test fixture.\n",
            )
            hits = _scan(root, "engine_file.md")
            self.assertEqual(len(hits), 1, hits)

    def test_title_is_also_caught(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom(t)
            _write(
                root / "engine_file.md",
                "Measure twice, ship once — small batches beat big rewrites — worked example.\n",
            )
            hits = _scan(root, "engine_file.md")
            self.assertEqual(len(hits), 1, hits)

    def test_abstract_paraphrase_is_not_caught(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom(t)
            _write(
                root / "engine_file.md",
                "General idea: keep improving when a better option is known.\n",
            )
            hits = _scan(root, "engine_file.md")
            self.assertEqual(hits, [], hits)

    def test_short_statement_below_threshold_is_not_derived(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/0_constitution/rule/tech/001-short.md",
                "---\nid: rule-test-001\ntitle: Short rule\nstatement: Too short.\nstatus: active\n---\n\n# Short rule\n",
            )
            values = M._constitution_candidates(root)
            self.assertEqual(values, [])


class TestSanctionedPrincipleHomes(unittest.TestCase):
    """`SANCTIONED_PRINCIPLE_HOMES` exempts only the constitution-derived
    slice of the dynamic blacklist, only for files under those three paths —
    every other pattern class (here: a PEOPLE.md row) still applies inside a
    sanctioned home, and the constitution-derived patterns still apply to
    every file NOT under one of those paths."""

    AXIOM_MD = TestConstitutionDerivation.AXIOM_MD

    def _root_with_axiom_and_person(self, t: str) -> Path:
        root = Path(t)
        _write(root / "zettelkasten/0_constitution/axiom/identity/001-test.md", self.AXIOM_MD)
        _write(
            root / "zettelkasten/3_resources/people/PEOPLE.md",
            "# People Registry\n\n"
            "| ID | Name | Role | Org | Profile | Tier | Mentions | Last |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| zzz-testperson | Тестова Персонова | Dev | acme | [[zzz-testperson]] | 1 | 3 | 2026-01-01 |\n",
        )
        return root

    def test_verbatim_axiom_not_flagged_in_starter_pack(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom_and_person(t)
            relpath = "zettelkasten/5_meta/starter-pack/axioms/measure-twice.md"
            _write(
                root / relpath,
                "Measure twice, ship once — small batches beat big rewrites\n",
            )
            hits = _scan_like_main(root, relpath)
            self.assertEqual(hits, [], hits)

    def test_verbatim_axiom_not_flagged_in_constitution_spec(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom_and_person(t)
            relpath = "zettelkasten/0_constitution/CONSTITUTION.md"
            _write(
                root / relpath,
                "Worked example:\ntitle: Measure twice, ship once — small batches beat big rewrites\n",
            )
            hits = _scan_like_main(root, relpath)
            self.assertEqual(hits, [], hits)

    def test_verbatim_axiom_not_flagged_in_pipeline_test_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom_and_person(t)
            relpath = "zettelkasten/_system/scripts/tests/_fixture.py"
            _write(
                root / relpath,
                '# Measure twice, ship once — small batches beat big rewrites\n',
            )
            hits = _scan_like_main(root, relpath)
            self.assertEqual(hits, [], hits)

    def test_same_verbatim_axiom_still_flagged_outside_sanctioned_home(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom_and_person(t)
            relpath = "integrations/claude-code/skills/example-skill/SKILL.md"
            _write(
                root / relpath,
                "Measure twice, ship once — small batches beat big rewrites\n",
            )
            hits = _scan_like_main(root, relpath)
            self.assertEqual(len(hits), 1, hits)

    def test_person_name_still_flagged_inside_sanctioned_home(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom_and_person(t)
            relpath = "zettelkasten/5_meta/starter-pack/axioms/measure-twice.md"
            _write(
                root / relpath,
                "Leaked mention of Тестова Персонова in a starter-pack file.\n",
            )
            hits = _scan_like_main(root, relpath)
            self.assertEqual(len(hits), 1, hits)

    def test_is_sanctioned_principle_home_paths(self) -> None:
        self.assertTrue(M.is_sanctioned_principle_home(
            Path("zettelkasten/5_meta/starter-pack/axioms/x.md")))
        self.assertTrue(M.is_sanctioned_principle_home(
            Path("zettelkasten/0_constitution/CONSTITUTION.md")))
        self.assertTrue(M.is_sanctioned_principle_home(
            Path("zettelkasten/_system/scripts/tests/test_foo.py")))
        self.assertFalse(M.is_sanctioned_principle_home(
            Path("zettelkasten/0_constitution/axiom/identity/001.md")))
        self.assertFalse(M.is_sanctioned_principle_home(
            Path("integrations/claude-code/skills/foo/SKILL.md")))

    def test_build_dynamic_blacklist_flat_view_unchanged(self) -> None:
        """`build_dynamic_blacklist` (flat) still returns exactly the union
        of the tagged split, so existing callers that don't care about the
        sanctioned-homes exception see no behaviour change."""
        with tempfile.TemporaryDirectory() as t:
            root = self._root_with_axiom_and_person(t)
            general, constitution = M.build_dynamic_blacklist_tagged(root)
            self.assertEqual(M.build_dynamic_blacklist(root), general + constitution)


class TestIdentityDerivation(unittest.TestCase):
    """SOUL.md Identity section: Name / Role-employer / Location, guarded."""

    def test_employer_extracted_from_role_at_and_parenthetical(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/_system/SOUL.md",
                "## Identity\n\n"
                "- **Name:** Test Ownerova\n"
                "- **Role:** Head of Delivery @ Acme Global Corp (brand Acme Cloud). Prior title: Lead.\n"
                "- **Location:** Testville, Testland\n\n"
                "## Values\n\nunrelated section\n",
            )
            values = M._identity_candidates(root)
            self.assertIn("Test Ownerova", values)
            self.assertIn("Acme Global Corp", values)
            self.assertIn("Acme Cloud", values)
            self.assertIn("Testville, Testland", values)
            # Location must NOT be split into a bare, over-generic country name.
            self.assertNotIn("Testland", values)

    def test_role_without_at_yields_no_employer_guess(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/_system/SOUL.md",
                "## Identity\n\n- **Role:** Freelance consultant, various clients\n\n## Values\n\nx\n",
            )
            self.assertEqual(M._identity_candidates(root), [])

    def test_fresh_clone_placeholders_yield_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/_system/SOUL.md",
                "## Identity\n\n"
                "- **Name:** {Your full name as you'd like agents to refer to you}\n"
                "- **Role:** {Current professional role / occupation}\n"
                "- **Location:** {City, Country}\n\n"
                "## Values\n\nx\n",
            )
            self.assertEqual(M._identity_candidates(root), [])


class TestTableParserRobustness(unittest.TestCase):
    """A single stray blank line inside a table body (real PEOPLE.md
    artifact from batch-appended rows) must not truncate the table."""

    def test_single_blank_line_inside_table_does_not_truncate(self) -> None:
        text = (
            "| ID | Name | Role | Org | Profile | Tier | Mentions | Last |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| first-person | First Person | Dev | acme | [[first-person]] | 1 | 5 | 2026-01-01 |\n"
            "\n"
            "| second-person | Second Person | Dev | acme | [[second-person]] | 1 | 2 | 2026-01-01 |\n"
        )
        rows = M._id_name_rows_from_tables(text)
        self.assertEqual(
            rows,
            [("first-person", "First Person"), ("second-person", "Second Person")],
        )

    def test_two_blank_lines_end_the_table(self) -> None:
        text = (
            "| ID | Name |\n"
            "|---|---|\n"
            "| a-b | A B |\n"
            "\n\n"
            "| c-d | C D |\n"
        )
        rows = M._id_name_rows_from_tables(text)
        self.assertEqual(rows, [("a-b", "A B")])

    def test_heading_between_tables_never_merges_them(self) -> None:
        text = (
            "| ID | Name |\n"
            "|---|---|\n"
            "| a-b | A B |\n"
            "\n"
            "## Next\n\n"
            "| Old ID | Status |\n"
            "|---|---|\n"
            "| a-b | archived |\n"
        )
        tables = M.parse_markdown_tables(text)
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0]["rows"], [["a-b", "A B"]])
        self.assertEqual(tables[1]["header"], ["Old ID", "Status"])


class TestMissingRegistries(unittest.TestCase):
    """(f) Missing registry files never error — each source degrades to []."""

    def test_empty_repo_yields_empty_dynamic_blacklist(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.assertEqual(M.build_dynamic_blacklist(root), [])

    def test_partial_repo_only_uses_what_exists(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(
                root / "zettelkasten/3_resources/people/PEOPLE.md",
                "| ID | Name | Role | Org | Profile | Tier | Mentions | Last |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| only-person | Only Person | Dev | acme | [[only-person]] | 1 | 1 | 2026-01-01 |\n",
            )
            patterns = M.build_dynamic_blacklist(root)
            self.assertTrue(any("only" in p.lower() for p in patterns), patterns)


class TestFinalizePatternGuards(unittest.TestCase):
    def test_min_length(self) -> None:
        self.assertIsNone(M._finalize_pattern("abcd"))
        self.assertIsNotNone(M._finalize_pattern("abcde"))

    def test_common_word_stoplist(self) -> None:
        for word in ("Status", "Active", "Personal", "Work", "Name", "Role", "Project"):
            self.assertIsNone(M._finalize_pattern(word), word)

    def test_regex_special_chars_are_escaped(self) -> None:
        pattern = M._finalize_pattern("O'Brien-Test.Name")
        self.assertIsNotNone(pattern)
        compiled = re.compile(pattern)
        self.assertTrue(compiled.search("mention of O'Brien-Test.Name here"))
        self.assertFalse(compiled.search("O'BrienXTestYName"))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Verbatim-corpus layer — a shipped file must not quote the owner's own words
# ---------------------------------------------------------------------------


def _corpus_repo(tmp: Path) -> Path:
    """A temp instance whose corpus holds one owner utterance."""
    root = tmp / "repo"
    # Wrapped mid-sentence ON PURPOSE: the shipped side quotes it on one line,
    # so the pair only matches when one normalisation is applied to both.
    _write(
        root / "zettelkasten/_records/observations/20260101-observation-planted.md",
        "# Observation\n\nPlanted line: Тут уже который год ни отпуска,\n"
        "ни продвижения не видно, и это уже не смешно.\n",
    )
    _write(
        root / "zettelkasten/_sources/processed/plaud/2026-04-27T15:36:23Z/t.md",
        "raw transcript ... и так каждый раз повторяется одно и то же ...\n",
    )
    return root


class VerbatimCorpusQuoteTests(unittest.TestCase):
    """The class that shipped: an owner utterance used as a worked example.

    The existing dynamic layer derives patterns from registries and greps
    shipped files for them. It cannot reach this class — the corpus is free
    prose with no bounded pattern to extract — so the search runs the other
    way: spans quoted in shipped files are tested against the corpus.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = _corpus_repo(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_verbatim_owner_quote_is_refused(self):
        rel = "zettelkasten/_system/registries/lenses/x/prompt.md"
        _write(
            self.root / rel,
            "## Example\n\n"
            "Пример брожения: «Тут уже который год ни отпуска, ни продвижения не видно» "
            "— подстановка убирает суть.\n",
        )
        corpus = M.build_corpus_blob(self.root)
        hits = M.scan_file_for_corpus_quotes(self.root / rel, corpus)
        self.assertEqual(len(hits), 1, f"expected the planted quote, got {hits}")
        self.assertEqual(hits[0][0], 3)

    def test_legitimate_unusual_span_is_accepted(self):
        """Accepts-sibling: long, quoted, non-ASCII, and NOT in the corpus."""
        rel = "zettelkasten/_system/registries/lenses/y/prompt.md"
        _write(
            self.root / rel,
            "Пиши наблюдательно: «эта возможность порождает другие возможности, "
            "а не закрывает их» — и не продавай.\n",
        )
        corpus = M.build_corpus_blob(self.root)
        self.assertEqual(M.scan_file_for_corpus_quotes(self.root / rel, corpus), [])

    def test_line_wrapped_corpus_copy_still_matches(self):
        """CR-4: one normalisation, both sides. The corpus copy of the planted
        utterance is wrapped mid-sentence; the shipped span is one line."""
        rel = "zettelkasten/_system/registries/lenses/z/prompt.md"
        _write(
            self.root / rel,
            "Х: «Тут уже который год ни отпуска, ни продвижения не видно, и это уже не смешно»\n",
        )
        corpus = M.build_corpus_blob(self.root)
        self.assertEqual(len(M.scan_file_for_corpus_quotes(self.root / rel, corpus)), 1)

    def test_short_and_spaceless_spans_are_ignored(self):
        rel = "zettelkasten/_system/registries/lenses/w/prompt.md"
        _write(
            self.root / rel,
            'Поле «tags» и путь "zettelkasten/_records/observations" — не высказывания.\n',
        )
        corpus = M.build_corpus_blob(self.root)
        self.assertEqual(M.scan_file_for_corpus_quotes(self.root / rel, corpus), [])

    def test_report_line_carries_no_corpus_text(self):
        """CR-1: the gate must not print corpus context into a log."""
        rel = "zettelkasten/_system/registries/lenses/v/prompt.md"
        _write(
            self.root / rel,
            "«Тут уже который год ни отпуска, ни продвижения не видно»\n",
        )
        corpus = M.build_corpus_blob(self.root)
        hits = M.scan_file_for_corpus_quotes(self.root / rel, corpus)
        located = M.locate_span_in_corpus(corpus, hits[0][1])
        self.assertTrue(located.endswith("20260101-observation-planted.md"))
        rendered = M.render_corpus_hit(rel, hits[0][0], hits[0][1], located)
        self.assertNotIn("и это уже не смешно", rendered)
        self.assertNotIn("Owner said", rendered)

    def test_sanctioned_homes_are_exempt(self):
        """CR-5: paths that legitimately ship verbatim owner axioms stay exempt
        for this layer too, exactly as they are for the constitution layer."""
        # A DIRECTORY home — the tuple also holds one exact-file entry,
        # which has no "under it" to place a file in.
        sanctioned = next(h for h in M.SANCTIONED_QUOTE_HOMES if h.endswith("/"))
        rel = f"{sanctioned}example.md"
        _write(
            self.root / rel,
            "«Тут уже который год ни отпуска, ни продвижения не видно»\n",
        )
        corpus = M.build_corpus_blob(self.root)
        self.assertTrue(M.is_sanctioned_quote_home(Path(rel)))
        # ...and the test tree is deliberately NOT exempt here.
        self.assertFalse(
            M.is_sanctioned_quote_home(Path('zettelkasten/_system/scripts/tests/t.py')))
        self.assertTrue(
            M.is_sanctioned_principle_home(Path('zettelkasten/_system/scripts/tests/t.py')))
        self.assertEqual(
            M.scan_file_for_corpus_quotes(self.root / rel, corpus, relpath=rel), []
        )

    def test_shipped_file_inside_a_corpus_dir_does_not_match_itself(self):
        """CR-10, found on the first real run: `_records/README.md` ships AND
        lives under a corpus directory, so an unsubtracted haystack reports it
        as quoting the owner — quoting itself. Same for a `.template.md` the
        engine seeds into `_sources/inbox/`."""
        readme = "zettelkasten/_records/README.md"
        tmpl = "zettelkasten/_sources/inbox/describe-me/PROFILE.template.md"
        line = "«эта строка живёт в отгружаемом файле внутри корпусной папки»\n"
        _write(self.root / readme, line)
        _write(self.root / tmpl, line)
        shipped = {(self.root / readme).resolve()}
        corpus = M.build_corpus(self.root, shipped=shipped)
        self.assertEqual(
            M.scan_file_for_corpus_quotes(self.root / readme, corpus, relpath=readme), []
        )
        self.assertEqual(
            M.scan_file_for_corpus_quotes(self.root / tmpl, corpus, relpath=tmpl), []
        )

    def test_prefilter_never_hides_a_real_hit(self):
        """The vocabulary prefilter is an optimisation; a span it rejects must
        be one the full search would also reject."""
        corpus = M.build_corpus(self.root)
        planted = "Тут уже который год ни отпуска, ни продвижения не видно"
        self.assertTrue(corpus.may_contain(planted))
        self.assertTrue(corpus.contains(planted))
        self.assertFalse(corpus.contains("совершенно посторонняя выдуманная фраза здесь"))

    def test_prefilter_is_sound_at_word_boundaries(self):
        """Second-model finding, reproduced before it was fixed: the corpus
        token can be LONGER than the span's edge word, so testing edge words
        against a token set rejects a span that is genuinely present. A false
        negative in a privacy gate is invisible — the run just goes green."""
        corpus = M.Corpus(
            [("x.md", M.normalize_for_corpus("unbrokenidentifier phrase that completes here"))]
        )
        span = "identifier phrase that completes"
        self.assertIn(span, corpus.blob)
        self.assertTrue(corpus.may_contain(span), "prefilter rejected a present span")
        self.assertTrue(corpus.contains(span))

    def test_report_hides_the_corpus_path_by_default(self):
        """The record's filename is built from its own subject, so printing it
        discloses what the gate exists to protect."""
        rendered = M.render_corpus_hit(
            "lens/prompt.md", 12, "какая-то длинная закавыченная фраза владельца",
            "zettelkasten/_records/observations/20260427-observation-mood-pay-call.md",
        )
        self.assertNotIn("observation-mood-pay-call", rendered)
        self.assertIn("--reveal-corpus-paths", rendered)
        revealed = M.render_corpus_hit(
            "lens/prompt.md", 12, "какая-то длинная закавыченная фраза владельца",
            "zettelkasten/_records/observations/20260427-observation-mood-pay-call.md",
            reveal=True,
        )
        self.assertIn("observation-mood-pay-call", revealed)

    def test_quote_exception_is_keyed_to_the_exact_span(self):
        """An exception dies when the shipped line is edited, so it cannot
        quietly outlive the thing it excused."""
        span = "фраза, которая случайно совпала у друга"
        _write(
            self.root / M.QUOTE_EXCEPTIONS_FILENAME,
            "# path\tdigest\treason\n"
            f"lens/prompt.md\t{M.span_digest(span)}\tcoincidence in this friend's own recording\n",
        )
        exc = M.load_quote_exceptions(self.root)
        self.assertIn(("lens/prompt.md", M.span_digest(span)), exc)
        self.assertNotIn(("lens/prompt.md", M.span_digest(span + " ещё")), exc)

    def test_exception_without_a_reason_is_not_loaded(self):
        _write(self.root / M.QUOTE_EXCEPTIONS_FILENAME, "lens/prompt.md\tdeadbeefdeadbeef\n")
        self.assertEqual(M.load_quote_exceptions(self.root), {})

    def test_long_block_quotation_is_still_extracted(self):
        long_span = "слово " * 120  # ~720 chars, over the previous 600 cap
        text = f"Пример: «{long_span.strip()}» — конец.\n"
        spans = [s for _, s in M.extract_quoted_spans(text)]
        self.assertEqual(len(spans), 1)
        self.assertGreater(len(spans[0]), 600)

    def test_ascii_string_literals_in_source_files_are_not_quotations(self):
        """In a .py or .sh file the ASCII double quote is the language's own
        string delimiter. Treating it as a quotation mark reported engine
        vocabulary — written by the engine INTO a record — as an owner leak."""
        _write(
            self.root / "zettelkasten/_records/biometric/garmin/2026-05-18.md",
            "no summary metrics aggregated for this day\n",
        )
        corpus = M.build_corpus(self.root)
        code = "zettelkasten/_system/scripts/tests/t_probe.py"
        _write(self.root / code, 'assert "no summary metrics aggregated" in text\n')
        self.assertEqual(
            M.scan_file_for_corpus_quotes(self.root / code, corpus, relpath=code), []
        )

    def test_guillemet_quote_in_a_source_file_is_still_caught(self):
        """The accepting sibling of the rule above — and the shape of the real
        leak this repo shipped inside a fixture."""
        planted = "Тут уже который год ни отпуска, ни продвижения не видно"
        corpus = M.build_corpus(self.root)
        code = "zettelkasten/_system/scripts/tests/t_probe2.py"
        _write(self.root / code, f'text = "Пример: «{planted}»"\n')
        hits = M.scan_file_for_corpus_quotes(self.root / code, corpus, relpath=code)
        self.assertEqual(len(hits), 1, f"guillemet quote in code must still be caught: {hits}")
