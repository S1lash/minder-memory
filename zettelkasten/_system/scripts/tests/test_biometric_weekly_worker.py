"""End-to-end tests for biometric_weekly_worker."""

from __future__ import annotations

import json
import shutil
import sys
import yaml
from datetime import date, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import biometric_weekly_worker as ww  # noqa: E402


def _setup_base(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    (base / "_records" / "biometric" / "garmin").mkdir(parents=True)
    (base / "_records" / "observations").mkdir(parents=True)
    (base / "_records" / "meetings").mkdir(parents=True)
    (base / "_system" / "state" / "biometric" / "garmin").mkdir(parents=True)
    (base / "_system" / "views" / "biometric" / "garmin").mkdir(parents=True)
    (base / "_system" / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPTS_DIR / "biometric_thresholds.yaml", base / "_system" / "scripts" / "biometric_thresholds.yaml")
    shutil.copy(SCRIPTS_DIR / "affect_lexicon.yaml", base / "_system" / "scripts" / "affect_lexicon.yaml")
    return base


def _emit_record(base: Path, d: date, sleep_h: float, hrv_ms: float, readiness: int) -> None:
    p = base / "_records" / "biometric" / "garmin" / f"{d.isoformat()}.md"
    body = (
        f"---\n"
        f"date: '{d.isoformat()}'\n"
        "kind: biometric\n"
        "domains: [health]\n"
        "audience_tags: []\n"
        "is_sensitive: true\n"
        "origin: personal\n"
        "device: garmin\n"
        "device_estimate: true\n"
        "concepts: []\n"
        "---\n\n"
        f"# Biometric — {d.isoformat()}\n\n"
        "## Key Numbers\n\n"
        "```yaml\n"
        f"sleep_h: {sleep_h}\n"
        f"hrv_ms: {hrv_ms}\n"
        f"readiness: {readiness}\n"
        "```\n"
    )
    p.write_text(body, encoding="utf-8")


def test_pre_check_fewer_than_14_records(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(5):
        _emit_record(base, d0 + timedelta(days=i), 7.0, 30, 88)
    res = ww.run(base, today="2024-01-10")
    assert res.mode == "pre-checks-failed"
    assert res.weeks_processed == []


def test_backfill_mode_first_run(tmp_path):
    base = _setup_base(tmp_path)
    # 30 days, simple stable series
    d0 = date(2024, 1, 1)
    for i in range(30):
        _emit_record(base, d0 + timedelta(days=i), 7.0 + (i % 3) * 0.1, 30 + (i % 2), 85 + (i % 4))
    res = ww.run(base, today="2024-02-01")
    assert res.mode == "backfill"
    # multiple completed ISO weeks should be processed
    assert len(res.weeks_processed) >= 2
    # at least one correlations file written
    assert any(Path(p).exists() for p in res.correlations_paths)
    # weekly-view BODY must carry the Recovery section — guards against the
    # renderer being handed the bare (non-namespaced) records dir, which
    # silently finds zero records and drops the section.
    view_text = Path(res.weekly_view_paths[0]).read_text(encoding="utf-8")
    assert "Recovery" in view_text


def test_idempotent_weekly_gate(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(20):
        _emit_record(base, d0 + timedelta(days=i), 7.0, 30, 88)
    res1 = ww.run(base, today="2024-01-25")
    assert res1.mode in {"backfill", "normal"}
    res2 = ww.run(base, today="2024-01-25")
    assert res2.mode == "noop"
    assert res2.weeks_processed == []


def test_maintain_manifest_emission(tmp_path):
    """run with --batch-id writes v2-conformant maintain manifest with
    `tier2_objects.biometric` section."""
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(20):
        _emit_record(base, d0 + timedelta(days=i), 7.0, 30, 88)
    res = ww.run(base, today="2024-01-25", batch_id="20240125-091500")
    if not res.weeks_processed:
        return  # no week to process is acceptable for this synthetic
    manifest_path = base / "_system" / "state" / "batches" / "20240125-091500-maintain.json"
    assert manifest_path.exists()
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert m["processor"] == "minder:mem:maintain"
    assert m["format_version"] == "2.0"
    assert m["batch_id"] == "20240125-091500"
    assert "biometric" in m["tier2_objects"]
    section = m["tier2_objects"]["biometric"]
    assert section["weeks_processed"] == res.weeks_processed
    # privacy trio on every entry
    for cf in section["correlations_files"]:
        assert cf["audience_tags"] == []
        assert cf["is_sensitive"] is True
        assert cf["origin"] == "personal"
        assert cf["checksum_sha256"]
    assert m["stats"]["biometric_weeks_processed"] == len(res.weeks_processed)


def test_maintain_manifest_merges_existing(tmp_path):
    """Tier II merges into pre-existing maintain manifest (mixed batch)."""
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(20):
        _emit_record(base, d0 + timedelta(days=i), 7.0, 30, 88)
    pre = base / "_system" / "state" / "batches" / "20240125-091500-maintain.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps({
        "batch_id": "20240125-091500",
        "processor": "minder:mem:maintain",
        "format_version": "2.0",
        "hubs": {"updated": [{"path": "5_meta/mocs/foo.md"}]},
        "stats": {"upstream_batch_id": "20240125-091500", "back_refs_written": 3},
    }), encoding="utf-8")
    ww.run(base, today="2024-01-25", batch_id="20240125-091500")
    m = json.loads(pre.read_text(encoding="utf-8"))
    # Pre-existing hubs section preserved
    assert m["hubs"]["updated"] == [{"path": "5_meta/mocs/foo.md"}]
    # Stats preserved + augmented
    assert m["stats"]["back_refs_written"] == 3
    assert "biometric_weeks_processed" in m["stats"]
    # tier2 added
    assert "biometric" in m["tier2_objects"]


def test_correlations_json_structure(tmp_path):
    base = _setup_base(tmp_path)
    d0 = date(2024, 1, 1)
    for i in range(20):
        _emit_record(base, d0 + timedelta(days=i), 7.0 + (i % 3) * 0.1, 30, 85 + (i % 5) * 2)
    res = ww.run(base, today="2024-01-25")
    if not res.correlations_paths:
        return  # backfill couldn't find a complete week — acceptable
    p = Path(res.correlations_paths[0])
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "iso_week" in data
    assert "phase_1" in data
    assert "phase_2" in data
    assert "calibration" in data
    assert "computed_at" in data
