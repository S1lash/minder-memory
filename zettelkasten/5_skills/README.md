---
id: readme-5-skills
title: Skill reference cards
layer: meta
tags:
- type/structural
created: '2026-08-15'
modified: '2026-08-15'
origin: personal
audience_tags: []
is_sensitive: false
---

# Skill reference cards

**The SKILL is the source of truth.** For every Minder Memory skill, the contract lives in
`integrations/claude-code/skills/{skill}/SKILL.md`. That file is what actually
runs, and it is the only place a behavioural question is answered.

The cards here are a **hand-picked subset** — a convenience for orientation, not
a contract and not an index of what exists. They cover the skills whose shape is
worth holding in your head before you read the real thing. A card that disagrees
with its SKILL is wrong by definition; trust the SKILL and fix the card.

**Cards present:**

| Card | Skill |
|---|---|
| `CLAUDE_ZETTELKASTEN.md` | cross-skill quick reference (not one skill) |
| `minder-mem-process.md` | `/minder:mem:process` |
| `minder-mem-agent-lens.md` | `/minder:mem:agent-lens` |
| `minder-mem-agent-lens-add.md` | `/minder:mem:agent-lens-add` |
| `minder-mem-roles.md` | `/minder:mem:roles` |
| `minder-mem-role-add.md` | `/minder:mem:role:add` |
| `minder-mem-role-edit.md` | `/minder:mem:role:edit` |
| `minder-mem-role-list.md` | `/minder:mem:role:list` |
| `minder-mem-role-ask.md` | `/minder:mem:role:ask` |

Every other shipped skill has no card, and **that means nothing about it** — not
that it is less important, less stable, or unfinished. The full set of skills is
the directory listing of `integrations/claude-code/skills/`.

Adding a card is optional and carries a cost: it is a second description of a
source that changes often, so it drifts. Add one only when the orientation it
buys is worth keeping in sync by hand.
