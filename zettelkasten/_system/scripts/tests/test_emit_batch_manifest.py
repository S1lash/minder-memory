"""Tests for emit_batch_manifest.py — JSON manifest emitter.

Coverage:
- happy path round-trip
- concept-name normalisation in concept_hints / member_concepts /
  applies_in_concepts / concept_ids / related_concepts / previous_slugs
- concepts.upserts[]: name normalise + drop unnormalisables + subtype
  normalise + nested lists normalise
- audience_tags whitelist enforcement (canonical 5 + extensions)
- privacy trio coercion (origin enum, is_sensitive bool)
- top-level required keys missing → warning, write succeeds
- dry-run does not write
- idempotence
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tests._fixture import clear_minder_memory_env  # type: ignore
import emit_batch_manifest as e  # type: ignore


def _audiences_file(root: Path, extensions: list[str] | None = None) -> Path:
    extensions = extensions or []
    rows = "\n".join(
        f"| {tag} | 2026-05-02 | active | test | — |" for tag in extensions
    )
    p = root / "AUDIENCES.md"
    p.write_text(
        "# Audiences\n"
        "<!-- BEGIN extensions -->\n"
        "| Tag | Added | Status | Purpose | Notes |\n"
        "|---|---|---|---|---|\n"
        + (rows + "\n" if rows else "")
        + "<!-- END extensions -->\n",
        encoding="utf-8",
    )
    return p


def _domains_file(root: Path, extensions: list[str] | None = None) -> Path:
    extensions = extensions or []
    rows = "\n".join(
        f"| {dom} | 2026-05-02 | active | test | — |" for dom in extensions
    )
    p = root / "DOMAINS.md"
    p.write_text(
        "# Domains\n"
        "<!-- BEGIN extensions -->\n"
        "| Domain | Added | Status | Purpose | Notes |\n"
        "|---|---|---|---|---|\n"
        + (rows + "\n" if rows else "")
        + "<!-- END extensions -->\n",
        encoding="utf-8",
    )
    return p


def _run(input_data: dict, output: Path, audiences: Path,
         dry_run: bool = False, *, domains: Path | None = None,
         deep_validate: bool = False,
         ) -> tuple[int, str, str]:
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", encoding="utf-8"
    ) as fh:
        json.dump(input_data, fh)
        in_path = Path(fh.name)
    # Always isolate from live registry — when caller did not provide a
    # specific DOMAINS.md, write an empty one alongside AUDIENCES.md so
    # tests use the canonical 13 with no extensions.
    if domains is None:
        domains = _domains_file(audiences.parent)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    args = ["--input", str(in_path), "--output", str(output),
            "--audiences", str(audiences), "--domains", str(domains)]
    # Most tests probe a single coercion with an intentionally-partial
    # manifest; the deep JSON-Schema gate (a production-only end-to-end
    # check) is off by default here and exercised explicitly by
    # DeepValidationGateTests + the retrofit over real batches.
    if not deep_validate:
        args.append("--no-deep-validate")
    if dry_run:
        args.append("--dry-run")
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = e.main(args)
    return rc, out_buf.getvalue(), err_buf.getvalue()


def _minimal_manifest() -> dict:
    return {
        "batch_id": "20260502-120000",
        "timestamp": "2026-05-02T12:00:00Z",
        "format_version": "2.1",
        "processor": "minder:mem:process",
        "sources_processed": [],
        "records": {"created": [], "updated": []},
        "knowledge_notes": {"created": [], "updated": []},
        "hubs": {"created": [], "updated": []},
        "concepts": {"upserts": []},
        "stats": {},
    }


class HappyPathTests(unittest.TestCase):
    def test_clean_input_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
                "concept_hints": ["office_move", "queue_prioritization"],
                "origin": "work",
                "audience_tags": ["work"],
                "is_sensitive": False,
            })
            output = tmp / "out.json"
            rc, _, err = _run(data, output, audiences)
            self.assertEqual(rc, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["created"][0]["concept_hints"],
                ["office_move", "queue_prioritization"],
            )
            # No fix events expected on clean input
            self.assertEqual(err.strip(), "")
        clear_minder_memory_env()


class ConceptNormalisationTests(unittest.TestCase):
    def test_concept_hints_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
                "concept_hints": ["Office-Move", "тема", "queue_prioritization"],
                "origin": "work",
                "audience_tags": [],
                "is_sensitive": False,
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            # Cyrillic dropped, kebab-snake normalised
            self.assertEqual(
                written["records"]["created"][0]["concept_hints"],
                ["office_move", "queue_prioritization"],
            )
            # Events on stderr
            self.assertIn("concept-format-autofix", err)
        clear_minder_memory_env()

    def test_concepts_upserts_dropped_when_unnormalisable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["concepts"]["upserts"] = [
                {"name": "valid_concept", "type": "theme",
                 "related_concepts": []},
                {"name": "тема", "type": "theme"},
                {"name": "Office-Move", "type": "theme"},
            ]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            names = [u["name"] for u in written["concepts"]["upserts"]]
            self.assertEqual(names, ["valid_concept", "office_move"])
            self.assertIn("concept-drop-autofix", err)
            self.assertIn("concept-format-autofix", err)
        clear_minder_memory_env()

    def test_type_prefixed_concept_names_kept_verbatim(self):
        # The engine does NOT strip type prefixes — names are kept verbatim
        # (only mechanical normalisation applies). Covers both the foreign
        # compound case (`event_loop_blocking` + type=theme) and the welded
        # own-type case (`skill_python` + type=skill): both are preserved,
        # because a blind strip cannot tell them apart and a wrong strip
        # corrupts identity (these WERE the real corpus corruptions).
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["concepts"]["upserts"] = [
                {"name": "skill_based_tournament_calibration",
                 "type": "theme", "related_concepts": []},
                {"name": "event_loop_blocking", "type": "theme",
                 "related_concepts": []},
                {"name": "skill_python", "type": "skill",
                 "related_concepts": []},
                {"name": "decision_making", "type": "theme",
                 "related_concepts": []},
            ]
            rc, _, _ = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            names = [u["name"] for u in written["concepts"]["upserts"]]
            self.assertEqual(names, [
                "skill_based_tournament_calibration",
                "event_loop_blocking",
                "skill_python",
                "decision_making",
            ])

    def test_concepts_upserts_subtype_and_related_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["concepts"]["upserts"] = [{
                "name": "qdrant",
                "type": "tool",
                "subtype": "Vector-Database",
                "related_concepts": ["Vector-Search", "embedding"],
                "previous_slugs": [],
            }]
            rc, _, _ = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            entry = written["concepts"]["upserts"][0]
            self.assertEqual(entry["subtype"], "vector_database")
            self.assertEqual(entry["related_concepts"],
                             ["vector_search", "embedding"])
        clear_minder_memory_env()


class AudienceWhitelistTests(unittest.TestCase):
    def test_unknown_tag_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)  # no extensions
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
                "concept_hints": [],
                "origin": "work",
                "audience_tags": ["work", "team-platform", "world"],
                "is_sensitive": False,
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["created"][0]["audience_tags"],
                ["work", "world"],
            )
            self.assertIn("audience-tag-drop-autofix", err)
        clear_minder_memory_env()

    def test_extension_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp, extensions=["spouse"])
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/observations/foo.md",
                "concept_hints": [],
                "origin": "personal",
                "audience_tags": ["spouse"],
                "is_sensitive": True,
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["created"][0]["audience_tags"],
                ["spouse"],
            )
        clear_minder_memory_env()

    def test_case_normalised_to_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/observations/foo.md",
                "concept_hints": [],
                "origin": "personal",
                "audience_tags": ["Family"],
                "is_sensitive": False,
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["created"][0]["audience_tags"],
                ["family"],
            )
            self.assertIn("audience-tag-normalise-autofix", err)
        clear_minder_memory_env()


class PrivacyCoercionTests(unittest.TestCase):
    def test_origin_coerced(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
                "concept_hints": [],
                "origin": "bogus",
                "audience_tags": [],
                "is_sensitive": False,
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["created"][0]["origin"], "personal"
            )
            self.assertIn("origin-coerce-autofix", err)
        clear_minder_memory_env()

    def test_is_sensitive_coerced_from_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
                "concept_hints": [],
                "origin": "work",
                "audience_tags": [],
                "is_sensitive": "true",
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertTrue(
                written["records"]["created"][0]["is_sensitive"]
            )
            self.assertIn("is-sensitive-coerce-autofix", err)
        clear_minder_memory_env()


class ManifestContractValidationTests(unittest.TestCase):
    def test_missing_required_top_level_key_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            del data["batch_id"]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 3)
            self.assertIn("missing required top-level keys", err)
            self.assertFalse((tmp / "out.json").exists())
        clear_minder_memory_env()

    def test_unknown_processor_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["processor"] = "minder:mem:bogus"
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 3)
            self.assertIn("processor 'minder:mem:bogus' not in", err)
            self.assertFalse((tmp / "out.json").exists())
        clear_minder_memory_env()

    def test_incompatible_major_version_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["format_version"] = "3.0"
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 3)
            self.assertIn("format_version major", err)
            self.assertFalse((tmp / "out.json").exists())
        clear_minder_memory_env()

    def test_minor_version_drift_accepted(self):
        # 2.5 still major-2 → accepted (forward-compat per ARCHITECTURE
        # §8.12.2)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["format_version"] = "2.5"
            rc, _, _ = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            self.assertTrue((tmp / "out.json").exists())
        clear_minder_memory_env()

    def test_missing_required_section_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            del data["concepts"]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 3)
            self.assertIn("requires sections", err)
            self.assertFalse((tmp / "out.json").exists())
        clear_minder_memory_env()

    def test_malformed_format_version_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["format_version"] = "two-point-zero"
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 3)
            self.assertIn("format_version", err)
        clear_minder_memory_env()

    def test_other_processors_have_relaxed_section_requirements(self):
        # minder:mem:lint / minder:mem:maintain / minder:mem:agent-lens require only `stats`
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            for proc in ("minder:mem:maintain", "minder:mem:lint", "minder:mem:agent-lens"):
                data = {
                    "batch_id": "20260502-120000",
                    "timestamp": "2026-05-02T12:00:00Z",
                    "format_version": "2.1",
                    "processor": proc,
                    "stats": {},
                }
                output = tmp / f"out-{proc.replace(':', '-')}.json"
                rc, _, err = _run(data, output, audiences)
                self.assertEqual(rc, 0, f"{proc}: {err}")
                self.assertTrue(output.exists())
        clear_minder_memory_env()


class DryRunTests(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            output = tmp / "out.json"
            rc, out, _ = _run(_minimal_manifest(), output, audiences,
                              dry_run=True)
            self.assertEqual(rc, 0)
            self.assertFalse(output.exists())
            # JSON was printed to stdout
            self.assertIn("batch_id", out)
        clear_minder_memory_env()


class IdempotenceTests(unittest.TestCase):
    def test_clean_input_zero_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
                "concept_hints": ["office_move"],
                "origin": "work",
                "audience_tags": ["work"],
                "is_sensitive": False,
            })
            _, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(err.strip(), "")
            # Re-emit the written file: should still be clean
            written_data = json.loads(
                (tmp / "out.json").read_text(encoding="utf-8")
            )
            _, _, err2 = _run(written_data, tmp / "out2.json", audiences)
            self.assertEqual(err2.strip(), "")
        clear_minder_memory_env()


class EmptySectionShapeTests(unittest.TestCase):
    """Producer-side coercion of legacy empty-shorthand `[]` to canonical
    empty-envelope shapes. Ensures schema-strict consumers never see the
    drift form even if the Claude-driven accumulator emits it.
    """

    def test_tier1_empty_lists_become_envelopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier1_objects"] = {
                "tasks": [],
                "ideas": [],
                "events": [],
                "decisions": [],
                "content": [],
                "people": [],
                "projects": [],
            }
            output = tmp / "out.json"
            rc, _, err = _run(data, output, audiences)
            self.assertEqual(rc, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            for key in ("tasks", "ideas", "events", "decisions", "content"):
                self.assertEqual(written["tier1_objects"][key],
                                 {"created": [], "updated": []})
            for key in ("people", "projects"):
                self.assertEqual(written["tier1_objects"][key],
                                 {"upserts": []})
            # Each coercion emits a fix event on stderr
            self.assertGreaterEqual(err.count("tier1-empty-shape-autofix"), 7)
        clear_minder_memory_env()

    def test_tier2_empty_list_becomes_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = []
            output = tmp / "out.json"
            rc, _, err = _run(data, output, audiences)
            self.assertEqual(rc, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["tier2_objects"], {})
            self.assertIn("tier2-empty-shape-autofix", err)
        clear_minder_memory_env()

    def test_tier2_inner_empty_list_becomes_upserts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = {"inventory": [], "wardrobe": []}
            output = tmp / "out.json"
            rc, _, err = _run(data, output, audiences)
            self.assertEqual(rc, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["tier2_objects"]["inventory"], {"upserts": []})
            self.assertEqual(written["tier2_objects"]["wardrobe"], {"upserts": []})
        clear_minder_memory_env()

    def test_constitution_principles_empty_list_becomes_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["constitution"] = {"principles": []}
            output = tmp / "out.json"
            rc, _, err = _run(data, output, audiences)
            self.assertEqual(rc, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                written["constitution"]["principles"],
                {"upserts": [], "archived": [], "superseded": []},
            )
            self.assertIn("constitution-principles-empty-shape-autofix", err)
        clear_minder_memory_env()

    def test_clean_envelopes_pass_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            # already canonical — no coercion fix events
            data["tier1_objects"] = {
                "tasks": {"created": [], "updated": []},
                "people": {"upserts": []},
            }
            output = tmp / "out.json"
            rc, _, err = _run(data, output, audiences)
            self.assertEqual(rc, 0)
            self.assertNotIn("empty-shape-autofix", err)
        clear_minder_memory_env()


class DomainNormalisationTests(unittest.TestCase):
    """`walk_and_normalise` handling of `domains:` (plural) and `domain:`
    (singular). Deterministic substrate — silent autofix or silent drop."""

    def test_canonical_passthrough(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["updated"].append(
                {"domains": ["work", "career", "health"]},
            )
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["updated"][0]["domains"],
                ["work", "career", "health"],
            )
            domain_events = [
                ln for ln in err.splitlines()
                if ln.strip() and "domain" in ln
            ]
            self.assertEqual(domain_events, [])
        clear_minder_memory_env()

    def test_unknown_value_dropped_from_array(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["updated"].append(
                {"domains": ["work", "payments", "career"]},
            )
            _, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["updated"][0]["domains"],
                ["work", "career"],
            )
            self.assertIn("domain-drop-autofix", err)
            self.assertIn("payments", err)

    def test_slash_syntax_split_keeps_canonical(self):
        # `work/process` → keep `work`, drop `process`.
        # `personal/psychology` → keep `personal`, drop `psychology`.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["updated"].append({
                "domains": ["work/process", "personal/psychology"],
            })
            _, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["updated"][0]["domains"],
                ["work", "personal"],
            )
            self.assertIn("domain-normalise-autofix", err)

    def test_slash_both_canonical_both_kept(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["updated"].append({"domains": ["work/learning"]})
            _, _, _ = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["updated"][0]["domains"],
                ["work", "learning"],
            )

    def test_extension_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp, extensions=["gardening"])
            data = _minimal_manifest()
            data["records"]["updated"].append(
                {"domains": ["gardening", "work"]},
            )
            _, _, err = _run(
                data, tmp / "out.json", audiences, domains=domains,
            )
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["updated"][0]["domains"],
                ["gardening", "work"],
            )

    def test_singular_domain_normalised(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["constitution"] = {
                "principles": [{"id": "axiom-x-001", "domain": "ai_interaction"}],
            }
            _, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["constitution"]["principles"][0]["domain"],
                "ai-interaction",
            )

    def test_singular_domain_dropped_when_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["constitution"] = {
                "principles": [{"id": "axiom-x-001", "domain": "junk"}],
            }
            _, _, err = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertNotIn(
                "domain", written["constitution"]["principles"][0],
            )
            self.assertIn("domain-drop-autofix", err)

    def test_dedupes_after_normalisation(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["updated"].append(
                {"domains": ["Work", "work", "WORK"]},
            )
            _, _, _ = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["records"]["updated"][0]["domains"], ["work"],
            )


class AtomicWriteTests(unittest.TestCase):
    def test_no_tmp_artifact_on_success(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            output = tmp / "out.json"
            rc, _, _ = _run(_minimal_manifest(), output, audiences)
            self.assertEqual(rc, 0)
            self.assertTrue(output.exists())
            self.assertFalse(output.with_suffix(".json.tmp").exists())
        clear_minder_memory_env()

    def test_crash_mid_write_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp)
            output = tmp / "out.json"
            in_path = tmp / "in.json"
            in_path.write_text(json.dumps(_minimal_manifest()), encoding="utf-8")
            args = [
                "--input", str(in_path), "--output", str(output),
                "--audiences", str(audiences), "--domains", str(domains),
            ]
            import os as _os
            real_replace = _os.replace

            def boom(*a, **kw):
                raise RuntimeError("simulated crash")

            _os.replace = boom
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertRaises(RuntimeError, e.main, args)
            finally:
                _os.replace = real_replace
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".json.tmp").exists())
        clear_minder_memory_env()


class SourcesProcessedCoercionTests(unittest.TestCase):
    """Producer-side coercion: bare-string entries in `sources_processed[]`
    are wrapped as structured `source_entry` objects with inferred
    source_type per SOURCE_TYPE_PREFIX_MAP.
    """

    def test_sources_processed_bare_string_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["sources_processed"] = [
                "_sources/processed/garmin/2026-05-17/metrics.md",
                "_sources/processed/plaud/2026-05-18T08:00:00Z/transcript.md",
                "_sources/processed/claude-sessions/2026-05-18-session.md",
                "_sources/processed/unknown-folder/foo.md",
                {"path": "_sources/processed/plaud/already-structured.md",
                 "source_type": "plaud-transcript"},
            ]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            sources = written["sources_processed"]
            self.assertEqual(len(sources), 5)
            for entry in sources:
                self.assertIsInstance(entry, dict)
                self.assertIn("path", entry)
            self.assertEqual(sources[0]["source_type"], "garmin-daily")
            self.assertEqual(sources[1]["source_type"], "plaud-transcript")
            self.assertEqual(sources[2]["source_type"], "claude-session")
            self.assertEqual(sources[3]["source_type"], "unknown")
            self.assertEqual(sources[4]["source_type"], "plaud-transcript")
            self.assertEqual(
                written["stats"].get("source_type_inferred_unknown"), 1,
            )
            self.assertIn("sources-processed-coerce-autofix", err)
        clear_minder_memory_env()


class Tier1NonEmptyArrayCoercionTests(unittest.TestCase):
    def test_tier1_people_nonempty_array_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier1_objects"] = {
                "people": [
                    {"id": "alice-smith", "display_name": "Alice Smith"},
                    {"id": "bob-jones"},
                ],
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {k for k in written["tier1_objects"]["people"]},
                {"upserts"},
            )
            self.assertEqual(
                [u["id"] for u in written["tier1_objects"]["people"]["upserts"]],
                ["alice-smith", "bob-jones"],
            )
            self.assertIn("tier1-nonempty-shape-autofix", err)
        clear_minder_memory_env()

    def test_tier1_projects_nonempty_bare_strings_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier1_objects"] = {
                "projects": ["minder", "minder-memory-engine"],
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            upserts = written["tier1_objects"]["projects"]["upserts"]
            self.assertEqual(
                [u["id"] for u in upserts],
                ["minder", "minder-memory-engine"],
            )
            self.assertIn("tier1-bare-string-wrap-autofix", err)
        clear_minder_memory_env()

    def test_hubs_nonempty_array_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["hubs"] = [
                {"path": "5_meta/mocs/foo.md", "state": "created",
                 "origin": "personal", "audience_tags": [],
                 "is_sensitive": False},
                {"path": "5_meta/mocs/bar.md",
                 "origin": "work", "audience_tags": ["work"],
                 "is_sensitive": False},
            ]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                len(written["hubs"]["created"]), 1,
            )
            self.assertEqual(
                len(written["hubs"]["updated"]), 1,
            )
            self.assertIn("hubs-nonempty-shape-autofix", err)
        clear_minder_memory_env()


class PrivacyTrioInjectionTests(unittest.TestCase):
    def test_privacy_trio_injected_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
            })
            data["knowledge_notes"]["created"].append({
                "path": "1_projects/foo.md",
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            rec = written["records"]["created"][0]
            self.assertEqual(rec["origin"], "personal")
            self.assertEqual(rec["audience_tags"], [])
            self.assertEqual(rec["is_sensitive"], False)
            note = written["knowledge_notes"]["created"][0]
            self.assertEqual(note["origin"], "personal")
            self.assertEqual(note["audience_tags"], [])
            self.assertEqual(note["is_sensitive"], False)
            self.assertIn("privacy-trio-inject-autofix", err)
        clear_minder_memory_env()

    def test_privacy_trio_partial_keys_injected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            # Only `origin` present; the other two should be injected.
            data["records"]["created"].append({
                "path": "_records/meetings/foo.md",
                "origin": "work",
            })
            rc, _, _ = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            rec = written["records"]["created"][0]
            self.assertEqual(rec["origin"], "work")
            self.assertEqual(rec["audience_tags"], [])
            self.assertEqual(rec["is_sensitive"], False)
        clear_minder_memory_env()

    def test_privacy_trio_not_injected_at_top_level(self):
        # Defaults must not leak onto the manifest root.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            rc, _, _ = _run(data, tmp / "out.json", audiences)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertNotIn("origin", written)
            self.assertNotIn("audience_tags", written)
            self.assertNotIn("is_sensitive", written)
        clear_minder_memory_env()


class RecordsKnowledgeNotesBareArrayTests(unittest.TestCase):
    def test_records_nonempty_bare_array_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["records"] = [
                {"id": "r1", "path": "_records/observations/r1.md",
                 "state": "created"},
                {"id": "r2", "path": "_records/observations/r2.md"},
            ]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertIsInstance(written["records"], dict)
            self.assertEqual(len(written["records"]["created"]), 1)
            self.assertEqual(len(written["records"]["updated"]), 1)
            self.assertEqual(written["records"]["created"][0]["id"], "r1")
            self.assertEqual(written["records"]["updated"][0]["id"], "r2")
            self.assertIn("records-nonempty-shape-autofix", err)
        clear_minder_memory_env()

    def test_knowledge_notes_nonempty_bare_array_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["knowledge_notes"] = [
                {"id": "n1", "path": "1_projects/foo/n1.md"},
                {"id": "n2", "path": "1_projects/foo/n2.md",
                 "state": "created"},
            ]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertIsInstance(written["knowledge_notes"], dict)
            self.assertEqual(len(written["knowledge_notes"]["created"]), 1)
            self.assertEqual(len(written["knowledge_notes"]["updated"]), 1)
            self.assertIn("knowledge-notes-nonempty-shape-autofix", err)
        clear_minder_memory_env()


class Tier2SubsectionBareArrayTests(unittest.TestCase):
    def test_tier2_tasks_with_name_nonempty_bare_array_coerced(self):
        # Genuine tier2 typed-object task (has `name`) stays in tier2
        # after envelope coercion. Items lacking `name` get relocated
        # to tier1 — see Tier2TasksRelocationTests.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = {
                "tasks": [
                    {"id": "task-foo", "type": "action",
                     "name": "Foo task", "note": "20260507-foo"},
                ],
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            upserts = written["tier2_objects"]["tasks"]["upserts"]
            self.assertEqual(len(upserts), 1)
            entry = upserts[0]
            # Original fields preserved …
            self.assertEqual(entry["id"], "task-foo")
            self.assertEqual(entry["type"], "action")
            self.assertEqual(entry["name"], "Foo task")
            self.assertEqual(entry["note"], "20260507-foo")
            # … and the privacy trio injected (tier2 entries require it).
            self.assertEqual(entry["origin"], "personal")
            self.assertEqual(entry["audience_tags"], [])
            self.assertEqual(entry["is_sensitive"], False)
            self.assertIn("tier2-nonempty-shape-autofix", err)
        clear_minder_memory_env()

    def test_tier2_all_known_subsections_coerced(self):
        # Parametrise-style: every tier2 subsection accepts bare-array
        # coercion. Both empty (existing behaviour) and non-empty.
        subsections = [
            "inventory", "wardrobe", "content_candidates",
            "lens_observation", "tasks", "ideas", "events", "decisions",
            "content", "lens-observation",
        ]
        for sub in subsections:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                audiences = _audiences_file(tmp)
                data = _minimal_manifest()
                data["tier2_objects"] = {
                    sub: [{"id": f"{sub}-x", "type": "kind", "name": "X"}],
                }
                rc, _, _ = _run(
                    data, tmp / f"out-{sub.replace('-', '_')}.json",
                    audiences,
                )
                self.assertEqual(rc, 0)
                written = json.loads(
                    (tmp / f"out-{sub.replace('-', '_')}.json").read_text(encoding="utf-8"),
                )
                self.assertIn("upserts", written["tier2_objects"][sub])
                self.assertEqual(
                    len(written["tier2_objects"][sub]["upserts"]), 1,
                )
            clear_minder_memory_env()


class LegacyConceptTypeAliasTests(unittest.TestCase):
    def test_legacy_concept_type_aliases_mapped(self):
        mappings = [
            ("technical_concept", "technical"),
            ("pattern", "technical"),
            ("process", "theme"),
            ("concept", "theme"),
            ("technique", "skill"),
            ("system", "theme"),
            ("policy", "decision"),
        ]
        for legacy, mapped in mappings:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                audiences = _audiences_file(tmp)
                data = _minimal_manifest()
                data["concepts"]["upserts"].append({
                    "name": f"sample_{legacy}",
                    "type": legacy,
                })
                rc, _, err = _run(
                    data, tmp / f"out-{legacy}.json", audiences,
                )
                self.assertEqual(rc, 0)
                written = json.loads(
                    (tmp / f"out-{legacy}.json").read_text(encoding="utf-8"),
                )
                entry = written["concepts"]["upserts"][0]
                self.assertEqual(entry["type"], mapped)
                self.assertEqual(
                    entry["section_extras"]["legacy_type"], legacy,
                )
                self.assertIn("concept-type-legacy-alias-autofix", err)
            clear_minder_memory_env()

    def test_unknown_concept_type_failsafe_to_other(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["concepts"]["upserts"].append({
                "name": "weird_thing",
                "type": "totally_unknown_type",
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            # Unmapped, non-enum type fail-safes to `other` so the
            # manifest is concept-type-valid by construction. Original
            # preserved under section_extras.legacy_type for audit.
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            entry = written["concepts"]["upserts"][0]
            self.assertEqual(entry["type"], "other")
            self.assertEqual(
                entry["section_extras"]["legacy_type"],
                "totally_unknown_type",
            )
            self.assertIn(
                "concept-type-unknown-coerced-to-other", err,
            )
        clear_minder_memory_env()


class ConstitutionEmptyArrayCoercionTests(unittest.TestCase):
    def test_constitution_empty_array_coerced_to_object(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["constitution"] = []
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(written["constitution"], {})
            self.assertIn("constitution-empty-shape-autofix", err)
        clear_minder_memory_env()


class HubMissingPathDerivationTests(unittest.TestCase):
    def test_hub_missing_path_derived(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["hubs"]["updated"].append({
                "id": "hub-example-topic",
                "notes_added": 4,
                "origin": "personal",
                "audience_tags": [],
                "is_sensitive": False,
            })
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            entry = written["hubs"]["updated"][0]
            self.assertEqual(entry["path"], "5_meta/mocs/hub-example-topic.md")
            self.assertIn("hub-path-derive-autofix", err)
        clear_minder_memory_env()


class SensitiveEntitiesCoercionTests(unittest.TestCase):
    def test_sensitive_entities_note_id_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["sensitive_entities"] = [
                {"note_id": "20260506-therapy", "reason": "privacy"},
            ]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            entry = written["sensitive_entities"][0]
            self.assertEqual(entry["id"], "20260506-therapy")
            self.assertEqual(entry["kind"], "note")
            self.assertEqual(entry["reason"], "privacy")
            self.assertNotIn("note_id", entry)
            self.assertTrue(
                entry["section_extras"]["legacy_note_id_field"]
            )
            self.assertIn(
                "sensitive-entities-note-id-coerce-autofix", err,
            )
        clear_minder_memory_env()

    def test_sensitive_entities_idempotent(self):
        # Re-running on already-coerced output emits zero coercion
        # events for sensitive_entities.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["sensitive_entities"] = [
                {"note_id": "20260506-therapy", "reason": "privacy"},
            ]
            out1 = tmp / "out1.json"
            rc1, _, _ = _run(data, out1, audiences)
            self.assertEqual(rc1, 0)
            first_pass = json.loads(out1.read_text(encoding="utf-8"))
            out2 = tmp / "out2.json"
            rc2, _, err2 = _run(first_pass, out2, audiences)
            self.assertEqual(rc2, 0)
            second_pass = json.loads(out2.read_text(encoding="utf-8"))
            self.assertEqual(first_pass, second_pass)
            self.assertNotIn(
                "sensitive-entities-note-id-coerce-autofix", err2,
            )
        clear_minder_memory_env()

    def test_sensitive_entities_missing_kind_injected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["sensitive_entities"] = [
                {"weird_field": "value", "reason": "x"},
            ]
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            # `kind` is required by schema — inject the inferred default
            # (`note` when nothing in id/path hints otherwise) so the
            # entry validates; unknown keys are preserved untouched.
            self.assertIn(
                "sensitive-entities-kind-inject-autofix", err,
            )
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            entry = written["sensitive_entities"][0]
            self.assertEqual(entry["weird_field"], "value")
            self.assertEqual(entry["kind"], "note")
        clear_minder_memory_env()


class Tier2TasksRelocationTests(unittest.TestCase):
    def test_tier2_tasks_relocated_to_tier1(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = {
                "tasks": {
                    "upserts": [
                        {
                            "id": "task-pay-by-bank-tink-communicate",
                            "type": "action",
                            "due": "2026-05-20",
                            "note": "_records/meetings/20260506-foo.md",
                            "assignee": "ivan-petrov",
                        },
                        {
                            "id": "task-followup-team",
                            "type": "delegate",
                        },
                    ],
                },
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertNotIn(
                "tasks", written.get("tier2_objects", {}) or {},
            )
            created = written["tier1_objects"]["tasks"]["created"]
            self.assertEqual(len(created), 2)
            first = created[0]
            self.assertEqual(
                first["id"], "task-pay-by-bank-tink-communicate",
            )
            self.assertEqual(
                first["title"], "Pay by bank tink communicate",
            )
            self.assertEqual(first["ownership"], "MINE")
            self.assertEqual(first["deadline"], "2026-05-20")
            self.assertEqual(
                first["source_record_path"],
                "_records/meetings/20260506-foo.md",
            )
            self.assertEqual(
                first["section_extras"]["legacy_origin"],
                "tier2_objects.tasks",
            )
            self.assertEqual(
                first["section_extras"]["legacy_type"], "action",
            )
            self.assertEqual(
                first["section_extras"]["assignee"], "ivan-petrov",
            )
            self.assertEqual(first["origin"], "personal")
            self.assertEqual(first["audience_tags"], [])
            self.assertFalse(first["is_sensitive"])
            second = created[1]
            self.assertEqual(second["ownership"], "DELEGATED")
            self.assertIn("tier2-tasks-relocated-to-tier1", err)
        clear_minder_memory_env()

    def test_tier2_tasks_with_name_field_NOT_relocated(self):
        # Genuine tier2 typed-object task (has `name`) stays in tier2.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = {
                "tasks": {
                    "upserts": [
                        {
                            "id": "task-genuine",
                            "type": "kind",
                            "name": "Genuine tier2 task",
                        },
                    ],
                },
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["tier2_objects"]["tasks"]["upserts"][0]["id"],
                "task-genuine",
            )
            tier1_tasks = written.get("tier1_objects", {}).get("tasks")
            if isinstance(tier1_tasks, dict):
                # No relocation — created list is whatever empty
                # envelope existed.
                for entry in tier1_tasks.get("created", []) or []:
                    self.assertNotEqual(entry.get("id"), "task-genuine")
            self.assertNotIn("tier2-tasks-relocated-to-tier1", err)
        clear_minder_memory_env()

    def test_tier2_events_unmappable_preserved_in_section_extras(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = {
                "events": {
                    "upserts": [
                        # Missing `type` AND `name` — unmappable.
                        {"id": "event-foo", "note": "blah"},
                    ],
                },
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertNotIn(
                "events", written.get("tier2_objects", {}) or {},
            )
            preserved = (
                written["section_extras"]["legacy_tier2_drop"]["events"]
            )
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0]["id"], "event-foo")
            self.assertIn("tier2-events-preserved-as-legacy", err)
        clear_minder_memory_env()

    def test_tier2_people_candidates_preserved_in_section_extras(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = {
                "people_candidates": [
                    {"name": "Old candidate"},
                ],
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertNotIn(
                "people_candidates",
                written.get("tier2_objects", {}) or {},
            )
            preserved = (
                written["section_extras"]
                       ["legacy_tier2_drop"]
                       ["people_candidates"]
            )
            self.assertEqual(preserved, [{"name": "Old candidate"}])
            self.assertIn(
                "tier2-people-candidates-preserved-as-legacy", err,
            )
        clear_minder_memory_env()

    def test_tier2_relocation_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier2_objects"] = {
                "tasks": {
                    "upserts": [
                        {"id": "task-foo", "type": "action"},
                    ],
                },
                "events": {
                    "upserts": [
                        {"id": "ev-x"},
                    ],
                },
                "people_candidates": [{"name": "X"}],
            }
            out1 = tmp / "out1.json"
            rc1, _, _ = _run(data, out1, audiences)
            self.assertEqual(rc1, 0)
            first_pass = json.loads(out1.read_text(encoding="utf-8"))
            out2 = tmp / "out2.json"
            rc2, _, err2 = _run(first_pass, out2, audiences)
            self.assertEqual(rc2, 0)
            second_pass = json.loads(out2.read_text(encoding="utf-8"))
            self.assertEqual(first_pass, second_pass)
            for fix_id in (
                "tier2-tasks-relocated-to-tier1",
                "tier2-events-preserved-as-legacy",
                "tier2-people-candidates-preserved-as-legacy",
            ):
                self.assertNotIn(fix_id, err2)
        clear_minder_memory_env()


class Phase4LowFindingsTests(unittest.TestCase):
    def test_idempotence_after_all_new_coercions(self):
        # Worst-case payload exercising every fix pattern. Re-running
        # the producer on its own output MUST produce 0 fix events.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = {
                "batch_id": "20260502-120000",
                "timestamp": "2026-05-02T12:00:00Z",
                "format_version": "2.1",
                "processor": "minder:mem:process",
                "sources_processed": [
                    "_sources/processed/garmin/2026-05-02.md",
                    {"path": "_sources/processed/plaud/x.md",
                     "source_type": "plaud-transcript"},
                ],
                "records": [
                    {"path": "_records/meetings/foo.md",
                     "state": "created"},
                ],
                "knowledge_notes": [],
                "hubs": [
                    {"id": "hub-foo"},
                ],
                "tier1_objects": {
                    "people": ["alice-x", {"id": "bob-y"}],
                    "projects": [],
                    "tasks": [],
                },
                "tier2_objects": {
                    "tasks": {
                        "upserts": [
                            {"id": "task-foo", "type": "action"},
                        ],
                    },
                    "events": {
                        "upserts": [{"id": "ev-x"}],
                    },
                    "people_candidates": [{"name": "X"}],
                },
                "concepts": {
                    "upserts": [
                        {"name": "office_move",
                         "type": "pattern"},
                    ],
                },
                "constitution": [],
                "sensitive_entities": [
                    {"note_id": "n1", "reason": "privacy"},
                ],
                "stats": {},
            }
            out1 = tmp / "out1.json"
            rc1, _, _ = _run(data, out1, audiences)
            self.assertEqual(rc1, 0)
            first = json.loads(out1.read_text(encoding="utf-8"))
            out2 = tmp / "out2.json"
            rc2, _, err2 = _run(first, out2, audiences)
            self.assertEqual(rc2, 0)
            second = json.loads(out2.read_text(encoding="utf-8"))
            self.assertEqual(first, second)
            # No autofix / coerce / inject / drop events on second
            # pass. The only stderr lines acceptable are the AUDIENCES
            # / DOMAINS warnings emitted during normal startup — those
            # would carry "warning:" prefix, not fix-event JSON.
            fix_lines = [
                ln for ln in err2.splitlines()
                if ln.strip().startswith("{") and "fix_id" in ln
            ]
            self.assertEqual(
                fix_lines, [], msg=f"unexpected fix events: {fix_lines}",
            )
        clear_minder_memory_env()

    def test_tier1_people_mixed_dict_and_bare_strings(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier1_objects"] = {
                "people": [
                    {"id": "alice"},
                    "bob-jones",
                    {"id": "charlie"},
                ],
            }
            rc, _, _ = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            upserts = written["tier1_objects"]["people"]["upserts"]
            self.assertEqual(len(upserts), 3)
            self.assertEqual(upserts[0]["id"], "alice")
            self.assertEqual(upserts[1]["id"], "bob-jones")
            self.assertEqual(upserts[2]["id"], "charlie")
        clear_minder_memory_env()

    def test_privacy_trio_NOT_injected_at_non_entity_lists(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            # concept_hints at top level (not an entity list).
            data["concept_hints"] = ["alpha_concept", "beta_concept"]
            # stats.streaks — arbitrary non-entity list.
            data["stats"]["streaks"] = [
                {"id": "s1", "len": 4},
                {"id": "s2", "len": 9},
            ]
            rc, _, _ = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["concept_hints"],
                ["alpha_concept", "beta_concept"],
            )
            for streak in written["stats"]["streaks"]:
                self.assertNotIn("origin", streak)
                self.assertNotIn("audience_tags", streak)
                self.assertNotIn("is_sensitive", streak)
        clear_minder_memory_env()


class LegacyConceptTypeAliasCompletenessTests(unittest.TestCase):
    def test_legacy_concept_type_aliases_complete_set(self):
        # Every alias key maps to a value in the canonical enum. The map
        # covers the full long-tail of historically-emitted non-enum
        # types; unmapped types fail-safe to `other` in the emitter.
        self.assertGreaterEqual(len(e.LEGACY_CONCEPT_TYPE_ALIASES), 16)
        for legacy_key, mapped in e.LEGACY_CONCEPT_TYPE_ALIASES.items():
            self.assertIn(
                mapped, e.CONCEPT_TYPE_ENUM,
                msg=f"alias {legacy_key!r} maps to {mapped!r}, "
                    f"not in CONCEPT_TYPE_ENUM",
            )
        # Regression guard: representative long-tail keys are mapped.
        for key in ("product", "technical_architecture", "practice",
                    "business_strategy", "principle", "ai"):
            self.assertIn(key, e.LEGACY_CONCEPT_TYPE_ALIASES)


class Tier1NullShapeTests(unittest.TestCase):
    def test_tier1_null_section_coerced_to_empty_shape(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["tier1_objects"] = {
                "tasks": None,
                "ideas": None,
                "people": None,
                "projects": None,
            }
            rc, _, err = _run(data, tmp / "out.json", audiences)
            self.assertEqual(rc, 0)
            written = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(
                written["tier1_objects"]["tasks"],
                {"created": [], "updated": []},
            )
            self.assertEqual(
                written["tier1_objects"]["ideas"],
                {"created": [], "updated": []},
            )
            self.assertEqual(
                written["tier1_objects"]["people"], {"upserts": []},
            )
            self.assertEqual(
                written["tier1_objects"]["projects"], {"upserts": []},
            )
            self.assertIn("tier1-null-shape-autofix", err)
        clear_minder_memory_env()


class DegenerateTaskIdTests(unittest.TestCase):
    def test_derive_task_title_degenerate_id(self):
        # Empty stem after strip → "Untitled task".
        self.assertEqual(e._derive_task_title_from_id("task-"), "Untitled task")
        self.assertEqual(e._derive_task_title_from_id(""), "Untitled task")
        self.assertEqual(e._derive_task_title_from_id("task----"), "Untitled task")
        # Non-string input → "Untitled task".
        self.assertEqual(e._derive_task_title_from_id(None), "Untitled task")
        # Valid stem still capitalises normally.
        self.assertEqual(
            e._derive_task_title_from_id("task-pay-the-bill"),
            "Pay the bill",
        )


class _NormaliserHelper:
    AUD = set(e.AUDIENCE_CANONICAL)
    DOM = set(e.ALLOWED_DOMAINS)

    @staticmethod
    def walk(node):
        events: list = []
        e.walk_and_normalise(
            node, _NormaliserHelper.AUD, _NormaliserHelper.DOM, events,
        )
        return events


class SynthesiseRequiredFieldsTests(unittest.TestCase):
    def test_timestamp_derived_from_batch_id(self):
        data = {"batch_id": "20260519-150515", "processor": "minder:mem:process"}
        e.synthesise_required_fields(data, [], fill_sections=False)
        self.assertEqual(data["timestamp"], "2026-05-19T15:05:15Z")
        self.assertEqual(data["format_version"], "2.0")

    def test_processor_derived_from_filename(self):
        data = {"batch_id": "20260519-150515", "format_version": "2.1"}
        e.synthesise_required_fields(
            data, [], filename="20260519-150515-maintain.json",
        )
        self.assertEqual(data["processor"], "minder:mem:maintain")

    def test_batch_id_conformed_from_batch_suffix(self):
        data = {"batch_id": "20260531-030000-batch3"}
        e.synthesise_required_fields(
            data, [], filename="20260531-030000-batch3.json",
        )
        self.assertEqual(data["batch_id"], "20260531-030000-3")
        self.assertEqual(
            data["section_extras"]["legacy_batch_id"],
            "20260531-030000-batch3",
        )

    def test_fill_sections_recovers_alias_and_empties(self):
        data = {
            "batch_id": "20260528-000000", "processor": "minder:mem:process",
            "format_version": "2.1", "timestamp": "2026-05-28T00:00:00Z",
            "sources": [{"path": "_sources/processed/plaud/x.md"}],
            "records": 2,
        }
        e.synthesise_required_fields(data, [], fill_sections=True)
        self.assertEqual(
            data["sources_processed"],
            [{"path": "_sources/processed/plaud/x.md"}],
        )
        self.assertEqual(data["records"], {"created": [], "updated": []})
        self.assertEqual(
            data["section_extras"]["legacy_scalar_sections"]["records"], 2,
        )
        self.assertIn("concepts", data)
        self.assertIn("knowledge_notes", data)


class LegacyShapeCoercionTests(unittest.TestCase):
    def test_stringified_array_parsed(self):
        node = {"people": "[]", "audience_tags": "[professional-network]"}
        _NormaliserHelper.walk(node)
        self.assertEqual(node["people"], [])
        self.assertEqual(node["audience_tags"], ["professional-network"])

    def test_plain_string_array_field_wrapped(self):
        node = {"supersedes": "20260603-decision-x"}
        _NormaliserHelper.walk(node)
        self.assertEqual(node["supersedes"], ["20260603-decision-x"])

    def test_tier_int_coerced_to_string(self):
        node = {"tier1_objects": {"people": {"upserts": [
            {"id": "x", "tier": 1,
             "origin": "work", "audience_tags": [], "is_sensitive": False},
        ]}}}
        _NormaliserHelper.walk(node)
        self.assertEqual(
            node["tier1_objects"]["people"]["upserts"][0]["tier"], "1",
        )

    def test_invalid_hub_kind_dropped(self):
        node = {"hubs": {"updated": [
            {"id": "hub-x", "hub_kind": "theme",
             "origin": "work", "audience_tags": [], "is_sensitive": False},
        ]}}
        _NormaliserHelper.walk(node)
        self.assertNotIn("hub_kind", node["hubs"]["updated"][0])

    def test_hub_id_field_renamed_and_path_derived(self):
        node = {"hubs": {"updated": [
            {"hub_id": "hub-tooling-rollout",
             "origin": "work", "audience_tags": [], "is_sensitive": False},
        ]}}
        _NormaliserHelper.walk(node)
        entry = node["hubs"]["updated"][0]
        self.assertEqual(entry["id"], "hub-tooling-rollout")
        self.assertEqual(entry["path"], "5_meta/mocs/hub-tooling-rollout.md")

    def test_bare_string_record_entry_wrapped(self):
        node = {"records": {"created": ["20260519-meeting-x"]}}
        _NormaliserHelper.walk(node)
        entry = node["records"]["created"][0]
        self.assertEqual(entry["path"], "_records/meetings/20260519-meeting-x.md")
        self.assertEqual(entry["origin"], "personal")

    def test_tier1_task_title_derived(self):
        node = {"tier1_objects": {"tasks": {"updated": [
            {"id": "task-team-announce",
             "origin": "work", "audience_tags": [], "is_sensitive": False},
        ]}}}
        _NormaliserHelper.walk(node)
        self.assertEqual(
            node["tier1_objects"]["tasks"]["updated"][0]["title"],
            "Team announce",
        )

    def test_lens_observation_is_hypothesis_forced_true(self):
        node = {"tier2_objects": {"lens_observation": {"upserts": [
            {"id": "lens-obs-1", "lens_name": "stalled", "observed_on": "x",
             "is_hypothesis": False,
             "origin": "personal", "audience_tags": [], "is_sensitive": False},
        ]}}}
        _NormaliserHelper.walk(node)
        self.assertIs(
            node["tier2_objects"]["lens_observation"]["upserts"][0][
                "is_hypothesis"], True,
        )

    def test_concept_null_type_failsafe_to_other(self):
        events: list = []
        out = e.process_concepts_upserts(
            [{"name": "x", "type": None}], events, "$.concepts.upserts",
        )
        self.assertEqual(out[0]["type"], "other")

    def test_tier2_misplaced_ideas_relocated_to_tier1(self):
        data = {"tier2_objects": {"ideas": {"upserts": [
            "20260601-idea-a", "20260601-idea-b",
        ]}}}
        e.relocate_tier2_misplaced_sections(data, [], {})
        self.assertNotIn("ideas", data["tier2_objects"])
        created = data["tier1_objects"]["ideas"]["created"]
        self.assertEqual({c["id"] for c in created},
                         {"20260601-idea-a", "20260601-idea-b"})

    def test_genuine_tier2_ideas_kept(self):
        data = {"tier2_objects": {"ideas": {"upserts": [
            {"id": "i1", "type": "kind", "name": "X"},
        ]}}}
        e.relocate_tier2_misplaced_sections(data, [], {})
        self.assertIn("ideas", data["tier2_objects"])

    def test_sensitive_entities_bare_string_wrapped(self):
        data = {"sensitive_entities": ["20260531-observation-x"]}
        e.coerce_sensitive_entities(data, [], {})
        entry = data["sensitive_entities"][0]
        self.assertEqual(entry["id"], "20260531-observation-x")
        self.assertEqual(entry["kind"], "record")

    def test_scalar_threads_coerced_to_array(self):
        data = {"threads_opened": 0, "threads_resolved": 0}
        e.normalise_empty_section_shapes(data, [], {})
        self.assertEqual(data["threads_opened"], [])
        self.assertEqual(data["threads_resolved"], [])


class DeepValidationGateTests(unittest.TestCase):
    def test_clean_manifest_passes_deep_gate(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            out = tmp / "out.json"
            rc, _, err = _run(data, out, audiences, deep_validate=True)
            self.assertEqual(rc, 0, msg=err)
            self.assertTrue(out.exists())

    def test_deep_gate_rejects_shallow_valid_deep_invalid(self):
        # Valid top-level shape (passes the shallow gate) but a batch_id
        # that violates the schema pattern (the deep gate must catch it).
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["batch_id"] = "not a valid batch id"
            out = tmp / "out.json"
            rc, _, err = _run(data, out, audiences, deep_validate=True)
            self.assertEqual(rc, 3)
            self.assertIn("deep schema validation failed", err)
            self.assertFalse(out.exists())  # refused — not written

    def test_no_deep_validate_flag_lets_it_through(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            data["batch_id"] = "not a valid batch id"
            out = tmp / "out.json"
            rc, _, _ = _run(data, out, audiences, deep_validate=False)
            self.assertEqual(rc, 0)  # shallow gate only — written

    def test_tier2_entry_trio_injected_passes_deep_gate(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            data = _minimal_manifest()
            # tier2 typed-object with id/type/name but NO privacy trio —
            # the normaliser must inject the trio so the gate passes.
            data["tier2_objects"] = {
                "inventory": {"upserts": [
                    {"id": "inv-1", "type": "thing", "name": "Lamp"},
                ]},
            }
            out = tmp / "out.json"
            rc, _, err = _run(data, out, audiences, deep_validate=True)
            self.assertEqual(rc, 0, msg=err)
            written = json.loads(out.read_text(encoding="utf-8"))
            entry = written["tier2_objects"]["inventory"]["upserts"][0]
            self.assertEqual(entry["origin"], "personal")
            self.assertIn("audience_tags", entry)
            self.assertIn("is_sensitive", entry)


if __name__ == "__main__":
    unittest.main()
