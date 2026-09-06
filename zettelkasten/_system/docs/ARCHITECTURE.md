# Minder Memory Architecture

> The knowledge platform as it is built: a git repository of markdown files,
> enriched in place by the Minder Memory skills. This document describes what runs on
> a machine that has installed the engine — the design principles behind it,
> the alternatives it was weighed against, and the system files it maintains.

**Related documents:**
- [CONVENTIONS.md](./CONVENTIONS.md) — documentation style rules для SKILL / system / spec files (binding)
- [SYSTEM_CONFIG.md](./SYSTEM_CONFIG.md) — the system contract: schemas, hard rules, lock matrix
- Constitution design rationale — folded into [CONSTITUTION.md §1](../../0_constitution/CONSTITUTION.md)

---

## Table of Contents

1. [Philosophy & Key Decisions](#1-philosophy--key-decisions)
2. [Why Not Minder / GBrain / Khoj](#2-why-not-minder--gbrain--khoj)
3. [Minder Memory System Files](#3-minder-memory-system-files)
4. [Risks & Open Questions](#4-risks--open-questions)

---

## 1. Philosophy & Key Decisions

### Core Principle: Git as Single Source of Truth

The entire knowledge base lives as markdown files in a git repository. There is no
separate database that mirrors or duplicates this data. Git provides versioning,
collaboration, and auditability. Everything else is a **lens** over these files.

### Architecture Layers

```
┌─────────────────────────────────────────────────┐
│  PROCESSING LAYER: /minder:mem:process (Claude/Codex)  │  Classifies, atomizes, enriches notes
├─────────────────────────────────────────────────┤
│  STORAGE LAYER: Git repository (markdown files) │  Single source of truth
├─────────────────────────────────────────────────┤
│  CAPTURE LAYER: recorders → _sources/inbox/     │  Voice recording → transcript
└─────────────────────────────────────────────────┘
```

Each layer has a single responsibility. No layer duplicates another's work:
- **Capture** produces raw transcripts (no processing). Which source-types are
  registered, and how each is shaped, is owned by
  [`_system/registries/SOURCES.md`](../registries/SOURCES.md) — the transport
  that delivers a transcript into the inbox is the owner's choice, not the
  engine's concern.
- **Storage** holds all data (no computation)
- **Processing** enriches data (writes to storage, doesn't store separately)

Retrieval is deliberately outside this stack. The engine ships no index and no
search daemon of its own; a reader — a chat client via MCP, an editor, `grep` —
reads the files directly. Prompt templates for one such reader live in
`integrations/minder-memory-mcp/`, and they carry no dependency on the engine
beyond the on-disk conventions described here.

### Key Design Decisions

| Decision | Choice | Alternatives Considered | Rationale |
|---|---|---|---|
| Knowledge store | Git + markdown | PostgreSQL (Minder), GBrain Pages | Git = versioning + collaboration + no sync issues |
| Enrichment | /minder:mem:process (Claude) | GBrain signal-detector, custom agents | Battle-tested skill, 8 processing principles, LLM classification |
| Interchange with consumers | Batch manifest (JSON + markdown) | Direct database access, custom API per consumer | One append-only contract, consumer-agnostic; schema in `manifest-schema/` |

---

## 2. Why Not Minder / GBrain / Khoj

This section is the shape argument: every alternative below stores knowledge in
its own database, and that single property is what the git-centric design
rejects.

### Why Not Minder

Minder is a 12-agent cognitive backend with PostgreSQL + Neo4j + Qdrant + Redis + MinIO.
It was designed as a "smart brain" on top of Minder Memory but introduced:
- **Data duplication**: Minder Memory in git AND Minder in 3 databases
- **Sync complexity**: Changes in git need to be ingested into Minder
- **Operational overhead**: 5 databases + Java app + blue-green deployment
- **Scope creep**: 12 agents, concept graphs, multi-round processing — overkill for note search

Minder Memory + /minder:mem:process already does enrichment. Minder duplicates this with its own pipeline.
The platform works better with Minder removed entirely — not deferred, not optional, removed.

**What Minder did well (preserved here):**
- Entity extraction → already in /minder:mem:process
- Task/event tracking → moved to Minder Memory _system/ files + BATCH_LOG

### Why Not GBrain

GBrain (github.com/garrytan/gbrain) is a Postgres-native knowledge system with:
- 30+ MCP tools, hybrid search, entity extraction, timeline tracking
- Built for Postgres-centric architecture (Pages ingested into pgvector)

**Fundamental incompatibility**: GBrain ingests files into its own database. This creates
a second source of truth alongside git. Every file change requires re-ingestion and sync.
Using GBrain would mean replacing Minder Memory's git model, not augmenting it.

**GBrain features adopted as Minder Memory markdown structures:**
- SOUL.md (identity & state) → see Section 3
- Compiled Truth + Timeline dual model → see Section 3
- OPEN_THREADS.md (unresolved items) → see Section 3
- Tiered entity enrichment → see Section 3
- BATCH_LOG for processing audit → see Section 3

### Why Not Khoj

Khoj is a Python-based AI assistant with web UI, multi-user support, and MCP.
Rejected because:
- Data duplication (same problem as GBrain — ingests into own storage)
- Python stack adds operational complexity
- Web UI is nice-to-have but users already have Claude Desktop / ChatGPT / Telegram
- Heavier resource requirements than reading markdown directly

---

## 3. Minder Memory System Files

Markdown structures the engine maintains. Детальные форматы и schemas —
[SYSTEM_CONFIG.md](./SYSTEM_CONFIG.md); routing — [FOLDERS.md](../registries/FOLDERS.md).

### 3.1 Ключевые принципы

- **Markdown-first.** Все форматы — markdown с YAML frontmatter. JSON используется
  только там, где контракт машиночитаемый по назначению (batch-манифест). Markdown
  лучше для LLM-скиллов + git diff + human review.
- **Backward compatibility.** Новые файлы не ломают существующие. Новые поля frontmatter опциональные.
- **CLARIFICATIONS safety valve (hard rule).** При confidence < threshold скилл пишет вопрос в `_system/state/CLARIFICATIONS.md` вместо auto-decision. Применяется ко всем скиллам (bootstrap, process, maintain, lint).

### 3.2 Системные файлы

| Файл | Назначение | Заполняет | Поддерживает |
|---|---|---|---|
| `_system/SOUL.md` | Identity + Current Focus + Working Style | bootstrap + вручную | lint (focus drift suggestions) |
| `_system/state/OPEN_THREADS.md` | Незакрытые темы (отличается от TASKS — это ожидания/вопросы, не действия) | bootstrap + maintain | maintain + lint |
| `_system/views/CURRENT_CONTEXT.md` | Live state для thin orientation | bootstrap, maintain after-batch | maintain + lint |
| `_system/views/INDEX.md` | Surface catalog of knowledge + archive + constitution + hubs (faceted by PARA / domains / cross-domain); records and posts intentionally out of scope | bootstrap (Step 5.5), maintain after-batch (Step 7.6), regen_all.py — all via `_system/scripts/render_index.py` | maintain + lint A.6 (heartbeat) |
| `_system/state/log_maintenance.md` | Append-only audit maintain + bootstrap | maintain, bootstrap | lint (reads) |
| `_system/state/log_process.md` | Append-only chronological process log | process | lint, maintain (reads) |
| `_system/state/log_lint.md` | Append-only lint audit trail | lint | — |
| `_system/docs/batch-format.md` | Batch format contract — markdown report + JSON manifest; per-entity privacy trio + concept fields; sections `## Concepts Upserted` + `## Sensitive Entities` | manual | manual bump + migration |
| `_system/state/BATCH_LOG.md` | Markdown table, append-only index of batches | process | — |
| `_system/state/batches/{id}.md` | Full report per batch (frontmatter + structured sections) | process | — |
| `_system/state/lint-context/daily/` | 30-day rolling daily summaries | lint | — |
| `_system/state/lint-context/monthly/` | Append-forever monthly summaries | lint | — |

### 3.3 Модификации существующих файлов

- **`SYSTEM_CONFIG.md`** — source type registry, canonical Resolution-action vocabulary, CLARIFICATIONS format contract, cross-skill exclusion rules
- **`PEOPLE.md`** — колонки `Tier`, `Mentions`, `Last`, `Profile`; bootstrap расставляет tiers с нуля, process инкрементирует mentions (1-per-file), maintain suggests promote, lint auto-generates Tier 1 profile skeletons
- **Knowledge notes** — mandatory append-only секция `## Evidence Trail` (timeline источников эволюции знания). Не mutable, только append

### 3.4 Tiered Entity Enrichment

PEOPLE.md registry с mention counting и tier'ами:
- **Tier 3 (stub):** 1-2 mentions → одна строка в PEOPLE.md с контекстом первого упоминания
- **Tier 2 (basic):** 3-7 mentions → расширенная строка с ролью и проектами
- **Tier 1 (full):** 8+ mentions → отдельный профиль в `3_resources/people/{id}.md`

Profile в `3_resources/people/{id}.md` = Tier 1 автоматически независимо от mention count.

**Кто что делает:**
- `/minder:mem:bootstrap` — первичная расстановка tiers, count mentions с нуля
- `/minder:mem:process` — incremental mentions (1-per-file rule), tier только при insert нового person
- `/minder:mem:maintain` — suggests Tier promote through CLARIFICATIONS, никогда не auto-apply
- `/minder:mem:lint` — auto Tier 2→1 profile skeleton generation при достижении threshold (reviewed tier — validate requested)

---

## 4. Risks & Open Questions

### Critical Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **LLM API costs per owner** | MEDIUM | /minder:mem:process, /minder:mem:lint, /minder:mem:agent-lens and /minder:mem:roles all run on a paid model, on every scheduled tick. Frequent recordings × several daily ticks = nontrivial spend. Each owner pays for their own instance; cadence is the lever if it gets expensive. |

### Open Questions

1. **Starter content for a new instance** — a fresh clone has no notes.
   `5_meta/starter-pack/` plus the bootstrap-seeded system files are the current
   answer: a minimal skeleton that grows organically. Whether that is enough for
   a new owner to feel the system work in week one is unproven.

### Architectural Concerns (Self-Criticism)

1. **Git as message bus** — using git push/pull as the sync and trigger mechanism
   is unconventional. It works, but git wasn't designed for event-driven
   architectures. Merge conflicts, push races, and git lock files are real risks
   whenever more than one writer touches the same repo — the scheduled ticks
   (`/minder:mem:process`, `/minder:mem:lint`, `/minder:mem:roles`) each commit and push, and the owner
   commits from more than one device. `/minder:mem:sync-data` and the cross-skill lock
   matrix reduce the window; they do not close it.
