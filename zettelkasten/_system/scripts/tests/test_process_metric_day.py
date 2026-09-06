"""End-to-end tests for process_metric_day orchestrator."""

from __future__ import annotations

import shutil
import sys
import yaml
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import process_metric_day as pmd  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures" / "garmin"


def _setup_base(tmp_path: Path) -> Path:
    """Build a minimal Minder Memory base layout under tmp_path."""
    base = tmp_path / "base"
    (base / "_records" / "biometric").mkdir(parents=True)
    (base / "_system" / "state" / "biometric").mkdir(parents=True)
    (base / "_system" / "state").mkdir(parents=True, exist_ok=True)
    (base / "_sources" / "inbox" / "garmin").mkdir(parents=True)
    (base / "_sources" / "processed" / "garmin").mkdir(parents=True)
    (base / "_system" / "scripts").mkdir(parents=True)
    # Copy thresholds yaml to expected path
    src_thr = SCRIPTS_DIR / "biometric_thresholds.yaml"
    shutil.copy(src_thr, base / "_system" / "scripts" / "biometric_thresholds.yaml")
    return base


def _stage_source(base: Path, fixture_name: str, target_name: str | None = None) -> Path:
    """Copy fixture into the base inbox and return the staged path."""
    target_name = target_name or fixture_name
    target = base / "_sources" / "inbox" / "garmin" / target_name
    shutil.copy(FIXTURES / fixture_name, target)
    return target


def test_failure_stub_no_record_emitted(tmp_path):
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-02-failure.md")
    res = pmd.run(src, base_dir=base)
    assert res.outcome == "skipped-failure-stub"
    assert not (base / "_records" / "biometric" / "garmin" / "2024-01-02.md").exists()
    # source moved to processed
    assert (base / "_sources" / "processed" / "garmin" / "2024-01-02-failure.md").exists()


def test_emit_record_on_clean_source(tmp_path):
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    res = pmd.run(src, base_dir=base)
    assert res.outcome == "emitted"
    rec = base / "_records" / "biometric" / "garmin" / "2024-01-01.md"
    assert rec.exists()
    text = rec.read_text(encoding="utf-8")
    assert "kind: biometric" in text
    assert "is_sensitive: true" in text
    assert "audience_tags: []" in text
    assert "origin: personal" in text
    assert "## Key Numbers" in text
    assert "sleep_h: 7.05" in text
    # source moved to processed
    assert not src.exists()
    assert (base / "_sources" / "processed" / "garmin" / "2024-01-01.md").exists()


def test_idempotent_re_run_same_content_noop(tmp_path):
    """If source already processed (in `processed/`) and record exists with
    matching source_hash, re-running the orchestrator on a fresh inbox
    copy of the same source is a no-op."""
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    pmd.run(src, base_dir=base)
    rec = base / "_records" / "biometric" / "garmin" / "2024-01-01.md"
    text_before = rec.read_text(encoding="utf-8")
    # Re-stage the same source content
    src = _stage_source(base, "2024-01-01.md")
    res = pmd.run(src, base_dir=base)
    assert res.outcome == "no-op-same-content"
    text_after = rec.read_text(encoding="utf-8")
    assert text_before == text_after


def _make_empty_ok_source(rich_text: str) -> str:
    """Strip the `## Detailed data` section → a status-ok source that
    aggregates to zero metrics (the device→cloud sync-gap shape)."""
    i = rich_text.find("\n## Detailed data")
    body = rich_text if i < 0 else rich_text[:i] + "\n"
    return body.replace(
        "## Summary\n", "## Summary\n_(no summary metrics aggregated)_\n", 1
    )


def test_rerender_auto_absorb_on_richer_or_equal(tmp_path):
    """A re-collected day with equal-or-greater richness is absorbed
    automatically (no CLARIFICATION); the record updates to the new data."""
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    pmd.run(src, base_dir=base)
    rec = base / "_records" / "biometric" / "garmin" / "2024-01-01.md"
    assert "sleep_score: 82" in rec.read_text(encoding="utf-8")
    # Re-collect with a changed value (same richness) — latest device data wins.
    src = _stage_source(base, "2024-01-01.md")
    text = src.read_text(encoding="utf-8")
    src.write_text(text.replace("value: 82", "value: 71"), encoding="utf-8")
    res = pmd.run(src, base_dir=base)
    assert res.outcome == "rerender-auto-absorbed"
    assert not res.clarifications
    assert "sleep_score: 71" in rec.read_text(encoding="utf-8")


def test_rerender_empty_to_rich_auto_absorbs(tmp_path):
    """The incident shape: an empty (device→cloud gap) day was recorded, then
    the sync heals and the day re-collects rich → absorbed automatically."""
    base = _setup_base(tmp_path)
    rich = (FIXTURES / "2024-01-01.md").read_text(encoding="utf-8")
    empty_path = base / "_sources" / "inbox" / "garmin" / "2024-01-01.md"
    empty_path.write_text(_make_empty_ok_source(rich), encoding="utf-8")
    pmd.run(empty_path, base_dir=base)
    rec = base / "_records" / "biometric" / "garmin" / "2024-01-01.md"
    assert "no summary metrics aggregated" in rec.read_text(encoding="utf-8")
    # Sync heals — re-collect the rich source.
    src = _stage_source(base, "2024-01-01.md")
    res = pmd.run(src, base_dir=base)
    assert res.outcome == "rerender-auto-absorbed"
    text = rec.read_text(encoding="utf-8")
    assert "no summary metrics aggregated" not in text
    assert "sleep_h: 7.05" in text


def test_rerender_keeps_existing_on_poorer_recollect(tmp_path):
    """A re-collect that came back poorer/empty must NOT clobber a good record."""
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    pmd.run(src, base_dir=base)
    rec = base / "_records" / "biometric" / "garmin" / "2024-01-01.md"
    good = rec.read_text(encoding="utf-8")
    assert "sleep_h: 7.05" in good
    # Re-collect empty (device stopped syncing again) — must not overwrite.
    empty_path = base / "_sources" / "inbox" / "garmin" / "2024-01-01.md"
    empty_path.write_text(
        _make_empty_ok_source((FIXTURES / "2024-01-01.md").read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    res = pmd.run(empty_path, base_dir=base)
    assert res.outcome == "rerender-kept-existing"
    assert not res.clarifications
    assert rec.read_text(encoding="utf-8") == good  # unchanged


def test_bulk_rerender_auto_absorb_no_inbox_collision(tmp_path):
    """A multi-day bulk re-collect in ONE batch — the real healed-sync-gap
    scenario. Auto-absorb replays baselines forward from inside run(); that
    replay must NOT round-trip through the shared inbox, or it clobbers the
    still-pending days (silent data loss) and crashes the batch. Every day's
    record must reflect its OWN re-collected value, with no duplicate baseline
    entries."""
    base = _setup_base(tmp_path)
    days = {"2024-01-01": "11", "2024-01-02": "22", "2024-01-03": "33"}
    # First pass: three ordinary rich days.
    for iso in days:
        src = _stage_source(base, "2024-01-01.md", target_name=f"{iso}.md")
        src.write_text(src.read_text(encoding="utf-8").replace("'2024-01-01'", f"'{iso}'"), encoding="utf-8")
        pmd.run(src, base_dir=base)
    # Second pass: re-collect all three with a changed score, in one batch.
    staged = []
    for iso, val in days.items():
        src = _stage_source(base, "2024-01-01.md", target_name=f"{iso}.md")
        text = src.read_text(encoding="utf-8").replace("'2024-01-01'", f"'{iso}'").replace("value: 82", f"value: {val}")
        src.write_text(text, encoding="utf-8")
        staged.append(src)
    results = pmd.run_batch(sorted(staged), base_dir=base)  # must not raise
    assert all(r.outcome == "rerender-auto-absorbed" for r in results)
    for iso, val in days.items():
        rec = (base / "_records" / "biometric" / "garmin" / f"{iso}.md").read_text(encoding="utf-8")
        assert f"sleep_score: {val}" in rec, f"{iso} did not absorb its own re-collected value"
    import json
    bl = json.loads((base / "_system" / "state" / "biometric" / "garmin" / "baselines.json").read_text(encoding="utf-8"))
    dates = [v["date"] for v in bl["metrics"]["sleep_score"]["values"]]
    assert len(dates) == len(set(dates)), "duplicate baseline dates after bulk re-collect"
    assert set(dates) == set(days), dates


def test_categorical_event_detection(tmp_path):
    base = _setup_base(tmp_path)
    # Day 1 — HIGH readiness, BALANCED HRV
    src1 = _stage_source(base, "2024-01-01.md")
    pmd.run(src1, base_dir=base)
    # Day 2 — same fixture but readiness drops to MODERATE, HRV → UNBALANCED
    src2 = _stage_source(base, "2024-01-01.md", target_name="2024-01-02.md")
    text = src2.read_text(encoding="utf-8")
    text = text.replace("'2024-01-01'", "'2024-01-02'")
    text = text.replace("level: HIGH", "level: MODERATE")
    text = text.replace("status: BALANCED", "status: UNBALANCED")
    src2.write_text(text, encoding="utf-8")
    res = pmd.run(src2, base_dir=base)
    assert res.outcome == "emitted"
    assert any("Readiness changed" in e for e in res.categorical_events)
    assert any("HRV status changed" in e for e in res.categorical_events)
    rec = (base / "_records" / "biometric" / "garmin" / "2024-01-02.md").read_text(encoding="utf-8")
    assert "## Categorical Events" in rec


def test_streak_emission_on_three_day_low_hrv(tmp_path):
    """Sequence: three consecutive days with hrv below baseline → state-concept
    `low_hrv_streak` appears in concepts on day 3."""
    base = _setup_base(tmp_path)
    # Build a 30-day baseline with hrv ≈ 30 ± small variance, then 3 deviation days
    template = (FIXTURES / "2024-01-01.md").read_text(encoding="utf-8")
    # Days 01-30 baseline
    for d in range(1, 31):
        date = f"2024-02-{d:02d}"
        body = template.replace("'2024-01-01'", f"'{date}'")
        # hrv varies tiny: 29/30/31
        hrv = [29, 30, 31][d % 3]
        body = body.replace("lastNightAvg: 30", f"lastNightAvg: {hrv}")
        # also keep sleep stable
        path = base / "_sources" / "inbox" / "garmin" / f"{date}.md"
        path.write_text(body, encoding="utf-8")
        pmd.run(path, base_dir=base)
    # Now days 31, 32, 33 — sharp drop to hrv 20 (~3σ low)
    last_concepts: list[str] = []
    for d, label in [(1, "2024-03-01"), (2, "2024-03-02"), (3, "2024-03-03")]:
        body = template.replace("'2024-01-01'", f"'{label}'")
        body = body.replace("lastNightAvg: 30", "lastNightAvg: 20")
        body = body.replace("(BALANCED)", "(BALANCED)")  # status field already BALANCED
        path = base / "_sources" / "inbox" / "garmin" / f"{label}.md"
        path.write_text(body, encoding="utf-8")
        res = pmd.run(path, base_dir=base)
        last_concepts = res.concepts
    assert "low_hrv_streak" in last_concepts


def test_first_run_emits_cold_start_clarification(tmp_path):
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    res = pmd.run(src, base_dir=base)
    assert any(c["type"] == "biometric-baseline-cold-start" for c in res.clarifications)


def test_batch_manifest_emission(tmp_path):
    """run_batch with --batch-id writes a v2-conformant manifest at
    `_system/state/batches/{batch_id}.json` with biometric records under
    `records.created`."""
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    pmd.run_batch([src], base_dir=base, batch_id="20240101-120000")
    manifest_path = base / "_system" / "state" / "batches" / "20240101-120000.json"
    assert manifest_path.exists()
    import json
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert m["batch_id"] == "20240101-120000"
    assert m["format_version"] == "2.0"
    assert m["processor"] == "minder:mem:process"
    created = m["records"]["created"]
    assert len(created) == 1
    entry = created[0]
    assert entry["primary_type"] == "biometric"
    assert entry["is_sensitive"] is True
    assert entry["audience_tags"] == []
    assert entry["origin"] == "personal"
    assert "checksum_sha256" in entry
    assert entry["section_extras"]["date"] == "2024-01-01"


def test_batch_manifest_auto_absorb_goes_to_updated(tmp_path):
    """An auto-absorbed re-render heals an existing record → it must land in the
    manifest's `records.updated` (not `created`), so a downstream consumer keyed
    on the manifest sees the heal (ENGINE_DOCTRINE §3.8)."""
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    pmd.run_batch([src], base_dir=base, batch_id="20240101-120000")
    # Re-collect the same day with a changed value in a second batch.
    src = _stage_source(base, "2024-01-01.md")
    src.write_text(src.read_text(encoding="utf-8").replace("value: 82", "value: 71"), encoding="utf-8")
    results = pmd.run_batch([src], base_dir=base, batch_id="20240101-130000")
    assert results[0].outcome == "rerender-auto-absorbed"
    import json
    m = json.loads((base / "_system" / "state" / "batches" / "20240101-130000.json").read_text(encoding="utf-8"))
    assert len(m["records"]["created"]) == 0, "a heal is an update, not a creation"
    updated = m["records"]["updated"]
    assert len(updated) == 1
    assert updated[0]["id"] == "2024-01-01"
    assert updated[0]["primary_type"] == "biometric"
    assert "checksum_sha256" in updated[0]
    # The processed source is tracked too.
    assert any(s["source_id"] == "2024-01-01" for s in m["sources_processed"])


def test_append_update_to_record(tmp_path):
    """append_update_to_record adds `## Update YYYY-MM-DD` section with diff."""
    base = _setup_base(tmp_path)
    src = _stage_source(base, "2024-01-01.md")
    pmd.run(src, base_dir=base)
    rec = base / "_records" / "biometric" / "garmin" / "2024-01-01.md"
    original = rec.read_text(encoding="utf-8")
    # Modify the processed source as if re-collected with different sleep_h
    proc = base / "_sources" / "processed" / "garmin" / "2024-01-01.md"
    text = proc.read_text(encoding="utf-8")
    proc.write_text(text.replace("score 82", "score 71"), encoding="utf-8")
    target = pmd.append_update_to_record(base, date="2024-01-01",
                                         today=__import__("datetime").datetime(2024, 6, 1))
    updated = target.read_text(encoding="utf-8")
    assert original in updated  # original preserved
    assert "## Update 2024-06-01" in updated
    assert "Key Numbers diff" in updated
    assert "sleep_score" in updated  # the field that changed


def test_recompute_baselines_forward(tmp_path):
    """recompute_baselines_forward truncates baselines + replays records."""
    base = _setup_base(tmp_path)
    # Process 3 days
    import shutil
    template = (FIXTURES / "2024-01-01.md").read_text(encoding="utf-8")
    for d in range(1, 4):
        date = f"2024-01-{d:02d}"
        body = template.replace("'2024-01-01'", f"'{date}'")
        path = base / "_sources" / "inbox" / "garmin" / f"{date}.md"
        path.write_text(body, encoding="utf-8")
        pmd.run(path, base_dir=base)
    # Sanity — 3 records emitted
    assert len(list((base / "_records" / "biometric" / "garmin").glob("2024-*.md"))) == 3

    # Recompute from day 2 forward
    summary = pmd.recompute_baselines_forward(base, from_date="2024-01-02")
    assert summary["records_replayed"] == 2
    # Baselines now hold only day 1's values (others truncated and replayed)
    import json
    bl = json.loads((base / "_system" / "state" / "biometric" / "garmin" / "baselines.json").read_text(encoding="utf-8"))
    sleep = bl["metrics"]["sleep_h"]
    # 3 values total again after replay (day 1 kept + 2 + 3 replayed)
    assert sleep["n"] == 3


def test_batch_manifest_merges_existing(tmp_path):
    """When batch manifest already exists (e.g. transcripts wrote it
    first in a mixed batch), the biometric records.created entries
    merge into the existing structure rather than overwriting."""
    base = _setup_base(tmp_path)
    pre_manifest = base / "_system" / "state" / "batches" / "20240101-120000.json"
    pre_manifest.parent.mkdir(parents=True, exist_ok=True)
    import json
    pre_manifest.write_text(json.dumps({
        "batch_id": "20240101-120000",
        "format_version": "2.0",
        "processor": "minder:mem:process",
        "records": {"created": [{"path": "_records/meetings/foo.md", "primary_type": "meeting"}], "updated": []},
        "sources_processed": [{"path": "_sources/processed/plaud/foo/transcript.md", "source_type": "plaud", "source_id": "foo"}],
    }), encoding="utf-8")
    src = _stage_source(base, "2024-01-01.md")
    pmd.run_batch([src], base_dir=base, batch_id="20240101-120000")
    m = json.loads(pre_manifest.read_text(encoding="utf-8"))
    types = {e["primary_type"] for e in m["records"]["created"]}
    assert types == {"meeting", "biometric"}
