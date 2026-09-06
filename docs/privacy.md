# Privacy & data ownership

Where your data lives, what travels where, what stays local. Read this
before deciding to put anything sensitive into Minder Memory.

## TL;DR

- **Your records, knowledge, constitution, registries** are text files
  in your git repo. They live on your machine (the working tree),
  plus the local `.git/` history, plus wherever you push the repo —
  typically a private GitHub repo you control. The engine itself
  never pushes; you do (via `/minder:mem:save` with your confirmation, or
  manually). Nothing else exfiltrates them — with one exception you
  create deliberately: a **role** you set up to reach an outside
  service will send it what its assignment says to send. See «Roles»
  below before you create one.
- **Your transcripts** — local files in `_sources/inbox/` after you
  drop them in. **The source you used to record** (Plaud, voice memos,
  etc.) had its own data path before the file got to your inbox; Minder Memory
  starts where the file lands.
- **Claude Code agent calls** — text content is sent to Anthropic's
  API per their terms. This is how the engine "thinks". You consent
  per-skill-invocation; nothing fires without your action or a
  scheduler you set up.
- **Git pushes** — only when you (or `/minder:mem:save`, with your
  confirmation) push to a remote. The default remote is `origin` (a
  private repo you control). The engine never auto-pushes to
  `upstream` (the public skeleton).

If you stop running skills and stop pushing, the system is fully
quiescent — markdown files on disk, nothing else.

## Data layers and where they live

| Layer | Location | Travels where |
|---|---|---|
| Voice recordings (raw audio) | Wherever your recorder stores them (Plaud cloud, iCloud, etc.) | Determined by your recorder, not by Minder Memory. |
| Transcripts (text) | `_sources/inbox/<source>/` and after processing `_sources/processed/<source>/` | Local. Read by `/minder:mem:process`, sent to Anthropic API as part of the prompt during processing. |
| Records | `_records/meetings/`, `_records/observations/` | Local. Sent to Anthropic API when skills read them (every `/minder:mem:*` call loads relevant records into context). |
| Knowledge notes | `0_constitution/`, `1_projects/`, `2_areas/`, `3_resources/`, `5_meta/mocs/` | Same — local, sent to Anthropic API when skills read them. |
| Registries | `3_resources/people/PEOPLE.md`, `1_projects/PROJECTS.md`, `_system/registries/` (tags, sources, concepts, domains, audiences) | Same. |
| Runtime state | `_system/state/` (logs, queues, candidate buffers, batches) | Same. |
| Role definitions, state and logs | `_system/roles/<id>/` | Same — local, sent to Anthropic API when the role runs. |
| Role credentials | `_system/state/secrets.enc.json` (encrypted) | **To your own git remote, encrypted.** The store is committed so a cloud scheduler can reach it; the key that opens it is never in git. Never in a prompt — a role loads the decrypted values in its own shell. See «Roles» below. |
| `audience_tags` and `is_sensitive` flags | Frontmatter on each note | Today: advisory. Engine respects them in views and lints. The slot exists; full automation around audience-aware redaction is on the roadmap, not active. |

## What "Anthropic API" means in practice

Every time you run `/minder:mem:process`, `/minder:mem:lint`, `/minder:mem:agent-lens`, or
any other skill, Claude Code:

1. Loads relevant Minder Memory files into the prompt context (records, system
   state, constitution, transcripts being processed).
2. Sends that prompt to Anthropic's API.
3. Receives the model's response.
4. Writes the response back to your filesystem (new records, updated
   indexes, etc.).

Anthropic's data handling for API calls is governed by their
[commercial terms](https://www.anthropic.com/legal/commercial-terms)
and their data retention policy. By default, prompts and completions
are not used for training. Confirm the current policy before sending
anything you would regret.

The engine does **not**:

- Send data to any other service (OpenAI, Google, etc.)
- Make outbound HTTP calls outside Anthropic's API and your configured
  git remote
- Run telemetry or analytics
- Have any "phone home" mechanism

The pipeline scripts under `zettelkasten/_system/scripts/` are pure
Python on your machine — no network calls.

## Git remotes — what gets pushed where

Your repo can have two remotes:

- **`origin`** — your private repo (the default. Created by
  `gh repo create my-minder-memory --private`).
- **`upstream`** — the public minder-memory skeleton (engine source).
  Read-only direction: you pull engine updates *from* upstream, never
  push to it.

`/minder:mem:save` and `/minder:mem:sync-data` push to `origin` only. They never
touch `upstream`. If you have private records you don't want on a
remote at all, simply don't push — the system works fully offline.

## Sensitivity flags — what they do today

Every note's frontmatter carries a privacy trio:

- `origin: personal | work | external`
- `audience_tags` — any subset of the canonical five (`family`,
  `friends`, `work`, `professional-network`, `world`) plus whatever you
  add to the Extensions table in
  `_system/registries/AUDIENCES.md`. Empty (the default) means
  owner-only.
- `is_sensitive: true | false`

Today these are **advisory metadata**:

- `/minder:mem:lint` audits for missing or inconsistent values.
- Graph and search presets (`docs/obsidian.md` / `integrations/obsidian/views.md`) include
  filters like "show only `is_sensitive: true`" for self-review.
- Hub views can be filtered by audience.

What they do **not** do today:

- Automatically redact sensitive content from prompts sent to Anthropic.
- Block git push of sensitive notes.
- Encrypt sensitive content at rest.

These are explicit design decisions to keep the slot in the schema
without overstating what the engine guarantees. If you want
encryption-at-rest for sensitive notes, use a tool outside Minder Memory
(e.g. git-crypt, age, or filesystem-level encryption) — they
compose cleanly with the markdown layout.

## Roles — the one path that can send your notes to a third party

Every other part of Minder Memory talks to exactly two places: Anthropic's API and your
own git remote. A **role** can talk to a third — but only one you set up
yourself, in the conversation where you created it. Worth knowing before you
create one:

- **You authorize the destination once, at creation.** `/minder:mem:role:add` captures
  the credential and proves the call works. After that the role runs unattended
  and does not ask again — that is the point of a standing job, and it is why
  the concierge makes you look at what the role will send.
- **A role reads your whole base.** Not a scoped slice: it can search records,
  notes, hubs and registries, including anything flagged `is_sensitive: true`.
  The flag is advisory here as everywhere else (see above) — it is instruction,
  not enforcement, and the role is told not to carry such content outward.
- **The credential is encrypted, and the encrypted form does travel.** It lives
  in `_system/state/secrets.enc.json`, which **is committed to your own remote** —
  each value encrypted separately, none of them readable without the key. The key
  is a single value you paste into your scheduler's environment config; it is
  never in git, never in a prompt body, and the engine never writes it anywhere.
  At run time the tick decrypts into a file **outside the repository**, the role
  reads it in its own shell, and it is deleted when the tick ends.

  **This is a deliberate step down from «the secret never leaves your machine»,
  and here is what you are trading for.** A gitignored file does not exist in a
  cloud clone, so with one a scheduled role could never reach an authenticated
  service unless your own computer was awake at the time. Committing the
  ciphertext is what makes an unattended outward role possible at all.

  What that costs you: if your private repository is ever exposed, the attacker
  holds the ciphertext. Not the key — but ciphertext plus time is not nothing.
  Lose the key and nothing is recoverable; you re-enter the credentials.

  This is an interim mechanism, chosen because the alternative was «this does not
  work at all», and it is replaced by a real secret manager when the platform
  becomes a service.
- **What a role writes inside its allowed paths is scanned** before that role's
  work is committed — file contents and filenames, plus the run line itself —
  for each credential in raw, base64, hex and percent-encoded form. A match is
  pulled out of the commit and you get a CLARIFICATION telling you to rotate.
  **Two limits, stated rather than glossed:** a credential shorter than 12
  characters is never scanned at all, because a short value would also match
  your own prose and the scan would destroy it; and encodings are unbounded
  (gzip, a value split across two files, spelled out in words), so the scan
  raises the cost of a leak — it does not make one impossible.
- **What the check does and does not hold against.** It holds against a role
  that makes a mistake, and against an injection in something the role read
  steering the role's work. It does **not** hold against a role attacking the
  check itself: a role has a shell, and a shell controls what `git status`
  prints and when. Three gaps are known and only partly closed — a write
  delayed until after the check, the unbounded encodings above, and changes to
  git's own configuration, which are reported rather than repaired.
- **What nothing can undo: an outward call already made.** A sent email is sent.
  The diff check protects your repository, not the outside world; a role that
  reaches outward is trusted at the moment you grant it.
- **To stop one:** `/minder:mem:role:edit` and pause it, or remove the `minder-mem-roles`
  schedule to stop all of them. Its accumulated state stays on disk either way.

## Multi-device

If you sync the repo across devices (laptop, phone, desktop) via git,
your data is wherever you push it:

- Push to `origin` on a private GitHub repo: GitHub holds an
  encrypted-at-rest copy.
- Push to a self-hosted gitea/forgejo: you control the server.
- iCloud / Working Copy / Termius for mobile: the file moves through
  Apple/the SSH layer per their respective policies.

The engine doesn't care which transport you use; it only sees a git
repo on disk.

## What to do if you put something you regret into Minder Memory

1. **Filesystem level:** delete the file, run `git rm` if committed.
   The git history still has it. Use `git filter-repo` or
   `git rebase -i` + force-push to remove from history (destructive;
   confirm carefully).
2. **In Anthropic's logs:** Anthropic retains API logs per their
   policy (currently 30 days for abuse monitoring, no training use
   on commercial accounts). You cannot delete from their logs; you
   can only stop sending more.
3. **In your records pipeline:** if `/minder:mem:process` already wrote a
   record citing the regrettable content, edit the record, run
   `/minder:mem:save`. The engine never auto-rewrites your edits.

## The cognitive-model lens — profiling from your reflections

Minder Memory ships a `cognitive-model` lens that is **on by default**. Every other Monday
it reads your own reflections (solo voice-notes, journal-style observations) and
proposes principles about how you think and want to be communicated with. It
touches your most private content and writes inferences about you into your repo
(see **Produces** below), so it is worth understanding — but it never changes
your constitution on its own: it only *proposes* to a review buffer you control,
and you promote nothing you do not approve. That gate is why it is safe to ship
active platform-wide.

- **Reads:** your `_records/observations/` (and meetings) — the same content
  every records-lens already sees. It does not reach outside your repo.
- **Produces:** dated lens outputs under `_system/agent-lens/cognitive-model/`
  and proposed candidates in `_system/state/principle-candidates.jsonl` —
  inferences about you, in plain text, in your repo.
- **Never promotes on its own.** A candidate becomes a constitution principle
  only through `/minder:mem:lint` F.5 + your review. Highly-confident candidates may
  append to the review buffer without a click (tunable in
  `insights-config.yaml`); medium / low always wait for you. Set the class to
  `never_auto` to click every one.
- **Travels with your repo.** Like all your data, these inference files sync to
  `origin` on `/minder:mem:save` and are sent to the Claude API when a skill reads
  them. `is_sensitive` is advisory only (see above) — it does not redact. If a
  derived inference feels too personal to live in your git history, delete the
  lens output + candidate line and run `/minder:mem:save`.
- **Turn it off:** set the lens row to `status: draft` in
  `_system/registries/AGENT_LENSES.md`. It stops immediately; existing outputs
  stay until you delete them. Note the opt-out is not durable across updates — a
  later `/minder:mem:update` re-applies the platform default of `active`, so re-set it
  after updating if you want it permanently off.

The guard against this becoming a profiler that flatters you is the
no-sycophancy rule (in `communication-baseline`, reinforced by
`advisory-baseline`'s requirement that the analysis stay even-handed about your
own arguments, and in your own constitution where you keep one): the lens is
instructed to model how you think, never to mine for what comforts you.

## The personal-data linter — what stops your data from shipping publicly

If you ever contribute an engine change upstream (or just run the release
tooling locally), `scripts/check_no_personal_data.py` scans everything
that would ship to the public skeleton for your own identifying data. It
does not rely on a hand-maintained list you'd have to remember to update:
it derives its patterns at scan time from your own `PEOPLE.md`,
`PROJECTS.md`, `SOUL.md` Identity section, and every constitution
axiom/principle/rule's title and statement — so a coworker added to
`PEOPLE.md` last week, or a new project in `PROJECTS.md`, is automatically
covered the next time the linter runs. Known-public terms (the engine's
own placeholder examples, product names like `Minder`/`Minder Memory`) are excluded
so the linter never flags its own depersonalized documentation. This
derivation is local-only — it reads your registries to build regex
patterns and never sends that data anywhere; the scan itself only runs
against files bound for the public skeleton, never your private notes.

It also reads the other way round, because names are not the only thing
that identifies you. A sentence lifted verbatim out of one of your
recordings and left in a prompt as a worked example carries no name to
match — and is often more identifying than one. So every quoted span in a
shipped file is tested for exact occurrence in your `_records/` and
`_sources/`, and a match fails the run. Files the engine legitimately
ships your verbatim principles in (the starter pack, the constitution
protocol's own example) stay exempt, exactly as they are for the pattern
layer. Anything that ships is subtracted from the haystack first, so
shipped text is never matched against itself.

This is a **backstop, not a boundary**, and the difference matters to
you: it catches a sentence someone pasted in between quotation marks,
and it misses one that was paraphrased, or written in without quotes.
The rule that engine examples are written rather than quoted is on the
author; the check only catches the careless half.

The whole scan is local, and the report is built so that failing does
not itself disclose anything: it names the shipped file, its line, and
a digest of the matched span — not the record's path, because a record
filename is built from its own subject. The real path is printed only
when you ask for it with `--reveal-corpus-paths`, on your own machine.

If your own recording happens to contain, word for word, an example the
engine ships, you can neither edit engine text nor delete your record.
List it in `shipped-quote-exceptions.txt` — instance-local, never
shipped, one line of shipped-path, span digest and a required reason.
Keying on the digest means the exception stops applying the moment that
engine line changes, so it cannot quietly outlive what it excused.

## Engine boundaries — what the engine is not allowed to do

Codified in `zettelkasten/_system/docs/ENGINE_DOCTRINE.md` (auto-loaded
into every Claude Code session). The contract:

- Never auto-create a knowledge profile in `3_resources/people/<id>.md`
  without surfacing the threshold-crossing → CLARIFICATION first.
- Never auto-promote a principle candidate to constitution. Owner gates.
- Never overwrite owner edits to SOUL.md / PEOPLE.md / PROJECTS.md /
  hub files. Re-runs add or surface, never rewrite.
- Never close an open thread silently.
- Never delete files from `_sources/`.

These hold across all skills. If you observe a violation, that's a bug.

## Questions

If you're considering putting something specifically sensitive into
Minder Memory and want to think it through, the right question is **"would I be
OK with this text appearing in a Claude API call?"** — that is the
boundary that matters.

For everything that's not "I would not want this in any API call ever"
— records of work, meetings, decisions, ideas, principles — the
system is designed for it.
