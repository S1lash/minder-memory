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
        _write(self.clone, "zettelkasten/_system/roles/digest/role.md",
               "---\nid: digest\n---\n\n"
               "Read from ~/projects/minder-ztn-"
               "\u0438\u0432\u0430\u043d\u043e\u0432/inbox each morning.\n")
        # Every shape 1.0.0 could damage, in the state that precedes it.
        _write(self.clone, "zettelkasten/_records/observations/own-shapes.md",
               "---\nid: own-shapes\n---\n"
               "Backup in ~/minder-ztn_\u0438\u0432\u0430\u043d\u043e\u0432.\n"
               "Scripts in ~/scripts/ztn-process-"
               "\u0438\u0432\u0430\u043d\u043e\u0432/run.sh.\n")
        _write(self.clone, self.NOTE_REL_BEFORE, self.NOTE_BODY)
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

    def test_an_own_name_is_admissible_in_every_shape_that_names_a_thing(self):
        """A slash was the old test, and it was too narrow by half.

        The same dead name turns up in a JSON scalar, a YAML scalar, an `id:`
        field and a wikilink — none of which contain a slash, and every one of
        which names something that has to exist. What stays excluded is the
        name in running prose, where it is just the product being discussed.
        """
        import sys as _sys
        _sys.path.insert(0, str(CHECK.parent))
        import check_update  # noqa: E402

        for label, line in (
            ("json scalar", '{"vaultName": "minder-memory-' + self.IV + '"}'),
            ("yaml scalar", "vault: minder-memory-" + self.IV),
            ("id field", "id: minder-memory-" + self.NA),
            ("wikilink", "See [[minder-memory-" + self.NA + "]] for the setup."),
            ("path", "Checked out at ~/projects/minder-memory-" + self.IV + "."),
            # A backtick introduces a name as surely as a colon does, and an
            # owner writing notes in Markdown reaches for it constantly.
            ("backtick", "- \u043a\u043e\u043f\u0438\u044f: `minder-memory-ivanov`"),
        ):
            found = check_update._admissible_own_names(line + "\n")
            self.assertTrue(found, f"{label} was not admitted: {line}")

        prose = "We renamed the product and minder-memory-platform moved with it.\n"
        self.assertEqual(check_update._admissible_own_names(prose), [],
                         "the product named in prose is not a thing that must exist")

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
