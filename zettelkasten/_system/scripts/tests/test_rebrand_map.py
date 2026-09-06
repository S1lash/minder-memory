"""The rename engine behind migration 032 — `scripts/migrations/_032_minder_memory_rebrand.py`.

The map is what turned the former product name into Minder Memory across the
authoring base, every clone and the sibling repositories. These tests pin the
properties a rename must have to be run unattended: an ordered map whose
composite rules beat the bare ones, protected source paths, code files that
keep their identifiers, file names and their references moving together,
`_sources/` and history untouched, idempotency, and a run that never
overwrites what already exists under the new name.
"""
# minder-memory-rebrand: keep-legacy-tokens — this module's inputs are the OLD spelling on purpose.

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"
sys.path.insert(0, str(_MIGRATIONS))

import _032_minder_memory_rebrand as rb  # noqa: E402

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", env=_ENV)


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return p


def _md5(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if ".git" in p.parts or "__pycache__" in p.parts:
            continue
        if p.is_file() and not p.is_symlink():
            out[p.relative_to(root).as_posix()] = hashlib.md5(p.read_bytes()).hexdigest()
    return out


class TokenMapTests(unittest.TestCase):
    CASES = {
        "Minder ZTN": "Minder Memory", "Minder/ZTN": "Minder Memory", "ZTN/Minder": "Minder Memory",
        "minder-ztn": "minder-memory",
        # A suffix after the skeleton name is somebody's OWN repository or folder;
        # renaming it in their notes would point at a path that does not exist.
        "minder-ztn-somebody": "minder-ztn-somebody",
        "~/repos/minder-ztn-ivanov/notes": "~/repos/minder-ztn-ivanov/notes",
        # ...except the engine's own retired project identifier, which is ours.
        "minder-ztn-platform": "minder-memory-platform",
        "/ztn:process": "/minder:mem:process", "ztn:role:add": "minder:mem:role:add",
        "name: ztn:process": "name: minder:mem:process",
        "ztn-process": "minder-mem-process", "ztn-role": "minder-mem-role", "ztn-roles-": "minder-mem-roles-",
        "/ztn-recap": "/minder:mem:recap", "`ztn-search`": "`minder:mem:search`",
        "ztn-hide-engine-paths": "minder-memory-hide-engine-paths",
        "ztn-engine-doctrine.md": "minder-memory-engine-doctrine.md",
        "ZTN_BASE": "MINDER_MEMORY_BASE", "{{MINDER_ZTN_BASE}}": "{{MINDER_MEMORY_BASE}}",
        "ZTN_ROLES_KEY": "MINDER_MEMORY_ROLES_KEY", "ZTN_SECRET_MASTER_KEY": "MINDER_MEMORY_SECRET_MASTER_KEY",
        "ZTN_SYMLINK_REEXEC": "MINDER_MEMORY_SYMLINK_REEXEC",
        # ...but a credential is the OWNER's name: a role declares it and the
        # store holds it under that spelling, and the store is never rewritten.
        # Renaming one side of that pair is what broke the role's preflight.
        "ZTN_TELEGRAM_TOKEN": "ZTN_TELEGRAM_TOKEN",
        "ZTN_OPENAI_API_KEY": "ZTN_OPENAI_API_KEY",
        "MINDER-ZTN BEGIN": "MINDER-MEMORY BEGIN",
        "urn:ztn:manifest-schema:v2": "urn:minder-memory:manifest-schema:v2",
        "ztn_constitution": "minder_memory_constitution", "clear_ztn_env": "clear_minder_memory_env",
        "minder_ztn_session": "minder_memory_session",
        "topic/ztn": "topic/minder-memory", "ztn-platform": "minder-memory-platform", "s3://minder-minder-memory-platform/": "s3://minder-memory-platform/",
        "20260519-meeting-ivan-petrov-team-ztn-demo": "20260519-meeting-ivan-petrov-team-minder-memory-demo",
        "only-the-ztn-memory-leaves": "only-the-minder-memory-leaves", "the ZTN memory": "the Minder Memory",
        "ZTN": "Minder Memory", "ЗТН": "Minder Memory", "«ЗТНа»": "«Minder Memory»", "my-ztn": "my-minder-memory",
        "«Майндер ZTN»": "«Minder Memory»", "«майндер ЗТН»": "«Minder Memory»",
        "ztn_search": "memory_search", "ztn.recall": "memory.recall",
        "john-doe-ztn.minder.host": "john-doe-memory.minder.host", "ztn.__USER__.minder.host": "memory.__USER__.minder.host",
        "zone=ztn_per_ip": "zone=memory_per_ip", "ztn-deploy-key": "minder-memory-deploy-key",
        "A0-ZTN": "A0-Minder-Memory", "ZTNVault": "MinderMemoryVault", "ztn-bridge": "minder-memory-bridge",
        "ztn-check-content": "minder-mem-check-content", "ztn-update-distribution-mechanism": "minder-memory-update-distribution-mechanism", "[[ztn-process-skill]]": "[[minder-mem-process-skill]]", "ztn-process": "minder-mem-process", "ZTNs": "Minder Memory bases", "minder-memory-*.yml": "minder-memory-*.yml", "rules/minder-memory-{a,b}.md": "rules/minder-memory-{a,b}.md", "skills/ztn-*/SKILL.md": "skills/minder-mem-*/SKILL.md",
        "ztn-{save,update}": "minder-mem-{save,update}",
    }

    def test_every_form_maps_to_its_current_spelling(self):
        for src, want in self.CASES.items():
            with self.subTest(src=src):
                self.assertEqual(rb.rebrand_text(src), want)

    def test_the_source_path_is_the_only_protected_span(self):
        line = "source: _sources/processed/plaud/2026-05-19T18:36:21Z/ztn-transcript.md — about ZTN\n"
        self.assertEqual(rb.rebrand_text(line),
                         "source: _sources/processed/plaud/2026-05-19T18:36:21Z/ztn-transcript.md — about Minder Memory\n")
        self.assertEqual(len(rb.PROTECTED_PATTERNS), 1)

    def test_idempotent(self):
        corpus = "\n".join(self.CASES) + "\n" + "\n".join(self.CASES.values())
        once = rb.rebrand_text(corpus)
        self.assertEqual(rb.rebrand_text(once), once)

    def test_no_doubled_product_name_survives(self):
        for text in ("Minder ZTN", "майндер ZTN", "Minder-ZTN", "ZTN memory"):
            self.assertNotIn("Minder Minder", rb.rebrand_text(text))
            self.assertNotIn("Memory Memory", rb.rebrand_text(text))

    def test_keep_markers(self):
        self.assertEqual(rb.rebrand_text("a ZTN line\nlegacy ZTN  # rebrand:keep\n"),
                         "a Minder Memory line\nlegacy ZTN  # rebrand:keep\n")
        whole = "ZTN everywhere\n# minder-memory-rebrand: keep-legacy-tokens\n"
        self.assertEqual(rb.rebrand_text(whole), whole)

    def test_code_mode_keeps_identifiers_and_moves_contracts(self):
        code = 'ztn: ZtnConfig\nuser.ztn.workdir\n"processor": "ztn:process"\n# the Minder ZTN base at minder-ztn-somebody /ztn:process ZTN_ROLES_KEY ztn_search\n'
        out = rb.rebrand_text(code, code=True)
        self.assertIn("ztn: ZtnConfig", out)
        self.assertIn("user.ztn.workdir", out)
        self.assertIn('"processor": "minder:mem:process"', out)
        self.assertIn("Minder Memory base at minder-ztn-somebody /minder:mem:process MINDER_MEMORY_ROLES_KEY memory_search", out)
        self.assertEqual(rb.rebrand_text("const ZTN = 1; x.ZTN; ZTN(); // ZTN base", code=True),
                         "const ZTN = 1; x.ZTN; ZTN(); // Minder Memory base")

    def test_an_owners_own_name_is_reported_as_residue_not_renamed(self):
        """Left alone AND named — silence would read as «nothing to see»."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "note.md",
                   "My clone lives in ~/repos/minder-ztn-ivanov and I run /ztn:process.\n")
            report = rb.run(root, dry_run=False)
            self.assertEqual(
                (root / "note.md").read_text(encoding="utf-8"),
                "My clone lives in ~/repos/minder-ztn-ivanov and I run /minder:mem:process.\n")
            payload = json.loads(report.to_json())
            self.assertEqual(payload["own_name"], {"note.md": 1})
            self.assertNotIn("note.md", payload["residue"],
                             "an own-name hit is explained, not unexplained residue")
            self.assertIn("name your own repository, folder or credential",
                          rb.render_inventory(report))

    def test_an_owners_credential_name_is_reported_as_kept_not_renamed(self):
        """Left alone AND named, on the same axis as their folder names."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "role.md", "secrets:\n  - ZTN_TELEGRAM_TOKEN\nRun /ztn:process.\n")
            report = rb.run(root, dry_run=False)
            self.assertEqual((root / "role.md").read_text(encoding="utf-8"),
                             "secrets:\n  - ZTN_TELEGRAM_TOKEN\nRun /minder:mem:process.\n")
            payload = json.loads(report.to_json())
            self.assertEqual(payload["own_name"], {"role.md": 1})
            self.assertNotIn("role.md", payload["residue"])
            self.assertIn("name your own repository, folder or credential",
                          rb.render_inventory(report))

    def test_every_code_safe_rule_names_a_real_map_entry(self):
        sources = {pat for pat, _ in rb.TOKEN_MAP}
        for rule in rb._CODE_SAFE_RULES:
            self.assertIn(rule, sources, rule)


class PathMapTests(unittest.TestCase):
    def test_paths(self):
        cases = {
            "integrations/claude-code/commands/ztn-recap.md": "integrations/claude-code/commands/minder/mem/recap.md",
            "integrations/claude-code/skills/ztn-process/SKILL.md": "integrations/claude-code/skills/minder-mem-process/SKILL.md",
            ".claude/skills/ztn-lint": ".claude/skills/minder-mem-lint",
            "zettelkasten/minder-ztn.md": "zettelkasten/minder-memory.md",
            "zettelkasten/.obsidian/snippets/ztn-note-types.css": "zettelkasten/.obsidian/snippets/minder-memory-note-types.css",
            "docs/plain.md": "docs/plain.md",
        }
        for src, want in cases.items():
            with self.subTest(src=src):
                self.assertEqual(rb.rebrand_path(src), want)

    def test_a_code_module_named_after_a_bare_identifier_keeps_its_name(self):
        self.assertEqual(rb.rebrand_path("src/ztn/ztn-renderer.ts", code=True), "src/ztn/ztn-renderer.ts")
        self.assertEqual(rb.rebrand_path("src/ztn/ztn-renderer.ts"), "src/minder-memory/minder-memory-renderer.ts")


class RunTests(unittest.TestCase):
    def _tree(self, root: Path) -> None:
        _write(root, "zettelkasten/1_projects/20260519-reflection-minder-ztn-origin-story.md",
               "---\nid: 20260519-reflection-minder-ztn-origin-story\ntags:\n  - topic/ztn\n---\n# Minder ZTN\nRun /ztn:process. «Майндер ZTN — это папка.» ЗТНа.\n")
        _write(root, "zettelkasten/2_areas/link.md",
               "See [[20260519-reflection-minder-ztn-origin-story]], [[20260519-reflection-minder-ztn-origin-story|label]] and [[20260519-reflection-minder-ztn-origin-story#h]].\n")
        _write(root, "zettelkasten/_sources/inbox/raw.md", "raw ZTN transcript\n")
        _write(root, "zettelkasten/_system/state/log_process.md", "ran /ztn:process\n")
        _write(root, "zettelkasten/_system/state/principle-candidates.jsonl", '{"captured_by": "ztn:capture-candidate"}\n')
        _write(root, "zettelkasten/_system/state/batches/x.json", '{"processor": "ztn:process"}\n')
        _write(root, "docs/CHANGELOG.md", "## 0.1 — /ztn:process\n")
        _write(root, "zettelkasten/5_meta/DECISION_LOG.md", "ADR-001 ZTN\n")
        _write(root, "scripts/migrations/031-x.sh", "# ZTN wiring\n")
        _write(root, "zettelkasten/_records/observations/2026-05-19-cyr.md", "Обсуждали ZTN и Minder ZTN.\n")
        (root / "bin.md").write_bytes(b"\xff\xfe ztn \x00")

    def test_full_run_moves_everything_but_sources_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            report = rb.run(root, dry_run=False)
            new = root / "zettelkasten/1_projects/20260519-reflection-minder-memory-origin-story.md"
            self.assertTrue(new.exists())
            body = new.read_text(encoding="utf-8")
            self.assertIn("id: 20260519-reflection-minder-memory-origin-story", body)
            self.assertIn("topic/minder-memory", body)
            self.assertIn("«Minder Memory — это папка.» Minder Memory.", body)
            self.assertEqual((root / "zettelkasten/2_areas/link.md").read_text(encoding="utf-8"),
                             "See [[20260519-reflection-minder-memory-origin-story]], [[20260519-reflection-minder-memory-origin-story|label]] and [[20260519-reflection-minder-memory-origin-story#h]].\n")
            self.assertEqual((root / "zettelkasten/_sources/inbox/raw.md").read_text(encoding="utf-8"), "raw ZTN transcript\n")
            self.assertEqual((root / "zettelkasten/_system/state/log_process.md").read_text(encoding="utf-8"), "ran /minder:mem:process\n")
            self.assertEqual((root / "zettelkasten/_system/state/principle-candidates.jsonl").read_text(encoding="utf-8"),
                             '{"captured_by": "minder:mem:capture-candidate"}\n')
            self.assertEqual((root / "zettelkasten/_system/state/batches/x.json").read_text(encoding="utf-8"),
                             '{"processor": "minder:mem:process"}\n')
            self.assertEqual((root / "docs/CHANGELOG.md").read_text(encoding="utf-8"), "## 0.1 — /ztn:process\n")
            self.assertEqual((root / "zettelkasten/5_meta/DECISION_LOG.md").read_text(encoding="utf-8"), "ADR-001 ZTN\n")
            self.assertEqual((root / "scripts/migrations/031-x.sh").read_text(encoding="utf-8"), "# Minder Memory wiring\n")
            self.assertEqual((root / "zettelkasten/_records/observations/2026-05-19-cyr.md").read_text(encoding="utf-8"),
                             "Обсуждали Minder Memory и Minder Memory.\n")
            self.assertIn("bin.md", report.skipped_binary)
            self.assertEqual(report.residue, {})
            # second run: nothing left to do
            before = _md5(root)
            second = rb.run(root, dry_run=False)
            self.assertEqual(second.changes, [])
            self.assertEqual(_md5(root), before)

    def test_dry_run_changes_nothing_and_reports_the_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            before = _md5(root)
            dry = rb.run(root, dry_run=True)
            self.assertEqual(_md5(root), before)
            wet = rb.run(root, dry_run=False)
            self.assertEqual(sorted(c.path for c in dry.changes), sorted(c.path for c in wet.changes))

    def test_git_repo_renames_and_relinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "integrations/claude-code/skills/ztn-lint/SKILL.md", "---\nname: ztn:lint\n---\n")
            (root / ".claude/skills").mkdir(parents=True)
            os.symlink("../../integrations/claude-code/skills/ztn-lint", root / ".claude/skills/ztn-lint")
            _git(root, "init", "-q")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "seed")
            rb.run(root, dry_run=False)
            self.assertTrue((root / "integrations/claude-code/skills/minder-mem-lint/SKILL.md").exists())
            self.assertFalse((root / "integrations/claude-code/skills/ztn-lint").exists())
            link = root / ".claude/skills/minder-mem-lint"
            self.assertTrue(link.is_symlink())
            self.assertEqual(os.readlink(link), "../../integrations/claude-code/skills/minder-mem-lint")
            self.assertFalse((root / ".claude/skills/ztn-lint").is_symlink())
            _git(root, "add", "-A")
            status = _git(root, "status", "--porcelain").stdout
            self.assertNotIn("ztn-lint/SKILL.md", [l[3:] for l in status.splitlines() if l.startswith("A")])

    def test_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "zettelkasten/minder-ztn.md", "# old dashboard\nRun /ztn:process\n")
            _write(root, "zettelkasten/minder-memory.md", "# the owner's CURRENT dashboard\n")
            report = rb.run(root, dry_run=False)
            self.assertEqual((root / "zettelkasten/minder-memory.md").read_text(encoding="utf-8"),
                             "# the owner's CURRENT dashboard\n")
            self.assertTrue((root / "zettelkasten/minder-ztn.md").exists())
            self.assertIn("zettelkasten/minder-ztn.md", report.conflicts)
            self.assertIn("/minder:mem:process", (root / "zettelkasten/minder-ztn.md").read_text(encoding="utf-8"))
            self.assertIn("merge by hand", rb.render_inventory(report))

    def test_skip_dirty_protects_both_sides_of_a_staged_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "notes/ztn-thing.md", "ZTN\n")
            _write(root, "notes/other.md", "ZTN\n")
            _git(root, "init", "-q")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "seed")
            _git(root, "mv", "notes/ztn-thing.md", "notes/moved-ztn-thing.md")
            dirty = rb._git_dirty(root)
            self.assertIn("notes/moved-ztn-thing.md", dirty)
            self.assertIn("notes/ztn-thing.md", dirty)
            report = rb.run(root, dry_run=False, skip_dirty=True)
            self.assertIn("notes/moved-ztn-thing.md", report.skipped_dirty)
            self.assertEqual((root / "notes/moved-ztn-thing.md").read_text(encoding="utf-8"), "ZTN\n")
            self.assertEqual((root / "notes/other.md").read_text(encoding="utf-8"), "Minder Memory\n")

    def test_exclude_prefix_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "keep/ztn.md", "ZTN\n")
            _write(root, "go/ztn.md", "ZTN\n")
            inv = root / "inv.md"
            r = subprocess.run(["python3", str(_MIGRATIONS / "_032_minder_memory_rebrand.py"), "--root", str(root),
                                "--exclude", "keep/", "--inventory", str(inv), "--json"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(r.stdout)
            self.assertEqual(data["changed"], 1)
            self.assertEqual(data["renamed"], 1)
            self.assertEqual((root / "keep/ztn.md").read_text(encoding="utf-8"), "ZTN\n")
            self.assertTrue((root / "go/minder-memory.md").exists())
            self.assertIn("go/ztn.md", inv.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
