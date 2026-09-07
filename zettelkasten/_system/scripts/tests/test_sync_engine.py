"""End-to-end tests for `scripts/sync_engine.sh` — the engine update channel.

Every test here pins a failure that was real, and each shares one shape: the
update reported success while doing nothing, or refused to proceed on exactly
the clone it was supposed to rescue. A channel whose failure looks like its
success is worse than one that is simply broken, because nobody goes looking.

The upstream in these tests is a tiny hand-built repo rather than a real
release: what is under test is the script's control flow, not the manifest's
contents.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_SCRIPTS = _REPO_ROOT / "scripts"

# The sync runs the REAL migration chain inside the temp clone, and a migration
# that re-wires the Claude Code home (031) reads `CLAUDE_HOME`. Left unset it
# would reach the developer's own `~/.claude` from a test — so every run here
# gets a throwaway home of its own.
_HOME_TMP = __import__("tempfile").TemporaryDirectory(prefix="sync-engine-home-")

_ENV = {
    **os.environ,
    "CLAUDE_HOME": _HOME_TMP.name,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}

_MANIFEST = textwrap.dedent(
    """\
    version: 1

    engine:
      - .engine-manifest.yml
      - integrations/VERSION
      - scripts/
      - engine-doc.md

    template: []

    exclude: []
    """
)


# What a clone at 0.65 / 0.69 carries as its own `sync_engine.sh`: a self-heal
# that restores `scripts/` from the remote and re-execs the RESTORED script
# WITHOUT passing the flag on. Everything the new script does inside its own
# self-heal branch is therefore unreachable from here — which is the whole
# point of this fixture.
_OLD_STYLE_SELF_HEAL = """#!/usr/bin/env bash
set -euo pipefail
REMOTE="upstream"
BRANCH="main"
SELF_HEAL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --self-heal) SELF_HEAL=1 ;;
    --remote) REMOTE="$2"; shift ;;
    --branch) BRANCH="$2"; shift ;;
    *) ;;
  esac
  shift
done
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
if [ $SELF_HEAL -eq 1 ]; then
  git fetch "$REMOTE" "$BRANCH"
  git checkout "$REMOTE/$BRANCH" -- scripts/
  exec bash "$REPO_ROOT/scripts/sync_engine.sh" --remote "$REMOTE" --branch "$BRANCH"
fi
echo "[old] this stub implements nothing but the self-heal" >&2
exit 2
"""


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8", env=_ENV
    )


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "scripts/sync_engine.sh", *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=_ENV,
    )


def _seed_upstream(tmp: Path, version: str = "1.0.2") -> Path:
    up = tmp / "upstream"
    (up / "integrations").mkdir(parents=True)
    (up / "integrations" / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (up / "engine-doc.md").write_text("current\n", encoding="utf-8")
    # `__pycache__` is regenerated with different bytes the moment python runs,
    # which would make `scripts/` legitimately dirty and abort every sync here.
    shutil.copytree(_SCRIPTS, up / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (up / ".engine-manifest.yml").write_text(_MANIFEST, encoding="utf-8")
    _git(up, "init", "-q", "-b", "main")
    _git(up, "add", "-A")
    _git(up, "commit", "-q", "-m", "engine")
    return up


def _clone(tmp: Path, up: Path, *, version: str) -> Path:
    clone = tmp / "clone"
    subprocess.run(["git", "clone", "-q", str(up), str(clone)], check=True, env=_ENV)
    _git(clone, "remote", "rename", "origin", "upstream")
    (clone / "integrations" / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (clone / "engine-doc.md").write_text("stale\n", encoding="utf-8")
    _git(clone, "commit", "-q", "-am", "older engine")
    return clone


class SyncEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = __import__("tempfile").TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.up = _seed_upstream(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_clone_below_the_floor_is_refused_with_the_two_step_path(self):
        clone = _clone(self.tmp, self.up, version="0.60.0")
        result = _run(clone)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--self-heal --branch release/0.69.0", result.stderr)
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(), "0.60.0")
        self.assertEqual((clone / "engine-doc.md").read_text(encoding="utf-8"), "stale\n",
                         "a refused sync must not have applied anything")

    def test_a_refused_update_leaves_no_file_the_self_heal_added(self):
        """A friend below the floor runs the skill, which self-heals from the
        current branch first; the refusal must not leave the floor release's
        sync facing files it does not have (it would refuse the tree as dirty)."""
        _git(self.up, "branch", "release/0.69.0")
        clone = _clone(self.tmp, self.up, version="0.60.0")
        _git(clone, "rm", "-q", "scripts/lib/version_floor.py")
        # ...and an older copy of something the restore will overwrite, so the
        # refusal has MODIFIED files to put back and not only added ones.
        (clone / "scripts" / "manifest_paths.py").write_text(
            "# the older release's copy\n", encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-q", "-m", "an engine that predates the floor")
        result = _run(clone, "--self-heal")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(_git(clone, "status", "--porcelain", "--", "scripts/lib/version_floor.py").stdout, "")
        self.assertFalse((clone / "scripts" / "lib" / "version_floor.py").exists())
        # «Leave the tree as it was found» has to mean the MODIFIED files too.
        # Removing only what the self-heal added leaves the rest of `scripts/`
        # carrying the newer release, so the floor release's own sync refuses
        # the tree as dirty — and the two-step path never gets past step one.
        left = [line for line in
                _git(clone, "status", "--porcelain", "--", "scripts/").stdout.splitlines()
                if line.strip() and "__pycache__" not in line
                and "scripts/sync_engine.sh" not in line]
        self.assertEqual(left, [], "a refused update must leave scripts/ as it found it")
        step_one = _run(clone, "--self-heal", "--branch", "release/0.69.0")
        self.assertEqual(step_one.returncode, 0, step_one.stdout + step_one.stderr)

    def test_the_floor_branch_itself_is_the_first_step_and_is_not_refused(self):
        _git(self.up, "branch", "release/0.69.0")
        clone = _clone(self.tmp, self.up, version="0.60.0")
        result = _run(clone, "--self-heal", "--branch", "release/0.69.0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((clone / "engine-doc.md").read_text(encoding="utf-8"), "current\n")

    def test_ordinary_sync_applies_and_moves_the_version(self):
        clone = _clone(self.tmp, self.up, version="0.69.0")
        result = _run(clone)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(),
                         "1.0.2")
        self.assertEqual((clone / "engine-doc.md").read_text(encoding="utf-8"), "current\n")
        self.assertIn("0.69.0 → 1.0.2", result.stdout)

    def test_a_path_added_upstream_lands_on_the_same_update(self):
        """The engine list is read from the manifest the sync is ABOUT TO APPLY.

        Read from the clone's own copy, a path that exists only in the new
        manifest was never walked — and `retire_paths.py`, which reads the
        manifest after checkout, had already removed its predecessor. A
        renamed component then vanished from every clone on its first update.
        """
        clone = _clone(self.tmp, self.up, version="0.69.0")
        # Upstream gains a new engine path AND retires an old one in one release.
        (self.up / "new-doc.md").write_text("added upstream\n", encoding="utf-8")
        (self.up / ".engine-manifest.yml").write_text(
            _MANIFEST.replace("  - engine-doc.md\n", "  - engine-doc.md\n  - new-doc.md\n")
            + "\nretired:\n  - old-doc.md\n",
            encoding="utf-8",
        )
        _git(self.up, "add", "-A")
        _git(self.up, "commit", "-q", "-m", "add new-doc, retire old-doc")
        (clone / "old-doc.md").write_text("to be retired\n", encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-q", "-m", "clone carries the old doc")

        result = _run(clone)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((clone / "new-doc.md").read_text(encoding="utf-8"), "added upstream\n",
                         "a path listed only in the upstream manifest must be fetched")
        self.assertFalse((clone / "old-doc.md").exists(), "the retired predecessor is removed")

    def test_dry_run_lists_the_upstream_manifest_paths_without_touching_the_tree(self):
        clone = _clone(self.tmp, self.up, version="0.69.0")
        (self.up / "new-doc.md").write_text("added upstream\n", encoding="utf-8")
        (self.up / ".engine-manifest.yml").write_text(
            _MANIFEST.replace("  - engine-doc.md\n", "  - engine-doc.md\n  - new-doc.md\n"),
            encoding="utf-8",
        )
        _git(self.up, "add", "-A")
        _git(self.up, "commit", "-q", "-m", "add new-doc")
        result = _run(clone, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("new-doc.md", result.stdout)
        self.assertFalse((clone / "new-doc.md").exists())
        dirty = [l for l in _git(clone, "status", "--porcelain").stdout.splitlines()
                 if "__pycache__" not in l]
        self.assertEqual(dirty, [])

    def test_a_sync_that_resolves_nothing_fails_loudly(self):
        """The Windows failure: a mangled path list read as 'absent upstream'.

        Simulated at the boundary it actually broke — the manifest reader's
        stdout, which on Git Bash carried a trailing `\\r` on every line.
        """
        clone = _clone(self.tmp, self.up, version="0.69.0")
        reader = clone / "scripts" / "manifest_paths.py"
        src = reader.read_text(encoding="utf-8")
        src = src.replace(
            '    emit_lines(p.rstrip("/") for p in paths)',
            '    for _p in paths:\n'
            '        sys.stdout.write(_p.rstrip("/") + "\\r\\n")',
        )
        with open(reader, "w", encoding="utf-8", newline="") as handle:
            handle.write(src)
        _git(clone, "commit", "-q", "-am", "simulate Git Bash CRLF")

        result = _run(clone)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not one of the", result.stderr)
        self.assertIn("--self-heal", result.stderr)
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(),
                         "0.69.0", "a failed sync must not claim a version it did not apply")

    def test_self_heal_recovers_a_clone_with_no_shared_lib(self):
        """A clone old enough to need recovering PREDATES `scripts/lib/`.

        Sourcing the library at the top of the script killed it on line one —
        on exactly the clone the recovery path exists for.
        """
        clone = _clone(self.tmp, self.up, version="0.69.0")
        shutil.rmtree(clone / "scripts" / "lib")
        _git(clone, "commit", "-q", "-am", "pre-lib clone")

        plain = _run(clone)
        self.assertEqual(plain.returncode, 2)
        self.assertIn("--self-heal", plain.stderr,
                      "the refusal must name the way out, not just fail")

        healed = _run(clone, "--self-heal")
        self.assertEqual(healed.returncode, 0, healed.stderr)
        self.assertTrue((clone / "scripts" / "lib" / "git.sh").is_file())
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(),
                         "1.0.2")

    def test_self_heal_removes_what_upstream_deleted_under_scripts(self):
        """A restore that only COPIES leaves the clone permanently un-syncable.

        `git checkout <ref> -- scripts/` writes what upstream has and says
        nothing about what upstream dropped, so a retired migration and its
        helpers stay in the tree. `scripts/` then differs from upstream
        forever, the dirty guard refuses it on every run, and the clone that
        the recovery path exists for is exactly the one it cannot rescue.
        """
        clone = _clone(self.tmp, self.up, version="0.69.0")
        # Something the restore must change, so `scripts/` is dirty vs HEAD...
        shutil.rmtree(clone / "scripts" / "lib")
        # ...and something upstream no longer has, so it is not identical to
        # upstream either — which is the deadlock.
        (clone / "scripts" / "migrations").mkdir(parents=True, exist_ok=True)
        (clone / "scripts" / "migrations" / "002-retired-upstream.sh").write_text(
            "# a migration upstream deleted\n", encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-q", "-m", "a clone carrying retired migrations")

        healed = _run(clone, "--self-heal")
        self.assertEqual(healed.returncode, 0, healed.stdout + healed.stderr)
        self.assertFalse((clone / "scripts" / "migrations" / "002-retired-upstream.sh").exists(),
                         "a path upstream deleted must not survive the restore")
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(),
                         "1.0.2", "the first --self-heal run must reach the upstream version")

    def _clone_carrying_a_retired_file(self) -> Path:
        """A clone whose `scripts/` differs from upstream in BOTH directions.

        `lib/` removed so the restore has something to write, and a migration
        upstream has since deleted so the restore has something to remove. Only
        the second one is invisible to a copy-only restore.
        """
        clone = _clone(self.tmp, self.up, version="0.69.0")
        shutil.rmtree(clone / "scripts" / "lib")
        (clone / "scripts" / "migrations").mkdir(parents=True, exist_ok=True)
        (clone / "scripts" / "migrations" / "002-retired-upstream.sh").write_text(
            "# a migration upstream deleted\n", encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-q", "-m", "an old clone carrying retired migrations")
        return clone

    def test_a_plain_sync_clears_what_upstream_deleted_under_scripts(self):
        """The convergence has to run on the ORDINARY path, not inside --self-heal.

        An old clone runs its own updater, whose self-heal restores `scripts/`
        and re-execs the restored script WITHOUT the flag. Everything guarded by
        `--self-heal` in the new script is therefore unreachable from the only
        clone that needs it, and the repaired script meets the dirty guard with
        the stale files still in place. This test enters at exactly that point.
        """
        clone = self._clone_carrying_a_retired_file()
        # Precisely what the old self-heal leaves behind before it re-execs.
        subprocess.run(["git", "checkout", "upstream/main", "--", "scripts/"],
                       cwd=clone, check=True, env=_ENV)

        result = _run(clone)          # PLAIN sync — no --self-heal
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((clone / "scripts" / "migrations" / "002-retired-upstream.sh").exists())
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(),
                         "1.0.2")

    def test_an_old_clones_own_self_heal_reaches_the_new_version(self):
        """End to end from the version the recovery exists for."""
        clone = self._clone_carrying_a_retired_file()
        (clone / "scripts" / "sync_engine.sh").write_text(_OLD_STYLE_SELF_HEAL, encoding="utf-8")
        _git(clone, "commit", "-q", "-am", "the updater this clone actually carries")

        result = _run(clone, "--self-heal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((clone / "scripts" / "migrations" / "002-retired-upstream.sh").exists())
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(),
                         "1.0.2")

    def test_the_closing_block_names_the_self_check_before_the_commit(self):
        """A friend on the CLI is never told the self-check exists.

        The skill runs it for them; the script's own closing block was the only
        place a script user would learn of it, and it said nothing. Order
        matters: check first, then commit — a commit made before the check is a
        commit of whatever the update got wrong.
        """
        clone = _clone(self.tmp, self.up, version="0.69.0")
        result = _run(clone)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("python3 scripts/check_update.py", result.stdout)
        self.assertIn("git add -A && git commit", result.stdout)
        self.assertLess(result.stdout.index("check_update.py"),
                        result.stdout.index("git add -A"),
                        "the check belongs above the commit, not after it")

    def test_the_dirty_guard_says_to_commit_scripts_alone(self):
        """A friend told only «commit or stash» commits their notes with it."""
        clone = _clone(self.tmp, self.up, version="0.69.0")
        (clone / "engine-doc.md").write_text("my own edit\n", encoding="utf-8")
        result = _run(clone)
        self.assertEqual(result.returncode, 2)
        self.assertIn("git add scripts && git commit", result.stderr)
        self.assertIn("your notes must not go into that commit", result.stderr)

    def test_a_path_dirty_but_identical_to_upstream_is_not_an_abort(self):
        """Otherwise the self-heal deadlocks against the script's own dirty check."""
        clone = _clone(self.tmp, self.up, version="0.69.0")
        subprocess.run(["git", "checkout", "upstream/main", "--", "engine-doc.md"],
                       cwd=clone, check=True, env=_ENV)
        result = _run(clone)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_real_local_customisation_still_aborts(self):
        clone = _clone(self.tmp, self.up, version="0.69.0")
        (clone / "engine-doc.md").write_text("my own edit\n", encoding="utf-8")
        result = _run(clone)
        self.assertEqual(result.returncode, 2)
        self.assertIn("uncommitted changes", result.stderr)

    def test_dry_run_changes_nothing(self):
        clone = _clone(self.tmp, self.up, version="0.69.0")
        result = _run(clone, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((clone / "integrations" / "VERSION").read_text(encoding="utf-8").strip(),
                         "0.69.0")


if __name__ == "__main__":
    unittest.main()
