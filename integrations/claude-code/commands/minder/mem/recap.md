---
name: minder:mem:recap
description: Summarize current Claude Code session and save as raw source for Zettelkasten processing. Can also save verbatim artifacts (toasts, letters, posts, specs) to crafted/. Use at end of important sessions.
---

# /minder:mem:recap — Session Recap to Minder Memory

Capture the current conversation into Minder Memory raw sources for later processing by `/minder:mem:process`.

Two kinds of output, chosen adaptively:

- **Recap** → `_sources/inbox/claude-sessions/` — a structured *summary* of the session (decisions, work, insights). Never verbatim.
- **Crafted artifact** → `_sources/inbox/crafted/` — a *verbatim* standalone piece the owner co-authored and will reuse as-is (toast, speech, letter, post/thread, proposal, manifesto, spec, poem, cover letter). Exact wording is preserved.

The skill picks the right combination for the situation. It never forces an output the user did not ask for or agree to.

## Arguments: $ARGUMENTS

Free-form. Recognised intents (natural language works too — match meaning, not exact flags):

- *(empty)* — recap, and **propose** a crafted artifact only if one clearly exists (see Step 0).
- `--crafted` / "save the original too" / "и оригинал положи" — recap **plus** crafted artifact.
- `--crafted-only` / "just save the original" / "только оригинал, без рекапа" — crafted artifact **only**, no recap.
- `--no-crafted` / "recap only" — recap only; do not propose crafted even if one exists.
- Anything else — treat as topic override / extra tags.

## Execution

### 0. Decide mode (adaptive)

First honour any explicit intent in `$ARGUMENTS`. If none, decide proactively:

1. Scan the session for a **crafted artifact**: a self-contained piece of writing whose *exact wording matters* and that the owner will reuse outside this chat. Signals: the owner pasted or iterated on a finished text; asked to "craft / write me a …"; the piece reads as deliverable, not as conversation. Drafts the owner explicitly discarded do not count.
2. Resolve to one of three modes:
   - **recap** — no qualifying artifact (default).
   - **recap + crafted** — a qualifying artifact exists alongside substantial session work.
   - **crafted-only** — the session was essentially *just* producing the artifact, or the user asked for original-only.
3. When you detected the artifact yourself (not asked), **state the choice and proceed** — e.g. "Session produced a finished toast; saving it verbatim to crafted/ and a recap alongside." If the user is present and it's ambiguous, ask one short question. Never silently drop a verbatim artifact the owner clearly wants kept, and never silently fabricate one.

**Rule of thumb:** if losing the exact wording would be a loss → crafted. If only the gist matters → recap.

### 1. Analyze the session

Extract: main topic (1-3 words for slug), category (Work / Career / Personal — may be multiple), key decisions + rationale, work done (files, research), insights & ideas, tasks / follow-ups, people mentioned, projects touched. For any crafted artifact, also capture its **exact text** and a one-line **context** (what it is, for whom, on what it's grounded).

### 2. Determine metadata

- **Date**: today (`YYYY-MM-DD`).
- **Recap folder**: `{YYYY-MM-DD}_{semantic-topic}` (e.g. `2026-04-01_skills-setup`).
- **Crafted file**: `{YYYY-MM-DD}_{semantic-slug}.md` (flat in `crafted/`).
- **Category tags**: from content (`#Work`, `#Career`, `#Personal`, `#AI`, `#Coding`, …).

### 3. Write the crafted artifact (if mode includes crafted)

**Path:** `{{MINDER_MEMORY_BASE}}/_sources/inbox/crafted/{YYYY-MM-DD}_{slug}.md`

**Format** (matches existing crafted sources — header block, no YAML, then the verbatim body):

```markdown
# {Artifact Title}

**Date**: YYYY-MM-DD
**Category**: {Personal|Work|Ideas_and_Concepts|…}
**Tags**: #tag1 #tag2
**Source session**: `_sources/inbox/claude-sessions/{recap_folder}/transcript.md`   ← omit this line in crafted-only mode
**Context**: {1-2 sentences — what this is, who it's for, what it's grounded on}

---

{The artifact, VERBATIM. Preserve the owner's exact wording, spelling, punctuation,
line breaks. If the owner pasted source originals, keep them byte-for-byte. Separate
distinct pieces with `## ` section headers. Do NOT clean up, paraphrase, or "improve".}
```

If the artifact draws on existing Minder Memory notes, add `[[wikilinks]]` in the **Context** line only — never edit the verbatim body.

### 4. Write the recap (if mode includes recap)

**Path:** `{{MINDER_MEMORY_BASE}}/_sources/inbox/claude-sessions/{recap_folder}/transcript.md`

**Format:**

```markdown
# Claude Session: {Descriptive Title}

**Date**: YYYY-MM-DD
**Category**: {Work|Career|Personal}
**Tags**: #claude-session #tag1 #tag2
**Source**: Claude Code CLI session
**Project**: {working directory or project name}
**Crafted artifacts**: `_sources/inbox/crafted/{file}.md` — {one line}   ← include only when a crafted file was written this run

---

## Summary

{2-3 sentence overview of the session}

## Key Decisions

- {Decision}: {rationale}

## Work Done

- {What was accomplished — files, features, research, with paths}

## Insights & Ideas

- 💡 {Non-obvious insight or idea that emerged}

## Tasks & Follow-ups

- [ ] {Follow-up}

## Key Exchanges

{3-5 most important moments — paraphrased, not verbatim. Enough context for /minder:mem:process
to author a rich note. The verbatim artifact lives in the crafted file, not here.}
```

### 5. Confirm

- Show the path(s) written (crafted and/or recap).
- Show a brief preview (first ~10 lines of each).
- If a crafted+recap pair was written, confirm the **bidirectional link** is present (recap `Crafted artifacts:` ↔ crafted `Source session:`).
- Remind: "Run `/minder:mem:process` to convert these into Zettelkasten notes."

## Important Rules

- **Language**: same language as the session (Russian if the session was in Russian).
- **Verbatim split**: crafted = exact wording preserved; recap = summarized, never a verbatim dump. Keep them on the right sides.
- **Bidirectional link**: whenever both are written in one run, each points at the other. Reason: the two files may be processed in different `/minder:mem:process` batches; a one-way pointer breaks if only one side is processed.
- **Don't restrict the user**: crafted-only with no recap is valid; recap-only is valid; both is valid.
- **Sensitivity**: do not redact — `/minder:mem:process` assigns the privacy trio (`is_sensitive`, `audience_tags`). Just preserve and let downstream classify.
- **Be honest about what happened**: include failures, pivots, dead ends — they have learning value.
- **One recap per session**: even across multiple topics. Multiple crafted files are fine if the session produced several distinct artifacts.

## Examples

```
/minder:mem:recap                          # recap; proposes crafted if a finished piece exists
/minder:mem:recap --crafted                # recap + save the verbatim artifact
/minder:mem:recap --crafted-only           # just save the original, no recap
/minder:mem:recap --no-crafted             # recap only, suppress proposal
/minder:mem:recap workspace reorganization # topic override
```
