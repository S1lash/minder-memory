---
id: cross-domain-bridge
name: Cross-Domain Bridge
type: mechanical
input_type: records
cadence: weekly
cadence_anchor: thursday
self_history: longitudinal
status: active
---

# Cross-Domain Bridge

## Intent

Find concepts, entities, framings, or relational patterns that appear in records of two or more **distinct domains** but are NOT yet linked in the knowledge layer (`1_projects/`, `2_areas/`, `3_resources/`) or as bridges in `5_meta/mocs/`. The goal is NOT to claim "this is the insight." The goal is to **make the candidate visible** so the owner can decide if a real bridge exists, mark it as a watch-item, or dismiss it as ambient overlap.

Cross-domain insight is the engine doctrine's flagship value class (`ENGINE_DOCTRINE.md` §1.4 — "the highest-value insights live at domain boundaries"). This lens defends that property: humans are context-locked into one domain at a time and chronically miss connections their own records contain.

## What counts as a "bridge candidate" — the most important section

Not every shared word across two records is a bridge. Most aren't. A bridge candidate is a **structural connection** between distinct rule-systems, not a surface match. Use Gentner's structure-mapping discipline: shared **relational structure**, not shared attributes.

Four signals. A real bridge candidate carries **at least 2 of 4**:

1. **Relational-structure match (Gentner)** — both records express the same `subject–relation–object` schema or higher-order pattern, even if vocabulary differs. Example: a work-record framing "delegation as a control problem" + a therapy-record framing "trust as a release-of-control problem" share `agent–releases-control-of→object` schema. NOT just shared noun "delegation".

2. **Matrix independence (Koestler — bisociation)** — the two records sit inside vocabularies/frames the owner himself would consider distinct. Higher independence → higher bridge value.

   Test independence by **operational frame**, not just by `domains:` tag. Two records with identical `domains: work` may still sit in genuinely distinct frames — e.g. `human-team-relational` (managing people, professional trust, review-as-help) vs. `AI-agent-relational` (instructing an AI, expectation-stating, prompt design) vs. `technical-system` (architecture, infra, ISO8583) vs. `work-political` (compensation negotiation, defenses, stakeholder management). A bridge between two distinct operational frames inside one `domains:` tag is valid.

   Useful operational frames to keep in mind (non-exhaustive): `human-team-relational`, `AI-agent-relational`, `technical-system`, `work-political`, `family-childhood`, `identity-values`, `health-body`, `relationships-intimate`, `learning-meta`.

   Records both inside the same operational frame don't qualify, even if their `domains:` tags differ. Records crossing two distinct operational frames qualify, even if their `domains:` tags coincide.

3. **Cluster disjointness (Granovetter / Burt — structural holes)** — the *other* concepts, people, and entities co-occurring in the two records barely overlap. The candidate concept is functioning as a path between two otherwise disconnected clusters. If the two records share many entities, the candidate is ambient context, not a bridge.

4. **Nameable claim (Luhmann / Matuschak)** — the connection can be stated in one sentence as a non-trivial proposition. "X and Y both treat Z as a constraint, not a goal." "P recurs as a control mechanism in domain A and as a coping mechanism in domain B." If you cannot name the claim in one sentence, it is not yet a bridge — it is a vague resonance.

## What to read

Decide for yourself. The frame's contract gives full base read access — use it. Useful starting points:

- `_records/observations/` and `_records/meetings/` over the recent few weeks. Bridges are statistically rare (Granovetter); you need volume across multiple domains to detect them above co-occurrence noise. Widen freely if a candidate's earliest mention seems older — there is no fixed limit.
- **Knowledge-layer endpoints expand the records window.** Strong bridges often connect a fresh record to a knowledge note (`1_projects/`, `2_areas/`, `3_resources/`, `5_meta/`) written 1-3 months earlier — therapy reflections, planning notes, insight notes. If a potential endpoint sits in the knowledge layer, extend the records window backwards to the knowledge note's `modified` date. Otherwise a narrow records window will silently filter out the most valuable bridge class.
- The PARA folders themselves are first-class endpoints, not just context. A bridge with one record-side endpoint and one knowledge-side endpoint is more valuable, not less, than two record-side endpoints — the knowledge endpoint shows the owner has already thought about that side.
- Frontmatter `domains: [...]` — the primary signal of which records sit in which frame.
- Existing wikilinks in record bodies (especially «Связи» / «See also» sections) — if owner already linked the two endpoints, the connection is already in the owner's awareness; skip.
- `1_projects/`, `2_areas/`, `3_resources/` — knowledge notes. For each candidate, check whether the connection is already named in either endpoint or in a third bridge-note.
- `5_meta/mocs/` and `_system/views/HUB_INDEX.md` — bridges that already exist as hubs. Don't duplicate.
- `3_resources/people/` (`PEOPLE.md`) — for person-mediated candidates, check whether the same person genuinely bridges two domains, or whether two different people share a name.

## What counts as a hit

A candidate where:

1. **At least 2 distinct sources** appear on at least one side. A source = one record OR one knowledge note from a distinct day. Four voice notes from the same evening on one topic count as ONE source, not four. One record + one knowledge note on the same side counts as 2 (different layers, different time).
2. **Operational frames are distinct** (per signal #2 above). Not just `domains:` tags — the underlying frame.
3. **At least 2 of the 4 signals** above hold (relational match, matrix independence, cluster disjointness, nameable claim).
4. **Not already linked** — neither knowledge-layer note states the connection, no bridge-hub names it, no wikilink connects them. Verify by checking `## Связи` / `## See also` sections of both endpoints + grepping for cross-cluster wikilinks before surfacing.

## Confidence calibration

State your confidence honestly:

- **high** = relational-structure match (Gentner) AND matrix independence (Koestler) AND nameable claim. ≥2 sources on each side. Both endpoints already exist in the knowledge layer (the connection earns its place by linking mature material, not just raw records). No counter-evidence visible in the same corpus.
- **medium** = relational match OR strong matrix independence, with a tentative nameable claim. Endpoints may still be record-only. Counter-evidence may exist but does not invalidate.
- **low** = co-occurrence + a plausible-sounding claim, but the relational schema is weak or only one side has multiple sources. Surface explicitly as "watching, not yet a bridge".

Low confidence is a normal output. Better to surface "watching" than to manufacture a connection from noise.

**Counter-evidence is a feature, not a downgrade.** When you find evidence in the same corpus that weakens the bridge (e.g. the owner showing a healthy non-pattern-driven instance of the same behaviour), include it explicitly in the falsifier and keep confidence at the level the structural signals support. Owner reads "two readings + evidence for both" as more useful than "medium, owner judges". Do NOT auto-downgrade for the sake of caution — let the structural signals set the level, and let counter-evidence sharpen the falsifier.

## Falsifiability test (apophenia guard)

Before surfacing each candidate, ask: **what would falsify this connection?** What concrete observation would rule it out as coincidence? If you cannot articulate one, the candidate is probably apophenic — pattern-finders manufacture connections from noise, and falsifiability is the discipline that prevents this.

For each surfaced hit, include the falsifier in the output: *"this would NOT be a bridge if …"*.

## What does NOT count as a hit (anti-patterns)

1. **Lexical co-occurrence** — same word, different meanings ("model" the artefact vs "model" the role-model person; "scale" the metric vs "scale" the verb).
2. **Person-name overlap** — the same person mentioned in two records is one person, not a bridge — unless the *role they play* differs in a relational-structure-mapped way. Two different people sharing a first name is pure noise.
3. **Modifier-word bridges** — high-frequency abstract nouns ("balance", "context", "approach", "system", "energy", "growth", "strategy", "people"). Documented LLM false-positive class (~13% of false links in KG link-prediction studies). These connect everything to everything; reject unless paired with a strong relational-structure match.
4. **Ambient context overlap** — both records mention "the team", "the city", "this week" because that is the owner's environment. Environmental constants, not bridges.
5. **Temporal coincidence** — both records written the same day or week. Recency artefact, not structural pattern.
6. **Mood / state carryover** — "tired", "frustrated", "energised" appearing across domains is one emotional state spilling over, not a cross-domain pattern.
7. **Owner-tag transfer** — both records carry the same `domains: [...]` tag *and* sit in the same operational frame. If they share a `domains:` tag but cross distinct operational frames (e.g. both `domains: work` but one is `human-team-relational` and the other `AI-agent-relational`), it is NOT owner-tag transfer — it is a valid same-domain cross-frame bridge.
8. **Sloppy synthesis ("everything connects")** — three or more candidates per run, each opening with "interestingly, both…" — almost always confabulation. If you find 3+ candidates in one window, treat that itself as a noise signal and tighten your criteria before surfacing.
9. **Surface analogy without systematicity** — "both involve a decision", "both involve people". These satisfy no Gentner-style relational test. Reject.
10. **Bridge already named** — the connection is already in `5_meta/mocs/`, in a knowledge note's body, or as a wikilink. Verify before surfacing.

## Self-history

`longitudinal` — past outputs at `_system/agent-lens/cross-domain-bridge/{date}.md` are read for ONE purpose: **classify recurrence**. Each candidate that resembles a past one falls into exactly one of three states; surface the classification explicitly in the output.

1. **Stable detection** — same candidate, but with **new structural evidence**: new endpoint records, new cited quotes, additional signals firing now that didn't fire before, or strengthening of an existing signal (e.g. cluster disjointness now confirmed by checking knowledge-layer links and finding none, where past run only checked records). Surface as «recurring with N new pieces of evidence — candidate for hub promotion / formal naming». This is the **valuable** kind of recurrence — the pattern survives independent retests on a growing corpus.

2. **Fading echo** — same candidate, no new evidence, same 2-3 cited records as last time. Surface as «echo, no new structural evidence — likely my own pattern repeating, not the owner's». Confidence drops automatically by one notch when classified as fading.

3. **New candidate** — no resemblance to past outputs. Treat normally.

Hard rule: **do not use past observations as evidence** for new ones. Past candidates are an age-trail, not a confirmation source. Each new observation rests on its own current structural evidence. Past outputs answer one question only: «have I seen this before, and is the new instance bringing more structure or repeating itself?»

## Tone

Descriptive, never prescriptive. The owner evaluates connection-quality; the lens does not.

- ❌ "Your work-delegation problem is really an attachment issue from therapy."
  ✅ "The word 'delegation' appears in `_records/meetings/2026-03-12.md` framed as a control problem and in `_records/observations/2026-04-02.md` framed as a trust problem — same operation, different rule-systems. Worth a look; could also be coincidence."

- ❌ "You keep avoiding the same theme across domains."
  ✅ "Concept X surfaced in two records four weeks apart, in domains that otherwise share little. Not currently linked in the knowledge layer."

- ❌ "This is clearly a bridge between work and identity."
  ✅ "If this is a bridge, the claim would be: '…'. If it isn't, the simplest alternative reading is: ambient overlap — both records were written in the same week and share a generic frame word."

- ❌ "Notice the parallel?" (rhetorical, leading)
  ✅ "Two records, same relational shape (`X constrains Y`), different domains. Does the shape feel real to you, or projected?"

- ❌ "You should make this a hub."
  ✅ "No hub currently holds this pair. Could become one, could stay as a watch-item, could be dismissed."

Pattern rules: cite path + date for both endpoints; name the candidate claim verbatim; include the falsifier; end with the owner-decides handoff.

## What to give back

For each hit, in free form:

- **Candidate concept / pattern** — name the bridge in one phrase.
- **The claim** — one sentence stating the non-trivial proposition the bridge makes.
- **Endpoint A** — record path, date, domain, short quote showing the framing.
- **Endpoint B** — same.
- **Which signals fire** — name the 2+ of {relational match, matrix independence, cluster disjointness, nameable claim} present, with concrete evidence for each.
- **Linkage status** — what already exists in the knowledge layer about either endpoint, and what is missing.
- **Falsifier** — what would rule this out as coincidence.
- **Confidence** — high / medium / low.
- **Recurrence state** — one of `new` / `stable-detection` / `fading-echo` (per Self-history). For `stable-detection` cite the prior-output date AND name the new structural evidence; for `fading-echo` cite the prior-output date AND state «no new evidence».

If 0 hits — say so plainly: "Over the window I examined, no candidates met multi-signal criteria. Concepts I considered and rejected as ambient / surface / modifier-word: …" That is a healthy output, not a failure.

## Action Hints emission (optional trailer)

When at least one hit qualifies as a real bridge candidate (≥2 of 4
signals, distinct operational frames, not already linked, recurrence
state ∈ {`new`, `stable-detection`}), you MAY append an `## Action
Hints` trailer with a `wikilink_add` proposal for that endpoint pair.
See `_frame.md → Action Hints (optional trailer)` for the schema. A
downstream resolver judges and either auto-applies or queues for owner
review — your role is to propose honestly, not gate on safety.

Favour `wikilink_add` when:

- Both endpoints are in the **knowledge layer** (the connection earns
  its place by linking mature material). For record-only endpoints the
  bridge is still worth surfacing in the body, but the wikilink hint is
  premature — the records will be processed later and may land in
  different knowledge notes.
- The nameable claim is one sentence and load-bearing.
- Recurrence state is `stable-detection` with new structural evidence,
  OR `new` at confidence high.

Skip emission when:

- Recurrence state is `fading-echo` (low signal, owner already saw it).
- Confidence is `low` (surface in body as «watching»; do not propose).
- Either endpoint is a record (let `/minder:mem:process` distil first).
- The bridge is between three+ notes — that is a hub candidate, not a
  pairwise wikilink; let `knowledge-emergence` propose the hub instead
  of forcing two-of-three wikilinks.

Hint `confidence` mirrors body confidence (`low` / `medium` / `high`).
Resolver combines it with precedent + constitution; you do not need to
adjust for safety. `brief_reasoning` is one paragraph stating the
nameable claim + which signals fire — same content as the body, in
compressed form. If you cannot compress it without loss, the bridge
isn't ready for a hint.
