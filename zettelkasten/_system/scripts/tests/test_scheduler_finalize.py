"""End-to-end tests for the scheduler single-commit protocol.

Covers stage.sh + finalize-tick.sh + ship-failure-note.sh in real git
worktrees with a bare origin remote, so regressions in any of:

  - engine-path filtering (via _classify_paths.py + .engine-manifest.yml)
  - heuristic commit message derivation
  - partial-tick recovery via reset --soft fold
  - refusal on owner non-scheduled commits ahead
  - ship-failure-note local-only fallback

surface as test failures rather than as drift in production scheduler logs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEDULER_DIR = REPO_ROOT / "scripts" / "scheduler"
LIB_DIR = REPO_ROOT / "scripts" / "lib"
MANIFEST = REPO_ROOT / ".engine-manifest.yml"


def _git(cwd: Path, *args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    full_env.update({
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    })
    if env:
        full_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True, encoding="utf-8",
        env=full_env,
    )


def _run_script(cwd: Path, script: str, *args: str,
                env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", f"scripts/scheduler/{script}", *args],
        cwd=cwd,
        capture_output=True,
        text=True, encoding="utf-8",
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            **(env or {}),
        },
    )


# Scheduler scripts a sandbox needs to be the shape production runs in. They
# source `scripts/lib/git.sh` and the classifier imports `lib.manifest` /
# `lib.portable`, so the lib tree is seeded alongside — in ONE place, because a
# per-test copy of this list is how a new engine dependency ends up seeded in
# some tests and not others.
_SCHEDULER_SCRIPTS = (
    "stage.sh",
    "finalize-tick.sh",
    "ship-failure-note.sh",
    "pin-main.sh",
    "_classify_paths.py",
    "_delivery_check.py",
)


def _seed_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create `origin.git` + a `work` clone carrying the scheduler surface.

    Returns `(work, origin)`. HEAD is `main`, pushed and tracking.
    """
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    work.mkdir()

    _git(work, "init", "-q", "-b", "main")
    _git(work, "remote", "add", "origin", str(origin))

    scheduler_dst = work / "scripts" / "scheduler"
    scheduler_dst.mkdir(parents=True)
    for name in _SCHEDULER_SCRIPTS:
        shutil.copy(SCHEDULER_DIR / name, scheduler_dst / name)
    shutil.copytree(LIB_DIR, work / "scripts" / "lib",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(MANIFEST, work / ".engine-manifest.yml")

    (work / "zettelkasten" / "_records").mkdir(parents=True)
    (work / "zettelkasten" / "_system" / "state").mkdir(parents=True)

    # Production ignores the scheduler's own state directory. Without it here,
    # `.scheduler-state/authored-shas` is staged as owner data and lands in the
    # delivery commit — which both misreports what a tick delivered and hides a
    # path-set check behind noise the real repository never has. The same goes for
    # bytecode: every python helper the scripts call writes `__pycache__/` beside
    # itself, which the real repository ignores. Unignored here it reads as engine
    # drift, and stage.sh stages a CLARIFICATIONS note about it — so whether a test
    # passed depended on whether a cache happened to exist when the sandbox was
    # copied.
    with open(work / ".gitignore", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(".scheduler-state/\n__pycache__/\n")

    _git(work, "add", ".gitignore", ".engine-manifest.yml", "scripts/scheduler/", "scripts/lib/")
    _git(work, "commit", "-q", "-m", "initial")
    _git(work, "push", "-q", "-u", "origin", "main")
    return work, origin


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    work, _ = _seed_repo(tmp_path)
    return work


def test_single_commit_for_mixed_staging(repo: Path) -> None:
    (repo / "zettelkasten/_records/r1.md").write_text("rec1\n", encoding="utf-8")
    (repo / "zettelkasten/_records/r2.md").write_text("rec2\n", encoding="utf-8")
    (repo / "zettelkasten/_system/state/s.md").write_text("state\n", encoding="utf-8")

    result = _run_script(repo, "finalize-tick.sh", "scheduler/process")
    assert result.returncode == 0, result.stderr

    log = _git(repo, "log", "--oneline", "origin/main..HEAD")
    assert log.stdout.strip() == "", "all commits should be pushed (no ahead)"

    head = _git(repo, "log", "--oneline", "-2")
    subjects = [line.split(" ", 1)[1] for line in head.stdout.strip().splitlines()]
    assert subjects[0].startswith("scheduler/process:")
    assert subjects[0].endswith("[scheduled]")
    assert "record(s)" in subjects[0]


def test_engine_paths_not_committed(repo: Path) -> None:
    (repo / "zettelkasten/_records/r1.md").write_text("owner data\n", encoding="utf-8")
    (repo / "scripts" / "drift.sh").write_text("# engine drift\n", encoding="utf-8")
    (repo / "integrations").mkdir(exist_ok=True)
    (repo / "integrations" / "drift.md").write_text("# more drift\n", encoding="utf-8")

    result = _run_script(repo, "finalize-tick.sh", "scheduler/process")
    assert result.returncode == 0, result.stderr

    head_files = _git(repo, "show", "--name-only", "--format=", "HEAD")
    assert "zettelkasten/_records/r1.md" in head_files.stdout
    assert "scripts/drift.sh" not in head_files.stdout
    assert "integrations/drift.md" not in head_files.stdout

    clar = repo / "zettelkasten/_system/state/CLARIFICATIONS.md"
    assert clar.exists()
    assert "engine drift" in clar.read_text(encoding="utf-8")


def test_commits_non_ascii_filenames(repo: Path) -> None:
    """Regression: Cyrillic / spaced filenames must not break staging.

    Under the default core.quotepath=true, `git status --porcelain`
    octal-escapes non-ASCII bytes (a Cyrillic name becomes "…\\320\\222…").
    stage.sh must read paths with quotepath disabled, otherwise the escaped
    pathspec never matches on `git add` and the whole tick fails to commit —
    stranding every processed record. Observed in production on a friend's
    Russian-named transcripts.
    """
    name = "20260703-встреча SPV инвестиции.md"
    f = repo / "zettelkasten/_records" / name
    # Seed + commit so the file is TRACKED. git status then reports it as an
    # individual (escaped-under-quotepath=true) path on the next change — the
    # exact condition that broke production. A brand-new untracked dir would
    # instead collapse to an unescaped dir name and mask the bug.
    f.write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed cyrillic record")
    _git(repo, "push", "-q", "origin", "main")

    f.write_text("v2\n", encoding="utf-8")  # -> " M <escaped path>"

    result = _run_script(repo, "finalize-tick.sh", "scheduler/process")
    assert result.returncode == 0, result.stderr

    # Committed and pushed — no local commits ahead of origin.
    ahead = _git(repo, "log", "--oneline", "origin/main..HEAD")
    assert ahead.stdout.strip() == ""

    # The Cyrillic-named file's change actually landed in the commit.
    head_files = _git(repo, "-c", "core.quotepath=false", "show", "--name-only", "--format=", "HEAD")
    assert name in head_files.stdout, head_files.stdout


def test_stage_is_idempotent(repo: Path) -> None:
    (repo / "zettelkasten/_records/r1.md").write_text("rec1\n", encoding="utf-8")

    r1 = _run_script(repo, "stage.sh")
    r2 = _run_script(repo, "stage.sh")
    r3 = _run_script(repo, "stage.sh")
    assert r1.returncode == 0
    assert r2.returncode == 0
    assert r3.returncode == 0

    staged = _git(repo, "diff", "--cached", "--name-only")
    assert "zettelkasten/_records/r1.md" in staged.stdout
    assert len(staged.stdout.strip().splitlines()) == 1


def test_fold_recovery_collapses_previous_scheduled_commits(repo: Path) -> None:
    (repo / "zettelkasten/_records/x.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "zettelkasten/_records/x.md")
    _git(repo, "commit", "-q", "-m", "scheduler/process: partial1 [scheduled]")
    (repo / "zettelkasten/_records/y.md").write_text("y\n", encoding="utf-8")
    _git(repo, "add", "zettelkasten/_records/y.md")
    _git(repo, "commit", "-q", "-m", "scheduler/process: partial2 [scheduled]")

    ahead_before = _git(repo, "rev-list", "--count", "origin/main..HEAD")
    assert ahead_before.stdout.strip() == "2"

    (repo / "zettelkasten/_records/z.md").write_text("z\n", encoding="utf-8")
    result = _run_script(repo, "finalize-tick.sh", "scheduler/lint")
    assert result.returncode == 0, result.stderr
    assert "folding 2 previous unpushed" in result.stdout

    ahead_after = _git(repo, "rev-list", "--count", "origin/main..HEAD")
    assert ahead_after.stdout.strip() == "0", "all folded commits pushed"

    new_commits_locally = _git(repo, "log", "--oneline", "HEAD~1..HEAD")
    assert new_commits_locally.stdout.count("\n") == 1, "single new commit"

    head_files = _git(repo, "show", "--name-only", "--format=", "HEAD")
    for fname in ("x.md", "y.md", "z.md"):
        assert fname in head_files.stdout


def test_refuses_to_reset_over_owner_manual_commit(repo: Path) -> None:
    (repo / "zettelkasten/_records/manual.md").write_text("owner work\n", encoding="utf-8")
    _git(repo, "add", "zettelkasten/_records/manual.md")
    _git(repo, "commit", "-q", "-m", "owner manual edit")

    (repo / "zettelkasten/_records/dirty.md").write_text("d\n", encoding="utf-8")
    result = _run_script(repo, "finalize-tick.sh", "scheduler/process")
    assert result.returncode == 2
    assert "refusing to reset" in result.stderr

    log = _git(repo, "log", "--oneline", "-2")
    assert "owner manual edit" in log.stdout
    assert "[scheduled]" not in log.stdout


def test_nothing_to_commit_is_noop(repo: Path) -> None:
    result = _run_script(repo, "finalize-tick.sh", "scheduler/lint")
    assert result.returncode == 0
    assert "nothing to commit" in result.stdout


def test_ship_failure_note_falls_back_to_local_when_finalize_refuses(repo: Path) -> None:
    (repo / "zettelkasten/_records/manual.md").write_text("owner work\n", encoding="utf-8")
    _git(repo, "add", "zettelkasten/_records/manual.md")
    _git(repo, "commit", "-q", "-m", "owner manual edit")

    result = _run_script(
        repo,
        "ship-failure-note.sh",
        "test cause",
        "process-scheduled",
    )
    assert result.returncode == 0, result.stderr
    assert "falling back to local-only commit" in result.stderr
    assert "committed locally" in result.stdout

    clar_text = (repo / "zettelkasten/_system/state/CLARIFICATIONS.md").read_text(encoding="utf-8")
    assert "test cause" in clar_text
    assert "process-scheduled" in clar_text

    head_subject = _git(repo, "log", "-1", "--format=%s").stdout.strip()
    assert head_subject.startswith("scheduler/failure-local:")

    ahead = _git(repo, "rev-list", "--count", "origin/main..HEAD").stdout.strip()
    assert ahead == "2", "owner commit + local failure note both unpushed"


def test_message_heuristic_records_only(repo: Path) -> None:
    for i in range(3):
        (repo / f"zettelkasten/_records/r{i}.md").write_text(f"{i}\n", encoding="utf-8")

    result = _run_script(repo, "finalize-tick.sh", "scheduler/process")
    assert result.returncode == 0

    subject = _git(repo, "log", "-1", "--format=%s").stdout.strip()
    assert subject == "scheduler/process: 3 record(s) updated [scheduled]"


FAKE_GH_SCRIPT = r"""#!/usr/bin/env bash
# Fake gh CLI for tests. Honours FAKE_GH_BARE (path to bare origin repo)
# and FAKE_GH_STATE_DIR (per-test marker dir).
set -u
state_dir="${FAKE_GH_STATE_DIR:-/tmp/fake-gh-state}"
mkdir -p "$state_dir"
bare="${FAKE_GH_BARE:-}"

slug() { printf '%s' "$1" | tr '/' '_'; }

case "$1" in
  repo)
    if [ "$2" = "view" ]; then
      echo "test-owner/test-repo"
      exit 0
    fi
    ;;
  pr)
    sub="$2"; shift 2
    case "$sub" in
      list)
        head=""
        while [ $# -gt 0 ]; do
          if [ "$1" = "--head" ]; then head="$2"; shift 2; continue; fi
          shift
        done
        marker="$state_dir/pr-$(slug "$head")"
        if [ -f "$marker" ]; then
          cat "$marker"
        fi
        exit 0
        ;;
      create)
        head=""; title=""
        while [ $# -gt 0 ]; do
          case "$1" in
            --head) head="$2"; shift 2 ;;
            --title) title="$2"; shift 2 ;;
            *) shift ;;
          esac
        done
        pr_num=$((42 + RANDOM % 1000))
        slug_head="$(slug "$head")"
        echo "$pr_num" > "$state_dir/pr-$slug_head"
        echo "$head" > "$state_dir/pr-$slug_head.branch"
        echo "$title" > "$state_dir/pr-$slug_head.title"
        echo "https://github.com/test-owner/test-repo/pull/$pr_num"
        exit 0
        ;;
      merge)
        pr="$1"; shift 1
        delete=0
        while [ $# -gt 0 ]; do
          case "$1" in
            --delete-branch) delete=1; shift ;;
            --body) printf '%s' "$2" > "$state_dir/merge-body"; shift 2 ;;
            *) shift ;;
          esac
        done
        for f in "$state_dir"/pr-*; do
          [ -f "$f" ] || continue
          case "$f" in *.branch|*.title|*.state) continue ;; esac
          stored="$(cat "$f")"
          if [ "$stored" = "$pr" ]; then
            slug_head="$(basename "$f")"
            slug_head="${slug_head#pr-}"
            branch="$(cat "$state_dir/pr-$slug_head.branch")"
            if [ -n "$bare" ]; then
              GIT_DIR="$bare" git update-ref refs/heads/main "refs/heads/$branch" || exit 1
              if [ "$delete" -eq 1 ]; then
                GIT_DIR="$bare" git update-ref -d "refs/heads/$branch" || true
              fi
              echo "MERGED" > "$state_dir/pr-$pr.state"
              exit 0
            fi
            exit 0
          fi
        done
        echo "fake-gh: PR $pr not found" >&2
        exit 1
        ;;
      view)
        pr="$1"; shift 1
        if [ -f "$state_dir/pr-$pr.state" ]; then
          cat "$state_dir/pr-$pr.state"
        else
          echo "OPEN"
        fi
        exit 0
        ;;
    esac
    ;;
  api)
    method=""; endpoint=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -X|--method) method="$2"; shift 2 ;;
        repos/*) endpoint="$1"; shift ;;
        *) shift ;;
      esac
    done
    if [ "${method:-}" = "DELETE" ] && [ -n "$bare" ]; then
      branch="${endpoint##*/heads/}"
      GIT_DIR="$bare" git update-ref -d "refs/heads/$branch" 2>/dev/null || true
      exit 0
    fi
    exit 0
    ;;
esac
echo "fake-gh: unknown command: $*" >&2
exit 1
"""


def _install_fake_gh(tmp_path: Path, bare_origin: Path) -> tuple[Path, dict]:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    state_dir = tmp_path / "fake-gh-state"
    state_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH_SCRIPT, encoding="utf-8")
    gh.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_GH_BARE": str(bare_origin),
        "FAKE_GH_STATE_DIR": str(state_dir),
    }
    return bin_dir, env


def test_routines_mode_push_to_sandbox_and_pr_merge(tmp_path: Path) -> None:
    work, origin = _seed_repo(tmp_path)

    state_dir = work / ".scheduler-state"
    state_dir.mkdir()
    (state_dir / "start-branch").write_text("claude/test-sandbox-XYZ\n", encoding="utf-8")

    _, gh_env = _install_fake_gh(tmp_path, origin)

    (work / "zettelkasten/_records/r1.md").write_text("rec1\n", encoding="utf-8")
    (work / "zettelkasten/_records/r2.md").write_text("rec2\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", "scripts/scheduler/finalize-tick.sh", "scheduler/process"],
        cwd=work,
        capture_output=True,
        text=True, encoding="utf-8",
        env={
            **os.environ,
            **gh_env,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "ROUTINES mode" in result.stdout
    assert "PR #" in result.stdout
    assert "squash-merged" in result.stdout

    refs = subprocess.run(
        ["git", "ls-remote", "--heads", str(origin)],
        capture_output=True,
        text=True, encoding="utf-8",
        check=True,
    )
    assert "claude/test-sandbox-XYZ" not in refs.stdout, "sandbox branch must be deleted"
    assert "refs/heads/main" in refs.stdout, "main must exist"

    main_log = subprocess.run(
        ["git", "log", "--format=%s", "-1", "main"],
        cwd=origin,
        capture_output=True,
        text=True, encoding="utf-8",
        check=True,
    )
    assert "scheduler/process:" in main_log.stdout
    assert "[scheduled]" in main_log.stdout

    # An empty squash body lets GitHub compose its own, which credits the sandbox
    # commit's author with a Co-authored-by trailer on main.
    merge_body = (tmp_path / "fake-gh-state" / "merge-body").read_text(encoding="utf-8")
    assert merge_body.strip(), "squash merge must pass an explicit, non-empty body"


def _second_clone(tmp_path: Path, origin: Path, name: str) -> Path:
    """A clone of `origin` that is guaranteed to be on `main`.

    `git clone` of a repository whose HEAD points at a branch the clone cannot
    resolve leaves the checkout on no branch at all ("remote HEAD refers to
    nonexistent ref"), and a later `git push origin main` then fails with nothing
    to push. That passed locally on a git that guessed `main` anyway and failed in
    CI — so the branch is asserted here rather than assumed.
    """
    other = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "config", "user.email", "test@example.com")
    _git(other, "config", "user.name", "test")
    _git(other, "checkout", "-q", "-B", "main", "origin/main")
    # `symbolic-ref --short -q`, never `rev-parse --abbrev-ref`: the latter prints
    # the literal string `HEAD` on a detached checkout, so it would report success
    # in precisely the state this assertion exists to catch. The engine's own
    # portability gate names this rule — and caught this line when I wrote it the
    # wrong way.
    branch = _git(other, "symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.strip()
    assert branch == "main", f"second clone is on {branch or 'a detached HEAD'!r}, not main"
    return other


def _clone_and_push(tmp_path: Path, origin: Path, rel: str, body: str, subject: str) -> None:
    """A second clone delivers while the tick under test is still running."""
    other = _second_clone(tmp_path, origin, f"other-{abs(hash(rel)) % 10000}")
    target = other / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", subject)
    _git(other, "push", "-q", "origin", "main")


def test_delivery_never_reverts_a_push_that_landed_mid_tick(tmp_path: Path) -> None:
    """The defect, pinned: the fold must not reinstate the tick's starting tree.

    A tick pins `origin/main`, commits its own work, and only then a concurrent
    tick delivers. Folding onto the fetched tip commits the stale index over it,
    which is how six real deliveries erased a day of records each.
    """
    work, origin = _seed_repo(tmp_path)

    (work / "zettelkasten/_system/state/log_lint.md").write_text("tick work\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "roles: one — ok, 1 write(s) [scheduled]")
    state = work / ".scheduler-state"
    state.mkdir(exist_ok=True)
    (state / "authored-shas").write_text(
        _git(work, "rev-parse", "HEAD").stdout.strip() + "\n", encoding="utf-8")

    _clone_and_push(tmp_path, origin, "zettelkasten/_records/concurrent.md", "keep me\n",
                    "scheduler/process: 1 record(s) updated [scheduled]")

    result = _run_script(work, "finalize-tick.sh", "scheduler/roles")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    survived = subprocess.run(
        ["git", "show", "main:zettelkasten/_records/concurrent.md"],
        cwd=origin, capture_output=True, text=True, encoding="utf-8")
    assert survived.returncode == 0, "the concurrent record was deleted from origin/main"
    assert "keep me" in survived.stdout

    delivered = subprocess.run(
        ["git", "show", "main:zettelkasten/_system/state/log_lint.md"],
        cwd=origin, capture_output=True, text=True, encoding="utf-8")
    assert delivered.returncode == 0 and "tick work" in delivered.stdout, (
        "the tick's own work must still be delivered")


def test_a_stale_version_of_a_staged_file_cannot_reach_origin(tmp_path: Path) -> None:
    """The hard case: the victim file IS in the tick's own surface.

    A path allowlist cannot help here — the tick legitimately handled that file, so
    membership proves nothing about the content. What protects the concurrent change
    is the integration step: the tick's patch is replayed onto the moved tip, and a
    tick carrying a pre-concurrent version of the same lines conflicts instead of
    overwriting. This test exists because the earlier one kept the victim OUT of the
    surface and therefore only exercised path membership.
    """
    work, origin = _seed_repo(tmp_path)
    (work / "zettelkasten/_records/shared.md").write_text("line one\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "seed shared file")
    _git(work, "push", "-q", "origin", "main")

    (work / "zettelkasten/_records/shared.md").write_text(
        "line one\ntick line\n", encoding="utf-8")
    _git(work, "add", "zettelkasten/_records/shared.md")
    state = work / ".scheduler-state"
    state.mkdir(exist_ok=True)
    (state / "staged-paths").write_text(
        "zettelkasten/_records/shared.md\n", encoding="utf-8")
    _git(work, "commit", "-q", "-m", "roles: one — ok [scheduled]")
    (state / "authored-shas").write_text(
        _git(work, "rev-parse", "HEAD").stdout.strip() + "\n", encoding="utf-8")

    _clone_and_push(tmp_path, origin, "zettelkasten/_records/shared.md",
                    "line one\nCONCURRENT LINE\n",
                    "scheduler/process: 1 record(s) updated [scheduled]")

    result = _run_script(work, "finalize-tick.sh", "scheduler/roles")
    assert result.returncode != 0, (
        "a tick whose tree predates the concurrent change must not deliver:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}")

    delivered = subprocess.run(
        ["git", "show", "main:zettelkasten/_records/shared.md"],
        cwd=origin, capture_output=True, text=True, encoding="utf-8")
    assert "CONCURRENT LINE" in delivered.stdout, (
        "the concurrent content must still be what origin/main holds")


def test_delivery_refuses_a_change_the_tick_never_staged(tmp_path: Path) -> None:
    """The invariant is on content: a path the tick never wrote may not move.

    Path membership is not the check — this plants a deletion inside the tick's
    own commit, which a path-level subset test would wave through as soon as the
    file appears in the staged set.
    """
    work, origin = _seed_repo(tmp_path)
    (work / "zettelkasten/_records/owner-note.md").write_text("owner\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "seed owner note")
    _git(work, "push", "-q", "origin", "main")

    (work / "zettelkasten/_records/owner-note.md").unlink()
    (work / "zettelkasten/_system/state/log_lint.md").write_text("tick\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "roles: one — ok [scheduled]")
    state = work / ".scheduler-state"
    state.mkdir(exist_ok=True)
    (state / "authored-shas").write_text(
        _git(work, "rev-parse", "HEAD").stdout.strip() + "\n", encoding="utf-8")
    (state / "staged-paths").write_text(
        "zettelkasten/_system/state/log_lint.md\n", encoding="utf-8")

    result = _run_script(work, "finalize-tick.sh", "scheduler/roles")
    assert result.returncode == 2, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "owner-note" in result.stderr

    still_there = subprocess.run(
        ["git", "show", "main:zettelkasten/_records/owner-note.md"],
        cwd=origin, capture_output=True, text=True, encoding="utf-8")
    assert still_there.returncode == 0, "nothing may be pushed when the invariant trips"


def test_pinning_moves_a_clean_main_forward_and_leaves_local_commits_alone(
        tmp_path: Path) -> None:
    """Both halves of pinning, because fixing one of them broke the other.

    Removing the rebase stopped the SHA-identity wedge and also stopped the tree
    from advancing at all — so a tick with nothing of its own read yesterday's
    inbox, state and registries, and no careful delivery afterwards can undo a
    decision taken on stale input. A clean main fast-forwards; a main carrying the
    tick's own commits is left exactly as it is.
    """
    work, origin = _seed_repo(tmp_path)
    _clone_and_push(tmp_path, origin, "zettelkasten/_records/arrived.md", "new\n",
                    "scheduler/process: 1 record(s) updated [scheduled]")

    result = _run_script(work, "pin-main.sh")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "fast-forwarded" in result.stdout
    assert (work / "zettelkasten/_records/arrived.md").exists(), (
        "the tick must see what arrived before it starts working")

    # Now the tick has work of its own, and a further push lands upstream.
    (work / "zettelkasten/_system/state/log_lint.md").write_text("mine\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "roles: one — ok [scheduled]")
    mine = _git(work, "rev-parse", "HEAD").stdout.strip()
    _clone_and_push(tmp_path, origin, "zettelkasten/_records/later.md", "later\n",
                    "scheduler/process: 1 record(s) updated [scheduled]")

    second = _run_script(work, "pin-main.sh")
    assert second.returncode == 0, f"stdout={second.stdout}\nstderr={second.stderr}"
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == mine, (
        "the tick's own commit must not be rewritten or dropped by pinning")


def test_a_stale_tick_cannot_overwrite_what_arrived_while_it_ran(tmp_path: Path) -> None:
    """The defect where it actually lives: the tick's tree is older than the tip.

    Not "a tick wrote something wrong" — no rail can tell that from legitimate
    work, because the tick staged the content itself and only the owner knows what
    was meant. The defect is narrower and mechanical: the tick's commit carries a
    version of a file from BEFORE a concurrent change that has since been
    delivered. Replaying the tick's own patch onto the moved tip is what keeps the
    concurrent content, and this test is what proves it does.
    """
    work, origin = _seed_repo(tmp_path)
    (work / "zettelkasten/_records/shared.md").write_text("line one\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "seed shared file")
    _git(work, "push", "-q", "origin", "main")

    # The tick pins here and appends its own line, knowing nothing of what follows.
    (work / "zettelkasten/_records/shared.md").write_text(
        "line one\ntick line\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "roles: one — ok [scheduled]")
    state = work / ".scheduler-state"
    state.mkdir(exist_ok=True)
    (state / "authored-shas").write_text(
        _git(work, "rev-parse", "HEAD").stdout.strip() + "\n", encoding="utf-8")
    (state / "staged-paths").write_text(
        "zettelkasten/_records/shared.md\n", encoding="utf-8")

    # Meanwhile another clone prepends its own line to the same file and delivers.
    other = _second_clone(tmp_path, origin, "other-shared")
    (other / "zettelkasten/_records/shared.md").write_text(
        "concurrent line\nline one\n", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "scheduler/process: 1 record(s) updated [scheduled]")
    _git(other, "push", "-q", "origin", "main")

    result = _run_script(work, "finalize-tick.sh", "scheduler/roles")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    delivered = subprocess.run(
        ["git", "show", "main:zettelkasten/_records/shared.md"],
        cwd=origin, capture_output=True, text=True, encoding="utf-8")
    assert delivered.returncode == 0, delivered.stderr
    assert "concurrent line" in delivered.stdout, "the concurrent change was overwritten"
    assert "tick line" in delivered.stdout, "the tick's own work was lost"


def test_a_failed_tick_survives_the_next_pinning(tmp_path: Path) -> None:
    """Authorship must outlive pinning, or a stuck tick stays stuck forever.

    `pin-main.sh` used to replay local commits, which rewrote their SHAs — and
    finalize authorises by exact SHA, so the rewritten commit read as unauthored
    and every later tick refused to touch it.
    """
    work, origin = _seed_repo(tmp_path)

    (work / "zettelkasten/_system/state/log_lint.md").write_text("first try\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "roles: one — ok [scheduled]")
    state = work / ".scheduler-state"
    state.mkdir(exist_ok=True)
    (state / "authored-shas").write_text(
        _git(work, "rev-parse", "HEAD").stdout.strip() + "\n", encoding="utf-8")
    # The real flow records a path when the step stages it, and the record survives
    # until a delivery succeeds — which is what lets a retried tick still prove its
    # own work. Writing it here is what makes this fixture the failed-tick case
    # rather than a tick whose record was lost.
    (state / "staged-paths").write_text(
        "zettelkasten/_system/state/log_lint.md\n", encoding="utf-8")

    _clone_and_push(tmp_path, origin, "zettelkasten/_records/later.md", "later\n",
                    "scheduler/process: 1 record(s) updated [scheduled]")

    pinned = _run_script(work, "pin-main.sh")
    assert pinned.returncode == 0, f"stdout={pinned.stdout}\nstderr={pinned.stderr}"

    result = _run_script(work, "finalize-tick.sh", "scheduler/roles")
    assert result.returncode == 0, (
        "the tick's own commit must still be recognised after pinning:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}")

    for rel, needle in (("zettelkasten/_records/later.md", "later"),
                        ("zettelkasten/_system/state/log_lint.md", "first try")):
        got = subprocess.run(["git", "show", f"main:{rel}"], cwd=origin,
                             capture_output=True, text=True, encoding="utf-8")
        assert got.returncode == 0 and needle in got.stdout, rel


def test_routines_mode_gh_missing_fails_gracefully(tmp_path: Path) -> None:
    work, _origin = _seed_repo(tmp_path)

    state_dir = work / ".scheduler-state"
    state_dir.mkdir()
    (state_dir / "start-branch").write_text("claude/no-gh-XYZ\n", encoding="utf-8")

    (work / "zettelkasten/_records/r1.md").write_text("rec1\n", encoding="utf-8")

    # Build a PATH that genuinely lacks `gh`: on GitHub runners gh lives in
    # /usr/bin, so just dropping homebrew dirs is not enough. Symlink every
    # system tool except gh into a sandbox dir and use it as the sole PATH.
    sandbox_bin = tmp_path / "sandbox-bin"
    sandbox_bin.mkdir()
    for bin_dir in ("/usr/bin", "/bin"):
        for tool in Path(bin_dir).iterdir():
            if tool.name == "gh":
                continue
            try:
                (sandbox_bin / tool.name).symlink_to(tool)
            except FileExistsError:
                pass  # same tool present in both dirs
    minimal_path = str(sandbox_bin)

    result = subprocess.run(
        ["bash", "scripts/scheduler/finalize-tick.sh", "scheduler/process"],
        cwd=work,
        capture_output=True,
        text=True, encoding="utf-8",
        env={
            "PATH": minimal_path,
            "HOME": str(tmp_path),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    assert result.returncode == 2
    assert "gh CLI not found" in result.stderr
    local_head = _git(work, "log", "--format=%s", "-1").stdout.strip()
    assert "scheduler/process:" in local_head



def test_classifier_uses_manifest(tmp_path: Path) -> None:
    paths = "\n".join([
        "zettelkasten/_records/x.md",
        "scripts/scheduler/stage.sh",
        ".engine-manifest.yml",
        "zettelkasten/_system/state/s.md",
        "zettelkasten/_system/docs/SYSTEM_CONFIG.md",
        "some/random/path/AUDIENCES.template.md",
    ])
    result = subprocess.run(
        ["python3", str(SCHEDULER_DIR / "_classify_paths.py")],
        input=paths,
        capture_output=True,
        text=True, encoding="utf-8",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    got: dict[str, str] = {}
    for line in result.stdout.strip().splitlines():
        label, path = line.split("\t", 1)
        got[path] = label
    assert got == {
        "zettelkasten/_records/x.md": "OWNER",
        "scripts/scheduler/stage.sh": "ENGINE",
        ".engine-manifest.yml": "ENGINE",
        "zettelkasten/_system/state/s.md": "OWNER",
        "zettelkasten/_system/docs/SYSTEM_CONFIG.md": "ENGINE",
        "some/random/path/AUDIENCES.template.md": "ENGINE",
    }


# ---------------------------------------------------------------------------
# Branch identity — the detached-HEAD delivery bug
# ---------------------------------------------------------------------------
#
# `git rev-parse --abbrev-ref HEAD` exits 0 and prints the literal string
# `HEAD` on a detached checkout, so the old `|| echo DETACHED` fallback in
# pin-main.sh never fired. That literal reached finalize-tick.sh, whose LOCAL
# test matched only `main` / `DETACHED` / empty — so a detached tick fell
# through to ROUTINES mode and tried to open a PR against a branch called
# `HEAD`. These pin both halves.


def _lib_git(work: Path, snippet: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'. scripts/lib/git.sh; {snippet}'],
        cwd=work,
        capture_output=True,
        text=True, encoding="utf-8",
    )


def test_git_current_branch_is_empty_and_nonzero_when_detached(tmp_path: Path) -> None:
    work, _ = _seed_repo(tmp_path)
    _git(work, "checkout", "-q", "--detach", "HEAD")

    result = _lib_git(work, "git_current_branch")
    assert result.stdout.strip() == "", "detached HEAD must yield no branch name"
    assert result.returncode != 0, "detached HEAD must be reported by exit status"

    # The primitive it replaces does neither — this is the whole bug.
    legacy = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # portability-ok: the assertion's subject
        cwd=work, capture_output=True, text=True, encoding="utf-8",
    )
    assert legacy.stdout.strip() == "HEAD" and legacy.returncode == 0


def test_git_current_branch_reports_the_branch_when_attached(tmp_path: Path) -> None:
    work, _ = _seed_repo(tmp_path)
    result = _lib_git(work, "git_current_branch")
    assert result.stdout.strip() == "main"
    assert result.returncode == 0


def test_pin_main_records_detached_not_the_literal_head(tmp_path: Path) -> None:
    work, _ = _seed_repo(tmp_path)
    shutil.copy(SCHEDULER_DIR / "pin-main.sh", work / "scripts" / "scheduler" / "pin-main.sh")
    _git(work, "checkout", "-q", "--detach", "HEAD")

    result = _run_script(work, "pin-main.sh")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    recorded = (work / ".scheduler-state" / "start-branch").read_text(encoding="utf-8").strip()
    assert recorded == "DETACHED", f"detached start recorded as {recorded!r}"


def test_pin_main_records_the_sandbox_branch_name(tmp_path: Path) -> None:
    work, _ = _seed_repo(tmp_path)
    shutil.copy(SCHEDULER_DIR / "pin-main.sh", work / "scripts" / "scheduler" / "pin-main.sh")
    _git(work, "checkout", "-q", "-b", "claude/admiring-shannon-ETCE3")

    result = _run_script(work, "pin-main.sh")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    recorded = (work / ".scheduler-state" / "start-branch").read_text(encoding="utf-8").strip()
    assert recorded == "claude/admiring-shannon-ETCE3"


@pytest.mark.parametrize("recorded", ["HEAD", "DETACHED", "main", ""])
def test_finalize_takes_local_mode_for_every_non_branch_value(
    repo: Path, recorded: str
) -> None:
    """A stale `HEAD` must never route delivery through gh + `HEAD:HEAD`."""
    state_dir = repo / ".scheduler-state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "start-branch").write_text(f"{recorded}\n", encoding="utf-8")

    (repo / "zettelkasten" / "_records" / "r1.md").write_text("rec\n", encoding="utf-8")

    result = _run_script(repo, "finalize-tick.sh", "scheduler/process")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "LOCAL mode" in result.stdout
    assert "ROUTINES mode" not in result.stdout


# ---------------------------------------------------------------------------
# The identity a delivery declares: the base its tree was built on, and its run.
# `recover_reverted_ticks.py` decides a stale delivery by the declared base, so a
# delivery that declares the wrong one — or none, through a route that silently
# drops the message body — turns a provable incident back into a guess.
# ---------------------------------------------------------------------------

import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib import tick_identity  # noqa: E402


def _origin_message(origin: Path) -> str:
    return subprocess.run(["git", "log", "-1", "--format=%B", "main"], cwd=origin,
                          capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def test_a_local_delivery_declares_the_base_it_was_built_on(tmp_path: Path) -> None:
    """The tip moved while the tick ran: the declared base is where the tick started,
    not the tip it was integrated onto — that difference is the whole signal."""
    work, origin = _seed_repo(tmp_path)
    started_on = _git(work, "rev-parse", "HEAD").stdout.strip()

    _clone_and_push(tmp_path, origin, "zettelkasten/_records/concurrent.md", "keep\n",
                    "scheduler/process: 1 record(s) updated [scheduled]")
    moved_tip = subprocess.run(["git", "rev-parse", "main"], cwd=origin, capture_output=True,
                               text=True, check=True).stdout.strip()
    assert moved_tip != started_on

    (work / "zettelkasten/_records/own.md").write_text("own\n", encoding="utf-8")
    result = _run_script(work, "finalize-tick.sh", "scheduler/roles",
                         env={"CLAUDE_CODE_SESSION_ID": "session-abc-123"})
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    delivered = _origin_message(origin)
    ident = tick_identity.parse(delivered)
    assert ident.status == "valid", delivered
    assert ident.base == started_on, "the base is what the tick read, not the tip it landed on"
    assert ident.run == "session-abc-123", "the run id joins the commit to its session"
    subject = delivered.splitlines()[0]
    assert subject == "scheduler/roles: 1 record(s) updated [scheduled]", (
        "the subject is what existing readers parse, and it does not change")


def test_a_folded_delivery_declares_the_fork_point(tmp_path: Path) -> None:
    """A commit left behind by a failed tick is folded into this one. The tree this
    tick worked from is that commit on top of ITS base, so the base is the fork
    point — and nothing is read from `.scheduler-state`, which outlives runs."""
    work, origin = _seed_repo(tmp_path)
    fork = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "zettelkasten/_system/state/log_lint.md").write_text("left behind\n",
                                                                  encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "scheduler/lint: state: routine update (1 file(s)) [scheduled]")
    state = work / ".scheduler-state"
    state.mkdir(exist_ok=True)
    (state / "authored-shas").write_text(_git(work, "rev-parse", "HEAD").stdout.strip() + "\n",
                                         encoding="utf-8")
    _clone_and_push(tmp_path, origin, "zettelkasten/_records/concurrent.md", "keep\n",
                    "garmin: metric day")

    (work / "zettelkasten/_records/own.md").write_text("own\n", encoding="utf-8")
    result = _run_script(work, "finalize-tick.sh", "scheduler/lint")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    ident = tick_identity.parse(_origin_message(origin))
    assert ident.status == "valid"
    assert ident.base == fork
    assert ident.run, "a run id is generated when the runtime gives none"


def test_a_routines_delivery_hands_the_identity_to_the_squash(tmp_path: Path) -> None:
    """A squash merge writes a NEW message on `main` from what it is handed. Handed
    only the lead line, the identity would stop at the sandbox branch."""
    work, origin = _seed_repo(tmp_path)
    started_on = _git(work, "rev-parse", "HEAD").stdout.strip()
    state_dir = work / ".scheduler-state"
    state_dir.mkdir()
    (state_dir / "start-branch").write_text("claude/test-sandbox-ID\n", encoding="utf-8")
    _, gh_env = _install_fake_gh(tmp_path, origin)

    (work / "zettelkasten/_records/r1.md").write_text("rec1\n", encoding="utf-8")
    result = _run_script(work, "finalize-tick.sh", "scheduler/process",
                         env={**gh_env, "CLAUDE_CODE_SESSION_ID": "sess-routines"})
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    body = (tmp_path / "fake-gh-state" / "merge-body").read_text(encoding="utf-8")
    assert body.splitlines()[0] == tick_identity.SQUASH_LEAD, (
        "the lead line stays: an empty or identity-only body is still composed by GitHub")
    ident = tick_identity.parse(body)
    assert ident.status == "valid", body
    assert (ident.base, ident.run) == (started_on, "sess-routines")


def test_an_identity_failure_never_blocks_delivery(tmp_path: Path) -> None:
    """Declaring the base is instrumentation. A tick whose identity cannot be written
    still delivers its work — losing a day of records to protect a label would invert
    the priorities the label exists to serve."""
    work, origin = _seed_repo(tmp_path)
    (work / "scripts/lib/tick_identity.py").write_text("raise SystemExit(7)\n", encoding="utf-8")
    _git(work, "commit", "-q", "-am", "break the identity writer")
    _git(work, "push", "-q", "origin", "main")

    (work / "zettelkasten/_records/own.md").write_text("own\n", encoding="utf-8")
    result = _run_script(work, "finalize-tick.sh", "scheduler/process")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "identity" in result.stderr.lower(), "the missing identity is named, not silent"
    assert tick_identity.parse(_origin_message(origin)).status == "absent"
    shown = subprocess.run(["git", "show", "main:zettelkasten/_records/own.md"], cwd=origin,
                           capture_output=True, text=True, encoding="utf-8")
    assert shown.returncode == 0, "the work itself was delivered"


def test_a_local_failure_note_declares_its_identity(repo: Path) -> None:
    """`ship-failure-note.sh` commits `[scheduled]` work that a later save delivers,
    so it declares its base like any other scheduled commit.

    This fallback runs precisely when the owner's own commits sit ahead of
    `origin/main`, so the tree the tick read already contains them. Declaring the
    older `origin/main` would make the tick look blind to the owner's commit — and a
    deliberate change the tick made on top of it would then prove as a stale revert.
    The declared base is the commit the tree was built on.
    """
    (repo / "zettelkasten/_records/manual.md").write_text("owner work\n", encoding="utf-8")
    _git(repo, "add", "zettelkasten/_records/manual.md")
    _git(repo, "commit", "-q", "-m", "owner manual edit")
    started_on = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = _run_script(repo, "ship-failure-note.sh", "test cause", "process-scheduled")
    assert result.returncode == 0, result.stderr
    ident = tick_identity.parse(_git(repo, "log", "-1", "--format=%B").stdout)
    assert ident.status == "valid"
    assert ident.base == started_on


def test_squash_body_of_a_commit_without_identity_is_the_lead_alone(tmp_path: Path) -> None:
    work, _ = _seed_repo(tmp_path)
    res = subprocess.run(["python3", "scripts/lib/tick_identity.py", "squash-body"], cwd=work,
                         capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == tick_identity.SQUASH_LEAD


def test_text_passed_into_a_subject_cannot_forge_a_declaration(repo: Path) -> None:
    """An override message or a failure cause is free text. A newline in it must not
    become a declaration line of its own — an injected older base is exactly the
    input that turns a deliberate change into a false incident."""
    forged = "0" * 39 + "1"
    (repo / "zettelkasten/_records/own.md").write_text("own\n", encoding="utf-8")
    result = _run_script(repo, "finalize-tick.sh", "scheduler/process",
                         f"batch\n\nMinder-Tick-Base: {forged}")
    assert result.returncode == 0, result.stderr
    message = _git(repo, "log", "-1", "--format=%B").stdout
    assert message.splitlines()[0].startswith("scheduler/process: batch"), message
    ident = tick_identity.parse(message)
    assert ident.status == "valid", message
    assert ident.base != forged


def test_a_forged_line_is_ignored_even_when_the_writer_is_down() -> None:
    """With no real declaration beside it, a forged line in the subject paragraph
    is not read at all — only lines after the subject paragraph count."""
    forged = "0" * 39 + "1"
    assert tick_identity.parse(f"subject\nMinder-Tick-Base: {forged}").status == "absent"


def test_a_routines_squash_body_is_never_empty_when_the_helper_fails(tmp_path: Path) -> None:
    work, origin = _seed_repo(tmp_path)
    (work / "scripts/lib/tick_identity.py").write_text("raise SystemExit(7)\n", encoding="utf-8")
    _git(work, "commit", "-q", "-am", "break the identity writer")
    _git(work, "push", "-q", "origin", "main")
    state_dir = work / ".scheduler-state"
    state_dir.mkdir()
    (state_dir / "start-branch").write_text("claude/test-sandbox-EMPTY\n", encoding="utf-8")
    _, gh_env = _install_fake_gh(tmp_path, origin)

    (work / "zettelkasten/_records/r1.md").write_text("rec1\n", encoding="utf-8")
    result = _run_script(work, "finalize-tick.sh", "scheduler/process", env=gh_env)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    body = (tmp_path / "fake-gh-state" / "merge-body").read_text(encoding="utf-8")
    assert body.strip(), "an empty squash body lets GitHub credit the sandbox author"
