---
name: minder:mem:update
description: >
  Pull engine updates from `upstream` (the public skeleton repo) into
  the owner's clone — interactive wrapper around `scripts/sync_engine.sh`.
  Reads `.engine-manifest.yml`, fetches upstream, computes VERSION
  delta, lists pending migrations from `scripts/migrations/`, detects
  local divergence on engine paths (where the owner customised), shows
  a per-path diff preview, asks for confirmation before overwriting,
  applies migrations in order, and surfaces follow-ups (re-run
  install.sh, regen constitution view). Never touches `template:` or
  data paths. Default UX for non-technical owners; bash script remains
  for CI / power users. Closes with a short, personalized benefit-first
  digest — what the update actually delivers for THIS owner, aligned to
  how they read, honest about marginal / technical changes, with detail
  on request.
disable-model-invocation: false
---

# /minder:mem:update — Pull engine updates from upstream

Engine = code, prompts, scripts, spec docs. Friend's clone owns engine
paths in their `main`, but they flow upstream → friend via this skill.
Data (records, knowledge, registries, constitution principles) is never
touched.

`scripts/sync_engine.sh` does the same thing without prompts — use that
in CI or when scripting. This skill is the interactive default.

**Documentation convention:** on any edit to this SKILL, follow
`_system/docs/CONVENTIONS.md` — the file describes current behaviour,
no version / phase / rename-history narratives.

## Arguments

`$ARGUMENTS`:
- `--remote <name>` — default `upstream`
- `--branch <name>` — default `main`
- `--dry-run` — show plan, apply nothing
- `--yes` — skip per-path confirmations (still aborts on dirty engine
  paths or unknown migrations)
- `--no-migrations` — apply file overwrites only, skip running scripts
  under `scripts/migrations/`

## Preconditions

1. Repo root has `.engine-manifest.yml` and `integrations/VERSION`.
2. No pipeline lock present under `_sources/` — `.processing.lock`,
   `.maintain.lock`, `.lint.lock`, `.agent-lens.lock`, `.content.lock`,
   `.roles.lock`, `.resolve.lock`. Abort naming the one found.
3. Working tree clean on engine paths (script-style requirement —
   uncommitted engine edits would be lost). Say the wider version out loud
   before an update that crosses 1.0.0: migration 032 rewrites the product
   name in **every file in the clone**, engine and owner data alike, including
   notes the owner has open and has not committed. That is the contract and it
   is reversible — git holds the previous text under the old name — but an
   owner who is told afterwards reads it as data loss. Ask them to commit what
   they are in the middle of; if they proceed anyway, carry the migration's own
   count of what it rewrote unsaved into the digest at Step 8.
4. `upstream` remote configured. If missing — offer to add it
   interactively:
   ```
   No `upstream` remote. Add it now? Default URL:
     https://github.com/<your-org>/minder-memory.git
   [y] add this URL   [u] enter custom URL   [n] abort
   ```

## Pipeline

### Step 1 — Fetch upstream

```
git fetch <remote> <branch>
```

### Step 1.5 — Repair the updater before trusting it

**Runs on every update, before anything else is read.** Land `scripts/` from
upstream first, then re-read the manifest, the migration list and the ledger
helpers from the copy that just arrived.

```bash
git checkout <remote>/<branch> -- scripts/
```

Why this is unconditional and first. The engine's update machinery ships
*through* the update. A clone carrying a broken copy of that machinery can
never receive its own repair by the normal path — which is exactly what
happened to a Windows clone whose `sync_engine.sh` silently applied nothing for
weeks, including the fix for itself. Refreshing `scripts/` before reading it
makes the updater self-repairing from **any** prior version, permanently. That
property is the point; the specific bug that revealed it is not.

This step is safe to do blind:

- `scripts/` is engine surface end to end — it holds no owner data, so there is
  nothing to lose by taking upstream's copy.
- Step 4's divergence detection still runs over it afterwards. A friend who
  deliberately customised something under `scripts/` sees the same
  keep-or-overwrite prompt they would have seen anyway, one step later.
- `git checkout <ref> -- <path>` takes no `<ref>:<path>` argument, so it is
  immune to the MSYS path rewriting that breaks the bash script's own manifest
  reader on Git Bash. This skill is therefore the recovery path for a clone
  that the script cannot reach.

If the checkout fails, say so plainly and stop: an updater that cannot update
itself must not proceed to update everything else.

### Step 2 — VERSION diff

Read `integrations/VERSION` from `HEAD` and from `<remote>/<branch>`.

| Local | Upstream | Action |
|---|---|---|
| same | same | print «engine already current», exit 0 |
| local > upstream | (impossible in friend clone) | warn, ask explicit confirm to proceed |
| local < upstream | upstream ahead | proceed |
| local < `0.69.0` | any | **the floor** — see below, do not proceed |

**The version floor.** The migration chain starts at `031`; a clone below
`0.69.0` never reached the shape those migrations assume, so the update is two
steps and never one. Run the first step as a command, then start this skill
again from Step 1:

```bash
bash scripts/sync_engine.sh --self-heal --branch release/0.69.0
```

`--self-heal` puts that release's own `scripts/` in place before running it;
Step 1.5 has just landed the CURRENT copy, which the floor release's sync would
refuse as a dirty tree. `scripts/lib/version_floor.py` is the one home of the
floor version and the branch name; the bash script refuses the same jump.

### Step 3 — Migration inventory

List `scripts/migrations/*.sh` on `<remote>/<branch>` not
present locally — those between local VERSION and upstream VERSION are
candidates. Read each migration's first 30 lines (header comment) to
extract the human-readable summary.

Ask the runner what is pending rather than reading a marker file directly:

```bash
python3 scripts/run_migrations.py --dry-run --json
```

It returns `{"pending": N, "ran": [{"name", "kind", "outcome"}, ...]}`. The
ledger (`.engine-migrations.jsonl`, with the legacy flat
`.engine-migrations-applied` folded in) is its business, not this skill's — one
owner of "what has run here". Each entry carries the migration's declared
`kind`, which is what Step 6 acts on.

Render:
```
Engine update: 0.1.0 → 0.3.0

Pending migrations:
  • 0001-example-structural.sh   (kind: structural)
      One-line summary from the migration's header comment.

  • 0002-example-heal.sh         (kind: heal)
      One-line summary from the migration's header comment.

[y] proceed with full update   [m] migrations only   [f] file copy only
[d] show full migration scripts   [n] abort
```

### Step 4 — Local divergence detection

For each path in `.engine-manifest.yml` `engine:` section, compute
`git diff --name-only HEAD <remote>/<branch> -- <path>`. Cross-check
against owner's local commits touching that path
(`git log <merge-base>..HEAD -- <path>`).

Three sub-cases per path:

| Local commits touch path | Upstream changed path | Meaning | Default |
|---|---|---|---|
| no | no | unchanged | skip silently |
| no | yes | clean upstream update | overwrite |
| yes | no | local-only customisation | keep local, no action |
| yes | yes | **DIVERGENCE** | ask owner |

For divergence cases — render per-path:
```
DIVERGENCE: integrations/claude-code/skills/minder-mem-process/SKILL.md
  Local commits:    2 (last: «tweak process step 4 wording»)
  Upstream commits: 5 (since 0.1.0)
  Diff stat (upstream vs local):  +47 -12

  [o] overwrite with upstream  (lose local edits)
  [k] keep local                (skip this file in update)
  [m] open merge tool           (manual three-way)
  [d] show full diff
```

If no `--yes`, owner answers each. With `--yes`, divergence files default
to `[k] keep local` (safe default — never silently lose work).

### Step 5 — Apply file overwrites

For each path marked overwrite:
```
git checkout <remote>/<branch> -- <path>
```

**`.claude/skills/` — pre-clean before checkout.** Upstream ships this path as
a real-file tree; a local clone may hold it as symlinks or, on a Windows clone
(`core.symlinks=false`), as text files masquerading as symlinks. A plain
`git checkout` then aborts on the file→dir type change. When `.claude/skills`
is among the overwrite paths, remove it first so the real-file tree lands
cleanly (it carries no owner data):
```
rm -rf .claude/skills
git checkout <remote>/<branch> -- .claude/skills
```

For each path marked keep — leave local copy.

For each path absent upstream (deleted in upstream) — leave local copy
and note «engine path removed upstream — review and delete locally if
appropriate».

### Step 5.1 — Apply retirements

```bash
python3 scripts/retire_paths.py
```

Step 5 can only copy what upstream HAS. A path upstream no longer has is never
walked, so without this every file the engine ever removed stays on the clone —
dead modules beside live ones, dead tests still collected, a log nothing writes
that still reads as one that stopped.

The helper removes only what `.engine-manifest.yml` lists under `retired:`, and
refuses outright if any of it falls under `exclude:` (owner space). A non-zero
exit means the manifest is wrong, not the clone: nothing was deleted, so report
it and stop rather than proceeding with a half-applied update.

Report what it removed in the closing digest — a file disappearing from an
owner's clone is something they should read about, not discover.

### Step 6 — Apply migrations

If `--no-migrations` — skip.

Otherwise, hand the whole chain to the runner and **capture its combined
stdout+stderr**:

```bash
out="$(python3 scripts/run_migrations.py 2>&1)"; rc=$?
```

The runner applies each pending migration in order and records the outcome in
the ledger. It acts on the migration's declared `kind`:

| Kind | On failure |
|---|---|
| `structural` | abort the chain, record nothing, exit non-zero — the next update resumes at exactly that migration |
| `heal` | record `partial`, print the failure, **keep going**; retried on the next update |

The `heal` arm is not leniency, it is the fix for a real failure mode: a
best-effort repair of historical data used to abort the whole update and stay
unrecorded, so every future update re-ran it and re-aborted at the same point.
A friend's clone sat unable to update for weeks because of one such repair. A
repair of old data must never be able to block a future engine update.

**Detection-only migrations (soft-nag) — MUST be surfaced, never let scroll past.**
A migration that exits 0 but prints recovery instructions (a `/minder:mem:...` command) is
NOT a failure — it detected a pre-existing backlog it cannot fix itself because
recovery needs the LLM pipeline (classification / repair), not a shell script.
Collect its captured message verbatim into a **Post-update recovery** list for
Step 8. `011`–`014` are exactly this kind: un-aggregated tasks (`011`) / events
(`012`), hub-index drift (`013`), misplaced note fences (`014`). If these are not
surfaced, the owner never runs the backfill and the recovered data stays hidden —
so surfacing them is load-bearing, not optional.

**`018` is the same kind and needs one thing more.** It carries roles built on
the previous shape out of the live path and writes the owner a hand-off — the
mechanical half is done when it exits. What it cannot do is re-create the roles,
because that is a conversation: the assignment is written in the owner's words
and `writes:` is a boundary decided with them, never inferred. Its message
therefore addresses YOU directly and asks you to read the hand-off, offer
`/minder:mem:role:add` per parked role, and run its self-check afterwards. Surface it
and **do the steps it names**, in this same session, after the update finishes.
An owner who is only shown the text will not know their roles are recoverable —
which is the exact failure the migration exists to prevent.

If the runner exits non-zero, a **structural** migration failed:
- The chain is already stopped and nothing after it ran.
- Print: «migration `<name>` failed. Engine files are already overwritten, so
  this clone is in a partial state. Inspect the output above, fix the cause,
  then re-run `/minder:mem:update` — it resumes at that migration.»
- Exit non-zero.

If the runner exits 0 but reported `partial` outcomes, surface each one in the
**Post-update recovery** list for Step 8, naming the migration and what it could
not finish. The update itself succeeded; the owner should know what is still
outstanding, and that it will be retried automatically.

### Step 6.5 — Derived vault docs (already done by the sync script)

`sync_engine.sh` refreshes `<vault>/5_meta/help/` right after the migration
chain — the four files there are copies of engine docs, so an update that
rewrote their sources has to rewrite them too. There is nothing to run here;
this step exists so the reader knows those files moved and why.

It lives in the sync script rather than in this skill because the script is
what BOTH update paths run: this skill wraps it, and a friend using the CLI
directly gets the same convergence. Wiring it here alone would have left the
documented power-user path frozen.

If the sync output carried `warning: vault help docs not refreshed`, put it in
the Step 8 recovery list with the command it names. A stale help doc never
fails an update.

### Step 7 — Follow-up detection

Inspect what changed:

| Pattern in changed files | Recommendation |
|---|---|
| `integrations/claude-code/{rules,commands,skills}/**` changed | «Re-run `bash integrations/claude-code/install.sh` to refresh `~/.claude/` symlinks.» |
| A NEW file added under `_system/docs/**` that install.sh symlinks as a hot rule (git status `A`; today `communication-baseline.md`, `advisory-baseline.md`, `ENGINE_DOCTRINE.md`, `constitution-capture.md`) | «Re-run `bash integrations/claude-code/install.sh` — a new always-on rule shipped and needs its `~/.claude/rules/` symlink plus its `@`-import in the managed block.» A migration may already have done it; say so rather than repeating the ask when `~/.claude/rules/<name>.md` resolves |
| Any file under `0_constitution/` engine paths or constitution tooling changed | «Run `/minder:mem:regen-constitution` to refresh views.» |
| `_system/scripts/**` changed | «Run tests: `pytest zettelkasten/_system/scripts/tests/`.» |
| A NEW file added under `integrations/claude-code/scheduler-prompts/**` (git status `A`) | «A new scheduled job shipped — set up a new `/schedule` routine for it (see `docs/scheduling.md` for the cron slot + its loader prompt).» |
| ANY file under `integrations/claude-code/scheduler-prompts/**` changed (git status `M`) | Run the routine reconciliation below. Do **not** emit a bare «re-paste the prompt» line — the owner cannot act on it without knowing which of their routines it means |

### Step 7.1 — Routine reconciliation (only when a prompt file changed)

A scheduler holds the prompt text it was given, verbatim and forever. So a
changed prompt file reaches a running routine only if that routine reads the
file (a **loader**) — and if it holds a pasted **body**, that copy is now the
older of the two and the tick is running an old release's contract against a
current engine.

**Identify by CONTENT, never by name.** Routine names are the owner's own —
`minder-mem-lint`, `minder-memory: lint (nightly)`, `nightly cleanup`, anything. Matching
on a name the engine invented is how this step silently skips the routine that
needed it most, or edits one that has nothing to do with Minder Memory.

1. List the owner's routines. In Claude Code that is the `RemoteTrigger` tool
   (`{action: "list"}`); load it with `ToolSearch select:RemoteTrigger`. If it
   is unavailable — another runtime, no cloud routines, tool not present — say
   so plainly, list the changed prompt FILES, and stop. Never guess.
2. Classify each routine by its stored prompt text:
   - **Loader** — it names a path under
     `integrations/claude-code/scheduler-prompts/`. Already self-updating;
     report it as up to date and change nothing.
   - **Pasted body** — it matches one of the shipped prompt files (compare
     against each file's content; the best match at high similarity is the
     tick it is, whatever it is called). Report it as stale, naming the
     routine's own name and id **and** which tick it is.
   - **Neither** — not a Minder Memory routine. Leave it entirely alone and do not
     mention it as an action item.
3. **Check every stale routine for owner customisation before touching it.**
   Diff its stored prompt against the shipped file it matched. Anything present
   in theirs and absent from the file is the owner's, and overwriting it is
   data loss — surface what you found and let them decide.

   The case that must never be got wrong is a **credential in the prompt
   body**. The engine's own instruction is that `MINDER_MEMORY_ROLES_KEY` belongs in the
   routine's environment config, but an owner may well have put it in the
   prompt instead, and a blind replace silently kills every role that reaches
   an outside service — with nothing in the failure that points back here.
   So: carry any such line into the new prompt **verbatim**, so the routine
   keeps working, and then tell the owner it would be safer in the environment
   config and offer to help move it. Never print the value back to them, into
   a log, or into a commit — say *that* a credential was found and carried,
   not what it is.

4. Lead with the offer, not with the mechanics. The owner does not need to
   know what a loader is: **«your scheduled routines need updating — want me to
   do it?»** is the whole message, plus which of their routines it touches.
   Explain the how only if they ask. Changing a live schedule is an external
   action — act only on an explicit yes.
5. When switching: replace the prompt content ONLY. Preserve name, cron,
   enabled, environment, model, tool allowlist, sources, notification settings
   and the event uuid — send them back unchanged in the update body. Verify by
   reading the routine back after the write.
6. Prefer proving it once over switching several at a time: convert the
   cheapest routine first, trigger a run, read its log, and convert the rest
   only after that run shows the loader was read and followed.

This procedure is the standing answer for **every** future prompt change, not
just this one. After a routine holds the loader, step 2 finds it already current
and there is nothing to ask — which is the whole point of the loader.

### Step 7.2 — Upgrade checklist (when the update crosses 1.0.0)

When `version_before` is below `1.0.0` and `version_after` is at or above it,
walk `docs/upgrade-1.0.0.md` with the owner, item by item, in order — first the
proofs that the update itself landed (skills, rule, managed block, remote,
clone, dashboard, version), then everything the rename touched that lives
OUTSIDE the repository; every item names what you do on your own, what you
need the owner for, and the proof that closes it. Do the routine environment (item 10) first: until the
credential key is renamed there, every role that reaches an outside service
fails at its next tick. Never print, log or quote a credential value; rename
the key and send the routine back otherwise unchanged. Report the checklist as
a table of items with «closed» / «open — needs the owner: …», and do not call
the update finished while an item is open without the owner having said so.

### Step 7.3 — Post-update self-check

Before the owner is told anything, prove from the filesystem that the update
did what it should have. What an update gets wrong is usually an ABSENCE — a
rule that stopped loading, a skill nothing resolves — and nothing in the tree
announces an absence: every artefact still looks correct. A migration that
succeeded at the wrong thing is recorded `applied` and never runs again, so the
proof has to be gathered now, by the run that made the change.

```bash
python3 scripts/check_update.py            # add --json for the machine-readable report
```

The probes live in that script, not here, for two reasons: a probe described in
a prompt drifts from the one that ran last time, and the literals a rename check
needs cannot live in a file the rename rewrites. It checks the version against
the remote, the managed block, the rule / command / agent links, the skill
count, leftovers and foreign dangling links under the harness home, the residue
grep of `docs/upgrade-1.0.0.md` row 7, conflict markers, the dashboard,
`_sources/`, the roles list and credential store, and the migration ledger.
Each probe answers `ok` / `fail` / `skip`; the exit code is 0 when nothing
failed, 1 when something did, 2 when the check could not run at all.

**Two things the script cannot reach**, because they are read through the
scheduler tool rather than the filesystem — do them yourself, here:

- Read each cloud routine back. The prompt body must name no command under the
  former product namespace, and no environment KEY may still carry the former
  product name or its `_ROLES_KEY` spelling. Never read, print or quote a
  value — only key names.
- Read each `role.md`. Anything in it that names the repository, a path, an
  environment variable or an outside service by a former name is a nuance to
  raise with the owner, not something to rewrite: a role's prose is theirs.

**Judgement.**

- A `fail` is yours to fix once and re-run the script — that is the whole point
  of checking while the change is still in hand.
- Two exceptions you do not act on: a remote that did not answer (nothing local
  fixes an offline host), and a credential that lives outside the repository.
- Never repoint a remote other than the one the engine syncs from.
- A `skip` is not a pass. Say which question could not be asked, and why, if it
  matters to the owner.
- The former name surviving in the places the residue grep excludes is correct —
  say nothing about them.
- `git status` must show only what this update produced. If the rename migration
  rewrote files the owner had not saved, name them; its own output carries the
  count.

**What the owner sees:** one line — «checked everything after the update — all
wired» — plus what you fixed, plus the one thing that needs them, if any. No
probe table, no command output. The evidence is for you; the conclusion is for
them.

### Step 8 — Stage + propose commit

`git add` all overwritten paths + the migration ledger
(`.engine-migrations.jsonl`, and the legacy `.engine-migrations-applied` if the
clone still carries it) + `integrations/VERSION` (if changed). Do NOT push —
push is `/minder:mem:save`'s job.

Render:
```
Engine updated locally.

Files:    <K> overwritten
Skipped:  <D> kept local (divergence)
Migrated: <M> migration(s) applied

Proposed commit:
  engine: update 0.1.0 → 0.3.0

  - <N> engine paths refreshed from upstream/main
  - migrations: 0001-example-structural, 0002-example-heal
  - kept local: integrations/claude-code/skills/minder-mem-process/SKILL.md

Follow-ups:
  • run bash integrations/claude-code/install.sh
  • run /minder:mem:regen-constitution
  • run pytest zettelkasten/_system/scripts/tests/

⚠ Post-update recovery — a migration detected a pre-existing backlog. Run these
  once to recover it (each command re-verifies itself when it finishes; if you
  defer, the nightly /minder:mem:lint keeps surfacing the same gap as a CLARIFICATION,
  so nothing is lost):
  • <verbatim recovery line captured from each soft-nag migration in Step 6, e.g.
    "011: 39 un-aggregated tasks → run /minder:mem:process --reconcile-tasks">
  (Omit this block entirely when no migration emitted a recovery nudge.)

[y] commit now   [m] edit message   [s] stage only, I'll commit
[n] unstage and abort
```

After commit, suggest `/minder:mem:save` for push (skill itself never pushes).

### Step 9 — What arrived for you (personalized benefit digest)

The final, human step. Everything above is plumbing; here the owner
should walk away knowing **what this update gives them** and wanting to
try what is new — not reading a changelog. Minder is already adopted —
this step does not sell the product, it sells the *value that just
landed*.

**When it runs:**
- No-op (already current, nothing applied) → skip entirely.
- `--dry-run` → render as a PREVIEW ("here is what you'd get if you
  update"), present-tense-conditional instead of past-tense.
- `--yes` / non-interactive → still print the digest; only the
  interactive "ask more" prompt is skipped.

**Source — what changed (in this order):**
1. `git show <remote>/<branch>:docs/CHANGELOG.md` — the user-readable
   release notes. Take every `## <version>` entry in the delta range
   (local VERSION < version ≤ upstream VERSION). This is the primary,
   already-benefit-oriented source. Read it from `<remote>/<branch>`,
   not the working copy, so it is correct even if CHANGELOG was
   kept-local at Step 4.
2. Migration summaries from Step 3 + recovery nudges from Step 6 —
   technical detail and one-time actions.
3. Changed engine paths from Step 4 — fallback when a version has no
   CHANGELOG entry (infer feature vs internal from the path).

**Who reads it — align + personalize (reuses the lens reader-alignment
contract).** Read whichever of these exist; a missing file is not an
error, skip it silently:
- `_system/docs/communication-baseline.md` — presentation floor
  (conclusion first, plain language, short, no filler, no flattery).
- `_system/SOUL.md` → "Working Style", "Context for Agents", and
  "Active Goals" / "Current Focus" — how THIS owner reads AND what they
  currently care about (for honest personalization).
- `_system/views/constitution-core.md` — the owner's ai-interaction /
  cognitive principles.

This calibrates PRESENTATION only — it never changes which items you
report or invents value that isn't in the changelog. If a file is
absent or its profile doesn't fit, ignore it and use the floor.

**Stance — sell the benefit, honestly:**
- **New capability / owner-facing feature** → lead with the benefit,
  not the mechanism: "what you can do now" and why it matters. Make it
  vivid enough to want to try, and give the one action that starts it
  (the enable / try command from the CHANGELOG entry). Personalize when
  there is a REAL link to the owner's focus or goals ("you're deep in X
  right now — this is exactly about that") — never force a link that
  isn't there.
- **Technical / internal** (fix, refactor, perf, schema, plumbing) → no
  hype. One plain line on what it means for the owner *if* there is
  owner-relevant meaning ("faster", "more reliable", "no longer loses
  X"); if there is none, fold the rest into a single terse "under the
  hood" line, or omit. Depends on the update.
- **Recovery actions** (soft-nag migrations, Step 6) → frame as "do
  this once to reclaim X" — benefit-first but honest that it's a
  one-time chore.

**Honesty guard — load-bearing (this is `principle-ai-interaction-012`,
not marketing).** Sell REAL value vividly; never manufacture excitement
for a marginal change, never oversell a benefit that isn't there. A
minor update is stated as minor. Personalization is a true link to the
owner's context, never flattery or an echo of what's pleasant to hear.
Inspiration rides on truth — the moment it doesn't, it costs the
owner's trust in every future digest, and the whole digest stops being
read.

**Shape — rails, not a template.** Short by default: a one-line
headline of the release's essence, then a benefit blurb per feature
(most-valuable first), then at most one "under the hood" line for the
technical remainder. Write the digest in the owner's language — match
how their notes and SOUL read; a friend's clone writes in theirs (the
illustration below is in English as the engine-doc default). Plain
language, no jargon — a non-technical friend must get it. End with an
open door: the owner can ask "tell me more about X" and this step
expands that one item (how it works / how to enable / a concrete
example), pulling from the CHANGELOG entry, the relevant skill doc, and
`docs/privacy.md` when the feature reads owner-data. Do not pre-dump the
detail — default short, depth on request.

**When the update crosses into 1.0.0** (`version_before` < `1.0.0`), the
release is a rename, and a rename is the one update where the mechanism IS the
news: every name the owner types changed at once. The beats below are what the
digest carries, in this order, in the owner's language. Everything above still
applies — short, plain, no hype — but none of these may be dropped, because
each one is a thing the owner would otherwise discover by something failing.

1. **The product has its own name now.** Same notes, same repository, same
   folder — nothing of theirs moved.
2. **Old → new, for the commands they actually use.** A two-column table built
   from what is on disk — `ls ~/.claude/commands/minder/mem/` and the skill
   list — not from memory. Listing a command that does not exist is worse than
   listing none.
3. **`ztn` / `зтн` / `ЗТН` still work when they speak to the assistant.** <!-- rebrand:keep -->
   They are aliases in the hot rule and stay so permanently; only the slash
   commands changed. (The line above keeps the former spellings on purpose —
   naming the alias is the whole point of the beat.)
4. **Their GitHub repository name is theirs and needs no change.** The redirect
   from the former name is permanent; renaming would drag cloud routines, inbox
   integrations and collectors with it. Offer to help only if they ask.
5. **The credential key rename** — what it is, what stays broken until it is
   done (every role that reaches an outside service), and that the assistant
   does it in the cloud routines itself.
6. **What changed in their scheduled routines, and what is still open** — from
   Step 7.1's reconciliation, by name.
7. **A loader-style routine prompt keeps working unchanged**, because the
   prompt FILE names did not change — only what is inside them.

The block below is an ILLUSTRATION of the stance, not a required
layout — adapt freely per update:

```
Update 0.42.0 → 0.43.0 — Minder now learns how you think, out of the box.

✨ New for you:
  • The cognitive-model lens is on by default. Your "how I think" hub
    used to stay blank until you switched it on yourself. Now it reads
    your reflections every other week and proposes "you seem to want X"
    — into a buffer you control (it never edits your constitution on
    its own). Want to see it fill in now → `/minder:mem:agent-lens --lens
    cognitive-model`.

🔧 Under the hood: new lenses are active by default (except the
   biometric ones — those need your health data first).

Ask for more detail on any point?
```

## What this skill does NOT do

- **Touch data paths.** Records, knowledge notes, registries,
  constitution principles, SOUL/TASKS/CALENDAR/POSTS, `*.template.md` —
  all left alone. One named exception, and it is not owner content:
  `<vault>/5_meta/help/` holds copies of engine docs and is refreshed in
  Step 6.5. A DERIVED surface is regenerated, never preserved
  (`SYSTEM_CONFIG.md → Identity Contract → Surface classes`); leaving these
  four alone is what froze them.
- **Auto-resolve divergence.** Three-way merge of prompts is not safe;
  owner decides per file.
- **Push.** Hands off to `/minder:mem:save`.
- **Run install.sh / regen-constitution / tests automatically.**
  Suggests; owner runs explicitly.
- **Rewrite the migration ledger.** If the owner needs to re-run a migration
  that already succeeded, they remove its line from
  `.engine-migrations.jsonl` themselves — guarded territory. A `heal` that
  ended `partial` needs no intervention: it is retried on the next update by
  design.

## Idempotency

VERSION current and no pending migrations → no-op exit 0.
Re-run immediately after success → no-op.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| «engine paths dirty» | Uncommitted engine edits | `/minder:mem:save --include-engine`, or `git restore` engine paths |
| «migration failed» | Bug in migration script or unexpected local state | Inspect script, fix manually, mark applied |
| «remote not configured» | First-time use | Skill offers to add `upstream` interactively |
| «merge tool requested but `git mergetool` not configured» | No mergetool | Owner picks `o` or `k`; manual merge stays out of scope |
| Local VERSION ahead of upstream | Owner is the maintainer running this in the wrong repo | Skill warns, requires explicit confirm |

## Relationship to other skills

- `/minder:mem:sync-data` pulls **owner's data** from `origin` (multi-device).
- `/minder:mem:update` pulls **engine** from `upstream` (skeleton).
- `/minder:mem:save` commits + pushes whatever the owner currently has staged.

These three never run automatically from each other. Owner orchestrates.
