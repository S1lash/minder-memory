"""Previous-shape role carry-over — the plan and the self-check.

`roles_previous_plan.py` turns a parked previous-shape role into the plan
`/minder:mem:role:add --from-previous` reads; `roles_previous_selfcheck.py`
proves, by looking, that a parked tree is whole. These pin the contracts the
concierge relies on: both YAML list forms are read (a tool-bearing role must
name what carries across), a plan is rebuilt from the parked directory alone,
and the self-check FAILS on a parked role with no plan rather than reporting
clean.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS_DIR = _THIS.parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))

import roles_previous_plan as plan  # noqa: E402  # type: ignore
from roles_previous_memory import PARKED_DIRNAME  # noqa: E402  # type: ignore


class ListedTests(unittest.TestCase):
    """`listed` reads BOTH YAML list forms — a concierge wrote these configs,
    not a schema, so `tools: [notion]` and a `- notion` block are both real."""

    def test_block_form(self):
        self.assertEqual(plan.listed("id: x\ntools:\n  - notion\n  - calendar\n", "tools"),
                         ["notion", "calendar"])

    def test_inline_flow_form(self):
        self.assertEqual(plan.listed("id: x\ntools: [notion, calendar]\n", "tools"),
                         ["notion", "calendar"])

    def test_inline_quoted_items(self):
        self.assertEqual(plan.listed("id: x\ntools: ['notion', \"calendar\"]\n", "tools"),
                         ["notion", "calendar"])

    def test_empty_forms_are_empty(self):
        for text in ("id: x\ntools: []\n", "id: x\n", "id: x\ntools:\n"):
            with self.subTest(text=text):
                self.assertEqual(plan.listed(text, "tools"), [])

    def test_a_following_key_does_not_leak_into_the_list(self):
        self.assertEqual(plan.listed("id: x\ntools:\n  - notion\ncadence: daily\n", "tools"), ["notion"])


def _park(base: Path, rid: str, cfg: str) -> Path:
    prev = base / "_system" / "roles" / PARKED_DIRNAME
    (prev / rid / "hooks").mkdir(parents=True)
    (prev / rid / "config.yml").write_text(cfg, encoding="utf-8")
    (prev / rid / "hooks" / "tick.md").write_text("do a thing\n", encoding="utf-8")
    return prev


class PlanTests(unittest.TestCase):
    def test_tool_bearing_role_gets_the_store_names_in_its_plan(self):
        for cfg in ("id: r\ncadence: daily\ntools: [notion]\n",
                    "id: r\ncadence: daily\ntools:\n  - notion\n"):
            with self.subTest(cfg=cfg), tempfile.TemporaryDirectory() as tmp:
                prev = _park(Path(tmp) / "base", "r", cfg)
                plan.main(["roles_previous_plan.py", str(prev), json.dumps(["NOTION_TOKEN"])])
                built = json.loads((prev / "r.plan.json").read_text(encoding="utf-8"))
                self.assertEqual(built["proposed"]["secrets"], ["NOTION_TOKEN"])
                self.assertIn("MINDER_MEMORY_ROLES_KEY", built["proposed"]["secrets_note"])

    def test_store_names_are_read_from_the_base_when_not_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            prev = _park(base, "r", "id: r\ncadence: daily\ntools: [notion]\n")
            (base / "_system" / "state").mkdir(parents=True)
            (base / "_system" / "state" / "secrets.enc.json").write_text('{"NOTION_TOKEN": "x"}', encoding="utf-8")
            plan.main(["roles_previous_plan.py", str(prev)])
            built = json.loads((prev / "r.plan.json").read_text(encoding="utf-8"))
            self.assertEqual(built["proposed"]["secrets"], ["NOTION_TOKEN"])


class SelfcheckTests(unittest.TestCase):
    def _run(self, base: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "roles_previous_selfcheck.py"), str(base)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(base.parent))

    def test_a_parked_role_without_a_plan_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            prev = _park(base, "r", "id: r\ncadence: daily\n")
            (prev / "HANDOFF.md").write_text("r\n" + "x" * 500, encoding="utf-8")
            res = self._run(base)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("has a conversion plan", res.stdout)

    def test_a_parked_role_with_a_rebuilt_plan_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            prev = _park(base, "r", "id: r\ncadence: daily\n")
            (prev / "HANDOFF.md").write_text("r\n" + "x" * 500, encoding="utf-8")
            plan.main(["roles_previous_plan.py", str(prev), "[]"])
            res = self._run(base)
            self.assertEqual(res.returncode, 0, res.stdout)
            self.assertIn("All checks passed", res.stdout)

    def test_no_base_is_a_refusal_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "roles_previous_selfcheck.py")],
                capture_output=True, text=True, encoding="utf-8", cwd=tmp)
            self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
