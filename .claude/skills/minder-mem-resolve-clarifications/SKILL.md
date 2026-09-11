---
name: minder:mem:resolve-clarifications
description: >
  Interactive facilitator for the owner's CLARIFICATIONS queue. Pre-syncs
  via /minder:mem:sync-data so the queue reflects state from all devices, then
  loads open items, clusters by Type, presents one theme at a time as a
  numbered batch (≤5 items, adaptive — 3 for heavy types, 5 for light),
  reminds full situation + verbatim quotes already stored in the file,
  pre-checks values-bearing items against the constitution, proposes
  resolution with labelled options, applies confirmed actions (silent
  for archival ops, diff-first for content edits), archives resolved
  items and re-prioritises deferred ones. After resolutions, refreshes
  derived views (/minder:mem:regen-constitution if principle accepts; /minder:mem:maintain
  if registries / hubs touched) and reminds owner to run /minder:mem:save when
  the working tree is dirty. Manual, owner-driven —
  never dumps the whole queue, never asks the owner to recall meeting
  context unaided.
disable-model-invocation: false
---

# /minder:mem:resolve-clarifications — Interactive Clarifications Facilitator

The owner's queue at `_system/state/CLARIFICATIONS.md` accumulates
ambiguities surfaced by producer skills. Reviewing it as a flat list is
high-friction: the owner has no fresh context for the underlying meeting,
items mix trivial (people-bare-name) with values-loaded (org-tension,
principle-candidate), and resolution mechanics differ per Type.

This skill turns review into a guided conversation: one theme per round,
numbered questions, full context reminded inline, decisions applied
mechanically, queue cleaned after.

**Working directory:** the zettelkasten base. Every path and every `python3`
command in this file is written relative to it.

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md` — файл описывает current behavior без
version/phase/rename-history narratives.

## Arguments

`$ARGUMENTS` supports:
- `--theme <type>` — pick a specific Type cluster directly, skip the menu
- `--max <N>` — override adaptive batch size (default: 3 heavy / 5 light)
- `--dry-run` — render the round but do not apply any resolution
- `--no-constitution` — skip constitution lookup even for values-bearing items
- `--continue` — after closing one round, immediately offer the next theme
- `--no-sync` — skip Step 0 pre-sync (offline review, known-current state)
- `--no-refresh` — skip Step 9 post-resolution refresh (`/minder:mem:regen-constitution`,
  `/minder:mem:maintain`); owner promises to run them manually
- `--no-save` — skip the Step 9.4 save reminder (commit later by hand)
- `--no-extraction` — skip Step 6.5 knowledge extraction pass entirely
  (no proposals surfaced; resolutions applied as usual). Use when owner
  wants pure queue review without follow-up artefact creation
- `--auto-mode` — non-interactive entry point dispatched by
  `/minder:mem:lint` Step 7.5 inline (the lint nightly tick is the timer;
  resolve is the engine). Runs Step A (lens hint ingestion + smart
  curation + auto-resolve sweep) and exits silently. Skips Step 0
  pre-sync (the dispatching scheduler tick already synced), skips
  theme menu / round / save reminder. Also skips Class I entirely —
  identity change is an owner decision and never happens in a
  non-interactive run. Residue clarifications stay
  queued for owner; auto-applied actions write to the session log
  under `_system/state/resolve-sessions/`. The most quality-sensitive
  isolation — agent-lens vs resolve — IS preserved at the scheduler
  level: lens runs are a separate scheduler tick, so the agent that
  judges proposals in A.2/A.3 has not just produced lens body output.

---

## Step 0: Pre-sync

**Skip entirely under `--auto-mode`.** The dispatching nightly chain
(scheduler → `/minder:mem:sync-data` → `/minder:mem:lint` → resolve) already synced
as its first step, AND lint has by now written invariant-scan
autofixes that leave the working tree dirty — re-running sync inside
auto-mode would either redundantly walk a clean tree or, more likely,
abort on the dirty tree and break the nightly chain. The auto-mode
caller (lint) owns sync; resolve trusts it.

Under interactive mode (`/minder:mem:resolve-clarifications` invoked by
owner), invoke `/minder:mem:sync-data` inline. Owner may be working from a
multi-device setup (phone captures, server processing, laptop A vs
laptop B); reviewing a stale CLARIFICATIONS queue wastes the owner's
attention on items already resolved elsewhere.

Behaviour:
- Up-to-date or no `origin` → continue silently to the lock step.
- Pulled commits → report one-line recap («синхронизировался: pulled
  N commits, K new clarifications») then continue.
- Working tree dirty → `/minder:mem:sync-data` aborts with its own message;
  surface it verbatim to the owner and exit (owner runs `/minder:mem:save`
  first, then re-invokes this skill).
- Conflict during rebase → `/minder:mem:sync-data` aborts and prints recovery
  instructions; surface verbatim and exit.
- Unsupported in `--dry-run` mode → still run sync (read-mostly; only
  effect is moving local HEAD), since stale data poisons the dry-run
  preview too.

Skip the sync only when `--no-sync` is passed (escape hatch for offline
review or known-current state). The skill never auto-syncs after Step 0
— the owner's session works against the snapshot taken here.

## Concurrency Lock

This skill writes to CLARIFICATIONS.md and may edit profiles / records.
Producer skills (`/minder:mem:process`, `/minder:mem:lint`, `/minder:mem:maintain`) write to
the same files. Mutual exclusion required.

Before starting, read every pipeline lock under `_sources/` and abort on any,
naming the skill that holds it. The set is owned whole by
`_system/docs/SYSTEM_CONFIG.md` → «Cross-skill exclusion» — read it there
rather than keeping a second copy that drifts.

**`--auto-mode` exception for `.lint.lock`.** Auto-mode is dispatched
by `/minder:mem:lint` Step 7.5; lint holds `.lint.lock` for the duration of
the dispatch. Treating that lock as «competitor» would deadlock the
nightly chain. Under `--auto-mode` only, presence of `.lint.lock` is
proof the dispatcher is alive — proceed with resolve work, do not
abort. Every OTHER pipeline lock stays competitive (lint already
cleared those at its own Step 0.1; if any appears here, something has
gone genuinely wrong — abort silently and let the next nightly tick
retry). Auto-mode also skips the Step 0 pre-sync and never writes
`lens-resolution-history.jsonl`.

Interactive mode keeps the full check with no exception; the
owner-driven session has no dispatcher above it.

1. Create `_sources/.resolve.lock` with `{ISO timestamp} — {session info}`
2. Delete it on every exit path (normal, error, abort, early exit)
3. Stale lock (>2h) — warn and offer to clear

Views (`constitution-core.md`, `CURRENT_CONTEXT.md`, etc.) are read as-is
during Steps 1–7. Regeneration is deferred to Step 9 (post-resolution
refresh) and runs only when this session's resolutions actually touched
the underlying source of truth.

---

## Step 1: Load Context

Read these system files (in parallel where possible). Default-on for
all rounds, regardless of Type — owner context is a hard prerequisite
for sane hypothesis forming, not a values-only concern.

| File | Why |
|---|---|
| `_system/docs/ENGINE_DOCTRINE.md` | Operating philosophy, owner-LLM contract |
| `_system/docs/SYSTEM_CONFIG.md` | CLARIFICATIONS schema, note formats |
| `_system/views/constitution-core.md` | Tier-1 axioms — background frame for every hypothesis; also carries the owner's presentation-delta principles (ai-interaction) used for reader alignment in Step 5 |
| `_system/docs/communication-baseline.md` | Universal presentation floor — how to shape the questions the owner reads (Step 5 reader alignment) |
| `_system/SOUL.md` | Identity, focus, working style — drives hypothesis defaults AND reader alignment (how this owner takes in information) |
| `3_resources/people/PEOPLE.md` | Mandatory for person-identity / people-bare-name resolution |
| `1_projects/PROJECTS.md` | Mandatory for project-identity |

Conditional / on-demand (load only when round contains relevant Types):

| File | Trigger |
|---|---|
| `_system/state/OPEN_THREADS.md` | `thread-closure-suggested` items |
| `_system/views/HUB_INDEX.md` | `thread-closure-suggested`, `cross-domain-link`, `hub-stale-vs-material` |
| `_system/views/INDEX.md` | `index-missing`, `index-stale`, `index-frontmatter-malformed` (heartbeat — usually resolves by running `/minder:mem:maintain`) |
| `_system/views/CURRENT_CONTEXT.md` | values-bearing rounds (org-tension, decisions) |
| `5_meta/PROCESSING_PRINCIPLES.md` | `principle-candidate-batch` rounds |
| `_system/scripts/query_constitution.py --domains <d>` | escalate when constitution-core lacks the principle needed to form a confident hypothesis (typically values-bearing items) |

**Concept and audience CLARIFICATIONs are never raised by the engine.**
The autonomous-resolution layer (`/minder:mem:lint` Scan A.7 +
`_system/scripts/lint_concept_audit.py` + `_common.py` normalisers)
auto-fixes or silent-drops every concept/audience format issue. This
skill therefore does NOT receive `concept-format-mismatch`,
`concept-type-prefix-in-name`, `concept-name-too-long`,
`audience-tag-unknown`, `audience-tag-reserved-conflict`, or
`audience-tag-format-mismatch` items — they don't exist as
CLARIFICATIONs. The Extensions table in `_system/registries/AUDIENCES.md`
remains owner-curated outside the pipeline; if owner wants to widen the
audience whitelist they edit AUDIENCES.md directly, no resolve flow.

**Context-only invariant.** Files in this section are read but never
written by this skill. The only writes go through the «Output Files
Touched» list in Step 7.

**Constitution as proposal accelerator, not validation gate.** The point
of loading the constitution is to let the skill pre-form a confident
hypothesis (option `a`) so the owner can one-click confirm instead of
recalling values from memory. Missing a relevant principle is not a
safety failure — at worst the skill proposes a weaker `a` and the owner
overrides. So default to cheap (`constitution-core.md` always-on); only
escalate to `query_constitution.py --domains <d>` when forming the
hypothesis genuinely needs the deeper tree (typically values-bearing
items). Skipped entirely under `--no-constitution`.

---

## Step A: Lens Action Hints + Smart-Resolve Sweep

### Biometric rate limiting + new action types

When biometric pipeline is active (any per-device namespace under
`_records/biometric/*/` non-empty), the smart-resolve sweep applies
anti-DDoS calibration on biometric-origin action hints:

- Read `_system/state/insights-config.yaml::biometric.biometric_max_hints_per_week`
  (default 3 if absent).
- For the current ISO week, count biometric-origin hints already
  surfaced via this sweep (parse session logs under
  `_system/state/resolve-sessions/` for the current week or use the
  CLARIFICATIONS queue's biometric-typed items).
- If exceeded, top-N by effect_size win; the remainder defer to next
  week (drop with a one-line «rate-limited» log entry, do NOT queue).
- Effect-size proxy: for `threshold_tune_proposal`, use
  `|observed - expected| / expected` (calibration drift factor); for
  `wikilink_add` from biometric lenses, use the cited correlation's r
  if available, else 0.5.

New CLARIFICATION types and action types added by biometric pipeline:

| Type | Class | Apply mechanism |
|---|---|---|
| `biometric-baseline-cold-start` | informational | One-time per source on its first metric-day run; resolution = dismiss with «expected cold-start» note |
| `biometric-threshold-drift` | C (proposal) | `threshold_tune_proposal` action — writes proposed σ to `biometric_thresholds.yaml` |
| `biometric-affect-lexicon-empty` | review | Owner audits lexicon; may add `affect_lexicon.local.yaml` overlay entries |

Action handlers `threshold_tune_proposal` and
`metric_record_rerender_apply` live in
`_system/scripts/lens_action_handlers.py` and follow the existing
two-phase contract (validate → apply with TOCTOU defence). The
`/minder:mem:process` metric-day branch resolves re-render drift autonomously by
richness (it does not emit `metric-record-rerender`); the
`metric_record_rerender_apply` handler is retained to resolve any
`metric-record-rerender` items present in the queue — owner picks
`skip` / `append-update` / `recompute-baselines-forward`. Per
ENGINE_DOCTRINE §3.6 spirit: no silent magic — every apply leaves an
inline `<!-- from_lens: ... -->` comment + session log entry; owner
sees the trail on the next interactive resolve session.

This step is the engine that turns implicit lens proposals into either
auto-applied additions or queued clarifications with rich reasoning.
Runs in **both** modes:

- `--auto-mode` (called by `/minder:mem:lint` Pass 2) — Step A is the entire
  body of work. Skip directly from here to Step A.4 (session log
  flush) and the lock-release cleanup.
- interactive — Step A pre-curates. Steps 2-9 then continue against a
  queue that has been triaged, deduplicated, and annotated with
  smart_resolve reasoning.

The intelligence here is LLM-driven «human-with-experience» reasoning,
not deterministic threshold counting. The whole purpose is approximating
how the experienced owner would decide, given their values, declared
focus, and prior reasoning available as precedent.

Insurance during the sweep: if any sub-step fails (LLM error, handler
crash, file lock), recover gracefully — never abort the whole skill. A
crashed handler falls back to a clarification («attempted auto-apply,
validation failed because X — owner review»). A crashed sweep means
items stay in their pre-sweep state; the next nightly tick retries.

**Per-step failure rules (explicit, not «recover gracefully»):**

| Failure | Recovery |
|---|---|
| Step A.0 — both live + template missing | Use built-in defaults (`posture: balanced`, `uncertainty_default: queue`). Log to session skipped-log. Continue. |
| Step A.1 — `_system/agent-lens/` walk fails (FS error) | Skip ingestion entirely. Set `last-resolve-tick.txt` to current ts (so next tick doesn't reprocess the same window). Log error to session. Continue to A.2 with empty hint set. |
| Step A.1 — individual hint fails stale-check | Drop that hint with reason; log to «Skipped lens hints». Other hints proceed. |
| Step A.2 — LLM error / timeout / malformed JSON output | Pass all parsed hints through unchanged (no curation, no coalescing). Log to session. Continue to A.3 with raw + open clarifications. |
| Step A.3 — LLM error / timeout / malformed JSON output | NO auto-applies this tick. NO queue annotations. All items remain in their pre-sweep state (lens hints stay in their output files; clarifications unchanged). Log error. Update `last-resolve-tick.txt` ANYWAY (avoids reprocessing storm) and exit Step A. |
| Step A.3 — handler validation failure on apply | Demote to `lens-action-apply-failed` clarification (canonical Type per SYSTEM_CONFIG) with handler's reason text. Other auto-applies in the batch continue independently — apply is per-item atomic, not all-or-nothing. |
| Step A.4 — session log write fails | Best-effort: write to `_system/state/resolve-sessions/{date}-{sid}.partial.md` with whatever the accumulator holds. Log error. Continue. |

The principle: **never poison the queue with half-done work, never
rewrite owner-curated state, never silently drop a hint**. The
session log is the audit trail of choice — every drop / failure /
recovery has a row.

### Step A.0 — One-shot bootstrap (idempotent)

Two checks before A.1; both noop on subsequent runs.

1. **insights-config seed.** If `_system/state/insights-config.yaml`
   does NOT exist, copy `_system/state/insights-config.yaml.template`
   to that path verbatim (no transformation). The live file is owner-
   mutable thereafter — never rewritten. If the template ALSO is
   missing (broken clone), proceed with built-in defaults
   (`posture: balanced`, `uncertainty_default: queue`, no per-class
   overrides) and log a single warning to the session accumulator's
   skipped-log; do not block the sweep.
2. **Sessions dir seed.** Ensure `_system/state/resolve-sessions/`
   exists (mkdir -p). The session log writer creates it lazily, but
   doing it here keeps Step A.4's flush path branchless.

### Step A.1 — Ingest fresh Action Hints (deterministic)

Scope:

1. Determine the «since» marker. Read `_system/state/last-resolve-tick.txt`
   if present; else fall back to «files modified in the last 24h». Update
   the marker to «now» at the END of Step A (only after the sweep
   completes; failure leaves the old marker so next run retries).
2. Walk `_system/agent-lens/{lens-id}/{date}.md` for files modified
   since the marker. Parse each via
   `_system/scripts/_common.py::parse_action_hints(body)`. Drops are
   logged to the session accumulator («Skipped lens hints») not to
   CLARIFICATIONS — malformed YAML is the lens's problem, surfaced via
   Stage 3 validator separately.
3. For every parsed `ActionHint`, run the deterministic stale pre-check
   via `lens_action_handlers.VALIDATORS[hint.type](hint.params)`. If
   validation fails (cited path missing, target already exists,
   wikilink already bidirectional, etc.) — drop the hint with reason in
   the «Skipped lens hints» section. The lens's body observation still
   stands; only the hint is dropped.
4. Carry the surviving hints forward to Step A.2 with provenance label
   `{lens-id}/{date}` derived from the source file path.

This step is pure plumbing — no LLM call, no judgement. Runs even when
`--auto-mode` is off (interactive mode benefits from the same triage).

### Step A.2 — Smart Curation (LLM)

A single Opus-grade LLM call. System prompt = curator role, framed as
«as the owner would triage if sitting down right now to review».

**System inputs to load (read once, cache for Step A.3):**

| File | Why |
|---|---|
| `_system/views/constitution-core.md` (always) + `0_constitution/{axiom,principle,rule}/*.md` | Full tree for veto + alignment reasoning |
| `_system/SOUL.md` | Identity, focus, working style |
| `3_resources/people/PEOPLE.md` | Relationship map (some hints reference people) |
| `1_projects/PROJECTS.md` | Active projects |
| `_system/agent-lens/weekly-insights/*.md` (newest 4 only) | Recent narrative context |
| `_system/state/CLARIFICATIONS.md` (open + last 30d resolved) | Existing queue + recent resolution context |
| `_system/state/insights-config.yaml` (or `.template` if missing) | Per-class overrides + posture |
| Recent git log paths (last 7 days, paths only) | Detect owner-edited areas to prefer / avoid |

**User-message inputs:**

- All surviving lens hints from Step A.1 (structured: lens, type,
  params, confidence, brief_reasoning).
- All open clarifications (raw blocks).

**LLM output (structured JSON):**

For each hint: one of
- `keep` — survive into Step A.3 with extracted `salient_features`
  (cluster_tightness, time_span_months, cross_para, existing_hub_overlap,
  domain_axis, cited_count, owner_recent_edits_overlap, ...).
- `drop` — with brief reason (hint conflicts with constitution, hint
  duplicates a recently-resolved clarification, hint touches an
  area the owner edited yesterday in a way that contradicts).
- `coalesce-with-{ids}` — merge with one or more other hints / open
  clarifications into a single combined entry with multiple options.

For each open clarification: pass-through unchanged unless the LLM
detects it should coalesce with a fresh hint.

**After the LLM:**

- Coalesced groups become single rows. The combined item carries an
  `options:` payload listing each branch.
- Dropped hints log to «Skipped lens hints (curator)» in the session
  accumulator.
- Kept hints proceed to Step A.3 carrying their `salient_features`.

**Posture awareness.** `insights-config.yaml::reasoning.posture`
(`conservative` / `balanced` / `aggressive`) tunes the curator's drop
aggressiveness. `balanced` is default. Owner overrides in the config
file directly; this skill never edits it.

### Step A.3 — Auto-resolve Sweep (LLM)

A single Opus-grade LLM call. System prompt = experienced-owner role:
«given full context, would I — knowing what I know about my values,
focus, and prior reasoning — approve this NOW?»

**System inputs (in addition to A.2's set):**

- Last 10 session logs from `_system/state/resolve-sessions/` newest-
  first — full reasoning narratives, not just counts.
- All entries in `_system/state/lens-resolution-history.jsonl` (or the
  most recent 200 if the file ever grows past that). The LLM uses
  history as PRECEDENT CORPUS: «when I approved a similar proposal
  before, what reasoning did I give? Does the current case fit?» —
  not as deterministic threshold counting.

**User-message inputs:**

- All clarifications surviving Step A.2 (existing + curated).

**LLM output per item (structured):**

```json
{
  "item_ref": "<id or anchor>",
  "decision": "auto-apply" | "queue" | "block-veto",
  "reasoning": "<1-3 sentences referencing specific principle / past
                session / SOUL focus when relevant>",
  "action": { "type": "wikilink_add", "params": {...} }  // present on `queue` AND `auto-apply` (queue carries the would-be action so Step A.3.5 can escalate it)
  "queue_reason": "uncertainty" | "anti-flip-flop" | "no-precedent" | "config-never-auto" | "other"  // present on `queue` only — drives Step A.3.5 escalation gate
  "veto_reason": "<which principle or SOUL element triggered>"  // when block-veto
}
```

`queue_reason` semantics — what each value means and whether Step A.3.5
escalates it:

| `queue_reason` | Meaning | Escalates in A.3.5? |
|---|---|---|
| `uncertainty` | LLM was on the fence between `auto-apply` and `queue` (rule 6). The proposal IS values-touching and the LLM lacked clarity. | Yes — this is the canonical «would have asked the owner» case |
| `no-precedent` | Cold-start (rule 2): action class never seen before. | Yes — escalate; aligned/no-match upgrade is exactly the «build precedent without bothering owner» path |
| `anti-flip-flop` | Owner explicitly rejected a similar proposal in the last 30 days (rule 4). | **No** — owner's prior rejection is the source of truth; do not reroute to constitution. Stays in queue. |
| `config-never-auto` | `insights-config.yaml::classes::{class_key} = never_auto` (rule 3). | **No** — owner's per-class config is the source of truth. Stays in queue. |
| `other` | Catch-all for cases the LLM cannot classify into the four above. | **No** — fail-closed default; owner reviews. |

**Decision rules the LLM is told to follow:**

1. **Constitution / SOUL veto is absolute.** Any axiom or principle
   conflict → `block-veto`. Any SOUL-declared «currently being
   processed, no formalisation» topic → `block-veto`. Owner's
   override path is editing `insights-config.yaml`, not the sweep.
2. **Auto-apply is earned, not assumed.** Cold-start (no precedent in
   history.jsonl) → default `queue` for additive hints; `block-veto`
   for anything that even smells like mutation (split-hub,
   rewrite-hub, etc.) — though those types are not currently
   whitelisted, so this is a forward-compatibility guard.
3. **Insights-config overrides win.** If `classes::{class_key}` is
   `auto`, force auto-apply (still subject to veto). If `never_auto`,
   force `queue` with `queue_reason: "config-never-auto"`. Class-key
   format: `{lens-id}__{action-type}__{confidence}`.
4. **Anti-flip-flop guard.** If history.jsonl shows the owner
   `reject`-ed a substantively-similar proposal in the last 30 days,
   default to `queue` with `queue_reason: "anti-flip-flop"` and a
   note linking the prior rejection.
5. **Additive-only restriction.** Exactly five types may auto-apply:
   `wikilink_add`, `hub_stub_create`, `open_thread_add`,
   `decision_update_section`, `principle_candidate_add`. All five are
   additive — no auto type can mutate or delete owner content.
   `principle_candidate_add` appends one line to the high-recall
   `principle-candidates.jsonl` buffer (CAPTURE, not promotion — the
   owner still gates promotion to `0_constitution/` via `/minder:mem:lint`
   F.5); append-only + git-revertible, on par with the others.
   `ACTION_HINT_TYPES` in `_common.py` is **wider** than this set — it
   also carries `threshold_tune_proposal` and
   `metric_record_rerender_apply`, both Class C (owner-approved, never
   auto-applied), and both non-additive. So membership in
   `ACTION_HINT_TYPES` is necessary but NOT sufficient: the resolver
   checks the five-name list above, and a proposal of either Class C
   type is demoted to `queue` even though the parser accepted it.
6. **Uncertainty default = queue with `queue_reason: "uncertainty"`.**
   When the LLM is unsure between auto and queue, route to queue and
   record `queue_reason: "uncertainty"` so Step A.3.5 can escalate to
   `/minder:mem:check-decision` (the constitution-tree proxy for the absent
   owner). Cold-start with no precedent uses `queue_reason:
   "no-precedent"` (rule 2). Anything else uses `"other"`.
7. **Carry the would-be `action` on `queue` decisions too.** Even when
   routing to queue, populate the `action` field with the proposal's
   full type + params. Step A.3.5 needs the structured action manifest
   to invoke check-decision against a real artifact. `action` is only
   omitted when the item has no structured action (curated CLARIFICATION
   from Step A.2 with no lens-emitted hint).

**After the LLM, deterministic execution:**

For each `auto-apply` decision:

- Validate `action.type` against the **five auto-appliable names** of rule 5,
  not against `ACTION_HINT_TYPES` (which is wider — it also holds the two
  Class C types). If not one of the five, demote to `queue` with reason «type
  not whitelisted for auto» — defends against the LLM proposing types it
  shouldn't.
- Invoke `lens_action_handlers.APPLIERS[action.type](action.params,
  source_lens, base)`. The handler re-validates (TOCTOU) and either
  applies or returns `success=False`.
- On `success=True`: append to session accumulator's `auto_applied`
  list. Targets and provenance label come from the handler return.
- On `success=False`: handler validation failed inside apply (e.g.
  another process created the target between Step A.1 stale-check and
  here). Demote to `queue` with reason «attempted auto-apply,
  validation failed because {handler.reason} — owner review».

For each `block-veto` decision: queue with prefix
`**Constitution-veto:**` and the veto_reason. Append to session's
`constitution_vetoed` list.

`queue` decisions are NOT immediately written to the queue — they pass
into Step A.3.5 first.

### Step A.3.5 — Constitution escalation on queue decisions

Premise: `queue` from Step A.3 means the LLM would have asked the owner
to break the tie. Doctrine (`ENGINE_DOCTRINE` §3.6) keeps the owner-LLM
contract intact, but the contract permits a values-bearing tie to be
resolved by `/minder:mem:check-decision` — this is exactly the «proxy for the
owner when the owner is not in the loop» role the skill was built for.
A.3.5 is the escalation handler that shrinks the queue without lowering
the bar: it only converts a `queue` to `auto-apply` or `block-veto`
when the constitution gives an unambiguous verdict, and leaves the
genuinely-owner-needed cases (tradeoff, anti-flip-flop, config) in the
queue.

**Eligibility — only escalate when ALL hold:**

1. `decision == "queue"` from Step A.3.
2. `queue_reason ∈ {uncertainty, no-precedent}` per the table above.
   Other reasons preserve owner authority unchanged.
3. `action` is present and `action.type ∈ ACTION_HINT_TYPES`. Items
   without an `action` (curated CLARIFICATIONS from Step A.2 that lack
   a structured action manifest) are not eligible — there is nothing
   for `/minder:mem:check-decision` to evaluate.
4. The action touches a values-bearing surface. `principle_candidate_add` is
   explicitly carved out — it appends to the high-recall review buffer, it
   never applies a value to `0_constitution/` (promotion stays at F.5), so it
   is **never** values-bearing for escalation. Skip it here regardless of its
   params; its safety must not rest on the incidental absence of path-typed
   params. For every OTHER action type, at least one of these holds:
   - `action.type == "decision_update_section"` (always values-bearing
     by definition — the action targets a decision note).
   - Any path in the action params (`note_a` / `note_b` for
     `wikilink_add`; `cited_notes` for `hub_stub_create`;
     `cited_records` for `open_thread_add`) resolves to a knowledge
     note or record whose frontmatter `types:` array contains
     `decision`. Use `_system/scripts/_common.py::read_frontmatter` to
     read each cited path; treat unparseable / missing frontmatter as
     «not values-bearing» (fail-closed for inclusion).
   - SOUL focus match (best-effort, optional layer). When a SOUL
     focus extractor exists in `_system/scripts/`, additionally check
     whether the cited title / slug / `update_reason` text matches any
     active focus identifier (case-insensitive substring). Until that
     extractor lands, this third condition is a no-op — the first two
     conditions cover the load-bearing cases (decisions are the
     primary values-bearing surface).

   Items that fail the values-touch heuristic stay in the queue with no
   escalation. The heuristic errs toward not-escalating: false negative
   means owner sees one extra CLARIFICATION; false positive means an
   Opus call returning `no-match`. The asymmetry favours skipping.

**Invocation — one `/minder:mem:check-decision` call per eligible item:**

- `situation` — single paragraph distilled from the proposed action:
  `"Lens {source_lens} proposes {action.type} on {targets}. Reason
  given: {action.params.update_reason or LLM reasoning}. Should
  applying this action without owner review align with the
  constitution?"`. Keep concrete: name the actual targets and the
  actual proposed bullet / link / hub title.
- `record_ref` — the most-cited path in the action params (decision
  note for `decision_update_section`; first entry of cited list for
  the others). When no single record is dominant, omit and let the
  skill default.
- `dry_run: false` — Evidence Trail citations are wanted; this is a
  real autonomous decision, telemetry must reflect it.
- `--from-pipeline /minder:mem:resolve-clarifications` — `caller_class:
  mechanical` accounting; resolve's session log owns the batch commit.
- `is_sensitive` — propagate `true` if any cited path resolves to a
  note / record with `is_sensitive: true` in frontmatter; defaults
  `false`.

**Verdict mapping — what each verdict does to the candidate:**

| Verdict | Confidence | New decision | Target accumulator |
|---|---|---|---|
| `aligned` | any | `auto-apply` | `auto_applied` (with `from_escalation: true`) |
| `no-match` | any | `auto-apply` | `auto_applied` (with `from_escalation: true`) |
| `no-basis` | any | stays `queue` (fail-closed; annotate «no principles loaded — the constitution could not weigh in») | normal queue |
| `violated` | ≥ 0.7 | `block-veto` (with `veto_reason` from check-decision) | `constitution_vetoed` (with `from_escalation: true`) |
| `violated` | < 0.7 | stays `queue` (annotate `**Smart_resolve reasoning:**` with the borderline verdict) | normal queue |
| `tradeoff` | any | stays `queue` (annotate with the two principles in tension) | normal queue |
| error / empty visible tree | — | stays `queue` (fail-closed) | normal queue |

`no-basis` and `no-match` look alike and route oppositely, which is the whole
reason the verdict is split. `no-match` means principles were loaded and none
applied — the constitution genuinely does not object, and promoting is the
«build precedent without bothering the owner» path. `no-basis` means none were
loaded, so nothing could have objected: reading that as approval turns an empty
constitution into blanket consent, and on a base that has not been populated
yet — every friend's first weeks — it would auto-apply the entire queue. The
row above already promised fail-closed on an empty tree; before the split it
was unreachable, because check-decision returned `no-match` and this table
matched that first.

The `escalations` accumulator captures one row per check-decision
invocation regardless of outcome (the audit trail). The
`auto_applied` / `constitution_vetoed` accumulators capture only the
flipped outcomes (the action trail). Both are written to the session
log; the cross-reference is `item_ref`.

The asymmetric thresholds — promote on ANY confidence for aligned /
no-match, demote on confidence ≥ 0.7 for violated — reflect the cost
asymmetry: a wrongly-promoted aligned-no-match action is bounded
(additive scaffolding, git-revertable); a wrongly-demoted violated
action is also bounded (ends up in queue, owner sees one extra item
they would have seen without escalation anyway). The dangerous case
would be promoting a violated action on low confidence — that's why
< 0.7 violated stays in queue.

**Audit:**

- Every escalation (regardless of outcome) appends a row to the
  session's `escalations` accumulator with `{item_ref, source_lens,
  action_type, queue_reason_in, verdict, confidence, decision_out}`.
- The check-decision call itself emits to
  `_system/state/check-decision-runs.jsonl` per its own contract; the
  session log cross-references via `record_ref` plus the accumulator
  rows.
- An escalation that flipped the decision (queue → auto-apply OR queue
  → block-veto) appends the verdict reasoning as `**Escalation-resolved
  by check-decision:**` annotation on the action's provenance comment
  inside the apply target (auto-apply path) or on the CLARIFICATION row
  (block-veto path), so the owner sees explicitly «this didn't reach
  you because the constitution gave a clear verdict; here is which
  principle it cited».

**After A.3.5, the deterministic execution loop runs again, but only
on items the escalation just flipped:**

- Promoted items (verdict `aligned` / `no-match`) go through the
  `auto-apply` block from Step A.3 (`ACTION_HINT_TYPES` validation +
  handler dispatch + TOCTOU fallback). On TOCTOU `success=False`, the
  item demotes to queue with the standard «attempted auto-apply,
  validation failed» reason — the `escalations` row stays in place
  (the check-decision call still happened) and an `**Escalation
  resolved-but-toctou-failed:**` annotation is added so the owner sees
  the full trail.
- Demoted items (verdict `violated ≥ 0.7`) get the
  `**Constitution-veto:**` prefix treatment from Step A.3.
- Items left in the queue (low-confidence violated, tradeoff,
  heuristic-skipped, not-eligible) go through the queue-write block
  with `**Smart_resolve reasoning:**` annotation, plus
  `**Escalation:**` annotation naming the verdict + reason for those
  that did pass through A.3.5 without flipping.

**For each `queue` decision (post-A.3.5):** rewrite the corresponding
clarification (or synthesise a new one for hints that didn't yet exist
as clarifications) to attach the LLM's `reasoning` text under a
`**Smart_resolve reasoning:**` field. When the item passed through
A.3.5 without flipping (tradeoff / low-confidence violated /
heuristic-skipped / not-eligible), additionally attach
`**Escalation:**` with the result so the owner sees why it stayed.
Owner sees this in interactive Step 5.

**Cost / latency.** One `/minder:mem:check-decision` call per eligible queue
item. Bounded: queue items per nightly tick are typically O(1)–O(10)
in a healthy steady state; the values-touch heuristic culls further.
The Opus calls are sequential, not parallel — sequencing keeps Evidence
Trail writes serialised against the per-record `last_applied` field
without coordination overhead.

**Evidence Trail growth from autonomous citations.** Every escalation
call writes a `citation-aligned` / `citation-violated` /
`citation-tradeoff` entry into the cited principle's `## Evidence
Trail` section, regardless of whether the candidate flipped. This
grows the trail at roughly «escalations per night × 1–3 principles
per call» rate. The bloat is bounded by `/minder:mem:lint` Scan F.7 (weekly
Evidence Trail compaction), so steady-state size stays manageable.
F.4 «Most-cited principles» (monthly health metric) will reflect
auto-mode citations alongside owner-driven ones — this is desired
signal, not noise: a principle cited often by the resolver is genuinely
load-bearing on the system's autonomy. F.1 stale-detection runs on
`last_reviewed`, not `last_applied`, so auto-mode citations do not
suppress legitimate staleness signals.

### Step A.4 — Session log flush + early exit branch

1. Build a `SessionState` via `resolve_session.new_session(mode,
   trigger)` at Step A's entry. Mode is `auto` or `interactive`;
   trigger is `lint` (when `--auto-mode`) or `owner` (otherwise).
2. Throughout Steps A.1–A.3.5, accumulate `auto_applied`,
   `constitution_vetoed`, and `escalations` entries on the state
   object. The `escalations` list carries one row per
   `/minder:mem:check-decision` invocation made in A.3.5: `{item_ref,
   source_lens, action_type, queue_reason_in, verdict, confidence,
   decision_out}`. Promoted / demoted items also appear in the
   `auto_applied` / `constitution_vetoed` lists with provenance
   `from_escalation: true` so a single read of the session log shows
   both the verdict trail and the final outcome. The `escalations`
   accumulator is a new `SessionState` field — implementer adds
   `escalations: list[dict] = field(default_factory=list)` alongside
   the existing accumulators in `_system/scripts/resolve_session.py`,
   plus an `items_escalated` count in `_frontmatter` and a
   `_render_escalations` section.
3. After A.3 completes, call `resolve_session.write_session_log(state)`.
4. Update `_system/state/last-resolve-tick.txt` with current ISO-Z
   timestamp.
5. Branch on mode:
   - `--auto-mode` → release lock, exit silently. Owner sees the
     session log next time they open `_system/state/resolve-sessions/`
     or run interactive resolve. No console output beyond a one-line
     summary («auto-resolve: applied N, queued M, vetoed K»).
   - interactive → continue to Step 2 with the queue now containing
     curated + smart_resolve-annotated items. The remaining flow
     (theme menu, rounds, owner clicks) operates against this richer
     queue. Each owner decision in Step 5/6 calls
     `resolve_session.append_history` with structured precedent fields,
     and updates the same session log via `state.owner_decisions`.

**No history.jsonl writes in `--auto-mode`.** This is deliberate: the
engine never trains on engine. Only owner clicks accrete precedent.
Auto-mode applies are visible in the session log + target file
provenance, but they do not influence the next sweep's reasoning beyond
the «what's in the codebase right now» layer.

**Failure handling.** Any unhandled exception inside Step A logs to
the session accumulator's `auto_applied` list with `success=False`
shape, flushes the partial session log, and continues to the
appropriate branch (auto-mode exits; interactive continues with
remaining queue items unchanged). The next nightly tick retries —
state is forward-compatible.

---

## Step 2: Load and Parse Queue

Read `_system/state/CLARIFICATIONS.md`. Parse all entries under
`## Open Items` (and any sub-section like `## maintain {batch-id}` /
`## lint {date}` — those are open by convention until archived).

Each entry is a `### {date} — {title}` block followed by labelled fields:
`**Type:**`, `**Subject:**`, `**Source:**`, `**Action taken:**`,
`**Quote:**`, `**Context:**`, `**Uncertainty:**`, `**To resolve:**`,
optionally `**Confidence tier:**`, `**Suggested action:**`, `**Status:**`.

Build an in-memory list of items with parsed fields and original raw
markdown block (for safe archiving later — never re-render, copy
verbatim).

If the schema deviates (missing fields, unexpected sub-section names) —
continue best-effort. Surface anomalies in the round-close report;
never delete an item that didn't parse cleanly.

**Early exit:** zero open items → report «Очередь пуста — ничего разбирать»
and stop (release lock).

**Pre-resolve scan:** any item whose title or Confidence tier already
contains `RESOLVED` — these were marked done by the producer but not yet
archived. Auto-archive them silently in Step 7 without asking the owner.
Report count in the menu («3 уже-RESOLVED закрою без вопроса»).

---

## Step 3: Cluster by Type

Group remaining items by `**Type:**`. Compute per-cluster size and
weight. Standard Types (extend as new ones appear in producer skills):

| Type | Weight | Default batch |
|---|---|---|
| `people-bare-name` | light | 5 |
| `person-identity` | light | 5 |
| `content-type-canon-reviewed` | light | 5 |
| `content-type-canon-surfaced` | light | 5 |
| `content-type-unknown` | light | 5 |
| `content-angle-missing` | light | 5 |
| `process-compatibility` | light | 5 |
| `thread-closure-suggested` | medium | 4 |
| `idea-ambiguous-match` | medium | 4 |
| `evidence-trail-anomaly` | medium | 4 |
| `cross-domain-link` | medium | 4 |
| `project-identity` | medium | 4 |
| `identity-*` (the family `/minder:mem:lint` A.8 raises — `identity-field-retired`, `identity-tag-retired`, `identity-wikilink-repoint`, `identity-node-relocate`, `identity-split-undecided`, `identity-successor-*`, `identity-gate-unproven`, …) | heavy | 3 |
| `org-structure-tension` | heavy | 3 |
| `principle-candidate-batch` | heavy | 3 |
| `decision-*` | heavy | 3 |
| `lens-action-proposed` | heavy | 3 |
| `lens-action-veto` | heavy | 3 |
| `lens-action-apply-failed` | medium | 4 |
| unknown / new | medium | 4 |

`--max N` overrides. Light = quick approve/dismiss; heavy = each item
demands reading + values-judgment.

---

## Step 4: Theme Menu

Render single screen — numbered list with weight hints and recency:

```
Очередь CLARIFICATIONS — {N} open ({M} уже-RESOLVED закрою тихо)

Темы (выбери номер):
  1. people-bare-name (4)        — лёгкая · ~5 мин · самое старое 2026-04-23
  2. person-identity (1)          — лёгкая · ~2 мин · 2026-04-27
  3. principle-candidate-batch (4) — тяжёлая · требует размышления · 2026-04-27
  4. content-type-canon-surfaced (3) — лёгкая · выбрать canonical content_type
  5. process-compatibility (1)    — техника · 2026-04-27

Введи номер темы (или `q` — выйти).
```

If `--theme <type>` was passed → skip menu, jump to Step 5 with that
cluster.

If owner picks `q` → release lock, exit. Pre-resolved items stay
archived (Step 7 already ran for them).

---

## Step 5: Render Round

**Reader alignment (rails, not a frame).** The owner — a human — reads
these rounds. Formulate the questions to fit how the owner takes in
information: the presentation floor in
`_system/docs/communication-baseline.md` (conclusion first, plain
language, high signal, no filler, no flattery), this owner's
presentation-delta principles (`constitution-core.md` ai-interaction),
and their working style (`SOUL.md`). Read whichever of these exist; if
one is absent, skip it silently and align on the rest — a missing file
is not an error. This shapes FORM only — wording and density within the
block structure below. It never softens a hypothesis, hides a tradeoff,
or drops an option to make a round easier to read, and it never adds a
template on top of the required blocks.

Take the chosen cluster. Slice to batch size (heavy 3 / light 5 / `--max N`).
If cluster larger than batch → first N items by recency (oldest first —
fresh items fade later); subsequent rounds will pick up the rest.

**Smart_resolve enrichment.** Items that came through Step A's
auto-resolve sweep carry an attached `**Smart_resolve reasoning:**`
field. When rendering, surface that reasoning in the «Procedural
context» block so the owner sees why this item was queued instead of
auto-applied. If the item has matching precedents in
`_system/state/lens-resolution-history.jsonl`, list 1-3 most-similar
prior session links with a one-line summary («2026-04-15 — approved
similar hub for cross-PARA cluster, owner reasoning: tight cluster +
no overlap»). The smart_resolve LLM has already produced this; render
verbatim — do not re-reason.

**Class L items (`lens-action-proposed` / `lens-action-veto` /
`lens-action-apply-failed`) — adapted seven-block render.** Same top-
down order (essence first, then files, then context, then options),
but the blocks pivot on the proposal shape instead of a free-form
question:

```
── Q{n} ── {date} — {action_type}: {one-line proposal summary}

🧩 Суть:
{1-2 sentences: what the lens proposes, what it would change, what
the resolver concluded. For lens-action-veto, lead with the veto
reason. For lens-action-apply-failed, lead with the handler error.}

📂 Files:
{Cited paths from action params — note_a/note_b for wikilink_add,
cited_notes for hub_stub_create, cited_records for open_thread_add,
decision_note_path for decision_update_section. Owner can open them
directly.}

🧠 Procedural context:
**Source lens:** {lens-id}/{date}
**Confidence (lens self-report):** {low|medium|high}
**Smart_resolve reasoning:** {verbatim from item}
**Veto reason:** {only on lens-action-veto}
**Handler error:** {only on lens-action-apply-failed}
**Action type:** {wikilink_add|hub_stub_create|...}
**Action params:** {YAML inline rendering of params dict}

🔗 Precedent:
{0-3 lines from lens-resolution-history.jsonl on similar past
proposals + how owner decided. Empty section is OK.}

❓ Options:
  [apply]  — invoke handler now; commits the targets listed above
  [reject] — archive with `dismiss-lens-proposal` + reason
  [modify] — edit params inline (typically slug rename or alternative
             cited list), then apply
  [defer]  — push to next session
```

Class A/B items keep their original `a/b/c/d/e` options. Step 6
dispatches per item Type. (Class L is distinct from the existing
Step 9 Class C — auto-invoked-refresh classes; different letter to
avoid confusion.)

For each item in the batch, render with the **mandatory seven blocks**.
Order matters — owner reads top-down without prior session context, so
the *essence* must come first, then files for direct access, then
procedural context, citations, and proposals.

```
── Q{n} ── {date} — {short title from the entry header}

🧩 Суть:
{1–2 plain-language sentences: what is this about, what is the problem,
what decision is being asked. No jargon, no wikilinks, no file paths.
A reader who has never seen this item should grasp the question from
this block alone. MANDATORY on every item — light or heavy.

For person-identity: «В записи X (про Y) неизвестно кто Z. Нужно
подтвердить identity или dismiss.»
For thread-closure: «Thread X открыт N дней; есть/нет signals что
закрылся. Решаем — закрыть или нет.»
For principle-candidate: «N кандидатов в принципы накопилось. Решаем по
каждому — accept в constitution / sharpen существующий / reject / defer.»
Для каждого показывай полную карточку (цитата-observation, hypothesis,
falsifier+alt-reading из brief_reasoning, ось-`dimension`). На **accept→новый
принцип**: если есть `dimension` — проставь `cognitive_axes: [{dimension}]`, и
если у принципа ещё НЕТ `source_quote:` — проставь `source_quote: {observation}`
(DEC-3-якорь; не перезаписывай существующий), и задай **hot-reach вопрос** «меняет
ли это как ассистент общается со мной каждый день?» → если да, взвесь `core: true`
(доезжает до актёров) или внеси рельсу в SOUL `Context for Agents`; если нет —
оставь non-core. Рефлексия
владельца по кандидату — сама сигнал: если она уточняет/противоречит принципу,
заведи её как новое наблюдение (Evidence Trail / следующий кандидат), чтобы модель
актуализировалась из его фидбека, не только из линзы.
For policy/values: «N records carry inconsistent state for {field};
решаем policy A/B/C про N.»}

📂 Files:
{Exact file paths the owner can open directly: record path, source
transcript path, any related profile / hub / view. Use repo-relative
paths. Include `:line` anchors when there is a specific line. Wikilinks
are fine ALONGSIDE paths but never instead of them.}

📍 Где это случилось:
{2–3 sentence procedural context derived from **Context:** field — when,
what meeting / call / pipeline run, what action the producer took. If
Context is absent, summarise Source path + Action taken. This is the
«timeline» block, not the «what is the problem» block — that's «Суть»
above.}

💬 Цитаты (verbatim):
{copy **Quote:** field as-is — already verbatim by item-format
contract. If Quote is `_(none — pipeline-level issue)_`, show that
literally.}

🧭 Конституция / soul:
{Render this block when there is an actual hit that strengthens the
hypothesis — not gated by Type. Procedure: scan constitution-core
(always loaded) for relevance to the item; for values-bearing items
where core has nothing or is too coarse, escalate to
query_constitution.py --domains <d>. If no principle is relevant —
omit the block entirely (do not render an empty header). When
rendering: list 1–3 principles with id + 1-line statement + verdict
(aligned / violated / tradeoff / no-match) + one-line rationale tying
the item to the principle. Goal of this block is to make option `a`
more confident, not to gatekeep the resolution.}

🎯 Гипотеза:
{Skill's pre-formed proposal — what the owner most likely wants to do,
with reasoning. For person-identity: best-match candidate from PEOPLE.md
+ alternatives. For thread-closure: signals fired vs not. For principle-
candidate: own assessment of whether it clears the bar. Always state
the reasoning ground; never just "I think X".}

✅ Варианты:
  {For HEAVY items (cluster weight «heavy» per Step 3 — org-structure-tension,
  principle-candidate-batch, decision-*, identity-*, semantic-drift /
  policy), each
  primary option (a/b/c) MUST include three micro-sections:}

  a) {one-line label}
     - **Что меняется:** {2–3 specifics — files, behaviour, schema, prompt}
     - **Что приносит:** {2–3 positive outcomes — clarity, correctness, perf}
     - **Риски / потери:** {1–2 things owner has to accept / things that may break}
  b) {one-line label}
     - **Что меняется:** ...
     - **Что приносит:** ...
     - **Риски / потери:** ...
  c) {one-line label}
     - ...

  {For LIGHT items (person-identity, people-bare-name, process-compatibility,
  content-type-canon-*, content-angle-missing): one-line options are sufficient;
  add a 1-line clarifier only when the action is non-obvious. For
  content-type-canon-surfaced, present the default canonical type + the
  alternative(s) from the item, with the note title/excerpt already in the
  Context block, so the owner picks insight vs observation (etc.) in one keystroke.}

  d) skip — оставить открытым в текущей форме (показать снова в следующий раз)
  e) defer — оставить открытым с пометкой `**Last reviewed:** {today} — deferred`,
     уйдёт в конец очереди при следующем выборе темы
  f) dismiss — закрыть как not-actionable, в архив с пометкой `Resolution: dismissed`

  Skip / defer / dismiss are universal escape hatches — never expanded with
  micro-sections; they have fixed semantics.
```

Always include c/d/e on every item — they are universal escape hatches.
Number questions Q1, Q2, … sequentially across the batch (not per-cluster
restart). Owner answers like:

```
Q1: a
Q2: b — собеседник Ivan Petrov, добавь как primary speaker
Q3: dismiss
Q4: skip
```

Multi-line answers per question are normal — parse loosely.

---

## Step 6: Apply Resolutions

For each answered question, classify the action:

**Class A — silent ops (no diff, just do):**
- `c` skip — no-op, item stays as-is
- `d` defer — append `**Last reviewed:** {today} — deferred` line to
  the item block (in-place edit, append-only line)
- `e` dismiss — move item to `CLARIFICATIONS_ARCHIVE.md` with
  `**Resolution:** {today} — dismissed: {one-line owner rationale or
  "not actionable"}` appended to the block; remove from open file
- `a/b` for `process-compatibility`, `content-angle-missing`,
  `evidence-trail-anomaly` archival cases (no content edit needed) —
  same as dismiss but with substantive `Resolution:` text.
  `content-angle-missing` is informational at resolve time: acknowledge and
  archive — the draft-maintainer proposes the actual hook on its next run
  (the owner confirms it there, not here).

**Class B — content edits (diff-first):**
- Profile creation (person-identity → `3_resources/people/{slug}.md` +
  PEOPLE.md row + people-frontmatter backfill in cited records)
- Note frontmatter edits (people:, projects:, threads:)
- `content_type` canonicalization (`content-type-canon-surfaced` /
  `content-type-unknown`): write the owner's chosen canonical type into the
  note's `content_type:` frontmatter and prepend an Evidence-Trail line
  (`{today}: content_type set {raw} → {chosen} (owner-resolved, A.11)`).
  `content-type-canon-reviewed` items were already applied with the default
  by lint; resolving them either confirms (archive) or overrides (rewrite to
  the owner's pick + new Evidence-Trail line).
- Hub edits (open questions, current understanding bullets)
- OPEN_THREADS.md state changes (open → resolved)
- Decision-note creation (typically already created by the producer
  skill; here only when owner explicitly requests)
- Constitution edits — **never auto**. Principle-candidate accepts
  always render the proposed `0_constitution/{type}/{domain}/{slug}.md`
  body and ask for explicit confirm before write.

For Class B: render unified diff or new-file body, ask `[y/N]` per file.
On `y` → write. On `N` → re-prompt with the original options (a/b/c/d/e)
for that question. The diff gate is friction — but it's the only gate
where the owner can catch the skill misreading their answer.

**Class L — lens-proposal apply (Step A residue, owner-driven):**

Lens-action items routed to queue by Step A's smart_resolve sweep
(Type ∈ {`lens-action-proposed`, `lens-action-veto`,
`lens-action-apply-failed`}; underlying `**Action type:**` ∈
`ACTION_HINT_TYPES`) render with options `[apply] / [reject] /
[modify] / [defer]`.

- `apply` → invoke
  `lens_action_handlers.APPLIERS[action_type](action_params,
  source_lens, base)` directly — the same code path Step A.3 uses for
  auto-apply. On `success=True`, archive the clarification with
  `Resolution-action: apply-lens-proposal`, payload
  `{action_type, targets: handler.targets, from_lens, owner_modified: false}`.
  On handler failure inside apply, demote to deferred (do NOT archive).
- `reject` → archive with `Resolution-action: dismiss-lens-proposal`,
  payload `{reason: "constitution-conflict | not-actionable |
  wrong-target | low-quality | <free-form>"}`. The reason text feeds
  the next sweep's precedent grounding via history.jsonl.
- `modify` → render the proposed params, ask owner for an inline
  edit (typically slug rename, alternative cited_notes set), then
  call the applier with the modified params. Archive with
  `apply-lens-proposal` payload `{owner_modified: true}` so future
  precedent matching knows the LLM's params were not exactly what
  the owner approved.
- `defer` → same as Class A defer (append `**Last reviewed:** {today}
   — deferred` line, item stays in queue).

For `lens-action-veto` items the default option is `reject` (resolver
already concluded constitution conflict), but `apply` remains
available — owner override path is editing
`_system/state/insights-config.yaml::classes` to `auto` for the
class_key, then re-running auto-mode. Direct interactive `apply` of
a veto'd item is also valid (owner judgement supersedes resolver).

**On every owner click for a Class L item (apply / reject / modify):**

1. Append a row to `_system/state/lens-resolution-history.jsonl` via
   `resolve_session.append_history()` with the canonical schema:
   `ts`, `session_ref` (current session log path), `class_key` (via
   `resolve_session.class_key(lens_id, action_type, confidence)`),
   `decision`, `proposal_summary` (1-line), `applied_target` (when
   applicable), `salient_features` (carried forward from Step A.2),
   `owner_comment` (free text), `inferred_pattern` (LLM post-decision
   call — see below).
2. Append the human-readable narrative to the in-memory session state
   `state.owner_decisions` for the session log flush.
3. **Inferred-pattern post-call.** A small Haiku-grade LLM call takes
   the proposal + salient_features + decision + (optional)
   owner_comment and produces a 1-2 sentence reasoning hypothesis:
   *«Owner approves hub creation when cluster has tight thematic
   overlap, span >2 months, no existing hub overlap.»* This becomes
   input for future smart_resolve precedent matching. Stored in the
   history row's `inferred_pattern` field. ~5s, ~50 tokens output.
4. **Auto-apply traces (Step A.3) do NOT write here.** The history
   layer accretes precedent only from owner clicks, never from engine-
   approved actions. This keeps the precedent corpus owner-grounded.

When the session ends (Step 9.4), `resolve_session.write_session_log`
overwrites the markdown session file with the final accumulated state
(auto-applied + vetoed + owner_decisions). The file is sensitive
(captures conversational reasoning) — `is_sensitive: true` by default,
`audience_tags: []`, `origin: personal`.

**Class I — identity change (interactive-only):**

Two actions, `entity-retire` and `entity-reclassify`, resolve
the `identity-*` family and identity-bearing `project-identity` items. Per
`_system/docs/SYSTEM_CONFIG.md → Identity Contract` this skill is the declared
writer for `1_projects/PROJECTS.md` rows and the `## Removed` section of
`3_resources/people/PEOPLE.md` when an identifier stops being valid — the
contract's obligee.

**Never runs under `--auto-mode`.** Identity is an owner decision
(`ENGINE_DOCTRINE` §3.6). Step A neither auto-applies nor escalates these
items: `entity-retire` / `entity-reclassify` are not in `ACTION_HINT_TYPES`,
so the sweep can only leave them in the queue for an interactive session.
Also skipped under `--dry-run` — the migration and its completion gate write.

**I.1 — kind and successor, declared not inferred.**

| Kind | Action | Successor | What the owner must supply |
|---|---|---|---|
| merge | `entity-retire` | required | the surviving identifier |
| rename | `entity-retire` | required | the new identifier |
| split | `entity-retire` | two or more required | every identifier the old one became |
| reclassify | `entity-reclassify` | not applicable | the target category (project → trajectory, person-row → organization) |
| void | `entity-retire` | forbidden | nothing — references freeze where they stand |

Refuse the action when the owner's answer does not determine the kind, or
determines a kind whose successor rule it violates (a merge with no successor,
a void naming one, a split naming one). Re-prompt with the five kinds; never
infer the kind from the item text or from the registry's current wording.

**Every named successor is checked before I.2 writes anything.** It must be an
identifier of the same registry, present in it, and **live** — not itself
retired, not void. A successor that fails any of the three is refused with the
reason named, and the owner is asked for another: per Identity Contract
Successor integrity this is what keeps a retirement from aiming at the dead and
makes a cycle unreachable through this path. When the owner names an identifier
that is itself retired, offer its terminal live successor as the candidate
rather than accepting the hop.

**I.2 — registry row (provisional until I.5).** Write the retirement /
reclassification row per Archive Contract Form B, carrying kind, successor and
date in the declared columns of that registry's retirement section
(`## Retired Identifiers` in PROJECTS.md, `## Removed` in PEOPLE.md).
The row goes first because `identity_audit.py` resolves «what counts as
residue» against the registry — before the row exists the scan has nothing to
report, so the row and the migration are one unit of work, not two.

**I.3 — migrate live surfaces off the audit's work list.** Run
`python3 _system/scripts/identity_audit.py --report --json` and take the
`findings` for this identity. Each finding carries `surface`, `surface_class`,
`action`, `current`, `target` — dispatch on `action`:

| `action` | Surfaces | How it is applied |
|---|---|---|
| `migrate` / `demote` | membership field | silent-safe — exact-token rewrite, report counts in the round-close report |
| `migrate` / `renamespace` | namespaced tag | silent-safe — same |
| `repoint` | wikilink | **owner-reviewed** — render the diff per the Class B gate; a repointed link changes prose the owner wrote, and a sentence true of the old identifier is often false of the successor |
| `relocate` | node card, node container, hub | **owner-reviewed, one confirmation per node** — a node moves by what it contains, not by its name, and the move is irreversible |
| `regenerate` | anything with `surface_class: derived` | never edited here — I.4 |

Matching is exact identifier equality on every surface; a longer identifier
containing the retired one is a different identity and is left alone. A `void`
kind migrates nothing — its references freeze and the audit excludes them. A
`split` kind migrates nothing automatically: each of its
`identity-split-undecided` findings is put to the owner as a choice among the
declared successors, one surface at a time, and applied per the row its chosen
action falls under above. Residue clears by his decisions, not by a template.

**I.4 — derived surfaces are queued, not edited.** Findings with
`surface_class: derived` are left untouched and `registry_writes++` — Step 9.3
runs `/minder:mem:maintain`, which rebuilds them. Hand-editing a derived surface is
undone by the next rebuild.

**I.5 — completion gate (per identity, recorded).** Run exactly:

```bash
python3 _system/scripts/identity_gate.py --identity {entity-id}
```

`identity_gate.py` holds no opinion of its own: it shells `identity_audit.py`
with `--report --json --fail-on-residue --identity {entity-id}` and passes that
exit code straight through. What it adds is the record — one append-only line in
`_system/state/identity-gate.jsonl` naming the command, the exit code, the
residue count and the commit it ran against, and the same line on stdout. That
line is the difference between a proof and a claim: without it the number in the
resolution is something the writer said about its own work, and afterwards
nothing can tell an honest run from a remembered one.

`--identity` is what makes this gate about **this** change: it restricts the
report, the residue count and the exit code to that identifier's buckets and
drops every other identity's findings from the output entirely, so an unrelated
dirty identity can neither fail this change nor be mistaken for its work list.
Exit codes: `0` — zero live residue for this identity; `2` — live residue
remains; `1` — the identifier is unknown to every registry, or the scan could
not run. **Exit 1 is a failure, never a pass.** Its ordinary causes are a
mistyped id and a registry row that never landed, and a gate that reads
«unknown» as «clean» closes the change against nothing.

Copy `ts`, `command`, `exit_code` and `residue_count` **out of the JSON line the
gate printed** into the resolution as `gate: {ts, command, exit_code,
residue_count}` — never from memory, and never `--no-record` here. `ts` is what
lets `/minder:mem:lint` A.8 (9) match the archived resolution against the log line
rather than against a number that appeared in a payload. Identity Contract
Obligation 4 makes this recorded scan part of the resolution; a resolution
archived without it is unproven.

- **Exit 0** → the row is final. Archive the item with `Resolution-action:
  entity-retire`, payload `{registry, entity_id, kind, successor | successors,
  date, gate, surfaces_migrated: {field: N, tag: N, wikilink: N, node: N}}` —
  or `entity-reclassify`, payload `{registry, entity_id, from_category,
  to_category, date, gate, surfaces_migrated: {...}}`.
- **Exit 2 or exit 1** → the change is not finalised. All four of the
  following, none optional:
  1. Do **not** archive the item and do not write a `Resolution-action` for it.
     The item left open **is** the refusal — it returns in the next session and
     in tonight's lint.
  2. Rewrite its `**To resolve:**` with the remaining findings copied out of
     the JSON — `surface`, path, `current`, `target`, one line each. On exit 1,
     write instead which identifier was queried and that no registry holds it.
  3. Leave every file written in I.2–I.3 in the working tree, untouched.
     **Nothing is reverted.** The migration already done is correct work; a
     `git checkout --` over a path list reconstructed from the session's own
     memory destroys more than it restores; and the registry row has to stay,
     because without it the scan cannot tell residue from an ordinary
     reference. An unfinished identity change is visible and resumable; a
     half-reverted one is neither.
  4. Report the dirty paths and the exact command above in the round-close, so
     the owner re-runs it himself and sees the same number. Step 9.4's save
     reminder names the unfinished change by id.

Honesty about what this gate is: the refusal binds because the failing branch
is the cheap one — nothing to undo, nothing to reconstruct — and because it is
not the last check. The same audit runs unattended in tonight's A.8 over the
same base and re-raises every surface still naming the identifier, whatever
this session recorded; A.8 (9) separately catches a resolution archived without
its gate line. A claim of zero residue costs a re-raised item tomorrow, under
the id of the resolution that made it.

`entity-reclassify` runs the same five sub-steps; its I.1 takes a target
category instead of a successor, and its I.5 gate demands the same zero live
residue for the same identity — the identity is alive, so what has to be gone
is every surface still carrying the old category's namespace.

**Archive Contract enforcement (cross-cutting, applies to any Class A or Class B action whose effect is archival):**

Per `_system/docs/SYSTEM_CONFIG.md → Archive Contract`, every archival event MUST carry a reason captured **with the entity**. When applying the actions below, the skill is responsible for writing the contract-required field in the same atomic operation as the archival flag. Skipping the field is a contract violation; a follow-up `/minder:mem:lint` Archive-contract scan will surface it as `archive-note-missing` / `archive-reason-missing` CLARIFICATION.

| Resolution-action | Archive Contract form | Required write |
|---|---|---|
| `archive-hub` | Form A (file-based) | Move hub `.md` from `5_meta/mocs/` to `4_archive/` per `target_path` payload AND append `## Archive Note` block at the end of the hub file with `date: today`, `reason: {payload.reason}`, `triggered_by: /minder:mem:resolve-clarifications`, optional `superseded_by` if the resolution mentioned one. Frontmatter `status: archived` + `archived_at: today` flipped if the hub file uses the `archived` status (knowledge-style); for hub-status `resolved` the Archive Note alone is the canonical record. |
| `dismiss` | Form C (queue) | The `**Rationale:**` line on the resolved CLARIFICATION block (what Step 7 already writes). Required for archival-effect dismissals — never leave the rationale empty for these. |
| `dismiss-duplicate` | Form C (queue) | Same as `dismiss`. |
| `merge-notes` (the merged-away note) | Form A (file-based) | Append `## Archive Note` to the merged-away note BEFORE removing it from active surface, with `reason: "merged into [[kept-note-id]]"`, `triggered_by: /minder:mem:resolve-clarifications`, `superseded_by: [[kept-note-id]]`. Move the merged-away file to `4_archive/` (do not delete). |
| `close-thread` | Form C (queue) | The `resolution_text` payload populates the Resolved-section entry in `OPEN_THREADS.md`. Required for every `close-thread` and `pursue-or-close` with `choice: close`. |
| `entity-retire` | Form B (registry-row) | Write the retirement row in the registry's retirement section with kind, successor and date populated (`## Retired Identifiers` in `1_projects/PROJECTS.md`, `## Removed` in `3_resources/people/PEOPLE.md`). Successor is required for `merge` / `rename` and forbidden for `void`. Same atomic write as the live-surface migration — a row without its migration is a contract violation, caught by the I.5 gate before it can be committed. `entity-reclassify` is not an archival event (the identity stays alive) and requires no Archive Contract write. |
| `demote-tier` (to `stale`) | Form B (registry-row) | Move the row from `## People` to `## Stale People` in `PEOPLE.md` and populate the `Reason` cell with `payload.reason`. Same atomic write — never leave the row half-moved. |

For all other Resolution-actions whose effect is non-archival (promotion, refresh, restructure), no Archive Contract write is required.

**Class C — auto-invoked refresh (Step 9):**

Some resolutions invalidate derived views or registries. Track which
classes of writes happened during the session (counters, not file lists):

| Counter | Incremented by | Triggers in Step 9 |
|---|---|---|
| `constitution_writes` | principle-candidate accept (new file under `0_constitution/{type}/{domain}/`) | `/minder:mem:regen-constitution` |
| `registry_writes` | person-identity (new profile + PEOPLE.md row), project-identity (PROJECTS.md), identity change (Class I — registry row + every migrated live surface), thread-closure (OPEN_THREADS.md), hub edits (`5_meta/mocs/`), `content_type` canonicalization (A.11 note frontmatter) | `/minder:mem:maintain` |

These are surfaced + acted on by Step 9. The skill no longer leaves
them as text suggestions in the round-close report.

### Inline extraction evaluation (parallel to resolution)

While processing each owner answer to apply its resolution above, the
skill ALSO evaluates whether the answer carries durable knowledge worth
capturing as a separate artefact. This evaluation runs in the same
processing pass as the resolution itself — no separate LLM call, no
pre-filter on word count. The running model has the answer fully
in-context already; extraction is a parallel output of the same
understanding.

**Skip extraction evaluation entirely (no per-answer work at all) when
ANY of:**
- `--no-extraction` flag is set on the run (owner opted out for the
  whole session — no point evaluating answers Step 6.5 won't show).
- `--auto-mode` is set (no owner conversation to extract from).
- `--dry-run` is set (no writes happen anyway).

**Otherwise, skip extraction for an individual answer when ANY of:**
- Owner gave a pure letter answer (`a`, `b`, `c`, `d`, `e`, `f`) with
  no accompanying explanation.
- Owner gave a `skip` / `defer` / `dismiss` with no rationale.
- Answer is ≤ ~10 words of purely procedural content («сделаю на
  следующей неделе», «не получилось добраться»).
- Owner explicitly opted out in the answer («не сохраняй», «не надо
  фиксировать», «just for context», «забудь это»).

**Otherwise evaluate as candidate for ONE of three classes:**

| Class | What it captures | Target |
|---|---|---|
| `knowledge-note` | Architectural / organizational / decision / factual content that exceeds what fits in the Resolution text — explanations of how systems work, why a choice was made, status updates, niche-research conclusions | A flat file in `_sources/inbox/resolve-clarifications/` carrying the owner-approved text; `/minder:mem:process` files it like any source (see «Filing a `knowledge-note` extraction» in Step 6.5) |
| `soul-update` | Identity / Focus / Active Goals / Values shift the owner just declared («не делаю X», «теперь focus Y», «убираю Z как направление») | `_system/SOUL.md` targeted edit |
| `people-update` | Factual update about an **existing** person — role change, org transition, relationship status change, biographical fact («Петя теперь в team B», «Маша вышла замуж»). NEW person mentions are NEVER handled by this class — they flow through the existing `people-bare-name` / `person-identity` CLARIFICATION path (raised by `/minder:mem:process` when transcripts surface unknown names) per doctrine §3.6 «no silent profile creation». | `3_resources/people/{id}.md` profile body edits and/or `PEOPLE.md` row updates (Org, Notes, Recent contexts columns). NEVER creates a new profile file. |

**Do NOT propose:**
- `principle-candidate` — handled by the global `constitution-capture`
  hook in CLAUDE.md (fires on triggers (a)/(b)/(c)/(d) during any
  Claude conversation). Step 6.5 transparency line reports hook fires
  for owner visibility but does not duplicate the capture path.
- `hub-context-update` — hub edits flow through `/minder:mem:maintain` Step 4
  linkage and lens action hints. Step 6.5 staying out of hub-write
  territory keeps the linkage layer single-source.

**Anti-dedup before proposing.** For each tentative proposal:
- If the same information was just written by Step 6 (Resolution text
  in CLARIFICATIONS_ARCHIVE, thread `Resolution:` field, Class B file
  edit) → drop, no proposal.
- For `knowledge-note`: a file in `_sources/inbox/resolve-clarifications/`
  or `_sources/processed/resolve-clarifications/` whose body already carries
  the same approved text → drop, no proposal; a resumed session files nothing
  twice. Clarification titles repeat across the queue, so the title is
  context only, never the match. Then check
  `_system/views/INDEX.md` for an existing note on the same topic (grep on
  topic keywords): a close match is named in the extraction as
  `Related: [[{note-id}]]`, a hint for processing's connection pass.

**Confidence floor: 0.6.** If extraction confidence is below 0.6, drop.
Owner declines via `n` on diff are cheap; missing a capture is
expensive — tilt toward proposing, not toward holding back.

**Independence from resolution outcome.** Evaluation considers the
answer text only, not which resolution action was finally executed.
A rich `defer` answer with substantive content still produces
proposals; a one-letter `apply` answer to a Class L item produces
none.

**Output template — MANDATORY structure in Step 6.** Even when no
extractions are proposed, the resolution output includes the
`## Extraction proposals` section explicitly. Format:

```
## Resolutions applied
- Q1: {resolution-action} → {target / file touched}
- Q2: ...
- ...

## Extraction proposals
- Q1: {class} — draft path: {path}; confidence: 0.X; one-line суть
- Q3: {class} + {class}  (multiple proposals for one Q ok)
- Q2, Q4: (none — purely procedural / already-captured / opt-out)
```

The empty-section case is written as `(none — all Qs procedural or
already-captured)` rather than omitting the section. This is a
force-function: future model invocations cannot silently forget the
extraction pass; the spec demands the section appears.

Accumulate proposals into in-memory `extracted_artefact_proposals[]`
for Step 6.5 batch UI.

---

## Step 6.5: Extraction Batch — Present and Apply

**Runs strictly before Step 7 archive.** If owner is interrupted
mid-6.5, CLARIFICATIONS items are still in `## Open Items`; resume
re-renders the round, Step 6 re-evaluates, anti-dedup catches
artefacts already written. State stays recoverable.

**Skip Step 6.5 entirely when:**
- `--auto-mode` flag is set (auto-mode has no owner conversation to
  extract from).
- `--no-extraction` flag is set (owner opted out for the session).
- `--dry-run` flag is set (preview-only sessions don't write).
- `extracted_artefact_proposals[]` is empty (silent no-op, no UI
  noise).

**Transparency line (optional, only when N>0).** Before showing the
proposal batch, check `_system/state/principle-candidates.jsonl` for
entries appended since the round started (by mtime / line count
delta). If N>0, print:

```
ℹ Constitution-capture hook fired N× during round →
  {1-line hypothesis per entry}
  Will surface in next /minder:mem:lint F.3 weekly aggregation.
```

When N=0, omit the line entirely. The line is FYI only — no owner
action expected.

**Batch UI.**

```
💡 Knowledge extraction — N предложений зафиксировать:

  1. Q{n} → {class}  (conf 0.X)
     📂 {target path}
     🧩 {1-2 sentence суть of what the artefact captures}
     People: {person-ids if relevant}

  2. Q{n} → {class}  (conf 0.X)
     ...

Какие применить? (y all / n / список номеров «1 3» / per item «1y 2n 3m»)
```

**Per-item handling.**

| Owner input | Action |
|---|---|
| `y` (whole batch) or `1,2,3` (numbers) | For each selected: enter Class B diff gate → owner confirms diff → write file → append entry to `extracted_artefacts[]` log with `decision: approved`. On diff-stage `N` → drop without retry, log `decision: declined_at_diff` |
| `n` (whole batch) | Drop all proposals, log each as `decision: declined` |
| `{n}m` (modify one item) | Owner provides 1-line edit instruction (e.g. «не decision, а insight; domain career не work»). Re-draft in place → re-show updated proposal in same batch (next iteration). Further `m` allowed once; second `n` drops |
| Mixed (`1y 2n 3m`) | Process each per its letter |

**No recursive sub-menus.** `m` is bounded — owner gives one-line
edit, skill re-drafts once, re-presents. If still wrong → `n` drop.
Owner can always recreate artefact manually if a complex case needs
attention.

**Atomicity ordering per approved item.**
1. Class B diff render.
2. Owner confirms `[y/N]`.
3. Write file to disk (inbox extraction / SOUL edit / people update).
4. Append entry to `extracted_artefacts[]` accumulator.
5. Proceed to next item.

A crash between (3) and (4) leaves the artefact on disk without a log
entry — recoverable (file is the truth; log is the audit). A crash
between (1) and (3) leaves nothing on disk. The ordering guarantees
no «log says written but file missing» state.

**Filing a `knowledge-note` extraction.** It becomes a source, not a note —
`/minder:mem:process` is the one writer of knowledge notes
(`_system/docs/SYSTEM_CONFIG.md` → Skill Write Territory). The engine ships
the `resolve-clarifications` source; this step only writes into it.
- No `resolve-clarifications` row under Active or Reserved Sources in
  `_system/registries/SOURCES.md` → write no file. Append an
  `extraction-source-missing` CLARIFICATION carrying the approved text
  verbatim, so nothing is lost, and go on with the session.
- One flat file in `_sources/inbox/resolve-clarifications/`, named
  `YYYY-MM-DD-{slug}.md` and portable per `_system/registries/SOURCES.md` →
  «Portable names (Windows compatibility)». The name must be free in both that
  folder and `_sources/processed/resolve-clarifications/` — processing moves the
  file there, and a taken name would overwrite a processed source — so the slug
  gets `-2`, `-3` until it is.
- Frontmatter is one line, `source: resolve-clarifications` — provenance only;
  `/minder:mem:process` reads the whole file as content.
- The body is the knowledge in the owner's own words and language, then a
  context line quoting the clarification item's title verbatim, then
  `Related: [[{note-id}]]` when the anti-dedup check named a note.

**Counter tracking for Step 9 refresh.**

Step 6.5 writes feed into Class C counters from Step 6:
- `knowledge-note` → no counter: the file waits in the inbox, and the
  views are refreshed by `/minder:mem:process` + `/minder:mem:maintain` when they
  file it
- `soul-update` → no counter (SOUL is read directly by other skills;
  not a derived view)
- `people-update` → `registry_writes++` (PEOPLE.md changed → INDEX
  surfaces the row delta on regen)

Step 9.3 then runs `/minder:mem:maintain` as usual when counter > 0.

---

## Step 7: Archive and Clean

Rewrite `CLARIFICATIONS.md` in place:

1. Read current file fresh.
2. Remove blocks for: pre-resolved items (Step 2 scan), all dismissed
   items, all `a/b`-resolved items.
3. Update in-place: deferred items get `**Last reviewed:**` line
   appended; skipped items unchanged.
4. Update top-of-file `**Last reviewed:**` field to today's date with
   short summary: `(YYYY-MM-DD — resolve session: closed N, deferred
   M, dismissed K, skipped S)`.
5. Append removed blocks to `CLARIFICATIONS_ARCHIVE.md` under a new
   `## Archived YYYY-MM-DD (resolve session)` section, in original order,
   each with `**Resolution:**` line appended.

On any error during this step: do not leave the file half-written.
Restore via `git checkout -- _system/state/CLARIFICATIONS.md` and
report the failure. Owner is responsible for working from a clean tree;
git is the rollback mechanism.

---

## Step 8: Round Close + Continue

Per-round report (printed after Step 7 each round, BEFORE Step 9):

```
Раунд закрыт — тема: {type}

  ✅ Закрыто: {N}     {one-line list of what got resolved}
  ⏸  Deferred: {M}    {short list}
  ⏭  Skip: {S}        {short list}
  🗑  Dismiss: {K}    {short list}
  🔁 Pre-resolved: {auto}

Осталось в очереди: {remaining} items в {remaining-themes} темах.

{If --continue passed: jump to Step 4 with refreshed counts.}
{Else: «Запустить ещё круг? — `y` или укажи тему: …». Wait for owner.}
```

When the owner declines further rounds (or queue empties) → proceed to
Step 9. Lock is held through Step 9 and released at the end.

---

## Step 9: Post-resolution refresh + save reminder

Always runs after the rounds end (even pure defer/skip/dismiss sessions
leave CLARIFICATIONS.md / ARCHIVE.md dirty and need a save reminder).
Sub-steps gate independently on what actually happened.

### 9.1 — Release lock first

Delete `_sources/.resolve.lock` before any Step 9.2 / 9.3 invocation
and before printing the save reminder. Two reasons:
- `/minder:mem:save` checks `_sources/.resolve.lock` and refuses if held —
  the owner running save next would hit a confusing abort.
- Cleanliness — the session's writes are committed in CLARIFICATIONS.md
  by Step 7 already; the lock has no further purpose.

`/minder:mem:maintain` and `/minder:mem:regen-constitution` do NOT check
`.resolve.lock` today, so the order of 9.1 vs 9.2/9.3 is not load-
bearing for them — but releasing first keeps the invariant simple
(no producer skill ever sees a stranded lock from this skill).

### 9.2 — Constitution refresh

Fires only if `constitution_writes > 0` and `--no-refresh` not passed.
- Print: «Записал N новых принципов — обновляю constitution-core view…»
- Invoke `/minder:mem:regen-constitution` inline.
- On failure → print the skill's error verbatim, continue to 9.3 (don't
  block other refreshes on one failure).

### 9.3 — Registry / hub refresh

Fires only if `registry_writes > 0` and `--no-refresh` not passed.
- Print: «Тронул N registries / hubs — запускаю /minder:mem:maintain для
  пересборки HUB_INDEX / INDEX / CONCEPTS…»
- Invoke `/minder:mem:maintain --no-sync-check` inline (Step 0 already synced;
  double-sync is wasteful and may surprise the owner with a second
  rebase preview).
- On failure → print the skill's error verbatim, continue.

### 9.4 — Save reminder

`/minder:mem:save` per its contract is **never auto-fired by other skills** —
it stays an explicit owner gesture. This step only reminds, never
invokes.

Compute `git status --porcelain` to detect dirty files (any of:
CLARIFICATIONS.md / ARCHIVE.md from Step 7, profile / record edits
from Class B, regen / maintain outputs from 9.2 / 9.3).

If dirty and `--no-save` not passed:
```
Сессия закрыта. Изменено файлов: <K>

  Закоммить и пушни когда готов:
    /minder:mem:save
```
If clean → print «Working tree clean — nothing to commit». Exit.

### 9.5 — Final recap

```
Сессия завершена.
  Резолюций: <closed>     Deferred: <M>     Dismissed: <K>
  Refreshes: constitution=<y/n/skipped>  maintain=<y/n/skipped>
  Working tree: <dirty K files | clean>
```

---

## Constraints

- **Essence first, never optional.** Every Q opens with `🧩 Суть:` —
  1–2 plain-language sentences. Owner is reading without session context
  on items often a week+ old; without «суть» up-front the procedural
  blocks below require mental reconstruction of «о чём это вообще» on
  every item. This rule is load-bearing on round friction.
- **Never recall meeting context unaided.** Every Q also renders the
  `📍 Где это случилось:` block. If the entry has no Context field and
  Source path leads to a missing file — say so explicitly, do not
  fabricate context.
- **Quotes are verbatim.** Never paraphrase the `**Quote:**` field. If
  it's empty / `_(none)_` — render that as-is.
- **Numbered questions across the whole round** — Q1..Qn, not Q1..Qm
  per cluster.
- **One theme per round.** No bulk operations across themes. Owner
  decides whether to chain via `--continue`.
- **Diff-gate is non-negotiable for Class B.** Even on unambiguous `a`
  answers, show the proposed write before applying.
- **Constitution lookup is opt-out (`--no-constitution`), default-on**
  via the always-loaded `constitution-core.md`. Deeper queries
  (`query_constitution.py`) escalate when needed — typically on
  values-bearing items, but the trigger is «hypothesis would benefit
  from more context», not Type. The skill renders the `🧭 Конституция`
  block only when there is a real hit; omits silently otherwise.
- **Non-personal-origin principle candidates always require manual
  review.** Items tagged `origin: work` or `origin: bootstrap-raw-scan`
  go through the diff gate even if the round logic could otherwise
  auto-archive them. Constitution stays signal-only.
- **Identity change is interactive-only and gated on a recorded scan.**
  `entity-retire` and `entity-reclassify` never run under `--auto-mode` or
  `--dry-run`, and the item is never archived while `identity_gate.py --identity
  {id}` returns anything but 0 — the work stays in the tree and the item stays
  open. The gate appends its own line to `_system/state/identity-gate.jsonl` and
  the resolution carries that line's `ts` and exit code; nightly A.8 checks the
  residue, the record, and that the two agree.
- **No re-render of stored blocks.** When archiving, the block markdown
  is copied verbatim plus a `**Resolution:**` line. Never normalise
  fields, never strip whitespace — preserves audit trail.
- **Sync before review (`--no-sync` to opt out).** Reviewing a stale
  queue wastes attention on items already resolved on another device.
  Step 0 always fronts the session unless owner opts out explicitly.
- **Refresh fires only on material writes.** Sub-steps 9.2 / 9.3 run
  `/minder:mem:regen-constitution` / `/minder:mem:maintain` only when this session
  produced principle accepts / registry edits respectively. Pure
  defer/skip/dismiss sessions still trigger 9.1 (lock release) and
  9.4 (save reminder) — the working tree is dirty either way.
- **Save is never auto-invoked.** Step 9.4 prints a reminder; the
  owner runs `/minder:mem:save` themselves. This preserves `/minder:mem:save`'s
  contract («never auto-fired by other skills»).
- **Lock released before any 9.2/9.3/9.4 step.** `/minder:mem:save` checks
  `.resolve.lock` and would refuse if held; releasing in 9.1 keeps
  the invariant simple regardless of which sub-steps fire.
- **Extraction evaluation is structural, not optional.** Step 6 output
  MUST include the `## Extraction proposals` section even when no
  candidates are surfaced (written as `(none — ...)` with reasoning).
  This is a force-function preventing silent extraction skips across
  model invocations.
- **Extraction stays out of `0_constitution/` and hubs.** Principle
  candidates flow through the global `constitution-capture` hook;
  hub edits flow through `/minder:mem:maintain` linkage and lens action
  hints. Step 6.5 owns only `knowledge-note` / `soul-update` /
  `people-update` — three classes, no overlap with other write paths.
- **Step 6.5 runs strictly before Step 7.** Archive ordering is
  load-bearing for interruption safety: if owner is interrupted
  during extraction review, CLARIFICATIONS items are still open and
  re-running the round re-evaluates with anti-dedup catching
  already-written artefacts.
- **Extraction `m` (modify) is bounded — one edit cycle.** Owner gives
  a 1-line correction, skill re-drafts once. Second wrong answer →
  drop (`n`). No recursive sub-menus inside the batch UI.

---

## Output Files Touched

Direct writes by this skill (Steps 1–8):
- `_system/state/CLARIFICATIONS.md` — items removed / deferred-line appended
- `_system/state/CLARIFICATIONS_ARCHIVE.md` — resolved blocks appended
- `_sources/.resolve.lock` — created/deleted
- `3_resources/people/{slug}.md` — when person-identity → create-profile
- `3_resources/people/PEOPLE.md` — registry rows added/updated
- `_records/{meetings,observations}/{note}.md` — frontmatter `people:` / `projects:` / `threads:` updates
- `5_meta/mocs/{hub}.md` — open questions / current understanding edits when thread-closure
- `_system/state/OPEN_THREADS.md` — thread state moves
- `0_constitution/{type}/{domain}/{slug}.md` — principle accepts (creates only)
- `1_projects/PROJECTS.md` — Class I retirement / reclassification rows
- `3_resources/people/PEOPLE.md` `## Removed` — Class I retirement rows
- Live surfaces named by `identity_audit.py` findings — membership fields,
  namespaced tags, wikilinks and nodes carrying a retired identifier

Step 6.5 extraction writes (when owner approves a proposal at diff gate):
- `_sources/inbox/resolve-clarifications/{YYYY-MM-DD}-{slug}.md` — one flat
  file per approved `knowledge-note` extraction; `/minder:mem:process` files it
- `_system/SOUL.md` — `soul-update` extraction edits (Identity, Focus,
  Active Goals zones; never the Values auto-zone)
- `3_resources/people/{id}.md` — `people-update` profile body edits
  for EXISTING profiles only (role, org, biographical facts). Never
  creates new profile files; new-person path stays the
  `people-bare-name` / `person-identity` CLARIFICATION flow
- `3_resources/people/PEOPLE.md` — `people-update` row changes (Org,
  Notes, Recent contexts) for existing rows

Step A direct writes (lens-action handlers + session log):
- `_system/state/resolve-sessions/{date}-{sid}.md` — per-session log
  (auto + interactive). `is_sensitive: true`, `origin: personal`.
- `_system/state/lens-resolution-history.jsonl` — append-only precedent
  index. **Interactive mode owner clicks only**; auto-mode does not
  write here.
- `_system/state/last-resolve-tick.txt` — high-water marker for the
  «modified since» scan.
- `_system/state/insights-config.yaml` — created from
  `insights-config.yaml.template` on first run when missing; never
  rewritten thereafter (owner-mutable).
- Lens-action handler targets (additive only):
  - `wikilink_add` → `## Связи (auto)` section in both notes
  - `hub_stub_create` → `5_meta/mocs/hub-{slug}.md` + back-wikilinks
    in each cited note's `## Связи (auto)` section
  - `open_thread_add` → `_system/state/OPEN_THREADS.md` `## Active`
  - `decision_update_section` → `## Update {today}` section appended
    to the cited decision note

Indirect writes via Step 9 chained skills:
- `/minder:mem:sync-data` (Step 0) — `git fetch` + rebase / fast-forward against `origin`
- `/minder:mem:regen-constitution` (Step 9.2) — `_system/views/constitution-core.md`,
  `_system/SOUL.md` Values zone, `_system/views/CONSTITUTION_INDEX.md`
- `/minder:mem:maintain` (Step 9.3) — `_system/views/HUB_INDEX.md`,
  `_system/views/INDEX.md`, `_system/registries/CONCEPTS.md`, registry hygiene
- `/minder:mem:save` (Step 9.4) — NOT invoked by this skill; reminder only,
  owner runs explicitly per save's contract

(Concept/audience format issues do NOT pass through this skill —
autonomous resolution by `/minder:mem:lint` Scan A.7 handles them
upstream. AUDIENCES.md Extensions table is owner-curated outside
the pipeline.)

## What This Skill Does NOT Do

- Does not invent new ambiguities — only resolves what producers wrote.
- Does not edit principle bodies in `0_constitution/` (only creates new
  files on accept).
- Does not invoke `/minder:mem:save` — Step 9.4 reminds, owner runs.
- Does not reorder or rewrite open items beyond the deferred-line append.
- Does not auto-resolve Class B without diff confirmation, even on
  unambiguous owner answers.
- Does not back up CLARIFICATIONS.md before writing — git is the
  rollback mechanism.
- Does not write extraction artefacts (knowledge-note / soul-update /
  people-update) without the Class B diff gate — every Step 6.5
  approval still shows the full draft before commit.
- Does not propose principle candidates from owner conversation —
  global `constitution-capture` hook owns that path; Step 6.5 only
  surfaces hook fires as transparency, never duplicates capture.
- Does not edit hubs from extraction — `/minder:mem:maintain` linkage and
  lens action hints are the single source of hub writes.
- Does not loop modify-after-diff. Extraction `m` (modify) accepts
  one 1-line edit instruction; second wrong answer drops the proposal
  without recursive sub-menus.
- Does not change identity in `--auto-mode` — `entity-retire` /
  `entity-reclassify` are owner decisions, taken in an interactive session or
  not at all.
- Does not edit derived surfaces during an identity change — they regenerate
  via `/minder:mem:maintain` in Step 9.3.
- Does not touch immutable surfaces: raw sources, append-only state, lens
  output, manifests, and the body of any record. A record's prose mentioning a
  retired identifier is history, not residue.
- Does not run extraction in `--auto-mode` (no owner conversation),
  `--dry-run` (preview only), or `--no-extraction` (explicit opt-out).
