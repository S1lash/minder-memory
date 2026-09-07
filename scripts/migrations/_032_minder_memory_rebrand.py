#!/usr/bin/env python3
"""The one home of the Minder Memory rename — token map, path map, scope.

The product this engine implements is Minder Memory (short form: Minder Mem).
Every surface that still says the previous name is rewritten by THIS module,
never by a second sed somewhere else: migration 032 runs it on a friend's clone,
the maintainer runs it on the authoring base and on the repositories that hold
paths into it. One map, one rename rule — so two surfaces can never drift apart
by having been renamed by two different lists.

Scope: every text file under the root, including the append-only state and the
owner's notes and records — a product rename is the one owner-data rewrite the
engine performs, deterministic, idempotent and reversible through git (ADR-029).

Never touched:
- `zettelkasten/_sources/**` — verbatim source material (doctrine §3.6).
- `minder-ztn-<suffix>` — the skeleton name with somebody's own tail on it is
  THEIR repository, folder, host or fork, and renaming it produces a path that
  does not exist. Left whole and reported on the `own_name` axis, so the
  digest can say why those lines still read the old way. The engine's own
  retired project identifier `minder-ztn-platform` is the one exception.
- `ZTN_<NAME>` that is not one of `ENGINE_ENV_NAMES` — the owner's own
  credential, declared by that name in a role and stored under it. The engine
  renames the variables it owns; renaming one of theirs breaks the pair.
- `zettelkasten/_system/state/secrets.enc.json` — the store itself, for the
  same reason and because its values are encrypted, so a change goes unseen.
- `docs/CHANGELOG.md` and `zettelkasten/5_meta/DECISION_LOG.md` — release and
  decision history; each carries its own note of the rename.
- Any `.git` directory, generated output, binaries, files that are not UTF-8.

Naming style (one rule, everywhere): the product is «Minder Memory» in prose,
`minder-memory` / `MINDER_MEMORY_` / `minder_memory` in slugs, variables and
identifiers; the short form `mem` appears ONLY in the slash-command namespace
`/minder:mem:<name>` and in what derives from it — skill directories
`minder-mem-<name>`, the role agent `minder-mem-role`, the roles temp prefix.

Code files (`CODE_SUFFIXES`) get the code-safe subset of the map: product forms,
slugs, namespaces, variables and the MCP surface move; a bare `ztn` identifier
that is somebody's attribute or config key is refactored by hand, not by regex.

Two opt-outs exist for text that must keep an old token ON PURPOSE — a test
whose input is the old form, a migration's matcher: a line carrying LINE_KEEP
is left as written; a file carrying FILE_KEEP is left whole.

Idempotent: a tree that carries no old token is left byte-identical.

Usage:
  python3 scripts/migrations/_032_minder_memory_rebrand.py --root .
  python3 scripts/migrations/_032_minder_memory_rebrand.py --root . --dry-run --inventory INVENTORY.md
  python3 scripts/migrations/_032_minder_memory_rebrand.py --root . --json [--exclude PREFIX ...] [--skip-dirty]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import ownership  # noqa: E402
from lib.portable import configure_std_streams  # noqa: E402

# -----------------------------------------------------------------------------
# Names
# -----------------------------------------------------------------------------

PRODUCT_NAME = "Minder Memory"
PRODUCT_SHORT = "Minder Mem"
PRODUCT_SLUG = "minder-memory"
SKILL_PREFIX = "minder-mem-"            # directory name prefix of every skill
SKILL_NAMESPACE = "minder:mem:"          # slash-command namespace
ENV_PREFIX = "MINDER_MEMORY_"

# The environment variables the ENGINE owns — every `ZTN_*` name the engine
# itself ever read, recovered from the tree as it stood before the rename.
#
# Why a list and not a pattern. A role declares its own credentials by name in
# its `secrets:` block, and those names are the OWNER's: they match whatever
# they called the thing in the store and in their scheduler. A blanket
# `ZTN_* -> MINDER_MEMORY_*` rule renamed one side of that pair and not the
# other — the credential store is never touched — so the role's next preflight
# failed with «declared secret ... is not in the credential store», naming a
# variable the owner had never written. The engine renames the variables it
# owns; everything else with the same shape is somebody's own name and is kept.
_ENGINE_ENV_ALT = "|".join(ownership.ENGINE_ENV_NAMES)
# The engine's own `minder[-_]ztn[-_]<tail>` identifiers, from the same one home
# that decides they are not the owner's — and per separator, because a hyphen
# form and an underscore form are different kinds of thing. Longest-first so a
# tail that is a prefix of another cannot shadow it.
def _slug_alt(tails) -> str:
    return "|".join(re.escape(t) for t in sorted(tails, key=len, reverse=True))


_ENGINE_SLUG_ALT_HYPHEN = _slug_alt(ownership.ENGINE_SLUG_TAILS_HYPHEN)
_ENGINE_SLUG_ALT_UNDERSCORE = _slug_alt(ownership.ENGINE_SLUG_TAILS_UNDERSCORE)

# The engine's skills come from `lib.ownership` — the one home of every «is this
# name ours» answer. Ordered longest-first there, so `role-add` is matched
# before `role` and `agent-lens-add` before `agent-lens`. A name absent from it
# falls through to the generic `ztn-` → `minder-memory-` rule, which is what a
# non-skill artifact wants.

# -----------------------------------------------------------------------------
# Protected spans — replaced by sentinels before the map runs, restored after
# -----------------------------------------------------------------------------

PROTECTED_PATTERNS: tuple[str, ...] = (
    r"_sources/[^\s`'\")\]|>]*",           # a path into verbatim sources
)

_SENTINEL = "@@PROTECT{}@@"

# The base whose roles and credential store say which names the OWNER has
# claimed. Set by `run()` for a real tree; `None` in a unit test, where the
# engine's own lists are the only thing there is to go on.
_OWNER_BASE = None

# WHICH spans are the owner's is not decided here. `lib.ownership` is the one
# home of that question — folders and repositories in any alphabet, credential
# names a role declares or the store holds, an engine skill name with the
# owner's own tail glued on — and every consumer of the answer imports it
# rather than restating it. Seven walkthroughs' worth of defects were the same
# rule drawn differently in three files; this is the fix for the class.

# -----------------------------------------------------------------------------
# Token map — ORDERED. Earlier rules win; each is applied over the whole text.
# -----------------------------------------------------------------------------

_SKILL_ALT = "|".join(re.escape(n) for n in ownership.ENGINE_SKILL_NAMES)

TOKEN_MAP: tuple[tuple[str, str], ...] = (
    # Composite product-name forms first, so the bare forms below never see them.
    (r"\bMinder[ /\-]ZTN\b", PRODUCT_NAME),
    # The owner says the product name aloud in Russian; a transcript writes it
    # «Майндер ZTN». The new name in the same register is the product name.
    (r"(?i)\bмайндер[ \-]ZTN\b", PRODUCT_NAME),
    (r"(?i)\bмайндер[ \-]ЗТН\b", PRODUCT_NAME),
    (r"\bminder_ztn_", "minder_memory_"),
    # The MCP surface: tools of the `minder-memory` connector and its hosts.
    (r"\bztn_(search|get|query|recent|save)\b", r"memory_\1"),
    (r"\bztn\.recall\b", "memory.recall"),
    (r"-ztn\.minder\.host\b", "-memory.minder.host"),
    (r"\bztn\.([A-Za-z0-9_-]+)\.minder\.host\b", r"memory.\1.minder.host"),
    (r"\bztn_per_ip\b", "memory_per_ip"),
    (r"\bsync-ztn-", "sync-minder-memory-"),
    (r"\bztn-deploy-key\b", "minder-memory-deploy-key"),
    (r"\bztn_deploy_key\b", "minder_memory_deploy_key"),
    (r"\bA0-ZTN\b", "A0-Minder-Memory"),
    (r"\btoZTN\b", "to-Minder-Memory"),
    (r"\bZtn\b", PRODUCT_NAME),
    (r"\bztn-(check-content|sync-pull|backfill-concepts)\b", SKILL_PREFIX + r"\1"),
    # The engine's own slug identifiers, renamed whole and EARLY — before the
    # generic `ztn-` rule can splice the product into the middle of one and
    # leave `minder-minder-memory-env` behind. Keyed on `lib.ownership`, the same
    # constant that tells `own_name_spans` these are not the owner's, so the two
    # answers cannot disagree.
    (r"\bminder-ztn-(" + _ENGINE_SLUG_ALT_HYPHEN + r")\b", "minder-memory-" + r"\1"),
    (r"\bminder_ztn_(" + _ENGINE_SLUG_ALT_UNDERSCORE + r")\b", "minder_memory_" + r"\1"),
    (r"\bztn-platform\b", "minder-memory-platform"),
    (r"\bztn_platform\b", "minder_memory_platform"),
    (r"\bminder-minder-memory\b", "minder-memory"),          # a double prefix an earlier run of the rules above left behind
    (r"\bminder_minder_memory\b", "minder_memory"),
    (r"\bZTNVault\b", "MinderMemoryVault"),
    (r"\bZTNAgentRunner\b", "MinderMemoryAgentRunner"),
    (r"\bztn-bridge\b", "minder-memory-bridge"),
    (r"\bsync-ztn\.sh\b", "sync-minder-memory.sh"),
    (r"\bsearchZtn\b", "searchMinderMemory"),
    (r"\bZTN/Minder\b", PRODUCT_NAME),
    # Inside a longer hyphen chain the product is being NAMED, not a repository:
    # a note slug `…-reflection-minder-ztn-origin-story` moves with the product.
    # A name that STARTS a token was protected before the map ever ran.
    (r"(?<=-)minder-ztn(?=-)", PRODUCT_SLUG),
    (r"\bminder-ztn\b(?!-)", PRODUCT_SLUG),
    # «the ZTN memory» named the same thing the product now is; never «Minder Memory memory».
    (r"\bztn-memory\b", PRODUCT_SLUG),
    (r"(?i)\bztn memory\b", PRODUCT_NAME),
    (r"\bminder_ztn\b(?!_)", "minder_memory"),
    (r"\bMINDER-ZTN\b", "MINDER-MEMORY"),
    (r"\bmy-ztn\b", "my-minder-memory"),
    (r"\burn:ztn:", "urn:minder-memory:"),
    # Environment and placeholders.
    (r"\bMINDER_ZTN_", ENV_PREFIX),
    # ONLY the variables the engine itself owns — see ENGINE_ENV_NAMES.
    (r"\bZTN_(" + _ENGINE_ENV_ALT + r")\b", ENV_PREFIX + r"\1"),
    # The two commands in their former flat spelling (`/ztn-recap`) answer to
    # the namespace now; the same for the wrong form an earlier map produced.
    (r"/ztn-(recap|search)\b", "/" + SKILL_NAMESPACE + r"\1"),
    (r"\bztn-(recap|search)\b", SKILL_NAMESPACE + r"\1"),
    (r"/minder-mem-(recap|search)\b", "/" + SKILL_NAMESPACE + r"\1"),
    (r"\bminder-mem-(recap|search)\b", SKILL_NAMESPACE + r"\1"),
    # Skills, commands, the agent, the temp-dir prefixes.
    (r"\bztn-roles-(?![a-z]+-)", SKILL_PREFIX + "roles-"),                       # the roles tick's temp-dir prefix
    (r"\bztn-(" + _SKILL_ALT + r")-skill\b", SKILL_PREFIX + r"\1-skill"),   # the quick-reference card ids
    (r"\bztn-(" + _SKILL_ALT + r")(?![\w-])", SKILL_PREFIX + r"\1"),           # a skill name followed by more slug is not the skill
    # A glob or brace over the skill directories (`ztn-*`, `ztn-{save,update}`)
    # names skills, never the product.
    (r"\bztn-(?=[*{])", SKILL_PREFIX),
    (r"/ztn:", "/" + SKILL_NAMESPACE),
    (r"\bztn:(?=[a-z])", SKILL_NAMESPACE),
    (r"\bztn:", SKILL_NAMESPACE),
    # Python identifiers and concept names.
    (r"\bztn_", "minder_memory_"),
    (r"_ztn_", "_minder_memory_"),
    # Everything else that is hyphen-joined to the old name.
    (r"\bztn-", PRODUCT_SLUG + "-"),
    (r"\bZTNs\b", PRODUCT_NAME + " bases"),
    (r"\bZTN-MVP\b", PRODUCT_NAME + " MVP"),
    (r"\bnon-ZTN\b", "non-" + PRODUCT_NAME.replace(" ", "-")),
    # Bare forms, whole word only. `ZTNVault` and the like never match.
    (r"\bZTN\b", PRODUCT_NAME),
    (r"\bztn\b", PRODUCT_SLUG),
    (r"\bЗТН[а-я]*\b", PRODUCT_NAME),
    (r"\bзтн[а-я]*\b", PRODUCT_NAME),
    # A product name that was already the new one, glued to a stray old form
    # that an earlier rule turned into the new one as well.
    (r"\bMinder[ \-]Minder Memory\b", PRODUCT_NAME),
    (r"\bminder Minder Memory\b", PRODUCT_NAME),
    (r"(?i)\bмайндер Minder Memory\b", PRODUCT_NAME),
)

_COMPILED_MAP: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pat), repl) for pat, repl in TOKEN_MAP
)

# Files whose text is CODE: a bare `ztn` there is an attribute, a config key,
# a variable — renaming it changes a contract somebody's deployment reads. In
# code mode only the rules that name the PRODUCT run (the composite forms, the
# slug, the markers, the slash-command namespace); everything that would
# rewrite an identifier is skipped and left for a deliberate refactor.
CODE_SUFFIXES = frozenset({
    ".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".yaml", ".yml", ".toml",
    ".sh", ".ps1", ".plist", ".conf", ".snap", ".template", ".example", ".env",
})
_CODE_SAFE_RULES = frozenset({
    r"\bMinder[ /\-]ZTN\b", r"(?i)\bмайндер[ \-]ZTN\b", r"(?i)\bмайндер[ \-]ЗТН\b", r"\bZTN/Minder\b",
    r"(?<=-)minder-ztn(?=-)", r"\bminder-ztn\b(?!-)", r"\bminder_ztn\b(?!_)", r"\bminder_ztn_", r"\bztn-memory\b", r"(?i)\bztn memory\b",
    r"\bMINDER-ZTN\b", r"\bmy-ztn\b", r"\burn:ztn:",
    r"\bMINDER_ZTN_", r"\bZTN_(" + _ENGINE_ENV_ALT + r")\b",
    r"/ztn:", r"\bztn:(?=[a-z])",
    r"\bztn-roles-(?![a-z]+-)", r"\bztn-(" + _SKILL_ALT + r")-skill\b", r"\bztn-(" + _SKILL_ALT + r")(?![\w-])", r"\bztn-(?=[*{])", r"\bZTN-MVP\b", r"\bnon-ZTN\b", r"\bZTNs\b",
    r"/ztn-(recap|search)\b", r"\bztn-(recap|search)\b", r"/minder-mem-(recap|search)\b", r"\bminder-mem-(recap|search)\b",
    r"\bztn_(search|get|query|recent|save)\b", r"\bztn\.recall\b", r"-ztn\.minder\.host\b",
    r"\bztn\.([A-Za-z0-9_-]+)\.minder\.host\b", r"\bztn_per_ip\b", r"\bsync-ztn-",
    r"\bztn-deploy-key\b", r"\bztn_deploy_key\b", r"\bA0-ZTN\b",
    r"\bztn-(check-content|sync-pull|backfill-concepts)\b", r"\bminder-ztn-(" + _ENGINE_SLUG_ALT_HYPHEN + r")\b", r"\bminder_ztn_(" + _ENGINE_SLUG_ALT_UNDERSCORE + r")\b", r"\bztn-platform\b", r"\bztn_platform\b", r"\bminder-minder-memory\b", r"\bminder_minder_memory\b",
    r"\bZTNVault\b", r"\bZTNAgentRunner\b", r"\bztn-bridge\b", r"\bsync-ztn\.sh\b", r"\bsearchZtn\b",
    r"\bMinder[ \-]Minder Memory\b", r"\bminder Minder Memory\b", r"(?i)\bмайндер Minder Memory\b",
})
# In code, the bare upper-case word is prose (a comment, a docstring, a
# user-facing string) unless it is glued to identifier syntax: `ZTN =`,
# `ZTN(`, `ZTN.`, `x.ZTN`, `ZTN_X`. Those stay.
_CODE_PROSE_ZTN = (re.compile(r"(?<![.\w])ZTN(?!\s*[=(]|[\w.])"), PRODUCT_NAME)
_COMPILED_CODE_MAP: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pat), repl) for pat, repl in TOKEN_MAP if pat in _CODE_SAFE_RULES
) + (_CODE_PROSE_ZTN,)

# Everything under the base is DATA even when its suffix says code: vault
# configuration names the CSS snippet files the engine also renames, batch
# manifests and buffers name records and concepts by slug — they are rewritten
# as prose so ids and files move together.
_PROSE_EVEN_IF_CODE: tuple[str, ...] = ("zettelkasten/", "integrations/obsidian/vault-config/")
# ...except the engine's own python under the base, which IS code.
_CODE_EVEN_UNDER_BASE: tuple[str, ...] = ("zettelkasten/_system/scripts/",)


def is_code_path(rel: str, name: str, suffix: str) -> bool:
    """Code mode for source files; prose mode for everything under the base
    (records, state, batches, vault config — data whose ids and slugs move
    with the files they name)."""
    if rel.startswith(_CODE_EVEN_UNDER_BASE):
        return True
    if rel.startswith(_PROSE_EVEN_IF_CODE):
        return False
    return suffix in CODE_SUFFIXES or name in ("install.sh", "uninstall.sh", "Dockerfile")
# Written by the engine's own installer, which runs (through migration 031)
# earlier in the SAME update. Whatever it seeds arrives either tracked-and-
# modified or brand new — the two shapes that are otherwise indistinguishable
# from the owner having left work unsaved. Counting them told every owner their
# notes had been rewritten when nothing of theirs had been touched, which is
# both untrue and the fastest way to make a real warning unreadable.
#
# The dashboard is listed under both spellings because the counts are taken
# against the path as it stood BEFORE this migration renamed it.
_ENGINE_SEEDED: tuple[str, ...] = (
    "zettelkasten/.obsidian/",
    "zettelkasten/5_meta/help/",
    "zettelkasten/minder-memory.md",
    "zettelkasten/minder-ztn.md",
)
_COMPILED_PROTECTED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pat) for pat in PROTECTED_PATTERNS
)
# Anything that still smells of the old name after the map ran.
_RESIDUE_RE = re.compile(r"ztn|ЗТН|зтн", re.IGNORECASE)

# Two opt-outs for text that must keep an old token ON PURPOSE — a reader that
# accepts the legacy environment name, a test whose input is the old form, a
# retirement row. A line carrying LINE_KEEP is left as written; a file carrying
# FILE_KEEP anywhere is left whole. Both are searched for literally.
LINE_KEEP = "rebrand:keep"
FILE_KEEP = "minder-memory-rebrand: keep-legacy-tokens"


def rebrand_text(text: str, *, code: bool = False) -> str:
    """Apply the token map to one text, honouring protected spans and opt-outs.

    `code=True` selects the code-safe subset of the map (see CODE_SUFFIXES).
    """
    if FILE_KEEP in text:
        return text
    if LINE_KEEP in text:
        lines = text.split("\n")
        return "\n".join(line if LINE_KEEP in line else _rebrand_span(line, code=code) for line in lines)
    return _rebrand_span(text, code=code)


def _rebrand_span(text: str, *, code: bool = False) -> str:
    kept: list[str] = []

    def _protect(m: re.Match[str]) -> str:
        kept.append(m.group(0))
        return _SENTINEL.format(len(kept) - 1)

    for pat in _COMPILED_PROTECTED:
        text = pat.sub(_protect, text)
    # The owner's own names — folders, credentials, their extensions of a skill
    # name — come from `lib.ownership`, which is the one place that answers «is
    # this name ours». Replaced from the end so earlier offsets stay valid.
    for start, end in reversed(ownership.own_name_spans(text, _OWNER_BASE)):
        kept.append(text[start:end])
        text = text[:start] + _SENTINEL.format(len(kept) - 1) + text[end:]
    for pat, repl in (_COMPILED_CODE_MAP if code else _COMPILED_MAP):
        text = pat.sub(repl, text)
    for index, original in enumerate(kept):
        text = text.replace(_SENTINEL.format(index), original)
    return text


# `ztn-recap` in prose is the slash command and becomes `/minder:mem:recap`; in a
# file name a colon is not a legal character on Windows, so the segment takes the
# directory-safe form the skills use.
_PATH_SEGMENT_COMMAND = re.compile(r"/?minder:mem:(recap|search)\b")


def rebrand_path(relpath: str, *, code: bool = False) -> str:
    """The new relative path of a file, segment by segment.

    A code file's name follows the code-safe map: a module called after a bare
    identifier keeps its name, so the imports that reference it keep resolving.

    Commands are the one structural move: `integrations/claude-code/commands/
    ztn-<name>.md` becomes `commands/minder/mem/<name>.md`, because that is how
    Claude Code namespaces a command. Everything else is the token map applied
    to each path segment, so a file name and every reference to it move by the
    same rule.
    """
    parts = PurePosixPath(relpath).parts
    if (
        len(parts) >= 2
        and "/".join(parts[:-1]).endswith("integrations/claude-code/commands")
        and parts[-1].startswith("ztn-")
    ):
        return "/".join(parts[:-1]) + "/minder/mem/" + parts[-1][len("ztn-"):]  # rebrand:keep
    return "/".join(_PATH_SEGMENT_COMMAND.sub(SKILL_PREFIX + r"\1", rebrand_text(p, code=code)) for p in parts)


# -----------------------------------------------------------------------------
# Scopes
# -----------------------------------------------------------------------------

# Relative paths (or directory prefixes with a trailing slash) never rewritten.
NEVER_TOUCH: tuple[str, ...] = (
    ".git/",
    "zettelkasten/_sources/",
    "docs/CHANGELOG.md",
    "zettelkasten/5_meta/DECISION_LOG.md",
    "zettelkasten/5_meta/help/",   # derived from docs/ by seed.sh --refresh-help; regenerated, never rewritten
    # A credential key is the OWNER's name for something outside the repository.
    # The engine renames what it owns; renaming a key here would break its
    # role's lookup at the next tick, with an error naming nothing — and the
    # value is encrypted, so nobody would spot the change by reading the file.
    "zettelkasten/_system/state/secrets.enc.json",
    "integrations/claude-code/built/",
    "node_modules/",
    "__pycache__/",
    ".venv/", "venv/",
    "_local-build/",
)
# Hand-authored in this change; the map must not touch its alias list.
_HAND_AUTHORED: tuple[str, ...] = (
    "integrations/claude-code/rules/minder-memory.md",
)

TEXT_SUFFIXES = frozenset({
    ".md", ".yml", ".yaml", ".sh", ".py", ".txt", ".json", ".toml", ".cfg",
    ".ini", ".ps1", ".css", ".js", ".ts", ".tsx", ".mjs", ".html", ".plist",
    ".conf", ".template", ".example", ".mmd", ".svg", ".csv", ".tsv", ".jsonl", ".env", "",
})


def _never(rel: str) -> bool:
    if any(rel == p or rel.startswith(p) for p in NEVER_TOUCH):
        return True
    return rel in _HAND_AUTHORED


def classify(rel: str) -> str:
    """Which class of surface a path belongs to — for the inventory, not for logic."""
    if rel.startswith("zettelkasten/_sources/"):
        return "source"
    if rel.startswith(("zettelkasten/_records/", "zettelkasten/1_projects/", "zettelkasten/2_areas/",
                       "zettelkasten/3_resources/", "zettelkasten/4_archive/", "zettelkasten/5_meta/mocs/",
                       "zettelkasten/6_posts/", "zettelkasten/0_constitution/axiom/",
                       "zettelkasten/0_constitution/principle/", "zettelkasten/0_constitution/rule/",
                       "zettelkasten/_system/roles/")):
        return "owner-data"
    if rel.startswith("integrations/claude-code/built/"):
        return "generated"
    if rel.startswith(("scripts/", "zettelkasten/_system/scripts/", ".github/", ".claude/")):
        return "engine-code"
    if rel.startswith("platform/"):
        return "design-record"
    return "contract-prose"


# -----------------------------------------------------------------------------
# Walking, renaming, rewriting
# -----------------------------------------------------------------------------

@dataclass
class Change:
    path: str
    new_path: str | None = None
    tokens: dict[str, int] = field(default_factory=dict)
    kind: str = "rewrite"        # rewrite | rename | rename+rewrite | relink
    cls: str = ""


@dataclass
class Report:
    root: str
    dry_run: bool
    changes: list[Change] = field(default_factory=list)
    skipped_binary: list[str] = field(default_factory=list)
    skipped_dirty: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    residue: dict[str, int] = field(default_factory=dict)
    # `minder-ztn-<suffix>` occurrences left alone: the owner's own repository
    # or folder, reported so the digest can say why they still read that way.
    own_name: dict[str, int] = field(default_factory=dict)
    # Files that were rewritten while carrying uncommitted work. Tracked ones
    # have their previous text in git; untracked ones have it nowhere.
    rewritten_dirty: list[str] = field(default_factory=list)
    rewritten_unsaved: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "root": self.root, "dry_run": self.dry_run,
            "changed": len(self.changes),
            "renamed": sum(1 for c in self.changes if c.new_path),
            "changes": [c.__dict__ for c in self.changes],
            "skipped_binary": self.skipped_binary,
            "skipped_dirty": self.skipped_dirty,
            "conflicts": self.conflicts,
            "residue": self.residue,
            "own_name": self.own_name,
            "rewritten_dirty": self.rewritten_dirty,
            "rewritten_unsaved": self.rewritten_unsaved,
        }, ensure_ascii=False, sort_keys=True, indent=1)


def _git_tracked(root: Path) -> set[str] | None:
    """Tracked + untracked-but-not-ignored files, or None when not a git repo."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}


def _candidates(root: Path) -> list[str]:
    tracked = _git_tracked(root)
    if tracked is not None:
        return sorted(rel for rel in tracked if not _never(rel))
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = [d for d in dirnames if not _never(rel_dir + d + "/")]
        for fn in filenames:
            rel = rel_dir + fn
            if not _never(rel):
                found.append(rel)
    return sorted(found)


def _count_tokens(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in re.finditer(r"[A-Za-z0-9_./:{}$\-]*(?:[zZ][tT][nN]|ЗТН|зтн)[A-Za-z0-9_./:{}\-]*", text):
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    return counts


def _rename(root: Path, old: str, new: str, *, use_git: bool) -> None:
    dst = root / new
    dst.parent.mkdir(parents=True, exist_ok=True)
    if use_git:
        subprocess.run(["git", "-C", str(root), "mv", "-k", old, new], check=False)
        if (root / old).exists() or (root / old).is_symlink():
            os.replace(root / old, dst)
            subprocess.run(["git", "-C", str(root), "add", "-A", "--", old, new], check=False)
    else:
        os.replace(root / old, dst)
    # A directory emptied by the move is not a file git tracks, so nothing else
    # would ever remove it — and an empty `ztn-<skill>/` beside the new one is
    # exactly what the retirement gate refuses.
    parent = (root / old).parent
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _git_dirty(root: Path) -> set[str]:
    """Paths with uncommitted changes — somebody's work in flight."""
    return _git_unsaved(root)[0]


def _git_unsaved(root: Path) -> tuple[set[str], set[str]]:
    """(everything uncommitted, the subset git has never seen).

    The split matters when the rename runs over them anyway: a tracked file's
    previous text is recoverable from git under its old name, an untracked
    one's is recoverable from nowhere. Reporting both as one number would
    promise a recovery that does not exist for half of them.
    """
    try:
        # `-uall`: without it git collapses a wholly untracked directory to
        # `dir/` and never names the files inside it — so a brand-new folder of
        # drafts, which is precisely the owner's most unsaved work, would be
        # rewritten and reported as nothing at all.
        out = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-uall", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return set(), set()
    dirty: set[str] = set()
    untracked: set[str] = set()
    fields = out.decode("utf-8", "surrogateescape").split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        dirty.add(path)
        if status == "??":
            untracked.add(path)
        # A rename or copy record is followed by a second NUL-terminated
        # field holding the ORIGINAL path; both sides are somebody's work.
        if "R" in status or "C" in status:
            if i < len(fields) and fields[i]:
                dirty.add(fields[i])
            i += 1
    return dirty, untracked


def run(root: Path, *, dry_run: bool,
        exclude: tuple[str, ...] = (), skip_dirty: bool = False) -> Report:
    root = root.resolve()
    global _OWNER_BASE
    base = root / "zettelkasten"
    _OWNER_BASE = base if base.is_dir() else None
    report = Report(root=str(root), dry_run=dry_run)
    use_git = _git_tracked(root) is not None
    # Read BEFORE anything is rewritten — afterwards every file is dirty and
    # the question «what was already unsaved?» can no longer be asked.
    unsaved, untracked = _git_unsaved(root)
    dirty = unsaved if skip_dirty else set()
    for rel in _candidates(root):
        if any(rel == e.rstrip("/") or rel.startswith(e.rstrip("/") + "/") for e in exclude):
            continue
        if rel in dirty:
            report.skipped_dirty.append(rel)
            continue
        src = root / rel
        if src.is_symlink():
            target = os.readlink(src)
            new_target = rebrand_text(target)
            new_rel = rebrand_path(rel)
            if new_target == target and new_rel == rel:
                continue
            change = Change(path=rel, new_path=new_rel if new_rel != rel else None,
                            tokens=_count_tokens(target + " " + rel), kind="relink", cls=classify(rel))
            report.changes.append(change)
            if not dry_run:
                src.unlink()
                dst = root / new_rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(new_target, dst)
                if use_git:
                    subprocess.run(["git", "-C", str(root), "add", "-A", "--", rel, new_rel], check=False)
            continue
        if not src.is_file():
            continue
        if src.suffix.lower() not in TEXT_SUFFIXES and src.name not in (
            "install.sh", "uninstall.sh", "Dockerfile", ".gitignore", ".gitattributes",
        ):
            continue
        try:
            raw = src.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            report.skipped_binary.append(rel)
            continue
        code = is_code_path(rel, src.name, src.suffix.lower())
        new_text = rebrand_text(text, code=code)
        new_rel = rebrand_path(rel, code=code)
        if new_text == text and new_rel == rel:
            continue
        tokens = _count_tokens(text)
        if new_rel != rel:
            for k, v in _count_tokens(rel).items():
                tokens[k] = tokens.get(k, 0) + v
        kind = "rewrite" if new_rel == rel else ("rename" if new_text == text else "rename+rewrite")
        if new_rel != rel and ((root / new_rel).exists() or (root / new_rel).is_symlink()):
            # Both the former and the current name exist. Whatever the owner
            # keeps under the current name is theirs; nothing here overwrites
            # it. The file is left where it is, with its text rewritten, and
            # the collision is reported for the owner to merge by hand.
            kind = "conflict"
            report.conflicts.append(rel)
            new_rel = rel
        report.changes.append(Change(path=rel, new_path=new_rel if new_rel != rel else None,
                                     tokens=tokens, kind=kind, cls=classify(rel)))
        if dry_run:
            continue
        if new_text != text:
            src.write_bytes(new_text.encode("utf-8"))
        if new_rel != rel:
            _rename(root, rel, new_rel, use_git=use_git)
    # What the run rewrote while it was somebody's work in flight. The rename
    # applies to a clone whole — that is the contract — but an owner who has
    # unsaved notes open deserves to be told which ones moved under them.
    changed = {c.path for c in report.changes
               if not c.path.startswith(_ENGINE_SEEDED) and c.path not in _ENGINE_SEEDED}
    # A file that also MOVED is reported `old → new`. Naming only where it used
    # to be sends the owner looking at a path that no longer exists, which is
    # the one thing this warning exists to prevent.
    moved = {c.path: c.new_path for c in report.changes if c.new_path}

    def _display(rel: str) -> str:
        return f"{rel} → {moved[rel]}" if rel in moved else rel

    report.rewritten_dirty = sorted(_display(p) for p in changed & unsaved
                                    if p not in untracked)
    report.rewritten_unsaved = sorted(_display(p) for p in changed & untracked)
    # Residue: what still matches after the run (or would, in a dry run).
    for rel in _candidates(root):
        if any(rel == e.rstrip("/") or rel.startswith(e.rstrip("/") + "/") for e in exclude) or rel in dirty:
            continue
        p = root / rel
        if not p.is_file() or p.is_symlink():
            continue
        try:
            text = p.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        probe = rebrand_text(text, code=is_code_path(rel, p.name, p.suffix.lower())) if dry_run else text
        key = rebrand_path(rel) if dry_run else rel
        # An own-name span carries exactly one old-name match and is EXPLAINED:
        # it is subtracted from the residue so that residue keeps meaning
        # «still unaccounted for», and reported on its own axis instead.
        own = len(ownership.own_name_spans(probe, _OWNER_BASE))
        if own:
            report.own_name[key] = own
        n = len(_RESIDUE_RE.findall(probe)) - own
        if n > 0:
            report.residue[key] = n
    return report


def dirty_sentence(paths: list[str]) -> str:
    """What the owner needs: WHICH files, and where the previous text went.

    Names, not a count: a number tells the owner something happened to work of
    theirs and leaves them to find out what. The whole point of the warning is
    that they can go and look.
    """
    count = len(paths)
    listed = ", ".join(paths)
    if count == 1:
        return ("1 file with uncommitted changes was rewritten in place "
                f"(its previous text is in git under the old name): {listed}")
    return (f"{count} files with uncommitted changes were rewritten in place "
            f"(their previous text is in git under the old name): {listed}")


def unsaved_sentence(paths: list[str]) -> str:
    count = len(paths)
    listed = ", ".join(paths)
    if count == 1:
        return ("1 file git had never seen was also rewritten "
                f"(nothing holds its previous text): {listed}")
    return (f"{count} files git had never seen were also rewritten "
            f"(nothing holds their previous text): {listed}")


def render_inventory(report: Report) -> str:
    lines = [
        "# Rebrand inventory" + (" (dry run)" if report.dry_run else ""),
        "",
        f"<!-- {FILE_KEEP}: this inventory lists the former names by design -->",
        "",
        f"Root: `{report.root}` · files changed: {len(report.changes)} · renamed: "
        f"{sum(1 for c in report.changes if c.new_path)} · binary skipped: {len(report.skipped_binary)}",
        "",
        "| Class | Path | Action | New path | Tokens |",
        "|---|---|---|---|---|",
    ]
    for c in sorted(report.changes, key=lambda c: (c.cls, c.path)):
        toks = ", ".join(f"`{k}`×{v}" for k, v in sorted(c.tokens.items(), key=lambda kv: -kv[1])[:6])
        lines.append(f"| {c.cls} | `{c.path}` | {c.kind} | {('`' + c.new_path + '`') if c.new_path else ''} | {toks} |")
    if report.conflicts:
        lines += ["", "## Not renamed — a file already exists under the new name (merge by hand)", ""]
        lines += [f"- `{rel}`" for rel in report.conflicts]
    if report.skipped_dirty:
        lines += ["", "## Left alone — uncommitted changes belong to somebody's session", ""]
        lines += [f"- `{rel}`" for rel in report.skipped_dirty]
    if report.own_name:
        lines += ["", "## Left alone — these name your own repository, folder or credential", "",
                  "| Path | Occurrences |", "|---|---|"]
        for rel, n in sorted(report.own_name.items()):
            lines.append(f"| `{rel}` | {n} |")
    if report.rewritten_dirty or report.rewritten_unsaved:
        lines += ["", "## Rewritten while unsaved", ""]
        if report.rewritten_dirty:
            lines.append(dirty_sentence(report.rewritten_dirty))
            lines += [f"- `{rel}`" for rel in report.rewritten_dirty]
        if report.rewritten_unsaved:
            lines.append(unsaved_sentence(report.rewritten_unsaved))
            lines += [f"- `{rel}`" for rel in report.rewritten_unsaved]
    if report.residue:
        lines += ["", "## Residue after the run (must each be an allowed one)", "",
                  "| Path | Matches |", "|---|---|"]
        for rel, n in sorted(report.residue.items()):
            lines.append(f"| `{rel}` | {n} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="repository root to rewrite")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--inventory", help="write a markdown inventory of every change to this path")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--exclude", action="append", default=[], metavar="PREFIX",
                    help="relative path prefix to leave untouched (repeatable)")
    ap.add_argument("--skip-dirty", action="store_true",
                    help="leave files with uncommitted changes alone (somebody's work in flight)")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"rebrand: {root} is not a directory", file=sys.stderr)
        return 2
    report = run(root, dry_run=args.dry_run, exclude=tuple(args.exclude), skip_dirty=args.skip_dirty)
    if args.inventory:
        with open(args.inventory, "w", encoding="utf-8", newline="") as handle:
            handle.write(render_inventory(report))
    if args.json:
        print(report.to_json())
    else:
        verb = "would change" if args.dry_run else "changed"
        print(f"rebrand: {verb} {len(report.changes)} file(s), "
              f"{sum(1 for c in report.changes if c.new_path)} renamed, "
              f"{len(report.residue)} file(s) keep the former name on purpose "
              "(aliases, history, migration inputs, your own names)")
        if report.own_name:
            print(f"rebrand: {len(report.own_name)} file(s) name your own repository, folder "
                  "or credential — kept exactly as you wrote them")
        if report.rewritten_dirty:
            print("rebrand: " + dirty_sentence(report.rewritten_dirty))
        if report.rewritten_unsaved:
            print("rebrand: " + unsaved_sentence(report.rewritten_unsaved))
    return 0


if __name__ == "__main__":
    sys.exit(main())
