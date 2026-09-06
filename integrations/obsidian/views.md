# Obsidian — graph and search presets for Minder Memory

A curated set of filters that turn Obsidian's graph and search into
specific lenses on your Minder Memory base. Each preset is a copy-paste query.

## How to apply a graph preset

1. Open Graph view (`Cmd+Shift+G`)
2. Top-left of the graph: type or paste the query into the **Filters → Search** field
3. The graph re-renders. To return to the default (everything visible),
   clear the field.

> If a preset shows an empty graph: check that quotes are intact when
> pasting (`path:"_records"` not `path:_records`). Obsidian's graph
> search is strict about quoted paths that start with an underscore.

## How to apply a search preset

1. Open Search (`Cmd+Shift+F`)
2. Paste the query
3. To save: click the bookmark icon next to the query.

---

## Graph presets

### 🌐 Default — full semantic graph

Records + constitution + PARA knowledge + people + hubs + lenses +
posts. Engine internals, registries, and aggregator dashboards
(`HOME`, `SOUL`, `CURRENT_CONTEXT`, `INDEX`, etc.) are hidden by
`userIgnoreFilters` automatically.

**Easy way:** clear the filter field (✕ on the right of the search
input, or `Cmd+A` then Delete).

**Explicit query** (starting point for tweaks):

```
path:"_records" OR path:"0_constitution" OR path:"1_projects" OR path:"2_areas" OR path:"3_resources" OR path:"4_archive" OR path:"5_meta/mocs" OR path:"_system/agent-lens" OR path:"6_posts"
```

**Use when:** open exploration; "what does my mind look like as a
network".

### 🪞 Personal layer — synthesis + your own reflections

Constitution + people + lenses + hubs + posts **+ your observations**
(`_records/observations/` — first-person solo reflections). Excludes
meetings (raw multi-party transcripts) and PARA knowledge.

```
(path:"0_constitution" OR path:"3_resources/people" OR path:"_system/agent-lens" OR path:"5_meta/mocs" OR path:"6_posts" OR path:"_records/observations") -file:"PEOPLE"
```

**Use when:** weekly review of your inner layer — what you've thought
about yourself, plus what the system has distilled, with the edges
between them visible.

### 🌊 Activity layer — synthesis + all records (no PARA)

Same as Personal layer **plus meetings**. Constitution + people +
lenses + hubs + posts + all records (meetings + observations). Strips
only the curated PARA knowledge layer.

```
(path:"0_constitution" OR path:"3_resources/people" OR path:"_system/agent-lens" OR path:"5_meta/mocs" OR path:"6_posts" OR path:"_records") -file:"PEOPLE"
```

**Use when:** weekly review of everything live — who you talked to,
what you reflected on, what the AI noticed, what's anchored in
values — without the cognitive load of curated PARA notes.

### 👥 People web

Just people and records. The social fabric — who you talk to, when, in
what context.

```
path:"_records" OR path:"3_resources/people"
```

**Use when:** preparing 1:1, reviewing relationship patterns, spotting
people you haven't engaged with lately.

### 🧠 Inner view — values, people, lenses, hubs

Strip raw capture (records) and curated knowledge (PARA). What's left
is identity: principles, people, AI insights, semantic hubs.

```
path:"0_constitution" OR path:"3_resources/people" OR path:"_system/agent-lens" OR path:"5_meta/mocs"
```

**Use when:** weekly identity check — are my values, my people, and
the AI's outside view of me coherent? Are hubs structuring my thinking
without leaning on day-to-day capture?

### 🚀 Project landscape

Projects + records + people. What's happening across all your work.

```
path:"1_projects" OR path:"_records" OR path:"3_resources/people"
```

**Use when:** weekly review, project health check, "who's blocking
what".

### 🧬 Hub network

Just hubs and PARA tops. Your mental scaffolding without the noise of
individual capture.

```
path:"5_meta/mocs" OR path:"1_projects" OR path:"2_areas"
```

**Use when:** assessing the structure of your thinking; spotting
isolated hubs that need links to other domains.

### 📚 Knowledge distillation

Everything except raw records. Constitution + projects + areas +
resources + hubs.

```
path:"0_constitution" OR path:"1_projects" OR path:"2_areas" OR path:"3_resources" OR path:"5_meta/mocs"
```

**Use when:** wanting to see only the curated layer — what survived the
capture-to-knowledge promotion.

### 🔒 Sensitive zone

Notes flagged `is_sensitive: true` (frontmatter).

```
["is_sensitive": true]
```

**Use when:** privacy review before sharing the vault, audience-tag
audit, or just confirming the boundary holds.

---

## Search presets

### All open tasks

Plain markdown checkboxes:

```
- [ ]
```

Tasks plugin block (in any note) — much richer:

````
```tasks
not done
sort by priority
```
````

### Recent records

Replace the date with «4 weeks ago» when you use it. Obsidian search
does not support relative dates yet.

```
path:"_records" ["created:>=2026-04-08"]
```

### Mentions of a specific person

```
[[<person-id>]]
```

Replace `<person-id>` with the canonical ID from `PEOPLE.md`
(e.g. `ivan-petrov`).

### Notes in a specific project

```
[[<project-id>]] OR ["projects": "<project-id>"]
```

Replace `<project-id>` with the canonical ID from `PROJECTS.md`.

### Cross-domain insights (heuristic)

Notes that mix work and personal domains — high-leverage entries:

```
["domains": "work"] ["domains": "identity"]
```

Or any other domain pair (`"learning"`, `"relationships"`, etc.). The
search ANDs both clauses.

### Audience: public-shareable

```
["audience_tags": "public"]
```

---

## Tips

- **Combine with Local Graph** — `Cmd+Shift+L` opens the graph view of
  the current note's neighbourhood. Settings inherit (color groups,
  forces). Adjust depth (1-3) to widen the view.
- **Color groups still apply** — graph presets only change which
  nodes are visible. People stay orange, meetings green, constitution
  purple regardless of preset.
- **Save your favourites** — Bookmarks: pin key files. Search: bookmark
  icon next to a query.
- **Front Matter Title plugin** — once installed, all graph nodes,
  file explorer entries, and tab titles show the human-readable
  `title:` from frontmatter instead of the snake-case file ID.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Empty graph after pasting preset | Path query syntax | Use **quoted** paths: `path:"_records"` not `path:_records`. Leading underscores need quotes. |
| Some files I expect are missing | Hidden by `userIgnoreFilters` in `app.json` | Open `app.json`, comment out the regex you want to relax. |
| Filenames showing instead of titles | Front Matter Title plugin not installed/enabled | Settings → Community plugins → search «Front Matter Title» by snezhig → Install + Enable |
| Graph too dense / too sparse | Forces config | Settings → Graph view → Forces → tune `Repel`, `Link distance`, `Center force` |
