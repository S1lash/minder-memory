# Using this Minder

The section above told you how the run works. This one tells you how the **base**
works — what lives where, how to find it, and the one way you put something back
into it.

---

## The shape of the base

Three layers, each a different grain of the same material.

| Layer | Where | What it holds |
|---|---|---|
| Records | `_records/meetings/`, `_records/observations/` | One file per captured conversation or solo recording, dated. Meetings are multi-speaker; observations are the owner alone — reflections, ideas, therapy. This is the raw operational memory |
| Knowledge | `1_projects/`, `2_areas/`, `3_resources/`, `4_archive/` | Distilled notes — decisions, insights, reflections, ideas, technical writeups. A claim about what the owner *thinks* belongs here, not in a record |
| Hubs | `5_meta/mocs/hub-*.md` | Per-theme synthesis: current understanding plus how it got there. The place to read before asserting how a topic evolved |

Two more, machine-produced: `_records/biometric/<device>/` and
`_records/activity/<source>/` — one deterministic file per day.

Behind every record sits its raw material in `_sources/processed/<source-id>/`.
Open it when a record is too compressed to answer the question.

---

## Finding things

Start from an index. A blind grep across the whole base is slow and misses
synonyms.

- `_system/views/INDEX.md` — catalog of every knowledge note, archived note,
  constitution entry and hub.
- `_system/views/HUB_INDEX.md` — every hub, with its theme.
- `_system/views/CURRENT_CONTEXT.md` — what the owner is on right now.
- `_system/state/OPEN_THREADS.md` — threads still unresolved.
- `_system/TASKS.md`, `_system/CALENDAR.md` — open tasks and dated events,
  aggregated from the notes.
- `_system/SOUL.md` — identity, focus, working style. Read once when the
  assignment is about the owner rather than about a topic.

Then narrow with frontmatter, which every record and note carries and which is a
far better filter than body text: `created:`, `people:`, `projects:`,
`concepts:`, `domains:`, `tags:`, `type:`, `origin:`, `is_sensitive:`.

Vocabularies live in `_system/registries/`: `TAGS.md` for `tags:`,
`CONCEPTS.md` + `CONCEPT_NAMING.md` for `concepts:` (`CONCEPTS.md` is
generated, so on a base whose owner has not run a maintain pass yet it is simply
absent — read the naming rules and move on), `DOMAINS.md` for
`domains:`, `FOLDERS.md` for where a note of a given kind is filed.

---

## People and projects resolve through their registries

- `3_resources/people/PEOPLE.md` — display name → person id. A person with a
  profile has one at `3_resources/people/{id}.md`.
- `1_projects/PROJECTS.md` — project name → project id.

Resolve through the registry every time. Never infer an id from a name you read
in a transcript: speech-to-text garbles names, and two spellings of one person
are the norm. No matching row means the base does not know that person or
project — say so; do not create one.

---

## Putting something back into the base

You do not write records or knowledge notes — those are produced by
`/minder:mem:process` from sources. If your work found something the base should know,
leave **one note in the inbox** and the next `/minder:mem:process` run folds it in like
any other source. This needs `inbox` among your allowed writes.

- **One flat file** directly in `_sources/inbox/roles/`. Never a subfolder — the
  source is registered `flat-md`, and a nested path is out of your zone and gets
  reverted.
- **Name it** `YYYY-MM-DD-<your-role-id>-<short-slug>.md`. The date orders the
  file against everything else in the inbox. Keep the whole name ASCII and free
  of `< > : " / \ | ? *` — those are illegal on Windows and the engine will
  rename the file before reading it.
- **Frontmatter is one line** — the provenance no path can carry:

  ```yaml
  ---
  source: role:<your-role-id>
  ---
  ```

  `/minder:mem:process` does not parse this block; it reads the whole file as content
  and classifies it like any other source. The line is there so the note's origin
  stays legible after it moves to `_sources/processed/roles/` and a record cites
  it.

- **The body is a note, not a report.** Write it the way the owner would say it,
  in their language: what you found, why it matters, who and what it touches. No
  tables of run statistics, no JSON, no status header. The pipeline's first gate
  asks whether the file is genuine content — a machine dump reads as noise and is
  dropped.
- **One note per run**, covering everything worth saying, not one per finding.
- Only what you actually read or fetched goes in it. A note that guesses becomes
  a record that lies.

---

## Everything else is read-only

You may read all of the base — follow links, open anything. You may write only
the paths listed in your allowed-writes block above.

Registries, views and indexes are produced by the engine's own skills; editing
one by hand is out of zone and would be overwritten anyway. A note carrying
`is_sensitive: true` is owner-only material — never carry its content into an
external system you reach.

---

## Engine scripts

`_system/scripts/` is the engine's own machinery, not a toolbox. **One script is
yours to run unasked:**

```bash
python3 zettelkasten/_system/scripts/query_constitution.py --compact
```

It prints the owner's active principles as JSON. Reads only, writes nothing,
takes no lock. Worth reaching for when your assignment asks you to weigh
something against them and the constitution is not already in your prompt.

**Every other script there is off-limits unless your assignment names it.** Most
of them write, and nothing in a filename tells you which.

- **`roles_run.py` is the runner that is running you — never invoke it.** Not to
  verify your own compliance, not to see whether you are due. A second `check`
  for your role exits non-zero, your runner reads that as a broken guard, and
  every role after you tonight is simply not run. `tick-begin` destroys the
  baseline that decides what may be reverted; `log` forges your own run line.
- **No pipeline skill** — `/minder:mem:process`, `/minder:mem:lint`, `/minder:mem:maintain`,
  `/minder:mem:agent-lens` and their siblings. The tick running you holds `.roles.lock`
  and every one of them aborts on it, so you would only be blocking against your
  own runner. Your inbox note reaches `/minder:mem:process` on its own schedule.
- **Never run git, and never write engine state outside your allowed paths.** A
  commit from inside a role is reported as an error; an out-of-zone write is
  reverted.

When your assignment *does* name a script, running it is the job — the recorded
verdict through `query_constitution.py` and `record_decision_run.py --no-commit` is
the path that exists. Run it exactly as written, flags included: its audit file
is already in your allowed writes, and `--no-commit` is what stops it committing
on your behalf.
