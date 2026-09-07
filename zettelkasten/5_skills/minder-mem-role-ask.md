---
id: minder-mem-role-ask-skill
title: 'Skill: /minder:mem:role:ask'
type: skill
created: 2026-07-28
modified: '2026-07-28'
tags:
- type/skill
- topic/automation
- topic/roles
---

# /minder:mem:role:ask

Pointer card. The full flow lives in the installed skill, not here.

## Sources of truth

- **Flow:** `~/.claude/skills/minder-mem-role-ask/SKILL.md` (after `install.sh`).
- **What it reads:** `_system/roles/{id}/state/**` and that role's
  `log.jsonl`.
- **How the role fills that state:** the closing section of its `role.md`
  — the one [[minder-mem-role-add]] writes as the role's «close», named in the
  owner's own words rather than by a fixed heading.
- **Full orientation card:** [[CLAUDE_MINDER_MEMORY]].

## What it does (one paragraph)

Answers a question from a role's own memory — the files it keeps under
`state/` plus its run log. Read-only: takes no lock, writes nothing, and never
runs the role to get a fresher answer. When the state does not hold the answer
it says so rather than inventing one, and offers to read the underlying zone of
the base directly instead.

## When to use

- «What has the sync role seen drift on this month?»
- «When did this role last find anything, and what was it?»
- Checking whether a role's memory is actually accumulating what you wanted
  before trusting it.

## When NOT to use

- Forcing a role to run now — that is the tick, [[minder-mem-roles]].
- Changing what the role tracks so it *would* answer — [[minder-mem-role-edit]].

This card carries no flow detail of its own.
