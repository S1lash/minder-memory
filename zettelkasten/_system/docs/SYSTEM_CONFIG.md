# Zettelkasten System Configuration

> **Documentation convention (binding):** любые изменения в этом файле + SKILL.md
> файлы + `_system/docs/batch-format.md` + связанные system specs подчиняются правилам
> [CONVENTIONS.md](../_system/docs/CONVENTIONS.md). Файлы описывают IS — current
> behavior, timeless spec. Никаких version/phase/release-notes narratives — они
> живут в git log.

---

## Overview

Это персональная система управления знаниями. Claude Code автоматически обрабатывает source-файлы из `_sources/inbox/` (whitelist живёт в `_system/registries/SOURCES.md` — voice-recorder transcripts, hand-written notes, Claude session recaps, и любые источники, которые owner добавил через `/minder:mem:source-add`), создавая структурированные Zettelkasten-заметки с богатыми метаданными для автоматизаций. После обработки исходные файлы перемещаются в `_sources/processed/`. Reference-материал, который не должен попадать в очередь обработки (raw payloads, escape-hatch данные), живёт в подкаталогах, помеченных колонкой `Skip Subdirs` в SOURCES.md. Self-descriptions / identity-материал — отдельный source `describe-me`: его читает и `/minder:mem:bootstrap` (как primary seed для SOUL.md, через свой контракт), и `/minder:mem:process` (как обычный контент). Файлы `*.template.md` не обрабатываются нигде — engine-wide правило (`/minder:mem:process` §2.2).

### Будущие автоматизации (контекст)
- Психолог / эдвайзер по жизни
- Рабочий эксперт / коуч / твин / помощник
- Таск-менеджер + календарь
- Агент для публичных профессиональных постов

### Document Ownership

This file is the **runtime configuration** loaded by `/minder:mem:process` at Step 1.
It defines note formats, entity types, naming conventions. Folder routing lives
in `_system/registries/FOLDERS.md → ## Routing Rules`.

For philosophy and architecture: see `5_meta/CONCEPT.md`.
For processing principles: see `5_meta/PROCESSING_PRINCIPLES.md`.
For pipeline algorithm: see SKILL.md (`/minder:mem:process`).
For batch output format: see `_system/docs/batch-format.md` (markdown
report + JSON manifest emission per `emit_batch_manifest.py`).

---

## CLARIFICATIONS Safety Valve (HARD RULE)

**При `confidence < threshold` скилл НЕ принимает решение молча — пишет вопрос в
`_system/state/CLARIFICATIONS.md` и продолжает работу с conservative default.**

Применяется ко ВСЕМ скиллам системы:

| Скилл | Типичный trigger для CLARIFICATIONS |
|---|---|
| `/minder:mem:bootstrap` | Неоднозначный tier человека, неясный thread closure, двусмысленный current focus, person identity collision |
| `/minder:mem:process` | Роль упомянутого неясна, splitting решение неоднозначно, cross-domain mapping сомнителен, domain value не resolved cascade'ом (`domain-resolution`) |
| `/minder:mem:maintain` | Thread вероятно закрылся, но confidence < 90% |
| `/minder:mem:lint` | Вероятный дубль с similarity < 95%, Evidence Trail backfill — какая трактовка |

Цель: система автономна + аудитируема. Owner раз в неделю отвечает на вопросы,
скиллы применяют ответы при следующем прогоне. Никаких молчаливых compromise.

### Canonical CLARIFICATION types (append-only)

Reason codes used by skills when raising entries to
`_system/state/CLARIFICATIONS.md`. Append-only — new types are added
as the engine evolves; renames are breaking changes that require
migrating existing open items.

| Type | Raised by | Trigger | Conservative default |
|---|---|---|---|
| `thread-hub-ambiguous` | `/minder:mem:maintain` | 2+ hubs pass topic filter with score ≥ 2 for the same thread | Skip linkage; thread stays without `hub:` |
| `tier-promote-suggested` | `/minder:mem:maintain` | Person mentions cross a tier-up threshold | No tier change applied |
| `principle-drift` | `/minder:mem:process` | `/minder:mem:check-decision` verdict violated at confidence ≥ 0.8 on an eligible artefact from the current batch — a knowledge note typed `decision`, or a record with `kind: observation` that the subagent flagged into `tradeoff_framing_records[]`, per §3.7.5. Each path selects on a field the layer it targets actually carries | Capture in trail; behaviour unchanged this batch |
| `principle-drift-retro` | `/minder:mem:lint` Scan F.2 | Same verdict + threshold as `principle-drift`, but on a historical decision-record re-checked against the current constitution tree. Trigger: explicit `--rescan-drift --days N` OR auto path on detecting `git log --since="${f2_last_ran_at}" -- 0_constitution/{axiom,principle,rule}/` non-empty | Capture in trail; owner reviews whether the principle edit was intentional |
| `people-bare-name` | `/minder:mem:process` (Step 3.7 escape hatch), `/minder:mem:lint` Scan C.5 (on aggregation), `/minder:mem:bootstrap` | A transcript mention whose name resolves to nobody in `PEOPLE.md`. Routine one-off mentions go to `people-candidates.jsonl` instead; this type is raised only when the high-importance escape hatch or C.5 promotion fires | Surface only. No profile is created and no `PEOPLE.md` row is written — per doctrine §3.6 there is no silent profile creation. Owner resolves via `/minder:mem:resolve-clarifications` (`resolve-bare-name` / `create-profile` / `dismiss`) |
| `person-identity` | `/minder:mem:process` (Step 3.7 escape hatch), `/minder:mem:bootstrap` | A mention that needs an identity decided — a new person, or a choice between existing candidates in `PEOPLE.md` | Surface only, same contract as `people-bare-name`. On `create-profile` the resolve skill writes `3_resources/people/{id}.md` + the `PEOPLE.md` row |
| `domain-resolution` | `/minder:mem:process` (Step 3.4.5) | Domain value cannot be resolved by the cascade `normalize_domain` → whitelist → LLM remap → trivial-vs-material | Drop the unmatched value; remaining `domains:` entries kept (possibly `[]`) |
| `process-compatibility` | every skill writing manifests | Schema deviation that would break the manifest contract with downstream consumers | Suspend that section's manifest emission until owner resolves |
| `concept-drift-on-reprocess` | `/minder:mem:process --reprocess-corpus` (Step 3.5) | Matcher's new `concepts:` set differs from prior set by > 50 % of the union (symmetric-difference / union ratio) | Apply the new (matcher-canonical) set; surface for owner audit, do not gate the write |
| `archive-note-missing` | `/minder:mem:lint` | File-based entity in archived state without `## Archive Note` block (per Archive Contract Form A); forward-only — pre-contract archives ignored | Surface for owner to fill `reason` / `triggered_by`; do not auto-write |
| `archive-reason-missing` | `/minder:mem:lint` | Registry-row in archived section with empty `Reason` cell, OR queue-archival action without required reason field (per Archive Contract Forms B and C) | Surface for owner to populate; do not auto-write |
| `batch-not-integrated` | `/minder:mem:lint` Scan A.12 | A `BATCH_LOG.md` batch older than 26 h has no `log_maintenance.md` entry — `/minder:mem:maintain` never consumed it. Its only trigger is Step 4.5 of the process tick, so a tick that skipped the step leaves a batch nobody integrates and still reports success | Surface as one aggregate naming every stale batch id; never autofix and never invoke maintain from lint — the two hold mutually exclusive locks, and a pipeline that quietly repairs another's omission hides it |
| `identity-orphan` | `/minder:mem:lint` Scan A.8, `/minder:mem:process` final gate | A tag `{namespace}/{id}` whose namespace a registry claims and whose identifier that registry never declared — live or retired. It is the one defect the identity procedure cannot reach by its own method: every other check reasons outward from a declared identity, so an identifier that was never declared is examined by nothing | Surface only, one item per tag and note. Never autofixed: registering the identity, retagging the note and dropping the tag are three different decisions and the scan cannot tell which is meant. Resolving one removes its row from `_system/state/identity-orphan-baseline.txt` |
| `telemetry-missing` | `/minder:mem:lint` Scan A.13 | A `[scheduled]` commit from the last 26 h whose diff never touched `_system/state/tick-telemetry.jsonl`, or a telemetry line with `status: unmeasured` — the tick ran and its Step 4.9 either did not run or found no transcript. The helper exits 0 unconditionally so the tick survives a broken odometer, which is exactly why nothing but this scan can see the failure | Surface as one aggregate naming the tick tags and SHAs; never autofix — the run's transcript lived in an ephemeral sandbox and is gone, so the measurement cannot be recomputed and must not be reconstructed |
| `telemetry-layout-drift` | `/minder:mem:lint` Scan A.13 | A telemetry line carries `layout_check: drift` — the tick recorded more `Agent` dispatches in its own transcript than sub-agent transcript files it could find, meaning the runtime moved where sub-agent sessions are written and every tick is now undercounting | Surface with the line's `agent_dispatches` / `subagent_files`; the fix is teaching `record_tick_telemetry.py` the new location, never adjusting the recorded numbers |
| `manifest-schema-violation` | `/minder:mem:lint` Scan H | A batch JSON manifest under `_system/state/batches/` fails validation against `_system/docs/manifest-schema/v{N}.json` for its declared `format_version` major | Do not rewrite the manifest (append-only); surface so owner can fix the producer or the schema |
| `manifest-schema-unknown-version` | `/minder:mem:lint` Scan H | Manifest's `format_version` major has no matching schema file in `manifest-schema/` | Surface; resolve by shipping the missing schema file or rolling back the producer |
| `validator-internal-error` | `/minder:mem:lint` Scan H | The schema validator raised an unexpected exception on a specific batch (json parse error, validator bug) | Lint continues other scans; owner reviews stack trace |
| `validator-helper-failed` | `/minder:mem:lint` Scan H | The `lint_manifest_schema.py` helper itself exited non-zero (jsonschema not installed, schemas-dir or batches-dir missing) | Lint continues other scans; owner restores the helper environment |
| `lens-action-proposed` | `/minder:mem:resolve-clarifications` (`--auto-mode` Step A.3) | Smart-resolve sweep judged a lens-emitted Action Hint as `queue` (not safe to auto-apply, not constitution-vetoed); the row carries `**Smart_resolve reasoning:**` + `**Action type:**` + `**Action params:**` for owner Class C review (apply / reject / modify / defer) | Queue stays as-is; auto-apply requires owner click |
| `lens-action-veto` | `/minder:mem:resolve-clarifications` (`--auto-mode` Step A.3) | Smart-resolve judged a lens-emitted Action Hint as `block-veto` against constitution / SOUL focus; row carries `**Smart_resolve reasoning:**` + `**Veto reason:**` naming the principle / SOUL element triggered. Step A.3.5 also routes here when an escalation `/minder:mem:check-decision` call returned `violated` at confidence ≥ 0.7 on a `queue` candidate; the row additionally carries `**Escalation-resolved by check-decision:**` annotation with the cited principle id | Owner reviews; can override per-class via `_system/state/insights-config.yaml::classes` |
| `lens-action-apply-failed` | `/minder:mem:resolve-clarifications` (`--auto-mode` Step A.3) | Handler validation failed inside apply (TOCTOU drift between Step A.1 stale-check and apply — e.g. another process created the hub target, or a cited note was renamed mid-tick) | Action is queued instead; owner reviews proposal + handler error reason |
| `biometric-baseline-cold-start` | `/minder:mem:process` metric-day branch | First metric-day file for a source processed AND `_system/state/biometric/<source>/baselines.json` does not exist | Initialize empty baselines for that source; emit informational CLARIFICATION (one-time per source, expected). Resolution: dismiss as resolved with note "expected cold-start". No further action needed |
| `biometric-threshold-drift` | `/minder:mem:maintain` Tier II calibration check | ≥3 consecutive weeks observed/expected fire-rate ratio outside [0.5, 2.0] for a metric × severity pair | Skip auto-tune; surface proposal with current vs proposed σ; owner approves via resolve action `threshold_tune_proposal` (Class C) |
| `biometric-affect-lexicon-empty` | `/minder:mem:maintain` Tier II Phase 2 | Lexicon overlay loaded successfully but produces zero affect tags across the entire 56-day window | Skip Phase 2; surface so owner can audit lexicon entries (may indicate non-RU/EN owner needs lexicon localisation via `affect_lexicon.local.yaml`) |
| `portable-name-collision` | `/minder:mem:process` §0.0b, `/minder:mem:save` Step 0.5, `/minder:mem:lint` A.10 | Non-portable (Windows-illegal) inbox name whose `normalize_portable_name()` form already exists in the same directory, or normalisation returned None | Skip the item this run (process) / exclude from staging (save); never guess a suffix |
| `portable-name-escape` | `/minder:mem:lint` A.10 | Non-portable tracked path outside `_sources/inbox/` and not grandfathered via PROCESSED.md — slipped past both ingestion gates | Surface only; rename + reference rewrite happens as an owner-reviewed resolve action, never autonomously |
| `source-layout-split-name` | `/minder:mem:process` §0.0a, `/minder:mem:lint` A.10a | An inbox directory carrying no item marker of its own but containing subdirectories, in a shape too ambiguous to rejoin — a producer's `/` in the recording title split one name into two folders | Leave the item in place and surface; the unambiguous single-child case is rejoined autonomously, everything else is never guessed |
| `content-type-canon-reviewed` | `/minder:mem:lint` A.11 | Judgment-row `content_type` drift mapped to its default canonical (weak × high) | Applied with the default; CLARIFICATION asks owner to validate (resolve action `canonicalize-content-type`) |
| `content-type-canon-surfaced` | `/minder:mem:lint` A.11 | Judgment-row `content_type` drift ambiguous between 2+ canonical types (weak × confident/unsure) | No apply; owner picks the canonical type with note excerpt in Context |
| `content-type-unknown` | `/minder:mem:lint` A.11 | `content_type` drift value not in `CANON_MAP` | No apply; owner picks a canonical mapping (optionally extends `CANON_MAP`) |
| `content-type-missing` | `/minder:mem:lint` A.11 | Note has `content_potential` but no `content_type` | No apply; owner sets the canonical type |
| `content-angle-missing` | `/minder:mem:lint` A.11 | Note has `content_potential` but empty/absent `content_angle` | Informational; the draft-maintainer proposes the hook on its next run |
| `frontmatter-unfixable-schema` | `/minder:mem:lint` A.2 | Frontmatter YAML does not parse and is not a repairable misplaced-fence case | Surface; owner fixes the schema by hand |
| `frontmatter-fence-misplaced` | `/minder:mem:lint` A.2, `/minder:mem:process` Step 4.5 | A `## ` body heading sits inside the YAML fence and `_common.repair_misplaced_fence` refused as ambiguous (multiple `---` in the displaced region) | Surface; owner relocates the closing `---` above the body |
| `task-aggregation-orphans` | `/minder:mem:lint` A.6.1 | `reconcile_tasks.py` finds open `- [ ]` task-ids in notes absent from every active/Stale section of TASKS.md | Surface count; owner runs `/minder:mem:process --reconcile-tasks` to classify + file them (read-only detection, no auto-write) |
| `hub-index-incomplete` | `/minder:mem:lint` A.6.2 | An on-disk `5_meta/mocs/hub-*.md` file is absent from HUB_INDEX.md | Surface missing ids; owner regenerates the index via `/minder:mem:maintain` |
| `calendar-aggregation-orphans` | `/minder:mem:lint` A.6.3 | `reconcile_calendar.py` finds a note with a future `📅` event whose link is absent from every forward-facing CALENDAR section | Surface count; owner runs `/minder:mem:process --reconcile-calendar` (read-only detection, no auto-write) |
| `role-secret-leak` | `/minder:mem:roles` | A credential surfaced in something the run produced. **The scan is store-wide, not limited to what the role declared** — otherwise a role could launder a sibling's credential by simply not naming it. What it looks at: an **in-zone** file's contents or its filename, the committed diff when HEAD moved, or the run line's own `note`. Matched in raw, base64, hex and percent-encoded form. Two stated limits — a credential shorter than 12 characters is never scanned (a short value false-positives on the owner's prose), and encodings are unbounded, so the scan raises the cost of an in-zone leak rather than closing the channel. Reverted when nothing of the owner's was at risk; left on disk when it was already dirty before that role started | Excluded from the role's commit either way, and named in `.scheduler-state/hold-back` so a scheduler tail cannot stage it afterwards — the credential never reaches history. Suggested action `rotate-credential`. Which credential leaked is deliberately not named: the tick never reads the secrets file |
| `role-head-moved` | `/minder:mem:roles` | `HEAD` moved between a role's snapshot and its check — the role committed, which the run frame forbids | No mutation at all: nothing reverted (a reset could destroy owner work committed alongside), out-of-zone paths reported. Run logged `error`. Suggested action `review-commit` |
| `role-unrestorable-write` | `/minder:mem:roles` | A role wrote outside its `writes:` to a path that was **already dirty when that role started**, so restoring it would destroy content the role did not author. Each reported entry carries `held_by`: `owner` (dirty since the tick baseline — the owner's uncommitted work) or `earlier-role` (dirtied during this tick). Not raised alongside `role-head-moved` — a moved HEAD means the guard mutated nothing, so «left alone» there does not mean «someone else's work was in the way» | Reported, never reverted — `git checkout --` there would erase that content. Suggested action `review-and-save`. A reported hole is recoverable; destroyed work is not |
| `role-guard-evaded` | `/minder:mem:roles` | The run changed something the guard cannot account for: git's own configuration (a remote's URL, `core.hooksPath`, an index flag, `.git/config`) differed between the snapshots, or the working tree kept changing after the role finished. An ignore change is NOT one of these — what it hid is attributed instead (see `role-ignore-changed`); it reaches this item only when a snapshot predates the ignored-path listing, so nothing could be attributed and the strict verdict stood. Both mean the role acted on the check itself rather than within it — the guard's whole model is that the repository is what `git status` prints, and these move that ground | Surfaced on the FIRST occurrence, never deferred to a repeat: the run is `error`, the tick stops dispatching further roles (every later check and push would stand on the changed ground), and nothing is repaired — reverting would mean writing inside `.git/`. Names the exact field with its before and after, or the paths that moved after the run. Suggested action `inspect-git-state` |
| `role-ignore-changed` | `/minder:mem:roles` | Git's ignore rules differed between the snapshots. An ignore rule hides a path from `git status`, which is what attribution reads — so the guard names every path that went invisible during the run and attributes it: digested, credential-scanned, and reported under the `ignored` label. Hiding therefore buys a role nothing, which is why this is not an evasion finding. The ordinary author is whatever hosts the tick, writing its own runtime files and rules into `.git/info/exclude` mid-run — a file the guard may not write to | The run is `ok` and the tick keeps dispatching — the danger was answered by looking, and an abort that fires on an ordinary night stops being read while taking the roles queued behind it down with it. Names the ignore files that differ, both digests, and every hidden path, stating that each was reported and deliberately **not** restored (for a path in no commit, «restore» means delete, and this is the path whose author the guard does not know). Carries NO credential-compromise warning — a hidden path that really carried one comes through `role-secret-leak`. Raised on the first occurrence and not again while an equivalent item is open. Stated limit: a path inside a directory that was already wholly ignored before the run is not covered — porcelain collapses it to one entry, so no comparison is possible. Suggested action `acknowledge` |
| `role-secrets-unavailable` | `/minder:mem:roles` | A credential store exists on this base but could not be opened for the tick: `MINDER_MEMORY_ROLES_KEY` is unset or wrong, or `cryptography` is not installed. Distinct from a declared name missing from the store, which preflight names at role-creation time — this is the whole store being unreadable at run time | Raised **once per tick**, not once per role: the condition is the key, not the roles. Roles declaring no credentials run untouched; every due role declaring one is skipped with an `error` run line naming the cause, because the file it would source does not exist and a half-reached outward call is worse than none. The tick never generates, repairs or guesses a key — a wrong one produces garbage silently and a new one orphans every stored credential. Suggested action `restore-secrets-key` |
| `role-repeated-degradation` | `/minder:mem:roles` | A role's two most recent run lines both ended `degraded` — it ran and delivered both times, but part of its job could not be done (a quota exhausted, a service refusing partway, a source unreachable), so some of what it reported is unverified | Role stays active. Suggested action `fix-role`. Raised only on the SECOND consecutive one: a single degraded run is a hiccup the next run covers, two is a standing limit that will keep hollowing out the role's work while every run line still reads as a success |
| `role-repeated-error` | `/minder:mem:roles` | A role's two most recent run lines both ended `error` | Role stays active and is attempted again next tick. Suggested action `fix-role` — owner repairs it or sets `status: paused` via `/minder:mem:role:edit`. A failing role never aborts a tick; only a changed git configuration or a broken guard stops further dispatch |
| `extraction-source-missing` | `/minder:mem:resolve-clarifications` Step 6.5 | An approved `knowledge-note` extraction has nowhere to go: `SOURCES.md` has no `resolve-clarifications` row under Active or Reserved Sources | No file is written; the item carries the approved text verbatim. Owner registers the source with `/minder:mem:source-add` (the command `/minder:mem:update` names) and drops the text into its inbox folder |

Per-skill SKILL.md may add narrower types for skill-internal flows;
this table covers the cross-skill canonical set referenced in
ENGINE_DOCTRINE §3.1.

---

## Cross-platform — Windows + macOS + Linux (HARD RULE)

Every engine artifact — migration, script, command, hook, path, symlink, doc
instruction — MUST work identically on all three platforms friends run: Windows
(Git Bash + `python3`), macOS (system **bash 3.2** + `python3`), Linux. Shell
must be bash-3.2-safe (no `mapfile`/`readarray`/`declare -A`/`${x^^}`) and use
portable commands only (no `md5`/`md5sum` split; `sed -i.bak` not `sed -i`; no
`readlink -f`); prefer `python3` for logic; resolve paths from repo-root, never
hardcode `/` or `C:\`; run scripts via `bash`/`python3` (no exec-bit); keep
`.sh`/`.py` LF (`.gitattributes` enforces it). Full statement + rationale:
`ENGINE_DOCTRINE.md §3.9`.

## Data & Processing Rules

Canonical rules, разделяемые между скиллами. Single source of truth.

### Mention counting (применяется в `/minder:mem:process`, `/minder:mem:maintain`, `/minder:mem:bootstrap`)

- **1 mention = 1 file**, где person появляется в `people:` frontmatter array OR является subject of record/note
- Не per-utterance, не per-topic. Длинная встреча с 6 упоминаниями человека = +1 mention, не +6
- Monotonic — counts только растут при `/minder:mem:process`. Decrements только при удалении нот (редкий случай, делается manually или `/minder:mem:lint` при dedup)
- `last_mention` date = latest `created` date across files referencing person

### People inclusion in `people:` frontmatter (применяется в `/minder:mem:process`)

- **Inclusion-biased**: если person resolved и упомянут в content (не noise) — добавлять в `people:` array
- Не применять эвристику "central to note" — это subjective и source of gaps
- **Bare first name** (без фамилии, не резолвится в full ID) → **append в `_system/state/people-candidates.jsonl`** (buffer) через `python3 _system/scripts/append_person_candidate.py`. **НЕ добавлять** в `people:`, **НЕ** raise CLARIFICATION per mention. `/minder:mem:lint` Scan C.5 еженедельно агрегирует buffer и promotes только recurring/information-rich candidates в CLARIFICATIONS. Rationale: снижает friction для one-off mentions (redesigned 2026-04-24).
- **Escape hatch** — raise CLARIFICATION immediately только при одном из явных сигналов: (a) external/client meeting, (b) full surname присутствует elsewhere в transcript но не сматчился из-за STT artifact, (c) user tag `@resolve-now`, (d) role+context полностью specified в mention. Подробности — `/minder:mem:process` Step 3.8.

### OPEN_THREADS grain (применяется в `/minder:mem:bootstrap`, `/minder:mem:maintain`)

- **Strategic grain only**: один thread = umbrella topic покрывающий несколько related TASKS.md Waiting items
- НЕ делать 1:1 mapping с TASKS.md Waiting — это operational layer
- Каждый thread должен иметь поле `## Related Tasks` со ссылками на TASKS.md tasks (для auto-closure tracking)
- Auto-closure: если все related tasks done/stale → thread → Resolved

### Thread ↔ Hub linkage (применяется в `/minder:mem:maintain` + `/minder:mem:lint`)

- При создании/обновлении thread: искать hub по теме (match по people + keyword signals). Если найден — thread field `hub: [[hub-id]]`
- При apparence thread — добавить bullet в hub's `## Открытые вопросы`
- При closure thread — убрать из hub's Open Questions, добавить resolution в hub's `## Ключевые выводы`
- `/minder:mem:lint` nightly verifies consistency: для каждого thread с `hub:` проверить существование hub и отсутствие drift между thread state и hub content

### Tier assignment (применяется в `/minder:mem:bootstrap`, `/minder:mem:maintain`, `/minder:mem:lint`)

- **Tier 1** — profile существует в `3_resources/people/{id}.md` OR mentions ≥ 8
- **Tier 2** — mentions 3-7 (no profile)
- **Tier 3** — mentions 1-2 (no profile)
- **stale** — 0 mentions, no profile (candidate для archival, но не автоматически)
- `/minder:mem:process` при добавлении нового человека: если creates profile → Tier 1, else Tier 3. Не пересчитывает existing entries
- `/minder:mem:maintain` при incremental update: **предлагает** promote Tier (3→2, 2→1) через CLARIFICATION `tier-promote-suggested`. **Никогда не применяет автоматически** — apply через `/minder:mem:resolve-clarifications` (owner confirms, skill diffs PEOPLE.md tier column). Никогда не demote (это `/minder:mem:lint` territory)
- Profile creation: для new person — inline в `/minder:mem:process` при достаточном контексте. Для existing person crossing Tier 1 threshold без profile — `/minder:mem:lint` generates profile skeleton при reviewed tier

### Profile template (canonical — applied by `/minder:mem:process`, `/minder:mem:lint`)

Все profiles (existing + auto-generated) match canonical template:

```yaml
---
id: {person-id}
name: "{Name cyrillic}"
role: {role}
org: {org}
tags:
  - person/{id}
  - org/{org}
  - role/{role}
---

# {Name cyrillic}

**Role:** {role summary one line}

## Контекст

{Narrative — role, relationship, recent notable context}

## Мои наблюдения

{Private — owner's subjective opinions. Structurally required section. NEVER auto-generated content. Auto-generation emits placeholder `_(заполняется вручную)_`}

## Упоминания

- [[note-id]] — {brief hint, date}
```

Order mandatory: frontmatter → `# Name` → `**Role:**` → `## Контекст` → `## Мои наблюдения` → `## Упоминания`.

### Log file ownership

- `log_lint.md` — written ONLY by `/minder:mem:lint`
- `log_maintenance.md` — written ONLY by `/minder:mem:maintain` + `/minder:mem:bootstrap`
- `log_process.md` — written ONLY by `/minder:mem:process`
- `log_agent_lens.md` — written ONLY by `/minder:mem:agent-lens`
- `agent-lens-runs.jsonl` — written ONLY by `/minder:mem:agent-lens` (append-only machine index)
- `tick-telemetry.jsonl` — written ONLY by `scripts/scheduler/record_tick_telemetry.py`, invoked at Step 4.9 of each scheduler tick (append-only, one line per tick, measured from the run's own transcript). Ticks only: a manual skill run writes nothing here, by design. The writer always exits 0, so `/minder:mem:lint` Scan A.13 is the only thing that can notice it stopped
- `resolve-sessions/{date}-{sid}.md` — written ONLY by `/minder:mem:resolve-clarifications` (one file per session, owner-readable narrative; `is_sensitive: true` by default)
- `lens-resolution-history.jsonl` — written ONLY by `/minder:mem:resolve-clarifications` interactive owner clicks (append-only precedent index; auto-mode applies do NOT write here — engine never trains on engine)
- `identity-gate.jsonl` — written ONLY by `identity_gate.py`, invoked from `/minder:mem:resolve-clarifications` Class I.5 (append-only per-identity scan record: command, exit code, residue count, HEAD). Created on first write; a base that has never retired an identity has no such file, and that is not a defect. `/minder:mem:lint` A.8 (9) reads it to corroborate an archived resolution's `gate` block — the reason it exists is that a payload alone is the writer's account of its own work
- `last-resolve-tick.txt` — written ONLY by `/minder:mem:resolve-clarifications` (high-water marker for «modified since» lens-output scan)
- `insights-config.yaml` — owner-mutable; engine creates from `.template` on first resolve run when missing, never rewrites
- Cross-reads OK (activity detection, context sourcing)

### Skill Write Territory (HARD RULES)

Pipeline skills have well-defined write territories: **each write-mode of a file
has exactly one owning skill.** A few files carry more than one write-mode (e.g.
OPEN_THREADS.md `## Active` is opened by maintain at strategic grain and appended
by resolve for lens/owner additions) — that is not an overlap, it is distinct
lanes with distinct owners. Writing outside your lane is a schema violation —
audits check this via git diff scope. This table is the single source of truth for
write territory; ENGINE_DOCTRINE §4 and `.claude/CLAUDE.md` point here rather than
restating it.

| Operation | Authorised skill | Rationale |
|---|---|---|
| Create new records / notes / tasks / events | `/minder:mem:process` only | Extraction from sources is the process domain |
| Aggregate note `- [ ]` tasks → `TASKS.md`; note `📅` events → `CALENDAR.md` | `/minder:mem:process` only | Derived aggregates (views over note items), NOT owner-authored files. Owner owns only the `## Stale` task section (preserved across regens). Completeness is guaranteed by `reconcile_tasks.py` / `reconcile_calendar.py` (Step 4.1/4.2 gate), not a full re-walk each run |
| Create a **full** hub (3+ note threshold) / update hub content (`Текущее понимание`, chronological map, changelog) in `5_meta/mocs/` | `/minder:mem:process` (additive, non-destructive) | Process records a batch's contribution; it MUST NOT full-rewrite `Текущее понимание` (single-batch view would destroy cross-batch synthesis). From-scratch re-synthesis is surfaced by `/minder:mem:lint` D.4 (`hub-stale-vs-material`), applied by owner — the synthesis layer is never auto-rewritten. (A lens-proposed **stub** hub is the separate lane below — `/minder:mem:resolve-clarifications`.) |
| Regenerate `HUB_INDEX.md` | `/minder:mem:maintain` (full rebuild) + `/minder:mem:process` (additive: append a newly-created hub) | Derived index of hub files. Drift (index behind on-disk hubs) is caught deterministically by `/minder:mem:lint` A.6.2 (`hub-index-incomplete`) → owner regens via `/minder:mem:maintain` |
| Increment PEOPLE.md `Mentions` column | `/minder:mem:process` only | Per-file counting happens inline at batch write |
| Modify body of existing records/notes | `/minder:mem:process` (initial) + `/minder:mem:lint` (dedup merge only) | Other skills reach a note only through the lanes this table names for them |
| Append `threads:` back-ref to record/note frontmatter | `/minder:mem:maintain` only | Structural metadata — body never touched |
| Tier change in PEOPLE.md (promote or demote) | **via `/minder:mem:resolve-clarifications` only** | Never auto-applied — surfaces CLARIFICATION |
| Thread closure (Active → Resolved in OPEN_THREADS.md) | **via `/minder:mem:resolve-clarifications` only** | Never auto-applied regardless of signal strength |
| Append row to OPEN_THREADS.md `## Active` | `/minder:mem:maintain` (strategic-grain thread opening) + `/minder:mem:resolve-clarifications` (auto-mode or owner click on `open_thread_add` lens hint) | Two write-modes, one owner each: maintain opens threads it detects at strategic grain; resolve applies lens/owner additions. Both additive; provenance via inline `from_lens` comment. `/minder:mem:process` never writes here (context-only) |
| Create new hub stub in `5_meta/mocs/` | `/minder:mem:resolve-clarifications` (`hub_stub_create` lens hint) OR owner-curated | New hub carries `from_lens:` in frontmatter; lint_hub_integrity passes the stub |
| Add wikilink to `## Связи (auto)` section in a knowledge note | `/minder:mem:resolve-clarifications` (`wikilink_add` lens hint) | Distinct section from manually curated `## Связи` so owner edits and auto edits don't collide |
| Append `## Update {today}` section to a decision note | `/minder:mem:resolve-clarifications` (`decision_update_section` lens hint) | Scaffold only — owner fills the body |
| SOUL.md edits (Identity / Focus / Working Style — outside auto-zone) | **manual only** | Identity file; auto-zone is a separate write-lane |
| SOUL.md auto-zone (Values between markers) | `render_soul_values.py` only | Deterministic render from `0_constitution/` |
| Write `_system/state/batches/{batch-id}-process.{md,json}` + `BATCH_LOG.md` row | `/minder:mem:process` only | One run = one batch; every other emitting skill writes only its own `-{skill}` pair |
| Hub linkage back-write (`hub:` field on thread, bullet in hub Open Questions) | `/minder:mem:maintain` only | Both sides updated atomically; lint verifies |
| Regenerate views (CONSTITUTION_INDEX, constitution-core, INDEX, HUB_INDEX, CURRENT_CONTEXT) | Scripts via `regen_all.py` / relevant skill | Views are derived — source is `0_constitution/` / knowledge notes / hubs |
| Create `_records/<family>/<source>/<date>.md` + update `_system/state/<family>/<source>/{baselines,streaks}.json` | `/minder:mem:process` metric-day branch only | Per-day deterministic emission from `_sources/inbox/<source>/<date>.md`, profile-driven (`<family>` = `biometric` for garmin/oura, `activity` for activitywatch). One source file → one record; records + baselines namespaced per source. Idempotent on re-run; content-hash drift auto-resolves by richness (richer-or-equal re-collect absorbed + baselines recomputed forward; poorer/empty keeps the existing record — no CLARIFICATION). |
| Write `_system/state/biometric/<source>/{correlations-{week}.json, calibration-history.json, last_weekly_run.txt}` + `_system/views/biometric/<source>/weekly-{week}.md` | `/minder:mem:maintain` only (biometric Tier II weekly worker, after-batch with weekly idempotency gate, run once per active biometric source) | Derived state — recomputable from `_records/biometric/<source>/`. Weekly-gated per source by `<source>/last_weekly_run.txt` ISO-week comparison; runs at most once per ISO week per source per first /minder:mem:maintain invocation. |
| Write `_system/state/activity/<source>/{weekly-{week}.json, last_weekly_run.txt}` + `_system/views/activity/<source>/weekly-{week}.md` | `/minder:mem:maintain` only (activity weekly worker, Step 6.8 — symmetric to biometric, after-batch with weekly idempotency gate) | Derived state — recomputable from `_records/activity/<source>/`. Activity has no σ-correlations/calibration layer (the heavy aggregation is upstream in the collector); the worker produces a weekly Focus-Engineering rollup (median scores, category/rhythm/switching trend, top death loops). Weekly-gated per source by `<source>/last_weekly_run.txt`. |
| Write `_system/roles/{id}/state/**` (the role's own tracked files) | the role itself, running inside `/minder:mem:roles` | The role's working memory — arbitrary files whose shape its own «Завершение» section defines. The engine never parses them; it only bounds where they land. `roles_guard.py` reverts out-of-zone writes after the run — except on a path already dirty when that role started, which it reports instead, because restoring it would destroy content the role did not author |
| Write `_system/roles/{id}/log.jsonl` | `/minder:mem:roles` only | One line per **executed** run (not per tick — a role whose cadence has not elapsed writes nothing). The role is explicitly barred from writing its own log; the tick appends it from the guard's verdict + the role's two-line return |
| Drop a note in `_sources/inbox/roles/` | a role with `inbox` in its `writes:` | The only path from a role back into the base. Flat file, `source: role:{id}` frontmatter, shape spec in `_system/roles/_minder.md`; `/minder:mem:process` then treats it as any other source |
| Drop a `knowledge-note` extraction in `_sources/inbox/resolve-clarifications/` | `/minder:mem:resolve-clarifications` (Step 6.5, after the owner approves it at the diff gate) | Knowledge the owner states while resolving becomes a source like any other, so `/minder:mem:process` stays the one writer of knowledge notes. Flat file, `source: resolve-clarifications` frontmatter; shape in that SKILL's Step 6.5 |
| Write `## Health Snapshot` block in CURRENT_CONTEXT.md | `/minder:mem:maintain` only (via `render_health_snapshot.py`, integrated into CURRENT_CONTEXT regen chain) | Extension of existing CURRENT_CONTEXT regen — derived view, not new content. ≤15 lines, life-connection focused. |
| Write rows in `1_projects/PROJECTS.md` (create, retire, reclassify) | `/minder:mem:resolve-clarifications` (identity changes — already the writer for `project-identity` items) + owner direct edit + `/minder:mem:bootstrap` (candidate seeding) | Identity is an owner decision, and resolve is the engine's one owner-driven write path. A retirement row names kind and successor per Identity Contract; without a named writer the contract has no obligee |
| Write the retirement section of `3_resources/people/PEOPLE.md` (`## Removed`) | `/minder:mem:resolve-clarifications` (identity changes) + owner direct edit + `/minder:mem:bootstrap` (candidate seeding) | Same lane and same reason as the projects registry. Distinct from `## Stale People`, which is a tier drop (archival), not an identity change |
| Append to `_system/state/identity-gate.jsonl` | `identity_gate.py` only, invoked from `/minder:mem:resolve-clarifications` Class I.5 | Append-only, never rewritten, never pruned. The writer is the script rather than the skill on purpose: the record has to be a side effect of the scan actually running, not something the run composes about itself afterwards. A skill that writes this line by hand has produced a claim, not a proof |
| Write AUTO-GENERATED zone of `5_meta/mocs/hub-cognitive-model.md` | `/minder:mem:maintain` only (via `render_cognitive_model_hub.py`, Step 7.9 — post-loop, after Step 7.8) | Pure projection of constitution `cognitive_axes` fields + candidate buffer; only the zone between the `<!-- AUTO-GENERATED: cognitive-model-hub -->` markers, never the owner's «portrait» above them. |

**Supporting invariants:**
1. `/minder:mem:maintain` NEVER creates knowledge content — no records, notes, or hub
   synthesis prose. It writes only structural state: back-references and
   strategic-grain thread opening in `OPEN_THREADS.md ## Active` (a tracking
   entry, not synthesis). Hub `Текущее понимание` synthesis is explicitly NOT
   maintain's — that stays with process (additive) + owner via lint D.4.
2. `/minder:mem:lint` NEVER applies closure or tier changes — only surfaces CLARIFICATIONS.
3. Hub `topic_relevance ≥ 1` required for hub ↔ thread linkage — pure people-overlap never links (prevents hub bloat).
4. Dedup (similarity ≥ 95%) is the ONLY body-edit `/minder:mem:lint` performs — it merges, never deletes unilaterally.
5. CLARIFICATIONS are the universal human-in-the-loop gate — any ambiguity at skill confidence below threshold writes a question, not a decision.

### CLARIFICATIONS format

All CLARIFICATION items MUST include:
- `**Context:**` field (2-4 sentence paragraph) — self-contained для LLM review session (owner не читает CLARIFICATIONS глазами напрямую, обсуждает с LLM)
- `**Quote:**` field — verbatim fragment when source = транскрипт
- Parsable fields: `Type`, `Subject`, `Source`, `Suggested action`, `Confidence tier`

Optional fields (added by specific producers; loose-parsed by `/minder:mem:resolve-clarifications`):
- `**Smart_resolve reasoning:**` — written by `/minder:mem:resolve-clarifications --auto-mode` when an item passes through the auto-resolve sweep but lands in the queue (not auto-applied). 1-3 sentences referencing constitution / past sessions / SOUL focus. Renders in resolve interactive Step 5 «Procedural context» block. Append-only — never rewritten on subsequent sweeps (latest sweep adds a new line if reasoning evolves)
- `**Action type:**` + `**Action params:**` (YAML inline) — written for `lens-action-proposed` items only. Carry the structured proposal that Class C apply / reject / modify operate on
- `**Veto reason:**` — written for `lens-action-veto` items only. Names the specific axiom / principle / rule ID or SOUL-section that triggered the veto
- `**Precedent:**` — optional list of `_system/state/resolve-sessions/{date}-{sid}.md` links with one-line summaries of how owner decided substantively-similar past proposals. Resolver renders these in Step 5 to ground owner judgement

Resolved items use structured format with `**Applied:** no|yes` field + `**Context:**` + `**Rationale:**` + canonical `Resolution-action` vocabulary. Single format — `## Open Items` + `## Resolved Items` sections only.

Owner-facing review path: `/minder:mem:resolve-clarifications` — interactive walker that clusters items by theme, reminds context inline, pre-forms hypotheses against constitution, applies confirmed resolutions, and archives closed items.

**Canonical `Resolution-action` vocabulary** (append-only evolution — stable contract for `/minder:mem:resolve-clarifications` and any future automated consumer):

| Action | Target | Payload example |
|---|---|---|
| `close-thread` | thread-id | `resolution_text: "Решение принято, выкатили X"` |
| `keep-thread-open` | thread-id | `(none)` |
| `close-partial` | thread-id | `remaining_tasks: [ids], new_status: "needs-decision"` |
| `promote-tier` | person-id | `from: 2, to: 1` |
| `demote-tier` | person-id | `from: 1, to: 2, reason: "inactive"` |
| `merge-notes` | kept-note-id | `deleted: [ids], merge_strategy: "A superset of B"` |
| `dismiss-duplicate` | note-id | `(none)` |
| `entity-retire` | entity-id | `kind: "merge \| rename \| split \| void", successor: "{id}" (merge and rename) \| successors: [{id}, ...] (split, ≥ 2) \| omitted (void), registry: "{path}", gate: {ts, command, exit_code: 0, residue_count: 0}` — an identity leaves circulation per Identity Contract; the `gate` block is the recorded per-identity scan that Obligation 4 requires, copied verbatim from the JSON line `identity_gate.py` printed; `ts` is what lets `/minder:mem:lint` A.8 (9) match the row against the gate's own log rather than against a number the row wrote about itself, and an archived row without the block is unproven. Interactive only, never `--auto-mode` |
| `entity-reclassify` | entity-id | `from_category: "project", to_category: "trajectory", registry: "{path}", gate: {ts, command, exit_code: 0, residue_count: 0}` — the identity stays alive and changes category; no successor. Interactive only |
| `backfill-evidence-trail` | note-id | `entries: [{date, source, action}]` |
| `resolve-bare-name` | subject-string | `person: person-id` OR `ignore: true` |
| `create-profile` | person-id | `from_tier: N, context_sources: [record-ids]` |
| `fix-process` | (free-form) | `suggestion: "process Step X.Y ..."` |
| `dismiss` | subject | `reason: noise | not-actionable | wontfix | stt-artifact` |
| `defer` | subject | `until: YYYY-MM-DD` |
| `validate-applied-fixes` | fix-id-range | `fix_ids: [ids], all_correct: bool, reverts: [ids]` |
| `pursue-or-close` | thread-id | `choice: pursue | close | keep-watching, note: "why"` |
| `review-soul` | soul-section | `edits_applied: bool, rationale: "..."` |
| `canonicalize-content-type` | note-id | `raw: "{drifted-value}", chosen: "{canonical-five}", applied: bool` — owner picked the canonical `content_type` for an A.11 judgment / unknown / reviewed item; note frontmatter rewritten + Evidence-Trail line |
| `decide-policy` | subject | `policy_chosen: "a|b|c|d", sdd_updated: bool` |
| `suppress-until` | subject | `date: YYYY-MM-DD, reason: "..."` — suppression cache entry |
| `update-hub-synthesis` | hub-id | `sections_updated: ["Текущее понимание", "Changelog"], notes_integrated: [ids]` — owner refreshed hub against fresh underlying material (D.4) |
| `split-hub` | hub-id | `new_hub_ids: [ids], theme_separation: "..."` — owner split a hub into ≥ 2 narrower hubs (D.4 split-mismatch resolution) |
| `archive-hub` | hub-id | `target_path: "4_archive/...", reason: "..."` — owner archived a hub whose theme is no longer active |
| `apply-lens-proposal` | `lens-action-proposed` item | `action_type: "wikilink_add | hub_stub_create | open_thread_add | decision_update_section", targets: [paths], from_lens: "{lens-id}/{date}", owner_modified: bool` — owner approved (and optionally modified) a queued lens-action proposal; resolver invokes `lens_action_handlers.APPLIERS[type]` and writes a row to `lens-resolution-history.jsonl` |
| `dismiss-lens-proposal` | `lens-action-proposed` / `lens-action-veto` item | `reason: "constitution-conflict | not-actionable | wrong-target | low-quality"` — owner rejected the proposal; row in history.jsonl marks the class_key as `reject` for future precedent grounding |
| `rotate-credential` | secret name (owner supplies — the tick does not know it) | `role: "{role-id}", rotated: bool` — a `role-secret-leak` item; owner treats the value as compromised, rotates it at the service, re-stores it through `/minder:mem:role:edit` (which re-encrypts that one value), and fixes what wrote it |
| `review-commit` | `{role-id}` | `before: sha, after: sha, kept: bool` — a `role-head-moved` item; owner inspects the commit the role made and keeps or reverts it by hand |
| `review-and-save` | `{role-id}` | `paths: [{path, held_by}]` — a `role-unrestorable-write` item; owner reviews paths the guard left alone because they were already dirty when the role started (`held_by: owner | earlier-role`), then keeps or discards |
| `inspect-git-state` | `{role-id}` | `field: "...", before: "...", after: "..."` or `paths: [...]` — a `role-guard-evaded` item; owner inspects git's configuration and the named paths by hand, because the engine deliberately does not write inside `.git/`. Treat any credential the role could reach as compromised |
| `restore-secrets-key` | tick timestamp | `resolved: bool, cause: "key-missing | key-wrong | package-missing"` — a `role-secrets-unavailable` item; owner puts the correct `MINDER_MEMORY_ROLES_KEY` into the scheduler routine's environment, or installs `cryptography`. The key itself is never recorded in the resolution |
| `acknowledge` | `{role-id}` | `note: "..."` — a finding the owner only needs to have seen. No repair, no external step: the engine reports it because it happened, not because it asks anything. Today's only user is `role-ignore-changed` |
| `fix-role` | `{role-id}` | `action: "edited | paused", note: "..."` — a `role-repeated-error` or `role-repeated-degradation` item; owner repairs the assignment via `/minder:mem:role:edit`, pauses it, or lifts whatever limit the role keeps hitting |

**Vocabulary governance:**
- Reason codes ending `-suggested` / `-resolved` / `-drift-warn` / `-promote-*` MUST use canonical vocabulary — feed `/minder:mem:resolve-clarifications` execution
- Reason codes ending `-reminder` / `-surfaced (policy-decision)` / `-advice` MAY use free-form Suggested action — conversational triggers, not executable operations
- New canonical verbs: append-only addition к this table. Removed / renamed verbs = breaking change requires migration of existing Resolved Items

### Cross-skill exclusion

All six pipeline skills (`/minder:mem:process`, `/minder:mem:maintain`, `/minder:mem:lint`, `/minder:mem:agent-lens`, `/minder:mem:content`, `/minder:mem:roles`) mutually exclusive. Each reads all seven `.{skill}.lock` files в `_sources/` (the six pipelines + `.resolve.lock`) on start. Any other skill's lock exists → abort. `/minder:mem:content` acquires `.content.lock` when it writes (`--maintain` / `--draft`); its read-only status mode needs no lock. `.content.lock` matters because the maintainer reads `CONTENT_MAP.md` while `/minder:mem:maintain` Step 7.8 rewrites it.

`/minder:mem:roles` acquires `.roles.lock` for the whole tick, held across every due role's run. It belongs in the matrix because roles write into the base like any pipeline: without the lock a concurrent `/minder:mem:lint` autofix lands inside a running role's diff window, is attributed to that role by `roles_guard.py`, and is **reverted** — the roles engine would silently destroy another pipeline's work. The consequence points the other way too: a role must not invoke a pipeline skill from inside its own run, since every one of them aborts on the lock its runner holds (`_system/roles/_minder.md` states this to the role).

The owner-driven role skills sit outside the matrix, each for its own reason. `/minder:mem:role:list` and `/minder:mem:role:ask` are read-only — no lock, nothing written, the role never run. `/minder:mem:role:add` and `/minder:mem:role:edit` take `.roles.lock` **narrowly and release it in a `finally`** — `edit` around the live write (a tick reads `role.md` while assembling a prompt, so an edit landing mid-tick would hand a role half of one version and half of another), `add` around its **Step 9 write** — the same reason as `edit`, and NOT around its trial run: the trial is `/minder:mem:roles --role {id}`, which acquires `.roles.lock` itself, so a caller holding it would deadlock the skill against its own gate and no role could ever be created. Neither holds the lock for the length of an owner conversation; both abort rather than wait if a tick already holds it.

`/minder:mem:resolve-clarifications` acquires `.resolve.lock` for both interactive and `--auto-mode` runs. Interactive mode reads all six pipeline locks (process / maintain / lint / agent-lens / content / roles) and aborts on any; it also pre-syncs via `/minder:mem:sync-data` (Step 0) so multi-device queues stay current. `/minder:mem:sync-data` and `/minder:mem:save` read **all seven** pipeline locks (process / maintain / lint / agent-lens / content / resolve / roles) and refuse while any is held — a rebase or a commit is equally unsafe under any running tick, and under `/minder:mem:roles` it is worse: `roles_guard.py` attributes every write in its diff window to the running role and reverts what falls outside that role's zone. Neither skill takes a lock of its own. The resolve skill's Step 9.1 releases `.resolve.lock` before reminding the owner to run save. **`--auto-mode` exception for `.lint.lock`:** auto-mode is dispatched by `/minder:mem:lint` Step 7.5 (lint holds its own lock during dispatch); treating that lock as competitor would deadlock the nightly chain. Auto-mode therefore proceeds when `.lint.lock` exists (it is the dispatcher's signature), aborts silently on any other pipeline lock (those should have cleared at lint's own Step 0.1; presence here means something genuinely went wrong — let the next nightly tick retry). Auto-mode also skips the Step 0 pre-sync (the dispatcher already synced, and lint's autofixes leave the working tree dirty) and never writes `lens-resolution-history.jsonl`.

**Nightly cadence:** three scheduler ticks. Agent-lens at 03:00 (lens production isolated), lint at 05:00 (invariant scans → Step 7.5 dispatches resolve --auto-mode inline → consumes fresh lens hints + new clarifications), roles at 07:00 (every due role, sequentially). Roles runs last of the three and ahead of the day's first process tick, so an inbox note a role leaves is folded in the same morning; its 07:00 slot is also the floor for any role cadence anchor, since an anchor later in the day is never reached at tick time. The two-hour gap separates lens emission from resolve consumption at the scheduler-agent-context level — the agent that judges proposals in Step A.2/A.3 has not just produced lens body output, which prevents confirmation bias on its own emissions. Lint and resolve in one tick is acceptable because their reasoning shapes are ortogonal (invariant pattern-match vs experienced-owner judgement) — minor contextual bleed in exchange for operational simplicity (one tick consumes the CLARIFICATIONS lint just emitted).

`/minder:mem:agent-lens-add` (lens creation wizard) is owner-driven, not in the lock matrix. It respects `/minder:mem:agent-lens`'s lock at pre-flight (would race on registry writes) but does not acquire its own — uses concurrent-edit detection (snapshot at Step 0, re-validate at write) to defend against rare parallel owner invocations.

**`/minder:mem:bootstrap` не входит в lock matrix** — disposable one-shot skill (запускается при системной инициализации, disaster recovery, onboarding'е друга). User ensures system idle before running bootstrap (runs <1 раз в год после initial setup).

---

## Architecture — Three Layers

Minder Memory v4 использует три слоя обработки знаний:

| Слой | Путь | Назначение | Формат |
|------|------|-----------|--------|
| Records | `_records/{meetings,observations}/` | Операционные логи transcript-grounded событий: рабочих встреч (`kind: meeting`) и соло Plaud-записей (`kind: observation`) | Лёгкий: summary + key points (+ action items для meetings) |
| Knowledge | PARA (`1_projects/`, `2_areas/`, `3_resources/`, `4_archive/`) | Атомарные инсайты, решения, идеи | Полный frontmatter + structured content |
| Hubs | `5_meta/mocs/` | Синтез и эволюция мышления по теме | Living document с chronological map |

**Принципы обработки:** `5_meta/PROCESSING_PRINCIPLES.md` (source of truth для LLM-суждений)
**Архитектура:** `5_meta/CONCEPT.md` (философия, ADR, примеры)
**Pipeline:** SKILL.md (`/minder:mem:process`) — полный алгоритм обработки

---

## Repository Structure

```
zettelkasten/
├── _sources/                         # ВСЕ сырые данные (input + processed)
│   ├── inbox/                        # Новые, необработанные файлы
│   │   └── {source-id}/              # Whitelist живёт в _system/registries/SOURCES.md.
│   │                                 # Layout каждой папки определяется колонкой Layout
│   │                                 # на её row: flat-md (*.md в корне) | dir-per-item
│   │                                 # ({folder}/transcript.md) | dir-with-summary
│   │                                 # ({folder}/transcript_with_summary.md preferred).
│   │                                 # Подкаталоги, объявленные в Skip Subdirs, исключены.
│   └── processed/                    # Обработанные файлы (зеркальная иерархия)
│       └── {source-id}/{id}/...
├── _records/                         # Слой 1: Records (операционная память)
│   ├── meetings/                     # Логи многосторонних встреч (kind: meeting)
│   └── observations/                 # Соло-записи: рефлексии, идеи, терапия (kind: observation)
├── _system/                          # Системные файлы
│   ├── SOUL.md                       # Identity + Focus + Working Style
│   ├── TASKS.md                      # Автогенерируемый список задач
│   ├── CALENDAR.md                   # Автогенерируемый календарь
│   ├── POSTS.md                      # Реестр опубликованных постов
│   ├── docs/                         # Платформенные документы (binding)
│   │   ├── SYSTEM_CONFIG.md          # Этот файл — runtime config
│   │   ├── ARCHITECTURE.md           # Системный дизайн как построен
│   │   ├── CONVENTIONS.md            # Documentation style rules (binding)
│   │   ├── batch-format.md           # Контракт batch формата
│   │   ├── constitution-capture.md   # Global hook (symlinked from ~/.claude/rules/)
│   │   └── harness-setup.md          # Per-machine install guide
│   ├── views/                        # Авто-генерируемые представления (read-only)
│   │   ├── CONSTITUTION_INDEX.md     # Registry активных principles
│   │   ├── constitution-core.md      # Harness view (symlinked from ~/.claude/rules/)
│   │   ├── HUB_INDEX.md              # Индекс всех hub-заметок
│   │   ├── INDEX.md                  # Surface catalog (knowledge + archive + constitution + hubs, faceted)
│   │   ├── CURRENT_CONTEXT.md        # Live state snapshot
│   │   └── CONTENT_MAP.md            # Content pipeline interface — view over hubs (writer: /minder:mem:maintain)
│   ├── state/                        # Pipeline state (write-heavy)
│   │   ├── content-pipeline-state.json  # Content ledger (drafts) — writer: /minder:mem:content --maintain
│   │   ├── BATCH_LOG.md              # Index всех batch-операций
│   │   ├── PROCESSED.md              # Source → Note маппинг
│   │   ├── CLARIFICATIONS.md         # Human-in-the-loop вопросы от скиллов
│   │   ├── OPEN_THREADS.md           # Незакрытые темы и ожидания
│   │   ├── principle-candidates.jsonl  # Append-only candidate buffer
│   │   ├── log_process.md            # Хронологический лог /minder:mem:process
│   │   ├── log_maintenance.md        # Append-only лог /minder:mem:maintain + /minder:mem:bootstrap
│   │   ├── log_lint.md               # Append-only лог /minder:mem:lint runs
│   │   ├── batches/                  # Полные batch-отчёты
│   │   └── lint-context/             # Lint Context Store: daily/ (30d rolling) + monthly/ (forever)
│   ├── scripts/                      # Python pipeline (см. scripts/README.md)
│   ├── roles/                        # Standing roles run by the /minder:mem:roles tick
│   │   ├── _run-frame.md             # Engine: per-run mechanics handed to every role
│   │   ├── _minder.md                # Engine: how to use the base, handed to every role
│   │   └── {role-id}/                # Owner data: role.md + state/ + log.jsonl
│   └── registries/                   # Реестры сущностей и форматные спеки
│       ├── TAGS.md                   # Реестр `tags:` namespace labels
│       ├── SOURCES.md                # Реестр источников
│       ├── FOLDERS.md                # Структура папок (этот layout)
│       ├── CONCEPT_NAMING.md         # Канонический формат concept-имён (snake_case)
│       ├── AUDIENCES.md              # Whitelist `audience_tags` privacy labels
│       ├── AGENT_LENSES.md           # Agent-lens registry
│       └── lenses/                   # Per-lens prompts + frame contract
├── 0_constitution/                   # Behavioural principles layer
│   ├── CONSTITUTION.md               # Root doc — scope, invariants, tree
│   ├── axiom/                        # Tier-1 axioms
│   ├── principle/                    # Tier-2 principles
│   └── rule/                         # Tier-3 rules
├── 1_projects/                       # Активные проекты
│   └── PROJECTS.md                   # Реестр проектов
├── 2_areas/                          # Области ответственности
│   ├── work/
│   │   ├── company/
│   │   ├── meetings/
│   │   ├── planning/
│   │   ├── reflection/
│   │   ├── technical/
│   │   └── team/
│   ├── career/
│   └── personal/
│       ├── reflection/
│       ├── health/
│       └── relationships/
├── 3_resources/                      # Ресурсы
│   ├── tech/
│   │   ├── ai-agents/
│   │   ├── architecture/
│   │   ├── fintech/
│   │   └── payments/
│   ├── ideas/
│   │   ├── business/
│   │   └── products/
│   └── people/                       # Профили людей
│       └── PEOPLE.md                 # Реестр людей
├── 4_archive/                        # Архив
├── 5_meta/                           # Мета-система
│   ├── CONCEPT.md                    # Архитектурный документ (source of truth)
│   ├── PROCESSING_PRINCIPLES.md      # 8 принципов обработки + values profile
│   ├── templates/
│   ├── workflows/
│   └── mocs/                         # Слой 3: Hubs (синтез и эволюция)
├── 5_skills/                         # Skills
└── 6_posts/                          # Опубликованный контент
```

---

## Naming Conventions

### Files
```
YYYYMMDD-short-semantic-name.md
```
- Дата в начале для сортировки
- Короткое смысловое имя на английском
- Lowercase, дефисы

**Примеры:**
- `20260125-meeting-ivan-petrov-restructuring.md`
- `20260113-idea-game-payment-gateway.md`
- `20260120-reflection-work-life-balance.md`

### Tags
```
category/specific-tag
```
- Lowercase
- Дефисы внутри слов
- Иерархия через `/`

**Примеры:**
- `type/meeting`
- `project/learning-goal`
- `person/ivan-petrov`

### Folders
- Lowercase
- Дефисы
- Без пробелов

### Entity IDs (people, projects)
- Lowercase
- Короткое имя
- `ivan-petrov`, `john-doe`, `acme-payments`, `project-alpha`

---

## Note Formats

Minder Memory v4 использует два формата: Record (лёгкий) и Knowledge Note (полный).
Шаблоны: `5_meta/templates/record-template.md`, `5_meta/templates/note-template.md`

### Record Frontmatter (layer: record)

Records have two kinds. `kind: meeting` для multi-speaker встреч; `kind: observation` для solo Plaud-записей. Поле `kind:` обязательно для observation; для meeting опционально (отсутствие = meeting для backward compat).

**Meeting record:**

```yaml
---
id: YYYYMMDD-meeting-{person}-{topic}
title: "Встреча: {тема}"
created: YYYY-MM-DD
source: _sources/processed/{source}/{timestamp}/transcript*.md

layer: record
kind: meeting              # optional — absence implies meeting (backward compat)
people:
  - person-id
projects:
  - project-id
concepts:                  # canonical concept names per CONCEPT_NAMING.md (snake_case ASCII)
  - concept_name_1
origin: work               # privacy trio per ENGINE_DOCTRINE §3.8 — defaults: work / [] / false on meeting
audience_tags: []
is_sensitive: false
tags:
  - record/meeting
  - person/{id}
  - project/{id}
---
```

Body: `## Summary`, `## Ключевые пункты`, `## Решения`, `## Action Items`, `## Упоминания людей`, `## Source`.

**Observation record:**

```yaml
---
id: YYYYMMDD-observation-{topic-slug}
title: "Наблюдение: {тема}"
created: YYYY-MM-DD
source: _sources/processed/{source}/{timestamp}/transcript_with_summary.md
recorded_at: {ISO timestamp}

layer: record
kind: observation          # mandatory
speaker: {person-id of the owner from SOUL.md Identity; "unknown" если ambiguous}
people:
  - {упомянутые по имени}
projects:
  - {если затронуты}
concepts:                  # canonical concept names per CONCEPT_NAMING.md
  - concept_name_1
origin: personal           # privacy trio — defaults: personal / [] / false on solo Plaud capture
audience_tags: []
is_sensitive: false        # set true on therapy / health / family / financial content
tags:
  - record/observation
  - person/{speaker}
  - topic/{topic}
---
```

Body: `## Summary`, `## Ключевые пункты`, `## Контекст / настроение` (опц.), `## Упоминания людей` (опц.), `## Source`. NO `## Решения` / `## Action Items` (живут в knowledge notes c `extracted_from:`).

Полный шаблон observation: `5_meta/templates/observation-record-template.md`.

### Biometric Record (kind: biometric)

Auto-emitted by `/minder:mem:process` metric-day branch from
`_sources/inbox/{source-id}/<date>.md` (e.g. `garmin`). One file per
calendar day. NO LLM in the emission path — pure deterministic Python
(`process_metric_day.py`). Owner never hand-edits.

```yaml
---
date: '<YYYY-MM-DD>'
kind: biometric
domains: [health]
people: []
audience_tags: []          # owner-only by family default
is_sensitive: true         # health data → friction on share
origin: personal
device: <source>           # which wearable feed this record belongs to (garmin, oura)
device_estimate: true      # wearable numbers are device estimates, not ground truth
concepts:                  # streak / event concepts emitted by Tier I
  - low_hrv_streak
  - sleep_debt
metric_failures: [...]     # only present when the source carried metric_failures
source: <source>/<date>.md
created: '<YYYY-MM-DDTHH:MM:SSZ>'
source_hash: <16-hex>      # hash of source content; drives re-render drift detection (richer-wins auto-absorb)
---
```

Body sections (only emit when non-empty):

- `# Biometric — <date>`
- `## Summary` — verbatim from source's `## Summary`
- `## Key Numbers` — extracted top-level YAML (sleep_h, hrv_ms,
  rhr, bb_end, stress_avg, readiness, train_status, acwr, steps,
  vo2max_running, …)
- `## Baseline Deviations` — σ-distance flags (light / medium / strong)
- `## Categorical Events` — status transitions (HRV, training, ACWR, readiness)
- `## Active Streaks` — current streak concepts with day count + start date
- `## Streak Transitions` — start / end events on this date
- `## Source` — wikilink to processed source for traceability

**Family-default privacy trio.** Set declaratively in
`process_metric_day.py` from the SOURCES.md row's `Family: metric-day`:
`is_sensitive: true`, `audience_tags: []`, `origin: personal`. Per-record
override is NOT a normal path — biometric data is owner-only by design.

**Idempotency.** Re-running `/minder:mem:process` on an already-processed source
is a no-op log line. Content-hash drift between source and existing record
is resolved autonomously by richness — a richer-or-equal re-collect (a
healed device→cloud sync gap, a provider backfill) is absorbed and baselines
are recomputed forward; a poorer/empty re-collect keeps the existing record.
No owner CLARIFICATION — metric-day records are deterministic device
projections with no owner edits to protect (doctrine §3.1).

### Activity Record (kind: activity)

The behavioural sibling of the biometric record — same metric-day pipeline,
the **activity** profile. Auto-emitted by `/minder:mem:process` from
`_sources/inbox/activitywatch/<date>.md`. One file per calendar day, pure
deterministic Python, owner never hand-edits. Computer-usage / attention
telemetry, NOT physiology — so a distinct `kind` and namespace
(`_records/activity/<source>/`), never under `biometric/`. The heavy
aggregation (Focus-Engineering metrics) runs upstream in the collector
(`minder-activity-collector`); Minder Memory ingests clean facts and σ-tracks them.

```yaml
---
date: '<YYYY-MM-DD>'
kind: activity
domains: [time, work]      # the meta-practice of running the day + work context
people: []
audience_tags: []          # owner-only by profile default
is_sensitive: true         # window titles / URLs captured verbatim → leak work/client identifiers
origin: personal
device: <source>           # activitywatch
concepts:                  # activity streak concepts (no device_estimate field — measured, not estimated)
  - late_night_work_streak
  - focus_drop_streak
source: <source>/<date>.md
created: '<YYYY-MM-DDTHH:MM:SSZ>'
source_hash: <16-hex>
---
```

Body sections (only emit when non-empty):

- `# Activity — <date>`
- `## Summary` — verbatim from source (scores, switching split, top death loop, categories, rhythm)
- `## Key Numbers` — focus / productivity / combined scores, `sustained_focus_h`,
  `human_switches`/`human_switches_per_active_hour` (genuine fragmentation — AI-coding
  churn split into `ai_assisted_*`), `top_death_loop(s)`, `late_night_ratio`,
  `early_morning_h`, `meeting_h`, work/personal split, `top_category`, `top_project`, …
- `## Baseline Deviations` — σ-flags on the non-sparse metrics only (focus/productivity/
  human-switch-rate/late-night/meeting/longest-block; sparse metrics like
  `early_morning_h` are tracked but never σ-flagged)
- `## Active Streaks` / `## Streak Transitions` — activity streak state
- `## Source` — wikilink to processed source

(No `## Categorical Events` — the activity profile carries no categorical pairs.)
Privacy + idempotency identical to the biometric record. Near-idle days
(`active_h < 0.5`) emit a record but are excluded from baselines and carry no
scores (the collector nulls them).

### Knowledge Note Frontmatter (layer: knowledge)

```yaml
---
id: YYYYMMDD-{type}-{topic}
title: "{Title}"
created: YYYY-MM-DD
modified: YYYY-MM-DD
source: _sources/processed/{source}/{timestamp}/transcript*.md
extracted_from: {record-id}  # если извлечён из record
related_to: {primary-note-id}  # если не primary note из группы (optional)
supersedes: {previous-note-id}  # если пересматривает предыдущее решение (optional)

layer: knowledge
types:
  - decision|insight|reflection|idea|technical
domains:
  - work|career|personal
projects:
  - project-id
people:
  - person-id

# contains: (OPTIONAL — include only when note has tasks/ideas/meetings)
# Omit entirely if all counts are 0 or if the only non-zero count is obvious from type.
#   tasks: N
#   ideas: N

status: actionable|reference|archived
archived_at: YYYY-MM-DD  # REQUIRED when status: archived (per Archive Contract Form A); equals `## Archive Note` date
priority: high|normal|low
content_potential: high|medium  # OPTIONAL — set by pipeline when note has public value
content_type: expert|reflection|story|insight|observation  # OPTIONAL — set with content_potential
content_angle: ["hook1", "hook2"]  # OPTIONAL — ALWAYS a list (single angle = 1-element list); lint A.11 normalizes a stray string
mentions: N  # OPTIONAL — for idea notes, counts how many times idea surfaced across transcripts

concepts:                                 # canonical concept names per CONCEPT_NAMING.md
  - concept_name_1
  - concept_name_2

# Privacy trio per ENGINE_DOCTRINE §3.8.
# `origin` ∈ {personal, work, external}; `audience_tags[]` from
# canonical 5 + AUDIENCES.md extensions; `is_sensitive` is bool.
# Defaults are conservative-safe (`personal` / `[]` / `false`).
origin: personal
audience_tags: []
is_sensitive: false

tags:
  - type/{type}
  - domain/{domain}
  - person/{id}
  - project/{id}
---
```

Knowledge note content: structured по теме (контекст, ключевая мысль, применение, связи).

### Hub Frontmatter (layer: hub)

```yaml
---
id: hub-{topic-slug}
title: "Hub: {Topic Name}"
aliases: []
created: YYYY-MM-DD
modified: YYYY-MM-DD
hub_created: YYYY-MM-DD

layer: hub
# Identity category of the hub — project | trajectory | domain.
# Absent → project. Semantics + eligibility for the membership axis:
# `## Identity Contract` in this file.
hub_kind: project
domains:
  - work|personal|career
projects: []
people: []

# Rendering policy for `## Хронологическая карта` — derived | curated.
# Absent → curated. `derived` means `/minder:mem:maintain` regenerates the map
# block via `_system/scripts/render_hub_maps.py`, and the body must carry
# the AUTO-GENERATED markers; `curated` means the owner maintains it.
# `excluded_from_map` holds record-ids the derived map skips;
# `excluded_from_map_reasons` is parallel to it and MUST be the same length.
chronological_map_mode: curated
excluded_from_map: []
excluded_from_map_reasons: []

# Privacy trio — auto-derived by `_common.py::recompute_hub_trio()`
# from member-note trios. `_engine_derived` lists fields the engine
# currently owns and re-derives on every touch. Owner takes over a
# field by removing its name from `_engine_derived`; the value is then
# preserved permanently. Hub frontmatter does NOT carry `concepts:` —
# `member_concepts` is manifest-only, derived at emission time.
origin: personal|work|external
audience_tags: []
is_sensitive: false
_engine_derived:
  - origin
  - audience_tags
  - is_sensitive

related_notes: N
first_mention: YYYY-MM-DD
last_mention: YYYY-MM-DD
cadence: daily|weekly|sporadic

status: active|dormant|resolved
priority: high|normal|low

tags:
  - hub
  - domain/{domain}
  - topic/{topic}
---
```

Hub content structure: `## Текущее понимание` (с подсекциями `### Ключевые выводы`,
`### Открытые вопросы`, `### Активные риски`), `## Хронологическая карта`,
`## Связанные знания` (с подсекциями `### Решения`, `### Инсайты`, `### Cross-Domain связи`),
`## Changelog`.

Шаблон: `5_meta/templates/hub-template.md`

### Source Section (вместо `<details>`)

Оригинальный транскрипт НЕ дублируется в заметках — он живёт в `_sources/processed/`.
Записи и заметки содержат `## Source` секцию со ссылкой:

```markdown
## Source

**Transcript:** `_sources/processed/plaud/{timestamp}/transcript_with_summary.md`
**Recorded:** YYYY-MM-DDTHH:MM:SSZ
```

Full-text search по raw content: `grep -r "keyword" zettelkasten/_sources/`

---

## Types (type:)

Словарь описывает сами типы. Папку заметки определяют правила маршрутизации —
`_system/registries/FOLDERS.md → ## Routing Rules`.

| Type | Description |
|------|-------------|
| meeting | Встреча, совещание — **DEPRECATED**: новые встречи создаются как records (`kind: meeting`) |
| reflection | Рефлексия, размышления |
| insight | Неочевидная связь, вывод, распознанный паттерн |
| task | Задача (редко отдельно) |
| idea | Идея |
| decision | Решение |
| log | Дневник, отчёт |
| planning | Планирование |
| technical | Техническое |
| reference | Справка |
| person | Профиль человека |
| project | Описание проекта |
| record | Операционный лог transcript-grounded события (kind: meeting или observation) |
| hub | Hub — синтез и эволюция по теме |

---

## Domains (domain:)

| Domain | Description |
|--------|-------------|
| work | Работа (проекты, команда, планирование) |
| career | Карьера (повышение, развитие) |
| personal | Личное (рефлексия, здоровье) |

---

## Statuses (status:)

| Status | Description |
|--------|-------------|
| actionable | Требует действий |
| waiting | Ждёт чего-то |
| someday | Когда-нибудь |
| reference | Просто информация |
| archived | В архиве |

---

## Archive Contract

**Invariant:** every archival event captures a reason. The reason lives **with the entity** — never in a parallel log, never as derived state. One source of truth per archived entity.

Archival event = transition where an entity stops being part of the active surface: knowledge-note moved to `4_archive/`, frontmatter `status: archived`, principle `status: archived`, registry row moved to a Deprecated/Stale section, lens `status: paused|archived`, person tier dropped to `stale`, candidate dismissed via CLARIFICATION resolution.

This contract applies **forward-only**: every archival event from contract adoption onward MUST carry a reason. Pre-existing archived entities are not backfilled.

**Identity boundary.** `## Identity Contract` below governs what happens to an identifier when it stops being valid — archival leaves the identifier valid, an identity change ends it.

### Form by entity shape

Three forms — pick by shape, not by skill. Every archival pathway falls into exactly one.

#### Form A — Inline `## Archive Note` (file-based entities)

For knowledge notes, hubs, principles (axiom / principle / rule), and any other entity that exists as a standalone `.md` file. Append-only block at the **end** of the file (after Evidence Trail, before any other trailing sections):

```markdown
## Archive Note

- date: YYYY-MM-DD
- reason: "<one-sentence rationale in owner's natural language>"
- triggered_by: owner | /minder:mem:lint F.3 | /minder:mem:resolve-clarifications | <skill-id>
- superseded_by: [[wikilink]]   # REQUIRED when the reason is a merge or a rename; otherwise omit
```

Plus frontmatter flags for machine-readable state:

```yaml
status: archived
archived_at: YYYY-MM-DD
```

Frontmatter `archived_at` MUST equal `## Archive Note` `date`. Skill enforcement: any writer that flips `status: archived` MUST append `## Archive Note` in the same atomic write. Writing one without the other = contract violation; surfaces as `archive-note-missing` CLARIFICATION on next `/minder:mem:lint`.

`triggered_by` value is the agent of the archival event — `owner` for direct hand-edits, the skill id (`/minder:mem:lint`, `/minder:mem:resolve-clarifications`, etc.) for engine-driven archivals. When a skill applies a CLARIFICATION resolution, the skill id wins (not `owner`); the resolution text is what carries the owner's reasoning into `reason`.

**Constitution-principle exception (single-source-of-truth guard).** Files under `0_constitution/{axiom,principle,rule}/` already use the Evidence Trail pattern. Per `0_constitution/CONSTITUTION.md` §9, archiving a principle appends a `deprecated` entry of the form `deprecated — reason: {reason}; status: archived` to the Evidence Trail. **That entry IS the Form A storage for principles** — do not also append a `## Archive Note` block. The `deprecated` Evidence Trail entry is the contract-required reason for principles; frontmatter `status: archived` is the machine flag (no `archived_at` — Evidence Trail entry date is the authoritative date).

#### Form B — `Reason` column (registry-row entities)

For entities whose canonical form is a row in a registry table — PEOPLE.md, PROJECTS.md, SOURCES.md, AGENT_LENSES.md, TASKS.md.

**Canonical pattern: split table.** Each registry holds active rows and archived rows in **separate tables / sections**. The archived sub-table carries a `Reason` column; the active table does not. Archival = move the row from the active table to the archived sub-table and populate `Reason`. This keeps active rows clean (no empty trailing cells) and makes archival a discrete writer operation.

Where the archived sub-table lives per registry:

| Registry | Active section | Archived sub-table |
|---|---|---|
| `3_resources/people/PEOPLE.md` | `## People` (tier 1 / 2 / 3) | `## Stale People` (tier `stale`) |
| `1_projects/PROJECTS.md` | `## Active Projects`, `## Completed Projects` | `## Archived Projects` (status `archived` — dropped before completion; completed projects are not an archival event and do not require Reason) |
| `1_projects/PROJECTS.md` | `## Active Projects`, `## Trajectories` | `## Retired Identifiers` (identity retirement — the `Successor` cell is the one Form A requires; a `split` row lists all of them, comma-separated) |
| `_system/registries/SOURCES.md` | `## Active Sources`, `## Reserved Sources` | `## Deprecated Sources` |
| `_system/registries/AGENT_LENSES.md` | `## Active Lenses`, `## Draft Lenses` | `## Paused/Archived Lenses` (status `paused` / `archived`) |

**Bullet-list variant for `_system/TASKS.md`.** Tasks live in bullet lists, not tables. The Stale section MUST carry a trailing `*(reason)*` italic suffix on every bullet — this is the bullet-list equivalent of the `Reason` column. Example: `- [ ] Подготовить презентацию для встречи в Баку — [[20260114-baku-presentation]] ^task-prepare-baku-presentation *(Баку прошло)*`.

Skill enforcement: any writer that moves a row into an archived sub-table (or a bullet into TASKS Stale) MUST populate `Reason` / `*(reason)*`. Empty cell or missing italic surfaces as `archive-reason-missing` CLARIFICATION on next `/minder:mem:lint`.

#### Form C — Existing structured field (queue-based archival)

For archival driven by a CLARIFICATIONS resolution or by a candidate-buffer dismissal, the reason already lives in an existing structured field. The contract does not invent new fields — it makes existing ones **required** for the archival sub-set of actions.

| Source | Field | Required for actions |
|---|---|---|
| `_system/state/CLARIFICATIONS.md` Resolved Items | `**Rationale:**` | every action whose effect is archival: `dismiss`, `dismiss-duplicate`, `archive-hub`, `close-thread`, `demote-tier`, `merge-notes` (the merged-away side), `pursue-or-close` with `choice: close` |
| `_system/state/people-candidates.jsonl` weekly-dismissed archive | `dismissal_reason` | every line written to `lint-context/weekly/{YYYY-WW}-people-candidates-dismissed.jsonl` |
| `_system/state/OPEN_THREADS.md` Resolved section | `resolution_text` (already required by `close-thread` action) | every entry under `## Resolved` |

Skill enforcement: any resolution that triggers archival without populating the required field surfaces as `archive-reason-missing` CLARIFICATION.

**Out of scope for Form C:** weekly bulk-archive of `principle-candidates.jsonl` via `archive_buffer.py` is a buffer-rollover snapshot, not a per-line rejection event — it preserves history of all candidates (promoted and rejected alike). Per-candidate rejection reason lives in the CLARIFICATIONS resolution that disposed of that candidate (Form C row 1).

### Cross-cutting rules

- **Atomic write.** The archival flag (`status: archived` / row move / tier change) and the reason (`## Archive Note` / `Reason` column / required field) MUST land in the same write. No two-stage archival.
- **Append-only.** Archive Notes and Reason cells are written once at archival time. Owner can later edit free-form text but never deletes the structure. Re-archival of an already-archived entity is a no-op (idempotency); a second `## Archive Note` block is forbidden.
- **No parallel log.** There is no `log_archival.md`. Cross-entity «what was archived in period X» is a derived view, generated on demand by reading the entities themselves.
- **Lint enforcement.** `/minder:mem:lint` adds an Archive-contract scan that emits `archive-note-missing` / `archive-reason-missing` CLARIFICATIONs for entities found in archived state without the required reason. Forward-only: pre-contract archived entities are not flagged.
- **Suggested-action vocabulary stays unchanged.** The canonical `Resolution-action` table above already carries `reason` payload examples (`dismiss`, `demote-tier`, `archive-hub`); this contract elevates them from documented-payload to enforced-required for the archival subset.

---

## Identity Contract

**Invariant:** an identity change is atomic and leaves zero residue. Companion to Archive Contract above, which owns the *reason* and the *successor* of every archival event; this contract owns *what else has to move* when an identifier stops being valid.

**Identity** = anything that has an identifier, a registry that declares it, and places that refer to it: a person, a project, a trajectory, a concept, a hub, a source, a lens. One procedure for all of them — the registry declares which surfaces it has and at which paths, everything below is shared. A new kind of identity that needs a special rule inside the procedure, rather than a row in its registry's own declaration, means the procedure is written wrong.

**What the procedure runs on today, and what the rest use instead.** The obligations below are enforced by `identity_audit.py` for the two registries that declare surfaces to it — `PROJECTS.md` (projects and trajectories) and `PEOPLE.md`. The other kinds are not covered by silence; each has its own mechanism, and naming it is the difference between a contract and a claim:

| Kind | How its identity change is carried | Detector |
|---|---|---|
| project, trajectory, person | this contract, in full | `identity_audit.py`, blocking at the `/minder:mem:process` final gate and re-run nightly by `/minder:mem:lint` A.8 |
| concept | `CONCEPTS.md` is a regenerated census, not a declaration: a rename is carried by the `aliases` column, which lint applies, and the census is rebuilt from the corpus | the alias application itself; no residue scan |
| source | `SOURCES.md → ## Deprecated Sources` | none |
| hub without a registry identity (`hub_kind: domain`) | Archive Contract Form A, with the `superseded_by` pointer the resolver reads | none |
| lens | nothing — a lens has never been retired, and no mechanism is written for it | none |

A row saying «none» is a statement about this engine, not a licence: the obligations still hold for whoever performs the change by hand, and nothing checks that they did. Adding a registry to the enforced set is a `RegistrySpec` declaration plus a parser — by design it is a row of data, never a special rule inside the procedure.

Birth of an identity is `## Entity Matching` below; this contract governs everything after it.

### Kinds of identity change

| Kind | What happens | Successor | Person-side example | Project-side example |
|---|---|---|---|---|
| merge | the entity became part of another | required | two rows turn out to be one person | two projects fold into one umbrella |
| rename | same entity, different identifier | required | a misspelt surname corrected | identifier renamed to its real scope |
| split | the entity became two or more | two or more required | one row turns out to be two namesakes | an umbrella that was really two efforts |
| reclassify | entity stays alive, category changes | not applicable | a row that is an organization, not a person | a project becomes a trajectory |
| void | the entity never existed | forbidden | a speech-to-text artefact that named no one | a placeholder id that never had content |

### Surfaces — roles, not paths

| Role | What it is |
|---|---|
| membership field | the frontmatter axis naming the identity (`projects:`, `people:`) |
| namespaced tag | `{namespace}/{id}` in `tags:` |
| wikilink | `[[id]]`, bare or labelled |
| node card | the identity's own `.md` file |
| node container | the identity's own folder plus its README |
| hub | a hub whose own identifier is exactly `hub-{id}` |
| registry row | the row in the registry that declares the identity |
| tag-registry row | the row counting the namespaced tag in TAGS.md — a census entry, not a declaration, and therefore DERIVED: it is corrected by regenerating the census, and a hand edit is undone by the next render |

A role a registry does not declare does not exist for that registry. **Matching is exact identifier equality, never substring** — on every role. A longer identifier that contains a retired one is a different identity and is never touched; every replacement template is anchored on the full token in a known position.

**A hub declares its identity's category** in `hub_kind:` — `project`, `trajectory` or `domain`, defaulting to `project` when absent. This is the hub-side statement of the same category the registry declares, and the two must agree — disagreement is a defect of the pair, reported by the identity scan against the hub and never silently repaired, because rewriting either side moves every member note between axes. Only `project` is eligible for the membership axis: a `trajectory` is carried as `tags: [trajectory/{id}]`, a `domain` as `domains:`. A `hub_kind` value outside the three is a defect, and changing one is an identity change of the reclassify kind — never a silent fix, because it moves every member note between axes.

A hub whose own identifier is not `hub-{id}` for any registered identity is not a surface of anything — it is an identity in its own right, and its retirement is Archive Contract Form A with a `superseded_by` pointer the resolver reads.

### Surface classes

| Class | Obligation |
|---|---|
| LIVE | migrate — membership fields, tags, wikilinks, nodes, and the registry row that *declares* an identity |
| DERIVED | regenerate, never hand-edit — a hand edit is undone by the next regeneration. Aggregate views, indexes, rendered views |
| IMMUTABLE | never touched, and excluded from the residue check by rule |
| UNCLASSIFIED | a path no rule claims. Counted as residue, because a scan that silently skips what it does not recognise has a green verdict that means nothing. Coverage is inverted, not enumerated: the scan walks the whole base, and this engine grows by adding top-level regions |

IMMUTABLE by rule: `_sources/`, manifests (they carry their own checksums), append-only logs, lens outputs, the resolved-clarification archive, and **the body of any record**. Rewritten history is not migration.

Residue is the sum of four things, not one: live surfaces still naming the retired identifier, unclassified paths, malformed registry rows, and orphan namespaced tags. A per-identity run (`--identity`) drops the last three — coverage gaps, unreadable rows and orphans belong to the base as a whole, and letting them fail one identity's gate is the confusion the filter exists to remove.

**Orphan namespaced tag** — a tag `{namespace}/{id}` whose namespace a registry claims and whose identifier that registry does not declare, live or retired. It is the one defect this contract cannot reach by its own method: every check above reasons *outward from a declared identity*, so an identifier that was never declared has nothing to reason from and is examined by nothing. Only namespaces a registry claims are judged — `topic/`, `domain/`, `type/` and the rest declare no identity — and each namespace belongs to exactly one registry, a collision being a defect of the declarations rather than something to resolve by picking one. Resolution is never automatic: registering the identity, retagging the note and dropping the tag are three different decisions and only the owner can tell which applies. The orphans a base already carries are listed in `_system/state/identity-orphan-baseline.txt`, a closed list that only shrinks — a new orphan is residue from the moment it appears.

The class is decided by what the content *is*, not by which folder holds it, and the line runs inside a record file: its body is a historical artifact and is never rewritten, while its frontmatter is engine-managed classification and migrates like any other live surface. A record whose frontmatter still names a retired identity is residue; a record whose prose mentions it is history.

### Obligations

1. **Atomic.** Every live surface migrates in the same unit of work as the decision. No two-stage identity change.
2. **Zero residue.** Afterwards a scan for the retired identifier across live surfaces returns nothing — proven by running the scan, not asserted by the writer.
3. **Well-formed.** A retirement row that breaks the successor rule of its own kind is a defect **of the row**, reported against the registry row rather than against the surfaces that refer to it. A malformed row blocks every automatic rewrite for that identity: there is no deterministic target to write.
4. **Proven per identity.** The proof is a run of the residue scan **filtered to the identity being changed**, and its exit code is recorded with the resolution. A whole-base scan proves nothing about one change — another identity's residue must never fail this change, and must never be repaired by undoing it.

### Successor integrity

A declared successor is an identifier of the **same registry**, present in it, and **live at the moment the retirement is written** — never one that is itself retired or void. This forbids aiming a new retirement at the dead, and it is why a cycle cannot be created through the write path at all; a cycle found in the registry got there by hand.

It does not abolish chains: an identifier retired into a live successor that is itself retired later is ordinary and expected. **A reader therefore resolves transitively to the terminal live successor** and rewrites to that one. A resolution that does not terminate — a cycle, or a chain ending in void, in a foreign registry, or in an identifier the registry does not hold — yields no target: it is a defect of the rows on the chain, reported and never guessed around.

### Canonical node

Resolution order by role: canonical hub → node card → node container README. First found wins; every other node of the same identity declares itself derived, otherwise one identifier carries several self-proclaimed sources of truth. A retired identity resolves to the node of its terminal live successor.

### References with no single target

Two kinds leave references without one identifier to migrate to, and they resolve oppositely.

- **void** — the identity never existed, so its references are frozen where they stand and excluded from the residue check.
- **split** — the identity became several, and which successor a given reference means is decided by what that reference says, not by anything the registry holds. References neither freeze nor migrate: every live surface of a split identity surfaces as an owner decision among the declared successors, and residue is cleared one surface at a time by that decision. The completion rule is unchanged — zero live residue — only the route to it is manual.

**Enforcement.** Write path: `/minder:mem:resolve-clarifications` Class I, the declared writer of both registries' retirement sections — it refuses a row its kind's successor rule forbids, and finalises only against a clean per-identity scan. Read path: `_system/scripts/identity_audit.py`, run nightly by `/minder:mem:lint` A.8, which recomputes residue from the base itself and re-raises whatever a write path let through.

---

## Concepts (concepts:)

Open-vocabulary semantic anchors — every "thing-in-the-world" the
knowledge base tracks. Format and rules: `_system/registries/CONCEPT_NAMING.md`.

- **Field on:** records (meeting + observation), knowledge notes,
  project profiles. NOT on hubs (hubs carry `member_concepts[]` only
  in the manifest, derived from members) and NOT on person profiles
  (people are first-class entities; their identifier is `firstname-lastname`).
- **Format:** snake_case ASCII `[a-z0-9_]`, length 1–64, no forbidden
  type prefix, English-only (translate non-English source terms; never
  transliterate).
- **Type lives in metadata, not in name.** The enum lives in manifest
  `concepts.upserts[].type`; `manifest-schema/v2.json` holds the canonical
  list — `theme`/`tool`/`decision`/`idea`/`event`/`organization`/`skill`/
  `technical`/`location`/`emotion`/`goal`/`value`/`preference`/`constraint`/
  `algorithm`/`fact`/`other`. `person` and `project` are reserved in the
  vocabulary and never emitted by Minder Memory.
- **Autonomous resolution.** Engine resolves every format issue via
  `_system/scripts/_common.py::normalize_concept_name()`; never raises
  CLARIFICATIONs (see ENGINE_DOCTRINE §3.1 layer-specific exception).

## Privacy Trio (origin / audience_tags / is_sensitive)

Three orthogonal slots on every entity per ENGINE_DOCTRINE §3.8.
Spec: `_system/registries/AUDIENCES.md` for `audience_tags`.

| Field | Type | Default | Spec |
|---|---|---|---|
| `origin` | enum `personal \| work \| external` | path-derived (see Lint Step 1.D); else `personal` | Source provenance — does NOT determine sharing scope |
| `audience_tags` | `text[]` | `[]` (owner-only) | Whitelist: canonical 5 (`family`/`friends`/`work`/`professional-network`/`world`) ∪ active extensions in AUDIENCES.md |
| `is_sensitive` | bool | `false` | Friction modifier on share — orthogonal to audience |

- **On records, knowledge notes, hubs, person profiles, project
  profiles, principles, every Tier 1/2 typed object.**
- **Hub auto-derivation:** `recompute_hub_trio()` fills MISSING fields
  from members (dominant origin / audience intersection / sensitivity
  contagion); never overwrites owner-set values.
- **Lint Step 1.D backfill** fills missing trio on existing entities
  (one-time migration on first lint run after the engine adopts the
  trio). `origin` derives from path:
  `_records/meetings/*` and `2_areas/work/*` → `work`; everything else
  → `personal`. `audience_tags` defaults to `[]` (sharing intent is
  owner-curated, never auto-assigned). `is_sensitive` defaults to
  `false` (content-driven, owner refines).

## Content Potential Fields

Three optional fields set together when a note has public sharing value.
Omit all three if note is purely operational, private, or context-free.

### content_potential: high|medium

| Value | When to set |
|-------|------------|
| high | Personal experience illustrating professional principle; specific technical insight/decision; industry opinion; career/leadership reflection; original business/product angle; useful workflow/process; personal reflection with universal resonance |
| medium | Interesting kernel not fully developed; public topic but private context needs rework; fragment that could combine with other notes into a post |
| (omit) | Purely operational, private, or context-free content |

### content_type: expert|reflection|story|insight|observation

| Type | What it is |
|------|-----------|
| expert | Professional/technical knowledge, architectural decisions, domain expertise |
| reflection | Personal introspection, psychology, self-analysis, therapy insights |
| story | Narrative arc — career journey, personal experience, life event |
| insight | Non-obvious connection, counter-intuitive observation, pattern recognition |
| observation | Lightweight seed thought, casual noticing, not yet developed |

Closed set — `/minder:mem:process` emits exactly one of these five; lint Scan A.11 heals
any drift (`CANON_MAP` in `lint_content_markup.py`).

### content_angle: ALWAYS a YAML list of strings

Each angle is one sentence — the "why would someone read this?" framing.
Written in the owner's language (the draft is conceptual; platform/translation
are publish-time choices).

**Always a list** (single angle = 1-element list) — uniform shape so consumers
never branch on string-vs-list. Lint Scan A.11 normalizes a stray bare string
(`content-angle-format` autofix).

```yaml
# Single angle (most notes) — still a list
content_angle:
  - "Why delegation is hard for tech leads"

# Multiple angles (each becomes a distinct post candidate)
content_angle:
  - "Childhood perfectionism → adult control patterns"
  - "Why delegation is hard for tech leads — it's not about trust"
```

**content_type drift → canonical mapping.** The non-canonical values producers
sometimes emit (technical, idea, decision, …) are mapped to the canonical five by
lint Scan A.11. The mapping table is owned in one place —
`_system/scripts/lint_content_markup.py::CANON_MAP` (synonym rows autofix; judgment
rows surface as CLARIFICATIONs). See `/minder:mem:lint` SKILL Scan A.11 for the method.

---

## Folder Routing Logic

Правила маршрутизации заметки в папку живут в реестре папок —
`_system/registries/FOLDERS.md → ## Routing Rules`. Он владеет порядком
разрешения (layer → project → types → domains) и всеми таблицами. Читай их
там. Без них заметка знаний не пишется — `/minder:mem:process`, Шаг 1, пункт 16.

---

## Processing Workflow (/minder:mem:process)

Pipeline обработки определён в SKILL.md (`/minder:mem:process`).

Краткая последовательность:
0. Pre-Scan — People Resolution Map (three-tier: RESOLVED / NEW / AMBIGUOUS), hub signal matching
1. Load Context — SYSTEM_CONFIG, PROCESSING_PRINCIPLES, registries, hubs, CLARIFICATIONS
2. Find New Files — scan `_sources/inbox/`, sort chronologically, move to `_sources/processed/`
3. **Process Files (per-batch full-pipeline subagents)** —
   Orchestrator partitions chronologically-sorted file list into batches
   (T = 250k input tokens, N = 6 transcripts max per batch, max 3 parallel
   subagents). Each subagent runs 3.1–3.7 for every transcript in its
   batch in shared context, returns manifest with notes + coverage data.
   - 3.1 Read transcript (two formats: with/without summary) — *in subagent*
   - 3.2 LLM Noise Gate (genuine vs noise, inclusion-biased) — *in subagent*
   - 3.3 Semantic Context Loading (resolve people, load hubs from briefing) — *in subagent*
   - 3.4 LLM Classification (14 questions) — *in subagent*
   - 3.5 Create Outputs (records, knowledge notes, hub updates/creates, cross-domain) — *in subagent*
   - 3.6 Structural Verification — *in subagent*
   - 3.7 **Self-Review** — producer-side coverage manifest (PEOPLE / TOPICS / DECISIONS / ACTIONS) reconciled against produced notes, fixes applied in place — *in subagent*
   - 3.7.5 Constitution Alignment Check — *in orchestrator, post-aggregate*
   - 3.8 People Profiles (create/update, CLARIFICATIONS for uncertain) — *in orchestrator, post-aggregate*
   - 3.9 System updates (PROCESSED, LOG) — *in orchestrator*
   - 3.10 Verify source integrity (file completeness invariant: union of subagent-processed paths = enumerated source set) — *in orchestrator*
4. Post-Processing — TASKS, CALENDAR, HUB_INDEX, content potential verification, batch verification
5. Completion Gate — mandatory checklist, halt-on-error, no deferring
6. Report — summary with coverage fix rate and clarifications

Принципы обработки: `5_meta/PROCESSING_PRINCIPLES.md`
Архитектура: `5_meta/CONCEPT.md`

---

## Entity Matching

Birth of an identity — how an identifier comes into existence. What happens to it afterwards is `## Identity Contract` above.

### Before creating any new entity:

```
1. Normalize name (lowercase, dashes, transliterate if needed)
2. Search in registry:
   - Exact match
   - Fuzzy match (similar names)
3. If found → use existing
4. If not found → create new → add to registry
```

### Name normalization:
- "Иван Петров" → "ivan-petrov"
- "Acme Payments" → "acme-payments"
- "Learning Goal" → "learning-goal"
- "AI Agents" → "ai-agents"

---

## People Profiles

When a person is mentioned:

1. Check PEOPLE.md registry
2. If exists → add mention link to their profile
3. If not exists:
   - Create profile in 3_resources/people/{id}.md
   - Add to PEOPLE.md registry

### Profile format:
```markdown
---
id: ivan-petrov
name: "Иван Петров"
role: CEO
org: acme
tags:
  - person/ivan-petrov
  - org/acme
  - role/ceo
---

# Иван Петров

**Role:** CEO @ Acme

## Контекст
[Описание роли и отношений]

## Упоминания
- [[20260125-meeting-ivan-petrov|Встреча 25 января]] — example link
```

---

## Task Format

### Inline в заметках (source)

```markdown
- [ ] Описание задачи → [[связь]] ^task-unique-id
- [x] Завершённая задача ✅ YYYY-MM-DD ^task-id
```

Task IDs: уникальные в рамках файла, формат `^task-short-description`.
Примеры: `^task-write-letter-ivan-petrov`, `^task-prepare-presentation`.

### Aggregate в TASKS.md (maintained by /minder:mem:process — incremental merge + reconciler backstop)

**Структура (6 секций):**

1. **Action — я делаю** — owner is the executor
2. **Waiting — жду от других** — другой человек должен прислать/дать результат owner'у
3. **Delegate — контролирую выполнение** — owner назначил/эскалировал, отслеживает
4. **Someday** — низкий приоритет / идеи на будущее
5. **Personal** — не связано с работой
6. **Stale** — кандидаты на удаление (устарели, поглощены, потерян контекст)

Внутри каждой секции — группировка по **потоку** (`### Stream Name`).
Потоки органические: создавай по мере появления кластеров задач —
кластеризация по теме / проекту / области ответственности; имена потоков
определяются органически из контента, а не предзаданы.

**Форматы по типу:**
```markdown
# Action:
- [ ] Description — [[note-link]] ^task-id

# Waiting:
- [ ] **@person-id** What I'm waiting for — deadline — [[note-link]] ^task-id

# Delegate:
- [ ] **@person-id** What they're doing — deadline — [[note-link]] ^task-id
```

**Правила классификации (Action / Waiting / Delegate):**

Owner-first-name = first name from SOUL.md `## Identity` `Name:` line. Skill resolves it at runtime.

| Признак | Тип |
|---------|-----|
| Источник: «{owner-first-name}: ...» / first-person speech (`I:` / `я:`) / задача явно для исполнения owner'ом | Action |
| Источник: «@person: ...» и owner — получатель результата (ответ, документ, данные) | Waiting |
| Owner поставил задачу / эскалировал / ведёт как owner-of-tracking, output нужен команде/процессу, не лично owner'у | Delegate |
| Не ясно кто исполнитель | Action (безопасный дефолт) |

**Практический маркер Waiting vs Delegate:**
- Waiting = «owner не может двигаться, пока X не ответит» (блокер для owner'а)
- Delegate = «X работает над задачей, owner следит за прогрессом» (owner как менеджер)

**Stale preservation (важно):**
При регенерации TASKS.md **секция Stale сохраняется** — прочитай текущий файл,
извлеки task-id из секции Stale, при записи новой версии положи их обратно в Stale
(не возвращай в активные секции, даже если в source note всё ещё `- [ ]`).
Stale — это результат ручного ревью пользователя, машина его не переопределяет.

**Шапка TASKS.md (обновляется каждую регенерацию):**
```markdown
**Last Updated:** YYYY-MM-DD
**Open:** N action / N waiting / N delegated / N someday / N personal
**Stale candidates:** N
**Total unique:** N
```

---

## Event/Meeting Format

### Inline в заметках (source)

```markdown
- 📅 **YYYY-MM-DD HH:MM** — Описание события ^meeting-id
```

### Aggregate в CALENDAR.md (maintained by /minder:mem:process — incremental merge; best-effort reconciler)

**Структура (4 секции):**

1. **Recurring** — регулярные встречи (маркер 🔄)
2. **Upcoming** — будущие одноразовые события owner'а (маркер 📅)
3. **Deadlines** — чужие дедлайны которые owner отслеживает (маркер ⏰, префикс `**@person**`)
4. **Past** — **только последние 2 недели**; более старые удаляются при регенерации

**Форматы:**
```markdown
# Recurring:
- 🔄 **День недели ЧЧ:ММ МСК** — Описание — [[note-link]]

# Upcoming:
- 📅 **YYYY-MM-DD** — Описание события — [[note-link]]

# Deadlines:
- ⏰ **YYYY-MM-DD** — **@person-id**: что они должны сделать — [[note-link]]

# Past:
- 📅 **YYYY-MM-DD** — Описание — [[note-link]]
```

---

## Language Rules

1. **Tags, types, IDs** → English
2. **Note content (title, text)** → Same language as source
3. **Folder names** → English
4. **Frontmatter keys** → English

---

## Quality Checklist

Before saving each note:
- [ ] ID matches filename
- [ ] All mentioned people exist in registry
- [ ] All mentioned projects exist in registry
- [ ] Tags follow naming convention
- [ ] Source section links to raw transcript in `_sources/processed/`
- [ ] Links use [[wikilink]] format
- [ ] Tasks have unique ^task-id
- [ ] Contains section exists if note has tasks/ideas/meetings (optional otherwise)

---

## Files Reference

| File | Purpose | Updated |
|------|---------|---------|
| _system/docs/SYSTEM_CONFIG.md | This file — runtime config (formats, types) | Manual |
| _system/SOUL.md | Identity + Focus + Working Style | Manual + /minder:mem:bootstrap (once) |
| _system/state/OPEN_THREADS.md | Active open threads + resolved history | /minder:mem:bootstrap, /minder:mem:maintain, /minder:mem:resolve-clarifications (writers per Skill Write Territory) |
| _system/views/CURRENT_CONTEXT.md | Live state snapshot for thin orientation | /minder:mem:bootstrap, /minder:mem:maintain |
| _system/views/INDEX.md | Surface catalog of knowledge + archive + constitution + hubs (PARA / domains / cross-domain / hubs facets); records and posts intentionally out of scope | /minder:mem:bootstrap Step 5.5, /minder:mem:maintain Step 7.6, regen_all.py — all via `_system/scripts/render_index.py` |
| _system/state/log_lint.md | Append-only log of /minder:mem:lint runs | Each /minder:mem:lint |
| `.engine-migrations.jsonl` (repo root) | Append-only migration ledger — one line per attempt: name, declared kind, exit code, outcome (`applied` / `partial`), timestamp, note. A clone carrying the older flat `.engine-migrations-applied` has it folded in on read. Committed, so a second machine agrees on what has run | `scripts/run_migrations.py`, called by `/minder:mem:update` and `scripts/sync_engine.sh` |
| _system/state/log_maintenance.md | Append-only log of /minder:mem:maintain + /minder:mem:bootstrap runs | Each /minder:mem:maintain / /minder:mem:bootstrap |
| _system/state/log_process.md | Chronological log of /minder:mem:process operations | Each /minder:mem:process |
| _system/state/log_agent_lens.md | Append-only log of /minder:mem:agent-lens runs | Each /minder:mem:agent-lens |
| _system/state/agent-lens-runs.jsonl | Machine index of every agent-lens run (one JSON line per run) | Each /minder:mem:agent-lens |
| _system/state/tick-telemetry.jsonl | Append-only token-consumption record, one JSON line per scheduler tick: totals (input / output / thinking / cache write split by 1h and 5m TTL / cache read / server-tool calls), per-model message counts, and a `by_agent` breakdown that names each role by its own id and carries that agent's own model tally — a roles tick can put each role on a different model, and the tick-level tally cannot say which one was where. Read from the tick's own transcript at Step 4.9, never self-reported by the model — a model cannot see its own usage. `measured_through` marks the horizon past which the tick's closing messages are uncounted; `layout_check` records whether sub-agent transcripts were where the parser expected them. | Each scheduler tick |
| _system/state/check-decision-runs.jsonl | Append-only audit substrate of `/minder:mem:check-decision` invocations. Two `kind`'s per line — `run` (mechanical fields always; optional self-report `intent` / `pre_confidence` / `expected_verdict` when caller supplies) and `followup` (post-action signal). Sensitive runs omit `situation_text` + `rationale`, keep `situation_hash`. Consumers: `decision-review` lens (Layer A enrichment via `record_ref` exact match; Layer B aggregate observations on rolling 30-day window). Schema is forward-additive — unknown fields treated as no-signal by consumers, never fail. Substrate is never compacted / aggregated; rotation by year only when volume warrants. | Each /minder:mem:check-decision (run + optional followup) |
| _system/state/.check-decision-runs.lock | Advisory `flock` serialising telemetry emission (run + followup) from concurrent /minder:mem:check-decision invocations. Narrow scope — does NOT cover Evidence Trail edits to `0_constitution/` (existing pre-emission race surface, out of telemetry scope). | /minder:mem:check-decision (helper acquires + releases) |
| _system/state/agent-lens-rejected/{lens}/{ts}.md | Raw Stage 2 outputs that failed structural validator | On validator rejection |
| _system/agent-lens/{lens}/{date}.md | Structured agent-lens observation outputs | Each successful /minder:mem:agent-lens lens run |
| _system/registries/AGENT_LENSES.md | Agent-lens registry (active/draft/paused, cadence, schema) | /minder:mem:agent-lens-add (table row append on creation) + Manual (owner edits) + /minder:mem:agent-lens (status updates only on auto-pause) |
| _system/registries/lenses/{id}/prompt.md | Per-lens prompt + frontmatter | /minder:mem:agent-lens-add (creates new lens) + Manual (owner edits) |
| _system/registries/lenses/_frame.md | Two-stage frame (thinker + structurer) + validator rules | Manual (engine-shipped) |
| _system/state/lint-context/daily/*.md | 30-day rolling daily summaries | Each /minder:mem:lint |
| _system/state/lint-context/monthly/*.md | Append-forever monthly summaries | First /minder:mem:lint of new UTC month |
| _system/state/BATCH_LOG.md | Append-only index of batch operations | Each /minder:mem:process |
| _system/state/batches/{batch-id}-{skill}.md + .json | Full batch report + JSON manifest, one pair per emitting run | Each /minder:mem:process, /minder:mem:maintain, /minder:mem:lint, /minder:mem:agent-lens |
| _system/docs/batch-format.md | Batch format contract — markdown report + JSON manifest; per-entity privacy trio + concept fields; sections `## Concepts Upserted` + `## Sensitive Entities` | Manual (bump version on change) |
| _system/state/PROCESSED.md | Source → Note mapping | Each /minder:mem:process |
| _system/TASKS.md | All open tasks | Regenerated |
| _system/CALENDAR.md | All events | Regenerated |
| _system/POSTS.md | Published posts archive + content strategy | Manual or /minder:mem:content |
| _system/views/CONTENT_MAP.md | Content pipeline interface — compact view over hubs + content notes + POSTS.md (ripeness, posts-on-theme) | /minder:mem:maintain Step 7.8 (canonical writer; regenerable, read-only) |
| 5_meta/mocs/hub-cognitive-model.md | Cognitive-model hub — per-axis projection of `cognitive_axes`-tagged principles + candidate buffer (axis set is the SoT in `lenses/cognitive-model/prompt.md`); AUTO-GENERATED zone between markers, owner «portrait» above | /minder:mem:maintain Step 7.9 via `render_cognitive_model_hub.py` (owner-data; managed zone regenerable) |
| _system/state/content-pipeline-state.json | Content ledger — per-draft state (theme_ids[], ripeness, draft_status, owner_touched) | /minder:mem:content --maintain (NOT regenerable) |
| _system/state/CLARIFICATIONS.md | Non-blocking human-in-the-loop questions | All skills (safety valve) |
| _system/registries/TAGS.md | Tag registry (`tags:` namespace labels) — census of the `tags:` frontmatter across the knowledge layer; AUTO-GENERATED zone between markers, owner-curated preamble above and `## Notes` below | `render_tags.py` only (via `/minder:mem:maintain` Step 7.10 and `regen_all.py`; managed zone regenerable, read-only) |
| _system/registries/CONCEPT_NAMING.md | Spec — canonical concept-name format (engine-shipped) | Manual (engine maintainer) |
| _system/registries/AUDIENCES.md | Spec + extensions for `audience_tags` privacy labels | /minder:mem:resolve-clarifications (extension append on owner approval) + Manual (owner edits) |
| 1_projects/PROJECTS.md | Project registry | When new projects |
| 3_resources/people/PEOPLE.md | People registry | When new people |
| _system/registries/FOLDERS.md | Folder structure | Rarely |
| _system/views/HUB_INDEX.md | Index of all hub notes | /minder:mem:maintain (rebuild) + /minder:mem:process (additive on hub create) — writers per Skill Write Territory |
| 5_meta/CONCEPT.md | Architecture, philosophy, ADRs (human reference) | Manual |
| 5_meta/PROCESSING_PRINCIPLES.md | 8 principles + values profile (LLM guidance) | Manual |
