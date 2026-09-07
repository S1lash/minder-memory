#!/usr/bin/env python3
"""The one home of «is this name the engine's, or the owner's».

minder-memory-rebrand: keep-legacy-tokens — the former names in this file are
its subject matter, not a surface that missed a rename.

Why this module exists. Seven walkthroughs of the rename produced defects of one
single shape: a boundary between engine-owned and owner-owned names, drawn one
notch too narrow. By file (a store protected, its declaration not); by pair (a
credential renamed on one side only); by alphabet (an ASCII-only tail); by
prefix (every `ztn-` assumed to be a skill the engine shipped). Each was fixed
where it was found, and each fix then had to be restated in two or three places
and pinned equal to itself by tests.

That is the wrong shape for a rule that decides who owns a name. The rule has one
home now, and every consumer imports it: the rename map, the post-update check,
migrations 031 and 033, and the vault seeder. Nothing restates it.

The questions it answers:

  is_engine_env_name              — is this environment variable the engine's?
  own_name_spans                  — which spans of this text are names the OWNER chose?
  is_engine_legacy_harness_entry  — did the ENGINE ship this harness file?
  in_owner_space                  — is this path the owner's to write, and so to name?
  is_engine_owned_name            — does this token name something the engine owns?

The bias throughout is the same and is deliberate: **when a name could be either,
it is the owner's.** Renaming something of theirs produces a path that does not
exist, silently, in the one place they would look for their own files; leaving
one of ours alone produces a stale word. The second is cheap; the first is not.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

__all__ = [
    "ENGINE_ENV_NAMES",
    "ENGINE_SKILL_NAMES",
    "ENGINE_LEGACY_HARNESS",
    "ENGINE_SLUG_TAILS_HYPHEN",
    "ENGINE_SLUG_TAILS_UNDERSCORE",
    "ENGINE_EXTENDED_SKILL_TOKENS",
    "ENGINE_EXTENDED_SKILL_SUFFIXES",
    "former_spellings",
    "sync_remote_and_branch",
    "OWNER_DATA_PREFIXES",
    "OWNER_DATA_FILES",
    "is_engine_env_name",
    "owner_env_names",
    "own_name_spans",
    "is_engine_legacy_harness_entry",
    "in_owner_space",
    "is_engine_owned_name",
    "is_engine_path",
]

# --------------------------------------------------------------------------- #
# (a) environment variables
# --------------------------------------------------------------------------- #

# Every `ZTN_*` the engine itself ever read, recovered from the tree as it stood
# before the rename. Bare suffixes; the caller supplies the prefix.
ENGINE_ENV_NAMES: tuple[str, ...] = (
    "BASE_PATH",              # longest-first, so `BASE` cannot shadow it
    "BASE",
    "CONCEPT_TYPE_JAVA",
    "DEV",
    "PATH",
    "ROLES_AUTONOMOUS_ACK",
    "ROLES_KEY",
    "SECRET_MASTER_KEY",
    "SYMLINK_REEXEC",
)

_SECRETS_REL = "_system/state/secrets.enc.json"
_ROLES_REL = "_system/roles"
_SECRETS_DECL = re.compile(r"^\s*-\s*([A-Za-z_][\w]*)\s*$")


def owner_env_names(base: Path | None) -> frozenset[str]:
    """Environment names the OWNER has claimed, by declaring or by storing one.

    A name a role declares in its `secrets:` block, or that the credential store
    holds, is theirs — even when it collides with the engine's own list. The
    engine cannot know what a friend called their token, and getting this
    backwards costs a role that fails at its next tick naming a variable the
    owner never wrote.
    """
    if base is None:
        return frozenset()
    claimed: set[str] = set()
    store = Path(base) / _SECRETS_REL
    if store.is_file():
        try:
            data = json.loads(store.read_bytes().decode("utf-8"))
            if isinstance(data, dict):
                claimed.update(str(key) for key in data)
        except (OSError, ValueError):
            pass
    roles = Path(base) / _ROLES_REL
    if roles.is_dir():
        for role in sorted(roles.glob("*/role.md")):
            try:
                text = role.read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            in_block = False
            for line in text.splitlines():
                if re.match(r"^\s*secrets\s*:", line):
                    in_block = True
                    continue
                if not in_block:
                    continue
                hit = _SECRETS_DECL.match(line)
                if hit:
                    claimed.add(hit.group(1))
                elif line.strip():
                    in_block = False
    return frozenset(claimed)


def is_engine_env_name(name: str, base: Path | None = None) -> bool:
    """True only when the engine owns this variable AND the owner has not claimed it."""
    bare = name
    for prefix in ("MINDER_MEMORY_", "MINDER_ZTN_", "ZTN_"):
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
            break
    if bare not in ENGINE_ENV_NAMES:
        return False
    return name not in owner_env_names(base)


# --------------------------------------------------------------------------- #
# (c) the harness home
# --------------------------------------------------------------------------- #

# The skills the ENGINE ships, by the bare name after the prefix. The harness
# home lives outside the repository, so the manifest's `retired:` rows — which
# name repository paths — cannot speak for what the installer once linked there.
# This list is therefore declared, not derived, and it is why a bare `ztn-`
# prefix is no longer treated as proof of ownership: an owner's own
# `skills/ztn-мой-скилл/` is theirs, and removing it would be the engine
# destroying work it did not write and cannot restore.
ENGINE_SKILL_NAMES: tuple[str, ...] = (
    "resolve-clarifications", "regen-constitution", "capture-candidate",
    "agent-lens-add", "check-decision", "source-add", "agent-lens",
    "bootstrap", "sync-data", "role-list", "role-edit", "role-add", "role-ask",
    "maintain", "process", "content", "update", "roles", "role", "save", "lint",
)
ENGINE_LEGACY_HARNESS: dict[str, tuple[str, ...]] = {
    "rules": ("ztn.md", "ztn-engine-doctrine.md"),
    "commands": ("ztn-recap.md", "ztn-search.md"),
    "agents": ("ztn-role.md",),
    "skills": tuple("ztn-" + name for name in ENGINE_SKILL_NAMES),
}


def is_engine_legacy_harness_entry(name: str, kind: str) -> bool:
    """Did the ENGINE ship a harness entry under this exact name?

    Exact names only. A prefix test reads an owner's own rule or skill as the
    engine's and deletes it — and unlike a stale word, that is not recoverable
    from anything the engine holds.
    """
    return name in ENGINE_LEGACY_HARNESS.get(kind, ())


# --------------------------------------------------------------------------- #
# (b) the owner's own names, in running text
# --------------------------------------------------------------------------- #

# `minder-ztn` joined by `-` OR `_` to a tail in any script. The lookbehind is
# what separates a NAME from a slug: a name starts a token, while
# `20260519-reflection-minder-ztn-origin-story` is a note's own slug with the
# product named inside it, and that one moves with the product.
_OWN_SLUG_RE = re.compile(r"(?i)(?<![\w-])minder[-_]ztn[-_][^\W_][\w-]*")
# Tails the ENGINE owns — SEPARATELY per separator, because the two are
# different kinds of thing, and one list serving both was wrong in the expensive
# direction. A hyphen form is a repository or project identifier, and the engine
# has exactly one: `minder-ztn-platform`, its retired project id. An underscore
# form is how the engine writes python identifiers and config keys, and an
# owner's folder name is indistinguishable from one by shape alone —
# `minder_ztn_ivanov` against `minder_ztn_session`.
#
# Applying the underscore list to hyphens meant `~/minder-ztn-env`, an ordinary
# owner folder, was rewritten to `~/minder-memory-env` — and since the engine
# renaming its own slug is not damage, it left no trace anywhere for the owner
# to find.
#
# Derived from the tree as it stood BEFORE the rename (`git grep -oE
# 'minder[-_]ztn[-_][A-Za-z0-9][A-Za-z0-9_-]*'` over the engine paths), which is
# the only place these forms ever lived: hyphen gave `mcp`, `skeleton` and the
# `backup-` prefix, none of which the engine needs renamed — `minder-ztn-mcp`
# survives on purpose in the manifest's `retired:` row, and the backup directory
# is matched by name in `is_engine_owned_name`. `test_ownership.py` re-derives
# the underscore side from the shipped tree and fails when a new one appears.
ENGINE_SLUG_TAILS_HYPHEN = frozenset({"platform"})
ENGINE_SLUG_TAILS_UNDERSCORE = frozenset({
    "platform", "session", "constitution", "env", "deploy_key", "rebrand",
})
# Any `ZTN_` name at all — no `[A-Z]` anchor after the underscore, because
# `ZTN_2FA_SECRET` and `ZTN_Telegram_Token` are names people really write.
# Which of these the engine owns is decided by `is_engine_env_name`, not here.
_ENV_CANDIDATE_RE = re.compile(r"(?<![\w-])ZTN_\w+")
# `ztn-<skill>-<tail>`: the skill rules stop at a word boundary, so a skill name
# with something of the owner's glued on falls through to the generic `ztn-`
# rule and gets the product spliced into the middle of a name they chose.
_SKILLISH_RE = re.compile(r"(?<![\w-])ztn-([\w-]+)")
# `ztn-roles-<suffix>` is the roles tick's own temp-directory prefix, generated
# at run time and never written down, so it is matched by its HEAD.
_SKILLISH_EXCLUDE = frozenset({"roles"})
# The engine's own forms that extend a skill name. Everything else shaped like
# one is the owner's — whatever alphabet it is in.
#
# The earlier rule claimed only non-ASCII tails, which made the answer depend on
# what alphabet a friend's name happens to use: `ztn-process-иванов` was kept and
# `ztn-process-ivanov` was renamed. Latin-named friends are the majority, so the
# rule was wrong for most of the people it exists to protect.
#
# Derived by grepping the shipped tree for what a skill-extending engine name
# looks like today (`minder-mem-<skill>-<tail>` / `minder-memory-<skill>-<tail>`)
# and mapping it back. `test_ownership.py` re-runs that derivation and fails when
# a new engine form appears unlisted, so the list cannot go stale in silence.
ENGINE_EXTENDED_SKILL_SUFFIXES: tuple[str, ...] = (
    "-skill",          # the quick-reference card ids: `ztn-<skill>-skill`
)
ENGINE_EXTENDED_SKILL_TOKENS: tuple[str, ...] = (
    # A note slug in which `update` is the English word and not the skill. It
    # names the product, so it moves with the product.
    "ztn-update-distribution-mechanism",
)


def own_name_spans(text: str, base: Path | None = None) -> list[tuple[int, int]]:
    """Every span of `text` that is a name the OWNER chose. Non-overlapping, in order."""
    spans: list[tuple[int, int]] = []
    for match in _OWN_SLUG_RE.finditer(text):
        token = match.group(0)
        pieces = re.split(r"([-_])", token, maxsplit=4)
        separator, tail = pieces[3], pieces[4].lower()
        engine_tails = (ENGINE_SLUG_TAILS_HYPHEN if separator == "-"
                        else ENGINE_SLUG_TAILS_UNDERSCORE)
        if tail in engine_tails:
            continue
        # `MINDER_ZTN_BASE` is the engine's own environment variable wearing the
        # same shape. The env question answers it — in one place, as everything
        # about ownership now is.
        if is_engine_env_name(token.upper().replace("-", "_"), base):
            continue
        spans.append(match.span())
    for match in _ENV_CANDIDATE_RE.finditer(text):
        if not is_engine_env_name(match.group(0), base):
            spans.append(match.span())
    for match in _SKILLISH_RE.finditer(text):
        tail = match.group(1)
        if tail in ENGINE_SKILL_NAMES:
            continue                      # the skill itself — the engine's
        token = match.group(0)
        if token in ENGINE_EXTENDED_SKILL_TOKENS:
            continue
        if token.endswith(ENGINE_EXTENDED_SKILL_SUFFIXES):
            continue
        parts = tail.split("-")
        for length in range(len(parts) - 1, 0, -1):
            head = "-".join(parts[:length])
            if head not in ENGINE_SKILL_NAMES or head in _SKILLISH_EXCLUDE:
                continue
            spans.append(match.span())
            break
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# --------------------------------------------------------------------------- #
# (b2) what a name USED to be called
# --------------------------------------------------------------------------- #

# Every shape the 1.0.0 map could turn an owner's name into. Both the single
# form and the doubled one it produced by splicing the product into the middle,
# in the hyphen and the underscore spelling.
# Both separators are captured, because they need not be the same one. A real
# clone carried `minder-ztn_ивaнов`; 1.0.0's underscore rule fired inside it and
# left `minder-minder_memory_ивaнов` — a hyphen in front, underscores behind.
# Rebuilding it with a single separator produces a name that never existed, the
# lookup fails, and the finding is dropped in silence.
_DAMAGED_FORMS = (
    re.compile(r"^minder([-_])minder([-_])memory([-_])(.+)$"),
    re.compile(r"^minder([-_])()memory([-_])(.+)$"),
)


def former_spellings(token: str) -> list[str]:
    """What this token could have been called before the rename, best first.

    One home for the inversion. The damage check and migration 033 both need to
    ask «what did this used to say», and a second regex set answering it beside
    the map's is exactly the drift this module exists to remove. The candidates
    are proposed here; what decides between them is the pre-rename text itself,
    which is the only authority that cannot be wrong.
    """
    out: list[str] = []
    for pattern in _DAMAGED_FORMS:
        hit = pattern.match(token)
        if not hit:
            continue
        lead, inner, tail = hit.group(1), hit.group(3), hit.group(4)
        out.append("minder" + lead + "ztn" + inner + tail)
        # `minder-memory-process-иванов` came from `ztn-process-иванов`: the map
        # rewrote a skill name the owner had extended, not the product slug.
        head = re.split(r"[-_]", tail)[0]
        if head in ENGINE_SKILL_NAMES:
            out.append("ztn" + inner + tail)
        break
    seen: set[str] = set()
    return [c for c in out if not (c in seen or seen.add(c))]


# --------------------------------------------------------------------------- #
# (d) + (e) paths
# --------------------------------------------------------------------------- #

# The owner-data classes. The manifest's `exclude:` is read alongside these, so
# the two answers to «whose file is this» cannot drift apart.
OWNER_DATA_PREFIXES: tuple[str, ...] = (
    "zettelkasten/_records/",
    "zettelkasten/1_projects/",
    "zettelkasten/2_areas/",
    "zettelkasten/3_resources/",
    "zettelkasten/4_archive/",
    "zettelkasten/5_meta/mocs/",
    "zettelkasten/6_posts/",
    "zettelkasten/0_constitution/axiom/",
    "zettelkasten/0_constitution/principle/",
    "zettelkasten/0_constitution/rule/",
    "zettelkasten/_system/roles/",
    "zettelkasten/_system/state/",
    "zettelkasten/.obsidian/",
)
OWNER_DATA_FILES: tuple[str, ...] = (
    "zettelkasten/_system/SOUL.md",
    "zettelkasten/_system/TASKS.md",
    "zettelkasten/_system/CALENDAR.md",
    "zettelkasten/_system/POSTS.md",
    "zettelkasten/_system/registries/TAGS.md",
    "zettelkasten/_system/registries/SOURCES.md",
    "zettelkasten/_system/registries/AUDIENCES.md",
    "zettelkasten/_system/registries/DOMAINS.md",
    "zettelkasten/_system/registries/CONCEPTS.md",
    "zettelkasten/minder-memory.md",
)

BASE_PREFIX = "zettelkasten/"

_MANIFEST_CACHE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}


def _manifest_sections(root: Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(engine paths, excluded paths) from `.engine-manifest.yml`, or empty."""
    if root is None:
        return (), ()
    key = str(root)
    if key in _MANIFEST_CACHE:
        return _MANIFEST_CACHE[key]
    manifest = Path(root) / ".engine-manifest.yml"
    engine: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    if manifest.is_file():
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from lib.manifest import read_section_lite  # noqa: PLC0415
            engine = tuple(read_section_lite(manifest, "engine"))
            excluded = tuple(read_section_lite(manifest, "exclude"))
        except Exception:  # noqa: BLE001 — an unreadable manifest is the sync's problem, not ours
            engine, excluded = (), ()
    _MANIFEST_CACHE[key] = (engine, excluded)
    return engine, excluded


def _under(rel: str, entry: str) -> bool:
    entry = entry.rstrip("/").rstrip("*").rstrip("/")
    if not entry:
        return False
    return rel == entry or rel.startswith(entry + "/")


def in_owner_space(rel: str, root: Path | None = None) -> bool:
    """Is this path the owner's to write, and therefore theirs to name?

    The manifest's `exclude:` is consulted alongside the owner-data classes: it
    is where the engine already declares which paths are not its own, and two
    lists answering the same question drift the moment one of them is edited.
    """
    if rel.startswith(OWNER_DATA_PREFIXES) or rel in OWNER_DATA_FILES:
        return True
    engine, excluded = _manifest_sections(root)
    if any(_under(rel, entry) for entry in excluded):
        return True
    # Inside the BASE, what the engine does not ship is the owner's. The engine
    # writes only what it declares, so a path under the base that the manifest
    # neither ships nor excludes was put there by them — a folder of notes the
    # engine has no name for, or a file left behind when a directory it shipped
    # was retired and kept for exactly that reason.
    #
    # Only inside the base, and only when the manifest could actually be read:
    # an empty engine list means «unknown», and unknown must not turn the whole
    # tree into owner space.
    if engine and rel.startswith(BASE_PREFIX):
        return not any(_under(rel, entry) for entry in engine)
    return False


def is_engine_path(rel: str, root: Path | None = None) -> bool:
    """Does the manifest ship this path?"""
    engine, _excluded = _manifest_sections(root)
    return any(_under(rel, entry) for entry in engine)


# The harness migration's own backup directory. Named by construction rather
# than by suffix, because it is a directory the ENGINE creates outside the
# repository, where no manifest can speak for it.
_ENGINE_BACKUP = re.compile(r"\.minder[-_](?:ztn|memory)-backup-")


def _git(repo_root: Path, *args: str) -> "subprocess.CompletedProcess":
    import subprocess  # noqa: PLC0415 — only the remote question needs a subprocess
    return subprocess.run(["git", "-C", str(repo_root), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def _renamed_url(url: str) -> str | None:
    """The same URL with its last path segment renamed, or None when it is not the old name."""
    stripped = url.rstrip("/")
    for sep in ("/", ":"):
        head, sep_found, last = stripped.rpartition(sep)
        if not sep_found:
            continue
        if last.lower() == "minder-ztn":
            return head + sep + "minder-memory"
        if last.lower() == "minder-ztn.git":
            return head + sep + "minder-memory.git"
        break
    return None


def sync_remote_and_branch(repo_root: Path) -> tuple[str | None, str]:
    """The remote and branch the ENGINE syncs from — whose remote is ours.

    An ownership question like the rest of this module, and it has to have one
    answer: the harness migration repoints exactly this remote and no other,
    and the retirement step reads exactly this remote's history to decide
    whether the engine ever shipped a file. Two answers to it would let one step
    protect what the other deletes.

    The sync exports what it was invoked with (`ENGINE_SYNC_REMOTE`,
    `ENGINE_SYNC_BRANCH`) so anything it runs follows the same pair — a fork, a
    release branch, a remote not called `upstream`. Outside a sync: `upstream`
    if it exists, else the single remote whose URL names the skeleton. Several
    qualifying remotes means an owner with a fork and a mirror, and guessing
    between them would repoint one of theirs.
    """
    import os as _os  # noqa: PLC0415
    remote = _os.environ.get("ENGINE_SYNC_REMOTE", "").strip() or None
    branch = _os.environ.get("ENGINE_SYNC_BRANCH", "").strip() or None
    names = _git(repo_root, "remote").stdout.split()
    if remote is None:
        if "upstream" in names:
            remote = "upstream"
        else:
            qualifying = []
            for name in names:
                url = _git(repo_root, "remote", "get-url", name).stdout.strip()
                tail = url.rstrip("/").rstrip(".git").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
                if _renamed_url(url) or tail.lower() == "minder-memory":
                    qualifying.append(name)
            if len(qualifying) == 1:
                remote = qualifying[0]
    if remote is None:
        return None, branch or "main"
    if branch is None:
        head = _git(repo_root, "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
        branch = head.stdout.strip().split("/", 1)[-1] if head.returncode == 0 and head.stdout.strip() else "main"
    return remote, branch


def is_engine_owned_name(token: str, root: Path | None = None) -> bool:
    """Does this token name something the ENGINE owns?

    Not a word list of suffixes. `minder-memory-mcp` is an engine directory when
    it IS one — `integrations/minder-memory-mcp` in this repository — and is the
    owner's when they wrote `~/repos/minder-memory-mcp` in a note. The full path
    decides, never the tail on its own.
    """
    if _ENGINE_BACKUP.search(token):
        return True
    candidate = token.strip().strip("\"'`,;")
    if candidate.startswith(("~/", "./", "/")):
        return False   # an absolute or home-relative path is not a repository path
    return is_engine_path(candidate, root)
