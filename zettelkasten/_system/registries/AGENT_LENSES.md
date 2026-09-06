# Agent Lenses Registry

Registry of agent-lens definitions. Each row points to a folder under
`_system/registries/lenses/{id}/` containing the lens prompt and any
companion files. To add a lens: create folder, add row, set status.
No skill-code changes required (same pattern as `SOURCES.md`).

## Concept

Agent lenses are **outside-view** observations the owner does not (yet)
make themselves. Each lens has a narrow intent (stalled threads,
stated-vs-lived gap, recurring reaction, etc.) and runs on its own
cadence under `/minder:mem:agent-lens`.

- Outputs land in `_system/agent-lens/{id}/{YYYY-MM-DD}.md` — one file
  per run, snapshot, never aggregated into a unified summary
- Each lens is independent — there is intentionally no cross-lens
  synthesis at the runner level. A meta-lens (`global-navigator`) reads
  other lenses' outputs but produces a digest of *pointers* (counts,
  ages, ids), not content
- All outputs are local to the owner

## Schema (lens frontmatter — required fields)

| Field | Values | Meaning |
|---|---|---|
| `id` | kebab-case slug | matches folder under `lenses/` and output dir |
| `name` | human title | shown in navigator |
| `type` | `mechanical` / `psyche` / `meta` | flavour — informs review cadence |
| `input_type` | `records` / `lens-outputs` / `multi-source` | drives which frame variant wraps the prompt. `records` = primary-source input (lens reads the Minder Memory base directly — records, knowledge, hubs, constitution, system; the lens prompt scopes which layer is primary). `lens-outputs` = meta-lens reads other lenses' outputs (status-page shape, no body-citation). `multi-source` = synthesis lens reads BOTH primary owner-data AND lens outputs with permission to synthesize across them; anchoring constraint applies (every owner-claim resolves to primary data) |
| `output_schema` | `standard` (default) / `synthesis-custom` | `standard` — Stage 2 reformats thinker output to canonical `## Observation N` schema; validator enforces. `synthesis-custom` — Stage 2 skipped; thinker writes directly to schema described in lens prompt; validator checks frontmatter privacy trio + non-empty body only. Lens prompt owns internal compliance (default-silence per section, anti-eye-roll guards). Chosen by any lens whose output shape is its own — synthesis lenses and narrators alike; a lens declares it in its own `prompt.md` frontmatter, which is the authority on which lenses use it. |
| `cadence` | `daily` / `weekly` / `biweekly` / `monthly` | scheduler runs it when due |
| `cadence_anchor` | `monday` / `sunday` / `1` (day-of-month) / `daily` | calendar anchor — see Cadence semantics below |
| `self_history` | `fresh-eyes` / `longitudinal` / `lens-decides` | NO default — must be explicit, lens fails registry validation otherwise |
| `status` | `draft` / `active` / `paused` / `archived` | scheduler runs only `active` (unless `--include-draft`); `paused`/`archived` rows MUST live under `## Paused/Archived Lenses` with required `Reason` per Archive Contract Form B (`_system/docs/SYSTEM_CONFIG.md`) |

Each lens folder MUST contain `prompt.md`. It MAY contain any number of
companion files (`what-counts.md`, `what-doesnt.md`, examples, anything).
The runner concatenates all `*.md` files in the folder, with `prompt.md`
first, the rest in alphabetical order. No fixed structure beyond
`prompt.md` being mandatory.

The lens prompt itself (in natural language) describes what to read,
what window to consider, and (if `self_history: lens-decides`) when to
look at past outputs. The runner does NOT constrain inputs — full read
access to the Minder Memory base is given.

## Cadence semantics

- `cadence: daily` → due every calendar day. `cadence_anchor` ignored
  (or set to `daily`).
- `cadence: weekly` → due on the day of week given by `cadence_anchor`
  (`monday`, `tuesday`, ...). If today matches anchor and last run was
  ≥6 days ago, run.
- `cadence: biweekly` → due every 14 calendar days, anchored to
  `cadence_anchor` day of week. First run defines the cycle.
- `cadence: monthly` → due on day-of-month given by `cadence_anchor`
  (`1`-`28`; values >28 clamp to 28).

**Catch-up policy:** if scheduler missed runs (laptop offline), the
runner does NOT replay missed days. It runs once for the current day
if due, and updates `last_run` to today. Missed days are gone — they
will be visible in `global-navigator` as gaps.

## Active Lenses

| ID | Name | Type | Input | Cadence | Self-history | Status |
|---|---|---|---|---|---|---|
| stalled-thread | Stalled Thread Detector | mechanical | records | weekly (mon) | fresh-eyes | active |
| stated-vs-lived | Stated vs Lived | psyche | records | biweekly (mon) | longitudinal | active |
| cross-domain-bridge | Cross-Domain Bridge | mechanical | records | weekly (thu) | longitudinal | active |
| decision-review | Decision Review | mechanical | records | monthly (1) | longitudinal | active |
| energy-pattern | Energy Pattern (records affect) | psyche | records | weekly (mon) | longitudinal | active |
| knowledge-emergence | Knowledge Emergence | mechanical | records | weekly (sat) | longitudinal | active |
| global-navigator | Global Navigator | meta | lens-outputs | weekly (mon) | longitudinal | active |
| weekly-insights | Weekly Insights | meta | multi-source | weekly (mon) | longitudinal | active |
| content-synthesis | Content Synthesis | meta | multi-source | weekly (mon) | longitudinal | active |
| cognitive-model | Cognitive Model | psyche | records | biweekly (mon) | longitudinal | active |
| opportunity | Opportunity | psyche | multi-source | weekly (fri) | longitudinal | active |

## Draft Lenses

| ID | Name | Type | Input | Cadence | Self-history | Status |
|---|---|---|---|---|---|---|
| biometric-anomaly-narrator | Biometric Anomaly Narrator | mechanical | records | daily | fresh-eyes | draft |
| biometric-cross-domain | Biometric Cross-Domain | psyche | records | weekly (thu) | longitudinal | draft |
| training-load-trend | Training Load Trend | mechanical | records | weekly (mon) | longitudinal | draft |
| biometric-life-synthesis | Biometric × Life Synthesis | meta | multi-source | weekly (mon) | longitudinal | draft |
| time-allocation | Time Allocation (computer-usage rhythm) | mechanical | records | weekly (mon) | longitudinal | draft |

## Lens summaries

Each active lens MUST have a summary block here — purpose / value / output format in 2-3 sentences each. This is what owner sees when scanning the registry; the full prompt lives in `lenses/{id}/prompt.md`.

### cognitive-model

Runs every other Monday. Mines the owner's own reasoning and reflection (`_records/observations` primarily) for **undeclared** patterns of how they think and want to be communicated with — structure of thought, insight-vs-noise judgement, what praise/criticism lands — and proposes them as `ai-interaction` / `learning` / `meta` principle candidates. The proactive head of the adaptation loop: where `stated-vs-lived` checks drift on EXISTING declarations, this generates NEW candidates from reflection. Output: pattern + ≥2 quoted records + why-it-is-new (which existing principle/SOUL section does NOT already cover it) + alternative reading + confidence, plus `principle_candidate_add` Action Hints (append to the high-recall buffer; owner gates promotion via `/minder:mem:lint` F.5). Conservative by design — 0-3 high-quality candidates, never a thin list. «No new pattern; existing principles + SOUL cover it» is a valid result. Self-history: reads `5_meta/mocs/hub-cognitive-model.md` as the axis coverage-map (which axes are `blank` vs `promoted`) before the per-run archive. Each candidate carries a `dimension` axis slug so the hub can show the axis `evidenced` before promotion.

### stalled-thread

Runs weekly on Monday. Surfaces topics the owner keeps returning to in records without resolution — what is rotating in his head but hasn't closed and hasn't graduated to a task / thread / hub. Output: list of threads with one-phrase framing + cited records + brooding-shape evidence + what is visible in the system as a next move (fix in OPEN_THREADS / open task / let go) + alternative reading + confidence. Action hints: `open_thread_add` when the brooding shape is unambiguous and the thread is absent from `OPEN_THREADS.md`.

### stated-vs-lived

Runs every other Monday. Compares what the owner declares (constitution + SOUL — values, goals, focus) against where attention actually goes in records over a window matched to the declaration's timescale. When `_records/activity/` is present it reads the **measured** lived-attention ledger (per-category / per-project hours, focus / rhythm) as the strongest lived-side signal — a declared goal with near-zero category-time is a hard action-gap, a barely-mentioned project with hours logged is a priority-shift. Output: declaration quote + multiple lived-side signals (count + completion + emotional energy + measured time) + three parallel readings (action gap / priority shift / stale declaration) with markers + confidence — owner judges which reading holds. No Action Hints — the gap is a reading for the owner to judge, not a structural change.

### cross-domain-bridge

Runs weekly on Thursday. Searches for connections the owner thought about independently in different life domains without noticing the structural overlap — defends Minder Memory's flagship value (highest-value insights at domain boundaries) by surfacing what context-lock makes the owner himself miss. Output: one-sentence claim + two endpoint records (path + cited framing each) + which of 4 signals fired (relational match / matrix independence / cluster disjointness / nameable claim) + a falsifier («this would NOT be a bridge if…») + confidence. Action hints: `wikilink_add` for the endpoint pair, only when both endpoints are in the knowledge layer.

### decision-review

Runs monthly on the 1st. Primary concern: takes substantive decisions 90-180 days old, extracts the assumptions / alternatives / expected outcome (from explicit sections OR embedded prose / TENTATIVE flags / Открытые вопросы), and checks whether records after the decision date confirm or disconfirm each assumption. Output: decision (path + date + one-line subject) + per-assumption verdict (confirmed / disconfirmed / open with cited records) + net call (held / drifted / mixed) + alternative reading + confidence. Top-3 most material per run; assumption-level scoring only — owner judges decision-quality. Edge case `hits: 0` differentiated by reason: «base too young», «present but not extractable», «extractable but no records-evidence». **Additive sub-concern (Skill-telemetry):** reads `/minder:mem:check-decision` audit substrate (`_system/state/check-decision-runs.jsonl`) in two layers — Layer A enriches per-decision observations with skill-verdict at decision-time when `record_ref` exact-matches; Layer B adds 0-3 standalone observations on rolling 30-day telemetry (constitution coverage gap, principle utilization, skill stability anomaly). Sub-concern claims agent-usage patterns only, never about owner; skipped entirely when substrate is empty. Action hints: `decision_update_section` when a decision note with declared assumptions has accumulated fresh evidence since its last `## Update`.

### energy-pattern

Runs weekly on Monday. Surfaces verbatim affect-markers from owner's voice-note records over a 14-day window and compares them against the SOUL Working Style baseline («Заряжает / Истощает / Выводит из себя») and the previous window — targeting **shifts** in distribution, not absolute mood. Records-only by design; behavioral (ActivityWatch) rhythm lives in the sibling `time-allocation` lens, deep physiological (Garmin somatic) stays a future sibling. Hit requires ≥3 markers distributed across ≥2 different records (no single-session venting bursts) OR a polarity crossing relative to baseline. Output: pattern + verbatim quotes (path + date) + shift framing (vs prev / vs SOUL) + three readings (action gap / baseline shift / episode) + confidence (high requires 2+ consecutive windows confirming). «No shift, baseline confirmed» is a valid output, not failure. No Action Hints — informational by design.

### time-allocation

Runs weekly on Monday — the behavioural twin of `energy-pattern` (attention in facts, not affect in words). Narrates **shifts** in the owner's computer-usage rhythm from the deterministic substrate already on each `_records/activity/{source}/` record — `## Baseline Deviations` + `## Active Streaks` over a 14-day window vs the prior window and vs the owner's SOUL-declared work-rhythm goals (read at runtime, not hardcoded). The metrics are Focus-Engineering-grade: `focus_score` / `productivity_score` (0-100), `human_switches` (genuine fragmentation — productive AI-coding churn split out into `ai_assisted_*` upstream, so switch-spikes on Claude-Code nights don't false-flag), `top_death_loop` (the attention-leak app-pair with verdict, already computed), plus deep-work / late-night-work / early-morning-shift / meeting-overload streaks. Cross-references same-week `_records/biometric/{source}/` for body co-occurrence (late-night/meeting-heavy week ↔ readiness/REM) under strict n=1 caveats. Output schema: `synthesis-custom` — Week shape / Facts (cited records) / Patterns / ranked Hypotheses (three readings: action gap / baseline shift / episode) / mandatory Counter-evidence / one falsifiable experiment / optional Memory note. First-run writes a baseline snapshot with `hits: 0`; «No shift, rhythm baseline holds» is a valid output. No Action Hints (informational, like its sibling `energy-pattern`).

### knowledge-emergence

Runs weekly on Saturday — primary input is the **knowledge layer** (`1_projects/`, `2_areas/`, `3_resources/`), not records. Surfaces themes / framings recurring across ≥3 knowledge notes that have no hub yet (or have a mismatched hub — too general / too narrow / split candidate). Defends Layer 3 (hubs) growth against passive owner-noticing: promotion knowledge → hub becomes an active observation, not a quiet drift. Output: one-sentence promotion claim + 3+ cited knowledge note paths + relational structure name + signal tally (recurrent / hub-absence / cross-PARA / independent-derivation, ≥2-of-4) + hub verdict (new-hub / split-existing / extend-existing / unclear) + falsifier + confidence + recurrence classification (new / stable / fading) + counter-evidence. Never recommends action — owner decides whether to promote. Action hints: `hub_stub_create` when a cluster of ≥3 independent knowledge notes has no hub covering it.

### global-navigator

Runs weekly on Monday — short status page for the **whole engine** over a trailing 7-day window ending the prior day (Mon-Sun calendar week): agent-lens layer (every active lens auto-discovered from this registry, including new ones), `/minder:mem:process` activity (batches + BATCH_LOG sums), `/minder:mem:lint` activity (F-codes + gaps), `/minder:mem:maintain` runs, candidate buffers (principle + people append counts by origin), CLARIFICATIONS state (new + open + by type), OPEN_THREADS delta. Output sections: stuck/failing → outstanding observations (by age) → lint → process → maintenance → candidates → clarifications → open-threads → productive lenses → silent lenses (only if non-empty) → aggregate counter; verbatim short titles, F-codes, batch-ids, type labels, counts only — no claims about the owner's life, no recommendations, no body-citation of any second-order content (observation bodies, candidate bodies, clarification quotes). Action hints: any whitelisted type, when cross-lens convergence makes an engine-level proposal warranted; the body-citation rule is relaxed inside the trailer only.

### biometric-anomaly-narrator

Runs daily — narrates yesterday's biometric record when at least one of `## Baseline Deviations` / `## Categorical Events` / `## Active Streaks` / `## Streak Transitions` is non-empty; otherwise outputs «Yesterday clean — no signal» and returns. Single-day frame → most outputs land at `weak` (question form) or `medium` tier. Bridges with same-day journal observations / meetings when the deviation has narrative context. Output schema: `synthesis-custom` per biometric-lens-protocol §«Output structure» (Facts / Patterns / Hypotheses-ranked / Counter-evidence / Suggested experiment / Memory note). Action hints: `wikilink_add` (record ↔ same-date journal), `open_thread_add` only if ≥4-day strong streak with actionable journal context.

### biometric-cross-domain

Runs weekly Thursday — narrates the top 1–2 strongest cross-domain findings from Tier II (`_system/state/biometric/{source}/correlations-{recent}.json` Phase 2: biometric × affect lexicon, plus Phase 1 cross-source), reading across every device namespace. Diagnostic gate: n ≥ 10 AND effect_size ≥ 0.5 → diagnostic statement permitted; below → tentative or question form. Counter-evidence + falsifier mandatory. Empty output («No cross-source findings this week above noise») is a valid result. Output schema: `synthesis-custom`. Action hints: `wikilink_add`, `open_thread_add` if pattern strong + actionable.

### training-load-trend

Runs weekly Monday with **conditional execution**: if last 14 days of biometric records show `acute_load == 0` for all days, outputs «No training activity in window — skipping» and returns immediately. Otherwise surfaces train_status transitions (DETRAINING / MAINTAINING / PRODUCTIVE / PEAKING / OVERREACHING), ACWR drift escapes from OPTIMAL, sustained zones >2 weeks. Garmin-pinned (training-load has no Oura equivalent): reads last 28 days of `_records/biometric/garmin/` Key Numbers only. Output schema: `synthesis-custom`. Action hints: `open_thread_add` only if overreaching OR sustained detraining ≥3 weeks.

### biometric-life-synthesis

Runs weekly Monday — flagship multi-source synthesis. Reads all 4 biometric lens outputs from past 7 days, Tier II correlations + weekly view, INDEX (week-faceted activity), this week's records, OPEN_THREADS, SOUL Focus, recent stated-vs-lived + energy-pattern outputs. Synthesises week-shape (meeting count / conflict markers / late-work markers / workouts), convergent/divergent patterns, ranked hypotheses (with biometric + journal anchoring), counter-evidence, one falsifiable suggested experiment, optional Memory note when strong tier (n≥10, effect≥0.5) reached. Anchoring constraint: every claim resolves to primary owner-data; lens output alone is hypothesis-grade. Output schema: `synthesis-custom`. Action hints: `wikilink_add`, `open_thread_add`, `decision_update_section` on stated-vs-lived gap.

### weekly-insights

Runs weekly on Monday — synthesis lens with `input_type: multi-source` and `output_schema: synthesis-custom`. Reads primary owner-data (records — including the biometric **body** and activity **attention** weekly views, knowledge, hubs, constitution, SOUL, operational layers, posts, people), engine state (CLARIFICATIONS, OPEN_THREADS, CURRENT_CONTEXT, indexes, runs / logs), other lenses' outputs, and own past insights (longitudinal). Synthesizes across them into a **variable-N theme-block digest** (not a fixed section list — as many blocks as it actually sees, each in the block-form that fits: mechanism-reveal / contradiction / drift-trajectory / bottleneck / naming / reference-class forecast / watch) the owner reads as a single file: convergence between lenses, drift between declaration and lived life, where movement is blocked, patterns not yet named, counter-evidence to the owner's narrative — plus a diagonal-read summary, a claim-giving table-of-contents, and one margin question. Default-silence per section is load-bearing — an empty theme is signal, not failure. **Opportunity DRY handoff:** standalone opportunities, serendipity, retro-fate and forks are owned by the `opportunity` lens (SoT); weekly-insights **reads** its output and surfaces opportunity-material only at convergence with another week-signal — it does not independently forecast standalone opportunities. **Strictly informational** — produces no actions, no auto-applies, no clarifications. Owner reads, owner decides what to do (if anything). Anchoring constraint: every claim about the owner resolves back to primary owner-data; lens output alone is hypothesis-grade, never the basis for a claim.

### opportunity

Runs weekly on Friday — **new-first** opportunity lens with `input_type: multi-source` and `output_schema: synthesis-custom`. Reconciles the owner's routine (what happened) with far-goals (SOUL `## Active Goals` / `## Current Focus` + constitution). The owner comes to see **what opportunities emerged or shifted THIS week**, so new leads first; the open-doors change-layer supports it. Four sections: (1) **new opportunities of the week** — every event/node that clears the quality bar (real signal + falsifier + not role-routine), **no artificial cap**, each with a branch (reasoning-type trust: deduction > chain > analogy > abduction, in plain language) + optionality (bounded downside + doors-opened) + a one-week cheap test (effectuation — keeps "new" from meaning "new rabbit hole"); (2) **serendipity** — a weak tie who entered orbit this week (structural distance outside the work hierarchy mandatory, mobilizable resource → goal, observational never instrumental, validation ≠ door); (3) **what changed in open doors** — delta-focused retro (advanced / running N weeks + what changed / decayed / closed / absorbed; a materially-changed old door is promoted into the current reading; scoped table + one decay aggregate, not a 150-note wall; frozen priors vs hindsight), plus a **soft execution mirror** — one dry line, only if the SOUL documents an execution-gap pattern AND ≥3 doors decayed (data, never reproach, never the lead); (4) fork (course-choice by reversibility). **Output contract: self-contained + jargon-free** — reads cold (the owner won't remember who a person is or what a conversation was), so every item carries its own who/what/when in plain language, no service or academic terms, no bare references. `hits: 0` («nothing new, open doors unchanged») is a valid honored output. Action Hints: `open_thread_add` only for a concrete external follow-up (contact + return-date). Deferred: `owner_question` primitive (separate ADR). DRY handoff — `weekly-insights` reads this lens's output instead of forecasting opportunities itself.

### content-synthesis

Runs weekly on Monday — the **sole classifier of the content pipeline**. Reads the compact `CONTENT_MAP.md` (themes by ripeness — its primary input), the content ledger, sibling lens outputs (especially `cross-domain-bridge` for cross-theme post candidates and `knowledge-emergence` for post-ready clusters), POSTS.md (anti-repetition + cross-link), and the constitution/SOUL for voice, drilling into note bodies only for the top themes. Classifies each theme against the ledger by ripeness **change** — new / strengthened / stable / published-out — so a theme seeded months ago resurfaces the moment a new note lifts it (the long tail is preserved). Surfaces, with no cap, two equal kinds of candidate: single-theme posts and cross-theme bridges (taken from the `cross-domain-bridge` output, not mechanical pairing, each with an explicit falsifier). **Observation only** — never writes a draft, never publishes; the draft-maintainer (`/minder:mem:content --maintain`) reads this output directly the next day and is the sole actor. Output schema: `synthesis-custom`. Echo-loop guard (re-derive ripeness from the map each run) + apophenia falsifiability guard (cross-theme) carried from `knowledge-emergence` / `cross-domain-bridge`. No Action Hints — the maintainer is its dedicated consumer.

## Frameworks behind the calibration

Each lens prompt is calibrated against external frameworks (cited inline in the prompt body where applicable):

- **stalled-thread**: GTD open-loops + Nolen-Hoeksema brooding/pondering + Matuschak incubation
- **stated-vs-lived**: ACT VLQ + Higgins self-discrepancy + MI tone + Argyris-Schön espoused-vs-in-use
- **cross-domain-bridge**: Gentner structure-mapping + Koestler bisociation + Granovetter/Burt structural holes + Luhmann/Matuschak nameable-claim + apophenia falsifiability guard
- **decision-review**: Kahneman/Klein post-mortem discipline + Argyris double-loop learning + Tetlock superforecasting (assumption-level scoring, not overall decision-rightness)
- **energy-pattern**: ESM (Csikszentmihalyi) episode-level affect + Higgins ideal/ought self-discrepancy lexicon + ACT lived-vs-lived comparison
- **global-navigator**: SRE Four Golden Signals + USE method + Tufte data-ink + multi-doc summarisation hallucination research
- **knowledge-emergence**: Luhmann Folgezettel (thematic anchor on ≥3 sister-notes) + Matuschak evergreen promotion ladder + Weick retrospective sensemaking + apophenia falsifiability guard
- **weekly-insights**: Bayesian belief-update + falsification + Munger inversion / pre-mortem + Kahneman reference-class forecasting + de Shazer solution-focused exception finding + Higgins self-discrepancy + Argyris-Schön espoused-vs-in-use + Theory of Constraints (bottleneck) + apophenia falsifiability guard + multi-doc summarisation hallucination research (anti-eye-roll guards on every section, default-silence load-bearing)
- **cognitive-model**: metacognition + cognitive-styles (analytic-vs-holistic, need-for-cognition, systemising) + Communication Accommodation Theory + trait-vs-state distinction + dual-process (System 1/2) + Argyris-Schön espoused-vs-in-use (shared with stated-vs-lived, opposite lane: undeclared vs drift) + anti-sycophancy guard against mining-for-comfort (no-sycophancy / rails-not-boxes rule in `communication-baseline`)
- **opportunity**: real options / Taleb antifragility (optionality asymmetry) + Sarasvathy effectuation (bird-in-hand / affordable-loss, antidote to causation-logic over-research) + Granovetter weak ties + Burt structural holes / brokerage (bridge two worlds) + Lin social capital (mobilizable embedded resource) + Krumboltz-Mitchell planned happenstance + Merton-Barber prepared-mind serendipity + Wald survivorship bias + Fischhoff hindsight bias (frozen priors) + Kahneman-Tversky prospect theory (decay as data not reproach) + March exploration-exploitation / Charnov Marginal Value Theorem (execution-gap antidote) + Dixit-Pindyck real-options irreversibility (fork) + Casciaro networking-morality guard (non-instrumental relationships) + apophenia falsifiability guard (shared with cross-domain-bridge)

## Operating principles

- Lenses are pure outside-view-of-life. System-health concerns (CLARIFICATIONS flow, lint context store, log audit) belong to `/minder:mem:lint` and `/minder:mem:maintain` and are deliberately not mixed in here.
- Numeric thresholds inside prompts are starting points, not hard limits. The thinker LLM has full base read access and license to widen windows when the pattern asks.
- Domain assumptions are owner-defined per `ENGINE_DOCTRINE.md` §1.5 — no hardcoded work/personal binary.
- The active lenses cover several observation flavours (within-records / records-vs-declarations / across-domains / decision-feedback-loop / affect-distribution / system-meta). They are not exhaustive; owners grow their own set via `/minder:mem:agent-lens-add`.
- Auto-pause safety net active: 3 consecutive validator rejections of any lens → runner flips status to `paused` (per `minder-mem-agent-lens/SKILL.md` §5.5).

## Paused/Archived Lenses

Lenses with `status: paused` or `status: archived`. Per Archive Contract Form B (`_system/docs/SYSTEM_CONFIG.md`), every row carries a `Reason` cell — free-form one-sentence rationale. Forward-only: lenses paused before contract adoption are not backfilled. Auto-pause writer (`/minder:mem:agent-lens` Step 5.5, after 3 consecutive validator rejections) populates Reason as `"auto-pause: 3 consecutive validator rejections"`.

| ID | Name | Type | Input | Cadence | Self-history | Status | Paused | Reason |
|---|---|---|---|---|---|---|---|---|
| _(empty)_ | | | | | | | | |

## Output discipline

- One file per run, dated `{YYYY-MM-DD}.md` in `_system/agent-lens/{id}/`
- Empty result (`hits: 0`) → file IS written (with `## Reasons` section)
  to keep the run trail uniform; absence of file means the run never
  happened, not that it found nothing
- Every run (success / empty / rejected) appends one line to
  `_system/state/agent-lens-runs.jsonl`
- Rejected outputs are saved at
  `_system/state/agent-lens-rejected/{lens-id}/{run_at}.md` for owner
  inspection; not written to the canonical output dir
- Output schema enforcement depends on the lens's `output_schema` field:
  - `standard` (default) — Stage 2 **structurer pass** (separate cheap
    LLM call) reformats free-form thinker output to canonical
    `## Observation N` schema; structural validator then enforces.
    The thinker writes free-form
  - `synthesis-custom` — Stage 2 is **skipped**; the thinker writes
    final output directly per the schema described in the lens
    prompt. Validator checks frontmatter privacy trio + non-empty
    body + cited path resolution. The lens prompt owns its internal
    section structure and analytical guards (default-silence per
    section, anti-eye-roll constraints, etc.)
  See `lenses/_frame.md` for both stages and the validator branches
- **Action Hints (optional trailer).** Lenses MAY append an
  `## Action Hints` section after the canonical body proposing
  structural changes (`wikilink_add`, `hub_stub_create`,
  `open_thread_add`, `decision_update_section`,
  `principle_candidate_add`). The trailer is
  consumed by `/minder:mem:resolve-clarifications --auto-mode` (dispatched
  inline by lint Step 7.5 at the nightly lint tick, ~2 h after
  agent-lens writes its outputs): the resolver judges every hint against full owner
  context and either auto-applies safe additive proposals or queues
  for owner review with rich smart_resolve reasoning. Schema +
  per-lens emission stance: `lenses/_frame.md → Action Hints
  (optional trailer)`. The Stage 3 validator does NOT parse the
  trailer; the resolver's deterministic parser handles malformed
  entries with drop-and-log. **Whether a lens emits hints is stated on
  its own row below**, with the action set it may propose and the
  condition under which it proposes it — that row is the authority, not
  a list kept here. A lens emits hints when its finding implies a
  structural change the base should absorb; a lens stays silent when its
  output is informational by design, or when a dedicated consumer other
  than the resolver already reads it.

## `agent-lens-runs.jsonl` schema

One JSON object per line, append-only:

```json
{
  "lens_id": "stalled-thread",
  "run_at": "2026-04-30T06:00:00Z",
  "status": "ok | empty | rejected | error",
  "hits": 2,
  "output_path": "_system/agent-lens/stalled-thread/2026-04-30.md",
  "rejection_reason": null,
  "duration_seconds": 47.2
}
```

- `status: ok` → output written, `hits > 0`
- `status: empty` → output written, `hits == 0`
- `status: rejected` → validator rejected, output in `state/agent-lens-rejected/`
- `status: error` → runner couldn't even produce output (LLM error, file IO);
  `rejection_reason` carries cause

## Privacy

All lens outputs are owner-local. They live under `_system/agent-lens/`
and `_system/state/agent-lens-rejected/` and are committed to the same
private repo as the rest of the Minder Memory base.

**Privacy trio on lens-observation entities** (per
`/minder:mem:agent-lens` SKILL Step 5.9). Every observation file carries:

- `origin: personal` — lens runs internal to the owner; never `work`
  (would risk leaking to a future work-team sync) or `external`.
- `audience_tags: []` — owner-only by construction. Engine never
  widens automatically; owner curates if a specific lens result is
  worth sharing.
- `is_sensitive: false` by default; `true` if the lens prompt
  explicitly surfaces sensitive patterns (relationship/conflict
  observations) — set via lens registry `output_sensitivity` field
  when added; default `false` otherwise.

If a lens output references concepts by name, the names are
normalised through `_common.py::normalize_concept_name()` at write
time — same autonomous-resolution contract as `/minder:mem:process` Q15
(silent autofix or silent drop; never raises CLARIFICATION).

**Search isolation is deferred.** A future phase will set up a separate
QMD index for lens outputs so they remain accessible to the owner via
`/minder:mem:search` but do not contaminate other skill sessions (e.g.
`/minder:mem:process` reading hypothesis-grade observations as if they were
records). For now: no search-side exclusion. Other skills that perform
content search (`/minder:mem:lint` Scan F.x, `/minder:mem:bootstrap`) MUST exclude
`_system/agent-lens/` and `_system/state/agent-lens-rejected/` paths
explicitly. This requirement is documented here and enforced by each
skill's own scope rules.

## Lock matrix

Doctrine for cross-skill lock matrix: `_system/docs/ENGINE_DOCTRINE.md`
§3.4. Implementation (which locks to read, in what order, abort
messages): `integrations/claude-code/skills/minder-mem-agent-lens/SKILL.md`
Step 0.2.

Lock file: `_sources/.agent-lens.lock` (consistent with other Minder Memory
skill locks).

## Registry validation

Loaded by `/minder:mem:agent-lens` at the start of each tick. Each lens row
must satisfy:

- Folder `_system/registries/lenses/{id}/` exists and contains `prompt.md`
- Frontmatter parses; all required fields present
- `id` matches folder name
- `id` is unique across registry
- `cadence` ∈ allowed set; `cadence_anchor` matches `cadence` (e.g.
  `weekly` requires day-of-week, `monthly` requires day-of-month)
- `self_history` is one of three explicit values (no default)
- `input_type` is one of two values (`records` = primary-source-input, the
  lens reads the Minder Memory base directly with the lens prompt scoping which
  layer is primary; `lens-outputs` = meta-lens reading other lenses'
  outputs)

Failures: registry-level (table malformed) → abort tick, write
CLARIFICATION. Lens-level (one lens malformed) → skip that lens with
log entry, continue with remaining lenses.

## Lens lifecycle

**Default posture — a new lens ships `active`.** Every lens is on by default so
its value reaches the owner without a manual flip. `draft` is reserved for a lens
that is *explicitly gated*: prerequisite-gated (needs source data the base may not
have — e.g. biometric records from a health-collector adapter), or an owner
opt-out ("let me preview it first"). Absent an explicit reason, create the lens
`active`. The runner's own safety net (validator rejection → auto-pause after 3
consecutive strikes) protects an active lens whose prompt turns out weak, so
active-by-default is not a quality risk.

- **draft** — explicitly gated (prerequisite-gated or owner opt-out); NOT in
  scheduled `--all-due` runs, reachable only via `--include-draft` or
  `--lens <id>` for manual dry-run
- **active** — included in scheduled `--all-due` runs (the default for a new lens)
- **paused** — manually paused by owner, OR auto-paused by runner after
  3 consecutive validator rejections; not run until owner flips to
  `active`. Row MUST be moved to `## Paused/Archived Lenses` with
  populated `Reason` per Archive Contract Form B
- **archived** — permanently retired by owner; row lives under
  `## Paused/Archived Lenses` with populated `Reason`

To activate a draft lens: dry-run via `/minder:mem:agent-lens --lens <id>
--dry-run` until output is satisfactory, then change status to `active`
in this file.

## Adding a new lens

**Recommended:** use `/minder:mem:agent-lens-add` — Socratic interview wizard that
generates a complete lens (prompt + registry row) with validation and
push-back on vague intent / missing anti-examples / duplicate of
existing. See `integrations/claude-code/skills/minder-mem-agent-lens-add/SKILL.md`.

**Manual (if you want to skip the wizard):**

1. Create folder `_system/registries/lenses/{new-id}/`
2. Add `prompt.md` with required frontmatter (see Schema above), `status: active`
   — the default posture (ship `draft` only if the lens is prerequisite-gated or
   you deliberately want to preview it before it joins the schedule)
3. Add the row to the `Active Lenses` table in this file (or `Draft Lenses` if you
   deliberately gated it in step 2)
4. Add a 2-3 sentence summary block under `## Lens summaries` (purpose / value / output format) — required for every active lens
5. Recommended before the next scheduled run: dry-run via
   `/minder:mem:agent-lens --lens {new-id} --dry-run` and iterate the prompt until the
   output is good — an active lens that misfires self-pauses after 3 validator
   rejections, but a dry-run catches it sooner

No skill code changes required either way.

## Open items

- QMD search-isolation deferred to a follow-up phase (see Privacy
  section). For now: `_system/agent-lens/` and
  `_system/state/agent-lens-rejected/` MUST be excluded explicitly
  by any other skill that performs full-base content scans
- Lens content calibration (per-lens prompt fine-tuning) — owner-driven
  iteration based on first real scheduled outputs. Auto-pause after
  3 consecutive validator rejections per lens is the safety net
