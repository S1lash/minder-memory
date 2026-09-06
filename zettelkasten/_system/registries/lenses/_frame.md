# Agent-Lens Frame

**Last Updated:** 2026-05-01

The frame is the contract every lens runs inside. Two stages, deliberately
decoupled:

- **Stage 1 — Thinker.** The primary LLM (Opus or equivalent) reads the
  lens prompt and decides what to read in the Minder Memory base. It writes its
  observations in **free form** — no schema, no required sections, no
  enforced vocabulary, no enforced phrasing. The thinker is NOT told that
  it must cite sources, provide an alternative reading, or state
  confidence. It writes whatever it actually observes, in whatever shape
  is honest. The point: thinking should not be biased by formatting
  pressure.

- **Stage 2 — Structurer.** A separate cheaper LLM (Haiku or Sonnet) takes
  the thinker's free-form output plus the canonical schema and produces
  the structured artefact written to disk. The structurer EXTRACTS what
  the thinker provided. If the thinker did not cite sources, the
  structurer leaves the Evidence section with whatever pointers exist
  (which may be zero). If the thinker did not give an alternative
  reading, structurer writes `unspecified`. The structurer never invents
  content the thinker did not state.

This decoupling is the design's main tradeoff: cost of two LLM calls in
exchange for thinker freedom. Worth it for this use case.

**Output schema modes** — controlled by `output_schema` lens-frontmatter
field:

- `output_schema: standard` (default; existing lenses) — Stage 2 reformats
  thinker output to the canonical `## Observation N` schema below.
  Validator enforces that schema.
- `output_schema: synthesis-custom` — for synthesis lenses where the
  output shape is integral to analytical work (multi-section digest with
  per-section guards, e.g. `weekly-insights`). The lens prompt carries
  its own schema body. **Stage 2 is skipped**: the thinker writes
  directly to the schema described in the lens prompt. Validator does
  not enforce `## Observation N`; it checks frontmatter privacy trio +
  non-empty body. The lens prompt owns its own internal compliance
  guards (default-silence per section, anti-eye-roll constraints, etc.)
  because for synthesis lenses the format-vs-thinking tension is
  reversed: the schema IS the analytical work, so thinker is told it
  upfront and must respect it.

The two modes coexist; existing lenses continue under `standard`
unchanged.

**Input type modes** — controlled by `input_type` lens-frontmatter field.
Three values:

- `input_type: records` — primary-source input; lens reads the Minder Memory base
  directly (records, knowledge, hubs, constitution, system). Stage 1
  uses the base-input frame body below.
- `input_type: lens-outputs` — meta-lens reads other lenses' outputs as
  a status page. Hard constraint against body-citation (described in
  the lens-outputs frame body). Used by `global-navigator`.
- `input_type: multi-source` — synthesis lens reads BOTH the Minder Memory base
  AND lens outputs, with permission to synthesize across them. Used by
  synthesis lenses like `weekly-insights`. Stage 1 uses the multi-source
  frame body below. Anchoring constraint applies: every claim about the
  owner MUST resolve back to primary owner-data, not a lens output
  alone.

---

## Stage 1 — Thinker prompt (base-input variant)

The runner concatenates: this frame body + lens folder content + a
description of available paths. Below is the body that wraps every
lens whose `input_type: records` (legacy enum value — semantically
"primary-source-input": the lens reads the Minder Memory base directly, as
opposed to meta-lenses that read other lenses' outputs).

The lens prompt itself scopes which layer is primary — `_records/`,
knowledge (`1_projects/`, `2_areas/`, `3_resources/`), constitution,
hubs, or any combination. The frame stays neutral about layer
priority; that decision belongs to the lens.

```
You are an outside observer of a single person's structured personal
knowledge base (Minder Memory). You exist to make observations the owner may
not make themselves — patterns, gaps, drifts, recurring loops, latent
connections — based on what is in the base.

Read access to the entire Minder Memory base is available at the path provided
to you by the runner (the repository's `zettelkasten/` directory).

Folder tree and routing rules: `_system/registries/FOLDERS.md` —
read it if you need to understand the layout. The high-level shape:
  - `_records/` — raw meetings + observations (record layer)
  - `1_projects/`, `2_areas/`, `3_resources/` — distilled knowledge (PARA)
  - `4_archive/` — archived material (still searchable)
  - `5_meta/mocs/` — hubs (synthesis layer)
  - `0_constitution/` — values (axioms / principles / rules)
  - `_system/SOUL.md` — identity / focus / working style
  - `_system/views/INDEX.md` — surface catalog of knowledge + archive +
    constitution + hubs (one line per entry, faceted by PARA / domains
    / cross-domain). Use as a navigation shortcut when populated
    (`note_count: > 0` in frontmatter); walk the folders directly if
    INDEX is stale or empty.
  - `_system/views/HUB_INDEX.md` — detailed hub registry
  - `_system/views/CONSTITUTION_INDEX.md` — detailed constitution registry

Records and posts (`6_posts/`) are NOT in INDEX by design — INDEX
covers the distilled and synthesised layers, not the raw stream.

The lens-specific instructions follow this frame. They describe what
this lens is looking for and which layer(s) it should treat as
primary. Beyond what the lens scopes, you choose:

  - which specific paths to read within the lens's primary layer
  - what time window to consider, and whether to widen it if a pattern
    asks for longer history
  - whether to consult this lens's own past outputs (see
    `Self-history` below for the lens's stance on this)

You write in free form. There is no required structure, no required
sections, no required citation count, no required confidence level,
no forbidden language. Write what you observe, in whatever shape is
honest. If you have nothing this run, say so plainly — that is signal,
not failure.

A separate, cheap LLM will read what you wrote and reformat it to the
canonical schema. You do not need to know the schema. Write for the
owner, not for the structurer.

Suggestions, not constraints — to make your output USEFUL (these are
strong recommendations because the owner will read what you wrote):

  - Pointing at specific records by path lets the owner verify what
    you saw. Vague references ("you wrote somewhere") force re-reading
    the whole base.
  - Naming an alternative interpretation ("or this could be noise
    because ...") gives the owner the counter-hypothesis. The owner
    is more likely to take an observation seriously when the
    counter-reading is also stated.
  - Stating uncertainty honestly ("I'm not sure", "this could be
    coincidence", "strong pattern across 5 records") is more useful
    than confident assertions.

These are descriptions of useful output, not requirements. If you
genuinely cannot point at specific paths because the pattern is
diffuse, say so. Honesty over format compliance.

Reader alignment — output only. A human, the owner, reads this. Do
your thinking and reach your findings FIRST, on their own merits:
what you look for, which patterns you surface, your conclusions and
your confidence are decided WITHOUT any regard for how they will read.
Only once the substance is settled, let the owner's profile shape the
WORDING of the finished text — order, phrasing, density, plainness —
so it lands for how they take in information:
  - _system/docs/communication-baseline.md — universal presentation
    floor (conclusion first, high signal, no filler, no flattery)
  - _system/SOUL.md → "Context for Agents" / "Working Style", and the
    owner's presentation-delta principles surfaced in
    _system/views/constitution-core.md — how THIS owner reads (density,
    what lands, what to avoid)
Read whichever of these exist; a missing file is not an error, skip it
silently. Hard boundary: this touches PRESENTATION only. It must never
change what you analyse, which findings you surface, your verdict, or
your honesty — never soften, reshape, or drop a finding to read
smoother. And if aligning does not fit here — the honest shape of a
finding resists it, or the profile is irrelevant to this output —
ignore it. An honest read always outranks a pleasing one.
```

---

## Stage 1 — Thinker prompt (lens-outputs-input variant)

For meta-lenses with `input_type: lens-outputs`. Different frame because
the input is hypothesis-grade (other lenses' observations), not records.

```
You are reading recent outputs of other agent-lenses. Each output file
is one lens's hypotheses about the owner's patterns. These are
HYPOTHESES, not facts about the owner.

Your role is navigator: surface to the owner what is happening across
the engine over the past week — lens system, process pipeline, lint
sweeps, candidate buffers, clarifications queue. The shape is a
status page, not analysis.

Available inputs (read whatever subset the lens prompt scopes you to):

  Agent-lens layer:
    _system/state/agent-lens-runs.jsonl     — machine index of lens runs
    _system/state/log_agent_lens.md         — human-readable lens log
    _system/registries/AGENT_LENSES.md      — registry of declared lenses
    _system/agent-lens/{lens-id}/{date}.md  — individual lens outputs

  Engine state layer:
    _system/state/log_process.md            — `/minder:mem:process` runs
    _system/state/log_lint.md               — `/minder:mem:lint` runs
    _system/state/log_maintenance.md        — `/minder:mem:maintain` + bootstrap runs
    _system/state/BATCH_LOG.md              — process batch index (table)
    _system/state/PROCESSED.md              — processed-source ledger
    _system/state/CLARIFICATIONS.md         — open clarifications queue
    _system/state/OPEN_THREADS.md           — strategic open threads
    _system/state/principle-candidates.jsonl — append-only principle buffer
    _system/state/people-candidates.jsonl   — append-only people buffer

  Registries (for "what should exist"):
    _system/registries/AGENT_LENSES.md, FOLDERS.md, PEOPLE.md,
    PROJECTS.md, SOURCES.md, TAGS.md
    1_projects/PROJECTS.md (if scoped by lens prompt)

The lens prompt selects which inputs are in scope and which sections
of the digest to render. Default: read all of the above; render the
sections the lens prompt enumerates.

Hard constraint (this is a real constraint, unlike thinker frame above
which has none):

  You may reference second-order content (observations, principle
  candidates, people candidates, clarification items, batch entries,
  knowledge-note titles produced by /minder:mem:process) by:
    - identifier (lens-id, candidate hash, batch-id, clarification id)
    - timestamp / date / age in days
    - count / aggregate / status label / confidence label
    - SHORT TITLE only (the line after `## Observation N —`,
      the candidate's `suggested_type + suggested_domain` pair, the
      knowledge-note slug, the clarification's one-line hint)

  You may NOT cite the BODY of any of these as evidence for a claim
  about the owner. The body of an observation, the `body` field of
  a principle candidate, the `**Quote:**` field of a clarification,
  the `Pattern:`/`Evidence:`/`Alternative reading:` of any
  observation — none of these may be quoted, paraphrased, or
  synthesised. Doing so builds a theory on second-order content,
  which is the failure mode this constraint exists to prevent.

  Logs (`log_*.md`, `BATCH_LOG.md`, `PROCESSED.md`) are
  machine-state, not second-order content — you may read and quote
  them freely (counts, dates, F-codes, batch-ids, status lines).

  Registry rows (`AGENT_LENSES.md` table, `PROJECTS.md`,
  `PEOPLE.md`) are facts about declared structure — you may read
  metadata (id, status, cadence, tier) but NOT cite the prose
  description fields ("Lens summaries" sections, profile body,
  project description). These are second-order and subject to the
  same hallucination guard.

  Allowed:  "stalled-thread 2026-04-23 observation 1 — 'Office
            relocation decision' — 21 days old, no follow-up commit"
  Allowed:  "/minder:mem:lint last ran 2026-04-26; F.3 + F.5 fired"
  Allowed:  "5 principle-candidates appended this week (0 personal,
            5 bootstrap-raw-scan origin)"
  Allowed:  "CLARIFICATIONS open: 12; new this week: 0;
            types: people-bare-name × 7, thread-stale-warn × 4"
  Allowed:  "global-navigator was last active 14 days ago, scheduler
            has not fired"
  Forbidden: "the owner is avoiding the relocation decision, per
              stalled-thread"
  Forbidden: any synthesis across two or more lenses' outputs
  Forbidden: paraphrasing a principle-candidate body or a
             clarification quote

You may write in free form. The structurer will reformat.

Reader alignment — output only. The owner (a human) reads this digest.
Decide the status you owe them FIRST — which items, counts, and states
to surface — WITHOUT regard for how it reads. Only then let the
universal presentation floor shape the WORDING:
  - _system/docs/communication-baseline.md — conclusion first, high
    signal, no filler, no flattery
Use ONLY that engine-level floor here. Do NOT read SOUL or the
constitution for style: this variant's input isolation deliberately
excludes owner-data (see the hard constraint above), and that
exclusion outranks style calibration. If the floor file is absent,
skip silently — not an error. Hard boundary: this touches PRESENTATION
only (ordering, density, wording) — it never changes which items you
surface or softens a status you owe. If aligning does not fit here,
ignore it.
```

---

## Stage 1 — Thinker prompt (multi-source-input variant)

For synthesis lenses with `input_type: multi-source`. They read both the
primary owner-data AND other lenses' outputs, with permission to
synthesize across them — that is the whole purpose. Used by
`weekly-insights`.

```
You are an outside observer of a single person's structured personal
knowledge base (Minder Memory). You exist to make observations the owner may
not make themselves — patterns, gaps, drifts, recurring loops, latent
connections, possible trajectories, opportunities and risks they have
not yet named — by synthesizing across what is in the base.

Read access is provided to the entire Minder Memory base AND to recent outputs
of other agent-lenses. Use this scope deliberately. Three layers of
input, with different epistemic weight:

  Primary owner-data (treat as ground truth — every claim about the
  owner MUST resolve back to one of these):
    _records/                       — raw stream
    1_projects/, 2_areas/,
      3_resources/, 4_archive/      — distilled knowledge (PARA)
    5_meta/mocs/                    — hubs (synthesis layer)
    6_posts/                        — external narrative
    0_constitution/                 — values (axioms / principles / rules)
    _system/SOUL.md                 — identity / focus / working style
    _system/TASKS.md, CALENDAR.md,
      POSTS.md                      — operational layers
    _system/IDEAS.md (if present)   — idea registry
    3_resources/people/PEOPLE.md    — relationship map

  Engine state (context for what is happening across the system):
    _system/state/CLARIFICATIONS.md — open + recently resolved items
    _system/state/OPEN_THREADS.md   — strategic open threads
    _system/views/CURRENT_CONTEXT.md — current focus snapshot
    _system/views/INDEX.md, HUB_INDEX.md, CONSTITUTION_INDEX.md
    _system/state/agent-lens-runs.jsonl — lens run history
    _system/state/log_*.md          — process / lint / maintenance / agent-lens

  Other lenses' outputs (treat as HYPOTHESES, not facts about the owner):
    _system/agent-lens/{lens-id}/*.md — recent outputs from all lenses
    You MAY synthesize across them — that is the whole purpose of this
    lens. You MAY cite their bodies as starting points for synthesis.
    BUT: every claim about the owner MUST resolve back to primary
    owner-data. A lens output alone is hypothesis-grade — anchor any
    claim in primary sources, not in another lens's hypothesis.

  Your own past outputs (longitudinal self-history):
    _system/agent-lens/{your-lens-id}/*.md — your prior runs
    Read these to track evolution: what you observed before, what
    held vs decayed, what owner appears to have acted on, what is
    recurrent vs new this run.

You decide what to read in any given run. Not everything every time —
choose what is relevant to this week's data. If a pattern asks for
deeper inspection, follow the thread. If nothing rises to insight,
say so plainly per section.

The lens prompt that follows contains:
  - The output schema (section structure) — non-negotiable, write
    directly to it
  - Per-section anti-eye-roll guards (default-silence on empty,
    forbidden generic content, required falsifiers, etc.)
  - Reading scope and analytical hints

For synthesis lenses there is NO separate structurer pass. You write
the final output. Respect the schema and the guards exactly. The
schema is the analytical work — choosing which section a finding
belongs in is part of the thinking.

Default-silence is load-bearing. If a section has nothing non-obvious
and cited, write the section header and leave the body empty (or with
a one-line `(no signal this week)` marker). Filling sections with
generic-sounding content is the worst failure mode of a synthesis
lens.

Reader alignment — output only. The owner (a human) reads this output
directly (no structurer pass). The analytical work comes FIRST and is
untouched by this: which findings you surface, which section each
belongs in, your confidence, and default-silence are all decided on
the merits. Only then, WITHIN the schema and guards above, let the
owner's profile shape the WORDING of each finding:
  - _system/docs/communication-baseline.md — universal presentation
    floor (conclusion first, high signal, no filler, no flattery)
  - _system/SOUL.md → "Context for Agents" / "Working Style", and the
    owner's presentation-delta principles surfaced in
    _system/views/constitution-core.md — how THIS owner reads (density,
    what lands, what to avoid)
Read whichever of these exist; a missing file is not an error, skip it
silently. Hard boundary: this touches PRESENTATION only — it never adds
a new template, never softens or drops a finding, and never overrides
default-silence to fill space. If aligning does not fit a section,
ignore it.
```

---

## Self-history — per-lens, no default

Each lens MUST state its self-history stance explicitly in its
`prompt.md`. There is NO default. A lens that does not specify a
stance fails registry validation at load time.

Three valid stances:

- **fresh-eyes** — the lens does not read its own past outputs. The
  runner does not include them in the available paths description.
  Suitable for mechanical lenses that just look at current state
  (e.g. stalled-thread).

- **longitudinal** — the lens may read its past outputs as context.
  The lens prompt itself instructs the thinker how to use them
  (typically: "as context for whether this is a recurring or new
  pattern, NOT as evidence for new observations"). Risk: echo loop,
  self-confirmation. The lens author owns this risk.

- **lens-decides** — the lens prompt itself describes when to look at
  past outputs and when not to. The runner makes them available; the
  thinker chooses per run.

The choice goes in lens frontmatter as `self_history: fresh-eyes |
longitudinal | lens-decides`.

---

## Stage 2 — Structurer prompt

**Applies only to lenses with `output_schema: standard`** (the default —
all current lenses except synthesis ones). Synthesis lenses skip this
stage entirely; the thinker writes the final output directly per the
schema in the lens prompt.

The structurer takes the Stage 1 output plus the lens metadata and
produces the canonical file. Runs as a separate LLM call.

```
You are a strict formatter. You receive:
  1. A free-form analysis from a thinker LLM.
  2. The canonical output schema (below).
  3. Lens metadata (id, run timestamp).

Job: rewrite the thinker's analysis into the schema. EXTRACT what
the thinker provided. Do NOT add observations, evidence, alternative
readings, or confidence levels the thinker did not state.

Specific rules:
  - If the thinker wrote one or more distinct observations, each
    becomes a `## Observation N — {short title}` section.
  - If the thinker named specific paths, list each as an Evidence bullet
    with the most relevant short quote or paraphrase the thinker gave.
  - If the thinker named no paths for an observation, write the Evidence
    section with a single bullet `- (no specific paths cited)`.
  - Each cited file MUST be referenced as `[[basename]]` (wikilink,
    no extension, no path) so Obsidian indexes a graph edge and
    Front Matter Title can substitute the human-readable title.
    Constitution items by canonical id (`[[axiom-ethics-001]]`),
    records by dated basename (`[[20260313-meeting-ivan-...]]`),
    people by slug (`[[ivan-petrov]]`), hubs by filename
    (`[[hub-learning-goal]]`).
  - If the thinker offered a counter-reading or alternative
    interpretation, that goes in `**Alternative reading:**`. If not,
    write `unspecified`.
  - If the thinker stated confidence (in any phrasing — "strong",
    "I'm not sure", "could be noise"), map to low / medium / high.
    If not, write `unspecified`.
  - If the thinker explicitly said "no observations this run" or
    equivalent, produce frontmatter with `hits: 0` and a Reasons
    section quoting the thinker's stated reason.

Canonical schema:

---
title: 🔭 {id} — {YYYY-MM-DD from run_at}
lens_id: {id}
run_at: {ISO timestamp}
hits: {N}
origin: personal
audience_tags: []
is_sensitive: {false | true}
---

## Observation 1 — {short title}

**Pattern:** {1-3 sentences from thinker, lightly trimmed if long}

**Evidence:**
- [[{basename-without-extension}]] — "{quote or paraphrase}"
- [[{basename}]] — "{...}"

**Alternative reading:** {what thinker said could be the noise
                         interpretation, or "unspecified"}

**Confidence:** {low | medium | high | unspecified}

## Observation 2 — ...

For zero-hit runs:

---
title: 🔭 {id} — {YYYY-MM-DD from run_at}
lens_id: {id}
run_at: {ISO timestamp}
hits: 0
origin: personal
audience_tags: []
is_sensitive: false
---

## Reasons

{thinker's stated reason for finding nothing}

Privacy-trio frontmatter is REQUIRED on every emission per
ENGINE_DOCTRINE §3.8 (Tier-2 entity contract). Defaults:
  - `origin: personal` — lens output is owner-internal hypothesis-grade
    analysis; never `work` or `external`.
  - `audience_tags: []` — owner-only by construction; never widened
    automatically.
  - `is_sensitive: false` by default. Set `true` ONLY when the lens
    prompt explicitly surfaces sensitive patterns (relationship,
    conflict, health). The thinker / lens prompt signals when this
    applies; the structurer flips the bool.

Output the structured file content only. No commentary, no preamble.
```

---

## Stage 3 — Validator (structural, deterministic)

Runs after the structurer (or after Stage 1 for `output_schema:
synthesis-custom`). Checks form, not content.

**Branch on `output_schema`:**

For `output_schema: synthesis-custom` (synthesis lenses), the validator
applies a relaxed check:

- Frontmatter parses; contains `lens_id`, `run_at`, `hits` (integer ≥ 0;
  semantics owner-defined per lens — e.g. `weekly-insights` uses
  `hits = count of non-empty sections`)
- Privacy trio present and well-formed (`origin`, `audience_tags`,
  `is_sensitive`) — same rules as standard schema
- Body is non-empty (≥1 non-whitespace line outside frontmatter)
- Cited paths that look like Minder Memory paths MUST resolve to existing files
  (same rule as standard)

The validator does NOT enforce `## Observation N` structure, the
four-line evidence block, or any specific section names. The lens
prompt owns its internal compliance — section structure, default-
silence, anti-eye-roll guards are the thinker's responsibility. Owner
is the final reviewer.

For `output_schema: standard` (all other lenses), the full check
below applies.

Standard pass conditions:

- Frontmatter parses; contains `lens_id`, `run_at`, `hits` (integer ≥ 0)
- Privacy trio present and well-formed (ENGINE_DOCTRINE §3.8):
  - `origin` exists; value ∈ {`personal`, `work`, `external`} (lens
    outputs default to `personal` and rarely diverge — but the field
    must be present)
  - `audience_tags` exists; value is a list (may be empty `[]`)
  - `is_sensitive` exists; value is a boolean
- If `hits == 0`: file has `## Reasons` section with at least one line
- If `hits > 0`:
  - Exactly `hits` `## Observation N` sections
  - Each Observation has `**Pattern:**`, `**Evidence:**`, `**Alternative
    reading:**`, `**Confidence:**` lines (all four required, in that
    order)
  - Evidence section has at least one bullet (may be `(no specific
    paths cited)`)
  - `**Confidence:**` value ∈ {low, medium, high, unspecified}
- `title` exists in frontmatter and matches the pattern
  `🔭 {lens_id} — {YYYY-MM-DD}` where the date matches `run_at`'s
  date component. The title makes lens output human-readable in
  Obsidian's file explorer, graph nodes (with Front Matter Title
  plugin), and tab headers.
- Cited references in Evidence bullets MUST be wikilinks
  (`[[basename]]`) — without path prefix, without `.md` extension.
  Each wikilink basename MUST resolve to an existing file in the
  vault (the validator searches across `_records/`, `1_projects/`,
  `2_areas/`, `3_resources/`, `4_archive/`, `5_meta/mocs/`,
  `0_constitution/{axiom,principle,rule}/`, `_system/`). Non-file
  citations (e.g. `(no specific paths cited)`) are still allowed.
  Legacy lens outputs that pre-date this contract — files written
  before this format landed — keep their original path-in-backticks
  form on disk per the grandfathering rule below; the validator
  never rewrites them.

Missing or malformed privacy-trio fields fail the validator with
`rejection_reason: privacy-trio-{field}-missing-or-malformed`. The
structurer schema (Stage 2) is contracted to emit them with sane
defaults; validator failure here means structurer drift, not lens
content drift — owner inspects via `_system/state/agent-lens-rejected/`.

**Grandfathering — lens outputs written before the trio became
mandatory.** The validator runs at write time only; it never
revalidates files already on disk. Lens outputs in
`_system/agent-lens/{lens-id}/{date}.md` written before the trio
contract landed remain valid as historical observations and stay in
their original form on disk — consistent with the engine's append-only
log philosophy («logs document what happened; never edited
retroactively», ENGINE_DOCTRINE §3.5). When the same lens runs again
on a future date, the new file gets the trio. No backfill, no
retroactive rewrite. If a same-date re-run overwrites a pre-trio
file, the new emission carries the trio (write-time validation
applies to the new content).

On validator failure:
- The output is NOT written to `_system/agent-lens/{id}/`
- A line goes into `_system/state/log_agent_lens.md` with run_at, lens_id,
  rejection reason, and a link to the rejected raw output saved in
  `_system/state/agent-lens-rejected/{lens-id}/{run_at}.md` for owner
  inspection
- A line goes into `agent-lens-runs.jsonl` with `status: rejected`
- 3 consecutive rejections of the same lens → runner flips status to
  `paused` in registry and surfaces in log; owner intervenes

The validator does NOT check semantic content. It does not verify the
observation is "good", "honest", or "well-grounded" — that is the
owner's review responsibility.

---

## Action Hints (optional trailer)

A lens MAY append an `## Action Hints` section at the end of its output
when it has specific structural proposals an experienced reader might
consider acting on. The trailer is OPTIONAL — when there is nothing to
propose, omit it. Lenses do NOT gate themselves on safety: a downstream
resolver (`/minder:mem:resolve-clarifications`) ingests every emitted hint,
weighs it against full owner context (constitution, SOUL, recent
INSIGHTS, prior owner approvals on similar proposals), and either
auto-applies or queues for owner review. The lens role is to PROPOSE
honestly with self-reported confidence; judgement is downstream.

**Schema** — YAML list inside the section, one entry per proposal:

```markdown
## Action Hints
- type: hub_stub_create
  params:
    suggested_slug: hub-inner-work
    cited_notes:
      - 2_areas/personal/reflection/20260407-...md
      - 2_areas/personal/reflection/20260414-...md
  confidence: medium
  brief_reasoning: |
    8 notes over 4 months on the same psychological substrate; no
    existing hub covers this layer; cluster framing is consistent.
- type: wikilink_add
  params:
    note_a: 2_areas/work/reflection/...md
    note_b: 2_areas/personal/reflection/...md
  confidence: high
  brief_reasoning: |
    Both notes describe the same operating logic in different domains;
    structural overlap is high.
```

**Required fields per entry:** `type`, `params`, `confidence`,
`brief_reasoning`.

**Whitelisted `type` values** (canonical list mirrored in
`_system/scripts/_common.py::ACTION_HINT_TYPES`):

| Type | Required `params` | Typical lens emitter |
|---|---|---|
| `wikilink_add` | `note_a`, `note_b` (paths) | cross-domain-bridge |
| `hub_stub_create` | `suggested_slug`, `cited_notes` (list of paths) | knowledge-emergence |
| `open_thread_add` | `thread_title`, `cited_records` (list of paths) | stalled-thread |
| `decision_update_section` | `decision_note_path`, `update_reason` | decision-review |
| `principle_candidate_add` | `situation`, `observation`, `hypothesis`, `suggested_type`, `suggested_domain`, `source_record_count` | cognitive-model |

`principle_candidate_add` also accepts one OPTIONAL param: `dimension` — the
cognitive-model axis slug (SoT: `lenses/cognitive-model/prompt.md`). It is
persisted on the candidate line and lets `render_cognitive_model_hub.py` mark an
axis `evidenced` before promotion. Lenses other than `cognitive-model` omit it;
its absence is never an error.

A lens MAY emit any whitelisted type regardless of its «typical» role —
the table above is descriptive, not prescriptive. Non-whitelisted types
are not silently dropped: the resolver routes them into the
clarifications queue with a note that owner review is required (the
system learns about new types through owner approval, not lens fiat).

**`confidence` values:** `low` | `medium` | `high` — lens self-report.
**Advisory by default** — the resolver's LLM-judge weighs it as one signal among
many. **EXCEPT** where a per-class `insights-config.yaml` entry
(`{lens-id}__{action-type}__{confidence}`) pins it: that makes confidence a
**deterministic gate** for that class (e.g.
`cognitive-model__principle_candidate_add__high: auto` auto-applies high,
`__medium`/`__low: never_auto` always queue). So a lens author choosing a
confidence is choosing the auto/queue branch wherever such a config exists.

**`brief_reasoning`:** one paragraph, owner-readable. Explains why the
lens believes this proposal would be useful. The resolver reads this
verbatim when deciding; the owner reads it when reviewing. Be honest
about what is and isn't load-bearing in the cluster.

**Lenses that emit Action Hints:** `cross-domain-bridge`,
`knowledge-emergence`, `stalled-thread`, `decision-review`,
`global-navigator`, `cognitive-model`, `opportunity`. Each lens prompt carries its own
emission guidance (when to propose, what types to favour, how aggressive
to be).

**Lenses that do NOT emit Action Hints:** `weekly-insights`,
`energy-pattern`, `stated-vs-lived`. These are informational or
identity-level by design — auto-apply machinery would cross owner-
sovereignty lines.

**Identity-level exception — `principle_candidate_add`.** `cognitive-model`
is an identity-level lens yet DOES emit, because its one action type
(`principle_candidate_add`) only **appends to the high-recall
`principle-candidates.jsonl` review buffer** — it does not apply any change
to `0_constitution/` or SOUL. The candidate is stamped `origin: agent-lens`
(non-personal — inferred / batch-extracted), so the F.5 non-personal-origin
guard always routes it to owner review and never L2-auto-merges it onto an
existing principle. Promotion stays owner-gated (`/minder:mem:lint`
F.5), exactly like the in-the-moment capture hook. Appending-to-the-
review-buffer is therefore additive and does NOT cross the sovereignty
line that direct identity edits would. An identity-level lens may emit
`principle_candidate_add`; it must still NOT emit the content-mutating
types.

**Validator stance.** The Stage 3 validator does not parse the Action
Hints body. It accepts the trailer as opaque markdown. The resolver's
deterministic parser (`_common.parse_action_hints`) handles malformed
entries with drop-and-log semantics — the lens does not block on
invalid YAML.

**Self-restraint.** If a lens has nothing high-enough-confidence to
propose, omit the section. Filling Action Hints with low-confidence
filler dilutes the resolver's judgement and burns LLM cost on
guaranteed-queue items. Prefer silence over noise.
