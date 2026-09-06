"""Shared utilities for constitution scripts.

Deterministic, no LLM. PyYAML is the single external dependency.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable

import yaml

# ---------------------------------------------------------------------------
# Std-stream encoding — one owner for this half of the engine
# ---------------------------------------------------------------------------
#
# Every helper here emits JSONL on stdout that a SKILL parses, and owner text is
# not ASCII. Python encodes std streams through the platform default — cp1252 on
# a stock Windows box — so a single Cyrillic note title raises
# `UnicodeEncodeError` and the helper dies mid-stream. Reading paths from a pipe
# fails the same way in the other direction.
#
# `scripts/lib/portable.py` is the engine-wide owner of this; the two script
# trees always ship together, so importing it is the normal path. The fallback
# exists because `_system/scripts/` must stay runnable on its own — migration
# `014` does exactly that, `cd`-ing here and importing `_common` with nothing
# else on the path. It duplicates one stdlib call, not a decision.
try:  # pragma: no cover - exercised by whichever tree is present
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from lib.portable import (  # noqa: F401
        configure_stdin,
        configure_stdout,
        configure_std_streams,
    )
except ImportError:  # pragma: no cover
    def _reconfigure(stream) -> None:
        fn = getattr(stream, "reconfigure", None)
        if fn is None:
            return
        try:
            fn(newline="\n", encoding="utf-8")
        except (ValueError, OSError):
            return

    def configure_stdout() -> None:
        _reconfigure(sys.stdout)

    def configure_stdin() -> None:
        _reconfigure(sys.stdin)

    def configure_std_streams() -> None:
        configure_stdin()
        configure_stdout()


# -----------------------------------------------------------------------------
# Schema definition (mirrors 0_constitution/CONSTITUTION.md §3)
# -----------------------------------------------------------------------------

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "type",
    "domain",
    "statement",
    "priority_tier",
    "scope",
    "applies_to",
    "status",
)

ALLOWED_TYPES = {"axiom", "principle", "rule"}
# Canonical thirteen — single source of truth for `domains:` / `domain:`.
# Mirrored in `_system/registries/DOMAINS.md`. Treat as immutable at runtime;
# changes require coordinated edits to DOMAINS.md and tests.
ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "work", "career", "personal",
    "identity", "ethics", "health",
    "relationships",
    "learning", "money", "time",
    "ai-interaction", "tech", "meta",
})

# Mirror of Minder's `ConceptDomain` enum
# (`minder/.../domain/value/ConceptDomain.java`). Per-concept-mention scope
# derived downstream from a note's `domains:` + `origin`. NOT used for
# Minder Memory-side validation — kept here as a documentation reference so future
# manifest/consumer work can spot drift between the two axes.
MINDER_CONCEPT_DOMAIN: frozenset[str] = frozenset({
    "work", "personal", "mixed", "unknown",
})
ALLOWED_PRIORITY_TIERS = {1, 2, 3}
ALLOWED_FRAMINGS = {"positive", "negative"}
ALLOWED_BINDINGS = {"hard", "soft"}
ALLOWED_SCOPES = {"shared", "personal", "sensitive"}
ALLOWED_APPLIES_TO = {
    "claude-code", "minder-memory", "chatgpt", "claude-desktop",
    "life-advice", "work-code", "bootstrap", "minder",
}
ALLOWED_CONFIDENCES = {"proven", "working", "experimental"}
ALLOWED_STATUSES = {"active", "candidate", "archived", "placeholder"}


# -----------------------------------------------------------------------------
# Concept-name normalisation per `_system/registries/CONCEPT_NAMING.md`
# -----------------------------------------------------------------------------
#
# Autonomous-pipeline policy: Minder Memory engine resolves concept-name format
# issues with deterministic heuristics — never raises, never blocks owner,
# never surfaces a CLARIFICATION. `normalize_concept_name(raw)` returns
# either a valid snake_case ASCII identifier or `None` to signal "drop
# this entry" — the only fallback when normalisation cannot produce a
# valid name. Callers MUST handle `None` as "skip silently."

CONCEPT_NAME_MAX_LEN = 64
CONCEPT_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_CONCEPT_SEP_RE = re.compile(
    r"[\s\-‐-―−/\\.,;:!?()\[\]{}\"'~%+@#&*=<>^|`]+"
)
_CONCEPT_RUN_US = re.compile(r"_+")

# NOTE: there is deliberately NO mechanical "type-prefix strip" here. A
# bare string cannot tell a redundant type label (`skill_python` = type
# `skill` welded onto `python`) from a compound where the type-word is part
# of the name (`skill_based`, `decision_making`, `value_chain`,
# `event_loop_blocking`). Guessing corrupts graph identity, the one thing
# the concept layer exists to protect — so the engine never guesses. Names
# are normalised mechanically (charset / case / separators / length) and
# kept verbatim otherwise; the only semantic drop is a BARE reserved
# type-word (rule 8, unambiguous — see RESERVED_TYPE_WORDS). Rule 5 ("no
# type prefix in the name") is enforced upstream at extraction by the
# `/minder:mem:process` prompt; a slipped weld is preserved (a cosmetic redundant
# prefix is safe and recoverable) rather than blindly amputated.

# Frozen mirror of Minder's `ConceptType` enum (18 values).
# Source of truth: minder/.../domain/graph/ConceptType.java.
# Mirrored in `_system/registries/CONCEPT_TYPES.md`. Drift detected by
# `test_common.py::TestConceptTypeMirror` (reads Java enum at test time).
# This is the documentation/audit set; emission gate is EMITTED_CONCEPT_TYPES.
CONCEPT_TYPES_ALL: frozenset[str] = frozenset({
    "person", "organization", "project", "idea", "tool", "skill", "location",
    "event", "emotion", "theme",
    "goal", "value", "preference", "constraint", "algorithm", "decision",
    "fact", "other",
})

# Per-type human-readable description, mirrored from Java enum constructor
# strings. Fed into the concept-matcher subagent prompt for disambiguation.
CONCEPT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "person": "People and contacts",
    "organization": "Companies, teams, communities",
    "project": "Projects and initiatives",
    "idea": "Ideas and concepts",
    "tool": "Technologies and instruments",
    "skill": "Skills and competencies",
    "location": "Places and locations",
    "event": "Events and meetings",
    "emotion": "Emotional states",
    "theme": "Topics and themes",
    "goal": "User goals and objectives",
    "value": "Personal values and principles",
    "preference": "User preferences",
    "constraint": "User constraints and rules",
    "algorithm": "Generalized decision patterns and reasoning sequences",
    "decision": "Explicit choices with reasoning and alternatives",
    "fact": "Individual facts and notes",
    "other": "Other concepts",
}

# `type` enum emitted by Minder Memory (lowercase, excludes person/project per
# §"Concept scope" in `_system/docs/batch-format.md`).
# Subset of CONCEPT_TYPES_ALL — gate at emit boundary.
EMITTED_CONCEPT_TYPES: frozenset[str] = CONCEPT_TYPES_ALL - frozenset({
    "person", "project",
})

# Bare type-enum words that collapse to drop per Rule 8 (broad
# classifiers belong in domains/tags, not as concepts). All 18 mirror
# values plus emit-set are reserved as concept-name surface — names
# matching any of these collapse via `normalize_concept_name`.
RESERVED_TYPE_WORDS: frozenset[str] = CONCEPT_TYPES_ALL


def validate_concept_type(value: str | None) -> bool:
    """Return True if value is a member of EMITTED_CONCEPT_TYPES.

    The validation gate at emit boundary: rejects unknown codes,
    rejects `person`/`project` (first-class entities, not concepts),
    rejects empty/null. Caller drops invalid entries silently.
    """
    if value is None or not isinstance(value, str):
        return False
    return value in EMITTED_CONCEPT_TYPES


def normalize_concept_type(raw: str | None) -> str | None:
    """Lowercase + strip + emit-set membership check; None on miss.

    Pure function. Strips surrounding whitespace, lowercases, then
    asserts membership in EMITTED_CONCEPT_TYPES. Returns the
    normalised code or None — caller drops on None.

    `person` and `project` map to None even though they're in the
    18-mirror — the emit boundary excludes them.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if s not in EMITTED_CONCEPT_TYPES:
        return None
    return s


def normalize_concept_name(raw: str | None) -> str | None:
    """Return a valid snake_case ASCII concept name or None to drop.

    Pure function; no side effects. Mirrors CONCEPT_NAMING.md normalisation
    algorithm with autonomous fallbacks:
    - non-ASCII residue after diacritic-fold → drop (None)
    - bare reserved type-word (`theme`, `tool`, …) → drop (None, rule 8)
    - over-length → truncate at last `_` boundary `≤ 64`; hard-cut otherwise

    Type prefixes are NOT stripped — the name is kept verbatim after
    mechanical normalisation (see the module note above for why). The caller
    is responsible for emitting the returned value verbatim or skipping the
    entry on None — never substitute, never raise.
    """
    if raw is None:
        return None
    s = unicodedata.normalize("NFKD", str(raw))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = _CONCEPT_SEP_RE.sub("_", s)
    s = _CONCEPT_RUN_US.sub("_", s)
    s = s.strip("_")
    if not s:
        return None
    if not all(ord(c) < 128 for c in s):
        return None
    if not CONCEPT_NAME_RE.match(s):
        return None
    # Bare type-enum words (`theme`, `tool`, `decision`, `person`,
    # `project`, …) collapse via Rule 8 — broad classifiers belong in
    # domains/tags, not as concepts. This is the ONE semantic drop: a name
    # that IS exactly a type word, not one that merely starts with one
    # (`theme_park`, `decision_making` are kept). `theme_` trims to `theme`
    # via the separator pass and drops here; bare `theme` drops directly.
    # People and projects are first-class entities with their own slots,
    # never routed through the concept channel.
    if s in RESERVED_TYPE_WORDS:
        return None
    if len(s) > CONCEPT_NAME_MAX_LEN:
        truncated = s[:CONCEPT_NAME_MAX_LEN]
        last_us = truncated.rfind("_")
        s = truncated[:last_us] if last_us > 0 else truncated
    if not s:
        return None
    return s


def normalize_concept_list(raw_iter) -> list[str]:
    """Apply normalize_concept_name to each entry; drop Nones; dedup
    preserving first-seen order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in (raw_iter or []):
        n = normalize_concept_name(raw)
        if n is None or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


# -----------------------------------------------------------------------------
# Audience-tag normalisation per `_system/registries/AUDIENCES.md`
# -----------------------------------------------------------------------------

AUDIENCE_CANONICAL: frozenset[str] = frozenset({
    "family", "friends", "work", "professional-network", "world",
})
AUDIENCE_TAG_RE = re.compile(r"^[a-z0-9-]+$")
AUDIENCE_TAG_MIN_LEN = 2
AUDIENCE_TAG_MAX_LEN = 32


HUB_TRIO_FIELDS: tuple[str, ...] = ("origin", "audience_tags", "is_sensitive")

_HUB_FIX_IDS: dict[str, str] = {
    "origin": "hub-origin-derive-autofix",
    "audience_tags": "hub-audience-derive-autofix",
    "is_sensitive": "hub-sensitivity-derive-autofix",
}


def recompute_hub_trio(
    hub_fm: dict, member_trios: list[dict]
) -> tuple[dict, list[dict]]:
    """Derive hub privacy trio from member-note trios.

    Single source of truth for `/minder:mem:process` hub C/D, `/minder:mem:maintain`
    Step 4 hub linkage, and `lint_concept_audit.py` hub-pass logic.

    Derivation rules:
    - `origin` ← dominant origin across members (tie → `personal`)
    - `audience_tags` ← intersection of member audience_tags (only
      audiences ALL members agree on widen the hub)
    - `is_sensitive` ← any-member contagion (`true` if any member is
      sensitive, else `false`)

    **Owner-vs-engine ownership contract via `_engine_derived`.** Hub
    frontmatter carries an `_engine_derived: [field, ...]` list that
    enumerates which trio fields the engine currently owns. Behaviour:

    - Field missing from frontmatter → engine derives, writes value,
      ADDS field name to `_engine_derived`. (First touch on a fresh
      hub leaves all three engine-owned, continuously re-derived.)
    - Field present AND its name in `_engine_derived` → engine
      RE-DERIVES on every call, overwriting prior engine value.
      Membership changed → trio updates automatically.
    - Field present AND name NOT in `_engine_derived` → owner edit;
      engine NEVER touches it. To re-engage the engine, owner removes
      the value AND adds the field name back to `_engine_derived` (or
      simply removes the value — engine re-adds the marker on next
      derive).

    Backward compatibility: if `_engine_derived` is absent and a trio
    field IS present, the engine treats it as owner-set (preserves
    it). This matches the legacy "set once, owner takes over"
    semantics for hubs created before the marker existed; new hubs
    get the marker on first derivation.

    Returns (modified_fm, events). Events list captures every
    re-derivation (not just first-touch) so audit logs reflect
    continuous engine activity.
    """
    events: list[dict] = []
    new_fm = dict(hub_fm)

    if member_trios:
        from collections import Counter
        origins = [m.get("origin", "personal") for m in member_trios
                   if isinstance(m, dict)]
        if origins:
            counter = Counter(origins)
            ranked = counter.most_common()
            if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
                derived_origin = ranked[0][0]
            else:
                derived_origin = "personal"
        else:
            derived_origin = "personal"

        audience_sets: list[set[str]] = []
        for m in member_trios:
            if not isinstance(m, dict):
                continue
            tags = m.get("audience_tags") or []
            if isinstance(tags, list):
                audience_sets.append(set(t for t in tags if isinstance(t, str)))
        if audience_sets:
            derived_audience = sorted(set.intersection(*audience_sets))
        else:
            derived_audience = []

        derived_sens = any(
            bool(m.get("is_sensitive"))
            for m in member_trios
            if isinstance(m, dict)
        )
    else:
        derived_origin = "personal"
        derived_audience = []
        derived_sens = False

    derived_values = {
        "origin": derived_origin,
        "audience_tags": derived_audience,
        "is_sensitive": derived_sens,
    }

    raw_marker = new_fm.get("_engine_derived")
    if isinstance(raw_marker, list):
        engine_owned = {x for x in raw_marker if isinstance(x, str)}
        marker_present = True
    else:
        engine_owned = set()
        marker_present = False

    for field in HUB_TRIO_FIELDS:
        present = field in new_fm
        if not present:
            # Missing → engine derives, takes ownership.
            new_fm[field] = derived_values[field]
            engine_owned.add(field)
            events.append({
                "fix_id": _HUB_FIX_IDS[field],
                "result": derived_values[field],
                "reason": "missing-field",
            })
        elif marker_present and field in engine_owned:
            # Engine-owned and value differs → re-derive.
            if new_fm[field] != derived_values[field]:
                events.append({
                    "fix_id": _HUB_FIX_IDS[field],
                    "result": derived_values[field],
                    "reason": "rederived",
                    "before": new_fm[field],
                })
                new_fm[field] = derived_values[field]
        # else: owner-set (no marker, or marker without this field).
        # Engine does not touch.

    if engine_owned:
        new_fm["_engine_derived"] = sorted(engine_owned)
    elif "_engine_derived" in new_fm and not engine_owned:
        # All fields owner-claimed; clean empty marker.
        del new_fm["_engine_derived"]

    return new_fm, events


def normalize_audience_tag(raw: str | None) -> str | None:
    """Normalise to kebab-case ASCII; return value if well-formed,
    else None. Caller checks against the canonical-five + Extensions
    whitelist to decide accept-vs-drop.

    Autonomous-pipeline policy: never raises; on any uncertainty, return
    None so caller drops the tag. Default empty `[]` audience is always
    safer than a guessed audience.
    """
    if raw is None:
        return None
    s = unicodedata.normalize("NFKD", str(raw))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        return None
    if not AUDIENCE_TAG_RE.match(s):
        return None
    if len(s) < AUDIENCE_TAG_MIN_LEN or len(s) > AUDIENCE_TAG_MAX_LEN:
        return None
    return s


# -----------------------------------------------------------------------------
# Portable filename normalisation (Windows-safe inbox names)
# -----------------------------------------------------------------------------
#
# NTFS forbids  < > : " / \ | ? *  and control chars in path segments,
# trailing dots/spaces, and reserved device basenames (CON, PRN, …).
# Producer tools (Plaud and other voice recorders) emit per-item folders
# named with pure-ISO timestamps (`2026-04-29T14:09:30Z`) whose colons make
# the path uncreatable on Windows and break `git checkout` on any Windows
# clone that pulls such a path. New inbox items are therefore normalised at
# ingestion (`/minder:mem:process` pre-scan) and before commit (`/minder:mem:save`
# pre-pass); `/minder:mem:lint` Scan A.10 is the backstop. Existing already-
# processed paths are grandfathered — references to them never rewrite.

WINDOWS_RESERVED_BASENAMES: frozenset[str] = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_PORTABLE_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def normalize_portable_name(raw: str | None) -> str | None:
    """Return a Windows/POSIX-portable file or folder name, or None to drop.

    Pure function; no side effects; idempotent (f(f(x)) == f(x)).
    - illegal characters (< > : " / \\ | ? * and control chars) → `-`
    - trailing dots / spaces stripped (NTFS forbids them at segment end)
    - reserved device basenames (CON, PRN, AUX, NUL, COM1-9, LPT1-9 —
      any case, with or without extension) → prefixed with `_`
    - empty result → None; the caller skips or surfaces, never substitutes
    """
    if raw is None:
        return None
    s = _PORTABLE_ILLEGAL_RE.sub("-", str(raw))
    s = s.rstrip(" .")
    if not s:
        return None
    stem = s.split(".", 1)[0]
    if stem.lower() in WINDOWS_RESERVED_BASENAMES:
        s = "_" + s
    return s


def is_portable_name(raw: str | None) -> bool:
    """True when the name is already portable (normalisation is a no-op)."""
    return raw is not None and normalize_portable_name(raw) == raw


# -----------------------------------------------------------------------------
# Domain normalisation per `_system/registries/DOMAINS.md`
# -----------------------------------------------------------------------------
#
# Same shape as audience normalisation: kebab-case ASCII, length 2..32, caller
# decides accept-vs-drop against canonical 13 ∪ active Extensions.
#
# Slash-syntax handling. Real corpus contains values like `work/process`,
# `personal/psychology` — owner's compact notation for "this entity belongs
# to MULTIPLE domains: work AND process". The Minder Memory axis is flat (no hierarchy)
# but it IS multi-valued, so slash entries split into independent values.
# Each part is normalised + filtered against the accept set independently.
# Real-corpus consequence: `work/process` keeps `work` (canonical) and drops
# `process` (not in whitelist) — same outcome as before — but `work/learning`
# keeps BOTH (both canonical), which the previous "prefix-only" policy lost.

DOMAIN_RE = re.compile(r"^[a-z0-9-]+$")
DOMAIN_MIN_LEN = 2
DOMAIN_MAX_LEN = 32


def normalize_domain(raw: str | None) -> str | None:
    """Strict single-value normalisation to kebab-case ASCII; return value if
    well-formed, else None.

    No slash handling — slash is treated as an irrecoverable separator that
    indicates multi-valued input. Callers that need to expand slash entries
    use `expand_domain_entry()` instead, which splits before normalising.
    Direct `normalize_domain("work/process")` returns None because the
    slash makes the string non-well-formed for a single-value slot.

    Autonomous-pipeline policy: never raises. On any irrecoverable shape,
    return None so the caller drops the value silently.
    """
    if raw is None:
        return None
    s = unicodedata.normalize("NFKD", str(raw))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        return None
    if not DOMAIN_RE.match(s):
        return None
    if len(s) < DOMAIN_MIN_LEN or len(s) > DOMAIN_MAX_LEN:
        return None
    return s


def expand_domain_entry(raw: str | None) -> list[str]:
    """Expand a single raw entry into zero, one, or many normalised values.

    Slash-syntax splits: `work/process` → `[work, process]` (each part runs
    through `normalize_domain` independently). Non-slash input collapses to
    a single-element list (`[work]`) or empty (`[]`) on irrecoverable shape.

    Returns deduplicated list preserving first-seen order. Caller filters
    against the accept set; this function only handles the format substrate.
    """
    if raw is None:
        return []
    if not isinstance(raw, str):
        return []
    parts = [p.strip() for p in raw.split("/")] if "/" in raw else [raw]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        n = normalize_domain(part)
        if n is None or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def normalize_domain_list(raw_iter, accept_set: Iterable[str] | None = None) -> list[str]:
    """Expand each entry via `expand_domain_entry` (slash-split aware), then
    filter against the accept set; dedup preserving first-seen order.

    `accept_set` defaults to ALLOWED_DOMAINS — pass `ALLOWED_DOMAINS | extensions`
    when extension-aware filtering is needed.
    """
    accept = frozenset(accept_set) if accept_set is not None else ALLOWED_DOMAINS
    seen: set[str] = set()
    out: list[str] = []
    for raw in (raw_iter or []):
        for n in expand_domain_entry(raw):
            if n in accept and n not in seen:
                seen.add(n)
                out.append(n)
    return out


# -----------------------------------------------------------------------------
# Generic Extensions-table parser (shared by AUDIENCES.md / DOMAINS.md / future)
# -----------------------------------------------------------------------------

_EXTENSIONS_BLOCK_RE = re.compile(
    r"<!-- BEGIN extensions -->(.*?)<!-- END extensions -->", re.DOTALL,
)


def parse_extensions_table(
    path: Path,
    canonical_blacklist: Iterable[str] | None = None,
) -> set[str]:
    """Parse the `<!-- BEGIN extensions --> ... <!-- END extensions -->` block
    from a registry markdown file (AUDIENCES.md, DOMAINS.md, ...).

    Table shape: `| Name | Added | Status | Purpose | Notes |`. Returns the
    set of NAME values whose Status does not start with `deprecated`. Tolerant
    of missing file or malformed table — returns empty set on any failure.

    `canonical_blacklist` (lower-cased internally) silently rejects any
    extension whose case-folded name equals a canonical-set member —
    enforces the «Extensions cannot be equal to a canonical word
    (case-folded)» rule documented in AUDIENCES.md and DOMAINS.md. The
    canonical row wins; the conflicting extension is dropped at parse
    time without surfacing — owner notices missing acceptance and
    renames to a non-conflicting form.

    Single source of truth — older lint / emit helpers carry their own
    near-identical implementations and may migrate to this when their
    callers are next touched.
    """
    if not path.exists():
        return set()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    m = _EXTENSIONS_BLOCK_RE.search(text)
    if not m:
        return set()
    blacklist = {c.lower() for c in (canonical_blacklist or ())}
    out: set[str] = set()
    for line in m.group(1).splitlines():
        if not line.strip().startswith("|"):
            continue
        if "---" in line:  # table separator row
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        name, _added, status = cells[0], cells[1], cells[2]
        if not name or name.lower() in {"tag", "domain", "name"}:
            continue
        if name.startswith("_(") or name in {"—", "-"}:
            continue
        if status.lower().startswith("deprecated"):
            continue
        if name.lower() in blacklist:
            # Reserved-keyword conflict: extension matches canonical
            # case-folded. Doc contract is silent-drop; canonical wins.
            continue
        out.add(name)
    return out


# -----------------------------------------------------------------------------
# Entity registry — the project registry as a set of identities
# -----------------------------------------------------------------------------
#
# An identity is anything that has an identifier, a registry row, and places
# that refer to it. The registry is the only authority on what an identifier
# currently means: a live entity, an entity on a different axis, or a retired
# identifier that must be read as its successor. Parsing it lives here rather
# than in a scanner because more than one consumer needs the same answer, and
# two parsers of one registry are two answers to one question.
#
# Matching against these identifiers is EXACT string equality, never substring:
# `hub-{id}-{something}` is a different identity that merely shares a prefix.

REGISTRY_CATEGORIES: tuple[str, ...] = ("project", "trajectory", "consolidated")

# The people registry's own categories. `person` is a live row — including a
# row whose tier dropped to stale, because a tier drop is archival and leaves
# the identifier valid. `consolidated` is the retired half, and is named after
# the project registry's retired category on purpose: every consumer asks the
# same question of both registries and must not need a per-registry branch to
# ask it.
PEOPLE_REGISTRY_CATEGORIES: tuple[str, ...] = ("person", "consolidated")

# The four kinds of identity change (SYSTEM_CONFIG → Identity Contract). Only
# three of them ever reach a retirement row — see `RETIREMENT_KINDS` — because
# a `reclassify` leaves the identity valid and is stated by which section of
# the registry it lives in, not by a row recording its end.
#
# `IDENTITY_KIND_UNKNOWN` is what a retirement row whose kind could not be read
# yields. It is a report, never a guess: a row that does not say what happened
# to it is work for the owner, not an inference for the scanner.
IDENTITY_KINDS: tuple[str, ...] = (
    "merge", "rename", "split", "reclassify", "void",
)
IDENTITY_KIND_UNKNOWN = "unknown"

# How many successors each kind's row must declare. A rule the row can break,
# which is the point: a row that breaks it is a defect OF THE ROW, reported
# once against the registry, rather than a mystery repeated at every reference
# that pointed at it.
SUCCESSOR_ARITY: dict[str, tuple[int, int | None]] = {
    "merge": (1, 1),
    "rename": (1, 1),
    "split": (2, None),
    "void": (0, 0),
}

# A registry identifier: lowercase slug, hyphen/underscore allowed, starting
# with a digit or a letter. Rejects header cells ("ID", "Old ID"), separator
# rows ("---") and placeholder cells ("_(empty)_", "-").
REGISTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# `[[hub-successor]]`, `[[successor]]`, `` `successor` `` — the three shapes a
# successor cell takes. A backticked identifier wins over a wikilink, because
# a row that carries both spells the wikilink as the hub and the backtick as
# the identifier proper.
_REGISTRY_BACKTICK_RE = re.compile(r"`([^`]+)`")
_REGISTRY_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_HUB_PREFIX = "hub-"


@dataclass(frozen=True)
class RegistryEntry:
    """One identifier as the registry declares it.

    `category` is one of `REGISTRY_CATEGORIES` / `PEOPLE_REGISTRY_CATEGORIES`.
    `successor` is the identifier that replaces this one, and is present only
    for a retired identifier whose row names one — a retirement with no
    successor (the entity turned out never to have existed) leaves it `None`,
    and so does any live row.

    `kind` is the kind of identity change (`IDENTITY_KINDS`, or
    `IDENTITY_KIND_UNKNOWN` when the row does not say), and is set only by a
    registry that declares it. A registry whose retirement table does not carry
    the kind yet leaves it `None` — absent, which is not the same statement as
    `unknown`.
    """

    entity_id: str
    category: str
    successor: str | None = None
    status: str = ""
    kind: str | None = None
    # Every successor the row declares, in the order it declares them. A
    # `split` names two or more and leaves `successor` None: there is no single
    # identifier its references migrate to, and offering one would be the
    # scanner choosing on the owner's behalf which of the two a given sentence
    # meant. Every other kind names at most one, and `successor` is it.
    successors: tuple[str, ...] = ()
    # Whether the KIND came from a column the table declares, rather than from
    # prose inference or from nothing at all. A row that had somewhere to state
    # its kind and did not is a defect; a table with no such column is the
    # older shape, and flagging it would flag every retirement recorded before
    # the column existed.
    kind_declared: bool = False


# A section header no rule recognises. NOT a category — the whole point is that
# nothing has classified it, so no row under it is claimed to be anything.
REGISTRY_SECTION_UNKNOWN = "unknown-section"

# The headers that name a project section. A whitelist rather than a default,
# and the difference is the entire reason this constant exists: an unrecognised
# heading used to fall through to `project`, which read every retired
# identifier under a renamed heading as an ACTIVE PROJECT. Rename `## Retired
# Identifiers` — a friend tidying their registry, a translation, a future
# engine rename — and every retirement silently un-happens, while the audit
# reports clean because there is nothing retired left to have residue. It fails
# green, which is the failure mode worth spending a whitelist on.
_PROJECT_SECTION_MARKERS: tuple[str, ...] = (
    "project registry", "projects", "project", "active", "completed",
    "archived", "in progress", "on hold", "paused", "planned", "backlog",
)


def registry_section_category(header: str) -> str | None:
    """Map a registry `#`-header to a category.

    Returns `None` for a section to skip (documentation), a category for a
    section this engine recognises, and `REGISTRY_SECTION_UNKNOWN` for a
    heading no rule claims. The third is not a default and never becomes one:
    a heading nobody recognises might be owner prose, a section the engine has
    not learned yet, or a typo in a heading that matters, and guessing between
    those is how a retirement section stops existing without anyone noticing.
    Rows under it are registered as nothing and the section is reported.

    The retirement section answers to `Retired Identifiers` (the shipped
    template, named for all the kinds it holds) and to `Consolidated /
    superseded` (what clones predating the rename still call it). Both must
    resolve for as long as both exist in the wild.
    """
    h = header.lower()
    if "template" in h:
        return None
    if "trajector" in h:
        return "trajectory"
    if "consolidat" in h or "supersed" in h or "retired" in h:
        return "consolidated"
    if any(marker in h for marker in _PROJECT_SECTION_MARKERS):
        return "project"
    return REGISTRY_SECTION_UNKNOWN


def _registry_successor(cell: str) -> str | None:
    """Read the successor identifier out of a retirement row's last cell."""
    cell = cell.strip()
    if not cell or cell in {"-", "—", "–"}:
        return None
    for m in _REGISTRY_BACKTICK_RE.finditer(cell):
        candidate = m.group(1).strip()
        if REGISTRY_ID_RE.match(candidate):
            return candidate
    m = _REGISTRY_WIKILINK_RE.search(cell)
    if m:
        target = m.group(1).strip()
        if target.startswith(_HUB_PREFIX):
            target = target[len(_HUB_PREFIX):]
        if REGISTRY_ID_RE.match(target):
            return target
    stripped = cell.strip("*_` ").strip()
    if REGISTRY_ID_RE.match(stripped):
        return stripped
    return None


def _registry_successors(cell: str) -> list[str]:
    """Every successor identifier a retirement row's cell declares.

    A `split` names two or more, comma-separated; every other kind names at
    most one. Splitting on the comma first and reading each part by the same
    single-successor rules keeps one reading of what a successor looks like —
    a part that is not an identifier simply yields nothing, so prose after a
    comma cannot become a phantom successor.
    """
    parts = cell.split(",") if "," in cell else [cell]
    out: list[str] = []
    for part in parts:
        found = _registry_successor(part)
        if found and found not in out:
            out.append(found)
    return out


def _successors_for_kind(cell: str | None, kind: str | None) -> tuple[
    str | None, tuple[str, ...]
]:
    """`(successor, successors)` for a retirement row.

    `successors` is everything the cell declares, whatever the kind, because
    the arity rule is checked against it and a rule cannot catch what the
    parser already discarded — reading only the first identifier would make a
    `merge` naming two look exactly like a `merge` naming one.

    `successor` is the single identifier references migrate to, and exists only
    when there IS one: a kind that permits one and declares several has no
    deterministic target, so it gets none and the row is reported instead.
    """
    if cell is None:
        return None, ()
    found = _registry_successors(cell)
    if kind == "split" or len(found) != 1:
        return None, tuple(found)
    return found[0], (found[0],)


# -----------------------------------------------------------------------------
# Registry tables — shared reading primitives
# -----------------------------------------------------------------------------
#
# Both registries are markdown tables under headers, and both are mid-schema:
# the columns a retirement row will declare are shipped in the templates and
# absent from most rows on disk. So every reader here works the same way — the
# DECLARED COLUMN WINS when the table's header row names it, and the row's
# prose is the fallback when it does not. One rule, so a consumer never has to
# know which shape the file it just read happened to be in.

_TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")

# Column aliases, per role. The declared column wins whenever it is present;
# these names are what "present" means.
_COL_KIND: frozenset[str] = frozenset({"kind", "change kind", "retirement kind"})
_COL_SUCCESSOR: frozenset[str] = frozenset({
    "successor", "superseded by", "now part of", "merged into", "renamed to",
})
_COL_REASON: frozenset[str] = frozenset({"reason", "status", "note", "notes"})

# The kinds a retirement row can carry. `reclassify` is deliberately absent:
# a reclassified identity stays valid and lives in a different section of its
# registry, and that section is the statement — there is nothing retired to
# record, so a retirement row never declares one.
RETIREMENT_KINDS: tuple[str, ...] = ("merge", "rename", "split", "void")


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    return [c.strip() for c in stripped.strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(
        _TABLE_SEPARATOR_RE.match(c.strip()) for c in cells if c.strip()
    )


def _row_value(row: dict[str, str], names: frozenset[str]) -> str | None:
    for key, value in row.items():
        if key in names:
            return value
    return None


def _declared_kind(row: dict[str, str]) -> str | None:
    """The kind this row declares — `None` when the table has no such column.

    The distinction is load-bearing. A table with no `Kind` column is the older
    registry shape: it never had anywhere to say what happened, and reading
    that as "the row fails to state its kind" would flag every retirement a
    friend recorded before the column existed. A table that HAS the column and
    holds something unreadable in it — a blank cell, a typo, `reclassify`,
    which never produces a retirement row at all — is a row that had somewhere
    to say it and did not, and that is a defect worth reporting.
    """
    if _row_value(row, _COL_KIND) is None:
        return None
    declared = (_row_value(row, _COL_KIND) or "").strip().lower()
    return declared if declared in RETIREMENT_KINDS else IDENTITY_KIND_UNKNOWN


# A cell that holds no identifier and is not trying to: an empty column, a
# dash, a parenthesised placeholder. It is not a malformed identifier and is
# never reported as one.
_PLACEHOLDER_CELL_RE = re.compile(r"^(?:[\s\-—–.·]*|\(.*\))$")


@dataclass(frozen=True)
class RegistryRow:
    """One row of a registry table, as it stands on the page.

    `entity_id` is the identifier when the first cell is one, and `None` when
    it is not. The parsers above drop an unreadable first cell, which is right
    for them — they answer "what does this identifier mean" and a cell that is
    not an identifier has no answer. It is wrong as the WHOLE system's
    behaviour: a mistyped retirement row then looks exactly like no retirement
    row at all, and the identifier it was meant to retire keeps reading as
    live. This view keeps the rejected cell so a caller can report it.

    `category` is the section the row sits in, which is also how a duplicate
    declaration becomes visible: one identifier with a row in two categories is
    a registry saying two things about itself.
    """

    raw: str
    entity_id: str | None
    category: str
    line: int
    # The `#`-header the row sits under, verbatim. Carried so a caller can name
    # the section in a finding rather than a line number in a file the owner
    # then has to open to find out what it was talking about.
    section: str = ""


def registry_rows(
    path: Path,
    section_category: Callable[[str], str | None],
    default_category: str | None = None,
) -> list[RegistryRow]:
    """Every table row of a registry, with the section it sits in.

    Reads by exactly the rules the two registry parsers read by — the same
    table primitives, the same identifier regex, the same "first row a table
    cannot read is its header" convention — so the two never disagree about
    what a row is. Two questions the parsers structurally cannot answer are
    answered here: which rows the registry could not read, and which
    identifiers it declares twice.

    A missing or unreadable registry yields an empty list, the same safe
    degradation the parsers have.
    """
    out: list[RegistryRow] = []
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out

    category = default_category
    section_header = ""
    headers_seen = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            # An unrecognised section is carried through rather than dropped:
            # the rows under it are exactly what a renamed heading makes
            # disappear, and a caller cannot report what it cannot see.
            category = section_category(line)
            section_header = line.lstrip("# ").strip()
            headers_seen = False
            continue
        cells = _table_cells(line)
        if cells is None:
            headers_seen = False
            continue
        if category is None or not cells or _is_separator_row(cells):
            continue
        candidate = cells[0].strip("*_` ").strip()
        if REGISTRY_ID_RE.match(candidate):
            out.append(RegistryRow(
                candidate, candidate, category, lineno, section_header,
            ))
            continue
        if not headers_seen:
            headers_seen = True  # the table's header row
            continue
        if _PLACEHOLDER_CELL_RE.match(candidate):
            continue
        out.append(RegistryRow(
            candidate, None, category, lineno, section_header,
        ))
    return out


def parse_project_registry(root: Path) -> dict[str, RegistryEntry]:
    """Parse the project registry into `{identifier: RegistryEntry}`.

    The registry is the single source of truth for project identity: whether an
    identifier names a project, names something on another axis (a trajectory),
    or is retired — and, when retired, what replaced it. The successor column is
    parsed rather than discarded, because a consumer that knows an identifier is
    dead but not what replaced it can only tell its reader to go and look.

    Safe degradation: a missing or unreadable registry yields an empty mapping,
    which leaves every consumer unable to resolve identity and therefore silent
    — the correct behaviour for a base that has not been set up yet.
    """
    out: dict[str, RegistryEntry] = {}
    path = root / "1_projects" / "PROJECTS.md"
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out

    category = "project"  # rows before the first section header default here
    skip = False
    headers: list[str] | None = None
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            cat = registry_section_category(line)
            # An unrecognised heading registers nothing. Rows under it are not
            # projects, not retirements, not anything — the section is reported
            # by the identity scan instead of being classified by default.
            skip = cat is None or cat == REGISTRY_SECTION_UNKNOWN
            headers = None
            if not skip:
                category = cat
            continue
        if skip:
            continue
        cells = _table_cells(line)
        if cells is None:
            headers = None
            continue
        if not cells or _is_separator_row(cells):
            continue
        # strip wrapping markdown emphasis from placeholder cells, e.g.
        # `_(empty)_` → `(empty)` — still rejected by the slug regex.
        candidate = cells[0].strip("*_` ").strip()
        if not REGISTRY_ID_RE.match(candidate):
            if headers is None:
                headers = [c.lower() for c in cells]
            continue
        row = dict(zip(headers, cells)) if headers else {}
        successor = None
        successors: tuple[str, ...] = ()
        kind = None
        kind_declared = False
        status = cells[1] if len(cells) > 1 else ""
        if category == "consolidated":
            # Kind is read only where the registry declares it. This registry
            # has no prose convention for it, and inferring one would put a
            # guess where the reader expects a statement. It is read first
            # because it decides whether the successor cell is read as one
            # identifier or as several.
            kind = _declared_kind(row)
            kind_declared = kind is not None
            # Declared column first; the last cell is the fallback for the
            # older shape, where the successor is simply the final column.
            declared = _row_value(row, _COL_SUCCESSOR)
            if declared is None and len(cells) > 1:
                declared = cells[-1]
            successor, successors = _successors_for_kind(declared, kind)
        out[candidate] = RegistryEntry(
            entity_id=candidate,
            category=category,
            successor=successor,
            status=status,
            kind=kind,
            successors=successors,
            kind_declared=kind_declared,
        )
    return out


def registry_ids_by_category(
    registry: dict[str, RegistryEntry],
) -> dict[str, set[str]]:
    """`{category: {identifier, ...}}` view over a parsed registry."""
    cats: dict[str, set[str]] = {c: set() for c in REGISTRY_CATEGORIES}
    for entry in registry.values():
        cats.setdefault(entry.category, set()).add(entry.entity_id)
    return cats


# -----------------------------------------------------------------------------
# People registry
# -----------------------------------------------------------------------------
#
# Same question, other registry: what does this identifier currently mean, and
# if it is retired, what replaced it. The people registry answers it in a
# different shape — its retirement table carries a free-text reason today and
# declared columns after the schema migration — so the parser reads the
# declared columns when they are there and falls back to the prose when they
# are not. Both paths produce the same `RegistryEntry`, because a consumer that
# had to know which shape it got would be a second parser wearing one name.
#
# The prose fallback is deliberately conservative: a row it cannot read yields
# `IDENTITY_KIND_UNKNOWN` with no successor, and that is reported. Guessing a
# successor is worse than admitting the row is unreadable — a wrong successor
# silently repoints live references at the wrong identity.

_PEOPLE_SECTIONS_LIVE: tuple[str, ...] = ("people", "stale", "owner")
_PEOPLE_SECTION_RETIRED: tuple[str, ...] = ("removed", "retired", "consolidated")

# Prose shapes of a retirement reason. English and Russian, because the reason
# cell is written by whoever resolved the row, in whichever language they were
# thinking in.
_PROSE_MERGE_RE = re.compile(
    r"\bmerged?\s+(?:with|into)\b|\bслит\w*\s+с\b|\bобъединён\w*\s+с\b",
    re.IGNORECASE,
)
_PROSE_RENAME_RE = re.compile(
    r"\brenamed?\s+(?:to|as)\b|\bпереименован\w*\s+в\b", re.IGNORECASE,
)
_PROSE_VOID_RE = re.compile(
    r"\bunknown\b|\bcould\s*n[o']?t\s+identify\b|\bnot\s+a\s+(?:real\s+)?person\b"
    r"|не\s+удалось\s+опознать|не\s+существу\w*",
    re.IGNORECASE,
)
_PROSE_TOKEN_SPLIT_RE = re.compile(r"[\s,;()«»\"']+")


def people_registry_section_category(header: str) -> str | None:
    """Map a people-registry `#`-header to a category, or None to skip.

    A whitelist rather than a default, because this registry's tail is full of
    reference tables — orgs, roles, the profile template — whose first cell is
    a perfectly valid-looking slug. Defaulting to "person" would register
    `ceo` and `rbs` as people.
    """
    h = header.lstrip("#").strip().lower()
    if not h:
        return None
    if any(h.startswith(s) for s in _PEOPLE_SECTION_RETIRED):
        return "consolidated"
    if h.startswith("people registry") or h == "people":
        return "person"
    # The owner's own row, kept apart from the tier machinery. A live person
    # row like any other as far as identity resolution is concerned.
    if h.startswith("owner"):
        return "person"
    # "Stale People" — a tier drop, which is archival and leaves the identity
    # valid. These rows are live people, not retirements.
    if h.startswith("stale") or "stale" in h.split():
        return "person"
    if any(h.startswith(s) for s in _PEOPLE_SECTIONS_LIVE):
        return "person"
    return None


def _prose_retirement(
    reason: str, live_ids: set[str],
) -> tuple[str, str | None]:
    """`(kind, successor)` read out of a free-text retirement reason.

    The successor is accepted only when the token following the marker is an
    identifier the registry declares live. That is the whole guard against
    guessing: "Merged with the person …" would otherwise hand back `the`.
    """
    for pattern, kind in (
        (_PROSE_MERGE_RE, "merge"),
        (_PROSE_RENAME_RE, "rename"),
    ):
        m = pattern.search(reason)
        if not m:
            continue
        for token in _PROSE_TOKEN_SPLIT_RE.split(reason[m.end():]):
            candidate = token.strip("`[]|#.,;:—–*_ ").strip()
            if candidate.startswith(_HUB_PREFIX):
                candidate = candidate[len(_HUB_PREFIX):]
            if not candidate:
                continue
            if candidate in live_ids:
                return kind, candidate
            break  # only the token directly after the marker may be the successor
        return kind, None
    if _PROSE_VOID_RE.search(reason):
        return "void", None
    return IDENTITY_KIND_UNKNOWN, None


def parse_people_registry(root: Path) -> dict[str, RegistryEntry]:
    """Parse the people registry into `{identifier: RegistryEntry}`.

    Live rows (`## People`, and `## Stale People` — a tier drop is archival,
    never an identity retirement) become `category="person"`. Retirement rows
    (`## Removed`) become `category="consolidated"` and carry the kind of
    identity change plus the successor, read from the declared columns when the
    table has them and from the reason prose when it does not.

    Safe degradation matches the project registry: a missing or unreadable
    registry yields an empty mapping, leaving every consumer silent rather than
    flagging a base that has not been set up yet.
    """
    out: dict[str, RegistryEntry] = {}
    path = root / "3_resources" / "people" / "PEOPLE.md"
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out

    # Two passes: the live rows have to be known before a prose retirement
    # reason can be checked against them.
    live: dict[str, RegistryEntry] = {}
    retired_rows: list[tuple[str, dict[str, str], str]] = []

    category: str | None = None
    headers: list[str] | None = None
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            category = people_registry_section_category(line)
            headers = None
            continue
        cells = _table_cells(line)
        if cells is None:
            headers = None
            continue
        if category is None or _is_separator_row(cells):
            continue
        candidate = cells[0].strip("*_` ").strip()
        if not REGISTRY_ID_RE.match(candidate):
            if headers is None:
                headers = [c.lower() for c in cells]
            continue
        row = dict(zip(headers, cells)) if headers else {}
        if category == "consolidated":
            retired_rows.append((candidate, row, line))
            continue
        live[candidate] = RegistryEntry(
            entity_id=candidate,
            category="person",
            successor=None,
            status=(_row_value(row, _COL_REASON) or ""),
        )

    out.update(live)
    live_ids = set(live)
    for entity_id, row, raw_line in retired_rows:
        reason = _row_value(row, _COL_REASON)
        if reason is None:
            cells = _table_cells(raw_line) or []
            reason = cells[1] if len(cells) > 1 else ""
        declared_successor_cell = _row_value(row, _COL_SUCCESSOR)
        kind = _declared_kind(row)
        kind_declared = kind is not None
        successor, successors = _successors_for_kind(
            declared_successor_cell, kind,
        )
        if kind is None or (successor is None and not successors):
            prose_kind, prose_successor = _prose_retirement(reason, live_ids)
            kind = kind or prose_kind
            if successor is None and not successors and prose_successor:
                successor, successors = prose_successor, (prose_successor,)
        if kind == "void":
            # a void identity never had a successor
            successor, successors = None, ()
        out[entity_id] = RegistryEntry(
            entity_id=entity_id,
            category="consolidated",
            successor=successor,
            status=reason,
            kind=kind,
            successors=successors,
            kind_declared=kind_declared,
        )
    return out


# -----------------------------------------------------------------------------
# Owner identity
# -----------------------------------------------------------------------------
#
# The owner is the one identity every base carries and no registry has to
# declare. Their identifier is on hundreds of live surfaces, so a check that
# reads "absent from the registry, therefore drift" calls the owner of the base
# garbage. The owner is valid by construction, and every identity check asks
# here rather than carrying its own exception.

_CYRILLIC_TRANSLIT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_SOUL_NAME_RE = re.compile(r"^\s*[-*]\s*\*\*Name:\*\*\s*(.+?)\s*$", re.MULTILINE)
_OWNER_SECTION_RE = re.compile(r"^#{1,6}\s*owner\b", re.IGNORECASE)


def transliterate_identifier(name: str) -> str | None:
    """A display name reduced to the registry's identifier form.

    Same shape the people registry's own ID rules describe: transliterated,
    lowercase, hyphen-joined. Returns None when nothing survives — an empty
    identifier is not an identity.
    """
    if not name:
        return None
    out_chars: list[str] = []
    for ch in name.strip().lower():
        if ch in _CYRILLIC_TRANSLIT:
            out_chars.append(_CYRILLIC_TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out_chars.append(ch)
        else:
            out_chars.append(" ")
    slug = "-".join("".join(out_chars).split())
    return slug or None


def owner_identity(root: Path) -> str | None:
    """The owner's identifier — declared if the registry declares it, derived
    from `SOUL.md → ## Identity → Name:` otherwise.

    Declared wins: once the people registry carries an owner section, that row
    is the statement. The derivation exists so a base that has not got one yet
    still knows who its owner is, and so no shipped code has to name a person.
    """
    people = root / "3_resources" / "people" / "PEOPLE.md"
    if people.exists():
        try:
            text = people.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        in_owner = False
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                in_owner = bool(_OWNER_SECTION_RE.match(line.strip()))
                continue
            if not in_owner:
                continue
            cells = _table_cells(line)
            if cells is None or _is_separator_row(cells):
                continue
            candidate = cells[0].strip("*_` ").strip()
            if REGISTRY_ID_RE.match(candidate):
                return candidate

    soul = root / "_system" / "SOUL.md"
    if not soul.exists():
        return None
    try:
        text = soul.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _SOUL_NAME_RE.search(text)
    if not m:
        return None
    return transliterate_identifier(m.group(1))


# Single-context model: every consumer loads every scope.
#
# The `scope` field on principles (shared / personal / sensitive) stays as
# a data marker for future multi-user scenarios (sharing to wife / friends,
# MCP tokens). It does not currently drive any runtime filter — the whole
# tree is visible to every consumer on this machine. Filter logic is
# intentionally absent so the single-user dogfood stays simple; it is a
# one-file diff to re-add when scenarios require narrowing.
ALL_SCOPES_VISIBLE: frozenset[str] = frozenset({"shared", "personal", "sensitive"})


# -----------------------------------------------------------------------------
# Paths (resolved relative to repo root)
# -----------------------------------------------------------------------------

BASE_ENV = "MINDER_MEMORY_BASE"


def base_from_env() -> Path | None:
    """The base named by `MINDER_MEMORY_BASE`, or None when it is not set."""
    value = os.environ.get(BASE_ENV, "").strip()
    return Path(value).resolve() if value else None


def repo_root() -> Path:
    """Return the zettelkasten repo root.

    `MINDER_MEMORY_BASE` overrides; otherwise derive from this file's location.
    """
    env = base_from_env()
    if env is not None:
        return env
    # scripts/_common.py → scripts → _system → zettelkasten
    return Path(__file__).resolve().parent.parent.parent


def constitution_root(base: Path | None = None) -> Path:
    return (base or repo_root()) / "0_constitution"


def system_dir(base: Path | None = None) -> Path:
    return (base or repo_root()) / "_system"


def views_dir(base: Path | None = None) -> Path:
    return system_dir(base) / "views"


def state_dir(base: Path | None = None) -> Path:
    return system_dir(base) / "state"


def registries_dir(base: Path | None = None) -> Path:
    return system_dir(base) / "registries"


def docs_dir(base: Path | None = None) -> Path:
    return system_dir(base) / "docs"


def scripts_dir(base: Path | None = None) -> Path:
    return system_dir(base) / "scripts"


# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------

class ConstitutionError(Exception):
    """Base error. Scripts catch and print to stderr, then sys.exit(1)."""


class SchemaError(ConstitutionError):
    """Frontmatter missing or invalid."""


class ParseError(ConstitutionError):
    """File cannot be parsed at the filesystem / YAML level."""


# -----------------------------------------------------------------------------
# Principle model
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Principle:
    path: Path
    frontmatter: dict
    body: str

    @property
    def id(self) -> str:
        return self.frontmatter["id"]

    @property
    def type(self) -> str:
        return self.frontmatter["type"]

    @property
    def domain(self) -> str:
        return self.frontmatter["domain"]

    @property
    def priority_tier(self) -> int:
        return int(self.frontmatter["priority_tier"])

    @property
    def scope(self) -> str:
        return self.frontmatter["scope"]

    @property
    def applies_to(self) -> list[str]:
        val = self.frontmatter.get("applies_to", [])
        return list(val) if val else []

    @property
    def status(self) -> str:
        return self.frontmatter["status"]

    @property
    def is_core(self) -> bool:
        return bool(self.frontmatter.get("core", False))

    @property
    def is_placeholder(self) -> bool:
        return self.status == "placeholder"

    @property
    def title(self) -> str:
        return self.frontmatter["title"]

    @property
    def statement(self) -> str:
        return str(self.frontmatter["statement"]).strip()

    @property
    def cognitive_axes(self) -> list[str]:
        """Optional axis tags powering hub-cognitive-model.

        Slugs from the cognitive-model lens axis list (single source of
        truth: `_system/registries/lenses/cognitive-model/prompt.md`). The
        schema validator does NOT enforce slug membership — that coupling
        belongs to `render_cognitive_model_hub.py`, which validates each
        slug against the axis SoT and drops unknowns. Here we only expose
        the raw list; non-list / absent → empty.
        """
        val = self.frontmatter.get("cognitive_axes", [])
        if not isinstance(val, list):
            return []
        # Dedup preserving first-seen order — a duplicate slug in the tag must
        # not produce a duplicated [[principle-id]] link in the hub row.
        return list(dict.fromkeys(str(x) for x in val))

    @property
    def source_quote(self) -> str:
        """Optional verbatim owner quote grounding the principle (set on
        promotion of a dimension-tagged candidate). The DEC-3 source quote;
        empty string when absent."""
        val = self.frontmatter.get("source_quote")
        return str(val).strip() if isinstance(val, str) else ""


# -----------------------------------------------------------------------------
# Parsing & validation
# -----------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)


def read_frontmatter(path: Path) -> tuple[dict, str] | None:
    """Generic frontmatter reader used by lint helpers.

    Returns (frontmatter_dict, body_text) or None when the file has no
    frontmatter block, the YAML cannot be parsed, or the YAML root is
    not a mapping. Tolerant of read errors (returns None) — the caller
    decides whether to skip silently or propagate. Distinct from
    `parse_file()` which is principle-schema-aware.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return fm, m.group(2)


def write_frontmatter(path: Path, fm: dict, body: str) -> None:
    """Round-trip frontmatter back to disk preserving body verbatim.

    YAML serialised with sort_keys=False, default_flow_style=False,
    allow_unicode=True. Width 10000 prevents PyYAML wrapping long
    lists. Insertion order on `fm` is preserved.
    """
    yaml_text = yaml.safe_dump(
        fm, sort_keys=False, default_flow_style=False,
        allow_unicode=True, width=10000,
    ).rstrip("\n")
    path.write_text(f"---\n{yaml_text}\n---\n{body}", encoding="utf-8")


def append_frontmatter_list_value(
    path: Path, key: str, value, modified: str | None = None,
) -> bool | None:
    """Add one value to a frontmatter list, creating the key if absent.

    The other write `/minder:mem:maintain` performs by the hundred — a thread
    back-reference into a record's `threads:`. Hand-rolled, it is the same
    hazard as the trio write next door: a list built by string concatenation
    is a list that can be built wrong, and a note whose frontmatter stops
    parsing is invisible to every scan rather than merely missing a field.
    One run wrote 135 of these and spent a whole step afterwards checking it
    had not broken anything, which is the tell that the operation wanted a
    function.

    Returns `True` when the value was added, `False` when it was already
    there (no write, so no `modified:` churn), and `None` when the
    frontmatter cannot be read — that file is left exactly as it is.

    An existing non-list value is NOT coerced: it is somebody's data in a
    shape this function does not understand, and overwriting it to fit would
    destroy the thing it is meant to preserve. Reported as `None`, same as
    unreadable.
    """
    read = read_frontmatter(path)
    if read is None:
        return None
    fm, body = read
    current = fm.get(key)
    if current is None:
        current = []
    elif not isinstance(current, list):
        return None
    if value in current:
        return False
    fm[key] = list(current) + [value]
    if modified is not None:
        fm["modified"] = modified
    write_frontmatter(path, fm, body)
    return True


def apply_hub_trio(
    path: Path, member_trios: list, modified: str | None = None,
) -> dict | None:
    """Recompute a hub's privacy trio and write it back. The ONLY writer.

    `recompute_hub_trio` decides what the trio should be; this puts it on
    disk. They were separate halves of one operation, and only the deciding
    half had a home — so every caller re-invented the writing half as ad-hoc
    YAML surgery, once per run, by hand.

    That is not a stylistic complaint. One such hand-write emitted
    `{is_sensitive: true}` and `_engine_derived: [a, b, c]` — flow style, into
    a block-style frontmatter — and the hub stopped parsing entirely: invisible
    to every downstream scan, not just wrong in one field. The run that did it
    happened to re-read the file and repair itself, which is luck, not a
    mechanism. `write_frontmatter` has always serialised block style; nothing
    was missing except a reason to call it.

    Returns `{"changed", "events", "trio", "_engine_derived"}`, or `None` when
    the frontmatter cannot be read — an unreadable hub is left untouched and
    reported, never rewritten from a guess.

    `modified` is stamped ONLY when the trio actually changed, so a no-op
    recompute does not churn the file and every `modified:` bump means
    something really moved.
    """
    read = read_frontmatter(path)
    if read is None:
        return None
    fm, body = read
    new_fm, events = recompute_hub_trio(fm, member_trios)

    # Compared by MEANING, not by dict equality. `recompute_hub_trio` rebuilds
    # `_engine_derived` from a set, so its order can differ from what is on
    # disk while saying exactly the same thing. Under `!=` that reads as a
    # change, and then every hub is rewritten on every run — a corpus-wide
    # `modified:` bump each night that means nothing and buries the ones that
    # do. Order is not content here, so it does not count as one.
    def signature(candidate: dict) -> tuple:
        marker = candidate.get("_engine_derived")
        return (
            candidate.get("origin"),
            tuple(candidate.get("audience_tags") or []),
            bool(candidate.get("is_sensitive")),
            frozenset(marker) if isinstance(marker, list) else None,
        )

    changed = signature(new_fm) != signature(fm)
    if changed and modified is not None:
        new_fm["modified"] = modified
    if changed:
        write_frontmatter(path, new_fm, body)
    return {
        "changed": changed,
        "events": events,
        "trio": {
            key: new_fm.get(key)
            for key in ("origin", "audience_tags", "is_sensitive")
        },
        "_engine_derived": new_fm.get("_engine_derived"),
    }


def frontmatter_closed_before_body(path: Path) -> bool:
    """True when the YAML fence closes before any body ``## `` heading.

    Detects the producer corruption where a body section (e.g.
    ``## Evidence Trail``) and its bullets are written *inside* the
    frontmatter block, before the closing ``---``. That makes
    ``yaml.safe_load`` fail (a ``- ...`` bullet becomes a root sequence
    item mixed with the mapping) and ``read_frontmatter`` return None.

    The closing fence is matched at column 0 only (``line == "---"``), so an
    indented ``---`` inside a block-scalar value — which ``yaml.safe_dump``
    can emit for a value that itself contains ``---`` — cannot be mistaken
    for the fence and mask a real heading below it. The opening probe stays
    tolerant (it only decides "is this a frontmatter file at all").

    This is a structural line invariant; a caller that must be certain a
    note is *usable* combines it with ``read_frontmatter(path) is not None``
    — the genuine corruption fails both, a benign parseable shape fails
    neither (so the AND at the call site suppresses false positives).

    Returns True when the file has no opening fence (nothing to misplace)
    or the column-0 closing fence precedes every ``## `` heading. Returns
    False when a ``## `` heading appears before the closing fence, or the
    opening fence never closes.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True  # unreadable — not this defect; caller handles I/O
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r").strip() != "---":
        return True  # no frontmatter block — nothing to misplace
    for line in lines[1:]:
        s = line.rstrip("\r")
        if s == "---":
            return True  # column-0 closing fence reached before any heading
        if s.startswith("## "):
            return False  # body heading inside the fence — corruption
    return False  # opening fence never closes


def repair_misplaced_fence(path: Path) -> bool:
    """Deterministically move a misplaced closing fence above the body.

    For a note broken per :func:`frontmatter_closed_before_body` — where
    ``## Evidence Trail`` / ``## Source`` blocks landed inside the YAML
    fence — insert the closing ``---`` immediately after the last YAML
    line and drop the original misplaced fence, so the body sections move
    out of the frontmatter intact.

    The return value is honest: True means the note is now (or already was)
    well-formed AND parses. Returns False, writing nothing, when the note is
    not the misplaced-fence defect (a well-formed fence but some other YAML
    error), or the shape is ambiguous — no YAML keys before the heading, or
    more than one column-0 ``---`` in the displaced region (an owner
    horizontal rule makes the intended fence indistinguishable). Ambiguous
    notes are left for a CLARIFICATION rather than risk silent content
    mutation. Idempotent: re-running on a repaired note is a no-op True.
    """
    if frontmatter_closed_before_body(path):
        # No misplaced fence. True only if the note actually parses — a
        # clean fence with unrelated broken YAML is not this helper's to fix.
        return read_frontmatter(path) is not None
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        return False
    if not lines or lines[0].rstrip("\r").strip() != "---":
        return False
    first_heading_idx = next(
        (i for i in range(1, len(lines)) if lines[i].startswith("## ")), None
    )
    if first_heading_idx is None:
        return False
    insertion_after = first_heading_idx - 1
    while insertion_after >= 1 and lines[insertion_after].rstrip("\r").strip() == "":
        insertion_after -= 1
    if insertion_after < 1:
        return False  # no YAML keys before the heading — unexpected shape
    head, tail = lines[: insertion_after + 1], lines[insertion_after + 1 :]
    fence_positions = [j for j, line in enumerate(tail) if line.rstrip("\r") == "---"]
    if len(fence_positions) != 1:
        return False  # 0 = no fence to relocate; >1 = ambiguous — refuse
    del tail[fence_positions[0]]
    new_text = "\n".join(head + ["---"] + tail)
    m = _FRONTMATTER_RE.match(new_text)
    if not m:
        return False
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return False
    if not isinstance(fm, dict):
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def parse_file(path: Path) -> Principle:
    """Read markdown file, split frontmatter / body, validate schema.

    Raises SchemaError / ParseError with a `{path}: {reason}` message.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ParseError(f"{path}: cannot read file ({exc})") from exc

    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ParseError(f"{path}: no YAML frontmatter found")

    yaml_text, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ParseError(f"{path}: YAML parse error — {exc}") from exc
    if not isinstance(fm, dict):
        raise SchemaError(f"{path}: frontmatter must be a mapping, got {type(fm).__name__}")

    validate_frontmatter(path, fm)
    return Principle(path=path, frontmatter=fm, body=body)


def validate_frontmatter(path: Path, fm: dict) -> None:
    """Raise SchemaError on any violation. Called by parse_file."""
    missing = [f for f in REQUIRED_FIELDS if f not in fm]
    if missing:
        raise SchemaError(f"{path}: missing required fields: {missing}")

    def check_enum(field_name: str, value, allowed: Iterable) -> None:
        if value not in allowed:
            raise SchemaError(
                f"{path}: field '{field_name}' has invalid value {value!r}; "
                f"allowed: {sorted(allowed)}"
            )

    check_enum("type", fm["type"], ALLOWED_TYPES)
    # Normalise domain before enum check so `ai_interaction` (snake) and
    # `AI-Interaction` (mixed case) are accepted as their canonical
    # `ai-interaction`. The normalised value is written back to the
    # frontmatter dict so downstream consumers (Principle.domain, id-prefix
    # check below, manifest emit) see the canonical form. None on
    # irrecoverable shape falls through to check_enum which raises with the
    # raw value — keeps error messages truthful about what owner wrote.
    norm_domain = normalize_domain(fm["domain"])
    if norm_domain is not None and norm_domain in ALLOWED_DOMAINS:
        fm["domain"] = norm_domain
    check_enum("domain", fm["domain"], ALLOWED_DOMAINS)
    check_enum("priority_tier", fm["priority_tier"], ALLOWED_PRIORITY_TIERS)
    check_enum("scope", fm["scope"], ALLOWED_SCOPES)
    check_enum("status", fm["status"], ALLOWED_STATUSES)

    if "framing" in fm:
        check_enum("framing", fm["framing"], ALLOWED_FRAMINGS)
    if "binding" in fm:
        check_enum("binding", fm["binding"], ALLOWED_BINDINGS)
    if "confidence" in fm:
        check_enum("confidence", fm["confidence"], ALLOWED_CONFIDENCES)

    applies_to = fm.get("applies_to", [])
    if not isinstance(applies_to, list):
        raise SchemaError(f"{path}: applies_to must be a list, got {type(applies_to).__name__}")
    for item in applies_to:
        if item not in ALLOWED_APPLIES_TO:
            # Consumer-side rule: unknown values are ignored but not a fatal
            # schema error — new enum values may land in CONSTITUTION.md before
            # scripts are updated. Log to stderr.
            print(
                f"warning: {path}: unknown applies_to value {item!r} — ignored",
                file=sys.stderr,
            )

    if "core" in fm and not isinstance(fm["core"], bool):
        raise SchemaError(f"{path}: field 'core' must be boolean")

    # ID shape: {type}-{domain}-{NNN}
    expected_prefix = f"{fm['type']}-{fm['domain']}-"
    if not str(fm["id"]).startswith(expected_prefix):
        raise SchemaError(
            f"{path}: id {fm['id']!r} does not match expected prefix "
            f"{expected_prefix!r} (type-domain-NNN)"
        )


def iter_principles(root: Path) -> list[Principle]:
    """Walk `root` (expected: 0_constitution/), return all parsed principles.

    Skips CONSTITUTION.md (the protocol doc itself) and any README-like files
    at the top level. Sub-folders {axiom,principle,rule}/* are scanned. Also
    validates that all ids are unique — duplicates raise SchemaError.
    Symbolic-link files are skipped (security defence for export paths).
    """
    if not root.exists():
        return []
    results: list[Principle] = []
    for type_name in sorted(ALLOWED_TYPES):
        type_dir = root / type_name
        if not type_dir.is_dir():
            continue
        for md_file in sorted(type_dir.rglob("*.md")):
            if md_file.is_symlink():
                # Symlinks are never followed — they could point outside the
                # repo (e.g. into $HOME) and leak content via export.
                print(
                    f"warning: {md_file}: symbolic link skipped",
                    file=sys.stderr,
                )
                continue
            results.append(parse_file(md_file))
    # Sort by id for deterministic output across platforms.
    results.sort(key=lambda p: p.id)
    _check_unique_ids(results)
    return results


def _check_unique_ids(principles: list[Principle]) -> None:
    seen: dict[str, Path] = {}
    for p in principles:
        prior = seen.get(p.id)
        if prior is not None:
            raise SchemaError(
                f"duplicate id {p.id!r}: "
                f"first seen in {prior}, also in {p.path}"
            )
        seen[p.id] = p.path


def constitution_principle_ids(base: Path | None = None) -> set[str]:
    """The set of every principle-id that resolves to a real file under
    `0_constitution/` — the deterministic existence check for a cited principle-id.

    Tolerant sibling of `iter_principles`: where that raises `SchemaError` /
    `ParseError` on a malformed or duplicate-id file (it is the schema-strict loader),
    this NEVER raises. It walks the same `{axiom,principle,rule}/**` tree, skips symlinks
    (never followed — they could point outside the repo), reads each file's frontmatter
    tolerantly (`read_frontmatter` returns None on any parse failure), and collects the
    `id:` field. A file that cannot be parsed contributes no id — so a caller checking
    membership fails CLOSED on it (an id pointing at a broken file is treated as
    non-existent), never crashing the caller.

    The existence half of a values-grounding oracle: a caller filters cited principle-ids
    against this set, so a fabricated id can never survive to ground a claim —
    deterministic, independent of the prompt stage that authored the citation. Pure
    filesystem: no LLM, no check-decision.
    """
    root = constitution_root(base)
    ids: set[str] = set()
    for type_name in ALLOWED_TYPES:
        type_dir = root / type_name
        if not type_dir.is_dir():
            continue
        for md_file in type_dir.rglob("*.md"):
            if md_file.is_symlink():
                continue
            parsed = read_frontmatter(md_file)
            if parsed is None:
                continue
            pid = parsed[0].get("id")
            if isinstance(pid, str) and pid.strip():
                ids.add(pid.strip())
    return ids


# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------

_HIDDEN_STATUSES_DEFAULT: frozenset[str] = frozenset({"archived", "placeholder"})


def is_visible(
    p: Principle,
    *,
    consumer: str | None = None,
    allow_statuses: frozenset[str] | set[str] | None = None,
) -> bool:
    """True if principle is visible to a consumer.

    `allow_statuses`: set of status values that override the default
    exclusion list (`archived`, `placeholder`). Use for test fixtures or
    for lint health views that need to see the full tree.

    Scope-based context narrowing is not currently applied — every scope
    is visible to every consumer. The `scope` field exists as a data
    marker for future multi-user scenarios.
    """
    hidden = _HIDDEN_STATUSES_DEFAULT - (frozenset(allow_statuses) if allow_statuses else frozenset())
    if p.status in hidden:
        return False
    if consumer and p.applies_to:
        if consumer not in p.applies_to:
            return False
    return True


# -----------------------------------------------------------------------------
# Body helpers (for Evidence Trail & SOUL markers)
# -----------------------------------------------------------------------------

EVIDENCE_TRAIL_HEADING = "## Evidence Trail"


def find_evidence_trail_bounds(body: str) -> tuple[int, int] | None:
    """Return (start, end) char offsets in body for the Evidence Trail section.

    `start` points to the first char of the first entry (line after heading).
    `end` points to the first char of the next `## ` heading, or len(body).
    Returns None if section not found.
    """
    pattern = re.compile(r"^## Evidence Trail\s*$", re.MULTILINE)
    m = pattern.search(body)
    if not m:
        return None
    start = m.end()
    # Skip leading newlines after heading
    while start < len(body) and body[start] in "\r\n":
        start += 1
    next_h = re.search(r"^## ", body[start:], re.MULTILINE)
    end = start + next_h.start() if next_h else len(body)
    return start, end


SOUL_MARKER_START = "<!-- AUTO-GENERATED FROM CONSTITUTION — DO NOT EDIT MANUALLY -->"
SOUL_MARKER_END = "<!-- END AUTO-GENERATED -->"


def find_soul_auto_zone(text: str) -> tuple[int, int] | None:
    """Return (content_start, content_end) between SOUL auto-markers.

    content_start = position right after the start marker line (including
    trailing newline). content_end = position right before the end marker line.
    Returns None if either marker is missing.
    """
    i_start = text.find(SOUL_MARKER_START)
    if i_start < 0:
        return None
    # Advance past the marker line including its newline
    line_end = text.find("\n", i_start)
    if line_end < 0:
        return None
    content_start = line_end + 1

    i_end = text.find(SOUL_MARKER_END, content_start)
    if i_end < 0:
        return None
    # content_end: include preceding newline so replacement is clean
    content_end = i_end
    return content_start, content_end


# -----------------------------------------------------------------------------
# Reprocess-corpus selection (deterministic substrate for /minder:mem:process §2.1)
# -----------------------------------------------------------------------------

# Roots walked by `/minder:mem:process --reprocess-corpus`. Keep aligned with the
# SKILL spec's `## Mode: --reprocess-corpus`: records cover transcript-grounded
# logs, knowledge covers PARA layers (4_archive intentionally excluded — history
# is not rewritten).
REPROCESS_CORPUS_ROOTS: dict[str, tuple[str, ...]] = {
    "records": ("_records/meetings", "_records/observations"),
    "knowledge": ("1_projects", "2_areas", "3_resources"),
}

REPROCESS_CORPUS_LAYERS: frozenset[str] = frozenset({"record", "knowledge"})


# -----------------------------------------------------------------------------
# Action Hints — lens emission contract (consumed by /minder:mem:resolve-clarifications)
# -----------------------------------------------------------------------------
#
# Lenses MAY append an `## Action Hints` trailer to their output file,
# proposing structural changes (wikilink_add, hub_stub_create, ...). The
# resolver ingests these hints, judges with full owner context, and either
# auto-applies (when precedent + constitution + safety align) or queues
# for owner review. See `integrations/claude-code/skills/
# minder-mem-resolve-clarifications/SKILL.md` for the consumer side.
#
# Whitelist enforcement happens at resolver Step 2, not at lens emission.
# Lenses propose freely; non-whitelisted types are routed to clarifications
# with «type X is not currently auto-applicable; owner review required».

ACTION_HINT_TYPES: frozenset[str] = frozenset({
    "wikilink_add",
    "hub_stub_create",
    "open_thread_add",
    "decision_update_section",
    "threshold_tune_proposal",
    "metric_record_rerender_apply",
    "principle_candidate_add",
})

ACTION_HINT_CONFIDENCES: frozenset[str] = frozenset({"low", "medium", "high"})

# Per-type required `params` fields. Resolver's stale pre-check + handlers
# rely on these. Missing fields → hint is dropped at parse with a reason.
ACTION_HINT_REQUIRED_PARAMS: dict[str, frozenset[str]] = {
    "wikilink_add": frozenset({"note_a", "note_b"}),
    "hub_stub_create": frozenset({"suggested_slug", "cited_notes"}),
    "open_thread_add": frozenset({"thread_title", "cited_records"}),
    "decision_update_section": frozenset({"decision_note_path", "update_reason"}),
    "threshold_tune_proposal": frozenset({"metric", "severity", "proposed_sigma"}),
    "metric_record_rerender_apply": frozenset({"date", "choice"}),
    "principle_candidate_add": frozenset(
        {"situation", "observation", "hypothesis", "suggested_type",
         "suggested_domain", "source_record_count"}
    ),
}


_ACTION_HINTS_HEADER_RE = re.compile(
    r"^##\s+Action\s+Hints\s*$", re.MULTILINE | re.IGNORECASE
)


def extract_action_hints_block(body: str) -> str | None:
    """Return the YAML body inside an `## Action Hints` section, or None.

    The block runs from the line after the header to either the next
    `## ` heading at column 0 or EOF. Returns the YAML text trimmed of
    leading/trailing blank lines. None when no `## Action Hints` header
    is present.
    """
    if not body:
        return None
    m = _ACTION_HINTS_HEADER_RE.search(body)
    if m is None:
        return None
    start = m.end()
    rest = body[start:]
    # Find next top-level `## ` heading (NOT `### ` or deeper).
    next_heading = re.search(r"\n##\s+(?!#)", rest)
    block = rest[: next_heading.start()] if next_heading else rest
    return block.strip("\n")


@dataclass(frozen=True)
class ActionHint:
    """One parsed Action Hint emitted by a lens.

    `raw_index` is the 0-based position inside the lens file's `## Action
    Hints` list — used for traceability when a hint is dropped or queued.
    """
    type: str
    params: dict
    confidence: str
    brief_reasoning: str
    raw_index: int


def parse_action_hints(body: str) -> tuple[list[ActionHint], list[dict]]:
    """Parse `## Action Hints` trailer into structured hints.

    Returns `(hints, drops)`:
      - `hints`: well-formed `ActionHint` instances (type whitelisted,
        confidence valid, required params present)
      - `drops`: list of `{raw_index, reason, raw}` for malformed entries

    Deterministic — no LLM. PyYAML strict load. Tolerant of missing
    section (returns `([], [])`). Caller logs drops.
    """
    block = extract_action_hints_block(body)
    if block is None or not block.strip():
        return ([], [])

    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        return ([], [{"raw_index": -1, "reason": f"yaml-parse-error: {exc}", "raw": block}])

    if not isinstance(parsed, list):
        return ([], [{"raw_index": -1, "reason": "expected-yaml-list", "raw": block}])

    hints: list[ActionHint] = []
    drops: list[dict] = []
    for idx, raw in enumerate(parsed):
        if not isinstance(raw, dict):
            drops.append({"raw_index": idx, "reason": "entry-not-mapping", "raw": raw})
            continue
        hint_type = raw.get("type")
        params = raw.get("params")
        confidence = raw.get("confidence")
        brief = raw.get("brief_reasoning")
        if not isinstance(hint_type, str) or not hint_type:
            drops.append({"raw_index": idx, "reason": "missing-type", "raw": raw})
            continue
        if hint_type not in ACTION_HINT_TYPES:
            drops.append({"raw_index": idx, "reason": f"type-not-whitelisted:{hint_type}", "raw": raw})
            continue
        if not isinstance(params, dict):
            drops.append({"raw_index": idx, "reason": "missing-params-mapping", "raw": raw})
            continue
        required = ACTION_HINT_REQUIRED_PARAMS[hint_type]
        missing = [k for k in required if k not in params]
        if missing:
            drops.append({"raw_index": idx, "reason": f"missing-params:{','.join(missing)}", "raw": raw})
            continue
        if confidence not in ACTION_HINT_CONFIDENCES:
            drops.append({"raw_index": idx, "reason": f"bad-confidence:{confidence}", "raw": raw})
            continue
        if not isinstance(brief, str) or not brief.strip():
            drops.append({"raw_index": idx, "reason": "missing-brief-reasoning", "raw": raw})
            continue
        hints.append(ActionHint(
            type=hint_type,
            params=params,
            confidence=confidence,
            brief_reasoning=brief.strip(),
            raw_index=idx,
        ))
    return (hints, drops)

_FILENAME_DATE_PREFIX_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-")


def _reprocess_created_key(fm: dict, filename: str) -> str:
    """Sort key for reprocess-corpus selection.

    Prefer YAML `created:` (string or date object); fall back to filename
    `YYYYMMDD-` prefix; last resort `9999-99-99` so files without any
    extractable date sort to the end without crashing.
    """
    raw = fm.get("created")
    if isinstance(raw, (date, datetime)):
        return raw.isoformat()[:10]
    if isinstance(raw, str) and raw:
        return raw[:10]
    m = _FILENAME_DATE_PREFIX_RE.match(filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return "9999-99-99"


def select_reprocess_corpus_files(
    base: Path | str,
    scope: str = "all",
    limit: int | None = None,
) -> list[Path]:
    """Return chronologically-sorted corpus files for `--reprocess-corpus`.

    Walks the roots determined by `scope`, keeps files whose YAML
    frontmatter declares `layer:` ∈ {`record`, `knowledge`}, sorts by
    `created:` (filename `YYYYMMDD-` prefix as fallback), then truncates
    to the first `limit` entries when `limit` is non-negative.

    scope:
        ``records``   — `_records/meetings/`, `_records/observations/`
        ``knowledge`` — `1_projects/`, `2_areas/`, `3_resources/`
        ``all``       — both (default)

    limit:
        ``None`` or negative → no truncation (full list)
        ``0``                → empty list (explicit no-op)
        ``N >= len(files)``  → full list

    `base` is the zettelkasten root (typically `repo_root()`).

    Implementation notes: deterministic, no LLM. Matches §2.1 reprocess-
    corpus branch of `/minder:mem:process` SKILL spec. Exposed so that the
    orchestrator can shell out for a single source-of-truth file list
    instead of reimplementing the walk per invocation.
    """
    if scope not in REPROCESS_CORPUS_ROOTS and scope != "all":
        raise ValueError(
            f"unknown scope {scope!r}; expected 'records', 'knowledge', or 'all'"
        )
    base = Path(base)
    if scope == "all":
        roots = REPROCESS_CORPUS_ROOTS["records"] + REPROCESS_CORPUS_ROOTS["knowledge"]
    else:
        roots = REPROCESS_CORPUS_ROOTS[scope]

    entries: list[tuple[str, str, Path]] = []
    for rel in roots:
        root = base / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            parsed = read_frontmatter(path)
            if parsed is None:
                continue
            fm, _body = parsed
            if fm.get("layer") not in REPROCESS_CORPUS_LAYERS:
                continue
            entries.append((_reprocess_created_key(fm, path.name), path.name, path))

    entries.sort(key=lambda e: (e[0], e[1]))
    files = [e[2] for e in entries]

    if limit is not None and limit >= 0:
        files = files[:limit]
    return files


# -----------------------------------------------------------------------------
# Misc
# -----------------------------------------------------------------------------

def today_iso() -> str:
    return date.today().isoformat()


def now_iso_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)
