#!/usr/bin/env python3
"""What a scheduler tick declares about itself in the commit it delivers.

A delivery commit carries two lines in its message body:

    Minder-Tick-Base: <40-hex SHA>
    Minder-Tick-Run: <run id>

**The base is the fact that decides.** It is the commit the tick's tree was built
on — `HEAD` at the moment the tick commits, before anything integrates it onto a
tip that moved. A tick can knowingly undo only what its base contains; whatever arrived
between that base and the commit's parent, it never read. So a delivery that puts
a path back to its base content while the parent holds something newer reverted
work it never saw — the stale-tree defect — whoever produced that work, a tick of
the same tag included. And a delivery whose base IS its parent saw everything it
undid, so whatever it undid, it undid deliberately. `recover_reverted_ticks.py`
reads this instead of guessing a producer from how a subject is spelled.

**The run id only labels.** A rollback of "my previous run" is a different run of
the same tag, so the run id cannot separate a race from a deliberate rollback and
nothing decides on it. It joins a commit to its telemetry line and run log: the
session id when the runtime provides one, a generated id otherwise.

Why the message and not a telemetry line keyed to the SHA: the SHA a tick creates
does not survive delivery — `finalize-tick.sh` rebases it onto the moved tip and
a cloud delivery squash-merges it into a third SHA the tick never sees. The
message survives both, provided the squash is handed it (`squash-body`).

This module is the one home for the key names, the writer and the reader. Shell
never spells a key.

Usage:
  python3 scripts/lib/tick_identity.py trailers [--repo <dir>]
      print the declaration for a commit about to be made on HEAD; exit 1
      and print nothing when HEAD cannot be read
  python3 scripts/lib/tick_identity.py squash-body [--repo <dir>] [--rev <rev>]
      print the body a squash merge of <rev> (default HEAD) must carry: the
      fixed lead line, then that commit's identity lines when it has them
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.portable import configure_std_streams  # noqa: E402

BASE_KEY = "Minder-Tick-Base"
RUN_KEY = "Minder-Tick-Run"

# The squash body's first line. It must be non-empty: left empty, GitHub composes
# the squash message itself and appends a `Co-authored-by` trailer for the sandbox
# commit's author, which puts an assistant-authorship mark on `main`.
SQUASH_LEAD = "Autonomous scheduler tick."

SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

_SHA = re.compile(r"[0-9a-f]{40}")
_RUN = re.compile(r"[A-Za-z0-9._-]{1,128}")
# Anchored whole lines, matched anywhere AFTER the subject paragraph — NOT git's
# trailer block. A squash message can gain a later paragraph (a `Co-authored-by`
# after a blank line), and `git interpret-trailers --parse` reads only the last
# paragraph, so it would report no identity on a commit that carries one. The
# subject paragraph is excluded because it is built from free text (an override
# message, a failure cause), and a line smuggled in there must never count.
_LINE = re.compile(rf"^({re.escape(BASE_KEY)}|{re.escape(RUN_KEY)}):[ \t]*(.*?)[ \t]*$",
                   re.MULTILINE)


@dataclass(frozen=True)
class Identity:
    """What one commit message declares.

    `status` is `absent` (no identity line at all), `valid`, or `invalid`, with
    `reason` saying why. Only the syntax is judged here; whether the base exists
    and precedes the commit is a question about a repository, answered by the
    reader that has one.
    """
    status: str
    base: str = ""
    run: str = ""
    reason: str = ""


def parse(message: str) -> Identity:
    found: dict[str, set[str]] = {BASE_KEY: set(), RUN_KEY: set()}
    _subject, _sep, body = (message or "").replace("\r\n", "\n").strip("\n").partition("\n\n")
    for key, value in _LINE.findall(body):
        found[key].add(value)
    if not found[BASE_KEY] and not found[RUN_KEY]:
        return Identity("absent")
    for key, values in found.items():
        if len(values) > 1:
            return Identity("invalid", reason=f"{key} declared more than once, with "
                                              f"different values")
    base = next(iter(found[BASE_KEY]), "")
    run = next(iter(found[RUN_KEY]), "")
    if not base:
        return Identity("invalid", run=run, reason=f"{RUN_KEY} without {BASE_KEY}")
    if not _SHA.fullmatch(base):
        return Identity("invalid", run=run, reason=f"{BASE_KEY} is not a full SHA: {base!r}")
    if run and not _RUN.fullmatch(run):
        return Identity("invalid", base=base, reason=f"{RUN_KEY} is malformed: {run!r}")
    return Identity("valid", base=base, run=run)


def run_id() -> str:
    session = os.environ.get(SESSION_ENV, "").strip()
    return session if _RUN.fullmatch(session) else uuid.uuid4().hex


def format_trailers(base: str, run: str) -> str:
    return f"{BASE_KEY}: {base}" + (f"\n{RUN_KEY}: {run}" if run else "")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def current_base(repo: Path) -> str:
    """`HEAD` before the commit is made — the commit the tree was built on.

    Not `merge-base HEAD origin/main`. In `finalize-tick.sh` the two are the same
    commit (after a fold `HEAD` is the fork point; otherwise it refuses to run with
    unauthored commits ahead). But `ship-failure-note.sh` commits precisely when the
    owner's own commits sit ahead of `origin/main`: its tree contains them, and the
    merge-base would declare the tick blind to them — so a deliberate change on top
    of the owner's commit would prove as a stale revert. An older base than the
    truth is the one direction this must never err in.

    Empty when it cannot be established. The caller commits without an identity
    then; it never substitutes a guess.
    """
    res = _git(repo, "rev-parse", "--verify", "-q", "HEAD^{commit}")
    out = res.stdout.strip()
    return out if res.returncode == 0 and _SHA.fullmatch(out) else ""


def squash_body(message: str) -> str:
    ident = parse(message)
    if ident.status != "valid":
        return SQUASH_LEAD
    return f"{SQUASH_LEAD}\n\n{format_trailers(ident.base, ident.run)}"


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("trailers", "squash-body"))
    ap.add_argument("--repo", default=".")
    ap.add_argument("--rev", default="HEAD")
    args = ap.parse_args(argv)
    repo = Path(args.repo)

    if args.mode == "trailers":
        base = current_base(repo)
        if not base:
            print("tick-identity: cannot read HEAD", file=sys.stderr)
            return 1
        print(format_trailers(base, run_id()))
        return 0

    res = _git(repo, "log", "-1", "--format=%B", args.rev)
    # A message that cannot be read still yields the lead line: the squash body
    # must never be empty, and an identity-less delivery is recoverable while an
    # assistant-credited one on `main` is not.
    print(squash_body(res.stdout if res.returncode == 0 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
