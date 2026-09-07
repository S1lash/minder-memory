#!/usr/bin/env python3
"""Post-update self-check — prove from the filesystem what the update should have done.

minder-memory-rebrand: keep-legacy-tokens — the former names in this file are
what it looks FOR. They are the check's subject, not a surface that missed a
rename, which is why this file is also on every allowed-residue list.

Why this exists as a script and not as prose in a skill. What an update gets
wrong is usually an ABSENCE — a rule that stopped loading, a skill nothing
resolves, a link pointing at a name that no longer exists. Nothing in the tree
announces an absence, and every artefact still looks correct. So the proof has
to be gathered deliberately, by the same run that made the change, and it has
to be the same proof every time: a probe described in a prompt is a probe that
drifts, and one whose literals must survive a rename cannot live in a file the
rename rewrites.

Each probe answers one question and reports `{probe, status, evidence}`:

  ok    — the answer is what it must be
  fail  — it is not, and that is actionable
  skip  — the question could not be asked here (no remote ref fetched, no
          harness home, no roles configured). A skip is never a pass in
          disguise: it says so, with the reason.

Exit codes: 0 every probe ok or skipped · 1 at least one failed · 2 the check
could not run at all (not a repository, no `integrations/VERSION`).

Usage:
  python3 scripts/check_update.py
  python3 scripts/check_update.py --json
  python3 scripts/check_update.py --remote upstream --branch main --before HEAD~1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import ownership  # noqa: E402
from lib.portable import configure_std_streams  # noqa: E402

# --------------------------------------------------------------------------- #
# What the update must have produced
# --------------------------------------------------------------------------- #

LEGACY_TOKEN = "ztn"
LEGACY_MARKER = "MINDER-ZTN"
CURRENT_MARKER = "MINDER-MEMORY BEGIN"

SKILL_PREFIX = "minder-mem-"
SKILL_COUNT = 20

REQUIRED_HARNESS_PATHS: tuple[str, ...] = (
    "rules/minder-memory.md",
    "rules/minder-memory-engine-doctrine.md",
    "agents/minder-mem-role.md",
    "commands/minder/mem/recap.md",
    "commands/minder/mem/search.md",
)
HARNESS_SUBDIRS: tuple[str, ...] = ("skills", "rules", "commands", "agents")

VERSION_FILE = "integrations/VERSION"
DASHBOARD = "zettelkasten/minder-memory.md"
LEGACY_DASHBOARD = "zettelkasten/minder-ztn.md"
LEDGER = ".engine-migrations.jsonl"
CLARIFICATIONS = "zettelkasten/_system/state/CLARIFICATIONS.md"
SECRETS = "zettelkasten/_system/state/secrets.enc.json"
ROLES_RUNNER = "zettelkasten/_system/scripts/roles_run.py"
BASE_DIR = "zettelkasten"

# The one place `_sources/` legitimately moves on an update: the template the
# engine ships there. Anything else under it is the owner's recording.
SOURCES_ROOT = "zettelkasten/_sources"
SOURCES_ENGINE_PREFIX = "zettelkasten/_sources/inbox/describe-me/"

# The exclusion set of `docs/upgrade-1.0.0.md` row 7 — the places where the
# former name is the subject of the line and is meant to stay. Kept here as
# data so the checklist and the check cannot drift into two different answers.
RESIDUE_EXCLUDE: tuple[str, ...] = (
    ":!zettelkasten/_sources",
    ":!docs/CHANGELOG.md",
    ":!zettelkasten/5_meta/DECISION_LOG.md",
    ":!scripts/migrations",
    ":!scripts/check_update.py",
    ":!zettelkasten/_system/scripts/tests",
    ":!integrations/claude-code/rules/minder-memory.md",
    ":!.engine-manifest.yml",
    ":!integrations/obsidian/seed.sh",
    ":!platform",
    ":!docs/upgrade-1.0.0.md",
    ":!zettelkasten/5_meta/help/CHANGELOG.md",
    # The queue is where the engine RAISES a former name with the owner — an
    # item that quotes one is the mechanism working, not a surface that missed
    # a rename.
    ":!zettelkasten/_system/state/CLARIFICATIONS.md",
    # A pre-refresh backup of the vault help holds what the docs said before;
    # it exists precisely so the former wording survives.
    ":!zettelkasten/5_meta/help/.pre-refresh-backup",
    # The credential store is NEVER_TOUCH by design: a key there is the owner's
    # name for a service, and the rename that moved one side of that pair and
    # not the other is exactly the defect the engine now refuses to repeat.
    ":!zettelkasten/_system/state/secrets.enc.json",
)

# The two rename opt-outs. A line carrying LINE_KEEP is written as it is on
# purpose; a file carrying FILE_KEEP is exempt whole. Both are therefore NOT
# residue, and a residue probe that counted them would train its reader to
# ignore it.
#
# Their home is the rename map, `scripts/migrations/_032_minder_memory_rebrand.py`
# (`LINE_KEEP` / `FILE_KEEP`). They are restated here rather than imported
# because this check is permanent and that module is a migration: when the
# chain floor moves past 032 the module is retired, and an import of it would
# take this check down with it — on a clone where nothing else was wrong.
# `test_check_update.py` asserts the two strings still equal the map's for as
# long as the map exists, so the copy cannot drift silently.
LINE_KEEP = "rebrand:keep"
FILE_KEEP = "minder-memory-rebrand: keep-legacy-tokens"

# Ownership is not restated here. `lib.ownership` is the one home of «is this
# name the engine's or the owner's» — folders and repositories in any alphabet,
# credential names a role declares or the store holds, harness entries the
# engine actually shipped, and which paths are the owner's to write. Every
# consumer imports it; seven walkthroughs' worth of defects were the same rule
# drawn differently in three files.

# What 1.0.0's map did before it learned the distinction: an owner's own
# repository or folder rewritten to a path that does not exist. Found by reading
# what the SAME file said before the rename migration ran — nothing in the tree
# afterwards betrays it, because the damaged line reads plausibly.
# `minder-minder-memory-<tail>` is the same damage in that release's doubled
# shape.
_RENAMED_OWN_NAME_RE = re.compile(
    r"(?<![\w-])(?:minder[-_.])?minder[-_.]memory[-_.][^\W_][\w-]*")

# The token a match sits in, so «is this a path?» can be asked of it.
_TOKEN_CHARS = re.compile(r"[^\s`'\"()\[\],;<>|]+")
# The ledger line whose first appearance dates the rename migration.
_LEDGER_MARK = "032-minder-memory"

MIGRATIONS_REQUIRED: tuple[str, ...] = (
    "031-minder-memory-harness-wiring.sh",
    "032-minder-memory-owner-surfaces.sh",
)

OK, FAIL, SKIP = "ok", "fail", "skip"


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #

def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude"))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _read(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""


def _result(probe: str, status: str, evidence: str) -> dict:
    return {"probe": probe, "status": status, "evidence": evidence}


# --------------------------------------------------------------------------- #
# probes — the clone
# --------------------------------------------------------------------------- #

def probe_version(repo: Path, remote: str, branch: str) -> dict:
    local = _read(repo / VERSION_FILE).strip()
    shown = _git(repo, "show", f"{remote}/{branch}:{VERSION_FILE}")
    if shown.returncode != 0:
        return _result("version", SKIP,
                       f"{remote}/{branch} is not fetched here — cannot compare (local {local})")
    upstream = shown.stdout.strip()
    if local == upstream:
        return _result("version", OK, f"{VERSION_FILE} is {local}, matching {remote}/{branch}")
    return _result("version", FAIL,
                   f"{VERSION_FILE} is {local} but {remote}/{branch} ships {upstream} — "
                   "the checkout did not land what it reported")


def probe_conflict_markers(repo: Path) -> dict:
    found = _git(repo, "grep", "-In", "-e", "^<<<<<<<", "-e", "^>>>>>>>", "--", ".")
    if found.returncode == 1:
        return _result("conflict-markers", OK, "no conflict marker in a tracked file")
    if found.returncode != 0:
        return _result("conflict-markers", SKIP, "git grep could not run")
    hits = [ln for ln in found.stdout.splitlines() if ln.strip()]
    return _result("conflict-markers", FAIL,
                   f"{len(hits)} conflict marker line(s): " + "; ".join(hits[:5]))


def probe_clone_residue(repo: Path) -> dict:
    """Files still carrying the former name outside the places it belongs.

    Matched line by line, not file by file, because the two rename opt-outs are
    what make a hit legitimate: a line carrying LINE_KEEP is written that way on
    purpose, and a file carrying FILE_KEEP is exempt whole. Counting either as
    residue would put a permanent failure in front of the reader, and a probe
    that always fails is a probe nobody reads.
    """
    found = _git(repo, "grep", "-Iin", "-e", LEGACY_TOKEN, "-e", "ЗТН", "--", ".",
                 *RESIDUE_EXCLUDE)
    if found.returncode == 1:
        return _result("clone-residue", OK,
                       "no file outside the allowed set still carries the former name")
    if found.returncode != 0:
        return _result("clone-residue", SKIP, "git grep could not run")
    counts: dict[str, int] = {}
    own = 0
    for line in found.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path, _lineno, text = parts
        if LINE_KEEP in text:
            continue
        # The owner's own names — a repository, a folder, a credential — are
        # kept BY DESIGN, so their spans come out of the line before what is
        # left is judged.
        found = ownership.own_name_spans(text, repo / BASE_DIR)
        stripped = text
        for span_start, span_end in reversed(found):
            stripped = stripped[:span_start] + stripped[span_end:]
        own += len(found)
        if not re.search(r"ztn|ЗТН", stripped, re.IGNORECASE):
            continue
        counts[path] = counts.get(path, 0) + 1
    files = sorted(p for p in counts if FILE_KEEP not in _read(repo / p))
    kept = (f"; {own} line{'' if own == 1 else 's'} name your own repository, folder or "
            "credential — kept" if own else "")
    if not files:
        return _result("clone-residue", OK,
                       "nothing outside the allowed set still carries the former name" + kept)
    return _result("clone-residue", FAIL,
                   f"{len(files)} file(s) still carry the former name: "
                   + ", ".join(files[:8]) + kept)


def pre_032_commit(repo: Path) -> str | None:
    """The commit the clone stood at before the rename migration ran.

    Dated by the ledger rather than by a tag or a version file: the ledger line
    is written by the runner at the moment the migration is applied, so its
    first appearance is the update that ran it, whatever the clone did before
    or since. The answer is that commit's PARENT — the last state of the tree
    the migration had not yet touched.
    """
    log = _git(repo, "log", "--reverse", "--format=%H", "-S", _LEDGER_MARK,
               "--", LEDGER)
    if log.returncode != 0:
        return None
    shas = [ln.strip() for ln in log.stdout.splitlines() if ln.strip()]
    if not shas:
        return None
    parent = _git(repo, "rev-parse", "--verify", shas[0] + "^")
    if parent.returncode != 0:
        return None
    return parent.stdout.strip()


def _renamed_own_names(text: str, root: Path | None = None) -> list[tuple[int, str, str]]:
    """(line number, matched token, whole line) for every renamed own name in `text`.

    No introducer test. There was one — a name counted only when a path, a key,
    a quote or a wikilink introduced it, so that the product merely being TALKED
    ABOUT in prose was not read as a thing that must exist. That guard is the
    right one when nothing else can settle the question.

    Here something else can. Every caller of this function is comparing against
    the pre-rename text, and that text is the evidence: if the line before the
    rename carried a name `lib.ownership` claims for the owner, and the line
    after carries its renamed form, the name was theirs and the path is now
    dead — whatever punctuation happens to sit in front of it. Requiring an
    introducer as well threw away real damage written the way people actually
    write, «сделал копию в minder-ztn-иванов рядом с проектом», and the owner
    was told their clone was clean.
    """
    out: list[tuple[int, str, str]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        for match in _RENAMED_OWN_NAME_RE.finditer(line):
            token = ""
            for candidate in _TOKEN_CHARS.finditer(line):
                if candidate.start() <= match.start() < candidate.end():
                    token = candidate.group(0)
                    break
            if ownership.is_engine_owned_name(token, root):
                continue
            out.append((index, match.group(0), line.rstrip()))
    return out


def _renames_by_map(repo: Path, ref: str) -> tuple[dict[str, str], str]:
    """`new -> old`, computed EXACTLY by inverting the rename's own path map.

    Similarity detection cannot be relied on here, and the reason is structural
    rather than a matter of tuning the threshold. An ordinary note carries the
    product's name in its title, its frontmatter slug, its tags and every
    command line it mentions; a product rename rewrites all of those at once,
    and what survives is only the owner's own prose. A real one measured 28 %
    against its predecessor — below any threshold that would not also pair
    unrelated files.

    The rename map, on the other hand, is a pure function: apply it to every
    path in the pre-rename tree and the one that lands on `rel` IS its
    predecessor. No heuristic, no threshold.

    The map lives in a migration, so the import is guarded: when the chain floor
    moves past it the module is gone, and the caller falls back to similarity
    with the reason attached rather than silently reporting fewer findings.
    """
    listed = _git(repo, "ls-tree", "-r", "--name-only", ref)
    if listed.returncode != 0:
        return {}, "the pre-rename tree could not be listed"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "migrations"))
        from _032_minder_memory_rebrand import rebrand_path  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — a retired migration is not an error here
        return {}, "the rename map has been retired, so predecessors are matched by similarity"
    out: dict[str, str] = {}
    for old in listed.stdout.splitlines():
        old = old.strip()
        if not old:
            continue
        try:
            new = rebrand_path(old)
        except Exception:  # noqa: BLE001
            continue
        if new != old:
            out[new] = old
    return out, ""


def _renames_since(repo: Path, ref: str) -> dict[str, str]:
    """`new -> old` for every file git sees renamed between `ref` and HEAD.

    The similarity answer. 30 %: a note whose body was rewritten by a product
    rename keeps well under half its lines, and git's default 50 % then reports
    the move as a delete plus an add.
    """
    diff = _git(repo, "diff", "--name-status", "-M30%", "--diff-filter=R", ref, "HEAD")
    if diff.returncode != 0:
        return {}
    out: dict[str, str] = {}
    for line in diff.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            out[parts[2]] = parts[1]
    return out


_TREE_CACHE: dict[tuple[str, str], frozenset[str]] = {}


def _tree_paths(repo: Path, ref: str) -> frozenset[str]:
    key = (str(repo), ref)
    if key not in _TREE_CACHE:
        listed = _git(repo, "ls-tree", "-r", "--name-only", ref)
        paths = frozenset(ln.strip() for ln in listed.stdout.splitlines() if ln.strip()) \
            if listed.returncode == 0 else frozenset()
        _TREE_CACHE[key] = paths
    return _TREE_CACHE[key]


def _own_name_predecessor(repo: Path, before: str, rel: str) -> str | None:
    """The path this file had before the rename, if the pre-rename tree had it.

    Exact and first, ahead of both the map inversion and similarity. The
    candidate spellings come from `lib.ownership.former_spellings` — the one
    home for «what could this have been called» — and the pre-rename TREE
    decides between them. No threshold, no inference: did it exist.
    """
    tree = _tree_paths(repo, before)
    for match in _RENAMED_OWN_NAME_RE.finditer(rel):
        for was in ownership.former_spellings(match.group(0)):
            candidate = rel[:match.start()] + was + rel[match.end():]
            if candidate != rel and candidate in tree:
                return candidate
    return None


def find_own_name_file_renames(repo: Path, before: str) -> list[dict]:
    """Files whose OWN NAME an earlier release renamed.

    The line-level finder answers «this path inside a file points nowhere». This
    one answers the same question one level up: the FILE is the thing that was
    named, and every `id:` and wikilink that pointed at it now names something
    the owner never chose. One finding per file, never a rewrite — whether to
    move it back or keep the new name is theirs, and both are fine as long as
    the file and its links agree.
    """
    listed = _git(repo, "ls-files", "-z", "--", ".", ":!zettelkasten/_sources", *RESIDUE_EXCLUDE)
    if listed.returncode != 0:
        return []
    out: list[dict] = []
    for rel in [p for p in listed.stdout.split("\0") if p.strip()]:
        if not ownership.in_owner_space(rel, repo):
            continue
        if not _RENAMED_OWN_NAME_RE.search(Path(rel).name):
            continue
        if ownership.is_engine_owned_name(rel, repo):
            continue
        predecessor = _own_name_predecessor(repo, before, rel)
        if not predecessor:
            continue
        # Was the FORMER name the owner's at all? `zettelkasten/minder-ztn.md`
        # is the dashboard — the engine renamed its own file, on purpose, and
        # reporting that as damage sends the owner to undo the update. The line
        # finder has asked this since 1.0.8; this one had not, and only a dot
        # tail made the gap visible.
        if not ownership.own_name_spans(Path(predecessor).name, repo / BASE_DIR):
            continue
        out.append({"path": rel, "line": 0, "text": rel, "before": predecessor,
                    "name": Path(predecessor).name, "kind": "file-name"})
    return out


def find_own_name_damage(repo: Path, before: str) -> list[dict]:
    """Names the rename turned into a path that does not exist.

    Owner space only. An engine file cannot hold an owner's directory name —
    everything in it was renamed by the engine, on purpose — and reading one as
    an owner's path is what made this fail on every clone.

    One home for the detection: the post-update check reports it, and migration
    `033` raises it with the owner. The migration imports THIS function rather
    than restating it — a migration may import a permanent script, never the
    other way round.
    """
    listed = _git(repo, "ls-files", "-z", "--", ".",
                  ":!zettelkasten/_sources", *RESIDUE_EXCLUDE)
    if listed.returncode != 0:
        return []
    # Two ways to find a file's predecessor, and they cover different cases, so
    # both are consulted per file rather than one replacing the other.
    #
    # Inverting the map is exact — but only for a name the map MOVES. A note
    # whose own file name is the owner's is left alone by today's map, so
    # inverting it yields nothing, even though an earlier release did move it.
    # That is precisely the file most likely to hold the damage, so similarity
    # is not just a fallback for a retired map: it is what answers the case the
    # exact method cannot see.
    renames, degraded = _renames_by_map(repo, before)
    similar = _renames_since(repo, before)
    findings: list[dict] = []
    for rel in [p for p in listed.stdout.split("\0") if p.strip()]:
        if not ownership.in_owner_space(rel, repo):
            continue
        current = _read(repo / rel)
        if not current:
            continue
        candidates = _renamed_own_names(current, repo)
        if not candidates:
            continue
        # The pre-rename text lives under the file's OLD path when the rename
        # moved the file too — which is exactly the case for a note whose own
        # name carried the product, and where an owner's path is most likely to
        # have been written down.
        shown = _git(repo, "show", f"{before}:{rel}")
        if shown.returncode != 0:
            for predecessor in (_own_name_predecessor(repo, before, rel),
                                renames.get(rel), similar.get(rel)):
                if not predecessor:
                    continue
                shown = _git(repo, "show", f"{before}:{predecessor}")
                if shown.returncode == 0:
                    break
        if shown.returncode != 0:
            continue  # the file did not exist before the migration — nothing to compare
        original = shown.stdout
        for lineno, matched, line in candidates:
            # What the name could have been is `lib.ownership`'s answer; which
            # of those it WAS is decided by the pre-rename text, the only
            # authority that cannot be wrong. Paired by proximity after that:
            # several lines may carry the owner's name, and quoting the first
            # one as «what it was» shows them a line that never moved.
            picked = None
            for was in ownership.former_spellings(matched):
                # Was the FORMER name the owner's at all? `~/minder-ztn-env` is
                # the engine's own slug, and the engine renaming its own name is
                # not damage. The same one home that decides the map may touch a
                # name decides whether its rename is worth reporting.
                if not ownership.own_name_spans(was, repo / BASE_DIR):
                    continue
                matcher = re.compile(re.escape(was) + r"(?![\w-])", re.IGNORECASE)
                matches = [(index, text.rstrip())
                           for index, text in enumerate(original.splitlines(), start=1)
                           if matcher.search(text)]
                if matches:
                    picked = (was, min(matches, key=lambda pair: abs(pair[0] - lineno))[1])
                    break
            if picked is None:
                continue
            was, before_line = picked
            findings.append({"path": rel, "line": lineno, "text": line,
                             "before": before_line, "name": was})
    return findings


def own_name_rows(findings: list[dict]) -> list[str]:
    """One row per damaged LINE, in the order found. The one home for both readers.

    Two damaged names on the same line are the same line, not two problems. The
    check and migration 033 render the same findings and drifted apart on this:
    033 deduped, the check did not, so its list filled with repeats and — being
    truncated to five — never reached the shapes that mattered. A count of
    findings is not a count of lines either, and the two disagree exactly when
    the duplicates are worst.
    """
    rows: list[str] = []
    seen: set = set()
    for f in findings:
        key = (f["path"], f["line"], f["text"].strip(), f["before"].strip())
        if key in seen:
            continue
        seen.add(key)
        if f.get("kind") == "file-name":
            rows.append(f"{f['path']} — your own note NAME was renamed; it was "
                        f"{f['before']}")
        else:
            rows.append(f"{f['path']}:{f['line']} now «{f['text'].strip()}», "
                        f"was «{f['before'].strip()}»")
    return rows


def probe_own_name_damage(repo: Path) -> dict:
    before = pre_032_commit(repo)
    if before is None:
        return _result("own-name-damage", SKIP,
                       "the ledger was never committed here — there is no before-state to read")
    findings = find_own_name_damage(repo, before)
    # A file whose own NAME was renamed is the same question one level up: the
    # note is still readable, but every `id:` and wikilink that named it now
    # names something the owner never chose.
    findings += find_own_name_file_renames(repo, before)
    findings.sort(key=lambda f: (f["path"], f["line"]))
    if not findings:
        return _result("own-name-damage", OK,
                       "no name of yours was renamed into a path that does not exist")
    rows = own_name_rows(findings)
    shown = "; ".join(rows[:5])
    more = (f" …and {len(rows) - 5} more — migration 033 files the full list as a "
            f"clarification in {CLARIFICATIONS}" if len(rows) > 5 else "")
    return _result("own-name-damage", FAIL,
                   f"{len(rows)} line(s) where your own name was renamed by an earlier "
                   f"release into a path that does not exist — restore by hand, nothing here "
                   f"rewrites them: {shown}{more}")


def probe_dashboard(repo: Path) -> dict:
    current = (repo / DASHBOARD).is_file()
    legacy = (repo / LEGACY_DASHBOARD).exists()
    if current and not legacy:
        return _result("dashboard", OK, f"{DASHBOARD} present, {LEGACY_DASHBOARD} gone")
    if not (repo / BASE_DIR).is_dir():
        return _result("dashboard", SKIP, "no base directory in this clone")
    missing = [] if current else [f"{DASHBOARD} is missing"]
    if legacy:
        missing.append(f"{LEGACY_DASHBOARD} still exists")
    return _result("dashboard", FAIL, "; ".join(missing))


def probe_sources(repo: Path) -> dict:
    if not (repo / SOURCES_ROOT).is_dir():
        return _result("sources-untouched", SKIP, "no _sources/ in this clone")
    status = _git(repo, "status", "--porcelain", "-uall", "--", SOURCES_ROOT)
    if status.returncode != 0:
        return _result("sources-untouched", SKIP, "git status could not run")
    stray = []
    for line in status.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if not path.startswith(SOURCES_ENGINE_PREFIX):
            stray.append(path)
    if not stray:
        return _result("sources-untouched", OK,
                       "nothing changed under _sources/ but the engine-shipped template")
    return _result("sources-untouched", FAIL,
                   f"{len(stray)} path(s) changed under _sources/: " + ", ".join(stray[:8]))


def probe_ledger(repo: Path) -> dict:
    text = _read(repo / LEDGER)
    if not text.strip():
        return _result("migration-ledger", SKIP, f"no {LEDGER} in this clone")
    outcome: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            outcome[name] = str(entry.get("outcome"))
    unapplied = [n for n in MIGRATIONS_REQUIRED if outcome.get(n) != "applied"]
    if not unapplied:
        return _result("migration-ledger", OK, "031 and 032 are recorded applied")
    return _result("migration-ledger", FAIL,
                   "not recorded applied: "
                   + ", ".join(f"{n} ({outcome.get(n, 'absent')})" for n in unapplied))


def probe_roles(repo: Path, before: str | None) -> dict:
    runner = repo / ROLES_RUNNER
    if not runner.is_file():
        return _result("roles", SKIP, "no roles runner in this clone")
    ran = subprocess.run(
        [sys.executable, str(runner), "due", "--base", BASE_DIR, "--repo", "."],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if ran.returncode != 0:
        return _result("roles", FAIL,
                       "roles_run.py due exited "
                       f"{ran.returncode}: {(ran.stderr or ran.stdout).strip()[:200]}")
    try:
        rows = json.loads(ran.stdout or "[]")
    except json.JSONDecodeError:
        rows = None
    if rows is None or not isinstance(rows, list):
        return _result("roles", FAIL, "roles_run.py due did not print a role list")
    nameless = [r for r in rows if not isinstance(r, dict) or not r.get("status")]
    if nameless:
        return _result("roles", FAIL, f"{len(nameless)} role(s) reported without a status")
    return _result("roles", OK, f"{len(rows)} role(s) listed with a status")


def _store_identity_note(repo: Path, before: str | None) -> str:
    """Whether the store's bytes moved — evidence beside the answer, not the answer.

    A store that differs from the pre-rename tree is not by itself a fault: a
    clone that passed through the release which renamed BOTH the declaration
    and the store is perfectly consistent and needs no repair. So the byte
    comparison is reported and never decides the probe.
    """
    baseline = before or pre_032_commit(repo)
    if baseline is None:
        return "no pre-rename commit to compare its bytes against"
    if _git(repo, "cat-file", "-e", f"{baseline}:{SECRETS}").returncode != 0:
        return "it did not exist before the rename"
    moved = _git(repo, "diff", "--quiet", baseline, "--", SECRETS)
    if moved.returncode == 0:
        return "byte-identical to before the rename"
    if moved.returncode == 1:
        return "its bytes differ from before the rename, which is fine when both sides moved together"
    return "git could not compare its bytes"


def probe_credential_store(repo: Path, before: str | None) -> dict:
    """Does every credential every role declares actually resolve in the store?

    That is the question, and byte-identity is not it. A credential name is the
    OWNER's name for a service: the role declares it and the store holds it
    under that spelling, and what breaks a role is the two sides disagreeing —
    not either side having changed. A clone that took a release which renamed
    both is consistent and needs nothing; a clone where only one side moved
    fails at its next tick with «declared secret X is not in the credential
    store», naming a variable the owner never wrote.

    So the engine's own preflight answers it, and the byte comparison rides
    along as evidence.
    """
    runner = repo / ROLES_RUNNER
    if not runner.is_file():
        return _result("credential-store", SKIP,
                       "no roles runner in this clone, so no declaration to resolve")
    if not (repo / SECRETS).is_file():
        return _result("credential-store", SKIP, "no credential store in this clone")
    ran = subprocess.run(
        [sys.executable, str(runner), "validate", "--base", BASE_DIR, "--repo", "."],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        report = json.loads(ran.stdout or "{}")
    except json.JSONDecodeError:
        return _result("credential-store", SKIP,
                       "the roles preflight did not return a report")
    findings = report.get("findings") or []
    # Only a finding that names a SECRET is about the pair under test. One
    # without it is about the environment doing the checking — no decryption
    # key here, which is normal and not the owner's problem to fix.
    unresolved = [f for f in findings
                  if f.get("secret") and "credential store" in str(f.get("issue", ""))]
    note = _store_identity_note(repo, before)
    if unresolved:
        named = "; ".join(f"{f.get('role')} declares {f.get('secret')}" for f in unresolved[:5])
        return _result("credential-store", FAIL,
                       f"{len(unresolved)} declared credential(s) do not resolve in the store — "
                       f"the role fails at its next tick with a lookup error: {named} ({note})")
    return _result("credential-store", OK,
                   f"every credential every role declares resolves in the store ({note})")


# --------------------------------------------------------------------------- #
# probes — the harness home
# --------------------------------------------------------------------------- #

def probe_managed_block(home: Path) -> dict:
    claude_md = home / "CLAUDE.md"
    if not claude_md.is_file():
        return _result("managed-block", SKIP, f"no {claude_md}")
    text = _read(claude_md)
    current = text.count(CURRENT_MARKER)
    legacy = text.count(LEGACY_MARKER)
    if current == 1 and legacy == 0:
        return _result("managed-block", OK, "exactly one current block, no former marker")
    return _result("managed-block", FAIL,
                   f"{current} current block marker(s) and {legacy} former marker(s) "
                   f"in {claude_md}")


def probe_harness_paths(home: Path) -> dict:
    if not home.is_dir():
        return _result("harness-paths", SKIP, f"no harness home at {home}")
    missing = [rel for rel in REQUIRED_HARNESS_PATHS if not (home / rel).exists()]
    if not missing:
        return _result("harness-paths", OK,
                       f"all {len(REQUIRED_HARNESS_PATHS)} rule / command / agent paths resolve")
    return _result("harness-paths", FAIL, "does not resolve: " + ", ".join(missing))


def probe_skill_count(home: Path) -> dict:
    d = home / "skills"
    if not d.is_dir():
        return _result("skill-count", SKIP, f"no {d}")
    found = sorted(p.name for p in d.iterdir() if p.name.startswith(SKILL_PREFIX))
    if len(found) == SKILL_COUNT:
        return _result("skill-count", OK, f"{SKILL_COUNT} skills linked")
    return _result("skill-count", FAIL,
                   f"{len(found)} skills linked, expected {SKILL_COUNT}")


def probe_legacy_harness_entries(home: Path) -> dict:
    """Anything named after the former product under the harness home.

    A hit is not a link the migration overlooked — it is a stub of the old
    wiring sitting beside the new one, and a session that resolves it loads a
    rule or a skill that no longer exists.
    """
    if not home.is_dir():
        return _result("legacy-harness-entries", SKIP, f"no harness home at {home}")
    hits: list[str] = []
    theirs: list[str] = []
    for sub in HARNESS_SUBDIRS:
        d = home / sub
        if not d.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
            for name in list(dirnames) + list(filenames):
                if LEGACY_TOKEN not in name.lower():
                    continue
                if ownership.is_engine_legacy_harness_entry(name, sub):
                    hits.append(os.path.join(dirpath, name))
                else:
                    theirs.append(os.path.join(dirpath, name))
    mine = (f"; {len(theirs)} entr(y/ies) carrying that word are yours, not the "
            "engine's, and were left alone" if theirs else "")
    if not hits:
        return _result("legacy-harness-entries", OK,
                       "no harness entry the engine shipped under its former name remains" + mine)
    return _result("legacy-harness-entries", FAIL,
                   f"{len(hits)} leftover entr(y/ies): " + ", ".join(sorted(hits)[:8]) + mine)


def probe_foreign_dangling(home: Path, repo: Path) -> dict:
    """Dangling links that are not ours — reported, never touched.

    Always `ok`: somebody else's broken link is not this update's business, and
    a check that fails on it would teach its reader to ignore failures.
    """
    if not home.is_dir():
        return _result("foreign-dangling-links", SKIP, f"no harness home at {home}")
    repo = repo.resolve()
    foreign: list[str] = []
    for sub in HARNESS_SUBDIRS:
        d = home / sub
        if not d.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
            for name in list(dirnames) + list(filenames):
                entry = Path(dirpath) / name
                if not entry.is_symlink() or entry.exists():
                    continue
                try:
                    raw = os.readlink(entry)
                except OSError:
                    continue
                target = Path(raw) if os.path.isabs(raw) else entry.parent / raw
                target = Path(os.path.normpath(target))
                if target == repo or repo in target.parents:
                    continue
                foreign.append(f"{entry} -> {raw}")
    if not foreign:
        return _result("foreign-dangling-links", OK, "no foreign dangling link")
    return _result("foreign-dangling-links", OK,
                   f"{len(foreign)} dangling link(s) belonging to something else, left alone: "
                   + ", ".join(sorted(foreign)[:8]))


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def run(repo: Path, home: Path, *, remote: str, branch: str, before: str | None) -> list[dict]:
    return [
        probe_version(repo, remote, branch),
        probe_conflict_markers(repo),
        probe_clone_residue(repo),
        probe_own_name_damage(repo),
        probe_dashboard(repo),
        probe_sources(repo),
        probe_ledger(repo),
        probe_roles(repo, before),
        probe_credential_store(repo, before),
        probe_managed_block(home),
        probe_harness_paths(home),
        probe_skill_count(home),
        probe_legacy_harness_entries(home),
        probe_foreign_dangling(home, repo),
    ]


def render(results: list[dict], repo: Path, home: Path) -> str:
    lines = [f"post-update check — clone {repo}, harness home {home}", ""]
    for r in results:
        mark = {OK: "ok  ", FAIL: "FAIL", SKIP: "skip"}[r["status"]]
        lines.append(f"  [{mark}] {r['probe']}: {r['evidence']}")
    failed = [r["probe"] for r in results if r["status"] == FAIL]
    skipped = [r["probe"] for r in results if r["status"] == SKIP]
    lines.append("")
    if failed:
        lines.append(f"{len(failed)} probe(s) failed: " + ", ".join(failed))
    else:
        lines.append("every probe that could be asked came back right"
                     + (f"; {len(skipped)} not applicable here" if skipped else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", default=".", help="the clone to check (default: cwd)")
    ap.add_argument("--remote", default=os.environ.get("ENGINE_SYNC_REMOTE") or "upstream")
    ap.add_argument("--branch", default=os.environ.get("ENGINE_SYNC_BRANCH") or "main")
    ap.add_argument("--before", default=None,
                    help="the commit the update started from, for before/after comparisons")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)

    repo = Path(args.repo_root).resolve()
    top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if top.returncode != 0 or not top.stdout.strip():
        print(f"check_update: {repo} is not a git clone — nothing to check", file=sys.stderr)
        return 2
    repo = Path(top.stdout.strip()).resolve()
    if not (repo / VERSION_FILE).is_file():
        print(f"check_update: {repo} carries no {VERSION_FILE} — this is not an engine clone",
              file=sys.stderr)
        return 2

    home = claude_home()
    results = run(repo, home, remote=args.remote, branch=args.branch, before=args.before)
    if args.json:
        print(json.dumps({"repo": str(repo), "home": str(home), "probes": results},
                         ensure_ascii=False, sort_keys=True, indent=1))
    else:
        print(render(results, repo, home))
    return 1 if any(r["status"] == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
