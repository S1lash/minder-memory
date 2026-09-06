#!/usr/bin/env python3
"""Validate recent Minder Memory engine batch manifests against the published JSON
Schema (`_system/docs/manifest-schema/v{N}.json`).

Defence-in-depth gate: producer-side normalisers in
`emit_batch_manifest.py` already conform manifests at write time. This
helper re-checks the on-disk artefact, catching:
- producer bugs that ship malformed manifests
- manual edits / shell scripts writing into `_system/state/batches/`
- schema drift introduced by a new feature without coordinated bump

Behaviour matches the autonomous-resolution doctrine §3.1 exception
*inversely*: the manifest contract is NOT autonomous — every violation
surfaces as a CLARIFICATION for the owner, never silently mutated. The
file as written is canonical evidence; this helper diagnoses, does not
rewrite.

Outputs JSONL on stdout, one event per line:

    {"kind": "violation", "batch": "<filename>", "format_version": "...",
     "errors": [{"path": [...], "message": "...", "schema_path": [...]}]}
    {"kind": "unknown-version", "batch": "<filename>",
     "format_version": "...", "available_majors": [2, ...]}
    {"kind": "internal-error", "batch": "<filename>", "error": "..."}
    {"kind": "ok", "batch": "<filename>", "format_version": "..."}
    {"kind": "skipped-pre-baseline", "batch": "<filename>",
     "baseline": "<iso ts>"}

Each non-`ok` line is the payload `/minder:mem:lint` Scan G converts into a
CLARIFICATION (`manifest-schema-violation: <batch_id>`,
`manifest-schema-unknown-version: <batch_id>`, or
`validator-internal-error: <batch_id>`).

Exit codes:
- 0 — scan completed (regardless of how many violations found)
- 2 — invocation error (schemas dir missing, jsonschema not installed,
  args malformed)

Fail-open: per-file errors are JSONL events; the helper always exits 0
on a successful scan completion.

Usage:
    python3 lint_manifest_schema.py \\
        --batches-dir _system/state/batches \\
        --schemas-dir _system/docs/manifest-schema \\
        [--baseline-file _system/state/batches/.validator-baseline] \\
        [--window-hours 26] \\
        [--init-baseline] \\
        [--all]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _common import configure_std_streams  # type: ignore

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    # NOT an error. The nightly tick runs in an ephemeral sandbox that ships
    # no third-party packages, so requiring this one meant installing it on
    # every single run and reporting the install in every single log — a cost
    # and a line of noise repeated nightly, forever, for a defence-in-depth
    # scan.
    #
    # So the scan degrades instead of refusing. Without jsonschema it applies
    # the SHALLOW contract check — the same `validate_manifest` the producer
    # runs at emission (top-level keys, processor enum, format_version major,
    # per-processor required sections), imported rather than restated so the
    # two cannot drift. What is lost is the deep per-field validation, and
    # every degraded run says so in its output rather than passing quietly as
    # if the full check had run.
    Draft202012Validator = None  # type: ignore[assignment]


SCHEMA_FILENAME_RE = re.compile(r"^v(\d+)(?:\.(\d+))?\.json$")


def load_schemas(schemas_dir: Path) -> dict[int, tuple[Path, dict]]:
    """Discover `v{MAJOR}.json` (and optional `v{MAJOR}.{MINOR}.json`)
    files in the schemas dir. Pick the highest-MINOR per MAJOR.
    Returns {major: (path, parsed_schema)}.
    """
    candidates: dict[int, tuple[int, Path]] = {}
    for entry in schemas_dir.iterdir():
        if not entry.is_file():
            continue
        m = SCHEMA_FILENAME_RE.match(entry.name)
        if not m:
            continue
        major = int(m.group(1))
        minor = int(m.group(2)) if m.group(2) else 0
        prev = candidates.get(major)
        if prev is None or minor > prev[0]:
            candidates[major] = (minor, entry)
    out: dict[int, tuple[Path, dict]] = {}
    for major, (_, path) in candidates.items():
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"lint_manifest_schema: schema {path} is not valid JSON: "
                f"{exc}\n"
            )
            continue
        try:
            if Draft202012Validator is not None:
                Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 — surface any metaschema break
            sys.stderr.write(
                f"lint_manifest_schema: schema {path} fails Draft 2020-12 "
                f"metaschema check: {exc}\n"
            )
            continue
        out[major] = (path, schema)
    return out


def parse_format_major(value) -> int | None:
    if not isinstance(value, str) or "." not in value:
        return None
    try:
        return int(value.split(".", 1)[0])
    except ValueError:
        return None


def batch_timestamp_from_filename(name: str) -> datetime | None:
    """Filenames are `{YYYYMMDD-HHMMSS}[-{skill}].json`. Parse leading
    timestamp; return UTC datetime or None.
    """
    m = re.match(r"^(\d{8})-(\d{6})", name)
    if not m:
        return None
    try:
        return datetime.strptime(
            m.group(1) + m.group(2), "%Y%m%d%H%M%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def read_baseline(path: Path) -> datetime | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        sys.stderr.write(
            f"lint_manifest_schema: baseline file {path} content not parseable "
            f"as ISO-8601: {text!r} — treating as absent.\n"
        )
        return None


def write_baseline(path: Path, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n",
        encoding="utf-8",
    )


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")


def validate_one(
    path: Path, schemas: dict[int, tuple[Path, dict]],
) -> None:
    """Validate a single batch file, emit one event."""
    name = path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        emit({
            "kind": "internal-error",
            "batch": name,
            "error": f"json-parse: {exc}",
        })
        return
    if not isinstance(data, dict):
        emit({
            "kind": "internal-error",
            "batch": name,
            "error": "manifest root not an object",
        })
        return

    fv = data.get("format_version")
    major = parse_format_major(fv)
    if major is None:
        emit({
            "kind": "violation",
            "batch": name,
            "format_version": fv,
            "errors": [{
                "path": ["format_version"],
                "message":
                    "missing or unparseable format_version "
                    "(expected string 'MAJOR.MINOR')",
                "schema_path": [],
            }],
        })
        return

    if major not in schemas:
        emit({
            "kind": "unknown-version",
            "batch": name,
            "format_version": fv,
            "available_majors": sorted(schemas.keys()),
        })
        return

    # A manifest the retrofit could not make valid by any deterministic repair
    # carries `section_extras.quarantine` with the reason. Re-raising it every
    # night would be a permanent nag over a state that is already recorded and
    # cannot be improved without inventing data. It is reported once, as its own
    # event kind, so the count stays visible without producing CLARIFICATIONs.
    extras = data.get("section_extras")
    if isinstance(extras, dict) and isinstance(extras.get("quarantine"), dict):
        emit({
            "kind": "quarantined",
            "batch": name,
            "format_version": fv,
            "reason": str(extras["quarantine"].get("reason", ""))[:300],
            "marked": extras["quarantine"].get("marked"),
        })
        return

    _, schema = schemas[major]
    if Draft202012Validator is None:
        # Degraded path: the shallow contract only. Imported from the producer
        # so there is one definition of «structurally valid», not two.
        try:
            from emit_batch_manifest import (  # type: ignore
                ManifestValidationError, validate_manifest,
            )
            validate_manifest(data)
        except ModuleNotFoundError as exc:
            emit({
                "kind": "internal-error",
                "batch": name,
                "error": f"degraded-check-unavailable: {exc}",
            })
            return
        except Exception as exc:  # noqa: BLE001 — ManifestValidationError et al
            emit({
                "kind": "violation",
                "batch": name,
                "format_version": fv,
                "degraded": True,
                "errors": [{"path": [], "message": str(exc), "schema_path": []}],
                "errors_truncated": False,
            })
            return
        emit({"kind": "ok", "batch": name, "format_version": fv, "degraded": True})
        return

    try:
        validator = Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
    except Exception as exc:  # noqa: BLE001 — fail-open, catch any validator bug
        emit({
            "kind": "internal-error",
            "batch": name,
            "error": f"validator-exception: {type(exc).__name__}: {exc}",
        })
        return

    if not errors:
        emit({"kind": "ok", "batch": name, "format_version": fv})
        return

    serialized = []
    for err in errors[:50]:  # cap at 50 to keep events small
        serialized.append({
            "path": list(err.absolute_path),
            "message": str(err.message)[:500],
            "schema_path": list(err.absolute_schema_path),
        })
    emit({
        "kind": "violation",
        "batch": name,
        "format_version": fv,
        "errors": serialized,
        "errors_truncated": len(errors) > 50,
        "errors_total": len(errors),
    })


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches-dir", type=Path, required=True)
    parser.add_argument("--schemas-dir", type=Path, required=True)
    parser.add_argument(
        "--baseline-file", type=Path, default=None,
        help="Defaults to {batches-dir}/.validator-baseline",
    )
    parser.add_argument(
        "--window-hours", type=float, default=26.0,
        help="Validate batches newer than now - window-hours. Default 26 "
             "(24h coverage + 2h cron / TZ buffer).",
    )
    parser.add_argument(
        "--init-baseline", action="store_true",
        help="Write the baseline file with current UTC time if absent. "
             "Idempotent — does NOT overwrite an existing baseline.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Validate every JSON in batches-dir, ignoring baseline / "
             "window. Use for one-off audit / fixture sweeps.",
    )
    args = parser.parse_args(argv)

    if not args.batches_dir.exists():
        sys.stderr.write(
            f"lint_manifest_schema: batches-dir {args.batches_dir} does not exist\n"
        )
        return 2
    if not args.schemas_dir.exists():
        sys.stderr.write(
            f"lint_manifest_schema: schemas-dir {args.schemas_dir} does not exist\n"
        )
        return 2

    schemas = load_schemas(args.schemas_dir)
    if not schemas:
        sys.stderr.write(
            f"lint_manifest_schema: no v{{MAJOR}}.json schemas found in "
            f"{args.schemas_dir}\n"
        )
        return 2

    baseline_file = (
        args.baseline_file
        or args.batches_dir / ".validator-baseline"
    )
    baseline = read_baseline(baseline_file)
    if baseline is None and args.init_baseline:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        write_baseline(baseline_file, now)
        baseline = now
        sys.stderr.write(
            f"lint_manifest_schema: initialised baseline at "
            f"{baseline_file} = {now.isoformat()}\n"
        )

    cutoff_window = (
        datetime.now(timezone.utc) - timedelta(hours=args.window_hours)
    )

    batches = sorted(
        p for p in args.batches_dir.glob("*.json") if p.is_file()
    )
    for path in batches:
        if not args.all:
            ts = batch_timestamp_from_filename(path.name)
            if ts is None:
                # Filename doesn't carry a parseable timestamp — fall back to
                # mtime.
                ts = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc,
                )
            if baseline is not None and ts < baseline:
                emit({
                    "kind": "skipped-pre-baseline",
                    "batch": path.name,
                    "baseline": baseline.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
                continue
            if ts < cutoff_window:
                # Outside the rolling window; skip silently (no event).
                continue
        validate_one(path, schemas)

    return 0


if __name__ == "__main__":
    sys.exit(main())
