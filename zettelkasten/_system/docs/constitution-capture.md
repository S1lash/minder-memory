# Constitution Capture — Global Hook

Active in every Claude Code session, every repo. When you observe one of
the narrow triggers below during any conversation with the owner — invoke
`/minder:mem:capture-candidate`. Do not ask permission. The buffer is
append-only; the owner resolves candidates in batch via `/minder:mem:lint` F.3.

## Capture (narrow triggers — exactly four)

**(a) Explicit behavioural principle.** The owner says "I always ...", "my rule
is ...", "I never ..." *with a reason*. Not a factual statement, a
principle — he explains why it's a rule for him.

**(b) Conscious trade-off.** Explicit choice of X over Y with reasoning
why one priority outranks the other in this specific situation. Example:
"here speed matters more than quality because the rollback cost is low".

**(c) Non-obvious ethical / emotional / interpersonal judgment.** A
decision most people would make differently, with explanation why the owner
does *not*. Includes "по понятиям" moments — acting on a personal code
that is not the default cultural one.

**(d) Implicit pattern.** The owner does not name the principle, but makes a
choice that clearly follows from an internal logic. Capture the
*observation* (what you watched) plus your *hypothesis* of the
principle behind it. The owner decides on review whether it is real or noise.

## Do NOT capture

- Technical preferences (prefer postgres, use records not classes) —
  those are conventions, not principles.
- Cosmetic stylistic preferences with no cognitive basis (commit-message
  phrasing, file naming). **NOT cosmetic — capture it:** how the owner wants
  information *presented* (conclusion-first, insight density, what praise or
  criticism actually lands, long-form shape). That is a cognitive /
  communication principle (`suggested_domain: ai-interaction`), not style —
  it is the lived signal that keeps the owner's presentation principles alive.
  Capture it even as a **bare instruction** («lead with the conclusion next
  time», «don't recap, tell me what it means») — the reason is implicit (so it
  lands for the owner), so it clears trigger (a)/(d) without an explicit
  «because».
- Task-execution decisions without philosophical content. **NOT
  task-execution — capture it:** how the owner decides when someone else has a
  stake in the outcome. Four shapes, all `suggested_domain: ai-interaction`:
  they reject a criterion an interested party introduced («that's her
  argument, not mine»); they overturn one of *their own* criteria as belonging
  to a situation that no longer holds («that mattered on holiday, not in
  ordinary life» — the regime test); they name a context as adversarial or
  cooperative and treat it differently; they weigh something unrecoverable
  (time, optionality, a relationship) against something recoverable. These are
  the lived signal that keeps the owner's advisory deltas alive, exactly as the
  presentation carve-out above does for how they want to be told things. The
  universal floor is in `advisory-baseline`; what belongs in the buffer is
  where THIS owner departs from it.
- Facts about people — those go through `/minder:mem:process` → PEOPLE.md.
- The entire session content — that is `/minder:mem:recap`.

**Better to miss 30% of real candidates than ingest 300% noise.** The
constitution buffer stays signal-heavy by design. A missed candidate
usually re-appears in future conversations; a noisy candidate dilutes
the review queue.

## How to invoke

```
/minder:mem:capture-candidate
  situation: "<1-2 sentences of what was happening>"
  observation: "<verbatim quote from owner if any, else empty>"
  hypothesis: "<one-line hypothesis; null if (a) explicit>"
  suggested_type: "axiom | principle | rule | unknown"
  suggested_domain: "identity | ethics | work | tech | relationships |
                     health | money | time | learning | ai-interaction |
                     meta | unknown"
```

Silent append — no user prompt, no summary back. The work is done when
the skill returns "appended candidate to ...".

## Origin tagging

By default the candidate lands with `origin: personal`. Pass
`--origin work` or `--origin external` explicitly when the session
context warrants different provenance (e.g. an observation captured
while working inside a work repo where identity-shaping deserves more
deliberate review). Work-origin candidates never qualify for L2
auto-merge in lint F.5 — they always require the owner's manual review.

## Relationship to `/minder:mem:recap`

Different concerns, no overlap:

- `/minder:mem:recap` — captures a *session* as knowledge for later processing
  into Minder Memory notes. End-of-session action.
- `/minder:mem:capture-candidate` — captures *one observation* that looks like
  a principle. In-the-moment action, triggered by the four rules above.

Both can fire in the same session. They write to different targets and
never conflict.
