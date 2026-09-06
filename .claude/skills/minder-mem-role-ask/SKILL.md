---
name: minder:mem:role:ask
description: >
  Ask a standing role what it knows. Answers from the role's own files
  and its run history — the memory it keeps between runs, not a fresh
  investigation. Read-only: takes no lock, writes nothing, never runs
  the role and never triggers a tick. When the role's own files do not
  answer the question, says so plainly and offers to go look in the
  base directly rather than filling the gap with something plausible.
disable-model-invocation: false
---

# /minder:mem:role:ask — Ask a role what it knows

A role keeps files between runs: that is its memory, and it is the only
thing it knows. This skill reads that memory and answers from it.

The answer is always **as of the role's last run**, never as of now.
Saying so is not a hedge; it is the difference between «the board had
three open items on Monday» and a claim about today that nobody checked.

Speak the owner's language. The role's own files are written in it.

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md`.

## When to invoke

- «What did the X role find?», «Is there anything open?», «When did it
  last see a change?»
- The owner suspects a role is doing nothing useful and wants to see
  what it has actually accumulated.

Do **not** invoke for: changing a role (`/minder:mem:role:edit`), listing roles
(`/minder:mem:role:list`), or making a role run now — this skill never runs
anything, and a role that is not due does not become due by being asked.

## Arguments

`$ARGUMENTS` — a free-text reference to the role, plus the question. Ask
for whichever is missing. With no question at all, summarise what the
role currently holds.

## Step 1 — Resolve the role

Resolve the reference exactly as `/minder:mem:role:edit` →
«## Resolving which role» specifies (source:
`integrations/claude-code/skills/minder-mem-role-edit/SKILL.md`). That section
is the single home of the rule — matching, confirming on a near-match,
what a resolved role's directory contains. Do not restate any of it
here.

## Step 2 — Read what it knows

Two sources, and only these two:

- **Its own files**, under the role's `state/` directory. Whatever is
  there is what the role decided to keep — a list, a running note, a
  date it last saw, a document it maintains. Read them all; they are
  small by design.
- **Its run history**, `log.jsonl`, one line per run. Each line carries
  when it ran, how it ended (`ok` did work, `idle` found nothing to do,
  `degraded` delivered with part of the job unverified, `error` failed)
  and a one-line note. This answers «has it been working», never «what
  did it find».

Read the role's `role.md` too, but only to know what the role was told
to keep and where — so an empty file reads as «nothing matched» rather
than «the role is broken».

## Step 3 — Answer, or say you cannot

Answer from what you read, and make the two statuses distinguishable:

- **What the files say** — state it directly, with when it was written.
- **What you conclude from them** — say it is your reading, and only
  when the owner's question turns on it.
- **What is not in them** — say so in one sentence and stop. Do not
  reconstruct the answer from the assignment («it was supposed to check
  the board, so presumably…»), from the base, or from what the role
  probably meant. An answer with no file behind it is indistinguishable
  from an answer with one, and that is the only way this skill can
  mislead.

When the files do not answer, offer the next step instead of inventing
one:

| What is missing | What to offer |
|---|---|
| The role has never run | Say so; the tick may not be scheduled on this machine |
| It ran, but its state is empty | Say so; its check may be finding nothing — `/minder:mem:role:edit` if that is wrong |
| The question is about the base, not the role | Offer to search the base directly, now, and answer from what is actually there |
| The question is about right now | Say the state is as of the last run, and offer the direct look |
| Its last runs are `error` | Report the notes verbatim and point at `/minder:mem:role:edit` |

Going and looking in the base is a normal, good answer — it is just no
longer the role speaking, and the owner is told which one they got.

## What this skill does NOT do

- **Never writes anything** — no lock, no state, no log, no commit.
  Answering a question must not change the memory the answer came from.
- **Never runs the role and never starts a tick.** «Ask it to check
  now» is not this skill; the role wakes on its own schedule.
- **Never repairs or reformats a role's files**, however untidy. They
  are the role's own, and the next run reads what it wrote.
- **Never reads the secrets store**, and never repeats a credential
  found in a state file — report that as a leak to fix, do not echo it.

## Failure modes

| Symptom | Cause | What to do |
|---|---|---|
| Role has no `state/` directory | It was created without a place to write, or has never run | Both are legitimate; say which one the log shows |
| State files are unreadable | Written by hand, or truncated mid-run | Report what you could read, name what you could not, do not guess the rest |
| The answer is stale | The role last ran days ago | Lead with the date; offer the direct look at the base |
| The role's notes contradict each other | Two runs disagreed and neither cleaned up | Report both with their dates; reconciling is the role's job, via `/minder:mem:role:edit` |
