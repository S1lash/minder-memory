"""Tests for compact_evidence_trail.py."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tests._fixture import clear_minder_memory_env, make_fixture  # type: ignore
import compact_evidence_trail as cmp_module  # type: ignore


def _note_with_trail(entries: list[str]) -> str:
    body = "\n".join(entries)
    return f"""---
id: axiom-identity-001
title: Test
type: axiom
domain: identity
statement: Test
priority_tier: 1
scope: shared
applies_to: [claude-code]
status: active
created: 2020-01-01
last_reviewed: 2020-01-01
last_applied: null
---

# Test

## Evidence Trail
{body}

## Source
test
"""


class CompactTests(unittest.TestCase):
    def test_compacts_old_entries_keeps_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            # Cutoff is 2 years ago → old entries from 2021 get compacted
            old_date = (date.today() - timedelta(days=800)).isoformat()
            recent_date = (date.today() - timedelta(days=100)).isoformat()
            entries = [
                f"- **{recent_date}** | citation-aligned | [[rec-1]] — recent",
                f"- **{old_date}** | citation-aligned | [[rec-old]] — old 1",
                f"- **{old_date}** | citation-aligned | [[rec-old]] — old 2",
            ]
            note = fx.write_principle("axiom/identity/001.md",
                                      _note_with_trail(entries))
            cutoff = (date.today() - timedelta(days=400)).isoformat()
            rc = cmp_module.main([
                "--file", str(note),
                "--cutoff", cutoff,
                "--summary", "test summary",
            ])
            self.assertEqual(rc, 0)
            text = note.read_text(encoding="utf-8")
            self.assertIn("[compacted] test summary", text)
            self.assertIn(recent_date, text)
            # Only one [compacted] line emitted
            self.assertEqual(text.count("[compacted]"), 1)
        clear_minder_memory_env()

    def test_refuses_cutoff_inside_protected_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            note = fx.write_principle("axiom/identity/001.md",
                                      _note_with_trail([
                                          "- **2026-04-01** | landing | — seed",
                                      ]))
            recent_cutoff = (date.today() - timedelta(days=30)).isoformat()
            with self.assertRaises(SystemExit):
                cmp_module.main([
                    "--file", str(note),
                    "--cutoff", recent_cutoff,
                    "--summary", "should never run",
                ])
        clear_minder_memory_env()

    def test_noop_when_no_old_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            recent_date = (date.today() - timedelta(days=30)).isoformat()
            note = fx.write_principle(
                "axiom/identity/001.md",
                _note_with_trail([
                    f"- **{recent_date}** | citation-aligned | [[rec]] — recent only",
                ]),
            )
            cutoff = (date.today() - timedelta(days=400)).isoformat()
            before = note.read_text(encoding="utf-8")
            rc = cmp_module.main([
                "--file", str(note),
                "--cutoff", cutoff,
                "--summary", "won't apply",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(before, note.read_text(encoding="utf-8"))
        clear_minder_memory_env()

    def test_already_compacted_entries_are_skipped(self):
        """Compacting a summary is nonsense — skip anything tagged [compacted]."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            old_date = (date.today() - timedelta(days=800)).isoformat()
            entries = [
                f"- **{old_date}** | compacted | [compacted] previously compacted summary",
                f"- **{old_date}** | citation-aligned | [[r1]] — raw entry 1",
                f"- **{old_date}** | citation-aligned | [[r2]] — raw entry 2",
            ]
            note = fx.write_principle("axiom/identity/001.md",
                                      _note_with_trail(entries))
            cutoff = (date.today() - timedelta(days=400)).isoformat()
            rc = cmp_module.main([
                "--file", str(note),
                "--cutoff", cutoff,
                "--summary", "new summary",
            ])
            self.assertEqual(rc, 0)
            text = note.read_text(encoding="utf-8")
            # Old [compacted] entry must still be there
            self.assertIn("previously compacted summary", text)
            # New [compacted] entry added
            self.assertIn("[compacted] new summary", text)
            # Raw entries gone
            self.assertNotIn("raw entry 1", text)
            self.assertNotIn("raw entry 2", text)
        clear_minder_memory_env()

    def test_frontmatter_bytes_preserved(self):
        """Frontmatter block must come out byte-identical after compaction —
        no key-order shuffle, no quoting change, no yaml round-trip artefact."""
        entries_old = (date.today() - timedelta(days=800)).isoformat()
        recent = (date.today() - timedelta(days=30)).isoformat()
        note_text = f"""---
id: axiom-identity-001
title: 'Preserve me exactly: quoting style matters'
type: axiom
domain: identity
statement: Test
priority_tier: 1
scope: shared
applies_to: [claude-code, minder-memory]
binding: hard
status: active
created: 2020-01-01
last_reviewed: 2020-01-01
last_applied: null
source_weight:
  own_experience: 5
  external_author: 0
---

# Body

## Evidence Trail
- **{recent}** | citation-aligned | [[r1]] — recent
- **{entries_old}** | citation-aligned | [[r2]] — old

## Source
test
"""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            note = fx.write_principle("axiom/identity/001.md", note_text)
            cutoff = (date.today() - timedelta(days=400)).isoformat()
            cmp_module.main([
                "--file", str(note),
                "--cutoff", cutoff,
                "--summary", "ok",
            ])
            result = note.read_text(encoding="utf-8")
            # Extract frontmatter block from both original and result
            orig_fm = note_text.split("---", 2)[1]
            result_fm = result.split("---", 2)[1]
            self.assertEqual(orig_fm, result_fm,
                             "frontmatter bytes must be identical after compact")
        clear_minder_memory_env()

    def test_frontmatter_with_triple_dash_in_value_survives(self):
        """Regression: earlier naive split-on-'---' would mangle this."""
        note_text = """---
id: axiom-identity-001
title: Test with --- inside
type: axiom
domain: identity
statement: |
  Line one.
  Separator: ---
  Line three.
priority_tier: 1
scope: shared
applies_to: [claude-code]
status: active
created: 2020-01-01
last_reviewed: 2020-01-01
last_applied: null
---

# Test

## Evidence Trail
- **{old}** | citation-aligned | [[r1]] — old entry

## Source
test
"""
        from datetime import date as _d, timedelta as _td
        old_date = (_d.today() - _td(days=800)).isoformat()
        populated = note_text.replace("{old}", old_date)
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            note = fx.write_principle("axiom/identity/001.md", populated)
            cutoff = (_d.today() - _td(days=400)).isoformat()
            rc = cmp_module.main([
                "--file", str(note),
                "--cutoff", cutoff,
                "--summary", "ok",
            ])
            self.assertEqual(rc, 0)
            result = note.read_text(encoding="utf-8")
            # Statement value must still contain the literal '---'
            self.assertIn("Separator: ---", result)
            # Frontmatter must still parse as valid YAML after rewrite
            import _common as c  # type: ignore
            p = c.parse_file(note)
            self.assertEqual(p.id, "axiom-identity-001")
        clear_minder_memory_env()


if __name__ == "__main__":
    unittest.main()
