#!/usr/bin/env python3
"""Portability gate — makes `ENGINE_DOCTRINE §3.9` executable.

§3.9 requires every shipped artefact to behave identically on Windows (Git
Bash), macOS (system **bash 3.2**) and Linux. Until this gate existed the rule
was enforced by human memory, and memory does not scale: a friend's Windows
clone was found running an engine update that silently applied nothing, an
installer that aborted halfway leaving residue, and a release gate that could
not start at all — every one of them a violation of a rule already written down.

What it does. For every file the manifest actually ships (`engine:` +
`template:`, minus `exclude:`), it looks for the specific constructs §3.9
forbids and reports each with the reason and the correct replacement.

Where it looks. Rules match against **code**, never prose: shell `#` comments,
python `#` comments and python docstrings are blanked before matching, and
markdown is scanned inside fenced code blocks only. A doc that *describes* a
banned construct — which the doctrine and the contributor guide both do,
deliberately — is therefore never a finding.

Two escapes, both loud, never silent:

  * an inline `portability-ok: <reason>` comment on the offending line or the
    line directly above it;
  * a row in `scripts/portability-allowlist.txt` — `path<TAB>rule<TAB>reason`,
    the reason column mandatory.

Usage:
  python3 scripts/check_portability.py              # enforce: exit 1 on any finding
  python3 scripts/check_portability.py --report     # list findings, exit 0
  python3 scripts/check_portability.py --rules      # describe every rule
  python3 scripts/check_portability.py --path X     # scan one path (repo-relative)

Run by CI and by `release_engine.py`, alongside the personal-data gate. A
release cannot ship a §3.9 violation.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.manifest import load_manifest, repo_root, scan_targets  # noqa: E402
from lib.portable import configure_stdout  # noqa: E402

ALLOWLIST_FILENAME = "scripts/portability-allowlist.txt"

# Fence languages whose body is shell. Unlabelled fences are included: in engine
# docs they are overwhelmingly shell snippets, and a false positive there costs
# one allowlist row while a false negative costs a friend's Windows install.
SHELL_FENCE_LANGS = frozenset({"", "bash", "sh", "shell", "console", "zsh"})
PYTHON_FENCE_LANGS = frozenset({"python", "python3", "py"})

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([A-Za-z0-9_+-]*)\s*$")
_OK_RE = re.compile(r"portability-ok:")


class Rule:
    """One forbidden construct: how to spot it, and what to write instead."""

    __slots__ = ("rule_id", "kind", "why", "fix", "_matcher")

    def __init__(self, rule_id: str, kind: str, why: str, fix: str, matcher) -> None:
        self.rule_id = rule_id
        self.kind = kind  # "sh" | "py" | "file"
        self.why = why
        self.fix = fix
        self._matcher = matcher

    def scan(self, ctx: "LineCtx") -> list[tuple[int, str]]:
        return self._matcher(ctx)


class Finding:
    __slots__ = ("path", "line", "rule", "snippet")

    def __init__(self, path: str, line: int, rule: Rule, snippet: str) -> None:
        self.path = path
        self.line = line
        self.rule = rule
        self.snippet = snippet


class LineCtx:
    """One scannable region: real line numbers, original text, and code text.

    `code` is the line with comments and docstrings blanked out. Every rule
    matches `code` and reports `text`, so a rule can never fire on prose that
    merely names the construct it hunts — which is what engine docs do on
    purpose.
    """

    __slots__ = ("path", "rows", "code_text", "raw")

    def __init__(self, path: str, rows: list[tuple[int, str, str]], raw: bytes = b"") -> None:
        self.path = path
        self.rows = rows
        self.code_text = "\n".join(c for _, _, c in rows)
        self.raw = raw


# ---------------------------------------------------------------------------
# Code extraction — the one place that decides what counts as code
# ---------------------------------------------------------------------------


def _shell_code(line: str) -> str:
    """Blank a trailing `#` comment, leaving the line's code prefix.

    Only strips a `#` that starts the line or follows whitespace outside quotes
    — enough to keep a rule from firing on its own explanatory comment, without
    pretending to be a shell parser.
    """
    in_single = in_double = False
    for i, ch in enumerate(line):
        prev = line[i - 1] if i else ""
        if ch == "'" and not in_double and prev != "\\":
            in_single = not in_single
        elif ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


_TRIPLE_RE = re.compile(r'"""|\'\'\'')


def _python_code_rows(lines: list[str], start: int = 1) -> list[tuple[int, str, str]]:
    """Blank python `#` comments and every line inside a triple-quoted string.

    Docstrings are where engine modules explain the very constructs this gate
    forbids; without blanking them, half the findings would be the explanations.
    Single-line triple-quoted strings are blanked on their own line only.
    """
    rows: list[tuple[int, str, str]] = []
    delim: str | None = None
    for offset, text in enumerate(lines):
        no = start + offset
        code = text
        if delim is None:
            m = _TRIPLE_RE.search(text)
            if m:
                token = m.group(0)
                rest = text[m.end() :]
                code = text[: m.start()]
                if token in rest:
                    # Opens and closes on the same line — keep the prefix only.
                    tail = rest.split(token, 1)[1]
                    code = text[: m.start()] + " " * (len(text) - len(tail) - m.start()) + tail
                else:
                    delim = token
            code = _shell_code(code)  # python uses `#` for comments too
        else:
            if delim in text:
                code = text.split(delim, 1)[1]
                delim = None
                code = _shell_code(code)
            else:
                code = ""
        rows.append((no, text, code))
    return rows


def _shell_code_rows(lines: list[str], start: int = 1) -> list[tuple[int, str, str]]:
    return [(start + i, t, _shell_code(t)) for i, t in enumerate(lines)]


# ---------------------------------------------------------------------------
# Matcher helpers
# ---------------------------------------------------------------------------


def regex_matcher(pattern: str, *, absent_in_file: str | None = None):
    """Flag every code line matching `pattern`.

    `absent_in_file` suppresses the whole rule for a file whose code already
    contains that literal — the way a file opts in to doing the thing correctly
    once (setting `MSYS_NO_PATHCONV`, sourcing `lib/git.sh`) rather than
    annotating every line.
    """
    rx = re.compile(pattern)

    def _match(ctx: LineCtx) -> list[tuple[int, str]]:
        if absent_in_file and absent_in_file in ctx.code_text:
            return []
        return [(no, text) for no, text, code in ctx.rows if rx.search(code)]

    return _match


_GIT_REF_SUBCOMMANDS = ("cat-file", "ls-tree", "archive")
_GIT_REF_SHOW = re.compile(r"\bgit\b[^\n]*\bshow\b")


def _msys_refspec(ctx: LineCtx) -> list[tuple[int, str]]:
    """Flag a `git` call passing a `<ref>:<path>` argument without MSYS_NO_PATHCONV.

    MSYS rewrites such an argument on Git Bash — the colon becomes `;` and the
    slash a backslash — so every dotfile path fails as an invalid object name.
    A caller that reads that failure as "absent upstream" then reports success
    having synced nothing.
    """
    if any(tok in ctx.code_text for tok in ("MSYS_NO_PATHCONV", "git_ref_has_path", "git_ref_read_path")):
        return []
    hits: list[tuple[int, str]] = []
    for no, text, code in ctx.rows:
        if "git" not in code:
            continue
        if not (any(sub in code for sub in _GIT_REF_SUBCOMMANDS) or _GIT_REF_SHOW.search(code)):
            continue
        for token in re.split(r"\s+", code):
            token = token.strip("\"'")
            if not token or token.startswith("-") or "://" in token:
                continue
            body = token.split("=", 1)[-1]
            if ":" in body and not body.endswith(":"):
                hits.append((no, text))
                break
    return hits


# Porcelain forms that emit a LIST of paths, which git octal-escapes under the
# default `core.quotePath=true`. `ls-files --error-unmatch -- <path>` is a
# membership QUERY against a pathspec the caller already holds — nothing is
# parsed out of its output — so it is deliberately not in this set.
_QUOTEPATH_CMDS = (
    "status --porcelain",
    "diff --cached --name-only",
    "diff --name-only",
)


def _quotepath(ctx: LineCtx) -> list[tuple[int, str]]:
    """Flag porcelain path listing that git will octal-escape.

    With `core.quotePath=true` a Cyrillic filename comes back as `"\\320\\222…"`.
    A caller that only strips the wrapping quotes hands that literal string to
    `git add`, which fails — losing a whole tick's commit over one filename.
    `-z` output is exempt: NUL-delimited porcelain is never quoted.
    """
    if "git_status_paths" in ctx.code_text or "git_staged_paths" in ctx.code_text:
        return []
    hits: list[tuple[int, str]] = []
    for no, text, code in ctx.rows:
        if "git" not in code or not any(cmd in code for cmd in _QUOTEPATH_CMDS):
            continue
        if "core.quotepath=false" in code.lower() or re.search(r"(^|\s)-z(\s|$)", code):
            continue
        hits.append((no, text))
    return hits


_HEREDOC_START = re.compile(r"<<-?\s*'?([A-Za-z_][A-Za-z0-9_]*)'?\s*$")


def python_heredocs(rows: list[tuple[int, str, str]]) -> list[tuple[int, str, list[str]]]:
    """Every `python3 … <<TERM` block in a shell region.

    Returns `(header_line_no, header_text, body_lines)`. One owner of "what is a
    python heredoc", because two things need the answer: the CRLF rule below,
    and `scan_file`, which runs the PYTHON rules over the body. Without the
    second, python embedded in a shell script was scanned only by shell rules —
    so an `open()` with no `encoding=` inside a migration's heredoc was invisible
    to a gate whose whole purpose is catching exactly that.
    """
    out: list[tuple[int, str, list[str]]] = []
    idx = 0
    while idx < len(rows):
        no, text, code = rows[idx]
        m = _HEREDOC_START.search(code)
        if not m or not re.search(r"\bpython3?\b", code):
            idx += 1
            continue
        terminator = m.group(1)
        body: list[str] = []
        jdx = idx + 1
        while jdx < len(rows) and rows[jdx][1].strip() != terminator:
            body.append(rows[jdx][1])
            jdx += 1
        out.append((no, text, body))
        idx = jdx + 1
    return out


def _crlf_heredoc(ctx: LineCtx) -> list[tuple[int, str]]:
    """Flag a python heredoc that prints lines a shell will read.

    On Git Bash python's text-mode stdout writes `\\r\\n`, so every value the
    shell reads carries a trailing `\\r` and every path built from it fails.
    The heredoc must reconfigure stdout or use `lib.portable.emit_lines`.

    A heredoc whose python writes files rather than stdout is not a finding:
    the rule looks for `print(`.
    """
    hits: list[tuple[int, str]] = []
    for no, text, body in python_heredocs(ctx.rows):
        blob = "\n".join(body)
        if re.search(r"\bprint\s*\(", blob) and "newline=" not in blob and "emit_lines" not in blob:
            hits.append((no, text))
    return hits


# Segment separators that start a fresh command in a shell line.
_CMD_SPLIT_RE = re.compile(r"\|\||&&|[|;&]|\$\(|`|\bthen\b|\bdo\b|\belse\b")
# A script named in command position by an unambiguous invocation form: `./x.sh`
# or `"$DIR/y.py"`. A BARE relative path (`scripts/x.sh`) is deliberately not
# matched — in prose and in fenced examples it is far more often a reference to
# a file than an invocation of it, and flagging it produced ~90 findings of
# which one was real. One precise flag is worth more than ten routine ones; the
# bare form is caught by review, not by this gate.
_SCRIPT_TOKEN_RE = re.compile(
    r"^\"?(?:\./|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/)[^\s\"']*\.(?:sh|py)\"?$"
)
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _exec_bit(ctx: LineCtx) -> list[tuple[int, str]]:
    """Flag a script invoked by path in COMMAND position.

    Windows checkouts carry no executable bit, so `./x.sh` and `"$DIR/y.py"`
    used as the command fail. The same token as an ARGUMENT — `python3
    "$DIR/y.py"`, `[ -f "$d/z.py" ]` — is correct and must not be flagged, so
    this walks command positions rather than matching the token anywhere.
    """
    hits: list[tuple[int, str]] = []
    for no, text, code in ctx.rows:
        stripped = code.strip()
        if not stripped:
            continue
        for segment in _CMD_SPLIT_RE.split(stripped):
            parts = segment.split()
            while parts and _ASSIGNMENT_RE.match(parts[0]):
                parts = parts[1:]
            if parts and _SCRIPT_TOKEN_RE.match(parts[0]):
                hits.append((no, text))
                break
    return hits


# `ensure_ascii=False` is only dangerous when the result reaches a std stream.
# Written to a file opened with `encoding="utf-8"`, or built into a string for an
# assertion, it is correct and common — flagging those produced ~98 findings of
# which none were real.
_STREAM_SINKS = ("print(", "sys.stdout", "sys.stderr")


def _entrypoint_streams(ctx: LineCtx) -> list[tuple[int, str]]:
    """Flag a runnable module that never configures its std streams.

    Uniform rather than clever: a targeted rule only caught the modules whose
    non-ASCII output was obvious from a keyword (`ensure_ascii=False`), and
    missed the ones that simply write markdown containing an em-dash. Every
    entrypoint configures, and the call is a no-op on POSIX — so the rule costs
    one line per script and removes a whole failure class.
    """
    # Test modules end in `unittest.main()`; their output belongs to the test
    # runner, which owns its own streams. The rule is about engine entrypoints
    # that emit owner text.
    if "/tests/" in ctx.path or "unittest.main()" in ctx.code_text:
        return []
    if '__name__ == "__main__"' not in ctx.code_text:
        return []
    if any(tok in ctx.code_text
           for tok in ("configure_std_streams", "configure_stdout", "emit_lines")):
        return []
    for no, text, code in ctx.rows:
        if '__name__ == "__main__"' in code:
            return [(no, text)]
    return []


def _nonascii_to_stream(ctx: LineCtx) -> list[tuple[int, str]]:
    if "configure_std" in ctx.code_text or "emit_lines" in ctx.code_text:
        return []
    hits: list[tuple[int, str]] = []
    for i, (no, text, code) in enumerate(ctx.rows):
        if "ensure_ascii" not in code or "False" not in code:
            continue
        # The sink can sit a line or two above on a wrapped call.
        window = "\n".join(c for _, _, c in ctx.rows[max(0, i - 2) : i + 2])
        if any(sink in window for sink in _STREAM_SINKS):
            hits.append((no, text))
    return hits


_OPEN_BINARY = re.compile(r"""["'][rwax]?\+?b\+?["']""")


def _py_encoding(call: str, *, attribute_only: bool = False):
    """Flag a text-mode file call that inherits the platform's ANSI code page.

    `Path.read_text()` / `open()` without `encoding=` decode through
    `locale.getpreferredencoding()`, which is cp1252 on a stock Windows box —
    so any non-ASCII byte in engine data either raises or mojibakes.

    `attribute_only` restricts the rule to `something.read_text(` — the
    unambiguous `Path` method. A module-level helper that happens to share the
    name (the test fixtures define a correct `write_text(path, text)`) is a
    different function; the gate still checks that helper's own body, where the
    real call lives.
    """
    prefix = r"\." if attribute_only else r"(?<!\.)\b"
    rx = re.compile(rf"{prefix}{re.escape(call)}\s*\(")

    def _match(ctx: LineCtx) -> list[tuple[int, str]]:
        hits: list[tuple[int, str]] = []
        for i, (no, text, code) in enumerate(ctx.rows):
            m = rx.search(code)
            if not m:
                continue
            window = _call_span(ctx.rows, i, code.index("(", m.start()))
            if "encoding=" in window:
                continue
            if call == "open" and _OPEN_BINARY.search(window):
                continue
            hits.append((no, text))
        return hits

    return _match


_CALL_SPAN_MAX_LINES = 60


def _call_span(rows: list[tuple[int, str, str]], row_index: int, open_col: int) -> str:
    """Text of one call, from its `(` to the matching `)`, across lines.

    A fixed line window is the wrong unit: a `write_text(...)` whose argument is
    a dozen concatenated string literals puts `encoding=` well past any window,
    and the gate would report a call that is already correct. Balancing parens
    is the only reading that matches how the call is actually written.
    """
    depth = 0
    out: list[str] = []
    for _, _, code in rows[row_index : row_index + _CALL_SPAN_MAX_LINES]:
        segment = code[open_col:] if not out else code
        open_col = 0
        out.append(segment)
        for ch in segment:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
                if depth == 0:
                    return "\n".join(out)
    return "\n".join(out)


def _crlf_bytes(ctx: LineCtx) -> list[tuple[int, str]]:
    """Flag a shipped executable script stored with CRLF line endings.

    A CRLF `.sh` from a Windows checkout breaks bash (`$'\\r': command not
    found`); a CRLF `.py` breaks its shebang. `.gitattributes` forces LF on
    checkout, but a file committed with literal CRLF bytes defeats it.
    """
    if b"\r\n" not in ctx.raw:
        return []
    return [(1, "file contains CRLF line endings")]


# ---------------------------------------------------------------------------
# The rule set
# ---------------------------------------------------------------------------

RULES: tuple[Rule, ...] = (
    # -- shell: bash 4 constructs absent from macOS's system bash 3.2 --------
    Rule(
        "bash4-mapfile", "sh",
        "`mapfile` / `readarray` are bash 4.0+; macOS ships bash 3.2",
        "read in a loop: `while IFS= read -r x; do arr+=(\"$x\"); done < <(...)`",
        regex_matcher(r"\b(mapfile|readarray)\b"),
    ),
    Rule(
        "bash4-assoc", "sh",
        "associative arrays are bash 4.0+; macOS ships bash 3.2",
        "use a python3 helper, or parallel indexed arrays",
        regex_matcher(r"\b(declare|local|typeset)\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*A\b"),
    ),
    Rule(
        "bash4-case-mod", "sh",
        "`${x^^}` / `${x,,}` case modification is bash 4.0+",
        "`tr '[:lower:]' '[:upper:]'`, or do it in python3",
        regex_matcher(r"\$\{[A-Za-z_][A-Za-z0-9_]*[^}]*(\^\^|,,)[^}]*\}"),
    ),
    # -- shell: GNU/BSD command differences ----------------------------------
    Rule(
        "sed-inplace", "sh",
        "`sed -i` needs an argument on BSD/macOS and must not have one on GNU",
        "`sed -i.bak ...` then remove the `.bak`, or rewrite the file in python3",
        regex_matcher(r"\bsed\s+(?:-[A-Za-z]+\s+)*-i(?![.\w])"),
    ),
    Rule(
        "readlink-f", "sh",
        "`readlink -f` does not exist on macOS",
        "resolve in python3 (`Path(...).resolve()`), or `cd \"$(dirname \"$x\")\" && pwd`",
        regex_matcher(r"\breadlink\s+(-[A-Za-z]+\s+)*-[A-Za-z]*f\b"),
    ),
    Rule(
        "stat-format", "sh",
        "`stat -c` is GNU-only and `stat -f` is BSD-only",
        "read the attribute in python3, or try both forms in sequence",
        regex_matcher(r"\bstat\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*[cf]\b"),
    ),
    Rule(
        "grep-perl", "sh",
        "`grep -P` is GNU-only; macOS BSD grep has no PCRE",
        "`grep -E` with a POSIX ERE, or match in python3",
        regex_matcher(r"\bgrep\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*P\b"),
    ),
    Rule(
        "md5-split", "sh",
        "the checksum binary is `md5sum` on GNU and `md5` on macOS",
        "hash in python3 (`hashlib`)",
        regex_matcher(r"(?:^|[\s|;&(`$])(md5sum|md5)(?=\s)"),
    ),
    # -- shell: git primitives with an owner in lib/git.sh -------------------
    Rule(
        "git-abbrev-ref", "sh",
        "`rev-parse --abbrev-ref HEAD` prints the literal string `HEAD` on a "
        "detached HEAD and exits 0, so an `|| fallback` never fires",
        "`git_current_branch` from `scripts/lib/git.sh` (empty + non-zero when detached)",
        regex_matcher(r"rev-parse\s+(?:--\S+\s+)*--abbrev-ref"),
    ),
    Rule(
        "git-quotepath", "sh",
        "porcelain path listing octal-escapes non-ASCII under the default "
        "`core.quotePath=true`, and the escaped string is not a valid pathspec",
        "`git_status_paths` / `git_staged_paths` from `scripts/lib/git.sh`, or add "
        "`-c core.quotepath=false` (or use `-z`)",
        _quotepath,
    ),
    Rule(
        "git-msys-refspec", "sh",
        "MSYS rewrites a `<ref>:<path>` argument on Git Bash, breaking every "
        "dotfile path",
        "`git_ref_has_path` / `git_ref_read_path` from `scripts/lib/git.sh`, or set "
        "`MSYS_NO_PATHCONV=1` on the invocation",
        _msys_refspec,
    ),
    # -- shell: process + filesystem ----------------------------------------
    Rule(
        "exec-bit", "sh",
        "Windows checkouts have no executable bit, so invoking a script by path fails",
        "call it through its interpreter: `bash x.sh` / `python3 x.py`",
        _exec_bit,
    ),
    Rule(
        "crlf-heredoc", "sh",
        "python's text-mode stdout emits CRLF on Git Bash, so every line the "
        "shell reads carries a trailing `\\r`",
        "`sys.stdout.reconfigure(newline=\"\\n\", encoding=\"utf-8\")`, or "
        "`lib.portable.emit_lines`",
        _crlf_heredoc,
    ),
    Rule(
        "bare-symlink", "sh",
        "Git Bash does not create real symlinks unless "
        "`MSYS=winsymlinks:nativestrict` is set; `ln -s` fails or writes a stub file",
        "guard the script with the Git-Bash re-exec used by "
        "`integrations/claude-code/install.sh`",
        regex_matcher(r"\bln\s+(-[A-Za-z]+\s+)*-[A-Za-z]*s\b", absent_in_file="winsymlinks"),
    ),
    # -- python -------------------------------------------------------------
    Rule(
        "py-exec-bit", "py",
        "invoking a `.sh` from python fails on Windows (`WinError 193`) — there "
        "is no executable bit and `.sh` is not a Win32 application",
        "run the python entrypoint via `sys.executable`, or `['bash', path]`",
        regex_matcher(r"subprocess\.(?:run|call|Popen|check_call|check_output)\s*\(\s*\[[^\]]*\.sh[\"']"),
    ),
    Rule(
        "py-encoding-read-text", "py",
        "`read_text()` without `encoding=` decodes through the platform code page "
        "(cp1252 on Windows)",
        "`read_text(encoding=\"utf-8\")`, or `lib.portable.read_text`",
        _py_encoding("read_text", attribute_only=True),
    ),
    Rule(
        "py-encoding-write-text", "py",
        "`write_text()` without `encoding=` encodes through the platform code page",
        "`write_text(text, encoding=\"utf-8\")`, or `lib.portable.write_text`",
        _py_encoding("write_text", attribute_only=True),
    ),
    Rule(
        "py-encoding-open", "py",
        "text-mode `open()` without `encoding=` decodes through the platform code page",
        "`open(path, encoding=\"utf-8\")` (binary modes and `os.open` are exempt)",
        _py_encoding("open"),
    ),
    Rule(
        "py-abbrev-ref", "py",
        "`rev-parse --abbrev-ref HEAD` prints the literal string `HEAD` on a detached HEAD",
        "`git symbolic-ref --short -q HEAD` — empty output, non-zero exit when detached",
        regex_matcher(r"--abbrev-ref"),
    ),
    Rule(
        "py-path-endswith", "py",
        "`str(path).endswith(\"a/b\")` never holds on Windows, where the separator is `\\`",
        "compare `Path` objects, or `path.as_posix().endswith(...)`",
        regex_matcher(r"str\s*\([^)]*\)\s*\.endswith\s*\(\s*[\"'][^\"']*/"),
    ),
    Rule(
        "py-entrypoint-unconfigured-streams", "py",
        "an engine entrypoint writes owner text to stdout; without configuring "
        "the stream, python encodes it through the platform code page and a "
        "single non-ASCII character raises `UnicodeEncodeError` on Windows",
        "`configure_std_streams()` as the first statement of `main()` — "
        "from `lib.portable` under `scripts/`, from `_common` under `_system/scripts/`",
        _entrypoint_streams,
    ),
    Rule(
        "py-write-text-newline", "py",
        "`Path.write_text(newline=...)` exists only from Python 3.10; the engine "
        "runs on 3.9, where the call raises `TypeError` before writing anything",
        "`lib.portable.write_text_utf8(path, text)` under `scripts/`, or "
        "`open(path, \"w\", encoding=\"utf-8\", newline=\"\")` — the same LF bytes on every version",
        regex_matcher(r"\.write_text\([^)]*\bnewline\s*=|^\s*newline\s*=\s*[\"']"),
    ),
    Rule(
        "py-stdin-unconfigured", "py",
        "`sys.stdin` decodes through the platform code page, so a Cyrillic path "
        "read from a pipe raises `UnicodeDecodeError` on Windows",
        "`lib.portable.configure_stdin()` (or `configure_std_streams()`) before the first read",
        regex_matcher(
            r"\bsys\.stdin\b",
            absent_in_file="configure_std",
        ),
    ),
    Rule(
        "py-nonascii-stream-unconfigured", "py",
        "writing deliberately non-ASCII output (`ensure_ascii=False`) to a std "
        "stream encodes it through the platform code page, which raises "
        "`UnicodeEncodeError` on Windows",
        "`lib.portable.configure_stdout()` before the first write, or `emit_lines`",
        _nonascii_to_stream,
    ),
    Rule(
        "py-stdout-print-for-shell", "py",
        "a helper whose stdout a shell parses must force LF, or Git Bash inserts CRLF",
        "`lib.portable.emit_lines`, or `configure_stdout()` before printing",
        regex_matcher(
            r"^\s*print\s*\(\s*f?[\"'][^\"']*\\t",
            absent_in_file="emit_lines",
        ),
    ),
    # -- any shipped file ---------------------------------------------------
    Rule(
        "crlf-on-disk", "file",
        "a script committed with CRLF bytes breaks bash and python on checkout",
        "store LF; `.gitattributes` enforces it for new files",
        _crlf_bytes,
    ),
)

RULES_BY_KIND: dict[str, tuple[Rule, ...]] = {
    kind: tuple(r for r in RULES if r.kind == kind) for kind in ("sh", "py", "file")
}

CRLF_CHECKED_SUFFIXES = frozenset({".sh", ".py", ".ps1"})

# Rules meaningful on a bare inline code span in prose. `exec-bit` qualifies
# because `./x.sh` is unambiguous in isolation; the others need surrounding
# command context to judge and would only produce noise here.
INLINE_MD_RULES = tuple(r for r in RULES if r.rule_id == "exec-bit")

# This file states every forbidden construct as a literal pattern and explains
# each one, so scanning it finds only its own rule table. The personal-data gate
# excludes itself for the identical reason.
SELF_EXEMPT = frozenset({"scripts/check_portability.py"})


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _inline_code_rows(lines: list[str], *, skip: set[int]) -> list[tuple[int, str, str]]:
    """Prose lines reduced to their inline `code spans` only.

    A doc that says «run `./install.sh`» is giving a friend an instruction, and
    the instruction is wrong on Windows just as it would be inside a fence.
    Scanning only fences left that hole open, so inline spans are scanned too —
    with a deliberately narrow rule set (`INLINE_MD_RULES`), because a span is
    a fragment and most rules need a whole command line to judge.
    """
    rows: list[tuple[int, str, str]] = []
    for no, text in enumerate(lines, start=1):
        if no in skip:
            continue
        spans = _INLINE_CODE_RE.findall(text)
        if spans:
            rows.append((no, text, " ; ".join(spans)))
    return rows


def _fenced_regions(lines: list[str]) -> list[tuple[str, int, list[str]]]:
    """Split markdown into fenced code regions: `(lang, first_line_no, body)`."""
    regions: list[tuple[str, int, list[str]]] = []
    fence: str | None = None
    lang = ""
    start = 0
    body: list[str] = []
    for no, text in enumerate(lines, start=1):
        m = _FENCE_RE.match(text)
        if fence is None:
            if m:
                fence, lang, start, body = m.group(1)[:3], m.group(2).lower(), no + 1, []
            continue
        if m and m.group(1).startswith(fence):
            regions.append((lang, start, body))
            fence, lang, body = None, "", []
            continue
        body.append(text)
    if fence is not None and body:
        regions.append((lang, start, body))
    return regions


def scan_file(path: Path, rel: str) -> list[Finding]:
    if rel in SELF_EXEMPT:
        return []
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    lines = text.splitlines()
    findings: list[Finding] = []

    def run(rules: tuple[Rule, ...], ctx: LineCtx) -> None:
        for rule in rules:
            for no, snippet in rule.scan(ctx):
                findings.append(Finding(rel, no, rule, snippet.strip()))

    def run_shell_region(rows: list[tuple[int, str, str]]) -> None:
        """Shell rules over the region, PYTHON rules over any heredoc inside it.

        Python embedded in a shell script is still python — a migration's
        heredoc reading a file through the platform code page is the same defect
        as a module doing it, and skipping it would leave the gate blind exactly
        where migrations do their work.
        """
        run(RULES_BY_KIND["sh"], LineCtx(rel, rows))
        for header_no, _header, body in python_heredocs(rows):
            if body:
                run(RULES_BY_KIND["py"], LineCtx(rel, _python_code_rows(body, header_no + 1)))

    suffix = path.suffix
    if suffix == ".sh":
        run_shell_region(_shell_code_rows(lines))
    elif suffix == ".py":
        run(RULES_BY_KIND["py"], LineCtx(rel, _python_code_rows(lines)))
    elif suffix == ".md":
        fenced: set[int] = set()
        for lang, start, body in _fenced_regions(lines):
            if not body:
                continue
            fenced.update(range(start, start + len(body)))
            if lang in SHELL_FENCE_LANGS:
                run_shell_region(_shell_code_rows(body, start))
            elif lang in PYTHON_FENCE_LANGS:
                run(RULES_BY_KIND["py"], LineCtx(rel, _python_code_rows(body, start)))
        run(INLINE_MD_RULES, LineCtx(rel, _inline_code_rows(lines, skip=fenced)))

    if suffix in CRLF_CHECKED_SUFFIXES:
        run(RULES_BY_KIND["file"], LineCtx(rel, [], raw=raw))

    return [f for f in findings if not _suppressed_inline(f, lines)]


def _suppressed_inline(f: Finding, lines: list[str]) -> bool:
    """True when the offending line, or the line above it, carries `portability-ok:`."""
    for idx in (f.line - 1, f.line - 2):
        if 0 <= idx < len(lines) and _OK_RE.search(lines[idx]):
            return True
    return False


def load_allowlist(root: Path) -> dict[tuple[str, str], str]:
    """`(path, rule) -> reason`. A row without a reason is itself an error."""
    p = root / ALLOWLIST_FILENAME
    out: dict[tuple[str, str], str] = {}
    if not p.exists():
        return out
    for lineno, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [c.strip() for c in raw.split("\t") if c.strip()]
        if len(parts) < 3:
            raise SystemExit(
                f"{ALLOWLIST_FILENAME}:{lineno}: need `path<TAB>rule<TAB>reason`, got {line!r}"
            )
        out[(parts[0], parts[1])] = "\t".join(parts[2:])
    return out


def collect(root: Path, targets: list[Path]) -> list[Finding]:
    allowlist = load_allowlist(root)
    findings: list[Finding] = []
    for path in targets:
        rel = path.relative_to(root).as_posix()
        for f in scan_file(path, rel):
            if (f.path, f.rule.rule_id) in allowlist:
                continue
            findings.append(f)
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Portability gate for ENGINE_DOCTRINE §3.9")
    ap.add_argument("--report", action="store_true", help="list findings but exit 0")
    ap.add_argument("--rules", action="store_true", help="describe every rule and exit")
    ap.add_argument("--path", action="append", default=[], help="scan this repo-relative path only")
    args = ap.parse_args(argv)

    configure_stdout()

    if args.rules:
        for rule in RULES:
            print(f"{rule.rule_id}  [{rule.kind}]\n  why: {rule.why}\n  fix: {rule.fix}\n")
        return 0

    root = repo_root()
    if args.path:
        targets: list[Path] = []
        for entry in args.path:
            p = root / entry
            if p.is_dir():
                targets.extend(sorted(x for x in p.rglob("*") if x.is_file()))
            elif p.is_file():
                targets.append(p)
    else:
        targets = scan_targets(root, load_manifest(root))

    findings = collect(root, targets)

    if not findings:
        print(f"portability: clean — {len(targets)} shipped file(s), {len(RULES)} rule(s)")
        return 0

    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule.rule_id, []).append(f)

    for rule_id in sorted(by_rule):
        group = by_rule[rule_id]
        rule = group[0].rule
        print(f"\n[{rule_id}]  {len(group)} finding(s)")
        print(f"  why: {rule.why}")
        print(f"  fix: {rule.fix}")
        for f in group:
            print(f"    {f.path}:{f.line}: {f.snippet[:140]}")

    print(
        f"\nportability: {len(findings)} finding(s) across {len(by_rule)} rule(s) "
        f"in {len(targets)} shipped file(s)"
    )
    print(
        "Suppress a justified one with an inline `portability-ok: <reason>` comment, "
        f"or a `path<TAB>rule<TAB>reason` row in {ALLOWLIST_FILENAME}."
    )
    return 0 if args.report else 1


if __name__ == "__main__":
    sys.exit(main())
