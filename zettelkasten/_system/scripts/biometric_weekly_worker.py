"""Tier II weekly worker — biometric × biometric + biometric × affect.

Triggered by /minder:mem:maintain after-batch invocation. Idempotent weekly
gate via `_system/state/biometric/last_weekly_run.txt`: read current
ISO week; if same as `last_weekly_run.txt`, no-op.

Two modes:
  - Normal current-week: when prior correlations files exist.
  - Backfill: when ≥14 records exist but no correlations file yet —
    iterates completed ISO weeks chronologically, oldest → newest, and
    produces per-week outputs.

Outputs (per ISO week run):
  _system/state/biometric/correlations-{YYYY-Www}.json
  _system/views/biometric/weekly-{YYYY-Www}.md
  _system/state/biometric/calibration-history.json (append)
  _system/state/biometric/last_weekly_run.txt (single line)

NO LLM — pure deterministic Python.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date as date_cls, timedelta
from pathlib import Path

from _common import configure_std_streams  # type: ignore
from typing import Any

import yaml

import biometric_correlations as bc
import biometric_calibration_check as bcc
import affect_extractor as ax


def _iso_week_label(d: date_cls) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_bounds(d: date_cls) -> tuple[date_cls, date_cls]:
    """Monday..Sunday of the ISO week containing d."""
    monday = d - timedelta(days=d.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _read_record_metrics(records_dir: Path, window_start: str, window_end: str) -> dict[str, Any]:
    """Return {metric: {date: value}} from biometric records in window."""
    out: dict[str, dict[str, float]] = {}
    if not records_dir.exists():
        return {"series": out, "deviations_per_day": {}}
    devs_per_day: dict[str, list[str]] = {}
    for p in sorted(records_dir.glob("2*-*-*.md")):
        date = p.stem
        if date < window_start or date > window_end:
            continue
        text = p.read_text(encoding="utf-8")
        # Key Numbers
        m = re.search(r"\n## Key Numbers\n+```yaml\n(.*?)\n```", text, re.DOTALL)
        if m:
            kn = yaml.safe_load(m.group(1)) or {}
            for k, v in kn.items():
                if isinstance(v, (int, float)):
                    out.setdefault(k, {})[date] = float(v)
        # Deviations parsed for cluster detection
        if "## Baseline Deviations" in text:
            section = text.split("## Baseline Deviations", 1)[1].split("\n##", 1)[0]
            mets: list[str] = []
            for line in section.splitlines():
                line = line.strip()
                if line.startswith("- "):
                    parts = line[2:].split()
                    if parts:
                        mets.append(parts[0])
            if mets:
                devs_per_day[date] = mets
    return {"series": out, "deviations_per_day": devs_per_day}


def _structural_affect(meetings_dir: Path, window_start: str, window_end: str) -> set[str]:
    return ax.detect_meeting_heavy_days(meetings_dir, window_start=window_start, window_end=window_end)


@dataclass
class WorkerResult:
    iso_week: str
    mode: str                 # 'normal' | 'backfill' | 'noop' | 'pre-checks-failed'
    weeks_processed: list[str]
    correlations_paths: list[str]
    weekly_view_paths: list[str]
    proposals: list[dict[str, Any]]
    n_records: int
    log_lines: list[str]


def run(
    base_dir: str | Path,
    *,
    source_id: str = "garmin",
    today: str | None = None,
    thresholds: dict[str, Any] | None = None,
    batch_id: str | None = None,
    manifest_out: str | Path | None = None,
) -> WorkerResult:
    base = Path(base_dir)
    today_d = date_cls.fromisoformat(today) if today else date_cls.today()
    today_iso = today_d.isoformat()
    iso_week = _iso_week_label(today_d)

    # Per-device namespace: each wearable's records + derived state live under
    # `{source_id}/`. Caller (/minder:mem:maintain) runs the worker once per active
    # metric-day source.
    state_dir = base / "_system" / "state" / "biometric" / source_id
    views_dir = base / "_system" / "views" / "biometric" / source_id
    records_dir = base / "_records" / "biometric" / source_id
    last_weekly = state_dir / "last_weekly_run.txt"
    calibration_path = state_dir / "calibration-history.json"

    log_lines: list[str] = []
    proposals_dicts: list[dict[str, Any]] = []
    correlations_paths: list[str] = []
    weekly_view_paths: list[str] = []
    weeks_processed: list[str] = []

    if not thresholds:
        thresholds = _load_thresholds(base)

    # Pre-check: idempotent gate
    if last_weekly.exists() and last_weekly.read_text(encoding="utf-8").strip() == iso_week:
        log_lines.append(f"weekly-worker noop iso_week={iso_week}")
        return WorkerResult(
            iso_week=iso_week, mode="noop",
            weeks_processed=[], correlations_paths=[], weekly_view_paths=[],
            proposals=[], n_records=0, log_lines=log_lines,
        )

    # Pre-check 2: count biometric records
    if not records_dir.exists():
        log_lines.append("weekly-worker pre-check failed: no _records/biometric/")
        return WorkerResult(
            iso_week=iso_week, mode="pre-checks-failed",
            weeks_processed=[], correlations_paths=[], weekly_view_paths=[],
            proposals=[], n_records=0, log_lines=log_lines,
        )
    all_records = sorted(records_dir.glob("2*-*-*.md"))
    n_records = len(all_records)
    if n_records < 14:
        log_lines.append(f"weekly-worker pre-check failed: only {n_records} records (<14)")
        return WorkerResult(
            iso_week=iso_week, mode="pre-checks-failed",
            weeks_processed=[], correlations_paths=[], weekly_view_paths=[],
            proposals=[], n_records=n_records, log_lines=log_lines,
        )

    # Decide mode: backfill if no prior correlations files
    existing_corr = sorted(state_dir.glob("correlations-*.json"))
    backfill_mode = not existing_corr

    # Determine list of ISO weeks to process
    weeks_to_process: list[date_cls] = []
    if backfill_mode:
        oldest = date_cls.fromisoformat(all_records[0].stem)
        newest = date_cls.fromisoformat(all_records[-1].stem)
        cur_monday, _ = _week_bounds(oldest)
        # iterate completed ISO weeks (Mon-Sun ≤ today)
        while cur_monday <= newest:
            mon, sun = _week_bounds(cur_monday)
            if sun >= today_d:
                # only emit completed weeks in backfill; current week is "normal"
                break
            weeks_to_process.append(cur_monday)
            cur_monday = cur_monday + timedelta(days=7)
        # plus the current ISO week as the active sentinel
        weeks_to_process.append(_week_bounds(today_d)[0])
    else:
        weeks_to_process.append(_week_bounds(today_d)[0])

    state_dir.mkdir(parents=True, exist_ok=True)
    views_dir.mkdir(parents=True, exist_ok=True)

    for monday in weeks_to_process:
        mon, sun = _week_bounds(monday)
        # window: trailing 56d up through `sun`
        win_end = sun.isoformat()
        win_start = (sun - timedelta(days=55)).isoformat()
        # require at least 4 days of records in this ISO week
        in_week = [p for p in all_records if mon.isoformat() <= p.stem <= sun.isoformat()]
        if len(in_week) < 4:
            log_lines.append(f"weekly-worker skip iso_week={_iso_week_label(monday)} reason=fewer-than-4-records-in-week")
            continue

        rec_data = _read_record_metrics(records_dir, win_start, win_end)
        series = rec_data["series"]
        deviations_per_day = rec_data["deviations_per_day"]
        clusters = bc.detect_anomaly_clusters(deviations_per_day)

        phase1 = bc.compute_pairs(series, lag_max=3, min_n=14, min_severity="medium")

        # Affect tagging
        affect_tags = ax.tag_records(
            [base / "_records" / "observations", base / "_records" / "meetings"],
            base / "_system" / "scripts" / "affect_lexicon.yaml",
            base / "_system" / "scripts" / "affect_lexicon.local.yaml",
            lexicon_template=base / "_system" / "scripts" / "affect_lexicon.template.yaml",
            window_start=win_start, window_end=win_end,
        )
        # Inject structural meeting_heavy_day tags
        heavy = _structural_affect(base / "_records" / "meetings", win_start, win_end)
        for d in heavy:
            affect_tags.setdefault(d, set()).add("meeting_heavy_day")

        phase2 = bc.compute_cross(series, affect_tags, lag_max=2)

        cats_with_signal = sorted({f.affect for f in phase2})
        cats_silent = sorted(c for c in (
            {a for tags in affect_tags.values() for a in tags}
        ) if c not in cats_with_signal)

        # Calibration: per-week fire-rates per metric × severity
        fire_rates = _compute_fire_rates(records_dir, win_start, win_end)
        bcc.record_week(calibration_path, _iso_week_label(monday), fire_rates, n_days=len(in_week))

        cal_state = json.loads(calibration_path.read_text(encoding="utf-8")) if calibration_path.exists() else {"weeks": []}
        proposals = bcc.detect_drift(cal_state, thresholds)
        proposals_dicts = [bcc.proposal_to_dict(p) for p in proposals]

        # Streak history snapshot from streaks.json
        streaks = _load_streaks(state_dir / "streaks.json", win_end)

        out = {
            "iso_week": _iso_week_label(monday),
            "computed_at": today_iso + "T00:00:00Z",
            "window_days": 56,
            "phase_1": {
                "top_strong": [bc.finding_to_dict(f) for f in phase1 if f.severity == "strong"][:5],
                "top_medium": [bc.finding_to_dict(f) for f in phase1 if f.severity == "medium"][:5],
                "anomaly_clusters": [bc.finding_to_dict(c) for c in clusters],
                "active_streaks": streaks["active"],
                "ended_streaks": streaks["ended"],
            },
            "phase_2": {
                "lexicon_health": {
                    "categories_with_signal": cats_with_signal,
                    "categories_silent": cats_silent,
                    "lexicon_overlay_loaded": (base / "_system" / "scripts" / "affect_lexicon.local.yaml").exists(),
                },
                "top_findings": [bc.finding_to_dict(f) for f in phase2[:5]],
            },
            "calibration": {
                "proposals": proposals_dicts,
                "fire_rates": fire_rates,
            },
        }
        corr_path = state_dir / f"correlations-{_iso_week_label(monday)}.json"
        corr_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        correlations_paths.append(str(corr_path))

        weekly_view = _render_weekly_view(out, records_dir)
        view_path = views_dir / f"weekly-{_iso_week_label(monday)}.md"
        view_path.write_text(weekly_view, encoding="utf-8")
        weekly_view_paths.append(str(view_path))

        weeks_processed.append(_iso_week_label(monday))
        log_lines.append(
            f"weekly-worker emit iso_week={_iso_week_label(monday)} "
            f"phase1={len(phase1)} phase2={len(phase2)} clusters={len(clusters)} "
            f"proposals={len(proposals_dicts)}"
        )

    # Phase 2 empty signal → CLARIFICATION
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
            weeks_processed=weeks_processed,
            correlations_paths=correlations_paths,
            weekly_view_paths=weekly_view_paths,
            proposals=proposals_dicts,
            n_records=n_records,
            today_iso=today_iso,
        )

    return WorkerResult(
        iso_week=iso_week,
        mode="backfill" if backfill_mode else "normal",
        weeks_processed=weeks_processed,
        correlations_paths=correlations_paths,
        weekly_view_paths=weekly_view_paths,
        proposals=proposals_dicts,
        n_records=n_records,
        log_lines=log_lines,
    )


def _load_streaks(path: Path, as_of: str) -> dict[str, Any]:
    if not path.exists():
        return {"active": [], "ended": []}
    s = json.loads(path.read_text(encoding="utf-8"))
    active = []
    for c, e in (s.get("active") or {}).items():
        active.append({
            "concept": c, "metric": e.get("metric"),
            "started": e.get("started"), "days": e.get("days"),
        })
    ended = [
        h for h in (s.get("history") or [])
        if (h.get("ended") or "") <= as_of
    ][-5:]
    return {"active": active, "ended": ended}


def _compute_fire_rates(records_dir: Path, win_start: str, win_end: str) -> dict[str, dict[str, float]]:
    """Per-metric × severity observed fire-rate over the window."""
    counts: dict[str, dict[str, int]] = {}
    n_days = 0
    for p in sorted(records_dir.glob("2*-*-*.md")):
        date = p.stem
        if date < win_start or date > win_end:
            continue
        n_days += 1
        text = p.read_text(encoding="utf-8")
        if "## Baseline Deviations" not in text:
            continue
        section = text.split("## Baseline Deviations", 1)[1].split("\n##", 1)[0]
        for line in section.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            # "- metric value — ±Nσ severity (baseline μ ± σ)"
            parts = line[2:].split()
            if len(parts) < 4:
                continue
            metric = parts[0]
            # find the severity word at position [4] (after sigma token)
            sev = None
            for tok in parts:
                t = tok.lower().rstrip("σ.,")
                if t in {"strong", "medium", "light"}:
                    sev = t
                    break
            if not sev:
                continue
            counts.setdefault(metric, {}).setdefault(sev, 0)
            counts[metric][sev] += 1
    if n_days == 0:
        return {}
    return {
        m: {s: round(c / n_days, 4) for s, c in by.items()}
        for m, by in counts.items()
    }


def _render_weekly_view(out: dict[str, Any], records_dir: Path) -> str:
    iso_week = out["iso_week"]
    fm = (
        "---\n"
        f"iso_week: '{iso_week}'\n"
        f"generated: '{out['computed_at']}'\n"
        f"window_days: {out['window_days']}\n"
        "audience_tags: []\n"
        "is_sensitive: true\n"
        "origin: personal\n"
        "---\n\n"
    )
    parts: list[str] = [fm, f"# Biometric Weekly — {iso_week}\n"]

    p1 = out.get("phase_1", {}) or {}
    p2 = out.get("phase_2", {}) or {}

    # Recovery summary
    recovery_line = _recovery_summary(records_dir, iso_week)
    if recovery_line:
        parts.append("\n## Recovery\n" + recovery_line + "\n")

    clusters = p1.get("anomaly_clusters", [])
    if clusters:
        parts.append("\n## Anomaly clusters this week\n")
        for c in clusters:
            ms = ", ".join(c.get("metrics_involved", []))
            parts.append(f"- {c['date_start']} → {c['date_end']}: {ms}\n")

    streaks = p1.get("active_streaks", [])
    if streaks:
        parts.append("\n## Streaks\n")
        for s in streaks:
            parts.append(f"- Active: {s['concept']} (day {s['days']}, started {s['started']})\n")

    findings: list[dict[str, Any]] = []
    findings.extend(p1.get("top_strong", []) or [])
    findings.extend((p2.get("top_findings") or []))
    findings.extend(p1.get("top_medium", []) or [])
    if findings:
        parts.append("\n## Strongest cross-source signals\n")
        for i, f in enumerate(findings[:5], 1):
            if "metric" in f and "affect" in f:
                parts.append(
                    f"{i}. **{f['severity']}** journal:{f['affect']} ↔ {f['metric']} "
                    f"(lag {f['lag']}, r_pb={f['r_pb']}, n={f['n_total']} of "
                    f"{f['n_total']}).\n"
                )
            else:
                parts.append(
                    f"{i}. **{f['severity']}** {f['a']} ↔ {f['b']} "
                    f"(lag {f['lag']}, r={f['r']}, n={f['n']}).\n"
                )

    cal = out.get("calibration", {}) or {}
    if cal.get("proposals"):
        parts.append("\n## Calibration\n")
        for p in cal["proposals"]:
            parts.append(
                f"- {p['metric']}/{p['severity']} drift {p['direction']}: "
                f"observed {p['observed_fire_rate']:.4f} vs expected "
                f"{p['expected_fire_rate']:.4f} → propose σ {p['proposed_sigma']} "
                f"(was {p['current_sigma']}).\n"
            )
    else:
        parts.append("\n## Calibration\nThreshold fire-rates within expected band. No drift proposal.\n")

    return "".join(parts)


def _recovery_summary(records_dir: Path, iso_week: str) -> str:
    """Produce a one-line recovery summary from the most recent record."""
    days = sorted(records_dir.glob("2*-*-*.md"), reverse=True)
    if not days:
        return ""
    p = days[0]
    text = p.read_text(encoding="utf-8")
    m = re.search(r"\n## Key Numbers\n+```yaml\n(.*?)\n```", text, re.DOTALL)
    if not m:
        return ""
    kn = yaml.safe_load(m.group(1)) or {}
    bits = []
    if "sleep_h" in kn:
        bits.append(f"sleep avg {kn['sleep_h']}h")
    if "hrv_ms" in kn:
        bits.append(f"HRV {kn['hrv_ms']}ms ({kn.get('hrv_status', '')})")
    if "rhr" in kn:
        bits.append(f"RHR {kn['rhr']}")
    return ", ".join(bits) + "."


def write_maintain_manifest(
    *,
    base: Path,
    batch_id: str,
    output_path: Path,
    weeks_processed: list[str],
    correlations_paths: list[str],
    weekly_view_paths: list[str],
    proposals: list[dict[str, Any]],
    n_records: int,
    today_iso: str,
) -> Path:
    """Emit (or merge into) v2-conformant `minder:mem:maintain` batch manifest.

    Required sections per `emit_batch_manifest.PROCESSOR_REQUIRED_SECTIONS`:
    `stats`. Tier II biometric output goes under `tier2_objects.biometric`
    (per ENGINE_DOCTRINE §3.8 — Tier 2 typed objects are schema-registered).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    biometric_section = {
        "weeks_processed": weeks_processed,
        "correlations_files": [
            {
                "path": _rel(base, p),
                "iso_week": _week_from_path(p),
                "checksum_sha256": _checksum(Path(p)),
                "audience_tags": [],
                "is_sensitive": True,
                "origin": "personal",
            }
            for p in correlations_paths
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
        "calibration_proposals": proposals,
    }

    if output_path.exists():
        manifest = json.loads(output_path.read_text(encoding="utf-8"))
        manifest.setdefault("tier2_objects", {})["biometric"] = biometric_section
        stats = manifest.setdefault("stats", {})
        stats["biometric_weeks_processed"] = len(weeks_processed)
        stats["biometric_calibration_proposals"] = len(proposals)
        stats["biometric_records_in_window"] = n_records
    else:
        manifest = {
            "batch_id": batch_id,
            "timestamp": today_iso + "T00:00:00Z" if "T" not in today_iso else today_iso,
            "processor": "minder:mem:maintain",
            "format_version": "2.0",
            "hubs": {"updated": []},
            "tier1_objects": {"people": {"upserts": []}},
            "tier2_objects": {"biometric": biometric_section},
            "threads_opened": [],
            "threads_resolved": [],
            "stats": {
                "upstream_batch_id": batch_id,
                "biometric_weeks_processed": len(weeks_processed),
                "biometric_calibration_proposals": len(proposals),
                "biometric_records_in_window": n_records,
            },
            "section_extras": {
                "biometric_pipeline": {
                    "tier2_subsection": "biometric",
                },
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
    # correlations-2026-W18.json or weekly-2026-W18.md
    for prefix in ("correlations-", "weekly-"):
        if name.startswith(prefix):
            return name[len(prefix):].split(".")[0]
    return ""


def _checksum(p: Path) -> str:
    import hashlib
    if not p.exists():
        return ""
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load_thresholds(base: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in [
        base / "_system" / "scripts" / "biometric_thresholds.template.yaml",
        base / "_system" / "scripts" / "biometric_thresholds.yaml",
        base / "_system" / "scripts" / "biometric_thresholds.local.yaml",
    ]:
        if p.exists():
            d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            _deep_merge(out, d)
    return out


def _deep_merge(target: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v


def _main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-dir", default=".")
    p.add_argument("--today", default=None, help="ISO date override")
    p.add_argument("--batch-id", default=None,
                   help="If set, emit Tier II maintain manifest at "
                        "_system/state/batches/{batch_id}-maintain.json.")
    p.add_argument("--manifest-out", default=None)
    args = p.parse_args(argv)
    res = run(args.base_dir, today=args.today,
              batch_id=args.batch_id, manifest_out=args.manifest_out)
    print(json.dumps(asdict(res), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())


configure_std_streams()
