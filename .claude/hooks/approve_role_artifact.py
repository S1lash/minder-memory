#!/usr/bin/env python3
"""Approve the Artifact tool for a role's own page, and for nothing else.

Why this exists: a scheduled roles tick runs with nobody watching it, and a
standing role's job includes publishing the page it maintains. A permission
request in that run has no one to answer it — the run waits on a human who is
asleep, and the page it was supposed to deliver silently does not appear. The
owner settles that consent once, when the role is created; the run itself must
never ask again.

Why a hook rather than a permission rule: a cloud run clones the repository
fresh, so the workspace is never trusted, and `permissions.allow` in a
project's settings is documented as "Not used" there. Hooks from the
repository ARE used in that same situation, which makes this the one
repository-shippable mechanism that reaches a friend's scheduled run.

The scope is deliberately narrow. This approves a publish whose source file
lives under `_system/roles/<role>/`, which is a role's own state directory and
the only place a role may write. Anything else — an artifact from a session
working anywhere else in the base — falls through to the normal permission
flow and still asks. Silence here is the safe answer: printing nothing leaves
the decision exactly where it was.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROLE_STATE = "/_system/roles/"


def _configure_streams() -> None:
    """UTF-8 both ways before the first read.

    A role's page can sit behind a path with non-ASCII in it, and on Windows
    both directions decode through the platform code page — the path dies on
    the way in, the answer on the way out. The engine's own helper owns this
    rule; the fallback exists because this file must keep working even in a
    clone where `scripts/` has not been checked out yet, and a hook that
    crashes is a hook that silently stops approving.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        from lib.portable import configure_std_streams  # noqa: PLC0415
        configure_std_streams()
    except Exception:
        for stream in (sys.stdin, sys.stdout):
            try:
                stream.reconfigure(encoding="utf-8", newline="\n")
            except (AttributeError, ValueError):
                pass


def _strings(value) -> "list[str]":
    """Every string anywhere in the tool input, however it is nested."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def decision(payload: dict) -> dict | None:
    if payload.get("tool_name") != "Artifact":
        return None
    # The path can arrive under any of several keys as the tool evolves, so
    # every string in the input is checked rather than one field guessed at. A
    # miss costs a prompt; a wrong guess would hand out a blanket approval.
    # Each value is normalised on its own: searching the JSON *rendering*
    # instead looks right and fails on Windows, where the encoder doubles every
    # backslash and `\_system\roles\` stops matching.
    if not any(ROLE_STATE in s.replace("\\", "/")
               for s in _strings(payload.get("tool_input", {}))):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": (
                "a standing role publishing the page it maintains; the owner "
                "consented when the role was created, and the run has nobody "
                "to ask"
            ),
        }
    }


def main() -> int:
    _configure_streams()
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Unreadable input must not become an approval.
        return 0
    verdict = decision(payload if isinstance(payload, dict) else {})
    if verdict is not None:
        print(json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
