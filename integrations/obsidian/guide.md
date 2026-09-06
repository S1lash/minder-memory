# Obsidian guide for Minder Memory

Working in your Minder Memory vault from Obsidian. Hotkeys, navigation patterns,
recipes for daily / weekly flows, the philosophy of what's where.

## Mental model

Three layers, all visible from Obsidian:

| Layer | Where | Role |
|---|---|---|
| **Records** | `_records/meetings/`, `_records/observations/` | Raw capture from transcripts. Append-only. Edited by `/minder:mem:process`. |
| **Knowledge** | `0_constitution/`, `1_projects/`, `2_areas/`, `3_resources/`, `4_archive/` | PARA hierarchy + constitution. Curated. Where insights distill from records. |
| **Hubs** | `5_meta/mocs/` | Maps of Content. Cross-cutting views — patterns spanning domains. |

Plus operational state: `_system/SOUL.md` (identity), `TASKS.md`,
`CALENDAR.md`, registries (`PEOPLE.md`, `PROJECTS.md`, `CONCEPTS.md`),
auto-generated views (`CURRENT_CONTEXT.md`, `INDEX.md`, `HUB_INDEX.md`).

## What's hidden, and why

Two layers of filtering work together:

- **CSS snippet `minder-memory-hide-engine-paths`** — hides engine internals
  (`_system/state/`, `_system/scripts/`, `_system/docs/`,
  `_sources/processed/`, `*.template.md`, `integrations/`,
  `__pycache__/`) from the file tree. Toggle off in Settings →
  Appearance → CSS snippets if you want to peek.
- **`userIgnoreFilters` in `app.json`** — hides flat aggregator nodes
  (registries, indexes, README files) from search, graph, and Quick
  Switcher. They would otherwise dominate the graph as star-shaped
  hubs connected to everything. Bookmarks pane gives one-click access
  instead.

If you ever need a registry from search, comment out the relevant
regex in `app.json` (`Cmd+P → "Open another vault"` is the only way
to fully reset config).

---

## Hotkeys

| Combo | Action |
|---|---|
| `Cmd+O` | Quick Switcher — fuzzy file open |
| `Cmd+Shift+F` | Global search |
| `Cmd+Shift+G` | Open graph view |
| `Cmd+Shift+L` | Open local graph (neighbours of current note) |
| `Cmd+Shift+B` | Toggle bookmarks pane |
| `Cmd+Shift+O` | Toggle outline pane (headings of current note) |
| `Cmd+Shift+K` | Toggle tag pane |
| `Cmd+Shift+Y` | Insert template (from `5_meta/templates/`) |
| `Cmd+E` | Toggle source / live-preview / reading mode |
| `Cmd+P` | Command palette — find any command by name |

To customise: Settings → Hotkeys → search command name → click `+`.
Engine-shipped defaults are in `.obsidian/hotkeys.json`; your
overrides live in the same file (your edits stick across `seed.sh`
runs because the seeder only re-seeds when `.obsidian/` is missing).

---

## Bookmarks pane (left sidebar)

`Cmd+Shift+B` toggles. Pre-seeded groups:

- 🏠 **Home** — the dashboard
- 📍 **Now** — Current Context, Open Threads, Clarifications
- 🧭 **Identity** — SOUL, Constitution Core, Tasks, Calendar
- 🗂️ **Registries** — People, Projects, Concepts, Tags
- 📊 **Browse** — INDEX, HUB_INDEX, hubs/, meetings/, observations/
- 🌐 **Graph presets** → views.md

Edit freely. Drag to reorder. Right-click any file → "Add to bookmarks".

---

## Graph: workflow

The graph view (`Cmd+Shift+G`) has a default state: empty filter,
your engine internals hidden by `userIgnoreFilters` and graph
`showOrphans: false`. This is the curated "everything semantic" view
shipped in `graph.json`.

### Apply a preset

1. Open `minder-memory.md` → scroll to **🌐 Graph presets**.
2. Click the chevron on a callout to expand. The query is in a code
   block — hover and click 📋 (top-right) to copy.
3. `Cmd+Shift+G` to open graph view.
4. Click **Filters** in the right pane to expand.
5. Paste into the **Search** field. Graph re-renders.

### Reset to default

The "engine default" filter is shipped in `graph.json`. To get back to
it:

- Click the **✕** icon on the right of the Filters → Search field, OR
- `Cmd+A` then `Delete` inside the field, OR
- Close graph view (`Cmd+W` on the graph tab) and reopen it
  (`Cmd+Shift+G`)

If Obsidian wiped your color groups while you tweaked filters (it
sometimes auto-saves the graph state and drops the colorGroups array
in the process), use the **🔄 Reset graph view to defaults** button at
the bottom of `minder-memory.md` (section ⚙️ Maintenance). One click
restores the engine snapshot of `graph.json` and auto-backs up your
current state. CLI alternative for power users:
`bash integrations/obsidian/seed.sh --reset-graph`.

### Why graph isn't fully clickable yet

Obsidian's core graph view doesn't support saving multiple named
filter presets you can switch between with one click. The presets in
HOME and `views.md` are copy-paste because that's the cleanest workflow
the platform allows today. If a community plugin lands that adds
clickable preset switching, the engine will adopt it.

## Graph: reading



The graph is your "second consciousness made visible". Default settings:

- **Color by PARA layer** — people orange, meetings green, observations
  teal, constitution purple, hubs gold, projects blue, archive grey.
- **Arrows show direction** — record → person, principle → record.
- **Hide unresolved** — phantom nodes (broken `[[wikilinks]]`) are
  hidden by default. Enable temporarily to find broken links.
- **Forces tuned for Minder Memory scale** — `repelStrength: 18`,
  `linkDistance: 280`. Clusters spread out instead of collapsing.

For specific lenses (people web, decision lineage, project landscape,
hub network, knowledge distillation, sensitive zone), see
[[views|Graph and search presets]].

### Local graph workflow

The local graph is more useful day-to-day than the global one.
`Cmd+Shift+L` while on any note shows that note's neighbourhood.

- **Open a person → see all your records mentioning them + projects
  they touch.** Quickly scan recent context before a 1:1.
- **Open a principle → see all records that cite it (Evidence Trail).**
  Verify the principle holds in practice.
- **Open a project → see records, people involved, related principles.**
  Project review without leaving the note.

Adjust depth (Settings → Graph view → Filters → Depth) — 1 shows
direct neighbours, 2-3 widens to second-order connections.

---

## Visual cues — note types at a glance

CSS snippet `minder-memory-note-types` colours the left border of each note's
editor and adds an emoji to its tab:

- 👤 **Person** — orange border
- 🤝 **Meeting** — green
- 👁 **Observation** — teal
- ⚖️ Axiom · 🧭 Principle · 📏 Rule — purple
- 🌟 **Hub** — gold
- 🚀 **Project** — blue
- (Archive — dim grey, slight opacity drop)

Toggle in Settings → Appearance → CSS snippets.

---

## Frontmatter — read but don't bulk-edit

Minder Memory frontmatter is consumed by skills (`/minder:mem:process`, `/minder:mem:lint`,
`/minder:mem:maintain`). The Properties panel in Obsidian's right pane is
fine for browsing — but **don't bulk-edit frontmatter through it** on
files in:

- `_records/` (meetings, observations)
- `0_constitution/` (axioms, principles, rules)
- `_system/registries/` (PEOPLE, PROJECTS, etc.)
- `_system/views/` (auto-generated)

Properties UI normalises keys, quotes, and array styles in ways the
linter flags as `process-compatibility` clarifications. For hand-edits,
use Source mode (`Cmd+E`) — edit YAML as text.

For your own knowledge notes (`1_projects/<your-note>.md`,
`2_areas/<your-note>.md`, `3_resources/ideas/...`), Properties UI is
fine — these are owner-edited.

---

## Daily flow

Suggested cadence inside Obsidian:

1. **Morning — orient:**
   - Open HOME (it's your default)
   - Read **Focus snapshot** ([[CURRENT_CONTEXT]]) — what's "in the air"
   - Scan **Open threads** — what's still open from prior weeks
   - Skim **Pending clarifications** — anything blocking the engine
2. **During work — capture:**
   - Use Plaud / voice input externally; transcripts arrive in
     `_sources/inbox/` (hidden from your view)
   - Run `/minder:mem:process` from Claude Code when batch is ready
3. **Evening — review:**
   - Open Local Graph on any record from today (`Cmd+Shift+L`)
   - See who you talked to, what got captured
   - Read the auto-generated note in `_records/`

## Weekly flow

1. Open the **Project landscape** graph preset
2. For each project, open its local graph — see records of the week,
   people involved, principles cited
3. Run `/minder:mem:lint` from Claude Code (auto-runs nightly anyway) to
   surface dangling threads
4. Use the **Hub network** preset to spot hubs that grew stale

## Monthly review

1. Open the **Decision lineage** graph preset
2. For each principle in `0_constitution/`, open local graph — does
   the Evidence Trail span the month, or has the principle gone
   silent?
3. Use the **Cross-domain insights** search query to find notes that
   bridge work + identity / health / learning — these are the highest-
   leverage entries

---

## Plugins (recommended)

Install via Settings → Community plugins → Browse:

- **Dataview** by Michael Brenan — powers the live blocks in HOME.
  **Required setup after install:** Settings → Dataview → toggle ON
  «Enable JavaScript Queries». Without it, every `dataviewjs` block
  in HOME shows "Dataview JS queries are disabled". The HOME blocks
  for lenses, meetings, observations, projects, and people all rely
  on JS queries to render frontmatter `title:` instead of file IDs.
- **Tasks** by Clare Macrae — global task view across the vault.
- **Front Matter Title** by snezhig (S. Mokienko) — shows
  `title:` from frontmatter instead of the file ID. Critical for
  Minder Memory where IDs are snake_case (`ivan-petrov.md`) but titles are
  human (`Иван Петров`).

Once installed, the plugin auto-loads — `community-plugins.json` lists
its ID. **One extra step required:** Front Matter Title ships with all
its features OFF by default. After install:

1. Settings → Front Matter Title → **Features**
2. Toggle ON: Explorer, Graph, Tab, Header, Quick Switcher, Suggester
3. (Default key is `title`, which matches Minder Memory frontmatter convention —
   no template config needed.)

Dataview and Tasks plugins have no equivalent setup — they auto-work
once installed.

## Things to avoid

- **Don't toggle `useMarkdownLinks` to true.** Settings → Files & Links
  → "Use [[Wikilinks]]" must stay enabled. Minder Memory skills emit and parse
  wikilinks; switching breaks round-trip with `/minder:mem:process`.
- **Don't enable Obsidian Sync.** Conflicts with the git-based
  pipeline and the cross-skill lock matrix. Use git via `/minder:mem:save`
  and `/minder:mem:sync-data`.
- **Don't bulk-edit frontmatter via Properties UI** in engine-managed
  files (see frontmatter section above).

---

## Reset to engine defaults

If your `.obsidian/` config gets weird:

```bash
bash integrations/obsidian/seed.sh --force
```

Backs up the existing `.obsidian/` to `.obsidian.backup-{ts}/` and
re-seeds with engine defaults. Your community plugin installations
survive (they live under `.obsidian/plugins/<id>/` which is preserved
by the recursive copy — only top-level config files get reset).

## Reference

- [[views|Graph and search presets]] — copy-paste filter queries
- [[HOME|HOME]] — the live dashboard
- `integrations/obsidian/README.md` — how the integration ships
