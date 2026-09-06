---
id: stalled-thread
name: Stalled Thread Detector
type: mechanical
input_type: records
cadence: weekly
cadence_anchor: monday
self_history: fresh-eyes
status: active
---

# Stalled Thread Detector

## Intent

Find topics, questions, or decisions the owner keeps returning to without moving them forward. The goal is NOT to say "resolve this." The goal is to **make visible** that a thread is hanging, so the owner can either add it to `_system/state/OPEN_THREADS.md`, file a task with a next action, or consciously let it go.

This lens acts as a **feeder for OPEN_THREADS.md**: the hits you produce are candidates the owner reviews and either fixes as an open thread, accepts as just-a-stage-of-thinking, or drops as noise.

## What counts as a "thread" — the most important section

A thread is NOT a keyword that recurs in records. A thread is a **recurring object of attention** with stable shape. Signals of one thread:

- **Recurring question** — the same question ("should I move to X", "how do I delegate Y"), even if phrased differently across mentions.
- **Recurring person + topic pair** — an "X + specific topic" combination, not just X mentioned in the background of unrelated topics.
- **Recurring concrete entity / decision** — the same choice / project / context that the reasoning keeps returning to.
- **Recurring framing** — the same words and angle of attack on the problem, without the formulation evolving between mentions.

If you cannot name the thread in one phrase ("a thread about X" / "a thread of deciding Y") — it is probably ambient context, not a thread. Ambient context is NOT a hit, and it is the **most common LLM false-positive class**: co-occurrence reads as recurrence when it is not.

## The primary signal — framing similarity, not count

From research on repetitive thinking (Nolen-Hoeksema brooding/pondering 2008; Watkins level-of-construal 2008): the signal that thought **isn't moving** is **abstract framing without progress**:

- **Brooding-shape (signal of stalled):** "why haven't I…", "still can't…", "same thing again…", abstract nouns without concrete grounding ("delegation", "balance", "meaning"), "why"-questions without "how"-follow-ups, no specific people / dates / actions appearing across mentions.
- **Pondering-shape (signal of healthy incubation):** each return adds a new sub-question, a new constraint, or new evidence; the formulation evolves; concrete "if X then Y" structures appear.

**Pondering is NOT stalled.** It is healthy incubation. Matuschak (evergreen notes) describes this directly: reaching insight requires holding parallel partially-formed ideas in motion. Do not conflate incubation with being stuck.

## GTD next-action test

From David Allen — open-loop test: for the thread, mentally formulate "the next physical action" as the owner would. If you cannot (because the owner never named one across the records) — the thread is **open**. If any mention contains a committed next action or an explicit decision — it is NOT open; it is in-flight or resolved.

**Sources to query before declaring «no committed next action»:**

1. `_system/state/OPEN_THREADS.md` — explicit thread + `Related tasks:` field
2. `_system/TASKS.md` — full pass on the topic by keyword + person + project; not just by frontmatter; tasks may live under unrelated section headers
3. `_records/` mentions themselves — a record-level `[ ]` checkbox or «договорились X сделать Y до Z» counts as committed
4. Hub `## Changelog` and `## Связанные knowledge` — a closure entry («решили X», «приняли Y») disqualifies the thread
5. `_system/CALENDAR.md` — a scheduled meeting on the topic counts as «in-flight», not stalled

If after all five the thread still has no committed next action — it is open.

## What to read

Decide for yourself. The frame's contract gives you full base access — use it. Useful starting points:

- `_records/observations/` and `_records/meetings/` over the recent few months. If a thread's roots seem older, widen the window — there is no fixed limit; let the pattern dictate the depth.
- `_system/state/OPEN_THREADS.md` — already-fixed threads. Don't duplicate them (they are already visible to the owner).
- `_system/TASKS.md` — if a topic lives as a task with a clear next action, it is not stalled, it is an open task.
- `_system/views/HUB_INDEX.md` and `5_meta/mocs/` — if a topic has a hub, it has reached synthesis.
- `3_resources/people/PEOPLE.md` — when a candidate is person+topic-shaped, resolve the canonical person-id before treating different mentions as the same thread.
- When useful — `_sources/inbox/` for fresh transcripts not yet shaped into records (if a thread seems to continue there).

## Window calibration by base maturity

A fresh Minder Memory base surfaces stalled threads at relatively high frequency in short windows — most recurring topics still live in raw records. A mature base (HUB_INDEX with >10 active hubs absorbing common recurring topics + a populated `OPEN_THREADS.md`) moves the obvious patterns into curated layers, so the threads that escape curation tend to recur slowly: a few mentions per quarter, not weekly.

In a mature base, default to a 3-6 month sweep over `_records/` — the monthly window will systematically miss the very threads the lens exists to find (the slow-burn ones that did not reach a hub). Fresh bases (few hubs, thin OPEN_THREADS) work fine with a few weeks. Criterion #3 below («not already fixed») does the de-duplication regardless of window size, so widening only changes what is detectable, not what is double-counted.

**Mature-by-curation, short-by-records edge case** — the base has >10 hubs and a populated `OPEN_THREADS.md`, but `_records/` history is shorter than the calibration window (e.g. recent migration, fresh capture pipeline, or first-ever scan). In that case: read the available `_records/` AND descend into hub `## Хронологическая карта` / `## Changelog` and into knowledge notes in `1_projects/`, `2_areas/`, `3_resources/` to reconstruct the multi-month / multi-year span of the thread. Note the asymmetry explicitly in the output: «N weeks in records + M months in hubs» rather than collapsing both into one span. The thread's true span is what matters for confidence; records are just one of several surfaces that capture it.

## First retroactive run mode

Distinct from steady-state weekly cadence. On the first run of a newly-created lens — or on an explicit deep re-baseline by the owner — the lens reads the **full available history** rather than the calibrated window. Output may surface more candidates than a steady-state run. Confidence calibration stays the same. Mark such runs in the output's notes («first retroactive run / deep baseline») so the owner can read it accordingly. Steady-state weekly runs revert to window-calibrated reading.

## What counts as a hit

A candidate where ALL hold:

1. **Multiple mentions** in `_records/` on different days, with meaningful spacing (consecutive-day mentions are usually one continued thinking session, not recurrence).
2. **Each mention leaves the topic open** by the GTD test above — no committed next action, no explicit decision.
3. **Not already fixed** in `OPEN_THREADS.md`, `TASKS.md` (as an active task), `5_meta/mocs/`, or closed inside a knowledge note in `1_projects/`, `2_areas/`, `3_resources/`.

   **Hub coverage is not binary.** A hub may capture the surrounding *arc* without the specific *sub-thread* having closure. Three gradations:
   - **(i) Hub closes the sub-thread** — there is an explicit decision / closure entry in `## Changelog` or in a linked decision note covering this exact question. → NOT a hit.
   - **(ii) Hub mentions the arc, sub-thread has no closure** — the changelog explicitly notes that this specific question stayed unresolved (e.g. «X не обсуждалось», «решение отложено»). → IS a hit, label «within hub, not closed».
   - **(iii) Hub silent on the sub-thread** — sub-thread present in records but no hub mention at all. → IS a hit.

   In case (ii) and (iii), surface explicitly so the owner sees that hub-presence ≠ resolution.

4. **Brooding-shape** by the test above — abstract framing, no new sub-questions or constraints between mentions. If framing evolves between mentions, it is pondering, probably NOT a hit.

## Ambient vs recurrence — operational tie-breaker

The most common false positive is treating co-occurrence (person X / project Y appearing across records) as recurrence of a thread. Apply this test:

> **The substitution test** — if you remove the candidate thread's framing and rewrite the record around the rest of its content, does the mention disappear? If YES, the mention is *about the thread*. If NO (the mention would survive in any record on the topic), it is ambient context.

Example: «Oleg молча реагировал на Project Alpha» — substitution removes Oleg, the record about Project Alpha stands. Oleg here is ambient. «Опять весь день ушёл не туда, и так уже который месяц» — substitution removes the brood, the record loses its core. The brood is the thread.

If you cannot decide — the candidate is weak. Surface as low-confidence «watching, ambient probability ≥ thread probability» rather than as a hit.

## Confidence calibration

State your confidence honestly:

- **high** = ≥3 mentions with the same abstract framing, no committed next action in any of them, span on the order of a month or more, option-set / question-shape does not narrow between mentions, no parallel processing of the same topic in adjacent channels (therapy, framing-reframes, structural moves).
- **medium** = 2-3 mentions with the same framing; OR more mentions with slowly-evolving framing but no resolution; OR the direct channel is brooding but adjacent indirect channels show evolution (mixed signal).
- **low** = two mentions with framing that differs or evolves; OR ambient/recurrence ambiguity per the substitution test; OR strong evidence of parallel processing in adjacent channels — surface as "thread in motion, watching, not yet stalled" rather than as stalled.

**Direct vs indirect-channel signal** — when a topic is brooding in one channel (e.g. direct salary conversation) but actively processed in 2+ adjacent channels (therapy, framing-reframes, structural workarounds), the more accurate pattern is «direct channel blocked, indirect channels active». State this explicitly rather than calling the whole topic stalled. Confidence drops to medium / low for the direct-channel-only piece.

Low confidence is a normal output. Better to surface low with a clear note than not surface at all, or surface with false high confidence.

## What does NOT count as a hit

1. **Cyclical / scheduled topics** — quarterly review, monthly 1:1 prep, weekly retro, sprint planning. Recurrence by design, not stuckness.
2. **Reference mentions** — person X or project Y appears as background across unrelated threads. This is ambient context, not one thread. The most common false-positive class — do not confuse co-occurrence with recurrence.
3. **Pondering with evolution** — same topic, but each mention adds a sub-question, a constraint, a new person involved. Healthy incubation (Matuschak), not stuckness. If you surface, label as "pondering, watching".
4. **Emotional texture without a question** — "tired of X", "frustrated with Y" without a question or topic behind it. A signal of state, not a thread.
5. **External-blocker waits** — the owner is waiting on someone else's reply, an event, a deadline. Stalled in the environment, not in the owner. NOT a hit.
6. **Identity-level long arcs** — "who do I want to be", "where am I going". These live at `0_constitution/` / `_system/SOUL.md`, not at record level. Surfacing them as stalled is a category error.
7. **Resolved-elsewhere** — closed inside a knowledge note or hub you didn't cross-check. Verify before surfacing.

## Self-history

`fresh-eyes` — past outputs are not read. If a thread was flagged before and is still stalled, you will flag it again — repetition in outputs is itself a signal to the owner. If it resolved, you won't find it on this pass because the criteria won't hold.

## Tone

Descriptive, never evaluative. Naming repetitive thought as "pathological" or "avoided" **increases** brooding (clinical literature, Nolen-Hoeksema 2008). Use:

- ✅ "Topic X appeared in records on {date1}, {date2}, {date3}. Each mention leaves it without a committed next action."
- ❌ "You are avoiding the decision on X."
- ✅ "Thread in motion — each mention adds a new angle. Surfacing as watching, not stalled."
- ❌ "Stuck thread." (used as a label)

Vocabulary: "thread in motion" (Matuschak idiom: ideas in motion) for pondering; "open thread" for stalled. No "avoiding", "stuck", "failing to". No second-person evaluative verbs.

**Russian-language output vocabulary** (when the lens runs in Russian — language follows record-base language per skill convention):
- ✅ «открытая нить», «нить в движении», «прямой канал заблокирован», «параллельные каналы обработки»
- ❌ «застрявшая нить», «залипшая тема», «избегаешь», «не справляешься», «откладываешь»

Same descriptive-not-evaluative discipline; literal translations of English vocabulary above.

## What to give back

For each hit, in free form:

- **What the thread is** — 1-2 sentences. Name it as one phrase.
- **Specific record references** — path + date + a short quote or paraphrase showing the framing.
- **Brooding-shape evidence** — what specifically shows the framing isn't moving (repeated phrasing, abstract language, absence of sub-questions).
- **What is visible in the system as a next move** for the owner — NOT advice, but a statement of what is available. Offer 2-3 concrete options when possible, framed as system-level moves rather than instructions:
  - «could be fixed as a separate row in OPEN_THREADS.md» (with a suggested thread-id)
  - «could become a task with a next action in TASKS.md»
  - «could be reframed as N-cycle test — if next direct attempt fails, accept channel as unavailable»
  - «could be consciously released — accepting the channel as background not actionable»
  - «could be pinned to hub `## Changelog` as `direct-channel-stall, indirect-channels-active` so future runs see the framing»
- **Alternative reading** — why this might NOT be stalled (it's a reference, or pondering, or external-blocker). If unsure, note that the thread may be weak and worth waiting another pass.
- **Confidence** — high / medium / low.

If 0 hits — say so plainly: "Over the window I examined, no threads met the criteria. Topics I considered and dismissed: …" That is also a signal.

## Action Hints emission (optional trailer)

When at least one hit shows a genuinely brooding-shape thread (repeated
abstract framing across multiple records, no movement on sub-questions,
not already tracked in `OPEN_THREADS.md`), you MAY append an `## Action
Hints` trailer with an `open_thread_add` proposal. See `_frame.md →
Action Hints (optional trailer)` for the schema. The resolver weighs
your hint against owner context and either appends a row to
`OPEN_THREADS.md` (with cited records + provenance) or queues for owner
review.

Favour `open_thread_add` when:

- The brooding shape is unambiguous — same framing recurs across ≥2
  records and at least one record sits 14+ days apart from the most
  recent surfacing (the gap is what makes it «stalled»).
- A short, specific `thread_title` can be stated (≤80 chars). If the
  title would be «owner is thinking about X», the thread isn't ready
  for a row.
- The thread is absent from `OPEN_THREADS.md` (verify before emitting —
  resolver re-checks, but emitting noise burns owner attention).

Skip emission when:

- Confidence is `low` (surface in body, do not propose).
- The thread looks like reference / pondering / external-blocker (the
  «alternative reading» you wrote in the body is plausible).
- A substantively-similar thread is already in `OPEN_THREADS.md`.
- The hit shape suggests fading echo of a prior surfacing rather than
  fresh brooding (you are seeing your own past output recur).

`priority` field in `params` is optional; default `medium`. Use `high`
sparingly — only when the brooding has visibly hardened (same framing
unchanged across 3+ records over 4+ weeks). `brief_reasoning`: one
paragraph naming the brooding shape + the gap evidence + what would
falsify it as a real stall.
