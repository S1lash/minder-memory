"""Integration tests for migration `031-minder-memory-harness-wiring.sh`.

Why this migration needs a suite that EXECUTES it. It is `structural`: it
rewrites the block markers in the owner's own `~/.claude/CLAUDE.md`, deletes
symlinks out of their harness home, re-runs the installer, and rewrites git
remote URLs. Every one of those is a change the owner cannot see happening, and
three of them are destructive. A migration of this shape that succeeds at the
wrong thing is recorded `applied` and never runs again — on this clone or on a
friend's — so only a test that runs the script can catch it.

Safety contract of this suite: `CLAUDE_HOME` is always pointed at a temp
directory, and every git repository involved is created inside a
`TemporaryDirectory`. Nothing here may touch the real `~/.claude` or a real
remote, and there is no network: the "remotes" are local bare repositories
reached over `file://`.
"""
# minder-memory-rebrand: keep-legacy-tokens — this module's inputs are the OLD spelling on purpose.

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"
_LIB = _REPO_ROOT / "scripts" / "lib"

MIGRATION = "031-minder-memory-harness-wiring.sh"
HELPER = "_031_harness_wiring.py"

BEGIN_OLD = "<!-- MINDER-ZTN BEGIN — managed by install.sh, do not edit by hand -->"
END_OLD = "<!-- MINDER-ZTN END -->"
BEGIN_NEW = "<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->"
END_NEW = "<!-- MINDER-MEMORY END -->"

STUB_INSTALL_OK = """#!/usr/bin/env bash
set -euo pipefail
: "${CLAUDE_HOME:?CLAUDE_HOME must reach install.sh}"
mkdir -p "$CLAUDE_HOME"
printf 'installed\\n' > "$CLAUDE_HOME/.install-ran"
echo "[install] stub ok" >&2
"""

STUB_INSTALL_FAIL = """#!/usr/bin/env bash
echo "[install] stub failing" >&2
exit 3
"""


# --------------------------------------------------------------------------- #
# runner + fixtures
# --------------------------------------------------------------------------- #

def _run(mig: Path, *args: str, env: dict[str, str] | None = None,
         cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Execute the migration in a subprocess — the gate's definition of coverage."""
    return subprocess.run(
        ["bash", str(mig), *args],
        capture_output=True, text=True, encoding="utf-8",
        env=env, cwd=str(cwd) if cwd else None,
    )


_GIT_IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # An identity in the environment: a CI runner has none configured, and a
    # commit that silently fails leaves the fixture without the branch every
    # later step fetches.
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, **_GIT_IDENTITY})


def _tree_md5(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        parts = p.relative_to(root).parts
        if ".git" in parts or "__pycache__" in parts:
            continue
        if p.is_symlink():
            out["/".join(parts)] = "symlink:" + os.readlink(p)
        elif p.is_file():
            out["/".join(parts)] = hashlib.md5(p.read_bytes()).hexdigest()
    return out


def _make_bare_remote(dirpath: Path) -> str:
    """A local bare repo with one commit; returns its `file://` URL."""
    work = dirpath.parent / (dirpath.name + ".work")
    work.mkdir(parents=True)
    (work / "README.md").write_text("hi\n", encoding="utf-8")
    _git(work, "init", "-q")
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "Test")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "seed")
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(dirpath)],
                   capture_output=True, text=True)
    shutil.rmtree(work)
    return dirpath.resolve().as_uri()


class EnginePathConvergenceTests(unittest.TestCase):
    """A path only the NEW manifest lists is fetched when the old sync skipped it."""

    def test_missing_engine_path_is_fetched_from_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            up = root / "up"
            up.mkdir()
            (up / "new-thing.md").write_text("shipped\n", encoding="utf-8")
            (up / ".engine-manifest.yml").write_text("version: 1\nengine:\n  - new-thing.md\n", encoding="utf-8")
            _git(up, "init", "-q", "-b", "main")
            _git(up, "add", "-A")
            _git(up, "commit", "-q", "-m", "up")
            clone = root / "clone"
            clone.mkdir()
            (clone / ".engine-manifest.yml").write_text("version: 1\nengine:\n  - new-thing.md\n", encoding="utf-8")
            (clone / "scripts").mkdir()
            shutil.copytree(_REPO_ROOT / "scripts" / "lib", clone / "scripts" / "lib")
            (clone / "scripts" / "migrations").mkdir()
            shutil.copy(_MIGRATIONS / HELPER, clone / "scripts" / "migrations" / HELPER)
            _git(clone, "init", "-q", "-b", "main")
            _git(clone, "add", "-A")
            _git(clone, "commit", "-q", "-m", "clone")
            _git(clone, "remote", "add", "upstream", str(up))
            _git(clone, "fetch", "-q", "upstream", "main")
            sys.path.insert(0, str(clone / "scripts" / "migrations"))
            import importlib
            mod = importlib.import_module(HELPER[:-3])
            res = mod.converge_engine_paths(clone, dry_run=False)
            self.assertEqual(res["missing"], ["new-thing.md"])
            self.assertEqual(res["fetched"], ["new-thing.md"], res)
            self.assertEqual((clone / "new-thing.md").read_text(encoding="utf-8"), "shipped\n")
            self.assertEqual(mod.converge_engine_paths(clone, dry_run=False)["missing"], [])


class Migration031Tests(unittest.TestCase):
    # Literal, not the module constant: the coverage gate reads this out of
    # the syntax tree and only recognises a string constant.
    NAME = "031-minder-memory-harness-wiring.sh"

    # -- fixture ---------------------------------------------------------- #

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "repo"
        self.home = self.tmp / "claude-home"
        self.home.mkdir(parents=True)
        self._build_repo()

    def tearDown(self):
        self._tmp.cleanup()

    def _build_repo(self) -> None:
        (self.root / "scripts" / "migrations").mkdir(parents=True)
        shutil.copytree(_LIB, self.root / "scripts" / "lib")
        (self.root / "integrations" / "claude-code").mkdir(parents=True)
        self._stub_install(STUB_INSTALL_OK)
        # A slice of owner data, so «never touches zettelkasten/» is checkable.
        zk = self.root / "zettelkasten" / "_records" / "observations"
        zk.mkdir(parents=True)
        (zk / "note.md").write_text("ZTN note the migration must not touch\n",
                                    encoding="utf-8")
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "t@example.invalid")
        _git(self.root, "config", "user.name", "Test")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "seed")

    def _stub_install(self, body: str) -> None:
        p = self.root / "integrations" / "claude-code" / "install.sh"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as handle:
            handle.write(body)

    def _migration(self) -> Path:
        """Copy the migration + its helper into the temp repo.

        FAILS (never skips) while they do not exist: the red state of this
        change is «the migration has not been written», and a skip would report
        that as success.
        """
        for name in (MIGRATION, HELPER):
            src = _MIGRATIONS / name
            if not src.is_file():
                self.fail(f"{name} does not exist yet at {src} — write the migration")
            shutil.copy(src, self.root / "scripts" / "migrations" / name)
        return self.root / "scripts" / "migrations" / MIGRATION

    def _env(self, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        env["CLAUDE_HOME"] = str(self.home)
        env.pop("MINDER_MEMORY_ROLES_KEY", None)
        env.pop("ZTN_ROLES_KEY", None)
        env.update(extra)
        return env

    def _go(self, *args: str, **envkw: str) -> subprocess.CompletedProcess:
        mig = self._migration()
        return _run(mig, *args, env=self._env(**envkw), cwd=self.root)

    # -- Step A: the CLAUDE.md block markers ------------------------------- #

    def _write_claude_md(self, begin: str, end: str) -> str:
        body = (
            "# My harness\n\n"
            "Some line the owner wrote.\n"
            f"{begin}\n"
            "@/path/to/base/rules/thing.md\n"
            f"{end}\n"
            "Trailing owner line.\n"
        )
        with open(self.home / "CLAUDE.md", "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
        return body

    def test_legacy_markers_are_renamed_and_nothing_else_moves(self):
        before = self._write_claude_md(BEGIN_OLD, END_OLD)
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        after = (self.home / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(after, before.replace(BEGIN_OLD, BEGIN_NEW).replace(END_OLD, END_NEW))
        self.assertNotIn("MINDER-ZTN", after)

    def test_backup_written_before_the_marker_rewrite(self):
        before = self._write_claude_md(BEGIN_OLD, END_OLD)
        self._go()
        backups = sorted(self.home.glob(".minder-memory-backup-*"))
        self.assertTrue(backups, "no backup directory was created before the write")
        # The copy's file name is the migration's to choose; what the contract
        # buys the owner is that the ORIGINAL bytes are recoverable from there.
        copies = [p for b in backups for p in b.rglob("*") if p.is_file()]
        self.assertTrue(copies, "backup directory holds no copy of CLAUDE.md")
        self.assertIn(before, [p.read_text(encoding="utf-8") for p in copies])

    def test_no_legacy_markers_means_no_write_and_no_backup(self):
        """The «does not touch» half — and its sibling above proves it can."""
        before = self._write_claude_md(BEGIN_NEW, END_NEW)
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.home / "CLAUDE.md").read_text(encoding="utf-8"), before)
        self.assertEqual(list(self.home.glob(".minder-memory-backup-*")), [])

    def test_missing_claude_md_is_skipped_not_fatal(self):
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse((self.home / "CLAUDE.md").exists())

    # -- Step B: stale symlinks ------------------------------------------- #

    def _seed_links(self) -> dict[str, Path]:
        """Every symlink shape the rule distinguishes, in one harness home."""
        for sub in ("rules", "commands", "skills", "agents"):
            (self.home / sub).mkdir(parents=True, exist_ok=True)

        live = self.root / "integrations" / "claude-code"
        (live / "rules").mkdir(parents=True, exist_ok=True)
        (live / "skills" / "minder-mem-lint").mkdir(parents=True, exist_ok=True)
        (live / "skills" / "minder-mem-lint" / "SKILL.md").write_text("x\n", encoding="utf-8")
        (live / "rules" / "minder-memory.md").write_text("x\n", encoding="utf-8")

        outside = self.tmp / "elsewhere"
        outside.mkdir(parents=True, exist_ok=True)

        links = {
            # into the repo, legacy basename, target gone -> removed
            "rules/ztn.md": self.root / "integrations/claude-code/rules/ztn.md",
            "rules/ztn-engine-doctrine.md":
                self.root / "integrations/claude-code/rules/ztn-engine-doctrine.md",
            "commands/ztn-recap.md":
                self.root / "integrations/claude-code/commands/ztn-recap.md",
            "commands/ztn-search.md":
                self.root / "integrations/claude-code/commands/ztn-search.md",
            "agents/ztn-role.md": self.root / ".claude/agents/ztn-role.md",
            "skills/ztn-lint": self.root / "integrations/claude-code/skills/ztn-lint",
            # into the repo, current basename, target exists -> kept
            "skills/minder-mem-lint":
                self.root / "integrations/claude-code/skills/minder-mem-lint",
            "rules/minder-memory.md":
                self.root / "integrations/claude-code/rules/minder-memory.md",
            # outside the repo, dangling -> never removed, only reported
            "rules/someone-elses.md": outside / "gone.md",
        }
        for rel, target in links.items():
            link = self.home / rel
            link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(str(target), link)
        return {rel: self.home / rel for rel in links}

    def test_stale_repo_links_removed_and_live_ones_kept(self):
        links = self._seed_links()
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)

        for rel in ("rules/ztn.md", "rules/ztn-engine-doctrine.md",
                    "commands/ztn-recap.md", "commands/ztn-search.md",
                    "agents/ztn-role.md", "skills/ztn-lint"):
            self.assertFalse(links[rel].is_symlink(), f"{rel} should have been removed")
        # siblings: what must survive
        for rel in ("skills/minder-mem-lint", "rules/minder-memory.md"):
            self.assertTrue(links[rel].is_symlink(), f"{rel} must be kept")

    def test_dangling_link_outside_the_repo_is_reported_not_removed(self):
        links = self._seed_links()
        res = self._go("--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(links["rules/someone-elses.md"].is_symlink(),
                        "a link outside the repo must never be removed")
        payload = json.loads(res.stdout)
        reported = " ".join(str(x) for x in payload["links_reported"])
        self.assertIn("someone-elses.md", reported)
        # sibling: the removals are reported separately and are non-empty
        self.assertTrue(payload["links_removed"])

    # -- Step C: install.sh ------------------------------------------------ #

    def test_install_is_run_with_claude_home_inherited(self):
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((self.home / ".install-ran").is_file(),
                        "install.sh did not run with CLAUDE_HOME pointing at the temp home")

    def test_failing_install_aborts_the_migration(self):
        """Structural: a broken install must not be reported as a completed update."""
        self._stub_install(STUB_INSTALL_FAIL)
        res = self._go()
        self.assertNotEqual(res.returncode, 0)

    def test_failing_install_names_the_manual_recovery_command(self):
        """An abort the owner cannot act on is an abort they will ignore."""
        self._stub_install(STUB_INSTALL_FAIL)
        res = self._go()
        self.assertIn("integrations/claude-code/install.sh", res.stderr)

    # -- Step D: git remotes ---------------------------------------------- #

    def _remote(self, name: str, url: str) -> None:
        _git(self.root, "remote", "add", name, url)

    def _url(self, name: str) -> str:
        return _git(self.root, "remote", "get-url", name).stdout.strip()

    def test_remote_rewritten_when_the_new_url_exists(self):
        remotes = self.tmp / "remotes"
        remotes.mkdir()
        old = _make_bare_remote(remotes / "minder-ztn.git")
        _make_bare_remote(remotes / "minder-memory.git")
        self._remote("origin", old)
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self._url("origin").endswith("minder-memory.git"),
                        f"origin is still {self._url('origin')}")

    def test_remote_left_alone_when_the_new_url_does_not_resolve(self):
        remotes = self.tmp / "remotes"
        remotes.mkdir()
        old = _make_bare_remote(remotes / "minder-ztn.git")   # no minder-memory.git
        self._remote("origin", old)
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._url("origin"), old)
        self.assertIn("git remote set-url", res.stdout)

    def test_remote_qualifies_by_url_not_by_name(self):
        remotes = self.tmp / "remotes"
        remotes.mkdir()
        old = _make_bare_remote(remotes / "minder-ztn.git")
        _make_bare_remote(remotes / "minder-memory.git")
        self._remote("upstream", old)
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self._url("upstream").endswith("minder-memory.git"))

    def test_lookalike_last_segment_is_not_rewritten(self):
        """`minder-ztn-alice` is somebody's fork name, not our repository."""
        remotes = self.tmp / "remotes"
        remotes.mkdir()
        old = _make_bare_remote(remotes / "minder-ztn-alice.git")
        _make_bare_remote(remotes / "minder-memory-alice.git")
        self._remote("origin", old)
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._url("origin"), old)

    # -- Step E: the digest ------------------------------------------------ #

    def test_digest_names_the_new_surfaces_and_the_env_fallback(self):
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        out = res.stdout + res.stderr
        for token in ("/minder:mem:update", "MINDER_MEMORY_BASE",
                      "MINDER_MEMORY_ROLES_KEY", "ZTN_ROLES_KEY"):
            self.assertIn(token, out, f"digest does not mention {token}")

    def test_digest_never_prints_a_credential_value(self):
        secret = "supersecretvalue123"
        res = self._go(MINDER_MEMORY_ROLES_KEY=secret)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn(secret, res.stdout)
        self.assertNotIn(secret, res.stderr)

    # -- flags -------------------------------------------------------------- #

    def test_dry_run_changes_nothing(self):
        self._write_claude_md(BEGIN_OLD, END_OLD)
        self._seed_links()
        remotes = self.tmp / "remotes"
        remotes.mkdir()
        old = _make_bare_remote(remotes / "minder-ztn.git")
        _make_bare_remote(remotes / "minder-memory.git")
        self._remote("origin", old)

        before = _tree_md5(self.home)
        res = self._go("--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(before, _tree_md5(self.home))
        self.assertEqual(self._url("origin"), old)
        self.assertFalse((self.home / ".install-ran").exists(),
                         "a dry run must not run install.sh")
        # sibling: it still says what it would have done
        out = res.stdout + res.stderr
        self.assertIn(str(self.home / "CLAUDE.md"), out)
        self.assertIn("minder-memory.git", out)

    def test_json_report_shape(self):
        self._write_claude_md(BEGIN_OLD, END_OLD)
        self._seed_links()
        res = self._go("--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        for key in ("markers", "links_removed", "links_reported", "install_rc", "remotes"):
            self.assertIn(key, payload)
        self.assertEqual(payload["install_rc"], 0)

    # -- invariants --------------------------------------------------------- #

    def test_idempotent(self):
        self._write_claude_md(BEGIN_OLD, END_OLD)
        self._seed_links()
        remotes = self.tmp / "remotes"
        remotes.mkdir()
        old = _make_bare_remote(remotes / "minder-ztn.git")
        _make_bare_remote(remotes / "minder-memory.git")
        self._remote("origin", old)

        first = self._go()
        self.assertEqual(first.returncode, 0, first.stderr)
        after_first = _tree_md5(self.home)
        url_first = self._url("origin")

        second = self._go()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(after_first, _tree_md5(self.home))
        self.assertEqual(url_first, self._url("origin"))

    def test_owner_data_never_modified(self):
        self._write_claude_md(BEGIN_OLD, END_OLD)
        self._seed_links()
        before = _tree_md5(self.root / "zettelkasten")
        res = self._go()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(before, _tree_md5(self.root / "zettelkasten"))

    def test_declared_kind_is_structural(self):
        """The header the runner reads decides whether a failure aborts the update."""
        mig = self._migration()
        head = mig.read_text(encoding="utf-8").splitlines()[:5]
        self.assertTrue(any("migration-kind: structural" in line for line in head),
                        f"no `# migration-kind: structural` header in:\n{head}")


if __name__ == "__main__":
    unittest.main()
