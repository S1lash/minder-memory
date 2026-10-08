"""A scheduled tick delivers its work — or leaves nothing half-done behind.

Covers the reliability layer around `finalize-tick.sh`:

* the closing record (`tick_state.py`) and the closing guard
  (`.claude/hooks/tick_guard.py`) that will not let a tick's session end
  before its work is delivered, and closes it itself when the model will not;
* conflict settling in three layers — mechanical for additions on both sides,
  the tick's own resolution for real overlaps, main's version as last resort;
* `ship-failure-note.sh --note-only` for a tick abandoned mid-skill;
* process's two deliveries, before and after maintain.

Every scenario runs the real scripts in a throwaway repository with a bare
`origin`, the same shape `test_scheduler_finalize.py` uses.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_scheduler_finalize as tsf  # noqa: E402

REPO_ROOT = tsf.REPO_ROOT
GUARD = REPO_ROOT / ".claude" / "hooks" / "tick_guard.py"
RESOLVER = REPO_ROOT / "scripts" / "scheduler" / "_resolve_conflicts.py"

ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    work, origin = tsf._seed_repo(tmp_path)
    hooks = work / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    shutil.copy(GUARD, hooks / "tick_guard.py")
    return work, origin


def _show(origin: Path, rel: str) -> str:
    res = subprocess.run(["git", "show", f"main:{rel}"], cwd=origin,
                         capture_output=True, text=True, encoding="utf-8")
    return res.stdout if res.returncode == 0 else ""


def _state(work: Path) -> dict:
    path = work / ".scheduler-state" / "tick.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _open_tick(work: Path, tag: str = "scheduler/lint", session: str = "S1") -> None:
    res = tsf._run_script(work, "pin-main.sh", tag)
    assert res.returncode == 0, res.stderr
    _guard(work, {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                  "session_id": session,
                  "tool_input": {"command": f"bash scripts/scheduler/pin-main.sh {tag}"}})


def _guard(work: Path, payload: dict) -> str:
    payload.setdefault("cwd", str(work))
    res = subprocess.run([sys.executable, str(work / ".claude/hooks/tick_guard.py")],
                         input=json.dumps(payload), cwd=work, capture_output=True,
                         text=True, encoding="utf-8",
                         env={**os.environ, **ENV, "CLAUDE_PROJECT_DIR": str(work)})
    assert res.returncode == 0, res.stderr
    return res.stdout


def _stop(work: Path, session: str = "S1", transcript: Path | None = None) -> dict | None:
    payload = {"hook_event_name": "Stop", "session_id": session, "stop_hook_active": False}
    if transcript is not None:
        payload["transcript_path"] = str(transcript)
    out = _guard(work, payload)
    return json.loads(out) if out.strip() else None


def _transcript(path: Path, *entries: dict) -> Path:
    with open(path, "a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    return path


_LAUNCHES = {
    "agent": lambda task: {"isAsync": True, "status": "async_launched", "agentId": task},
    "command": lambda task: {"backgroundTaskId": task, "stdout": ""},
    "monitor": lambda task: {"taskId": task, "timeoutMs": 300000, "persistent": False},
    "resume": lambda task: {"success": True, "resumedAgentId": task},
}


def _launch(task: str, kind: str = "agent") -> dict:
    result = _LAUNCHES[kind](task)
    return {"type": "user", "toolUseResult": result,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_x",
                 "content": [{"type": "text", "text": "launched"}]}]}}


def _notice(task: str, status: str = "completed", shape: str = "queued",
            call: str = "toolu_1") -> dict:
    # A notice names the call that started its run: a resumed agent's second
    # notice differs from its first, while one notice delivered twice does not.
    text = (f"<task-notification>\n<task-id>{task}</task-id>\n"
            f"<tool-use-id>{call}</tool-use-id>\n"
            f"<status>{status}</status>\n</task-notification>")
    if shape == "attached":
        return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": text}}
    if shape == "message":
        return {"type": "user", "message": {"role": "user", "content": text}}
    return {"type": "queue-operation", "operation": "enqueue", "content": text}


def _stopped(task: str) -> dict:
    return {"type": "user", "toolUseResult": {
        "message": f"Successfully stopped task: {task}", "task_id": task,
        "task_type": "local_bash", "command": "sleep 900"},
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_s", "content": "stopped"}]}}


SHARED = "zettelkasten/_records/shared.md"
SPACED = "zettelkasten/_records/meeting with ivan petrov.md"


def _overlap(tmp_path: Path, work: Path, origin: Path, rel: str = SHARED) -> None:
    """Both this tick and a run that delivered first rewrite the same line."""
    (work / rel).write_text("status: draft\n", encoding="utf-8")
    tsf._git(work, "add", "-A")
    tsf._git(work, "commit", "-q", "-m", "seed")
    tsf._git(work, "push", "-q", "origin", "main")
    _open_tick(work)
    (work / rel).write_text("status: tick\n", encoding="utf-8")
    (work / "zettelkasten/_system/state/log_lint.md").write_text("ran\n", encoding="utf-8")
    tsf._clone_and_push(tmp_path, origin, rel, "status: main\n",
                        "scheduler/process: 1 record(s) updated [scheduled]")


# --- conflict settling ------------------------------------------------------


def test_a_real_overlap_stops_for_the_tick_and_its_resolution_is_delivered(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _overlap(tmp_path, work, origin)

    first = tsf._run_script(work, "close-tick.sh", "scheduler/lint")
    assert first.returncode == 3, first.stdout + first.stderr
    assert _state(work)["state"] == "conflict"
    assert SHARED in (work / ".scheduler-state/conflict").read_text(encoding="utf-8")
    assert _show(origin, SHARED) == "status: main\n", "nothing pushed while open"
    assert "<<<<<<< " in (work / SHARED).read_text(encoding="utf-8")

    # The tick resolves it, keeping both meanings (Step 5c), and closes again.
    (work / SHARED).write_text("status: main\nnote: tick\n", encoding="utf-8")
    second = tsf._run_script(work, "close-tick.sh", "scheduler/lint")
    assert second.returncode == 0, second.stdout + second.stderr
    assert _show(origin, SHARED) == "status: main\nnote: tick\n"
    assert _show(origin, "zettelkasten/_system/state/log_lint.md") == "ran\n"
    assert _state(work)["state"] == "closed"
    subject = tsf._git(origin, "log", "-1", "--format=%s", "main").stdout
    assert "[scheduled]" in subject and "Merge" not in subject, "one squash-shaped commit"


def test_the_last_resort_keeps_mains_version_and_delivers_the_rest(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _overlap(tmp_path, work, origin)
    assert tsf._run_script(work, "close-tick.sh", "scheduler/lint").returncode == 3

    res = tsf._run_script(work, "close-tick.sh", "scheduler/lint", "--resolve-by-main")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _show(origin, SHARED) == "status: main\n"
    assert _show(origin, "zettelkasten/_system/state/log_lint.md") == "ran\n"
    assert SHARED in _show(origin, "zettelkasten/_system/state/CLARIFICATIONS.md")


def test_a_path_with_spaces_survives_both_resolution_paths(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _overlap(tmp_path, work, origin, rel=SPACED)
    assert tsf._run_script(work, "close-tick.sh", "scheduler/lint").returncode == 3
    assert SPACED in (work / ".scheduler-state/conflict").read_text(encoding="utf-8")
    res = tsf._run_script(work, "close-tick.sh", "scheduler/lint", "--resolve-by-main")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _show(origin, SPACED) == "status: main\n"
    assert _show(origin, "zettelkasten/_system/state/log_lint.md") == "ran\n"


# --- the closing guard ------------------------------------------------------


def test_no_record_means_the_guard_stays_silent(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    assert _stop(work) is None


def test_another_session_is_never_held(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work, session="TICK")
    assert _stop(work, session="OWNER") is None


def test_binding_happens_only_after_pin_main(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    tsf._run_script(work, "pin-main.sh", "scheduler/lint")
    _guard(work, {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                  "session_id": "S1", "tool_input": {"command": "ls"}})
    assert _state(work)["session_id"] is None
    assert _stop(work) is None, "an unbound record holds nobody"


def test_a_stale_record_is_ignored(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    record = _state(work)
    record["opened_at"] = time.time() - 9 * 3600
    (work / ".scheduler-state/tick.json").write_text(json.dumps(record), encoding="utf-8")
    assert _stop(work) is None


def test_the_guard_nudges_twice_then_delivers_the_tick_itself(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _open_tick(work)
    (work / "zettelkasten/_system/state/log_lint.md").write_text("ran\n", encoding="utf-8")

    for _ in range(2):
        answer = _stop(work)
        assert answer and answer["decision"] == "block"
        assert "close-tick.sh scheduler/lint" in answer["reason"]
        assert _show(origin, "zettelkasten/_system/state/log_lint.md") == ""

    assert _stop(work) is None, "the third time it lets go — after closing the tick"
    assert _show(origin, "zettelkasten/_system/state/log_lint.md") == "ran\n"
    assert _state(work)["state"] == "closed"


def test_a_run_waiting_on_its_subagent_is_not_held_or_closed(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _open_tick(work, tag="scheduler/process")
    lock = work / "zettelkasten/_sources/.processing.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("running\n", encoding="utf-8")
    transcript = _transcript(tmp_path / "session.jsonl", _launch("agent-1"))

    for _ in range(4):
        assert _stop(work, transcript=transcript) is None, "waiting, not walking away"
    record = _state(work)
    assert record["state"] == "open" and record["nudges"] == 0
    assert "failure" not in tsf._git(origin, "log", "-1", "--format=%s", "main").stdout

    # The subagent reports back; the run is woken and ends without closing.
    _transcript(transcript, _notice("agent-1"))
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_a_background_command_holds_the_guard_back_too(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    transcript = _transcript(tmp_path / "session.jsonl", _launch("bash-1", kind="command"))
    assert _stop(work, transcript=transcript) is None
    _transcript(transcript, _notice("bash-1", status="failed"))
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_a_monitor_holds_the_guard_back_until_it_ends(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    transcript = _transcript(tmp_path / "session.jsonl", _launch("mon-1", kind="monitor"))
    assert _stop(work, transcript=transcript) is None
    _transcript(transcript, _notice("mon-1"))
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_a_resumed_agent_is_running_again(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    transcript = _transcript(tmp_path / "session.jsonl", _launch("agent-1"),
                             _notice("agent-1"), _launch("agent-1", kind="resume"))
    assert _stop(work, transcript=transcript) is None, "its first notice is history"
    _transcript(transcript, _notice("agent-1", call="toolu_2"))
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_a_task_list_entry_is_not_background_work(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    todo = {"type": "user", "toolUseResult": {"taskId": "7", "subject": "close the tick"},
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_z", "content": "created"}]}}
    transcript = _transcript(tmp_path / "session.jsonl", todo)
    assert _stop(work, transcript=transcript)["decision"] == "block"


@pytest.mark.parametrize("shape", ["queued", "attached", "message"])
def test_every_delivered_shape_of_a_notice_ends_the_wait(tmp_path: Path, shape: str) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    transcript = _transcript(tmp_path / "session.jsonl", _launch("agent-1"),
                             _notice("agent-1", shape=shape))
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_work_the_run_stopped_itself_is_not_waited_for(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    transcript = _transcript(tmp_path / "session.jsonl",
                             _launch("bash-1", kind="command"), _stopped("bash-1"))
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_a_persistent_monitor_is_not_waited_for(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    persistent = _launch("mon-1", kind="monitor")
    persistent["toolUseResult"]["persistent"] = True
    transcript = _transcript(tmp_path / "session.jsonl", persistent)
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_a_notice_redelivered_after_a_resume_does_not_end_it(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    first = _notice("agent-1")
    attached = _notice("agent-1", shape="attached")
    transcript = _transcript(tmp_path / "session.jsonl", _launch("agent-1"), first,
                             _launch("agent-1", kind="resume"), attached)
    assert _stop(work, transcript=transcript) is None, "the same notice, seen again"


def test_a_wait_is_written_into_the_record(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    transcript = _transcript(tmp_path / "session.jsonl", _launch("agent-1"))
    assert _stop(work, transcript=transcript) is None
    assert _state(work)["waiting_on"] == ["agent-1"]


def test_an_unreadable_transcript_falls_back_to_the_guard(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    assert _stop(work, transcript=tmp_path / "missing.jsonl")["decision"] == "block"


def test_a_notice_quoted_in_a_tool_result_does_not_count(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    quoted = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_y", "content":
         "<task-notification><task-id>agent-1</task-id><status>completed</status>"
         "</task-notification>"}]}}
    transcript = _transcript(tmp_path / "session.jsonl", _launch("agent-1"), quoted)
    assert _stop(work, transcript=transcript) is None


def test_background_work_that_never_reports_stops_holding_back(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    record = _state(work)
    record["opened_at"] = time.time() - 4 * 3600
    (work / ".scheduler-state/tick.json").write_text(json.dumps(record), encoding="utf-8")
    transcript = _transcript(tmp_path / "session.jsonl", _launch("agent-1"))
    assert _stop(work, transcript=transcript)["decision"] == "block"


def test_a_closed_tick_lets_the_session_end(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work)
    (work / "zettelkasten/_system/state/log_lint.md").write_text("ran\n", encoding="utf-8")
    assert tsf._run_script(work, "close-tick.sh", "scheduler/lint").returncode == 0
    assert _stop(work) is None


def test_an_interrupted_skill_ships_only_the_note(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _open_tick(work, tag="scheduler/process")
    lock = work / "zettelkasten/_sources/.processing.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("running\n", encoding="utf-8")
    (work / "zettelkasten/_records/half-done.md").write_text("half\n", encoding="utf-8")

    assert _stop(work)["decision"] == "block"
    assert _stop(work)["decision"] == "block"
    assert _stop(work) is None

    assert _show(origin, "zettelkasten/_records/half-done.md") == "", \
        "half-done work never lands — the next tick redoes it whole"
    assert "middle of its work" in _show(origin, "zettelkasten/_system/state/CLARIFICATIONS.md")
    assert _state(work)["state"] == "closed"


def test_the_process_reminder_names_maintain(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work, tag="scheduler/process")
    reason = _stop(work)["reason"]
    assert "maintain" in reason and "process-scheduled.md" in reason


# --- two deliveries for process ----------------------------------------------


def test_process_delivers_before_and_after_maintain(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    (work / ".scheduler-state").mkdir(exist_ok=True)
    _, gh_env = tsf._install_fake_gh(tmp_path, origin)
    tsf._git(work, "checkout", "-q", "-b", "claude/sandbox-XYZ")
    res = tsf._run_script(work, "pin-main.sh", "scheduler/process", env=gh_env)
    assert res.returncode == 0, res.stderr

    (work / "zettelkasten/_records/r1.md").write_text("record\n", encoding="utf-8")
    first = tsf._run_script(work, "close-tick.sh", "scheduler/process", "--checkpoint",
                            env=gh_env)
    assert first.returncode == 0, first.stdout + first.stderr
    assert _show(origin, "zettelkasten/_records/r1.md") == "record\n"
    assert _state(work)["state"] == "open", "a checkpoint keeps the tick open"

    (work / "zettelkasten/_system/state/log_maintenance.md").write_text("maintained\n",
                                                                        encoding="utf-8")
    second = tsf._run_script(work, "close-tick.sh", "scheduler/process", env=gh_env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert _show(origin, "zettelkasten/_system/state/log_maintenance.md") == "maintained\n"
    assert _show(origin, "zettelkasten/_records/r1.md") == "record\n"
    assert _state(work)["state"] == "closed"


# --- the mechanical resolver -------------------------------------------------


def _resolver():
    sys.path.insert(0, str(RESOLVER.parent))
    import _resolve_conflicts  # noqa: PLC0415
    return _resolve_conflicts


def test_additions_on_both_sides_keep_both_earlier_delivery_first() -> None:
    text = ("head\n<<<<<<< ours\ntick entry\n||||||| base\n=======\nmain entry\n"
            ">>>>>>> theirs\ntail\n")
    new, done = _resolver().resolve_text(text)
    assert done and new == "head\nmain entry\ntick entry\ntail\n"


def test_identical_additions_are_kept_once() -> None:
    text = "<<<<<<< ours\nsame\n||||||| base\n=======\nsame\n>>>>>>> theirs\n"
    new, done = _resolver().resolve_text(text)
    assert done and new == "same\n"


def test_a_changed_line_is_left_for_the_tick() -> None:
    text = ("<<<<<<< ours\nstatus: tick\n||||||| base\nstatus: draft\n=======\n"
            "status: main\n>>>>>>> theirs\n")
    new, done = _resolver().resolve_text(text)
    assert not done and new == text


def test_two_additions_of_the_same_field_are_left_for_the_tick() -> None:
    # Both runs added `last_applied:` where the note had none. Keeping both
    # lines would write the key twice — frontmatter that no longer parses.
    text = ("---\n<<<<<<< ours\nlast_applied: 2026-10-02\n||||||| base\n=======\n"
            "last_applied: 2026-10-01\n>>>>>>> theirs\n---\n")
    new, done = _resolver().resolve_text(text)
    assert not done and new == text


def test_different_fields_added_on_both_sides_are_both_kept() -> None:
    text = ("<<<<<<< ours\ntags: [a]\n||||||| base\n=======\nstatus: open\n"
            ">>>>>>> theirs\n")
    new, done = _resolver().resolve_text(text)
    assert done and new == "status: open\ntags: [a]\n"


def test_a_checkpoint_is_marked_in_its_subject(tmp_path: Path) -> None:
    # `/minder:mem:lint` A.13 skips commits marked this way: a checkpoint is
    # half a tick and carries no telemetry line by design.
    work, origin = _seed(tmp_path)
    _open_tick(work, tag="scheduler/process")
    (work / "zettelkasten/_records/r1.md").write_text("record\n", encoding="utf-8")
    res = tsf._run_script(work, "close-tick.sh", "scheduler/process", "--checkpoint")
    assert res.returncode == 0, res.stdout + res.stderr
    subject = tsf._git(origin, "log", "-1", "--format=%s", "main").stdout
    assert ": checkpoint — " in subject and subject.strip().endswith("[scheduled]")
    assert "tick-telemetry" not in tsf._git(origin, "show", "--name-only", "--format=",
                                            "main").stdout


def test_a_failed_checkpoint_leaves_the_tick_open_not_failed(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work, tag="scheduler/process")
    (work / "zettelkasten/_records/r1.md").write_text("record\n", encoding="utf-8")
    tsf._git(work, "remote", "set-url", "origin", str(tmp_path / "nowhere.git"))
    res = tsf._run_script(work, "close-tick.sh", "scheduler/process", "--checkpoint")
    assert res.returncode != 0
    assert _state(work)["state"] == "open"
    assert "close-tick.sh scheduler/process" in _stop(work)["reason"]


def test_a_push_rejected_because_main_moved_integrates_again(tmp_path: Path) -> None:
    # Main moves in the instant between integration and push: the push is
    # rejected, and the run integrates once more instead of giving up.
    work, origin = _seed(tmp_path)
    other = tsf._second_clone(tmp_path, origin, "racer")
    marker = tmp_path / "raced"
    hook = work / ".git" / "hooks" / "pre-push"
    hook.write_text(
        "#!/usr/bin/env bash\n"
        f"[ -f '{marker}' ] && exit 0\n"
        f"touch '{marker}'\n"
        f"cd '{other}' && echo racer > zettelkasten/_records/racer.md 2>/dev/null "
        f"|| {{ mkdir -p zettelkasten/_records && echo racer > zettelkasten/_records/racer.md; }}\n"
        "git add -A && git commit -q -m 'racer [scheduled]' && git push -q origin main\n",
        encoding="utf-8")
    hook.chmod(0o755)
    (work / "zettelkasten/_system/state/log_lint.md").write_text("ran\n", encoding="utf-8")

    res = tsf._run_script(work, "finalize-tick.sh", "scheduler/lint")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "integrating again" in res.stdout
    assert _show(origin, "zettelkasten/_records/racer.md") == "racer\n"
    assert _show(origin, "zettelkasten/_system/state/log_lint.md") == "ran\n"


# --- regressions found by independent review --------------------------------


def _routines_env(tmp_path: Path, origin: Path, fake: str | None = None) -> dict:
    _, env = tsf._install_fake_gh(tmp_path, origin)
    if fake:
        (Path(env["PATH"].split(os.pathsep)[0]) / "gh").write_text(fake, encoding="utf-8")
    return env


def _squashing_gh(retain_branch: bool) -> str:
    """A fake gh that squashes like GitHub does (a new commit, not the branch
    tip), and optionally refuses to delete the merged branch."""
    s = tsf.FAKE_GH_SCRIPT.replace(
        'GIT_DIR="$bare" git update-ref refs/heads/main "refs/heads/$branch" || exit 1',
        'tree=$(GIT_DIR="$bare" git rev-parse "refs/heads/$branch^{tree}"); '
        'sq=$(GIT_DIR="$bare" GIT_AUTHOR_NAME=gh GIT_AUTHOR_EMAIL=g@h GIT_COMMITTER_NAME=gh '
        'GIT_COMMITTER_EMAIL=g@h git commit-tree "$tree" -p refs/heads/main -m squash) || exit 1; '
        'GIT_DIR="$bare" git update-ref refs/heads/main "$sq" || exit 1')
    if retain_branch:
        s = s.replace('GIT_DIR="$bare" git update-ref -d "refs/heads/$branch" 2>/dev/null || true\n    exit 0 ;;',
                      'echo "HTTP 422 protected" >&2; exit 1 ;;')
    return s


def test_a_resolved_conflict_delivers_in_routines_mode(tmp_path: Path) -> None:
    # The resumed call never built the commit, so it had no subject to title
    # the PR with — every cloud conflict lost its run.
    work, origin = _seed(tmp_path)
    (work / SHARED).write_text("status: draft\n", encoding="utf-8")
    tsf._git(work, "add", "-A")
    tsf._git(work, "commit", "-q", "-m", "seed")
    tsf._git(work, "push", "-q", "origin", "main")
    env = _routines_env(tmp_path, origin)
    tsf._git(work, "checkout", "-q", "-b", "claude/sandbox-XYZ")
    assert tsf._run_script(work, "pin-main.sh", "scheduler/lint", env=env).returncode == 0
    (work / SHARED).write_text("status: tick\n", encoding="utf-8")
    (work / "zettelkasten/_system/state/log_lint.md").write_text("ran\n", encoding="utf-8")
    tsf._clone_and_push(tmp_path, origin, SHARED, "status: main\n", "x [scheduled]")
    assert tsf._run_script(work, "close-tick.sh", "scheduler/lint", env=env).returncode == 3
    (work / SHARED).write_text("status: main\nnote: tick\n", encoding="utf-8")
    res = tsf._run_script(work, "close-tick.sh", "scheduler/lint", env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "finalize-tick: committed" in res.stdout, "Step 5b keys on this line"
    assert _show(origin, SHARED) == "status: main\nnote: tick\n"
    assert _show(origin, "zettelkasten/_system/state/log_lint.md") == "ran\n"


@pytest.mark.parametrize("retain_branch", [False, True])
def test_the_second_process_delivery_survives_a_kept_sandbox_branch(
        tmp_path: Path, retain_branch: bool) -> None:
    # After the checkpoint is squashed onto main, the final commit is not a
    # descendant of what is still on the sandbox branch.
    work, origin = _seed(tmp_path)
    env = _routines_env(tmp_path, origin, _squashing_gh(retain_branch))
    tsf._git(work, "checkout", "-q", "-b", "claude/sandbox-XYZ")
    assert tsf._run_script(work, "pin-main.sh", "scheduler/process", env=env).returncode == 0
    (work / "zettelkasten/_records/r1.md").write_text("record\n", encoding="utf-8")
    first = tsf._run_script(work, "close-tick.sh", "scheduler/process", "--checkpoint", env=env)
    assert first.returncode == 0, first.stdout + first.stderr
    (work / "zettelkasten/_system/state/log_maintenance.md").write_text("m\n", encoding="utf-8")
    second = tsf._run_script(work, "close-tick.sh", "scheduler/process", env=env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert _show(origin, "zettelkasten/_system/state/log_maintenance.md") == "m\n"
    assert _show(origin, "zettelkasten/_records/r1.md") == "record\n"


def _markerless_conflict(tmp_path: Path, kind: str) -> tuple[Path, Path, str]:
    work, origin = _seed(tmp_path)
    rel = "zettelkasten/_records/img.bin"
    (work / rel).write_bytes(b"\x00\x01base\xff")
    tsf._git(work, "add", "-A")
    tsf._git(work, "commit", "-q", "-m", "seed")
    tsf._git(work, "push", "-q", "origin", "main")
    _open_tick(work)
    (work / rel).write_bytes(b"\x00\x01tick\xff")
    (work / "zettelkasten/_system/state/log_lint.md").write_text("ran\n", encoding="utf-8")
    other = tsf._second_clone(tmp_path, origin, "o2")
    if kind == "binary":
        (other / rel).write_bytes(b"\x00\x01main\xff")
    else:
        (other / rel).unlink()
    tsf._git(other, "add", "-A")
    tsf._git(other, "commit", "-q", "-m", "main side [scheduled]")
    tsf._git(other, "push", "-q", "origin", "main")
    assert tsf._run_script(work, "close-tick.sh", "scheduler/lint").returncode == 3
    return work, origin, rel


def test_an_untouched_binary_conflict_is_not_read_as_resolved(tmp_path: Path) -> None:
    work, origin, rel = _markerless_conflict(tmp_path, "binary")
    again = tsf._run_script(work, "close-tick.sh", "scheduler/lint")
    assert again.returncode == 3, "a file left as it was is still open"
    res = tsf._run_script(work, "close-tick.sh", "scheduler/lint", "--resolve-by-main")
    assert res.returncode == 0, res.stdout + res.stderr
    blob = subprocess.run(["git", "cat-file", "-p", f"main:{rel}"], cwd=origin,
                          capture_output=True).stdout
    assert blob == b"\x00\x01main\xff"
    assert rel in _show(origin, "zettelkasten/_system/state/CLARIFICATIONS.md")


def test_a_file_main_deleted_is_not_resurrected(tmp_path: Path) -> None:
    work, origin, rel = _markerless_conflict(tmp_path, "delete")
    res = tsf._run_script(work, "close-tick.sh", "scheduler/lint", "--resolve-by-main")
    assert res.returncode == 0, res.stdout + res.stderr
    gone = subprocess.run(["git", "cat-file", "-e", f"main:{rel}"], cwd=origin)
    assert gone.returncode != 0, "main deleted it; the tick must not bring it back"


def test_a_tick_whose_only_change_was_dropped_still_names_it(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    (work / SHARED).write_text("status: draft\n", encoding="utf-8")
    tsf._git(work, "add", "-A")
    tsf._git(work, "commit", "-q", "-m", "seed")
    tsf._git(work, "push", "-q", "origin", "main")
    _open_tick(work)
    (work / SHARED).write_text("status: tick\n", encoding="utf-8")
    tsf._clone_and_push(tmp_path, origin, SHARED, "status: main\n", "x [scheduled]")
    res = tsf._run_script(work, "finalize-tick.sh", "--resolve-by-main", "scheduler/lint")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _show(origin, SHARED) == "status: main\n"
    assert SHARED in _show(origin, "zettelkasten/_system/state/CLARIFICATIONS.md")


def test_failure_handling_on_a_conflict_keeps_the_tick_closed(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _overlap(tmp_path, work, origin)
    assert tsf._run_script(work, "close-tick.sh", "scheduler/lint").returncode == 3
    tsf._run_script(work, "ship-failure-note.sh", "finalize-tick failed", "lint-nightly")
    assert _state(work)["state"] == "closed"
    assert _stop(work) is None, "a tick that ended through failure handling is not reopened"
    assert "finalize-tick failed" in _show(origin, "zettelkasten/_system/state/CLARIFICATIONS.md")


def test_a_checkpoint_conflict_resumes_as_a_checkpoint(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    (work / SHARED).write_text("status: draft\n", encoding="utf-8")
    tsf._git(work, "add", "-A")
    tsf._git(work, "commit", "-q", "-m", "seed")
    tsf._git(work, "push", "-q", "origin", "main")
    _open_tick(work, "scheduler/process")
    (work / SHARED).write_text("status: tick\n", encoding="utf-8")
    tsf._clone_and_push(tmp_path, origin, SHARED, "status: main\n", "scheduler/lint: x [scheduled]")
    assert tsf._run_script(work, "close-tick.sh", "scheduler/process", "--checkpoint").returncode == 3
    assert "--checkpoint" in _stop(work)["reason"]
    (work / SHARED).write_text("status: main\nnote: tick\n", encoding="utf-8")
    # Even the plain close a model might run instead completes the checkpoint
    # only — maintain and the final close are still owed.
    res = tsf._run_script(work, "close-tick.sh", "scheduler/process")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _state(work)["state"] == "open"
    assert _show(origin, "zettelkasten/_system/state/tick-telemetry.jsonl") == ""
    assert _stop(work)["decision"] == "block"


def test_a_second_pipeline_in_the_same_clone_leaves_the_first_ones_record(
        tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    _open_tick(work, "scheduler/process", "PROC")
    _open_tick(work, "scheduler/lint", "LINT")
    record = _state(work)
    assert record["tag"] == "scheduler/process" and record["session_id"] == "PROC"
    assert _stop(work, "LINT") is None
    assert _stop(work, "PROC")["decision"] == "block", "the running tick keeps its guard"


def test_mentioning_pin_main_does_not_bind_a_session(tmp_path: Path) -> None:
    work, _ = _seed(tmp_path)
    tsf._run_script(work, "pin-main.sh", "scheduler/lint")
    _guard(work, {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "OWNER",
                  "tool_input": {"command": "grep -n fetch scripts/scheduler/pin-main.sh"}})
    assert _state(work)["session_id"] is None
    assert _stop(work, "OWNER") is None


def test_abandoned_work_is_set_aside_not_left_for_the_next_tick(tmp_path: Path) -> None:
    work, origin = _seed(tmp_path)
    _open_tick(work, tag="scheduler/process")
    lock = work / "zettelkasten/_sources/.processing.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("running\n", encoding="utf-8")
    (work / "zettelkasten/_records/half-done.md").write_text("half\n", encoding="utf-8")
    for _ in range(3):
        _stop(work)
    assert not (work / "zettelkasten/_records/half-done.md").exists()
    assert "minder: unfinished" in tsf._git(work, "stash", "list").stdout
    assert "git stash" in _show(origin, "zettelkasten/_system/state/CLARIFICATIONS.md")
    lock.unlink()
    _open_tick(work, tag="scheduler/lint")
    (work / "zettelkasten/_system/state/log_lint.md").write_text("ran\n", encoding="utf-8")
    assert tsf._run_script(work, "close-tick.sh", "scheduler/lint").returncode == 0
    assert _show(origin, "zettelkasten/_records/half-done.md") == ""
