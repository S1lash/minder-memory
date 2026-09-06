"""Migration 032 — every file in a friend's clone says Minder Memory.

The migration runs the rename engine over the whole clone. These tests pin
what a friend must be able to rely on: their dashboard keeps its edits under
the new name, their notes and state say the current name, `_sources/` is
untouched, a base without `_system/` is refused (heal → retried), and a second
run is a no-op.
"""
# minder-memory-rebrand: keep-legacy-tokens — this module's inputs are the OLD spelling on purpose.

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"
_LIB = _REPO_ROOT / "scripts" / "lib"
MIGRATION = "032-minder-memory-owner-surfaces.sh"
HELPER = "_032_minder_memory_rebrand.py"
_OWNER_EDIT = "my custom dashboard line"


def _run(mig: Path, *args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(mig), *args], capture_output=True, text=True, encoding="utf-8",
                          env=env or dict(os.environ), cwd=str(cwd) if cwd else None)


def _tree_md5(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        parts = p.relative_to(root).parts
        if ".git" in parts or "__pycache__" in parts:
            continue
        if p.is_file() and not p.is_symlink():
            out["/".join(parts)] = hashlib.md5(p.read_bytes()).hexdigest()
    return out


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return p


class Migration032Tests(unittest.TestCase):
    NAME = "032-minder-memory-owner-surfaces.sh"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "scripts" / "migrations").mkdir(parents=True)
        shutil.copytree(_LIB, self.root / "scripts" / "lib")
        shutil.copy(_MIGRATIONS / HELPER, self.root / "scripts" / "migrations" / HELPER)
        shutil.copy(_MIGRATIONS / MIGRATION, self.root / "scripts" / "migrations" / MIGRATION)
        self.mig = self.root / "scripts" / "migrations" / MIGRATION

    def tearDown(self):
        self._tmp.cleanup()

    def _clone(self) -> None:
        (self.root / "zettelkasten" / "_system").mkdir(parents=True, exist_ok=True)
        _write(self.root, "zettelkasten/minder-ztn.md", f"# Minder ZTN\n\nRun /ztn:process daily.\n\n{_OWNER_EDIT}\n")
        _write(self.root, "zettelkasten/_system/SOUL.md", "I use Minder ZTN. Nightly I run /ztn:process.\n")
        _write(self.root, "zettelkasten/.obsidian/appearance.json", '{"enabledCssSnippets":["ztn-hide-engine-paths","ztn-note-types"]}\n')
        _write(self.root, "zettelkasten/.obsidian/snippets/ztn-note-types.css", "/* ZTN */\n")
        _write(self.root, "zettelkasten/_records/observations/2026-05-19-demo.md", "Talked about ZTN with the team.\n")
        _write(self.root, "zettelkasten/_sources/inbox/raw.md", "raw ZTN transcript\n")
        _write(self.root, "zettelkasten/_system/state/log_process.md", "ran /ztn:process\n")
        _write(self.root, "zettelkasten/_system/state/agent-lens-runs.jsonl", '{"skill":"ztn:agent-lens"}\n')

    def test_declared_kind_is_heal(self):
        head = self.mig.read_text(encoding="utf-8").splitlines()[:5]
        self.assertTrue(any("migration-kind: heal" in line for line in head))

    def test_refuses_a_base_without_system(self):
        self._clone()
        shutil.rmtree(self.root / "zettelkasten" / "_system")
        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 1)
        self.assertIn("no _system/", res.stderr)

    def test_renames_the_clone_and_keeps_the_owner_edit(self):
        self._clone()
        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        dash = self.root / "zettelkasten/minder-memory.md"
        self.assertTrue(dash.exists())
        self.assertIn(_OWNER_EDIT, dash.read_text(encoding="utf-8"))
        self.assertIn("/minder:mem:process", dash.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "zettelkasten/minder-ztn.md").exists())
        self.assertEqual((self.root / "zettelkasten/_system/SOUL.md").read_text(encoding="utf-8"),
                         "I use Minder Memory. Nightly I run /minder:mem:process.\n")
        self.assertEqual((self.root / "zettelkasten/.obsidian/appearance.json").read_text(encoding="utf-8"),
                         '{"enabledCssSnippets":["minder-memory-hide-engine-paths","minder-memory-note-types"]}\n')
        self.assertTrue((self.root / "zettelkasten/.obsidian/snippets/minder-memory-note-types.css").exists())
        self.assertEqual((self.root / "zettelkasten/_records/observations/2026-05-19-demo.md").read_text(encoding="utf-8"),
                         "Talked about Minder Memory with the team.\n")
        self.assertEqual((self.root / "zettelkasten/_system/state/log_process.md").read_text(encoding="utf-8"),
                         "ran /minder:mem:process\n")
        self.assertEqual((self.root / "zettelkasten/_system/state/agent-lens-runs.jsonl").read_text(encoding="utf-8"),
                         '{"skill":"minder:mem:agent-lens"}\n')
        self.assertEqual((self.root / "zettelkasten/_sources/inbox/raw.md").read_text(encoding="utf-8"),
                         "raw ZTN transcript\n")

    def test_unsaved_owner_files_are_rewritten_and_the_count_is_reported(self):
        """The rename applies to the clone whole — including work in flight.

        That is the contract, and it is fine: git holds the previous text. What
        was missing is the SAYING of it. An owner who left a note open finds it
        renamed under them and no line anywhere telling them where the old text
        went, which reads as data loss.
        """
        self._clone()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "seed")):
            subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, env=env)
        # One tracked note edited but not committed, one never saved at all.
        _write(self.root, "zettelkasten/_system/SOUL.md",
               "I use Minder ZTN and I am mid-edit.\n")
        _write(self.root, "zettelkasten/_records/observations/2026-06-01-open.md",
               "An unsaved ZTN note.\n")

        res = _run(self.mig, env=env, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.root / "zettelkasten/_system/SOUL.md").read_text(encoding="utf-8"),
                         "I use Minder Memory and I am mid-edit.\n")
        self.assertIn("1 unsaved files were renamed in place — their previous text is in git "
                      "under the old name", res.stdout)
        self.assertIn("never saved to git", res.stdout)

    def test_second_run_is_a_no_op(self):
        self._clone()
        self.assertEqual(_run(self.mig, cwd=self.root).returncode, 0)
        before = _tree_md5(self.root)
        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(_tree_md5(self.root), before)


if __name__ == "__main__":
    unittest.main()
