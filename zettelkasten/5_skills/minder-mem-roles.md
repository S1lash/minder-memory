---
id: minder-mem-roles-skill
title: 'Skill: /minder:mem:roles'
type: skill
created: 2026-07-28
modified: '2026-07-28'
tags:
- type/skill
- topic/automation
- topic/roles
---

# /minder:mem:roles

Pointer card. The full tick contract lives in the installed skill, not here.

## Sources of truth

- **Tick contract:** `~/.claude/skills/minder-mem-roles/SKILL.md` (after
  `install.sh`).
- **What a role is handed:** `_system/roles/_run-frame.md` (run mechanics) +
  `_system/roles/_minder.md` (how to use the base).
- **The subagent it spawns:** `.claude/agents/minder-mem-role.md`.
- **CLI it drives:** `_system/scripts/roles_run.py`
  (`due` / `context` / `tick-begin` / `role-begin` / `check` / `log`,
  plus `secrets-open` / `secrets-close` around the credential store).
  `validate` is not one of them — it belongs to role creation and
  editing.
- **Scheduler-prompt body:**
  `integrations/claude-code/scheduler-prompts/roles-nightly.md`
  (daily tick at 07:00 — after lint, ahead of the morning process run, so
  an inbox note a role leaves is folded in the same morning).
- **Lock matrix + CLARIFICATION types:** `_system/docs/SYSTEM_CONFIG.md`.
- **Full orientation card:** [[CLAUDE_MINDER_MEMORY]].

## What it does (one paragraph)

Takes `.roles.lock`, snapshots the repository as the tick baseline, then runs
every role whose cadence has elapsed — sequentially, never two at once, each as
a subagent with the ordinary tool set, bounded by its own `timeout_seconds`.
After every run, whatever the outcome, it compares the repository against that
role's own snapshot: paths outside the role's declared `writes:` are reverted,
except where the path was already dirty when that role started — restoring it
would destroy content the role did not author, so it is reported and left alone,
labelled `owner`, `earlier-role`, or `ignored` (an ignore rule made it
invisible during the run, so the guard cannot tell whose it is). In-zone files are scanned, contents and
filename, for every credential on the base — not only the declared ones — in
raw, base64, hex and percent-encoded form;
a hit is pulled out of the commit. One line per executed
run goes to `_system/roles/{id}/log.jsonl`, and that role's own paths are
committed — `[scheduled]` in the subject — before the next role is dispatched.

## When to use

- It is the scheduled tick — normally you never invoke it by hand.
- Manually after creating or repairing a role, to watch one full cycle.

## When NOT to use

- To create, change, list or interrogate a role — that is
  [[minder-mem-role-add]], [[minder-mem-role-edit]], [[minder-mem-role-list]], [[minder-mem-role-ask]].
- From inside a role's own run. The tick already holds `.roles.lock`; a role
  invoking a pipeline skill blocks against its own runner.

This card carries no tick detail of its own.
