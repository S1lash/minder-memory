---
last_updated: 2026-05-02
---

# Domains Registry

Whitelist of valid `domains:` values — the "which life area is this
in?" slot on every entity in the knowledge base. Same registry serves
the singular `domain:` field on constitution principles (see
`0_constitution/CONSTITUTION.md` §3) and the plural `domains:` array
on notes, hubs, and typed objects.

---

## Why a closed registry, not free-form vocabulary

A domain is a **structural axis**, not a topical label. Its job is to
partition the knowledge base into life areas the owner navigates by —
so that `domains: [work, learning]` answers "what context is this in?"
not "what is this about?". The latter belongs in `concepts:` (open
graph) or `tags:` (closed bucket registry). Conflating them turns
`domains:` into a second tag vocabulary and destroys the structural
function: cross-domain hub detection, principle scoping, lens routing
all assume a small, stable set.

Three axes, three closed/open trade-offs:

| Axis | Field | Question | Cardinality |
|---|---|---|---|
| Domain | `domains:` / `domain:` | "Which life area?" | **Closed** — small fixed set, owner-extensible via Extensions |
| Tag | `tags:` | "Which categorical bucket?" | Closed registry of `category/value` |
| Concept | `concepts:` | "What does this touch?" | Open graph — new nodes emerge as the world expands |

Closing the domain set is what makes hubs that span domains visible
(a note tagged `[work, learning]` is an honest cross-domain bridge;
a note tagged `[payments, queue, restructuring]` is just a list of
concepts mislabelled as domains).

---

## What a domain means

A domain names **a life area the owner navigates by** — a context
that organises attention, energy, and decisions. It is not "what
this note is about" (concept), nor "which formal category" (tag) —
it's "which slice of life does this belong to?".

The set is deliberately **broad-but-distinct**: each label captures
a context coarse enough to host hundreds of notes, narrow enough
that two domains do not collapse into the same answer.

### The canonical thirteen

Every knowledge base ships with the same thirteen labels, grouped
for readability. The groups are presentational; the labels are flat
peers in the validation set.

#### Life context — where the activity happens

| Domain | Meaning | What distinguishes it |
|---|---|---|
| `work` | Current role / employment / team / projects | Bounded by the present job. NOT past employment, NOT industry-wide thinking. |
| `career` | Professional trajectory, role transitions, growth | The arc above any single job. Career-shape thinking lives here even while employed at a specific `work`. |
| `personal` | Personal life, umbrella catch-all | Used when a more specific label below doesn't fit. Honest fallback, not a synonym for "private". |

#### Self & values — about me

| Domain | Meaning | What distinguishes it |
|---|---|---|
| `identity` | Self-narrative, who I am, what shapes me | Inward-facing — values, formative episodes, self-understanding. |
| `ethics` | Moral code, how to act | Outward-facing answer to "what's right here?". Distinct from `identity` (which is descriptive of self) by being prescriptive of conduct. |
| `health` | Body + mind, energy, wellbeing | Physical and mental together — sleep, exercise, mood, recovery. Not split by body/mind because the system reads them as one substrate. |

#### People — with whom

| Domain | Meaning | What distinguishes it |
|---|---|---|
| `relationships` | Close circle — family, partner, friends | Voluntary or kinship-bound bonds. Not transactional / professional contacts (those are work-context people, not a `relationships` matter). |

#### Investments — active investment of energy / resources

| Domain | Meaning | What distinguishes it |
|---|---|---|
| `learning` | Active skill acquisition, study, deliberate practice | Distinguished from passive reading by intent — courses, structured study, deliberate practice. Reading "for information" is not `learning`. |
| `money` | Personal finances, investments, spending | Personal-side only. Work-budget questions are `work`. |
| `time` | Time + energy management | Calendar shape, focus practices, recovery, throughput thinking. The meta-practice of running one's day. |

#### Practices — cross-cutting toolboxes

| Domain | Meaning | What distinguishes it |
|---|---|---|
| `ai-interaction` | How to work with AI agents | Prompt patterns, agent design, what behaviour to ask for. Distinct from `tech` because it's about the *interaction*, not the implementation. |
| `tech` | Technical knowledge not bound to current work | Languages, frameworks, tooling explored outside the immediate job. If a tech topic is bound to a current `work` project, tag both. |
| `meta` | Reflection on the system itself — Minder Memory, second-brain practice | Notes about how the knowledge base or workflow itself works. Self-referential by nature. |

These thirteen are reserved keywords. Extensions cannot **be equal
to** a canonical label (case-folded) and cannot differ only in
casing or punctuation (`Work`, `work_`, `work.` all conflict with
`work`). Extensions **may** use a canonical word as part of a
clearly distinct longer label — `work-platform` is fine alongside
`work`, `health-mental` is fine alongside `health`. The test:
would a reader instantly see them as different domains? If yes,
allowed. If a reader would think «that's just `work` spelt
differently», the engine treats it as a reserved-keyword conflict
and silently drops the extension at load time (the canonical wins).

### Why flat (no hierarchy)

`personal ⊃ health ⊃ relationships` looks plausible but is wrong in
practice. A note about a difficult conversation with a partner is
both `relationships` and `health` (mental load); collapsing it under
`personal` loses both signals. Cross-domain notes ARE the high-value
class — flat membership preserves them as `[relationships, health]`
without forcing one over the other.

### Why `personal` exists alongside the granular labels

Real notes don't always partition cleanly into `identity / ethics /
relationships / health`. A bulk reflection on "how my last weekend
went" touches several without being primarily about any. Forcing a
choice would either drop the note out of the system or distort its
classification. `personal` is the honest umbrella for that residual.

It is NOT a synonym for "private" — privacy is governed by
`audience_tags`. A `personal` note can still be `audience_tags=[friends]`
if owner intends to share. Domain answers "which life area"; audience
answers "who can see it"; never conflate.

### Why empty `[]` is allowed

Some notes — pure technical references, raw transcripts before
processing, structural index pages — don't belong to any life area.
Empty `domains: []` is the correct answer, not a defect. The engine
treats absence as a deliberate signal, not as missing data to be
filled.

---

## Format (extensions)

- ASCII `[a-z0-9-]` only
- Lowercase, kebab-case
- Length 2–32
- Concrete enough to host multiple notes — `gardening` good if you
  garden often; `that-one-conference` bad (too narrow, would never
  reach reuse threshold)
- Don't invent one-offs you wouldn't reuse ≥10 times — leave the
  entity in an existing canonical domain or `[]` instead

The kebab-case convention matches `audience_tags`. Domain values are
**literal labels stored as-is**, not normalised graph identifiers,
so the convention follows the slot's role (categories) rather than
the concept layer's (graph nodes).

---

## Semantics

- `[]` → not assigned to a life area (deliberate, not a defect).
- `[a]` → single-domain entity.
- `[a, b]` → cross-domain. Both contexts share the entity equally;
  no implicit primary.

The plural `domains:` (notes, hubs, typed objects) is a list. The
singular `domain:` (constitution principles) is a single string —
principles answer "which life area does this principle govern?",
and a principle that genuinely spans two domains is usually two
related principles, not one unscoped.

---

## On violation — autonomous resolution

The domain layer is autonomous on the deterministic substrate — the
engine resolves format violations and unknown values via
`_system/scripts/_common.py::normalize_domain()` plus the whitelist
check (canonical 13 ∪ active Extensions) performed by `/minder:mem:lint`
Scan A.7 (`lint_concept_audit.py::fix_domains`).

| Condition | Engine action |
|---|---|
| Value in canonical 13 verbatim | Pass-through. |
| Value normalises to a canonical or active extension entry | **Silent autofix** — rewrite to normalised form. Fix-id `domain-normalise-autofix`. (Catches `Work` → `work`, `ai_interaction` → `ai-interaction`.) |
| Slash-syntax (`work/learning`, `personal/psychology`) | **Split-and-filter.** Each part normalised independently and filtered against the accept set. Both canonical → both kept (`work/learning` → `[work, learning]`). Suffix not in whitelist → silent drop of suffix only (`work/process` → `[work]`). Fix-id `domain-normalise-autofix` on the resulting set; `domain-drop-autofix` on each part that fails the filter. The rationale: slash is the owner's compact notation for multi-domain membership; the flat Minder Memory axis is multi-valued (`domains: [work, learning]`), so the substrate honours the intent rather than collapsing it. |
| Value well-formed but NOT in canonical or extension list | **Silent drop** — entity loses that single value (other valid entries kept). Fix-id `domain-drop-autofix` with reason `not-in-whitelist`. |
| Value fails kebab-case ASCII / length 2–32 / contains non-ASCII | **Silent drop**. Fix-id `domain-drop-autofix` with reason `format-unfixable`. |

**Why fail-closed via drop.** A misclassified domain silently expands
the structural axis and dilutes hub detection. The safest failure is
"not classified" (`[]` or fewer entries), never "guessed". The engine
never coins new extensions on its own — Extensions table below is
owner-curated outside the pipeline.

**LLM cascade.** Residual values that survive deterministic
normalisation but miss the whitelist are not silently dropped at the
substrate level — they enter the concept-matcher subagent in
`/minder:mem:process` Step 3.4.5 (same matcher for inbox-scan and
`--reprocess-corpus` modes), which receives them alongside unmatched
concept candidates and emits `domain_resolutions[]` per value:

1. `normalize_domain` (deterministic) →
2. whitelist check (canonical ∪ extensions) →
3. matcher subagent: **LLM remap** to nearest canonical with reasoning →
4. matcher subagent: judge material-vs-trivial — trivial → drop with
   log entry; material → CLARIFICATION of type `domain-resolution`
   with conservative default (drop the value).

The lint-level deterministic substrate (this file's «On violation»
table) is the floor; the matcher cascade is layered on top by the
SKILL that owns LLM judgement. Lint never invokes LLM directly.

---

## Heuristics for novel cases

- **Is this `work` or `career`?** Current role / project / team
  decision → `work`. Thinking about the arc — promotions,
  transitions, "what role do I want next" → `career`. A note can
  be both: `[work, career]` for "this current project is shaping
  the trajectory I want".

- **Is this `personal` or one of the granular ones?** If a granular
  domain is the dominant frame, use it. If the note is genuinely
  about life broadly without a single frame, `personal` is honest.
  Don't over-pick `personal` as a hedge — it weakens cross-domain
  hub detection.

- **Is this `tech` or `work`?** Work-context tech (your team's stack,
  current project's database) → `work`. Tech explored independently
  (a side-project framework, a language being learned) → `tech`. If
  it's a side-project explicitly serving career growth, all three
  apply: `[tech, learning, career]`.

- **Cross-domain content?** List all that apply: `[work, learning]`,
  `[relationships, health]`, `[ai-interaction, meta]`. The flat-union
  model exists for exactly this. Choosing one when several fit is
  the drift the closed set is designed to prevent.

- **Is the owner using a domain I've never seen?** Don't guess.
  Engine silently drops it (entity falls back to its remaining valid
  entries, possibly `[]`). If the value should be a canonical, owner
  proposes a canonical update (manual edit to `_common.py::ALLOWED_DOMAINS`
  + DOMAINS.md). If it's a personal extension, owner adds a row to
  the Extensions table below; subsequent emissions accept it.

- **Domain retirement?** Append-only. Mark `Status: deprecated:{date}`
  in the extensions table; existing entities keep their historical
  labels. Hard-deletion would silently rewrite the past.

---

## Extensions

Append rows below. Append-only — to retire a domain, change `Status`
to `deprecated:{YYYY-MM-DD}`; do not delete.

<!-- BEGIN extensions -->

| Domain | Added | Status | Purpose | Notes |
|---|---|---|---|---|
| _(none yet)_ | — | — | — | — |

<!-- END extensions -->

---

## Examples

| Note shape | domains | Notes |
|---|---|---|
| Standup decision in current sprint | `[work]` | Bounded by present role. |
| Career-shape reflection on next move | `[career]` | Independent of current sprint detail. |
| Side-project architecture exploration | `[tech, learning]` | Not bound to current job; explicit growth. |
| Stoic reflection | `[identity, ethics]` | Self-narrative + how-to-act. |
| Difficult conversation with partner | `[relationships, health]` | Mental load is real signal — keep both. |
| Workout log entry | `[health]` | Single granular context. |
| Personal budget review | `[money]` | Personal-side; work budget would be `[work]`. |
| Calendar redesign for the quarter | `[time]` | Meta-practice of running one's day. |
| Prompt-engineering pattern for an agent | `[ai-interaction]` | About interaction, not stack implementation. |
| Minder Memory engine spec edit | `[meta]` | Self-referential to the system. |
| Generic life reflection | `[personal]` | When more specific doesn't fit. |
| Pure code-snippet reference | `[]` | Not a life-area question. |

---

## Relationship to Minder downstream

Minder Memory emits `domains: [...]` arrays as-is; downstream Minder consumer
derives its per-concept-mention scope (`ConceptDomain` enum: WORK /
PERSONAL / MIXED / UNKNOWN) internally from the containing entity's
`domains:` + `origin`. Minder Memory does NOT emit ConceptDomain values
directly. The two axes are kept structurally separate: Minder Memory's
fine-grained life-area axis is richer than Minder's per-mention
scope, and collapsing one into the other would lose information at
the boundary.

The Minder enum is mirrored as `_common.py::MINDER_CONCEPT_DOMAIN`
for documentation and downstream consumer reference; it does NOT
participate in engine-side validation of `domains:` values.

---

Sibling axes: `audience_tags:` → `AUDIENCES.md`, `concepts:` →
`CONCEPT_NAMING.md`, `tags:` → `TAGS.md`.
