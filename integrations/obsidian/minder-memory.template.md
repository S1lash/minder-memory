---
id: minder-memory
layer: ui
type: hub
title: minder-memory
---

# minder-memory

> Your second consciousness — at a glance. Records of what happened,
> threads still open, what the AI noticed, what's pulling your
> attention right now.

📖 [Obsidian guide](5_meta/help/guide.md) · 🌐 [Graph & Search presets](5_meta/help/views.md) · 🔒 [Privacy](5_meta/help/privacy.md) · 🆕 [What's new](5_meta/help/CHANGELOG.md)

> [!warning]+ ✏️ Editing rules — what's yours to edit, what the engine owns
> **Edit freely (your hand-curated layer):**
> - Knowledge notes you wrote (`1_projects/`, `2_areas/`, `3_resources/ideas`, `3_resources/tech`, `4_archive/`)
> - Constitution principles you authored (`0_constitution/{axiom,principle,rule}/`)
> - Hubs (`5_meta/mocs/`)
> - Identity files: [[SOUL]], [[TASKS]], [[CALENDAR]], [[POSTS]]
> - This dashboard
>
> **Don't hand-edit (engine-managed — edits get overwritten or surface as clarifications):**
> - Records (`_records/meetings/`, `_records/observations/`) — `/minder:mem:process` writes them
> - Lens output (`_system/agent-lens/`) — `/minder:mem:agent-lens` writes them
> - Registries (`PEOPLE.md`, `PROJECTS.md`, `TAGS.md`, `CONCEPTS.md`, `AUDIENCES.md`, `DOMAINS.md`) — `/minder:mem:maintain` and `/minder:mem:lint` maintain them
> - Auto-generated views ([[INDEX]], [[HUB_INDEX]], [[CONSTITUTION_INDEX]], [[CURRENT_CONTEXT]], [[constitution-core]])
> - Runtime state (`_system/state/` logs, queues, batches)
> - Roles (`_system/roles/`) — `role.md` belongs to `/minder:mem:role:edit` (a hand edit skips validation), `state/` is the role's own memory, `log.jsonl` is the tick's
>
> **Don't bulk-edit frontmatter via Properties UI** on engine-managed files — Obsidian normalises keys/quotes and surfaces as `process-compatibility` clarifications. Use Source mode (`Cmd+E`) for hand edits.
>
> Need to change something engine-owned? Use the matching skill (`/minder:mem:process`, `/minder:mem:resolve-clarifications`, `/minder:mem:capture-candidate`, `/minder:mem:maintain`).

## 📍 Now

- Focus snapshot: [[CURRENT_CONTEXT]]
- Constitution core: [[constitution-core]]
- Open threads: [[OPEN_THREADS]]
- Pending clarifications: [[CLARIFICATIONS]]

## 🔭 Outside view — lenses **[live]**

> One row per lens, the latest run shown. Lenses recently active stay
> on top; stale ones sink to the bottom. Adding a new lens to
> `_system/agent-lens/` makes a row appear automatically on next
> Dataview refresh.

```dataviewjs
const allLensFiles = dv.pages('"_system/agent-lens"')
  .where(p => p.lens_id);

const byLens = {};
for (const f of allLensFiles) {
  const id = f.lens_id;
  const ts = f.run_at ? +new Date(f.run_at) : 0;
  if (!byLens[id] || ts > byLens[id]._ts) {
    byLens[id] = { f, _ts: ts };
  }
}

const rows = Object.values(byLens).sort((a, b) => b._ts - a._ts);

dv.table(["Lens", "Hits", "Last run", "Output"], rows.map(r => [
  r.f.lens_id,
  r.f.hits ?? 0,
  r.f.run_at ?? "—",
  r.f.title ? `[${r.f.title}](${r.f.file.path})` : r.f.file.link
]));
```

## 🤝 Recent meetings **[live]**

```dataviewjs
const meetings = dv.pages('"_records/meetings"')
  .where(p => !p.file.name.includes("template") && !p.file.name.includes("README"))
  .sort(p => p.created, 'desc')
  .limit(7);

dv.table(["Meeting", "Date", "People"], meetings.map(m => {
  const meetingLink = m.title
    ? `[${m.title}](${m.file.path})`
    : m.file.link;
  const peopleLinks = (m.people || []).map(pid => {
    const p = dv.page(`3_resources/people/${pid}`);
    if (p && p.title) {
      return `[${p.title}](${p.file.path})`;
    }
    return `[[${pid}]]`;
  }).join(", ");
  return [meetingLink, m.created, peopleLinks];
}));
```

## 👁 Recent observations **[live]**

```dataviewjs
const observations = dv.pages('"_records/observations"')
  .where(p => !p.file.name.includes("template") && !p.file.name.includes("README"))
  .sort(p => p.created, 'desc')
  .limit(5);

dv.table(["Observation", "Date"], observations.map(o => [
  o.title ? `[${o.title}](${o.file.path})` : o.file.link,
  o.created
]));
```

## ✅ Open tasks across the vault **[live]**

> Powered by the Tasks plugin. The Tasks plugin renders tasks with its
> own engine — file labels show basenames; Front Matter Title's
> integration with Tasks is limited. To see source notes, click any
> task's location link.

```tasks
not done
limit 20
sort by priority
```

## 🚀 Active projects **[live]**

```dataviewjs
const projects = dv.pages('"1_projects"')
  .where(p => p.file.folder === "1_projects"
           && !p.file.name.includes("template")
           && p.file.name !== "PROJECTS"
           && p.file.name !== "README")
  .sort(p => p.file.name, 'asc');

dv.list(projects.map(p => p.title
  ? `[${p.title}](${p.file.path})`
  : p.file.link
));
```

## 👥 People — recent activity **[live]**

```dataviewjs
const people = dv.pages('"3_resources/people"')
  .where(p => p.file.folder === "3_resources/people"
           && !p.file.name.includes("template")
           && p.file.name !== "PEOPLE"
           && p.file.name !== "README")
  .sort(p => p.modified, 'desc')
  .limit(15);

dv.table(["Person", "Role", "Org", "Last update"], people.map(p => [
  p.title ? `[${p.title}](${p.file.path})` : p.file.link,
  p.role || "",
  p.org || "",
  p.modified
]));
```

## 🌐 Graph presets

> Open graph (`Cmd+Shift+G`). Hover the code block → click 📋
> (top-right of the block) to copy. Paste into the **Filters → Search**
> field in graph view.
>
> **Reset to default:** clear the filter field — click ✕ on the right
> of the search input, or `Cmd+A` then Delete.

> [!example]+ 🌐 Default — full semantic graph
> Records + constitution + PARA knowledge + people + hubs + lenses +
> posts. Aggregator registries (`PEOPLE.md`, `PROJECTS.md`), indexes
> (`INDEX`, `HUB_INDEX`, `CONSTITUTION_INDEX`), and dashboards
> (`minder-memory`, `SOUL`, `CURRENT_CONTEXT`) are excluded — both by
> `userIgnoreFilters` and by the negative file: clauses below.
>
> ```
> (path:"_records" OR path:"0_constitution" OR path:"1_projects" OR path:"2_areas" OR path:"3_resources" OR path:"4_archive" OR path:"5_meta/mocs" OR path:"_system/agent-lens" OR path:"6_posts") -file:"PEOPLE" -file:"PROJECTS" -file:"INDEX" -file:"HUB_INDEX" -file:"CONSTITUTION_INDEX"
> ```

> [!example]- 🪞 Personal layer — synthesis + your own reflections (no meetings, no PARA)
> Constitution + people + lenses + hubs + posts **+ your observations**
> (`_records/observations/` — first-person solo reflections, already a
> synthesis pass through your own awareness). Excludes: meetings (raw
> multi-party transcripts) and PARA knowledge.
>
> **Use when:** weekly review of your inner layer — what you've thought
> about yourself, plus what the system has distilled.
> ```
> (path:"0_constitution" OR path:"3_resources/people" OR path:"_system/agent-lens" OR path:"5_meta/mocs" OR path:"6_posts" OR path:"_records/observations") -file:"PEOPLE"
> ```

> [!example]- 🌊 Activity layer — synthesis + all records (no PARA)
> Same as Personal layer **plus meetings**. Constitution + people +
> lenses + hubs + posts + all records (meetings + observations). Strips
> only the curated PARA knowledge layer.
>
> **Use when:** weekly review of everything live — who you talked to,
> what you reflected on, what the AI noticed, what's anchored in
> values — without the cognitive load of curated PARA notes.
> ```
> (path:"0_constitution" OR path:"3_resources/people" OR path:"_system/agent-lens" OR path:"5_meta/mocs" OR path:"6_posts" OR path:"_records") -file:"PEOPLE"
> ```

> [!example]- 👥 People web — records + people only
> Your social fabric. Who you talk to, when, in what context.
> ```
> (path:"_records" OR path:"3_resources/people") -file:"PEOPLE"
> ```

> [!example]- 🚀 Project landscape — projects + records + people
> Weekly review view. What's happening across all your work.
> ```
> (path:"1_projects" OR path:"_records" OR path:"3_resources/people") -file:"PROJECTS" -file:"PEOPLE"
> ```

> [!example]- 🧬 Hub network — semantic structure
> Just hubs and PARA tops. Mental scaffolding without capture noise.
> ```
> (path:"5_meta/mocs" OR path:"1_projects" OR path:"2_areas") -file:"PROJECTS"
> ```

> [!example]- 📚 Knowledge distillation — curated layer only
> Everything except raw records. What survived the promotion to
> knowledge.
> ```
> (path:"0_constitution" OR path:"1_projects" OR path:"2_areas" OR path:"3_resources" OR path:"5_meta/mocs") -file:"PEOPLE" -file:"PROJECTS"
> ```

> [!example]- 🔭 Lens observations — what the AI caught
> Outside-view lens output and the records they connect to. Lens files
> now use `[[wikilinks]]` in Evidence and carry a human-readable
> `title:` — they appear as named nodes with proper edges to the
> records they observe.
> ```
> path:"_system/agent-lens" OR path:"_records"
> ```

> [!example]- 🔒 Sensitive zone — privacy review
> Notes flagged `is_sensitive: true` in frontmatter.
> ```
> ["is_sensitive": true]
> ```

## 🧭 Identity & cadence

- Identity, values, focus, working style: [[SOUL]]
- Tasks: [[TASKS]]
- Calendar: [[CALENDAR]]
- Posts queue: [[POSTS]]

## 📊 Browse

- Constitution → [axioms](0_constitution/axiom) · [principles](0_constitution/principle) · [rules](0_constitution/rule)
- Hubs → [5_meta/mocs](5_meta/mocs)
- Records → [meetings](_records/meetings) · [observations](_records/observations)
- Lenses → [_system/agent-lens](_system/agent-lens)
- Hub Index, Note Index, Registries — left sidebar **Bookmarks** pane (`Cmd+Shift+B`)

## 📖 Engine reference

- Concept: [[CONCEPT]]
- Processing principles: [[PROCESSING_PRINCIPLES]]
- Constitution protocol: [[CONSTITUTION]]

## ⚙️ Maintenance

> **Reset graph view to engine defaults** — restores color groups,
> forces, and the default filter from the engine snapshot at
> `.obsidian/graph-defaults.json`. Useful when Obsidian wiped your
> color groups while you tweaked filters. Backs up the current
> `graph.json` to `graph.json.bak-{timestamp}` first.

```dataviewjs
const container = dv.container;
const wrap = container.createEl("div");
wrap.style.display = "flex";
wrap.style.alignItems = "center";
wrap.style.gap = "12px";

const button = wrap.createEl("button", { text: "🔄 Reset graph view to defaults" });
button.style.padding = "6px 12px";
button.style.cursor = "pointer";

const status = wrap.createEl("span");
status.style.color = "var(--text-muted)";

button.addEventListener("click", async () => {
  status.textContent = "working…";
  status.style.color = "var(--text-muted)";
  try {
    const sourcePath = ".obsidian/graph-defaults.json";
    const targetPath = ".obsidian/graph.json";
    const content = await app.vault.adapter.read(sourcePath);

    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 15);
    try {
      const current = await app.vault.adapter.read(targetPath);
      await app.vault.adapter.write(`.obsidian/graph.json.bak-${ts}`, current);
    } catch (e) { /* no current file — first run, skip backup */ }

    await app.vault.adapter.write(targetPath, content);
    status.textContent = "✓ Reset complete. Reload Obsidian (Cmd+P → Reload app without saving) to apply.";
    status.style.color = "var(--text-success, #4ABF41)";
  } catch (e) {
    status.textContent = `✗ Failed: ${e.message}`;
    status.style.color = "var(--text-error, #E91E63)";
  }
});
```
