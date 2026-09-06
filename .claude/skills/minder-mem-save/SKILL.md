---
name: minder:mem:save
description: >
  Owner-friendly wrapper around git commit + push. Groups working-tree
  changes by type (records / knowledge / state / engine / other),
  proposes a sensible commit message, shows a summary diff, asks for
  confirmation, then commits and pushes to origin. For non-technical
  owners who want a single-step «save my work» button instead of
  remembering git plumbing. Never auto-fired by other skills — always
  invoked explicitly. Refuses to push to non-origin remotes (engine
  updates flow through `/minder:mem:update`, not this).
disable-model-invocation: false
---

# /minder:mem:save — Commit and push owner's working changes

The owner accumulates changes across `_records/`, `_sources/`, knowledge
notes, registries, state files, and constitution as they live with the
system. This skill is the canonical «I'm done for now, sync to my
remote» step. Replaces the cognitive load of: which files to stage,
what to write in the message, did I push, should I rebase first.

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md`.

## Arguments

`$ARGUMENTS`:
- `--message <text>` — override the auto-proposed commit message
- `--no-push` — commit only, do not push
- `--include-engine` — allow staging files under engine paths (default
  refuses; engine paths are owned upstream and changed by `/minder:mem:update`)
- `--dry-run` — show what would be committed and the proposed message,
  apply nothing
- `--auto` — non-interactive mode for owner power use. Skips Step 3
  confirmation, uses the auto-proposed message verbatim (or `--message`
  if passed), commits and pushes silently. Engine refusal still applies
  (`--include-engine` is forbidden in combination with `--auto`). On push
  rejection fails loud (no force-push). **Not for scheduler use** — the
  autonomous scheduler protocol uses `scripts/scheduler/finalize-tick.sh`
  instead, which guarantees one commit per tick. Calling `/minder:mem:save
  --auto` from a scheduler prompt is a contract violation that produces
  multiple commits per tick.
- `--tag <text>` — prepend `<text>: ` to the commit message before the
  `[scheduled]` suffix is appended (e.g. `--tag scheduler/lint` yields
  `scheduler/lint: <auto-or-message-msg> [scheduled]`). Idempotent: if
  the message already starts with `<text>:`, no second prefix is added.
  Retained for parity with `finalize-tick.sh`; scheduler prompts use
  `finalize-tick.sh` directly.

## Preconditions

1. Current directory is the Minder Memory repo root (has `.engine-manifest.yml`).
2. `origin` remote is configured and reachable.
3. No other Minder Memory producer skill is currently running. Read **all seven**
   pipeline locks, in this order, and abort with a clear message naming
   the conflicting skill if any exists:
   - `_sources/.processing.lock` → `/minder:mem:process`
   - `_sources/.maintain.lock` → `/minder:mem:maintain`
   - `_sources/.lint.lock` → `/minder:mem:lint`
   - `_sources/.agent-lens.lock` → `/minder:mem:agent-lens`
   - `_sources/.content.lock` → `/minder:mem:content`
   - `_sources/.resolve.lock` → `/minder:mem:resolve-clarifications`
   - `_sources/.roles.lock` → `/minder:mem:roles`

   The full set, not a subset: committing inside a running tick is
   equally unsafe whichever tick it is. A roles tick is the sharpest
   case — `roles_guard.py` attributes every write in its diff window to
   the role that is running and reverts what falls outside that role's
   zone, so a commit landing mid-tick is attributed to a role that did
   not make it. A lock this skill does not read is a lock it walks into.

This skill does NOT take its own lock — it does not write to Minder Memory
content files, only to git, plus the rename-only portable-name
pre-pass in Step 0.5 (file names, never file contents).

## Pipeline

### Step 0.5 — Portable-name pre-pass (inbox only)

Before snapshotting, walk `_sources/inbox/{id}/` (immediate children of
every source folder, plus files one level inside per-item folders). Any
entry whose name fails `_system/scripts/_common.py::is_portable_name` is
renamed to `normalize_portable_name(name)` — same SoT and same rules as
`/minder:mem:process` §0.0b. This keeps Windows-illegal names (colons in Plaud
ISO timestamps, etc.) out of git entirely: a raw inbox drop committed
from a phone or a Mac would otherwise break `git checkout` on a Windows
device pulling it.

- Renames are autonomous and silent per-item (deterministic pure
  function — ENGINE_DOCTRINE §3.1 autonomous-resolution layer); list
  them in the Step 3 summary under a `renamed:` line when any happened.
- Collision with an existing name, or normalisation returning None →
  do NOT rename, do NOT guess; leave the entry uncommitted (exclude
  from staging), append a `portable-name-collision` CLARIFICATION, and
  continue with the rest of the save.
- Scope is `_sources/inbox/` only — `_sources/processed/` legacy names
  are grandfathered and referenced as-is; renaming them would break
  `source:` pointers.
- In `--auto` mode behaviour is identical (silent rename, CLARIFICATION
  on collision) — never blocks.

### Step 1 — Snapshot working tree

Run `git -c core.quotepath=false status --porcelain=v1`. The
`core.quotepath=false` is load-bearing: with the default (`true`) git
octal-escapes non-ASCII bytes in the output (a Cyrillic filename becomes
`"…\320\222…"`), and a later `git add` of that escaped string fails with
«pathspec did not match». With it off, paths print as raw UTF-8 (spaces still
wrap a path in quotes, which you strip). Build a categorisation:

| Category | Path globs | Default action |
|---|---|---|
| records | `zettelkasten/_records/**` | stage |
| sources | `zettelkasten/_sources/**` (excluding `**/.*.lock`) | stage |
| knowledge | `zettelkasten/{1_projects,2_areas,3_resources,4_archive,6_posts}/**` | stage |
| constitution | `zettelkasten/0_constitution/{axiom,principle,rule}/**` | stage |
| system-data | `zettelkasten/_system/{SOUL,TASKS,CALENDAR,POSTS}.md`, `_system/registries/*.md`, `3_resources/people/PEOPLE.md`, `1_projects/PROJECTS.md` | stage |
| state | `zettelkasten/_system/state/**` | stage |
| views | `zettelkasten/_system/views/**` | stage |
| engine | any path matching `engine:` in `.engine-manifest.yml` | **refuse unless `--include-engine`** |
| other | anything else (e.g. ad-hoc owner files) | stage and flag for review |

If `engine` paths are dirty and `--include-engine` not passed:
- **Interactive mode:** abort with: «engine paths have local edits —
  these belong upstream. Use `/minder:mem:update` to pull, contribute upstream
  via `CONTRIBUTING.md`, or pass `--include-engine` if you intentionally
  maintain a local fork». List the dirty engine paths.
- **`--auto` mode:** do NOT abort. Skip engine paths from staging
  (they remain dirty in working tree), append a one-line note to
  `_system/state/CLARIFICATIONS.md` under `### Scheduler failures` —
  format `YYYY-MM-DDTHH:MM scheduler: engine drift in <path1>, <path2>…
  — run /minder:mem:update or revert before next tick`. Continue with
  non-engine staging. Rationale: scheduler's contract is «always
  commit data progress»; engine drift is an owner concern, surfaced
  not enforced. `--include-engine` remains forbidden under `--auto`.

### Step 2 — Propose a commit message

Heuristic, not LLM-generated unless category is mixed/unclear:

| Composition | Proposed message |
|---|---|
| Only `records` | `records: <N> new entries` (bump count) |
| Only `sources` (raw inbox grew) | `sources: drop <N> transcript(s)` |
| Only `knowledge` | `knowledge: <N> note(s) edited` |
| Only `state` | `state: routine update` |
| Only `system-data` | `system: edit <PEOPLE\|PROJECTS\|...>` (most-changed first) |
| Only `constitution` | `constitution: <N> principle(s) edited` |
| Mixed routine (`records` + `state` + `system-data`) | `process batch: <N> records, registries refreshed` |
| Mixed broad | `routine save: <N> file(s) across <K> areas` |

If `--message` passed — use that verbatim. Otherwise show the proposal
and let the owner edit (single-line input). Keep messages in lowercase
imperative, no Claude attribution, no body unless owner asks.

In `--auto` mode: use the proposed message (or `--message`) without
prompting. If `--tag <text>` is set, prepend `<text>: ` to that message
(skip the prepend if the message already starts with `<text>:`). Append
`[scheduled]` suffix so the owner can grep
`git log --grep '\[scheduled\]'` and audit autonomous commits. Final
shape: `[<tag>: ]<auto-or-message-msg> [scheduled]`.

### Step 3 — Show summary

Render compact:

```
Будет закоммичено:
  records:     +3 -0  (~/IdeaProjects/.../meetings/2026-04-28-*.md)
  state:       +1 ~5  (BATCH_LOG, log_process)
  system-data: ~1     (PEOPLE.md)
Всего: 9 файлов, 4 категории.

Сообщение: process batch: 3 records, registries refreshed

[y] commit + push   [m] edit message   [s] skip push (commit only)
[d] show full diff  [n] abort
```

### Step 4 — Apply

- `y` (or `--auto`) → `git add <staged paths>` then `git commit -m "<message>"`
  then, unless `--no-push` or owner picked `s`, `git push origin <current-branch>`.
- If push fails on rejection (non-fast-forward) — do NOT force.
  Suggest: «remote has new commits. Run `/minder:mem:sync-data` first, then
  re-run `/minder:mem:save`.» Exit non-zero.
- If push fails for other reasons (auth, network) — surface error,
  leave commit in place.

### Step 5 — Recap

Print:
```
Saved.
  Commit:  <short SHA>  <message>
  Pushed:  origin/<branch>  ✓
  Backup:  remote up to date as of <ISO timestamp>

Next: continue working, or run /minder:mem:process if you have new transcripts.
```

If `--no-push`:
```
Committed locally — not pushed.
Run `/minder:mem:save` again (without `--no-push`) when ready.
```

## What this skill does NOT do

- **Resolve merge conflicts.** Push rejection → fail loud, redirect to
  `/minder:mem:sync-data`. Markdown three-way auto-merge is unsafe.
- **Modify Minder Memory content.** Pure git wrapper.
- **Auto-fire from other skills.** Owner invokes explicitly.
- **Squash / amend / rebase.** Linear history of save points is the goal;
  reorganisation is power-user territory, not this skill's concern.
- **Create branches.** Operates on the currently checked-out branch.
- **Push tags.** No release semantics here.

## Idempotency

- No staged changes and clean tree → skill prints «nothing to save» and
  exits 0.
- Already-pushed commit + clean tree → same.
- Re-running after a successful save → no-op.

## Output files

None. Only side-effect: a single commit on the current branch +
optionally a push.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| «engine paths have local edits» | Owner edited an engine file | Re-run with `--include-engine`, or revert engine path |
| «remote has new commits» (push rejected) | Another device pushed first | Run `/minder:mem:sync-data`, then `/minder:mem:save` again |
| «no upstream branch» | Branch never pushed | Skill runs `git push -u origin <branch>` automatically on first push |
| «authentication failed» | Bad credentials / SSH key | Surface git's error verbatim; this skill does not diagnose auth |
