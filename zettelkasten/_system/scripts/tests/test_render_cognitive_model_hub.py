"""Tests for render_cognitive_model_hub.py.

Isolated via MINDER_MEMORY_BASE → a tempdir holding a minimal Minder Memory tree (axis-SoT prompt,
schema-valid principles, candidate buffer, hub-with-markers). No LLM, no network.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# The real axis block — the test base copies it so the helper parses the same
# SoT the engine ships. If the real prompt's block changes shape, this read
# fails loudly (which is the point: the parser contract is pinned to the SoT).
_REAL_PROMPT = SCRIPTS.parent / "registries/lenses/cognitive-model/prompt.md"
_REAL_TEMPLATE = SCRIPTS.parent.parent / "5_meta/mocs/hub-cognitive-model.template.md"


def _axis_block_text() -> str:
    text = _REAL_PROMPT.read_text(encoding="utf-8")
    start = text.index("<!-- cognitive-axes:begin")
    end = text.index("<!-- cognitive-axes:end -->")
    return text[start:end] + "<!-- cognitive-axes:end -->\n"


def _reload_module(base: Path):
    """Import (or re-import) the helper with MINDER_MEMORY_BASE pointed at `base`.

    repo_root() reads MINDER_MEMORY_BASE at call time, but registries_dir()/state_dir()
    are computed inside main() per call — so a plain import is enough; we set
    the env in the fixture.
    """
    import render_cognitive_model_hub as mod
    return importlib.reload(mod)


PRINCIPLE_TEMPLATE = """\
---
id: principle-{domain}-{nnn}
title: {title}
type: principle
domain: {domain}
statement: {statement}
priority_tier: 2
scope: shared
applies_to: [claude-code]
status: {status}
{axes_line}---

## Statement

{statement}
"""


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDER_MEMORY_BASE", str(tmp_path))
    # Axis SoT prompt
    prompt = tmp_path / "_system/registries/lenses/cognitive-model/prompt.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("# Cognitive Model\n\n" + _axis_block_text(), encoding="utf-8")
    # Empty candidate buffer
    state = tmp_path / "_system/state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "principle-candidates.jsonl").write_text("", encoding="utf-8")
    # Hub with markers (owner zone above, empty managed zone)
    hub = tmp_path / "5_meta/mocs/hub-cognitive-model.md"
    hub.parent.mkdir(parents=True, exist_ok=True)
    hub.write_text(_hub_seed(), encoding="utf-8")
    # Constitution dirs
    (tmp_path / "0_constitution/principle").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _hub_seed() -> str:
    from render_cognitive_model_hub import ZONE_START, ZONE_END
    return (
        "---\n"
        "id: hub-cognitive-model\n"
        "title: 'Hub: Cognitive Model'\n"
        "layer: hub\n"
        "hub_kind: domain\n"
        "chronological_map_mode: curated\n"
        "origin: personal\n"
        "audience_tags: []\n"
        "is_sensitive: false\n"
        "---\n\n"
        "# Hub: Cognitive Model\n\n"
        "## Портрет мышления\n\n"
        "_owner prose — engine never touches this._\n\n"
        f"{ZONE_START}\n{ZONE_END}\n"
    )


def _write_principle(base: Path, domain: str, nnn: str, *, axes=None, status="active",
                     title="T", statement="S"):
    axes_line = ""
    if axes is not None:
        axes_line = "cognitive_axes: [" + ", ".join(axes) + "]\n"
    path = base / f"0_constitution/principle/{domain}/{nnn}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        PRINCIPLE_TEMPLATE.format(
            domain=domain, nnn=nnn, title=title, statement=statement,
            status=status, axes_line=axes_line,
        ),
        encoding="utf-8",
    )
    return path


def _run(mod, *args) -> int:
    return mod.main(list(args))


def _hub_text(base: Path) -> str:
    return (base / "5_meta/mocs/hub-cognitive-model.md").read_text(encoding="utf-8")


def test_promoted_and_blank(base, capsys):
    _write_principle(base, "ai-interaction", "011", axes=["feedback-reception"])
    _write_principle(base, "learning", "001", axes=["abstraction-level"])
    mod = _reload_module(base)
    rc = _run(mod)
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["ok"] is True
    assert out["status_counts"]["promoted"] == 2
    # count-agnostic: every non-promoted axis is blank (no candidates here)
    total_axes = len(yaml.safe_load(
        _axis_block_text().split("```yaml")[1].split("```")[0])["axes"])
    assert out["status_counts"]["blank"] == total_axes - 2
    text = _hub_text(base)
    assert "[[principle-ai-interaction-011]]" in text
    assert "[[principle-learning-001]]" in text
    assert "| Feedback reception | promoted |" in text
    # a blank axis appears with em-dash principle cell
    assert "| Cognitive energy | blank | — | — | — |" in text
    assert "Cognitive energy" in text.split("## Пробелы")[1]


def test_idempotent_second_run_noop(base, capsys):
    _write_principle(base, "ai-interaction", "011", axes=["feedback-reception"])
    mod = _reload_module(base)
    _run(mod)
    capsys.readouterr()
    first = _hub_text(base)
    _run(mod)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["changed"] is False
    second = _hub_text(base)
    assert first == second, "second render must be byte-identical (true no-op)"


def test_check_mode_exit_code(base, capsys):
    _write_principle(base, "ai-interaction", "011", axes=["feedback-reception"])
    mod = _reload_module(base)
    # First check: hub still empty zone → would change → exit 3
    rc = _run(mod, "--check")
    assert rc == 3
    capsys.readouterr()
    # Apply, then check again → no change → exit 0
    _run(mod)
    capsys.readouterr()
    rc = _run(mod, "--check")
    assert rc == 0


def test_archived_principle_excluded(base, capsys):
    _write_principle(base, "ai-interaction", "011", axes=["feedback-reception"],
                     status="archived")
    mod = _reload_module(base)
    _run(mod)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["status_counts"]["promoted"] == 0
    assert "feedback-reception" in out["blank_axes"]


def test_evidenced_from_candidate(base, capsys):
    # No principle for cognitive-energy, but a candidate carries that dimension.
    cand = {
        "date": "2026-06-20", "dimension": "cognitive-energy",
        "record_ref": "_records/observations/20260620-reflection.md",
        "observation": "o", "hypothesis": "h",
    }
    (base / "_system/state/principle-candidates.jsonl").write_text(
        json.dumps(cand) + "\n", encoding="utf-8"
    )
    mod = _reload_module(base)
    _run(mod)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["status_counts"]["evidenced"] == 1
    text = _hub_text(base)
    assert "| Cognitive energy | evidenced | — | [[20260620-reflection]] | 2026-06-20 |" in text


def test_promoted_beats_evidenced(base, capsys):
    _write_principle(base, "ai-interaction", "012", axes=["feedback-reception"])
    cand = {"date": "2026-06-20", "dimension": "feedback-reception",
            "record_ref": "_records/observations/x.md", "observation": "o", "hypothesis": "h"}
    (base / "_system/state/principle-candidates.jsonl").write_text(
        json.dumps(cand) + "\n", encoding="utf-8"
    )
    mod = _reload_module(base)
    _run(mod)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["status_counts"]["promoted"] == 1
    assert out["status_counts"]["evidenced"] == 0


def test_unknown_slug_dropped_and_surfaced(base, capsys):
    _write_principle(base, "ai-interaction", "011",
                     axes=["feedback-reception", "not-a-real-axis"])
    mod = _reload_module(base)
    rc = _run(mod)
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    # the known slug still promotes; the unknown one is dropped + surfaced
    assert "not-a-real-axis" not in _hub_text(base)
    assert out["dropped_unknown_slugs"] == [
        {"principle_id": "principle-ai-interaction-011", "slug": "not-a-real-axis"}
    ]


def test_missing_hub_graceful(base, capsys):
    (base / "5_meta/mocs/hub-cognitive-model.md").unlink()
    mod = _reload_module(base)
    rc = _run(mod)
    assert rc == 0  # never crash maintain
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["ok"] is False
    assert "not found" in out["reason"]


def test_missing_markers_graceful(base, capsys):
    """Hub exists but its managed-zone markers were removed → exit 0, ok:false,
    no traceback (the splice() crash regression)."""
    hub = base / "5_meta/mocs/hub-cognitive-model.md"
    hub.write_text("---\nid: hub-cognitive-model\n---\n\n# no markers here\n",
                   encoding="utf-8")
    mod = _reload_module(base)
    rc = _run(mod)
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["ok"] is False
    assert "markers" in out["reason"]


def test_stats_mode_no_hub_needed(base, capsys):
    """--stats reports coverage from constitution state without reading/writing
    the hub file (used by lint F.4)."""
    _write_principle(base, "ai-interaction", "011", axes=["feedback-reception"])
    (base / "5_meta/mocs/hub-cognitive-model.md").unlink()  # no hub at all
    mod = _reload_module(base)
    rc = _run(mod, "--stats")
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True
    assert out["status_counts"]["promoted"] == 1
    assert "feedback-reception" not in out["blank_axes"]
    # hub file was not recreated
    assert not (base / "5_meta/mocs/hub-cognitive-model.md").exists()


def test_duplicate_slug_dedup(base, capsys):
    """A principle tagging the same axis twice must not produce a duplicate
    [[id]] link in the row."""
    _write_principle(base, "ai-interaction", "011",
                     axes=["feedback-reception", "feedback-reception"])
    mod = _reload_module(base)
    _run(mod)
    text = _hub_text(base)
    assert text.count("[[principle-ai-interaction-011]]") == 1


def test_unknown_candidate_dimension_warned(base, capsys):
    cand = {"date": "2026-06-20", "dimension": "bogus-axis",
            "record_ref": "x.md", "observation": "o", "hypothesis": "h"}
    (base / "_system/state/principle-candidates.jsonl").write_text(
        json.dumps(cand) + "\n", encoding="utf-8")
    mod = _reload_module(base)
    rc = _run(mod)
    assert rc == 0
    err = capsys.readouterr().err
    assert "unknown dimension slug" in err


def test_sot_no_principle_body_in_hub(base):
    _write_principle(base, "ai-interaction", "011", axes=["feedback-reception"],
                     statement="THIS IS THE PRINCIPLE BODY STATEMENT")
    mod = _reload_module(base)
    _run(mod)
    text = _hub_text(base)
    assert "[[principle-ai-interaction-011]]" in text
    assert "THIS IS THE PRINCIPLE BODY STATEMENT" not in text


def test_all_covered_summary(base, capsys):
    axes = yaml.safe_load(_axis_block_text().split("```yaml")[1].split("```")[0])["axes"]
    for i, ax in enumerate(axes):
        _write_principle(base, "ai-interaction", f"{100 + i:03d}", axes=[ax["slug"]])
    mod = _reload_module(base)
    _run(mod)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert out["status_counts"]["blank"] == 0
    text = _hub_text(base)
    assert f"Все {len(axes)} осей покрыты" in text


def test_template_matches_blank_render(base):
    """Template-spec-sync: the shipped template's managed zone must equal the
    helper's all-blank render (modulo timestamp/hash). Guards drift between
    hub-cognitive-model.template.md and the renderer."""
    if not _REAL_TEMPLATE.exists():
        pytest.skip("template not authored yet")
    mod = _reload_module(base)
    # base has no principles, empty candidates → blank render
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--dry-run"])
    assert rc == 0
    rendered_zone = buf.getvalue()
    tmpl_text = _REAL_TEMPLATE.read_text(encoding="utf-8")
    b = mod.find_zone(tmpl_text)
    assert b is not None, "template missing managed-zone markers"
    tmpl_zone = tmpl_text[b[0]:b[1]]
    assert mod.normalise_zone(rendered_zone) == mod.normalise_zone(tmpl_zone)
