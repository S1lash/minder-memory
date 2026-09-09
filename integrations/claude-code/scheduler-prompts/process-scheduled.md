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

**Single-commit guarantee.** This tick produces **exactly one git commit
+ one git push**, both from `bash scripts/scheduler/finalize-tick.sh` at
Step 5. No other path in this prompt commits or pushes. `/minder:mem:save` is
**forbidden** in scheduler ticks — it is an owner-interactive tool. Any
intermediate `git commit`, `git push`, or `git add` outside the helper
scripts listed below is a contract violation.

**Hard prohibitions:**

- Do NOT invoke `/minder:mem:save` in any form. Use `finalize-tick.sh` at Step 5.
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
  The single exception is `record_tick_telemetry.py` at Step 4.9: it reads
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
  `finalize-tick.sh` collapses every dirty owner path into one commit.

**Bash is permitted only for the helper invocations explicitly listed
in the steps below.** Anything else is a contract violation.

## Failure handling

Any non-zero exit from a bash helper, or any skill error / "Unknown skill"
response, triggers this exit path:

```
bash scripts/scheduler/ship-failure-note.sh "<one-line cause>" process-scheduled
```

Then exit `partial` immediately. Do not retry.

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

1. `bash scripts/scheduler/pin-main.sh` — get on fresh `origin/main`,
   capture the starting sandbox branch, and best-effort recover any
   stranded scheduler work from prior ticks via PR-merge sweep.

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
   - When the skill returns, the immediate next action is step 4.5 with
     no intermediate text.

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
     is not stranded: `ship-failure-note.sh` ships through
     `finalize-tick.sh`, so the tick still lands its one commit.
   - When the skill returns, the immediate next action is step 5 with
     no intermediate text.

4.9. `python3 scripts/scheduler/record_tick_telemetry.py process` — append this
   tick's own token consumption to `_system/state/tick-telemetry.jsonl`, read from
   the run's own transcript (main session plus every sub-agent it spawned).

   It runs HERE, before Step 5, because Step 5 is what commits and the
   single-commit guarantee leaves no second commit to carry a line written
   after it. The cost of that ordering is that this tick's own closing
   messages are not in the count; the line records `measured_through` so the
   horizon is explicit rather than implied.

   **This helper always exits 0 and never triggers failure-handling**, even
   when it measures nothing — it writes `status: unmeasured` with the reason
   instead. Its output is informational. Do NOT retry it, do NOT repair it,
   and never abandon a tick because its odometer failed: the tick's real work
   is already done and losing it to a broken measurement would invert every
   priority this step exists to serve.

5. `bash scripts/scheduler/finalize-tick.sh scheduler/process` — the
   single commit + delivery for this tick. The script auto-detects mode:
   - **LOCAL mode** (start branch = main) — single direct
     `git push origin main`.
   - **ROUTINES mode** (start branch = `claude/...` or other non-main) —
     push HEAD to the sandbox branch, `gh pr create --base main --head
     <sandbox>`, then `gh pr merge --squash --delete-branch`. End state:
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

   **No manual push retries.** If `finalize-tick.sh` exits 2 because
   `git push`, `gh pr create`, or `gh pr merge` failed (HTTP 403,
   network, anything), do NOT invent a retry loop with direct git / gh
   calls. The script makes exactly one delivery attempt by design. If
   work could not be delivered, surface the failure via failure-handling
   and exit `partial`; the next tick processes fresh inbox state.

   **Exception — gh missing.** If exit 2 is specifically because
   `"gh CLI not found in PATH"` (Cloud Routines sandboxes don't ship
   gh), proceed to Step 5b INSTEAD of failure-handling.

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
   5. Branch cleanup is automatic. The repo has «Automatically delete
      head branches» enabled in GitHub Settings → General → Pull
      Requests; GitHub removes `<SANDBOX_BRANCH>` the moment the squash
      merge in step 4 completes. No manual delete call is needed.
   6. Print final status: `success <merged-SHA>` and skip Step 6
      failure-handling.

   This is the ONE authorized non-script git/MCP path in this prompt.
   It exists because `finalize-tick.sh`'s gh-based delivery cannot run
   when gh is missing. Outside of «`gh CLI not found in PATH`» exit, do
   NOT invoke any github MCP tool from this prompt — failure-handling
   covers other failure modes.

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
