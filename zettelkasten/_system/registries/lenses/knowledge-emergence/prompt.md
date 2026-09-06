---
id: knowledge-emergence
name: Knowledge Emergence
type: mechanical
input_type: records
cadence: weekly
cadence_anchor: saturday
self_history: longitudinal
status: active
---

# Knowledge Emergence

## Intent

Scan the **knowledge layer** (`1_projects/`, `2_areas/`, `3_resources/`)
for themes, framings, or relational patterns that recur across **3+
knowledge notes** and have **no hub yet** (or have a hub that is
mismatched — too general / too narrow / should split). Surface
emerging clusters before the owner notices them himself, so promotion
knowledge → hub does not depend on passive owner-noticing.

This is the only lens whose primary input is the knowledge layer
rather than records. Records are «what the owner said»; knowledge is
«what the owner already distilled». The signal lives in the second:
distilled material is post-filter, so recurrence here means a real
pattern in his thinking, not just talking-volume.

The lens defends Layer 3 (hubs) of the Minder Memory doctrine
(`5_meta/CONCEPT.md` §«Три слоя»): hubs are the synthesis layer, the
highest-leverage tier. Their growth currently rests entirely on owner-
noticing. This lens makes promotion candidates visible.

## Distinction from sibling lenses

The lens explicitly does NOT do what these do:

- **`cross-domain-bridge`** discovers latent **edges** between
  far-apart clusters. This lens discovers **clusters** themselves —
  one theme repeating in 3+ notes. Edge vs cluster topology.
- **`stalled-thread`** scans records for unresolved open-loops.
  Different layer (records, not knowledge) and different shape (single
  unresolved thread, not recurring crystallised theme).
- **`decision-review`** checks past decisions vs subsequent records.
  Backward-looking validation, not forward-looking promotion.
- Lint **D.4 `hub-stale-vs-material`** flags when an *existing* hub
  drifts behind its underlying material. This lens flags when a *new*
  hub is missing entirely (or the existing one is the wrong shape).

If in doubt: «is the candidate a missing/wrong hub?» → this lens. «Is
it a stale existing hub?» → D.4. «Is it an unconnected pair across
domains?» → `cross-domain-bridge`.

## What to read

Decide for yourself — full base read access. Suggested anchors:

- **Primary:** `1_projects/`, `2_areas/`, `3_resources/` — all
  knowledge notes (`layer: knowledge`). Frontmatter (`title`,
  `description`, `domains`, `tags`, `types`, `extracted_from`,
  `created`, `modified`) + body sections (`## Ключевая мысль`,
  `## Применение / Следствие`, `## Связи`).
- `_system/views/INDEX.md` — surface catalog of knowledge + archive +
  constitution + hubs. **Use only if populated** (check `note_count:`
  in frontmatter > 0). On a fresh base or stale catalog (bootstrap
  state, or A.6 lint flagged `index-stale`) walk PARA folders directly
  — INDEX is a navigation shortcut, not the source of truth. INDEX
  contains four sources, but for **emergence** purposes scope to:
  - `## By PARA` → `Projects` / `Areas` / `Resources` (the knowledge
    layer — primary input)
  - `## By Domain` and `## Cross-domain` (faceted views over the
    same knowledge entries — useful for spotting cross-PARA themes)
  Skip `## Archive` (out-of-scope for emerging-theme detection — these
  notes are explicitly not active material), `## Constitution` (values
  layer — different shape: principles, not knowledge fragments), and
  `## Hubs` (already-promoted synthesis — use HUB_INDEX.md for
  hub-absence verification instead).
- **Cross-check:** `5_meta/mocs/` + `_system/views/HUB_INDEX.md` —
  to verify «no hub yet» and to detect mismatched-shape hubs.
- **Anti-noise:** `_records/` is NOT primary input. Records may be
  consulted only to disambiguate whether a knowledge note is genuinely
  load-bearing for the candidate or just touches the topic in passing.
- `1_projects/PROJECTS.md` and `3_resources/people/PEOPLE.md` — to
  separate project-id and person-id co-occurrence (anti-pattern, see
  below) from genuine theme recurrence.

## Window

- **Primary window:** knowledge notes with `modified` or `created` in
  the last **3-6 months**. Knowledge crystallises slowly — short
  windows miss the formation arc; long windows catch already-promoted
  themes.
- **Widening allowed:** if a candidate's earliest endpoint sits in a
  knowledge note older than 6 months and newer notes extend the same
  framing — widen freely. Emerging themes by definition have a long
  tail.

## What counts as a hit — 4 signals (need ≥ 2)

A real emerging theme carries structural recurrence, not just
keyword overlap. Follow Luhmann's Folgezettel discipline (a permanent
note earns a thematic anchor when ≥3 sister-notes form a coherent
sequence) + Matuschak's evergreen promotion ladder (a concept
deserves its own note when it's been touched independently 3+ times)
+ Weick's retrospective sensemaking (patterns visible only in
hindsight, when scattered notes are read as one corpus).

1. **Recurrent framing.** The same concept / pattern / relational
   schema appears in **3+ knowledge notes** within the window. Match
   on **semantic role**, not just lexical match — the same operating
   logic in different vocabulary still counts. Example: «делегирование
   как акт доверия» в одной ноте + «отпустить контроль над процессом»
   в другой + «overdelivery как защитная реакция на потерю контроля»
   в третьей — три ноты, одна relational структура (`agent → releases
   control → outcome`).

2. **Hub absence or hub mismatch.** Verify against `5_meta/mocs/` and
   `HUB_INDEX.md`:
   - **Absence:** no hub names this concept in title or in «Текущее
     понимание» body.
   - **Mismatch — too general:** existing hub covers a broader topic;
     the candidate is a coherent sub-theme that deserves its own hub
     (split signal).
   - **Mismatch — too narrow:** existing hub covers a sibling theme,
     the candidate would extend its scope sensibly (extend signal —
     not a new hub, but a hub-update).
   - Surface mismatch type explicitly in the output.

3. **Cross-PARA appearance.** Candidate notes sit across **≥ 2 PARA
   folders** (e.g. some in `1_projects/` and some in `2_areas/`, or
   `2_areas/work/` + `2_areas/personal/`, or `2_areas/` + `3_resources/`).
   This signals a transversal theme, not a project-local concern. A
   single-PARA candidate is more likely a project-specific concept
   that doesn't deserve a hub.

4. **Independent derivation.** The candidate notes are NOT all
   `extracted_from:` the same record. At least 2 different sources
   (records or independent reflections without `extracted_from:`)
   produced the candidate notes. One transcript producing 3 notes on
   one topic = same source, not independent recurrence.

## What does NOT count as a hit (anti-patterns)

1. **Project-id co-occurrence.** 3 notes share `projects: [acme-payments]`
   — the project itself is the binding, not an emerging theme. Reject.
   Project hubs (e.g. `hub-acme-payments`) already cover this — the
   binding has a name and a home.
2. **Person-name co-occurrence.** 3 notes mention the same person —
   that's a person-tier signal (handled in PEOPLE.md), not an
   emerging theme. Reject unless the candidate is a *role pattern*
   the person plays (e.g. «X как noise-amplifier in any deliberation»
   — that's a structural claim about a role, not about X).
3. **Generic abstraction.** «качество», «процесс», «решение»,
   «approach», «system», «context», «balance» — high-frequency
   abstract nouns. Documented LLM false-positive class. These connect
   everything to everything. Reject unless paired with a sharp
   relational schema (≥1 other signal at high evidence).
4. **Domain-tag overlap.** 3 notes share `domains: [work]` —
   `domains:` is a coarse axis, not a theme. Reject unless an
   underlying relational schema is also recurrent.
5. **Single-PARA, single-extraction.** Candidate sits in one PARA
   folder AND all source notes share one `extracted_from:` chain.
   Project-local concept, not emerging theme. Reject.
6. **Bridge already named.** A hub already covers the candidate. Don't
   re-flag — D.4 covers stale-hub maintenance instead.
7. **Sloppy synthesis ("everything is converging").** Three or more
   candidates per run, each opening with «interestingly, several notes
   touch on...» — almost always confabulation. If you find 3+
   candidates in one window, treat that itself as a noise signal and
   tighten criteria before surfacing.
8. **Owner already promoted.** Candidate has a wikilink in body of a
   recent (last 30 days) hub or knowledge note that explicitly names
   the theme — the owner is already aware. Verify by grepping
   `[[candidate-keyword]]` patterns and «hub for ...» fragments.

## Confidence calibration

- **High** = 3+ notes with recurrent framing **AND** cross-PARA
  appearance **AND** independent derivation **AND** clear hub-absence-
  or-mismatch verdict. Nameable promotion claim («this should be
  `hub-{slug}` because notes A, B, C all express the relational shape
  X»).
- **Medium** = 3+ notes with recurrent framing AND ≥ 1 other signal,
  with a tentative promotion claim. May be a sub-theme of an existing
  hub rather than a standalone hub — say so.
- **Low** = co-occurrence + plausible-sounding theme but the
  relational schema is weak or only one signal beyond recurrence.
  Surface as «watching, not yet a promotion candidate».

### Mandatory downgrades (apply BEFORE settling on a tier)

These rules force one tier down regardless of how strongly the
positive signals fire. Calibrating them tightens the lens against
sloppy synthesis and project-id false positives.

1. **Project-id concentration (≥ 50% rule).** If the majority (≥ 50%)
   of cited notes share a single `projects:` id, downgrade by one
   tier (high → medium, medium → low). The relational shape may be
   project-specific in disguise, not a generalisable theme. State the
   downgrade explicitly: «high signals on the surface, downgraded to
   medium because 4/6 notes carry `projects: [acme-payments]` —
   the catalyst may be project-bound rather than the schema being
   generalisable». Anti-pattern #1 still REJECTS outright when ALL
   notes share one project; this rule catches the borderline case.

2. **Single-extraction concentration.** If 3+ cited notes share a
   single `extracted_from:` source (one transcript spawned several
   knowledge notes), downgrade one tier. Same source ≠ independent
   derivation, even if the resulting notes look distinct.

3. **One-month concentration.** If all cited notes were modified
   within the same calendar month, downgrade one tier. Emerging
   themes form across multi-month cadence; one-month spikes are
   often topical bursts that fade.

Downgrades stack: a hit that triggers two of the above lands two
tiers below its raw signal count.

Low confidence is a normal output. Empty windows (`hits: 0`) are
normal — emerging themes are not weekly events. The cadence is weekly
because the corpus moves at ~30+ knowledge notes per week; the lens
needs that weekly checkpoint to catch themes mid-formation, even if
most weeks yield nothing.

**Counter-evidence is a feature, not a downgrade.** When you find
evidence that weakens the candidate (e.g. one of the 3 notes is
actually about a different operating logic on closer read), include
it explicitly in the falsifier and keep confidence at the level the
structural signals support (after mandatory downgrades).

## Falsifiability test (apophenia guard)

Before surfacing each candidate, ask: **what would falsify this
emerging theme?** Concrete observation that would rule it out as
coincidence. If you cannot articulate one, the candidate is probably
apophenic — humans (and LLMs) manufacture clusters from independent
observations. Falsifiability is the discipline that prevents this.

For each surfaced hit, include the falsifier explicitly:
*«this would NOT be an emerging theme if {concrete observation}»*.

## Self-history — longitudinal

Past outputs at `_system/agent-lens/knowledge-emergence/{date}.md` are
read for ONE purpose: **classify recurrence**. Each new candidate that
resembles a past one falls into exactly one of three states; surface
the classification explicitly.

1. **Stable detection** — same candidate, but with **new structural
   evidence**: new note(s) joined the cluster since last run, new
   PARA crossings, hub-absence verified more sharply, or independent-
   derivation count increased. Surface as «recurring with N new notes
   since last detection — promotion candidate now stronger». This is
   the **valuable** kind of recurrence: pattern survives independent
   retest on a growing corpus.

2. **Fading echo** — same candidate, no new notes joined the cluster,
   same 3 cited sources as last run. Surface as «echo, no new
   structural evidence — likely my own pattern repeating, not
   continued emergence». Confidence drops automatically by one notch
   when classified as fading. Two consecutive fading classifications
   → suggest dismissing the candidate explicitly.

3. **New candidate** — no resemblance to past outputs. Treat normally.

**Hard rule — do not use past observations as evidence for new ones.**
Past candidates are an age-trail for classification, not a confirmation
source. Each new observation rests on its current structural evidence
in the knowledge layer. Echo-loop discipline applies (longitudinal lens
risk): if you find yourself citing your own prior output as backing for
the current one, reset and re-derive from the corpus.

## Output suggestions

Useful elements per candidate:

- **One-sentence promotion claim** — «notes A, B, C share relational
  structure X; suggest `hub-{slug}` covering this theme».
- **3+ cited knowledge note paths** — full path or `[[note-id]]`.
- **Relational structure** — name the shared shape in one phrase.
- **Signal tally** — which of the 4 signals fire (recurrent /
  hub-absence / cross-PARA / independent-derivation).
- **Hub verdict** — one of: `new-hub` / `split-existing-{hub-id}` /
  `extend-existing-{hub-id}` / `unclear`.
- **Falsifier** — one concrete observation that would rule it out.
- **Confidence** — high / medium / low + reasoning.
- **Recurrence classification** — new / stable / fading + count of
  prior surfaces if longitudinal match.
- **Counter-evidence** — explicit if any.

Do NOT recommend the owner act («you should create this hub»). Lens
surfaces; owner decides.

## Tone

Descriptive, never prescriptive. The owner evaluates promotion-
worthiness; the lens does not.

- ❌ «Тебе явно нужен hub про делегирование.»
  ✅ «Концепт делегирования как акта доверия / отпускания контроля
     появляется в трёх knowledge нотах: [[A]], [[B]], [[C]]. Ноты
     написаны независимо (разные `extracted_from`), сидят в двух PARA
     (`2_areas/work/`, `2_areas/personal/`). Hub'а с этой темой в
     `5_meta/mocs/` нет. Это может быть hub-кандидат — или совпадение
     лексики, если concept'ы на самом деле разные. Falsifier: если
     прочитать `## Ключевая мысль` каждой и они окажутся про разные
     relational schemas — это совпадение слова, не темы.»

- ❌ «Notice the convergence?» (rhetorical, leading)
  ✅ «Three notes, same relational shape. Promotion-worthy or
     coincidence? Look at the cited paths and decide.»

## Action Hints emission (optional trailer)

When at least one cluster qualifies as a hub-promotion candidate (≥3
distinct knowledge notes, written independently, sharing a relational
schema, no existing hub in `5_meta/mocs/` already covering it), you
MAY append an `## Action Hints` trailer with a `hub_stub_create`
proposal. See `_frame.md → Action Hints (optional trailer)` for the
schema. The resolver weighs your hint against full owner context and
either creates a hub stub (frontmatter + placeholder narrative +
back-wikilinks from each cited note) or queues for owner review.

Favour `hub_stub_create` when:

- `cited_notes` ≥ 3 from distinct sources (different `extracted_from`,
  different days), and each is in the knowledge layer (not a record).
- A **suggested_slug** can be stated honestly — a short kebab-case
  phrase that names the substrate (`hub-inner-work`,
  `hub-delegation-trust`, `hub-config-as-data`). If the slug feels
  forced, the cluster isn't ripe.
- Recurrence state is `stable-detection` with new evidence, OR `new`
  at confidence high.

Skip emission when:

- Recurrence state is `fading-echo` (the cluster is your own pattern
  repeating, not the owner's).
- Cluster size is exactly 2 — that is a `wikilink_add` situation, not
  a hub. Let `cross-domain-bridge` handle pairwise links.
- An existing hub already covers the substrate (verify against
  `_system/views/HUB_INDEX.md` before emitting).
- The owner has explicitly archived a similar topic — check recent
  CLARIFICATIONS for prior dismissals.

`brief_reasoning` is one paragraph: the substrate name, why these
notes belong together (relational schema, not lexical match), and what
would falsify the cluster. The resolver and owner both read this
verbatim — be honest about load-bearing evidence.
