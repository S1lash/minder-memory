#!/usr/bin/env python3
"""Migration 031's producer — re-wire the Claude Code harness for Minder Memory.

After the engine sync that carries the rename, the friend's clone holds the new
skills, the new hot rule and the new commands, and `retire_paths.py` has removed
the old ones. What the sync cannot reach is the harness home (`~/.claude`),
because it is outside the repository: every symlink the installer once created
still points at a name that no longer exists, and the managed block in
`~/.claude/CLAUDE.md` still `@`-imports the old rule file. Nothing fails —
the rule simply stops loading in every session. This module is what closes
that window, in five steps that are each idempotent:

  A. The legacy managed-block markers in `$CLAUDE_HOME/CLAUDE.md` become the
     current ones, in place, so the installer refreshes the block where the
     owner put it instead of appending a second one at the end.
  B. Symlinks under `$CLAUDE_HOME/{rules,commands,skills,agents}` that point
     INTO this repository and either dangle or carry a legacy name are removed.
     A link that points anywhere else is never touched — it is only reported
     when it dangles, because it is somebody else's.
  C. `integrations/claude-code/install.sh` runs. Its failure is the
     migration's failure: the migration is `structural`, so the update aborts
     and retries next time rather than recording a half-wired harness. A clone
     that carries no installer has no harness to re-wire and passes.
  D. Any git remote whose URL names the skeleton by its old repository name is
     pointed at the new one — but only after `git ls-remote` proves the new
     URL answers. No network, no answer, or a fork that merely shares the old
     name: the remote is left alone and the manual command is printed.
  E. A digest tells the owner what changed and what they hold outside the
     repository: the routine prompts to reconcile, the environment variable
     names (the old ones still work), the connector name.

Never prints a credential value. Never touches anything under `zettelkasten/`.

Usage:
  python3 scripts/migrations/_031_harness_wiring.py --repo-root <root> [--dry-run] [--json]
"""

from __future__ import annotations

# minder-memory-rebrand: keep-legacy-tokens — the former names below are what this migration removes.

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.manifest import read_section_lite  # noqa: E402
from lib.portable import configure_std_streams, read_text_utf8, write_text_utf8  # noqa: E402

LEGACY_BEGIN = "<!-- MINDER-ZTN BEGIN — managed by install.sh, do not edit by hand -->"
LEGACY_END = "<!-- MINDER-ZTN END -->"
BEGIN_MARK = "<!-- MINDER-MEMORY BEGIN — managed by install.sh, do not edit by hand -->"
END_MARK = "<!-- MINDER-MEMORY END -->"

# What the installer used to link, by directory. A `ztn-` prefix under skills/
# covers every skill the engine ever shipped under the old namespace.
LEGACY_LINK_NAMES: dict[str, tuple[str, ...]] = {
    "rules": ("ztn.md", "ztn-engine-doctrine.md"),
    "commands": ("ztn-recap.md", "ztn-search.md"),
    "agents": ("ztn-role.md",),
    "skills": (),
}
LEGACY_SKILL_PREFIX = "ztn-"

OLD_REPO_NAME = "minder-ztn"
NEW_REPO_NAME = "minder-memory"

INSTALLER_REL = Path("integrations/claude-code/install.sh")
BACKUP_PREFIX = ".minder-memory-backup-"


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude"))


# -----------------------------------------------------------------------------
# A — markers
# -----------------------------------------------------------------------------

def rewrite_markers(home: Path, *, dry_run: bool) -> dict:
    claude_md = home / "CLAUDE.md"
    result = {"file": str(claude_md), "action": "absent"}
    if not claude_md.is_file():
        return result
    text = read_text_utf8(claude_md)
    if LEGACY_BEGIN not in text and LEGACY_END not in text:
        result["action"] = "already-current" if BEGIN_MARK in text else "no-block"
        return result
    new_text = text.replace(LEGACY_BEGIN, BEGIN_MARK).replace(LEGACY_END, END_MARK)
    result["action"] = "rewritten"
    if dry_run:
        return result
    backup_dir = home / (BACKUP_PREFIX + datetime.now().strftime("%Y%m%d-%H%M%S"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(claude_md, backup_dir / "CLAUDE.md.before-031")
    write_text_utf8(claude_md, new_text)
    result["backup"] = str(backup_dir / "CLAUDE.md.before-031")
    return result


# -----------------------------------------------------------------------------
# B — links
# -----------------------------------------------------------------------------

def _points_into(link: Path, repo_root: Path) -> bool:
    """True when the link's target, resolved as the OS would, sits under repo_root."""
    try:
        raw = os.readlink(link)
    except OSError:
        return False
    target = Path(raw) if os.path.isabs(raw) else link.parent / raw
    try:
        target = Path(os.path.normpath(target)).resolve(strict=False)
        return target == repo_root or repo_root in target.parents
    except OSError:
        return False


def _is_legacy_name(subdir: str, name: str) -> bool:
    if subdir == "skills":
        return name.startswith(LEGACY_SKILL_PREFIX)
    return name in LEGACY_LINK_NAMES.get(subdir, ())


def prune_links(home: Path, repo_root: Path, *, dry_run: bool) -> tuple[list[str], list[str]]:
    """Remove our dangling / legacy links; report foreign dangling ones."""
    removed: list[str] = []
    reported: list[str] = []
    repo_root = repo_root.resolve()
    for subdir in ("rules", "commands", "skills", "agents"):
        d = home / subdir
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            if not entry.is_symlink():
                continue
            dangling = not entry.exists()
            ours = _points_into(entry, repo_root)
            if ours and (dangling or _is_legacy_name(subdir, entry.name)):
                removed.append(str(entry))
                if not dry_run:
                    entry.unlink()
            elif dangling:
                reported.append(str(entry))
    # The commands namespace directory the current installer links as a whole:
    # a dangling `commands/minder/mem` is ours by the same rule.
    ns = home / "commands" / "minder" / "mem"
    if ns.is_symlink() and not ns.exists() and _points_into(ns, repo_root):
        removed.append(str(ns))
        if not dry_run:
            ns.unlink()
    return removed, reported


# -----------------------------------------------------------------------------
# B2 — engine paths the OLD sync could not fetch
# -----------------------------------------------------------------------------

def converge_engine_paths(repo_root: Path, *, dry_run: bool) -> dict:
    """Fetch every `engine:` path of the manifest that is absent on disk.

    A clone that ran its previous `sync_engine.sh` (not the update skill, which
    repairs the script first) read the engine list from its OWN, older manifest
    and so never fetched a path that exists only in the new one — while the
    retirement step, reading the new manifest, already removed the
    predecessor. The renamed role agent and the MCP guide are exactly that. The
    current sync reads the manifest it applies; this step closes the gap for
    the one update that ran with the old script. Remote: `upstream`, or any
    remote whose URL names the skeleton.
    """
    manifest = repo_root / ".engine-manifest.yml"
    result = {"missing": [], "fetched": [], "remote": None}
    if not manifest.is_file():
        return result
    try:
        engine = read_section_lite(manifest, "engine")
    except Exception:  # noqa: BLE001 — an unreadable manifest is the sync's problem, not ours
        return result
    missing = [p for p in engine if not (repo_root / p).exists()]
    result["missing"] = missing
    if not missing:
        return result
    remote, branch = sync_remote_and_branch(repo_root)
    result["remote"] = remote
    result["branch"] = branch
    if remote is None or dry_run:
        return result
    result["errors"] = {}
    # Fetch the branch here rather than trusting a remote-tracking ref: on a
    # clone wired by `git remote add` + `git fetch <remote> <branch>` some git
    # builds leave no `refs/remotes/<remote>/<branch>` behind, and the checkout
    # then fails with «invalid reference» for a path the remote plainly has.
    # FETCH_HEAD is what the fetch just wrote, whatever the ref layout.
    fetched = _git(repo_root, "fetch", "-q", remote, branch)
    if fetched.returncode != 0:
        for p in missing:
            result["errors"][p] = (fetched.stderr or fetched.stdout).strip()
        return result
    for p in missing:
        got = _git(repo_root, "checkout", "FETCH_HEAD", "--", p)
        if got.returncode == 0:
            result["fetched"].append(p)
        else:
            # Kept for the report: a path that stays missing must say why, or
            # the owner learns of it from the next skill that cannot find it.
            result["errors"][p] = (got.stderr or got.stdout).strip()
    return result


def sync_remote_and_branch(repo_root: Path) -> tuple[str | None, str]:
    """The remote and branch the engine syncs from.

    The sync exports what it was invoked with (`ENGINE_SYNC_REMOTE`,
    `ENGINE_SYNC_BRANCH`) so a migration it runs follows the same pair — a
    fork, a release branch, a remote not called `upstream`. Outside a sync:
    `upstream` if it exists, else the remote whose URL names the skeleton;
    the branch is the remote's HEAD when known, else `main`.
    """
    remote = os.environ.get("ENGINE_SYNC_REMOTE", "").strip() or None
    branch = os.environ.get("ENGINE_SYNC_BRANCH", "").strip() or None
    names = _git(repo_root, "remote").stdout.split()
    if remote is None:
        if "upstream" in names:
            remote = "upstream"
        else:
            for name in names:
                url = _git(repo_root, "remote", "get-url", name).stdout.strip()
                if _renamed_url(url) or url.rstrip("/").rstrip(".git").endswith(NEW_REPO_NAME):
                    remote = name
                    break
    if remote is None:
        return None, branch or "main"
    if branch is None:
        head = _git(repo_root, "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
        branch = head.stdout.strip().split("/", 1)[-1] if head.returncode == 0 and head.stdout.strip() else "main"
    return remote, branch


# -----------------------------------------------------------------------------
# C — installer
# -----------------------------------------------------------------------------

def run_installer(repo_root: Path, *, dry_run: bool) -> int:
    installer = repo_root / INSTALLER_REL
    if not installer.is_file():
        # A clone without the Claude Code integration has no harness to
        # re-wire: nothing to do is not a failure. (A clone WITH it whose
        # installer fails is — see below.)
        print(f"031: no installer at {INSTALLER_REL} — no harness wiring to refresh here")
        return 0
    if dry_run:
        return 0
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(["bash", str(installer)], cwd=str(repo_root)).returncode


# -----------------------------------------------------------------------------
# D — remotes
# -----------------------------------------------------------------------------

def _renamed_url(url: str) -> str | None:
    """The same URL with its last path segment renamed, or None when it is not the old name."""
    stripped = url.rstrip("/")
    for sep in ("/", ":"):
        head, sep_found, last = stripped.rpartition(sep)
        if not sep_found:
            continue
        if last == OLD_REPO_NAME:
            return head + sep + NEW_REPO_NAME
        if last == OLD_REPO_NAME + ".git":
            return head + sep + NEW_REPO_NAME + ".git"
        break
    return None


def _git(repo_root: Path, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout)


def rewrite_remotes(repo_root: Path, *, dry_run: bool) -> list[dict]:
    out: list[dict] = []
    listed = _git(repo_root, "remote")
    if listed.returncode != 0:
        return out
    for name in listed.stdout.split():
        url = _git(repo_root, "remote", "get-url", name).stdout.strip()
        new_url = _renamed_url(url)
        if not new_url:
            continue
        entry = {"remote": name, "url": url, "new_url": new_url, "action": "kept"}
        try:
            probe = _git(repo_root, "ls-remote", "--exit-code", new_url, "HEAD", timeout=30)
            reachable = probe.returncode == 0
        except subprocess.TimeoutExpired:
            reachable = False
        if not reachable:
            entry["action"] = "unreachable"
            entry["manual"] = f"git remote set-url {name} {new_url}"
        elif dry_run:
            entry["action"] = "would-rewrite"
        else:
            set_url = _git(repo_root, "remote", "set-url", name, new_url)
            entry["action"] = "rewritten" if set_url.returncode == 0 else "failed"
        out.append(entry)
    return out


# -----------------------------------------------------------------------------
# E — digest
# -----------------------------------------------------------------------------

def digest(result: dict) -> str:
    lines = ["", "031 — Minder Memory harness wiring", "=" * 36]
    m = result["markers"]
    lines.append(f"managed block in {m['file']}: {m['action']}")
    lines.append(f"links removed under {result['home']}: {len(result['links_removed'])}")
    for p in result["links_removed"]:
        lines.append(f"  - {p}")
    if result["links_reported"]:
        lines.append("dangling links NOT ours (left in place — remove them yourself if unwanted):")
        for p in result["links_reported"]:
            lines.append(f"  - {p}")
    ep = result.get("engine_paths") or {}
    if ep.get("missing"):
        still = [p for p in ep["missing"] if p not in ep.get("fetched", [])]
        lines.append(f"engine paths the previous sync could not fetch: {len(ep['missing'])}, fetched now: {len(ep.get('fetched', []))}")
        for p in still:
            lines.append(f"  - {p} — still absent; run the update once more")
    lines.append(f"install.sh exit code: {result['install_rc']}")
    for r in result["remotes"]:
        if r["action"] in ("rewritten", "would-rewrite"):
            lines.append(f"remote {r['remote']}: {r['url']} -> {r['new_url']} ({r['action']})")
        else:
            lines.append(f"remote {r['remote']} still points at {r['url']}; the new URL did not answer.")
            lines.append(f"  when you are online:  {r['manual']}")
    lines += [
        "",
        "What is now different, and what stays in your hands:",
        "  - Skills answer to /minder:mem:<name> (for example /minder:mem:process,",
        "    /minder:mem:update). The /ztn:* names are gone; 'ztn' remains a spoken alias.",
        "  - The base path variable is MINDER_MEMORY_BASE; the former ZTN_BASE and",
        "    MINDER_ZTN_BASE are no longer read — rename them where you set them.",
        "  - The credential-store key is MINDER_MEMORY_ROLES_KEY; ZTN_ROLES_KEY is no",
        "    longer read. Until it is renamed in your scheduler's environment, every",
        "    role that reaches an outside service cannot decrypt its credentials.",
        "  - Your scheduled routines hold the prompt text and the environment they",
        "    were given. /minder:mem:update walks the upgrade checklist",
        "    (docs/upgrade-1.0.0.md): it renames the variable, switches stale prompt",
        "    bodies and verifies every wiring this migration touched.",
        "  - An MCP connector you configured under the old name keeps working; a new",
        "    install names it minder-memory.",
        "  - Open a new Claude Code session so the re-wired rules load.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_std_streams()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    home = claude_home()
    result: dict = {"home": str(home), "repo_root": str(repo_root), "dry_run": args.dry_run}

    result["markers"] = rewrite_markers(home, dry_run=args.dry_run)
    removed, reported = prune_links(home, repo_root, dry_run=args.dry_run)
    result["links_removed"] = removed
    result["links_reported"] = reported
    result["engine_paths"] = converge_engine_paths(repo_root, dry_run=args.dry_run)
    still_missing = [p for p in result["engine_paths"].get("missing", [])
                     if p not in result["engine_paths"].get("fetched", [])]
    if still_missing and not args.dry_run:
        print("031: these engine paths are absent and could not be fetched — the harness would be wired "
              "against a clone that lacks part of the engine:", file=sys.stderr)
        for p in still_missing:
            print(f"    {p}", file=sys.stderr)
        print("031: run the update once more (it fetches them), then this migration re-runs by itself.",
              file=sys.stderr)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    result["install_rc"] = run_installer(repo_root, dry_run=args.dry_run)
    if result["install_rc"] != 0:
        print(f"031: install.sh exited {result['install_rc']} — the harness is not re-wired; "
              f"the update will retry this migration. To re-wire by hand, run from the repository root:\n"
              f"    bash integrations/claude-code/install.sh", file=sys.stderr)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    result["remotes"] = rewrite_remotes(repo_root, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(digest(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
