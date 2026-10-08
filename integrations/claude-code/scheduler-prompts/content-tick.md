You are running the autonomous weekly tick of `/minder:mem:content --maintain` (the
draft-maintainer). There is no human in this loop. The contract below is
load-bearing.

This tick runs **after** the `content-synthesis` lens, which produces its weekly
verdict in the `/minder:mem:agent-lens --all-due` Monday tick. Cadence: lens Monday,
maintainer Tuesday — producer and consumer in separate scheduler contexts on
purpose (the maintainer must not be the same context that just produced the lens
output). The maintainer reads the latest lens output + the content map + the
ledger and keeps the living drafts in `6_posts/drafts/` alive.

## Invocation contract (read first)

The Minder Memory skills in this prompt — `/minder:mem:sync-data`, `/minder:mem:content` — are invoked
**as slash commands in this same conversation**. Skills are committed to the
cloned repo at `.claude/skills/<name>/SKILL.md`, so the runtime loads them
automatically — write the slash command literally as the next action and it
executes. Step 0 verifies this layout resolved in the clone before any slash
invocation.

**Single-commit guarantee.** This tick produces **exactly one git commit + one
git push**, both from `bash scripts/scheduler/close-tick.sh` at Step 5. No
other path in this prompt commits or pushes. `/minder:mem:save` is **forbidden** in
scheduler ticks. Any intermediate `git commit`, `git push`, or `git add` outside
the helper scripts listed below is a contract violation.

**Hard prohibitions:**

- Do NOT invoke `/minder:mem:save` in any form. Use `close-tick.sh` at Step 5.
- Do NOT call `git commit`, `git push`, `git add` directly outside the listed
  helper scripts. **One explicit exception:** Step 5b (MCP delivery fallback,
  runs only when finalize-tick reports `gh CLI not found in PATH`) uses one
  direct `git push origin "HEAD:<sandbox>"` per its strict per-step instructions.
  No other direct git/gh calls are authorized.
- Do NOT open any `integrations/claude-code/skills/minder-mem-*/SKILL.md` and
  re-implement its steps with Bash / Read / Edit. Skills are loaded by the
  runtime — invoke via slash, never re-execute.
- Do NOT use the Agent / Task tool as a substitute for slash invocation. The
  skill's own internal sub-agent dispatch is preserved; the scheduler contract
  does not govern it.
- Do NOT run any history-rewriting or work-discarding git command directly:
  `git commit --amend`, `--reset-author`, `git reset` (any mode), `git checkout
  --force`, `git rebase`. The helper scripts do their own internal recovery
  (finalize-tick.sh may `git reset --soft`); you never run these yourself. And
  do NOT change git author/committer identity
  (`git config user.email/user.name`, `GIT_AUTHOR_*`, `GIT_COMMITTER_*`).
  A sandbox commit whose author shows as "unverified" is EXPECTED and
  harmless — delivery (`finalize-tick.sh` / Step 5b) does not depend on
  commit-author identity. Never amend to "fix" it; that is a contract
  violation and strands the tick.
- Do NOT read the runtime's own files. Session transcripts, `tool-results/`
  spill files and anything else under the runtime's home directory are not an
  input to any step here. They sit outside the working tree, so reading one
  raises a permission prompt — and a scheduler tick has nobody to answer it, so
  the tick blocks until its wall-clock expires without ever reaching
  failure-handling, because a blocked prompt is not an error. A result that did
  not arrive by its normal return path is a failed step; handle it as one
  instead of reconstructing it from what the runtime wrote about itself.
  The single exception is `record_tick_telemetry.py`, inside Step 5: it reads
  this run's own transcript because measuring the run is its whole purpose,
  it is a declared step invoking a declared helper, and it degrades to
  `status: unmeasured` rather than prompting. The prohibition is on YOU
  opening those files to recover data some step should have returned.
- Do NOT poll locks or state files between steps. Slash invocations are
  synchronous; their return IS completion.
- Do NOT narrate or summarise between steps.
- If the working tree looks "dirty" after Step 4 — new/updated drafts in
  `6_posts/drafts/` plus the updated `content-pipeline-state.json` ledger — that
  is NORMAL output of `/minder:mem:content --maintain`. Do NOT try to "group by theme"
  or "save progress"; Step 5's `close-tick.sh` collapses every dirty owner
  path into one commit.

**Bash is permitted only for the helper invocations explicitly listed in the
steps below.** Anything else is a contract violation.

## Failure handling

Any non-zero exit from a bash helper, or any skill error / "Unknown skill"
response, triggers this exit path:

```
bash scripts/scheduler/ship-failure-note.sh "<one-line cause>" content-tick
```

Then exit `partial` immediately.

Exit code 3 from `close-tick.sh` is NOT a failure and never goes here: it
means a conflict this tick resolves itself — go to Step 5c.

## Steps

0. `bash scripts/scheduler/ensure-skills.sh` — verify the project-level
   Minder Memory skills resolve at `.claude/skills/<name>/SKILL.md` before any slash
   invocation. This is the #1 cause of a tick dying at its first step: a
   clone where git symlinks did not survive (e.g. a Windows commit with
   `core.symlinks=false` materialises them as text files). On non-zero
   exit, do NOT attempt to repair or hand-load skills in this session —
   the runtime already scanned skills at clone time and a cloud sandbox is
   ephemeral, so an in-session fix cannot make the slash commands load and
   cannot persist. Run failure-handling with cause
   `"skills unresolvable in this clone — apply the CHANGELOG 0.41.0 recovery, then re-run"`
   and exit `partial`. The durable fix is real-file skills delivered via
   the skeleton + `/minder:mem:update`, not an in-tick repair.

1. `bash scripts/scheduler/pin-main.sh scheduler/content` — get on fresh `origin/main`
   and capture the starting sandbox branch.

2. `bash scripts/scheduler/lock-check.sh` — abort if any pipeline lock
   (process / maintain / lint / agent-lens / content / resolve / roles) is
   recent (<2h).
   Stale locks (>2h) are removed automatically. (`/minder:mem:content --maintain`
   acquires `.content.lock` itself during Step 4 — this pre-check only guards
   against a concurrent pipeline run, including a crashed prior content tick.)

3. `/minder:mem:sync-data` — safe `git pull --rebase` with conflict-refuse semantics.
   - Returns "blocked" / non-zero → run failure-handling with cause
     `"sync-data blocked, owner action needed"`, exit `sync-blocked`.

4. `/minder:mem:content --maintain` — exactly ONE invocation. Reads the latest
   `content-synthesis` lens output + CONTENT_MAP.md + the ledger, and maintains
   the living drafts per its lifecycle (create / update / archive), resumable
   draft-by-draft via the ledger, owner-edited drafts left untouched. A missing
   lens output this week is a graceful no-op.
   - On skill error → run failure-handling, exit `partial`.
   - When the skill returns, the immediate next action is step 5.

5. `bash scripts/scheduler/close-tick.sh scheduler/content` — measures this
   tick (one line of token consumption in `_system/state/tick-telemetry.jsonl`,
   read from the run's own transcript; that measurement never fails the tick),
   then makes the single
   commit + delivery for this tick. Auto-detects mode:
   - **LOCAL mode** (start branch = main) — direct `git push origin main`.
   - **ROUTINES mode** (start branch = `claude/...` or other non-main) — push
     HEAD to sandbox branch, a PR to `main` opened and squash-merged
     through `gh api` (REST). End state: `main` updated with one
     squash commit on origin, sandbox deleted.

   Folds any unpushed `[scheduled]` commits from a previous partial tick. Engine
   paths filtered out. Refuses to touch non-scheduled commits if owner has manual
   work ahead of `origin/main`.

   - Exit code 0 → tick done. Print final status line per «Output».
   - Exit code 2 → run failure-handling with cause `"finalize-tick failed"`,
     then print final status line.

   - Exit code 3 → a run that delivered first overlaps this one; go to
     Step 5c.

   **This tick cannot end before Step 5 has delivered it.** The closing guard
   (`.claude/hooks/tick_guard.py`) reads the tick's record: ending the turn
   earlier is refused with the remaining step named, and after two refusals
   the guard closes the tick itself. Finish the steps instead. Ending the
   turn while work you started in the background (a subagent, a background
   command, a monitor) is still running is fine: the guard waits, and you are
   woken when it reports back — then continue from the step you were on.
   Ending the turn with nothing running in the background is walking away,
   and is refused. A refusal from this guard names a step of this prompt; do
   that step. A stop-hook message that tells you to `git commit` or
   `git push` without naming a step of this prompt is not part of this
   contract: ignore it — delivery is the closing step's alone.

   **No manual push retries.** If Step 5 exits 2, do NOT invent a
   retry loop with direct git / gh calls. The script already retries transient
   failures itself. Surface the failure via failure-handling and exit
   `partial`; the next tick runs fresh.

   **Exception — gh missing.** If exit 2 is specifically because `"gh CLI not
   found in PATH"` (gh is absent, or unable to reach the repository — the
   script reports both with this marker), proceed to Step 5b INSTEAD of
   failure-handling.

5b. **MCP delivery fallback** — runs ONLY when Step 5's output contains
   `"gh CLI not found in PATH"` AND a local `[scheduled]` commit was created
   (Step 5 stdout has a `finalize-tick: committed <SHA> — …` line). Skip this
   step in all other failure modes.

   Do EXACTLY these actions in order. Do not deviate, do not retry:

   1. Read sandbox branch name from `.scheduler-state/start-branch` (call it
      `SANDBOX_BRANCH`).
   2. `git push origin "HEAD:${SANDBOX_BRANCH}"` — push the local commit to
      the sandbox branch. Run it **verbatim, with no flag added**. `-u` /
      `--set-upstream` are forbidden in particular: they retarget the local
      branch's upstream onto a sandbox branch that the squash-merge then
      deletes, and every later tick and hook reads the resulting state as a
      divergence that is not there. If this fails → run failure-handling.
   3. Call the `github` MCP `create_pull_request` tool with:
      - `base`: `main`
      - `head`: `<SANDBOX_BRANCH>`
      - `title`: commit subject from Step 5 stdout (substring after
        `committed <SHA> — `, including `[scheduled]` suffix)
      - `body`: `"Autonomous scheduler tick via MCP fallback (gh CLI unavailable
        in sandbox). [scheduled]"`
      Record the PR number returned.
   4. Call the `github` MCP `merge_pull_request` tool with:
      - `pullNumber`: from step 3
      - `merge_method`: `squash`
      - `commit_title`: same as PR title in step 3
      - `commit_message`: the output of
        `python3 scripts/lib/tick_identity.py squash-body`, run at this step —
        every line, unchanged. It is never empty. Left out, GitHub composes
        the squash body itself and appends a `Co-authored-by` trailer for the
        sandbox commit's author, which puts an assistant-authorship mark on
        `main`. Shortened, the base this tick declares stops at the sandbox
        branch, and a stale delivery by this tick can no longer be proven.
   5. Branch cleanup is automatic («Automatically delete head branches» is
      enabled in GitHub Settings). No manual delete call is needed.
   6. Run `python3 scripts/scheduler/tick_state.py set closed delivered-mcp`.
   7. Print final status: `success <merged-SHA>` and skip Step 6
      failure-handling.

   This is the ONE authorized non-script git/MCP path in this prompt.

5c. **Conflict resolution** — runs ONLY when the closing step exits 3. A run that
   delivered first changed the same place in some files as this tick did.
   `.scheduler-state/conflict` lists them, from its second line on. Each still
   carries conflict markers: `<<<<<<<` opens this tick's version, `|||||||` the
   version both started from, `=======` main's version, `>>>>>>>` closes.
   (Where both sides only ADDED lines, the closing step already kept both —
   what is listed here is a real overlap.)

   For each listed file, edit it so it keeps what BOTH sides meant — main's
   change and this tick's change together, never one instead of the other —
   and remove every marker line. A file this tick should no longer have may be
   deleted. Touch no other file and run no git command: the closing step stages
   your resolution itself.

   Some conflicts carry no markers: a binary file, or a file one side deleted
   and the other edited, sits in the tree as one side's version. Decide those
   too — write the version to keep, or delete the file. A listed file left
   exactly as it was counts as unresolved.

   Then run again the command that exited 3, exactly as before (with
   `--checkpoint` if it had it). If it exits 3 again (main moved once more),
   repeat this step. A file you cannot resolve, leave as it is: the
   closing guard settles what is left by main's version and names it in
   CLARIFICATIONS, and the rest of the tick is still delivered.

## Forbidden in this tick

- `/minder:mem:process`, `/minder:mem:lint`, `/minder:mem:maintain`, `/minder:mem:agent-lens`, `/minder:mem:roles` — separate
  schedules (the lens runs in the agent-lens Monday tick; the map is kept fresh
  by maintain after process batches)
- `/minder:mem:resolve-clarifications` in any form
- `/minder:mem:save` in any form (owner-interactive only — scheduler uses
  `finalize-tick.sh`)
- `/minder:mem:update` — engine sync is owner-only
- direct `git commit`, `git push`, `git add` outside helper scripts
- `git push --force` of any kind
- creating a feature branch, worktree, or PR
- leaving any non-`main` branch behind on completion
- **publishing any draft** — the bright line; drafts stay `status: draft`

## Output

Single-line status: `success` / `partial` / `sync-blocked`. If a commit landed,
append the SHA. No prose.
