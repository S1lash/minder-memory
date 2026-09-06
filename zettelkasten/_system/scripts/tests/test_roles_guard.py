"""Tests for roles_guard — the write boundary (CORE-SPEC §3).

Every rule in §3.4 gets a test named after it, plus named SIBLINGS proving the
same check ACCEPTS an unusual-but-legitimate shape. The guard is the only
thing between an autonomous role and the owner's base, so a guard that reverts
a legitimate write is as bad as one that misses a violation — both end with
the owner switching the tick off.

Every test builds its own throwaway git repo in a tmp dir via
`_roles_fixture.init_repo`, drives git through subprocess argument lists, and
leaves `core.quotepath` at its DEFAULT so the `-z` requirement (§3.4 rule 1)
is genuinely exercised rather than configured away. The real repo is never
touched and no test reads the wall clock.

The digest snapshot (§3.1) is what makes attribution real: a path-set
difference loses role B's edit of a file role A created, because git emits the
identical status line. `attribute` is therefore always fed real snapshots from
`capture_snapshot`, never hand-built dicts.

Flatness (§3.5) rides on the prefix: `classify` takes `WritePrefix` objects, so
the guard holds no copy of the inbox path that `roles_config` already owns.
That is why this suite imports `WritePrefix` — the type, not `RoleConfig`;
`check` still takes prefixes, which `test_check_takes_prefixes_not_a_role_config`
keeps honest.

--------------------------------------------------------------------------
REQUIRED FIXTURE DIMENSIONS — read this before adding a test here
--------------------------------------------------------------------------

Three defects reached `origin/main` past a large, green suite. All three were
the same failure, and it was NOT a missing assertion: it was a WORLD no
fixture had ever built. The tests checked the right things about the wrong
state, so no amount of sharpening the existing ones would have found them.

  1. STAGED BUT UNCOMMITTED. Every `git add` in the suite was immediately
     followed by a `git commit`, so no test ever left an entry sitting in the
     index across a `check`. `git checkout -- <path>` restores from the INDEX,
     so a role that staged its work made every revert a silent no-op while the
     guard reported success.

  2. OUT OF ZONE AND ALREADY DIRTY. Every leak fixture used `STATE_PREFIX`, so
     every constructed leak was in-zone. `reported_only` holds exactly the
     paths the guard deliberately leaves on disk — the one set guaranteed to
     survive a run was the one set never scanned, and a credential reached
     history through it.

  3. EACH ABORT BRANCH. `head_moved`, `git_surface` and `unsettled` revert
     nothing, so everything the role wrote survives. Any rule about what
     happens to a role's output has a different answer on these paths, and a
     suite that only ever exercises the main path cannot see it.

  4. AN ENCRYPTED STORE, AND A KEY THAT MAY BE ABSENT (§6). Credentials no
     longer sit in a plaintext file that is always readable. The store is
     committed ciphertext; the values exist only in a decrypted file outside
     the repository, and only while the tick holds the key. So «the guard has
     the values» is now a precondition rather than a given: a scan written
     against a base with no key, or with the store never materialised, tests
     a different world than the one a scheduled tick runs in.

So: when you add a rule here, ask what it does in each of those four states
before asking whether your assertion is sharp. A fifth will eventually join
the list — add it here when it bites, because a convention that lives only in
a review comment dies with the review.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests._roles_fixture import (  # type: ignore
    can_create,
    generate_key,
    git,
    key_env,
    head_content,
    head_sha,
    init_repo,
    porcelain_z,
    read_text,
    repo_base,
    index_paths,
    repo_path,
    secrets_path,
    staged_paths,
    write_bytes,
    write_encrypted_store,
    write_prefix,
    write_secrets,
    write_text,
)
import roles_guard as guard  # type: ignore

STATE_PREFIX = "zettelkasten/_system/roles/notion/state/"
OTHER_STATE_PREFIX = "zettelkasten/_system/roles/other/state/"
INBOX_PREFIX = "zettelkasten/_sources/inbox/roles/"

# §3.6: a value shorter than 12 characters is not scanned at all.
SECRET_VALUE = "secret-abc-1234"          # 15 chars — scanned
SHORT_SECRET = "sunshine"                 # 8 chars  — below the floor
FLOOR_VALUE = "abcdefghijkl"              # exactly 12 — the boundary
UNDER_FLOOR_VALUE = "abcdefghijk"         # exactly 11 — just under


def _state(flat: bool = False):
    return (write_prefix(STATE_PREFIX, flat=flat),)


def _inbox(flat: bool = True):
    return (write_prefix(INBOX_PREFIX, flat=flat),)


def _secrets_file(repo: Path) -> Path:
    return secrets_path(repo_base(repo))


def _snap(repo: Path) -> dict:
    return guard.capture_snapshot(repo, _secrets_file(repo))


def _touched(repo: Path, role_snapshot: dict) -> list:
    return guard.attribute(role_snapshot, _snap(repo))


def _check(repo: Path, tick: dict, snap: dict, prefixes=None) -> dict:
    if prefixes is None:
        prefixes = _state()
    return guard.check(repo, tick, snap, tuple(prefixes), _secrets_file(repo))


def _holds(path: Path, needle: str) -> bool:
    """True when `path`'s bytes contain `needle` as UTF-8 text."""
    try:
        return needle in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _report_paths(result: dict) -> list:
    """The paths in `reported_only`, whatever shape carries the §3.2 label.

    §3.3 requires the report to distinguish the owner's work from an earlier
    role's, but does not fix how — a plain string cannot carry a label, so the
    entries may well be dicts. Tests that care about WHICH paths were reported
    go through here; the one test that cares about the LABEL compares the raw
    structures directly.
    """
    out = []
    for entry in result["reported_only"]:
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, dict):
            out.append(entry.get("path", entry))
        else:
            out.append(entry)
    return out


# ==========================================================================
# capture_snapshot / §3.1 digests
# ==========================================================================

class SnapshotTests(unittest.TestCase):
    def test_clean_repo_snapshot_has_a_head_sha_and_no_entries(self):
        """SIBLING — nothing dirty is the ordinary state, not an error."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            self.assertRegex(snap["head"], r"^[0-9a-f]{40}$")
            self.assertEqual(snap["entries"], {})

    def test_head_matches_git_rev_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            self.assertEqual(_snap(repo)["head"], head_sha(repo))

    def test_entries_map_each_dirty_path_to_a_sha256_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, STATE_PREFIX + "new.md"), "content\n")
            entries = _snap(repo)["entries"]
            self.assertIn(STATE_PREFIX + "new.md", entries)
            self.assertRegex(entries[STATE_PREFIX + "new.md"], r"^[0-9a-f]{64}$")

    def test_digest_changes_when_content_changes(self):
        rel = STATE_PREFIX + "new.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), "one\n")
            first = _snap(repo)["entries"][rel]
            write_text(repo_path(repo, rel), "two\n")
            second = _snap(repo)["entries"][rel]
            self.assertNotEqual(first, second)

    def test_deleted_tracked_file_gets_the_deleted_sentinel(self):
        rel = "README.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            repo_path(repo, rel).unlink()
            self.assertEqual(_snap(repo)["entries"][rel], "<deleted>")

    def test_snapshot_is_deterministic_for_an_unchanged_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, STATE_PREFIX + "new.md"), "content\n")
            self.assertEqual(_snap(repo), _snap(repo))


class AttributionTests(unittest.TestCase):
    def test_a_new_file_is_attributed_to_the_role_that_created_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "new.md"), "content\n")
            self.assertEqual(_touched(repo, snap), [STATE_PREFIX + "new.md"])

    def test_modification_by_role_b_of_a_file_role_a_created_is_attributed_to_b(self):
        """§3.1, the confirmed hole in the previous draft: role A creates the
        file, so B's snapshot already records it dirty and `git status` emits
        the identical line. Only the digest difference catches B's edit."""
        rel = OTHER_STATE_PREFIX + "new.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), "written by A\n")   # role A ran
            snap_b = _snap(repo)                                  # role B starts
            write_text(repo_path(repo, rel), "modified by B\n")   # role B edits it
            touched = _touched(repo, snap_b)
            self.assertIn(rel, touched)
            _, out_of_zone = guard.classify(touched, _state())
            self.assertIn(rel, out_of_zone)

    def test_role_a_output_untouched_by_role_b_is_not_attributed_to_b(self):
        """SIBLING — the other direction of the same mis-attribution. A file
        that is merely dirty when B starts is not B's doing."""
        rel = OTHER_STATE_PREFIX + "new.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), "written by A\n")
            snap_b = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "b did its own work\n")
            self.assertNotIn(rel, _touched(repo, snap_b))

    def test_rewriting_a_file_with_identical_bytes_is_not_attributed(self):
        """SIBLING — a role that rewrites its state with the same content has
        changed nothing; a byte-identical rewrite must not be reported."""
        rel = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            original = read_text(repo_path(repo, rel))
            snap = _snap(repo)
            write_text(repo_path(repo, rel), original)
            self.assertEqual(_touched(repo, snap), [])

    def test_attribute_returns_sorted_plain_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            for name in ("zzz.md", "aaa.md", "mmm.md"):
                write_text(repo_path(repo, STATE_PREFIX + name), "x\n")
            touched = _touched(repo, snap)
            self.assertEqual(touched, sorted(touched))
            for path in touched:
                self.assertNotIn("\\", path)


# ==========================================================================
# rule 1 — `--porcelain -uall -z`
# ==========================================================================

class Rule1StatusFlagsTests(unittest.TestCase):
    def test_rule1_uall_new_directory_expands_to_individual_files(self):
        """Without `-uall` a wholly new directory collapses to one entry and
        the check inspects a directory instead of files."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "newdir/one.md"), "1\n")
            write_text(repo_path(repo, STATE_PREFIX + "newdir/two.md"), "2\n")
            touched = _touched(repo, snap)
            self.assertIn(STATE_PREFIX + "newdir/one.md", touched)
            self.assertIn(STATE_PREFIX + "newdir/two.md", touched)
            self.assertNotIn(STATE_PREFIX + "newdir/", touched)
            self.assertNotIn(STATE_PREFIX + "newdir", touched)

    def test_rule1_z_cyrillic_path_is_unquoted_and_stays_in_zone(self):
        """SIBLING and the load-bearing case. Without `-z`, `core.quotepath`
        emits `"zettelkasten/…/\\321\\200…"`, which fails the prefix check and
        is deleted on every run — and `state/расхождения.md` is the design's
        own worked example."""
        rel = STATE_PREFIX + "расхождения.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "открытых: 3\n")
            # prove the premise: git itself would C-quote this path without -z
            self.assertIn("\\3", git(repo, "status", "--porcelain", "-uall").stdout)
            touched = _touched(repo, snap)
            self.assertIn(rel, touched)
            result = _check(repo, tick, snap)
            self.assertIn(rel, result["in_zone"])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, rel).exists())

    def test_rule1_z_path_with_a_space_survives(self):
        """SIBLING — a filename with a space is another shape the default
        porcelain quoting mangles."""
        rel = STATE_PREFIX + "open items.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "x\n")
            self.assertIn(rel, _touched(repo, snap))

    def test_rule1_deeply_nested_new_directory_expands(self):
        """SIBLING — depth is not a defect; a role may build a tree in state/."""
        rel = STATE_PREFIX + "a/b/c/d/e.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "deep\n")
            self.assertIn(rel, _touched(repo, snap))


# ==========================================================================
# rule 2 — renames in the `-z` wire format
# ==========================================================================

class Rule2RenameTests(unittest.TestCase):
    def test_rule2_rename_out_of_zone_is_split_into_both_paths(self):
        old_rel = STATE_PREFIX + "seen.txt"
        new_rel = "zettelkasten/1_projects/seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            git(repo, "mv", old_rel, new_rel)
            self.assertTrue(porcelain_z(repo).lstrip().startswith("R"))
            touched = _touched(repo, snap)
            self.assertIn(old_rel, touched)
            self.assertIn(new_rel, touched)
            in_zone, out_of_zone = guard.classify(touched, _state())
            self.assertEqual(in_zone, [old_rel])
            self.assertEqual(out_of_zone, [new_rel])

    def test_rule2_rename_within_the_zone_leaves_both_halves_in_zone(self):
        """SIBLING — a role renaming its own state file is legitimate, and both
        halves must land in zone rather than one being reverted."""
        old_rel = STATE_PREFIX + "seen.txt"
        new_rel = STATE_PREFIX + "последний-снимок.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            git(repo, "mv", old_rel, new_rel)
            in_zone, out_of_zone = guard.classify(_touched(repo, snap), _state())
            self.assertEqual(sorted(in_zone), sorted([old_rel, new_rel]))
            self.assertEqual(out_of_zone, [])

    def test_rule2_no_rename_arrow_survives_into_a_path(self):
        """The pre-`-z` `R old -> new` form must never be carried through as a
        single string."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            git(repo, "mv", STATE_PREFIX + "seen.txt", "zettelkasten/1_projects/seen.txt")
            for path in _touched(repo, snap):
                self.assertNotIn("->", path)
                self.assertNotIn("\x00", path)


# ==========================================================================
# rule 3 — never --force, never git clean, never touch .git/
# ==========================================================================

class Rule3NoForceTests(unittest.TestCase):
    # `clean` and `stash` can discard work the guard never inspected. `reset`
    # is NOT banned: `git reset -q -- <path>` is a path-scoped unstage that
    # leaves the working tree alone, and it is how the guard clears an index
    # entry a role staged. `reset --hard` is the destructive form, so the flag
    # is what is banned, and `test_..._reset_is_always_path_scoped` pins the
    # shape rather than the verb.
    BANNED_SUBCOMMANDS = ("clean", "stash")
    BANNED_FLAGS = ("--force", "-f", "--hard", "--merge", "--keep",
                    "-D", "--no-preserve-root")

    def _stage_the_scenario(self, repo):
        """Set the repo up so one `check` exercises untracked-delete,
        tracked-restore, tracked-deleted-restore, an unstage, a leak revert
        and a report-only path. Returns the two snapshots.

        Setup is separated from the run so the argv interceptor can wrap the
        GUARD's git calls only — wrapping the fixture's own `git add` would
        make the tests assert against commands the guard never issued."""
        write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
        write_text(repo_path(repo, "zettelkasten/1_projects/owner-wip.md"), "draft\n")
        tick = _snap(repo)
        snap = _snap(repo)
        write_text(repo_path(repo, "zettelkasten/1_projects/owner-wip.md"), "touched\n")
        write_text(repo_path(repo, "zettelkasten/1_projects/rogue.md"), "rogue\n")
        write_text(repo_path(repo, "zettelkasten/2_areas/architecture.md"), "over\n")
        repo_path(repo, "README.md").unlink()
        write_text(repo_path(repo, STATE_PREFIX + "leak.md"), f"{SECRET_VALUE}\n")
        git(repo, "add", "zettelkasten/1_projects/rogue.md")
        return tick, snap

    def _argv_of_one_check(self, repo):
        """Every git argv the guard itself issues during one `check`."""
        tick, snap = self._stage_the_scenario(repo)
        real_run = guard.subprocess.run
        argvs = []

        def spy(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "git":
                argvs.append(list(cmd))
            return real_run(cmd, *args, **kwargs)

        guard.subprocess.run = spy
        try:
            _check(repo, tick, snap)
        finally:
            guard.subprocess.run = real_run
        return argvs

    def test_rule3_never_hands_git_a_destructive_subcommand_or_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            argvs = self._argv_of_one_check(init_repo(Path(tmp)))
            self.assertGreaterEqual(len(argvs), 3, "the interceptor saw no git calls")
            for argv in argvs:
                rest = [a for a in argv[1:] if not a.startswith("-")]
                subcommand = rest[0] if rest else None
                self.assertNotIn(subcommand, self.BANNED_SUBCOMMANDS, f"argv={argv}")
                for flag in self.BANNED_FLAGS:
                    self.assertNotIn(flag, argv, f"argv={argv}")

    def test_rule3_reset_is_always_path_scoped_and_never_hard(self):
        """`git reset` clears the index entry a role staged. In its
        path-scoped form (`reset -q -- <path>`) it does not touch the working
        tree; without the `--` it would move HEAD, and with `--hard` it would
        discard the owner's uncommitted work wholesale. The verb is fine, the
        shape is what matters."""
        with tempfile.TemporaryDirectory() as tmp:
            argvs = self._argv_of_one_check(init_repo(Path(tmp)))
            resets = [a for a in argvs if "reset" in a]
            self.assertTrue(resets, "the index is never cleared — staged work survives")
            for argv in resets:
                self.assertIn("--", argv, f"unscoped reset moves HEAD: {argv}")
                self.assertLess(argv.index("reset"), argv.index("--"))
                self.assertNotIn("--hard", argv)

    def test_rule3_the_interceptor_would_catch_a_banned_flag(self):
        """SIBLING — proves the check above CAN fail. An assertion over an
        empty list, or over argv the guard never produces, is the same no-op
        the source grep was."""
        with tempfile.TemporaryDirectory() as tmp:
            argvs = self._argv_of_one_check(init_repo(Path(tmp)))
            poisoned = argvs + [["git", "checkout", "-f", "HEAD"]]
            offenders = [a for a in poisoned
                         if any(f in a for f in self.BANNED_FLAGS)]
            self.assertEqual(len(offenders), 1,
                             "the flag test must react to `checkout -f`")

    def test_rule3_every_git_call_carries_literal_pathspecs(self):
        """The flag that makes a path DATA rather than a pathspec, asserted on
        the real argv.

        Intercepts `subprocess.run`, not `_git`: `_git` is where the flag is
        added, so spying one level higher would assert nothing about what git
        actually receives."""
        with tempfile.TemporaryDirectory() as tmp:
            argvs = self._argv_of_one_check(init_repo(Path(tmp)))
            self.assertGreaterEqual(len(argvs), 3, "no git argv was captured")
            for argv in argvs:
                self.assertIn("--literal-pathspecs", argv, f"argv={argv}")
                self.assertEqual(argv[1], "--literal-pathspecs",
                                 f"the flag must precede the subcommand: {argv}")

    def test_rule3_git_internals_are_never_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            marker = repo / ".git" / "roles-scratch.tmp"
            write_text(marker, "engine scratch\n")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, "zettelkasten/1_projects/rogue.md"), "rogue\n")
            _check(repo, tick, snap)
            self.assertTrue(marker.exists(), ".git/ must never be touched")
            self.assertEqual(git(repo, "rev-parse", "HEAD").returncode, 0)

    def test_rule3_revert_is_scoped_and_leaves_other_dirt_alone(self):
        """SIBLING — proves the revert is per-path, not a blunt
        `git checkout .` / `git clean -fd` that would erase the owner's
        concurrent uncommitted work."""
        owner_rel = "zettelkasten/1_projects/owner-wip.md"
        rogue_rel = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, owner_rel), "owner draft\n")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rogue_rel), "rogue\n")
            _check(repo, tick, snap)
            self.assertFalse(repo_path(repo, rogue_rel).exists())
            self.assertEqual(read_text(repo_path(repo, owner_rel)), "owner draft\n")


# ==========================================================================
# rule 4 — prefix comparison on POSIX repo-relative paths
# ==========================================================================

class Rule4PrefixTests(unittest.TestCase):
    def test_rule4_classify_is_prefix_based_on_posix_paths(self):
        touched = [
            STATE_PREFIX + "seen.txt",
            STATE_PREFIX + "deep/nested/файл.md",
            "zettelkasten/1_projects/PROJECTS.md",
            "README.md",
        ]
        in_zone, out_of_zone = guard.classify(touched, _state())
        self.assertEqual(
            in_zone, [STATE_PREFIX + "seen.txt", STATE_PREFIX + "deep/nested/файл.md"]
        )
        self.assertEqual(out_of_zone, ["zettelkasten/1_projects/PROJECTS.md", "README.md"])

    def test_rule4_a_longer_sibling_directory_name_is_not_a_prefix_match(self):
        """The prefix is a path boundary, not a string.

        Exercised against a prefix with NO trailing slash, which is the only
        shape that tests the boundary rule. With a trailing-slash prefix a
        bare `path.startswith(prefix)` already rejects `state-extra/`, so the
        old fixture passed under the very mutant it claimed to cover —
        decorative on the axis it named. §1.1 stores explicit prefixes
        verbatim, so a slashless prefix is a real shape, not a contrivance."""
        prefix = write_prefix("zettelkasten/2_areas/team")
        sibling = "zettelkasten/2_areas/team-extra/x.md"
        inside = "zettelkasten/2_areas/team/notes.md"
        exact = "zettelkasten/2_areas/team"
        in_zone, out_of_zone = guard.classify([sibling, inside, exact], (prefix,))
        self.assertEqual(out_of_zone, [sibling])
        self.assertEqual(in_zone, [inside, exact])

    def test_rule4_a_longer_sibling_name_is_out_of_zone_for_a_slashed_prefix_too(self):
        """SIBLING — the same boundary with the sugar's trailing-slash shape."""
        rel = "zettelkasten/_system/roles/notion/state-extra/x.md"
        in_zone, out_of_zone = guard.classify([rel], _state())
        self.assertEqual(in_zone, [])
        self.assertEqual(out_of_zone, [rel])

    def test_rule4_an_explicit_file_prefix_matches_exactly_that_file(self):
        """SIBLING — `writes:` may name a single owner-facing document; that
        prefix must match the file and nothing beside it."""
        doc = "zettelkasten/2_areas/architecture.md"
        in_zone, out_of_zone = guard.classify(
            [doc, "zettelkasten/2_areas/architecture.md.bak"], (write_prefix(doc),)
        )
        self.assertIn(doc, in_zone)
        self.assertIn("zettelkasten/2_areas/architecture.md.bak", out_of_zone)

    def test_rule4_another_roles_state_dir_is_out_of_zone_and_restored(self):
        rel = OTHER_STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            original = read_text(repo_path(repo, rel))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "notion reached into other\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [rel])
            self.assertEqual(read_text(repo_path(repo, rel)), original)

    def test_rule4_path_outside_the_base_is_out_of_zone_and_reverted(self):
        rel = "scripts/rogue.sh"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "#!/bin/sh\n")
            result = _check(repo, tick, snap, _state() + _inbox())
            self.assertEqual(result["reverted"], [rel])
            self.assertFalse(repo_path(repo, rel).exists())

    def test_rule4_classify_never_emits_backslash_separators(self):
        """Windows parity: classification works on POSIX-normalised paths."""
        touched = [STATE_PREFIX + "a/b.md", "zettelkasten/1_projects/PROJECTS.md"]
        in_zone, out_of_zone = guard.classify(touched, _state())
        for p in in_zone + out_of_zone:
            self.assertNotIn("\\", p)

    def test_rule4_multiple_prefixes_are_all_honoured(self):
        """SIBLING — sugar and an explicit prefix side by side."""
        doc = "zettelkasten/2_areas/architecture.md"
        touched = [STATE_PREFIX + "seen.txt", INBOX_PREFIX + "note.md", doc, "README.md"]
        in_zone, out_of_zone = guard.classify(touched, _state() + _inbox() + (write_prefix(doc),))
        self.assertEqual(sorted(in_zone),
                         sorted([STATE_PREFIX + "seen.txt", INBOX_PREFIX + "note.md", doc]))
        self.assertEqual(out_of_zone, ["README.md"])


# ==========================================================================
# rule 5 — empty allowlist
# ==========================================================================

class Rule5EmptyAllowlistTests(unittest.TestCase):
    def test_rule5_role_with_no_prefixes_has_everything_reverted(self):
        state_rel = STATE_PREFIX + "seen.txt"
        inbox_rel = INBOX_PREFIX + "note.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            original = read_text(repo_path(repo, state_rel))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, state_rel), "should not survive\n")
            write_text(repo_path(repo, inbox_rel), "should not survive\n")
            result = _check(repo, tick, snap, ())
            self.assertEqual(sorted(result["reverted"]), sorted([state_rel, inbox_rel]))
            self.assertEqual(result["in_zone"], [])
            self.assertEqual(read_text(repo_path(repo, state_rel)), original)
            self.assertFalse(repo_path(repo, inbox_rel).exists())

    def test_rule5_read_only_role_that_touched_nothing_passes_clean(self):
        """SIBLING — a role that reads, goes outside and leaves only a log line
        is legitimate, and must report a clean run rather than an empty
        violation."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            result = _check(repo, tick, snap, ())
            self.assertEqual(result["reverted"], [])
            self.assertEqual(result["in_zone"], [])
            self.assertEqual(result["reported_only"], [])
            self.assertEqual(result["failed"], [])
            self.assertEqual(result["secret_leak"], [])
            self.assertIs(result["head_moved"], False)


# ==========================================================================
# §3.3 — the remedy branches on RESTORABILITY, not on ownership
# ==========================================================================

class RemedyRestorabilityTests(unittest.TestCase):
    """§3.3's three-case table, one named test per row, each with a sibling.

    The question is never «whose is this» — it is «can the guard put this back
    exactly as it was before this role ran?», decided ONLY by the ROLE
    snapshot. The tick baseline decides nothing here; it only labels a
    report-only path in the report.

    The ownership branch this replaced destroyed data in a live two-role tick:
    role A created a file in its own zone, role B touched it out of B's zone,
    and because the path was absent from the TICK baseline it looked
    revertible — and «revert» for an untracked file means delete. See
    `RoleACreatedRoleBTouchedTests` below for the regression test.
    """

    # --- row 1: absent from the role snapshot, untracked -> delete ---------

    def test_absent_from_role_snapshot_and_untracked_is_deleted(self):
        """It did not exist when the role started, so nothing is lost."""
        rel = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            self.assertNotIn(rel, snap["entries"])
            write_text(repo_path(repo, rel), "rogue\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [rel])
            self.assertEqual(result["reported_only"], [])
            self.assertFalse(repo_path(repo, rel).exists())

    def test_absent_from_role_snapshot_and_untracked_in_zone_survives(self):
        """SIBLING — the same shape inside the zone is a role's normal output
        and must not be touched."""
        rel = STATE_PREFIX + "новый.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "новый\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [])
            self.assertIn(rel, result["in_zone"])
            self.assertEqual(read_text(repo_path(repo, rel)), "новый\n")

    # --- row 2: absent from the role snapshot, tracked -> checkout ---------

    def test_absent_from_role_snapshot_and_tracked_is_restored_to_head(self):
        """Absent from a `git status` listing means the tracked file equalled
        HEAD when the role started, so checkout restores precisely the
        pre-role state. Asserted against HEAD's bytes, not against a
        remembered string — a restore that wrote the wrong content would pass
        an existence check."""
        rel = "zettelkasten/1_projects/PROJECTS.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            committed = head_content(repo, rel)
            tick = _snap(repo)
            snap = _snap(repo)
            self.assertNotIn(rel, snap["entries"])
            write_text(repo_path(repo, rel), "rewritten by the role\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [rel])
            self.assertEqual(read_text(repo_path(repo, rel)), committed)
            self.assertEqual(read_text(repo_path(repo, rel)), head_content(repo, rel))

    def test_absent_from_role_snapshot_and_tracked_deleted_is_restored_to_head(self):
        """The same row, deletion side: a tracked file the role removed is
        brought back with HEAD's exact content."""
        rel = "README.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            committed = head_content(repo, rel)
            tick = _snap(repo)
            snap = _snap(repo)
            repo_path(repo, rel).unlink()
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [rel])
            self.assertTrue(repo_path(repo, rel).exists())
            self.assertEqual(read_text(repo_path(repo, rel)), committed)

    def test_absent_from_role_snapshot_and_tracked_in_zone_keeps_the_new_content(self):
        """SIBLING — updating its own committed state file is what a role does
        on every run; restorability is only consulted out of zone."""
        rel = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "2026-07-28\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [])
            self.assertEqual(read_text(repo_path(repo, rel)), "2026-07-28\n")

    # --- row 3: present in the role snapshot -> report only ----------------

    def test_present_in_role_snapshot_is_reported_never_reverted(self):
        """It was already dirty before this role ran. Git does not hold that
        content and the snapshot carries only a digest, so no remedy can
        reproduce it — deleting it or resetting it to HEAD destroys work that
        was never the offending role's. Here the prior content is the OWNER's,
        but that is not what decides it."""
        rel = "zettelkasten/1_projects/owner-wip.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), "owner draft\n")
            tick = _snap(repo)
            snap = _snap(repo)
            self.assertIn(rel, snap["entries"])
            write_text(repo_path(repo, rel), "role overwrote it\n")
            result = _check(repo, tick, snap)
            self.assertEqual(_report_paths(result), [rel])
            self.assertEqual(result["reverted"], [])
            self.assertEqual(read_text(repo_path(repo, rel)), "role overwrote it\n")

    def test_present_in_role_snapshot_and_untouched_produces_no_finding(self):
        """SIBLING — a dirty tree must not generate a finding on every tick
        just for being dirty. Only a path this role TOUCHED is reported."""
        rel = "zettelkasten/1_projects/owner-wip.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), "owner draft\n")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "2026-07-28\n")
            result = _check(repo, tick, snap)
            self.assertEqual(_report_paths(result), [])
            self.assertEqual(result["reverted"], [])
            self.assertEqual(read_text(repo_path(repo, rel)), "owner draft\n")

    def test_the_tick_baseline_is_not_an_input_to_the_remedy_decision(self):
        """The SoT form of the rewrite: `remedy` takes the ROLE snapshot. A
        signature still naming the tick baseline is the defect itself."""
        params = list(inspect.signature(guard.remedy).parameters)
        self.assertEqual(params[:3], ["repo", "out_of_zone", "role_snapshot"])
        self.assertNotIn("tick_baseline", params)


class RoleACreatedRoleBTouchedTests(unittest.TestCase):
    """The regression suite for the live two-role data loss.

    Role A creates a file in ITS OWN zone. Role B then touches that file, out
    of B's zone. The path is absent from the TICK baseline (A made it
    mid-tick) but PRESENT in role B's snapshot. Under the old ownership branch
    the guard read «absent from the tick baseline» as «revertible» and deleted
    role A's legitimate work — reporting the path in `reverted` without saying
    it could not be undone.
    """

    A_FILE = OTHER_STATE_PREFIX + "работа-роли-а.md"
    A_CONTENT = "накопленная работа роли А\nстрока два\n"

    def _two_role_tick(self, repo: Path):
        """Tick baseline, then role A writes in its own zone, then role B's
        snapshot — the exact sequence the tick performs."""
        tick = _snap(repo)
        write_text(repo_path(repo, self.A_FILE), self.A_CONTENT)
        snap_b = _snap(repo)
        return tick, snap_b

    def test_role_b_touching_role_as_in_zone_file_does_not_delete_it(self):
        """The regression assertion, on CONTENT — existence alone would pass a
        restore that wrote the wrong bytes, and role A's accumulated work is
        exactly what an existence check fails to protect."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick, snap_b = self._two_role_tick(repo)
            self.assertNotIn(self.A_FILE, tick["entries"])
            self.assertIn(self.A_FILE, snap_b["entries"])
            write_text(repo_path(repo, self.A_FILE), self.A_CONTENT + "приписка от Б\n")
            _check(repo, tick, snap_b)
            self.assertTrue(repo_path(repo, self.A_FILE).exists(),
                            "role A's work was deleted for role B's transgression")
            self.assertIn(self.A_CONTENT, read_text(repo_path(repo, self.A_FILE)))

    def test_role_b_touching_role_as_in_zone_file_is_reported_not_reverted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick, snap_b = self._two_role_tick(repo)
            write_text(repo_path(repo, self.A_FILE), self.A_CONTENT + "приписка от Б\n")
            result = _check(repo, tick, snap_b)
            self.assertEqual(_report_paths(result), [self.A_FILE])
            self.assertEqual(result["reverted"], [])
            self.assertEqual(result["failed"], [])

    def test_role_b_leaving_role_as_file_alone_produces_no_finding(self):
        """SIBLING — the sequence that made the bug reachable must stay silent
        when role B behaves. Role A's mid-tick output is not a finding."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick, snap_b = self._two_role_tick(repo)
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "2026-07-28\n")
            result = _check(repo, tick, snap_b)
            self.assertEqual(_report_paths(result), [])
            self.assertEqual(result["reverted"], [])
            self.assertEqual(read_text(repo_path(repo, self.A_FILE)), self.A_CONTENT)

    def test_role_b_deleting_role_as_untracked_file_is_reported_not_ignored(self):
        """The guard CANNOT restore an untracked file it never held. The one
        thing it must not do is nothing, quietly: the path is detected as
        touched and reported, so the owner learns the file is gone."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick, snap_b = self._two_role_tick(repo)
            repo_path(repo, self.A_FILE).unlink()
            touched = guard.attribute(snap_b, _snap(repo))
            self.assertIn(self.A_FILE, touched, "a deletion is a change")
            result = _check(repo, tick, snap_b)
            self.assertEqual(_report_paths(result), [self.A_FILE])
            self.assertEqual(result["reverted"], [])

    def test_role_b_deleting_a_tracked_file_is_restored_not_merely_reported(self):
        """SIBLING to the deletion case — when the guard CAN restore, it does.
        The two deletion cases differ only in whether git holds the content."""
        rel = "zettelkasten/1_projects/PROJECTS.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            committed = head_content(repo, rel)
            tick, snap_b = self._two_role_tick(repo)
            repo_path(repo, rel).unlink()
            result = _check(repo, tick, snap_b)
            self.assertEqual(result["reverted"], [rel])
            self.assertEqual(read_text(repo_path(repo, rel)), committed)


class ReportOnlyLabellingTests(unittest.TestCase):
    """§3.2/§3.3 — the tick baseline's ONLY remaining job.

    A report-only path present in the tick baseline is the owner's uncommitted
    work; otherwise it is an earlier role's output. Two different things for
    the owner to read on a morning report, and the one cheap snapshot that
    still distinguishes them.

    Both scenarios below use the SAME path and produce the SAME remedy, so the
    only thing that can differ between the two results is the label. A bare
    list of path strings cannot carry it and fails these tests by construction.
    """

    REL = "zettelkasten/1_projects/contested.md"

    def _owner_scenario(self, repo: Path):
        write_text(repo_path(repo, self.REL), "owner draft\n")
        tick = _snap(repo)
        snap = _snap(repo)
        write_text(repo_path(repo, self.REL), "role touched it\n")
        return _check(repo, tick, snap)

    def _earlier_role_scenario(self, repo: Path):
        tick = _snap(repo)
        write_text(repo_path(repo, self.REL), "written by an earlier role\n")
        snap = _snap(repo)
        write_text(repo_path(repo, self.REL), "role touched it\n")
        return _check(repo, tick, snap)

    def test_owner_wip_is_reported_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            result = self._owner_scenario(repo)
            self.assertEqual(_report_paths(result), [self.REL])
            self.assertEqual(result["reverted"], [])

    def test_an_earlier_roles_output_is_reported_only_too(self):
        """SIBLING — same remedy, different provenance. Both are unrestorable,
        so both are reported; the rule does not care which."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            result = self._earlier_role_scenario(repo)
            self.assertEqual(_report_paths(result), [self.REL])
            self.assertEqual(result["reverted"], [])

    def test_the_two_report_only_kinds_are_distinguishable_in_the_report(self):
        """Identical path, identical remedy — so if the two reports are equal,
        the owner cannot tell their own half-finished note from a role's
        output, and the tick baseline is being captured for nothing.

        Deliberately shape-agnostic: it compares the two whole structures
        rather than naming a field, so any labelling scheme passes and a bare
        list of path strings — which cannot carry a label — cannot."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            owner = self._owner_scenario(repo)
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            earlier = self._earlier_role_scenario(repo)
        self.assertEqual(_report_paths(owner), _report_paths(earlier))
        self.assertNotEqual(
            json.dumps(owner["reported_only"], ensure_ascii=False, sort_keys=True),
            json.dumps(earlier["reported_only"], ensure_ascii=False, sort_keys=True),
            "the tick baseline's only job is to tell these two apart",
        )

    def test_the_owner_label_is_carried_on_the_reported_entry(self):
        """The label has to reach the owner's morning report, so it rides on
        the entry rather than living in a second parallel list nobody prints."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            entries = self._owner_scenario(repo)["reported_only"]
            self.assertEqual(len(entries), 1)
            self.assertNotIsInstance(entries[0], str,
                                     "a bare string cannot carry the §3.2 label")
            self.assertIn(self.REL, json.dumps(entries[0], ensure_ascii=False))

    def test_a_role_that_touches_both_kinds_labels_them_separately_in_one_report(self):
        """One run, both kinds — the labels must not collapse to whichever the
        guard saw first."""
        owner_rel = "zettelkasten/1_projects/owner-wip.md"
        role_rel = OTHER_STATE_PREFIX + "earlier-role.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, owner_rel), "owner draft\n")
            tick = _snap(repo)
            write_text(repo_path(repo, role_rel), "written by an earlier role\n")
            snap = _snap(repo)
            write_text(repo_path(repo, owner_rel), "role touched it\n")
            write_text(repo_path(repo, role_rel), "role touched it too\n")
            result = _check(repo, tick, snap)
            self.assertEqual(sorted(_report_paths(result)),
                             sorted([owner_rel, role_rel]))
            rendered = {
                _report_paths({"reported_only": [e]})[0]:
                    json.dumps(e, ensure_ascii=False, sort_keys=True)
                for e in result["reported_only"]
            }
            self.assertNotEqual(
                rendered[owner_rel].replace(owner_rel, "PATH"),
                rendered[role_rel].replace(role_rel, "PATH"),
                "both entries carry the same label — the kinds collapsed",
            )

    def test_the_report_is_json_serialisable_whatever_shape_the_label_takes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            json.dumps(self._owner_scenario(repo))

    def test_tracked_modified_out_of_zone_file_is_restored(self):
        rel = "zettelkasten/1_projects/PROJECTS.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            original = read_text(repo_path(repo, rel))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "rewritten by the role\n")
            result = _check(repo, tick, snap)
            self.assertEqual(read_text(repo_path(repo, rel)), original)
            self.assertEqual(result["reverted"], [rel])

    def test_tracked_deleted_out_of_zone_file_is_restored(self):
        rel = "README.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            original = read_text(repo_path(repo, rel))
            tick = _snap(repo)
            snap = _snap(repo)
            repo_path(repo, rel).unlink()
            result = _check(repo, tick, snap)
            self.assertTrue(repo_path(repo, rel).exists())
            self.assertEqual(read_text(repo_path(repo, rel)), original)
            self.assertEqual(result["reverted"], [rel])

    def test_in_zone_writes_of_every_shape_survive(self):
        """SIBLING covering all three remedy shapes from the other side: a new
        state file, an updated one, and a pruned one are the normal output of
        a role and none may be touched."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "новый.md"), "новый\n")
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "2026-07-28\n")
            write_text(repo_path(repo, INBOX_PREFIX + "note.md"), "заметка\n")
            result = _check(repo, tick, snap, _state() + _inbox())
            self.assertEqual(result["reverted"], [])
            self.assertEqual(len(result["in_zone"]), 3)
            self.assertTrue(repo_path(repo, STATE_PREFIX + "новый.md").exists())
            self.assertTrue(repo_path(repo, INBOX_PREFIX + "note.md").exists())

    def test_check_is_idempotent_on_a_second_call(self):
        """SIBLING — re-running the guard after it already reverted is a clean
        no-op, not a second round of damage."""
        rogue = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rogue), "rogue\n")
            first = _check(repo, tick, snap)
            second = _check(repo, tick, snap)
            self.assertEqual(first["reverted"], [rogue])
            self.assertEqual(second["reverted"], [])
            self.assertEqual(second["failed"], [])


# ==========================================================================
# rule 6 — HEAD moved
# ==========================================================================

class Rule6HeadMovedTests(unittest.TestCase):
    def test_rule6_head_moved_reverts_nothing(self):
        """A reset could destroy the owner's work committed alongside."""
        committed_rel = "zettelkasten/1_projects/PROJECTS.md"
        dirty_rel = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, committed_rel), "role committed this\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "role committed")
            write_text(repo_path(repo, dirty_rel), "and left this dirty\n")
            result = _check(repo, tick, snap)
            self.assertIsInstance(result["head_moved"], dict)
            self.assertEqual(result["reverted"], [])
            self.assertEqual(read_text(repo_path(repo, committed_rel)),
                             "role committed this\n")
            self.assertTrue(repo_path(repo, dirty_rel).exists())

    def test_rule6_head_moved_reports_both_shas_as_before_and_after(self):
        """§3.4 rule 6: `{"before": sha, "after": sha}` — the tick needs both
        to tell the owner what the role committed, and JSON has to carry it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            before = head_sha(repo)
            write_text(repo_path(repo, "zettelkasten/1_projects/PROJECTS.md"), "x\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "role committed")
            after = head_sha(repo)
            result = _check(repo, tick, snap)
            self.assertEqual(result["head_moved"], {"before": before, "after": after})
            self.assertNotEqual(before, after)
            json.dumps(result)  # the CLI has to serialise it

    def test_rule6_head_moved_sends_out_of_zone_paths_to_reported_only(self):
        """§3.4 rule 6: `check` performs no mutation at all, so an out-of-zone
        path was — literally — left alone, and `reported_only` is where the
        run line records that."""
        rogue = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, "zettelkasten/2_areas/architecture.md"), "x\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "role committed")
            write_text(repo_path(repo, rogue), "rogue\n")
            result = _check(repo, tick, snap)
            self.assertIn(rogue, _report_paths(result))
            self.assertEqual(result["reverted"], [])
            self.assertEqual(result["failed"], [])
            self.assertTrue(repo_path(repo, rogue).exists())

    def test_rule6_head_moved_does_not_reduce_in_zone(self):
        """No remedy ran, so nothing may be subtracted from `in_zone` — the
        post-remedy rule has nothing to subtract."""
        in_zone_rel = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, "zettelkasten/2_areas/architecture.md"), "x\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "role committed")
            write_text(repo_path(repo, in_zone_rel), "2026-07-28\n")
            result = _check(repo, tick, snap)
            self.assertIn(in_zone_rel, result["in_zone"])
            self.assertEqual(read_text(repo_path(repo, in_zone_rel)), "2026-07-28\n")

    def test_rule6_head_moved_still_runs_the_read_only_leak_scan(self):
        """A committed credential is exactly the case worth reporting loudest,
        so the scan — which mutates nothing — still runs."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, "zettelkasten/2_areas/architecture.md"), "x\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "role committed")
            write_text(repo_path(repo, rel), f"leaked {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertIsInstance(result["head_moved"], dict)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, rel).exists(),
                            "the scan reports; on a moved HEAD it must not revert")

    def test_rule6_head_moved_mutates_nothing_on_disk(self):
        """The whole clause in one assertion: every dirty path is byte-identical
        before and after `check`."""
        rogue = "zettelkasten/1_projects/rogue.md"
        state = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, "zettelkasten/2_areas/architecture.md"), "x\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "role committed")
            write_text(repo_path(repo, rogue), "rogue\n")
            write_text(repo_path(repo, state), "2026-07-28\n")
            before = _snap(repo)["entries"]
            _check(repo, tick, snap)
            self.assertEqual(_snap(repo)["entries"], before)

    def test_rule6_head_unchanged_reports_head_moved_exactly_false(self):
        """SIBLING — the ordinary run must not be mistaken for a commit, and
        `false` is the literal contract, not an empty dict."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "2026-07-28\n")
            result = _check(repo, tick, snap)
            self.assertIs(result["head_moved"], False)
            self.assertEqual(result["reverted"], [])


# ==========================================================================
# rule 7 — a failed revert is reported, never swallowed
# ==========================================================================

class Rule7RevertFailureTests(unittest.TestCase):
    def test_rule7_a_revert_that_cannot_succeed_lands_in_failed(self):
        """A directory where a file path is expected cannot be unlinked and
        cannot be checked out; the guard must report it rather than swallow
        the exception and let the tick claim a clean run."""
        blocked = "zettelkasten/1_projects/blocked"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, blocked + "/keep.md"), "not a file path\n")
            out = guard.remedy(repo, [blocked], snap)
            self.assertEqual(out["failed"], [blocked])
            self.assertEqual(out["reverted"], [])
            self.assertTrue(repo_path(repo, blocked + "/keep.md").exists())

    def test_rule7_a_successful_revert_never_lands_in_failed(self):
        """SIBLING — the ordinary revert must not be reported as a failure."""
        rogue = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, rogue), "rogue\n")
            out = guard.remedy(repo, [rogue], snap)
            self.assertEqual(out["reverted"], [rogue])
            self.assertEqual(out["failed"], [])
            self.assertEqual(out["reported_only"], [])

    def test_rule7_remedy_on_an_empty_list_is_a_no_op(self):
        """SIBLING — the overwhelmingly common case must not error."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            out = guard.remedy(repo, [], snap)
            self.assertEqual(out, {"reverted": [], "reported_only": [], "failed": []})

    def test_rule7_one_failure_does_not_abort_the_other_reverts(self):
        blocked = "zettelkasten/1_projects/blocked"
        rogue = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, blocked + "/keep.md"), "x\n")
            write_text(repo_path(repo, rogue), "rogue\n")
            out = guard.remedy(repo, [blocked, rogue], snap)
            self.assertEqual(out["failed"], [blocked])
            self.assertEqual(out["reverted"], [rogue])


# ==========================================================================
# rule 9 — the credential surface, split across two mechanisms
# ==========================================================================

class Rule8SecretsSurfaceTests(unittest.TestCase):
    """§3.4 rule 9 — the credential surface, split across two mechanisms.

    The store is COMMITTED ciphertext, so git sees a change to it exactly
    like any other tracked path and no special case is needed. The decrypted
    file lives OUTSIDE the repository, which is rule 10's territory. The
    digest special-case in `capture_snapshot` therefore fires for nothing:
    it only triggers on a secrets file inside the repo, and there is none.

    These tests pin both halves, and the siblings that keep the first half
    from over-reaching onto the owner's own edits.
    """

    STORE_REL = "zettelkasten/_system/state/secrets.enc.json"

    def _committed_store(self, repo, pairs):
        key = generate_key()
        write_encrypted_store(repo_base(repo), key, pairs)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "commit the encrypted store")
        return key

    def test_the_committed_store_is_visible_to_porcelain_like_any_tracked_file(self):
        """The premise that replaced the old one: no ignore rule, no blind
        spot, no special case needed."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            key = self._committed_store(repo, {"NOTION_TOKEN": SECRET_VALUE})
            write_encrypted_store(repo_base(repo), key, {"NOTION_TOKEN": "rotated-1234"})
            self.assertIn("secrets.enc.json", porcelain_z(repo))

    def test_a_role_rewriting_the_committed_store_is_attributed_and_reverted(self):
        """It is a tracked file the role had no business touching, so the
        ordinary rules apply: absent from the role snapshot, restorable,
        reverted to HEAD."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            key = self._committed_store(repo, {"NOTION_TOKEN": SECRET_VALUE})
            committed = head_content(repo, self.STORE_REL)
            tick = _snap(repo)
            snap = _snap(repo)
            write_encrypted_store(repo_base(repo), key, {"STOLEN": "exfiltrated-1234"})
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [self.STORE_REL])
            self.assertEqual(read_text(repo_path(repo, self.STORE_REL)), committed)

    def test_a_store_the_owner_was_editing_is_reported_never_reverted(self):
        """SIBLING — §3.3 still governs. An owner mid-rotation has an
        unrestorable store, and destroying it would lose every credential."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            key = self._committed_store(repo, {"NOTION_TOKEN": SECRET_VALUE})
            write_encrypted_store(repo_base(repo), key, {"NOTION_TOKEN": "owner-rotating-1234"})
            tick = _snap(repo)
            snap = _snap(repo)
            write_encrypted_store(repo_base(repo), key, {"NOTION_TOKEN": "role-touched-1234"})
            result = _check(repo, tick, snap)
            self.assertIn(self.STORE_REL, _report_paths(result))
            self.assertEqual(result["reverted"], [])

    def test_an_untouched_store_produces_no_finding(self):
        """SIBLING — having credentials must not generate a finding per tick."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            self._committed_store(repo, {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            result = _check(repo, tick, snap)
            self.assertEqual(_report_paths(result), [])
            self.assertEqual(result["reverted"], [])

    def test_the_decrypted_file_is_outside_the_snapshot_entirely(self):
        """Rule 10's territory: it is outside the repository, so it is not in
        `entries`, cannot be attributed to a role, and cannot be reverted."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            decrypted = write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            snap = _snap(repo)
            self.assertTrue(decrypted.is_file())
            self.assertNotIn(str(decrypted), json.dumps(snap["entries"]))
            for path in snap["entries"]:
                self.assertNotIn("roles-decrypted-secrets", path)

    def test_a_role_editing_the_decrypted_file_is_outside_the_guards_reach(self):
        """The limitation, stated rather than pretended away (rule 10). The
        file is outside the repo, so `git status` never mentions it and the
        guard neither reports nor restores it — the bound on its lifetime is
        `destroy`, not the guard."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            decrypted = write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(decrypted, "NOTION_TOKEN=tampered-by-the-role\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [])
            self.assertEqual(_report_paths(result), [])

    def test_a_base_with_no_credentials_at_all_is_tolerated(self):
        """SIBLING — the common case: no store, no key, no decrypted file."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            self.assertNotIn("secrets.enc.json", json.dumps(snap["entries"]))
            self.assertEqual(_check(repo, snap, snap)["failed"], [])


# ==========================================================================
# rule 9 — log.jsonl is never an allowed prefix
# ==========================================================================

class Rule9LogTests(unittest.TestCase):
    def test_rule9_a_role_writing_its_own_log_is_out_of_zone_and_reverted(self):
        rel = "zettelkasten/_system/roles/notion/log.jsonl"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), '{"forged":true}\n')
            result = _check(repo, tick, snap, _state() + _inbox())
            self.assertEqual(result["reverted"], [rel])
            self.assertFalse(repo_path(repo, rel).exists())

    def test_rule9_a_state_file_named_log_jsonl_is_in_zone(self):
        """SIBLING — the ban is on the tick's log path, not on the filename."""
        rel = STATE_PREFIX + "log.jsonl"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), '{"mine":true}\n')
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [])
            self.assertIn(rel, result["in_zone"])


# ==========================================================================
# rule 10 — paths outside the repository, stated as a limitation
# ==========================================================================

class Rule10OutsideRepoTests(unittest.TestCase):
    def test_rule10_module_docstring_states_the_outside_repo_limitation(self):
        doc = (guard.__doc__ or "").lower()
        self.assertIn("outside", doc)
        self.assertIn("repo", doc)

    def test_rule10_a_file_outside_the_repository_is_not_attributed_and_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            outside = Path(tmp) / "outside" / "note.md"
            snap = _snap(repo)
            write_text(outside, "the role reached outside the repo\n")
            self.assertEqual(_touched(repo, snap), [])
            self.assertTrue(outside.exists())


# ==========================================================================
# §3.5 — the inbox is flat-md
# ==========================================================================

class InboxShapeTests(unittest.TestCase):
    """§3.5 — flatness is carried ON the prefix, so the guard needs no copy of
    the inbox path. Every assertion below is about `WritePrefix.flat`, never
    about the literal inbox string."""

    def test_a_subdirectory_beneath_a_flat_prefix_is_out_of_zone(self):
        """SOURCES.md registers `roles` as flat-md, so the registered layout
        cannot be violated silently."""
        rel = INBOX_PREFIX + "2026-07/note.md"
        in_zone, out_of_zone = guard.classify([rel], _inbox())
        self.assertEqual(in_zone, [])
        self.assertEqual(out_of_zone, [rel])

    def test_a_flat_file_beneath_a_flat_prefix_is_in_zone(self):
        """SIBLING — the registered shape must be accepted, including a
        Cyrillic filename."""
        flat = [INBOX_PREFIX + "2026-07-28-notion.md", INBOX_PREFIX + "расхождения.md"]
        in_zone, out_of_zone = guard.classify(flat, _inbox())
        self.assertEqual(in_zone, flat)
        self.assertEqual(out_of_zone, [])

    def test_a_subdirectory_beneath_a_NON_flat_prefix_is_in_zone(self):
        """SIBLING — the flat refusal must come from `flat=True` and nothing
        else. An explicit prefix the owner declared for a directory tree keeps
        accepting subdirectories, or the open prefix set is open in name only."""
        rel = "zettelkasten/2_areas/team/notes/weekly/2026-07.md"
        in_zone, out_of_zone = guard.classify(
            [rel], (write_prefix("zettelkasten/2_areas/team/", flat=False),)
        )
        self.assertEqual(in_zone, [rel])
        self.assertEqual(out_of_zone, [])

    def test_the_same_path_flips_zone_with_the_flat_flag_alone(self):
        """The sharpest form of §3.5: identical path, identical prefix string,
        opposite verdicts — driven only by the flag the prefix carries."""
        rel = INBOX_PREFIX + "2026-07/note.md"
        strict_in, strict_out = guard.classify([rel], (write_prefix(INBOX_PREFIX, True),))
        loose_in, loose_out = guard.classify([rel], (write_prefix(INBOX_PREFIX, False),))
        self.assertEqual((strict_in, strict_out), ([], [rel]))
        self.assertEqual((loose_in, loose_out), ([rel], []))

    def test_a_deeply_nested_path_beneath_a_flat_prefix_is_out_of_zone(self):
        rel = INBOX_PREFIX + "a/b/c/note.md"
        in_zone, out_of_zone = guard.classify([rel], _inbox())
        self.assertEqual(in_zone, [])
        self.assertEqual(out_of_zone, [rel])

    def test_an_inbox_subdirectory_is_reverted_end_to_end(self):
        rel = INBOX_PREFIX + "2026-07/note.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "nested\n")
            result = _check(repo, tick, snap, _inbox())
            self.assertEqual(result["reverted"], [rel])
            self.assertFalse(repo_path(repo, rel).exists())

    def test_a_flat_inbox_note_survives_end_to_end(self):
        """SIBLING — the shape `/minder:mem:process` expects must reach the inbox."""
        rel = INBOX_PREFIX + "2026-07-28-notion.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "заметка\n")
            result = _check(repo, tick, snap, _inbox())
            self.assertEqual(result["reverted"], [])
            self.assertIn(rel, result["in_zone"])
            self.assertTrue(repo_path(repo, rel).exists())


# ==========================================================================
# §3.6 — the secret-value scan
# ==========================================================================

class SecretScanTests(unittest.TestCase):
    def test_an_in_zone_file_containing_a_secret_value_is_flagged(self):
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), f"token is {SECRET_VALUE}\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], [SECRET_VALUE]), [rel])

    def test_an_in_zone_file_with_unrelated_content_is_not_flagged(self):
        """SIBLING — exact-value match only, no entropy heuristic. A random
        base64-looking blob that is NOT a secret value must pass; the previous
        engine's entropy guess dropped legitimate rows."""
        rel = STATE_PREFIX + "notes.md"
        blob = "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3A="
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), f"unrelated payload {blob}\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], [SECRET_VALUE]), [])

    def test_a_cyrillic_in_zone_file_is_scanned_without_a_decode_error(self):
        """SIBLING — §0: every read is explicit UTF-8. Under the locale default
        this file would raise or mojibake and the scan would silently pass."""
        rel = STATE_PREFIX + "расхождения.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), f"открытых: 3, токен {SECRET_VALUE}\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], [SECRET_VALUE]), [rel])

    def test_a_binary_in_zone_file_does_not_break_the_scan(self):
        """SIBLING — an undecodable state file must not abort the scan for the
        files after it."""
        binary = STATE_PREFIX + "snapshot.png"
        leaking = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_bytes(repo_path(repo, binary), b"\x89PNG\r\n\x1a\n\x00\xff\xfe" * 8)
            write_text(repo_path(repo, leaking), f"{SECRET_VALUE}\n")
            self.assertEqual(
                guard.scan_secrets(repo, [binary, leaking], [SECRET_VALUE]), [leaking]
            )

    def test_no_secret_values_configured_flags_nothing(self):
        """SIBLING — the common case: a role with no credentials at all."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), "ordinary content\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], []), [])


class SecretScanLengthFloorTests(unittest.TestCase):
    """§3.6 — a value shorter than 12 characters is not scanned at all.

    This is what makes exact substring matching safe: below the floor a secret
    is a word or fragment, and scanning for it would revert the owner's
    legitimate content on every run. The honest position below the floor is
    "this credential cannot be leak-scanned", surfaced by `validate` at
    creation (tested in `test_roles_run`), not a silent false-positive machine
    at 07:00.
    """

    def test_a_short_value_is_not_scanned_even_when_present(self):
        """The common-English-word case: `sunshine` appears verbatim in the
        owner's prose and must NOT be flagged, because it is under the floor."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), "the sunshine was lovely today\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], [SHORT_SECRET]), [])

    def test_a_value_of_exactly_twelve_characters_is_scanned(self):
        """SIBLING and the boundary: "shorter than 12" means 12 is scanned."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), f"leaked {FLOOR_VALUE} here\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], [FLOOR_VALUE]), [rel])

    def test_a_value_of_exactly_eleven_characters_is_not_scanned(self):
        """The other side of the same boundary, one character apart."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), f"leaked {UNDER_FLOOR_VALUE} here\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], [UNDER_FLOOR_VALUE]), [])

    def test_a_long_value_made_of_common_english_words_is_matched_exactly(self):
        """SIBLING — the floor is about LENGTH, not vocabulary. A long
        passphrase of ordinary words is a real credential and is scanned."""
        rel = STATE_PREFIX + "notes.md"
        value = "correct horse battery staple"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), f"pasted: {value}\n")
            self.assertEqual(guard.scan_secrets(repo, [rel], [value]), [rel])

    def test_a_short_value_does_not_suppress_a_long_one_in_the_same_batch(self):
        """SIBLING — one under-floor value must not short-circuit the scan for
        the credentials that CAN be checked."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, rel), f"the sunshine and {SECRET_VALUE}\n")
            self.assertEqual(
                guard.scan_secrets(repo, [rel], [SHORT_SECRET, SECRET_VALUE]), [rel]
            )


class SecretLeakRemedyTests(unittest.TestCase):
    def test_check_reverts_a_leaking_in_zone_file_and_reports_secret_leak(self):
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"leaked {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertFalse(repo_path(repo, rel).exists())

    def test_a_leaked_file_is_excluded_from_in_zone_post_remedy(self):
        """§3.6 API note: `in_zone` is post-remedy, so §5's `writes` count is
        the length of that list and the two agree by construction."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"leaked {SECRET_VALUE}\n")
            self.assertNotIn(rel, _check(repo, tick, snap)["in_zone"])

    def test_a_clean_file_beside_a_leaking_one_stays_in_zone(self):
        """SIBLING — post-remedy `in_zone` drops only the reverted file, not
        the whole run's output."""
        leaking = STATE_PREFIX + "notes.md"
        clean = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, leaking), f"leaked {SECRET_VALUE}\n")
            write_text(repo_path(repo, clean), "2026-07-28\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [leaking])
            self.assertEqual(result["in_zone"], [clean])
            self.assertTrue(repo_path(repo, clean).exists())

    def test_an_under_floor_secret_never_reverts_the_owners_content(self):
        """SIBLING and the reason the floor exists: with a short credential
        configured, prose that happens to contain the word must survive."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"WEAK_TOKEN": SHORT_SECRET})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "the sunshine was lovely today\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [])
            self.assertIn(rel, result["in_zone"])
            self.assertTrue(repo_path(repo, rel).exists())

    def test_a_clean_in_zone_write_alongside_a_configured_secret_survives(self):
        """SIBLING — having credentials configured must not make ordinary
        state writes suspect."""
        rel = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "2026-07-28\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [])
            self.assertIn(rel, result["in_zone"])


class SecretLeakRestorabilityTests(unittest.TestCase):
    """§3.6 × §3.3 — the leak branch asks the SAME question as every other
    remedy: «can the guard put this back exactly as it was before this role
    ran?», decided by the ROLE snapshot.

    It used to ask about ownership, and that is the branch §3.3 rewrote after
    it destroyed data. A leak is not a licence to delete: if the file was
    already dirty when the role started, git does not hold its previous
    content and neither does the snapshot, so reverting would take the
    credential out by taking the work out with it. The credential is instead
    reported, left in the working tree where the owner can see it, and kept
    out of the commit by the tick (§7.1 step 4).

    NOTE for the spec: §3.6's prose still frames this branch around "already
    dirty at the TICK baseline". §3.3 is the rewritten rule and the role
    snapshot is what decides; these tests follow §3.3. Flagged in the report.
    """

    def test_a_leak_absent_from_the_role_snapshot_is_reverted(self):
        """Row 1: the file did not exist when the role started, so removing it
        loses nothing and the credential never reaches the commit."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            self.assertNotIn(rel, snap["entries"])
            write_text(repo_path(repo, rel), f"leaked {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertFalse(repo_path(repo, rel).exists())

    def test_a_leak_absent_from_the_role_snapshot_but_tracked_is_restored_to_head(self):
        """Row 2 for the leak branch: a committed state file the role polluted
        goes back to HEAD's exact bytes — restorable, so restored."""
        rel = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            committed = head_content(repo, rel)
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"leaked {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertEqual(read_text(repo_path(repo, rel)), committed)

    def test_a_leak_present_in_the_role_snapshot_as_owner_wip_is_reported_not_reverted(self):
        """Row 3, owner flavour. The owner was already editing this file when
        the tick began and the role appended a credential to it. Destroying the
        draft to remove the credential is the cure being worse than the
        disease."""
        rel = STATE_PREFIX + "notes.md"
        owner_draft = "мой черновик, ещё не закоммичен\n"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            write_text(repo_path(repo, rel), owner_draft)
            tick = _snap(repo)
            snap = _snap(repo)
            self.assertIn(rel, snap["entries"])
            write_text(repo_path(repo, rel), owner_draft + f"leaked {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertEqual(result["reverted"], [])
            on_disk = read_text(repo_path(repo, rel))
            self.assertIn(owner_draft.strip(), on_disk)

    def test_a_leak_present_in_the_role_snapshot_as_an_earlier_roles_work_is_reported(self):
        """Row 3, earlier-role flavour — and the case the ownership branch got
        WRONG. Role A wrote this file in its own zone mid-tick, so it is absent
        from the tick baseline; role B then leaked a credential into it. Asking
        «whose is this» said revertible and deleted role A's work. Asking «can
        I restore it» says no, so it is reported."""
        rel = OTHER_STATE_PREFIX + "работа-роли-а.md"
        a_content = "накопленная работа роли А\n"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            write_text(repo_path(repo, rel), a_content)          # role A
            snap_b = _snap(repo)
            write_text(repo_path(repo, rel), a_content + f"{SECRET_VALUE}\n")
            result = _check(repo, tick, snap_b, (write_prefix(OTHER_STATE_PREFIX),))
            self.assertEqual(result["secret_leak"], [rel])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, rel).exists())
            self.assertIn(a_content.strip(), read_text(repo_path(repo, rel)))

    def test_a_non_leaking_file_in_the_same_run_is_untouched(self):
        """SIBLING — the accepts side. A file the role touched that carries no
        credential produces no finding at all: not `secret_leak`, not
        `reverted`, not `reported_only`."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            write_text(repo_path(repo, rel), "мой черновик\n")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "мой черновик, дополнено ролью\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [])
            self.assertEqual(result["reverted"], [])
            self.assertEqual(_report_paths(result), [])
            self.assertEqual(
                read_text(repo_path(repo, rel)), "мой черновик, дополнено ролью\n"
            )

    def test_a_clean_file_beside_a_leaking_one_survives(self):
        """SIBLING — one leak must not sweep the run's other output away."""
        leaking = STATE_PREFIX + "leak.md"
        clean = STATE_PREFIX + "clean.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, leaking), f"leaked {SECRET_VALUE}\n")
            write_text(repo_path(repo, clean), "обычная запись\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [leaking])
            self.assertTrue(repo_path(repo, clean).exists())
            self.assertIn(clean, result["in_zone"])

    def test_both_leak_branches_in_one_run_are_reported_together(self):
        """One run, one file of each kind: the restorable one is reverted, the
        unrestorable one survives, and both are reported."""
        fresh = STATE_PREFIX + "fresh.md"
        prior = STATE_PREFIX + "prior.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            write_text(repo_path(repo, prior), "draft\n")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, fresh), f"leaked {SECRET_VALUE}\n")
            write_text(repo_path(repo, prior), f"draft + {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertEqual(sorted(result["secret_leak"]), sorted([fresh, prior]))
            self.assertFalse(repo_path(repo, fresh).exists())
            self.assertTrue(repo_path(repo, prior).exists())


# ==========================================================================
# hostile path names — a path is data, never a pathspec
# ==========================================================================

class HostilePathNameTests(unittest.TestCase):
    """A repo-relative path handed to git is DATA. Git reads it as a
    **pathspec**, which has globbing and magic-prefix syntax of its own.

    The one that bites: a role writes an out-of-zone file literally named
    `*.md`. `git ls-files '*.md'` matches the tracked `architecture.md`, so the
    guard concludes the offender is tracked and runs
    `git checkout -- '*.md'` — which restores every `.md` from the index,
    destroying the owner's uncommitted edit, and leaves the offending file
    exactly where it was. Precisely inverted.

    The others are accepts-siblings: unusual names an owner or a role can
    legitimately produce, all of which must keep working. `can_create` skips a
    name the filesystem itself refuses, so a Windows run reports honestly
    instead of failing on `*` or `?`.
    """

    OWNER_DOC = "zettelkasten/2_areas/architecture.md"
    OWNER_EDIT = "черновик владельца, не закоммичен\n"

    HOSTILE_NAMES = [
        ("glob-star", "*.md"),
        ("glob-question", "?.md"),
        ("glob-bracket", "[ab].md"),
        ("glob-doublestar", "**.md"),
        ("leading-dash", "-not-a-flag.md"),
        ("leading-colon", ":not-pathspec-magic.md"),
        ("colon-slash", ":(icase)literal.md"),
        ("space", "open items.md"),
        ("backslash", "back\\slash.md"),
        ("single-quote", "it's.md"),
        ("double-quote", 'say "hi".md'),
        ("newline", "two\nlines.md"),
        ("cyrillic", "расхождения.md"),
        ("hash", "#draft.md"),
    ]

    def _run(self, filename: str):
        """Owner has an uncommitted edit; the role drops `filename` out of
        zone. Returns (offender_gone, owner_edit_survived, result)."""
        rel = f"zettelkasten/1_projects/{filename}"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            offender = repo_path(repo, rel)
            if not can_create(offender):
                return None
            write_text(repo_path(repo, self.OWNER_DOC), self.OWNER_EDIT)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(offender, "written by the role\n")
            result = _check(repo, tick, snap)
            return (
                not offender.exists(),
                read_text(repo_path(repo, self.OWNER_DOC)) == self.OWNER_EDIT,
                result,
            )

    def test_a_glob_named_file_does_not_destroy_the_owners_uncommitted_edit(self):
        """The failing case, on its own so it cannot hide inside a subTest."""
        outcome = self._run("*.md")
        if outcome is None:
            self.skipTest("this filesystem refuses '*' in a filename")
        gone, owner_intact, result = outcome
        self.assertTrue(owner_intact,
                        "the owner's uncommitted edit was destroyed as collateral")
        self.assertTrue(gone, "the offending file survived while others were reverted")
        self.assertEqual(result["failed"], [])

    def test_every_hostile_name_is_handled_as_data(self):
        """SIBLINGS — the reviewer found only the glob case failing, so these
        must STAY passing: a fix that starts quoting pathspecs must not begin
        refusing ordinary unusual names."""
        for label, filename in self.HOSTILE_NAMES:
            with self.subTest(name=label):
                outcome = self._run(filename)
                if outcome is None:
                    self.skipTest(f"filesystem refuses {label}")
                    continue
                gone, owner_intact, result = outcome
                self.assertTrue(owner_intact, f"{label}: owner's edit destroyed")
                self.assertTrue(gone, f"{label}: offender survived")

    def test_a_glob_named_file_inside_the_zone_is_kept(self):
        """SIBLING — a role may legitimately name its own state file
        oddly. The guard must not delete an in-zone file just because its
        name would glob."""
        rel = STATE_PREFIX + "*.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            if not can_create(repo_path(repo, rel)):
                self.skipTest("this filesystem refuses '*' in a filename")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "состояние\n")
            result = _check(repo, tick, snap)
            self.assertIn(rel, result["in_zone"])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, rel).exists())

    def test_reverting_a_tracked_glob_named_file_touches_only_that_file(self):
        """The test that actually pins `--literal-pathspecs`.

        The untracked cases above cannot: the guard lists the whole index with
        a bare `ls-files -z` and compares in Python, so no hostile name ever
        reaches git AS a pathspec there — the vector is closed structurally and
        the flag is defence in depth. It reaches git in exactly one place, the
        `git checkout HEAD -- <path>` of a TRACKED file, so that is where the
        flag has to be pinned.

        Here `*.md` is committed, and a sibling `.md` in the same directory
        carries the owner's uncommitted edit. Without the flag the checkout
        expands to both and the owner's work is destroyed as collateral.
        """
        glob_rel = "zettelkasten/1_projects/*.md"
        sibling_rel = "zettelkasten/1_projects/PROJECTS.md"
        owner_edit = "черновик владельца\n"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            target = repo_path(repo, glob_rel)
            if not can_create(target):
                self.skipTest("this filesystem refuses '*' in a filename")
            write_text(target, "committed\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "commit a glob-named file")
            write_text(repo_path(repo, sibling_rel), owner_edit)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(target, "role overwrote it\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [glob_rel])
            self.assertEqual(read_text(target), "committed\n")
            self.assertEqual(
                read_text(repo_path(repo, sibling_rel)), owner_edit,
                "the checkout globbed and destroyed the owner's uncommitted edit",
            )

    def test_a_tracked_file_with_a_hostile_name_is_restored_to_head(self):
        """SIBLING — the revert path itself must work for such a name, not
        merely avoid collateral damage."""
        rel = "zettelkasten/1_projects/it's [draft].md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            target = repo_path(repo, rel)
            if not can_create(target):
                self.skipTest("this filesystem refuses the name")
            write_text(target, "committed\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "add oddly named file")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(target, "role overwrote it\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [rel])
            self.assertEqual(read_text(target), "committed\n")


# ==========================================================================
# the index — a second place a change hides
# ==========================================================================

class StagedChangeTests(unittest.TestCase):
    """A role that runs `git add` defeats every revert, silently.

    `git checkout -- <path>` restores the working tree FROM THE INDEX, not
    from HEAD, and `git ls-files` lists index entries. So once a role stages
    its work, the guard's revert is a no-op while `reverted` reports success —
    and the tick then commits the staged change.

    Not exotic: the owner's own hot-loaded canon instructs agents to `git add`
    after every edit, so an agent-run role staging its output is the expected
    case, not the strange one.

    Every assertion here checks BOTH surfaces. Content alone passes a fix that
    forgets the index; an index check alone passes one that forgets the file.
    """

    DOC = "zettelkasten/2_areas/architecture.md"
    NEW = "zettelkasten/1_projects/rogue.md"
    STATE = STATE_PREFIX + "notes.md"

    def test_a_staged_out_of_zone_modification_is_restored_to_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            committed = head_content(repo, self.DOC)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.DOC), "РОЛЬ ПЕРЕЗАПИСАЛА\n")
            git(repo, "add", self.DOC)
            self.assertEqual(staged_paths(repo), [self.DOC], "premise: it is staged")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [self.DOC])
            self.assertEqual(read_text(repo_path(repo, self.DOC)), committed)
            self.assertEqual(staged_paths(repo), [],
                             "reverted on disk but still staged — the tick commits it")

    def test_a_staged_out_of_zone_creation_is_removed_from_disk_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.NEW), "rogue\n")
            git(repo, "add", self.NEW)
            self.assertIn(self.NEW, index_paths(repo), "premise: it is in the index")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [self.NEW])
            self.assertFalse(repo_path(repo, self.NEW).exists())
            self.assertNotIn(self.NEW, index_paths(repo),
                             "gone from disk but still tracked — the tick commits it")
            self.assertEqual(staged_paths(repo), [])

    def test_a_staged_out_of_zone_deletion_is_restored_to_disk_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            committed = head_content(repo, self.DOC)
            tick = _snap(repo)
            snap = _snap(repo)
            git(repo, "rm", "-q", self.DOC)
            self.assertEqual(staged_paths(repo), [self.DOC])
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [self.DOC])
            self.assertTrue(repo_path(repo, self.DOC).exists())
            self.assertEqual(read_text(repo_path(repo, self.DOC)), committed)
            self.assertEqual(staged_paths(repo), [])

    def test_a_staged_credential_in_an_in_zone_file_leaves_nothing_staged(self):
        """The variant that reached history: the leak is caught and the file
        reverted, but a staged entry survives and the tick commits the
        credential with `secret_leak` looking handled."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), f"leaked {SECRET_VALUE}\n")
            git(repo, "add", self.STATE)
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [self.STATE])
            self.assertFalse(repo_path(repo, self.STATE).exists())
            self.assertNotIn(self.STATE, index_paths(repo))
            self.assertEqual(staged_paths(repo), [],
                             "the credential is still staged — it reaches the commit")

    def test_a_staged_credential_in_a_tracked_in_zone_file_is_unstaged_too(self):
        """The same, where the file is already committed: reverting to HEAD
        must clear the index entry as well, or the staged version is what the
        tick writes."""
        rel = STATE_PREFIX + "seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            committed = head_content(repo, rel)
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"{SECRET_VALUE}\n")
            git(repo, "add", rel)
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertEqual(read_text(repo_path(repo, rel)), committed)
            self.assertEqual(staged_paths(repo), [])

    def test_a_staged_in_zone_write_is_kept_and_reported_in_zone(self):
        """SIBLING — staging is not itself an offence. A role that follows the
        owner's canon and stages its own state file must keep it: reverting
        here would destroy the role's memory for obeying instructions."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), "накопленная память\n")
            git(repo, "add", self.STATE)
            result = _check(repo, tick, snap)
            self.assertIn(self.STATE, result["in_zone"])
            self.assertEqual(result["reverted"], [])
            self.assertEqual(read_text(repo_path(repo, self.STATE)), "накопленная память\n")
            self.assertEqual(staged_paths(repo), [self.STATE],
                             "the role's own staged work must survive untouched")

    def test_a_staged_in_zone_write_is_attributed_at_all(self):
        """SIBLING — staging must not hide a change from attribution either.
        `git status --porcelain` reports staged entries, so this is the half
        that already worked; asserted so a future index-aware rewrite cannot
        lose it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), "содержимое\n")
            git(repo, "add", self.STATE)
            self.assertIn(self.STATE, _touched(repo, snap))

    def test_a_staged_owner_wip_path_is_reported_never_reverted(self):
        """SIBLING — §3.3 still governs. A path already dirty at the role
        snapshot is unrestorable whether or not it is staged, so it is
        reported and left exactly as it was, index included."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, self.DOC), "owner draft\n")
            git(repo, "add", self.DOC)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.DOC), "role appended\n")
            result = _check(repo, tick, snap)
            self.assertEqual(_report_paths(result), [self.DOC])
            self.assertEqual(result["reverted"], [])
            self.assertEqual(read_text(repo_path(repo, self.DOC)), "role appended\n")


# ==========================================================================
# §3.6 — the scan follows the SURVIVORS, not the zone
# ==========================================================================

class OutOfZoneLeakTests(unittest.TestCase):
    """A credential in an already-dirty OUT-OF-ZONE file reached origin/main.

    The scan was called with `in_zone` at every site. But `reported_only`
    holds exactly the paths the guard deliberately leaves on disk — §3.3 keeps
    them because it cannot restore them — so the one set of files GUARANTEED
    to survive a run was the one set never read. The tick then staged and
    committed them.

    Why no test saw it: every leak fixture in this suite used `STATE_PREFIX`,
    so every constructed leak was in-zone. The same shape as the staged-index
    gap — one fixture state absent, one whole class invisible. These use an
    out-of-zone path on purpose.

    The rule the fix encodes: scan what SURVIVED the run, which is
    `in_zone + reported_only`, and never the reverted paths.
    """

    OUT = "zettelkasten/1_projects/owner-wip.md"
    INNOCENT = "zettelkasten/2_areas/architecture.md"
    OWNER_LINE = "мой черновик, ещё не закоммичен\n"

    def test_a_leak_in_an_already_dirty_out_of_zone_file_is_reported_not_reverted(self):
        """The path is unrestorable (§3.3), so the credential is reported and
        the file left alone. Asserted on the owner's OWN line: a fix that
        reverted the file to remove the credential would take the draft with
        it, which is the data loss §3.3 exists to refuse."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            write_text(repo_path(repo, self.OUT), self.OWNER_LINE)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.OUT),
                       self.OWNER_LINE + f"token {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertIn(self.OUT, result["secret_leak"],
                          "the surviving out-of-zone file was never scanned")
            self.assertEqual(result["reverted"], [])
            self.assertIn(self.OUT, _report_paths(result))
            on_disk = read_text(repo_path(repo, self.OUT))
            self.assertIn(self.OWNER_LINE.strip(), on_disk,
                          "the owner's own line was destroyed to remove the leak")

    def test_an_innocent_already_dirty_out_of_zone_file_is_neither_flagged_nor_touched(self):
        """SIBLING — the scan must not turn every kept path into a finding.
        This one is dirty and out of zone and touched by the role, and it
        carries no credential, so it is reported-only and nothing more."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            write_text(repo_path(repo, self.INNOCENT), self.OWNER_LINE)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.INNOCENT), self.OWNER_LINE + "дописано\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [])
            self.assertEqual(result["reverted"], [])
            self.assertIn(self.INNOCENT, _report_paths(result))
            self.assertIn("дописано", read_text(repo_path(repo, self.INNOCENT)))

    def test_both_kinds_in_one_run_are_separated(self):
        """One leaking survivor and one innocent survivor: only the first is
        flagged, and neither is reverted."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            write_text(repo_path(repo, self.OUT), self.OWNER_LINE)
            write_text(repo_path(repo, self.INNOCENT), self.OWNER_LINE)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.OUT), self.OWNER_LINE + SECRET_VALUE + "\n")
            write_text(repo_path(repo, self.INNOCENT), self.OWNER_LINE + "ok\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [self.OUT])
            self.assertEqual(sorted(_report_paths(result)),
                             sorted([self.OUT, self.INNOCENT]))
            self.assertEqual(result["reverted"], [])

    def test_a_leak_in_a_reverted_out_of_zone_file_is_reported_and_still_reverted(self):
        """§3.6: `secret_leak` means «a credential was WRITTEN here», not «a
        credential survived».

        `reverted` already says the file is gone. Nothing else says the value
        reached disk at all — and that is a rotate-now signal on its own,
        because a role that wrote a credential to a file may equally have sent
        it somewhere the guard cannot see. Deleting the file does not un-send
        it.

        Reporting must not change the remedy: the file is restorable, so it is
        still removed."""
        rel = "zettelkasten/1_projects/fresh.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"{SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertIn(rel, result["secret_leak"],
                          "the owner is never told the credential reached disk")
            self.assertEqual(result["reverted"], [rel])
            self.assertFalse(repo_path(repo, rel).exists(),
                             "reporting must not change the remedy")

    def test_secret_leak_and_reverted_may_name_the_same_path(self):
        """The overlap is CORRECT, not contradictory, and it will look wrong
        to a reader who assumes the two lists partition.

        They answer different questions: `secret_leak` is «a credential was
        written here», `reverted` is «the file is gone». One path can be both,
        and the pair together is exactly what the owner needs — rotate the
        credential AND know the file did not reach the commit. Asserted
        explicitly so nobody later «fixes» the overlap by making the lists
        disjoint."""
        rel = "zettelkasten/1_projects/fresh.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"{SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertIn(rel, result["secret_leak"])
            self.assertIn(rel, result["reverted"])
            self.assertTrue(
                set(result["secret_leak"]) & set(result["reverted"]),
                "the two lists must be allowed to intersect",
            )

    def test_a_leak_in_a_reverted_in_zone_file_is_reported_and_still_reverted(self):
        """SIBLING — the same rule on the in-zone side, where the leak branch
        itself does the reverting."""
        rel = STATE_PREFIX + "notes.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"{SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertIn(rel, result["secret_leak"])
            self.assertFalse(repo_path(repo, rel).exists())
            self.assertNotIn(rel, result["in_zone"], "post-remedy, so not counted")

    def test_a_reverted_file_without_a_credential_raises_no_finding(self):
        """SIBLING — «scan everything touched» must not mean «flag everything
        touched». An ordinary out-of-zone write is reverted and silent."""
        rel = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "обычная запись\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [])
            self.assertEqual(result["reverted"], [rel])

    def test_a_reverted_path_whose_filename_carries_a_credential_is_not_a_finding(self):
        """The phantom-finding guard, and it is subtler since §3.6 changed.

        A reverted path IS now scanned — its CONTENT, read before the file is
        removed. The filename is not content. So a file whose name carries the
        credential but whose bytes do not must raise nothing, even though the
        path string sitting in `reverted` contains the value.

        The discriminator against the widening mutation is exactly this: read
        the bytes before removal (a finding only when the value was written),
        versus match the value against the path (a finding for a file that
        never held it). The two look almost identical from the outside, which
        is why this case is asserted on its own."""
        rel = f"zettelkasten/1_projects/{SECRET_VALUE}.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "содержимое без секрета\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [rel])
            self.assertFalse(repo_path(repo, rel).exists())
            self.assertEqual(result["secret_leak"], [],
                             "a phantom finding for a file that never held it")

    def test_a_reverted_file_whose_name_and_content_both_carry_it_is_reported_once(self):
        """SIBLING to the phantom guard — when the bytes DO hold the value the
        finding is real, so the name-versus-content distinction cannot be
        implemented by ignoring the path's file entirely."""
        rel = f"zettelkasten/1_projects/{SECRET_VALUE}.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), f"и содержимое: {SECRET_VALUE}\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertEqual(result["secret_leak"].count(rel), 1, "reported once")
            self.assertFalse(repo_path(repo, rel).exists())

    def test_a_surviving_files_name_carrying_a_credential_is_a_finding(self):
        """The other half of the name/content split, and the reason the
        phantom guard is about SURVIVAL rather than about names being ignored.

        A filename is committed too. A surviving file called
        `<credential>.md` puts the value in the tree just as surely as one
        containing it, so the name of a survivor IS scanned — while the name
        of a reverted path is not, because it is gone. Content is read for
        everything touched; names are read only for what remains."""
        rel = STATE_PREFIX + f"{SECRET_VALUE}.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "содержимое без секрета\n")
            result = _check(repo, tick, snap)
            self.assertEqual(result["secret_leak"], [rel],
                             "a credential in a surviving filename reaches the commit")

    def test_an_unrestorable_files_name_carrying_a_credential_is_reported_not_reverted(self):
        """SIBLING — the name scan obeys §3.3 like every other finding: a path
        the guard cannot restore is reported and left alone, even when the
        credential is in its name."""
        rel = "zettelkasten/1_projects/" + f"{SECRET_VALUE}.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            write_text(repo_path(repo, rel), "черновик владельца\n")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rel), "черновик владельца, дополнено\n")
            result = _check(repo, tick, snap)
            self.assertIn(rel, result["secret_leak"])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, rel).exists())

    def test_a_deleted_file_the_guard_never_read_raises_no_finding(self):
        """SIBLING — a role that DELETES an out-of-zone tracked file leaves no
        bytes to scan at that path. The restore brings back HEAD's content,
        which is the owner's, so it must not be read as the role's leak."""
        rel = "zettelkasten/2_areas/architecture.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick = _snap(repo)
            snap = _snap(repo)
            repo_path(repo, rel).unlink()
            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [rel])
            self.assertEqual(result["secret_leak"], [])
            self.assertTrue(repo_path(repo, rel).exists())


class EncryptedStoreLeakTests(unittest.TestCase):
    """§6.5 — the leak scan needs the VALUES, and they now come from an
    encrypted store rather than a plaintext file.

    Two properties matter and neither is implied by the scan working:

      - a credential a role writes is still caught, so the value source
        changing underneath §3.6 did not quietly disable it;
      - the values reach no file inside the repository. The store holds
        ciphertext; the plaintext exists only in the decrypted file outside
        the tree, for the length of the run.
    """

    STATE = STATE_PREFIX + "notes.md"
    OUT = "zettelkasten/1_projects/owner-wip.md"

    def _repo_with_store(self, tmp, pairs=None):
        """A repo whose store is committed and whose decrypted file lives
        outside it — the shape a real tick has after `secrets-open`."""
        repo = init_repo(Path(tmp))
        base = repo_base(repo)
        key = generate_key()
        write_encrypted_store(base, key, pairs or {"NOTION_TOKEN": SECRET_VALUE})
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "commit the encrypted store")
        decrypted = Path(tmp) / "outside" / "secrets.env"
        with key_env(key):
            import roles_secrets
            roles_secrets.materialise(
                base / "_system" / "state" / "secrets.enc.json", decrypted)
        return repo, base, decrypted

    def _check_with(self, repo, decrypted, tick, snap, prefixes=None):
        return guard.check(repo, tick, snap, tuple(prefixes or _state()), decrypted)

    def test_a_credential_from_the_encrypted_store_is_still_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, decrypted = self._repo_with_store(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), f"leaked {SECRET_VALUE}\n")
            result = self._check_with(repo, decrypted, tick, snap)
            self.assertEqual(result["secret_leak"], [self.STATE])
            self.assertFalse(repo_path(repo, self.STATE).exists())

    def test_an_out_of_zone_survivor_is_still_caught_from_the_encrypted_store(self):
        """The union with the §3.6 gap: the new value source must not undo the
        «scan the survivors» fix."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, decrypted = self._repo_with_store(tmp)
            write_text(repo_path(repo, self.OUT), "owner draft\n")
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.OUT), f"owner draft\n{SECRET_VALUE}\n")
            result = self._check_with(repo, decrypted, tick, snap)
            self.assertIn(self.OUT, result["secret_leak"])
            self.assertEqual(result["reverted"], [])
            self.assertIn("owner draft", read_text(repo_path(repo, self.OUT)))

    def test_no_plaintext_value_reaches_any_file_in_the_repository(self):
        """The property the whole §6 trade rests on: the repo carries
        ciphertext and nothing else. Asserted over every file in the tree
        rather than over the store alone — a scan that wrote a cache, or a
        report that quoted a value, would land somewhere else."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, decrypted = self._repo_with_store(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), f"leaked {SECRET_VALUE}\n")
            self._check_with(repo, decrypted, tick, snap)
            offenders = [
                p for p in repo.rglob("*")
                if p.is_file() and ".git" not in p.parts and _holds(p, SECRET_VALUE)
            ]
            self.assertEqual(offenders, [],
                             "a plaintext credential is inside the repository")

    def test_the_committed_store_holds_only_ciphertext(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._repo_with_store(tmp)
            raw = (base / "_system" / "state" / "secrets.enc.json").read_text(
                encoding="utf-8")
            self.assertNotIn(SECRET_VALUE, raw)
            self.assertIn("NOTION_TOKEN", raw)

    def test_the_scan_is_silent_when_the_store_was_never_materialised(self):
        """SIBLING — a base with no decrypted file (no key, or a tick that
        never opened it) must not error. It cannot scan, and saying so by
        crashing the guard would take the whole tick down."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            missing = Path(tmp) / "outside" / "never-opened.env"
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), f"leaked {SECRET_VALUE}\n")
            result = self._check_with(repo, missing, tick, snap)
            self.assertEqual(result["secret_leak"], [])
            self.assertEqual(result["failed"], [])

    def test_an_innocent_run_against_a_real_store_reports_nothing(self):
        """SIBLING — having credentials configured must not make ordinary
        state writes suspect."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, decrypted = self._repo_with_store(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), "обычная запись\n")
            result = self._check_with(repo, decrypted, tick, snap)
            self.assertEqual(result["secret_leak"], [])
            self.assertIn(self.STATE, result["in_zone"])


class AbortBranchLeakTests(unittest.TestCase):
    """An abort reverts NOTHING, so everything the role wrote survives — which
    is why the scan matters more on these paths, not less.

    On a `git_surface` abort the role has already demonstrated it is attacking
    the guard, so leaving its writes unread there would be the worst possible
    place to skip.
    """

    OUT = "zettelkasten/1_projects/owner-wip.md"
    STATE = STATE_PREFIX + "notes.md"

    def _leaking_repo(self, tmp):
        repo = init_repo(Path(tmp))
        write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
        write_text(repo_path(repo, self.OUT), "owner draft\n")
        return repo

    def test_the_head_moved_abort_still_scans_the_survivors(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._leaking_repo(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), f"{SECRET_VALUE}\n")
            write_text(repo_path(repo, "zettelkasten/2_areas/architecture.md"), "x\n")
            git(repo, "add", "zettelkasten/2_areas/architecture.md")
            git(repo, "commit", "-q", "-m", "role committed")
            result = _check(repo, tick, snap)
            self.assertTrue(result["head_moved"])
            self.assertIn(self.STATE, result["secret_leak"])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, self.STATE).exists())

    def test_the_git_surface_abort_still_scans_the_survivors(self):
        """The role repoints a remote AND leaks. Both must be reported; the
        surface change must not swallow the credential."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._leaking_repo(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), f"{SECRET_VALUE}\n")
            git(repo, "remote", "add", "exfil", "https://attacker.invalid/x.git")
            result = _check(repo, tick, snap)
            self.assertTrue(result["git_surface"])
            self.assertIn(self.STATE, result["secret_leak"])
            self.assertEqual(result["reverted"], [])

    def test_the_unsettled_abort_still_scans_the_survivors(self):
        """A background process writing after the role exits. Induced by
        making the tree change between the guard's two snapshots, which is the
        condition the branch actually keys on."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._leaking_repo(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), f"{SECRET_VALUE}\n")
            real = guard.capture_snapshot
            calls = {"n": 0}

            def racing(repo_arg, secrets_arg):
                calls["n"] += 1
                if calls["n"] == 2:      # between the guard's two reads
                    write_text(repo_path(repo, "zettelkasten/1_projects/late.md"),
                               "written after the role exited\n")
                return real(repo_arg, secrets_arg)

            guard.capture_snapshot = racing
            try:
                result = guard.check(repo, tick, snap, _state(), _secrets_file(repo))
            finally:
                guard.capture_snapshot = real
            self.assertTrue(result["unsettled"])
            self.assertIn(self.STATE, result["secret_leak"])
            self.assertEqual(result["reverted"], [])

    def test_an_abort_with_no_credential_reports_no_leak(self):
        """SIBLING — the abort branches must not manufacture findings either."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._leaking_repo(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.STATE), "обычная запись\n")
            git(repo, "remote", "add", "exfil", "https://attacker.invalid/x.git")
            result = _check(repo, tick, snap)
            self.assertTrue(result["git_surface"])
            self.assertEqual(result["secret_leak"], [])

    def test_an_abort_scans_out_of_zone_survivors_too(self):
        """The union of both gaps: an abort, and the credential in the
        out-of-zone file the abort leaves untouched."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._leaking_repo(tmp)
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, self.OUT), f"owner draft\n{SECRET_VALUE}\n")
            git(repo, "remote", "add", "exfil", "https://attacker.invalid/x.git")
            result = _check(repo, tick, snap)
            self.assertTrue(result["git_surface"])
            self.assertIn(self.OUT, result["secret_leak"])
            self.assertTrue(repo_path(repo, self.OUT).exists())


# ==========================================================================
# the .git surface — changes `git status` never reports
# ==========================================================================

class GitSurfaceTests(unittest.TestCase):
    """Some of the most consequential things a role can change are invisible
    to `git status` entirely.

    Repointing `remote.origin.url` sends the owner's whole base to an attacker
    on the next push. Appending to `.gitignore` makes future writes invisible
    to every later tick. `git update-index --assume-unchanged` on an owner
    file makes git itself stop reporting that path. None of the three touches
    a working-tree file, so a path-and-digest snapshot over `git status`
    cannot see any of them — hence the separate `git` section of the snapshot.
    """

    def _snapshots(self, repo):
        return _snap(repo), _snap(repo)

    def test_a_changed_remote_url_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            git(repo, "remote", "add", "origin", "https://example.invalid/owner.git")
            before, snap = self._snapshots(repo)
            git(repo, "remote", "set-url", "origin", "https://attacker.invalid/x.git")
            after = _snap(repo)
            self.assertNotEqual(before["git"], after["git"],
                                "a repointed remote is invisible to the guard")

    def test_a_new_remote_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            before = _snap(repo)
            git(repo, "remote", "add", "exfil", "https://attacker.invalid/x.git")
            self.assertNotEqual(before["git"], _snap(repo)["git"])

    def test_an_appended_ignore_file_is_detected(self):
        """`.gitignore` is tracked, so `git status` WOULD report it — but
        `.git/info/exclude` is not, and it has the same effect."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            before = _snap(repo)
            exclude = repo / ".git" / "info" / "exclude"
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with exclude.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write("zettelkasten/_system/roles/\n")
            self.assertNotEqual(before["git"], _snap(repo)["git"],
                                "future writes are now invisible to every tick")

    def test_assume_unchanged_on_an_owner_file_is_detected(self):
        """After this, git reports the path as clean no matter what a role
        writes into it — the guard's own input is poisoned."""
        rel = "zettelkasten/2_areas/architecture.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            before = _snap(repo)
            git(repo, "update-index", "--assume-unchanged", rel)
            after = _snap(repo)
            self.assertNotEqual(before["git"], after["git"])
            write_text(repo_path(repo, rel), "invisible edit\n")
            self.assertEqual(porcelain_z(repo), "",
                             "premise: git itself now reports the tree as clean")

    def test_a_changed_hooks_path_is_detected(self):
        """A hooks directory the role controls runs its code on every later
        git operation the owner performs."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            before = _snap(repo)
            git(repo, "config", "core.hooksPath", ".mine/hooks")
            self.assertNotEqual(before["git"], _snap(repo)["git"])

    def test_an_ordinary_run_leaves_the_git_surface_identical(self):
        """SIBLING, and the one that keeps this from crying wolf: a role doing
        exactly its job must not perturb the surface. If it did, every tick
        would report a `.git` change and the real one would be invisible."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            before = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "2026-07-28\n")
            write_text(repo_path(repo, INBOX_PREFIX + "note.md"), "заметка\n")
            git(repo, "add", STATE_PREFIX + "seen.txt")
            self.assertEqual(before["git"], _snap(repo)["git"])

    def test_the_git_surface_is_stable_across_repeated_snapshots(self):
        """SIBLING — the surface must be a digest of state, not of the moment
        it was read, or every comparison is a false positive."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            self.assertEqual(_snap(repo)["git"], _snap(repo)["git"])


# ==========================================================================
# malformed snapshots — untrusted input to the guard
# ==========================================================================

class MalformedSnapshotTests(unittest.TestCase):
    """A snapshot is JSON read back from a file in the OS temp directory. It
    can be truncated by a crash, or be a leftover from another version.

    Two things must hold for every shape: no traceback, and no silent garbage
    attribution. Returning «nothing was touched» from a snapshot the guard
    could not read is the worse of the two — it reports a clean run.
    """

    BAD_SHAPES = (
        ("a list, not an object", []),
        ("entries is a string", {"head": "a" * 40, "entries": "not-a-dict"}),
        ("entries is a list", {"head": "a" * 40, "entries": ["x"]}),
        ("digest is an integer", {"head": "a" * 40, "entries": {"a.md": 12345}}),
        ("digest is null", {"head": "a" * 40, "entries": {"a.md": None}}),
        ("head is missing", {"entries": {}}),
        ("head is a number", {"head": 12345, "entries": {}}),
        ("entries is missing", {"head": "a" * 40}),
        ("empty object", {}),
    )

    def test_a_malformed_tick_baseline_does_not_suppress_the_remedy(self):
        """The role snapshot is sound and a rogue file was written after it,
        so the remedy is owed regardless of what the TICK baseline looks like
        — since §3.3 the baseline only labels the report. A malformed one must
        not turn a violation into a clean run."""
        for label, shape in self.BAD_SHAPES:
            with self.subTest(shape=label):
                with tempfile.TemporaryDirectory() as tmp:
                    repo = init_repo(Path(tmp))
                    good = _snap(repo)
                    write_text(repo_path(repo, "zettelkasten/1_projects/rogue.md"),
                               "rogue\n")
                    try:
                        result = _check(repo, shape, good)
                    except (TypeError, AttributeError, KeyError, IndexError) as exc:
                        self.fail(f"{label}: raw traceback {type(exc).__name__}: {exc}")
                    except Exception:
                        continue          # a deliberate, typed refusal is fine
                    self.assertNotEqual(
                        result["reverted"], [],
                        f"{label}: reported a clean run from an unreadable snapshot",
                    )

    def test_a_malformed_role_snapshot_does_not_silently_attribute_nothing(self):
        for label, shape in self.BAD_SHAPES:
            with self.subTest(shape=label):
                with tempfile.TemporaryDirectory() as tmp:
                    repo = init_repo(Path(tmp))
                    write_text(repo_path(repo, "zettelkasten/1_projects/rogue.md"),
                               "rogue\n")
                    try:
                        touched = guard.attribute(shape, _snap(repo))
                    except (TypeError, AttributeError, KeyError, IndexError) as exc:
                        self.fail(f"{label}: raw traceback {type(exc).__name__}: {exc}")
                    except Exception:
                        continue
                    self.assertIn("zettelkasten/1_projects/rogue.md", touched,
                                  f"{label}: the change vanished")

    def test_a_well_formed_snapshot_is_still_accepted(self):
        """SIBLING — the validation must not start refusing real snapshots."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "2026-07-28\n")
            self.assertEqual(_check(repo, tick, snap)["reverted"], [])

    def test_a_snapshot_round_trips_through_json(self):
        """SIBLING — the CLI writes it to a file and reads it back, so the
        shape the guard produces must survive that trip unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_text(repo_path(repo, STATE_PREFIX + "seen.txt"), "x\n")
            snap = _snap(repo)
            self.assertEqual(json.loads(json.dumps(snap)), snap)


# ==========================================================================
# check() contract
# ==========================================================================

class CheckContractTests(unittest.TestCase):
    KEYS = ("in_zone", "reverted", "reported_only", "secret_leak", "head_moved", "failed")

    def test_check_returns_every_contract_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            snap = _snap(repo)
            result = _check(repo, snap, snap)
            for key in self.KEYS:
                self.assertIn(key, result)
            self.assertIs(result["head_moved"], False)
            for key in ("in_zone", "reverted", "reported_only", "secret_leak", "failed"):
                self.assertIsInstance(result[key], list)

    def test_check_result_is_json_serialisable(self):
        """The CLI prints it verbatim (§7), so no field may be a Path or a set."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, "zettelkasten/1_projects/rogue.md"), "rogue\n")
            json.dumps(_check(repo, tick, snap))

    def test_check_takes_prefixes_not_a_role_config(self):
        """§3 API: the guard must not depend on `RoleConfig`, and its tests
        must not have to build one. It does take `WritePrefix` — the flatness
        of a prefix is a property of the prefix (§3.5), not a second copy of
        the inbox path."""
        params = list(inspect.signature(guard.check).parameters)
        self.assertIn("prefixes", params)
        self.assertNotIn("cfg", params)
        self.assertNotIn("config", params)

    def test_check_counts_every_in_zone_path_it_saw(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, STATE_PREFIX + "a.md"), "a\n")
            write_text(repo_path(repo, STATE_PREFIX + "b.md"), "b\n")
            self.assertEqual(len(_check(repo, tick, snap)["in_zone"]), 2)

    def test_reverted_paths_are_posix_and_repo_relative(self):
        rogue = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick = _snap(repo)
            snap = _snap(repo)
            write_text(repo_path(repo, rogue), "rogue\n")
            for path in _check(repo, tick, snap)["reverted"]:
                self.assertNotIn("\\", path)
                self.assertIsNone(re.match(r"^([a-zA-Z]:)?/", path))


class GuardInputIsNotRoleWritableTests(unittest.TestCase):
    """The guard's model is «the repository is what `git status` prints».

    Every test here is a way a role edited that sentence instead of working
    within it — making the guard's INPUT, not its logic, the thing that failed.
    Each one was reachable, each left a payload on disk with every field of the
    report reading clean, and each is a one-liner for a role with a shell.
    """

    PAYLOAD = "zettelkasten/2_areas/payload.md"

    def _prepared(self, tmp):
        repo = init_repo(Path(tmp))
        write_text(repo_path(repo, "zettelkasten/2_areas/seed.md"), "seed\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "seed")
        return repo

    def test_an_untracked_gitignore_cannot_hide_a_payload(self):
        """A `.gitignore` a role CREATES is untracked, and `*` matches itself —
        so listing ignore files from the index found neither the rule nor what
        it hid, and `check` returned every field empty."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._prepared(tmp)
            tick, snap = _snap(repo), _snap(repo)
            write_text(repo_path(repo, self.PAYLOAD), "payload\n")
            write_text(repo_path(repo, "zettelkasten/2_areas/.gitignore"), "*\n")
            result = _check(repo, tick, snap)
            self.assertIn(self.PAYLOAD, result["reverted"])
            self.assertFalse(repo_path(repo, self.PAYLOAD).exists())
            # The rule itself is reverted AND recorded. Repairing it silently
            # would leave the run reporting a spotless tree with no trace that
            # a role touched the one surface the guard's model rests on.
            self.assertIn("zettelkasten/2_areas/.gitignore", result["reverted"])

    def test_a_global_excludes_file_is_a_surface_change(self):
        """`core.excludesFile` set at GLOBAL scope lives outside the repository,
        survives every clone of it, and silenced the guard for every future
        tick while leaving nothing in the repo to notice."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._prepared(tmp)
            home = Path(tmp) / "home"
            home.mkdir()
            gcfg, excl = home / "gitconfig", home / "excludes"
            write_text(gcfg, "")
            write_text(excl, "payload.md\n")
            # `git_surface` shells out with the AMBIENT environment, so the
            # redirect has to be in `os.environ` for the whole window — and
            # redirected, never the real one, or the test would edit the
            # developer's own global git config.
            saved = {k: os.environ.get(k) for k in ("HOME", "GIT_CONFIG_GLOBAL")}
            os.environ["HOME"] = str(home)
            os.environ["GIT_CONFIG_GLOBAL"] = str(gcfg)
            try:
                before = guard.git_surface(repo)
                subprocess.run(["git", "-C", str(repo), "config", "--global",
                                "core.excludesFile", str(excl)],
                               check=True, capture_output=True)
                delta = guard.surface_delta(before, guard.git_surface(repo))
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            self.assertIn("excludes_file", delta)
            self.assertEqual(delta["excludes_file"]["after"]["value"], str(excl))

    def test_a_planted_hook_is_a_surface_change(self):
        """The hooks PATH was watched; the hooks were not — and the tick runs
        `git commit` per role, so a planted `post-commit` executes inside the
        tick's own process, which is where `MINDER_MEMORY_ROLES_KEY` lives."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._prepared(tmp)
            before = guard.git_surface(repo)
            hook = repo / ".git" / "hooks" / "post-commit"
            write_text(hook, "#!/bin/sh\necho x\n")
            hook.chmod(0o755)
            delta = guard.surface_delta(before, guard.git_surface(repo))
            self.assertIn("hooks", delta)
            self.assertIn("post-commit", delta["hooks"]["after"])

    def test_shipped_hook_samples_are_not_a_surface_change(self):
        """SIBLING — every clone ships `*.sample` hooks and none is ever
        executed. Digesting them would make an alarm fire on every tick, which
        is how a real alarm stops being read."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._prepared(tmp)
            samples = list((repo / ".git" / "hooks").glob("*.sample"))
            self.assertTrue(samples, "fixture assumption: git ships samples")
            self.assertEqual(guard.git_surface(repo)["hooks"], {})

    def test_an_unchanged_repository_yields_no_surface_delta(self):
        """SIBLING — the accepts case for all of the above. A surface that
        reported drift on a quiet repo would abort every tick forever."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._prepared(tmp)
            self.assertEqual(
                guard.surface_delta(guard.git_surface(repo), guard.git_surface(repo)), {})

    def test_reverting_an_ignore_file_does_not_forfeit_the_remedy(self):
        """The branch that reverts an ignore file and re-attributes used to
        re-add an `ignore` key to `delta` afterwards, which made `delta`
        permanently truthy: the abort fired, the remedy never ran, and the
        payload it had just correctly attributed stayed on disk. It also handed
        the CLARIFICATION `{before: null, after: null}` where the spec demands
        which file changed and how."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._prepared(tmp)
            tick, snap = _snap(repo), _snap(repo)
            write_text(repo_path(repo, self.PAYLOAD), "payload\n")
            write_text(repo_path(repo, ".gitignore"), "zettelkasten/2_areas/payload.md\n")
            result = _check(repo, tick, snap)
            self.assertFalse(result["git_surface"])
            self.assertIn(self.PAYLOAD, result["reverted"])
            self.assertIn(".gitignore", result["reverted"])
            self.assertFalse(repo_path(repo, self.PAYLOAD).exists())


class LeakScanReadsUndecodableFilesTests(unittest.TestCase):
    """§3.6 — one stray byte used to be a complete bypass of the scan.

    `read_text` raised `UnicodeDecodeError`, the loop skipped the file, and it
    stayed in `in_zone` — which is the tick's staging set. So the credential was
    committed with `[scheduled]` and pushed, and `hold-back` never saw it.
    """

    REL = "zettelkasten/_system/roles/notion/state/leak.md"

    def test_a_leading_invalid_byte_does_not_hide_a_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            target = repo_path(repo, self.REL)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\xff exfil: " + SECRET_VALUE.encode() + b"\n")
            self.assertEqual(
                guard.scan_secrets(repo, [self.REL], [SECRET_VALUE]), [self.REL])

    def test_a_clean_undecodable_file_is_still_not_a_finding(self):
        """SIBLING — the accepts case. Binary content that holds no credential
        must not be flagged, or every image a role saves is destroyed."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            target = repo_path(repo, self.REL)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\xff\xfe binary, no secret here \x00\x01")
            self.assertEqual(guard.scan_secrets(repo, [self.REL], [SECRET_VALUE]), [])


# ==========================================================================
# the ignore surface, judged by consequence
# ==========================================================================

class IgnoreConsequenceTests(unittest.TestCase):
    """An ignore rule is answered by ATTRIBUTION, never by stopping the tick.

    The veto had exactly one job: `git status` omits an ignored path, so a
    rule added mid-run moved a write outside everything the guard reads. That
    is a blind spot in attribution — and a blind spot is closed by looking.
    `newly_hidden` names what went invisible, each path is digested, scanned
    and reported under the `ignored` label, and hiding therefore buys a role
    nothing: a hidden write is handled exactly as the same write in plain
    sight would have been.

    With the gap closed the veto had no remaining job, and it had a real cost.
    `.git/info/exclude` belongs to the harness hosting the tick, which writes
    its own runtime files and rules there DURING a role's run — so the abort
    fired on ordinary nights, and an abort that fires on ordinary nights stops
    being read while still taking down every role queued behind it.

    These tests hold all of it: nothing hides from the report, nothing is
    deleted, and every other field on the surface keeps its absolute veto.
    """

    STATE = f"{STATE_PREFIX}note.md"

    def _exclude(self, repo: Path) -> Path:
        path = repo / ".git" / "info" / "exclude"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_deleting_an_exclude_file_is_reported_not_aborted(self):
        """The real nightly failure: the host rewrites `.git/info/exclude`
        (unlink + recreate) and the guard sampled the gap. Removing an ignore
        source makes MORE of the tree visible, so it can hide nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            exclude = self._exclude(repo)
            exclude.write_text("host-runtime.lock\n", encoding="utf-8")
            (repo / "host-runtime.lock").write_text("x\n", encoding="utf-8")

            tick, snap = _snap(repo), _snap(repo)
            write_text(repo_path(repo, self.STATE), "работа роли\n")
            exclude.unlink()

            result = _check(repo, tick, snap)
            self.assertFalse(result["git_surface"], "must not abort — nothing was hidden")
            self.assertTrue(result["ignore_changed"], "but it is still reported")
            self.assertEqual(result["ignore_changed"]["hidden"], [])
            self.assertIn(self.STATE, result["in_zone"], "the role's own write still lands")

    def test_a_payload_hidden_behind_a_new_rule_is_reported_not_lost(self):
        """SIBLING — the attack the field exists for. A role writes a payload
        and adds the rule that hides it from `git status` in the same run.

        The tick is not stopped, and that is the point: the payload is named
        in the report, so hiding it achieved nothing. What a role gains by the
        rule is exactly what it would have gained by writing the file in plain
        sight — a `reported_only` entry the owner reads in the morning."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick, snap = _snap(repo), _snap(repo)

            (repo / "payload.txt").write_text("exfiltrated\n", encoding="utf-8")
            self._exclude(repo).write_text("payload.txt\n", encoding="utf-8")

            result = _check(repo, tick, snap)
            self.assertFalse(result["git_surface"], "attribution replaced the veto")
            self.assertIn("payload.txt", result["ignore_changed"]["hidden"])
            self.assertIn("payload.txt", _report_paths(result),
                          "the hidden write must still reach the owner's report")
            self.assertEqual(
                [entry["held_by"] for entry in result["reported_only"]
                 if entry["path"] == "payload.txt"],
                ["ignored"], "and it must say WHY it was left alone")

    def test_a_hidden_payload_carrying_a_credential_is_still_a_leak(self):
        """SIBLING, and the one that matters most. Hiding must not buy a role
        the one thing the guard exists to catch. The file is scanned wherever
        it is — but it is NOT deleted, because a leak makes a path tempting to
        remove and this is precisely the path whose author is unknown."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            write_secrets(repo_base(repo), {"NOTION_TOKEN": SECRET_VALUE})
            tick, snap = _snap(repo), _snap(repo)

            (repo / "stash.txt").write_text(f"{SECRET_VALUE}\n", encoding="utf-8")
            self._exclude(repo).write_text("stash.txt\n", encoding="utf-8")

            result = _check(repo, tick, snap)
            self.assertIn("stash.txt", result["secret_leak"])
            self.assertTrue((repo / "stash.txt").exists(),
                            "a path the guard cannot attribute is never deleted")

    def test_a_file_the_host_creates_mid_run_does_not_stop_the_tick(self):
        """REGRESSION, 2026-08-11. The scheduler harness created its own lock
        file and added the rule for it WHILE the role ran. The file was in no
        snapshot — nothing could have listed it — so it read as a payload the
        role had hidden, and the tick stopped dispatching on an ordinary
        night. Reported, and the loop carries on."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick, snap = _snap(repo), _snap(repo)

            write_text(repo_path(repo, self.STATE), "работа роли\n")
            (repo / "scheduled_tasks.lock").write_text("held\n", encoding="utf-8")
            self._exclude(repo).write_text("scheduled_tasks.lock\n", encoding="utf-8")

            result = _check(repo, tick, snap)
            self.assertFalse(result["git_surface"], "an ordinary night must not abort")
            self.assertIn(self.STATE, result["in_zone"], "the role's own work still lands")
            self.assertIn("scheduled_tasks.lock", result["ignore_changed"]["hidden"])
            self.assertTrue((repo / "scheduled_tasks.lock").exists(),
                            "the host's live lock file must survive the check")

    def test_the_guard_never_deletes_the_hosts_exclude_file(self):
        """The other half of the same night. `.git/info/exclude` is absent from
        the role snapshot, and the remedy read that as «untracked → deleting it
        restores the previous state» — so it deleted git's own file, which no
        role owns and which the guard promises never to touch."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            exclude = self._exclude(repo)
            tick, snap = _snap(repo), _snap(repo)
            exclude.write_text("host-runtime.lock\n", encoding="utf-8")

            _check(repo, tick, snap)
            self.assertTrue(exclude.exists(), "the host's ignore file must survive")
            self.assertEqual(exclude.read_text(encoding="utf-8"), "host-runtime.lock\n")

    def test_a_path_visible_before_the_run_is_not_a_hidden_payload(self):
        """The host adds a runtime entry mid-run that hides its own lock file.
        The file was on disk and visible when the role started, so the role
        cannot have hidden its own payload behind it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            (repo / "host-runtime.lock").write_text("held\n", encoding="utf-8")
            tick, snap = _snap(repo), _snap(repo)

            self._exclude(repo).write_text("host-runtime.lock\n", encoding="utf-8")

            result = _check(repo, tick, snap)
            self.assertFalse(result["git_surface"], "pre-existing file, not a payload")
            self.assertEqual(result["ignore_changed"]["hidden"], [])

    def test_a_second_field_keeps_its_absolute_veto(self):
        """SIBLING — the softening is scoped to `ignore` alone. A remote has
        no benign author here, so it aborts even alongside a harmless one."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            exclude = self._exclude(repo)
            exclude.write_text("host-runtime.lock\n", encoding="utf-8")
            tick, snap = _snap(repo), _snap(repo)

            exclude.unlink()
            git(repo, "remote", "add", "exfil", "https://attacker.invalid/x.git")

            result = _check(repo, tick, snap)
            self.assertTrue(result["git_surface"])
            self.assertIn("remotes", result["git_surface"])

    def test_an_ordinary_run_reports_no_ignore_change(self):
        """SIBLING — the field must not manufacture a finding on a quiet night."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            tick, snap = _snap(repo), _snap(repo)
            write_text(repo_path(repo, self.STATE), "обычная запись\n")
            result = _check(repo, tick, snap)
            self.assertFalse(result["ignore_changed"])
            self.assertFalse(result["git_surface"])

    def test_a_snapshot_without_the_field_keeps_the_strict_verdict(self):
        """A tick that began before this field existed must not have its
        ignore change read as safe — absence of evidence is not evidence."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            exclude = self._exclude(repo)
            exclude.write_text("host-runtime.lock\n", encoding="utf-8")
            tick, snap = _snap(repo), _snap(repo)
            snap.pop("ignored")

            exclude.unlink()
            result = _check(repo, tick, snap)
            self.assertTrue(result["git_surface"], "cannot tell → stay conservative")

    def test_the_ignored_listing_never_leaks_into_attribution(self):
        """An ignored path is not a write the role is accountable for — it was
        already invisible before the run, and counting it would revert build
        output the guard has no business touching."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            self._exclude(repo).write_text("cache/\n", encoding="utf-8")
            tick, snap = _snap(repo), _snap(repo)

            (repo / "cache").mkdir()
            (repo / "cache" / "art.bin").write_text("build output\n", encoding="utf-8")

            result = _check(repo, tick, snap)
            self.assertEqual(result["reverted"], [])
            self.assertNotIn("cache/art.bin", result["in_zone"] + result["reported_only"])


if __name__ == "__main__":
    unittest.main()
