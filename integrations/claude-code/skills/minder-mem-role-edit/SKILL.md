---
name: minder:mem:role:edit
description: >
  Change a standing role — what it does, when it wakes, where it may
  write, whether it is paused. Resolves a role from a free-text
  reference (display name, id, or a garbled speech-to-text version of
  either), shows what the role is today in plain language, takes the
  change, and proves the result valid before anything reaches the live
  file. Holds `.roles.lock` while writing, so an edit can never land in
  the middle of a running tick. Pausing and resuming a role is this
  same skill.
disable-model-invocation: false
---

# /minder:mem:role:edit — Change a standing role

A role is a scheduled job the owner described once, in their own words.
This skill changes it. The owner talks about what the role should do
differently; the skill works out which part of the role that is, and
never says the mechanical word out loud.

Speak the owner's language throughout — the role's own instructions are
written in it, and the owner reads them back here.

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md`.

## When to invoke

- The owner wants a role to do something different, more, or less.
- A role should stop for a while, or start again.
- A role has been failing and its instructions need fixing.

Do **not** invoke for: creating a role (`/minder:mem:role:add`), asking what a
role found (`/minder:mem:role:ask`), seeing what roles exist
(`/minder:mem:role:list`), or running a role now — execution belongs to the
tick, `/minder:mem:roles`.

## Arguments

`$ARGUMENTS` — a free-text reference to the role, optionally followed by
what to change. Both halves are optional; ask for whichever is missing.

- `--pause` / `--resume` — shortcut for the one change that has a name.

## Resolving which role

**This section is the single home of the rule. `/minder:mem:role:list` and
`/minder:mem:role:ask` resolve by it and do not restate it.**

1. Get the roster. **The base directory's name is the owner's choice, not
   a constant** — the write shorthand expands from it, and assuming a name
   makes a renamed base report no roles at all. Derive it once, from the
   repository root, and reuse `$BASE` everywhere below:

   ```bash
   REPO="$(git rev-parse --show-toplevel)"; BASE=""; export PYTHONIOENCODING=utf-8
   for d in "$REPO"/*/; do [ -f "$d/_system/scripts/roles_run.py" ] || continue; BASE="$(python3 "$d/_system/scripts/roles_run.py" base --repo "$REPO")"; break; done
   python3 "$BASE/_system/scripts/roles_run.py" due --base "$BASE" --repo "$REPO"
   ```

   **This is the one derivation, and it is the same one `/minder:mem:roles` uses.**
   The loop only locates a copy of the CLI; `roles_run.py base` is what
   decides, so «which directory is the base» is answered in one place with
   one message. Two things about the surrounding shell are load-bearing:
   `git rev-parse` means it works from any subdirectory, not only the
   repository root (a `ls -d */...` from inside the base matches nothing and
   yields an EMPTY `$BASE`, after which every command silently runs against
   `/_system/scripts/roles_run.py`); and the absolute `$REPO` is what the CLI
   is given, so nothing depends on the working directory.

   Zero bases and two bases are both loud: the CLI prints the reason on
   stderr and exits non-zero, leaving `$BASE` empty. `BASE` empty → repeat
   that reason to the owner and stop. Do not proceed with a guessed path.

   One JSON row per role: `id`, `name`, `due`, `reason`, `status`.
   Nothing else enumerates roles — never glob the roles directory to
   build a list.

2. Match the reference against `id` and `name`:

   | Outcome | What to do |
   |---|---|
   | Exact `id`, or `name` matching apart from case | Resolved. Proceed without a question. |
   | One plausible near-match | Name it back in one line and wait for a yes. |
   | Several plausible | List them by `name` only and ask which. |
   | None | Say so, show what does exist, offer `/minder:mem:role:add`. |

3. **Match loosely, confirm strictly.** A reference arrives spoken, so
   it may be a mangled display name — a dropped ending, words in
   another order, one word transliterated into another script, a
   homophone. Compare by sound and by content words, not by string
   equality. Loose comparison is for *finding* a candidate; the
   confirmation is what makes it right. Editing the wrong role silently
   is far worse than one extra question, and no reference is ever
   resolved by guessing.

4. Resolution yields exactly one role id, and everything else follows
   from it. A role is one directory, `zettelkasten/_system/roles/{id}/`:
   `role.md` is the whole role, `state/` holds the files it keeps for
   itself, `log.jsonl` has one line per run.

5. A role whose `role.md` is malformed still appears in the roster, with
   `status: "unknown"` and the parser's complaint as its `reason`. It
   resolves like any other — it is the role most likely to need editing.

## Step 1 — Say what it is today

Read the role's `role.md` and say it back in four to six plain lines:

- **what it does** — its assignment, condensed, in the owner's own words;
- **when it wakes** — as a sentence («every morning at seven», «Mondays»),
  never the schedule string;
- **what it may change** — as places («the notes it keeps for itself»,
  «new notes into your inbox», «the file X»), never a path;
- **where it reaches** — the service by name, never the credential;
- **running or paused**, and when it last ran — the last line of
  `log.jsonl`, or «never yet».

Never print frontmatter, a path, or the raw file. The owner is being
reminded what their role does, not shown a config.

## Step 2 — Take the change

One question at a time. The owner describes the behaviour they want;
you decide what that is. Illustrative, not a lookup table:

| The owner says | What actually changes |
|---|---|
| «it should also…», «stop doing X» | the assignment prose |
| «check it in the mornings», «once a week» | the wake-up schedule |
| «let it keep a list of…» | where it may write, plus the closing instruction that fills it |
| «it should weigh this against my principles» | the principles flag |
| «pause it», «start it again» | its status |
| «it hangs and never finishes» | its time limit |
| «it needs a key for X» | its declared credentials, plus the credential in the secrets store |

Rewrite prose the way the owner would have written it: instructions to
the role, second person, their register. Keep the three-section shape
the role already has — the check that decides whether a run is worth
doing, the work, the close.

Push back when the change would make the role weaker: a check that can
never be false makes it fire every time and find nothing; a role that
may write nowhere leaves nothing behind but a log line.

## Step 3 — Prove it valid, then write

The live file is never the place where an invalid role is discovered.

1. Assemble a scratch copy: a temporary directory holding
   `$TMP/$(basename "$BASE")/_system/roles/{id}/role.md`, plus the credential
   store copied in beside it. The **basename**, not `$BASE` — `$BASE` is
   absolute, and `$TMP/$BASE` concatenates two absolute paths into a nonsense
   tree. The name itself has to be kept, because the `writes` shorthand
   expands from it and a differently-named copy would validate a different
   role.

   **The store has to come along, and it is the encrypted one** — `validate`
   resolves a declared credential against the store under the base it was
   given, so a scratch base without it reports every declared name as having
   no value. That finding would be about the scratch tree, not about the
   edit, and it blocks every credentialed role from ever being edited. The
   copy is the committed ciphertext; no key is needed to check that a name is
   present, and nothing is decrypted here.

2. Validate the scratch copy — deriving `$BASE` in the same call, per the
   prelude:

   ```bash
   REPO="$(git rev-parse --show-toplevel)"; BASE=""; export PYTHONIOENCODING=utf-8
   for d in "$REPO"/*/; do [ -f "$d/_system/scripts/roles_run.py" ] || continue; BASE="$(python3 "$d/_system/scripts/roles_run.py" base --repo "$REPO")"; break; done
   NAME="$(basename "$BASE")"
   mkdir -p "$TMP/$NAME/_system/state"
   [ -f "$BASE/_system/state/secrets.enc.json" ] && \
       cp "$BASE/_system/state/secrets.enc.json" "$TMP/$NAME/_system/state/"
   python3 "$BASE/_system/scripts/roles_run.py" validate \
       --base "$TMP/$NAME" --repo "$TMP" --role {id}
   ```

3. `"ok": false` → the live file stays untouched. Translate each
   `findings` entry into plain language, fix it with the owner, and
   validate again. Never hand the owner the raw finding and never write
   past one. A credential the owner just named is a finding until its
   value is actually in the secrets store — the name alone is not enough.

   **One finding is about this shell, not about the role:** the entry whose
   `role` is `null` and which names `MINDER_MEMORY_ROLES_KEY`. It says the key is not
   in this conversation's environment, so no value could be decrypted and
   measured. Carry the key in the same call to clear it —
   `MINDER_MEMORY_ROLES_KEY='<the key>' python3 … validate …`, in one Bash call,
   since shell state does not persist between them. If the owner does not
   have it to hand, say plainly which check did not run and do not read it
   as a defect in their edit; every finding that names the role itself is
   still a blocker.

4. `"notes"` are not refusals; they name a shape that only works under a
   condition the engine cannot check. Say each one plainly **before**
   writing. The one that matters: a schedule carrying a time of day only
   ever runs if a scheduler tick fires at or after that hour, and the
   owner is the only one who knows when theirs runs.

5. `"ok": true` → take `.roles.lock` (see below), write the live
   `role.md`, release the lock, then run `validate` once more against the
   real base as confirmation.

Report the change in a line or two, in the same plain language as
Step 1, and remind the owner that saving is `/minder:mem:save`.

## Pausing and resuming

Lifecycle is this same path — one status change, validated and written
like any other edit. A paused role stays in the roster, reports
`due: false` with `status is paused` as its reason, and keeps its state
and its log untouched. Resuming does not catch up on wake-ups missed
while it slept: a missed anchor waits for the next one.

Retiring a role for good has no verb. Pausing is the reversible form;
deleting the role's directory by hand also destroys its memory and its
history, so it is the owner's deliberate act, not this skill's.

## Rotating or replacing a credential

«Токен протух», «я его перевыпустил», «пусть ходит под другим аккаунтом» — all
the same operation, and the only one in this skill that writes outside
`role.md`. The store is encrypted, so there is no file the owner can open and
edit; this path is the only way a value changes.

1. **The key has to be there.** `MINDER_MEMORY_ROLES_KEY` unset means the store cannot be
   opened and a write would be impossible, not merely refused. Say so plainly —
   the key lives in the scheduler routine's environment, and this conversation
   needs it in the shell too. Do not offer to generate a new one: a fresh key
   does not open the existing store, and writing with it would orphan every
   credential already in there.
2. **Take the value the way it was first taken** — ask in the owner's terms, hold
   it in the session, never echo it back, never read the store back to check.
   Confirm the write by the NAME being present, never by its value.
3. **Write the one name**, through `roles_secrets.store_secret`, which re-encrypts
   that value alone and leaves every other ciphertext byte-identical:

   ```bash
   REPO="$(git rev-parse --show-toplevel)"; BASE=""; export PYTHONIOENCODING=utf-8
   for d in "$REPO"/*/; do [ -f "$d/_system/scripts/roles_run.py" ] || continue; BASE="$(python3 "$d/_system/scripts/roles_run.py" base --repo "$REPO")"; break; done
   MINDER_MEMORY_ROLES_KEY='<the key>' python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import roles_secrets, pathlib; \
       roles_secrets.store_secret(pathlib.Path(sys.argv[2]), sys.argv[3], sys.stdin.read().rstrip("\n"))' \
       "$BASE/_system/scripts" "$BASE/_system/state/secrets.enc.json" NOTION_TOKEN <<'SECRET'
   <the value the owner pasted>
   SECRET
   ```

   **The key rides on this same call.** Shell state does not persist between
   tool calls, so a key exported earlier is not here; without it
   `store_secret` refuses and nothing is written. It goes on the command
   line rather than into a file — a key sitting in plaintext beside the store
   it opens is the one place it must never be.

   Feed the value on stdin, with a quoted heredoc so the shell expands
   nothing inside it. Never as an argument — arguments are visible in the
   process list to every other process on the machine, and they land in shell
   history. A value containing a newline is refused here rather than at
   render time: it would split into a second line that parses as another
   credential.
4. **A rename is two changes, not one.** If the declared name changes as well,
   the new name goes into the store *and* into the role's `secrets:` through the
   ordinary validated write above. The old name is not removed automatically:
   another role may declare it, and the store is shared.
5. **Re-validate, then prove it.** `validate` only says the name resolves to a
   value. That a *working* credential is in there is a different claim, and the
   only thing that settles it is a real read-only call to the real service, made
   the way the role makes it. Without that, a rotation that quietly stored a
   typo looks identical to a rotation that worked, until the role fails at its
   next wake-up and reports it as an error every day after.

The store is owner data and this skill does not commit it — `/minder:mem:save` does,
with the rest.

## Locks

Read-only steps — the roster, reading `role.md`, the scratch validation
— need no lock.

Before writing the live file, create `"$BASE/_sources/.roles.lock"` — from the
derived base, never the literal name, or on a renamed base this skill and the
tick take DIFFERENT locks and an edit lands mid-tick
and release it in a `finally`. If it already exists, a tick is running:
abort and say so. The tick reads `role.md` while assembling each role's
prompt, so an edit landing mid-tick would hand a role half of one
version and half of another. A lock older than two hours is surfaced as
a warning, never silently deleted.

## What this skill does NOT do

- **Never runs the role.** Execution is the tick's, `/minder:mem:roles`.
- **Never commits.** `/minder:mem:save` does.
- **Never touches `state/` or `log.jsonl`.** The state is the role's own
  memory and the log belongs to the tick; editing either makes the role
  lie to its next run.
- **Never writes a credential value into `role.md`.** Credentials are
  declared by name; the value lives only in the secrets store.
- **Never creates a role** — that conversation is `/minder:mem:role:add`.

## Failure modes

| Symptom | Cause | What to do |
|---|---|---|
| The reference matches nothing | The role goes by a different display name, or the spoken one is badly mangled | Show what exists; offer `/minder:mem:role:add` |
| `validate` refuses the scratch copy | The edit broke the schedule, a write destination, or the schema | Fix with the owner and revalidate; the live file was never touched |
| `.roles.lock` present | A tick is mid-run | Wait for it; a role's own run finishes in minutes |
| `validate` refuses a credential just added | The declared name has no value — the store lacks the name, or does not exist yet | Put the value in the secrets store, then revalidate |
| The roster shows a role as `unknown` | Its `role.md` is malformed | Resolve it as usual and fix it here — that is what this skill is for |
