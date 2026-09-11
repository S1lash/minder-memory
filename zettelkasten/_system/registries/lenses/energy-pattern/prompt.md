---
id: energy-pattern
name: Energy Pattern (records affect)
type: psyche
input_type: records
cadence: weekly
cadence_anchor: monday
self_history: longitudinal
status: active
---

# Energy Pattern (records affect)

## Намерение

Surface affect/energy markers из voice-note records — что в СОБСТВЕННОЙ narrative tone owner'а заряжает или истощает — и сравнить с предыдущим window'ом, чтобы поймать **SHIFT** в распределении.

Не absolute level (он declared в `SOUL.md`/Working Style), а сдвиг: что-то, что было charge, начало появляться как drain; новая категория drain'а выросла; категория исчезла. Цель — **second-derivative сигнал**, не «mood-ring».

Калибровка:
- ESM (Csikszentmihalyi) — episode-level affect, не aggregated mood.
- Higgins ideal/ought self-discrepancy lexicon — тип сдвига видно в лексике.
- ACT lived-vs-lived comparison — сравнение наблюдаемого с наблюдаемым же, не с идеалом.

## Scope (load-bearing)

Scope разделён на **evidence-scope** (откуда берутся verbatim affect-markers — единственный источник hits) и **context-scope** (куда смотреть для baseline и uniqueness-guard, никогда не как evidence).

**Evidence-scope — ТОЛЬКО records (verbatim affect-markers):**
- `_records/observations/` — solo voice-notes, journal-shape.
- `_records/meetings/` — own-affect parts only. Attribution: верь quote-блокам с явным `<owner>:` / `«…»` приписанным speaker'у (где `<owner>` — имя владельца базы из `_system/SOUL.md` Identity) + `speaker:` frontmatter. Если attribution фразы неоднозначна — skip и зафиксируй в Reasons как «ambiguous attribution, not counted».
- Reflection-ноты — knowledge-ноты с `reflection` в `types:`, в любой папке PARA: recent, если есть verbatim affect-фразы.

**Context-scope — automatic read для baseline и uniqueness-guard (НЕ evidence для hits):**
- `_system/SOUL.md` → Working Style → «Заряжает / Истощает / Выводит из себя» — explicit declared baseline.
- `5_meta/mocs/` — все hub'ы. Особенно: `hub-learning-goal`, `hub-team-communication`, `hub-office-move`, `hub-tooling-rollout` (типичные work-affect темы). На каждом run сканируй hub'ы по affect-релевантным заголовкам / chronological-map / known-pattern секциям — чтобы поймать «уже ли категория отрефлексирована» (uniqueness guard #2).
- `2_areas/` PARA notes, если категория hit'а пересекается с известной life-area (опционально — thinker decides).

Hub-просмотр работает **автоматически на каждом run** без отдельного триггера: если категория-кандидат на hit совпадает с темой существующего hub'а, surface это явно («recurring known pattern, see [[hub-X]] dated YYYY-MM-DD»).

**НЕ scope этой линзы:**
- **Garmin physiological data** (HRV, sleep, body battery, stress) — теперь partly доступно через `_records/biometric/` (см. ниже §«Biometric ground truth»). Глубокая somatic линза остаётся отдельной.

## Biometric ground truth (when `_records/biometric/` is non-empty)

Biometric records are per wearable device:
`_records/biometric/{source}/<date>.md` where `{source}` ∈ `garmin`,
`oura`. Cross-reference journal energy markers with same-date Key
Numbers from **whichever device(s) carry the relevant signal** —
Garmin `bb_end` / `train_status`, Oura `readiness` (Oura's 0-100)
/ `resilience_level`. Read both devices when present; if only one
has data for a day, use that one (never error on the missing one).
Probe specifically for **divergence**:

- Journal says «энергично» / «in flow» BUT Garmin `bb_end < 40`
  consistently same days → potential measurement bias (sensor noise)
  OR misperception (subjective feel diverges from physiological state).
- Journal says «exhausted» BUT `readiness_lvl: HIGH` and
  `stress_avg < 30` → mood-state ≠ physiological recovery.
- Journal silent on energy BUT biometric shows `low_bb_streak` /
  `low_readiness_streak` — silent depletion.

When both devices report the **same** recovery metric for the day
(e.g. sleep_h, HRV, RHR), note any divergence inline as a brief
footnote (e.g. «Oura readiness HIGH while Garmin bb_end low — devices
disagree on recovery that day») — divergence between devices is
itself a signal, not noise to average away.

Treat divergence as **hypothesis**, not conclusion. Surface as one of
the existing three readings (action gap / baseline shift / episode)
with the biometric pattern as the additional anchor.

Per biometric-lens-protocol §n=1 caveats — phrase as «Garmin reports
X while owner journaled Y» / «Oura reports X while owner journaled Y»,
never «X is true while Y was lied about».
- **ActivityWatch behavioral data** (app time, context switches) — живёт в отдельной линзе `time-allocation` (читает `_records/activity/`); сюда не тянуть.
- **Affect about other people** (третьи лица) — «Oleg looked stressed» вне scope.
- **Inferred affect без verbatim source** — гадание, reject.

**Scope-граница**: эта линза НЕ расширяется под Garmin/ActivityWatch. Behavioural-ритм живёт в `time-allocation`; deep somatic-pattern (Garmin) — отдельная будущая линза. Meta-correlation между modalities — задача `biometric-life-synthesis` или owner'а на review.

## Известные ограничения (load-bearing)

**Charge-vs-drain detection asymmetry.** Records-only scope **систематически под-детектит charge** относительно drain. Drain-маркеры вербализуются в voice-notes часто («устал», «бесит», «надоел»). Charge-маркеры почти никогда — owner не говорит вслух «это меня заряжает», он просто работает над этим. Поэтому:

- Это не баг, это scope. Compensating signal — `time-allocation` lens + behavioral signal в meeting-records (что owner добровольно выбирает обсуждать / возвращается к теме).
- На каждом baseline snapshot фиксируй явно «charge surfaced / charge expected (per SOUL declared)» — если ratio устойчиво <1, это known limitation, не shift.
- НЕ изобретать charge-markers, чтобы balance'ить output. Лучше честно зафиксировать «charge thin in records-only scope».

## Окно

- **Текущее окно**: 14 дней (последняя пара недель records).
- **Сравнение**: с предыдущим 14-дневным окном (через past lens outputs as age-trail).

Полный read-доступ есть. Если pattern явно требует более длинного арки — расширяй, но текущее окно для shift-detection — 14 дней.

## Что считается hit

1. **Verbatim affect-phrase** в record — с path + date + цитатой. Не narrative-analysis, а реальная фраза из transcript'а.
2. **Phrase про own state**, не narrative analysis третьих лиц. Распознавание own-vs-other:
   - Own: «я устал», «меня бесит X», «зашло», «не мог сконцентрироваться», «было драйвово», явные I-statements в transcript'ах.
   - Other (out of scope): «N looked stressed», «команда выгорает», «у Y нет энергии». Surface про owner own state only.
   - Граница: в meeting-record собственная реплика owner'а (если transcript её сохранил) — own; описание чужой реакции — other.
3. **Sustained — multi-record**: ≥3 markers одной полярности в текущем окне в одной категории, **distributed across ≥2 different records**. Стандартный hit, full confidence-ladder применима.
   ИЛИ
4. **Sustained — single-session saturated**: ≥3 verbatim markers в ≥2 категориях из ОДНОГО record, при условии что record — длинная reflective session (peer-call ≥30 минут, journal-entry ≥1KB transcript). Допустимо surface как hit, но **cap confidence at medium** до подтверждения в next window. Явно помечать «single-session origin, requires next-window confirmation».
   ИЛИ
5. **Shift**: категория-charge стала появляться как drain (или vice versa) относительно SOUL baseline или предыдущего window. Это и есть основной target линзы.

Категория = тематическая группа (delegation, deep work, meetings, конкретный человек/команда, конкретный вид задач, конкретная life-area). Owner-defined через содержание; не imposed taxonomy. Используй verbatim phrasing owner'а где возможно, чтобы категория была recognizable.

## Что НЕ считается hit (anti-patterns)

1. **Mood ring**: narrative «ты устал» без verbatim source — reject. Без цитаты — гадание.
2. **Single-burst** (single-record SHALLOW) — 1-2 markers из короткой реплики/абзаца, без распределения по категориям. Это аберрация, не паттерн. Surface как «watching only», не как hit.
3. **Single-record SHALLOW concentration** — все markers из одного record И не дотягивает до условий «single-session saturated» из hit-критерия #4 (т.е. либо record короткий, либо markers все в одной категории, либо <3 markers). Surface честно как «episode, single-record, not pattern — все markers из {path}». NB: длинная reflective session с saturated cross-category markers попадает под hit #4, не сюда.
4. **Affect attribution к третьим лицам** — out of scope (будет отдельной линзой про interpersonal patterns, если появится).
5. **Inferred affect без явной фразы** — «он наверное расстроен» по контексту — гадание, reject.
6. **Cross-categorical analogy** «frustration в work и frustration в health = same pattern» — это `cross-domain-bridge` территория, не energy-pattern.
7. **Confirming what is already declared in SOUL** без shift — surface честно как «no shift, baseline confirmed», не как hit.
8. **Tone moralizing** — «надо больше отдыхать», «ты должен», generic поп-психология — запрещено.
9. **Overconfident formulations** — «это burnout точно», «это депрессия» — запрещено. Линза surface'ит наблюдения; диагнозы не её работа.

## Uniqueness guard (load-bearing — bake в reasoning)

Owner уже self-aware — affect-категории explicit'но declared в SOUL Working Style («Заряжает / Истощает / Выводит из себя»), темы регулярно проявляются в reflection-нотах и hub'ах.

Перед тем как surface'ить hit, проверь:
1. **Уже ли это в SOUL Working Style baseline?** Если категория и её полярность совпадают с declared — это НЕ shift. Surface как «no shift, baseline confirms» если это самый сильный сигнал недели.
2. **Уже ли это явно зафиксировано в недавних reflection-нотах** (reflection-ноты последних 30 дней — по `types:`, в любой папке PARA — и hub'ы)? Если уже отрефлексировано owner'ом — surface как «recurring known pattern» с пометкой на reflection-source, не как новое observation.

**Hit valid когда:**
- Категория появилась/выросла относительно baseline (новая, или sustained но не declared).
- Полярность пересекла baseline (был charge → появляется как drain).
- Магнитуда: declared categories — frequency shift (с ≤1/week к ≥3/week и подобное).

**Hit invalid когда:**
- Тон/категория совпадают с SOUL без новизны.
- Already explicitly captured в reflection-ноте за последние 30 дней.

«No shift, baseline confirmed» — валидный и важный output, не failure. Линза не должна изобретать shift'ы, чтобы оправдать существование.

## Domain

Work / personal — обе оси. Тэгировать в каждом hit, к какой относится. Cross-domain affect (one category spans both) — допустимо, но отметить explicitly.

## Вывод

- **Pattern**: «Charge ↑ от X (N records, paths)» / «Drain ↑ от Y (N records, paths)».
- **Quotes**: 2-3 verbatim phrases per category, с path + date.
- **Shift indicator** (если есть):
  - vs prev window — «категория Y выросла с N до M markers».
  - vs SOUL declared — «Y был заявлен как charge, появляется как drain».
- **Three readings** — surface все три, owner judges:
  - **(a) Action gap** — drain растёт в категории, которая всё ещё declared как важная; possible move: time-allocation pull-back.
  - **(b) Baseline shift** — значение Y изменилось; possible move: обновить SOUL Working Style.
  - **(c) Single-week episode** — variance, не pattern; watching only.
- **Confidence** (см. калибровку).

## Confidence calibration

- **High**: SHIFT detected — категория явно пересекла baseline (charge → drain или наоборот) ИЛИ новая категория drain'а; ≥3 verbatim quotes поддерживают; **подтверждено ≥2 consecutive windows**.
- **Medium**: Sustained pattern в текущем окне (≥3 verbatim в одной категории, multi-record per hit-критерий #3) ИЛИ single-session saturated hit (#4) ИЛИ shift-сигнал на одном окне без 2-window confirmation.
- **Low**: Single-window aberration — single-burst (#2 anti-pattern) или single-record SHALLOW (#3) — surface as watching only. Также low когда категория уже в SOUL baseline-confirmed (см. uniqueness guard).

Промежуточные значения («medium-high», «strong») запрещены — только {low, medium, high, unspecified}.

## First-run protocol (load-bearing)

Линза детектит first-run следующим образом:
- В `_system/agent-lens/energy-pattern/` нет prior outputs, ИЛИ
- В `_system/state/agent-lens-runs.jsonl` нет entries для `lens_id: energy-pattern` со `status` ∈ {ok, empty}.

На first-run shift-detection **невозможна by design** (нет prev window для diff). Hits>0 на first run **запрещены**. Output обязательно `hits: 0` с `## Reasons` секцией, содержащей **обязательный блок baseline snapshot** (схема ниже). Этот snapshot — единственный артефакт first-run'а; он фиксирует начальное состояние, чтобы second run имел машинно-сопоставимую базу для shift-detection.

В Reasons-секции на first-run:
1. Явно констатировать «First run — baseline establishment, shift-detection inactive by design».
2. Заполнить блок `### Baseline snapshot` (схема ниже).
3. Опционально — отметить single-record episodes как «watching only» (не hit) с цитатами и path'ами.
4. Echo-loop guard preventive note: «no prior outputs, echo-loop невозможен structurally on first run».

## Baseline snapshot schema (load-bearing на first-run и любом hits=0)

На любом run где `hits: 0` — обязательный блок в Reasons с фиксированной структурой. На hits>0 не требуется (но можно добавить, если thinker считает уместным).

```
### Baseline snapshot

**Drain categories present:**
- {category} ({declared|new}) — N markers / M records — paths: {path1, path2, ...}
- ...

**Charge categories present:**
- {category} ({declared|new}) — N markers / M records — paths
- ...
- charge surfaced / charge expected (per SOUL declared): N/M — {note if asymmetric}

**Cross-polarity shift candidates this window:** {none | category X — was {polarity} per SOUL, surfaces as {polarity} in records}

**New-category drain candidates:** {none | brief description}

**Domain split:** work N markers / personal N markers / cross-domain N markers

**Single-record episodes (watching only):** {none | path + 1-line framing per episode}
```

Категории — owner-defined через содержание, verbatim phrasing где возможно. `declared` = категория уже в SOUL Working Style. `new` = категория не в SOUL.

Это машинно-сопоставимая база. Next run сравнивает свой snapshot с предыдущим — тогда shift-detection становится тривиальной (категории появились / исчезли / сменили полярность / выросли по magnitude).

## Self-history — longitudinal

Past outputs at `_system/agent-lens/energy-pattern/{date}.md` читать как **age-trail для shift-detection**:

- Если категория Y выросла как drain в **трёх consecutive weeks** — pattern крепнет (raise to high).
- Если только в текущем — episode (low).

**НЕ использовать прошлые outputs как evidence для new claims** — только как timeline counter («это третья consecutive неделя где Y появляется как drain, vs ноль таких markers до 2026-04-{...}»).

**Echo-loop risk** (load-bearing):
Longitudinal psyche-линза может self-confirm — увидеть гипотезу из прошлого output'а и трактовать её как evidence для current. Hard rule: **каждое observation rest on verbatim records от current window**. Если current records не содержат свежих verbatim affect-phrase в категории — нет hit'а, даже если прошлые outputs её обсуждали.

Если ловишь себя на повторении прошлой conclusion без свежих records-evidence — surface честно: «this recurs in my outputs but no fresh verbatim affect in records этой недели — это может быть echo, не сдвиг».

## Что хочется получить от тебя

Free-form, в духе frame'а. Полезные элементы:
- Verbatim quote + path + date для каждого markers.
- Категория явно named, owner-recognizable.
- Shift framing где applicable (vs prev window, vs SOUL).
- Three readings (action gap / baseline shift / episode).
- Honest confidence.
- Если recurring — отметь, с датой prior output.

Тон descriptive. Без диагнозов, без морали, без поп-психологии. Surface — owner judges.

Если 0 observations — say so. «No shift, baseline confirmed» — валидный и важный output. Линза должна молчать честно, а не изобретать сдвиги.
