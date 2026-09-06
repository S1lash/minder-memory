---
id: soul
layer: system
modified: REPLACE_WITH_DATE
---

# SOUL

> Identity + Current Focus + Working Style + Active Goals.
> Maintained manually. Focus shift detection — suggestion in `/minder:mem:lint`.
>
> **Bootstrap:** `/minder:mem:bootstrap` interviews you and fills the sections below
> on first run. Edit freely afterwards. The Values auto-zone (between markers)
> is regenerated from `0_constitution/` and must not be hand-edited.

## Identity

- **Name:** {Your full name as you'd like agents to refer to you}
- **Role:** {Current professional role / occupation}
- **Location:** {City, Country}
- **Timezone:** {IANA tz, e.g. Europe/Berlin (UTC+1)}
- **Language:** {Primary language for notes; secondary for code/metadata}
- **Domain:** {Industry / domain expertise — one sentence}
- **Experience:** {Years + summary, optional}

## Values

> Free-form bullets — what you stand for, what trade-offs you make consciously.
> Used to calibrate skill behaviour (see `5_meta/PROCESSING_PRINCIPLES.md`
> Values Profile section).

- {Core value 1 — short statement + reason}
- {Core value 2 — ...}
- {Core value 3 — ...}

## Current Focus

> Derived from TASKS.md streams (density of last 4 weeks) + open threads.
> Split into **Work** and **Personal** to mirror TASKS.md sections.
> Refreshed by `/minder:mem:bootstrap` and reviewed manually.

### Work

- {Active focus area 1}
- {Active focus area 2}

### Personal

- {Active focus area 1}
- {Active focus area 2}

## Working Style

> How you prefer to operate — used by skills to align outputs with you.

- **Communication:** {Direct / structured / Socratic / ...}
- **Cadence:** {Async-first / sync-heavy / mixed}
- **Capture preference:** {Voice-first / written / mixed}
- **Review cadence:** {Daily / weekly / monthly}

## Active Goals

> Outcome-level goals (3-12 month horizon). Concrete tasks live in TASKS.md.

1. {Goal 1 — outcome statement}
2. {Goal 2 — ...}

## Values (auto-zone)

> Auto-rendered from `0_constitution/` core principles by
> `_system/scripts/render_soul_values.py`. Do NOT hand-edit between the
> markers — drift is detected and reported as CLARIFICATION.

<!-- soul-values:start -->
{populated by render_soul_values.py — empty until first principle lands}
<!-- soul-values:end -->

## Context for Agents

> Plain version: the assistant already answers you conclusion-first, no fluff,
> by default (the shipped "communication baseline"), and already works FOR you
> rather than refereeing between you and the world (the shipped "advisory
> baseline"). This section is where YOU add anything specific to you. Leave it
> empty and the sensible defaults apply.

### How I like answers (optional)

> e.g. "Praise me with facts, not labels — tell me what I did, not that I'm
> great. Criticism only if it's concrete and tells me what to change. I think
> in systems — give me the big picture before the details."

{Write yours here, or leave blank.}

### Long-form deliverables (optional)

> Your long-form recipe lives in its own file — `_system/long-form-playbook.md`
> (loaded on demand, only for an actual long-form piece, never for normal
> answers). Edit it there.

### Decisions where someone else has a stake (optional)

> How a decision with a third party, high stakes, or no way back gets worked
> through lives in `_system/decision-advisory-playbook.md` — also loaded on
> demand, never for normal answers. Edit it there.
