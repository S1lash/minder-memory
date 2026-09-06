# Obsidian — open your Minder Memory vault

The Minder Memory base ships with an Obsidian vault config. This doc is the
short setup guide. The full usage manual — hotkeys, workflows, graph
presets, daily/weekly recipes — lives at
[`integrations/obsidian/guide.md`](../integrations/obsidian/guide.md)
and is bookmarked from `minder-memory.md` once you open the vault.

## Quick start

After cloning the skeleton (or after `/minder:mem:update`), run:

```bash
bash integrations/claude-code/install.sh
```

This wires Claude Code skills **and** seeds Obsidian config under
`zettelkasten/.obsidian/` plus a `minder-memory.md` dashboard at the vault root.

Then in Obsidian:

1. **Open folder as vault** → select `zettelkasten/`
2. Trust the vault when prompted
3. `Cmd+O` → `HOME` to start

## What you get

- Wikilinks preserved as `[[basename]]` (engine round-trip works)
- Engine runtime paths hidden from search and graph (`_system/state/`,
  `_system/scripts/`, `_sources/processed/`, `*.template.md`)
- Templates plugin pre-pointed to `5_meta/templates/`
- Graph coloured by PARA layer (records, constitution, projects, areas,
  resources, archive, hubs)
- Frontmatter shown as YAML text — Properties UI is available in the
  panel but does not auto-rewrite documents

## What stays yours

After seeding, `.obsidian/` is your config. Subsequent
`scripts/sync_engine.sh` and `install.sh` runs leave it alone. Customise
freely — themes, hotkeys, snippets, community plugins, workspace layout.

To reset to engine defaults later:

```bash
bash integrations/obsidian/seed.sh --force
```

This backs up your existing `.obsidian/` to `.obsidian.backup-{ts}/` and
re-seeds.

## Things to avoid

**Don't toggle `useMarkdownLinks` to true.** Settings → Files & Links →
"Use [[Wikilinks]]" must stay enabled. Minder Memory skills emit and parse
wikilinks; switching would break round-trip with `/minder:mem:process` and
`/minder:mem:maintain`.

**Don't bulk-edit frontmatter via the Properties panel** on files in
`_records/`, `_system/registries/`, `0_constitution/`, or
`_system/views/`. The Properties UI normalises keys, quotes, and array
styles in ways that surface as `process-compatibility` clarifications
on the next `/minder:mem:lint` run. Edit those files via skills (`/minder:mem:process`,
`/minder:mem:maintain`, `/minder:mem:resolve-clarifications`) — or, for hand edits,
use the source view (`Cmd+E` → Source mode).

**Don't enable Obsidian Sync on the vault.** It conflicts with the
git-based pipeline and the cross-skill lock matrix. Use git (the
skills `/minder:mem:save` and `/minder:mem:sync-data` handle commit + push + pull).

## Community plugins (recommended)

The seed lists three plugin IDs in `community-plugins.json`. They are
**auto-enabled the moment you install them** — Obsidian reads that
list and activates matching IDs. The seeder does not download plugins
itself (Obsidian's plugin distribution model requires user consent
per install).

The dashboard at `minder-memory.md` is designed around these three. Without them
the `[live]` sections render as code blocks; with them, you get a
working dashboard.

### Required for the dashboard

| Plugin | Search by | What it does |
|---|---|---|
| **Dataview** | "Dataview" by Michael Brenan | Powers `[live]` blocks: recent meetings, observations, active projects. Reads Minder Memory frontmatter directly. |
| **Tasks** | "Tasks" by Clare Macrae | Global view of `[ ]` checkboxes across the vault. Minder Memory already uses this convention in records. |

### Install in one pass

1. Settings → Community plugins → **Turn on community plugins** (one-time consent)
2. Browse → search by name + author above → Install + Enable

### File explorer cleanup — CSS snippet, no plugin

The vault config ships `minder-memory-hide-engine-paths.css` under
`.obsidian/snippets/`. The seeder enables it automatically via
`appearance.json`. It hides `_system/state/`, `_system/scripts/`,
`_system/docs/`, `_system/agent-lens/`, `_sources/processed/`,
`integrations/`, all `*.template.md` files, and Python caches from the
file tree.

To extend: edit the snippet file directly — add a CSS selector like

```css
.nav-folder-title[data-path^="my-folder"] { display: none; }
```

A CSS snippet rather than a plugin on purpose: it is shipped with the
seed, native to Obsidian, and edit-in-place, so hiding a path costs no
third-party dependency you would have to install and keep working.

### Optional extras

- **Calendar** — daily-note view across `_records/`. Pairs nicely with
  the daily-record convention.
- **Templater** — richer templates with variables and JS execution. The
  core Templates plugin shipped in the seed is enough for the existing
  `5_meta/templates/` set; Templater is for friends who want to write
  more complex ones.

None of these are required by the engine — engine skills run from
Claude Code regardless of what's installed in Obsidian.

## Mobile

Obsidian's mobile app works as long as the vault is reachable on the
device (iCloud sync, Working Copy, Termius + git, etc). The same
`.obsidian/` config seeds; community plugins must be installed
per-device.

The Minder Memory engine itself does not run on mobile (skills require Claude
Code). Use mobile for capture and reading; run skills from the desktop.
