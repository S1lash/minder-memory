#!/usr/bin/env python3
"""Migration 033's producer — raise what an earlier rename did to the owner's own names.

minder-memory-rebrand: keep-legacy-tokens — the former name below is what this
migration looks FOR; it is the subject of the check, not a missed surface.

A clone that took the 1.0.0 update had its whole tree renamed by a map that did
not yet distinguish the product from the owner. `minder-ztn-<their own tail>` —
their repository, their clone folder, a host of theirs — became
`minder-memory-<tail>`, which is a path that does not exist. Nothing announces
it: the damaged line reads perfectly well, and the only witness is what the same
file said before the migration ran.

What this migration does NOT do is fix it. The engine cannot know whether the
directory on disk still carries the old name, was renamed to match, or never
existed on this machine at all — and a rewrite that guessed wrong would replace
a visible wrong path with an invisible one. So each finding becomes ONE
clarification for the owner, with the current text and the text from before the
rename beside each other, and the file is left exactly as it is.

Detection is not restated here: it is `find_own_name_damage` in
`scripts/check_update.py`, which the post-update check also uses. The import
runs in that direction on purpose — a migration is transient and may import a
permanent script; the reverse would take the check down when the chain floor
moves past this migration.

`heal`: a clone where this never ran is not broken, only unwarned, and a notice
must never be able to block a future update.

Usage:
  python3 scripts/migrations/_033_own_names.py --repo-root <root> [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_update import find_own_name_damage, pre_032_commit  # noqa: E402
from lib.portable import configure_std_streams, read_text_utf8, write_text_utf8  # noqa: E402

CLARIFICATIONS = Path("zettelkasten/_system/state/CLARIFICATIONS.md")
BASE_MARKER = Path("zettelkasten/_system")
OPEN_ITEMS = "## Open Items"
MIGRATION_NAME = "033-own-names-after-the-rename.sh"
SOURCE_LINE = f"**Source:** migration {MIGRATION_NAME}"

RESTORE_SENTENCE = (
    "your own repository or folder name was renamed by 1.0.0; restore it if the "
    "directory is still named that way"
)


def _subject_line(findings: list[dict]) -> str:
    paths = sorted({f"{f['path']}:{f['line']}" for f in findings})
    return "**Subject:** " + ", ".join(f"`{p}`" for p in paths)


def render_item(findings: list[dict], *, today: str) -> str:
    """One clarification, whatever the number of findings.

    One item and not one per line: they are all the same question asked of the
    same owner about the same release, and a queue that asks it nine times is a
    queue that gets skimmed once.
    """
    lines = [
        "",
        f"## 033 {today} own-names-after-the-rename "
        f"({len(findings)} line(s) — 1 process-compatibility)",
        "",
        f"### {today} — process-compatibility: a name of yours was renamed by an earlier release",
        "",
        "**Type:** process-compatibility",
        _subject_line(findings),
        SOURCE_LINE,
        "**Suggested action:** fix-by-hand | dismiss",
        "**Confidence tier:** surfaced",
        "**Applied:** no",
        "",
        "**Quote:**",
    ]
    for f in findings:
        lines.append(f"> `{f['path']}:{f['line']}` now: {f['text'].strip()}")
        lines.append(f"> before the rename: {f['before'].strip()}")
    lines += [
        "",
        "**Context:** The 1.0.0 rename map could not yet tell the product from its owner. A "
        "name that opened with the former product slug and continued with something of yours "
        "— a repository, a folder, a host — was rewritten as though the whole of it named the "
        "product, so the path now points somewhere that does not exist. The line still reads "
        "plausibly, which is why nothing else has flagged it; the second line under each "
        "quote is what the same file said at the commit before the rename migration ran.",
        "",
        "**Uncertainty:** Only you know what that path is on this machine now. The directory "
        "may still carry its original name, may have been renamed to match, or may never have "
        "existed here. Nothing in the repository can answer that, so nothing here rewrote the "
        "line — a wrong guess would turn a visible wrong path into an invisible one.",
        "",
        f"**To resolve:** {RESTORE_SENTENCE.capitalize()}. Check each path above, put back "
        "whichever spelling matches the directory as it actually is, and dismiss the item. "
        "The engine will not touch these names again: it renames what it owns and leaves "
        "yours whole. If a path named here belongs to a file the engine ships rather than "
        "one of yours, that is a defect of this check and not of your clone — report it, and "
        "do not edit the shipped file.",
        "",
    ]
    return "\n".join(lines)


def run(repo_root: Path, *, dry_run: bool) -> dict:
    result: dict = {"findings": [], "action": "none", "clarifications": str(CLARIFICATIONS)}
    if not (repo_root / BASE_MARKER).is_dir():
        result["action"] = "no-base"
        return result
    before = pre_032_commit(repo_root)
    if before is None:
        result["action"] = "no-before-state"
        return result
    result["before"] = before
    findings = find_own_name_damage(repo_root, before)
    result["findings"] = findings
    if not findings:
        result["action"] = "nothing-to-raise"
        return result

    target = repo_root / CLARIFICATIONS
    text = read_text_utf8(target) if target.is_file() else "# Clarifications Needed\n\n## Open Items\n"
    subject = _subject_line(findings)
    if SOURCE_LINE in text and subject in text:
        # Idempotent by the question, not by a timestamp: the same paths raised
        # again is the same question, and a queue that regrows every night is a
        # queue nobody finishes.
        result["action"] = "already-raised"
        return result
    result["action"] = "would-append" if dry_run else "appended"
    if dry_run:
        return result

    item = render_item(findings, today=date.today().isoformat())
    if OPEN_ITEMS in text:
        head, _, tail = text.partition(OPEN_ITEMS)
        new_text = head + OPEN_ITEMS + item + tail
    else:
        new_text = text.rstrip("\n") + "\n\n" + OPEN_ITEMS + item
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_utf8(target, new_text)
    return result


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    result = run(repo_root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result["action"] == "no-base" else 0

    if result["action"] == "no-base":
        print(f"033: {repo_root} holds no {BASE_MARKER} — this is not a base; will retry next update",
              file=sys.stderr)
        return 1
    if result["action"] == "no-before-state":
        print("033: the migration ledger was never committed here, so there is no state from "
              "before the rename to compare against — nothing raised.")
        return 0
    if result["action"] == "nothing-to-raise":
        print("033: no name of yours was renamed into a path that does not exist.")
        return 0
    if result["action"] == "already-raised":
        print(f"033: the same {len(result['findings'])} line(s) are already in the "
              "clarifications queue — nothing appended.")
        return 0
    print(f"033: {len(result['findings'])} line(s) where an earlier release renamed a name of "
          f"yours — raised as one item in {CLARIFICATIONS}. Nothing was rewritten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
