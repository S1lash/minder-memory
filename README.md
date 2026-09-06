# minder-memory

> **Your second consciousness.** Voice in, structured memory out.
> Self-hosted, privacy-first, lives in your git repo.

A personal knowledge system that thinks alongside you. You speak,
record, journal — minder-memory ingests it, files it into structured
records, distills patterns into knowledge, and surfaces what you'd
otherwise miss: stalled threads, drift between your stated values
and actual behaviour, cross-domain connections that re-shape how
you think.

Three things make it different from a notes app:

- **It carries context across months.** Your records, decisions, and
  open threads stay live and queryable. Past you informs present you.
- **It has a constitution.** Your axioms, principles, and rules are
  first-class — and the engine watches whether your decisions actually
  follow them.
- **It's yours.** A single git repo. Records, knowledge, and
  constitution stay where you keep them — on your machine, plus your
  private remote if you push there. The engine itself never pushes
  and makes no outbound calls beyond the Claude API (which it uses to
  process the text you ask it to). See `docs/privacy.md` for the full
  data flow.

## What it looks like

**Daily.** Open the Obsidian vault. Your dashboard (`minder-memory.md`) shows
focus snapshot, open threads, today's clarifications, recent meetings
and observations, active projects, people you track. Click into any
record — local graph reveals who, what, when, and which principles
were in play.

**Capture.** Speak. Drop a transcript into the inbox. Run
`/minder:mem:process` from Claude Code. The engine slots it into records,
links the right people and projects, captures principle candidates,
opens follow-up threads — overnight if you want, autonomously.

**Reflect.** Switch to a graph preset — *People web*, *Decision
lineage*, *Project landscape*. See your week as a network. Run
`/minder:mem:lint` (nightly by default) to surface drift. Resolve
clarifications when convenient.

**Distill.** When a record-level capture matures into knowledge, it
graduates into PARA notes. When a captured behaviour pattern stabilises
into a value, it graduates into the constitution. Both transitions
are owner-gated; the engine never silently elevates.

## Quickstart (10 minutes)

```bash
# 1. Create your own Minder Memory repo from this template
#    Replace <maintainer>/minder-memory with this repo's own URL
gh repo create my-minder-memory --template <maintainer>/minder-memory --private --clone
cd my-minder-memory

# 2. Install the Claude Code integration + Obsidian vault config
bash integrations/claude-code/install.sh

# 3. Open Claude Code in the repo and run:
#    /minder:mem:bootstrap
#    /minder:mem:resolve-clarifications

# 4. Open Obsidian → Open folder as vault → zettelkasten/
#    Install three community plugins (Dataview, Tasks, Front Matter
#    Title) — instructions print on first run.
```

That's the whole setup. From here, the daily flow is:

- `/minder:mem:process` — voice transcripts in `_sources/inbox/` → records
- `/minder:mem:lint` — nightly drift detection (auto-scheduled)
- `/minder:mem:agent-lens` — outside-view observations (auto-scheduled)
- Open the Obsidian vault for orientation, review, and reading

Full walkthrough: `docs/onboarding.md`.
Daily use manual (hotkeys, graph presets, recipes):
`integrations/obsidian/guide.md`.

## What you get

- **Engine** (`integrations/claude-code/`) — rules, slash commands,
  skills that read and write your vault.
- **Obsidian UI** (`integrations/obsidian/`) — vault config, dashboard,
  graph presets, bookmarks, visual cues per note type.
- **Vault layout** (`zettelkasten/`) — three layers (records, knowledge,
  hubs) plus constitution, registries, and runtime state.
- **Pipeline scripts** (`zettelkasten/_system/scripts/`) — Python
  workers behind the skills (constitution regen, evidence-trail
  compactor, candidate buffers, format autofix, manifest emission).
- **Sync tooling** (`scripts/sync_engine.sh`, `/minder:mem:update`) — pull
  engine updates without touching your data.

## Run it on a schedule

Five engine-shipped scheduler prompts make Minder Memory largely autonomous:

| Prompt | Cadence | What it does |
|---|---|---|
| `process-scheduled.md` | ≥ 3× per day | Ingest new transcripts |
| `agent-lens-nightly.md` | 03:00 daily | Run due outside-view lenses |
| `lint-nightly.md` | 05:00 daily | Invariant scans + auto-resolve safe clarifications |
| `content-tick.md` | 06:00 Tuesdays | Keep living post drafts alive |
| `roles-nightly.md` | 07:00 daily | Run due standing roles |

You show up for the human-judgment work; the engine handles the rest.
Setup: `docs/scheduling.md`.

## Privacy & data ownership

Your data is your git repo. Where things live, what travels where, and
what stays local — `docs/privacy.md`.

## Updates

Pull engine improvements with `/minder:mem:update` (interactive Claude
skill) or `scripts/sync_engine.sh` (CI / power users). Your records,
constitution, and registries are never touched by updates. Release
notes: `docs/CHANGELOG.md`.

## Hacking on the engine

Improvements to skills, scripts, the engine pipeline, or the Obsidian
integration are welcome. Read `CONTRIBUTING.md` and
`.claude/CLAUDE.md` for the engine boundary, conventions, and
verification commands.

## License

MIT — see `LICENSE`.
