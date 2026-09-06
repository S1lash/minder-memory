"""Tests for render_hub_index.py — the hub registry projection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._fixture import clear_minder_memory_env, make_fixture  # type: ignore
import render_hub_index as r  # type: ignore


def hub(
    hid: str,
    *,
    title: str | None = None,
    kind: str = "domain",
    modified: str = "2026-01-02",
    status: str = "active",
    related_notes: int | None = None,
    domains: list[str] | None = None,
    people: list[str] | None = None,
) -> str:
    lines = [
        "---",
        f"id: {hid}",
        f"title: '{title if title is not None else f'Hub: {hid} topic'}'",
        f"hub_kind: {kind}",
        f"modified: '{modified}'",
        f"status: {status}",
    ]
    if related_notes is not None:
        lines.append(f"related_notes: {related_notes}")
    for key, values in (("domains", domains), ("people", people)):
        if values:
            lines.append(f"{key}:")
            lines.extend(f"- {v}" for v in values)
    lines += ["---", "", f"# {hid}", ""]
    return "\n".join(lines)


VIEW_WITH_MARKERS = f"""# Hub Index

{r.ZONE_START}
stale content
{r.ZONE_END}

---

## Cross-link state

| Hub A | Hub B | Why orthogonal |
|---|---|---|
| hub-a | hub-b | owner-authored rationale that must survive |
"""


VIEW_LEGACY = """# Hub Index

Индекс всех hub-заметок. 2026-08-14 (batch 20260814-process: 5 hubs bumped …)

---

## Active Hubs (99)

| Hub | Topic | Updated | Notes | Domains | Key People |
|---|---|---|---:|---|---|
| [[hub-gone]] | a hub that no longer exists | 2026-01-01 | 5 | work | someone |

---

## Cross-link state

| Hub A | Hub B | Why orthogonal |
|---|---|---|
| hub-a | hub-b | owner-authored rationale that must survive |
"""


class RenderHubIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fx = make_fixture(self.tmp)
        self.base = self.fx.base
        self.mocs = self.base / "5_meta" / "mocs"
        self.mocs.mkdir(parents=True, exist_ok=True)
        self.views = self.base / "_system" / "views"
        self.views.mkdir(parents=True, exist_ok=True)
        self.view_path = self.views / "HUB_INDEX.md"

    def tearDown(self) -> None:
        clear_minder_memory_env()
        self._tmp.cleanup()

    # -- helpers ---------------------------------------------------------

    def write_hub(self, name: str, content: str) -> Path:
        p = self.mocs / name
        p.write_text(content, encoding="utf-8")
        return p

    def run_render(self, *extra: str) -> int:
        return r.main([
            "--base", str(self.base), "--output", str(self.view_path), *extra,
        ])

    def seed_view(self, content: str = VIEW_WITH_MARKERS) -> None:
        self.view_path.write_text(content, encoding="utf-8")

    # -- collection ------------------------------------------------------

    def test_collects_every_hub_with_frontmatter(self) -> None:
        self.write_hub("hub-a.md", hub("hub-a"))
        self.write_hub("hub-b.md", hub("hub-b"))
        hubs = r.collect_hubs(self.base)
        self.assertEqual([h.id for h in hubs], ["hub-a", "hub-b"])

    def test_engine_template_seed_excluded(self) -> None:
        self.write_hub("hub-a.md", hub("hub-a"))
        self.write_hub("hub-a.template.md", hub("hub-a"))
        self.assertEqual([h.id for h in r.collect_hubs(self.base)], ["hub-a"])

    def test_symlinked_hub_not_listed_twice(self) -> None:
        real = self.write_hub("hub-a.md", hub("hub-a"))
        link = self.mocs / "hub-a-link.md"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this platform")
        self.assertEqual([h.id for h in r.collect_hubs(self.base)], ["hub-a"])

    def test_hub_without_frontmatter_is_skipped_not_invented(self) -> None:
        self.write_hub("hub-a.md", hub("hub-a"))
        self.write_hub("hub-broken.md", "no frontmatter at all\n")
        self.assertEqual([h.id for h in r.collect_hubs(self.base)], ["hub-a"])

    def test_row_fields_come_from_the_hub_only(self) -> None:
        self.write_hub("hub-a.md", hub(
            "hub-a", title="Hub: Topic — dashes", kind="project",
            modified="2026-05-06", related_notes=42,
            domains=["work", "tech"], people=["ivan-petrov", "john-doe"],
        ))
        h = r.collect_hubs(self.base)[0]
        self.assertEqual(h.topic, "Topic — dashes")   # `Hub: ` prefix stripped
        self.assertEqual(h.kind, "project")
        self.assertEqual(h.modified, "2026-05-06")
        self.assertEqual(h.notes, "42")
        self.assertEqual(h.domains, ("work", "tech"))
        self.assertEqual(h.people, ("ivan-petrov", "john-doe"))

    def test_absent_fields_render_as_missing_never_invented(self) -> None:
        self.write_hub("hub-a.md", hub("hub-a"))
        h = r.collect_hubs(self.base)[0]
        self.assertEqual(h.notes, r.MISSING)
        self.assertEqual(h.domains, ())
        row = r._row(h)
        self.assertIn(f"| {r.MISSING} |", row)

    # -- grouping --------------------------------------------------------

    def test_standing_sections_always_render(self) -> None:
        self.write_hub("hub-a.md", hub("hub-a", status="active"))
        sections = r.group_by_status(r.collect_hubs(self.base))
        self.assertEqual([s for s, _ in sections][:3], list(r.ALWAYS_SECTIONS))

    def test_unknown_status_gets_its_own_section_no_hub_dropped(self) -> None:
        self.write_hub("hub-a.md", hub("hub-a", status="active"))
        self.write_hub("hub-r.md", hub("hub-r", status="reference"))
        sections = r.group_by_status(r.collect_hubs(self.base))
        names = [s for s, _ in sections]
        self.assertEqual(names, ["active", "dormant", "resolved", "reference"])
        listed = {h.id for _, bucket in sections for h in bucket}
        self.assertEqual(listed, {"hub-a", "hub-r"})

    def test_rows_sort_by_modified_desc_then_id(self) -> None:
        self.write_hub("hub-old.md", hub("hub-old", modified="2026-01-01"))
        self.write_hub("hub-new.md", hub("hub-new", modified="2026-09-09"))
        sections = dict(r.group_by_status(r.collect_hubs(self.base)))
        self.assertEqual([h.id for h in sections["active"]],
                         ["hub-new", "hub-old"])

    # -- writing ---------------------------------------------------------

    def test_owner_section_survives_regeneration(self) -> None:
        self.seed_view()
        self.write_hub("hub-a.md", hub("hub-a"))
        self.assertEqual(self.run_render(), 0)

        text = self.view_path.read_text(encoding="utf-8")
        self.assertIn("owner-authored rationale that must survive", text)
        self.assertIn("## Cross-link state", text)
        self.assertIn("[[hub-a]]", text)
        self.assertNotIn("stale content", text)

    def test_legacy_layout_adopted_and_stale_rows_dropped(self) -> None:
        self.seed_view(VIEW_LEGACY)
        self.write_hub("hub-a.md", hub("hub-a"))
        self.assertEqual(self.run_render(), 0)

        text = self.view_path.read_text(encoding="utf-8")
        self.assertIn(r.ZONE_START, text)
        self.assertIn(r.ZONE_END, text)
        self.assertIn("[[hub-a]]", text)
        # A hub no longer on disk, and the batch narrative above the table,
        # are both inside the generated region — neither survives.
        self.assertNotIn("hub-gone", text)
        self.assertNotIn("batch 20260814-process", text)
        self.assertIn("owner-authored rationale that must survive", text)
        # The heading keeps exactly one blank line before the zone.
        self.assertTrue(text.startswith(f"# Hub Index\n\n{r.ZONE_START}"))

    def test_rerun_is_byte_identical_and_writes_nothing(self) -> None:
        self.seed_view()
        self.write_hub("hub-a.md", hub("hub-a", related_notes=3))
        self.assertEqual(self.run_render(), 0)

        first = self.view_path.read_text(encoding="utf-8")
        mtime = self.view_path.stat().st_mtime_ns
        self.assertEqual(self.run_render(), 0)
        second = self.view_path.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        # Unchanged input → no write at all, so even the timestamp is stable.
        self.assertEqual(mtime, self.view_path.stat().st_mtime_ns)

    def test_check_mode_reports_drift_without_writing(self) -> None:
        self.seed_view()
        self.write_hub("hub-a.md", hub("hub-a"))
        before = self.view_path.read_text(encoding="utf-8")
        self.assertEqual(self.run_render("--check"), 3)
        self.assertEqual(self.view_path.read_text(encoding="utf-8"), before)

        self.assertEqual(self.run_render(), 0)
        self.assertEqual(self.run_render("--check"), 0)

    def test_missing_view_is_skipped_not_a_crash(self) -> None:
        self.write_hub("hub-a.md", hub("hub-a"))
        self.assertEqual(self.run_render(), 0)      # view file absent
        self.assertFalse(self.view_path.exists())

    def test_unrecognised_view_is_skipped_not_guessed(self) -> None:
        self.seed_view("Some other document entirely.\n")
        self.write_hub("hub-a.md", hub("hub-a"))
        self.assertEqual(self.run_render(), 0)
        self.assertEqual(self.view_path.read_text(encoding="utf-8"),
                         "Some other document entirely.\n")

    def test_dry_run_prints_and_does_not_write(self) -> None:
        self.seed_view()
        self.write_hub("hub-a.md", hub("hub-a"))
        before = self.view_path.read_text(encoding="utf-8")
        self.assertEqual(self.run_render("--dry-run"), 0)
        self.assertEqual(self.view_path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
