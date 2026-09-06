#!/usr/bin/env python3
"""Identity audit — one identifier, eight surfaces, one verdict.

The registry decides what an identifier means. The identifier itself lives in
eight places. Auditing one of them lets a retirement reach the registry and stop
there, which is how a decision recorded once survives only as long as the author
remembered to carry it. This scanner resolves every surface against the registry
and reports what still names a retired or mis-classified identifier.

**Matching is exact identifier equality, never substring.** A hub whose own
identifier merely CONTAINS a retired one is a different identity that happens to
share a prefix — it is not a surface of that identity and is never reported as
one.

Surfaces, per the identity contract — roles, not paths:

  field              the membership array entry (`projects:`, `people:`)
  tag                `{namespace}/{id}` in `tags:`
  wikilink           `[[id]]`, `[[id|label]]`, `[[id#section]]`, `[[path/id]]`
  node-card          the identity's own `.md` file in its registry's node dir
  node-container     the identity's own folder in its registry's node dir
  hub                the hub whose own `id:` is this identity's hub identifier
  registry-row       the row in the registry that declares the identity
  tag-registry-row   the row declaring `{namespace}/{id}` in the tag registry

**Which roles exist is a property of the registry, not of this code.** Each
registry declares its surfaces, its node directory, its membership field and
its tag namespaces in a `RegistrySpec`; the scan below is written once against
those declarations. A registry that does not declare a role does not have it —
the people registry has no node container and no hub, and says so as data. A
third registry is a third `RegistrySpec`, not a third branch. That is the
contract's own sanity test: a new kind of identity that needs a special rule
inside the procedure, rather than a row in its registry's declaration, means
the procedure is written wrong.

**Coverage is inverted, not enumerated.** The scan walks the whole base and
classifies every markdown path by rule; a path no rule claims is itself a
finding (`surface_class: "unclassified"`), counted as residue. An allowlist of
scanned roots fails GREEN — it proves only that the paths someone remembered
are clean, and this engine grows by adding top-level regions. Inverting it
makes the contract's own doctrine — silence needs a detector — something the
code does rather than something the document claims.

Two identities are never reported, and both exclusions are principled rather
than convenient:

  the owner    named by `SOUL.md → ## Identity → Name:` (or by the registry's
               own owner section once it has one). The owner's identifier is
               on hundreds of live surfaces and in no registry table; a check
               that reads "absent from the registry, therefore drift" would
               call the owner of the base garbage.
  void kinds   a retirement of the `void` kind never had a successor, so its
               references are frozen where they stand rather than migrated,
               and are excluded from the residue check by the contract itself.

A node surface reported for relocation pulls its inbound links in with it: every
wikilink resolving to that node is live work too (`action: repoint`, target = the
canonical node by the resolution order hub → card → container README). Reporting
the node alone would let the gate pass a graph that breaks the moment the node
moves. For a RETIRED identifier those links are already residue and stay
`migrate` — a repoint means the identity lives on and only its node moved.

Surface classes decide what a finding MEANS, and exist so that "no residue" can
never be satisfied by rewriting history:

  live          migrates — notes, cards, containers, hubs
  derived       regenerates — views and aggregates; migrating them is a category
                error, the next rebuild overwrites the edit
  immutable     never touched and never reported — raw sources, append-only
                state, lens output, manifests with their own checksums, and the
                BODY of any record
  unclassified  no rule claims this path, so nothing has decided what it is.
                Reported as residue, because a scan that silently skips what it
                does not recognise is a scan whose green verdict means nothing.

The record split is inside the file, not at the folder: a record's frontmatter
is engine-managed classification and migrates like any other live surface,
while its body is a historical artifact. A record whose frontmatter names a
retired identity is residue; a record whose prose mentions it is history, and
demanding that history be rewritten is the one thing the contract forbids.

Two modes, because one caller wants an event stream and the other wants a gate:

  default            the drift event stream (JSONL on stdout), exit 0 — the
                     nightly scan's contract, plus the hub-kind check, which
                     belongs to the scan that already holds the registry
  --report [--json]  the identity report: findings grouped per identifier
  --fail-on-residue  exit non-zero when residue exists, so a gate can be built
                     on it at all
  --identity {id}    restrict the report, the counts and the exit code to one
                     identifier. The completion gate is per-identity while the
                     audit is global, so a caller reading a whole-base verdict
                     as its own reverts a correct migration because something
                     unrelated is dirty. Other identities' findings are dropped
                     from the output entirely, not merely uncounted

A filtered run reports which of three things happened, because all three exit
0 and only the first is what a reader assumes (`identity_scope` in `--json`):

  audited       the identity was scanned; the residue count is real and the
                verdict prints as `clean: True/False`
  set-aside     auditable in principle, but every registry that holds it set
                it aside (a `void` retirement, the owner row)
  out-of-scope  declared and live, so no registry audits it — a live
                identifier on its own axis is where it belongs

The last two print `NOT AUDITED ({scope})` with the reason, never `clean`:
zero buckets and a clean scan are different facts and must not share a word.

Exit status:
  0  ran; no residue, or residue found without --fail-on-residue, or nothing
     applies to the filtered identity (see the three scopes above — read the
     scope, not the exit code, to tell «no residue» from «no check»)
  1  could not run — the root does not exist, or `--identity` names an
     identifier no registry declares. Never 0: the ordinary causes are a typo
     and a retirement row that never landed, and reading "unknown" as "clean"
     closes a change against nothing
  2  residue present, with --fail-on-residue

Usage:
    python3 identity_audit.py [--root <path>]
    python3 identity_audit.py --report --json [--root <path>]
    python3 identity_audit.py --report --fail-on-residue
    python3 identity_audit.py --identity old-project --fail-on-residue
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from dataclasses import dataclass
from typing import Callable

from _common import (
    IDENTITY_KIND_UNKNOWN,
    REGISTRY_CATEGORIES,
    REGISTRY_SECTION_UNKNOWN,
    RegistryEntry,
    SUCCESSOR_ARITY,
    configure_std_streams,
    owner_identity,
    parse_people_registry,
    parse_project_registry,
    people_registry_section_category,
    read_frontmatter,
    registry_ids_by_category,
    registry_rows,
    registry_section_category,
    repo_root,
)


# Folders whose `projects:` arrays are the SUBJECT of the drift event stream —
# unchanged from the projects-array scan this widened. Hubs are absent on
# purpose: a hub may legitimately carry `projects:` as its own primary, so it is
# read as a TARGET for the kind check, never as a subject.
SCOPE_INCLUDE: tuple[str, ...] = (
    "_records/",
    "1_projects/",
    "2_areas/",
    "3_resources/",
    "4_archive/",
)

SURFACE_FIELD = "field"
SURFACE_TAG = "tag"
SURFACE_WIKILINK = "wikilink"
SURFACE_NODE_CARD = "node-card"
SURFACE_NODE_CONTAINER = "node-container"
SURFACE_HUB = "hub"
SURFACE_REGISTRY_ROW = "registry-row"
SURFACE_TAG_REGISTRY_ROW = "tag-registry-row"

SURFACES: tuple[str, ...] = (
    SURFACE_FIELD,
    SURFACE_TAG,
    SURFACE_WIKILINK,
    SURFACE_NODE_CARD,
    SURFACE_NODE_CONTAINER,
    SURFACE_HUB,
    SURFACE_REGISTRY_ROW,
    SURFACE_TAG_REGISTRY_ROW,
)

CLASS_LIVE = "live"
CLASS_DERIVED = "derived"
CLASS_IMMUTABLE = "immutable"
CLASS_UNCLASSIFIED = "unclassified"

TAG_REGISTRY = "_system/registries/TAGS.md"


# -----------------------------------------------------------------------------
# Coverage — the classification is a partition, and its gaps are findings
# -----------------------------------------------------------------------------
#
# Three allowlists of scanned roots do not partition a base: a region no list
# names is scanned by nothing, and the verdict for it is `clean: true`. That is
# the worst possible failure mode, because an allowlist fails GREEN — it proves
# only that the paths someone remembered are clean, and says so in the same
# words it would use if they were all clean. This engine grows precisely by
# adding top-level regions, so the gap is not hypothetical; it is scheduled.
#
# So the walk goes the other way. Every markdown path in the base is put
# through the rules below in order, first match wins, and a path no rule claims
# is reported. Adding a region without deciding what it is now fails loudly
# instead of passing quietly.

@dataclass(frozen=True)
class SurfaceRule:
    """One classification rule: which paths, which class, and why.

    `why` is not decoration. Whoever adds the next top-level region will decide
    its class by reading the neighbouring reasons, so the reasons are the part
    of this table that has to keep working.
    """

    match: Callable[[str], bool]
    surface_class: str
    why: str
    # A file whose BODY is history and whose frontmatter is engine-managed
    # classification. The class above governs the frontmatter; the body is
    # immutable regardless of it.
    body_immutable: bool = False


def _under(*prefixes: str) -> Callable[[str], bool]:
    return lambda rel: any(rel.startswith(p) for p in prefixes)


def _exact(*names: str) -> Callable[[str], bool]:
    return lambda rel: rel in names


def _depth_one(prefix: str) -> Callable[[str], bool]:
    """A file directly inside `prefix`, not in any sub-directory of it."""
    return lambda rel: rel.startswith(prefix) and "/" not in rel[len(prefix):]


def _root_level(rel: str) -> bool:
    return "/" not in rel


def _role_state(rel: str) -> bool:
    return rel.startswith("_system/roles/") and "/state/" in rel


CLASSIFICATION: tuple[SurfaceRule, ...] = (
    # --- immutable: rewriting any of these falsifies a record of what happened
    SurfaceRule(
        _under("_sources/"), CLASS_IMMUTABLE,
        "raw material exactly as it arrived; editing it forges the input",
    ),
    SurfaceRule(
        _under("_system/state/"), CLASS_IMMUTABLE,
        "append-only engine state — logs, buffers, queues, and manifests that "
        "carry their own checksums",
    ),
    SurfaceRule(
        _under("_system/agent-lens/"), CLASS_IMMUTABLE,
        "a lens output is a dated observation — what the lens saw on that day, "
        "not a surface that can be brought up to date",
    ),
    SurfaceRule(
        _under("_system/roles/_previous/"), CLASS_IMMUTABLE,
        "a superseded generation of the roles layer, kept as history",
    ),
    SurfaceRule(
        _role_state, CLASS_IMMUTABLE,
        "a role's own memory between runs — written and rewritten by the role "
        "itself, so an outside edit is overwritten on the next tick",
    ),
    # --- derived: an edit here is undone by the next regeneration
    SurfaceRule(
        _under("_system/views/"), CLASS_DERIVED,
        "rendered views, rebuilt wholesale from the layers they summarise",
    ),
    SurfaceRule(
        _exact("_system/TASKS.md", "_system/CALENDAR.md"), CLASS_DERIVED,
        "aggregates over note-level `- [ ]` and `📅` items, reconciled by "
        "script rather than edited",
    ),
    SurfaceRule(
        _exact(
            TAG_REGISTRY, "_system/registries/TAGS.template.md",
            "_system/registries/CONCEPTS.md",
        ), CLASS_DERIVED,
        "regenerated from the corpus between AUTO-GENERATED markers — a row "
        "naming a retired identifier disappears when the corpus that produced "
        "it is migrated, so migrating the row by hand is a category error",
    ),
    # --- live, with an immutable body
    SurfaceRule(
        _under("_records/"), CLASS_LIVE,
        "a record's frontmatter is engine-managed classification and migrates; "
        "its prose is what was said, and is never rewritten",
        body_immutable=True,
    ),
    # --- live: the knowledge layers, the values layer, the hubs
    SurfaceRule(
        _under(
            "0_constitution/", "1_projects/", "2_areas/", "3_resources/",
            "4_archive/", "5_meta/", "6_posts/",
        ), CLASS_LIVE,
        "owner knowledge, curated and edited in place. `0_constitution/` is "
        "here because a principle carries an Evidence Trail of wikilinks into "
        "the base — a link like any other, and residue like any other when the "
        "identity it names is retired. `4_archive/` is here because archival "
        "leaves an identifier valid, so an archived note is a stale surface "
        "rather than a historical one. `6_posts/` is here because a post is a "
        "draft the owner reworks, not a published artifact the base may not "
        "touch",
    ),
    # --- live: the engine's own prose, where an owner identity is a leak
    SurfaceRule(
        _under(
            "5_skills/", "_system/docs/", "_system/scripts/",
            "_system/registries/", "_system/roles/",
        ), CLASS_LIVE,
        "engine documentation, registries and role definitions. A registry row "
        "and a role's brief name identities and must migrate. The engine cards "
        "and system docs should name no owner identity at all — one appearing "
        "here is a personal-data leak, which is exactly a finding worth having",
    ),
    SurfaceRule(
        _depth_one("_system/"), CLASS_LIVE,
        "the owner's operational files at the root of `_system/` — SOUL, "
        "POSTS, the playbooks and their templates: hand-curated, so they "
        "migrate rather than regenerate",
    ),
    SurfaceRule(
        _root_level, CLASS_LIVE,
        "the vault's own front page at the base root — a hand-maintained note "
        "full of links into the layers below, and a live surface like any "
        "other note",
    ),
)


def classify(rel: str) -> SurfaceRule | None:
    """The rule claiming this path, or None when no rule does."""
    for rule in CLASSIFICATION:
        if rule.match(rel):
            return rule
    return None


def _region(rel: str) -> str:
    """The top-level region a path belongs to — what an owner would have to
    make a decision about, rather than the individual file."""
    head, sep, _ = rel.partition("/")
    return head + "/" if sep else head


@dataclass(frozen=True)
class ClassifiedFile:
    path: Path
    rel: str
    rule: SurfaceRule


def walk_base(root: Path) -> tuple[list[ClassifiedFile], list[dict]]:
    """Every markdown file in the base, classified — plus the ones no rule
    claims, as findings.

    Dot-directories are skipped by rule rather than by omission: `.git`,
    `.obsidian` and `.pytest_cache` are tool state that no part of the base
    layer owns, and none of them is a surface of an identity.
    """
    classified: list[ClassifiedFile] = []
    unclassified: list[dict] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if any(part.startswith(".") for part in rel.split("/")):
            continue
        rule = classify(rel)
        if rule is None:
            unclassified.append({
                "identity": None,
                "registry": None,
                "surface": None,
                "surface_class": CLASS_UNCLASSIFIED,
                "kind": CODE_UNCLASSIFIED,
                "severity": "strong",
                "autofixable": False,
                "path": rel,
                "region": _region(rel),
                "line": None,
                "action": "classify",
                "reason": (
                    f"no classification rule claims `{rel}`. Nothing has "
                    f"decided whether the `{_region(rel)}` region is a live "
                    f"surface, a derived one or history, so nothing scans it "
                    f"and a retired identifier sitting there reads as clean. "
                    f"Add a rule to CLASSIFICATION in identity_audit.py."
                ),
            })
            continue
        classified.append(ClassifiedFile(path, rel, rule))
    return classified, unclassified


HUB_PREFIX = "hub-"
HUB_DIR = ("5_meta", "mocs")
PROJECT_DIR = "1_projects"
PEOPLE_DIR = "3_resources/people"

# The namespace a tag is expected to carry, per registry category. A retired
# identifier has no correct namespace at all — every namespaced tag naming it is
# residue.
EXPECTED_NAMESPACE: dict[str, str | None] = {
    "project": "project",
    "trajectory": "trajectory",
    "consolidated": None,
}

PEOPLE_EXPECTED_NAMESPACE: dict[str, str | None] = {
    "person": "person",
    "consolidated": None,
}

RETIRED_CATEGORY = "consolidated"


# -----------------------------------------------------------------------------
# Registries — the surface set is data
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class RegistrySpec:
    """One registry, and the roles it declares.

    Everything the scan needs to know about a registry lives here, so the scan
    itself knows about roles and never about a particular registry. `surfaces`
    is the whole statement of which roles exist: a role absent from it is not
    looked for, is not reported, and does not exist for this registry.
    """

    name: str
    registry_path: str
    parse: Callable[[Path], dict[str, RegistryEntry]]
    surfaces: tuple[str, ...]
    # `field` role: the frontmatter key whose array names this identity.
    membership_field: str | None
    # `node-card` / `node-container` roles: the directory that holds them.
    node_dir: str | None
    # `tag` role: the namespace each category belongs in; None = no correct
    # namespace exists (a retired identifier).
    expected_namespace: dict[str, str | None]
    # Categories that can leave residue at all. A live identity sitting on its
    # own axis is by definition where it belongs.
    audited_categories: tuple[str, ...]
    # Live categories whose node is in the wrong home for what they are.
    relocate_categories: tuple[str, ...] = ()
    # `registry-row` role: how this registry's own `#`-headers map to
    # categories, so the audit can see a row the parser dropped and a row that
    # declares an identifier a second time. A registry that supplies neither
    # does not have the role, whatever `surfaces` claims.
    section_category: Callable[[str], str | None] | None = None
    default_section_category: str | None = None
    # `tag-registry-row` role: the file declaring namespaced tags.
    tag_registry: str | None = None
    # Whether the owner's identifier is set aside for this registry. It is the
    # PEOPLE registry's owner row that is valid-by-construction — not the slug
    # itself, everywhere. Applied to every registry, this exclusion silently
    # un-audits a project whose identifier happens to collide with a slug
    # transliterated out of prose in SOUL.md.
    excludes_owner: bool = False


PROJECT_SPEC = RegistrySpec(
    name="project",
    registry_path=f"{PROJECT_DIR}/PROJECTS.md",
    parse=parse_project_registry,
    surfaces=(
        SURFACE_FIELD, SURFACE_TAG, SURFACE_WIKILINK,
        SURFACE_NODE_CARD, SURFACE_NODE_CONTAINER, SURFACE_HUB,
        SURFACE_REGISTRY_ROW, SURFACE_TAG_REGISTRY_ROW,
    ),
    membership_field="projects",
    node_dir=PROJECT_DIR,
    expected_namespace=EXPECTED_NAMESPACE,
    audited_categories=(RETIRED_CATEGORY, "trajectory"),
    relocate_categories=("trajectory",),
    section_category=registry_section_category,
    # Rows above the first header are projects — the registry opens with its
    # active table, exactly as the parser reads it.
    default_section_category="project",
    tag_registry=TAG_REGISTRY,
)

# The people registry declares six roles and, by omission, states that it has
# no node container and no hub: a person is one card, never a folder, and a
# `hub-{person}` would be a hub about a person rather than the person's node.
PEOPLE_SPEC = RegistrySpec(
    name="people",
    registry_path=f"{PEOPLE_DIR}/PEOPLE.md",
    parse=parse_people_registry,
    surfaces=(
        SURFACE_FIELD, SURFACE_TAG, SURFACE_WIKILINK, SURFACE_NODE_CARD,
        SURFACE_REGISTRY_ROW, SURFACE_TAG_REGISTRY_ROW,
    ),
    membership_field="people",
    node_dir=PEOPLE_DIR,
    expected_namespace=PEOPLE_EXPECTED_NAMESPACE,
    audited_categories=(RETIRED_CATEGORY,),
    relocate_categories=(),
    section_category=people_registry_section_category,
    # No default: this registry's tail is full of reference tables — orgs,
    # roles, the profile template — whose first cells are perfectly good slugs,
    # and a row outside a recognised section is not a person.
    #
    # Which is also why this registry reports no unknown-section defect where
    # the project registry does. The two failure modes are not the same: an
    # unrecognised heading in the project registry USED TO BE CLASSIFIED, and
    # classified as the live category, so a renamed retirement section
    # resurrected every identifier under it. Here an unrecognised heading has
    # always registered nothing, so a renamed `## Removed` makes retirements
    # invisible rather than live — and reporting every unrecognised heading in
    # a file that legitimately has half a dozen of them would fire on the
    # reference tables on every run, which is how a real finding gets ignored.
    default_section_category=None,
    tag_registry=TAG_REGISTRY,
    excludes_owner=True,
)

REGISTRY_SPECS: tuple[RegistrySpec, ...] = (PROJECT_SPEC, PEOPLE_SPEC)


# -----------------------------------------------------------------------------
# Orphan namespaced tags — a tag naming an identity no registry declares
# -----------------------------------------------------------------------------

# The known orphans of THIS base, one per line as `tag | path`. Owner data, not
# engine: it names identifiers out of the owner's own notes, so it never ships.
ORPHAN_BASELINE_NAME = "identity-orphan-baseline.txt"
ORPHAN_BASELINE_REL = f"_system/state/{ORPHAN_BASELINE_NAME}"


class IdentityAuditError(RuntimeError):
    """A declaration the audit cannot act on — never a finding about the base."""


def namespace_owners(
    specs: tuple[RegistrySpec, ...] = REGISTRY_SPECS,
) -> dict[str, RegistrySpec]:
    """`namespace -> the one registry that claims it`.

    The specs declare `category -> namespace`; this is the inverse, and it is
    built once here rather than open-coded wherever a namespace has to be
    resolved back to its owner. A namespace claimed twice is a defect of the
    declarations: picking either registry would make one of them read the
    other's identities as orphans, so it is refused rather than resolved.
    """
    owners: dict[str, RegistrySpec] = {}
    for spec in specs:
        for namespace in spec.expected_namespace.values():
            if namespace is None:
                continue
            other = owners.get(namespace)
            if other is not None and other is not spec:
                raise IdentityAuditError(
                    f"namespace `{namespace}` is claimed by both "
                    f"`{other.name}` and `{spec.name}` — one namespace, one "
                    f"registry, or every identity of one reads as an orphan "
                    f"of the other"
                )
            owners[namespace] = spec
    return owners


def _read_orphan_baseline(root: Path) -> set[tuple[str, str]]:
    path = root / ORPHAN_BASELINE_REL
    if not path.is_file():
        return set()
    out: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tag, _, where = line.partition("|")
        tag, where = tag.strip(), where.strip()
        if tag and where:
            out.add((tag, where))
    return out


def baseline_additions(root: Path, ref: str = "HEAD") -> list[str] | None:
    """Rows this working tree added to the orphan baseline since `ref`.

    The baseline is documented as a list that only shrinks, and documentation is
    not a mechanism: appending one line silences a real orphan, and every scan
    afterwards reports clean. Nothing in the file itself can tell an original
    row from one added yesterday — only its own history can, which is why this
    reads git rather than the file.

    Returns `None` — never `[]` — when the ref cannot be read, and the two are
    different facts that must not print the same word. A shallow checkout, no
    git, or a first commit all mean «nothing was compared»; reporting that as
    «nothing was added» is how a guard passes forever on a machine where it has
    never once run. The caller decides what an unestablished result is worth;
    in CI it is a failure, by the same rule the identity gate already applies to
    its own could-not-run.
    """
    import subprocess

    rel = ORPHAN_BASELINE_REL
    cwd = str(root.parent if root.name == "zettelkasten" else root)
    try:
        # Whether the REF resolves and whether the PATH existed in it are two
        # different questions, and `git show` fails the same way for both. Asked
        # together they turn the commit that first creates the baseline into a
        # «could not compare» failure — the guard would refuse its own seeding.
        known_ref = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        )
        if known_ref.returncode != 0:
            return None
        prior = subprocess.run(
            ["git", "show", f"{ref}:zettelkasten/{rel}"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        )
    except OSError:
        return None
    if prior.returncode != 0:
        # The ref is good and the file is not in it: the baseline is being
        # created here. Nothing to compare against, and a creating commit is
        # read in review like any other. Removing the file and re-adding it with
        # fresh rows would slip past this — as two commits that both show what
        # they did, which is the level of visibility this guard is for.
        return []
    def _rows(text: str) -> set[str]:
        out = set()
        for raw in text.splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                out.add(line)
        return out
    path = root / rel
    now = _rows(path.read_text(encoding="utf-8")) if path.is_file() else set()
    before = _rows(prior.stdout)
    # A note renamed since `ref` keeps its row: the row's path follows the file,
    # and that is the same orphan under a new name, not a new orphan. Git's
    # rename detection between the two trees is the one source for that map.
    renamed = _renames_since(cwd, ref)
    if renamed:
        carried = set()
        for row in before:
            tag, sep, old_path = row.partition("|")
            old_path = old_path.strip()
            if sep and old_path in renamed:
                carried.add(f"{tag.strip()} | {renamed[old_path]}")
        before |= carried
    return sorted(now - before)


def _renames_since(cwd: str, ref: str) -> dict[str, str]:
    """`old -> new` for every file git sees renamed between `ref` and the
    working tree, as paths relative to the base (`zettelkasten/`)."""
    import subprocess

    try:
        diff = subprocess.run(
            # 30 %: a note whose body was rewritten by a product rename keeps
            # well under half its lines, and git's default 50 % then reports the
            # move as a delete plus an add — which is exactly the shape this map
            # exists to see through.
            ["git", "diff", "--name-status", "-M30%", "--diff-filter=R", ref],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        )
    except OSError:
        return {}
    if diff.returncode != 0:
        return {}
    out: dict[str, str] = {}
    prefix = "zettelkasten/"
    for line in diff.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        old_path, new_path = parts[1], parts[2]
        if old_path.startswith(prefix) and new_path.startswith(prefix):
            out[old_path[len(prefix):]] = new_path[len(prefix):]
    return out


def _tags_of(fm: dict) -> list[str]:
    tags = fm.get("tags")
    if isinstance(tags, str):
        return [tags]
    if isinstance(tags, list):
        return [t for t in tags if isinstance(t, str)]
    return []


def scan_orphan_tags(
    root: Path,
    files: list[ClassifiedFile],
    registries: dict[str, dict[str, RegistryEntry]],
    specs: tuple[RegistrySpec, ...] = REGISTRY_SPECS,
) -> list[dict]:
    """Tags naming an identity that the claiming registry never declared.

    The audit reasons outward from declared identities, so an identifier that
    was never declared has no entity to reason from and is examined by nothing.
    The registry is the source of truth for what a project or a person IS; a tag
    in its namespace naming something absent from it is drift by that same rule.

    Only LIVE surfaces are read, and the class comes from the audit's own
    classification rather than a second list of excluded paths — a second list
    is how the two would drift apart.
    """
    owners = namespace_owners(specs)
    findings: list[dict] = []
    for item in files:
        if item.rule.surface_class != CLASS_LIVE:
            continue
        parsed = read_frontmatter(item.path)
        if not parsed:
            continue
        fm, _ = parsed
        for tag in _tags_of(fm):
            split = _split_tag(tag)
            if split is None:
                continue
            namespace, identifier = split
            spec = owners.get(namespace)
            if spec is None:
                continue  # nobody claims this namespace; it declares no identity
            if identifier in registries.get(spec.name, {}):
                continue  # declared — live or retired, both are the audit's job
            rel = item.path.relative_to(root).as_posix()
            findings.append({
                "scan": "orphan-tag",
                "tag": tag,
                "namespace": namespace,
                "identifier": identifier,
                "registry": namespace,
                "registry_path": spec.registry_path,
                "path": rel,
                "reason": (
                    f"`{tag}` names `{identifier}` in the `{namespace}` "
                    f"namespace, and {spec.registry_path} does not declare it "
                    f"— neither live nor retired. Nothing else examines this: "
                    f"every other check reasons outward from a declared "
                    f"identity."
                ),
                "to_resolve": (
                    f"Decide which it is and do that one thing: register "
                    f"`{identifier}`, retag the note to an identity that "
                    f"exists, or drop the tag. The choice is the owner's — the "
                    f"three are not interchangeable."
                ),
            })
    return findings

# Body-text markers accepted as boundary-case annotation when
# projects.length == 2.
BOUNDARY_MARKERS: tuple[str, ...] = (
    "boundary case",
    "boundary:",
    "cross-project",
    "joint review",
    "boundary record",
)


# -----------------------------------------------------------------------------
# Surface detection
# -----------------------------------------------------------------------------

def _wikilink_re(entity_id: str) -> re.Pattern[str]:
    r"""Every legal Obsidian link to this node, and nothing else.

    Five shapes, all of which resolve to the same node: `[[id]]`, `[[id|label]]`,
    `[[id#section]]`, the path form `[[1_projects/id]]` that Obsidian writes
    whenever a bare name would be ambiguous, and the table form `[[id\|label]]`
    whose pipe is backslash-escaped because an unescaped one would end the
    markdown cell. Missing the path form is not a smaller version of the same
    check — it is a link the migration will not find, in the one situation (a
    duplicated name) where the base already told us the graph is delicate. The
    table form is the same failure with the opposite frequency: every hub map
    this engine renders writes it, so a retirement landing in a hub map is
    exactly the case a scan blind to it would call clean.

    The optional prefix must end in `/`, which is what keeps
    `[[{id}-something]]` and `[[x-{id}]]` out: the identifier is matched whole,
    in a known position, on both sides. The escape is optional in the
    lookahead rather than consumed, so the terminator stays part of the
    boundary and a longer identifier is still not a match.
    """
    return re.compile(
        r"\[\[\s*(?:[^\]|#\n]*/)?" + re.escape(entity_id) + r"\s*(?=\\?[\]|#])"
    )


_FENCE_RE = re.compile(r"^(?:`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _mask_code(text: str) -> str:
    """The same text with every code span blanked out, offsets preserved.

    A `[[link]]` inside backticks or a fenced block is not a surface of an
    identity — it is quoted documentation ABOUT a link, and reporting it pushes
    a migration toward editing the very docs that explain the format. Blanking
    with spaces rather than deleting keeps every line number and every offset
    of the untouched text exactly where it was, so a finding still points at
    the real line.
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        stripped = line.lstrip()
        m = _FENCE_RE.match(stripped)
        if fence is None:
            if m:
                fence = m.group(0)[0]
                out.append(" " * len(line))
                continue
        else:
            if m and m.group(0)[0] == fence:
                fence = None
            out.append(" " * len(line))
            continue
        out.append(_INLINE_CODE_RE.sub(lambda mm: " " * len(mm.group(0)), line))
    return "\n".join(out)


def hub_id_of(entity_id: str) -> str:
    """The identifier of this identity's hub node.

    Normally `hub-{id}`. An identity whose OWN identifier already begins
    `hub-` is the exception, and composing blindly loses it: the audit would
    probe `hub-hub-{id}`, find nothing, and report zero residue while the real
    node sat in plain sight. An identifier that already carries the prefix IS
    the hub identifier.
    """
    return (
        entity_id if entity_id.startswith(HUB_PREFIX)
        else f"{HUB_PREFIX}{entity_id}"
    )


def hub_path(root: Path, entity_id: str) -> Path:
    return root.joinpath(*HUB_DIR) / f"{hub_id_of(entity_id)}.md"


def hub_is_node_of(root: Path, entity_id: str) -> bool:
    """True when `hub-{id}.md` exists AND declares itself `hub-{id}`.

    Both halves matter. The path check alone already rejects a hub whose name
    merely contains the identifier, because the name is compared whole; the
    frontmatter check then rejects a file that was copied or renamed into that
    name while still declaring a different identity. Identity is what the file
    says it is, not what its name looks like.
    """
    path = hub_path(root, entity_id)
    if not path.is_file():
        return False
    fm_body = read_frontmatter(path)
    if fm_body is None:
        return False
    declared = fm_body[0].get("id")
    if declared is None:
        return True  # no self-declaration — the exact filename is the identity
    return str(declared).strip() == hub_id_of(entity_id)


def canonical_node(
    root: Path, entity_id: str, spec: "RegistrySpec" = None,  # type: ignore[assignment]
) -> str | None:
    """The link target that names this identity's canonical node.

    Resolution is by ROLE, in order: canonical hub → node card → node
    container README. The first that exists wins; the rest are derived nodes of
    the same identity and never the link target. A role the registry does not
    declare is skipped — it cannot be the canonical node of an identity whose
    registry says it has no such node. Returns the wikilink target (without
    brackets), or None when the identity has no node at all.
    """
    spec = spec or PROJECT_SPEC
    if SURFACE_HUB in spec.surfaces and hub_is_node_of(root, entity_id):
        return hub_id_of(entity_id)
    if spec.node_dir is None:
        return None
    node_dir = root / spec.node_dir
    if SURFACE_NODE_CARD in spec.surfaces and (node_dir / f"{entity_id}.md").is_file():
        return entity_id
    if (
        SURFACE_NODE_CONTAINER in spec.surfaces
        and (node_dir / entity_id / "README.md").is_file()
    ):
        return entity_id
    return None


def _hub_kind(root: Path, entity_id: str) -> tuple[str | None, bool]:
    """(hub_kind, hub_exists) for the drift event stream. `hub_kind` defaults to
    `project` when the field is absent on an existing hub."""
    path = hub_path(root, entity_id)
    if not path.exists():
        return None, False
    fm_body = read_frontmatter(path)
    if fm_body is None:
        return None, True  # malformed frontmatter — surface as unknown
    kind = fm_body[0].get("hub_kind")
    if kind is None:
        return "project", True
    return str(kind).strip().lower(), True


def _split_tag(tag: str) -> tuple[str, str] | None:
    """`namespace/identifier` → (namespace, identifier); None when unnamespaced."""
    if "/" not in tag:
        return None
    namespace, _, tail = tag.rpartition("/")
    if not namespace or not tail:
        return None
    return namespace, tail


def _line_of(lines: list[str], needle: str, *, exact_token: bool) -> int | None:
    for i, line in enumerate(lines, start=1):
        if exact_token:
            if line.strip().lstrip("-").strip().strip("\"'") == needle:
                return i
        elif needle in line:
            return i
    return None


# -----------------------------------------------------------------------------
# Successor integrity — resolved once per identity, before any surface is read
# -----------------------------------------------------------------------------
#
# Two things were wrong with reading `entity.successor` at each surface.
#
# It resolves ONE HOP. `A→B→C` yields B, so applying the audit's own work list
# produces fresh residue: every reference to A now names an identifier that is
# itself retired. The contract's reader resolves to the TERMINAL LIVE successor,
# which means walking the chain — and refusing when the walk does not end in a
# live identifier, rather than handing back the last thing it saw.
#
# And it reports a defect of the ROW once per REFERENCE. A `rename` that names
# no successor produced four findings all targeting nothing and no complaint
# about the row that caused them. The row is the thing that is wrong, it is
# wrong once, and until it is fixed there is no deterministic target — so a
# malformed row suppresses every automatic rewrite for that identity.

# -----------------------------------------------------------------------------
# Reason codes — the machine half of every finding
# -----------------------------------------------------------------------------
#
# Every finding carries a `kind`, and these are the whole vocabulary of it. The
# consumer keys deduplication on this value, so a code the consumer has to mint
# for itself differs between nights and the same finding re-surfaces as new
# forever. A prose `reason` cannot carry that weight: it is written for a human
# and it changes whenever the sentence improves.
#
# `kind` on a FINDING is the kind of problem. `kind` on an IDENTITY is the kind
# of identity change (merge / rename / split / void). Both names are right in
# their own frame and the event stream already spells the first one `kind`, so
# a finding also carries `change_kind` for the second rather than renaming
# either.

CODE_FIELD_RETIRED = "identity-field-retired"
CODE_FIELD_NON_MEMBER = "identity-field-non-member"
CODE_TAG_RETIRED = "identity-tag-retired"
CODE_TAG_NAMESPACE = "identity-tag-namespace"
CODE_WIKILINK_RETIRED = "identity-wikilink-retired"
CODE_WIKILINK_REPOINT = "identity-wikilink-repoint"
CODE_NODE_RELOCATE = "identity-node-relocate"
CODE_DERIVED_STALE = "identity-derived-stale"
CODE_KIND_UNKNOWN = "identity-kind-unknown"
CODE_SUCCESSOR_UNDECLARED = "identity-successor-undeclared"
CODE_SUCCESSOR_FORBIDDEN = "identity-successor-forbidden"
CODE_SUCCESSOR_UNRESOLVABLE = "identity-successor-unresolvable"
CODE_SPLIT_UNDECIDED = "identity-split-undecided"
CODE_ROW_DUPLICATE = "identity-registry-row-duplicate"
CODE_ROW_UNREADABLE = "identity-registry-row-unreadable"
CODE_SECTION_UNKNOWN = "identity-registry-section-unknown"
CODE_UNCLASSIFIED = "identity-surface-unclassified"
CODE_HUB_KIND_MISMATCH = "identity-hub-kind-mismatch"

INTEGRITY_CODES: tuple[str, ...] = (
    CODE_KIND_UNKNOWN,
    CODE_SUCCESSOR_UNDECLARED,
    CODE_SUCCESSOR_FORBIDDEN,
    CODE_SUCCESSOR_UNRESOLVABLE,
)

# Every code this scanner can emit — the closed set a consumer may rely on.
REASON_CODES: tuple[str, ...] = (
    CODE_FIELD_RETIRED, CODE_FIELD_NON_MEMBER,
    CODE_TAG_RETIRED, CODE_TAG_NAMESPACE,
    CODE_WIKILINK_RETIRED, CODE_WIKILINK_REPOINT,
    CODE_NODE_RELOCATE, CODE_DERIVED_STALE,
    CODE_SPLIT_UNDECIDED,
    CODE_ROW_DUPLICATE, CODE_ROW_UNREADABLE, CODE_SECTION_UNKNOWN,
    CODE_UNCLASSIFIED,
) + INTEGRITY_CODES


@dataclass(frozen=True)
class Resolution:
    """What a reference to this identity resolves to, and why.

    `terminal` is the live identifier every live reference migrates to, or None
    when there is not exactly one. `defect` names the integrity code when the
    row itself is at fault; `chain` is the walk that was actually performed, so
    a reader can see where it stopped instead of being told it failed.
    """

    terminal: str | None
    chain: tuple[str, ...]
    defect: str | None
    detail: str
    successors: tuple[str, ...] = ()

    @property
    def well_formed(self) -> bool:
        return self.defect is None

    @property
    def is_split(self) -> bool:
        """A genuine split — several successors AND a row that says so.

        Several successors on a row whose kind permits one is a defect, not a
        split, and must not be rendered as an owner choice between them: the
        row does not mean «either of these», it means somebody wrote two where
        one belongs.
        """
        return self.defect is None and len(self.successors) > 1


def _chain_text(chain: tuple[str, ...]) -> str:
    return " → ".join(chain)


def _walk_successors(
    registry: dict[str, RegistryEntry], start: str, first: str,
) -> Resolution:
    """Follow the successor chain to its terminal live identifier.

    Bounded by the number of rows the registry holds and refusing to revisit an
    identifier, so a cycle is reported rather than spun on. Every way the walk
    can fail to reach a live identifier — a cycle, a chain into void or split,
    a hop out of this registry, a row that does not declare its next hop — is
    the same answer: no target, and the chain that got here.
    """
    chain = [start]
    current = first
    for _ in range(len(registry) + 1):
        chain.append(current)
        if current in chain[:-1]:
            return Resolution(
                None, tuple(chain), CODE_SUCCESSOR_UNRESOLVABLE,
                f"the successor chain {_chain_text(tuple(chain))} is a cycle "
                f"and reaches no live identifier",
            )
        entry = registry.get(current)
        if entry is None:
            return Resolution(
                None, tuple(chain), CODE_SUCCESSOR_UNRESOLVABLE,
                f"the successor chain {_chain_text(tuple(chain))} leaves this "
                f"registry — `{current}` has no row in it, so nothing here "
                f"says what it means",
            )
        if entry.category != RETIRED_CATEGORY:
            return Resolution(current, tuple(chain), None, "", (current,))
        if entry.kind == "void":
            return Resolution(
                None, tuple(chain), CODE_SUCCESSOR_UNRESOLVABLE,
                f"the successor chain {_chain_text(tuple(chain))} ends in a "
                f"`void` identity, which by the contract never existed",
            )
        if len(entry.successors) > 1:
            return Resolution(
                None, tuple(chain), CODE_SUCCESSOR_UNRESOLVABLE,
                f"the successor chain {_chain_text(tuple(chain))} reaches a "
                f"`split`, and which of its successors a given reference means "
                f"is not something the registry holds",
            )
        if not entry.successors:
            return Resolution(
                None, tuple(chain), CODE_SUCCESSOR_UNRESOLVABLE,
                f"the successor chain {_chain_text(tuple(chain))} stops at a "
                f"retired identifier that declares no successor of its own",
            )
        current = entry.successors[0]
    return Resolution(
        None, tuple(chain), CODE_SUCCESSOR_UNRESOLVABLE,
        f"the successor chain {_chain_text(tuple(chain))} did not terminate "
        f"within the number of rows the registry holds",
    )


def resolve_identity(
    entity: RegistryEntry, registry: dict[str, RegistryEntry],
) -> Resolution:
    """The terminal live successor of one identity, or the defect that stops it.

    Live identities resolve to themselves — they are not going anywhere, and
    the caller asks the same question of every identity so it never has to
    branch on category first.
    """
    if entity.category != RETIRED_CATEGORY:
        return Resolution(
            entity.entity_id, (entity.entity_id,), None, "",
            (entity.entity_id,),
        )
    kind = entity.kind
    declared = entity.successors
    if kind == IDENTITY_KIND_UNKNOWN and entity.kind_declared:
        return Resolution(
            None, (entity.entity_id,), CODE_KIND_UNKNOWN,
            "the retirement row has somewhere to say what happened to this "
            "identifier — merge, rename, split or void — and does not say it, "
            "so no rule decides what its references should become",
            declared,
        )
    if kind is None or kind == IDENTITY_KIND_UNKNOWN:
        # The older registry shape: no Kind column at all, or a prose reason
        # this engine could not read one out of. Not a defect of the row — it
        # never had anywhere to state a kind, and its successor cell is still
        # enough to resolve a target. A row that also names no successor simply
        # has no target, reported at each surface as it always was. Inventing a
        # defect here would flag every retirement recorded before the column
        # existed.
        if not declared:
            return Resolution(None, (entity.entity_id,), None, "", ())
        return _walk_successors(registry, entity.entity_id, declared[0])
    arity = SUCCESSOR_ARITY.get(kind)
    if arity is not None:
        low, high = arity
        if len(declared) < low:
            code = (
                CODE_SUCCESSOR_FORBIDDEN if kind == "split"
                else CODE_SUCCESSOR_UNDECLARED
            )
            return Resolution(
                None, (entity.entity_id,), code,
                f"a `{kind}` row must declare "
                f"{'at least two successors' if kind == 'split' else 'a successor'}"
                f", and this one declares "
                f"{len(declared) or 'none'}",
                declared,
            )
        if high is not None and len(declared) > high:
            return Resolution(
                None, (entity.entity_id,), CODE_SUCCESSOR_FORBIDDEN,
                f"a `{kind}` row must declare "
                f"{'no successor' if high == 0 else 'exactly one successor'}, "
                f"and this one declares {len(declared)} "
                f"({', '.join(declared)})",
                declared,
            )
    if kind == "void":
        return Resolution(None, (entity.entity_id,), None, "", ())
    if kind == "split":
        return Resolution(None, (entity.entity_id,), None, "", declared)
    return _walk_successors(registry, entity.entity_id, declared[0])


@dataclass(frozen=True)
class _Disposition:
    """How every live reference to one retired identity is disposed of.

    Computed once per identity from its `Resolution`, so the three surface
    scans below never re-derive it and never disagree about it.
    """

    action: str
    severity: str
    autofixable: bool
    suffix: str
    successors: tuple[str, ...] = ()

    def code_for(self, default: str) -> str:
        """The reason code for a surface whose ordinary code is `default`.

        A split overrides it: what is wrong with the surface is not that it
        names a dead identifier but that it names one of several live ones, and
        the two want different handling downstream.
        """
        return CODE_SPLIT_UNDECIDED if self.successors else default

    def target_label(
        self, resolved: str | None, *, split_prefix: str = "",
        split_suffix: str = "",
    ) -> str | None:
        """The target to show for this surface.

        A split has no single target, so the label names the declared
        successors instead of picking one — the finding exists so the residue
        is counted and walked, not so it can be rewritten.
        """
        if self.successors:
            return "one of: " + " | ".join(
                f"{split_prefix}{s}{split_suffix}" for s in self.successors
            )
        return resolved


def _disposition(resolution: Resolution, base_action: str) -> _Disposition:
    if resolution.is_split:
        return _Disposition(
            "decide", "weak", False,
            f" that split into {', '.join(resolution.successors)}; which one "
            f"this reference means is decided by what the reference says, not "
            f"by anything the registry holds",
            resolution.successors,
        )
    if not resolution.well_formed:
        return _Disposition(
            base_action, "strong", False,
            f", and its retirement row is malformed, so there is no "
            f"deterministic target to write — {resolution.detail}. Fix the row "
            f"first; the defect is reported against it.",
        )
    return _Disposition(base_action, "strong", True, "")


def _resolution_for(
    entity: RegistryEntry, resolutions: dict[str, Resolution] | None,
) -> Resolution:
    if resolutions and entity.entity_id in resolutions:
        return resolutions[entity.entity_id]
    return Resolution(
        entity.successor, (entity.entity_id,), None, "", entity.successors,
    )


# -----------------------------------------------------------------------------
# Findings
# -----------------------------------------------------------------------------

def _finding(
    entity: RegistryEntry,
    surface: str,
    surface_class: str,
    path: str,
    *,
    registry: str,
    line: int | None = None,
    current: str | None = None,
    target: str | None = None,
    action: str,
    reason: str,
    kind: str,
    severity: str = "strong",
    autofixable: bool = True,
) -> dict:
    # A derived surface naming a retired identifier is one thing whatever the
    # role it sits in: stale output waiting for its own regeneration. Deciding
    # that here rather than at each call site is what keeps a caller from
    # proposing a hand-edit to a file the next rebuild overwrites.
    if (
        surface_class == CLASS_DERIVED
        and entity.category == RETIRED_CATEGORY
        and kind not in INTEGRITY_CODES
        and kind != CODE_SPLIT_UNDECIDED
    ):
        kind = CODE_DERIVED_STALE
    return {
        "identity": entity.entity_id,
        "registry": registry,
        "category": entity.category,
        "kind": kind,
        "change_kind": entity.kind,
        "successor": entity.successor,
        "successors": list(entity.successors),
        "surface": surface,
        "surface_class": surface_class,
        "path": path,
        "line": line,
        "current": current,
        "target": target,
        "action": action,
        "reason": reason,
        "severity": severity,
        "autofixable": autofixable,
    }


def _tag_target(
    entity: RegistryEntry,
    namespace: str,
    spec: RegistrySpec,
    resolution: Resolution,
) -> str | None:
    if entity.category == RETIRED_CATEGORY:
        return f"{namespace}/{resolution.terminal}" if resolution.terminal else None
    expected = spec.expected_namespace.get(entity.category)
    return f"{expected}/{entity.entity_id}" if expected else None


def _scan_text_surfaces(
    path: Path,
    root: Path,
    entities: list[RegistryEntry],
    surface_class: str,
    repoint: dict[str, str | None] | None = None,
    spec: RegistrySpec = PROJECT_SPEC,
    body_immutable: bool = False,
    resolutions: dict[str, Resolution] | None = None,
) -> list[dict]:
    """Field, tag and wikilink surfaces in one file.

    `repoint` maps an identity whose node this audit marks for relocation to the
    link target its inbound links must be repointed at. A link into a node that
    is about to stop existing at its current path is live work exactly like the
    node itself — reporting the node and not its inbound links certifies a graph
    that breaks the moment the node moves.

    `body_immutable` splits the file where the contract splits it. Frontmatter
    is engine-managed classification and is matched normally; the body is
    matched only when it is not history. Running the link regex over the whole
    file text of a record makes the next retirement of anything ever MENTIONED
    in a meeting demand that the meeting be rewritten — the one migration the
    contract forbids outright.
    """
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    rel = path.relative_to(root).as_posix()
    lines = text.splitlines()
    fm_body = read_frontmatter(path)
    fm: dict = fm_body[0] if fm_body else {}
    # The frontmatter span, in characters: `read_frontmatter` returns the body
    # verbatim, so its length locates the boundary exactly. No frontmatter
    # means the whole file is body — and a record that is all body has no live
    # text surface at all, which is the correct reading of it.
    body_start = len(text) - len(fm_body[1]) if fm_body else 0
    link_text = _mask_code(text)
    if body_immutable:
        link_text = link_text[:body_start]

    raw_members = fm.get(spec.membership_field) if spec.membership_field else None
    members = (
        [str(p).strip() for p in raw_members if p]
        if isinstance(raw_members, list) else []
    )
    raw_tags = fm.get("tags")
    tags = (
        [str(t).strip() for t in raw_tags if t]
        if isinstance(raw_tags, list) else []
    )

    action = "regenerate" if surface_class == CLASS_DERIVED else "migrate"

    field = spec.membership_field
    for entity in entities:
        eid = entity.entity_id
        retired = entity.category == RETIRED_CATEGORY
        res = _resolution_for(entity, resolutions)
        # How a retired identity's live references are disposed of. Three
        # cases, and only the first one is a rewrite anything may perform
        # automatically.
        marks = _disposition(res, action)

        # 1. field — membership array entry, exact equality
        if SURFACE_FIELD in spec.surfaces and eid in members:
            if retired:
                reason = f"{field}: entry names a retired identifier{marks.suffix}"
                target = marks.target_label(res.terminal)
            else:
                reason = (
                    f"{field}: entry names a registered {entity.category}, "
                    f"which does not belong on the {field} axis"
                )
                target = None
            out.append(_finding(
                entity, SURFACE_FIELD, surface_class, rel,
                registry=spec.name,
                line=_line_of(lines, eid, exact_token=True),
                current=eid, target=target,
                action=marks.action if retired else "demote", reason=reason,
                kind=(
                    marks.code_for(CODE_FIELD_RETIRED) if retired
                    else CODE_FIELD_NON_MEMBER
                ),
                severity=marks.severity if retired else "strong",
                autofixable=marks.autofixable if retired else False,
            ))

        # 2. tag — `{namespace}/{id}`, exact equality on the identifier part
        expected = spec.expected_namespace.get(entity.category)
        for tag in tags if SURFACE_TAG in spec.surfaces else ():
            split = _split_tag(tag)
            if split is None or split[1] != eid:
                continue
            namespace = split[0]
            if not retired and namespace == expected:
                continue  # correctly namespaced — not residue
            reason = (
                f"tag names a retired identifier{marks.suffix}" if retired
                else f"tag sits in the `{namespace}` namespace; "
                     f"this identifier belongs in `{expected}`"
            )
            out.append(_finding(
                entity, SURFACE_TAG, surface_class, rel,
                registry=spec.name,
                line=_line_of(lines, tag, exact_token=True),
                current=tag,
                target=marks.target_label(
                    _tag_target(entity, namespace, spec, res),
                    split_prefix=f"{namespace}/",
                ),
                action=marks.action if retired else "renamespace",
                reason=reason,
                kind=(
                    marks.code_for(CODE_TAG_RETIRED) if retired
                    else CODE_TAG_NAMESPACE
                ),
                severity=marks.severity if retired else "strong",
                autofixable=marks.autofixable if retired else True,
            ))

        # 3. wikilink — a retired identifier makes every link to it residue. A
        #    live identity does not, EXCEPT when this audit is moving the node
        #    the link resolves to: the identity stays, only its node moves, so
        #    the link is repointed rather than retired.
        if SURFACE_WIKILINK not in spec.surfaces:
            continue
        link_code, link_severity, link_autofix = (
            CODE_WIKILINK_REPOINT, "strong", True,
        )
        if retired:
            # A link must name a NODE, not an identifier. The terminal
            # successor's identifier is what a field or a tag carries;
            # resolving it through the same role order every other link uses is
            # what keeps the suggestion from being a broken link to a node that
            # never existed.
            successor_node = (
                canonical_node(root, res.terminal, spec)
                if res.terminal else None
            )
            link_target = marks.target_label(
                f"[[{successor_node}]]" if successor_node else None,
                split_prefix="[[", split_suffix="]]",
            )
            link_action = marks.action
            link_reason = f"wikilink targets a retired identifier{marks.suffix}"
            link_code, link_severity, link_autofix = (
                marks.code_for(CODE_WIKILINK_RETIRED),
                marks.severity, marks.autofixable,
            )
        elif repoint and eid in repoint:
            node = repoint[eid]
            link_target = f"[[{node}]]" if node else None
            link_action = "regenerate" if surface_class == CLASS_DERIVED else "repoint"
            link_reason = (
                f"wikilink resolves to the node this audit relocates. The "
                f"`{eid}` identity stays live — only its node moves, so the "
                f"link is repointed at the canonical node, not retired."
            )
        else:
            continue

        for m in _wikilink_re(eid).finditer(link_text):
            line_no = text.count("\n", 0, m.start()) + 1
            out.append(_finding(
                entity, SURFACE_WIKILINK, surface_class, rel,
                registry=spec.name,
                line=line_no, current=f"[[{eid}]]",
                target=link_target, action=link_action, reason=link_reason,
                kind=link_code, severity=link_severity,
                autofixable=link_autofix,
            ))
    return out


def _scan_node_surfaces(
    root: Path, entities: list[RegistryEntry], spec: RegistrySpec = PROJECT_SPEC,
    resolutions: dict[str, Resolution] | None = None,
) -> list[dict]:
    """Card, container and hub — the file-level surfaces of an identity.

    Each role is looked for only when the registry declares it. A people
    identity therefore never reports a container or a hub: the registry states
    it has neither, and looking anyway would invent a surface.
    """
    out: list[dict] = []
    node_dir = root / spec.node_dir if spec.node_dir else None
    for entity in entities:
        eid = entity.entity_id
        retired = entity.category == RETIRED_CATEGORY
        misplaced = retired or entity.category in spec.relocate_categories
        if node_dir is not None and misplaced:
            card = node_dir / f"{eid}.md"
            container = node_dir / eid
            if SURFACE_NODE_CARD in spec.surfaces and card.is_file():
                out.append(_finding(
                    entity, SURFACE_NODE_CARD, CLASS_LIVE,
                    card.relative_to(root).as_posix(),
                    registry=spec.name,
                    current=card.relative_to(root).as_posix(),
                    target=None, action="relocate",
                    kind=CODE_NODE_RELOCATE,
                    autofixable=False,
                    reason=(
                        "node card of a retired identifier" if retired
                        else f"node card sits under {spec.node_dir}/ but the "
                             f"registry classifies this identifier as a "
                             f"{entity.category}"
                    ),
                ))
            if SURFACE_NODE_CONTAINER in spec.surfaces and container.is_dir():
                out.append(_finding(
                    entity, SURFACE_NODE_CONTAINER, CLASS_LIVE,
                    container.relative_to(root).as_posix() + "/",
                    registry=spec.name,
                    current=container.relative_to(root).as_posix() + "/",
                    target=None, action="relocate",
                    kind=CODE_NODE_RELOCATE,
                    autofixable=False,
                    reason=(
                        "node container of a retired identifier" if retired
                        else f"node container sits under {spec.node_dir}/ but "
                             f"the registry classifies this identifier as a "
                             f"{entity.category}"
                    ),
                ))
        if SURFACE_HUB in spec.surfaces and retired and hub_is_node_of(root, eid):
            res = _resolution_for(entity, resolutions)
            marks = _disposition(res, "relocate")
            out.append(_finding(
                entity, SURFACE_HUB, CLASS_LIVE,
                hub_path(root, eid).relative_to(root).as_posix(),
                registry=spec.name,
                current=hub_id_of(eid),
                target=marks.target_label(
                    hub_id_of(res.terminal) if res.terminal else None,
                    split_prefix=HUB_PREFIX,
                ),
                action="relocate",
                reason=f"hub is the node of a retired identifier{marks.suffix}",
                kind=marks.code_for(CODE_NODE_RELOCATE),
                # Never autofixable, like every other node surface: where a
                # node belongs depends on what it CONTAINS, which no registry
                # knows. The registry decides the identifier, not the home.
                severity=marks.severity, autofixable=False,
            ))
    return out


# -----------------------------------------------------------------------------
# Registry surfaces — the row that declares the identity, and the tag row
# -----------------------------------------------------------------------------

def _scan_registry_row_surfaces(
    root: Path,
    spec: RegistrySpec,
    entities: list[RegistryEntry],
    resolutions: dict[str, Resolution],
    surface_class: str,
) -> tuple[list[dict], list[dict]]:
    """`(findings, registry_defects)` for the registry itself.

    Two things live here that no surface walk can see. **Integrity** — a
    retirement row that breaks its own kind's successor rule is a defect of the
    ROW, reported once here rather than once per reference that pointed at it.
    **Duplication** — an identifier declared retired in one section and live in
    another is a registry saying two things about itself, and whichever one the
    parser happens to read last becomes the answer for the whole engine.

    Registry-level defects come back separately because they belong to no
    identity. A mistyped row is otherwise indistinguishable from no row at all,
    and a section heading nobody recognises un-retires everything under it —
    neither has an identity to be filed against, and both make the scan report
    clean for the wrong reason.
    """
    findings: list[dict] = []
    unreadable: list[dict] = []
    if spec.section_category is None:
        return findings, unreadable
    rows = registry_rows(
        root / spec.registry_path, spec.section_category,
        spec.default_section_category,
    )
    if SURFACE_REGISTRY_ROW not in spec.surfaces:
        return findings, unreadable

    # A heading no rule recognises is reported once, for the section, not once
    # per row under it. The rows are collateral: what actually happened is that
    # a section of the registry stopped being a section of the registry.
    unknown_sections: dict[str, int] = {}
    for row in rows:
        if row.category == REGISTRY_SECTION_UNKNOWN:
            unknown_sections[row.section] = row.line
    for header, line in sorted(unknown_sections.items(), key=lambda kv: kv[1]):
        unreadable.append({
            "identity": None,
            "registry": spec.name,
            "surface": SURFACE_REGISTRY_ROW,
            "surface_class": surface_class,
            "path": spec.registry_path,
            "line": line,
            "current": header,
            "target": None,
            "action": "repair",
            "kind": CODE_SECTION_UNKNOWN,
            "severity": "strong",
            "autofixable": False,
            "reason": (
                f"`{spec.registry_path}` has a section headed `{header}` that "
                f"no rule recognises, and it holds table rows. Nothing "
                f"classifies them, so they declare no identity at all. If this "
                f"is the retirement section under a new name, every identifier "
                f"in it has silently stopped being retired — and a scan for "
                f"residue then reports clean because there is nothing retired "
                f"left to have any."
            ),
        })

    by_id: dict[str, list] = {}
    for row in rows:
        if row.category == REGISTRY_SECTION_UNKNOWN:
            continue  # already reported, once, as the section it is
        if row.entity_id is None:
            unreadable.append({
                "identity": None,
                "registry": spec.name,
                "surface": SURFACE_REGISTRY_ROW,
                "surface_class": surface_class,
                "path": spec.registry_path,
                "line": row.line,
                "current": row.raw,
                "target": None,
                "action": "repair",
                "kind": CODE_ROW_UNREADABLE,
                "severity": "strong",
                "autofixable": False,
                "reason": (
                    f"row {row.line} of `{spec.registry_path}` is in the "
                    f"`{row.category}` section but its first cell, "
                    f"`{row.raw}`, is not a readable identifier. The row is "
                    f"silently dropped, so whatever it was meant to declare "
                    f"reads as if it had never been written."
                ),
            })
            continue
        by_id.setdefault(row.entity_id, []).append(row)

    for entity in entities:
        eid = entity.entity_id
        res = resolutions.get(eid)
        rows_here = by_id.get(eid, [])
        categories = {
            r.category for r in rows_here
            if r.category != REGISTRY_SECTION_UNKNOWN
        }
        line = rows_here[0].line if rows_here else None

        if res is not None and res.defect is not None:
            findings.append(_finding(
                entity, SURFACE_REGISTRY_ROW, surface_class,
                spec.registry_path, registry=spec.name, line=line,
                current=eid, target=None, action="repair",
                kind=res.defect, severity="strong", autofixable=False,
                reason=(
                    f"the retirement row for `{eid}` is malformed: "
                    f"{res.detail}. Until the row is fixed there is no "
                    f"deterministic target, so every automatic rewrite for "
                    f"this identity is suppressed."
                ),
            ))

        if entity.category == RETIRED_CATEGORY and categories - {RETIRED_CATEGORY}:
            others = ", ".join(sorted(categories - {RETIRED_CATEGORY}))
            findings.append(_finding(
                entity, SURFACE_REGISTRY_ROW, surface_class,
                spec.registry_path, registry=spec.name, line=line,
                current=eid, target=None, action="migrate",
                kind=CODE_ROW_DUPLICATE, severity="strong", autofixable=False,
                reason=(
                    f"`{eid}` is retired and still has a live row in the "
                    f"`{others}` section of the same registry. One identifier "
                    f"declared twice means the registry answers its own "
                    f"question differently depending on which row is read "
                    f"last."
                ),
            ))
    return findings, unreadable


_TAG_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def _scan_tag_registry_surfaces(
    root: Path,
    spec: RegistrySpec,
    entities: list[RegistryEntry],
    resolutions: dict[str, Resolution],
    surface_class: str,
) -> list[dict]:
    """The rows of the tag registry that declare `{namespace}/{id}`.

    Its class is not decided here — it is whatever the classification says
    about the file, which for this engine is DERIVED: the tag registry is
    rebuilt from the corpus between its AUTO-GENERATED markers, so a row naming
    a retired identifier disappears when the corpus that produced it is
    migrated. Reporting it is still worth doing: it is the visible proof that
    either the corpus still carries the tag or the regeneration has not run.
    """
    out: list[dict] = []
    if SURFACE_TAG_REGISTRY_ROW not in spec.surfaces or not spec.tag_registry:
        return out
    path = root / spec.tag_registry
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out

    declared: list[tuple[int, str, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _TAG_ROW_RE.match(line.strip())
        if not m:
            continue
        split = _split_tag(m.group(1).strip())
        if split is not None:
            declared.append((lineno, m.group(1).strip(), split[0], split[1]))

    action = "regenerate" if surface_class == CLASS_DERIVED else "migrate"
    for entity in entities:
        eid = entity.entity_id
        retired = entity.category == RETIRED_CATEGORY
        expected = spec.expected_namespace.get(entity.category)
        res = _resolution_for(entity, resolutions)
        marks = _disposition(res, action)
        for lineno, tag, namespace, tail in declared:
            if tail != eid:
                continue
            if not retired and namespace == expected:
                continue
            out.append(_finding(
                entity, SURFACE_TAG_REGISTRY_ROW, surface_class,
                spec.tag_registry, registry=spec.name, line=lineno,
                current=tag,
                target=(
                    marks.target_label(
                        _tag_target(entity, namespace, spec, res),
                        split_prefix=f"{namespace}/",
                    ) if retired else _tag_target(entity, namespace, spec, res)
                ),
                action=action if retired else "renamespace",
                kind=(
                    marks.code_for(CODE_TAG_RETIRED) if retired
                    else CODE_TAG_NAMESPACE
                ),
                severity=marks.severity if retired else "strong",
                autofixable=False,
                reason=(
                    f"the tag registry still declares `{tag}`, which names "
                    + (
                        f"a retired identifier{marks.suffix}" if retired
                        else f"a registered {entity.category} in the "
                             f"`{namespace}` namespace rather than "
                             f"`{expected}`"
                    )
                ),
            ))
    return out


# -----------------------------------------------------------------------------
# Audit
# -----------------------------------------------------------------------------

def _iter_md(root: Path, prefixes: tuple[str, ...]):
    for prefix in prefixes:
        base = root / prefix
        if not base.exists():
            continue
        yield from sorted(base.rglob("*.md"))


def _auditable(
    registry: dict[str, RegistryEntry], spec: RegistrySpec, owner: str | None,
) -> tuple[list[RegistryEntry], list[RegistryEntry]]:
    """`(audited, excluded)` — the entities this scan may report, and the ones
    it must not, each with the reason it was set aside.

    Two exclusions, both from the contract rather than from convenience: a
    `void` retirement freezes its references where they stand, and the owner is
    valid by construction on every base.
    """
    audited: list[RegistryEntry] = []
    excluded: list[RegistryEntry] = []
    for entity in registry.values():
        if entity.category not in spec.audited_categories:
            continue
        # The owner exclusion belongs to the registry that declares the owner,
        # not to the slug. Applied everywhere, it silently un-audits a project
        # whose identifier happens to match a slug transliterated out of prose.
        if spec.excludes_owner and owner is not None and entity.entity_id == owner:
            excluded.append(entity)
            continue
        if entity.kind == "void":
            excluded.append(entity)
            continue
        audited.append(entity)
    return audited, excluded


def _exclusion_reason(
    entity: RegistryEntry, spec: RegistrySpec, owner: str | None,
) -> str:
    if spec.excludes_owner and owner is not None and entity.entity_id == owner:
        return "owner"
    return "void"


def _scan_registry(
    root: Path,
    spec: RegistrySpec,
    entities: list[RegistryEntry],
    files: list[ClassifiedFile],
    resolutions: dict[str, Resolution],
) -> tuple[list[dict], list[dict]]:
    """`(findings, registry_defects)` for one registry.

    Registry-row integrity runs FIRST and its result reaches every later scan
    through `resolutions`: a malformed row has no deterministic target, so no
    surface of that identity may propose one.
    """
    registry_class = _class_of(spec.registry_path)
    row_findings, unreadable = _scan_registry_row_surfaces(
        root, spec, entities, resolutions, registry_class,
    )
    # A row nobody could read belongs to the registry, not to an identity — so
    # it survives a registry with nothing auditable in it, which is exactly the
    # state a registry whose only retirement row is mistyped is in.
    if not entities:
        return row_findings, unreadable

    # Node surfaces next: a node marked for relocation turns every inbound
    # link to it into live work, and the text pass needs to know that before
    # it walks the corpus.
    node_findings = _scan_node_surfaces(root, entities, spec, resolutions)
    repoint: dict[str, str | None] = {}
    for f in node_findings:
        if f["action"] != "relocate" or f["category"] == RETIRED_CATEGORY:
            continue  # a retired identity's links are already residue
        node = canonical_node(root, f["identity"], spec)
        # A canonical node that IS the moving node gives the link nothing to
        # point at — the new home is the owner's decision, not the audit's.
        repoint[f["identity"]] = None if node == f["identity"] else node

    findings: list[dict] = list(row_findings)
    for item in files:
        if item.rule.surface_class not in (CLASS_LIVE, CLASS_DERIVED):
            continue
        findings.extend(_scan_text_surfaces(
            item.path, root, entities, item.rule.surface_class, repoint, spec,
            body_immutable=item.rule.body_immutable, resolutions=resolutions,
        ))
    findings.extend(node_findings)
    findings.extend(_scan_tag_registry_surfaces(
        root, spec, entities, resolutions,
        _class_of(spec.tag_registry) if spec.tag_registry else CLASS_DERIVED,
    ))
    return findings, unreadable


def _class_of(rel: str) -> str:
    """The class the classification table gives this path.

    Asked rather than assumed, so a surface that lives in a file is classed by
    what that file IS. The registry rows are live because the registry is; the
    tag-registry rows are derived because the tag registry is regenerated.
    """
    rule = classify(rel)
    return rule.surface_class if rule else CLASS_UNCLASSIFIED


def _bucket(
    entity: RegistryEntry,
    spec: RegistrySpec,
    resolution: Resolution,
    excluded: str | None,
) -> dict:
    return {
        "id": entity.entity_id,
        "registry": spec.name,
        "registry_path": spec.registry_path,
        "category": entity.category,
        "kind": entity.kind,
        "successor": entity.successor,
        "successors": list(entity.successors),
        "terminal_successor": resolution.terminal,
        "successor_chain": list(resolution.chain),
        "defect": resolution.defect,
        "status": entity.status,
        "excluded": excluded,
        "residue_count": 0,
        "derived_count": 0,
        "by_surface": {},
        "findings": [],
    }


def _identity_scope(
    identity: str | None,
    buckets: list[dict],
    placements: list[tuple[str, str, tuple[str, ...]]],
) -> tuple[str, str | None]:
    """`(scope, reason)` for a filtered run — what the verdict below it means.

    Three answers, and only the first is the one a reader assumes:

    - `audited`      — the identity was scanned and the residue count is real.
    - `set-aside`    — it is auditable in principle but every registry set it
                       aside (a `void` retirement, or the owner row).
    - `out-of-scope` — it is declared and live, so no registry audits it: a
                       live identifier on its own axis is by definition where
                       it belongs, and there is nothing that could be residue.

    An unfiltered run is always `audited` — it scans everything auditable.

    Exit 0 is right in all three cases; the caller's contract is unchanged.
    What must not stay the same is the sentence: «clean» over zero buckets
    reports «nothing was examined» in the words of «nothing was wrong».
    """
    if identity is None:
        return "audited", None
    if any(b["excluded"] is None for b in buckets):
        return "audited", None
    if buckets:
        reasons = sorted({str(b["excluded"]) for b in buckets if b["excluded"]})
        return "set-aside", (
            f"`{identity}` is set aside by every registry that holds it "
            f"({', '.join(reasons)}), so nothing about it was scanned"
        )
    if placements:
        parts = [
            f"{name} registry classifies it as `{category}`, and that scan "
            f"audits {' / '.join(f'`{c}`' for c in audited) or 'nothing'}"
            for name, category, audited in placements
        ]
        return "out-of-scope", (
            f"`{identity}` is live: the {'; the '.join(parts)}. A live "
            f"identifier on its own axis is where it belongs, so there is "
            f"nothing here that could be residue"
        )
    return "out-of-scope", (
        f"no registry scan covers `{identity}`, so nothing about it was checked"
    )


def audit(
    root: Path,
    registries: dict[str, dict[str, RegistryEntry]] | None = None,
    specs: tuple[RegistrySpec, ...] = REGISTRY_SPECS,
    identity: str | None = None,
) -> dict:
    """Resolve every surface against every registry; report what still names a
    retired or mis-classified identifier.

    One procedure, N registries: each spec declares its own roles and the scan
    below is the same code for all of them. `registries` maps a spec name to an
    already-parsed registry, for a caller that has one; anything absent is
    parsed here.

    `identity` restricts the whole report — buckets, counts and verdict — to one
    identifier, in every registry that holds it. The completion gate is
    per-identity while the audit is global, and a caller handed another
    identity's work list will act on it: the filter is what keeps a change from
    being reverted because something unrelated is dirty.
    """
    owner = owner_identity(root)
    files, unclassified = walk_base(root)
    per_identity: dict[tuple[str, str], dict] = {}
    findings: list[dict] = []
    registry_defects: list[dict] = []
    registry_summaries: list[dict] = []
    known_identity = False
    # Where a filtered identity was found, and what that registry can report on
    # at all. A live identity is declared but outside `audited_categories`, so
    # it produces no bucket — and a verdict computed over zero buckets must not
    # be reported in the same words as one computed over a clean scan.
    identity_placements: list[tuple[str, str, tuple[str, ...]]] = []

    parsed_by_spec: dict[str, dict[str, RegistryEntry]] = {}
    for spec in specs:
        parsed = (registries or {}).get(spec.name)
        if parsed is None:
            parsed = spec.parse(root)
        parsed_by_spec[spec.name] = parsed
        if identity is not None and identity in parsed:
            known_identity = True
            identity_placements.append(
                (spec.name, parsed[identity].category, spec.audited_categories),
            )
        entities, excluded = _auditable(parsed, spec, owner)
        # Integrity is resolved for every identity, including the ones set
        # aside: a `void` row that declares a successor is a defect of the row
        # even though the identity itself is frozen.
        resolutions = {
            e.entity_id: resolve_identity(e, parsed)
            for e in list(entities) + list(excluded)
        }
        if identity is not None:
            entities = [e for e in entities if e.entity_id == identity]
            excluded = [e for e in excluded if e.entity_id == identity]
        for entity in sorted(entities, key=lambda e: e.entity_id):
            per_identity[(spec.name, entity.entity_id)] = _bucket(
                entity, spec, resolutions[entity.entity_id], None,
            )
        for entity in sorted(excluded, key=lambda e: e.entity_id):
            per_identity[(spec.name, entity.entity_id)] = _bucket(
                entity, spec, resolutions[entity.entity_id],
                _exclusion_reason(entity, spec, owner),
            )
        # A `void` row that declares a successor is reported against the row,
        # not against the references it wrongly claims to redirect.
        malformed_excluded = [
            e for e in excluded if resolutions[e.entity_id].defect is not None
        ]
        spec_findings, spec_unreadable = _scan_registry(
            root, spec, entities, files, resolutions,
        )
        if malformed_excluded:
            extra, _ = _scan_registry_row_surfaces(
                root, spec, malformed_excluded, resolutions,
                _class_of(spec.registry_path),
            )
            spec_findings.extend(extra)
        findings.extend(spec_findings)
        registry_defects.extend(spec_unreadable)
        registry_summaries.append({
            "registry": spec.name,
            "registry_path": spec.registry_path,
            "surfaces": list(spec.surfaces),
            "identity_count": len(entities),
            "excluded_count": len(excluded),
            "residue_count": sum(
                1 for f in spec_findings if f["surface_class"] == CLASS_LIVE
            ),
        })

    for f in findings:
        bucket = per_identity[(f["registry"], f["identity"])]
        bucket["findings"].append(f)
        if f["surface_class"] == CLASS_LIVE:
            bucket["residue_count"] += 1
            bucket["by_surface"][f["surface"]] = (
                bucket["by_surface"].get(f["surface"], 0) + 1
            )
        else:
            bucket["derived_count"] += 1

    # A per-identity run answers for that identity only. Coverage gaps and
    # unreadable registry rows belong to the base as a whole, and letting them
    # fail one identity's gate is exactly the confusion the filter exists to
    # remove.
    # An orphan is a fact about the base: no identity owns it, so it must never
    # fail the proof of one retirement — the same reason coverage gaps and
    # unreadable rows are dropped here.
    orphans_all = scan_orphan_tags(root, files, parsed_by_spec, specs)
    baseline = _read_orphan_baseline(root)
    orphans_baselined = [o for o in orphans_all if (o["tag"], o["path"]) in baseline]
    orphans = [o for o in orphans_all if (o["tag"], o["path"]) not in baseline]
    # A row whose orphan is gone is not harmless: it is a silencer left armed
    # over a spot that may drift back, and it makes the list look longer than
    # the work remaining. Reported, never residue — the night must not stop for
    # a stale line in a state file.
    live_pairs = {(o["tag"], o["path"]) for o in orphans_all}
    orphans_stale = sorted(f"{tag} | {where}" for tag, where in baseline
                           if (tag, where) not in live_pairs)

    if identity is not None:
        unclassified, registry_defects = [], []
        orphans, orphans_baselined, orphans_stale = [], [], []

    ordered = [per_identity[k] for k in sorted(per_identity)]
    surface_residue = sum(b["residue_count"] for b in ordered)
    derived_count = sum(b["derived_count"] for b in ordered)
    residue_count = (
        surface_residue + len(unclassified) + len(registry_defects) + len(orphans)
    )
    coverage: dict[str, int] = {
        CLASS_LIVE: 0, CLASS_DERIVED: 0, CLASS_IMMUTABLE: 0,
        CLASS_UNCLASSIFIED: len(unclassified),
    }
    for item in files:
        coverage[item.rule.surface_class] = (
            coverage.get(item.rule.surface_class, 0) + 1
        )
    scope, scope_reason = _identity_scope(
        identity, ordered, identity_placements,
    )
    return {
        "owner": owner,
        "identity_filter": identity,
        "identity_known": known_identity if identity is not None else True,
        "identity_scope": scope,
        "identity_scope_reason": scope_reason,
        "registries": registry_summaries,
        "identity_count": sum(
            1 for b in ordered if b["excluded"] is None
        ),
        "residue_count": residue_count,
        "surface_residue_count": surface_residue,
        "derived_count": derived_count,
        "unclassified_count": len(unclassified),
        "unclassified": unclassified,
        "registry_defect_count": len(registry_defects),
        "registry_defects": registry_defects,
        "orphan_count": len(orphans),
        "orphans": orphans,
        "orphans_baselined": orphans_baselined,
        "orphans_stale": orphans_stale,
        "coverage": coverage,
        "clean": residue_count == 0,
        "surfaces": list(SURFACES),
        "identities": ordered,
    }


# -----------------------------------------------------------------------------
# Drift event stream (the nightly scan's contract)
# -----------------------------------------------------------------------------

def _has_boundary_marker(fm: dict, body: str) -> bool:
    if fm.get("boundary") is True:
        return True
    body_lower = body.lower()
    return any(m in body_lower for m in BOUNDARY_MARKERS)


def _emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")


def _scan_note(path: Path, root: Path, registry: dict[str, set[str]]) -> None:
    fm_body = read_frontmatter(path)
    if fm_body is None:
        return
    fm, body = fm_body

    projects = fm.get("projects") or []
    if not isinstance(projects, list):
        # invalid type — out of scope here (handled by the schema scan)
        return
    # filter empty/None entries
    projects = [str(p).strip() for p in projects if p]

    note_id = fm.get("id") or path.stem
    rel_path = path.relative_to(root).as_posix()
    base_event = {
        "scan": "A.8",
        "note_id": note_id,
        "path": rel_path,
        "projects": projects,
    }

    n = len(projects)

    # Check 1: length
    if n == 2 and not _has_boundary_marker(fm, body):
        _emit({
            **base_event,
            "kind": "projects-array-2-without-boundary-marker",
            "severity": "weak",
            "reason": (
                "projects: has 2 entries but body lacks boundary annotation "
                "(boundary case / cross-project / joint review) and no "
                "`boundary: true` frontmatter field. Either pick the primary "
                "or annotate the boundary case explicitly."
            ),
            "to_resolve": (
                "Pick primary topic (drop one); OR add 'boundary case' "
                "annotation in body OR `boundary: true` in frontmatter."
            ),
        })
    elif n >= 3:
        _emit({
            **base_event,
            "kind": "projects-array-overcount",
            "severity": "weak",
            "reason": (
                f"projects: has {n} entries — primary-topic-only semantic "
                "allows max 2 (boundary). 3+ indicates umbrella/loose tagging "
                "drift (PROCESSING_PRINCIPLES §9)."
            ),
            "to_resolve": (
                "Pick the single primary; demote others to "
                "`tags: [project/{slug}]` (umbrella) or `concepts:` (topical)."
            ),
        })

    # PROJECTS.md is the source of truth; if it is absent or empty we cannot
    # resolve identity at all. Skip resolution rather than flag every entry —
    # a friend mid-setup legitimately has notes before a populated registry.
    # (Length check above is registry-independent and still applies.)
    if not any(registry.values()):
        return

    # Check 2 + 3: per-entry resolution against the registry (single SoT).
    # PROJECTS.md is authoritative for both existence and classification of
    # every projects: entry. A hub never vouches for a project's existence —
    # it is consulted only to refine the diagnostic for an ID that is absent
    # from the registry entirely (orphan hub vs non-project hub vs typo).
    for project_id in projects:
        if project_id in registry["project"]:
            continue  # registered project — valid
        if project_id in registry["trajectory"]:
            _emit({
                **base_event,
                "kind": "projects-array-non-project",
                "severity": "weak",
                "project_id": project_id,
                "reason": (
                    f"projects entry `{project_id}` is a registered "
                    f"trajectory, not a project. The projects: axis is "
                    f"reserved for actual projects (Identity Contract, SYSTEM_CONFIG)."
                ),
                "to_resolve": (
                    f"Drop `{project_id}` from projects: ; use "
                    f"`tags: [trajectory/{project_id}]` instead."
                ),
            })
            continue
        if project_id in registry["consolidated"]:
            _emit({
                **base_event,
                "kind": "projects-array-consolidated",
                "severity": "weak",
                "project_id": project_id,
                "reason": (
                    f"projects entry `{project_id}` is a consolidated / "
                    f"superseded ID in PROJECTS.md. Records should point at "
                    f"its successor, not the retired ID."
                ),
                "to_resolve": (
                    f"Replace `{project_id}` with its successor project ID "
                    f"(see the Consolidated / superseded table in PROJECTS.md)."
                ),
            })
            continue
        # Absent from the registry — consult the hub only to refine.
        kind, hub_exists = _hub_kind(root, project_id)
        if hub_exists and kind == "project":
            _emit({
                **base_event,
                "kind": "projects-array-orphan-hub",
                "severity": "weak",
                "project_id": project_id,
                "hub_kind": kind,
                "reason": (
                    f"projects entry `{project_id}` has a hub_kind=project "
                    f"hub but no row in PROJECTS.md. PROJECTS.md is the source "
                    f"of truth for project existence; the orphan hub is "
                    f"registry drift."
                ),
                "to_resolve": (
                    f"Register `{project_id}` in PROJECTS.md, or — if it is "
                    f"not a real project — remove hub-{project_id}.md and drop "
                    f"the entry."
                ),
            })
        elif hub_exists:
            _emit({
                **base_event,
                "kind": "projects-array-non-project-hub",
                "severity": "weak",
                "project_id": project_id,
                "hub_kind": kind,
                "reason": (
                    f"projects entry `{project_id}` is unregistered and "
                    f"resolves to a hub_kind={kind} hub. Only registered "
                    f"projects are eligible for the projects: axis "
                    f"(Identity Contract, SYSTEM_CONFIG)."
                ),
                "to_resolve": (
                    f"Drop `{project_id}` from projects: ; if the signal "
                    f"matters, add `tags: [{kind}/{project_id}]`"
                    f"{' or `domains:`' if kind == 'domain' else ''} instead."
                ),
            })
        else:
            _emit({
                **base_event,
                "kind": "projects-array-unknown-id",
                "severity": "weak",
                "project_id": project_id,
                "reason": (
                    f"projects entry `{project_id}` resolves to neither a row "
                    f"in PROJECTS.md nor a hub file at "
                    f"5_meta/mocs/hub-{project_id}.md."
                ),
                "to_resolve": (
                    f"Verify project ID; fix the slug, register the project "
                    f"in PROJECTS.md, or drop the entry."
                ),
            })


def _iter_notes(root: Path):
    yield from _iter_md(root, SCOPE_INCLUDE)


# The category a hub declares in `hub_kind:` and the category the registry
# declares are the same statement made twice. `project` is the default when the
# field is absent, per the contract.
HUB_KIND_FOR_CATEGORY: dict[str, str] = {
    "project": "project",
    "trajectory": "trajectory",
}


def _scan_hub_kinds(root: Path, registry: dict[str, RegistryEntry]) -> None:
    """Emit a drift event wherever a hub's `hub_kind` contradicts the registry.

    The two sides must agree, and nothing checked it. This scan owns the check
    because it is the one that already holds the registry — and the pair is
    never silently repaired, because changing either side moves every member
    note between axes.

    A hub whose identifier is absent from every registry is out of scope: it is
    an identity in its own right, not a surface of one.
    """
    hub_dir = root.joinpath(*HUB_DIR)
    if not hub_dir.is_dir():
        return
    for path in sorted(hub_dir.glob("*.md")):
        stem = path.stem
        if not stem.startswith(HUB_PREFIX):
            continue
        entity_id = stem[len(HUB_PREFIX):]
        entry = registry.get(entity_id)
        if entry is None or entry.category == RETIRED_CATEGORY:
            # A retired identity's hub is residue, which the identity report
            # owns; a mismatched kind on top of it is not the useful sentence.
            continue
        expected = HUB_KIND_FOR_CATEGORY.get(entry.category)
        if expected is None:
            continue
        declared, exists = _hub_kind(root, entity_id)
        if not exists or declared == expected:
            continue
        _emit({
            "scan": "A.8",
            "kind": CODE_HUB_KIND_MISMATCH,
            "severity": "strong",
            "path": path.relative_to(root).as_posix(),
            "identity": entity_id,
            "hub_kind": declared,
            "registry_category": entry.category,
            "reason": (
                f"`{path.name}` declares `hub_kind: {declared}` while "
                f"PROJECTS.md classifies `{entity_id}` as a "
                f"{entry.category}. The hub-side declaration and the registry "
                f"are the same statement made twice and must agree."
            ),
            "to_resolve": (
                f"Decide which side is right and change that one. Never fix "
                f"both silently: the value decides which axis every member "
                f"note carries this identity on (`projects:` for a project, "
                f"`tags: [trajectory/{entity_id}]` for a trajectory), so a "
                f"change here is an identity change of the reclassify kind."
            ),
        })


def _print_report(result: dict) -> None:
    scope = (
        f"identity: {result['identity_filter']} | "
        if result.get("identity_filter") else ""
    )
    # `clean: True` over zero buckets and `clean: True` over a scanned identity
    # are different facts and must not print the same word. The counts still
    # follow, so a reader who wants them has them either way.
    verdict = (
        f"clean: {result['clean']}"
        if result.get("identity_scope", "audited") == "audited"
        else f"NOT AUDITED ({result['identity_scope']})"
    )
    print(
        f"{scope}identities: {result['identity_count']} | "
        f"residue: {result['residue_count']} "
        f"(surfaces {result['surface_residue_count']}, "
        f"unclassified {result['unclassified_count']}, "
        f"registry defects {result['registry_defect_count']}, "
        f"orphan tags {result['orphan_count']}) | "
        f"derived: {result['derived_count']} | {verdict} | "
        f"owner: {result['owner'] or '—'}"
    )
    if result.get("identity_scope_reason"):
        print(f"  why: {result['identity_scope_reason']}")
        print(
            "  exit 0 here means «no check applies», not «no residue found» — "
            "nothing about this identifier was examined."
        )
    if result.get("orphans_stale"):
        print(
            f"  orphan baseline: {len(result['orphans_stale'])} stale row(s) — "
            "the orphan is gone, the silencer is still armed. Remove them:"
        )
        for row in result["orphans_stale"]:
            print(f"    {row}")
    cov = result["coverage"]
    print(
        f"  coverage: {cov[CLASS_LIVE]} live, {cov[CLASS_DERIVED]} derived, "
        f"{cov[CLASS_IMMUTABLE]} immutable, "
        f"{cov[CLASS_UNCLASSIFIED]} unclassified"
    )
    regions: dict[str, int] = {}
    for item in result["unclassified"]:
        regions[item["region"]] = regions.get(item["region"], 0) + 1
    for region, count in sorted(regions.items()):
        print(f"    unclassified region `{region}`: {count} file(s)")
    for row in result["registry_defects"]:
        print(
            f"    {row['kind']} {row['path']}:{row['line']} — "
            f"`{row['current']}` in the {row['registry']} registry"
        )
    for reg in result["registries"]:
        print(
            f"  {reg['registry_path']}: {reg['identity_count']} audited, "
            f"{reg['residue_count']} live residue, "
            f"{reg['excluded_count']} excluded"
        )
    for ident in result["identities"]:
        if ident["excluded"]:
            # Printed even with no findings: an identity nobody checks is worth
            # exactly as much as a check nobody runs, unless you can see it was
            # set aside and why.
            print(
                f"  {ident['id']} ({ident['category']}"
                f"{'/' + ident['kind'] if ident['kind'] else ''}): "
                f"excluded — {ident['excluded']}"
            )
            continue
        if not ident["findings"]:
            continue
        surfaces = ", ".join(
            f"{k} {v}" for k, v in sorted(ident["by_surface"].items())
        ) or "—"
        successor = ident["successor"] or "—"
        kind = f"/{ident['kind']}" if ident["kind"] else ""
        print(
            f"  {ident['id']} ({ident['category']}{kind} → {successor}): "
            f"{ident['residue_count']} live [{surfaces}], "
            f"{ident['derived_count']} derived"
        )


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=None,
        help="Minder Memory base path (defaults to repo_root(), the zettelkasten base).",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="print the identity report instead of the drift event stream",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="machine-readable report (with --report)",
    )
    parser.add_argument(
        "--fail-on-residue", action="store_true",
        help="exit 2 when residue exists",
    )
    parser.add_argument(
        "--identity", default=None, metavar="ENTITY-ID",
        help=(
            "restrict the report, the counts and the exit code to one "
            "identifier, in every registry that holds it. Exit 1 when no "
            "registry knows it. The report names its scope — audited / "
            "set-aside / out-of-scope — so exit 0 is never read as a check "
            "that happened when none applies."
        ),
    )
    args = parser.parse_args(argv)

    # `repo_root()` already resolves to the zettelkasten base (or `MINDER_MEMORY_BASE`).
    root = args.root or repo_root()
    if not root.exists():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 1

    registry = parse_project_registry(root)

    result = None
    if args.report or args.fail_on_residue or args.identity:
        result = audit(
            root, {PROJECT_SPEC.name: registry}, identity=args.identity,
        )

    # An identifier no registry declares is not clean — it is unknown, and the
    # ordinary causes are a typo and a row that never landed. Reading it as
    # clean would close a change against nothing.
    if result is not None and not result["identity_known"]:
        print(
            f"ERROR: no registry declares `{args.identity}` — nothing to "
            f"prove about it. Check the identifier, or check that its "
            f"retirement row actually landed.",
            file=sys.stderr,
        )
        return 1

    if args.report or args.identity:
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            _print_report(result)
    else:
        by_category = registry_ids_by_category(registry)
        for cat in REGISTRY_CATEGORIES:
            by_category.setdefault(cat, set())
        for path in _iter_notes(root):
            _scan_note(path, root, by_category)
        _scan_hub_kinds(root, registry)

    if args.fail_on_residue and result and result["residue_count"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
