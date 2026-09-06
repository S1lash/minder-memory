"""Tests for lint_cognitive_axes.py — cognitive_axes frontmatter integrity."""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_REAL_PROMPT = SCRIPTS.parent / "registries/lenses/cognitive-model/prompt.md"


def _axis_prompt(base: Path):
    p = base / "_system/registries/lenses/cognitive-model/prompt.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    text = _REAL_PROMPT.read_text(encoding="utf-8")
    start = text.index("<!-- cognitive-axes:begin")
    end = text.index("<!-- cognitive-axes:end -->")
    p.write_text("# prompt\n\n" + text[start:end] + "<!-- cognitive-axes:end -->\n",
                 encoding="utf-8")


def _principle(base: Path, nnn: str, axes_line: str = "", scope: str = "shared"):
    p = base / f"0_constitution/principle/ai-interaction/{nnn}-x.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        f"id: principle-ai-interaction-{nnn}",
        "title: T",
        "type: principle",
        "domain: ai-interaction",
    ]
    if axes_line:
        fm.append(axes_line.rstrip("\n"))
    fm += [
        "statement: S",
        "priority_tier: 2",
        f"scope: {scope}",
        "applies_to: [claude-code]",
        "status: active",
        "---",
        "",
        "## Statement",
        "S",
        "",
    ]
    p.write_text("\n".join(fm), encoding="utf-8")


def _hub(base: Path, is_sensitive="false", audience="[]"):
    p = base / "5_meta/mocs/hub-cognitive-model.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nid: hub-cognitive-model\nis_sensitive: {is_sensitive}\n"
                 f"audience_tags: {audience}\n---\n", encoding="utf-8")


def _run(base: Path, monkeypatch) -> list[dict]:
    monkeypatch.setenv("MINDER_MEMORY_BASE", str(base))
    import importlib
    import lint_cognitive_axes as mod
    importlib.reload(mod)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--root", str(base)])
    assert rc == 0
    return [json.loads(l) for l in buf.getvalue().splitlines() if l.strip()]


def test_clean(tmp_path, monkeypatch):
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "cognitive_axes: [feedback-reception]\n")
    _hub(tmp_path)
    assert _run(tmp_path, monkeypatch) == []


def test_unknown_slug(tmp_path, monkeypatch):
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "cognitive_axes: [feedback-reception, bogus]\n")
    _hub(tmp_path)
    kinds = [e["kind"] for e in _run(tmp_path, monkeypatch)]
    assert "cognitive-axes-unknown-slug" in kinds


def test_duplicate(tmp_path, monkeypatch):
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "cognitive_axes: [feedback-reception, feedback-reception]\n")
    _hub(tmp_path)
    kinds = [e["kind"] for e in _run(tmp_path, monkeypatch)]
    assert "cognitive-axes-duplicate" in kinds


def test_malformed_string(tmp_path, monkeypatch):
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "cognitive_axes: feedback-reception\n")  # bare string
    _hub(tmp_path)
    kinds = [e["kind"] for e in _run(tmp_path, monkeypatch)]
    assert "cognitive-axes-malformed" in kinds


def test_sensitivity_mismatch(tmp_path, monkeypatch):
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "cognitive_axes: [feedback-reception]\n", scope="sensitive")
    _hub(tmp_path, is_sensitive="false")
    events = _run(tmp_path, monkeypatch)
    assert any(e["kind"] == "cognitive-hub-sensitivity-mismatch" for e in events)


def test_sensitivity_ok_when_hub_marked(tmp_path, monkeypatch):
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "cognitive_axes: [feedback-reception]\n", scope="sensitive")
    _hub(tmp_path, is_sensitive="true")
    kinds = [e["kind"] for e in _run(tmp_path, monkeypatch)]
    assert "cognitive-hub-sensitivity-mismatch" not in kinds


def test_untagged_principles_clean(tmp_path, monkeypatch):
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "")  # no cognitive_axes
    _hub(tmp_path)
    assert _run(tmp_path, monkeypatch) == []


def test_archived_principle_not_flagged(tmp_path, monkeypatch):
    """Only active principles feed the hub — a bad slug or sensitive scope on an
    archived principle must NOT surface (it is not in the hub)."""
    _axis_prompt(tmp_path)
    _principle(tmp_path, "011", "cognitive_axes: [bogus]\n",
               scope="sensitive")  # would trip 3 checks if active...
    # ...but make it archived:
    p = tmp_path / "0_constitution/principle/ai-interaction/011-x.md"
    p.write_text(p.read_text().replace("status: active", "status: archived"), encoding="utf-8")
    _hub(tmp_path, is_sensitive="false")
    assert _run(tmp_path, monkeypatch) == []
