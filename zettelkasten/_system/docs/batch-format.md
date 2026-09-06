---
id: batch-format
layer: system
version: 2.2
modified: 2026-05-04
---

# Batch Format

> Контракт формата batch-отчётов Minder Memory engine. Two artefacts per batch
> live side by side under `_system/state/batches/`:
>
> - **`{batch_id}-{skill}.json`** — machine-parseable manifest. **The
>   canonical contract** consumed by every downstream process. Schema
>   lives at `_system/docs/manifest-schema/v{N}.json`; reference doc
>   at `_system/docs/manifest-schema/README.md`. This file does NOT
>   re-document the JSON manifest field-by-field — read the JSON
>   Schema for that. Anything below this line covers only the
>   markdown summary.
> - **`{batch_id}-{skill}.md`** — human-narrative summary. Owner
>   reading + lint scanning surface; not a contract for any external
>   consumer. The contents below are about this file only.
>
> Изменение формата markdown summary = bump `version:` во frontmatter
> + добавление row в Version History. Изменение формата JSON manifest
> = SemVer bump в `manifest-schema/v{N}.json` per
> `manifest-schema/README.md` evolution rules.

---

## Version History

- **v2.2**: extracted JSON manifest contract into
  `_system/docs/manifest-schema/v2.json` + `README.md` (consumer-
  agnostic); clarified that this file documents only the markdown
  summary, not the JSON manifest. No content change to either
  artefact at runtime.
- **v2.1**: added ARCH-B hub-state fields per hub entry —
  `hub_kind` (project / trajectory / domain), `chronological_map_mode`
  (derived / curated), `excluded_from_map_count`, and `auto_member_count`.
  Additive minor — pre-2.1 consumers ignore unknown fields via
  `section_extras` pattern. No breaking change.
- **v2.0**: added concept emission (`concepts:` frontmatter,
  `concept_hints[]` per-entity, `member_concepts[]` per-hub,
  `concepts.upserts[]` registry-level) and privacy trio (`origin`,
  `audience_tags`, `is_sensitive`) per-entity. Markdown report sections
  unchanged; JSON manifest gains `concepts` top-level section + privacy
  fields on every entity. Format-version flips to `2.0` in frontmatter.

---

## File Locations

- **Index:** `_system/state/BATCH_LOG.md` — append-only markdown table, one row per `/minder:mem:process` batch
- **Reports:** `_system/state/batches/{batch-id}-{skill}.md` — one file per batch, full structured report
- **Manifests:** `_system/state/batches/{batch-id}-{skill}.json` — machine contract; schema in `_system/docs/manifest-schema/v{N}.json`

---

## batch-id Format

```
YYYYMMDD-HHmmss
```

- UTC timestamp начала обработки
- Уникален, монотонно возрастает
- Сортируется корректно как строка

**Пример:** `20260416-103000`

---

## BATCH_LOG.md Schema

Одна строка markdown-таблицы на каждый `/minder:mem:process` batch.
Append-only, не перезаписывается.

| Column | Type | Description |
|---|---|---|
| `batch_id` | string | `YYYYMMDD-HHmmss` (UTC) |
| `timestamp` | ISO 8601 | начало обработки (UTC, с суффиксом `Z`) |
| `sources` | int | сколько файлов из inbox обработано в этом batch |
| `records` | int | создано записей в `_records/{meetings,observations}/` (обоих kind'ов суммарно) |
| `notes` | int | создано knowledge notes в PARA (`1_projects/` … `4_archive/`) |
| `tasks` | int | извлечено задач (inline `^task-*` в нотах) |
| `events` | int | извлечено событий (inline 📅) |
| `threads_open` | int | новых open threads за batch |
| `threads_close` | int | переведено в resolved за batch |

---

## batches/{batch-id}-{skill}.md Schema (markdown summary, owner-narrative)

### Frontmatter (required)

```yaml
---
batch_id: YYYYMMDD-HHmmss
timestamp: YYYY-MM-DDTHH:MM:SSZ
processor: minder:mem:process v{version}
format_version: 2.0
sources: N
records: N
notes: N
tasks: N
events: N
threads_opened: N
threads_resolved: N
clarifications_raised: N
people_candidates_appended: N
concepts_upserted: N        # count of distinct concepts in concepts.upserts[]
sensitive_entities: N       # count of entities with is_sensitive=true
---
```

`format_version` value mirrors the JSON manifest's top-level
`format_version`. Same SemVer evolution rules — see
`manifest-schema/README.md`.

### Sections (in order)

1. `## Sources Processed`
2. `## Records Created`
3. `## Knowledge Notes Created`
4. `## Tasks Extracted`
5. `## Events Extracted`
6. `## People Updates`
7. `## Threads` → `### Opened` + `### Resolved`
8. `## Hubs Updated`
9. `## CLARIFICATIONS Raised`
10. `## People Candidates Appended` (added 2026-04-24) — per entry: `{candidate_id} | {name_as_transcribed} | {note-id} | {role_hint or —}`. Count MUST equal `people_candidates_appended` in frontmatter. Use `(none)` if empty. Rationale: bare-name mentions routed to `_system/state/people-candidates.jsonl` instead of CLARIFICATIONS — see `/minder:mem:process` Step 3.8 + `/minder:mem:lint` Scan C.5.
11. `## Concepts Upserted` — per entry: `{name} | {type} | {subtype or —} | {related_concepts comma-list or —}`. Count MUST equal `concepts_upserted` in frontmatter. Use `(none)` if empty. Mirrors the JSON manifest's `concepts.upserts[]`. Names conform to `_system/registries/CONCEPT_NAMING.md` (snake_case ASCII, English-only, no type prefix in name).
12. `## Sensitive Entities` — per entry: `{path or id} | {kind: record|note|hub|task|...} | audience_tags: {[...] or "[]"}`. Count MUST equal `sensitive_entities` in frontmatter. Use `(none)` if empty. Lists every entity emitted in this batch with `is_sensitive: true` so downstream sync can apply extra-friction handling without re-scanning frontmatter.

Пустые секции сохраняются с пометкой `(none)` — удобнее для diff и downstream consumer.

---

## Example Batch Report (markdown summary)

```markdown
---
batch_id: 20260416-103000
timestamp: 2026-04-16T10:30:00Z
processor: minder:mem:process
format_version: 2.0
sources: 1
records: 1
notes: 2
tasks: 2
events: 1
threads_opened: 1
threads_resolved: 0
clarifications_raised: 0
people_candidates_appended: 0
concepts_upserted: 2
sensitive_entities: 0
---

## Sources Processed
- _sources/inbox/plaud/2026-04-16T10-15-00/transcript_with_summary.md (plaud)

## Records Created
- [[20260416-meeting-petya-strategy]] | Встреча с Петей: стратегия инвестиций
  - People: petya-ivanov
  - Projects: —

## Knowledge Notes Created
- [[20260416-investment-approach]] | Подход к инвестиционной стратегии
  - Types: insight | Domains: work
  - Evidence Trail: started

## Tasks Extracted
- task-20260416-001 | Позвонить Пете до пятницы | deadline: 2026-04-18 | priority: high
  - From: [[20260416-meeting-petya-strategy]]

## Events Extracted
- 2026-04-18T14:00:00+04:00 | Follow-up с Петей | participants: petya-ivanov
  - From: [[20260416-meeting-petya-strategy]]

## People Updates
- petya-ivanov | new_context | mentions: 4→5 | tier: 2 (no change)

## Threads

### Opened
- thread-20260416-investment-proposal | Ожидаем proposal от Пети | status: waiting-for-response

### Resolved
(none)

## Hubs Updated
- [[hub-investment-strategy]]

## CLARIFICATIONS Raised
(none)

## Concepts Upserted
- investment_approach | theme | — | risk_tolerance, portfolio_strategy
- portfolio_strategy | theme | — | investment_approach

## Sensitive Entities
(none)
```

---

## Per-Entity Fields — Concepts and Privacy Trio (markdown narrative side)

Every entity surfaced in the markdown summary mirrors the manifest's
**privacy trio**:

| Field | Type | Default | Source of values |
|---|---|---|---|
| `origin` | enum | `personal` | `personal` / `work` / `external` (plus `bootstrap-*`/`sync-*` synthetic origins). Inferred per `/minder:mem:process` Step 3.4 Q16 from SOURCE TYPE + content signals. |
| `audience_tags` | `text[]` | `[]` | Whitelist in `_system/registries/AUDIENCES.md` (canonical 5 + Extensions). Empty = owner-only. |
| `is_sensitive` | bool | `false` | Set `true` on NDA, salary, health, financial detail, intimate disclosure. Friction-modifier, NOT audience narrower. |

The trio is **slot-only** at this layer: Minder Memory emits values, downstream
consumers (Minder backend, sync targets, custom forks) apply policy.
Defaults are chosen so that absence of inference fails closed
(private, not leaked).

Concept fields per entity:

| Field | Where | Purpose |
|---|---|---|
| `concepts:` | frontmatter on records and knowledge notes | Canonical concept-name list ("what things does this entity touch"); list of strings per CONCEPT_NAMING. |
| `concept_hints[]` | per-record / per-note section in JSON manifest | Mirror of frontmatter `concepts:` for downstream consumption. Same values; "hint" name preserves the upstream-tentative semantics. |
| `member_concepts[]` | per-hub section in JSON manifest | Union of concepts from hub's member knowledge notes. Aggregated at manifest emission time; not stored in hub frontmatter. |
| `applies_in_concepts[]` | per-principle section in JSON manifest | Concepts a principle applies to. Sourced from constitution principle frontmatter (`/minder:mem:regen-constitution` reads). |
| `concepts.upserts[]` | top-level JSON manifest section | Registry-level deduplicated concept emission for the batch. Each entry: `{name, type, subtype?, related_concepts[]?, previous_slugs[]?}`. Where the same concept appeared in N entities, ONE upsert entry is emitted with consolidated metadata. |

**Concept scope.** `/minder:mem:process` emits non-person, non-project concepts.
People are tracked via `tier1_objects.people` and `people:` frontmatter;
projects via `tier1_objects.projects` and `projects:` frontmatter. The
`type` enum in `CONCEPT_NAMING.md` includes `person` and `project` for
downstream graph completeness, but Minder Memory-side emission deliberately
excludes them to avoid dual-emit ambiguity. Downstream consumers infer
person↔concept and project↔concept edges from co-occurrence in the
manifest.

**Concept-name format.** All concept-name strings (frontmatter values,
`concept_hints[]`, `member_concepts[]`, `applies_in_concepts[]`,
`concepts.upserts[].name`, `subtype`, every entry in `related_concepts`,
every entry in `previous_slugs`) MUST conform to
`_system/registries/CONCEPT_NAMING.md` — snake_case `[a-z0-9_]`, ≤64
chars, no type prefix in the name, English-only. The "no type prefix"
rule is enforced **upstream at extraction** (`/minder:mem:process`), not by a
mechanical strip — the normaliser keeps names verbatim because a blind
strip cannot tell a redundant label from a compound (`decision_making`)
and would corrupt identity. Non-English source terms MUST be translated
upstream (in `/minder:mem:process` Step 3.4 Q15) BEFORE emission. Mechanical
non-conformance (case / separators / diacritics / over-length, and
non-ASCII or bare-type-word drops) is silently autofixed or dropped by
the autonomous-resolution helpers in `_system/scripts/_common.py` — at
producer side (`emit_batch_manifest.py`) and again at lint Scan A.7
(`lint_concept_audit.py`) as defence-in-depth. The owner sees no queue;
see `_system/registries/CONCEPT_NAMING.md` "On violation" for the full
action table.

**Audience-tag format.** All `audience_tags[]` values MUST be either one
of the canonical five (`family`, `friends`, `work`,
`professional-network`, `world`) or appear in the Extensions table of
`_system/registries/AUDIENCES.md`. Unknown / non-conformant values are
**silently dropped** by the autonomous pipeline (the engine never coins
new extensions); the entity falls back to its remaining accept-set
audiences, or to `[]` if all entries dropped. Lint Scan A.7 applies the
same drop-or-normalise rule against Minder Memory-internal manifest files as a
post-write safety net.

**Autonomous resolution — no CLARIFICATIONs for the concept layer.**
The concept and audience layers are 100% autonomous: every format issue
(non-snake_case concept name, over-length name, non-canonical audience
tag, reserved-keyword conflict) is resolved
deterministically by `_system/scripts/_common.py` helpers
(`normalize_concept_name`, `normalize_concept_list`,
`normalize_audience_tag`). On unresolvable input (non-ASCII residue,
bare reserved type-word, audience tag not in whitelist that cannot be
mapped to canonical) the helpers return `None` and callers drop the
entry silently. The owner sees no CLARIFICATION queue for these issues —
heuristic resolution is the contract. Violations that DO surface
(format issues persisting after autofix at write-time, e.g. due to a
helper bug) are caught by lint A.7's defence-in-depth pass and logged
under `concept-*-autofix` / `audience-tag-*-autofix` fix-ids in
`log_lint.md` for traceability.

**Owner-curated registries (privacy trio NOT applicable).** The
following files are owner-curated outside the `/minder:mem:process` pipeline
and intentionally do NOT carry the privacy trio (origin /
audience_tags / is_sensitive). Lint Scan A.7 explicitly skips them:

- `_system/SOUL.md` (identity, focus, values — owner's calibration
  layer; entire file is owner-only by definition)
- `_system/TASKS.md` (task aggregation — entire surface is owner-only
  operational state)
- `_system/CALENDAR.md` (calendar aggregation — same)
- `_system/POSTS.md` (publishing log — owner-controlled publication
  records; sharing decisions made at compose-time, not via trio)
- `_system/registries/{TAGS,SOURCES,PEOPLE,PROJECTS,AGENT_LENSES,
  CONCEPT_NAMING,AUDIENCES,DOMAINS}.md` (engine registries — meta-spec, not
  content)
- `_system/views/*.md` (auto-generated derived views — derive
  privacy from inputs at consumption time, do not store)
- `_sources/processed/**/*.md` (raw transcripts — pre-processing
  artefacts)
- `_system/state/log_*.md` (append-only audit logs)

---

## JSON manifest — pointer

The JSON manifest schema is **canonical** in
`_system/docs/manifest-schema/v{N}.json` (currently `v2.json`).
Documentation, version evolution rules, consumer integration patterns,
and the "what is NOT in the manifest" contract live in
`_system/docs/manifest-schema/README.md` — that doc is consumer-agnostic
and is the source of truth for any process consuming Minder Memory output.

This file no longer maintains a separate JSON sketch — the schema
file is itself the spec. Keeping a parallel narrative led to drift
(field names diverging, optional/required shifting). One spec, one
location.

---

## Consumers

Формат потребляют:

- **`/minder:mem:process`** (writer) — генерирует `batches/{id}-process.md` +
  `batches/{id}-process.json` + добавляет строку в `BATCH_LOG.md`
- **`/minder:mem:maintain`** (writer + reader) — читает последний batch для
  incremental обновлений (mention counts, thread detection,
  CURRENT_CONTEXT regen); пишет `batches/{id}-maintain.json`
- **`/minder:mem:lint`** (writer + reader) — сканирует `BATCH_LOG.md` для
  detect stale threads, Evidence Trail gaps, content pipeline candidates;
  пишет `batches/{id}-lint.json`; Scan G validates every recent JSON
  manifest against the active schema
- **`/minder:mem:agent-lens`** (writer) — пишет
  `batches/{id}-agent-lens.json` per universal manifest contract;
  audit trail остаётся в `_system/state/agent-lens-runs.jsonl`
- **Downstream consumers** (open set — Minder backend, custom forks,
  experimental tooling) — read manifests per
  `manifest-schema/README.md` integration patterns

При bump версии — migration path документируется здесь же (для
markdown summary) или в `manifest-schema/v{N}.json` history (для JSON
manifest).
