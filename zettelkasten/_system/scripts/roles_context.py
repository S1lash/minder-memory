#!/usr/bin/env python3
"""What one role is given — the assembled prompt for a single run.

Reads, never writes. Six parts in a fixed order, each starting on its own
line so a mechanic and an instruction can never share one:

1. `_system/roles/_run-frame.md`, rendered. Engine-owned, ships as a
   template, and this module only substitutes placeholders into a copy —
   the file on disk is never touched. Its ABSENCE IS A HARD ERROR: it means
   a broken install, and tolerating it would run a role with no mechanics.
   The one thing the renderer decides rather than substitutes: a role that
   declares no `secrets:` never sees the credentials passage at all. Handing
   it the store's path and the recipe to source it is a map it never asked
   for, and an invitation to fail over credentials it never had.
2. `_system/roles/_minder.md` verbatim, or a marker. It is prose, and a role
   can still do useful work without it.
3. `_system/views/constitution-core.md` verbatim, only when the role asked
   for it, or a marker. A derived view's absence means the owner never
   regenerated it, not that the install is broken — deliberately a different
   posture from the run frame.
4. The previous run line. Without it a role cannot detect that its
   predecessor died mid-flight, and it will redo an already-performed
   outward act.
5. The role's own body, verbatim and unparsed.
6. The inventory of its `state/` tree.

`{{NOW_LOCAL}}` exists because a role whose question is "the last week" must
not derive today's date from the ambient harness: under an injected `--now`
the runner and the role would disagree about what day it is.

Budget: content only. Header lines are not charged against it, so the
inventory of a role with many small files cannot be squeezed out by its own
headers. A file larger than what REMAINS of the budget is inlined up to what
remains and marked INSIDE its own block, never demoted to a name-only entry —
a role whose entire job is to maintain one large document would otherwise be
handed the name of the file it must update and none of its content, and
would regenerate it from scratch, destroying the accumulated work while
every surface reported success. Only when nothing remains does a file join
the `[state truncated: N more files]` listing, because a truncated block with
no content under it tells the role less than a name and a size do.

Every read passes `encoding="utf-8"` explicitly; a file that is not
decodable is listed as binary and never inlined.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import roles_config

RUN_FRAME_NAME = "_run-frame.md"
MINDER_NAME = "_minder.md"
CONSTITUTION_VIEW_REL_TO_BASE = "_system/views/constitution-core.md"

DEFAULT_BUDGET = 40_000

MINDER_MISSING = "[_minder.md missing — base conventions unavailable]"
CONSTITUTION_MISSING = (
    "[constitution-core.md missing — run /minder:mem:regen-constitution]"
)
PREVIOUS_RUN_NONE = "[previous run: none]"

SECTION_FRAME = "### RUN FRAME"
SECTION_BASE = "### BASE CONVENTIONS"
SECTION_CONSTITUTION = "### CONSTITUTION CORE"
SECTION_PREVIOUS = "### PREVIOUS RUN"
SECTION_ROLE = "### ROLE"
SECTION_STATE = "### STATE"

EMPTY_LIST_RENDERING = "(none)"
NO_LAST_RUN_RENDERING = "none"

# The two placeholders that make a passage of the frame be ABOUT credentials.
# They are also how the credentials passage is located when a role declares
# none — identified by the placeholders this module already fills, never by a
# copy of the frame's heading text, which is prose and will be reworded.
PLACEHOLDER_SECRETS_FILE = "{{SECRETS_FILE}}"
PLACEHOLDER_SECRET_NAMES = "{{SECRET_NAMES}}"
SECRET_PLACEHOLDERS = (PLACEHOLDER_SECRETS_FILE, PLACEHOLDER_SECRET_NAMES)

# A markdown horizontal rule alone on its line — the frame's own section
# boundary. Captured, so the template's exact separators survive a removal.
_SECTION_RULE_RE = re.compile(r"(\n-{3,}[ \t]*\n)")


def run_frame_path(base: Path) -> Path:
    return roles_config.roles_root(base) / RUN_FRAME_NAME


def minder_path(base: Path) -> Path:
    return roles_config.roles_root(base) / MINDER_NAME


def constitution_view_path(base: Path) -> Path:
    return base.joinpath(*CONSTITUTION_VIEW_REL_TO_BASE.split("/"))


def _mentions_secrets(chunk: str) -> bool:
    return any(placeholder in chunk for placeholder in SECRET_PLACEHOLDERS)


def _drop_credentials_passage(template: str) -> str:
    """Remove the frame's credentials passage, for a role that declares none.

    A role with no `secrets:` has no business being handed the absolute path
    of the credential store and the recipe to source it: it is a map it never
    asked for, it costs context in the one file whose budget discipline
    exists because context is finite, and it invites an `error` outcome over
    credentials the role never had. §6 concedes that `secrets:` is a
    declaration and not a boundary — an accepted residual about what a role
    CAN reach, not a licence to point at it.

    The passage is located by the placeholders this module fills, never by
    the frame's heading text: the frame is prose and will be reworded, and a
    heading copied into this module is a drift site.

    The unit removed is the smallest one the template itself offers. A frame
    with horizontal-rule sections loses the whole section, separator
    included; a flat `key: {{PLACEHOLDER}}` frame, which has no sections to
    speak of, loses exactly those lines. Nothing else is touched either way.
    """
    parts = _SECTION_RULE_RE.split(template)
    if len(parts) > 1:
        keep = [True] * len(parts)
        for index in range(0, len(parts), 2):          # even entries are blocks
            if not _mentions_secrets(parts[index]):
                continue
            keep[index] = False
            # Drop one adjacent separator too, or the removal leaves a pair
            # of rules with nothing between them.
            if index > 0:
                keep[index - 1] = False
            elif index + 1 < len(parts):
                keep[index + 1] = False
        if not all(keep):
            return "".join(part for part, kept in zip(parts, keep) if kept)
    return "\n".join(
        line for line in template.split("\n") if not _mentions_secrets(line)
    )


def _read_utf8(path: Path) -> str | None:
    """File content, or `None` when it is absent or not decodable UTF-8."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _header_path(path: Path, repo: Path) -> str:
    """The path as it appears in a state header line.

    `to_repo_relative` returns `None` for a state tree outside the repo —
    unusual but not fatal here, so the header falls back to the absolute
    POSIX path rather than dropping the file from the inventory.
    """
    relative = roles_config.to_repo_relative(repo, path)
    return relative if relative is not None else path.as_posix()


def _render_prefixes(cfg) -> str:
    rendered = [prefix.path for prefix in cfg.write_prefixes]
    return ", ".join(rendered) if rendered else EMPTY_LIST_RENDERING


def _render_frame(base: Path, repo: Path, cfg, now: datetime,
                  last_run_line: dict | None) -> str:
    text = _read_utf8(run_frame_path(base))
    if text is None:
        raise FileNotFoundError(
            f"{run_frame_path(base)}: {RUN_FRAME_NAME} is engine-owned and "
            f"missing — the install is broken; a role must not run without "
            f"its mechanics"
        )
    if not cfg.secrets:
        text = _drop_credentials_passage(text)
    last_ts = (last_run_line or {}).get("ts") or NO_LAST_RUN_RENDERING
    substitutions = {
        "{{ROLE_ID}}": cfg.id,
        "{{ROLE_NAME}}": cfg.name,
        "{{REPO_ROOT}}": str(repo),
        "{{BASE}}": str(base),
        "{{STATE_DIR}}": str(cfg.state_dir),
        "{{ALLOWED_WRITES}}": _render_prefixes(cfg),
        PLACEHOLDER_SECRETS_FILE: str(roles_config.secrets_file(base)),
        PLACEHOLDER_SECRET_NAMES: ", ".join(cfg.secrets) or EMPTY_LIST_RENDERING,
        "{{NOW_LOCAL}}": now.isoformat(timespec="minutes"),
        "{{LAST_RUN}}": str(last_ts),
    }
    for placeholder, value in substitutions.items():
        text = text.replace(placeholder, value)
    return text.strip()


def _render_previous_run(last_run_line: dict | None) -> str:
    if not last_run_line:
        return PREVIOUS_RUN_NONE
    note = last_run_line.get("note")
    return (
        f"[previous run: outcome={last_run_line.get('outcome')} "
        f"ts={last_run_line.get('ts')} "
        f"note={'null' if note is None else note}]"
    )


def _state_entries(cfg, repo: Path) -> list:
    """Every file under `state/`, sorted, as `(rel, byte size, text|None)`.

    `text` is `None` for a file that is not inlinable: a NUL byte or an
    undecodable sequence. The NUL test is git's own rule and catches the
    file that decodes as UTF-8 but is plainly not text.
    """
    state_dir: Path = cfg.state_dir
    if not state_dir.is_dir():
        return []
    entries = []
    for path in sorted((p for p in state_dir.rglob("*") if p.is_file()),
                       key=lambda p: p.as_posix()):
        rel = _header_path(path, repo)
        try:
            data = path.read_bytes()
        except OSError:
            entries.append((rel, 0, None))
            continue
        if b"\x00" in data:
            entries.append((rel, len(data), None))
            continue
        try:
            entries.append((rel, len(data), data.decode("utf-8")))
        except UnicodeDecodeError:
            entries.append((rel, len(data), None))
    return entries


def _render_state(cfg, repo: Path, budget: int) -> list:
    """The state inventory: header lines plus inlined content, within budget."""
    blocks: list = []
    remaining = budget
    entries = _state_entries(cfg, repo)
    for index, (rel, size, text) in enumerate(entries):
        if text is None:
            blocks.append(f"{rel} (binary, {size} bytes)")
            continue
        length = len(text)
        if length <= remaining:
            blocks.append(f"{rel} ({size} bytes)\n{text}")
            remaining -= length
            continue
        if remaining > 0:
            # Larger than what REMAINS: inline what remains and say so inside
            # the block, marked with the file's full size. Some of the file
            # beats none — a role handed the name of the one document it
            # maintains and none of its content regenerates it from scratch.
            blocks.append(
                f"{rel} ({size} bytes)\n{text[:remaining]}\n"
                f"[truncated: {remaining} of {length} characters shown]"
            )
            remaining = 0
            continue
        # Nothing remains: listing the file beats a truncated block with no
        # content under it.
        rest = entries[index:]
        blocks.append(f"[state truncated: {len(rest)} more files]")
        for tail_rel, tail_size, _ in rest:
            blocks.append(f"{tail_rel} ({tail_size} bytes)")
        break
    return blocks


def build_context(base: Path, repo: Path, cfg, *, now: datetime,
                  last_run_line: dict | None, budget: int = DEFAULT_BUDGET) -> str:
    """Assemble the prompt for one run of one role. Reads, never writes."""
    parts = [SECTION_FRAME, _render_frame(base, repo, cfg, now, last_run_line)]

    parts.append(SECTION_BASE)
    minder = _read_utf8(minder_path(base))
    parts.append(MINDER_MISSING if minder is None else minder.strip())

    if cfg.constitution:
        parts.append(SECTION_CONSTITUTION)
        view = _read_utf8(constitution_view_path(base))
        parts.append(CONSTITUTION_MISSING if view is None else view.strip())

    parts.append(SECTION_PREVIOUS)
    parts.append(_render_previous_run(last_run_line))

    parts.append(SECTION_ROLE)
    parts.append(cfg.body.strip())

    state_blocks = _render_state(cfg, repo, budget)
    if state_blocks:
        parts.append(SECTION_STATE)
        parts.extend(state_blocks)

    return "\n\n".join(parts) + "\n"
