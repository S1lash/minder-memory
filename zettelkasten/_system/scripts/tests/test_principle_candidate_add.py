"""Tests for the `principle_candidate_add` action hint — parse, validate, apply.

The miner lens (`cognitive-model`) emits this type. It appends one candidate
to the high-recall `principle-candidates.jsonl` buffer (CAPTURE, not
promotion — `/minder:mem:lint` F.5 gates the constitution downstream).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import _common as c  # type: ignore
import lens_action_handlers as h  # type: ignore


_GOOD_PARAMS = {
    "situation": "Across three debriefs the owner re-derived a decision from its consequence.",
    "observation": "не пересказывай что было — скажи что это значит",
    "hypothesis": "The owner wants conclusions framed forward, not as recap.",
    "suggested_type": "principle",
    "suggested_domain": "ai-interaction",
    "source_record_count": 3,
}


def _make_base(tmp: Path) -> Path:
    base = tmp / "zettelkasten"
    (base / "_system/state").mkdir(parents=True)
    return base


class ParseTests(unittest.TestCase):
    def test_type_is_whitelisted_with_required_params(self):
        self.assertIn("principle_candidate_add", c.ACTION_HINT_TYPES)
        self.assertEqual(
            c.ACTION_HINT_REQUIRED_PARAMS["principle_candidate_add"],
            frozenset({"situation", "observation", "hypothesis",
                       "suggested_type", "suggested_domain", "source_record_count"}),
        )

    def test_well_formed_hint_parses(self):
        body = (
            "Body.\n\n## Action Hints\n"
            "- type: principle_candidate_add\n"
            "  params:\n"
            "    situation: s\n"
            "    observation: o\n"
            "    hypothesis: hyp\n"
            "    suggested_type: principle\n"
            "    suggested_domain: ai-interaction\n"
            "    source_record_count: 3\n"
            "  confidence: medium\n"
            "  brief_reasoning: recurs across records\n"
        )
        hints, drops = c.parse_action_hints(body)
        self.assertEqual(drops, [])
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].type, "principle_candidate_add")

    def test_missing_required_param_is_dropped(self):
        body = (
            "## Action Hints\n"
            "- type: principle_candidate_add\n"
            "  params:\n"
            "    situation: s\n"
            "    observation: o\n"
            "    suggested_type: principle\n"
            "    suggested_domain: ai-interaction\n"
            "  confidence: low\n"
            "  brief_reasoning: x\n"
        )
        hints, drops = c.parse_action_hints(body)
        self.assertEqual(hints, [])
        self.assertEqual(len(drops), 1)
        self.assertIn("missing-params", drops[0]["reason"])
        self.assertIn("hypothesis", drops[0]["reason"])


class ValidateTests(unittest.TestCase):
    def test_passes_on_good_params(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            ok, reason = h.validate_principle_candidate_add(dict(_GOOD_PARAMS), base=base)
            self.assertTrue(ok, reason)

    def test_rejects_bad_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            p = dict(_GOOD_PARAMS, suggested_type="guideline")
            ok, reason = h.validate_principle_candidate_add(p, base=base)
            self.assertFalse(ok)
            self.assertIn("suggested_type", reason)

    def test_rejects_bad_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            p = dict(_GOOD_PARAMS, suggested_domain="nonsense")
            ok, reason = h.validate_principle_candidate_add(p, base=base)
            self.assertFalse(ok)
            self.assertIn("suggested_domain", reason)

    def test_rejects_empty_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            p = dict(_GOOD_PARAMS, observation="   ")
            ok, reason = h.validate_principle_candidate_add(p, base=base)
            self.assertFalse(ok)
            self.assertIn("observation", reason)

    def test_rejects_low_record_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            for bad in (1, 0, True, "3", None):
                p = dict(_GOOD_PARAMS, source_record_count=bad)
                ok, reason = h.validate_principle_candidate_add(p, base=base)
                self.assertFalse(ok, f"{bad!r} should be rejected")
                self.assertIn("source_record_count", reason)

    def test_rejects_duplicate_already_in_buffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            h.apply_principle_candidate_add(dict(_GOOD_PARAMS), "cognitive-model/2026-06-27", base=base)
            # Same observation+hypothesis, whitespace/case perturbed → still a dup.
            p = dict(_GOOD_PARAMS,
                     observation="  НЕ пересказывай что было — скажи что это значит  ".upper().lower())
            ok, reason = h.validate_principle_candidate_add(p, base=base)
            self.assertFalse(ok)
            self.assertIn("already present", reason)


class ApplyTests(unittest.TestCase):
    def test_appends_well_formed_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            out = h.apply_principle_candidate_add(
                dict(_GOOD_PARAMS), source_lens="cognitive-model/2026-06-27", base=base)
            self.assertTrue(out["success"], out["reason"])
            self.assertTrue(out["applied"])
            buf = base / "_system/state/principle-candidates.jsonl"
            self.assertTrue(buf.is_file())
            lines = [l for l in buf.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)
            obj = json.loads(lines[0])
            self.assertEqual(obj["suggested_domain"], "ai-interaction")
            self.assertEqual(obj["source_record_count"], 3)
            self.assertEqual(obj["origin"], "agent-lens")
            self.assertEqual(obj["captured_by"], "minder:mem:agent-lens")
            self.assertEqual(obj["session_id"], "agent-lens/cognitive-model/2026-06-27")
            self.assertEqual(obj["date"], date.today().isoformat())
            self.assertEqual(obj["applies_in_concepts"], [])

    def test_appends_without_clobbering_existing_buffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            buf = base / "_system/state/principle-candidates.jsonl"
            buf.write_text(json.dumps({"observation": "x", "hypothesis": "y"}) + "\n", encoding="utf-8")
            h.apply_principle_candidate_add(
                dict(_GOOD_PARAMS), source_lens="cognitive-model/2026-06-27", base=base)
            lines = [l for l in buf.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)

    def test_apply_refuses_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _make_base(Path(tmp))
            h.apply_principle_candidate_add(dict(_GOOD_PARAMS), "cognitive-model/2026-06-27", base=base)
            out = h.apply_principle_candidate_add(dict(_GOOD_PARAMS), "cognitive-model/2026-06-28", base=base)
            self.assertFalse(out["success"])
            self.assertFalse(out["applied"])
            buf = base / "_system/state/principle-candidates.jsonl"
            lines = [l for l in buf.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
