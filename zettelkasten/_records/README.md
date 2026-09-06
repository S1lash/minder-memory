# Records Layer

Операционная память Minder Memory. Record — лёгкая, доступная поиску запись одного события:
встречи, соло-наблюдения или одного календарного дня измерений.

## Характеристики

- 1:1 с источником: одна встреча = один record
- Лёгкий формат: summary, key points, decisions, action items
- Ссылка на исходный транскрипт в `## Source` (оригинал в `_sources/processed/`)
- Не содержат рефлексии или аналитики
- Knowledge notes извлекаются отдельно, когда есть значимый инсайт

## Структура

```
_records/
├── meetings/
│   └── YYYYMMDD-meeting-{participants}-{topic}.md
├── observations/
│   └── YYYYMMDD-observation-{topic}.md
├── biometric/
│   └── {source}/YYYY-MM-DD.md
└── activity/
    └── {source}/YYYY-MM-DD.md
```

Четыре kind'а. Первые два приходят из транскрипта и несут смысл, который извлёк LLM:

- **meeting** — multi-speaker work meetings (см. `meetings/`)
- **observation** — solo Plaud transcripts: рефлексии, идеи, терапия (см. `observations/README.md`)

Вторые два — детерминированная проекция данных устройства, один файл на календарный
день на источник. Их пишет metric-day-ветка `/minder:mem:process` без участия LLM, и руками
их не правят:

- **biometric** — суточные срезы носимых устройств (см. `biometric/README.md`)
- **activity** — суточные срезы работы за компьютером (см. `activity/README.md`)

Якорь для knowledge notes: всегда wikilink на record-id, никогда на путь транскрипта.

## Отличие от Knowledge Notes

Records отвечают на вопрос: «Что произошло?»
Knowledge Notes отвечают на вопрос: «Что решили / поняли / осознали?»

См. `5_meta/CONCEPT.md` для полной архитектуры.
