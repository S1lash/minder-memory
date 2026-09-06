"""Activity weekly worker — at-a-glance weekly rollup of computer-usage days.

Mirrors `biometric_weekly_worker`: triggered by `/minder:mem:maintain` after-batch,
idempotent weekly gate via `_system/state/activity/{source}/last_weekly_run.txt`,
ISO-week keyed, backfill on first run. Pure deterministic Python — no LLM.

Reads each ISO week's `_records/activity/{source}/*.md` Key Numbers and the
Summary "Top categories:" line (working days only — idle days with
`active_h < 0.5` are absence, not signal, and are skipped). Computes a weekly
rollup the owner can glance at and the weekly-insights lens can read cleanly.

Outputs (per processed ISO week):
  _system/state/activity/{source}/weekly-{YYYY-Www}.json   (machine rollup)
  _system/views/activity/{source}/weekly-{YYYY-Www}.md     (human glance)
  _system/state/activity/{source}/last_weekly_run.txt      (single line gate)

The view carries privacy frontmatter `origin: personal / audience_tags: [] /
is_sensitive: true` — category labels can leak work/client context.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date as date_cls, timedelta
from pathlib import Path

from _common import configure_std_streams  # type: ignore
from statistics import median
from typing import Any

import yaml


# Idle/absence threshold — a near-off Mac day is not "low deep work". Mirrors
# `metric_day_profiles._ACTIVITY_BASELINE_MIN_ACTIVE_H`: feeding its zeros would
# corrupt the weekly medians the same way it would the baselines.
_WORKING_DAY_MIN_ACTIVE_H = 0.5

# Scores summarised with median + min/max across the working days of a week.
_SCORE_METRICS: tuple[str, ...] = (
    "combined_score",
    "productivity_score",
    "focus_score",
)

# Other numeric Key Numbers rolled up as weekly medians.
_ROLLUP_MEDIAN_METRICS: tuple[str, ...] = (
    "human_switches_per_active_hour",
    "human_switches",
    "sustained_focus_h",
    "longest_focus_block_min",
    "meeting_h",
    "late_night_ratio",
    "late_night_h",
    "early_morning_h",
    "active_h",
)

# Weekly totals (sum across working days).
_ROLLUP_SUM_METRICS: tuple[str, ...] = (
    "meeting_h",
    "sustained_focus_h",
    "active_h",
    "work_h",
    "personal_h",
)

# A day counts as "late-night" / "early-morning" when its ratio/hours cross a
# small floor — used for the rhythm summary (how many days ran late vs early).
_LATE_NIGHT_DAY_RATIO = 0.10
_EARLY_MORNING_DAY_H = 0.25


def _iso_week_label(d: date_cls) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_bounds(d: date_cls) -> tuple[date_cls, date_cls]:
    """Monday..Sunday of the ISO week containing d."""
    monday = d - timedelta(days=d.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


_DURATION_RE = re.compile(r"(\d+)\s*([hms])")


def _duration_to_seconds(token: str) -> int:
    """'4h 41m' / '53s' / '2h 25m 10s' → seconds. Unparseable → 0."""
    total = 0
    for value, unit in _DURATION_RE.findall(token):
        n = int(value)
        if unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        else:
            total += n
    return total


def _parse_top_categories(summary_text: str) -> dict[str, int]:
    """Parse the Summary 'Top categories:' line → {category: seconds}.

    Format: '- **Top categories:** deep_work 4h 41m, vpn_remote 1m, ...'.
    Category time lives in the day record's Summary (the source-level
    `seconds_by_category` is not re-surfaced as Key Numbers); this is the
    deterministic record-only read."""
    out: dict[str, int] = {}
    m = re.search(r"\*\*Top categories:\*\*\s*(.+)", summary_text)
    if not m:
        return out
    for chunk in m.group(1).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        # '<category> <duration>' — split on first whitespace run after the name.
        cm = re.match(r"([A-Za-z0-9_]+)\s+(.+)", chunk)
        if not cm:
            continue
        cat, dur = cm.group(1), cm.group(2)
        secs = _duration_to_seconds(dur)
        if secs > 0:
            out[cat] = out.get(cat, 0) + secs
    return out


@dataclass
class _DayMetrics:
    date: str
    numbers: dict[str, float]
    categories: dict[str, int]
    top_death_loop: str | None
    distracting_loop_count: int


def _read_day(path: Path) -> _DayMetrics | None:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"\n## Key Numbers\n+```yaml\n(.*?)\n```", text, re.DOTALL)
    if not m:
        return None
    kn = yaml.safe_load(m.group(1)) or {}
    numbers: dict[str, float] = {}
    for k, v in kn.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            numbers[k] = float(v)
    summary = text.split("## Key Numbers", 1)[0]
    return _DayMetrics(
        date=path.stem,
        numbers=numbers,
        categories=_parse_top_categories(summary),
        top_death_loop=(str(kn["top_death_loop"]) if kn.get("top_death_loop") else None),
        distracting_loop_count=int(kn.get("distracting_loop_count") or 0),
    )


def _read_working_days(records_dir: Path, mon: date_cls, sun: date_cls) -> list[_DayMetrics]:
    """Records in [mon, sun] with active_h >= the working-day floor."""
    days: list[_DayMetrics] = []
    if not records_dir.exists():
        return days
    for p in sorted(records_dir.glob("2*-*-*.md")):
        if not (mon.isoformat() <= p.stem <= sun.isoformat()):
            continue
        dm = _read_day(p)
        if dm is None:
            continue
        active = dm.numbers.get("active_h")
        if active is None or active < _WORKING_DAY_MIN_ACTIVE_H:
            continue
        days.append(dm)
    return days


_DEATH_LOOP_PAIR_RE = re.compile(r"^(.*?)\s*×(\d+)")


def _death_loop_pair(label: str) -> tuple[str, int]:
    """'Google Chrome <-> Slack ×216 (mixed)' → ('Google Chrome <-> Slack', 216)."""
    m = _DEATH_LOOP_PAIR_RE.match(label.strip())
    if not m:
        return label.strip(), 0
    return m.group(1).strip(), int(m.group(2))


def _stat_block(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "median": round(median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _compute_rollup(days: list[_DayMetrics]) -> dict[str, Any]:
    scores: dict[str, dict[str, float]] = {}
    for metric in _SCORE_METRICS:
        vals = [d.numbers[metric] for d in days if metric in d.numbers]
        block = _stat_block(vals)
        if block:
            scores[metric] = block

    medians: dict[str, float] = {}
    for metric in _ROLLUP_MEDIAN_METRICS:
        vals = [d.numbers[metric] for d in days if metric in d.numbers]
        if vals:
            medians[metric] = round(median(vals), 2)

    totals: dict[str, float] = {}
    for metric in _ROLLUP_SUM_METRICS:
        vals = [d.numbers[metric] for d in days if metric in d.numbers]
        if vals:
            totals[metric] = round(sum(vals), 2)

    # Category-time trend: sum seconds across the week, rank top categories.
    cat_seconds: dict[str, int] = {}
    for d in days:
        for cat, secs in d.categories.items():
            cat_seconds[cat] = cat_seconds.get(cat, 0) + secs
    top_categories = sorted(cat_seconds.items(), key=lambda kv: kv[1], reverse=True)

    # Recurring death-loop pairs aggregated across the week.
    loop_counts: dict[str, int] = {}
    loop_days: dict[str, int] = {}
    distracting_total = 0
    for d in days:
        distracting_total += d.distracting_loop_count
        if d.top_death_loop:
            pair, count = _death_loop_pair(d.top_death_loop)
            loop_counts[pair] = loop_counts.get(pair, 0) + count
            loop_days[pair] = loop_days.get(pair, 0) + 1
    top_loops = sorted(
        loop_counts.items(),
        key=lambda kv: (loop_days[kv[0]], kv[1]),
        reverse=True,
    )

    # Rhythm: how many days ran late vs early.
    late_days = sorted(
        d.date for d in days
        if (d.numbers.get("late_night_ratio") or 0) >= _LATE_NIGHT_DAY_RATIO
    )
    early_days = sorted(
        d.date for d in days
        if (d.numbers.get("early_morning_h") or 0) >= _EARLY_MORNING_DAY_H
    )

    return {
        "n_working_days": len(days),
        "working_days": sorted(d.date for d in days),
        "scores": scores,
        "medians": medians,
        "totals": totals,
        "top_categories": [{"category": c, "seconds": s} for c, s in top_categories],
        "top_death_loops": [
            {"pair": p, "total_count": loop_counts[p], "days": loop_days[p]}
            for p, _ in top_loops
        ],
        "distracting_loop_count_total": distracting_total,
        "rhythm": {
            "late_night_days": late_days,
            "early_morning_days": early_days,
        },
    }


def _delta_vs_prior(rollup: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any]:
    """Week-over-week delta of score medians + key median metrics.

    `prior` is a full prior-week rollup JSON; its comparable values live under
    `prior["rollup"]` (the same shape this run emits)."""
    if not prior:
        return {}
    prior_rollup = prior.get("rollup", {}) or {}
    out: dict[str, float] = {}
    for metric, block in rollup.get("scores", {}).items():
        prev = (prior_rollup.get("scores", {}) or {}).get(metric)
        if prev and "median" in prev:
            out[metric] = round(block["median"] - prev["median"], 2)
    for metric, val in rollup.get("medians", {}).items():
        prev = (prior_rollup.get("medians", {}) or {}).get(metric)
        if prev is not None:
            out[metric] = round(val - prev, 2)
    return out


@dataclass
class WorkerResult:
    iso_week: str
    mode: str                 # 'normal' | 'backfill' | 'noop' | 'pre-checks-failed'
    weeks_processed: list[str]
    rollup_paths: list[str]
    weekly_view_paths: list[str]
    n_records: int
    log_lines: list[str]


def run(
    base_dir: str | Path,
    *,
    source_id: str = "activitywatch",
    today: str | None = None,
    batch_id: str | None = None,
    manifest_out: str | Path | None = None,
) -> WorkerResult:
    base = Path(base_dir)
    today_d = date_cls.fromisoformat(today) if today else date_cls.today()
    today_iso = today_d.isoformat()
    iso_week = _iso_week_label(today_d)

    state_dir = base / "_system" / "state" / "activity" / source_id
    views_dir = base / "_system" / "views" / "activity" / source_id
    records_dir = base / "_records" / "activity" / source_id
    last_weekly = state_dir / "last_weekly_run.txt"

    log_lines: list[str] = []
    rollup_paths: list[str] = []
    weekly_view_paths: list[str] = []
    weeks_processed: list[str] = []

    # Pre-check: idempotent gate
    if last_weekly.exists() and last_weekly.read_text(encoding="utf-8").strip() == iso_week:
        log_lines.append(f"activity-weekly-worker noop iso_week={iso_week}")
        return WorkerResult(iso_week, "noop", [], [], [], 0, log_lines)

    if not records_dir.exists():
        log_lines.append("activity-weekly-worker pre-check failed: no _records/activity/")
        return WorkerResult(iso_week, "pre-checks-failed", [], [], [], 0, log_lines)

    all_records = sorted(records_dir.glob("2*-*-*.md"))
    n_records = len(all_records)
    if n_records < 14:
        log_lines.append(f"activity-weekly-worker pre-check failed: only {n_records} records (<14)")
        return WorkerResult(iso_week, "pre-checks-failed", [], [], [], n_records, log_lines)

    existing = sorted(state_dir.glob("weekly-*.json"))
    backfill_mode = not existing

    weeks_to_process: list[date_cls] = []
    if backfill_mode:
        oldest = date_cls.fromisoformat(all_records[0].stem)
        newest = date_cls.fromisoformat(all_records[-1].stem)
        cur_monday, _ = _week_bounds(oldest)
        while cur_monday <= newest:
            _, sun = _week_bounds(cur_monday)
            if sun >= today_d:
                break  # current week handled as the sentinel below
            weeks_to_process.append(cur_monday)
            cur_monday = cur_monday + timedelta(days=7)
        weeks_to_process.append(_week_bounds(today_d)[0])
    else:
        weeks_to_process.append(_week_bounds(today_d)[0])

    state_dir.mkdir(parents=True, exist_ok=True)
    views_dir.mkdir(parents=True, exist_ok=True)

    for monday in weeks_to_process:
        mon, sun = _week_bounds(monday)
        week_label = _iso_week_label(monday)
        days = _read_working_days(records_dir, mon, sun)
        if len(days) < 2:
            log_lines.append(f"activity-weekly-worker skip iso_week={week_label} reason=fewer-than-2-working-days")
            continue

        rollup = _compute_rollup(days)

        prior_label = _iso_week_label(monday - timedelta(days=7))
        prior_path = state_dir / f"weekly-{prior_label}.json"
        prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else None
        delta = _delta_vs_prior(rollup, prior)

        out = {
            "iso_week": week_label,
            "computed_at": today_iso + "T00:00:00Z",
            "source": source_id,
            "rollup": rollup,
            "delta_vs_prior_week": delta,
            "prior_week": prior_label if prior else None,
        }
        rollup_path = state_dir / f"weekly-{week_label}.json"
        rollup_path.write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        rollup_paths.append(str(rollup_path))

        view_path = views_dir / f"weekly-{week_label}.md"
        view_path.write_text(_render_weekly_view(out), encoding="utf-8")
        weekly_view_paths.append(str(view_path))

        weeks_processed.append(week_label)
        log_lines.append(
            f"activity-weekly-worker emit iso_week={week_label} "
            f"working_days={len(days)} top_cats={len(rollup['top_categories'])} "
            f"loops={len(rollup['top_death_loops'])}"
        )

    if weeks_processed:
        last_weekly.write_text(iso_week, encoding="utf-8")

    if batch_id and weeks_processed:
        out_path = Path(manifest_out) if manifest_out else (
            base / "_system" / "state" / "batches" / f"{batch_id}-maintain.json"
        )
        write_maintain_manifest(
            base=base,
            batch_id=batch_id,
            output_path=out_path,
            source_id=source_id,
            weeks_processed=weeks_processed,
            rollup_paths=rollup_paths,
            weekly_view_paths=weekly_view_paths,
            n_records=n_records,
            today_iso=today_iso,
        )

    return WorkerResult(
        iso_week=iso_week,
        mode="backfill" if backfill_mode else "normal",
        weeks_processed=weeks_processed,
        rollup_paths=rollup_paths,
        weekly_view_paths=weekly_view_paths,
        n_records=n_records,
        log_lines=log_lines,
    )


def _fmt_hms(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    if h and m:
        return f"{h}h {m:02d}m"
    if h:
        return f"{h}h"
    if m:
        return f"{m}m"
    return f"{int(seconds)}s"


def _arrow(delta: float) -> str:
    if delta > 0:
        return f"▲ +{delta}"
    if delta < 0:
        return f"▼ {delta}"
    return "= 0"


def _render_weekly_view(out: dict[str, Any]) -> str:
    iso_week = out["iso_week"]
    rollup = out["rollup"]
    delta = out.get("delta_vs_prior_week") or {}

    fm = (
        "---\n"
        f"iso_week: '{iso_week}'\n"
        f"generated: '{out['computed_at']}'\n"
        f"source: {out['source']}\n"
        "audience_tags: []\n"
        "is_sensitive: true\n"
        "origin: personal\n"
        "---\n\n"
    )
    parts: list[str] = [fm, f"# Activity Weekly — {iso_week}\n"]
    parts.append(f"\n_{rollup['n_working_days']} working day(s)_\n")

    # Scores
    scores = rollup.get("scores", {})
    if scores:
        parts.append("\n## Scores (median · min–max)\n")
        labels = {
            "combined_score": "Combined",
            "productivity_score": "Productivity",
            "focus_score": "Focus",
        }
        for metric in _SCORE_METRICS:
            b = scores.get(metric)
            if not b:
                continue
            d = delta.get(metric)
            d_str = f"  ({_arrow(d)} vs prior)" if d is not None else ""
            parts.append(
                f"- **{labels[metric]}:** {b['median']} "
                f"(min {b['min']}, max {b['max']}){d_str}\n"
            )

    # Focus & switching rhythm
    med = rollup.get("medians", {})
    tot = rollup.get("totals", {})
    if med or tot:
        parts.append("\n## Focus & switching\n")
        if "sustained_focus_h" in tot:
            parts.append(f"- Sustained focus this week: **{tot['sustained_focus_h']}h** total\n")
        if "human_switches_per_active_hour" in med:
            d = delta.get("human_switches_per_active_hour")
            d_str = f"  ({_arrow(d)})" if d is not None else ""
            parts.append(f"- Human switches/active-hr (median): **{med['human_switches_per_active_hour']}**{d_str}\n")
        if "longest_focus_block_min" in med:
            parts.append(f"- Longest focus block (median): {med['longest_focus_block_min']}m\n")
        if "meeting_h" in tot:
            parts.append(f"- Meetings this week: {tot['meeting_h']}h total\n")

    # Rhythm
    rhythm = rollup.get("rhythm", {})
    late = rhythm.get("late_night_days", [])
    early = rhythm.get("early_morning_days", [])
    parts.append("\n## Rhythm\n")
    parts.append(f"- Late-night days: {len(late)}" + (f" ({', '.join(late)})" if late else "") + "\n")
    parts.append(f"- Early-morning days: {len(early)}" + (f" ({', '.join(early)})" if early else "") + "\n")

    # Category-time trend
    cats = rollup.get("top_categories", [])
    if cats:
        parts.append("\n## Where the week went\n")
        for c in cats[:8]:
            parts.append(f"- {c['category']}: {_fmt_hms(c['seconds'])}\n")

    # Death loops
    loops = rollup.get("top_death_loops", [])
    if loops:
        parts.append("\n## Recurring attention leaks\n")
        for lp in loops[:5]:
            parts.append(
                f"- {lp['pair']} — {lp['total_count']}× across {lp['days']} day(s)\n"
            )
    else:
        parts.append("\n## Recurring attention leaks\nNone surfaced this week.\n")

    return "".join(parts)


def write_maintain_manifest(
    *,
    base: Path,
    batch_id: str,
    output_path: Path,
    source_id: str,
    weeks_processed: list[str],
    rollup_paths: list[str],
    weekly_view_paths: list[str],
    n_records: int,
    today_iso: str,
) -> Path:
    """Emit (or merge into) the v2 `minder:mem:maintain` batch manifest under
    `tier2_objects.activity` (per ENGINE_DOCTRINE §3.8)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    activity_section = {
        "source": source_id,
        "weeks_processed": weeks_processed,
        "rollup_files": [
            {
                "path": _rel(base, p),
                "iso_week": _week_from_path(p),
                "checksum_sha256": _checksum(Path(p)),
                "audience_tags": [],
                "is_sensitive": True,
                "origin": "personal",
            }
            for p in rollup_paths
        ],
        "weekly_views": [
            {
                "path": _rel(base, p),
                "iso_week": _week_from_path(p),
                "checksum_sha256": _checksum(Path(p)),
                "audience_tags": [],
                "is_sensitive": True,
                "origin": "personal",
            }
            for p in weekly_view_paths
        ],
    }

    if output_path.exists():
        manifest = json.loads(output_path.read_text(encoding="utf-8"))
        manifest.setdefault("tier2_objects", {})["activity"] = activity_section
        stats = manifest.setdefault("stats", {})
        stats["activity_weeks_processed"] = len(weeks_processed)
        stats["activity_records_in_window"] = n_records
    else:
        manifest = {
            "batch_id": batch_id,
            "timestamp": today_iso + "T00:00:00Z" if "T" not in today_iso else today_iso,
            "processor": "minder:mem:maintain",
            "format_version": "2.0",
            "hubs": {"updated": []},
            "tier1_objects": {"people": {"upserts": []}},
            "tier2_objects": {"activity": activity_section},
            "threads_opened": [],
            "threads_resolved": [],
            "stats": {
                "upstream_batch_id": batch_id,
                "activity_weeks_processed": len(weeks_processed),
                "activity_records_in_window": n_records,
            },
            "section_extras": {
                "activity_pipeline": {"tier2_subsection": "activity"},
            },
        }

    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def _rel(base: Path, p: str | Path) -> str:
    p = Path(p)
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def _week_from_path(p: str | Path) -> str:
    name = Path(p).name
    if name.startswith("weekly-"):
        return name[len("weekly-"):].split(".")[0]
    return ""


def _checksum(p: Path) -> str:
    import hashlib
    if not p.exists():
        return ""
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-dir", default=".")
    p.add_argument("--source-id", default="activitywatch")
    p.add_argument("--today", default=None, help="ISO date override")
    p.add_argument("--batch-id", default=None,
                   help="If set, emit Tier II maintain manifest at "
                        "_system/state/batches/{batch_id}-maintain.json.")
    p.add_argument("--manifest-out", default=None)
    args = p.parse_args(argv)
    res = run(args.base_dir, source_id=args.source_id, today=args.today,
              batch_id=args.batch_id, manifest_out=args.manifest_out)
    print(json.dumps(asdict(res), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())


configure_std_streams()
