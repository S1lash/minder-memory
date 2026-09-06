---
id: minder-memory-integrations-minder-memory-mcp
title: minder-memory MCP — agent prompts for chat clients
type: integration-doc
created: '2026-04-27'
modified: '2026-04-28'
tags:
- type/integration-doc
- project/minder-memory-platform
---

# minder-memory MCP — agent prompts for chat clients

Reusable prompt templates for chat clients connected to a `minder-memory` MCP instance. They tell the model how to use the connector well — and, just as importantly, **when not to use it**.

Primary target: **Claude Desktop / Claude.ai** (where MCP support is most mature). The same prompts also work in **ChatGPT** without modification.

The MCP connector name is `minder-memory` on a new install (the platform standard; a connector configured under the former name keeps working unchanged). The prompts ship deliberately user-agnostic — they reference only Minder Memory platform conventions (PARA layout, `_system/` orientation files, frontmatter rules), no specific people, no owner-specific topics. Each operator can fork and tune them locally.

**Per-entity frontmatter the MCP consumer may filter on.** Every record / knowledge note / hub / person profile / project profile carries:
- `concepts: [...]` — snake_case ASCII concept names (open vocabulary; format spec in `_system/registries/CONCEPT_NAMING.md`)
- `audience_tags: [...]` — whitelist labels (canonical 5: `family`/`friends`/`work`/`professional-network`/`world`; tenant extensions in `_system/registries/AUDIENCES.md`). Empty `[]` = owner-only.
- `is_sensitive: true|false` — friction modifier (orthogonal to audience scope)
- `origin: personal|work|external` — provenance tag

These fields are conformant by Minder Memory-side construction (engine resolves all format issues autonomously); MCP queries can filter on them without re-validating shape.

## Files

The two `.md` files contain **only the text to copy-paste into a chat client**. No headers, no explanations — paste the whole file as-is. All meta and rationale lives in this README.

| File | Purpose |
|---|---|
| [`instructions-short.md`](instructions-short.md) | Account-level — global "behaviour" prompt for any chat client where the connector is attached. Default: do NOT call the connector. |
| [`instructions-project.md`](instructions-project.md) | Workspace-level — for a dedicated Claude Project or ChatGPT Custom GPT focused on Minder Memory work. Default: DO call the connector proactively. |

## Two-tier model with inverted defaults

The two prompts intentionally have **opposite defaults**.

| Tier | Default | Where it goes |
|---|---|---|
| Account-level | **Don't call the connector** unless explicitly invoked or a personal entity is named | Account / global custom instructions |
| Workspace-level | **Do call the connector** proactively — this workspace exists for Minder Memory work | Claude Project / ChatGPT Custom GPT |

### Why the inversion

Most chats with a flagship LLM have nothing to do with the notes (a kettle to buy, a generic career thought, a one-off web question). If the global profile encourages the connector, the model either over-fetches (slow, noisy citations on irrelevant questions) or develops fearful hedging ("should I check the notes? maybe? just in case?"). Either failure mode degrades day-to-day usefulness. So at the account level the rule is **don't touch Minder Memory unless explicitly invoked** — with two narrow exceptions to keep the door open.

When the operator wants serious Minder Memory work, they switch into a dedicated workspace where the connector is the point. There the default flips, and the model is told to query proactively. The heavy guidance — proactive triggers, prefetch optimisation, citation rules, frontmatter quirks — lives only in that workspace's instructions, not in the global profile.

## Where to paste — Claude Desktop (primary)

The prompts are written and tuned for **Claude Desktop / Claude.ai**, where MCP support is most mature.

- **Account-level (`instructions-short.md`).** Claude.ai → Settings → Profile → **Custom Instructions**. The same instruction set covers Claude.ai web, Claude Desktop, and Claude Mobile (one account profile, all surfaces).
- **Workspace-level (`instructions-project.md`).** Claude.ai sidebar → Projects → New Project (e.g. "Minder Memory"). Attach the `minder-memory` MCP connector under the Project's resources. Paste the file into the Project's **System Prompt** field. Claude Desktop and Claude Mobile pick up the Project automatically.

## Where to paste — ChatGPT (secondary)

The prompts are markdown-prose and work in ChatGPT instruction fields without modification. ChatGPT splits its instruction surface differently:

- **Account-level (`instructions-short.md`).** ChatGPT → Settings → Personalization → **Custom Instructions**. Paste the full file into the **"How would you like ChatGPT to respond?"** field. Leave the **"What would you like ChatGPT to know about you?"** field for personal identity blurb (out of scope here).
- **Workspace-level (`instructions-project.md`).** ChatGPT → Explore GPTs → Create → **Configure → Instructions**. Attach the `minder-memory` connector under Knowledge / Connectors. Paste the file as instructions.

## Personal identity / profile

These two files are intentionally identity-free. They explain how to use the connector, not who the operator is. Most operators will want to add a small personal blurb (role, current focus, working style, common topics) somewhere their workspace can see it — a Claude Project knowledge file, a ChatGPT custom-GPT description. That blurb is per-user and not shipped here. The most stable source for it is the operator's own `_system/SOUL.md` (or a curated extract).

## Iteration loop

1. Use the chat client with the current prompts for a few real conversations.
2. Note what failed: over-querying on a casual question? skipping prefetch in the workspace? hallucinating sources? wrong query language?
3. Edit the prompt files here.
4. Re-paste into the client (account-level field / workspace instructions).
5. Commit improvements.

Open avenues to explore:

- **Auto-prefetch heuristics** — currently relies on the model's judgment of "intent is vague". A stricter rule (e.g. "fewer than N specific tokens AND open question → prefetch") may help.
- **Per-workspace specialisation** — a Career-only Project, a Tech-only Project, etc., each with a tailored subset.
- **Voice-input handling** — transcripts have specific phrasing patterns; explicit guidance about handling transcript-derived facts vs curated notes might help.
- **Output-shape preference** — TLDR + sources + open questions baked into the workspace template.
- **What to do when query returns mostly `_sources/processed/` transcripts** — currently a performance note; could become a deterministic re-query policy.

## Reference

- Minder Memory platform conventions: PARA layout (`0_constitution/`, `1_projects/`, `2_areas/`, `3_resources/`, `4_archive/`, `5_meta/`), system layer (`_system/`), records (`_records/`), sources (`_sources/`).
- Orientation files used by the prefetch pattern: `_system/SOUL.md`, `_system/views/HUB_INDEX.md`, `_system/views/CURRENT_CONTEXT.md`.
- Minder Memory MCP server documentation: see your platform infra repo.
