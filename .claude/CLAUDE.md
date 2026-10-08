# minder-memory — project guide for Claude Code

This repo holds two things side-by-side:

1. The **Minder Memory engine** — skills, scripts, system docs, integration tooling. Authored here, released to the public skeleton (`minder-memory`) via `scripts/release_engine.py`, consumed by friends through `/minder:mem:update`.
2. **Owner data** under `zettelkasten/` — records, knowledge notes, constitution, registries, hubs. Owned by the human running this clone.

Different rules apply to each. This file is the project-local contract.

The global rule `minder-memory.md` (imported by the managed block of `~/.claude/CLAUDE.md`) covers HOW to USE the base from any session. The operating philosophy loads in this repository only (from another subdirectory the import is external: interactive sessions ask once, headless ones skip it):

@../zettelkasten/_system/docs/ENGINE_DOCTRINE.md

**This file covers what those don't: how to WORK ON THIS REPO.**

## Authority order (top wins on conflict)

1. `zettelkasten/_system/docs/SYSTEM_CONFIG.md` — system contract; hard rules, schemas, lock matrix
2. `zettelkasten/_system/docs/CONVENTIONS.md` — documentation conventions; binding on every edit to engine docs and SKILLs
3. `zettelkasten/_system/docs/ENGINE_DOCTRINE.md` — operating philosophy; cross-skill principles (loaded in this repo)
4. This file — project-local engine-development rules
5. Skill `SKILL.md` under `integrations/claude-code/skills/<name>/` — pipeline-specific spec
6. `zettelkasten/_system/SOUL.md` — owner identity calibration

When you find these in conflict, the higher one wins. When a rule is absent everywhere, surface a CLARIFICATION rather than silently choose.

## Engine vs data — the boundary

`.engine-manifest.yml` at the repo root is the **source of truth** for what is engine. Read it before touching any path you're unsure about.

### Engine paths

What the main engine paths are for: `zettelkasten/_system/docs/ENGINE_MAP.md → Engine paths`; the complete set is `.engine-manifest.yml`.

`AGENTS.md` is engine too — the Codex-facing twin of this file, shipped so a friend's non-Claude runtime reads the same contract; keep the two reconciled, since a rule that reaches one runtime and not the other is worse than no rule. Notably **not** engine, though they sit beside engine paths: `.github/workflows/` (owner-only CI; a friend's clone stays CI-free by design), and the repo-root `README.md` (the maintainer's own; the public one ships from `README.template.md`).

### Owner-data paths (NEVER edit by hand — route through Minder Memory skills)

| Path | Skill that owns writes |
|---|---|
| `zettelkasten/_records/{meetings,observations}/` | `/minder:mem:process` |
| `zettelkasten/_records/{biometric,activity}/<source>/` + `_system/state/{biometric,activity}/`, `_system/views/{biometric,activity}/` | `/minder:mem:process` metric-day branch (records/baselines) + `/minder:mem:maintain` weekly workers (views) — deterministic, never hand-edit |
| `zettelkasten/_sources/inbox/` | `/minder:mem:process` consumes; `/minder:mem:source-add` registers new types |
| `zettelkasten/_sources/processed/` | `/minder:mem:process` (move-only); never delete |
| `zettelkasten/0_constitution/{axiom,principle,rule}/` | `/minder:mem:capture-candidate` → `/minder:mem:lint` F.5 promotion → `/minder:mem:regen-constitution` |
| `zettelkasten/{1_projects,2_areas,3_resources,4_archive}/` (excluding READMEs) | `/minder:mem:process`, `/minder:mem:maintain` |
| `zettelkasten/5_meta/mocs/`, `zettelkasten/6_posts/` | `/minder:mem:maintain` (incl. `hub-cognitive-model.md`: its `<!-- AUTO-GENERATED: cognitive-model-hub -->` zone is rendered by `render_cognitive_model_hub.py` Step 7.9 — never hand-edit the table; the prose «portrait» above the markers is owner-curated) |
| `zettelkasten/_system/{SOUL,POSTS,long-form-playbook,decision-advisory-playbook}.md` | owner-curated; engine reads, surfaces clarifications, never silently overwrites |
| `zettelkasten/_system/{TASKS,CALENDAR}.md` | `/minder:mem:process` — derived aggregates over note `- [ ]` / `📅` items (owner owns only the TASKS `## Stale` section). Not hand-edited; completeness enforced by `reconcile_tasks.py` / `reconcile_calendar.py` |
| `zettelkasten/_system/registries/TAGS.md` | `/minder:mem:maintain` (`render_tags.py`) |
| `zettelkasten/_system/registries/SOURCES.md` | `/minder:mem:source-add` (rows); owner (`## Deprecated Sources`) |
| `zettelkasten/3_resources/people/PEOPLE.md` | `/minder:mem:process` (rows + mentions), `/minder:mem:bootstrap`, `/minder:mem:lint` (dedup/audit); tier only via `/minder:mem:resolve-clarifications`, and the `## Removed` retirement section only via `/minder:mem:resolve-clarifications` + owner, per Identity Contract |
| `zettelkasten/1_projects/PROJECTS.md` | `/minder:mem:bootstrap` (candidates); owner; retirement / reclassification rows via `/minder:mem:resolve-clarifications` (the declared obligee of the Identity Contract) |
| `zettelkasten/_system/registries/AUDIENCES.md` (Extensions table only) | `/minder:mem:resolve-clarifications` (appends rows on owner approval); spec sections never edited by hand |
| `zettelkasten/_system/roles/{role-id}/` (every instance dir; the `_`-prefixed engine files are not one) | `role.md` — `/minder:mem:role:add`, `/minder:mem:role:edit`; `state/` — the role itself inside a `/minder:mem:roles` tick; `log.jsonl` — `/minder:mem:roles` only |
| `zettelkasten/_system/state/secrets.enc.json` | `/minder:mem:role:add` (capture, via `roles_secrets.store_secret`). **Committed, encrypted per value** — so a cloud scheduler's fresh clone has it. The key lives only in the scheduler's env (`MINDER_MEMORY_ROLES_KEY`), never in git. The tick decrypts to a file outside the repo and deletes it; never echo a value into a log or a commit |
| `zettelkasten/_system/state/tick-telemetry.jsonl` | `scripts/scheduler/record_tick_telemetry.py`, in the closing step (`close-tick.sh`) of every scheduler tick — append-only, one line per tick, measured from the tick's own transcript. Ticks only; manual skill runs write nothing here |
| `zettelkasten/_system/state/` | append-only logs, candidate buffers, clarifications queue — every skill writes its own files |
| `zettelkasten/_system/views/` | auto-generated by `/minder:mem:regen-constitution`, `/minder:mem:maintain` |

If a task tempts you to hand-edit any owner-data path, **stop and route through the right skill.** The append-only / idempotency / audit-trail guarantees of the engine depend on it. The CLARIFICATIONS queue exists precisely so you do not have to silently decide.

## Engine conventions — non-negotiable when editing engine docs and SKILLs

These are quoted from `_system/docs/CONVENTIONS.md` because they get violated otherwise. They apply to every contributor — friend or maintainer. Engine docs describe **current behaviour**, not history. A reader six months from now sees «how it works now», not «how it evolved».

1. **No version references.** Never write `v4.5`, `Version: 4.7`, `Minder Memory v3` in SKILL headers, descriptions, system docs. Components describe themselves by name. The single exception is `batch-format.md`, where `version: 1.0` IS the content of the spec.
2. **No phase references.** Never write `(Phase 4)`, `Phase 5+`, `per PHASE-4-SDD §Q8`. Phase narratives are git history, not doc content.
3. **No rename or migration history.** Don't write «previously this was called X», «moved from Y to Z», «renamed in vN». The file IS the contract; git log carries narrative.
4. **No personal names, and no verbatim owner utterances, in engine code.** Engine prompts, system docs, SKILL examples use placeholders (`john-doe`, `ivan-petrov`, `<owner>`) or read from `zettelkasten/_system/SOUL.md → ## Identity → Name:` at runtime — and a worked example is WRITTEN, never quoted out of a record: a sentence with no name in it still identifies the person who said it. The personal-data linter (`scripts/check_no_personal_data.py`) blocks PRs on names, via patterns derived from the registries. On utterances it is a **backstop, not a boundary**: it tests every *delimited* span in a shipped file for an exact match in `_records/` / `_sources/`, so it catches a quotation pasted in and misses one paraphrased or written without quotation marks. The rule is on the author; the linter only catches the careless half.
5. **Describe current behaviour.** Default mental check before committing any doc edit: *would this sentence still make sense after the v4.6→v4.7 narrative is forgotten?* If no, rephrase.
6. **Template-spec sync — both files or neither.** Several engine-spec docs ship as `*.template.md` (see `.engine-manifest.yml → template:`). These are **strip-seed** entries: `release_engine.py` renames `X.template.<ext>` → `X.<ext>` when copying to the skeleton (for the full seed-contract — strip-seed vs skill-seed vs layered — read the header comment above `template:` in `.engine-manifest.yml`; the `check_seed_contract.py` gate enforces it at release + CI). `sync_engine.sh` skips template paths so friend's owner-Extensions survive `/minder:mem:update`. Consequence: any **spec-portion edit** to a live file with a `.template.md` sibling MUST be backported to the template in the same change, otherwise friends never receive the spec update. Owner-mutable sections (Extensions tables, populated rows, owner data) naturally diverge — that is by design — but canonical sets, format rules, autofix tables, heuristic descriptions, and example values are spec and must stay byte-identical between live and template. Verify with `diff <live>.md <live>.template.md` before commit. The high-risk files today: `AUDIENCES.md` ↔ `AUDIENCES.template.md`, `DOMAINS.md` ↔ `DOMAINS.template.md`, `INDEX.md` ↔ `INDEX.template.md`, `TAGS.md` ↔ `TAGS.template.md`. CI does not enforce this; the discipline is on the editor.

These rules are aggressive on purpose. Engine docs are read cold by friends with no shared session history; drift here is the largest entropy risk in the system.

## Cross-platform — Windows + macOS + Linux (HARD RULE)

Every engine artifact runs identically on Windows (Git Bash + `python3`), macOS (bash 3.2) and Linux — no exceptions. The rule and its checklist are `zettelkasten/_system/docs/ENGINE_DOCTRINE.md §3.9`; `scripts/check_portability.py` enforces it.

## Where skills are authored

Skills live at `integrations/claude-code/skills/<name>/SKILL.md`. **That is the source of truth.**

The `minder-mem-role*` family shares one subagent definition at `.claude/agents/minder-mem-role.md` — the agent `/minder:mem:roles` spawns per due role. It is the only agent definition the engine ships. The two engine files every role's prompt is assembled from live at `zettelkasten/_system/roles/{_run-frame.md,_minder.md}`; everything else under `_system/roles/` is owner data.

Skills are discovered through two paths:

1. **Project-level (Routines + interactive in repo CWD)** — `.claude/skills/minder-mem-*` symlinks at the repo root point into `integrations/claude-code/skills/<name>/`. Auto-discovered by Claude Code (interactive + Routines) when CWD is inside the repo. SKILL.md sources use repo-relative `zettelkasten/...` paths and need no rendering.

2. **User-level (interactive from any CWD)** — `bash integrations/claude-code/install.sh` renders rules / commands templates (which still use `{{MINDER_MEMORY_BASE}}`) into `integrations/claude-code/built/` (gitignored) and symlinks `~/.claude/{minder-memory,commands,skills,agents}/` so the constitution-capture hook + ambient `/minder:mem:capture-candidate` / `/minder:mem:check-decision` are reachable from sessions opened outside this repo. The skills loop in install.sh is a no-op pass for skills (no placeholder to render); kept for user-level symlink coverage.

**Never edit:**
- `integrations/claude-code/built/**` — generated output of install.sh
- `~/.claude/skills/<name>/SKILL.md` — symlink chain into the repo

After editing a SKILL source, no rebuild is required — both `.claude/skills/` and `~/.claude/skills/` resolve to the same source. After editing a rule or command source, re-run `bash integrations/claude-code/install.sh` (idempotent) to refresh `built/`.

## What moves with an engine change

When engine behaviour changes, what must move with it is listed in `zettelkasten/_system/docs/ENGINE_MAP.md → What moves with an engine change` — open it before closing any engine change, and move every doc it names in the same change. **Two-stage doc edits create drift; one-stage edits prevent it.**

## Release and sync — the gotchas that bite

- **`template:` category strips the `.template` suffix at release.** A file whose
  *name* is load-bearing (e.g. anything protected by the engine-wide
  `*.template.md` processing exclusion) must ship under `engine:` instead —
  engine paths copy verbatim. That is why
  `zettelkasten/_sources/inbox/describe-me/PROFILE.template.md` is listed under
  `engine:`.
- **The update reads the UPSTREAM `.engine-manifest.yml` to decide what to check
  out**, falling back to the local copy only when the remote one cannot be read.
  A path newly added to `engine:` therefore lands on the SAME update that adds
  it — verified end to end by updating a 1.1.3 clone against a 1.2.0 skeleton and
  finding `.claude/hooks/` in place afterwards. `scripts/` is landed earlier
  still: `/minder:mem:update` Step 1.5 and `sync_engine.sh --self-heal` check it
  out FIRST, so the runner, the shared libs and any newly-added migration are
  current before anything reads them — which is why a migration may rely on
  `scripts/` and on itself, both of which are guaranteed, rather than on the
  order the rest of the tree arrives in.
- **`release_engine.py` requires an empty `--target` and never prunes.** Real
  releases go: release to a fresh mktemp dir → `rsync -a` (no `--delete`) onto
  the skeleton clone → manually `git rm` paths removed from the engine set →
  commit. A stale skeleton file removed upstream does NOT propagate to friends
  via sync (checkout never deletes) — that is what `retired:` +
  `scripts/retire_paths.py` are for; declare the removal there.

## Test runner — pytest, not `unittest discover`

CI and local runs use `python -m pytest tests/` from
`zettelkasten/_system/scripts/`. `unittest discover` silently skips
pytest-style function tests (no `TestCase` class), so whole suites never
execute anywhere while the run still reports green. New test files may be
pytest-style; never reintroduce `unittest discover` as the runner.

**Deps** (`zettelkasten/_system/scripts/requirements.txt`): PyYAML, jsonschema
(a hard import-time dependency of `lint_manifest_schema.py` — it `sys.exit(2)`s
on a missing module, which kills test discovery), pytest, and `cryptography`
(imported lazily by the encrypted credential store, so a base with no
credentials neither needs it nor breaks without it).

## Verification — run before finalising engine changes

```bash
# Portability gate — every shipped artifact must behave the same on Windows
# (Git Bash), macOS (bash 3.2) and Linux. CI runs this; engine PRs fail
# otherwise. `--report` lists findings without failing; `--rules` explains each.
python3 scripts/check_portability.py

# Personal-data linter — engine code must not name any specific person.
# CI runs this; engine PRs fail otherwise.
python3 scripts/check_no_personal_data.py

# Python pipeline tests
pytest zettelkasten/_system/scripts/tests/

# Release dry-run — confirms the manifest is consistent and all engine
# paths exist. Run after touching `.engine-manifest.yml` or moving files.
python3 scripts/release_engine.py --target /tmp/skeleton-check --dry-run

# Seed-contract gate — assembles a throwaway skeleton and verifies the seed
# contract (no template leaks, no owner-override/tuning leaks, no double-ship).
# Run after touching `.engine-manifest.yml → template:/seed_skill` or the
# threshold/config seed files. CI runs it too.
python3 scripts/check_seed_contract.py

# Migration-coverage gate — every migration has a suite that executes it, or a
# dated row in the closed allowlist. Run after adding a migration; CI runs it too.
python3 scripts/check_migration_coverage.py

# Retirement gate — every shipped path we deleted is declared in `retired:`,
# so it actually leaves a friend's clone. Needs full git history; refuses on a
# shallow checkout instead of passing. Run after deleting or renaming any
# engine path. CI runs it too.
python3 scripts/check_retirements.py
```

If the change touches a SKILL contract, also bump `integrations/VERSION` (semver). For breaking changes add a migration under `scripts/migrations/NNN-short-slug.sh` (see `scripts/migrations/README.md`).

## Commit / save

- **Engine changes** (engine paths per `.engine-manifest.yml`; `ENGINE_MAP.md → Engine paths`) — normal `git commit` + `git push`. English only, imperative mood, explain WHY not WHAT.
- **Owner-data changes** (records, knowledge, constitution, registries, hubs) — go through `/minder:mem:save`. The skill stages by category, drafts a message, commits and pushes after confirmation.

Never mix engine and owner-data in one commit — the boundary becomes muddled in history and `release_engine.py` cannot extract cleanly.

## Autonomous operation

Several skills run unattended via scheduler prompts (`integrations/claude-code/scheduler-prompts/`):

- `/minder:mem:process` — pre-sync → process → maintain → save (3× per day)
- `/minder:mem:lint` — pre-sync → lint → save (nightly)
- `/minder:mem:maintain` — after-batch integrator; Step 4.5 of the process tick, which
  is its only trigger. It cannot run inside `/minder:mem:process` — the two are
  mutually exclusive on the cross-skill lock
- `/minder:mem:agent-lens --all-due` — pre-sync → lens runs → save (daily; runs the
  `content-synthesis` lens on Mondays)
- `/minder:mem:content --maintain` — pre-sync → draft-maintainer → finalize (weekly,
  Tuesday; the content pipeline's actor)
- `/minder:mem:roles` — pre-sync → run every due role sequentially → finalize (daily,
  07:00). Each role is a subagent with the ordinary tool set; the boundary is
  the post-run diff check in `roles_guard.py`, not a tool cage
- `/minder:mem:sync-data` — pre-work pull on multi-device setups

They follow the cross-skill lock matrix in `SYSTEM_CONFIG.md` and write to append-only logs under `_system/state/log_*.md` — plus, for roles, one line per executed run in `_system/roles/{id}/log.jsonl`. When debugging an autonomous run, **read the relevant log first** — the audit trail is designed to make every decision recoverable without re-running.

When proposing changes to skills that run autonomously, preserve the contract: never block on user input, always surface judgement to `CLARIFICATIONS.md` with a conservative default, never silently mutate owner-curated state.
