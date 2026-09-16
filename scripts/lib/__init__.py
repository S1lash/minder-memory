"""Shared primitives for engine tooling under `scripts/`.

Importable as `lib.<module>` from any script whose directory tree puts
`scripts/` on `sys.path` — that is the case automatically for
`python3 scripts/<name>.py`, and explicitly via a `sys.path.insert` for the
helpers under `scripts/scheduler/`.

Modules here own a cross-cutting concern that would otherwise be re-derived at
every call site:

- `portable`  — LF/UTF-8 stdout and file I/O that behaves the same on Windows
- `manifest`  — the single reader of `.engine-manifest.yml`
- `migrations` — the migration ledger: what ran, with what outcome
- `tick_identity` — what a scheduler delivery declares about itself: the base its
  tree was built on, and its run id

Deliberately NOT here: a python twin of `lib/git.sh`. The engine's python code
reaches git in exactly two places (`roles_guard.py`, `record_decision_run.py`), both
already using the `-z` porcelain form that is immune to `core.quotePath`, and
neither needing branch identity. An abstraction with no second caller is
speculative plumbing; the shell library exists because the shell call sites are
real and numerous.
"""
