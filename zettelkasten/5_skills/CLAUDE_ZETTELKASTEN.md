---
id: claude-zettelkasten
title: 'Claude Code: Zettelkasten Quick Reference'
created: 2025-01-01
tags:
- type/reference
- topic/zettelkasten
- topic/claude-code
modified: '2026-08-15'
---

# Claude Code: Zettelkasten Quick Reference

---

## При каждом вызове /minder:mem:process

### Обязательно прочитать:

```
0.  _system/docs/ENGINE_DOCTRINE.md        ← Загружается ПЕРВЫМ — обязывающая рамка для всех шагов
1.  _system/docs/SYSTEM_CONFIG.md          ← Runtime config (форматы, routing, типы)
2.  5_meta/PROCESSING_PRINCIPLES.md        ← 8 принципов обработки + values profile
3.  _system/SOUL.md                        ← Identity + Current Focus + Working Style
4.  _system/views/CURRENT_CONTEXT.md       ← Live state — что актуально сейчас
5.  _system/state/OPEN_THREADS.md          ← Незакрытые стратегические нити
6.  3_resources/people/PEOPLE.md           ← Реестр людей (Tier/Mentions/Last)
7.  1_projects/PROJECTS.md                 ← Реестр проектов
8.  _system/registries/TAGS.md             ← Перепись тегов
9.  _system/registries/CONCEPT_NAMING.md   ← Concept-name format spec (autonomous resolution)
10. _system/registries/AUDIENCES.md        ← `audience_tags` whitelist (canonical 5 + extensions)
11. _system/registries/DOMAINS.md          ← `domains:` whitelist (canonical 13 + extensions)
12. _system/registries/SOURCES.md          ← Whitelist источников инбокса
13. _system/views/HUB_INDEX.md             ← Индекс хабов
14. _system/state/PROCESSED.md             ← Что обработано
15. _system/state/CLARIFICATIONS.md        ← Pending clarifications
```

### Pipeline (Steps 0-6):

```
0. Pre-Scan — People Resolution Map + Hub Signal Matching
1. Load Context — system files (see above)
2. Find New Files — scan _sources/inbox/, process all found files
3. Process Each File (sequential):
   3.1 Read transcript
   3.2 LLM Noise Gate
   3.3 Semantic Context Loading
   3.4 16-Question Classification (incl. Q14 content potential, Q15 CONCEPTS — translate non-English / never transliterate, Q16 PRIVACY TRIO inference)
   3.5 Create Outputs (records, knowledge notes, hubs, ideas as living docs)
   3.6 Structural Verification (concept format autofix, trio defaults)
   3.7 Self-Review (subagent-internal coverage check)
   3.8 People Profile Enrichment
   3.9 System Updates
   3.10 Verify Source Integrity
4. Post-Processing — TASKS, CALENDAR, HUB_INDEX, content potential verification, concepts.upserts aggregation, sensitive_entities aggregation
5. Completion Gate — mandatory checklist
5.5 Batch Artifacts — emit `{batch-id}-process.md` (markdown) + `{batch-id}-process.json` (manifest via emit_batch_manifest.py). Суффикс processor'а обязателен — каталог `batches/` общий для process / maintain / lint / agent-lens
6. Report — текстовый отчёт о processed files + audit stats + clarifications
```

---

## Три слоя

| Слой | Путь | Формат |
|------|------|--------|
| Records | `_records/{meetings,observations}/` | Лёгкий: summary + key points (+ action items только в meetings) |
| Knowledge | PARA (`1_projects/` — `4_archive/`) | Полный frontmatter + structured content |
| Hubs | `5_meta/mocs/` | Living document с chronological map |

---

## Ключевые правила

1. **Обрабатывать ВСЕ** новые файлы, не спрашивать
2. **Язык контента** = язык оригинала
3. **Теги/ID** = English, lowercase-with-dashes
4. **Проверять registry** перед созданием сущностей
5. **Обновлять registry** при создании новых
6. **Source section** — ссылка на `_sources/processed/`, НЕ дублирование транскрипта
7. **Рабочие встречи** → `_records/meetings/` (kind: meeting); **соло Plaud** → `_records/observations/` (kind: observation). НЕ `2_areas/work/meetings/`
8. **Self-review** (3.7) — обязателен для КАЖДОГО транскрипта; целостность источника проверяется отдельно в 3.10
9. **Идеи** — living documents (поиск существующих перед созданием)
10. **Люди** — обязательное обогащение профиля при новом контексте
11. **CLARIFICATIONS HARD RULE** — при `confidence < threshold` не принимать решение молча; писать вопрос в `_system/state/CLARIFICATIONS.md`, использовать conservative default, продолжать работу. **Layer-specific exception:** несколько детерминированных слоёв разрешаются автономно и никогда не поднимают CLARIFICATION — квалифицированный список и три критерия допуска живут в ENGINE_DOCTRINE §3.1, здесь не дублируются
12. **Privacy trio per entity** — каждый record / knowledge note / hub / person profile / project profile несёт `origin` (personal/work/external) + `audience_tags[]` (canonical 5 + AUDIENCES.md extensions, default `[]`) + `is_sensitive` (bool). Hub trio auto-derived через `recompute_hub_trio` (preserve owner edits)

---

## Naming

- **Files**: `YYYYMMDD-short-semantic-name.md`
- **Tags**: `category/specific-tag` (kebab-case OK; **distinct axis** from `concepts:`)
- **Concepts**: `snake_case_ascii` (English-only; per CONCEPT_NAMING.md). Translation, never transliteration; engine drops on impossibility
- **People**: `firstname-lastname` (transliterated, lowercase, dash). Голое имя без фамилии — НЕ CLARIFICATION: уходит в `_system/state/people-candidates.jsonl`, `/minder:mem:lint` C.5 еженедельно поднимает только повторяющиеся
- **Projects**: `short-descriptive-name`

---

## Folder Routing

Правила живут в реестре папок — `_system/registries/FOLDERS.md` → `## Routing Rules`.
Он владеет порядком разрешения и всеми таблицами. Читай их там; если файл
недоступен — не угадывай папку, подними CLARIFICATION.

---

## Minder Memory Skills

| Skill | Purpose |
|-------|---------|
| `/minder:mem:process` | Обработка транскриптов → records + notes + batch report |
| `/minder:mem:maintain` | After-batch integrator: threads, hub linkage, CURRENT_CONTEXT regen |
| `/minder:mem:lint` | Nightly consistency, dedup, profile gen, Lint Context Store |
| `/minder:mem:bootstrap` | One-shot populator системных файлов. Disposable. Три режима: established / fresh-onboarding / mixed |
| `/minder:mem:recap` | Session recap → `_sources/inbox/claude-sessions/`; адаптивно сохраняет verbatim-артефакты (тост/письмо/пост) в `_sources/inbox/crafted/` (`--crafted` / `--crafted-only`), двусторонняя связь |
| `/minder:mem:search` | Поиск по базе |
| `/minder:mem:agent-lens` | Прогон линз «взгляда со стороны» по их каденции → `_system/agent-lens/{id}/{date}.md` |
| `/minder:mem:agent-lens-add` | Консьерж создания линзы: разговор на обычном языке → готовая линза (папка + строка в реестре) |
| `/minder:mem:capture-candidate` | Append одного кандидата-принципа в `_system/state/principle-candidates.jsonl`. Fire-and-forget, без локов |
| `/minder:mem:check-decision` | Проверка решения против активного дерева конституции; вердикт + цитаты + запись Evidence Trail |
| `/minder:mem:regen-constitution` | Регенерация производных представлений (CONSTITUTION_INDEX, constitution-core, INDEX, TAGS-зона, SOUL Values) |
| `/minder:mem:source-add` | Регистрация нового типа источника: строка в SOURCES.md + парные папки inbox/processed |
| `/minder:mem:content` | Status из CONTENT_MAP · `--draft <topic>` · `--maintain` (draft-maintainer: живые черновики в 6_posts/drafts/) |
| `/minder:mem:resolve-clarifications` | Interactive разбор очереди CLARIFICATIONS — кластеризация по темам, numbered questions, hypothesis pre-forming против constitution-core, archive resolved |
| `/minder:mem:save` | Категоризованный commit + push в `origin`. Owner-friendly обёртка над git, без auto-chain из других скиллов |
| `/minder:mem:sync-data` | Pull данных из `origin` с rebase (мульти-девайс). Refuses auto-merge на конфликтах прозы — escalates owner |
| `/minder:mem:update` | Pull engine updates из `upstream` (skeleton). Detects local divergence на engine paths, asks per-file, runs migrations. Никогда не трогает data |
| `/minder:mem:roles` | Scheduled tick: прогоняет каждую due-роль последовательно, проверяет её дифф против `writes:`, пишет строку в `_system/roles/{id}/log.jsonl` |
| `/minder:mem:role:add` | Консьерж создания роли: развивает пожелание, зондирует реальные заметки, пишет `role.md`, проверяет предполётом (validate + живой вызов сервиса + пробный прогон) |
| `/minder:mem:role:edit` | Открыть роль, поменять что/когда/куда, провалидировать перед записью. Пауза и возобновление — тот же путь |
| `/minder:mem:role:list` | Что есть, за чем следит, когда последний раз отработала. Read-only |
| `/minder:mem:role:ask` | Спросить роль; отвечает из своих state-файлов и лога, роль не запускает |

---

## Documentation conventions (binding)

Перед любым edit SKILL файлов + `_system/docs/SYSTEM_CONFIG.md` + `_system/docs/batch-format.md`
+ связанных spec files → читай [`_system/docs/CONVENTIONS.md`](../_system/docs/CONVENTIONS.md).

**Короткое правило:** файлы = final spec of current behavior. Никаких version
tags (`v4.5`, `v4.7`), phase references (`Phase 4+`, `per PHASE-4-SDD §Q8`),
rename history (`renamed from X`), release-notes narratives (`V7 closes Phase 4
contract`). Всё это живёт в git log. Файл описывает IS, git описывает BECAME.

---

## Full Documentation

→ `_system/docs/SYSTEM_CONFIG.md` — runtime config
→ `_system/docs/batch-format.md` — batch output contract
→ `5_meta/CONCEPT.md` — архитектура + ADRs
→ `5_meta/PROCESSING_PRINCIPLES.md` — 8 принципов обработки + `projects:`-ось
→ `~/.claude/skills/minder-mem-process/SKILL.md` — pipeline /minder:mem:process
→ `~/.claude/skills/minder-mem-maintain/SKILL.md` — pipeline /minder:mem:maintain
→ `~/.claude/skills/minder-mem-lint/SKILL.md` — pipeline /minder:mem:lint
→ `~/.claude/skills/minder-mem-bootstrap/SKILL.md` — bootstrap logic
→ `_system/docs/ARCHITECTURE.md` — system design
→ `_system/docs/CONVENTIONS.md` — documentation style rules (binding)
