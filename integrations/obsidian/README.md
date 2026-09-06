# Obsidian Integration

Opinionated Obsidian vault config for the Minder Memory base. Seeds a `.obsidian/`
directory and a root `minder-memory.md` dashboard so the vault opens cleanly with
engine paths hidden, wikilinks preserved, Properties UI in passive
mode, and a curated set of bookmarks, hotkeys, and graph presets.

## What's here

| Path | Role |
|---|---|
| `vault-config/app.json` | Link format, attachment folder, `userIgnoreFilters` (registries, indexes, engine internals) |
| `vault-config/appearance.json` | Theme defaults + enabled CSS snippets |
| `vault-config/core-plugins.json` | Enabled core plugins (templates, bookmarks, properties, etc.) |
| `vault-config/community-plugins.json` | Auto-enable IDs: dataview, obsidian-tasks-plugin, obsidian-front-matter-title-plugin |
| `vault-config/templates.json` | Templates plugin → `5_meta/templates/` |
| `vault-config/graph.json` | Graph view defaults + colour groups by PARA layer |
| `vault-config/bookmarks.json` | Pre-pinned navigation tree (Now / Identity / Registries / Browse / Obsidian docs) |
| `vault-config/hotkeys.json` | `Cmd+Shift+G` graph, `Cmd+Shift+L` local graph, `Cmd+Shift+B` bookmarks, etc. |
| `vault-config/snippets/minder-memory-hide-engine-paths.css` | Hides engine runtime paths from the file tree |
| `vault-config/snippets/minder-memory-note-types.css` | Coloured borders + emoji prefixes per note type |
| `minder-memory.template.md` | Dashboard seeded into vault root |
| `guide.md` | Friend-facing usage guide (hotkeys, workflows, recipes) |
| `views.md` | Graph and search preset queries (copy-paste reference) |
| `seed.sh` | Idempotent seeder |

## How it ships

This directory is an `engine:` path in `.engine-manifest.yml`. Friends
pull updates via `scripts/sync_engine.sh` like any other engine path.
Re-running `integrations/claude-code/install.sh` invokes `seed.sh` at
the end, which:

- Copies `vault-config/` (recursively, including `snippets/`) →
  `<vault>/.obsidian/` only if the destination does not exist.
  Friend's customisations are preserved on subsequent syncs.
- Copies `minder-memory.template.md` → `<vault>/minder-memory.md` only if missing.
- Detects missing recommended community plugins and prints install
  instructions.

To reset both to engine defaults, run `seed.sh --force`. It backs up
the existing `.obsidian/` to `.obsidian.backup-{ts}/` first.

## Engine constraints honoured

- `useMarkdownLinks: false` and `newLinkFormat: shortest` — required so
  Obsidian preserves the `[[wikilink]]` format that Minder Memory skills emit and
  parse. Changing these will break round-trip with `/minder:mem:process` and
  `/minder:mem:maintain`.
- `propertiesInDocument: source` — keeps frontmatter as YAML text in the
  editor. Properties UI is still available via the panel but does not
  auto-rewrite the document. This matters because engine skills are
  strict about frontmatter format and Obsidian's Properties UI normalises
  keys, quotes, and array styles in ways that surface as
  `process-compatibility` clarifications.
- `userIgnoreFilters` excludes from search, graph, and Quick Switcher:
  `_system/state/` audit files (`log_*`, `PROCESSED`, `BATCH_LOG`,
  `*.jsonl`), `_system/scripts/`, `_system/docs/`,
  `_system/agent-lens/`, registries (`PEOPLE`, `PROJECTS`, `TAGS`,
  `CONCEPTS`, `AUDIENCES`, `DOMAINS`, `SOURCES`, `AGENT_LENSES`),
  views (`INDEX`, `HUB_INDEX`, `CONSTITUTION_INDEX`),
  `_sources/processed/`, `*.template.md`, `integrations/`,
  `__pycache__/`, all `README.md`. The Bookmarks pane provides
  one-click access to anything important that's filtered out.

## What's NOT shipped

- `workspace.json`, `workspace-mobile.json`, `cache/`, `.trash/`,
  `.obsidian.backup-*/` — per-device state. Listed in repo
  `.gitignore` so friend's Obsidian state never leaks back upstream.
- Community plugin source code. Friends install plugins themselves;
  `community-plugins.json` lists the IDs so auto-enable kicks in on
  first launch after install.
