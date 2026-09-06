# Minder Memory — Personal Knowledge Base

## What is Minder Memory

The owner's structured personal knowledge base — meeting notes, reflections,
decisions, people context, ideas, recaps. Three layers: Records (`_records/`),
Knowledge (PARA: `1_projects/` `2_areas/` `3_resources/` `4_archive/`), Hubs
(`5_meta/mocs/`). The values layer (`0_constitution/`) is loaded separately
as a directive via `constitution-core.md`, not searched here.

**Minder Memory base:** `{{MINDER_MEMORY_BASE}}/`

Its skills answer to `/minder:mem:<name>` — `/minder:mem:process`,
`/minder:mem:search`, `/minder:mem:recap`, `/minder:mem:check-decision`, and
the rest. The short form of the product name is **Minder Mem**.

## Aliases — every one of these means this base, permanently

The owner dictates, often by voice and in Russian, and a speech-to-text layer
mangles names. Each of the forms below resolves to Minder Memory; none is
transitional, and the former name stays an alias for as long as this rule
exists:

- the product name and its short form: `Minder Memory`, `minder-memory`,
  `Minder Mem`, `minder-mem`, `память Minder`, `майндер мемори`, `майндер мем`,
  `миндер мем`, `миндер мэм`, `minder mam`, `minder mem`
- the ecosystem word alone, when the context is notes or recall: `minder`,
  `майндер`, `миндер`
- the method it grew from: `zettelkasten`, `цеттелькастен`
- its former name: `ztn`, `зтн`, `ЗТН`, `minder-ztn`
- plain words: `моя база`, `мои заметки`, `вторая память`, `база знаний`,
  `my notes`, `my base`, `second memory`

## Trigger — when to search Minder Memory

### Reactive (owner asks)
When the owner asks to find, recall, or reference something from their notes,
Minder Memory, or any alias above — **search automatically**, no slash command
needed.

### Proactive (Claude initiates) — narrow signals only

Search Minder Memory **without being asked** only when one of these holds:

- The owner explicitly signals recurrence: "я уже думал…", "в прошлый раз…",
  "где-то записывал…", "I've thought about this before", "we discussed this".
- The owner re-derives reasoning that sounds like recovering captured material
  (working through a question that almost certainly lives in a hub).

When searching proactively, surface it: "Проверил твои заметки — нашёл
релевантное: …"

**Do NOT trigger** for: general code work, web search, git history, generic
mentions of a person without recall context, hypothetical decisions, pros/cons
discussions without explicit recall signal.

## How to search

1. **Resolve entities** when searching by person/project/concept:
   - `3_resources/people/PEOPLE.md` — name → ID
   - `1_projects/PROJECTS.md` — project → ID
   - `_system/registries/TAGS.md` — census of the `tags:` axis
   - `_system/registries/CONCEPTS.md` — census of the `concepts:` axis;
     `_system/registries/CONCEPT_NAMING.md` — its name format (snake_case
     ASCII, English-only). Concepts are a separate axis from tags.
   - `_system/registries/DOMAINS.md` — `domains:` whitelist
   - `_system/registries/AUDIENCES.md` — `audience_tags` whitelist
     (canonical 5 + active extensions)

2. **Search** (Grep/Glob, parallel):
   - **Catalog:** `_system/views/INDEX.md` — one line per knowledge, archive,
     constitution and hub entry; the fastest way to locate a topic
   - **Records:** `_records/meetings/`, `_records/observations/`
   - **Knowledge:** PARA folders (`1_projects/` … `4_archive/`)
   - **Hubs:** `5_meta/mocs/`; `_system/views/HUB_INDEX.md` for topic overview
   - **Sources:** `_sources/` for full-text on raw transcripts when the notes
     lack detail
   - Frontmatter grep: person ID, project ID, tags, domains, types, concepts,
     audience_tags, is_sensitive, origin
   - System indexes: `_system/TASKS.md` (todos), `_system/CALENDAR.md` (events)

3. **Return synthesised results.** For each match: title, date, excerpt, tags.
   If the owner asked a question — synthesise an answer from multiple notes,
   not a raw list.

## Session recap — `/minder:mem:recap`

Saves the current session as a transcript under
`{{MINDER_MEMORY_BASE}}/_sources/inbox/claude-sessions/` for later processing by
`/minder:mem:process`. Suggest after sessions with important decisions or
context worth preserving.

Adaptive: when a session produced a **verbatim artifact** the owner will reuse
as-is (toast, speech, letter, post, proposal, spec), the skill can also save it
exactly to `_sources/inbox/crafted/` — on request (`--crafted` / `--crafted-only`)
or proactively, with a bidirectional link to the recap. Crafted-only (no recap)
is valid when only the original matters.

## Decision check — `/minder:mem:check-decision` (suggest, do NOT auto-invoke)

Surface this skill when the owner explicitly frames a decision in **values
terms**:
- "is this aligned with my principles?", "am I being consistent?"
- explicit trade-off framing between two values
- owner asks for a formal / recorded check, not just an opinion

The skill loads the **full** active constitution tree (not only the loaded
`constitution-core.md`), emits a structured verdict, and persists an Evidence
Trail citation on cited principles. That persistence is its unique value vs
inline reasoning over the loaded axioms.

**Do NOT** suggest for: generic pros/cons, architecture choices without
values content, task routing. Inline reasoning over the loaded axioms covers
those without skill overhead.
