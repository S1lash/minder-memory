#!/usr/bin/env python3
"""Render SOUL.md Values auto-zone from 0_constitution/ core principles.

Writes deterministic content between the SOUL auto-markers:
    <!-- AUTO-GENERATED FROM CONSTITUTION — DO NOT EDIT MANUALLY -->
    ...
    <!-- END AUTO-GENERATED -->

Outside the markers, SOUL.md is hand-written and untouched.

Drift detection: if the current between-markers content differs from what
the script would render, and 0_constitution/ has NOT changed since last run,
it means someone edited the auto-zone by hand. The script surfaces this via
CLARIFICATION `soul-manual-edit-to-auto-zone` (when --write-clarification is
set) before overwriting.

Deterministic, no LLM. Filters by `core: true`, `status != placeholder`,
`scope in {shared, personal}`.

Usage:
    python3 render_soul_values.py [--dry-run] [--soul PATH]
                                  [--write-clarification]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from _common import (
    ConstitutionError,
    Principle,
    SOUL_MARKER_END,
    SOUL_MARKER_START,
    constitution_root,
    die,
    find_soul_auto_zone,
    iter_principles,
    now_iso_utc,
    repo_root,
    state_dir,
    system_dir,
    today_iso,
    configure_std_streams,
)


# In single-user dogfood phase SOUL.Values loads all three scopes (shared,
# personal, sensitive). SOUL is read by /minder:mem:process, /minder:mem:maintain, /minder:mem:lint
# system prompts, so this keeps the user's full identity visible to their own
# pipelines. Flip to {"shared", "personal"} when sharing scenarios land.
SOUL_VALUES_SCOPES = {"shared", "personal", "sensitive"}
CLARIFICATIONS_FILENAME = "CLARIFICATIONS.md"

# Marker used inside the auto-zone to record the hash of the source set
# at the time of last render. Lets subsequent runs distinguish a
# legitimate source-change refresh from a hand-edit drift.
SOURCE_HASH_COMMENT_PREFIX = "<!-- Source hash: "
SOURCE_HASH_COMMENT_SUFFIX = " -->"
SOURCE_HASH_RE = re.compile(
    re.escape(SOURCE_HASH_COMMENT_PREFIX) + r"([0-9a-f]+)" + re.escape(SOURCE_HASH_COMMENT_SUFFIX)
)


def select_for_soul(principles: list[Principle]) -> list[Principle]:
    selected = [
        p for p in principles
        if p.is_core
        and not p.is_placeholder
        and p.scope in SOUL_VALUES_SCOPES
    ]
    order = {"axiom": 0, "principle": 1, "rule": 2}
    selected.sort(key=lambda p: (order.get(p.type, 99), p.id))
    return selected


def compute_source_hash(principles: list[Principle]) -> str:
    """SHA-256 over the rendered-body-relevant content of the selected
    principles. Used to distinguish refresh vs hand-edit drift.

    Input is order-stable (principles already sorted by caller) and
    timestamp-free, so the hash is deterministic across runs when source
    has not changed.
    """
    h = hashlib.sha256()
    for p in principles:
        h.update(p.id.encode("utf-8"))
        h.update(b"\x00")
        h.update(p.title.encode("utf-8"))
        h.update(b"\x00")
        h.update(p.statement.encode("utf-8"))
        h.update(b"\x01")
    return h.hexdigest()


def render_values_body(principles: list[Principle], source_hash: str) -> str:
    """Content that goes between markers (excluding the markers themselves).

    Empty-principle case emits a single placeholder line so markers remain
    distinguishable in diffs. The source_hash stays stable across runs while
    source is unchanged — it is the signal used to tell refresh from drift.
    """
    lines: list[str] = []
    lines.append(f"<!-- Sourced from: 0_constitution/ where core=true, "
                 f"status!=placeholder, scope in {sorted(SOUL_VALUES_SCOPES)} -->")
    lines.append(f"{SOURCE_HASH_COMMENT_PREFIX}{source_hash}{SOURCE_HASH_COMMENT_SUFFIX}")
    lines.append(f"<!-- Last regenerated: {now_iso_utc()} -->")
    lines.append("# Values (constitution core)")
    lines.append("")
    if not principles:
        lines.append("_No core principles landed yet. Placeholder status notes are "
                     "excluded from this view._")
        lines.append("")
    else:
        for p in principles:
            lines.append(f"- **{p.title}** — {p.statement}")
        lines.append("")
    return "\n".join(lines)


def extract_source_hash(auto_zone_text: str) -> str | None:
    """Return the source hash recorded in the auto-zone, or None if the
    marker is absent (first-render or pre-upgrade state)."""
    m = SOURCE_HASH_RE.search(auto_zone_text)
    return m.group(1) if m else None


def _count_marker_pairs(text: str) -> tuple[int, int]:
    return text.count(SOUL_MARKER_START), text.count(SOUL_MARKER_END)


def splice_into_soul(soul_text: str, new_body: str) -> str:
    start_count, end_count = _count_marker_pairs(soul_text)
    if start_count == 0 or end_count == 0:
        raise ConstitutionError(
            "SOUL.md does not contain the required markers:\n"
            f"  {SOUL_MARKER_START}\n"
            f"  {SOUL_MARKER_END}\n"
            "Add them in the SOUL integration step before running this script."
        )
    if start_count != 1 or end_count != 1:
        raise ConstitutionError(
            f"SOUL.md has {start_count} start markers and {end_count} end "
            f"markers — exactly one pair is required. Remove the duplicates."
        )
    bounds = find_soul_auto_zone(soul_text)
    if bounds is None:
        raise ConstitutionError(
            "SOUL.md has markers but they are out of order (END before START) "
            "or malformed. Fix the order."
        )
    content_start, content_end = bounds
    # Ensure new_body ends with newline so marker stays on own line
    if not new_body.endswith("\n"):
        new_body += "\n"
    return soul_text[:content_start] + new_body + soul_text[content_end:]


def current_auto_zone(soul_text: str) -> str | None:
    bounds = find_soul_auto_zone(soul_text)
    if bounds is None:
        return None
    start, end = bounds
    return soul_text[start:end]


def append_clarification_drift(path: Path, current: str, expected: str) -> None:
    """Append a `soul-manual-edit-to-auto-zone` CLARIFICATION.

    Idempotent-ish: adds a new dated entry each call. Resolution is human.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    entry_date = today_iso()
    block = [
        "",
        f"### {entry_date} — soul-manual-edit-to-auto-zone",
        "",
        "**Type:** soul-manual-edit-to-auto-zone",
        f"**Source:** _system/SOUL.md auto-zone (between constitution markers)",
        "**Action taken:** render_soul_values.py detected manually-edited content "
        "between SOUL auto-markers that does not match the deterministic render.",
        "**Uncertainty:** The user may have intended to edit a principle under "
        "`0_constitution/`, but edited the generated view by mistake.",
        "**To resolve:** Copy the intended change into the relevant "
        "`0_constitution/{type}/{domain}/*.md` and run "
        "`/minder:mem:regen-constitution`. The auto-zone will be overwritten.",
        "",
        "**Expected render (next overwrite will produce this):**",
        "",
        "```",
        expected.rstrip(),
        "```",
        "",
        "**Current content in auto-zone:**",
        "",
        "```",
        current.rstrip(),
        "```",
        "",
    ]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(block))


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print rendered SOUL.md to stdout without writing")
    parser.add_argument("--soul", type=Path, default=None,
                        help="override SOUL.md path (default: _system/SOUL.md)")
    parser.add_argument(
        "--write-clarification", action="store_true",
        help="when drift is detected, append a CLARIFICATION entry before overwrite",
    )
    parser.add_argument(
        "--clarifications", type=Path, default=None,
        help=f"override CLARIFICATIONS.md path (default: _system/state/{CLARIFICATIONS_FILENAME})",
    )
    args = parser.parse_args(argv)

    try:
        principles = iter_principles(constitution_root())
    except ConstitutionError as exc:
        die(str(exc))

    soul_path = args.soul or (system_dir() / "SOUL.md")
    if not soul_path.exists():
        die(f"SOUL.md not found at {soul_path}")

    soul_text = soul_path.read_text(encoding="utf-8")
    selected = select_for_soul(principles)
    new_source_hash = compute_source_hash(selected)
    expected_body = render_values_body(selected, new_source_hash)
    try:
        new_soul = splice_into_soul(soul_text, expected_body)
    except ConstitutionError as exc:
        die(str(exc))

    current = current_auto_zone(soul_text)
    if current is None:
        die(
            f"SOUL.md at {soul_path} is missing the auto-zone markers. "
            "Place them in the SOUL integration step."
        )

    def normalise(s: str) -> str:
        """Drop dynamic/volatile metadata lines and strip trailing whitespace
        per line. Timestamp and source-hash comments are ignored in the diff;
        only user-visible body content counts for drift comparison."""
        lines = []
        for line in s.splitlines():
            stripped = line.strip()
            if stripped.startswith("<!-- Last regenerated:"):
                continue
            if stripped.startswith(SOURCE_HASH_COMMENT_PREFIX):
                continue
            lines.append(line.rstrip())
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    old_source_hash = extract_source_hash(current)
    body_differs = normalise(current) != normalise(expected_body)
    source_changed = old_source_hash != new_source_hash

    # Drift = hand-edit of auto-zone: body differs AND source is unchanged.
    # If source has changed, any body difference is a legitimate refresh
    # (expected behaviour) and must NOT be reported as drift.
    # Pre-upgrade auto-zones without a source hash marker are treated as
    # legitimate refresh on first encounter (source_changed := True).
    if old_source_hash is None:
        source_changed = True
    drift_detected = body_differs and not source_changed

    if args.dry_run:
        sys.stdout.write(new_soul)
        if drift_detected:
            print(f"\n[dry-run] hand-edit DRIFT detected in {soul_path.name} auto-zone",
                  file=sys.stderr)
        elif source_changed and body_differs:
            print(f"\n[dry-run] refreshing {soul_path.name} from source change",
                  file=sys.stderr)
        return 0

    if drift_detected and args.write_clarification:
        clar_path = args.clarifications or (state_dir() / CLARIFICATIONS_FILENAME)
        append_clarification_drift(clar_path, current, expected_body)
        print(f"hand-edit drift → CLARIFICATION appended to {clar_path}",
              file=sys.stderr)

    # Atomic write — avoid partial SOUL on interrupt.
    tmp = soul_path.with_suffix(soul_path.suffix + ".tmp")
    tmp.write_text(new_soul, encoding="utf-8")
    tmp.replace(soul_path)

    if drift_detected:
        status = "hand-edit drift overwritten"
    elif source_changed and body_differs:
        status = "refreshed from source change"
    elif body_differs:
        status = "body updated"
    else:
        status = "no change"
    print(f"wrote {soul_path} ({len(selected)} core principles, {status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
