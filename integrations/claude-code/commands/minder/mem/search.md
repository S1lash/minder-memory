---
name: minder:mem:search
description: Search personal Zettelkasten knowledge base from any session. Finds notes by topic, person, project, or keyword.
---

# /minder:mem:search — Search Zettelkasten

Search the personal Minder Memory knowledge base and return relevant content.

**Base path:** `{{MINDER_MEMORY_BASE}}/`

## Query: $ARGUMENTS

## Execution

### 1. Parse Query

Interpret `$ARGUMENTS` as a natural language search query. Extract:
- **Keywords** — main search terms
- **People** — if mentioned (map to person IDs via PEOPLE.md; the format is
  `firstname-lastname`, transliterated lowercase)
- **Projects** — if mentioned (map to project IDs)
- **Time range** — if mentioned ("last week", "in January", etc.)
- **Type filter** — if mentioned ("meetings", "ideas", "tasks", etc.)

### 2. Search Strategy

Run searches in parallel for speed:

**a) Frontmatter search** — grep YAML fields:
```bash
# By person
grep -rl "person-id" {{MINDER_MEMORY_BASE}}/

# By project
grep -rl "project-id" {{MINDER_MEMORY_BASE}}/

# By tag
grep -rl "tag-pattern" {{MINDER_MEMORY_BASE}}/
```

**b) Content search** — grep note bodies for keywords (use Grep tool, not bash grep)

**c) Registry lookup** — check registries for entity resolution:
- `3_resources/people/PEOPLE.md` — resolve person names to IDs
- `1_projects/PROJECTS.md` — resolve project names to IDs
- `_system/registries/TAGS.md` — find relevant tags
- `_system/registries/CONCEPTS.md` — find relevant concepts
- `_system/views/INDEX.md` — one-line catalog of every knowledge, archive,
  constitution and hub entry; scan it before grepping the whole tree

**d) Tasks/Calendar** — if query is about tasks or events:
- `_system/TASKS.md` — search open tasks
- `_system/CALENDAR.md` — search events

### 3. Filter & Rank

- If time range specified: filter by `created:` date in frontmatter
- If type specified: filter by `types:` in frontmatter
- Rank by relevance: exact keyword match > tag match > content mention
- Limit to **top 5-10 most relevant notes**

### 4. Return Results

For each relevant note, show:
- **File path** (relative to zettelkasten/)
- **Title** and **date**
- **Relevant excerpt** — the paragraph or section that matches the query
- **Tags** — for context

If the user asked a question (not just "find X"), also provide a **synthesis** — combine information from multiple notes into a coherent answer.

## Examples

```
/minder:mem:search meetings with my team about strategy
/minder:mem:search learning goal decisions
/minder:mem:search what did I think about AI agents in January
/minder:mem:search tasks related to acme-payments
/minder:mem:search ideas about content publishing
```
