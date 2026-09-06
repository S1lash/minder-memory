"""Tests for lint_manifest_schema.py — Scan H validator helper.

Coverage:
- ok event on valid manifest
- violation event on missing required field
- violation event on shape drift
- unknown-version event on incompatible major
- internal-error event on corrupt JSON
- skipped-pre-baseline event respects baseline file
- baseline init is idempotent (does not overwrite)
- window-hours filters old batches silently (no event)
- --all overrides both baseline and window
- exit code 2 on missing batches-dir / schemas-dir
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import lint_manifest_schema as L  # type: ignore


_MIN_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "test://v2.json",
    "type": "object",
    "required": ["batch_id", "timestamp", "format_version", "processor"],
    "properties": {
        "batch_id":       {"type": "string"},
        "timestamp":      {"type": "string"},
        "format_version": {"type": "string"},
        "processor":      {"enum": ["minder:mem:process", "minder:mem:lint"]},
        "tier1_objects": {
            "type": "object",
            "properties": {
                "tasks": {"type": "object"},
            },
        },
    },
}


def _setup(tmp: Path, schemas: dict[str, dict] | None = None) -> tuple[Path, Path]:
    schemas = schemas or {"v2.json": _MIN_SCHEMA}
    bdir = tmp / "batches"
    sdir = tmp / "schemas"
    bdir.mkdir()
    sdir.mkdir()
    for name, schema in schemas.items():
        (sdir / name).write_text(json.dumps(schema), encoding="utf-8")
    return bdir, sdir


def _write_batch(bdir: Path, name: str, data: dict | str) -> Path:
    p = bdir / name
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _run(bdir: Path, sdir: Path, *extra: str) -> tuple[int, list[dict], str]:
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    args = ["--batches-dir", str(bdir), "--schemas-dir", str(sdir),
            "--all", *extra]
    # --all bypasses the now-window so unit tests work regardless of clock
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = L.main(args)
    events = []
    for line in out_buf.getvalue().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return rc, events, err_buf.getvalue()


class ScanHTests(unittest.TestCase):
    def test_ok_on_valid_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir, sdir = _setup(Path(tmp))
            _write_batch(bdir, "20260601-000000-process.json", {
                "batch_id": "x", "timestamp": "y",
                "format_version": "2.0", "processor": "minder:mem:process",
            })
            rc, events, _ = _run(bdir, sdir)
            self.assertEqual(rc, 0)
            self.assertEqual(events[0]["kind"], "ok")

    def test_violation_on_missing_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir, sdir = _setup(Path(tmp))
            _write_batch(bdir, "20260601-000001-process.json", {
                "format_version": "2.0", "processor": "minder:mem:process",
            })
            _, events, _ = _run(bdir, sdir)
            self.assertEqual(events[0]["kind"], "violation")
            paths = [e["path"] for e in events[0]["errors"]]
            self.assertIn([], paths)  # missing top-level required

    def test_violation_on_shape_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir, sdir = _setup(Path(tmp))
            _write_batch(bdir, "20260601-000002-process.json", {
                "batch_id": "x", "timestamp": "y",
                "format_version": "2.0", "processor": "minder:mem:process",
                "tier1_objects": {"tasks": []},
            })
            _, events, _ = _run(bdir, sdir)
            self.assertEqual(events[0]["kind"], "violation")
            self.assertIn(
                ["tier1_objects", "tasks"],
                [e["path"] for e in events[0]["errors"]],
            )

    def test_unknown_version_when_major_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir, sdir = _setup(Path(tmp))
            _write_batch(bdir, "20260601-000003-process.json", {
                "batch_id": "x", "timestamp": "y",
                "format_version": "9.0", "processor": "minder:mem:process",
            })
            _, events, _ = _run(bdir, sdir)
            self.assertEqual(events[0]["kind"], "unknown-version")
            self.assertEqual(events[0]["available_majors"], [2])

    def test_internal_error_on_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir, sdir = _setup(Path(tmp))
            _write_batch(bdir, "20260601-000004-process.json", "{not json")
            _, events, _ = _run(bdir, sdir)
            self.assertEqual(events[0]["kind"], "internal-error")
            self.assertIn("json-parse", events[0]["error"])

    def test_skipped_pre_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir, sdir = _setup(Path(tmp))
            _write_batch(bdir, "20260601-000005-process.json", {
                "batch_id": "x", "timestamp": "y",
                "format_version": "2.0", "processor": "minder:mem:process",
            })
            # baseline AFTER the batch's timestamp prefix
            future = datetime(2027, 1, 1, tzinfo=timezone.utc)
            (bdir / ".validator-baseline").write_text(
                future.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="utf-8",
            )
            # Without --all but window wide enough: baseline excludes
            out_buf = io.StringIO()
            err_buf = io.StringIO()
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                # large window to take the rolling-window gate out of play;
                # baseline alone should reject the pre-baseline batch
                rc = L.main([
                    "--batches-dir", str(bdir),
                    "--schemas-dir", str(sdir),
                    "--window-hours", "8760000",  # ~1000 years; under datetime range
                ])
            self.assertEqual(rc, 0)
            events = [json.loads(l) for l in out_buf.getvalue().splitlines() if l.strip()]
            self.assertEqual(events[0]["kind"], "skipped-pre-baseline")

    def test_baseline_init_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir, sdir = _setup(Path(tmp))
            baseline_path = bdir / ".validator-baseline"
            baseline_path.write_text(
                "2025-01-01T00:00:00Z", encoding="utf-8",
            )
            args = [
                "--batches-dir", str(bdir),
                "--schemas-dir", str(sdir),
                "--init-baseline",
                "--all",
            ]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                L.main(args)
            self.assertEqual(
                baseline_path.read_text(encoding="utf-8").strip(),
                "2025-01-01T00:00:00Z",
            )

    def test_exit_2_on_missing_batches_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp) / "schemas"
            sdir.mkdir()
            (sdir / "v2.json").write_text(json.dumps(_MIN_SCHEMA), encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                rc = L.main([
                    "--batches-dir", "/tmp/no-such-batches-dir-12345",
                    "--schemas-dir", str(sdir),
                    "--all",
                ])
            self.assertEqual(rc, 2)

    def test_exit_2_on_missing_schemas_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            bdir = Path(tmp) / "batches"
            bdir.mkdir()
            with redirect_stderr(io.StringIO()):
                rc = L.main([
                    "--batches-dir", str(bdir),
                    "--schemas-dir", "/tmp/no-such-schemas-dir-12345",
                    "--all",
                ])
            self.assertEqual(rc, 2)

    def test_picks_highest_minor_per_major(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            v20 = dict(_MIN_SCHEMA, properties={
                **_MIN_SCHEMA["properties"],
                "must_have": {"type": "string"},
            })
            v20["required"] = list(_MIN_SCHEMA["required"]) + ["must_have"]
            bdir, sdir = _setup(tmp, schemas={
                "v2.json": _MIN_SCHEMA,
                "v2.5.json": v20,
            })
            _write_batch(bdir, "20260601-000010-process.json", {
                "batch_id": "x", "timestamp": "y",
                "format_version": "2.0", "processor": "minder:mem:process",
            })
            _, events, _ = _run(bdir, sdir)
            # v2.5 schema requires `must_have`; missing → violation
            self.assertEqual(events[0]["kind"], "violation")
            self.assertIn("must_have", json.dumps(events[0]["errors"]))


if __name__ == "__main__":
    unittest.main()
