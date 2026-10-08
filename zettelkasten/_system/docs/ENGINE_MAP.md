# Engine map

Which paths are engine, and which docs move when engine behaviour changes.
`.engine-manifest.yml` is the source of truth for the boundary; this map says
what each engine path is for. Open it when a path's side of the boundary is
unclear, and before closing any engine change.

## Engine paths

Normal code edits land here.

- `integrations/claude-code/{rules,commands,skills}/` — Claude Code prompts and skills (sources)
- `integrations/claude-code/{install.sh,uninstall.sh,SETUP_PROMPT.md,scheduler-prompts/}` — installer + scheduler templates
- `integrations/minder-memory-mcp/` — MCP integration guide
- `integrations/obsidian/` — Obsidian vault config seed (`vault-config/` defaults + the `minder-memory.template.md` dashboard, idempotently seeded to `<vault>/minder-memory.md` by `seed.sh` from `claude-code/install.sh`)
- `scripts/` — release, sync, gates, migrations; `scripts/lib/` holds the shared primitives every one of them uses
- `zettelkasten/_system/docs/` — system spec
- `zettelkasten/_system/scripts/` — python pipeline + tests
- `zettelkasten/_system/registries/{FOLDERS.md,CONCEPT_NAMING.md,CONCEPT_TYPES.md,AGENT_LENSES.md,lenses/}` — engine registries (pure spec; sync upstream-to-downstream)
- `zettelkasten/_system/registries/{AUDIENCES,DOMAINS}.template.md` — seeds for `AUDIENCES.md` / `DOMAINS.md` (spec + owner-mutable Extensions table; ship as templates so owner extensions survive sync)
- `zettelkasten/_system/roles/{_run-frame.md,_minder.md}` — the two engine files every role's prompt is assembled from (run mechanics; base conventions). Everything else under `_system/roles/` is owner data
- `zettelkasten/5_meta/{CONCEPT.md,PROCESSING_PRINCIPLES.md,templates/,starter-pack/}`
- `zettelkasten/5_skills/` — engine quick-reference cards
- `zettelkasten/0_constitution/CONSTITUTION.md` — protocol spec (NOT the `axiom/principle/rule/` subdirs)
- `zettelkasten/{1_projects,2_areas,3_resources,_records}/README.md` — PARA explainers
- `.claude/CLAUDE.md`, `.claude/settings.json` — project-local engine-development guide (`AGENTS.md` is its Codex twin) and permissive command allowlist
- `.claude/skills/` — the canonical skill-discovery tree (symlinks here; `release_engine.py` dereferences them into real files on release, because a git symlink does not survive a Windows clone)
- `.claude/agents/minder-mem-role.md` — the subagent definition the `/minder:mem:roles` tick spawns per due role
- Root meta: `.gitignore`, `.gitattributes`, `LICENSE`, `integrations/VERSION`, `CONTRIBUTING.md`, `README.template.md`, `docs/{onboarding,upstream-sync,scheduling,obsidian,privacy,CHANGELOG,upgrade-1.0.0}.md`

## Docs that move with the engine

When engine behaviour changes, these are the docs that must move with it.
Drift between them is the engine's largest entropy risk.

| File | Purpose |
|---|---|
| `zettelkasten/_system/docs/ENGINE_MAP.md` | This map: engine paths, and the docs that move with engine behaviour |
| `zettelkasten/_system/docs/SYSTEM_CONFIG.md` | System contract: schemas, hard rules, cross-skill lock matrix |
| `zettelkasten/_system/docs/CONVENTIONS.md` | Documentation style; binding on every edit listed in this table |
| `zettelkasten/_system/docs/ENGINE_DOCTRINE.md` | Operating philosophy; imported by `.claude/CLAUDE.md` — loads in this repo only |
| `zettelkasten/_system/docs/ARCHITECTURE.md` | System design as built: git-centric layers, rejected alternatives, the system files the engine maintains |
| `zettelkasten/_system/docs/manifest-schema/v{N}.json` | Canonical JSON Schema for Minder Memory engine manifest (consumer-agnostic). New major = new file alongside; old majors retained for validating old batches |
| `zettelkasten/_system/docs/manifest-schema/README.md` | Reference doc for manifest contract: SemVer evolution rules, per-skill semantics, "what is NOT in the manifest", consumer integration patterns |
| `zettelkasten/_system/docs/manifest-schema/fixtures/` | Per-skill sanitized example manifests; regression test for schema evolution — schema changes MUST keep these validating |
| `zettelkasten/_system/docs/batch-format.md` | Markdown batch-summary format (`{ts}-{skill}.md` next to each JSON manifest); narrative side only — JSON contract canonical lives in `manifest-schema/` |
| `zettelkasten/_system/docs/constitution-capture.md` | In-the-moment capture trigger spec |
| `zettelkasten/_system/docs/communication-baseline.md` | Universal presentation spine — how a result is DELIVERED; hot-loaded into every session (via the managed block) |
| `zettelkasten/_system/docs/advisory-baseline.md` | Universal reasoning spine — how a result is REACHED: objective function, advocate-with-unbiased-instrument, interested-party ledger, criteria provenance + regime test, sweep gate, variance and irreversibility. Hot-loaded beside its sibling. Owner deltas layer on top in their `ai-interaction` principles; the heavy protocol is the owner's on-demand `_system/decision-advisory-playbook.md` |
| `zettelkasten/_system/docs/harness-setup.md` | Harness setup |
| `zettelkasten/5_meta/CONCEPT.md` | Three-layer model; long-form philosophy |
| `zettelkasten/5_meta/PROCESSING_PRINCIPLES.md` | The 8 processing principles |
| `zettelkasten/0_constitution/CONSTITUTION.md` | Constitution protocol spec (axiom / principle / rule schema, scope, evolution ladder) |
| `zettelkasten/_system/registries/FOLDERS.md` | Folder routing rules |
| `zettelkasten/_system/registries/CONCEPT_NAMING.md` | Canonical concept-name format (snake_case ASCII; rules + normalisation algorithm + heuristics) |
| `zettelkasten/_system/registries/AUDIENCES.md` | `audience_tags` privacy whitelist (canonical five + owner extensions + spec) |
| `zettelkasten/_system/registries/AGENT_LENSES.md` | Agent-lens registry + frame contract |
| `zettelkasten/_system/roles/_run-frame.md` | The per-run mechanics handed to every role — allowed writes, credentials, the two-line return |
| `zettelkasten/_system/roles/_minder.md` | How a role uses the base — layer shapes, registries, the inbox-note shape `/minder:mem:process` picks up |
| `zettelkasten/5_skills/CLAUDE_MINDER_MEMORY.md`, `zettelkasten/5_skills/minder-mem-*.md` | Engine quick-reference cards |
| `.engine-manifest.yml` | Engine boundary; what ships to skeleton. Header comment above `template:` is the **SoT for the seed contract** (strip-seed / skill-seed / layered) |
| `scripts/lib/` | Shared engine primitives: `portable` (LF/UTF-8 stdout + file I/O), `manifest` (the single reader of `.engine-manifest.yml`), `migrations` (the ledger + declared kinds), `git.sh` (branch identity, quotepath-safe path listing, MSYS-safe ref access), `tick_identity` (the base and run a scheduler delivery declares in its message — the one home for its keys, writer and reader). A concern that lands here has more than one call site — that is the bar |
| `scripts/scheduler/record_tick_telemetry.py` | The tick odometer: reads the run's own session transcript (plus every sub-agent's) and appends one line of token consumption to `_system/state/tick-telemetry.jsonl`. It exists because a model cannot see its own usage — the only figure in its context is a remaining-budget counter that ignores cache reads and sub-agents entirely, so any self-reported number would be invention. Always exits 0: instrumentation that can abort a tick is worse than no instrumentation, which is why `/minder:mem:lint` A.13 has to watch for it going quiet |
| `zettelkasten/_system/scripts/pipeline_health.py` | The single answer to «when did this pipeline last run», for every pipeline and every role. Takes the MAXIMUM timestamp, never the last line: logs are newest-first but carry an older ascending tail, so a last-line read reported `log_process.md` 68 days stale while it had run that week. Reports `last_in_file_order` alongside so a discrepancy is visible. `global-navigator` calls it instead of parsing prose |
| `scripts/check_portability.py` | Portability gate — makes `ENGINE_DOCTRINE §3.9` executable. Runs in CI and inside `release_engine.py`; a release cannot ship a §3.9 violation. Escapes: inline `portability-ok: <reason>` or a row in `scripts/portability-allowlist.txt` |
| `scripts/manifest_paths.py` | Emits one manifest section as LF-separated lines for a shell caller. Exists so `sync_engine.sh` has no inline `python3 - <<'PY'` heredoc on the boundary — that heredoc printed with a bare `print()`, and python's text-mode stdout writes CRLF on Git Bash, which is what made `/minder:mem:update` silently apply nothing there |
| `scripts/run_migrations.py` | The migration runner. Honours each migration's declared `# migration-kind:` — `structural` failure aborts, `heal` failure is recorded and the update continues. Called by `sync_engine.sh` and by `/minder:mem:update` |
| `scripts/check_migration_coverage.py` | Migration-coverage gate — a migration ships with a suite that EXECUTES it, or a dated row in `scripts/migration-coverage-allowlist.txt`. Coverage is read from the test's syntax tree (class naming the migration, a real `test_*`, a runner that itself shells out), because a `NAME` line beside no test is trivial to write and grep cannot tell them apart. The allowlist's ceiling is a constant in the gate, not a line in the list — a limit a file declares about itself is raised by editing that file. Runs in CI and inside `release_engine.py`. Exists because an untested `heal` that SUCCEEDS at the wrong thing is marked applied and never runs again, on any clone |
| `scripts/check_seed_contract.py` | Seed-contract gate — enforces the contract at release + CI; add a new seed's invariant here if you introduce a new seeding kind |
| `scripts/check_retirements.py` | Retirement gate — proves every shipped path this engine deleted is declared in `retired:`. Runs in CI and inside `release_engine.py`. Exists because no content scan can see it: the absence of a file is not a file, and a half-declared removal is worse than none — the survivors go on importing what was retired, so the update meant to clean the tree is what breaks it. Refuses on a shallow clone rather than reporting clean |
| `scripts/recover_reverted_ticks.py` | The one home for the stale-delivery defect: `detect` (whole-history signature scan in a single `git log --raw` pass), `plan` (reconstruct what the commit should have been and replay the difference onto the tip) and `apply` (write it into the working tree — never commits, never pushes). Detection is a signature; **writing needs a proof** — scheduler provenance, a tree equal to an ancestor's everywhere the commit wrote nothing, the commit's own work on top (which a deliberate revert cannot have), and somebody ELSE's work inside the interval it reverted (which a run rolling back its own output does not have). A commit that declares the base its tree was built on (`scripts/lib/tick_identity.py`) is judged by that base instead: a path put back to its base content while the parent holds something newer is a revert of work the tick never read — proven, whoever produced it — and a base equal to the parent is never an incident, so a declared commit needs no producer inferred from its subject and never reaches `needs_review`. Every candidate gets a verdict rather than silence: `proven` may be written, `needs_review` is handed to the owner for an undeclared commit where a same-tag race and a deliberate self-rollback are indistinguishable in the history, and the rest is reported on stderr only. `identity` names every `[scheduled]` commit after the first declared one that declares nothing usable. Three callers share it: the owner's recovery, migration `035`, and `/minder:mem:lint` A.15. Refuses on a shallow clone and on any target path carrying uncommitted work, because there the repair could not be undone cleanly |
| `scripts/scheduler/_delivery_check.py` | The rail under the delivery fix: nothing may differ from `origin/main` except paths the tick recorded that it staged. Content-level on purpose — a path-level subset test passes as soon as a file appears in the staged set, so a stale tree could erase another tick's hunk inside a file this tick legitimately staged. The surface is read from each committing step's own record (`stage.sh`, and the roles skill for its per-role commits), **never** from the commits being policed: a surface derived from the artifact under suspicion authorises exactly what it exists to catch |
| `scripts/retire_paths.py` | Removes what the manifest lists as `retired:`. A sync copies what upstream HAS and cannot express what it no longer has, so without this a deleted module lives on every clone forever. Runs on every update rather than as a one-off migration, so it converges a clone at any version — including one dark for months |
| `CONTRIBUTING.md` | Contribution rules |
| `docs/onboarding.md`, `docs/upstream-sync.md`, `docs/scheduling.md` | Friend-facing docs |

When you change a SKILL.md, ask: *does this affect anything in the table above?*
If yes, update both in the same change. **Two-stage doc edits create drift;
one-stage edits prevent it.**
