# Describe me — profile for /minder:mem:bootstrap

> **What this is.** A guided profile of you. `/minder:mem:bootstrap` reads
> this file as the **primary source** for `_system/SOUL.md` (Identity,
> Values, Working Style, Active Goals) on a fresh skeleton. Filling
> this in well dramatically increases the quality of every downstream
> skill — `/minder:mem:process` calibrates tone, `/minder:mem:lint` calibrates
> standards, `/minder:mem:capture-candidate` calibrates principle detection
> against your real value system.
>
> **How to use.** Copy this file to `PROFILE.md` in the same folder
> and fill the copy — keep this template pristine (files named
> `*.template.md` are engine seed material, never processed).
>
> **You don't have to write it from scratch.** A common workflow:
>
> 1. Open Claude (or ChatGPT) in a separate session.
> 2. Paste a few of your typical transcripts / journal entries / past
>    notes / a CV / a personal manifesto.
> 3. Ask: «Fill in the template below as if you were me — quote me
>    where you can, hypothesize where you can't, and mark hypotheses
>    explicitly.»
> 4. Paste the result into your `PROFILE.md`, then read through and
>    edit anything wrong.
>
> **You don't have to fill every section.** Empty sections become
> CLARIFICATIONS during bootstrap — you'll be asked specific
> follow-ups. Better a small honest profile than a large fabricated
> one.
>
> **Privacy.** This file lives in your private repo. It only ever
> reaches Claude through your local skills. It is NOT shared with the
> upstream `minder-memory` skeleton.
>
> **After bootstrap reads your profile, the consumed files move to
> `_sources/processed/describe-me/`** — kept as reference for re-runs.
> You can drop more self-description files into this folder over time
> (career updates, value shifts, new context); `/minder:mem:process` picks
> them up as regular content, and a re-run of `/minder:mem:bootstrap` re-reads
> both sides.

---

## Identity

- **Name:** {Full name as you want agents to address you}
- **Role:** {Current professional role / occupation, one line}
- **Side projects:** {Optional — anything you spend significant energy on outside the day job}
- **Location:** {City, Country}
- **Timezone:** {IANA, e.g. Europe/Berlin (UTC+1)}
- **Languages:** {Primary for thinking/notes; secondary; how you mix them}
- **Domain:** {One sentence — the industry / field you work in}
- **Experience:** {Years + a one-line summary of your trajectory}

## Values — what you actually stand for

> Free-form bullets. What trade-offs do you make consciously? What do
> you refuse to compromise on, and why? What do other people think is
> important that you genuinely don't? Honest > flattering.
>
> Each bullet: short statement + the reason behind it (the «why»
> matters for principle detection later).

- {Value 1 — statement + why}
- {Value 2 — ...}
- {Value 3 — ...}

## Current Focus

> What dominates your attention right now? Split work vs personal —
> the system mirrors this split. 2-4 bullets per side is plenty.

### Work

- **Primary:** {The thing eating most of your week}
- **Secondary:** {The next-largest investment}
- **Tertiary (optional):** {Background commitments}

### Personal

- **Primary:** {Most active personal investment}
- **Secondary:** {...}

## Active Goals (3-12 month horizon)

> Outcome-level. Concrete tasks live in TASKS.md. Goals are the
> «why» behind tasks. Split into work and personal — both are first-
> class. Skip a side if it doesn't apply (no work context, or no
> active personal goals — both are valid states).

### Work

1. {Work goal 1 — outcome statement, optionally with a rough deadline}
2. {Work goal 2}

### Personal

1. {Personal goal 1}
2. {Personal goal 2}

## Working Style

> How you prefer to operate. Used by skills to align outputs with you
> (response shape, level of formality, when to push back, when to ask
> for clarification).

- **Communication style:** {Direct / structured / Socratic / narrative / ...}
- **Cadence:** {Async-first / sync-heavy / mixed; deep-work hours}
- **Capture preference:** {Voice-first / written / mixed; tools you use}
- **Decision-making:** {Data-driven / intuition-led / consensus-seeking — be specific}
- **Delegation:** {How you hand work off and verify it}
- **Red lines:** {What you actively do not tolerate — overcomplexity, buzzwords, missed deadlines, ...}
- **Energy:** {What charges you up; what drains you; known execution gaps you're aware of}

## Context for Agents

> Operational hints for how Claude / skills should behave when
> assisting you. The more concrete, the better.

### Default response shape

- {How long, how structured, what to lead with}
- {Markdown vs prose; tables vs bullets; code-block conventions}
- {End-of-turn summary: yes / no}

### How you like information presented & consumed

> The assistant already defaults to conclusion-first, no-fluff, no-sycophancy
> (the shipped communication baseline). This is where you tune it to you — skip
> any line and the default still applies. Concrete answers here seed your
> `ai-interaction` principles (add the firm ones to «Principles you live by»
> below) and your long-form playbook.

- **Order:** {Conclusion first, then evidence — or context / the story before the point?}
- **Praise that lands:** {Facts ("14 people came to you unprompted") or labels ("great job")? Many people reject evaluative labels.}
- **Criticism that lands:** {Only if concrete + actionable + provable? Blunt or cushioned? What makes you defensive vs sharper?}
- **Insight vs recap:** {Weight interpretation / "what it means" over the play-by-play, or do you want faithful detail?}
- **Long-form** (reports / audiobooks / debriefs you read or listen to top-to-bottom): {density, pacing, chapter structure, narrative devices, hard bans? → put the recipe in `_system/long-form-playbook.md`, loaded on demand only for such pieces.}

### Language

- {Which language you write/think in vs which language code/metadata uses}

### What to keep in mind

- {Any non-obvious bridge domains or stack details — e.g. «my work
  bridges fintech and ML, both contexts are usually relevant»}
- {Tools / stack you default to}
- {Things to check before suggesting new approaches — existing
  knowledge in Minder Memory, current codebase patterns, etc.}

### What to avoid

- {Habits / patterns that don't serve you — silent trade-offs,
  premature abstraction, motivational filler, ...}

### When to ask vs decide

- {When should the agent push back, when should it just proceed,
  when should it surface a CLARIFICATION}

---

## People who matter (optional, helpful)

> If you list 5-15 people you talk about often, `/minder:mem:bootstrap`
> seeds them as Tier-2/3 candidates in PEOPLE.md (subject to your
> review). Skip this section if it feels weird — the raw transcript
> scan finds them anyway, this just removes ambiguity for the
> common cases.
>
> The `Org` field is how the system distinguishes work-context
> people from personal-context people: empty `Org` = personal
> relation (friend / family / mentor unaffiliated / ...); non-empty
> `Org` = work-context relation. Tag honestly — overlap is fine
> (your spouse who's also a co-founder belongs in both worlds).

| Name (any form) | Canonical id (firstname-lastname) | Role | Org | Relationship |
|---|---|---|---|---|
| {how you call them} | {ivan-petrov} | {their role} | {their org — leave empty for personal-context relations} | {colleague / friend / mentor / family / partner / ...} |

## Projects you care about (optional, helpful)

> Same idea — pre-seeds PROJECTS.md so the bootstrap raw scan can
> match transcripts to projects you've already declared, instead
> of guessing.
>
> `Scope` ∈ {`work` (employer / clients), `personal` (life / health
> / learning), `side` (side business, freelance, public project),
> `mixed` (truly cross-context — rare, prefer one of the others
> when in doubt)}.

| Project id (kebab-case) | Name | One-line description | Scope | Status |
|---|---|---|---|---|
| {api-redesign} | {Public API redesign} | {short description} | {work / personal / side / mixed} | {active / paused / completed} |

## Principles you live by (optional, very helpful)

> Pre-seeds the constitution. If you have explicit personal rules
> you've already articulated (5-15 is normal), drop them here. They
> land in `_system/state/principle-candidates.jsonl` for you to
> review-and-promote via `/minder:mem:lint` rather than auto-loading.
>
> Format each as: `[type | domain] short rule — why you hold it`.
>
> `type` ∈ {`axiom` (always-on identity claim), `principle` (default
> rule with exceptions), `rule` (concrete operational rule)}. If
> unsure, write `unknown` — review will classify it.
>
> `domain` ∈ {`identity`, `ethics`, `work`, `tech`, `relationships`,
> `health`, `money`, `time`, `learning`, `ai-interaction`, `meta`}.
> Note: «personal» is NOT a valid domain — it's too vague. Pick a
> richer tag (a personal principle about boundaries → `relationships`;
> about not overspending → `money`; about reading habits → `learning`).
> A principle that genuinely spans both work and personal is usually
> an axiom in `identity` or `ethics`.

- {axiom | identity: Measure twice, cut once — rework costs more than care}
- {principle | ethics: Surface trade-offs before deciding — silent compromise = future debt}
- {rule | work: Don't ship without a rollback plan if 1+ user is affected}
- {principle | ai-interaction: Lead with the conclusion, not the recap — I read for meaning, not the play-by-play}
