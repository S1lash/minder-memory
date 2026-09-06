# Scheduling — autonomous Minder Memory ticks

Minder Memory is designed to run **multiple times a day, every day**, without you
in the loop for the routine path. This doc describes the canonical
scheduling setup, the assumptions baked into it, and how to plug it in.

## The canonical loop

Five scheduled jobs.

| Job | Cadence | Skill chain | Prompt source |
|---|---|---|---|
| `minder-mem-process` | ≥ 3× per day | `/minder:mem:sync-data` → `/minder:mem:process` → `/minder:mem:maintain --no-sync-check` → `finalize-tick.sh scheduler/process` | `integrations/claude-code/scheduler-prompts/process-scheduled.md` |
| `minder-mem-agent-lens` | 1× nightly (03:00) | `/minder:mem:sync-data` → `/minder:mem:agent-lens --all-due` → `finalize-tick.sh scheduler/agent-lens` | `integrations/claude-code/scheduler-prompts/agent-lens-nightly.md` |
| `minder-mem-lint` | 1× nightly (05:00) | `/minder:mem:sync-data` → `/minder:mem:lint` (Step 7.5 dispatches `/minder:mem:resolve-clarifications --auto-mode` inline) → `finalize-tick.sh scheduler/lint` | `integrations/claude-code/scheduler-prompts/lint-nightly.md` |
| `minder-mem-content` | 1× weekly (Tue 06:00) | `/minder:mem:sync-data` → `/minder:mem:content --maintain` → `finalize-tick.sh scheduler/content` | `integrations/claude-code/scheduler-prompts/content-tick.md` |
| `minder-mem-roles` | 1× daily (07:00) | `/minder:mem:sync-data` → `/minder:mem:roles` → `finalize-tick.sh scheduler/roles` | `integrations/claude-code/scheduler-prompts/roles-nightly.md` |

The content pipeline runs across two ticks a day apart: the `content-synthesis`
lens (the classifier) is a registered agent-lens (`weekly mon`), so the existing
`minder-mem-agent-lens` tick runs it on Mondays; the `minder-mem-content` maintainer drafts on
Tuesdays. Producer (lens) and consumer (maintainer) stay in separate scheduler
contexts on purpose — the maintainer must not be the same context that just
produced the lens verdict.

The two deep-night ticks. Agent-lens runs first (03:00) in its own scheduler-
agent context — lens production isolated from resolve consumption,
prevents the agent that produces lens bodies from also voting on its
own proposals (confirmation bias). Lint runs later (05:00), invokes
its invariant scans, then Step 7.5 dispatches resolve --auto-mode
inline so the same tick consumes fresh lens hints + CLARIFICATIONS
that lint just emitted. The agent-lens skill filters lenses by per-
lens cadence — nightly fire ≠ nightly lens runs.

The roles tick closes the overnight sequence at 07:00. Three reasons for that
slot, in order of weight:

1. **After lint, before process.** A role that leaves a note in
   `_sources/inbox/roles/` needs `/minder:mem:process` to fold it in; landing two hours
   before the 09:00 process tick means the note is knowledge the same morning
   rather than the next day. Running it before lint would instead have roles read
   a base lint has not yet cleaned.
2. **The tick time is the floor for every role's cadence anchor.** A role
   declaring `daily 07:00` fires at this tick; one declaring `daily 14:00` is
   never due, because the anchor is not reached at tick time and the grammar
   does not catch up. The concierge that writes a role sizes its cadence to the
   tick, and an owner who moves the tick moves that floor with it.
3. **No overlap.** Roles hold `.roles.lock` for the whole tick and every
   pipeline aborts on it; 07:00 is clear of 03:00 / 05:00 / 06:00-Tuesday and of
   the 09:00 process tick.

Like agent-lens, one fire ≠ one run per role: the tick runs only the roles whose
own cadence has elapsed, sequentially, never two at once.

There is no `minder-mem-maintain` schedule — maintain has no cadence of its own
and runs as Step 4.5 of the process tick, once `/minder:mem:process` has
returned and released its lock (the two are mutually exclusive, so the
integrator cannot run inside the producer). There is no `minder-mem-resolve-clarifications` schedule —
the owner reviews the queue manually; that is the human-in-loop hinge
of the whole system. There is no `minder-mem-agent-lens-add` schedule — lens
creation is owner-driven (wizard-style); see
`integrations/claude-code/skills/minder-mem-agent-lens-add/SKILL.md`.

## Single-commit guarantee

Every scheduler tick produces **exactly one commit on `origin/main`**.
The contract is enforced by `scripts/scheduler/finalize-tick.sh` — the
single point in the prompt that commits + delivers. Two helpers feed
into it:

- `scripts/scheduler/stage.sh` — staging-only (idempotent). Engine
  paths are filtered (defined in `.engine-manifest.yml` + a small
  conservative-prefix list in `_classify_paths.py`); only owner data
  is staged. May be called any number of times during a tick.
- `scripts/scheduler/finalize-tick.sh <tag>` — single commit + delivery.
  Folds any unpushed `[scheduled]` commits from a previous partial tick
  into one commit. Refuses to rewrite history if owner has manual
  non-scheduled commits ahead of `origin/main` (no force-push, ever).

`/minder:mem:save` is owner-interactive only. Scheduler prompts never invoke
it and never call `git commit` / `git push` / `git add` outside the
helper scripts (with one narrow exception below for the MCP fallback).

**One skill commits inside its own tick: `/minder:mem:roles`.** Its write guard
compares the repository before and after each role, so whatever a role leaves
uncommitted is still dirty when the next one starts — and a path already dirty
when a role starts is one the guard may not revert, because restoring it would
destroy content that role did not write. The tick therefore commits each role's
own paths before dispatching the next, every commit marked `[scheduled]`, and
`finalize-tick.sh` folds them all into the one delivered commit like any
partial-tick leftover. The guarantee is unchanged: one commit reaches
`origin/main` per tick.

## Skill discovery — the Step 0 preflight

Every tick invokes `/minder:mem:*` skills as slash commands. The runtime discovers
them from `.claude/skills/<name>/SKILL.md` in the clone. If that layout is
broken, the tick dies at its first slash invocation — historically the most
common scheduler failure.

The layout is cross-platform by construction: the skeleton ships
`.claude/skills/<name>/SKILL.md` as **real files**, not symlinks. Git symlinks
do not survive a Windows clone (`core.symlinks=false` materialises the symlink
blob as a text file, so `.claude/skills/minder-mem-process` becomes a file and its
`SKILL.md` disappears). The owner repo keeps symlinks for the dev loop;
`scripts/release_engine.py` dereferences them into real files on release, and
`scripts/sync_engine.sh` replaces a broken local `.claude/skills/` with the
real-file tree on `/minder:mem:update`.

As a fail-fast guard, **Step 0** of every tick runs
`scripts/scheduler/ensure-skills.sh` (check-only) and, if any skill does not
resolve, ships a precise failure note and exits `partial` instead of cascading
into confused recovery. The tick does **not** try to repair the layout
in-session: the runtime scans skills at clone time, so a mid-tick fix cannot
make the slash commands load, and a cloud sandbox is ephemeral so it cannot
persist either. Repair belongs to persistent local setups — `install.sh` runs
`ensure-skills.sh --repair` there (symlink where supported, real-file copy as
fallback). The durable fix for a broken clone is the real-file skeleton layout
delivered via `/minder:mem:update`.

## Delivery model — two modes with an MCP fallback

`finalize-tick.sh` auto-detects how to deliver the tick's commit:

**LOCAL mode** — start branch is `main` (local cron, launchd, GitHub
Actions running with full push rights to main). Single
`git push origin main`. No sandbox branch involved.

**ROUTINES mode** — start branch is a sandbox ref (`claude/...`).
Anthropic Cloud Routines' git proxy refuses direct push to `main` and
refuses `git push origin --delete <branch>` (both HTTP 403). The script
instead:

1. `git push origin HEAD:<sandbox-branch>` (proxy-allowed).
2. `gh pr create --base main --head <sandbox-branch>`.
3. `gh pr merge --squash --delete-branch`.

End state: `main` has one squash commit, sandbox branch deleted.

**MCP fallback** — Cloud Routines sandboxes typically don't ship `gh`.
When `finalize-tick.sh` exits 2 with `"gh CLI not found in PATH"`, the
scheduler prompts have an explicit Step 5b that routes through the
`github` MCP server: push HEAD to the sandbox branch via plain `git
push`, call MCP `create_pull_request`, call MCP `merge_pull_request`
with `merge_method: squash`. Branch cleanup falls to the repo setting
described in the next section. Step 5b is the **only** authorized
non-script git/MCP path in the prompts.

## ⚠️ Required repo setting — auto-delete head branches

The Routines proxy blocks `git push origin --delete <branch>`, and the
github MCP server does not currently have a `delete_branch` tool. The
scheduler therefore **cannot** delete its own sandbox branch from
within a Routines tick. The cleanup mechanism is GitHub itself:

**Settings → General → Pull Requests → ☑ Automatically delete head
branches**

Enable this **once per repository**. With it on, GitHub removes the
head branch the moment its PR is squash-merged. With it off, each
scheduler tick leaves a sandbox branch on origin and they accumulate.

This is the load-bearing assumption of the ROUTINES delivery path. The
new-repo onboarding checklist (`docs/onboarding.md` §9) calls it out
explicitly. Verify it is on before relying on cloud scheduling.

For LOCAL mode the setting is not required (no PR involved), but
enabling it does no harm.

## Credentials for the roles tick — MINDER_MEMORY_ROLES_KEY

Skip this until you have a role that reaches an outside service — a task
board, a mail API, anything authenticated. Roles that only read and write
your own notes need none of it.

Such a role reads its credential from an encrypted store committed to your
repo, `zettelkasten/_system/state/secrets.enc.json`. Every value in it is
encrypted on its own, and none is readable without a single key:
`MINDER_MEMORY_ROLES_KEY`, one 44-character value, one per base.

**The key goes in the environment config of your `minder-mem-roles` routine and
nowhere else.** Not in the prompt — that is text you paste and share around.
Not in the repo — the engine writes it to no file, and nothing in the tick
prints it.

- **Claude Code `/schedule`** — set it in the routine's environment /
  secrets configuration, next to the cron line and the prompt.
- **cron, launchd, GitHub Actions** — set it in whatever launches
  `claude`: a wrapper script that exports it, a launchd
  `EnvironmentVariables` entry, a systemd `Environment=` line, or an
  Actions secret exposed through `env:`. Not in a shell profile you also
  use interactively.

**You never invent the key yourself.** `/minder:mem:role:add` generates it the
first time a role on this base needs a credential, shows it once, and says
where it goes. Once, because the engine keeps no copy. **A lost key cannot
be recovered** — everything encrypted with it is gone and you enter those
credentials again against a new key. Keep it wherever you keep passwords,
not only in the routine config.

**If the key is missing the tick degrades; it does not die.** Roles that
declare no credential run exactly as usual. Every due role that declares one
is skipped, with an error line in its own log naming the cause, and the tick
raises a single clarification for your morning review. It never generates a
key to get past this — a new key does not open what the old one wrote, so it
would silently orphan every credential already stored. The tick's output
carries:

```
error: MINDER_MEMORY_ROLES_KEY is not set: the credential store is encrypted and the key arrives from the environment. Set MINDER_MEMORY_ROLES_KEY in the scheduler routine's env config — never in the prompt body and never in git.
```

**A base that has credentials also needs the `cryptography` package** in the
environment the tick runs in:

```bash
python3 -m pip install "cryptography>=41.0"
```

It is imported only when a store exists, so a base without credentials
neither needs it nor breaks without it.

**The scheduled tick installs it for you when it has to.** A cloud sandbox
starts from a fresh clone every run, so anything you install there is gone by
the next one — which would make «install it where the tick runs» advice you
cannot act on. The tick therefore checks at startup and installs the one
declared package itself, but only when a credential store exists and only
when the import fails; a base without credentials never installs anything.
Run the command above yourself only for the machine where you use
`/minder:mem:role:add`, since role creation needs the package too.

If the install cannot happen, nothing crashes: the tick degrades exactly as
above and names the package instead of the key.

**What committing the store trades away.** If your repo is ever exposed, an
attacker holds the ciphertext — not the key, but ciphertext plus time is not
nothing. It is committed deliberately: a file git ignores does not exist in
a fresh cloud clone, so with one a scheduled role could only reach an
authenticated service while your own machine happened to be awake.
Committing it is what makes an unattended outward role possible at all.
`docs/privacy.md` carries the same trade in full.

## Opinionated assumptions

These are not configurable. If you need a different model, the
scheduler prompts are not for you yet.

- **Process at least daily, usually multiple times.** Minder Memory's value
  comes from cadence. Less than once a day means transcripts pile up
  and the macro picture lags reality.
- **Lint at night, after the day's last process tick.** Lint reads the
  day's accumulated state. Running it before processing is wasteful;
  running it concurrently with processing risks lock contention.
- **Every scheduled run autocommits and pushes.** Without push,
  multi-device use breaks. Without autocommit, the working tree
  accumulates uncommitted scheduler output and the next manual
  `/minder:mem:save` becomes ambiguous.
- **Ambiguity goes to CLARIFICATIONS, not to you.** The whole
  CLARIFICATIONS mechanism exists for this exact case. A scheduled
  run that pauses on a question is broken — it just hangs the agent
  until timeout. CLARIFICATIONS is the async hand-off.
- **Engine drift is never resolved by the scheduler.** `stage.sh` and
  `finalize-tick.sh` refuse engine paths. If you edited engine files
  locally, the scheduler will leave them dirty and surface a
  CLARIFICATIONS note. Run `/minder:mem:update` (or revert) yourself.

## What the scheduler will NEVER do

| Operation | Why not |
|---|---|
| `git push --force` (or `--force-with-lease`) | Data-loss risk. Push rejection means «sync next tick», not «overwrite remote». |
| Stage engine paths | Engine is owned upstream. Local edits to engine paths are an owner concern; engine drift is logged to CLARIFICATIONS instead. |
| `/minder:mem:resolve-clarifications` interactive | Resolution is the human-in-loop step by design. The auto-mode dispatch inside lint Step 7.5 is the exception. |
| `/minder:mem:update` | Engine sync needs owner attention (VERSION delta, migrations, divergence resolution). |
| Pause and ask the owner | No human in this loop. Anything that would be a question becomes a CLARIFICATIONS row. |
| Retry push on failure | The script makes exactly one delivery attempt per tick. A failed delivery surfaces as `partial`; next tick processes fresh state from inbox. |
| Skip commit on «small» changes | Every tick commits, even routine state-only churn. Predictability beats minimalism. |

## Partial-tick handling

If a tick aborts between push and PR-merge (network glitch, MCP error,
PR creation failure), the sandbox branch on origin holds the unmerged
commit. There is **no automatic recovery sweep** — the new architecture
keeps the design minimal. The next tick processes fresh state from
`_sources/inbox/` and produces a new commit. The stranded sandbox
branch is harmless (work content is re-derivable from inputs) and can
be removed manually if it accumulates:

```bash
git push origin --delete <branch>   # from a local clone with push rights
```

Routines tick output ends with the contract status: `success <SHA>`,
`partial`, or `sync-blocked`. Owner sees the line in the Routine's
own log and can intervene if needed.

## How skills reach the scheduler agent

The scheduler agent is just a Claude Code session running your prompt
body. For the slash invocations (`/minder:mem:sync-data`, `/minder:mem:process`,
`/minder:mem:maintain`, `/minder:mem:agent-lens --all-due`, `/minder:mem:lint`,
`/minder:mem:content --maintain`, `/minder:mem:roles`) to actually fire, Minder Memory skills
must be visible in the session's skill registry.

- **Cloud Routines / `/schedule`** — clone the repo fresh and look at
  `.claude/skills/<name>/SKILL.md` at the repo root. Your clone ships
  those as **real files** (see «Skill discovery — the Step 0 preflight»
  above for why they are not symlinks), so all skills load
  automatically. Nothing to configure.
- **Local cron / launchd / GitHub Actions** — the same
  `.claude/skills/` tree loads when the runner has the repo as CWD. If
  the runner invokes `claude` from a different CWD, also run
  `bash integrations/claude-code/install.sh` once on the runner so
  user-level `~/.claude/skills/` symlinks cover the case.

The bash helpers under `scripts/scheduler/` (`ensure-skills.sh`,
`pin-main.sh`, `lock-check.sh`, `stage.sh`, `finalize-tick.sh`,
`ship-failure-note.sh`, plus `ensure-roles-deps.sh` for the roles tick)
are repo-local — every prompt body invokes them via
`bash scripts/scheduler/<name>.sh`. They handle skill-layout preflight +
git plumbing + cross-skill lock detection + single-commit delivery so the
prompt bodies stay thin and near-identical across all five ticks.

## Plug-in — Claude Code `/schedule`

The recommended path. Five routines — one per row of the canonical table above.

**Each routine's prompt is a loader, not the tick body.** A scheduler holds
the prompt text you gave it, verbatim and forever; the tick body lives in this
repository and changes with every engine update. Pasting the body puts one
contract in two places, and the copy in the scheduler silently becomes the
older of the two — a tick then runs last quarter's instructions against this
quarter's engine, and nothing announces it. So the scheduler holds a pointer
and the repository holds the contract. Paste each loader once; engine updates
reach every tick on their own from then on.

```
/schedule
  name: minder-mem-process
  cron: 0 9,14,19 * * *
  prompt: Read integrations/claude-code/scheduler-prompts/process-scheduled.md
    in this repository and follow it exactly, from its first step to its last.
    That file is the entire contract for this run — do nothing it does not
    authorize, and do not substitute your own judgement for any step. If it
    cannot be read, stop immediately, change nothing, and report `partial`.
```

```
/schedule
  name: minder-mem-agent-lens
  cron: 0 3 * * *
  prompt: Read integrations/claude-code/scheduler-prompts/agent-lens-nightly.md
    in this repository and follow it exactly, from its first step to its last.
    That file is the entire contract for this run — do nothing it does not
    authorize, and do not substitute your own judgement for any step. If it
    cannot be read, stop immediately, change nothing, and report `partial`.
```

```
/schedule
  name: minder-mem-lint
  cron: 0 5 * * *
  prompt: Read integrations/claude-code/scheduler-prompts/lint-nightly.md
    in this repository and follow it exactly, from its first step to its last.
    That file is the entire contract for this run — do nothing it does not
    authorize, and do not substitute your own judgement for any step. If it
    cannot be read, stop immediately, change nothing, and report `partial`.
```

```
/schedule
  name: minder-mem-content
  cron: 0 6 * * 2
  prompt: Read integrations/claude-code/scheduler-prompts/content-tick.md
    in this repository and follow it exactly, from its first step to its last.
    That file is the entire contract for this run — do nothing it does not
    authorize, and do not substitute your own judgement for any step. If it
    cannot be read, stop immediately, change nothing, and report `partial`.
```

```
/schedule
  name: minder-mem-roles
  cron: 0 7 * * *
  prompt: Read integrations/claude-code/scheduler-prompts/roles-nightly.md
    in this repository and follow it exactly, from its first step to its last.
    That file is the entire contract for this run — do nothing it does not
    authorize, and do not substitute your own judgement for any step. If it
    cannot be read, stop immediately, change nothing, and report `partial`.
```

If any of your roles reaches an outside service, the `minder-mem-roles` routine
also needs `MINDER_MEMORY_ROLES_KEY` in its environment config — see «Credentials for
the roles tick — MINDER_MEMORY_ROLES_KEY» above.

Each routine runs in a fresh agent against a fresh clone, so the file it reads
is the current one — which is what makes the loader safe. The refusal clause is
load-bearing: a tick that cannot read its contract must do nothing at all, never
improvise a plausible one.

The body stays fully self-contained. Nothing about the loader changes what a
tick does; it changes only where the tick gets its instructions, so that an
engine update reaches your schedules without you re-pasting anything.

**Name your routines whatever you like.** `minder-mem-lint` above is a suggestion, not
a handle the engine uses — you may well call yours `minder-memory: lint (nightly)`
or `ночная уборка`. Nothing reads these names. When a future engine update
changes a prompt file, `/minder:mem:update` finds the affected routines by comparing
what each one's prompt actually says against the shipped files, then tells you
which of YOUR routines are involved and offers to update them for you. A
recommendation phrased as «re-paste the prompt» is one you cannot act on
without first working out which routine it means — so the engine does that
work instead of handing it to you.

## Plug-in — non-Claude-Code schedulers

cron + `claude --print`, launchd, GitHub Actions on a private fork:
same prompt bodies. Ensure:

- Filesystem access to the Minder Memory repo working tree.
- Configured git identity for autonomous push.
- Authentication to `origin` (SSH key in the runner / token in env).
  Concrete setup options (passphrase-less SSH, PAT-baked remote URL,
  platform-managed credentials) — see `docs/onboarding.md` §9.
- A way to surface non-zero exit (logs, email, pager) — the prompt
  bodies exit non-zero on sync-blocked / partial.
- For the roles job only, and only if one of your roles reaches an outside
  service: `MINDER_MEMORY_ROLES_KEY` in that job's environment and the `cryptography`
  package installed for that runner's `python3` — see «Credentials for the
  roles tick — MINDER_MEMORY_ROLES_KEY» above.

Local cron starts on the `main` branch by default, so LOCAL mode in
`finalize-tick.sh` applies — no PR ceremony, just direct push.

## Owner morning routine

The other half of the loop. Whatever happened overnight + during the
day lands in CLARIFICATIONS by morning.

1. `/minder:mem:resolve-clarifications` — pre-syncs against `origin`, walks
   you through the queue one theme at a time, refreshes derived views
   (`/minder:mem:regen-constitution`, `/minder:mem:maintain`) when your resolutions
   touched constitution / registries, and reminds you to save.
2. `/minder:mem:save` (interactive, not `--auto`) — commit + push your
   resolutions when the skill prompts you.

That's it. The scheduler covers ingestion + slop-catching; you cover
judgement + resolution.

## Why this shape (instead of N tiny jobs or one big one)

- **One big nightly job.** Tried mentally: would mean transcripts
  dropped at 10am don't surface until 03:00 the next day. Minder Memory is a
  thinking aid; latency >12h kills the feedback loop.
- **Per-skill schedules (process, maintain, lint, resolve, agent-lens,
  agent-lens-add, content, roles, role-add).** Tried mentally: maintain has no
  independent cadence (it is a step of the process tick); resolve, agent-lens-add and
  `/minder:mem:role:{add,edit,list,ask}` must not be autonomous (owner judgement /
  concierge interview). The five scheduled jobs (process / agent-lens / lint /
  content / roles) cover the autonomous surface area; every other skill is
  either owner-gated or tails another tick, so it earns no standalone schedule.
- **Process every hour.** Wasteful for typical input rates and burns
  Claude Code budget; revisit only if you start dropping transcripts
  faster than the recommended 3× cadence drains them.
