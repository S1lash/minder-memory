# Claude Code wiring — what the installer puts into `~/.claude`

What every machine needs so that:

1. The engine's global files — the Minder Memory rule, the constitution-capture
   hook, the constitution core and the two baselines — load into every Claude
   Code session, and the engine doctrine into every session in this repository.
2. The skills the hook invokes (`/minder:mem:capture-candidate`,
   `/minder:mem:check-decision`, `/minder:mem:regen-constitution`) and the ambient Minder Memory
   commands (`/minder:mem:search`, `/minder:mem:recap`) are discoverable outside this
   repo too (work-project sessions, HQ sessions, scheduler).

All install steps are automated by `integrations/claude-code/install.sh`
in the repo root. The script is idempotent and reads the absolute repo
path automatically — no manual env vars to set.

## What the installer does

The installer creates symlinks from `$HOME/.claude/` into the repo so
that the source stays version-controlled here while each machine sees a
stable local path:

| Symlink | Repo source |
|---|---|
| `~/.claude/minder-memory/minder-memory.md` | `integrations/claude-code/built/rules/minder-memory.md` (rendered) |
| `~/.claude/minder-memory/constitution-capture.md` | `zettelkasten/_system/docs/constitution-capture.md` |
| `~/.claude/minder-memory/communication-baseline.md` | `zettelkasten/_system/docs/communication-baseline.md` |
| `~/.claude/minder-memory/advisory-baseline.md` | `zettelkasten/_system/docs/advisory-baseline.md` |
| `~/.claude/minder-memory/constitution-core.md` | `zettelkasten/_system/views/constitution-core.md` |
| `~/.claude/skills/minder-mem-*` (one per skill dir) | `integrations/claude-code/skills/minder-mem-*` (direct, no render step) |
| `~/.claude/commands/minder/mem` (one link for the product's namespace directory; `commands/minder/` itself stays a real directory shared with sibling Minder products) | `integrations/claude-code/built/commands/minder/mem/` (rendered; `recap.md`, `search.md`) |
| `~/.claude/agents/minder-mem-role.md` | `.claude/agents/minder-mem-role.md` |

### One mechanism for what loads into every session

`~/.claude/minder-memory/` is a directory Claude Code does **not** load by
itself. Each file in it reaches a session through an `@`-import in the
managed block the installer writes into `~/.claude/CLAUDE.md`:

```markdown
<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->
## Zettelkasten (Minder Memory) — Personal Knowledge Base
- @~/.claude/minder-memory/minder-memory.md
…one heading and one import per file in the table above…
<!-- MINDER-MEMORY END -->
```

So the block is the complete list of the files the engine loads into every
session outside this repository (skills, commands and the role agent are
discovered, not loaded). The links and the block are generated from one
table at the top of `install.sh` (`HOT_FILES`); neither is written by hand.
Nothing of the engine's goes into `~/.claude/rules/`, which Claude Code loads
on its own: a file there would load in every session on the machine beside
the block, whether the block lists it or not. The installer removes the
engine's retired links there — by the exact names `lib/ownership.py` declares
(`ENGINE_RETIRED_HARNESS`), and only when the link points into this
repository; a link into another clone is that clone's installer's to remove. The post-update check (`scripts/check_update.py`, probe
`rules-dir-clean`) fails while one remains.

The engine doctrine (`_system/docs/ENGINE_DOCTRINE.md`) is not global. The
repository's `.claude/CLAUDE.md` imports it, so it loads in every session
started at the repository root or under `zettelkasten/` — interactive, a
cloud routine's fresh clone, a role's subagent — and in no other session on
the machine. A session started in another repository subdirectory sees the
import as external: interactively Claude Code asks once, headless it skips
it. Skills that bind on the doctrine also read it in their own Step 1.

Install and uninstall take one lock per Claude Code home
(`scripts/lib/install_lock.sh`), so a manual run and an update's migration —
or two clones sharing one home — never interleave their writes.

`built/` is gitignored. The installer renders **rules and commands**
from `integrations/claude-code/{rules,commands}/` into `built/` by
substituting `{{MINDER_MEMORY_BASE}}` with the absolute path to
`<repo>/zettelkasten`. It renders into a staging directory and swaps it in
only when complete, so the links of the current wiring never point at a
half-rendered tree. **Skills carry no placeholder** (sources use
repo-relative `zettelkasten/...` paths) — they are NOT rendered, and
`~/.claude/skills/minder-mem-*` symlinks point directly at the source tree.
Re-running the installer (after `git pull`, after moving the repo)
refreshes `built/` and rewrites symlinks in place.

### Two parallel discovery paths

Skills are reached through **two independent symlink layers**, both
pointing at the same source:

- **Project-level** (`.claude/skills/minder-mem-*` at the repo root, committed
  to git) — required for cloud Routines, since Routines clone the repo
  fresh and only look at this canonical path. Active when Claude Code
  CWD is inside the repo.
- **User-level** (`~/.claude/skills/minder-mem-*`, created by `install.sh`) —
  active from any CWD. Lets ambient skills like `/minder:mem:capture-candidate`
  and `/minder:mem:check-decision` reach sessions opened from work projects.

When CWD is inside the repo, both layers load simultaneously; Claude
Code dedupes by skill name. When CWD is outside, only the user-level
layer loads.

## Install (per machine)

```bash
cd <wherever-you-cloned>/minder-memory
bash integrations/claude-code/install.sh
```

The installer writes the managed block itself; nothing is added to
`~/.claude/CLAUDE.md` by hand.

## Scheduler / headless environments

The installer is idempotent and non-interactive. In a fresh container:

1. `git clone <your-fork-url>` (or `gh repo create my-minder-memory --template <upstream>`)
2. `pip install -r minder-memory/zettelkasten/_system/scripts/requirements.txt`
3. `bash minder-memory/integrations/claude-code/install.sh`

A cloud routine needs none of this for the doctrine and the skills: both
reach it from the clone (`.claude/CLAUDE.md`, `.claude/skills/`).

## Why `built/` for rules + commands but not skills

- **Rules and commands** still need machine-portable absolute paths,
  because they reference `{{MINDER_MEMORY_BASE}}` for things the user-
  level layer must resolve from any CWD. `built/` is the rendered
  output (gitignored, machine-local); symlinks point to it.
- **Skills** use repo-relative `zettelkasten/...` paths because (a) the
  same source must be discoverable by cloud
  Routines via committed `.claude/skills/` symlinks at the repo root,
  and (b) all engine pipeline skills (process / lint / agent-lens /
  bootstrap / etc.) inherently run inside the repo CWD, so the
  relative paths always resolve. No render step needed; user-level
  symlinks land directly on the source.

## Why symlinks into the repo rather than files under `~/.claude/`?

- That path is outside the repo — updates cannot be tracked in git.
- Fresh machines and scheduler containers do not have it populated.
- Another user cloning the project would not get the hook.

Storing in the repo + symlinking + rendering keeps three properties:
version control, stable local path, and machine-portable paths.

## Add a new rule, command, or skill

1. Drop the new file into the right `integrations/claude-code/{rules,commands,skills}/` subdir.
2. **Rules / commands:** use `{{MINDER_MEMORY_BASE}}` for any reference to the data root — install.sh substitutes it during render.
   **Skills:** use repo-relative `zettelkasten/...` paths — no placeholder, no render step.
3. **For a new skill:** add a committed symlink at `.claude/skills/<name> → ../../integrations/claude-code/skills/<name>` so cloud Routines discover it.
4. **For a new global file** (a rule, or a doc every session must carry): add one row to `HOT_FILES` in `install.sh` — the link, the block import and the post-update check (`ownership.engine_global_files`) all follow from it — and a row to the table above. A rule under `integrations/claude-code/rules/` without a row is rendered and never loaded; `test_install_hot_wiring.py` fails on it. Keep it short: a global file is paid for in every session on the machine, work sessions included.
5. Re-run `install.sh` — skills and commands are picked up by directory listing.
