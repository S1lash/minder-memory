---
name: minder:mem:agent-lens
description: >
  Outside-view observation runner for the Minder Memory base. Reads
  _system/registries/AGENT_LENSES.md, runs the lenses lens_due.py names
  as due — on their cadence, or retried after a failed thinker — and runs each through a two-stage pipeline (free-form thinker in
  a clean call of its own + runner-side structurer + structural
  validator), writes outputs to
  _system/agent-lens/{id}/{date}.md and machine index to
  _system/state/agent-lens-runs.jsonl. Each lens is independent — no
  cross-lens synthesis at runner level. Meta-lens (input_type=lens-outputs)
  produces digest of pointers across other lenses' outputs. Cross-skill
  lock awareness symmetric. Best-effort, idempotent, rollback via git.
disable-model-invocation: false
---

# /minder:mem:agent-lens — Agent-Lens Observation Runner

Autonomous observer of the Minder Memory base. Each registered lens is a narrow
intent (stalled threads, stated-vs-lived gap, recurring reaction, etc.)
that runs on its own cadence and produces structured observations the
owner reviews on their own schedule.

**Philosophy:**
- Thinker-free, structurer-strict — the thinker (the latest Opus, in a
  clean call of its own) writes free-form analysis; the runner reformats
  it to the canonical schema without adding to it. Decoupling so
  thinking is not biased by formatting pressure.
- Hypothesis-grade, not fact — outputs are the agent's hypotheses about
  patterns. Owner judges on review. Skill never auto-promotes a lens
  observation to constitution / knowledge / hub / clarification.
- Per-lens isolation — lenses are independent. No cross-lens synthesis
  at runner level. A meta-lens with `input_type: lens-outputs` may
  produce pointers (counts/dates/ids/short-titles), never content
  citations from other lenses.
- Best-effort over hard-fail — single lens error never aborts the run;
  errors surface to log + CLARIFICATIONS as designed. Run continues
  with remaining lenses.
- Cadence-honest — scheduler fires daily; per-lens cadence is enforced
  by `lens_due.py`, not judged by the runner. Daily tick ≠ daily lens
  runs; a lens whose thinker failed on its day is retried on the next
  nights rather than a week later.
- Isolation by construction — every thinker runs in a clean model call
  of its own (`_system/scripts/lens_think.py`) with an empty history: no
  cross-lens carry-over, no inheritance of the runner's context. Never
  a subagent, never the runner itself. See Step 4.5 for the load-bearing
  contract.
- Surface-everything to CLARIFICATIONS — any unexpected condition
  (registry error, malformed lens, LLM exhaustion after retries,
  IO failure, missing context, unhandled exception) becomes a row
  in `_system/state/CLARIFICATIONS.md` plus a log entry. Never silent
  failure, never owner pause, never auto-recovery beyond the explicit
  retry policy in §4.5.4. Doctrine §3.1 — surface, don't decide
  silently.

**Language convention (load-bearing):**

Establish and lock the user-facing language at the very first turn:

- **User-facing output** — exit status messages, CLARIFICATIONS rows,
  summaries surfaced to the owner, error messages — MUST be in the
  owner's language. Detect from: (1) most recent records in
  `_records/` (last 7 days, language of body text), (2) `SOUL.md`
  body text, (3) fall back to English if neither is decisive. The
  detection happens during Step 1 context load.
- **Generated lens content** — observations written by the thinker,
  formatted by the runner — MUST be in the owner's language established
  above. The runner passes it to every thinker (`lens_think.py
  --language`), because the thinker sees nothing of this run and the
  frame itself is in English.
- **Internal artefacts** — `_system/state/log_agent_lens.md` block
  headers, `_system/state/agent-lens-runs.jsonl` field values,
  exit-status tokens, error codes, file paths — English only
  (debugging + machine-readability). Never localised.

This mirrors `/minder:mem:process` convention («язык контента = язык
оригинала») and aligns with `/minder:mem:agent-lens-add` (which detects from
conversation tone). All Minder Memory skills follow the same shape: user-facing
in user's language, machine state in English.

**Working directory:** the zettelkasten base. Every path and every `python3`
command in this file is written relative to it; `scripts/` (the shared shell
libraries) sits one level above, at the repo root.

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md` — файл описывает current behavior без
version/phase/rename-history narratives.

**Contracts:**
- `_system/docs/ENGINE_DOCTRINE.md` — operating philosophy (load first):
  §3.1 surface-don't-decide, §3.3 idempotency, §3.4 lock matrix,
  §3.5 logs, §3.6 owner-LLM contract (this skill never auto-promotes)
- `_system/docs/SYSTEM_CONFIG.md` — log file ownership, cross-skill
  exclusion matrix, CLARIFICATIONS format
- `_system/registries/AGENT_LENSES.md` — lens registry schema, cadence
  semantics, lens lifecycle, registry validation rules
- `_system/registries/lenses/_frame.md` — two-stage frame (thinker +
  structurer), validator rules, self-history stances

> **Schema expectations.** Skill polagaется на наличие системных
> файлов: `AGENT_LENSES.md` registry, `lenses/_frame.md` frame,
> `lenses/{id}/prompt.md` per lens, `_system/state/log_agent_lens.md`,
> `_system/state/agent-lens-runs.jsonl`. Если во время flow обнаруживается
> несостыковка (missing file, malformed registry, lens with broken
> frontmatter) — **не останавливать run целиком**: зафиксировать
> вопрос в `_system/state/CLARIFICATIONS.md` под `## Open Items` с
> type `agent-lens-compatibility`, skip affected lens, continue with
> остальными. Owner разбирает на ревью.

## Arguments

`$ARGUMENTS` supports:
- `--all-due` (default if no other mode flag) — run every active lens
  whose cadence indicates it is due today. Used by the scheduled tick.
- `--lens <id>` — run a single named lens regardless of due-status.
  Owner-driven testing.
- `--include-draft` — only meaningful with `--lens`; allows running a
  lens with `status: draft`. Without this flag, draft lenses are
  skipped even when explicitly named.
- `--dry-run` — execute the full pipeline including the thinker calls,
  but write nothing under `_system/` except the log entry: no output in
  `_system/agent-lens/`, no runs.jsonl line, no raw or rejected copy, no
  lens status change. Print the thinker's text and the formatted
  artefact (or the validator's verdict) for inspection. Used during lens
  prompt iteration.
- `--force` — bypass the «another agent-lens run completed <30min ago»
  guard. Useful when the owner is iterating manually.
- `--no-sync-check` — skip the data-freshness pre-flight (see below).

Modes are mutually exclusive in spirit: `--lens X` overrides `--all-due`.
The scheduled tick uses `--all-due` only.

---

## Pre-flight: data freshness (non-blocking)

Multi-device safeguard. If `origin` has commits not yet pulled, the
agent-lens may produce observations on a stale view of the records,
duplicating work another device's tick already completed.

Skip with `--no-sync-check` (the scheduled tick passes this implicitly
because Step 1 of the scheduler-prompt runs `/minder:mem:sync-data` first).

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

- `origin` not configured, or fetch failed (offline) → silently proceed.
- `remote_ahead == 0` → silently proceed.
- `remote_ahead > 0` → render owner-facing prompt:
  ```
  ⓘ origin/<branch> ahead by <N> commit(s). Lens observations on a
    stale base may duplicate work already done elsewhere.

    [s] run /minder:mem:sync-data first  (recommended — abort current run)
    [c] continue with current local state
    [d] show pending commits         (then re-prompt)
  ```
  - `s`: print «owner: run `/minder:mem:sync-data`, then re-run
    `/minder:mem:agent-lens`», exit 0.
  - `c`: proceed.
  - `d`: `git log HEAD..origin/$branch --oneline`, then re-prompt s/c.

Courtesy nudge, not a gate. `c` is always safe.

---

## Error handling principle (applies to every step)

Single rule: **any unexpected condition → CLARIFICATIONS + log +
proceed-or-exit per severity**. Never silent failure, never owner pause.

Severity → action map:

| Class | Examples | Action |
|---|---|---|
| **Catastrophic** (cannot proceed at all) | missing `_frame.md`, missing `AGENT_LENSES.md`, registry table unparseable, lock acquisition failed mid-tick, unhandled exception | Append CLARIFICATION «agent-lens: {cause}» under `## Open Items`, write log entry, release lock (finally), exit with non-success status. **Do NOT** continue to other lenses. |
| **Lens-level** (one lens broken, others fine) | lens folder missing, frontmatter incomplete, `id` collision, `cadence_anchor`/`cadence` mismatch, `self_history` invalid, lens prompt unreadable | Append CLARIFICATION «agent-lens: lens {id} {cause}», log entry, **skip this lens, continue** with remaining due lenses. |
| **Run-level recoverable** (transient) | LLM timeout, rate-limit, 5xx, partial network failure | Retry per §4.5.4 (2 retries, each a clean call). After exhaustion → log `status: error` only (no CLARIFICATION — transient, not actionable by owner). Continue to next lens. |
| **Quality issue** (output produced but invalid) | structurer output fails validator, cited paths don't resolve, schema mismatch | Save raw to `_system/state/agent-lens-rejected/`, log `status: rejected`, continue. CLARIFICATION raised ONLY on auto-pause trigger (3 consecutive rejections per §5.5). |
| **Owner-action-required** (system needs attention) | auto-pause after 3 rejections, registry collision, `cadence_anchor` impossible | Append CLARIFICATION explicitly naming what owner should do, log entry, continue. |

Defaults if condition is novel and not classified above: treat as
**Catastrophic** (CLARIFICATION + exit) — better to surface a stop than
to silently swallow an unknown.

CLARIFICATIONS rows ALWAYS include:
- Timestamp (run_at)
- Lens id (if scoped to one lens)
- Cause (the specific error message / detected condition)
- Where to look (`log_agent_lens.md` block ref, rejected-output path,
  registry row, etc.)
- Suggested owner action (one line)

Never write a CLARIFICATION without all five fields. Doctrine §3.1.

---

## Step 0 — Early Exit Check + Cross-Skill Lock Awareness

**FIRST action.** No context load, no work until passed.

### 0.1 Early exit check

If `--all-due`: note the UTC date now — the tick's date — and run
`lens_due.py due` with it (Step 3). If it prints nothing → report
«no lenses due today» and **exit immediately**. No lock, no further
context loading.

If `--lens <id>`: skip this check (owner explicitly named a target).

This saves a full registry parse + lock churn on no-op days (most days,
since most lenses have weekly+ cadence).

### 0.2 Cross-skill lock check (HARD contract — symmetric mutual exclusion)

Read every pipeline lock under `_sources/` and abort on any that exists,
with `"{holder} running, try again later"` — or, for this skill's own
`.agent-lens.lock`, `"another /minder:mem:agent-lens run in progress"`. The lock
set is owned whole by `_system/docs/SYSTEM_CONFIG.md` → «Cross-skill
exclusion»; read it there rather than keeping a second copy that drifts.

Stale lock (>2h old, parse ISO timestamp from file content) → warn,
report PID if present, **offer manual removal, do NOT auto-delete.**
Auto-clean is the scheduler-prompt's responsibility, not the skill's
— skills are conservative because human may still be inspecting the
crashed-run side effects.

### 0.3 Recent-run check

Read last entry of `_system/state/agent-lens-runs.jsonl`. If most
recent entry across ALL lenses has `run_at` < 30 minutes ago, report:
```
agent-lens ran {N} minutes ago (last entry: {timestamp}). Pass --force
to proceed anyway.
```
Exit unless `--force`.

Rationale: 30 min is shorter than lint's 6h because agent-lens has no
cumulative LLM-cache state to protect; the guard exists only to prevent
accidental double-runs from the owner re-firing while a tick is queueing.

The scheduled tick passes `--force` implicitly via cron timing alignment
(once a night — never <30min from prior tick by construction).

---

## Step 0.5 — Concurrency Lock

Create `_sources/.agent-lens.lock` with content:
```
{ISO UTC timestamp} — agent-lens run, PID {pid}, mode: {all-due|lens X|dry-run}, args: {$ARGUMENTS}
```

**Finally semantics mandatory:** lock release in every exit path
(normal completion, skip, exception, malformed abort). Wrap Steps 1-9
in try/finally; delete lock in finally. If crashed mid-run, next
invocation detects stale lock → warn owner, manual removal recommended.

`--dry-run` still acquires the lock (we're using LLMs, holding the
exclusive resource), and releases it identically.

---

## Step 1 — Context Load

Read in this order:
1. `_system/docs/ENGINE_DOCTRINE.md` (operating philosophy + lock matrix)
2. `_system/docs/SYSTEM_CONFIG.md` (log ownership, exclusion matrix)
3. `_system/registries/AGENT_LENSES.md` (registry table + concept doc)
4. `_system/registries/lenses/_frame.md` (Stage 1/2/3 frame bodies)

If any of these is missing → write CLARIFICATION «agent-lens: required
context file missing: {path}», release lock (finally), exit.

---

## Step 2 — Registry Validation

Parse `AGENT_LENSES.md`. Extract Active and Draft lens tables.

For each lens row in scope (Active for `--all-due`; Active+Draft for
`--lens X --include-draft`; Active for `--lens X` without
`--include-draft`):

1. Resolve folder `_system/registries/lenses/{id}/`. Missing → record
   `registry-error: folder missing for {id}`, append CLARIFICATION,
   skip lens.
2. Resolve `prompt.md` inside that folder. Missing → record
   `registry-error: prompt.md missing for {id}`, skip.
3. Concatenate all `*.md` files in the folder (prompt.md first,
   remainder alphabetically). Parse frontmatter from `prompt.md`.
4. Required fields: `id`, `name`, `type`, `input_type`, `cadence`,
   `cadence_anchor`, `self_history`, `status`. Missing any → skip
   with registry-error. `output_schema` is OPTIONAL and defaults to
   `standard` when absent.
5. Validate field values:
   - `type` ∈ {mechanical, psyche, meta}
   - `input_type` ∈ {records, lens-outputs, multi-source}
   - `output_schema` ∈ {standard, synthesis-custom} (default: standard)
   - `cadence` ∈ {daily, weekly, biweekly, monthly}
   - `cadence_anchor` consistent with `cadence` (weekly/biweekly →
     day-of-week; monthly → day-of-month 1-28; daily → "daily" or
     ignored)
   - `self_history` ∈ {fresh-eyes, longitudinal, lens-decides}
     (no default — missing/invalid value fails validation)
   - `status` ∈ {draft, active, paused}
   - `id` matches folder name
6. Check id uniqueness across all lenses. Collisions → skip both,
   raise CLARIFICATION «agent-lens: id collision {id}».

Lens-level errors → log and skip individual lens, continue. Registry-
level table parse failure (whole `AGENT_LENSES.md` malformed) → write
CLARIFICATION, release lock, exit.

---

## Step 3 — Filter Due Lenses

Apply mode flags:

- `--all-due`: keep exactly the lenses the due script names — never
  work the due set out by hand:

  ```
  python3 _system/scripts/lens_due.py due --base . --today {tick's UTC date from Step 0.1}
  ```

  One line per due lens, `{lens-id} scheduled` or `{lens-id} retry`
  (a lens whose thinker ended `status: error` on its day — its in-run
  retries of §4.5.4 exhausted — tried again on the next two nights);
  nothing printed means nothing is due. Step 0.1 and this step use the
  same date and the same set; Step 3 does not recompute it.
- `--lens <id>`: keep only the matching lens. Status check:
  - `active` → run
  - `draft` → require `--include-draft`, else abort with message
  - `paused` → abort with message «lens {id} is paused; un-pause in
    registry to run»

The rule the script applies — once a day at most, the cadence, and the
retry of a lens whose thinker failed — is canonical in `AGENT_LENSES.md`
Cadence semantics section; the script is its only implementation.

---

## Step 4 — Order Lenses

Sort the due list:
1. `input_type == records` first (in registry order)
2. `input_type == lens-outputs` middle (in registry order)
3. `input_type == multi-source` last (in registry order)

Rationale: meta-lenses (`lens-outputs`) read other lenses' outputs
from the current run, so non-meta must complete first within the
same tick. Synthesis lenses (`multi-source`) read both primary
data AND lens outputs (including meta-lens outputs like
global-navigator), so they run last.

---

## Step 4.5 — Isolation contract (load-bearing)

A lens is an outside view, and the outside is the point: the thinker
sees its frame, its own prompt and the owner's data — nothing of the
tick that runs it, the project's rules, or the other lenses of the same
run. The runner enforces that at four levels; violating any one breaks
the design.

### 4.5.1 The thinker is a clean call, never the runner

Every Stage 1 runs through `_system/scripts/lens_think.py`, which makes
one headless Claude Code call per lens (`claude -p`, the owner's own
login and subscription):

- **System prompt** = exactly the `_frame.md` Stage 1 body for the
  lens's `input_type`, extracted by the script. Nothing prepended or
  appended by the runner.
- **User message** = the lens folder (`prompt.md` first, other `*.md`
  alphabetically), the self-history hint for its stance, and one line
  of run context (lens id, today's date, the base as working
  directory) — assembled by the script, not by the runner.
- **Tools** = read-only over the base: Read, Glob, Grep. No settings,
  no MCP servers, no hooks, no session history.
- **Model** = the alias `opus`, so the latest Opus is used without a
  version pinned anywhere. No other model is ever substituted: the
  script checks that the model which wrote the answer (`thinker_model`)
  is an Opus and otherwise fails the attempt with `wrong-model`. A
  lighter model listed beside it in `models` is the CLI's own
  housekeeping, not the thinker.

Forbidden, because each one puts the runner's context or a foreign
system prompt around the frame:
- writing the thinker's text in the runner's own turn;
- the Agent / Task tool, a «general-purpose» or any other subagent;
- passing anything from another lens, or from this run's loop, into a
  thinker's message.

The platform still adds its own reminders and an environment note to
every call; they carry nothing of the tick and are accepted. No
CLAUDE.md, rule or memory file reaches the thinker.

### 4.5.2 The runner formats, and only formats

For `output_schema: standard` the runner itself is the structurer
(Step 5.3): it lays the thinker's text out in the canonical schema
using the `_frame.md` Stage 2 body as its instructions. It extracts,
never authors — no claim added, removed, sharpened or softened, and
nothing from another lens or from the runner's own knowledge of the
base. The thinker's raw text is kept beside the result, so the two can
always be compared.

### 4.5.3 One call per lens, in parallel within a cohort

`lens_think.py` takes every lens of one cohort (Step 4 order: records →
lens-outputs → multi-source) and runs their thinkers concurrently, at
most three at a time. A cohort can take longer than a single command
may run, so the work is never run inside one command: `start` launches
it as a process of its own and returns at once, and `wait` blocks for
at most nine minutes and returns; the runner calls `wait` again until
the cohort is done. The runner stays in its turn throughout — it never
uses the Agent tool, never backgrounds a command and never ends its
turn to wait. A cohort completes before the next one starts, so a
meta-lens always reads this run's finished outputs.

### 4.5.4 Retry is a clean slate

A failed call (timeout, rate limit, API error, refusal, unparseable
output) is retried by the script up to twice, after a pause, each time
a new clean call with the original message — never with the failed
attempt as context. A timeout is retried once: it is already the
expensive case. After three failures the lens is `status: error` with
`rejection_reason: stage1-{cause}-retries-exhausted`; the run goes on
with the other lenses.

---

## Step 5 — Per-Lens Execution

For each cohort (Step 4 order), run Step 5.2 once for all its due
lenses, then Steps 5.3-5.5 for each of them in registry order. Errors in
one lens do NOT abort the loop.

### 5.1 What the thinker receives

`lens_think.py` assembles this; the runner never does. The list below is
what the script builds, so a reader knows what a thinker sees:
1. Stage 1 frame body for `input_type` (extracted from `_frame.md`):
   - `records` → base-input variant (lens prompt scopes which layer is primary)
   - `lens-outputs` → lens-outputs-input variant
   - `multi-source` → multi-source-input variant (synthesis lenses; lens
     prompt carries its own output schema, written directly without
     Stage 2 reformat)
2. Lens folder content (prompt.md first, other `*.md` alphabetically)
3. Self-history hint (depends on `self_history` value):
   - `fresh-eyes` → frame mentions: «do not read your own past outputs»
   - `longitudinal` → frame mentions:
     «past outputs available at `_system/agent-lens/{lens-id}/`; use
     as context, not as evidence — see lens prompt for guidance.
     Skip outputs that are superseded by a later run on the same
     date — `runs.jsonl` entries with a `supersedes` field point to
     the prior `run_at` they replace; the per-day file on disk
     reflects the latest run only»
   - `lens-decides` → frame mentions same path; lens prompt itself
     decides whether to read

**Supersedes filter (longitudinal lookup).** When the runner reads
`agent-lens-runs.jsonl` for past `last_run` of this lens, exclude any
entry whose `run_at` is referenced by a later entry's `supersedes`
field. Same-day re-runs (e.g. owner iterating during prompt
calibration) leave a chain in `runs.jsonl` but only the last file on
disk; the longitudinal view should mirror what is actually persisted.
The thinker is told the same in the self-history hint above so it
does not double-count an iteration as two independent past surfaces.

### 5.2 Stage 1 — Thinker calls (one cohort at a time)

**Isolation contract: see Step 4.5.** For each cohort of due lenses, from
`zettelkasten/`:

```bash
python3 _system/scripts/lens_think.py start --base . --language "{owner language}" \
  {lens-id} {lens-id} ...
```

It prints `OUT <dir>` — a fresh temporary directory — and returns at
once. Then, as its own command each time:

```bash
python3 _system/scripts/lens_think.py wait --out "<dir>"
```

Exit 0: every thinker of the cohort has answered or failed. Exit 3: still
running — run the same `wait` again. Exit 4: the work died before
finishing — every lens not yet `ok` in `results.json` is an error
(`rejection_reason: stage1-runner-died`). Never run `wait` in the
background, and never end the turn between two `wait` calls.

`<dir>` then holds `{lens-id}.thinker.md` (the thinker's text, verbatim)
and `results.json` (per lens: `status`, `cause` and `error` on failure,
`attempts`, the model that answered, token usage, seconds). A lens with
`status: error` is logged with `rejection_reason:
stage1-{cause}-retries-exhausted` and goes no further. Do NOT trim,
summarise, or rewrite a thinker's text.

Keep the thinker's text: copy it to
`_system/state/agent-lens-raw/{lens-id}/{run_at-fs}.md` before Step
5.3, whatever happens after (`{run_at-fs}` is `run_at` with `:` turned
into `-`, legal in a file name on every platform) — except in `--dry-run`, which writes
nothing under `_system/` but its log entry and prints the thinker's
text instead.

### 5.3 Stage 2 — The runner formats

**Branch on `output_schema`:**

- `output_schema: synthesis-custom` — no reformatting. The thinker
  wrote directly to the schema in its lens prompt; the artefact is its
  text, verbatim, under a frontmatter the runner writes: `title: 🔭
  {lens-id} — {YYYY-MM-DD}`, `lens_id`, `run_at`, `hits` (the number of
  findings, as the lens prompt counts them — its `## ` sections when it
  names no count) and the privacy trio of Step 5.9. The body is not
  touched. Proceed to Step 5.4.
- `output_schema: standard` (default) — the runner lays the thinker's
  text out in the canonical schema, following the `_frame.md` Stage 2
  body as its instructions, with `lens_id` and `run_at`. It extracts,
  never authors (Step 4.5.2): where the thinker gave no evidence, no
  alternative reading or no confidence, the field says so
  (`unspecified`, `(no specific paths cited)`) rather than being filled
  in. A confidence the thinker gave as a range takes its lower end.
  Material the schema has no field for (a list of readings the thinker
  considered and set aside) is left out of the artefact, not squeezed
  into a field; it survives in `agent-lens-raw/`. Read only this lens's
  thinker text while formatting it.

If the runner cannot lay a thinker's text out in the schema without
adding to it, it does not repair the text: the lens's thinker runs once
more (a new clean call, Step 5.2 for that lens alone), and if that text
cannot be laid out either, the lens is `status: rejected` with
`rejection_reason: stage2-unformattable` and its raw text stays in
`agent-lens-raw/`.

### 5.4 Validator (structural, deterministic)

**Frontmatter fence integrity (universal, runs first for every `output_schema`).**
A Stage 2 output is a model-composed file (frontmatter + `## Observation N` body) —
structurally identical to a knowledge note, so it carries the same risk of a `## `
body heading being captured inside the YAML fence (breaks `yaml.safe_load`). Before
the schema branches, run `python3 _system/scripts/check_frontmatter_fence.py --repair <path>`
(from `zettelkasten/`) — it applies both fence helpers and the deterministic repair,
so they are never re-composed inline. Any status other than `ok` / `repaired` is a
validator **Fail** (save to rejected, do not write to `_system/agent-lens/`) — never
ship an unparseable observation file. Deterministic, no LLM.

The fence check above is the only part backed by a helper. The schema
branches below ship no validator script — the runner performs them itself
against `_frame.md` §«Stage 3 — Validator (structural, deterministic)», so
«deterministic» describes the rules, not an enforcing process. Nothing
downstream re-checks a shipped observation file; a branch skipped here is a
branch that never ran.

Then apply the branch matching the lens's `output_schema`:

- `output_schema: standard` → full canonical-schema validation
  (frontmatter privacy trio, `## Observation N` structure with
  Pattern / Evidence / Alternative reading / Confidence, cited path
  resolution).
- `output_schema: synthesis-custom` → relaxed validation (frontmatter
  privacy trio + `lens_id` + `run_at`, non-empty body, cited Minder Memory
  paths resolve to existing files). The lens prompt owns its internal
  section structure; runner does not enforce it.

**Pass:**
- Write output to `_system/agent-lens/{lens-id}/{YYYY-MM-DD}.md`.
  If file already exists for today (re-run scenario), overwrite.
- Append to `agent-lens-runs.jsonl` with `status: ok` (hits>0) or
  `status: empty` (hits==0).

**Fail:**
- Save Stage 2 raw output to
  `_system/state/agent-lens-rejected/{lens-id}/{run_at-fs}.md`.
- Append run record with `status: rejected`,
  `rejection_reason: {validator-failure-summary}`.
- Do NOT write to `_system/agent-lens/`.

### 5.5 Consecutive-rejection auto-pause

After updating runs.jsonl, look at the last 3 entries for this
`lens_id`. If all 3 have `status: rejected`:
- Update lens frontmatter `status: paused` in
  `_system/registries/lenses/{lens-id}/prompt.md`
- **Move** the row in `AGENT_LENSES.md` from `## Active Lenses` to
  `## Paused/Archived Lenses` (split-table per Archive Contract Form B
  in `_system/docs/SYSTEM_CONFIG.md`), populating the row with:
  - `Status: paused`
  - `Paused: {today}`
  - `Reason: "auto-pause: 3 consecutive validator rejections"`
  Atomic write — never leave the row in Active with `Status: paused`.
- Append CLARIFICATION «agent-lens: {id} auto-paused after 3
  consecutive validator rejections — see
  `_system/state/agent-lens-rejected/{id}/` for raw outputs»

---

## Step 5.9 — Privacy trio + concept fields on lens-observation entities

Lens outputs are written as markdown observation files; per
ENGINE_DOCTRINE §3.8 they are Tier 2 entities and **must carry
the privacy trio** (`origin`, `audience_tags`, `is_sensitive`) on
every emission. Apply these defaults at write time:

- `origin: personal` — lens observations are owner-internal
  hypothesis-grade analysis; never `work` (would leak to work-team
  in a future sync) or `external` (lens is internal).
- `audience_tags: []` — lens output is owner-only by construction.
  Never widened automatically; owner curates if they want to share
  a specific lens result.
- `is_sensitive: false` by default; `true` if the lens prompt
  explicitly asks the model to surface sensitive patterns
  (e.g. relationship/conflict observations) — consult the lens's
  `output_sensitivity` registry field if present, default `false`
  otherwise.

If a lens output references concepts by name, every concept-name
string MUST be normalised through
`_system/scripts/_common.py::normalize_concept_name()` at write
time (same autonomous-resolution contract as `/minder:mem:process`
Q15) — drop unnormalisables, never transliterate, never raise
CLARIFICATION. Lens outputs that wind up in the manifest pipeline
inherit conformance via this gate, so downstream Minder consumers
see the same clean concept/audience surface as for records and
notes.

---

## Step 5.95 — Emit batch manifest (universal contract)

Per ENGINE_DOCTRINE §3.8 and the canonical schema at
`_system/docs/manifest-schema/v{N}.json`, every Minder Memory engine
skill that produces persistent state changes emits a JSON manifest at
`_system/state/batches/{batch_id}-{skill}.json`. The
`agent-lens-runs.jsonl` log stays as audit trail, but downstream
consumers receive lens-observation upserts via the same universal
manifest path as the other three skills — uniform parsing, uniform
idempotency.

**When to emit:** at the END of the tick (after Step 5 across all due
lenses, before Step 6 Log Summary). One manifest per tick — covers
ALL lenses run in this tick, not one per lens. This matches the
"batch" semantic of the contract (a lens-tick is a batch of lens
observations).

**When to SKIP emission:** dry-run mode, or zero lenses with
`status: ok` in the tick (every lens was empty / rejected /
auto-paused). The manifest is opt-in evidence of state change; an
empty tick has nothing to write.

**Where to emit:**
- `batch_id` = UTC timestamp `YYYYMMDD-HHMMSS` of tick start (the
  same `run_at` used for the runs.jsonl entries).
- File path: `_system/state/batches/{batch_id}-agent-lens.json`.

**Schema:** `manifest-schema/v2.json`. Required top-level keys:
`batch_id`, `timestamp`, `format_version: "2.0"`,
`processor: "minder:mem:agent-lens"`, `stats`. Substantive payload lives in
`tier2_objects.lens_observation.upserts[]` — one entry per lens that
emitted an observation this tick (status `ok`, including hits>0; skip
`empty` and `rejected`).

**Per-observation entry:**

```json
{
  "id": "lens-obs-{lens-id}-{YYYYMMDD}",
  "lens_name": "{lens-id}",
  "observed_on": "{YYYY-MM-DD}",
  "observation_period": "{free-form: e.g. 'last 4 weeks'}",
  "body_markdown": "{full content of {date}.md, minus frontmatter}",
  "is_hypothesis": true,
  "generated_by_lens_run": "{runs.jsonl entry id or run_at iso}",
  "related_concepts": ["{snake_case names referenced in observation}"],
  "related_entity_refs": {"decisions_referenced": [...], "threads_referenced": [...]},
  "prompt_version": "{lens-id}@{version from registry frontmatter, default 'unversioned'}",
  "path": "_system/agent-lens/{lens-id}/{date}.md",
  "checksum_sha256": "{sha256 of the .md file bytes}",
  "origin": "personal",
  "audience_tags": [],
  "is_sensitive": "{from Step 5.9: false default; true if lens registry output_sensitivity=true}"
}
```

**`stats` shape:**

```json
{
  "lenses_considered": N,
  "lenses_run": N,
  "lenses_skipped_not_due": N,
  "lenses_skipped_registry_error": N,
  "lenses_failed": N,
  "observations_emitted": N,
  "candidates_appended": N,
  "clarifications_raised": N,
  "duration_seconds": N
}
```

**Emission via the helper:**

```bash
python3 _system/scripts/emit_batch_manifest.py \
    --input <path-to-temp-json> \
    --output _system/state/batches/{batch_id}-agent-lens.json
```

The helper applies the same producer-side normalisations as for
`/minder:mem:process`: concept-name conformance, audience-tag whitelist
filtering, privacy-trio coercion, empty-section shape coercion. Exit
codes per `emit_batch_manifest.py` docstring; treat exit 3 the same
way `/minder:mem:process` does — surface as a `process-compatibility`
CLARIFICATION ONLY if root cause cannot be auto-corrected in the
accumulator assembly.

**Then verify what actually landed — in this tick, not tonight.**

```bash
python3 _system/scripts/lint_manifest_schema.py \
    --batches-dir _system/state/batches --schemas-dir _system/docs/manifest-schema --all \
  | grep '"batch": "{batch_id}-agent-lens.json"'
```

A `"kind": "violation"` line here means the file on disk does not honour the
manifest contract. Treat it exactly as an emitter `exit 3`: the manifest is not
valid, so surface it in the run report and in `log_agent_lens.md`, and leave the
observation files and `agent-lens-runs.jsonl` entries alone (see failure
semantics below — the observations are the authoritative artefact).

This check exists because the emitter can only refuse what it is given. A tick
that assembles the JSON and writes it to `batches/` **without invoking the
emitter** bypasses every guarantee above, and the only thing that notices is the
nightly lint — a full day later, on a manifest a downstream consumer may already
have read. Verifying the artefact rather than trusting the procedure closes that
gap whatever its cause. Same check, same shape, as `/minder:mem:maintain` Step 6.6.

**Failure semantics:** if the JSON write fails, KEEP the
`agent-lens-runs.jsonl` entries already written and the
`_system/agent-lens/{lens-id}/{date}.md` files already on disk
(observation files ARE the authoritative artefact; the manifest is
downstream-routing). Surface as «agent-lens manifest write failed —
{cause}» CLARIFICATION; the next tick will re-attempt. Do not add a
BATCH_LOG.md row (`/minder:mem:agent-lens` does not write to BATCH_LOG —
that index is `/minder:mem:process` only).

---

## Step 6 — Log Summary

Append to `_system/state/log_agent_lens.md` a single block:

```
## {YYYY-MM-DD HH:MM:SSZ} — agent-lens run

Mode: --all-due | --lens X | --dry-run
Lenses considered: {count}
Lenses run: {count}
  - {lens-id}: {status} ({hits} hits, {duration_seconds}s)
  - ...
Lenses skipped (registry errors): {count}
Lenses skipped (not due): {count}
Lenses auto-paused this run: {list or "none"}
Total duration: {seconds}
```

`--dry-run` adds `[dry-run]` prefix in title and includes a note
«files NOT written» at end.

---

## Step 7 — Cleanup

- Delete `_sources/.agent-lens.lock` (in finally — guaranteed).
- Exit with single-line status:
  - `success` — all due lenses completed pipeline cleanly (some may
    be empty / rejected — those count as completed runs from the
    pipeline's POV)
  - `partial` — at least one lens errored at LLM/IO level (NOT
    validator rejection — those count as completed)
  - `lens-locked` — aborted at Step 0.2, lock active
  - `registry-error` — aborted at Step 2, registry malformed beyond
    individual-lens skip
  - `dry-run-complete` — `--dry-run` mode finished
  - `recent-run-blocked` — Step 0.3 blocked, no `--force`

---

## Skill-level invariants (doctrine §3.6)

- Never auto-promote a lens observation to constitution, knowledge,
  hub, or any owner-curated artefact. Outputs stay in
  `_system/agent-lens/{id}/` until owner manually promotes.
- Never overwrite owner edits to a lens prompt. If owner has modified
  `prompt.md` for a paused lens, do not silently un-pause.
- Never delete from `_sources/`. (This skill does not touch
  `_sources/` content — only writes its own `.lock` file there.)
- Never modify `0_constitution/`, `5_meta/mocs/`, `_system/SOUL.md`,
  `3_resources/people/PEOPLE.md`, `1_projects/PROJECTS.md`,
  `_system/state/OPEN_THREADS.md`. The lens **reads** these (via the
  thinker); the runner never writes to them.
- Never include lens outputs (`_system/agent-lens/`), rejected
  outputs (`_system/state/agent-lens-rejected/`) or raw thinker text
  (`_system/state/agent-lens-raw/`) in default search scope. Other skills that perform full-base search MUST exclude
  these paths (until QMD-isolation phase lands).

---

## Files written by this skill

Full descriptions in `_system/docs/SYSTEM_CONFIG.md` Files Reference.
Per-run write surface:

- `_system/agent-lens/{lens-id}/{date}.md` — overwrite if same date
- `_system/state/batches/{batch_id}-agent-lens.json` — once per tick (Step 5.95), only when ≥1 lens emitted with `status: ok`
- `_system/state/agent-lens-runs.jsonl` — append-only
- `_system/state/log_agent_lens.md` — append-only
- `_system/state/agent-lens-rejected/{lens-id}/{run_at-fs}.md` — append
- `_system/state/agent-lens-raw/{lens-id}/{run_at-fs}.md` — the thinker's verbatim text, one per thinker that answered; kept for good
- `_sources/.agent-lens.lock` — create + delete (concurrency lock)
- `_system/registries/lenses/{lens-id}/prompt.md` — frontmatter `status`
  only, only on auto-pause
- `_system/registries/AGENT_LENSES.md` — status column only, only on
  auto-pause
- `_system/state/CLARIFICATIONS.md` — append on registry errors / lock
  contention / auto-pause / missing context

## Files read by this skill

The thinker (Stage 1) has full read access to the Minder Memory base. The runner
itself reads:
- `_system/registries/AGENT_LENSES.md`, `lenses/**`
- `_system/agent-lens/**` (only when lens is `longitudinal` /
  `lens-decides`, or for meta-lenses)
- `_system/state/agent-lens-runs.jsonl` (last_run + recent-run check)
- `_system/docs/ENGINE_DOCTRINE.md`, `SYSTEM_CONFIG.md` (context load)

---

## Boundary cases

Behaviour following directly from Steps 0-7 (lock contention, registry
errors, validator rejection, --lens on paused, etc.) is described
in-place. Listed here are non-obvious cases that don't follow trivially
from the step text:

| Case | Behaviour |
|---|---|
| Thinker output but no specific paths | Structurer emits observations with `(no specific paths cited)` evidence; validator passes — diffuse patterns are valid signal, not a bug |
| Tick spans midnight | `run_at` captured once per tick, when the first cohort's Step 5.2 starts, and shared by every lens of the tick; the due set is computed once, for the UTC date noted at Step 0.1, and kept for the whole tick (consistency across lenses within one tick) |
| Owner edits a lens prompt mid-tick | Lens already loaded into memory at Step 2; mid-tick edits not picked up. Next tick sees them |
| Two lenses with same id | Both skipped (not first-wins); raises CLARIFICATION «id collision»; remaining lenses run normally |
| `--dry-run` on Active lens | Allowed — useful when iterating prompt of an already-deployed lens |
| `--dry-run` on draft lens | Requires `--lens` + `--include-draft` (testing intent); abort otherwise |

---

## Coordination with other skills

- `/minder:mem:lint` — lint may surface stale agent-lens artefacts (orphan
  output dirs for deleted lenses, runs.jsonl entries for removed lens
  ids). This skill does NOT clean those; lint is the cleaner. Adding
  this scan-class to lint is owner-driven future work.
- `/minder:mem:process` — exclusive via lock matrix. No data overlap on
  output paths (`_records/`, `1_projects/`, `5_meta/` vs
  `_system/agent-lens/`).
- `/minder:mem:capture-candidate` — independent. Lens observations are NOT
  principle candidates. Owner may, on review, manually create a
  principle candidate inspired by a lens observation; skill does not
  auto-link.
- `/minder:mem:check-decision` — independent. Owner may, on review, run
  check-decision on a lens observation that touches values. Skill-
  to-skill linkage is owner-mediated, not automated.
- `/minder:mem:bootstrap` — exclusive. Bootstrap reseeds system state and
  may rewrite registries.
- `/minder:mem:save` — sequential. Save runs after agent-lens completes;
  not concurrent.

---

## What good looks like (output contract)

A successful tick produces:
- 0 to N output files in `_system/agent-lens/{id}/{date}.md` (one per
  due lens, including empty-result files)
- Exactly N+M+R lines appended to `agent-lens-runs.jsonl` (N=ok,
  M=empty, R=rejected, all due lenses accounted for)
- One block in `log_agent_lens.md`
- 0 or more CLARIFICATIONS (only on registry errors / auto-pause /
  context-file missing)
- Lock file removed
- Exit status 0 with single-line status

The skill is intentionally narrow. Cross-cutting concerns (cleanup
of orphan files, schema migrations of runs.jsonl, archival of old
outputs) are NOT this skill's responsibility — those belong to lint
or owner.
