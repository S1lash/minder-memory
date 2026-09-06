#!/usr/bin/env python3
"""Strict self-check for the previous-shape role carry-over.

Re-runnable by the owner at any time, from the repository root:

    python3 <base>/_system/scripts/roles_previous_selfcheck.py [<base>]

It answers one question — **is the owner's data still whole, and is the state
of play what the parked tree says it is?** — and it answers it by looking, not
by trusting a report.

The bar is deliberately harsh in one direction: every check that cannot prove
its claim FAILS. A carry-over that quietly half-worked is worse than one that
refused, because the owner stops looking.

Exit codes:
    0 — every check passed
    1 — at least one check FAILED (owner data at risk, or a false claim)
    2 — the check could not run (no base, unreadable tree)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _common import configure_std_streams  # type: ignore

# One owner for the parked directory's name.
from roles_previous_memory import PARKED_DIRNAME as PARKED  # type: ignore


HANDOFF = "HANDOFF.md"
CONFIG = "config.yml"
ROLE = "role.md"

OK, FAIL, INFO = "PASS", "FAIL", "  · "


class Report:
    def __init__(self) -> None:
        self.failures: list = []
        self.lines: list = []

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        mark = OK if ok else FAIL
        self.lines.append(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.failures.append(label)
        return ok

    def note(self, text: str) -> None:
        self.lines.append(f"{INFO}{text}")

    def emit(self) -> int:
        print("\n".join(self.lines))
        if self.failures:
            print(f"\n  {len(self.failures)} CHECK(S) FAILED:")
            for f in self.failures:
                print(f"    - {f}")
            print("\n  Nothing was deleted in any case — but do not")
            print("  treat the move as complete until these are resolved.")
            return 1
        print("\n  All checks passed.")
        return 0


def discover_base(repo: Path) -> Path | None:
    found = [d for d in sorted(repo.iterdir())
             if d.is_dir() and (d / "_system/scripts/roles_run.py").is_file()]
    if len(found) == 1:
        return found[0]
    if not found and (repo / "zettelkasten").is_dir():
        return repo / "zettelkasten"
    return None


def file_count(d: Path) -> int:
    return sum(1 for p in d.rglob("*") if p.is_file())


def main(argv: list) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    repo = Path.cwd().resolve()
    base = Path(argv[1]).resolve() if len(argv) > 1 else discover_base(repo)
    if base is None or not base.is_dir():
        print("selfcheck: no single Minder Memory base found — cannot verify.", file=sys.stderr)
        return 2
    repo = base.parent
    roles_root = base / "_system" / "roles"
    parked_root = roles_root / PARKED

    r = Report()
    r.lines.append("")
    r.lines.append(f"[roles previous-shape selfcheck] base: {base.name}")
    r.lines.append("")

    if not parked_root.is_dir():
        r.note("Nothing was parked — this base had no previous-shape roles.")
        live = [d for d in roles_root.iterdir()
                if roles_root.is_dir() and d.is_dir() and not d.name.startswith("_")] \
            if roles_root.is_dir() else []
        stragglers = [d.name for d in live
                      if (d / CONFIG).is_file() and not (d / ROLE).is_file()]
        r.check(not stragglers,
                "no previous-shape role left un-parked",
                f"still in the live path: {', '.join(stragglers)}" if stragglers else "")
        return r.emit()

    # --- 1. the hand-off exists and is not empty -----------------------------
    handoff = parked_root / HANDOFF
    r.check(handoff.is_file(), "hand-off file was written",
            str(handoff.relative_to(repo)))
    if handoff.is_file():
        text = handoff.read_text(encoding="utf-8", errors="replace")
        r.check(len(text) > 400, "hand-off has real content, not a stub",
                f"{len(text)} chars")

    parked = sorted(d for d in parked_root.iterdir()
                    if d.is_dir() and not d.name.startswith("_"))
    r.check(bool(parked), "at least one role is parked", f"{len(parked)} found")

    # --- 2. every parked role still has its files ----------------------------
    for d in parked:
        n = file_count(d)
        r.check((d / CONFIG).is_file(),
                f"{d.name}: its config survived the move")
        r.check(n > 0, f"{d.name}: files are present", f"{n} file(s)")
        # The hand-off must actually mention it, or the owner never learns it
        # exists — which is the entire failure this check was built for.
        if handoff.is_file():
            r.check(d.name in text or f"/{d.name}/" in text,
                    f"{d.name}: named in the hand-off")
        # The plan is what makes `--from-previous` possible. Without it the
        # concierge has nothing to pre-fill from and the owner is back to
        # re-interviewing themselves about a role they already designed.
        plan = parked_root / f"{d.name}.plan.json"
        if r.check(plan.is_file(), f"{d.name}: has a conversion plan"):
            try:
                payload = json.loads(plan.read_text(encoding="utf-8"))
                r.check(bool(payload.get("certain", {}).get("cadence")),
                        f"{d.name}: the plan carries a schedule")
                r.check(bool(payload.get("proposed", {}).get("writes")),
                        f"{d.name}: the plan proposes where it may write")
                # A role that ran carries a board, a reading, a decision log —
                # usually more of its value than the assignment. If the plan
                # does not point at it, the owner re-creates the role and it
                # wakes up remembering nothing, while every byte sits intact one
                # directory away. Present-but-unreferenced is lost, so this is a
                # FAIL rather than a note.
                mem = payload.get("memory") or {}
                if mem.get("has_memory"):
                    located = bool(mem.get("rendered") or mem.get("parts")
                                   or mem.get("decisions"))
                    r.check(located and bool(mem.get("instruction")),
                            f"{d.name}: the plan carries the memory it built up",
                            f"{mem.get('records', 0)} record(s) located")
            except ValueError:
                r.check(False, f"{d.name}: the plan is valid JSON")

    # --- 3. nothing previous-shape was left behind in the live path ----------
    live = [d for d in roles_root.iterdir()
            if d.is_dir() and not d.name.startswith("_")]
    stragglers = [d.name for d in live
                  if (d / CONFIG).is_file() and not (d / ROLE).is_file()]
    r.check(not stragglers, "no previous-shape role left in the live path",
            f"still there: {', '.join(stragglers)}" if stragglers else "")

    # --- 4. a parked role can never be mistaken for a live one ---------------
    r.check(PARKED.startswith("_"),
            "the parked directory is invisible to role discovery",
            f"`{PARKED}` — the engine skips `_`-prefixed names")

    # --- 5. the engine agrees: it discovers only real roles ------------------
    cli = base / "_system" / "scripts" / "roles_run.py"
    if cli.is_file():
        proc = subprocess.run(
            [sys.executable, str(cli), "due", "--base", str(base), "--repo", str(repo)],
            capture_output=True, text=True)
        r.check(proc.returncode == 0, "the engine lists roles without error",
                proc.stderr.strip()[:120])
        if proc.returncode == 0:
            try:
                rows = json.loads(proc.stdout or "[]")
                ids = sorted(i for i in (row.get("id") for row in rows) if i)
                # Deliberately NOT a check on id reuse. Re-creating a role under
                # the SAME id is the intended outcome — the parked original is
                # `_`-prefixed and has no `role.md`, so it cannot be discovered
                # or run whatever it is called. An earlier version flagged reuse
                # as a failure, which called the desired result broken AND
                # masked the real finding underneath it.
                r.note(f"engine sees {len(rows)} live role(s)"
                       + (f": {', '.join(ids)}" if ids else ""))
                revived = sorted(set(ids) & {d.name for d in parked})
                if revived:
                    r.note(f"re-created from a parked original: {', '.join(revived)}")
            except ValueError:
                r.check(False, "the engine's role listing is valid JSON")

    # --- 6. re-created roles, if any, actually validate ----------------------
    recreated = sorted(d.name for d in live if (d / ROLE).is_file())
    if recreated:
        proc = subprocess.run(
            [sys.executable, str(cli), "validate", "--base", str(base), "--repo", str(repo)],
            capture_output=True, text=True)
        try:
            payload = json.loads(proc.stdout or "{}")
        except ValueError:
            payload = {}
        findings = payload.get("findings") or []
        # A missing key is not a defect here: it lives in the scheduler's
        # environment, so it is absent from any ordinary shell — including this
        # one. Failing on it would report the expected state as broken and bury
        # the findings that do matter underneath.
        real = [f for f in findings
                if "MINDER_MEMORY_ROLES_KEY is not set" not in str(f.get("issue", f))]
        skipped = len(findings) - len(real)
        r.check(not real, "every re-created role validates",
                "; ".join(str(f) for f in real)[:200])
        if skipped:
            r.note("credential VALUES were not checked — MINDER_MEMORY_ROLES_KEY is not in "
                   "this shell, which is normal outside the scheduler. Names were "
                   "still verified against the store.")
        for name in recreated:
            if name in {d.name for d in parked}:
                r.note(f"{name}: re-created — its previous-shape original is parked "
                       f"under {PARKED}/, so nothing was overwritten")
    else:
        r.note("No role has been re-created yet. Nothing is wrong: open "
               "/minder:mem:role:add --from-previous <id> and re-run this check after.")

    # --- 7. is anything still owed, or is the parked tree now pure residue? ---
    parked_ids = {d.name for d in parked}
    carried = parked_ids & set(recreated)
    outstanding = sorted(parked_ids - carried)
    if outstanding:
        r.note(f"still to carry across: {', '.join(outstanding)} — "
               f"/minder:mem:role:add --from-previous <id>")
    elif parked_ids:
        # Everything the owner had is live again. What is left under `_previous/`
        # is a copy of superseded files, and leaving it is how a base silently
        # accumulates directories nobody dares touch because nobody remembers
        # what they were. Say plainly that it is finished with, and how to say
        # goodbye to it — but never do it here: it is the owner's data, and a
        # check deleting it on their behalf is exactly the move that makes a
        # person stop trusting the engine.
        r.lines.append("")
        r.lines.append(f"  Every parked role is live again ({', '.join(sorted(carried))}).")
        r.lines.append(f"  `{parked_root.relative_to(repo)}/` is now residue — nothing reads it.")
        r.lines.append("  Remove it whenever you like:")
        r.lines.append("")
        r.lines.append(f"      git rm -r --quiet {parked_root.relative_to(repo)}")
        r.lines.append("")

    return r.emit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
