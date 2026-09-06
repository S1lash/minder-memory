---
name: minder:mem:maintain
description: >
  After-batch integrator for Minder Memory. Reads unprocessed batches from
  `_system/state/batches/` + `_system/state/BATCH_LOG.md`, integrates them into live state:
  thread detection & strategic-grain opening, back-reference writes into
  records/notes frontmatter, hub linkage for new threads, thread closure
  suggestions (suggest-only — never auto-closes), tier promote suggestions
  (suggest-only — never auto-applies), mention consistency sanity check,
  CURRENT_CONTEXT full regen, log_maintenance.md append. Multi-batch iteration,
  per-batch idempotency, concurrency lock, best-effort malformed batch handling.
disable-model-invocation: false
---

# /minder:mem:maintain — After-Batch Integrator

Consumes `_system/state/batches/{batch-id}-process.md` produced by `/minder:mem:process`. Integrates
each unprocessed batch into live state.

**Philosophy:**
- Maintain = integrate, not extract. Never creates knowledge notes, records,
  tasks, events, or increments mention counts. These are `/minder:mem:process` territory.
- Maintain only modifies: `OPEN_THREADS.md`, hubs, `CURRENT_CONTEXT.md`,
  `CLARIFICATIONS.md`, `log_maintenance.md`, and frontmatter back-refs in
  existing records/notes (`threads:` field). Body of existing notes — never.
- **Suggest, don't apply** for user-facing state changes (thread closure, tier
  promote). Maintain raises CLARIFICATIONS; owner applies manually via edit.
- Best-effort over hard fail. Malformed batch → workaround + CLARIFICATION.
- LLM-first reasoning with rule-based floor.

**Invocation:** owner-driven, and Step 4.5 of the scheduled process tick
(`integrations/claude-code/scheduler-prompts/process-scheduled.md`) — which is
its only autonomous trigger. It is never invoked from *inside* `/minder:mem:process`:
the two hold mutually exclusive cross-skill locks, so integration can only
start once the producer has returned and released `.processing.lock`.

**Contracts:** `_system/docs/ENGINE_DOCTRINE.md` (operating philosophy
— load first; binding cross-skill rules: surface-don't-decide,
inclusion-bias-on-capture / curation-on-promotion, idempotency,
owner-LLM contract), `_system/docs/batch-format.md`,
`_system/docs/SYSTEM_CONFIG.md` (Data & Processing Rules),
`5_meta/PROCESSING_PRINCIPLES.md` (8 principles — calibrate hub
linkage and tier-promote judgements against principle 3 Connection
Awareness, principle 4 Cross-Domain Permeability, principle 7 People).

**Working directory:** the zettelkasten base. Every path and every `python3`
command in this file is written relative to it.

**Documentation convention:** при любых edits этого SKILL соблюдай `_system/docs/CONVENTIONS.md` — файл описывает current behavior без version/phase/rename-history narratives.

## Arguments

`$ARGUMENTS` supports:
- `--dry-run` — scan unprocessed batches, report planned actions without writes
- `--batch <id>` — process only a specific batch-id. Must exist as
  `_system/state/batches/{id}-process.md` (validated in Early Exit). Raises a warning if the
  batch is already recorded in log_maintenance.md and requires `--force` to
  proceed (re-run creates duplicate CLARIFICATIONS and may create duplicate
  thread entries, back-refs are idempotent)
- `--force` — used with `--batch <id>` only. Acknowledge duplicate risk and
  bypass log_maintenance.md idempotency check. No effect without `--batch`
- `--verbose` — include full decision rationale in report
- `--no-sync-check` — skip the data-freshness pre-flight (see below)

---

## Pre-flight: data freshness (non-blocking)

Multi-device safeguard. If `origin` has commits not yet pulled, the
batch under `_system/state/batches/` may have been produced on another
device and already integrated there. Courtesy check, not a gate.

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
  ⓘ origin/<branch> ahead by <N> commit(s). Maintain on stale state
    may double-integrate batches already handled elsewhere.

    [s] run /minder:mem:sync-data first  (recommended)
    [c] continue with current local state
    [d] show pending commits
  ```
- `s` → exit 0, owner re-runs after sync-data.
- `c` → proceed; `d` → show log, re-prompt.

---

## Early Exit Check

**FIRST action — before lock, before context loading.**

**0. Cross-skill lock check.** Read every pipeline lock under `_sources/` and
abort on any that exists, with «`{holder}` running, try again later» — or, for
this skill's own `.maintain.lock`, «another `/minder:mem:maintain` run in progress».
The lock set is owned whole by `_system/docs/SYSTEM_CONFIG.md` → «Cross-skill
exclusion»; read it there rather than keeping a second copy that drifts. Stale
lock (>2 hours) → warn, offer manual removal, do NOT auto-delete.

1. Read `_system/state/BATCH_LOG.md` — all rows.
2. Read `_system/state/log_maintenance.md` — grep for entries matching
   `## ... | maintain | by: minder:mem:maintain | batch: {id}` AND absence of
   `### Errors / Warnings → Aborted` marker.
3. Compute **unprocessed set** = BATCH_LOG batches \ log_maintenance.md maintain
   batches. Sort oldest-first by `batch_id` (monotonic timestamp string sort).

   **`batch_id` is `YYYYMMDD-HHMMSS`** — the UTC instant the producing tick
   acquired its lock, nothing else. Maintain never mints one: it carries across
   the id of the `/minder:mem:process` batch it is integrating, so a malformed id
   propagates rather than originates here. Sorting depends on the format
   (lexicographic sort is only chronological because the format is fixed), and
   so does every downstream consumer that orders by filename prefix. If an
   inherited id does not match that shape, that is the process batch reporting a
   defect — surface it, do not copy it forward.
4. If `--batch <id>` given:
   - Validate `_system/state/batches/{id}-process.md` file exists — if not, abort with
     `"Error: batch {id} not found in _system/state/batches/"` and exit immediately.
   - Check if `{id}` appears in log_maintenance.md as already processed. If yes:
     - Without `--force`: abort with warning
       `"Batch {id} already integrated (log_maintenance.md entry exists). Re-running will duplicate CLARIFICATIONS and may duplicate thread entries. Pass --force to proceed, or omit --batch to skip."`
     - With `--force`: proceed with unprocessed set = `{id}` and log the force
       flag in log_maintenance.md entry Errors/Warnings section.
   - If not in log_maintenance.md: unprocessed set = `{id}`.
5. If unprocessed set is empty (and not `--batch`): report
   `"No unprocessed batches — nothing to integrate."` and **exit immediately**.
   No lock, no further reads.

---

## Concurrency Lock

Runs only when unprocessed set is non-empty.

1. Check `_sources/.maintain.lock`. If exists → report to user and abort.
   If stale (>2 hours old), warn user and offer manual deletion; do not
   auto-delete.
2. Create `_sources/.maintain.lock` with content:
   `{ISO timestamp} — maintain run, PID {pid}, batches: {ids comma-separated}`.
3. **Finally semantics:** lock MUST be deleted in ALL exit paths — normal
   completion, skip, malformed abort, exception. Implementation: wrap Steps 1–9
   in try/finally, delete in finally.

---

## Step 0.0: Regenerate Constitution Derived Views

Invoke `/minder:mem:regen-constitution` (or run `python3 _system/scripts/regen_all.py`)
as the very first action of the run, before the per-batch loop opens.

The pattern-detect sub-step (§Step 7.5) queries the active constitution tree
to dedupe new candidates against existing principles; SOUL.Values lands in
Step 7 CURRENT_CONTEXT via its auto-zone. Both rely on derived views being
fresh relative to `0_constitution/`.

Consistency rule for the whole platform: every pipeline that reads a derived
view regenerates first. Cost is ~100 ms. Failure is fatal — report the
underlying script error and abort the run.

---

## Per-Batch Loop — Steps 1–6 + per-batch log_maintenance.md write

Iterate unprocessed batches **oldest-first**. Each iteration runs Steps 1–6
for that single batch, then writes its log_maintenance.md entry **before**
moving to the next batch. This protects idempotency across crashes: if the
run dies mid-loop, already-written entries mark their batches as processed
and a retry skips them.

After the loop exits, Step 7 (CURRENT_CONTEXT regen) runs once per run.
Step 7 does not produce its own log_maintenance.md entry — the last batch's
entry (written at end of its iteration) records the final
`CURRENT_CONTEXT.md: regenerated` note retrospectively, updated via edit
after Step 7 completes.

---

## Step 1: Load & Parse Batch

1. Load `_system/state/batches/{batch_id}-process.md`. Read entire file.
2. Parse YAML frontmatter. Required keys: `batch_id`, `timestamp`, `processor`,
   `format_version`, `sources`, `records`, `notes`, `tasks`, `events`,
   `threads_opened`, `threads_resolved`, `clarifications_raised`,
   `people_candidates_appended` (optional — a batch without this key is read
   as 0: no warning, no `batch-version-unknown` escalation).
3. Parse body sections by `## Heading` markers (per `_system/docs/batch-format.md` §Sections).

### Malformed handling (best-effort, never hard-fail)

For each anomaly: apply workaround, raise CLARIFICATION with the concrete
reason code below, continue processing.

| Anomaly | Workaround | Reason code |
|---|---|---|
| Missing / invalid frontmatter | Extract what parses; use section bodies as fallback metadata (batch_id from filename) | `batch-malformed-frontmatter` |
| Unknown `format_version` | Assume current spec semantics per `_system/docs/batch-format.md` | `batch-version-unknown` |
| Required section missing entirely | Treat as empty | `batch-missing-section` |
| Header count ≠ actual list length | Use actual list count; flag header | `batch-counts-inconsistent` |
| Count negative / non-numeric | Use list-based count | `batch-counts-anomaly` |
| `[[note-id]]` reference to non-existent file | Skip linkage for that ref | `batch-dangling-reference` |
| People Update references unknown person id (not in PEOPLE.md) | Skip tier check for that person | `batch-unknown-person` |

CLARIFICATIONS written in Step 8 (aggregated with run-level items).

---

## Step 2: Thread Detection (open new threads)

### Input

- Current batch: `## Records Created`, `## Knowledge Notes Created`,
  `## Tasks Extracted` (task descriptions, `deadline:`, and `From:` links)
- Live: `_system/TASKS.md ## Waiting` (existing waiting tasks)
- Live: `_system/state/OPEN_THREADS.md ## Active` (to avoid duplicates)

### Pipeline

**2.1 Collect candidates.** For each new record and each new decision-type
knowledge note, apply LLM reasoning:

> Is this starting a new **strategic expectation** that spans multiple tasks
> and takes time to resolve (waiting-for-response, needs-decision, needs-research,
> blocked)? Or is it operational detail (single task, fact captured, no blocking
> expectation)?

Strategic candidate = umbrella ожидание. Operational = single action, already
covered by TASKS.md.

**2.2 Dedup against existing active threads.** For each candidate, scan
`OPEN_THREADS.md ## Active`:
- People overlap: candidate.People ∩ thread.People ≠ ∅
- Topic overlap: LLM semantic match over titles + Context fields

If strong match (same umbrella) → DO NOT open new thread. Instead:

**(a) Merge into Source field.** Add `[[{batch-record-id}]]` into the existing
thread's `Source:` field. Source field comes in two live formats — normalize
before append:

- **Single-link form** (current bootstrap output):
  `- Source: [[{existing-id}]]`

  Convert to multi-link inline form:
  `- Source: [[{existing-id}]], [[{batch-record-id}]]`

- **Multi-link inline form** (comma-separated on one line):
  `- Source: [[{id1}]], [[{id2}]]`

  Append: `- Source: [[{id1}]], [[{id2}]], [[{batch-record-id}]]`

Dedup: if `{batch-record-id}` already present in Source — skip the Source
append, continue to (b).

**(b) Track for back-ref write.** Record this `(batch-record-id, existing-thread-id)`
pair in the run's back-ref worklist. Step 3 will write the `threads:` back-ref
into the record's frontmatter — same treatment as newly-created threads. This
ensures existing threads benefit from structural matching in future Step 5
Signal 2 runs.

Skip to next candidate.

**2.3 Strategic grain filter.** Per SYSTEM_CONFIG Data & Processing Rules:
- Thread ≥ 2 related tasks OR 1 waiting-for-response expectation that doesn't
  resolve in single-call action
- Thread < 2 weeks to resolve expected (heuristic, not strict)
- Reject single-task candidates: log in internal state for Step 8 report,
  no CLARIFICATION needed (operational-by-design is not ambiguous)

**2.4 Ambiguity gate.** LLM confidence about «new strategic thread?»
< 90% → CLARIFICATION `thread-detection-ambiguous` with:
- Candidate source record id + batch-id
- Arguments for (strategic signals)
- Arguments against (operational signals)
- **Suggested action:** `open-thread` | `skip` | `merge-into-existing-thread-X`

Do NOT create the thread. Owner resolves.

**2.5 Create new thread** for candidates that pass filters AND ambiguity gate.

Thread id: `thread-{YYYYMMDD}-{semantic-slug}` where date = batch timestamp
(UTC date part). Slug: 3–5 kebab-case keywords from title. Uniqueness check
against OPEN_THREADS.md — if collision, append `-2`, `-3`.

Entry format in `OPEN_THREADS.md ## Active` — use `###` heading to match
existing bootstrap-generated threads:

```markdown
### {thread-id}: {thread title — strategic umbrella в одну строку}

- Status: {waiting-for-response | needs-decision | needs-research | blocked}
- Since: {YYYY-MM-DD — batch timestamp UTC date}
- People: {person-id1, person-id2, ...} (from related records' `people:`)
- Source: [[{record-id1}]], [[{note-id1}]], [[{note-id2}]]
- Context: {2–4 sentence summary from LLM: what we're waiting for, why it matters, what blocks what}
- Related Tasks: {task-id1, task-id2, ...} (from batch `## Tasks Extracted` + any matching TASKS.md Waiting items)
- hub: [[{hub-id}]]   # populated in Step 4; omit line if no hub match
```

Append new thread block after the last existing `### thread-...` in `## Active`
(preserving existing order), before the `---` separator or `## Resolved` section.

### Update OPEN_THREADS.md header (precise operation)

Parse existing header:

```
**Last Updated:** {YYYY-MM-DD}
**Active:** {A} | **Resolved:** {R}
```

Regex: `\*\*Active:\*\* (\d+) \| \*\*Resolved:\*\* (\d+)`.

Update:
- `{A}` → `{A + N_new_threads_opened_this_batch}`
- `{R}` → unchanged (maintain does not apply closures)
- `**Last Updated:** {YYYY-MM-DD}` → today's date (UTC date part of run start)

Preserve all other lines. Rewrite entire file with the header swap.

Also update frontmatter `modified:` to today's date if present.

---

## Step 3: Back-Reference Write

Back-ref worklist = union of:

- **(A) New threads** created in Step 2.5 — each thread's Source list pairs
  with that thread-id
- **(B) Merged records** from Step 2.2.(b) — each `(batch-record-id, existing-thread-id)`
  pair recorded there

Both groups follow identical write logic:

1. For each `(record-or-note-id, thread-id)` pair in the worklist:
   - Locate file: scan `_records/meetings/` + `_records/observations/` for record ids, PARA folders
     (`1_projects/`, `2_areas/`, `3_resources/`, `4_archive/`) for knowledge
     note ids. If not found → skip, raise `batch-dangling-reference`.
   - Add the back-reference with the helper — never by editing the YAML:

     ```python
     import sys; sys.path.insert(0, "_system/scripts")
     import _common
     added = _common.append_frontmatter_list_value(
         path, "threads", thread_id, modified="{YYYY-MM-DD}")
     ```

     `True` — added. `False` — already present, nothing written and no
     `modified:` churn. `None` — the frontmatter will not parse, or `threads:`
     holds something that is not a list; that file is left untouched and
     counted, never repaired by guesswork. Body is preserved verbatim by
     construction.

     A list built by hand is a list that can be built wrong, and a note whose
     frontmatter stops parsing is invisible to every later scan rather than
     just missing a field. This runs by the hundred per batch, so the odds
     compound.
2. Track count `back_refs_written` for Step 8 report. Report split:
   - `N_backrefs_new_threads` (from worklist group A)
   - `N_backrefs_merged_threads` (from worklist group B)

### Idempotency

Back-ref write is idempotent by design (check-before-append). Safe on retry.
Both new-thread and merged-thread writes use the same check-append logic.

### Why

- Structural (not fuzzy) match for Step 5 Signal 2 in future batches — works
  equally for new AND existing threads once first record with that topic
  lands
- Navigation: from a record/note file, owner can jump to the linked strategic
  thread via frontmatter `threads:` list

---

## Step 4: Hub Linkage

For each thread created in Step 2:

**4.1 Hub search.** Glob `5_meta/mocs/*.md`. For each hub:

- **Primary:** people overlap — hub frontmatter `people:` ∩ thread.People.
  If hub has no `people:` frontmatter, skip primary criterion for this hub.
- **Secondary:** keyword/topic overlap — LLM semantic match over hub title +
  `## Ключевые выводы` top bullets (or `## Текущее понимание` if first is absent)
  vs thread title + Context.

Score each hub: `(people_overlap_count * 2) + topic_relevance_score`.
Topic relevance — LLM judgment 0–3:
- 0 = unrelated (hub's topic domain differs from thread's core topic)
- 1 = tangentially related (shared person but different problem domain)
- 2 = clearly related (thread's topic is a subtopic of hub)
- 3 = core match (thread is central expectation within hub's current focus)

**4.2 Ambiguity gate:**

**HARD RULE:** `topic_relevance ≥ 1` is **required** for any linkage. A hub with
only people overlap and `topic_relevance = 0` is NEVER linked regardless of
score — prevents hub bloat from incidental people overlap. This overrides the
score threshold below.

After topic filter applied:

| Match result (topic_relevance ≥ 1 candidates only) | Action |
|---|---|
| 0 hubs pass topic filter | Skip linkage. Thread stays with empty `hub:` field. This is OK — not every thread maps to a hub. If thread clearly needs hub but none exists — consider suggesting new hub creation (`/minder:mem:lint` territory) |
| 1 hub passes topic filter with score ≥ 2 | Apply linkage (4.3) |
| 2+ hubs pass topic filter with score ≥ 2 | CLARIFICATION `thread-hub-ambiguous` with candidate hubs + scoring + topic_relevance for each. Skip until resolved |
| 1+ hubs pass topic filter but all with score < 2 | Skip linkage (people signal too weak + mediocre topic) |

**4.3 Apply linkage** (when exactly one hub matches):

1. In `OPEN_THREADS.md`: set `hub: [[{hub-id}]]` field in thread entry.
2. In `5_meta/mocs/{hub-id}.md`:
   - Append bullet to `## Открытые вопросы` section:
     `- [[{thread-id}]] — {thread title} (since {YYYY-MM-DD})`
   - If section doesn't exist — create it using this placement priority:
     1. **Before `## Ключевые выводы`** if that section exists
     2. Else **before `## Changelog`** if that section exists
     3. Else **at end of body** (append after last content line)
   - Update frontmatter: `modified: {today}`. Do NOT touch `last_mention` —
     that's updated by `/minder:mem:process` when notes are added. Maintain only
     adds structural metadata (thread linkage), not new mentions.

No hub Changelog entry added by maintain — that's semantic evolution, not
structural link. `/minder:mem:lint` handles semantic drift if it becomes visible.

**Hub privacy and member_concepts (autonomous, owner-edits preserved).**
Hubs do not carry a `concepts:` field — `member_concepts[]` is
manifest-only. Privacy trio derivation invokes
`_system/scripts/_common.py::recompute_hub_trio()` — the SAME helper
called by `/minder:mem:process` hub C/D, single source of truth.

The helper fills MISSING trio fields from member-note trios:
- `origin` (when missing) ← dominant member origin; tie → `personal`.
- `audience_tags` (when missing) ← intersection of member-note
  audiences; fail-closed default `[]`.
- `is_sensitive` (when missing) ← any-member contagion.

**Owner-edit preservation contract.** Trio fields already present
on the hub frontmatter are NEVER overwritten. Owner manual edits
survive across every maintain touch. No CLARIFICATIONS, no clobbering.

**Never hand-edit the frontmatter to apply it.** Read, recompute and write
are one call:

```python
import sys; sys.path.insert(0, "_system/scripts")
import _common
result = _common.apply_hub_trio(hub_path, member_trios, modified="{YYYY-MM-DD}")
```

It returns `{"changed", "events", "trio", "_engine_derived"}`, writes only
when the trio really moved, stamps `modified:` only then, and returns `None`
for a hub whose frontmatter will not parse — which is left untouched and
reported, never rewritten from a guess.

Editing the YAML by hand instead is how a hub was written as
`{is_sensitive: true}` — flow style into a block-style frontmatter — and
stopped parsing altogether: not one wrong field, but a file invisible to every
downstream scan. The write is deterministic, so it belongs to a function
rather than to whoever is running tonight.

**Hub manifest emission for this batch.** When this maintain run
emits its batch manifest (`_system/state/batches/{ts}-maintain.json`),
each hub touched in this run gets a `hubs.updated[]` entry with:

- `path`, `checksum_sha256`, `domains` (existing fields)
- `member_concepts[]` — every member-note `concepts:` value passed
  through `_system/scripts/_common.py::normalize_concept_name()`,
  Nones dropped, deduplicated. Non-conformant raw values are silently
  normalised; entries that cannot be normalised are silently dropped.
  Lint Scan A.7 stays silent on this manifest because every emission
  is conformant by construction.
- `origin`, `audience_tags`, `is_sensitive` — the auto-recomputed
  values from the rules above (also written to hub frontmatter).

---

## Step 4.5: Concept Registry Regeneration

After hub linkage settles new structural edges, regenerate the
canonical concept registry from the union of corpus frontmatter
(`concepts:` arrays) and prior batch manifests
(`concepts.upserts[]` for type / subtype). The registry is the
loaded-vocabulary input to `/minder:mem:process` Step 3.4.5 (concept-matcher
subagent) — in both inbox-scan and `--reprocess-corpus` modes.

**Invocation.** Run from the maintain orchestrator with:

```bash
python3 _system/scripts/build_concept_registry.py
```

No tunables — single flat registry sorted by mentions descending. The
matcher subagent in `/minder:mem:process` Step 3.4.5 loads the entire file
(Sonnet handles it cheaply).

The script is deterministic, idempotent, and pure — no LLM. It walks
`_records/{meetings,observations}/`, PARA folders, `5_meta/mocs/`,
and `_system/state/batches/*.json`, then writes
`_system/registries/CONCEPTS.md` from scratch each invocation.

**Owner-edit preservation contract.** The owner's only mutable column
is `aliases` (comma-separated list of older / equivalent names that
get rewritten to the canonical name on the next `/minder:mem:lint` Scan A.7
pass). On rebuild, the script reads the prior `CONCEPTS.md`, parses
the `aliases` column verbatim, and re-attaches it to the
freshly-aggregated row. Every other column is auto-derived; owner
edits to those columns are silently overwritten on regen. Aliases for
concepts that no longer appear in any corpus / batch source are
preserved as zero-mention rows so the lint rewrite is never lost.

**Logging.** Capture stdout (`{"ok": true, "files_scanned": N,
"mentions_seen": M, "batches_read": K, "total_concepts": T,
"total_mentions": U}`) and stderr structured events
(`concepts-registry-rebuilt`). Include the row delta (prior
`total_concepts` → new `total_concepts`) in the per-batch
log_maintenance.md entry written in Step 6.5 and in the maintain
manifest's `stats` section.

**Failure mode.** If the script exits non-zero, surface the failure
to log_maintenance.md as `concepts-registry-failed` with stderr
captured, and continue with the rest of the maintain pipeline — the
prior CONCEPTS.md remains in place. Do NOT raise a CLARIFICATION;
the registry is rebuildable on the next maintain pass and downstream
SKILLs degrade gracefully when CONCEPTS.md is stale (the matcher
subagent still works against the older vocabulary, just without the
freshest entries).

---

## Step 5: Thread Closure Suggestion (suggest-only)

**Applies to ALL active threads** — existing + freshly created in Step 2.

For each thread, evaluate 4 signals. **Graceful field handling:** older
bootstrap-generated threads may not have `Related Tasks` or `hub:` fields.
A missing field means the corresponding signal cannot fire (neither positive
nor negative) — it's excluded from scoring, not counted as a failed signal.
Note this in CLARIFICATION if the thread scores closure from only 2–3
available signals.

### Signal 1 — Tasks

**Prerequisite:** thread has `Related Tasks` field. If absent → **signal
excluded from scoring** (not fired, not counted). Log as «signal-1-unavailable»
in CLARIFICATION evidence if this thread reaches closure threshold.

If `Related Tasks` present, check each task id against `TASKS.md`:
- task in `## Done` (or marked `cancelled` / `stale`) → task counts as done
- task in `## Waiting` or `## Actions` → not-done
- task id not found in TASKS.md → unknown; raise `thread-dangling-task-ref`;
  count as not-done for scoring (conservative)

**Signal fires** if ALL related tasks are done/cancelled/stale AND
`Related Tasks` list is non-empty.

### Signal 2 — Explicit closure

Scan batch records + notes for closure references to this thread:

- **Structural match (priority):** open each record/note body-or-frontmatter.
  If frontmatter `threads:` list contains this thread-id AND record/note
  contains closure-marker language → fire signal. Closure markers (LLM
  semantic match, not regex):
  - «закрыли», «решили», «решение принято», «получили ответ», «больше не ждём»
  - «выкатили», «задача закрыта», «done», «resolved», «вопрос снят»
- **Fuzzy fallback:** no `threads:` in batch records — LLM judgment over
  people+topic overlap + closure-marker presence. Must have ≥2 of: person
  overlap, topic overlap, closure-marker. Lower confidence than structural.

**Signal fires** if structural match found, or fuzzy fallback confidence
≥ 70%.

### Signal 3 — Staleness

- Thread `Since` > 4 weeks from batch timestamp
- AND no mentions of thread.People in batch's records/notes

**Signal fires** if both conditions hold.

### Signal 4 — Hub resolution

**Prerequisite:** thread has `hub: [[{hub-id}]]` field. If absent or empty →
**signal excluded from scoring** (same semantics as Signal 1).

If present:
- Read hub's `## Ключевые выводы` section
- Check for bullet referencing this thread's title/topic (LLM semantic match)

**Signal fires** if hub already captured a resolution for this thread.

### Scoring & CLARIFICATION

- **≥ 2 signals fire** → CLARIFICATION `thread-closure-suggested`
- **< 2 signals** → keep open, no action

Excluded signals (missing field) are neither positive nor negative for
scoring. Example: thread with no `Related Tasks` and no `hub:` (Signals 1
and 4 unavailable) closes only via Signals 2+3 together.

CLARIFICATION content — parsable fields + rich free-form:

```markdown
### {YYYY-MM-DD} — thread-closure-suggested: {thread-id}

**Type:** thread-closure-suggested
**Subject:** {thread-id}
**Source:** batch-{batch_id}
**Suggested action:** close-thread | close-partial | keep-thread-open
**Confidence tier:** surfaced (HARD RULE — closure never auto-applied)
**Signals fired:** {N}/4
  - Signal 1 (tasks): {fired | not-fired} — {evidence: task-ids + статусы}
  - Signal 2 (explicit closure): {fired | not-fired} — {evidence: record-id + Quote если fuzzy}
  - Signal 3 (staleness): {fired | not-fired} — {evidence: since {date}, age {N} weeks}
  - Signal 4 (hub resolution): {fired | not-fired} — {evidence: hub-id + bullet}

**Quote:** > «{verbatim if Signal 2 via closure-marker}»   # optional

**Context:** {2–4 sentence paragraph: что за тема thread, кто participants, какие signals сошлись и почему, текущий hub state если linked, candidate resolution rationale. Self-contained для LLM review.}

**Suggested resolution text:** {1–2 sentences готовые для вставки в hub's `## Ключевые выводы`}

**Uncertainty:** {what LLM was unsure about — edge cases, remaining tasks, partial closure nuances}

**To resolve:** Run `/minder:mem:resolve-clarifications` — the skill diffs OPEN_THREADS.md (move entry to `## Resolved` + add `Resolved:` + `Resolution:` fields) and hub edits (`## Открытые вопросы` remove bullet, `## Ключевые выводы` append resolution) on owner confirm.
```

**Maintain NEVER moves thread to Resolved.** Owner does this manually.

---

## Step 6: Tier Promote & Mention Consistency

### Input

Batch `## People Updates` section — one row per person:
`- {person-id} | {change-type} | mentions: {X}→{Y} | tier: {T} ({note})`

### 6.1 Mention consistency check

For each row:
1. Read `3_resources/people/PEOPLE.md` row for `{person-id}`.
2. Compare PEOPLE.md `Mentions` column with batch-reported `Y`.
3. If not equal → CLARIFICATION `mention-count-drift` with:
   - person-id, batch-expected Y, PEOPLE.md actual Z, diff
   - Note: may indicate lost write or concurrent edit in `/minder:mem:process`

**Maintain does NOT edit PEOPLE.md counts.** Only logs anomaly.

### 6.2 Tier promote check

For each row (assuming PEOPLE.md has person — if not, raise `batch-unknown-person`):

1. Compute **expected tier** per SYSTEM_CONFIG rules:
   - Profile exists in `3_resources/people/{id}.md` OR mentions ≥ 8 → **Tier 1**
   - mentions 3–7 (no profile) → **Tier 2**
   - mentions 1–2 (no profile) → **Tier 3**
2. Read **current tier** from PEOPLE.md `Tier` column.
3. Compare:
   - current == expected → no action
   - expected > current (promote: 3→2 or 2→1) → CLARIFICATION
     `tier-promote-suggested` (see format below)
   - expected < current (demote direction) → skip. Demote is `/minder:mem:lint`
     territory — never maintain.

CLARIFICATION format:

```markdown
### {YYYY-MM-DD} — tier-promote-suggested: {person-id}

**Type:** tier-promote-suggested
**Subject:** {person-id}
**Source:** batch-{batch_id}
**Suggested action:** promote-tier | keep-thread-open (keep current)
**Confidence tier:** surfaced (HARD RULE — PEOPLE.md Tier column never auto-applied)
**Mentions:** {old}→{new}
**Current tier:** {T_current}
**Expected tier:** {T_expected} (per SYSTEM_CONFIG thresholds)
**Recent contexts:** {3–5 most recent record/note titles referencing this person}

**Context:** {2–4 sentence paragraph: кто этот person (role, org from PEOPLE.md), recent activity pattern (last N records/topics), relationship density signal (coordinator / implementer / external stakeholder), candidate action rationale.}

**To resolve:** Edit `3_resources/people/PEOPLE.md` — change `Tier` column for {person-id} to {T_expected}. Profile generation for Tier 1 without existing profile — handled by `/minder:mem:lint` weekly.

**Uncertainty:** {if LLM sees signals suggesting relationship density doesn't match raw count, note here}
```

**Maintain does NOT edit PEOPLE.md Tier column.** Owner applies manually.

---

## Step 6.5: Write log_maintenance.md entry for this batch (IN-LOOP)

Append ONE entry to `_system/state/log_maintenance.md` for the current batch,
newest first (prepend to the entries block after `<!-- Entries append BELOW this line, newest first -->`).

Format:

```markdown
## {ISO UTC timestamp of this batch iteration} | maintain | by: minder:mem:maintain | batch: {batch_id}

### Updates
- Threads: +{N_opened_this_batch} opened, {N_merged_this_batch} existing threads received new batch-records (via Source+back-ref merge), 0 closed (closure is manual — see Suggestions)
- Back-references: +{N_backrefs_this_batch} records/notes enriched with `threads:` frontmatter ({N_backrefs_new} for new threads + {N_backrefs_merged} for merged into existing)
- Hubs: +{N_hubs_linked_this_batch} threads linked
- Mention consistency: {N_checked_this_batch} checked, {M_drifts_this_batch} drifts flagged
- Tier: 0 applied (suggest-only, see Suggestions for pending promotes)
- CURRENT_CONTEXT.md: pending (regenerated post-loop; see last-batch entry for confirmation)
- INDEX.md: pending (regenerated post-loop; see last-batch entry for confirmation)

### Auto-Fixes
- (none — maintain does not auto-fix, suggest-only)

### Suggestions → CLARIFICATIONS
- {total_items_this_batch} items raised: {breakdown}

### Errors / Warnings
- {batch anomalies specific to this batch, or `(none)`}
- {if `--force` used on already-processed batch: "Re-run via --force, duplicate risk acknowledged"}
```

After this write, a crash before the next batch iteration leaves the system
in a recoverable state: retry picks up from the next unprocessed batch.

Proceed to next batch or, if this was the last, exit the loop.

### 6.6 Emit per-batch JSON manifest

Alongside `log_maintenance.md`, emit a machine-parseable JSON
manifest of this maintain batch's state changes. Schema:
`_system/docs/manifest-schema/v{N}.json` (reference doc:
`manifest-schema/README.md`) with `processor: "minder:mem:maintain"`. Top-level: `batch_id` (matches the
upstream /minder:mem:process batch_id this maintain run integrated),
`timestamp` (this maintain iteration's UTC start),
`format_version: "2.1"`, `processor: "minder:mem:maintain"`, plus the
per-skill sections relevant to maintain output:
`hubs.updated[]` (with `member_concepts[]` derived via
`_common.py::normalize_concept_list`, plus the post-recompute
privacy trio from `recompute_hub_trio`), `tier1_objects.people`
on tier promotions, `threads_opened[]` / `threads_resolved[]`
(unique to maintain — empty in /minder:mem:process manifests), `stats{}`.

Assemble in memory, then invoke:

```bash
python3 _system/scripts/emit_batch_manifest.py \
    --input <path-to-temp-json> \
    --output _system/state/batches/{batch_id}-maintain.json
```

The helper applies the same autonomous concept/audience normalisation
and trio coercion as on /minder:mem:process emission. Conformant output by
construction. Emission events to stderr — log to log_maintenance.md
Auto-Fixes section under fix-id `manifest-emit-autofix` if any.

**Then verify what actually landed — in this tick, not tonight.**

```bash
python3 _system/scripts/lint_manifest_schema.py \
    --batches-dir _system/state/batches --schemas-dir _system/docs/manifest-schema --all \
  | grep '"batch": "{batch_id}-maintain.json"'
```

A `"kind": "violation"` line here means the file on disk does not honour the
manifest contract. Treat it exactly as an emitter `exit 3`: the manifest is not
valid, so do NOT append the BATCH_LOG row, and surface it in the run report.

This check exists because the emitter can only refuse what it is given. A tick
that assembles the JSON and writes it to `batches/` **without invoking the
emitter** bypasses every guarantee above, and the only thing that noticed was
the nightly lint — a full day later, on a manifest a downstream consumer may
already have read. It has happened: a tick invented `batch_id: 20260807-processtick`
where the format is `YYYYMMDD-HHMMSS`. Verifying the artefact rather than
trusting the procedure closes that gap whatever its cause.

---

## Post-Loop — Steps 7–9

Run **once** after the per-batch loop completes.

---

## Step 6.7: Biometric Weekly Worker — After-Batch with Weekly Gate

Triggered on every `/minder:mem:maintain` after-batch invocation. **No new
scheduler-prompt added** — re-uses the existing maintain tick.

### Per-source loop

Biometric records + derived state are namespaced per wearable device
under `<source>/` (e.g. `garmin`, `oura`). The worker + snapshot run
**once per active metric-day source** — every device directory that has
records under `_records/biometric/*/`. Enumerate active sources by
listing the immediate subdirectories of `_records/biometric/`; each
subdirectory name is a `source_id`. Run the steps below for each in turn
(order does not matter — sources are independent).

### Idempotency gate (per source)

For source `<id>`, read `_system/state/biometric/<id>/last_weekly_run.txt`.
If contents equal the current ISO week (`YYYY-Www`) → log
"biometric weekly <id>: noop" and skip that source. Otherwise the
worker proceeds for it.

This means the worker runs at most once per ISO week **per source**, on
the first `/minder:mem:maintain` invocation of that week, regardless of weekday.

### Pre-checks (per source)

1. `_records/biometric/<id>/` contains ≥ 14 records. Below that,
   log `pre-checks-failed <id>` and skip that source — Tier II requires
   substantial data.
2. If `_records/biometric/<id>/` has ≥ 14 records BUT no
   `_system/state/biometric/<id>/correlations-*.json` exists yet → enter
   **backfill mode** for that source (worker iterates completed ISO weeks
   chronologically, produces per-week outputs, then the current sentinel
   week).
3. Otherwise → normal current-week mode.

### Steps (per source `<id>`)

1. Call `biometric_weekly_worker.run(base, source_id="<id>", batch_id=…, manifest_out=…)`.
   The worker (reading + writing only the `<id>/` namespace):
   - Loads thresholds (template → live → .local layered merge).
   - Reads last 56 days of `_records/biometric/<id>/` Key Numbers.
   - Phase 1: Pearson over metric pairs at lag 0..3, anomaly clusters.
   - Phase 2: lexicon-based affect tag extraction over `_records/observations/`
     + `_records/meetings/`, point-biserial correlations vs metrics
     at lag 0..2, structural `meeting_heavy_day` injection.
   - Calibration: per-metric × severity fire-rate observation, drift
     detection vs expected (light ≈ 16%, medium ≈ 7%, strong ≈ 2%);
     proposes new σ when drift factor outside [0.5, 2.0] for ≥ 3
     consecutive weeks.
   - Writes `_system/state/biometric/<id>/correlations-{YYYY-Www}.json`
     per processed week (1 file in normal mode; up to ~8 in backfill).
   - Writes owner-readable `_system/views/biometric/<id>/weekly-{YYYY-Www}.md`
     per processed week.
   - Appends per-week observation to `_system/state/biometric/<id>/calibration-history.json`.
   - Surfaces `biometric-threshold-drift` CLARIFICATIONs (rate-limited
     by `insights-config.yaml::biometric_max_hints_per_week`).
2. After the worker completes successfully for `<id>`, write current ISO
   week into `_system/state/biometric/<id>/last_weekly_run.txt`
   (single line, no trailing newline).

### Health Snapshot integration into Step 7 (CURRENT_CONTEXT regen)

When CURRENT_CONTEXT.md regenerates (Step 7 below), inject the
`## Health Snapshot` block. Render **one block per active metric-day
source** by calling `render_health_snapshot.render(base, source_id="<id>")`
for each source (so CURRENT_CONTEXT shows both `garmin` and `oura`).
Place the blocks AFTER the `## Focus` block, BEFORE the
Tasks/Meetings/Threads blocks — Health Snapshot is contextual to focus
declarations.

If a source's `render()` returns empty (e.g. no biometric records yet
for that device), skip its block silently.

### Failure semantics

Per-step try/except. A failed worker step logs the error and does not
block subsequent maintain steps. `last_weekly_run.txt` is updated only
when the worker actually emitted output — otherwise next maintain run
retries. Treat worker failure as a soft warning, not a hard error.

### Lock matrix

Reuses existing `/minder:mem:maintain` lock — biometric worker runs inside
the same critical section. No new lock entries. CLARIFICATIONs raised
follow normal `/minder:mem:resolve-clarifications` flow.

### Manifest emission

Each emitted correlations-week file + weekly-view file (across all
sources) contributes a row under `derived_views.biometric` section of
the maintain batch manifest, carrying privacy trio (`is_sensitive: true`,
`audience_tags: []`, `origin: personal`). Tier II derived files are
NOT new content (per Skill Write Territory rules) — they are
recomputable from `_records/biometric/<source>/`.

---

## Step 6.8: Activity Weekly Worker — After-Batch with Weekly Gate

Triggered on every `/minder:mem:maintain` after-batch invocation, symmetric to the
biometric weekly worker (Step 6.7) but for the activity (computer-usage)
metric-day family. **No new scheduler-prompt added** — re-uses the same
maintain tick. Biometric and activity workers are independent: each gates on
its own family namespace, so a biometric source never triggers an activity
run and vice versa.

### Per-source loop

Activity records + derived state are namespaced per source under
`_records/activity/<source>/` (e.g. `activitywatch`). Enumerate active
sources by listing the immediate subdirectories of `_records/activity/`;
run the steps below for each (sources are independent).

### Idempotency gate (per source)

For source `<id>`, read `_system/state/activity/<id>/last_weekly_run.txt`.
If it equals the current ISO week (`YYYY-Www`) → log
"activity weekly <id>: noop" and skip. Otherwise the worker proceeds —
at most once per ISO week per source, on the first `/minder:mem:maintain` of that
week regardless of weekday.

### Pre-checks (per source)

1. `_records/activity/<id>/` contains ≥ 14 records. Below that, log
   `pre-checks-failed <id>` and skip.
2. ≥ 14 records BUT no `_system/state/activity/<id>/weekly-*.json` yet →
   **backfill mode** (worker iterates completed ISO weeks chronologically,
   then the current sentinel week).
3. Otherwise → normal current-week mode.

### Steps (per source `<id>`)

1. Call `activity_weekly_worker.run(base, source_id="<id>", batch_id=…, manifest_out=…)`.
   The worker (reading + writing only the `<id>/` namespace):
   - Reads each ISO week's `_records/activity/<id>/*.md` Key Numbers + the
     Summary "Top categories:" line; **working days only** — days with
     `active_h < 0.5` are absence, not signal, and are skipped.
   - Computes a weekly rollup: median (+ min/max) of the scores
     (combined / productivity / focus); medians of switching, focus and
     rhythm metrics; weekly totals (sustained focus, meetings); the
     category-time trend (sum seconds per category across the week, ranked);
     the top recurring death-loop pairs (aggregated `top_death_loop` +
     `distracting_loop_count`); a rhythm summary (late-night vs
     early-morning day counts); and the week-over-week delta vs the prior
     week's rollup if it exists.
   - Writes `_system/state/activity/<id>/weekly-{YYYY-Www}.json` (machine
     rollup) per processed week.
   - Writes owner-readable `_system/views/activity/<id>/weekly-{YYYY-Www}.md`
     (the at-a-glance human surface; also the weekly-insights lens input)
     with privacy frontmatter `origin: personal / audience_tags: [] /
     is_sensitive: true`.
2. After the worker emits output for `<id>`, write the current ISO week
   into `_system/state/activity/<id>/last_weekly_run.txt`.

### Failure semantics

Per-step try/except, same as Step 6.7. A failed worker step logs the error
and does not block subsequent maintain steps. `last_weekly_run.txt` updates
only when the worker actually emitted output.

### Lock matrix

Reuses the existing `/minder:mem:maintain` lock — runs inside the same critical
section. No new lock entries.

### Manifest emission

Each emitted rollup file + weekly-view file contributes a row under
`tier2_objects.activity` of the maintain batch manifest, carrying privacy
trio (`is_sensitive: true`, `audience_tags: []`, `origin: personal`). Tier II
derived files are NOT new content — they are recomputable from
`_records/activity/<source>/`.

---

## Step 7: CURRENT_CONTEXT Full Regen

Overwrite `_system/views/CURRENT_CONTEXT.md` entirely. Regenerate from source-of-truth:

### Input sources

| Source | Used for |
|---|---|
| `_system/SOUL.md` | `## Focus` — copy Work + Personal streams from SOUL.md |
| `_system/TASKS.md` | Waiting tasks with deadline ≤ (today + 2 days) |
| `_system/CALENDAR.md` | Events in (today, today + 7 days] |
| `_system/state/OPEN_THREADS.md` | Top 3 oldest active threads |
| Last processed batch (highest batch_id in this run) | `## Last Activity` counts |

Use **today** = date part of `generated` timestamp (UTC) written in frontmatter.

### Output format

```markdown
---
id: current-context
layer: system
generated: {ISO UTC timestamp with Z suffix}
generated_by: minder:mem:maintain
batch_id: {last processed batch_id in this run}
---

# Current Context

> Live state для thin orientation. Регенерируется `/minder:mem:maintain` после каждого batch
> и `/minder:mem:lint` nightly. Не редактируется вручную.

## Focus (from SOUL.md)

**Work:**
- {copy from SOUL.md Focus → Work}

**Personal:**
- {copy from SOUL.md Focus → Personal}

## Tasks Due by {today + 2d} (as of {today})

- [ ] {task description} — **до {date}** — [[{source-note-id}]]
- ...

(empty → `(none — no tasks due in this window)`)

## Meetings through {today + 7d} (as of {today})

- 📅 **{YYYY-MM-DD}** — {event description}
- ...

(empty → `(none)`)

## Open Threads ({N} active)

Top 3 по давности:

- **{thread-id}** — {title} ({status}, since {date})
- **{thread-id}** — {title} ({status}, since {date})
- **{thread-id}** — {title} ({status}, since {date})

Полный список — `_system/state/OPEN_THREADS.md`.

## Last Activity

- Last batch: {last_batch_id} at {last_batch_timestamp} — {notes_last} notes, {tasks_last} tasks, {events_last} events
- This maintain run: processed {N_batches} batches (first {first_batch_id} → last {last_batch_id}), +{total_threads_opened_across_run} threads opened, +{total_backrefs_across_run} back-refs, +{total_clarifications_across_run} CLARIFICATIONS raised
```

Aggregated counts (`total_*_across_run`) sum over all batches processed this
run. Empty-run case (0 batches in unprocessed set) does not reach Step 7 —
Early Exit handles it. Single-batch case writes `{N_batches} = 1`.

Use explicit absolute dates in section headers (not "Today/Tomorrow") to
eliminate ambiguity when user reads file later.

---

## Step 7.5: Pattern → Candidate Detection (once per run, post-loop)

Scan recent decision records for recurring rationale that looks like an
unstated principle. Runs once per `/minder:mem:maintain` run, after all batches
are integrated and after Step 7 has refreshed the live context. Output is
append-only into `_system/state/principle-candidates.jsonl`; no constitution
files are modified.

### Input

- All files under `_records/meetings/` and `_records/observations/` with
  `types:` including `decision`, created within the last 30 days (use
  the record's `created:` frontmatter or file mtime fallback).
- The active constitution tree, via
  `python3 _system/scripts/query_constitution.py --compact`
  (visible active principles; `--consumer` defaults to `claude-code`,
  archived and placeholder excluded).
- The current candidate buffer `_system/state/principle-candidates.jsonl`
  for dedupe.

### Pipeline

1. **Group by rationale.** Extract `rationale` (from the decision
   record's prose or the `## Rationale` section). Use LLM clustering
   to group records whose rationale expresses the same operating
   logic (semantic match; stylistic differences do not split groups).

2. **Filter.** Keep only groups where:
   - `|group| ≥ 2` records (two or more independent occurrences in the
     last 30 days)
   - No active principle statement semantically covers the group's
     rationale. Use the principle `statement` + first paragraph of
     body from `query_constitution.py` output for the comparison.

3. **Dedupe against buffer.** For each surviving group, scan
   `principle-candidates.jsonl`. Skip if an entry within the last 30
   days has an `observation` or `hypothesis` that already covers the
   same operating logic. Comparison is LLM semantic, not string match.

4. **Append candidates.** For each non-duplicate group, invoke:

   ```bash
   python3 _system/scripts/append_candidate.py \
       --situation "Recurring decision rationale across N records" \
       --observation "<short verbatim fragment if one is representative, else empty>" \
       --hypothesis "<one-line inferred principle from the group>" \
       --suggested-type principle \
       --suggested-domain <inferred-domain-or-unknown> \
       --origin personal \
       --captured-by minder:mem:maintain \
       --session-id "maintain-$(date -u +%Y-%m-%d)" \
       --record-ref "[[<most-recent-record-id-of-group>]]"  # any record kind: meeting or observation
   ```

   `--captured-by minder:mem:maintain` is not decoration: `captured_by` is read at
   F.5 promotion, and a line this step appended while claiming to come from
   an in-the-moment capture is a line whose promotion is judged on the wrong
   evidence. The flag defaults to `minder:mem:capture-candidate`, so every producer
   other than that skill names itself.

   `suggested_type: principle` is the default — recurring rationale
   rarely qualifies as `axiom` (too fundamental) or `rule` (too
   binary). Pick `unknown` over guessing wrong.

### Invariants for this step

- Do not modify any file under `0_constitution/`. Candidate surfacing
  is append-only into the buffer; promotion is `/minder:mem:lint` F.3 +
  human review territory.
- Do not reason about verdicts (aligned / violated) — that is
  `/minder:mem:process` Step 3.7.5's job. Maintain only spots *new* patterns.
- Running on an empty tree (no active principles) is valid: every
  recurring rationale becomes a candidate. Expected in early bootstrap.
- Output count feeds Step 8 log patch (see below) so each run's
  contribution is visible in `log_maintenance.md`.

### Output

A list of `{candidate_count, session_id}` consumed by Step 8.
Console trace lists each appended candidate for the run report.

---

## Step 7.6: INDEX.md Full Regen

Overwrite `_system/views/INDEX.md` entirely via deterministic Python
script. Surface-line catalog of every entry in the knowledge, archive,
constitution, and synthesis (hub) layers — faceted by PARA + `domains:`.
This is the «navigation surface» Karpathy-style: read INDEX → drill
into the right page or specialised index.

Runs **once** post-loop, after Step 7 (CURRENT_CONTEXT regen) and Step
7.5 (pattern detect). Cost is one frontmatter pass + one wikilink pass
(~600 files at current scale, sub-second).

### Invocation

```bash
python3 _system/scripts/render_index.py
```

Pure, deterministic, idempotent. No LLM. Re-running on unchanged source
data yields a byte-identical file modulo the `generated:` timestamp.
Atomic write via `INDEX.md.tmp` + `rename` — readers never see a
half-written file under concurrent access.

The script is the single source of truth for INDEX scope, format, and
sort order. The sections below mirror its behaviour for cross-skill
reference; on conflict, the script wins.

### Input sources

| Source | Section in INDEX |
|---|---|
| `1_projects/**/*.md` (excl. README, `PROJECTS.md`, `PROJECTS.template.md`) | By PARA → Projects |
| `2_areas/**/*.md` (excl. README) | By PARA → Areas |
| `3_resources/**/*.md` (excl. README, `PEOPLE.md`, `PEOPLE.template.md`) | By PARA → Resources |
| `4_archive/**/*.md` (excl. README) | Archive (rendered with `[archived]` marker) |
| `0_constitution/{axiom,principle,rule}/**/*.md` | Constitution (rendered with `tier N`; `archived` / `placeholder` skipped — surfaced in `CONSTITUTION_INDEX.md` instead) |
| `5_meta/mocs/*.md` | Hubs (rendered with `inbound_count`) |

**Out of scope by design** — each owns its own pipeline / store:

- `_records/` — operational provenance (record layer, growing
  daily; would dominate the catalog without serving the «what's in
  the wiki» question)
- `6_posts/` — outbound publishing pipeline
- `_sources/`, `_system/`, `5_meta/CONCEPT.md`,
  `5_meta/PROCESSING_PRINCIPLES.md`, `5_meta/templates/`,
  `5_meta/starter-pack/` — engine docs and scaffolds

### Per-entry rendering — knowledge / archive

For each note in PARA / archive, extract:
- `id` (frontmatter `id:`; fallback to filename stem)
- `title` (frontmatter `title:`; fallback to filename stem)
- `summary` via fallback chain (first non-empty wins):
  1. `description:` from frontmatter
  2. `title:` from frontmatter
  3. First non-empty, non-heading, non-HTML-comment prose line,
     trimmed to 100 chars + `…`
  4. Literal `_(no description)_`
- `domains` (frontmatter `domains:`; default `[]`)
- `modified` (frontmatter `modified:`; fallback to `created:`)

Row format:

```
- [[id]] — {summary} · `[domain1, domain2]` · YYYY-MM-DD
```

Archive rows prepend `[archived]` to the summary:

```
- [[id]] — [archived] {summary} · `[domains]` · YYYY-MM-DD
```

### Per-entry rendering — constitution

For each axiom / principle / rule with `status: active`, extract:
- `id`
- `title` (used as summary; statement detail lives in
  `CONSTITUTION_INDEX.md` and the principle file itself —
  surface-line discipline)
- `domain` (rendered as a single-element list)
- `priority_tier` (rendered as `tier N`)
- `last_reviewed` (fallback to `created`)

Row format:

```
- [[id]] — {title} · `[domain]` · tier N · YYYY-MM-DD
```

Grouped under `### Axioms — N`, `### Principles — N`, `### Rules — N`,
sorted by tier ascending then id.

### Per-entry rendering — hubs

For each hub in `5_meta/mocs/`, additionally extract:
- `inbound_count` — count of `[[hub-id]]` and `[[hub-id|alias]]`
  references across the base, excluding `_system/views/` (would
  self-amplify) and `_system/state/` (audit trail, not graph edges).
  Self-references inside the hub file itself are subtracted to keep
  the centrality signal honest.

Row format:

```
- [[hub-id]] — {summary} · `[domains]` · {inbound_count} inbound · upd YYYY-MM-DD
```

### Sort order within sections

- **By PARA / Archive / Cross-domain / By Domain**: `modified`
  descending (freshest first), tie-break by `id` descending
- **Constitution**: `priority_tier` ascending then `id` ascending
- **Hubs**: `inbound_count` descending (centrality first), tie-break
  by `modified` descending then `id` ascending

### By Domain / Cross-domain facet

The `## By Domain` and `## Cross-domain` sections pull from
**knowledge + archive + constitution** (NOT hubs — hubs have their own
section + dedicated `HUB_INDEX.md`). Domain headers are emitted in
descending count order; entries with no canonical-domain values land
under `### unscoped (N)` last. Unknown domain strings (drift) are
silently skipped at this layer — surfaced through lint, never INDEX.

Cross-domain row format keeps marker information so the facet stays
informative when read in isolation:

```
- [[id]] — [archived?] {summary} · [tier N?] · `[domain1, domain2]` · YYYY-MM-DD
```

### Counts in frontmatter

```yaml
generated: {ISO UTC timestamp with Z suffix}
generator: render_index.py
note_count:        {len(knowledge entries)}              # 1_projects + 2_areas + 3_resources
archive_count:     {len(archive entries)}                # 4_archive/
constitution_count: {len(active axioms + principles + rules)}
hub_count:         {len(5_meta/mocs/*.md)}
domain_count:      {len(distinct canonical domains across knowledge+archive+constitution)}
```

### Atomicity

The script writes to `_system/views/INDEX.md.tmp` then atomically
`rename`s over `INDEX.md`. Concurrent readers (lens, lint) never see a
half-written file.

### Failure mode

If `render_index.py` exits non-zero, surface
`INDEX.md: regen-failed ({error})` in the log patch (Step 8) and
continue. Per-file frontmatter parse failures are skipped silently
(consistent with `read_frontmatter()` semantics in `_common.py`); Lint
Scan A.2 normalises schema, so this is a transient state.

---

## Step 7.7: Derived Chronological-Map Render (project hubs)

Regenerate the auto-derived chronological map for each hub with
`chronological_map_mode: derived` in frontmatter (typically project
hubs). The map is rendered between `<!-- AUTO-GENERATED -->` markers
and reflects every record / knowledge note where `projects:` contains
the hub's project ID, minus records listed in `excluded_from_map`.

Hubs with `chronological_map_mode: curated` (default; trajectory and
domain hubs) are skipped — their maps stay hand-curated.

**Invocation.**

```bash
python3 _system/scripts/render_hub_maps.py --apply
```

Pass no `--root`: the default resolves the base from the script's own
location, so the command is correct from any working directory. `--root .`
is only correct when the cwd happens to be the base — from anywhere else it
scans an empty tree, reports `hubs_total: 0`, exits 0 and reads as clean.

The script is deterministic, idempotent, and pure — no LLM. Re-running
on unchanged source data yields zero file modifications.

Per-hub event JSONL on stdout (`hub`, `project_id`, `members`,
`visible`, `excluded`, `replace_mode` ∈ {replaced,
inserted-from-legacy, appended}, `changed`). Aggregate summary on
stderr. Capture both for the run report.

**First-run behaviour.** When a hub has no AUTO-GENERATED markers yet,
the script replaces the existing `## Хронологическая карта` section
in-place (anchor-based replacement, `replace_mode:
inserted-from-legacy`). Subsequent runs use the markers directly.

**Failure mode.** Same as Step 4.5: surface `derived-hub-map-failed`
to log_maintenance.md with stderr captured; continue the rest of the
pipeline. Maps remain in their last good state.

**Editorial exclusions.** When a record matches a hub's project but
the curator wants it excluded from the map (low signal, repetitive,
narrative noise), add the record-id to hub frontmatter
`excluded_from_map:` and a 1-line rationale to
`excluded_from_map_reasons:` at the same index. The renderer surfaces
exclusions in a separate «Excluded from map (editorial)» table at the
bottom of the AUTO-GENERATED block — visible audit trail.

---

## Step 7.8: Content Map Render (content pipeline interface)

Regenerate `_system/views/CONTENT_MAP.md` — the compact interface the weekly
`content-synthesis` lens reads. **Maintain is the canonical writer:** it runs
after every process batch, so the map is guaranteed fresh *before* the weekly
lens reads it (the lens must never read a stale map). Runs after Step 7.7 so
hub structure is current first.

A pure projection over hubs + content-flagged note frontmatter + POSTS.md
`source_notes` — carries no state (the ledger
`_system/state/content-pipeline-state.json` holds state separately; the view
is regenerable, so it must not). One compact line per content note; ripeness
(`convergence × note_count × avg_potential`) is a sortable hint the lens
re-derives, never authoritative.

**Invocation.**

```bash
python3 _system/scripts/render_content_map.py
```

Deterministic, idempotent, pure — no LLM. Atomic write via `.tmp` + rename.
Re-running on unchanged source yields a byte-identical body (modulo the
`generated:` timestamp). Prints `wrote {path} ({N} themes)` to stderr.

**Failure mode.** Surface `content-map-render-failed` to log_maintenance.md
with stderr captured; continue the rest of the pipeline. The map remains in
its last good state (best-effort, like Step 7.7).

---

## Step 7.9: Cognitive-Model Hub Render

Regenerate the managed zone of `5_meta/mocs/hub-cognitive-model.md` — the visible,
accumulating projection of «how the owner thinks» across the cognitive /
communication axes (status `blank` / `evidenced` / `promoted` + source principle
links + anchor records). A **pure projection** over `0_constitution/` (active
principles tagged `cognitive_axes`) plus the principle-candidate buffer
(`dimension`-tagged agent-lens candidates). The hub holds no truth of its own — it
only links `[[principle-id]]` and reflects current state: archive a principle and
its axis drops off automatically on the next run. It reads the source principles
under `0_constitution/` directly (not the regenerated views) plus the candidate
buffer, so its only ordering dependency is Step 7.5 (the candidate buffer must be
current); it is placed after Step 7.8 to keep the post-loop renderers together.

**Invocation.**

```bash
python3 _system/scripts/render_cognitive_model_hub.py
```

Deterministic, idempotent, pure — no LLM. Writes ONLY between the hub's
`<!-- AUTO-GENERATED: cognitive-model-hub -->` markers; the owner's frontmatter and
prose «portrait» outside the markers are never touched. Re-running on unchanged
source performs **no write at all** (byte-identical tree — stricter than the SOUL
renderer). Prints a JSON line `{"ok", "changed", "status_counts", "blank_axes"}` to
stdout — plus `dropped_unknown_slugs: [{principle_id, slug}]` when a principle
carries a `cognitive_axes` slug not in the SoT (the renderer drops it so the hub
never carries a typo; the authoritative re-check is lint Scan F.8). Capture the
status counts, `changed`, and any dropped slugs for the Step 8 log entry.

**Failure mode.** A missing hub, missing markers, or unparseable axis SoT → the
script prints `{"ok": false, "changed": false, "reason": ...}` and exits 0
(best-effort, like Step 7.7/7.8). Surface `cognitive-model-hub-render-skipped` to
log_maintenance.md with the reason and continue; the hub stays in its last good
state.

---

## Step 7.10: Tag Registry Render

Regenerate the managed zone of `_system/registries/TAGS.md` — the census of the
`tags:` axis. One table per namespace (`category/value` → `category`) with a use
count per tag, plus the totals. A **pure projection** over `tags:` frontmatter
across the knowledge layer: every `*.md` except `_records/`, `_sources/`,
`_system/`, `0_constitution/` and `6_posts/`, minus `*.template.md` engine seeds
and symlinks. The registry holds no truth of its own — retire an identifier and
its row drops off on the next run.

Tags are counted as literal labels. Convention drift (`cat/sub` vs `cat-sub`) is
surfaced by the census, never silently merged. A tag repeated inside one note's
`tags:` list counts once — a use is a note, not a mention.

**Invocation.**

```bash
python3 _system/scripts/render_tags.py
```

Deterministic, idempotent, pure — no LLM. Writes ONLY between the registry's
`<!-- AUTO-GENERATED: tag-registry -->` markers; the preamble with its
three-axis table and the `## Notes` section are owner-owned and never touched.
Re-running on unchanged source performs **no write at all**. Prints a JSON line
`{"ok", "changed", "unique_tags", "total_uses", "namespaces", "notes_scanned"}`
to stdout — capture it for the Step 8 log entry.

**First-run behaviour.** On a registry that has no markers yet, the region from
the `**Total unique tags:**` line to the `## Notes` heading is the generated
region and is replaced by the marked zone. Subsequent runs use the markers.

**Failure mode.** A missing registry, or a registry with neither markers nor the
totals anchor → the script prints `{"ok": false, "changed": false, "reason": ...}`
and exits 0 (best-effort, like Step 7.7/7.8/7.9). Surface
`tag-registry-render-skipped` to log_maintenance.md with the reason and continue;
the registry stays in its last good state.

---

## Step 7.11: HUB_INDEX Render

Regenerate the managed zone of `_system/views/HUB_INDEX.md` — the registry of
every hub file on disk, grouped by `status:`. A **pure projection** over
`5_meta/mocs/hub-*.md` frontmatter (minus `*.template.md` engine seeds and
symlinks): `id`, `title` (leading `Hub: ` stripped), `hub_kind`, `modified`,
`related_notes`, `domains`, `people`. A field a hub does not carry renders as
`—`; the renderer never invents one and never carries a stale value forward.

This is the rebuild that `/minder:mem:lint` A.6.2 (`hub-index-incomplete`) sends the
owner to, and the counterpart of `/minder:mem:process` §4.3's additive append: create a
hub mid-run and its row appears immediately; everything else about the index is
reconciled here.

`active`, `dormant` and `resolved` sections render whether or not any hub is in
that state. Any other status found on disk gets its own section, so no hub can
fall out of the index.

**Invocation.**

```bash
python3 _system/scripts/render_hub_index.py
```

Deterministic, idempotent, pure — no LLM. Writes ONLY between the view's
`<!-- AUTO-GENERATED: hub-index -->` markers; the `## Cross-link state` section
below them is owner-curated rationale and is never touched. Re-running on
unchanged source performs **no write at all**. Prints a JSON line
`{"ok", "changed", "hub_count", "sections"}` to stdout — capture it for the
Step 8 log entry.

**First-run behaviour.** On a view that has no markers yet, everything between
the `# Hub Index` heading and the `## Cross-link state` heading (or EOF) is the
generated region and is replaced by the marked zone. Subsequent runs use the
markers.

**Failure mode.** A missing view, or a view with neither markers nor the
`# Hub Index` heading → the script prints
`{"ok": false, "changed": false, "reason": ...}` and exits 0 (best-effort, like
Step 7.7/7.8/7.9/7.10). Surface `hub-index-render-skipped` to log_maintenance.md
with the reason and continue; the view stays in its last good state.

---

## Step 8: Patch last-batch log_maintenance.md entry with regen + pattern-detect confirmation

The per-batch entries were written in Step 6.5 with
`CURRENT_CONTEXT.md: pending` and `INDEX.md: pending`. After Step 7,
Step 7.5, Step 7.6, Step 7.7, Step 7.8, Step 7.9, Step 7.10, and Step 7.11
complete successfully:

1. Locate the log_maintenance.md entry for the **last batch** of this run
   (highest batch_id processed).
2. Replace `CURRENT_CONTEXT.md: pending (regenerated post-loop; see last-batch entry for confirmation)`
   with `CURRENT_CONTEXT.md: regenerated (generated: {timestamp}, covers batches {first_id}..{last_id})`.
3. Replace `INDEX.md: pending (regenerated post-loop; see last-batch entry for confirmation)`
   with `INDEX.md: regenerated (generated: {timestamp}, note_count: {N}, archive_count: {A}, constitution_count: {C}, hub_count: {M}, domain_count: {D})`.
4. Append a line immediately below noting the Step 7.5 pattern-detect
   result: `principle-candidates.jsonl: +{candidate_count} new candidates
   (session_id: {session_id})`. If Step 7.5 produced zero new candidates,
   write `+0 (no recurring rationale patterns)` to keep the trace explicit.
5. Append the Step 7.9 hub render result:
   `hub-cognitive-model.md: {changed|no-change} ({P} promoted, {E} evidenced,
   {B} blank)`. If `dropped_unknown_slugs` is non-empty, append
   `; dropped {N} unknown slug(s): {principle_id:slug, …}` so the typo is visible
   without waiting for the nightly lint. If Step 7.9 was skipped, write
   `hub-cognitive-model.md: skipped ({reason})`.
6. Append the Step 7.10 tag-registry render result:
   `TAGS.md: {changed|no-change} ({U} unique tags, {T} uses, {N} namespaces
   over {S} notes)`. If Step 7.10 was skipped, write
   `TAGS.md: skipped ({reason})`.
7. Append the Step 7.11 hub-index render result:
   `HUB_INDEX.md: {changed|no-change} ({N} hubs; {status}: {n}, …)`. If Step
   7.11 was skipped, write `HUB_INDEX.md: skipped ({reason})`.

Earlier batches in the run retain their `pending` notes — readable as
«covered by the last batch's regen», consistent with invariant that regen
runs once per run, not once per batch.

If Step 7 / 7.6 were skipped (e.g. `--dry-run`), leave `pending` in
place and also skip the pattern-detect confirmation — no patch needed.

---

## Step 9: Release Lock

Delete `_sources/.maintain.lock`. Must execute on every path — use finally
semantics.

---

## CLARIFICATIONS Format

Append new items under a single dated header at the END of `## Open Items`
section, BEFORE the HTML comment block:

```markdown
## maintain {YYYY-MM-DD} batch-{batch_id}

### {individual item 1}
...

### {individual item 2}
...
```

If a maintain run processes multiple batches, use multiple headers (one per
batch) for cleaner grouping.

### Item format (parsable fields + free-form body)

All items use the structured body from the step that raised them
(see Step 2.4, 4.2, 5, 6). Common fields:

- `**Type:**` — one of reason codes below
- `**Subject:**` — the primary entity id
- `**Source:**` — `batch-{id}` always (maintain never cites raw `_sources/*`)
- `**Suggested action:**` — parsable verb from the Resolution-action canonical vocabulary (close-thread / keep-thread-open / promote-tier / pursue-or-close / fix-process / dismiss / etc. — see `_system/docs/SYSTEM_CONFIG.md`)
- `**Confidence tier:**` — surfaced (maintain never auto-applies thread closure / tier promote; HARD RULE)
- `**To resolve:**` — imperative instruction for the owner
- `**Quote:**` — verbatim fragment when applicable (closure fuzzy match,
  transcript quotes for person-ambiguity items)
- `**Context:**` — **mandatory** — 2–4 sentence paragraph self-contained для LLM review session. Includes: what ambiguity is about, why uncertain, related entities inline (wikilinks/ids), relevant live-state context (OPEN_THREADS state, PEOPLE.md row, hub content if applicable), 1–2 candidate resolutions с brief rationale. Owner не открывает source files для resolve.

**Distinction Quote vs Context:**
- `Quote` = verbatim fragment из batch artifact or source (deterministic, grounded)
- `Context` = LLM-synthesized surrounding understanding (what item is *about*, not what was said verbatim)

### Reason codes

- `thread-detection-ambiguous` — new-thread candidate with LLM confidence < 90%
- `thread-closure-suggested` — ≥2/4 closure signals, manual apply needed
- `thread-hub-ambiguous` — 2+ hub candidates for linkage
- `thread-dangling-task-ref` — thread.Related Tasks references missing task
- `tier-promote-suggested` — mentions crossed threshold, manual apply needed
- `mention-count-drift` — PEOPLE.md count vs batch report mismatch
- `batch-malformed-frontmatter`, `batch-version-unknown`,
  `batch-missing-section`, `batch-counts-inconsistent`, `batch-counts-anomaly`,
  `batch-dangling-reference`, `batch-unknown-person` — batch anomalies

Parsable fields are stable across codes to enable automated reader (`/minder:mem:resolve-clarifications`).
Do not reorder or rename — append-only evolution.

---

## Output Report

Write to user (stdout) at end of run:

```
## Minder Memory Maintain Report — YYYY-MM-DD

### Batches Processed: N
{For each batch, one line:}
- {batch_id}: +{threads_opened} threads, +{backrefs} back-refs, +{hubs_linked} hubs, {suggestions_raised} CLARIFICATIONS

### Aggregated Summary
- Threads opened: N
- Back-references written: N (across M records/notes)
- Hubs linked: N (across K unique hubs)
- Closure suggestions raised: N
- Tier promote suggestions raised: N
- Mention drifts flagged: N
- Batch anomalies flagged: N

### CLARIFICATIONS Raised: N
{list with Type + Subject + Suggested action for each, grouped by reason code}

### State Updates
- OPEN_THREADS.md: {Active N→M}
- CURRENT_CONTEXT.md: regenerated (batch_id: {last})
- INDEX.md: regenerated (note_count: {N}, archive_count: {A}, constitution_count: {C}, hub_count: {M}, domain_count: {D})
- log_maintenance.md: +{N} entries

### Completion Gate
- [x] All unprocessed batches iterated (N processed)
- [x] Lock released
- [x] CURRENT_CONTEXT regenerated
- [x] INDEX regenerated
- [x] log_maintenance.md entries written (one per batch)
- [x] No silent closures — maintain never moves threads to Resolved, suggest-only
- [x] No silent tier changes — maintain never edits PEOPLE.md Tier column
- [x] Back-refs only modified frontmatter of records/notes (body untouched)
- [x] No writes to TASKS.md / CALENDAR.md / _records/ body / PARA body / PEOPLE.md counts or tier

### Next Actions for Owner
{if any CLARIFICATIONS were raised:}
Run `/minder:mem:resolve-clarifications` to review the queue interactively. Specifically pending:
- {N} thread closures suggested — skill renders signals + hypothesis, applies move to OPEN_THREADS.md `## Resolved` on confirm
- {N} tier promotes suggested — skill proposes PEOPLE.md Tier edit with diff
- {N} batch anomalies — surfaced for review; root cause may need `/minder:mem:process` re-run
```

---

## Example Usage

```
/minder:mem:maintain
/minder:mem:maintain --dry-run
/minder:mem:maintain --batch 20260417-211522
/minder:mem:maintain --verbose
```

---

## Invariants

These are structural invariants maintain guarantees:

1. **Zero writes** to: `_records/meetings/*` + `_records/observations/*` body, PARA notes body, `_system/TASKS.md`,
   `_system/CALENDAR.md`, `_system/state/BATCH_LOG.md`, `_system/state/batches/*`,
   `_system/state/PROCESSED.md`, `_system/SOUL.md`, `3_resources/people/PEOPLE.md`
   (mention counts AND tier column).
2. **Only frontmatter writes** allowed on records/notes — specifically the
   `threads:` back-reference field. No body modifications, no other frontmatter
   fields touched.
3. **Idempotent retry** — running `/minder:mem:maintain` twice on the same unprocessed
   set must yield identical state on second run. Guaranteed by:
   - Per-batch log_maintenance.md write in Step 6.5 (inside loop) — a crash
     mid-loop leaves already-processed batches marked, retry skips them.
   - Back-ref writes are append-if-missing (check before append).
   - Header counter updates are parsed + incremented from live state, not
     cumulative across runs.
4. **No silent apply** — thread closures and tier promotions never executed
   by maintain. Only CLARIFICATIONS raised.
5. **Lock always released** — finally semantics mandatory.
6. **CURRENT_CONTEXT + INDEX regenerated when batches were processed** —
   if at least one batch reached Step 6.5, Step 7 (CURRENT_CONTEXT) and
   Step 7.6 (INDEX) each run once post-loop. Exceptions: `--dry-run` (no
   regen), empty unprocessed set (never reaches post-loop — Early Exit
   handles it). INDEX regen failure does NOT abort the run — surface in
   report, continue to Step 8 with `INDEX.md: regen-failed ({error})` in
   the log patch.
7. **Best-effort on malformed batch** — hard fail is forbidden. Every anomaly
   must have a workaround + CLARIFICATION.
8. **Empty batch safe** — a batch with 0 records, 0 notes, 0 tasks still
   passes through cleanly: 0 threads opened, 0 back-refs, 0 hubs linked,
   log_maintenance.md entry written with zeroed counters. CURRENT_CONTEXT
   and INDEX regen still run post-loop (fresh timestamp even if state
   didn't change).
9. **Threads without the optional fields handled gracefully** — a thread
   carrying no `Related Tasks` or `hub:` field (bootstrap writes them that way)
   does not cause errors. Its missing closure signals are excluded from scoring
   (Step 5).

---

## Contract dependencies

Maintain consumes artifacts produced by `/minder:mem:process`:
- `_system/docs/batch-format.md` frontmatter schema
- Inline Mentions increment in PEOPLE.md (1-per-file rule)
- Structured batch sections per `_system/docs/batch-format.md`

If a batch is malformed or written by an unknown processor version — treat
per Step 1 malformed-handling table, raise `batch-version-unknown` or
`batch-malformed-frontmatter` CLARIFICATION, continue best-effort.
