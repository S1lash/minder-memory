---
id: minder-mem-agent-lens-add-skill
title: 'Skill: /minder:mem:agent-lens-add'
type: skill
created: 2026-04-30
modified: '2026-04-30'
tags:
- type/skill
- topic/automation
- topic/agent-lens
---

# /minder:mem:agent-lens-add

Pointer card. The full wizard flow lives in the installed skill, not here.

## Sources of truth

- **Wizard flow:** `~/.claude/skills/minder-mem-agent-lens-add/SKILL.md` (after
  `install.sh`).
- **What lenses are:** [[minder-mem-agent-lens]] + `_system/registries/AGENT_LENSES.md`.
- **Two-stage frame contract:** `_system/registries/lenses/_frame.md`.
- **Full orientation card:** [[CLAUDE_ZETTELKASTEN]].

## What it does (one paragraph)

Lens creation concierge. User says what they want in plain language
(«weekly food review», «watch my recurring stress patterns»,
«psychoanalyst-style observer»); skill detects complexity tier,
shows a concrete preview of what observations the lens would produce,
optionally probes real records to refine, generates a complete lens
(folder + AGENT_LENSES.md row) calibrated to user data and intent.
User never sees frontmatter fields, frame contracts, or other internal
mechanics — those are skill's responsibility. Output passes registry
validation on first try; default activation policy adapts to tier.

## When to use

- Casual idea you want shipped well: «draft me a lens that catches
  when I overcommit».
- Friend onboarding: non-technical user who wants their own
  observation system without learning the schema.
- Iterating on existing lens: `--from-existing <id>` for
  duplicate-and-modify.
- Complex multi-dimensional psyche lens: skill enforces mandatory
  data probe + tone constraints + first-cycle review.

## When NOT to use

- Editing existing lens prompts (just edit `prompt.md` directly).
- Schema extension (new frontmatter field, new self_history value)
  — skill blocks; engine maintainer flow.
- Activating an already-drafted lens (just flip `status: draft` →
  `active` in frontmatter and registry table).

This card carries no flow detail of its own.
