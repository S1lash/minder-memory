#!/usr/bin/env python3
"""The single reader of `.engine-manifest.yml`.

The manifest declares what leaves this instance for the public skeleton. Four
tools need that answer — the release copier, the personal-data gate, the
seed-contract gate, the portability gate — and a fifth (the scheduler's path
classifier) needs it inside a sandbox that has no PyYAML. Before this module
each had its own reader, and they had already drifted: the personal-data gate
expanded `engine:` + `template:` but never subtracted `exclude:`, so a file the
manifest says never ships still tripped the gate.

Two readers live here, on purpose, with a test that pins them together:

- `load_manifest` — PyYAML, full document. For tooling that already depends on
  PyYAML and needs the whole structure (`seed_skill:`, `version:`).
- `read_section_lite` — dependency-free line parser for the three list-shaped
  sections. The scheduler sandbox runs `_classify_paths.py` with nothing but a
  stock python, so it cannot import PyYAML; that constraint is real and is why
  a second reader exists rather than being a DRY violation.

`test_engine_lib.py::ManifestTests::test_lite_matches_yaml_on_every_list_section`
asserts the two agree on every section of the live manifest, so they cannot
diverge silently. It has already earned its keep: it caught the lite reader
keeping an inline `# comment` that YAML strips.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "TEXT_SUFFIXES",
    "LIST_SECTIONS",
    "repo_root",
    "load_manifest",
    "read_section_lite",
    "expand_paths",
    "scan_targets",
]

# Text file kinds any engine gate can read line-by-line. A suffix absent here is
# treated as binary and skipped rather than guessed at.
TEXT_SUFFIXES = frozenset(
    {".md", ".yml", ".yaml", ".sh", ".py", ".txt", ".json", ".toml", ".cfg", ".ini", ".ps1"}
)

# Manifest sections whose value is a flat list of path entries.
LIST_SECTIONS = ("engine", "template", "exclude", "seed_skill", "retired")

_ENTRY_RE = re.compile(r"^\s*-\s+(.+?)\s*$")
# YAML ends a scalar at a `#` preceded by whitespace. The lite reader has to do
# the same or an entry with a trailing note — `.gitattributes  # forces LF` —
# reaches a caller as a path that does not exist. `test_engine_lib` pins the two
# readers together precisely so this cannot drift back.
_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def repo_root() -> Path:
    """The GIT REPO root — the parent of `scripts/`, resolved from this file.

    Not to be confused with `_system/scripts/_common.py::repo_root`, which
    despite the name returns the ZETTELKASTEN BASE (`<repo>/zettelkasten`, or
    whatever `MINDER_MEMORY_BASE` points at). The two live in separate `sys.path` worlds
    and no module imports both, so the collision is latent rather than live —
    but a future module that imported the wrong one would get a path one level
    off and no error. If you are in `_system/scripts/`, you want that one.
    """
    return Path(__file__).resolve().parents[2]


def load_manifest(root: Path | None = None) -> dict:
    """Parse the whole manifest with PyYAML.

    `encoding="utf-8"` is not optional: the manifest's comments carry em-dashes,
    and python on Windows would otherwise decode the file through the ANSI code
    page and either raise or corrupt them.
    """
    import yaml  # imported lazily so `read_section_lite` callers need no PyYAML

    p = (root or repo_root()) / ".engine-manifest.yml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def read_section_lite(manifest_path: Path, section: str) -> list[str]:
    """Return one list-shaped manifest section without importing PyYAML.

    Handles exactly the shape the manifest uses for `engine:` / `template:` /
    `exclude:` / `seed_skill:` — a top-level key followed by indented `- entry`
    lines, with `#` comments and blank lines interleaved. Anything richer is out
    of scope by design; use `load_manifest` for that.
    """
    if section not in LIST_SECTIONS:
        raise ValueError(f"read_section_lite: {section!r} is not a list-shaped section")
    out: list[str] = []
    current: str | None = None
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t", "-")):
            current = line.split(":", 1)[0].strip()
            continue
        if current != section:
            continue
        m = _ENTRY_RE.match(line)
        if m:
            value = _INLINE_COMMENT_RE.sub("", m.group(1)).strip()
            if value:
                out.append(value.strip('"').strip("'"))
    return out


def expand_paths(
    root: Path,
    entries: list[str] | None,
    *,
    suffixes: frozenset[str] | None = TEXT_SUFFIXES,
) -> set[Path]:
    """Expand manifest entries into the concrete files they cover.

    A trailing `/` entry expands recursively; a bare entry is one file. An entry
    naming a path that does not exist yet is skipped silently — the release
    copier is the tool that errors on a missing manifested path, and a gate
    should not duplicate that judgement.

    `suffixes=None` returns every file regardless of kind (for gates that read
    bytes, such as the CRLF check).
    """
    out: set[Path] = set()
    for entry in entries or []:
        p = root / entry.rstrip("/")
        if p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and (suffixes is None or sub.suffix in suffixes):
                    out.add(sub)
        elif p.is_file():
            if suffixes is None or p.suffix in suffixes:
                out.add(p)
    return out


def scan_targets(
    root: Path,
    manifest: dict,
    *,
    suffixes: frozenset[str] | None = TEXT_SUFFIXES,
    include_template: bool = True,
) -> list[Path]:
    """Every file that actually ships, with `exclude:` subtracted.

    This is what a gate means by "engine surface": the union of `engine:` and
    `template:`, minus everything `exclude:` carves back out. Engine entries are
    frequently directory globs (`scripts/`) with owner-specific files excluded
    beneath them, so skipping the subtraction makes a gate fire on a file that
    can never reach a friend.
    """
    sections = ["engine"] + (["template"] if include_template else [])
    targets: set[Path] = set()
    for section in sections:
        targets |= expand_paths(root, manifest.get(section, []), suffixes=suffixes)
    targets -= expand_paths(root, manifest.get("exclude", []), suffixes=suffixes)
    return sorted(targets)
