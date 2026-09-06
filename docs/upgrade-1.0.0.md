# Upgrade to 1.0.0 — the product is Minder Memory

<!-- minder-memory-rebrand: keep-legacy-tokens — this checklist names the former forms on purpose: they are what it removes -->

The engine's skills, rule, variables and files are named Minder Memory from
1.0.0. The update carries most of it by itself — migration 031 re-wires the
Claude Code home, migration 032 renames the clone — but some of what an owner
holds lives outside the repository, where no migration can reach: a scheduler's
environment, a routine's stored prompt, a shell alias, a connector. This is the
list `/minder:mem:update` walks after the sync, item by item, and the list an
owner can walk by hand.

Each item says what the assistant does on its own, what it needs the owner
for, and how it proves the item is closed. Nothing here is optional: an item
left open is a silent failure — a rule that stops loading, a role that cannot
decrypt, a tick that dies at its first step — and none of them announces itself.

## What the update already did (verify, do not redo)

| # | Surface | Proof it landed |
|---|---|---|
| 1 | Skills answer to `/minder:mem:<name>` | `ls .claude/skills/` lists only `minder-mem-*`; `ls ~/.claude/skills/ \| grep minder-mem` lists twenty; nothing named `ztn-*` remains in either place |
| 2 | Commands `/minder:mem:recap`, `/minder:mem:search` | `~/.claude/commands/minder/mem/{recap,search}.md` resolve |
| 3 | Hot rule and doctrine | `~/.claude/rules/minder-memory.md` and `~/.claude/rules/minder-memory-engine-doctrine.md` resolve; `~/.claude/rules/ztn.md` and `ztn-engine-doctrine.md` are gone |
| 4 | Managed block in `~/.claude/CLAUDE.md` | exactly one block between `<!-- MINDER-MEMORY BEGIN` and `<!-- MINDER-MEMORY END -->`, importing `@~/.claude/rules/minder-memory.md`; no `MINDER-ZTN` marker anywhere in the file |
| 5 | Role agent | `~/.claude/agents/minder-mem-role.md` resolves |
| 6 | Upstream remote | `git remote get-url upstream` ends in `/minder-memory.git` (or `/minder-memory`). This is the ONLY remote the update touches — the remote the engine syncs from. Every other remote is yours and is left exactly as you named it, even when it carries the former name |
| 7 | The clone's own files | `git grep -il ztn -- . ':!zettelkasten/_sources' ':!docs/CHANGELOG.md' ':!zettelkasten/5_meta/DECISION_LOG.md' ':!scripts/migrations' ':!scripts/check_update.py' ':!zettelkasten/_system/scripts/tests' ':!integrations/claude-code/rules/minder-memory.md' ':!.engine-manifest.yml' ':!integrations/obsidian/seed.sh' ':!platform' ':!docs/upgrade-1.0.0.md' ':!zettelkasten/5_meta/help/CHANGELOG.md'` prints nothing — the excluded places are the alias list, the two history documents (and the vault's derived copy of the changelog), the migration and its tests plus the post-update check `scripts/check_update.py` (whose inputs — and whose subject — are the former form), the manifest's `retired:` rows and the dashboard chain in `seed.sh` (former names by definition), and the maintainer's design records. `_sources/` is excluded because a transcript is evidence of what was said — the one file the sync does rewrite in there is the engine-shipped template under `_sources/inbox/describe-me/`, which is engine, not a recording of yours. The proof is that it prints nothing except lines that name your own repository or folder (`minder-ztn-<something>`) — those are kept on purpose, and `scripts/check_update.py` discounts them together with the rename's two opt-outs: a line ending `rebrand:keep`, and anything inside a file carrying `minder-memory-rebrand: keep-legacy-tokens`. Both say the former spelling is the point of the line |
| 8 | Vault dashboard | `zettelkasten/minder-memory.md` exists with the owner's edits; `minder-ztn.md` does not |
| 9 | Engine version | `cat integrations/VERSION` → `1.0.0` |

A row that fails: re-run `bash integrations/claude-code/install.sh` for rows
1–5; `python3 scripts/migrations/_032_minder_memory_rebrand.py --root .` for
rows 7–8; `git remote set-url upstream <new url>` for row 6.

## What lives outside the repository (the assistant does it, the owner confirms)

| # | Surface | What changes | How the assistant does it | Proof |
|---|---|---|---|---|
| 10 | Scheduler routines — environment | the variable `ZTN_ROLES_KEY` is renamed to `MINDER_MEMORY_ROLES_KEY`, same value; any `ZTN_BASE` / `MINDER_ZTN_BASE` → `MINDER_MEMORY_BASE` | Claude Code cloud routines: list them (`RemoteTrigger list`), and for each routine whose environment carries a former name, send the routine back with the key renamed and everything else unchanged — the value is never printed, logged or quoted. Local cron / launchd / GitHub Actions: the assistant names the file, the line number and the variable NAME to change and waits for the owner — it never prints the line itself, because the line holds the value | reading each routine back shows the new key and no former one; the next roles tick decrypts (`_system/roles/<id>/log.jsonl` gains a run with `outcome: ok` and no `credential` error) |
| 11 | Scheduler routines — prompt | a routine that holds a PASTED prompt body says `/ztn:…`; it must say `/minder:mem:…` | exactly the routine reconciliation of `/minder:mem:update` Step 7.1 — classify by content, replace a pasted body with the current file, carry an owner line the file lacks verbatim, touch nothing else; that step is the one home of the procedure | reading each routine back shows no `/ztn:` and no `ztn-`; the next tick of each routine finishes without «Unknown skill» |
| 12 | Shell aliases and profiles | an alias that `cd`s into the clone or exports a former variable | the assistant greps `~/.zshrc`, `~/.bashrc`, `~/.zprofile`, `~/.profile` for `ztn`, `ZTN_` and `MINDER_ZTN` and shows each matching line with its replacement — with everything after an `=` replaced by `…`, because an `export` line holds the value; the owner applies (their shell profile is theirs) | the grep prints nothing except an alias the owner keeps on purpose (`alias ztn=…` as a spoken shortcut is fine — its TARGET must be current) |
| 13 | Other agent runtimes | Codex `~/.codex/config.toml`, Cursor, any runtime that registered the clone's path or the former variable | same grep-show-apply | grep prints nothing |
| 14 | MCP connector | a connector named after the former product keeps working under its configured name; a new install names it `minder-memory` | the assistant says so; renaming is the owner's UI action, if they want it | — |
| 15 | Collectors and other producers into the inbox | a collector's config that holds a former variable name. The repository name it pushes to is unchanged (item 16), so nothing there needs touching | the assistant lists what it can see (`~/.minder-*/config.json`, launchd plists); the owner applies on any machine or server it cannot see | the next collector run lands in `_sources/inbox/` as before |
| 15a | A name of yours an earlier release renamed | nothing automatic. If you updated through 1.0.0 before 1.0.2, the rename map of that release could not yet tell the product from its owner, and a folder or repository of yours may have been rewritten to a path that does not exist | migration `033` raises it as a clarification naming the file, the line, the text now and the text from before the rename. Nothing is rewritten: only you know whether the directory on this machine still carries its original name | the clarification is resolved — you restored whichever spelling matches the directory as it actually is, or dismissed it |
| 16 | Repository names | nothing. The owner's own repository, clone folder and remotes keep whatever names they have | Renaming them is optional and NOT suggested. GitHub's redirect from a former repository name is permanent, so nothing breaks by leaving it — while renaming drags a list with it: a cloud routine's repository source, every inbox integration that pushes into `_sources/inbox/` (Zapier, Plaud and anything else), every collector's config, every other clone, and the keys under `~/.claude.json`. The assistant states this once and moves on; it acts only if the owner asks | — (nothing to close) |

## Then

Open a new Claude Code session: the re-wired rules load only in a session
started after the update. Say «найди в Minder Memory …» — and «найди в ZTN …»
still works, because the former name is a spoken alias in the hot rule and
stays one.
