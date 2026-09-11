"""Integration tests for migration `034-resolve-clarifications-source.sh`.

The migration never writes the owner's registry. It checks whether the
`resolve-clarifications` source is registered; when it is not, it hands the agent
running `/minder:mem:update` the exact `/minder:mem:source-add` command and exits
non-zero, so the runner records `partial` and the check comes back on every update
until the source exists.

Why a suite that EXECUTES it: a `heal` migration that exits 0 on a clone where the
source is missing is recorded `applied` and never checks again — the agent is never
told, and nothing else would notice.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"
_SCRIPTS = _REPO_ROOT / "scripts"
_TEMPLATE = _REPO_ROOT / "zettelkasten" / "_system" / "registries" / "SOURCES.template.md"

MIGRATION = "034-resolve-clarifications-source.sh"
HELPER = "_034_resolve_clarifications_source.py"
REGISTRY = "zettelkasten/_system/registries/SOURCES.md"
SOURCE_ID = "resolve-clarifications"
COMMAND = "/minder:mem:source-add --id resolve-clarifications"

HEADER = "| ID | Inbox Path | Family | Layout | Default Domain | Skip Subdirs | Description | Status |"
SEP = "|---|---|---|---|---|---|---|---|"
DEP_HEADER = ("| ID | Inbox Path | Family | Layout | Default Domain | Skip Subdirs | Description "
              "| Status | Reason |")
DEP_SEP = "|---|---|---|---|---|---|---|---|---|"
NOTES_ROW = "| notes | `_sources/inbox/notes/` | transcript | flat-md | auto | — | Plain notes. | active |"
OWN_ROW = ("| resolve-clarifications | `_sources/inbox/resolve-clarifications/` | transcript | flat-md "
           "| auto | — | Mine. | active |")


def _registry(*, active=(NOTES_ROW,), reserved=(), deprecated=(), notes_extra=()) -> str:
    lines = ["# Source Registry", "", "## Active Sources", "", HEADER, SEP, *active, "",
             "## Reserved Sources", "", HEADER, SEP, *(reserved or ("| _(empty)_ | | | | | | | |",)), "",
             "## Deprecated Sources", "", DEP_HEADER, DEP_SEP,
             *(deprecated or ("| _(empty)_ | | | | | | | | |",)), "",
             "## Notes", "", "- Owner remark.", *notes_extra, ""]
    return "\n".join(lines)


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


class Migration034Tests(unittest.TestCase):
    # Literal, not the module constant: the coverage gate reads this out of the
    # syntax tree and only recognises a string constant.
    NAME = "034-resolve-clarifications-source.sh"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "scripts" / "migrations").mkdir(parents=True)
        shutil.copytree(_SCRIPTS / "lib", self.root / "scripts" / "lib")
        for name in (MIGRATION, HELPER):
            src = _MIGRATIONS / name
            if not src.is_file():
                self.fail(f"{name} does not exist yet at {src} — write the migration")
            shutil.copy(src, self.root / "scripts" / "migrations" / name)
        self.mig = self.root / "scripts" / "migrations" / MIGRATION

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.mig)], cwd=self.root, capture_output=True,
                              text=True, encoding="utf-8", env=dict(os.environ))

    def _write(self, text: str, *, crlf: bool = False) -> Path:
        path = self.root / REGISTRY
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace("\n", "\r\n") if crlf else text)
        return path

    def _assert_untouched(self, path: Path, digest: str) -> None:
        self.assertEqual(_md5(path), digest, "the migration must never write the registry")
        self.assertFalse((self.root / "zettelkasten/_sources/inbox" / SOURCE_ID).exists())
        self.assertFalse((self.root / "zettelkasten/_sources/processed" / SOURCE_ID).exists())

    # -- a base without the source ----------------------------------------- #

    def test_a_missing_source_asks_the_agent_and_stays_partial(self):
        path = self._write(_registry())
        digest = _md5(path)
        proc = self._run()
        self.assertNotEqual(proc.returncode, 0, "exit 0 would record `applied` and never check again")
        self.assertIn(COMMAND, proc.stderr)
        self.assertIn("/minder:mem:update", proc.stderr)
        self._assert_untouched(path, digest)

    def test_a_row_quoted_under_notes_is_not_a_registration(self):
        path = self._write(_registry(notes_extra=("", "```", OWN_ROW, "```")))
        digest = _md5(path)
        proc = self._run()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(COMMAND, proc.stderr)
        self._assert_untouched(path, digest)

    def test_a_crlf_registry_is_read_the_same_way(self):
        path = self._write(_registry(), crlf=True)
        digest = _md5(path)
        proc = self._run()
        self.assertNotEqual(proc.returncode, 0)
        self._assert_untouched(path, digest)

    # -- a base that has it ------------------------------------------------ #

    def test_an_active_row_closes_the_check(self):
        path = self._write(_registry(active=(NOTES_ROW, OWN_ROW)))
        digest = _md5(path)
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(COMMAND, proc.stderr + proc.stdout)
        self._assert_untouched(path, digest)

    def test_a_reserved_row_closes_the_check(self):
        reserved = OWN_ROW.replace("| active |", "| reserved |")
        self._write(_registry(reserved=(reserved,)))
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_an_id_in_another_case_or_backticks_counts(self):
        for spelled in ("Resolve-Clarifications", "`resolve-clarifications`"):
            with self.subTest(spelled=spelled):
                row = OWN_ROW.replace("| resolve-clarifications |", f"| {spelled} |", 1)
                self._write(_registry(active=(NOTES_ROW, row)))
                self.assertEqual(self._run().returncode, 0)

    def test_a_source_the_owner_retired_is_not_brought_back(self):
        retired = OWN_ROW[:-len("| active |")] + "| deprecated | owner retired it |"
        path = self._write(_registry(deprecated=(retired,)))
        digest = _md5(path)
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(COMMAND, proc.stderr + proc.stdout)
        self._assert_untouched(path, digest)

    def test_a_missing_registry_is_not_an_error(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.root / REGISTRY).exists())

    # -- the command matches what new clones ship -------------------------- #

    def test_the_command_registers_exactly_the_row_the_template_ships(self):
        self._write(_registry())
        stderr = self._run().stderr
        template_rows = [ln for ln in _TEMPLATE.read_text(encoding="utf-8").splitlines()
                         if ln.startswith("|") and _cells(ln)[0] == SOURCE_ID]
        self.assertEqual(len(template_rows), 1, "the template must ship the source")
        cells = _cells(template_rows[0])
        expected = {"--family": cells[2], "--layout": cells[3], "--default-domain": cells[4],
                    "--status": cells[7]}
        for flag, value in expected.items():
            self.assertRegex(stderr, re.escape(f"{flag} {value}") + r"(\s|$)", flag)
        self.assertIn(f'--description "{cells[6]}"', stderr)


if __name__ == "__main__":
    unittest.main()
