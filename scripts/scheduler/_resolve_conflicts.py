"""Settle the conflicts a tick's delivery can settle without judgement.

Why this exists. Two scheduled runs that overlap both write into the same
ledgers — the clarifications queue, the per-pipeline logs, a person's mention
list — and the later one to deliver used to stop on the first such file and
lose its whole run. Almost every one of those collisions is two runs ADDING
different lines at the same place, with neither touching what was there
before. Keeping both is the only correct result for that shape, and it needs
no judgement, so it is done here, mechanically, before anything is asked of
the model.

What is NOT settled here: two additions that introduce the same `key:` (both
lines kept would duplicate a frontmatter field), a block where either side
changed or removed a line that was already there (the common ancestor's section is not empty), a file
deleted on one side and edited on the other, and anything without three-way
conflict markers. Those carry a real decision, and are left for the tick to
resolve (Step 5c of the scheduler prompts) — or, if it cannot, for
finalize-tick.sh's last resort.

The merge this reads is `origin/main` merged INTO the tick's commit, with
`merge.conflictStyle=diff3`: "ours" is the tick, "theirs" is what landed on
main first. Kept order is theirs then ours — the earlier delivery first.

Usage:
  python3 scripts/scheduler/_resolve_conflicts.py auto
      Resolve every unmerged path that is safely resolvable, stage it, and print
      the paths still unresolved (one per line).
  python3 scripts/scheduler/_resolve_conflicts.py markers <path>...
      Print the given paths that still carry conflict markers.
  python3 scripts/scheduler/_resolve_conflicts.py snapshot <file> <path>...
      Record the open paths as they stand when the closing step stops.
  python3 scripts/scheduler/_resolve_conflicts.py open <snapshot> <path>...
      Print the paths still unresolved: markers left, or unchanged since the
      snapshot.

Always exits 0 unless git itself cannot be read (exit 2).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.portable import configure_std_streams  # noqa: E402

OURS = "<<<<<<< "
BASE = "||||||| "
SEP = "======="
THEIRS = ">>>>>>> "


def git(*args: str) -> str:
    res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()[:200]}")
    return res.stdout


def unmerged_paths() -> list[str]:
    return [p for p in git("diff", "--name-only", "--diff-filter=U").splitlines() if p]


def has_markers(text: str) -> bool:
    for line in text.splitlines():
        if line.startswith(OURS) or line.startswith(THEIRS):
            return True
    return False


def resolve_text(text: str) -> tuple[str, bool]:
    """Return (new_text, fully_resolved).

    Insertion-only blocks are replaced by theirs + ours; any other block is
    kept verbatim, markers and all, so a later reader sees it untouched.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    resolved_all = True
    while i < len(lines):
        line = lines[i]
        if not line.startswith(OURS):
            out.append(line)
            i += 1
            continue
        # Collect one block.
        start = i
        ours: list[str] = []
        base: list[str] = []
        theirs: list[str] = []
        section = "ours"
        has_base = False
        i += 1
        closed = False
        while i < len(lines):
            cur = lines[i]
            if cur.startswith(BASE) and section == "ours":
                section = "base"
                has_base = True
            elif cur.rstrip("\r\n") == SEP and section in ("ours", "base"):
                section = "theirs"
            elif cur.startswith(THEIRS) and section == "theirs":
                closed = True
                i += 1
                break
            elif section == "ours":
                ours.append(cur)
            elif section == "base":
                base.append(cur)
            else:
                theirs.append(cur)
            i += 1
        block = lines[start:i]
        if closed and has_base and not "".join(base).strip() and not _same_field(ours, theirs):
            if ours == theirs:
                out.extend(theirs)
            else:
                out.extend(_ensure_newline(theirs))
                out.extend(ours)
        else:
            out.extend(block)
            resolved_all = False
    return "".join(out), resolved_all


_FIELD = re.compile(r"^\s*([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*:")


def _same_field(ours: list[str], theirs: list[str]) -> bool:
    """Both sides introduce the same `key:` — keeping both would duplicate it.

    Two runs adding a frontmatter field the note did not have (`last_applied:`,
    `status:`) is an addition on both sides, and keeping both lines writes the
    key twice: frontmatter that no longer parses. That is a decision between
    two values, so it goes to the tick, not to concatenation.
    """
    def keys(chunk: list[str]) -> set[str]:
        return {m.group(1) for m in (_FIELD.match(line) for line in chunk) if m}
    if ours == theirs:
        return False
    return bool(keys(ours) & keys(theirs))


def _ensure_newline(chunk: list[str]) -> list[str]:
    if chunk and not chunk[-1].endswith("\n"):
        return chunk[:-1] + [chunk[-1] + "\n"]
    return chunk


def cmd_auto() -> int:
    remaining: list[str] = []
    for rel in unmerged_paths():
        path = Path(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Deleted on one side, or not text: a decision, not a merge.
            remaining.append(rel)
            continue
        if BASE not in text:
            remaining.append(rel)
            continue
        new, done = resolve_text(text)
        if new != text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(new)
        if done and not has_markers(new):
            git("add", "--", rel)
        else:
            remaining.append(rel)
    for rel in remaining:
        print(rel)
    return 0


def cmd_markers(paths: list[str]) -> int:
    for rel in paths:
        try:
            text = Path(rel).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            continue
        if has_markers(text):
            print(rel)
    return 0


def _digest(rel: str) -> str | None:
    """Hash of a path's bytes, or None when the path does not exist."""
    try:
        with open(rel, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except FileNotFoundError:
        return None


def cmd_snapshot(out: str, paths: list[str]) -> int:
    """Record each open path as it stands when the closing step stops."""
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({rel: _digest(rel) for rel in paths}, handle, ensure_ascii=False)
    return 0


def cmd_open(snapshot: str, paths: list[str]) -> int:
    """Print the paths not yet resolved.

    Open means: still carrying conflict markers, or byte-for-byte what it was
    when the closing step stopped. The second test is what catches conflicts
    with no markers at all — a binary file, or one deleted on one side and
    edited on the other sits in the tree as one side's version, and only a
    change since the stop shows that the tick actually decided it.
    """
    try:
        with open(snapshot, "r", encoding="utf-8") as handle:
            before = json.load(handle)
    except (OSError, ValueError):
        before = {}
    for rel in paths:
        now = _digest(rel)
        if rel in before and before[rel] == now:
            print(rel)
            continue
        if now is None:
            continue
        try:
            text = Path(rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if has_markers(text):
            print(rel)
    return 0


def main(argv: list[str]) -> int:
    configure_std_streams()
    try:
        if argv and argv[0] == "auto":
            return cmd_auto()
        if argv and argv[0] == "markers":
            return cmd_markers(argv[1:])
        if len(argv) >= 2 and argv[0] == "snapshot":
            return cmd_snapshot(argv[1], argv[2:])
        if len(argv) >= 2 and argv[0] == "open":
            return cmd_open(argv[1], argv[2:])
    except RuntimeError as exc:
        print(f"_resolve_conflicts: {exc}", file=sys.stderr)
        return 2
    print("usage: _resolve_conflicts.py auto | markers <path>...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
