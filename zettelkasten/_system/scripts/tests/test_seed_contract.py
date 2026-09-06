"""Tests for scripts/check_seed_contract.py — the seed-contract gate.

Proves the gate detects every seed-contract violation class (so it cannot rot
into a no-op), plus that the real manifest passes the static checks.

Coverage:
- real manifest passes static_checks
- clean fabricated skeleton passes scan_skeleton
- detects un-materialised template leak (a .template.* that is not skill-seed / layered / whitelisted)
- skill-seed (.template kept) and layered (.template.yaml) and whitelist do NOT trip the leak check
- detects owner .local.yaml leak
- detects layered baseline divergence (tuning leak)
- static: seed_skill not subset of template
- static: template path under an engine directory (double-ship regression)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO / "scripts"))

import check_seed_contract as G  # type: ignore
from release_engine import load_manifest  # type: ignore


def _write(p: Path, text: str = "x\n") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class TestStaticChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_manifest(_REPO)

    def test_real_manifest_passes(self) -> None:
        self.assertEqual(G.static_checks(self.manifest, _REPO), [])

    def test_seed_skill_must_be_subset_of_template(self) -> None:
        bad = dict(self.manifest)
        bad["seed_skill"] = list(self.manifest.get("seed_skill", [])) + [
            "zettelkasten/_system/state/NOPE.template.md"
        ]
        v = G.static_checks(bad, _REPO)
        self.assertTrue(any("not in template" in x for x in v), v)

    def test_template_under_engine_dir_is_double_ship(self) -> None:
        # Regression guard for the threshold bug: a seed listed in template: that
        # also lives under an engine directory ships twice and gets clobbered by sync.
        bad = dict(self.manifest)
        bad["template"] = list(self.manifest.get("template", [])) + [
            "zettelkasten/_system/scripts/biometric_thresholds.yaml"
        ]
        v = G.static_checks(bad, _REPO)
        self.assertTrue(any("double-ship" in x for x in v), v)


class TestScanSkeleton(unittest.TestCase):
    def _fake_skeleton(self, tmp: Path) -> Path:
        sk = tmp / "skeleton"
        # strip-seed (already renamed), skill-seed (verbatim), layered pair
        _write(sk / "zettelkasten/_system/SOUL.md")
        _write(sk / "zettelkasten/_system/state/insights-config.yaml.template")
        _write(sk / "zettelkasten/_system/state/content-pipeline-state.template.json", "{}\n")
        _write(sk / "zettelkasten/_system/scripts/biometric_thresholds.template.yaml", "a: 1\n")
        _write(sk / "zettelkasten/_system/scripts/biometric_thresholds.yaml", "a: 1\n")
        _write(sk / "integrations/obsidian/minder-memory.template.md")  # whitelist
        return sk

    def _manifest(self) -> dict:
        return {
            "template": [
                "zettelkasten/_system/SOUL.template.md",
                "zettelkasten/_system/state/insights-config.yaml.template",
                "zettelkasten/_system/state/content-pipeline-state.template.json",
            ],
            "engine": ["zettelkasten/_system/scripts/"],
            "seed_skill": [
                "zettelkasten/_system/state/insights-config.yaml.template",
                "zettelkasten/_system/state/content-pipeline-state.template.json",
            ],
        }

    def test_clean_skeleton_passes(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            sk = self._fake_skeleton(Path(t))
            self.assertEqual(G.scan_skeleton(sk, self._manifest(), _REPO), [])

    def test_detects_unmaterialised_template_leak(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            sk = self._fake_skeleton(Path(t))
            _write(sk / "zettelkasten/_system/state/stray.template.json", "{}\n")
            v = G.scan_skeleton(sk, self._manifest(), _REPO)
            self.assertTrue(any("un-materialised" in x for x in v), v)

    def test_detects_local_yaml_leak(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            sk = self._fake_skeleton(Path(t))
            _write(sk / "zettelkasten/_system/scripts/biometric_thresholds.local.yaml")
            v = G.scan_skeleton(sk, self._manifest(), _REPO)
            self.assertTrue(any("local.yaml" in x for x in v), v)

    def test_detects_baseline_divergence(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            sk = self._fake_skeleton(Path(t))
            (sk / "zettelkasten/_system/scripts/biometric_thresholds.yaml").write_text("a: 999\n", encoding="utf-8")
            v = G.scan_skeleton(sk, self._manifest(), _REPO)
            self.assertTrue(any("tuning leak" in x for x in v), v)


class TestFindStrays(unittest.TestCase):
    """find_strays compares a git-tracked skeleton against a fresh release —
    catches committed cruft a rsync-without-delete ship left behind."""

    def test_tracked_stray_detected_untracked_ignored(self) -> None:
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            release = root / "release"
            skel = root / "skeleton"
            _write(release / "a.md")  # the clean release: one file
            # skeleton: same file + a tracked stray + an untracked bytecode file
            _write(skel / "a.md")
            _write(skel / "stray.template.md")
            _write(skel / "junk.pyc")
            subprocess.run(["git", "-C", str(skel), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(skel), "add", "a.md", "stray.template.md"], check=True)
            # junk.pyc left UNtracked on purpose
            strays = G.find_strays(skel, release)
            self.assertTrue(any("stray.template.md" in s for s in strays), strays)
            self.assertFalse(any("junk.pyc" in s for s in strays), strays)
            self.assertFalse(any("a.md" in s for s in strays), strays)


if __name__ == "__main__":
    unittest.main()
