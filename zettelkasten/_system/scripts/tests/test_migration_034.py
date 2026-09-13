"""Integration tests for migration `034-register-resolve-clarifications-source.sh`.

The migration asks the agent running `/minder:mem:update` to register the
`resolve-clarifications` source, and keeps asking on every update until the
registry carries its row. It never writes the registry itself — a row is the
owner's data, added through `/minder:mem:source-add`.

Safety contract: every repository lives in a `TemporaryDirectory`, and the
registry fixture is written here, never read from the authoring tree.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"

MIGRATION = "034-register-resolve-clarifications-source.sh"
SOURCES = "zettelkasten/_system/registries/SOURCES.md"
COMMAND = "/minder:mem:source-add --id resolve-clarifications --layout flat-md --description"

HEADER = "| ID | Inbox Path | Family | Layout | Default Domain | Skip Subdirs | Description | Status |\n|---|---|---|---|---|---|---|---|\n"
NOTES_ROW = "| notes | `_sources/inbox/notes/` | transcript | flat-md | auto | — | Plain notes. | active |\n"
OWN_ROW = "| resolve-clarifications | `_sources/inbox/resolve-clarifications/` | transcript | flat-md | auto | — | Approved knowledge. | {status} |\n"


def _registry(active: str = "", deprecated: str = "") -> str:
    return ("# Sources Registry\n\n## Active Sources\n\n" + HEADER + NOTES_ROW + active
            + "\n## Deprecated Sources\n\n" + HEADER + deprecated)


class Migration034Tests(unittest.TestCase):
    # Literal, not the module constant: the coverage gate reads this out of the
    # syntax tree and only recognises a string constant.
    NAME = "034-register-resolve-clarifications-source.sh"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "scripts" / "migrations").mkdir(parents=True)
        shutil.copy(_MIGRATIONS / MIGRATION, self.root / "scripts" / "migrations" / MIGRATION)
        self.mig = self.root / "scripts" / "migrations" / MIGRATION

    def tearDown(self):
        self._tmp.cleanup()

    def _write_registry(self, text: str) -> Path:
        path = self.root / SOURCES
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return path

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.mig)], capture_output=True, text=True,
                              encoding="utf-8", cwd=str(self.root))

    def test_a_registry_without_the_row_is_asked_on_every_run(self):
        path = self._write_registry(_registry())
        before = hashlib.md5(path.read_bytes()).hexdigest()
        for _ in range(2):
            res = self._run()
            self.assertNotEqual(res.returncode, 0, "a non-zero exit is what brings the ask back")
            self.assertIn(COMMAND, res.stdout)
        self.assertEqual(hashlib.md5(path.read_bytes()).hexdigest(), before,
                         "the migration must never write the registry")

    def test_the_row_in_any_section_ends_the_ask(self):
        for registry in (_registry(active=OWN_ROW.format(status="active")),
                         _registry(deprecated=OWN_ROW.format(status="deprecated"))):
            with self.subTest(registry=registry):
                self._write_registry(registry)
                res = self._run()
                self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertNotIn(COMMAND, res.stdout)

    def test_declared_kind_is_heal(self):
        head = self.mig.read_text(encoding="utf-8").splitlines()[:5]
        self.assertTrue(any("migration-kind: heal" in line for line in head),
                        f"no `# migration-kind: heal` header in:\n{head}")


if __name__ == "__main__":
    unittest.main()
