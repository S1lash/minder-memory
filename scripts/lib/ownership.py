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
# Tails the ENGINE owns. The hyphen form is a repository or folder name and the
# engine has exactly one of those; the underscore form is how the engine writes
# its own python identifiers and config keys — and an owner's folder name is
# indistinguishable from one by shape alone, `minder_ztn_ivanov` against
# `minder_ztn_session`. So the engine's are named here, and everything else with
# a tail is the owner's.
_ENGINE_SLUG_TAILS = frozenset({
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
# `ztn-roles-<suffix>` is the roles tick's own temp-directory prefix and has its
# own rule in the map. It is the one skill name the engine itself extends.
_SKILLISH_EXCLUDE = frozenset({"roles"})


def own_name_spans(text: str, base: Path | None = None) -> list[tuple[int, int]]:
    """Every span of `text` that is a name the OWNER chose. Non-overlapping, in order."""
    spans: list[tuple[int, int]] = []
    for match in _OWN_SLUG_RE.finditer(text):
        token = match.group(0)
        tail = re.split(r"[-_]", token, maxsplit=2)[2].lower()
        if tail in _ENGINE_SLUG_TAILS:
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
        parts = tail.split("-")
        for length in range(len(parts) - 1, 0, -1):
            head = "-".join(parts[:length])
            if head not in ENGINE_SKILL_NAMES or head in _SKILLISH_EXCLUDE:
                continue
            remainder = "-".join(parts[length:])
            # The engine extends its own skill names with ASCII words it owns —
            # `ztn-process-skill` is a quick-reference card, and
            # `ztn-update-distribution-mechanism` is a document slug. Those are
            # indistinguishable by shape from an ASCII tail of the owner's, so
            # the claim is made only for a tail carrying a character the engine
            # never uses in its own identifiers. It is a narrower rule than the
            # ideal one, and narrow in the safe direction: the cost is that
            # `ztn-process-ivanov` is still renamed, not that an engine name is
            # frozen.
            if remainder.isascii():
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
    _engine, excluded = _manifest_sections(root)
    return any(_under(rel, entry) for entry in excluded)


def is_engine_path(rel: str, root: Path | None = None) -> bool:
    """Does the manifest ship this path?"""
    engine, _excluded = _manifest_sections(root)
    return any(_under(rel, entry) for entry in engine)


# The harness migration's own backup directory. Named by construction rather
# than by suffix, because it is a directory the ENGINE creates outside the
# repository, where no manifest can speak for it.
_ENGINE_BACKUP = re.compile(r"\.minder[-_](?:ztn|memory)-backup-")


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
