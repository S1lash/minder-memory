"""Orchestrator for the /minder:mem:process metric-day branch.

Pure deterministic Python (no LLM). One source file → one per-day record
under `_records/<family>/<source_id>/<date>.md` plus updated rolling
baselines + streak state, namespaced per source. The source's
`MetricDayProfile` (see `metric_day_profiles`) supplies the family
directory, record kind/domains, metric vocabulary and thresholds — the
orchestrator itself is profile-agnostic, serving biometric wearables
(garmin/oura) and behavioural feeds (activitywatch) through one path.

Reads `_sources/inbox/{source}/<date>.md`, emits records, moves the
source to `_sources/processed/{source}/`, appends to manifest.

API:
  run(source_path, *, base_dir, source_id="garmin", thresholds=None,
      now=None, manifest=None, dry_run=False) -> ProcessResult

  run_batch(source_paths, *, base_dir, source_id="garmin",
            thresholds=None, now=None) -> list[ProcessResult]

CLI:
  python3 process_metric_day.py <source_path> [--source-id garmin]
                                [--base-dir .] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from _common import configure_std_streams  # type: ignore
from typing import Any, Iterable, Optional

import yaml

import biometric_baselines as baselines_mod
from emit_batch_manifest import PROCESSOR_NAMESPACE
from biometric_baselines import Deviation, flag_deviations
from biometric_streaks import advance as streaks_advance, StreakEvent
import metric_day_profiles as profiles
from metric_day_profiles import MetricDayProfile


@dataclass
class ProcessResult:
    source_path: str
    outcome: str            # 'emitted' | 'skipped-failure-stub' | 'skipped-no-data' |
                            # 'rerender-auto-absorbed' | 'rerender-kept-existing' |
                            # 'no-op-already-processed' | 'no-op-same-content'
    record_path: Optional[str] = None
    deviations: list[Deviation] = field(default_factory=list)
    streak_events: list[StreakEvent] = field(default_factory=list)
    categorical_events: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    clarifications: list[dict[str, Any]] = field(default_factory=list)
    manifest_entry: Optional[dict[str, Any]] = None


@dataclass
class _Paths:
    base: Path
    records_dir: Path
    state_dir: Path
    baselines_path: Path
    streaks_path: Path
    inbox_dir: Path
    processed_dir: Path
    log_path: Path
    clarifications_path: Path

    @classmethod
    def for_source(cls, base_dir: str | Path, source_id: str,
                   family_dir: str = "biometric") -> "_Paths":
        b = Path(base_dir)
        # Records + derived state are namespaced per source under a profile
        # family directory (`biometric` / `activity`). A user may run two
        # sources of the same family at once (e.g. garmin + oura); a shared
        # store would collide records on the same date and pool two
        # distributions into one σ-baseline (different sensors / signals read
        # differently → meaningless deviations). Per-source isolation keeps
        # each baseline statistically valid.
        records_dir = b / "_records" / family_dir / source_id
        state_dir = b / "_system" / "state" / family_dir / source_id
        return cls(
            base=b,
            records_dir=records_dir,
            state_dir=state_dir,
            baselines_path=state_dir / "baselines.json",
            streaks_path=state_dir / "streaks.json",
            inbox_dir=b / "_sources" / "inbox" / source_id,
            processed_dir=b / "_sources" / "processed" / source_id,
            log_path=b / "_system" / "state" / "log_process.md",
            clarifications_path=b / "_system" / "state" / "CLARIFICATIONS.md",
        )


def _load_thresholds(base_dir: Path, basename: str = "biometric_thresholds") -> dict[str, Any]:
    """Load thresholds with template → live → .local layering.

    `basename` selects the profile's threshold family
    (`biometric_thresholds` / `activity_thresholds`).
    """
    scripts = base_dir / "_system" / "scripts"
    template = scripts / f"{basename}.template.yaml"
    live = scripts / f"{basename}.yaml"
    local = scripts / f"{basename}.local.yaml"
    out: dict[str, Any] = {}
    for p in (template, live, local):
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            _deep_merge(out, data)
    return out


def _deep_merge(target: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _is_failure_stub(filename: str, status: str | None) -> bool:
    if filename.startswith("collection-failed-"):
        return True
    if filename.endswith(".resolved.md"):
        return True
    if (status or "").lower() == "collection-failed":
        return True
    return False


def _read_prior_record(records_dir: Path, today: str) -> Optional[dict[str, Any]]:
    """Read the most recent biometric record dated strictly before `today`.

    Returns dict {date, key_numbers, frontmatter} or None if no prior.
    """
    if not records_dir.exists():
        return None
    candidates = sorted(records_dir.glob("*.md"), reverse=True)
    for p in candidates:
        if p.name == "README.md":
            continue
        stem = p.stem
        if stem >= today:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        return _parse_record(text)
    return None


def _parse_record(text: str) -> dict[str, Any]:
    """Parse an emitted biometric record (frontmatter + Key Numbers YAML)."""
    fm: dict[str, Any] = {}
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            fm = yaml.safe_load(text[4:end]) or {}
    # Key Numbers section
    kn: dict[str, Any] = {}
    marker = "\n## Key Numbers\n"
    i = text.find(marker)
    if i >= 0:
        rest = text[i + len(marker):]
        block_end = rest.find("\n## ")
        block = rest if block_end < 0 else rest[:block_end]
        # block is `\n```yaml\n...\n```\n`
        ms = block.find("```yaml\n")
        if ms >= 0:
            ye = block.find("\n```", ms + 8)
            if ye > 0:
                kn = yaml.safe_load(block[ms + 8:ye]) or {}
    return {"frontmatter": fm, "key_numbers": kn}


def _categorical_events(
    today: dict[str, Any],
    prior: Optional[dict[str, Any]],
    pairs: tuple[tuple[str, str], ...],
) -> list[str]:
    """Compare categorical fields against prior record. Return list of
    one-line event strings. `pairs` is the profile's (key, label) set;
    an empty tuple (e.g. the activity profile) yields no events."""
    if not prior or not pairs:
        return []
    prior_kn = prior.get("key_numbers", {}) or {}
    out: list[str] = []
    for key, label in pairs:
        new = today.get(key)
        old = prior_kn.get(key)
        if new and old and new != old:
            out.append(f"{label} changed: {old} → {new}")
    # readiness_drops_to_or_below: MODERATE/LOW
    new_lvl = today.get("readiness_lvl")
    old_lvl = prior_kn.get("readiness_lvl")
    if new_lvl in {"MODERATE", "LOW"} and old_lvl == "HIGH":
        # already covered by generic transition above; no duplicate
        pass
    return out


def _categorical_concepts(events: list[str]) -> list[str]:
    """Derive concept slugs from categorical event lines."""
    out: list[str] = []
    for ev in events:
        low = ev.lower()
        if low.startswith("training status changed"):
            target = ev.split("→")[-1].strip().lower()
            out.append(f"train_status_transition_to_{target}")
        elif low.startswith("hrv status changed"):
            target = ev.split("→")[-1].strip().lower()
            out.append(f"hrv_status_changed_to_{target}")
        elif low.startswith("acwr zone changed"):
            target = ev.split("→")[-1].strip().lower()
            out.append(f"acwr_zone_changed_to_{target}")
        elif low.startswith("readiness changed"):
            target = ev.split("→")[-1].strip().lower()
            out.append(f"readiness_changed_to_{target}")
    return out


def _format_record(
    *, date: str, source_id: str, source_filename: str, summary_text: str,
    metrics: dict[str, Any], deviations: list[Deviation],
    categorical_events: list[str], streaks_state: dict[str, Any],
    streak_events: list[StreakEvent], concepts: list[str],
    metric_failures: list[Any], created_iso: str, profile: MetricDayProfile,
) -> str:
    fm: dict[str, Any] = {
        "date": date,
        "kind": profile.kind,
        "domains": list(profile.domains),
        "people": [],
        "audience_tags": [],
        "is_sensitive": profile.is_sensitive,
        "origin": "personal",
        "device": source_id,
    }
    if profile.device_estimate is not None:
        fm["device_estimate"] = profile.device_estimate
    fm["concepts"] = concepts
    if metric_failures:
        fm["metric_failures"] = metric_failures
    fm["source"] = f"{source_id}/{source_filename}"
    fm["created"] = created_iso

    # Render frontmatter in canonical order.
    fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False)

    parts: list[str] = []
    parts.append(f"---\n{fm_text}---\n")
    parts.append(f"\n# {profile.heading} — {date}\n")

    # Summary verbatim
    summary_clean = summary_text.strip()
    if summary_clean:
        parts.append(f"\n{summary_clean}\n")

    # Key Numbers
    kn: dict[str, Any] = {}
    for key in profile.key_number_order:
        if key in metrics and metrics[key] is not None:
            kn[key] = metrics[key]
    if kn:
        kn_yaml = yaml.safe_dump(kn, sort_keys=False, allow_unicode=True, default_flow_style=False)
        parts.append(f"\n## Key Numbers\n\n```yaml\n{kn_yaml}```\n")

    # Baseline Deviations
    if deviations:
        lines = []
        for d in deviations:
            sign = "−" if d.sigma_distance < 0 else "+"
            lines.append(
                f"- {d.metric} {d.value:g} — {sign}{abs(d.sigma_distance):.1f}σ {d.severity} "
                f"(baseline {d.baseline_mu:.2f} ± {d.baseline_sigma:.2f})"
            )
        parts.append("\n## Baseline Deviations\n\n" + "\n".join(lines) + "\n")

    # Categorical events
    if categorical_events:
        lines = [f"- {e}" for e in categorical_events]
        parts.append("\n## Categorical Events\n\n" + "\n".join(lines) + "\n")

    # Active streaks (only those active as of today)
    active = streaks_state.get("active", {}) or {}
    if active:
        lines = []
        for c in sorted(active.keys()):
            e = active[c]
            lines.append(f"- {c} — day {e['days']} (started {e['started']})")
        parts.append("\n## Active Streaks\n\n" + "\n".join(lines) + "\n")

    # Streak transitions
    if streak_events:
        lines = []
        for ev in streak_events:
            if ev.kind == "state":
                lines.append(f"- {ev.concept} crossed threshold (day {ev.days}, started {ev.started})")
            else:
                lines.append(f"- {ev.concept} (was {ev.days} days, started {ev.started})")
        parts.append("\n## Streak Transitions\n\n" + "\n".join(lines) + "\n")

    # Source link. Record lives at _records/biometric/{source_id}/{date}.md,
    # so three levels up reaches the base.
    parts.append(f"\n## Source\n\n[[../../../_sources/processed/{source_id}/{source_filename}]]\n")

    return "".join(parts)


def _append_log(log_path: Path, line: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run(
    source_path: str | Path,
    *,
    base_dir: str | Path,
    source_id: str = "garmin",
    thresholds: Optional[dict[str, Any]] = None,
    now: Optional[dt.datetime] = None,
    dry_run: bool = False,
) -> ProcessResult:
    """Process one metric-day source file.

    Idempotent on source already in processed/ AND record content
    matching. A re-collected source whose content drifted from the
    existing record is resolved autonomously by richness: richer-or-equal
    data is absorbed (record + baselines recomputed forward); a poorer/
    empty re-collect keeps the existing record. No owner CLARIFICATION —
    metric-day records are deterministic device projections with no owner
    edits to protect (doctrine §3.1 autonomous-resolution).
    """
    src = Path(source_path).resolve()
    profile = profiles.for_source(source_id)
    paths = _Paths.for_source(base_dir, source_id, profile.family_dir)
    thresholds = thresholds or _load_thresholds(paths.base, profile.thresholds_basename)

    now = now or dt.datetime.now(dt.timezone.utc)
    created_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    src_text = src.read_text(encoding="utf-8")
    src_hash = _content_hash(src_text)
    parsed = profile.extractor(src)
    date = parsed["date"] or src.stem
    status = parsed["status"]

    # Pre-check 1: failure stub
    if _is_failure_stub(src.name, status):
        log = f"{created_iso} metric-day skip-failure-stub source={source_id}/{src.name}"
        if not dry_run:
            _append_log(paths.log_path, log)
            _move_to_processed(src, paths.processed_dir)
        return ProcessResult(
            source_path=str(src),
            outcome="skipped-failure-stub",
            log_lines=[log],
        )

    # Pre-check 2: existing record content-hash drift
    record_path = paths.records_dir / f"{date}.md"
    if record_path.exists():
        existing = record_path.read_text(encoding="utf-8")
        # Compare against a hash of the source-derived content rather
        # than the rendered record (rendered text changes across runs
        # via `created` timestamp). Source-level hash is sufficient.
        # Look for `source_hash:` marker in frontmatter; absent on
        # historical records — treat absence as "no drift" (idempotent
        # on first pass).
        prior_hash = None
        if existing.startswith("---\n"):
            end = existing.find("\n---\n", 4)
            if end > 0:
                fm = yaml.safe_load(existing[4:end]) or {}
                prior_hash = fm.get("source_hash")
        if prior_hash and prior_hash != src_hash:
            # A re-collected metric-day source differs from the record we built
            # before. Metric-day records are deterministic projections of device
            # data — there are no owner edits to protect — so the resolution is
            # not the owner's to make: it is a pure function of which version
            # carries more data. RICHER-OR-EQUAL new data is an authoritative
            # refresh (a device→cloud sync gap healed, a provider backfill) and
            # is absorbed automatically; POORER new data (an empty re-collect)
            # must never clobber a good record, so the existing record is kept.
            # This makes a manually-fixed data sync count on the very next
            # process tick with no owner CLARIFICATION — qualifying for the
            # doctrine §3.1 autonomous-resolution exception: deterministic
            # (richness is a pure count), conservative-safe (either a richer
            # refresh or a no-loss keep — good data is never overwritten by
            # poorer), and low per-decision value (the owner cannot meaningfully
            # choose against counting their own recovered data).
            new_richness = len(parsed["metrics"])
            existing_kn = _parse_record(existing).get("key_numbers") or {}
            existing_richness = sum(1 for v in existing_kn.values() if v is not None)
            if new_richness == 0 or new_richness < existing_richness:
                # Poorer/empty re-collect — keep the existing record; only move
                # the source to processed so the inbox stays clean.
                log = (
                    f"{created_iso} metric-day rerender-kept-existing "
                    f"source={source_id}/{src.name} "
                    f"new_richness={new_richness} existing_richness={existing_richness} "
                    f"prior_hash={prior_hash[:8]} new_hash={src_hash[:8]}"
                )
                if not dry_run:
                    _append_log(paths.log_path, log)
                    _move_to_processed(src, paths.processed_dir)
                return ProcessResult(
                    source_path=str(src),
                    outcome="rerender-kept-existing",
                    record_path=str(record_path),
                    log_lines=[log],
                )
            # Richer-or-equal (and non-empty): absorb automatically. Move the
            # healed source into processed, then recompute baselines/streaks +
            # re-emit records from this date forward off the healed source
            # (recompute deletes each record before replay, so no drift recursion).
            log = (
                f"{created_iso} metric-day rerender-auto-absorbed "
                f"source={source_id}/{src.name} "
                f"new_richness={new_richness} existing_richness={existing_richness} "
                f"prior_hash={prior_hash[:8]} new_hash={src_hash[:8]}"
            )
            absorbed_entry: Optional[dict[str, Any]] = None
            if not dry_run:
                _append_log(paths.log_path, log)
                _move_to_processed(src, paths.processed_dir)
                summary = recompute_baselines_forward(
                    paths.base, from_date=date, source_id=source_id
                )
                # Lift this day's rebuilt record into the batch manifest as an
                # UPDATE (ENGINE_DOCTRINE §3.8) — the replay of later days is
                # ignored here; each drifted day carries its own entry.
                for r in summary.get("results", []):
                    if r.manifest_entry and r.manifest_entry.get("id") == date:
                        absorbed_entry = r.manifest_entry
                        break
            return ProcessResult(
                source_path=str(src),
                outcome="rerender-auto-absorbed",
                record_path=str(record_path),
                log_lines=[log],
                manifest_entry=absorbed_entry,
            )
        elif prior_hash == src_hash:
            log = f"{created_iso} metric-day no-op-same-content source={source_id}/{src.name}"
            if not dry_run:
                _append_log(paths.log_path, log)
                _move_to_processed(src, paths.processed_dir)
            return ProcessResult(
                source_path=str(src),
                outcome="no-op-same-content",
                record_path=str(record_path),
                log_lines=[log],
            )

    # 3: Cold-start informational CLARIFICATION on first run
    cold_start_clarification: Optional[dict[str, Any]] = None
    if not paths.baselines_path.exists():
        cold_start_clarification = {
            "type": f"{profile.name}-baseline-cold-start",
            "subject": f"{profile.family_dir}/baselines",
            "context": (
                "First metric-day file processed; no prior baselines.json. "
                "Initialised empty baselines. One-time, expected. "
                "Resolution: dismiss as resolved with note 'expected cold-start'."
            ),
        }

    # 4: Update baselines + flag deviations. Skip the baseline contribution
    # for days the profile deems non-representative (e.g. a near-idle Mac day
    # would pull every behavioural baseline toward zero), but still emit the
    # record — the empty day is itself signal.
    if profile.should_baseline(parsed["metrics"]):
        baselines_state = baselines_mod.update(
            paths.baselines_path, date, parsed["metrics"], thresholds,
            numeric_metrics=profile.numeric_metrics,
        )
    else:
        baselines_state = baselines_mod.load(paths.baselines_path)
    deviations = flag_deviations(baselines_state, parsed["metrics"], thresholds)

    # 5: Categorical events vs prior record
    prior = _read_prior_record(paths.records_dir, date)
    categorical_events = _categorical_events(parsed["metrics"], prior, profile.categorical_pairs)
    categorical_concepts = _categorical_concepts(categorical_events)

    # 6: Streak advancement
    streak_rule = thresholds.get("streak_rule", {}) or {}
    streaks_state, streak_events = streaks_advance(
        paths.streaks_path,
        date,
        deviations,
        min_consecutive=int(streak_rule.get("min_consecutive_days", 3)),
        min_severity=streak_rule.get("min_severity", "medium"),
        concept_map=profile.concept_map,
    )

    # 7: Concept synthesis
    concepts: list[str] = []
    for c in sorted(streaks_state.get("active", {}).keys()):
        if streaks_state["active"][c].get("emitted_state_concept"):
            concepts.append(c)
    for ev in streak_events:
        if ev.kind == "recovery":
            concepts.append(ev.concept)
    for cc in categorical_concepts:
        if cc not in concepts:
            concepts.append(cc)

    # 8: Format + write record
    rendered = _format_record(
        date=date,
        source_id=source_id,
        source_filename=src.name,
        summary_text=parsed["summary_text"],
        metrics=parsed["metrics"],
        deviations=deviations,
        categorical_events=categorical_events,
        streaks_state=streaks_state,
        streak_events=streak_events,
        concepts=concepts,
        metric_failures=parsed["metric_failures"],
        created_iso=created_iso,
        profile=profile,
    )

    # Inject `source_hash:` into frontmatter for idempotency on re-run.
    rendered = _inject_frontmatter_field(rendered, "source_hash", src_hash)

    if not dry_run:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(rendered, encoding="utf-8")
        _move_to_processed(src, paths.processed_dir)

    log_parts = [
        f"{created_iso} metric-day emit source={source_id}/{src.name}",
        f"date={date}",
        f"deviations={len(deviations)}",
        f"streak_events={len(streak_events)}",
        f"concepts={','.join(concepts) if concepts else '-'}",
    ]
    log_line = " ".join(log_parts)
    if not dry_run:
        _append_log(paths.log_path, log_line)
        if cold_start_clarification:
            _append_clarification(paths.clarifications_path, cold_start_clarification)

    clarifications: list[dict[str, Any]] = []
    if cold_start_clarification:
        clarifications.append(cold_start_clarification)

    record_text = record_path.read_text(encoding="utf-8") if record_path.exists() else rendered
    record_checksum = hashlib.sha256(record_text.encode("utf-8")).hexdigest()
    manifest_entry = {
        "path": str(record_path.relative_to(paths.base)),
        "id": date,
        "title": f"{profile.heading} — {date}",
        "checksum_sha256": record_checksum,
        "people": [],
        "projects": [],
        "concept_hints": concepts,
        "primary_type": profile.manifest_primary_type,
        "origin": "personal",
        "audience_tags": [],
        "is_sensitive": profile.is_sensitive,
        # Minder Memory-specific extras (allowed via section_extras pattern)
        "section_extras": {
            "date": date,
            "source_hash": src_hash,
            "domains": list(profile.domains),
            "deviations": len(deviations),
            "categorical_events": list(categorical_events),
            "streak_events": [
                {"kind": e.kind, "concept": e.concept} for e in streak_events
            ],
        },
    }

    return ProcessResult(
        source_path=str(src),
        outcome="emitted",
        record_path=str(record_path),
        deviations=deviations,
        streak_events=streak_events,
        categorical_events=categorical_events,
        concepts=concepts,
        log_lines=[log_line],
        clarifications=clarifications,
        manifest_entry=manifest_entry,
    )


def _inject_frontmatter_field(rendered: str, key: str, value: str) -> str:
    """Insert a `key: value` line into the frontmatter just before the
    closing `---`."""
    if not rendered.startswith("---\n"):
        return rendered
    end = rendered.find("\n---\n", 4)
    if end < 0:
        return rendered
    fm = rendered[4:end]
    rest = rendered[end:]
    if f"\n{key}:" in fm or fm.startswith(f"{key}:"):
        return rendered
    new_fm = fm.rstrip() + f"\n{key}: {value}\n"
    return f"---\n{new_fm}---{rest[len(chr(10)+'---'):]}"


def _move_to_processed(src: Path, processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    target = processed_dir / src.name
    shutil.move(str(src), str(target))
    # Move the sibling raw payload alongside, whatever its extension —
    # garmin/oura ship `raw/<date>.json`, activitywatch `raw/<date>.json.gz`.
    raw_dir = src.parent / "raw"
    if raw_dir.is_dir():
        for raw_src in sorted(raw_dir.glob(f"{src.stem}.json*")):
            raw_target_dir = processed_dir / "raw"
            raw_target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(raw_src), str(raw_target_dir / raw_src.name))


def _append_clarification(path: Path, clar: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "# CLARIFICATIONS\n\n## Open Items\n\n## Resolved Items\n",
            encoding="utf-8",
        )
    text = path.read_text(encoding="utf-8")
    open_marker = "\n## Open Items\n"
    idx = text.find(open_marker)
    if idx < 0:
        # append the section
        text = text + open_marker + "\n"
        idx = text.find(open_marker)
    insert_at = idx + len(open_marker)
    body = (
        f"\n### {clar['type']}: {clar['subject']}\n"
        f"**Type:** {clar['type']}\n"
        f"**Subject:** {clar['subject']}\n"
        f"**Context:** {clar['context']}\n"
    )
    if clar.get("default"):
        body += f"**Suggested action:** {clar['default']}\n"
    text = text[:insert_at] + body + text[insert_at:]
    path.write_text(text, encoding="utf-8")


def run_batch(
    source_paths: Iterable[str | Path],
    *,
    base_dir: str | Path,
    source_id: str = "garmin",
    thresholds: Optional[dict[str, Any]] = None,
    now: Optional[dt.datetime] = None,
    dry_run: bool = False,
    batch_id: Optional[str] = None,
    manifest_out: Optional[str | Path] = None,
) -> list[ProcessResult]:
    """Process a chronologically-sorted batch of metric-day sources.

    Order matters: baselines and streaks are stateful — files MUST be
    processed in date order. Caller is responsible for sorting.

    When `batch_id` (and optionally `manifest_out`) is provided, emits
    a v2-conformant batch manifest containing the records.created
    section with biometric entries. Default `manifest_out`:
    `_system/state/batches/{batch_id}.json`.
    """
    profile = profiles.for_source(source_id)
    paths = _Paths.for_source(base_dir, source_id, profile.family_dir)
    thresholds = thresholds or _load_thresholds(paths.base, profile.thresholds_basename)
    results = []
    sorted_paths = sorted([Path(p) for p in source_paths], key=lambda p: p.name)
    for sp in sorted_paths:
        results.append(run(
            sp,
            base_dir=base_dir,
            source_id=source_id,
            thresholds=thresholds,
            now=now,
            dry_run=dry_run,
        ))

    if batch_id and not dry_run:
        out_path = Path(manifest_out) if manifest_out else (
            paths.base / "_system" / "state" / "batches" / f"{batch_id}.json"
        )
        write_batch_manifest(results, batch_id, out_path, source_id=source_id, now=now)

    return results


def write_batch_manifest(
    results: list[ProcessResult],
    batch_id: str,
    output_path: str | Path,
    *,
    source_id: str = "garmin",
    now: Optional[dt.datetime] = None,
) -> Path:
    """Emit (or merge into) a v2-conformant batch manifest with biometric
    records under `records.created`.

    If `output_path` already exists (mixed batch — transcripts already
    wrote it), merge the biometric entries into the existing
    `records.created` array. Otherwise write a complete fresh manifest.
    Privacy trio + checksum + section_extras as defined by
    `manifest-schema/v2.json`.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    profile = profiles.for_source(source_id)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # A fresh emit is a `created` record; an auto-absorbed re-render heals a
    # record that already existed → `updated` (ENGINE_DOCTRINE §3.8). Both
    # outcomes moved a source to processed, so both count as processed sources.
    created_entries = [
        r.manifest_entry for r in results
        if r.manifest_entry and r.outcome == "emitted"
    ]
    updated_entries = [
        r.manifest_entry for r in results
        if r.manifest_entry and r.outcome == "rerender-auto-absorbed"
    ]
    sources_processed_entries = [
        {
            "path": f"_sources/processed/{source_id}/{Path(r.source_path).name}",
            "source_type": source_id,
            "source_id": Path(r.source_path).stem,
        }
        for r in results
        if r.outcome in {
            "emitted", "skipped-failure-stub", "no-op-same-content",
            "rerender-auto-absorbed", "rerender-kept-existing",
        }
    ]

    if output_path.exists():
        manifest = json.loads(output_path.read_text(encoding="utf-8"))
        manifest.setdefault("records", {"created": [], "updated": []})
        manifest["records"].setdefault("created", []).extend(created_entries)
        manifest["records"].setdefault("updated", []).extend(updated_entries)
        manifest.setdefault("sources_processed", []).extend(sources_processed_entries)
    else:
        manifest = {
            "batch_id": batch_id,
            "timestamp": timestamp,
            "format_version": "2.0",
            "processor": PROCESSOR_NAMESPACE + "process",
            "sources_processed": sources_processed_entries,
            "records": {"created": created_entries, "updated": updated_entries},
            "knowledge_notes": {"created": [], "updated": []},
            "hubs": {"created": [], "updated": []},
            "concepts": {"upserts": []},
            "constitution": {"principles": {"created": [], "updated": []}},
            "tier1_objects": {},
            "tier2_objects": {},
            "sensitive_entities": [],
            "threads_opened": [],
            "threads_resolved": [],
            "stats": {
                "files_processed": len(results),
                f"{profile.name}_records_emitted": len(created_entries) + len(updated_entries),
            },
            "section_extras": {
                f"{profile.name}_pipeline": {
                    "source_id": source_id,
                    "outcomes": _outcome_counts(results),
                },
            },
        }

    output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def append_update_to_record(
    base_dir: str | Path,
    *,
    date: str,
    source_id: str = "garmin",
    today: Optional[dt.datetime] = None,
) -> Path:
    """Append a `## Update {today}` section to an existing biometric record.

    Used by `metric_record_rerender_apply(choice='append-update')`. Reads
    the current source from `_sources/processed/<source>/<date>.md`
    (already moved by run()), re-extracts metrics, computes diff against
    the existing Key Numbers + new baseline deviations against the
    current baselines snapshot.
    """
    profile = profiles.for_source(source_id)
    paths = _Paths.for_source(base_dir, source_id, profile.family_dir)
    record_path = paths.records_dir / f"{date}.md"
    src_path = paths.processed_dir / f"{date}.md"
    if not record_path.exists() or not src_path.exists():
        raise FileNotFoundError(f"record or source missing for {date}")

    today = today or dt.datetime.now(dt.timezone.utc)
    today_iso = today.strftime("%Y-%m-%d")

    # Re-parse current source
    parsed = profile.extractor(src_path)
    new_metrics = parsed["metrics"]

    # Read existing record's Key Numbers
    existing_text = record_path.read_text(encoding="utf-8")
    existing_record = _parse_record(existing_text)
    old_metrics = existing_record.get("key_numbers", {}) or {}

    # Compute diff
    diff_lines: list[str] = []
    keys = sorted(set(old_metrics) | set(new_metrics))
    for k in keys:
        old_v = old_metrics.get(k)
        new_v = new_metrics.get(k)
        if old_v != new_v:
            diff_lines.append(f"- {k}: {old_v!r} → {new_v!r}")

    # Recompute deviations against current baselines
    thresholds = _load_thresholds(paths.base, profile.thresholds_basename)
    baselines_state = baselines_mod.load(paths.baselines_path)
    new_devs = flag_deviations(baselines_state, new_metrics, thresholds)

    update_block = [f"\n## Update {today_iso}\n"]
    if diff_lines:
        update_block.append("\n### Key Numbers diff\n\n" + "\n".join(diff_lines) + "\n")
    else:
        update_block.append("\n### Key Numbers diff\n\n_(no field-level changes)_\n")
    if new_devs:
        update_block.append("\n### Deviations re-computed against current baselines\n\n")
        for d in new_devs:
            sign = "−" if d.sigma_distance < 0 else "+"
            update_block.append(
                f"- {d.metric} {d.value:g} — {sign}{abs(d.sigma_distance):.1f}σ {d.severity} "
                f"(baseline {d.baseline_mu:.2f} ± {d.baseline_sigma:.2f})\n"
            )

    record_path.write_text(existing_text.rstrip() + "\n" + "".join(update_block), encoding="utf-8")
    return record_path


def recompute_baselines_forward(
    base_dir: str | Path,
    *,
    from_date: str,
    source_id: str = "garmin",
) -> dict[str, Any]:
    """Replay biometric records from `from_date` forward.

    Steps:
      1. Truncate `baselines.json` and `streaks.json` of all entries
         with date >= from_date (for baselines: drop values; for
         streaks: trim active/history bound by date).
      2. Truncate `last_weekly_run.txt` so /minder:mem:maintain re-enters
         backfill mode for affected weeks.
      3. Re-process every existing biometric record from `from_date`
         forward, in date order, re-running baseline.update +
         flag_deviations + streaks.advance, then re-emitting the
         record body (frontmatter `source_hash` preserved).

    Returns a summary dict with counts.
    """
    profile = profiles.for_source(source_id)
    paths = _Paths.for_source(base_dir, source_id, profile.family_dir)
    # 1) Truncate baselines per-metric
    baselines_state = baselines_mod.load(paths.baselines_path)
    truncated_metrics = 0
    for metric, m in (baselines_state.get("metrics") or {}).items():
        kept = [v for v in m.get("values", []) if v.get("date") < from_date]
        if len(kept) != len(m.get("values", [])):
            truncated_metrics += 1
        m["values"] = kept
        # recompute μ/σ
        nums = [v["value"] for v in kept]
        n = len(nums)
        if n >= 2:
            import statistics
            m["mu"] = statistics.fmean(nums)
            m["sigma"] = statistics.pstdev(nums)
            m["n"] = n
        elif n == 1:
            m["mu"] = nums[0]
            m["sigma"] = None
            m["n"] = 1
        else:
            m["mu"] = None
            m["sigma"] = None
            m["n"] = 0
    # write truncated state
    baselines_mod._atomic_write(paths.baselines_path, baselines_state)

    # 2) Truncate streaks
    streaks_state = json.loads(paths.streaks_path.read_text(encoding="utf-8")) if paths.streaks_path.exists() else {}
    streaks_state["active"] = {
        c: e for c, e in (streaks_state.get("active") or {}).items()
        if (e.get("started") or "9999-99-99") < from_date
    }
    streaks_state["history"] = [
        h for h in (streaks_state.get("history") or [])
        if (h.get("ended") or "9999-99-99") < from_date
    ]
    streaks_state["last_date"] = from_date_minus_one(from_date)
    paths.streaks_path.write_text(
        json.dumps(streaks_state, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 3) Truncate weekly idempotency gate
    lwr = paths.state_dir / "last_weekly_run.txt"
    if lwr.exists():
        lwr.unlink()

    # 4) Re-process existing records from from_date forward by replaying the
    #    upstream processed source files through run(). Each source is staged in
    #    an ISOLATED temp dir — never the live inbox. This replay can run from
    #    inside run()'s auto-absorb branch while a batch still has other days
    #    pending in the inbox; routing it through the shared inbox would
    #    overwrite those pending files (silent data loss) and then crash the
    #    batch with FileNotFoundError. run() consumes the staged source and
    #    moves it (+ its raw sibling, which `_move_to_processed` finds under
    #    `<src.parent>/raw`) back to processed.
    records_replayed = 0
    replay_results: list[ProcessResult] = []
    sources_dir = paths.processed_dir
    staging = Path(tempfile.mkdtemp(prefix=f"minder-memory-recompute-{source_id}-"))
    try:
        for src in sorted(sources_dir.glob("*.md")):
            if src.stem < from_date:
                continue
            staged = staging / src.name
            shutil.move(str(src), str(staged))
            raw_dir = sources_dir / "raw"
            if raw_dir.is_dir():
                for raw_src in sorted(raw_dir.glob(f"{src.stem}.json*")):
                    (staging / "raw").mkdir(parents=True, exist_ok=True)
                    shutil.move(str(raw_src), str(staging / "raw" / raw_src.name))
            # Delete existing record so run() does not detect content drift.
            rec = paths.records_dir / f"{src.stem}.md"
            if rec.exists():
                rec.unlink()
            replay_results.append(run(staged, base_dir=base_dir, source_id=source_id))
            records_replayed += 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        "from_date": from_date,
        "metrics_truncated": truncated_metrics,
        "records_replayed": records_replayed,
        # Per-day ProcessResults of the replay — the auto-absorb caller lifts the
        # manifest_entry for the day it is absorbing so the heal reaches the
        # batch manifest (ENGINE_DOCTRINE §3.8). Other callers ignore this key.
        "results": replay_results,
    }


def from_date_minus_one(date: str) -> str:
    d = dt.date.fromisoformat(date) - dt.timedelta(days=1)
    return d.isoformat()


def _outcome_counts(results: list[ProcessResult]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results:
        out[r.outcome] = out.get(r.outcome, 0) + 1
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", nargs="+", help="One or more source paths.")
    p.add_argument("--source-id", default="garmin")
    p.add_argument("--base-dir", default=".")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--batch-id", default=None,
                   help="If set, emit a v2 batch manifest at "
                        "_system/state/batches/{batch_id}.json (or "
                        "--manifest-out path).")
    p.add_argument("--manifest-out", default=None)
    args = p.parse_args(argv)
    results = run_batch(
        args.source,
        base_dir=args.base_dir,
        source_id=args.source_id,
        dry_run=args.dry_run,
        batch_id=args.batch_id,
        manifest_out=args.manifest_out,
    )
    for r in results:
        print(json.dumps({
            "source": Path(r.source_path).name,
            "outcome": r.outcome,
            "deviations": [
                {"metric": d.metric, "severity": d.severity,
                 "direction": d.direction, "sigma": round(d.sigma_distance, 2)}
                for d in r.deviations
            ],
            "concepts": r.concepts,
            "categorical_events": r.categorical_events,
        }, ensure_ascii=False))
    return 0


configure_std_streams()


if __name__ == "__main__":
    raise SystemExit(_main())
