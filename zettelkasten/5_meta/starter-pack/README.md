# Constitution starter pack

Optional generic axioms `/minder:mem:bootstrap --with-starter-axioms` can drop
into your `0_constitution/axiom/{domain}/` as starting points. Engine
ships these marked `confidence: starter` and `status: draft`, so it is
obvious at a glance that you have not yet made them yours.

They are visible in your constitution but do **not** auto-load into the
hot `constitution-core` view. What holds them back is `applies_to:` —
`gen_constitution_core.py` selects a principle only when `core: true`,
`status != placeholder`, and `applies_to` contains `claude-code`, and
these ship without it. So adopting one means adding `claude-code` to its
`applies_to`, then re-running `/minder:mem:regen-constitution`. Editing
`confidence` or `status` alone changes nothing — those two fields are
for you, not for the filter.

These are starting points, not prescriptions. Most users:

- keep 1-3 that resonate, edit the wording into their own voice;
- delete the rest;
- write 5-10 of their own over the first month using
  `/minder:mem:capture-candidate` while working with Claude.

If you don't want any starter content, run `/minder:mem:bootstrap` without the
flag — your `0_constitution/` stays empty and grows from your own
captured candidates.

## Files

| File | Domain | One-liner |
|---|---|---|
| `axioms/name-the-tradeoff.md` | ethics | Surface trade-offs explicitly before implementing |
| `axioms/own-your-mistakes.md` | ethics | When something breaks, own it; don't defer or rationalize |
| `axioms/internal-honesty.md` | identity | Don't push externally what you're not honest about internally |
| `axioms/quality-as-respect.md` | identity | Quality is respect for self and for whoever lives with the result |
| `axioms/first-time-hard.md` | work | First implementation of anything reusable should be done well |
| `axioms/long-term-consequences.md` | work | Optimize for the people who'll live with this in 12-24 months |
