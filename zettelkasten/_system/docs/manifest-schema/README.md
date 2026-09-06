# Minder Memory engine output contract

`v2.json` (this directory) is the canonical **JSON Schema** that every
manifest written by a Minder Memory engine skill MUST validate against. Any
process that wants to consume Minder Memory output — Minder's ingest worker, a
fork running on someone's laptop, an experimental GraphRAG layer, a
notebook — reads this contract and nothing more.

This README is consumer-agnostic on purpose. Minder Memory is a standalone
engine; downstream is an open set.

---

## What is a manifest

After every persistent-state-changing run of `/minder:mem:process`,
`/minder:mem:maintain`, `/minder:mem:lint`, or `/minder:mem:agent-lens`, the engine writes
a single JSON file under `_system/state/batches/`:

```
_system/state/batches/{batch_id}-{skill}.json
```

`{batch_id}` is `YYYYMMDD-HHMMSS` UTC (sortable as string, monotone
non-decreasing per skill). `{skill}` is one of `process`, `maintain`,
`lint`, `agent-lens`. The same file is also written as a
human-narrative `{batch_id}-{skill}.md` next to it; the markdown is
informal and not part of the contract.

All four skills emit into one shape distinguished by the top-level
`processor` field. A consumer reads them uniformly.

---

## Schema location and version evolution

- **Active schema:** `v2.json` in this directory. `$id` =
  `urn:minder-memory:manifest-schema:v2.3` (URN — no URL resolution, no domain
  commitment, consumer-agnostic). Draft 2020-12.
- **Past schemas** stay in this directory unchanged
  (`v2.json` → `v2.1.json` → `v3.json` …). Old batches keep
  validating against the version they were emitted with.
- **Version pinning per batch:** every manifest carries
  `format_version: "MAJOR.MINOR"`. Consumers pick the matching schema
  file by major (and minor when relevant).

### Evolution rules (SemVer)

| Change kind | Bump | Behaviour |
|---|---|---|
| Add new optional field | MINOR | Consumers accept; missing → use defaults. |
| Add new manifest section | MINOR | Process if known; ignore if not. |
| Add new entity type to existing section | MINOR | Route to handler; warn if not registered. |
| Remove deprecated field | MAJOR | Consumer rejects with loud error. |
| Change field semantics | MAJOR | Consumer rejects; explicit migration shim. |
| Restructure section | MAJOR | Consumer rejects. |

**Forward-compat slot.** Every section accepts `section_extras: jsonb`
for fields not yet promoted to schema. A top-level `section_extras`
covers entirely new sections. Consumers log unknown contents but do
not fail. This is what lets the engine ship new fields without
coordinating a major bump.

### SemVer log

One of the two sanctioned exceptions to the «no version history in doc
bodies» rule (`CONVENTIONS.md`): the schema contract IS its version
log. Entries describe what changed and why, so a consumer can decide
whether to update.

| Version | Change | Rationale |
|---|---|---|
| 2.2 | Add `technical` to `concepts.upserts[].type` enum (additive). | Producer-emitted category observed in real batches (e.g. `20260514-103200-process`); owner-approved trade-off 2a in resolve-clarifications session 2026-05-18. |
| 2.3 | `processor` and `captured_by` name the product's namespace `minder:mem:<pipeline>`; the schema `$id` moves to `urn:minder-memory:…`. The former spelling is rejected; batches written before engine 1.0.0 validate after migration 032 has rewritten them. | Product rename (ADR-029). Not additive by the letter of the rules, shipped as MINOR because no consumer of the former spelling exists and the on-disk batches are rewritten in the same update. |

---

## Producer-side conformance — valid by construction

A manifest is **schema-valid by construction, or it is not written**. The
producer in `_system/scripts/emit_batch_manifest.py` applies two gates before
write:

1. **The normaliser** — absorbs every representational quirk the (LLM-driven)
   accumulator emits and coerces it to the shape `v2.json` expects.
2. **The deep gate** (`deep_validate_manifest`) — runs the *full* JSON-Schema
   validation (the same one the nightly lint runs) right after the
   normaliser. If anything still violates the schema — a shape the normaliser
   didn't cover — the producer **refuses to write and exits non-zero (rc=3)**
   with the exact errors, instead of emitting a manifest that only the nightly
   lint would catch days later.

So a normaliser gap surfaces *at emit time, loudly*, never as a silently
written bad batch. The schema (`v2.json`) stays strict — it is the consumer
contract; the normaliser absorbs the quirks so consumers never have to, and
the deep gate guarantees the normaliser actually succeeded.

What the normaliser guarantees on the way out:

- **Concept type is always in the enum.** Values are mapped via
  `LEGACY_CONCEPT_TYPE_ALIASES` to the closest canonical type; anything
  unmapped (or null / non-string) **fail-safes to `other`**, with the
  original kept under `section_extras.legacy_type`. The producer therefore
  cannot emit a non-enum concept type, whatever vocabulary the upstream
  accumulator invents.
- **Every list section is the object shape the schema expects.** Bare arrays
  become `{created, updated}` / `{upserts}`; bare-string record / note / hub /
  people entries become objects (paths derived by id convention); stringified
  arrays (`"[]"`, `"[a, b]"`) and plain scalars on array fields are parsed
  back into arrays.
- **The privacy trio** (`origin`, `audience_tags`, `is_sensitive`) is injected
  with conservative-safe defaults on every entity-list entry that lacks it.
- **Tier discipline.** Tier 1 types misrouted under `tier2_objects`
  (tasks / ideas / decisions / content) relocate to their tier1 home;
  genuine tier2 typed-objects (`{id, type, name}`) stay. Integer `tier`,
  legacy `hub_kind` (e.g. pre-ARCH-B `theme`), and scalar-count array slots
  (`threads_opened: 0`) are coerced or dropped.

Nothing is discarded silently: every coercion appends a fix-event (emitted on
stderr, ingested into the batch audit log), and original values survive under
`section_extras.legacy_*`.

### Backfilling historical batches

`_system/scripts/rewrite_manifest_violations.py` re-runs historical manifests
through the **same** normaliser, so a batch written before a coercion existed
is brought up to the current contract in place (atomic write, idempotent —
re-running a conformant batch is a no-op). The retrofit additionally runs a
**retrofit-only** identity/section synthesiser (`synthesise_required_fields`,
`fill_sections=True`) that recovers `timestamp` / `processor` / `batch_id` /
`format_version` from the filename and batch_id and recovers early-dialect
section aliases (`sources` → `sources_processed`, `notes` →
`knowledge_notes`). Live emission keeps that synthesis **off** so a genuine
"process produced no records" still fails loudly rather than being masked.

Run after any normaliser change:

```bash
python3 _system/scripts/rewrite_manifest_violations.py --batches-dir _system/state/batches --apply
python3 _system/scripts/lint_manifest_schema.py --batches-dir _system/state/batches --schemas-dir _system/docs/manifest-schema --all   # expect 0 violations
```

### Preventing recurrence — when the producer's vocabulary grows

1. **Extend the normaliser, never the consumers.** A new emission shape is the
   producer's problem to absorb. Add the coercion (or alias) in
   `emit_batch_manifest.py` and a regression test; the schema and every
   consumer stay untouched.
2. **Prefer aliasing to enum growth.** A new concept type maps into
   `LEGACY_CONCEPT_TYPE_ALIASES`. Only promote a type into the enum (additive
   MINOR bump + a SemVer-log row above) when it is a genuinely new *canonical*
   category, not a synonym of an existing one.
3. **One normaliser, two callers.** `emit_batch_manifest.py` (live) and
   `rewrite_manifest_violations.py` (retrofit) share the same coercion
   functions — keep them in sync; the retrofit's pipeline mirrors
   `main()`'s.
4. **Backfill in the same change.** Whenever you add a coercion that historical
   batches need, run the retrofit + lint above so the whole batch corpus stays
   at 0 violations. State is kept current, not left to drift.

---

## What is in the manifest

`v2.json` is the field-by-field authority; this table is the map.

| Top-level key | What it carries |
|---|---|
| `batch_id` / `timestamp` / `format_version` / `processor` | Identity. Always present. |
| `sources_processed` | Files consumed (transcripts under `_sources/processed/`). `/minder:mem:process` only. |
| `records` | Records created/updated under `_records/{meetings,observations}/`. |
| `knowledge_notes` | PARA notes created/updated under `1_projects/`…`4_archive/`. |
| `hubs` | Hub files created/updated under `5_meta/mocs/`. |
| `concepts.upserts[]` | Per-batch deduplicated concept registry. Names are conformant by construction. |
| `constitution.{principles,constitution_core_view,soul}` | Tier 0 surface — principles, the auto-rendered core view, SOUL fields. |
| `tier1_objects` | First-class typed objects: `tasks`, `ideas`, `events`, `decisions`, `people`, `projects`, `content`. |
| `tier2_objects` | Schema-registered structured objects: `inventory`, `wardrobe`, `content_candidates`, `lens_observation`, owner-extensible. |
| `sensitive_entities` | Per-batch summary of every entity emitted with `is_sensitive: true`. |
| `threads_opened` / `threads_resolved` | Slot for the deferred Tier 1 thread type. |
| `stats` | Per-skill counters. Schema accepts unknown keys (additive without bump). |
| `section_extras` | Forward-compat slot. |

### Privacy trio

Every Tier 0/1/2 entity entry carries:

- `origin` — provenance enum (`personal | work | external` plus the
  `bootstrap-*` and `sync-*` prefixes for synthetic origins).
- `audience_tags` — `text[]`, whitelist enforced by the engine
  (canonical 5 + per-tenant Extensions in `AUDIENCES.md`); schema
  enforces type only.
- `is_sensitive` — boolean modifier orthogonal to audience.

Defaults are conservative-safe (`personal` / `[]` / `false`). Defaults
are applied at emission, not at validation; the schema enforces
presence + type only.

### Per-skill emission semantics

| Skill | Role | What it emits |
|---|---|---|
| `/minder:mem:process` | Creator. Turns transcripts into records / knowledge / hubs / concepts / Tier 1 typed objects. | All sections; the densest manifest. |
| `/minder:mem:maintain` | Integrator. Reconciles drift, completes graph linkage, suggests tier shifts. | Diff-shaped: `hubs.updated[]`, `tier1_objects.people.upserts[]` with `tier_suggested`, etc. Suggests; never silently mutates ownership semantics. |
| `/minder:mem:lint` | Cleaner / promoter. Auto-fixes (concept names, audience tags, privacy-trio backfill), promotes principle candidates to Tier 0, surfaces dedup pairs as CLARIFICATIONs (does not auto-merge). | Stats + checksum updates for autofixed files; `constitution.principles.upserts[]` on F.5 promotion. |
| `/minder:mem:agent-lens` | Outside-view hypothesiser. Generates lens observations about owner state from accumulated content. | `tier2_objects.lens_observation.upserts[]` with `is_hypothesis: true`; references existing concepts (never creates new ones). |

Per-section field detail: the `$defs` in `v2.json`.

---

## What is NOT in the manifest

Per ENGINE_DOCTRINE.md §3.8 — these stay inside the engine and never
reach a consumer:

- **Candidate buffers** — `principle-candidates.jsonl`,
  `people-candidates.jsonl`. Pre-resolution staging; promotion gates
  on `/minder:mem:lint` F.5 (principles) or `/minder:mem:resolve-clarifications`
  (people).
- **Working memory** — `OPEN_THREADS.md`. Until the focus engine arrives.
- **HITL queues** — `_system/state/CLARIFICATIONS.md`. Owner-facing only.
- **Audit trails** — `log_process.md`, `log_maintenance.md`, `log_lint.md`,
  `agent-lens-runs.jsonl`, `check-decision-runs.jsonl`. Substrate for
  lenses and future cross-source analysis; not consumer-routable.
- **Derived / regenerable views** — `CURRENT_CONTEXT.md`,
  `_system/views/INDEX.md`, `lint-context/{daily,monthly}/*`, hub-map
  projections under `5_meta/mocs/`.

If a consumer needs any of these, the right answer is to derive them
itself from the manifests it does receive — not to reach into engine
internals.

---

## Consumer integration patterns

These are the rules a consumer is expected to follow to stay
compatible with the contract.

### Read order

1. List all `*.json` under `_system/state/batches/` that the consumer
   has not seen before (track by `batch_id` in your own bookkeeping).
2. Sort by **filename timestamp prefix** (the `YYYYMMDD-HHMMSS` part
   of the basename). Filename is canonical — do not rely on
   filesystem ctime, it churns on copy / git restore.
3. Process one at a time. No parallel reads — preserve causal order.

### Idempotency

Every batch carries a `batch_id` that the producer guarantees stable
across re-runs of the same logical batch (re-emit on a downstream
filesystem failure produces the same `batch_id`). Consumers MUST be
idempotent on `batch_id`: receiving the same batch twice yields the
same final state.

For finer-grained idempotency on individual entities, every entity
carries `path` (records / notes / hubs) or a stable `id` (Tier 1/2
objects). Re-applying an unchanged entity should be a no-op; the
`checksum_sha256` field (where present) tells the consumer when
content actually changed and graph reconciliation must run
(consumer invariant 1, below).

### Forward compatibility

When a consumer encounters a key it does not know:

- Inside a known section → skip the key, log once at startup, do
  NOT fail. The producer is allowed to add MINOR-version optional
  fields without coordinating with consumers.
- A whole unknown section → same: skip + log + continue.
- An unknown entry in `section_extras` → same. That slot exists
  exactly to absorb pre-promotion fields.

When a consumer encounters an incompatible major version
(`format_version` major ≠ what the consumer speaks):

- Reject the batch with a loud error. Do not silently skip; the
  whole point of MAJOR is "your code needs updating".
- Recommended: pause subsequent newer batches until the operator
  resolves (ship an updated consumer or a migration shim).

### Graph reconciliation (consumers that maintain a graph)

When an entity's `checksum_sha256` changes between batches, the
consumer MUST diff the entity's relational arrays
(`people`, `concept_hints`, etc.) against its existing graph state
and reconcile edges (add new, remove obsolete). Re-applying based on
the new checksum alone, without diffing, accumulates stale edges.
This is consumer invariant 1, and it applies uniformly across all four
skills' emissions.

### Status semantics

No skill ever causes a hard delete. Lifecycle uses `status`
(`active | archived | superseded | deprecated | dormant`). Consumers
preserve history; default queries can filter by status. This is
consumer invariant 2.

### Epistemic markers

Two entity classes carry epistemic markers consumers should respect:

- **Tier 0 principles** drive prompt calibration in agent consumers.
- **Tier 2 lens-observations** carry `is_hypothesis: true`. A
  consumer that retrieves them as evidence should preserve the flag
  end-to-end so downstream synthesis can frame them as "noticed, not
  confirmed". Never auto-inject into prompt context unconditionally.

---

## Validating a batch

```bash
python3 - << 'EOF'
import sys; sys.stdout.reconfigure(newline="\n", encoding="utf-8")  # LF on Git Bash
import json, sys
from jsonschema import Draft202012Validator
schema = json.load(open('zettelkasten/_system/docs/manifest-schema/v2.json', encoding='utf-8'))
v = Draft202012Validator(schema)
batch = json.load(open(sys.argv[1] if len(sys.argv) > 1 else '/dev/stdin', encoding='utf-8'))
errs = list(v.iter_errors(batch))
if not errs:
    print('valid')
else:
    for e in errs[:20]:
        print(f'@ {list(e.absolute_path)}: {e.message[:200]}')
EOF
```

The same logic runs nightly inside `/minder:mem:lint` Scan H — see
`integrations/claude-code/skills/minder-mem-lint/SKILL.md`. Validator failures
surface as `manifest-schema-violation: <batch_id>` CLARIFICATIONs in
the engine, never silently.

---

## Adjacent docs

- `_system/docs/batch-format.md` — narrative about the
  human-readable `.md` summary that ships next to each `.json`.
- `_system/docs/SYSTEM_CONFIG.md` — engine contract (locks, append-only,
  per-entity field schemas).
- `_system/docs/ENGINE_DOCTRINE.md` §3.8 — the manifest emission
  doctrine across all skills.
- `_system/registries/CONCEPT_NAMING.md` — concept-name format spec.
- `_system/registries/AUDIENCES.md` — audience-tag whitelist.
- `_system/registries/DOMAINS.md` — domains whitelist.
- `fixtures/` — sanitized example manifests, one per skill, used as
  schema-evolution regression tests.
