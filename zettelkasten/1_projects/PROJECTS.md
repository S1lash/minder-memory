# Project Registry

**Last Updated:** REPLACE_WITH_DATE

All projects in the system. Add a row when a new project is created.

**Schema:**
- `Scope` — `work` (employer / clients), `personal` (life, health, learning),
  `side` (side business, freelance, public projects), `mixed` (truly cross-context).
  Owner-tagged; `/minder:mem:bootstrap` seeds with a hint from raw-scan source bias,
  owner edits. Empty `Scope` defaults to `work` for legacy rows.
- `Status` — `active`, `paused`, `candidate` (added by bootstrap, awaiting owner review),
  `completed` (moved to `## Completed Projects`), `archived` (dropped before completion;
  moved to `## Archived Projects` with required `Reason` per Archive Contract Form B
  in `_system/docs/SYSTEM_CONFIG.md`).

---

## Active Projects

| ID | Name | Description | Folder | Scope | Status |
|----|------|-------------|--------|-------|--------|
| _(empty)_ | | | | | |

---

## Trajectories

Long-term arcs and multi-year themes — an identity whose hub declares `hub_kind: trajectory`.

**Trajectories are NOT eligible for the `projects:` membership axis.** A note that belongs to a trajectory carries `tags: [trajectory/{id}]`; only `hub_kind: project` identities are named in `projects:` (Identity Contract → `_system/docs/SYSTEM_CONFIG.md`). Moving an identity between `project` and `trajectory` is an identity change of the `reclassify` kind, not a silent edit — it moves every member note between axes.

**Schema:**
- `ID` — the identity's identifier; the hub is `hub-{id}` and the tag is `trajectory/{id}`.
- `Hub` — wikilink to the canonical hub node.
- `Status` — `active`, `paused`, `completed`. A trajectory that stops being a valid identifier moves to `## Retired Identifiers` below.

| ID | Name | Hub | Status |
|----|------|-----|--------|
| _(empty)_ | | | |

---

## Retired Identifiers

Identifiers from this registry — projects and trajectories alike — that are no longer valid. Per Identity Contract (`_system/docs/SYSTEM_CONFIG.md`), a retirement is atomic and leaves zero residue: every live surface naming the old identifier migrates in the same unit of work. Per Archive Contract Form B, every row carries a `Reason`.

**Schema:**
- `Old ID` — the retired identifier, exactly as it was written. Matching is exact identifier equality, never substring — a longer identifier containing this one is a different identity.
- `Kind` — `merge` (became part of another identity), `rename` (same identity, different identifier), `void` (the identity never existed). A `reclassify` never appears here: the identity stays valid and simply lives in a different section above, and that section is the statement — see Identity Contract.
- `Successor` — wikilink to the surviving node. **Required** for `merge` and `rename`; **empty** for `void`.
- `Date` — ISO date the retirement was decided.
- `Reason` — free-form one sentence.

| Old ID | Kind | Successor | Date | Reason |
|--------|------|-----------|------|--------|
| _(empty)_ | | | | |

---

## Completed Projects

| ID | Name | Description | Folder | Scope | Completed |
|----|------|-------------|--------|-------|-----------|
| _(empty)_ | | | | | |

---

## Archived Projects

Projects with `Status: archived` — dropped before completion. Per Archive Contract Form B (`_system/docs/SYSTEM_CONFIG.md`), every row carries a `Reason` cell — free-form one-sentence rationale. Forward-only: projects archived before contract adoption are not backfilled. (Successfully completed projects belong in `## Completed Projects` and do not require Reason.)

| ID | Name | Description | Folder | Scope | Status | Archived | Reason |
|----|------|-------------|--------|-------|--------|----------|--------|
| _(empty)_ | | | | | | | |

---

## Project Template

To create a new project:

1. Add a row to `## Active Projects` — that row IS the registration of the identifier.
2. Create the folder `1_projects/{project-id}/`. The project's material lives there as
   dated notes (`YYYYMMDD-{type}-{slug}.md`), shaped by
   `5_meta/templates/note-template.md`. There is no card file standing for the project
   itself.
3. Create the hub `5_meta/mocs/hub-{project-id}.md` from
   `5_meta/templates/hub-template.md` with `hub_kind: project` — that hub is the
   project's canonical node, and what links point at.

A note belongs to a project through the `projects: [{project-id}]` field in its own
frontmatter. That is the membership axis: primary topic only, cardinality 1–2, and
eligibility to occupy it is decided by the Identity Contract
(`_system/docs/SYSTEM_CONFIG.md`).

The `project/{project-id}` tag is **a second signal, not a derivative of that field.**
The note's producer writes it, and it marks any relevance to the project — including
the peripheral relevance the membership axis does not carry by definition
(`5_meta/PROCESSING_PRINCIPLES.md` → «Project Tagging — Primary-Topic Only»). Nothing
derives it from `projects:`, and retiring an identifier migrates the two surfaces
separately. `_system/registries/TAGS.md` is a census of tag *uses*, not their source:
it is rendered by script and never written by hand.
