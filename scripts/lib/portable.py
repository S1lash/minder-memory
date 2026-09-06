#!/usr/bin/env python3
"""Cross-platform I/O primitives — the one place the engine gets stdout right.

Why this exists. Several engine shell scripts parse a python helper's stdout as
a newline-separated list (manifest paths, migration names, batch ids). On
Windows Git Bash, python's default text-mode stdout translates ``\\n`` to
``\\r\\n``, so every value the shell reads carries a trailing ``\\r``. The shell
then passes that literal byte to ``git``, which fails on every path — and the
script, seeing per-path failures it treats as "absent upstream", reports success
having done nothing. That is exactly the silent-no-op class this module removes:
one function, used by every producer, instead of the same three lines remembered
correctly at eight call sites.

The same applies to encoding: python on Windows defaults stdout to the ANSI code
page (cp1252), so a Cyrillic path or an em-dash raises or mojibakes on the way
out. Both are fixed together because both are properties of the same stream.

Usage — in a script whose stdout a shell reads::

    from lib.portable import emit_lines
    emit_lines(p.rstrip("/") for p in manifest["engine"])

Usage — inside a `python3 - <<'PY'` heredoc, where imports are awkward::

    import sys
    sys.stdout.reconfigure(newline="\\n", encoding="utf-8")

`configure_stdout()` is the importable form of that same call, and
`check_portability.py` accepts either as proof the heredoc is safe.

Nothing here is Windows-specific in effect: on POSIX every call is a no-op, so
there is never a reason for a caller to branch on platform.
"""

from __future__ import annotations

import sys
from typing import IO, Iterable

# The `_utf8` suffix is not decoration: `read_text` / `write_text` would shadow
# the `Path` methods they replace, and a reader — or the portability gate —
# could not tell which one a call site meant.
__all__ = [
    "configure_stdout",
    "configure_stdin",
    "configure_std_streams",
    "configure_stream",
    "emit_lines",
    "read_text_utf8",
    "write_text_utf8",
]


def configure_stream(stream: IO[str]) -> None:
    """Force LF line endings and UTF-8 on a text stream, idempotently.

    `reconfigure` exists on `io.TextIOWrapper` (CPython 3.7+). A stream that
    does not support it — a `StringIO` in a test, a redirected pipe wrapper —
    is left alone rather than raising: the caller's output is still correct on
    POSIX, and a test capturing stdout must not fail on plumbing.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(newline="\n", encoding="utf-8")
    except (ValueError, OSError):
        # Detached or already-closed stream. Nothing to configure; writing is
        # the caller's problem and will raise on its own terms.
        return


def configure_stdout() -> None:
    """Force LF + UTF-8 on `sys.stdout`. Call once, before any output."""
    configure_stream(sys.stdout)


def configure_stdin() -> None:
    """Force UTF-8 on `sys.stdin`. Call once, before any read.

    A helper that reads paths from a shell pipe decodes them through the
    platform default, so a Cyrillic path raises `UnicodeDecodeError` on Windows
    and kills the whole pipeline. That is the same failure class as the
    quotepath one, one layer deeper: the path survives git and then dies on the
    way into python.
    """
    configure_stream(sys.stdin)


def configure_std_streams() -> None:
    """Both directions at once, for a script that reads AND writes text.

    The default in an engine entrypoint: getting one right and forgetting the
    other is the same bug with a different symptom.
    """
    configure_stdin()
    configure_stdout()


def emit_lines(lines: Iterable[str]) -> None:
    """Write each item as its own LF-terminated UTF-8 line on stdout.

    The single supported way for an engine python helper to hand a list to a
    shell caller. Values are written verbatim — no stripping, no quoting — so a
    path containing spaces survives; the shell side reads with
    `while IFS= read -r`.
    """
    configure_stdout()
    out = sys.stdout
    for line in lines:
        out.write(f"{line}\n")
    out.flush()


def read_text_utf8(path, *, default: str | None = None) -> str:
    """Read a file as UTF-8, regardless of the platform's ANSI code page.

    `Path.read_text()` without `encoding=` uses `locale.getpreferredencoding()`,
    which is cp1252 on a stock Windows box — so any non-ASCII byte in engine
    data (Cyrillic note titles, em-dashes in generated markers) either raises or
    silently mojibakes. Engine code reads UTF-8 always.

    `default` returns that value instead of raising when the file is missing or
    undecodable; omit it to let the error propagate.
    """
    from pathlib import Path

    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        if default is None:
            raise
        return default


def write_text_utf8(path, text: str) -> None:
    """Write a file as UTF-8 with LF endings, on every platform.

    `newline=""` suppresses python's universal-newline translation, so the
    bytes on disk are exactly what the caller passed. Without it a shipped
    `.sh` written from Windows lands with CRLF and breaks bash on the next
    checkout.
    """
    # `open(newline="")` rather than `Path.write_text(newline=...)`: the latter
    # only exists from Python 3.10, and the engine runs on 3.9.
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
