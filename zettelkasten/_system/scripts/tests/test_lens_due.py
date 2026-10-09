"""lens_due.py — which lenses run tonight."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lens_due  # noqa: E402

THU = dt.date(2026, 10, 8)  # a Thursday


def _base(tmp_path: Path, lenses: dict, runs: list) -> Path:
    base = tmp_path / "zettelkasten"
    for lens_id, fields in lenses.items():
        folder = base / lens_due.LENSES_DIR / lens_id
        folder.mkdir(parents=True)
        front = {"id": lens_id, "status": "active", **fields}
        lines = "".join(f"{k}: {v}\n" for k, v in front.items())
        (folder / "prompt.md").write_text(f"---\n{lines}---\n\n# {lens_id}\n", encoding="utf-8")
    runs_path = base / lens_due.RUNS
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    runs_path.write_text("".join(
        json.dumps({"lens_id": lens_id, "run_at": f"{day}T02:40:00Z", "status": status}) + "\n"
        for lens_id, day, status in runs), encoding="utf-8")
    return base


def _due(base: Path, today: dt.date) -> dict:
    return dict(lens_due.due(base, today))


WEEKLY_THU = {"cadence": "weekly", "cadence_anchor": "thursday"}


def test_a_lens_that_ran_today_is_not_due_again_today(tmp_path: Path) -> None:
    base = _base(tmp_path, {"daily-one": {"cadence": "daily"}, "weekly-one": WEEKLY_THU},
                 [("daily-one", THU, "empty"), ("weekly-one", THU, "ok")])
    assert _due(base, THU) == {}
    assert _due(base, THU + dt.timedelta(days=1)) == {"daily-one": "scheduled"}


def test_weekly_runs_on_its_anchor_after_a_week(tmp_path: Path) -> None:
    base = _base(tmp_path, {"weekly-one": WEEKLY_THU},
                 [("weekly-one", THU - dt.timedelta(days=7), "ok")])
    assert _due(base, THU) == {"weekly-one": "scheduled"}
    assert _due(base, THU + dt.timedelta(days=1)) == {}
    fresh = _base(tmp_path / "b", {"weekly-one": WEEKLY_THU}, [])
    assert _due(fresh, THU) == {"weekly-one": "scheduled"}, "first run: the anchor decides"


def test_an_error_on_its_day_is_retried_for_two_nights_then_waits(tmp_path: Path) -> None:
    base = _base(tmp_path, {"weekly-one": WEEKLY_THU},
                 [("weekly-one", THU - dt.timedelta(days=7), "ok"),
                  ("weekly-one", THU, "error"),
                  ("weekly-one", THU + dt.timedelta(days=1), "error")])
    assert _due(base, THU + dt.timedelta(days=1)) == {"weekly-one": "retry"}
    assert _due(base, THU + dt.timedelta(days=2)) == {"weekly-one": "retry"}
    assert _due(base, THU + dt.timedelta(days=3)) == {}, "the window counts from the first error"


def test_a_successful_retry_ends_the_retries(tmp_path: Path) -> None:
    base = _base(tmp_path, {"weekly-one": WEEKLY_THU},
                 [("weekly-one", THU, "error"), ("weekly-one", THU + dt.timedelta(days=1), "ok")])
    assert _due(base, THU + dt.timedelta(days=2)) == {}
    assert _due(base, THU + dt.timedelta(days=7)) == {"weekly-one": "scheduled"}


def test_a_rejected_output_is_not_retried_early(tmp_path: Path) -> None:
    base = _base(tmp_path, {"weekly-one": WEEKLY_THU},
                 [("weekly-one", THU, "error"), ("weekly-one", THU, "rejected")])
    assert _due(base, THU + dt.timedelta(days=1)) == {}


def test_monthly_and_biweekly_and_inactive(tmp_path: Path) -> None:
    base = _base(tmp_path, {
        "monthly-one": {"cadence": "monthly", "cadence_anchor": 8},
        "biweekly-one": {"cadence": "biweekly", "cadence_anchor": "thursday"},
        "paused-one": {"cadence": "daily", "status": "paused"},
    }, [("monthly-one", dt.date(2026, 9, 8), "ok"),
        ("biweekly-one", THU - dt.timedelta(days=7), "ok")])
    assert _due(base, THU) == {"monthly-one": "scheduled"}
    assert _due(base, THU + dt.timedelta(days=7)) == {"biweekly-one": "scheduled"}


def test_cli_prints_one_line_per_due_lens(tmp_path: Path, capsys) -> None:
    base = _base(tmp_path, {"weekly-one": WEEKLY_THU}, [])
    assert lens_due.main(["due", "--base", str(base), "--today", THU.isoformat()]) == 0
    assert capsys.readouterr().out == "weekly-one scheduled\n"


def test_a_retry_that_succeeds_late_never_costs_the_next_turn(tmp_path: Path) -> None:
    base = _base(tmp_path, {
        "weekly-one": WEEKLY_THU,
        "biweekly-one": {"cadence": "biweekly", "cadence_anchor": "thursday"},
        "monthly-one": {"cadence": "monthly", "cadence_anchor": 28},
    }, [("weekly-one", THU, "error"), ("weekly-one", THU + dt.timedelta(days=2), "ok"),
        ("biweekly-one", THU, "error"), ("biweekly-one", THU + dt.timedelta(days=2), "ok"),
        ("monthly-one", dt.date(2026, 9, 28), "error"), ("monthly-one", dt.date(2026, 9, 30), "ok")])
    assert _due(base, THU + dt.timedelta(days=7)) == {"weekly-one": "scheduled"}
    assert _due(base, THU + dt.timedelta(days=14)) == {"weekly-one": "scheduled",
                                                       "biweekly-one": "scheduled"}
    assert _due(base, dt.date(2026, 10, 28)) == {"monthly-one": "scheduled"}


def test_a_run_by_hand_just_before_the_anchor_is_not_repeated(tmp_path: Path) -> None:
    base = _base(tmp_path, {"weekly-one": WEEKLY_THU,
                            "biweekly-one": {"cadence": "biweekly", "cadence_anchor": "thursday"}},
                 [("weekly-one", THU - dt.timedelta(days=3), "ok"),
                  ("biweekly-one", THU - dt.timedelta(days=7), "ok")])
    assert _due(base, THU) == {}, "within the window: the hand run counts as this turn"


def test_each_failed_anchor_gets_its_own_retry(tmp_path: Path) -> None:
    week = dt.timedelta(days=7)
    base = _base(tmp_path, {"weekly-one": WEEKLY_THU, "never-ok": WEEKLY_THU},
                 [("weekly-one", THU - 30 * dt.timedelta(days=1), "ok"),
                  ("weekly-one", THU - week, "error"),
                  ("weekly-one", THU - week + dt.timedelta(days=1), "error"),
                  ("weekly-one", THU - week + dt.timedelta(days=2), "error"),
                  ("weekly-one", THU, "error"),
                  ("never-ok", THU - week, "error"), ("never-ok", THU, "error")])
    assert _due(base, THU + dt.timedelta(days=1)) == {"weekly-one": "retry", "never-ok": "retry"}


def test_only_an_error_today_leaves_the_lens_due_today(tmp_path: Path) -> None:
    base = _base(tmp_path, {"rejected-one": WEEKLY_THU, "error-one": WEEKLY_THU,
                            "skipped-one": WEEKLY_THU},
                 [("rejected-one", THU, "rejected"), ("error-one", THU, "error"),
                  ("skipped-one", THU, "skipped")])
    assert _due(base, THU) == {"error-one": "scheduled"}


def test_a_monthly_hand_run_does_not_cost_the_next_anchor(tmp_path: Path) -> None:
    base = _base(tmp_path, {"monthly-one": {"cadence": "monthly", "cadence_anchor": "1"},
                            "monthly-late": {"cadence": "monthly", "cadence_anchor": 31}},
                 [("monthly-one", dt.date(2026, 10, 10), "ok")])
    assert _due(base, dt.date(2026, 11, 1)) == {"monthly-one": "scheduled"}
    assert _due(base, dt.date(2027, 2, 28)) == {"monthly-late": "scheduled"}


def test_anchor_spelling_is_forgiving(tmp_path: Path) -> None:
    base = _base(tmp_path, {"weekly-one": {"cadence": "weekly", "cadence_anchor": "Thursday "}}, [])
    assert _due(base, THU) == {"weekly-one": "scheduled"}


def test_a_duplicate_id_runs_neither_lens(tmp_path: Path, capsys) -> None:
    base = _base(tmp_path, {"a-folder": {"id": "same", "cadence": "daily"},
                            "b-folder": {"id": "same", "cadence": "daily"},
                            "other": {"cadence": "daily"}}, [])
    assert _due(base, THU) == {"other": "scheduled"}
    assert "same" in capsys.readouterr().err


def test_a_missing_registry_or_bad_date_fails_loudly(tmp_path: Path) -> None:
    assert lens_due.main(["due", "--base", str(tmp_path)]) == 2
    base = _base(tmp_path / "b", {"weekly-one": WEEKLY_THU}, [])
    try:
        lens_due.main(["due", "--base", str(base), "--today", "tomorrow"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("an unreadable --today must not pass silently")
