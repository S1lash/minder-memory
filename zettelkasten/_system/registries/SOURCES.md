# Sources Registry

Whitelist of inbox source directories scanned by `/minder:mem:process`. Each row
describes one source type. Adding a source is a **declarative** operation:
either invoke `/minder:mem:source-add` or append a row here + create the
`_sources/inbox/{id}/` and `_sources/processed/{id}/` folders. No SKILL
code changes required — every per-source behaviour is encoded as a column
on this row.

---

## Schema

| Column | Required | Meaning |
|---|---|---|
| `ID` | yes | Canonical source identifier. Kebab-case. Matches the folder name under `_sources/inbox/` and `_sources/processed/`. |
| `Inbox Path` | yes | Relative path scanned by `/minder:mem:process` Step 2.1. Always `_sources/inbox/{id}/`. |
| `Family` | yes | Processing family — drives which `/minder:mem:process` branch consumes files. One of: `transcript`, `metric-day`, `recap`. See **Family routing** below. Default `transcript` for backwards compatibility (older registries lacking the column are treated as transcript). |
| `Layout` | yes | One of: `flat-md`, `dir-per-item`, `dir-with-summary`. See **Layout types** below. |
| `Default Domain` | yes | Hint for cross-domain classification when content is ambiguous. Free-form (`personal`, `work`, `mixed`, `auto`, `health`, …). `auto` = let the LLM decide per-file; concrete values short-circuit classification. |
| `Skip Subdirs` | optional | Comma-separated list of subdirectory names (relative to `Inbox Path`) that the processor MUST ignore. Empty / `—` = scan everything. Used for reference material that lives alongside transcripts (e.g. `raw/` under `garmin`). |
| `Description` | yes | One-line human description of what lives in this source. |
| `Status` | yes | `active` / `reserved` / `deprecated`. Reserved = whitelisted but inbox empty by design (no error if no files). Deprecated = retain row for audit, skip during scan. |
| `Reason` | required when `Status: deprecated` | Free-form one-sentence rationale per Archive Contract Form B (`SYSTEM_CONFIG.md`). Empty cell on a row in `## Deprecated Sources` is a contract violation — surfaces as `archive-reason-missing` CLARIFICATION on next `/minder:mem:lint`. |

### Family routing

| Family | Branch | Pipeline shape |
|---|---|---|
| `transcript` | Default LLM pipeline (Step 3 onward) | Subagent dispatch, classification, knowledge-note extraction, multi-domain routing. Files become record + knowledge notes. |
| `metric-day` | Inline deterministic Python (Step 2.5, no LLM) | One file → one biometric record under `_records/biometric/{source_id}/{date}.md` (per-device namespace; each metric-day source keeps independent records + σ-baselines). Rolling baselines + σ-deviation flags + streak detection. See `_system/scripts/process_metric_day.py`. Privacy trio hard-set: `is_sensitive: true`, `audience_tags: []`, `origin: personal`. |
| `recap` | Reserved | Future short-form session-recap branch; falls back to `transcript` for now. |

A single `/minder:mem:process` invocation may mix families; the metric-day
phase runs first inline, transcript phase runs second via existing
subagent dispatch. Manifest carries one batch_id with multiple
sections (e.g. `records`, `records.biometric`).

### Layout types

- **`flat-md`** — files live directly at `inbox/{id}/*.md`. One file = one item. The file's mtime or filename is the chronological key. Example: hand-written notes, daily Garmin snapshots.
- **`dir-per-item`** — each item is its own folder: `inbox/{id}/{folder}/transcript.md`. The folder name carries the timestamp / topic. Example: voice-note exports without summary. The single-`*.md` fallback applies (see «Naming tolerance» below) when `transcript.md` is absent.
- **`dir-with-summary`** — same shape as `dir-per-item`, but the source MAY also produce `transcript_with_summary.md` next to `transcript.md`. The processor prefers the `_with_summary` variant when present, falls back to plain `transcript.md`, then to the single-`*.md` fallback. Example: Plaud, DJI mic, any AI-summarising recorder.

### Per-item folder naming (dir-per-item / dir-with-summary)

The processor parses the leading timestamp from the folder name. Forms supported and may coexist within a single source:

1. **Portable ISO** (canonical) — `2026-04-29T14-09-30Z` (hyphens in the time part — Windows-safe; what new items look like after ingestion normalisation, see below)
2. **Pure ISO** — `2026-04-29T14:09:30Z` (producer-native form; remains parseable forever for already-processed paths)
3. **ISO + topic suffix** — `2026-04-29T14-09-30Z_short topic` / `2026-04-29T14:09:30Z_short topic`
4. **Date + topic** — `2026-04-29_short-topic`
5. **Legacy / free-form** — `04-29 short topic`, `14-05-2026 19:40`, `2026-05-06_ctp-tms-passkey-tech-recap`, or any other layout an owner / producer creates. Best-effort parse first; if it fails, fall back to file mtime silently. mtime is a safe lower bound for chronological order.

### Portable names (Windows compatibility)

NTFS forbids `< > : " / \ | ? *` in path segments, trailing dots/spaces, and
reserved device basenames (`CON`, `PRN`, `COM1`…). Some producers (Plaud and
similar recorders) name export folders with pure-ISO timestamps whose colons
make the path uncreatable on Windows and break `git checkout` on any Windows
clone pulling such a path. The engine therefore normalises **new** inbox item
names at two gates, via the single SoT
`_system/scripts/_common.py::normalize_portable_name` (deterministic,
idempotent — autonomous-resolution layer per ENGINE_DOCTRINE §3.1):

- `/minder:mem:process` pre-scan (§0.0b in the SKILL) — renames before anything reads
  the path, so every downstream reference (`source:`, PROCESSED.md, manifests)
  is born with the safe name;
- `/minder:mem:save` inbox pre-pass — renames before staging, so a raw inbox drop
  committed from one device never breaks checkout on a Windows device;
- `/minder:mem:lint` Scan A.10 — backstop for paths that slipped past both gates.

**Split names.** A producer can put a `/` in the recording title — «07-09
Встреча - A/B-тест». No filesystem accepts that in a name, so the sync or the
unzip turns one segment into two nested directories, and the item lands one
level deeper than its layout says. `normalize_portable_name` cannot reach this:
it works on a NAME, and both resulting segments are legal names. Recovery is
`_system/scripts/repair_split_names.py`, run by `/minder:mem:process` §0.0a with
`/minder:mem:lint` A.10a as the backstop. It rejoins with the same `-` the normaliser
substitutes for `/`, and only inside a folder layout (`dir-per-item` /
`dir-with-summary`), never entering a `Skip Subdirs` folder, and ONLY when the
parent holds exactly one child that is itself a complete item. Every other shape
— including any directory under a `flat-md` source, which may be the owner's own
— surfaces as a `source-layout-split-name` CLARIFICATION and is left in place.

Already-processed paths are **grandfathered**: names under
`_sources/processed/` listed in PROCESSED.md keep their original form, and
references to them are never rewritten. Rename collisions are never resolved
by guessing — they surface as `portable-name-collision` CLARIFICATIONs.

### Naming tolerance (universal across all source-types)

Folder names and contained filenames may be created by the owner manually (drag-drop, ad-hoc capture) or by a variety of producer tools (Claude Code `/minder:mem:recap`, voice recorders exporting under different versions, `kebab-case` renames, etc.). The engine treats both as **best-effort hints**, never as contracts:

1. **Folder naming** — if a folder name doesn't match any pattern above, fall back to file mtime silently. No CLARIFICATION on pure naming non-canonicity.
2. **File naming inside a subfolder** — if `transcript.md` (and `transcript_with_summary.md` for `dir-with-summary`) is absent but a single `*.md` exists, take it. No CLARIFICATION.
3. **CLARIFICATION reserved for genuine quality risk:**
   - Multiple `*.md` files in one subfolder with no canonical name → which is the real transcript? Picking wrong degrades downstream. → `source-format-anomaly`.
   - Missing summary-delimiter inside a file actually named `transcript_with_summary.md` → summary contract violation, downstream consumers rely on it. → `source-format-anomaly`.
   - Folder name parsed to a date that contradicts mtime in a way mtime cannot resolve (e.g. parsed-date in the future, or mtime preserved from a copy long after the content). → `source-folder-naming`.
4. **Producer-controlled source-types** (`plaud`, `garmin`) typically emit canonical names; deviations may signal a producer bug. The right place to catch producer drift is `/minder:mem:lint` heuristics on the source itself, not the inbox scanner. Pure naming non-canonicity is never a blocker.

The principle: **never block on naming**. Naming is a hint; mtime + content classify everything else. CLARIFICATIONs only fire when the engine would otherwise have to guess at the cost of correctness.

For metric-day family the filename is canonical `YYYY-MM-DD.md` — one file per calendar day.

---

## Active Sources

| ID | Inbox Path | Family | Layout | Default Domain | Skip Subdirs | Description | Status |
|---|---|---|---|---|---|---|---|
| plaud | `_sources/inbox/plaud/` | transcript | dir-with-summary | auto | — | Plaud voice-recorder transcripts (popular AI-summarising hardware recorder). | active |
| voice-notes | `_sources/inbox/voice-notes/` | transcript | dir-per-item | auto | — | Generic voice-note transcripts from any recorder/app. Catch-all for users without a brand-specific source. | active |
| claude-sessions | `_sources/inbox/claude-sessions/` | transcript | dir-per-item | work | — | Claude Code session recaps captured via `/minder:mem:recap`. Almost always work-context. | active |
| notes | `_sources/inbox/notes/` | transcript | flat-md | auto | — | Plain Markdown notes dropped manually into the folder. | active |
| crafted | `_sources/inbox/crafted/` | transcript | flat-md | auto | — | Hand-written long-form documents processed through the same pipeline; also the target for verbatim artifacts saved by `/minder:mem:recap --crafted`. | active |
| describe-me | `_sources/inbox/describe-me/` | transcript | flat-md | identity | — | Owner self-descriptions and identity reference material. Primary seed for `/minder:mem:bootstrap` SOUL.md draft; files added after bootstrap flow through `/minder:mem:process` as regular content. `PROFILE.template.md` is excluded by the engine-wide `*.template.md` rule. | active |
| roles | `_sources/inbox/roles/` | transcript | flat-md | auto | — | The inbox door for the owner's Minder Memory roles — an engine-level source registered ONCE for all roles, never per role. A role that finds a fact worth the base's attention drops one human-phrased note here, flat, named `YYYY-MM-DD-{role-id}-{slug}.md` with `source: role:{role-id}` frontmatter; `/minder:mem:process` folds it in like any source. Producer: a role with `inbox` in its `writes:`, run by the `/minder:mem:roles` tick. Shape spec: `_system/roles/_minder.md`. | active |
| resolve-clarifications | `_sources/inbox/resolve-clarifications/` | transcript | flat-md | auto | — | Knowledge the owner states while resolving clarifications, filed here by /minder:mem:resolve-clarifications and processed like any source. | active |
| garmin | `_sources/inbox/garmin/` | metric-day | flat-md | health | raw | Garmin daily biometric snapshots. One file per calendar day; `raw/` holds full minute-level JSON payloads (skipped by /minder:mem:process; available as escape hatch for biometric lenses). Inactive until owner wires a Garmin collector — pipeline lies dormant otherwise. | active |

---

## Reserved Sources

_(Empty by default. Add rows here when whitelisting a source whose inbox stays empty until a future integration is enabled.)_

| ID | Inbox Path | Family | Layout | Default Domain | Skip Subdirs | Description | Status |
|---|---|---|---|---|---|---|---|
| _(empty)_ | | | | | | | |

---

## Deprecated Sources

_(Empty by default. To retire a source, MOVE its row here — do not delete it. Audit trail matters more than table tidiness. The deprecated table carries an additional `Reason` column per Archive Contract Form B.)_

| ID | Inbox Path | Family | Layout | Default Domain | Skip Subdirs | Description | Status | Reason |
|---|---|---|---|---|---|---|---|---|
| _(empty)_ | | | | | | | | |

---

## Adding a new source

**Recommended:** invoke `/minder:mem:source-add` and answer the prompts. The skill validates the ID, appends a correctly-formed row, and creates both inbox/processed folders with `.gitkeep`. Pass `--family <transcript|metric-day|recap>` (default `transcript`).

**Manual fallback:** append a row to the table above using the schema, then create:

```
_sources/inbox/{id}/.gitkeep
_sources/processed/{id}/.gitkeep
```

After either route, `/minder:mem:process` picks up the new source on the next run. No SKILL.md edits required.

---

## Notes

- `/minder:mem:process` Step 2.1 iterates rows in declaration order, then sorts the resulting file list chronologically (Step 2.3) — declaration order is **not** processing order.
- `Family` column drives processing branch (see Family routing above). Default `transcript` if column absent (migration `002-sources-family-column.sh` populates).
- Reserved sources may have empty inbox folders. That is expected and never reported as an error.
- Deprecation protocol: retire a source by moving its row to `## Deprecated Sources` and populate the `Reason` cell. Do not delete rows. (Archive Contract Form B — `SYSTEM_CONFIG.md`.)
- Files named `*.template.md` are never processing candidates in ANY source — engine-wide rule (`/minder:mem:process` §2.2). They are spec/seed material shipped by the engine (e.g. `describe-me/PROFILE.template.md`).
- `describe-me` is dual-consumed: `/minder:mem:bootstrap` reads it (inbox + processed sides) as the primary SOUL.md seed and moves consumed inbox files to the processed-side mirror; `/minder:mem:process` picks up whatever the bootstrap has not consumed — both consumers move files to `processed/` before use, so nothing is ingested twice.
- Reference subdirs that must never reach the processing queue are declared via `Skip Subdirs` (e.g. `garmin/raw/`).
