---
last_updated: 2026-05-02
mirror_of: minder/domain/graph/ConceptType.java
---

# Concept Types Registry

Frozen mirror of Minder's `ConceptType` enum (18 values). Names the
**kind** of a concept node — what the node represents in the
knowledge graph — independent of its life-area context (`domains:`)
or audience scope (`audience_tags:`).

Concept type is the third closed axis on a concept entry; the other
two are documented in `CONCEPT_NAMING.md` (open name graph) and
`DOMAINS.md` (closed life-area axis).

---

## Why a frozen mirror, not free-form vocabulary

The set is **owned downstream**: Minder's Java enum is the source of
truth. Minder Memory mirrors it for two reasons:

1. **Subagent disambiguation.** When the concept-matcher subagent
   coins a new concept (`/minder:mem:process` Step 3.4.5, in either inbox
   mode or `--reprocess-corpus` mode), it must assign a type so downstream
   consumers route the node correctly. The 18-value vocabulary plus
   per-value descriptions gives the subagent enough context to
   disambiguate cases the prompt alone cannot resolve (`PROJECT` vs
   `IDEA`, `GOAL` vs `VALUE`, `THEME` vs `IDEA`).
2. **Drift detection.** `mirror_of:` above states the path SUFFIX the
   parity test matches on — not an absolute path, which would resolve on
   exactly one machine. Resolution itself is owned by that test
   (`test_common.py::TestConceptTypeMirror`): it walks up from the checkout
   looking for a descendant ending in that suffix, honours
   `MINDER_MEMORY_CONCEPT_TYPE_JAVA` when the file lives elsewhere, and asserts both
   sets match. It is a
   **local** guard, not a CI one: the Java source is only reachable
   where the Minder repo is checked out alongside this one, and the
   test skips where it is not — so shared CI, and every friend's
   clone, verify the shape-invariants (18 / 16 / descriptions cover
   all) but never the mirror against Java itself.

Owner does NOT edit this file; sync is upstream-only via manual
re-mirror when Minder's enum changes (no auto-sync — owner makes the
call to land the change).

---

## Mirror vs emit gate

The mirror is **18 values**. Minder Memory's emission gate is **16** —
`person` and `project` are excluded from the concept channel because
they are first-class entities with dedicated registries
(`PEOPLE.md`, `PROJECTS.md`). See `_system/docs/batch-format.md`
§"Concept scope" + `_system/scripts/_common.py::EMITTED_CONCEPT_TYPES`.

Two distinct sets, two distinct roles:

| Set | Source | Cardinality | Role |
|---|---|---|---|
| `CONCEPT_TYPES_ALL` | this file | 18 | Mirror against Java; drift detection; documentation |
| `EMITTED_CONCEPT_TYPES` | `_common.py` | 16 | Validation gate at emit boundary; subagent prompt vocabulary |

If a subagent ever returns `type=person` or `type=project`, the gate
drops the entry as `concept-type-drop-autofix`. People and projects
flow through their own first-class channels, never the concept channel.

---

## The canonical eighteen

Values are kebab-case in markdown / lowercase in code. Java's enum
constants (`PERSON`, `ORGANIZATION`, …) map to lowercase codes.
Groups are presentational; the mirror is flat at the validation set.

### Entities (7) — things that exist in the world

| Code | Java enum | Description | Notes |
|---|---|---|---|
| `person` | `PERSON` | People and contacts | **NOT emitted by Minder Memory concept channel** — people are first-class entities (PEOPLE.md). Mirror entry exists for round-trip parity with Java only. |
| `organization` | `ORGANIZATION` | Companies, teams, communities | A company, team, project group, community. Distinct from `project` (initiatives) and `person` (individuals). |
| `project` | `PROJECT` | Projects and initiatives | **NOT emitted by Minder Memory concept channel** — projects are first-class entities (PROJECTS.md). Mirror entry exists for round-trip parity with Java only. |
| `idea` | `IDEA` | Ideas and concepts | A specific idea or proposal. Distinct from `theme` (broad topic) by being a concrete, articulable proposition. |
| `tool` | `TOOL` | Technologies and instruments | Software, frameworks, hardware, methodologies-as-tools. Distinct from `skill` by being external; `skill` is a competency. |
| `skill` | `SKILL` | Skills and competencies | A capability someone has or is acquiring. Distinct from `tool` (the thing) and `learning` (the act of acquiring). |
| `location` | `LOCATION` | Places and locations | Physical or virtual places. Cities, offices, online communities-as-places. |

### Events & States (3) — temporal or episodic

| Code | Java enum | Description | Notes |
|---|---|---|---|
| `event` | `EVENT` | Events and meetings | A specific occurrence. Conferences, meetings, releases, incidents. |
| `emotion` | `EMOTION` | Emotional states | Named affective states the owner experiences or observes. |
| `theme` | `THEME` | Topics and themes | A broad recurring topic. Distinct from `idea` (a specific proposition) by breadth. |

### Behavioral (6) — drivers, constraints, choices

| Code | Java enum | Description | Notes |
|---|---|---|---|
| `goal` | `GOAL` | User goals and objectives | What the owner is trying to achieve. Distinct from `value` (what they care about) by being a target outcome. |
| `value` | `VALUE` | Personal values and principles | What the owner cares about. Distinct from `goal` (target) by being orienting/standing rather than achieved. |
| `preference` | `PREFERENCE` | User preferences | Stated or revealed leaning between options. Lighter than `value`; can change without identity shift. |
| `constraint` | `CONSTRAINT` | User constraints and rules | Hard or soft boundary on action. Time, money, ethics, capacity. |
| `algorithm` | `ALGORITHM` | Generalized decision patterns and reasoning sequences | A reusable how-to for a class of decisions. Distinct from `decision` (one specific choice). |
| `decision` | `DECISION` | Explicit choices with reasoning and alternatives | One specific choice between alternatives, with rationale. Distinct from `algorithm` (the pattern). |

### Meta (2) — fallback / uncategorised

| Code | Java enum | Description | Notes |
|---|---|---|---|
| `fact` | `FACT` | Individual facts and notes | Single-fact concepts that don't fit the other 16. Last-resort before `other`. |
| `other` | `OTHER` | Other concepts | Genuine catch-all. Subagent uses `other` only when no other type applies AND `fact` is also wrong. |

---

## On violation — autonomous resolution

The concept-type layer is autonomous on the deterministic substrate.
No CLARIFICATIONs raised on type validation; unknown values are
silently dropped at emit/lint boundary.

| Condition | Engine action | Fix-id |
|---|---|---|
| Code in `EMITTED_CONCEPT_TYPES` (16) | Pass-through. | — |
| Code is `person` or `project` | **Silent drop** — entry is rerouted as a structural concern (see Mirror vs emit gate above). | `concept-type-drop-autofix` (reason: `first-class-entity-not-concept`) |
| Code well-formed but not in mirror | **Silent drop**. | `concept-type-drop-autofix` (reason: `not-in-mirror`) |
| Uppercase / mixed case | **Silent autofix** to lowercase via `normalize_concept_type`; then revalidate. | `concept-type-normalise-autofix` |
| Empty / null / non-string | **Silent drop**. | `concept-type-drop-autofix` (reason: `empty-or-malformed`) |

**Why fail-closed via drop.** A misclassified type pollutes
downstream consumer routing. The safest failure is "no type"
(downstream maps to `OTHER` per Java's `fromCode` fallback), never
"guessed". The engine never coins new types — owner mirrors Java
upstream when the enum evolves.

---

## Heuristics for novel cases (subagent guidance)

When the concept-matcher subagent assigns a type to a newly coined
concept, it follows these heuristics in order:

1. **Is it a known-named entity (org/place/tool)?** → `organization`,
   `location`, `tool`. Stop.
2. **Is it a competency someone has?** → `skill`.
3. **Is it a specific dated occurrence?** → `event`.
4. **Is it an affective state?** → `emotion`.
5. **Is it a broad recurring topic?** → `theme`. (If concrete
   proposition, prefer `idea`.)
6. **Is it a concrete proposition or articulable plan?** → `idea`.
7. **Is it an aspiration or target?** → `goal`.
8. **Is it an orienting principle or "what I care about"?** → `value`.
9. **Is it a stated leaning between options?** → `preference`.
10. **Is it a boundary on action?** → `constraint`.
11. **Is it a reusable how-to / decision pattern?** → `algorithm`.
12. **Is it a specific choice with alternatives + reasoning?** → `decision`.
13. **Is it a single fact?** → `fact`.
14. **None of the above?** → `other`.

**NEVER assign `person` or `project`.** Those flow as first-class
entities through PEOPLE.md / PROJECTS.md; subagent's prompt
explicitly excludes them from the assignable set.

---

## Relationship to Minder downstream

Minder's `ConceptType.fromCode(code)` accepts any of the 18 codes
verbatim and falls back to `OTHER` on unknown. Minder Memory's emission
guarantees codes are always in the 16 emit set, so downstream never
hits the `OTHER` fallback for an entry the engine emitted — `OTHER` rows in
Minder come from external sources or owner manual edits.

When Minder's enum evolves:

1. Owner re-mirrors this file from the updated Java source.
2. Owner updates `_common.py::CONCEPT_TYPES_ALL` (18-set) and, if
   appropriate, `EMITTED_CONCEPT_TYPES` (16-set).
3. `test_common.py::TestConceptTypeMirror` re-runs and confirms
   parity — any drift fails the test.
4. VERSION bumps with a release note describing the new value(s).

No auto-sync. Manual upstream-pulls only — owner makes the call.

---

Sibling axes: `domains:` → `DOMAINS.md`, `audience_tags:` →
`AUDIENCES.md`, concept names → `CONCEPT_NAMING.md`, `tags:` →
`TAGS.md`.
