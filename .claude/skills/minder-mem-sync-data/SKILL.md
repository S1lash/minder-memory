---
name: minder:mem:sync-data
description: >
  Pull the owner's own data from `origin` with rebase. For multi-device
  setups: phone records into inbox/ on laptop A, laptop B wants to
  process the same content; or `/minder:mem:process` ran on a server and the
  owner wants the produced records locally. Safe-by-default — refuses
  to merge if there are uncommitted local changes, refuses to
  auto-resolve markdown conflicts (always escalates to owner), never
  touches engine paths (those belong to `/minder:mem:update`). Recommended
  before `/minder:mem:process`, `/minder:mem:lint`, `/minder:mem:maintain` on any device
  that is not the canonical writer.
disable-model-invocation: false
---

# /minder:mem:sync-data — Pull owner's data with rebase

The owner's repo is single-remote (`origin`) by default. Minder Memory content
flows: device A captures + processes → pushes → device B pulls before
working. This skill is the «before I start, am I current?» step.

Distinct from `/minder:mem:update`, which pulls **engine** updates from a
different remote (`upstream`, the public skeleton).

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md`.

## Arguments

`$ARGUMENTS`:
- `--remote <name>` — default `origin`
- `--branch <name>` — default current branch
- `--dry-run` — show what would be pulled, apply nothing
- `--auto-stash` — stash local uncommitted changes before pull, pop
  after (default: refuse if dirty)

## Preconditions

1. Repo root has `.engine-manifest.yml`.
2. `origin` (or `--remote`) is configured and reachable.
3. No producer-skill lock present. Read **all seven**, in this order:
   - `_sources/.processing.lock` → `/minder:mem:process`
   - `_sources/.maintain.lock` → `/minder:mem:maintain`
   - `_sources/.lint.lock` → `/minder:mem:lint`
   - `_sources/.agent-lens.lock` → `/minder:mem:agent-lens`
   - `_sources/.content.lock` → `/minder:mem:content`
   - `_sources/.resolve.lock` → `/minder:mem:resolve-clarifications`
   - `_sources/.roles.lock` → `/minder:mem:roles`

   Abort with the conflicting skill name if any. The full set, not a
   subset: a rebase under any running tick moves the tree beneath it. A
   roles tick is the sharpest case — `roles_guard.py` attributes every
   write in its diff window to the running role and reverts what falls
   outside that role's zone, so a rebase landing mid-tick is attributed
   to a role that did not make it.

## Pipeline

### Step 1 — Fetch

```
git fetch <remote> <branch>
```

Compute:
- `local_ahead` = `git rev-list --count <remote>/<branch>..HEAD`
- `remote_ahead` = `git rev-list --count HEAD..<remote>/<branch>`

Cases:

| local_ahead | remote_ahead | Meaning | Action |
|---|---|---|---|
| 0 | 0 | already current | print «up to date», exit 0 |
| >0 | 0 | local ahead only | suggest `/minder:mem:save` to push, exit 0 |
| 0 | >0 | clean fast-forward | proceed to Step 3 |
| >0 | >0 | divergence — rebase needed | proceed to Step 2 |

### Step 2 — Pre-rebase safety check (only when both diverge)

Show preview:
```
Локально: <N> коммит(а/ов) еще не отправлено
В origin:  <M> новых коммита/ов

Будут переподложены под remote (rebase). Конфликты возможны если
один и тот же файл изменён с обеих сторон.

Затронутые файлы (overlap):
  zettelkasten/_records/2026-04-28-*.md   (local + remote)
  zettelkasten/3_resources/people/PEOPLE.md (local + remote)

[y] continue   [n] abort
```

Compute overlap as `git diff --name-only <merge-base>..HEAD ∩ git diff
--name-only <merge-base>..<remote>/<branch>`.

If overlap is empty → low risk, default to `y`.
If overlap is non-empty → owner must explicitly confirm.

### Step 3 — Working tree check

If `git status --porcelain` is non-empty:
- Without `--auto-stash` → abort: «working tree has uncommitted changes
  on: <list>. Either commit via `/minder:mem:save`, or re-run with
  `--auto-stash`».
- With `--auto-stash` → `git stash push -u -m "minder:mem:sync-data autostash"`,
  remember to pop after.

### Step 4 — Rebase / fast-forward

For dry-run: print the planned operation and exit.

Otherwise:
- Fast-forward case: `git merge --ff-only <remote>/<branch>`.
- Divergence case: `git pull --rebase <remote> <branch>`.

If rebase encounters a conflict:
- Do NOT attempt auto-resolution.
- Run `git rebase --abort` to leave the tree in pre-pull state.
- Print:
  ```
  Конфликт при rebase. Файлы:
    <list of conflicted paths>

  Авто-резолюшен не применяется — это owner data в прозе.
  Что делать:
    1. Зафиксируй локальные правки: /minder:mem:save --no-push
    2. Запусти руками: git pull --rebase origin <branch>
    3. Разруль конфликты в редакторе
    4. git rebase --continue && /minder:mem:save (для push)
  ```
- Exit non-zero.

### Step 5 — Post-pull tasks

If `--auto-stash` was applied → `git stash pop`. If pop conflicts —
inform owner, leave stash in place (`git stash list`).

If pulled commits touched any of:
- `_system/views/CURRENT_CONTEXT.md` → mention «context refreshed».
- `_system/registries/*.md` → mention «registries updated».
- `_records/**` → count new records, report.
- `_sources/inbox/**` → count new transcripts, suggest `/minder:mem:process`.

### Step 6 — Recap

```
Synced.
  Pulled: <N> commit(s) from <remote>/<branch>
  Files:  +<added> ~<modified> -<deleted>
  Notable:
    • <count> new transcript(s) in _sources/inbox/  → /minder:mem:process
    • registries refreshed: PEOPLE, PROJECTS
    • <K> new record(s) in _records/

Working tree: clean.
```

## What this skill does NOT do

- **Pull engine updates.** That is `/minder:mem:update` against `upstream`,
  not `origin`. This skill refuses if `--remote upstream` is passed.
- **Resolve merge conflicts.** Always aborts, hands off to owner.
- **Push.** Read-only against remote (besides fetch). Push is
  `/minder:mem:save`'s job.
- **Modify Minder Memory content.** Only re-arranges git history.

## Idempotency

Up-to-date repo → no-op exit 0. Re-running immediately → no-op.

## Recommended cadence

- Before `/minder:mem:process` if inbox/ may have grown elsewhere.
- Before `/minder:mem:lint` or `/minder:mem:maintain` if processing happens on
  another device.
- After waking up a long-dormant clone.

A producer skill never fires this one mid-pipeline — a surprise rebase
under a running pipeline is the failure it avoids. Two callers invoke it
as an explicit pre-work step, before any lock is taken: the scheduler
prompts (Step 3 of every tick) and `/minder:mem:resolve-clarifications` (its
Step 0, so the queue reflects every device).

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| «working tree dirty» | Uncommitted local edits | `/minder:mem:save --no-push` first, or pass `--auto-stash` |
| «conflict during rebase» | Same file edited on both sides | Resolve manually per the printed instructions |
| «remote upstream rejected» | Wrong remote | Use default `origin`; engine syncs go through `/minder:mem:update` |
| «no upstream branch» | Branch never pushed | Push first via `/minder:mem:save` |
