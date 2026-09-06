"""Orphan namespaced tags — a tag naming an identity no registry declares.

The gap this closes. The audit reasons outward from identities the registry
declares: for each one it asks where the identifier still appears. An
identifier the registry never declared has no entity to reason from, so it is
not examined at all — `project/some-topic` sits on a note forever while every
scan reports clean. The registry is the single source of truth for what a
project IS; a tag in the project namespace naming something it never declared
is drift by that same rule.

Two boundaries make this safe rather than noisy. Only namespaces a registry
CLAIMS are judged — `topic/`, `domain/`, `type/` and the rest are nobody's
identities. And an orphan is a fact about the base, not about any one identity,
so it never enters a per-identity gate: it must not fail the proof of an
unrelated retirement.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import identity_audit as ia  # type: ignore



def _scaffold(root: Path) -> None:
    for sub in (
        "_records/meetings", "1_projects", "2_areas", "3_resources",
        "4_archive", "5_meta/mocs", "_system/views", "_sources/inbox",
        "_system/state",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _write_projects_md(root: Path, body: str) -> None:
    (root / "1_projects" / "PROJECTS.md").write_text(body, encoding="utf-8")


def _write_note(root: Path, rel: str, *, tags: list[str] | None = None,
                body: str = "body\n") -> Path:
    fm = f"id: {Path(rel).stem}\n"
    if tags is not None:
        fm += "tags:\n" + "".join(f"  - {t}\n" for t in tags)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}---\n{body}", encoding="utf-8")
    return path

_REGISTRY = """# Projects

| ID | Name | Description | Path | Scope | Status |
|---|---|---|---|---|---|
| alpha-app | Alpha | a | 1_projects/alpha-app/ | work | active |

## Retired Identifiers

| ID | Kind | Successor | Reason |
|---|---|---|---|
| legacy-thing | merge | alpha-app | folded in |
"""


def _base(tmp: str) -> Path:
    root = Path(tmp)
    _scaffold(root)
    _write_projects_md(root, _REGISTRY)
    return root


def _orphans(root: Path, identity: str | None = None) -> list[dict]:
    return ia.audit(root, identity=identity).get("orphans", [])


class OrphanDetectionTests(unittest.TestCase):
    def test_tag_naming_an_undeclared_identity_is_an_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/never-registered"])
            found = _orphans(root)
            self.assertEqual([o["tag"] for o in found], ["project/never-registered"])
            self.assertEqual(found[0]["registry"], "project")

    def test_a_registered_identity_is_not_an_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/alpha-app"])
            self.assertEqual(_orphans(root), [])

    def test_a_namespace_no_registry_claims_is_not_judged(self):
        """`topic/`, `domain/`, `type/` are nobody's identities."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md",
                        tags=["topic/anything", "domain/work", "type/decision"])
            self.assertEqual(_orphans(root), [])

    def test_a_retired_identity_is_residue_not_an_orphan(self):
        """It IS declared — by the retirement row. Counting it twice would
        report one defect as two and offer two contradictory resolutions."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            self.assertEqual(_orphans(root), [])
            self.assertGreater(ia.audit(root)["surface_residue_count"], 0)

    def test_orphan_counts_as_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/never-registered"])
            result = ia.audit(root)
            self.assertEqual(result["orphan_count"], 1)
            self.assertFalse(result["clean"])

    def test_a_baselined_orphan_does_not_fail_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/never-registered"])
            (root / "_system" / "state" / ia.ORPHAN_BASELINE_NAME).write_text(
                "project/never-registered | 2_areas/a.md\n", encoding="utf-8")
            result = ia.audit(root)
            self.assertEqual(result["orphan_count"], 0)
            self.assertEqual(len(result["orphans_baselined"]), 1)
            self.assertTrue(result["clean"])

    def test_a_new_orphan_fails_even_when_another_is_baselined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/never-registered"])
            _write_note(root, "2_areas/b.md", tags=["project/brand-new"])
            (root / "_system" / "state" / ia.ORPHAN_BASELINE_NAME).write_text(
                "project/never-registered | 2_areas/a.md\n", encoding="utf-8")
            result = ia.audit(root)
            self.assertEqual([o["tag"] for o in result["orphans"]], ["project/brand-new"])
            self.assertFalse(result["clean"])

    def test_baseline_is_pinned_to_the_path(self):
        """The same orphan appearing somewhere new is a new orphan."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/never-registered"])
            _write_note(root, "2_areas/moved.md", tags=["project/never-registered"])
            (root / "_system" / "state" / ia.ORPHAN_BASELINE_NAME).write_text(
                "project/never-registered | 2_areas/a.md\n", encoding="utf-8")
            self.assertEqual([o["path"] for o in _orphans(root)], ["2_areas/moved.md"])

    def test_per_identity_run_drops_orphans(self):
        """An orphan belongs to the base; it must never fail one retirement."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/never-registered"])
            result = ia.audit(root, identity="legacy-thing")
            self.assertEqual(result["orphans"], [])
            self.assertEqual(result["orphan_count"], 0)


class TagGrammarTests(unittest.TestCase):
    def test_nested_slash_uses_the_same_splitter_as_every_other_surface(self):
        """`project/a/b` splits on the LAST slash everywhere in this module.

        Two splitters — one on the first slash, one on the last — agree on every
        flat tag and disagree on the first hierarchical one, which is why the
        divergence would have shipped unseen.
        """
        self.assertEqual(ia._split_tag("project/a/b"), ("project/a", "b"))
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/a/b"])
            # namespace is `project/a`, which no registry claims → not judged
            self.assertEqual(_orphans(root), [])

    def test_malformed_tags_are_ignored_not_crashed_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/", "/orphan", "plain"])
            self.assertEqual(_orphans(root), [])

    def test_scalar_tags_field_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            path = root / "2_areas" / "s.md"
            path.write_text("---\nid: s\ntags: project/never-registered\n---\nbody\n",
                            encoding="utf-8")
            self.assertEqual([o["tag"] for o in _orphans(root)],
                             ["project/never-registered"])


class NamespaceOwnershipTests(unittest.TestCase):
    def test_every_claimed_namespace_has_exactly_one_registry(self):
        """Two registries claiming one namespace is a defect of the declaration.

        Without this the orphan check would silently pick whichever spec it
        happened to see first, and one registry's identities would read as the
        other's orphans.
        """
        owners = ia.namespace_owners(ia.REGISTRY_SPECS)
        self.assertIn("project", owners)
        self.assertIn("person", owners)
        self.assertIn("trajectory", owners)

    def test_a_collision_is_refused(self):
        import dataclasses
        dup = dataclasses.replace(ia.PEOPLE_SPEC, expected_namespace={"person": "project"})
        with self.assertRaises(ia.IdentityAuditError):
            ia.namespace_owners((ia.PROJECT_SPEC, dup))


if __name__ == "__main__":
    unittest.main()


class BaselineGuardTests(unittest.TestCase):
    """The baseline says it only shrinks. Saying so is not a mechanism."""

    def test_a_stale_row_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            (root / "_system" / "state" / ia.ORPHAN_BASELINE_NAME).write_text(
                "project/long-gone | 2_areas/vanished.md\n", encoding="utf-8")
            result = ia.audit(root)
            self.assertEqual(result["orphans_stale"],
                             ["project/long-gone | 2_areas/vanished.md"])
            # Reported, never residue: a night must not stop for a stale line.
            self.assertTrue(result["clean"])

    def test_additions_are_detected_against_git(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            rc = subprocess.run(["git", "init", "-q"], cwd=tmp,
                                capture_output=True, text=True)
            if rc.returncode != 0:  # no git here — the guard is CI's, not the base's
                self.skipTest("git unavailable")
            for cmd in (["git", "config", "user.email", "t@t"],
                        ["git", "config", "user.name", "t"]):
                subprocess.run(cmd, cwd=tmp, capture_output=True)
            bl = root / "_system" / "state" / ia.ORPHAN_BASELINE_NAME
            # The repo root is the parent of the Minder Memory base, as in the real tree.
            zk = root / "zettelkasten"
            zk.mkdir(exist_ok=True)
            (zk / "_system" / "state").mkdir(parents=True, exist_ok=True)
            tracked = zk / "_system" / "state" / ia.ORPHAN_BASELINE_NAME
            tracked.write_text("project/one | a.md\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)
            subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp, capture_output=True)

            self.assertEqual(ia.baseline_additions(zk), [])
            tracked.write_text("project/one | a.md\nproject/sneaked | b.md\n",
                               encoding="utf-8")
            self.assertEqual(ia.baseline_additions(zk), ["project/sneaked | b.md"])
            # Removing a row is the sanctioned direction and reports nothing.
            tracked.write_text("", encoding="utf-8")
            self.assertEqual(ia.baseline_additions(zk), [])
            del bl

    def test_a_renamed_note_keeps_its_row(self):
        """The row follows the file: the same orphan under a new name is not
        a new orphan. Git's rename detection is the one source for the map."""
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            if subprocess.run(["git", "init", "-q"], cwd=tmp,
                              capture_output=True).returncode != 0:
                self.skipTest("git unavailable")
            for cmd in (["git", "config", "user.email", "t@t"],
                        ["git", "config", "user.name", "t"]):
                subprocess.run(cmd, cwd=tmp, capture_output=True)
            zk = root / "zettelkasten"
            (zk / "_system" / "state").mkdir(parents=True, exist_ok=True)
            note = zk / "old-name.md"
            note.write_text("---\nid: n\n---\n" + "body line\n" * 20, encoding="utf-8")
            tracked = zk / "_system" / "state" / ia.ORPHAN_BASELINE_NAME
            tracked.write_text("project/one | old-name.md\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)
            subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp, capture_output=True)
            subprocess.run(["git", "mv", "old-name.md", "new-name.md"], cwd=zk, capture_output=True)
            tracked.write_text("project/one | new-name.md\n", encoding="utf-8")
            self.assertEqual(ia.baseline_additions(zk), [])
            # a genuinely new row beside the carried one is still reported
            tracked.write_text("project/one | new-name.md\nproject/sneaked | b.md\n", encoding="utf-8")
            self.assertEqual(ia.baseline_additions(zk), ["project/sneaked | b.md"])

    def test_creating_the_baseline_is_not_an_addition(self):
        """The commit that first writes the file must not fail its own guard."""
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            if subprocess.run(["git", "init", "-q"], cwd=tmp,
                              capture_output=True).returncode != 0:
                self.skipTest("git unavailable")
            for cmd in (["git", "config", "user.email", "t@t"],
                        ["git", "config", "user.name", "t"]):
                subprocess.run(cmd, cwd=tmp, capture_output=True)
            zk = root / "zettelkasten"
            (zk / "_system" / "state").mkdir(parents=True, exist_ok=True)
            (zk / "seed.txt").write_text("x", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)
            subprocess.run(["git", "commit", "-qm", "before"], cwd=tmp, capture_output=True)
            (zk / "_system" / "state" / ia.ORPHAN_BASELINE_NAME).write_text(
                "project/one | a.md\n", encoding="utf-8")
            self.assertEqual(ia.baseline_additions(zk), [])

    def test_an_unreadable_ref_is_not_reported_as_clean(self):
        """«Could not compare» and «nothing added» must not print the same word."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _base(tmp)
            self.assertIsNone(ia.baseline_additions(root, ref="no-such-ref"))
