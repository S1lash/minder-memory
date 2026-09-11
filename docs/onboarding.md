# Onboarding — your first 30 minutes

After this guide you'll have:

- A vault opening cleanly in Obsidian (your daily UI) with a dashboard,
  graph view, hotkeys, bookmarks, and visual cues per note type.
- A populated `SOUL.md` (your identity, focus, working style) and
  registries (people, projects) seeded from your existing context.
- A clarifications queue you've walked through, resolving anything
  bootstrap was uncertain about.
- An autonomous schedule catching drift while you sleep — ingestion
  through the day, lenses and lint overnight, and optionally the
  content and roles ticks.

Two shell commands by hand: clone, then `install.sh`. Everything else
is Claude Code skills — `/minder:mem:bootstrap` first, then the daily flow.

If you only have 5 minutes: do steps 1–2, then `/minder:mem:bootstrap`.
You'll have a working system. The rest is enrichment.

## 1. Clone

Replace `<maintainer>/minder-memory` with the URL of the repo you are reading
this in — the one whoever shared it with you pointed you at.

```bash
gh repo create my-minder-memory --template <maintainer>/minder-memory --private --clone
cd my-minder-memory
```

You'll need an `upstream` remote later to pull engine updates, but you
don't have to add it now — `/minder:mem:update` (step 8) will offer to add it
interactively the first time you run it. Manual:

```bash
git remote add upstream https://github.com/<maintainer>/minder-memory.git
```

See `docs/upstream-sync.md` for the full engine-update flow.

> **Windows note.** Windows filesystems forbid colons (and a few other
> characters) in file names, and some recorder tools — Plaud in
> particular — name their export folders with ISO timestamps like
> `2026-04-29T14:09:30Z`. The engine handles this for you: any
> non-portable name dropped into `_sources/inbox/` is automatically
> renamed to a Windows-safe form (`2026-04-29T14-09-30Z`) when
> `/minder:mem:process` or `/minder:mem:save` runs, before any links to it are
> created. You don't need to rename anything by hand. If an export tool
> refuses to unpack a colon-named folder on Windows, let your unzip tool
> rename it however it wants — the engine normalises it on pickup.

## 2. Install the Claude Code integration

```bash
bash integrations/claude-code/install.sh
```

Then add to `~/.claude/CLAUDE.md` if not already present:

```
## Constitution Capture — Global Hook
- @~/.claude/rules/constitution-capture.md

## Zettelkasten (Minder Memory) — Personal Knowledge Base
- @~/.claude/rules/minder-memory.md
```

## 3. (Optional but high-leverage) Drop your backlog and write a profile

If you have an existing corpus — voice-recorder transcripts, voice
notes, journal exports, past Zettelkasten dumps — copy them into the
matching subfolder of `_sources/inbox/`. The skeleton ships with a
universal starter set of sources defined in
`zettelkasten/_system/registries/SOURCES.md`:

- `plaud/` — Plaud voice-recorder transcripts (preferred summary +
  fallback transcript layout)
- `voice-notes/` — generic voice-note transcripts (any recorder)
- `claude-sessions/` — Claude Code session recaps captured via
  `/minder:mem:recap`
- `notes/` — plain Markdown notes you drop in by hand
- `crafted/` — hand-written long-form documents (also where
  `/minder:mem:recap --crafted` saves verbatim artifacts like toasts, letters,
  posts)
- `resolve-clarifications/` — knowledge you state while answering
  `/minder:mem:resolve-clarifications`; the skill files it here, you don't

If your input does not match any of the starter sources, run
`/minder:mem:source-add` after install — it registers a new source-type
declaratively (one row in SOURCES.md + paired inbox/processed
folders). No code changes required.

If you want a high-quality identity seed, copy
`_sources/inbox/describe-me/PROFILE.template.md` to `PROFILE.md`
(same folder) and fill the copy — keep the template pristine. The
template suggests a workflow of pasting your transcripts into a
separate ChatGPT/Claude session and asking it to fill the template
for you.

Both steps are optional. If you skip them, bootstrap will detect that
and offer alternatives (interview-only path, or proceed with empty
backlog).

## 4. Run /minder:mem:bootstrap

In a Claude Code session opened in this repo:

```
/minder:mem:bootstrap
```

The skill is the actual orchestrator from here. It will:

- Run pre-flight checks (transcripts present? profile present? install
  sane?) and ask you what to do for any missing inputs.
- Scan your raw corpus in chunks via parallel subagents — extracting
  people, projects, hub candidates, principle candidates, open threads.
- Seed `SOUL.md`, `PEOPLE.md`, `PROJECTS.md`, `OPEN_THREADS.md`,
  `CURRENT_CONTEXT.md`, `INDEX.md` (surface catalog of knowledge +
  archive + constitution + hubs), and the principle-candidates buffer.
- Surface decisions to `_system/state/CLARIFICATIONS.md` for your
  review.
- Print an exit summary with explicit next steps and timing
  expectations.

Follow the instructions in the exit summary. Bootstrap is idempotent —
re-run anytime as your inputs evolve.

## 5. Review the clarifications queue

After bootstrap (and after every `/minder:mem:process`, `/minder:mem:lint`, or
`/minder:mem:maintain` run that surfaces items), run:

```
/minder:mem:resolve-clarifications
```

The skill pre-syncs against `origin` (so a queue resolved on another
device doesn't waste your attention), clusters open items by theme,
presents one round at a time with full meeting context + verbatim
quotes inline, pre-forms hypotheses against your constitution, and
applies confirmed resolutions in place. After your rounds it
auto-refreshes derived views (`/minder:mem:regen-constitution` if you
accepted principle candidates; `/minder:mem:maintain` if you touched
registries / hubs) and reminds you to run `/minder:mem:save`. Designed for
offline-style review — you do not need to recall meeting context from
memory; the skill reminds you.

## 6. Save your work — `/minder:mem:save`

When you are done for now, run:

```
/minder:mem:save
```

The skill stages your changes by category (records, knowledge,
registries, state), proposes a commit message, shows a summary, asks
for confirmation, then commits and pushes to `origin`. No git plumbing
required.

## 7. Pull data on a second device — `/minder:mem:sync-data`

If you work from more than one machine (laptop ↔ desktop ↔ phone via
git push), run before any work session:

```
/minder:mem:sync-data
```

This pulls the latest from your `origin` with rebase, refusing to
auto-merge conflicting prose and handing off to you if anything is
ambiguous. Recommended before `/minder:mem:process`, `/minder:mem:lint`, and
`/minder:mem:maintain` on any non-canonical device.

## 8. Pull engine updates — `/minder:mem:update`

When the upstream skeleton (the public `minder-memory` repo) ships new
engine code, prompts, or migrations, pull them:

```
/minder:mem:update
```

Different from `sync-data`: this targets the `upstream` remote (engine
maintainer) instead of `origin` (your data backup). It detects local
customisations on engine files, asks per-file what to do on
divergence, and runs migrations in order. Your data is never touched.

## 9. (Optional) Schedule autonomous processing

Five ready-made scheduler prompts ship in
`integrations/claude-code/scheduler-prompts/` (canonical cadence table +
exact cron in `docs/scheduling.md`):

- `process-scheduled.md` — pre-sync → `/minder:mem:process` → `/minder:mem:maintain` →
  `finalize-tick.sh scheduler/process`.
  Recommended cadence: 3× per day (e.g. cron `0 9,14,19 * * *`).
- `agent-lens-nightly.md` — pre-sync → `/minder:mem:agent-lens --all-due` →
  `finalize-tick.sh scheduler/agent-lens`. Recommended cadence: 1× per
  night (e.g. cron `0 3 * * *`). The skill filters lenses by per-lens
  cadence — nightly tick ≠ nightly lens runs.
- `lint-nightly.md` — pre-sync → `/minder:mem:lint` (which dispatches
  `/minder:mem:resolve-clarifications --auto-mode` inline via Step 7.5)
  → `finalize-tick.sh scheduler/lint`. Recommended cadence: ~2 h after
  agent-lens (e.g. cron `0 5 * * *`).
- `content-tick.md` — pre-sync → `/minder:mem:content --maintain` →
  finalize. Recommended cadence: weekly (e.g. cron `0 6 * * 2`, Tuesday).
- `roles-nightly.md` — pre-sync → `/minder:mem:roles` → finalize. Recommended
  cadence: 1× per day (e.g. cron `0 7 * * *`). Only needed once you have
  roles; the tick is a no-op with none. The skill runs only the roles whose
  own cadence has elapsed.

The daily ticks are offset from each other (lens production isolated from
lint+resolve consumption; roles last, so what a role writes is processed the
same morning) — see `docs/scheduling.md` for the offset rationale. To create
new lenses use `/minder:mem:agent-lens-add`, and new roles `/minder:mem:role:add` — both
owner-driven, neither scheduled.

You do not paste these bodies into your scheduler. Each routine gets a
one-line **loader** instead — it points at the file above, so the tick reads
its contract from the repository at run time and engine updates reach your
schedules without you re-pasting anything. The loaders are in
`docs/scheduling.md` → «Plug-in — Claude Code `/schedule`». Any runner that
can launch a Claude Code session with this repository as its working
directory works: Claude Code `/schedule`, GitHub Actions cron, a host crontab
calling `claude` headless.

## 10. (Optional) Tune how the assistant talks to you

After install the assistant already answers you **conclusion-first, no fluff,
and stays critical** by default — the shipped *communication baseline*. And it
already works *for you* rather than refereeing between you and the world — the
shipped *advisory baseline*: it treats a claim from someone with a stake in the
outcome as a claim rather than a fact, builds the decision criteria from your
situation before adopting anyone else's list, and checks your own criteria
against how you actually live rather than one vivid week. You don't have to do
anything for either.

To make it yours: put how you like praise and criticism in
`zettelkasten/_system/SOUL.md → ## Context for Agents`, your recipe for long
pieces (reports, audiobooks, debriefs) in
`zettelkasten/_system/long-form-playbook.md`, and how you want a decision with
someone else's interest in it worked through in
`zettelkasten/_system/decision-advisory-playbook.md`. Both playbooks load on
demand — only for an actual long piece or an actual decision — so an ordinary
answer never pays for them. All three ship with filled examples.

The assistant also *learns* your style over time through the `cognitive-model`
lens, which is **on by default**. Every other Monday it reads your own
reflections and proposes "you seem to want X" for you to approve via `/minder:mem:lint`
— it only appends to your review buffer and never changes your constitution on
its own. It fills your cognitive-model hub
(`5_meta/mocs/hub-cognitive-model.md`). To populate it now instead of waiting for
the next cycle, run `/minder:mem:agent-lens --lens cognitive-model`. To turn it off, set
its row to `draft` in `_system/registries/AGENT_LENSES.md` (note: a later
`/minder:mem:update` re-applies the platform default of `active`). See `docs/privacy.md`
for exactly what it reads and produces.

### Required GitHub repo setting — auto-delete head branches

Before relying on Cloud Routines (Claude Code `/schedule`), enable:

**GitHub repo → Settings → General → Pull Requests → ☑ Automatically
delete head branches**

In Routines mode `finalize-tick.sh` pushes each tick's commit to a
sandbox branch (the Routines git proxy refuses direct push to `main`),
then creates and squash-merges a PR. The Routines proxy also refuses
`git push origin --delete <branch>`, so deleting the sandbox branch
after merge must happen on GitHub's side via this setting. Without it
on, every Routines tick leaves a leftover `claude/*` branch on origin
and they accumulate.

This is a one-time toggle per repository. Local cron / launchd setups
do not strictly need it (LOCAL delivery mode pushes directly to `main`
with no PR involved), but enabling it does no harm.

### Push credentials

The scheduler runs in a non-interactive environment, so it cannot
prompt for SSH passphrases or 2FA. Set up one of:

- **SSH key without passphrase** stored on the scheduler host, added
  to your GitHub account.
- **Personal Access Token** with `repo` scope, configured as the
  remote URL:
  `git remote set-url origin https://<TOKEN>@github.com/<you>/my-minder-memory.git`.
- **Platform-managed credentials** — Claude Code cloud `/schedule`
  inherits your authenticated GitHub session (no extra setup).

Verify before relying on the schedule: run the prompt body manually
once in the scheduler environment and confirm:

1. The `[scheduled]` commit lands on `origin/main` (via direct push in
   LOCAL mode, or via squash-merged PR in ROUTINES mode).
2. The sandbox branch (Routines only) is gone from origin after the
   tick — proves the auto-delete setting is on and working.

Full design — `docs/scheduling.md`.

## 11. (Optional) Stand up a role

A **role** is a standing job you describe in your own words and the system runs
on a schedule without you — «every Monday check whether anything on the board
moved and tell me what did not», «watch my notes for the weeks I stop mentioning
sleep». It reads your base as context, keeps its own notes between runs, and can
reach an outside service if you give it a credential.

```
/minder:mem:role:add
```

Describe what you want in plain language. The concierge does the rest: it asks
what you would want to know without having to ask, probes your actual notes to
show you what the role would have found last week, argues for a stronger version
when your data supports one, and writes the role file itself. You never see a
path, a schedule grammar, or a config field.

Before it declares the role done it validates the config, makes a real call
against any service the role needs, and does a trial run — so a role that cannot
work is fixed with you in that conversation, not at 07:00 in silence.

The rest of the family:

- `/minder:mem:role:list` — what you have, what each watches, when it last ran.
- `/minder:mem:role:ask` — ask a role what it knows; it answers from its own notes.
- `/minder:mem:role:edit` — change what it does or when, or pause it.

Two things worth knowing up front. A role writes only where its definition says
it may — everything else it touches is put back after the run and shown to you,
with one exception: a file that was **already changed before that role started**
is reported instead, because putting it back would erase work the role did not
write. The report says whose it was, yours or an earlier role's in the same run.
And a role that reaches an outside service needs a credential: the concierge
captures it into an encrypted store and generates the one key that opens it.
That key goes into the environment config of your `minder-mem-roles` schedule, never
into the repo, and a lost key means entering those credentials again —
`docs/scheduling.md` has the setup, including the one Python package a base with
credentials needs. `docs/privacy.md` says what the encrypted store trades away,
and what the write check does and does not hold against.

Roles run from the `minder-mem-roles` tick in §9. Without that schedule they exist but
never fire.


## Reference

- **`integrations/claude-code/skills/minder-mem-bootstrap/SKILL.md`** — the
  canonical playbook the skill executes. Read this if you want to
  understand exactly what bootstrap does and why.
- **`docs/upstream-sync.md`** — engine update flow, deeper details
  (`/minder:mem:update` is the friendly wrapper).
- **`docs/obsidian.md`** — opening the vault in Obsidian; what the
  Minder Memory-shipped `.obsidian/` config does and what to avoid.
- **`integrations/claude-code/skills/minder-mem-{save,sync-data,update}/SKILL.md`**
  — git-flow skills.
- **`zettelkasten/_system/docs/SYSTEM_CONFIG.md`** — full system spec.
- **`zettelkasten/5_skills/`** — engine reference cards for a hand-picked subset
  of the skills. They are a convenience, not a contract: the SKILL under
  `integrations/claude-code/skills/{skill}/SKILL.md` is the source of truth, and
  a skill without a card is no different from one with it. See
  `zettelkasten/5_skills/README.md`.
