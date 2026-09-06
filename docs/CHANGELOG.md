# What's new

User-readable release notes. For the engineering log, see git history.

## 1.0.1 — The rename update, after watching someone take it

Five things that only show up when a real clone goes through the rename.

**The recovery no longer stalls at 0.69.0.** `--self-heal` restores `scripts/`
from upstream — but a restore that only copies leaves behind every file
upstream has since deleted, so `scripts/` differed from upstream forever and
the next run refused the tree as dirty. On exactly the clone the recovery
exists for. It now removes what upstream dropped as well as writing what it
ships, and the first run gets through.

**Only the remote the engine syncs from is repointed.** If your own repository
is named after the old skeleton — plenty are — the update used to point it at
the engine's, silently, and you would find out at your next push. Your remotes
keep their names and are listed as untouched.

**Leftovers from a Windows install are cleared.** An install without symlink
support writes real files where links were meant, so a stub of the old wiring
survived under `~/.claude` and shadowed the new one. Anything under an engine
name is now moved into the update's backup directory whatever its file type;
anything under a name that is not the engine's is never touched.

**Your own repository and folder names are yours.** A name like
`minder-ztn-<yours>` in your notes is your repository or folder, not the
product, and renaming it produced a path that does not exist. Those are left
whole and reported, so you can see why those lines still read the old way.

**The update checks itself.** Before it tells you anything, it re-derives what
the migrations should have done and proves it from your filesystem — version,
managed block, rules, commands, skills, dashboard, routines, credential store —
fixes what it can, and reports the one thing that needs you. And it says, up
front, that the rename rewrites files you have open and not yet saved, with
their previous text recoverable from git.

## 1.0.0 — The product is Minder Memory

The second memory has its own name inside the Minder ecosystem: **Minder
Memory**, short form **Minder Mem**. «ZTN» was the method it grew from, not the
product, and it stays only as something you can still say out loud — «найди в
ZTN» keeps working, because the hot rule lists the former name among its
aliases, permanently.

**What changes on your machine.** Every skill answers to `/minder:mem:<name>`
now — `/minder:mem:process`, `/minder:mem:update`, `/minder:mem:save` and the
rest; the `/ztn:*` names are gone. The update re-wires your Claude Code home by
itself (migration 031): the old links under `~/.claude` are removed, the new
rule `minder-memory.md` and the new skills are linked, the managed block in
`~/.claude/CLAUDE.md` is refreshed in place, and your `upstream` remote is
pointed at the renamed skeleton once the new address answers. Open a new
session afterwards so the re-wired rules load.

**What the update renames for you.** Migration 032 runs the engine's one
rename map over your whole clone — the registries and system files that were
seeded once, the vault config and dashboard (your edits travel with it), your
notes, records, hubs and the append-only state — so nothing in your base says
the old name any more. A note that quotes the former name as a name now reads
the new one — the rename is of the product wherever the product is named, not
of a token in engine files only — while `_sources/` keeps the wording exactly
as recorded: a transcript is evidence of what was said. The rename is
deterministic, idempotent, and one `git` step away from undone.

**Names you hold outside the repository — these are renamed, not read twice.**
The base-path variable is `MINDER_MEMORY_BASE` and the credential-store key is
`MINDER_MEMORY_ROLES_KEY`; the former `ZTN_BASE`, `MINDER_ZTN_BASE` and
`ZTN_ROLES_KEY` are no longer read at all. Your scheduled routines hold the
prompt text and the environment they were given, so `/minder:mem:update` walks
the upgrade checklist (`docs/upgrade-1.0.0.md`) with you after the sync: it
renames the variable in each cloud routine, switches a pasted prompt body to
the current one, shows you the shell-profile and collector lines that name the
old form, and proves each item closed. Until the key is renamed, a role that
reaches an outside service cannot decrypt its credentials — that is why the
checklist runs first, not last.

**The manifest contract says one name.** Emitters write
`processor: minder:mem:<pipeline>`; the schema (`urn:minder-memory:manifest-schema:v2.3`)
accepts only that spelling, and migration 032 rewrites the batches and buffers
already on disk to it — the append-only files keep their order and every line,
only the name changes.

**The floor.** The migration chain now starts at 031; the migrations that
shaped a base between older releases and 0.69.0 are no longer part of the
engine. A clone below 0.69.0 updates to 0.69.0 first
(`scripts/sync_engine.sh --self-heal --branch release/0.69.0` — the self-heal
puts that release's own update machinery in place first), commits, then
updates to this release; the sync refuses the direct jump and prints the path.

**One defect fixed on the way.** The sync read the engine list from the clone's
OWN manifest, so a path that existed only in the new one was never fetched on
the update that introduced it — while the retirement step, reading the new
manifest, had already removed its predecessor. The sync now reads the manifest
it is about to apply.

## 0.69.0 — A tag can no longer name a project you never had, and a migration can no longer arrive untested

Two holes of the same shape: a rule that was written down and watched by
nothing.

**A tag naming an identity that does not exist was invisible to every check.**
The identity procedure reasons outward from what a registry declares — for each
project and person it knows, it asks where the identifier still appears. An
identifier the registry never declared has nothing to reason from, so it was
examined by nobody. `project/some-topic` could sit in a note for years while
every scan reported clean.

The scan now reads the other direction too: a tag whose namespace belongs to a
registry, naming something that registry never declared — neither live nor
retired — is residue. Only namespaces a registry claims are judged, so
`topic/`, `domain/` and the rest are untouched, and each namespace belongs to
exactly one registry, a collision being refused rather than quietly resolved.

Nothing is repaired automatically, because registering the identity, retagging
the note and dropping the tag are three different decisions and only you can
tell which applies. The ones your base already carries are listed in
`_system/state/identity-orphan-baseline.txt` so tonight's run does not stop for
drift that predates the check; each becomes a clarification. The list only
shrinks, and CI now refuses a commit that adds a row to it — a list that can be
appended to is not a baseline, it is a mute button.

On the authoring base it found ten, in thirteen notes: topics tagged as
projects, a person archived out of the registry while their tag stayed, and one
placeholder.

**Your own base is seeded on update, so tonight's run is unaffected.** The check
arrives with the gate armed, and on a base that predates it that would be a new
verdict about old data — tags that have sat in notes for a year failing a tick
that neither created them nor can resolve them. So the update runs the scan once
and writes what it finds into your baseline first; from that moment a NEW orphan
fails and the existing ones wait for you. If you already have a baseline it is
left exactly as it is: re-deriving it would re-admit every orphan you had
already resolved.

**A migration could ship with no test, and nothing anywhere said otherwise.**
Six of twenty-eight had one. The gap had grown by three across two releases,
because coverage was a habit rather than a rule, and a habit stops without any
artifact looking wrong.

This matters more for migrations than for ordinary code. One that FAILS is
recorded and retried on your next update. One that *succeeds at the wrong
thing* is marked applied and never runs again — not on your clone, not after a
corrected version ships. Only a test that actually executes the script can see
that case, so the new gate demands execution rather than a declaration: a test
class naming the migration, holding a real test, and calling a runner that
genuinely shells out. All three are read from the test's syntax tree, because a
declaration of coverage is trivial to write beside no test at all.

The twenty-two that predate the gate are listed with a reason and a date, and
that list is closed: its ceiling lives in the gate's own code, so it cannot be
raised by editing the list. Anything added from now on ships with a suite.

**And the identity contract now says what it actually enforces.** It named seven
kinds of identity and one procedure for all of them; two are enforced. The
others are not covered by silence — a concept rename rides the regenerated
census, a source has its deprecated section, a domain hub has the archive
contract, and a lens has nothing at all. Each is now named, including the
nothing.

## 0.68.0 — Your help docs stop freezing, and the engine stops quoting you

Two things that had been true since long before anyone noticed.

**The help docs in your vault were frozen at the day you installed.** The four
files under `5_meta/help/` — the guide, the view presets, the privacy note and
this changelog — are copies of engine documents. They were copied only when
missing, and nothing ever refreshed them: updates do not run the installer, and
the installer skipped anything already there. So every improvement to those
documents reached the repository and stopped at the vault door. Nothing
reported it, because a stale document looks exactly like a current one.

They are now treated as what they are: derived copies, re-rendered on every
seeder run and by `/ztn:update` after each checkout. Nothing to do — the next
update brings them level. On the authoring instance the changelog was 217 lines
behind and the privacy note 122, and one copy still carried a person's real
name where the engine source had used a placeholder for months.

If you deliberately edited one of those four in your vault, that edit is
overwritten from now on. They are engine documents; edit the source or keep
your note somewhere the engine does not regenerate.

**The personal-data gate now catches your own words, not just your names.** It
already derived patterns from your people, projects, identity and principles
and refused any shipped file containing them. It could not see a different
class: a sentence lifted verbatim out of one of your transcripts and left in a
prompt as a worked example. Those are the words that identify a person most
sharply, and there is no name in them to match.

The gate now reads the other way round — every quoted span in a shipped file is
tested against your own records and sources, and an exact match fails the run.
It found one: a lens prompt shipping a sentence about pay, quoted from a
recording made in April. Replaced with a synthetic example of the same shape.

The check reports the shipped file, the line, and the *path* of the record it
matched — never the surrounding text. A gate against leaking your words must
not print them into a log while reporting.

## 0.67.1 — Your ticks now record what they cost

Every scheduled tick writes one line to `_system/state/tick-telemetry.jsonl`
saying what it consumed: input, output, thinking, cache writes split by TTL,
cache reads, which models it used and how many messages each got, and — on a
roles tick — a breakdown naming each role with its own model tally. There is
nothing to set up. Your routines read their instructions from the repository
at run time, so the next tick after this update starts recording.

**It measures, it does not report.** A model cannot see its own consumption.
The only figure in its context is a remaining-budget counter that ignores
cache reads and sub-agents entirely, so a tick asked to state its own cost
would be guessing. Instead the tick reads the transcripts the runtime wrote
for it — its own, plus one per sub-agent it spawned — and adds up what is
actually there. On a real run, sub-agents accounted for six times the output
of the main session, so anything counting only the obvious half would have
reported a seventh of the truth and looked entirely plausible doing it.

**It keeps what explains the number, not just the number.** Each line also
carries why the cache was missed and how many tokens that cost, which tools
the tick ran and how often, why each response stopped, and the wall-clock
window it ran in. Those are the fields that turn "this tick was expensive"
into "this tick was expensive because the system prompt changed and 427k
tokens re-entered the cache". None of it survives the run: a cloud tick's
transcripts live in a sandbox that is destroyed minutes later, which is also
why the recording happens mid-tick and why a tick that went unmeasured cannot
be measured afterwards.

**It can never cost you a tick.** The recorder always exits successfully, even
when it finds nothing — a tick that threw away real work because its odometer
broke would be worse than having no odometer. The consequence is that it also
cannot fail loudly, so `/ztn:lint` now checks that every scheduled commit
carries a telemetry line and tells you when one does not. It ignores ticks
that ran before the recorder existed, so the first run does not open with a
wall of false findings, and it watches for the sub-agent transcripts moving
somewhere new — which would otherwise show up as your usage quietly dropping
rather than as an error.

**Both recorders now say which telemetry they are.** This engine writes two
audit substrates, and until now each was called simply "telemetry" — you had
to be told which file a script meant. The tick odometer is
`record_tick_telemetry.py` → `tick-telemetry.jsonl`; the check-decision
recorder is `record_decision_run.py` → `check-decision-runs.jsonl`, with its
lock renamed to match. Decision-run lines now carry `format_version` like
every other versioned record the engine writes, and the update backfills the
lines already on disk — inserting the field, changing no value and reordering
no key. The old module paths are declared retired, so the update removes them
instead of leaving a second copy of a one-home module behind.

**Ticks only.** Running `/ztn:process` or `/ztn:lint` by hand records nothing
and warns about nothing. The scheduled loop is the thing being measured.

Two limits worth knowing. This starts from today — there is no way to recover
what past ticks consumed, whether from the transcripts (gone with their
sandboxes) or from Anthropic (subscription usage is not itemised per token).
And it counts tokens, not money: a cost figure can be derived later from the
numbers and a price list, but nothing here is a bill.

## 0.66.0 — An empty constitution stops counting as a yes

0.65 made `/ztn:check-decision` useful before you have written anything.
Wiring that up surfaced something worse sitting underneath it, which this
release fixes.

**The skill had one word for two opposite situations.** «None of your
principles apply here» and «you have no principles» both came back as
`no-match`. To you reading the answer that difference is obvious. To the
skills downstream it was invisible — and one of them acts on it:
`/ztn:resolve-clarifications`, when it hits a decision it would otherwise have
queued for you, asks the constitution and promotes the item to auto-apply on
`no-match`, on the reasoning that your principles were consulted and did not
object. On a base whose constitution is still empty, that answer comes back for
*every* item. The queue would have applied itself, on the strength of
principles nobody had written yet. Its own rules already said an empty tree
must fail closed; that line was unreachable, because the verdict it needed
never existed.

It exists now. `no-basis` means nothing was loaded, so nothing could object,
and it holds the item in the queue where you will see it. `no-match` keeps its
old meaning — principles exist, none bear on this — and still promotes, because
there the constitution genuinely was consulted. During bulk processing
`no-basis` stays silent rather than raising one clarification per record, which
on a fresh base would bury you on the first run; the run shows up in your
monthly decision review instead.

**And both silences now come with an actual answer.** Neither verdict stops at
«nothing matched» any more. You get the read: who else has a stake in this and
how that bends what they are telling you, which of the criteria on the table
are yours and which arrived with someone else, what here is unrecoverable as
against merely expensive, and what would have to be true for the advice to be
wrong. The same applies when your principles *do* cover part of a decision but
miss an axis — a third party, a step with no way back — and that gap is where
the expensive mistakes live. Every time, it says which of the two you are
getting: your principle, or the shipped floor. Passing one off as the other
remains the one thing it must never do.

## 0.65.0 — The stance starts working on day one, and your own version of it grows by itself

0.64 gave every session a reasoning floor. This makes it reachable from a base
that has nothing in it yet, and makes your own departures from it accumulate
without you having to know that is what you are doing.

**`/ztn:check-decision` stops answering «nothing matched».** On a fresh base it
had exactly one thing to say — your constitution is empty, come back in a few
months. Technically true and useless: you asked about a real decision and got
told about your filing system. It now falls back to the shipped baseline and
gives you the actual read — who else has a stake and how that bends what they
say, where each criterion came from, what is unrecoverable here as against
merely expensive, and what would have to be true for the recommendation to be
wrong. It says which one it is giving you, every time. «No principle of yours
covers this, reading it against the baseline instead» is an honest answer; the
same paragraph passed off as your own principle would not be, and that remains
the one thing the skill must never do.

**And the capture hook now hears you decide.** It already knew to catch how you
like to be told things — that is what keeps your presentation principles alive
instead of frozen at whatever you wrote on day one. It was deaf to the other
half: the moment you throw out a criterion because it was the other side's, not
yours; the moment you throw out one of your *own* because it belonged to a
situation that has ended («that mattered on holiday, not in ordinary life»); the
moment you treat a conversation as a negotiation rather than a collaboration;
the moment you weigh time or a relationship against money and the money loses.
Those now land in your review buffer like anything else, and become your
principles when you approve them. The baseline is the floor everyone gets;
these are where you turn out to differ from it, collected while you work rather
than recalled later.

**One thing to look at if you took the starter pack.** Migration 027 checks
whether any starter axiom has been acting as a standing principle without you
ever adopting it — the defect 0.64.1 fixed in the shipped pack could not reach
a copy already in your constitution, because a migration is not allowed to edit
what is yours. If it finds one you get a clarification explaining it and two
ways out, and nothing is changed on your behalf. If you never took the pack,
you will not hear from it.

## 0.64.1 — The new rule actually reaches a fresh install, and starter axioms stop going hot uninvited

Two delivery holes and one older defect, found reviewing what 0.64.0 shipped.

**A brand-new base would not have heard of the advisory baseline.** The seed
`SOUL.md` tells you where your presentation tuning and your long-form recipe
live; it said nothing about the reasoning stance or the decision playbook, so
someone starting fresh got the rule loaded but never learned it was theirs to
shape. Both are named there now, and `/ztn:bootstrap` points at the decision
playbook where it already pointed at the long-form one.

**And `/ztn:update` would not have told you to finish the install.** Its
follow-up table watched the integration folder for changes that need
`install.sh` re-run, but a hot rule ships from `_system/docs/` — a path the
table did not cover. A migration wired this particular rule, but the next one
would have landed silently. The table covers that shape now, and says nothing
when a migration already did the work.

**Older, and the one worth knowing about: a starter axiom went hot the moment
you adopted the pack.** The starter axioms exist as drafts you edit into your
own voice, and their README is explicit that they do not auto-load into the
always-on core view — you opt one in by adding `claude-code` to its
`applies_to`. One of the six shipped with `claude-code` already there, so
adopting the pack put an unedited draft straight into every session. The other
five were held back only by accident: their `applies_to` values were not real
values at all (`code`, `work`, `architecture`, `hiring`), silently discarded by
anything reading them. All six now ship as the README always claimed.

## 0.64.0 — Your assistant gets a stance, not just a voice

Until now the engine told your assistant how to *present* an answer — lead with
the conclusion, no fluff, no flattery. It said nothing about how to *reach*
one. So the moment a decision involved somebody else with their own stake — an
agent, a vendor, a recruiter, a contractor — your assistant had no instruction
beyond being helpful, and helpful is exactly what an interested party's framing
exploits.

**There is now a second always-on rule: the advisory baseline.** It sits beside
the presentation one and states the thing that was implicit and therefore
unreliable: your assistant works for you. Not as a neutral referee weighing all
sides fairly — as your representative, maximising your benefit on a long
horizon, inside your own ethics. The partisanship is in the goal only. The
analysis stays even-handed, and that explicitly includes being even-handed
about *your* arguments: an argument does not become sound because you made it.

**The sharpest part is about your own criteria, not theirs.** When somebody
with a stake tells you what matters, the weapon is never the argument — it is
the list. Argue inside their list and you have already lost, however well you
argue. So the assistant now builds the criteria from your actual situation
first and maps outside claims onto that, never the reverse, and it tracks where
each criterion came from: yours, introduced by an interested party, or
inherited from a situation that no longer holds. Then it runs the same audit on
yours — against how you actually live most of the time, not against one vivid
week. The vivid case is always louder than the typical one, and that error
runs in the same direction every time.

**It also weighs the two things a pros-and-cons list flattens.** How much of an
outcome was chance rather than skill, so one result does not rewrite your model
of the world. And what cannot be bought back — money is recoverable, time and
optionality and relationships are not, and they weigh more than their number
suggests precisely because they quantify worse. Where two options look equal,
the one that is cheaper to undo wins.

**None of this makes your answers longer.** The sweep across empathy,
proportionality, risk and second-order effects runs inside; what surfaces is
only the part that changes the recommendation. A full sweep printed into every
reply is the boilerplate the presentation rule already exists to prevent.

**When something gets reworked, you now read the difference, not the whole
thing again.** Revisions, reviews, counter-proposals and updated plans open
with a verdict ledger — what was kept, what was refined, what was rejected and
why, what is newly proposed — each stated against the version you already read.
You paid the cognitive cost of version one; re-deriving it from a fresh full
text charges you twice for one change. Note the deliberate asymmetry: the
artifact itself is still built whole, as it should be now, never as a patch
layered on what was there. Built whole, reported as a difference.

**What you need to do:** nothing beyond the update. The two rules ship with the
engine, and a migration wires the new one into your `~/.claude` and tells you
if it could not. If you have never run `integrations/claude-code/install.sh` on
this machine, run it once — otherwise the rule sits in your base unread.

## 0.63.0 — Files this engine deleted finally leave your clone, and a proof stops being a claim

An update copies what the engine HAS. There is no way for it to say what the
engine no longer has — so removing a file upstream does nothing to your copy
unless the removal is declared. Forty-three deletions were never declared, and
the survivors have been sitting on every clone that ever received them.

**A removal that was declared in half is the one that actually hurts.** The
roles subsystem was replaced wholesale, and about half of it was marked for
removal. Six modules that were not marked import one that was. On a clone
carrying that generation, updating would have deleted the imported half and
kept the importers — turning a tree that was merely dead into one where the
test suite cannot even start collecting. All forty-five are declared now, so
the next update clears them.

**And the quiet version of that hole is now closed.** Every other check this
engine runs reasons about files it has — it scans them for leaks, for
portability, for seed shape. None of them can see a deletion, because the
absence of a file is not a file. There is now a check that compares the
engine's own history against what it declared: delete a shipped file without
declaring it and the release fails, whether or not you removed its manifest
line in the same commit. It is not a proof against every way a file can stop
shipping — rewriting history out from under it still hides one — but it closes
the ordinary way, which is the way this happened. On a truncated clone it
refuses outright instead of finding nothing and calling that clean.

**Retiring a name now leaves evidence, not testimony.** When you merge or
rename a project or a person, the change closes only against a scan proving no
mention of the old name survives. Until now that proof was a number written
into the record by the same run that did the work — a claim about itself,
indistinguishable afterwards from a fact. The scan now writes its own line as
a side effect of actually running, and the nightly check matches the record
against that line rather than against the number. A resolution that asserts a
scan which never happened is now visible.

**Three repairs stopped claiming a success they could not prove.** If a repair
could not tell which folder held your base, it guessed, announced that there
was nothing to do, and marked itself permanently done — so the thing it was
meant to fix survived and was never looked at again. One of them did the same
after a repair step actually failed, while printing that it would be retried.
They now say they could not tell, and are retried. Note the limit honestly: a
repair already recorded as done is never re-run, so on a clone that already
hit this, the fix arrives but does not reach backwards. What it protects is
every clone from here on.

**A lens that cannot have anything to read ships off.** The computer-usage
rhythm lens needs records from a collector that is not part of this engine.
Left on, it made a scheduled call every week that could only ever come back
empty. It now arrives as a draft, like the biometric lenses, and turns on when
you wire up the source. One wrinkle it shares with them: the lens registry is
engine-owned, so switching it back to active is undone by your next update
until you re-apply it.

**The quickstart says out loud that it is a placeholder.** The first command
in the README and in onboarding names a repository that does not exist; now it
tells you to put your own there first.

## 0.62.0 — The checks that kept telling you everything was fine now actually look

An audit read every engine document against the code behind it. Almost every
finding was the same shape: something promised, and nothing on the other end.
None of it announced itself, because what was missing was never a file — it was
an event that quietly stopped happening while every report still read clean.

**Your tag registry is maintained again.** It said in its own header that the
nightly integrator regenerated it. Nothing did, and nothing had since May: it
claimed 448 tags while holding 490 rows, and went on counting names that no
longer exist anywhere in your base. The index of your hubs had the same hole —
it named a writer that had no step and no renderer, so when the nightly scan
told you to regenerate it, the thing it told you to run did not exist. Both
have a renderer now, and the hub one immediately found the hand-kept index
disagreeing with the hubs it indexes.

**The freshness check no longer says you are up to date without looking.** In
three of the four pipelines it loaded its own library from a path one level
off, swallowed the failure, and reported your base current however far behind
it actually was. A scan meant to catch un-integrated work had been returning
nothing at all over a full corpus and reading as clean.

**A retirement that lands in a hub map is now caught.** The scan that proves
an identity change left nothing behind knew four ways to write a link and
missed the fifth — the one with an escaped pipe, which is what every hub map
this engine renders writes, and the most common link form in a mature base. It
would have reported a hub map full of the old name as clean. Nothing in your
base was affected; the check was simply narrower than the promise it made.

**Origin is no longer guessed wrong in the unsafe direction.** The capture that
watches for your principles claimed it could tell work from personal by itself.
It cannot — and since only personal-origin candidates are eligible to merge
into your constitution without you, the mistake pointed the wrong way. It now
says what it actually knows.

**Three files the identity work removed now actually leave your clone.** An
update copies what the engine has and cannot express what it no longer has, so
a deletion only reaches you when it is declared. These were not, which would
have left every clone carrying the project-card template — the one shape the
new contract abolished, still teaching it — beside a superseded scanner whose
tests your test run kept collecting.

## 0.61.0 — Renaming something no longer leaves half your notes pointing at the old name

Projects get renamed. Two of them turn out to be one. A project turns out to
have been a long personal arc all along. That happens, and it should — your
view changes, and the base is supposed to follow.

What did not follow was everything else. You could record the decision in the
project registry and the registry would be right, while your notes went on
naming the old thing: in their tags, in their links, in the folder holding a
card for something that no longer exists. Only one of those places was ever
checked, so the rest drifted quietly and nothing said a word.

From this release a change of identity is one operation with a name, and the
engine holds you to finishing it. Ask to retire or reclassify an identifier
and every place naming it moves in the same sitting — and the registry entry
is refused if anything is left behind. Not warned about. Refused.

Four kinds are recognised, because they are not the same job: one thing
merging into another, a plain rename, something staying alive but changing
category, and an identifier that turned out to name nothing real. The last
one has no successor, so its mentions are left frozen where they are rather
than pointed somewhere false.

Some things are deliberately never rewritten. Your meeting records keep their
words, your transcripts and logs are left exactly as they were: an old name in
something written last March is true about last March. What gets corrected is
the classification the engine itself maintains, never the text you or anyone
else actually said.

Your own registries gain what they were missing. There is now somewhere to
record a long-running arc that is not a project, and somewhere to record a
retirement with who replaced it — before, neither had a home, so a decision
had nowhere to live but your memory.

And you are now a person in your own base. You were in almost every meeting
and named in none of them, with no profile and no row, which meant checks
could flag their own owner as a stray reference. Your profile is assembled
from what your base already knows about you — your identity notes, the
principles you actually operate by, the people around you — and it is not
filled in with anything your files do not say. You are registered, but not
auto-added to every note: you are in nearly all of them, so it is your
absence that carries information.

Nothing about this needs anything from you. If your base has drift already,
the update leaves you a note about it and lets you decide, one identifier at
a time.

## 0.60.1 — A hub can no longer be broken by the run that maintains it

Found by reading a real nightly run rather than by a failing test.

Your hubs carry three fields the engine derives from their member notes —
where the material came from, who may see it, whether it is sensitive. Working
out the values had a proper home in the code; writing them back did not, so
each run edited the file by hand. One of those hand-edits wrote the values in
the wrong YAML shape, and the hub stopped being readable at all — not one
wrong field, but a file every later check silently skipped. The run happened
to re-read it and repair itself, which is luck rather than a mechanism, and
nothing damaged reached your repository.

Writing is now the same single call as deriving, so there is nothing left to
do by hand. A hub whose frontmatter will not parse is reported and left
exactly as it is, never rewritten from a guess.

The same change stops a quieter waste: the derivation rebuilt an internal
list in a different order each time, which read as «this hub changed» on
every run. Hubs are now compared by what the values mean, so a `modified:`
date that moves means something really moved.

## 0.60.0 — Removals finally reach you, and a role can admit it half-worked

Three findings from reading real nightly runs, all the same family as the last
release: something looked fine and was not.

**Deleting a file now actually deletes it on your machine.** An update copies
what the engine has; it had no way to say what the engine no longer has — so
every file ever removed is still sitting in your clone. If you passed through
the earlier roles subsystem, that is two dozen dead modules beside the live
ones, dead tests your test run still collects, and a log nothing has written
for months that still reads like a log which stopped updating. One review of
the nightly runs reported exactly that as an outage; it was a leftover.

The engine now lists retired paths, and every update removes them. The sweep
can never reach your own files: anything inside your data is refused outright,
and retiring something you produced takes a migration that tells you it did.

**A role can now say it half-worked.** The honest failure of a standing role is
not a crash — it is a service that runs out of quota partway, so the role
delivers most of its work and marks the rest unverified. That was recorded as
success, which looks identical to a good night. A run can now end `degraded`,
and if two in a row do, you are told: one is a hiccup the next run covers, two
is a limit that will keep hollowing out the work while every line still reads
as fine.

**The nightly check stops installing a package every single night.** Its
manifest validation required a library the sandbox does not ship, so every run
installed it and every log recorded the install. Without the library it now
falls back to the structural check the engine already applies when writing
those files, and says which of the two it ran. Nothing is skipped silently.

## 0.59.0 — The integrator actually runs, and an ignore rule stops halting the night

Two silent failures, both of the same kind: a thing that was supposed to happen
did not, and every file involved still looked perfectly fine.

**Your notes are integrated again.** After each processing run, a second pass
turns what was just written into connections — it opens and updates threads,
links notes into hubs, writes the back-references that let a note find its way
home, and produces the weekly health and activity summaries. That pass had no
trigger. The scheduler's instructions said it ran «inside» the processing run,
and it never did — the two cannot even run at the same time, because each holds
a lock the other refuses to start on. It had been happening only because
whatever was running the tick sometimes did it unprompted; when that stopped,
five runs in a row produced notes nobody connected, and each one reported
success.

It is now a step of its own, stated plainly, and it runs after every processing
tick. The backlog is not lost: the next run drains every batch that was missed.

**Your scheduler stops holding a stale copy of the instructions.** A scheduler
keeps the prompt you gave it, word for word, forever — so pasting a tick's body
into it put one contract in two places, and the copy in the scheduler quietly
became the older one. That is how the problem above survived: the fix could sit
in the repository while the nightly run kept following instructions from
months back.

Each routine now takes a one-line pointer to the file instead of the file's
contents. Replace your routine prompts with the loaders in `docs/scheduling.md`
once — after that, engine updates reach your schedules on their own and no
release will ask you to paste anything again.

**And the system now notices this class of failure.** The nightly check gained
one that watches for something *not having happened* — a batch older than a day
that was never integrated is raised for you. Everything else it checks looks at
what a pipeline produced; this one looks at the gap where a pipeline's output
was never consumed, which is the only shape that stays invisible when every
individual file is correct.

**A standing role no longer stops the night over an ignore rule.** The
previous release judged such a change by whether anything became invisible, and
that was still not enough: the tool hosting the tick creates its own working
files *while* a role is running, so they had not existed when the role started
and read as something the role was hiding.

The rule was answering the wrong question. An ignore rule matters only because
it hides a path from the report — so now the guard reads those paths anyway.
Whatever went invisible during a run is listed, checked for credentials, and
reported exactly like any other write. Hiding gains a role nothing, so there is
nothing left to halt the night for. Such a path is never deleted: the guard
cannot tell whose file it is, and the thing it would delete may well be the
live lock of the process running the tick.

Everything else on that surface — remotes, hooks, index flags, `.git/config` —
still stops the tick outright. There is no benign author for those.

**The nightly check now leaves a machine-readable record of its own run.** It
was the one pipeline that wrote only prose. Its runs are now summarised in the
same structured form the others use, so «what did the system do last week» can
be answered without reading a log by eye. Earlier runs are not reconstructed —
their numbers exist only as sentences, and inventing them would put guesses
into an audit trail.

## 0.58.0 — A standing role no longer fails every night over an ignore rule

If you run standing roles on a scheduler, they were reporting an error on runs
where nothing had gone wrong, and the tick was stopping before it reached the
roles queued behind them.

Two faults, both in the guard that checks what a role wrote.

The guard watches git's configuration, because a role could add an ignore rule
to hide what it wrote from `git status`. It watched by comparing the ignore
files byte for byte. But `.git/info/exclude` is git's own file, and the tool
hosting the tick keeps its runtime entries there — so an ordinary night looked
exactly like a role covering its tracks.

Worse, on seeing that change the guard tried to put the file back. That file is
never in a commit, so «put it back» resolved to «delete it» — the guard deleted
git's own file, which it promises never to touch, and then reported the
deletion it had just performed as the role's doing.

Both are fixed. The guard now never writes anywhere inside `.git/`, and it
judges an ignore change by what it did rather than by the fact that it
happened: it asks whether anything the role could have written became
invisible. When something did, the run still stops, exactly as before. When
nothing did, the change is reported as a note and the run stands.

Everything else on that surface — remotes, hooks, index flags, `.git/config` —
keeps stopping the tick outright. There is no benign author for those.

## 0.57.0 — «When did this last run» now has one answer

Nothing changes in what your pipelines do. What changes is how you find out that
they are working.

Pipeline logs are written newest-first. But each one still carries a tail of
older entries in the opposite order, so anyone reading «the last line» got the
newest entry of that tail rather than the newest entry in the file. The gap
reached 68 days: `log_process.md` reported 1 June while having run on 8 August.

Everyone was caught by this, including the `global-navigator` lens — which
honestly raised «activity is not visible where it is expected». The flag was
right; the conclusion drawn from it was not.

**`_system/scripts/pipeline_health.py`** is now the single answer to «when did
this pipeline last run», for every pipeline and every role. It takes the maximum
timestamp rather than the last line, so it does not depend on entry order and
will not break if that order changes again. Alongside it reports
`last_in_file_order`, so a discrepancy is visible instead of silent.

Run it: `python3 _system/scripts/pipeline_health.py --base zettelkasten`.

Nothing in your logs was wrong — the reading of them was.

## 0.56.0 — A carried-across role keeps what it learnt

If you have a role built on the previous shape, it now moves with what it
accumulated, not with its assignment alone.

A role that ran for months is half intent and half memory: a board of work in
flight, a reading of where the project stands, a verdict per item, a log of what
it decided. All of it lived in `state.md`, `parts/*.json` and `decisions.jsonl`.
Migration `018` named those files only as proof that the role had run, and
pointed at nothing inside them. Every byte survived the move and nothing
referenced it — so the role was re-created from its assignment and woke up
remembering nothing.

Now both the owner hand-off and the concierge plan list what the role
accumulated, how much of it there is, and where it sits. The concierge reads
those files and seeds the re-created role from them **before** the trial run —
rewriting rather than pasting: the old part archetypes are gone, what they held
is not.

**If you already updated and `018` has run for you**, a new migration `020`
reaches you too: it regenerates the hand-off and the plans from your parked
roles. The role's own files are not touched at all.

## 0.55.0 — Updates that actually apply, on every machine

If you run minder-ztn on Windows, `/ztn:update` has been quietly doing nothing.
It reported success each time and changed no files — the update machinery read
its own list of paths through a helper that adds an invisible character on Git
Bash, so every path failed to match and every failure was read as "this file
was removed upstream". Nothing about the output said so. This release fixes
that and, more importantly, makes the failure impossible to repeat silently.

**The updater now repairs itself first.** Before reading anything, `/ztn:update`
pulls the update machinery from upstream and re-reads it from the copy that
just arrived. A clone stuck on any older version can now recover by running the
update — which is the property that matters, because a broken updater could
never deliver its own fix.

**A sync that changes nothing now says so, loudly.** It counts what it applied,
checks the version really moved, and refuses to print «done» over an empty run.

**A repair can no longer block your updates.** Some migrations repair old data
rather than change the engine's shape. One of those used to abort the whole
update when it could not finish, and stayed unrecorded — so the next update
re-ran it and aborted at the same point, forever. Each migration now declares
which kind it is: a repair that cannot finish is recorded, the update continues,
and it is retried next time. If a better repair ships later, your clone picks it
up by itself.

**Your task list is read correctly whichever way it was written.** The
completeness check that finds tasks living in a note but missing from
`TASKS.md` expected the task id in one exact position on the line. Written the
other common way, it matched nothing — and reported every task as missing. It
now reads both, counts a line carrying two ids as two tasks, and refuses to
report a result at all when it cannot parse what it is looking at.

**A recording whose title contains a slash is recovered.** Your recorder names
the export after the title, and a title like «A/B-тест» cannot be a filename —
the sync turns it into two nested folders and the item lands where nothing
looks for it. It is now rejoined automatically when there is only one sensible
reading, and surfaced for you when there is not.

**Installing on Windows no longer half-works.** The installer detects Git Bash
and re-runs itself with real symlinks enabled, instead of failing partway and
leaving debris you had to delete by hand.

Also: historical batch manifests are repaired rather than re-reported every
night; anything genuinely unrepairable is marked once with the reason instead
of nagging forever, and nothing is ever invented to make it look valid.

## 0.54.0 — Roles are back, as standing jobs you describe in your own words

A role is a job you would otherwise do by hand every week: check whether the
board moved, see whether a topic has gone quiet in your notes, keep a document
you actually read up to date. You describe it in plain language; it runs on a
schedule without you, with your notes as its context and a memory of its own
between runs.

**Start one with `/ztn:role:add`.** The concierge asks what you would want to
know without having to ask, probes your real notes to show you what the role
would have found last week, and pushes for a stronger version when your data
supports one. It writes the role itself — you never see a path, a schedule
grammar or a config field. Before calling it done it validates the setup, makes
a real call against any service the role needs, and does a trial run, so a role
that cannot work is fixed with you in that conversation instead of failing
silently at dawn. `/ztn:role:list` shows what you have and when each last ran,
`/ztn:role:ask` asks a role what it knows, `/ztn:role:edit` changes or pauses
one.

**What bounds it.** A role gets the ordinary assistant toolset, so it can read
your base, run a script, or call an API — and every run is checked afterwards
against the paths its definition allows. Anything it touched outside them is put
back and shown to you in the morning, with one deliberate exception: a file that
was **already changed before that role started** is reported, never restored,
because putting it back would erase work the role did not write. The report says
whose it was — yours, or an earlier role's in the same run.

A role also cannot be given write access to the machinery that runs it — the
engine's own scripts, the skills, the scheduler helpers, `.gitignore` — because
a role that can rewrite the check is not checked. And the check reads git's own
configuration too: an ignore rule, a remote's URL, a commit hook, so a role
cannot quietly edit what the check is allowed to see.

Files it wrote inside its allowed paths are also scanned — contents and
filenames — for every credential on your base, not only the ones that role
declared, in raw, base64, hex and percent-encoded form, and the run line is
redacted the same way. A match is pulled out of the
commit, so a slip does not reach your history. Two limits stated plainly: a
credential shorter than 12 characters is never scanned, because a short value
would match your own prose and destroy it; and encodings are unbounded, so the
scan raises the cost of a leak rather than making one impossible.

**Notes back into your base.** A role that finds something worth remembering
drops one plainly-written note into your inbox, and the next processing run
folds it in like any other source — it does not edit your records or notes
directly.

**Credentials, and the one key that opens them.** A role that reaches an outside
service reads its credential from an encrypted store that travels with your repo
— each value encrypted on its own, none readable without a single key. That key
lives in the environment config of your `ztn-roles` schedule and nowhere else:
not in the repo, not in a prompt, and the credential value never enters the
assistant's context either. `/ztn:role:add` generates the key the first time you
need one and shows it once — keep it where you keep passwords, because a lost key
cannot be recovered and those credentials are simply entered again. The store is
committed deliberately: a file git ignores does not exist in a fresh cloud clone,
so without it a role could only reach outside while your own machine happened to
be awake. The cost, plainly — if your repo is ever exposed an attacker holds the
ciphertext; not the key, but not nothing. `docs/scheduling.md` has the setup,
including the one Python package a base with credentials needs;
`docs/privacy.md` carries the whole trade.

**One new schedule.** Add the `ztn-roles` tick — `roles-nightly.md`, daily at
07:00 (`0 7 * * *`). It runs last of the overnight ticks and ahead of the
morning processing run, so a note a role leaves is folded in the same morning.
Worth knowing: the tick time is the floor for a role's own timing — a role set
to fire at 14:00 never comes due at a 07:00 tick. Without this schedule your
roles exist but never run.

**If you built roles on the previous shape, this update finds them.** They were
never deleted — but the current engine locates a role by its `role.md`, which the
old shape never wrote, so they would simply have gone invisible: absent from
`/ztn:role:list`, absent from every nightly run, with nothing to tell you why.

The update moves each one to `_system/roles/_previous/` and writes a hand-off
beside them that quotes back, **in your own words**, what each role was for —
when it woke, what you told it to do, whether it ever ran. Re-create it with
`/ztn:role:add` in one conversation.

They are not converted for you, and that is deliberate. The old text speaks a
vocabulary that no longer exists, so carried across verbatim it would tell a
role to do things nothing implements — it would not fail, it would improvise,
which is worse. And `writes:` — where a role may write — is the boundary the
whole design rests on; the old shape had no equivalent to derive it from, so
guessing it for you is the one guess that must not be made. Your old
`TOOLS.md` is still there too, and named in the hand-off.

## 0.53.0 — Recovered health data counts itself

When a wearable stops syncing for a while — the watch was off your wrist, the phone
app fell behind, a ring didn't upload — the collector records those days as empty. That
part hasn't changed. What changed is what happens **after** you fix the sync and the
days come back with real data.

Before, each recovered day landed as a question in your review queue («this day was
re-collected with different content — keep, update, or recompute?») — dozens of them
after a multi-week gap, all asking the same thing. Now the engine just does the obvious
right thing on its own: a re-collected day that carries **more** data than the empty
placeholder is absorbed automatically — the record and your baselines rebuild from the
real data, no questions asked. A re-collect that somehow came back **emptier** never
overwrites a good day. Your recovered health history simply counts, the way it should.

There is nothing to do and nothing to clean up. Health records are the machine's own
read of your device — there was never a judgment call there for you to make, so the
engine no longer pretends there is one.

## 0.52.0 — Roles removed, to be rebuilt simpler

The roles subsystem is gone from the engine. The tick runner, the five `/ztn:role:*`
skills, the tools registry and everything around them have been removed.

**Why.** What was built asked you to fit a standing task into a fixed vocabulary — five
kinds of memory a role could keep, a closed list of shapes an action could take, a board
that could be written but not read. Real standing tasks do not fit a list. The design was
buying safety it did not deliver and charging complexity for it.

**What replaces it.** A role becomes what it should have been from the start: a standing
job you describe in your own words, run by the same assistant you already talk to, with
your Minder notes as its context. It decides how to do the job; the engine only bounds
where it may write and what it may reach.

**What this means for you now.** If you set up a role, its folder under
`_system/roles/` is still on disk and untouched — but nothing runs it. Nothing of yours
was deleted. A migration says so on update. When roles return you describe yours again;
the old folder is a record of what you wanted, not something that carries over.

Remove the `ztn-roles` job from your scheduler if you added one.

## 0.51.0 — Acting roles: real autonomy when you want it, honest setup

Acting roles now run the way you choose, and the friend-facing setup for running one on a
schedule is correct and complete end-to-end:

- **You pick autonomous or manual — and autonomous is real.** At creation the concierge
  asks: should the role act on its own on schedule, or will you drive it? If you say «on
  its own», it makes its board changes in the nightly run with no per-act approval —
  including sending an email or posting, if you granted that. You turn it on with one
  honest switch in your scheduler's settings (`ZTN_ROLES_AUTONOMOUS_ACK=1`) — off until
  you set it, so nothing acts hands-free by accident. The honest caveat, stated plainly:
  the runtime isn't a verified sandbox yet, so an autonomous role acts on your informed
  say-so (a booby-trapped doc it reads could steer an act, bounded to the board you
  scoped). Prefer «manual» and it stages every change for your one-word approval, as
  before.

- **The inbox door reaches existing clones.** A one-time migration registers the `roles`
  source in your live registry, so a role that notes facts back into your base
  (`emit_inbox`) is actually folded in — previously only brand-new clones had it. Runs
  automatically on `/ztn:update`.
- **The master-key instruction is now correct and concrete.** The concierge and the docs
  now name the exact environment variable (`ZTN_SECRET_MASTER_KEY`) and where it goes —
  your roles routine's env / secret config, never the prompt. An earlier wording named a
  variable that didn't exist, so a secret-bearing role would silently skip its tool at
  3am.
- **Scheduling now explains acting/secret roles.** The scheduling guide has a dedicated
  section: an acting role stages its board edits and waits for you (`--approve-acts`), a
  new role's first draft waits for `--approve-coldstart`, and the master key must live in
  the routine's env — plus a morning-routine step to approve what your roles staged.
- **Fixes.** A staged act's approval now clears its "needs you" prompt instead of leaving
  it lingering; the concierge's remit-preview probe works as documented; the nightly roles
  routine now knows its own layout up front — it runs the tick from the `zettelkasten` base
  without stopping to hunt for the pipeline scripts, so a scheduled run no longer wastes
  steps (or risks a misstep) locating them.

## 0.50.0 — A role can keep an external board in sync — with your hand on it

A role can now reach OUT: read a project's docs and its task board, work out what's
out of sync, and update the board for you — create a missing task, move a status,
close a done one. Two things stay true so you can trust it:

- **Nothing is written until you approve it.** Every change the role wants to make is
  shown to you first — the exact edits AND what it will note back into your memory — and
  runs only when you say go (`--approve-acts`). It re-checks the target right before
  writing, so it never overwrites a change someone else made in between, and it never
  double-creates a task that's already there.
- **Your notes are the source of truth; the board is a projection.** The role reconciles
  the outside board TOWARD what your grounded notes say — when they disagree, your notes
  win and the board is corrected, never the reverse.

To raise a role that acts on an external system you wire one credential once (the
concierge walks you through it) and grant the role a mandate scoping the specific board
— see the onboarding guide's «raise a role into an external system». The board tool is
config-only: the same engine drives a GitHub-issues board, a Jira project, or a Notion
database by a registry row, no code.

## 0.49.0 — Roles that track a number, keep a verdict, or push back on you

The reference library is complete: a role can now steward the shapes a plain catalog
can't compute. Describe almost any role in plain words — the concierge builds it, you
never pick a "type".

- **Track a number toward a target.** «Track my number toward a goal» → a role that
  reads your latest reading from a source you already feed it, and tells you where you
  are, the gap to your target, and which way it's trending. It never invents the number
  — it reports only what your data says, and honestly says «no data yet» when there's
  none.
- **Keep an on/off-track read on each thing.** «Give each of these a verdict —
  on-track / at-risk / off» → a role that assigns each thing a verdict from a scale you
  name, grounded in your notes, and keeps the trail whenever a verdict changes.
- **A role that pushes back when you drift.** «Hold a position and push me on it when I
  drift» → a role that argues a position and raises it when you're slipping from it —
  by default from your OWN notes (what you decided and wrote down), or from your
  life-principles when you'd rather it argue from those. It's advisory: it only ever
  raises a dismissable nudge you can read, act on, or ignore — it never acts on its own,
  and it eases off once you've pushed back on a point twice.

Everything a role records stays grounded and safe by construction: the thinking half
only proposes, a deterministic writer checks the grounding before anything is written,
and a role never asserts a fact — or forges a principle — it can't back up.

## 0.48.0 — A role can steward almost anything you describe

Roles are no longer limited to work-items and meaning. Describe what you want kept
in plain words and the concierge builds the shape for you — you never pick a
"type". New under the hood is a universal keeper:

- **A catalog of your things.** «Keep a list of things and where each one is» →
  a role that holds each entry with its own attributes (a location, a count, a
  category) and answers «where's X?». Update it as things change; it never loses
  the history.
- **A log you keep adding to.** «Keep a running log I only add to» → a role that
  appends each new entry and never rewrites the past.
- **It never makes facts up.** When a role wants to record something about your
  world that it has no note to back up, it doesn't just write it — it proposes it
  and you confirm. A role never asserts a fact on your behalf.
- **Still composable.** One role can pair a running log with a living read of what
  that log adds up to; a keeper can sit beside a narrative of how a collection evolved.

This universal keeper is the foundation for the compute-shaped roles that follow in
0.49.0 (a number toward a target, a keyed verdict, an argued push-back).

## 0.47.0 — Roles grow up: real stewards, not just task lists

A role is no longer a single ledger — it is a **composition of parts**, so it can
be the kind of steward you actually want. A project PM now holds BOTH the
**workstreams** (a keyed status board — with owner, priority, due date, and
dependencies) AND the project's **meaning**: a living, grounded read of what the
work is *for* and whether it still serves that. Most real roles want both, and the
concierge composes them for you — you never think about "part kinds".

- **Ask a role anything, in your own words.** «Спроси у Руди про X», «ask my PM role
  what's blocking the launch» — the new `/ztn:role:ask` answers read-only in the
  role's voice, from a quick status glance up to a full grounded investigation of
  its zone (notes, meetings, calls, the link-graph), and it finds the role even from
  a garbled voice reference.
- **Improve a role you already have.** `/ztn:role:edit` reads how a role has actually
  run and proposes grounded improvements («ran eight weeks, never flagged a stale
  item — add that?»), retunes its voice or zone, and pauses / resumes / retires it —
  always validating before it writes, never stranding what it tracked.
- **See your roles at a glance** with `/ztn:role:list`.
- **A role can speak up.** When something genuinely warrants your attention now — a
  blocker holding three other things, work drifting from the idea — a role surfaces
  a short, grounded nudge for you (never a silent change, always your call, and it
  won't nag or pile up).
- **An expert concierge that fights for your best role.** `/ztn:role:add` proposes
  power-uses grounded in your real notes, offers a meeting-aware zone, and honestly
  routes a wish that's really a lens or a metric source elsewhere — rather than
  cramming it into a role.

## 0.46.0 — Roles: a standing agent that keeps a living ledger for you

Minder can now run **roles** — a standing agent you give a remit (a scope of your
base) and a persona, which wakes on its own cadence, reads what's new in its zone,
and maintains a keyed, append-only ledger of the things it tracks (workstreams,
decisions, open items). Unlike a lens, which only observes, a role **keeps state**:
it advances, merges, splits, and renames items across ticks, anchoring them to real
Minder ids where they exist.

- **Safe by construction.** The thinking half only ever *proposes* a change; a
  deterministic writer runs a validator first (grounding, append-not-replace,
  churn-guard) and is the only thing that ever writes the ledger. An ungrounded or
  runaway proposal is rejected, not written — three rejects in a row auto-pause the
  role for you to look at.
- **You stay sovereign.** The role never edits its own identity (persona / remit) —
  it can only suggest, and you approve. A brand-new role's first draft is held
  frozen until you say yes.
- **Create one in plain language** with the `/ztn:role:add` concierge — describe
  what you want watched and it builds the role for you.
- **Setup step:** a new daily tick (`ztn-roles`, 06:30) joins the scheduler — see
  `docs/scheduling.md`. Existing installs pick it up on the next scheduler refresh.

## 0.45.2 — The published skeleton can't accumulate stray files (internal)

Follow-on to 0.45.1, still maintainer-only — nothing changes for you. The seed-
contract gate now also checks the *published skeleton* (not just a throwaway
build): `check_seed_contract.py --skeleton PATH` diffs the skeleton against a
clean release and fails if it carries any tracked file a fresh release does not
produce. This closes the one hole 0.45.1 left — a release copied with `rsync`
(no `--delete`) could leave behind cruft from an older release (e.g. a strip-
seed's pre-strip `.template` twin), which a fresh clone would then ship to
friends. One such leftover (`hub-cognitive-model.template.md`) is removed in this
release.

## 0.45.1 — Seeded files can't silently drift (internal)

Nothing changes in how your Minder behaves — this hardens the machinery that
builds and ships releases, so a whole class of "your fresh clone was seeded
wrong" bugs is now impossible by construction rather than by luck.

- The three ways the engine seeds a starter file — rename-on-release, copy-on-
  first-run by a skill, and read-the-template-directly — used to be told apart by
  a filename coincidence (`.md` vs not). They are now **declared explicitly** and
  a release gate (`check_seed_contract.py`, run at release and in CI) refuses any
  release where a template would leak un-materialised, an owner's private tuning
  or `.local.yaml` override would leak upstream, or a file would be shipped twice
  and clobbered on update. If a future seed is mis-declared, the release fails
  loudly instead of shipping a broken skeleton.

## 0.45.0 — Minder now speaks the way you read

Everything Minder writes for you to read — lens observations, the questions it
asks you to resolve, and the update notes you are reading right now — is now
shaped to how you personally take in information, not a one-size-fits-all voice.

- **Lens observations read the way you do.** Every lens now aligns how it
  presents what it found to your presentation profile (your SOUL working style +
  your ai-interaction principles): conclusion first, your density, plain
  language. It only touches wording — the analysis, the findings, and the
  honesty never change, and it never softens a hard observation to read nicer.
  If your profile does not fit a given finding, the lens ignores it rather than
  forcing a smoother read.
- **The clarifications review meets you halfway.** When Minder asks you to
  resolve a batch of open questions, it now phrases them for how you read —
  same rigour, less friction.
- **Updates now tell you what you actually got.** `/ztn:update` closes with a
  short, personal digest of what the update gives you — new features written to
  make you want to try them, technical fixes kept plain, and you can ask for
  more detail on any point. It sells the real value and never hypes a marginal
  change.

## 0.44.0 — A weekly read on the opportunities you're not seeing

Minder gains a new lens that, once a week, shows you where your actual week
opened a door toward what you say you want — the leads, lucky connections, and
forks that are easy to miss while you are heads-down.

- **The `opportunity` lens runs every Friday.** It lines up what actually
  happened this week against your far-goals (your SOUL goals + constitution) and
  surfaces four things: new opportunities worth a look — each with a cheap
  one-week test, so "new" never means "new rabbit hole"; a weak-tie connection
  that just entered your orbit; what changed in the doors already open (advanced,
  decayed, or closed — a short delta, not a wall of notes); and the occasional
  fork worth choosing deliberately. It is informational — it surfaces, you
  decide. Every item reads cold, in plain language, so you do not need to
  remember the backstory. See this week's read now →
  `/ztn:agent-lens --lens opportunity`.

## 0.43.0 — The cognitive-model hub works for everyone, by default

Minder now learns how you think out of the box, and every new friend gets the
cognitive-model hub instead of an empty page.

- **The `cognitive-model` lens is on by default.** It used to ship disabled
  (`status: draft`), so unless you knew to flip it on, your cognitive-model hub
  stayed blank forever. Now it runs every other Monday out of the box: it reads
  your own reflections and proposes "you seem to want X" to a review buffer you
  control — it never changes your constitution on its own, which is why it is
  safe to run by default. To see your hub fill now, run
  `/ztn:agent-lens --lens cognitive-model`. To turn it off, set its row to
  `draft` in `_system/registries/AGENT_LENSES.md` (see `docs/privacy.md` for
  exactly what it reads and produces).
- **Fresh installs get the cognitive-model hub.** The hub's seed template was
  never shipped, so a brand-new base could never build the hub at all. It now
  ships with every install; existing bases already received it via an earlier
  migration.
- **New lenses are active by default.** The platform posture is now "a lens is
  on unless there is an explicit reason to gate it" — the only gated lenses are
  the biometric ones, which need health-data you have to provision first.

## 0.42.0 — Aggregates never silently drop; broken notes self-repair

Three integrity fixes so the pipeline can no longer quietly do less than it
claims. Each ships with a migration that DETECTS your existing backlog and points
you at a one-command recovery — the migrations never touch your data and never
fail the update.

- **Tasks & calendar no longer leak.** At scale, a processing tick could quietly
  stop aggregating every note's `- [ ]` tasks and `📅` events into `TASKS.md` /
  `CALENDAR.md`, so items accumulated un-aggregated. Now a deterministic
  reconciler (`reconcile_tasks.py` / `reconcile_calendar.py`) checks completeness
  every run, the nightly lint catches any gap, and `/ztn:process --reconcile-tasks`
  (or `--reconcile-calendar`) recovers what was missed. Nothing was ever lost —
  the tasks live in your notes; they just weren't indexed.
- **Notes with a misplaced YAML fence self-repair.** A note whose
  `## Evidence Trail` heading landed inside the frontmatter fence became
  unparseable to the whole system. The producer now structurally prevents it, and
  `/ztn:lint` deterministically moves the fence back (the note's body is preserved,
  never deleted).
- **Hub synthesis stops being overwritten.** A hub's "current understanding"
  section was being wholesale-rewritten from a single batch's view, discarding
  cross-batch synthesis. It's now updated additively; a from-scratch re-synthesis
  only happens through the existing owner-reviewed staleness path.

After `/ztn:update`, if a migration reports a backlog: run the command it prints
(`/ztn:process --reconcile-tasks`, `/ztn:lint`, or `/ztn:maintain`). If it reports
nothing, you're already clean.

## 0.41.2 — Non-ASCII filenames + no git improvisation, everywhere

Hardening pass so the two failure modes from 0.41.0/0.41.1 cannot recur through
any other path:

- **`/ztn:save`** now reads the working tree with `core.quotepath=false`, so
  the interactive "save my work" button stages Cyrillic (and any non-ASCII)
  filenames instead of failing the same way a scheduled tick did.
- **Scheduler prompts** now explicitly forbid every history-rewriting or
  work-discarding git command run by hand — `--amend`, `git reset` (any mode),
  `git checkout --force`, `git rebase`, and identity edits. Recovery is the
  helper scripts' job; a tick never does git surgery itself.

## 0.41.1 — Scheduled ticks commit non-ASCII (Cyrillic, etc.) filenames

A scheduled tick could process everything correctly and then fail at the very
last step — the single commit — if any changed file had a non-ASCII name (e.g.
a Russian-titled transcript). All processed records, notes, and people would be
stranded uncommitted.

Cause: `git status --porcelain` octal-escapes non-ASCII bytes by default, and
the staging helper passed those escaped strings straight to `git add`, which
never matched them. Fixed by reading paths with escaping disabled. Covered by a
regression test.

If a tick was failing this way, just re-run it after `/ztn:update` — no data was
lost (source transcripts stay in the inbox until a tick commits successfully).

## 0.41.0 — Scheduled ticks work on Windows clones

Scheduled runs discover the `/ztn:*` skills from `.claude/skills/<name>/SKILL.md`
in your clone. That layout was shipped as git symlinks — which **do not survive
a Windows clone** (`core.symlinks=false` turns each symlink into a text file, so
the skill folder vanishes). On such a clone every scheduled tick died at its
first step, and the agent could spiral into out-of-contract recovery.

### What you get

- **Cross-platform skills.** The skeleton now ships `.claude/skills/` as real
  files, not symlinks — they clone correctly on Windows, macOS, Linux, and in
  Cloud Routines. (The maintainer's own repo keeps symlinks for the dev loop;
  they are dereferenced to real files at release.)
- **Self-healing update.** `/ztn:update` now replaces a broken local
  `.claude/skills/` with the real-file layout.
- **A pre-flight guard.** Every tick verifies skills resolve before running and,
  if something is still wrong, ships a precise failure note instead of failing
  obscurely. Scheduler prompts also explicitly forbid rewriting commit identity
  (`git commit --amend` / `--reset-author`) — an "unverified" sandbox author is
  normal and never needs fixing.

### If a scheduled tick was already failing on Windows

An already-broken clone cannot self-heal on the first `/ztn:update` (the old
update path and a stale `.gitignore` block it). Run this once to repair and
push the fix so your Cloud Routines pick it up, then future updates self-heal:

```
git fetch upstream
rm -rf .claude/skills
git checkout upstream/main -- .gitignore .claude/skills
git add -A .gitignore .claude/skills
git commit -m "fix: cross-platform real-file skills layout"
git push
```

No personal data is affected — `.gitignore` and `.claude/skills/` hold only
engine files. If unsure, ask your Claude to run these for you.

## 0.40.0 — Scheduled processing self-drains a backlog

If your scheduler is off for a while, the inbox piles up. Previously the first
catch-up run tried to process the whole backlog at once — and on a cloud
schedule that single run could run past its time limit, get killed mid-way, and
strand its work (nothing saved, next run repeats the overload).

Now `/ztn:process` bounds how much it takes per run, so a backlog drains
steadily across successive runs instead of choking on one.

### What you get

- **A per-run transcript cap (default 12).** Each run processes the oldest
  transcripts up to the cap; the rest wait in the inbox and are picked up next
  run — nothing is lost, order is preserved. On a normal daily inflow the cap
  never binds.
- **Biometric days are never capped.** `metric-day` sources (Garmin, Oura,
  ActivityWatch, …) are deterministic and cheap — they always process in full,
  so no biometric gaps.
- **Manual escape hatch.** For a supervised local catch-up with no time
  pressure, `/ztn:process --limit all` drains the whole inbox in one run.
  `--limit N` sets a custom cap for a single run.

### Behaviour change

A bare `/ztn:process` now processes at most 12 transcripts per run (was:
unbounded). Pass `--limit all` to restore the old drain-everything behaviour
for a single run. Scheduled ticks need no change — they pick up the default
automatically.

## 0.39.0 — A visible model of how you think

The `cognitive-model` lens (0.38.0) proposed «you seem to want X» one candidate
at a time. Now those patterns have a **home you can see**: a single hub —
*«how you think, as Minder sees it»* — with one row per cognitive /
communication axis (how you structure thought, what evidence convinces you, what
feedback lands, how you want directness, how context should carry across
sessions, …), each showing what's understood, how confidently, and the
principle + the verbatim quote it rests on.

### What you get

- **The hub** at `5_meta/mocs/hub-cognitive-model.md` — a maintained map of the
  model across the cognitive axes, updated automatically by `/ztn:maintain`. The
  «portrait» at the top is yours to write; the table below is auto-rendered —
  don't hand-edit it. Blank/thin axes show the lens what to look at next.
- **Source quotes on learned principles.** A principle promoted from a reflection
  can carry the verbatim quote that grounds it (`source_quote:`) — so «why does
  Minder believe this about me?» is always answerable, and a future
  «Your Mind» screen can render principle + quote.
- **A nightly integrity check** keeps the axis tags honest (valid axis, no
  duplicates, sensitivity coherence) and surfaces issues for your review — it
  never edits your constitution on its own.

### To opt in / out

Nothing to do. The hub fills only from principles you've tagged and from the
`cognitive-model` lens — which still ships **OFF** (enable it deliberately in
`AGENT_LENSES.md`, same as before). With the lens off and no tagged principles,
the hub simply stays blank.

### Backward compatibility

Additive — nothing breaks. `cognitive_axes:` and `source_quote:` are optional
principle fields. A one-time migration (`010-cognitive-model-hub-seed.sh`, run
automatically on `/ztn:update`) creates the empty hub for existing installs; the
next `/ztn:maintain` fills it.

### For maintainers

New engine pieces: `render_cognitive_model_hub.py` (deterministic hub renderer,
`/ztn:maintain` Step 7.9), `lint_cognitive_axes.py` (lint Scan F.8), the axis SoT
block in `lenses/cognitive-model/prompt.md` (the single source for the axis set),
and the `source_quote`/`cognitive_axes` fields in the principle schema. The hub
is a pure projection of the constitution — it holds no truth of its own.

## 0.38.0 — The assistant learns how to talk to you

Two layers, plus a way the system keeps learning your style — without becoming
a yes-man.

### What changed

- **A communication baseline, loaded by default.** The assistant now answers
  you conclusion-first (the point before the play-by-play), leads with a ready
  result instead of an options menu, structures for scanning, cuts fluff — and
  stays critical: no flattery, it pushes back with reasons. This is the
  universal floor; your personal calibration layers on top.
- **Your own presentation preferences.** Put how you like praise and criticism
  in your `SOUL.md → ## Context for Agents`; put your recipe for long-form pieces
  (reports, audiobooks, debriefs) in its own `_system/long-form-playbook.md`
  (loaded on demand, never for normal answers). Both ship as templates with
  filled examples to copy.
- **A lens that learns your style from your reflections — opt-in, off by
  default.** A new `cognitive-model` lens can read your own voice-notes and
  reflections and propose "you seem to want X" as principles for you to approve
  or ignore. It ships OFF — enable it deliberately by setting its row to
  `active` in `AGENT_LENSES.md`. It never changes anything on its own:
  proposals land in your review queue, only highly-confident ones append
  without a click (tunable), and promotion into your constitution always needs
  your approval. See `docs/privacy.md` for exactly what it reads and produces.

### Why
The more the assistant adapts to how you think, the bigger the risk it just
tells you what you want to hear. The baseline's "no sycophancy" rule and the
lens's "don't mine for what comforts you" guard are deliberate: it learns your
thinking, it does not become your echo.

## 0.35.0 — Content becomes a living shelf, not a cold backlog

The content pipeline is rebuilt to be push-based and incremental like the rest of
the system, instead of one heavy session you have to start cold.

### What changed

- **`/ztn:check-content` → `/ztn:content`.** Three modes: default shows status
  from the new content map; `--draft <topic>` drafts one post on demand;
  `--maintain` is the scheduled draft-maintainer that keeps living drafts in
  `6_posts/drafts/` — creating, updating on new material, and archiving published
  ones, never rewriting a draft you've edited.
- **A weekly rhythm.** A new `content-synthesis` lens (Mondays) reads your whole
  content backlog from the outside, finds what's ripe and the cross-theme posts;
  the maintainer (Tuesdays) turns those into drafts. One autonomous run, a warm
  shelf of drafts waiting when you want them. Publishing stays your manual act.
- **Drafts are conceptual, in your language.** Each draft is the idea/argument, in
  your primary language (from SOUL) — platform and final language are your
  publish-time choices, not baked in.
- **Cleaner markup.** `content_type` drift is healed automatically; `content_angle`
  is always a list. A new `CONTENT_MAP.md` view + a small ledger track it all.

### Action needed

If you pinned the old `/ztn:check-content` command, switch to `/ztn:content`.
Migration `008` cleans up the old skill folder and seeds the new ledger on
`/ztn:update`; re-run `install.sh` afterwards.

## 0.33.0 — PROJECTS.md is the single source of truth for projects

### What changed

The nightly project check (Scan A.8) now treats `PROJECTS.md` as the one
authoritative list of your projects. Before, a project hub page could
silently stand in for a registry entry — so a project that had a hub but
was never written into `PROJECTS.md` (registry drift) passed unnoticed.
A hub is a view over your notes, not proof that a project exists; only the
registry is.

Each `projects:` entry on a note is now resolved against the registry and
gets a precise, actionable message instead of a generic "unknown":

- **registered project** → fine (with or without a hub yet);
- **a trajectory** used as a project → "use `tags: [trajectory/…]`";
- **a consolidated/retired ID** → "point at its successor";
- **a hub with no registry row** → "register it, or remove the hub";
- **a real typo** → "fix the slug or register it".

If `PROJECTS.md` is missing or empty (e.g. mid-setup), the check now stays
quiet instead of flagging every note — it has no source of truth to judge
against. Nothing to migrate; your existing notes are unaffected.

## 0.32.0 — Concept names kept verbatim + fewer false project warnings

### What changed

Two correctness fixes, nothing to migrate.

**Concept names that begin with a category-like word are no longer
mangled.** The engine used to strip a leading "type word" from concept
names — so `decision_making` silently became `making`, `value_chain`
became `chain`, and `skill_based_...` lost its `skill_`. That split one
concept into wrong pieces and quietly merged unrelated notes. The problem:
a bare name can't tell a redundant label (`skill_python`) from a compound
where the word belongs (`decision_making`), and guessing corrupts the very
thing the knowledge graph is built on — stable identity. So the engine now
keeps every concept name **exactly as written**. The "no type prefix in a
name" guideline is still honoured where it can be done safely — at
extraction, where the model knows the concept's type — never by a blind
rewrite. (A name that *is* nothing but a bare category word, like `theme`
or `skill` alone, is still dropped — that's too broad to be a concept.)

**The nightly check stopped false-alarming about real projects.** A record
tagged with a project that is registered in `PROJECTS.md` but doesn't have a
hub page yet was wrongly flagged as an "unknown project" every night
(hub pages only appear once a topic accumulates enough notes). The check
now treats a project as valid if it's in `PROJECTS.md` **or** has a hub —
so registered-but-young projects stop generating noise.

## 0.31.0 — Windows-safe filenames

### What changed

Some recorder tools — Plaud in particular — name their export folders
with ISO timestamps like `2026-04-29T14:09:30Z`. Colons are illegal in
file names on Windows, so such a folder couldn't be created in your
inbox on a Windows machine, and pulling it from another device (a Mac
or a phone) broke `git checkout` on the Windows clone.

The engine now keeps every new name Windows-safe automatically:

- **`/ztn:process`** renames non-portable inbox items before processing
  (`2026-04-29T14:09:30Z` → `2026-04-29T14-09-30Z`), so every link the
  engine writes is born with the safe name — nothing ever breaks.
- **`/ztn:save`** does the same rename before committing, so a raw inbox
  drop from one device never breaks checkout on your Windows device.
- **`/ztn:lint`** backstops both nightly.

Nothing to migrate and nothing to do by hand: your existing processed
files keep their names (old colon-named folders remain readable
forever), only new arrivals are normalised. Windows users can now
onboard without workarounds.

## 0.30.0 — `describe-me` is a first-class source

### What changed

Self-descriptions now have their own inbox: `_sources/inbox/describe-me/`
(previously a hidden subfolder under `crafted/` that `/ztn:process` skipped).

- **Drop identity material there anytime** — profile updates, "how I think"
  notes, AI-generated self-portraits. `/ztn:process` picks them up as
  regular content and they become knowledge notes like everything else.
- **`/ztn:bootstrap` still reads it first** as the primary seed for SOUL.md
  during onboarding; files it consumes are moved to
  `_sources/processed/describe-me/` so nothing is ingested twice.
- **`PROFILE.template.md` stays put** — files named `*.template.md` are now
  excluded from processing engine-wide, in every source. Templates are
  seed material, not content.

Migration `006-describe-me-top-level-source.sh` runs automatically on
`/ztn:update`: it moves the old `crafted/describe-me/` folders (inbox and
processed sides) to the new location and updates your SOURCES.md registry.

## 0.29.0 — `/ztn:recap` can save verbatim artifacts to `crafted/`

### What changed

`/ztn:recap` is now adaptive. Besides the usual session *summary* into
`_sources/inbox/claude-sessions/`, it can also save a **verbatim
artifact** — a self-contained piece you'll reuse as-is (a toast, speech,
letter, post, proposal, spec) — into `_sources/inbox/crafted/`, with the
exact wording preserved.

Three modes, never forced on you:

- **recap** (default) — summary only. If a finished piece is detected,
  the skill *proposes* saving it; it never fabricates or drops one
  silently.
- **recap + crafted** (`--crafted`, "save the original too") — summary
  plus the verbatim artifact.
- **crafted-only** (`--crafted-only`, "just save the original") — the
  artifact alone, no recap.

When both are written they carry a **bidirectional link** (recap
`Crafted artifacts:` ↔ crafted `Source session:`), so `/ztn:process`
connects them even if they land in different batches. Verbatim text
lives only in `crafted/`; the recap stays a summary.

## 0.27.0 — Source naming tolerance (universal)

### What changed

The `/ztn:process` inbox scanner now treats folder names and contained
filenames as **best-effort hints**, not contracts. Across every source-
type (`plaud`, `garmin`, `claude-sessions`, manual drop-ins, …) the
processor accepts whatever the owner or producer drops in:

- Folder names that don't match the ISO / date / topic patterns fall
  back to file mtime silently — no CLARIFICATION.
- A subfolder containing a single `*.md` with a non-canonical filename
  is taken as-is (applies to `dir-per-item` and the new third
  fallback step in `dir-with-summary`).
- CLARIFICATIONs are reserved for cases where the engine would
  otherwise have to guess at the cost of correctness: multiple `*.md`
  files in one subfolder with no canonical name, missing summary-
  delimiter inside a file actually named `transcript_with_summary.md`,
  or a parsed folder-date that contradicts mtime in a way mtime can't
  resolve.

This removes friction for owner-driven flows (ad-hoc capture, manual
folder creation, `/ztn-recap` exports across Claude Code versions that
produce non-canonical filenames like `TECH-RECAP.md`) without weakening
the producer-drift signal (the right place to catch a producer suddenly
emitting weird names is `/ztn:lint` heuristics on the source itself,
not the inbox scanner).

### Affected files

- `integrations/claude-code/skills/ztn-process/SKILL.md` — §2.1
  «Naming tolerance» blockquote + relaxed `dir-per-item` /
  `dir-with-summary` scan rules; §2.3 folder-name parsing drops the
  CLARIFICATION on legacy / free-form names.
- `zettelkasten/_system/registries/SOURCES.template.md` — new spec
  section «Naming tolerance (universal across all source-types)»;
  `dir-per-item` / `dir-with-summary` Layout descriptions extended.

### Compatibility

Backward-compatible relaxation. Strict-canonical-name producers
(`plaud`, `garmin`) continue to emit canonical names — no change to
producer output. Friends running older `/ztn:process` will keep
seeing CLARIFICATIONs on free-form folder names until they sync
this version via `/ztn:update`.

## 0.25.0 — Scheduler single-commit + Cloud Routines delivery

### What changed

The autonomous scheduler protocol was producing dozens of commits per
tick (one per phase the agent felt like grouping) and accumulating
stranded `claude/*` branches on origin in Cloud Routines setups.
Replaced the old per-step `/ztn:save --auto` model with a strict
single-commit + adaptive-delivery design:

- **One commit per tick, guaranteed.** `scripts/scheduler/stage.sh`
  is staging-only (idempotent, may be called any number of times
  during a tick); `scripts/scheduler/finalize-tick.sh <tag>` is the
  sole commit + delivery point. Engine paths are filtered out via
  `.engine-manifest.yml` + a small conservative-prefix list.
- **Two delivery modes auto-detected.** LOCAL (start branch = main):
  direct `git push origin main`. ROUTINES (start branch = sandbox
  ref like `claude/<random>`): push to sandbox, `gh pr create
  --base main --head <sandbox>`, `gh pr merge --squash
  --delete-branch`. Cloud Routines' git proxy refuses direct push
  to main; this routes around it.
- **MCP fallback for gh-less sandboxes.** Cloud Routines sandboxes
  typically don't ship `gh`. When `finalize-tick.sh` exits 2 with
  «gh CLI not found in PATH», the scheduler prompts have a strict
  Step 5b that routes the create + merge through the `github` MCP
  server. The only authorized non-script git/MCP path in the
  prompts.
- **Partial-tick fold recovery.** If a previous tick committed
  locally but never pushed, the next tick's `finalize-tick.sh`
  folds it into the current commit via `git reset --soft
  origin/main`. Refuses to touch non-scheduled commits ahead of
  origin/main (no force-push, ever).

### Required repo setting

Cloud Routines also refuses `git push origin --delete <branch>`, and
the github MCP server has no `delete_branch` tool. Sandbox-branch
cleanup is therefore delegated to GitHub's repo setting:

**Settings → General → Pull Requests → ☑ Automatically delete head
branches**

Enable this once per repository. Without it, every Routines tick
leaves a sandbox branch on origin.

`docs/onboarding.md` §9 calls this out for new setups.
`docs/scheduling.md` documents the full delivery model.

### Migration

`scripts/migrations/005-scheduler-pr-merge-delivery.sh` prints a
re-paste reminder when run after `/ztn:update`. After this engine
update:

1. Enable the «Auto-delete head branches» repo setting (above).
2. Re-paste the three updated prompt bodies from
   `integrations/claude-code/scheduler-prompts/` into your
   `/schedule` Routines.
3. (Optional one-time) Delete any pre-existing `claude/*` sandbox
   branches accumulated before this update:
   `git push origin --delete <branch>` from a local clone.

### Removed

- `scripts/scheduler/save.sh` — replaced by `stage.sh` +
  `finalize-tick.sh`.
- `scripts/scheduler/cleanup-sandbox.sh` — replaced by GitHub's
  built-in auto-delete on PR merge.

## 0.22.0 — Biometric pipeline (metric-day source family)

### What landed

A complete biometric ingestion + analysis pipeline running on top of the
existing /ztn:process → /ztn:maintain → /ztn:agent-lens stack:

- **Tier I** — Per-day deterministic pipeline. New `metric-day` source
  family on SOURCES.md. /ztn:process metric-day branch parses
  `_sources/inbox/garmin/<date>.md` (Garmin daily snapshot) into
  `_records/biometric/<date>.md` with rolling 28-day baselines (42 for
  chronic_load), σ-deviation flags, categorical event detection (HRV /
  training / ACWR / readiness transitions), and streak state machine.
  No LLM in this branch — pure Python (~100 ms per file).

- **Tier II** — Weekly correlation worker, runs from /ztn:maintain
  after-batch with weekly idempotency gate (`last_weekly_run.txt`).
  Phase 1: Pearson over biometric × biometric metric pairs at lags
  0–3, anomaly cluster detection. Phase 2: lexicon-based affect tag
  extraction over `_records/observations/` + `_records/meetings/` +
  point-biserial correlation against biometric metrics. Calibration
  drift detection vs expected fire-rates surfaces
  `biometric-threshold-drift` CLARIFICATIONs. Backfill mode on
  first run iterates completed ISO weeks chronologically.

- **Tier III** — Four new agent-lenses ship under `status: draft`:
  - `biometric-anomaly-narrator` (daily) — narrates yesterday's
    biometric record when non-empty.
  - `biometric-cross-domain` (weekly thursday) — top 1–2 strongest
    cross-source findings from Tier II with cited journal evidence.
  - `training-load-trend` (weekly monday, conditional) —
    self-skips when `acute_load == 0` for 14 days.
  - `biometric-life-synthesis` (weekly monday, flagship) —
    multi-source synthesis bridging biometric pattern with life
    narrative; emits Memory note when strong tier reached.

- **Patches** to four existing lenses (`stated-vs-lived`,
  `energy-pattern`, `weekly-insights`, `global-navigator`) so they
  read biometric records / Tier II output / new biometric lens runs.

- **Ambient layer** — `## Health Snapshot` block (≤15 lines,
  life-connection focused) injected into `CURRENT_CONTEXT.md` after
  the Focus block, before Active Threads.

### Migration

`scripts/migrations/002-sources-family-column.sh` adds the `Family`
column to existing SOURCES.md; existing rows populate as `transcript`.
Idempotent — safe to re-run.

### Activation

The pipeline lies dormant until you wire a biometric source:

```
/ztn:source-add garmin --family metric-day
```

Then drop daily Garmin snapshots into `_sources/inbox/garmin/<date>.md`
(your collector's responsibility). After ≥14 days of records, Tier II
worker activates. Activate biometric lenses by flipping
`status: draft` → `active` in `AGENT_LENSES.md`.

### Notes for friends

- Universal: thresholds are σ-based (auto-adapt per-user baseline);
  affect lexicon ships RU+EN seeds, owner extends via
  `affect_lexicon.local.yaml`. Non-RU users in the cohort can drop RU
  entries via the local overlay.
- Privacy hard-set: `is_sensitive: true`, `audience_tags: []`,
  `origin: personal` on every biometric record + derived view.
  Owner-only by construction.
- Lens prompt patches reset precedent calibration in
  `lens-resolution-history.jsonl` for the four patched lenses; first
  interactive resolve session post-update will recalibrate naturally.

## 0.21.0 — Skills work in cloud Routines + thin scheduler prompts

### Cloud Routines now discover ZTN skills

Cloud Claude Code Routines (the cron-like scheduler that runs an
autonomous agent against your repo) clone the repo fresh and look for
skills only at the canonical `.claude/skills/<name>/SKILL.md` path. ZTN
skills lived only at `integrations/claude-code/skills/`, so slash
invocations like `/ztn:process` and `/ztn:lint` were inert in
Routines — they fell back to a fragile pattern of "open the SKILL.md
yourself and execute its steps", which broke in different ways every
night.

This release commits `.claude/skills/ztn-*` symlinks at the repo root
that point into `integrations/claude-code/skills/<name>/`. Routines
now load all 15 ZTN skills automatically; slash invocations work
identically in cloud and local sessions. SKILL.md sources were
de-templatized in the same change (`{{MINDER_ZTN_BASE}}/...` →
`zettelkasten/...`) so paths resolve from the repo CWD without a
render step.

### Scheduler prompts shrank by 65%

The three scheduler prompts (`process-scheduled.md`,
`lint-nightly.md`, `agent-lens-nightly.md`) were rewritten to ~92
lines each (down from ~250). They now invoke `/ztn:process` /
`/ztn:lint` / `/ztn:agent-lens --all-due` directly via slash and
delegate shared plumbing to five new bash helpers under
`scripts/scheduler/`:

- `pin-main.sh` — fetch + checkout fresh `origin/main` (with safe
  rebase if local commits exist), capture the sandbox branch
  for cleanup, and GC any leftover sandbox branches from prior ticks
- `lock-check.sh` — abort if any cross-skill pipeline lock is recent
  (<2h); auto-clean stale (>2h) locks
- `save.sh` — engine-aware commit + push (renamed from the old
  `scripts/scheduler-fallback-save.sh`)
- `cleanup-sandbox.sh` — first-attempt delete of the sandbox branch
  the Routine cloned onto, with diagnostic surfacing when the
  platform holds the active session ref
- `ship-failure-note.sh` — append a one-line cause to
  CLARIFICATIONS.md and ship via save.sh, so failures surface in
  the next interactive resolve session

### Scheduler-tagged commit messages

`/ztn:save` now accepts a `--tag <text>` flag that prefixes the commit
message before the `[scheduled]` suffix. Each scheduler prompt passes
its tick name (`--tag scheduler/process`, `--tag scheduler/lint`,
`--tag scheduler/agent-lens`) so every autonomous commit makes the
producing tick visible at a glance:

```
scheduler/lint: routine save: 25 file(s) across 6 areas [scheduled]
scheduler/process: process batch: 8 sources → 9 records + 6 notes [scheduled]
```

Idempotent: if the message already starts with the tag, no second
prefix is added. The bash fallback `save.sh` produces the same shape
when invoked with `"scheduler/<tick>: ..."` style messages.

### Sandbox branch cleanup

When a Routine clones the repo onto its session branch (e.g.
`claude/admiring-shannon-ETCE3`), the platform holds the branch ref
for the duration of the run, so end-of-tick `git push --delete` is
often rejected. Pin-main now runs a GC pass at the start of every
tick that lists `claude/*` branches on origin (excluding the current
session's own ref) and deletes any leftover from prior ticks. Net
effect: the previous tick's sandbox branch goes away when the next
tick fires, instead of accumulating on origin indefinitely.

### After `/ztn:update`

No manual migration required for friends pulling this release —
`git pull` brings the new `.claude/skills/` symlinks; re-running
`bash integrations/claude-code/install.sh` (already part of the
`/ztn:update` follow-up reminder) refreshes user-level symlinks.
If you have scheduled prompts pasted into Claude Code's `/schedule`,
re-paste the bodies of the three updated files in
`integrations/claude-code/scheduler-prompts/` — `/schedule` holds
prompt text verbatim and does not auto-update on `/ztn:update`.

## 0.20.0 — Lens output upgraded for Obsidian + in-vault graph reset

### In-vault Reset Graph button

`minder-ztn.md` now ships a `## ⚙️ Maintenance` section with a
DataviewJS button: «🔄 Reset graph view to defaults». One click
restores `graph.json` (color groups, forces, default filter) from
the engine snapshot at `.obsidian/graph-defaults.json`, with an
auto-backup of your current state. No CLI needed for the common
recovery case after Obsidian wipes color groups during filter
tweaks. Requires Dataview JS Queries enabled (already part of the
Dataview setup checklist).

The CLI path stays available for power users:
`bash integrations/obsidian/seed.sh --reset-graph`.

### Lens output upgraded for Obsidian


Lens output files now carry a human-readable `title:` and reference
cited files via `[[wikilinks]]` instead of paths in backticks. Two
practical effects:

- **Lens nodes in the graph have real names.** Instead of seeing
  `2026-05-04` as a node label, you see «🔭 stalled-thread —
  2026-05-04» (with Front Matter Title plugin enabled). Files become
  scannable in the file tree, Quick Switcher, and graph view.
- **Lens nodes connect to the records they observe.** Each Evidence
  bullet is now `[[basename]]` so Obsidian draws an edge between the
  lens output and the record / hub / principle it cites. The
  `🔭 Lens observations` graph preset becomes meaningful — you see
  «what the AI noticed about which records», not a cluster of
  disconnected dates.

**To opt in:**

1. Run `/ztn:update` (or `scripts/sync_engine.sh`) — pulls the new
   `_frame.md` Stage 2 schema.
2. The next `/ztn:agent-lens` run emits the new format automatically.
   No action needed for friends without prior lens output.

**For pre-existing lens output:** if you happen to have lens files
from before this version (rare — most friends adopt lenses fresh),
they remain valid in their original form per the grandfathering
clause in `_frame.md` Stage 3. The validator never rewrites files
already on disk. New emissions from this version forward use the new
format.

**For maintainers:** `_frame.md` Stage 2 prompt schema and Stage 3
validator updated in lockstep. Wikilink basename resolution replaces
ZTN-path resolution. Legacy outputs grandfathered.

---

## 0.19.0 — Obsidian vault integration

The first proper UI for ZTN. Until now you read your records as files
and your registries as markdown tables; now there's a vault config
that opens cleanly in Obsidian, a dashboard, graph presets, hotkeys,
bookmarks, and visual cues per note type.

**What you get after `/ztn:update` + re-running `install.sh`:**

- **`minder-ztn.md` dashboard** at the vault root. Live blocks (powered by
  Dataview) for recent meetings, observations, active projects, people,
  open tasks. Static links to Current Context, Open Threads,
  Clarifications, SOUL.
- **Bookmarks pane** (left sidebar, `Cmd+Shift+B`) — pre-pinned
  navigation: Now, Identity, Registries, Browse, Obsidian docs.
- **Graph view tuned for ZTN** — colour-coded by PARA layer (people
  orange, meetings green, observations teal, constitution purple, hubs
  gold, projects blue, archive grey). Engine internals and flat
  aggregator nodes (INDEX, registries) hidden by default.
- **6 graph presets** documented in `integrations/obsidian/views.md` —
  copy-paste filters for People web, Decision lineage, Project
  landscape, Hub network, Knowledge distillation, Sensitive zone.
- **Hotkeys** — `Cmd+Shift+G` graph, `Cmd+Shift+L` local graph,
  `Cmd+Shift+B` bookmarks, `Cmd+Shift+O` outline, `Cmd+Shift+K` tag
  pane, `Cmd+Shift+Y` insert template.
- **Visual cues** — coloured left border on the editor pane plus
  emoji prefix in tab headers and file explorer per note type
  (👤 person, 🤝 meeting, 👁 observation, ⚖️ axiom, 🧭 principle,
  📏 rule, 🌟 hub, 🚀 project).
- **Engine paths hidden** — `_system/state/`, `_system/scripts/`,
  `_system/docs/`, `_sources/processed/`, `*.template.md`,
  `integrations/`, `__pycache__/`, README files. Two layers: a CSS
  snippet hides them from the file tree, `userIgnoreFilters` hides
  them from search and graph.
- **Comprehensive guide** at `integrations/obsidian/guide.md` —
  hotkeys reference, daily/weekly/monthly recipes, frontmatter rules,
  reset-to-defaults procedure.

**To opt in:**

1. Run `/ztn:update` (or `scripts/sync_engine.sh`)
2. Run `bash integrations/claude-code/install.sh` — it now seeds
   `<vault>/.obsidian/` and `<vault>/minder-ztn.md` if they don't exist.
3. Open Obsidian → "Open folder as vault" → select `zettelkasten/`
4. Install three community plugins (instructions print on first run):
   - **Dataview** by Michael Brenan — powers HOME's live blocks
   - **Tasks** by Clare Macrae — global task view across the vault
   - **Front Matter Title** by snezhig — shows `title:` from
     frontmatter instead of snake-case file IDs in graph, file tree,
     tab headers, Quick Switcher

**To opt out:** delete `<vault>/.obsidian/` and `<vault>/minder-ztn.md`. The
ZTN engine itself doesn't depend on Obsidian — skills work the same
whether you have the vault open or not.

**Backward compatibility:** purely additive. All earlier skills,
manifests, and engine internals unchanged.

**For maintainers:** new engine paths under `integrations/obsidian/`
ship via `release_engine.py`. The seeder is idempotent and never
overwrites a friend's live `.obsidian/` (only `--force` does, with
auto-backup). See `integrations/obsidian/README.md`.

---

## How to read this changelog

Each release has:

- **What you get** — concrete features after running `/ztn:update`
- **To opt in / out** — what you actively need to do
- **Backward compatibility** — whether anything broke
- **For maintainers** — engine-level notes (skip if you're a user)

Versions before 0.19.0 are not documented here in user-readable form;
see git log + integration commit messages for the engineering history.
