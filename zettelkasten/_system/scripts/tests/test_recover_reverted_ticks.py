"""Tests for `scripts/recover_reverted_ticks.py` — detection, proof, recovery.

The defect these exercise: a scheduler tick folded its commits onto a moved
`origin/main`, so its single commit reinstated the tick's own starting snapshot
and reverted whatever arrived in between. This suite builds that shape
synthetically — a base, a concurrent push, a stale-tree commit on top — and
asserts three things the tool must never get wrong:

  1. it names a stale-tree delivery,
  2. it never writes on anything that merely *looks* like one (a deliberate
     revert restores an ancestor's tree exactly and is not the defect),
  3. it refuses rather than mixing its writes with the owner's uncommitted work.

Every repository is built inside `tmp_path`; nothing reads the authoring tree.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
TOOL = REPO_ROOT / "scripts" / "recover_reverted_ticks.py"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    })
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True,
                          text=True, encoding="utf-8", env=env)


def _tool(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["python3", str(TOOL), *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8")


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _damaged(tmp_path: Path) -> tuple[Path, str]:
    """A repository carrying one stale-tree delivery.

    Returns `(repo, bad_sha)`. History:

        base  →  concurrent (a process tick's work)  →  bad (the stale tick)

    `bad`'s tree equals `base` everywhere except the tick's own two files, so
    the concurrent tick's note and its log line are gone from the tip.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")

    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n")
    _write(repo, "zettelkasten/_system/roles/pm/state/today.md", "day one\n")
    _git(repo, "add", "."), _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # A concurrent tick delivers a batch: two notes, a record, its manifest, and
    # the log line that says it ran. A real stale delivery reverts the whole
    # interval, not one file, and the detector's floor reflects that.
    concurrent_files = {
        "zettelkasten/2_areas/work/20260910-insight-kept.md": "concurrent work\n",
        "zettelkasten/2_areas/work/20260910-decision-also-kept.md": "second note\n",
        "zettelkasten/_records/meetings/20260910-meeting-kept.md": "a meeting\n",
        "zettelkasten/_system/state/batches/20260910-110000-process.json": "{}\n",
    }
    for rel, body in concurrent_files.items():
        _write(repo, rel, body)
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n- concurrent run\n")
    _git(repo, "add", "."), _git(repo, "commit", "-q", "-m",
                                 "scheduler/process: process batch: 1 record(s) [scheduled]")

    # The stale tick: tree of `base` + its own work on top.
    _git(repo, "read-tree", base)
    _git(repo, "checkout-index", "-a", "-f")
    for rel in concurrent_files:
        (repo / rel).unlink()
    _write(repo, "zettelkasten/_system/roles/pm/state/today.md", "day two\n")
    _write(repo, "zettelkasten/_system/roles/pm/log.jsonl", '{"outcome": "ok"}\n')
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m",
                                  "scheduler/roles: process batch: 1 record(s) [scheduled]")
    return repo, _git(repo, "rev-parse", "HEAD").stdout.strip()


def _deliberate_revert(tmp_path: Path) -> Path:
    """A repository whose last commit is an intentional full revert.

    Same restored-blob signature as the defect — the tree goes back to an
    ancestor exactly — and no own work on top. The tool must report it and
    write nothing.
    """
    repo = tmp_path / "revert"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "zettelkasten/2_areas/work/a.md", "one\n")
    _git(repo, "add", "."), _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write(repo, "zettelkasten/2_areas/work/b.md", "two\n")
    _write(repo, "zettelkasten/2_areas/work/a.md", "one changed\n")
    _git(repo, "add", "."), _git(repo, "commit", "-q", "-m", "add b, touch a")
    _git(repo, "read-tree", base), _git(repo, "checkout-index", "-a", "-f")
    (repo / "zettelkasten/2_areas/work/b.md").unlink()
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m", 'Revert "add b, touch a"')
    return repo


def test_detect_names_the_stale_delivery(tmp_path: Path) -> None:
    repo, bad = _damaged(tmp_path)
    res = _tool(repo, "detect", "--json")
    assert res.returncode == 0, res.stderr
    found = json.loads(res.stdout)
    assert [c["commit"] for c in found] == [bad[:10]], found


def test_a_deliberate_revert_is_reported_but_never_written(tmp_path: Path) -> None:
    repo = _deliberate_revert(tmp_path)
    before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    res = _tool(repo, "apply", "--json")
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload["applied"] == [], payload
    assert _git(repo, "status", "--porcelain").stdout == ""
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == before


def _scheduled_revert_with_a_log_line(tmp_path: Path) -> Path:
    """A deliberate rollback by a scheduled run — which also writes its log.

    The realistic shape the first proof missed: "own work on top" is satisfied by
    the audit line every tick appends, so provenance + stale-tree shape + own work
    all hold while the commit is an intentional revert. Restoring here would undo
    a rollback the owner meant.
    """
    repo = tmp_path / "sched-revert"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n")
    _write(repo, "zettelkasten/2_areas/work/keep.md", "one\n")
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    for rel, body in (("zettelkasten/2_areas/work/a.md", "a\n"),
                      ("zettelkasten/2_areas/work/b.md", "b\n"),
                      ("zettelkasten/2_areas/work/keep.md", "one changed\n")):
        _write(repo, rel, body)
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m",
                                  "scheduler/process: batch [scheduled]")

    # The deliberate rollback: back to `base` for those three paths, plus this
    # run's own log line.
    _git(repo, "read-tree", base), _git(repo, "checkout-index", "-a", "-f")
    for rel in ("zettelkasten/2_areas/work/a.md", "zettelkasten/2_areas/work/b.md"):
        (repo / rel).unlink()
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n- rollback run\n")
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m",
                                  "scheduler/process: roll back the batch [scheduled]")
    return repo


def test_a_scheduled_rollback_with_its_own_log_line_is_never_written(tmp_path: Path) -> None:
    repo = _scheduled_revert_with_a_log_line(tmp_path)
    before = _git(repo, "rev-parse", "HEAD").stdout.strip()

    res = _tool(repo, "apply", "--json")
    assert res.returncode in (0, 3), res.stderr
    payload = json.loads(res.stdout)
    assert payload["applied"] == [], (
        "a deliberate rollback must not be undone just because the run also logged")
    assert _git(repo, "status", "--porcelain").stdout == ""
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == before
    for rel in ("zettelkasten/2_areas/work/a.md", "zettelkasten/2_areas/work/b.md"):
        assert not (repo / rel).exists(), f"{rel} was resurrected"


def test_apply_restores_the_lost_paths_and_keeps_the_ticks_own_work(tmp_path: Path) -> None:
    repo, _ = _damaged(tmp_path)
    res = _tool(repo, "apply")
    assert res.returncode == 0, res.stderr
    kept = repo / "zettelkasten/2_areas/work/20260910-insight-kept.md"
    assert kept.exists(), "the concurrent tick's note is back"
    assert kept.read_text(encoding="utf-8") == "concurrent work\n"
    log = (repo / "zettelkasten/_system/state/log_process.md").read_text(encoding="utf-8")
    assert "concurrent run" in log
    own = repo / "zettelkasten/_system/roles/pm/state/today.md"
    assert own.read_text(encoding="utf-8") == "day two\n", "the tick's own work stays"


def test_apply_is_idempotent(tmp_path: Path) -> None:
    repo, _ = _damaged(tmp_path)
    assert _tool(repo, "apply").returncode == 0
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m", "recovery")
    second = _tool(repo, "apply")
    assert second.returncode == 0, second.stderr
    assert _git(repo, "status", "--porcelain").stdout == "", "second run writes nothing"


def test_nothing_at_the_tip_is_rolled_back_by_the_repair(tmp_path: Path) -> None:
    """The case a live base is always in: work landed after the incident.

    The reconstruction carries the whole pre-incident state, so writing it back
    would undo everything since — which is the defect being repaired, performed by
    the repair. Only paths that are absent and untouched may be written.
    """
    repo, _ = _damaged(tmp_path)

    # Days pass. The log grows, a note is edited, a registry count moves on.
    _write(repo, "zettelkasten/_system/state/log_process.md",
           "# log\n- concurrent run\n- a later run\n")
    _write(repo, "zettelkasten/_system/roles/pm/state/today.md", "day three\n")
    _write(repo, "zettelkasten/2_areas/work/20260912-insight-newer.md", "written later\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "scheduler/process: later work [scheduled]")

    res = _tool(repo, "apply", "--json")
    assert res.returncode in (0, 3), res.stderr
    payload = json.loads(res.stdout)

    log = (repo / "zettelkasten/_system/state/log_process.md").read_text(encoding="utf-8")
    assert "a later run" in log, "the repair must not roll the log back"
    assert (repo / "zettelkasten/2_areas/work/20260912-insight-newer.md").exists()
    assert (repo / "zettelkasten/_system/roles/pm/state/today.md").read_text(
        encoding="utf-8") == "day three\n"

    restored = set(payload["applied"])
    assert "zettelkasten/2_areas/work/20260910-insight-kept.md" in restored, (
        "what is genuinely absent still comes back")
    assert "zettelkasten/_system/state/log_process.md" not in restored
    reported = {row["path"] for row in payload["residue"]}
    assert "zettelkasten/_system/state/log_process.md" in reported, (
        "a diverged path is reported, with what to run instead")


def test_a_file_the_incident_resurrected_is_reported_not_silently_kept(
        tmp_path: Path) -> None:
    """The mirror case: the concurrent work DELETED something, the stale tree
    brought it back.

    The correct repair is to remove it again, and the tool does not do that — a
    deletion of owner content is a different act from a restoration, and only one
    of the two is safe unattended. What it must not do is pass over the path in
    silence, which is what happens when "absent at the parent" and "git could not
    look" are the same empty answer.
    """
    repo = tmp_path / "resurrected"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n")
    _write(repo, "zettelkasten/2_areas/work/retired.md", "to be deleted\n")
    _write(repo, "zettelkasten/2_areas/work/keep.md", "keep\n")
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # A concurrent tick retires the file and writes two notes.
    (repo / "zettelkasten/2_areas/work/retired.md").unlink()
    for rel in ("zettelkasten/2_areas/work/a.md", "zettelkasten/2_areas/work/b.md",
                "zettelkasten/2_areas/work/c.md"):
        _write(repo, rel, "note\n")
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n- concurrent\n")
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m",
                                  "scheduler/process: process batch: 1 record(s) [scheduled]")

    # The stale roles tick delivers its starting snapshot: the retired file is back.
    _git(repo, "read-tree", base), _git(repo, "checkout-index", "-a", "-f")
    for rel in ("zettelkasten/2_areas/work/a.md", "zettelkasten/2_areas/work/b.md",
                "zettelkasten/2_areas/work/c.md"):
        (repo / rel).unlink()
    _write(repo, "zettelkasten/_system/roles/pm/state/today.md", "own work\n")
    _git(repo, "add", "-A"), _git(repo, "commit", "-q", "-m",
                                  "scheduler/roles: process batch: 1 record(s) [scheduled]")

    res = _tool(repo, "apply", "--json")
    assert res.returncode in (0, 3), res.stderr
    payload = json.loads(res.stdout)

    resurrected = [r for r in payload["residue"]
                   if r["path"].endswith("retired.md")]
    assert resurrected, f"the resurrected path was passed over in silence: {payload['residue']}"
    assert "resurrect" in resurrected[0]["why"]
    assert (repo / "zettelkasten/2_areas/work/retired.md").exists(), (
        "the tool must not delete owner content on its own")


def test_a_dirty_target_refuses_to_be_repaired(tmp_path: Path) -> None:
    """Uncommitted work in a file the repair would write blocks the whole run.

    Reachable exactly where the repair writes: an untracked file sitting at a path
    the incident deleted — a half-finished earlier recovery, or the owner starting
    the note again by hand. Writing there would mix their text with the restored
    version in one file, and afterwards git cannot separate the two.
    """
    repo, _ = _damaged(tmp_path)
    target = "zettelkasten/2_areas/work/20260910-insight-kept.md"
    _write(repo, target, "my own draft\n")

    res = _tool(repo, "apply")
    assert res.returncode == 2, res.stdout + res.stderr
    assert "dirty" in (res.stdout + res.stderr).lower()
    assert (repo / target).read_text(encoding="utf-8") == "my own draft\n"
    assert not (repo / "zettelkasten/_records/meetings/20260910-meeting-kept.md").exists(), (
        "a refusal writes nothing at all, not even the paths that were fine")


def test_uncommitted_work_outside_the_write_set_does_not_block(tmp_path: Path) -> None:
    """The complement: the repair does not hold itself hostage to unrelated edits.

    A file the repair only *reports* on is never written, so an edit there is in no
    danger — refusing on it would make the repair unreachable on any base the owner
    actually works in.
    """
    repo, _ = _damaged(tmp_path)
    _write(repo, "zettelkasten/2_areas/work/unrelated-draft.md", "in progress\n")

    res = _tool(repo, "apply")
    assert res.returncode in (0, 3), res.stdout + res.stderr
    assert (repo / "zettelkasten/2_areas/work/20260910-insight-kept.md").exists()
    assert (repo / "zettelkasten/2_areas/work/unrelated-draft.md").read_text(
        encoding="utf-8") == "in progress\n"


def test_a_shallow_clone_refuses_instead_of_reporting_clean(tmp_path: Path) -> None:
    repo, _ = _damaged(tmp_path)
    clone = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo}", str(clone))
    res = _tool(clone, "detect")
    assert res.returncode != 0, "a blind detector must not print a clean bill"
    assert "shallow" in (res.stdout + res.stderr).lower()


def test_an_ambiguous_rollback_is_named_for_review_not_dropped(tmp_path: Path) -> None:
    """The honest middle, and the reason it cannot be silence.

    A scheduled run that rolls back its OWN producer's work is shaped exactly like
    two ticks of the same tag racing each other — the first is deliberate, the
    second is the defect, and nothing in the history separates them. Writing would
    undo an intentional decision; dropping would report a damaged base as clean.
    So the commit is named to the owner and nothing is written.
    """
    repo = _scheduled_revert_with_a_log_line(tmp_path)

    res = _tool(repo, "detect", "--json")
    assert res.returncode == 0, res.stderr
    found = json.loads(res.stdout)
    assert len(found) == 1, found
    assert found[0]["proven"] is False
    assert found[0]["needs_review"] is True, (
        "an ambiguous signature must reach the caller, not vanish between "
        "`detect` and the migration that reads it")
    assert found[0].get("reason"), "the owner is told WHY it could not be settled"

    human = _tool(repo, "detect")
    assert "needs your review" in human.stderr
    assert "no stale-tree delivery found" not in human.stdout, (
        "a base with an unsettled commit must never print a clean bill")


def _load_tool_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("recover_reverted_ticks", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _one_blob(repo: Path, text: str) -> str:
    """Store `text` as a loose object and return its oid."""
    return subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=repo, input=text,
                          capture_output=True, text=True, check=True).stdout.strip()


def test_write_blob_refuses_to_write_through_a_symlink(tmp_path: Path) -> None:
    """Proven on a scratch repository: a plain write truncated a file OUTSIDE the
    tree, because `open(target, "wb")` follows the link at the destination."""
    tool = _load_tool_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    outside = tmp_path / "outside.txt"
    outside.write_text("do not touch me\n", encoding="utf-8")
    (repo / "note.md").symlink_to(outside)
    oid = _one_blob(repo, "restored\n")

    with pytest.raises(tool.GitFailed) as caught:
        tool.write_blob(repo, "note.md", oid)
    assert "symlink" in str(caught.value)
    assert outside.read_text(encoding="utf-8") == "do not touch me\n", (
        "the file the link pointed at must be untouched")


def test_write_blob_preserves_the_executable_bit_and_symlink_objects(
        tmp_path: Path) -> None:
    """A mode is part of what was lost, so restoring content alone is a partial
    repair: a script comes back unrunnable, and a symlink comes back as a file
    holding its own target as text."""
    tool = _load_tool_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")

    tool.write_blob(repo, "hook.sh", _one_blob(repo, "#!/bin/sh\necho hi\n"), "100755")
    assert os.access(repo / "hook.sh", os.X_OK), "an executable came back unrunnable"

    tool.write_blob(repo, "link.md", _one_blob(repo, "target.md\n"), "120000")
    assert (repo / "link.md").is_symlink(), "a symlink came back as a regular file"
    assert os.readlink(repo / "link.md") == "target.md"

    with pytest.raises(tool.GitFailed):
        tool.write_blob(repo, "weird", _one_blob(repo, "x\n"), "160000")


def test_an_unreadable_history_refuses_instead_of_reporting_clean(
        tmp_path: Path) -> None:
    """The failure that used to read as good news.

    Every git helper returned empty stdout on error, so a corrupt object store
    produced `detect() == []` — indistinguishable from a healthy base, and enough
    to let the migration retire as though it had checked.
    """
    repo, _ = _damaged(tmp_path)
    oid = subprocess.run(["git", "hash-object", "--stdin"], cwd=repo,
                         input="concurrent work\n", capture_output=True, text=True,
                         check=True).stdout.strip()
    loose = repo / ".git" / "objects" / oid[:2] / oid[2:]
    assert loose.exists(), "fixture expects loose objects (no gc has run)"
    loose.unlink()

    res = _tool(repo, "detect", "--json")
    assert res.returncode == 2, (
        f"an unreadable history must refuse, not print a clean bill:\n"
        f"rc={res.returncode} stdout={res.stdout!r} stderr={res.stderr[-400:]}")
    assert "[]" not in res.stdout


# ---------------------------------------------------------------------------
# Declared identity. A delivery that states the base its tree was built on is
# judged by that base: a path put back to its base content while the parent holds
# something newer is a revert of work the tick never read — an incident whoever
# produced that work. A base equal to the parent means the tick saw everything it
# undid. Without a declaration the older reasoning stands, unchanged.
# ---------------------------------------------------------------------------

def _identity(base: str, run: str = "run-test") -> str:
    return f"Minder-Tick-Base: {base}\nMinder-Tick-Run: {run}"


def _commit(repo: Path, subject: str, body: str | None = None) -> str:
    _git(repo, "add", "-A")
    args = ["commit", "-q", "-m", subject]
    if body:
        args += ["-m", body]
    _git(repo, *args)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _same_tag_race(tmp_path: Path, declare: bool, files: int = 3,
                   base_override: str | None = None) -> tuple[Path, str, str]:
    """Two process ticks start on the same base; the slower one delivers a stale tree.

    Returns `(repo, base, stale_sha)`. Exactly the shape the subject heuristic
    cannot settle: the interval the stale tick reverted holds only work of its own
    tag.
    """
    repo = tmp_path / "race"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n")
    _write(repo, "zettelkasten/2_areas/work/keep.md", "keep\n")
    base = _commit(repo, "base")

    for i in range(files):
        _write(repo, f"zettelkasten/2_areas/work/20260917-note-{i}.md", f"note {i}\n")
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n- fast tick\n")
    _commit(repo, "scheduler/process: process batch: 1 record(s) [scheduled]",
            _identity(base, "run-fast") if declare else None)

    _git(repo, "read-tree", base), _git(repo, "checkout-index", "-a", "-f")
    for i in range(files):
        (repo / f"zettelkasten/2_areas/work/20260917-note-{i}.md").unlink()
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n- slow tick\n")
    _write(repo, "zettelkasten/_records/meetings/20260917-slow-own.md", "own record\n")
    stale = _commit(repo, "scheduler/process: process batch: 1 record(s) [scheduled]",
                    _identity(base_override or base, "run-slow") if declare else None)
    return repo, base, stale


def _judged(repo: Path, sha: str) -> dict:
    res = _tool(repo, "detect", "--json", "--commit", sha)
    assert res.returncode == 0, res.stderr
    rows = json.loads(res.stdout)
    return rows[0] if rows else {"proven": False, "needs_review": False}


def test_an_undeclared_same_tag_race_stays_for_review(tmp_path: Path) -> None:
    """The baseline this work closes, pinned so the fallback keeps its meaning."""
    repo, _, stale = _same_tag_race(tmp_path, declare=False)
    verdict = _judged(repo, stale)
    assert verdict["proven"] is False and verdict["needs_review"] is True, verdict


def test_a_declared_same_tag_race_is_proven(tmp_path: Path) -> None:
    repo, base, stale = _same_tag_race(tmp_path, declare=True)
    verdict = _judged(repo, stale)
    assert verdict["proven"] is True, verdict
    assert verdict["needs_review"] is False
    assert verdict["base"] == base[:10], "the declared base, not a searched-for ancestor"
    assert verdict["reverted"] == 3, verdict


def test_a_declared_same_tag_race_is_repaired(tmp_path: Path) -> None:
    repo, _, _ = _same_tag_race(tmp_path, declare=True)
    res = _tool(repo, "apply", "--json")
    assert res.returncode in (0, 3), res.stderr
    for i in range(3):
        path = repo / f"zettelkasten/2_areas/work/20260917-note-{i}.md"
        assert path.read_text(encoding="utf-8") == f"note {i}\n", f"note {i} was not restored"
    assert (repo / "zettelkasten/_records/meetings/20260917-slow-own.md").exists(), (
        "the stale tick's own work stays")


def test_a_declared_rollback_of_what_the_tick_saw_is_never_an_incident(
        tmp_path: Path) -> None:
    """The deliberate rollback, declared: its base is its parent — it read the work it
    undid. Not proven, and not for review either: there is nothing left to settle."""
    repo = tmp_path / "declared-rollback"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n")
    _write(repo, "zettelkasten/2_areas/work/keep.md", "one\n")
    base = _commit(repo, "base")
    for rel, body in (("zettelkasten/2_areas/work/a.md", "a\n"),
                      ("zettelkasten/2_areas/work/b.md", "b\n"),
                      ("zettelkasten/2_areas/work/keep.md", "one changed\n")):
        _write(repo, rel, body)
    batch = _commit(repo, "scheduler/process: batch [scheduled]", _identity(base, "run-1"))

    _git(repo, "read-tree", base), _git(repo, "checkout-index", "-a", "-f")
    for rel in ("zettelkasten/2_areas/work/a.md", "zettelkasten/2_areas/work/b.md"):
        (repo / rel).unlink()
    _write(repo, "zettelkasten/_system/state/log_process.md", "# log\n- rollback run\n")
    rollback = _commit(repo, "scheduler/process: roll back the batch [scheduled]",
                       _identity(batch, "run-2"))

    verdict = _judged(repo, rollback)
    assert verdict["proven"] is False and verdict["needs_review"] is False, verdict
    res = _tool(repo, "apply", "--json")
    assert json.loads(res.stdout)["applied"] == []
    assert not (repo / "zettelkasten/2_areas/work/a.md").exists()


def test_an_invalid_declaration_falls_back_and_says_why(tmp_path: Path) -> None:
    """A declared base that is not an ancestor of the commit (a cherry-pick, a
    rewritten origin, a forged line) is not trusted in either direction."""
    repo, _, _ = _same_tag_race(tmp_path, declare=False)
    # A commit object that exists in the repository but is on no ancestry path.
    tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    dangling = _git(repo, "commit-tree", tree, "-m", "dangling").stdout.strip()

    (tmp_path / "second").mkdir()
    repo2, _, stale = _same_tag_race(tmp_path / "second", declare=True,
                                     base_override="0" * 39 + "1")
    verdict = _judged(repo2, stale)
    assert verdict["proven"] is False and verdict["needs_review"] is True, verdict
    assert "declared" in verdict.get("reason", "").lower(), verdict

    _git(repo, "commit", "-q", "--amend", "-m",
         "scheduler/process: process batch: 1 record(s) [scheduled]",
         "-m", _identity(dangling))
    verdict = _judged(repo, _git(repo, "rev-parse", "HEAD").stdout.strip())
    assert verdict["proven"] is False and verdict["needs_review"] is True, verdict
    assert "ancestor" in verdict.get("reason", "").lower(), verdict


def test_a_declared_partial_revert_below_the_signature_floor_is_found(
        tmp_path: Path) -> None:
    """The signature floor exists because an undeclared commit needs a big restored
    set to look like the defect at all. A declared commit does not: one reverted
    path is provable, so it must not be filtered out before the proof runs."""
    repo, _, stale = _same_tag_race(tmp_path, declare=True, files=1)
    res = _tool(repo, "detect", "--json")
    assert res.returncode == 0, res.stderr
    found = json.loads(res.stdout)
    assert [c["commit"] for c in found if c["proven"]] == [stale[:10]], found


def test_identity_audit_names_a_scheduled_commit_that_declares_nothing(
        tmp_path: Path) -> None:
    """A route that silently stops declaring would return its commits to the guess
    with nobody told. Before the first declaration anywhere in the history, a missing
    one is normal and not reported."""
    repo = tmp_path / "audit"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "zettelkasten/_system/state/log_process.md", "0\n")
    base = _commit(repo, "scheduler/process: before the cutover [scheduled]")
    _write(repo, "zettelkasten/_system/state/log_process.md", "1\n")
    _commit(repo, "scheduler/process: declared [scheduled]", _identity(base))
    _write(repo, "zettelkasten/_system/state/log_process.md", "2\n")
    silent = _commit(repo, "scheduler/lint: declares nothing [scheduled]")
    _write(repo, "zettelkasten/_system/state/log_process.md", "3\n")
    _commit(repo, "garmin: metric day")
    _write(repo, "zettelkasten/_system/state/log_process.md", "4\n")
    broken = _commit(repo, "scheduler/roles: broken [scheduled]",
                     "Minder-Tick-Base: not-a-sha")

    res = _tool(repo, "identity", "--json")
    assert res.returncode == 0, res.stderr
    rows = json.loads(res.stdout)
    assert sorted(r["commit"] for r in rows) == sorted([silent[:10], broken[:10]]), rows
    assert all(r.get("reason") for r in rows)


def test_identity_audit_is_silent_before_any_declaration(tmp_path: Path) -> None:
    repo, _, _ = _same_tag_race(tmp_path, declare=False)
    res = _tool(repo, "identity", "--json")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == []


def test_a_declaration_in_the_subject_paragraph_is_not_read(tmp_path: Path) -> None:
    """Only lines after the subject paragraph are a declaration. A subject built from
    free text that smuggles a base in is judged as undeclared."""
    repo, base, _ = _same_tag_race(tmp_path, declare=False)
    _git(repo, "commit", "-q", "--amend", "-m",
         f"scheduler/process: batch [scheduled]\nMinder-Tick-Base: {base}")
    verdict = _judged(repo, _git(repo, "rev-parse", "HEAD").stdout.strip())
    assert verdict.get("declared") is not True, verdict
    assert verdict["needs_review"] is True, verdict
