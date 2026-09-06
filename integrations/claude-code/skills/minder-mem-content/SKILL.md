---
name: minder:mem:content
description: >
  The content pipeline's actor. Default mode shows status from CONTENT_MAP.md —
  themes by ripeness, what changed since last run, the drafts shelf. `--draft
  <topic>` is the owner-controlled manual path: generate one ready-to-edit draft
  on demand. `--maintain` is the scheduled draft-maintainer (the sole actor):
  reads the content-synthesis lens output and keeps living drafts in
  6_posts/drafts/ alive — create or update on ripe/strengthened themes, never
  rewrite an owner-edited draft, archive published ones. Publishing stays a manual
  owner act — the bright line. Additive + idempotent + resumable.
disable-model-invocation: false
---

# /minder:mem:content — content pipeline actor

This skill is the **drafting organ** of the content pipeline. The classification
and outside-view reasoning live upstream in the `content-synthesis` lens (the
sole classifier); this skill is the **sole actor** that turns ripe themes into
living drafts. The two run sequentially in the weekly content tick (lens Monday,
maintainer Tuesday) — for the owner it is one autonomous weekly run.

**The bright line:** auto-DRAFT to `6_posts/drafts/` (status: draft) is additive,
reversible, owner-visible → allowed. **Auto-PUBLISH is never allowed.** The owner
publishes manually (Telegram / LinkedIn — a separate vector, out of scope).

## Arguments

| Invocation | Mode | Purpose |
|---|---|---|
| (no args) | **status** | Read-only. Show themes by ripeness from the map, what strengthened since the ledger, the drafts shelf, a companion nudge. Writes nothing. |
| `--draft <topic>` | **manual draft** | Owner-controlled. Generate one ready-to-edit draft for a topic/theme on demand, regardless of ripeness change. |
| `--maintain` | **draft-maintainer** | The scheduled actor. Read the latest lens output + map + ledger; create/update/archive living drafts per the lifecycle; update the ledger. Resumable, idempotent. |

---

**Working directory:** the zettelkasten base. Every path and every `python3`
command in this file is written relative to it; `scripts/` (the scheduler
helpers) sits one level above, at the repo root.

## Cross-skill lock (writing modes only)

`--maintain` and `--draft` write owner data (drafts + ledger) and read
`CONTENT_MAP.md` while `/minder:mem:maintain` Step 7.8 may be rewriting it. So at the
start of a writing run, read every pipeline lock under `_sources/` (the set is
owned whole by `_system/docs/SYSTEM_CONFIG.md` → «Cross-skill exclusion»; read
it there rather than keeping a second copy that drifts) — abort if any is
recent (<2h) — then acquire `.content.lock`
(touch it), and remove it when done. The default **status** mode is read-only and
takes no lock. (Scheduler ticks run `lock-check.sh` before invoking the skill;
this guard also covers interactive runs.)

## Step 0: Load context

Read, in order:

1. `_system/views/CONTENT_MAP.md` — **the interface.** Do NOT re-scan all notes;
   the map is the canonical compact view (`/minder:mem:maintain` keeps it fresh). Drill
   into individual note bodies only for the themes you actually draft.
2. `_system/state/content-pipeline-state.json` — the ledger (per-draft state).
   If it is missing (fresh clone), seed it once by copying
   `_system/state/content-pipeline-state.template.json` to that path.
3. `_system/POSTS.md` — published posts (anti-repetition + archive triggers).
4. `_system/SOUL.md` — Identity + voice/values calibration (read the owner's name
   + working style; never hardcode a name).
5. `5_meta/PROCESSING_PRINCIPLES.md` — values profile for tone.
6. **`--maintain` only:** the latest `_system/agent-lens/content-synthesis/{date}.md`
   — the lens verdict. **Structure** (defined by the lens's `output_schema:
   synthesis-custom` — see `registries/lenses/content-synthesis/prompt.md`):
   markdown, one `## Candidate N` block per surfaced post, each with `Verdict`,
   `theme_ids` (hub ids, or `note:{id}` for a standalone), `Ripeness` (per theme),
   `Angle`, `Uncovered`, `Adjacent published`, `Related hubs`, and (cross-theme)
   `Falsifier`. One candidate = one draft. Read it **directly** (the maintainer is
   the lens's dedicated consumer — not via resolver Action Hints, which is the
   resolver's mechanism). If the file is missing/failed this week → no-op gracefully
   (best-effort; the next tick recovers). If the latest output's `run_at` is
   **older than ~8 days** (the Monday lens tick was skipped — laptop offline),
   note it in the self-surface and lean conservative: ripeness is still re-derived
   from the *current* map, but treat the stale verdict list as possibly missing
   themes that ripened since, and do not archive on a stale run.

### content_type assumption

Assume `content_type` is canonical (lint Scan A.11 heals drift at the source).
Keep only a **thin defensive fallback** for a not-yet-linted note: treat any
non-canonical value as `insight` for routing purposes and note it — **do NOT
re-canonicalize and do NOT duplicate lint's `CANON_MAP`** (single SoT lives in
`lint_content_markup.py`). Healing drift is lint's job, not this skill's.

---

## Mode: status (default) — read-only

Render a scannable status from the map + ledger. Write nothing.

1. **Themes by ripeness** (top of the map): per theme — note count, ripeness,
   posts-on-theme, and its draft state from the ledger (no draft / auto draft /
   owner-editing / strengthened-since-last-surfaced).
2. **What changed** — themes whose current map ripeness exceeds the ledger
   `last_surfaced_ripeness` (the strengthened set — what the next `--maintain`
   would act on), and any draft flagged `new insight available`.
3. **Drafts shelf** — list `6_posts/drafts/` with status (auto / owner-editing /
   stale / archived).
4. **Companion nudge** (publishing-friction guard — the barrier is emotional, not
   tooling): one lowest-friction pick with reasoning, progress ("you've published
   N, M drafts are warm"), one concrete micro-action — never a menu. Keep it
   honest and brief; do not nag.

---

## Mode: `--draft <topic>` — manual single draft (owner path)

The owner-controlled manual entry. Generates a draft regardless of ripeness
change — the owner asked for it.

1. Resolve `<topic>` to a theme: match a hub/theme in the map, else fuzzy-match
   note titles/angles. If nothing matches → report "no matching content for
   '{topic}'" and stop.
2. Read the matched theme's source notes in full (not just frontmatter).
3. Generate the draft (see **Draft generation** below) using the note's
   `content_angle` and the owner's voice (SOUL).
4. Write to `6_posts/drafts/{YYYYMMDD}-draft-{slug}.md`, upsert a ledger entry,
   display the draft inline for immediate review.

---

## Mode: `--maintain` — the draft-maintainer (sole actor)

The scheduled organ. **Trusts the lens verdict — does NOT re-classify.**

**The unit is the lens candidate, and one candidate = one draft.** The lens has
already split each ripe theme into its genuinely distinct post-angles (and the
standalones and bridges) — so a rich theme arrives as *several* candidates, each
its own draft. The maintainer iterates candidates (matched to ledger drafts by
`draft_id`), not themes. The lifecycle below is per draft.

### Lifecycle (all idempotent)

| Candidate state (lens verdict × ledger) | Draft action |
|---|---|
| ripe + no draft for this candidate yet | **create** draft (status: auto); add ledger entry |
| strengthened (ripeness score up — see the test below) + **auto** draft | **update** draft; append an Evidence-Trail-style "what's new" note; bump ledger `last_surfaced` + `last_surfaced_ripeness` |
| strengthened + **owner-editing** draft | **do NOT touch**; set ledger `new_insight_available: true` (surfaced in status) |
| published (a matching post appears in POSTS.md) | **archive** draft → `6_posts/drafts/archived/` (record reason); ledger `draft_status: archived-published`. Applies even to an `owner-editing` draft |
| stable, untouched | leave as-is |
| de-ripened (notes archived / lost `content_potential`, theme below ready) + auto draft | mark draft `stale — material thinned`; do **NOT** delete (owner decides) |
| published + substantial *new* material later | conservative: surface "follow-up?" — do **NOT** auto-resurrect |

### Ripeness comparison — the exact "strengthened / de-ripened" test

`last_surfaced_ripeness` in the ledger is a **per-theme map**:
`{ "<theme_id>": { "note_count": N, "score": S }, ... }` — one entry per
`theme_id` the draft references. `score` is the map's ripeness for that hub
(`convergence × note_count × avg_potential`); the renderer is the SoT.

To classify a draft on each run, read the **current** ripeness of each of its
`theme_ids` from `CONTENT_MAP.md` (read the value, never recompute the formula)
and compare to the ledger. Two shapes of `theme_id`:
- a **hub id** (`hub-...`) → parse `ripeness {SCORE} · {COUNT} note(s)` on the
  theme heading.
- a **standalone** (`note:{id}`, a strong note surfaced on its own) → find the
  `[[{id}]]` line anywhere in the map (every content-note line carries its own
  `ripeness {SCORE}`, whether the note sits under a hub or in Unclustered) and
  parse that.

Then compare to the ledger:

- **strengthened** — for ANY `theme_id`, current `score` > ledger
  `last_surfaced_ripeness[theme_id].score` (a higher score means a note joined or
  potential rose). For a cross-theme draft this is why the map must be per-theme:
  one constituent rising is enough.
- **stable** — every `theme_id`'s current score == its ledger score → no-op.
- **de-ripened** — for ALL `theme_id`s, current score < ledger score (material
  thinned) → mark the auto draft `stale`, never delete.

After acting, write the current per-theme ripeness back to
`last_surfaced_ripeness` so the next run diffs against the new baseline.

### Owner-edit guard (load-bearing)

The first time the owner edits an auto draft, the maintainer must stop rewriting
it. Detection is by a **deterministic** content hash:

- Compute the hash with the helper — `python3 _system/scripts/content_draft_hash.py
  <draft-path>` (sha256 of the body below frontmatter, each line rstripped). It is
  body-only on purpose: a frontmatter `status:` flip is not an owner edit. Using
  the helper (not an LLM-computed hash) is what makes the guard reliable.
- The ledger stores `last_auto_hash` = that hash at the maintainer's last write.
- On each run, for an `auto` draft, recompute. If it differs from `last_auto_hash`
  → the owner edited it: set `owner_touched: true`, `draft_status: owner-editing`.
  From then on the maintainer **only flags** (`new_insight_available`), never
  rewrites.
- Whenever the maintainer itself writes/updates a draft (create or update), it
  recomputes and stores the new `last_auto_hash` in the same ledger write — so its
  own edit never false-trips the guard on the next run.

### Cross-theme drafts (first-class)

A draft may reference a **set** of `theme_ids` (length 1 single-theme, N
cross-theme). Cross-theme candidates come from the lens output (which reads
`cross-domain-bridge`), never from mechanical pairing here. A cross-theme draft
is updated when **any** constituent theme strengthens — see the per-theme test
above (`last_surfaced_ripeness` keyed by `theme_id` is what makes "which one
rose" answerable).

### Published-match rule (how the maintainer knows a draft was published)

POSTS.md is owner-maintained: when the owner publishes, they add a row whose
`Source Notes` lists the note(s) the post drew from. A draft counts as
**published** when a POSTS.md `Source Notes` cell shares **≥ 1 note id** with the
draft's `source_notes` (the draft's notes are the evidence the post was built
from). On match: record the matched post id(s) into the ledger
`published_post_ids`, set `draft_status: archived-published`, and move the draft
to `6_posts/drafts/archived/`. If the owner instead filled the ledger
`published_post_ids` by hand, honour that directly. A theme already covered by a
published post is not re-drafted unless it strengthens **substantially** after
the publish (then: surface "follow-up?", never auto-resurrect).

### No cap · resumable chunks

Draft **all** ripe themes + all genuine cross-theme bridges — no top-N limit
(the owner wants the full warm shelf). Robustness comes from **resumable chunked
execution**, not truncation: process **draft-by-draft**, writing the ledger entry
immediately after each draft (draft file first, then its ledger entry). If the run
is interrupted or hits a budget/time limit, the next run resumes where it stopped
(the ledger records what is already drafted — re-running a done theme is a no-op).
**Crash-between guard:** before drafting a candidate, if its `draft_path` already
exists on disk but has **no** ledger entry (a crash landed the file but not the
entry), do NOT overwrite and do NOT trust it as pristine — you cannot prove the
owner hasn't edited it since. Adopt it **conservatively as `owner-editing`**
(`owner_touched: true`, `last_auto_hash` = its current hash) so the maintainer
only flags it thereafter, never rewrites. This loses no owner edit. On a large
first run (cold-start) resumability is the whole safeguard — there is no cap
behind it.

### Self-surface

End a `--maintain` run by printing one "what changed this week" line to the run's
**stdout / report** (not a CLARIFICATION, not a separate file) — the content
pipeline surfaces itself, so nothing else needs to remind the owner about the
backlog. State separate counts: `created: N · updated: M · owner-editing flagged:
K · archived: A · stale: S`. No publish prompt — the bright line.

### Manifest

`--maintain` emits **no** batch manifest. Its only outputs are pre-publication
drafts in `6_posts/drafts/` (owner staging — the published SoT is POSTS.md, filled
manually when the owner ships) and the `content-pipeline-state.json` ledger
(working state). Neither is a downstream-consumer contract under ENGINE_DOCTRINE
§3.8 (which excludes working memory and owner-facing staging). Content-flagged
*notes* already appear in `/minder:mem:process`'s manifest.

### Lock release

Release `.content.lock` after the **final** ledger write of the run (the last
thing the maintainer does). On crash mid-run it lingers and is cleared as stale
(>2h) by the next tick's `lock-check`.

---

## Draft generation (shared by `--draft` and `--maintain`)

A draft is a **conceptual post** — the substance: the idea, the argument, the
narrative — **not** a platform-specific, ready-to-paste artifact. Platform
(LinkedIn / Telegram / both) and final language are the owner's **publish-time**
decisions, made when they pick a draft to ship; the shelf exists so the
blank-page barrier is gone, in a form the owner can read and rework comfortably.

1. Read all source notes for this angle (full bodies). One draft = **one
   genuinely distinct angle**, not one-per-note and not one-per-hub: a rich theme
   with several real angles yields several drafts; a strong standalone
   (unclustered) note with a clear angle is its own draft; thin/duplicative
   material is not forced into a post.
2. **Language: the owner's primary language** — read it from `SOUL.md` (Identity /
   working style); never hardcode a language (the engine ships to friends in many
   languages). Write the whole shelf in that one language so the owner works in
   their own tongue; translation to another language is a publish-time step, not
   a drafting one.
3. **Voice: the owner's** (SOUL) — their register, their idiom. The draft is a
   real, reworkable first draft (a coherent post, not an outline/stub), long
   enough to carry the idea; trim platform-fitting (char limits, hashtags) — that
   is publish-time, not now.
4. Draft frontmatter:
   ```yaml
   ---
   draft_for: "{topic / angle title}"
   theme_ids: [{hub-id or theme slug}, ...]
   content_type: "{dominant canonical type of the source notes}"
   angle_used: "{the specific angle this draft is built on}"
   platform_hint: "{optional, non-binding — where this would likely fit, e.g.
                    linkedin | telegram | both; a convenience hint, never a gate}"
   source_notes: [{note-id}, ...]
   status: draft
   created: {YYYY-MM-DD}
   ---
   ```
   `platform_hint` is **optional** and advisory only — omit it if unsure. There is
   no per-platform body and no per-platform language: one conceptual draft.
5. Path: `6_posts/drafts/{YYYYMMDD}-draft-{slug}.md` (create dirs if needed).

A draft is a **living document** (engine precedent: the `/minder:mem:process` Idea
Living Document pattern). Updates append a dated "what's new" note rather than
rewriting wholesale, so the owner can see what changed.

---

## Ledger entry (the only state this skill writes)

Per draft, in `_system/state/content-pipeline-state.json` `drafts[]`:

```json
{
  "draft_id": "project-alpha-x-team-management",
  "theme_ids": ["hub-project-alpha", "hub-team-communication"],
  "last_surfaced": "2026-06-15",
  "last_surfaced_ripeness": {
    "hub-project-alpha": { "note_count": 14, "score": 99.0 },
    "hub-team-communication": { "note_count": 34, "score": 605.0 }
  },
  "draft_path": "6_posts/drafts/20260615-draft-project-alpha-x-team-management.md",
  "draft_status": "auto | owner-editing | archived-published | stale",
  "owner_touched": false,
  "new_insight_available": false,
  "last_auto_hash": "<content_draft_hash.py of last maintainer-written body>",
  "published_post_ids": []
}
```

Write the entry immediately after each draft action (resumability). Never rewrite
historical entries beyond their own state transitions; the ledger is incremental.

---

## Hard rules

- **Never publish.** Drafts are `status: draft`; the owner publishes manually.
- **Never rewrite an owner-edited draft** (owner-edit guard). Flag only.
- **The map is the interface** — read it, don't re-scan the whole corpus.
- **Single SoT** — never duplicate lint's `content_type` table; never write the
  CONTENT_MAP (that's `/minder:mem:maintain`); the ledger is this skill's only state.
- **Idempotent + resumable** — re-running on unchanged themes is a no-op; an
  interrupted run resumes from the ledger.
- **Best-effort** — a missing/failed lens output → no-op gracefully.

## Examples

```bash
/minder:mem:content                       # status: themes by ripeness, what changed, drafts shelf
/minder:mem:content --draft "remote work"   # generate one draft on demand
/minder:mem:content --maintain            # scheduled draft-maintainer (run after the lens tick)
```
