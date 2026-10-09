"""How `install.sh` wires the files every Claude Code session loads.

One mechanism: the installer links the global files into
`$CLAUDE_HOME/minder-memory/` — a directory Claude Code does not auto-load — and
the managed block in `$CLAUDE_HOME/CLAUDE.md` imports each of them. The block is
therefore the complete list of what the engine puts into a session outside this
repository. The engine doctrine is not in it: it loads only in this repository,
through `.claude/CLAUDE.md`.

The six links an earlier installer placed in `$CLAUDE_HOME/rules/` (a directory
Claude Code DOES auto-load) are removed — by exact name, and only when the link
points into this repository. Anything else in `rules/` is somebody's.

Safety contract: every repository and every harness home lives in a
`TemporaryDirectory`; `CLAUDE_HOME` always points there.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_INSTALLER = _REPO_ROOT / "integrations" / "claude-code" / "install.sh"

HOT = ("minder-memory.md", "constitution-capture.md", "communication-baseline.md",
       "advisory-baseline.md", "constitution-core.md")
DOCTRINE_LINK = "minder-memory-engine-doctrine.md"
RETIRED = HOT + (DOCTRINE_LINK,)
SOURCES = {
    "constitution-capture.md": "zettelkasten/_system/docs/constitution-capture.md",
    "communication-baseline.md": "zettelkasten/_system/docs/communication-baseline.md",
    "advisory-baseline.md": "zettelkasten/_system/docs/advisory-baseline.md",
    "constitution-core.md": "zettelkasten/_system/views/constitution-core.md",
    DOCTRINE_LINK: "zettelkasten/_system/docs/ENGINE_DOCTRINE.md",
}
BEGIN = "<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->"
END = "<!-- MINDER-MEMORY END -->"
_IMPORT = re.compile(r"@(\S+)")


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return p


def _block(md: str) -> str:
    return md[md.index(BEGIN):md.index(END)]


def _snapshot(home: Path) -> dict[str, str]:
    """Every entry under the home except the installer's dated backups."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(home):
        dirnames[:] = [d for d in dirnames if not d.startswith(".minder-memory-backup-")]
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = str(p.relative_to(home))
            if p.is_symlink():
                out[rel] = "-> " + os.readlink(p)
            elif p.is_file():
                out[rel] = p.read_text(encoding="utf-8")
            else:
                out[rel] = "<dir>"
    return out


class InstallHotWiringTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.repo = tmp / "repo"
        self.home = tmp / "home"
        self.elsewhere = tmp / "elsewhere"
        self._fake_repo()
        self.home.mkdir()
        self.elsewhere.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    # -- fixtures ---------------------------------------------------------- #

    def _fake_repo(self) -> None:
        repo = self.repo
        shutil.copy(_INSTALLER, _write(repo, "integrations/claude-code/install.sh", ""))
        shutil.copytree(_REPO_ROOT / "scripts" / "lib", repo / "scripts" / "lib",
                        ignore=shutil.ignore_patterns("__pycache__"))
        _write(repo, "integrations/claude-code/rules/minder-memory.md", "base {{MINDER_MEMORY_BASE}}\n")
        shutil.copy(_REPO_ROOT / "integrations/claude-code/uninstall.sh",
                    _write(repo, "integrations/claude-code/uninstall.sh", ""))
        _write(repo, "integrations/claude-code/commands/minder/mem/recap.md", "cmd\n")
        (repo / "integrations/claude-code/skills").mkdir(parents=True)
        for name, rel in SOURCES.items():
            _write(repo, rel, f"{name}\n")

    def _legacy_home(self, *, target_root: Path | None = None) -> None:
        """The wiring a 1.4.0 installer leaves: six links in `rules/`, five imports."""
        root = target_root or self.repo
        rules = self.home / "rules"
        rules.mkdir(parents=True, exist_ok=True)
        os.symlink(root / "integrations/claude-code/built/rules/minder-memory.md",
                   rules / "minder-memory.md")
        for name, rel in SOURCES.items():
            os.symlink(root / rel, rules / name)
        _write(self.home, "CLAUDE.md",
               "# mine\n\n" + BEGIN + "\n"
               + "".join(f"- @~/.claude/rules/{n}\n" for n in HOT)
               + END + "\n\n- below\n")

    def _env(self, *, failing_awk: bool = False) -> dict[str, str]:
        env = {**os.environ, "CLAUDE_HOME": str(self.home)}
        if failing_awk:
            shim = Path(self._tmp.name) / "shim"
            _write(shim, "awk", "#!/bin/sh\nexit 2\n").chmod(0o755)
            env["PATH"] = f"{shim}{os.pathsep}{env['PATH']}"
        return env

    def _run(self, repo: Path | None = None, *, failing_awk: bool = False) -> subprocess.CompletedProcess:
        installer = (repo or self.repo) / "integrations/claude-code/install.sh"
        return subprocess.run(["bash", str(installer)], cwd=str(repo or self.repo),  # portability-ok: invoked through bash, never by the executable bit
                              capture_output=True, text=True, encoding="utf-8",
                              env=self._env(failing_awk=failing_awk))

    def _ok(self, repo: Path | None = None) -> subprocess.CompletedProcess:
        res = self._run(repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    # -- the new wiring ---------------------------------------------------- #

    def test_global_files_are_linked_beside_rules_not_into_it(self):
        self._ok()
        hot = self.home / "minder-memory"
        self.assertEqual(sorted(p.name for p in hot.iterdir()), sorted(HOT))
        for name in HOT:
            self.assertTrue((hot / name).is_symlink(), name)
            self.assertTrue((hot / name).resolve().is_relative_to(self.repo.resolve()), name)
        rules = self.home / "rules"
        self.assertEqual([p.name for p in rules.iterdir()] if rules.is_dir() else [], [],
                         "nothing of the engine's may sit in the auto-loaded rules/")

    def test_the_block_imports_exactly_the_linked_files(self):
        self._ok()
        block = _block((self.home / "CLAUDE.md").read_text(encoding="utf-8"))
        imports = _IMPORT.findall(block)
        self.assertEqual(sorted(imports), sorted(f"~/.claude/minder-memory/{n}" for n in HOT))
        for imp in imports:
            self.assertTrue((self.home / imp.removeprefix("~/.claude/")).exists(), imp)

    def test_the_doctrine_is_not_wired_globally(self):
        self._ok()
        for p in self.home.rglob("*"):
            if p.is_symlink():
                self.assertNotEqual(p.resolve().name, "ENGINE_DOCTRINE.md", str(p))
        self.assertNotIn("ENGINE_DOCTRINE", (self.home / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertNotIn(DOCTRINE_LINK, (self.home / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_every_source_rule_is_wired(self):
        """A rule added beside `minder-memory.md` without a table row would be rendered and never loaded."""
        installer = _INSTALLER.read_text(encoding="utf-8")
        for src in sorted((_REPO_ROOT / "integrations/claude-code/rules").glob("*.md")):
            self.assertRegex(installer, rf"(?m)^{re.escape(src.name)}\|",
                             f"{src.name} has no row in the installer's hot table")

    # -- converging a 1.4.0 home ------------------------------------------- #

    def test_the_six_old_links_are_removed(self):
        self._legacy_home()
        self._ok()
        for name in RETIRED:
            self.assertFalse(os.path.lexists(self.home / "rules" / name), name)
        md = (self.home / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("~/.claude/rules/", md)
        self.assertEqual(md.count(BEGIN), 1)
        self.assertLess(md.index("# mine"), md.index(BEGIN))
        self.assertLess(md.index(END), md.index("- below"))

    def test_an_old_link_recorded_through_the_physical_path_is_removed(self):
        """`/var` vs `/private/var`, a symlinked home: the same repository by another spelling."""
        physical = Path(os.path.realpath(self.repo))
        if physical == self.repo:
            alias = Path(self._tmp.name) / "alias"
            os.symlink(self.repo, alias)
            self._legacy_home(target_root=self.repo)
            self._ok(alias)
        else:
            self._legacy_home(target_root=physical)
            self._ok()
        for name in RETIRED:
            self.assertFalse(os.path.lexists(self.home / "rules" / name), name)

    def test_what_is_not_ours_in_rules_is_left_alone(self):
        rules = self.home / "rules"
        _write(self.home, "rules/constitution-core.md", "my own file under a retired name\n")
        _write(self.elsewhere, "doctrine.md", "another product\n")
        os.symlink(self.elsewhere / "doctrine.md", rules / DOCTRINE_LINK)
        _write(self.home, "rules/mine.md", "mine\n")
        os.symlink(self.repo / "zettelkasten/_system/docs/advisory-baseline.md", rules / "my-link.md")
        self._ok()
        self.assertEqual((rules / "constitution-core.md").read_text(encoding="utf-8"),
                         "my own file under a retired name\n")
        self.assertTrue((rules / DOCTRINE_LINK).is_symlink())
        self.assertEqual(os.readlink(rules / DOCTRINE_LINK), str(self.elsewhere / "doctrine.md"))
        self.assertTrue((rules / "mine.md").is_file())
        self.assertTrue((rules / "my-link.md").is_symlink(),
                        "a link the owner made under their own name is theirs, whatever it points at")

    def test_a_second_run_changes_nothing(self):
        self._legacy_home()
        self._ok()
        self.assertFalse(os.path.lexists(self.home / "rules" / DOCTRINE_LINK),
                         "precondition: the first run converged")
        before = _snapshot(self.home)
        self._ok()
        self.assertEqual(_snapshot(self.home), before)

    def test_without_the_ownership_helper_the_new_wiring_lands_and_the_run_fails(self):
        """Degraded, never broken — and never silently: an exit 0 would retire migration 036 for good."""
        (self.repo / "scripts/lib/harness_entries.py").unlink()
        self._legacy_home()
        res = self._run()
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("left in place", res.stdout + res.stderr)
        self.assertTrue((self.home / "rules" / DOCTRINE_LINK).is_symlink())
        md = (self.home / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("~/.claude/rules/", md)
        self.assertEqual(md.count("@~/.claude/minder-memory/"), len(HOT))
        self.assertEqual(len(list((self.home / "minder-memory").iterdir())), len(HOT))

    def test_a_block_that_cannot_be_rewritten_keeps_the_old_links_and_fails(self):
        """The old block imports the old links: retiring them under an unchanged block kills every import."""
        self._legacy_home()
        before = (self.home / "CLAUDE.md").read_text(encoding="utf-8")
        res = self._run(failing_awk=True)
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual((self.home / "CLAUDE.md").read_text(encoding="utf-8"), before)
        for name in RETIRED:
            self.assertTrue((self.home / "rules" / name).is_symlink(), name)
        self.assertFalse(any(p.name.startswith("CLAUDE.md.") for p in self.home.iterdir()),
                         "temporary files are cleaned up on failure")

    def test_a_crlf_claude_md_is_rewritten_not_left_importing_retired_links(self):
        """A Windows editor saves CRLF; a marker that no longer matches must not mean a silent no-op."""
        self._legacy_home()
        md = self.home / "CLAUDE.md"
        md.write_bytes(md.read_bytes().replace(b"\n", b"\r\n"))
        self._ok()
        text = md.read_text(encoding="utf-8")
        self.assertNotIn("~/.claude/rules/", text)
        self.assertEqual(text.count("@~/.claude/minder-memory/"), len(HOT))
        self.assertEqual(text.count("MINDER-MEMORY BEGIN"), 1)
        self.assertIn("# mine", text)
        self.assertIn("- below", text)

    def test_a_block_without_its_closing_marker_is_refused_and_nothing_is_lost(self):
        """The splice skips to the END marker; without one it dropped everything after BEGIN."""
        self._legacy_home()
        md = self.home / "CLAUDE.md"
        md.write_text(md.read_text(encoding="utf-8").replace(END, "<!-- end of minder block -->"),
                      encoding="utf-8")
        before = md.read_text(encoding="utf-8")
        res = self._run()
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(md.read_text(encoding="utf-8"), before)
        for name in RETIRED:
            self.assertTrue((self.home / "rules" / name).is_symlink(), name)

    def test_an_old_link_recorded_through_an_alias_is_removed_from_the_real_path(self):
        alias = Path(self._tmp.name) / "alias"
        os.symlink(self.repo, alias)
        self._legacy_home(target_root=alias)
        self._ok()
        for name in RETIRED:
            self.assertFalse(os.path.lexists(self.home / "rules" / name), name)

    def test_a_relative_old_link_is_removed(self):
        rules = self.home / "rules"
        rules.mkdir(parents=True)
        target = self.repo / SOURCES[DOCTRINE_LINK]
        os.symlink(os.path.relpath(target, rules), rules / DOCTRINE_LINK)
        self._ok()
        self.assertFalse(os.path.lexists(rules / DOCTRINE_LINK))

    def test_the_global_files_table_is_read_in_any_heredoc_spelling_and_fails_closed(self):
        import sys
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
        from lib import ownership  # noqa: PLC0415
        root = Path(self._tmp.name) / "variants"
        rows = "a.md|x/a.md|A\nb.md|x/b.md|B\n"
        for opener in ("HOT_FILES=\"$(cat <<'TABLE'", "HOT_FILES=\"$(cat << 'TABLE'",
                       "HOT_FILES=\"$(cat <<TABLE", 'HOT_FILES="$(cat <<\"TABLE\"'):
            with self.subTest(opener=opener):
                _write(root, "integrations/claude-code/install.sh", f"#!/bin/bash\n{opener}\n{rows}TABLE\n)\"\n")
                self.assertEqual(ownership.engine_global_files(root), [("a.md", "x/a.md"), ("b.md", "x/b.md")])
        _write(root, "integrations/claude-code/install.sh", "#!/bin/bash\necho no table\n")
        with self.assertRaises(ownership.GlobalFilesUnreadable):
            ownership.engine_global_files(root)
        with self.assertRaises(ownership.GlobalFilesUnreadable):
            ownership.engine_global_files(Path(self._tmp.name) / "no-such-clone")

    def test_the_check_fails_when_it_cannot_read_the_global_files(self):
        import sys
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
        import check_update  # noqa: PLC0415
        bad = Path(self._tmp.name) / "no-such-clone"
        self.home.mkdir(exist_ok=True)
        _write(self.home, "CLAUDE.md", f"{BEGIN}\n{END}\n")
        for probe in (check_update.probe_harness_paths(self.home, engine_root=bad),
                      check_update.probe_managed_block(self.home, engine_root=bad)):
            self.assertEqual(probe["status"], check_update.FAIL, probe)
            self.assertIn("install.sh", probe["evidence"])

    def test_the_post_update_check_reads_the_global_files_from_the_installer(self):
        """One list: the installer's table. The check derives its required paths from it."""
        import sys
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
        from lib import ownership  # noqa: PLC0415
        import check_update  # noqa: PLC0415
        files = ownership.engine_global_files(_REPO_ROOT)
        self.assertEqual([name for name, _ in files], list(HOT))
        required = check_update.required_harness_paths(_REPO_ROOT)
        for name in HOT:
            self.assertIn(f"minder-memory/{name}", required)

    def test_a_claude_md_kept_in_dotfiles_stays_a_link(self):
        """Replacing the link with a file cut the owner's CLAUDE.md off from their dotfiles repo."""
        self._legacy_home()
        dotfiles = Path(self._tmp.name) / "dotfiles" / "CLAUDE.md"
        dotfiles.parent.mkdir()
        (self.home / "CLAUDE.md").rename(dotfiles)
        os.symlink(dotfiles, self.home / "CLAUDE.md")
        for _ in range(2):
            self._ok()
            self.assertTrue((self.home / "CLAUDE.md").is_symlink())
            text = dotfiles.read_text(encoding="utf-8")
            self.assertEqual(text.count("@~/.claude/minder-memory/"), len(HOT))
            self.assertIn("# mine", text)
        self._uninstall_ok = self._uninstall()
        self.assertEqual(self._uninstall_ok.returncode, 0, self._uninstall_ok.stderr)
        self.assertTrue((self.home / "CLAUDE.md").is_symlink())
        self.assertNotIn("MINDER-MEMORY BEGIN", dotfiles.read_text(encoding="utf-8"))

    def test_malformed_marker_layouts_are_refused_and_nothing_is_lost(self):
        """Only well-formed BEGIN…END pairs are spliced; anything else would drop the owner's text."""
        layouts = {
            "end-before-begin": "# mine\n{END}\nmiddle of mine\n{BEGIN}\n- old\ntail of mine\n",
            "begin-twice-in-a-row": "# mine\n{BEGIN}\n- old\n{BEGIN}\n- older\n{END}\ntail of mine\n",
            "end-twice-in-a-row": "# mine\n{BEGIN}\n- old\n{END}\nmiddle\n{END}\ntail of mine\n",
        }
        md = self.home / "CLAUDE.md"
        for name, layout in layouts.items():
            with self.subTest(layout=name):
                text = layout.format(BEGIN=BEGIN, END=END)
                md.write_text(text, encoding="utf-8")
                for tool in (self._run, self._uninstall):
                    res = tool()
                    self.assertNotEqual(res.returncode, 0, f"{tool.__name__}: {res.stdout}{res.stderr}")
                    self.assertEqual(md.read_text(encoding="utf-8"), text, tool.__name__)

    def test_a_stray_end_marker_with_no_block_is_refused(self):
        md = self.home / "CLAUDE.md"
        for eol in ("\n", "\r\n"):
            text = f"# mine{eol}{END}{eol}tail{eol}"
            md.write_bytes(text.encode("utf-8"))
            for tool in (self._run, self._uninstall):
                res = tool()
                self.assertNotEqual(res.returncode, 0, f"{tool.__name__}: {res.stdout}{res.stderr}")
                self.assertEqual(md.read_bytes(), text.encode("utf-8"), tool.__name__)

    def test_two_well_formed_blocks_still_collapse_to_one(self):
        md = self.home / "CLAUDE.md"
        md.write_text(f"# mine\n{BEGIN}\n- a\n{END}\nmiddle\n{BEGIN}\n- b\n{END}\ntail\n", encoding="utf-8")
        self._ok()
        text = md.read_text(encoding="utf-8")
        self.assertEqual(text.count(BEGIN), 1)
        self.assertIn("middle", text)
        self.assertIn("tail", text)

    def test_concurrent_installs_leave_a_whole_installation(self):
        """Two runs at once (a manual install while an update runs 036) must not destroy each other's work."""
        self._legacy_home()
        installer = self.repo / "integrations/claude-code/install.sh"
        procs = [subprocess.Popen(["bash", str(installer)], cwd=str(self.repo),  # portability-ok: invoked through bash, never by the executable bit
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  env=self._env()) for _ in range(4)]
        outs = [(p.wait(timeout=120), p.stdout.read().decode("utf-8", "replace")) for p in procs]
        for p in procs:
            p.stdout.close()
        self.assertTrue(any(rc == 0 for rc, _ in outs), outs)
        for rc, out in outs:
            if rc != 0:
                self.assertIn("another install", out)
        built = self.repo / "integrations/claude-code/built/rules/minder-memory.md"
        self.assertTrue(built.is_file())
        for name in HOT:
            self.assertTrue((self.home / "minder-memory" / name).exists(), name)
        self.assertEqual([p.name for p in (self.repo / "integrations/claude-code").iterdir()
                          if p.name.startswith("built.")], [])
        self._ok()

    def test_a_lock_left_by_a_dead_run_is_taken_over(self):
        lock = self.home / ".minder-memory-install.lock"
        lock.mkdir()
        (lock / "owner").write_text("999999 dead-run-token\n", encoding="utf-8")
        self._ok()
        self.assertFalse(lock.exists())

    def test_many_runs_racing_for_a_dead_runs_lock_leave_a_whole_installation(self):
        """Every contender sees the same dead holder; only one may take the lock over."""
        lock = self.home / ".minder-memory-install.lock"
        self._legacy_home()
        lock.mkdir()
        (lock / "owner").write_text("999999 dead-run-token\n", encoding="utf-8")
        installer = self.repo / "integrations/claude-code/install.sh"
        procs = [subprocess.Popen(["bash", str(installer)], cwd=str(self.repo),  # portability-ok: invoked through bash, never by the executable bit
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  env=self._env()) for _ in range(6)]
        outs = [(p.wait(timeout=180), p.stdout.read().decode("utf-8", "replace")) for p in procs]
        for p in procs:
            p.stdout.close()
        self.assertTrue(any(rc == 0 for rc, _ in outs), outs)
        for rc, out in outs:
            if rc != 0:
                self.assertIn("another install", out)
        self.assertFalse(lock.exists(), "the last owner releases the lock")
        self.assertEqual([p.name for p in self.home.iterdir() if ".lock" in p.name], [])
        self.assertTrue((self.repo / "integrations/claude-code/built/rules/minder-memory.md").is_file())
        self._ok()

    def test_a_live_holders_lock_is_never_removed_by_a_refused_run(self):
        lock = self.home / ".minder-memory-install.lock"
        lock.mkdir()
        (lock / "owner").write_text(f"{os.getpid()} live-token\n", encoding="utf-8")
        for tool in (self._run, self._uninstall):
            res = tool()
            self.assertNotEqual(res.returncode, 0, tool.__name__)
            self.assertIn("another install", res.stdout + res.stderr)
            self.assertEqual((lock / "owner").read_text(encoding="utf-8"), f"{os.getpid()} live-token\n")

    def test_uninstall_holds_the_lock_while_it_works(self):
        self._ok()
        res = self._uninstall()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("lock", (self.repo / "integrations/claude-code/uninstall.sh").read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".minder-memory-install.lock").exists())

    def test_an_orphan_stage_under_a_reused_pid_is_never_published(self):
        """A live pid proves nothing about who left a stage; this run renders into a fresh one."""
        orphan = self.repo / f"integrations/claude-code/built.new.{os.getpid()}-1-1"
        _write(orphan, "commands/minder/mem/removed-long-ago.md", "stale\n")
        _write(orphan, "rules/minder-memory.md", "stale rule\n")
        self._ok()
        built = self.repo / "integrations/claude-code/built"
        self.assertFalse((built / "commands/minder/mem/removed-long-ago.md").exists())
        self.assertNotIn("stale", (built / "rules/minder-memory.md").read_text(encoding="utf-8"))
        shutil.rmtree(orphan)

    def test_uninstall_with_no_harness_home_does_nothing(self):
        shutil.rmtree(self.home)
        res = self._uninstall()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(self.home.exists(), "uninstall must not create the home it is removing from")

    def test_staging_of_a_live_run_is_not_cleaned_up(self):
        live = self.repo / f"integrations/claude-code/built.new.{os.getpid()}-1-1"
        dead = self.repo / "integrations/claude-code/built.new.999999-1-1"
        live.mkdir(parents=True); dead.mkdir(parents=True)
        self._ok()
        self.assertTrue(live.is_dir(), "another live process's staging is not ours to delete")
        self.assertFalse(dead.exists())
        live.rmdir()

    def test_rendering_leaves_no_staging_directory_behind(self):
        self._ok()
        siblings = sorted(p.name for p in (self.repo / "integrations/claude-code").iterdir())
        self.assertIn("built", siblings)
        self.assertEqual([n for n in siblings if n.startswith("built") and n != "built"], [])

    # -- uninstall --------------------------------------------------------- #

    def _uninstall(self, *, failing_awk: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.repo / "integrations/claude-code/uninstall.sh")],  # portability-ok: invoked through bash, never by the executable bit
                              capture_output=True, text=True, encoding="utf-8",
                              env=self._env(failing_awk=failing_awk))

    def test_uninstall_that_cannot_strip_the_block_keeps_what_it_imports(self):
        """Removing the files first and then failing on the block left every session importing nothing."""
        self._ok()
        before = (self.home / "CLAUDE.md").read_text(encoding="utf-8")
        res = self._uninstall(failing_awk=True)
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual((self.home / "CLAUDE.md").read_text(encoding="utf-8"), before)
        self.assertEqual(len(list((self.home / "minder-memory").iterdir())), len(HOT))

    def test_uninstall_removes_the_directory_it_made(self):
        self._ok()
        self.assertTrue((self.home / "minder-memory").is_dir(), "precondition: install made it")
        res = self._uninstall()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(os.path.lexists(self.home / "minder-memory"))
        self.assertNotIn(BEGIN, (self.home / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_uninstall_keeps_a_file_someone_else_put_there(self):
        self._ok()
        self.assertEqual(len(list((self.home / "minder-memory").iterdir())), len(HOT),
                         "precondition: install made it")
        _write(self.home, "minder-memory/mine.md", "mine\n")
        res = self._uninstall()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual([p.name for p in (self.home / "minder-memory").iterdir()], ["mine.md"])


if __name__ == "__main__":
    unittest.main()
