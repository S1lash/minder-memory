"""The portability gate's `py-write-text-newline` rule sees a wrapped call.

`Path.write_text(newline=...)` raises `TypeError` on Python 3.9. A call
wrapped over two lines once reached CI because the rule read one line at a
time and the keyword sat on the continuation line.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO / "scripts"))

import check_portability as gate  # noqa: E402


def _rule_hits(tmp_path: Path, source: str) -> list:
    path = tmp_path / "probe.py"
    path.write_bytes(source.encode("utf-8"))
    return [f for f in gate.scan_file(path, "probe.py") if f.rule.rule_id == "py-write-text-newline"]


def test_a_wrapped_call_with_newline_is_flagged(tmp_path: Path) -> None:
    # portability-ok: the rule's own fixture, a string, never executed
    source = 'p.write_text(text + "\\n",\n               encoding="utf-8", newline="\\n")\n'
    assert len(_rule_hits(tmp_path, source)) == 1


def test_a_one_line_call_with_newline_is_flagged(tmp_path: Path) -> None:
    source = 'p.write_text(t, encoding="utf-8", newline="")\n'  # portability-ok: fixture
    assert len(_rule_hits(tmp_path, source)) == 1


def test_open_with_newline_and_a_plain_write_text_pass(tmp_path: Path) -> None:
    source = ('with open(p, "w", encoding="utf-8",\n          newline="\\n") as h:\n'
              '    h.write(t)\n'
              'p.write_text(t,\n             encoding="utf-8")\n'
              'q.write_text(t, encoding="utf-8")\nnewline = 1\n')
    assert _rule_hits(tmp_path, source) == []
