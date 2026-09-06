#!/usr/bin/env python3
"""Turn a previous-shape role directory into a conversion PLAN the concierge runs.

The hand-off tells the owner what they had. This tells `/minder:mem:role:add` what it
can carry across without asking, and — just as importantly — what it must not
decide alone. One JSON file per parked role, read by `/minder:mem:role:add --from-previous`.

Why a plan rather than a finished role: the previous shape's prose is written in
a vocabulary that no longer exists (parts, ledger ops, staged acts), and copying
it verbatim would tell a role to do things nothing implements — it would not
fail, it would improvise. Rewriting that prose into the current vocabulary is
exactly what the concierge is for. And `writes:` is the boundary the whole design
rests on: the plan PROPOSES it, with its reasoning, and the owner confirms. A
proposal the owner sees is not a guess.

What is derivable, and how confident:

    certain   — id, name, cadence, status. Same meaning in both shapes.
    proposed  — writes. `emit_inbox: true` means the role put notes in the
                inbox; any role keeps its own state. Both are safe defaults the
                owner confirms. Anything beyond them is theirs to name.
    proposed  — secrets, and ONLY for a role that actually reached outward.
                The store's names belong to the base, not to any one role. The
                store is the SAME file and the SAME encryption in both shapes —
                only the env var holding the key was renamed — so the values
                carry across intact and nothing is re-entered.
    seed      — the body. The old `hooks/tick.md`, handed to the concierge as
                RAW MATERIAL to rewrite, never as text to paste.
    memory    — what the role LEARNT, as an inventory with paths. The
                assignment is half a long-running role; the other half is the
                board, the reading and the verdicts it built up over months.
                Both shapes keep that between runs, so it carries across — but
                only if something points at it. Nothing did, and a re-created
                role woke up remembering nothing while every byte sat intact
                one directory away.

Emits `_previous/{id}.plan.json`. Deletes nothing, reads only.

**The plan file is a view, not the source.** What a parked role holds lives in
the parked directory; this only reads it. So the file may be regenerated at any
time, and `/minder:mem:role:add --from-previous` does exactly that before reading it:

    python3 <base>/_system/scripts/roles_previous_plan.py <base>/_system/roles/_previous

Deriving at read time is what removes the whole «this artifact was written
before we knew better» class, rather than one instance of it: a plan written
by an older engine would otherwise stay on disk, authoritative and wrong,
forever.

Invoked with the parked directory alone, it reads the credential store's names
itself. That derivation used to live in the calling shell, which made two owners
for one fact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import configure_std_streams  # type: ignore

from roles_previous_memory import inventory  # type: ignore


CONFIG = "config.yml"
# Old and new secret stores are the same path, shape and primitive (Fernet);
# only the environment variable holding the key was renamed. Verified by
# encrypting in the old scheme and decrypting with the current module.
NEW_KEY_ENV = "MINDER_MEMORY_ROLES_KEY"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def scalar(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""


def flag(text: str, key: str) -> bool:
    return scalar(text, key).lower() in ("true", "yes", "on")


def listed(text: str, key: str) -> list:
    """Values of a top-level `key:`, in either YAML list form.

    Both forms occur in real previous-shape configs, because they were written
    by a concierge rather than by a schema:

        tools:            tools: [notion, calendar]
          - notion

    Reading only the block form makes a tool-bearing role look like it used no
    tools — and the role's conversion plan then tells the owner no credentials
    carry across, when they do. Silence about a credential is exactly the class
    of miss this whole carry-over exists to prevent.
    """
    for line in text.splitlines():
        if not line.startswith(f"{key}:"):
            continue
        inline = line.split(":", 1)[1].strip()
        if inline.startswith("[") and inline.endswith("]"):
            return [
                item.strip().strip("'\"")
                for item in inline[1:-1].split(",")
                if item.strip()
            ]
        break

    out, capturing = [], False
    for line in text.splitlines():
        if line.startswith(f"{key}:"):
            capturing = True
            continue
        if capturing:
            stripped = line.strip()
            if line[:1] not in (" ", "\t", "-") and stripped:
                break
            if stripped.startswith("- "):
                out.append(stripped[2:].strip().strip("'\""))
    return out


def cadence_of(cfg: str) -> str:
    """`cadence` + `cadence_anchor` as one current-shape cadence string.

    The grammars agree on the forms that matter — `daily`, `weekly <dow>`,
    `monthly <n>` — so this is a join, not a translation.
    """
    parts = [scalar(cfg, "cadence"), scalar(cfg, "cadence_anchor")]
    return " ".join(p for p in parts if p)


def build(role_dir: Path, store_names: list) -> dict:
    cfg = read(role_dir / CONFIG)
    tick = read(role_dir / "hooks" / "tick.md").strip()
    ask = read(role_dir / "hooks" / "ask.md").strip()
    brief = read(role_dir / "brief.md").strip()
    memory = inventory(role_dir)

    writes, why = ["state"], ["every role keeps its own memory"]
    if flag(cfg, "emit_inbox"):
        writes.append("inbox")
        why.append("`emit_inbox: true` — it put notes into your inbox")

    return {
        "id": scalar(cfg, "id") or role_dir.name,
        "certain": {
            "name": scalar(cfg, "name") or role_dir.name,
            "cadence": cadence_of(cfg) or "weekly",
            "status": scalar(cfg, "status") or "active",
        },
        "proposed": {
            "writes": writes,
            "writes_reasoning": why,
            # ONLY for a role that actually reached outward. The store's names
            # belong to the base, not to any one role, and handing every role
            # every credential would declare ones it never used — noise at best,
            # and a preflight failure at worst. Which of these a tool-bearing
            # role used lived in the old tools registry, which is opaque here,
            # so these are candidates the owner confirms, never a conclusion.
            "secrets": store_names if listed(cfg, "tools") else [],
            "secrets_note": (
                f"read from the credential store, which is the same file and the "
                f"same encryption in both shapes; the key lives in {NEW_KEY_ENV}. "
                f"The values carry across untouched; nothing has to be re-entered."
            ) if (store_names and listed(cfg, "tools")) else "",
        },
        "seed": {
            "assignment": tick,
            "ask_hook": ask,
            "brief": brief,
            "instruction": (
                "RAW MATERIAL, not text to paste. It is written in a vocabulary "
                "that no longer exists — parts, ledger ops, staged acts. Read what "
                "the owner WANTED and write that in the current shape, in their "
                "register. If a sentence only makes sense under the old machinery, "
                "drop it and say so."
            ),
        },
        "memory": dict(
            memory,
            instruction=(
                "What this role LEARNT, still on disk, paths relative to the "
                "directory this plan sits in. A role that ran for months is half "
                "assignment and half accumulated state, and re-creating only the "
                "assignment ships a role that has forgotten everything it knew. "
                "READ these files, then seed the new role's `state/` from them "
                "before the trial run — carrying the substance across, in "
                "whatever files the new assignment says it keeps. As with the "
                "assignment: rewrite, never paste. The old part archetypes "
                "(ledger / narrative / assessment) are gone; what they held is "
                "not."
            ) if memory["has_memory"] else "",
        ),
        "must_ask": _must_ask(cfg, tick),
    }


def _must_ask(cfg: str, tick: str) -> list:
    """What the concierge may NOT settle alone. Kept short on purpose.

    A long list turns a two-minute confirmation into an interview and the owner
    stops reading — which is how a `writes:` they never looked at gets accepted.
    """
    asks = []
    if any(w in tick.lower() for w in ("файл", "документ", "file", "document",
                                       "доку", "note", "заметку")):
        asks.append({
            "topic": "a named document",
            "why": ("the assignment mentions maintaining a document. If it keeps "
                    "ONE file, that file goes in `writes:` by name — a whole "
                    "directory of the owner's notes is refused, and rightly"),
        })
    if listed(cfg, "tools"):
        asks.append({
            "topic": "the outside service",
            "why": ("it reached outward. The credential carries across, but the "
                    "endpoint and request shape lived in the old tools registry "
                    "and must be written into the role's own prose now"),
        })
    return asks


def store_names_for(parked_root: Path) -> list:
    """Credential names on this base, read from the parked directory's position.

    The store is the SAME file, shape and primitive in both shapes — only the
    environment variable holding the key was renamed — so the NAMES are readable
    with no key at all. Reading them here rather than in the calling shell is
    what lets any caller regenerate a plan with one argument.

    `_previous` sits at `<base>/_system/roles/_previous`, so the base is three
    levels up. A directory that is not shaped that way (a test fixture, a
    hand-made copy) yields no names rather than an error: a plan that names no
    credential is recoverable, and a crash mid-update is not.
    """
    try:
        store = parked_root.parents[2] / "_system" / "state" / "secrets.enc.json"
        payload = json.loads(store.read_text(encoding="utf-8"))
    except (IndexError, OSError, UnicodeDecodeError, ValueError):
        return []
    return sorted(payload) if isinstance(payload, dict) else []


def main(argv: list) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parked_root = Path(argv[1]).resolve()
    if not parked_root.is_dir():
        return 0
    store_names = json.loads(argv[2]) if len(argv) > 2 else store_names_for(parked_root)
    written = 0
    for d in sorted(parked_root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        plan = build(d, store_names)
        (parked_root / f"{plan['id']}.plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
    print(f"[roles previous-shape] wrote {written} conversion plan(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
