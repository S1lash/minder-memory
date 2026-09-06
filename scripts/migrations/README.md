# Engine migrations

Migration scripts run by `scripts/run_migrations.py`, which both
`scripts/sync_engine.sh` and the `/minder:mem:update` skill call after a successful
fetch + checkout. One file per breaking engine change.

## Convention

- Filename: `NNN-short-slug.sh` (zero-padded order). NNN starts at `001`.
- Each script is idempotent. The runner records every attempt in the ledger at
  repo root and never re-runs a migration that succeeded.
- Scripts run from the repo root. They may rewrite files, move paths,
  or print upgrade instructions for the user. They MUST NOT touch
  user-data paths (records, knowledge, registries, SOUL, constitution).
- Keep migrations small and reversible.
- **Declared kind — `structural` vs `heal`.** Every migration states, in a
  header comment on the second line, what its failure means:

  ```bash
  #!/usr/bin/env bash
  # migration-kind: heal
  ```

  **Choose by ONE question: after this migration fails, is CONTINUING the update
  DANGEROUS — would the engine then read or write the wrong place?** Not "is this
  migration important"; every migration is important, and that question yields
  `structural` for all of them.

  - **`structural`** — yes, dangerous. A non-zero exit ABORTS the update and is
    deliberately NOT recorded, so the next update resumes at exactly that
    migration. Conservative default when the header is absent.
  - **`heal`** — no, merely incomplete. A non-zero exit is recorded as
    `partial`, the update CONTINUES, and the migration is retried on the next
    update — so an improved repair shipped later reaches a clone **where it kept
    failing**.

  **Retry follows failure, never improvement.** A migration recorded `applied`
  never runs again, of any kind. So improving a migration reaches only clones
  that have not run it yet: the population that already succeeded is
  unreachable through that file, forever. This is correct — re-running a
  succeeded migration on every update is how a chain becomes unbounded work —
  but it decides where a repair goes, and getting it wrong ships a fix into a
  branch nothing can execute.

  Two ways to reach an already-migrated clone, in order of preference:

  1. **Derive at read time instead of storing.** When the artifact is a VIEW of
     data the clone still holds, have the consumer rebuild it rather than trust
     a file written once. This removes the whole «written before we knew
     better» class rather than one instance, and needs no ledger entry at all
     (`018`'s conversion plans, rebuilt by `/minder:mem:role:add --from-previous`).
  2. **A new migration.** When the artifact is read by a person rather than by
     code, there is no read-time hook to hang the rebuild on, and a new ledger
     entry is the only mechanism. Delegate to the original's producers rather
     than restating them (`020`, which re-runs `018`'s two).

  Worked examples on both sides, because the line is not "does it touch owner
  data":

  | Migration | Kind | Why |
  |---|---|---|
  | `031` harness wiring | structural | after the sync the old skills are gone and the old hot rule dangles; a session that continues imports a dead rule and finds no skill under either name |
  | `032` product rename over the clone | heal | un-run means the old name in files the engine still reads correctly — stale words, not a wrong place |

  The distinction is not stylistic. A repair of historical data used to abort
  the whole update and stay unrecorded, so every future update re-ran it and
  re-aborted at the same point; a friend's clone was unable to update for weeks
  because of one. **A repair of old data must never be able to block a future
  engine update** — and neither may a notice.

  A detection-only migration still exits 0 and prints its recovery command to
  stderr, which `/minder:mem:update` surfaces in its Post-update recovery list. It must
  NOT coerce a failed detector run into a false "all clear" — if the detector
  produces no valid output, say so and point to a manual check.

- **The ledger, not a name list.** `scripts/run_migrations.py` runs the chain and
  records one JSONL line per attempt in `.engine-migrations.jsonl` — name, kind,
  rc, outcome, timestamp, note. A clone carrying the older flat
  `.engine-migrations-applied` has it folded in automatically on first read.
  Never write either file from a migration; the runner owns them.

- **Cross-platform — Windows + macOS + Linux (HARD RULE).** A migration runs on
  EVERY friend's machine, so it MUST work on all three. macOS ships **bash 3.2**
  (no `mapfile`/`readarray`/`declare -A`/`${x^^}`); Windows runs Git Bash. Use
  `python3` for logic; portable commands only (no `md5`/`md5sum` split, use
  `sed -i.bak` not `sed -i`/`sed -i ''`, no `readlink -f`); resolve paths from
  `BASH_SOURCE`/repo-root (never hardcode `/` or `C:\`); invoke helpers via
  `bash`/`python3` (no exec-bit reliance). `.sh` stays LF (`.gitattributes`
  enforces it — a CRLF migration breaks bash on a Windows checkout). Verify with
  `/bin/bash -n <migration>.sh` on macOS before shipping. Full rule:
  `_system/docs/ENGINE_DOCTRINE.md §3.9`.

## Helpers beside a migration

A migration whose logic does not fit in portable bash keeps its python beside it,
named `_NNN_*.py` — the leading underscore is what keeps the runner from globbing
it as a migration of its own (`pending()` globs `*.sh`).

- `_031_harness_wiring.py` — migration `031`'s producer: the Claude Code home
  re-wired for Minder Memory (markers, links, the installer, the upstream
  remote) and the digest that tells the owner what they hold outside the
  repository.
- `_032_minder_memory_rebrand.py` — the rename engine: the one token map and
  path rule that turned the former product name into Minder Memory. Migration
  `032` runs it over the clone; the maintainer ran it over the authoring base
  and the sibling repositories.

## The floor

The chain starts at `031`. A clone older than engine `0.69.0` updates to
`0.69.0` first (`scripts/sync_engine.sh --self-heal --branch release/0.69.0`), then to the
current release; `sync_engine.sh` refuses the direct jump, because the
migrations that shaped a base between those versions are not part of the
current engine.

## When to author one

Whenever an engine change requires friends to do something other than
"pull the new files". Examples:

- A skill is renamed (need to remove the old `~/.claude/skills/foo`
  symlink before re-installing).
- A state file changes shape (new column, renamed field).
- A path moves under `_system/` (needs `git mv` mirrored locally).

## When NOT to author one

- New skill / new doc / additive change — `sync_engine.sh` already
  pulls the new file in. No migration needed.
- Internal refactor of an engine script that doesn't change its
  contract — no migration needed.

## Template

```bash
#!/usr/bin/env bash
# migration-kind: structural
# 001-example-rename.sh
# Brief: explain the breaking change in one sentence.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ... idempotent migration steps here ...

echo "[migration 001] done"
```
