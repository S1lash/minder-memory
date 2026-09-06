"""Render `## Health Snapshot` block for CURRENT_CONTEXT.md.

Reads:
  _system/state/biometric/baselines.json
  _system/state/biometric/streaks.json
  _system/state/biometric/correlations-{latest-week}.json
  _system/views/biometric/weekly-{latest-week}.md (just the path, not body)
  Latest biometric record under _records/biometric/
  _system/SOUL.md (Goals section, optional)

Output: a markdown block (≤ 15 lines normally; 5-line variant on
no-signal day). Caller (minder-mem-maintain) injects this between existing
sections of CURRENT_CONTEXT.md.

Layout choice (per SDD §16.5.5): inserted AFTER Identity/Focus block,
BEFORE Active Threads block. Caller responsible for placement.
"""

from __future__ import annotations

import json
import re
from datetime import date as date_cls
from pathlib import Path
from typing import Any


def _latest_biometric_record(records_dir: Path) -> dict[str, Any] | None:
    if not records_dir.exists():
        return None
    candidates = sorted(records_dir.glob("2*-*-*.md"), reverse=True)
    if not candidates:
        return None
    p = candidates[0]
    text = p.read_text(encoding="utf-8")
    return {"path": p, "text": text, "date": p.stem}


def _latest_correlations(state_dir: Path) -> dict[str, Any] | None:
    if not state_dir.exists():
        return None
    candidates = sorted(state_dir.glob("correlations-*.json"), reverse=True)
    if not candidates:
        return None
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def _soul_goals(soul_path: Path) -> list[str]:
    """Pull bullets from SOUL.md `## Goals` section. Returns list of
    natural-language goal strings."""
    if not soul_path.exists():
        return []
    text = soul_path.read_text(encoding="utf-8")
    m = re.search(r"\n##\s+Goals?\s*\n(.+?)(?=\n##\s|$)", text, re.DOTALL)
    if not m:
        return []
    body = m.group(1)
    return [
        line.lstrip("-* ").strip()
        for line in body.splitlines()
        if line.strip().startswith(("-", "*"))
    ]


def _adherence_for_goal(goal: str, baselines: dict[str, Any], records_dir: Path) -> str | None:
    """Best-effort match of a SOUL goal to biometric metric and report
    last-7-day adherence. Returns formatted line or None if no match."""
    g = goal.lower()
    metrics = baselines.get("metrics", {}) or {}
    # Sleep ≥ X
    m = re.search(r"sleep\s*(?:≥|>=|at least|min(?:imum)?)\s*([\d.]+)\s*h", g)
    if m and "sleep_h" in metrics:
        target = float(m.group(1))
        recent = _last_n_values(metrics["sleep_h"], 7)
        if recent:
            hits = sum(1 for v in recent if v >= target)
            return f"sleep ≥{target}h — {hits}/{len(recent)} this week"
    # workout / weekly N
    m = re.search(r"work[ -]?out\s*(\d+)\s*[x×]?\s*/?\s*week", g)
    if m:
        target = int(m.group(1))
        # rough: count days in last 7 with acute_load>0 — but baselines tracks numeric only
        # caller can refine; here surface the goal echo
        return f"workout {target}×/week — derived from records (see weekly view)"
    return None


def _last_n_values(metric_state: dict[str, Any], n: int) -> list[float]:
    vs = metric_state.get("values") or []
    return [v["value"] for v in vs[-n:]]


def render(
    base_dir: str | Path,
    *,
    source_id: str = "garmin",
    today: str | None = None,
) -> str:
    """Render the snapshot block for one wearable source. Returns multi-line
    markdown string. Records + derived state are read from the `{source_id}/`
    namespace; the caller renders one block per active metric-day source."""
    base = Path(base_dir)
    biometric_dir = base / "_records" / "biometric" / source_id
    state_dir = base / "_system" / "state" / "biometric" / source_id
    views_dir = base / "_system" / "views" / "biometric" / source_id
    soul = base / "_system" / "SOUL.md"

    today = today or date_cls.today().isoformat()

    baselines: dict[str, Any] = {}
    bp = state_dir / "baselines.json"
    if bp.exists():
        baselines = json.loads(bp.read_text(encoding="utf-8"))

    streaks: dict[str, Any] = {}
    sp = state_dir / "streaks.json"
    if sp.exists():
        streaks = json.loads(sp.read_text(encoding="utf-8"))

    correlations = _latest_correlations(state_dir) or {}
    latest_record = _latest_biometric_record(biometric_dir)
    weekly_views = sorted(views_dir.glob("weekly-*.md"), reverse=True) if views_dir.exists() else []

    active_streaks = (streaks.get("active") or {})
    has_signal = bool(active_streaks) or bool(_record_has_deviations(latest_record))

    if not has_signal:
        return _render_clean(
            today=today,
            latest_record=latest_record,
            weekly_views=weekly_views,
            soul_goals=_soul_goals(soul),
            baselines=baselines,
            base=base,
        )

    return _render_full(
        today=today,
        active_streaks=active_streaks,
        correlations=correlations,
        latest_record=latest_record,
        weekly_views=weekly_views,
        soul_goals=_soul_goals(soul),
        baselines=baselines,
        biometric_dir=biometric_dir,
        base=base,
    )


def _record_has_deviations(rec: dict[str, Any] | None) -> bool:
    if not rec:
        return False
    return "## Baseline Deviations" in rec["text"]


def _render_clean(
    *, today: str, latest_record: dict[str, Any] | None,
    weekly_views: list[Path], soul_goals: list[str],
    baselines: dict[str, Any], base: Path,
) -> str:
    parts = [
        "## Health Snapshot",
        f"**As of:** {today} — no active deviations, streaks, or cross-domain alarms.",
        f"**Recovery state:** {_recovery_one_liner(latest_record)}",
        f"**Goal adherence:** {_adherence_one_liner(soul_goals, baselines)}",
        f"**Last weekly insight:** {_link_weekly(weekly_views, base)}",
    ]
    return "\n".join(parts) + "\n"


def _render_full(
    *, today: str, active_streaks: dict[str, Any],
    correlations: dict[str, Any], latest_record: dict[str, Any] | None,
    weekly_views: list[Path], soul_goals: list[str],
    baselines: dict[str, Any], biometric_dir: Path, base: Path,
) -> str:
    lines = [
        "## Health Snapshot",
        f"**As of:** {today} (last 7d, baselines 28d)",
        "",
        "**Active streaks + life context:**",
    ]
    if active_streaks:
        for c in sorted(active_streaks.keys()):
            e = active_streaks[c]
            lines.append(f"- {c} {e['days']}d (started {e['started']})")
    else:
        lines.append("- (none)")

    # Last cross-domain link
    top = ((correlations.get("phase_2") or {}).get("top_findings") or [])
    p1 = ((correlations.get("phase_1") or {}).get("top_strong") or [])
    bridge = (top[:1] or p1[:1])
    if bridge:
        b = bridge[0]
        if "metric" in b and "affect" in b:
            lines.append("")
            lines.append("**Last cross-domain link** (latest weekly synthesis):")
            lines.append(
                f"- {b['metric']} ↔ {b['affect']} — {b.get('severity', 'medium')} "
                f"(r={b.get('r_pb', b.get('r'))}, n={b.get('n_total', b.get('n'))})"
            )
        else:
            lines.append("")
            lines.append("**Last cross-domain link** (latest weekly synthesis):")
            lines.append(
                f"- {b.get('a')} ↔ {b.get('b')} (lag {b.get('lag', 0)}) — "
                f"{b.get('severity', 'medium')} (r={b.get('r')}, n={b.get('n')})"
            )

    # This week's outliers
    outliers = _this_week_outliers(biometric_dir, today)
    if outliers:
        lines.append("")
        lines.append("**This week's outliers + context:**")
        for line in outliers[:3]:
            lines.append(f"- {line}")

    # Goal adherence
    goal_line = _adherence_one_liner(soul_goals, baselines)
    if goal_line and goal_line != "(none declared)":
        lines.append("")
        lines.append("**Goal adherence (from SOUL.md):**")
        lines.append(f"- {goal_line}")

    lines.append("")
    lines.append(f"**Last weekly insight:** {_link_weekly(weekly_views, base)}")
    lines.append(f"**Recovery state (current day):** {_recovery_one_liner(latest_record)}")

    block = "\n".join(lines) + "\n"
    return _cap_lines(block, 15)


def _this_week_outliers(biometric_dir: Path, today: str) -> list[str]:
    """Return 1-line summaries of per-day deviations in last 7 days."""
    if not biometric_dir.exists():
        return []
    out: list[str] = []
    days = sorted(biometric_dir.glob("2*-*-*.md"), reverse=True)[:7]
    for p in days:
        text = p.read_text(encoding="utf-8")
        if "## Baseline Deviations" not in text:
            continue
        # Take the first one or two deviation bullets.
        section = text.split("## Baseline Deviations", 1)[1]
        for line in section.splitlines():
            line = line.strip()
            if line.startswith("- "):
                out.append(f"{p.stem} {line[2:]}")
                break
    return out


def _link_weekly(weekly_views: list[Path], base: Path) -> str:
    if not weekly_views:
        return "(none yet — Tier II awaits 14+ days of records)"
    p = weekly_views[0]
    rel = p.relative_to(base) if p.is_relative_to(base) else p
    return f"[[{rel}]]"


def _recovery_one_liner(rec: dict[str, Any] | None) -> str:
    if not rec:
        return "(no record yet)"
    text = rec["text"]
    # try Key Numbers — readiness_lvl + train_status
    m = re.search(r"\n## Key Numbers\n+```yaml\n(.*?)\n```", text, re.DOTALL)
    if not m:
        return "data available — see record"
    parts = []
    for k in ("readiness_lvl", "train_status", "hrv_status"):
        mm = re.search(rf"^{k}:\s*(\S+)", m.group(1), re.MULTILINE)
        if mm:
            parts.append(f"{k.split('_')[0]}={mm.group(1)}")
    return "; ".join(parts) if parts else "see record"


def _adherence_one_liner(goals: list[str], baselines: dict[str, Any]) -> str:
    if not goals:
        return "(none declared)"
    bits: list[str] = []
    for g in goals[:2]:
        line = _adherence_for_goal(g, baselines, Path())
        if line:
            bits.append(line)
    return "; ".join(bits) if bits else "(SOUL goals not health-quantifiable)"


def _cap_lines(block: str, cap: int) -> str:
    """Cap rendered block at `cap` lines (excluding blanks). v1 soft cap."""
    lines = block.split("\n")
    if len(lines) <= cap + 5:
        return block
    return "\n".join(lines[: cap + 5]) + "\n"
