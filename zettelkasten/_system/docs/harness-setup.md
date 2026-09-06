# Claude rules + cross-project skills — install

Two coupled install requirements per machine so that:

1. The global constitution-capture hook fires in every Claude Code session.
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
| `~/.claude/rules/minder-memory.md` | `integrations/claude-code/built/rules/minder-memory.md` (rendered) |
| `~/.claude/rules/constitution-capture.md` | `zettelkasten/_system/docs/constitution-capture.md` |
| `~/.claude/rules/constitution-core.md` | `zettelkasten/_system/views/constitution-core.md` |
| `~/.claude/rules/communication-baseline.md` | `zettelkasten/_system/docs/communication-baseline.md` |
| `~/.claude/rules/minder-memory-engine-doctrine.md` | `zettelkasten/_system/docs/ENGINE_DOCTRINE.md` |
| `~/.claude/skills/minder-mem-*` (one per skill dir) | `integrations/claude-code/skills/minder-mem-*` (direct, no render step) |
| `~/.claude/commands/minder/mem` (one link for the product's namespace directory; `commands/minder/` itself stays a real directory shared with sibling Minder products) | `integrations/claude-code/built/commands/minder/mem/` (rendered; `recap.md`, `search.md`) |

`built/` is gitignored. The installer renders **rules and commands**
from `integrations/claude-code/{rules,commands}/` into `built/` by
substituting `{{MINDER_MEMORY_BASE}}` with the absolute path to
`<repo>/zettelkasten`. **Skills carry no placeholder** (sources use
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

After install, add the constitution-capture import to `~/.claude/CLAUDE.md`
once if not already present:

```markdown
## Constitution Capture — Global Hook
- @~/.claude/rules/constitution-capture.md
```

## Scheduler / headless environments

The installer is idempotent and non-interactive. In a fresh container:

1. `git clone <your-fork-url>` (or `gh repo create my-minder-memory --template <upstream>`)
2. `pip install -r minder-memory/zettelkasten/_system/scripts/requirements.txt`
3. `bash minder-memory/integrations/claude-code/install.sh`

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

## Why not store directly in `~/.claude/rules/`?

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
4. Re-run `install.sh` — symlinks are picked up automatically (skills/commands by directory listing).
5. For new rules: add a row to the table above and the `@` import in `~/.claude/CLAUDE.md`.
