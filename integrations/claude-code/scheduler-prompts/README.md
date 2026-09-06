# scheduler-prompts/

The tick contracts for the autonomous Minder Memory loop. Each `.md` file in this
directory contains **only** the prompt — no headers, no meta, no fences — so a
tick can be handed the file's whole content as its instructions.

You do not paste them into your scheduler. Each routine holds a one-line
loader pointing here, and reads the current file at run time; see «Plug-in —
Claude Code `/schedule`» below for why.

For full design rationale, cadence, and plug-in instructions see
`docs/scheduling.md`.

## Files

| File | What it runs | Recommended cadence |
|---|---|---|
| `process-scheduled.md` | `/minder:mem:sync-data` → `/minder:mem:process` → `/minder:mem:maintain --no-sync-check` → `finalize-tick.sh scheduler/process` | ≥ 3× per day, e.g. cron `0 9,14,19 * * *` |
| `agent-lens-nightly.md` | `/minder:mem:sync-data` → `/minder:mem:agent-lens --all-due` → `finalize-tick.sh scheduler/agent-lens` | 1× nightly, e.g. cron `0 3 * * *` |
| `lint-nightly.md` | `/minder:mem:sync-data` → `/minder:mem:lint` (Step 7.5 dispatches `/minder:mem:resolve-clarifications --auto-mode` inline) → `finalize-tick.sh scheduler/lint` | 1× nightly, e.g. cron `0 5 * * *` |
| `content-tick.md` | `/minder:mem:sync-data` → `/minder:mem:content --maintain` (draft-maintainer) → `finalize-tick.sh scheduler/content` | 1× weekly Tuesday, e.g. cron `0 6 * * 2` |
| `roles-nightly.md` | `/minder:mem:sync-data` → `/minder:mem:roles` (every due role, sequentially) → `finalize-tick.sh scheduler/roles` | 1× daily, e.g. cron `0 7 * * *` |

The `content-synthesis` lens (the content pipeline's classifier) is NOT a
separate tick — it is a registered agent-lens (`weekly (mon)`), so the existing
`agent-lens-nightly.md` tick runs it on Mondays via `--all-due`. The
`content-tick.md` maintainer runs the next day (Tuesday) — producer (lens) and
consumer (maintainer) in separate scheduler contexts on purpose.

## Delivery model — two modes with an MCP fallback

`finalize-tick.sh` auto-detects how to deliver the tick's commit to
`origin/main`:

**LOCAL mode** — start branch is `main` (local cron, launchd, GitHub
Actions running with full push rights). Single `git push origin main`.

**ROUTINES mode** — start branch is a sandbox ref (`claude/...`). Cloud
Routines' git proxy refuses direct push to `main`. The script instead:

1. `git push origin HEAD:<sandbox-branch>` (proxy-allowed)
2. `gh pr create --base main --head <sandbox-branch>`
3. `gh pr merge --squash --delete-branch`

End state: `main` updated with one squash commit on origin, sandbox
branch deleted on origin.

**MCP fallback** — Anthropic Cloud Routines sandboxes don't ship `gh`.
When `finalize-tick.sh` exits 2 with `"gh CLI not found in PATH"`, the
scheduler prompts have an explicit Step 5b that:

1. Pushes the local commit to the sandbox branch via plain `git push`.
2. Calls the `github` MCP `create_pull_request` tool.
3. Calls the `github` MCP `merge_pull_request` tool with squash method.
4. Leaves branch cleanup to GitHub's «Automatically delete head branches»
   setting — the prompts issue no delete call.

Step 5b is the **only** authorized non-script git/MCP path in the
prompts. It runs only on the specific «gh missing» exit and only after
`finalize-tick.sh` has produced a local `[scheduled]` commit.

## Sandbox-branch cleanup

The Cloud Routines proxy blocks both `git push origin main` AND
`git push origin --delete <branch>` (both return HTTP 403). The
`github` MCP server typically has create + merge tools but no
`delete_branch`. So in-tick deletion is best-effort.

The **load-bearing cleanup layer is GitHub's repo setting
«Automatically delete head branches»** (Settings → General → Pull
Requests). When enabled, GitHub itself removes the head branch the
moment its PR is merged (squash, merge, or rebase). Owner must enable
this once per repository; the scheduler relies on it.

With the setting on, every tick's flow ends with «PR merged → branch
auto-deleted by GitHub». No script-side recovery is needed and no
scheduler-created branch should ever linger on origin.

## Partial-tick handling

If a tick aborts between push and PR-merge, the sandbox branch on
origin holds the unmerged commit. There is no automatic recovery —
the next tick processes fresh state from `_sources/inbox/` and
produces a new commit. The stranded sandbox branch is harmless (work
content is re-derivable from inputs) and can be removed manually by
the owner if it accumulates: `git push origin --delete <branch>` from
a local clone.

If an agent driving a scheduler tick invents its own retry loop with
direct `git push` or `gh` calls, that is a contract violation — the
prompts forbid it explicitly.

## Single-commit guarantee

Every scheduler tick produces **exactly one commit on `origin/main`**.

- `scripts/scheduler/stage.sh` — staging-only helper (idempotent). May
  be called any number of times during a tick; commits nothing.
- `scripts/scheduler/finalize-tick.sh <tag>` — single commit + delivery
  (LOCAL: direct push, ROUTINES: push-to-sandbox + PR + squash-merge).
  Folds any unpushed `[scheduled]` commits from a previous partial tick.
  Refuses to rewrite history if owner has manual non-scheduled commits
  ahead of `origin/main` (no force-push, ever).

`/minder:mem:save` is **owner-interactive only**. Scheduler prompts must never
invoke it (slash form or otherwise) and must never call `git commit` /
`git push` / `git add` / `gh` directly outside the helper scripts.

There is no `maintain` prompt — maintain has no cadence of its own and
runs as Step 4.5 of the process tick, right after `/minder:mem:process` returns
and releases its lock. There is no separate `resolve-clarifications` prompt
— `--auto-mode` is dispatched by lint Step 7.5 inline; interactive
mode is owner-only by design. There is no prompt for
`/minder:mem:role:{add,edit,list,ask}` — creating and changing a role is a
conversation with the owner, never a scheduled act.

`roles-nightly.md` is the one prompt whose skill commits inside its own
tick: the roles write guard may not revert a path that was already dirty
when a role started, so `/minder:mem:roles` commits each role's own paths —
`[scheduled]` in every subject — before dispatching the next, and
`finalize-tick.sh` folds them into the single delivered commit. One
commit still reaches `origin/main` per tick.

**Why two nightly entries (lens separate from lint+resolve).** The
most quality-sensitive isolation is between agent-lens and resolve:
agent-lens stages produce `## Action Hints`, and resolve A.2/A.3
judges them. If both ran in the same scheduler-agent context, the
agent that produced lens bodies would also vote on its own proposals
— maximum confirmation bias. So agent-lens is its own tick.

Lint and resolve, by contrast, do ortogonal reasoning: lint pattern-
matches invariant violations (people-bare-name, archive-note-missing,
manifest-schema), resolve judges «would the experienced owner
approve this NOW». Chaining them in one tick accumulates context
but the bleed is small. The operational simplicity of one tick (lint
runs invariant cleanup → immediately consumes the resulting
CLARIFICATIONS + fresh lens hints in resolve A.2/A.3) outweighs the
marginal quality dip.

Order matters: agent-lens at 03:00 (runs due lenses, may emit
`## Action Hints`); lint at 05:00 — lint cleans invariants, then
Step 7.5 dispatches resolve to consume hints + new CLARIFICATIONS
+ existing queue, and either auto-applies safe additive proposals
or queues residue for owner.

**Manifest emission per tick.** `/minder:mem:process` Step 5.5 writes both
`{batch_id}.md` (markdown report) and `{batch_id}.json` (machine-
parseable JSON manifest; canonical schema in
`_system/docs/manifest-schema/`). `/minder:mem:maintain`
Step 6.6 writes its own `{batch_id}-maintain.json`, and `/minder:mem:lint`
Step 7.6 its own `{batch_id}-lint.json`. All of them commit
through `finalize-tick.sh` at the tail of the scheduler tick.

**Concept and audience layer is fully autonomous.** Format issues
never reach the CLARIFICATIONs queue from these layers — engine
resolves via `_common.py` normalisers + lint Scan A.7 autofix. The
scheduler tick should NOT see new owner-facing items from these
classes (records / notes / hubs / profile concept-name and audience-
tag format). If owner sees one, that's a bug in the producer-side
guard, not a normal autonomy boundary.

## Per-tick telemetry

Every tick runs `python3 scripts/scheduler/record_tick_telemetry.py <tag>` at Step
4.9 and appends one line to `_system/state/tick-telemetry.jsonl`, delivered in the
tick's own single commit. The line is read from the run's own session
transcript — the main session plus every sub-agent it spawned — and carries
input, output, thinking, cache writes split by TTL, cache reads, per-model
message counts and a `by_agent` breakdown that names each role by its id.

It is measured, not reported. A model cannot see its own consumption: the one
figure in its context is a remaining-budget counter that knows nothing about
cache reads or sub-agents, so a self-reported number would be fabrication.

Three properties are deliberate and should survive any edit to these prompts:

- **It runs before Step 5**, because Step 5 commits and there is no second
  commit to carry a later line. The tick's own closing messages therefore go
  uncounted; `measured_through` states the horizon instead of hiding it.
- **It always exits 0**, so a broken odometer can never cost a tick its real
  work. When it measures nothing it writes `status: unmeasured` and the
  reason.
- **Because it cannot fail loudly, something else must notice it going
  quiet** — `/minder:mem:lint` Scan A.13 checks that every `[scheduled]` commit
  carries a telemetry line, and raises `telemetry-missing` when one does not.

One consequence is deliberate and worth stating, because it changes what the
repository history looks like: **an idle tick now lands a commit where it
previously landed none.** A tick whose skill found nothing to do still leaves
a telemetry line, so `finalize-tick.sh` has something to stage. That is the
intended trade — an idle tick is not free, it still pays for loading its
context before discovering there is nothing to process, and a tick schedule
that is too aggressive is exactly the thing this data is meant to make
visible. The alternative, skipping the line when nothing else changed, would
hide the cheapest waste there is to find.

Ticks only. A manual `/minder:mem:process` writes no telemetry and raises nothing:
A.13 anchors on `[scheduled]` commits precisely so an owner working by hand
is never nagged.

## Plug-in — Claude Code `/schedule`

The path of least friction. Five routines — and each one's prompt is a
**loader**, not the tick body.

A scheduler holds the prompt text you give it verbatim, forever. Pasting a body
into it puts one contract in two places, and the scheduler's copy silently
becomes the older of the two — a tick then runs an old release's instructions
against a current engine, and nothing announces it. So the scheduler holds a
pointer and this directory holds the contract.

The five loaders, with their cron slots, live in `docs/scheduling.md` →
«Plug-in — Claude Code `/schedule`» (one source, so they cannot drift from the
cadence table beside them). Each is one sentence: read this directory's file
for that tick, follow it exactly, and refuse to act at all if it cannot be
read.

Paste them once. From then on an engine update reaches every routine on its
own — including a change to the very files in this directory.

Each routine still runs in a fresh agent against a fresh clone, so the body it
reads is the current one, and the body remains fully self-contained.

## Plug-in — non-Claude-Code schedulers

cron + `claude --print`, launchd, GitHub Actions on a private fork:
same prompt bodies. Ensure the agent has:

- filesystem access to the Minder Memory repo working tree
- configured git identity for autonomous push
- authentication to `origin` (SSH key in the runner / token in env)
- a way to surface a non-`success` status (logs, email, pager) — the
  prompts report `partial` / `sync-blocked` instead of `success`

## After `/minder:mem:update`

**Nothing to do, as long as your routines hold the loader.** These prompt
bodies are engine-shipped, `/minder:mem:update` keeps the files current, and a
routine set up per «Plug-in» above holds only a one-line loader that reads
the current file at run time — so the next tick after an update already runs
the new contract.

**A routine holding a pasted body is the case that needs action.** A scheduler
stores the text it was given and never revisits it, so such a routine keeps
running whichever version was pasted, indefinitely, while the repository moves
on. Nothing announces the divergence: the tick still succeeds, it simply does
an older thing. Replace that routine's prompt with the loader — one sentence
naming this directory's file for that tick — and it stops being a copy that
can drift.

That is why the loader exists at all, and why it is the documented setup
rather than a convenience: one contract, one home, read fresh every run.

## Contract guarantees

What the scheduler will NEVER do, regardless of which prompt is run:

- `git push --force` (of any kind, including `--force-with-lease`)
- direct `git commit`, `git push`, `git add` outside helper scripts
- `/minder:mem:save` in any form (owner-interactive only)
- staging engine paths (scripts/, integrations/, docs/, `_system/docs/`,
  `_system/scripts/`, `.engine-manifest.yml`, etc.) — `finalize-tick.sh`
  filters them and logs to CLARIFICATIONS
- `/minder:mem:resolve-clarifications` (owner-only)
- `/minder:mem:update` (owner-only)
- pause and ask the human

Anything that would be a question becomes a row in
`_system/state/CLARIFICATIONS.md` (under `### Scheduler failures` for
terminal errors). Owner reviews via `/minder:mem:resolve-clarifications` on
the next morning routine.

## Cadence guidance

Recommended:

- `minder-mem-process` — minimum 3× per day (09/14/19 local). Higher
  frequency is fine; `/minder:mem:process` is a no-op when
  `_sources/inbox/` is empty. Back-to-back ticks <5 min apart are
  wasteful (Claude Code rate / token budget).
- `minder-mem-agent-lens` (03:00 local) and `minder-mem-lint` (05:00 local) —
  two nightly ticks. Agent-lens runs first in its own scheduler-
  agent context (lens production isolated from resolve consumption,
  no confirmation bias). Lint runs ~2 h later, dispatches
  `/minder:mem:resolve-clarifications --auto-mode` via Step 7.5 inline so
  the same tick that cleans invariants also consumes fresh hints +
  CLARIFICATIONS. Owner wakes up to fully committed queue + lens
  outputs + resolve session log.
- `minder-mem-roles` (07:00 local) — after lint, before the first process
  tick, so an inbox note a role leaves is folded in the same morning.
  The tick time is also the floor for every role's cadence anchor: a
  role declaring `daily 14:00` is never due at a 07:00 tick, because
  the grammar does not catch up on a missed anchor.
