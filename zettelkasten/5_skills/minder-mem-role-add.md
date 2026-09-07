---
id: minder-mem-role-add-skill
title: 'Skill: /minder:mem:role:add'
type: skill
created: 2026-07-28
modified: '2026-07-28'
tags:
- type/skill
- topic/automation
- topic/roles
---

# /minder:mem:role:add

Pointer card. The full concierge flow lives in the installed skill, not here.

## Sources of truth

- **Concierge flow:** `~/.claude/skills/minder-mem-role-add/SKILL.md` (after
  `install.sh`).
- **What it produces:** one `_system/roles/{id}/role.md` + a `state/` dir, and
  a credential, encrypted, in `_system/state/secrets.enc.json` when the role reaches
  outward.
- **What runs the result:** [[minder-mem-roles]].
- **Full orientation card:** [[CLAUDE_MINDER_MEMORY]].

## What it does (one paragraph)

Role creation concierge. The owner says what they want in plain language
(«следи за проектом», «watch whether a topic goes quiet in my notes») and the
skill develops the wish rather than transcribing it: it asks what they would
want to know without having to ask, probes their real notes to show what the
role would actually have found last week, and argues for the higher-leverage
version when their data supports one. It then writes the role file itself —
mechanical frontmatter in English, the three prose sections in the owner's own
language. Before declaring the role done it validates the config, makes a real
call against every declared service, and does a trial run that must do something
meaningful and touch nothing outside the declared paths. A role that fails any of
the three is fixed in the same conversation, not created.

## When to use

- Any standing job the owner would otherwise do by hand on a rhythm.
- A job that needs an outside service — the concierge captures the credential
  and proves it works before the role goes live.

## When NOT to use

- Changing an existing role, or pausing it — [[minder-mem-role-edit]].
- A one-off question about the base — just ask; a role is for recurrence.
- An observation about the owner's own patterns with no outward act and no
  tracked state — that is an agent-lens ([[minder-mem-agent-lens-add]]).

This card carries no flow detail of its own.
