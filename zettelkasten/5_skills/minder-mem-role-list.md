---
id: minder-mem-role-list-skill
title: 'Skill: /minder:mem:role:list'
type: skill
created: 2026-07-28
modified: '2026-07-28'
tags:
- type/skill
- topic/automation
- topic/roles
---

# /minder:mem:role:list

Pointer card. The full flow lives in the installed skill, not here.

## Sources of truth

- **Flow:** `~/.claude/skills/minder-mem-role-list/SKILL.md` (after `install.sh`).
- **What it reads:** each `_system/roles/{id}/role.md` and the tail of its
  `log.jsonl`.
- **Full orientation card:** [[CLAUDE_ZETTELKASTEN]].

## What it does (one paragraph)

Enumerates the roles that exist: what each one watches, when it last ran and how
that run ended, whether it is active or paused. Read-only — takes no lock,
writes nothing, runs nothing. With no roles set up it says so and offers to
create one.

## When to use

- «What do I actually have running?»
- Before editing or asking, to get the role's real name.
- After a scheduled tick, to see at a glance which roles fired.

## When NOT to use

- To find out what a role has learned — [[minder-mem-role-ask]] answers from its state.
- To debug a specific failure — read `_system/roles/{id}/log.jsonl` directly;
  the run line carries the reverted and reported-only paths.

This card carries no flow detail of its own.
