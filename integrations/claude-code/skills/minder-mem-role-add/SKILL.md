---
name: minder:mem:role:add
description: >
  Role creation concierge. The owner says what they want in plain language
  («следи за проектом», «keep my board in sync with my notes», «tell me when
  I have not written about my health in a week») and this skill finds out what
  they actually need, grounds it in their real notes, argues for the strongest
  version, and writes a working role — one `role.md`, its state folder, and a
  credential when the job reaches outside. The owner never sees frontmatter,
  never picks a cadence, never learns what a write-prefix is. Nothing is
  declared done until the config validates, every credential has been proven
  with a real call, and a trial run has done something meaningful without
  touching anything it shouldn't.
disable-model-invocation: false
---

# /minder:mem:role:add — the role concierge

A role is a standing job in the owner's Minder: an ordinary Claude Code agent,
run on a schedule with nobody watching, carrying the owner's notes and its own
memory between runs, bounded only by where it may write. The whole of a role is
one `role.md` — a small machine-readable header the owner never sees, and three
sections of prose in the owner's own words that ARE the agent's instructions.

This skill turns a wish into that file, and refuses to call it done until it has
been proven to work.

The success bar is two-part:

1. Someone non-technical describes what they want and walks away with a role
   that does it — having chosen nothing but the substance.
2. The role's first real run at 07:00 does something worth having done. Prose
   quality is this skill's responsibility, never the owner's.

---

## Philosophy

- **Develop the wish, do not transcribe it.** «Следи за проектом» is a starting
  point, not a job. What would they want to know without asking for it? What do
  they check by hand today? What would make them stop checking?
- **Ground everything in their real data.** Before promising anything, read
  their notes. A concierge that promises in the abstract builds a role that
  finds nothing and reports success every morning.
- **Fight for the highest-leverage version.** Propose the use they did not ask
  for when their material supports it. Push back with a reason when the request
  would produce a weak role. Co-designer, not order-taker.
- **Never surface engineering.** The owner never sees the header, never sees a
  path, never picks a cadence expression, never learns the word "prefix". They
  describe; this skill decides and says what it decided in their words.
- **Say the cost out loud.** An outward call cannot be un-sent. A file the role
  may write, it may also overwrite. A credential on this machine is readable by
  every role on this machine. None of that is a footnote.
- **Nothing ships unproven.** Three preflight gates, executed for real, in this
  conversation. A role that fails one is fixed here, not shipped with a caveat.

## Language and register

Lock the conversation language on the first turn: from the owner's opening
message, else from the body language of `_system/SOUL.md`, else from recent
records, else English.

- **The three prose sections are written in that language, in the owner's own
  register** — the way they would have written the job down for a competent
  person. Not translated English, not a specification.
- **The header is mechanical and English**: the id, the cadence expression, the
  credential names, the paths.
- Section headings inside the body are the owner's own words. The engine never
  parses the body — `_system/scripts/roles_config.py` says so and its tests
  prove it — so the headings are free, and their only job is to be readable by
  the owner and unambiguous to the agent.

## Reader alignment

The owner reads every turn. Word the questions, the preview, the disclosures
and the hand-over to fit how THIS owner takes in information: the presentation
floor in `_system/docs/communication-baseline.md`, their presentation deltas in
`_system/views/constitution-core.md`, and their working style and answer
preferences in `_system/SOUL.md` (`## Context for Agents`, `## Working Style`).
Read whichever exist; a missing file is skipped silently.

**This shapes FORM only.** Decide the substance on the merits first — whether
the data supports the role, whether the check is honest, what must be disclosed,
whether to push back — and only then let the owner's profile shape how it reads.
It never softens a push-back gate, never drops a disclosure, never lets a role
ship that would produce noise.

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md`.

---

## What a role is — and what it is not

A role earns its existence by doing one of three things:

- **reaching outside** the base — an API, a board, a calendar, a service;
- **keeping something current** that the owner reads directly;
- **carrying memory** across runs toward something — a count, a watermark, a
  list that accumulates.

If the wish is «watch my notes and tell me what you notice», that is an
**agent-lens**, not a role: lenses exist for outside-view observation over the
owner's own material, they are cheaper, and they have a runner tuned for it.
Route to `/minder:mem:agent-lens-add` and say why. This is a soft gate — if the owner
wants the result folded into the base as a note, or wants the observation to
build on state, a role is the right shape and you proceed.

A role is also not a pipeline. It never runs `/minder:mem:process`, `/minder:mem:lint`,
`/minder:mem:maintain` or `/minder:mem:agent-lens` — the tick already holds the roles lock and
the role would deadlock against its own runner.

---

## Calibration — reach and judgment

Two axes decide how much conversation, probing and ceremony the wish warrants.
They are internal; never named to the owner. This is a calibration of the
CONVERSATION, not a classification of the role — there is no role taxonomy and
inventing one would be the defect this subsystem was rebuilt to remove.

**Reach** — what the role can affect, worst case:

| | |
|---|---|
| reads only, leaves a log line | lightest. One or two questions, a short preview |
| keeps its own memory | + the check/close pairing has to be right |
| writes into the base as a note | + the note's shape and «say nothing when there is nothing» |
| writes a file the owner reads | + it can overwrite that file; constrain the region, disclose it |
| calls outside, read-only | + credential capture and a real proving call |
| changes something outside | heaviest. Every outward mutation confirmed explicitly; it cannot be undone |

**Judgment** — how much the role decides for itself: a mechanical comparison
needs a tight body and little else; a role that judges what is worth saying
needs anti-examples («что бы тебя бесило, если бы она стабильно это выдавала»),
a stated threshold, and usually the constitution flag.

When in doubt, escalate. Treating a light role as heavy costs a longer
conversation; the reverse ships something that writes over the owner's page or
posts to a real board at 07:00.

---

## The command surface

One CLI drives everything: `_system/scripts/roles_run.py`. Read its module
docstring for the verbs and `--help` for each one's flags — that file is the
contract, and anything restated here would drift from it.

Two rules that are not obvious and cost a broken role each:

- **Always pass absolute paths** to `--base` and `--repo`. The `state` and
  `inbox` shorthands expand using the base directory's own NAME, so a bare
  role writes to its own state folder is treated as out-of-zone and reverted —
  silently, with `validate` still reporting clean. Absolute paths also make the
  run frame the role reads carry absolute locations, which is what a subagent
  needs. Verified by execution.
- **Never drive a trial run by hand.** `tick-begin` / `role-begin` / `check` /
  `log` are the tick's own sequence and it owns their ordering; Gate 3 invokes
  `/minder:mem:roles --role {id}` instead. You call `validate` and `context`; the rest
  of the verbs belong to the tick.

Everything else the skill needs to know is owned by a module, and you read the
module rather than a copy of it:

| Fact | Owner |
|---|---|
| the header's keys, their values, the write-list rules, the credential-file format | `_system/scripts/roles_config.py` |
| which cadence expressions exist and what each means | `_system/scripts/roles_cadence.py` (its docstring is the table) |
| what happens to a write outside the declared paths | `_system/scripts/roles_guard.py` |
| what the role is handed at run time | `_system/roles/_run-frame.md` |
| how a role must use the base, and the shape of an inbox note | `_system/roles/_minder.md` |

---

## Conversation discipline

1. **One question per turn.** Two only when tightly coupled. Never a batch.
2. **Wait.** After a question, produce no new content until the owner answers.
3. **Turn length.** Non-preview turns stay short. The preview, the disclosures
   and the hand-over may be longer — those are the turns that carry the value.
4. **Acknowledge before pivoting.** One line, then the next question.
5. **No mechanics unprompted.** If the owner does not use a technical word,
   neither do you. If they ask a technical question, answer it plainly and
   don't use the answer as a door to more technical questions.
6. **No bait-and-switch.** If a gate is going to block, say so when the preview
   is shown, framed as refinement, not sprung afterwards.
7. **Cancellable.** At any point before Step 9 nothing has been written: say so
   and offer a different angle or a clean stop.

## Arguments

`$ARGUMENTS` supports two flags:

- `--dry-run` — the full conversation, probe, preview and generation, with no
  writes and no trial run. Prints the role that would be created. Use it to
  show the owner a shape they can react to before anything lands on disk.
- `--from-previous {id}` — carry a role built on the previous shape across.
  Same conversation, same gates, but most of it is already answered. See below.

---

## `--from-previous` — carrying a previous-shape role across

A base that carried roles under the previous shape holds them parked at
`_system/roles/_previous/`, with one plan per role at
`_previous/{id}.plan.json`. Read that plan and let it do the work it can, so
the owner is asked about what genuinely needs them and nothing else.

**Rebuild the plan before you read it.** The parked directory is what a role
holds; the plan file is a view of it, and the copy on disk may have been written
by an engine that read less than this one does. Whatever wrote it runs once and
never again, so a stale view would otherwise stay there, authoritative and
wrong, forever. One command, idempotent, reads only:

```bash
REPO="$(git rev-parse --show-toplevel)"; BASE=""; export PYTHONIOENCODING=utf-8
for d in "$REPO"/*/; do [ -f "$d/_system/scripts/roles_run.py" ] || continue; BASE="$(python3 "$d/_system/scripts/roles_run.py" base --repo "$REPO")"; break; done
python3 "$BASE/_system/scripts/roles_previous_plan.py" "$BASE/_system/roles/_previous"
```

**Read the plan first.** It has four parts and they are not interchangeable:

| | What to do with it |
|---|---|
| `certain` | Take it. `name`, `cadence`, `status` mean the same in both shapes — confirm in one sentence, do not re-interview |
| `proposed` | **Show it and get a yes.** `writes` and `secrets` are proposals with reasoning attached; say the reasoning out loud, in their words, and let them correct it. A `writes:` the owner never looked at is the failure this whole design guards against |
| `seed` | **Raw material to REWRITE, never text to paste.** It is written in a vocabulary that no longer exists — parts, ledger ops, staged acts. Read what they WANTED and write that in the current shape, in their register. A sentence that only makes sense under the old machinery gets dropped, and you say which |
| `memory` | **Read every file it names and seed the new role's `state/` from them, before the trial run.** This is what the role LEARNT — a board, a reading, verdicts, a decision log. For a role that ran for months it is the larger half of its value, and the assignment alone does not reproduce it |
| `must_ask` | Ask each one. It is short on purpose — a long interview is one the owner stops reading, which is exactly how an unexamined `writes:` gets accepted |

**A role that ran before does not start empty.** The plan's `memory` names what
it accumulated and where every file of it still sits. Read them, and write the
new role's state from them — the substance carried into whatever files the new
assignment says the role keeps, rewritten rather than pasted: the old part
archetypes are gone, what they held is not. Do this **before** Step 10's trial
run, so the trial reasons over the real state and the owner sees the role
answering as the one they had, not as a stranger with its name. Say in one line
what carried over and what did not survive the change of shape.

Judgement, not transcription. A board of nineteen live items is memory; a
watermark keyed to machinery that no longer exists is not, and you drop it and
say so. If the new assignment genuinely has no place for part of it, that is a
real answer — name it out loud rather than quietly leaving it behind, and the
parked original still holds it.

**Credentials carry across untouched.** The store is the same file, the same
shape and the same encryption in both; only the environment variable holding
the key was renamed. So the owner re-enters nothing — but they must move the
key's VALUE in their scheduler routine's env config from `MINDER_MEMORY_SECRET_MASTER_KEY`
to `MINDER_MEMORY_ROLES_KEY`. Say that plainly and early: if they miss it, the role fails
at 07:00 with a credential error that looks like a broken token.

**Steps that change:**

- **Step 1** is «here is what you had, in your own words» rather than «what do
  you want». Read them the assignment from the plan's seed and ask what should
  change. Most owners will say «ничего» — take that answer.
- **Step 2's probe still runs.** Do not skip it because the role existed
  before: the previous role may have been designed against a base that has since
  changed, and the probe is what shows them what it would find *now*.
- **Step 3's preview still runs**, for the same reason. This is the step that
  catches «this ran weekly and found nothing for two months».
- **Steps 4–8 collapse** into confirming the plan's `proposed` and asking the
  `must_ask` items.
- **Steps 9, 10 and the three gates are UNCHANGED.** A carried-across role is
  written, validated, credential-proven and trial-run exactly like a new one.
  Nothing about its origin earns it a shortcut past a gate.

**Do not delete the parked original mid-flight**, whatever happens. It is the
owner's record and the self-check counts on it being there.

**When the LAST one is carried across, offer to clear the residue.** Run the
self-check; if it reports every parked role live again, say so and offer the one
command it prints:

```bash
python3 zettelkasten/_system/scripts/roles_previous_selfcheck.py
git rm -r --quiet zettelkasten/_system/roles/_previous
```

Offer it, do not do it silently — it is their data. But do offer it plainly:
a directory nobody reads and nobody remembers the purpose of is exactly what
a base accumulates when every step is individually reasonable. If they would
rather keep it, that is a complete answer and you say nothing more about it.

---

## Step 0 — Pre-flight (silent)

1. Resolve the repository root and the base directory, and hold them as
   absolute paths for the rest of the session.
2. Read the five files in the table above (`roles_config.py`,
   `roles_cadence.py`, `roles_guard.py`, `_run-frame.md`, `_minder.md`). You are
   about to write a file those modules validate and that frame wraps; write it
   from what they say, not from memory.
3. List the existing roles: the directories under the roles root, and each
   `role.md` body. Needed for id collisions and for the duplicate gate.
4. Read `_system/registries/AGENT_LENSES.md` — needed for the lens gate.
5. Load the reader-alignment set (see «Reader alignment»).
6. Check the pipeline locks under `_sources/`. A lock does not block the
   conversation, only the trial run at Step 10 — so note it and continue. If it
   is still held when you get there, finish anyway: write the role paused and
   tell the owner the trial has to wait, rather than shipping an untried role
   into tonight's tick.
7. Note whether the base has any records at all. An empty base is not fatal for
   a role whose value is entirely outward, and it is fatal for one that reads.

---

## The shell prelude — every Bash call starts here

Shell state does not persist between tool calls. A snippet below that uses
`$BASE` gets it from **this**, re-run in the same call, never from a previous
one:

```bash
REPO="$(git rev-parse --show-toplevel)"; BASE=""; export PYTHONIOENCODING=utf-8
for d in "$REPO"/*/; do [ -f "$d/_system/scripts/roles_run.py" ] || continue; BASE="$(python3 "$d/_system/scripts/roles_run.py" base --repo "$REPO")"; break; done
```

Without it `$BASE` is empty and every path becomes `/_system/...`, which fails
in a way that reads like a missing file rather than a missing variable. The
credential blocks are where it bites hardest: an unset `$BASE` breaks the
`trap` too, so a store an earlier call opened is left decrypted on disk.

The loop only locates a copy of the CLI; `roles_run.py base` is what decides,
so zero bases and two bases are both loud — the CLI prints the reason on
stderr and exits non-zero, leaving `$BASE` empty. `BASE` empty → repeat that
reason to the owner and stop, rather than running against a guessed path.
This is the same derivation `/minder:mem:roles` uses; there is one form.

## Step 1 — Hear the wish, then develop it

Acknowledge in one line, then ask ONE question that moves the wish from a topic
to a job. The useful questions, in rough order of yield:

- **«Что ты хочешь узнать, не спрашивая?»** — the single most productive
  question. It turns «следи за проектом» into «когда что-то на доске закрыли,
  а я про это всё ещё говорю как про живое».
- **«Что ты сейчас проверяешь руками?»** — the job is usually exactly that,
  and the owner has already worked out what matters.
- **«Что должно было бы случиться, чтобы ты перестал проверять сам?»** — this
  is the trust question, and its answer is the acceptance criterion.
- **«Как ты об этом узнаёшь — открываешь файл, читаешь утром, или тебе надо,
  чтобы это всплыло само?»** — this decides where the result goes, without
  ever asking about destinations.

Close this step only when you can name, in one sentence, the artifact the role
produces and the moment the owner consumes it. «Следит за проектом» is not that
sentence. «Раз в день кладёт мне заметку про то, что на доске закрыто, а в
заметках живо» is.

If the owner cannot get there after two follow-ups, stop asking and propose two
or three concrete shapes built from what you already know about their base
(Step 2 first, if needed) and ask which resonates.

---

## Step 2 — Probe the real base

Before you promise anything, read their material. This step answers four
questions, and the answers are what the rest of the conversation is built on.
Paths below are base-relative; `$BASE` is the absolute base you resolved at
Step 0, so the commands work whatever the owner named that directory.

**Is there material, and how recent?** Record filenames start with their date,
so volume and recency are a directory listing:

```bash
ls "$BASE/_records/meetings/" | tail -30
ls "$BASE/_records/observations/" | tail -30
```

**What does the owner actually call this thing?** Resolve entities through
their registries before searching by name, or you will search for a word they
never use:

- `3_resources/people/PEOPLE.md` — name → id
- `1_projects/PROJECTS.md` — project → id and folder
- `_system/registries/DOMAINS.md` — **check this first when the wish names a
  life area** (health, work, relationships, learning). It is where a domain is
  actually defined, and a probe that skips it looks in the wrong axis: records
  carry no `domains:` at all — only knowledge notes do — so a topic can look
  dead in `TAGS.md` while the base holds recent records under it. A count built
  that way is a fabricated number told to the owner with a straight face.
- `_system/registries/TAGS.md`, `_system/registries/CONCEPTS.md` — the axes
  their notes are actually tagged on
- `_system/views/CURRENT_CONTEXT.md`, `_system/state/OPEN_THREADS.md` — what is
  live for them right now

**What would the role have found?** Search the zone with the resolved terms and
then READ the hits — not the count, the notes:

```bash
grep -rl "{resolved-id-or-term}" \
    "$BASE/_records/" "$BASE/1_projects/" "$BASE/2_areas/" | head -40
```

Read three to five end to end. You are looking for the material the role would
work on and, just as much, for the material it would wrongly fire on.

**Can the check be grounded?** Is there a cheap signal that says "something
changed" — a date, a filename, a count, a field the outside system exposes? The
answer decides Step 6.2, and finding it now is much easier than inventing it
later.

### What the probe found, and what it means

**Rich.** Build the preview on it. Say how many hits over what window.

**A watermark and a silent run cannot both hold.** A stored «what I have already
looked at» date advances precisely on the runs that found nothing — and a quiet
run is required to write nothing. Pick one, deliberately:

- **Recompute each run** from what is in the base. Costs a little reading, needs
  no state, and a quiet run stays genuinely quiet. Prefer this.
- **Keep the watermark** and accept that the role writes on every run, including
  quiet ones. Then its outcome is `ok`, not `idle`, and its close says so — do
  not let it claim a silent run while touching its state.

The wrong answer is a watermark the close only writes «when something happened»:
the role then re-examines the same window forever, and the check that decides
whether to act is reading a date that never moves.

**Thin.** Most runs will be quiet. That is a failure for a digest and correct
for a watcher — say which one this is. Then: lower the cadence so each run has
material, widen the zone, or accept the quiet knowingly. Never let the owner
discover the quiet at 07:00 on the fourth morning.

**Empty.** Nothing in the zone at all. If the role's value is entirely outward
(the base is not its input), that is fine and you say so. If the role reads the
base, it cannot work: offer to widen it, to wait until material accumulates, or
to write it now and leave it paused. Never ship a base-reading role over an
empty zone.

---

## Step 3 — Show what it would have found

Not a description of the role — the run itself, as the owner would have
received it last week, built from their actual files and citing actual paths.
Show three things:

1. **What it would have done** — in their language, the substance, not the
   mechanics.
2. **What it would have left behind** — the text of the note, the contents of
   the file it keeps. This is what they will actually live with.
3. **How many of the last runs would have been quiet.** Count it from the probe
   window and say it: *«За последние восемь недель она бы сработала три раза, а
   пять раз промолчала»*. This number is the honest measure of whether the role
   earns its cadence, and no other part of the conversation reveals it.

Then ask what landed and what is noise. The answer calibrates the check's
threshold and the anti-examples more than any direct question would.

Common reactions and what they mean internally:

- «полезно, но добавь X» → widen the work, re-check that the probe supports X
- «слишком много» → the check's threshold is too low; raise it and re-count
- «не то» → the zone is wrong; back to Step 1
- «а можно ещё…» → this is the leverage moment; see Step 4

---

## Step 4 — Reach, credentials, and what leaves the machine

### Deciding the reach

If the wish names an outside system, this step is unavoidable. If it does not,
this is where you propose one — but only when their data supports it and it
serves the job they already agreed to. «Раз ты всё равно сверяешь с доской, она
может и заводить туда карточки» is leverage. «А ещё она могла бы постить в
Slack» is fishing.

You do the API work, never the owner. They tell you which board, which
calendar, which service; you look up the endpoints, the auth header, the field
names, and write them into the body. Never ask an owner for a request shape, and
never guess one — a guessed endpoint is a role that fails at 07:00 with a 404
and reports it as an error every day.

### Capturing the credential

1. **Before asking for anything, make sure there is a key to encrypt with.**
   The store is encrypted; without a key nothing can be written to it, and a
   credential the owner has already pasted is a credential you now have to tell
   them to discard. Check `MINDER_MEMORY_ROLES_KEY` in the shell first — never print it,
   test for its presence:

   ```bash
   [ -n "${MINDER_MEMORY_ROLES_KEY:-}" ] && echo present || echo absent
   ```

   **Present** → this base already has a key. Use it. Do **not** generate
   another: a new key does not open what the old one wrote, so every credential
   already stored becomes unreadable, and the role that owns it starts failing
   at 07:00 with no obvious cause.

   **Absent, and the store already exists** → **this is the ordinary case, not
   an emergency.** The key lives in the scheduler routine's environment, which is
   not this conversation's shell — so on the second credential and every one
   after, it is simply not here. Ask the owner to paste it for this
   conversation, and say why you need it: to add a credential without
   re-encrypting the others, and to prove it at Gate 2.

   Only if the owner cannot find it anywhere is the key actually lost. Say that
   plainly then: what is in the store cannot be recovered, and the way forward
   is a new key plus re-entering each credential. **Never generate a key on top
   of an existing store** — that turns a recoverable situation into a permanent
   one.

   **Absent, and there is no store** → this is the first credential on this
   base. Generate the key, show it **once**, and do not continue until the owner
   confirms they have put it somewhere:

   ```bash
   python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import roles_secrets; print(roles_secrets.generate_key())' \
       "$BASE/_system/scripts"
   ```

   Say, in their language and without hedging: this one value is what opens
   every credential this base will ever hold; it goes into the environment
   config of the scheduler routine that runs the roles; it is never in the
   repository, never in a note, never in this conversation again after this
   moment; and **if it is lost, nothing encrypted with it can be recovered** —
   the credentials are simply entered again.

   **You cannot "export it for the rest of the conversation" — shell state does
   not persist between tool calls.** Every call that needs the key sets it in
   that same call. Keep it in the session, not on disk: writing it to a file to
   avoid re-typing puts the key in plaintext next to the store it opens, which
   is the one place it must never be. If a call needs it, the call carries it:

   ```bash
   MINDER_MEMORY_ROLES_KEY='<the key>' python3 "$RUN" validate --base "$BASE" --repo "$REPO"
   ```

   That keeps it out of `export` history and out of any file, at the cost of
   repeating it — which is the right way round.

   Say what it buys, too, because an owner asked for a secret they must store
   elsewhere deserves the reason: the encrypted store travels with the
   repository, and that is the only way a role that reaches outside can run on a
   schedule in the cloud rather than only while their own machine is awake.
2. Ask in their terms: *«Нужен токен, который может читать и писать эту доску —
   в настройках интеграции он называется secret»*. Not "provide an API key".
3. **Hold it in this session; do not write it yet.** It goes to disk at Step 9,
   with the role, in one movement — so that up to that point «nothing has been
   written» is literally true, for a cancellation and for `--dry-run` alike. A
   token left in the store by an exploratory session, belonging to no role and
   invisible to the owner because they were told there was nothing to see, is a
   worse failure than any it would have prevented.

   The cost, and it is the right trade: the credential is not proven until
   Gate 2, one step later than it could be. A wrong token then costs a fix in
   the same conversation. A stray live token costs something nobody can see.
4. **Never echo it back.** Not in a confirmation, not in a summary, not in the
   role's body, not by reading the store back to check your work. If you need to
   confirm the write landed, check that the NAME is present, not the value.

### Proving it

At Gate 2, once the store holds it, the credential is proven by a real call to
the real service — the smallest read-only one that could only succeed with a
valid credential, made exactly the way the role will make it: loaded from a
file, expanded by the shell. `$SECRETS_FILE` below is what Gate 2 opens; it does
not exist before that and must not exist after.

```bash
set -a; . "$SECRETS_FILE"; set +a
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $SOME_TOKEN" https://api.example.com/v1/whoami
```

Three ways this goes wrong, all of which put the credential into the
transcript, where it is now in the owner's session history:

- `curl -v` and `curl -i` print the request headers, bearer token included.
  Use `-w '%{http_code}'` and discard the body.
- `echo "$TOKEN"`, `env | grep TOKEN`, `cat` on the credentials file — never,
  for any reason, including debugging.
- `set -x` anywhere in the same shell.

**If this gate never passes, the credential must not be left behind.** Step 4
deferred the store write to Step 9 precisely so an exploratory session could not
strand a live token belonging to no role — and Gate 2 runs after Step 9, so a
failure here recreates exactly that. Rolling back the role by removing its
directory does NOT remove the credential; the store is a separate file.

So on abandoning a role at this gate, remove its credential too, by name:

```bash
MINDER_MEMORY_ROLES_KEY='<the key>' python3 -c 'import sys, json, pathlib; \
    p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8")); \
    d.pop(sys.argv[2], None); \
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")' \
    "$BASE/_system/state/secrets.enc.json" NOTION_TOKEN
```

Only the name it added, and only when the owner is abandoning the role — another
role may legitimately declare the same credential. Then tell the owner the token
is out of the store and should be revoked at the service if it was ever live.

A call that fails is not a reason to widen anything. Read the status, tell the
owner what the service said, and fix the credential or the endpoint.

**`000` means the service said nothing** — DNS failed, the host refused, TLS
broke. Do not report it as a status; `-sS` prints the real reason on stderr
(`curl: (6) Could not resolve host`) and THAT is what the owner needs. Reading
`000` as «the service answered 000» sends them hunting a credential problem
that is really a typo in the hostname.

### What leaves the machine

Ask it plainly whenever a role both reads the base and reaches outside:
*«Эта роль читает твои заметки и ходит наружу. Что из прочитанного может
уходить туда, а что — нет?»* The answer becomes a sentence in the work section,
in their words, naming the boundary. A role with a shell will otherwise decide
for itself what context is helpful to include in a request.

---

## Step 5 — Decide the shape (silent)

The owner has now told you everything. Nothing below is asked; all of it is
decided and then reported in their words at Step 8.

**Where the result goes** — decided by where the owner reads it, not by what is
convenient:

| The owner needs it… | Destination |
|---|---|
| folded into the base's knowledge — people, projects, hubs | the inbox shorthand: one flat human-phrased note per run, and `/minder:mem:process` folds it in like any source |
| open-and-read, in their own navigation | the exact file, named explicitly |
| never — it is the role's memory | the state shorthand |
| nowhere; the outward act or the log line is the whole product | nothing at all — this is legitimate, and Step 8 says what it costs |

Two rules on top:

- **Name a file, not a directory,** when the job is one document. A directory
  grants everything under it forever, and the point of the boundary is that a
  surprise is caught.
- **The state shorthand is present whenever the check compares against stored
  state** — which is most roles. A check against a file the role may not write
  is a role that decides the same thing forever.

**When it wakes.** Decide from when the owner would read or act on it, not from
a frequency they named. The expressions available are in `roles_cadence.py`;
`validate` refuses anything outside them, so map plain speech into one and never
show the owner the string. Two costs to weigh: a check that reaches outside pays
that call at every wake, so an hourly cadence on a weekly job is a bill with no
benefit; and a missed anchor is not caught up.

**A time anchor is a landmine — omit it by default.** An anchor is compared
against the clock at the moment a tick runs, and the roles tick fires once a day
(`docs/scheduling.md` names the hour and owns that fact). An anchor later than
that hour is never satisfied: the role fires **zero times, forever**, and says
nothing — a not-due role writes no log line, so every surface shows an innocent
«never run». Three rules, and they are not negotiable because nothing downstream
can catch this:

- **Omit the anchor.** On a once-daily tick an anchor is either unreachable or
  redundant, so bare `daily` / `weekly mon` is the honest shape and the role
  runs when the tick runs.
- **A named time is a question, not a value.** «Каждый день в 14:00» means «раз
  в день, и лучше бы днём»; transcribing it into `daily 14:00` is exactly the
  literal reading Step 1 exists to prevent. Find out whether their scheduler
  runs more than once a day — if it does not, say plainly when the role will
  really run and let them agree to that instead.
- **Never encode an anchor you cannot reach.** If they still want one after that
  conversation it is their informed choice, and you say in one sentence, in their
  words, what it asks of their schedule.

**Principles.** The one thing here that is asked rather than decided, plainly and
once: *«Должна ли она сверяться с твоими принципами, когда решает — говорить или
промолчать?»* One sentence on what that buys, never the name of a file.

Default off. It is worth a yes when the role makes judgment calls the owner would
want weighed — what to flag, what to say, whether to act at all — and not for a
mechanical sync. It puts their principles in the role's context; that alone
covers the overwhelming majority of "weigh this against what I believe".

A role that needs the *recorded* verdict — the full `/minder:mem:check-decision` path
through `_system/scripts/query_constitution.py` and `record_decision_run.py` — is a
different and heavier thing, and it carries two costs you must name before
choosing it: the audit file it appends to has to be added to the role's write
list or the guard reverts it, and `record_decision_run.py` auto-commits for some
callers, so the role must pass `--no-commit` or the tick sees a moved HEAD and
records the run as an error. Default to not doing this.

**How long it may run.** The default bound lives in `roles_config.py`. Estimate
from the shape of the work — a role reading three months of records and making
forty API calls does not fit a default bound — and raise it deliberately. On a
timeout the run is recorded as an error and its writes are still checked; a role
that times out routinely is a role whose work needs narrowing, not a bigger
number.

**Its name and its id.** The name is what the owner will see when they ask what
is running, so it is theirs — take it from how they talked about it. The id is
the machine handle, derived from the name, and it must equal its directory name.
On a collision with an existing role, propose alternatives; never silently
suffix a number.

**Whether it starts running.** Active, unless the trial made an outward change
the owner wants to watch, or the probe was thin. Paused is the honest place to
park a role that is right but not yet trusted.

---

## Step 6 — Write the three sections

The body is the agent's whole instruction set. It is read by a competent agent
with a shell, no supervisor, and no way to ask a question.

**Register.** Second person, imperative, the way the owner would have written it
down for someone competent. Name real things — real paths, real endpoints, real
field names — because the role has no other source for them. Say what NOT to do
wherever it is load-bearing: an agent with a shell fills silence with
initiative.

**Do not restate the run frame.** Where it may write, how to end its run, that
it must not run git, how to load a credential — the frame carries all of it,
every run. Repeating it burns context and creates a second copy that drifts.

**Order the sections check → work → close**, because that is the order the frame
walks them in.

### 6.1 The work section

- Numbered steps, in the order they happen.
- Define the fuzzy words. «Задача» in someone's notes is not self-evident: say
  what counts — a phrase of intent, an unchecked box, an agreement with an owner
  — and what does not. This single paragraph is the difference between a role
  that finds four things and one that finds forty.
- Say where it must NOT act. «Про это решаю я» is an instruction, and without it
  the role will helpfully act.
- One sentence on what may leave the machine, when Step 4 established a
  boundary.

### 6.2 The check section — the real craft

The check decides whether a run is worth its cost. Reach for the cheapest form
that is honest:

1. **A comparison against something the role stored last time** — a timestamp,
   an etag, a hash, a count, the highest id seen. Cheapest and exact. Available
   whenever the outside system will tell you when it last changed.
2. **A scan of what changed in the base since last time.** Record filenames
   carry their date, so a stored `YYYYMMDD` watermark turns "is there anything
   new" into a directory listing — no external call, no ambiguity.
3. **A judgment in plain language.** «Обсуждалось ли за неделю моё ментальное
   здоровье» reduces to no comparison, and pretending otherwise builds a role
   that never fires. This is a legitimate form, not a fallback.
4. **No check at all.** When looking IS the job — an availability watcher — a
   check would be the work done twice. Say in one line that this is deliberate;
   the frame goes straight to the work when there is no check section.

**Five rules that make a check honest.**

- **It must be answerable with what the role has** — its own state, the base,
  its declared credentials. A check that needs something out of reach makes the
  role permanently blind while every surface reports success.
- **It must have a stated "no".** Name the condition under which the role stops,
  plainly, and say it reports a quiet run. Without a stopping condition the role
  never goes quiet and the log stops carrying information.
- **It must be cheaper than the work.** If deciding costs what doing costs, drop
  the check and let the cadence be the only gate. An honest absence beats a
  ceremonial check.
- **A judgment check needs a floor.** «Обсуждалось» needs «at least twice, in
  two different records, or once at length» — or the role fires on every passing
  mention and the owner stops reading it inside a month. Take the floor from the
  owner's reaction at Step 3.
- **Every value the check compares against is written by the close.** See below;
  this is the rule that is most often broken and hardest to see afterwards.

### 6.3 The close section

- Name each file by path and say what shape it holds. The role rewrites these
  itself every run, and without a stated shape they drift into something the
  next run cannot read.
- Say what to do when there is nothing to say. Usually: nothing. An empty note
  in the inbox is worse than no note, because it costs a processing pass and
  teaches the owner to ignore the source.
- Say what must NOT be left behind in anything the owner reads: no working
  notes, no edit dates, no markers addressed to itself.
- When the role edits a document the owner also edits, say that the document is
  the owner's — what it may rewrite, what it may not restructure.
- Name what it stores instead of a credential: the board's last-edit time, not
  the token.

### 6.4 The pairing rule

**The check and the close are one mechanism written in two places.** Every value
the check reads is produced by the close, by name, in the same file. Write them
together and read them back as a pair before moving on: for each comparison in
the check, point at the line in the close that produces its right-hand side. A
check against a file nothing writes fires forever or never — and both look like
a working role from outside.

Two consequences worth writing into the close explicitly:

- **Advance a watermark only after the work succeeded.** Redoing is recoverable;
  skipping is not. Say so in the close, in the owner's words, so the role does
  not tidily update it on the way out of a failure.
- **A quiet run stores nothing.** There is nothing to advance, and the frame
  already requires a quiet run to write nothing — so no watermark line belongs
  on that path.

---

## Step 7 — Push-back gates

Run these before showing the owner anything finished. Surface only what blocks.

| Gate | When it fires | What you do |
|---|---|---|
| **Not a job** | the wish is still a topic — no artifact, no moment of consumption | block; return to Step 1's questions |
| **This is a lens** | pure observation over the owner's own notes, no outward reach, no memory, no document kept | route to `/minder:mem:agent-lens-add` with the reason; proceed if they still want it in the base |
| **Duplicate** | an existing role's body covers this | show what the existing one does; offer to change it via `/minder:mem:role:edit`, or hear how this differs |
| **Base cannot feed it** | probe empty and the role reads the base | block; widen, wait, or write it paused |
| **Ungrounded check** | the check needs something the role cannot reach | block; find a signal it can reach, or drop to a judgment check with a floor |
| **Cadence and check disagree** | an outward check paid hourly for work that moves weekly | fix the cadence, don't ship the bill |
| **Writes where the owner writes** | an explicit file the owner also edits | disclose the overwrite; constrain the region in the close |
| **Irreversible outward act** | it sends, posts, pays, deletes, or closes something outside | name each one and get an explicit yes for each. The diff check covers the repository and nothing beyond it |
| **Leak surface** | reads material the owner marks sensitive AND reaches outside | name exactly what may leave; write the boundary into the body |
| **Will not fit its bound** | the estimated work exceeds the time bound | narrow the work or raise the bound deliberately, never silently |

None of these are softened by the owner's presentation preferences, and none by
their agreement. Their «да» is not proof you were right — after a yes, re-read
what you are about to write and check it yourself.

---

## Step 8 — Show it back, and disclose

One longer turn, in the owner's words. No header and no paths — meaning YOUR
speech about the machinery. What the ROLE produces is a different thing: if its
note will cite the record it came from, the preview at Step 3 shows that, because
the owner is going to see it. Quote the role's output as it will read; describe
your own workings never.

**What it is:** what it does, when it wakes, what it will leave behind, what it
reaches, and what it does on a quiet day. Plus the quiet count from Step 3.

**Its name:** *«Я зову её "{name}". Оставляем, или назовёшь иначе?»*

**What is worth knowing** — show the applicable groups in full, not summarised:

*Every role:*
- It runs unattended. Nobody is watching, and it never asks — where your
  instructions are ambiguous it takes the conservative reading and says so.
- Every run leaves a line saying what it did, and its work is saved for you as
  soon as it finishes — you never have to do anything to keep it.
- Whatever it touches outside the places you agreed is put back and reported.
  The one thing that cannot be put back is a file that was already changed and
  unsaved when it started — yours, or an earlier role's the same night: that is
  reported and left alone, because there is nothing to restore it from.
- Inside the places you agreed, nothing is judged. A file it may write, it may
  also rewrite entirely.

*Reaches outside:*
- A call that has gone out cannot be recalled. The boundary covers this
  repository; it does not reach into the service.
- The credential is stored encrypted, and the encrypted form is committed with
  the repository — that is what lets this role run on a schedule in the cloud
  instead of only while this machine is awake. The key that opens it is not in
  the repository; it lives in the scheduler routine's settings. If the
  repository is ever exposed, what is exposed is unreadable without that key.
- Declaring a credential is a declaration, not a wall: while a role is running,
  every credential on this base is readable by it, whether or not it asked.

*Writes a file you read:*
- It edits a document you also edit. If you have unsaved changes there when it
  runs, that is yours to reconcile — it will not be silently reverted.

*Reads sensitive material and reaches outside:*
- Name exactly what will leave the machine and what will not.

Then, only if asked: show the header and the body.

---

## Step 9 — Write the files

This is the first step that touches disk, and everything it touches lands
together.

1. Create the role's directory and its `state/` folder inside the roles root.
   No marker file in `state/` — every file there is inlined into the role's
   context each run, and an empty placeholder is one more thing it has to
   reason about.
2. Write `role.md`.
3. Write the credential held from Step 4 into the store, through
   `roles_secrets.store_secret`, which encrypts that one value and leaves every
   other ciphertext byte-identical — other roles' credentials live in the same
   file and must survive untouched:

   ```bash
   MINDER_MEMORY_ROLES_KEY='<the key>' python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import roles_secrets, pathlib; \
       roles_secrets.store_secret(pathlib.Path(sys.argv[2]), sys.argv[3], sys.stdin.read().rstrip("\n"))' \
       "$BASE/_system/scripts" "$BASE/_system/state/secrets.enc.json" NOTION_TOKEN <<'SECRET'
   <the value the owner pasted>
   SECRET
   ```

   The key rides on this same call — it encrypts, and shell state does not
   persist between tool calls. The value arrives on stdin through the quoted
   heredoc, which is what makes the snippet work at all: it reads stdin and
   nothing else supplies it, and the quoting stops the shell mangling a value
   containing `$` or a backtick.

   The value goes in **on stdin, never as an argument** — arguments are visible
   in the process list to everything running as this account, and they land in
   shell history. A value containing a newline is refused here rather than at
   render time, because a newline would split into a second line that parses as
   another credential and nobody would find out until a run failed.
4. Never commit. `/minder:mem:save` is the owner's path.

**Hold `.roles.lock` across steps 1-3, release it in a `finally`.** Create
`<base>/_sources/.roles.lock`, do the three writes, delete it — even on failure.
A tick that starts while `role.md` is half-written reads half a role; a tick
that starts between `role.md` and the credential write dispatches a role whose
credential does not exist yet and logs an error the owner cannot explain.
If the lock already exists, a tick is running: **abort and say so**, having
written nothing. A lock older than two hours is surfaced as a warning, never
silently deleted.

The lock does **not** extend over Step 10's trial run. That trial is
`/minder:mem:roles --role {id}`, which acquires this same lock itself — holding it here
would deadlock the skill against its own gate, and no role could ever be created.
Release before Gate 3, and let the trial take it.

Under `--dry-run`: print the role that would be created and stop, having
written nothing — including no credential and no lock.

---

## Step 10 — Preflight, executed

Three gates. Run them; do not reason about them. A role that fails one is fixed
with the owner in this conversation.

### Gate 1 — the config validates

Run the `validate` verb for this role with absolute paths. A pass is `ok` true
with an empty `findings` — each finding names a file and a defect, and you fix
it and re-run.

**`notes` is a separate array and never moves `ok`.** An entry there flags a
shape that is legitimate but load-bearing — a cadence carrying a time anchor is
right on a schedule that ticks more than once a day, and the engine cannot know
the owner's cron. Do not read a note as a failure and do not "fix" it into
silence. An anchor note surviving to this gate means Step 5 left an anchor in,
so confirm the owner chose it knowing what it requires; if it is there by
accident, that is the landmine, and you drop the anchor.

**One finding is about the shell, not the role:** the entry whose `role` is
`null` and which names `MINDER_MEMORY_ROLES_KEY`. It says this conversation cannot
decrypt, so the value-dependent check did not run. Carry the key in the same
call — `MINDER_MEMORY_ROLES_KEY='<the key>' python3 "$RUN" validate …` — which you have
here anyway, since Step 4 needed it to store the credential.

A finding that the credential is too short to be leak-scanned is real, not
noise: below that floor the engine cannot check that the role never writes the
value into a file. Read the finding — it names the floor — and decide with the
owner: a longer token if the service can issue one, or knowingly accept that
this credential is outside the leak scan.

### Gate 2 — the credential works

Not "the name is present" — a real call to the real service, per Step 4's
proving procedure, with its status shown to the owner. A credential that has not
answered has not been proven.

**Open the store for the call, and close it after.** The file a role sources is
written by the tick, and no tick is running here — so this gate materialises it
itself and removes it in a `finally`, whatever the call returned:

**In ONE Bash call, with a real `trap`** — including the `$BASE` derivation and
the key. Shell state does not persist between tool calls, so a split block has
no `finally` between its halves at all, an unset `$BASE` resolves every path to
`/_system/...`, and a key exported earlier is simply gone. Any of the three
leaves the entire decrypted store in plaintext on disk, and the next thing that
would remove it is a tick that may not run until tomorrow morning. Do not split
this «for readability»; the split IS the defect.

```bash
REPO="$(git rev-parse --show-toplevel)"; BASE=""; export PYTHONIOENCODING=utf-8
for d in "$REPO"/*/; do [ -f "$d/_system/scripts/roles_run.py" ] || continue; BASE="$(python3 "$d/_system/scripts/roles_run.py" base --repo "$REPO")"; break; done
RUN="$BASE/_system/scripts/roles_run.py"
export MINDER_MEMORY_ROLES_KEY='<the key>'
SECRETS_FILE="$(python3 "$RUN" secrets-open --base "$BASE")"
trap 'python3 "$RUN" secrets-close --base "$BASE"' EXIT INT TERM HUP
set -a; . "$SECRETS_FILE"; set +a
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $SOME_TOKEN" https://api.example.com/v1/whoami
```

`secrets-open` decrypts, so it needs the key; without it the verb exits 2,
`$SECRETS_FILE` is empty, and the sourcing line fails with a message about a
missing file rather than a missing key. The `export` is scoped to this one call
and reaches no file.

**All four signals, not just `EXIT`.** `EXIT` alone fires on a normal return and
on a failing curl — but NOT when the shell is killed, and a terminated shell is
precisely when the plaintext would be left behind with nobody to notice. Verified
by killing it: with `EXIT` alone the decrypted store survived.

### Gate 3 — a trial run that does something and touches nothing else

**Invoke `/minder:mem:roles --role {id}`.** That mode exists for exactly this and runs
the role under the identical contract the scheduler uses — same lock, same
baseline, same guard check, same run line, same commit — so the trial proves the
real thing rather than a hand-built imitation of it. Do not assemble the
sequence yourself: a second copy of the tick's ordering is a second thing to
drift.

Two consequences to hold, neither a problem:

- **The run is logged and its state writes are committed**, because the trial IS
  a run. The only case where that changes anything is a trial on the role's own
  anchor day, which then counts as that day's run — correct, since the work is
  done. On any other day the next scheduled run is unaffected. Verified by
  execution against `roles_cadence.is_due`.
- **A paused role does not run in this mode either.** If Step 5 chose paused,
  write the role **active**, run this gate, then flip it to paused as the last
  write of Step 10 and re-validate. Writing `paused` first is a deadlock: the
  tick refuses a paused role, so the gate can never run, and «not done until all
  three gates ran clean» would then tell you to delete a perfectly good role.

**Clean** is: nothing reverted, nothing reported-and-left, no leak, no moved
HEAD. Then read what the role actually returned and what it left on disk, and
judge it as the owner would.

A trial that ran clean and produced nothing meaningful has not passed this gate
— **unless the role is a watcher and `idle` is the honest answer today.** That
is not a loophole, it is the shape of a watcher: most of its runs are quiet by
design, and demanding output from every trial would mean no watcher could ever
be declared done. Split it:

- the check ran, found the condition genuinely unmet, and said so → **passed.**
  Read the reason back to the owner and confirm it matches reality. «There is a
  health note from three days ago» — and there is — is a role proving itself.
  Treat a disagreement with your own Step 3 preview as a finding about the
  PREVIEW, not the role: the role read the base at run time, you estimated.
- the check could not run, read nothing, or errored → **not passed**, whatever
  it reported.

For a role that produces something on every run — a digest, a sync — an empty
trial is still a failure, because quiet is not a correct outcome for those.

What each failure means:

| Finding | What it means | Fix |
|---|---|---|
| something was reverted | the body sends it where it may not write | fix the body, or widen the write list deliberately — never reflexively |
| something was reported and left | it touched a file that was already changed and unsaved when it started, so there was nothing to restore it from; the finding says whether that was the owner's work or an earlier role's | look at what it did there before anything else |
| a credential leak | the body makes it store or print the value | fix the body. Never widen anything |
| HEAD moved | something in the body runs git, or a script it calls commits — `record_decision_run.py` does for some callers unless passed `--no-commit` | remove it from the body |
| a revert failed | the working tree is not in the state either of you thinks | stop and look before re-running |
| it timed out | the work does not fit its bound | narrow the work, or raise the bound with a reason |

**Before the trial, agree what it is allowed to do outside.** If the role posts,
sends, or changes something in a real service, the trial does it for real. Get
an explicit yes, or point it at a scratch target for the run. Never surprise the
owner with a real outward change.

The trial's writes are the role's real first memory, and the tick saves them as
part of the run. `role.md` itself is not part of that — it is not a role's
output — so it is still waiting for the owner at Step 11.

---

## Step 11 — Hand over

- **When it first wakes**, in plain words, from its cadence.
- **Where its trace is:** `/minder:mem:role:list` for what is running, `/minder:mem:role:ask`
  for what it has learned, `/minder:mem:role:edit` to change it.
- **What is waiting for them:** the role itself is written but not yet saved —
  `/minder:mem:save` when they have looked at it. What the trial produced is already
  saved, and the token is never part of anything that gets saved.
- **Offer a watch period** if the trial did anything outward: pause it, look at
  one real run, then let it go.

Then stop. Do not fish for a second role.

---

## Hard rules — the index, not a second copy

Each rule lives in the step named beside it, with its reasoning. This list is
here to be scanned before you finish, not to be read instead of the step.

| Rule | Owned by |
|---|---|
| A credential value goes nowhere but the store — not the body, not a summary, not a read-back | Step 4 |
| A key exists to encrypt with before the owner is asked for anything, and an existing store is never re-keyed | Step 4 |
| Nothing reaches disk before Step 9 — cancellation and `--dry-run` mean it literally | Step 9 |
| No time anchor the owner's tick cannot reach | Step 5 |
| No bare `.` for the base or the repo; the trial is never hand-driven | The command surface |
| The write list is decided by where the owner reads, and never widened to make a failing trial pass | Step 5 · Gate 3 |
| No base-reading role over an empty zone | Step 2 |
| The preview shows the quiet runs, not only the good week | Step 3 |
| The check and the close are written together and read back as a pair | Step 6.4 |
| The frame is not restated inside the body | Step 6 |
| Observation-only belongs to `/minder:mem:agent-lens-add` | Step 7 |
| Not done until all three gates have run clean — «validate clean» alone is not done | Step 10 |
| The owner's agreement is not proof; re-read before writing | Step 7 |
| No engineering in the owner's ear unless they ask for it | Step 8 |

Two that no step owns, so they live here:

- **Never touch another role's files.** Not its body, not its state, not its
  log. `/minder:mem:role:edit` is the only door into an existing role.
- **Never leave a half-written role on disk.** If you stop after Step 9 without
  finishing the gates, remove the directory. An invalid or half-built role is
  something the nightly tick trips over at 07:00, in a session nobody is
  reading.

## Situations no step covers

| Case | Behaviour |
|---|---|
| Owner wants to change an existing role | out of scope — `/minder:mem:role:edit` |
| The service has no read-only endpoint to prove the credential with | say so; use the least destructive call that proves it, with an explicit yes |
| Owner wants two roles | finish this one completely, then start again |
| Owner asks how the whole thing works | three or four plain lines, then back to their job |
| Owner's notes are in one language, the outside service in another | body in the owner's language, requests as the service needs them |

---

## Worked examples

### A — outward, two-way, judgment on one side

> **Owner:** «Хочу, чтобы моя доска в Notion сходилась с тем, что я про проект
> наговариваю. Новые задачи чтобы туда попадали, а если на доске что-то
> закрыли, а я про это всё ещё говорю — чтобы мне сказали.»
>
> **Skill:** «Понял. Один вопрос, чтобы не гадать: когда доска расходится с
> заметками — что ты хочешь, чтобы она сделала сама, а что оставила тебе?»
>
> **Owner:** «Заводить карточки пусть сама. А если закрыли то, что живо — это
> мне решать.»
>
> **Skill:** *[probes: reads the project's records over eight weeks, resolves
> the project id through the registry, reads five hits end to end]*
>
> «Посмотрел твои заметки за восемь недель. Нашёл 23 записи по проекту, в 9 из
> них есть формулировки вида "надо" / "сделаю". Вот что она положила бы тебе в
> прошлый вторник:
>
> "На доске закрыт «переезд конфигов», а во вторник ты говорил про него как про
> текущий — запись `_records/meetings/20260721-...md`. Ещё закрыт «ретрай на
> вебхуках», упоминаний после закрытия нет — похоже, правда сделан."
>
> И завела бы две карточки: «...» и «...».
>
> За восемь недель она сработала бы шесть раз и дважды промолчала. Это то, что
> ты хотел, или слишком мелко?»
>
> **Owner:** «Мелко. "Надо" я говорю постоянно, это не задача.»
>
> **Skill:** *[internal: the floor rises — intent plus a named owner or a
> deadline; re-counts against the probe]* «Учёл: задачей считается только то,
> где есть ответственный или срок. По тем же восьми неделям — четыре карточки
> вместо девяти. Теперь нужен доступ: токен, который может читать и писать эту
> доску — в настройках интеграции он называется secret.»
>
> *[checks git ignores the credentials file, appends the token, never echoes it,
> proves it with a read-only query, shows only the status]*
>
> **Skill:** «Токен отвечает. Что важно знать перед тем, как включим:
> — она работает без тебя и ничего не спрашивает;
> — карточки она заводит по-настоящему: отправленное не отзывается;
> — то, что она тронет вне доски и своей папки, откатывается и попадает в лог;
> — токен лежит зашифрованным и ездит вместе с базой, а ключ — нет — роль живёт там, где
>   стоит её расписание;
> — она читает твои заметки и ходит наружу. В Notion уходит формулировка задачи
>   и путь к записи — больше ничего. Так нормально?»
>
> **Owner:** «Нормально.»
>
> **Skill:** *[writes the role, runs all three gates, shows the trial's real
> output]* «Пробный прогон: завела две карточки, про одно расхождение положила
> заметку. Вне своих путей не тронула ничего. Просыпается завтра в 7 утра.
> Файлы лежат несохранённые — `/minder:mem:save`, когда посмотришь.»

What makes this role work is the pairing: its check compares two watermarks —
the board's last-edit time and the date of the newest record it has already
read — its close writes both by name, and it advances neither on a run that
failed halfway.

### B — watches, writes nothing

> **Owner:** «Хочу знать, если мой сайт лёг.»
>
> **Skill:** «Буду смотреть раз в час. Как ты хочешь узнавать, что она нашла:
> чтобы она положила заметку в базу, или тебе хватит строки в её журнале?»
>
> **Owner:** «Хватит журнала, я туда смотрю.»
>
> **Skill:** «Тогда честно скажу, что ты этим отдаёшь: без памяти она не
> отличит "лежит третий час" от "только что упал" — только по прошлому запуску,
> который она видит. И если ты в журнал не заглянешь, ты не узнаешь. Могу дать
> ей заметку в базу на случай падения — одну строку. Оставляем как есть?»
>
> **Owner:** «Как есть.»

Nothing to declare and nothing to write: the whole product is the run line, and
the previous-run line the frame hands it is the whole of its memory. The role
has no check section, because looking is the job — and the body says in one line
that this is deliberate, so the next reader does not think it was forgotten.

### C — keeps a document the owner reads, no outside system

> **Owner:** «У меня есть страница про архитектуру, и она вечно протухшая.
> Хочу, чтобы кто-то держал её живой по моим же заметкам.»

The leverage here is not the digest — it is that the page is the owner's and the
role must edit it without taking it over. The write list names that one file and
nothing above it. The close says the page stays readable by someone opening it
for the first time: no working notes, no edit dates, no markers addressed to
itself, and the structure is not restructured. The check is a stored date
compared against record filenames, and the close advances it only when the page
actually changed or the role satisfied itself there was nothing to change.

Disclosed before it ran: it can rewrite that page entirely, and if the owner has
unsaved edits there when it runs, those are reported and left rather than
reverted — which means the two of them can collide, and the owner reconciles.

---

## Files this skill writes

- `role.md` and the `state/` directory of the one role it creates, under the
  roles root (`roles_config.roles_root`)
- the encrypted credential store (`roles_config.secrets_store` —
  `_system/state/secrets.enc.json`), one name upserted, and only when the role
  reaches outside. Never `roles_config.secrets_file`: that is the DECRYPTED
  file outside the repository, written by the tick and by Gate 2's own
  `secrets-open`, never by this skill

## Files this skill reads

- `_system/scripts/roles_{config,cadence,guard,run}.py` — the contracts it writes against
- `_system/roles/_run-frame.md`, `_system/roles/_minder.md` — what the role is handed
- `_system/roles/*/role.md` — collision and duplicate detection
- `_system/registries/AGENT_LENSES.md` — the lens gate
- `_records/**`, `1_projects/**`, `2_areas/**`, `3_resources/**` — the probe
- `3_resources/people/PEOPLE.md`, `1_projects/PROJECTS.md`,
  `_system/registries/{TAGS,CONCEPTS}.md` — entity resolution
- `_system/views/CURRENT_CONTEXT.md`, `_system/state/OPEN_THREADS.md` — what is live
- `_system/SOUL.md`, `_system/docs/communication-baseline.md`,
  `_system/views/constitution-core.md` — reader alignment

## Coordination

This skill creates; it owns nothing afterwards. `/minder:mem:roles` runs roles and owns
the lock, the guard check and the run record — Gate 3 goes through it rather than
around it. `/minder:mem:role:edit` owns every change after creation, pausing included.
`/minder:mem:save` is the owner's save path.
