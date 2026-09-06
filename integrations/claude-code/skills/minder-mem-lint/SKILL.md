---
name: minder:mem:lint
description: >
  Nightly slop catcher for Minder Memory. Reads the whole base, autonomously fixes
  the obvious, surfaces the non-obvious as CLARIFICATIONS with rich Context
  paragraphs (self-contained для LLM review session), generates Lint Context
  Store (30-day rolling daily + forever monthly summaries = system memory beyond
  lint). Confidence tier routing (silent/noted/reviewed/surfaced/hidden) via
  rule-floor × LLM-verdict. Dedup = content-merging (not destructive).
  Cross-skill lock awareness symmetric. Best-effort, idempotent, rollback via git.
disable-model-invocation: false
---

# /minder:mem:lint — Nightly Slop Catcher

Autonomous ночной ревизор базы.

**Philosophy:**
- Autonomy-first with audit — lint действует как owner сам бы рефакторил базу
  ночью, но каждое действие логируется с fix-id + rollback via git
- Unified format non-negotiable — все profiles + CLARIFICATIONS в canonical schema
- Dedup = content-merging, not destructive — worst-case wrong merge = related-topic
  content landed в primary, reversible via git revert
- CLARIFICATIONS self-contained — mandatory `**Context:**` paragraph
- Lint Context Store = system memory beyond lint (owner, future agents)
- Best-effort over hard fail — never abort run due to single file anomaly

**Contracts:** `_system/docs/ENGINE_DOCTRINE.md` (operating philosophy
— load first; binding cross-skill rules — F.5 non-personal-origin
guard implements §3.6 owner-LLM contract; lint as «curation-on-promotion»
gate per §3.2),
`_system/docs/SYSTEM_CONFIG.md` (Data & Processing Rules, Profile
template, Log file ownership, Cross-skill exclusion, CLARIFICATIONS
format), `5_meta/PROCESSING_PRINCIPLES.md` (8 principles — slop
detection calibrated against principle 1 Capture First, principle 5
Evolution Tracking, principle 8 Texture).

**Working directory:** the zettelkasten base. Every path in this file — every
`python3 _system/scripts/…` invocation, every `_system/` / `5_meta/` / PARA
reference — is relative to it. The two engine paths that live above the base
(`scripts/lib/`, `scripts/scheduler/`) are reached through
`git rev-parse --show-toplevel`, never through a `../` guess.

**Documentation convention:** при любых edits этого SKILL соблюдай `_system/docs/CONVENTIONS.md` — файл описывает current behavior без version/phase/rename-history narratives.

## Arguments

`$ARGUMENTS` supports:
- `--dry-run` — scan all, report planned actions + diffs for auto-fixes, NO writes
- `--dry-run --verbose` — full diff for every would-be action (auto-fixes + CLARIFICATIONS appends + Lint Context Store generation)
- `--scope fast` — skip expensive scans (dedup + Evidence Trail backfill); use for ad-hoc day-time runs. Default = full
- `--verbose` — include reasoning traces in stdout report (doesn't change scan scope)
- `--force` — bypass «lint ran recently (<6h)» warning
- `--weekly` — force weekly/monthly-gated scan triggers (e.g. Scan F constitution reviews) even if not first run of UTC week
- `--no-sync-check` — skip the data-freshness pre-flight (see below)
- `--rescan-drift [--days N]` — owner-driven historical drift re-scan (Scan F.2 manual path, default `N=30`). Out-of-band: it does not bump the `f2_last_ran_at` marker the nightly auto-path reads

---

## Pre-flight: data freshness (non-blocking)

Multi-device safeguard. If `origin` has commits not yet pulled, lint
on a stale snapshot may produce CLARIFICATIONS that another device
already resolved. Courtesy check, not a gate.

Skip with `--no-sync-check`.

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

- `origin` absent, fetch failed, or `remote_ahead == 0` → silently proceed.
- `remote_ahead > 0` → prompt:
  ```
  ⓘ origin/<branch> ahead by <N> commit(s). Lint on stale data may
    re-surface already-resolved items.

    [s] run /minder:mem:sync-data first  (recommended)
    [c] continue with current local state
    [d] show pending commits
  ```
- `s` → exit 0 with «owner: run `/minder:mem:sync-data`, then re-run `/minder:mem:lint`».
- `c` → proceed; `d` → show log, re-prompt.

---

## Step 0 — Early Exit Check + Cross-Skill Lock Awareness

**FIRST action.** No context load, no work until passed.

### 0.1 Cross-skill lock check (HARD contract — symmetric mutual exclusion)

Read all seven lock files в order:
1. `_sources/.processing.lock` — exists → abort с `"/minder:mem:process running, try again later"`
2. `_sources/.maintain.lock` — exists → abort с `"/minder:mem:maintain running, try again later"`
3. `_sources/.agent-lens.lock` — exists → abort с `"/minder:mem:agent-lens running, try again later"`
4. `_sources/.content.lock` — exists → abort с `"/minder:mem:content running, try again later"`
5. `_sources/.roles.lock` — exists → abort с `"/minder:mem:roles running, try again later"` (a roles tick attributes every diff in its window to the running role; an autofix landing inside it is reverted by `roles_guard.py`)
6. `_sources/.resolve.lock` — exists → abort с `"/minder:mem:resolve-clarifications running, try again later"` (owner is mid-interactive resolve; lint Pass 2 would stomp the resolve session lock at dispatch time)
7. `_sources/.lint.lock` — exists → abort с `"another /minder:mem:lint run in progress"` (unless `--force`)

Stale lock (>2 hours old, parse ISO timestamp from file content) → warn, report PID if present, **offer manual removal, do NOT auto-delete.**

### 0.2 Recent-run check

Read `_system/state/log_lint.md` — last entry timestamp. If < 6 hours ago, report:
```
Lint ran {N} hours ago (last entry: {timestamp}). Pass --force to proceed anyway.
```
Exit unless `--force`.

---

## Step 0.3 — Regenerate Constitution Derived Views

Invoke `/minder:mem:regen-constitution` (or run `python3 _system/scripts/regen_all.py`).
Runs after Early Exit / Recent-run checks so skipped runs do not regenerate,
and before the concurrency lock so a fatal regen failure does not leave a
stray lock file.

Scan F reads the active constitution tree plus the candidate buffer;
Step 2 Context Load reads SOUL.md (which contains the auto-rendered Values
zone). Both require derived views to be fresh relative to `0_constitution/`.

Platform consistency: every pipeline that reads a derived view regenerates
first. Failure is fatal — report the underlying script error and abort the
run before acquiring the lock.

---

## Step 0.5 — Concurrency Lock

Create `_sources/.lint.lock` with content:
```
{ISO UTC timestamp} — lint run, PID {pid}, mode: {full|fast}, args: {$ARGUMENTS}
```

**Finally semantics mandatory:** lock release in every exit path (normal, skip, exception, malformed abort). Wrap Steps 2–9 в try/finally; delete lock in finally. If crashed mid-run, next run detects stale lock + PID absent → safe to remove manually.

---

## Step 2 — Context Load

Load into memory (streamed on-demand where noted):

**Core live state:**
- `_system/SOUL.md` (Focus + Values + Working Style — used by Scan E + monthly SOUL advice)
- `_system/docs/SYSTEM_CONFIG.md` (Data & Processing Rules, Tier thresholds, Profile template, CLARIFICATIONS format contract)
- `_system/registries/CONCEPT_NAMING.md` (concept name format — informational; Scan A.7 enforces via the autonomous helpers in `_system/scripts/_common.py` (`normalize_concept_name`, `normalize_concept_list`). All format issues resolved by silent autofix or silent drop — never raises CLARIFICATION. Fix-ids `concept-format-autofix` / `concept-drop-autofix` / `concept-manifest-autofix` logged in `log_lint.md`)
- `_system/registries/AUDIENCES.md` (audience tag whitelist — Scan A.7 parses `<!-- BEGIN extensions -->` … `<!-- END extensions -->` block, excludes `Status: deprecated:*` rows. Tags failing whitelist (canonical 5 ∪ active extensions) silently dropped via `_common.py::normalize_audience_tag`. Fix-ids `audience-tag-normalise-autofix` / `audience-tag-drop-autofix` / `audience-tag-manifest-autofix`. Engine never coins new extensions; AUDIENCES.md extensions remain owner-curated outside the pipeline)
- `3_resources/people/PEOPLE.md` (all persons, Tier/Mentions/Last — used by Scan C)
- `_system/state/OPEN_THREADS.md` (Active + recent Resolved — used by Scan B)
- `_system/TASKS.md` (Waiting/Action/Delegate sections — thread activity detection)
- `_system/CALENDAR.md` (next 7 + past 7 days)
- `_system/state/CLARIFICATIONS.md` (Open Items + Resolved Items, both in the structured format)
- `_system/state/BATCH_LOG.md` (last 30 days)

**Log files (read-only для activity):**
- `_system/state/log_lint.md` (previous runs, own history)
- `_system/state/log_maintenance.md` (maintain activity signals)
- `_system/state/log_process.md` (process chronological, recent entries)

**Lint Context Store:**
- `_system/state/lint-context/daily/*.md` — last 30 if exist (empty on first run post-bootstrap)
- `_system/state/lint-context/monthly/*.md` — last 3 if exist

**Hubs:**
- `_system/views/HUB_INDEX.md`
- `_system/views/INDEX.md` (A.6 heartbeat input + on-demand catalog reference)
- `5_meta/mocs/*.md` (frontmatter + `## Ключевые выводы` + `## Открытые вопросы` sections — on-demand streamed via glob)

**Streamed on-demand during scans:**
- `_records/meetings/*.md` + `_records/observations/*.md` (Scan A, B, D — both record kinds)
- PARA: `1_projects/**/*.md`, `2_areas/**/*.md`, `3_resources/**/*.md`, `4_archive/**/*.md` (Scan A, D, E)
- `3_resources/people/*.md` profile bodies (Scan C)
- `_sources/processed/**/transcript*.md` (Scan C.4 mention drift — sampled, not full)
- `_system/state/PROCESSED.md` (Scan C.4 baseline)

---

## Step 3 — Scan Pipeline (Scans A–H)

Scans run sequentially (some feed each other: A-fixed links used by B; C-normalized people used by D). Each scan:
1. Collects raw candidates
2. For each candidate → compute rule-floor + run LLM verdict prompt (§Step 3 Confidence Routing below)
3. Route per tier table → add to run worklist (apply-or-clarification)

### Suppression pre-check (applies к all scans before candidate-to-worklist routing)

**Before** adding candidate к worklist as CLARIFICATION, run suppression check:

1. Compute candidate's «suppression key» — deterministic signature:
   - Dedup pair: `dedup:{sorted([primary_id, secondary_id])}`
   - Thread: `thread:{thread-id}`
   - Orphan note: `orphan:{note-id}`
   - Tier demote: `tier-demote:{person-id}`
   - Profile extensions: `profile-extensions:{person-id}`
   - Content pipeline: `content-pipeline` (global key)
   - etc.
2. Scan `_system/state/CLARIFICATIONS.md` `## Resolved Items` for matching `Original-subject` × `Resolution-action` ∈ canonical suppression set (defined in `_system/docs/SYSTEM_CONFIG.md` Data & Processing Rules).
3. If match AND within active suppression window → do NOT add к CLARIFICATIONS worklist. Instead log к `log_lint.md` `### Hidden (verbose audit)` с reason `suppressed-via-resolved` + Resolved Item's `Resolution-date` + suppression window end date.
4. **Semantic-change exception:** if candidate's underlying evidence materially changed post-resolution (dedup similarity Δ >10%, thread gained new back-refs, orphan got inbound link), bypass suppression — re-surface CLARIFICATION с explicit prefix в Context: «⚠ Re-surfaced after `{resolution-action}` on `{date}` — material evidence change: {delta description}».

Suppression applies к ALL scans (A–H) producing surfaced-tier CLARIFICATIONS. Reviewed-tier (apply + validate) CLARIFICATIONS are NOT suppressed — they represent actual changes executed, always reported.

### Scan A — Consistency & Structural

**A.1 Broken wikilinks:**
- Grep all `.md` files for `[[...]]` patterns
- For each link target, check if file exists в expected paths (records, PARA, hubs, people)
- If exact match → OK
- If unique case/whitespace variant exists → `strong` floor, auto-fix candidate (normalize to correct case)
- If 2+ candidates → `weak` floor, CLARIFICATION `link-broken-2plus-candidates`
- If 0 candidates → `weak` floor, CLARIFICATION `link-broken-unresolvable`

**A.2 Frontmatter schema normalization:**
- Iterate all notes/records/hubs/profiles
- Check required keys per layer (record/knowledge/hub/person)
- Missing `modified:` → copy `created:` (`strong` → silent)
- Missing `layer:` → infer from folder path (`strong` → silent)
- Missing `tags:` → empty list `tags: []` (`strong` → silent)
- `tags:` string not list → wrap in list (`strong` → silent)
- Frontmatter invalid YAML → **first attempt deterministic fence repair** via `_common.repair_misplaced_fence(path)`. This fixes the producer corruption where a `## ` body heading (typically `## Evidence Trail` and its `- **date** …` bullet) was written inside the frontmatter fence, captured into the YAML, and broke `yaml.safe_load`. Detection is `_common.frontmatter_closed_before_body(path)` False AND `_common.read_frontmatter(path)` None.
  - Repair returns True → `strong` → silent autofix, fix-id `frontmatter-fence-repair-autofix` logged in `log_lint.md` (same shape as other Scan A fixes).
  - Repair returns False (ambiguous split point) → `weak`, CLARIFICATION `frontmatter-fence-misplaced`.
  - Invalid YAML for any other reason (not a misplaced fence) → `weak`, CLARIFICATION `frontmatter-unfixable-schema`.

**A.3 Duplicate hub bullets:**
- For each hub в `5_meta/mocs/`, scan `## Открытые вопросы` for exact-duplicate bullets (same wikilink + same text)
- Remove duplicates (keep first occurrence), `strong` → silent

**A.4 Duplicate back-refs in frontmatter `threads:` lists:**
- Iterate records/notes, check frontmatter `threads:` list for duplicates
- Remove duplicates, `strong` → silent

**A.5 Orphan files:**
- For each note/record, check if inbound references exist:
  - Mentioned in any hub bullet
  - Mentioned в any thread's Source field
  - Mentioned в any other note's wikilinks
  - Referenced in PROCESSED.md
- Zero inbound → `weak`, CLARIFICATION `orphan-file`

**A.6 INDEX heartbeat:**

Sanity check that `_system/views/INDEX.md` is fresh against the
underlying source layers. INDEX is regenerated by
`_system/scripts/render_index.py` (invoked from `/minder:mem:bootstrap`
Step 5.5, `/minder:mem:maintain` Step 7.6, and `regen_all.py`) — staleness
signals that no regen has run since the last source change, or that a
hand-edit replaced the auto-generated content.

Pipeline:
1. Read `_system/views/INDEX.md` frontmatter `generated:` timestamp.
2. Compute `latest_modified` across all INDEX source layers — knowledge
   (`1_projects/`, `2_areas/`, `3_resources/` excluding registries) +
   archive (`4_archive/` excluding READMEs) + constitution
   (`0_constitution/{axiom,principle,rule}/`) + hubs (`5_meta/mocs/`).
   Max of frontmatter `modified:` (or `created:` fallback). Records
   and posts are intentionally out of INDEX scope and are NOT included
   in this computation.
3. If INDEX missing entirely → `weak` floor, CLARIFICATION
   `index-missing`. To resolve: «run `/minder:mem:maintain` to regenerate».
4. If `INDEX.generated < latest_modified - 7 days` → `weak` floor,
   CLARIFICATION `index-stale`. Subject = «INDEX.md last regenerated
   {date}; newest source entry (knowledge / archive / constitution /
   hub) is {date} ({delta} days drift)». Surfaced tier (never
   auto-apply — INDEX regen happens via maintain / bootstrap /
   regen_all, not lint).
5. If INDEX frontmatter is malformed (missing `generated:` or
   `generator:`) → `weak`, CLARIFICATION `index-frontmatter-malformed`.

The 7-day grace window absorbs the «no maintain run for a few days»
case (e.g. owner travelling) without spamming. Beyond 7 days drift
warrants surfacing — the catalog is materially behind the corpus.

**A.6.1 Task aggregation reconciliation:**

Deterministic backstop for the aggregation silent-drop: `/minder:mem:process`
Step 4.1 aggregates note `- [ ]` items into `TASKS.md` incrementally,
and at scale an autonomous tick can leave tasks un-aggregated. This scan
re-derives the full picture cheaply and surfaces any gap.

Pipeline:
1. Run `python3 _system/scripts/reconcile_tasks.py --base . --report --json`.
   It walks all note roots (`_records` + PARA excluding `4_archive`) for
   open `^task-id` items and diffs against active + Stale ids in `TASKS.md`.
2. If `orphan_count > 0` → `weak` floor, CLARIFICATION
   `task-aggregation-orphans`. Subject = «{orphan_count} task(s) present
   in notes but not aggregated into TASKS.md — run `/minder:mem:process
   --reconcile-tasks` to classify + file them». Surfaced tier (never
   auto-apply — classification Action/Waiting/Delegate is process
   territory, not lint's). Read-only: this scan never writes TASKS.md.
3. `dangling_active_count` (aggregate ids no longer open in any note —
   completion / deletion candidates) is informational only; it feeds the
   existing Stale-candidate flow, not a CLARIFICATION here.

**A.6.2 Hub index completeness:**

Deterministic drift check for `_system/views/HUB_INDEX.md`. The view is
rebuilt by `/minder:mem:maintain` Step 7.11 (`render_hub_index.py`) and appended to by
`/minder:mem:process` §4.3 on hub create — between two maintain runs it can lag the
hub files, and a base whose maintain step keeps failing lags indefinitely.

Pipeline:
1. Count hub files on disk: `5_meta/mocs/hub-*.md` (exclude `*.template.md`).
2. Extract the `[[hub-*]]` ids listed in HUB_INDEX.md.
3. If any on-disk hub is missing from HUB_INDEX → `weak` floor, CLARIFICATION
   `hub-index-incomplete`. Subject = «HUB_INDEX lists {listed} of {on-disk}
   hubs; missing: {ids}». Surfaced tier — `/minder:mem:maintain` regenerates the index
   (owner action), not lint. Read-only.

**A.6.3 Calendar aggregation reconciliation:**

Coarse BEST-EFFORT detector for the calendar silent-drop (the aggregate carries
no stable `^meeting-id`, so per-event keying is not possible). Coverage is partial:
it catches drops of events authored as `- 📅` BODY lines only — events synthesized
from meeting prose have no anchor and are out of reach. Not a completeness guarantee.

Pipeline:
1. Run `python3 _system/scripts/reconcile_calendar.py --base . --report --json`.
   It reports notes with a FUTURE `📅` event whose `[[note-link]]` is absent from
   every forward-facing CALENDAR section (parseable future dates only — fuzzy /
   past dates never flagged).
2. If `orphan_note_count > 0` → `weak` floor, CLARIFICATION
   `calendar-aggregation-orphans`. Subject = «{orphan_note_count} note(s) with a
   future event dropped from CALENDAR — run `/minder:mem:process --reconcile-calendar`».
   Surfaced tier; read-only.

**A.7 Concept and audience-tag format autofix (autonomous, no CLARIFICATIONs):**

Frontmatter and manifest double-check for the privacy + concept fields
emitted by `/minder:mem:process` Steps 3.4 Q15/Q16 and §4.7. Lint is the
post-write **autofix** gate. **The concept layer is fully autonomous —
A.7 raises ZERO CLARIFICATIONs. Every violation is resolved
deterministically by `_system/scripts/lint_concept_audit.py`** (which
delegates to `_system/scripts/_common.py` helpers
`normalize_concept_name` / `normalize_concept_list` /
`normalize_audience_tag`). All fix-ids are `strong` floor (silent
autofix, log entry only).

**Implementation: invoke the python helper.**

```bash
python3 _system/scripts/lint_concept_audit.py \
    --mode {scan|fix} \
    --root .
```

Registries the helper reads: `_system/registries/AUDIENCES.md` (audience
accept-set), `_system/registries/DOMAINS.md` (domain accept-set),
`_system/registries/CONCEPTS.md` (the `Aliases` column, which is the
concept alias map).

- `--mode scan` (default) — emit JSONL events on stdout without
  writing; used for dry-run preview and scan-only diagnostics.
- `--mode fix` — apply changes in place; same JSONL stream on stdout
  for log_lint.md fix-id ingestion.

Each stdout line is one event: `{"fix_id": "<code>", "path": "<file>",
"field": "<concepts|audience_tags>", "raw": "...", "result": "..."}`
(or `"fields_added": [...]` / `"reason": "..."` depending on the
fix). The skill ingests the stream, deduplicates by `(path, fix_id,
raw)`, and records each as a `fix-{run-id}-{seq}` entry under §1
log_lint.md Auto-Fixes — same shape as every other Scan A fix-id.

**Idempotence is the contract.** A second `--mode fix` invocation on
unchanged state produces zero events; the test suite covers this
explicitly (`test_clean_state_zero_events`,
`test_fix_then_rerun_no_events`).

**Conceptual algorithm (the helper enforces this exact pipeline):**

1. **Concept-name autofix — frontmatter.** Iterate every `.md` file
   with frontmatter. For each value in `concepts:`, call
   `normalize_concept_name(raw)`:
   - `raw == result` → OK, no fix.
   - `raw != result` (got back a normalised name) → `strong` floor,
     **silent autofix**, fix-id reason `concept-format-autofix` with
     `{path}` + `{raw}` + `{normalised}` in `log_lint.md`. Frontmatter
     value rewritten in place.
   - `result is None` (cannot normalise — non-ASCII residue,
     bare reserved type-word) → `strong` floor,
     **silent drop** of that entry; fix-id reason `concept-drop-autofix`
     with `{path}` + `{raw}` + reason. The `concepts:` list shrinks;
     other entries preserved.

1b. **Concept-alias rewrite.** Build the alias map from the `Aliases`
   column of `_system/registries/CONCEPTS.md` (each cell lists the
   retired spellings of that row's canonical name). Any `concepts:`
   entry matching an alias → `strong` floor, **silent autofix** to the
   canonical name, fix-id `concept-alias-rewrite-autofix`. Collisions
   dedupe to one entry; an alias claimed by two canonicals keeps the
   first seen. Idempotent — a name already canonical is not an alias.

2. **Concept-name conformance — manifest (by construction, no
   helper needed).** `/minder:mem:process` Step 4.7 and `/minder:mem:maintain` Step
   4 hub linkage both run every concept-name string through
   `normalize_concept_name()` BEFORE writing the manifest JSON.
   Result: manifest concept fields (`concept_hints[]`,
   `member_concepts[]`, `applies_in_concepts[]`,
   `concepts.upserts[].{name,subtype,related_concepts,previous_slugs}`)
   are conformant by construction — the producer-side guarantee
   makes a separate lint-side manifest scan redundant. If a manifest
   non-conformance is ever observed in the wild, that's a bug in the
   producer skill, not a lint-side autofix opportunity. The
   markdown-side autofix (above) is the actual safety net for
   round-trip drift through manual edits.

3. **Audience-tag autofix — frontmatter.** Iterate every `.md` file
   with frontmatter `audience_tags:`. Load AUDIENCES.md and parse the
   Extensions table (rows between `<!-- BEGIN extensions -->` and
   `<!-- END extensions -->`, status NOT `deprecated:*`). Build the
   accept-set = canonical 5 ∪ active extensions. For each tag:
   - In accept-set verbatim → OK, no fix.
   - `normalize_audience_tag(raw)` returns a value that IS in the
     accept-set → `strong` floor, autofix to normalised, fix-id
     `audience-tag-normalise-autofix`. Catches case / punctuation
     drift and reserved-word conflicts (`Family` → `family`).
   - `normalize_audience_tag(raw)` returns a value NOT in accept-set
     OR returns `None` → `strong` floor, **silent drop** of the tag,
     fix-id `audience-tag-drop-autofix`. List collapses to `[]` if
     all entries dropped. Fail-closed: the engine never coins a new
     extension; AUDIENCES.md Extensions remains owner-curated outside
     the pipeline.

3b. **`domains:` whitelist autofix.** Iterate every `.md` file with a
   plural `domains:` field (the singular `domain:` on constitution
   principles is parse-time validated elsewhere and out of scope here —
   the constitution tree is excluded). Accept-set = canonical 13 ∪
   active `_system/registries/DOMAINS.md` extensions. A canonical entry
   passes untouched. A slash-compound (`work/learning`) is split and
   filtered per part; kept parts are rewritten as separate entries →
   `strong` floor, silent autofix, fix-id `domain-normalise-autofix`.
   A part outside the accept-set, an unnormalisable value, a non-string
   entry, or a non-list field → `strong` floor, **silent drop**, fix-id
   `domain-drop-autofix` with the reason (`not-in-whitelist` /
   `format-unfixable` / `non-string entry` / `invalid type`).
   Fail-closed, same policy as audience tags: lint runs the
   deterministic substrate only and never coins a domain. Remapping an
   unmappable value is LLM work and belongs to `/minder:mem:process`.

4. **Manifest audience-tag conformance — by construction.** Same
   producer-side guarantee as concepts. `/minder:mem:process` Step 3.4 Q16
   only emits canonical 5 ∪ AUDIENCES.md active extensions; everything
   else silently drops. The manifest carries pre-validated values; no
   lint-side autofix needed.

5. **Privacy-trio presence autofix.** For every record / knowledge
   note / hub / person profile / project profile, check
   (`origin`, `audience_tags`, `is_sensitive`) present in frontmatter.
   Missing → `strong` floor, **silent autofix** with conservative
   defaults (`origin: personal`, `audience_tags: []`,
   `is_sensitive: false`). Fix-id `privacy-trio-backfill-autofix`.
   No CLARIFICATION; defaults are conservative-safe by construction.

6. **`is_sensitive` type coercion.** Must be boolean. String `"true"`
   / `"True"` → `true`; string `"false"` / `"False"` → `false`. Any
   other non-bool type (int 0/1 → bool; null / list / number / other
   string → coerce to `false` — the safer outcome). All `strong`
   floor autofix, fix-id `is-sensitive-coerce-autofix`. No CLARIFICATION.

7. **`origin` value coercion.** Must be one of `personal | work |
   external`. Any other value or type → coerce to `personal`
   (conservative default), `strong` floor autofix, fix-id
   `origin-coerce-autofix`.

Scope: this scan ignores files where the trio intentionally does not
apply (registries themselves under `_system/registries/`, generated
views under `_system/views/`, raw transcripts under
`_sources/processed/`, append-only audit logs under
`_system/state/log_*.md`, and owner-curated registries SOUL.md /
TASKS.md / CALENDAR.md / POSTS.md — see batch-format.md
"Owner-curated registries" note).

**A.8 Identity consistency — every surface of every registry identity:**

The nightly enforcement of the Identity Contract
(`_system/docs/SYSTEM_CONFIG.md`), which owns the surface roles, the three
surface classes, the five kinds of identity change, the successor-integrity
rule and the exact-match rule.
The project registry (`1_projects/PROJECTS.md`) is the sole existence
authority for the identities in scope; a hub vouches for nothing and is read
only to refine the diagnostic for an identifier the registry does not know.
**Matching is exact identifier equality, never substring** — a longer
identifier that contains a retired one is a different identity and is never
reported as a surface of it.

```bash
python3 _system/scripts/identity_audit.py --root .
python3 _system/scripts/identity_audit.py --report --json --root .
```

Lint runs both, because they answer different questions. The default mode is
the drift event stream over the membership-field axis: array length, plus what
each entry resolves to in the registry. `--report --json` resolves every
declared surface of every registry identity and returns findings carrying
`surface` (`field` / `tag` / `wikilink` / `node-card` / `node-container` /
`hub`), `surface_class` (`live` / `derived`), `action` (`migrate` / `demote` /
`renamespace` / `repoint` / `relocate` / `regenerate`), `current` and `target`.
Lint never passes `--fail-on-residue`, deliberately: a scan that aborts on its
first finding stops scanning, and lint is best-effort by contract — its job is
to see everything and report it. Refusing is the gate's job, and the gates hold
the flag: `/minder:mem:process`'s completion gate and the identity step in CI.

Live findings are migration work; derived findings carry `action: regenerate`
and route to the owning regenerator, never to a text fix; immutable surfaces
are never walked. A **void** identity has no successor by rule, so its
references are frozen where they stand and excluded from the residue check.

**Orphan tags arrive in their own key and are never autofixed.** The report's
`orphans` list holds tags naming an identity no registry declares — they carry
no `action` and no `target` on purpose: registering the identity, retagging the
note and dropping the tag are three different decisions, and nothing in the
scan can tell which one the owner means. Each new orphan is an
`identity-orphan` CLARIFICATION naming the tag and the note. The ones the base
already carried sit in `_system/state/identity-orphan-baseline.txt` and are
absent from `orphans` entirely, so a nightly run reports only what appeared
since — and removing a row there is how a resolved orphan leaves the list.

**Successor resolution is transitive.** The target of any surface naming a
retired identifier is the **terminal live successor** — follow the chain of
retirement rows until an identity that is not itself retired, and write that.
Resolving one hop produces fresh residue on the next nightly run. A chain that
does not terminate is handled by (5) and produces no target at all: the walk
is bounded by the number of registry rows and never revisits an identifier.

1. **Membership-field axis (event stream).**
   - length 0 → ignore; length 1 → OK.
   - length 2 without a boundary annotation in the body — acceptable markers,
     case-insensitive substring: `boundary case`, `cross-project`,
     `joint review`, or a `boundary:` frontmatter field → `weak`,
     `projects-array-2-without-boundary-marker`.
   - length ≥ 3 → `weak`, `projects-array-overcount`. Fix: pick the primary,
     demote the rest to `tags: [project/{slug}]`. (The primary-topic-only
     semantic itself is `5_meta/PROCESSING_PRINCIPLES.md` §9.)
   - entry resolves to a registered **trajectory** → `projects-array-non-project`.
     Fix: drop from `projects:`, carry it as `tags: [trajectory/{slug}]`.
   - entry resolves to a **retired** identifier → `projects-array-consolidated`.
     Fix: replace with the declared successor.
   - entry **absent from the registry** — the hub is consulted for the
     diagnostic only: `hub_kind: project` (or absent) → `projects-array-orphan-hub`;
     other-kind hub → `projects-array-non-project-hub`; no hub →
     `projects-array-unknown-id`. All `weak`: an unregistered identifier has no
     registry answer, so there is nothing deterministic to apply.

2. **Tag surface.** A `{namespace}/{id}` tag whose identifier part matches a
   registry identity but whose namespace contradicts the registry's category →
   `identity-tag-namespace`, target `{expected-namespace}/{id}`. A tag naming a
   retired identifier → `identity-tag-retired`, target
   `{namespace}/{successor}`.

3. **Wikilink surface.** A `[[id]]` — bare, labelled or sectioned — targeting a
   retired identifier → `identity-wikilink-retired`. A link resolving to a node
   this audit marks for relocation → `identity-wikilink-repoint`: the identity
   stays live, only its node moves, so the target is the canonical node
   (resolution order hub → card → container README), not a successor.

4. **Node surfaces.** A node card, node container or hub belonging to a retired
   identifier, or sitting under `1_projects/` while the registry classifies the
   identifier as something else → `identity-node-relocate`, one finding per
   node.

5. **Registry-row integrity — evaluated before the surface walk.** The row is
   the decision; a malformed one makes every surface finding point at nothing,
   so it is judged first, reported **against the registry row** (`Source:` =
   the registry path, `Surface:` = `registry-row`), and it blocks every autofix
   for that identity. One finding per malformed row, never one per reference.

   | Row state | Code |
   |---|---|
   | kind requires a successor (merge, rename) and the cell is empty | `identity-successor-undeclared` |
   | kind forbids one (void) or the count is wrong for its kind (split with fewer than two) | `identity-successor-forbidden` |
   | successor declared but does not resolve to a terminal live identity of the same registry — absent from it, foreign to it, terminating in a void, or on a cycle | `identity-successor-unresolvable`, reason string naming which of the four and printing the chain it walked |
   | `Kind` cell holds a value outside the five the Identity Contract declares | `identity-kind-unknown` |

   Every one of these is `strong` (the rule decides it outright) and none is
   autofixable: the defect is a decision the owner made incompletely, and the
   engine has no way to complete it.

6. **Derived residue.** A derived surface still naming a retired identifier →
   `identity-derived-stale`, fix-suggestion = run the regeneration that owns
   that view. Never a text edit.

7. **Hub-kind agreement.** For every `5_meta/mocs/hub-{id}.md` whose `{id}` is
   a registry identity, the hub's `hub_kind` MUST equal the category the
   registry declares for that row. Disagreement → `identity-hub-kind-mismatch`,
   `Current:` = the hub's value, `Target:` = the registry's category, `strong`,
   never autofixed. Which side is wrong is the owner's call and the answer
   changes what the identity **is**: agreeing by rewriting the hub moves every
   member note between the membership axis and a namespaced tag, which is a
   reclassify, not a repair. A hub whose `{id}` is absent from the registry is
   not a surface of anything and is out of scope here — A.9 reads it as a
   document.

8. **Split surfaces.** A live surface naming an identifier retired with
   `kind: split` → `identity-split-undecided`, `Target:` = «one of
   {successors}», `weak`, never autofixed. Which successor a reference means is
   in the reference, not the registry; the finding exists so the residue is
   counted and walked, not so it can be rewritten.

9. **Retirement provenance.** For every `entity-retire` / `entity-reclassify`
   resolution in `_system/state/CLARIFICATIONS_ARCHIVE.md`, the payload's `gate`
   block must be corroborated by the gate's own record. Raise
   `identity-gate-unproven`, `Subject:` = the entity id, `strong`, never
   autofixed, when any of these holds:
   - the payload lacks a `gate` block, or its `exit_code` is non-zero;
   - the payload's `gate` block carries a `ts` and no line in
     `_system/state/identity-gate.jsonl` matches it on both `identity` == the
     entity id and `ts` — the payload asserts a scan the gate never recorded;
   - such a line matches but disagrees with the payload on `exit_code` or
     `residue_count`.

   The match is the whole point. A payload is written by the same run that did
   the work, so on its own it is the writer's account of itself; the log line is
   written by the gate as a side effect of actually running, and afterwards
   nothing else can distinguish an honest run from a remembered one. Identity
   Contract Obligation 4 makes that recorded per-identity scan part of the
   resolution.

   Forward-only, and `gate.ts` is what makes it so. A resolution archived before
   the gate existed carries a `gate` block with no `ts`, and no log line it
   could ever match — flagging those would fault a base for the shape its own
   engine asked of it at the time. Such a block is judged on presence and exit
   code alone. A matching pair is not flagged either. This scan is a backstop, not the gate: the
   gate lives in `/minder:mem:resolve-clarifications` Class I.5, and the residue itself
   is caught by (1)–(4) regardless of what any payload claims.

**Degradation:** if PROJECTS.md is absent or empty the existence authority is
missing — identity resolution is skipped entirely, so a friend mid-setup is not
flooded. The length check in (1) is registry-independent and still runs.

CLARIFICATION format:

```markdown
### YYYY-MM-DD — {reason-code}: {identity} in {note-id}

**Type:** {reason-code}
**Subject:** {identity}
**Source:** {note-path}
**File path:** {absolute path}
**Surface:** {surface} ({surface_class}) — proposed action: {action}
**Action taken:** none — surfaced for owner review
**Quote:** _(none — frontmatter-level issue)_ | {line excerpt for a body surface}
**Current:** {current}
**Target:** {target or «none declared»}
**Reason:** {the finding's own reason string}
**To resolve:** {specific suggestion for this surface}
```

**Autofix eligibility.** Eligibility is decided per surface and action against
the doctrine's three-property rule for autonomous resolution
(`_system/docs/ENGINE_DOCTRINE.md` §3.1) — deterministic algorithm,
conservative-safe failure, low per-decision value. Only these qualify:

| Finding | Floor | Fix-id |
|---|---|---|
| `projects-array-non-project`, registry-confirmed trajectory, **note is a record** | `medium` | `projects-array-trajectory-demote` |
| `identity-field-retired`, successor declared | `strong` | `identity-field-migrate-autofix` |
| `identity-tag-namespace` | `strong` | `identity-tag-renamespace-autofix` |
| `identity-tag-retired`, successor declared | `strong` | `identity-tag-migrate-autofix` |

**Codes the report emits that the event stream does not.** Item 1 above is the
event stream over `projects:` only, and its `projects-array-*` codes name that
axis by shape. The report walks every registry, so a membership-field finding on
a person cannot borrow a projects-shaped name without lying about what it found:

| Code | What it is |
|---|---|
| `identity-field-retired` | a membership field names a retired identifier |
| `identity-field-non-member` | a membership field names an identity its own category may not occupy |
| `identity-registry-row-duplicate` | one identifier declared twice in a registry |
| `identity-registry-row-unreadable` | a row whose identifier cell cannot be read |
| `identity-registry-section-unknown` | a section heading the registry parser does not recognise — reported rather than defaulted, because a default would read every retired identifier in it as active |
| `identity-surface-unclassified` | a path no classification rule claims; counted as residue, because an unscanned region is how a clean verdict becomes a statement about the scanner rather than about the base |

Each is a metadata rewrite the registry determines exactly, reversible by one
git op, and surfacing it would give the owner nothing to decide.

The record-only qualifier on the first row is load-bearing, not a leftover.
Dropping an identifier from the membership axis **removes** the note from a
derived view; renaming a tag **moves** it within an axis and it stays findable
under the correct name. Removal changes what a knowledge note is retrieved by,
which is the owner's call — so on a knowledge note that one surfaces instead.

Everything else is a CLARIFICATION:

- **wikilink repointing** rewrites prose and the graph — a link inside a
  sentence can be right as a target and false as a claim once repointed;
- **node relocation** depends on what the node *contains*, which no registry
  declares, and is irreversible in the sense that matters;
- **hub-kind changes** reclassify what a hub is;
- **an undeclared successor** leaves no deterministic target at all;
- **unregistered identifiers** and the length checks are judgments the registry
  cannot settle.

**A.9 Hub frontmatter integrity (ARCH-B):**

Validates the ARCH-B hub schema (`hub_kind`, `chronological_map_mode`,
`excluded_from_map`, `excluded_from_map_reasons`).

For each `5_meta/mocs/hub-*.md`:

1. **`hub_kind` value check:**
   - Acceptable values: `project`, `trajectory`, `domain`. Absent
     value defaults to `project` (backward-compat).
   - Any other value → `weak`, CLARIFICATION `hub-kind-unknown`.

2. **`chronological_map_mode` value check:**
   - Acceptable values: `derived`, `curated`. Absent defaults to
     `curated`.
   - Any other value → `weak`, CLARIFICATION
     `hub-chronological-map-mode-unknown`.

3. **Derived-mode marker presence:**
   - When `chronological_map_mode: derived`, body MUST contain both
     `<!-- AUTO-GENERATED by render_hub_maps.py` opening marker AND
     `<!-- /AUTO-GENERATED -->` closing marker.
   - Markers absent → `weak`, CLARIFICATION
     `hub-derived-map-markers-missing`. Fix-suggestion: run
     `python3 _system/scripts/render_hub_maps.py --apply` (covered
     by `/minder:mem:maintain` Step 7.7 on next maintain run).

4. **Excluded-list integrity:**
   - `excluded_from_map` and `excluded_from_map_reasons` arrays must
     have the same length.
   - Each entry in `excluded_from_map` must resolve to a real
     record-id (parseable note in the corpus).
   - Length mismatch → `weak`, CLARIFICATION
     `hub-excluded-arrays-length-mismatch`.
   - Unresolvable record-id → `weak`, CLARIFICATION
     `hub-excluded-id-unresolvable`. Fix-suggestion: drop the entry
     OR check for renamed record.

5. **Trajectory / domain hubs with derived mode:**
   - If `hub_kind` is `trajectory` or `domain` AND
     `chronological_map_mode: derived` — flag as policy violation. A
     derived map is completeness over one primary topic; a trajectory or a
     domain spans several, so its map is curated by intent. Override by
     explicit owner choice if the auto-derivation IS desired.
   - `weak`, CLARIFICATION `hub-trajectory-derived-policy`.

A hub is read here as a document. Whether it is also a *surface* of a
registry identity, or an identity in its own right, is the Identity Contract's
call (`_system/docs/SYSTEM_CONFIG.md`) and A.8's scan — a `hub_kind` change is
never autofixed by either.

A.9 raises CLARIFICATIONs only — no autofix. Every candidate fix here either
regenerates a derived body (owned by `/minder:mem:maintain` Step 7.7) or reclassifies
what a hub is; neither is lint's to apply silently.

Implementation — invoke the helper; JSONL on stdout, one event per finding
(`kind` = the CLARIFICATION type above), exit 0 always:

```bash
python3 _system/scripts/lint_hub_integrity.py --root .
```

**A.10 Portable filename backstop:**

Defence-in-depth behind the two primary gates (`/minder:mem:process` §0.0b
pre-scan, `/minder:mem:save` Step 0.5 pre-pass). Catches non-portable names —
Windows-illegal characters (`< > : " / \ | ? *`, control chars),
trailing dots/spaces, reserved device basenames — that slipped into the
tree, e.g. via a raw `git add` bypassing `/minder:mem:save` or a producer
writing outside inbox. Single SoT:
`_common.py::is_portable_name` / `normalize_portable_name`.

Walk git-tracked paths plus `_sources/inbox/` untracked entries; check
every path segment:

1. **`_sources/inbox/` entries** — rename to the normalised form
   (`strong` floor → silent autofix, fix-id `portable-name-autofix`).
   No references exist yet for unprocessed inbox items, so the rename
   is reference-safe. Collision with an existing name or normalisation
   returning None → `weak`, CLARIFICATION `portable-name-collision`
   (never guess a suffix).
2. **`_sources/processed/` entries listed in PROCESSED.md** —
   grandfathered legacy (pre-portable-convention data, references point
   at them as-is). Skip silently; renaming would break `source:`
   pointers.
3. **Any other non-portable tracked path** (processed entry NOT in
   PROCESSED.md, records, PARA, state) — something escaped both gates
   AND was never registered; an autofix rename here could break
   references the engine can't enumerate cheaply. `weak`, CLARIFICATION
   `portable-name-escape` with the offending path; owner resolves via
   `/minder:mem:resolve-clarifications` (rename + reference rewrite as a
   deliberate, reviewed action).

**A.10a Split-name backstop:**

The same defence-in-depth for the shape portable-name normalisation cannot
see: an inbox item whose producer put a `/` in the recording title, which the
filesystem turned into two nested directories. Both resulting segments are
legal names, so A.10 above finds nothing wrong with either.

```bash
python3 _system/scripts/repair_split_names.py --inbox _sources/inbox --apply --json
```

Backstop behind `/minder:mem:process` §0.0a, same routing as A.10: an unambiguous
join (parent holds exactly one child, and that child is a complete item) is a
silent autofix, fix-id `split-name-autofix` — reference-safe by construction,
because an unprocessed inbox item has no references yet. Every other shape is
`weak`, CLARIFICATION `source-layout-split-name`, item left in place.

A.10 never rewrites references — only inbox renames and rejoins
(reference-free by construction) are autonomous.

**A.11 Content markup canonicalization (content_type drift + missing content_angle):**

The post-write hygiene gate for the content pipeline's preparation layer.
`/minder:mem:process` Q14 constrains its OWN output to the canonical five
(`expert`, `reflection`, `story`, `insight`, `observation`); A.11 heals
**existing** notes and any incoming drift (manual edits, older notes, future
producers) so a drifted `content_type` never silently falls out of content
routing. Scope: every PARA + archive knowledge note carrying
`content_potential` (the routing gate — a drift type on a non-content note is
irrelevant). `story` is canonical and never touched.

**Single SoT for the mapping: `_system/scripts/lint_content_markup.py`
`CANON_MAP`.** The table is defined once, in code; this prose describes the
*method*, not the rows (no drift). Run it from the lint orchestrator:

```bash
python3 _system/scripts/lint_content_markup.py --mode {scan|fix} --root .
```

`--mode scan` emits JSONL events without writing (dry-run preview);
`--mode fix` applies the autonomous tier in place, same JSONL on stdout for
`log_lint.md` fix-id ingestion. Each event:
`{"kind": "content-type|content-angle", "path": ..., "raw": ..., "target": ..., "floor": "strong|weak", "tier_hint": ..., "reason": ...}`.

**Method — each drifted-type candidate carries a floor; the standard §Step 3
Confidence Routing (floor × LLM verdict → tier) decides the rest.** Two
classes of mapping, distinguished in `CANON_MAP`:

- **Synonym rows** (`strong` floor) — the drift value is an unambiguous
  alias for exactly one canonical type (technical / technical-decision /
  practice family → `expert`; `personal` → `reflection`). The declared value
  itself canonicalizes deterministically regardless of body, so this
  qualifies for the doctrine §3.1 autonomous-resolution exception: the helper
  applies the rewrite in place and **prepends an Evidence-Trail note**
  recording `{raw} → {canonical} (content-type-canon-autofix)`. Silent,
  logged, reversible — no CLARIFICATION.
- **Judgment rows** (`weak` floor) — the drift value could map to 2+
  canonical types: a raw `idea` is `insight` when it carries a non-obvious
  angle but `observation` when it is still a lightweight seed;
  `decision` / `principle` / `framework` / `product-insight` are `insight` by
  default but `expert` when the note is established domain knowledge. The
  helper does NOT write; it emits the candidate with the default target. The
  LLM verdict reads the actual note against the canonical definitions →
  `weak × high` (reviewed: apply default + validate-CLARIFICATION) or
  `weak × confident/unsure` (surfaced: no apply, CLARIFICATION carries the
  default + the alternative + a note excerpt so the owner picks with context).
  Never a silent guess on a judgment call (doctrine §3.1).

**Unknown drift value (not in `CANON_MAP`)** — never silently dropped or
guessed. `weak` floor → surfaced CLARIFICATION `content-type-unknown` with the
LLM's suggested canonical mapping; resolving it can optionally extend
`CANON_MAP` (one place). This is the forward-compat guard: a new finer-grained
type a future producer invents surfaces for the owner instead of breaking
content routing silently.

**`content_angle` shape — always a list.** A note whose `content_angle` is a bare
**string** is normalized to a 1-element list deterministically (`strong` floor →
silent autofix, fix-id `content-angle-format`; the scalar is preserved verbatim,
the note's own list indentation matched, only the one line rewritten).
Already-list and block/anchor scalars are left alone.

**Missing `content_angle`** — A.11 only *flags*, never invents. A note with
`content_potential` set but `content_angle` empty/absent is emitted as a
`content-angle` event aggregated into a single surfaced CLARIFICATION
`content-angle-missing` (count + note list). The angle hook ("why would
someone read this?") is content reasoning, not deterministic hygiene — it is
**proposed per-note by the draft-maintainer** (`/minder:mem:content --maintain`) on
its first run and owner-confirmed, never auto-written by lint.

Idempotent: a second run on a healed note is a no-op (its type is now
canonical; its angle, once owner-supplied, is present). Reversible: every
autofix leaves an Evidence-Trail entry; one edit to `CANON_MAP` + re-run
re-heals cleanly.

**A.12 Un-integrated batch backstop:**

The one check that watches a pipeline for **not having run**. Every other scan
reads what a pipeline produced; this one reads the gap where a producer's
output was never consumed.

- Unprocessed set = `BATCH_LOG.md` rows minus the batch ids in
  `log_maintenance.md` — the same computation `/minder:mem:maintain` does in its own
  Early Exit, deliberately, so the two cannot disagree about what «integrated»
  means.
- Surface a `batch-not-integrated` CLARIFICATION when any unprocessed batch is
  **older than 26 h** (the same 24 h + cron/TZ buffer Scan H uses). One
  aggregate item naming every stale batch id and the oldest one's age, never
  one per batch.
- Under 26 h is normal and silent: a batch produced by tonight's tick is
  integrated by that same tick, and one produced minutes before this lint run
  legitimately has not been yet.
- Never autofixed. Lint does not invoke `/minder:mem:maintain` — the two hold
  mutually exclusive locks, and a pipeline that repairs another pipeline's
  omission hides the omission. Lint's job here is to make silence loud.

Why it exists: `/minder:mem:maintain` has no cadence of its own — it runs as Step 4.5
of the process tick and nowhere else, so a tick that skips the step produces a
batch nobody ever integrates and reports success. Threads, hub linkage,
back-references and the weekly biometric / activity workers all stop, and every
individual artefact still looks correct, because what is missing is an event
rather than a file. Nothing in the corpus is wrong; something simply never
happened. That is precisely the shape no content scan can see.

**A.13 Tick telemetry backstop:**

The second check in the A.12 family — it watches for a step that stopped
happening rather than for a file that came out wrong. Every scheduler tick
runs `record_tick_telemetry.py` at its Step 4.9 and appends one line to
`_system/state/tick-telemetry.jsonl` in the same commit as its work. That helper
exits 0 unconditionally, by design, so the tick cannot die of a broken
odometer — which means nothing except this scan notices when the odometer
stops.

- **Ran-but-unmeasured.** Take the tick commits with this exact command —

  ```
  for sha in $(git log --since="26 hours ago" -F --grep='[scheduled]' --format='%H'); do
    git ls-tree -r --name-only "$sha" -- scripts/scheduler/record_tick_telemetry.py \
      | grep -q . || continue
    git show --name-only --format= "$sha" | grep -q 'tick-telemetry\.jsonl' \
      && echo "OK   $sha" || echo "MISS $sha"
  done
  ```

  The `git ls-tree` line is a skip, not a check: it asks whether the
  recorder existed in the tree that tick ran against, and moves on when it did
  not. Without it, the first lint after an engine update reports every tick
  from the preceding day — ticks that ran correctly, before the step existed —
  as un-measured. That is a false alarm on day one for every base, and a check
  whose debut is a wall of wrong findings is not trusted afterwards. Anchoring
  on the feature's own presence also means no grace period, no dated cut-off,
  and nothing to remove later.

  It asks with `ls-tree` rather than the shorter `git cat-file -e "$sha:path"`
  for a reason that costs nothing here and is expensive to debug: in zsh a `:`
  directly after a parameter is read as a history modifier, so that form
  mangles its own argument and fails with `Not a valid object name` — while
  behaving perfectly in bash. The failure lands on the skip branch, meaning
  every commit gets skipped and the scan reports clean forever. A check whose
  shell decides whether it checks anything is worse than no check, so this one
  uses a form with no shell-parsed punctuation in it.

  Two properties of that command are load-bearing, and both fail silently
  rather than loudly when dropped:

  - **`-F`.** Without it `[scheduled]` is a regular expression and `[...]` is
    a character class, so the pattern matches any subject containing one of
    those letters — nearly every commit in the repository. The scan would
    report most of the history as un-measured on its first run, and a check
    that cries wolf immediately is a check the owner learns to skip.
  - **The per-commit `git show`, rather than one `git log --name-only`.**
    Combining `--format` with `--name-only` interleaves subjects and file
    lists with blank-line separators that are easy to mis-parse — and a
    mis-parse here reads as "no telemetry file in this commit", i.e. a false
    alarm on a healthy tick. Asking each commit separately removes the
    parsing step entirely.

  Every `MISS` → one aggregate `telemetry-missing` CLARIFICATION naming the
  tick tags and SHAs, never one item per commit. Name the likeliest cause in
  the item: a scheduled routine whose prompt is a pasted copy of the tick body
  rather than the one-line loader keeps running the instructions it was given,
  so its ticks never reach the recording step. The tick itself looks healthy
  because it is — what is stale is the routine's copy of what to do.
- **Measured-but-empty.** Lines in the window with `status: unmeasured` are
  the same item with a different reason: the step ran and could not find its
  transcript. Carry the line's own `note` — it already says why.
- **Layout drift.** Lines with `layout_check: drift` → a separate
  `telemetry-layout-drift` CLARIFICATION carrying `agent_dispatches` and
  `subagent_files` from the line. The two failures deserve separate items
  because their remedies are unrelated: a missing line means the step did not
  run, drift means the runtime moved its sub-agent transcripts and the parser
  is now undercounting every tick until it is taught the new location.
- Never autofixed, and never by re-running the measurement. A tick's
  transcript lives in the sandbox that produced it and is destroyed minutes
  later, so an absent measurement is gone — there is nothing to recompute,
  and writing a plausible line after the fact would be inventing the number
  the whole mechanism exists to avoid inventing.

**Scoped to ticks on purpose.** A manual `/minder:mem:process` or `/minder:mem:lint` the
owner runs by hand produces no telemetry and must raise nothing: anchoring on
`[scheduled]` commits keeps the scan silent for those without needing to know
anything about how the owner works. The consequence, stated plainly: this
scan proves a tick that ran was measured, and says nothing about a tick that
never fired. That absence is A.12's and `pipeline_health.py`'s job, not this
one's.

**Why the cross-check lives in the tick and not here.** Comparing sub-agent
transcripts on disk against the dispatches recorded in the main transcript
can only be done while those files exist — that is, inside the run. By the
time lint reads the repository, the only surviving evidence is the verdict
the tick wrote down. So the tick judges and lint reads the judgement; a scan
that tried to re-derive it would find no transcript and conclude, wrongly,
that everything is fine.

### Scan B — Thread Lifecycle

**B.1 Stale thread detection per-status:**

Per-status thresholds (warn → escalate):
- `waiting-for-response`: 2 weeks → 5 weeks
- `needs-decision`: 3 weeks → 6 weeks
- `needs-research`: 4 weeks → 8 weeks
- `blocked`: 6 weeks → 10 weeks

Activity detection (reset counter if ANY):
- Thread-id mentioned в last N daily summaries (N = warn-threshold weeks) in Lint Context Store
- Related task moved Done/Cancelled since thread's `Since`
- Back-ref added to record/note with this thread-id (from `log_maintenance.md` entries since last lint run)
- Hub bullet about thread updated
- LLM semantic match — last 7 days records mention thread's topic/people (even without structural back-ref)

If past warn → CLARIFICATION `thread-stale-warn` (**surfaced tier** — no apply per HARD RULE, thread closure manual only).
If past escalate → CLARIFICATION `thread-stale-escalate` (**surfaced tier** — explicit decision required, no apply per HARD RULE).

**Tier note:** thread closure всегда HARD RULE (no auto-apply regardless of signal strength). Surfaced tier matches реальное apply behavior (no apply, user decides). Signal strength передаётся через Context paragraph (prose), не через tier label.

**B.2 Thread-hub linkage backfill:**
- For each Active thread без `hub:` field, search hubs for semantic match:
  - People overlap + topic overlap (LLM semantic judgment)
- If strong match (1 hub, people + topic clear) → `strong` floor, reviewed tier (creates linkage, owner validates)
- If weak match → `weak` floor, surfaced tier `thread-hub-linkage-backfill-surfaced`

**B.3 Orphan CLARIFICATIONS escalation:**
- For each Open Item > 3 weeks old → CLARIFICATION `orphan-clarification-escalate` (surfaced tier)
- For each Resolved Item with `Applied: no` > 2 weeks old → CLARIFICATION `applied-pending` (surfaced tier)

### Scan C — People Lifecycle

**C.1 Auto Tier 2→1 profile generation** — dual-apply semantics:
- Iterate PEOPLE.md — find persons с mentions ≥ 8 AND no existing profile file в `3_resources/people/`
- For each crossing candidate:
  - Recent records где person в `people:` frontmatter (top 3–5)
  - LLM infer: role, org, tags
  - Generate canonical profile (reviewed tier apply):
    - Frontmatter: id, name, role, org, tags
    - `# {Name}` heading
    - `**Role:** {role summary}`
    - `## Контекст` — LLM 2–3 sentences from recent records
    - `## Мои наблюдения` — placeholder `_(заполняется вручную)_`
    - `## Упоминания` — top 10 wikilinks chronological
  - PEOPLE.md Tier column update — **HARD RULE blocks auto-apply** (via `/minder:mem:resolve-clarifications`)

**Dual-apply CLARIFICATION format `tier-promote-auto-profile`:**

```markdown
**Applied sub-actions:**
- profile-file-created: yes (fix-id: lint-{id}-profile-create-{seq})
- people-md-tier-updated: no (HARD RULE — via `/minder:mem:resolve-clarifications`)
```

One CLARIFICATION carries both sub-actions с explicit status. Reader parses sub-action table for exact apply state per component.

Floor `strong` (threshold deterministically crossed) + LLM high verdict → profile creation tier `reviewed` (file created, validate requested) + tier column update `surfaced` (blocked by HARD RULE).

**C.2 Tier demote candidates:**
- Find persons с current Tier 1 BUT no profile AND mentions dropped < threshold OR no activity в last 60 days
- `strong` floor (deterministic condition) + LLM verdict → always surfaced tier (never apply tier changes per HARD RULE)
- CLARIFICATION `tier-demote-candidate`

**C.3 Orphan bare-name resolution:**

Resolving a bare name to a person-id is an identity change of the `rename`
kind, so it is atomic across live surfaces and leaves zero residue per the
Identity Contract (`_system/docs/SYSTEM_CONFIG.md`). The person registry
declares three live surfaces:

1. **Frontmatter `people:` array entries** matching bare-name pattern (no `-lastname`)
2. **Frontmatter `tags:` array entries** matching `person/{bare-name}` pattern
3. **Body inline wikilinks** `[[{bare-name}]]` — these point к non-existent files (broken wikilinks) until fixed

What is C.3's own, and needs judgment, is the resolution itself:

- Grep all three surfaces across entire Minder Memory base
- LLM semantic resolution: bare name → candidate person-id using SOUL + PEOPLE + recent records
- If unambiguous (single `{bare}-*` candidate in PEOPLE.md) + LLM high verdict → `reviewed` tier (apply ALL three surfaces + validate via CLARIFICATION)
- If multiple candidates → surfaced tier `orphan-bare-name-surfaced` с per-file disambiguation

**Apply logic:**
- For each file containing bare name at any surface:
  - Frontmatter `people:` → replace bare с full-id
  - Frontmatter `tags:` person/{bare} → person/{full-id}
  - Body `[[{bare}]]` → `[[{full-id}]]`
- Each surface = separate fix-id with qualifier `bare-name-resolve-frontmatter` / `bare-name-resolve-tag` / `bare-name-resolve-wikilink`
- Residue check per resolved name at the Completion Gate. Non-zero → abort fix (surface) + raise surfaced CLARIFICATION for remaining occurrences.

**CLARIFICATION for reviewed-tier apply:**
Aggregated per resolved name с explicit sub-surface counts:

```markdown
**Applied sub-actions:**
- frontmatter-people: {N} refs (fix-ids {range})
- frontmatter-tags: {N} refs (fix-ids {range})
- body-wikilinks: {N} refs (fix-ids {range})
- total: {T} fixes across {F} files
```

User validates via `git diff` + `grep "operation:bare-name-resolve" _system/state/log_lint.md`.

**C.4 Mention count drift:**
- For each person в PEOPLE.md, recount mentions by scanning all notes/records frontmatter `people:` lists
- If counted != PEOPLE.md `Mentions` column → drift detected
- If drift direction makes semantic sense (note deletion for decrement) → `strong` floor + LLM high → silent tier auto-fix (update Mentions column)
- NOTE: this is exception to «never write PEOPLE.md Mentions» — Mentions column is derived data; silent correction of drift is integrity fix, not process territory. BUT: if ambiguous direction, surfaced tier `mention-count-drift-surfaced`

**C.5 People candidates aggregation (weekly — first lint run of UTC week).**

Gate: current UTC weekday = Monday AND no previous `log_lint.md` entry this week fired C.5. Mirrors the F.3 cadence for `principle-candidates`.

Purpose: reduce friction from one-off bare-name mentions. `/minder:mem:process` Step 3.8 routes AMBIGUOUS bare names to `_system/state/people-candidates.jsonl` instead of raising a CLARIFICATION per mention. This sub-scan aggregates the buffer weekly and promotes only recurring / information-rich candidates to the resolution queue.

Pipeline:

1. **Read buffer.** Load all entries from `_system/state/people-candidates.jsonl`. If empty → skip (no CLARIFICATION, no archive).

2. **Aggregate by name.** Group entries by `slugify(name_as_transcribed)` (Cyrillic transliteration + lowercase). For each group, compute:
   - `mention_count` = number of distinct `(date, note_id)` pairs in group (double-mentions in same transcript collapse — 1-per-file consistent with PEOPLE.md rule)
   - `first_seen` = earliest `date`; `last_seen` = latest `date`
   - `sources` = deduplicated list of `source` paths
   - `notes` = deduplicated list of `note_id`
   - `role_hints` = deduplicated non-null `role_hint` values
   - `suggested_ids` = deduplicated non-null `suggested_id` values
   - `any_high_importance` = logical OR of `high_importance_hint` across group
   - `age_days` = today - first_seen

3. **Promotion rules (evaluate per group, first match wins).**
   - **R1 — High importance.** If `any_high_importance` AND no CLARIFICATION was already raised at process-time for this group → promote.
   - **R2 — Recurrence.** If `mention_count ≥ 2` → promote.
   - **R3 — Strong context.** If `mention_count == 1` AND (at least one `role_hint` is non-empty AND at least one `related_people` array is non-empty AND `len(quote) ≥ 120` chars) → promote. Rationale: single mention with full role + contextual anchor + substantial quote has enough info for the user to decide without re-reading the transcript.
   - **R4 — Stale dismiss.** If `mention_count < 2` AND `age_days ≥ 90` → auto-dismiss. Move all entries of this group to `_system/state/lint-context/weekly/{YYYY-WW}-people-candidates-dismissed.jsonl` with an appended `dismissal_reason: "stale-single-mention-90d"` field. Do NOT emit a CLARIFICATION — the archive line is the audit trail.
   - **R5 — Hold.** Otherwise, leave in buffer for future weeks.

4. **Emit aggregated CLARIFICATION (one per promoted group).**

   ```markdown
   ### YYYY-MM-DD — people-candidate-promoted: «{name_as_transcribed}» ({mention_count}× mentions, first {first_seen} → last {last_seen})

   **Type:** people-bare-name
   **Subject:** {name_as_transcribed}
   **Source:** aggregated from {N} mentions in buffer (see archive path below)
   **Suggested action:** resolve-bare-name | create-profile | dismiss
   **Confidence tier:** surfaced

   **Promotion rule:** R{1|2|3}

   **Aggregated quotes:**
   {for each entry in group, rendered inline:}
   - {date} — [[{note_id}]] — > «{quote}»
     - role_hint: {role_hint or —}
     - related: {related_people joined or —}
     - suggested_id: {suggested_id or —}

   **Candidates in PEOPLE.md (fuzzy match on name_as_transcribed prefix):** {list or «none»}

   **To resolve:** pick one of:
     (a) create profile `{id}` in `3_resources/people/` + add PEOPLE.md row + update backlinks in each listed note_id;
     (b) map to existing `{id}` (add alias) + backfill `people:` frontmatter in each note_id;
     (c) dismiss (external/one-off) — confirm no profile needed.

   **Archive reference:** `_system/state/lint-context/weekly/{YYYY-WW}-people-candidates-archived.jsonl`
   ```

   Include `high_importance_hint: true` inline on the CLARIFICATION when R1 fires so the reader knows process flagged it but deferred the full CLARIFICATION to this aggregation.

5. **Archive + verify + clear (atomic).** After ALL promoted CLARIFICATIONS are rendered AND all dismissed entries written:
   ```bash
   python3 _system/scripts/archive_buffer.py \
     --buffer _system/state/people-candidates.jsonl \
     --archive-dir _system/state/lint-context/weekly
   ```
   The script derives the archive name from the buffer's filename stem
   (`people-candidates.jsonl` → `{YYYY-WW}-people-candidates-archived.jsonl`),
   so the same helper serves C.5 and F.3. **R5 (held) entries** must be
   preserved — re-write them back to the buffer after archive (the hold-subset
   write is the final step; the script clears the buffer, it does not
   re-populate it).

6. **Exit code 2 from archive → `lint-archive-failure` CLARIFICATION** with stderr message; buffer is NOT cleared so data persists for next week's retry.

**Invariants:**
- Never silent-delete a candidate. Dismissals go to the weekly dismissed archive with explicit `dismissal_reason`.
- Buffer line count before run == Promoted + Dismissed + Held + Archive-failed (conservation law; checked at Completion Gate).
- `mention_count` aggregation is deterministic (unique `(date, note_id)` pairs) — same buffer produces same promotions across re-runs, idempotent if buffer unchanged.
- Fuzzy-match на Cyrillic-variants (e.g. «Антон» ≠ «Антоша» ≠ «Антоха» but same person) is OUT OF SCOPE for this version — each variant is its own group. If the user resolves a group and knows it's an alias of another, they record the alias manually in PEOPLE.md and the next week's R4 cleanup handles stale variants.

### Scan D — Note Lifecycle

**D.1 Dedup scan (content-merging, not destructive):**

Pairs similarity check (expensive — N² for ~400 notes = 80K pairs; sample pre-filter by frontmatter overlap first):
1. **Pre-filter:** pairs с ≥ 2 common `tags` + same `layer` + similar `type` → candidate pool
2. **Similarity scoring** per candidate pair:
   - Title similarity (normalized Levenshtein) × 20%
   - Body semantic similarity (LLM judgment 0–100) × 40%
   - Frontmatter overlap (tags, people, projects union count / total) × 40%
3. Combined score ≥ 90% → strong floor; 75–90% → weak floor; < 75% → skip
4. For tier-routed candidates:
   - **Primary selection** — completeness score:
     - Frontmatter fields filled: +1 each (id, created, modified, tags, people, projects)
     - Evidence Trail present: +3
     - Hub linkage: +2
     - Content length: +1 per 100 words capped at 5
     - Age (oldest): +1
     - Tie-breaker: oldest `created:` → alphabetical id ascending
   - **Unique content extraction** — LLM reads secondary body, identifies content NOT in primary
   - **Merge:**
     - Frontmatter union (tags/people/projects)
     - `modified: {today}`
     - Body: append unique bullets в matching primary sections; add new sections если secondary имеет не-existing
     - `## Evidence Trail`: prepend entry `{today}: merged content from deduplicated note [[secondary-id]]`
   - **Secondary treatment:**
     - `silent` / `noted`: delete secondary file + update PROCESSED.md source pointers → primary + **backlink redirect** (see below)
     - `reviewed`: keep secondary, frontmatter `status: merged-into, merged_into: {primary-id}, modified: today`, CLARIFICATION `dedup-reviewed`
     - `surfaced`: no changes, CLARIFICATION `dedup-surfaced`

5. **Backlink redirect (mandatory for silent/noted merge with delete):**
   - Grep all `.md` files for `[[{secondary-id}]]` content wikilinks
   - Skip audit files: `_system/state/log_lint.md`, `_system/state/CLARIFICATIONS.md ## Resolved Items`, primary note's `## Evidence Trail`
   - Rewrite elsewhere `[[{secondary-id}]]` → `[[{primary-id}]]`, silent tier per-fix
   - Also grep tags `person/{secondary-id}` (rare — applies only if dedup target was profile)
   - Log each as fix-id с qualifier `dedup-backlink-redirect`
   - **Completion Gate check:** post-merge grep `[[{deleted-id}]]` in non-audit files → must return 0

**D.2 Evidence Trail backfill** — two modes:

**Mode A: Template-only backfill (silent tier):**
Conditions (all must hold):
- Knowledge note has `source:` frontmatter pointing к valid transcript path
- Note missing `## Evidence Trail` section
- Task = insert 1-line shell entry: `{created date}: original insight captured — source: \`{source basename}\` (backfilled retroactively)`

This is **deterministic schema completion** — no LLM semantic reasoning, just known-data template. Strong floor + trivial verdict → **silent tier OK**. Treat identical to frontmatter schema normalization (Scan A).

**Mode B: Semantic reconstruction (reviewed floor):**
Conditions (used when Mode A insufficient, e.g. Owner wants richer trail):
- LLM reads source transcript + current note body → reconstructs nuanced trail entries pointing к specific insights derived
- Creates narrative evidence chain, not just template pointer
- Floor `weak` (semantic reasoning carries burden) → **reviewed tier minimum**
- CLARIFICATION `evidence-trail-backfill-surfaced` для cases где source не accessible или LLM uncertain

Initial bulk backfill для legacy notes uses **Mode A** (template pointers). Mode B reserved для opt-in deep enrichment runs.

**D.3 Orphan notes:**
- For each knowledge note, check inbound references (hubs, records, threads, other notes' wikilinks)
- Zero inbound → surfaced tier `orphan-note` (archive candidate)

**D.4 Stale hub vs fresh material:**

Detects the specific failure mode of evolution-tracking discipline
(Principle 5: accumulate, don't deduplicate): material accumulates
under a hub, but the hub's «Текущее понимание» / synthesis sections are
not refreshed. The hub becomes a stale index of fresh content.

Hub-level scan, runs daily. Mechanical date arithmetic — no LLM
reasoning at the detection step (LLM may judge later in the worklist).

Pipeline:
1. For each hub in `5_meta/mocs/*.md`:
   - `hub_modified` = frontmatter `modified:` (fallback `created:`)
   - **Underlying material** = knowledge notes connected to the hub
     by a **wikilink in either direction**:
     - Note body contains `[[hub-id]]` (grep across PARA `.md`), OR
     - Hub body contains `[[note-id]]` (typically inside the hub's
       «Хронологическая карта» section)
   - **`domains:` overlap is NOT used as a primary connection
     signal** — it is too coarse on project-themed hubs (e.g.
     `domains: [work]` matches every work-domain note). The
     wikilink contract is what hubs maintain by design.
   - `latest_underlying = max(modified)` across underlying notes;
     `fresh_count = count(notes where modified > hub_modified)`.
   - **Edge case:** if a hub has zero underlying material — skip the
     hub entirely. Zero underlying ≠ stale hub; orphan-hub detection
     (no inbound + no outbound wikilinks) is a separate concern,
     handled implicitly via Scan A.5 `orphan-file` if applicable.
2. If `latest_underlying - hub_modified > 60 days` AND `fresh_count ≥ 2`
   → `weak` floor (deterministic threshold) + LLM verdict against the
   hub body itself (does «Текущее понимание» reference the new material
   or not?) → **always surfaced tier** (synthesis layer, never auto-
   apply — owner judgement required regardless of LLM confidence).
3. CLARIFICATION `hub-stale-vs-material`. Subject = «{hub-id} last
   updated {date}; {fresh_count} newer notes accumulated, latest
   {latest_date} ({delta} days)». Quote = first 3 freshest underlying
   note ids inline (helps owner skim what's new).
4. **Suggested action vocabulary** (canonical, see
   `_system/docs/SYSTEM_CONFIG.md` Resolution-action table):
   `update-hub-synthesis` / `split-hub` / `archive-hub` / `dismiss`
   (with `reason: noise | not-actionable`).
5. **Suppression key:** `hub-stale:{hub-id}`. Once resolved (any
   action taken), suppress re-surfacing for 30 days unless additional
   `≥ 2` freshness deltas land in that window (semantic-change
   exception per Suppression pre-check).

Why surfaced-only:
- Hubs are the synthesis layer (Layer 3 in CONCEPT.md). Auto-rewriting
  «Текущее понимание» is exactly what HARD RULE forbids — the synthesis
  carries owner's interpretation, not a derivable summary.
- This complements `cross-domain-bridge` lens (discovery of *new*
  bridges) and lens `knowledge-emergence` (promotion knowledge → hub).
  D.4 covers maintenance of *existing* hubs against their material.

### Scan E — Focus

**E.1 SOUL focus drift (daily scan):**
- Load SOUL.md Focus (Work + Personal)
- Aggregate themes from last 7–14 days daily summaries (or records if Lint Context Store thin)
- LLM rubric: identify themes в activity absent from Focus, Focus items с 0 activity, emerging patterns
- Output: prose assessment (3–5 sentences) + specific observations
- Always surfaced tier `soul-focus-drift` (SOUL never auto-edit — HARD RULE)

Content surfacing lives outside lint: the draft-maintainer
(`/minder:mem:content --maintain`) self-surfaces "what changed this week" on its own
weekly tick, and Scan A.11 owns content-markup hygiene. Scan E covers SOUL
focus only.

---

### Scan F — Constitution Alignment

Health + maintenance of the `0_constitution/` layer. Eight sub-scans with
explicit cadences; daily scans run every invocation, weekly and monthly
scans gate on first lint run of the UTC week / month. Scan F never edits
principle body content (L1 write limit — see `0_constitution/CONSTITUTION.md`
§8); it only appends to Evidence Trail (on F.5 auto-merge) and surfaces
CLARIFICATIONS.

Input across the whole scan: walk `0_constitution/`, load
`_system/state/principle-candidates.jsonl`, consult recent `_records/` for drift
context.

#### F.1 — Stale principles (daily)

For each principle where `last_reviewed` is older than 180 days: raise a
CLARIFICATION `principle-stale` with subject=principle.title,
Quote=principle.statement, Uncertainty="Last reviewed {date}; > 180 days
old", To resolve="confirm still applicable / rephrase / deprecate".

#### F.2 — Historical drift re-scan (manual + auto-on-constitution-edit)

Two trigger paths, identical per-record logic:

**Manual path** — `/minder:mem:lint --rescan-drift --days N` (default N=30).
Owner-driven, used after explicit retroactive principle edits or on
demand. `--days` is honoured verbatim.

**Auto path** — fires inside the normal nightly tick (no flag needed)
when the constitution tree has changed since the last lint run that
fired F.2. Detection:

1. Read `_system/state/log_lint.md` frontmatter for the most recent
   `f2_last_ran_at` ISO-Z timestamp.
   - **Absent.** Bootstrap silently: write `f2_last_ran_at:
     <run-start-ts>` and skip F.2 for this tick. Rationale: a missing
     marker means no prior tick has populated it; historical commits
     in `0_constitution/` predate any incremental signal the owner is
     watching for. A retroactive rescan on bootstrap would surface
     drift CLARIFICATIONS for changes the owner has already lived with
     — noise, not signal. Next tick the marker exists and normal
     incremental detection applies.
   - **Present.** Use it as the `--since` timestamp.
2. Run `git log --since="${f2_last_ran_at}" --name-only --pretty=format: -- 0_constitution/{axiom,principle,rule}/`.
   Filter out paths matching `*/CONSTITUTION.md` (protocol spec, not a
   principle body) and any path under `0_constitution/_archived/`.
3. If the filtered set is empty → skip F.2 (no auto-trigger).
4. Otherwise, derive `days = max(30, ceil((now - oldest_change_ts) / 86400))`
   so the rescan window covers every decision record written under the
   pre-edit tree, capped at a per-run ceiling of 90 days to bound cost.
   Owner can still run the manual path with a larger `--days` after.

The rescan window override **never shrinks** below the user-supplied
`--days N` when both paths fire in the same invocation: `effective_days
= max(N, derived_days)`.

Per-record logic — same as `/minder:mem:process` Step 3.7.5 but emits
CLARIFICATIONS of type `principle-drift-retro` (distinct from daily
`principle-drift`) so the user can tell historical rescans apart from
live checks. Pass `--from-pipeline /minder:mem:lint` to `/minder:mem:check-decision`
for `caller_class: mechanical` accounting (skips per-record auto-commit
on the telemetry JSONL — lint's own commit at Step 7 picks up the
batch).

After the per-record loop completes (auto path only), update
`log_lint.md` frontmatter with `f2_last_ran_at: <run-start-ts>` so the
next nightly tick sees a fresh marker. Manual `--rescan-drift` runs do
NOT bump this marker — they are out-of-band and would suppress the
next legitimate auto-trigger if they did.

**Cost / latency note.** The auto path is silent on weeks where the
owner did not edit the constitution — no Opus calls beyond F.5's
existing usage. On weeks with one edit, expected window is 30 days ×
typical decision density (≤ 5–10 records). Bounded.

**Invariants:**

- Never edit principle bodies. Same L1 write limit as F.5.
- Best-effort heavy-fixes guard. If the record's originating batch
  manifest at `_system/state/batches/{batch_id}.json` is reachable
  AND shows the per-record entry has `fixes_applied >= 3` OR any
  HALLUCINATED fix → skip (mirrors `/minder:mem:process` Step 3.7.5
  exclusion). When the manifest is unreachable (rotated, pre-engine,
  malformed) → proceed without exclusion. The retroactive nature of
  F.2 means perfect parity with Step 3.7.5 is not enforceable; the
  `principle-drift-retro` type itself signals «historical re-check»
  semantics to the owner.
- On `/minder:mem:check-decision` error (empty visible tree, transient
  failure) → log to `log_lint.md` and continue; never block the lint
  run.

#### F.3 — Candidate aggregation (weekly — first lint run of UTC week)

Gate: current UTC weekday = Monday AND no previous log_lint.md entry this
week fired F.3.

Pipeline:
1. Read `_system/state/principle-candidates.jsonl`. If empty → skip.
2. Render ONE CLARIFICATION `principle-candidate-batch` with **all
   candidates inline** (not by reference to the jsonl — entries must stay
   readable if the file rotates). Per candidate render EVERY field that helps
   the owner judge without re-reading the source: situation, observation (the
   verbatim quote), hypothesis, `brief_reasoning` (falsifier + alternative
   reading + record count, when present), suggested_type, suggested_domain,
   `dimension` (cognitive-model axis slug, if present), origin, session_id,
   record_ref, date captured.

   **Promotion outcomes — the owner's review must land somewhere (this is the
   help, so nothing he decides is lost):** for each candidate the owner's
   verdict routes to one of —
   - **Promote → new principle:** author it; if it carries a `dimension`, set
     `cognitive_axes: [{dimension}]` AND `source_quote: {observation}` (the
     DEC-3 anchor); then make the **hot-reach decision** — does this change how
     an assistant should engage the owner day-to-day? If yes, weigh `core: true`
     (it reaches actors via `constitution_core_view`; budget is 5–8) or fold the
     rail into SOUL `Context for Agents`; if it only matters to the owner's own
     pipelines, leave non-core.
   - **Sharpen existing principle:** the candidate makes a vague principle
     specific/conditional → refine that principle's statement; carry
     `cognitive_axes`/`source_quote` if missing.
   - **Reject / not-a-principle:** record the owner's reason inline (his
     reflection IS the audit), candidate stays in the archived jsonl.
   - **Defer:** keep for a later batch.
   The owner's free-text reflection on a candidate is itself signal — when it
   sharpens or contradicts an existing principle, treat it as a new observation
   (it can seed the next candidate or an Evidence-Trail entry), so the model
   actualizes from his feedback, not only from the lens.
3. **Archive + verify + clear** — invoke:
   ```bash
   python3 _system/scripts/archive_buffer.py
   ```
   The script copies the buffer to
   `_system/state/lint-context/weekly/{YYYY-WW}-principle-candidates-archived.jsonl`,
   re-reads the archive, verifies line count matches, then clears the
   buffer. Exit code 2 = verify failed → raise CLARIFICATION
   `lint-archive-failure` with stderr message as body; **buffer is not
   cleared** on failure so candidates persist for next week's retry.
4. The aggregate CLARIFICATION references the archive path
   (`_system/state/lint-context/weekly/{YYYY-WW}-principle-candidates-archived.jsonl`)
   so the user can trace each candidate from the CLARIFICATION back to
   the raw buffer entry.

Never silent-delete a candidate. If owner rejects one on review, he writes
the rejection outcome inline in the resolved CLARIFICATION — the
archived jsonl stays forever as audit trail.

#### F.4 — Health metrics (monthly — first lint run of UTC month)

Gate: current UTC day = 1 AND no previous log_lint.md entry this month
fired F.4.

Append a block to `_system/state/lint-context/monthly/{YYYY-MM}.md` under a
dedicated `## Constitution` section:

```
## Constitution ({YYYY-MM})
- Active principles: {N}
  - axioms: {N} · principles: {N} · rules: {N}
- Core (core=true, non-placeholder): {N} (watch: surfaces F.6 if > 10)
- Archived this month: {N}
- Stale surfaced this month (F.1): {N}
- Candidates surfaced: {N_total} → accepted {N_accepted} / rejected {N_rejected} / deferred {N_deferred}
- Auto-merges performed (F.5): {exact: N, llm: N}
- Cognitive-model axes: {P} promoted / {B} blank{ — blank: {blank list} if B>0}
- Evidence Trail compactions (F.7 approved): {N}
- Most-cited principles (top 3 by Evidence Trail length): {id1}, {id2}, {id3}
- Most-contradicted (top 3 by citation-violated count, if any): ...
```

Numbers come from this month's log_lint.md entries + a tree walk at
write time. The cognitive-model axes line comes from
`python3 _system/scripts/render_cognitive_model_hub.py --stats` (reads
constitution state, prints `{status_counts, blank_axes}`, never touches the
hub file). This is information for owner's review, not a trigger for
automation — a long-blank axis is a coverage gap to fill, not an error. It is
also the low-noise reconciliation surface for the owner-gated promotion step:
if a cognitive-model candidate was promoted but its principle was never tagged
with `cognitive_axes`, the affected axis simply shows here as still blank (or
under-linked), surfaced monthly without per-candidate nagging.

#### F.5 — LLM-judge merge (daily, L2 write)

Input: `principle-candidates.jsonl` + visible active principles (via
`query_constitution.py`).

**Level 1 — exact match (no LLM).** For each candidate, normalise its
`hypothesis` + `observation` (lowercase, strip punctuation, collapse
whitespace). Compare against each active principle's normalised
`statement`. On equality: append Evidence Trail entry to the active
principle (`automerge-exact` event type, reference the candidate record),
**propagate the candidate's `applies_in_concepts[]` to the principle
frontmatter** (set-union with existing, then
`_common.py::normalize_concept_list()` to dedupe/sanitise; write back),
**and propagate the candidate's `dimension` (if present) into the
principle's `cognitive_axes:`** (set-union with existing, default `[]`;
write back — this keeps `hub-cognitive-model` promoting the right axis when
a cognitive-model candidate merges into an existing principle).
**If the target principle has no `source_quote:` yet, set it from the
candidate's `observation`** (the verbatim grounding quote — the DEC-3 anchor;
never overwrite an existing one).
Then remove the candidate from the buffer, raise CLARIFICATION
`principle-automerge-exact` (info-only). When the `cognitive_axes` set-union
or `source_quote` actually changed the principle, name it in the CLARIFICATION
«Action taken» line (`cognitive_axes: {old} → {new}`; `source_quote: set`) so
the field change is directly auditable, not only inferable from the candidate.

**Level 2 — Opus LLM-judge (for everything not resolved by Level 1).**
Invoke reasoning LLM with prompt:

> Candidate: `{content}`
> Active principles in overlapping domains: `{list}`
> Is the candidate:
>   (a) a semantic duplicate of one of the principles (same meaning,
>       different wording)?
>   (b) an edge-case / extension of one principle (adds context without
>       contradicting)?
>   (c) a new independent principle?
>   (d) noise / non-principle (stylistic / emotional reaction without
>       rule-content)?
> Return JSON `{verdict, target_principle_id, confidence, reasoning}`.

- `(a) confidence > 0.8` → automerge as in Level 1, CLARIFICATION
  `principle-automerge-llm` (info, with LLM reasoning preserved).
  **Propagate `applies_in_concepts[]` from the candidate buffer entry
  to the target principle's frontmatter:** read existing
  `applies_in_concepts:` (default `[]`), set-union with the candidate's
  `applies_in_concepts[]`, run the result through
  `_common.py::normalize_concept_list()` to dedupe and sanitise, write
  back. Never raises — autonomous propagation under the same concept-
  layer policy as A.7. **Also set-union the candidate's `dimension` (if
  present) into the target's `cognitive_axes:`, and — if the target has no
  `source_quote:` yet — set it from the candidate's `observation`** (the
  DEC-3 anchor; never overwrite an existing one), same write boundary, so
  the cognitive-model hub promotes the merged axis.
- `(b) confidence > 0.8` → add candidate to the target principle's
  `## Related` section as an edge-case reference. CLARIFICATION
  `principle-extended-llm` (info, owner may override). Same
  `applies_in_concepts[]`, `dimension → cognitive_axes`, and
  `source_quote` (set-if-missing) propagation rules as (a).
- `(c)` or low-confidence → candidate stays in buffer for F.3 weekly
  aggregate.
- `(d) confidence > 0.9` → tag candidate as suggested-noise in the
  buffer (add `"suggested_noise": true` to the jsonl entry); F.3 surfaces
  these in a distinct section for explicit owner confirmation. Never
  silent-discard.

**Scope-mismatch guard.** If a candidate and a matching active principle
differ in `scope` (e.g. candidate is `personal`, principle is `shared`),
do not automerge. Raise CLARIFICATION `principle-automerge-scope-mismatch`
so owner resolves the scope before merge.

**Non-personal-origin guard.** Candidates whose `origin` is anything
other than `personal` (e.g. `work`, `external`, `bootstrap-raw-scan`,
`bootstrap-profile`, `agent-lens`) never qualify for automatic Level 2 merge —
always surface as CLARIFICATION (info tier) and let owner confirm
whether the pattern belongs in the personal tree. Rationale: these
origins represent inferred / batch-extracted / cross-context signals
where high recall is expected at the cost of precision; auto-merge
would erode constitution signal density. Only `origin: personal`
(in-the-moment owner-attended capture) is precise enough to qualify.

**`dimension → cognitive_axes` closure (read with the guard above).** The
`cognitive-model` lens stamps its candidates `origin: agent-lens`, so they are
blocked from automatic Level 2 merge — the L2 `dimension → cognitive_axes`
propagation above therefore does NOT fire for them automatically. For
cognitive-model candidates the path is: the `dimension` is carried to the F.3
weekly batch (which renders it per candidate), and the owner sets
`cognitive_axes` on the principle when promoting (whether merging into an
existing principle or authoring a new one — see CONSTITUTION.md §3). The Level 1
exact-match path and the L2 propagation fire automatically only for a future
`origin: personal` candidate that carries a `dimension`. So the hub's `promoted`
status for an axis is, by design, owner-gated — consistent with constitution
sovereignty; the lens contributes the `evidenced` status (live candidate), the
owner confirms the `promoted` status.

#### F.6 — Core bloat watch (daily)

Count principles where `core: true` AND `status != placeholder`.

- ≤ 8: silent.
- 9 or 10: append a line to the monthly summary (F.4), no CLARIFICATION.
- \> 10: raise CLARIFICATION `core-bloat` with subject="Core grew to {N}",
  body="compression discipline is eroding — revisit which of the core
  entries are truly irreducible vs derivable from another core".

#### F.7 — Evidence Trail compaction (weekly — first lint run of UTC week)

For every principle whose `## Evidence Trail` has > 50 entries: raise a
CLARIFICATION `evidence-trail-compact` with inline options:

1. **LLM-compact.** Summarise all entries older than 6 months into one
   `[compacted]` line of the form
   `{YYYY-MM}..{YYYY-MM} — cited N times across M decisions; pattern:
   {one-line synthesis}`. Owner approves / edits / rejects inline.
2. **Keep as-is.** If the history is chronologically valuable.
3. **Selective.** Owner lists specific dates / refs to remove.

On owner approval of option 1 or 3, invoke
`python3 _system/scripts/compact_evidence_trail.py --file {path}
--cutoff {YYYY-MM-DD} --summary "{approved text}"`. The script enforces
the protected-window rule (no compaction newer than 365 days).

#### Scan F output contract

All Scan F output is additive to the existing worklist — Step 4 Apply
Worklist routes CLARIFICATIONS identically to Scan A-E items via the
confidence-tier table.

#### F.8 — Cognitive-axes integrity (daily)

Validate the optional `cognitive_axes` field on principles (the field that powers
`5_meta/mocs/hub-cognitive-model.md`). Deterministic, no LLM:

```bash
python3 _system/scripts/lint_cognitive_axes.py --root .
```

JSONL on stdout, one event per finding, exit 0 always. The script reads the axis
slug SoT (the `<!-- cognitive-axes:begin -->` block in
`_system/registries/lenses/cognitive-model/prompt.md`) and every principle's
`cognitive_axes`, and emits:

- `cognitive-axes-malformed` — value is not a list of slug strings.
- `cognitive-axes-unknown-slug` — a slug not in the axis SoT (the hub silently
  drops it; lint surfaces it so the typo gets fixed).
- `cognitive-axes-duplicate` — a slug listed twice on one principle.
- `cognitive-hub-sensitivity-mismatch` — a `scope: sensitive` principle is tagged
  but the hub is not `is_sensitive: true` / owner-only (`audience_tags: []`),
  which would expose the sensitive principle if the hub is shared or surfaced.
- `axis-sot-unreadable` — the axis SoT block itself could not be read or parsed.
  Emitted alone (no per-principle findings are possible without it), so this
  one reports the scan as unrun rather than the principles as clean.

Route each finding to a CLARIFICATION of the matching type (Subject = the
`principle_id`, Quote = the offending slug / value, To resolve = "fix the slug
against the axis SoT / dedupe / set the hub privacy trio"). Never autofix the
sacred constitution tree — surface for owner review. The field is optional, so an
absent `cognitive_axes` is never a finding.

New CLARIFICATION types introduced by Scan F (vocabulary):
`principle-stale`, `principle-drift`, `principle-drift-retro`,
`principle-tradeoff`, `principle-candidate-batch`,
`principle-automerge-exact`, `principle-automerge-llm`,
`principle-extended-llm`, `principle-automerge-scope-mismatch`,
`core-bloat`, `evidence-trail-compact`, `lint-archive-failure`,
`cognitive-axes-malformed`, `cognitive-axes-unknown-slug`,
`cognitive-axes-duplicate`, `cognitive-hub-sensitivity-mismatch`,
`soul-manual-edit-to-auto-zone` (emitted by `render_soul_values.py`;
Scan F consumes / reports on existence).

All types follow the standard CLARIFICATION schema (Type, Subject,
Source, Action taken, Quote where applicable, Context, Uncertainty,
To resolve).

---

### Scan G — Archive Contract enforcement

Forward-only enforcement of `_system/docs/SYSTEM_CONFIG.md → Archive Contract`. Surfaces archived entities that lack the contract-required reason. **Forward-only:** entities archived before the contract adoption date are not flagged. Adoption date is encoded as `archive_contract_adopted_at: 2026-05-04` constant in `_system/scripts/_common.py`; an archived entity is flagged only when its archival timestamp ≥ adoption date.

#### G.1 — File-based entities (Form A): missing `## Archive Note`

Glob targets:
- Knowledge notes under `1_projects/`, `2_areas/`, `3_resources/`, `4_archive/` with frontmatter `status: archived`
- Hubs under `5_meta/mocs/` AND `4_archive/` whose location is `4_archive/` (folder-move archival)

For each candidate file:
1. If frontmatter `archived_at` is absent OR `archived_at < archive_contract_adopted_at` → skip (legacy / pre-contract archival).
2. Otherwise grep the file body for `## Archive Note` heading.
3. If absent → emit `archive-note-missing` CLARIFICATION (surfaced tier) with the file path, the `archived_at` value, and the conservative default «Surface for owner to fill `reason` / `triggered_by`; do not auto-write.»

Exception (single-source-of-truth): files under `0_constitution/{axiom,principle,rule}/` are NOT covered by G.1. Their Form A storage is the Evidence Trail `deprecated` entry — covered by Scan F (the constitution-alignment scans already enforce Evidence Trail health).

#### G.2 — Registry-row entities (Form B): empty `Reason` cell

Targets and the canonical archived sub-table per registry (per `SYSTEM_CONFIG.md → Archive Contract → Form B`):

| File | Section | Required Reason cell |
|---|---|---|
| `_system/registries/SOURCES.md` | `## Deprecated Sources` | every row |
| `3_resources/people/PEOPLE.md` | `## Stale People` | every row |
| `1_projects/PROJECTS.md` | `## Archived Projects` | every row |
| `1_projects/PROJECTS.md` | `## Retired Identifiers` | every row — the `Successor` cell is what Form A requires here; a `split` row lists all of them, comma-separated |
| `_system/registries/AGENT_LENSES.md` | `## Paused/Archived Lenses` | every row |

For each row:
1. Parse the row's `Reason` cell.
2. If empty (`-`, blank, `_(empty)_`, whitespace) AND the row's archival date (`Archived` / `Paused` / equivalent column) is ≥ adoption date → emit `archive-reason-missing` CLARIFICATION with file path, row identifier, archived date.
3. Rows where archival date is absent OR pre-adoption → skip.

#### G.3 — Bullet-list variant (Form B for TASKS Stale)

Target: `_system/TASKS.md → ## Stale` section.

For each `- [ ]` bullet under `## Stale`:
1. Determine when the bullet entered Stale (heuristic: the bullet's `^task-id` appears in `## Stale` of the previous run's TASKS.md snapshot — read previous-run snapshot from git via `git show HEAD~1:_system/TASKS.md` if available; otherwise treat all current bullets as pre-existing and skip).
2. For bullets that appeared in this run's Stale section but were NOT in the previous run's Stale section AND today's date ≥ adoption date:
3. Check the bullet ends with an italic `*(...)*` suffix.
4. If absent → emit `archive-reason-missing` CLARIFICATION with the bullet's `^task-id` and the offending line.

#### G.4 — Queue-based archival (Form C): missing required field

Targets:
- `_system/state/CLARIFICATIONS.md` `## Resolved Items` — for entries whose `Resolution-action` ∈ archival-effect set (`dismiss`, `dismiss-duplicate`, `archive-hub`, `close-thread`, `demote-tier`, `merge-notes`, `pursue-or-close` with `choice: close`) AND `Resolution-date` ≥ adoption date — every entry MUST have a non-empty `**Rationale:**` line.
- `_system/state/lint-context/weekly/{YYYY-WW}-people-candidates-dismissed.jsonl` — every line MUST have a non-empty `dismissal_reason` field (already enforced by R4 writer; G.4 is the audit).
- `_system/state/OPEN_THREADS.md` `## Resolved` section — every entry MUST have a non-empty `**Resolution:**` (or `resolution_text`) line for entries with `Resolved-date` ≥ adoption date.

Empty / missing required field → emit `archive-reason-missing` CLARIFICATION with the source file + entry identifier.

#### Scan G output contract

All Scan G output is additive to the existing worklist; Step 4 routes the two new CLARIFICATION types via the standard confidence-tier table. Both types are **surfaced tier** — never auto-resolve, owner populates the missing field via `/minder:mem:resolve-clarifications` round.

New CLARIFICATION types introduced by Scan G (already registered in `SYSTEM_CONFIG.md → Canonical CLARIFICATION types`):
- `archive-note-missing` (G.1)
- `archive-reason-missing` (G.2 / G.3 / G.4)

---

### Scan H — Manifest schema validation

Defence-in-depth gate over `_system/state/batches/*.json`. The producer-side normalisers in `_system/scripts/emit_batch_manifest.py` already conform every manifest at write time per the autonomous-resolution doctrine §3.1 layer-specific exception (concept names, audience tags, privacy trio, empty-section shapes). Scan H re-validates the on-disk artefact against the published JSON Schema, catching: (a) producer bugs that ship malformed manifests despite the normalisers, (b) manual edits / shell scripts writing into `batches/` outside the pipeline, (c) schema drift introduced by a new feature without coordinated bump.

Unlike concept / audience format issues — which are autonomous and never surface — **manifest contract violations always surface as CLARIFICATIONS**. The contract with downstream consumers is non-negotiable; an unroutable manifest is never silently corrected at lint time. Owner sees the violation, root-causes producer or schema.

#### H.1 — Validate recent batches against schema

Pipeline:

1. Read schemas from `_system/docs/manifest-schema/v{N}.json` (highest minor per major; per `manifest-schema/README.md` evolution rules, future v3.json sits next to v2.json — both kept).
2. On first run after deploy, init baseline at `_system/state/batches/.validator-baseline` to current UTC time. Idempotent: existing baseline is never overwritten. Older batches are excluded retroactively (legitimate pre-validator drift).
3. Validate every `*.json` in `_system/state/batches/` whose filename-timestamp prefix is ≥ baseline AND ≥ now − 26h (24h coverage + 2h cron / TZ buffer). The 26h window is the rolling daily lint cadence; the baseline is the absolute floor. Both gate.
4. For each batch: parse JSON → read `format_version` → pick matching major schema → validate.

Implementation: invoke the python helper.

```bash
python3 _system/scripts/lint_manifest_schema.py \
    --batches-dir _system/state/batches \
    --schemas-dir _system/docs/manifest-schema \
    --init-baseline
```

Stdout is JSONL — one event per validated batch. Skill ingests the stream, routes each `kind`:

| Event `kind` | CLARIFICATION emitted | Notes |
|---|---|---|
| `ok` | none | log to `log_lint.md` Hidden (verbose audit) only |
| `skipped-pre-baseline` | none | log to Hidden — confirms baseline is doing its job |
| `violation` | `manifest-schema-violation: {batch_id}` | Subject = batch filename. Context lists each error path + message + schema-path; `errors_truncated: true` shown when error count > 50 |
| `unknown-version` | `manifest-schema-unknown-version: {batch_id}` | Subject = batch filename + reported `format_version`. Context lists `available_majors` from the schemas dir. To resolve: ship the missing schema file (`v{N}.json`) or roll back the producer's `format_version` |
| `internal-error` | `validator-internal-error: {batch_id}` | Validator-side fault (json parse, validator exception). Lint never crashes — error becomes a CLARIFICATION; other scans continue |
| `quarantined` | none | log to Hidden, and report the total count in the run entry. The manifest carries `section_extras.quarantine` with a reason: no deterministic repair reaches conformance (typically a checksum whose file is gone). Re-raising it nightly would be a permanent nag over a state that cannot improve without inventing data — and inventing it is exactly what the retrofit refuses to do |

All three CLARIFICATION classes are **surfaced tier** — never auto-resolve. Floor: `weak`. The owner reviews and either fixes the producer (e.g. /minder:mem:process emission shape) or commits a schema migration shim.

A `violation` on a HISTORICAL batch is usually repairable rather than reportable: `python3 _system/scripts/rewrite_manifest_violations.py --batches-dir _system/state/batches --base . --apply --quarantine` runs every deterministic repair and quarantines the rest. Migration `007` does exactly this, so a friend's clone reaches a stable state on update rather than accumulating the same CLARIFICATIONs each night.

#### H.2 — Validator helper missing

**Do NOT install anything for this scan.** `jsonschema` is absent from the
ephemeral sandbox the nightly tick runs in, and installing it per run is a cost
and a log line repeated every night, forever, for a defence-in-depth check.
Without it the helper degrades by itself: it applies the shallow contract check
(the producer's own `validate_manifest` — top-level keys, processor enum,
format_version major, required sections) and stamps `"degraded": true` on every
event it emits. Report the run as degraded in the log entry when that flag is
present; that is the honest outcome, not a failure to fix. The deep per-field
validation resumes wherever the package happens to be available.

If `lint_manifest_schema.py` exits non-zero (schemas-dir missing, batches-dir missing), wrap the failure as a single CLARIFICATION `validator-helper-failed` with the stderr content. Do NOT crash subsequent scans — fail-open per ENGINE_DOCTRINE §3.1 wider doctrine ("never block; surface, don't decide silently"). The contract is: lint always completes; any subsystem failure becomes a clarification.

#### Scan H output contract

All Scan H output is additive to the existing worklist; Step 4 routes via the standard confidence-tier table. All H CLARIFICATION classes are surfaced tier (never auto-resolve), `weak` floor.

CLARIFICATION types Scan H emits (registered in `SYSTEM_CONFIG.md → Canonical CLARIFICATION types`):
- `manifest-schema-violation` (H.1)
- `manifest-schema-unknown-version` (H.1)
- `validator-internal-error` (H.1)
- `validator-helper-failed` (H.2)

#### Why a separate scan, not a sub-check inside Scan A

Scan A (Consistency & Structural) operates on owner-authored markdown and applies autonomous fix-ids to records / notes / hubs / profiles. Scan H operates on engine-emitted JSON manifests and never auto-fixes — surfacing only. Different territory, different rules, different audit trail. Coupling them would conflate "owner content drift autofix" with "engine output contract surveillance" and lose the per-skill traceability of the manifest contract.

---

## Step 4 — Apply Worklist

Iterate worklist в deterministic order (Scan A → F → within scan by candidate id).

### Confidence tier routing

Each worklist item has:
- Rule-based floor: `strong` | `weak`
- LLM verdict (4-point rubric с explicit evidence): `high` | `confident` | `probable` | `unsure` | `skip`

LLM verdict prompt (template):
```
Proposed fix: {operation} on {target}.
Context: {SOUL + PEOPLE + Lint Context Store relevant + related notes/hub}.

Answer each (y/n + one-sentence evidence):
1. Is structural match sufficient to apply without further review?
2. Does surrounding context corroborate?
3. Is there an analogous resolved case in CLARIFICATIONS archive?
4. Is there clean counter-evidence suggesting this fix is wrong?

Provide verdict: high | confident | probable | unsure | skip
Provide 2-sentence reasoning.
```

Positives − Negatives → verdict:
- 3–4 pos, 0 neg → `high`
- 2–3 pos, 0 neg → `confident`
- 1–2 pos OR 1 neg → `probable`
- 0 pos OR 2+ neg → `unsure`
- Clean counter-evidence present → `skip`

### Tier combined table → action

| Floor | LLM verdict | Tier | Action |
|---|---|---|---|
| strong | high | `silent` | Apply, log_lint.md Auto-Fixes entry (no CLARIFICATION) |
| strong | confident | `noted` | Apply, log_lint.md Auto-Fixes entry with confidence note (no CLARIFICATION) |
| strong | probable | `reviewed` | Apply + CLARIFICATION «validate» (cross-referenced by fix-id) + log_lint.md Auto-Fixes entry |
| weak | high | `reviewed` | Apply + CLARIFICATION (semantic-only match — always validate) + log_lint.md Auto-Fixes entry |
| weak | confident | `surfaced` | No apply, CLARIFICATION only |
| strong | unsure | `surfaced` | No apply, CLARIFICATION only |
| any | unsure (2+ neg) OR skip | `hidden` | No apply, no CLARIFICATION, log_lint.md Hidden subsection only |

**NO inline markers** in target files regardless of tier — see §«No inline markers в target files» below. `log_lint.md` is the single source of truth for audit trail; notes остаются clean reading state.

### HARD RULES override (non-negotiable)

Regardless of tier routing:
- Thread closure (move OPEN_THREADS Active → Resolved + hub coordination) → NEVER apply, max tier `surfaced`
- Tier change в PEOPLE.md Tier column (promote OR demote) → NEVER apply, max tier `surfaced`
- SOUL.md edits → NEVER apply
- Record/note body edits вне dedup-merge → NEVER
- PEOPLE.md Mentions column increment (non-drift-correction) → NEVER

**Profile generation** (C.1) — max tier capped at `reviewed` (creates new file, always validate first iteration).

### Conflict handling (same file, multiple ops)

Sequential mutation — each op re-reads target file immediately before write (catches earlier mutations). All auto-fix ops idempotent (check-before-apply) → re-reads safe.

### No inline markers в target files

**`log_lint.md` = single source of truth** для all fix audit trail. NO HTML-comment markers inserted в target notes. Rationale:
- Notes остаются clean для reading/reference use — not polluted debug info
- No marker accumulation across multiple lint runs (avoid N markers per file after N runs)
- Centralized history in one file simplifies grep + audit + rollback
- git commit + fix-id combination уникально locates any change

**Forensic workflow:**
- Странное изменение в файле X → `grep "target:{X}" _system/state/log_lint.md` → full fix record (fix-id + operation + before/after + reasoning + rollback hint)
- «Find all dedup operations» → `grep "operation:dedup" _system/state/log_lint.md`
- «Find all Evidence Trail backfills» → `grep "operation:evidence-trail" _system/state/log_lint.md`
- Rollback → `git log` + fix-id lookup → `git revert` or manual

### fix-id format (mandatory extended)

**Normal run:**
```
lint-{YYYYMMDD}-{run-seq}-{operation-qualifier}-{op-seq}
```

**`--force` run (lock-bypass):**
```
lint-{YYYYMMDD}-{run-seq}-p{PID}-{operation-qualifier}-{op-seq}
```

Components:
- `YYYYMMDD` — UTC date of lint run start (no dashes)
- `run-seq` — 3-digit counter per day (`001`, `002`, ...)
- `p{PID}` — **only when `--force` flag active** — OS process ID prevents collision between parallel `--force` runs bypassing lock
- `operation-qualifier` — **mandatory** — operation class identifier (kebab-case). Examples: `scan-a`, `scan-b`, `scan-c`, `scan-d-trail`, `dedup`, `dedup-backlink-redirect`, `bare-name-resolve-frontmatter`, `bare-name-resolve-tag`, `bare-name-resolve-wikilink`
- `op-seq` — sequential counter per qualifier within run

Examples:
- `lint-20260420-001-evidence-trail-42` — 42nd Evidence Trail backfill в run 001 on 2026-04-20 (normal)
- `lint-20260420-001-dedup-1` — 1st dedup merge (normal)
- `lint-20260420-001-bare-name-resolve-wikilink-3` — 3rd body-wikilink substitution (normal)
- `lint-20260420-002-p54321-scan-a-7` — Scan A fix #7 in `--force` run (PID 54321)

**Qualifier обязателен** — enables greppable operation-level analysis directly в `log_lint.md` без lookup tables.

**Rationale for PID-on-force:** `--force` bypasses cross-skill lock. Two parallel `--force` runs same day = counter collision risk. PID inclusion guarantees uniqueness без complicating normal id format.

### Applied CLARIFICATION format (mandatory Context field)

```markdown
### {YYYY-MM-DD} — {reason-code}: {subject-short-title}

**Type:** {reason-code}
**Subject:** {entity-id}
**Source:** lint-{run-id}
**Suggested action:** {canonical Resolution-action verb — see `_system/docs/SYSTEM_CONFIG.md`}
**Confidence tier:** {silent|noted|reviewed|surfaced}
**Applied:** {no — if surfaced, yes/fix-{id} — if reviewed}
**Fix-id:** lint-{run-id}-{seq} (cross-reference to log_lint.md Auto-Fixes entry, если applied)

**Quote:** > «{verbatim fragment, 1-3 sentences, when applicable (transcript source)}»

**Context:** {2-4 sentence paragraph — what ambiguity is about, why uncertain, related entities inline with wikilinks, relevant facts from Lint Context Store / SOUL / related hub, 1-2 candidate resolutions with pros/cons}

**Recent contexts:**
- [[{note-id-1}]] — {1-line hint, date}
- [[{note-id-2}]] — {...}

**To resolve:** {imperative — what unblocks system}

**Uncertainty:** {LLM doubt — edge cases, counter-signals}
```

---

## Step 5 — Lint Context Store — Daily Generation (gap-aware catch-up)

After worklist applied, generate all missing daily summaries between `latest_daily_file.date + 1` and yesterday (inclusive).

### Bootstrap mode

If `_system/state/lint-context/daily/` empty → generate last 30 days only (not all-time; cost без value for ancient days). Older days remain un-generated; monthly catch-up uses whatever dailies available.

### Per-day generation

For each target date:
1. Skip if `_system/state/lint-context/daily/{date}.md` already exists.
2. Collect source data:
   - `BATCH_LOG.md` entries dated this day
   - `PROCESSED.md` entries with `created:=this day`
   - `log_maintenance.md` entries dated this day
   - `log_process.md` entries dated this day
   - OPEN_THREADS.md, TASKS.md state diffs (если snapshot possible vs previous day)
3. **Quiet day detection:** if all source data empty → quiet day template with thread-state snapshot + weekday context + pattern from last 7 days.

### Daily format

```markdown
---
id: lint-daily-{YYYY-MM-DD}
layer: system
generated_by: minder:mem:lint
generated: {ISO UTC timestamp}
covers: {YYYY-MM-DD}
quiet_day: {true|false}
---

# Daily Summary — {date}

## Activity
- Batches processed: {N} ({ids}) | Records: {N} | Notes: {N} | Tasks added: {N} / done: {M}
- Threads: opened {N}, closed {M}, merged {K}
- People: {N} mention events across {M} persons
- Hubs touched: {ids with bullet/content counts}

## Hotspots
- Most-mentioned people (top 3): {ids + counts}
- Most-active threads: {ids}
- Hub of the day (if notable): {id + activity}

## Auto-Fixes (lint previous run)
- {brief summary if lint ran this day — per-tier count}
- (none) — on quiet day or if lint didn't run

## CLARIFICATIONS
- Raised: {count + reason codes breakdown}
- Resolved: {count}

## Notable (LLM-synthesized, 2-4 sentences)
{prose observations — what mattered, why, what drifted; quiet day — contextual commentary from recent patterns + weekday}
```

### Retention purge

After all daily writes, scan `_system/state/lint-context/daily/`, delete files с `{date}.md` date < today − 30 days.

---

## Step 6 — Lint Context Store — Monthly Generation (gap-aware catch-up)

Check for missing monthlies:
1. Read `_system/state/lint-context/monthly/` — find latest sealed month.
2. For each month between `latest_monthly + 1` and `current_month - 1` (inclusive) — generate missing monthly.

### Per-month generation

1. Load daily files from target month (whatever present — gap tolerance).
2. Load live-state snapshots (OPEN_THREADS, PEOPLE, CLARIFICATIONS Resolved archive, content pipeline):
   - For immediately previous month: use current state as snapshot (fresh).
   - For deeper backfill: snapshot `_system/` current state, mark в frontmatter `snapshot_at: {current-date}` (honest limitation).
3. LLM prompt generates summary per template below.
4. **SOUL advice trigger:** if generating monthly AND this month is immediately previous (not deep backfill) → raise `soul-update-advice` CLARIFICATION. Deeper backfill skips SOUL advice (stale recommendations = noise).
5. Write `_system/state/lint-context/monthly/{YYYY-MM}.md`.

### Monthly format («нормальный документ» per Owner)

```markdown
---
id: lint-monthly-{YYYY-MM}
layer: system
generated_by: minder:mem:lint
generated: {ISO UTC timestamp}
covers: {YYYY-MM-01}..{YYYY-MM-LAST}
daily_coverage: {N}/{days_in_month}
snapshot_at: {generated_date | "fresh" if immediately previous month}
---

# Monthly Summary — {Month Name YYYY}

## TL;DR

{IF `daily_coverage / days_in_month < 0.5` → prepend one-line banner:
 `> ⚠ Reconstructed retroactively on {snapshot_at} from {N} dailies + git history + static file scan. Confidence: medium. Treat as imperfect recall.`
ELSE omit banner.}

- {3-5 bullets — executive summary}

## Structured activity roll-up
- Batches: {N} | Records: {N} | Notes: {N} | Tasks added: {N} / closed: {M} / stale: {K}
- Threads: opened {N}, closed {M}, carried-over {K} → current {total}
- People: new profiles {N}, tier changes (promote/demote) {breakdown}
- Hubs: active {N}, new {M}, top-growing {id}

## Narrative highlights
{1-2 paragraphs — LLM prose. «What mattered this month» with substantive detail for recall}

## Patterns & trends
{1-2 paragraphs — LLM observations: recurring themes, focus drift vs SOUL, emerging topics, counter-patterns}

## Decisions made this month
- {extracted from decision-type notes + resolved threads}

## People focus
- **Top 10 mentioned:** {ids + counts}
- **New additions:** {ids}
- **Relationship-density shifts:** {notable jumps}

## Content pipeline
- High-potential notes accumulated: {N}
- Content types breakdown: expert {N} / reflection {M} / story {K} / insight / observation

## Carrying into {next month}
- **Unresolved threads:** {count + top 3 titles}
- **Pending CLARIFICATIONS:** {count per reason code}
- **Forward-looking from SOUL Focus:** {carry-over priorities}

## Analysis
{1 paragraph — LLM honest reflection. «This month felt X». Soft artifact — owner may edit manually}
```

### soul-update-advice CLARIFICATION (when applicable)

LLM prompt inputs:
- Current SOUL.md content
- 30 daily summaries from generated month
- Resolved threads during month
- Decisions extracted
- People dynamics (new profiles, tier changes)

LLM rubric:
1. Which Focus items received meaningful activity?
2. Which Focus items received 0 activity?
3. Which themes were present in activity but absent from Focus?
4. Has priority shifted observably?
5. Have Values shown strain / reinforcement?
6. Any new emerging patterns warranting Focus addition?

Output CLARIFICATION:

```markdown
### {YYYY-MM-01} — soul-update-advice (monthly)

**Type:** soul-update-advice
**Subject:** _system/SOUL.md
**Source:** lint-monthly-{YYYY-MM}
**Confidence tier:** surfaced (SOUL never auto-edit)
**Suggested action:** review-soul

**Context:** {3-5 sentence LLM summary — how past month's activity aligns/diverges with SOUL Focus. Highlight: (a) themes present but absent from Focus, (b) Focus items receiving 0 activity, (c) emerging patterns}

**Specific recommendations:**

*Focus Work:*
- {Add: theme X — evidence}
- {Revise: Focus item Y — reason}
- {Remove: Focus item Z — 0 activity}

*Focus Personal:*
- {same structure}

*Values reassessment (only if strong signal):*
- {if applicable}

*Working Style (only if strong signal):*
- {if applicable}

**To resolve:** Read recommendations → manually edit `_system/SOUL.md` если aligned → mark resolved with `Resolution-action: fix-process` + payload summarizing edits. `Resolution-action: dismiss` if no change warranted.

**Uncertainty:** {any recommendation feeling uncertain}
```

---

## Step 7 — Write log_lint.md Entry

Append ONE entry к `_system/state/log_lint.md` (aggregate across all scans):

```markdown
## {ISO UTC timestamp} | lint | by: minder:mem:lint | batch: lint-{YYYYMMDD}-{NNN} | manifest: {YYYYMMDD-HHmmss}

### Scans Executed
- Scan A (consistency): {N items processed, K auto-fixes, M CLARIFICATIONS}
- Scan B (threads): {...}
- Scan C (people): {...}
- Scan D (notes): {...}
- Scan E (focus): {...}
- Scan F (constitution): {...}
- Scan G (archive contract): {...}
- Scan H (manifest schema): {... incl. `degraded: true` when the deep validator was unavailable}

### Auto-Fixes
- Silent tier: {N} applied — {breakdown by operation}
- Noted tier: {N} applied — {breakdown}
- Reviewed tier: {N} applied (cross-linked to CLARIFICATIONS by fix-id) — {breakdown}

#### fix-{run-id}-{seq} | tier:{t} | target:{path}
- **Operation:** {op}
- **Before:** `{1-line state}` (or «see git diff» for multi-line)
- **After:** `{1-line state}`
- **Reasoning:** {LLM 1-2 sentences}
- **Reversible:** yes
- **Rollback hint:** `git diff HEAD~1 {path}` or manual revert

{... per-fix entries ...}

### Suggestions → CLARIFICATIONS
- {total items} raised under `## lint {YYYY-MM-DD}` header:
  - Surfaced: {N} ({breakdown by reason code})
  - Reviewed (apply + validate): {N} ({breakdown})

### Hidden (verbose audit)
- {N} items hidden (LLM verdict = skip / 2+ counter-evidence). Listed below для audit — NOT surfaced к CLARIFICATIONS.
  - {reason-code}: {subject} — {one-line LLM reasoning}

### Lint Context Store
- Daily: {created {dates} | skipped (exists)}
- Monthly: {created {YYYY-MM}.md | skipped (month not turned)}
- Retention purge: {N daily files deleted}

### Errors / Warnings
- {malformed files encountered с workarounds; empty list if clean run}
```

---

## Step 7.5 — Dispatch /minder:mem:resolve-clarifications --auto-mode

After invariant scans + log entry land, dispatch the smart-resolve
sweep inline. Lint's role re: Action Hints is ZERO plumbing — resolve
handles ingestion, curation, auto-resolve, history-aware reasoning
end-to-end. Lint is the timer; resolve is the engine.

Pre-flight short-circuit (deterministic, cheap):

1. Walk `_system/agent-lens/{lens-id}/{date}.md` for files modified
   since `_system/state/last-resolve-tick.txt` (or last 24h if marker
   absent). If ZERO files match AND CLARIFICATIONS.md has no items
   carrying `**Smart_resolve reasoning:**` (i.e. nothing left for
   smart_resolve to retry stale-checks on) → skip resolve dispatch.
   Saves the LLM cost on idle nights.
2. Otherwise → invoke `/minder:mem:resolve-clarifications --auto-mode` inline
   in the same scheduler-agent context.

Failure handling:

- Resolve failure surfaces as a CLARIFICATION (`type:
  resolve-dispatch-failed`, severity weak) but does NOT fail lint —
  invariant scans + log entry already landed. Owner sees the
  CLARIFICATION next interactive resolve session.
- Resolve writes its own session log under
  `_system/state/resolve-sessions/`; lint does not need to mirror it
  in `log_lint.md`. Cross-reference: include a one-line entry in
  log_lint's «### Auto-Fixes» section if resolve ran («auto-resolve:
  applied N, queued M, vetoed K» — taken from resolve's session log
  frontmatter).

Lock interaction:

- Lint holds `_sources/.lint.lock` throughout. Resolve, when invoked
  with `--auto-mode`, observes lint's lock as «caller is the
  dispatcher, not a competitor» — it acquires its own `.resolve.lock`
  for the duration of Step A and releases on exit. Both locks coexist
  for the ~30-90 s of the sweep.
- If resolve cannot acquire `.resolve.lock` (an owner-driven
  interactive session somehow started after Step 0.1's cross-skill
  check) → resolve exits silently without doing work. Lint surfaces
  this as a CLARIFICATION, continues normally.

**Quality trade-off (acknowledged).** The dispatched resolve
A.2/A.3 LLM judgements run in the same scheduler-agent context that
lint just used for invariant scans + log writing. Some accumulated
reasoning bleeds across — lint's «pattern-match invariant violations»
chain stays visible to resolve's «would the experienced owner
approve this NOW» judgement. The bleed is real but small (different
reasoning shapes, ortogonal input concerns). Operational simplicity
of one tick wins over a stricter context isolation. The most
quality-sensitive split — agent-lens vs resolve — IS preserved (lens
runs are a separate scheduler tick, so resolve never judges its own
agent's lens body output).

---

## Step 7.6 — Emit the batch manifest

Every engine skill that changes persistent state emits a manifest
(ENGINE_DOCTRINE §3.8). Lint's is the record that a nightly tick ran and what
it did — the audit trail a downstream consumer reads without parsing prose.

`batch_id` is `{YYYYMMDD-HHmmss}` of this run's lock acquisition. The manifest
schema requires that shape (`^YYYYMMDD-HHMMSS(-N)?$`), which is NOT the
`lint-{YYYYMMDD}-{NNN}` run-id the `log_lint.md` header carries — so the Step 7
entry names the manifest's `batch_id` alongside its own run-id, and the two
artefacts stay cross-referable rather than merely adjacent. Lint mints its own
id (unlike `/minder:mem:maintain`, which carries across the process batch's) because a
lint run integrates nothing: it is its own event.

**`stats` shape** — the only required section for `minder:mem:lint`:

```json
{
  "scans_executed": ["A.1", "A.2", "..."],
  "scans_deferred": ["D.1", "..."],
  "events_total": N,
  "autofixes_applied": N,
  "autofixes_by_fix_id": {"{fix-id-prefix}": N},
  "files_modified": N,
  "clarifications_raised": N,
  "clarifications_pending_in_queue": N,
  "idempotency_verified": true
}
```

**Emission via the helper:**

```bash
python3 _system/scripts/emit_batch_manifest.py \
    --input <path-to-temp-json> \
    --output _system/state/batches/{batch_id}-lint.json
```

Exit codes per the helper's docstring; treat exit 3 as `/minder:mem:process` does —
a `process-compatibility` CLARIFICATION only when the root cause cannot be
auto-corrected in the assembly.

**Failure semantics:** the manifest is downstream routing, never the
authoritative artefact — `log_lint.md`, the applied autofixes and the raised
CLARIFICATIONs are. A failed write is surfaced as one CLARIFICATION and the
tick continues to Step 7.5; it is never a reason to abort a lint run or to
roll back a fix already applied. **No BATCH_LOG.md row** — that index belongs
to `/minder:mem:process` alone, and a lint run is not a batch to integrate. This is
also why Scan A.12 must not read lint manifests when computing its unprocessed
set: only process batches are integrable.

Scan H validates manifests written **before** the current run's baseline
window, so a manifest this step writes is checked by the NEXT tick rather than
by the run that produced it. That ordering is deliberate — a producer
validating its own output in the same breath tests nothing.

---

---

## Step 8 — Release Lock

Delete `_sources/.lint.lock`. Guaranteed finally path.

---

## Step 9 — Report

Write to stdout:

```
## Minder Memory Lint Report — {YYYY-MM-DD}

### Scans Run
- A (consistency): {counts}
- B (threads): {counts}
- C (people): {counts}
- D (notes): {counts}
- E (focus): {counts}
- F (constitution): {counts}
- G (archive contract): {counts}
- H (manifest schema): {counts}

### Auto-Fixes Applied: {total}
- Silent: {N} — {operations summary}
- Noted: {N} — {operations summary}
- Reviewed: {N} — {operations summary, cross-linked to CLARIFICATIONS}

### CLARIFICATIONS Raised: {total}
- Surfaced: {N} — {reason codes + subjects summary}
- Reviewed (apply + validate): {N} — {reason codes + subjects summary}

### State Changes
- Files modified: {N}
- Files created: {N} (profiles + daily + monthly)
- Files deleted: {N} (dedup secondaries + daily retention purge)

### Lint Context Store
- Daily: {created {dates}}
- Monthly: {created {YYYY-MM}.md | skipped}

### Completion Gate
- [x] All scans executed
- [x] Lock released
- [x] log_lint.md entry written
- [x] Lint Context Store updated
- [x] No writes to forbidden territories (HARD RULES invariant)
- [x] **Bare-name three-surface consistency** — for each resolved bare-name, grep frontmatter/tags/body wikilinks → 0 residual bare references
- [x] **Identity autofix residue** — for each identifier A.8 autofixed, re-run `identity_audit.py --report --json` → 0 live findings on the surfaces that were written
- [x] **Dedup backlink invariant** — for each deleted secondary, grep `[[{deleted-id}]]` in non-audit files → 0 results
- [x] **Suppression via Resolved Items** — no surfaced CLARIFICATION raised для subject matching resolved suppression entry within active window

### Next Actions for Owner
Run `/minder:mem:resolve-clarifications` to review the queue interactively. {N} items accumulated:
- {reason-code-1}: {N items}
- {reason-code-2}: {N items}

The skill clusters items by theme, reminds context + verbatim quotes inline, and applies confirmed resolutions in-place.
```

---

## CLARIFICATIONS Reason Codes

**Structural:**
- `link-broken-2plus-candidates` — broken wikilink с 2+ possible targets
- `link-broken-unresolvable` — broken wikilink с 0 candidates
- `frontmatter-unfixable-schema` — schema mismatch not auto-fixable
- `frontmatter-fence-misplaced` — a `## ` body heading sits inside the YAML fence (A.2) and `repair_misplaced_fence` refused as ambiguous (multiple `---` in the displaced region); owner relocates the fence
- `orphan-file` — file без any inbound references
- `index-missing` — `_system/views/INDEX.md` does not exist (A.6)
- `index-stale` — INDEX.generated > 7 days behind newest knowledge note modified (A.6)
- `index-frontmatter-malformed` — INDEX frontmatter missing `generated:` or `generator:` (A.6)
- `task-aggregation-orphans` — tasks present in notes as open `- [ ]` but absent from TASKS.md (A.6.1); owner runs `/minder:mem:process --reconcile-tasks`
- `hub-index-incomplete` — HUB_INDEX.md is missing one or more on-disk hub files (A.6.2); regen via `/minder:mem:maintain`
- `calendar-aggregation-orphans` — a note's future `📅` event is absent from CALENDAR.md (A.6.3); owner runs `/minder:mem:process --reconcile-calendar`
- `portable-name-collision` — non-portable inbox name whose normalised form already exists in the same directory, or normalisation returned None (A.10 — no autofix, owner resolves)
- `portable-name-escape` — non-portable tracked path outside inbox and not grandfathered via PROCESSED.md (A.10 — surfaced only; rename + reference rewrite is an owner-reviewed action)
- `source-layout-split-name` — an inbox directory holding no item marker of its own but containing subdirectories, in a shape too ambiguous to rejoin (several children, a child that is not a complete item, or a target name already taken). A producer's `/` in the recording title split one name into two folders; A.10a rejoins the unambiguous case and surfaces this one (no autofix — never guess which folders belong together)

**Content markup (A.11):**
- `content-type-canon-reviewed` — judgment remap applied with default target, validate (A.11 — weak × high; reversible via Evidence Trail)
- `content-type-canon-surfaced` — judgment remap ambiguous between 2+ canonical types, owner picks with note excerpt (A.11 — weak × confident/unsure, no apply)
- `content-type-unknown` — drift `content_type` not in `CANON_MAP`; LLM-suggested canonical mapping, optionally extend the table (A.11 — surfaced only, never guessed)
- `content-type-missing` — note has `content_potential` but no `content_type`; owner sets the canonical type (A.11 — surfaced, no apply)
- `content-angle-missing` — note has `content_potential` but empty/absent `content_angle`; the draft-maintainer proposes a hook on its first run (A.11 — surfaced, aggregated count + note list, never auto-written)

**Thread lifecycle:**
- `thread-stale-warn` — past warn threshold, no activity (reviewed — no apply, CLARIFICATION)
- `thread-stale-escalate` — past escalate threshold, explicit decision required
- `thread-hub-linkage-backfill-surfaced` — thread без hub, semantic-only match
- `orphan-clarification-escalate` — Open Item unresolved > 3 weeks
- `applied-pending` — structured resolved item с `Applied: no` older than 2 weeks

**People lifecycle:**
- `tier-promote-auto-profile` — crossed Tier 1, profile auto-generated (reviewed)
- `tier-demote-candidate` — below threshold + no profile + no activity (surfaced only)
- `orphan-bare-name-surfaced` — bare name unresolved, multiple profile candidates (surfaced)
- `orphan-bare-name-resolved` — unambiguous bare name auto-substituted (reviewed — apply + validate batch via git diff + log_lint.md grep)
- `mention-count-drift-surfaced` — recount conflicts, source of truth unclear

**Note lifecycle:**
- `dedup-reviewed` — merge applied, validate unique content extraction
- `dedup-surfaced` — similarity detected, tier too low to auto-merge
- `evidence-trail-backfill-surfaced` — legacy note, semantic reconstruction uncertain
- `orphan-note` — not linked, archive candidate
- `hub-stale-vs-material` — hub `modified` 60+ days behind newer underlying knowledge notes, ≥2 such notes accumulated since last hub edit (D.4 — surfaced only, synthesis layer never auto-rewritten)

**Focus:**
- `soul-focus-drift` — Focus misaligned vs recent activity (daily scan)
- `soul-update-advice` — monthly structured SOUL review

**Profile normalization:**
- `profile-non-canonical-sections` — profile has extra sections beyond canonical template (surfaced — policy decision pending between strict / allowed extensions / whitelist)

**Concept and audience autofix (A.7) — autonomous, fix-codes only.**
These are NOT CLARIFICATION codes; they are fix-ids logged in
`log_lint.md` for traceability. The concept layer is 100% autonomous:
the engine resolves every concept/audience format issue with
deterministic heuristics in `_common.py`. Owner sees no queue,
takes no action.

- `concept-format-autofix` — concept-name rewritten in place by
  `normalize_concept_name()` (case / kebab→snake / diacritic-fold /
  length truncate). Type prefixes are NOT stripped — names are kept
  verbatim (see CONCEPT_NAMING.md).
- `concept-drop-autofix` — concept-name entry dropped silently
  (non-ASCII residue, bare type-enum word, or otherwise
  unnormalisable). The `concepts:` list shrinks; other entries kept.
- `concept-alias-rewrite-autofix` — concept-name entry rewritten from a
  retired alias to its canonical name, per the `Aliases` column of
  `_system/registries/CONCEPTS.md`.
- `domain-normalise-autofix` — `domains:` entry rewritten (slash-compound
  expanded to its whitelisted parts)
- `domain-drop-autofix` — `domains:` entry dropped (not in canonical 13 ∪
  active DOMAINS.md extensions, unnormalisable, or wrong type). Fail-closed:
  the engine never coins a domain.
- `audience-tag-normalise-autofix` — audience-tag rewritten to
  normalised form when normalised version is in canonical 5 or
  AUDIENCES.md Extensions
- `audience-tag-drop-autofix` — audience-tag entry dropped (not in
  whitelist, can't be normalised to whitelisted form). Fail-closed:
  engine never coins an extension.
- `privacy-trio-backfill-autofix` — missing `origin` / `audience_tags`
  / `is_sensitive` field inserted with conservative defaults
  (`personal` / `[]` / `false`)
- `is-sensitive-coerce-autofix` — non-bool `is_sensitive` value
  coerced to bool (`"true"`/`"True"` → `true`, anything else → `false`)
- `origin-coerce-autofix` — out-of-enum `origin` value coerced to
  `personal`
- `portable-name-autofix` — non-portable `_sources/inbox/` entry renamed
  via `normalize_portable_name()` (A.10 — reference-safe by construction:
  unprocessed inbox items have no inbound references)

**Content markup autofix (A.11) — autonomous, fix-codes only** (via
`lint_content_markup.py`; targeted line-edits, not whole-frontmatter re-dumps):
- `content-type-canon-autofix` — drifted `content_type` synonym rewritten to its
  canonical type (technical/technical-decision/practice → expert; personal →
  reflection) with an Evidence-Trail note. Judgment / unknown drift is NOT
  autofixed — it routes to CLARIFICATIONs (see Content markup codes above).
- `content-angle-format` — bare-string `content_angle` normalized to a 1-element
  YAML list (uniform shape), scalar preserved verbatim, note's list indent matched.

(Manifest concept and audience fields are conformant by upstream
construction in `/minder:mem:process` §4.7 and `/minder:mem:maintain` Step 4 hub
linkage — no separate manifest fix-ids needed.)

**Anomalies (malformed handling):**
- `lint-malformed-frontmatter` / `hub-dangling-reference` / `person-unknown-in-frontmatter` / `log-malformed-entry` / `lint-context-daily-unreadable` / `lint-scan-exceeded-soft-timeout-surfaced`

Parsable fields are a stable contract (per `_system/docs/SYSTEM_CONFIG.md` CLARIFICATIONS format). Forward-compat: new codes append-only.

---

## Example Usage

```
/minder:mem:lint                        # full nightly run
/minder:mem:lint --dry-run              # hybrid preview (diffs for auto-fixes, prose for CLARIFICATIONS)
/minder:mem:lint --dry-run --verbose    # full diff including Lint Context Store generation
/minder:mem:lint --scope fast           # skip expensive scans (dedup + Evidence Trail backfill)
/minder:mem:lint --verbose              # reasoning traces в stdout
/minder:mem:lint --force                # bypass «ran recently» warning
/minder:mem:lint --weekly               # force weekly/monthly-gated triggers (Scan F reviews) even mid-week
```

---

## Invariants

Check during adversarial audit:

1. **HARD RULES (never auto-apply):** thread closure, PEOPLE.md Tier column, SOUL.md, record/note body вне dedup-merge, PEOPLE.md Mentions non-drift, TASKS.md/CALENDAR.md/BATCH_LOG.md/batches/ writes
2. **Confidence tier routing:** silent requires strong+high, noted requires strong+confident (or strong+high with concern), without rule-floor max tier `surfaced`
3. **CLARIFICATIONS:** all items MUST have `**Context:**` field; parsable fields stable (canonical Resolution-action vocabulary); Resolved items structured format с `Applied` field
4. **Idempotency:** second run on unchanged state → only a new daily summary diff если new UTC day, else zero state changes
5. **Best-effort:** single malformed file never aborts run; missing Lint Context Store first run handled gracefully
6. **Dedup safety:** no unique content lost (LLM confirmation required); frontmatter lists union (no deletion); Evidence Trail entry prepended; post-merge backlink redirect invariant
7. **Rollback via git:** every lint run produces diff-able changes; fix-id → git diff hunk
8. **Lint Context Store:** daily для every past day (quiet с template); monthly sealed first run new UTC month; retention purge > 30 days only; monthly never deleted
9. **Parsable Resolved:** ALL resolved items structured format
10. **Empty-run safe:** always ≥ 1 daily summary + 1 log_lint.md entry; zero auto-fixes + zero CLARIFICATIONS = valid healthy run
11. **Cross-skill exclusion symmetric:** process/maintain/lint — любой other lock exists → abort
12. **Log file ownership:** log_lint.md written ONLY by /minder:mem:lint; others read-only
13. **Profile template unified:** all profiles match canonical schema; `## Мои наблюдения` structurally required, never auto-generated content
14. **CLARIFICATIONS single format:** `## Open Items` + `## Resolved Items` only
15. **SOUL advice cadence:** only immediately previous month raised; deep backfill skips; SOUL never auto-edited
16. **Suppression via Resolved Items:** no surfaced CLARIFICATION raised для subject matching resolved suppression entry within active window
17. **Bare-name three-surface consistency:** per resolved bare-name, grep frontmatter/tags/wikilinks → 0 residual bare references
18. **Dedup backlink integrity:** post-merge grep `[[{deleted-id}]]` in non-audit files → 0 results
19. **Identity autofix residue:** per autofixed identifier, re-audit → 0 live findings on the written surfaces

---

## Contract dependencies

Lint consumes artifacts produced by other skills:
- `_system/docs/batch-format.md` — batch output contract
- `/minder:mem:process` inline Mentions increment in PEOPLE.md
- `/minder:mem:maintain` threads + hub linkage

Forward-compatible: Resolved structured format + canonical `Resolution-action` vocabulary + confidence tier enum — all append-only evolution. New reason codes append-only. Downstream `/minder:mem:resolve-clarifications` consumer reads structured Resolved Items directly.
