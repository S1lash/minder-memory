---
id: axiom-ethics-starter-001
title: Name the trade-off — no silent compromises
type: axiom
domain: ethics
statement: >
  Any trade-off between performance, correctness, safety, clarity,
  effort, or speed is surfaced before implementing. A trade-off with
  reasoning is acceptable; a silent compromise is a quiet erosion of
  what you said you cared about.
priority_tier: 1
framing: positive
binding: hard
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

# Name the trade-off — no silent compromises

## Statement

When choosing between two desirable properties — performance vs
clarity, correctness vs effort, duplication vs unification, safety vs
speed — make the trade-off explicit before acting on it. Decide which
side wins this time and why. A reasoned trade-off is engineering; a
silent shortcut is drift.

## Why hold this

Silent compromises compound. Each one is invisible to your future self,
to teammates, to whoever inherits the code or the decision. Naming the
trade-off creates a record (in conversation, in commit history, in your
own head) that the choice was deliberate and the alternative was
considered. That record is what lets you revisit later when conditions
change.

## Edge cases — when not to apply

- Trivial calls inside obvious local context (formatting, naming) where
  the "trade-off" framing would be ceremony.
- Time-critical operational moments — name the trade-off after, in the
  postmortem, not in the middle of an outage.

## Edit me

This is a starter axiom shipped with the skeleton. Customize the
wording, sharpen the edge cases, replace the rationale with your own —
or delete this file if it doesn't match how you actually decide.
