#!/usr/bin/env python3
"""Regenerate all derived views in one call.

Runs the generators in dependency order:
    1. gen_constitution_index   → _system/views/CONSTITUTION_INDEX.md
    2. gen_constitution_core    → _system/views/constitution-core.md
    3. render_index             → _system/views/INDEX.md (knowledge + archive + constitution + hubs surface catalog)
    4. render_hub_index         → _system/views/HUB_INDEX.md managed zone (hub registry)
    5. render_tags              → _system/registries/TAGS.md managed zone (`tags:` axis census)
    6. render_soul_values       → _system/SOUL.md auto-zone (between markers)

Exit status: 0 when every applicable step succeeded — including the documented
skip of the SOUL step on a base whose SOUL.md has no auto-zone markers yet
(`--strict-soul` turns that skip into exit 2). Any other non-zero is a real
failure of the step that printed it.

Fail-fast: any step's non-zero exit propagates immediately — the remaining
steps are not run. All writes are idempotent (same inputs → same outputs
aside from the timestamp line).

Invocation:
    - Manually after editing `0_constitution/`
    - As the first step of every Minder Memory pipeline that reads derived views
      (`/minder:mem:process`, `/minder:mem:maintain`, `/minder:mem:lint`). This is the single
      consistent rule: every consumer regenerates before reading.
    - From scheduler tasks on the Claude platform

Usage:
    python3 regen_all.py [--dry-run]
                        [--strict-soul] [--write-soul-clarification]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from _common import configure_std_streams  # type: ignore


SCRIPTS_DIR = Path(__file__).resolve().parent


def _run_step(script_name: str, extra_args: list[str], dry_run: bool) -> int:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + extra_args
    if dry_run and "--dry-run" not in extra_args:
        cmd.append("--dry-run")
    print(f"→ {script_name} " + " ".join(extra_args), file=sys.stderr)
    return subprocess.call(cmd)


def _soul_has_markers(soul_path: Path) -> bool:
    """SOUL marker presence is a prerequisite for render_soul_values.

    Until the SOUL integration step places the markers, render_soul_values
    would fail with a clear error. Skipping it keeps regen_all usable on
    fresh / pre-integration repos without manual flag juggling.
    """
    if not soul_path.exists():
        return False
    try:
        text = soul_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        "<!-- AUTO-GENERATED FROM CONSTITUTION" in text
        and "<!-- END AUTO-GENERATED -->" in text
    )


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="propagate --dry-run to every step (no writes)",
    )
    parser.add_argument(
        "--strict-soul", action="store_true",
        help="fail (exit 2) if SOUL.md is missing its auto-zone markers; "
             "default is to skip that step with an info message and exit 0",
    )
    parser.add_argument(
        "--write-soul-clarification", action="store_true",
        help="pass --write-clarification to render_soul_values",
    )
    args = parser.parse_args(argv)

    # Step 1: index
    rc = _run_step("gen_constitution_index.py", [], args.dry_run)
    if rc != 0:
        print("regen_all: gen_constitution_index failed", file=sys.stderr)
        return rc

    # Step 2: core (single file, all scopes visible)
    rc = _run_step("gen_constitution_core.py", [], args.dry_run)
    if rc != 0:
        print("regen_all: gen_constitution_core failed", file=sys.stderr)
        return rc

    # Step 3: INDEX — surface catalog of knowledge + archive + constitution + hubs.
    # Reads frontmatter across the base; no hard dependency on prior steps,
    # but ordered after constitution regen so INDEX never lags constitution
    # changes that landed in the same call.
    rc = _run_step("render_index.py", [], args.dry_run)
    if rc != 0:
        print("regen_all: render_index failed", file=sys.stderr)
        return rc

    # Step 4: HUB_INDEX — registry of the hub files on disk. Reads hub
    # frontmatter only; ordered after INDEX so the two hub surfaces are
    # rendered from the same tree in one call.
    rc = _run_step("render_hub_index.py", [], args.dry_run)
    if rc != 0:
        print("regen_all: render_hub_index failed", file=sys.stderr)
        return rc

    # Step 5: TAGS — census of the `tags:` axis. Reads note frontmatter across
    # the knowledge layer; no dependency on the prior steps. Placed before the
    # SOUL step because that step returns early on a base without auto-zone
    # markers, and the tag census must run on such a base too.
    rc = _run_step("render_tags.py", [], args.dry_run)
    if rc != 0:
        print("regen_all: render_tags failed", file=sys.stderr)
        return rc

    # Step 6: SOUL — may be skipped if markers aren't in place yet
    from _common import system_dir  # local import — avoids polluting module load
    soul_path = system_dir() / "SOUL.md"
    if not _soul_has_markers(soul_path):
        if args.strict_soul:
            print(
                f"regen_all: SOUL.md at {soul_path} has no auto-zone markers "
                "(--strict-soul requires them)",
                file=sys.stderr,
            )
            return 2
        print(
            f"info: SOUL.md has no auto-zone markers yet — render_soul_values "
            "skipped. Add markers in the SOUL integration step.",
            file=sys.stderr,
        )
        # Exit 0. This is the DOCUMENTED graceful path — a base whose SOUL.md
        # has no auto-zone yet is healthy, and every view that could be
        # regenerated was. A distinct code here made every caller that checks
        # the exit status report a failure on a healthy run, which is the same
        # class of defect as a silent success: the status stops meaning what it
        # says. `--strict-soul` is how a caller that genuinely requires the SOUL
        # step asks for a failure.
        return 0

    soul_args: list[str] = []
    if args.write_soul_clarification:
        soul_args.append("--write-clarification")
    rc = _run_step("render_soul_values.py", soul_args, args.dry_run)
    if rc != 0:
        print("regen_all: render_soul_values failed", file=sys.stderr)
        return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
