"""Tests for rewrite_manifest_violations.py — one-shot retrofit utility.

Coverage:
- broken manifest (bare-string sources, non-empty bare-string tier1.people,
  missing privacy trio) → post-retrofit passes schema validation
- dry-run does NOT mutate the file on disk
- --apply writes back atomically
- clean manifest → no-op (idempotent)
- single-file mode
- directory mode batches multiple files
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import rewrite_manifest_violations as r  # type: ignore
from tests._fixture import clear_minder_memory_env  # type: ignore


def _audiences_file(root: Path) -> Path:
    p = root / "AUDIENCES.md"
    p.write_text(
        "# Audiences\n"
        "<!-- BEGIN extensions -->\n"
        "| Tag | Added | Status | Purpose | Notes |\n"
        "|---|---|---|---|---|\n"
        "<!-- END extensions -->\n",
        encoding="utf-8",
    )
    return p


def _domains_file(root: Path) -> Path:
    p = root / "DOMAINS.md"
    p.write_text(
        "# Domains\n"
        "<!-- BEGIN extensions -->\n"
        "| Domain | Added | Status | Purpose | Notes |\n"
        "|---|---|---|---|---|\n"
        "<!-- END extensions -->\n",
        encoding="utf-8",
    )
    return p


def _broken_manifest() -> dict:
    """Manifest exhibiting every broken pattern Phase 3 fixes."""
    return {
        "batch_id": "20260514-103200",
        "timestamp": "2026-05-14T10:32:00Z",
        "format_version": "2.1",
        "processor": "minder:mem:process",
        # Bare strings + structured (mixed list).
        "sources_processed": [
            "_sources/processed/plaud/2026-05-14T10:00:00Z/transcript.md",
            "_sources/processed/garmin/2026-05-14/metrics.md",
        ],
        # Missing privacy trio.
        "records": {
            "created": [
                {"path": "_records/meetings/foo.md"},
            ],
            "updated": [],
        },
        "knowledge_notes": {"created": [], "updated": []},
        # Non-empty bare-string array.
        "hubs": [],
        "concepts": {
            "upserts": [{"name": "manifest_schema_evolution",
                         "type": "technical"}],
        },
        "tier1_objects": {
            "people": ["alice-smith", "bob-jones"],
            "projects": [{"id": "minder"}],
        },
        "stats": {},
    }


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = r.main(args)
    return rc, out_buf.getvalue(), err_buf.getvalue()


class RetrofitTests(unittest.TestCase):
    def test_broken_manifest_retrofitted_to_schema_valid(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp)
            audience_accept = {"work", "family", "world", "team", "client"}
            domain_accept = {"work", "career", "health", "identity"}
            data = _broken_manifest()
            retro, events = r.retrofit_manifest(
                data, audience_accept, domain_accept,
            )
            # sources_processed: bare strings wrapped
            for entry in retro["sources_processed"]:
                self.assertIsInstance(entry, dict)
                self.assertIn("path", entry)
            self.assertEqual(
                retro["sources_processed"][0]["source_type"],
                "plaud-transcript",
            )
            self.assertEqual(
                retro["sources_processed"][1]["source_type"],
                "garmin-daily",
            )
            # hubs: empty list became canonical envelope
            self.assertEqual(retro["hubs"], {"created": [], "updated": []})
            # tier1.people: bare strings wrapped into upserts
            self.assertEqual(
                [u["id"] for u in retro["tier1_objects"]["people"]["upserts"]],
                ["alice-smith", "bob-jones"],
            )
            # tier1.projects: dict list bucketed into upserts; trio defaults
            # injected because tier1.projects.upserts is an entity-list path.
            self.assertEqual(
                retro["tier1_objects"]["projects"]["upserts"][0]["id"],
                "minder",
            )
            self.assertEqual(
                retro["tier1_objects"]["projects"]["upserts"][0]["origin"],
                "personal",
            )
            # records[0]: privacy trio injected
            rec = retro["records"]["created"][0]
            self.assertEqual(rec["origin"], "personal")
            self.assertEqual(rec["audience_tags"], [])
            self.assertEqual(rec["is_sensitive"], False)
            # Events should have multiple fix categories
            event_ids = {ev["fix_id"] for ev in events}
            self.assertIn("sources-processed-coerce-autofix", event_ids)
            self.assertIn("hubs-empty-shape-autofix", event_ids)
            self.assertIn("tier1-bare-string-wrap-autofix", event_ids)
            self.assertIn("privacy-trio-inject-autofix", event_ids)
        clear_minder_memory_env()

    def test_idempotent_on_clean_input(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp)
            audience_accept, domain_accept = r._load_accept_sets(
                audiences, domains,
            )
            data = {
                "batch_id": "20260514-103200",
                "timestamp": "2026-05-14T10:32:00Z",
                "format_version": "2.1",
                "processor": "minder:mem:process",
                "sources_processed": [],
                "records": {"created": [], "updated": []},
                "knowledge_notes": {"created": [], "updated": []},
                "hubs": {"created": [], "updated": []},
                "concepts": {"upserts": []},
                "stats": {},
            }
            before = json.dumps(data, sort_keys=True)
            _, events = r.retrofit_manifest(
                data, audience_accept, domain_accept,
            )
            after = json.dumps(data, sort_keys=True)
            self.assertEqual(before, after)
            self.assertEqual(events, [])
        clear_minder_memory_env()


class CliDryRunTests(unittest.TestCase):
    def test_dry_run_does_not_mutate_file(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp)
            batches = tmp / "batches"
            batches.mkdir()
            broken = batches / "20260514-103200-process.json"
            original = json.dumps(_broken_manifest(), indent=2)
            broken.write_text(original, encoding="utf-8")

            rc, out, _ = _run_cli([
                "--batches-dir", str(batches),
                "--audiences", str(audiences),
                "--domains", str(domains),
            ])
            self.assertEqual(rc, 0)
            self.assertIn("would change", out)
            # File on disk is unchanged.
            self.assertEqual(broken.read_text(encoding="utf-8"), original)
        clear_minder_memory_env()

    def test_apply_rewrites_file(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp)
            batches = tmp / "batches"
            batches.mkdir()
            broken = batches / "20260514-103200-process.json"
            broken.write_text(
                json.dumps(_broken_manifest(), indent=2), encoding="utf-8",
            )

            rc, out, _ = _run_cli([
                "--batches-dir", str(batches),
                "--audiences", str(audiences),
                "--domains", str(domains),
                "--apply",
            ])
            self.assertEqual(rc, 0)
            self.assertIn("rewrote", out)
            written = json.loads(broken.read_text(encoding="utf-8"))
            self.assertIsInstance(written["sources_processed"][0], dict)
            upserts = written["tier1_objects"]["people"]["upserts"]
            self.assertEqual(
                [u["id"] for u in upserts],
                ["alice-smith", "bob-jones"],
            )
            self.assertEqual(
                written["records"]["created"][0]["origin"], "personal",
            )
        clear_minder_memory_env()

    def test_clean_file_reports_clean(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp)
            batches = tmp / "batches"
            batches.mkdir()
            clean = batches / "20260514-103200-process.json"
            clean.write_text(json.dumps({
                "batch_id": "20260514-103200",
                "timestamp": "2026-05-14T10:32:00Z",
                "format_version": "2.1",
                "processor": "minder:mem:process",
                "sources_processed": [],
                "records": {"created": [], "updated": []},
                "knowledge_notes": {"created": [], "updated": []},
                "hubs": {"created": [], "updated": []},
                "concepts": {"upserts": []},
                "stats": {},
            }, indent=2), encoding="utf-8")
            rc, out, _ = _run_cli([
                "--batches-dir", str(batches),
                "--audiences", str(audiences),
                "--domains", str(domains),
            ])
            self.assertEqual(rc, 0)
            self.assertIn("clean", out)
        clear_minder_memory_env()

    def test_single_file_mode(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            audiences = _audiences_file(tmp)
            domains = _domains_file(tmp)
            broken = tmp / "broken.json"
            broken.write_text(
                json.dumps(_broken_manifest(), indent=2), encoding="utf-8",
            )
            rc, out, _ = _run_cli([
                "--file", str(broken),
                "--audiences", str(audiences),
                "--domains", str(domains),
                "--apply",
            ])
            self.assertEqual(rc, 0)
            written = json.loads(broken.read_text(encoding="utf-8"))
            self.assertEqual(
                written["tier1_objects"]["projects"]["upserts"][0]["id"],
                "minder",
            )
        clear_minder_memory_env()


class RetrofitFullPipelineTests(unittest.TestCase):
    def test_retrofit_handles_legacy_sensitive_entities_shape(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _audiences_file(tmp)
            _domains_file(tmp)
            audience_accept = {"work", "family", "world", "team", "client"}
            domain_accept = {"work", "career", "health", "identity"}
            data = {
                "batch_id": "20260514-103200",
                "timestamp": "2026-05-14T10:32:00Z",
                "format_version": "2.1",
                "processor": "minder:mem:process",
                "sources_processed": [],
                "records": {"created": [], "updated": []},
                "knowledge_notes": {"created": [], "updated": []},
                "hubs": {"created": [], "updated": []},
                "concepts": {"upserts": []},
                "sensitive_entities": [
                    {"note_id": "20260506-therapy", "reason": "privacy"},
                ],
                "stats": {},
            }
            retro, events = r.retrofit_manifest(
                data, audience_accept, domain_accept,
            )
            entry = retro["sensitive_entities"][0]
            self.assertEqual(entry["id"], "20260506-therapy")
            self.assertEqual(entry["kind"], "note")
            self.assertEqual(entry["reason"], "privacy")
            self.assertNotIn("note_id", entry)
            self.assertIn(
                "sensitive-entities-note-id-coerce-autofix",
                {ev["fix_id"] for ev in events},
            )
        clear_minder_memory_env()

    def test_retrofit_relocates_misplaced_tier2_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _audiences_file(tmp)
            _domains_file(tmp)
            audience_accept = {"work", "family", "world", "team", "client"}
            domain_accept = {"work", "career", "health", "identity"}
            data = {
                "batch_id": "20260514-103200",
                "timestamp": "2026-05-14T10:32:00Z",
                "format_version": "2.1",
                "processor": "minder:mem:process",
                "sources_processed": [],
                "records": {"created": [], "updated": []},
                "knowledge_notes": {"created": [], "updated": []},
                "hubs": {"created": [], "updated": []},
                "concepts": {"upserts": []},
                "tier2_objects": {
                    "tasks": {
                        "upserts": [
                            {
                                "id": "task-pay-the-bill",
                                "type": "action",
                                "due": "2026-05-20",
                            },
                        ],
                    },
                },
                "stats": {},
            }
            retro, events = r.retrofit_manifest(
                data, audience_accept, domain_accept,
            )
            self.assertNotIn(
                "tasks", retro.get("tier2_objects", {}) or {},
            )
            created = retro["tier1_objects"]["tasks"]["created"]
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0]["id"], "task-pay-the-bill")
            self.assertEqual(created[0]["title"], "Pay the bill")
            self.assertEqual(created[0]["ownership"], "MINE")
            self.assertEqual(created[0]["deadline"], "2026-05-20")
            self.assertIn(
                "tier2-tasks-relocated-to-tier1",
                {ev["fix_id"] for ev in events},
            )
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()


class HistoricalRepairTests(unittest.TestCase):
    """Corruption classes that predate producer conformance.

    Every repair derives its value from the manifest or from disk. None is
    invented — a manifest whose missing value cannot be derived is quarantined
    honestly rather than filled with a plausible one.
    """

    def _base(self, tmp: str) -> Path:
        base = Path(tmp)
        (base / "_records" / "meetings").mkdir(parents=True)
        (base / "2_areas").mkdir(parents=True)
        return base

    def test_truncated_timestamp_rebuilt_from_filename(self):
        data = {"timestamp": "2026-07-20T23", "section_extras": {}}
        events = r.repair_historical(
            data, filename="/x/20260720-152238-maintain.json", base=None
        )
        self.assertEqual(data["timestamp"], "2026-07-20T15:22:38Z")
        self.assertEqual(data["section_extras"]["legacy_timestamp"], "2026-07-20T23")
        self.assertTrue(any(e["event"] == "timestamp_truncated" for e in events))

    def test_null_section_extras_becomes_object(self):
        data = {"section_extras": None}
        r.repair_historical(data, filename="/x/20260720-152238-process.json", base=None)
        self.assertEqual(data["section_extras"], {})

    def test_batch_id_loses_the_skill_suffix(self):
        data = {"batch_id": "20260801-230515-process"}
        r.repair_historical(data, filename="/x/20260801-230515-process.json", base=None)
        self.assertEqual(data["batch_id"], "20260801-230515")
        self.assertEqual(
            data["section_extras"]["legacy_batch_id"], "20260801-230515-process"
        )

    def test_null_id_and_title_recovered_from_path_and_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            note = base / "_records" / "meetings" / "20260726-meeting-x.md"
            note.write_text("# Встреча: тема\n\nbody\n", encoding="utf-8")
            data = {
                "records": {
                    "created": [
                        {
                            "path": "_records/meetings/20260726-meeting-x.md",
                            "id": None,
                            "title": None,
                        }
                    ]
                }
            }
            r.repair_historical(data, filename="/x/20260726-110000-process.json", base=base)
            entry = data["records"]["created"][0]
            self.assertEqual(entry["id"], "20260726-meeting-x")
            self.assertEqual(entry["title"], "Встреча: тема")

    def test_absent_title_is_left_alone(self):
        """An absent optional field is an early dialect, not corruption."""
        data = {"records": {"created": [{"path": "_records/meetings/a.md", "id": "a"}]}}
        r.repair_historical(data, filename="/x/20260726-110000-process.json", base=None)
        self.assertNotIn("title", data["records"]["created"][0])

    def test_missing_path_located_by_unique_note_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            (base / "2_areas" / "some-insight.md").write_text("# T\n", encoding="utf-8")
            data = {"knowledge_notes": {"created": [{"id": "some-insight"}]}}
            r.repair_historical(data, filename="/x/20260726-110000-process.json", base=base)
            self.assertEqual(
                data["knowledge_notes"]["created"][0]["path"], "2_areas/some-insight.md"
            )

    def test_missing_path_not_guessed_when_the_note_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            data = {"knowledge_notes": {"created": [{"id": "vanished-note"}]}}
            r.repair_historical(data, filename="/x/20260726-110000-process.json", base=base)
            self.assertNotIn("path", data["knowledge_notes"]["created"][0])

    def test_truncated_checksum_recomputed_never_padded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            note = base / "_records" / "meetings" / "n.md"
            note.write_text("content\n", encoding="utf-8")
            import hashlib

            expected = hashlib.sha256(note.read_bytes()).hexdigest()
            data = {
                "records": {
                    "created": [
                        {
                            "path": "_records/meetings/n.md",
                            "id": "n",
                            "checksum_sha256": expected[:63],
                        }
                    ]
                }
            }
            r.repair_historical(data, filename="/x/20260726-110000-process.json", base=base)
            self.assertEqual(data["records"]["created"][0]["checksum_sha256"], expected)

    def test_truncated_checksum_left_alone_when_file_is_gone(self):
        data = {
            "records": {
                "created": [
                    {"path": "_records/meetings/gone.md", "id": "gone",
                     "checksum_sha256": "a" * 63}
                ]
            }
        }
        r.repair_historical(data, filename="/x/20260726-110000-process.json", base=None)
        self.assertEqual(data["records"]["created"][0]["checksum_sha256"], "a" * 63)

    def test_null_org_dropped(self):
        data = {"records": {"created": [{"path": "p.md", "id": "p", "org": None}]}}
        r.repair_historical(data, filename="/x/20260726-110000-process.json", base=None)
        self.assertNotIn("org", data["records"]["created"][0])

    def test_lens_observation_entries_are_not_given_a_type(self):
        """`lens_observation` has its own entry shape — no `type`, no `name`."""
        data = {
            "tier2_objects": {
                "lens_observation": {"upserts": [{"id": "lens-obs-1", "path": "p.md"}]},
                "activity": {"upserts": [{"path": "_system/views/activity/w.md"}]},
            }
        }
        r.repair_historical(data, filename="/x/20260726-110000-maintain.json", base=None)
        lens = data["tier2_objects"]["lens_observation"]["upserts"][0]
        self.assertNotIn("type", lens)
        self.assertNotIn("name", lens)
        activity = data["tier2_objects"]["activity"]["upserts"][0]
        self.assertEqual(activity["type"], "activity")
        self.assertEqual(activity["id"], "w")

    def test_repair_is_idempotent(self):
        data = {"timestamp": "2026-07-20T23", "batch_id": "20260720-152238-maintain"}
        r.repair_historical(data, filename="/x/20260720-152238-maintain.json", base=None)
        first = json.dumps(data, sort_keys=True)
        r.repair_historical(data, filename="/x/20260720-152238-maintain.json", base=None)
        self.assertEqual(json.dumps(data, sort_keys=True), first)


class QuarantineTests(unittest.TestCase):
    def test_marker_carries_the_reason_with_the_entity(self):
        data = {"section_extras": {}}
        r.quarantine(data, reason="unreachable", errors=["e1", "e2"], ts="2026-08-07T00:00:00Z")
        q = data["section_extras"]["quarantine"]
        self.assertEqual(q["reason"], "unreachable")
        self.assertEqual(q["errors"], ["e1", "e2"])
        self.assertEqual(q["marked"], "2026-08-07T00:00:00Z")

    def test_marker_creates_section_extras_when_absent(self):
        data = {}
        r.quarantine(data, reason="x", errors=[], ts="2026-08-07T00:00:00Z")
        self.assertIn("quarantine", data["section_extras"])


class BatchIdRecoveryTests(unittest.TestCase):
    """A malformed `batch_id` is recovered from the manifest's own timestamp.

    A live tick wrote `batch_id: 20260807-processtick` — it had assembled the
    JSON and written it to `batches/` WITHOUT invoking the emitter, so the
    emitter's refusal (which does fire; replaying that file through it exits 3)
    never got the chance. The real instant was sitting in the same document as
    `2026-08-07T15:12:38Z`, so recovering `20260807-151238` reads the document
    rather than guessing at it.
    """

    @staticmethod
    def _conform(raw, stem=None, ts=None):
        import emit_batch_manifest as e  # type: ignore

        return e._conform_batch_id(raw, stem, ts)

    def test_recovers_the_exact_time_from_the_timestamp(self):
        self.assertEqual(
            self._conform("20260807-processtick", None, "2026-08-07T15:12:38Z"),
            "20260807-151238",
        )

    def test_refuses_a_timestamp_from_a_different_day(self):
        """A date mismatch means the two fields disagree — do not pick a winner."""
        self.assertEqual(
            self._conform("20260807-processtick", None, "2026-08-01T15:12:38Z"),
            "20260807-000000",
        )

    def test_zero_fills_when_there_is_no_timestamp_to_read(self):
        self.assertEqual(self._conform("20260807-processtick", None, None),
                         "20260807-000000")

    def test_a_conformant_id_is_returned_untouched(self):
        self.assertEqual(self._conform("20260807-151238", None, "2026-08-07T09:00:00Z"),
                         "20260807-151238")

    def test_no_date_anywhere_yields_nothing(self):
        self.assertIsNone(self._conform("processtick", None, "2026-08-07T15:12:38Z"))

    def test_end_to_end_repair_keeps_the_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260807-processtick-process.json"
            path.write_text(json.dumps({
                "batch_id": "20260807-processtick",
                "timestamp": "2026-08-07T15:12:38Z",
                "format_version": "2.1",
                "processor": "minder:mem:process",
            }, ensure_ascii=False), encoding="utf-8")

            data = json.loads(path.read_text(encoding="utf-8"))
            r.repair_historical(data, filename=str(path), base=None)
            self.assertEqual(data["batch_id"], "20260807-151238")
            self.assertEqual(
                data["section_extras"]["legacy_batch_id"], "20260807-processtick"
            )

    def test_the_emitter_still_refuses_a_malformed_id_it_is_handed(self):
        """The producer's refusal is the first line of defence and must stay."""
        import emit_batch_manifest as e  # type: ignore

        with self.assertRaises(Exception):
            e.validate_manifest({"batch_id": "20260807-processtick"})
