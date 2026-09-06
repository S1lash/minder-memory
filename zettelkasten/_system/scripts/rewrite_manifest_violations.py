#!/usr/bin/env python3
"""One-shot retrofit utility — re-run historical manifests through the
fixed emit normaliser.

When the producer normaliser gains new coercions (e.g. bare-string
`sources_processed[]` → structured `source_entry`, non-empty
`tier1_objects.people: [...]` → `{upserts: [...]}`, privacy-trio
defaults on entity-list entries), historical manifests written before
the fix carry the broken shape. `/minder:mem:lint` Scan G surfaces them as
`manifest-schema-violation` CLARIFICATIONs; this utility fixes them in
place.

Idempotency: re-running over an already-fixed manifest yields the same
output (no events). Atomic write via tempfile + os.replace, matching
emit_batch_manifest's contract.

Usage:
    # Dry-run (default) — print per-batch diff summary, no writes.
    python3 rewrite_manifest_violations.py --batches-dir _system/state/batches

    # Apply — write back. NEVER bypass --apply; default is safe.
    python3 rewrite_manifest_violations.py --batches-dir _system/state/batches --apply

    # Single file mode for testing.
    python3 rewrite_manifest_violations.py --file path/to/batch.json --apply

Exit codes:
- 0 — all batches processed (with or without changes)
- 2 — invalid input (path missing, JSON parse failure on >0 files)
- 3 — at least one batch failed structural validation post-retrofit
      (the utility surfaces; never auto-repairs structural faults)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

import emit_batch_manifest as e  # type: ignore
import lint_manifest_schema as ls  # type: ignore
from _common import (  # type: ignore
    ALLOWED_DOMAINS,
    AUDIENCE_CANONICAL,
    parse_extensions_table,
    repo_root,
    configure_std_streams,
)


def _load_accept_sets(
    audiences_path: Path | None, domains_path: Path | None,
) -> tuple[set[str], set[str]]:
    audiences_path = audiences_path or (
        repo_root() / "_system" / "registries" / "AUDIENCES.md"
    )
    audience_extensions = e.parse_audience_extensions(audiences_path)
    audience_accept = set(AUDIENCE_CANONICAL) | audience_extensions

    domains_path = domains_path or (
        repo_root() / "_system" / "registries" / "DOMAINS.md"
    )
    domain_extensions = parse_extensions_table(
        domains_path, canonical_blacklist=ALLOWED_DOMAINS,
    )
    domain_accept = set(ALLOWED_DOMAINS) | domain_extensions
    return audience_accept, domain_accept


# The `YYYYMMDD-HHMMSS` prefix of a manifest FILENAME, used to rebuild a
# truncated `timestamp`. Not a batch_id authority — `_conform_batch_id` in the
# emitter owns that rule, and this module delegates to it.
_FILENAME_TS_RE = re.compile(r"^(\d{8})-(\d{6})")

_SCHEMAS_CACHE: dict | None = None


def schema_errors(data: dict, schemas_dir: Path | None = None) -> list[str]:
    """JSON-Schema errors for one manifest, as readable strings.

    The SAME validator `/minder:mem:lint` Scan H runs, so "this manifest needs repair"
    and "Scan H will complain about this manifest" are the same question. Any
    other check here would let the two drift.

    An unreadable schema set or an unknown `format_version` yields no errors:
    this is a repair tool, and refusing to repair is safer than repairing on a
    guess.
    """
    global _SCHEMAS_CACHE
    if _SCHEMAS_CACHE is None:
        directory = schemas_dir or (repo_root() / "_system" / "docs" / "manifest-schema")
        try:
            _SCHEMAS_CACHE = ls.load_schemas(directory)
        except Exception:  # noqa: BLE001 — repair must never crash on schema plumbing
            _SCHEMAS_CACHE = {}
    major = ls.parse_format_major(data.get("format_version"))
    entry = _SCHEMAS_CACHE.get(major) if major is not None else None
    if entry is None:
        return []
    try:
        validator = ls.Draft202012Validator(entry[1])
        return [f"{'/'.join(map(str, err.absolute_path))}: {err.message}"[:300]
                for err in list(validator.iter_errors(data))[:50]]
    except Exception:  # noqa: BLE001
        return []

# Record kind → the folder its notes live in. Used only to reconstruct a `path`
# a historical manifest omitted, and only when the reconstructed file actually
# exists on disk.
# Tier-2 sections whose entries do NOT use the generic typed-object shape.
# Mirrors `$defs.tier2_objects_section.properties` in the manifest schema.
_TIER2_SPECIAL_SECTIONS = frozenset({"section_extras", "lens_observation"})

_RECORD_KIND_DIRS = {
    "meeting": "_records/meetings",
    "observation": "_records/observations",
}


_NOTE_INDEX_CACHE: dict[str, list[str]] | None = None

# Where a note can live. `_sources/` is excluded: a transcript sharing a stem
# with a note must never be offered as that note's path.
_NOTE_SEARCH_ROOTS = (
    "_records", "1_projects", "2_areas", "3_resources", "4_archive",
    "5_meta", "6_posts", "_system",
)


def _note_index(base: Path | None) -> dict[str, list[str]]:
    """`stem -> [repo-relative paths]` for every note under the base.

    Built once. Used to reconstruct a `path` that a historical manifest omitted
    — and only when the stem resolves to EXACTLY one file, because two
    candidates mean the manifest would be made to point at a guess.
    """
    global _NOTE_INDEX_CACHE
    if _NOTE_INDEX_CACHE is not None:
        return _NOTE_INDEX_CACHE
    index: dict[str, list[str]] = {}
    if base is not None:
        for root in _NOTE_SEARCH_ROOTS:
            root_dir = base / root
            if not root_dir.is_dir():
                continue
            for f in root_dir.rglob("*.md"):
                index.setdefault(f.stem, []).append(f.relative_to(base).as_posix())
    _NOTE_INDEX_CACHE = index
    return index


def _locate_note(base: Path | None, note_id: str) -> str | None:
    """The one file whose stem is `note_id`, or None when it is not unambiguous."""
    matches = _note_index(base).get(note_id) or []
    return matches[0] if len(matches) == 1 else None


def _note_title(base: Path | None, rel_path: str) -> str | None:
    """First `# ` heading of the note at `rel_path`, or None."""
    if base is None:
        return None
    try:
        for line in (base / rel_path).read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        return None
    return None


def _sha256(base: Path | None, rel_path: str) -> str | None:
    if base is None:
        return None
    import hashlib

    try:
        return hashlib.sha256((base / rel_path).read_bytes()).hexdigest()
    except OSError:
        return None


def repair_historical(
    data: dict, *, filename: str, base: Path | None,
) -> list[dict]:
    """Repair corruption classes that predate producer conformance.

    Each repair below is deterministic and derives its value from something
    already in the manifest or on disk. Nothing is invented: a value that cannot
    be derived is left alone for the caller to quarantine, because a fabricated
    checksum is worse than an honestly-invalid manifest.

    Originals are preserved under `section_extras.legacy_*`, matching what the
    existing normaliser does, so no information is destroyed by the repair.
    """
    events: list[dict] = []
    stem = Path(filename).stem

    def note(kind: str, detail: str) -> None:
        events.append({"event": kind, "detail": detail})

    def legacy(container: dict, key: str, value) -> None:
        extras = container.setdefault("section_extras", {})
        if isinstance(extras, dict):
            extras.setdefault(f"legacy_{key}", value)

    # --- root: section_extras written as null instead of an object ----------
    if data.get("section_extras", {}) is None:
        data["section_extras"] = {}
        note("section_extras_null", "root section_extras null → {}")

    # --- root: timestamp truncated mid-value ("2026-07-20T23") -------------
    ts = data.get("timestamp")
    m = _FILENAME_TS_RE.match(stem)
    if isinstance(ts, str) and not ts.endswith("Z") and m:
        d, t = m.group(1), m.group(2)
        rebuilt = f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}Z"
        legacy(data, "timestamp", ts)
        data["timestamp"] = rebuilt
        note("timestamp_truncated", f"{ts!r} → {rebuilt}")

    # --- root: a batch_id that is not `YYYYMMDD-HHMMSS(-N)` ----------------
    #
    # Delegated to the emitter's `_conform_batch_id`, which OWNS that rule —
    # it strips a skill suffix, normalises a `-batchN` form, recovers the time
    # from the manifest's own `timestamp`, and zero-fills only as a last
    # resort. A second implementation here would be a second answer to the
    # same question, and the two would drift.
    bid = data.get("batch_id")
    conformed = e._conform_batch_id(bid, stem, data.get("timestamp"))
    if conformed is not None and conformed != bid:
        if isinstance(bid, str):
            legacy(data, "batch_id", bid)
        data["batch_id"] = conformed
        note("batch_id_conformed", f"{bid!r} → {conformed}")

    # --- records / knowledge_notes created[]: missing path, null id/title ---
    for section_name in ("records", "knowledge_notes"):
        created = (data.get(section_name) or {}).get("created")
        if not isinstance(created, list):
            continue
        for entry in created:
            if not isinstance(entry, dict):
                continue
            rel = entry.get("path")

            if not rel and isinstance(entry.get("id"), str):
                # Prefer the record kind's canonical folder; fall back to a
                # base-wide stem lookup, which is what knowledge notes need
                # (they live wherever PARA routed them). Both accept only a
                # file that is really there and unambiguous — a guessed path
                # would make the manifest lie about which file it describes.
                candidate = None
                folder = _RECORD_KIND_DIRS.get(entry.get("kind") or entry.get("primary_type"))
                if folder and base is not None and (base / f"{folder}/{entry['id']}.md").is_file():
                    candidate = f"{folder}/{entry['id']}.md"
                else:
                    candidate = _locate_note(base, entry["id"])
                if candidate:
                    entry["path"] = rel = candidate
                    note("path_synthesised", candidate)

            # PRESENT-and-null only. An absent `title` is an early dialect the
            # schema accepts; inventing one there would be adding data, not
            # repairing corruption.
            if entry.get("id", "") is None and isinstance(rel, str):
                entry["id"] = Path(rel).stem
                note("id_from_path", entry["id"])

            if entry.get("title", "") is None and isinstance(rel, str):
                entry["title"] = _note_title(base, rel) or Path(rel).stem
                note("title_from_note", entry["title"])

            # A checksum truncated below 64 hex chars is unusable. Recompute it
            # from the file when the file is still there; otherwise leave it and
            # let the caller quarantine — never pad or invent a digest.
            digest = entry.get("checksum_sha256")
            if isinstance(digest, str) and len(digest) != 64 and isinstance(rel, str):
                fresh = _sha256(base, rel)
                if fresh:
                    legacy(entry, "checksum_sha256", digest)
                    entry["checksum_sha256"] = fresh
                    note("checksum_recomputed", rel)

            # `org: null` on a person-shaped entry: absent is the schema's way
            # of saying unknown; explicit null is not.
            if "org" in entry and entry["org"] is None:
                del entry["org"]
                note("null_org_dropped", str(entry.get("id")))

    # --- tier2_objects.{type}.upserts[]: missing id / type / name ----------
    #
    # Only the generic `{upserts:[typed_object_entry]}` sections, which are the
    # ones the schema requires id/type/name on. `lens_observation` has its own
    # entry shape with neither `type` nor `name`, so stamping them there would
    # invent fields the schema never asked for.
    tier2 = data.get("tier2_objects")
    if isinstance(tier2, dict):
        for type_name, section in tier2.items():
            if type_name in _TIER2_SPECIAL_SECTIONS or not isinstance(section, dict):
                continue
            for entry in section.get("upserts") or []:
                if not isinstance(entry, dict):
                    continue
                rel = entry.get("path")
                if not entry.get("type"):
                    entry["type"] = type_name
                    note("tier2_type_from_section", type_name)
                if not entry.get("id") and isinstance(rel, str):
                    entry["id"] = Path(rel).stem
                    note("tier2_id_from_path", entry["id"])
                if not entry.get("name") and isinstance(rel, str):
                    entry["name"] = Path(rel).stem
                    note("tier2_name_from_path", entry["name"])

    return events


def quarantine(data: dict, *, reason: str, errors: list[str], ts: str) -> None:
    """Mark a manifest that no deterministic repair can make valid.

    The marker lives in `section_extras` — the manifest's own forward-compat
    field — so the reason travels WITH the entity, per the Archive Contract.
    `/minder:mem:lint` Scan H reads it and stops re-raising, which turns a permanent
    nag into a recorded, inspectable state.

    Nothing about the manifest's data is altered. A quarantined manifest stays
    honestly invalid; the alternative would be inventing the missing values.
    """
    extras = data.get("section_extras")
    if not isinstance(extras, dict):
        extras = {}
        data["section_extras"] = extras
    extras["quarantine"] = {
        "reason": reason,
        "errors": errors[:20],
        "marked": ts,
    }


def retrofit_manifest(
    data: dict, audience_accept: set[str], domain_accept: set[str],
    filename: str | None = None, base: Path | None = None,
) -> tuple[dict, list[dict]]:
    """Run the data dict through the emit normaliser pipeline. Returns
    (mutated_data, events). The data dict is mutated in place; the
    return is a convenience for the caller.

    Unlike live emission, the retrofit passes `fill_sections=True` to the
    identity/section synthesiser so structurally-incomplete historical
    manifests (missing timestamp / processor / required sections, or
    early-dialect key names) become schema-valid. The filename supplies
    the processor and batch_id when the manifest body lacks them.
    """
    events: list[dict] = []
    # Historical corruption first: the normaliser below assumes well-shaped
    # scalars, so a null id or a truncated timestamp has to be repaired before
    # it runs, not after.
    #
    # Gated on the manifest ACTUALLY failing the schema. An ungated repair
    # rewrites healthy manifests too — filling optional fields the schema never
    # asked for, and stamping a `type` onto entry shapes that do not carry one.
    # Repair is a response to a diagnosed violation, never a blanket pass.
    if filename and schema_errors(data):
        events.extend(repair_historical(data, filename=filename, base=base))
    if not isinstance(data.get("stats"), dict):
        data["stats"] = {}
    stats = data["stats"]
    # Mirror of emit_batch_manifest.main() pipeline — keep in sync.
    e.synthesise_required_fields(
        data, events, filename=filename, fill_sections=True,
    )
    e.coerce_sources_processed(data, events, stats)
    e.normalise_empty_section_shapes(data, events, stats)
    e.relocate_tier2_misplaced_sections(data, events, stats)
    e.coerce_sensitive_entities(data, events, stats)
    e.walk_and_normalise(data, audience_accept, domain_accept, events)
    return data, events


def process_file(
    path: Path, audience_accept: set[str], domain_accept: set[str],
    apply: bool, base: Path | None = None, allow_quarantine: bool = False,
) -> tuple[bool, int, str | None]:
    """Process one manifest file. Returns (changed, event_count, error).

    On structural validation failure post-retrofit the manifest is NOT written
    and the error is returned — unless `allow_quarantine`, in which case the
    repaired body is written with a `section_extras.quarantine` marker naming
    what is still wrong. Quarantine is the honest end state for a manifest whose
    missing values cannot be derived from anything (a checksum whose file is
    gone): the alternative is inventing them.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, 0, f"read error: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, 0, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return False, 0, "root is not an object"

    before_text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    _, events = retrofit_manifest(
        data, audience_accept, domain_accept, filename=str(path), base=base,
    )
    after_text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    changed = before_text != after_text

    try:
        e.validate_manifest(data)
        deep_errors = e.deep_validate_manifest(data)
        if deep_errors:
            raise e.ManifestValidationError(
                "deep schema validation failed: " + "; ".join(deep_errors)
            )
    except e.ManifestValidationError as exc:
        if not allow_quarantine:
            return False, len(events), f"post-retrofit validation error: {exc}"
        quarantine(
            data,
            reason="no deterministic repair reaches schema conformance",
            errors=[str(exc)],
            ts=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        changed = True
        events.append({"event": "quarantined", "detail": str(exc)[:200]})

    if changed and apply:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        except BaseException:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise

    return changed, len(events), None


def main(argv: list[str] | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--batches-dir", type=Path, default=None,
        help="Directory containing manifest JSON files to retrofit.",
    )
    group.add_argument(
        "--file", type=Path, default=None,
        help="Single manifest file to retrofit.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write changes back. Default is dry-run.",
    )
    parser.add_argument(
        "--audiences", type=Path, default=None,
        help="AUDIENCES.md path.",
    )
    parser.add_argument(
        "--domains", type=Path, default=None,
        help="DOMAINS.md path.",
    )
    parser.add_argument(
        "--base", type=Path, default=None,
        help="Zettelkasten base dir, for on-disk repairs (title, checksum, path "
             "existence). Defaults to the batches dir's grandparent's parent.",
    )
    parser.add_argument(
        "--quarantine", action="store_true",
        help="Mark a manifest no deterministic repair can fix with "
             "`section_extras.quarantine` instead of leaving it a recurring "
             "failure. Never invents a value.",
    )
    args = parser.parse_args(argv)

    audience_accept, domain_accept = _load_accept_sets(
        args.audiences, args.domains,
    )

    base = args.base
    if base is None:
        anchor = args.batches_dir or (args.file.parent if args.file else None)
        # `<base>/_system/state/batches` → three levels up is the base.
        if anchor is not None and anchor.name == "batches":
            candidate = anchor.parents[2]
            if (candidate / "_system").is_dir():
                base = candidate

    if args.file:
        targets = [args.file]
    else:
        if not args.batches_dir.is_dir():
            sys.stderr.write(
                f"rewrite_manifest_violations: not a directory: "
                f"{args.batches_dir}\n"
            )
            return 2
        targets = sorted(args.batches_dir.glob("*.json"))

    total = 0
    changed_count = 0
    failed: list[tuple[Path, str]] = []
    for target in targets:
        if not target.is_file():
            continue
        total += 1
        changed, event_count, error = process_file(
            target, audience_accept, domain_accept, args.apply,
            base=base, allow_quarantine=args.quarantine,
        )
        if error is not None:
            failed.append((target, error))
            sys.stderr.write(
                f"{target.name}: FAIL: {error}\n"
            )
            continue
        if changed:
            changed_count += 1
            mode = "would change" if not args.apply else "rewrote"
            sys.stdout.write(
                f"{target.name}: {mode} ({event_count} fix events)\n"
            )
        else:
            sys.stdout.write(f"{target.name}: clean\n")

    sys.stdout.write(
        f"\nSummary: {total} file(s) scanned, {changed_count} "
        f"{'would change' if not args.apply else 'rewritten'}, "
        f"{len(failed)} failed.\n"
    )
    if failed:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
