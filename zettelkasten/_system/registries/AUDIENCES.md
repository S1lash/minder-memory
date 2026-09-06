---
last_updated: 2026-05-02
---

# Audiences Registry

Whitelist of valid `audience_tags` values — the "who is allowed to
see this" slot on every entity in the knowledge base.

---

## Why three privacy axes, not one

Privacy is **not a single ordinal scalar**. The naive enum
(`private | shareable | public`) silently mixes three independent
questions and collapses on real cases — "public within work, hidden
outside" is inexpressible as a single rank. So content carries three
orthogonal fields, each answering one question:

| Field | Question | Type | Default |
|---|---|---|---|
| `origin` | Where was this captured? (provenance) | enum | `personal` |
| `audience_tags` | Who is allowed to see it? (access) | `text[]` | `[]` (owner only) |
| `is_sensitive` | Does sharing require extra friction? (risk) | bool | `false` |

This file governs the second one. The first lives in the engine
doctrine; the third is a plain boolean.

A note can be `origin=work, audience_tags=[friends], is_sensitive=false`
("captured during work hours, but it's a thought meant to share
with friends, no special handling"). Each axis varies independently;
no axis subsumes another.

---

## What an audience tag means

An audience tag names **a circle of people who are allowed to see
the entity** if and when sharing happens. It does not yet *cause*
sharing — sharing logic is a downstream concern. The tag only
declares intent: "this content is appropriate for that audience."

Treating the tag as intent (not enforcement) is what makes
classifying easy at write-time: the question is "who is this
information appropriate for?", not "who will actually receive it?".

### The canonical five

Every knowledge base ships with the same five labels. They cover the
default social topology of the owner's life. Their meanings are
deliberately broad-but-distinct — narrowing happens through
extensions, not by redefinition.

| Tag | Meaning | What distinguishes it |
|---|---|---|
| `family` | Owner's immediate family circle | Kinship-bound; the tightest social ring; spouse, parents, siblings, children. Default audience for intimate life details. |
| `friends` | Owner's friend circle | Voluntary chosen relationships, non-transactional. Distinct from `family` (kinship) and from `professional-network` (career-instrumental). |
| `work` | Current work team / colleagues | Bounded by the owner's current employment / project context. NOT past colleagues, NOT the broader industry. |
| `professional-network` | Broader career-relevant relationships | Past colleagues, mentors, conference contacts, "LinkedIn audience". Public-professional voice — what you'd say in a public industry forum. |
| `world` | Public broadcast | Anyone, including strangers. Twitter posts, public blog. |

These five are reserved keywords. Extensions cannot **be equal to**
a canonical word (case-folded) and cannot differ from one only in
casing or punctuation (`Family`, `family_`, `family.` all conflict
with `family`). Extensions **may** use a canonical word as part of
a clearly distinct longer label — `work-platform` is fine alongside
`work`, `family-extended` is fine alongside `family`. The test:
would a reader instantly see them as different audiences? If yes,
allowed. If a reader would think «that's just `family` spelt
differently», the engine treats it as a reserved-keyword conflict and
silently drops the extension at load time (the canonical wins).

### Why flat (no hierarchy)

`world ⊃ friends ⊃ family` looks plausible but is wrong in practice.
Real sharing patterns are not inclusive: a public Twitter post may
not be something you'd send to your close friends (different voice,
different framing); a thought intimate enough for family is not
"public-but-also-private". Treating tags as flat forces deliberate
choice — `[work, friends]` says "I want both circles, separately"
instead of leaving the choice to a hierarchy that doesn't model how
people actually share.

### Why empty `[]` means owner-only

Absence of an audience decision is **the most restrictive** state.
Permission is opt-in, never opt-out. If classification ever drifts
or extraction misses a label, the safe failure is "stays private",
not "leaks to a default circle". Backfill, syncs, and ambiguous
captures all default to `[]`; widening is always an explicit owner
action.

### Why `is_sensitive` is orthogonal

`is_sensitive` doesn't narrow the audience — it adds friction at
share time. An NDA-locked work memo has `audience_tags=[work],
is_sensitive=true`: the team can see it, but actually sharing it
outside requires explicit confirmation. Health notes shared with a
spouse are `audience_tags=[family], is_sensitive=true` for the same
reason. Two questions ("who" and "with how much friction") don't
reduce to one.

The orthogonality holds at the empty-audience end too:
`audience_tags=[], is_sensitive=true` is a legitimate combination —
owner-only content that should still be flagged when quoted, exported,
or surfaced into any downstream context (a private financial note,
a therapy reflection, a draft you never want auto-included anywhere).
`[]` answers the audience question; `is_sensitive` answers the
handling-risk question; both can be set without contradiction.

---

## Format (extensions)

- ASCII `[a-z0-9-]` only
- Lowercase, kebab-case
- Length 2–32
- Concrete (`team-platform` good; `team` bad — too generic, collides
  with `work`)
- Don't invent one-offs you wouldn't reuse ≥5 times — leave entities
  as `[]` instead

Why kebab-case here when concepts use snake_case: audience tags are
**literal labels stored as-is**, not normalised identifiers. They
function like categories on a slot, not like nodes in a graph.
Different role, different convention; both are deliberate.

---

## Semantics

- `[]` → owner only.
- `[a, b]` → union. Anyone in `a` OR `b`.
- `is_sensitive: true` is orthogonal: extra-friction modifier on
  share, not a narrower audience.

---

## On violation — autonomous resolution (no CLARIFICATIONs)

The audience layer is fully autonomous — the engine resolves every
violation with deterministic heuristics and never raises a
CLARIFICATION. The single source of truth is
`_system/scripts/_common.py::normalize_audience_tag()` plus the
whitelist check (canonical 5 ∪ active Extensions) performed by
`/minder:mem:lint` Scan A.7 (`lint_concept_audit.py`).

| Condition | Engine action |
|---|---|
| Tag in canonical 5 verbatim | Pass-through. |
| Tag normalises to a canonical or active extension entry | **Silent autofix** — rewrite to normalised form. Fix-id `audience-tag-normalise-autofix`. (Catches `Family` → `family`, `professional_network` → `professional-network`.) |
| Tag well-formed but NOT in canonical or extension list | **Silent drop** — entity falls back to `[]` (owner-only). Fix-id `audience-tag-drop-autofix` with reason `not-in-whitelist`. |
| Tag fails kebab-case ASCII / length 2-32 / contains non-ASCII | **Silent drop**. Fix-id `audience-tag-drop-autofix` with reason `format-unfixable`. |

**Why fail-closed via drop.** False-positive audience inference leaks
content; false-negative just keeps content owner-only (the safest
default). The engine never coins new extensions on its own — the
Extensions table below remains owner-curated outside the pipeline.
When owner wants a new audience available to the engine, owner adds
a row; subsequent emissions can use it.

`/minder:mem:process` Q16 applies a heuristic canonical-mapping at extraction
time when the model's intended audience semantically fits a canonical
(e.g. "team" → `work`, "linkedin" → `professional-network`, "tweet" →
`world`). Only after that mapping fails is the tag silently dropped.

---

## Heuristics for novel cases

- **Is this `family` or do I need an extension?** If the canonical
  tag captures the intent and you'd reuse it ≥5 times, use canonical.
  If you need to distinguish nuclear from extended family, or one
  specific person, propose an extension (`spouse`, `parents`).

- **Is this `work` or `professional-network`?** Current
  employment / collaboration context → `work`. Past colleague no
  longer collaborating, mentor outside the company, conference
  contact → `professional-network`. The split is "people I see in
  the next sprint" vs "people in my career orbit".

- **Should this be `is_sensitive`?** If the content, accidentally
  shared even with the *intended* audience's wider circle, would
  cause concrete harm — NDA breach, health disclosure, financial
  detail, anything reputational — yes. The marker is friction at
  share time, not narrowing of audience.

- **Cross-domain content (work + family)?** List both:
  `[work, family]`. Don't pick one; the flat union model exists
  exactly for this. Same content can carry overlapping circles.

- **Default `[]` or speculative tag?** When in doubt, `[]`. You can
  always widen later with confidence; you cannot un-share. Tagging
  something `[friends]` because it "feels friendly" without a
  concrete reason is exactly the drift this axis is designed to
  prevent.

- **Is the owner using a tag I've never seen?** Don't guess. The
  engine silently drops it (entity falls back to `[]` — owner-only,
  the safest outcome). If owner wants the tag accepted, they add a
  row to the Extensions table below; subsequent emissions accept it.
  No CLARIFICATION — fail-closed by drop is the contract.

- **Is the same content captured for different audiences in
  different notes?** That's expected. Audience is per-entity, not
  per-concept. The same fact can appear in a private journal entry
  (`[]`) and a LinkedIn-grade thought (`[professional-network]`)
  without contradiction.

- **Tag retirement?** Append-only. Mark `Status: deprecated:{date}`
  in the extensions table; existing entities keep their historical
  labels. Hard-deletion would silently rewrite the past.

---

## Extensions

Append rows below. Append-only — to retire a tag, change `Status` to
`deprecated:{YYYY-MM-DD}`; do not delete.

<!-- BEGIN extensions -->

| Tag | Added | Status | Purpose | Notes |
|---|---|---|---|---|
| _(none yet)_ | — | — | — | — |

<!-- END extensions -->

---

## Examples

| Situation | audience_tags | is_sensitive |
|---|---|---|
| Default private | `[]` | false |
| Owner-only health note (still careful when quoted/exported) | `[]` | true |
| Work decision visible to team | `[work]` | false |
| NDA-locked work memo | `[work]` | true |
| Health note for me + spouse | `[family]` | true |
| Twitter post | `[world]` | false |
| LinkedIn-grade thought | `[professional-network]` | false |
| Stoic reflection for friends | `[friends]` | false |
| Cross-shared (work + friends) | `[work, friends]` | false |

---

Sibling axes: `concepts:` → `CONCEPT_NAMING.md`, `tags:` → `TAGS.md`.
