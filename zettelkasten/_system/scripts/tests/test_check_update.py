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

HOT_FILES = ("minder-memory.md", "constitution-capture.md", "communication-baseline.md",
             "advisory-baseline.md", "constitution-core.md")

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


def parent_ref(sha: str) -> str:
    """`<sha>^` — spelled out so the caret cannot be eaten by a shell."""
    return sha + "^"


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

    OWN_NAME_LINE = "My base lives in ~/projects/minder-ztn-ivanov/zettelkasten.\n"
    PROSE = ("\u0421\u0434\u0435\u043b\u0430\u043b \u043a\u043e\u043f\u0438\u044e "
             "\u0432 {tail}\u0438\u0432\u0430\u043d\u043e\u0432 "
             "\u0440\u044f\u0434\u043e\u043c \u0441 \u043f\u0440\u043e\u0435\u043a\u0442\u043e\u043c.\n")
    SOUL_BEFORE = (OWN_NAME_LINE
                   + "\nSome prose in between.\n\n"
                   + "Backups go to ~/backups/minder-ztn-"
                     "\u0438\u0432\u0430\u043d\u043e\u0432/daily.\n")
    NOTE_REL_BEFORE = "zettelkasten/1_projects/ztn-as-second-brain.md"
    NOTE_REL_AFTER = "zettelkasten/1_projects/minder-memory-as-second-brain.md"
    # An ORDINARY renamed note: a product rename rewrites the title, the slug in
    # the frontmatter, every command line and every path. What survives is the
    # owner's own prose — which is why git's similarity detection does not pair
    # the two sides, and why the predecessor has to be resolved exactly.
    NOTE_BODY = (
        "---\nid: ztn-as-second-brain\ntags:\n  - topic/ztn\n---\n"
        "# ZTN as a second brain\n\n"
        "Run /ztn:process every evening.\n"
        "Then /ztn:maintain, and /ztn:lint before bed.\n"
        "The base is ~/projects/minder-ztn-ivanov/zettelkasten.\n"
        "Backups live in ~/backups/minder-ztn-ivanov.\n"
    )
    NOTE_BODY_AFTER = (
        "---\nid: minder-memory-as-second-brain\ntags:\n  - topic/minder-memory\n---\n"
        "# Minder Memory as a second brain\n\n"
        "Run /minder:mem:process every evening.\n"
        "Then /minder:mem:maintain, and /minder:mem:lint before bed.\n"
        "The base is ~/projects/minder-memory-ivanov/zettelkasten.\n"
        "Backups live in ~/backups/minder-memory-ivanov.\n"
    )
    # The engine's OWN backup directory, renamed with the product. An engine
    # file cannot hold an owner's folder name, and reading it as one is what
    # made the damage probe fail on every clone.
    INSTALLER_BEFORE = 'BACKUP="$CLAUDE_HOME/.minder-ztn-backup-$(date +%Y%m%d)"\n'
    INSTALLER_AFTER = 'BACKUP="$CLAUDE_HOME/.minder-memory-backup-$(date +%Y%m%d)"\n'
    SECRETS_REL = "zettelkasten/_system/state/secrets.enc.json"

    def _rebuild_clone(self, before_rename: dict[str, str]) -> None:
        """The same clone, with `before_rename` files present when the rename ran."""
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.clone)
        self._build_clone(before_rename)

    def _build_clone(self, before_rename: dict[str, str] | None = None) -> None:
        """Two commits, because the damage probe needs a BEFORE to read.

        The first is the clone as it stood before the rename migration ran; the
        second is the update that recorded 032 in the ledger. The owner's own
        folder name survives both — untouched, which is the correct outcome and
        this fixture's baseline — while the engine's own name moved with the
        product, which must not read as damage.
        """
        _write(self.clone, "integrations/VERSION", "1.0.4\n")
        _write(self.clone, "zettelkasten/minder-memory.md",
               "# Minder Memory\n\nMy own dashboard line.\n")
        _write(self.clone, "zettelkasten/_sources/inbox/.gitkeep", "")
        _write(self.clone, "zettelkasten/_records/observations/note.md",
               "An ordinary note about Minder Memory.\n")
        _write(self.clone, "zettelkasten/_system/SOUL.md", self.SOUL_BEFORE)
        _write(self.clone, "zettelkasten/_system/roles/digest/role.md",
               "---\nid: digest\n---\n\n"
               "Read from ~/projects/minder-ztn-"
               "\u0438\u0432\u0430\u043d\u043e\u0432/inbox each morning.\n")
        # A sentence with the name in bare prose — no path, no key, no quotes —
        # which is how people actually write about a folder of theirs.
        _write(self.clone, "zettelkasten/_records/observations/prose.md",
               self.PROSE.format(tail="minder-ztn-"))
        # Every shape 1.0.0 could damage, in the state that precedes it.
        _write(self.clone, "zettelkasten/_records/observations/own-shapes.md",
               "---\nid: own-shapes\n---\n"
               "Backup in ~/minder-ztn_\u0438\u0432\u0430\u043d\u043e\u0432.\n"
               "Scripts in ~/scripts/ztn-process-"
               "\u0438\u0432\u0430\u043d\u043e\u0432/run.sh.\n")
        _write(self.clone, self.NOTE_REL_BEFORE, self.NOTE_BODY)
        for rel, text in (before_rename or {}).items():
            _write(self.clone, rel, text)
        # A note whose own file name is the OWNER's: today's map leaves it
        # alone, so a predecessor cannot be found by inverting the map, and
        # only similarity can pair the two sides.
        _write(self.clone,
               "zettelkasten/1_projects/minder-ztn-"
               "\u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430.md",
               "# Setup\n\n" + "A paragraph of ordinary prose.\n" * 20
               + "Checked out at ~/projects/minder-ztn-"
               "\u0438\u0432\u0430\u043d\u043e\u0432.\n"
               + "Mirrored to deploy@box:/srv/minder-ztn-"
               "\u0438\u0432\u0430\u043d\u043e\u0432.\n")
        # A key is the OWNER's name for a service. It carries the former token
        # on purpose and the store is never rewritten.
        _write(self.clone, self.SECRETS_REL,
               '{"ZTN_TELEGRAM_TOKEN":"' + "x" * 64 + '"}\n')
        _write(self.clone, "integrations/claude-code/install.sh", self.INSTALLER_BEFORE)
        _git(self.clone, "init", "-q", "-b", "main")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "the clone before the rename migration ran")

        # What the rename migration did: the engine's own name moved, the
        # owner's did not, and one note's FILE NAME moved with the product.
        _write(self.clone, "integrations/claude-code/install.sh", self.INSTALLER_AFTER)
        _git(self.clone, "mv", self.NOTE_REL_BEFORE, self.NOTE_REL_AFTER)
        _write(self.clone, self.NOTE_REL_AFTER,
               self.NOTE_BODY_AFTER.replace("minder-memory-ivanov", "minder-ztn-ivanov"))
        ledger = "".join(
            json.dumps({"name": name, "kind": kind, "rc": 0, "outcome": "applied",
                        "ts": "2026-01-01T00:00:00Z", "note": ""}, sort_keys=True) + "\n"
            for name, kind in (("031-minder-memory-harness-wiring.sh", "structural"),
                               ("032-minder-memory-owner-surfaces.sh", "heal"))
        )
        _write(self.clone, ".engine-migrations.jsonl", ledger)
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "a clone that came through the update")

    def _build_home(self) -> None:
        _write(self.home, "CLAUDE.md",
               "# My harness\n"
               "<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->\n"
               + "".join(f"- @~/.claude/minder-memory/{name}\n" for name in HOT_FILES)
               + "<!-- MINDER-MEMORY END -->\n")
        for rel in (*(f"minder-memory/{name}" for name in HOT_FILES),
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
                      "legacy-harness-entries", "rules-dir-clean", "dashboard", "migration-ledger",
                      "conflict-markers", "clone-residue", "sources-untouched"):
            self.assertEqual(statuses[probe], "ok", f"{probe}: {statuses[probe]}")

    def _upstream(self, version: str) -> Path:
        bare = self.tmp / "upstream.git"
        work = self.tmp / "upstream-work"
        if not bare.exists():
            _git(self.tmp, "init", "-q", "--bare", "-b", "main", str(bare))
            _git(self.tmp, "clone", "-q", str(bare), str(work))
        _write(work, "integrations/VERSION", version + "\n")
        _git(work, "add", "-A")
        _git(work, "commit", "-qm", f"engine {version}")
        _git(work, "push", "-q", "origin", "HEAD:main")
        return bare

    def _version_probe(self) -> dict:
        res = self._run("--json")
        return next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "version")

    def test_a_stale_upstream_ref_is_refreshed_before_comparing(self):
        """The ref is whatever the last fetch left; the check asks the remote itself."""
        bare = self._upstream("1.0.3")
        _git(self.clone, "remote", "add", "upstream", str(bare))
        _git(self.clone, "fetch", "-q", "upstream")
        self._upstream("1.0.4")
        probe = self._version_probe()
        self.assertEqual(probe["status"], "ok", probe["evidence"])

    def test_a_custom_fetch_mapping_cannot_leave_the_comparison_stale(self):
        """The comparison reads what this fetch brought, not a ref the mapping never updates."""
        bare = self._upstream("1.0.3")
        _git(self.clone, "remote", "add", "upstream", str(bare))
        _git(self.clone, "fetch", "-q", "upstream")
        _git(self.clone, "config", "remote.upstream.fetch", "+refs/heads/nothing:refs/remotes/upstream/nothing")
        self._upstream("1.0.5")
        probe = self._version_probe()
        self.assertEqual(probe["status"], "fail", probe["evidence"])
        self.assertIn("1.0.5", probe["evidence"])

    def test_a_concurrent_fetch_cannot_change_what_is_compared(self):
        """Anything else fetching between the probe's fetch and its read rewrites FETCH_HEAD."""
        import sys  # noqa: PLC0415
        sys.path.insert(0, str(CHECK.parent))
        import check_update  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415
        decoy = self.tmp / "decoy.git"
        _git(self.tmp, "init", "-q", "--bare", "-b", "main", str(decoy))
        _git(self.clone, "push", "-q", str(decoy), "HEAD:main")       # carries the clone's 1.0.4
        _git(self.clone, "remote", "add", "upstream", str(self._upstream("1.0.5")))
        real = check_update._git

        def racing(repo, *args):
            if args and args[0] == "show":
                real(repo, "fetch", "-q", str(decoy), "main")      # someone else fetches now
            return real(repo, *args)
        with mock.patch.object(check_update, "_git", side_effect=racing):
            probe = check_update.probe_version(self.clone, "upstream", "main")
        self.assertEqual(probe["status"], check_update.FAIL, probe)
        self.assertIn("1.0.5", probe["evidence"])
        leftovers = real(self.clone, "for-each-ref", "refs/minder-check/").stdout.strip()
        self.assertEqual(leftovers, "", "the probe's own ref is removed")

    def test_a_clone_behind_upstream_fails(self):
        _git(self.clone, "remote", "add", "upstream", str(self._upstream("1.1.0")))
        probe = self._version_probe()
        self.assertEqual(probe["status"], "fail", probe["evidence"])
        self.assertIn("behind", probe["evidence"])

    def test_a_clone_ahead_of_upstream_is_not_a_failed_update(self):
        """The authoring clone carries the next version before it is released."""
        _git(self.clone, "remote", "add", "upstream", str(self._upstream("1.0.2")))
        probe = self._version_probe()
        self.assertEqual(probe["status"], "ok", probe["evidence"])
        self.assertIn("ahead", probe["evidence"])

    def test_an_unreachable_upstream_is_a_skip_even_when_the_old_ref_matches(self):
        """A ref nobody refreshed proves nothing about what upstream ships now."""
        bare = self._upstream("1.0.4")
        _git(self.clone, "remote", "add", "upstream", str(bare))
        _git(self.clone, "fetch", "-q", "upstream")
        import shutil  # noqa: PLC0415
        shutil.rmtree(bare)
        probe = self._version_probe()
        self.assertEqual(probe["status"], "skip", probe["evidence"])
        self.assertIn("could not reach", probe["evidence"])

    def test_a_fetch_that_times_out_is_a_skip_not_a_crash(self):
        import sys  # noqa: PLC0415
        sys.path.insert(0, str(CHECK.parent))
        import check_update  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415
        real = subprocess.run

        def slow(cmd, *a, **k):
            if "fetch" in cmd:
                raise subprocess.TimeoutExpired(cmd, 60)
            return real(cmd, *a, **k)
        with mock.patch.object(check_update.subprocess, "run", side_effect=slow):
            probe = check_update.probe_version(self.clone, "upstream", "main")
        self.assertEqual(probe["status"], check_update.SKIP, probe)

    def test_a_shallow_history_cannot_excuse_a_line(self):
        """Lines that cannot be dated are counted, and the check says why."""
        self._rebuild_clone({"zettelkasten/_records/observations/note.md": "I run /ztn:process.\n"})
        shallow = self.tmp / "shallow"
        _git(self.tmp, "clone", "-q", "--depth", "1", "file://" + str(self.clone), str(shallow))
        res = subprocess.run(["python3", str(CHECK), "--repo-root", str(shallow), "--json"],
                             capture_output=True, text=True, encoding="utf-8",
                             env={**os.environ, "CLAUDE_HOME": str(self.home)})
        residue = next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "fail", residue["evidence"])
        self.assertIn("note.md", residue["evidence"])
        self.assertIn("shallow", residue["evidence"])

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

    def test_a_link_of_ours_left_in_rules_fails(self):
        """`rules/` is auto-loaded: a link left there loads beside the block, in every session."""
        doctrine = _write(self.clone, "zettelkasten/_system/docs/ENGINE_DOCTRINE.md", "x\n")
        (self.home / "rules").mkdir(parents=True, exist_ok=True)
        os.symlink(doctrine, self.home / "rules" / "minder-memory-engine-doctrine.md")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"rules-dir-clean"})
        self.assertIn("minder-memory-engine-doctrine.md", res.stdout)

    def test_what_is_not_ours_in_rules_passes(self):
        _write(self.home, "rules/mine.md", "mine\n")
        _write(self.home, "rules/constitution-core.md", "my own, under a name the engine once used\n")
        elsewhere = self.home.parent / "elsewhere.md"
        elsewhere.write_text("x\n", encoding="utf-8")
        os.symlink(elsewhere, self.home / "rules" / "other.md")
        playbook = _write(self.clone, "zettelkasten/_system/long-form-playbook.md", "x\n")
        os.symlink(playbook, self.home / "rules" / "my-playbook.md")
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        probe = next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "rules-dir-clean")
        self.assertIn("my-playbook.md", probe["evidence"])

    def test_an_engine_link_into_another_clone_fails_until_this_installer_removes_it(self):
        """Any clone's installer removes the engine's retired links, wherever they point."""
        other = self.home.parent / "other-clone"
        doctrine = _write(other, "zettelkasten/_system/docs/ENGINE_DOCTRINE.md", "x\n")
        _write(other, ".engine-manifest.yml", "engine: []\n")
        _write(other, "integrations/claude-code/install.sh", "#!/bin/bash\n")
        (self.home / "rules").mkdir(parents=True, exist_ok=True)
        os.symlink(doctrine, self.home / "rules" / "minder-memory-engine-doctrine.md")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"rules-dir-clean"})
        self.assertIn("other-clone", res.stdout)
        self.assertIn("install.sh", res.stdout)

    def test_a_dangling_engine_link_of_a_moved_clone_fails_until_removed(self):
        """It loads nothing, but the installer removes it — so the check asks for that run."""
        (self.home / "rules").mkdir(parents=True, exist_ok=True)
        gone = self.home.parent / "moved-away/zettelkasten/_system/docs/ENGINE_DOCTRINE.md"
        os.symlink(gone, self.home / "rules" / "minder-memory-engine-doctrine.md")
        res = self._run("--json")
        self.assertEqual(self._failed(res), {"rules-dir-clean"})
        self.assertIn("minder-memory-engine-doctrine.md", res.stdout)

    def test_a_block_that_imports_nothing_fails(self):
        """Every file present and nothing loading it is the quietest way to lose all five."""
        md = self.home / "CLAUDE.md"
        md.write_text("".join(ln for ln in md.read_text(encoding="utf-8").splitlines(True)
                              if "@~/.claude/minder-memory/" not in ln), encoding="utf-8")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"managed-block"})

    def test_an_owners_file_under_a_retired_name_is_named_not_failed(self):
        _write(self.home, "rules/constitution-capture.md", "my edited copy\n")
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        probe = next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "rules-dir-clean")
        self.assertIn("constitution-capture.md", probe["evidence"])
        self.assertIn("minder-memory/constitution-capture.md", probe["evidence"])

    def test_a_relative_link_into_this_clone_is_ours(self):
        doctrine = _write(self.clone, "zettelkasten/_system/docs/ENGINE_DOCTRINE.md", "x\n")
        rules = self.home / "rules"
        rules.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(doctrine, rules), rules / "minder-memory-engine-doctrine.md")
        res = self._run("--json")
        self.assertEqual(self._failed(res), {"rules-dir-clean"})
        self.assertIn("this clone", res.stdout)

    def test_a_hand_added_import_of_a_retired_link_outside_the_block_fails(self):
        """Older setup docs told friends to add these lines by hand; after 036 they import nothing."""
        md = self.home / "CLAUDE.md"
        md.write_text(md.read_text(encoding="utf-8")
                      + "\n## Constitution Capture — Global Hook\n- @~/.claude/rules/constitution-capture.md\n",
                      encoding="utf-8")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"rules-dir-clean"})
        self.assertIn("delete", res.stdout)
        self.assertIn("constitution-capture.md", res.stdout)

    def test_an_import_of_the_owners_own_rule_is_not_ours(self):
        md = self.home / "CLAUDE.md"
        md.write_text(md.read_text(encoding="utf-8") + "\n- @~/.claude/rules/my-own.md\n", encoding="utf-8")
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_block_still_importing_from_rules_fails(self):
        md = self.home / "CLAUDE.md"
        md.write_text(md.read_text(encoding="utf-8").replace(
            "- @~/.claude/minder-memory/minder-memory.md\n",
            "- @~/.claude/minder-memory/minder-memory.md\n- @~/.claude/rules/minder-memory.md\n"),
            encoding="utf-8")
        _write(self.home, "rules/minder-memory.md", "x\n")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"rules-dir-clean"})

    def test_the_doctrine_is_not_required_in_the_harness_home(self):
        payload = json.loads(self._run("--json").stdout)
        paths = next(p for p in payload["probes"] if p["probe"] == "harness-paths")
        self.assertEqual(paths["status"], "ok")
        self.assertFalse((self.home / "rules").exists())

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

    def test_a_file_the_rename_missed_fails_the_residue_probe(self):
        """Present when the rename ran and still carrying the former name: the rename missed it."""
        self._rebuild_clone({"zettelkasten/_records/observations/note.md":
                             "I still run /ztn:process every night.\n"})
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(self._failed(res), {"clone-residue"})
        self.assertIn("note.md", res.stdout)

    def test_a_line_written_after_the_rename_is_not_residue(self):
        """A note about the rename names the former product on purpose — nothing missed it."""
        _write(self.clone, "zettelkasten/1_projects/rebrand-decision.md",
               "We renamed ztn to Minder Memory; /ztn:process still works as an alias.\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "a note written after the rename")
        res = self._run("--json")
        residue = next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "ok", residue["evidence"])
        self.assertIn("written after the rename", residue["evidence"])

    def test_an_uncommitted_line_is_judged_as_written_now(self):
        note = self.clone / "zettelkasten/_records/observations/note.md"
        note.write_text(note.read_text(encoding="utf-8") + "Talked about ztn today.\n", encoding="utf-8")
        res = self._run("--json")
        residue = next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "ok", residue["evidence"])

    def test_a_pre_rename_line_that_opts_out_is_not_residue(self):
        """The two opt-outs are what make a pre-rename former-name line legitimate."""
        marked = ("A beat that must keep the aliases: `ztn` / `\u0417\u0422\u041d`. "
                  "<!-- rebrand:keep -->\n")
        self._rebuild_clone({"zettelkasten/_records/observations/beat.md": marked})
        res = self._run("--json")
        residue = next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "ok", residue["evidence"])
        # Without the marker the same pre-rename line is residue — otherwise the
        # assertion above would pass against a probe that had stopped looking.
        self._rebuild_clone({"zettelkasten/_records/observations/beat.md":
                             marked.replace(" <!-- rebrand:keep -->", "")})
        res = self._run("--json")
        self.assertEqual(self._failed(res), {"clone-residue"})
        self.assertIn("beat.md", res.stdout)

    def test_without_a_rename_point_every_former_name_line_counts(self):
        """No ledger and no dashboard history: nothing tells before from after, so nothing is excused."""
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.clone / ".git")
        (self.clone / ".engine-migrations.jsonl").unlink()
        (self.clone / "zettelkasten/minder-memory.md").unlink()
        _git(self.clone, "init", "-q", "-b", "main")
        _write(self.clone, "zettelkasten/_records/observations/note.md", "I run /ztn:process.\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "one commit, no history")
        res = self._run("--json")
        residue = next(p for p in json.loads(res.stdout)["probes"] if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "fail", residue["evidence"])

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

    def test_an_owners_own_folder_name_is_kept_and_named_not_counted_as_residue(self):
        """The fixture's SOUL names the owner's own folder — that is correct.

        Counting it as residue put a permanent failure in front of every friend
        whose clone came through the update exactly right.
        """
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        residue = next(p for p in json.loads(res.stdout)["probes"]
                       if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "ok", residue["evidence"])
        self.assertIn("name your own repository, folder or credential",
                      residue["evidence"])

    def test_a_name_the_rename_damaged_is_reported_against_the_pre_migration_tree(self):
        """1.0.0's map renamed the owner's own folder into a path that is not there.

        Nothing in the tree says so afterwards: the line reads plausibly, and
        the only witness is what the same file said before the migration ran.
        """
        _write(self.clone, "zettelkasten/_system/SOUL.md",
               self.OWN_NAME_LINE.replace("minder-ztn-ivanov", "minder-memory-ivanov"))
        _git(self.clone, "commit", "-qam", "what 1.0.0 did to the owner's own name")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("own-name-damage", self._failed(res))
        payload = res.stdout
        self.assertIn("zettelkasten/_system/SOUL.md", payload)
        self.assertIn("minder-ztn-ivanov", payload, "the report must carry the original text")
        # And it changed nothing.
        self.assertIn("minder-memory-ivanov",
                      (self.clone / "zettelkasten/_system/SOUL.md").read_text(encoding="utf-8"))

    def test_the_damage_probe_skips_when_the_ledger_was_never_committed(self):
        """No ledger in history means no before-state — and a skip says so.

        Silence would be the dangerous answer here: «no damage found» on a
        clone where the question was never asked reads exactly like a clean
        bill of health.
        """
        fresh = self.tmp / "no-ledger"
        _write(fresh, "integrations/VERSION", "1.0.4\n")
        _write(fresh, "zettelkasten/minder-memory.md", "# Minder Memory\n")
        _git(fresh, "init", "-q", "-b", "main")
        _git(fresh, "add", "-A")
        _git(fresh, "commit", "-qm", "a clone whose ledger was never committed")
        res = subprocess.run(
            ["python3", str(CHECK), "--repo-root", str(fresh), "--json"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "CLAUDE_HOME": str(self.home)},
        )
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "skip")
        self.assertIn("no before-state", damage["evidence"])

    def test_ownership_has_exactly_one_home(self):
        """The parity tests are gone because there is nothing left to pin.

        For four releases the same rule lived in two or three files and was held
        together by tests asserting the copies equal. That is a smell, not a
        safeguard: it makes drift detectable instead of impossible. The rule has
        one definition now, and this test guards the property that replaced the
        parity checks — that no consumer restates it.
        """
        import subprocess as sp
        roots = [str(_REPO_ROOT / "scripts"), str(_REPO_ROOT / "zettelkasten/_system/scripts")]
        for symbol in ("ENGINE_ENV_NAMES", "ENGINE_SKILL_NAMES", "OWNER_DATA_PREFIXES",
                       "ENGINE_LEGACY_HARNESS"):
            found = sp.run(["grep", "-rn", "--include=*.py", f"^{symbol}", *roots],
                           capture_output=True, text=True, encoding="utf-8").stdout
            lines = [ln for ln in found.splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1, f"{symbol} is defined {len(lines)}x:\n{found}")
            self.assertIn("lib/ownership.py", lines[0], lines[0])

    def test_every_consumer_imports_the_one_home(self):
        for rel in ("scripts/check_update.py",
                    "scripts/migrations/_032_minder_memory_rebrand.py",
                    "scripts/migrations/_033_own_names.py",
                    "scripts/migrations/_031_harness_wiring.py"):
            text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertTrue("ownership" in text,
                            f"{rel} does not consult the one home")

    IV = "\u0438\u0432\u0430\u043d\u043e\u0432"
    NA = "\u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430"

    def _damage_everywhere(self) -> None:
        """Six dead paths across four files, in every shape that occurs.

        SOUL and a role are ordinary rewrites; the note whose file name the
        CURRENT map moves is found by inverting that map; the note that only
        1.0.0's map moved is not, and needs another route to its predecessor.
        The tails are Cyrillic throughout, because that is the base this was
        found on.
        """
        _write(self.clone, "zettelkasten/_system/SOUL.md",
               f"My base lives in ~/projects/minder-ztn-{self.IV}/zettelkasten.\n"
               "\nSome prose in between.\n\n"
               f"Backups go to ~/backups/minder-memory-{self.IV}/daily.\n")
        _write(self.clone, "zettelkasten/_system/roles/digest/role.md",
               "---\nid: digest\n---\n\n"
               f"Read from ~/projects/minder-memory-{self.IV}/inbox each morning.\n")
        _write(self.clone, self.NOTE_REL_AFTER, self.NOTE_BODY_AFTER)
        # What 1.0.0 did to a note whose own NAME was the owner's.
        _git(self.clone, "mv", f"zettelkasten/1_projects/minder-ztn-{self.NA}.md",
             f"zettelkasten/1_projects/minder-memory-{self.NA}.md")
        _write(self.clone, f"zettelkasten/1_projects/minder-memory-{self.NA}.md",
               "# Setup\n\n" + "A paragraph of ordinary prose.\n" * 20
               + f"Checked out at ~/projects/minder-memory-{self.IV}.\n"
               + f"Mirrored to deploy@box:/srv/minder-memory-{self.IV}.\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "what 1.0.0 did across the whole base")

    def test_every_dead_path_is_reported_whatever_shape_it_arrived_in(self):
        self._damage_everywhere()
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "fail")
        count = int(damage["evidence"].split(" ", 1)[0])
        self.assertGreaterEqual(count, 6, f"expected at least six findings: {damage['evidence']}")

    def test_the_doubled_1_0_0_spelling_is_the_same_damage(self):
        """1.0.0 produced `minder-minder-memory-<tail>` as well as the single form."""
        _write(self.clone, "zettelkasten/_system/SOUL.md",
               f"My base lives in ~/projects/minder-minder-memory-{self.IV}/zettelkasten.\n")
        _git(self.clone, "commit", "-qam", "the doubled spelling")
        res = self._run("--json")
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "fail")
        self.assertIn(f"minder-ztn-{self.IV}", damage["evidence"])

    def test_a_cyrillic_own_name_is_kept_and_counted(self):
        _write(self.clone, "zettelkasten/_records/observations/cyr.md",
               f"Base: ~/minder-ztn-{self.IV}/zettelkasten\n"
               f"Mirror: deploy@box:/srv/minder-ztn-{self.IV}\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "an owner writing in their own alphabet")
        res = self._run("--json")
        residue = next(p for p in json.loads(res.stdout)["probes"]
                       if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "ok", residue["evidence"])
        self.assertIn("name your own repository, folder or credential", residue["evidence"])

    def test_damage_in_bare_prose_is_reported_because_the_old_text_proves_it(self):
        """No introducer, no quotes, no slash — just a sentence.

        The finder required something to INTRODUCE a name — a path, a key, a
        quote, a wikilink — so that the product merely being talked about was
        not read as a thing that must exist. That is the right guard when
        nothing else can settle it. Here something can: the line before the
        rename carried a name `lib.ownership` claims for the owner, and the line
        after carries its renamed form. People write «сделал копию в
        minder-ztn-иванов рядом», and their clone was reported clean.
        """
        # The fixture wrote the sentence before the rename; this is what 1.0.0
        # made of it.
        _write(self.clone, "zettelkasten/_records/observations/prose.md",
               self.PROSE.format(tail="minder-memory-"))
        _git(self.clone, "commit", "-qam", "the rename reached the sentence")

        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "fail", damage["evidence"])
        self.assertIn("prose.md", damage["evidence"])
        self.assertIn(f"minder-ztn-{self.IV}", damage["evidence"],
                      "the pre-rename sentence is the evidence, and it is quoted")

    def test_the_product_named_in_prose_with_no_such_history_is_not_damage(self):
        """The sibling that keeps the loosened rule honest.

        Dropping the introducer only works because the pre-rename text decides.
        A line that merely mentions the product, with nothing behind it in the
        old tree, must still report nothing.
        """
        _write(self.clone, "zettelkasten/_records/observations/talk.md",
               "We renamed the product and minder-memory-platform moved with it.\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qam", "talking about the product")
        res = self._run("--json")
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "ok", damage["evidence"])

    def test_a_file_whose_own_name_was_renamed_is_reported_once(self):
        """The note is readable; every link that named it is not.

        One finding for the FILE, never a rewrite: moving it back or keeping the
        new name are both fine so long as the file and its links agree, and only
        the owner knows which they want.
        """
        self._damage_everywhere()
        res = self._run("--json")
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "fail", damage["evidence"])
        self.assertIn(f"minder-memory-{self.NA}.md", damage["evidence"])
        self.assertIn(f"minder-ztn-{self.NA}.md", damage["evidence"],
                      "the name it used to have is what makes the finding actionable")

    def test_the_shapes_1_0_0_left_behind_are_all_inverted(self):
        """Two shapes the check could not see, both from a real 1.0.0 clone.

        `minder-ztn_<tail>` became `minder-minder_memory_<tail>` — an underscore
        spelling the hyphen-only pattern never matched. And
        `~/scripts/ztn-process-<tail>/run.sh` became
        `minder-memory-process-<tail>`, whose predecessor was reconstructed as
        `minder-ztn-process-<tail>` — a name that never existed, so the finding
        was silently dropped.
        """
        _write(self.clone, "zettelkasten/_records/observations/own-shapes.md",
               "---\nid: own-shapes\n---\n"
               f"Backup in ~/minder-minder_memory_{self.IV}.\n"
               f"Scripts in ~/scripts/minder-memory-process-{self.IV}/run.sh.\n")
        _git(self.clone, "commit", "-qam", "what 1.0.0 made of the owner's names")

        res = self._run("--json")
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "fail", damage["evidence"])
        self.assertIn(f"minder-ztn_{self.IV}", damage["evidence"],
                      "the underscore shape and its before/now pair")
        self.assertIn(f"ztn-process-{self.IV}", damage["evidence"],
                      "the skill-extension shape and its before/now pair")

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
