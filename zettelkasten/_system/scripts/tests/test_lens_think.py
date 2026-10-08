"""lens_think.py — the clean Stage 1 thinker call for agent lenses.

The real `claude` CLI is never run here: a stand-in executable on PATH records
what it was asked and answers as the CLI does (`--output-format json`).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lens_think  # noqa: E402

FRAME = """# Agent-Lens Frame

intro

## Stage 1 — Thinker prompt (base-input variant)

text around

```
BASE FRAME BODY
line two
```

## Stage 1 — Thinker prompt (lens-outputs-input variant)

```
META FRAME BODY
```

## Stage 1 — Thinker prompt (multi-source-input variant)

```
MULTI FRAME BODY
```

## Stage 2 — Structurer prompt

```
STRUCTURER
```
"""

# The stand-in CLI: records argv, stdin and the system prompt it was handed,
# then answers according to FAKE_CLAUDE_MODE.
FAKE = r'''#!/usr/bin/env python3
import hashlib, json, os, subprocess, sys, time
args = sys.argv[1:]
log = os.environ["FAKE_CLAUDE_LOG"]
system = ""
system_file = ""
if "--system-prompt-file" in args:
    system_file = args[args.index("--system-prompt-file") + 1]
    with open(system_file, encoding="utf-8") as h:
        system = h.read()
message = sys.stdin.read()
key = hashlib.sha1(message.encode("utf-8")).hexdigest()
with open(log, "a", encoding="utf-8") as h:
    h.write(json.dumps({"args": args, "system": system, "system_file": system_file,
                        "message": message, "key": key, "cwd": os.getcwd()}) + "\n")
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
mine = sum(1 for line in open(log, encoding="utf-8") if json.loads(line)["key"] == key)
if mode == "fail-then-ok" and mine == 1:
    print(json.dumps({"is_error": True, "result": "overloaded"}))
elif mode == "always-fail":
    print(json.dumps({"is_error": True, "result": "api safeguard"}))
elif mode == "garbage":
    print("not json at all")
    sys.exit(1)
elif mode == "empty":
    print(json.dumps({"is_error": False, "result": "  "}))
elif mode == "light-model":
    print(json.dumps({"is_error": False, "result": "THOUGHTS",
                      "modelUsage": {"claude-light-test": {"outputTokens": 900},
                                     "claude-opus-test": {"outputTokens": 10}}}))
elif mode == "hang":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(log + ".child", "w") as h:
        h.write(str(child.pid))
    time.sleep(60)
else:
    print(json.dumps({"is_error": False, "result": "THOUGHTS about the base",
                      "num_turns": 3, "usage": {"output_tokens": 42},
                      "modelUsage": {"claude-opus-test": {"outputTokens": 42},
                                     "claude-light-test": {"outputTokens": 5}}}))
'''


def _base(tmp_path: Path) -> Path:
    base = tmp_path / "zettelkasten"
    lenses = base / "_system" / "registries" / "lenses"
    lenses.mkdir(parents=True)
    (lenses / "_frame.md").write_text(FRAME, encoding="utf-8")
    for lens_id, input_type, stance in (("alpha", "records", "fresh-eyes"),
                                        ("beta", "lens-outputs", "longitudinal"),
                                        ("gamma", "multi-source", "lens-decides")):
        folder = lenses / lens_id
        folder.mkdir()
        (folder / "prompt.md").write_text(
            f"---\nid: {lens_id}\ninput_type: {input_type}\nself_history: {stance}\n---\n\n"
            f"PROMPT OF {lens_id}\n", encoding="utf-8")
    (lenses / "alpha" / "what-counts.md").write_text("COUNTS\n", encoding="utf-8")
    return base


@pytest.fixture()
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "claude"
    script.write_text(FAKE, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    if os.name == "nt":  # pragma: no cover — a .py is not executable by name there
        pytest.skip("stand-in CLI relies on a POSIX shebang")
    monkeypatch.setattr(lens_think, "BACKOFF_S", (0, 0))
    return log


def _calls(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _run(base: Path, out: Path, *lenses: str) -> list[dict]:
    assert lens_think.main(["run", "--base", str(base), "--out", str(out), *lenses]) == 0
    return json.loads((out / "results.json").read_text(encoding="utf-8"))


def test_each_input_type_gets_exactly_its_frame_body() -> None:
    assert lens_think.frame_body(FRAME, "records") == "BASE FRAME BODY\nline two\n"
    assert lens_think.frame_body(FRAME, "lens-outputs") == "META FRAME BODY\n"
    assert lens_think.frame_body(FRAME, "multi-source") == "MULTI FRAME BODY\n"
    with pytest.raises(lens_think.LensError):
        lens_think.frame_body(FRAME, "nonsense")


def test_the_real_frame_has_a_body_for_every_input_type() -> None:
    frame = Path(__file__).resolve().parents[2] / "registries" / "lenses" / "_frame.md"
    text = frame.read_text(encoding="utf-8")
    for input_type in lens_think.VARIANTS:
        body = lens_think.frame_body(text, input_type)
        assert len(body) > 200 and "```" not in body
        assert "agent-lens-raw/" in body, "a thinker is told not to read unvalidated drafts"


def test_the_message_is_the_lens_folder_and_its_hint(tmp_path: Path) -> None:
    base = _base(tmp_path)
    system, message, meta = lens_think.assemble(base, "alpha", "2026-10-08")
    assert system == "BASE FRAME BODY\nline two\n"
    assert message.index("PROMPT OF alpha") < message.index("COUNTS")
    assert "fresh-eyes" in message and "2026-10-08" in message
    _, message, _ = lens_think.assemble(base, "beta", "2026-10-08")
    assert "_system/agent-lens/beta/" in message


def test_the_thinker_is_told_the_prompt_language(tmp_path: Path) -> None:
    assert lens_think.prompt_language("---\nid: x\n---\n## Намерение\nСмотреть на записи `_records/`\n") == "Russian"
    assert lens_think.prompt_language("---\nid: x\n---\n## Intent\nLook at the records\n") == ""
    base = _base(tmp_path)
    prompt = base / "_system/registries/lenses/alpha/prompt.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "Наблюдать за энергией владельца.\n",
                      encoding="utf-8")
    _, message, _ = lens_think.assemble(base, "alpha", "2026-10-08")
    assert "language the lens prompt above is written in — Russian." in message
    _, message, _ = lens_think.assemble(base, "alpha", "2026-10-08", "Russian")
    assert "Write your observations in Russian, the owner's language." in message


def test_a_thinker_runs_clean_read_only_on_the_latest_opus(tmp_path: Path, fake_claude: Path) -> None:
    base = _base(tmp_path)
    out = tmp_path / "out"
    [result] = _run(base, out, "alpha")
    assert result["status"] == "ok" and result["thinker_model"] == "claude-opus-test"
    assert (out / "alpha.thinker.md").read_text(encoding="utf-8") == "THOUGHTS about the base\n"
    [call] = _calls(fake_claude)
    args = call["args"]
    assert args[args.index("--model") + 1] == "opus", "an alias, never a pinned version"
    assert args[args.index("--tools") + 1] == "Read,Glob,Grep"
    assert args[args.index("--setting-sources") + 1] == ""
    assert args[args.index("--allowedTools") + 1] == "Read,Glob,Grep"
    assert args[args.index("--output-format") + 1] == "json"
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert not os.path.exists(call["system_file"]), "the system prompt file is removed"
    assert "--bare" not in args, "bare mode leaves the subscription login"
    assert call["system"] == "BASE FRAME BODY\nline two\n"
    assert "PROMPT OF alpha" in call["message"]
    assert Path(call["cwd"]).resolve() == base.resolve()


def test_a_failed_call_is_retried_from_a_clean_slate(tmp_path: Path, fake_claude: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "fail-then-ok")
    [result] = _run(_base(tmp_path), tmp_path / "out", "alpha")
    assert result["status"] == "ok" and result["attempts"] == 2
    first, second = _calls(fake_claude)
    assert first["message"] == second["message"], "the retry carries no trace of the failure"


def test_the_thinker_is_the_model_that_wrote_most_and_must_be_opus(
        tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base(tmp_path)
    [result] = _run(base, tmp_path / "out", "alpha")
    assert result["status"] == "ok" and result["thinker_model"] == "claude-opus-test"
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "light-model")
    [result] = _run(base, tmp_path / "out2", "alpha")
    assert result["status"] == "error" and result["cause"] == "wrong-model"
    assert result["attempts"] == lens_think.ATTEMPTS


def test_a_thinker_that_never_answers_fails_only_its_lens(tmp_path: Path, fake_claude: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "always-fail")
    results = _run(_base(tmp_path), tmp_path / "out", "alpha", "beta")
    assert [r["status"] for r in results] == ["error", "error"]
    assert all(r["attempts"] == lens_think.ATTEMPTS for r in results)
    assert "api safeguard" in results[0]["error"] and results[0]["cause"] == "model-error"
    assert len(_calls(fake_claude)) == 2 * lens_think.ATTEMPTS


def test_unparseable_output_is_an_error_not_a_crash(tmp_path: Path, fake_claude: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "garbage")
    [result] = _run(_base(tmp_path), tmp_path / "out", "alpha")
    assert result["status"] == "error" and "exit 1" in result["error"]
    assert result["cause"] == "unparseable"


def test_several_lenses_run_and_report_in_order(tmp_path: Path, fake_claude: Path) -> None:
    results = _run(_base(tmp_path), tmp_path / "out", "gamma", "alpha", "beta")
    assert [r["lens_id"] for r in results] == ["gamma", "alpha", "beta"]
    assert all(r["status"] == "ok" for r in results)
    systems = {c["system"] for c in _calls(fake_claude)}
    assert systems == {"MULTI FRAME BODY\n", "BASE FRAME BODY\nline two\n", "META FRAME BODY\n"}


def test_a_broken_lens_does_not_stop_the_others(tmp_path: Path, fake_claude: Path) -> None:
    results = _run(_base(tmp_path), tmp_path / "out", "missing", "alpha")
    assert results[0]["status"] == "error" and "no prompt.md" in results[0]["error"]
    assert results[0]["cause"] == "assemble"
    assert results[1]["status"] == "ok"


def test_no_claude_cli_is_a_clear_error_per_lens(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lens_think, "claude_binary", lambda: None)
    [result] = _run(_base(tmp_path), tmp_path / "out", "alpha")
    assert result["status"] == "error" and "not found" in result["error"]


def test_parallel_lenses_each_get_their_own_retry(tmp_path: Path, fake_claude: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "fail-then-ok")
    results = _run(_base(tmp_path), tmp_path / "out", "alpha", "beta", "gamma")
    assert [(r["status"], r["attempts"]) for r in results] == [("ok", 2)] * 3


def test_an_empty_answer_is_a_model_error(tmp_path: Path, fake_claude: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "empty")
    [result] = _run(_base(tmp_path), tmp_path / "out", "alpha")
    assert result["status"] == "error" and result["cause"] == "model-error"


def test_a_hung_call_is_killed_with_everything_it_started(tmp_path: Path, fake_claude: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "hang")
    out = tmp_path / "out"
    started = time.monotonic()
    assert lens_think.main(["run", "--base", str(_base(tmp_path)), "--out", str(out),
                            "--timeout", "2", "alpha"]) == 0
    [result] = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert result["cause"] == "timeout" and result["attempts"] == lens_think.TIMEOUT_ATTEMPTS
    assert time.monotonic() - started < 30
    child = int(Path(str(fake_claude) + ".child").read_text(encoding="utf-8"))
    time.sleep(0.5)
    assert not _running(child), "the call's own child was killed too"


def _running(pid: int) -> bool:
    """Alive and not a zombie waiting for a reaper (/proc where there is one)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    status = Path(f"/proc/{pid}/status")
    if status.exists():
        return "\tZ" not in status.read_text(encoding="utf-8").split("State:", 1)[1].splitlines()[0]
    return True


def test_an_unreadable_prompt_fails_only_its_lens(tmp_path: Path, fake_claude: Path) -> None:
    base = _base(tmp_path)
    (base / "_system/registries/lenses/beta/prompt.md").write_bytes(b"\xff\xfe not utf-8")
    results = _run(base, tmp_path / "out", "beta", "alpha")
    assert results[0]["status"] == "error" and results[0]["cause"] == "assemble"
    assert results[1]["status"] == "ok"


def test_a_lens_named_twice_runs_once_and_odd_ids_are_refused(tmp_path: Path,
                                                             fake_claude: Path) -> None:
    results = _run(_base(tmp_path), tmp_path / "out", "alpha", "alpha", "../alpha")
    assert [r["lens_id"] for r in results] == ["alpha", "../alpha"]
    assert results[1]["cause"] == "assemble" and len(_calls(fake_claude)) == 1


def test_start_returns_at_once_and_wait_reports_the_finished_run(tmp_path: Path,
                                                                fake_claude: Path,
                                                                capsys) -> None:
    base = _base(tmp_path)
    out = tmp_path / "out"
    started = time.monotonic()
    assert lens_think.main(["start", "--base", str(base), "--out", str(out),
                            "alpha", "beta"]) == 0
    assert time.monotonic() - started < 5, "start does not wait for the thinkers"
    code = 3
    for _ in range(20):
        code = lens_think.main(["wait", "--out", str(out), "--max-wait", "5"])
        if code != 3:
            break
    assert code == 0
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in results] == ["ok", "ok"]
    assert "alpha: ok" in capsys.readouterr().out


def test_wait_gives_up_after_its_limit_and_can_be_called_again(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    started = time.monotonic()
    assert lens_think.main(["wait", "--out", str(out), "--max-wait", "1"]) == 3
    assert time.monotonic() - started < 5


def test_wait_reports_a_run_that_died(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (out / "pid").write_text(f"{dead.pid}\n", encoding="utf-8")
    assert lens_think.main(["wait", "--out", str(out), "--max-wait", "10"]) == 4
