"""The post-update self-check — `scripts/check_update.py`.

The check exists because what an update gets wrong is an ABSENCE, and an
absence is invisible: every file still reads correctly, and the migration that
produced it is recorded `applied` and never runs again. So the check itself has
to be tested the way it will be used — on a whole fixture clone and a whole
fixture harness home, one defect at a time — because a check that silently
stops noticing is worse than no check, for exactly the same reason.

Safety contract: `CLAUDE_HOME` always points at a temp directory, every
repository lives inside a `TemporaryDirectory`, and there is no network.
"""
# minder-memory-rebrand: keep-legacy-tokens — the defects this suite injects are the OLD spelling on purpose.

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
CHECK = _REPO_ROOT / "scripts" / "check_update.py"

SKILL_NAMES = (
    "bootstrap", "process", "maintain", "lint", "agent-lens", "agent-lens-add",
    "capture-candidate", "content", "check-decision", "regen-constitution",
    "resolve-clarifications", "save", "sync-data", "source-add", "update",
    "roles", "role-add", "role-edit", "role-list", "role-ask",
)

_GIT_IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", env={**os.environ, **_GIT_IDENTITY})


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return p


class CheckUpdateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.clone = self.tmp / "clone"
        self.home = self.tmp / "claude-home"
        self._build_clone()
        self._build_home()

    def tearDown(self):
        self._tmp.cleanup()

    # -- fixtures ---------------------------------------------------------- #

    def _build_clone(self) -> None:
        _write(self.clone, "integrations/VERSION", "1.0.1\n")
        _write(self.clone, "zettelkasten/minder-memory.md",
               "# Minder Memory\n\nMy own dashboard line.\n")
        _write(self.clone, "zettelkasten/_sources/inbox/.gitkeep", "")
        _write(self.clone, "zettelkasten/_records/observations/note.md",
               "An ordinary note about Minder Memory.\n")
        ledger = "".join(
            json.dumps({"name": name, "kind": kind, "rc": 0, "outcome": "applied",
                        "ts": "2026-01-01T00:00:00Z", "note": ""}, sort_keys=True) + "\n"
            for name, kind in (("031-minder-memory-harness-wiring.sh", "structural"),
                               ("032-minder-memory-owner-surfaces.sh", "heal"))
        )
        _write(self.clone, ".engine-migrations.jsonl", ledger)
        _git(self.clone, "init", "-q", "-b", "main")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "a clone that came through the update")

    def _build_home(self) -> None:
        _write(self.home, "CLAUDE.md",
               "# My harness\n"
               "<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->\n"
               "@~/.claude/rules/minder-memory.md\n"
               "<!-- MINDER-MEMORY END -->\n")
        for rel in ("rules/minder-memory.md", "rules/minder-memory-engine-doctrine.md",
                    "agents/minder-mem-role.md", "commands/minder/mem/recap.md",
                    "commands/minder/mem/search.md"):
            _write(self.home, rel, "x\n")
        for name in SKILL_NAMES:
            _write(self.home, f"skills/minder-mem-{name}/SKILL.md", "x\n")

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(CHECK), "--repo-root", str(self.clone), *args],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "CLAUDE_HOME": str(self.home)},
        )

    def _failed(self, res: subprocess.CompletedProcess) -> set[str]:
        payload = json.loads(res.stdout)
        return {p["probe"] for p in payload["probes"] if p["status"] == "fail"}

    # -- the healthy case --------------------------------------------------- #

    def test_a_clone_that_came_through_the_update_passes(self):
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        payload = json.loads(res.stdout)
        statuses = {p["probe"]: p["status"] for p in payload["probes"]}
        self.assertEqual([p for p, s in statuses.items() if s == "fail"], [])
        # The probes that CAN be answered from this fixture must actually be
        # answered — a suite where everything skips proves nothing.
        for probe in ("managed-block", "harness-paths", "skill-count",
                      "legacy-harness-entries", "dashboard", "migration-ledger",
                      "conflict-markers", "clone-residue", "sources-untouched"):
            self.assertEqual(statuses[probe], "ok", f"{probe}: {statuses[probe]}")

    def test_a_probe_that_cannot_be_asked_says_so_rather_than_passing(self):
        """No remote is fetched in the fixture, so the version probe skips."""
        res = self._run("--json")
        payload = json.loads(res.stdout)
        version = next(p for p in payload["probes"] if p["probe"] == "version")
        self.assertEqual(version["status"], "skip")
        self.assertIn("cannot compare", version["evidence"])

    # -- one defect at a time ---------------------------------------------- #

    def test_a_plain_leftover_under_the_harness_home_fails(self):
        _write(self.home, "skills/ztn-process/SKILL.md", "a stub of the old wiring\n")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"legacy-harness-entries"})
        self.assertIn("ztn-process", res.stdout)

    def test_a_former_managed_block_marker_fails(self):
        _write(self.home, "CLAUDE.md",
               "# My harness\n"
               "<!-- MINDER-ZTN BEGIN — managed by install.sh, do not edit by hand -->\n"
               "@~/.claude/rules/minder-memory.md\n"
               "<!-- MINDER-ZTN END -->\n")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"managed-block"})

    def test_a_conflict_marker_in_a_tracked_note_fails(self):
        _write(self.clone, "zettelkasten/_records/observations/note.md",
               "<<<<<<< HEAD\nmine\n=======\ntheirs\n>>>>>>> upstream/main\n")
        _git(self.clone, "commit", "-qam", "a merge nobody finished")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"conflict-markers"})

    def test_a_missing_skill_link_fails_on_the_count(self):
        import shutil
        shutil.rmtree(self.home / "skills" / "minder-mem-lint")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"skill-count"})

    def test_a_file_still_carrying_the_former_name_fails_the_residue_probe(self):
        _write(self.clone, "zettelkasten/_records/observations/note.md",
               "I still run /ztn:process every night.\n")
        _git(self.clone, "commit", "-qam", "a file the rename missed")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"clone-residue"})

    def test_a_line_that_opts_out_of_the_rename_is_not_residue(self):
        """The two opt-outs are what make a former-name line legitimate.

        Without discounting them the probe fails forever on the engine's own
        files — and a probe that always fails is a probe nobody reads.
        """
        marked = ("A beat that must keep the aliases: `ztn` / `\u0417\u0422\u041d`. "
                  "<!-- rebrand:keep -->\n")
        _write(self.clone, "zettelkasten/_records/observations/beat.md", marked)
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "a line that opts out on purpose")
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        residue = next(p for p in json.loads(res.stdout)["probes"]
                       if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "ok", residue["evidence"])

        # The same line WITHOUT the marker is residue — otherwise the test above
        # would pass just as well against a probe that had stopped looking.
        _write(self.clone, "zettelkasten/_records/observations/beat.md",
               marked.replace(" <!-- rebrand:keep -->", ""))
        _git(self.clone, "commit", "-qam", "the marker removed")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"clone-residue"})
        self.assertIn("beat.md", res.stdout)

    def test_a_file_that_opts_out_whole_is_not_residue(self):
        _write(self.clone, "zettelkasten/_records/observations/inventory.md",
               "<!-- minder-memory-rebrand: keep-legacy-tokens -->\n"
               "This file lists the former names on purpose: ztn, ztn-process.\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "a file that opts out whole")
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_the_opt_out_markers_match_the_rename_map(self):
        """Restated, not imported — so a test has to hold them together.

        `check_update.py` cannot import the map: that module is a migration and
        leaves the engine when the chain floor moves past it, which would take
        this permanent check down with it. The copy is pinned here instead.
        """
        map_module = _REPO_ROOT / "scripts" / "migrations" / "_032_minder_memory_rebrand.py"
        if not map_module.is_file():
            self.skipTest("the rename map has been retired; the check keeps its own copy")
        import sys as _sys
        _sys.path.insert(0, str(map_module.parent))
        _sys.path.insert(0, str(CHECK.parent))
        import _032_minder_memory_rebrand as rename_map  # noqa: E402
        import check_update  # noqa: E402
        self.assertEqual(check_update.LINE_KEEP, rename_map.LINE_KEEP)
        self.assertEqual(check_update.FILE_KEEP, rename_map.FILE_KEEP)

    # -- cannot run at all -------------------------------------------------- #

    def test_a_directory_that_is_not_a_clone_exits_two(self):
        elsewhere = self.tmp / "not-a-clone"
        elsewhere.mkdir()
        res = subprocess.run(
            ["python3", str(CHECK), "--repo-root", str(elsewhere), "--json"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "CLAUDE_HOME": str(self.home)},
        )
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("not a git clone", res.stderr)

    def test_a_repository_without_the_version_file_exits_two(self):
        other = self.tmp / "some-repo"
        other.mkdir()
        _write(other, "README.md", "not an engine clone\n")
        _git(other, "init", "-q", "-b", "main")
        _git(other, "add", "-A")
        _git(other, "commit", "-qm", "seed")
        res = subprocess.run(
            ["python3", str(CHECK), "--repo-root", str(other), "--json"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "CLAUDE_HOME": str(self.home)},
        )
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("not an engine clone", res.stderr)

    # -- the plain summary --------------------------------------------------- #

    def test_the_plain_summary_names_what_failed(self):
        _write(self.home, "skills/ztn-process/SKILL.md", "a stub\n")
        res = self._run()
        self.assertEqual(res.returncode, 1)
        self.assertIn("legacy-harness-entries", res.stdout)
        self.assertIn("probe(s) failed", res.stdout)


if __name__ == "__main__":
    unittest.main()
