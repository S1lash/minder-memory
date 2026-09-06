---
name: minder:mem:bootstrap
description: >
  One-shot populator for Minder Memory system files on an existing Zettelkasten base.
  Scans all records and knowledge notes, counts person mentions, assigns PEOPLE.md tiers,
  extracts active and resolved threads from the last 4-8 weeks, drafts SOUL.md from
  ~/.claude/CLAUDE.md + recent focus signals, generates CURRENT_CONTEXT snapshot.
  Disposable — after first run incremental updates are handled by /minder:mem:maintain and
  /minder:mem:lint. Keep for onboarding a new user, disaster recovery, or major refactor.
  NOT in cross-skill lock matrix — user ensures system idle before running.
disable-model-invocation: false
---

# /minder:mem:bootstrap — One-Shot Populator

Disposable one-shot populator for Minder Memory system files on an existing base.

**Cross-skill:** bootstrap is NOT in the `process/maintain/lint` lock matrix. User
ensures no other skill is running before invocation. Bootstrap writes `log_maintenance.md`;
operationally this runs once at system init (or disaster recovery / friend onboarding),
so race with concurrent skills is not an operational concern.

**Philosophy:** Never decide silently. At any confidence gap — log a question to
`_system/state/CLARIFICATIONS.md` (HARD RULE from SYSTEM_CONFIG.md) and use a conservative default.

**Disposable:** after the first run, incremental upkeep is `/minder:mem:maintain` (after each batch)
and `/minder:mem:lint` (nightly). Keep this skill for:
- Onboarding a friend (their Minder Memory with imported records)
- Disaster recovery if system files are corrupted
- Major refactor (structure changes → recompute from scratch)

**Documentation convention:** при любых edits этого SKILL соблюдай `_system/docs/CONVENTIONS.md` — файл описывает current behavior без version/phase/rename-history narratives.

---

## Arguments

`$ARGUMENTS` supports:
- `--dry-run` — report what would be done, write nothing
- `--skip-people` — keep existing PEOPLE.md tier/mentions untouched
- `--skip-threads` — skip OPEN_THREADS detection
- `--skip-soul` — do not regenerate SOUL.md draft (assume user filled it)
- `--skip-raw-scan` — skip raw transcript scan of `_sources/inbox/` + `_sources/processed/` (see Step 1.5). Disables ALL four signal classes.
- `--skip-projects` — skip Step 3.5 PROJECTS.md seeding (people / hubs / principle candidates still run)
- `--skip-hub-candidates` — skip Step 4.5 hub-candidate clustering
- `--skip-principles` — skip Step 1.5 signal 4 (do not append to principle-candidates.jsonl)
- `--raw-scan-only` — force a raw-only scan even when structured signal exists (friend onboarding, disaster recovery)
- `--threads-window <N>` — weeks to scan for active threads (default: 6)
- `--with-starter-axioms` — opt-in: copy generic starter axioms from
  `5_meta/starter-pack/axioms/` into `0_constitution/axiom/{domain}/`
  as drafts. Default OFF — friend's constitution should grow from
  their own captured candidates, not from inherited principles. See
  Step 2.5 below

---

## Operating Modes

Bootstrap auto-detects its mode based on current Minder Memory state. No mode flag needed
unless user forces via `--raw-scan-only` or `--skip-raw-scan`.

| Mode | Trigger | Primary signal | Raw scan role |
|---|---|---|---|
| **Established** | `_records/` + PARA have files with rich `people:` frontmatter | Structured frontmatter (authoritative counts) | Catch-up: flag new names in inbox/processed not yet in registry (CLARIFICATIONS) |
| **Fresh onboarding** | No records, no knowledge notes, only transcripts in `_sources/inbox/` | Raw transcript text (LLM extraction) | Primary — everything comes from raw scan + user's profile file if any |
| **Mixed** | Both structured notes AND pending inbox transcripts | Structured (primary) + raw (secondary) | Incremental: add new people from inbox to CLARIFICATIONS before first `/minder:mem:process` |

**Fresh-clone onboarding use case (explicit):** new user clones the
skeleton, optionally drops transcripts into `_sources/inbox/`, then runs
`/minder:mem:bootstrap` BEFORE any `/minder:mem:process`. Skill conducts the SOUL
interview (Step 2 primary path), seeds PEOPLE/OPEN_THREADS drafts from
raw content (if any). User reviews CLARIFICATIONS, then runs
`/minder:mem:process` for first real batch.

---

## Preconditions

Before running, verify:

1. `_system/docs/batch-format.md` exists → если нет, abort — базовая структура Minder Memory не инициализирована
2. `_system/SOUL.md`, `OPEN_THREADS.md`, `CURRENT_CONTEXT.md`, `log_maintenance.md`, `BATCH_LOG.md`, `batches/` existence
3. `_system/state/CLARIFICATIONS.md` exists и writable
4. `3_resources/people/PEOPLE.md` существует — skilll модифицирует его, не создаёт

---

## Step 0: Pre-flight checks (fresh-clone orchestration)

This skill is the **canonical orchestrator** for first-time onboarding
on a fresh skeleton clone. The user did `install.sh` + invoked
`/minder:mem:bootstrap` — everything else is on the skill. Before any work,
detect missing inputs and ask the user inline how to proceed. Do NOT
silently start scanning when key inputs look absent — the user almost
certainly meant to provide them.

Run these checks in order. Each check that fails → ask the user once,
record the answer, continue. Multiple failures → batch them into ONE
question with numbered options when possible.

### 0.1 Mode detection

Run mode detection from Step 1 first. The pre-flight prompts below
adapt based on whether mode is `established`, `mixed`, or
`fresh-onboarding`. On `established` mode skip 0.2–0.4 (the user is
not in first-time onboarding).

### 0.2 Transcript backlog check (fresh / mixed only)

Glob `_sources/inbox/**/*.md` and `_sources/processed/**/*.md`. If
total transcript count < 5 AND mode is `fresh-onboarding`:

> **Found {N} transcripts in your sources.** Bootstrap's signal
> extraction (people, projects, hubs, principles) needs raw material —
> below ~10 transcripts the registries will be near-empty. Choose:
>
> 1. **Pause now.** Drop your backlog (voice-recorder transcripts,
>    journal exports, past notes) into the matching `_sources/inbox/{id}/`
>    folder for each active source declared in `_system/registries/SOURCES.md`,
>    then re-invoke `/minder:mem:bootstrap`. If you need a source that does not
>    exist yet, run `/minder:mem:source-add` first.
> 2. **Proceed anyway** — identity-only path. Useful if you genuinely
>    have no backlog and want to start fresh from `/minder:mem:capture-candidate`
>    + future `/minder:mem:process` runs.
> 3. **Cancel.**

Record the choice in log_maintenance.md.

### 0.3 Profile check (fresh / mixed only)

Read `_sources/inbox/describe-me/*.md` (recursive) and
`_sources/processed/describe-me/*.md`. Apply the
template-default detection from Step 2.1. If no non-template profile
file found:

> **No describe-me profile found.** Bootstrap can either:
>
> 1. **Pause** so you can copy
>    `_sources/inbox/describe-me/PROFILE.template.md` to `PROFILE.md`
>    (same folder) and fill the copy (or paste an AI-generated draft
>    per the template's prompt). Re-invoke when ready. This is the
>    highest-quality path — the profile is the primary source for
>    SOUL.md.
> 2. **Run a short interview now** — I'll ask 3–5 questions to seed
>    SOUL.md Identity / Values / Working Style. Faster but lower
>    fidelity than a written profile.
> 3. **Skip identity** — proceed with a minimal `Name: <unset>` SOUL
>    and let it accrete over time via `/minder:mem:lint` and manual edits.

Record the choice. If (1), abort the skill cleanly; do NOT partially
run.

### 0.4 Install sanity (any mode)

Verify `~/.claude/skills/minder-mem-bootstrap/` (or wherever the user's
`CLAUDE_HOME` points) symlink resolves into THIS repo. If the skill is
loaded from a different path (e.g. another instance), surface a
warning:

> **Install path mismatch.** The skill is loaded from `{path}` but
> this repo is at `{repo}`. If you have multiple Minder Memory instances, this
> may cause writes to land in the wrong tree. Re-run
> `bash integrations/claude-code/install.sh` from this repo, then re-
> invoke. Continue anyway? (y/n)

This catches the common «cloned a new instance, forgot to re-install»
mistake.

### 0.5 Skill collision (any mode)

Check `_sources/.processing.lock`, `_sources/.maintain.lock`,
`_sources/.lint.lock`. Bootstrap is not in the cross-skill lock
matrix, but a stale lock from a prior run is a strong signal that
another skill crashed mid-flight. If found > 2 hours old, surface:

> **Stale lock found:** `_sources/.{maintain,lint,process}.lock`
> ({age}). A previous skill run may have crashed. Inspect and
> consider deleting before continuing.

### 0.6 Pre-flight summary + doctrine transmission

After all checks pass / are answered, surface a one-screen frame +
plan to the owner. The frame block is the **doctrine transmission** —
the only moment where the owner explicitly sees what their system
operates by. Skip ONLY in `established` mode (owner already runs
this — re-stating the frame is noise).

For `fresh-onboarding` and `mixed` modes:

> **The frame your system runs by**
>
> Minder Memory is your second consciousness — not an archive, not a TODO list.
> Three layers store knowledge: records (what happened), knowledge
> notes (what it means), hubs (how understanding evolves). A fourth
> layer — your constitution — governs how skills reason on your behalf.
>
> Eight processing principles guide every judgement: capture first
> (filter never), weight by structure (don't discard), look for
> connections (causal / evolutionary / structural), cross domain
> boundaries (where the highest-value insights live), accumulate
> (don't deduplicate), capture both action and knowledge, capture
> every deliberate person mention, preserve texture and narrative.
>
> Three rules every skill enforces: **surface, don't decide silently**
> (CLARIFICATIONS over guesses); **inclusion bias on capture, curation
> on promotion** (cheap to add, expensive to canonise); **idempotency**
> (re-runs add or surface, never overwrite your edits).
>
> Long-form: `_system/docs/ENGINE_DOCTRINE.md` (auto-loaded in every
> session via `~/.claude/rules/minder-memory-engine-doctrine.md`). The frame
> persists from this point — every future `/minder:mem:process`, `/minder:mem:lint`,
> `/minder:mem:maintain` operates against it.
>
> ---
>
> **Bootstrap plan**
>
> - Mode: {fresh-onboarding | mixed | established}
> - Transcripts to scan: {N} (chunked into ~{C} parallel waves)
> - Profile source: {describe-me/PROFILE.md | interview | skip}
> - Starter axioms: {yes via --with-starter-axioms | no}
> - Estimated wall-clock: {~10–20 minutes for fresh-onboarding with
>   100 transcripts on Opus}
>
> Proceeding. CLARIFICATIONS will be written to
> `_system/state/CLARIFICATIONS.md` for your review at the end. No
> further prompts during the scan — review at the exit summary.

---

## Pipeline

### Step 1: Load Context

Read for context (read-only). Doctrine sources first — these calibrate
every judgement made later in the pipeline.

**Doctrine (load FIRST, before any data):**

- `zettelkasten/_system/docs/ENGINE_DOCTRINE.md` — engine
  operating philosophy. **Authority is binding** — every Step in this
  skill operates against this frame. If a Step's behaviour appears to
  conflict with doctrine, raise a `process-compatibility` CLARIFICATION
  rather than diverging.
- `zettelkasten/5_meta/PROCESSING_PRINCIPLES.md` — 8 principles
  + values-profile calibration. Bootstrap is the FIRST run on a fresh
  instance; read full principles even though SOUL.md may not yet
  override the defaults.
- `zettelkasten/_system/docs/SYSTEM_CONFIG.md` — system contract
  (canonical rules; no version check — file IS the contract per
  CONVENTIONS.md).
- `zettelkasten/_system/docs/CONVENTIONS.md` — documentation
  style (binding on every edit this skill makes to engine docs / SKILLs).
- `zettelkasten/0_constitution/CONSTITUTION.md` — constitution
  protocol (used by Step 1.5 signal 4 + Step 2.5 starter axioms +
  principle-candidates schema).

**Owner state:**

- Owner profile sources (see Step 2 priority order): describe-me
  PROFILE.md is primary; bootstrap interview is fallback;
  `_sources/inbox/` profile files are secondary; `~/.claude/CLAUDE.md`
  is advisory only (may belong to a different instance).
- `3_resources/people/PEOPLE.md` — existing people registry (may be
  empty or template-only on fresh onboarding)
- `_system/TASKS.md`, `_system/CALENDAR.md` — current active
  tasks/events (optional)
- `3_resources/people/*.md` — existing profiles (auto-Tier-1
  regardless of mentions)

Glob for structured signal:
- `_records/meetings/*.md` + `_records/observations/*.md` — record files (both kinds)
- PARA trees (`1_projects/`, `2_areas/`, `3_resources/`, `4_archive/`) — knowledge notes

Glob for raw signal (used in Step 1.5):
- `_sources/inbox/**/*.md` — unprocessed sources (every active source declared in `_system/registries/SOURCES.md`)
- `_sources/processed/**/*.md` — already processed sources (for catch-up scan)

Bootstrap is source-agnostic: it does not name individual source IDs. Whatever
rows are present in SOURCES.md determine the scan surface. The only path
bootstrap treats specially is the one declared as `Skip Subdirs` on the
`crafted` row (or any row that uses the same mechanism for reference content),
which is read in Step 2 as the SOUL profile source and is moved from inbox
to processed mirror after consumption.

**Mode detection:**

```
if count(structured notes) == 0 AND count(transcripts) > 0:
    mode = "fresh-onboarding"
elif count(structured notes) > 0 AND count(unprocessed inbox files) > 0:
    mode = "mixed"
else:
    mode = "established"
```

Record mode in log_maintenance.md entry for auditability.

### Step 1.5: Raw transcript scan (inbox + processed) — multi-signal

Skip if `--skip-raw-scan`. Force-only if `--raw-scan-only` (then skip structured glob above).

The raw scan extracts FOUR signal classes from the corpus, not just people.
On a fresh skeleton clone with 50–500 dropped transcripts this is the
high-leverage step — every signal seeded here saves friction during the
first `/minder:mem:process` batch.

#### Scaling — partition + parallel subagents

A single LLM pass over 100+ transcripts produces low-quality extraction
(attention drift, missed entities, hallucinated clusters) regardless of
context-window size. Partition the raw corpus before dispatching:

- **Chunk algorithm.** Sort transcripts chronologically (oldest first).
  Pack into chunks until either:
  - cumulative input tokens ≥ **200 000** (orchestrator briefing
    overhead headroom on top), OR
  - chunk size ≥ **15 transcripts**
  whichever fires first. Under-filled chunks acceptable. Single-file
  oversize → solo chunk.
- **Dispatch.** One subagent per chunk via parallel `Task` blocks,
  **max 3 concurrent** (matches `/minder:mem:process` Step 3.0.2). Queue the
  rest FIFO. Each subagent extracts all 4 signal classes from its
  chunk and returns a structured signal report.
- **Aggregation (orchestrator).** After all subagents return:
  - **People** — union by candidate id; sum mention counts; merge
    ambiguity flags (any subagent flagging ambiguity wins).
  - **Projects** — union by candidate id; sum mention counts; collect
    supporting transcript paths.
  - **Hub candidates** — global topic-cluster pass over all returned
    cluster candidates: clusters appearing in ≥ 2 subagent reports
    merge by slug; clusters from a single subagent stay if their
    support already crosses the 3-transcripts / 14-days threshold.
    Cap final list at top-15 by support.
  - **Principle candidates** — append all returned candidates to
    `principle-candidates.jsonl`; dedup against last 30 days of buffer
    by `(situation, observation, hypothesis)` triple.

**Why not single-pass even with 1M-context Opus.** Context-window size
is not a quality guarantee. LLM extraction quality on a corpus of 100+
heterogeneous transcripts drops sharply when held in one attention
span — we trade fewer LLM calls for measurably worse signal. Subagent
partitioning is the standard Minder Memory pattern (`/minder:mem:process` Step 3.0.2)
for the same reason.

**Time / cost note.** A 100-transcript onboarding scan on Opus typically
runs in ~7 chunks × ~3 minutes wall-clock = 10–15 minutes if 3-wave
parallelism holds, plus aggregation. Friend should expect this and not
abort early. Bootstrap surface a progress line per dispatched wave.

For each transcript in the raw globs above:

1. **People (signal 1).**
   - Extract mentioned names — scan body text for proper nouns (any
     language; expect mixed Cyrillic / Latin / etc.), patterns like
     «Вася», «Петя сказал», «встретились с @imya». Use LLM for
     disambiguation — regex alone won't catch conjugated forms.
   - Normalize to candidate IDs per `registries/PEOPLE.md` ID Generation
     Rules (`firstname-lastname`, lowercase, dash, transliteration). If
     only first name found — candidate is ambiguous.
   - Match against existing registry: exact match → increment raw-scan
     mention count; ambiguous → CLARIFICATION; no match → CLARIFICATION
     ("Found name '{form}' in {file}. Add to PEOPLE.md as new person?").
   - Track raw dates — transcript timestamp feeds `last_mention`.

2. **Project candidates (signal 2).**
   - Extract recurring named initiatives / codenames / product names
     across transcripts: capitalised noun phrases, project codenames
     repeated across ≥ 2 distinct transcripts, explicit phrases like
     «проект X», «инициатива Y».
   - Normalize to kebab-case candidate id.
   - **Cross-check with PROJECTS.md / `_sources/inbox/describe-me/`
     PROFILE.md projects table** — if friend pre-declared a project, raw
     scan matches and increments mention count rather than creating a
     duplicate candidate.
   - Output: list of `(candidate-id, name-form, mention-count, first-seen, last-seen)`
     for Step 3.5.

3. **Hub candidates (signal 3).**
   - Cluster transcripts by topic using LLM topic extraction. A topic
     becomes a hub-candidate when it appears in **≥ 3 distinct transcripts**
     across **≥ 14 days** (matching the `/minder:mem:process` Step 3.5 hub
     creation threshold; raw scan does NOT create hub files — that
     remains `/minder:mem:process` territory once knowledge notes exist).
   - Output: list of `(candidate-slug, supporting-transcripts, span,
     1-line-rationale)` for Step 4.5.
   - **Cap at top-15 by support** to keep the review queue manageable.

4. **Principle candidates (signal 4).**
   - Detect explicit principle moments per
     `~/.claude/rules/constitution-capture.md` triggers (a–d): explicit
     behavioural principle stated with reason; conscious trade-off; non-obvious
     ethical / interpersonal judgement; clear implicit pattern with
     hypothesis. Conservative — better to miss 30% than ingest 300% noise.
   - **Derivation invariant.** Every candidate must derive from a specific
     transcript moment. Do not synthesize candidates from prior knowledge
     of how mature constitutions look or from `/minder:mem:capture-candidate`'s
     calibration examples — those examples illustrate form, not content.
     If a transcript chunk yields zero qualifying moments, the correct
     output is zero candidates, not "plausible defaults".
   - Apply the same well-formedness rules and boundary cases listed in
     `/minder:mem:capture-candidate` SKILL — the field constraints
     (concrete `situation`, verbatim-or-empty `observation`, hypothesis
     with reasoning, `unknown` over forced guess, no proper nouns) hold
     identically here.
   - For each match append a single record to
     `_system/state/principle-candidates.jsonl` with fields per
     `/minder:mem:capture-candidate` schema PLUS `origin: bootstrap-raw-scan`
     and `session_id: bootstrap-{YYYY-MM-DD}`. Buffer is append-only —
     `/minder:mem:lint` F.3 weekly review picks them up. Bootstrap-origin
     candidates never qualify for F.5 LLM auto-merge (mirrors
     `origin: work` guard in lint F.5).

#### Scope tagging (work / personal axis)

Minder Memory handles the work / personal axis as a first-class universal
property of every owner — see `ENGINE_DOCTRINE.md` «The work /
personal axis — first-class». Every
extracted signal gets a **scope hint** during raw scan, so downstream
seeding (PEOPLE.md Org column, PROJECTS.md Scope column, principle
domain tagging) honours the split without owner having to retag
afterwards.

For each transcript determine a **source-scope bias** before extraction.
The bias comes from two declarative inputs — never from hardcoded source
IDs in this SKILL:

1. **Layer signal** (from path):
   - `_records/meetings/` (and its processed mirror) → bias `work`
   - `_records/observations/` (and its processed mirror) → bias `personal`
2. **Source signal** (from `Default Domain` column on the matching
   row of `_system/registries/SOURCES.md`):
   - `personal` / `work` → use directly as the bias
   - `mixed` → infer per-transcript content (LLM scope classification:
     «is the dominant topic about employer / clients / professional
     team OR life / relationships / health / personal projects?»)
   - `auto` → same as `mixed` — let the LLM decide per-file

If a row carries `Skip Subdirs`, those subdirectories are out of scope
entirely (they are reference material, consumed via a different contract
in Step 2).

Apply the bias to each extracted signal:

- **Person** — if scope-bias is `work` AND person resolves to a
  candidate with hints of organisational role → suggest `Org` value
  for PEOPLE.md row. If scope-bias is `personal` AND no org clue →
  leave `Org` empty (personal-context relation per PEOPLE.md
  Org-as-scope convention).
- **Project candidate** — emit a `scope_hint` field ∈ {`work`,
  `personal`, `side`, `mixed`} based on transcript bias + content.
  Step 3.5 writes this to PROJECTS.md `Scope` column.
- **Hub candidate** — emit a `domains` array (work / personal-richer
  tags like `identity`, `relationships`, `learning`); Step 4.5
  surfaces this in CLARIFICATIONS so future `/minder:mem:process` Step 3.5
  hub creation inherits.
- **Principle candidate** — set `suggested_domain` from the
  constitution vocabulary (`identity` / `ethics` / `work` / `tech` /
  `relationships` / `health` / `money` / `time` / `learning` /
  `ai-interaction` / `meta`) — the closed enum in
  `0_constitution/CONSTITUTION.md` «Domains», which is a different axis
  from the note-level `domains:` whitelist in
  `_system/registries/DOMAINS.md` and does NOT contain `personal`.
  For personal-bias transcripts,
  prefer `identity` / `ethics` / `relationships` / `learning` based
  on principle content.

Cross-domain signals (work delegation through a therapy lens; career
decision affecting personal life) produce signals in BOTH scopes —
Principle 4 (Cross-Domain Permeability) at the bootstrap level.

**Dual-source reconciliation for established/mixed modes:**

- Authoritative count = structured frontmatter (Step 3 below)
- Raw count is advisory — used only to surface gaps (person in transcripts but not in registry)
- Raw count never overrides structured; instead it triggers CLARIFICATIONS

**Fresh-onboarding mode:**

- Raw count becomes the primary mention count for all four signal classes
- All discovered names go through CLARIFICATIONS first (never auto-added to PEOPLE.md)
- Skill produces a "seed PEOPLE.md" draft with candidates flagged for user review
- Project candidates seed PROJECTS.md as `status: candidate` rows with `Scope` filled from `scope_hint` (Step 3.5)
- Hub and principle candidates surface as CLARIFICATIONS / jsonl appends only — no file creation

### Step 2: SOUL.md draft

Source priority for Identity / Values / Working Style / Active Goals.
SOUL.md is the canonical owner-profile source; the user's global
`~/.claude/CLAUDE.md` is advisory only.

1. **Owner profile in `_sources/inbox/describe-me/`** (primary
   when present and non-template).

   **File discovery.** Read every `*.md` in the directory (recursive).
   Multiple files are allowed — owner's instance has examples like
   `1 - personal_profile-claude.md`, `2 - personal_profile-gpt.md`. When
   multiple non-template files are found, **merge** by section: for each
   SOUL.md section, prefer the longer non-placeholder body across files
   and surface a CLARIFICATION listing the alternates so the owner can
   pick a different version. Do not concatenate sections silently.

   **Template-default detection** (per file). Count placeholder markers
   matching the regex `\{[A-Z][^{}]{4,}\}` (curly-brace placeholders
   shipped in `PROFILE.template.md`). If ≥ 60% of the file's bracketed
   spans are still unchanged, treat the file as template and skip it
   (write CLARIFICATION «Profile draft detected but mostly placeholders
   — consider editing or deleting»). This handles three failure modes:
   (a) friend opens template, edits nothing, runs bootstrap — caught;
   (b) friend edits one or two fields and forgets — surfaced not
   silently consumed; (c) friend deletes some placeholders but leaves
   the rest as TODO markers — counts edited fraction, partial profiles
   still flow through.

   **Section parsing.** Pull section-by-section into SOUL.md draft.
   Sections whose body is still a placeholder span surface as items in
   CLARIFICATIONS `### Profile gaps` instead of triggering interview
   questions (placeholders are an explicit «I'll fill this later»
   signal — interview only fires when the section is *missing*, not
   *unfilled*).

   **Auxiliary tables in profile** feed downstream steps:
   - `### People who matter` table → Step 3 PEOPLE.md (rows with
     placeholder ids like `{ivan-petrov}` are dropped, not seeded)
   - `### Projects you care about` table → Step 3.5 PROJECTS.md
     (same placeholder-row drop)
   - `### Principles you live by` bullets → Step 1.5 signal 4
     (each bullet becomes a `principle-candidates.jsonl` entry with
     `origin: bootstrap-profile` and `session_id: bootstrap-{date}`)

   **After read:** move the consumed (non-template) files from
   `_sources/inbox/describe-me/` to `_sources/processed/describe-me/`,
   marking them consumed — `/minder:mem:process` scans `describe-me` as a
   regular source and must not re-ingest the SOUL-consumed profile as
   knowledge notes. Keep the folder itself and `PROFILE.template.md`
   in place: the folder is a registered source row in SOURCES.md, and
   the template is excluded from processing engine-wide (`*.template.md`
   rule). If `_sources/processed/describe-me/` already has files
   (re-run, or owner's pre-existing reference set), merge — never
   overwrite existing files; collisions surface as CLARIFICATIONS.

2. **Bootstrap interview** (primary fallback when (1) is absent or
   template-default, or to fill gaps left by (1)). Ask 3-5 short
   questions targeting only the *missing* SOUL sections: name (used
   as `## Identity` `Name:`), role, current focus, values, working
   style. Write answers directly into SOUL.md.

3. **Other profile files in `_sources/`** (secondary) — any file in
   `_sources/inbox/` or `_sources/processed/` (outside `describe-me/`)
   whose filename contains `bio`, `profile`, `about-me`, `describe-me`
   (case-insensitive). Pull verbatim into a CLARIFICATION asking user
   whether to merge into SOUL.md (not auto-merged — too risky, format
   unknown).

4. **`~/.claude/CLAUDE.md`** (advisory only) — may belong to a
   different instance (work vs personal) or to no instance yet. Use
   only when (1)–(3) yield nothing AND the file clearly identifies
   the same person. Never silently authoritative — always confirm
   with user before copying values into SOUL.md.

5. **Fallback** — if all four are empty / inconclusive: draft minimal
   Identity (`Name: <unset>`) + CLARIFICATION asking user to fill the
   profile manually.

Focus signals:

- **Established/mixed:** derive Primary/Secondary/Personal from top streams in TASKS.md +
  density of last 30-50 records
- **Fresh onboarding:** derive from transcripts in `_sources/` (inbox + processed) — if the
  user dumped 10 transcripts all about "finding new job", that's a signal

Field confidence:

- **Identity** (high) — directly from profile
- **Values** (high) — from profile Values section if present, else CLARIFICATION
- **Current Focus** (medium) — from streams/transcripts. If ≥ 5 distinct themes active — CLARIFICATION
- **Active Goals** (low) — pull explicit deadlines/commitments. Leave empty if unclear
- **Working Style, Context for Agents** — always `<!-- TODO -->` markers (never derivable automatically)

Skip regeneration if `--skip-soul` — append note to log_maintenance.md and leave file untouched.

### Step 2.5: Constitution starter pack (opt-in)

Skipped unless `--with-starter-axioms` is set. Off by default — fresh
clones should grow their constitution from `/minder:mem:capture-candidate`
observations, not from inherited principles.

When the flag is on:

1. Read every `*.md` under `5_meta/starter-pack/axioms/`.
2. For each file, derive destination path
   `0_constitution/axiom/{domain}/{filename}` from the file's `domain:`
   frontmatter field (e.g. `ethics`, `identity`, `work`).
3. **Skip if destination already exists** — never overwrite an axiom
   the user has already authored or edited.
4. Copy verbatim. Files keep `confidence: starter` and `status: draft`,
   so they appear in the constitution but do NOT auto-load into
   `constitution-core` (that view filters on `confidence: proven`
   `status: active`).
5. Append a single CLARIFICATION grouping copied filenames with the
   action: "Review each starter axiom — keep, edit, or delete; mark
   as `confidence: proven` `status: active` to promote into core."

The flag does nothing on second/third runs (idempotent — destinations
already exist after first run, all are skipped).

### Step 3: PEOPLE.md tier + mention counting

Process depends on mode:

**Established / Mixed modes (primary = structured frontmatter):**

For every person already in `PEOPLE.md`:

1. **Count structured mentions** across:
   - `_records/meetings/*.md` + `_records/observations/*.md` frontmatter `people:` (and `speaker:` for observations) arrays
   - PARA knowledge notes frontmatter `people:` arrays
   - Dedup rule: ONE mention per file (person appearing 6 times in one transcript = 1, not 6).
     Canonical rule per `_system/docs/SYSTEM_CONFIG.md` Data & Processing Rules — mention counting is 1-per-file
2. **Capture `last_mention`** — latest `created` date across files referencing the person
3. **Cross-check with raw scan (Step 1.5 output):**
   - If person appears in raw transcripts but 0 structured mentions → CLARIFICATION
     ("mentioned in N transcripts, not yet in any record/note — expected?")
   - If raw scan found new name not in registry → CLARIFICATION
     ("found '{Russian form}' in {file}. Add to PEOPLE.md as `{candidate-id}`?")
4. **Assign tier:**
   - **Tier 1** — profile in `3_resources/people/{id}.md` (auto) OR mentions ≥ 8
   - **Tier 2** — mentions 3-7
   - **Tier 3** — mentions 1-2
5. **Update PEOPLE.md schema:** add columns `Tier`, `Mentions`, `Last`. Idempotent — recompute on each run

**Fresh onboarding mode (primary = raw scan):**

1. PEOPLE.md starts empty or template-only
2. Raw scan from Step 1.5 found candidate names with `(russian form → candidate id → transcript count)`
3. **Do NOT auto-populate PEOPLE.md.** Instead write ALL candidates to CLARIFICATIONS under
   `### Suggested people from raw scan` with structure:
   ```
   - "Иван Петров" → candidate id `ivan-petrov` — mentioned in 3 transcripts, org: unknown, role: unknown
   ```
4. User reviews CLARIFICATIONS, approves/edits/rejects each. Re-run bootstrap or `/minder:mem:process`
   will then register approved entries

**CLARIFICATIONS triggers (all modes):**

- Same-name collision: bare first name matches multiple registered (`Даша` → `daria-kudryavtseva` vs `daria-panfilova`) → CLARIFICATION per occurrence
- Person with 0 mentions but has profile (stale?) → CLARIFICATION: "Still relevant? Archive?"
- Person with 8+ mentions but NO profile → CLARIFICATION: "Generate profile?" (actual creation is `/minder:mem:lint`)
- Raw scan finds name not resolved to any registered ID → CLARIFICATION (see above)

### Step 3.4: Owner identity — registry row + profile

The owner is a first-class identity: identity checks treat their identifier as
registered by definition, and every record they took part in resolves through
it. Skipped under `--skip-people` (writes to PEOPLE.md) and under `--dry-run`
(reports only).

**1. Resolve the identifier.** Read `_system/SOUL.md → ## Identity → Name:`
(written by Step 2) and derive `firstname-lastname` by the registry's own ID
rule. Name still `<unset>` / empty / a placeholder span → write CLARIFICATION
`owner-identity-unresolved` and stop this step. Nothing is guessed from the OS
user, the git config, or a transcript.

**2. Registry row.** Write the row into the `## Owner` section of
`3_resources/people/PEOPLE.md` — `ID | Name | Role | Profile`, `Role` from
SOUL `## Identity`. Never into the general `## People` table: tier mechanics
do not apply. A row already present with the *same* id is left as it stands;
a row present with a *different* id surfaces CLARIFICATION
`owner-identity-mismatch` (SOUL and the registry disagree — owner decides) and
nothing is rewritten.

**3. Profile.** Create `3_resources/people/{owner-id}.md` from
`5_meta/templates/person-template.md` — the same shape as any other person
profile, no second shape. **Assembled, not stubbed:** a file carrying only a
name answers none of the questions a profile exists for.

Each part comes from a named source, in this order:

| Part of the profile | Source |
|---|---|
| `name`, `role`, `**Role:**` line | `_system/SOUL.md → ## Identity` |
| `origin: personal`, `audience_tags: []`, `is_sensitive: false`, `tags: [person/{id}]` | fixed by the privacy trio defaults in the person template |
| `## Контекст` — who they are, how they work, what they are on now | `_system/SOUL.md` → `## Identity` (role, location), `## Working Style`, `## Context for Agents`, `## Current Focus` |
| `## Контекст`, closing line — the circle around them | `3_resources/people/PEOPLE.md` → Tier 1 rows, as `[[id]]` wikilinks with role / org |
| `## Ключевые темы` — the values and principles they operate by | the active constitution tree `0_constitution/` (`status: active`) — one bullet per axiom / tier-1 principle: its title plus a wikilink to its file |
| any of the above, where the owner wrote it themselves | `_sources/inbox/describe-me/` (and `_sources/processed/describe-me/` after Step 2 moved the consumed files) — the owner's own words win over a derived sentence |
| `## Упоминания` | left as the template placeholder — the ordinary backlink machinery fills it; the owner appears in nearly every note, so a list here would carry no signal |

**Assembly is deterministic from the sources named above, never invented.**
What the sources do not say, the profile does not claim: an empty
constitution yields no `## Ключевые темы` bullets, a SOUL with no
`## Working Style` yields no sentence about working style. No plausible text
fills a gap — a gap worth closing is a CLARIFICATION, not a paragraph.

**4. No auto-population.** The owner is registered, NOT added to the `people:`
array of any record or note, and not counted in anyone's mention totals. They
are present by default almost everywhere; auto-population would inflate every
count and carry no signal. Their absence from a record is what is significant.

**Idempotency.** Re-run adds only what is missing and overwrites nothing the
owner touched: an existing frontmatter field keeps its value, an existing
section with a non-placeholder body is left alone, and a section that is
missing or still the template placeholder is (re)assembled from the sources
above. A friend whose constitution was empty on the first run gets
`## Ключевые темы` on the run after their first principles land.

### Step 3.5: PROJECTS.md seeding (raw scan only)

Skip if `--skip-raw-scan` or no project candidates found in Step 1.5
signal 2. Skipped silently in `established` mode unless the raw scan
discovered a project not yet in PROJECTS.md (then surface as
CLARIFICATION, do not auto-add).

**Fresh-onboarding mode (PROJECTS.md is template-default):**

1. Take project candidates from Step 1.5 signal 2 (deduped against the
   `### Projects you care about` profile table if present — when
   profile pre-declared a project with explicit `Scope`, use that;
   otherwise use raw-scan `scope_hint`).
2. For each candidate write a row to PROJECTS.md `Active Projects`
   table with columns: `ID | Name | Description | Folder | Scope |
   Status`. `Scope` ∈ {`work`, `personal`, `side`, `mixed`} from
   profile / scope_hint. `Status: candidate`. Do NOT pick
   `### Completed Projects` automatically — staleness goes through
   CLARIFICATIONS.
3. Append a CLARIFICATIONS subsection `### Suggested projects from raw
   scan` listing each row (with Scope) + supporting transcripts +
   suggested action (`promote-active` | `merge-with-existing` |
   `correct-scope` | `dismiss`).

**Idempotency:** re-running matches by candidate id. Existing rows are
never overwritten — bootstrap only ADDS new candidate rows the first
time it sees them, then surfaces them as CLARIFICATIONS.

### Step 4: OPEN_THREADS.md detection

Source depends on mode:

- **Established / mixed:** scan `_records/meetings/*.md` + `_records/observations/*.md` + TASKS.md Waiting section from last `--threads-window` weeks (default 6). TASKS.md Waiting items cluster into strategic threads (grain: one thread covers multiple child tasks). Observation records can carry open threads too (planning sessions, therapy follow-ups).
- **Fresh onboarding:** scan raw transcripts in `_sources/inbox/` + `_sources/processed/` from last `--threads-window` weeks (or all, if less). Grain stays the same — strategic threads, not per-utterance.

Signal extraction (all modes):

1. Unresolved action items without `deadline` or phrasing like "ждём / жду от / нужно решить / нужно дождаться / уточнить у / неясно"
2. Open questions (`## Открытые вопросы`, `## Нерешённое`) in structured records
3. For raw transcripts: LLM extraction of "what's the owner waiting on, from whom, since when"

For each candidate:

1. Grep subsequent records/transcripts for closure signals: resolution, follow-up, decision
2. **If clear closure** — move to Resolved section with resolution + source
3. **If still open** — add to Active with status (waiting-for-response / needs-decision / needs-research / blocked), source, people involved, 1-2 line context
4. **If unclear** — CLARIFICATION: "Thread <slug> — still open? last signal <date>"

Thread ID: `thread-YYYYMMDD-{semantic-slug}` where YYYYMMDD = origin date.

**Grain rule (strategic, not operational):**
One OPEN_THREADS entry should cover an umbrella topic (e.g. "Restructuring & Career") with
multiple cross-referenced TASKS.md Waiting items underneath. Do NOT create 1 thread per Waiting
task — that would duplicate TASKS.md at another grain. When in doubt — CLARIFICATION asking
user to confirm grain level.

Idempotency: re-running matches by thread-id. Existing Active threads stay unless closure detected. Resolved entries never re-open.

### Step 4.5: Hub candidates from raw scan

Skip if `--skip-raw-scan` or no hub candidates from Step 1.5 signal 3.

Bootstrap does **NOT** create hub files. Hub files require ≥ 3 atomic
knowledge notes per `/minder:mem:process` Step 3.5 — those notes don't exist
yet on a fresh clone. Instead:

1. For each hub candidate (capped at top-15 by support), append a
   CLARIFICATION under `### Suggested hubs from raw scan` with:
   - candidate slug
   - 1-line rationale (what the cluster is about)
   - supporting transcripts (≤ 5 paths, sorted by date)
   - suggested action: `seed-hub-after-first-process` (default) or
     `dismiss` (false-positive cluster)
2. After the friend's first `/minder:mem:process` batch produces knowledge
   notes that hit the threshold, `/minder:mem:process` Step 3.5 will create
   the corresponding hub naturally. The CLARIFICATION serves as a
   review log — friend can compare bootstrap's expectation vs reality
   and dismiss noise early.

**Why not lower the hub-creation threshold for fresh onboarding.** A
hub created with 0 supporting knowledge notes is a stub; the «3+ notes»
threshold encodes a real signal-to-noise floor. Pre-seeding the
candidate list captures bootstrap's macro view without weakening the
floor.

### Step 4.7: Principle-candidate harvest

Already executed inline as part of Step 1.5 signal 4. Step 4.7 only
counts and reports for log_maintenance.md (number appended to jsonl,
breakdown by `suggested_type`, breakdown by `suggested_domain`).

### Step 5: CURRENT_CONTEXT.md generation

Compose snapshot from updated SOUL + OPEN_THREADS + TASKS + CALENDAR:

- **Focus** — copy SOUL.md Primary focus
- **Tasks Due Today/Tomorrow** — filter TASKS.md by deadline
- **Meetings Today** — filter CALENDAR.md Upcoming by date = today
- **Open Threads** — count + top 3 by recency from OPEN_THREADS.md
- **Last Activity** — `(no batches yet)` since bootstrap predates any `/minder:mem:process` run

Frontmatter: `generated_by: minder:mem:bootstrap`, `batch_id: bootstrap`, `generated: {now ISO 8601}`.

### Step 5.5: Derived registries + views generation

Generate the two derived files that downstream skills assume exist:
the concept registry (`_system/registries/CONCEPTS.md`) and the wiki
index (`_system/views/INDEX.md`). Both scripts are pure, deterministic,
idempotent; bootstrap and `/minder:mem:maintain` MUST produce byte-identical
output on the same base.

#### 5.5.a CONCEPTS.md

```bash
python3 _system/scripts/build_concept_registry.py
```

Same script invoked by `/minder:mem:maintain` Step 4.5. On a fresh-onboarding
clone the corpus is empty, so the script writes a registry with zero
rows and the placeholder body `_(none — registry is empty)_`. This
matters because `/minder:mem:process` Step 3.4.5 reads `CONCEPTS.md` verbatim
into the matcher subagent prompt — without this step the file would not
exist on first `/minder:mem:process` and the matcher prompt would silently
inject a read error.

Owner-edit preservation contract (aliases column) is documented in
`/minder:mem:maintain` Step 4.5; it is a no-op on fresh setup but the same
code path runs here.

Failure mode: non-zero exit → surface
`CONCEPTS.md: regen-failed ({error})` in the log entry (Step 6) and
continue the rest of bootstrap. `/minder:mem:maintain` will retry on next run.

#### 5.5.b INDEX.md

```bash
python3 _system/scripts/render_index.py
```

Same script invoked by `/minder:mem:maintain` Step 7.6. Atomic write via
`.tmp` + rename. The script handles both states uniformly:
- Empty knowledge layer (fresh setup) → all sections render as
  `_(empty)_`, frontmatter counts at zero.
- Populated base → full catalog: knowledge (`1_projects` / `2_areas` /
  `3_resources`), archive (`4_archive`), constitution
  (`0_constitution/{axiom,principle,rule}`), hubs (`5_meta/mocs`).
  Records and posts intentionally out of scope.

The script writes `generator: render_index.py` in the frontmatter —
Minder Memory-wide single source of truth, regardless of which skill triggered
the call.

Failure mode: non-zero exit → surface
`INDEX.md: regen-failed ({error})` in the log entry (Step 6) and
continue the rest of bootstrap. INDEX is a derived view; `/minder:mem:maintain`
will retry on next run.

### Step 6: log_maintenance.md entry

Append to `_system/state/log_maintenance.md` (newest first, below the `<!-- Entries append BELOW -->` marker):

```markdown
## {ISO 8601 UTC} | bootstrap | by: minder:mem:bootstrap | batch: —

### Updates
- SOUL.md drafted (Identity + Values high confidence, Focus medium, Working Style + Context for Agents — TODO markers)
- PEOPLE.md: {N} entries updated (tiers assigned, mentions recomputed, last_mention added)
  - Tier 1: {N} | Tier 2: {N} | Tier 3: {N}
- OPEN_THREADS.md: {N} active, {M} resolved
- CURRENT_CONTEXT.md: generated
- CONCEPTS.md: generated (total_concepts: {T}, total_mentions: {U})
- INDEX.md: generated (note_count: {N}, archive_count: {A}, constitution_count: {C}, hub_count: {M}, domain_count: {D})

### Auto-Fixes
- {anything auto-corrected — normally empty for bootstrap}

### Suggestions → CLARIFICATIONS
- {count} questions raised (see _system/state/CLARIFICATIONS.md under header 'bootstrap YYYY-MM-DD')

### Errors / Warnings
- {none | warning text}
```

### Step 7: CLARIFICATIONS grouping

Все вопросы от bootstrap — inline в `_system/state/CLARIFICATIONS.md` под заголовком
`## bootstrap YYYY-MM-DD`. Один файл, унифицированный подход для всех скиллов.

Внутри секции группировка по типу для читаемости:
- `### Tier / mention rules`
- `### Thread closures`
- `### Focus / SOUL ambiguities`
- `### People identity / same-name collisions`
- `### Suggested people from raw scan` (fresh/mixed — candidate IDs для утверждения)
- `### Suggested projects from raw scan` (fresh/mixed — candidate project rows added to PROJECTS.md)
- `### Suggested hubs from raw scan` (fresh — topic clusters; no hub files created until first /minder:mem:process meets 3-note threshold)
- `### Profile gaps` (sections in describe-me/PROFILE.md still on placeholder defaults)

Volume не ограничиваем. Если реально будет 100+ — revisit дизайн, но до этого
единый файл лучше чем два (consistency > size optimization).

### Step 8: Report

Output to user:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Minder Memory BOOTSTRAP COMPLETE ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mode:           {established | fresh-onboarding | mixed}
Profile seed:   {used: describe-me/PROFILE.md | used: bootstrap interview | none}
Raw scan:       {N} transcripts in inbox + {M} in processed
Structured:     {R} records + {K} knowledge notes scanned

SOUL.md           drafted — review Working Style + Context for Agents sections
PEOPLE.md         {N} persons (structured) + {N_raw} raw-scan candidates → CLARIFICATIONS
  Tier 1: {N}  | Tier 2: {N}  | Tier 3: {N}
Owner             {registered as `{owner-id}`, profile {created | gaps filled | unchanged} | unresolved → CLARIFICATION}
PROJECTS.md       {N_proj} candidate rows added → CLARIFICATIONS
Hub candidates    {N_hub} clusters surfaced → CLARIFICATIONS (no files created)
Principle cand.   {N_princ} appended to principle-candidates.jsonl (review via /minder:mem:lint F.3)
OPEN_THREADS      {N} active | {M} resolved
CURRENT_CONTEXT   generated ({no batches yet | last batch: X})
log_maintenance.md bootstrap entry appended

Next steps (in order — do not skip):

1. **Run `/minder:mem:resolve-clarifications`** — {K} questions accumulated,
   grouped by subsection (people / projects / hubs / threads / focus
   / profile gaps). The skill walks them by theme one round at a time
   with full context inline, applies confirmed resolutions, and
   archives closed items. 5–30 minutes depending on corpus size.

2. **Finalise `_system/SOUL.md`** — fill any Working Style / Context
   for Agents gaps the profile or interview left as TODO markers. The
   profile's "How you like information presented" answers go here (general
   tuning) and into `_system/long-form-playbook.md` (the long-form recipe);
   how they want a decision with someone else's interest in it worked through
   goes into `_system/decision-advisory-playbook.md`;
   firm presentation rules you wrote under "Principles you live by" are already
   queued as `ai-interaction` principle-candidates for F.3 review.

3. **Run `/minder:mem:process`** — backfill the inbox into records, knowledge
   notes, and hubs.
   - Process partitions automatically: N=6 transcripts or 250 000
     tokens per batch, max 3 parallel subagents per wave.
   - `/minder:mem:maintain` runs as after-batch integrator inside the same
     flow — DO NOT invoke it manually between batches.
   - For 50–200 transcripts expect 30 min – 2 h wall-clock, 8–35
     batches across 3–12 waves.
   - Hubs that bootstrap surfaced as candidates materialise as actual
     hub files when knowledge-note threshold (3+) is met mid-backfill.

4. **DO NOT run `/minder:mem:lint` between batches.** Lint is the nightly
   slop-catcher; on a fresh backfill the same items re-surface batch
   after batch and resolve themselves as later batches land. Run lint
   ONCE after the entire `/minder:mem:process` flow completes — or just wait
   for the first weekly Monday-UTC tick which fires F.3 automatically.
   First lint promotes/dismisses the {N_princ} bootstrap-origin
   principle candidates and starts populating
   `_system/views/constitution-core.md`.

5. **From here on**: drop new transcripts into `_sources/inbox/` as
   they accrue, run `/minder:mem:process` (manual or scheduled), invoke
   `/minder:mem:capture-candidate` in-the-moment when you state a personal
   principle. Weekly `/minder:mem:lint` keeps hygiene.

**Doctrine transmission — confirmed.** The engine's operating
philosophy is now anchored in three independent paths so it survives
any single point of failure:

- `~/.claude/rules/minder-memory-engine-doctrine.md` → `_system/docs/ENGINE_DOCTRINE.md`
  (auto-loaded in every Claude Code session in this repo via the
  `install.sh` symlink chain)
- `_system/views/CURRENT_CONTEXT.md` frontmatter `engine_doctrine`,
  `processing_principles`, `constitution_core` keys (any skill
  loading just CURRENT_CONTEXT inherits the pointers)
- Explicit Step 1 / Contracts loads inside `/minder:mem:process`,
  `/minder:mem:maintain`, `/minder:mem:lint`, `/minder:mem:bootstrap` SKILL.md (the four
  pipeline skills that make the most judgements)

Future processing inherits the frame. If you ever feel a future
`/minder:mem:process` batch is operating against a different philosophy,
the doctrine likely drifted in one of those three paths — check
them in order.
```

---

## CLARIFICATIONS examples

Write to `_system/state/CLARIFICATIONS.md` under `## bootstrap YYYY-MM-DD` header.

**Mandatory fields (applied к all bootstrap items):**
- `**Type:**` — reason code. Canonical list:
  - `tier-promote-suggested` / `tier-demote-candidate`
  - `thread-closure-suggested`
  - `focus-ambiguous`
  - `people-bare-name`
  - `people-candidate-suggested` (raw scan found unregistered name)
  - `project-candidate-suggested` (raw scan / profile suggested project row)
  - `hub-candidate-suggested` (topic cluster crossed support threshold; no file created)
  - `profile-gap` (profile section still on placeholder default — expected fill)
  - `profile-merge-conflict` (multiple profile files disagree on a section)
  - `process-compatibility` (schema mismatch noticed during raw scan)

> **Note on bare-name items:** per `_system/docs/SYSTEM_CONFIG.md` «People inclusion in `people:` frontmatter», a routine bare-name mention is appended to `_system/state/people-candidates.jsonl` via `python3 _system/scripts/append_person_candidate.py` rather than raised as a CLARIFICATION — unless the high-importance escape hatch fires (external/client meeting, full surname present, role+context fully specified). Bootstrap runs once on a fresh base and can produce many bare-name mentions; buffer-routing keeps the CLARIFICATIONS queue manageable. `/minder:mem:lint` Scan C.5 aggregates weekly.
- `**Subject:**` — primary entity id
- `**Source:**` — `bootstrap-{YYYY-MM-DD}` or specific file path
- `**Suggested action:**` — canonical verb from the Resolution-action vocabulary (see `_system/docs/SYSTEM_CONFIG.md`) or descriptive (reminder items)
- `**Confidence tier:**` — surfaced (bootstrap always surfaces — never auto-applies)
- `**Quote:**` — verbatim fragment when source = транскрипт (для person-bare-name items)
- `**Context:**` — 2-4 sentence paragraph (self-contained для LLM review session)
- `**To resolve:**` — imperative unblock instruction

```markdown
## bootstrap 2026-04-17

### 2026-04-17 — tier-ambiguity: petya-ivanov

**Type:** tier-promote-suggested
**Subject:** petya-ivanov
**Source:** bootstrap-2026-04-17
**Confidence tier:** surfaced
**Suggested action:** promote-tier OR fix-process (dedup rule)

**Context:** Person `petya-ivanov` упомянут 6 раз structurally, но 4 из 6 — в одной 90-минутной встрече. Применён canonical rule 1-per-file (per `_system/docs/SYSTEM_CONFIG.md` Data & Processing Rules) → mentions = 3 → Tier 2. Подтверди или переклассифицируй если контекст meeting был существенно фрагментирован.

**To resolve:** Подтверди dedup rule (1-per-file принят в SYSTEM_CONFIG Data & Processing Rules) или измени → обновить PEOPLE.md Mentions для petya-ivanov соответственно.

---

### 2026-04-17 — thread-closure-suggested: thread-20260310-strategy-proposal

**Type:** thread-closure-suggested
**Subject:** thread-20260310-strategy-proposal
**Source:** bootstrap-2026-04-17
**Confidence tier:** surfaced
**Suggested action:** pursue-or-close

**Context:** Thread «Strategy proposal от Ивана» last signal 2026-03-18 meeting с комментарием «ждём к концу месяца». В April records — 0 mentions этой темы. Либо closed silently (декабрьские events не документировались), либо stalled. Related: [[ivan-petrov]] primary stakeholder.

**To resolve:** Либо закрой с `Resolution-action: close-thread` + resolution_text, либо `keep-thread-open` если реально ждём.

---

### 2026-04-17 — focus-ambiguous: current-focus-split

**Type:** focus-ambiguous
**Subject:** _system/SOUL.md Focus
**Source:** bootstrap-2026-04-17
**Confidence tier:** surfaced
**Suggested action:** review-soul

**Context:** Current Focus split across 4 streams с density: Project Alpha (8 records), Project Beta (6), Tooling (5), Reliability (4). Bootstrap применил conservative default (Primary = Project Alpha, Secondary = Project Beta, Tertiary = Tooling). Corresponds к a recent focus shift. Reliability — operational, возможно не Focus-level.

**To resolve:** Подтверди или edit SOUL.md Focus section. Если Tertiary должен быть Reliability вместо Tooling — манual edit.

---

### 2026-04-17 — people-bare-name: Alex в record 20260403

**Type:** people-bare-name
**Subject:** bare-name «Alex»
**Source:** _sources/processed/plaud/2026-04-03T.../transcript.md
**Confidence tier:** surfaced
**Suggested action:** resolve-bare-name

**Quote:** > «Alex said he'd sort out the weekend hiking route, just needs to confirm the trailhead.»

**Context:** Bare «Alex» в record `20260403-meeting-*` без people: entry в frontmatter. В PEOPLE.md registry 3 кандидата: alex-doe, alex-smith, alex-jones. По контексту (hiking route, trailhead) — leans alex-doe (regular hiking partner), но требуется подтверждение.

**To resolve:** Подтверди person-id или edit frontmatter `people:` list в source record.

---

### 2026-04-17 — tier-demote-candidate: oleg-volkov

**Type:** tier-demote-candidate
**Subject:** oleg-volkov
**Source:** bootstrap-2026-04-17
**Confidence tier:** surfaced
**Suggested action:** pursue-or-close

**Context:** Person `oleg-volkov` — last mention 2025-11, 0 recent activity в records с Dec 2025. Либо архивировать (status: archived), либо реально остаётся активной связью (offline cadence). HARD RULE: bootstrap никогда не downgrade'ит tier автоматически.

**To resolve:** Либо dismiss (keep active), либо `fix-process` manual edit PEOPLE.md status.
```

---

## What this skill does NOT do

- Не модифицирует существующие knowledge notes (Evidence Trail backfill — ответственность `/minder:mem:lint`)
- Не создаёт новые knowledge notes (ответственность `/minder:mem:process`)
- Не создаёт hub-файлы — даже когда raw scan находит сильные кластеры. Hubs требуют ≥ 3
  knowledge notes per `/minder:mem:process` Step 3.5; bootstrap surfaces только candidates → CLARIFICATIONS
- Не трогает `_records/` (они уже корректны)
- Не создаёт новые профили в `3_resources/people/` (Tier 2→1 auto-generation — ответственность `/minder:mem:lint`).
  **Исключение — профиль владельца** (Step 3.4): он не проходит через tier-механику вообще,
  поэтому его некому создать по порогу упоминаний
- Не запускает `/minder:mem:process`
- **Не перемещает транскрипты из inbox в processed** — это ответственность `/minder:mem:process`.
  Raw scan читает транскрипты read-only.
- **Исключение:** консумированные (non-template) файлы из `_sources/inbox/describe-me/`
  ПЕРЕМЕЩАЮТСЯ в `_sources/processed/describe-me/` после Step 2 — отметка «consumed»,
  чтобы `/minder:mem:process` (для которого `describe-me` — обычный source) не заинжестил
  профиль повторно. Сам каталог и `PROFILE.template.md` остаются на месте
- **Не парсит транскрипт на structured records/notes** — bootstrap извлекает signal classes
  (people, projects, hub-candidates, principle-candidates, threads, focus), а не полный content.
  Для onboarding друга: он запускает bootstrap для seed registries → потом `/minder:mem:process` для
  полной обработки inbox

---

## Idempotency

Повторный запуск:

- **Threads** — match by `thread-id`. Existing Active stay unless closure detected. Resolved never re-open
- **PEOPLE.md** — mentions recomputed from scratch. Tier upgrades only (downgrade требует explicit `/minder:mem:lint` suggestion через CLARIFICATIONS)
- **CLARIFICATIONS** — previous answers preserved. New questions под новой `## bootstrap YYYY-MM-DD` header; не перезаписывают предыдущие
- **SOUL.md** — если `--skip-soul` или пользователь вручную редактировал → не перезаписывается. Иначе перезапись с сохранением Working Style + Context for Agents секций при наличии текста
- **Owner row + profile** — row added once into PEOPLE.md `## Owner`; a row with a different id surfaces a CLARIFICATION instead of being rewritten. Profile assembled per section: owner-written bodies stay, missing or still-placeholder sections are re-assembled from SOUL / constitution / registry, so a constitution that filled up after the first run reaches the profile on the next one
- **PROJECTS.md** — candidate rows added by id; existing rows never overwritten. If a candidate id matches an existing row, increment mention count surfaced via CLARIFICATION rather than rewrite the row
- **principle-candidates.jsonl** — append-only buffer. Re-running bootstrap appends new candidates only when their `(situation, observation, hypothesis)` triple is not already present in the buffer (dedup against last 30 days of entries)
- **describe-me/ move** — per file, happens once. On re-run, consumed files are already in `_sources/processed/describe-me/`; bootstrap re-reads from there with no further move. New inbox-side files added since the previous run are consumed (and moved) the same way

---

## Output files summary

| File | Action | Notes |
|---|---|---|
| `_system/SOUL.md` | rewrite (draft) | Sections present in profile/interview filled; gaps marked TODO |
| `_system/state/OPEN_THREADS.md` | populate | Active + Resolved sections |
| `_system/views/CURRENT_CONTEXT.md` | rewrite | `generated_by: minder:mem:bootstrap`, `batch_id: bootstrap` |
| `_system/registries/CONCEPTS.md` | rewrite (via `build_concept_registry.py`) | Same script as `/minder:mem:maintain` Step 4.5; on fresh setup writes an empty registry so `/minder:mem:process` Step 3.4.5 matcher prompt has a file to read |
| `_system/views/INDEX.md` | rewrite (via `render_index.py`) | `generator: render_index.py`; surface catalog of knowledge + archive + constitution + hubs (records / posts excluded by design); empty placeholders on fresh setup |
| `_system/state/log_maintenance.md` | append | One bootstrap entry |
| `_system/state/CLARIFICATIONS.md` | append | Under `## bootstrap YYYY-MM-DD` header, grouped by subsection |
| `_system/state/principle-candidates.jsonl` | append | One record per harvested principle; `origin: bootstrap-raw-scan` |
| `3_resources/people/PEOPLE.md` | rewrite | New columns: Tier, Mentions, Last; owner row in `## Owner` (Step 3.4) |
| `3_resources/people/{owner-id}.md` | create / fill gaps | Owner profile assembled from SOUL + active constitution + registry (Step 3.4) |
| `1_projects/PROJECTS.md` | append rows | Candidate rows added in fresh-onboarding mode (`Status: candidate`) |
| `_sources/inbox/describe-me/` | move consumed files to processed | After consumption, non-template files relocate to `_sources/processed/describe-me/`; folder + `PROFILE.template.md` stay in place (registered source row) |
