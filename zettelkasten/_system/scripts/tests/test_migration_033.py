"""Integration tests for migration `033-own-names-after-the-rename.sh`.

Why this migration needs a suite that EXECUTES it. Its whole output is a
clarification — a message to the owner — and a message that is wrong, missing
or repeated nightly is indistinguishable from one that is right until somebody
reads the queue. Worse, `heal` migrations that succeed are recorded `applied`
and never run again, so a run that raised nothing on a damaged clone would
close the case silently, on every friend's machine at once.

Safety contract: every repository lives in a `TemporaryDirectory`, there is no
network, and the migration is asserted never to rewrite the damaged file.
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
_SCRIPTS = _REPO_ROOT / "scripts"

MIGRATION = "033-own-names-after-the-rename.sh"
HELPER = "_033_own_names.py"
CLARIFICATIONS = "zettelkasten/_system/state/CLARIFICATIONS.md"
SOUL = "zettelkasten/_system/SOUL.md"

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", env=_ENV)


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return p


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class Migration033Tests(unittest.TestCase):
    # Literal, not the module constant: the coverage gate reads this out of the
    # syntax tree and only recognises a string constant.
    NAME = "033-own-names-after-the-rename.sh"

    OWN = "My base lives in ~/projects/minder-ztn-ivanov/zettelkasten.\n"
    DAMAGED = "My base lives in ~/projects/minder-memory-ivanov/zettelkasten.\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "scripts" / "migrations").mkdir(parents=True)
        shutil.copytree(_SCRIPTS / "lib", self.root / "scripts" / "lib")
        shutil.copy(_SCRIPTS / "check_update.py", self.root / "scripts" / "check_update.py")
        for name in (MIGRATION, HELPER):
            src = _MIGRATIONS / name
            if not src.is_file():
                self.fail(f"{name} does not exist yet at {src} — write the migration")
            shutil.copy(src, self.root / "scripts" / "migrations" / name)
        self.mig = self.root / "scripts" / "migrations" / MIGRATION

    def tearDown(self):
        self._tmp.cleanup()

    # -- fixtures ---------------------------------------------------------- #

    def _base(self, *, damaged: bool) -> None:
        """A clone with a before-state and an after-state, as an update leaves it."""
        _write(self.root, SOUL, self.OWN)
        _write(self.root, CLARIFICATIONS,
               "# Clarifications Needed\n\n---\n\n## Open Items\n\n## an earlier item\n")
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "before the rename migration ran")

        if damaged:
            _write(self.root, SOUL, self.DAMAGED)
        _write(self.root, ".engine-migrations.jsonl",
               '{"kind":"heal","name":"032-minder-memory-owner-surfaces.sh","outcome":"applied",'
               '"rc":0,"ts":"2026-01-01T00:00:00Z"}\n')
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "the update that ran the rename")

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.mig), *args], capture_output=True, text=True,
                              encoding="utf-8", env=_ENV, cwd=str(self.root))

    def _queue(self) -> str:
        return (self.root / CLARIFICATIONS).read_text(encoding="utf-8")

    # -- the damaged clone -------------------------------------------------- #

    def test_a_damaged_name_becomes_one_item_carrying_both_texts(self):
        self._base(damaged=True)
        before = _md5(self.root / SOUL)
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stderr)
        queue = self._queue()
        self.assertIn("process-compatibility", queue)
        self.assertIn("**Source:** migration 033-own-names-after-the-rename.sh", queue)
        self.assertIn("minder-memory-ivanov", queue, "the current text must be quoted")
        self.assertIn("minder-ztn-ivanov", queue, "the pre-rename text must be quoted")
        self.assertIn("restore it if the directory is still named that way", queue)
        self.assertIn(f"`{SOUL}:1`", queue)
        self.assertEqual(_md5(self.root / SOUL), before,
                         "the migration must never rewrite the damaged file")

    def test_the_item_lands_under_open_items_and_keeps_what_was_there(self):
        self._base(damaged=True)
        self._run()
        queue = self._queue()
        self.assertIn("## Open Items", queue)
        self.assertLess(queue.index("## Open Items"), queue.index("033 "))
        self.assertIn("## an earlier item", queue, "an existing item must survive")

    def test_a_second_run_appends_nothing(self):
        self._base(damaged=True)
        self.assertEqual(self._run().returncode, 0)
        first = self._queue()
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._queue(), first)
        self.assertIn("already in the clarifications queue", res.stdout)

    # -- the clean clone ---------------------------------------------------- #

    def test_a_clone_whose_own_name_survived_gets_nothing(self):
        self._base(damaged=False)
        first = self._queue()
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._queue(), first)

    def test_no_before_state_says_so_rather_than_reporting_all_clear(self):
        _write(self.root, SOUL, self.DAMAGED)
        _write(self.root, CLARIFICATIONS, "# Clarifications Needed\n\n## Open Items\n")
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "a clone whose ledger was never committed")
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("no state from", res.stdout)

    # -- contract ----------------------------------------------------------- #

    def test_a_tree_that_is_not_a_base_is_refused_and_retried(self):
        self._base(damaged=True)
        shutil.rmtree(self.root / "zettelkasten" / "_system")
        res = self._run()
        self.assertEqual(res.returncode, 1)
        self.assertIn("not a base", res.stderr)

    def test_dry_run_changes_nothing(self):
        self._base(damaged=True)
        first = self._queue()
        res = self._run("--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._queue(), first)

    def test_declared_kind_is_heal(self):
        head = self.mig.read_text(encoding="utf-8").splitlines()[:5]
        self.assertTrue(any("migration-kind: heal" in line for line in head),
                        f"no `# migration-kind: heal` header in:\n{head}")


if __name__ == "__main__":
    unittest.main()
