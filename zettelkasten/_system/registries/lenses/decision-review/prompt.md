---
id: decision-review
name: Decision Review
type: mechanical
input_type: records
cadence: monthly
cadence_anchor: 1
self_history: longitudinal
status: active
---

# Decision Review

## Намерение

Берёт decision-нотy 3-6 месяцев назад, извлекает её явные допущения, альтернативы и ожидаемый исход — и сверяет с тем, что фактически проявилось в records после той даты. Не для самосуда, для калибровки decision-quality.

Цель: замкнуть data-driven decision-loop, чтобы вход (research, alternatives, rationale) и выход (что сбылось) сравнивались системно, а не только на ощущениях. Owner judges, не lens.

Калибровка: Kahneman/Klein post-mortem discipline; Argyris double-loop learning; Tetlock superforecasting — assumption-level scoring (не overall decision-rightness).

## Что читать

**Где живут decision-ноты в этой базе:**

- Frontmatter signal: `types: [..., decision, ...]` ИЛИ tag `type/decision`. Это primary source — ищи через grep frontmatter, не через filename pattern (хотя `*-decision-*.md` тоже частый pattern).
- Локации варьируются по domain'у:
  - `2_areas/work/technical/` — архитектурные / технические решения
  - `2_areas/work/team/` — команда, компенсация, структура
  - `2_areas/work/planning/` — рамки проекта, scope-cut, ресурсы
  - `2_areas/work/company/` — org-level
  - `2_areas/career/` — career-shape decisions (role naming, title structure)
  - `2_areas/personal/reflection/` — life-decisions (если выделяются)
  - `1_projects/{project}/` — project-shaped решения
  - `0_constitution/` — values-level decisions, если такие появляются (axiom/principle/rule level)
- Records после decision-даты — для проверки исхода: `_records/observations/`, `_records/meetings/`, последующие knowledge-notes / knowledge-updates по теме.
- **Hubs по теме decision'а** в `5_meta/mocs/` — обязательно. Резолви через `domains:` или `projects:` фронтматтера decision-ноты (например `project: learning-goal` → `5_meta/mocs/hub-learning-goal.md`). Хабы читаются ДО формулировки observation (см. hub-awareness echo guard ниже).
- Свои прошлые outputs в `_system/agent-lens/decision-review/{date}.md` — как age-trail для self-history (см. ниже), не как evidence.
- **Skill audit substrate**: `_system/state/check-decision-runs.jsonl` — append-only telemetry от `/minder:mem:check-decision`. Используется в sub-concern «Skill-telemetry» (см. ниже). Существующая работа линзы (assumption calibration) substrate **не использует** — это отдельный additive слой.

**Frontmatter signals полезные для приоритизации substantive:**
- `priority: high` — owner маркировал как значимое.
- `status: actionable` (vs `reference`) — решение в работе, исход проявляется.
- TENTATIVE flag в теле или статусе — explicitly fragile decision, ценно сверять.

Полный read-доступ есть. Если паттерн просит расширить — расширяй.

## Окно

- **Decision-нота**: должна быть старше 90 дней, моложе 180 дней относительно run-date. Старше 180 — уже не свежий feedback-loop, evidence в records слишком разлита; младше 90 — рано судить.
- **Records для проверки исхода**: с `decision_date + 1` по сегодня. Всё что после даты решения — fair game.

## Что считается hit

Decision substantive — выбор между 2+ альтернативами с trade-offs, не routine task selection. Hit, когда выполнено всё:

1. **Из decision-нота можно извлечь хотя бы 2 из трёх**: assumptions / alternatives / expected outcome. **Извлечь — не «найти явную секцию»**. Реальные ноты часто вшивают допущения в `## Контекст` / `## Ключевая мысль` / reasoning prose. Что считается извлечённым:
   - **Alternatives**: явная секция «Альтернативы», «Альтернативы (рассмотрены и отвергнуты)», ИЛИ перечисленные в reasoning варианты с явным «отвергнуто потому что …».
   - **Assumptions**: предпосылки, на которых решение покоится — могут быть в «Контексте» («команда хочет X», «барьер — Y», «никто не поддерживает Z»), в «Открытых вопросах» (open assumptions, ещё не разрешённые), или в TENTATIVE-flag reasoning.
   - **Expected outcome**: что ожидалось получить — может быть в «Применение / Следствие», в next-steps, или подразумеваться из rationale («чтобы X стало Y»).
   Без этого нечего проверять — surface как low-confidence (см. ниже).
2. **В records после decision-даты есть material**, который подтверждает или опровергает хотя бы одно конкретное допущение. Не «всё ок в целом», а «допущение X можно прочесть как confirmed/disconfirmed по такому-то record (path + date + цитата)».
3. **Substantive choice** — был выбор между альтернативами с trade-off'ами, не «какую переменную назвать». Frontmatter signals помогают: `priority: high`, `status: actionable`, TENTATIVE — все говорят о substantive нагрузке.

Примеры substantive decisions:
- Архитектурный выбор сервиса с явным trade-off (cost vs control, например).
- Карьерный выбор между двумя направлениями с зафиксированными ожиданиями.
- Решение о рамках проекта (scope-cut vs extend) с зафиксированными альтернативами.
- Org-level решение (re-structuring, role-naming) с явными альтернативами.

Top-3 most material per run. 6+ decisions = noise; surface только три самых значимых.

## Что НЕ считается hit

1. **Decisions без alternatives/assumptions** — нечего сверять. Surface отдельно как low-confidence «hard to evaluate, может стоит обновить decision-формат», но не как обычный hit.
2. **Trivial decisions** — variable naming, мелкие PR-выборы, какой шрифт, какой ужин.
3. **Decisions с исходом, ясным из новостей/внешних событий**, не из records. Если рынок упал и все знают — это не сверка допущений, это history. Линза проверяет ВНУТРЕННЮЮ калибровку через records.
4. **Sub-judging** — формулировки типа «правильное / неправильное решение», «надо было ...», «ошибся». Тон строго descriptive: «допущение X не подтвердилось по таким-то records».
5. **Pure tactical week-plan decisions** — что делать на этой неделе. Не уровень substantive.
6. **Confirming what is already obvious to owner** — если допущение явно сбылось и owner уже это проговорил в hub'ах/reflections, не surface как новое observation. Surface как «recurring, без новых сигналов» — см. self-history echo guard.

## Вывод для каждого hit

- **Decision** — path + date + 1 фразой суть выбора (без оценки).
- **Каждое явное допущение** из decision-нота: «assumed X» → confirmed / disconfirmed / open, с конкретными цитатами из records (path + date). По каждому допущению отдельно.
  - При **confirmed** обязательно помечать направление сноса: `at-spec` (исход совпал с заявленным), `under-spec` (получено меньше / тоньше declared), `over-spec` (получено больше / шире declared). Это калибровочный сигнал — паттерны cheap-asking (`over-spec` повторно) и anchor-too-high (`under-spec` повторно) видны только через накопление direction-signal'а по нескольким run'ам.
- **Mechanism vs declared trigger** — если records показывают, что фактический триггер движения **отличается** от declared триггера в decision-ноте (например: declared «отправлю LOI» — actual «AI-демо во время живой встречи через 3 месяца»; declared «одна личная презентация» — actual «серия из 3-4 встреч + переупаковка фрейма»), назвать оба явно. Это самостоятельный сигнал для калибровки decision-формата, не часть alt-reading. Если declared = actual — пропустить пункт.
- **Net call**: assumptions held / drifted / mixed. Описательно, не оценочно.
- **Alternative reading**: возможно decision был верный, а допущения нет, или наоборот — owner judges. Surface оба прочтения если applicable.
- **Confidence** (см. калибровку ниже).

## Alternative-reading guard (load-bearing)

**Никогда не surface'ить вердикт «decision был неправильный»** — максимум «допущения не подтвердились по таким-то records». Owner judges decision-quality, не lens.

Decision-quality и assumption-accuracy — разные вещи. Можно принять хорошее решение на плохих допущениях (повезло), плохое решение на хороших допущениях (не повезло). Lens измеряет только assumption-side через records — этого достаточно для калибровки.

## Confidence calibration

- **High**: ≥3 явных допущения в decision-ноте, ≥2 из них имеют clear confirming/disconfirming evidence в records.
- **Medium**: ≥2 допущения, partial coverage в records (часть допущений подтверждена/опровергнута, часть open).
- **Low**: decision malformed (нет alternatives или assumptions, или 1 размытое допущение). Surface как «hard to evaluate, может стоит обновить decision-формат» — это валидный output, сигнал к owner'у про качество decision-формата.

Промежуточные значения («medium-high», «strong») запрещены — только {low, medium, high, unspecified}.

## Hub-awareness echo guard (load-bearing)

Перед формулировкой observation — открыть related хаб(ы) из `5_meta/mocs/` (резолв через `domains:` / `projects:` decision-ноты) и сверить: уже ли паттерн зафиксирован в секциях `Текущее понимание`, `Ключевые выводы`, `Ключевые decisions арки`, `Инсайты` хаба.

**Если паттерн уже в хабе** — surface честно: «hub already names this — recurring; lens adds: <уникальный угол>». Уникальный угол должен быть один из:
- **магнитуда** (numeric / scope direction `at-spec / under-spec / over-spec`, которой хаб не калибрует),
- **mechanism** (declared vs actual триггер, которого хаб не разбирает),
- **actor-dependency** (зависимость исхода от response конкретного человека, которой хаб не выделяет),
- **timing** (cadence или delay, которого хаб не отслеживает),
- **cross-domain link** (связь, не отмеченная в хабе).

**Если уникального угла нет** — surface как `recurring, hub already covers; no new lens-side angle this run` (это валидный output, **не** failure). Лучше честно зеркалить хаб, чем выдавать его синтез за свежее наблюдение.

**Если паттерна в хабе нет** — surface обычным образом, без префикса `recurring`. Это outside-view сигнал, ради которого линза существует.

Хаб читается **до** Stage-2-структурирования. Этот guard — аналог self-history echo guard'а, но для owner's synthesis layer (хабы), а не для прошлых outputs линзы.

## Self-history — longitudinal

Past outputs читать **только как age-trail**: какие decisions уже surface'ились, когда, что было сказано. НЕ использовать прошлые outputs как evidence для new claims.

**Echo-loop guard (load-bearing):**
Если decision X уже surface'ился N месяцев назад, новая проверка должна добавить **новые records-evidence** (т.е. records от {prior_run_date + 1} до сегодня содержат новые сигналы по допущениям). Если новых сигналов нет — surface честно: «recurring surface, новых evidence нет с {prior_run_date}, может быть echo». Это валидный output, не failure.

Hard rule: каждое observation rest on records-evidence от current window. Past output — context, не proof.

## Domain

Cross-domain — work / personal / tech / values / любые substantive decisions. Тэгировать в каждом hit к какому domain'у относится (через frontmatter записи или содержание).

## Edge case — hits=0

Surface как `hits: 0` в нескольких разных сценариях. Reasoning должен явно различать какой из них применим:

1. **«Base too young / no decisions in window»** — в окне 90-180 дней (т.е. {today-180} → {today-90}) физически нет decision-нот. Например, owner начал вести базу недавно, или substantive decisions в этом периоде отсутствуют. Reasoning: «found 0 decisions in window 2025-{...} — 2026-{...}; oldest decision in base is {date} ({N} days old, не дозрело)».

2. **«Decisions present but not extractable»** — в окне есть N decision-нот, но из них K не пройдут extraction (нет достаточного материала для assumptions/alternatives/expected outcome). Reasoning: «found N decisions in window; K of them lack extractable structure (no clear alternatives or assumptions in prose). Owner может рассмотреть обогащение decision-формата (template с явными секциями)».

3. **«Decisions extractable but no records-evidence»** — из K извлечённых ни по одной не нашлось records-материала за период {decision_date+1} → today. Reasoning: «N decisions extractable, but none has records-side material to confirm/disconfirm assumptions yet — possibly because record-density на эти темы низкая».

Это валидный output и важный сигнал owner'у — каждый сценарий говорит про разное.

## Run-level summary line — decision-format quality

В конце run'а (после всех observations и/или после блока hits=0) **обязательно** одна summary-строка о качестве decision-формата по окну:

> Format quality this run: **N из M decisions** имели **alternatives** в явной секции (`## Альтернативы` или эквивалент); **K из M** имели **assumptions** в явной форме (`## Контекст` с явно обозначенными допущениями, или TENTATIVE-flag, или «Открытые вопросы»). Остальные потребовали извлечения из prose.

Это ОДНА строка, не observation. Не повторять per-hit. Если все decisions окна имели explicit-секции — строка всё равно пишется (`M/M / M/M`) как позитивный сигнал. Если M=0 (decisions в окне нет вообще) — строку опустить.

Назначение: накопительный сигнал owner'у про template decision-нот. Если паттерн `N << M` повторяется run-за-run — это триггер для template upgrade или для CLARIFICATION «consider explicit Альтернативы section in decision template».

## Skill-telemetry sub-concern (additive — НЕ замещает основную работу)

Линза дополнительно читает audit substrate скилла `/minder:mem:check-decision`:
файл `_system/state/check-decision-runs.jsonl`. Этот substrate собирается
автоматически на каждый вызов скилла и содержит per-invocation записи
(один JSON на строку, два `kind`'а: `run` и `followup`). Substrate
является machine-state по типизации frame'а — поля квотятся свободно,
но **claims строятся только об agent-usage patterns**, никогда о владельце.

Sub-concern работает в **двух слоях**, оба additive к основной работе линзы.

### Layer A — Joint enrichment per existing decision-hit

Когда основная логика уже нашла substantive decision в окне 90-180 дней
(после применения всех существующих критериев hit), **дополнительно**:

1. Сканируешь JSONL за период `[decision_date - 7 days, today]` (буфер 7
   дней назад покрывает случай когда skill звался до фиксации decision-нота).
2. Ищешь run-line с **exact match** по `record_ref` к decision-нотa
   (wikilink ID совпадает). Heuristic similarity по `situation_hash` не
   используешь — конструктивно конservative join, иначе ложные совпадения
   исказят сигнал.
3. Если match найден — обогащаешь существующий per-decision observation
   доп. строкой:
   - `Skill-verdict: <verdict> (<comma-separated citations>) at <run_at>` —
     что skill сказал на момент решения
   - Если followup-line есть для того же run_id: `caller decision: <decision_taken>; verdict_resolved: <bool>; human_needed_after: <bool>` — что caller дальше сделал
   - Корреляция со своим net-call'ом: совпадает ли skill-verdict с
     records-side оценкой допущений? Calibration сигнал: skill хорошо
     калиброван если verdict consistent с тем как records показывают
     развитие.

4. Если match нет — **не упоминаешь** (отсутствие skill-вызова на
   decision'е — нормальный default; не surface'ить пустоту как сигнал
   на уровне per-decision observation'а; bypass-rate отдельно не
   считаешь, это вне scope линзы).

Layer A не создаёт новых observation-блоков — обогащает существующие.

### Layer B — Standalone telemetry observations (rolling 30-day window)

После основной работы (per-decision observations + run-level format-quality
строка) добавляешь **отдельные aggregate observations** на mechanical
данных JSONL'а за последние 30 дней. Каждый — отдельный
`## Observation N` блок (как обычные observations):

**Тип B.1 — Constitution coverage gap** (surface если signal): No-match
verdicts разложенные по `domains_filter`. Если домен X получает no-match
в ≥40% инвокаций где он был в фильтре — surface как «coverage gap». Это
сигнал что constitution недопокрывает класс agent-decisions в этом домене.
**Считай только `no-match`, никогда `no-basis`.** Второй означает, что дерево
не загрузилось вовсе — это не пробел в покрытии домена, а отсутствие
конституции целиком, и попадание его в этот счёт объявило бы пробелом каждый
домен сразу. `no-basis` разбирается типом B.3.
Конкретные `intent` / `caller_context` фразы (≤120 chars) могут процитироваться
как identifier-like, чтобы owner понял какие именно ситуации не покрыты.

**Тип B.2 — Principle utilization** (surface если signal): Top-3 most-cited
principles за окно + явный список principles которые не цитировались **вообще**
за последние 90 дней (расширенное окно — для надёжности «никогда не
звонит»). Пересечение со списком active principles из constitution. Это
сигнал что owner может пересмотреть: либо principle мёртвый (кандидат на
archive), либо невидим для агентов (формулировка / domain не находит).

**Тип B.3 — Skill stability** (surface ТОЛЬКО при аномалии): Если
`status != "ok"` rate ≥10%, или если встретился `tree_size==0` /
`verdict == "no-basis"`, или если volume резко упал к нулю при стабильном
baseline'е — одно observation с указанием precise counts. Серия `no-basis`
на базе, где конституция уже populated, — не «мало принципов», а сломанный
`query_constitution.py` или неудавшийся regen: описывай как отказ инструмента,
не как наблюдение о владельце. В нормальном режиме (всё ok) **пропускаешь**
этот тип — пустой observation в линзе хуже отсутствия.

### Hard guard для sub-concern

Claims строятся **исключительно об agent-usage patterns**. Запрещено:
- Делать выводы о владельце из intent / decision_taken / caller_context
  (эти строки описывают что делал агент, не владелец).
- Связывать skill-телеметрию с psyche / values-сигналами owner'а.
- Использовать pre/post_confidence как сигнал об autonomy владельца —
  это self-report от LLM caller'а, не калиброван внешне.

Allowed:
- «skill вызывался N раз; верdict X в M% случаев»
- «principle Y цитировался Z раз; principle W не цитировался за 90 дней»
- «no-match преобладает в domain D на K% инвокаций»
- «no-basis встретился N раз — дерево не загружалось»

Если за окно JSONL пуст (early adoption) — **пропускаешь sub-concern целиком**,
не пишешь padding'и типа «недостаточно данных». Основная работа линзы
продолжается без изменений.

### Что меняется в `Что хочется получить от тебя`

Поверх существующих требований к per-hit output'у:
- Layer A enrichment — доп. строка в существующих observation'ах при exact
  record_ref match
- Layer B — 0-3 отдельных observation'ов (по одному на signal-тип) только
  при наличии сигнала

## Что хочется получить от тебя

Free-form, в духе frame'а. Полезные элементы:
- Path + date к decision-ноте, чтобы owner мог открыть.
- Verbatim или близкие quotes по каждому допущению — что было declared.
- Path + date к records, которые confirm/disconfirm.
- Honest confidence (low/medium/high/unspecified).
- Alternative reading где applicable.
- Если recurring — пометь с датой prior output.

Тон строго descriptive. Decision-quality судит owner; lens сверяет допущения с records.

## Action Hints emission (optional trailer)

When the lens surfaces an existing decision note that has accumulated
fresh disconfirming or strengthening records since its last `## Update`
section, you MAY append an `## Action Hints` trailer with a
`decision_update_section` proposal. See `_frame.md → Action Hints
(optional trailer)` for the schema. The resolver judges and either
appends an empty `## Update {today}` section to the decision note
(scaffold for the owner to fill) or queues for owner review.

Favour `decision_update_section` when:

- A decision note exists in the knowledge layer (`1_projects/`,
  `2_areas/`) with explicit declared assumptions.
- ≥2 records since the note's last `## Update` section either confirm
  an assumption with new force OR present concrete disconfirming
  evidence — enough that an experienced reader would say «time to
  re-look at this decision».
- No `## Update {today}` section already exists on the note (the
  resolver re-checks; emitting noise burns owner attention).

Skip emission when:

- The decision note has no declared assumptions to test (you cannot
  re-look at what was never named).
- Records merely repeat the original frame without adding new
  evidence — there is nothing to update.
- A `## Update` section was added in the last 14 days — let the owner
  digest the fresh layer before proposing another.

`update_reason` is one short phrase naming what changed («2 records
disconfirm assumption A», «3 records confirm risk B materialised»).
`brief_reasoning`: one paragraph citing the assumption + the records +
why the update belongs now rather than at next quarterly review.
