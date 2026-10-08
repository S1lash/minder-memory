# Contributing

Engine improvements — skills, slash commands, scripts, system docs —
are welcome. Personal data layers are not.

## What is "engine"

`.engine-manifest.yml` at the repo root is the source of truth. The
`engine:` and `template:` sections list every path that ships from the
upstream skeleton to friend clones. Anything outside those sections is
your own data and stays in your repo.

What each main engine path is for: `zettelkasten/_system/docs/ENGINE_MAP.md
→ Engine paths`.

Notably **not** engine: `.github/workflows/` is owner-only CI (a
friend's clone stays CI-free by design — engine quality is upstream's
concern), and the repo root `README.md` is the maintainer's own; the
public one ships from `README.template.md`.

Before opening an engine PR, read `.claude/CLAUDE.md` — it codifies
the boundary between engine paths and owner-data paths, the
documentation conventions enforced on every doc edit, and the
verification commands (linter, pytest, release dry-run) that gate
engine changes.

## Workflow

1. Fork the upstream skeleton (the public `minder-memory` repo).
2. Branch off `main` (`feat/<short-slug>` or `fix/<short-slug>`).
3. Make engine changes only — never touch a path outside the manifest.
   A `template:` path is edited **only** for its spec portion (a
   canonical set, a format rule, an example value), never for the
   owner-mutable rows beside it; when a template has a live sibling in
   this repo, both move in the same change or neither does.
4. Run the three gates before opening a PR. CI runs all three, and
   `release_engine.py` runs all three again at release time — the first
   two before it copies anything, the seed-contract gate against the
   assembled skeleton afterwards:

   ```bash
   python3 scripts/check_portability.py      # ENGINE_DOCTRINE §3.9
   python3 scripts/check_no_personal_data.py # no owner identity in engine code
   python3 scripts/check_seed_contract.py    # template / seed declarations
   ```

   The portability gate is the one most likely to stop you, and it is the
   one worth reading the output of: it names the construct, why it breaks,
   and what to write instead. Every rule it enforces already existed in
   `ENGINE_DOCTRINE §3.9` — the gate only makes it executable, because a
   rule enforced by memory alone reaches a friend's Windows machine broken.
5. Bump `integrations/VERSION` (semver). Add a migration under
   `scripts/migrations/NNN-short-slug.sh` if your change is
   breaking — see `scripts/migrations/README.md`, and declare its
   `# migration-kind:` (`structural` or `heal`) in the header.
6. Open a pull request describing the user-visible behaviour change
   and the migration story.

## Style

- Engine docs follow `_system/docs/CONVENTIONS.md` — describe current
  behaviour, no version refs / phase narratives / rename history.
- Engine prompts never hardcode a person's name. When personal
  attribution is needed, read `_system/SOUL.md` `## Identity` `Name:`
  at runtime.
- Tests live under `zettelkasten/_system/scripts/tests/` (pytest).

## What does NOT belong upstream

- Anyone's `_records/`, `_sources/`, PARA notes, constitution
  principles, SOUL/PEOPLE/PROJECTS/TAGS values.
- Examples that name a real person. Use `john-doe` / `ivan-petrov`
  placeholders.
- Personal `~/.claude/` rules or memory files.
- Your migration ledger (`.engine-migrations.jsonl`, and the older flat
  `.engine-migrations-applied` if your clone still carries one).

## Release process (maintainer)

The upstream maintainer authors engine changes in their personal
instance, then runs `scripts/release_engine.py --target <skeleton-tree>`
to publish to the public skeleton. Friends pick up the change via
`/minder:mem:update` (interactive Claude skill — default) or
`scripts/sync_engine.sh` (non-interactive shell, CI / power users).
