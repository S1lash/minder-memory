"""Tests for _common parsing & validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import (  # type: ignore
    BAD_ENUM,
    BAD_ID_SHAPE,
    MALFORMED_YAML,
    VALID_NOTE,
    VALID_PERSONAL_NOTE,
    VALID_SENSITIVE_NOTE,
    clear_minder_memory_env,
    make_fixture,
)
import _common as c  # type: ignore


class ParseFileTests(unittest.TestCase):
    def test_valid_note_parses_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            p = c.parse_file(md)
            self.assertEqual(p.id, "axiom-identity-001")
            self.assertEqual(p.type, "axiom")
            self.assertTrue(p.is_core)
            self.assertEqual(p.scope, "shared")
            self.assertIn("claude-code", p.applies_to)
        clear_minder_memory_env()

    def test_missing_required_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/002.md", MALFORMED_YAML)
            with self.assertRaises(c.SchemaError):
                c.parse_file(md)
        clear_minder_memory_env()

    def test_bad_enum_value_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/003.md", BAD_ENUM)
            with self.assertRaises(c.SchemaError):
                c.parse_file(md)
        clear_minder_memory_env()

    def test_bad_id_shape_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/004.md", BAD_ID_SHAPE)
            with self.assertRaises(c.SchemaError):
                c.parse_file(md)
        clear_minder_memory_env()

    def test_no_frontmatter_raises_parse_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/005.md", "# no frontmatter\njust markdown\n")
            with self.assertRaises(c.ParseError):
                c.parse_file(md)
        clear_minder_memory_env()


class IterPrinciplesTests(unittest.TestCase):
    def test_ignores_constitution_md_and_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            # Top-level protocol doc — must be skipped
            (fx.constitution / "CONSTITUTION.md").write_text("# proto", encoding="utf-8")
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            principles = c.iter_principles(fx.constitution)
            self.assertEqual(len(principles), 1)
            self.assertEqual(principles[0].id, "axiom-identity-001")
        clear_minder_memory_env()

    def test_deterministic_ordering_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_principle("principle/tech/001.md", VALID_PERSONAL_NOTE)
            fx.write_principle("rule/health/001.md", VALID_SENSITIVE_NOTE)
            principles = c.iter_principles(fx.constitution)
            self.assertEqual(
                [p.id for p in principles],
                sorted([p.id for p in principles]),
            )
        clear_minder_memory_env()

    def test_duplicate_id_across_files_fails(self):
        """Two files with the same `id` is a real bug (copy-paste mistake)."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            # Second file with same id but different path
            fx.write_principle("axiom/identity/002.md", VALID_NOTE)
            with self.assertRaises(c.SchemaError) as ctx:
                c.iter_principles(fx.constitution)
            self.assertIn("duplicate id", str(ctx.exception))
        clear_minder_memory_env()

    def test_unicode_title_and_statement_preserved(self):
        """Russian text in title / statement must round-trip cleanly."""
        ru_note = (
            "---\n"
            "id: axiom-identity-001\n"
            "title: Качество — форма уважения к себе и к миру\n"
            "type: axiom\n"
            "domain: identity\n"
            "statement: Выбирай путь качества, когда система переживёт решение.\n"
            "priority_tier: 1\n"
            "scope: shared\n"
            "applies_to: [claude-code]\n"
            "status: active\n"
            "created: 2026-01-01\n"
            "---\n\n"
            "# Title\n\n"
            "## Evidence Trail\n"
            "- **2026-01-01** | landing | — seeded\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/001.md", ru_note)
            p = c.parse_file(md)
            self.assertIn("Качество", p.title)
            self.assertIn("Выбирай", p.statement)
        clear_minder_memory_env()

    def test_symlinks_are_skipped(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            real = fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            link = fx.constitution / "axiom" / "identity" / "002-symlink.md"
            os.symlink(real, link)
            principles = c.iter_principles(fx.constitution)
            # Only the real file, symlink skipped
            self.assertEqual(len(principles), 1)
        clear_minder_memory_env()


class VisibilityTests(unittest.TestCase):
    def test_all_scopes_visible_constant(self):
        """Single-context model: three scopes, all visible."""
        self.assertEqual(
            c.ALL_SCOPES_VISIBLE,
            frozenset({"shared", "personal", "sensitive"}),
        )

    def test_is_visible_excludes_archived_and_placeholder(self):
        """Default exclusion: archived + placeholder never visible."""
        import tempfile
        from tests._fixture import VALID_NOTE  # type: ignore
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            p = c.parse_file(md)
            self.assertTrue(c.is_visible(p, consumer="claude-code"))
            # Simulate a placeholder by using allow_statuses
            placeholder = VALID_NOTE.replace("status: active", "status: placeholder")
            md2 = fx.write_principle("axiom/ethics/001.md",
                                     placeholder.replace("axiom-identity-001", "axiom-ethics-001")
                                                .replace("domain: identity", "domain: ethics"))
            p2 = c.parse_file(md2)
            self.assertFalse(c.is_visible(p2, consumer="claude-code"))
            self.assertTrue(c.is_visible(p2, consumer="claude-code",
                                          allow_statuses={"placeholder"}))
        clear_minder_memory_env()

    def test_is_visible_respects_applies_to(self):
        """Consumer filter uses applies_to inclusion."""
        import tempfile
        from tests._fixture import VALID_NOTE  # type: ignore
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            md = fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            p = c.parse_file(md)
            self.assertTrue(c.is_visible(p, consumer="claude-code"))
            self.assertFalse(c.is_visible(p, consumer="minder"))
        clear_minder_memory_env()


class SoulMarkersTests(unittest.TestCase):
    def test_finds_bounds_when_markers_present(self):
        text = (
            "before\n"
            f"{c.SOUL_MARKER_START}\n"
            "auto-content\n"
            f"{c.SOUL_MARKER_END}\n"
            "after\n"
        )
        bounds = c.find_soul_auto_zone(text)
        self.assertIsNotNone(bounds)
        start, end = bounds
        self.assertEqual(text[start:end], "auto-content\n")

    def test_none_when_markers_missing(self):
        self.assertIsNone(c.find_soul_auto_zone("no markers here"))


class NormalizeConceptNameTests(unittest.TestCase):
    """CONCEPT_NAMING.md autonomous heuristic — happy + edge cases."""

    def test_passthrough_canonical(self):
        self.assertEqual(c.normalize_concept_name("office_move"),
                         "office_move")

    def test_kebab_to_snake(self):
        self.assertEqual(c.normalize_concept_name("office-move"),
                         "office_move")

    def test_uppercase_to_lower(self):
        self.assertEqual(c.normalize_concept_name("Office-Move"),
                         "office_move")

    def test_em_dash_separator(self):
        self.assertEqual(c.normalize_concept_name("office — move"),
                         "office_move")

    def test_diacritic_fold(self):
        self.assertEqual(c.normalize_concept_name("naïve_bayes"),
                         "naive_bayes")

    def test_drops_non_ascii_residue(self):
        self.assertIsNone(c.normalize_concept_name("тема"))

    def test_type_prefix_is_not_stripped(self):
        # No mechanical type-prefix strip: a name that merely STARTS with a
        # type word is kept verbatim. The blind helper cannot tell a
        # redundant label from a compound, so it never guesses (a wrong
        # strip would corrupt graph identity).
        for name in (
            "theme_queue_prioritization",
            "skill_python",
            "tool_qdrant",
        ):
            self.assertEqual(c.normalize_concept_name(name), name)

    def test_compound_concepts_kept_intact(self):
        # The whole point: type-word + anything is preserved. These were the
        # real corruptions before the fix (`decision_making`→`making`,
        # `value_chain`→`chain`, `event_loop_blocking`→`loop_blocking`).
        for name in (
            "decision_making",
            "value_chain",
            "goal_setting",
            "skill_set",
            "skill_based_tournament_calibration",
            "value_added_reseller",
            "event_driven_architecture",
            "event_loop_blocking",
            "project_status_update",
            "fact_checking",
            "idea_generation",
        ):
            self.assertEqual(c.normalize_concept_name(name), name)

    def test_drops_bare_reserved_type_word(self):
        # Rule 8: a name that IS exactly a type word drops (too broad to be
        # a concept). `theme_` trims to `theme` and drops the same way.
        self.assertIsNone(c.normalize_concept_name("theme"))
        self.assertIsNone(c.normalize_concept_name("skill"))
        self.assertIsNone(c.normalize_concept_name("theme_"))

    def test_drops_when_empty_after_strip(self):
        self.assertIsNone(c.normalize_concept_name(""))
        self.assertIsNone(c.normalize_concept_name("   "))
        self.assertIsNone(c.normalize_concept_name("___"))

    def test_collapses_runs_of_underscores(self):
        self.assertEqual(c.normalize_concept_name("office___move"),
                         "office_move")

    def test_truncates_overlength(self):
        long_name = "a_" * 40 + "tail"
        result = c.normalize_concept_name(long_name)
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), 64)

    def test_punctuation_separators(self):
        self.assertEqual(c.normalize_concept_name("Node.js (v18)"),
                         "node_js_v18")

    def test_acronym_kept_lowercase(self):
        self.assertEqual(c.normalize_concept_name("OAuth"), "oauth")
        self.assertEqual(c.normalize_concept_name("p2p"), "p2p")

    def test_handles_none_input(self):
        self.assertIsNone(c.normalize_concept_name(None))

    def test_no_transliteration_heuristic(self):
        # Translation is the LLM's contract in /minder:mem:process Q15. There is
        # no mechanical transliteration-detector — its false-positive cost
        # (legitimate English borrowings like `intelligentsia`) outweighs
        # its narrow Russian-morphology hit rate. If the model slips, the
        # phantom node is the visible cost; the engine does not guess.
        self.assertEqual(
            c.normalize_concept_name("intelligentsia"), "intelligentsia"
        )
        self.assertEqual(
            c.normalize_concept_name("restrukturizatsiya"),
            "restrukturizatsiya",
        )
        self.assertEqual(
            c.normalize_concept_name("borshch_recipe"), "borshch_recipe"
        )
        self.assertEqual(c.normalize_concept_name("ratio"), "ratio")


class NormalizeConceptListTests(unittest.TestCase):
    def test_dedupes_after_normalisation(self):
        result = c.normalize_concept_list([
            "Office-Move", "office_move", "OFFICE-move"
        ])
        self.assertEqual(result, ["office_move"])

    def test_preserves_first_seen_order(self):
        result = c.normalize_concept_list(["alpha", "beta", "gamma"])
        self.assertEqual(result, ["alpha", "beta", "gamma"])

    def test_drops_unresolvable_keeps_others(self):
        result = c.normalize_concept_list(["valid_one", "тема", "valid_two"])
        self.assertEqual(result, ["valid_one", "valid_two"])

    def test_empty_input_empty_output(self):
        self.assertEqual(c.normalize_concept_list([]), [])
        self.assertEqual(c.normalize_concept_list(None), [])


class NormalizeAudienceTagTests(unittest.TestCase):
    def test_canonical_passthrough(self):
        for tag in ("family", "friends", "work",
                    "professional-network", "world"):
            self.assertEqual(c.normalize_audience_tag(tag), tag)

    def test_uppercase_normalised(self):
        self.assertEqual(c.normalize_audience_tag("Family"), "family")

    def test_underscore_to_hyphen(self):
        self.assertEqual(c.normalize_audience_tag("professional_network"),
                         "professional-network")

    def test_drops_non_ascii(self):
        self.assertIsNone(c.normalize_audience_tag("семья"))

    def test_drops_too_short(self):
        self.assertIsNone(c.normalize_audience_tag("a"))

    def test_drops_too_long(self):
        self.assertIsNone(c.normalize_audience_tag("a" * 33))

    def test_passes_through_well_formed_extension(self):
        # caller decides accept/drop based on AUDIENCES.md Extensions
        self.assertEqual(c.normalize_audience_tag("team-platform"),
                         "team-platform")


class NormalizePortableNameTests(unittest.TestCase):
    def test_iso_timestamp_colons_to_hyphens(self):
        self.assertEqual(c.normalize_portable_name("2026-04-29T14:09:30Z"),
                         "2026-04-29T14-09-30Z")

    def test_iso_with_topic_suffix(self):
        self.assertEqual(
            c.normalize_portable_name("2026-04-29T14:09:30Z_short topic"),
            "2026-04-29T14-09-30Z_short topic")

    def test_portable_name_passthrough(self):
        for name in ("2026-04-29T14-09-30Z", "2026-04-29_short-topic",
                     "transcript_with_summary.md", "20260408-meeting.md"):
            self.assertEqual(c.normalize_portable_name(name), name)

    def test_idempotent(self):
        once = c.normalize_portable_name("2026-04-29T14:09:30Z*?")
        self.assertEqual(c.normalize_portable_name(once), once)

    def test_all_illegal_chars_replaced(self):
        self.assertEqual(c.normalize_portable_name('a<b>c:d"e/f\\g|h?i*j'),
                         "a-b-c-d-e-f-g-h-i-j")

    def test_control_chars_replaced(self):
        self.assertEqual(c.normalize_portable_name("a\x07b"), "a-b")

    def test_trailing_dots_and_spaces_stripped(self):
        self.assertEqual(c.normalize_portable_name("note. . "), "note")

    def test_reserved_basename_prefixed(self):
        self.assertEqual(c.normalize_portable_name("con"), "_con")
        self.assertEqual(c.normalize_portable_name("CON.md"), "_CON.md")
        self.assertEqual(c.normalize_portable_name("lpt3"), "_lpt3")

    def test_reserved_prefix_is_idempotent(self):
        self.assertEqual(c.normalize_portable_name("_con.md"), "_con.md")

    def test_non_reserved_lookalike_untouched(self):
        self.assertEqual(c.normalize_portable_name("console.md"),
                         "console.md")

    def test_unicode_preserved(self):
        # portability targets the filesystem, not ASCII — Cyrillic stays
        self.assertEqual(c.normalize_portable_name("Идея: сервер"),
                         "Идея- сервер")

    def test_empty_and_none_dropped(self):
        self.assertIsNone(c.normalize_portable_name(None))
        self.assertIsNone(c.normalize_portable_name(""))
        self.assertIsNone(c.normalize_portable_name(" . "))
        self.assertIsNone(c.normalize_portable_name("..."))

    def test_is_portable_name(self):
        self.assertTrue(c.is_portable_name("2026-04-29T14-09-30Z"))
        self.assertFalse(c.is_portable_name("2026-04-29T14:09:30Z"))
        self.assertFalse(c.is_portable_name(None))


class RecomputeHubTrioTests(unittest.TestCase):
    """Hub privacy derivation: dominant origin / audience intersection /
    sensitivity contagion. Owner-set fields ALWAYS preserved."""

    def test_empty_members_uses_conservative_defaults(self):
        fm, events = c.recompute_hub_trio({}, [])
        self.assertEqual(fm["origin"], "personal")
        self.assertEqual(fm["audience_tags"], [])
        self.assertFalse(fm["is_sensitive"])
        self.assertEqual(len(events), 3)

    def test_dominant_origin_wins(self):
        members = [
            {"origin": "work"},
            {"origin": "work"},
            {"origin": "personal"},
        ]
        fm, _ = c.recompute_hub_trio({}, members)
        self.assertEqual(fm["origin"], "work")

    def test_origin_tie_breaks_to_personal(self):
        members = [
            {"origin": "work"},
            {"origin": "personal"},
        ]
        fm, _ = c.recompute_hub_trio({}, members)
        self.assertEqual(fm["origin"], "personal")

    def test_audience_intersection_fail_closed(self):
        members = [
            {"audience_tags": ["work", "friends"]},
            {"audience_tags": ["work"]},
            {"audience_tags": []},  # one member at owner-only collapses set
        ]
        fm, _ = c.recompute_hub_trio({}, members)
        self.assertEqual(fm["audience_tags"], [])

    def test_audience_intersection_when_all_agree(self):
        members = [
            {"audience_tags": ["work", "friends"]},
            {"audience_tags": ["work", "friends"]},
        ]
        fm, _ = c.recompute_hub_trio({}, members)
        self.assertEqual(fm["audience_tags"], ["friends", "work"])

    def test_sensitivity_contagion(self):
        members = [
            {"is_sensitive": False},
            {"is_sensitive": True},
            {"is_sensitive": False},
        ]
        fm, _ = c.recompute_hub_trio({}, members)
        self.assertTrue(fm["is_sensitive"])

    def test_owner_set_origin_preserved(self):
        """If hub.origin already set, derivation does not overwrite."""
        members = [{"origin": "work"}, {"origin": "work"}]
        fm, events = c.recompute_hub_trio({"origin": "personal"}, members)
        self.assertEqual(fm["origin"], "personal")
        self.assertNotIn("hub-origin-derive-autofix",
                         {e["fix_id"] for e in events})

    def test_owner_set_audience_preserved(self):
        members = [{"audience_tags": []}]
        fm, events = c.recompute_hub_trio(
            {"audience_tags": ["work"]}, members
        )
        self.assertEqual(fm["audience_tags"], ["work"])
        self.assertNotIn("hub-audience-derive-autofix",
                         {e["fix_id"] for e in events})

    def test_owner_set_is_sensitive_preserved(self):
        members = [{"is_sensitive": True}]
        fm, events = c.recompute_hub_trio(
            {"is_sensitive": False}, members
        )
        self.assertFalse(fm["is_sensitive"])
        self.assertNotIn("hub-sensitivity-derive-autofix",
                         {e["fix_id"] for e in events})

    def test_partial_owner_set_only_missing_filled(self):
        """Owner set origin only; audience and is_sensitive derived."""
        members = [
            {"origin": "work", "audience_tags": ["work"], "is_sensitive": True},
        ]
        fm, events = c.recompute_hub_trio({"origin": "personal"}, members)
        self.assertEqual(fm["origin"], "personal")  # preserved
        self.assertEqual(fm["audience_tags"], ["work"])  # derived
        self.assertTrue(fm["is_sensitive"])  # derived
        ids = {e["fix_id"] for e in events}
        self.assertIn("hub-audience-derive-autofix", ids)
        self.assertIn("hub-sensitivity-derive-autofix", ids)
        self.assertNotIn("hub-origin-derive-autofix", ids)

    def test_idempotent_after_full_set(self):
        """Running twice on a fully-set hub produces zero events."""
        fm, _ = c.recompute_hub_trio({}, [{"origin": "work"}])
        _, events_again = c.recompute_hub_trio(fm, [{"origin": "work"}])
        self.assertEqual(events_again, [])

    def test_engine_derived_marker_added_on_first_touch(self):
        """First derive populates _engine_derived list with all
        derived field names so the engine knows it owns them."""
        fm, _ = c.recompute_hub_trio({}, [{"origin": "work"}])
        self.assertEqual(
            fm["_engine_derived"],
            ["audience_tags", "is_sensitive", "origin"],
        )

    def test_engine_owned_field_rederived_when_members_change(self):
        """If a field is in _engine_derived, engine re-derives on
        member change — owner sees continuous tracking, not stale value."""
        fm, _ = c.recompute_hub_trio({}, [{"origin": "personal"}])
        self.assertEqual(fm["origin"], "personal")
        # Members shifted to work-dominant; expect engine to follow.
        fm2, events = c.recompute_hub_trio(
            fm, [{"origin": "work"}, {"origin": "work"}]
        )
        self.assertEqual(fm2["origin"], "work")
        rederive = [e for e in events if e["fix_id"] == "hub-origin-derive-autofix"]
        self.assertEqual(len(rederive), 1)
        self.assertEqual(rederive[0]["reason"], "rederived")
        self.assertEqual(rederive[0]["before"], "personal")

    def test_owner_takeover_via_marker_removal(self):
        """Owner removes 'origin' from _engine_derived → engine stops
        re-deriving that field; value preserved across runs."""
        fm, _ = c.recompute_hub_trio({}, [{"origin": "personal"}])
        # Owner edits: keeps origin: personal but removes from marker.
        fm["_engine_derived"] = ["audience_tags", "is_sensitive"]
        fm2, events = c.recompute_hub_trio(
            fm, [{"origin": "work"}, {"origin": "work"}]
        )
        self.assertEqual(fm2["origin"], "personal")  # preserved
        origin_events = [
            e for e in events if e["fix_id"] == "hub-origin-derive-autofix"
        ]
        self.assertEqual(origin_events, [])

    def test_legacy_field_without_marker_treated_as_owner_set(self):
        """Backward compat: hub with origin set but NO _engine_derived
        marker (created before marker existed) → engine treats as owner-set."""
        fm, events = c.recompute_hub_trio(
            {"origin": "personal"}, [{"origin": "work"}, {"origin": "work"}]
        )
        self.assertEqual(fm["origin"], "personal")
        origin_events = [
            e for e in events if e["fix_id"] == "hub-origin-derive-autofix"
        ]
        self.assertEqual(origin_events, [])
        # Marker captures only newly-engine-derived fields.
        self.assertEqual(
            fm["_engine_derived"], ["audience_tags", "is_sensitive"]
        )


class NormalizeDomainTests(unittest.TestCase):
    """`normalize_domain`: kebab-case ASCII output, slash-prefix policy,
    fail-closed on irrecoverable shape."""

    def test_canonical_passthrough(self):
        for d in ["work", "career", "personal", "ai-interaction", "meta"]:
            self.assertEqual(c.normalize_domain(d), d)

    def test_lowercase(self):
        self.assertEqual(c.normalize_domain("Work"), "work")
        self.assertEqual(c.normalize_domain("AI-Interaction"), "ai-interaction")

    def test_snake_to_kebab(self):
        self.assertEqual(c.normalize_domain("ai_interaction"), "ai-interaction")

    def test_slash_returns_none_on_strict_normalise(self):
        # `normalize_domain` is strict single-value; slash is not a valid
        # character in the kebab-case alphabet. Callers needing slash
        # expansion use `expand_domain_entry` instead.
        self.assertIsNone(c.normalize_domain("work/process"))
        self.assertIsNone(c.normalize_domain("personal/psychology"))
        self.assertIsNone(c.normalize_domain("work/team/sub"))

    def test_whitespace_strip(self):
        self.assertEqual(c.normalize_domain("  health  "), "health")

    def test_collapses_separators(self):
        self.assertEqual(c.normalize_domain("ai__interaction"), "ai-interaction")
        self.assertEqual(c.normalize_domain("ai - - interaction"), "ai-interaction")

    def test_empty_returns_none(self):
        self.assertIsNone(c.normalize_domain(""))
        self.assertIsNone(c.normalize_domain("   "))
        self.assertIsNone(c.normalize_domain("/"))

    def test_none_returns_none(self):
        self.assertIsNone(c.normalize_domain(None))

    def test_too_short(self):
        self.assertIsNone(c.normalize_domain("a"))

    def test_too_long(self):
        self.assertIsNone(c.normalize_domain("x" * 33))

    def test_non_ascii_drops(self):
        self.assertIsNone(c.normalize_domain("тема"))


class ExpandDomainEntryTests(unittest.TestCase):
    """Slash-aware expansion: single raw entry → list of normalised parts."""

    def test_no_slash_single_entry(self):
        self.assertEqual(c.expand_domain_entry("work"), ["work"])

    def test_slash_splits_two(self):
        self.assertEqual(c.expand_domain_entry("work/learning"), ["work", "learning"])

    def test_slash_splits_three(self):
        self.assertEqual(
            c.expand_domain_entry("work/learning/career"),
            ["work", "learning", "career"],
        )

    def test_each_part_normalised(self):
        self.assertEqual(
            c.expand_domain_entry("Work/AI_Interaction"),
            ["work", "ai-interaction"],
        )

    def test_format_unfixable_part_dropped(self):
        # тема fails normalize → just `work` returned
        self.assertEqual(c.expand_domain_entry("work/тема"), ["work"])

    def test_dedup_preserves_order(self):
        self.assertEqual(c.expand_domain_entry("work/work"), ["work"])

    def test_empty_returns_empty_list(self):
        self.assertEqual(c.expand_domain_entry(""), [])
        self.assertEqual(c.expand_domain_entry(None), [])
        self.assertEqual(c.expand_domain_entry("/"), [])

    def test_non_string_returns_empty(self):
        self.assertEqual(c.expand_domain_entry(123), [])
        self.assertEqual(c.expand_domain_entry(["work"]), [])


class NormalizeDomainListTests(unittest.TestCase):
    def test_default_accept_set_is_canonical(self):
        result = c.normalize_domain_list(["work", "career", "junk"])
        self.assertEqual(result, ["work", "career"])

    def test_dedupes_after_normalisation(self):
        result = c.normalize_domain_list(["Work", "work", "WORK"])
        self.assertEqual(result, ["work"])

    def test_preserves_first_seen_order(self):
        result = c.normalize_domain_list(["health", "work", "career"])
        self.assertEqual(result, ["health", "work", "career"])

    def test_explicit_accept_set_with_extension(self):
        result = c.normalize_domain_list(
            ["work", "custom-ext"], accept_set={"work", "custom-ext"},
        )
        self.assertEqual(result, ["work", "custom-ext"])

    def test_drops_format_unfixable(self):
        result = c.normalize_domain_list(["work", "тема", "career"])
        self.assertEqual(result, ["work", "career"])

    def test_empty_input(self):
        self.assertEqual(c.normalize_domain_list([]), [])
        self.assertEqual(c.normalize_domain_list(None), [])

    def test_slash_expansion_both_canonical_kept(self):
        result = c.normalize_domain_list(["work/learning"])
        self.assertEqual(result, ["work", "learning"])

    def test_slash_expansion_suffix_filtered(self):
        # `process` not in canonical → only `work` survives
        result = c.normalize_domain_list(["work/process"])
        self.assertEqual(result, ["work"])

    def test_slash_with_extension_in_accept(self):
        result = c.normalize_domain_list(
            ["work/gardening"],
            accept_set=set(c.ALLOWED_DOMAINS) | {"gardening"},
        )
        self.assertEqual(result, ["work", "gardening"])


class ParseExtensionsTableTests(unittest.TestCase):
    """Generic Extensions parser used by both AUDIENCES.md and DOMAINS.md."""

    def test_missing_file_returns_empty(self):
        self.assertEqual(c.parse_extensions_table(Path("/nonexistent.md")), set())

    def test_no_extensions_block_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.md"
            p.write_text("# No markers here", encoding="utf-8")
            self.assertEqual(c.parse_extensions_table(p), set())

    def test_empty_block(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.md"
            p.write_text(
                "<!-- BEGIN extensions -->\n"
                "| Domain | Added | Status | Purpose | Notes |\n"
                "|---|---|---|---|---|\n"
                "| _(none yet)_ | — | — | — | — |\n"
                "<!-- END extensions -->\n",
                encoding="utf-8",
            )
            self.assertEqual(c.parse_extensions_table(p), set())

    def test_active_entries_collected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.md"
            p.write_text(
                "<!-- BEGIN extensions -->\n"
                "| Domain | Added | Status | Purpose | Notes |\n"
                "|---|---|---|---|---|\n"
                "| gardening | 2026-05-01 | active | hobby | — |\n"
                "| spouse | 2026-04-01 | active | one-person | — |\n"
                "<!-- END extensions -->\n",
                encoding="utf-8",
            )
            self.assertEqual(c.parse_extensions_table(p), {"gardening", "spouse"})

    def test_deprecated_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.md"
            p.write_text(
                "<!-- BEGIN extensions -->\n"
                "| Domain | Added | Status | Purpose | Notes |\n"
                "|---|---|---|---|---|\n"
                "| gardening | 2026-05-01 | active | hobby | — |\n"
                "| oldtag | 2025-01-01 | deprecated:2026-04-01 | — | retired |\n"
                "<!-- END extensions -->\n",
                encoding="utf-8",
            )
            self.assertEqual(c.parse_extensions_table(p), {"gardening"})

    def test_canonical_conflict_silently_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.md"
            p.write_text(
                "<!-- BEGIN extensions -->\n"
                "| Domain | Added | Status | Purpose | Notes |\n"
                "|---|---|---|---|---|\n"
                "| gardening | 2026-05-01 | active | hobby | — |\n"
                "| Work | 2026-05-01 | active | typo | — |\n"
                "| HEALTH | 2026-05-01 | active | shouted | — |\n"
                "<!-- END extensions -->\n",
                encoding="utf-8",
            )
            # `Work` and `HEALTH` case-fold to canonical → silent drop
            result = c.parse_extensions_table(
                p, canonical_blacklist=c.ALLOWED_DOMAINS,
            )
            self.assertEqual(result, {"gardening"})

    def test_no_blacklist_param_keeps_all(self):
        # Without blacklist, parser doesn't reject canonical-named entries
        # (backward compat with audience callers that don't pass it yet).
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.md"
            p.write_text(
                "<!-- BEGIN extensions -->\n"
                "| Domain | Added | Status | Purpose | Notes |\n"
                "|---|---|---|---|---|\n"
                "| gardening | 2026-05-01 | active | hobby | — |\n"
                "| Work | 2026-05-01 | active | typo | — |\n"
                "<!-- END extensions -->\n",
                encoding="utf-8",
            )
            result = c.parse_extensions_table(p)
            self.assertEqual(result, {"gardening", "Work"})


class ValidateFrontmatterDomainNormalisationTests(unittest.TestCase):
    """Closes Phase-1 latent defect: principles with normalisable but
    non-canonical domain values (snake-case, mixed case) must not raise
    SchemaError. validate_frontmatter normalises in place before enum check.
    """

    def _principle(self, domain_value: str) -> dict:
        return {
            "id": f"principle-{domain_value}-001",  # raw form for prefix check
            "title": "test",
            "type": "principle",
            "domain": domain_value,
            "statement": "irrelevant",
            "priority_tier": 1,
            "scope": "shared",
            "applies_to": [],
            "status": "active",
        }

    def test_canonical_passthrough(self):
        fm = self._principle("ai-interaction")
        c.validate_frontmatter(Path("/tmp/fake.md"), fm)
        self.assertEqual(fm["domain"], "ai-interaction")

    def test_snake_case_rewrites_in_place(self):
        fm = {
            "id": "principle-ai-interaction-001",
            "title": "test", "type": "principle",
            "domain": "ai_interaction",  # snake input
            "statement": "x", "priority_tier": 1, "scope": "shared",
            "applies_to": [], "status": "active",
        }
        c.validate_frontmatter(Path("/tmp/fake.md"), fm)
        self.assertEqual(fm["domain"], "ai-interaction")

    def test_mixed_case_rewrites(self):
        fm = {
            "id": "principle-work-001",
            "title": "test", "type": "principle",
            "domain": "Work",
            "statement": "x", "priority_tier": 1, "scope": "shared",
            "applies_to": [], "status": "active",
        }
        c.validate_frontmatter(Path("/tmp/fake.md"), fm)
        self.assertEqual(fm["domain"], "work")

    def test_unfixable_domain_still_raises(self):
        fm = {
            "id": "principle-junk-001",
            "title": "test", "type": "principle",
            "domain": "junk",  # not in canonical, well-formed
            "statement": "x", "priority_tier": 1, "scope": "shared",
            "applies_to": [], "status": "active",
        }
        with self.assertRaises(c.SchemaError):
            c.validate_frontmatter(Path("/tmp/fake.md"), fm)


class AllowedDomainsExtensionTests(unittest.TestCase):
    """Lock the canonical 13 in place — changes here require coordinated
    edits to DOMAINS.md and the corresponding test fixtures."""

    def test_canonical_count(self):
        self.assertEqual(len(c.ALLOWED_DOMAINS), 13)

    def test_all_thirteen_present(self):
        expected = {
            "work", "career", "personal",
            "identity", "ethics", "health",
            "relationships",
            "learning", "money", "time",
            "ai-interaction", "tech", "meta",
        }
        self.assertEqual(set(c.ALLOWED_DOMAINS), expected)

    def test_minder_concept_domain_mirror(self):
        self.assertEqual(
            set(c.MINDER_CONCEPT_DOMAIN),
            {"work", "personal", "mixed", "unknown"},
        )


class TestConceptTypeMirror(unittest.TestCase):
    """Parity test: CONCEPT_TYPES_ALL must mirror Java enum verbatim.

    Reads the Minder ConceptType.java file at test time and parses enum
    constants. Skipped (with note) if the Java source is not reachable
    from this checkout — friend instances of the engine do not have the
    Minder repo siblinged. Runs as hard assertion in owner's environment.
    """

    # Search pattern for the upstream Minder ConceptType.java enum
    # source. Owner-package-agnostic so the engine repo carries no
    # personal data in tests; resolution happens via filesystem glob
    # at test time. Override via env var MINDER_MEMORY_CONCEPT_TYPE_JAVA when
    # the file lives elsewhere.
    JAVA_FILENAME = "ConceptType.java"
    JAVA_GLOB_SUFFIX = "minder/domain/graph/ConceptType.java"

    @classmethod
    def _find_java_source(cls) -> Path | None:
        import os
        env_override = os.environ.get("MINDER_MEMORY_CONCEPT_TYPE_JAVA")
        if env_override:
            p = Path(env_override)
            return p if p.exists() else None
        here = Path(__file__).resolve()
        # Walk up looking for any descendant matching the path suffix.
        for parent in here.parents:
            for match in parent.rglob(cls.JAVA_FILENAME):
                if match.as_posix().endswith(cls.JAVA_GLOB_SUFFIX):
                    return match
            # Don't recurse past 6 ancestors — bounded scan.
            if len(parent.parts) <= 3:
                break
        return None

    def test_concept_types_all_size_is_18(self):
        self.assertEqual(len(c.CONCEPT_TYPES_ALL), 18)

    def test_emitted_concept_types_size_is_16(self):
        self.assertEqual(len(c.EMITTED_CONCEPT_TYPES), 16)

    def test_emitted_excludes_person_and_project(self):
        self.assertNotIn("person", c.EMITTED_CONCEPT_TYPES)
        self.assertNotIn("project", c.EMITTED_CONCEPT_TYPES)
        self.assertEqual(c.CONCEPT_TYPES_ALL - c.EMITTED_CONCEPT_TYPES, {"person", "project"})

    def test_descriptions_cover_all_types(self):
        self.assertEqual(set(c.CONCEPT_TYPE_DESCRIPTIONS.keys()), set(c.CONCEPT_TYPES_ALL))
        for code, desc in c.CONCEPT_TYPE_DESCRIPTIONS.items():
            self.assertTrue(desc, f"Empty description for {code}")
            self.assertIsInstance(desc, str)

    def test_validate_concept_type(self):
        self.assertTrue(c.validate_concept_type("idea"))
        self.assertTrue(c.validate_concept_type("organization"))
        self.assertFalse(c.validate_concept_type("person"))
        self.assertFalse(c.validate_concept_type("project"))
        self.assertFalse(c.validate_concept_type("IDEA"))
        self.assertFalse(c.validate_concept_type(""))
        self.assertFalse(c.validate_concept_type(None))
        self.assertFalse(c.validate_concept_type("bogus"))

    def test_normalize_concept_type(self):
        self.assertEqual(c.normalize_concept_type("IDEA"), "idea")
        self.assertEqual(c.normalize_concept_type("  Tool  "), "tool")
        self.assertIsNone(c.normalize_concept_type("person"))
        self.assertIsNone(c.normalize_concept_type("Project"))
        self.assertIsNone(c.normalize_concept_type(""))
        self.assertIsNone(c.normalize_concept_type(None))
        self.assertIsNone(c.normalize_concept_type("unknown"))

    def test_java_enum_parity(self):
        """Snapshot test: CONCEPT_TYPES_ALL == codes parsed from Java source."""
        src = self._find_java_source()
        if src is None:
            self.skipTest(
                "Java enum source not reachable from this checkout — "
                "parity test only runs in environments with minder repo siblinged"
            )
        text = src.read_text(encoding="utf-8")
        # Match `IDENT("code", "description")` lines inside the enum body.
        # Tolerates leading whitespace, trailing commas/semicolons.
        import re
        pattern = re.compile(r'^\s*[A-Z_]+\s*\(\s*"([a-z_]+)"\s*,', re.MULTILINE)
        codes = set(pattern.findall(text))
        self.assertEqual(
            codes, set(c.CONCEPT_TYPES_ALL),
            f"Java enum drift: java={codes - set(c.CONCEPT_TYPES_ALL)} "
            f"python={set(c.CONCEPT_TYPES_ALL) - codes}",
        )


class CognitiveFieldTests(unittest.TestCase):
    def _p(self, fm):
        return c.Principle(path=Path("x.md"), frontmatter=fm, body="")

    def test_cognitive_axes_dedup_and_nonlist(self):
        self.assertEqual(
            self._p({"cognitive_axes": ["a", "a", "b"]}).cognitive_axes, ["a", "b"])
        self.assertEqual(self._p({"cognitive_axes": "a"}).cognitive_axes, [])
        self.assertEqual(self._p({}).cognitive_axes, [])

    def test_source_quote(self):
        self.assertEqual(self._p({"source_quote": "  demo > слова "}).source_quote,
                         "demo > слова")
        self.assertEqual(self._p({"source_quote": 5}).source_quote, "")
        self.assertEqual(self._p({}).source_quote, "")


# A well-formed knowledge note: fence closes before any body heading.
_GOOD_NOTE = """\
---
id: insight-demo
layer: knowledge
type: insight
---

## Связи

- [[record-demo]]

## Evidence Trail

- **2026-05-05** | [[record-demo]] — initial

## Source

- [[record-demo]]
"""

# The F8 corruption: `## Evidence Trail` + bullet land inside the fence,
# so the intended closing `---` sits after `## Source`.
_BROKEN_NOTE = """\
---
id: insight-demo
layer: knowledge
type: insight
## Evidence Trail

- **2026-05-05** | [[record-demo]] — initial

## Source

- [[record-demo]]
---

## Связи

- [[record-demo]]
"""


class FrontmatterFenceTests(unittest.TestCase):
    def _write(self, tmp: str, text: str) -> Path:
        p = Path(tmp) / "note.md"
        p.write_text(text, encoding="utf-8")
        return p

    def test_good_note_passes_guard_and_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, _GOOD_NOTE)
            self.assertTrue(c.frontmatter_closed_before_body(p))
            self.assertIsNotNone(c.read_frontmatter(p))

    def test_broken_note_fails_guard_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, _BROKEN_NOTE)
            # red: the corruption is detected structurally AND breaks the parser
            self.assertFalse(c.frontmatter_closed_before_body(p))
            self.assertIsNone(c.read_frontmatter(p))

    def test_file_without_frontmatter_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "# Registry\n\n## Section\n\nbody\n")
            self.assertTrue(c.frontmatter_closed_before_body(p))

    def test_repair_fixes_broken_note_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, _BROKEN_NOTE)
            self.assertTrue(c.repair_misplaced_fence(p))
            # green: now guard passes, YAML parses, body sections preserved
            self.assertTrue(c.frontmatter_closed_before_body(p))
            fm_body = c.read_frontmatter(p)
            self.assertIsNotNone(fm_body)
            fm, body = fm_body
            self.assertEqual(fm["id"], "insight-demo")
            self.assertIn("## Evidence Trail", body)
            self.assertIn("## Source", body)
            self.assertIn("## Связи", body)
            # idempotent: a second repair is a no-op that still returns True
            before = p.read_text(encoding="utf-8")
            self.assertTrue(c.repair_misplaced_fence(p))
            self.assertEqual(before, p.read_text(encoding="utf-8"))

    def test_repair_noop_on_good_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, _GOOD_NOTE)
            before = p.read_text(encoding="utf-8")
            self.assertTrue(c.repair_misplaced_fence(p))
            self.assertEqual(before, p.read_text(encoding="utf-8"))

    def test_indented_fence_in_value_does_not_mask_corruption(self):
        # A frontmatter value containing '---' renders as an indented line;
        # the guard must NOT treat it as the closing fence and miss the real
        # '## Evidence Trail' corruption below it (column-0 fence only).
        text = (
            "---\n"
            "id: insight-demo\n"
            "desc: 'a\n\n  ---\n\n  b'\n"
            "## Evidence Trail\n\n"
            "- **2026-05-05** | [[r]] — x\n"
            "---\n\nbody\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, text)
            self.assertFalse(c.frontmatter_closed_before_body(p))
            self.assertIsNone(c.read_frontmatter(p))

    def test_repair_returns_false_on_clean_fence_but_broken_yaml(self):
        # Guard is clean (fence closes before body) but YAML is broken for an
        # unrelated reason — repair must not claim True (honest contract) and
        # must write nothing.
        text = "---\nid: x\nbad: [unclosed\n---\n\n## Body\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, text)
            self.assertTrue(c.frontmatter_closed_before_body(p))
            self.assertIsNone(c.read_frontmatter(p))
            before = p.read_text(encoding="utf-8")
            self.assertFalse(c.repair_misplaced_fence(p))
            self.assertEqual(before, p.read_text(encoding="utf-8"))

    def test_repair_refuses_ambiguous_multiple_fences(self):
        # An owner horizontal rule inside the displaced block makes the
        # intended fence indistinguishable — repair must refuse, not guess.
        text = (
            "---\n"
            "id: insight-demo\n"
            "type: insight\n"
            "## Evidence Trail\n\n"
            "- bullet\n\n"
            "---\n\n"
            "- more\n"
            "## Source\n\n"
            "- x\n"
            "---\n\n"
            "## Связи\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, text)
            self.assertFalse(c.frontmatter_closed_before_body(p))
            before = p.read_text(encoding="utf-8")
            self.assertFalse(c.repair_misplaced_fence(p))
            self.assertEqual(before, p.read_text(encoding="utf-8"))


class FenceHelperRobustnessTests(unittest.TestCase):
    """Regression tests for the fence helpers on hostile / non-ideal inputs."""

    def _write_bytes(self, tmp: str, data: bytes) -> Path:
        p = Path(tmp) / "note.md"
        p.write_bytes(data)
        return p

    def test_non_utf8_file_never_raises(self):
        # A non-UTF-8 file (Windows-1251 paste, stray binary) must not crash the
        # helpers — they read utf-8. Regression for the UnicodeDecodeError that
        # took down the whole reconciler scan.
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_bytes(tmp, b"\xff\xfe\x00---\nid: x\n---\n")
            self.assertTrue(c.frontmatter_closed_before_body(p))  # graceful, no raise
            self.assertIsNone(c.read_frontmatter(p))
            self.assertFalse(c.repair_misplaced_fence(p))

    def test_latin1_encoded_body_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_bytes(tmp, "---\nid: x\n---\n\n## Тело\n".encode("cp1251"))
            # Must return a bool/None, never raise UnicodeDecodeError
            self.assertIn(c.frontmatter_closed_before_body(p), (True, False))
            self.assertIsNone(c.read_frontmatter(p))

    def test_crlf_broken_note_repairs(self):
        text = (
            "---\r\nid: insight-demo\r\nlayer: knowledge\r\n"
            "## Evidence Trail\r\n\r\n- **2026-05-05** | [[r]] — x\r\n"
            "---\r\n\r\nbody\r\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "note.md"
            # write exact bytes (CRLF preserved, no newline translation) — `write_bytes`
            # is portable; `write_text(newline=...)` is Python 3.10+ and breaks on 3.9.
            p.write_bytes(text.encode("utf-8"))
            self.assertFalse(c.frontmatter_closed_before_body(p))
            self.assertTrue(c.repair_misplaced_fence(p))
            self.assertTrue(c.frontmatter_closed_before_body(p))
            self.assertIsNotNone(c.read_frontmatter(p))

    def test_broken_note_without_trailing_newline_repairs(self):
        text = ("---\nid: x\nlayer: knowledge\n## Evidence Trail\n\n"
                "- **2026-05-05** | [[r]] — x\n---\n\nbody")  # no trailing \n
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "note.md"
            p.write_text(text, encoding="utf-8")
            self.assertFalse(c.frontmatter_closed_before_body(p))
            self.assertTrue(c.repair_misplaced_fence(p))
            fm_body = c.read_frontmatter(p)
            self.assertIsNotNone(fm_body)
            self.assertIn("## Evidence Trail", fm_body[1])

    def test_wellformed_note_with_body_horizontal_rule_passes(self):
        # A `---` horizontal rule in the BODY of a well-formed note must not be
        # mistaken for the closing fence.
        text = ("---\nid: x\nlayer: knowledge\n---\n\n"
                "## A\n\ntext\n\n---\n\n## B\n\nmore\n")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "note.md"
            p.write_text(text, encoding="utf-8")
            self.assertTrue(c.frontmatter_closed_before_body(p))
            self.assertIsNotNone(c.read_frontmatter(p))
            before = p.read_text(encoding="utf-8")
            self.assertTrue(c.repair_misplaced_fence(p))  # no-op
            self.assertEqual(before, p.read_text(encoding="utf-8"))

    def test_repair_preserves_cyrillic_body_verbatim(self):
        text = ("---\nid: x\nlayer: knowledge\n## Evidence Trail\n\n"
                "- **2026-05-05** | [[r]] — извлечено из встречи\n---\n\n"
                "## Связи\n\n- [[запись]]\n")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "note.md"
            p.write_text(text, encoding="utf-8")
            self.assertTrue(c.repair_misplaced_fence(p))
            body = c.read_frontmatter(p)[1]
            self.assertIn("извлечено из встречи", body)
            self.assertIn("## Связи", body)
            self.assertIn("[[запись]]", body)


class ApplyHubTrioTests(unittest.TestCase):
    """Writing the trio is half the operation, and it had no home.

    `recompute_hub_trio` decided the values; putting them on disk was left to
    whoever called it, so every run hand-rolled YAML surgery. One such write
    emitted flow style into a block-style frontmatter and the hub stopped
    parsing — invisible to every downstream scan, not merely wrong in a field.
    """

    HUB = """---
id: hub-x
title: "Hub: X"
layer: hub
origin: work
audience_tags: []
is_sensitive: false
_engine_derived:
  - origin
  - audience_tags
  - is_sensitive
modified: 2026-08-01
---

## Body

text
"""

    def _hub(self, tmp: str) -> Path:
        path = Path(tmp) / "hub-x.md"
        path.write_text(self.HUB, encoding="utf-8")
        return path

    def test_the_written_frontmatter_stays_block_style_and_parses(self):
        """THE regression. A sensitive member flips `is_sensitive`, which is
        exactly the write that produced `{is_sensitive: true}` by hand."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._hub(tmp)
            result = c.apply_hub_trio(
                path, [{"origin": "work", "audience_tags": [], "is_sensitive": True}]
            )
            self.assertTrue(result["changed"])
            self.assertTrue(result["trio"]["is_sensitive"])

            fence = path.read_text(encoding="utf-8").split("---")[1]
            self.assertNotIn("{", fence, "flow-style mapping in the frontmatter")
            self.assertNotIn("[", fence.replace("audience_tags: []", ""),
                             "flow-style sequence in the frontmatter")
            self.assertIsNotNone(c.read_frontmatter(path),
                                 "the hub must still parse after the write")

    def test_an_owner_set_field_is_never_rewritten(self):
        """SIBLING — the ownership contract survives the writer. A field the
        owner set (absent from `_engine_derived`) is untouched."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hub-y.md"
            path.write_text(self.HUB.replace(
                "_engine_derived:\n  - origin\n  - audience_tags\n  - is_sensitive\n",
                "_engine_derived:\n  - origin\n"), encoding="utf-8")
            c.apply_hub_trio(
                path, [{"origin": "work", "audience_tags": [], "is_sensitive": True}]
            )
            fm, _ = c.read_frontmatter(path)
            self.assertFalse(fm["is_sensitive"], "owner's value was overwritten")

    def test_a_no_op_recompute_writes_nothing(self):
        """SIBLING — byte-identical file and no `modified:` churn, so a bumped
        date always means something really moved."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._hub(tmp)
            before = path.read_bytes()
            result = c.apply_hub_trio(
                path,
                [{"origin": "work", "audience_tags": [], "is_sensitive": False}],
                modified="2026-08-13",
            )
            self.assertFalse(result["changed"])
            self.assertEqual(path.read_bytes(), before)

    def test_modified_is_stamped_only_on_a_real_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._hub(tmp)
            c.apply_hub_trio(
                path,
                [{"origin": "work", "audience_tags": [], "is_sensitive": True}],
                modified="2026-08-13",
            )
            fm, _ = c.read_frontmatter(path)
            self.assertEqual(str(fm["modified"]), "2026-08-13")

    def test_applying_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._hub(tmp)
            members = [{"origin": "work", "audience_tags": [], "is_sensitive": True}]
            c.apply_hub_trio(path, members)
            after_first = path.read_bytes()
            second = c.apply_hub_trio(path, members)
            self.assertFalse(second["changed"])
            self.assertEqual(path.read_bytes(), after_first)

    def test_an_unreadable_hub_is_reported_and_left_alone(self):
        """SIBLING — a hub whose frontmatter cannot be parsed is exactly the
        damage this helper exists to prevent. Rewriting it from a guess would
        destroy whatever is really in there."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.md"
            path.write_text("---\nid: hub-z\n{is_sensitive: true}\n: :\n---\nbody\n",
                            encoding="utf-8")
            before = path.read_bytes()
            self.assertIsNone(c.apply_hub_trio(path, []))
            self.assertEqual(path.read_bytes(), before)

    def test_the_body_survives_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._hub(tmp)
            c.apply_hub_trio(
                path, [{"origin": "work", "audience_tags": [], "is_sensitive": True}]
            )
            self.assertIn("## Body", path.read_text(encoding="utf-8"))


class AppendFrontmatterListTests(unittest.TestCase):
    """The other write maintain performs by the hundred — a thread back-ref.

    Hand-rolled it is the same hazard as the trio write: a list built by
    string concatenation can be built wrong, and a note whose frontmatter
    stops parsing is invisible to every scan rather than missing a field.
    """

    NOTE = """---
id: 20260812-meeting-x
layer: record
threads:
  - thread-a
modified: 2026-08-01
---

## Body

text
"""

    def _note(self, tmp: str, text: str | None = None) -> Path:
        path = Path(tmp) / "note.md"
        path.write_text(text if text is not None else self.NOTE, encoding="utf-8")
        return path

    def test_a_new_value_is_appended_and_the_file_still_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._note(tmp)
            self.assertTrue(
                c.append_frontmatter_list_value(path, "threads", "thread-b")
            )
            fm, body = c.read_frontmatter(path)
            self.assertEqual(fm["threads"], ["thread-a", "thread-b"])
            self.assertIn("## Body", body, "body must survive verbatim")

    def test_the_key_is_created_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._note(tmp, self.NOTE.replace("threads:\n  - thread-a\n", ""))
            self.assertTrue(
                c.append_frontmatter_list_value(path, "threads", "thread-b")
            )
            fm, _ = c.read_frontmatter(path)
            self.assertEqual(fm["threads"], ["thread-b"])

    def test_a_duplicate_writes_nothing_at_all(self):
        """SIBLING — idempotency without churn. Re-running a batch must not
        bump `modified:` on every note it already touched."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._note(tmp)
            before = path.read_bytes()
            self.assertFalse(
                c.append_frontmatter_list_value(
                    path, "threads", "thread-a", modified="2026-08-13")
            )
            self.assertEqual(path.read_bytes(), before)

    def test_modified_is_stamped_only_when_something_was_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._note(tmp)
            c.append_frontmatter_list_value(
                path, "threads", "thread-b", modified="2026-08-13")
            fm, _ = c.read_frontmatter(path)
            self.assertEqual(str(fm["modified"]), "2026-08-13")

    def test_a_non_list_value_is_refused_rather_than_coerced(self):
        """SIBLING — somebody's data in a shape this does not understand.
        Reshaping it to fit would destroy what it is meant to preserve."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._note(
                tmp, self.NOTE.replace("threads:\n  - thread-a\n", "threads: thread-a\n"))
            before = path.read_bytes()
            self.assertIsNone(
                c.append_frontmatter_list_value(path, "threads", "thread-b")
            )
            self.assertEqual(path.read_bytes(), before)

    def test_an_unparseable_note_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._note(tmp, "---\nid: x\n: :\n{a: b}\n---\nbody\n")
            before = path.read_bytes()
            self.assertIsNone(
                c.append_frontmatter_list_value(path, "threads", "thread-b")
            )
            self.assertEqual(path.read_bytes(), before)

    def test_the_written_list_is_block_style(self):
        """SIBLING — the shape that caused the original damage."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._note(tmp)
            c.append_frontmatter_list_value(path, "threads", "thread-b")
            fence = path.read_text(encoding="utf-8").split("---")[1]
            self.assertIn("- thread-b", fence)
            self.assertNotIn("[", fence)
            self.assertNotIn("{", fence)


if __name__ == "__main__":
    unittest.main()
