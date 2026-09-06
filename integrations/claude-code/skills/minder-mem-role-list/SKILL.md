---
name: minder:mem:role:list
description: >
  Show the owner's standing roles — what each one watches, when it wakes,
  when it last ran and how that went, and whether it is running or
  paused. Read-only: takes no lock, changes nothing, never runs a role.
  Given a reference to one role, shows that role in more detail instead
  of the whole roster. When there are no roles yet, says so and offers
  to create one.
disable-model-invocation: false
---

# /minder:mem:role:list — What is standing

The owner's answer to «what do I have running, and is it alive?». One
short block per role, in plain language. Nothing is written and no lock
is taken, so it is safe at any moment, including while a tick runs.

Speak the owner's language. Their roles are described in it.

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md`.

## When to invoke

- The owner asks what roles exist, or whether one is still running.
- Before `/minder:mem:role:edit` or `/minder:mem:role:ask`, when the owner cannot
  recall what they called a role.

Do **not** invoke for: what a role found (`/minder:mem:role:ask`), changing a
role (`/minder:mem:role:edit`), or running one (`/minder:mem:roles`).

## Arguments

`$ARGUMENTS` — optionally a free-text reference to one role. Given one,
show that role alone, with its last few runs instead of just the last.

## Step 1 — Read the roster

Derive `$BASE` and read the roster exactly as `/minder:mem:role:edit` →
«## Resolving which role» step 1 does (source:
`integrations/claude-code/skills/minder-mem-role-edit/SKILL.md`) — that step is
the single home of both the derivation and the reason the base
directory's name is never assumed. Then:

```bash
python3 "$BASE/_system/scripts/roles_run.py" due --base "$BASE" --repo "$REPO"
```

Both paths absolute, from that same derivation — a bare `.` makes the
answer depend on where the session happens to stand.

One JSON row per role: `id`, `name`, `due`, `reason`, `status`. This is
the only enumeration — never glob the roles directory.

Empty list → the owner has no roles. Say exactly that, in one line,
and offer `/minder:mem:role:add` with one concrete example of what a role
could do for them. Stop there.

When a reference was given, resolve it by that same section — matching,
and confirming on a near-match. Do not restate any of it here.

## Step 2 — Fill in each row

For every role in the roster, read two more things:

- its `role.md` — the assignment says what it watches; the frontmatter
  says when it wakes and what it may change;
- the last line of its `log.jsonl` — when it last ran, how it ended
  (`ok` did work, `idle` found nothing to do, `degraded` delivered with
  part of the job unverified, `error` failed), and its one-line note. No log, or no line in it, means no run has ever
  completed — read the rendering rule below before calling that «new».

A role whose `role.md` is malformed comes back with `status: "unknown"`
and the parser's complaint as its `reason`. Do not try to read past it —
show it as needing attention, in one line, and point at
`/minder:mem:role:edit`.

## Step 3 — Render

Per role, four lines at most:

```
{name} — {what it watches, one clause in the owner's own words}
  wakes: {schedule as a sentence}
  last run: {when}, {what happened} — {note, if there is one}
  {paused, if it is}
```

Say a role's schedule, its write destinations and its reach the same way
`/minder:mem:role:edit` → «## Step 1 — Say what it is today» says them (source:
`integrations/claude-code/skills/minder-mem-role-edit/SKILL.md`) — that section
owns how a role is put into plain language. What is particular to a
roster:

- **Active roles first**, paused ones after, under a one-word divider.
  A role that has never run and a role that failed last time both belong
  in the active group — they are standing, they are just not healthy.
- **`idle` is not a problem.** A role whose check found nothing to do
  did the right thing. Do not render it as a failure.
- **`degraded` is neither.** The role ran and delivered; part of its job
  went unverified. Render it as it is, with the note — folded into «ok»
  it disappears, and a limit hit every night hollows the role out while
  the roster still reads healthy.
- **Never print a bare «never run».** A role with no run history is
  either brand new or its wake-up never comes due — a schedule carrying
  a time of day only fires if a tick runs at or after that hour, and a
  role that never ran leaves no line, so the two look identical from its
  files. Name both possibilities in one line and point at
  `/minder:mem:role:edit`; only the owner knows when their scheduler runs.

Close with one line only when it earns itself: a role that errored on
its last run, or that has never run despite being due for a while, is
worth naming with `/minder:mem:role:ask` or `/minder:mem:role:edit` as the next step.

## What this skill does NOT do

- **Never writes anything** — no lock, no state, no log, no commit.
- **Never runs a role**, and never triggers a tick.
- **Never reads a role's `state/` files.** What a role found is
  `/minder:mem:role:ask`'s question; this skill answers whether it is alive.
- **Never repairs a malformed role** — it reports one and points at
  `/minder:mem:role:edit`.

## Failure modes

| Symptom | Cause | What to do |
|---|---|---|
| Roster is empty | No roles yet, or `$BASE` came back empty because the derivation found zero bases or more than one | Offer `/minder:mem:role:add`; if the derivation did not resolve one base, repeat its reason rather than reporting «no roles» |
| A role shows as `unknown` | Its `role.md` is malformed | Report it in one line, point at `/minder:mem:role:edit` |
| «Last run» is missing for everything | The tick has never run on this machine | Say so plainly — a role only runs where its scheduler runs |
| One role alone has never run | Brand new, or its wake-up hour never comes due | Name both; `/minder:mem:role:edit` is where the schedule is settled |
| A role is due but its last run is old | The tick is not scheduled, or it errors before reaching this role | Its log's last line usually names the reason |
