# minder-memory — project guide for Codex

This repo holds two things side-by-side:

1. The **Minder Memory engine** — skills, scripts, system docs, integration tooling. Authored here, released to the public skeleton (`minder-memory`) via `scripts/release_engine.py`, consumed by friends through `/minder:mem:update`.
2. **Owner data** under `zettelkasten/` — records, knowledge notes, constitution, registries, hubs. Owned by the human running this clone.

Different rules apply to each. This file is the project-local contract.

**This repo ships exactly one agent integration, `integrations/claude-code/`, and its project-local config lives at `.claude/`.** Those are the real paths whatever agent is reading this; there is no second tree to look for.

`integrations/claude-code/install.sh` installs the operating philosophy as a global rule for Claude Code only (`~/.claude/rules/minder-memory-engine-doctrine.md`, a symlink to `zettelkasten/_system/docs/ENGINE_DOCTRINE.md`). **Nothing is installed into a Codex home**, so a Codex session does not get it automatically — read it at its repo path before working here. **This file covers what it does not: how to WORK ON THIS REPO.**

## Authority order (top wins on conflict)

1. `zettelkasten/_system/docs/SYSTEM_CONFIG.md` — system contract; hard rules, schemas, lock matrix
2. `zettelkasten/_system/docs/CONVENTIONS.md` — documentation conventions; binding on every edit to engine docs and SKILLs
3. `zettelkasten/_system/docs/ENGINE_DOCTRINE.md` — operating philosophy; cross-skill principles (auto-loaded)
4. This file — project-local engine-development rules
5. Skill `SKILL.md` under `integrations/claude-code/skills/<name>/` — pipeline-specific spec
6. `zettelkasten/_system/SOUL.md` — owner identity calibration

When you find these in conflict, the higher one wins. When a rule is absent everywhere, surface a CLARIFICATION rather than silently choose.

## Engine vs data — the boundary

`.engine-manifest.yml` at the repo root is the **source of truth** for what is engine. Read it before touching any path you're unsure about.

### Engine paths (normal code edits land here)

- `integrations/claude-code/{rules,commands,skills}/` — Claude Code prompts and skills (sources)
- `integrations/claude-code/{install.sh,uninstall.sh,SETUP_PROMPT.md,scheduler-prompts/}` — installer + scheduler templates
- `integrations/minder-memory-mcp/` — MCP integration guide
- `integrations/obsidian/` — Obsidian vault config seed (`vault-config/` defaults + the `minder-memory.template.md` dashboard, idempotently seeded to `<vault>/minder-memory.md` by `seed.sh` from `claude-code/install.sh`)
- `scripts/` — release, sync, gates, migrations; `scripts/lib/` holds the shared primitives every one of them uses
- `zettelkasten/_system/docs/` — system spec
- `zettelkasten/_system/scripts/` — python pipeline + tests
- `zettelkasten/_system/registries/{FOLDERS.md,CONCEPT_NAMING.md,CONCEPT_TYPES.md,AGENT_LENSES.md,lenses/}` — engine registries (pure spec; sync upstream-to-downstream)
- `zettelkasten/_system/registries/{AUDIENCES,DOMAINS}.template.md` — seeds for `AUDIENCES.md` / `DOMAINS.md` (spec + owner-mutable Extensions table; ship as templates so owner extensions survive sync)
- `zettelkasten/5_meta/{CONCEPT.md,PROCESSING_PRINCIPLES.md,templates/,starter-pack/}`
- `zettelkasten/5_skills/` — engine quick-reference cards
- `zettelkasten/0_constitution/CONSTITUTION.md` — protocol spec (NOT the `axiom/principle/rule/` subdirs)
- `zettelkasten/{1_projects,2_areas,3_resources,_records}/README.md` — PARA explainers
- `zettelkasten/_system/roles/{_run-frame.md,_minder.md}` — the two engine files every role's prompt is assembled from (run mechanics; base conventions). Everything else under `_system/roles/` is owner data
- `.claude/CLAUDE.md`, `.claude/settings.json` — project-local engine-development guide and permissive command allowlist
- `.claude/skills/` — the canonical skill-discovery tree (symlinks here; `release_engine.py` dereferences them into real files on release, because a git symlink does not survive a Windows clone)
- `.claude/agents/minder-mem-role.md` — the subagent definition the `/minder:mem:roles` tick spawns per due role
- Root meta: `.gitignore`, `.gitattributes`, `LICENSE`, `integrations/VERSION`, `CONTRIBUTING.md`, `README.template.md`, `docs/{onboarding,upstream-sync,scheduling,obsidian,privacy,CHANGELOG,upgrade-1.0.0}.md`

**This file is in the manifest** and ships to the skeleton beside `.claude/CLAUDE.md`, so a friend's Codex reads the same contract. Keep the two reconciled: they are the same contract for two runtimes, and a rule that reaches one and not the other is worse than no rule. `.github/workflows/` and the repo-root `README.md` are likewise excluded (owner-only CI; the public README ships from `README.template.md`).

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
| `zettelkasten/_system/registries/{TAGS,SOURCES}.md` | `/minder:mem:maintain`, `/minder:mem:lint` |
| `zettelkasten/3_resources/people/PEOPLE.md` | `/minder:mem:process` (rows + mentions), `/minder:mem:bootstrap`, `/minder:mem:lint` (dedup/audit); tier only via `/minder:mem:resolve-clarifications`, and the `## Removed` retirement section only via `/minder:mem:resolve-clarifications` + owner, per Identity Contract |
| `zettelkasten/1_projects/PROJECTS.md` | `/minder:mem:bootstrap` (candidates); owner; retirement / reclassification rows via `/minder:mem:resolve-clarifications` (the declared obligee of the Identity Contract) |
| `zettelkasten/_system/registries/AUDIENCES.md` (Extensions table only) | `/minder:mem:resolve-clarifications` (appends rows on owner approval); spec sections never edited by hand |
| `zettelkasten/_system/roles/{role-id}/` (every instance dir; the `_`-prefixed engine files are not one) | `role.md` — `/minder:mem:role:add`, `/minder:mem:role:edit`; `state/` — the role itself inside a `/minder:mem:roles` tick; `log.jsonl` — `/minder:mem:roles` only |
| `zettelkasten/_system/state/secrets.enc.json` | `/minder:mem:role:add` (capture, via `roles_secrets.store_secret`). **Committed, encrypted per value** — so a cloud scheduler's fresh clone has it. The key lives only in the scheduler's env (`MINDER_MEMORY_ROLES_KEY`), never in git. The tick decrypts to a file outside the repo and deletes it; never echo a value into a log or a commit |
| `zettelkasten/_system/state/tick-telemetry.jsonl` | `scripts/scheduler/record_tick_telemetry.py`, at Step 4.9 of every scheduler tick — append-only, one line per tick, measured from the tick's own transcript. Ticks only; manual skill runs write nothing here |
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

**Every engine artifact MUST work on all three platforms friends run — no exceptions, ever.** Migrations, features, scripts, commands, hooks, paths, symlinks, doc instructions: anything the engine ships. A friend on Windows runs Git Bash + `python3`; a friend on macOS runs the system shell (**bash 3.2** — old) + `python3`. An artifact that only works on the author's Mac is a silent breakage that surfaces months later as "it doesn't work for me." This is non-negotiable and applies to every edit.

- **Shell must be bash-3.2-safe AND Git-Bash-safe.** macOS ships bash 3.2 — NO `mapfile`/`readarray`, NO associative arrays (`declare -A`), NO `${var^^}`/`${var,,}`. Prefer `python3` for any non-trivial logic. Portable commands only: no `md5`(mac)/`md5sum`(gnu) split, no `sed -i ''`(mac) vs `sed -i`(gnu) — use `sed -i.bak`, no `readlink -f`/`stat -f`/`stat -c`/`grep -P`. Invoke scripts via `bash x` / `python3 x` — never rely on the executable bit (Windows has none).
- **Line endings = LF, enforced by `.gitattributes`.** A CRLF `.sh`/`.py` (the Windows checkout default) breaks bash and python. `.gitattributes` at repo root forces LF; keep it shipped (it is in `.engine-manifest.yml`).
- **Paths portable.** Python: `pathlib`/`os.path`, never hardcode `/` or `C:\`; resolve from repo root (`git rev-parse` / `BASH_SOURCE`), never an absolute path.
- **Parity in lockstep.** A shell mechanism that has a Windows-equivalent (e.g. a future `install.ps1` beside `install.sh`) is edited in the SAME change, or the limitation is stated explicitly.
- **Readiness test before finalising:** «will this run **identically** on a friend's Windows machine and on a plain macOS bash 3.2?» "It works on my Mac" is NOT the bar. If unsure — verify (`/bin/bash -n script.sh` on macOS proves bash-3.2 syntax; check for CRLF; grep for the banned commands above).

The canonical statement of this rule lives in `_system/docs/ENGINE_DOCTRINE.md §3.9` (auto-loaded into every session); this section is its contributor-facing checklist.

## Where skills are authored

Skills live at `integrations/claude-code/skills/<name>/SKILL.md`. **That is the source of truth.** The full set lives under that path:

```
integrations/claude-code/skills/
  minder-mem-bootstrap/        minder-mem-process/         minder-mem-maintain/
  minder-mem-lint/             minder-mem-agent-lens/      minder-mem-agent-lens-add/
  minder-mem-capture-candidate/ minder-mem-content/        minder-mem-check-decision/
  minder-mem-regen-constitution/ minder-mem-resolve-clarifications/
  minder-mem-save/             minder-mem-sync-data/       minder-mem-source-add/
  minder-mem-update/           minder-mem-roles/           minder-mem-role-add/
  minder-mem-role-edit/        minder-mem-role-list/       minder-mem-role-ask/
```

The `minder-mem-role*` family shares one subagent definition at `.claude/agents/minder-mem-role.md` — the agent `/minder:mem:roles` spawns per due role. It is the only agent definition the engine ships. The two engine files every role's prompt is assembled from live at `zettelkasten/_system/roles/{_run-frame.md,_minder.md}`; everything else under `_system/roles/` is owner data.

Skills are discovered through two paths:

1. **Project-level (Routines + interactive in repo CWD)** — `.claude/skills/minder-mem-*` symlinks at the repo root point into `integrations/claude-code/skills/<name>/`. Auto-discovered by Claude Code (interactive + Routines) when CWD is inside the repo. SKILL.md sources use repo-relative `zettelkasten/...` paths and need no rendering.

2. **User-level (interactive from any CWD)** — `bash integrations/claude-code/install.sh` renders rules / commands templates (which still use `{{MINDER_MEMORY_BASE}}`) into `integrations/claude-code/built/` (gitignored) and symlinks `~/.claude/{rules,commands,skills}/` so the constitution-capture hook + ambient `/minder:mem:capture-candidate` / `/minder:mem:check-decision` are reachable from sessions opened outside this repo. The skills loop in install.sh is a no-op pass for skills (no placeholder to render); kept for user-level symlink coverage.

**Never edit:**
- `integrations/claude-code/built/**` — generated output of install.sh
- `~/.claude/skills/<name>/SKILL.md` — symlink chain into the repo

After editing a SKILL source, no rebuild is required — both `.claude/skills/` and `~/.claude/skills/` resolve to the same source. After editing a rule or command source, re-run `bash integrations/claude-code/install.sh` (idempotent) to refresh `built/`.

## Authoritative docs to keep current

When engine behaviour changes, these are the docs that must move with it. Drift between them is the engine's largest entropy risk.

| File | Purpose |
|---|---|
| `zettelkasten/_system/docs/SYSTEM_CONFIG.md` | System contract: schemas, hard rules, cross-skill lock matrix |
| `zettelkasten/_system/docs/CONVENTIONS.md` | Documentation style; binding on every edit listed in this table |
| `zettelkasten/_system/docs/ENGINE_DOCTRINE.md` | Operating philosophy; auto-loaded into every session via `~/.claude/rules/minder-memory-engine-doctrine.md` |
| `zettelkasten/_system/docs/ARCHITECTURE.md` | System design as built: git-centric layers, rejected alternatives, the system files the engine maintains |
| `zettelkasten/_system/docs/manifest-schema/v{N}.json` | Canonical JSON Schema for Minder Memory engine manifest (consumer-agnostic). New major = new file alongside; old majors retained for validating old batches |
| `zettelkasten/_system/docs/manifest-schema/README.md` | Reference doc for manifest contract: SemVer evolution rules, per-skill semantics, "what is NOT in the manifest", consumer integration patterns |
| `zettelkasten/_system/docs/manifest-schema/fixtures/` | Per-skill sanitized example manifests; regression test for schema evolution — schema changes MUST keep these validating |
| `zettelkasten/_system/docs/batch-format.md` | Markdown batch-summary format (`{ts}-{skill}.md` next to each JSON manifest); narrative side only — JSON contract canonical lives in `manifest-schema/` |
| `zettelkasten/_system/docs/constitution-capture.md` | In-the-moment capture trigger spec |
| `zettelkasten/_system/docs/harness-setup.md` | Harness setup |
| `zettelkasten/5_meta/CONCEPT.md` | Three-layer model; long-form philosophy |
| `zettelkasten/5_meta/PROCESSING_PRINCIPLES.md` | The 8 processing principles |
| `zettelkasten/0_constitution/CONSTITUTION.md` | Constitution protocol spec (axiom / principle / rule schema, scope, evolution ladder) |
| `zettelkasten/_system/registries/FOLDERS.md` | Folder routing rules |
| `zettelkasten/_system/registries/CONCEPT_NAMING.md` | Canonical concept-name format (snake_case ASCII; rules + normalisation algorithm + heuristics) |
| `zettelkasten/_system/registries/AUDIENCES.md` | `audience_tags` privacy whitelist (canonical five + owner extensions + spec) |
| `zettelkasten/_system/registries/AGENT_LENSES.md` | Agent-lens registry + frame contract |
| `zettelkasten/_system/docs/communication-baseline.md` | Universal presentation spine — how a result is DELIVERED; hot-loaded into every session (symlinked to `~/.claude/rules/`) |
| `zettelkasten/_system/docs/advisory-baseline.md` | Universal reasoning spine — how a result is REACHED: objective function, advocate-with-unbiased-instrument, interested-party ledger, criteria provenance + regime test, sweep gate, variance and irreversibility. Hot-loaded beside its sibling. Owner deltas layer on top in their `ai-interaction` principles; the heavy protocol is the owner's on-demand `_system/decision-advisory-playbook.md` |
| `zettelkasten/_system/roles/_run-frame.md` | The per-run mechanics handed to every role — allowed writes, credentials, the two-line return |
| `zettelkasten/_system/roles/_minder.md` | How a role uses the base — layer shapes, registries, the inbox-note shape `/minder:mem:process` picks up |
| `zettelkasten/5_skills/CLAUDE_MINDER_MEMORY.md`, `zettelkasten/5_skills/minder-mem-*.md` | Engine quick-reference cards |
| `scripts/lib/` | Shared engine primitives: `portable` (LF/UTF-8 stdout + file I/O), `manifest` (the single reader of `.engine-manifest.yml`), `migrations` (the ledger + declared kinds), `git.sh` (branch identity, quotepath-safe path listing, MSYS-safe ref access). A concern lands here when it has more than one call site — that is the bar |
| `scripts/scheduler/record_tick_telemetry.py` | The tick odometer: reads the run's own session transcript (plus every sub-agent's) and appends one line of token consumption to `_system/state/tick-telemetry.jsonl`. It exists because a model cannot see its own usage — the only figure in its context is a remaining-budget counter that ignores cache reads and sub-agents entirely, so any self-reported number would be invention. Always exits 0: instrumentation that can abort a tick is worse than no instrumentation, which is why `/minder:mem:lint` A.13 has to watch for it going quiet |
| `zettelkasten/_system/scripts/pipeline_health.py` | The single answer to «when did this pipeline last run», for every pipeline and every role. Takes the MAXIMUM timestamp, never the last line: logs are newest-first but carry an older ascending tail, so a last-line read reported `log_process.md` 68 days stale while it had run that week. Reports `last_in_file_order` alongside so a discrepancy is visible. `global-navigator` calls it instead of parsing prose |
| `scripts/check_portability.py` | Portability gate — makes `ENGINE_DOCTRINE §3.9` executable. Runs in CI and inside `release_engine.py`; a release cannot ship a §3.9 violation. Escapes: inline `portability-ok: <reason>` or a row in `scripts/portability-allowlist.txt` |
| `scripts/manifest_paths.py` | Emits one manifest section as LF-separated lines for a shell caller. Exists so `sync_engine.sh` has no inline `python3 - <<'PY'` heredoc on the boundary — that heredoc printed with a bare `print()`, and python's text-mode stdout writes CRLF on Git Bash, which is what made `/minder:mem:update` silently apply nothing there |
| `scripts/run_migrations.py` | The migration runner. Honours each migration's declared `# migration-kind:` — a `structural` failure aborts, a `heal` failure is recorded and the update continues. Called by `sync_engine.sh` and by `/minder:mem:update` |
| `scripts/check_migration_coverage.py` | Migration-coverage gate — a migration ships with a suite that EXECUTES it, or a dated row in `scripts/migration-coverage-allowlist.txt`. Coverage is read from the test's syntax tree (class naming the migration, a real `test_*`, a runner that itself shells out), because a `NAME` line beside no test is trivial to write and grep cannot tell them apart. The allowlist's ceiling is a constant in the gate, not a line in the list — a limit a file declares about itself is raised by editing that file. Runs in CI and inside `release_engine.py`. Exists because an untested `heal` that SUCCEEDS at the wrong thing is marked applied and never runs again, on any clone |
| `scripts/check_seed_contract.py` | Seed-contract gate — enforces the contract at release + CI; add a new seed's invariant here if you introduce a new seeding kind |
| `scripts/check_retirements.py` | Retirement gate — proves every shipped path this engine deleted is declared in `retired:`. Runs in CI and inside `release_engine.py`. Exists because no content scan can see it: the absence of a file is not a file, and a half-declared removal is worse than none — the survivors go on importing what was retired, so the update meant to clean the tree is what breaks it. Refuses on a shallow clone rather than reporting clean |
| `scripts/retire_paths.py` | Removes what the manifest lists as `retired:`. A sync copies what upstream HAS and cannot express what it no longer has, so without this a deleted module lives on every clone forever. Runs on every update rather than as a one-off migration, so it converges a clone at any version — including one dark for months |
| `.engine-manifest.yml` | Engine boundary; what ships to skeleton. Header comment above `template:` is the **SoT for the seed contract** (strip-seed / skill-seed / layered) |
| `CONTRIBUTING.md` | Contribution rules |
| `docs/onboarding.md`, `docs/upstream-sync.md`, `docs/scheduling.md` | Friend-facing docs |

When you change a SKILL.md, ask: *does this affect anything in the table above?* If yes, update both in the same change. **Two-stage doc edits create drift; one-stage edits prevent it.**

## Release and sync — the gotchas that bite

- **`template:` category strips the `.template` suffix at release.** A file whose
  *name* is load-bearing (e.g. anything protected by the engine-wide
  `*.template.md` processing exclusion) must ship under `engine:` instead —
  engine paths copy verbatim. That is why
  `zettelkasten/_sources/inbox/describe-me/PROFILE.template.md` is listed under
  `engine:`.
- **The update reads the LOCAL `.engine-manifest.yml` to decide what to check
  out.** A path newly added to `engine:` therefore reaches friends one
  `/minder:mem:update` cycle late: run N lands the new manifest, run N+1 checks
  out the path it lists. `scripts/` is the exception — `/minder:mem:update`
  Step 1.5 and `sync_engine.sh --self-heal` check it out FIRST, so the runner,
  the shared libs and any newly-added migration are always current within the
  same run. Design a migration to rely on `scripts/` and on itself being
  current, but NOT on a newly-listed engine file outside `scripts/` being
  present yet.
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

- **Engine changes** (paths in the engine table above) — normal `git commit` + `git push`. English only, imperative mood, explain WHY not WHAT.
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
  07:00). Each role is a subagent with the ordinary tool set; the boundary is the
  post-run diff check in `roles_guard.py`, not a tool cage
- `/minder:mem:sync-data` — pre-work pull on multi-device setups

They follow the cross-skill lock matrix in `SYSTEM_CONFIG.md` and write to append-only logs under `_system/state/log_*.md` — plus, for roles, one line per executed run in `_system/roles/{id}/log.jsonl`. When debugging an autonomous run, **read the relevant log first** — the audit trail is designed to make every decision recoverable without re-running.

When proposing changes to skills that run autonomously, preserve the contract: never block on user input, always surface judgement to `CLARIFICATIONS.md` with a conservative default, never silently mutate owner-curated state.
