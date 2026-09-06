"""End-to-end tests for activity_weekly_worker."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import activity_weekly_worker as ww  # noqa: E402


def _setup_base(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    (base / "_records" / "activity" / "activitywatch").mkdir(parents=True)
    (base / "_system" / "state" / "activity" / "activitywatch").mkdir(parents=True)
    (base / "_system" / "views" / "activity" / "activitywatch").mkdir(parents=True)
    return base


def _emit_record(
    base: Path,
    d: date,
    *,
    active_h: float = 6.0,
    combined: float = 70.0,
    productivity: float = 72.0,
    focus: float = 68.0,
    switches_per_hr: float = 50.0,
    sustained_focus_h: float = 0.0,
    meeting_h: float = 1.0,
    late_night_ratio: float = 0.0,
    early_morning_h: float = 0.0,
    top_categories: str = "deep_work 4h 00m, communication_work 1h 00m",
    top_death_loop: str | None = "Google Chrome <-> Slack ×100 (mixed)",
    distracting_loop_count: int = 1,
) -> None:
    p = base / "_records" / "activity" / "activitywatch" / f"{d.isoformat()}.md"
    loop_line = f"top_death_loop: {top_death_loop}\n" if top_death_loop else ""
    body = (
        f"---\ndate: '{d.isoformat()}'\nkind: activity\n"
        "domains: [time, work]\naudience_tags: []\nis_sensitive: true\n"
        "origin: personal\ndevice: activitywatch\n---\n\n"
        f"# Activity — {d.isoformat()}\n\n"
        f"- **Top categories:** {top_categories}\n\n"
        "## Key Numbers\n\n"
        "```yaml\n"
        f"combined_score: {combined}\n"
        f"productivity_score: {productivity}\n"
        f"focus_score: {focus}\n"
        f"active_h: {active_h}\n"
        f"sustained_focus_h: {sustained_focus_h}\n"
        "longest_focus_block_min: 20\n"
        "human_switches: 300\n"
        f"human_switches_per_active_hour: {switches_per_hr}\n"
        f"meeting_h: {meeting_h}\n"
        f"late_night_ratio: {late_night_ratio}\n"
        f"early_morning_h: {early_morning_h}\n"
        "work_h: 5.0\n"
        "personal_h: 0.0\n"
        + loop_line
        + f"distracting_loop_count: {distracting_loop_count}\n"
        "```\n"
    )
    p.write_text(body, encoding="utf-8")


def test_pre_check_fewer_than_14_records(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(5):
        _emit_record(base, d0 + timedelta(days=i))
    res = ww.run(base, today="2024-01-10")
    assert res.mode == "pre-checks-failed"
    assert res.weeks_processed == []


def test_working_day_filter_skips_idle_days(tmp_path):
    """Idle days (active_h < 0.5) are excluded from the rollup."""
    base = _setup_base(tmp_path)
    mon = date(2024, 1, 1)  # ISO 2024-W01 Monday
    # 3 working days + 2 idle days in the same week
    for i in range(3):
        _emit_record(base, mon + timedelta(days=i), active_h=6.0, focus=80.0)
    for i in range(3, 5):
        _emit_record(base, mon + timedelta(days=i), active_h=0.1, focus=10.0)
    # pad enough total records to pass the >=14 pre-check (next weeks)
    for i in range(7, 21):
        _emit_record(base, mon + timedelta(days=i), active_h=6.0, focus=80.0)
    res = ww.run(base, today="2024-01-28")
    p = Path(next(x for x in res.rollup_paths if "2024-W01" in x))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["rollup"]["n_working_days"] == 3
    # idle days' focus=10 must not drag the median below the working 80
    assert data["rollup"]["scores"]["focus_score"]["median"] == 80.0


def test_rollup_median_and_category_aggregation(tmp_path):
    base = _setup_base(tmp_path)
    mon = date(2024, 1, 1)
    focus_vals = [60.0, 70.0, 80.0]  # median 70
    for i, f in enumerate(focus_vals):
        _emit_record(
            base, mon + timedelta(days=i), focus=f,
            top_categories="deep_work 1h 00m, email 10m",
        )
    for i in range(7, 21):
        _emit_record(base, mon + timedelta(days=i))
    res = ww.run(base, today="2024-01-28")
    data = json.loads(Path(next(x for x in res.rollup_paths if "2024-W01" in x)).read_text(encoding="utf-8"))
    assert data["rollup"]["scores"]["focus_score"]["median"] == 70.0
    assert data["rollup"]["scores"]["focus_score"]["min"] == 60.0
    assert data["rollup"]["scores"]["focus_score"]["max"] == 80.0
    # deep_work summed across 3 days = 3h, email = 30m → deep_work ranked first
    cats = {c["category"]: c["seconds"] for c in data["rollup"]["top_categories"]}
    assert cats["deep_work"] == 3 * 3600
    assert cats["email"] == 3 * 600
    assert data["rollup"]["top_categories"][0]["category"] == "deep_work"


def test_top_death_loop_aggregation(tmp_path):
    base = _setup_base(tmp_path)
    mon = date(2024, 1, 1)
    # Same pair recurs 3 days with counts 100/50/30 → total 180 across 3 days
    for i, c in enumerate((100, 50, 30)):
        _emit_record(
            base, mon + timedelta(days=i),
            top_death_loop=f"Chrome <-> Slack ×{c} (mixed)",
        )
    for i in range(7, 21):
        _emit_record(base, mon + timedelta(days=i), top_death_loop=None)
    res = ww.run(base, today="2024-01-28")
    data = json.loads(Path(next(x for x in res.rollup_paths if "2024-W01" in x)).read_text(encoding="utf-8"))
    loops = data["rollup"]["top_death_loops"]
    top = loops[0]
    assert top["pair"] == "Chrome <-> Slack"
    assert top["total_count"] == 180
    assert top["days"] == 3


def test_week_over_week_delta(tmp_path):
    base = _setup_base(tmp_path)
    w1 = date(2024, 1, 1)   # W01
    w2 = date(2024, 1, 8)   # W02
    for i in range(3):
        _emit_record(base, w1 + timedelta(days=i), focus=60.0)
    for i in range(3):
        _emit_record(base, w2 + timedelta(days=i), focus=75.0)
    # pad to clear 14-record pre-check
    for i in range(14, 28):
        _emit_record(base, w1 + timedelta(days=i), focus=75.0)
    res = ww.run(base, today="2024-02-04")
    data = json.loads(Path(next(x for x in res.rollup_paths if "2024-W02" in x)).read_text(encoding="utf-8"))
    assert data["prior_week"] == "2024-W01"
    # W02 focus median 75 - W01 focus median 60 = +15
    assert data["delta_vs_prior_week"]["focus_score"] == 15.0


def test_idempotent_weekly_gate(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(20):
        _emit_record(base, d0 + timedelta(days=i))
    res1 = ww.run(base, today="2024-01-25")
    assert res1.mode in {"backfill", "normal"}
    assert res1.weeks_processed
    res2 = ww.run(base, today="2024-01-25")
    assert res2.mode == "noop"
    assert res2.weeks_processed == []


def test_backfill_produces_multiple_weeks(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(28):
        _emit_record(base, d0 + timedelta(days=i))
    res = ww.run(base, today="2024-02-01")
    assert res.mode == "backfill"
    assert len(res.weeks_processed) >= 2
    view = Path(res.weekly_view_paths[0]).read_text(encoding="utf-8")
    assert "Activity Weekly" in view
    assert "is_sensitive: true" in view
    assert "origin: personal" in view


def test_maintain_manifest_emission(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(20):
        _emit_record(base, d0 + timedelta(days=i))
    res = ww.run(base, today="2024-01-25", batch_id="20240125-091500")
    assert res.weeks_processed
    manifest_path = base / "_system" / "state" / "batches" / "20240125-091500-maintain.json"
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert m["processor"] == "minder:mem:maintain"
    assert m["format_version"] == "2.0"
    assert "activity" in m["tier2_objects"]
    section = m["tier2_objects"]["activity"]
    assert section["weeks_processed"] == res.weeks_processed
    for vf in section["weekly_views"]:
        assert vf["audience_tags"] == []
        assert vf["is_sensitive"] is True
        assert vf["origin"] == "personal"
        assert vf["checksum_sha256"]
    assert m["stats"]["activity_weeks_processed"] == len(res.weeks_processed)


def test_maintain_manifest_merges_existing(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(20):
        _emit_record(base, d0 + timedelta(days=i))
    pre = base / "_system" / "state" / "batches" / "20240125-091500-maintain.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps({
        "batch_id": "20240125-091500",
        "processor": "minder:mem:maintain",
        "format_version": "2.0",
        "hubs": {"updated": [{"path": "5_meta/mocs/foo.md"}]},
        "tier2_objects": {"biometric": {"weeks_processed": ["2024-W03"]}},
        "stats": {"upstream_batch_id": "20240125-091500", "back_refs_written": 3},
    }), encoding="utf-8")
    ww.run(base, today="2024-01-25", batch_id="20240125-091500")
    m = json.loads(pre.read_text(encoding="utf-8"))
    # Pre-existing sections preserved
    assert m["hubs"]["updated"] == [{"path": "5_meta/mocs/foo.md"}]
    assert m["tier2_objects"]["biometric"]["weeks_processed"] == ["2024-W03"]
    assert m["stats"]["back_refs_written"] == 3
    # activity added alongside
    assert "activity" in m["tier2_objects"]
    assert "activity_weeks_processed" in m["stats"]
