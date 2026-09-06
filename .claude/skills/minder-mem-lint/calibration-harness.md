# /minder:mem:lint Calibration Harness

> Deterministic 10-case test harness для confidence tier routing calibration.
> Run before first scheduled nightly, after every SKILL prompt update, and every
> 10 nightly runs thereafter для drift detection.
> 
> **Not executable by lint** — operator invokes during SKILL revisions.

---

## Purpose

Detect drift в LLM verdict prompt calibration. Each case has known-correct tier routing. Operator runs SKILL verdict prompt on each case input → asserts match expected tier. 2+ mismatches = drift → raise CLARIFICATION `calibration-drift-detected` + review prompt.

---

## Cases

### Case 1 — Schema completion, strong + high → silent

**Candidate:** Knowledge note `20260325-insight-team-dynamics.md` missing `modified:` frontmatter field. `created: 2026-03-25`.

**Context:** File exists, frontmatter valid YAML, all other schema fields present. Operation = copy `created` к `modified`.

**Expected rule-floor:** strong (deterministic schema fix, no semantic component)
**Expected LLM verdict:** high (3-4 positive, 0 negative rubric answers)
**Expected tier:** `silent`
**Expected action:** apply + log_lint.md entry + no CLARIFICATION

---

### Case 2 — Frontmatter type normalization, strong + high → silent

**Candidate:** Note has `tags: "person/ivan-petrov,project/example-project"` (string) instead of YAML list.

**Context:** Standard schema normalization. Parse string by delimiter, convert к list.

**Expected rule-floor:** strong
**Expected LLM verdict:** high
**Expected tier:** `silent`

---

### Case 3 — Dedup merge, strong + high → silent (delete secondary + backlink redirect)

**Candidate:** 2 notes с 92% structural similarity, same source transcript, identical frontmatter tags, primary has Evidence Trail + hub linkage, secondary has neither. No unique content в secondary.

**Context:** Dedup pair passes all similarity thresholds. LLM confirms extraction complete.

**Expected rule-floor:** strong (high similarity + clear primary selection)
**Expected LLM verdict:** high
**Expected tier:** `silent`
**Expected action:** merge + delete secondary + backlink redirect + log_lint.md per-fix

---

### Case 4 — Dedup medium similarity, weak + confident → surfaced

**Candidate:** 2 notes 78% similarity, overlapping people but partially different topics (career vs technical filing of same meeting).

**Context:** Could be intentional dual-write OR accidental duplicate. LLM semantic reasoning only — no structural strong signal.

**Expected rule-floor:** weak
**Expected LLM verdict:** confident (not high — structural similarity below threshold)
**Expected tier:** `surfaced`
**Expected action:** CLARIFICATION `dedup-surfaced`, no apply

---

### Case 5 — Thread staleness, strong (date math) → surfaced (HARD RULE)

**Candidate:** Thread `thread-20260310-strategy-review` waiting-for-response since 2026-03-10 (41 days ago, past 14-day warn threshold). No activity в last 14 daily summaries.

**Context:** Staleness computed deterministically. But HARD RULE — closure never auto-applied.

**Expected rule-floor:** strong (date math)
**Expected LLM verdict:** high (evidence clear)
**Expected tier:** `surfaced` (HARD RULE overrides — closure is manual)
**Expected action:** CLARIFICATION `thread-stale-warn`, no apply

---

### Case 6 — Bare-name unambiguous resolution, strong + high → reviewed

**Candidate:** Frontmatter `people: [ivan]` в note. PEOPLE.md has exactly one `ivan-*` id (`ivan-petrov`). File context = API v2 technical session (matches Role: Tech Lead API v2).

**Context:** Single candidate in registry + context corroborates. Three-surface scan finds: 1 frontmatter ref + 1 tag `person/ivan` + 1 inline `[[ivan]]` wikilink.

**Expected rule-floor:** strong (registry unambiguous)
**Expected LLM verdict:** high (context matches)
**Expected tier:** `reviewed` (profile-generation equivalent — creates visible substitution across 3 surfaces, always validate first)
**Expected action:** apply all 3 surfaces + CLARIFICATION `orphan-bare-name-resolved` с sub-action counts

---

### Case 7 — Bare-name ambiguous, weak + probable → surfaced

**Candidate:** Frontmatter `people: [sasha]`. PEOPLE.md has 7 `sasha-*` ids. File context = team meeting about salary (mentions role «dev»).

**Context:** Multiple candidates, context partially informative (narrows к sasha-morozov likely, but sasha-panin (DBA) could also be «dev»-classified).

**Expected rule-floor:** weak (multiple candidates)
**Expected LLM verdict:** probable (leans but uncertain)
**Expected tier:** `surfaced`
**Expected action:** CLARIFICATION `orphan-bare-name-surfaced` с per-candidate analysis

---

### Case 8 — Evidence Trail Mode A backfill, strong + high → silent (bulk-uniform)

**Candidate:** 50 legacy knowledge notes missing `## Evidence Trail` section. All have valid `source:` frontmatter pointing к existing transcript.

**Context:** Template-only backfill — insert 1-line entry `{created date}: original insight captured — source: \`{source basename}\` (backfilled retroactively)`. Deterministic across all 50 candidates.

**Expected rule-floor:** strong (deterministic schema completion)
**Expected LLM verdict:** high (no judgment variance across candidates)
**Expected tier:** `silent` (bulk-uniform — one deterministic template, no per-candidate judgment)
**Expected action:** apply all 50 + aggregated log_lint.md summary

---

### Case 9 — Evidence Trail Mode B semantic reconstruction, weak + confident → reviewed

**Candidate:** Knowledge note без ET, source transcript accessible. LLM proposes narrative trail с 3 entries («initial insight», «confirmation с follow-up meeting», «superseded by later decision»).

**Context:** LLM synthesizes per-note narrative — different reasoning per candidate. Source accessible but judgment variance real.

**Expected rule-floor:** weak (semantic synthesis carries burden)
**Expected LLM verdict:** confident (evidence accessible but per-candidate judgment)
**Expected tier:** `reviewed`
**Expected action:** apply + CLARIFICATION `evidence-trail-mode-b-reviewed` с LLM reasoning

---

### Case 10 — SOUL focus drift, semantic-only → surfaced (HARD RULE — SOUL never auto-edit)

**Candidate:** Last 14 days of daily summaries show 60% activity on «AI Tools & Adoption» theme. SOUL.md Focus → Work → Tertiary lists AI Tools.

**Context:** Strong semantic signal что Tertiary по Focus actually dominates activity. Candidate observation: reclassify priority.

**Expected rule-floor:** strong (semantic activity count deterministic)
**Expected LLM verdict:** high
**Expected tier:** `surfaced` (HARD RULE — SOUL never auto-edit regardless of signal strength)
**Expected action:** CLARIFICATION `soul-focus-drift`, no apply

---

## Execution protocol

1. Operator reads each Case
2. Feeds «Candidate» + «Context» into the LLM verdict prompt template in `SKILL.md` → «Confidence tier routing»
3. Collects verdict + tier routing
4. Asserts match с «Expected tier» + «Expected action»
5. Counts mismatches

### Pass criteria

- 0 mismatches → calibration clean, proceed к run
- 1 mismatch → review that case's prompt handling, document in log_lint.md Errors/Warnings
- ≥ 2 mismatches → **calibration drift detected** → halt scheduled runs, raise CLARIFICATION `calibration-drift-detected`, human review verdict prompt wording

### Tier distribution sanity (meta-check)

Expected tier distribution across 10 cases:
- silent: 3 (cases 1, 2, 3, 8 — actually 4, but case 8 is bulk-uniform variant)
- noted: 0 explicit
- reviewed: 2 (cases 6, 9)
- surfaced: 4 (cases 4, 5, 7, 10)
- hidden: 0

Sanity bounds: ≥ 2 silent (mechanical fixes exist), ≥ 2 surfaced (safety floor active), < 7 silent (not all high-confidence, pure LLM apply).

---

## Harness maintenance

**Update protocol:** append-only case additions. Case reworded ≠ removed —
add new case with «supersedes case X» note, keep original для baseline comparison.

**Governance:**
- New canonical Resolution-action verbs added → add case demonstrating expected tier
- New reason codes added → add case
- Calibration drift detected repeatedly → review case wording, consider retiring stale cases
