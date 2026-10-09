"""Integration tests for migration `037-converge-clones-and-backups.sh`.

The migration re-runs the installer once more, so a clone that already ran 036
also gets the installer's convergence across clones (the engine's retired links
into any clone removed) and its backup retention (one CLAUDE.md backup kept).
It is a `heal`: when the installer fails, the wiring 036 left is still whole,
so the update continues and the next one tries again.

Safety contract: every repository and harness home lives in a
`TemporaryDirectory`, and `CLAUDE_HOME` always points there.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"

MIGRATION = "037-converge-clones-and-backups.sh"
INSTALLER = "integrations/claude-code/install.sh"

STUB_OK = """#!/usr/bin/env bash
set -euo pipefail
: "${CLAUDE_HOME:?CLAUDE_HOME must reach install.sh}"
mkdir -p "$CLAUDE_HOME"
pwd > "$CLAUDE_HOME/.install-ran"
"""
STUB_FAIL = """#!/usr/bin/env bash
echo "[install] stub failing" >&2
exit 3
"""


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return p


class Migration037Tests(unittest.TestCase):
    # Literal, not the module constant: the coverage gate reads this out of the
    # syntax tree and only recognises a string constant.
    NAME = "037-converge-clones-and-backups.sh"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.root = tmp / "repo"
        self.home = tmp / "home"
        self.home.mkdir()
        shutil.copy(_MIGRATIONS / MIGRATION, _write(self.root, f"scripts/migrations/{MIGRATION}", ""))
        self.mig = self.root / "scripts" / "migrations" / MIGRATION

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.mig)], capture_output=True, text=True,
                              encoding="utf-8", cwd=str(self.root),
                              env={**os.environ, "CLAUDE_HOME": str(self.home)})

    def test_declared_kind_is_heal(self):
        second = self.mig.read_text(encoding="utf-8").splitlines()[1]
        self.assertEqual(second, "# migration-kind: heal")

    def test_runs_the_installer_from_the_repo_root_with_the_home_inherited(self):
        _write(self.root, INSTALLER, STUB_OK)
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        ran = self.home / ".install-ran"
        self.assertTrue(ran.is_file(), "install.sh did not run against CLAUDE_HOME")
        self.assertEqual(Path(ran.read_text(encoding="utf-8").strip()).resolve(), self.root.resolve())

    def test_a_failing_installer_fails_the_migration_and_names_the_command(self):
        _write(self.root, INSTALLER, STUB_FAIL)
        res = self._run()
        self.assertNotEqual(res.returncode, 0, "a non-zero exit is what brings the retry back")
        self.assertIn("bash integrations/claude-code/install.sh", res.stdout + res.stderr)

    def test_a_clone_without_the_integration_has_nothing_to_wire(self):
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse((self.home / ".install-ran").exists())


class Migration037EndToEndTests(unittest.TestCase):
    """The real installer, on a home another clone wired and earlier runs backed up."""

    NAME = "037-converge-clones-and-backups.sh"

    def test_another_clones_links_go_backups_shrink_and_a_second_run_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, home, other = Path(tmp) / "repo", Path(tmp) / "home", Path(tmp) / "other-clone"
            for rel in (INSTALLER, f"scripts/migrations/{MIGRATION}"):
                shutil.copy(_REPO_ROOT / rel, _write(root, rel, ""))
            shutil.copytree(_REPO_ROOT / "scripts" / "lib", root / "scripts" / "lib",
                            ignore=shutil.ignore_patterns("__pycache__"))
            _write(root, "integrations/claude-code/rules/minder-memory.md", "base {{MINDER_MEMORY_BASE}}\n")
            _write(root, "integrations/claude-code/commands/minder/mem/recap.md", "cmd\n")
            (root / "integrations/claude-code/skills").mkdir(parents=True)
            sources = {
                "constitution-capture.md": "zettelkasten/_system/docs/constitution-capture.md",
                "communication-baseline.md": "zettelkasten/_system/docs/communication-baseline.md",
                "advisory-baseline.md": "zettelkasten/_system/docs/advisory-baseline.md",
                "constitution-core.md": "zettelkasten/_system/views/constitution-core.md",
                "minder-memory-engine-doctrine.md": "zettelkasten/_system/docs/ENGINE_DOCTRINE.md",
            }
            for rel in sources.values():
                _write(root, rel, "x\n")
                _write(other, rel, "other\n")
            _write(other, ".engine-manifest.yml", "engine: []\n")
            _write(other, INSTALLER, "#!/bin/bash\n")
            rules = home / "rules"
            rules.mkdir(parents=True)
            for name, rel in sources.items():
                os.symlink(other / rel, rules / name)
            _write(home, "rules/mine.md", "mine\n")
            for stamp in ("20200101-000000", "20200102-000000"):
                _write(home, f".minder-memory-backup-{stamp}/CLAUDE.md.before-refresh", "old\n")
            _write(home, "CLAUDE.md",
                   "<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->\n"
                   "- @~/.claude/rules/minder-memory.md\n<!-- MINDER-MEMORY END -->\n")
            env = {**os.environ, "CLAUDE_HOME": str(home)}
            mig = root / "scripts" / "migrations" / MIGRATION
            for _ in range(2):
                res = subprocess.run(["bash", str(mig)], capture_output=True, text=True,
                                     encoding="utf-8", cwd=str(root), env=env)
                self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertEqual(sorted(p.name for p in rules.iterdir()), ["mine.md"])
                backups = [p for p in home.iterdir() if p.name.startswith(".minder-memory-backup-")]
                self.assertEqual(len(backups), 1, backups)
                self.assertEqual((home / "CLAUDE.md").read_text(encoding="utf-8").count("@~/.claude/minder-memory/"), 5)


if __name__ == "__main__":
    unittest.main()
