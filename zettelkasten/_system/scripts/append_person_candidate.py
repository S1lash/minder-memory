#!/usr/bin/env python3
"""Append a bare-name people candidate to `_system/state/people-candidates.jsonl`.

Invoked by `/minder:mem:process` Step 3.8 when a bare first name is encountered
that cannot be resolved to a `firstname-lastname` PEOPLE.md ID. Instead
of creating a CLARIFICATION per one-off mention (high friction for the
user), the mention is appended to this buffer. `/minder:mem:lint` Scan C.5
aggregates the buffer weekly and promotes recurring or information-rich
candidates to CLARIFICATIONS.

Schema of each JSONL line:

    {
      "candidate_id": "cand-YYYYMMDD-{slug}-{seq}",
      "date": "YYYY-MM-DD",               # transcript date (record.created)
      "captured_at": "YYYY-MM-DDThh:mm:ssZ",
      "name_as_transcribed": "Петя",
      "source": "plaud/2026-04-21T13:31:11Z",
      "note_id": "20260421-meeting-...",  # record produced by /minder:mem:process
      "quote": "...",                     # verbatim transcript fragment (≥1 sentence)
      "role_hint": "dev (review likes)" | null,
      "related_people": ["ivan-petrov"] | [],
      "suggested_id": null | "petya-ivanov",
      "high_importance_hint": false,      # if true, lint will auto-promote regardless of count
      "captured_by": "minder:mem:process"
    }

Usage:
    python3 append_person_candidate.py \\
        --name "Петя" \\
        --date 2026-04-21 \\
        --source "plaud/2026-04-21T13:31:11Z" \\
        --note-id 20260421-meeting-team-weekly \\
        --quote "У Пети требуйте лайков на ревью" \\
        [--role-hint "dev"] \\
        [--related-people ivan-petrov,anna-smirnova] \\
        [--suggested-id petya-ivanov] \\
        [--high-importance] \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from _common import configure_std_streams, die, state_dir


BUFFER_FILENAME = "people-candidates.jsonl"


def slugify(name: str) -> str:
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = []
    for ch in name.lower():
        if ch in translit:
            out.append(translit[ch])
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug or "unknown"


def next_seq_for_day(buffer_path: Path, date_compact: str, name_slug: str) -> int:
    if not buffer_path.exists():
        return 1
    prefix = f"cand-{date_compact}-{name_slug}-"
    max_seq = 0
    with buffer_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = rec.get("candidate_id", "")
            if cid.startswith(prefix):
                try:
                    max_seq = max(max_seq, int(cid[len(prefix):]))
                except ValueError:
                    pass
    return max_seq + 1


def now_iso_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="name as transcribed (bare)")
    parser.add_argument("--date", required=True, help="transcript date YYYY-MM-DD")
    parser.add_argument("--source", required=True, help="source path excerpt")
    parser.add_argument("--note-id", required=True, help="Minder Memory record/note id produced by process")
    parser.add_argument("--quote", required=True, help="verbatim transcript fragment (≥1 sentence)")
    parser.add_argument("--role-hint", default=None)
    parser.add_argument("--related-people", default="", help="comma-separated person ids")
    parser.add_argument("--suggested-id", default=None)
    parser.add_argument("--high-importance", action="store_true")
    parser.add_argument("--buffer", type=Path, default=None,
                        help=f"override buffer path (default: _system/state/{BUFFER_FILENAME})")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        die(f"invalid --date {args.date!r}; expected YYYY-MM-DD")
    if not args.name.strip():
        die("--name must be non-empty")
    if not args.quote.strip():
        die("--quote must be non-empty")

    buffer_path = args.buffer or (state_dir() / BUFFER_FILENAME)
    date_compact = args.date.replace("-", "")
    name_slug = slugify(args.name)
    seq = next_seq_for_day(buffer_path, date_compact, name_slug)
    candidate_id = f"cand-{date_compact}-{name_slug}-{seq:02d}"

    related = [p.strip() for p in args.related_people.split(",") if p.strip()]

    record = {
        "candidate_id": candidate_id,
        "date": args.date,
        "captured_at": now_iso_utc(),
        "name_as_transcribed": args.name,
        "source": args.source,
        "note_id": args.note_id,
        "quote": args.quote.strip(),
        "role_hint": args.role_hint,
        "related_people": related,
        "suggested_id": args.suggested_id,
        "high_importance_hint": bool(args.high_importance),
        "captured_by": "minder:mem:process",
    }

    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))

    if args.dry_run:
        print(line)
        return 0

    buffer_path.parent.mkdir(parents=True, exist_ok=True)
    with buffer_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(f"appended {candidate_id} to {buffer_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
