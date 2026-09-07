---
id: minder-mem-role-edit-skill
title: 'Skill: /minder:mem:role:edit'
type: skill
created: 2026-07-28
modified: '2026-07-28'
tags:
- type/skill
- topic/automation
- topic/roles
---

# /minder:mem:role:edit

Pointer card. The full flow lives in the installed skill, not here.

## Sources of truth

- **Flow, incl. how a role reference is resolved:**
  `~/.claude/skills/minder-mem-role-edit/SKILL.md` (after `install.sh`). That
  resolution is written once there; `list` and `ask` reference it.
- **What it edits:** `_system/roles/{id}/role.md`, and — on a credential
  rotation only — the encrypted value in `_system/state/secrets.enc.json`.
  Nothing else.
- **What runs the result:** [[minder-mem-roles]].
- **Full orientation card:** [[CLAUDE_MINDER_MEMORY]].

## What it does (one paragraph)

Resolves a role from a free-text reference — display name, id, or a garbled
dictation of either — confirming on a fuzzy match and never guessing. Shows what
the role is now in plain language, takes the change, validates before writing,
and never leaves an invalid definition on disk. Lifecycle is the same path:
pausing a role and resuming it are `status:` changes, not a separate ceremony.
Changing what a role writes or when it wakes needs no re-baselining, because the
state files are the role's own and nothing tracked depends on their shape.

## When to use

- The role does the wrong thing, or the right thing at the wrong time.
- Pause a role that is noisy, failing, or no longer wanted — without deleting
  what it has accumulated.
- Point a role at a different destination or a different credential.

## When NOT to use

- Creating a role — [[minder-mem-role-add]].
- Reading what a role knows — [[minder-mem-role-ask]].
- Hand-editing `role.md` in an editor: the skill validates before writing, a
  hand edit does not, and an invalid definition surfaces at 07:00.

This card carries no flow detail of its own.
