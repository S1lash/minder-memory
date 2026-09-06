#!/usr/bin/env python3
"""Seed-contract gate — enforce the three seeding conventions so they cannot drift.

The engine ships owner-facing files three ways (declared in `.engine-manifest.yml`):

  1. strip-seed  — `template:` minus `seed_skill:`; release renames
                   `X.template.<ext>` → `X.<ext>` (any extension). The stripped
                   file must exist in a fresh clone.
  2. skill-seed  — `template:` ∩ `seed_skill:`; ships verbatim (`.template` kept);
                   the owning skill copies it to the live name on first run.
  3. layered     — a `*.template.yaml` under the engine `_system/scripts/` dir,
                   read directly by the runtime loader; owner overrides live in
                   `*.local.yaml` (never shipped).

This gate proves an assembled skeleton honours the contract. It runs at release
time (inside `release_engine.py`, aborting a malformed release) and standalone in
CI. A mis-declared or leaked seed fails hard here — the contract cannot silently
rot.

Usage:
  scripts/check_seed_contract.py                  # static checks + build a temp skeleton and scan it
  scripts/check_seed_contract.py --skeleton PATH  # ALSO diff an existing skeleton clone against a
                                                  # fresh release — catches stray cruft that a
                                                  # `rsync`-without-`--delete` release left behind
                                                  # (run this post-rsync, pre-commit, on every ship)
  (imported)  scan_skeleton(target, manifest, repo_root) -> list[str]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from lib.portable import configure_std_streams  # noqa: E402


from release_engine import load_manifest, repo_root

# Engine `.template.*` files that legitimately ship verbatim (not seeds — their
# own installers/skills consume them at their `.template` name).
WHITELIST_TEMPLATE_BASENAMES = {
    "minder-memory.template.md",  # obsidian vault dashboard seed (seed.sh renames it)
    "PROFILE.template.md",     # describe-me profile seed (excluded from /minder:mem:process by the *.template.md rule)
}


def _norm(paths: list[str]) -> set[str]:
    return {p.rstrip("/") for p in paths}


def static_checks(manifest: dict, repo: Path) -> list[str]:
    """Manifest-level invariants — no build needed."""
    v: list[str] = []
    template = _norm(manifest.get("template", []))
    engine = _norm(manifest.get("engine", []))
    seed_skill = _norm(manifest.get("seed_skill", []))

    for p in sorted(seed_skill - template):
        v.append(f"seed_skill entry not in template: {p}")

    # A template file must never sit under an engine directory — it would ship
    # twice (engine dir copy + template seed) and /minder:mem:update (engine-only) would
    # silently overwrite the seeded owner file. Exact overlap or dir-prefix.
    engine_dirs = [e for e in engine if (repo / e).is_dir()]
    for t in sorted(template):
        if t in engine:
            v.append(f"path declared in BOTH engine and template: {t}")
        for e in engine_dirs:
            if t.startswith(e + "/"):
                v.append(f"template seed under engine dir (double-ship): {t}  ⊂  {e}/")
    return v


def scan_skeleton(skeleton: Path, manifest: dict, repo: Path) -> list[str]:
    """Full gate: static manifest checks + scan of an assembled skeleton tree."""
    v = static_checks(manifest, repo)

    seed_skill_basenames = {Path(p.rstrip("/")).name for p in manifest.get("seed_skill", [])}

    # 1. No un-materialised template leaks. Every `*.template.*` in the skeleton
    #    must be an intended verbatim ship: a skill-seed, a layered baseline
    #    (`*.template.yaml`), or an explicit whitelist entry.
    for p in skeleton.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        name = p.name
        is_templatey = ".template." in name or name.endswith(".template")
        if not is_templatey:
            continue
        if name in seed_skill_basenames:
            continue
        if name.endswith(".template.yaml"):  # layered baseline, read directly
            continue
        if name in WHITELIST_TEMPLATE_BASENAMES:
            continue
        v.append(f"un-materialised template leaked into skeleton: {p.relative_to(skeleton)}")

    # 2. No owner override leaks — `*.local.yaml` is owner-private, never shipped.
    for p in skeleton.rglob("*.local.yaml"):
        v.append(f"owner override (.local.yaml) leaked into skeleton: {p.relative_to(skeleton)}")

    # 3. Layered baseline integrity — a plain `{base}.yaml` shipped next to a
    #    `{base}.template.yaml` must be byte-identical (owner tuning belongs in
    #    `.local.yaml`; a divergent plain `.yaml` means tuning leaked to friends).
    for tmpl in skeleton.rglob("*.template.yaml"):
        plain = tmpl.with_name(tmpl.name[: -len(".template.yaml")] + ".yaml")
        if plain.exists() and plain.read_bytes() != tmpl.read_bytes():
            v.append(f"baseline diverges from template (tuning leak): {plain.relative_to(skeleton)}")

    return v


def _build_release(repo: Path, target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / "release_engine.py"),
         "--target", str(target), "--skip-lint"],
        capture_output=True, text=True,
    )


def find_strays(skeleton: Path, release: Path) -> list[str]:
    """Git-TRACKED files in an existing skeleton clone but NOT produced by a fresh
    release. Only tracked files reach friends (they clone/pull), so untracked
    bytecode / local cruft is intentionally ignored — a `.gitignore` already keeps
    it out of the ship. What this catches is committed cruft a `rsync`-without-
    `--delete` ship left behind — e.g. a strip-seed's pre-strip `.template` twin
    from an older release. A fresh clone must contain exactly the release output;
    anything extra tracked is a stray that reaches friends and must be `git rm`ed."""
    tracked = subprocess.run(
        ["git", "-C", str(skeleton), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    release_files = {
        str(p.relative_to(release))
        for p in release.rglob("*")
        if p.is_file() and not p.is_symlink()
    }
    strays = [t for t in tracked if t and t not in release_files]
    return sorted(f"stray in skeleton (not in a fresh release): {s}" for s in strays)


def main() -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    ap = argparse.ArgumentParser(description="Seed-contract gate.")
    ap.add_argument("--skeleton", help="also diff this existing skeleton clone against a fresh release")
    args = ap.parse_args()

    repo = repo_root()
    manifest = load_manifest(repo)

    # Build a throwaway skeleton and scan it — the most robust check is over the
    # ACTUAL release output, not a re-derivation of the naming logic.
    with tempfile.TemporaryDirectory(prefix="seed-contract-") as tmp:
        target = Path(tmp) / "skeleton"
        rc = _build_release(repo, target)
        # release_engine runs scan_skeleton internally and returns 2 on violation.
        if rc.returncode != 0:
            sys.stderr.write(rc.stdout)
            sys.stderr.write(rc.stderr)
            print("seed-contract gate: FAILED (release output malformed)", file=sys.stderr)
            return 1

        if args.skeleton:
            skel = Path(args.skeleton).resolve()
            problems = scan_skeleton(skel, manifest, repo) + find_strays(skel, target)
            if problems:
                print("seed-contract gate: FAILED — skeleton clone diverges from a clean release:",
                      file=sys.stderr)
                for p in problems:
                    print(f"  ✗ {p}", file=sys.stderr)
                print("remove the stray/leaking files from the skeleton (git rm), then re-run.",
                      file=sys.stderr)
                return 1
            print(f"seed-contract gate: OK (skeleton {skel} matches a clean release)")
            return 0

    print("seed-contract gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
