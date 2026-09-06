"""Persistence helpers for `/minder:mem:resolve-clarifications`.

Two append-only artefacts:

  - **Session log** — one markdown file per resolve session under
    `_system/state/resolve-sessions/{date}-{session-id}.md`. Captures
    auto-applied actions, constitution-vetoed proposals, and (for
    interactive sessions) per-item owner reasoning. Owner-readable.

  - **History JSONL** — `_system/state/lens-resolution-history.jsonl`,
    one JSON object per line. Structured precedent index consumed by
    smart_resolve as input to its «would the experienced owner approve
    this NOW?» reasoning. WRITES ONLY happen on owner clicks in
    interactive mode — auto-mode applies do NOT write here (engine
    never trains on engine).

Both writers are append-only and idempotent under re-run by session-id
(callers handle dedup by passing the same `session_id`). The session
log's «Auto-applied» / «Owner decisions» sections are accreted across
the session via `append_*` calls; finalisation writes the closing
frontmatter when the session ends.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from _common import state_dir


# ---------------------------------------------------------------------------
# Paths + filesystem helpers
# ---------------------------------------------------------------------------

def _now_iso_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def session_id() -> str:
    """Six-hex-char session id (collision-resistant inside one day)."""
    return secrets.token_hex(3)


def sessions_dir(base: Path | None = None) -> Path:
    return state_dir(base) / "resolve-sessions"


def session_log_path(sid: str, base: Path | None = None, *, day: str | None = None) -> Path:
    return sessions_dir(base) / f"{day or _today_iso()}-{sid}.md"


def history_jsonl_path(base: Path | None = None) -> Path:
    return state_dir(base) / "lens-resolution-history.jsonl"


# ---------------------------------------------------------------------------
# Session log
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    """In-memory session accumulator. Caller flushes via `write_session_log`."""
    sid: str
    started_at: str
    mode: str  # "interactive" | "auto"
    trigger: str  # "owner" | "lint"
    auto_applied: list[dict] = field(default_factory=list)
    constitution_vetoed: list[dict] = field(default_factory=list)
    owner_decisions: list[dict] = field(default_factory=list)
    extracted_artefacts: list[dict] = field(default_factory=list)
    items_total: int = 0
    items_deferred: int = 0


def new_session(mode: str, trigger: str) -> SessionState:
    if mode not in {"interactive", "auto"}:
        raise ValueError(f"unknown mode: {mode!r}")
    if trigger not in {"owner", "lint", "scheduler"}:
        raise ValueError(f"unknown trigger: {trigger!r}")
    return SessionState(sid=session_id(), started_at=_now_iso_z(), mode=mode, trigger=trigger)


def _frontmatter(state: SessionState, ended_at: str) -> str:
    counts = {
        "items_total": state.items_total,
        "items_auto_applied": len(state.auto_applied),
        "items_owner_approved": sum(1 for d in state.owner_decisions if d.get("decision") == "approve"),
        "items_owner_rejected": sum(1 for d in state.owner_decisions if d.get("decision") == "reject"),
        "items_owner_modified": sum(1 for d in state.owner_decisions if d.get("decision") == "modify"),
        "items_deferred": state.items_deferred,
        "items_constitution_veto": len(state.constitution_vetoed),
        "items_extracted_approved": sum(1 for e in state.extracted_artefacts if e.get("decision") == "approved"),
        "items_extracted_declined": sum(1 for e in state.extracted_artefacts if e.get("decision") in {"declined", "declined_at_diff"}),
    }
    lines = [
        "---",
        f"session_id: {state.sid}",
        f"started_at: {state.started_at}",
        f"ended_at: {ended_at}",
        f"mode: {state.mode}",
        f"trigger: {state.trigger}",
    ]
    for k, v in counts.items():
        lines.append(f"{k}: {v}")
    lines += [
        "origin: personal",
        "audience_tags: []",
        "is_sensitive: true",
        "---",
    ]
    return "\n".join(lines) + "\n"


def _render_auto(state: SessionState) -> str:
    if not state.auto_applied:
        return "## Auto-applied\n\n_(none this session)_\n"
    out = ["## Auto-applied (no owner interaction)", ""]
    for entry in state.auto_applied:
        out.append(f"- **{entry['type']}** — {entry.get('summary', '')}")
        out.append(f"  - Source: {entry.get('source_lens', 'unknown')}")
        if entry.get("targets"):
            out.append(f"  - Targets: {', '.join(entry['targets'])}")
        if entry.get("reasoning"):
            out.append(f"  - Reasoning: {entry['reasoning']}")
    out.append("")
    return "\n".join(out)


def _render_veto(state: SessionState) -> str:
    if not state.constitution_vetoed:
        return ""
    out = ["## Constitution-vetoed", ""]
    for entry in state.constitution_vetoed:
        out.append(f"- **{entry['type']}** — {entry.get('summary', '')}")
        out.append(f"  - Veto reason: {entry.get('veto_reason', '—')}")
        out.append("  - Status: queued for owner; can override via `_system/state/insights-config.yaml`.")
    out.append("")
    return "\n".join(out)


def _render_decisions(state: SessionState) -> str:
    if not state.owner_decisions:
        return ""
    out = ["## Owner decisions", ""]
    for n, entry in enumerate(state.owner_decisions, start=1):
        out.append(f"### #{n} — {entry.get('type', '?')} ({entry.get('source_lens', 'unknown')})")
        if entry.get("proposal"):
            out.append(f"**Proposal:** {entry['proposal']}")
        if entry.get("smart_reasoning"):
            out.append(f"**Smart_resolve reasoning:** {entry['smart_reasoning']}")
        out.append(f"**Owner action:** {entry.get('decision', '?')}")
        if entry.get("owner_comment"):
            out.append(f"**Owner comment:** {entry['owner_comment']}")
        if entry.get("applied_target"):
            out.append(f"**Applied:** {entry['applied_target']}")
        if entry.get("inferred_pattern"):
            out.append(f"**Inferred pattern:** {entry['inferred_pattern']}")
        out.append("")
    return "\n".join(out)


def _render_extracted(state: SessionState) -> str:
    if not state.extracted_artefacts:
        return ""
    out = ["## Extracted artefacts (Step 6.5)", ""]
    for n, entry in enumerate(state.extracted_artefacts, start=1):
        out.append(f"### #{n} — {entry.get('class', '?')} from {entry.get('q_ref', '?')}")
        if entry.get("target_path"):
            out.append(f"**Target:** `{entry['target_path']}`")
        if entry.get("confidence") is not None:
            out.append(f"**Confidence (at proposal):** {entry['confidence']}")
        out.append(f"**Decision:** {entry.get('decision', '?')}")
        if entry.get("summary"):
            out.append(f"**Суть:** {entry['summary']}")
        if entry.get("owner_comment"):
            out.append(f"**Owner comment:** {entry['owner_comment']}")
        out.append("")
    return "\n".join(out)


def write_session_log(state: SessionState, base: Path | None = None) -> Path:
    """Flush the in-memory session accumulator to disk.

    Idempotent: re-running with the same `state.sid` overwrites the
    file (callers should not rotate sid mid-session). Returns the
    written path.
    """
    sessions_dir(base).mkdir(parents=True, exist_ok=True)
    path = session_log_path(state.sid, base)
    body_parts = [
        _frontmatter(state, ended_at=_now_iso_z()),
        f"# Resolve session {state.started_at}",
        "",
        _render_auto(state),
    ]
    veto = _render_veto(state)
    if veto:
        body_parts.append(veto)
    decisions = _render_decisions(state)
    if decisions:
        body_parts.append(decisions)
    extracted = _render_extracted(state)
    if extracted:
        body_parts.append(extracted)
    path.write_text("\n".join(body_parts), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# History JSONL — interactive-mode writes only
# ---------------------------------------------------------------------------

def append_history(entry: dict, base: Path | None = None) -> None:
    """Append one structured precedent row to lens-resolution-history.jsonl.

    Caller MUST populate at minimum: `ts`, `session_ref`, `class_key`,
    `decision`, `proposal_summary`, `salient_features`. The schema
    matches `_planning/sdd-lens-action-routing.md` §4.5 and is consumed
    by smart_resolve as precedent corpus.
    """
    required = {"ts", "session_ref", "class_key", "decision", "proposal_summary", "salient_features"}
    missing = required - set(entry)
    if missing:
        raise ValueError(f"history entry missing required fields: {sorted(missing)}")
    path = history_jsonl_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_history(base: Path | None = None, *, recent_n: int | None = None) -> list[dict]:
    """Return parsed history rows, oldest first. Tolerant of malformed lines."""
    path = history_jsonl_path(base)
    if not path.is_file():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # Tolerate corruption (rare); resolver should surface a CLARIFICATION.
            continue
    if recent_n is not None and recent_n >= 0:
        rows = rows[-recent_n:]
    return rows


# ---------------------------------------------------------------------------
# Convenience helpers used by tests + resolver prose
# ---------------------------------------------------------------------------

def class_key(lens_id: str, action_type: str, confidence: str) -> str:
    """Canonical class-key used both in history rows and config overrides.

    Mirrors `_system/state/insights-config.yaml.template → classes:` keys.
    """
    return f"{lens_id}__{action_type}__{confidence}"
