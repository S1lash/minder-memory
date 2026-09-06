#!/usr/bin/env python3
"""
Personal-data linter.

Reads `.engine-manifest.yml` to learn which paths are engine + template
(those must contain no personal data identifying the owner of this
specific instance). Greps each path for blacklist patterns and reports.

The blacklist itself ships EMPTY in this script (see `DEFAULT_BLACKLIST`
below) — this script is engine code and reaches every friend's clone.
Three layers feed the final pattern list, in order:

1. `DEFAULT_BLACKLIST` — always empty (see above).
2. `load_owner_blacklist` — this instance's hand-curated residue list,
   read from `<repo-root>/personal-data-blacklist.txt` (git-tracked here,
   never shipped — see below).
3. `build_dynamic_blacklist` — patterns DERIVED at scan time from this
   instance's own data registries: `zettelkasten/3_resources/people/PEOPLE.md`
   (every real person's id + name), `zettelkasten/1_projects/PROJECTS.md`
   (every real project's id + display name), `zettelkasten/_system/SOUL.md`
   (the owner's Identity section — name, employer, location, handle, email),
   and `zettelkasten/0_constitution/{axiom,principle,rule}/*.md` (every
   principle's verbatim title + statement, ≥20 chars). This is what makes
   the linter auto-cover a growing PEOPLE.md/PROJECTS.md without hand-
   maintaining a blacklist line per person — a static list proved
   insufficient in practice (real coworker names, project names, and a
   verbatim axiom quote slipped through it before this layer existed).
   Guarded by `SAFE_TERMS` (synthetic placeholders and public product
   names like `Minder`/`Minder Memory` are never turned into patterns, even though
   they appear literally in the registries as example rows or project
   names), a common-word stoplist, a minimum length, and a placeholder
   (`{...}`) skip — see `_finalize_pattern` and the source-specific
   extractors below it for the full guard chain. On a fresh clone the
   registries are still template-shaped, so this layer returns close to
   nothing and the linter still runs clean.

The constitution-derived slice of the dynamic layer (verbatim axiom/
principle/rule title + statement patterns) is further scoped by
`SANCTIONED_PRINCIPLE_HOMES`: a small set of paths that legitimately ship
verbatim owner axioms as worked examples (the onboarding starter-pack, the
constitution protocol spec's own example, and the pipeline test fixtures).
`build_dynamic_blacklist_tagged` returns the constitution patterns as a
separate tagged list; `main()` skips that list — and only that list — when
scanning a file under one of those paths. Every other pattern class (people,
projects, identity, static blacklist) still applies there, and the
constitution patterns still apply to every other file. See
`SANCTIONED_PRINCIPLE_HOMES` below for the exact path list and rationale.

This instance's real patterns live in `<repo-root>/personal-data-blacklist.txt`,
a git-tracked-but-never-shipped file read at runtime (see
`load_owner_blacklist`). Friends populate their own from
`personal-data-blacklist.example.txt` (which does ship); the dynamic layer
above works for them too, with zero setup, once their own registries fill in.

Exit code:
  0 — no leaks found
  1 — leaks found (CI fails)

Usage:
  scripts/check_no_personal_data.py            # human report
  scripts/check_no_personal_data.py --quiet    # machine-readable, hits only
  scripts/check_no_personal_data.py --extra-pattern '\bAlice\b'

Manifest must be at repo root: `.engine-manifest.yml`.
"""

from __future__ import annotations

import argparse
import os
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.manifest import TEXT_SUFFIXES, repo_root, scan_targets  # noqa: E402
from lib.manifest import load_manifest as _load_manifest  # noqa: E402
from lib.portable import emit_lines  # noqa: E402


# Ships EMPTY — this file is engine code, distributed to every friend's
# clone. Naming the owner's identity, employer, or coworkers here would be
# exactly the leak this linter exists to prevent. This instance's real
# patterns are read at runtime from `<repo-root>/personal-data-blacklist.txt`
# (git-tracked in THIS private repo, never shipped — see `load_owner_blacklist`).
# Friends: copy `personal-data-blacklist.example.txt` to
# `personal-data-blacklist.txt` and add your own identifiers.
DEFAULT_BLACKLIST: list[str] = []

BLACKLIST_FILENAME = "personal-data-blacklist.txt"


# Paths that legitimately ship a verbatim owner axiom/principle/rule as a
# worked example — the owner's rule is "abstract principles may ship", so a
# constitution-derived pattern (title/statement text mined from
# `0_constitution/`) is never a leak in these three homes:
#   - the onboarding starter-pack, which literally IS a curated set of
#     example axioms handed to friends;
#   - the constitution protocol spec's own worked example (`CONSTITUTION.md`
#     documents the axiom/principle/rule shape by showing one, verbatim);
#   - the pipeline test fixtures, which need a realistic verbatim statement
#     to exercise `_constitution_candidates` / the dynamic-blacklist tests.
# Only the constitution-derived slice of the dynamic blacklist is skipped
# here (see `build_dynamic_blacklist_tagged`) — people, projects, identity,
# and the static blacklist still apply to every path below, and the
# constitution-derived patterns still apply to every path NOT listed here.
# A trailing `/` matches a directory prefix; no trailing `/` matches exactly
# one file.
SANCTIONED_PRINCIPLE_HOMES = (
    "zettelkasten/5_meta/starter-pack/",
    "zettelkasten/0_constitution/CONSTITUTION.md",
    "zettelkasten/_system/scripts/tests/",
)


def is_sanctioned_principle_home(rel_path: Path) -> bool:
    """True when `rel_path` (relative to repo root) falls under one of the
    `SANCTIONED_PRINCIPLE_HOMES` — see that constant for the guard chain
    this participates in."""
    rel_str = rel_path.as_posix()
    for home in SANCTIONED_PRINCIPLE_HOMES:
        if home.endswith("/"):
            if rel_str.startswith(home):
                return True
        elif rel_str == home:
            return True
    return False


# ---------------------------------------------------------------------------
# Verbatim-corpus layer
# ---------------------------------------------------------------------------
#
# The dynamic layer above derives patterns from the instance's REGISTRIES and
# greps shipped files for them. It structurally cannot reach one class: the
# owner's own words, quoted out of a transcript and left in a shipped prompt as
# a worked example. The corpus (`_records/`, `_sources/`) is free prose with no
# bounded pattern to extract — any extraction wide enough to catch such a
# sentence flags ordinary language.
#
# So this layer searches the other way. Spans a shipped file DELIMITS as a
# quotation are few (hundreds) and are by construction intended examples; each
# is tested for exact occurrence in the corpus. Exact match keeps the verdict
# deterministic and the false-positive rate near zero: a sentence the engine
# invented does not appear verbatim in a transcript.
#
# Known limitation, stated rather than papered over: only DELIMITED spans are
# checked. A verbatim owner sentence written into a prompt with no quotation
# marks escapes this layer. Widening to undelimited n-grams was considered and
# rejected — the cost is a false-positive tail that needs a stoplist, and every
# example these prompts actually contain is delimited.
#
# Output discipline (load-bearing): a hit prints the SHIPPED file, its line,
# the span — all three already committed in git — plus the corpus file's PATH.
# Never corpus surrounding text. A gate against leaking the owner's words must
# not leak them into a terminal or a CI log while reporting.

CORPUS_DIRS = ("zettelkasten/_records", "zettelkasten/_sources")

# Above the length at which an ordinary phrase coincides, below the shortest
# real leak found in practice.
QUOTE_MIN_LEN = 24

# Upper bound on a delimited span. Not a judgement about what counts as a
# quotation — purely a guard against a runaway match when a closing delimiter
# is missing. High enough that a real block quotation is still tested.
QUOTE_MAX_LEN = 2000

# A separator that cannot occur in the sources, so a span can never match
# across the seam between two corpus files.
_CORPUS_SEP = "\x00"

def _span_re(pairs: tuple[tuple[str, str], ...]) -> re.Pattern[str]:
    return re.compile(
        "|".join(
            f"{re.escape(o)}(?P<g{i}>[^{re.escape(c)}]{{{QUOTE_MIN_LEN},{QUOTE_MAX_LEN}}}?){re.escape(c)}"
            for i, (o, c) in enumerate(pairs)
        ),
        re.DOTALL,
    )


# In prose, all four pairs delimit a quotation.
_PROSE_PAIRS = (("«", "»"), ('"', '"'), ("\u201c", "\u201d"), ("『", "』"))

# In SOURCE files the ASCII double quote is the language's own string
# delimiter, not a quotation mark: every literal in a python or shell file
# would otherwise be treated as something someone said. Two such literals
# ("applies_to: [claude-code]", "no summary metrics aggregated") were reported
# as leaks on the first run with the test tree unexempted — both engine
# vocabulary that the engine itself had written into a record, matched against
# itself. The typographic pairs stay: a real owner sentence quoted inside a
# fixture is written with guillemets, which is exactly how the one real leak in
# this repo's own tests was written.
_CODE_PAIRS = (("«", "»"), ("\u201c", "\u201d"), ("『", "』"))

_CODE_SUFFIXES = {".py", ".sh", ".bash", ".js", ".mjs", ".json", ".yml", ".yaml", ".toml", ".ps1"}

_QUOTE_SPAN_RE = _span_re(_PROSE_PAIRS)
_CODE_SPAN_RE = _span_re(_CODE_PAIRS)


def span_re_for(path: Path | str | None) -> re.Pattern[str]:
    if path is None:
        return _QUOTE_SPAN_RE
    return _CODE_SPAN_RE if Path(path).suffix.lower() in _CODE_SUFFIXES else _QUOTE_SPAN_RE


def normalize_for_corpus(text: str) -> str:
    """The ONE normalisation, applied to both sides of every comparison.

    Applying it to one side only is the failure mode that matters: every
    multi-line quote would silently stop matching and the gate would report
    green forever, which looks exactly like success.
    """
    return re.sub(r"[^\S\x00]+", " ", unicodedata.normalize("NFC", text)).strip()


def extract_quoted_spans(text: str, path: Path | str | None = None) -> list[tuple[int, str]]:
    """`(line_number, normalised_span)` for every delimited span worth testing.

    A span with no space is an identifier or a path, never an utterance.
    """
    out: list[tuple[int, str]] = []
    seen: set[str] = set()
    for m in span_re_for(path).finditer(text):
        raw = next((g for g in m.groups() if g is not None), None)
        if raw is None:
            continue
        span = normalize_for_corpus(raw)
        if len(span) < QUOTE_MIN_LEN or " " not in span or span in seen:
            continue
        seen.add(span)
        out.append((text.count("\n", 0, m.start()) + 1, span))
    return out


class Corpus:
    """The owner's own words, read once.

    Engine and template files are SUBTRACTED from the haystack even when they
    live under a corpus directory (`_records/README.md`, the describe-me
    questionnaire under `_sources/inbox/`). Without that subtraction the gate
    matches shipped text against itself and reports a leak that is nothing of
    the kind — two such false positives appeared on the first real run.

    Holds the per-file texts as well as the joined blob: locating a hit then
    costs nothing, where re-reading the corpus per hit cost ~25 s each.
    """

    # A separator that cannot occur in the sources, so a span can never match
    # across the seam between two corpus files.
    SEP = "\x00"

    # Prefilter vocabulary. Soundness is the whole game here: a filter that
    # rejects a span the full search WOULD have found is a false negative in a
    # privacy gate, and it is invisible — the run goes green.
    #
    # Only the span's INTERIOR words are safe to test. If the span occurs in
    # the corpus, every word bounded by spaces on both sides inside the span is
    # a complete corpus token; its FIRST and LAST words may be fragments of
    # longer tokens there (corpus «unbrokenidentifier», span starting
    # «identifier …»), so testing those against a token set rejects real
    # matches. That exact case is pinned by a test.
    _WORD_RE = re.compile(r"[^\W\d_]{7,}", re.UNICODE)
    _INTERIOR_RE = re.compile(r"(?<=\s)[^\W\d_]{7,}(?=\s)", re.UNICODE)

    def __init__(self, files: list[tuple[str, str]]) -> None:
        self.files = files
        self.blob = self.SEP.join(text for _, text in files)
        self.words = set(self._WORD_RE.findall(self.blob))

    def __bool__(self) -> bool:
        return bool(self.blob)

    def may_contain(self, span: str) -> bool:
        """A NECESSARY condition for `span in self.blob` — never a sufficient
        one, and never allowed to be wrong in the rejecting direction."""
        return all(w in self.words for w in self._INTERIOR_RE.findall(span))

    def contains(self, span: str) -> bool:
        return self.may_contain(span) and span in self.blob

    def locate(self, span: str) -> str | None:
        """Repo-relative path of the first corpus file holding `span`."""
        for rel, text in self.files:
            if span in text:
                return rel
        return None


def build_corpus(root: Path, shipped: set[Path] | None = None) -> Corpus:
    """Read the corpus once, minus anything that ships."""
    shipped = shipped or set()
    files: list[tuple[str, str]] = []
    for rel in CORPUS_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if path.resolve() in shipped or path.name.endswith(".template.md"):
                continue
            try:
                text = normalize_for_corpus(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            files.append((path.relative_to(root).as_posix(), text))
    return Corpus(files)


def build_corpus_blob(root: Path, shipped: set[Path] | None = None) -> Corpus:
    """Name kept for callers that read this as «the haystack»."""
    return build_corpus(root, shipped)


def scan_file_for_corpus_quotes(
    path: Path, corpus: "Corpus", relpath: str | None = None
) -> list[tuple[int, str]]:
    """Spans this shipped file quotes that occur verbatim in the corpus.

    `relpath` (repo-relative) opts the file into the sanctioned-homes
    exemption — the same paths the constitution layer exempts, for the same
    reason: they legitimately ship verbatim owner axioms.
    """
    if relpath is not None and is_sanctioned_quote_home(Path(relpath)):
        return []
    if not corpus:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [
        (ln, span)
        for ln, span in extract_quoted_spans(text, path)
        if corpus.contains(span)
    ]


def locate_span_in_corpus(corpus: "Corpus", span: str) -> str | None:
    return corpus.locate(span)


QUOTE_EXCEPTIONS_FILENAME = "shipped-quote-exceptions.txt"


def span_digest(span: str) -> str:
    """Stable short digest of a normalised span. Identifies a hit in a report
    without reproducing it, and keys an exception to the exact text — so an
    exception stops applying the moment the shipped line changes."""
    return hashlib.sha256(span.encode("utf-8")).hexdigest()[:16]


def load_quote_exceptions(root: Path) -> dict[tuple[str, str], str]:
    """Instance-local, never-shipped exceptions for the corpus layer.

    Same shape and the same promise as `personal-data-blacklist.txt`: tracked
    in this private repo, absent from `.engine-manifest.yml`, so it reaches no
    skeleton. It exists for one case the shared engine cannot solve — a
    friend's own recording happening to contain, word for word, an example the
    engine ships. They can neither edit engine text nor delete their own
    record, so without this the gate is permanently red on something that is
    nobody's defect.

    Format, tab-separated: `<shipped-path>	<span-digest>	<reason>`. The
    reason is required — an exception with no stated ground is the failure mode
    this file would otherwise become. Keying on the digest means an exception
    dies when the shipped line is edited, so it cannot quietly outlive what it
    excused.
    """
    p = root / QUOTE_EXCEPTIONS_FILENAME
    if not p.exists():
        return {}
    out: dict[tuple[str, str], str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [f.strip() for f in stripped.split("\t") if f.strip()]
        if len(parts) < 3:
            continue
        out[(parts[0], parts[1])] = parts[2]
    return out


def render_corpus_hit(
    rel: str, line_no: int, span: str, corpus_path: str | None, reveal: bool = False
) -> str:
    """One report line.

    Carries no corpus text — and, by default, no corpus PATH either. A record's
    filename is built from its own subject («…observation-defenses-critique-
    mood-…»), so printing it into a terminal or a CI log discloses the very
    thing this gate exists to keep private. The default is an opaque digest;
    `--reveal-corpus-paths` prints the real path for an owner looking locally.
    """
    if corpus_path is None:
        where = "(corpus file not located)"
    elif reveal:
        where = corpus_path
    else:
        where = f"corpus file {span_digest(corpus_path)} (re-run with --reveal-corpus-paths)"
    return (
        f"{rel}:{line_no}  [verbatim in corpus, span {span_digest(span)}]\n"
        f"    a quoted span here occurs word-for-word in {where}"
    )


# Homes exempt from the VERBATIM-CORPUS layer. Deliberately NARROWER than
# `SANCTIONED_PRINCIPLE_HOMES`: those two ship the owner's principles as worked
# examples by design, so a verbatim match there is the feature. The test tree is
# not on this list, and that is the point — a test plants its own corpus in a
# temp directory, so it never needs a real owner sentence, and exempting it once
# let exactly such a sentence ship inside a fixture. Found in the built
# skeleton, after the gate that exists to prevent it had passed.
SANCTIONED_QUOTE_HOMES = (
    "zettelkasten/5_meta/starter-pack/",
    "zettelkasten/0_constitution/CONSTITUTION.md",
)


def is_sanctioned_quote_home(rel_path: Path) -> bool:
    rel_str = rel_path.as_posix()
    for home in SANCTIONED_QUOTE_HOMES:
        if home.endswith("/"):
            if rel_str.startswith(home):
                return True
        elif rel_str == home:
            return True
    return False


def load_manifest(root: Path) -> dict:
    """The manifest, or a clean abort naming the file this gate cannot run without."""
    if not (root / ".engine-manifest.yml").exists():
        print(f"error: manifest not found at {root / '.engine-manifest.yml'}", file=sys.stderr)
        sys.exit(2)
    return _load_manifest(root)


def load_owner_blacklist(root: Path) -> list[str]:
    """Read this instance's real patterns from `personal-data-blacklist.txt`.

    That file is git-tracked in THIS private repo (so CI here has it) but is
    never listed in `.engine-manifest.yml`, so it never ships to the public
    skeleton. Absent file (e.g. a friend's fresh clone that hasn't copied
    `personal-data-blacklist.example.txt` yet) is not an error — the linter
    just runs with an empty blacklist and passes.
    """
    p = root / BLACKLIST_FILENAME
    if not p.exists():
        return []
    patterns: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


# -----------------------------------------------------------------------------
# Dynamic blacklist — derived from this instance's own data registries.
# -----------------------------------------------------------------------------
#
# Never turned into a pattern even if a registry row literally contains one:
# synthetic placeholder ids used throughout the engine's own depersonalized
# examples, and public product names that are meant to ship. Case-insensitive;
# a derived value that is entirely composed of these tokens is also dropped
# (see `_is_safe_term`) — otherwise a project literally named "minder" (this
# instance's own project id) would flag every mention of the product itself.
SAFE_TERMS = {
    "ivan-petrov", "petya-ivanov", "anna-smirnova", "maria-sidorova",
    "oleg-volkov", "katya-orlova", "sergey-kozlov", "john-doe",
    "acme-payments", "example.com", "project-alpha", "project-beta",
    "Minder", "Minder Memory", "Minder Mem", "minder-memory", "minder-mem",
    "minder.host", "Zettelkasten",
}
_SAFE_TERMS_LOWER = {t.lower() for t in SAFE_TERMS}

# Table header words / stray fragments that must never stand alone as a
# pattern (defence in depth against a parsing edge case grabbing a header
# cell instead of a data cell).
_COMMON_WORD_STOPLIST = {"status", "active", "personal", "work", "name", "role", "project"}

# Below this length a derived token is more likely a stray initial/fragment
# than a real identifier — drop it rather than risk a noisy pattern.
MIN_PATTERN_LENGTH = 5

_PLACEHOLDER_MARKERS = ("{", "}", "REPLACE_WITH_", "<", ">", "...")

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9][\w.\-]*")


def _looks_like_placeholder(value: str) -> bool:
    """True for unfilled template values — never derive a pattern from these."""
    return any(marker in value for marker in _PLACEHOLDER_MARKERS)


def _is_safe_term(value: str) -> bool:
    """True when `value` matches — or is composed entirely of — SAFE_TERMS."""
    lowered = value.strip().lower()
    if lowered in _SAFE_TERMS_LOWER:
        return True
    tokens = _TOKEN_RE.findall(lowered)
    return bool(tokens) and all(t in _SAFE_TERMS_LOWER for t in tokens)


def _is_word_char(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch == "_")


def _finalize_pattern(value: str) -> str | None:
    """Single choke point every derived candidate passes through.

    Applies the placeholder / length / stoplist / safe-term guards, then
    `re.escape`s the literal and wraps it in `\\b...\\b` boundaries — mirrors
    how `personal-data-blacklist.txt` patterns are written by hand, so the
    dynamic layer composes with `DEFAULT_BLACKLIST` / `load_owner_blacklist`
    as plain interchangeable regex strings.

    A `\\b` boundary is only added on a side whose edge character is a word
    character. Names and ids always qualify on both sides. A constitution
    statement typically ends in sentence punctuation (`.`, `»`) — `\\b`
    there would require the *following* character to be a word character,
    which a sentence-ending period essentially never is (it's followed by
    whitespace or end-of-line), silently making the pattern unmatchable.
    Dropping the boundary on that side only removes an assertion, it never
    changes what literal text the pattern still requires.
    """
    v = value.strip()
    if not v or _looks_like_placeholder(v):
        return None
    if len(v) < MIN_PATTERN_LENGTH:
        return None
    if v.lower() in _COMMON_WORD_STOPLIST:
        return None
    if _is_safe_term(v):
        return None
    prefix = r"\b" if _is_word_char(v[0]) else ""
    suffix = r"\b" if _is_word_char(v[-1]) else ""
    return f"{prefix}{re.escape(v)}{suffix}"


# --- Markdown table parsing (PEOPLE.md, PROJECTS.md) ------------------------


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


def _is_separator_row(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def parse_markdown_tables(text: str) -> list[dict]:
    """Generic GFM-table parser: `[{'header': [...], 'rows': [[...], ...]}, ...]`.

    Tolerant of a single stray blank line inside a table body (PEOPLE.md's
    batch-append log occasionally leaves one between row runs) but stops at
    two consecutive blank lines or any non-table content line — so it never
    merges two distinct tables (they are always separated by a `##` heading
    or a `---` rule in the files this reads).
    """
    lines = text.splitlines()
    n = len(lines)
    tables: list[dict] = []
    i = 0
    while i < n - 1:
        if lines[i].strip().startswith("|") and _is_separator_row(lines[i + 1]):
            header = _split_table_row(lines[i])
            i += 2
            rows: list[list[str]] = []
            blank_run = 0
            while i < n:
                stripped = lines[i].strip()
                if stripped.startswith("|"):
                    rows.append(_split_table_row(lines[i]))
                    blank_run = 0
                    i += 1
                elif stripped == "":
                    blank_run += 1
                    i += 1
                    if blank_run >= 2:
                        break
                else:
                    break
            tables.append({"header": header, "rows": rows})
            continue
        i += 1
    return tables


_EMPTY_CELL_VALUES = {"", "-", "—"}
_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _is_empty_cell(value: str) -> bool:
    v = value.strip()
    return v in _EMPTY_CELL_VALUES or v.startswith("_(")


def _id_name_rows_from_tables(text: str) -> list[tuple[str, str]]:
    """Extract (id, name) pairs from every table whose header is
    `ID | Name | ...` (case-insensitive) — the shape PEOPLE.md's `## People` /
    `## Stale People` tables and PROJECTS.md's project tables share.

    Tables with a different header shape are skipped automatically: PEOPLE.md's
    2-column `## Removed` list (header `ID | Reason`, no `Name` column) and
    PROJECTS.md's `Old ID | Status | Now part of` redirect table (first header
    cell is `Old ID`, not `ID`) never match.
    """
    out: list[tuple[str, str]] = []
    for table in parse_markdown_tables(text):
        header = [h.strip().lower() for h in table["header"]]
        if not header or header[0] != "id" or "name" not in header:
            continue
        name_idx = header.index("name")
        for row in table["rows"]:
            if len(row) <= name_idx:
                continue
            rid, name = row[0].strip(), row[name_idx].strip()
            if not _ID_RE.match(rid):
                continue
            if _is_empty_cell(rid) or _is_empty_cell(name):
                continue
            if _looks_like_placeholder(rid) or _looks_like_placeholder(name):
                continue
            out.append((rid, name))
    return out


def _is_specific_display_name(name: str) -> bool:
    """Guard for PROJECTS.md display names: the id is always emitted (specific
    by construction — a kebab identifier), but the free-text name is only
    emitted when it is unlikely to be a generic single word."""
    v = name.strip()
    return bool(v) and (" " in v or "-" in v or len(v) >= 6)


def _people_candidates(root: Path) -> list[str]:
    path = root / "zettelkasten" / "3_resources" / "people" / "PEOPLE.md"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[str] = []
    for rid, name in _id_name_rows_from_tables(text):
        out.append(rid)
        out.append(name)
    return out


def _project_candidates(root: Path) -> list[str]:
    path = root / "zettelkasten" / "1_projects" / "PROJECTS.md"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[str] = []
    for rid, name in _id_name_rows_from_tables(text):
        out.append(rid)
        if _is_specific_display_name(name):
            out.append(name)
    return out


# --- SOUL.md Identity section -------------------------------------------------

_IDENTITY_FIELDS = {"name", "role", "location", "handle", "github", "email", "employer"}
_IDENTITY_BULLET_RE = re.compile(r"^-\s+\*\*([^*:]+):\*\*\s*(.+)$")


def _extract_section(text: str, heading: str) -> str | None:
    """Return the body of a `## Heading` section (up to the next `## `), or
    None if the heading is absent."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def _extract_employer_candidates(role_value: str) -> list[str]:
    """Pull employer-like proper nouns out of a free-text Role bullet.

    Structural, not semantic — deliberately does not try to parse arbitrary
    prose (that risks grabbing a generic word and turning it into an
    over-broad pattern). Only two shapes qualify:

    - Text after a literal `@` (the `Role @ Employer` convention), up to the
      next `.`/`,`/`(`.
    - Any parenthetical alias, e.g. `(brand X)` / `(бренд X)`, with the
      lead-in word stripped.

    Both are additionally required to start with an uppercase letter (a
    cheap proper-noun heuristic) — this is what keeps a hypothetical
    `(remote)` or `(part-time)` annotation from becoming a pattern. A Role
    value with neither shape yields nothing rather than guessing from prose.
    """
    out: list[str] = []
    at_match = re.search(r"@\s*([^.,(\n]+)", role_value)
    if at_match:
        candidate = at_match.group(1).strip()
        if candidate and candidate[0].isupper():
            out.append(candidate)
    for paren in re.findall(r"\(([^)]+)\)", role_value):
        cleaned = re.sub(r"^(?:бренд|brand|aka|a\.k\.a\.)\s+", "", paren.strip(), flags=re.IGNORECASE)
        if cleaned and cleaned[0].isupper():
            out.append(cleaned)
    return out


def _identity_candidates(root: Path) -> list[str]:
    path = root / "zettelkasten" / "_system" / "SOUL.md"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    section = _extract_section(text, "## Identity")
    if section is None:
        return []
    out: list[str] = []
    for line in section.splitlines():
        m = _IDENTITY_BULLET_RE.match(line.strip())
        if not m:
            continue
        field, value = m.group(1).strip().lower(), m.group(2).strip()
        if field not in _IDENTITY_FIELDS or _looks_like_placeholder(value):
            continue
        if field == "role":
            out.extend(_extract_employer_candidates(value))
        else:
            # Name / Location / Handle / Github / Email / Employer: taken
            # verbatim as one value, not split into words — e.g. Location's
            # "City, Country" stays one pattern rather than splitting into a
            # bare country name (a real false-positive risk: a country name
            # alone is generic enough to collide with unrelated text).
            out.append(value)
    return out


# --- Constitution (0_constitution/{axiom,principle,rule}/*.md) --------------

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def _read_frontmatter_fields(path: Path, fields: tuple[str, ...]) -> dict:
    """Minimal standalone frontmatter reader.

    Deliberately does not import `zettelkasten/_system/scripts/_common.py`
    (which has its own `read_frontmatter`) — this script ships standalone to
    every friend's clone under `scripts/`, a different subsystem than the Minder Memory
    pipeline package under `zettelkasten/_system/scripts/`, and stays
    independently distributable without that cross-package coupling.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in fields if k in data}


def _constitution_candidates(root: Path) -> list[str]:
    base = root / "zettelkasten" / "0_constitution"
    out: list[str] = []
    for kind in ("axiom", "principle", "rule"):
        kind_dir = base / kind
        if not kind_dir.exists():
            continue
        for md_path in sorted(kind_dir.rglob("*.md")):
            fm = _read_frontmatter_fields(md_path, ("title", "statement"))
            for field in ("title", "statement"):
                value = fm.get(field)
                if not isinstance(value, str):
                    continue
                normalized = " ".join(value.split())
                if len(normalized) >= 20 and not _looks_like_placeholder(normalized):
                    out.append(normalized)
    return out


def _dedupe_into_patterns(candidates: list[str], seen: set[str]) -> list[str]:
    """Run `candidates` through `_finalize_pattern`, keeping first-seen order
    and skipping anything already in `seen` (mutated in place — shared across
    the general/constitution split in `build_dynamic_blacklist_tagged` so a
    value that would produce the same pattern from two sources is never
    listed twice)."""
    patterns: list[str] = []
    for value in candidates:
        pattern = _finalize_pattern(value)
        if pattern and pattern not in seen:
            seen.add(pattern)
            patterns.append(pattern)
    return patterns


def build_dynamic_blacklist_tagged(root: Path) -> tuple[list[str], list[str]]:
    """Derive personal-data regex patterns from this instance's own data
    registries, split into `(general_patterns, constitution_patterns)`.

    `general_patterns` come from people, projects, and identity (SOUL.md) —
    these apply everywhere, unconditionally. `constitution_patterns` come
    from verbatim axiom/principle/rule title + statement text — these are
    the ones `main()` skips for files under `SANCTIONED_PRINCIPLE_HOMES`
    (see that constant for why). The two lists are deduped against a shared
    `seen` set, general first, so this split changes nothing about which
    patterns exist versus the pre-split single-list design — only how
    `main()` is able to apply them. See the module docstring for the full
    design and the guard chain in `_finalize_pattern`.

    Pattern sources are read directly by path (not through `expand_paths`),
    so reading them never adds them to the linter's own scan targets — they
    are owner-data paths, already outside `.engine-manifest.yml`'s
    `engine:`/`template:` lists.

    Missing registry files are not an error — each source function returns
    `[]` and derivation continues with whatever is available. On a fresh
    clone the registries are still template-shaped (`{placeholder}` values),
    so every candidate is caught by the placeholder guard and this returns
    two empty (or near-empty) lists — the linter still runs clean.
    """
    general_candidates: list[str] = []
    general_candidates.extend(_people_candidates(root))
    general_candidates.extend(_project_candidates(root))
    general_candidates.extend(_identity_candidates(root))

    seen: set[str] = set()
    general_patterns = _dedupe_into_patterns(general_candidates, seen)
    constitution_patterns = _dedupe_into_patterns(_constitution_candidates(root), seen)
    return general_patterns, constitution_patterns


def build_dynamic_blacklist(root: Path) -> list[str]:
    """Flat, untagged view of `build_dynamic_blacklist_tagged` — general
    patterns followed by constitution-derived patterns, identical to the
    single-list design before the sanctioned-homes split existed. Kept for
    callers (tests, ad-hoc scans) that don't need the per-file exception
    `main()` applies; see `build_dynamic_blacklist_tagged` for that."""
    general_patterns, constitution_patterns = build_dynamic_blacklist_tagged(root)
    return general_patterns + constitution_patterns


# Two files that are engine surface but must never be scanned: this gate (it
# would match its own explanatory prose) and the owner blacklist (it is a list
# of the very patterns being hunted, and it never ships).
def _self_excluded(root: Path) -> set[Path]:
    return {Path(__file__).resolve(), (root / BLACKLIST_FILENAME).resolve()}


def expand_paths(root: Path, raw: list[str]) -> list[Path]:
    """Expand manifest entries into concrete scannable files.

    Thin wrapper over `lib.manifest.expand_paths` for callers holding one
    section. `main()` uses `scan_targets` instead, which additionally subtracts
    `exclude:`.
    """
    from lib.manifest import expand_paths as _expand

    skip = _self_excluded(root)
    return sorted(p for p in _expand(root, raw) if p.resolve() not in skip)


def scan_file(path: Path, patterns: list[re.Pattern[str]]) -> list[tuple[int, str, str]]:
    """Return list of (line_no, pattern, line_text) for each hit."""
    hits: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            if pat.search(line):
                hits.append((line_no, pat.pattern, line.rstrip()))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="machine-readable, hits only")
    ap.add_argument(
        "--reveal-corpus-paths",
        action="store_true",
        help="print the real corpus path of a verbatim hit instead of a digest "
             "(local use — the path itself carries the record's subject)",
    )
    ap.add_argument(
        "--extra-pattern",
        action="append",
        default=[],
        help="add an extra regex to the blacklist (repeatable)",
    )
    args = ap.parse_args()

    root = repo_root()
    manifest = load_manifest(root)

    # `scan_targets` subtracts `exclude:`. Engine entries are frequently
    # directory globs (`scripts/`) with owner-specific files carved out beneath
    # them; without the subtraction such a file still trips this gate even
    # though the manifest says it never ships, and excluding it has no
    # observable effect.
    skip = _self_excluded(root)
    targets = [p for p in scan_targets(root, manifest) if p.resolve() not in skip]

    general_dynamic, constitution_dynamic = build_dynamic_blacklist_tagged(root)
    always_raw = (
        DEFAULT_BLACKLIST
        + load_owner_blacklist(root)
        + general_dynamic
        + list(args.extra_pattern)
    )
    always_patterns = [re.compile(p) for p in always_raw]
    constitution_patterns = [re.compile(p) for p in constitution_dynamic]

    # Built once. Empty on a fresh clone whose corpus has not filled in,
    # which makes the layer a no-op there rather than a false green.
    corpus = build_corpus(root, shipped={p.resolve() for p in targets})
    quote_exceptions = load_quote_exceptions(root)

    total_hits = 0
    files_with_hits = 0
    for path in targets:
        rel = path.relative_to(root)
        # Constitution-derived verbatim patterns are skipped for files under
        # SANCTIONED_PRINCIPLE_HOMES — see that constant. Every other
        # pattern class (people, projects, identity, static blacklist,
        # --extra-pattern) still applies everywhere, including here.
        patterns = (
            always_patterns
            if is_sanctioned_principle_home(rel)
            else always_patterns + constitution_patterns
        )
        hits = scan_file(path, patterns)
        quote_hits = scan_file_for_corpus_quotes(path, corpus, relpath=rel.as_posix())
        if not hits and not quote_hits:
            continue
        before = total_hits
        for line_no, pat, line in hits:
            total_hits += 1
            if args.quiet:
                emit_lines([f"{rel}:{line_no}\t{pat}\t{line}"])
            else:
                print(f"{rel}:{line_no}  [{pat}]")
                print(f"    {line}")
        for line_no, span in quote_hits:
            excused = quote_exceptions.get((rel.as_posix(), span_digest(span)))
            if excused:
                if not args.quiet:
                    print(f"{rel}:{line_no}  [verbatim in corpus — excused: {excused}]")
                continue
            total_hits += 1
            corpus_path = corpus.locate(span)
            if args.quiet:
                emit_lines([f"{rel}:{line_no}\tverbatim-in-corpus\t{span_digest(span)}"])
            else:
                print(render_corpus_hit(rel.as_posix(), line_no, span, corpus_path,
                                        reveal=args.reveal_corpus_paths))

        if total_hits > before:
            files_with_hits += 1

    if not args.quiet:
        print()
        print(f"scanned {len(targets)} files, {files_with_hits} with leaks, {total_hits} total hits")
        if total_hits == 0:
            print("✓ no personal data leaks found")
        else:
            print("✗ personal data leaks found — fix before extraction")

    return 1 if total_hits > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
