#!/usr/bin/env python3
"""
Release engine — copy engine + template paths into a target directory.

Reads `.engine-manifest.yml`. For each `engine` path, copies as-is. Each
`template` path ships one of two ways, per the seed contract:

  - strip-seed (`template:` minus `seed_skill:`) — the `.template`
    segment is dropped from the destination name, whatever the extension
    (`SOUL.template.md` → `SOUL.md`, `x.template.json` → `x.json`), so a
    fresh clone opens with the file already in place.
  - skill-seed (`template:` ∩ `seed_skill:`) — copied verbatim, name
    intact; the owning skill materialises it on first run.

Anything not in `engine` or `template` is excluded by default.

Symlinks are preserved as symlinks, except under a deref-prefix
(`.claude/skills/`) where they are dereferenced into real files — git
symlinks do not survive a Windows clone.

Used by the owner to assemble the public skeleton (`minder-memory`) from
the personal instance.

Usage:
  scripts/release_engine.py --target /tmp/minder-memory-skeleton
  scripts/release_engine.py --target /tmp/skeleton --dry-run

Verifies before write:
  - All manifested paths exist in the source
  - `check_no_personal_data.py` — no owner identity in what ships
  - `check_portability.py` — no ENGINE_DOCTRINE §3.9 violation ships

Verifies after write:
  - `check_seed_contract.py::scan_skeleton` — the assembled tree honours
    the seed contract (no un-materialised template leak, no owner
    override or tuning file, nothing shipped twice)

Any of these failing aborts the release.

Does NOT initialize git in the target — that is the operator's job
(orphan-init recommended for the public repo).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# `repo_root` / `load_manifest` are re-exported so the historical
# `from release_engine import ...` call sites keep working; `lib.manifest` is
# the single owner of both.
from lib.manifest import load_manifest, repo_root  # noqa: E402,F401
from lib.portable import configure_std_streams  # noqa: E402


_TEMPLATE_SUFFIX_RE = re.compile(r"^(.*)\.template(\.[^.]+)$")


def strip_template_suffix(name: str) -> str:
    """`SOUL.template.md` → `SOUL.md`; `content-pipeline-state.template.json` →
    `content-pipeline-state.json`. Strips a `.template` segment before the final
    extension, for ANY extension — the strip decision is intent-explicit (see
    `seed_skill` in the manifest), never keyed on `.md`, so a future non-markdown
    strip-seed cannot silently ship un-renamed. Applied ONLY to strip-seed
    entries; skill-seed entries (in `seed_skill:`) are shipped verbatim."""
    m = _TEMPLATE_SUFFIX_RE.match(name)
    if m:
        return m.group(1) + m.group(2)
    return name


def parse_source_ids_from_template(template_path: Path) -> list[str]:
    """Read SOURCES.template.md, return ordered list of IDs from the
    `## Active Sources` and `## Reserved Sources` tables. Skips
    `## Deprecated Sources`. ID is the first column of the markdown table.
    """
    if not template_path.exists():
        return []
    ids: list[str] = []
    section: str | None = None
    for raw in template_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if heading.startswith("active sources") or heading.startswith("reserved sources"):
                section = heading
            else:
                section = None
            continue
        if section is None:
            continue
        # Table row: `| id | ... |` — skip header and separator rows.
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if not first or first.lower() == "id" or set(first) <= set("-: "):
            continue
        # Strip backticks/markdown around the ID if any.
        first = first.strip("`").strip()
        # A deliberately-empty table still needs a row to render, and the
        # placeholder in that row is prose, not an identifier. Taken as one it
        # becomes a real directory in every friend's vault, named with
        # parentheses the whole engine otherwise keeps out of paths. A source
        # ID is the portable identifier `/minder:mem:source-add` validates, so
        # anything outside that shape is a rendering artifact and not a source.
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", first):
            continue
        ids.append(first)
    return ids


def _copy_symlink(src: Path, dst: Path, dry_run: bool, label: Path) -> None:
    """Preserve a symlink at the destination (relative target stored verbatim)."""
    target = os.readlink(src)
    if dry_run:
        print(f"  + {label} (symlink → {target})")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    os.symlink(target, dst)


# Paths whose committed symlinks must ship to the skeleton as REAL files rather
# than being preserved as symlinks. `.claude/skills/<name>` are symlinks into
# `integrations/claude-code/skills/` in the owner repo (native on macOS/Linux,
# convenient for the dev loop) — but git symlinks do NOT survive a Windows
# clone: with `core.symlinks=false` git materialises the symlink blob as a text
# file containing the target path, so `.claude/skills/minder-mem-process` becomes a
# FILE and `.claude/skills/minder-mem-process/SKILL.md` no longer exists. That breaks
# skill discovery for Cloud Routines and project-CWD sessions on friends'
# machines. Dereferencing at release time makes the skeleton cross-platform.
_DEREF_SYMLINK_PREFIXES: tuple[str, ...] = (".claude/skills/",)


def _under_deref(rel: Path) -> bool:
    """True if this manifest-relative path must be dereferenced on release."""
    posix = rel.as_posix()
    return any(
        posix == pref.rstrip("/") or posix.startswith(pref)
        for pref in _DEREF_SYMLINK_PREFIXES
    )


def _copy_deref_symlink(src: Path, dst: Path, dry_run: bool, label: Path) -> int:
    """Dereference a symlink and copy its target as real file(s) at dst.

    Returns the count of files written. A broken symlink is reported and
    skipped (returns 0) rather than aborting the release.
    """
    resolved = src.resolve()
    if not resolved.exists():
        print(f"  ! broken symlink, cannot dereference: {label}", file=sys.stderr)
        return 0

    if not resolved.is_dir():
        if dry_run:
            print(f"  + {label} (dereferenced file)")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, dst)
        return 1

    count = 0
    for f in sorted(resolved.rglob("*")):
        rel_in = f.relative_to(resolved)
        if any(part in _SKIP_DIRS or part.endswith(_SKIP_SUFFIXES) for part in rel_in.parts):
            continue
        if f.is_dir():
            continue
        target = dst / rel_in
        if dry_run:
            print(f"  + {label}/{rel_in.as_posix()} (dereferenced)")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
        count += 1
    return count


# Lenses that ship `status: draft` to the skeleton even though the maintainer
# runs them `active` locally, because they are prerequisite-gated: their input
# comes from a collector the engine does not ship, so a friend's base has no
# such records at all. The runner has no empty-input short-circuit — it makes
# the call first and records `status: empty` after — so an active lens over an
# absent source burns LLM budget on every scheduled run and can only ever
# return nothing. They flip to `active` once the friend wires up the source
# and opts in.
#
# Identity/values proposers are NOT gated here: `cognitive-model` mines private
# reflections but only APPENDS to the high-recall `principle-candidates.jsonl`
# review buffer (stamped `origin: agent-lens`, never auto-merged into
# `0_constitution/` — the owner promotes via `/minder:mem:lint` F.5). Proposing is safe
# to ship on by default; promotion stays owner-sovereign. So it ships `active`
# platform-wide.
#
# Add to this list only when a lens is source-gated (needs data the friend must
# provision first). Do NOT add a lens merely because it reads private content —
# the buffer-append + owner-promotion gate already protects that surface.
DEMOTE_LENSES_ON_RELEASE: tuple[str, ...] = (
    # health-collector adapter — biometric records
    "biometric-anomaly-narrator",
    "biometric-cross-domain",
    "training-load-trend",
    "biometric-life-synthesis",
    # local ActivityWatch collector — computer-usage activity records
    "time-allocation",
)


def _demote_lens_status(skeleton_root: Path, *, lens_ids: tuple[str, ...]) -> int:
    """Demote each lens's `status: active` → `status: draft` in two
    places under the freshly-extracted skeleton:

      1. `_system/registries/lenses/<id>/prompt.md` frontmatter.
      2. `_system/registries/AGENT_LENSES.md` rows — moves them out of
         the `## Active Lenses` table into `## Draft Lenses`.

    Idempotent: if a lens row is already `draft` (or missing), no-op
    on that lens. Returns count of lenses demoted (across both files).
    """
    import re

    demoted = 0
    # 1) Per-prompt frontmatter
    for lens in lens_ids:
        prompt = skeleton_root / "zettelkasten" / "_system" / "registries" / "lenses" / lens / "prompt.md"
        if not prompt.exists():
            continue
        text = prompt.read_text(encoding="utf-8")
        new_text = re.sub(
            r"^(status:\s*)active\s*$", r"\1draft",
            text, count=1, flags=re.MULTILINE,
        )
        if new_text != text:
            prompt.write_text(new_text, encoding="utf-8")
            demoted += 1

    # 2) Registry table — move rows from Active Lenses → Draft Lenses
    registry = skeleton_root / "zettelkasten" / "_system" / "registries" / "AGENT_LENSES.md"
    if not registry.exists():
        return demoted
    text = registry.read_text(encoding="utf-8")
    moved_rows: list[str] = []
    new_lines: list[str] = []
    for line in text.splitlines():
        is_target_active_row = (
            line.startswith("|")
            and any(f"| {lid} " in line for lid in lens_ids)
            and line.rstrip().endswith("| active |")
        )
        if is_target_active_row:
            moved_rows.append(line.replace("| active |", "| draft |"))
            continue  # skip from output (will re-insert in Draft Lenses)
        new_lines.append(line)
    if not moved_rows:
        return demoted
    # Insert moved rows under `## Draft Lenses` (replacing the
    # `_(empty)_` placeholder if present, else appending under header).
    out: list[str] = []
    i = 0
    while i < len(new_lines):
        line = new_lines[i]
        out.append(line)
        if line.startswith("## Draft Lenses"):
            # Skip blank + `_(empty)_` placeholder if present
            j = i + 1
            while j < len(new_lines) and (new_lines[j].strip() == "" or new_lines[j].strip() == "_(empty)_"):
                j += 1
            # Emit blank + table header + moved rows
            out.append("")
            out.append("| ID | Name | Type | Input | Cadence | Self-history | Status |")
            out.append("|---|---|---|---|---|---|---|")
            out.extend(moved_rows)
            out.append("")
            i = j
            continue
        i += 1
    registry.write_text("\n".join(out) + "\n", encoding="utf-8")
    return demoted + len(moved_rows)


# Build artifacts and IDE / editor noise that locally git-ignores but
# physically lives under engine paths. Filtered at copy time so the
# skeleton stays clean.
_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    "node_modules",
})

_SKIP_SUFFIXES: tuple[str, ...] = (
    ".pyc", ".pyo", ".pyd",
)


def copy_path(src_root: Path, dst_root: Path, rel: str, *, strip_template: bool, dry_run: bool) -> int:
    """Copy a manifest entry. Returns count of files copied."""
    rel_clean = rel.rstrip("/")
    src = src_root / rel_clean

    # Top-level symlink — dereference to real files under a deref-prefix
    # (e.g. .claude/skills/), otherwise preserve as symlink.
    if src.is_symlink():
        sub_rel = Path(rel_clean)
        if _under_deref(sub_rel):
            return _copy_deref_symlink(src, dst_root / sub_rel, dry_run, sub_rel)
        _copy_symlink(src, dst_root / sub_rel, dry_run, sub_rel)
        return 1

    if not src.exists():
        print(f"  ! missing in source: {rel_clean}", file=sys.stderr)
        return 0

    count = 0
    if src.is_dir():
        for sub in src.rglob("*"):
            sub_rel = sub.relative_to(src_root)
            # Skip Python bytecode caches and other build artifacts that
            # are gitignored locally but rglob still finds on disk. They
            # would pollute the skeleton clone and cause permission /
            # ownership weirdness on friend's machines.
            if any(part in _SKIP_DIRS or part.endswith(_SKIP_SUFFIXES) for part in sub_rel.parts):
                continue
            dst = dst_root / sub_rel
            # Symlinks (to files OR directories) — preserve as symlinks.
            # Must be checked BEFORE is_dir(), since is_dir() follows symlinks
            # and rglob would otherwise either descend into them (duplicating
            # content under a different path) or skip them silently.
            if sub.is_symlink():
                if _under_deref(sub_rel):
                    count += _copy_deref_symlink(sub, dst, dry_run, sub_rel)
                else:
                    _copy_symlink(sub, dst, dry_run, sub_rel)
                    count += 1
                continue
            if sub.is_dir():
                continue
            if dry_run:
                print(f"  + {sub_rel}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sub, dst)
            count += 1
    else:
        sub_rel = Path(rel_clean)
        dst_name = strip_template_suffix(sub_rel.name) if strip_template else sub_rel.name
        dst = dst_root / sub_rel.parent / dst_name
        if dry_run:
            print(f"  + {sub_rel.parent / dst_name}{' (renamed from template)' if dst_name != sub_rel.name else ''}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        count = 1
    return count


def main() -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True, help="destination directory (must not exist or be empty)")
    ap.add_argument("--dry-run", action="store_true", help="list files without copying")
    ap.add_argument("--skip-lint", action="store_true", help="skip personal-data linter (NOT recommended)")
    args = ap.parse_args()

    root = repo_root()
    manifest = load_manifest(root)

    target = Path(args.target).resolve()
    if not args.dry_run:
        if target.exists() and any(target.iterdir()):
            print(f"error: target {target} exists and is not empty", file=sys.stderr)
            return 2
        target.mkdir(parents=True, exist_ok=True)

    if not args.skip_lint:
        # Both gates are invoked through `sys.executable`, never through the
        # `.sh` wrapper: Windows has no executable bit and `.sh` is not a Win32
        # application, so `subprocess.run(["…/x.sh"])` raises WinError 193 and
        # the release cannot start at all. The wrapper stays as a human
        # convenience.
        for label, script, failure in (
            ("personal-data linter", "check_no_personal_data.py", "linter found leaks"),
            ("portability gate", "check_portability.py", "portability violations found"),
            # Release is the only moment this can still be fixed cheaply. Once a
            # version ships, every clone that takes it holds the undeclared file
            # for good — and a half-declared removal breaks the survivors that
            # import what was retired.
            ("retirement gate", "check_retirements.py", "shipped paths deleted but undeclared"),
            # A migration reaches a friend's clone and runs there once. An
            # untested one that succeeds at the wrong thing is marked applied
            # and never retried, so release is the last moment the omission is
            # still free to fix.
            ("migration-coverage gate", "check_migration_coverage.py",
             "a migration ships with no suite and no exemption"),
        ):
            print(f"running {label}...")
            rc = subprocess.run(
                [sys.executable, str(root / "scripts" / script)]
            ).returncode
            if rc != 0:
                print(f"error: {failure} — fix before release", file=sys.stderr)
                return 2

    total = 0
    print(f"\nengine paths → {target}")
    for entry in manifest.get("engine", []):
        total += copy_path(root, target, entry, strip_template=False, dry_run=args.dry_run)

    # Seed contract: strip-seed entries get `.template` stripped; skill-seed
    # entries (declared in `seed_skill:`) ship verbatim so the owning skill can
    # materialise the live file on first run. Intent is declared, never inferred.
    seed_skill = {p.rstrip("/") for p in manifest.get("seed_skill", [])}
    unknown_skill = seed_skill - {p.rstrip("/") for p in manifest.get("template", [])}
    if unknown_skill:
        print(f"error: seed_skill entries not in template: {sorted(unknown_skill)}", file=sys.stderr)
        return 2
    print(f"\ntemplate paths → {target} (strip-seed renamed; skill-seed verbatim)")
    for entry in manifest.get("template", []):
        strip = entry.rstrip("/") not in seed_skill
        total += copy_path(root, target, entry, strip_template=strip, dry_run=args.dry_run)

    print(f"\n{'would copy' if args.dry_run else 'copied'} {total} files")

    if not args.dry_run:
        # Source folders are derived from SOURCES.template.md (single source
        # of truth). After release_engine copied templates and stripped the
        # `.template` suffix, the file lives at registries/SOURCES.md in
        # the target.
        sources_template = target / "zettelkasten/_system/registries/SOURCES.md"
        source_ids = parse_source_ids_from_template(sources_template)
        if not source_ids:
            print(
                "warning: no source IDs found in SOURCES.template — "
                "skeleton will ship without inbox/processed source folders",
                file=sys.stderr,
            )

        source_dirs: list[str] = []
        for sid in source_ids:
            source_dirs.append(f"zettelkasten/_sources/inbox/{sid}")
            source_dirs.append(f"zettelkasten/_sources/processed/{sid}")

        # Non-source layout dirs that always ship empty.
        layout_dirs = [
            "zettelkasten/_records/meetings",
            "zettelkasten/_records/observations",
            "zettelkasten/0_constitution/axiom",
            "zettelkasten/0_constitution/principle",
            "zettelkasten/0_constitution/rule",
            "zettelkasten/1_projects",
            "zettelkasten/2_areas",
            "zettelkasten/3_resources/people",
            "zettelkasten/3_resources/ideas",
            "zettelkasten/3_resources/tech",
            "zettelkasten/4_archive",
            "zettelkasten/5_meta/mocs",
            "zettelkasten/6_posts",
            "zettelkasten/_system/state/batches",
            "zettelkasten/_system/state/lint-context",
        ]
        empty_dirs = source_dirs + layout_dirs
        for d in empty_dirs:
            (target / d).mkdir(parents=True, exist_ok=True)
            keep = target / d / ".gitkeep"
            if not keep.exists():
                keep.touch()

        # Skeleton-only post-process: demote owner-activated lenses
        # back to `status: draft` so friends don't auto-run lenses
        # against absent data. The maintainer's clone retains `active`
        # for the maintainer's own data; this hook only touches the
        # extracted skeleton tree.
        _demote_lens_status(target, lens_ids=DEMOTE_LENSES_ON_RELEASE)

        # Seed-contract gate — verify the assembled skeleton against the seed
        # contract (no un-materialised template leaks, no owner override / tuning
        # leaks, no double-listing). A violation means the release is malformed;
        # fail hard before the operator publishes it.
        from check_seed_contract import scan_skeleton  # noqa: E402 (co-located gate)

        violations = scan_skeleton(target, manifest, root)
        if violations:
            print("\nerror: seed-contract gate FAILED — skeleton is malformed:", file=sys.stderr)
            for v in violations:
                print(f"  ✗ {v}", file=sys.stderr)
            print("release aborted; fix the manifest / source and re-run.", file=sys.stderr)
            return 2
        print("seed-contract gate: OK")

        print(f"\nlayout ready at {target}")
        print("\nnext steps (operator):")
        print(f"  cd {target}")
        print("  git init")
        print("  git add .")
        print('  git commit -m "Initial skeleton release"')
        print("  gh repo create minder-memory --public --source=. --remote=origin --push")
        print("  gh repo edit --enable-issues --enable-projects --template")

    return 0


if __name__ == "__main__":
    sys.exit(main())
