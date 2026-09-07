---
id: minder-mem-agent-lens-skill
title: 'Skill: /minder:mem:agent-lens'
type: skill
created: 2026-04-30
modified: '2026-04-30'
tags:
- type/skill
- topic/automation
- topic/agent-lens
---

# /minder:mem:agent-lens

Pointer card. The full pipeline lives in the installed skill, not here.

## Sources of truth

- **Pipeline:** `~/.claude/skills/minder-mem-agent-lens/SKILL.md` (after
  `install.sh`).
- **Lens registry:** `_system/registries/AGENT_LENSES.md` — concept,
  schema, cadence semantics, lens lifecycle.
- **Two-stage frame contract:** `_system/registries/lenses/_frame.md` —
  thinker prompt + structurer prompt + validator rules.
- **Per-lens definitions:** `_system/registries/lenses/{id}/prompt.md`.
- **Scheduler-prompt body:**
  `integrations/claude-code/scheduler-prompts/agent-lens-nightly.md`
  (standalone nightly tick at ~03:00; lint+resolve runs separately
  ~2 h later, so lens production stays isolated from resolve
  consumption — prevents confirmation bias on the lens's own
  Action Hints).
- **Full orientation card:** [[CLAUDE_MINDER_MEMORY]] — three layers,
  routing, all Minder Memory skills, conventions.

## What it does (one paragraph)

Reads the lens registry, filters lenses that are due per their
per-lens cadence, runs each through a two-stage pipeline (free-form
thinker LLM → structurer LLM → structural validator), writes
— a lens declaring `output_schema: synthesis-custom` skips the
structurer and writes its final shape itself, validator still enforcing
the frontmatter trio and a non-empty body. It writes
observation snapshots to `_system/agent-lens/{id}/{date}.md`. Each
lens runs in isolation: fresh API context per Stage, no cross-lens
carry-over, no subagent dispatch. Meta lenses (input_type=lens-outputs)
read other lenses' outputs and produce a navigator digest of pointers,
never content. Each observation entity carries the privacy trio per
SKILL Step 5.9 (`origin: personal`, `audience_tags: []`,
`is_sensitive: false` defaults — owner-only by construction since
lens output is internal hypothesis-grade analysis).

## How to add a lens

Use the wizard: [[minder-mem-agent-lens-add]].

This card carries no skill detail of its own.
