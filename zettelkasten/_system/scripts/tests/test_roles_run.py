"""Tests for roles_run — the CLI and the tick contract (CORE-SPEC §7).

Proves each verb's contract end to end against a throwaway git repo: `due`
reports EVERY role with an explicit boolean so "not due" and "missing" are
never confused, `tick-begin` / `role-begin` put their snapshots outside the
repo, `check` still classifies after a crash, `log` appends one line, and
`validate` reads only the KEY names from the secrets file and never prints a
value under any flag.

`roles_run` composes and owns no domain logic (§0/§7), which is asserted
directly rather than left as an aspiration.

Entry point `main(argv: list[str] | None = None) -> int` (§7), matching the
suite's existing scripts. `_cli` below tolerates either a return code or
`SystemExit`, so an argparse-native implementation passes unchanged.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import sys

import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from tests._roles_fixture import (  # type: ignore
    KEY_ENV,
    generate_key,
    git,
    init_repo,
    key_env,
    porcelain_z,
    purge_roles_tmp,
    read_text,
    repo_base,
    repo_path,
    roles_dir,
    roles_tmp_entries,
    secrets_path,
    write_role,
    write_secrets,
    write_encrypted_store,
    write_state,
    write_text,
)
import roles_run as run  # type: ignore

NOW = "2026-07-28T07:00:00+00:00"
STATE_PREFIX = "zettelkasten/_system/roles/notion-sync/state/"

# §3.6: a secret value must be >= 12 characters to be leak-scannable, so every
# fixture that expects a CLEAN validate uses one at or above the floor. The
# floor is a property of the VALUE; nothing here may be separable by the length
# of the NAME, or a validator could pass the suite by keying on the wrong one.
GOOD_SECRET = "healthy-token-1234"     # 18 chars — scannable
SHORT_SECRET = "sunshine"              # 8 chars  — below the floor


@contextlib.contextmanager
def _in_dir(path):
    """Run a block with the process CWD moved, always restoring it.

    pytest runs the whole suite in one process, so a test that leaves the CWD
    inside a `TemporaryDirectory` breaks every test after it once that
    directory is removed. The restore is in a `finally` for that reason, and
    `test_the_cwd_is_restored_after_a_relative_base_run` asserts it.
    """
    previous = os.getcwd()
    os.chdir(str(path))
    try:
        yield
    finally:
        os.chdir(previous)


def _cli(argv: list[str], cwd=None):
    """Run the CLI in-process; returns `(rc, stdout, stderr)`.

    Tolerates both `return 2` and `raise SystemExit(2)` so the test does not
    prescribe argparse-vs-manual error handling. `cwd` moves the process there
    for the call, which is what makes a relative `--base` mean anything.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        if cwd is not None:
            stack.enter_context(_in_dir(cwd))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        try:
            rc = run.main(argv)
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
    return (0 if rc is None else rc), out.getvalue(), err.getvalue()


def _json(argv: list[str], cwd=None, expect_rc: int = 0):
    """Run a JSON verb and return the decoded payload, pinning the exit code.

    The caller states the code it expects, because the exit code is part of
    the contract and not a property of "being JSON". `validate` exits
    `EXIT_FINDINGS` (1) when `ok` is false, so a base with an unresolvable
    credential cannot look clean to a caller testing `$?` — which is exactly
    what the concierge's first gate does. That is kept distinct from
    `EXIT_ERROR` (2), «the verb could not run».

    Deliberately not `assert rc in (0, 1)`: that would stop distinguishing the
    two cases and let a real regression through. A test that expects findings
    says so here, in the same breath as asserting `ok` is false.
    """
    rc, out, err = _cli(argv, cwd=cwd)
    assert rc == expect_rc, f"rc={rc} (expected {expect_rc}) stderr={err}"
    return json.loads(out)


def _write_run_frame(base: Path) -> Path:
    """A placeholder-complete `_run-frame.md`, as wave 1 ships it."""
    return write_text(roles_dir(base) / "_run-frame.md",
                      "role_id: {{ROLE_ID}}\nrole_name: {{ROLE_NAME}}\n"
                      "repo_root: {{REPO_ROOT}}\nbase: {{BASE}}\n"
                      "state_dir: {{STATE_DIR}}\n"
                      "allowed_writes: {{ALLOWED_WRITES}}\n"
                      "secrets_file: {{SECRETS_FILE}}\n"
                      "secret_names: {{SECRET_NAMES}}\nnow_local: {{NOW_LOCAL}}\n"
                      "last_run: {{LAST_RUN}}\n")


def _seed(tmp, **role_kwargs) -> tuple[Path, Path]:
    """A repo whose base carries one healthy role plus the engine files.

    The default cadence is deliberately ANCHOR-FREE. A time anchor is a
    legitimate shape but it carries a §2.1 note, so a fixture that anchored by
    default would make every «healthy base» assertion carry a finding and the
    note-specific tests indistinguishable from the baseline. Tests that care
    about anchors ask for one explicitly.
    """
    repo = init_repo(Path(tmp))
    base = repo_base(repo)
    kwargs = {"writes": "[state]", "cadence": "daily"}
    kwargs.update(role_kwargs)
    write_role(base, "notion-sync", **kwargs)
    _write_run_frame(base)
    return repo, base


def _by_id(rows: list[dict]) -> dict:
    return {row["id"]: row for row in rows}


class RolesCliTestCase(unittest.TestCase):
    """Base case that leaves the OS temp directory exactly as it found it.

    `tick-begin` / `role-begin` write snapshots under a per-tick directory in
    the OS temp dir (§7). The tick removes it in wave 2 — but the SUITE must
    not rely on wave 2 to stay clean, or every run silently accretes a
    `minder-mem-roles-*` directory and a later run could read stale state from one.

    Two layers, and the first is what matters:

    1. **Isolation.** Each test redirects `tempfile.tempdir`, which is what
       `roles_run` resolves the snapshot directory from, into a private
       directory. Nothing the CLI writes can reach the developer's real temp
       dir, and — the reason this exists rather than a purge alone — no test
       can see or delete another test's snapshot directory.

       A purge alone was not enough, observed by execution: two consecutive
       runs of the same files produced different failures. Every test shared
       one global directory that they all both wrote to and deleted from, so a
       result depended on what happened to be lying in it — leftovers from an
       earlier run, or a real tick in flight in another process. Isolation
       removes the shared state instead of tidying it.
    2. **Purge.** Belt and braces for anything that escaped isolation.

    `TempDirHygieneTests` asserts both layers actually work.
    """

    def setUp(self) -> None:
        self._tmp_home = tempfile.TemporaryDirectory(prefix="roles-suite-tmp-")
        self._tmp_restore = tempfile.tempdir
        tempfile.tempdir = self._tmp_home.name
        self._tmp_before = roles_tmp_entries()

    def tearDown(self) -> None:
        try:
            purge_roles_tmp(self._tmp_before)
        finally:
            tempfile.tempdir = self._tmp_restore
            self._tmp_home.cleanup()


# ==========================================================================
# due
# ==========================================================================

class DueTests(RolesCliTestCase):
    def test_due_reports_every_role_with_an_explicit_boolean(self):
        """§7: "not due" and "missing" must never be confused."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="every tick")
            write_role(base, "sleepy", role_id="sleepy", cadence='"monthly 15"')
            rows = _json(["due", "--base", str(base), "--repo", str(repo), "--now", NOW])
            by_id = _by_id(rows)
            self.assertEqual(set(by_id), {"notion-sync", "sleepy"})
            for row in rows:
                self.assertEqual(set(row) & {"id", "name", "due", "reason", "status"},
                                 {"id", "name", "due", "reason", "status"})
                self.assertIsInstance(row["due"], bool)
                self.assertTrue(row["reason"].strip())
            self.assertTrue(by_id["notion-sync"]["due"])
            self.assertFalse(by_id["sleepy"]["due"])

    def test_due_reports_a_paused_role_as_not_due_with_its_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="every tick", status="paused")
            row = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                "--now", NOW]))["notion-sync"]
            self.assertFalse(row["due"])
            self.assertEqual(row["status"], "paused")

    def test_due_reports_an_active_due_role_as_due(self):
        """SIBLING — the whole point of the verb."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="every tick", status="active")
            row = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                "--now", NOW]))["notion-sync"]
            self.assertTrue(row["due"])
            self.assertEqual(row["status"], "active")

    def test_due_reports_a_malformed_role_as_not_due_with_the_error_as_reason(self):
        """§7: the tick surfaces it and continues; one broken role never
        aborts a tick."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="every tick")
            write_text(roles_dir(base) / "broken" / "role.md", "---\nid: [unclosed\n---\n")
            rc, out, _ = _cli(["due", "--base", str(base), "--repo", str(repo),
                               "--now", NOW])
            self.assertEqual(rc, 0)
            by_id = _by_id(json.loads(out))
            self.assertIn("broken", by_id)
            self.assertFalse(by_id["broken"]["due"])
            self.assertTrue(by_id["broken"]["reason"].strip())
            self.assertTrue(by_id["notion-sync"]["due"], "the healthy role still runs")

    def test_due_honours_the_injected_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 07:00"')
            early = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                  "--now", "2026-07-28T06:00:00+00:00"]))
            late = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                 "--now", "2026-07-28T08:00:00+00:00"]))
            self.assertFalse(early["notion-sync"]["due"])
            self.assertTrue(late["notion-sync"]["due"])

    def test_due_on_a_base_with_no_roles_returns_an_empty_list(self):
        """SIBLING — a base with no roles is normal, not an error."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            base = repo_base(repo)
            self.assertEqual(
                _json(["due", "--base", str(base), "--repo", str(repo), "--now", NOW]),
                [],
            )

    def test_due_writes_nothing_to_the_log(self):
        """§5: a role that was not due writes nothing. Logging a not-due skip
        would make `last_run` the most recent tick and freeze every cadence
        longer than the tick interval."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"monthly 15"')
            _json(["due", "--base", str(base), "--repo", str(repo), "--now", NOW])
            self.assertFalse((roles_dir(base) / "notion-sync" / "log.jsonl").exists())

    def test_due_does_not_mutate_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="every tick")
            before = sorted(p.name for p in (roles_dir(base) / "notion-sync").iterdir())
            _json(["due", "--base", str(base), "--repo", str(repo), "--now", NOW])
            after = sorted(p.name for p in (roles_dir(base) / "notion-sync").iterdir())
            self.assertEqual(before, after)


# ==========================================================================
# context
# ==========================================================================

class ContextTests(RolesCliTestCase):
    def test_context_prints_the_prompt_text_not_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            rc, out, err = _cli(["context", "--base", str(base), "--repo", str(repo),
                                 "--role", "notion-sync", "--now", NOW])
            self.assertEqual(rc, 0, err)
            self.assertIn("role_id: notion-sync", out)
            with self.assertRaises(json.JSONDecodeError):
                json.loads(out)

    def test_context_includes_the_roles_state_and_body(self):
        """SIBLING — a role with Cyrillic state and body is the normal case."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_state(base, "notion-sync", "расхождения.md", "открытых: 3\n")
            _, out, _ = _cli(["context", "--base", str(base), "--repo", str(repo),
                              "--role", "notion-sync", "--now", NOW])
            self.assertIn("открытых: 3", out)
            self.assertIn("## Задача", out)

    def test_context_for_an_unknown_role_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            rc, _, _ = _cli(["context", "--base", str(base), "--repo", str(repo),
                             "--role", "nope", "--now", NOW])
            self.assertNotEqual(rc, 0)

    def test_context_never_prints_a_secret_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": "secret-value-do-not-leak"})
            _, out, err = _cli(["context", "--base", str(base), "--repo", str(repo),
                                "--role", "notion-sync", "--now", NOW])
            self.assertIn("NOTION_TOKEN", out)
            self.assertNotIn("secret-value-do-not-leak", out + err)


# ==========================================================================
# tick-begin / role-begin / check
# ==========================================================================

class SnapshotVerbTests(RolesCliTestCase):
    def test_tick_begin_prints_the_file_it_wrote(self):
        """§7: both verbs print the path of the FILE they wrote — the tick
        derives the directory from it when it needs to clean up. Printing the
        directory instead would leave the tick guessing at the filename."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            rc, out, err = _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            self.assertEqual(rc, 0, err)
            printed = Path(out.strip())
            self.assertTrue(printed.is_file(), f"not a file: {printed}")
            self.assertTrue(printed.parent.is_dir())
            json.loads(printed.read_text(encoding="utf-8"))

    def test_tick_begin_writes_the_snapshot_outside_the_repository(self):
        """§7: nothing about the snapshots lands in the repo."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _, out, _ = _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            printed = Path(out.strip()).resolve()
            self.assertNotIn(str(repo.resolve()), str(printed))

    def test_role_begin_prints_the_file_it_wrote(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            rc, out, err = _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                                 "--role", "notion-sync"])
            self.assertEqual(rc, 0, err)
            printed = Path(out.strip())
            self.assertTrue(printed.is_file(), f"not a file: {printed}")
            json.loads(printed.read_text(encoding="utf-8"))

    def test_role_begin_writes_the_snapshot_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _, out, _ = _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                              "--role", "notion-sync"])
            printed = Path(out.strip()).resolve()
            self.assertNotIn(str(repo.resolve()), str(printed))

    def test_both_snapshot_files_share_one_per_tick_directory(self):
        """`check` locates the role snapshot by convention WITHIN the tick
        directory, so the two files must actually live in the same one."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _, tick_out, _ = _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _, role_out, _ = _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                                   "--role", "notion-sync"])
            tick_file, role_file = Path(tick_out.strip()), Path(role_out.strip())
            self.assertEqual(tick_file.parent.resolve(), role_file.parent.resolve())
            self.assertNotEqual(tick_file.resolve(), role_file.resolve())

    def test_two_roles_get_distinct_snapshot_files_in_the_same_directory(self):
        """SIBLING — a tick runs several roles in sequence; each needs its own
        snapshot, or role B is attributed against role A's starting point."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_role(base, "second-role", role_id="second-role", writes="[state]")
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _, a_out, _ = _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                                "--role", "notion-sync"])
            _, b_out, _ = _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                                "--role", "second-role"])
            a, b = Path(a_out.strip()), Path(b_out.strip())
            self.assertNotEqual(a.resolve(), b.resolve())
            self.assertEqual(a.parent.resolve(), b.parent.resolve())
            self.assertTrue(a.is_file())
            self.assertTrue(b.is_file())

    def test_snapshots_leave_the_working_tree_clean(self):
        """SIBLING — capturing state must not itself dirty the repo, or the
        next role inherits phantom changes."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            from tests._roles_fixture import git, porcelain_z  # local: fixture helpers
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "seed role")
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                  "--role", "notion-sync"])
            self.assertEqual(porcelain_z(repo), "")

    def test_check_returns_the_full_contract_and_reverts_out_of_zone(self):
        rogue = "zettelkasten/1_projects/rogue.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                  "--role", "notion-sync"])
            write_text(repo_path(repo, rogue), "rogue\n")
            result = _json(["check", "--base", str(base), "--repo", str(repo),
                            "--role", "notion-sync"])
            for key in ("in_zone", "reverted", "reported_only", "secret_leak",
                        "head_moved", "failed"):
                self.assertIn(key, result)
            self.assertEqual(result["reverted"], [rogue])
            self.assertFalse(repo_path(repo, rogue).exists())

    def test_check_after_a_crash_still_classifies(self):
        """§7.1(c): whatever the outcome — success, error, timeout, crash —
        `check` always runs, or that role's out-of-zone writes leak into the
        next role's snapshot and are attributed to nobody."""
        rogue = "zettelkasten/1_projects/half-written.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                  "--role", "notion-sync"])
            # the agent died mid-flight, leaving a partial out-of-zone write
            write_text(repo_path(repo, rogue), "half a thought\n")
            result = _json(["check", "--base", str(base), "--repo", str(repo),
                            "--role", "notion-sync"])
            self.assertEqual(result["reverted"], [rogue])

    def test_check_leaves_in_zone_writes_alone(self):
        """SIBLING — the ordinary successful run."""
        rel = STATE_PREFIX + "расхождения.md"
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                  "--role", "notion-sync"])
            write_text(repo_path(repo, rel), "открытых: 3\n")
            result = _json(["check", "--base", str(base), "--repo", str(repo),
                            "--role", "notion-sync"])
            self.assertEqual(result["reverted"], [])
            self.assertIn(rel, result["in_zone"])
            self.assertTrue(repo_path(repo, rel).exists())

    def test_check_without_a_prior_tick_begin_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            rc, _, _ = _cli(["check", "--base", str(base), "--repo", str(repo),
                             "--role", "notion-sync"])
            self.assertNotEqual(rc, 0)


# ==========================================================================
# log
# ==========================================================================

class LogVerbTests(RolesCliTestCase):
    def _entries(self, base: Path) -> list[dict]:
        path = roles_dir(base) / "notion-sync" / "log.jsonl"
        return [json.loads(ln) for ln in read_text(path).splitlines() if ln.strip()]

    def test_log_appends_one_line_with_the_given_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            rc, _, err = _cli(["log", "--base", str(base), "--role", "notion-sync",
                               "--outcome", "ok", "--ms", "41200",
                               "--ts", "2026-07-28T07:00:11+00:00"])
            self.assertEqual(rc, 0, err)
            entries = self._entries(base)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["outcome"], "ok")
            self.assertEqual(entries[0]["ms"], 41200)
            self.assertEqual(entries[0]["ts"], "2026-07-28T07:00:11Z")

    def test_log_defaults_writes_and_note_when_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "idle", "--ms", "800",
                  "--ts", "2026-07-28T07:00:11+00:00"])
            entry = self._entries(base)[0]
            self.assertEqual(entry["writes"], 0)
            self.assertIsNone(entry["note"])

    def test_log_accepts_a_cyrillic_note_with_spaces(self):
        """SIBLING — the note comes from the role's own structured return."""
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "idle", "--ms", "800", "--note", "доска не менялась",
                  "--ts", "2026-07-28T07:00:11+00:00"])
            self.assertEqual(self._entries(base)[0]["note"], "доска не менялась")

    def test_log_round_trips_reverted_and_reported_only(self):
        """§5/§7: without these flags the two fields would be permanently
        empty, and §3.3's promise — that the report-don't-revert choice is
        recorded every time it fires — would be unkeepable."""
        reverted = ["zettelkasten/1_projects/rogue.md"]
        reported = ["zettelkasten/1_projects/owner-wip.md"]
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            rc, _, err = _cli([
                "log", "--base", str(base), "--role", "notion-sync",
                "--outcome", "ok", "--ms", "1200", "--writes", "1",
                "--ts", "2026-07-28T07:00:11+00:00",
                "--reverted", json.dumps(reverted),
                "--reported-only", json.dumps(reported),
            ])
            self.assertEqual(rc, 0, err)
            entry = self._entries(base)[0]
            self.assertEqual(entry["reverted"], reverted)
            self.assertEqual(entry["reported_only"], reported)

    def test_log_defaults_both_path_lists_to_empty_when_omitted(self):
        """SIBLING — the overwhelmingly common clean run passes neither flag."""
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "ok", "--ms", "1200",
                  "--ts", "2026-07-28T07:00:11+00:00"])
            entry = self._entries(base)[0]
            self.assertEqual(entry["reverted"], [])
            self.assertEqual(entry["reported_only"], [])

    def test_log_accepts_an_explicitly_empty_json_list(self):
        """SIBLING — a tick that always passes the flags, even on a clean run,
        must not be punished for it."""
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            rc, _, err = _cli(["log", "--base", str(base), "--role", "notion-sync",
                               "--outcome", "ok", "--ms", "1",
                               "--ts", "2026-07-28T07:00:11+00:00",
                               "--reverted", "[]", "--reported-only", "[]"])
            self.assertEqual(rc, 0, err)
            self.assertEqual(self._entries(base)[0]["reverted"], [])

    def test_log_round_trips_a_cyrillic_path_through_the_json_flag(self):
        """SIBLING — a reverted path may be the owner's own filename, and it
        has to survive both the shell-free argv and the JSON decode."""
        paths = ["zettelkasten/_system/roles/notion-sync/state/расхождения.md"]
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "error", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00",
                  "--reverted", json.dumps(paths, ensure_ascii=False)])
            self.assertEqual(self._entries(base)[0]["reverted"], paths)

    def test_log_rejects_malformed_json_in_a_path_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            rc, _, _ = _cli(["log", "--base", str(base), "--role", "notion-sync",
                             "--outcome", "ok", "--ms", "1",
                             "--reverted", "not json at all"])
            self.assertNotEqual(rc, 0)

    def test_log_without_a_required_flag_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            rc, _, _ = _cli(["log", "--base", str(base), "--role", "notion-sync",
                             "--ms", "800"])
            self.assertNotEqual(rc, 0)

    def test_log_for_an_unknown_role_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            rc, _, _ = _cli(["log", "--base", str(base), "--role", "nope",
                             "--outcome", "ok", "--ms", "1"])
            self.assertNotEqual(rc, 0)


# ==========================================================================
# validate
# ==========================================================================

class ValidateTests(RolesCliTestCase):
    def test_validate_reports_ok_on_a_healthy_base(self):
        """SIBLING for every finding below — a correct base must come back
        clean, or the preflight is noise.

        The value is at or above the §3.6 scan floor on purpose: a short one
        would be a legitimate finding, and asserting `findings == []` over it
        would make this test and its short-secret sibling unsatisfiable
        together, whatever threshold an implementation chose."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET})
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"])
            self.assertEqual(result["findings"], [])

    def test_validate_reports_a_finding_for_an_id_dir_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_role(base, "mismatch", role_id="something-else")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertTrue(result["findings"])
            self.assertIn("mismatch", json.dumps(result, ensure_ascii=False))

    def test_validate_reports_a_finding_for_an_unparseable_cadence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_role(base, "bad-cadence", role_id="bad-cadence", cadence="fortnightly")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertIn("bad-cadence", json.dumps(result, ensure_ascii=False))

    def test_validate_reports_a_missing_declared_secret_when_the_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"SLACK_TOKEN": GOOD_SECRET})
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertIn("NOTION_TOKEN", json.dumps(result, ensure_ascii=False))

    def test_validate_reports_a_declared_secret_when_the_file_does_not_exist(self):
        """§7.2 — the absent-file case is the MOST likely one for a fresh
        clone, and skipping the check exactly there inverts the gate's purpose:
        the concierge sees `validate` clean, creates the role, and at 07:00 it
        gets an empty variable, a 401, and reports success."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            self.assertFalse(secrets_path(base).exists())
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            payload = json.dumps(result, ensure_ascii=False)
            self.assertIn("NOTION_TOKEN", payload)
            self.assertIn("notion-sync", payload)

    def test_validate_is_clean_for_a_role_declaring_no_secrets_with_no_file(self):
        """SIBLING, and the one that keeps §7.2 from becoming noise: the rule
        is about a DECLARED NAME having no resolvable value, never about the
        file's mere existence. Without this pair an implementer could satisfy
        the table by flagging every base that lacks the file — which is every
        base that needs no credentials."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            base = repo_base(repo)
            write_role(base, "watcher", role_id="watcher", cadence="hourly")
            self.assertFalse(secrets_path(base).exists())
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"])
            self.assertEqual(result["findings"], [])

    def test_validate_flags_only_the_declaring_role_when_the_file_is_absent(self):
        """A base where one role needs a credential and another does not: the
        finding lands on the first and the second is not swept up with it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_role(base, "watcher", role_id="watcher", cadence="hourly")
            self.assertFalse(secrets_path(base).exists())
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            findings = json.dumps(result["findings"], ensure_ascii=False)
            self.assertIn("notion-sync", findings)
            self.assertNotIn("watcher", findings)

    def test_validate_reports_an_unparseable_store_as_a_corrupt_blob(self):
        """§6.6 — a store that does not parse is a corrupt or TAMPERED blob,
        and is reported as that.

        The old finding was «a malformed line, with its line number», which
        made sense when the owner hand-wrote the file. Nobody hand-writes the
        store: it is JSON the engine renders. Pointing an owner at a line
        number inside ciphertext they never edited sends them to inspect the
        wrong thing entirely, and hides the possibility that someone else
        edited it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_text(base / "_system" / "state" / "secrets.enc.json", "not json {{{\n")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                           expect_rc=1)
            self.assertFalse(result["ok"])
            text = json.dumps(result, ensure_ascii=False).lower()
            self.assertIn("secrets.enc.json", text)
            self.assertTrue(
                any(w in text for w in ("corrupt", "tamper", "not valid json",
                                        "unreadable", "parse")),
                f"the finding does not say the blob is corrupt: {text}",
            )

    def test_the_corrupt_store_finding_is_not_framed_as_a_malformed_line(self):
        """SIBLING to the rule above, and the reason it is worth a test.

        The objection is to the FRAMING, not to diagnostics: `json` reports
        «line 1 column 1» of the blob it failed on, which is real information
        about a real file and worth keeping. What must not survive is the old
        wording — «malformed line N in your secrets file» — because it tells
        an owner to go and edit a line of a file they never wrote, and buries
        the possibility that someone else edited it.

        A store that happens to hold the OLD plaintext format is the sharpest
        case: it looks exactly like the thing the old message described."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_text(base / "_system" / "state" / "secrets.enc.json",
                       "NOTION_TOKEN=looks-like-the-old-format\n")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                           expect_rc=1)
            store_findings = [f for f in result["findings"]
                              if "secrets.enc.json" in json.dumps(f, ensure_ascii=False)]
            self.assertTrue(store_findings)
            text = json.dumps(store_findings, ensure_ascii=False).lower()
            self.assertIn("corrupt", text)
            self.assertNotIn("malformed line", text)
            self.assertNotIn("secrets file", text)

    def test_validate_accepts_a_well_formed_store(self):
        """SIBLING — a real store must not be read as corrupt."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET})
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False))

    def test_validate_never_emits_a_value_when_the_store_is_unparseable(self):
        """A parser error is exactly where a naive implementation dumps the
        offending text as context."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET})
            store = base / "_system" / "state" / "secrets.enc.json"
            write_text(store, store.read_text(encoding="utf-8") + "trailing garbage")
            _, out, err = _cli(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertNotIn(GOOD_SECRET, out + err)

    def test_validate_never_prints_a_secret_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": "secret-value-do-not-leak"})
            _, out, err = _cli(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertNotIn("secret-value-do-not-leak", out + err)

    def test_validate_never_prints_a_secret_value_even_when_reporting_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN, MISSING_ONE]")
            write_secrets(base, {"NOTION_TOKEN": "secret-value-do-not-leak"})
            _, out, err = _cli(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertIn("MISSING_ONE", out + err)
            self.assertNotIn("secret-value-do-not-leak", out + err)

    def test_validate_scopes_to_one_role_with_the_role_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_role(base, "bad-cadence", role_id="bad-cadence", cadence="fortnightly")
            scoped = _json(["validate", "--base", str(base), "--repo", str(repo),
                            "--role", "notion-sync"])
            self.assertTrue(scoped["ok"])
            whole = _json(["validate", "--base", str(base), "--repo", str(repo)],
                          expect_rc=1)
            self.assertFalse(whole["ok"])

    def test_validate_reports_a_secret_value_below_the_scan_length_floor(self):
        """§3.6: a value shorter than 12 characters is not scanned, and
        `validate` reports that on the declaring role — "this credential
        cannot be leak-scanned", surfaced at creation rather than as a silent
        gap at 07:00."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[WEAK_TOKEN]")
            write_secrets(base, {"WEAK_TOKEN": SHORT_SECRET})
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            payload = json.dumps(result, ensure_ascii=False)
            self.assertIn("WEAK_TOKEN", payload)
            self.assertIn("notion-sync", payload)

    def test_validate_names_the_declaring_role_for_a_short_secret(self):
        """The finding lands on the role that DECLARES it, not on the secrets
        file — the owner fixes it by rotating that role's credential."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_role(base, "weak-role", role_id="weak-role", secrets="[WEAK_TOKEN]")
            write_secrets(base, {"WEAK_TOKEN": SHORT_SECRET})
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertIn("weak-role", json.dumps(result, ensure_ascii=False))

    def test_validate_accepts_a_secret_value_at_the_length_floor(self):
        """SIBLING — exactly 12 characters is scannable, so no finding."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": "abcdefghijkl"})
            self.assertTrue(
                _json(["validate", "--base", str(base), "--repo", str(repo)])["ok"]
            )

    def test_validate_accepts_a_short_NAME_with_a_long_value(self):
        """SIBLING and a decoupling test: the floor is a property of the VALUE.
        A one-character name with an 18-character value is fine. Together with
        its partner below, this makes it impossible for an implementation to
        satisfy the suite by measuring the wrong string."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[T]")
            write_secrets(base, {"T": GOOD_SECRET})
            self.assertTrue(
                _json(["validate", "--base", str(base), "--repo", str(repo)])["ok"]
            )

    def test_validate_reports_a_long_NAME_with_a_short_value(self):
        """The partner: a 29-character name over an 8-character value is still
        a finding, because the name was never what mattered."""
        name = "A_VERY_LONG_TOKEN_NAME_INDEED"
        self.assertGreater(len(name), len(GOOD_SECRET))
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets=f"[{name}]")
            write_secrets(base, {name: SHORT_SECRET})
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertIn(name, json.dumps(result, ensure_ascii=False))

    def test_validate_never_prints_a_short_secret_value_it_complains_about(self):
        """The finding says the credential is too short; printing it to prove
        the point would put a live credential in a log."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[WEAK_TOKEN]")
            write_secrets(base, {"WEAK_TOKEN": SHORT_SECRET})
            _, out, err = _cli(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertIn("WEAK_TOKEN", out + err)
            self.assertNotIn("sunshine", out + err)

    def test_validate_reports_an_out_of_range_timeout(self):
        """§1 — `timeout_seconds` is 1..86400."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_role(base, "slowpoke", role_id="slowpoke", timeout_seconds="0")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertIn("slowpoke", json.dumps(result, ensure_ascii=False))

    def test_validate_accepts_a_role_with_a_custom_timeout(self):
        """SIBLING — a long-running role declaring its own bound is the point
        of the key, not a defect."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, timeout_seconds="3600")
            self.assertTrue(
                _json(["validate", "--base", str(base), "--repo", str(repo)])["ok"]
            )

    def test_validate_reports_an_invalid_writes_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_role(base, "escaper", role_id="escaper", writes='["/etc/cron.d/"]')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertIn("escaper", json.dumps(result, ensure_ascii=False))

    def test_validate_accepts_a_role_with_no_secrets_and_no_writes(self):
        """SIBLING — a read-only role with no credentials is legitimate."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            base = repo_base(repo)
            write_role(base, "watcher", role_id="watcher", cadence="hourly")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"])

    def test_validate_reports_a_role_whose_config_does_not_load(self):
        """§7.2 — named per role, with the defect. A malformed role must not
        pass preflight by being unreadable."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_text(roles_dir(base) / "broken" / "role.md", "---\nid: [unclosed\n---\n")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            self.assertIn("broken", json.dumps(result, ensure_ascii=False))

    def test_validate_reports_every_condition_in_one_pass(self):
        """§7.2's table is a set of unconditional findings, not a first-match
        ladder: a base with three different defects reports all three, or the
        owner fixes one and is surprised twice more."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_role(base, "bad-cadence", role_id="bad-cadence", cadence="fortnightly")
            write_role(base, "weak", role_id="weak", secrets="[WEAK_TOKEN]")
            write_secrets(base, {"WEAK_TOKEN": SHORT_SECRET})
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            payload = json.dumps(result, ensure_ascii=False)
            self.assertIn("NOTION_TOKEN", payload)   # declared, absent from the file
            self.assertIn("bad-cadence", payload)    # config does not load
            self.assertIn("WEAK_TOKEN", payload)     # below the scan floor
            self.assertGreaterEqual(len(result["findings"]), 3)

    def test_validate_touches_no_network(self):
        """§7: reachability is the concierge's trial run, not a deterministic
        check. A validate that hits the network is non-deterministic and fails
        on a plane."""
        src = inspect.getsource(run)
        for banned in ("urllib", "requests", "socket", "http.client", "urlopen"):
            with self.subTest(module=banned):
                self.assertNotIn(banned, src)


# ==========================================================================
# CLI shape / SRP
# ==========================================================================

class CliShapeTests(RolesCliTestCase):
    def test_unknown_subcommand_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            rc, _, _ = _cli(["frobnicate", "--base", str(base), "--repo", str(repo)])
            self.assertNotEqual(rc, 0)

    def test_no_subcommand_exits_non_zero(self):
        rc, _, _ = _cli([])
        self.assertNotEqual(rc, 0)

    def test_main_signature_defaults_argv_to_none(self):
        """§7: `main(argv: list[str] | None = None) -> int`. Asserted by
        signature rather than by calling `main()` — under pytest that would
        parse pytest's own argv."""
        params = inspect.signature(run.main).parameters
        self.assertIn("argv", params)
        self.assertIsNone(params["argv"].default)

    def test_every_documented_verb_is_reachable(self):
        """SIBLING of the two rejections above — the real verbs must not be
        swept up by an over-eager usage guard."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            for argv in (
                ["due", "--base", str(base), "--repo", str(repo), "--now", NOW],
                ["context", "--base", str(base), "--repo", str(repo),
                 "--role", "notion-sync", "--now", NOW],
                ["tick-begin", "--base", str(base), "--repo", str(repo)],
                ["role-begin", "--base", str(base), "--repo", str(repo),
                 "--role", "notion-sync"],
                ["check", "--base", str(base), "--repo", str(repo),
                 "--role", "notion-sync"],
                ["log", "--base", str(base), "--role", "notion-sync",
                 "--outcome", "ok", "--ms", "1", "--ts", "2026-07-28T07:00:11+00:00"],
                ["validate", "--base", str(base), "--repo", str(repo)],
            ):
                with self.subTest(verb=argv[0]):
                    rc, _, err = _cli(argv)
                    self.assertEqual(rc, 0, f"{argv[0]}: {err}")

    def test_run_module_owns_no_domain_logic(self):
        """§0/§7: `roles_run` composes. Cadence arithmetic and git plumbing
        living here would be a second home for both."""
        src = inspect.getsource(run)
        for banned in ("--porcelain", "-uall", "timedelta(", "weekday()", "sha256"):
            with self.subTest(token=banned):
                self.assertNotIn(banned, src)

    def test_json_verbs_print_parseable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            for argv in (
                ["due", "--base", str(base), "--repo", str(repo), "--now", NOW],
                ["validate", "--base", str(base), "--repo", str(repo)],
            ):
                with self.subTest(verb=argv[0]):
                    _, out, _ = _cli(argv)
                    json.loads(out)


# ==========================================================================
# DST through the composition root
# ==========================================================================

class DstThroughTheCliTests(RolesCliTestCase):
    """`is_due` gets the zone right when handed one; the question here is
    whether the CLI ever hands it one.

    `_resolve_now` is where a wall-clock instant becomes an aware datetime,
    and `datetime.now(timezone.utc).astimezone()` yields a FIXED OFFSET — the
    rule is dropped at exactly that seam. So the defect cannot be seen from
    `is_due` at all; it has to be pinned end to end.

    The scenario is the US spring-forward. A role ran at 23:30 local on
    2026-03-07 (EST) and the tick asks at 07:00 local on 03-08 (EDT). The
    local date advanced, so a `daily` role is due. Under a fixed -04:00 the
    stored UTC instant reads as 00:30 on 03-08 and the role is held for a day
    it should have run.

    Skipped where the platform has no tz database or no `TZ` support, rather
    than failing for a reason that is not the engine's.
    """

    LAST_RUN_UTC = "2026-03-08T04:30:00Z"      # 2026-03-07 23:30 EST
    NOW_LOCAL = "2026-03-08T07:00:00-04:00"    # 2026-03-08 07:00 EDT
    ZONE = "America/New_York"

    def _require_zone(self):
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(self.ZONE)
        except Exception as exc:               # noqa: BLE001
            self.skipTest(f"no tz database for {self.ZONE}: {exc}")
        if not hasattr(time, "tzset"):
            self.skipTest("TZ cannot be changed in-process on this platform")

    @contextlib.contextmanager
    def _host_zone(self, zone: str):
        previous = os.environ.get("TZ")
        os.environ["TZ"] = zone
        time.tzset()
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            time.tzset()

    def _seed_with_last_run(self, tmp, cadence="daily"):
        repo, base = _seed(tmp, cadence=cadence)
        write_text(roles_dir(base) / "notion-sync" / "log.jsonl",
                   json.dumps({"ts": self.LAST_RUN_UTC, "role": "notion-sync",
                               "outcome": "ok", "writes": 0, "reverted": [],
                               "reported_only": [], "ms": 1, "note": None}) + "\n")
        return repo, base

    def test_a_daily_role_is_due_across_the_spring_forward_boundary(self):
        self._require_zone()
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = self._seed_with_last_run(tmp)
            with self._host_zone(self.ZONE):
                row = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                    "--now", self.NOW_LOCAL]))["notion-sync"]
            self.assertTrue(
                row["due"],
                "the local date advanced across the DST boundary but the role "
                f"was held: {row['reason']}",
            )

    def test_the_same_role_is_not_due_twice_on_one_local_date(self):
        """SIBLING — the fix must not make the role fire twice on the day the
        clocks change; both instants are 03-08 local."""
        self._require_zone()
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="daily")
            write_text(roles_dir(base) / "notion-sync" / "log.jsonl",
                       json.dumps({"ts": "2026-03-08T12:30:00Z", "role": "notion-sync",
                                   "outcome": "ok", "writes": 0, "reverted": [],
                                   "reported_only": [], "ms": 1, "note": None}) + "\n")
            with self._host_zone(self.ZONE):
                row = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                    "--now", "2026-03-08T18:00:00-04:00"]))["notion-sync"]
            self.assertFalse(row["due"])

    def test_an_ordinary_day_far_from_any_transition_still_works(self):
        """SIBLING — a zone-aware `now` must not disturb the common case."""
        self._require_zone()
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="daily")
            write_text(roles_dir(base) / "notion-sync" / "log.jsonl",
                       json.dumps({"ts": "2026-07-27T11:00:00Z", "role": "notion-sync",
                                   "outcome": "ok", "writes": 0, "reverted": [],
                                   "reported_only": [], "ms": 1, "note": None}) + "\n")
            with self._host_zone(self.ZONE):
                row = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                    "--now", "2026-07-28T07:00:00-04:00"]))["notion-sync"]
            self.assertTrue(row["due"])

    def test_a_utc_host_is_unaffected(self):
        """SIBLING — an owner in UTC has no transitions at all, and nothing
        about the fix may change their behaviour."""
        self._require_zone()
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = self._seed_with_last_run(tmp)
            with self._host_zone("UTC"):
                row = _by_id(_json(["due", "--base", str(base), "--repo", str(repo),
                                    "--now", "2026-03-09T07:00:00+00:00"]))["notion-sync"]
            self.assertTrue(row["due"])


# ==========================================================================
# credentials must not reach the run line
# ==========================================================================

class LogRedactionTests(RolesCliTestCase):
    """The run line is committed and pushed. A credential that reaches it is
    in history permanently, and `log.jsonl` is one of the paths §7.1 stages by
    design — so this is not a hypothetical route.

    Two carriers, both real. A role's own `note:` is free text it composes,
    and the obvious thing to put in an error note is the request that failed,
    headers and all. A FILENAME is the subtler one: a role that names a file
    after the token it fetched puts the credential in a path, and the path is
    what `reverted` reports.
    """

    def _entries(self, base: Path) -> list:
        path = roles_dir(base) / "notion-sync" / "log.jsonl"
        return [json.loads(ln) for ln in read_text(path).splitlines() if ln.strip()]

    def _seed_with_secret(self, tmp):
        repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
        write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET})
        return repo, base

    def test_a_credential_in_the_note_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = self._seed_with_secret(tmp)
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "error", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00",
                  "--note", f"401 from notion with Bearer {GOOD_SECRET}"])
            raw = (roles_dir(base) / "notion-sync" / "log.jsonl").read_bytes()
            self.assertNotIn(GOOD_SECRET.encode("utf-8"), raw)
            self.assertTrue(self._entries(base)[0]["note"], "the note is not just dropped")

    def test_a_credential_in_a_reverted_path_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = self._seed_with_secret(tmp)
            path = f"zettelkasten/1_projects/{GOOD_SECRET}.md"
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "ok", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00",
                  "--reverted", json.dumps([path])])
            raw = (roles_dir(base) / "notion-sync" / "log.jsonl").read_bytes()
            self.assertNotIn(GOOD_SECRET.encode("utf-8"), raw)
            self.assertEqual(len(self._entries(base)[0]["reverted"]), 1,
                             "the path is redacted, not dropped")

    def test_a_credential_in_a_reported_only_path_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, base = self._seed_with_secret(tmp)
            path = f"zettelkasten/1_projects/{GOOD_SECRET}.md"
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "ok", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00",
                  "--reported-only", json.dumps([path])])
            raw = (roles_dir(base) / "notion-sync" / "log.jsonl").read_bytes()
            self.assertNotIn(GOOD_SECRET.encode("utf-8"), raw)

    def test_every_secret_in_the_file_is_redacted_not_only_declared_ones(self):
        """A role can read the whole secrets file (§1: `secrets:` is a
        declaration, never a boundary), so a value it never declared can still
        end up in its note."""
        other = "another-tokens-value-9876"
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET, "OTHER": other})
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "error", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00",
                  "--note", f"leaked {other}"])
            raw = (roles_dir(base) / "notion-sync" / "log.jsonl").read_bytes()
            self.assertNotIn(other.encode("utf-8"), raw)
            self.assertTrue(repo)

    def test_an_ordinary_note_survives_redaction_intact(self):
        """SIBLING — redaction must not mangle the message. A note that came
        back scrubbed of ordinary words would make every error report
        useless, and the owner would stop reading them."""
        note = "notion returned 429, backing off until tomorrow"
        with tempfile.TemporaryDirectory() as tmp:
            _, base = self._seed_with_secret(tmp)
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "error", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00", "--note", note])
            self.assertEqual(self._entries(base)[0]["note"], note)

    def test_an_ordinary_path_survives_redaction_intact(self):
        """SIBLING — the paths in `reverted` are what the owner uses to find
        what happened; redacting them into uselessness defeats the report."""
        path = "zettelkasten/_system/roles/notion-sync/state/расхождения.md"
        with tempfile.TemporaryDirectory() as tmp:
            _, base = self._seed_with_secret(tmp)
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "ok", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00",
                  "--reverted", json.dumps([path], ensure_ascii=False)])
            self.assertEqual(self._entries(base)[0]["reverted"], [path])

    def test_redaction_works_with_no_secrets_file_at_all(self):
        """SIBLING — the common case must not error on the way through."""
        with tempfile.TemporaryDirectory() as tmp:
            _, base = _seed(tmp)
            rc, _, err = _cli(["log", "--base", str(base), "--role", "notion-sync",
                               "--outcome", "ok", "--ms", "1",
                               "--ts", "2026-07-28T07:00:11+00:00",
                               "--note", "nothing to redact here"])
            self.assertEqual(rc, 0, err)
            self.assertEqual(self._entries(base)[0]["note"], "nothing to redact here")

    def test_a_short_unscannable_secret_is_still_redacted_from_the_log(self):
        """The §3.6 scan floor is about searching the OWNER's files, where a
        short value would false-positive. The log line is the engine's own
        output and contains only what a role handed it, so there is no such
        cost — and refusing to redact a weak credential publishes it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[WEAK_TOKEN]")
            write_secrets(base, {"WEAK_TOKEN": SHORT_SECRET})
            _cli(["log", "--base", str(base), "--role", "notion-sync",
                  "--outcome", "error", "--ms", "1",
                  "--ts", "2026-07-28T07:00:11+00:00",
                  "--note", f"auth failed with {SHORT_SECRET}"])
            raw = (roles_dir(base) / "notion-sync" / "log.jsonl").read_bytes()
            self.assertNotIn(SHORT_SECRET.encode("utf-8"), raw)
            self.assertTrue(repo)


# ==========================================================================
# §6 — the encrypted store, through the CLI
# ==========================================================================

class SecretsStoreCliTests(RolesCliTestCase):
    """The store is committed and the key is not, so every verb has to cope
    with a key that may be absent — and `validate` in particular, because a
    preflight runs on a laptop that has never held one.

    The CLI is also where «outside the repository» is decided: the module
    writes wherever it is told, and `roles_config.secrets_file` is what makes
    that somewhere git cannot see.
    """

    def _seed_with_store(self, tmp, pairs, secrets="[NOTION_TOKEN]"):
        repo, base = _seed(tmp, secrets=secrets)
        key = generate_key()
        write_encrypted_store(base, key, pairs)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "commit the encrypted store")
        return repo, base, key

    # --- validate resolves names without the key ------------------------

    def test_validate_resolves_names_without_the_key(self):
        """§6.5 — names come from the JSON structure, so a declared credential
        that IS in the store passes preflight with no key present."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            names = json.dumps(result["findings"], ensure_ascii=False)
            self.assertNotIn("NOTION_TOKEN is not in", names,
                             "the name was in the store; only the key is missing")

    def test_a_missing_name_is_reported_without_the_key(self):
        """The half that must still work: preflight says «this credential is
        not in the store» without ever decrypting anything."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._seed_with_store(tmp, {"OTHER_TOKEN": GOOD_SECRET})
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            self.assertIn("NOTION_TOKEN", json.dumps(result, ensure_ascii=False))

    def test_a_missing_key_is_a_distinct_finding_from_a_missing_name(self):
        """Conflating them sends the owner to fix the wrong thing: one is «add
        the credential to the store», the other is «paste the key into your
        routine's env». Both are true here, and they must be separable."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._seed_with_store(tmp, {"OTHER_TOKEN": GOOD_SECRET})
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            findings = result["findings"]
            key_findings = [f for f in findings
                            if KEY_ENV in json.dumps(f, ensure_ascii=False)]
            name_findings = [f for f in findings
                             if "NOTION_TOKEN" in json.dumps(f, ensure_ascii=False)]
            self.assertTrue(key_findings, "the absent key is not reported at all")
            self.assertTrue(name_findings, "the absent name is not reported at all")
            self.assertNotEqual(key_findings, name_findings,
                                "the two causes are one undifferentiated finding")

    def test_the_key_finding_alone_does_not_claim_a_name_is_missing(self):
        """SIBLING — with every declared name present, the only complaint is
        the key. A preflight that also blamed the store would send the owner
        re-entering credentials they already have."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            self.assertEqual(len(result["findings"]), 1, json.dumps(result))
            self.assertIn(KEY_ENV, json.dumps(result["findings"][0], ensure_ascii=False))

    def test_a_store_and_a_key_together_validate_clean(self):
        """SIBLING — the configured case must reach `ok`, or the gate is shut
        for everyone who did everything right."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(key):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False))

    def test_validate_never_decrypts_and_never_prints_a_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(key):
                _, out, err = _cli(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertNotIn(GOOD_SECRET, out + err)

    # --- open / close ----------------------------------------------------

    def test_secrets_open_writes_a_file_git_cannot_see(self):
        """Where «outside the repository» is actually decided. Asserted
        through `git status` on a repo whose store is committed, so the only
        thing that could appear is the decrypted file."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(key):
                rc, out, err = _cli(["secrets-open", "--base", str(base)])
                self.assertEqual(rc, 0, err)
                path = Path(out.strip())
                try:
                    self.assertTrue(path.is_file())
                    self.assertIn(GOOD_SECRET, path.read_text(encoding="utf-8"))
                    self.assertEqual(porcelain_z(repo), "",
                                     "git can see the decrypted store")
                    self.assertNotIn(str(repo.resolve()), str(path.resolve()))
                finally:
                    _cli(["secrets-close", "--base", str(base)])

    def test_secrets_close_removes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(key):
                _, out, _ = _cli(["secrets-open", "--base", str(base)])
                path = Path(out.strip())
                self.assertTrue(path.is_file())
                self.assertEqual(_cli(["secrets-close", "--base", str(base)])[0], 0)
            self.assertFalse(path.exists())

    def test_secrets_close_is_safe_twice_and_without_an_open(self):
        """It runs from the tick's `finally`, so it is called on a path that
        may never have existed and may already be gone. A cleanup that raised
        would mask the role's real failure."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            self.assertEqual(_cli(["secrets-close", "--base", str(base)])[0], 0)
            with key_env(key):
                _cli(["secrets-open", "--base", str(base)])
            self.assertEqual(_cli(["secrets-close", "--base", str(base)])[0], 0)
            self.assertEqual(_cli(["secrets-close", "--base", str(base)])[0], 0)
            self.assertTrue(repo)

    def test_a_crash_between_open_and_close_leaves_nothing_decrypted(self):
        """The tick's actual shape: open, work, explode, `finally` closes."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(key):
                _, out, _ = _cli(["secrets-open", "--base", str(base)])
                path = Path(out.strip())
                try:
                    try:
                        raise RuntimeError("the role agent crashed")
                    finally:
                        _cli(["secrets-close", "--base", str(base)])
                except RuntimeError:
                    pass
            self.assertFalse(path.exists())
            self.assertEqual(porcelain_z(repo), "")

    def test_secrets_open_without_the_key_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._seed_with_store(tmp, {"NOTION_TOKEN": GOOD_SECRET})
            with key_env(None):
                rc, out, err = _cli(["secrets-open", "--base", str(base)])
            self.assertNotEqual(rc, 0)
            self.assertIn(KEY_ENV, out + err)
            self.assertNotIn(GOOD_SECRET, out + err)
            self.assertTrue(repo)


class ScanFloorGatedOnTheKeyTests(RolesCliTestCase):
    """§6.5 — the value-dependent checks run when the key is present, and the
    missing-key finding NAMES the ones it skipped when it is not.

    «Can run without the key» is not «never uses one». The caller that always
    has the key is the concierge's Gate 1, moments after the owner typed the
    credential — exactly where a below-floor warning is worth the most, and
    the only moment the owner is still there to retype it.

    And the distinction that makes the gating honest: a gap the owner is told
    about is not the same as a gap that quietly stopped happening. A preflight
    that silently dropped the floor check would report a clean base whose
    credential can never be leak-scanned.
    """

    def _base_with(self, tmp, value):
        repo, base = _seed(tmp, secrets="[WEAK_TOKEN]")
        key = generate_key()
        write_encrypted_store(base, key, {"WEAK_TOKEN": value})
        return repo, base, key

    def test_a_below_floor_value_is_reported_when_the_key_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._base_with(tmp, SHORT_SECRET)
            with key_env(key):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            payload = json.dumps(result, ensure_ascii=False)
            self.assertIn("WEAK_TOKEN", payload)
            self.assertNotIn(SHORT_SECRET, payload, "never emit the value itself")

    def test_an_at_floor_value_is_clean_when_the_key_is_present(self):
        """SIBLING — decrypting to measure must not make every credential a
        finding; only a genuinely short one is."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._base_with(tmp, "abcdefghijkl")
            with key_env(key):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False))

    def test_no_floor_finding_is_raised_when_the_key_is_absent(self):
        """It cannot be measured without decrypting, so it is not claimed."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._base_with(tmp, SHORT_SECRET)
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            floor_findings = [f for f in result["findings"]
                              if "WEAK_TOKEN" in json.dumps(f, ensure_ascii=False)
                              and KEY_ENV not in json.dumps(f, ensure_ascii=False)]
            self.assertEqual(floor_findings, [],
                             "a value-dependent claim was made without the value")

    def test_the_missing_key_finding_names_the_checks_it_skipped(self):
        """The load-bearing half. Without this the gating is indistinguishable
        from the check having been quietly deleted, and the owner would read a
        base as «only the key is missing» when a credential in it can never be
        leak-scanned either."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = self._base_with(tmp, SHORT_SECRET)
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            key_findings = [f for f in result["findings"]
                            if KEY_ENV in json.dumps(f, ensure_ascii=False)]
            self.assertEqual(len(key_findings), 1)
            text = json.dumps(key_findings[0], ensure_ascii=False).lower()
            self.assertTrue(
                any(word in text for word in ("skip", "not checked", "unchecked")),
                f"the finding does not say what it skipped: {text}",
            )

    def test_supplying_the_key_turns_the_skipped_check_into_a_real_finding(self):
        """The pair, end to end: same base, same store, key added — and the
        warning the owner could not get before appears."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._base_with(tmp, SHORT_SECRET)
            argv = ["validate", "--base", str(base), "--repo", str(repo)]
            with key_env(None):
                without = _json(argv, expect_rc=1)
            with key_env(key):
                with_key = _json(argv, expect_rc=1)
            self.assertNotIn("WEAK_TOKEN", json.dumps(
                [f for f in without["findings"]
                 if KEY_ENV not in json.dumps(f, ensure_ascii=False)],
                ensure_ascii=False))
            self.assertIn("WEAK_TOKEN", json.dumps(with_key, ensure_ascii=False))

    def test_a_missing_name_is_still_reported_without_the_key(self):
        """SIBLING — gating the VALUE checks must not gate the NAME check,
        which is the whole reason preflight works without a key."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_encrypted_store(base, generate_key(), {"OTHER": GOOD_SECRET})
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)],
                               expect_rc=1)
            self.assertIn("NOTION_TOKEN", json.dumps(result, ensure_ascii=False))


class DecryptedFilePermissionTests(RolesCliTestCase):
    """`materialise` sets mode 600 «where supported».

    Windows has no POSIX mode bits, so the POSIX half is SKIPPED there rather
    than faked — a test that passes on one platform and lies on the other is
    worse than one that says it did not run. What IS portable is asserted
    everywhere: the file exists, holds the values, and is outside the repo.
    """

    def _open_store(self, tmp):
        repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
        key = generate_key()
        write_encrypted_store(base, key, {"NOTION_TOKEN": GOOD_SECRET})
        with key_env(key):
            _, out, err = _cli(["secrets-open", "--base", str(base)])
        return repo, base, Path(out.strip()), err

    def test_the_decrypted_file_is_owner_only_on_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX mode bits are not supported on this platform")
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, path, err = self._open_store(tmp)
            try:
                self.assertTrue(path.is_file(), err)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            finally:
                _cli(["secrets-close", "--base", str(base)])
            self.assertTrue(repo)

    def test_the_decrypted_file_is_readable_and_outside_the_repo_everywhere(self):
        """The portable half — asserted on every platform, including the one
        where the mode check is skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, path, err = self._open_store(tmp)
            try:
                self.assertTrue(path.is_file(), err)
                self.assertIn(GOOD_SECRET, path.read_text(encoding="utf-8"))
                self.assertNotIn(str(repo.resolve()), str(path.resolve()))
            finally:
                _cli(["secrets-close", "--base", str(base)])


class NoSecretsBaseCliTests(RolesCliTestCase):
    """The accepts-sibling for the whole feature.

    Most owners will never store a credential. For them there is no store
    file, no key and possibly no `cryptography` — and every verb must behave
    exactly as it did before §6 existed. A capability that taxes the people
    who never use it is a worse trade than the one it replaced.
    """

    VERBS = ("due", "context", "validate", "tick-begin", "role-begin", "check")

    def _argv(self, verb, repo, base):
        common = ["--base", str(base), "--repo", str(repo)]
        if verb == "due":
            return ["due", *common, "--now", NOW]
        if verb == "context":
            return ["context", *common, "--role", "notion-sync", "--now", NOW]
        if verb in ("role-begin", "check"):
            return [verb, *common, "--role", "notion-sync"]
        return [verb, *common]

    def test_every_verb_works_with_no_store_and_no_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            with key_env(None):
                for verb in self.VERBS:
                    with self.subTest(verb=verb):
                        rc, _, err = _cli(self._argv(verb, repo, base))
                        self.assertEqual(rc, 0, f"{verb}: {err}")

    def test_validate_is_clean_with_no_store_no_key_and_no_declared_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            with key_env(None):
                result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"])
            self.assertEqual(result["findings"], [])

    def test_no_store_file_is_created_by_any_verb(self):
        """SIBLING — running the engine must not conjure a credential store
        into the owner's repo."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            with key_env(None):
                for verb in self.VERBS:
                    _cli(self._argv(verb, repo, base))
            self.assertFalse((base / "_system" / "state" / "secrets.enc.json").exists())

    def test_every_verb_works_with_cryptography_absent(self):
        """§6.2 — the lazy import, simulated rather than assumed. A module-level
        `import cryptography` would satisfy every other test here and still
        break every friend who never stores a credential."""
        blocked = {name: None for name in list(sys.modules)
                   if name == "cryptography" or name.startswith("cryptography.")}
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            with key_env(None), unittest.mock.patch.dict(sys.modules, blocked):
                for verb in self.VERBS:
                    with self.subTest(verb=verb):
                        rc, _, err = _cli(self._argv(verb, repo, base))
                        self.assertEqual(rc, 0, f"{verb}: {err}")

    def test_secrets_close_is_a_no_op_on_a_base_that_never_had_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            with key_env(None):
                self.assertEqual(_cli(["secrets-close", "--base", str(base)])[0], 0)
            self.assertTrue(repo)


# ==========================================================================
# validate's exit code — the concierge's gate reads $?
# ==========================================================================

class ValidateExitCodeTests(RolesCliTestCase):
    """Three outcomes, three codes, and the distinction is load-bearing.

    `0` clean · `1` the base has a blocker · `2` the verb could not run. A
    caller testing `$?` — which is what the concierge's first gate does — must
    not read an unresolvable credential as success, and must not confuse it
    with a crash either: the first is «fix your base», the second is «the
    engine is broken», and they need different responses.

    The note case is the one that had no coverage and is the easiest to get
    wrong, because a note IS a finding in the loose sense. It must exit 0, or
    every anchored role becomes uncreatable at the shell level exactly as it
    would have in the JSON.
    """

    def _rc(self, argv, cwd=None) -> int:
        return _cli(argv, cwd=cwd)[0]

    def test_a_clean_base_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            self.assertEqual(
                self._rc(["validate", "--base", str(base), "--repo", str(repo)]), 0)

    def test_a_blocker_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            self.assertEqual(
                self._rc(["validate", "--base", str(base), "--repo", str(repo)]), 1)

    def test_a_note_alone_exits_zero(self):
        """SIBLING, and the pair that keeps the gate working: an anchored
        cadence is a legitimate shape on a schedule that ticks often enough,
        so it may not read as a failure to a shell any more than it does in
        the JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["notes"], "premise: a note was emitted")
            self.assertTrue(result["ok"])
            self.assertEqual(
                self._rc(["validate", "--base", str(base), "--repo", str(repo)]), 0)

    def test_a_note_beside_a_blocker_still_exits_one(self):
        """The blocker decides, exactly as it decides `ok`."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"', secrets="[NOTION_TOKEN]")
            self.assertEqual(
                self._rc(["validate", "--base", str(base), "--repo", str(repo)]), 1)

    def test_the_exit_code_tracks_ok_exactly(self):
        """One rule rather than two that can drift: `rc == 0` iff `ok`."""
        cases = (
            ({"cadence": "daily"}, True),
            ({"cadence": '"daily 14:00"'}, True),
            ({"cadence": "daily", "secrets": "[NOTION_TOKEN]"}, False),
            ({"cadence": '"daily 14:00"', "secrets": "[NOTION_TOKEN]"}, False),
        )
        for kwargs, expected_ok in cases:
            with self.subTest(**kwargs):
                with tempfile.TemporaryDirectory() as tmp:
                    repo, base = _seed(tmp, **kwargs)
                    argv = ["validate", "--base", str(base), "--repo", str(repo)]
                    rc, out, _ = _cli(argv)
                    self.assertEqual(json.loads(out)["ok"], expected_ok)
                    self.assertEqual(rc, 0 if expected_ok else 1)

    def test_a_usage_error_exits_two_not_one(self):
        """«The verb could not run» must stay separable from «the base has a
        problem», or a caller cannot tell a broken engine from a broken base.

        A filesystem root is a real usage error: `resolve_base` refuses it
        because there is no `.name` to expand the sugar from, so the verb
        never gets as far as inspecting the base."""
        root = str(Path(tempfile.gettempdir()).anchor)
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = _seed(tmp)
            self.assertEqual(
                self._rc(["validate", "--base", root, "--repo", str(repo)]), 2)

    def test_an_unknown_role_is_a_finding_not_a_usage_error(self):
        """SIBLING, and the boundary between the two codes: `--role nope` is
        something true about the base — the verb ran and answered — so it is
        `1`, not `2`. Asking about a role that is not there is a fact to
        report, not an engine failure."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            rc, out, _ = _cli(["validate", "--base", str(base), "--repo", str(repo),
                               "--role", "no-such-role"])
            self.assertEqual(rc, 1)
            payload = json.loads(out)
            self.assertFalse(payload["ok"])
            self.assertIn("no-such-role", json.dumps(payload, ensure_ascii=False))

    def test_findings_still_print_json_on_stdout_when_exiting_one(self):
        """SIBLING — a non-zero exit must not turn the report into a bare
        error. The caller needs the findings precisely when there are some."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            rc, out, _ = _cli(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertEqual(rc, 1)
            payload = json.loads(out)
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["findings"])

    def test_the_other_json_verbs_still_exit_zero_on_a_healthy_base(self):
        """SIBLING — only `validate` carries this contract; `due` reporting a
        not-due role is not a failure."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"monthly 15"')
            self.assertEqual(
                self._rc(["due", "--base", str(base), "--repo", str(repo),
                          "--now", NOW]), 0)


# ==========================================================================
# §2.1 — the unreachable-anchor note
# ==========================================================================

def _finding_count(result: dict) -> int:
    """Total entries across every list-valued collection in a validate result.

    Shape-agnostic on purpose. §2.1 requires `validate` to distinguish a NOTE
    from a BLOCKER, but leaves the shape to the implementer — one `findings`
    list with a severity field, or a separate `notes` key, both satisfy it.
    Counting across all list-valued keys works for either, so these tests
    assert the behaviour and not a field name.
    """
    return sum(len(v) for v in result.values() if isinstance(v, list))


class CadenceAnchorNoteTests(RolesCliTestCase):
    """§2.1 — `validate` warns about a time anchor without refusing it.

    An anchor is evaluated at the instant a tick runs, so one later than the
    tick's own time is never satisfied and the role fires zero times forever,
    silently. The engine cannot know the owner's cron, so refusing the shape
    would be a validator refusing what its author has not seen — hence a note.

    And the note must not break the gate: the concierge's first preflight step
    is `validate` clean, so if an anchor made `ok` false, creating any anchored
    role would be blocked outright.

    SHAPE: most of these were written before the note landed and name no
    field — they assert `ok`, a total count across every list-valued key, and
    what appears in the payload, so they hold for any scheme that separates
    the two kinds. `AnchorNoteShapeTests` below pins the shape that actually
    shipped, read off a real run rather than guessed.
    """

    def test_an_anchored_daily_cadence_produces_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertGreater(_finding_count(result), 0)
            payload = json.dumps(result, ensure_ascii=False)
            self.assertIn("14:00", payload)
            self.assertIn("notion-sync", payload)

    def test_an_anchored_weekly_cadence_produces_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"weekly mon 09:00"')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertGreater(_finding_count(result), 0)
            self.assertIn("09:00", json.dumps(result, ensure_ascii=False))

    def test_an_anchored_monthly_cadence_produces_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"monthly 3 18:30"')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertGreater(_finding_count(result), 0)
            self.assertIn("18:30", json.dumps(result, ensure_ascii=False))

    def test_ok_stays_true_when_a_note_is_the_only_finding(self):
        """THE load-bearing one. The concierge gates role creation on
        `validate` clean; an anchor that flipped `ok` would block every
        anchored role from ever being created, which is a worse failure than
        the one §2.1 warns about."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertGreater(_finding_count(result), 0, "premise: a note was emitted")
            self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False))

    def test_an_unanchored_cadence_produces_no_note(self):
        """SIBLING, and the one that keeps the note from becoming noise. A
        gate that fires on every role is what makes the one real warning
        invisible.

        `hourly` and `every tick` are deliberately NOT in this list — they
        carry their own note, tested below. They are the mirror of the anchor
        hazard rather than an absence of one: against the shipped once-a-day
        tick they come due on every tick, so an owner who asks for an hourly
        summary gets one a day, silently."""
        for cadence in ("daily", '"weekly mon"', '"monthly 3"'):
            with self.subTest(cadence=cadence):
                with tempfile.TemporaryDirectory() as tmp:
                    repo, base = _seed(tmp, cadence=cadence)
                    result = _json(["validate", "--base", str(base),
                                    "--repo", str(repo)])
                    self.assertTrue(result["ok"])
                    self.assertEqual(_finding_count(result), 0,
                                     json.dumps(result, ensure_ascii=False))

    def test_a_tick_rate_cadence_carries_its_own_note(self):
        """The hazard `hourly` actually has, and the reason it needs saying.

        The grammar is correct, so this is a note and never a refusal — the
        shape is right the moment the owner's scheduler ticks more often. But
        silence here means an owner asks for 24 summaries a day, `validate`
        reports clean, and they get one.
        """
        for cadence in ("hourly", '"every tick"'):
            with self.subTest(cadence=cadence):
                with tempfile.TemporaryDirectory() as tmp:
                    repo, base = _seed(tmp, cadence=cadence)
                    result = _json(["validate", "--base", str(base),
                                    "--repo", str(repo)])
                    self.assertTrue(result["ok"], "a note never blocks")
                    self.assertEqual(len(result["notes"]), 1,
                                     json.dumps(result, ensure_ascii=False))
                    self.assertIn("every scheduler tick",
                                  json.dumps(result, ensure_ascii=False))

    def test_the_note_names_only_the_anchored_role_on_a_mixed_base(self):
        """SIBLING — one anchored role among several must not tar the rest."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="daily")
            write_role(base, "anchored", role_id="anchored",
                       cadence='"daily 14:00"', writes="[state]")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"])
            self.assertEqual(_finding_count(result), 1)
            self.assertIn("anchored", json.dumps(result, ensure_ascii=False))

    def test_a_note_and_a_blocker_together_leave_ok_false(self):
        """Item 4: the note must not mask a real defect."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"', secrets="[NOTION_TOKEN]")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)], expect_rc=1)
            self.assertFalse(result["ok"])
            payload = json.dumps(result, ensure_ascii=False)
            self.assertIn("14:00", payload)          # the note
            self.assertIn("NOTION_TOKEN", payload)   # the blocker
            self.assertGreaterEqual(_finding_count(result), 2)

    def test_ok_tracks_the_blocker_and_never_the_note(self):
        """How «distinguishable» is proved without naming a field: the same
        anchored role is clean or not purely according to whether a blocker is
        present. If notes and blockers were one undifferentiated bucket, the
        first case could not be `ok`."""
        anchored = '"daily 14:00"'
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence=anchored)
            note_only = _json(["validate", "--base", str(base), "--repo", str(repo)])
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="daily", secrets="[NOTION_TOKEN]")
            blocker_only = _json(["validate", "--base", str(base), "--repo", str(repo)],
                                 expect_rc=1)
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence=anchored, secrets="[NOTION_TOKEN]")
            both = _json(["validate", "--base", str(base), "--repo", str(repo)],
                         expect_rc=1)
        self.assertTrue(note_only["ok"])
        self.assertFalse(blocker_only["ok"])
        self.assertFalse(both["ok"])
        self.assertGreater(_finding_count(both), _finding_count(blocker_only))

    def test_removing_the_blocker_returns_ok_to_true_with_the_note_still_there(self):
        """SIBLING — the note is stable across the fix, so an owner who
        resolves the real defect is not left with a gate that stays shut."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"', secrets="[NOTION_TOKEN]")
            self.assertFalse(
                _json(["validate", "--base", str(base), "--repo", str(repo)],
                      expect_rc=1)["ok"])
            write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET})
            fixed = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(fixed["ok"])
            self.assertGreater(_finding_count(fixed), 0, "the note survives the fix")
            self.assertIn("14:00", json.dumps(fixed, ensure_ascii=False))

    def test_the_note_survives_the_role_scoping_flag(self):
        """SIBLING — `--role` narrows the scope; it must not drop the note for
        the role it was asked about."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"')
            scoped = _json(["validate", "--base", str(base), "--repo", str(repo),
                            "--role", "notion-sync"])
            self.assertTrue(scoped["ok"])
            self.assertIn("14:00", json.dumps(scoped, ensure_ascii=False))

    def test_the_note_emits_no_secret_value(self):
        """§7.2's standing rule holds for the new finding too."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"', secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET})
            _, out, err = _cli(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertNotIn(GOOD_SECRET, out + err)


class AnchorNoteShapeTests(RolesCliTestCase):
    """The shape that shipped, pinned. Read off a real `validate` run, not
    guessed: a top-level `notes` list beside `findings`, with `ok` computed
    from `findings` alone.

    The behavioural tests above are deliberately shape-agnostic and stay that
    way; these exist so the contract a consumer reads — the concierge's
    preflight gate, `/minder:mem:role:list` — cannot drift silently.
    """

    def test_notes_are_a_separate_top_level_list_from_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertIn("notes", result)
            self.assertIn("findings", result)
            self.assertIsInstance(result["notes"], list)
            self.assertEqual(result["findings"], [],
                             "an anchor is a note, never a finding")
            self.assertEqual(len(result["notes"]), 1)

    def test_ok_is_computed_from_findings_alone(self):
        """The rule behind the gate, stated directly: notes never move `ok`."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"')
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertTrue(result["ok"])
            self.assertTrue(result["notes"])
            self.assertEqual(result["ok"], not result["findings"])

    def test_a_note_names_the_role_its_cadence_and_the_anchor(self):
        """Everything the owner needs to act on it, without reopening the file."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"weekly mon 09:00"')
            note = _json(["validate", "--base", str(base), "--repo", str(repo)])["notes"][0]
            self.assertEqual(note["role"], "notion-sync")
            self.assertEqual(note["cadence"], "weekly mon 09:00")
            self.assertIn("09:00", note["note"])
            self.assertTrue(
                all(ord(ch) < 0x400 for ch in note["note"]),
                "§0: the engine emits no owner-language prose",
            )

    def test_notes_is_present_and_empty_when_there_is_nothing_to_say(self):
        """SIBLING — the key is stable, so a consumer can read `result["notes"]`
        without guarding for its absence on every clean base."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="daily")
            result = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertEqual(result["notes"], [])
            self.assertTrue(result["ok"])

    def test_one_note_per_anchored_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence='"daily 14:00"')
            write_role(base, "second", role_id="second",
                       cadence='"monthly 3 18:30"', writes="[state]")
            write_role(base, "third", role_id="third", cadence="hourly",
                       writes="[state]")
            write_role(base, "fourth", role_id="fourth", cadence="daily",
                       writes="[state]")
            notes = _json(["validate", "--base", str(base),
                           "--repo", str(repo)])["notes"]
            # `hourly` carries its OWN note now — the mirror of the anchor
            # hazard, and just as silent: against a once-a-day tick it comes due
            # every tick, so «summarise each hour» yields one summary a day.
            # A plain `daily` still carries nothing; a note on every role is
            # noise, and noise is what hides the one that matters.
            self.assertEqual({n["role"] for n in notes},
                             {"notion-sync", "second", "third"})
            self.assertEqual(len(notes), 3, "one note per role, never two")


# ==========================================================================
# a relative --base
# ==========================================================================

class RelativeBaseTests(RolesCliTestCase):
    """`--base .` must mean exactly what the absolute path means.

    The rest of the engine is invoked with `--base .` as the house convention
    (`reconcile_tasks.py`, `reconcile_calendar.py`), so a roles CLI that only
    works with an absolute base is a matter of when, not if.

    What made this worth its own class: the sugar expands from `base.name`,
    and `Path(".").name` is the empty string, so the prefixes collapsed to
    `/_system/roles/{id}/state/` and matched nothing. Every write a role made
    into its OWN state tree was then classified out-of-zone and reverted — the
    role's memory destroyed on every run — while `validate` reported
    `{"ok": true}` and the log line reported success. Verified by execution
    before these tests were written.

    Equivalence is asserted on the OUTPUTS, not on each result being
    individually plausible: `{"ok": true}` was individually plausible.

    Which verbs can actually detect this class, measured by re-introducing the
    defect and seeing which tests go red:

    - `context` and `check` DO — they render or classify real paths, so an
      unresolved base changes their output.
    - `due` and `validate` do NOT, and cannot. `due`'s report carries no
      paths, and `validate` returns `{"ok": true, "findings": []}` whether or
      not the base resolved. Their equivalence tests are consistency checks,
      kept for the regressions they would catch, but the guarantee for THIS
      defect rests on the path-bearing verbs and on `ResolveBaseTests`.

    That `validate` is green either way is not a gap in the tests — it is the
    defect's whole character, and the reason a silent one ran for as long as
    it did.
    """

    STATE_REL = "zettelkasten/_system/roles/notion-sync/state/seen.txt"
    MEMORY = "the role's accumulated memory\n"

    # --- the defect, head on --------------------------------------------

    def test_a_state_write_is_in_zone_under_a_relative_base(self):
        """The test that would have caught it. The on-disk assertion is the
        load-bearing half: a `reverted` list that merely looks empty proves
        nothing if the file is gone."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", ".", "--repo", str(repo)], cwd=base)
            _cli(["role-begin", "--base", ".", "--repo", str(repo),
                  "--role", "notion-sync"], cwd=base)
            write_text(repo_path(repo, self.STATE_REL), self.MEMORY)
            result = _json(["check", "--base", ".", "--repo", str(repo),
                            "--role", "notion-sync"], cwd=base)
            self.assertIn(self.STATE_REL, result["in_zone"])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, self.STATE_REL).exists(),
                            "the role's memory was deleted under a relative base")
            self.assertEqual(read_text(repo_path(repo, self.STATE_REL)), self.MEMORY)

    # --- equivalence, verb by verb ---------------------------------------

    def test_due_is_identical_under_a_relative_and_an_absolute_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="every tick")
            relative = _json(["due", "--base", ".", "--repo", str(repo),
                              "--now", NOW], cwd=base)
            absolute = _json(["due", "--base", str(base), "--repo", str(repo),
                              "--now", NOW])
            self.assertEqual(relative, absolute)

    def test_validate_is_identical_under_a_relative_and_an_absolute_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, secrets="[NOTION_TOKEN]")
            write_secrets(base, {"NOTION_TOKEN": GOOD_SECRET})
            relative = _json(["validate", "--base", ".", "--repo", str(repo)], cwd=base)
            absolute = _json(["validate", "--base", str(base), "--repo", str(repo)])
            self.assertEqual(relative, absolute)

    def test_context_is_identical_under_a_relative_and_an_absolute_base(self):
        """The strictest of the four: the context renders `{{BASE}}`,
        `{{REPO_ROOT}}` and `{{STATE_DIR}}` as real paths, so a base that was
        not resolved shows up as a different prompt — and the role is told to
        write somewhere else."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_state(base, "notion-sync", "seen.txt", "2026-07-01\n")
            _, relative, _ = _cli(["context", "--base", ".", "--repo", str(repo),
                                   "--role", "notion-sync", "--now", NOW], cwd=base)
            _, absolute, _ = _cli(["context", "--base", str(base), "--repo", str(repo),
                                   "--role", "notion-sync", "--now", NOW])
            self.assertEqual(relative, absolute)
            self.assertIn(str(base), absolute)

    def test_check_is_identical_under_a_relative_and_an_absolute_base(self):
        """Two freshly built repos, one cycle each.

        Not two cycles in one repo: the first cycle leaves the state file
        dirty, so the second would rewrite identical bytes, and digest
        attribution correctly reports that as untouched. The confound is real
        engine behaviour, so the fixture has to avoid it rather than assert
        around it. `check`'s report is entirely repo-relative paths and
        booleans, so two repos are directly comparable.
        """
        def cycle(tmp, base_arg_from_base: bool):
            repo, base = _seed(tmp)
            base_arg, cwd = (".", base) if base_arg_from_base else (str(base), None)
            _cli(["tick-begin", "--base", base_arg, "--repo", str(repo)], cwd=cwd)
            _cli(["role-begin", "--base", base_arg, "--repo", str(repo),
                  "--role", "notion-sync"], cwd=cwd)
            write_text(repo_path(repo, self.STATE_REL), self.MEMORY)
            write_text(repo_path(repo, "zettelkasten/1_projects/rogue.md"), "rogue\n")
            report = _json(["check", "--base", base_arg, "--repo", str(repo),
                            "--role", "notion-sync"], cwd=cwd)
            return report, repo

        with tempfile.TemporaryDirectory() as tmp_a:
            relative, repo_a = cycle(tmp_a, True)
            with tempfile.TemporaryDirectory() as tmp_b:
                absolute, _ = cycle(tmp_b, False)
            self.assertEqual(relative, absolute)
            self.assertIn(self.STATE_REL, absolute["in_zone"])
            self.assertEqual(absolute["reverted"], ["zettelkasten/1_projects/rogue.md"])
            self.assertTrue(repo_path(repo_a, self.STATE_REL).exists())

    # --- relative bases that are not `.` ----------------------------------

    def test_a_named_relative_base_from_the_repo_root_matches_the_absolute_form(self):
        """Compared on `context`, not on `due`: `due`'s report carries no
        paths, so it reads identical whether or not the base was resolved.
        `context` renders the base into the prompt, so it bites."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_state(base, "notion-sync", "seen.txt", "2026-07-01\n")
            _, relative, _ = _cli(["context", "--base", base.name, "--repo", str(repo),
                                   "--role", "notion-sync", "--now", NOW], cwd=repo)
            _, absolute, _ = _cli(["context", "--base", str(base), "--repo", str(repo),
                                   "--role", "notion-sync", "--now", NOW])
            self.assertEqual(relative, absolute)
            self.assertIn(str(base), relative)

    def test_a_dotdot_relative_base_from_a_subdirectory_matches_the_absolute_form(self):
        """`..` has to normalise, not merely concatenate — and the sugar must
        come out of the resolved name, not the literal string."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            write_state(base, "notion-sync", "seen.txt", "2026-07-01\n")
            inner = repo_path(repo, "zettelkasten/1_projects")
            _, relative, _ = _cli(["context", "--base", f"../../{base.name}",
                                   "--repo", str(repo), "--role", "notion-sync",
                                   "--now", NOW], cwd=inner)
            _, absolute, _ = _cli(["context", "--base", str(base), "--repo", str(repo),
                                   "--role", "notion-sync", "--now", NOW])
            self.assertEqual(relative, absolute)
            self.assertNotIn("..", relative)

    def test_a_named_relative_base_keeps_the_sugar_pointing_at_the_state_tree(self):
        """SIBLING of the `--base .` case, for a base reached by name: the
        role's own writes stay in zone."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", base.name, "--repo", str(repo)], cwd=repo)
            _cli(["role-begin", "--base", base.name, "--repo", str(repo),
                  "--role", "notion-sync"], cwd=repo)
            write_text(repo_path(repo, self.STATE_REL), self.MEMORY)
            result = _json(["check", "--base", base.name, "--repo", str(repo),
                            "--role", "notion-sync"], cwd=repo)
            self.assertIn(self.STATE_REL, result["in_zone"])
            self.assertTrue(repo_path(repo, self.STATE_REL).exists())

    def test_a_base_named_something_other_than_zettelkasten_works_relatively_too(self):
        """SIBLING — the two derivations must compose: the base name is read
        from the resolved path, whatever the owner called their base.

        Asserted on a state write rather than only on `validate`, because
        `validate` reports `{"ok": true}` under the unresolved base too — that
        is exactly what made the original defect silent."""
        state_rel = "второй-мозг/_system/roles/notion-sync/state/seen.txt"
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp), base_dirname="второй-мозг")
            base = repo / "второй-мозг"
            write_role(base, "notion-sync", writes="[state]")
            _write_run_frame(base)
            self.assertTrue(
                _json(["validate", "--base", ".", "--repo", str(repo)], cwd=base)["ok"])
            _cli(["tick-begin", "--base", ".", "--repo", str(repo)], cwd=base)
            _cli(["role-begin", "--base", ".", "--repo", str(repo),
                  "--role", "notion-sync"], cwd=base)
            write_text(repo_path(repo, state_rel), self.MEMORY)
            result = _json(["check", "--base", ".", "--repo", str(repo),
                            "--role", "notion-sync"], cwd=base)
            self.assertIn(state_rel, result["in_zone"])
            self.assertEqual(result["reverted"], [])
            self.assertTrue(repo_path(repo, state_rel).exists())

    # --- the suite must not corrupt itself --------------------------------

    def test_the_cwd_is_restored_after_a_relative_base_run(self):
        """A test that leaves the CWD inside a removed temp directory breaks
        every test after it, which reads as a defect somewhere else entirely."""
        before = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp, cadence="every tick")
            _cli(["due", "--base", ".", "--repo", str(repo), "--now", NOW], cwd=base)
        self.assertEqual(os.getcwd(), before)

    def test_the_cwd_is_restored_even_when_the_verb_fails(self):
        """SIBLING — the restore is in a `finally`, so a usage error does not
        strand the process in a directory that is about to be deleted."""
        before = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            rc, _, _ = _cli(["context", "--base", ".", "--repo", str(repo),
                             "--role", "nope", "--now", NOW], cwd=base)
            self.assertNotEqual(rc, 0)
        self.assertEqual(os.getcwd(), before)


# ==========================================================================
# OS temp-dir hygiene — the suite must clean up after itself
# ==========================================================================

class TempDirHygieneTests(unittest.TestCase):
    """Asserts both hygiene layers rather than trusting them: a teardown that
    silently no-ops looks identical to a clean suite until someone opens their
    temp directory a month later.

    Deliberately NOT a `RolesCliTestCase` — it manages the lifecycle itself so
    it can stand on both sides of it. It still isolates `tempfile.tempdir`,
    so its own marker directories cannot collide with a concurrently running
    real tick or with another test.
    """

    def setUp(self) -> None:
        self._home = tempfile.TemporaryDirectory(prefix="roles-hygiene-")
        self._restore = tempfile.tempdir
        tempfile.tempdir = self._home.name

    def tearDown(self) -> None:
        tempfile.tempdir = self._restore
        self._home.cleanup()

    def test_a_full_tick_cycle_creates_temp_state_and_the_purge_removes_it(self):
        before = roles_tmp_entries()
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                  "--role", "notion-sync"])
            _cli(["check", "--base", str(base), "--repo", str(repo),
                  "--role", "notion-sync"])
            created = roles_tmp_entries() - before
            self.assertTrue(created, "the CLI is expected to use the OS temp dir")
            removed = purge_roles_tmp(before)
            self.assertEqual(set(removed), created)
        self.assertEqual(roles_tmp_entries(), before)

    def test_the_purge_leaves_pre_existing_entries_alone(self):
        """SIBLING — cleanup must remove only what this run created. A real
        tick may be in flight in another process; deleting its snapshot
        directory would make the guard attribute its writes to nobody."""
        marker = Path(tempfile.gettempdir()) / "minder-mem-roles-not-ours-testfixture"
        marker.mkdir(exist_ok=True)
        before = roles_tmp_entries()
        self.assertIn(marker, before)
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = _seed(tmp)
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            purge_roles_tmp(before)
        self.assertTrue(marker.exists(), "pre-existing entries are not ours")

    def test_a_cli_test_case_leaves_no_roles_temp_directories_behind(self):
        """The end-state assertion, driven through the real `TestCase`
        lifecycle so the teardown is exercised the way pytest exercises it.

        Two named methods, not whole classes: each one builds a git repo, so
        re-running a class here would multiply the suite's cost for no extra
        signal about the teardown."""
        before = roles_tmp_entries()
        suite = unittest.TestSuite()
        for name in ("test_tick_begin_prints_the_file_it_wrote",
                     "test_both_snapshot_files_share_one_per_tick_directory"):
            suite.addTest(SnapshotVerbTests(name))
        with open(os.devnull, "w", encoding="utf-8") as sink:
            result = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)
        self.assertTrue(result.wasSuccessful(), "the nested tests must pass to count")
        self.assertEqual(roles_tmp_entries(), before)

    def test_each_cli_test_gets_its_own_isolated_temp_home(self):
        """Layer 1: no test can see another's snapshot directory. This is what
        makes the suite order-independent under `pytest-randomly`; a shared
        global directory that tests both write to and delete from is
        order-dependent by construction."""
        seen = []

        class Probe(RolesCliTestCase):
            def runTest(self):  # noqa: N802 — unittest's own naming
                seen.append(tempfile.gettempdir())

        for _ in range(2):
            Probe().run()
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1], "each test needs its own temp home")
        for home in seen:
            self.assertNotEqual(home, self._restore)
            self.assertFalse(Path(home).exists(), "the home is removed on teardown")


class ScanIsStoreWideTests(RolesCliTestCase):
    """§3.6 — the scan reads «every value in the secrets file», not the values
    the role happened to declare.

    This is the compensating control for the admission that `secrets:` is a
    declaration and not a boundary. Every role has a shell and can therefore
    read the whole decrypted file; if the scan only looked for what a role
    declared, the way to launder a sibling's credential into a committed file
    would be to simply not name it. Scoping the scan to `cfg.secrets` looks
    like an obvious optimisation — decrypt less, compare less — which is
    exactly why it needs a test standing in front of it.
    """

    DECLARED = "ntn-declared-token-1234567890"
    UNDECLARED = "xoxb-undeclared-token-098765"

    def _seed_two_credentials(self, tmp):
        repo, base = _seed(tmp, writes="[state]", secrets="[NOTION_TOKEN]")
        key = generate_key()
        write_encrypted_store(base, key, {"NOTION_TOKEN": self.DECLARED,
                                          "SLACK_TOKEN": self.UNDECLARED})
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "commit the encrypted store")
        return repo, base, key

    def _run_and_check(self, repo, base, key, write_value):
        """The documented tick order, because the scan depends on it.

        `check` takes its values from the DECRYPTED file, not from the store —
        so `secrets-open` is what arms the scan, and a test that skipped it
        would prove the scan disabled rather than the scan narrow. That
        dependency is the reason 1.1 sits ahead of the loop and `secrets-close`
        sits in Step 3, after every role has been checked.
        """
        rel = "zettelkasten/_system/roles/notion-sync/state/notes.md"
        _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
        with key_env(key):
            rc, _, err = _cli(["secrets-open", "--base", str(base)])
            assert rc == 0, err
        _cli(["role-begin", "--base", str(base), "--repo", str(repo),
              "--role", "notion-sync"])
        target = repo_path(repo, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_text(target, f"found: {write_value}\n")
        try:
            with key_env(key):
                result = _json(["check", "--base", str(base), "--repo", str(repo),
                                "--role", "notion-sync"])
        finally:
            with key_env(key):
                _cli(["secrets-close", "--base", str(base)])
        return rel, result

    def test_a_credential_the_role_never_declared_is_still_caught(self):
        """The whole point. The role declares NOTION_TOKEN and writes only
        SLACK_TOKEN's value into its own allowed zone."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_two_credentials(tmp)
            with key_env(key):
                rel, result = self._run_and_check(repo, base, key, self.UNDECLARED)
            self.assertEqual(result["secret_leak"], [rel])
            self.assertNotIn(self.UNDECLARED, read_text(repo_path(repo, rel))
                             if repo_path(repo, rel).exists() else "")

    def test_the_declared_credential_is_caught_too(self):
        """SIBLING — widening the scan must not have cost the ordinary case."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_two_credentials(tmp)
            with key_env(key):
                rel, result = self._run_and_check(repo, base, key, self.DECLARED)
            self.assertEqual(result["secret_leak"], [rel])

    def test_without_secrets_open_the_scan_is_armed_by_nothing(self):
        """The dependency stated as a property, so it cannot drift unnoticed.

        Not a wish — a fact about where `check` reads values from. If someone
        later moves the decryption inside `check`, this test fails and tells
        them the tick's open/close bracket is now dead weight rather than
        leaving both mechanisms half-live.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_two_credentials(tmp)
            rel = "zettelkasten/_system/roles/notion-sync/state/notes.md"
            _cli(["tick-begin", "--base", str(base), "--repo", str(repo)])
            _cli(["role-begin", "--base", str(base), "--repo", str(repo),
                  "--role", "notion-sync"])
            target = repo_path(repo, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            write_text(target, f"found: {self.DECLARED}\n")
            with key_env(key):
                result = _json(["check", "--base", str(base), "--repo", str(repo),
                                "--role", "notion-sync"])
            self.assertEqual(result["secret_leak"], [])

    def test_ordinary_content_is_untouched(self):
        """SIBLING — the accepts case. A store-wide scan that flagged innocent
        prose would revert the owner's real work, which is worse than the leak
        it prevents."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._seed_two_credentials(tmp)
            with key_env(key):
                rel, result = self._run_and_check(repo, base, key,
                                                  "нормальный текст без секретов")
            self.assertEqual(result["secret_leak"], [])
            self.assertIn("нормальный текст", read_text(repo_path(repo, rel)))


if __name__ == "__main__":
    unittest.main()
