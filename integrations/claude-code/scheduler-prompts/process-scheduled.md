You are running an autonomous scheduled tick of `/minder:mem:process`. There is
no human in this loop. The contract below is load-bearing.

## Invocation contract (read first)

The Minder Memory skills in this prompt — `/minder:mem:sync-data`, `/minder:mem:process`,
`/minder:mem:maintain` — are
invoked **as slash commands in this same conversation**. Skills are
committed to the cloned repo at `.claude/skills/<name>/SKILL.md`, so the
runtime loads them automatically — write the slash command literally as
the next action and it executes. Step 0 verifies this layout resolved in
the clone before any slash invocation.

**Two-delivery guarantee.** This tick delivers to `main` at most twice, and
only from `bash scripts/scheduler/close-tick.sh`: once at Step 4.1, with the
processed records, before maintain begins, and once at Step 5, with what
maintain integrated. A run cut short during maintain — the longest stretch of
the tick — no longer takes its records down with it. No other path in this prompt commits or pushes. `/minder:mem:save` is
**forbidden** in scheduler ticks — it is an owner-interactive tool. Any
intermediate `git commit`, `git push`, or `git add` outside the helper
scripts listed below is a contract violation.

**Hard prohibitions:**

- Do NOT invoke `/minder:mem:save` in any form. Use `close-tick.sh` at Step 5.
- Do NOT call `git commit`, `git push`, `git add` directly. The only
  allowed git mutations come from the helper scripts listed in the
  steps, with one explicit exception: Step 5b (MCP delivery fallback,
  runs only when finalize-tick reports `gh CLI not found in PATH`) uses
  one direct `git push origin "HEAD:<sandbox>"` per its strict per-step
  instructions. No other direct git/gh calls are authorized.
- Do NOT open `integrations/claude-code/skills/minder-mem-*/SKILL.md` and
  re-implement its steps yourself with Bash / Read / Edit. Skills are
  loaded by the runtime — invoke via slash, never re-execute.
- Do NOT use the Agent / Task tool as a substitute for slash invocation.
  Each Minder Memory skill must enter through its slash form in this same
  conversation. (The skill's own internal Task dispatch — specifically
  `/minder:mem:process` Step 3 per-batch sub-agents — IS preserved; that fires
  inside the skill invocation as the skill's own architecture.)
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
- Do NOT poll locks, `git status`, or any state file to infer skill
  progress. Slash invocations are synchronous; their return IS completion.
- Do NOT narrate or summarise between steps. After each step returns, the
  next action is the next step's command with no intermediate prose.
- If the working tree looks "dirty across many categories" after Steps 4
  and 4.5, that is NORMAL output of `/minder:mem:process` + `/minder:mem:maintain`. Do
  NOT try to "group by theme" or "save progress" — Step 5's
  the closing step collects every dirty owner path into its commit.

**Bash is permitted only for the helper invocations explicitly listed
in the steps below.** Anything else is a contract violation.

## Failure handling

Any non-zero exit from a bash helper, or any skill error / "Unknown skill"
response, triggers this exit path:

```
bash scripts/scheduler/ship-failure-note.sh "<one-line cause>" process-scheduled
```

Then exit `partial` immediately. Do not retry.

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

1. `bash scripts/scheduler/pin-main.sh scheduler/process` — get on fresh `origin/main`
   and capture the starting sandbox branch.

2. `bash scripts/scheduler/lock-check.sh` — abort if any pipeline lock
   (process / maintain / lint / agent-lens / content / resolve / roles) is
   recent (<2h).
   Stale locks (>2h) are removed automatically.

3. `/minder:mem:sync-data` — safe `git pull --rebase` with conflict-refuse
   semantics, ensures the local clone has the latest owner data from
   any other device that pushed since this Routine started.
   - Returns "blocked" / non-zero on uncommitted local changes or
     unresolvable conflict → run failure-handling above with cause
     `"sync-data blocked, owner action needed"`, exit `sync-blocked`.

4. `/minder:mem:process` — exactly ONE invocation. Per-batch sub-agent
   dispatch fires inside the skill (Step 3) — that is the skill's own
   architecture and IS preserved. The skill ends at its own Step 6 report;
   integration of what it produced is Step 4.5 below, not part of this
   invocation.

   The skill caps its transcript queue per run by default (see
   `/minder:mem:process` §Arguments `--limit`; metric-day / biometric files are
   never capped). That bound is what keeps a large backlog — e.g. after a
   paused scheduler — self-draining across successive ticks instead of
   exhausting one tick's cloud wall-clock and orphaning in-flight sub-agents.
   Do NOT pass `--limit` here — the default is the intended scheduler
   behaviour, and passing a number would duplicate the canonical value.
   - On skill error → run failure-handling, exit `partial`.
   - When the skill returns, the immediate next action is step 4.1 with
     no intermediate text.

4.1. `bash scripts/scheduler/close-tick.sh scheduler/process --checkpoint` —
   delivers what Step 4 produced and keeps the tick open.
   - Exit code 0 → go straight to step 4.5.
   - Exit code 3 → do Step 5c, then run this same command again.
   - Any other exit (including `"gh CLI not found in PATH"`) → do NOT run
     failure-handling and do NOT do Step 5b here; go on to step 4.5. Nothing
     is lost: the work stays in this tick, and Step 5 delivers all of it.

4.5. `/minder:mem:maintain --no-sync-check` — exactly ONE invocation, always,
   whatever Step 4 reported. This is the after-batch integrator, and it
   is the ONLY thing that runs it: threads, hub linkage, back-references,
   tier suggestions, `CURRENT_CONTEXT.md`, `CONCEPTS.md` and the weekly
   biometric / activity workers all live here, and none of them happens
   inside `/minder:mem:process`. A tick that skips this step leaves its own
   batch un-integrated and says nothing — the batch stays in the
   unprocessed set and the next tick's invocation drains it, which is the
   only reason a missed step is recoverable at all.

   It runs as its own step rather than inside `/minder:mem:process` because the
   two skills are mutually exclusive on the cross-skill lock: process
   deletes `.processing.lock` on completion, so maintain may take
   `.maintain.lock` only after the skill has returned.

   `--no-sync-check` is required, not optional: the freshness pre-flight
   PROMPTS when `origin` is ahead, and a scheduler tick has no human to
   answer. Step 3 already synced. Do NOT pass `--batch` — the whole
   unprocessed set is the intended scope, which is what lets a backlog
   self-drain.
   - Empty unprocessed set → the skill exits immediately with "nothing to
     integrate". That is a normal outcome, not an error.
   - On skill error → run failure-handling, exit `partial`. Step 4's work
     is not stranded: it was delivered at Step 4.1, or — if that delivery
     failed — `ship-failure-note.sh` ships it through `finalize-tick.sh`.
   - When the skill returns, the immediate next action is step 5 with
     no intermediate text.

5. `bash scripts/scheduler/close-tick.sh scheduler/process` — measures this
   tick (one line of token consumption in `_system/state/tick-telemetry.jsonl`,
   read from the run's own transcript; that measurement never fails the tick),
   then makes the
   final commit + delivery for this tick. The script auto-detects mode:
   - **LOCAL mode** (start branch = main) — single direct
     `git push origin main`.
   - **ROUTINES mode** (start branch = `claude/...` or other non-main) —
     push HEAD to the sandbox branch, a PR to `main` opened and squash-merged
     through `gh api` (REST). End state:
     `main` updated with one squash commit on origin, sandbox branch
     deleted.

   Folds any unpushed `[scheduled]` commits from a previous partial tick
   into one commit with the current working-tree changes. Engine paths
   are filtered out (logged to CLARIFICATIONS). Refuses to touch
   non-scheduled commits if owner has manual work ahead of `origin/main`.

   - Exit code 0 → tick done. The next action is to print the final
     status line per «Output» below.
   - Exit code 2 → run failure-handling with cause
     `"finalize-tick failed"`, then print the final status line.

   - Exit code 3 → a run that delivered first overlaps this one; go to
     Step 5c.

   **This tick cannot end before Step 5 has delivered it.** The closing guard
   (`.claude/hooks/tick_guard.py`) reads the tick's record: ending the turn
   earlier is refused with the remaining step named, and after two refusals
   the guard closes the tick itself. Finish the steps instead.

   **No manual push retries.** If Step 5 exits 2 because
   `git push`, the PR create, or the PR merge failed (HTTP 403,
   network, anything), do NOT invent a retry loop with direct git / gh
   calls. The script already retries transient failures itself. If
   work could not be delivered, surface the failure via failure-handling
   and exit `partial`; the next tick processes fresh inbox state.

   **Exception — gh missing.** If exit 2 is specifically because
   `"gh CLI not found in PATH"` (gh is absent, or unable to reach the
   repository — the script reports both with this marker), proceed to
   Step 5b INSTEAD of failure-handling.

5b. **MCP delivery fallback** — runs ONLY when Step 5's output contains
   `"gh CLI not found in PATH"` AND a local `[scheduled]` commit was
   created (Step 5 stdout has a `finalize-tick: committed <SHA> — …`
   line). Skip this step in all other failure modes.

   Do EXACTLY these actions in order. Do not deviate, do not retry on
   transient errors (let Step 5b's first failure trip failure-handling):

   1. Read sandbox branch name from `.scheduler-state/start-branch`
      (call it `SANDBOX_BRANCH`).
   2. `git push origin "HEAD:${SANDBOX_BRANCH}"` — push the local commit to
      the sandbox branch. Run it **verbatim, with no flag added**. `-u` /
      `--set-upstream` are forbidden in particular: they retarget the local
      branch's upstream onto a sandbox branch that the squash-merge then
      deletes, and every later tick and hook reads the resulting state as a
      divergence that is not there. If this fails → run failure-handling.
   3. Call the `github` MCP `create_pull_request` tool with:
      - `base`: `main`
      - `head`: `<SANDBOX_BRANCH>`
      - `title`: the commit subject from Step 5 stdout (the substring
        after `committed <SHA> — `, including the `[scheduled]` suffix)
      - `body`: `"Autonomous scheduler tick via MCP fallback (gh CLI
        unavailable in sandbox). [scheduled]"`
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
   5. Branch cleanup is automatic. The repo has «Automatically delete
      head branches» enabled in GitHub Settings → General → Pull
      Requests; GitHub removes `<SANDBOX_BRANCH>` the moment the squash
      merge in step 4 completes. No manual delete call is needed.
   6. Run `python3 scripts/scheduler/tick_state.py set closed delivered-mcp`.
   7. Print final status: `success <merged-SHA>` and skip Step 6
      failure-handling.

   This is the ONE authorized non-script git/MCP path in this prompt.
   It exists because `finalize-tick.sh`'s gh-based delivery cannot run
   when gh is missing. Outside of «`gh CLI not found in PATH`» exit, do
   NOT invoke any github MCP tool from this prompt — failure-handling
   covers other failure modes.

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

- `/minder:mem:lint`, `/minder:mem:agent-lens`, `/minder:mem:content`, `/minder:mem:roles` — separate schedules
- `/minder:mem:resolve-clarifications` — owner-only interactive; auto-mode is
  dispatched by lint Step 7.5, not from process
- `/minder:mem:save` in any form (owner-interactive only — scheduler uses
  `finalize-tick.sh`)
- `/minder:mem:update` — engine sync is owner-only
- direct `git commit`, `git push`, `git add` outside helper scripts
- `git push --force` of any kind
- creating a feature branch, worktree, or PR
- leaving any non-`main` branch behind on completion

## Output

Single-line status: `success` / `partial` / `sync-blocked`. If a commit
landed, append the SHA. No prose.
