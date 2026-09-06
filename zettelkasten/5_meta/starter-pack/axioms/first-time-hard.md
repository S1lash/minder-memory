---
id: axiom-work-starter-001
title: First time do it hard — so it's easy forever after
type: axiom
domain: work
statement: >
  When building something for the first time that you'll reuse — a
  library, a process, an integration, a script — over-invest in
  quality, generality, and clarity on the first pass. Cheap-first
  costs compound; thorough-first amortizes.
priority_tier: 1
framing: positive
binding: soft
core: true
scope: shared
applies_to: [minder-memory]
derived_from: []
contradicts: []
confidence: starter
status: draft
created: 2026-04-28
last_reviewed: 2026-04-28
last_applied: null
source_weight:
  own_experience: 0
  external_author: 5
---

# First time hard — so it's easy forever after

## Statement

The first implementation of something reusable sets the cost of every
future use. Done properly the first time — proper interfaces, decent
observability, sensible defaults, tests where it counts — every
subsequent use is cheap. Done sloppily, every subsequent use is a tax
plus a hidden risk.

## Why hold this

Rework is the most expensive type of work. Stack-of-debt grows
geometrically; each new fix on top of an old hack is more expensive
than the previous one. Up-front investment is economically superior
even when it feels heavy in the moment.

## Edge cases — when not to apply

- True throwaway prototypes (validating a hypothesis, probing an API,
  proof-of-concept) — explicitly TTL'd. Be honest with yourself when
  "throwaway" is real vs when it's a self-justification.
- Exploratory research where scope isn't clear yet — premature
  architecture is waste. Iterate quickly, then invest once direction
  is confirmed.

## Edit me

This axiom is well-established in engineering culture; consider
keeping it. Tighten the edge cases to match your own judgement of
when "good enough fast" beats "good".
