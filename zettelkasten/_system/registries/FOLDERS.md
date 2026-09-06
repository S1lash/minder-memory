# Folder Registry

Структура папок системы и правила маршрутизации.

`_sources/` и `_system/` описаны точно — это одинаковый на каждой инсталляции
каркас движка. Подпапки PARA-слоёв (`1_projects/` … `4_archive/`) —
**иллюстрация**: их заводит владелец под свою жизнь по правилу «3+ заметки»
внизу файла, и совпадать с примером они не обязаны.

---

## Sources (input)

```
_sources/                             # ВСЕ сырые данные (внутри zettelkasten)
├── inbox/                            # Новые, необработанные файлы
│   └── {source-id}/                  # Whitelist active sources — _system/registries/SOURCES.md.
│                                     # Layout (flat-md | dir-per-item | dir-with-summary)
│                                     # и Skip Subdirs объявлены на row of source.
│                                     # Добавить новый source: /minder:mem:source-add.
└── processed/                        # Обработанные (зеркальная иерархия)
    └── {source-id}/{id}/...          # Mirrors inbox layout. Сюда двигают консумированные
                                      # файлы оба консумера: /minder:mem:process (Step 2.4) и
                                      # /minder:mem:bootstrap (describe-me профиль после Step 2).
```

---

## Zettelkasten Structure (output)

```
zettelkasten/
├── _sources/                     # Сырые данные (см. выше)
│
├── _records/                     # Слой 1: Records (операционная память)
│   ├── meetings/                 # Логи рабочих встреч (kind: meeting)
│   │   └── YYYYMMDD-meeting-{person}-{topic}.md
│   ├── observations/             # Соло Plaud-транскрипты: reflection/idea/therapy (kind: observation)
│   │   └── YYYYMMDD-observation-{topic}.md
│   ├── biometric/                # Daily wearable snapshots (kind: biometric)
│   │   └── {source}/             # per-device namespace (garmin, oura): independent records + baselines
│   │       └── YYYY-MM-DD.md     # one file per calendar day per device; auto-emitted by /minder:mem:process
│   │                             # metric-day branch from _sources/inbox/{source}/<date>.md.
│   │                             # Frontmatter: device: {source}, device_estimate: true.
│   │                             # Privacy: is_sensitive: true, audience_tags: [], origin: personal.
│   │                             # Never hand-edit (see _records/biometric/README.md).
│   └── activity/                 # Daily computer-usage snapshots (kind: activity)
│       └── {source}/             # per-source namespace (activitywatch): focus/attention rhythm + baselines
│           └── YYYY-MM-DD.md     # one file per calendar day; same metric-day branch, activity profile.
│                                 # Metrics: context switches, deep-work blocks, late-night/early-morning,
│                                 # meeting load, work/personal split — σ-baseline tracked like biometric.
│                                 # domains: [time, work]. Privacy: is_sensitive: true (verbatim titles/URLs).
│                                 # Never hand-edit (see _records/activity/README.md).
│
├── _system/                      # Системные файлы (не для заметок)
│   ├── SOUL.md                   # identity + focus + working style
│   ├── TASKS.md                  # автогенерируемый список задач
│   ├── CALENDAR.md               # автогенерируемый календарь
│   ├── POSTS.md                  # реестр опубликованных постов
│   ├── long-form-playbook.md     # owner-рецепт лонгформа (читается по требованию)
│   ├── docs/                     # платформенные документы (binding)
│   │   ├── SYSTEM_CONFIG.md      # runtime config
│   │   ├── ENGINE_DOCTRINE.md    # operating philosophy (symlinked from ~/.claude/rules/)
│   │   ├── ARCHITECTURE.md       # системный дизайн как построен
│   │   ├── CONVENTIONS.md        # documentation style rules (binding)
│   │   ├── batch-format.md       # контракт batch формата (нарратив)
│   │   ├── manifest-schema/      # канонический JSON Schema манифеста + fixtures
│   │   ├── biometric-lens-protocol.md  # общий протокол биометрических линз
│   │   ├── communication-baseline.md   # universal presentation spine (symlinked from ~/.claude/rules/)
│   │   ├── constitution-capture.md     # global hook (symlinked from ~/.claude/rules/)
│   │   └── harness-setup.md      # per-machine install guide
│   ├── roles/                    # standing roles
│   │   ├── _run-frame.md         # механика одного прогона (engine)
│   │   ├── _minder.md            # как роль пользуется базой (engine)
│   │   └── {role-id}/            # один инстанс роли (owner data)
│   │       ├── role.md           # назначение роли целиком
│   │       ├── state/            # память роли между прогонами
│   │       └── log.jsonl         # по строке на исполненный прогон
│   ├── views/                    # авто-генерируемые представления (read-only)
│   │   ├── CONSTITUTION_INDEX.md    # registry активных principles
│   │   ├── constitution-core.md  # harness view (symlinked from ~/.claude/rules/)
│   │   ├── HUB_INDEX.md          # индекс всех hub-заметок
│   │   ├── INDEX.md              # surface catalog: knowledge + archive + constitution + hubs (faceted)
│   │   ├── CURRENT_CONTEXT.md    # live state snapshot
│   │   ├── CONTENT_MAP.md        # content pipeline interface — view over hubs (writer: /minder:mem:maintain)
│   │   ├── biometric/            # недельные биометрические сводки (writer: /minder:mem:maintain)
│   │   └── activity/             # недельные сводки computer-usage (writer: /minder:mem:maintain)
│   ├── state/                    # pipeline state (write-heavy)
│   │   ├── BATCH_LOG.md          # index batch-операций
│   │   ├── PROCESSED.md          # source → note маппинг
│   │   ├── CLARIFICATIONS.md     # human-in-the-loop вопросы от скиллов
│   │   ├── CLARIFICATIONS_ARCHIVE.md  # разрешённые вопросы (append-only)
│   │   ├── OPEN_THREADS.md       # незакрытые стратегические нити
│   │   ├── principle-candidates.jsonl  # append-only candidate buffer
│   │   ├── people-candidates.jsonl     # append-only буфер неразрешённых имён
│   │   ├── check-decision-runs.jsonl   # append-only телеметрия /minder:mem:check-decision
│   │   ├── lens-resolution-history.jsonl  # прецеденты owner-решений по lens-хинтам
│   │   ├── insights-config.yaml  # owner-настройки авто-применения lens-хинтов
│   │   ├── secrets.enc.json      # per-value зашифрованные креды ролей (ключ — вне репо)
│   │   ├── log_process.md        # хронологический лог /minder:mem:process
│   │   ├── log_maintenance.md    # append-only лог /minder:mem:maintain + /minder:mem:bootstrap
│   │   ├── log_lint.md           # append-only лог /minder:mem:lint runs
│   │   ├── log_agent_lens.md     # append-only лог /minder:mem:agent-lens runs
│   │   ├── agent-lens-runs.jsonl # машинный индекс agent-lens runs (one JSON per line)
│   │   ├── agent-lens-rejected/  # raw Stage 2 outputs (validator rejected)
│   │   ├── resolve-sessions/     # per-session логи /minder:mem:resolve-clarifications
│   │   ├── biometric/            # σ-baselines по устройствам
│   │   ├── activity/             # σ-baselines по источникам computer-usage
│   │   ├── batches/              # полные batch-отчёты
│   │   │   ├── {batch_id}.md            # human-readable markdown report (per-batch)
│   │   │   ├── {batch_id}.json          # machine-parseable JSON manifest (consumer contract)
│   │   │   └── {batch_id}-maintain.json # /minder:mem:maintain manifest (per maintain integration batch)
│   │   └── lint-context/         # Lint Context Store: daily/ (30d rolling) + monthly/ (forever)
│   ├── agent-lens/               # agent-lens outputs (private, owner-only review)
│   │   └── {lens-id}/{date}.md   # one snapshot per run per lens
│   ├── scripts/                  # Python pipeline (см. scripts/README.md)
│   └── registries/               # реестры сущностей
│       ├── TAGS.md               # перепись тегов (`tags:` axis; рендерится скриптом)
│       ├── SOURCES.md            # реестр источников
│       ├── CONCEPTS.md           # перепись концептов (рендерится /minder:mem:maintain)
│       ├── CONCEPT_NAMING.md     # canonical concept-name format (`concepts:` axis)
│       ├── CONCEPT_TYPES.md      # зеркало downstream-энума типов концепта
│       ├── DOMAINS.md            # `domains:` whitelist (канонические 13 + extensions)
│       ├── AUDIENCES.md          # `audience_tags` whitelist (canonical 5 + extensions)
│       ├── AGENT_LENSES.md       # agent-lens registry + concept + lifecycle
│       ├── lenses/               # per-lens definitions
│       │   ├── _frame.md         # two-stage frame + validator rules
│       │   └── {lens-id}/        # one folder per lens
│       │       └── prompt.md     # required; companion *.md files allowed
│       └── FOLDERS.md            # этот файл
│
├── 0_constitution/               # Behavioural principles
│   ├── CONSTITUTION.md           # root doc
│   ├── axiom/                    # Tier-1 axioms
│   ├── principle/                # Tier-2 principles
│   └── rule/                     # Tier-3 rules
│
├── 1_projects/                   # Активные проекты с дедлайнами
│   ├── PROJECTS.md               # реестр проектов
│   ├── learning-goal/
│   └── acme-payments/
│
├── 2_areas/                      # Области ответственности
│   ├── work/
│   │   ├── company/              # Компания, оргструктура
│   │   ├── meetings/             # Встречи, совещания
│   │   ├── planning/             # Планирование, стратегия
│   │   ├── reflection/           # Рабочая рефлексия
│   │   ├── technical/            # Технические обсуждения
│   │   └── team/                 # Команда, люди, процессы
│   ├── career/                   # Карьерное развитие
│   └── personal/
│       ├── reflection/           # Рефлексия, мысли
│       ├── health/               # Здоровье
│       └── relationships/        # Отношения
│
├── 3_resources/                  # Ресурсы, справочники
│   ├── tech/
│   │   ├── ai-agents/            # AI, LLM, агенты
│   │   ├── architecture/         # Архитектура систем
│   │   ├── fintech/              # Финтех, платежи
│   │   └── payments/             # Платежные системы
│   ├── ideas/
│   │   ├── business/             # Бизнес-идеи
│   │   └── products/             # Продуктовые идеи
│   └── people/                   # Профили людей
│       └── PEOPLE.md             # реестр людей
│
├── 4_archive/                    # Архив завершённого
│
├── 5_meta/                       # Мета-система
│   ├── CONCEPT.md                # трёхслойная модель + философия
│   ├── PROCESSING_PRINCIPLES.md  # 8 принципов + values profile
│   ├── templates/                # Шаблоны заметок
│   ├── starter-pack/             # стартовые аксиомы для новой базы
│   ├── help/                     # owner-facing справка (посеяна в vault)
│   └── mocs/                     # Maps of Content
│
├── 5_skills/                     # Карточки-шпаргалки по скиллам
│
└── 6_posts/                      # Опубликованный контент
```

---

## Routing Rules

Единственный дом правил маршрутизации: `_system/docs/SYSTEM_CONFIG.md` ссылается
сюда, не дублирует.

Порядок разрешения — первый сработавший шаг выигрывает:
`layer` (record / hub) → `types` по приоритету → `domain` → keywords контента.

### По layer

| Layer | Folder |
|-------|--------|
| record | по `kind` — строки `record (kind: …)` в таблице ниже; `kind` отсутствует → `_records/meetings/` |
| hub | 5_meta/mocs/ |

### По типу (приоритет)

| Type | Folder |
|------|--------|
| project | 1_projects/{project-id}/ |
| meeting | 2_areas/work/meetings/ **[DEPRECATED — новые встречи маршрутизируются как record]** |
| planning | 2_areas/work/planning/ |
| technical + work | 2_areas/work/technical/ |
| technical + ideas | 3_resources/tech/ |
| idea + business | 3_resources/ideas/business/ |
| idea + product | 3_resources/ideas/products/ |
| idea (general) | 3_resources/ideas/ |
| reflection | 2_areas/personal/reflection/ |
| person | 3_resources/people/ |
| log | 2_areas/personal/ |
| record (kind: meeting) | _records/meetings/ |
| record (kind: observation) | _records/observations/ |
| record (kind: biometric) | _records/biometric/{source}/ |
| record (kind: activity) | _records/activity/{source}/ |
| hub | 5_meta/mocs/ |

### По домену (если тип неясен)

| Domain | Folder |
|--------|--------|
| work | 2_areas/work/ |
| career | 2_areas/career/ |
| personal | 2_areas/personal/ |

### По контенту (keywords)

| Keywords | Folder |
|----------|--------|
| проекты, команда, релиз | 2_areas/work/ |
| повышение, зарплата, должность | 2_areas/career/ |
| AI, LLM, агенты, модели | 3_resources/tech/ai-agents/ |
| архитектура, система, дизайн | 3_resources/tech/architecture/ |
| платежи, эквайринг, карты | 3_resources/tech/payments/ |
| стартап, бизнес, монетизация | 3_resources/ideas/business/ |
| продукт, MVP, фича | 3_resources/ideas/products/ |

---

## Creating New Folders

1. Только если есть 3+ заметок для категории
2. Добавить в эту структуру
3. Использовать lowercase-with-dashes
4. Обновить routing rules
