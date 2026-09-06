#!/usr/bin/env python3
"""Append a check-decision telemetry line to the audit substrate.

Invoked by `/minder:mem:check-decision` from any session — pipelines, ad-hoc
agents, schedulers. Two modes:

  - `--kind run`     — full per-invocation record. Mandatory mechanical
                       fields are populated by the skill; optional
                       self-report fields (intent / pre_confidence /
                       expected_verdict) are passed through verbatim
                       when supplied, written as null when absent.
  - `--kind followup` — post-action signal referencing a prior run_id.
                       Looks up the original run's caller_class to
                       inherit auto-commit policy.

Atomic JSONL append under an advisory `flock`; per-class auto-commit
with graceful fallback (if git fails, JSONL line stays as source of
truth, helper exits 0). Path: `_system/state/check-decision-runs.jsonl`
+ `_system/state/.check-decision-runs.lock`.

Sensitive-redaction: when `--is-sensitive` is set on a run-line,
`situation_text` and `rationale` are omitted; `situation_hash` is
preserved for join purposes (one-way digest, not sensitive).

Schema notes:
  - Run-line fields:
      kind, run_id, run_at, caller_class, working_dir,
      situation_hash, situation_text?, is_sensitive,
      domains_filter, dry_run, record_ref, tree_size, status,
      verdict, citations, tradeoffs, rationale?,
      intent?, pre_confidence?, expected_verdict?
  - Followup-line fields:
      kind, run_id, followup_at, post_confidence,
      decision_taken, human_needed_after, verdict_resolved

The substrate is append-only by contract — never mutate prior lines.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import configure_std_streams, die, state_dir


JSONL_FILENAME = "check-decision-runs.jsonl"
# Same convention as the batch manifests and the tick odometer: a record
# format that consumers read carries the version they are reading.
FORMAT_VERSION = "1.0"
LOCK_FILENAME = ".check-decision-runs.lock"

CALLER_CLASSES = frozenset({"mechanical", "judgmental"})
MECHANICAL_PIPELINES = frozenset({
    "/minder:mem:process",
    "/minder:mem:lint",
    "/minder:mem:maintain",
    "/minder:mem:agent-lens",
    "/minder:mem:bootstrap",
    "/minder:mem:resolve-clarifications",
})

# `no-match` and `no-basis` are NOT interchangeable and consumers route them
# differently: `no-match` means principles were loaded and none applied — a
# real "the constitution does not object". `no-basis` means none were loaded
# at all, so there is nothing that could have objected. Collapsing the two
# reads an empty constitution as universal approval, which is how a fresh
# base ends up auto-applying everything it is asked about.
VERDICTS = frozenset({
    "aligned", "violated", "tradeoff", "no-match", "no-basis",
})
EXPECTED_VERDICTS = VERDICTS | {"unknown"}
CONFIDENCES = frozenset({"low", "medium", "high"})
RUN_STATUSES = frozenset({
    "ok",
    "failed_regen",
    "failed_query",
    "failed_edit",
})

SITUATION_TEXT_CAP = 120
RATIONALE_CAP = 500
RUN_ID_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z-[0-9a-f]{8}$"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_caller_class(args: argparse.Namespace) -> str:
    """Resolve caller_class from --from-pipeline (mechanical whitelist)
    or default judgmental.

    Forgery is possible (caller passes spurious --from-pipeline) but
    bounded: lens-side correlation (working_dir, caller_context patterns)
    surfaces mismatches, and the skill itself doesn't grant elevated
    capability based on caller_class.
    """
    if args.from_pipeline:
        if args.from_pipeline not in MECHANICAL_PIPELINES:
            die(
                f"--from-pipeline {args.from_pipeline!r} not in mechanical "
                f"whitelist {sorted(MECHANICAL_PIPELINES)}"
            )
        return "mechanical"
    return "judgmental"


def hash_situation(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate(value: str | None, cap: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) <= cap:
        return value
    return value[:cap]


def parse_json_arg(label: str, raw: str | None):
    if raw is None or raw.strip() == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"{label} expects JSON, got: {exc}")


def parse_domains(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


def parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    norm = raw.strip().lower()
    if norm in {"true", "yes", "1"}:
        return True
    if norm in {"false", "no", "0"}:
        return False
    die(f"expected boolean, got {raw!r}")


def build_run_entry(args: argparse.Namespace) -> dict:
    if not RUN_ID_RE.match(args.run_id):
        die(f"--run-id {args.run_id!r} does not match required format "
            f"YYYY-MM-DDTHH:MM:SSZ-<8-hex>")
    if args.status not in RUN_STATUSES:
        die(f"--status {args.status!r} not in {sorted(RUN_STATUSES)}")
    if not args.situation or not args.situation.strip():
        die("--situation must not be empty")

    caller_class = parse_caller_class(args)
    situation_clean = args.situation.strip()
    situation_hash_value = hash_situation(situation_clean)
    is_sensitive = bool(args.is_sensitive)

    if args.verdict is not None and args.verdict not in VERDICTS:
        die(f"--verdict {args.verdict!r} not in {sorted(VERDICTS)}")
    if (args.pre_confidence is not None
            and args.pre_confidence not in CONFIDENCES):
        die(f"--pre-confidence {args.pre_confidence!r} not in "
            f"{sorted(CONFIDENCES)}")
    if (args.expected_verdict is not None
            and args.expected_verdict not in EXPECTED_VERDICTS):
        die(f"--expected-verdict {args.expected_verdict!r} not in "
            f"{sorted(EXPECTED_VERDICTS)}")

    citations = parse_json_arg("--citations", args.citations) or []
    tradeoffs = parse_json_arg("--tradeoffs", args.tradeoffs) or []

    # Derive run_at from run_id prefix to keep the two consistent.
    run_at = args.run_id.rsplit("-", 1)[0]

    entry = {
        "kind": "run",
        "format_version": FORMAT_VERSION,
        "run_id": args.run_id,
        "run_at": run_at,
        "caller_class": caller_class,
        "from_pipeline": args.from_pipeline,
        "working_dir": args.working_dir or os.getcwd(),
        "situation_hash": situation_hash_value,
        "is_sensitive": is_sensitive,
        "domains_filter": parse_domains(args.domains),
        "dry_run": bool(args.dry_run_flag),
        "record_ref": args.record_ref,
        "tree_size": args.tree_size,
        "status": args.status,
        "verdict": args.verdict,
        "citations": citations,
        "tradeoffs": tradeoffs,
        "intent": (args.intent.strip() if args.intent else None),
        "pre_confidence": args.pre_confidence,
        "expected_verdict": args.expected_verdict,
    }

    if not is_sensitive:
        entry["situation_text"] = truncate(situation_clean, SITUATION_TEXT_CAP)
        entry["rationale"] = truncate(args.rationale, RATIONALE_CAP)

    return entry


def build_followup_entry(args: argparse.Namespace, jsonl_path: Path) -> dict:
    if not RUN_ID_RE.match(args.run_id):
        die(f"--run-id {args.run_id!r} does not match required format")
    if args.post_confidence not in CONFIDENCES:
        die(f"--post-confidence {args.post_confidence!r} not in "
            f"{sorted(CONFIDENCES)}")
    if not args.decision_taken or not args.decision_taken.strip():
        die("--decision-taken must not be empty")

    human_needed = parse_bool(args.human_needed_after)
    if human_needed is None:
        die("--human-needed-after is required for followup mode")
    verdict_resolved = parse_bool(args.verdict_resolved)
    if verdict_resolved is None:
        die("--verdict-resolved is required for followup mode")

    if not jsonl_path.exists():
        die(f"telemetry substrate {jsonl_path} does not exist — cannot "
            f"record followup for nonexistent run")

    if not _run_id_exists(jsonl_path, args.run_id):
        die(f"--run-id {args.run_id!r} not found in {jsonl_path.name} — "
            f"refusing to append orphan followup")

    return {
        "kind": "followup",
        "format_version": FORMAT_VERSION,
        "run_id": args.run_id,
        "followup_at": now_iso(),
        "post_confidence": args.post_confidence,
        "decision_taken": args.decision_taken.strip(),
        "human_needed_after": human_needed,
        "verdict_resolved": verdict_resolved,
    }


def _run_id_exists(jsonl_path: Path, run_id: str) -> bool:
    """Check whether a `kind: "run"` line with matching run_id exists.

    Linear scan — substrate is append-only and bounded by usage volume;
    any future indexing belongs to a downstream consumer, not this helper.
    """
    needle = f'"run_id": "{run_id}"'
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if needle in line and '"kind": "run"' in line:
                return True
    return False


def _lookup_run_caller_class(jsonl_path: Path, run_id: str) -> str:
    """Find the caller_class of the original run for a given run_id.

    Used in followup mode to inherit auto-commit policy. Defaults to
    judgmental on lookup failure (safer — extra commit beats lost
    audit trail).
    """
    if not jsonl_path.exists():
        return "judgmental"
    needle_id = f'"run_id": "{run_id}"'
    needle_kind = '"kind": "run"'
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if needle_id in line and needle_kind in line:
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cc = parsed.get("caller_class")
                if cc in CALLER_CLASSES:
                    return cc
    return "judgmental"


@contextlib.contextmanager
def acquire_lock(lock_path: Path):
    """Advisory exclusive flock around emit + commit.

    Scope is narrow: serialises concurrent telemetry writers from
    parallel sessions. Does NOT cover the rest of /minder:mem:check-decision
    (Evidence Trail edits remain unguarded — that race is pre-existing
    and out of this helper's scope).
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except ImportError:
            print(
                "warning: fcntl unavailable; proceeding without exclusive "
                "lock. Concurrent appenders may interleave.",
                file=sys.stderr,
            )
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
        fh.close()


def append_line(jsonl_path: Path, entry: dict) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    with jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def auto_commit(repo_root: Path, jsonl_path: Path, message: str) -> None:
    """Path-specific commit. Graceful fallback on any git failure.

    Never raises — telemetry must not block the verdict pipeline. JSONL
    line is the source of truth; commit is convenience for ad-hoc
    callers that won't trigger /minder:mem:save themselves.
    """
    rel = jsonl_path.relative_to(repo_root)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "add", str(rel)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print(
                f"warning: git add failed (rc={result.returncode}): "
                f"{result.stderr.strip()} — JSONL line written, commit "
                f"skipped; will be picked up by next /minder:mem:save",
                file=sys.stderr,
            )
            return
        result = subprocess.run(
            ["git", "-C", str(repo_root), "commit", "-m", message],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print(
                f"warning: git commit failed (rc={result.returncode}): "
                f"{result.stderr.strip()} — JSONL line written, commit "
                f"skipped; will be picked up by next /minder:mem:save",
                file=sys.stderr,
            )
    except FileNotFoundError:
        print(
            "warning: git executable not found — JSONL line written, "
            "commit skipped",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"warning: git commit raised {type(exc).__name__}: {exc} — "
            f"JSONL line written, commit skipped",
            file=sys.stderr,
        )


def repo_root_from_jsonl(jsonl_path: Path) -> Path:
    """Walk up from the JSONL path to find the git repo root.

    For Minder Memory setups with the repo rooted at the parent of `zettelkasten/`
    (current layout), repo root is two levels up from `_system/state/`.
    Use `git rev-parse` for robustness rather than hard-coding levels.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(jsonl_path.parent), "rev-parse",
             "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except FileNotFoundError:
        pass
    # Fallback: assume zettelkasten root is repo root.
    return jsonl_path.parent.parent.parent


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=("run", "followup"))
    parser.add_argument("--run-id", required=True,
                        help="ISO-timestamp + 8-hex suffix")
    parser.add_argument("--jsonl", type=Path, default=None,
                        help=f"override JSONL path (default: "
                             f"_system/state/{JSONL_FILENAME})")

    # Run-line fields
    parser.add_argument("--status", default=None,
                        help=f"one of {sorted(RUN_STATUSES)} (run mode)")
    parser.add_argument("--from-pipeline", default=None,
                        help="mechanical pipeline name; absence = judgmental")
    parser.add_argument("--working-dir", default=None,
                        help="caller's PWD; default = helper's CWD")
    parser.add_argument("--situation", default=None,
                        help="situation text; required in run mode")
    parser.add_argument("--is-sensitive", action="store_true",
                        help="redact situation_text + rationale; keep hash")
    parser.add_argument("--domains", default=None,
                        help="comma-separated domain filter")
    parser.add_argument("--dry-run-flag", action="store_true",
                        help="mark this run as dry-run in telemetry")
    parser.add_argument("--record-ref", default=None,
                        help="wiki-link to a record")
    parser.add_argument("--tree-size", type=int, default=None,
                        help="number of principles loaded after filter")
    parser.add_argument("--verdict", default=None,
                        help=f"one of {sorted(VERDICTS)}; null on failed runs")
    parser.add_argument("--citations", default=None,
                        help="JSON array of {id, relation}")
    parser.add_argument("--tradeoffs", default=None,
                        help="JSON array of {between, chosen, reason}")
    parser.add_argument("--rationale", default=None,
                        help="prose explanation; truncated at 500 chars; "
                             "omitted when is_sensitive")
    parser.add_argument("--intent", default=None,
                        help="optional self-report — caller's intent")
    parser.add_argument("--pre-confidence", default=None,
                        help=f"optional self-report; one of {sorted(CONFIDENCES)}")
    parser.add_argument("--expected-verdict", default=None,
                        help=f"optional self-report; one of "
                             f"{sorted(EXPECTED_VERDICTS)}")

    # Followup-line fields
    parser.add_argument("--post-confidence", default=None,
                        help=f"one of {sorted(CONFIDENCES)} (followup mode)")
    parser.add_argument("--decision-taken", default=None,
                        help="what caller did with the verdict (followup mode)")
    parser.add_argument("--human-needed-after", default=None,
                        help="boolean (followup mode)")
    parser.add_argument("--verdict-resolved", default=None,
                        help="boolean (followup mode)")

    parser.add_argument("--no-commit", action="store_true",
                        help="skip auto-commit step regardless of caller_class "
                             "(useful for tests)")

    args = parser.parse_args(argv)

    jsonl_path = args.jsonl or (state_dir() / JSONL_FILENAME)
    # Lock co-locates with JSONL so test paths and overrides keep the
    # lock alongside the data they protect.
    lock_path = jsonl_path.parent / LOCK_FILENAME

    if args.kind == "run":
        entry = build_run_entry(args)
        commit_class = entry["caller_class"]
        commit_message = f"check-decision: telemetry {args.run_id}"
    else:
        entry = build_followup_entry(args, jsonl_path)
        commit_class = _lookup_run_caller_class(jsonl_path, args.run_id)
        commit_message = f"check-decision: followup {args.run_id}"

    with acquire_lock(lock_path):
        append_line(jsonl_path, entry)
        if (not args.no_commit) and commit_class == "judgmental":
            repo_root = repo_root_from_jsonl(jsonl_path)
            auto_commit(repo_root, jsonl_path, commit_message)

    print(
        f"telemetry: appended {entry['kind']} run_id={args.run_id} "
        f"caller_class={commit_class} "
        f"commit={'yes' if commit_class == 'judgmental' and not args.no_commit else 'skip'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
