---
name: minder:mem:process
description: >
  Process new voice transcripts from _sources/inbox/ into Minder Memory three-layer architecture
  (Records + Knowledge + Hubs). Full pipeline: pre-scan with People Resolution Map,
  LLM noise gate, 16-question classification (incl. content potential, concepts, privacy trio),
  atomization, cross-domain scan, hub detection, per-batch subagent dispatch with self-review, people profile
  enrichment, idea living documents. Emits batch report per run and Evidence Trail
  initial entry in every new knowledge note.
disable-model-invocation: false
---

# /minder:mem:process — Transcript Processing Pipeline

Process new source files from `_sources/inbox/` into the Minder Memory three-layer architecture:
- **Records** (`_records/{meetings,observations}/`) — lightweight transcript-grounded logs (meetings = multi-speaker; observations = solo voice / journal / reflection)
- **Knowledge** (PARA: `1_projects/` through `4_archive/`) — atomic insights
- **Hubs** (`5_meta/mocs/`) — synthesis and evolution tracking

**Philosophy:** Inclusion-biased. Better to over-capture than to miss a fact.
Per-batch full-pipeline subagent (Step 3) + producer self-review (Step 3.7) guarantee trustworthiness.

**Working directory: the zettelkasten base.** Every path in this SKILL — reads,
writes, and the `python3 _system/scripts/…` invocations — is relative to it. A
path prefixed `zettelkasten/` is a *repo-relative value written into a file* (the
PROCESSED.md note column, §3.9), never a path to open.

**Documentation convention:** при любых edits этого SKILL соблюдай `_system/docs/CONVENTIONS.md` — файл описывает current behavior без version/phase/rename-history narratives.

> **Schema expectations.** Skill polagaется на наличие системных файлов: `SOUL.md`,
> `OPEN_THREADS.md`, `CURRENT_CONTEXT.md`, `log_maintenance.md`, `log_process.md`,
> `log_lint.md`, `BATCH_LOG.md`, `batches/`, `batch-format.md`, `registries/SOURCES.md`;
> расширенная схема PEOPLE.md с колонками Tier/Mentions/Last; `## Evidence Trail` секция
> в knowledge notes. Если во время flow обнаруживается несостыковка (missing file,
> unexpected schema, inconsistent references между registries) — **не останавливаться
> и не гадать**: зафиксировать вопрос в `_system/state/CLARIFICATIONS.md` под `## Open Items`
> с type `process-compatibility`, применить conservative default, продолжить обработку.
> User разбирает на ревью.

## Arguments

`$ARGUMENTS` supports:
- `--dry-run` — list new files without processing
- `--file <path>` — process a single specific file (skip PROCESSED.md comparison)
- `--reprocess` — re-process files already in PROCESSED.md
- `--limit N` — cap the **transcript** processing queue at the first `N`
  (oldest) files after the chronological sort, applied in §2.3 (before the
  §2.4 move-to-processed) to the `Family: transcript` files only.
  **`DEFAULT_TRANSCRIPT_LIMIT = 12`** — this line is the single source of truth
  for the cap; when the flag is absent the queue is capped at that value. Do
  NOT restate the number anywhere else (scheduler prompts, §2.3, §2.5 refer to
  "the effective `--limit` / its default", never a literal). Accepted values:
  integer `N >= 1` → cap at N; `N = 0` → process zero transcripts (metric-day
  still runs); `all` (or any non-integer) → unbounded, process every
  transcript. `N >= transcript count` → no-op (full list). `metric-day`
  (biometric / activity) files are NEVER capped — deterministic, inline, cheap;
  a cap would leave biometric-day gaps. Files beyond the cap stay in
  `_sources/inbox/` (not moved in §2.4) and are picked up next run — the queue
  is inbox-driven, nothing is lost. Purpose: bound per-run subagent work so a
  large backlog (e.g. after a paused scheduler) self-drains across successive
  runs instead of exhausting one run's cloud wall-clock. Escape hatch for a
  supervised manual catch-up with no wall-clock pressure: `--limit all`.
  Silently ignored under `--file`, `--reprocess`, and `--reprocess-corpus`
  (the last has its own `--corpus-limit`) — the default cap applies to the
  plain inbox path only.
- `--reprocess-corpus` — historical-corpus mode: walk existing records and
  knowledge notes (instead of inbox), re-extract concepts via the matcher
  subagent, UPDATE existing files in place. See **Mode: --reprocess-corpus**
  below for the per-step delta. Mutually exclusive with `--file` and
  `--reprocess` (which target raw transcripts in `_sources/`).
- `--scope <records|knowledge|all>` — only meaningful with `--reprocess-corpus`;
  narrows the corpus walk. Default `all`.
- `--corpus-limit N` — only meaningful with `--reprocess-corpus`. After the
  chronological sort (§2.3 reprocess-corpus delta), truncate the in-scope
  file list to the first `N` entries. Use for staged / smoke / chunked runs
  on a large historical corpus when you want to exercise the full pipeline
  (lock → matcher subagent → frontmatter writeback → manifest emission →
  log entry → BATCH_LOG row) end-to-end on a bounded blast radius before
  unleashing on the rest. `N <= 0` → process zero files (explicit no-op,
  Early Exit Check fires). `N >= corpus size` → full list (no-op of the
  flag). Silently ignored without `--reprocess-corpus`. The deterministic
  substrate is `_common.py::select_reprocess_corpus_files`.
- `--reconcile-tasks` — recovery mode: run `reconcile_tasks.py --report`, classify the reported orphans (task-ids in notes but absent from TASKS.md) and file them into the right section + stream, recompute the header. Bounded to the orphan delta. No transcript processing. Entry point for the lint `task-aggregation-orphans` CLARIFICATION and the update-migration nudge (Step 4.1).
- `--reconcile-calendar` — recovery mode: re-aggregate the future `📅` events of the notes `reconcile_calendar.py --report` flags as dropped. No transcript processing (Step 4.2).
- `--no-sync-check` — skip the data-freshness pre-flight (see below)

---

## Mode: --reprocess-corpus

A single flag that re-routes the same pipeline at four well-defined points
so that the historical corpus can be re-extracted for `concepts:` (and
`domain_resolutions[]`) without recreating any record or knowledge note.
Reuses every other guarantee of `/minder:mem:process` — the same matcher
subagent, the same registry-aware vocabulary, the same batch manifest
emission with `concepts.upserts[]` carrying types.

**Why this lives in `/minder:mem:process`, not its own SKILL.** The historical-
backfill operation is structurally identical to processing inbox
transcripts: open content, run the LLM-noise / classification /
concept-matcher chain, emit a batch manifest. Forking it into a parallel
SKILL means dual maintenance of every contract change (manifest schema,
matcher prompt, batch partitioning, lock semantics). One SKILL, one
mental model.

**Per-step delta vs default mode.** All steps not listed run unchanged.

| Step | Reprocess-corpus behaviour |
|---|---|
| Pre-flight, Early Exit, Concurrency Lock | Same `_sources/.processing.lock`. Lock matrix unchanged. Early Exit Check is replaced by «corpus scope is non-empty» check (the inbox glob is irrelevant). |
| Step 0 Pre-Scan | Skipped. The corpus is already classified; pre-scan exists to seed inbox→records mapping which doesn't apply. People Resolution Map is not built; concept-matcher operates on already-resolved frontmatter. |
| Step 2.1 Scan Directories | **Branch:** walk `_records/{meetings,observations}/` and PARA `1_projects/`, `2_areas/`, `3_resources/` for files with `layer:` ∈ {`record`, `knowledge`}. Skip `4_archive/` (history is not rewritten). `--scope records` → records only; `--scope knowledge` → PARA only; `--scope all` (default) → both. The deterministic substrate is `_common.py::select_reprocess_corpus_files(base, scope, limit)` — orchestrator MUST call it (or shell to a script that does) rather than reimplementing the walk. |
| Step 2.2–2.3 File Selection / Sort | Sort chronologically by `created:` frontmatter (fall back to filename `YYYYMMDD-` prefix; final fallback `9999-99-99` so undated files land last without crashing). When `--corpus-limit N` is passed, truncate the post-sort list to the first `N` entries (`N <= 0` → empty list → Early Exit Check fires; `N >= len(files)` → full list, flag is no-op). |
| Step 2.4 Move to Processed | **Skipped.** Sources are already in `_sources/processed/`; corpus files are themselves the artefacts being mutated. |
| Step 3.0.1 Batch Partitioning | Token threshold T identical. Primary keys for batch grouping: by `extracted_from:` cluster (notes sharing a record) → by domain cluster → alphabetical fallback. Unchanged math. |
| Step 3.1 Read Transcript | **Branch:** read the file ITSELF (frontmatter + body) AND, when present and accessible, read the underlying source via the file's `source:` frontmatter pointer for richer matcher context. If `source:` is missing or its target file does not exist on disk → log entry to `log_process.md` (`reprocess-corpus: missing-source`), continue with the note's body alone. NEVER raises CLARIFICATION (legacy state is expected). |
| Step 3.2 LLM Noise Gate | Skipped. Corpus content is by definition non-noise. |
| Step 3.3 Semantic Context Loading | Same as default mode (hubs / related notes loaded for matcher grounding). |
| Step 3.4 LLM Classification | **Unchanged.** All 16 questions still run; Q15 (concepts) and Q16 (privacy) carry the load. Q1-Q14 outputs are accepted but not consumed by Step 3.5 in this mode (they remain available to the manifest for completeness). |
| Step 3.4.5 Concept Matcher Subagent | **Unchanged.** Sees the populated CONCEPTS.md, prefers existing canonical names verbatim, coins new ones with type assignment. Idempotent on a clean state. |
| Step 3.5 Create Outputs | **Branch:** UPDATE existing files. For each note, replace the `concepts:` array verbatim with the matcher output (post-`normalize_concept_name`). Apply `domain_resolutions[]` (`drop` / `remap` per the same contract). Preserve every other frontmatter field verbatim; never touch the body. NO new records, NO new knowledge notes, NO hub creation, NO `Evidence Trail` mutation. |
| Step 3.6 Structural Verification | Runs the same checks against the updated frontmatter, except folder placement: this mode never moves a file. |
| Step 3.7 Self-Review | Skipped. Self-review's coverage manifest assumes new extraction; reprocess re-uses prior atomization decisions. |
| Step 3.7.5 Constitution Alignment | Skipped (extraction-time concern). |
| Step 3.8 People Profiles | Skipped (no new mentions are introduced). |
| Step 3.9 System Updates | Skipped (TASKS / CALENDAR / OPEN_THREADS already reflect the originally-extracted state). |
| Step 3.10 Verify Source Integrity | Runs (cheap, read-only). |
| Step 4.1 TASKS.md / 4.2 CALENDAR.md / 4.3 HUB_INDEX.md | Skipped — no new tasks / events / hubs created. |
| Step 4.4 Content Potential Verification | Skipped. |
| Step 4.5 Batch Verification | Runs (frontmatter integrity check). |
| Step 4.6 Content Proportionality | Skipped (no creation ratio to evaluate). |
| Step 4.7 Batch Data Accumulation | Runs. The accumulator's `records[]` and `knowledge_notes[]` lists are populated under the `updated[]` keys (not `created[]`). `concepts.upserts[]` IS populated — this is the load-bearing output of the mode. |
| Step 5 Completion Gate | Runs unchanged. |
| Step 5.5.1.5 Batch Manifest | **Branch (data-only):** identical schema; populates `records.updated[]`, `knowledge_notes.updated[]`, `concepts.upserts[]`. `created[]` arrays are emitted empty. `processor: "minder:mem:process"` unchanged; `format_version: "2.4"` unchanged. |
| Step 6 Report | Renders «Reprocessed: N» instead of «Created: N». |

**Idempotency.** Re-running `--reprocess-corpus` on a clean post-reprocess
state produces zero frontmatter changes (matcher reuses canonical names
from the registry) and zero `concepts.upserts[]` rows that materially
shift `CONCEPTS.md` after maintain Step 4.5.

**Drift handling.** When the matcher returns a `concepts:` set whose
symmetric difference with the file's existing set exceeds 50 % of the
union (i.e., the new extraction radically disagrees with the prior one),
DO NOT silently overwrite. Surface a CLARIFICATION
(`type: concept-drift-on-reprocess`) with the file path, prior set, new
set, and apply the new set conservatively (the matcher run is canonical
because it sees the current registry). Owner reviews; the buffer makes
the decision recoverable.

**Lock matrix.** Reprocess-corpus takes the same `_sources/.processing.lock`
as default mode, and reads the same seven lock files (see **Concurrency Lock**).

---

## Pre-flight: data freshness (non-blocking)

Before any heavy work, check if the owner's `origin` has commits not
yet pulled into this clone. Multi-device setups (phone records into
inbox/ on laptop A, this laptop B is a passive consumer) mean local
inbox/ may be stale.

Skip entirely if `--no-sync-check` is passed.

```bash
remote_ahead=0
if git remote get-url origin >/dev/null 2>&1; then
  git fetch origin --quiet 2>/dev/null || true
  # `git_current_branch` (scripts/lib/git.sh) — NOT `rev-parse --abbrev-ref`,
  # which exits 0 and prints the literal string `HEAD` when HEAD is detached,
  # making the comparison ref `origin/HEAD` and the count meaningless.
  # Sourced by repo-root path: the run's cwd is the zettelkasten base, one
  # level below, so a bare `scripts/lib/git.sh` silently resolves to nothing
  # and leaves the whole check inert.
  . "$(git rev-parse --show-toplevel)/scripts/lib/git.sh" 2>/dev/null || true
  branch=$(git_current_branch 2>/dev/null || true)
  if [ -n "$branch" ]; then
    remote_ahead=$(git rev-list --count "HEAD..origin/${branch}" 2>/dev/null || echo 0)
  fi
fi
```

Detached HEAD leaves `branch` empty and `remote_ahead` at 0 — there is no
remote-tracking counterpart to compare against, so the check silently
proceeds like any other unavailable-signal case.

Cases:
- `origin` not configured, or fetch failed (offline) → silently proceed.
- `remote_ahead == 0` → silently proceed.
- `remote_ahead > 0` → render owner-facing prompt:
  ```
  ⓘ origin/<branch> ahead by <N> commit(s). New transcripts may be
    waiting in inbox/ from another device.

    [s] run /minder:mem:sync-data first  (recommended — abort current /minder:mem:process)
    [c] continue with current local state  (safe — won't lose anything)
    [d] show pending commits         (then re-prompt)
  ```
  - `s`: print «owner: run `/minder:mem:sync-data`, then re-run `/minder:mem:process`», exit 0.
  - `c`: proceed (`remote_ahead` snapshot logged in batch report for traceability).
  - `d`: `git log HEAD..origin/$branch --oneline`, then re-prompt s/c.

The check is a courtesy nudge, not a gate — `c` is always safe (process
operates on local working-tree only; pulled commits won't be lost).

---

## Early Exit Check

**FIRST action — before lock, context, or pre-scan.**

Quick-scan `_sources/inbox/` subdirectories for any transcript files
(`transcript*.md` in dir-layout sources, or top-level `*.md` in flat-md
sources). `*.template.md` files never count as candidates (§2.2). Use
Glob, not full reads.

- If `--file` or `--reprocess` flag: skip this check (files come from elsewhere).
- If `--reprocess-corpus`: skip this check; instead glob the corpus per Step 2.1's reprocess-corpus branch and exit early only when the corpus walk yields zero in-scope files.
- If 0 candidate files found: report `"No new transcripts in inbox — nothing to process."` and **exit immediately**. No lock, no context loading, no system file reads.
- If `--dry-run` with 0 files: same — report empty and exit.

This saves ~10 file reads and all pre-scan work on empty runs.

---

## Concurrency Lock

Runs only when Early Exit Check found files to process.

**Cross-skill lock check — read all seven lock files first:**
- `_sources/.maintain.lock` — exists → abort «`/minder:mem:maintain` running, try again later»
- `_sources/.lint.lock` — exists → abort «`/minder:mem:lint` running, try again later»
- `_sources/.agent-lens.lock` — exists → abort «`/minder:mem:agent-lens` running, try again later»
- `_sources/.content.lock` — exists → abort «`/minder:mem:content` running, try again later»
- `_sources/.roles.lock` — exists → abort «`/minder:mem:roles` tick running, try again later»
- `_sources/.resolve.lock` — exists → abort «`/minder:mem:resolve-clarifications` running, try again later»
- `_sources/.processing.lock` — exists → abort «another `/minder:mem:process` run in progress»

All seven skills mutually exclusive — the matrix is `_system/docs/SYSTEM_CONFIG.md`.

1. After cross-skill checks pass, create `_sources/.processing.lock` with content: `{ISO timestamp} — {session info}`
2. On completion (success or failure): **DELETE** `_sources/.processing.lock`

The lock file MUST be deleted in all exit paths — normal completion, errors, and early abort.
If you find a stale lock (>2 hours old), warn the user and offer to delete it.

---

## Step 0.0: Regenerate Constitution Derived Views

Invoke `/minder:mem:regen-constitution` (or run `python3 _system/scripts/regen_all.py`)
as the very first action. This ensures SOUL.md Values zone,
`_system/views/constitution-core.md`, and `_system/views/CONSTITUTION_INDEX.md`
reflect the current state of `0_constitution/` before any context load.

Consistency rule for the whole platform: every pipeline that reads a derived
view regenerates first. Cost is ~100 ms; the guarantee is that nothing in
Step 1 Context Load is stale relative to source.

Failure of this step is fatal — report the underlying script error and stop.
Partial derived views would poison downstream reasoning.

---

## Step 0: Pre-Scan

> **Reprocess-corpus mode:** skip Step 0 entirely. Pre-scan exists to
> seed inbox→records mapping; the corpus is already classified.

Before any processing begins, scan ALL new transcripts to build shared context.

### 0.0a Split-name recovery

Runs before §0.0b, because it decides what the item folders even are.

A producer names an export after the recording's title, and a title can contain
`/` — «07-09 Встреча - A/B-тест», «вкладки Top/New». No filesystem accepts that
in a name, so the sync or the unzip turns one segment into two directories and
the item arrives one level deeper than the layout says.

`normalize_portable_name` cannot reach this: it maps `/` → `-` on a NAME, and by
the time the engine looks there is no illegal character left — both segments are
legal names. The information survives in the directory structure, and joining
the segments with `-` reproduces exactly what the normaliser would have made of
the original string.

```bash
python3 _system/scripts/repair_split_names.py --inbox _sources/inbox --apply --json
```

Scope comes from `SOURCES.md`, never from guesswork:

- **`Skip Subdirs` is never entered** (`garmin/raw/`). A source declares those
  folders out of the queue; a repair that reaches past a declared boundary and
  MOVES owner data is the failure this engine exists to prevent.
- **`dir-per-item` / `dir-with-summary`** are the only layouts eligible for an
  autonomous join — they are the ones whose items are folders.
- **`flat-md`, or a source not in the registry** — items are files, so the
  layout defines no folders at all. A directory there is surfaced and never
  joined: it may be the owner's own organisation.

Within an eligible layout, a **split-name candidate** is a directory carrying no
item marker of its own and containing subdirectories — a shape the folder
layouts never otherwise produce.

- **Exactly one child, and that child is a complete item** → join, silently.
  Qualifies for the autonomous-resolution exception (ENGINE_DOCTRINE §3.1): the
  join is a pure function of the two names, it refuses on any ambiguity, and the
  owner has nothing to decide because it is plainly one name.
- **Anything else** — several children, a child that is not an item, a target
  name already taken → **no move**. Surface a `source-layout-split-name`
  CLARIFICATION naming the paths, and leave the item where it is; it processes
  next run once the owner resolves.
- **Audit** — list every join (`old → new`) in the batch report and the
  `log_process.md` run entry. Zero joins → no mention.

### 0.0b Portable-name normalisation

Runs before Quick Read touches any inbox path. Walk
`_sources/inbox/{id}/` for every Active + Reserved source: each immediate
child (folder or file, plus files one level inside per-item folders) whose
name fails `_common.py::is_portable_name` is renamed to
`normalize_portable_name(name)`. Rationale: producer tools (Plaud and
similar) name export folders with pure-ISO timestamps
(`2026-04-29T14:09:30Z`) whose colons are illegal on Windows/NTFS; renaming
BEFORE anything reads or references the path guarantees every downstream
artefact (pre-scan briefing, `source:` frontmatter, `**Transcript:**`
lines, PROCESSED.md, manifests) is born with the safe name — nothing ever
needs rewriting. Spec: `_system/registries/SOURCES.md` →
«Portable names (Windows compatibility)».

Rules:

- **Autonomous, silent per-rename** — qualifies for the
  autonomous-resolution exception (ENGINE_DOCTRINE §3.1): deterministic
  pure function, conservative failure mode, high-volume surface. No
  CLARIFICATION per rename.
- **Collision** — if the target name already exists in the same directory,
  do NOT rename and do NOT guess a suffix: surface a
  `portable-name-collision` CLARIFICATION and skip the item this run
  (conservative default: item stays in inbox, processed next run after
  owner resolves).
- **`normalize_portable_name` returns None** (name empty after
  normalisation) — same treatment as collision: skip + CLARIFICATION.
- **Audit** — list every rename (`old → new`) in the batch report and in
  the `log_process.md` run entry. Zero renames → no mention needed.
- **Scope** — inbox only. Never touch `_sources/processed/` (legacy names
  there are grandfathered; references point at them as-is).

### 0.1 Quick Read

For each new file selected by §2.1 (layout-aware), read a cheap preview:
- If the filename is `transcript_with_summary.md`: read only the summary section (the part AFTER `<transcript_to_summary_delimiter>`). The summary is short — full read is acceptable.
- If the filename is `transcript.md`: read first 50 lines.
- For `flat-md` files (any other filename — sources like `notes`, `crafted`): read first 50 lines.

Extract (quick, no deep analysis):
- Date/timestamp from folder name (`dir-per-item` / `dir-with-summary`) or from filename / mtime (`flat-md`). Folder-name forms accepted are listed in §2.3.
- Names of people mentioned
- Main topics / keywords
- Source type — derived from the parent folder under `_sources/inbox/{source-id}/...`; the canonical whitelist is `_system/registries/SOURCES.md`.

### 0.2 Build People Resolution Map

Collect ALL person names/diminutives across ALL new transcripts.
Load `3_resources/people/PEOPLE.md`.
Resolve each name against the registry.

**The raw transcript outranks any summary of it.** Where a source ships both
— a recorder's own LLM summary alongside the verbatim text — resolve names
against the verbatim text, and treat a name that appears only in the summary
as unattested. A summariser states the wrong name with exactly the fluency it
states the right one, so the error arrives carrying no doubt with it and
propagates into `people:` frontmatter, backlinks and mention counts across the
whole batch before anything contradicts it. When summary and transcript
disagree on who someone is, the transcript wins and the disagreement itself
goes to CLARIFICATIONS with both readings quoted — the mismatch is evidence
about the source, and the next batch from that source deserves it.

Three tiers:

| Tier | Condition | Action |
|------|-----------|--------|
| RESOLVED | Unambiguous match to existing person in PEOPLE.md (exact name or alias) | Use existing ID. BINDING — all files must use this ID |
| NEW | No match in PEOPLE.md, enough context to create profile | Assign canonical ID in `firstname-lastname` format NOW. If last name unknown — AMBIGUOUS instead. BINDING — all files must use this ID |
| AMBIGUOUS | Could match multiple people, or unclear identity | Note the ambiguity. Defer to full-context resolution in Step 3.3. Recommendation only |

Fuzzy matching rules:
- Russian diminutives: Серёга→sergey-kozlov, Ром/Рома→roman-belov, Женя→evgeny-frolov, etc.
  Always resolve to the FULL ID (firstname-lastname), never to a bare first name.
- Check `aliases` field in PEOPLE.md
- **Check CLARIFICATIONS.md Resolved Archive** for known transcription artifacts
  (e.g., «Нуара»→lara-gromova, «Трафт»→ivan-petrov, «Сотки»→maxim-barinov).
  These are RESOLVED tier — use the mapped ID directly.
- First-name-only: if only one person with that name exists → RESOLVED;
  if multiple → AMBIGUOUS

**ID format (MANDATORY):** `firstname-lastname` in transliterated lowercase.
Use the name the author uses in conversation (Костя, not Константин; Леха, not Алексей).
NEVER create IDs without a last name (e.g., `ivan`, `petya`, `oleg`).
If the last name is unknown from the transcript — mark as AMBIGUOUS and log to CLARIFICATIONS.md.
Exception: people known only by one name (e.g., a therapist referred to only as "Мария") — must be explicitly justified.

The People Resolution Map is LIVE and MUTABLE. New people discovered during
processing (e.g., surfaced by §3.7 self-review or in subagent's classification
pass) are aggregated post-batch by orchestrator at Step 3.8, ensuring subsequent
runs use consistent IDs.

### 0.3 Hub Signal Matching

Load `_system/views/HUB_INDEX.md`.
Match pre-scan topics/people against the hub index.
For each file, note which hubs it likely touches.
This guides context loading in Step 3.3 — load only relevant hubs, not all of them.

---

## Step 1: Load Context

Read these system files (in parallel where possible):

0. `_system/docs/ENGINE_DOCTRINE.md` — operating philosophy (load FIRST; binding frame for every step). Cross-skill rules from §3 govern: surface-don't-decide, inclusion-bias-on-capture / curation-on-promotion, idempotency, the owner-LLM contract.
1. `_system/docs/SYSTEM_CONFIG.md` — note formats, naming
2. `5_meta/PROCESSING_PRINCIPLES.md` — 8 principles + values profile
3. `_system/SOUL.md` — identity + current focus + working style (context only)
4. `_system/views/CURRENT_CONTEXT.md` — live state snapshot (context only)
5. `_system/state/OPEN_THREADS.md` — open strategic threads (context only)
6. `3_resources/people/PEOPLE.md` — people registry. Schema: `ID | Name | Role | Org | Profile | Tier | Mentions | Last`. Preserve all columns when writing
7. `1_projects/PROJECTS.md` — project registry
8. `_system/registries/TAGS.md` — `tags:` namespace labels. **Read-only:** its tables are an AUTO-GENERATED census `render_tags.py` derives from note frontmatter; nothing in this pipeline writes there
9. `_system/registries/CONCEPT_NAMING.md` — canonical concept-name format. **Autonomous-pipeline policy:** the engine resolves all concept-name format issues with deterministic heuristics — never raises CLARIFICATIONs, never blocks owner. `_system/scripts/_common.py::normalize_concept_name()` is the single source of truth: normalisation algorithm + drop-on-impossibility (returns `None` to signal skip when non-ASCII residue or empty-after-strip). For non-English source terms, translate semantically to English; if genuinely untranslatable, drop the entry rather than transliterate (transliteration splits graph identity).
10. `_system/registries/AUDIENCES.md` — `audience_tags` whitelist (canonical five + tenant Extensions). **Autonomous-pipeline policy:** unknown / non-canonical / non-whitelisted tags are silently dropped (entity stays `[]`, owner-only). Helper: `_system/scripts/_common.py::normalize_audience_tag()`. The fail-closed default (`[]`) is the right outcome on any uncertainty — false-positive sharing leaks; false-negative just keeps content owner-only.
11. `_system/registries/DOMAINS.md` — `domains:` (plural — notes / hubs / typed objects) and `domain:` (singular — constitution principles) whitelist (canonical thirteen ∪ tenant Extensions). **Autonomous-pipeline policy (cascade):** (1) deterministic normalisation via `_system/scripts/_common.py::normalize_domain()` (case + separator drift autofixes to canonical); (2) slash-syntax (`work/learning`, `personal/psychology`) is split via `expand_domain_entry()` and each part is filtered against the accept set independently — `work/learning` keeps both, `work/process` keeps `work` and drops `process`; (3) residuals that survive (1) and (2) but miss the whitelist enter the concept-matcher subagent (Step 3.4.5) which runs an LLM remap-or-judge pass and emits `domain_resolutions[]` with `keep | remap | drop | clarify`; (4) `clarify` verdicts surface as `domain-resolution` CLARIFICATIONs with the conservative default (drop the value). Canonical set lives in `ALLOWED_DOMAINS`. Domains answer "which life area" — keep them coarse and structural; concrete topics belong in `concepts:`, categorical buckets in `tags:`.
12. `_system/registries/SOURCES.md` — inbox source whitelist (consumed by Step 2.1)
13. `_system/views/HUB_INDEX.md` — hub index (if not loaded in Step 0)
14. `_system/state/PROCESSED.md` — already processed files
15. `_system/state/CLARIFICATIONS.md` — pending clarifications.
    Also scan **Resolved Archive** table: previously resolved name variants (e.g.,
    «Нуара» = Лара Громова, «Трафт» = Петров). Use these to auto-resolve
    transcription artifacts in new transcripts without re-creating ambiguities.
16. `_system/registries/FOLDERS.md` → `## Routing Rules` — the folder of every knowledge note; passed verbatim into every batch briefing (§3.0.3)

**CLARIFICATIONS HARD RULE.** При `confidence < threshold` — не принимать решение
молча. Записать вопрос в `_system/state/CLARIFICATIONS.md` под `## Open Items`, использовать
conservative default, продолжить работу. Применяется на всех шагах skill.

**SOUL / CURRENT_CONTEXT / OPEN_THREADS — контекст-only.** Не модифицируются этим
skill. Используются для лучшего понимания priority/focus при классификации нот
и адверсариал-аудите. Их incremental обновление — ответственность `/minder:mem:maintain`.

---

## Step 2: Find New Files

> **Reprocess-corpus mode:** the «New Files» framing is repurposed as
> «Files In Scope». Section 2.1 scans the corpus instead of the inbox;
> section 2.4 is skipped. See the per-step delta table at top of file.

### 2.1 Scan Directories

> **Reprocess-corpus branch:** ignore SOURCES.md entirely. Walk these
> roots for files whose frontmatter `layer:` ∈ {`record`, `knowledge`}:
> `_records/meetings/`, `_records/observations/`, `1_projects/`,
> `2_areas/`, `3_resources/`. NEVER `4_archive/`. The `--scope` argument
> further narrows: `records` → first two roots only; `knowledge` → last
> three only; `all` (default) → all five. PARA `README.md` files are
> excluded (no `layer:` frontmatter).
>
> The deterministic walk + chronological sort + optional `--corpus-limit`
> truncation lives in `_system/scripts/_common.py::select_reprocess_corpus_files`.
> Orchestrator invokes it (directly via Python or via shell) so the file
> list is reproducible and unit-testable. Sort precedence: YAML `created:`
> → filename `YYYYMMDD-` prefix → `9999-99-99` sentinel. Truncation
> happens AFTER sort so `--corpus-limit N` always returns the N
> chronologically-earliest in-scope files — staged runs are deterministic
> and contiguous along the timeline.

Load `_system/registries/SOURCES.md` — the whitelist of inbox source types.
Every source-specific behaviour is declared there, in the row's columns; this
SKILL branches on the columns (`Family`, `Layout`, `Skip Subdirs`), never on a
source ID. Source IDs appear below only as illustrations of a column value.

Iterate over rows in `## Active Sources` and `## Reserved Sources` (skip
`## Deprecated Sources` rows entirely). For each row, scan `Inbox Path`
according to the row's `Layout` column:

| Layout | Scan rule |
|---|---|
| `flat-md` | Glob `{Inbox Path}/*.md` (top-level only — never recurse). |
| `dir-per-item` | For every immediate subfolder of `Inbox Path`, pick exactly one file with this priority: (1) `transcript.md` if present, (2) the single `*.md` file in the subfolder otherwise. If multiple `*.md` files exist with no `transcript.md`, surface a `source-format-anomaly` CLARIFICATION (genuine ambiguity — picking the wrong file degrades downstream quality). Zero `*.md` → skip silently (empty subfolder). |
| `dir-with-summary` | For every immediate subfolder of `Inbox Path`, pick exactly one file with this priority: (1) `transcript_with_summary.md` if present (combined raw+summary, see §3.1 delimiter contract), (2) `transcript.md` otherwise, (3) the single `*.md` file in the subfolder otherwise. A folder with no `*.md` at all is skipped silently (empty / partial export). A folder with multiple `*.md` files but no `transcript_with_summary.md` / `transcript.md` surfaces a `source-format-anomaly` CLARIFICATION (ambiguity). A folder that has BOTH `transcript_with_summary.md` and `transcript.md` never reads `transcript.md` — the combined file is canonical. |

> **Naming tolerance.** Folder names and contained filenames are best-effort
> hints, never contracts — the engine never blocks on naming. The binding rules
> (what falls back to mtime, what is taken as-is, and the three cases that do
> earn a CLARIFICATION) are `_system/registries/SOURCES.md` →
> «Naming tolerance (universal across all source-types)», already loaded above.

For every layout, honour the row's `Skip Subdirs` column — any subdirectory
whose name matches an entry in that comma-separated list is skipped without
warning. Reserved sources may have empty inbox folders; that is expected and
NEVER an error.

Adding a new source is declarative: invoke `/minder:mem:source-add` (or append a
row to SOURCES.md + create `_sources/inbox/{id}/.gitkeep` and
`_sources/processed/{id}/.gitkeep` manually). No edits to this SKILL.

Everything in `_sources/inbox/` not skipped above is unprocessed — the
filesystem IS the primary filter. PROCESSED.md serves three roles:
1. **Crash recovery** — files are moved to `processed/` BEFORE processing (Step 2.4).
   If a file is in `processed/` but NOT in PROCESSED.md, it was moved but processing
   failed — needs retry.
2. **`--reprocess` support** — identifies which files to re-process from `processed/`.
3. **Audit log** — historical record of all processing operations.

> **Reference material under sources.** Some sources expose reference content
> (raw payloads, escape-hatch data) inside a subfolder that must NEVER reach
> the processing queue. The mechanism is the `Skip Subdirs` column on
> SOURCES.md. Example: `garmin` declares `Skip Subdirs: raw`, so
> `_sources/inbox/garmin/raw/` and its mirror under `processed/` are invisible
> to this SKILL.
>
> **Dual-consumed sources.** The `describe-me` source is also read by
> `/minder:mem:bootstrap` (inbox + processed sides) as the primary SOUL.md seed;
> bootstrap moves consumed inbox files to the processed-side mirror through
> its own contract. This SKILL treats `describe-me` as a regular flat-md
> source — whatever bootstrap has not consumed is processed normally. Both
> consumers move files to `processed/` before use, so nothing is ingested
> twice.

### 2.2 File Selection

All files in `_sources/inbox/` are candidates for processing.

**Template exclusion (engine-wide).** Files named `*.template.md` are NEVER
processing candidates — in any source, any layout, any mode (including
`--reprocess` / `--reprocess-corpus` and the Early Exit Check glob). They are
spec/seed material shipped by the engine (e.g. `describe-me/PROFILE.template.md`),
not owner content. Skip silently, no CLARIFICATION.

If `--file <path>`: process only that file (can be in inbox or processed).
If `--reprocess`: also scan `_sources/processed/` and re-process specified files.

### 2.3 Sort Chronologically

Sort new files by timestamp ASCENDING (oldest first). Extract the timestamp
from the folder name (for `dir-per-item` / `dir-with-summary` layouts) or
the file name / mtime (for `flat-md`).

Folder-name forms accepted (all may coexist within one source):

1. **Portable ISO** (canonical for new items, post-§0.0b) — `2026-04-29T14-09-30Z` → hyphens in the time part map back to `HH:MM:SS`; use as-is.
2. **Pure ISO** — `2026-04-29T14:09:30Z` → use as-is. Legacy form: appears only under `_sources/processed/` (grandfathered) — §0.0b normalises it away in inbox.
3. **ISO + topic suffix** — `2026-04-29T14-09-30Z_short topic` (or the colon variant) → split on first `_`, parse left side.
4. **Date + topic** — `2026-04-29_short-topic` → midnight UTC of that date.
5. **Legacy short date + topic** — `04-29 short topic` → assume current year, midnight UTC. No CLARIFICATION; mtime is the secondary anchor if parsing later turns out wrong.
6. **No parseable date** → fall back to file mtime silently. Never drop the file. No CLARIFICATION — the naming-tolerance principle (see §2.1) applies: owners and producers may create folders in any layout, the processor proceeds best-effort.

The engine surfaces a `source-folder-naming` CLARIFICATION ONLY when both parsing fails AND mtime is unreliable (e.g. mtime is in the future, or noticeably older than file contents would suggest because the file was moved/copied with metadata reset). Pure naming non-canonicity is not a CLARIFICATION-worthy event — it is a hint about quality, not a blocker.

Chronological order matters: earlier transcripts provide context for later ones —
within a batch via shared subagent context, across batches via the pre-scan
briefing (see §3.0.1, §3.0.3).

**Transcript cap (`--limit`, transcripts only).** After the sort above, cap
the `Family: transcript` files (per SOURCES.md Family column — see §2.5) to the
effective `--limit` — the flag value, or its default when the flag is absent
(the canonical default lives in §Arguments `--limit`; never restate the number
here). `--limit all` disables the cap. Files beyond the cap are left untouched
in `_sources/inbox/` — NOT moved in §2.4 — and are picked up by a later run
(the queue is inbox-driven, so nothing is lost). `metric-day` files are exempt
and always process in full. Edge cases: `0` → zero transcripts retained;
cap `>=` transcript count → no-op. The retained set is the "files to be
processed" that §2.4 moves. When the cap actually truncated the queue, state it
in the run's report — «processed the N oldest of M new transcripts; M−N remain
in inbox for the next run (pass `--limit all` to drain in one go)» — so a bound
run never looks like silent under-processing. Purpose: bound per-run subagent
work so a large backlog self-drains across runs instead of exhausting one run's
cloud wall-clock.

If 0 new files found (after any `--limit` truncation): report "No new
transcripts to process" and exit. If `--dry-run`: list new files with
timestamps (reflecting `--limit`), then STOP.

### 2.4 Move to Processed (before processing)

> **Reprocess-corpus mode:** skip this step entirely. Source transcripts
> are already in `_sources/processed/`; corpus files are themselves the
> artefacts being updated.

For each file to be processed:
1. Move from `_sources/inbox/{source}/{id}/` to `_sources/processed/{source}/{id}/`
2. This ensures `source:` fields in created notes point to the FINAL file location immediately
3. If processing fails after move, crash recovery detects: file in `processed/` but NOT in PROCESSED.md → needs processing

This "move-first" approach guarantees:
- `source:` fields are always correct (no temporary mismatch)
- New deliveries to `inbox/` won't be confused with in-progress files
- PROCESSED.md entry = fully processed; no entry = needs processing or retry

---

## Step 2.5: Family Routing — Inline Pre-processing for `metric-day`

After Step 2 produces a chronological file list, partition by the
SOURCES.md `Family` column before Step 3 dispatch:

- `Family: transcript` (default) → flows into Step 3 batch + subagent
  + LLM pipeline as before. No change. (This partition was already capped in
  §2.3 by the effective `--limit` — default-on unless `--limit all` — the
  `metric-day` branch below is never capped.)
- `Family: metric-day` → processed **inline, synchronously, in the
  main orchestrator process** by `_system/scripts/process_metric_day.py`.
  NO subagent dispatch, NO LLM. Each file goes through
  `process_metric_day.run()` deterministically (~100 ms per file).
- `Family: recap` → reserved; falls back to `transcript` until the
  reserved branch ships.

Default for rows lacking the `Family` column → `transcript`.

### 2.5.1 Metric-day branch contract

The metric-day branch is **profile-driven**: `process_metric_day.run()`
resolves the source's `MetricDayProfile` via `metric_day_profiles.for_source(source_id)`
(`garmin`/`oura` → **biometric**, `activitywatch` → **activity**; unknown →
biometric default). The profile determines the record family directory,
`kind`/`domains`, the metric vocabulary + thresholds file, the streak concept
map, and the manifest `primary_type`. The orchestrator itself is profile-agnostic
— the same code path serves biometric wearables and behavioural feeds. Below,
`<family>` = the profile's family dir (`biometric` | `activity`).

For each file in the metric-day partition, in chronological order
(date-sorted by filename):

1. Call `process_metric_day.run(source_path, base_dir=…, source_id=<source-id>)`.
2. Outcomes — one of:
   - `emitted` — record written under `_records/<family>/<source-id>/<date>.md`
     (e.g. `_records/biometric/garmin/…` or `_records/activity/activitywatch/…`),
     that source's baselines + streaks updated, source moved to
     `_sources/processed/<source>/<filename>` (raw payload moved alongside,
     matching any extension — garmin/oura `.json`, activitywatch `.json.gz`).
   - `skipped-failure-stub` — source had `status: collection-failed`
     OR filename began `collection-failed-` / ended `.resolved.md`. No
     record emitted; source moved to processed; log line written.
   - `no-op-same-content` — record already exists with matching
     `source_hash` frontmatter field. Source moved to processed; no
     record write.
   - `rerender-auto-absorbed` — record exists but the re-collected
     source is richer-or-equal (more/equal real metrics). Authoritative
     refresh (a healed device→cloud sync gap, a provider backfill): the
     healed source is absorbed and records + baselines are recomputed
     forward from this date. No CLARIFICATION — metric-day records are
     deterministic device projections with no owner edits to protect.
   - `rerender-kept-existing` — record exists and the re-collected
     source is poorer/empty (fewer real metrics). The good record is
     kept, never clobbered by a degraded re-collect. Source moved to
     processed; no record write.
3. Concepts that surface on the emitted record's frontmatter are
   **profile-specific** (from the profile's streak concept map):
   - biometric: `low_hrv_streak`, `sleep_debt`, `rhr_elevation_streak`,
     recovery concepts (`recovery_after_low_hrv_streak`), and categorical
     transitions (`train_status_transition_to_productive`,
     `readiness_changed_to_moderate`).
   - activity: `late_night_work_streak`, `focus_drop_streak`,
     `low_productivity_streak`, `context_switch_spike_streak`,
     `fragmented_focus_streak`, `meeting_overload_streak` (no categorical
     transitions — the activity profile carries no categorical pairs).
4. Privacy trio is hard-set per profile in `process_metric_day.py`:
   `is_sensitive: true`, `audience_tags: []`, `origin: personal`. Per-record
   override is NOT a normal path — both biometric and activity data are
   owner-only by design (activity titles/URLs leak work/client context).
5. Manifest emission — each emitted record contributes an entry to the
   unified batch manifest under `records.created`, with
   `primary_type` = the profile kind (`biometric` | `activity`),
   `section_extras.domains`, source_hash, privacy trio, concepts.

### 2.5.2 Cold-start CLARIFICATION

On the very first metric-day file processed for a source (when
`_system/state/<family>/<source-id>/baselines.json` does not exist),
`process_metric_day.run` emits an informational `<profile>-baseline-cold-start`
CLARIFICATION (`biometric-baseline-cold-start` / `activity-baseline-cold-start`).
Resolution: dismiss as resolved with note "expected cold-start". One-time
per source, expected, not actionable.

### 2.5.3 Mixed-batch handling

A single `/minder:mem:process` invocation may contain both `transcript` and
`metric-day` files. Order:

1. Metric-day phase runs **first** inline (deterministic Python).
2. Transcript phase runs **second** via existing Step 3 subagent
   dispatch (LLM pipeline).

Single `batch_id`, single `BATCH_LOG` row, single manifest carrying
multiple sections. The Step 2.4 "move-first" pass is skipped for
metric-day files — the inline branch handles its own moves atomically
with the record write.

### 2.5.4 Why inline, not subagent

Metric-day work is deterministic Python (~100 ms per file). The
subagent infrastructure exists for parallel LLM work; for
deterministic Python it adds overhead without benefit. Inline keeps
state (baselines, streaks) consistent across the batch in a single
process — no cross-subagent state-sync race window.

### 2.5.5 Lock matrix

Reuses the existing `/minder:mem:process` lock — metric-day branch acquires
the same lock as the transcript branch. Mutual exclusion preserved.
No new lock entries.

### 2.5.6 Helper API (internal)

```
metric_day_profiles.for_source(source_id) -> MetricDayProfile   # biometric | activity
biometric_extractor.extract(path) / activity_extractor.extract(path) -> dict   # per profile
biometric_baselines.update(baselines_path, date, metrics, thresholds, numeric_metrics) -> state
biometric_baselines.flag_deviations(state, today_metrics, thresholds) -> [Deviation]
biometric_streaks.advance(streaks_path, date, deviations, concept_map=…) -> (state, events)
process_metric_day.run(source_path, *, base_dir, source_id, …) -> ProcessResult
process_metric_day.run_batch(source_paths, *, base_dir, source_id) -> [ProcessResult]
```

The baseline/streak engines are profile-agnostic — `numeric_metrics` and
`concept_map` are supplied by the resolved profile (default = biometric).
The extractor is dispatched per profile (`activity_extractor` for activity;
the collector emits the activity aggregate upstream, Minder Memory maps it).

Thresholds layered at runtime per profile — `<profile>_thresholds`:
`*.template.yaml` (engine-shipped baseline) → `*.yaml` (live, one-time seed) →
`*.local.yaml` (owner-only override; missing file is OK). Biometric →
`biometric_thresholds.*`; activity → `activity_thresholds.*`.

---

## Step 3: Process Files (per-batch full-pipeline subagents)

### Architecture

The orchestrator partitions the chronologically-sorted file list (from §2.3)
into batches and dispatches one full-pipeline subagent per batch. Each
subagent runs Steps 3.1–3.7 (read → classify → produce notes → structural
verify → self-review) for every transcript in its batch, in shared context.

Steps that REMAIN in the orchestrator and run AFTER all subagents complete:
3.7.5 (constitution alignment), 3.8 (people profiles), 3.9 (system updates),
3.10 (source integrity), and Steps 4.x / 5.x.

**Why this topology:** trust unit = «Opus + sufficient context for the work
unit». Per-batch subagent gives every transcript dedicated attention without
batch-saturation pressure on the orchestrator. Cross-transcript context
within a batch is preserved (full prior transcripts are in the same
subagent context, not summaries).

### 3.0.1 Batch Partitioning

- **Order:** chronological, by source timestamp (filename-derived) — never
  reordered. Order is preserved both within and across batches.
- **Token threshold T = 250 000** input tokens per batch (sum of all
  transcript file contents in the batch, before briefing overhead).
- **Transcript cap N = 6** per batch — secondary limit, even if T not
  reached. Caps attention dilution within shared context.
- **Algorithm:** scan files in chronological order. Pack into current batch
  while both (a) cumulative tokens ≤ T AND (b) transcript count < N. When
  either breaks, close current batch, start a new one with the next file.
  Under-filled batches are acceptable — chronological priority over packing
  density.
- **Oversize edge case:** single source > T → solo batch with that source
  alone. No splitting. Opus 1M context handles it.

### 3.0.2 Concurrency

- Max **3 parallel subagents** at any time.
- If batch count > 3, queue remaining FIFO.
- All subagents within a wave dispatched in a single tool-use message
  (multiple parallel `Task` blocks).

### 3.0.3 Subagent Invocation Contract

- Tool: `Task`, `subagent_type: general-purpose` (inherits Opus from
  orchestrator), **always `run_in_background: false`**. Never background a
  batch, and never poll for one.

  **This does not make batches sequential.** A wave still goes out as §3.0.2
  specifies — up to three `Task` blocks in one tool-use message, running
  concurrently — and the orchestrator waits for that wave and receives all of
  its manifests inline. Foreground is about where the result arrives, not about
  how many run at once; reading it as «one batch at a time» would triple a
  tick's wall-clock and strand a large backlog against the sandbox's time
  limit.

  This is load-bearing rather than stylistic, and the failure it prevents is
  not obvious. The manifest below is a **return value** — Step 3.4.5 and every
  orchestrator-side step consume it directly. A backgrounded batch returns
  through a notification instead, and when the watcher cannot attach the
  orchestrator is left holding no manifest and no way to ask for one. What it
  reaches for next is the runtime's own spilled tool-result file, and that read
  is outside the working tree: in an interactive session it raises a permission
  prompt, and in a scheduler tick there is nobody to answer it, so the tick
  blocks until its wall-clock expires. It never reaches failure-handling,
  because a blocked prompt is not an error — so the tick dies without shipping
  the failure note that would have made the death visible.

  **The runtime's own files are never an input.** Session transcripts,
  `tool-results/` spill files and anything else under the runtime's home are
  not part of this pipeline. A batch whose manifest did not arrive is a failed
  batch — treat it as one; never reconstruct it by reading what the runtime
  wrote about itself.
- Per-batch input passed in the Task prompt:
  - **Briefing (verbatim):** pre-scan results from Step 0 — PEOPLE.md,
    PROJECTS.md, HUB_INDEX.md, OPEN_THREADS, principle-candidates buffer
    state. Identical across all subagents in the same run.
  - **Retired identifiers, as prohibitions (verbatim):** the orchestrator
    turns every row of the registry's `## Retired Identifiers` and
    `## Trajectories` sections into one imperative line — never a table the
    subagent has to interpret. Retirement row → `never write project/{old}
    or [[{old}]]; that identifier is retired — write {successor} instead`.
    Trajectory row → `never put {id} in projects:; it is a trajectory — use
    tags: [trajectory/{id}]`. Nothing to emit when both sections are empty.
    Whole-identifier match only: a longer id that contains a retired one is
    a different identity, left alone.
  - **Routing rules (verbatim):** the `## Routing Rules` section of
    `_system/registries/FOLDERS.md`; the subagent files every knowledge note
    it creates by them.
  - **Batch transcripts:** ordered list of absolute paths to source files
    in `_sources/processed/...`, in chronological order.
  - **Pipeline spec:** instruction to execute Steps 3.1–3.7 for every
    transcript in the batch. The subagent reads the full transcript
    content from each path and processes them sequentially in chronological
    order, sharing context across them within the batch.
- Subagent return value (manifest):
  ```yaml
  batch_id: "{orchestrator-assigned}"
  transcripts_processed:        # one entry per transcript
    - path: "_sources/processed/..."
      records_created: ["_records/meetings/...", "_records/observations/..."]
      knowledge_notes_created: ["1_projects/..."]
      tasks_extracted: [...]
      events_extracted: [...]
      people_mentions: [...]    # raw, unresolved (orchestrator handles 3.8)
      project_mentions: [...]
      coverage_manifest: {...}  # per §3.7 — see below
      fixes_applied: [...]      # what self-review caught and fixed
      tradeoff_framing_records: # per §3.7.5 trade-off-observation path —
        - "_records/observations/..."  # record paths, NOT note paths
      processing_log: [...]     # key decisions for debug/audit visibility
  errors: [...]                 # empty if all transcripts processed cleanly
  ```

  `tradeoff_framing_records` is a list of `_records/observations/...`
  paths the subagent flagged for the §3.7.5 trade-off-observation path.
  The list is empty in the typical case. Subagents apply the strict
  three-condition check from §3.7.5 («explicit named alternatives» +
  «values-bearing reason» + «foreground, not parenthetical»). False
  negatives are recovered by `/minder:mem:lint --rescan-drift` later; false
  positives cost one Opus call and produce `no-match`. Bias toward
  conservative emission.
- Subagents write produced notes to disk directly (records, knowledge notes,
  hub updates inside their scope). Subagents **do NOT** write to global
  registries (PEOPLE.md, PROJECTS.md, TAGS.md, HUB_INDEX.md,
  PROCESSED.md, log_process.md, TASKS.md, CALENDAR.md) — those are
  orchestrator-only at Steps 3.8, 3.9, 4.x.

### 3.0.4 File Completeness Invariant (hard guarantee)

- Before dispatch: orchestrator computes set `S` = all source paths
  enumerated in §2.4 (after move to `_sources/processed/`).
- After all subagents return: union of `transcripts_processed[].path`
  across all manifests must equal `S` exactly.
- Mismatch (any file missing OR any duplicate processing) → **halt**.
  No partial writes to global registries, no batch artifacts written.
  Surface explicit error in report. Counter `sources` checked against
  `len(S)` at Step 5 Completion Gate.
- Any subagent returning a non-empty `errors` list → halt.

### 3.0.5 Equal-Attention Invariant

- Single subagent prompt template applies to every batch. No fast-path for
  short transcripts, no thorough-path for long ones.
- Within a batch, subagent is instructed to give every transcript identical
  processing depth (Steps 3.1–3.7 in full per transcript) and return
  outputs in the same order as input.

### Steps that follow per transcript inside the subagent

For each transcript in the batch (in chronological order, shared context):
execute Steps 3.1 → 3.6 → 3.7 (self-review) sequentially. After each
transcript, the subagent carries forward a brief running context (3–5
sentences: entities, decisions, open threads) to the next transcript in
the same batch — this is now natural shared-context continuation, not an
explicit handoff document.

### 3.1 Read Transcript

> **Reprocess-corpus branch:** the «file» here is an existing record or
> knowledge note. Read its frontmatter + body. Then resolve the
> underlying source via the note's `source:` frontmatter pointer and,
> if the target file exists on disk, also read it for richer matcher
> context. If `source:` is absent OR points at a non-existent path, log
> `reprocess-corpus: missing-source — {note_id}` to `log_process.md` and
> continue with the note's body alone. NEVER raise a CLARIFICATION for
> missing legacy sources — that state is expected by design.

Read full file content. The selected file (per §2.1 layout rule) is one of two formats — same contract regardless of source ID:

- **`transcript_with_summary.md`** (combined): raw transcript + LLM summary in a single file, separated by the literal token `<transcript_to_summary_delimiter>` on its own line.
  - Split the file on that token. Both halves MUST be used.
  - Part BEFORE the delimiter = raw transcript (the SOURCE OF TRUTH for classification, atomization, quotes).
  - Part AFTER the delimiter = LLM-generated summary (use as classification HINT only — never as authority, never quoted).
  - If the delimiter is missing in a file named `transcript_with_summary.md`, treat the entire file as raw transcript and surface a CLARIFICATION (`type: source-format-anomaly`) so the owner can investigate the producer.
- **`transcript.md`** (raw only): the entire file is raw transcript. No summary, no hint.

For `flat-md` sources the file IS the content — no delimiter expected, no summary contract.

### 3.2 LLM Noise Gate

> **Reprocess-corpus mode:** skip. Corpus content has already passed the
> noise gate during its original `/minder:mem:process` run.

Ask a single binary question about the transcript content:

> "Is this genuine speech content (a real conversation, reflection, or dictation)
> or is it noise (accidental recording, audio artifacts, unintelligible fragments,
> system test output)?"

- **Genuine** → proceed to Step 3.3
- **Noise** → skip this file. Log: `SKIPPED (noise): {path} — {reason}`
  Do NOT add to PROCESSED.md (so it can be re-evaluated if the noise gate
  was wrong — the file stays "new" until genuinely processed).
- **Inclusion-biased:** if in doubt, classify as genuine and process.

### 3.3 Semantic Context Loading

Before classification, load relevant context for THIS specific transcript:

1. **Resolve people** via the People Resolution Map (from Step 0.2):
   - RESOLVED / NEW → use the assigned ID directly
   - AMBIGUOUS → read full transcript context to attempt resolution.
     If still ambiguous: make best guess, log to CLARIFICATIONS.md

2. **Load matching hubs** (from Step 0.3 signals):
   - Read ONLY "Текущее понимание" section (includes subsections: Ключевые выводы,
     Открытые вопросы, Активные риски)
   - Do NOT load full hub files — prevents context window bloat

3. **Grep related notes** for context:
   - **Recent (last 2-3 weeks):** by matched people/projects/topics.
     Read titles and frontmatter only, not full content.
   - **Topic-deep (any age):** if Q10/Q12 will need to check existing knowledge
     on a specific topic (e.g., for hub threshold counting), grep for knowledge
     notes with matching `topic/` or `project/` tags across all time.
     Read frontmatter only — enough to count and detect evolution.
   - Purpose: detect evolution, avoid redundancy, enable accurate hub threshold checks

4. **Resolve projects** against the registry — **primary-topic semantic**.

   For every project candidate the transcript suggests, **open
   `1_projects/PROJECTS.md` and look the identifier up** — none of the three
   outcomes is «write it anyway». Active project → eligible for `projects:`.
   Trajectory, or consolidated / superseded → not eligible; route per the
   retirement prohibitions in the briefing (§3.0.3). Absent from the registry
   → do not invent a project id; carry the signal as `tags:` / `concepts:` /
   `[[wikilink]]` and let Step 3.8 surface it.

   Which identifiers may occupy the axis at all is the Identity Contract in
   `_system/docs/SYSTEM_CONFIG.md`; the judgment half — primary-topic test,
   cardinality, where a non-primary signal goes instead — is
   `5_meta/PROCESSING_PRINCIPLES.md` → «Project Tagging — Primary-Topic Only». Apply both; re-derive
   neither from memory.

5. **Leverage existing Minder Memory knowledge:**
   For each topic, consider:
   - Is this NEW information?
   - Is this CONFIRMATION of existing knowledge?
   - Is this CONTRADICTION of existing understanding?
   - Is this EVOLUTION of a previous position?

### 3.4 LLM Classification

Answer these 16 questions for each transcript, using the loaded context.
Be specific and cite evidence from the transcript.

**== SOURCE CLASSIFICATION ==**

1. SOURCE TYPE: What kind of source is this?
   Options: work-meeting | personal-reflection | therapy | idea-brainstorm | mixed
   Evidence: [quote from transcript that supports classification]

2. LANGUAGE: What is the primary language of the transcript?
   (Note content will be written in this language. Section headers follow the language.)

**== CONTENT ANALYSIS ==**

3. KEY TOPICS: List 2-5 main topics discussed.
   For each: [topic] — [one-sentence summary]

4. DECISIONS MADE: List any decisions (explicit OR implicit consensus).
   For each decision:
   a) What was decided
   b) What alternatives were considered (even if not explicitly stated — infer from context)
   c) Who made or influenced the decision
   d) Why this choice (reasoning, constraints)
   e) Scope: FINAL (committed) or TENTATIVE (still open to revision)
   f) Supersedes: does this override a previous decision? If yes, which one?
      Check loaded hubs for prior decisions on the same topic.

   Decision markers to scan for: «решили», «договорились», «будем делать», «выбрали»,
   «утвердили», «отложили», «пока так», «по итогу»
   Implicit consensus markers: repeated agreement, lack of objection to a proposal,
   "ну давай так и сделаем", default acceptance

5. ACTION ITEMS: List any tasks, to-dos, commitments.
   For each: [task] — [who is responsible] — [deadline if mentioned]
   Classify each as ACTION / WAITING / DELEGATE per the rules in SYSTEM_CONFIG.md
   (section "Task Format → Правила классификации"). This classification feeds
   TASKS.md aggregation in Step 4.1 and lets Waiting/Delegate items inherit the
   `@person-id` prefix in the aggregate file.

6. INSIGHTS: List any non-obvious realizations, connections, or understanding shifts.
   For each: [insight] — [what changed in understanding]

7. PEOPLE: List ALL people mentioned with their role/context.
   Scan the ENTIRE transcript for names, diminutives, and references.
   Mark as: [participant] (was in the meeting) or [mentioned] (talked about)
   For new people not in registry: [name] — [role] — [org] — [context]

**== STRUCTURAL DECISIONS ==**

8. SPLITTING: How many distinct knowledge streams exist in this transcript?
   A "knowledge stream" = self-contained topic that deserves its own note.
   Consider: Can this topic be understood WITHOUT the other topics in this transcript?
   - If yes → separate note
   - If no → part of the same note

   For each stream: [topic] — [type: decision/insight/reflection/idea/technical]

9. RECORD: What kind of record fits this transcript?
   Records are MANDATORY for every transcript-grounded source so that knowledge
   notes always anchor to a record-id (wikilink), never to a raw transcript path.

   - SOURCE TYPE = work-meeting → **meeting record** in `_records/meetings/`
     Filename: `YYYYMMDD-meeting-{main-participant}-{topic-slug}.md`
     Body: summary (2-3 sentences), key points (ALL significant — Principle 1),
     decisions, action items, participants, source link.

   - SOURCE TYPE ∈ {personal-reflection, idea-brainstorm, therapy} (solo speaker,
     no meeting context) → **observation record** in `_records/observations/`
     Filename: `YYYYMMDD-observation-{topic-slug}.md`
     Body: speaker, summary (2-3 sentences), key points, mood/context if salient,
     source link. NO decisions / action items sections (those live in knowledge
     notes that link back via `extracted_from:`).

   - SOURCE TYPE = mixed → split into the dominant kind by majority of content,
     or create both a meeting record AND an observation record if two distinct
     transcript segments warrant it. Document the choice in Q9 evidence.

   Output: proposed filename(s), kind, speaker (for observation), summary, key points.

10. KNOWLEDGE EXTRACTION: For each knowledge stream from Q8:
    - Should this become a standalone Knowledge Note?
    - Threshold: Does it have VALUE beyond the meeting context?
      (A status update = no. An architectural decision = yes. A career insight = yes.)
    - If yes: proposed filename, folder, types, domains
    - EXISTING KNOWLEDGE CHECK (use Step 3.3 topic-deep grep results):
      Does a note on this exact topic already exist?
      If yes: is this NEW, CONFIRMATION, CONTRADICTION, or EVOLUTION?

11. HUB CONTINUITY: Does this transcript continue/update any existing hub?
    Check loaded hubs. For each match:
    - Hub ID
    - What new information does this transcript add?
    - How does "Текущее понимание" need to change?
    - New entry for Хронологическая карта: [date] [note-ref] [type] [what happened]
    - New entry for Changelog: [date] [what shifted]

12. NEW HUB: Does any topic now reach the 3+ knowledge notes threshold?
    Count existing KNOWLEDGE notes touching this topic (use Step 3.3 topic-deep
    grep results + notes created earlier in this batch). If 3+ including
    this one → propose new hub.
    (Records do NOT count toward the threshold — only knowledge notes.)
    - Proposed hub ID: hub-{topic}
    - Initial "Текущее понимание" draft
    - Backfill хронологическая карта from existing notes

13. CROSS-DOMAIN: Is there anything here that changes understanding in ANOTHER domain?
    Threshold: ~30% confidence. If it MIGHT be relevant → capture the link.
    - [insight from domain A] → [relevance to domain B]
    - Proposed wikilink or hub update

14. CONTENT POTENTIAL: Assess each knowledge stream from Q8 for public sharing value.

    Three fields (all OPTIONAL — omit entirely if no public value):

    #### content_potential: high|medium

    `high` — at least ONE is true:
    - Author shares personal experience/story illustrating a professional principle
    - Specific technical insight, approach, or architectural decision
    - Opinion/position on a topic discussed in the industry (AI, fintech, management, etc.)
    - Career, leadership, or management reflection with concrete examples
    - Business or product idea with an original angle
    - Workflow, process, or tool usage pattern useful to others
    - Personal reflection or life insight with universal resonance

    `medium` — at least ONE is true:
    - Kernel of interesting thought, not yet fully developed
    - Topic is potentially public, but current context is too personal/company-specific — needs rework
    - Fragment that could become part of a larger post when combined with other notes

    #### content_type: expert|reflection|story|insight|observation

    Set when `content_potential` is set. Determines the NATURE of the note (single value):

    | Type | What it is | Example |
    |------|-----------|---------|
    | `expert` | Professional/technical knowledge, architectural decisions, domain expertise | "DBA alias vs merchant profiles" |
    | `reflection` | Personal introspection, psychology, self-analysis, therapy insights | "Валидация и отвержение комплиментов" |
    | `story` | Narrative arc — career journey, personal experience, travel, life event | "From Java Dev to TPM: 9-year journey" |
    | `insight` | Non-obvious connection, counter-intuitive observation, pattern recognition | "AI adoption в QA: творческое сопротивление — не страх замены" |
    | `observation` | Lightweight seed thought, casual noticing, not yet developed | "Music's role in creative thinking" |

    `content_type` is the dominant type of the NOTE, not the post. A therapy reflection
    that can be reframed as a management insight for LinkedIn is still `reflection` —
    the reframing is `/minder:mem:content`'s job when generating drafts.

    **Closed set — emit EXACTLY one of the five above** (`expert`, `reflection`,
    `story`, `insight`, `observation`). Never invent a finer-grained value
    (`technical`, `idea`, `decision`, `principle`, `framework`, `practice`,
    `product-insight`, `personal`, …). If a note feels like one of those, map it to
    the closest canonical type: technical/architectural → `expert`; a raw idea or
    a decision/principle/framework articulation → `insight`; a personal note →
    `reflection`. Downstream hygiene assumes this set is closed; a drift value
    silently falls out of content routing.

    #### content_angle: a YAML list of strings (single angle = 1-element list)

    Each angle = one sentence hook — the "why would someone read this?" framing.
    Always a list; never a bare string.

    **Single angle** (most notes) — still a list:
    ```yaml
    content_angle:
      - "Почему делегирование — это не про контроль, а про детский перфекционизм"
    ```

    **Multiple angles** (when a note can produce posts with different framings):
    ```yaml
    content_angle:
      - "Childhood perfectionism → adult control patterns: a therapy insight"
      - "Why delegation is hard for tech leads — it's not about trust"
    ```

    Multiple angles typically arise when a note sits at the intersection of domains
    (personal + professional, technical + management). Each angle becomes a distinct
    post candidate — `/minder:mem:content` drafts one conceptual post per genuinely distinct
    angle, not one per note.

    **Default: one angle (as a 1-element list).** Only add more when genuinely
    distinct framings exist. Don't force it — one good angle beats two weak ones.

    #### Bias and filtering

    **Bias: inclusion.** When in doubt, mark `medium`. Do NOT skip.
    Filtering is `/minder:mem:content`'s job, not this step's.
    False positives are cheap; false negatives lose content opportunities.

15. CONCEPTS: Extract every meaningful "thing-in-the-world" mentioned that
    warrants a node in the knowledge graph. Concepts span themes, tools,
    decision classes, ideas, events, organizations, skills, locations,
    emotions, goals, values, preferences, constraints, algorithms, facts,
    other. **People and projects are NOT concepts here** — they have
    first-class channels (`people:` / `projects:` frontmatter,
    `tier1_objects.{people,projects}` in manifest); do NOT duplicate.

    **Translation rule (HARD, non-negotiable).** Source language can be
    Russian, English, or mixed. Concept names emit in **English snake_case
    only** per `_system/registries/CONCEPT_NAMING.md`. When the source
    uses a non-English term, **translate semantically at extraction**:

    - «переезд офиса» → `office_move` ✓
    - «приоритизация очереди» → `queue_prioritization` ✓
    - «ежедневник» → `daily_planner` ✓
    - «делегирование как контроль» → `delegation_control_pattern` ✓

    NEVER transliterate (would split graph identity across languages):

    - «реструктуризация» → `restrukturizatsiya` ✗
    - «делегирование» → `delegirovanie` ✗

    **The translation contract is the only contract.** There is no
    mechanical transliteration-detector — the LLM (you) is always
    available in this pipeline and is the sole resolver. If you slip
    and emit a transliteration, it lands as a phantom graph node
    (`restrukturizatsiya` and the next run's `restrukturisatsia` are
    two distinct identifiers). The cost of one mistake is a split
    node forever; the cost of dropping an untranslatable term is one
    lost mention. Translate or drop — never transliterate.

    **Translation-impossible fallback (autonomous, no owner action).**
    If a term is genuinely untranslatable (cultural/legal/domain jargon
    with no clean English equivalent — `dacha`-class) → **drop the
    entry**, do not emit. Dropping loses one mention but keeps graph
    identity stable (transliterating across mentions would create
    multiple variants of the same node). When multiple plausible
    translations exist, pick the one most consistent with surrounding
    concepts in the same transcript (lexical-context heuristic). Never
    raise a CLARIFICATION; the model is the only resolver.

    **Normalisation (autonomous, run on every emitted name).** Apply
    `_system/scripts/_common.py::normalize_concept_name()` heuristic:
    diacritic-fold → lowercase → separator→`_` → collapse runs → trim
    `_` → drop if non-ASCII residue → drop if charset fails → drop if
    the result is a bare reserved type-word (rule 8) → truncate at
    last `_` boundary `≤ 64`. The function returns `None` when
    normalisation cannot produce a valid identifier; callers MUST
    treat `None` as «skip silently». **Type prefixes are NOT
    stripped** — the name is kept verbatim. A bare string cannot tell
    a redundant label (`skill_python`) from a compound where the type
    word is part of the name (`decision_making`, `skill_based`,
    `value_chain`), and a wrong strip corrupts identity. Rule 5 ("no
    type prefix in name") is YOUR job at this step — do not weld the
    type into the name. Type lives in metadata, not in name; a slipped
    weld is preserved, never amputated.

    **Selectivity (Rule 8).** Reject broad classifiers — if a name
    would match half the corpus (`work`, `general`, `meetings`), it's
    a domain or tag, not a concept. Reject sentence-fragments that
    only describe one specific moment (`q3_2026_team_offsite_notes`)
    — extract the load-bearing noun (`office_move`) instead.
    The selectivity test: would this name plausibly recur across
    multiple future notes that the owner would want to link?

    **For each emitted concept, capture metadata for the manifest:**

    | Field | Required | Notes |
    |---|---|---|
    | `name` | yes | Canonical snake_case identifier |
    | `type` | yes | One of (lowercase): `theme`, `tool`, `decision`, `idea`, `event`, `organization`, `skill`, `location`, `emotion`, `goal`, `value`, `preference`, `constraint`, `algorithm`, `fact`, `other`. **NOT** `person` / `project`. |
    | `subtype` | optional | Finer category within type (e.g. type=`tool`, subtype=`database`). Same snake_case format. |
    | `related_concepts` | optional | Other concepts mentioned alongside this one in the same transcript context. Same snake_case format on every entry. |
    | `previous_slugs` | optional | Past names this concept was known by — chain via this field on rename. Same snake_case format. |

    **Output for downstream steps:**

    - **Per record:** the canonical concept-name list will populate
      the record's `concepts:` frontmatter (Step 3.5 §A) and the
      manifest's `records.created[].concept_hints[]` (Step 4 batch
      assembly).
    - **Per knowledge note:** subset of the parent record's concepts
      that this specific knowledge stream covers — populates the
      note's `concepts:` frontmatter and the manifest's
      `knowledge_notes.created[].concept_hints[]`.
    - **Per hub touched:** union of `concepts:` from member knowledge
      notes — populates the manifest's `hubs.{updated|created}[].member_concepts[]`
      at emission time. Hub frontmatter does NOT carry `concepts:`
      (would invite drift between hub field and member-aggregate);
      the field is manifest-only.
    - **Batch level:** every distinct concept emitted across the run
      → one entry in `concepts.upserts[]` with `name` + `type` +
      optional `subtype` / `related_concepts` / `previous_slugs`.
      Deduplicated by `name` (case-folded snake_case is canonical).
      Two notes mentioning `org_structure` → ONE upsert entry; their
      consolidated `related_concepts` is the union.

    **Edge cases:**

    - **Acronyms / versions:** lowercase wins (`oauth`, not `o_auth`;
      `api_v2`, not `api_v_2`). Treat acronym as one segment.
    - **Subtype vs separate concept:** if the would-be subtype could
      stand on its own and be referenced by other notes (`vector_database`
      as its own concept), make it a separate concept with a
      `related_concepts` link instead of a subtype. Subtype is only
      for "this particular tool happens to be of subtype X."
    - **Compound names:** if parts mean meaningfully different things,
      split into multiple concepts. If the long form is a context-
      sentence dressed as an identifier, pick the load-bearing noun.

16. PRIVACY TRIO (origin / audience_tags / is_sensitive): Decide privacy
    fields for every entity emitted in this transcript pass — record(s),
    each knowledge note, hubs touched, person profiles created/updated,
    project profiles, tasks, events, ideas. The trio is **slot-only at
    this layer**: this skill emits values; downstream consumers (Minder
    backend, sync targets) apply policy.

    **HARD invariant — fail closed.** Defaults are chosen so that absence
    of inference yields owner-only access (`audience_tags: []`). The
    inclusion-bias from Principle 1 does NOT apply here — false-positive
    audience inference leaks content. When uncertain, leave `[]`.

    **`origin` (single value):**

    | Value | When |
    |---|---|
    | `personal` | SOURCE TYPE (Q1) ∈ {personal-reflection, idea-brainstorm, therapy}. Solo Plaud captures. Family / health / life-decision content. **Default when ambiguous.** |
    | `work` | SOURCE TYPE = work-meeting. Content explicitly about work projects, work team, work decisions. Mixed transcripts where the dominant content is work-context. |
    | `external` | Content extracted from external sources (clipped articles, third-party documents, AI-generated profile summaries). Rare in `/minder:mem:process` since `Skip Subdirs` typically excludes external reference. |

    Mixed transcripts: pick the dominant context for the record's
    origin; per-knowledge-note `origin` is set independently per the
    note's content (a personal-reflection knowledge note extracted
    from a work-meeting record can carry `origin: personal`).

    **`audience_tags` (list, conservative):**

    Default `[]` (owner-only) unless content shows **clear, explicit**
    sharing intent. Set tags only when:

    | Tag | Trigger |
    |---|---|
    | `[work]` | Owner explicitly says they will share with the work team (status update for standup, decision draft to communicate, doc draft for the team), OR content_potential note where content_type aligns with internal work audience. |
    | `[professional-network]` | Content has clear LinkedIn-grade voice (career / leadership / management insight ready for public-professional audience). content_potential=high notes with content_type ∈ {expert, insight} typically land here. |
    | `[friends]` | Content explicitly framed for friend circle (stoic reflection meant to share, friend-circle decision). |
    | `[family]` | Content explicitly framed for family (family decision, vacation plan). |
    | `[world]` | Content explicitly meant for public broadcast (Twitter / public blog draft). |

    **content_potential mapping (Q14 → Q16):**

    - `content_potential: high` + `content_type: expert | insight`
      → `[professional-network]` is a reasonable default
    - `content_potential: high` + `content_type: reflection | story`
      → `[professional-network]` if owner has shared similar before
        (visible in `_system/POSTS.md` history); else `[]` — let
        `/minder:mem:content` decide at draft time
    - `content_potential: medium` or `observation` → `[]` — still
      seed-stage; widening is owner's call later
    - No content_potential → `[]`

    **Multiple tags allowed** (`[work, friends]`) when the audience
    genuinely overlaps. Flat union, no hierarchy.

    **Unknown / extension tags (autonomous resolution).** If you'd
    want to set a tag NOT in the canonical 5 AND NOT in
    `_system/registries/AUDIENCES.md` Extensions table → silently drop
    that tag and emit `audience_tags: []` for the entity. The
    fail-closed default is the right outcome on any uncertainty —
    false-positive sharing leaks; false-negative just keeps content
    owner-only. Never coin a new tag, never raise CLARIFICATION; the
    AUDIENCES Extensions table is owner-curated outside the
    `/minder:mem:process` pipeline. **Heuristic mapping before drop:** if the
    intended audience semantically maps to a canonical (e.g. "team" →
    `work`, "linkedin" → `professional-network`, "tweet" → `world`),
    use the canonical. Only drop when no canonical applies.

    **`is_sensitive` (bool):**

    Set `true` if content matches ANY:

    - NDA / confidential mention («под NDA», «не для разглашения»,
      «конфиденциально», "off the record")
    - Salary / compensation / equity / specific financial detail
      (specific amounts, comp packages, equity grants, debt detail)
    - Health / medical detail (diagnoses, conditions, medications,
      mental-health specifics — beyond "feeling tired")
    - Family conflict, intimate relationship detail (specific
      grievances, emotional disclosures involving named family /
      partners)
    - Reputational risk content (specific allegations about named
      people, legal-risk topics)

    `false` otherwise. **`is_sensitive: true` does NOT narrow
    `audience_tags`** — they're orthogonal. A work memo can be
    `audience_tags=[work], is_sensitive=true` (team can see it; share
    outside requires friction). Health note for spouse:
    `audience_tags=[family], is_sensitive=true`.

    **Per-entity application table:**

    | Entity | origin | audience_tags | is_sensitive |
    |---|---|---|---|
    | Record (meeting / observation) | from SOURCE TYPE | `[]` unless explicit sharing intent | per content scan |
    | Knowledge note | independent of parent record (a personal-reflection note from a work-meeting record can be `personal`) | per content_potential mapping above; default `[]` | per content scan |
    | Hub touched | inherit dominant member-note `origin` | `[]` (owner curates by hand) | `false` unless any member note is sensitive |
    | Person profile (new / updated) | inherit from creating record (work-meeting → `work`; personal-reflection → `personal`) | `[]` always | `false` unless owner-curated content is sensitive |
    | Project profile (new) | from project's actual context — work-employment project → `work`, personal side-project → `personal`, external/clipped → `external` (NOT hardcoded `work`) | `[]` | `false` |
    | Task | inherit from parent note | inherit from parent note | inherit from parent note |
    | Event | inherit from parent note | inherit from parent note | inherit from parent note |
    | Idea note | per content scan | `[]` (ideas are seed-stage) | per content scan |

### 3.4.5 Concept Matcher Subagent (post-Q15 canonicalisation)

After the LLM classifier emits Q15 raw concept candidates and Q9
domain candidates, the orchestrator (NOT the per-file subagent — see
§A below) consolidates them across all files in the batch and runs
ONE Sonnet matcher subagent per source/transcript-cluster against
the loaded concept registry. This step exists to (a) reuse existing
canonical names verbatim instead of coining near-duplicates, (b)
type-tag genuinely-new concepts via the Minder ConceptType emit set,
and (c) close out unmatched domain values via the
cascade in `DOMAINS.md` → «On violation — autonomous resolution».

**Why a subagent rather than expanding the classification prompt.**
The classifier subagent already runs against a per-file context
budget. Loading the full `CONCEPTS.md` registry (which can grow into
thousands of rows) into the per-file prompt scales badly. A separate
Sonnet matcher takes the cheap-context model, sees the full
vocabulary, and emits canonical decisions in one shot — Opus
orchestrator stays small, classification subagents stay focused.

#### A) Inputs collected by the orchestrator

For each transcript / source unit processed in this batch, collect:

- The Q15 raw concept candidates (list of strings, possibly dirty —
  not yet normalised).
- The Q9 domain candidates that did NOT clear `normalize_domain` ∪
  ALLOWED_DOMAINS ∪ active extensions (the residual that the
  deterministic substrate cannot resolve).
- A short source excerpt (the transcript title + 1–2 representative
  paragraphs) for disambiguation.

Group these per source/transcript so each subagent invocation
operates on one logical unit at a time. Multiple transcripts in the
same batch fan out as parallel subagent calls.

#### B) Subagent invocation

Spawn via the harness `Agent` tool:

```
Agent(
  description: "Concept matcher for transcript {source-id}",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: <see below>
)
```

Prompt template (skeleton — orchestrator fills in placeholders):

```
You are the Minder Memory concept matcher. Read the full registry below; then
canonicalise the candidates from the transcript at the bottom.

REGISTRY (authoritative — prefer existing names verbatim):
<contents of _system/registries/CONCEPTS.md>

CONCEPT TYPES (assignable values — 16):
<from `_system/registries/CONCEPT_TYPES.md`: the «Mirror vs emit gate»
section + the 16 emit codes with descriptions; explicitly forbid
`person` and `project`>

DOMAINS (canonical 13 + active extensions):
<contents of _system/registries/DOMAINS.md canonical block + Extensions table>

TRANSCRIPT EXCERPT:
<source title + representative paragraphs>

Q15 CANDIDATES (raw, possibly dirty):
<list>

UNMATCHED DOMAIN VALUES (residual after deterministic substrate):
<list, may be empty>

OUTPUT — strict JSON, no prose:
{
  "concepts": ["canonical_name_a", "canonical_name_b", ...],
  "new_concepts": [
    {"name": "...", "type": "<one of the 16>",
     "subtype": "<optional, free-form>",
     "justification": "<one short sentence>"}
  ],
  "domain_resolutions": [
    {"raw": "...", "action": "keep" | "remap" | "drop" | "clarify",
     "target": "<canonical or extension>"}
  ],
  "needs_decision_check": [
    {"summary": "<one line>", "rationale": "<one sentence>"}
  ]
}

RULES:
- Prefer existing canonical names — coin a new concept ONLY when no
  registry entry fits the meaning.
- For new concepts, assign type from the 16 emit values. NEVER use
  `person` or `project` (those are first-class entities).
- For unmatched domains, choose `remap` if a canonical clearly fits,
  `drop` if the value is genuinely trivial, `keep` only if owner
  has plausibly extended the registry but the extension hasn't
  landed yet (then orchestrator surfaces a `domain-resolution`
  CLARIFICATION). Use `clarify` to escalate borderline cases.
- Use `needs_decision_check` ONLY for genuinely values-laden cases
  (extension would conflict with a canonical principle, or the
  concept reframes a previously-decided trade-off). Default empty.
```

#### C) Apply verdicts

Parse the JSON response, then:

1. Pass each `concepts[]` and `new_concepts[].name` through
   `_system/scripts/_common.py::normalize_concept_name` — drop on
   `None` (the gate is defence-in-depth; subagent is supposed to
   emit normalised names already).
2. Pass each `new_concepts[].type` through `validate_concept_type` —
   drop the entry on miss (autonomous resolution: subagent can re-
   coin under a fallback type on next batch).
3. Pass each `domain_resolutions[]`:
   - `action: keep` → orchestrator surfaces a `domain-resolution`
     CLARIFICATION with conservative default (drop the value);
     never silently expands the canonical/extension set.
   - `action: remap` + `target` in canonical/extension → record the
     replacement; orchestrator rewrites the affected note's
     `domains:` array on frontmatter write (Step 3.5).
   - `action: drop` → silently drop the value at frontmatter write.
   - `action: clarify` → `domain-resolution` CLARIFICATION,
     conservative default same as `keep`.
4. Apply concept verdicts to per-note frontmatter via
   `write_frontmatter` at Step 3.5 §A — the canonicalised
   `concepts:` array is what lands on the record / knowledge-note.

#### D) Decision-check escape hatch

If the subagent populated `needs_decision_check[]`, the orchestrator
makes ONE batched call to `/minder:mem:check-decision` with the entire
list — never one per item. The verdict comes back per-item;
orchestrator applies each silently to the per-note frontmatter
(NOT a CLARIFICATION). This is the rare-path resolution channel for
values-laden concept choices and is expected to be empty in
typical batches.

#### E) Residual domain CLARIFICATIONs

Domain values that exhausted the cascade
(`normalize_domain` → whitelist → LLM remap → LLM trivial-vs-
material) without resolving land as `domain-resolution`
CLARIFICATIONs in `_system/state/CLARIFICATIONS.md` per the
canonical type registered in `SYSTEM_CONFIG.md`. Conservative
default: drop the value, leave the note's `domains:` as the
remaining valid entries (possibly `[]`). Owner resolves the
CLARIFICATION by editing `DOMAINS.md` Extensions table or by
confirming the drop.

#### F) Failure mode

If the subagent fails to return parseable JSON, retry once. Second
failure: fall through to the deterministic substrate as if Step
3.4.5 did not run — Q15 raw output passes through `normalize_concept_list`
unchanged at frontmatter write, unmatched domains drop silently per
the deterministic substrate, and a `concept-matcher-failed` log entry is
emitted to `log_process.md` for the batch. No CLARIFICATION; the
SKILL contract is non-blocking.

---

### 3.5 Create Outputs

> **Reprocess-corpus branch — UPDATE, not CREATE.** Skip subsections A
> (records), B (knowledge), C (hubs update), D (hubs create), E (cross-
> domain) below. Instead, for each note in the batch, perform a
> minimal frontmatter mutation:
>
> 1. Read the note's existing frontmatter via
>    `_common.py::read_frontmatter`.
> 2. Replace the `concepts:` array verbatim with the matcher output
>    (each entry already passed through `normalize_concept_name`).
> 3. Apply `domain_resolutions[]` against the note's `domains:` list:
>    `action: drop` → remove the value; `action: remap` + valid
>    `target` → replace; other actions → log
>    `domain-resolution-unknown-action`, leave the value.
> 4. Preserve every other frontmatter key verbatim. NEVER touch the
>    body. NEVER mutate Evidence Trail. NEVER create new files. NEVER
>    update hubs (corpus already drove hub creation in original run).
> 5. **Drift guard:** if the symmetric difference between prior
>    `concepts:` set and new matcher set exceeds 50 % of the union,
>    apply the new set AND surface a CLARIFICATION
>    (`type: concept-drift-on-reprocess`) with note path, prior set,
>    new set. The matcher run is canonical (it sees current registry);
>    the CLARIFICATION exists for owner audit, not gating.
> 6. Write back via `write_frontmatter`. Append the note to the in-
>    memory accumulator's `knowledge_notes.updated[]` or
>    `records.updated[]` (per `layer:`).

Based on the 16-question classification, create outputs. Fully automatic, no confirmation needed.

#### A) Records → RECORD in `_records/{kind}/`

Create exactly one record per transcript. Two kinds:

##### A1) Work meetings → `_records/meetings/`

Filename: `YYYYMMDD-meeting-{main-participant}-{topic-slug}.md`
Template: `5_meta/templates/record-template.md`

Frontmatter: `layer: record`, `kind: meeting` (omit `kind` for backward compat —
absence implies meeting; new records SHOULD include it explicitly).

**Concept + privacy fields (mandatory on every new record).** Add to
frontmatter from Q15 / Q16 outputs:

- `concepts:` — list of canonical concept-name strings mentioned in
  this transcript per Q15. Empty list `[]` allowed when no concept
  cleared the selectivity bar (Rule 8). All entries snake_case ASCII
  per `_system/registries/CONCEPT_NAMING.md`. People and projects do
  NOT go here.
- `origin:` — `work` (default for meeting records, consistent with
  SOURCE TYPE = work-meeting). Override only when Q16 inferred
  otherwise.
- `audience_tags:` — `[]` by default (owner-only). Set canonical tag
  ONLY on explicit sharing intent per Q16.
- `is_sensitive:` — boolean per Q16 sensitivity scan.

Record contains:
- Summary (2-3 sentences)
- Ключевые пункты (bullets — ALL significant points, not just "important" ones.
  Principle 1: Capture First. Even a one-line mention of a client goes in.)
- Решения (with rationale — from Q4 enhanced format)
- Action Items (with `- [ ]`, person link `[[person-id]]`, `^task-{slug}`)
- Упоминания людей (with context: role in this meeting, participant vs mentioned)
- `## Source` section with relative path to raw transcript

NO `<details>` blocks. NO raw transcript duplication. The `## Source` section
links to `_sources/processed/` for full-text access.

##### A2) Solo transcripts → `_records/observations/`

Use for personal-reflection / idea-brainstorm / therapy / any single-speaker
Plaud capture where there is no meeting to log. The observation record is the
canonical anchor for any knowledge notes extracted from this transcript — it
is what their `extracted_from:` and `## Evidence Trail` wikilink points to.

Filename: `YYYYMMDD-observation-{topic-slug}.md`
Template: `5_meta/templates/observation-record-template.md`

Frontmatter:
```yaml
---
id: YYYYMMDD-observation-{topic-slug}
title: "Наблюдение: {topic on transcript language}"
created: YYYY-MM-DD
source: _sources/processed/{source}/{timestamp}/transcript_with_summary.md
recorded_at: {ISO timestamp from transcript folder name, when known}

layer: record
kind: observation
speaker: {person-id of the owner from SOUL.md Identity; "unknown" if ambiguous}
people:
  - {anyone mentioned by name}
projects:
  - {primary-topic project only — resolved against the registry per §3.3 step 4}
concepts:
  - {snake_case concept name from Q15 — translated, normalised, selective}
origin: {personal | work | external — from Q16; default personal for solo capture}
audience_tags: []
is_sensitive: {true | false — from Q16 sensitivity scan; therapy / health / family content typically true}
tags:
  - record/observation
  - person/{speaker}
  - topic/{key-topic}
---
```

Body:
- `## Summary` — 2-3 sentences capturing what the recording was about
- `## Ключевые пункты` — bullets covering ALL significant points (same Principle 1)
- `## Контекст / настроение` — optional: where/when/mood if salient (e.g., «в машине после встречи с Димой», «после терапии»)
- `## Упоминания людей` — only if names came up (otherwise omit)
- `## Source` — transcript path, recorded timestamp

NO `## Решения` / `## Action Items` sections. Decisions and tasks belong in
knowledge notes, where they earn their own structure and link back via
`extracted_from: {observation-record-id}`.

##### Routing summary

| SOURCE TYPE (Q1)                                | Record kind | Folder                  |
|-------------------------------------------------|-------------|-------------------------|
| work-meeting                                    | meeting     | `_records/meetings/`    |
| personal-reflection / idea-brainstorm / therapy | observation | `_records/observations/`|
| mixed                                           | both kinds  | split per dominant segment |

#### B) Knowledge streams → KNOWLEDGE NOTE in PARA folders

For each knowledge stream identified in Q8/Q10:

Filename mapping by primary type:
- decision → `YYYYMMDD-decision-{topic}.md`
- insight → `YYYYMMDD-insight-{topic}.md`
- reflection → `YYYYMMDD-reflection-{topic}.md`
- idea → `YYYYMMDD-idea-{topic}.md`
- technical → `YYYYMMDD-technical-{topic}.md`

Folder: resolve by the routing rules in the briefing
(`_system/registries/FOLDERS.md → ## Routing Rules`).
Template: `5_meta/templates/note-template.md`

Frontmatter MUST include `layer: knowledge`.
If extracted from a record: add `extracted_from: {record-id}` to frontmatter.
`contains:` block is OPTIONAL — include only if note has tasks or ideas.

**Concept + privacy fields (mandatory on every new knowledge note).**

- `concepts:` — list of canonical concept-name strings this knowledge
  note covers. Subset of the parent record's `concepts:` list, narrowed
  to what *this specific knowledge stream* is about (per Q15 →
  per-knowledge-note allocation). Each entry snake_case ASCII, English
  only, normalised per CONCEPT_NAMING. Empty list `[]` allowed when no
  concept clears Rule 8 selectivity. People / projects do NOT go here.
- `origin:` — set independently of the parent record. A
  personal-reflection knowledge note extracted from a work-meeting
  record can be `origin: personal` if the content is genuinely
  personal-context. Default: inherit parent record's `origin`.
- `audience_tags:` — `[]` by default. Set per Q16 mapping including
  the content_potential → audience-tag rule (high+expert/insight →
  `[professional-network]`; high+reflection/story → conditional;
  medium / observation → `[]`).
- `is_sensitive:` — boolean per Q16 sensitivity scan applied to this
  note's specific content (a knowledge note can be more or less
  sensitive than its parent record).

**`description:` field — mandatory for new knowledge notes.** One-line
summary (≤100 chars) of what the note is about. Consumed by
`_system/scripts/render_index.py` (invoked from `/minder:mem:maintain`
Step 7.6, `/minder:mem:bootstrap` Step 5.5, and `regen_all.py`) to render the
INDEX.md catalog. Distinct from `title:`:
- `title:` names the note («Стратегический разбор встречи с Василием»)
- `description:` describes its content («Решение перейти к ежемесячным
  планам, а не квартальным; reasoning по 1-1 cadence»)

If the LLM cannot draft a meaningful description in one short line, it
SHOULD still write a fallback derived from `## Ключевая мысль` truncated
to 100 chars rather than omitting the field. INDEX.md fallback chain
(description → title → first prose line → `_(no description)_`) tolerates
omission, but legacy notes already have no `description:` and the goal of
this field is to phase that out for new content.

If Q14 determined content_potential for this knowledge stream:
  - Add `content_potential: high` or `content_potential: medium` to frontmatter (after `priority:`)
  - Add `content_type: {type}` — one of: expert, reflection, story, insight, observation
  - Add `content_angle:` — ALWAYS a YAML list (single angle = a 1-element list)
  - All three fields are OPTIONAL — omit entirely if Q14 found no public value

Decision notes:
- Body includes: what was decided, alternatives considered, reasoning, who decided, scope
- If superseding a previous decision: add `supersedes: {previous-note-id}` to frontmatter
- The superseded note is NOT modified — both versions persist (Principle 5: Evolution Tracking)

#### Idea Notes — Living Document Pattern

When a knowledge stream's primary type is `idea`:

1. **SEARCH** existing ideas before creating a new file:
   - Grep the frontmatter of knowledge notes whose `types:` contains `idea`, across
     `1_projects/`, `2_areas/` and `3_resources/` — the routing rules file an idea
     by its project or by its nature, so an earlier version can sit in any of them
   - Match signals (all contribute to confidence):
     a) Tag overlap: compare `topic/*` and `project/*` tags (weight: 40%)
     b) Title/keyword overlap: extract 2-4 key words from new idea title,
        compare against existing titles and aliases (weight: 35%)
     c) Folder match: the candidate's routed folder equals the new idea's (weight: 25%).
        A candidate's routed folder is its project's folder when its own
        `projects:` resolves to one under the routing rules, otherwise the folder
        it sits in — existing notes are never moved, so where a file sits is not
        where the rules would file it today

2. **Decision thresholds:**
   - **≥ 80% confidence — MATCH:** Update the existing idea note:
     - READ existing note
     - APPEND section: `## Update YYYY-MM-DD` with: source link, new context, what changed/evolved
     - Update `modified:` date in frontmatter
     - Increment `mentions:` count (add field if missing, default to 1 for existing notes)
     - Add additional source to `## Source` section
     - Do NOT create a new file
   - **50-79% confidence — AMBIGUOUS:** Create new note (safe default).
     Add `mentions: 1`. Log to CLARIFICATIONS.md:
     "New idea [{title}] may be related to existing [[{existing-id}]]. Consider merging."
   - **< 50% confidence — NO MATCH:** Create new idea note as before.
     Add `mentions: 1` to frontmatter.

3. **Edge cases:**
   - Multiple matches ≥ 80%: pick highest confidence, log runner-ups to CLARIFICATIONS
   - Match whose routed folders differ (e.g. business↔products, a project folder↔`3_resources/ideas/`): treat as AMBIGUOUS regardless of score

Body structure for knowledge notes — the frontmatter fence (`---`) closes FIRST,
then the body headings follow. Skeleton:

```markdown
---
{frontmatter fields}
---

## Контекст
## Ключевая мысль
## Применение / Следствие
## Связи
## Evidence Trail
## Source
```

**Structural invariant (hard).** Every `## ` section is BODY, written AFTER the
closing `---`. A `## ` heading placed before the closing fence (the common failure
is `## Evidence Trail` and its `- **date** …` bullet) is captured into the YAML
block, breaks `yaml.safe_load`, and makes the note unparseable to every frontmatter
consumer. Step 3.6 enforces this deterministically.

Section meanings:
- ## Контекст — where/when this came up
- ## Ключевая мысль — the core insight/decision/idea (with `^insight-{slug}` anchor if needed)
- ## Применение / Следствие — so what? how does this change things?
- ## Связи — `[[wikilinks]]` to related notes, hubs, people
- ## Evidence Trail — append-only audit trail of knowledge (see below)
- ## Source — link to raw transcript

#### Evidence Trail (mandatory for new knowledge notes)

Every new knowledge note (`layer: knowledge`, any type: decision / insight / reflection /
idea / technical) MUST include a `## Evidence Trail` section placed **before** `## Source`.
Records (`layer: record`) and people profiles do NOT get Evidence Trail.

Format — the closing `---` fence sits ABOVE this; Evidence Trail is a BODY section,
never inside the frontmatter:

```markdown
---
{last frontmatter field}
---

… other body sections …

## Evidence Trail

- **YYYY-MM-DD** | [[{source-record-or-note-id}]] — {≤1-2 sentences: what was extracted / confirmed / contradicted / raised}
```

Rules:
1. **Initial entry (N ≥ 1)** on creation:
   - Typically 1 entry — the source record/transcript this note was extracted from.
   - 2+ entries when the note has multiple origins (e.g., `extracted_from:` + explicit `related_to:` references that point at other source records in the same batch).
2. **Ordering:** newest-first. New entries prepended at the top of the list.
3. **Append-only:** never delete or rewrite entries. Corrections land as new entries noting the previous one was inaccurate.
4. **Matching is limited to `type: idea` Living Document pattern.** For other types, a new transcript that touches the same topic produces a new note (linked via `supersedes:` / `related_to:`) with its own initial Evidence Trail — NOT an append to the existing note's Trail. Rich matching for decision / insight / reflection / technical is `/minder:mem:lint` territory.
5. **Legacy notes without Evidence Trail are valid.** Never backfill existing notes via `/minder:mem:process` — that is `/minder:mem:lint` territory through CLARIFICATIONS suggestions.
6. **Multiple `## Evidence Trail` sections in one file** (anomaly, e.g., human edit): append to the first section encountered. Do NOT merge or delete the others. Raise an item in `_system/state/CLARIFICATIONS.md` `## Open Items` with type `evidence-trail-anomaly` (and this increments `clarifications_raised`).

#### Idea Living Document — Evidence Trail append + dedup

Extension of the Living Document pattern above (≥ 80% match branch):

- After reading the existing idea note and before writing, **prepend** a new entry to its `## Evidence Trail` section:
  `- **{today}** | [[{new-source-id}]] — {1-2 sentence summary of what this transcript adds}`
- **Dedup by (date + source-id):** if the existing Trail already contains an entry with the same date AND same `[[source-id]]`, **skip the prepend** (do NOT create a duplicate). This makes `--reprocess` idempotent and protects against re-run dirt.
- All other Living Document side effects (Update section, `modified:`, `mentions:`, additional Source link) remain as before.

#### `--reprocess` semantics for Evidence Trail

- **Decision / insight / reflection / technical / initial idea:** the note is fully rewritten by the reprocess run → the Evidence Trail is **reset** → write exactly one fresh initial entry with the reprocess date and the source link. Prior Trail history is discarded (it reflected a classification we are deliberately revising).
- **Idea via Living Document update during `--reprocess`:** apply the same (date + source-id) dedup described above. If the source is already present in the Trail → skip the prepend. This makes `--reprocess` idempotent at the Trail level.
- **Legacy notes without Evidence Trail** that the skill did NOT create: untouched. Backfill is `/minder:mem:lint` territory.

For personal content (reflections, therapy, ideas):
- Write in the language of the original transcript
- Preserve texture: direct quotes with `> "цитата"`, emotional context, narrative arc
- No record created — only knowledge notes

Primary note: When N knowledge notes come from one transcript, all reference
the source via `source:` in frontmatter. The primary note (closest to the main
topic) is first. Others include `related_to: {primary-note-id}` in frontmatter
(analogous to `extracted_from` and `supersedes` — relationship metadata belongs
in frontmatter, not content).

#### C) Hub updates → UPDATE existing hub in `5_meta/mocs/`

Process is a per-BATCH actor with a single-batch view; a hub is a cross-batch
synthesis (Layer 3). So a hub UPDATE here is **additive and non-destructive** —
it records what THIS batch contributed, never overwrites the accumulated synthesis.

For each matching hub (from Q11):
1. Read current hub file
2. **Integrate into "Текущее понимание" — non-destructively.** Weave this batch's
   new understanding into the existing text, PRESERVING prior synthesis. Never
   full-rewrite the section: a single-batch view rewriting the six-month synthesis
   overwrites accumulated cross-batch understanding with a keyhole view (a
   non-idempotent destruction). When new info genuinely supersedes prior text, add
   it as an evolution and record the shift in the Changelog (step 5) — do not
   silently discard the prior state. A true from-scratch re-synthesis (reading the
   hub's full membership) is a periodic action surfaced by `/minder:mem:lint` D.4
   (`hub-stale-vs-material` — the synthesis layer is never auto-rewritten), not a
   per-batch overwrite. Process must not bypass that gate with a destructive rewrite.
3. ADD row to "Хронологическая карта" — date, `[[note-ref|title]]`, type, what
   happened — **only when the hub's frontmatter `chronological_map_mode` is
   `curated` or absent.** A hub declaring `chronological_map_mode: derived`
   renders that section inside an `<!-- AUTO-GENERATED by render_hub_maps.py -->`
   managed zone from the notes whose `projects:` carry the hub's id: a hand-added
   row there is discarded by the next render, so do not write one. The note this
   batch created is what feeds it — nothing further is needed.
4. ADD entries to "Связанные знания" — decisions, insights, cross-domain links
5. ADD entry to "Changelog" (newest first) — date + what shifted in understanding
6. Update `modified` date in frontmatter
7. Update `people`, `projects` lists if new entries

**Hub privacy + member_concepts on update (autonomous, owner edits
preserved via explicit marker).** Hub frontmatter does NOT gain a
`concepts:` field — `member_concepts[]` lives only in the manifest,
derived at emission time (Step 4.7). Privacy trio on hub frontmatter
(`origin` / `audience_tags` / `is_sensitive`) is derived by the
deterministic helper `_system/scripts/_common.py::recompute_hub_trio()`.
Derivation rules:

- `origin` ← dominant `origin` across member knowledge notes; tie →
  `personal` (conservative default).
- `audience_tags` ← intersection of member-note `audience_tags[]`
  (only audiences ALL members agree on widen the hub; default `[]`).
  Intersection, not union — fail-closed across members.
- `is_sensitive` ← `true` if ANY member is sensitive, else `false`.
  Sensitivity is contagious upward.

**Owner-vs-engine ownership contract.** Hub frontmatter carries an
`_engine_derived: [field, ...]` list that names the trio fields the
engine currently owns:

- Field NOT in frontmatter → engine derives, writes value, ADDS field
  name to `_engine_derived`. (Fresh hub: all three engine-owned;
  membership changes flow through automatically on every touch.)
- Field IN frontmatter AND name IN `_engine_derived` → engine
  RE-DERIVES on every touch. New members shift dominant origin →
  hub follows; owner doesn't have to babysit.
- Field IN frontmatter AND name NOT IN `_engine_derived` → owner
  edit. Engine NEVER touches.

**To take over a field as owner:** remove the field name from
`_engine_derived`. The current value stays as the owner's authoritative
choice. To re-engage the engine on that field: add the name back to
`_engine_derived` (or just delete the field — engine re-derives + re-marks
on next run).

**Backward compatibility.** Hubs created before the marker existed
have trio fields without `_engine_derived`. The engine treats those
as owner-set (preserves them) — matching the legacy "set once, owner
takes over" semantics. New derivations on those hubs grow the marker
incrementally; over time the hub transitions to the explicit model.

The manifest emission step (4.7) reads the post-recompute frontmatter
values verbatim. No CLARIFICATIONs at any point.

#### D) New hub creation → CREATE in `5_meta/mocs/`

When a topic reaches 3+ KNOWLEDGE notes (Q12):
1. Use template: `5_meta/templates/hub-template.md`
2. Fill "Текущее понимание" — synthesize from all related notes
3. BACKFILL "Хронологическая карта" — rows for ALL existing related notes. A new
   hub is `curated` by default (the field is absent), so the map is hand-written
   here; `chronological_map_mode: derived` is an owner opt-in, never set by this
   step
4. Fill "Связанные знания" — decisions, insights, questions
5. Fill "Changelog" — initial entry
6. Add to `_system/views/HUB_INDEX.md`

Hub ID format: `hub-{topic-slug}` (e.g., `hub-api-platform`, `hub-delegation-pattern`)

**New hub privacy trio on creation.** Same helper
(`_common.py::recompute_hub_trio`), same rules: dominant origin,
audience intersection, sensitivity contagion. On a fresh hub all
three fields are missing → derivation fills all three. Subsequent
touches preserve any owner edits per the same owner-edit
preservation contract.

#### E) Cross-domain insights

If significant enough (from Q13):
- Create standalone knowledge note in the TARGET domain
- Link back to source note and source domain hub
- Update target domain hub if it exists

If minor:
- Add `[[wikilink]]` in source note's "Связи" section
- Mention in hub's "Связанные знания → Cross-Domain" section

### 3.6 Structural Verification

After creating EACH file with frontmatter + body that the subagent writes (record, knowledge note, or hub), verify:

- [ ] **Frontmatter fence integrity (deterministic — the load-bearing check).** The frontmatter `---` fence closes BEFORE any `## ` body heading. Verify with `_common.frontmatter_closed_before_body(path)` returning True AND `_common.read_frontmatter(path)` returning non-None. On failure a body heading (typically `## Evidence Trail`) was written before the closing `---` and captured into the YAML — re-emit the note moving the closing `---` to sit immediately after the last frontmatter field and before the first `## ` heading, then re-verify. Deterministic autofix, never a CLARIFICATION. This is the load-bearing check: a valid-YAML self-assertion cannot catch a comment-tolerated misplaced fence, but the helper's column-0 line invariant can. Applies to every note the run writes — both freshly created and updated in place (e.g. the idea Living-Document append).
- [ ] Frontmatter has all required fields present
- [ ] `layer:` field is correct — `record` for records, `knowledge` for knowledge notes
- [ ] People IDs in `people:` exist in PEOPLE.md OR will be created in Step 3.8
- [ ] Every id in `projects:` is eligible for the axis per the Identity Contract in `_system/docs/SYSTEM_CONFIG.md` — looked up in `1_projects/PROJECTS.md`, not recalled; a retired or reclassified id is a fail, not a warning. Cardinality per `5_meta/PROCESSING_PRINCIPLES.md` → «Project Tagging — Primary-Topic Only».
- [ ] Tags follow conventions from TAGS.md (format: `type/xxx`, `domain/xxx`, etc.)
- [ ] A note this run created sits in the folder the routing rules (`_system/registries/FOLDERS.md → ## Routing Rules`) resolve for it; a note updated in place stays where it is
- [ ] `source:` points to a real file path in `_sources/processed/`
- [ ] `extracted_from:` (if present) references an existing or just-created record ID
- [ ] `supersedes:` (if present) references an existing note ID
- [ ] ID matches filename (without `.md` extension)
- [ ] `concepts:` field present (list, possibly empty `[]`). Each entry passed through `normalize_concept_name()`; non-conformant raw values are silently rewritten to the canonical normalised form; entries that cannot be normalised are silently dropped. **Never halt; never CLARIFICATION** — autonomous resolution per the engine doctrine for the concept layer.
- [ ] `origin:` field present — value ∈ {`personal`, `work`, `external`}. Missing / unknown value → coerce to `personal` silently (the conservative default).
- [ ] `audience_tags:` field present (list, possibly empty `[]`). Each entry passed through `normalize_audience_tag()`; result accepted only if it matches canonical 5 OR an Extensions row in `_system/registries/AUDIENCES.md`; otherwise silently dropped. Final list may collapse to `[]` — that is the correct fail-closed outcome.
- [ ] `is_sensitive:` field present — boolean. String `"true"` / `"false"` coerced silently; any other type coerced to `false`.

If any check fails, fix immediately before proceeding.

### 3.7 Self-Review (subagent-internal coverage check)

> **Reprocess-corpus mode:** skip. Self-review verifies coverage of the
> source by newly-created notes; reprocess re-uses prior atomization.

**Runs inside the subagent**, per transcript, **after** §3.6 structural
verification, **before** the subagent moves to the next transcript or
returns its manifest. NON-OPTIONAL. Every transcript must produce a
coverage manifest.

**Purpose:** producer-side completion ritual. The subagent has just
processed a transcript and produced notes — before declaring done, it
re-anchors itself to the source one more time through the four scan
lenses, generates an explicit coverage manifest, and reconciles the
manifest against its own produced notes. Mismatches are fixed in place.

**Trust model:** this is producer-trust under «Opus + full context», not
external verifier-redundancy. The subagent is the authority on its own
output; self-review is the explicit finishing step that ensures every
transcript got the four-lens treatment uniformly. Limitation acknowledged:
shared blind spots between the main pass and the self-review pass cannot
be caught here — that is the cost of the producer-trust model.

#### 3.7.1 Generate coverage manifest

For the current transcript, anchor back to the **raw transcript content**
(skip any LLM-generated summary section in `transcript_with_summary.md`)
and produce four lenses:

a) PEOPLE SCAN: every person name, diminutive, or contextual reference
   («мой техлид», «тот парень из QA»). For each: participant or mentioned?

b) TOPIC SCAN: every topic shift or subject change. For each: one-sentence
   summary of what was discussed.

c) DECISION SCAN: every decision marker.
   Explicit: «решили», «договорились», «будем делать», «выбрали», «утвердили»,
   «отложили», «пока так», «по итогу».
   Implicit: agreement without objection, «ну давай так», default acceptance.
   For each: what was decided, by whom, with what reasoning?

d) ACTION SCAN: every commitment marker.
   «сделаю», «до пятницы», «надо будет», «я возьму», «запланирую».
   For each: who committed, to what, by when?

Quote literally where quotes matter. Be exhaustive — completeness here is
the entire value of the step.

#### 3.7.2 Reconcile against produced notes

For each item in the manifest:
- PRESENT in produced note(s) → MATCHED. Verify meaning preserved.
- ABSENT from produced notes → MISSED.

For each claim in the produced notes:
- Anchored to a manifest item or to a clear inference from one → OK.
- No basis in source → HALLUCINATED.

Failure types and fixes (apply in place, before returning):
- **MISSED** — fact in source, absent from note. Add to the note.
- **DISTORTED** — fact in note, meaning changed from source. Correct.
- **HALLUCINATED** — fact in note, no source basis. Remove.
- **THIN DECISION** — decision captured but lacks alternatives/reasoning/scope. Enrich.
- **UNLINKED REVISION** — decision updates a prior one without `supersedes:`. Add link.

#### 3.7.3 Manifest output

Subagent attaches per-transcript to its return manifest:
- `coverage_manifest`: the four scan lists.
- `fixes_applied`: list of `{type, target_note_id, brief}` for every fix.
- If no fixes were needed, `fixes_applied: []` — explicit empty, not omitted.
- `tradeoff_framing_records`: list of `_records/observations/...` paths
  (created in §3.5) that meet the §3.7.5 trade-off-observation
  eligibility — explicit named alternatives + values-bearing reason +
  reasoning-as-foreground. Empty list `[]` is the typical case;
  populate only when all three conditions hold. A record whose trade-off
  was already atomised into a `decision` knowledge note in this same run
  is NOT eligible for this list — that note carries the check through the
  typed-decision path, and listing the record too spends a second Opus
  call on the same reasoning.

### 3.7.5 Constitution Alignment Check

> **Reprocess-corpus mode:** skip. No new decisions are extracted; alignment was checked in the original run.

For every artefact produced in this run that satisfies the eligibility
criteria below, run an alignment check against the active constitution
tree. Artefacts carrying heavy `fixes_applied` from §3.7 self-review
(≥ 3 fixes, or any HALLUCINATED fix) are deferred — content reliability
borderline, do not generate drift clarifications until reviewed.

This step runs in the **orchestrator**, after all subagents complete and
their manifests are aggregated.

**Each path selects on a field the layer it targets actually carries.**
That is a hard constraint on this step, not a description of it. The two
paths draw from two different layers, and those layers have different
frontmatter: knowledge notes carry `types:` (§record-vs-note schema —
`layer: knowledge`), records carry `kind:` and never `types:`. A selector
pointed at a field its own layer does not emit matches nothing, forever,
while every artefact it should have caught still looks correct on disk —
so the failure is invisible to every content scan and is caught only by
the candidate count this step reports (below). Changing either layer's
frontmatter means revisiting this block in the same edit.

**Eligibility — two paths.**

1. **Typed-decision path (load-bearing).** A knowledge note created in
   this run whose `types:` array contains `decision`. Always eligible.
   Decisions are a knowledge-layer artefact — a record is the raw capture
   a decision was extracted *from*, and checking the raw capture would
   sweep in every alternative that was discussed and discarded.

2. **Trade-off-observation path (per Principle 6 «Action vs Knowledge —
   Capture Both»).** A record with `kind: observation` AND
   the record path appears in the subagent's
   `tradeoff_framing_records[]` list (§3.0.3 manifest schema). Trade-off
   framing is detected by the subagent during §3.5 / §3.7 with
   conservative criteria — emit the path into the list when ALL three
   hold:
   - The record contains an explicit choice between two named
     alternatives (X over Y, A vs B). Implicit preference (one option
     mentioned, the other absent) does NOT qualify.
   - A reason for the choice is given that names a value or priority
     ranking, not just a mechanical constraint («faster» without
     a values clause is mechanical; «faster matters more here than
     correctness because rollback is cheap» is values-bearing).
   - The reasoning is the record's foreground, not a parenthetical —
     i.e. removing the trade-off would gut the record's point.

   Subagents err toward `false` when uncertain. False negatives surface
   on the next `/minder:mem:lint --rescan-drift` (auto path or manual);
   false positives waste an Opus call but produce a `no-match` verdict
   with no further side effect. The asymmetric cost favours strict
   detection.

   **Why this path exists at all, rather than promoting the observation
   into a decision note.** The `types:` taxonomy is owner-facing —
   `decision` semantically implies a chosen path the owner can later
   reference («what did we decide about X?»). A trade-off observation in
   a journal entry («I notice I keep choosing speed over depth») is a
   values pattern, not a decision artifact; minting a decision note for
   it would corrupt search and registry semantics and put words in the
   owner's mouth. So the values signal is read where it actually lives,
   in the record, and the eligibility expansion stays in this step's
   logic rather than in the type taxonomy.

Artefacts that match neither path are skipped — not everything produced in
a run touches the constitution.

**Report what was considered, not only what was checked.** The step emits
`constitution_alignment.candidates_considered` into the batch manifest —
the count of artefacts each path examined before eligibility, per path.
A step that checks nothing because it *found* nothing and a step that
checks nothing because its selector cannot match are indistinguishable in
every other artefact this run produces, and the second condition held here
undetected for months. The count is what separates them, and
`/minder:mem:lint` A.14 watches it.

**How:** invoke `/minder:mem:check-decision` per eligible artefact. Pass:

- `situation` = one-sentence distillation of the decision (context + chosen
  path + stated rationale from the artefact)
- `record_ref` = wiki-link to the artefact the verdict is about — the
  decision note on path 1 (`[[YYYYMMDD-decision-...]]`), the observation
  record on path 2 (`[[YYYYMMDD-observation-...]]`). It is the citation the
  Evidence Trail carries back, so it points at what was actually read, never
  at the source the artefact was extracted from.
- `dry_run: false` (Evidence Trail append on cited principles is desired)
- `--from-pipeline /minder:mem:process` — marks the call as `caller_class:
  mechanical`. Skips per-decision auto-commit on the telemetry JSONL
  (`_system/state/check-decision-runs.jsonl`); the orchestrator's batch
  commit (or `/minder:mem:save`) picks up the accumulated telemetry lines.
  Without this flag every decision in the batch would create its own
  tiny commit.

**Verdict handling:**

| Verdict | Action |
|---|---|
| `aligned` | No CLARIFICATION. `/minder:mem:check-decision` already appends `citation-aligned` to cited principles' Evidence Trail and bumps their `last_applied`. |
| `violated` with per-decision confidence ≥ 0.8 | Raise CLARIFICATION of type `principle-drift`. Include: quote from the record, the violated principle id, short "why this looks like drift" rationale, options to resolve (confirm deviation → refine principle; reconsider decision; mark exception). |
| `tradeoff` | Raise CLARIFICATION of type `principle-tradeoff` (info-level). Include: the two principles in tension, the direction the record chose, invitation to log explicit reasoning back into the record. |
| `no-match` | No CLARIFICATION. Not every decision touches the constitution. |
| `no-basis` | No CLARIFICATION either — but for the opposite reason: nothing was loaded to match against. Silent here on purpose, because this fires on EVERY record of a base whose constitution is still empty, and one clarification per record would bury a new owner on their first run. The signal is not lost: telemetry carries `tree_size: 0`, and the `decision-review` lens reports the run of them as one observation. |

**CLARIFICATION item format** — same schema as other items under `## Open Items`:

```markdown
### YYYY-MM-DD — principle-drift: {principle.title}

**Type:** principle-drift
**Subject:** {principle.id}
**Source:** _records/{path}
**Action taken:** raised by /minder:mem:process Step 3.7.5 after /minder:mem:check-decision verdict violated (confidence 0.85)
**Quote:** > «{1–3 verbatim sentences from the record context}»
**Uncertainty:** Decision `{record.chosen}` appears to contradict `{principle.statement}`.
**To resolve:** confirm drift is intentional (refine principle or add exception note), reconsider the decision, or mark as a one-off exception with rationale.
```

`principle-tradeoff` uses the same shape with two principle refs in **Subject:**.

**Invariants for this sub-step:**

- Do not edit principle body. `/minder:mem:check-decision` handles L1 writes
  (Evidence Trail + `last_applied`); this step only raises CLARIFICATIONS.
- Do not create new principles. Pattern extraction into candidates is
  `/minder:mem:maintain`'s job, not `/minder:mem:process`.
- If `/minder:mem:check-decision` returns with an error (e.g. empty visible tree),
  log the failure in the processing record but do not block the batch —
  continue to Step 3.8. Constitution checking is additive, not a gate.

**Cost / latency note.** Each decision invokes `/minder:mem:check-decision`, which
runs Opus. On a Max subscription this is not a cost concern, but batches
with many decision records will add noticeable latency. If a batch starts
producing > 10 decision records per run, consider a single LLM call that
classifies the whole batch against the tree (one prompt, multi-record
reasoning) — that optimisation is not implemented today because current
batch sizes sit below that threshold and the per-record contract is
simpler to audit in `log_process.md`.

### 3.8 People Profiles

> **Reprocess-corpus mode:** skip. No new mentions are introduced; PEOPLE.md is unchanged.

**This step APPLIES the canonical rules from `_system/docs/SYSTEM_CONFIG.md` → "Data & Processing Rules".
Those rules are the single source of truth. If a rule changes, update SYSTEM_CONFIG, not this step.**

**Edit PEOPLE.md by anchor, never by a heading string.** Its header holds a
long prose `**Last Updated:**` paragraph that narrates the batch, and that
prose routinely contains the very heading names the file also uses as
structure — so a substitution keyed on a string like `## Stats` matches inside
the narration first and overwrites content that merely *described* the
section. Address the row or the table you mean, or read the file and rewrite
the specific region; a pattern that could match twice in this file is a
pattern that will. Nothing in this step authorises inventing a substitution
the step does not name: an edit shape not written here does not exist, and a
run that finds itself needing one has found a gap to surface, not a licence to
improvise on the owner's registry.

Applicable rules (all mandatory, no silent compromise):

1. **People inclusion — `inclusion-biased`.**
   - Every person with tier RESOLVED or NEW from the People Resolution Map (Step 0.2) who is mentioned in the transcript content (not noise) → include in the note's `people:` frontmatter array.
   - Do NOT apply "central to note" heuristic — it is subjective and a source of gaps.
   - **Bare first name** (AMBIGUOUS and cannot be resolved to a `firstname-lastname` ID) → do NOT add to `people:`. Default path: **append to `_system/state/people-candidates.jsonl`** via `python3 _system/scripts/append_person_candidate.py` (one entry per distinct mention — if the same bare name appears in N different transcripts in a batch, that's N appends). The buffer is aggregated weekly by `/minder:mem:lint` Scan C.5, which promotes recurring / information-rich candidates to CLARIFICATIONS. This keeps one-off mentions out of the user's resolution queue.

     **High-importance escape hatch.** Bypass the buffer and raise a CLARIFICATION immediately ONLY when ANY of these signals are present:
     - Bare name belongs to an external/client meeting (transcript contains `meeting` + `external` markers, or the session is clearly a 1:1 with an outside party).
     - Full surname is present elsewhere in the same transcript but wasn't matched due to STT artifacts (you have enough info to resolve NOW).
     - Explicit user tagging `@resolve-now` in transcript or inbox override file.
     - Role + context are fully specified in a single mention (e.g. "новый Head of X", "CEO of {company}") — promoting later adds no info.

     In all other cases: buffer append, no CLARIFICATION, `clarifications_raised` counter NOT incremented for this mention (buffer appends are reported separately as `people_candidates_appended`).

     **Invocation:**
     ```bash
     python3 _system/scripts/append_person_candidate.py \
       --name "Антон" \
       --date {record.created} \
       --source {source-path-excerpt} \
       --note-id {produced-note-id} \
       --quote "{1–3 verbatim sentences around the mention}" \
       [--role-hint "{role inferred from context}"] \
       [--related-people id1,id2] \
       [--suggested-id {id if fuzzy-match suggests one}] \
       [--high-importance]  # only if escape-hatch triggered — but in that case ALSO raise a CLARIFICATION; the buffer line serves as audit trail
     ```

     Quote + role_hint + related_people are optional but strongly encouraged — they make weekly aggregation + promotion decisions deterministic (lint reads the buffer, never re-reads transcripts).

**CLARIFICATION item formatting requirement (`people-bare-name` / `person-identity`).**

> The two canonical type strings, and the only two this step emits. `people-bare-name` is a mention whose name resolves to nobody in `PEOPLE.md`; `person-identity` is a mention that needs an identity decided — a new profile, or a choice between candidates. Never write a third spelling: the type string is the key the resolve queue clusters and filters on, so a variant makes an item invisible to the batch it belongs in.

> Applies ONLY when the high-importance escape hatch (above) triggers. For routine one-off bare names — append to the candidates buffer instead; `/minder:mem:lint` Scan C.5 will emit the CLARIFICATION on aggregation if promotion rules fire.

The item body MUST include:

1. **`**Quote:**` field** — verbatim transcript fragment (≥1 full sentence, ideally 2–3) around the mention. User resolves без opening source transcript.
2. **`**Context:**` field** (mandatory) — 2–4 sentence paragraph self-contained для LLM review session. Includes: what ambiguity is about, why uncertain, related entities inline (wikilinks/ids), relevant Focus/People context, 1–2 candidate resolutions с brief pros/cons.

Also include nearby topic/project markers when they help disambiguate (often more useful than role heuristic alone).

**Distinction Quote vs Context:**
- `Quote` = verbatim fragment из транскрипта (deterministic, source-grounded)
- `Context` = LLM-synthesized surrounding understanding (what item is *about*, not what was said verbatim)

Template:

```markdown
### YYYY-MM-DD — «{name-as-transcribed}» в T{N} ({timestamp}) — {one-line hint}

**Type:** people-bare-name | person-identity
**Subject:** {bare-name string OR candidate person-id}
**Source:** _sources/processed/{path}
**Suggested action:** resolve-bare-name | create-profile | dismiss
**Confidence tier:** surfaced (process always surfaces — never auto-applies identity)
**Action taken:** {what the pipeline did}

**Quote:** > «{1–3 verbatim sentences around the mention from the transcript}»

**Context:** {2–4 sentence paragraph: what ambiguity is about, PEOPLE.md candidates if any, related hub/project context, 1–2 candidate resolutions с brief rationale}

**Uncertainty:** {what is unclear and why}
**To resolve:** {what the user needs to do}
```

2. **Mention counting — `1-per-file`.**
   - When a person first appears in this file (in `people:` frontmatter OR as subject of the record/note), `Mentions` in PEOPLE.md += **1**.
   - Repeated occurrences of the SAME person within the SAME file do NOT increment further. Monotonic.
   - Decrements only happen on manual deletion or `/minder:mem:lint` dedup (out of scope here).

3. **PEOPLE.md 8-column schema preservation.**
   - Any write to PEOPLE.md (insert OR update) preserves all 8 columns: `ID | Name | Role | Org | Profile | Tier | Mentions | Last`.
   - On update of an existing row: change only the columns that changed (typically `Mentions`, `Last`, sometimes `Role`/`Org`). Never drop or reorder columns.

4. **Tier assignment — only on insert of a NEW person.**
   - If a profile was created in `3_resources/people/{id}.md` during this step → `Tier = 1`.
   - Otherwise → `Tier = 3` (default for newly added entries without profile).
   - **Existing persons are NEVER re-tiered by this skill.** Tier promotion (3 → 2, 2 → 1) is `/minder:mem:maintain` responsibility. Demotion requires human-in-the-loop via CLARIFICATION (never automatic).

For each person mentioned in the transcript (using the People Resolution Map):

1. **If exists in PEOPLE.md:**
   a) **New context check** — does the transcript reveal any of:
      - New role, title, or responsibility?
      - Organizational change (team move, promotion, new project)?
      - New relationship context with the author or other people?
      - Expressed opinion, skill, or competency not previously captured?
      - Key quote or characterization?
   b) If yes to ANY: READ current profile (`3_resources/people/{id}.md`)
      → APPEND new information to `## Контекст` section (don't overwrite existing text)
      → Update `## Ключевые темы` if new topic areas emerged
   c) **ALWAYS** add backlink to `## Упоминания`:
      `- [[{note-id}|{brief context}]] — YYYY-MM-DD`
      This is NOT optional — every mention in every processed transcript gets a backlink.
   d) Update row in PEOPLE.md:
      - `Mentions` += 1 (increment; dedup rule: 1 per file per person, не per-utterance)
      - `Last` = note's `created` date (YYYY-MM-DD)
      - `Tier` — не пересчитывать здесь (это задача `/minder:mem:maintain`). Оставить текущее значение

2. **If NEW (from People Resolution Map or discovered during audit):**
   - Create profile in `3_resources/people/{id}.md` using
     `5_meta/templates/person-template.md`
   - **Privacy trio (mandatory).** Set in profile frontmatter:
     - `origin` — inherit from the **creating record's `origin`** (the
       record that first surfaced this person in the current batch).
       Work-meeting record → `work`; personal-reflection record →
       `personal`; external-source record → `external`. If multiple
       records mention the new person in the same batch, use the
       chronologically-first record's `origin`. NEVER hardcode
       `personal` — it biases work-roster profiles wrongly.
     - `audience_tags` — ALWAYS `[]`. Profile aggregates owner-side
       context (mentions, opinions) which must not be re-shared
       without explicit owner widening — even for public colleagues.
     - `is_sensitive` — `true` if any captured content about this
       person is health / legal / personal-risk; `false` otherwise.
   - Add row to `3_resources/people/PEOPLE.md`. Все 8 колонок обязательны:
     - `ID`, `Name`, `Role`, `Org` — из extracted context
     - `Profile` — `[[{id}]]` (wikilink)
     - `Tier` — `1` если профиль создан (profile created ⇒ Tier 1); иначе `3`
     - `Mentions` — `1`
     - `Last` — note's `created` date
   - Carry `person/{id}` in the profile's own `tags:` frontmatter. Nothing is
     written to `_system/registries/TAGS.md`: its tables are a census rendered
     by `_system/scripts/render_tags.py` from the `tags:` frontmatter of the
     knowledge layer, inside an `AUTO-GENERATED: tag-registry` managed zone. A
     tag appears there because a note carries it and the census counts it, so
     anything written into that zone by hand is discarded by the next render —
     which is Step 0.0 of this very run.
   - Add person to the People Resolution Map (for subsequent files)

3. **If identity uncertain:**
   - Make best guess and create the profile (inclusion-biased)
   - Log uncertainty in `_system/state/CLARIFICATIONS.md` **Open Items** section
     with enough context for the user to resolve quickly
   - When user resolves: move item from Open Items to **Resolved Archive** table
     (one-line summary: date, item, resolution). This keeps Open Items clean
     while preserving audit trail for future transcription artifact matching.

Within a batch: if the same new person appears in multiple transcripts,
consolidate information BEFORE creating the profile. Collect all mentions
first, then create one comprehensive profile.

### 3.9 System Updates

> **Reprocess-corpus mode:** skip. TASKS / CALENDAR / OPEN_THREADS already reflect the original extraction.

**Runs in orchestrator, post-aggregate.** Subagents do NOT touch
PROCESSED.md or log_process.md — those updates are batched here from
aggregated subagent manifests.

For each processed source path (collected from all subagent manifests):

1. **PROCESSED.md** — add entry to the existing table (header: `| Source | Main Note | Date |`):
   `| _sources/processed/{source}/{timestamp}/transcript*.md | zettelkasten/{path-to-main-note}.md | YYYY-MM-DD |`
   Source path points to the FINAL location in `processed/` (file was moved there in Step 2.4).
   Duplicate check: if source path already in table, skip (unless `--reprocess`).

2. **log_process.md** — add one entry per run at TOP (newest first), aggregating across all batches:

   ```markdown
   ## YYYY-MM-DD — Processing: {run-summary}

   **Sources:** {N total, list grouped by batch}
   **Records created:** {N} — {list of record IDs}
   **Knowledge notes created:** {N} — {list of note IDs}
   **Knowledge notes extracted:** {N} — {list, with "from {record-id}"}
   **Hubs updated:** {N} — {list of hub IDs with brief change description}
   **Hubs created:** {N} — {list of new hub IDs}
   **People created:** {N} — {list}
   **People updated:** {N} — {list}
   **Self-review fixes:** {N total} — {distribution by type: MISSED / DISTORTED / HALLUCINATED / THIN DECISION / UNLINKED REVISION}
   **Concepts upserted:** {N} — total distinct concept identities touched this run
   **Concept type-conflicts:** {N} — same concept name carried different `type` across mentions; first-chronological wins (autofix, no CLARIFICATION)
   **Concept translations dropped:** {N} — non-English source terms with no clean translation; dropped to keep graph identity stable
   **Sensitive entities:** {N} — entities emitted with `is_sensitive: true`
   **Batches:** {batch_count} — {token totals, transcript counts per batch}
   ```

(Context handoff between transcripts now happens implicitly within shared
subagent context per batch; no per-file handoff document needed.)

### 3.10 Verify Source Integrity

**Runs in orchestrator, post-aggregate.** Cross-cuts the file completeness
invariant from §3.0.4 with note-level path checks.

For every source path in `S` (enumerated set from §3.0.4):
- Confirm file exists in `_sources/processed/{source}/{id}/` (moved in Step 2.4).
- Confirm at least one note in subagent manifests carries this path in its
  `source:` field (or in any `source:` of its produced notes).
- Confirm PROCESSED.md entry was written for it (Step 3.9).

If any check fails — halt at Completion Gate (Step 5). Do NOT proceed to
batch artifacts. The mismatch implies either a subagent silently dropped
a transcript or a write-step failed; both require investigation, not
continuation.

---

## Step 4: Post-Processing

After ALL files in the batch are processed:

### 4.1 Update TASKS.md

> **Reprocess-corpus mode:** skip (no new tasks).

**Canonical structure & format: see `_system/docs/SYSTEM_CONFIG.md` → "Task Format" section.**
Source of truth for section names, classification rules, header format, and stream grouping.

**Incremental algorithm:**

1. **Read existing TASKS.md first** — extract the set of `^task-id` values currently
   in the `## Stale` section. These IDs MUST be preserved in Stale, never moved back
   to active sections, even if the source note still has them as `- [ ]`.
   Stale = result of user's manual review; pipeline doesn't override it.

2. **Incremental scan (this batch only).** Extract `- [ ]` items from the notes
   created OR updated in THIS batch — already in memory from Step 3, not a walk of
   the whole corpus. Each yields task description, linked note, `^task-id`, and any
   `→ [[person-id]]` reference. (A full corpus walk is unsustainable at scale — an
   autonomous tick would silently downgrade it and drop tasks. Completeness is
   guaranteed deterministically by the reconciler in step 8, not by re-walking
   everything each run.)

3. **Classify each new task** using the table in SYSTEM_CONFIG (Action / Waiting / Delegate).
   Key distinctions:
   - **Action**: «{owner-first-name from SOUL.md Identity}: ...», first-person speech (`I:`/`я:`), or task clearly for owner to execute
   - **Waiting**: «@person: ...» AND owner is the recipient of the output (blocker for owner)
   - **Delegate**: owner assigned/escalated, owns tracking, but output goes to team/process
   - **Someday** / **Personal**: separate sections (low priority; non-work)
   - **Unclear**: → Action (safe default)

4. **Merge by `^task-id` into the existing structure.** For each extracted id:
   - id in the `## Stale` set → leave in Stale (never resurrect; owner's manual review).
   - id already in an active section → update text/link in place, keep its current
     section and stream (do not re-litigate a prior classification).
   - new id → classify (step 3) and insert into the right section + stream.

5. **Group within each section by stream** (`### Stream Name`). Use existing streams
   from the current TASKS.md; create new stream when a clear topic cluster emerges
   (≥3 related tasks). Stream list is organic and evolves.

6. **Semantic dedup — keyed by `(note-link, ^task-id)`, not id alone.** The same
   `^task-id` intentionally recurs across a record and its derived knowledge notes
   (one logical task, many notes) → merge those into one entry (union the note-links).
   But `^task-id` is unique only *within a file* (SYSTEM_CONFIG Task Format), so two
   genuinely different tasks in different notes can collide on an id — keying dedup by
   id alone would silently drop one. Merge only when the task text matches; on a true
   collision keep both, disambiguating the id, and log it.

7. **Update header** — recompute `Last Updated`, per-section counts, `Total unique`.

8. **Completeness gate (deterministic backstop — the load-bearing anti-drop check).**
   Run `python3 _system/scripts/reconcile_tasks.py --base . --report --json`.
   It walks ALL notes (cheap, unbounded, no LLM) and reports `orphan_count` — task-ids
   present in notes but in no active/Stale section of TASKS.md. If `orphan_count > 0`,
   the incremental pass left tasks un-aggregated (tasks in notes not touched this
   batch): classify and file each reported orphan, then re-run until `consistent: true`.
   Never self-certify "TASKS.md updated" without this reconciliation passing — a
   checkbox the agent ticks while having appended only the batch's own tasks silently
   drops every task in a note it did not touch this run. The nightly lint A.6.1 scan
   is the durable backstop that catches the gap regardless of what a tick did.

**On-demand reconcile — `/minder:mem:process --reconcile-tasks`.** Runs
`reconcile_tasks.py --report --json`, then classifies each reported orphan per step 3
and files it into the right section + stream, and recomputes the header. Bounded to
the orphan delta — cheap, never downgraded. This is the classifier half of the
reconciler; the script is the deterministic scanner half. Entry point for the weekly
lint `task-aggregation-orphans` CLARIFICATION and the update-migration nudge — both
detect orphans and point the owner here. The reconciler never writes (orphans are
always re-derivable from the notes), so nothing is lost between detection and
classification. **Finish with a re-verification: re-run `reconcile_tasks.py --report`
and confirm `consistent: true` (orphan_count 0) before reporting done — the owner's
immediate proof the backfill actually landed. If orphans remain, repeat until clean.**
`--reconcile-calendar` mirrors this: re-aggregate the flagged notes' future events, then
re-run `reconcile_calendar.py --report`; any residue is prose-only events out of the
coarse check's reach (report that honestly rather than looping).

### 4.2 Update CALENDAR.md

> **Reprocess-corpus mode:** skip (no new events).

**Canonical structure & format: see `_system/docs/SYSTEM_CONFIG.md` → "Event/Meeting Format" section.**

**Incremental algorithm:**
1. Extract `📅 **{date}**` items — with descriptions and note links — from the notes
   created OR updated in THIS batch (not a walk of the whole corpus — a full
   corpus walk is unsustainable at scale; an autonomous tick would silently
   downgrade it and drop events).
2. Separate Recurring (explicit regular meetings in note content) from one-off events.
3. Identify Deadlines — events framed as «@person должен сделать X к дате» — move to Deadlines section.
4. Merge each event into the existing CALENDAR.md sections by (date, note-link); split by date vs today:
   - Future → Upcoming (Deadlines if `@person`)
   - Past but within 2 weeks → Past
   - Older than 2 weeks → DROP (don't carry forward)
5. Update `Last Updated` in header.
6. **Best-effort completeness check (NOT a deterministic gate).** Run
   `python3 _system/scripts/reconcile_calendar.py --base . --report --json`.
   It reports notes carrying a FUTURE `📅` BODY line whose `[[note-link]]` is absent
   from every forward-facing CALENDAR section. Coverage is partial: unlike tasks
   (real `^task-id` anchors), many events are synthesized from meeting PROSE and
   never appear as a `- 📅` line, so a drop of a prose-only event is invisible to
   this check — it catches `📅`-anchored drops only. If `orphan_note_count > 0`,
   re-aggregate those notes' future events. The durable protection is the nightly
   lint A.6.3 scan surfacing what it CAN see; this in-process check is an assist,
   not a guarantee. On-demand: `/minder:mem:process --reconcile-calendar`.

### 4.3 Update HUB_INDEX.md

> **Reprocess-corpus mode:** skip (no new hubs created).

**Additive only.** Append a `[[hub-*]]` row for each hub this run CREATED (§3.5 D).
Rows for hubs this run merely updated need no touch.

**The row goes INSIDE the managed zone** — into the section matching the hub's
`status:`, between `<!-- AUTO-GENERATED: hub-index -->` and its `END` marker,
matching the columns already there. A row written below the `END` marker lands
in the owner's `## Cross-link state` region, where no rebuild can ever reconcile
or remove it: `/minder:mem:maintain` Step 7.11 rewrites the zone and nothing else.

The full rebuild belongs to
`/minder:mem:maintain` Step 7.11 (`render_hub_index.py`) per the Skill Write Territory in `_system/docs/SYSTEM_CONFIG.md`;
index-vs-disk drift is caught deterministically by `/minder:mem:lint` A.6.2
(`hub-index-incomplete`), which routes the owner back to maintain. A rebuild
here would overwrite maintain's curation from a single-batch view.

### 4.4 Content Potential Verification

Verify that all newly created knowledge notes with content potential have
complete frontmatter: `content_potential`, `content_type`, and `content_angle`.
If any field is missing — add it now based on Q14 assessment.

NOTE: There is no separate CONTENT_PIPELINE registry. Content candidates live
in note frontmatter and are discovered dynamically by `/minder:mem:content`.
POSTS.md tracks only published posts.

### 4.5 Batch Verification

Run these checks over the ENTIRE processing run's output:

- [ ] Count match: every transcript-grounded source produced exactly one record (kind = meeting | observation per Q9 routing)
- [ ] **Fence integrity (batch-wide, defence-in-depth):** for every file created OR updated in this run that carries frontmatter + body — knowledge notes, records, **hubs (`5_meta/mocs/`), and person profiles (`3_resources/people/`)** — `_common.frontmatter_closed_before_body(path)` is True and `_common.read_frontmatter(path)` is non-None. Any failure is repaired via `_common.repair_misplaced_fence(path)`; if repair returns False (ambiguous shape), raise a `frontmatter-fence-misplaced` CLARIFICATION rather than shipping an unparseable file. The same corruption (a `## ` body heading captured inside the YAML) can occur in any LLM-composed file, not only knowledge notes.
- [ ] No orphan path-link Evidence Trails: every new knowledge note's `## Evidence Trail` wikilink points at a record-id or note-id, never at `_sources/...`
- [ ] No orphan extracted_from: every `extracted_from:` reference points to an existing record
- [ ] All hubs exist: every hub referenced in notes exists as a file in `5_meta/mocs/`
- [ ] Bidirectional cross-references: if note A links to note B, note B's hub/relations should reference note A
- [ ] No duplicate notes: no two notes cover the same topic from the same source
- [ ] PROCESSED.md complete: every processed source file has an entry
- [ ] People registry consistent: every person ID in any note's frontmatter exists in PEOPLE.md
- [ ] Concept aggregation: every distinct concept name appearing in any frontmatter `concepts:` field across the run has exactly one entry in `concepts.upserts[]` (deduplication by case-folded snake_case). When the same name was emitted with different `type` values across mentions, the **first-chronological-mention wins** (deterministic by transcript timestamp); subsequent mentions silently coerce to that type for the upsert. No CLARIFICATION raised — autonomous tie-break.
- [ ] Hub `member_concepts[]` consistency: for every hub touched, manifest `member_concepts[]` equals the union of `concepts:` from member knowledge notes that exist on disk after this run. No phantom concept names (in member_concepts but in no member note's frontmatter).

### 4.6 Content Proportionality Check + Coverage Fix Rate

#### Proportionality

Compare source length vs output density:

| Source type | Expected key points per ~10 minutes |
|---|---|
| Work meeting (tactical) | 5-8 bullets |
| Work meeting (strategic) | 3-5 bullets + 1-2 knowledge notes |
| Therapy / reflection | 2-4 knowledge notes |
| Idea brainstorm | 1-3 knowledge notes |

If output is significantly thinner than expected, flag in the report.

#### Coverage Fix Rate

Aggregate `fixes_applied` from all subagent manifests. Calculate: what %
of notes had any fix during §3.7 self-review?

- < 20%: Normal. Producer pass and self-review well-aligned.
- 20-50%: Elevated. Subagent's main pass leaving gaps the self-review is
  catching — review classification prompt or context budget per batch.
- > 50%: Systemic issue. Flag in report with recommendation (likely
  T threshold too high or N cap too high — subagent attention diluted).

Also report: distribution of fix types (MISSED / DISTORTED / HALLUCINATED /
THIN DECISION / UNLINKED REVISION) — concentration in one type points to
a specific failure mode in the pipeline.

### 4.7 Batch Data Accumulation (in-memory, before Completion Gate)

Assemble the full dataset required for the batch artifacts — **in memory only**, no disk
writes yet. Disk writes happen at Step 5.5, strictly after the Completion Gate.

Accumulate:

- **`batch_id`** = UTC timestamp of run start, format `YYYYMMDD-HHmmss`. Fixed at the moment the concurrency lock was acquired and stable for the rest of the run. On collision (theoretical, due to concurrency lock this should not happen) — append suffix `-1`, `-2`.
- **`timestamp`** = ISO 8601 UTC with trailing `Z` (run start).
- **`processor`** = `minder:mem:process`.
- **`format_version`** = `2.4`. The markdown report mirrors the JSON manifest's
  top-level `format_version`; the contract that owns the value is
  `_system/docs/manifest-schema/` (`v{MAJOR}.json` + its README's SemVer rules),
  NOT `batch-format.md`'s own `version:` frontmatter field, which versions that
  document rather than the manifest.
- **Counts:** `sources`, `records`, `notes`, `tasks`, `events`, `threads_opened = 0`, `threads_resolved = 0`, `clarifications_raised`, `people_candidates_appended`, `concepts_upserted`, `sensitive_entities`, `concept_type_conflicts`, `concept_translations_dropped` (see counter mechanics below).
- **Lists for each section of the batch report:** Sources Processed (with source type ID), Records Created (id + title + people + projects), Knowledge Notes Created (id + title + types + domains + Evidence Trail status), Tasks Extracted (task-id + description + deadline + priority + from-note), Events Extracted (datetime + description + participants + from-note), People Updates (id + change type + mentions delta + tier note), Hubs Updated (id list), CLARIFICATIONS Raised (type + summary per item), Concepts Upserted (name + type + subtype + related_concepts), Sensitive Entities (path + kind + audience_tags).

**Observability counters (engine self-watch — no owner action).**

- `concept_type_conflicts` — increment when the same canonical concept
  name appears in this batch with two or more different `type` values
  across mentions. The first-chronological-mention wins (§4.7 below);
  subsequent mentions silently coerce. The counter exists so a sustained
  non-zero trend over weeks can be eyeballed in `BATCH_LOG.md` and
  prompts a pipeline review — no per-batch CLARIFICATION.
- `concept_translations_dropped` — increment for every concept candidate
  Q15 dropped because the source term was genuinely untranslatable.
  Same rationale: per-event invisible to owner; aggregate over time
  surfaces a translation-quality regression worth investigating.

Both counters land in two places:
- per-batch frontmatter at `_system/state/batches/{batch_id}-process.md` (one
  row per batch — high-fidelity)
- per-run summary at `_system/state/log_process.md` (one entry per
  /minder:mem:process invocation — easy-to-eyeball aggregate)

They are NOT added to BATCH_LOG.md (which is a 9-column terse routing
index for lint scanning, not an observability surface — adding columns
bloats it without corresponding usage). They are observability slots,
never gating signals.

**Concept registry aggregation.** Build `concepts.upserts[]` for
the batch:

1. Walk every record + knowledge note + hub touched in this run; collect
   their `concepts:` frontmatter values (plus, for hubs, the union of
   member-note `concepts:` → `member_concepts[]`).
2. Run every collected name through `normalize_concept_name()`. Drop
   `None` returns silently. Deduplicate the surviving list by canonical
   name (case-folded snake_case). For each distinct name, consolidate
   metadata captured during Q15 extraction:
   - `type` — first-chronological-mention wins (deterministic by
     transcript timestamp). If `qdrant` was tagged `tool` in transcript
     T1 and `theme` in T2, the upsert carries `type: tool`. Subsequent
     mentions silently coerce.
   - `subtype` — same first-wins rule.
   - `related_concepts[]` — set-union of all related lists across
     mentions, each entry passed through `normalize_concept_name()` and
     filtered to exclude the parent `name` (no self-loops).
   - `previous_slugs[]` — present only if a Q15 rename was detected;
     each entry passed through normaliser; otherwise omitted.
3. **Autonomous post-normalisation guard.** Every value emitted into
   `concepts.upserts[]` was already produced by `normalize_concept_name()`
   in step 2 — by construction it is conformant. No additional halt,
   no CLARIFICATION. Lint Scan A.7 is a post-write double-check that
   stays silent on a clean batch.
4. Final list = `concepts.upserts[]`. `concepts_upserted` counter =
   `len(concepts.upserts)`.

**Sensitive-entity aggregation.** Walk every entity emitted in
this run (records, knowledge notes, hubs touched, person profiles
created/updated, project profiles, tasks, events, ideas). For each
where `is_sensitive: true`, append `{path, kind, audience_tags}` to
`sensitive_entities[]`. `sensitive_entities` counter = `len(...)`.

**Per-entity privacy field aggregation.** Every entity entry in the
in-memory accumulator carries the trio (`origin`, `audience_tags`,
`is_sensitive`) read directly from the entity's frontmatter. The
manifest emission step (5.5) writes these into the JSON manifest's
per-entity sections so downstream Minder can populate `audience_tags
text[] NOT NULL DEFAULT '{}'` columns without re-parsing markdown.

**`clarifications_raised` counter mechanics:**

- The skill maintains an in-memory integer counter across the entire run. Reset to **0** at run start.
- Every time the skill appends an item under `## Open Items` in `_system/state/CLARIFICATIONS.md` — regardless of type (`process-compatibility`, `people-bare-name`, `person-identity`, `idea-ambiguous-match`, `evidence-trail-anomaly`, etc.) — the counter increments by exactly **1**.
- The final counter value is recorded in batch frontmatter as `clarifications_raised:`.
- The counter is **not** persisted between runs.

**`people_candidates_appended` counter mechanics:**

- Parallel in-memory counter reset to **0** at run start.
- Increments by 1 for every successful `append_person_candidate.py` invocation (one per bare-name mention routed to the buffer).
- Does NOT double-count high-importance escape-hatch cases: in that path, a CLARIFICATION is raised (increments `clarifications_raised`) AND a buffer line is written as audit trail (increments `people_candidates_appended`). Both counters are independent.
- The final value is recorded in batch frontmatter as `people_candidates_appended:`.
- Report it separately from `clarifications_raised` in the batch report — these are two distinct user-visible states (inbox for lint aggregation vs immediate resolution queue).

**Thread counts are zero.** `/minder:mem:process` does NOT open or resolve threads — that is `/minder:mem:maintain` responsibility. This is a hard invariant and is checked at the Completion Gate.

---

## Step 5: Completion Gate

**MANDATORY. Do NOT produce the report until ALL items are verified.**

If any item is incomplete, go back and complete it. No deferring as "follow-up."

- [ ] All transcripts processed (records + knowledge notes written to disk)
- [ ] **File completeness invariant** (§3.0.4): union of `transcripts_processed[].path` across all subagent manifests equals enumerated source set `S` exactly — no missing, no duplicates
- [ ] Self-review (Step 3.7) coverage manifest returned for EVERY transcript; `fixes_applied` populated (empty list explicit if no fixes)
- [ ] No subagent returned a non-empty `errors` list (halt-on-error invariant)
- [ ] Per-note structural verification passed (Step 3.6, inside subagent)
- [ ] People profiles: new people added to PEOPLE.md + profile files created in `3_resources/people/`
- [ ] People profiles: existing people's `## Упоминания` updated with new mentions
- [ ] Tags: every new person's profile carries `person/{id}` in its own `tags:` frontmatter. Nothing is checked in `_system/registries/TAGS.md` — its tables are a census `render_tags.py` derives from that frontmatter, so a tag arrives there by being carried, never by being added
- [ ] Hubs: existing hubs updated **non-destructively** (integrate into "Текущее понимание" preserving prior synthesis — never full-rewrite; add to chronological map, changelog)
- [ ] Hubs: new hubs CREATED for topics reaching 3+ knowledge notes threshold
- [ ] HUB_INDEX.md carries a `[[hub-*]]` row for **every hub this run created** (additive; §4.3). Whole-index completeness is `/minder:mem:maintain`'s rebuild and lint A.6.2's check, not this gate's
- [ ] PROCESSED.md updated for all processed source paths
- [ ] log_process.md entry added (newest first)
- [ ] TASKS.md updated (header counts refreshed; Stale section preserved from previous TASKS.md; classification Action/Waiting/Delegate applied per SYSTEM_CONFIG rules) **AND `reconcile_tasks.py --report` returns `consistent: true` (orphan_count 0)** — the deterministic anti-drop invariant, not a self-certified checkbox
- [ ] **Identity residue is zero.** Run `python3 _system/scripts/identity_audit.py --report --fail-on-residue` and record its `live residue` count in the batch report. It resolves every identifier surface against `1_projects/PROJECTS.md` — the deterministic anti-drift invariant, not a self-certified checkbox. Read the compact `--report` summary, not `--json`: the full finding stream runs to a hundred kilobytes and belongs in an investigation, not in every tick's context. A non-zero exit has three causes and the report names which: **live residue** — this run put a retired identifier back on a live surface, so fix it in the notes this run wrote and re-run the audit; **an unclassified region** — a path no classification rule claims, which is what a new top-level folder looks like on its first run and is not something this batch did wrong; or **an orphan tag** — a note this run wrote carries `{namespace}/{id}` naming an identity its registry never declared, live or retired. The second is a `process-compatibility` CLARIFICATION naming the region. The third is a defect of this run's own notes when they are the ones carrying it: retag to an identity that exists, or drop the tag — never invent a registry row to make the gate green, because registering an identity is the owner's decision and this gate is not the place it gets made. An orphan on a note this run did NOT touch is an `identity-orphan` CLARIFICATION, not this batch's work. Either way, do not tick this gate around it.
- [ ] CALENDAR.md updated (Past section pruned to last 2 weeks; Deadlines have `@person-id` prefix); `reconcile_calendar.py --report` run as a **best-effort** assist (it catches only `📅`-anchored future-event drops — the nightly lint A.6.3 scan is the durable check)
- [ ] Content potential fields verified (content_potential + content_type + content_angle)
- [ ] Knowledge notes placed in correct PARA folder (NOT in deprecated `2_areas/work/meetings/`)
- [ ] New records in `_records/{meetings,observations}/` per Q9 routing (NOT in `2_areas/work/meetings/`); every transcript anchored to exactly one record
- [ ] Batch verification passed (Step 4.5)
- [ ] CLARIFICATIONS.md reviewed — new items noted for report
- [ ] content_potential assessed for all new knowledge notes (Q14)
- [ ] Every new knowledge note (`layer: knowledge`, not record, not profile) in this batch contains `## Evidence Trail` with ≥ 1 initial entry placed BEFORE `## Source`
- [ ] PEOPLE.md — 8 columns (`ID | Name | Role | Org | Profile | Tier | Mentions | Last`) preserved in every row touched this run; new rows have all 8 populated
- [ ] In-memory batch data accumulated (Step 4.7): `batch_id` fixed; count fields reconcile with actually created artifacts; `clarifications_raised` matches the in-memory counter value
- [ ] `threads_opened = 0` AND `threads_resolved = 0` (process does not touch threads)
- [ ] `people_candidates_appended` matches both (a) the in-memory counter and (b) actual line-count delta in `_system/state/people-candidates.jsonl` since run start. If mismatch — do NOT write batch; investigate the gap (typically missed append invocation or double-count on escape-hatch path)
- [ ] **Concept extraction (Q15) ran for every transcript.** Every produced record + knowledge note carries a `concepts:` frontmatter field (list, possibly `[]`). Every non-empty entry is the output of `normalize_concept_name()` (post-normalisation values are conformant by construction).
- [ ] **Privacy trio (Q16) set on every emitted entity.** Every record, knowledge note, hub touched, person profile created/updated, project profile, task, event, idea has all three fields (`origin`, `audience_tags`, `is_sensitive`) present in frontmatter. Defaults applied silently where Q16 didn't infer.
- [ ] **`concepts.upserts[]` aggregation passed (§4.7).** Every entry produced by `normalize_concept_name()` chain; first-chronological-mention wins for `type` ties. `concepts_upserted` counter matches `len(concepts.upserts)`.
- [ ] **`sensitive_entities[]` aggregation passed (§4.7).** Every entity with `is_sensitive: true` listed once in `sensitive_entities[]` with `{path, kind, audience_tags}`. `sensitive_entities` counter matches `len(...)`.
- [ ] **Hub privacy auto-derivation passed.** Every hub touched in this run had `origin` / `audience_tags` / `is_sensitive` re-derived from current members (dominant origin / audience-intersection / any-sensitive) before manifest emission.

**Note on batch artifacts:** the files `_system/state/batches/{batch-id}-process.md` and the new row in
`_system/state/BATCH_LOG.md` are NOT yet on disk at this point, and therefore are NOT checked in
this gate. Their write happens at Step 5.5 — strictly POST-Gate. If this gate fails, Step 5.5
does not run and no batch file appears on disk. Absence of batch = absence of contract.
Crash recovery via PROCESSED.md handles partial filesystem state on the next run.

**No deferring.** Every item above is part of the pipeline, not follow-up.
If context window is tight, use subagents for parallel work
(hub creation, view regeneration) — but verify their output.

---

## Step 5.5: Batch Artifacts Write (post-Gate)

**Runs ONLY if Step 5 Completion Gate passed fully.** If the gate failed, stop here —
no batch artifacts on disk.

### 5.5.1 Write `_system/state/batches/{batch-id}-process.md`

Create the per-batch report file according to the contract in
`_system/docs/batch-format.md`.

**Frontmatter (all keys required):**

```yaml
---
batch_id: {YYYYMMDD-HHmmss}
timestamp: {ISO 8601 UTC with trailing Z}
processor: minder:mem:process
format_version: {current spec version from batch-format.md}
sources: N
records: N
notes: N
tasks: N
events: N
threads_opened: 0
threads_resolved: 0
clarifications_raised: N
people_candidates_appended: N
concepts_upserted: N
sensitive_entities: N
concept_type_conflicts: N
concept_translations_dropped: N
---
```

**Sections (in this exact order, never skipped — use `(none)` when empty):**

1. `## Sources Processed` — one bullet per transcript: `- {path} ({source-type-id})`
2. `## Records Created` — per record: `- [[{id}]] | {title}` + child bullets `People:` and `Projects:`
3. `## Knowledge Notes Created` — per note: `- [[{id}]] | {title}` + child bullets `Types:` + `Domains:` + `Evidence Trail: started|appended`
4. `## Tasks Extracted` — per task: `- {task-id} | {description} | deadline: {date or —} | priority: {low|normal|high}` + child bullet `From: [[{note-id}]]`
5. `## Events Extracted` — per event: `- {datetime} | {description} | participants: {ids}` + child bullet `From: [[{note-id}]]`
6. `## People Updates` — per person touched: `- {id} | {change-type} | mentions: {before}→{after} | tier: {value} (no change | promoted via maintain later)`
7. `## Threads` with sub-sections `### Opened` and `### Resolved` — both `(none)` for `/minder:mem:process` (process never touches threads)
8. `## Hubs Updated` — `- [[{hub-id}]]` per hub touched
9. `## CLARIFICATIONS Raised` — per item: `- {type} | {one-line summary}` — count MUST equal `clarifications_raised` in frontmatter
10. `## People Candidates Appended` — per entry: `- {candidate_id} | {name_as_transcribed} | {note-id} | {role_hint or —}` — count MUST equal `people_candidates_appended` in frontmatter. Use `(none)` if empty.
11. `## Concepts Upserted` — per concept upsert from §4.7 aggregation: `- {name} | {type} | {subtype or —} | {related_concepts comma-list or —}` — count MUST equal `concepts_upserted` in frontmatter. Use `(none)` if empty. Mirrors the JSON manifest's `concepts.upserts[]`.
12. `## Sensitive Entities` — per entity emitted in this run with `is_sensitive: true`: `- {path-or-id} | {kind: record|note|hub|task|...} | audience_tags: [{tags or "[]"}]` — count MUST equal `sensitive_entities` in frontmatter. Use `(none)` if empty.

### 5.5.1.5 Write `_system/state/batches/{batch-id}-process.json`

> **Reprocess-corpus mode:** identical schema, identical
> `processor: "minder:mem:process"`, identical `format_version`. The
> `records.created[]` and `knowledge_notes.created[]` arrays are
> empty; populated entries land under `records.updated[]` /
> `knowledge_notes.updated[]`. `concepts.upserts[]` IS populated —
> this is the load-bearing output of the mode and the mechanism by
> which `/minder:mem:maintain` Step 4.5 picks up types into `CONCEPTS.md`.

Emit the machine-parseable JSON manifest alongside the markdown
report. Canonical schema: `_system/docs/manifest-schema/v{MAJOR}.json`
in this repo, reference doc `manifest-schema/README.md`. (Any one
downstream consumer's own design doc is a consumer, not the contract —
a friend's clone has no such repo.)

Assemble the JSON dict in memory from the in-memory accumulator
(§4.7) — top-level keys per that schema (`batch_id`,
`timestamp`, `format_version: "2.4"`, `processor: "minder:mem:process"`,
`sources_processed[]`, `records.{created,updated}[]`,
`knowledge_notes.{created,updated}[]`, `hubs.{created,updated}[]`,
`constitution{}`, `tier1_objects{}`, `tier2_objects{}`,
`concepts.upserts[]`, `stats{}`). Each per-entity entry carries
`origin`, `audience_tags`, `is_sensitive` from frontmatter; concept
fields per the same accumulator output.

`constitution.alignment` carries §3.7.5's own accounting and is emitted on
every run, including runs where nothing was eligible:

```yaml
constitution:
  alignment:
    candidates_considered:
      typed_decision: 24        # knowledge notes this run, before eligibility
      tradeoff_observation: 3   # observation records this run, before eligibility
    checked: 9                  # passed eligibility and were checked
```

Emit the counts even when they are zero — a zero that is present says the
selector ran and found nothing, and a zero that is absent says nothing at
all. That distinction is the whole point of the field: it is what lets
`/minder:mem:lint` A.14 tell a quiet fortnight apart from a selector that
stopped being able to match its own layer.

Then invoke the autonomous emitter:

```bash
python3 _system/scripts/emit_batch_manifest.py \
    --input <path-to-temp-json> \
    --output _system/state/batches/{batch_id}-process.json
```

The helper:
- runs every concept name through `normalize_concept_name()` (post-
  emission safety net; clean accumulator → zero events)
- enforces audience-tag whitelist via canonical 5 + AUDIENCES.md
  active extensions
- coerces `origin` / `is_sensitive` to safe defaults if invalid
- drops `concepts.upserts[]` entries whose `name` is unnormalisable
- writes the conformant JSON; emits any normalisation events on
  stderr for ingestion into the batch's audit log

Failure semantics:
- exit `0` — manifest written
- exit `2` — input is not parseable JSON or root is not an object
- exit `3` — manifest fails the structural contract with downstream
  Minder (missing required top-level key, unknown `processor`,
  incompatible `format_version` major, or processor-required section
  missing). Field-level concept / audience normalisation NEVER
  produces non-zero exit — autofix or drop per the autonomous-
  pipeline contract.

**Then verify what actually landed — in this tick, not tonight.**

```bash
python3 _system/scripts/lint_manifest_schema.py \
    --batches-dir _system/state/batches --schemas-dir _system/docs/manifest-schema --all \
  | grep '"batch": "{batch_id}-process.json"'
```

A `"kind": "violation"` line here means the file on disk does not honour the
manifest contract. Treat it exactly as an emitter `exit 3`: the manifest is not
valid, so do NOT append the BATCH_LOG row, and surface it in the run report.

The emitter can only refuse what it is given: a tick that assembles the JSON and
writes it to `batches/` **without invoking the emitter** bypasses every guarantee
above, and nothing would notice until the nightly lint — a day later, on a
manifest a downstream consumer may already have read. Verify the artefact rather
than trust the procedure.

If exit `3` fires: the in-memory accumulator is malformed (missing
section the SKILL forgot to populate, or wrong processor enum). Do
NOT retry blindly — read stderr message, fix the accumulator
assembly, re-emit. Surface to owner as a `process-compatibility`
CLARIFICATION ONLY if root cause cannot be auto-corrected (e.g.
the manifest schema changed and this SKILL's assembly drifted from it).

### 5.5.2 Append row to `_system/state/BATCH_LOG.md`

Append ONE new markdown table row to the Batch Log, matching the schema defined
in `_system/docs/batch-format.md` (9 columns):

```
| {batch_id} | {timestamp} | {sources} | {records} | {notes} | {tasks} | {events} | 0 | 0 |
```

**Strict rules:**
- Append-only. Never rewrite, reorder, or delete existing rows.
- Exactly ONE new row per successful run.
- The `threads_open` and `threads_close` columns are always `0` for `/minder:mem:process` output.

### 5.5.3 Failure semantics

The three artifacts of Step 5.5 (markdown, JSON manifest, BATCH_LOG row)
are atomic-ish: BATCH_LOG row appends only after BOTH `batches/{id}-process.md`
AND `batches/{id}-process.json` wrote successfully.

- If markdown write fails (filesystem error) → best-effort delete the
  partial file; do NOT proceed to JSON write or BATCH_LOG append.
- If JSON write fails (filesystem error, OR `emit_batch_manifest.py`
  exit 3 = structural contract violation) → no partial JSON ever
  lands at the output path (emitter writes via `.tmp` + `os.replace()`
  and unlinks the `.tmp` on crash); KEEP the markdown file (it
  remains a valid human-readable record of the run); do NOT append
  BATCH_LOG row. Markdown without JSON is observable as «row missing
  in BATCH_LOG» on next lint scan — surfaces the gap explicitly.
- On any 5.5 failure: log the error, surface it in the Step 6 report
  under `### Errors`, exit non-zero. Crash recovery via PROCESSED.md
  handles the next-run picture; this run's notes are already on disk
  (Step 3.5 wrote them inside subagents) and will not be re-processed
  unless `--reprocess` is passed.

---

## Step 6: Report

Output to user:

```
## Minder Memory Processing Report — YYYY-MM-DD

### Files Processed: N

| # | Source | Record | Knowledge Notes | Hubs |
|---|--------|--------|-----------------|------|
| 1 | {timestamp} — {topic} | {record-id or "—"} | {note-ids or "—"} | {hub updates/creates} |

### Summary
- Records created: N
- Knowledge notes created: N (of which N extracted from records)
- Hubs updated: N
- Hubs created: N
- People created: N ({list})
- People updated: N ({list})
- Concepts upserted: N
- Sensitive entities flagged: N

### Observability counters
- Concept type-conflicts: N (autofix via first-chronological-mention; sustained non-zero → review pipeline)
- Concept translations dropped: N (untranslatable non-English source terms; sustained non-zero → review translation quality)

### Self-Review Stats
- Notes self-reviewed: N
- Fixes applied: N (coverage fix rate: X%)
- MISSED items caught: N
- DISTORTED items corrected: N
- HALLUCINATED items removed: N
- THIN DECISIONS enriched: N
- UNLINKED REVISIONS resolved: N

### Batch Stats
- Batches dispatched: N (each ≤ 250k tokens, ≤ 6 transcripts)
- Max parallel subagents: N (cap = 3)
- File completeness: PASSED ({len(S)} sources enumerated, {len(S)} processed)

### New Entities
- Tags: {list of new tags}
- People: {list of new people with roles}
- Projects: {list of new projects}
- Hubs: {list of new hubs}

### Clarifications Needed: N
{list items from CLARIFICATIONS.md added during this run, if any}

{if N > 0:} Run `/minder:mem:resolve-clarifications` to review interactively when ready.

### Completion Gate
- [x] All transcripts processed
- [x] File completeness invariant passed (all enumerated sources in subagent manifests)
- [x] Self-review (Step 3.7) coverage manifests returned for every transcript
- [x] People profiles created/updated
- [x] Hubs created/updated
- [x] System aggregates updated (TASKS, CALENDAR, HUB_INDEX)
- [x] Identity residue: {N} live
- [x] PROCESSED.md + log_process.md updated
- [x] Batch verification passed
- [x] Evidence Trail present in every new knowledge note
- [x] PEOPLE.md 8-column schema preserved
- [x] Batch artifacts written (batches/{id}-process.md + batches/{id}-process.json + BATCH_LOG row)

### Batch Artifact
- **batch_id:** {YYYYMMDD-HHmmss}
- **Markdown report:** `_system/state/batches/{batch-id}-process.md`
- **JSON manifest:** `_system/state/batches/{batch-id}-process.json` (canonical contract — schema in `_system/docs/manifest-schema/v2.json`, reference doc in `_system/docs/manifest-schema/README.md`)
- **BATCH_LOG:** +1 row (threads_open/close = 0)
- **clarifications_raised:** {N}
- **concepts_upserted:** {N}
- **sensitive_entities:** {N}

### Health Indicators
- Open tasks: {N} (oldest: {date}, {age} ago)
  {if age > 60 days}: ⚠️ Flag for owner review — stale tasks accumulating
- Content candidates: {N} notes with content_potential (high: {N}, medium: {N})
  {if high > 3 and no published in last 30 days}: 💡 Run `/minder:mem:content` to review and draft
- People profiles: {N} total, {N} with empty Контекст section
  {if empty > 5}: 📋 Consider one-time people enrichment pass
```

## Example Usage

```
/minder:mem:process
/minder:mem:process --dry-run
/minder:mem:process --limit all       # drain the whole inbox in one run (supervised manual catch-up; bypasses the default transcript cap)
/minder:mem:process --limit 6         # cap this run to the 6 oldest transcripts
/minder:mem:process --file _sources/inbox/plaud/2026-01-25_meeting/transcript_with_summary.md
/minder:mem:process --reprocess
/minder:mem:process --reprocess-corpus --scope records --dry-run
/minder:mem:process --reprocess-corpus --scope records --corpus-limit 6
/minder:mem:process --reprocess-corpus --scope all
```
