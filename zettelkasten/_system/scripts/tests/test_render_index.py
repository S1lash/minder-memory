"""Tests for render_index.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import (  # type: ignore
    VALID_NOTE,
    VALID_PERSONAL_NOTE,
    VALID_SENSITIVE_NOTE,
    clear_minder_memory_env,
    make_fixture,
)
import render_index as r  # type: ignore


KNOWLEDGE_NOTE = """---
id: 20260101-test-knowledge-note
title: Test knowledge note
description: Concise description from frontmatter
created: 2026-01-01
modified: 2026-01-15
domains:
- work
- learning
layer: knowledge
---

# Body
First prose line.
"""


KNOWLEDGE_NOTE_NO_DESC = """---
id: 20260102-no-description
title: Note without description
created: 2026-01-02
modified: 2026-01-02
domains:
- personal
layer: knowledge
---

# Heading

Body line should be summary.
"""


KNOWLEDGE_NOTE_NO_DOMAINS = """---
id: 20260103-no-domains
title: Unscoped note
created: 2026-01-03
modified: 2026-01-03
layer: knowledge
---

# Body
Just text.
"""


CROSS_DOMAIN_NOTE = """---
id: 20260104-bridge
title: Bridge note
description: Cross-domain bridge
created: 2026-01-04
modified: 2026-01-04
domains:
- work
- personal
- identity
layer: knowledge
---

# Body
"""


ARCHIVE_NOTE = """---
id: legacy-thing
title: Legacy archived thing
created: 2025-06-01
modified: 2025-06-01
domains:
- work
---

# Body
Archived material.
"""


HUB_NOTE = """---
id: hub-test-cluster
title: 'Hub: Test cluster'
description: Test hub for inbound counting
created: 2026-01-05
modified: 2026-01-10
hub_created: 2026-01-05
layer: hub
domains:
- work
- tech
---

# Body
Hub content.
"""


REFERENCING_NOTE = """---
id: 20260106-refers-hub
title: Note referencing the hub
created: 2026-01-06
modified: 2026-01-06
domains:
- work
layer: knowledge
---

# Body
This note links to [[hub-test-cluster]] and again [[hub-test-cluster]].
"""


def _write(base: Path, rel: str, content: str) -> Path:
    dest = base / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


class RenderIndexTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_minder_memory_env()

    def test_empty_base_renders_with_zero_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            out = fx.base / "_system" / "views" / "INDEX.md"
            rc = r.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("note_count: 0", text)
            self.assertIn("archive_count: 0", text)
            self.assertIn("constitution_count: 0", text)
            self.assertIn("hub_count: 0", text)
            self.assertIn("## By PARA", text)
            self.assertIn("## Archive", text)
            self.assertIn("## Constitution", text)
            self.assertIn("## By Domain", text)
            self.assertIn("## Cross-domain", text)
            self.assertIn("## Hubs", text)

    def test_knowledge_note_in_para_and_by_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "2_areas/work/note.md", KNOWLEDGE_NOTE)
            out = fx.base / "_system" / "views" / "INDEX.md"
            rc = r.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("note_count: 1", text)
            # PARA — Areas section has the entry with full row format
            self.assertIn(
                "[[20260101-test-knowledge-note]] — Concise description "
                "from frontmatter · `[work, learning]` · 2026-01-15",
                text,
            )
            # By Domain — work facet
            self.assertIn("### work (1)", text)
            self.assertIn("### learning (1)", text)

    def test_summary_fallback_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "2_areas/personal/note.md", KNOWLEDGE_NOTE_NO_DESC)
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            # description absent → title used
            self.assertIn("— Note without description", text)

    def test_unscoped_bucket_for_no_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "2_areas/misc/note.md", KNOWLEDGE_NOTE_NO_DOMAINS)
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertIn("### unscoped (1)", text)
            self.assertIn("[[20260103-no-domains]]", text)

    def test_cross_domain_section_only_2plus_canonical_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "2_areas/personal/single.md", KNOWLEDGE_NOTE_NO_DOMAINS)
            _write(fx.base, "2_areas/personal/bridge.md", CROSS_DOMAIN_NOTE)
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertIn("Cross-domain (≥ 2 domains, 1)", text)
            self.assertIn("[[20260104-bridge]]", text)
            self.assertNotIn(
                "## Cross-domain (≥ 2 domains, 1)\n\n"
                "Notes whose `domains:` list contains 2+ canonical values.",
                text.split("[[20260103-no-domains]]")[0],  # noqa
            )

    def test_archive_renders_with_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "4_archive/people/legacy.md", ARCHIVE_NOTE)
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertIn("archive_count: 1", text)
            self.assertIn(
                "[[legacy-thing]] — [archived] Legacy archived thing",
                text,
            )

    def test_constitution_renders_with_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            fx.write_principle("principle/tech/001.md", VALID_PERSONAL_NOTE)
            fx.write_principle("rule/health/001.md", VALID_SENSITIVE_NOTE)
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertIn("constitution_count: 3", text)
            self.assertIn("### Axioms — 1", text)
            self.assertIn("### Principles — 1", text)
            self.assertIn("### Rules — 1", text)
            self.assertIn(
                "[[axiom-identity-001]] — If it can be better, it should be "
                "better · `[identity]` · tier 1 ·",
                text,
            )

    def test_hubs_inbound_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "5_meta/mocs/hub-test-cluster.md", HUB_NOTE)
            _write(fx.base, "2_areas/work/refer.md", REFERENCING_NOTE)
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertIn("hub_count: 1", text)
            # Two `[[hub-test-cluster]]` mentions in the referencing note
            self.assertIn(
                "[[hub-test-cluster]] — Test hub for inbound counting",
                text,
            )
            self.assertIn("· 2 inbound · upd 2026-01-10", text)

    def test_records_and_posts_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "_records/meetings/2026-01-01-meeting.md",
                   "---\nid: 20260101-meeting\ntitle: Meeting\nlayer: record\n---\nbody")
            _write(fx.base, "6_posts/post-1.md",
                   "---\nid: post-1\ntitle: Post\n---\nbody")
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertNotIn("[[20260101-meeting]]", text)
            self.assertNotIn("[[post-1]]", text)
            self.assertIn("note_count: 0", text)

    def test_readme_files_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "1_projects/README.md",
                   "---\nid: readme-1\ntitle: Projects README\n---\nx")
            _write(fx.base, "1_projects/p1.md",
                   "---\nid: p1\ntitle: Real project\ndomains: [work]\n"
                   "modified: 2026-01-01\n---\nbody")
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertNotIn("[[readme-1]]", text)
            self.assertIn("[[p1]]", text)
            self.assertIn("Projects (`1_projects/`) — 1", text)

    def test_atomic_write_replaces_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            out = fx.base / "_system" / "views" / "INDEX.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("STALE\n", encoding="utf-8")
            r.main(["--output", str(out)])
            text = out.read_text(encoding="utf-8")
            self.assertNotIn("STALE", text)
            self.assertIn("# Wiki Index", text)
            # No leftover .tmp
            self.assertFalse((out.parent / "INDEX.md.tmp").exists())

    def test_deterministic_across_runs(self):
        """Two consecutive runs must produce byte-identical output except
        for the timestamp line in the frontmatter."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = make_fixture(Path(tmp))
            _write(fx.base, "2_areas/work/note.md", KNOWLEDGE_NOTE)
            _write(fx.base, "5_meta/mocs/hub-test-cluster.md", HUB_NOTE)
            fx.write_principle("axiom/identity/001.md", VALID_NOTE)
            out = fx.base / "_system" / "views" / "INDEX.md"
            r.main(["--output", str(out)])
            first = out.read_text(encoding="utf-8")
            r.main(["--output", str(out)])
            second = out.read_text(encoding="utf-8")
            # Strip the generated: line for comparison
            def strip_ts(s: str) -> str:
                return "\n".join(
                    line for line in s.splitlines()
                    if not line.startswith("generated:")
                )
            self.assertEqual(strip_ts(first), strip_ts(second))


if __name__ == "__main__":
    unittest.main()
