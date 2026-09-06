---
name: minder:mem:regen-constitution
description: >
  Regenerate the derived views — CONSTITUTION_INDEX.md,
  constitution-core.md (harness view), INDEX.md, the TAGS.md managed
  zone, and the SOUL.md Values auto-zone. Thin wrapper over
  _system/scripts/regen_all.py. Deterministic, no LLM, idempotent.
  Call after any edit under 0_constitution/ and as the first step of
  every Minder Memory pipeline that reads a derived view.
disable-model-invocation: false
---

# /minder:mem:regen-constitution — Regenerate Derived Views

Orchestrates the Python generators that produce the base's derived
views. Deterministic, runs in ~100 ms on a small tree, and is safe
to invoke from any environment (local Claude Code, scheduler task, friend's
clone after pip install).

**Documentation convention:** при любых edits этого SKILL соблюдай
`_system/docs/CONVENTIONS.md` — файл описывает current behavior без
version/phase/rename-history narratives.

## When to call

Call this skill **as the first step of any pipeline that reads a derived
view**, and **after any manual edit under `0_constitution/`**.

Callers by design:

- `/minder:mem:process` — invokes before Step 1 Context Load (SOUL.md includes the
  auto-rendered Values zone)
- `/minder:mem:maintain` — invokes before thread detection (same reason)
- `/minder:mem:lint` — invokes as pre-scan warm-up
- Owner manually — after editing a principle file, before `git commit`
- Scheduler tasks — as an explicit step in the pipeline

The single rule: **consumers regenerate before reading, every time**.
Cost is negligible (< 200 ms), benefit is that no derived view is ever
stale relative to its source.

## What it does

Runs five generators in order, fail-fast:

1. `gen_constitution_index.py` → `_system/views/CONSTITUTION_INDEX.md` (registry
   table + stats for human browse)
2. `gen_constitution_core.py` → `_system/views/constitution-core.md` (harness
   view; all scopes visible, filtered by `applies_to: claude-code` and
   `status != placeholder`). Users symlink
   `~/.claude/rules/constitution-core.md` to this file once per machine.
3. `render_index.py` → `_system/views/INDEX.md` (surface catalog of the
   knowledge, archive, constitution and hub layers)
4. `render_tags.py` → the `AUTO-GENERATED: tag-registry` managed zone of
   `_system/registries/TAGS.md` (census of the `tags:` axis)
5. `render_soul_values.py` → `_system/SOUL.md` auto-zone between markers
   (the Values section loaded into pipeline system prompts)

If any step fails, subsequent steps are not run. Failure exits non-zero
with the specific script's error on stderr.

If `_system/SOUL.md` does not yet contain the auto-zone markers, step 5 is
**skipped with an info log and exit 0** (not treated as failure). This keeps
the skill usable on a fresh repo before SOUL integration lands. A caller that
genuinely requires the SOUL step asks for a failure with `--strict-soul`.

## Invocation

The skill has no arguments in its default form. For overrides, invoke the
underlying script directly:

Run from the zettelkasten base.

```bash
# Default — auto-detect SOUL marker presence
python3 _system/scripts/regen_all.py

# Strict — fail if SOUL markers are missing (for post-integration sanity)
python3 _system/scripts/regen_all.py --strict-soul

# Dry-run — print what would be written to every derived view
python3 _system/scripts/regen_all.py --dry-run

# Write a drift CLARIFICATION if SOUL auto-zone was hand-edited
python3 _system/scripts/regen_all.py --write-soul-clarification
```

## Multi-environment notes

- All outputs live inside the repo — the skill never writes to `$HOME`.
- `MINDER_MEMORY_BASE` env var can override repo location if running from outside
  the repo's working directory.
- PyYAML is the single external dependency
  (`_system/scripts/requirements.txt`).
- Clone-safe: works identically on any machine that has Python ≥ 3.9 and
  PyYAML installed.

## Invariants preserved

- Python + PyYAML only, no LLM. Mechanical transformations are
  deterministic by design (CONSTITUTION.md §13 invariant #14).
- Atomic writes (temp file + rename) on every destination — never leaves a
  partial file on interrupt.
- Placeholder-status notes are excluded from every derived view
  (CONSTITUTION.md §13 invariant #18).
- SOUL.md hand-written zones outside the auto-markers are never touched —
  `render_soul_values.py` rewrites only the text between the markers.

## Failure modes

| Exit code | Meaning |
|---|---|
| 0 | Every applicable step succeeded — including a base whose SOUL.md has no auto-zone markers yet, where the SOUL step is skipped |
| 1 | A generator raised a schema / parse / IO error; earlier steps may have succeeded (their outputs are valid) |
| 2 | `--strict-soul` was set and SOUL markers are missing |

On non-zero exit, read stderr for the specific script name and line.

## Recovering from an accidental regen

Derived views contain dynamic timestamps. A regen run that produced no
semantic change will still show a small diff on the timestamp lines:

```
_system/views/CONSTITUTION_INDEX.md    | 2 +-  _Generated: line
_system/views/constitution-core.md     | 2 +-  <!-- Generated: ... -->
_system/SOUL.md                        | 2 +-  <!-- Last regenerated: ... -->
```

This is expected, not drift. If the diff is unwanted (the regen was
accidental, or you want the working tree to match HEAD), run:

```bash
git checkout HEAD -- \
    zettelkasten/_system/views/CONSTITUTION_INDEX.md \
    zettelkasten/_system/views/constitution-core.md \
    zettelkasten/_system/views/INDEX.md \
    zettelkasten/_system/registries/TAGS.md \
    zettelkasten/_system/SOUL.md
```

Source files under `0_constitution/` are never modified by regen, so
their state on disk is authoritative; you never need to reset them.
