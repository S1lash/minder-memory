"""Pins for the defects the adversarial review of the rebrand found.

Each test here reproduces a finding first reported by the second-model review
of the finished work, so that the fix cannot quietly regress:

- the manifest schema names one processor spelling and every fixture
  validates; the shallow validator rejects a manifest missing its sections;
- the installer refreshes its managed block in place and collapses a
  duplicate, never appends a second block;
- migration 031's convergence follows the sync's remote and branch.
"""
# minder-memory-rebrand: keep-legacy-tokens — the inputs are the OLD spelling on purpose.

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS_DIR = _THIS.parents[1]
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"
sys.path.insert(0, str(_MIGRATIONS))
sys.path.insert(0, str(_SCRIPTS_DIR))


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


class ManifestSchemaTests(unittest.TestCase):
    SCHEMA = _REPO_ROOT / "zettelkasten/_system/docs/manifest-schema/v2.json"
    FIXTURES = _REPO_ROOT / "zettelkasten/_system/docs/manifest-schema/fixtures"

    def test_every_fixture_validates(self):
        try:
            from jsonschema import Draft202012Validator
        except ModuleNotFoundError:
            self.skipTest("jsonschema not installed")
        schema = json.loads(self.SCHEMA.read_text(encoding="utf-8"))
        v = Draft202012Validator(schema)
        for path in sorted(glob.glob(str(self.FIXTURES / "*.json"))):
            errs = list(v.iter_errors(json.loads(Path(path).read_text(encoding="utf-8"))))
            self.assertEqual(errs, [], f"{Path(path).name}: {[e.message for e in errs][:3]}")

    def test_schema_names_one_spelling(self):
        schema = json.loads(self.SCHEMA.read_text(encoding="utf-8"))
        enum = schema["$defs"]["processor"]["enum"]
        self.assertEqual(sorted(enum), sorted(f"minder:mem:{n}" for n in ("process", "maintain", "lint", "agent-lens")))

    def test_shallow_validator_rejects_a_manifest_missing_its_sections(self):
        import emit_batch_manifest as e
        bad = {"batch_id": "20260902-000000", "timestamp": "2026-09-02T00:00:00Z",
               "format_version": "2.3", "processor": "minder:mem:process", "stats": {}}
        with self.assertRaises(e.ManifestValidationError):
            e.validate_manifest(bad)


class InstallerMarkersTests(unittest.TestCase):
    """install.sh refreshes its block in place and collapses a duplicate."""

    def _fake_repo(self, tmp: Path) -> Path:
        repo = tmp / "repo"
        (repo / "integrations/claude-code/rules").mkdir(parents=True)
        (repo / "integrations/claude-code/commands/minder/mem").mkdir(parents=True)
        (repo / "integrations/claude-code/skills").mkdir(parents=True)
        (repo / "zettelkasten/_system/docs").mkdir(parents=True)
        (repo / "zettelkasten/_system/views").mkdir(parents=True)
        shutil.copy(_REPO_ROOT / "integrations/claude-code/install.sh", repo / "integrations/claude-code/install.sh")
        _write(repo, "integrations/claude-code/rules/minder-memory.md", "base {{MINDER_MEMORY_BASE}}\n")
        _write(repo, "integrations/claude-code/commands/minder/mem/recap.md", "cmd\n")
        for name in ("constitution-capture.md", "communication-baseline.md", "advisory-baseline.md", "ENGINE_DOCTRINE.md"):
            _write(repo, f"zettelkasten/_system/docs/{name}", "x\n")
        _write(repo, "zettelkasten/_system/views/constitution-core.md", "x\n")
        return repo

    def _run(self, repo: Path, home: Path) -> subprocess.CompletedProcess:
        env = {**os.environ, "CLAUDE_HOME": str(home)}
        return subprocess.run(["bash", str(repo / "integrations/claude-code/install.sh")], cwd=str(repo),  # portability-ok: invoked through bash, never by the executable bit
                              capture_output=True, text=True, encoding="utf-8", env=env)

    def test_block_is_refreshed_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fake_repo(Path(tmp))
            home = Path(tmp) / "home"
            home.mkdir()
            (home / "CLAUDE.md").write_text(textwrap.dedent("""\
                # mine
                - above

                <!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->
                - @~/.claude/rules/stale.md
                <!-- MINDER-MEMORY END -->

                - below
                """), encoding="utf-8")
            r = self._run(repo, home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = (home / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(md.count("BEGIN — managed by install.sh"), 1, md)
            self.assertIn("@~/.claude/rules/minder-memory.md", md)
            self.assertNotIn("stale.md", md)
            self.assertLess(md.index("- above"), md.index("MINDER-MEMORY BEGIN"))
            self.assertLess(md.index("MINDER-MEMORY END"), md.index("- below"))

    def test_two_blocks_collapse_to_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fake_repo(Path(tmp))
            home = Path(tmp) / "home"
            home.mkdir()
            (home / "CLAUDE.md").write_text(textwrap.dedent("""\
                <!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->
                old
                <!-- MINDER-MEMORY END -->

                <!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->
                newer
                <!-- MINDER-MEMORY END -->
                """), encoding="utf-8")
            r = self._run(repo, home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = (home / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(md.count("BEGIN — managed by install.sh"), 1, md)
            self.assertNotIn("old", md.splitlines())
            self.assertNotIn("newer", md.splitlines())


class ConvergenceFollowsTheSyncTests(unittest.TestCase):
    def test_non_main_branch_and_non_upstream_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            up = root / "up"
            up.mkdir()
            _write(up, "new-thing.md", "shipped on release\n")
            _write(up, ".engine-manifest.yml", "version: 1\nengine:\n  - new-thing.md\n")
            _git(up, "init", "-q", "-b", "release")
            _git(up, "add", "-A")
            _git(up, "commit", "-q", "-m", "up")
            clone = root / "clone"
            clone.mkdir()
            _write(clone, ".engine-manifest.yml", "version: 1\nengine:\n  - new-thing.md\n")
            shutil.copytree(_REPO_ROOT / "scripts" / "lib", clone / "scripts" / "lib")
            (clone / "scripts" / "migrations").mkdir()
            shutil.copy(_MIGRATIONS / "_031_harness_wiring.py", clone / "scripts" / "migrations" / "_031_harness_wiring.py")
            _git(clone, "init", "-q", "-b", "main")
            _git(clone, "add", "-A")
            _git(clone, "commit", "-q", "-m", "clone")
            _git(clone, "remote", "add", "skeleton", str(up))
            _git(clone, "fetch", "-q", "skeleton", "release")
            env = {**os.environ, "ENGINE_SYNC_REMOTE": "skeleton", "ENGINE_SYNC_BRANCH": "release"}
            code = ("import sys, json; sys.path.insert(0, 'scripts/migrations'); "
                    "import _031_harness_wiring as m; from pathlib import Path; "
                    "print(json.dumps(m.converge_engine_paths(Path('.').resolve(), dry_run=False)))")
            r = subprocess.run(["python3", "-c", code], cwd=str(clone), capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            res = json.loads(r.stdout)
            self.assertEqual(res["remote"], "skeleton")
            self.assertEqual(res["branch"], "release")
            self.assertEqual(res["fetched"], ["new-thing.md"])
            self.assertEqual((clone / "new-thing.md").read_text(encoding="utf-8"), "shipped on release\n")


if __name__ == "__main__":
    unittest.main()
