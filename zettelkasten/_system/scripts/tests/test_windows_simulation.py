"""Reproduce, on POSIX, the Windows mechanisms that actually broke the engine.

The portability gate is static: it finds forbidden constructs. This module is
the dynamic half — it recreates the three runtime behaviours a Git Bash box has
and a Mac does not, and runs real engine code inside them. A gate can only find
what someone thought to describe; these tests find what the behaviour does.

What is genuinely reproduced, and how:

1. **The ANSI code page.** Windows python defaults `locale.getpreferredencoding()`
   to cp1252, so `read_text()` without `encoding=` raises on any non-ASCII byte.
   `LC_ALL=C` with `PYTHONCOERCECLOCALE=0` and `PYTHONUTF8=0` makes the default
   US-ASCII here — a strictly NARROWER encoding than cp1252, so anything that
   survives this would survive Windows.

2. **MSYS argument rewriting.** The MSYS runtime rewrites an argument shaped
   like `<ref>:<path>` into `<ref>;<path>` with backslashes. A `git` shim on
   PATH does exactly that unless `MSYS_NO_PATHCONV=1` is set, so the failure is
   produced by the same mechanism rather than asserted about.

3. **No executable bit.** A Windows checkout carries no mode bits. Stripping
   `+x` from every shipped script reproduces it exactly.

Plus bash 3.2, which macOS ships as `/bin/bash` — that one needs no simulation.

What is NOT reproduced, stated so nobody reads more into a green run than is
there: the `\\` path separator, NTFS filename rules at the syscall level, and
the case-insensitivity of the filesystem (macOS is already case-insensitive, so
that one is covered by accident rather than by design). Those remain the job of
the static gate and of a friend actually running it.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_ENGINE_SCRIPTS = _THIS.parents[1]                 # zettelkasten/_system/scripts
_REPO_ROOT = _THIS.parents[4]
_SCRIPTS = _REPO_ROOT / "scripts"

# The ANSI-code-page simulation. `PYTHONCOERCECLOCALE=0` defeats PEP 538, which
# would otherwise quietly upgrade `C` to `C.UTF-8` and make the whole test a
# no-op; `PYTHONUTF8=0` defeats PEP 540 for the same reason.
ANSI_ENV = {
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONCOERCECLOCALE": "0",
    "PYTHONUTF8": "0",
    "PYTHONIOENCODING": "ascii",
}

CYRILLIC_NOTE = textwrap.dedent(
    """\
    ---
    id: 20260806-meeting-встреча
    ---

    # Встреча — обсуждение

    - [ ] Сделать разбор по фасаду — [[20260806-meeting-встреча]] ^task-разбор
    - 📅 **2026-09-01** — созвон с командой
    """
)


def _ansi_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ANSI_ENV}
    env.update(ANSI_ENV)
    return env


def _ansi_filesystem_is_utf8() -> bool:
    """Whether the ANSI simulation leaves the FILESYSTEM encoding at UTF-8.

    The simulation models Windows, where the platform default for TEXT is a
    code page but file names are always Unicode. macOS behaves the same way.
    Linux does not: under `LC_ALL=C` with UTF-8 mode off, python decodes file
    names as ASCII with surrogate escapes, and a Cyrillic path then fails on
    output for a reason no Windows or macOS box can reproduce. On such a host
    the simulation is testing the host, not the engine, and the suite says so.
    """
    probe = subprocess.run(
        ["python3", "-c", "import sys; print(sys.getfilesystemencoding())"],
        capture_output=True, text=True, encoding="utf-8", env=_ansi_env(),
    )
    return probe.stdout.strip().lower().replace("-", "") == "utf8"


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        env=env if env is not None else os.environ.copy(),
    )


class AnsiCodePageTests(unittest.TestCase):
    """Engine code must read and write UTF-8 whatever the platform's default is."""

    def setUp(self) -> None:
        if not _ansi_filesystem_is_utf8():
            self.skipTest("the ANSI simulation narrows the filesystem encoding on this host, "
                          "which Windows and macOS never do — see _ansi_filesystem_is_utf8")
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "zettelkasten"
        for sub in ("_records/meetings", "_system", "_system/registries",
                    "_sources/inbox/plaud"):
            (self.base / sub).mkdir(parents=True)
        (self.base / "_records/meetings/20260806-meeting-встреча.md").write_text(
            CYRILLIC_NOTE, encoding="utf-8")
        (self.base / "_system/TASKS.md").write_text(
            "# Tasks\n\n## Action\n\n- [ ] Сделать разбор по фасаду ^task-разбор\n",
            encoding="utf-8")
        (self.base / "_system/CALENDAR.md").write_text(
            "# Calendar\n\n## Upcoming\n\n- 📅 **2026-09-01** — [[20260806-meeting-встреча]]\n",
            encoding="utf-8")
        (self.base / "_system/registries/SOURCES.md").write_text(
            "| ID | Inbox Path | Family | Layout | Default Domain | Skip Subdirs | Description | Status |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| plaud | `_sources/inbox/plaud/` | transcript | dir-with-summary | auto | — | Плауд | active |\n",
            encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_the_simulation_actually_bites(self):
        """A guard on the guard: if the env stopped narrowing the default
        encoding, every test below would pass for the wrong reason."""
        probe = self.base / "probe.txt"
        probe.write_text("кириллица\n", encoding="utf-8")
        result = _run(
            ["python3", "-c",
             # portability-ok: unconfigured ON PURPOSE — this IS the probe
             f"import pathlib; pathlib.Path({str(probe)!r}).read_text()"],
            self.base, _ansi_env(),
        )
        self.assertNotEqual(result.returncode, 0,
                            "the ANSI simulation is not narrowing the default encoding")
        self.assertIn("UnicodeDecodeError", result.stderr)

    def test_reconcile_tasks_survives_an_ascii_default(self):
        result = _run(
            ["python3", str(_ENGINE_SCRIPTS / "reconcile_tasks.py"),
             "--base", str(self.base), "--report", "--json"],
            self.base, _ansi_env(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"orphan_count": 0', result.stdout)

    def test_reconcile_calendar_survives_an_ascii_default(self):
        result = _run(
            ["python3", str(_ENGINE_SCRIPTS / "reconcile_calendar.py"),
             "--base", str(self.base), "--report", "--json", "--today", "2026-08-01"],
            self.base, _ansi_env(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_split_name_repair_survives_an_ascii_default(self):
        item = self.base / "_sources/inbox/plaud/07-09 Встреча - A/B-тест вкладок"
        item.mkdir(parents=True)
        (item / "transcript_with_summary.md").write_text("тело\n", encoding="utf-8")
        result = _run(
            ["python3", str(_ENGINE_SCRIPTS / "repair_split_names.py"),
             "--inbox", str(self.base / "_sources/inbox"), "--apply", "--json"],
            self.base, _ansi_env(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.base / "_sources/inbox/plaud/07-09 Встреча - A-B-тест вкладок").is_dir()
        )

    def test_manifest_reader_survives_an_ascii_default(self):
        """The manifest's own comments carry em-dashes."""
        result = _run(
            ["python3", str(_SCRIPTS / "manifest_paths.py"), "--section", "engine"],
            _REPO_ROOT, _ansi_env(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scripts", result.stdout)

    def test_path_classifier_survives_an_ascii_default(self):
        result = subprocess.run(
            ["python3", str(_SCRIPTS / "scheduler" / "_classify_paths.py")],
            cwd=str(_REPO_ROOT), input="zettelkasten/_records/встреча.md\n",
            capture_output=True, text=True, encoding="utf-8", env=_ansi_env(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("OWNER\t"))

    def test_helper_stdout_is_lf_even_under_a_narrow_locale(self):
        result = _run(
            ["python3", str(_SCRIPTS / "manifest_paths.py"), "--section", "engine"],
            _REPO_ROOT, _ansi_env(),
        )
        self.assertNotIn("\r", result.stdout,
                         "a \\r here fails every path the shell builds from it")


class MsysPathConversionTests(unittest.TestCase):
    """A `git` shim that rewrites `<ref>:<path>` exactly as the MSYS runtime does."""

    SHIM = textwrap.dedent(
        """\
        #!/usr/bin/env bash
        # Stand-in for the MSYS runtime's argument rewriting. Applies to any
        # argument holding a single `:` that is not part of a `://` URL, unless
        # MSYS_NO_PATHCONV is set — which is precisely the real behaviour.
        args=()
        for a in "$@"; do
          if [ -z "${MSYS_NO_PATHCONV:-}" ] && \\
             [ "${a#-}" = "$a" ] && \\
             case "$a" in *://*) false ;; *:*) true ;; *) false ;; esac
          then
            a="$(printf '%s' "$a" | tr ':' ';' | tr '/' '\\\\')"
          fi
          args+=("$a")
        done
        exec {REAL_GIT} "${args[@]}"
        """
    )

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        with open(self.bin / "git", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self.SHIM.replace("{REAL_GIT}", real_git))
        (self.bin / "git").chmod(0o755)

        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=self.repo, check=True)
        (self.repo / ".gitignore").write_text("junk\n", encoding="utf-8")
        (self.repo / "plain.txt").write_text("x\n", encoding="utf-8")
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=self.repo, check=True, env=env)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _bash(self, snippet: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"}
        return subprocess.run(
            ["/bin/bash", "-c", f'. "{_SCRIPTS / "lib" / "git.sh"}"; {snippet}'],
            cwd=str(self.repo), capture_output=True, text=True, encoding="utf-8", env=env,
        )

    def test_the_shim_actually_breaks_a_naive_call(self):
        """Guard on the guard — the shim must reproduce the failure."""
        naive = self._bash('git cat-file -e "HEAD:.gitignore" && echo FOUND')
        self.assertNotEqual(naive.returncode, 0,
                            "the MSYS shim is not rewriting the argument")
        self.assertNotIn("FOUND", naive.stdout)

    def test_git_ref_has_path_survives_msys_on_a_dotfile(self):
        """The dotfile case is the one that broke every Windows `/minder:mem:update`."""
        result = self._bash('git_ref_has_path HEAD .gitignore && echo FOUND')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FOUND", result.stdout)

    def test_git_ref_has_path_survives_msys_on_a_plain_path(self):
        result = self._bash('git_ref_has_path HEAD plain.txt && echo FOUND')
        self.assertIn("FOUND", result.stdout, result.stderr)

    def test_git_ref_has_path_still_reports_a_genuinely_absent_path(self):
        result = self._bash('git_ref_has_path HEAD nope.txt || echo ABSENT')
        self.assertIn("ABSENT", result.stdout, result.stderr)

    def test_git_ref_read_path_survives_msys(self):
        result = self._bash('git_ref_read_path HEAD .gitignore')
        self.assertEqual(result.stdout.strip(), "junk", result.stderr)


class NoExecutableBitTests(unittest.TestCase):
    """A Windows checkout carries no mode bits — nothing may rely on one."""

    def test_every_shipped_script_runs_through_its_interpreter_without_x(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copytree(_SCRIPTS, work / "scripts",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            shutil.copy(_REPO_ROOT / ".engine-manifest.yml", work / ".engine-manifest.yml")
            for f in (work / "scripts").rglob("*"):
                if f.is_file():
                    f.chmod(f.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

            # A representative of each interpreter, invoked the sanctioned way.
            checks = [
                (["python3", "scripts/manifest_paths.py", "--section", "engine"], "python"),
                (["/bin/bash", "-n", "scripts/sync_engine.sh"], "bash"),
                (["/bin/bash", "-n", "scripts/scheduler/stage.sh"], "bash"),
            ]
            for cmd, label in checks:
                with self.subTest(interpreter=label, cmd=cmd[1]):
                    result = _run(cmd, work)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_shipped_script_is_reached_by_its_executable_bit(self):
        """`./x.sh` in a shipped file would work here and fail on Windows."""
        result = _run(
            ["python3", str(_SCRIPTS / "check_portability.py"), "--report"], _REPO_ROOT
        )
        self.assertNotIn("[exec-bit]", result.stdout, result.stdout)


class Bash32Tests(unittest.TestCase):
    """macOS ships bash 3.2 as `/bin/bash` — no simulation needed, just use it."""

    @unittest.skipUnless(sys.platform == "darwin", "the 3.2 shell is macOS's; elsewhere the parse tests below run on whatever bash the host has")
    def test_system_bash_really_is_3_2(self):
        out = subprocess.run(["/bin/bash", "--version"], capture_output=True, text=True, encoding="utf-8").stdout
        self.assertIn("version 3.2", out,
                      "this suite assumes the system shell is the old one it defends against")

    def test_every_shipped_shell_script_parses(self):
        scripts = subprocess.run(
            ["git", "ls-files", "*.sh"], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout.split()
        self.assertGreater(len(scripts), 10)
        for rel in scripts:
            with self.subTest(script=rel):
                result = subprocess.run(["/bin/bash", "-n", rel], cwd=str(_REPO_ROOT),
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_shared_library_works_under_the_old_shell(self):
        result = subprocess.run(
            ["/bin/bash", "-c",
             f'. "{_SCRIPTS / "lib" / "git.sh"}"; git_current_branch_or DETACHED'],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip())


class LineEndingTests(unittest.TestCase):
    def test_gitattributes_pins_lf_for_every_executed_format(self):
        for rel in ("scripts/sync_engine.sh", "scripts/run_migrations.py",
                    "integrations/claude-code/install.sh"):
            with self.subTest(path=rel):
                out = subprocess.run(
                    ["git", "check-attr", "eol", "--", rel],
                    cwd=str(_REPO_ROOT), capture_output=True, text=True, encoding="utf-8", check=True,
                ).stdout
                self.assertIn("eol: lf", out)


if __name__ == "__main__":
    unittest.main()


