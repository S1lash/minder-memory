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
    SOUL_BEFORE = (OWN_NAME_LINE
                   + "\nSome prose in between.\n\n"
                   + "Backups go to ~/backups/minder-ztn-ivanov/daily.\n")
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

    def _build_clone(self) -> None:
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
        _write(self.clone, self.NOTE_REL_BEFORE, self.NOTE_BODY)
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

    def test_the_own_name_pattern_matches_the_rename_map(self):
        map_module = _REPO_ROOT / "scripts" / "migrations" / "_032_minder_memory_rebrand.py"
        if not map_module.is_file():
            self.skipTest("the rename map has been retired; the check keeps its own copy")
        import sys as _sys
        _sys.path.insert(0, str(map_module.parent))
        _sys.path.insert(0, str(CHECK.parent))
        import _032_minder_memory_rebrand as rename_map  # noqa: E402
        import check_update  # noqa: E402
        self.assertEqual(check_update.OWN_NAME_PATTERN, rename_map.OWN_NAME_PATTERN)
        self.assertEqual(check_update.OWN_CREDENTIAL_PATTERN,
                         rename_map.OWN_CREDENTIAL_PATTERN)
        self.assertEqual(tuple(check_update.ENGINE_ENV_NAMES),
                         tuple(rename_map.ENGINE_ENV_NAMES),
                         'the engine-owned variable list must not fork')

    def test_the_engines_own_renamed_name_is_not_read_as_damage(self):
        """`.minder-memory-backup-` in the installer is the ENGINE's own name.

        It matches every shape the damage detector looks for — path-like, and
        its predecessor is in the pre-rename tree — so before this was scoped
        to owner space the probe failed on every clone in existence.
        """
        res = self._run("--json")
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "ok", damage["evidence"])
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_damage_inside_a_file_the_rename_renamed_is_still_found(self):
        """The pre-rename text is under the file's OLD path, or nowhere.

        A note whose own file name moved with the product is exactly where an
        owner's path is most likely to be written down, so failing to follow
        the rename loses the findings most worth having.
        """
        _write(self.clone, self.NOTE_REL_AFTER, self.NOTE_BODY_AFTER)
        _git(self.clone, "commit", "-qam", "the same damage, in a file that was renamed")

        # The test must not be able to pass by accident: similarity detection
        # does NOT pair these two sides, which is the whole reason the
        # predecessor has to be resolved exactly.
        before = _git(self.clone, "log", "--reverse", "--format=%H", "-S", "032-minder-memory",
                      "--", ".engine-migrations.jsonl").stdout.splitlines()[0].strip()
        parent = _git(self.clone, "rev-parse", parent_ref(before)).stdout.strip()
        paired = _git(self.clone, "diff", "--name-status", "-M30%", "--diff-filter=R",
                      parent, "HEAD").stdout
        self.assertNotIn("as-second-brain", paired,
                         "similarity paired the rename, so this fixture proves nothing")

        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("own-name-damage", self._failed(res))
        self.assertIn("minder-memory-as-second-brain.md", res.stdout)
        # BOTH dead paths, each with its before/now pair.
        self.assertIn("~/projects/minder-ztn-ivanov/zettelkasten", res.stdout)
        self.assertIn("~/backups/minder-ztn-ivanov", res.stdout)

    def test_the_before_text_is_the_line_that_matches_not_the_first_one(self):
        """Two lines carry the name; the evidence must quote the right one."""
        _write(self.clone, "zettelkasten/_system/SOUL.md",
               self.SOUL_BEFORE.replace("~/backups/minder-ztn-ivanov",
                                        "~/backups/minder-memory-ivanov"))
        _git(self.clone, "commit", "-qam", "the fourth line damaged, the first intact")
        res = self._run("--json")
        damage = next(p for p in json.loads(res.stdout)["probes"]
                      if p["probe"] == "own-name-damage")
        self.assertEqual(damage["status"], "fail")
        self.assertIn("Backups go to ~/backups/minder-ztn-ivanov/daily.", damage["evidence"])
        self.assertNotIn("My base lives in", damage["evidence"],
                         "the first line carrying the token is not the one that moved")

    def test_the_clarifications_queue_may_quote_former_names(self):
        """The queue is where the engine RAISES an old name with the owner."""
        _write(self.clone, "zettelkasten/_system/state/CLARIFICATIONS.md",
               "# Clarifications Needed\n\n## Open Items\n\n"
               "> now: ~/projects/minder-memory-ivanov, before: ~/projects/minder-ztn-ivanov\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "a queue item quoting both spellings")
        res = self._run("--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_store_whose_bytes_moved_is_not_a_fault_by_itself(self):
        """Both sides renamed together is a consistent clone, not a broken one.

        A clone that passed through the release which renamed the declaration
        AND the store needs no repair, and failing it would send its owner
        hunting for damage that is not there. The bytes are evidence; whether
        every declared credential RESOLVES is the answer.
        """
        runner = _REPO_ROOT / "zettelkasten" / "_system" / "scripts" / "roles_run.py"
        if not runner.is_file():
            self.skipTest("no roles runner in this engine")
        import shutil
        dest = self.clone / "zettelkasten" / "_system" / "scripts"
        dest.mkdir(parents=True, exist_ok=True)
        for item in runner.parent.iterdir():
            if item.is_file() and item.suffix == ".py":
                shutil.copy(item, dest / item.name)
        _write(self.clone, self.SECRETS_REL, '{"MY_TELEGRAM_TOKEN":"' + "y" * 64 + '"}\n')
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qam", "a store both sides of which moved together")

        res = self._run("--json")
        store = next(p for p in json.loads(res.stdout)["probes"]
                     if p["probe"] == "credential-store")
        self.assertEqual(store["status"], "ok", store["evidence"])
        self.assertIn("bytes differ", store["evidence"],
                      "the byte comparison is still reported, as evidence")

    def test_the_owner_space_predicate_agrees_with_the_rename_map(self):
        """Owner space is the map's own owner-data class, plus named extras."""
        map_module = _REPO_ROOT / "scripts" / "migrations" / "_032_minder_memory_rebrand.py"
        if not map_module.is_file():
            self.skipTest("the rename map has been retired; the check keeps its own copy")
        import sys as _sys
        _sys.path.insert(0, str(map_module.parent))
        _sys.path.insert(0, str(CHECK.parent))
        import _032_minder_memory_rebrand as rename_map  # noqa: E402
        import check_update  # noqa: E402
        for prefix in check_update._OWNER_DATA_PREFIXES:
            self.assertEqual(rename_map.classify(prefix + "thing.md"), "owner-data", prefix)
            self.assertTrue(check_update.in_owner_space(prefix + "thing.md"), prefix)
        for extra in check_update._OWNER_SPACE_EXTRA_FILES:
            self.assertTrue(check_update.in_owner_space(extra), extra)
        for engine in ("integrations/claude-code/install.sh", "scripts/check_update.py",
                       "docs/CHANGELOG.md", "zettelkasten/_system/docs/SYSTEM_CONFIG.md"):
            self.assertNotEqual(rename_map.classify(engine), "owner-data", engine)
            self.assertFalse(check_update.in_owner_space(engine), engine)

    def test_the_credential_store_may_carry_the_owners_own_key_names(self):
        """The store is never rewritten, so a key of theirs keeps its spelling."""
        res = self._run("--json")
        residue = next(p for p in json.loads(res.stdout)["probes"]
                       if p["probe"] == "clone-residue")
        self.assertEqual(residue["status"], "ok", residue["evidence"])

    def test_the_credential_probe_asks_whether_every_declared_secret_resolves(self):
        """Byte-identity is evidence; resolution is the question.

        A clone that passed through the release which renamed BOTH sides has a
        store that differs from the pre-rename tree and is perfectly correct.
        The check that matters is the engine's own preflight: does every name a
        role declares exist in the store.
        """
        runner = _REPO_ROOT / "zettelkasten" / "_system" / "scripts" / "roles_run.py"
        if not runner.is_file():
            self.skipTest("no roles runner in this engine")
        dest = self.clone / "zettelkasten" / "_system" / "scripts"
        dest.mkdir(parents=True, exist_ok=True)
        import shutil
        for item in (runner.parent).iterdir():
            if item.is_file() and item.suffix == ".py":
                shutil.copy(item, dest / item.name)
        _write(self.clone, "zettelkasten/_system/roles/telegram-digest/role.md",
               "---\nid: telegram-digest\nname: Telegram digest\nstatus: active\n"
               "cadence: daily 07:00\nsecrets:\n  - ZTN_TELEGRAM_TOKEN\n---\n\nDo it.\n")
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "-qm", "a role declaring a credential of the owner's")

        res = self._run("--json")
        store = next(p for p in json.loads(res.stdout)["probes"]
                     if p["probe"] == "credential-store")
        self.assertEqual(store["status"], "ok", store["evidence"])
        self.assertIn("resolve", store["evidence"])

        # ...and a declaration the store cannot answer is a failure that names
        # the role and the secret.
        _write(self.clone, "zettelkasten/_system/roles/telegram-digest/role.md",
               "---\nid: telegram-digest\nname: Telegram digest\nstatus: active\n"
               "cadence: daily 07:00\nsecrets:\n  - ZTN_MISSING_TOKEN\n---\n\nDo it.\n")
        _git(self.clone, "commit", "-qam", "a declaration nothing answers")
        res = self._run("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("credential-store", self._failed(res))
        self.assertIn("telegram-digest", res.stdout)
        self.assertIn("ZTN_MISSING_TOKEN", res.stdout)

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
