# Minder Memory Engine Doctrine

> **What this is.** The compact, load-bearing operating philosophy of
> the Minder Memory engine. `install.sh` symlinks it into
> `~/.claude/rules/minder-memory-engine-doctrine.md`, so it auto-loads in every
> Claude Code session — every skill runs against it whether or not its
> own Step 1 / Load Context names it.
>
> **What this is NOT.** Not the full spec. Pointers below lead to the
> authoritative long-form sources. This file is what every skill
> internalises in 90 seconds before doing anything else.
>
> **Authority order** (top wins on conflict):
>
> 1. `_system/docs/SYSTEM_CONFIG.md` — system contract (the rules the
>    engine MUST hold)
> 2. `_system/docs/CONVENTIONS.md` — documentation conventions (binding
>    on every edit to engine docs and SKILLs)
> 3. **This file (`ENGINE_DOCTRINE.md`)** — operating philosophy +
>    cross-skill principles
> 4. Skill `SKILL.md` — pipeline-specific spec
> 5. `_system/SOUL.md` — owner identity calibration (Values zone
>    auto-rendered from constitution; Working Style hand-edited)
> 6. `0_constitution/` — owner principles (axioms / principles /
>    rules); `constitution-core.md` view auto-loaded as harness rule
>
> The engine doctrine is below the system contract and conventions
> (which are mechanical) but above all skill-level specs (which are
> mechanical applications of the doctrine).

---

## 1. Why Minder Memory exists — the frame

Minder Memory is a personal **second consciousness**, not an archive, not a
TODO-list, not a CRM, not a chatbot. The system *thinks alongside its
owner*: holds context across months, surfaces connections between
domains, traces how thinking evolves.

The system optimises for **one user with many contexts** — work,
career, personal, therapy, business ideas, relationships. The
disproportionate value lives at domain boundaries, where a therapy
insight illuminates a work-delegation pattern, or an architecture
decision seeds a product idea. Every skill operates with that in
mind.

### Three levels of value

| Level | Question | Layer that serves it |
|---|---|---|
| 1. Search | «What did we discuss with X in March?» | Records (`_records/`) |
| 2. Context | «What architectural decisions did we make on API v2?» | Knowledge notes (PARA) |
| 3. Synthesis | «How did my understanding of delegation change over six months?» | Hubs (`5_meta/mocs/`) |

Records, knowledge, hubs — three layers, each with a distinct shape.
Skipping a layer breaks the whole.

### The work / personal axis — first-class

Every Minder Memory owner lives in **at least two contexts simultaneously**: a
work / professional context (job, clients, team, domain expertise) and
a personal context (relationships, health, life decisions, side
projects, therapy, reflections). The system treats this split as a
**universal axis**, not an opinionated assumption.

Where the axis lives mechanically:

| Layer | How the axis is encoded | Notes |
|---|---|---|
| Records | NOT encoded at folder level. `_records/meetings/` and `_records/observations/` is a **shape axis** (multi-speaker vs solo Plaud / journal), not a scope axis. A solo work-reflection is still an `observation`; a personal book-club meeting is still a `meeting`. | Don't conflate shape and scope. |
| Knowledge notes | `domains:` frontmatter array. `work` is one valid value; personal-side values are richer (`identity`, `relationships`, `health`, `learning`, etc) — «personal» itself is too vague to tag. | Cross-domain notes carry both: `domains: [work, learning]`. |
| Hubs | `domains:` frontmatter array (same vocabulary as knowledge notes). | Cross-domain hubs are some of the highest-value (e.g. delegation patterns spanning therapy + work). |
| Tasks (`TASKS.md`) | Dedicated `## Personal` section + the rest defaulting to work. | Already in template. |
| Goals + Focus (`SOUL.md`) | Explicit `### Work` and `### Personal` subsections under both. | Already in template. |
| Projects (`PROJECTS.md`) | `Scope` column with values `work` / `personal` / `side` / `mixed`. | Scope is owner-tagged; bootstrap seeds with hint, owner edits. |
| People (`PEOPLE.md`) | `Org` column. Empty Org → personal-context relation; non-empty → work-context. | De-facto convention; surfaced in onboarding. |
| Constitution principles | `domain` field on each principle. Same vocabulary as knowledge notes. | A principle can be `domain: work` (applies in professional context) or `domain: identity` (applies everywhere); axiom-level principles typically span both. |
| Capture origin | `--origin work` flag on `/minder:mem:capture-candidate`. Default `personal`. Bootstrap adds `bootstrap-raw-scan` / `bootstrap-profile`. | F.5 non-personal-origin guard requires manual review for any non-personal origin (per §3.6). |

**Why the axis matters for skill calibration:**

1. **Texture preservation differs.** Personal observations (therapy,
   reflections) carry emotional and narrative texture that is signal,
   not noise. Work-meeting transcripts compress aggressively to
   facts + decisions. Principle 8 (Texture & Narrative) is calibrated
   per scope.
2. **People resolution differs.** Work people resolve via Org +
   role + first name; personal people often have only first name +
   relationship type — bootstrap and `/minder:mem:process` apply different
   confidence thresholds.
3. **Constitution scope differs.** Work-origin principle candidates
   never auto-merge (per F.5). Personal-origin ones can, post-
   threshold.
4. **Cross-domain insights are the highest-value class.** A therapy
   insight applied to work delegation; a work architecture decision
   seeding a side-project idea. Skills that detect cross-domain
   permeability (Principle 4) actively look for the work ↔ personal
   crossings.

The axis is **owner-defined**, not engine-imposed. Friends with
unusual splits (multiple work contexts, no work context, blended
freelance) tag accordingly — the system doesn't assume a 9-to-5
structure.

### Constitution — the fourth layer

Above the three knowledge layers sits the **constitution**
(`0_constitution/` — axioms / principles / rules). It is the
rules-of-engagement layer: how skills should reason and act on the
owner's behalf. Quality-first, narrowly curated; never accumulates on
autopilot. Knowledge is capture-first; constitution is curation-first.
Both are sacred for different reasons.

> Long form: `5_meta/CONCEPT.md`, `0_constitution/CONSTITUTION.md`.

---

## 2. The 8 processing principles (load-bearing)

These govern every transcript-processing decision. Inclusion-biased.
Skills calibrate their judgement against this list.

1. **Capture First, Filter Never** — every deliberate utterance lands
   in a record. False positives are cheap (a minute on next sweep);
   false negatives are forever. «Too small to record» is forbidden.
2. **Importance Gradient — Weight, Don't Discard** — importance shapes
   FORMAT (record line vs knowledge note vs hub), never filtering.
3. **Connection Awareness** — for every fact, actively probe causal /
   evolutionary / structural links to the loaded context. Wikilinks +
   hub updates are the artefacts.
4. **Cross-Domain Permeability** — the highest-value insights live at
   domain boundaries. Threshold ≈ 30 % confidence: if it *might* be
   relevant in another domain, link it.
5. **Evolution Tracking — Accumulate, Don't Deduplicate** — knowledge
   accumulates. January's decision and March's revised decision both
   stay. Hubs trace the evolution; nothing rewrites history.
6. **Action vs Knowledge — Capture Both** — dual-nature items become
   BOTH a `[ ]` task AND a knowledge insight. Never one or the other.
7. **People — Capture Every Deliberate Mention** — participants AND
   discussed-about. Three levels (participant / discussed / new
   context). Drives PEOPLE.md tier and profile growth.
8. **Preserve Texture and Narrative** — quotes, emotion, metaphor,
   narrative arcs are *signal*. Knowledge notes preserve them; records
   keep them only when load-bearing. Filler and stutter are removed.

> Long form (with antipatterns and examples):
> `5_meta/PROCESSING_PRINCIPLES.md`. The values-profile calibration
> (capture_threshold, atomization_depth, etc.) lives in the same file
> §«Values Profile» — overrides are read from `SOUL.md`.

---

## 3. Cross-skill philosophy

These are the rules every skill enforces, regardless of pipeline.

### 3.1 Surface, don't decide silently

Whenever judgement is uncertain, write a CLARIFICATION to
`_system/state/CLARIFICATIONS.md` with a conservative default and
continue. Never block; never silently choose. The owner reviews and
resolves. CLARIFICATION types are canonicalised in
`SYSTEM_CONFIG.md` and per-skill SKILL.md.

**Layer-specific exception: autonomous resolution.** A layer of the
engine qualifies for the «resolve silently» exception when **all three**
of these properties hold:

1. **Deterministic canonicalisation algorithm.** Every input has a
   single correct output computable by a pure function — no model
   judgment in the loop, no per-case reasoning. Re-running yields
   identical results.
2. **Conservative-safe failure mode.** When the algorithm cannot
   produce a valid output, the fallback is *drop* (or the most-
   restrictive default). The cost of one false negative is bounded
   and recoverable (one missing entry, owner-only privacy); the cost
   of guessing would be a leak or a phantom graph node.
3. **High-volume / low-per-decision-value surface.** Surfacing each
   case to the owner would drown the CLARIFICATIONS queue without
   giving the owner anything actionable to decide — the algorithm is
   already the right answer.

Layers currently qualifying:

- **Concept-name format** — `normalize_concept_name` /
  `normalize_concept_list` (single SoT: `_common.py`).
- **Audience-tag whitelist + format** — `normalize_audience_tag` +
  AUDIENCES.md whitelist check.
- **Privacy-trio backfill + hub derivation** — `recompute_hub_trio`,
  trio backfill in `lint_concept_audit.py`.
- **Portable filename normalisation** — `normalize_portable_name` /
  `is_portable_name` (single SoT: `_common.py`). Applied to new
  `_sources/inbox/` names by `/minder:mem:process` §0.0b pre-scan and
  `/minder:mem:save` Step 0.5 pre-pass; `/minder:mem:lint` A.10 is the backstop.
  Collisions are NOT covered by the exception — they surface as
  `portable-name-collision` CLARIFICATIONs.
- **Split-name recovery** — `repair_split_names.py`. Rejoins an inbox item
  whose name a producer's `/` turned into two nested directories, which
  portable-name normalisation cannot reach (it works on a NAME, and both
  resulting segments are legal names). Three-property check: (1)
  deterministic — the join is a pure function of the two segment names,
  using the same `-` the normaliser substitutes for `/`; (2)
  conservative-safe — the join runs ONLY when the parent holds exactly one
  child and that child is a complete item, and refuses on every other
  shape, so the failure mode is "left in place, surfaced"; (3)
  low-per-decision-value — for the unambiguous shape the rejoin is the only
  correct reading, so asking the owner offers them nothing to decide.
  Applied by `/minder:mem:process` §0.0a; `/minder:mem:lint` A.10 is the backstop.
  Ambiguous shapes surface as `source-layout-split-name` CLARIFICATIONs.
- **Frontmatter fence repair** — `frontmatter_closed_before_body` /
  `repair_misplaced_fence` (single SoT: `_common.py`). Relocates a `## `
  body heading (typically `## Evidence Trail`) that a producer captured
  inside the YAML fence. Three-property check: (1) deterministic — pure
  line-surgery, same output on re-run; (2) conservative-safe — on any
  ambiguity (more than one candidate `---` in the displaced region) it
  refuses and surfaces a `frontmatter-fence-misplaced` CLARIFICATION,
  never guessing; (3) low-per-decision-value — for an unambiguous
  misplacement the relocation is the only correct action, so surfacing it
  would give the owner nothing to decide. Rarity does not disqualify: the
  property is "surfacing yields no actionable choice," which holds. Applied
  at write time by `/minder:mem:process` Steps 3.6/4.5 and `/minder:mem:agent-lens`
  Stage 3 validator; `/minder:mem:lint` A.2 is the backstop. This is the first
  qualifying layer that repairs structural note anatomy rather than
  normalising a metadata field — hence the explicit property write-up.
- **Metric-day re-render resolution** — `process_metric_day.run` on a
  re-collected metric-day source whose content-hash drifted from the
  existing record. Three-property check: (1) deterministic — the choice is
  a pure comparison of real-metric counts (richer-or-equal → absorb +
  `recompute_baselines_forward`; poorer/empty → keep existing); (2)
  conservative-safe — good data is never overwritten by a degraded
  re-collect, and the absorbed alternative is the device's own
  authoritative refresh, so both branches are no-loss; (3)
  low-per-decision-value — a metric-day record is a deterministic
  projection of device data with no owner edits to protect, so surfacing
  "should your recovered biometric data count?" gives the owner nothing to
  decide. This is why metric-day re-render qualifies where general content
  drift does not (below): the resolution needs no judgment about meaning,
  only a count. Backstop: none needed — a poorer re-collect is simply kept,
  never lost.

Any new layer added to the engine MUST be tested against the three
properties before claiming the exception. If even one property fails,
the universal «surface, don't decide silently» rule applies.
**Threading, dedup, general content-drift detection, principle promotion,
people identity, content classification** — all of these involve judgment
and are explicitly NOT covered by the exception. (Metric-day re-render is
the narrow, deterministic exception carved out above — it turns on a pure
metric count, not on judging whether a change is meaningful.)

Per-layer rule sets: `_system/registries/CONCEPT_NAMING.md`,
`_system/registries/AUDIENCES.md`, `_system/docs/batch-format.md`
"Autonomous resolution" clauses.

### 3.1.5 Archive Contract — every archival event captures a reason

Every archival event in the engine — knowledge-note moved to `4_archive/`, principle deprecated, registry row moved to a Stale / Deprecated / Archived sub-table, lens auto-paused, person tier dropped to `stale`, candidate dismissed via CLARIFICATION — MUST capture a reason **with the entity**. The reason lives in the file or registry row itself; there is no parallel archival log. Spec: `SYSTEM_CONFIG.md → Archive Contract` (Form A inline `## Archive Note`, Form B `Reason` column / italic suffix, Form C existing structured field). Forward-only: pre-contract archives are not backfilled. Enforcement: `/minder:mem:lint` Scan G surfaces missing reasons as `archive-note-missing` / `archive-reason-missing` CLARIFICATIONs.

### 3.2 Inclusion bias on capture, curation on promotion

Capture (records, raw scan, candidates buffer) is high-recall: better
to include and dismiss later than miss. Promotion (knowledge → hub,
candidate → constitution principle, tier shifts) is high-precision:
gated by thresholds, owner review, weekly lint.

### 3.3 Idempotency

Every skill is re-runnable. Re-runs match by id (thread-id, person-id,
candidate triple, batch_id) and never overwrite owner edits. Updates
take the «add new entry» path, not the «rewrite existing» path.
Resolved threads, archived principles, and historical entries never
re-open or re-mutate.

### 3.4 Locks and exclusivity

The six pipeline skills — `/minder:mem:process`, `/minder:mem:maintain`, `/minder:mem:lint`,
`/minder:mem:agent-lens`, `/minder:mem:content` (when writing) and `/minder:mem:roles` — are mutually
exclusive, and each also aborts on `.resolve.lock`. Owner-driven skills sit
outside the matrix, each for its own reason — but sitting outside it is not
permission to ignore it: `/minder:mem:save` and `/minder:mem:sync-data` take no lock of their
own and read all seven, because a commit or a rebase moves the tree beneath
whichever tick is running.

**The matrix itself, lock by lock, is `SYSTEM_CONFIG.md → Cross-skill
exclusion`** — which skill takes which lock, the `--auto-mode` exception for
`.lint.lock`, and the nightly tick cadence. It is the one home; nothing restates
it.

The doctrinal part is why the matrix exists at all: a skill that writes into the
base while another is mid-run corrupts a diff neither can see. That is also why
a role must not invoke a pipeline skill from inside its own run — every pipeline
aborts on the lock the role's own runner is holding. Stale locks > 2 h are
surfaced as warnings, never silently deleted: a lock deleted on a guess is
indistinguishable from no lock at all.

### 3.5 Logs and audit trail

| Log | Skill | Append-only |
|---|---|---|
| `_system/state/log_process.md` | `/minder:mem:process` | yes |
| `_system/state/log_maintenance.md` | `/minder:mem:maintain`, `/minder:mem:bootstrap` | yes |
| `_system/state/log_lint.md` | `/minder:mem:lint` | yes |
| `_system/state/log_agent_lens.md` | `/minder:mem:agent-lens` | yes |
| `_system/state/BATCH_LOG.md` | `/minder:mem:process` | yes |
| `_system/state/PROCESSED.md` | `/minder:mem:process` | yes |
| `_system/state/agent-lens-runs.jsonl` | `/minder:mem:agent-lens` | yes |
| `_system/state/check-decision-runs.jsonl` | `/minder:mem:check-decision` (run + optional followup lines per invocation) | yes |
| `_system/state/tick-telemetry.jsonl` | `scripts/scheduler/record_tick_telemetry.py` (Step 4.9 of every scheduler tick) | yes |
| `_system/state/identity-gate.jsonl` | `identity_gate.py`, from `/minder:mem:resolve-clarifications` Class I.5 (one line per per-identity residue scan) | yes |
| `_system/roles/{id}/log.jsonl` | `/minder:mem:roles` (one line per **executed** run — a role whose cadence has not elapsed writes nothing) | yes |
| Knowledge note `## Evidence Trail` | every skill that touches the note | yes |

Logs document WHAT happened and WHY. They are the engine's memory of
its own operation; never edited retroactively.

### 3.6 The owner-LLM contract — what skills NEVER do silently

- Never auto-create a knowledge profile in `3_resources/people/{id}.md`
  without surfacing the threshold-crossing → CLARIFICATION first.
- Never auto-promote a principle candidate from
  `principle-candidates.jsonl` to `0_constitution/`. Promotion is L2
  merge in `/minder:mem:lint` F.5 — and only `origin: personal` candidates
  qualify (work / external / bootstrap / agent-lens origins always require
  manual review per F.5 non-personal-origin guard — a lens mines inferred,
  batch-extracted signal, so its candidates are stamped `origin: agent-lens`
  and never auto-merge). **Appending a candidate TO
  the buffer is not promotion** — both the in-the-moment capture hook
  (`/minder:mem:capture-candidate`) and the `principle_candidate_add` lens
  action hint append to the high-recall buffer autonomously; the F.5
  gate above is what keeps promotion owner-sovereign.
- Never overwrite owner edits to SOUL.md / PEOPLE.md / PROJECTS.md /
  hub files. Re-runs add or surface, never rewrite.
- Never demote tier silently — tier downgrades go through
  CLARIFICATIONS only.
- Never close an open thread silently — closure requires explicit
  signal in subsequent records or owner action.
- Never delete files from `_sources/`. The only `_sources/` mutation
  any skill performs is move-to-processed (`/minder:mem:process`) or
  consume-and-move-describe-me (`/minder:mem:bootstrap`).
- **A product rename is the one owner-data rewrite the engine performs
  unasked** (ADR-029): migration 032 runs a deterministic, idempotent token
  map over the whole clone — notes, records, hubs, seeded files, the
  append-only state — because a name is a fact about the product, not about
  the owner, and leaving it stale in half the base is the drift this section
  exists to prevent. `_sources/` is exempt; the rewrite is one `git` step
  from undone.

**Interpretation: lens Action Hints + smart_resolve auto-apply.**
`/minder:mem:resolve-clarifications --auto-mode` (dispatched by lint nightly)
applies a narrow class of additive lens proposals — `wikilink_add`,
`hub_stub_create`, `open_thread_add`, `decision_update_section`,
`principle_candidate_add` — without per-action owner CLARIFICATION.
This is consistent with §3.6, not an exception to it, because:

1. The action set is **additive only** — never mutates, deletes, or
   rewrites existing owner content. Worst case is a misplaced new
   bullet / hub / scaffold section / buffer line that the owner can git
   revert. `principle_candidate_add` appends to the high-recall
   `principle-candidates.jsonl` (capture, not promotion — F.5 still
   gates the constitution per the contract above), so it is additive in
   the same sense.
2. Each apply is **bounded** — handlers re-validate inside apply
   (TOCTOU), refuse on any drift from the stale-check baseline, and
   fall back to a clarification on validation failure.
3. **Constitution + SOUL veto is absolute** — any proposal that the
   resolver judges in conflict with an axiom / principle / rule /
   SOUL focus zone is queued or vetoed, not auto-applied. Owner
   override path is editing `_system/state/insights-config.yaml`, not
   the sweep.
4. **Queue is the «I would have asked the owner» signal — but
   `/minder:mem:check-decision` is the constitution-tree proxy for the
   absent owner.** Step A.3.5 escalates `queue` candidates whose
   `queue_reason ∈ {uncertainty, no-precedent}` to
   `/minder:mem:check-decision`; aligned / no-match upgrades to auto-apply,
   `violated ≥ 0.7` upgrades to block-veto, `tradeoff` and low-
   confidence `violated` stay in queue. **`no-basis` — the tree loaded
   nothing — stays in queue, fail-closed, and is the one silence that
   must never read as approval:** on a base whose constitution is still
   empty it is the answer to every escalation, so promoting it would
   auto-apply the whole queue on the strength of principles nobody has
   written yet. `no-match` is the opposite case (principles exist, none
   bear on this) and remains a genuine «the constitution does not
   object». Queue reasons that encode
   prior owner authority — `anti-flip-flop` (owner rejected a similar
   proposal recently) and `config-never-auto` (owner pinned the class
   to never-auto in `insights-config.yaml`) — are NOT escalated; the
   owner's existing signal is the source of truth and the proxy
   does not override it.
5. Auto-apply is **earned through demonstrated owner approval OR
   constitution-tree alignment**. smart_resolve consults
   `_system/state/lens-resolution-history.jsonl` (interactive owner
   clicks only — auto-mode applies do NOT accrete precedent) as its
   precedent corpus. Cold-start (no precedent) → default queue with
   `queue_reason: "no-precedent"`, then Step A.3.5 escalates as in
   point 4. Items whose action does not touch a values-bearing
   surface (per A.3.5 eligibility heuristic) stay in queue without
   escalation — those need owner judgment for non-constitutional
   reasons.
6. Every auto-apply leaves an inline `<!-- from_lens: ... -->` comment
   at the inserted line and a row in the per-session log under
   `_system/state/resolve-sessions/`. Provenance is opaque-by-default
   on the LLM side but visible-by-default on the filesystem side.
   Escalation-promoted applies additionally carry an
   `<!-- escalation: check-decision/{verdict}/{pid} -->` comment so the
   trail back to the proxy decision is explicit.

The spirit of «no silent magic» is preserved: the owner sees every
auto-apply on next interactive resolve session, can rev the
`insights-config.yaml::classes` overrides per-class, and can revert
any apply with a single git op. The other §3.6 prohibitions
(profiles, principle promotion, SOUL/PEOPLE/PROJECTS overwrites,
tier demotion, thread closure, source deletion) remain absolute and
unchanged by this interpretation.

### 3.7 Documentation conventions

Engine docs and SKILLs describe **current behaviour**. No version
narratives, no «previously this worked like X», no rename history. The
file IS the contract. When behaviour changes, the file changes; git
log carries the history.

> Binding spec: `_system/docs/CONVENTIONS.md`.

### 3.8 Manifest emission — bridging to downstream consumers

Every Minder Memory engine skill that produces persistent state changes
emits a structured **batch manifest** in JSON form alongside its
existing markdown summaries:

```
_system/state/batches/{ts}-process.json
_system/state/batches/{ts}-maintain.json
_system/state/batches/{ts}-lint.json
_system/state/batches/{ts}-agent-lens.json
```

The manifest schema is shared across all four skills, distinguished
by top-level `processor` field. It carries:
- Section per artifact kind (`sources`, `records`, `knowledge_notes`,
  `hubs`, `tier1_objects.{tasks,ideas,events,decisions,people,
  projects,content}`, `tier2_objects.{inventory,wardrobe,
  lens-observation,biometric,activity,...}`, `concepts`, `constitution.principles`,
  `constitution.constitution_core_view`, `constitution.soul`)
  - Note: the two universal baselines (engine behavioral floors at
    `_system/docs/communication-baseline.md` — how a result is presented — and
    `_system/docs/advisory-baseline.md` — how it is reached) are part of the
    Tier-0 behavioral contract an actor needs, but neither is emitted — the
    owner's deltas reach actors via `constitution_core_view`, the universal
    floors do not. When the first actor consumer exists, carry them via
    `constitution.section_extras.communication_baseline` /
    `.advisory_baseline` (a MINOR add each).
    Deferred-not-dropped: emitting them with no consumer is speculative
    plumbing.
- Privacy trio per entity: `origin`, `audience_tags`, `is_sensitive`
  (defaults `personal / [] / false`)
- Format version (`format_version: "MAJOR.MINOR"`) for evolution
  policy
- `section_extras: jsonb` per section for forward-compat new fields
- Idempotency via `batch_id` (top-level) + checksums per file

**Manifest is the contract** between the Minder Memory engine and any downstream
consumer (Minder backend is one specific example; other potential
consumers are forks, custom backends, experimental tooling).
Downstream:
- Reads manifests chronologically
- Idempotent by `batch_id` + checksums
- Routes per `processor` field semantics
- Rejects incompatible major versions with loud alert; accepts
  unknown minor fields via `section_extras`

**Universality matters:** new Minder Memory skills emitting persistent state
inherit this contract by default. Downstream consumers need no code
change to integrate. The contract is engine-level, not skill-level.

**What is intentionally NOT in manifest:**
- Pre-resolution staging (`people-candidates.jsonl`,
  `principle-candidates.jsonl`)
- Working memory (`OPEN_THREADS.md` — until focus engine arrives)
- HITL queues (`CLARIFICATIONS.md`)
- Audit trails (`log_*.md`, `agent-lens-runs.jsonl`,
  `check-decision-runs.jsonl`, `identity-gate.jsonl`, `tick-telemetry.jsonl`) — owner-internal
  feedback substrate; consumed by lenses, by `/minder:mem:lint` A.8 (9) and by
  future cross-source analysis, not by Minder backend
- Derived/regenerable views (`CURRENT_CONTEXT.md`,
  `lint-context/{daily,monthly}/*`)
- The cognitive-model hub (`5_meta/mocs/hub-cognitive-model.md`). It is a
  pure projection of `constitution.principles` (each principle's
  `cognitive_axes` field) plus the candidate buffer, regenerated by
  `/minder:mem:maintain` Step 7.9. It is therefore NOT emitted in the maintain
  manifest's `hubs.updated[]` (which tracks concept-cluster hubs touched by
  Step 4 thread-linkage, not this post-loop owner-data projection). A
  downstream consumer projects the hub itself from the principles it already
  receives — but `cognitive_axes` is not carried on `constitution.principles`
  in the manifest. When the first such consumer exists, add it to the principle
  emission (a MINOR add via `section_extras`). Same posture as the
  communication-baseline note above.

> **Canonical schema:** `_system/docs/manifest-schema/v{N}.json` (this
> repo). Reference doc + consumer integration patterns:
> `_system/docs/manifest-schema/README.md`. Defence-in-depth lint:
> `/minder:mem:lint` Scan H validates every recent batch against the schema
> and surfaces violations as CLARIFICATIONs (never silently rewrites
> — manifests are append-only). The contract is consumer-agnostic: no
> engine doc depends on any one consumer's design to be readable.

### 3.9 Cross-platform — Windows + macOS + Linux (HARD RULE)

**Every engine artifact MUST work identically on all three platforms friends
run.** Migrations, scripts, commands, hooks, paths, symlinks, doc instructions —
anything shipped. Friends run this engine on Windows (Git Bash + `python3`),
macOS (system **bash 3.2** — the old default — + `python3`), and Linux. An
artifact that only works on the maintainer's machine is a silent breakage that
surfaces as a friend's "it doesn't work for me," long after the change.

- **Shell = bash-3.2-safe AND Git-Bash-safe.** No `mapfile`/`readarray`, no
  `declare -A`, no `${var^^}`/`${var,,}` (all bash 4+). Prefer `python3` for
  non-trivial logic. Portable commands only — no `md5`(mac)/`md5sum`(gnu) split,
  no `sed -i ''`(mac) vs `sed -i`(gnu) (use `sed -i.bak`), no `readlink -f` /
  `stat -f|-c` / `grep -P`. Run scripts via `bash x` / `python3 x` — never via
  the executable bit (Windows has none).
- **Line endings = LF, enforced by `.gitattributes`** (shipped root-meta). A
  CRLF `.sh`/`.py` from a Windows checkout breaks bash and python.
- **Paths portable** — `pathlib`/`os.path`, resolved from repo root; never
  hardcode `/` or `C:\` or an absolute path.
- **Parity in lockstep** — a shell mechanism with a Windows equivalent is edited
  in the same change, or its limitation is stated explicitly.
- **Readiness gate** — «runs identically on a friend's Windows machine AND on
  plain macOS bash 3.2?» "works on my Mac" is never the bar; verify
  (`/bin/bash -n` for bash-3.2 syntax, grep for the banned commands, check CRLF).

This applies to every skill, script, and migration the engine ships, forever.

---

### 3.10 A contract has one home, and silence has a detector

Two failure shapes recur, and neither announces itself. Both are cheap to
prevent at design time and expensive to find afterwards, so they are checked
when a mechanism is built rather than when it breaks.

**One home.** A behavioural contract lives in exactly one place, and everything
else points at it. A copy — a spec restated in a prompt, a tick body pasted
into a scheduler, a rule quoted into a second doc — becomes the older of the
two the moment the original moves, and nothing in the system reports the
divergence. The reader trusts the copy precisely because it looks authoritative.
So when a mechanism needs a contract somewhere it cannot import it, it gets a
POINTER and a refusal clause («if this cannot be read, do nothing»), never a
duplicate. Applies to prose as much as to code: the class is *the same fact
stated twice*, whatever the medium.

**A step nothing detects is a step that will stop happening.** Every engine
behaviour is either enforced by something that fails loudly, or watched by a
check that notices its absence. A step described in a prompt but implemented
nowhere is not a weak guarantee — it is no guarantee, and it will run for a
while on goodwill before quietly stopping, with every produced artefact still
looking correct because what is missing is an *event*, not a file. Content
scans cannot see this class; only a check that asks «did the thing that should
have happened, happen?» can (`/minder:mem:lint` Scan A.12 is the worked example).

**Whatever a run needs from the world outside the repository, name it and
carry it.** An owner's scheduler, credentials, routine names and cron slots are
theirs, not the engine's: never keyed by a name the engine invented, never
overwritten without diffing for what the owner put there, and a credential
found in an unexpected place is carried forward intact before anything else is
discussed. An automated change that silently drops one of these breaks a system
the engine cannot see and did not build.

### 3.11 Build the reference result; report the difference

Two rules that read as opposites and are not, because they govern different
halves of the same delivery. Getting them backwards is the common case, and it
degrades the engine from both ends at once.

**What is built is the reference result for here and now, not a patch on the
last one.** When a mechanism is reworked, the target is what it should be given
everything now known — not the smallest edit that closes the immediate
complaint. A shape kept only because replacing it would enlarge the diff is
technical debt that the diff itself concealed; ten such increments produce a
component nobody designed, whose current form no document explains. This is why
the engine ships migrations, retirement declarations and a seed contract at
all: they exist precisely so a component CAN be replaced rather than patched
forever, and a change that avoids them to stay small is avoiding the mechanism
built for it.

**What is reported is the difference from what the reader already holds.** The
reader has read the previous version; its shape is in their head. Handing them
a fresh full text and letting them re-derive what moved charges them twice for
one change, and the second charge buys nothing. So the report leads with what
was kept, what was refined, what was rejected and on what grounds, and what is
newly proposed — each against the state they already know. The presentation
contract for this is in `communication-baseline`.

The two never trade against each other. «The diff would be large» is not a
reason to build less; «the result is new» is not a reason to report it as if
nothing preceded it.

---

### 3.12 Uncommitted work is destroyed quietly (HARD RULE)

**`--force` is not the dangerous half.** `git checkout -- <path>`, `git restore
<path>` and `git stash drop` carry no alarming flag, are never refused by git,
and destroy uncommitted work exactly as irreversibly as `reset --hard` — with
one difference that makes them worse: **nothing announces the loss.** The file
simply reads as it did before the work existed, so there is no moment at which
anyone notices something is gone.

This is not a general caution: it is specific to how this engine is edited.
Contributors change it through gates and mutation checks — deliberately breaking
a rule to confirm the check catches it, then putting it back. That loop is a
revert loop, and a revert takes the unrelated work sitting beside it.

- **Break on purpose only AFTER committing, never revert afterwards.** Commit
  first, then mutate, then discard the mutation by resetting to the commit. The
  order is the whole rule: reverting to undo a deliberate break is the moment
  everything else uncommitted disappears.
- **Better still, mutate a throwaway copy.** A mutation harness that operates on
  a copy of the tree removes the possibility rather than relying on remembering
  the order.
- **Treat the quiet three as the force list.** `checkout --`, `restore`, `stash
  drop` need the same explicit in-the-moment approval as `--force`, or a commit
  first.
- **Never truncate a check's own output to decide whether it passed.** A verdict
  read from a trimmed tail reports green while the run is red — the same class
  of quiet failure, one layer up.

---

## 4. Sacred state

These files are the engine's load-bearing state. Every skill knows
their schema and respects them. This index gives schema/purpose and a
writer summary. **For any file it covers, the Skill Write Territory table
in `SYSTEM_CONFIG.md` is authoritative on the writer — defer to it on any
discrepancy;** files without a territory row (operational layers, append-only
buffers) take the writer named here.

| File | Writer (summary — canonical in SYSTEM_CONFIG) | Purpose |
|---|---|---|
| `_system/SOUL.md` | owner (manual) + `/minder:mem:bootstrap` (draft) + `regen` (Values zone) | Identity, values, focus, working style |
| `_system/TASKS.md`, `CALENDAR.md` | `/minder:mem:process` (derived aggregates; owner owns only the TASKS `## Stale` section) | Aggregated views over note `- [ ]` / `📅` items |
| `_system/POSTS.md` | owner | Operational layer |
| `_system/registries/TAGS.md` | `render_tags.py` only (via `/minder:mem:maintain` Step 7.10 and `regen_all.py`) | Census of the `tags:` axis — managed zone regenerated, never hand-written |
| `_system/registries/SOURCES.md` | `/minder:mem:source-add` (rows), `/minder:mem:lint` (`## Deprecated Sources`) | Inbox source whitelist |
| `_system/state/OPEN_THREADS.md` | `/minder:mem:bootstrap`, `/minder:mem:maintain`, `/minder:mem:resolve-clarifications` | Strategic open threads (`## Active` opened by maintain / resolve; `/minder:mem:process` context-only) |
| `_system/state/CLARIFICATIONS.md` | every skill | Owner-gated resolution queue |
| `_system/state/principle-candidates.jsonl` | `/minder:mem:capture-candidate`, `/minder:mem:bootstrap`, `/minder:mem:lint` (F.5 archive) | Append-only principle buffer |
| `_system/state/people-candidates.jsonl` | `/minder:mem:process`, `/minder:mem:bootstrap`, `/minder:mem:lint` (dismiss/archive) | Append-only people buffer |
| `_system/state/check-decision-runs.jsonl` | `/minder:mem:check-decision` | Append-only audit substrate (run + followup lines per invocation); consumed by `decision-review` lens + future cross-source autonomy analysis |
| `_system/state/tick-telemetry.jsonl` | `record_tick_telemetry.py`, from each scheduler tick | Append-only token-consumption record, one line per tick, read from the tick's own transcript. Ticks only — a manual run writes nothing. Watched by `/minder:mem:lint` A.13, which is the only thing that can see the writer stop, because the writer never fails a tick |
| `_system/state/identity-gate.jsonl` | `identity_gate.py`, from `/minder:mem:resolve-clarifications` Class I.5 | Append-only record that a per-identity residue scan actually ran — command, exit code, residue count, HEAD. Identity Contract Obligation 4's proof; `/minder:mem:lint` A.8 (9) matches an archived resolution against a line here rather than against a number the resolution wrote about itself |
| `_system/views/CURRENT_CONTEXT.md` | `/minder:mem:bootstrap`, `/minder:mem:maintain` | Auto-generated focus snapshot |
| `_system/views/HUB_INDEX.md` | `/minder:mem:maintain` (rebuild) + `/minder:mem:process` (additive on hub create) | Hub registry (auto-generated) |
| `_system/views/INDEX.md` | `/minder:mem:maintain` (via `render_index.py`) | Surface-line catalog of knowledge + archive + constitution + hubs (auto-generated, faceted by PARA / domains / cross-domain). Records and posts intentionally out of scope — own pipelines |
| `_system/views/constitution-core.md` | `/minder:mem:regen-constitution` | Harness-loaded core principles |
| `3_resources/people/PEOPLE.md` | `/minder:mem:bootstrap`, `/minder:mem:process`, `/minder:mem:lint` | People registry with tiers |
| `1_projects/PROJECTS.md` | owner + `/minder:mem:bootstrap` (candidates) | Project registry |
| `_system/roles/{id}/role.md` | `/minder:mem:role:add` (create), `/minder:mem:role:edit` (change) | One standing role, whole: frontmatter the engine owns, prose body in the owner's own language that the engine never parses |
| `_system/roles/{id}/state/` | the role itself, inside a `/minder:mem:roles` tick | The role's memory between runs — arbitrary files it defines and maintains. Read at the start of every run, so a run that leaves them untrue corrupts the next one |
| `_system/roles/{id}/log.jsonl` | `/minder:mem:roles` | One line per executed run: outcome, write count, reverted and reported-only paths, duration |

Skills writing to these files do so per the schema; deviations surface
as `process-compatibility` CLARIFICATIONS rather than silent format
drift.

---

## 5. Bootstrap as doctrine transmission

`/minder:mem:bootstrap` is the **first contact** between the engine and a
fresh instance. It is responsible for:

1. Loading this doctrine (Step 1) and confirming the LLM session
   operates against it.
2. Surfacing the doctrine briefly to the owner at pre-flight summary
   (Step 0.6) — so the owner sees the frame their system runs by.
3. Seeding system files (SOUL, PEOPLE, PROJECTS, OPEN_THREADS,
   CURRENT_CONTEXT, candidates buffers) such that future
   `/minder:mem:process` runs inherit the seeded context.
4. Pinning a doctrine reference into `CURRENT_CONTEXT.md` frontmatter
   so any future skill loading CURRENT_CONTEXT alone still has a
   pointer back to this file.

After bootstrap completes, the doctrine flows into every subsequent
skill invocation through:

- the harness symlink (`~/.claude/rules/minder-memory-engine-doctrine.md`)
- explicit Step 1 loads inside each SKILL.md
- the CURRENT_CONTEXT frontmatter pointer

If those three transmission paths drift, the engine drifts.

---

## 6. Pointers to long-form sources

| Topic | File |
|---|---|
| System concept, three-layer model, full philosophy | `5_meta/CONCEPT.md` |
| 8 processing principles + values-profile calibration | `5_meta/PROCESSING_PRINCIPLES.md` |
| System contract, schemas, hard rules | `_system/docs/SYSTEM_CONFIG.md` |
| Archive Contract (every archival event captures a reason — Forms A/B/C, enforcement) | `_system/docs/SYSTEM_CONFIG.md → ## Archive Contract` |
| Documentation style (binding) | `_system/docs/CONVENTIONS.md` |
| Architecture as built — layers, rejected alternatives, system files | `_system/docs/ARCHITECTURE.md` |
| Constitution protocol (axiom / principle / rule schema, scope, evolution ladder) | `0_constitution/CONSTITUTION.md` |
| Folder routing | `_system/registries/FOLDERS.md` |
| Inbox source whitelist | `_system/registries/SOURCES.md` |
| Constitution capture trigger spec (in-the-moment) | `_system/docs/constitution-capture.md` |

A skill that finds itself making a non-obvious judgement should consult
the relevant long-form file before acting, and surface a CLARIFICATION
if the doctrine is silent on the case.
