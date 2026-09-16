"""Tests for the PreToolUse hook that lets a standing role publish its page.

The hook is what makes an unattended roles tick turnkey: without it the run
stops on a permission request nobody is awake to answer, and the page the role
exists to deliver silently never appears. With it, the approval is settled once
— and only for a role's own state directory, never as a blanket grant.

What these pin: the narrow yes, the many nos, and the shape of the answer. The
Windows case is not decoration — the first implementation searched the JSON
rendering of the input, where the encoder doubles every backslash, so a friend
on Windows would have been asked every night while the tests passed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[4] / ".claude" / "hooks" / "approve_role_artifact.py"

ROLE_PAGE = "/home/u/zettelkasten/_system/roles/minder-pm/state/99-today.html"
WINDOWS_ROLE_PAGE = "C:\\repo\\zettelkasten\\_system\\roles\\pm\\state\\99-today.html"


def _run(payload) -> tuple[int, str]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    done = subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True,
                          text=True, encoding="utf-8")
    return done.returncode, done.stdout.strip()


def _allows(payload) -> bool:
    code, out = _run(payload)
    assert code == 0, f"the hook must never fail the tool call: exit {code}"
    if not out:
        return False
    verdict = json.loads(out)["hookSpecificOutput"]
    assert verdict["hookEventName"] == "PreToolUse"
    return verdict["permissionDecision"] == "allow"


def test_it_approves_a_roles_own_page():
    assert _allows({"tool_name": "Artifact", "tool_input": {"file_path": ROLE_PAGE}})


def test_it_approves_that_page_on_windows():
    """The encoder doubles a backslash; normalising the rendering instead of the
    value looks correct and asks a Windows owner every single night."""
    assert _allows({"tool_name": "Artifact",
                    "tool_input": {"file_path": WINDOWS_ROLE_PAGE}})


def test_it_finds_the_path_however_deeply_it_is_nested():
    assert _allows({"tool_name": "Artifact",
                    "tool_input": {"files": {"a.css": ROLE_PAGE.replace(".html", ".css")}}})


@pytest.mark.parametrize("payload, why", [
    ({"tool_name": "Artifact",
      "tool_input": {"file_path": "/home/u/zettelkasten/6_posts/draft.html"}},
     "an artifact from anywhere else in the base still asks"),
    ({"tool_name": "Artifact", "tool_input": {"title": "my roles are great"}},
     "the word `roles` in prose is not a path"),
    ({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
     "another tool is none of this hook's business"),
    ({}, "an empty payload decides nothing"),
    ("not json at all", "unreadable input must never become an approval"),
])
def test_everything_else_falls_through_to_the_normal_flow(payload, why):
    assert not _allows(payload), why


def test_the_hook_is_registered_for_the_artifact_tool():
    """A hook nothing invokes is the same as no hook, and nothing else would
    notice: the run would simply go back to waiting on a human."""
    settings = json.loads((HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    matched = [e for e in entries if "Artifact" in e.get("matcher", "")]
    assert matched, f"no PreToolUse entry matches Artifact: {entries}"
    commands = [h["command"] for e in matched for h in e["hooks"]]
    assert any(HOOK.name in c for c in commands), commands
    assert any(c.startswith("python3 ") for c in commands), (
        "invoke through python3: a Windows checkout carries no executable bit")
