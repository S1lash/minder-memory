# Pulling engine updates from upstream

Your data stays yours. Engine updates flow upstream → your repo.
Two entry points:

- **`/minder:mem:update`** — interactive Claude skill (recommended default).
  Detects local engine customisations, asks per-file before overwriting,
  applies migrations in order, surfaces follow-ups (re-run install.sh,
  regen constitution view, run tests).
- **`scripts/sync_engine.sh`** — non-interactive shell script (CI /
  power users). Same manifest, no prompts. See «Routine sync (script —
  CI / power users)» below.

## One-time setup

```bash
git remote add upstream https://github.com/<maintainer>/minder-memory.git
```

Replace `<maintainer>/minder-memory` with the actual upstream URL — the
repo you cloned the template from.

## Routine sync (skill — recommended)

In a Claude Code session:

```
/minder:mem:update
```

The skill walks you through VERSION delta, pending migrations,
divergence detection (per-file ask if you customised an engine path
locally), and proposes a commit. It does not push — run `/minder:mem:save`
afterwards.

## Routine sync (script — CI / power users)

```bash
bash scripts/sync_engine.sh             # fetch + apply
bash scripts/sync_engine.sh --dry-run   # preview changes only
bash scripts/sync_engine.sh --self-heal # repair the script itself, then apply
```

What the script does:

1. `git fetch upstream main`.
2. Reads `.engine-manifest.yml`. For each `engine:` path, runs
   `git checkout upstream/main -- <path>` to overwrite local engine
   files.
3. Skips `template:` paths — those seeded once at clone time and are
   now your data (e.g. your `SOUL.md`, your `PEOPLE.md`).
4. Checks its own post-conditions: at least one engine path really
   resolved upstream, and `integrations/VERSION` really moved to what
   upstream ships. A run that changed nothing is a broken run, not an
   up-to-date one, and the script refuses to print «done» over it.
5. Removes the paths the manifest lists as `retired:`, through
   `scripts/retire_paths.py`. A sync copies what upstream *has*; it
   cannot express what upstream no longer has, so without this step a
   module the engine deleted would sit on your clone forever. It only
   ever deletes what the manifest names, and refuses outright if a
   retired path falls inside owner space.
6. Runs any pending migrations through `scripts/run_migrations.py`,
   which records every attempt in `.engine-migrations.jsonl` (commit
   it). Each migration declares its kind: a `structural` failure stops
   the update, a `heal` failure — a repair of existing data — is
   recorded and retried next time, never blocking.
7. Prints a recap with the version delta.

If you have local changes inside any engine path, the script aborts
with `error: engine paths have uncommitted changes`. Commit or stash
first, then re-run. A path that is dirty but already identical to
upstream is not an abort — there is nothing there to lose.

When the dirty path is `scripts/`, that is the update machinery having
repaired itself, and the commit that clears it should contain nothing
else: `git add scripts && git commit`. Your notes must not go into that
commit — a `git add -A` here sweeps whatever you had open into a commit
about the engine, and untangling it later costs more than the update did.

### When the sync itself is broken

The update machinery ships through the update, so a clone carrying a
broken copy cannot receive its own repair the normal way. If the script
reports that **none** of the engine paths were found upstream, that is
what happened — recover with either:

```bash
/minder:mem:update                              # the skill repairs scripts/ first, always
bash scripts/sync_engine.sh --self-heal  # the script equivalent
```

Both restore `scripts/` from the remote before doing anything else, then
proceed with the repaired copy.

Restoring means making `scripts/` match upstream in both directions:
what upstream ships is written, and what upstream has since dropped — a
retired migration, a helper that moved — is removed. The removal runs on
**every** sync, not only under `--self-heal`, because a clone old enough
to need recovering runs its own older updater: that one restores
`scripts/` and re-runs the restored script without passing the flag on,
so anything the new script did only under the flag would never happen on
the clone that needs it. A copy-only restore leaves those files behind,
`scripts/` then differs from upstream forever, and every later run
refuses the tree as dirty.

## The version floor

The migration chain starts at `031`; a clone below `0.69.0` cannot jump
straight to the current engine, and the sync refuses rather than applying
migrations that assume a shape the clone never reached. The path is two
steps, and the refusal prints them:

```bash
bash scripts/sync_engine.sh --self-heal --branch release/0.69.0   # to the floor release
git add -A && git commit -m "engine 0.69.0"                       # what /minder:mem:update does for you
bash scripts/sync_engine.sh                                       # then to the current one
```

`--self-heal` on the first step matters: it puts that release's own update
machinery in `scripts/` before running it. Without it `scripts/` holds the
newer copy from the refused attempt, and the sync refuses the tree as dirty.

## After a sync

- Re-install the Claude Code symlinks (some skills may have been
  renamed): `bash integrations/claude-code/install.sh`. This step also
  invokes `integrations/obsidian/seed.sh` to seed `<vault>/.obsidian/`
  and `<vault>/minder-memory.md` if missing — engine improvements to the
  Obsidian config never overwrite your live `.obsidian/` (run
  `seed.sh --force` if you want engine defaults back, with auto-backup).
- Run the test suite: `pytest zettelkasten/_system/scripts/tests/`.
- Review the diff: `git status` then `git diff`.
- Commit the engine update: `git add -A && git commit -m "engine sync"`.

## Customizing engine behaviour

If you want to override an engine prompt or script for your instance,
**don't edit the engine path directly** — the next sync will overwrite
your change. Instead:

- For Claude rules / commands / skills: edit your local
  `~/.claude/{rules,commands,skills}/` file after install. The
  installer respects existing files (it backs them up before
  symlinking, but you can replace the symlink with a real file).
- For system prompts that the engine reads from `_system/`: copy the
  engine file to a sibling path under `2_areas/personal/`, edit there,
  and update your `~/.claude/CLAUDE.md` to @-reference your version.
- For deeper changes you'd like everyone to benefit from: contribute
  upstream — see `CONTRIBUTING.md`.

## What is NOT pulled

`sync_engine.sh` deliberately leaves your data alone. It will never
touch:

- `_records/` — your meeting and observation logs.
- `_sources/` — your raw transcripts (inbox + processed).
- `1_projects/`, `2_areas/`, `3_resources/`, `4_archive/`,
  `6_posts/` — your knowledge notes (the PARA layout, except the
  README explainers).
- `0_constitution/{axiom,principle,rule}/` — your personal principles.
- `_system/SOUL.md`, `long-form-playbook.md`,
  `decision-advisory-playbook.md`, `TASKS.md`,
  `CALENDAR.md`, `POSTS.md`, and the registries (`PEOPLE.md`,
  `PROJECTS.md`, `TAGS.md`, `SOURCES.md`, `AUDIENCES.md`,
  `DOMAINS.md`) — each seeded once from its `.template` sibling and
  yours from then on.
- `_system/state/` and `_system/views/` — runtime state, regenerated
  by skills.
- `_system/roles/<id>/` — your roles, their state and their logs
  (the `_`-prefixed engine files beside them *are* pulled).

The authoritative list is `.engine-manifest.yml`: `engine:` is what a
sync overwrites, `template:` is what it seeds once and never touches
again, `exclude:` never ships at all.

If you ever want to reset a `template:` file back to the upstream seed
(e.g. you blew up `SOUL.md`), do it manually:

```bash
git checkout upstream/main -- zettelkasten/_system/SOUL.template.md
mv zettelkasten/_system/SOUL.template.md zettelkasten/_system/SOUL.md
```

