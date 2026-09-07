"""Tests for the shared engine primitives under `scripts/lib/`.

These exist because each concern here was previously re-derived at every call
site and got it wrong in the same way at several of them — LF-forcing on the
shell boundary, the `exclude:` subtraction, branch identity. A shared owner is
only an improvement if the owner is pinned.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib import manifest as lm  # noqa: E402
from lib import portable as lp  # noqa: E402
import retire_paths as rp  # noqa: E402


class PortableTests(unittest.TestCase):
    def test_emit_lines_writes_lf_only(self):
        """The whole point: a `\\r` here fails every path a shell builds from it."""
        buf = io.StringIO()
        real, sys.stdout = sys.stdout, buf
        try:
            lp.emit_lines(["a/b", "c d", "кириллица"])
        finally:
            sys.stdout = real
        self.assertEqual(buf.getvalue(), "a/b\nc d\nкириллица\n")
        self.assertNotIn("\r", buf.getvalue())

    def test_emit_lines_does_not_strip_or_quote(self):
        buf = io.StringIO()
        real, sys.stdout = sys.stdout, buf
        try:
            lp.emit_lines(["  padded  "])
        finally:
            sys.stdout = real
        self.assertEqual(buf.getvalue(), "  padded  \n")

    def test_configure_stream_tolerates_a_stream_without_reconfigure(self):
        lp.configure_stream(io.StringIO())  # must not raise

    def test_write_text_utf8_stores_lf_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.sh"
            lp.write_text_utf8(p, "a\nb\n")
            self.assertEqual(p.read_bytes(), b"a\nb\n")

    def test_read_text_utf8_is_utf8_regardless_of_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.md"
            p.write_bytes("тире — em dash\n".encode("utf-8"))
            self.assertEqual(lp.read_text_utf8(p), "тире — em dash\n")

    def test_read_text_utf8_default_covers_a_missing_file(self):
        self.assertEqual(lp.read_text_utf8(Path("/nope/nope.md"), default="!"), "!")


class ManifestTests(unittest.TestCase):
    def test_lite_matches_yaml_on_every_list_section(self):
        """Two readers exist only because the scheduler sandbox has no PyYAML.

        They must never disagree about what ships.
        """
        root = lm.repo_root()
        full = lm.load_manifest(root)
        path = root / ".engine-manifest.yml"
        for section in lm.LIST_SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    lm.read_section_lite(path, section),
                    [str(x) for x in (full.get(section) or [])],
                )

    def test_read_section_lite_rejects_a_non_list_section(self):
        with self.assertRaises(ValueError):
            lm.read_section_lite(lm.repo_root() / ".engine-manifest.yml", "version")

    def test_scan_targets_subtracts_exclude(self):
        """The bug this fixes: excluding a file had no observable effect."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "keep.py").write_text("x\n", encoding="utf-8")
            (root / "scripts" / "personal.py").write_text("x\n", encoding="utf-8")
            manifest = {"engine": ["scripts/"], "exclude": ["scripts/personal.py"]}

            names = {p.name for p in lm.scan_targets(root, manifest)}
            self.assertEqual(names, {"keep.py"})

    def test_scan_targets_skips_a_manifested_path_that_does_not_exist_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {"engine": ["integrations/VERSION"]}
            self.assertEqual(lm.scan_targets(root, manifest), [])

    def test_expand_paths_can_return_every_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "d").mkdir()
            (root / "d" / "a.png").write_bytes(b"\x89PNG")
            (root / "d" / "b.md").write_text("x\n", encoding="utf-8")
            self.assertEqual(
                {p.name for p in lm.expand_paths(root, ["d/"], suffixes=None)},
                {"a.png", "b.md"},
            )
            self.assertEqual({p.name for p in lm.expand_paths(root, ["d/"])}, {"b.md"})


class GitShellLibTests(unittest.TestCase):
    """`scripts/lib/git.sh` — sourced by every scheduler script."""

    LIB = REPO_ROOT / "scripts" / "lib" / "git.sh"

    def _run(self, snippet: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f'. "{self.LIB}"; {snippet}'],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
        )

    def test_is_branch_name_rejects_every_non_branch_value(self):
        for value in ("", "DETACHED", "HEAD"):
            with self.subTest(value=value):
                self.assertNotEqual(
                    self._run(f'git_is_branch_name "{value}"').returncode, 0
                )

    def test_is_branch_name_accepts_a_real_branch(self):
        for value in ("main", "claude/admiring-shannon-ETCE3"):
            with self.subTest(value=value):
                self.assertEqual(self._run(f'git_is_branch_name "{value}"').returncode, 0)

    def test_current_branch_or_falls_back(self):
        out = self._run('cd /tmp && git_current_branch_or DETACHED')
        self.assertEqual(out.stdout.strip(), "DETACHED")
        self.assertEqual(out.returncode, 0)

    def test_syntax_is_bash_3_2_clean(self):
        """macOS ships bash 3.2 — the library must parse there."""
        self.assertEqual(
            subprocess.run(["/bin/bash", "-n", str(self.LIB)]).returncode, 0
        )


class RetirementTests(unittest.TestCase):
    """`retired:` is how a REMOVAL reaches the people running the engine.

    A sync copies what upstream has; a path upstream no longer has is never
    walked, so it stays on the clone forever. Every removal the engine ever
    made is still present on every clone that predates it — dead modules
    beside live ones, dead tests pytest still collects, a dead log that reads
    as one that stopped updating.
    """

    def test_the_manifests_retired_paths_are_all_gone_from_this_repo(self):
        """A path listed as retired and still present here means the removal
        was never finished on the authoring side — friends would then be told
        to delete something the maintainer still ships."""
        manifest = lm.load_manifest(REPO_ROOT)
        still_here = [
            path for path in (manifest.get("retired") or [])
            if (REPO_ROOT / path).exists()
        ]
        self.assertEqual(still_here, [], "retired but still shipped")

    def test_a_retired_path_inside_owner_space_is_refused(self):
        """THE guard. `exclude:` is the manifest's own enumeration of owner
        space, and a sweep must never delete from it — an owner-produced
        artifact is retired by a migration that explains itself, if at all."""
        offending = rp.guard(
            ["zettelkasten/_records/meetings/20260101-meeting-x.md"],
            ["zettelkasten/_records/meetings/"],
        )
        self.assertEqual(offending, ["zettelkasten/_records/meetings/20260101-meeting-x.md"])

    def test_the_live_manifest_lists_nothing_inside_owner_space(self):
        """SIBLING — the guard fires on the real manifest, not just a fixture."""
        manifest = lm.load_manifest(REPO_ROOT)
        self.assertEqual(
            rp.guard(manifest.get("retired") or [], manifest.get("exclude") or []),
            [],
        )

    def test_a_star_entry_covers_subdirs_but_not_files_beside_them(self):
        """`_system/roles/*/` is owner instance dirs; `_run-frame.md` sitting
        beside them is engine. Reading the star as a plain prefix looks
        cautious and is not — it swallows the engine files into owner space,
        and the guard then refuses the whole sweep. Over-covering does not
        fail safe here, it fails shut."""
        star = "zettelkasten/_system/roles/*/"
        self.assertTrue(rp._covered_by(star, "zettelkasten/_system/roles/minder-pm/state/x.md"))
        self.assertFalse(rp._covered_by(star, "zettelkasten/_system/roles/_run-frame.md"))

    def test_retirement_removes_only_what_is_listed_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "zettelkasten/_system/scripts").mkdir(parents=True)
            dead = root / "zettelkasten/_system/scripts/dead.py"
            live = root / "zettelkasten/_system/scripts/live.py"
            dead.write_text("gone\n", encoding="utf-8")
            live.write_text("stays\n", encoding="utf-8")

            listed = ["zettelkasten/_system/scripts/dead.py"]
            self.assertEqual(rp.retire(root, listed)[0], listed)
            self.assertFalse(dead.exists())
            self.assertTrue(live.exists(), "an unlisted neighbour must survive")
            self.assertEqual(rp.retire(root, listed)[0], [], "second run is a no-op")

    def test_dry_run_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            target = root / "a/gone.py"
            target.write_text("x\n", encoding="utf-8")
            self.assertEqual(rp.retire(root, ["a/gone.py"], dry_run=True)[0], ["a/gone.py"])
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()


class RetirementOwnerFileTests(unittest.TestCase):
    """A retired engine directory must never take the owner's files with it.

    The guard used to be «is this file untracked», and the update itself
    defeats it: the closing block tells the owner `git add -A && git commit`,
    so a file of theirs is untracked on the first sync and tracked on the
    second — and on the second the directory was deleted with their file inside.
    A guard that a documented step disarms is not a guard.

    What settles it is the ENGINE's own history: a path the engine ever shipped
    is in the sync remote's log, and a path it never shipped is not, whoever has
    committed it since.
    """
    # minder-memory-rebrand: keep-legacy-tokens

    ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def _git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, encoding="utf-8", env=self.ENV)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        # The engine, as upstream: it ships a subsystem directory.
        self.up = tmp / "upstream"
        (self.up / "scripts" / "old_subsystem").mkdir(parents=True)
        (self.up / "scripts" / "old_subsystem" / "engine_mod.py").write_text(
            "# engine\n", encoding="utf-8")
        (self.up / "scripts" / "old_subsystem" / "engine_two.py").write_text(
            "# engine\n", encoding="utf-8")
        self._git(self.up, "init", "-q", "-b", "main")
        self._git(self.up, "add", "-A")
        self._git(self.up, "commit", "-qm", "the engine ships the subsystem")

        self.root = tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(self.up), str(self.root)],
                       capture_output=True, env=self.ENV)
        self._git(self.root, "remote", "rename", "origin", "upstream")
        self._git(self.root, "fetch", "-q", "upstream", "main")

    def tearDown(self):
        self._tmp.cleanup()

    def _retire(self):
        return rp.retire(self.root, ["scripts/old_subsystem"])

    def test_an_owner_file_inside_keeps_the_directory(self):
        (self.root / "scripts/old_subsystem/my-notes.md").write_text("mine\n", encoding="utf-8")
        removed, kept = self._retire()
        self.assertEqual(removed, [])
        self.assertEqual(len(kept), 1)
        self.assertIn("scripts/old_subsystem/my-notes.md", kept[0][1])
        self.assertNotIn("scripts/old_subsystem/engine_mod.py", kept[0][1],
                         "an engine file is not reported as the owner's")
        self.assertTrue((self.root / "scripts/old_subsystem/my-notes.md").is_file())

    def test_it_still_keeps_after_the_owner_commits_as_instructed(self):
        """The defect: the update's own advice disarmed the guard."""
        (self.root / "scripts/old_subsystem/my-notes.md").write_text("mine\n", encoding="utf-8")
        self._retire()
        self._git(self.root, "add", "-A")
        self._git(self.root, "commit", "-qm", "engine update")

        removed, kept = self._retire()
        self.assertEqual(removed, [], "committing does not make the owner's file the engine's")
        self.assertIn("scripts/old_subsystem/my-notes.md", kept[0][1])
        self.assertTrue((self.root / "scripts/old_subsystem/my-notes.md").is_file())
        self.assertTrue((self.root / "scripts/old_subsystem").is_dir())

    def test_a_directory_of_only_engine_files_is_removed(self):
        removed, kept = self._retire()
        self.assertEqual(removed, ["scripts/old_subsystem"], kept)
        self.assertFalse((self.root / "scripts/old_subsystem").exists())

    def test_an_empty_directory_is_removed(self):
        for stale in (self.root / "scripts/old_subsystem").iterdir():
            stale.unlink()
        self._git(self.root, "add", "-A")
        self._git(self.root, "commit", "-qm", "emptied")
        removed, kept = self._retire()
        self.assertEqual(removed, ["scripts/old_subsystem"], kept)
        self.assertFalse((self.root / "scripts/old_subsystem").exists())

    def test_no_engine_history_keeps_and_says_why(self):
        """Silence is the dangerous answer; «I could not tell» is the safe one."""
        self._git(self.root, "remote", "remove", "upstream")
        removed, kept = self._retire()
        self.assertEqual(removed, [])
        self.assertIsNotNone(kept[0][2])
        self.assertIn("engine history", kept[0][2])
