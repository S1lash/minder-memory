#!/usr/bin/env python3
"""The write boundary — snapshots, attribution, remedy, and the leak scan.

`writes:` is a checked contract here, not an inability elsewhere: a role runs
with a shell and could write anywhere, so the guard compares what actually
changed against the role's allowlist and repairs the difference.

**Snapshots carry content digests, not just paths.** Paths alone cannot
attribute a modification: role A creates `…/state/x.md`, role B's snapshot
records it as dirty, B edits it, and git emits the identical status line — a
path-set difference removes it at step one and B's edit is invisible
forever. The digest is what makes attribution real.

Two snapshots, two jobs. The **role snapshot** is captured immediately
before each role; it drives attribution — a path is touched by this role
when its (presence, digest) differs between that snapshot and the current
state — and it is what the remedy branches on. The **tick baseline** is
captured once, before the first role, and its job is narrower: it labels an
unrestorable path in the REPORT as the owner's uncommitted work or an
earlier role's output. Nothing about safety depends on it.

**The remedy branches on RESTORABILITY, not on ownership.** The question is
not "whose is this" — it is "can the guard put this back exactly as it was
before this role ran?" If it cannot, the alternatives are to leave it or to
destroy it, and destroying it is never right. Decided only by whether the
path appears in the role snapshot: absent and untracked → delete, it did not
exist at role start; absent and tracked → restore from the index, since
absence from a status listing means it equalled HEAD; present → report only,
because the snapshot carries a digest and git does not hold that content, so
nothing can reproduce it.

That rule replaced an ownership branch that destroyed data: role A created a
file in its own zone, role B touched it out of B's zone, and the guard
deleted it — the path was absent from the TICK baseline, so it looked
revertible, and revert of an untracked file means delete. The residual is
named rather than hidden: a role CAN modify a path that was already dirty
and the guard will report it without undoing it. A hole that is reported is
recoverable; destroyed work is not.

`git status --porcelain -uall -z`, all three flags, always. `-uall` because a
wholly new directory otherwise collapses to a single entry and the check
inspects a directory instead of files. `-z` because git C-quotes any
non-ASCII path by default, so a state file the owner named in their own
script arrives octal-escaped — `"state/\\321\\200\\320\\260…"` — fails the
prefix check, and is deleted on every run. With `-z` a rename is two
NUL-separated fields — new path, then old — not `R old -> new`, and both
paths are classified independently.

The leak scan asks the same question, because it is the same question. A
leaking in-zone file the guard can restore exactly is reverted; one it
cannot — already dirty when this role started — is reported and left on
disk, because destroying a draft to remove a credential is the cure being
worse than the disease. The tick keeps it out of the commit, so the
credential stays where the owner can see it and never reaches history.

Nothing here ever runs git with a force flag, ever removes untracked files
in bulk, or ever touches `.git/`. Reverts are per-path.

**The guard's INPUT is watched as carefully as its output.** This module's
model is «the repository is what `git status` prints», and a role with a shell
controls both what it prints and when — so the snapshot carries the surface
that decides it, and a change to any part is a finding that aborts, in the same
class as a moved HEAD:

- every `.gitignore` git can see — tracked, untracked-visible, AND
  untracked-ignored, which is the one that matters: a rule of `*` matches
  itself, so plain status reports neither it nor what it hides. `ls-files
  --cached --others`, deliberately WITHOUT `--exclude-standard`, is what lists
  all three at once;
- `core.excludesFile` at merged scope, plus a digest of what it points at — set
  globally it lives outside the repository and survives every clone of it;
- the hooks directory's **contents**, not only `core.hooksPath` — the tick runs
  `git commit` per role, so a planted hook executes in the tick's own process;
- remotes, `.git/config`, and the index flag bits, each of which redirects or
  hides without writing a file the working-tree diff would show.

**Stated limitations. Each is open, and none is closed by anything above:**

- A path outside the repository is outside `git status` entirely. A role
  that writes outside the repo is invisible here — and a SYMLINK is one route
  to that, worth naming because it does not look like one: a link created
  inside the allowed zone is reported as an ordinary in-zone write, while what
  it writes through lands wherever it points. Verified: the link is attributed
  and remedied, the file it targeted outside the repo is not. This adds no
  capability a role with a shell lacks, so there is no machinery here for it;
  what it adds is a way for «wrote in zone» to read as bounded when it is not.
  A link pointing back INTO the repository is different and is handled: git
  reports the real path, so an out-of-zone target is attributed and reverted
  normally.
- A background process outlives the check. The settle interval and the
  second snapshot catch what is still in flight; they do NOT stop a patient
  attacker, who need only wait longer than the interval. The real fix is a
  process-group kill at the dispatcher, which is not this module's to make.
- Encodings are unbounded. The scan carries the raw value plus its base64,
  hex and percent-encoded forms, which closes the common cases and raises
  the cost — it does not close the class, and no exact-match scan can.
- An in-zone write is a legal channel by design. The guard judges WHERE a
  role wrote and whether a known credential appears; it does not judge what
  the role chose to say there.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

from roles_config import parse_secrets_file, to_repo_relative

# §3.6: a value shorter than this is not scanned at all. Below the floor a
# credential is a word or a fragment, and an exact substring match on it
# would revert the owner's legitimate content on every run. The honest
# position there is "this credential cannot be leak-scanned", surfaced by
# preflight at creation rather than as a false-positive machine at 07:00.
SECRET_SCAN_MIN_LENGTH = 12

DELETED = "<deleted>"
UNREADABLE = "<unreadable>"

# What replaces a credential that reached a reported string (§ redaction).
REDACTION = "[redacted]"

# How long `check` waits before its second snapshot. Deliberately small: the
# second snapshot is the mechanism, the interval only widens the window, and
# no practical interval beats a patient attacker. The tick may raise it.
SETTLE_SECONDS = 0.25

# Ignore files whose content decides what `git status` is allowed to see.
ROOT_IGNORE = ".gitignore"
INFO_EXCLUDE = ".git/info/exclude"

# Report-only labels (§3.3). The tick baseline decides which of the first two
# a path gets; none of them changes what the guard did to it, which is nothing.
OWNER_LABEL = "owner"
ROLE_LABEL = "earlier-role"
# A path an ignore rule made invisible during the run. It is reported rather
# than restored for the same reason as the other two — the guard cannot undo
# it safely — but the reason is the path's visibility, not its content, so the
# baseline has no say and the label is assigned directly.
HIDDEN_LABEL = "ignored"

# Porcelain v1 emits `XY PATH`; a rename or a copy is followed by one more
# NUL-separated field carrying the original path.
_STATUS_PREFIX_WIDTH = 3
_RENAME_CODES = "RC"
# Porcelain's code for «this path is ignored». Never followed by a second
# NUL-separated field, so it is consumed and the loop moves on.
_IGNORED_CODE = "!!"


class SnapshotError(Exception):
    """A snapshot is not a snapshot — refused, never acted upon.

    A snapshot is JSON read back from a file in the OS temp directory: a
    crash can truncate it and another version can leave one behind. Acting on
    a shape the guard cannot read is the worse of the two failures, because
    «nothing was touched» from an unreadable snapshot reports a clean run
    over a violation. A typed refusal reaches the owner as an error; an
    `AttributeError` reaches them as a stack trace.
    """


def _validate_snapshot(snapshot, what: str) -> dict:
    """Refuse anything that is not `{head: str, entries: {str: str}}`."""
    if not isinstance(snapshot, dict):
        raise SnapshotError(f"{what} is {type(snapshot).__name__}, not a snapshot")
    head, entries = snapshot.get("head"), snapshot.get("entries")
    if not isinstance(head, str):
        raise SnapshotError(f"{what} has no string `head`")
    if not isinstance(entries, dict):
        raise SnapshotError(f"{what} has no `entries` mapping")
    for path, digest in entries.items():
        if not isinstance(path, str) or not isinstance(digest, str):
            raise SnapshotError(
                f"{what} carries a non-string entry ({path!r}: {digest!r})"
            )
    return snapshot


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git in `repo` without a shell, capturing raw bytes.

    `--literal-pathspecs` on every invocation, always. Git reads a pathspec
    as a GLOB by default, so a file the role names `*.md` — which an
    unmatched bash glob in its own script produces by accident — makes
    `ls-files` match the owner's tracked files and the remedy check out the
    wrong one, destroying uncommitted work while the offender survives.
    """
    return subprocess.run(
        ["git", "--literal-pathspecs", *args],
        cwd=str(repo),
        capture_output=True,
    )


def _decode(raw: bytes) -> str:
    """Explicit UTF-8, never the locale default — paths carry any script."""
    return raw.decode("utf-8")


def _status_scan(repo: Path) -> tuple:
    """`(changed, ignored)` — repo-relative POSIX paths, from ONE git call.

    `--ignored=matching` costs nothing extra here and buys the guard the one
    listing an ignore rule cannot suppress. It collapses a wholly-ignored
    directory to a single entry, which is what keeps the second list small
    enough to carry in every snapshot.

    Both lists come from the same invocation on purpose. Asking twice would
    let the tree move between the two answers, and a role that arranged that
    window would be reported as having hidden nothing.
    """
    proc = _git(repo, "status", "--porcelain", "-uall", "--ignored=matching", "-z")
    if proc.returncode != 0:
        raise RuntimeError(
            f"{repo}: git status failed ({_decode(proc.stderr).strip()})"
        )
    fields = _decode(proc.stdout).split("\0")
    paths: list = []
    ignored: list = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        code, path = field[:2], field[_STATUS_PREFIX_WIDTH:]
        if code == _IGNORED_CODE:
            ignored.append(path)
            continue
        paths.append(path)
        if any(char in _RENAME_CODES for char in code) and index < len(fields):
            original = fields[index]
            index += 1
            if original:
                paths.append(original)
    return paths, ignored


def _digest(path: Path) -> str:
    """SHA-256 of the file's bytes, or a sentinel."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return DELETED
    except OSError:
        return UNREADABLE
    return hashlib.sha256(data).hexdigest()


def _repo_path(repo: Path, relpath: str) -> Path:
    return repo.joinpath(*relpath.split("/"))


def _config_value(repo: Path, key: str) -> str | None:
    proc = _git(repo, "config", "--get", key)
    return _decode(proc.stdout).strip() if proc.returncode == 0 else None


def _ignore_files(repo: Path) -> list:
    """Every file whose content decides what `git status` may report.

    Listing only TRACKED `.gitignore` files misses the one that matters: a
    role creates `2_areas/.gitignore` containing `*`, which matches itself,
    so plain `git status` reports neither the rule nor the payload it hides
    and the guard's entire input goes empty while every field reads clean.

    `--cached --others` with **no `--exclude-standard`** is the whole answer,
    in one call. Dropping that flag is the point rather than an omission: with
    it, `--others` hides exactly the files the ignore rules hide, which is the
    class the self-ignoring `.gitignore` belongs to. Without it, `--others`
    lists every untracked path, ignored or not, so all three states — tracked,
    untracked-visible, untracked-ignored — arrive together.

    Asking git rather than walking the tree in python is a correctness choice
    before a speed one: the question is «what can git see», and git is the
    authority on that. Measured on a mature base the two are within noise of
    each other — both are a working-tree scan, and this runs on every snapshot,
    several times per role, so a tick pays a few seconds for it. That is the
    honest cost; it buys the one check a role cannot edit its way around.

    `.git/` never appears in the listing, so `info/exclude` is named
    explicitly.
    """
    found = set()
    proc = _git(repo, "ls-files", "--cached", "--others", "-z")
    if proc.returncode == 0:
        for name in _decode(proc.stdout).split("\0"):
            # Case-INSENSITIVE, because macOS and Windows filesystems are.
            # `.GITIGNORE` there is the same file git reads as an ignore
            # source, and an exact `== ".gitignore"` compare skipped it — so
            # the digest was never taken and the tamper was invisible while
            # the rule still hid the payload. On a case-sensitive filesystem
            # this only adds a harmless extra digest of a file git does not
            # treat as an ignore source, which is the safe direction to err.
            if name and name.rsplit("/", 1)[-1].lower() == ROOT_IGNORE:
                found.add(name)
    return sorted(found | {ROOT_IGNORE, INFO_EXCLUDE})


def _excludes_file(repo: Path) -> tuple:
    """`core.excludesFile` — its configured value and the digest of its target.

    Read from git's MERGED configuration, so a role that runs
    `git config --global core.excludesFile ...` is caught. Global scope is
    the dangerous one: it lives outside the repository, survives every clone
    of it, and silences the guard for every role and every future tick while
    leaving nothing behind in the repository to notice.
    """
    value = _config_value(repo, "core.excludesFile")
    if not value:
        return None, None
    target = Path(os.path.expanduser(value))
    if not target.is_absolute():
        target = repo / target
    return value, _digest(target)


def _hooks_digest(repo: Path) -> dict:
    """A digest per file in the effective hooks directory.

    The hooks PATH was already watched; the hooks themselves were not, and
    the tick runs `git commit` once per role. A `post-commit` planted by a
    role therefore executes inside the tick's own process — which is exactly
    where `MINDER_MEMORY_ROLES_KEY` lives — with the guard reporting a clean surface.
    Digesting the directory closes the gap without the guard ever writing
    inside `.git/`, which it is forbidden to do.
    """
    configured = _config_value(repo, "core.hooksPath")
    hooks_dir = Path(os.path.expanduser(configured)) if configured else repo / ".git" / "hooks"
    if not hooks_dir.is_absolute():
        hooks_dir = repo / hooks_dir
    if not hooks_dir.is_dir():
        return {}
    out = {}
    for entry in sorted(hooks_dir.iterdir()):
        if entry.is_file():
            # `.sample` files ship with every clone and are never executed.
            if entry.name.endswith(".sample"):
                continue
            out[entry.name] = _digest(entry)
    return out


def git_surface(repo: Path) -> dict:
    """The git CONFIGURATION a role can change without touching a file.

    The guard's whole model is «the repository is what `git status` prints».
    A role with a shell controls both what it prints and when — it can point
    `origin` at its own server, add an ignore rule that hides its payload, or
    mark an owner file assume-unchanged so edits to it are invisible to
    status, to this guard, to staging and to the owner's save. None of that
    writes a file the working-tree diff would show.

    So the snapshot carries this surface too, and any difference is a
    first-class finding.
    """
    remotes = {}
    proc = _git(repo, "config", "--get-regexp", r"^remote\..*\.url")
    if proc.returncode == 0:
        for line in _decode(proc.stdout).splitlines():
            name, _, url = line.partition(" ")
            remotes[name] = url
    flags = {}
    proc = _git(repo, "ls-files", "-v", "-z")
    if proc.returncode == 0:
        for entry in _decode(proc.stdout).split("\0"):
            if len(entry) > 2 and entry[0] != "H":
                # Anything but the ordinary `H` — lowercase means
                # assume-unchanged, `S` skip-worktree, and both hide edits.
                flags[entry[2:]] = entry[0]
    excludes_value, excludes_digest = _excludes_file(repo)
    return {
        "remotes": remotes,
        "hooks_path": _config_value(repo, "core.hooksPath"),
        "hooks": _hooks_digest(repo),
        "config": _digest(repo / ".git" / "config"),
        "ignore": {name: _digest(_repo_path(repo, name)) for name in _ignore_files(repo)},
        "excludes_file": {"value": excludes_value, "digest": excludes_digest},
        "index_flags": flags,
    }


def surface_delta(before: dict, after: dict) -> dict:
    """Fields of the git surface that differ, as `{field: {before, after}}`."""
    return {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in sorted(set(before) | set(after))
        if before.get(field) != after.get(field)
    }


def capture_snapshot(repo: Path, secrets_file: Path) -> dict:
    """`{"head": sha, "entries": {path: digest}}` for the current tree."""
    head = _git(repo, "rev-parse", "HEAD")
    entries = {}
    changed, ignored = _status_scan(repo)
    for relpath in changed:
        entries[relpath] = _digest(_repo_path(repo, relpath))
    # `None` here means the secrets file lives outside the repository, where
    # nothing this guard does can see it (rule 10).
    secrets_rel = to_repo_relative(repo, secrets_file)
    if secrets_rel is not None and secrets_file.is_file():
        # Gitignored, therefore invisible to porcelain — checked directly.
        entries[secrets_rel] = _digest(secrets_file)
    return {
        "head": _decode(head.stdout).strip(),
        "entries": entries,
        "ignored": sorted(ignored),
        "git": git_surface(repo),
    }


def newly_hidden(role_snapshot: dict, current: dict) -> list | None:
    """Paths git could see before the run and cannot see after it.

    THE question behind the whole ignore surface, asked directly instead of
    through a digest. A digest answers «did the rules change», which is a
    proxy — and a poor one, because most changes to the rules hide nothing at
    all. This answers «did anything become invisible», which is the only
    reason the guard watches the rules in the first place.

    What the caller does with the answer is ATTRIBUTE it — these paths are
    digested, scanned and reported like any other write. This is a detector
    feeding attribution, not a tripwire: it exists to close the gap where
    `git status` stops printing, so nothing here is a verdict about intent.

    Ignore rules do not apply to TRACKED files: git reports a modification to
    one whatever any rule says. So the only payload an ignore rule can hide is
    an untracked path — and a path that is ignored now while it was not
    ignored before is exactly that, whether the rule is new or the file is.
    Both readings are worth stopping for: either the role wrote something into
    a place the guard cannot look, or it made such a place.

    A set that only SHRANK hid nothing — it made more of the tree visible, not
    less. That is the ordinary case when something outside the role rewrites
    `.git/info/exclude`, and it is why the harness doing so no longer reads as
    a role attacking the guard.

    A path that was ALREADY VISIBLE when the role started is discounted,
    because `attribute` already covers it: it is in the role snapshot's
    `entries`, so it is compared by digest like any other path and reporting
    it a second time under a different label would say nothing new.

    Everything else is returned, including files the HOST created during the
    run — its own lock and runtime state, which appear here for the same
    mechanical reason a role's payload would: they did not exist when the
    role started, so nothing could have listed them. Telling the two apart is
    not possible from here and is not attempted; the caller reports both and
    restores neither, which is the only honest handling of a path whose
    author the guard does not know.

    Returns `None` — «cannot tell» — when either snapshot predates this field,
    so a caller keeps the conservative verdict rather than inferring safety
    from an absence.
    """
    before, after = role_snapshot.get("ignored"), current.get("ignored")
    if not isinstance(before, list) or not isinstance(after, list):
        return None
    was_visible = set(role_snapshot.get("entries") or {})
    candidates = set(after) - set(before)
    return sorted(
        path for path in candidates
        if path not in was_visible
        # A wholly-ignored directory collapses to one entry, so it is
        # discounted when anything under it was visible before.
        and not (path.endswith("/")
                 and any(seen.startswith(path) for seen in was_visible))
    )


def attribute(role_snapshot: dict, current: dict) -> list:
    """Paths whose (presence, digest) changed between the two snapshots."""
    before = _validate_snapshot(role_snapshot, "the role snapshot")["entries"]
    after = _validate_snapshot(current, "the current snapshot")["entries"]
    return sorted(
        path for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )


def classify(touched: list, prefixes: tuple) -> tuple:
    """Split touched paths into `(in_zone, out_of_zone)`, order preserved."""
    in_zone, out_of_zone = [], []
    for path in touched:
        covered = any(prefix.covers(path) for prefix in prefixes)
        (in_zone if covered else out_of_zone).append(path)
    return in_zone, out_of_zone


def _is_in_head(repo: Path, relpath: str) -> bool:
    """Does HEAD carry this path?

    HEAD, never the index. `git ls-files` lists INDEX entries, so a role that
    stages its own work — which the owner's own canon tells agents to do
    after every edit — reads as tracked, takes the restore branch, and is
    restored FROM ITS OWN STAGED CONTENT. The guard then reports the path in
    `reverted` while the file on disk still holds what the role wrote.
    """
    return _git(repo, "cat-file", "-e", f"HEAD:{relpath}").returncode == 0


def _restore_from_head(repo: Path, relpath: str) -> None:
    proc = _git(repo, "checkout", "HEAD", "--", relpath)
    if proc.returncode != 0:
        raise OSError(
            f"git checkout of {relpath} failed: {_decode(proc.stderr).strip()}"
        )


def _unstage(repo: Path, relpath: str) -> None:
    """Drop this path from the index, so the tick starts from a clean one.

    Without it the tick's «stage only named paths» discipline is decoration:
    the index is already dirty with the role's version when staging begins.
    """
    proc = _git(repo, "reset", "-q", "--", relpath)
    if proc.returncode != 0:
        raise OSError(
            f"git reset of {relpath} failed: {_decode(proc.stderr).strip()}"
        )


def _revert_one(repo: Path, relpath: str) -> None:
    """Restore one path to its pre-role state. Raises when it cannot be.

    Only ever called for a path absent from the role snapshot, so presence in
    HEAD alone decides the remedy: in HEAD means it equalled HEAD at role
    start (whether the role then modified, staged or deleted it), absent from
    HEAD means it did not exist at all. Both branches clear the index entry.
    """
    if _is_in_head(repo, relpath):
        _restore_from_head(repo, relpath)
        _unstage(repo, relpath)
        return
    _unstage(repo, relpath)
    target = _repo_path(repo, relpath)
    if target.is_symlink() or target.exists():
        # Absent from HEAD: remove the single file. `unlink` refuses a
        # directory, which is exactly the report-it-never-guess case.
        target.unlink()


def _revert_all(repo: Path, paths: list) -> tuple:
    """Revert each path independently; one failure never aborts the rest."""
    reverted, failed = [], []
    for relpath in paths:
        try:
            _revert_one(repo, relpath)
        except OSError:
            failed.append(relpath)
        else:
            reverted.append(relpath)
    return reverted, failed


def _restorable(role_snapshot: dict, path: str) -> bool:
    """Can the guard put this path back exactly as it was before the role ran?

    The one question the remedy is allowed to ask, and the only one that is
    answerable. A path ABSENT from the role snapshot was, at role start,
    either non-existent (untracked → delete restores that) or identical to
    HEAD (tracked → checkout restores that). A path PRESENT in the snapshot
    was already dirty, and the snapshot carries only a digest — git does not
    hold that content and nothing here can reproduce it.

    Ownership deliberately does not appear: asking "whose is this" against
    the TICK baseline deleted role A's in-zone file when role B touched it,
    because A created it mid-tick and it therefore looked revertible.

    NOTHING inside `.git/` is ever restorable, whatever the snapshot says.
    The rule above reads «absent from the snapshot → untracked → deleting it
    restores the previous state», and for a working-tree path that is true.
    For git's own files it is false twice over: they are never in HEAD, so
    «restore» always resolves to «delete», and they are not the role's to
    begin with — `.git/info/exclude` is created by `git init` and maintained
    by whatever hosts the repository. Without this line the guard deleted the
    host's ignore file on every run that touched it, destroying state it did
    not own, breaking its own promise never to write inside `.git/`, and then
    aborting anyway on the deletion it had just performed.
    """
    if path == INFO_EXCLUDE or path.startswith(".git/"):
        return False
    return path not in role_snapshot.get("entries", {})


def _held_owner_work(tick_baseline: dict, path: str) -> bool:
    """Report-only label: the owner's uncommitted work, or an earlier role's.

    Demoted to a pure reporting question (§3.2) — nothing about safety
    depends on it. A path already dirty when the TICK began was the owner's;
    one that became dirty later was an earlier role's output. Two different
    things for the owner to read in the morning.
    """
    return path in tick_baseline.get("entries", {})


def remedy(repo: Path, out_of_zone: list, role_snapshot: dict) -> dict:
    """Apply the restorability branch to every out-of-zone path.

    Branches on the ROLE snapshot: what this role found already dirty it may
    not undo, whoever left it there. The tick baseline is not an input — it
    labels the report, and a safety rule that consulted it destroyed data.
    """
    unrestorable = [p for p in out_of_zone if not _restorable(role_snapshot, p)]
    revertible = [p for p in out_of_zone if _restorable(role_snapshot, p)]
    reverted, failed = _revert_all(repo, revertible)
    return {"reverted": reverted, "reported_only": unrestorable, "failed": failed}


def label_reported(tick_baseline: dict, reported_only: list) -> list:
    """Attach the §3.2 label to each unrestorable path, for the report.

    The tick baseline's whole remaining job, and the reason `check` still
    takes it. `owner` — the path was already dirty when the TICK began, so
    it is the owner's uncommitted work. `earlier-role` — it became dirty
    during this tick, so an earlier role produced it. Two different things
    for the owner to read on a morning report; neither changes what the
    guard did, which is nothing.

    The label rides on the entry rather than in a parallel key, because a
    bare path string cannot carry it and a second key invites the two to
    drift apart. `remedy` returns plain paths — it has no baseline and
    cannot label — and this is where they acquire the label.
    """
    return [
        {
            "path": path,
            "held_by": OWNER_LABEL if _held_owner_work(tick_baseline, path)
            else ROLE_LABEL,
        }
        for path in reported_only
    ]


def label_hidden(hidden: list) -> list:
    """Attach the `ignored` label to each path an ignore rule made invisible.

    Separate from `label_reported` because the baseline cannot answer for
    these: `owner` and `earlier-role` are read off who had already dirtied
    the path, and a path that only became INVISIBLE was not necessarily
    dirtied by anyone. Its label states the one thing that is true of all of
    them — git can no longer see it, and the guard did not restore it.
    """
    return [{"path": path, "held_by": HIDDEN_LABEL} for path in hidden]


def secret_values(secrets_file: Path) -> list:
    """Every value in the secrets file, or `[]` when there is no such file."""
    if not secrets_file.is_file():
        return []
    return list(parse_secrets_file(secrets_file).values())


def needles(values: list, floor: int = SECRET_SCAN_MIN_LENGTH) -> list:
    """Every form of each scannable credential the scan looks for.

    The raw value plus its base64, hex and percent-encoded forms. One
    `base64` call is all it takes to walk a token past an exact-match scan,
    and these three are what a role reaches for first. Encodings are
    unbounded — gzip, rot13, split across two files, spelled out in words —
    so this closes the common cases, NOT the class. The honest position is
    that an in-zone write is a legal channel and the scan raises its cost.
    """
    out = []
    for value in values:
        if not isinstance(value, str) or len(value) < max(floor, 1):
            continue
        raw = value.encode("utf-8")
        for form in (
            value,
            base64.b64encode(raw).decode("ascii"),
            base64.b64encode(raw).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="),
            raw.hex(),
            raw.hex().upper(),
            urllib.parse.quote(value, safe=""),
        ):
            if form and form not in out:
                out.append(form)
    return out


def redact(text: str, values: list) -> str:
    """Replace every form of every credential in `text` with the marker.

    The run line is written AFTER `check`, so nothing scanned it: a token in
    the role's own `note:`, or used as a FILENAME so that it arrives as a
    path in `reverted`, is pushed in plain text by the tick. The guard's own
    audit trail is otherwise an exfiltration channel.
    """
    if not isinstance(text, str):
        return text
    # No floor here. The floor exists because scanning the OWNER's files for
    # a short value false-positives on their prose; the log line is the
    # engine's own output, so there is no such cost — and refusing to redact
    # a weak credential publishes it.
    for needle in needles(values, floor=1):
        if needle in text:
            text = text.replace(needle, REDACTION)
    return text


def redact_paths(paths: list, values: list) -> list:
    return [redact(path, values) for path in paths]


def scan_secrets(repo: Path, paths: list, values: list, *,
                 content: bool = True, names: bool = True) -> list:
    """Paths carrying a scannable credential, by content, by name, or both.

    Exact-value match only, no entropy heuristic: the previous engine's
    scanner guessed at entropy and dropped legitimate rows, and a guess here
    would either miss a real leak or destroy the owner's real content.

    The two halves are separable because they are true at different moments.
    CONTENT is read while the file is still on disk, and a hit means the
    value really reached the disk, whatever becomes of the file afterwards.
    A NAME is only a string, so matching one after the file is gone reports
    an artefact of the path rather than an event. The caller therefore scans
    content over everything touched and names over what survives.
    """
    forms = needles(values)
    if not forms:
        return []
    hits = []
    for relpath in paths:
        # A credential used as a FILENAME ships as a pushed path, so a file
        # still on disk that is named for one is a real finding.
        if names and any(form in relpath for form in forms):
            hits.append(relpath)
            continue
        if not content:
            continue
        try:
            raw = _repo_path(repo, relpath).read_bytes()
        except OSError:
            continue
        # Decode with replacement rather than refusing undecodable content.
        # Refusing it made ONE stray byte a complete bypass: a file whose
        # first byte is invalid UTF-8 skipped the scan, stayed in `in_zone`,
        # and was therefore staged, committed and pushed with the credential
        # in it. `errors="replace"` only mangles the bytes around the bad
        # one, and a credential is ASCII, so every form still matches.
        text = raw.decode("utf-8", errors="replace")
        if any(form in text for form in forms):
            hits.append(relpath)
    return hits


def scan_commit(repo: Path, before: str, after: str, values: list) -> list:
    """Paths whose committed diff carries a credential.

    A role that commits leaves a clean tree, so `in_zone` is empty and the
    working-tree scan has nothing to read — the credential is in history and
    every surface says the run was clean. When HEAD moved, the diff IS the
    role's output, so that is what gets scanned.
    """
    forms = needles(values)
    if not forms or not before or not after or before == after:
        return []
    listing = _git(repo, "diff", "--name-only", "-z", f"{before}..{after}")
    if listing.returncode != 0:
        return []
    hits = []
    for name in _decode(listing.stdout).split("\0"):
        if not name:
            continue
        diff = _git(repo, "diff", f"{before}..{after}", "--", name)
        text = diff.stdout.decode("utf-8", errors="replace")
        if any(form in text for form in forms):
            hits.append(name)
    return hits


def _abort(reason_key, reason, repo, in_zone, out_of_zone, tick_baseline,
           values, also=(), ignore_changed=False, hidden=()) -> dict:
    """A report with no mutation performed. Every abort has this shape.

    An abort reverts nothing, so EVERYTHING the role wrote is still on disk —
    which is exactly why the scan matters more here, not less. On a
    `git_surface` abort the role has already shown it is attacking the guard;
    leaving its writes unread there would be the worst place to skip.

    `hidden` carries the paths an ignore rule made invisible during the run.
    They are scanned and reported like any other path, because an abort on a
    DIFFERENT field must not be the thing that loses them: the guard can see
    them, so it says so, whatever else went wrong in the same run.
    """
    hidden_files = [path for path in hidden if not path.endswith("/")]
    leaks = scan_secrets(
        repo, list(in_zone) + list(out_of_zone) + hidden_files, values)
    for path in also:
        if path not in leaks:
            leaks.append(path)
    result = {
        "in_zone": in_zone,
        "reverted": [],
        "reported_only": label_reported(tick_baseline, out_of_zone)
        + label_hidden(hidden),
        "secret_leak": leaks,
        "head_moved": False,
        "git_surface": False,
        "unsettled": False,
        "ignore_changed": ignore_changed,
        "failed": [],
    }
    result[reason_key] = reason
    return result


def check(repo: Path, tick_baseline: dict, role_snapshot: dict,
          prefixes: tuple, secrets_file: Path,
          settle_seconds: float = SETTLE_SECONDS) -> dict:
    """Attribute, classify, remedy and scan one role's run.

    `in_zone` is POST-remedy: a file REVERTED for a secret leak is not in
    it, so the run line's `writes` count is the length of that list and the
    two agree by construction rather than by a rule someone must remember. A
    leaking file left on disk because it held the owner's work stays in
    `in_zone` — it is a write that really happened — and the tick excludes
    it from the commit on the strength of `secret_leak`.

    **A path can appear in both `secret_leak` and `reverted`, and that is
    correct rather than contradictory.** The lists answer different
    questions: `secret_leak` says a credential was WRITTEN there, `reverted`
    says the file is now GONE. An out-of-zone file the role created with a
    token inside is both — removed, and still worth telling the owner about,
    because deleting the file does not un-send the value. Do not read these
    lists as a partition.

    Takes `prefixes`, never a role config: flatness is a property of the
    prefix, so the guard holds no second copy of any path.

    Three conditions abort with no mutation at all, each reported in its own
    field: `unsettled` (the tree changed while the check was running),
    `git_surface` (the role changed git's configuration) and `head_moved`
    (the role committed). Ignore-file changes are the exception — they are
    reverted first and attribution is re-run from scratch, because a payload
    hidden behind a rule that no longer exists must be attributed normally.

    An ignore change the revert could not undo does NOT abort. What it hid is
    recovered instead: `newly_hidden` names every path that went invisible,
    each is scanned and reported under the `ignored` label, and none is
    restored. Hiding therefore changes nothing about how a write is handled,
    which is what makes stopping the tick unnecessary — and stopping it was
    never free, because `.git/info/exclude` is the harness's own file and the
    abort fired on ordinary nights.

    The limit, stated rather than implied: a path inside a directory that was
    ALREADY wholly ignored before the role ran is not covered. Porcelain
    collapses such a directory to a single entry, so nothing under it is
    listed on either side and no comparison can be made. That is a real hole,
    it predates this handling, and no wording here should read as if the
    guard sees into one.
    """
    _validate_snapshot(role_snapshot, "the role snapshot")
    _validate_snapshot(tick_baseline, "the tick baseline")
    values = secret_values(secrets_file)

    # A background process defeats a post-hoc check by design: the role
    # exits, `check` sees a spotless tree, and the payload lands afterwards.
    # A second snapshot catches what is still in flight. It does NOT stop a
    # patient attacker and must not be read as if it did — the real fix is a
    # process-group kill, which belongs to the dispatcher.
    first = capture_snapshot(repo, secrets_file)
    if settle_seconds > 0:
        time.sleep(settle_seconds)
    current = capture_snapshot(repo, secrets_file)
    if first != current:
        moved = sorted(set(attribute(first, current)))
        in_zone, out_of_zone = classify(attribute(role_snapshot, current), prefixes)
        return _abort("unsettled", {"paths": moved}, repo, in_zone, out_of_zone,
                      tick_baseline, values)

    # An ignore rule added mid-run hides the payload from `git status`, and
    # reverting the ignore file alone would UN-hide it just in time for the
    # tick to commit it. Revert the ignore files first, then attribute from
    # scratch against a tree that can no longer hide anything.
    delta = surface_delta(role_snapshot.get("git", {}), current.get("git", {}))
    reverted_ignores: list = []
    ignore_failures: list = []
    if "ignore" in delta:
        changed = sorted(
            name for name in set(delta["ignore"]["before"] or {})
            | set(delta["ignore"]["after"] or {})
            if (delta["ignore"]["before"] or {}).get(name)
            != (delta["ignore"]["after"] or {}).get(name)
        )
        reverted_ignores, ignore_failures = _revert_all(
            repo, [n for n in changed if _restorable(role_snapshot, n)])
        current = capture_snapshot(repo, secrets_file)
        delta = surface_delta(role_snapshot.get("git", {}), current.get("git", {}))
        # NOTHING is re-added to `delta` here. Re-adding an `ignore` key made
        # the branch above pointless: `delta` became permanently truthy, so
        # the abort below fired and the remedy this branch exists to enable
        # never ran — the payload was attributed correctly and then left on
        # disk. It also destroyed the evidence, handing the CLARIFICATION a
        # `{before: null, after: null}` where its spec demands which file
        # changed and how.
        #
        # An ignore file the revert could NOT restore is still in `delta`,
        # with its real digests, because `surface_delta` recomputed it from
        # the fresh snapshot — so the un-restorable case still aborts, loudly
        # and with evidence, while the ordinary case proceeds to remedy.
        #
        # But the revert IS recorded, in `reverted` and `failed` below. A run
        # that silently repaired an ignore rule and then reported a spotless
        # tree would leave no trace that a role touched the one surface the
        # guard's whole model rests on — and the owner would read the run line
        # as an ordinary quiet night.

    touched = attribute(role_snapshot, current)
    in_zone, out_of_zone = classify(touched, prefixes)

    # An ignore change that survived the revert is ATTRIBUTED, not vetoed.
    #
    # The veto existed for exactly one reason: `git status` omits an ignored
    # path, so `attribute` could not see one, so a rule added mid-run moved a
    # write outside everything the guard reads. That is a blind spot in
    # attribution, and a blind spot is closed by looking — not by stopping the
    # tick whenever something might have entered it. `newly_hidden` names the
    # paths, they are digested, scanned and reported below, and hiding
    # therefore buys a role nothing at all: a hidden write is treated exactly
    # as the same write in plain sight would have been.
    #
    # With the gap closed the veto had no remaining job, and it had a real
    # cost. `.git/info/exclude` belongs to the harness hosting the tick, which
    # writes its own runtime entries there mid-run — so the abort fired on
    # ordinary nights, and an abort that fires on ordinary nights stops being
    # read while still taking down every role queued behind it.
    #
    # Every other field on the surface stays absolute. A remote, a hook, an
    # index flag or `.git/config` has no benign author, and no amount of
    # looking makes one safe.
    #
    # The verdict changes; `delta` does not. It carries git-surface FIELDS, and
    # the consequence of an ignore change is not one — a reader handed a
    # `hidden` key beside `remotes` would report a git field that does not
    # exist. So the evidence goes to its own place, and the abort's fields stay
    # exactly what the surface really holds.
    ignore_changed: dict | bool = False
    hidden: list = []
    if "ignore" in delta:
        found = newly_hidden(role_snapshot, current)
        ignore_changed = {"fields": {"ignore": delta["ignore"]}, "hidden": found}
        if found is None:
            # «Cannot tell» — one snapshot predates the `ignored` field, so
            # nothing can be attributed and the conservative verdict stands.
            # Inferring safety from an absence is the one reading this branch
            # must never take.
            return _abort("git_surface", delta, repo, in_zone, out_of_zone,
                          tick_baseline, values, ignore_changed=ignore_changed)
        hidden = found
        delta = {field: pair for field, pair in delta.items() if field != "ignore"}

    if delta:
        return _abort("git_surface", delta, repo, in_zone, out_of_zone,
                      tick_baseline, values, ignore_changed=ignore_changed,
                      hidden=hidden)

    head_moved = (
        False if current["head"] == role_snapshot.get("head")
        else {"before": role_snapshot.get("head"), "after": current["head"]}
    )
    if head_moved:
        # The role committed. Reverting anything now could destroy the
        # owner's work committed alongside it, so nothing is mutated at all.
        # The tree is clean, so the working-tree scan would read nothing —
        # the committed diff is the role's output and is what gets scanned.
        # Both surfaces, because a role can do both: what it committed, and
        # what it left on disk. The working-tree scan alone reads nothing when
        # the commit swept the tree clean; the commit scan alone misses a
        # credential still sitting in an unstaged file.
        return _abort(
            "head_moved", head_moved, repo, in_zone, out_of_zone, tick_baseline,
            values,
            also=scan_commit(repo, head_moved["before"], head_moved["after"], values),
            ignore_changed=ignore_changed, hidden=hidden,
        )

    # CONTENT first, over EVERY path the role touched, while the files are
    # all still on disk. `secret_leak` means «a credential was written
    # here», not «a credential survived»: deleting the file does not un-send
    # the value, and a role that wrote a token to disk may equally have sent
    # it somewhere this guard cannot see. That is a rotate-now signal on its
    # own, and `reverted` already carries «it is gone».
    #
    # A hidden path is scanned here with everything else. It is deliberately
    # NOT handed to `remedy`: the guard cannot tell a role's hidden payload
    # from the harness's own runtime file, and «restore» for a path in no
    # commit means DELETE — which is how a live lock file belonging to the
    # process running the tick would get removed. Reported, never touched.
    hidden_files = [path for path in hidden if not path.endswith("/")]
    leaks = scan_secrets(repo, touched + hidden_files, values, names=False)

    applied = remedy(repo, out_of_zone, role_snapshot)

    # NAMES only over what survived. A path whose name matches after the
    # file has been removed is an artefact of the string, not an event; an
    # in-zone file still on disk and NAMED for the credential would ship as
    # a pushed path, so that one is real.
    survivors = list(in_zone) + list(applied["reported_only"]) + hidden_files
    for path in scan_secrets(repo, survivors, values, content=False):
        if path not in leaks:
            leaks.append(path)

    # §3.6 meets §3.3 here. Only a file still on disk can be reverted for a
    # leak, and only when the guard could restore it: a kept path is kept
    # BECAUSE it cannot be restored, so a leak in one is reported and left,
    # and the tick keeps it out of the commit. Reverting it would destroy
    # content the role did not author — the cure worse than the disease.
    #
    # `hidden_files` are excluded from revert eligibility on purpose, and this
    # is the one place the distinction bites: a leak makes a path MORE
    # tempting to delete, and a hidden path is precisely the one the guard
    # cannot attribute to the role. The leak is still reported — that is the
    # rotate-now signal, and the tick holds the path out of its commit — but
    # the file itself is left where it is.
    surviving = set(in_zone) | set(applied["reported_only"])
    revertible = [p for p in leaks
                  if p in surviving and _restorable(role_snapshot, p)]
    reverted_leaks, leak_failures = _revert_all(repo, revertible)
    removed = set(reverted_leaks)
    return {
        "in_zone": [path for path in in_zone if path not in removed],
        "reverted": sorted(set(applied["reverted"]) | set(reverted_ignores)),
        "reported_only": label_reported(tick_baseline, applied["reported_only"])
        + label_hidden(hidden),
        "secret_leak": leaks,
        "head_moved": False,
        "git_surface": False,
        "unsettled": False,
        "ignore_changed": ignore_changed,
        "failed": applied["failed"] + leak_failures + ignore_failures,
    }
