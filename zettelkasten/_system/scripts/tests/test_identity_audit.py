"""Tests for identity_audit.py — registry resolution + the six surfaces.

Two halves. The drift event stream (the nightly scan's contract) must keep
resolving a projects: entry against the registry exactly as before. The
identity audit must find an identifier on every surface it can appear on,
must classify each finding as live / derived / immutable, and must never
mistake a longer identifier that merely shares a prefix for the identity
itself — the false positive the whole design turns on.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import identity_audit as ia  # type: ignore
from _common import (  # type: ignore
    IDENTITY_KIND_UNKNOWN,
    parse_project_registry,
    registry_ids_by_category,
    registry_section_category,
    repo_root,
)


def _scaffold(root: Path) -> None:
    for sub in (
        "_records/meetings", "1_projects", "2_areas", "3_resources",
        "4_archive", "5_meta/mocs", "_system/views", "_sources/inbox",
        "_system/state",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _write_projects_md(root: Path, body: str) -> None:
    (root / "1_projects" / "PROJECTS.md").write_text(body, encoding="utf-8")


def _write_note(
    root: Path,
    rel: str,
    *,
    projects: list[str] | None = None,
    tags: list[str] | None = None,
    body: str = "body\n",
) -> Path:
    fm = f"id: {Path(rel).stem}\n"
    if projects is not None:
        fm += "projects:\n" + "".join(f"  - {p}\n" for p in projects)
    if tags is not None:
        fm += "tags:\n" + "".join(f"  - {t}\n" for t in tags)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}---\n{body}", encoding="utf-8")
    return path


def _write_tag_registry(root: Path, tags: list[str]) -> Path:
    rows = "".join(f"| `{tag}` | 1 |\n" for tag in tags)
    path = root / "_system" / "registries" / "TAGS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Tag Registry\n\n## Project\n\n| Tag | Uses |\n|---|---:|\n" + rows,
        encoding="utf-8",
    )
    return path


def _write_hub(root: Path, slug: str, hub_kind: str | None = None,
               declared_id: str | None = None, body: str = "hub\n") -> Path:
    # Real hubs always carry frontmatter (id, title, …); an `id` keeps the
    # block non-empty so an absent hub_kind reads as "field absent → default
    # project" rather than "malformed frontmatter".
    fm = f"id: {declared_id or ('hub-' + slug)}\n"
    if hub_kind:
        fm += f"hub_kind: {hub_kind}\n"
    path = root / "5_meta" / "mocs" / f"hub-{slug}.md"
    path.write_text(f"---\n{fm}---\n{body}", encoding="utf-8")
    return path


_REGISTRY = """# Project Registry

## Active Projects

| ID | Name | Description | Folder | Status |
|----|------|-------------|--------|--------|
| alpha-app | Alpha | desc | 1_projects/alpha-app/ | active |
| beta-service | Beta | desc | 1_projects/beta-service/ | active |

## Trajectories (not projects)

| ID | Name | Hub | Status |
|----|------|-----|--------|
| growth-arc | Growth arc | [[hub-growth-arc]] | active |

## Consolidated / superseded

| Old ID | Status | Now part of |
|--------|--------|-------------|
| legacy-thing | consolidated 2026-01-02 | [[hub-alpha-app]] (project ID `alpha-app`) |
| old-tool | consolidated 2026-01-02 | [[hub-beta-service]] |
| ghost-entry | empty 2026-01-02 | - |

## Archived Projects

| ID | Name | Description | Folder | Status | Archived | Reason |
|----|------|-------------|--------|--------|----------|--------|
| _(empty)_ | | | | | | |

## Project Template

| ID | placeholder |
|----|-------------|
| project-id | example |
"""


# The registry in the shape the shipped template gives a fresh clone: the
# retirement section renamed for all three kinds it holds, and the kind /
# successor / date declared as columns rather than embedded in a status cell.
_TEMPLATE_REGISTRY = """# Project Registry

## Active Projects

| ID | Name | Description | Folder | Scope | Status |
|----|------|-------------|--------|-------|--------|
| alpha-app | Alpha | desc | 1_projects/alpha-app/ | personal | active |

## Trajectories

| ID | Name | Hub | Status |
|----|------|-----|--------|
| growth-arc | Growth arc | [[hub-growth-arc]] | active |

## Retired Identifiers

| Old ID | Kind | Successor | Date | Reason |
|--------|------|-----------|------|--------|
| legacy-thing | merge | [[hub-alpha-app]] | 2026-01-02 | folded into the umbrella |
| ghost-entry | void | | 2026-01-02 | never existed |

## Project Template

| ID | placeholder |
|----|-------------|
| project-id | example |
"""


def _run_stream(root: Path) -> list[dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        ia.main(["--root", str(root)])
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


def _audit(root: Path) -> dict:
    return ia.audit(root)


def _findings(root: Path, identity: str | None = None) -> list[dict]:
    out = []
    for ident in _audit(root)["identities"]:
        if identity is None or ident["id"] == identity:
            out.extend(ident["findings"])
    return out


# -----------------------------------------------------------------------------
# Registry parsing — the successor column is the point
# -----------------------------------------------------------------------------

class RegistryParsingTests(unittest.TestCase):
    def test_categorises_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            cats = registry_ids_by_category(parse_project_registry(root))
            self.assertEqual(cats["project"], {"alpha-app", "beta-service"})
            self.assertEqual(cats["trajectory"], {"growth-arc"})
            self.assertEqual(
                cats["consolidated"], {"legacy-thing", "old-tool", "ghost-entry"}
            )
            for ids in cats.values():
                self.assertNotIn("project-id", ids)

    def test_successor_from_backticked_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            reg = parse_project_registry(root)
            self.assertEqual(reg["legacy-thing"].successor, "alpha-app")
            self.assertEqual(reg["legacy-thing"].status, "consolidated 2026-01-02")

    def test_successor_from_hub_wikilink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            reg = parse_project_registry(root)
            self.assertEqual(reg["old-tool"].successor, "beta-service")

    def test_empty_retirement_has_no_successor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            reg = parse_project_registry(root)
            self.assertIsNone(reg["ghost-entry"].successor)
            # a live row never carries one either
            self.assertIsNone(reg["alpha-app"].successor)

    def test_missing_registry_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            self.assertEqual(parse_project_registry(root), {})

    def test_both_retirement_headings_resolve_to_one_category(self):
        """The shipped template names the section `Retired Identifiers`; clones
        predating the rename still say `Consolidated / superseded`. A heading
        the parser cannot see falls through to `project`, and every retired
        identifier in it reads as an active one — silently."""
        for heading in (
            "## Retired Identifiers",
            "## Consolidated / superseded",
            "## Retired identifiers (merge / rename / void)",
            "### Superseded",
        ):
            self.assertEqual(
                registry_section_category(heading), "consolidated", heading
            )

    def test_template_shaped_registry_parses_end_to_end(self):
        """A friend installs, records a retirement in the section the template
        gave them, in the columns the template declares."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _TEMPLATE_REGISTRY)
            reg = parse_project_registry(root)
            cats = registry_ids_by_category(reg)
            self.assertEqual(cats["project"], {"alpha-app"})
            self.assertEqual(cats["trajectory"], {"growth-arc"})
            self.assertEqual(cats["consolidated"], {"legacy-thing", "ghost-entry"})
            # The successor is the declared column, not the last cell — which
            # in this shape is the free-text reason.
            self.assertEqual(reg["legacy-thing"].successor, "alpha-app")
            self.assertEqual(reg["legacy-thing"].kind, "merge")
            self.assertIsNone(reg["ghost-entry"].successor)
            self.assertEqual(reg["ghost-entry"].kind, "void")

    def test_declared_reclassify_kind_is_rejected(self):
        """A reclassification never produces a retirement row: the identity
        stays valid and its section is the statement. A row claiming otherwise
        is a defect, and reads as UNSTATED rather than as a fifth kind — and
        because the column exists and holds something unreadable, the row is
        reported rather than quietly treated as the older column-less shape."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _TEMPLATE_REGISTRY.replace(
                "| legacy-thing | merge |", "| legacy-thing | reclassify |",
            ))
            entry = parse_project_registry(root)["legacy-thing"]
            self.assertEqual(entry.kind, IDENTITY_KIND_UNKNOWN)
            self.assertTrue(entry.kind_declared)

    def test_absent_kind_column_is_not_a_declaration(self):
        """The older registry shape has nowhere to state a kind. Reading that
        as "the row fails to state it" flags every retirement a friend recorded
        before the column existed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            entry = parse_project_registry(root)["legacy-thing"]
            self.assertIsNone(entry.kind)
            self.assertFalse(entry.kind_declared)


# -----------------------------------------------------------------------------
# The six surfaces
# -----------------------------------------------------------------------------

class SurfaceDetectionTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_field_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "_records/meetings/m1.md", projects=["legacy-thing"])
            f = _findings(root, "legacy-thing")
            self.assertEqual([x["surface"] for x in f], ["field"])
            self.assertEqual(f[0]["target"], "alpha-app")
            self.assertEqual(f[0]["surface_class"], "live")

    def test_tag_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            f = _findings(root, "legacy-thing")
            self.assertEqual([x["surface"] for x in f], ["tag"])
            self.assertEqual(f[0]["current"], "project/legacy-thing")
            self.assertEqual(f[0]["target"], "project/alpha-app")

    def test_wikilink_surface_all_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "3_resources/r.md",
                body="see [[legacy-thing]] and [[legacy-thing|label]] "
                     "and [[legacy-thing#part]]\n",
            )
            _write_note(root, "1_projects/alpha-app.md")
            f = _findings(root, "legacy-thing")
            self.assertEqual([x["surface"] for x in f], ["wikilink"] * 3)
            # A link names a NODE. The successor's identifier is what a field
            # or a tag carries; the link resolves through the same role order
            # every other link uses, so it can never suggest a node that is
            # not on disk.
            self.assertEqual(f[0]["target"], "[[alpha-app]]")
            self.assertEqual(f[0]["successor"], "alpha-app")

    def test_node_card_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/legacy-thing.md")
            f = _findings(root, "legacy-thing")
            self.assertIn("node-card", [x["surface"] for x in f])

    def test_node_container_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            (root / "1_projects" / "old-tool").mkdir()
            (root / "1_projects" / "old-tool" / "README.md").write_text(
                "readme\n", encoding="utf-8"
            )
            f = _findings(root, "old-tool")
            self.assertEqual([x["surface"] for x in f], ["node-container"])
            self.assertTrue(f[0]["path"].endswith("/"))

    def test_hub_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "legacy-thing")
            f = _findings(root, "legacy-thing")
            self.assertIn("hub", [x["surface"] for x in f])

    def test_every_declared_surface_is_reachable(self):
        """Eight roles are declared and eight must be findable.

        A role the contract declares and the code never emits is a role that
        cannot fail — the registry row and the tag-registry row were exactly
        that, so a retired identifier still declared in TAGS.md passed as
        clean."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            # A retired identifier that ALSO still has a live row: the
            # registry-row surface is a registry contradicting itself.
            _write_projects_md(root, _REGISTRY.replace(
                "| beta-service | Beta | desc | 1_projects/beta-service/ | active |",
                "| beta-service | Beta | desc | 1_projects/beta-service/ | active |\n"
                "| legacy-thing | Legacy | desc | 1_projects/legacy-thing/ | active |",
            ))
            _write_note(root, "_records/meetings/m1.md", projects=["legacy-thing"])
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"],
                        body="link [[legacy-thing]]\n")
            _write_note(root, "1_projects/legacy-thing.md")
            (root / "1_projects" / "legacy-thing").mkdir()
            _write_hub(root, "legacy-thing")
            _write_tag_registry(root, ["project/legacy-thing"])
            surfaces = {x["surface"] for x in _findings(root, "legacy-thing")}
            self.assertEqual(surfaces, set(ia.SURFACES))


# -----------------------------------------------------------------------------
# Exact match, never substring — the false positive the design names
# -----------------------------------------------------------------------------

class ExactMatchTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_longer_named_hub_is_not_a_surface_of_the_shorter_identity(self):
        """A research-cluster hub whose name CONTAINS a retired identifier but
        whose own id differs is a separate identity, not a surface of it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "legacy-thing-research-2025")
            hubs = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "hub"
            ]
            self.assertEqual(hubs, [])
            self.assertFalse(
                ia.hub_is_node_of(root, "legacy-thing"),
                "hub-legacy-thing-research-2025 must not answer for legacy-thing",
            )

    def test_hub_declaring_another_identity_is_not_the_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "legacy-thing", declared_id="hub-something-else")
            self.assertFalse(ia.hub_is_node_of(root, "legacy-thing"))

    def test_prefix_sharing_tag_and_wikilink_not_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "3_resources/r.md",
                tags=["project/legacy-thing-2", "project/x-legacy-thing"],
                body="[[legacy-thing-research-2025]] [[hub-legacy-thing]]\n",
            )
            self.assertEqual(_findings(root, "legacy-thing"), [])

    def test_body_of_longer_identity_still_migrates_its_own_links(self):
        """The prefix-sharing hub is not a surface, but its BODY refers to the
        retired identifier like any other note and must be reported."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "legacy-thing-research-2025",
                       body="cluster of [[legacy-thing]] work\n")
            f = _findings(root, "legacy-thing")
            self.assertEqual([x["surface"] for x in f], ["wikilink"])
            self.assertTrue(f[0]["path"].endswith("hub-legacy-thing-research-2025.md"))


# -----------------------------------------------------------------------------
# Surface classes
# -----------------------------------------------------------------------------

class SurfaceClassTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_derived_surface_is_regenerate_not_migrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "_system/views/INDEX.md",
                        body="[[legacy-thing]]\n")
            f = _findings(root, "legacy-thing")
            self.assertEqual([x["surface_class"] for x in f], ["derived"])
            self.assertEqual([x["action"] for x in f], ["regenerate"])
            result = _audit(root)
            self.assertEqual(result["residue_count"], 0)
            self.assertEqual(result["derived_count"], 1)
            self.assertTrue(result["clean"])

    def test_immutable_surfaces_never_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            for rel in (
                "_sources/inbox/raw.md",
                "_system/state/log_lint.md",
            ):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(
                    "---\ntags:\n  - project/legacy-thing\n---\n[[legacy-thing]]\n",
                    encoding="utf-8",
                )
            self.assertEqual(_findings(root, "legacy-thing"), [])


# -----------------------------------------------------------------------------
# Reclassification — a live entity on the wrong axis
# -----------------------------------------------------------------------------

class ReclassificationTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_correctly_namespaced_tag_is_not_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", tags=["trajectory/growth-arc"])
            self.assertEqual(_findings(root, "growth-arc"), [])

    def test_mis_namespaced_tag_is_renamespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/growth-arc"])
            f = _findings(root, "growth-arc")
            self.assertEqual([x["action"] for x in f], ["renamespace"])
            self.assertEqual(f[0]["target"], "trajectory/growth-arc")

    def test_wikilink_to_live_entity_is_not_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", body="[[growth-arc]]\n")
            self.assertEqual(_findings(root, "growth-arc"), [])

    def test_node_card_under_projects_is_wrong_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/growth-arc.md")
            f = _findings(root, "growth-arc")
            self.assertEqual([x["surface"] for x in f], ["node-card"])


# -----------------------------------------------------------------------------
# Inbound links to a relocating node — the gate's blind spot
# -----------------------------------------------------------------------------

class RepointTests(unittest.TestCase):
    """A node reported for relocation makes every inbound link live work.

    Report the node and not its inbound links, and the gate certifies a graph
    that breaks the moment the node moves.
    """

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_inbound_links_reported_when_node_relocates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/growth-arc.md")   # node to relocate
            _write_hub(root, "growth-arc", hub_kind="trajectory")  # canonical node
            _write_note(root, "2_areas/a.md", body="see [[growth-arc]]\n")
            _write_note(root, "3_resources/b.md", body="[[growth-arc|label]]\n")
            links = [
                x for x in _findings(root, "growth-arc")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 2)
            for x in links:
                self.assertEqual(x["action"], "repoint")
                self.assertEqual(x["target"], "[[hub-growth-arc]]")
                self.assertEqual(x["surface_class"], "live")
                # the identity is alive — the reason must not read as retirement
                self.assertIn("stays live", x["reason"])
                self.assertNotIn("retired identifier", x["reason"])

    def test_no_inbound_findings_when_node_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "growth-arc", hub_kind="trajectory")
            _write_note(root, "2_areas/a.md", body="see [[growth-arc]]\n")
            self.assertEqual(_findings(root, "growth-arc"), [])

    def test_retired_identity_links_stay_migrate_not_repoint(self):
        # A retired identity's links are already residue; they must not be
        # reported twice, nor relabelled as a repoint.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/legacy-thing.md")
            _write_note(root, "2_areas/a.md", body="[[legacy-thing]]\n")
            links = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "wikilink"
            ]
            _write_note(root, "1_projects/alpha-app.md")
            links = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]["action"], "migrate")
            self.assertEqual(links[0]["target"], "[[alpha-app]]")

    def test_successor_without_a_node_suggests_no_link(self):
        # The successor is declared but has no node on disk. Suggesting
        # `[[successor]]` would be a link to nothing — the honest answer is no
        # target, and the successor stays visible in its own field.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", body="[[legacy-thing]]\n")
            links = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 1)
            self.assertIsNone(links[0]["target"])
            self.assertEqual(links[0]["successor"], "alpha-app")

    def test_container_node_also_gets_inbound_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            (root / "1_projects" / "growth-arc").mkdir()
            (root / "1_projects" / "growth-arc" / "README.md").write_text(
                "readme\n", encoding="utf-8"
            )
            _write_hub(root, "growth-arc", hub_kind="trajectory")
            _write_note(root, "2_areas/a.md", body="[[growth-arc]]\n")
            actions = {
                x["action"] for x in _findings(root, "growth-arc")
                if x["surface"] == "wikilink"
            }
            self.assertEqual(actions, {"repoint"})

    def test_no_canonical_node_leaves_target_null(self):
        # No hub: the only node IS the one moving, so the audit has nothing to
        # point the link at — the new home is the owner's decision.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/growth-arc.md")
            _write_note(root, "2_areas/a.md", body="[[growth-arc]]\n")
            links = [
                x for x in _findings(root, "growth-arc")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 1)
            self.assertIsNone(links[0]["target"])
            self.assertEqual(links[0]["action"], "repoint")

    def test_derived_inbound_link_is_regenerate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/growth-arc.md")
            _write_hub(root, "growth-arc", hub_kind="trajectory")
            _write_note(root, "_system/views/INDEX.md", body="[[growth-arc]]\n")
            links = [
                x for x in _findings(root, "growth-arc")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual([x["action"] for x in links], ["regenerate"])
            self.assertEqual([x["surface_class"] for x in links], ["derived"])

    def test_repoint_findings_count_as_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/growth-arc.md")
            _write_hub(root, "growth-arc", hub_kind="trajectory")
            _write_note(root, "2_areas/a.md", body="[[growth-arc]]\n")
            result = _audit(root)
            ident = next(
                i for i in result["identities"] if i["id"] == "growth-arc"
            )
            self.assertEqual(ident["by_surface"]["wikilink"], 1)
            self.assertGreater(result["residue_count"], 0)


class CanonicalNodeTests(unittest.TestCase):
    """Resolution is by role: canonical hub → node card → container README."""

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_hub_wins_over_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "growth-arc")
            _write_note(root, "1_projects/growth-arc.md")
            self.assertEqual(ia.canonical_node(root, "growth-arc"),
                             "hub-growth-arc")

    def test_card_wins_over_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "1_projects/growth-arc.md")
            (root / "1_projects" / "growth-arc").mkdir()
            (root / "1_projects" / "growth-arc" / "README.md").write_text(
                "readme\n", encoding="utf-8"
            )
            self.assertEqual(ia.canonical_node(root, "growth-arc"), "growth-arc")

    def test_no_node_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            self.assertIsNone(ia.canonical_node(root, "growth-arc"))

    def test_prefix_sharing_hub_is_not_the_canonical_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "growth-arc-research-2025")
            self.assertIsNone(ia.canonical_node(root, "growth-arc"))


# -----------------------------------------------------------------------------
# Exit codes
# -----------------------------------------------------------------------------

class ExitCodeTests(unittest.TestCase):
    def _run(self, root: Path, argv: list[str]) -> int:
        buf = io.StringIO()
        with redirect_stdout(buf):
            return ia.main(["--root", str(root)] + argv)

    def test_default_mode_is_event_stream_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "_records/meetings/m1.md", projects=["legacy-thing"])
            self.assertEqual(self._run(root, []), 0)
            kinds = {e["kind"] for e in _run_stream(root)}
            self.assertIn("projects-array-consolidated", kinds)

    def test_fail_on_residue_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            self.assertEqual(self._run(root, ["--report", "--fail-on-residue"]), 2)

    def test_fail_on_residue_exits_zero_when_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "2_areas/a.md", tags=["project/alpha-app"])
            self.assertEqual(self._run(root, ["--report", "--fail-on-residue"]), 0)

    def test_report_without_flag_stays_zero_on_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            self.assertEqual(self._run(root, ["--report", "--json"]), 0)

    def test_missing_root_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            self.assertEqual(ia.main(["--root", str(missing)]), 1)

    def test_json_report_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                ia.main(["--root", str(root), "--report", "--json"])
            data = json.loads(buf.getvalue())
            for key in (
                "registries", "identity_count", "residue_count",
                "derived_count", "clean", "surfaces", "identities", "owner",
            ):
                self.assertIn(key, data)
            ident = next(i for i in data["identities"] if i["id"] == "legacy-thing")
            self.assertEqual(ident["successor"], "alpha-app")
            self.assertEqual(ident["by_surface"], {"tag": 1})
            # registry_path is per identity now — there is more than one registry
            self.assertEqual(ident["registry_path"], "1_projects/PROJECTS.md")
            self.assertEqual(ident["registry"], "project")
            self.assertIn(
                "1_projects/PROJECTS.md",
                [r["registry_path"] for r in data["registries"]],
            )


# -----------------------------------------------------------------------------
# Drift event stream — the nightly scan's contract, unchanged
# -----------------------------------------------------------------------------

class EventStreamTests(unittest.TestCase):
    def _kinds_for(self, projects, *, hubs=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            for slug, kind in (hubs or {}).items():
                _write_hub(root, slug, hub_kind=kind)
            _write_note(root, "_records/meetings/n.md", projects=projects)
            return [e for e in _run_stream(root) if "project_id" in e]

    def test_registered_project_clean_with_or_without_hub(self):
        self.assertEqual(self._kinds_for(["alpha-app"]), [])
        self.assertEqual(
            self._kinds_for(["beta-service"], hubs={"beta-service": None}), []
        )

    def test_registered_trajectory_flagged_non_project(self):
        ev = self._kinds_for(["growth-arc"])
        self.assertEqual([e["kind"] for e in ev], ["projects-array-non-project"])

    def test_consolidated_id_flagged(self):
        ev = self._kinds_for(["legacy-thing"])
        self.assertEqual([e["kind"] for e in ev], ["projects-array-consolidated"])

    def test_orphan_project_hub_flagged(self):
        ev = self._kinds_for(["ghost-proj"], hubs={"ghost-proj": "project"})
        self.assertEqual([e["kind"] for e in ev], ["projects-array-orphan-hub"])

    def test_orphan_default_kind_hub_is_project(self):
        ev = self._kinds_for(["ghost-default"], hubs={"ghost-default": None})
        self.assertEqual([e["kind"] for e in ev], ["projects-array-orphan-hub"])

    def test_unregistered_non_project_hub(self):
        ev = self._kinds_for(["some-domain"], hubs={"some-domain": "domain"})
        self.assertEqual([e["kind"] for e in ev], ["projects-array-non-project-hub"])

    def test_unknown_id_no_hub(self):
        ev = self._kinds_for(["ghost-typo"])
        self.assertEqual([e["kind"] for e in ev], ["projects-array-unknown-id"])

    def test_empty_registry_skips_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_hub(root, "has-hub", hub_kind="project")
            _write_note(root, "_records/meetings/a.md", projects=["has-hub"])
            _write_note(root, "_records/meetings/b.md", projects=["no-hub"])
            ev = [e for e in _run_stream(root) if "project_id" in e]
            self.assertEqual(ev, [])

    def test_length_check_runs_without_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_note(root, "_records/meetings/c.md", projects=["a", "b", "c"])
            kinds = {e["kind"] for e in _run_stream(root)}
            self.assertIn("projects-array-overcount", kinds)


if __name__ == "__main__":
    unittest.main()


# -----------------------------------------------------------------------------
# Coverage — the classification partitions the base, and its gaps are findings
# -----------------------------------------------------------------------------

class CoverageTests(unittest.TestCase):
    """An allowlist of scanned roots fails GREEN.

    That is the failure mode worth a test of its own: the scan says `clean:
    true` in exactly the words it would use if everything really were clean,
    and the only difference is that nobody looked. These pin the inversion.
    """

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_new_top_level_region_is_reported_not_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            newest = root / "7_experiments"
            newest.mkdir()
            (newest / "note.md").write_text(
                "---\nid: note\ntags:\n  - project/legacy-thing\n---\nbody\n",
                encoding="utf-8",
            )
            result = _audit(root)
            self.assertEqual(result["unclassified_count"], 1)
            item = result["unclassified"][0]
            self.assertEqual(item["path"], "7_experiments/note.md")
            self.assertEqual(item["region"], "7_experiments/")
            self.assertEqual(item["surface_class"], "unclassified")
            self.assertEqual(item["kind"], ia.CODE_UNCLASSIFIED)
            # Residue, so it cannot pass as clean.
            self.assertFalse(result["clean"])
            self.assertGreaterEqual(result["residue_count"], 1)

    def test_unclassified_region_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            (root / "7_experiments").mkdir()
            (root / "7_experiments" / "n.md").write_text("x\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = ia.main([
                    "--root", str(root), "--report", "--fail-on-residue",
                ])
            self.assertEqual(code, 2)

    def test_the_four_deliberate_regions_are_classified(self):
        """The regions the inversion first exposed, each decided on purpose.

        The constitution is live because a principle's Evidence Trail is a
        wikilink into the base; the posts and the vault front page are live
        because the owner edits them; the engine cards are live because an
        owner identity appearing in one is a leak, not history.
        """
        for rel, expected in (
            ("0_constitution/principle/principle-work-001.md", "live"),
            ("6_posts/drafts/some-post.md", "live"),
            ("5_skills/minder-mem-process.md", "live"),
            ("minder-memory.md", "live"),
        ):
            rule = ia.classify(rel)
            self.assertIsNotNone(rule, rel)
            self.assertEqual(rule.surface_class, expected, rel)
            self.assertTrue(rule.why.strip(), f"{rel} classified with no reason")

    def test_immutable_and_derived_regions_keep_their_class(self):
        for rel, expected in (
            ("_sources/inbox/raw.md", "immutable"),
            ("_system/state/log_lint.md", "immutable"),
            ("_system/agent-lens/foo/2026-01-01.md", "immutable"),
            ("_system/roles/minder-pm/state/01-status.md", "immutable"),
            ("_system/views/INDEX.md", "derived"),
            ("_system/TASKS.md", "derived"),
            ("_system/registries/TAGS.md", "derived"),
            ("_system/roles/minder-pm/role.md", "live"),
            ("_system/SOUL.md", "live"),
            ("_records/meetings/m.md", "live"),
        ):
            rule = ia.classify(rel)
            self.assertIsNotNone(rule, rel)
            self.assertEqual(rule.surface_class, expected, rel)

    def test_real_base_has_no_unclassified_region(self):
        """The detector. A region added to the real base without a decision
        about what it is fails HERE, at the moment it is added, rather than
        silently widening the scan's blind spot."""
        root = repo_root()
        if not root.exists():  # pragma: no cover - a checkout without the base
            self.skipTest("no zettelkasten base in this checkout")
        _files, unclassified = ia.walk_base(root)
        self.assertEqual(
            sorted({u["region"] for u in unclassified}), [],
            "a region of the real base is classified by nothing — decide what "
            "it is and add a rule to identity_audit.CLASSIFICATION",
        )


# -----------------------------------------------------------------------------
# A record's body is history and is never residue
# -----------------------------------------------------------------------------

class RecordBodyTests(unittest.TestCase):
    """The line the contract draws runs INSIDE a record file.

    Frontmatter is engine-managed classification and migrates; the prose is
    what was said. Running the link regex over the whole file makes the next
    retirement of anything ever mentioned in a meeting demand that the meeting
    be rewritten.
    """

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_record_body_wikilink_is_never_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "_records/meetings/m1.md",
                body="We spent an hour on [[legacy-thing]] and moved on.\n",
            )
            self.assertEqual(_findings(root, "legacy-thing"), [])

    def test_record_frontmatter_is_still_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "_records/meetings/m1.md",
                projects=["legacy-thing"], tags=["project/legacy-thing"],
                body="prose mentioning [[legacy-thing]] again\n",
            )
            surfaces = sorted(x["surface"] for x in _findings(root, "legacy-thing"))
            self.assertEqual(surfaces, ["field", "tag"])

    def test_record_frontmatter_wikilink_is_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            path = root / "_records" / "meetings" / "m2.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "---\nid: m2\nhub: \"[[legacy-thing]]\"\n---\n"
                "prose about [[legacy-thing]]\n",
                encoding="utf-8",
            )
            links = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]["line"], 3)

    def test_knowledge_note_body_is_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", body="see [[legacy-thing]]\n")
            self.assertEqual(
                [x["surface"] for x in _findings(root, "legacy-thing")],
                ["wikilink"],
            )


# -----------------------------------------------------------------------------
# Link forms — the path form counts, a quoted one does not
# -----------------------------------------------------------------------------

class LinkFormTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_path_form_link_is_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "2_areas/a.md",
                body="[[1_projects/legacy-thing]] and "
                     "[[1_projects/legacy-thing|label]]\n",
            )
            links = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 2)

    def test_path_form_does_not_match_a_longer_identifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "2_areas/a.md",
                body="[[1_projects/legacy-thing-2]] [[x/y-legacy-thing]]\n",
            )
            self.assertEqual(_findings(root, "legacy-thing"), [])

    def test_table_escaped_pipe_link_is_matched(self):
        """`[[id\\|label]]` — the form every rendered hub map writes.

        A pipe inside a markdown table cell has to be backslash-escaped or it
        ends the cell, so this is not an exotic shape: it is the majority of
        the links this engine itself generates. A scan blind to it reports a
        retirement that landed in a hub map as clean.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "2_areas/a.md",
                body="| note | [[legacy-thing\\|Legacy]] |\n"
                     "| path | [[1_projects/legacy-thing\\|Legacy]] |\n",
            )
            links = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 2)

    def test_table_escaped_pipe_does_not_match_a_longer_identifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "2_areas/a.md",
                body="| a | [[legacy-thing-2\\|L]] |\n"
                     "| b | [[x-legacy-thing\\|L]] |\n",
            )
            self.assertEqual(_findings(root, "legacy-thing"), [])

    def test_link_inside_inline_code_is_not_a_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "2_areas/a.md",
                body="write it as `[[legacy-thing]]` in the frontmatter\n",
            )
            self.assertEqual(_findings(root, "legacy-thing"), [])

    def test_link_inside_a_fenced_block_is_not_a_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "2_areas/a.md",
                body="example:\n\n```markdown\n[[legacy-thing]]\n```\n",
            )
            self.assertEqual(_findings(root, "legacy-thing"), [])

    def test_masking_preserves_line_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(
                root, "2_areas/a.md",
                body="```\n[[legacy-thing]]\n```\n\nreal [[legacy-thing]]\n",
            )
            links = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "wikilink"
            ]
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]["line"], 8)


# -----------------------------------------------------------------------------
# `hub-` collision
# -----------------------------------------------------------------------------

_HUB_ID_REGISTRY = _REGISTRY.replace(
    "| legacy-thing | consolidated 2026-01-02 |",
    "| hub-legacy | consolidated 2026-01-02 |",
)


class HubIdentifierTests(unittest.TestCase):
    """An identity whose own identifier begins `hub-`.

    Composing `hub-{id}` blindly probes `hub-hub-{id}`, finds nothing, and
    reports zero residue while the real node sits in plain sight — a green
    verdict produced by looking in the wrong place.
    """

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _HUB_ID_REGISTRY)
        return root

    def test_hub_prefixed_identifier_resolves_to_its_own_file(self):
        self.assertEqual(ia.hub_id_of("hub-legacy"), "hub-legacy")
        self.assertEqual(ia.hub_id_of("legacy"), "hub-legacy")

    def test_its_hub_node_is_visible_to_the_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "legacy", declared_id="hub-legacy")
            self.assertTrue(ia.hub_is_node_of(root, "hub-legacy"))
            hubs = [
                x for x in _findings(root, "hub-legacy")
                if x["surface"] == "hub"
            ]
            self.assertEqual(len(hubs), 1)
            self.assertEqual(hubs[0]["path"], "5_meta/mocs/hub-legacy.md")

    def test_canonical_node_of_a_hub_prefixed_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "legacy", declared_id="hub-legacy")
            self.assertEqual(ia.canonical_node(root, "hub-legacy"), "hub-legacy")


# -----------------------------------------------------------------------------
# Registry rows — integrity, duplication, and rows that cannot be read
# -----------------------------------------------------------------------------

_DECLARED = """# Project Registry

## Active Projects

| ID | Name | Status |
|----|------|--------|
| alpha-app | Alpha | active |
| beta-service | Beta | active |

## Retired Identifiers

| Old ID | Kind | Successor | Date | Reason |
|--------|------|-----------|------|--------|
{rows}
"""


def _declared_registry(root: Path, rows: str) -> None:
    _write_projects_md(root, _DECLARED.format(rows=rows))


class RegistryRowTests(unittest.TestCase):
    def _base(self, tmp: str, rows: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _declared_registry(root, rows)
        return root

    def _codes(self, root: Path, identity: str) -> list[str]:
        return [x["kind"] for x in _findings(root, identity)]

    def test_merge_without_successor_is_reported_once_against_the_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(
                tmp, "| gone | merge |  | 2026-01-02 | folded in |",
            )
            _write_note(root, "2_areas/a.md", tags=["project/gone"],
                        body="[[gone]] [[gone]] [[gone]]\n")
            f = _findings(root, "gone")
            rows = [x for x in f if x["surface"] == "registry-row"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], ia.CODE_SUCCESSOR_UNDECLARED)
            self.assertEqual(rows[0]["path"], "1_projects/PROJECTS.md")
            self.assertFalse(rows[0]["autofixable"])
            # every surface still counted, none of them offering a target
            surfaces = [x for x in f if x["surface"] != "registry-row"]
            self.assertEqual(len(surfaces), 4)
            for x in surfaces:
                self.assertIsNone(x["target"])
                self.assertFalse(x["autofixable"])

    def test_void_declaring_a_successor_is_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(
                tmp, "| ghost | void | `alpha-app` | 2026-01-02 | never was |",
            )
            codes = self._codes(root, "ghost")
            self.assertIn(ia.CODE_SUCCESSOR_FORBIDDEN, codes)

    def test_split_with_one_successor_is_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(
                tmp, "| both | split | `alpha-app` | 2026-01-02 | two efforts |",
            )
            codes = self._codes(root, "both")
            self.assertIn(ia.CODE_SUCCESSOR_FORBIDDEN, codes)

    def test_unreadable_kind_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(
                tmp, "| odd | reclassify | `alpha-app` | 2026-01-02 | ? |",
            )
            codes = self._codes(root, "odd")
            self.assertIn(ia.CODE_KIND_UNKNOWN, codes)

    def test_unreadable_row_is_surfaced_not_dropped(self):
        """A mistyped retirement row is otherwise indistinguishable from no
        retirement row: the parser drops it and the identifier it was meant to
        retire keeps reading as live."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(
                tmp,
                "| Alpha App | merge | `alpha-app` | 2026-01-02 | typo'd id |",
            )
            result = _audit(root)
            self.assertEqual(result["registry_defect_count"], 1)
            row = result["registry_defects"][0]
            self.assertEqual(row["current"], "Alpha App")
            self.assertEqual(row["kind"], ia.CODE_ROW_UNREADABLE)
            self.assertEqual(row["path"], "1_projects/PROJECTS.md")
            self.assertFalse(result["clean"])

    def test_placeholder_cells_are_not_unreadable_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)  # holds `_(empty)_` and `-`
            self.assertEqual(_audit(root)["registry_defect_count"], 0)

    def test_retired_identifier_with_a_live_row_is_a_registry_contradiction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _DECLARED.format(
                rows="| alpha-app | merge | `beta-service` | 2026-01-02 | x |",
            ))
            codes = self._codes(root, "alpha-app")
            self.assertIn(ia.CODE_ROW_DUPLICATE, codes)


class TagRegistryRowTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_retired_tag_still_declared_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_tag_registry(root, ["project/legacy-thing", "project/alpha-app"])
            rows = [
                x for x in _findings(root, "legacy-thing")
                if x["surface"] == "tag-registry-row"
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], "_system/registries/TAGS.md")
            # The tag registry regenerates, so the row is stale output rather
            # than residue to hand-edit.
            self.assertEqual(rows[0]["surface_class"], "derived")
            self.assertEqual(rows[0]["kind"], ia.CODE_DERIVED_STALE)
            self.assertEqual(rows[0]["action"], "regenerate")

    def test_live_correctly_namespaced_tag_row_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_tag_registry(root, ["trajectory/growth-arc"])
            rows = [
                x for x in _findings(root, "growth-arc")
                if x["surface"] == "tag-registry-row"
            ]
            self.assertEqual(rows, [])


# -----------------------------------------------------------------------------
# Successor resolution — transitive, bounded, and refusing rather than guessing
# -----------------------------------------------------------------------------

class SuccessorResolutionTests(unittest.TestCase):
    def _base(self, tmp: str, rows: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _declared_registry(root, rows)
        return root

    def test_chain_resolves_to_the_terminal_live_successor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp, (
                "| a | rename | `b` | 2026-01-01 | first |\n"
                "| b | rename | `alpha-app` | 2026-01-02 | second |"
            ))
            _write_note(root, "2_areas/n.md", tags=["project/a"])
            f = [x for x in _findings(root, "a") if x["surface"] == "tag"]
            self.assertEqual(len(f), 1)
            # NOT `project/b` — resolving one hop leaves residue behind that
            # the next nightly run reports all over again.
            self.assertEqual(f[0]["target"], "project/alpha-app")
            bucket = next(
                i for i in _audit(root)["identities"] if i["id"] == "a"
            )
            self.assertEqual(bucket["terminal_successor"], "alpha-app")
            self.assertEqual(bucket["successor_chain"], ["a", "b", "alpha-app"])

    def test_cycle_yields_no_target_and_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp, (
                "| a | rename | `b` | 2026-01-01 | one |\n"
                "| b | rename | `a` | 2026-01-02 | other |"
            ))
            _write_note(root, "2_areas/n.md", tags=["project/a"])
            f = _findings(root, "a")
            rows = [x for x in f if x["surface"] == "registry-row"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], ia.CODE_SUCCESSOR_UNRESOLVABLE)
            self.assertIn("a → b → a", rows[0]["reason"])
            for x in f:
                self.assertIsNone(x["target"])

    def test_chain_into_a_void_does_not_terminate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp, (
                "| a | rename | `b` | 2026-01-01 | one |\n"
                "| b | void |  | 2026-01-02 | never was |"
            ))
            rows = [
                x for x in _findings(root, "a")
                if x["surface"] == "registry-row"
            ]
            self.assertEqual(
                [x["kind"] for x in rows], [ia.CODE_SUCCESSOR_UNRESOLVABLE],
            )

    def test_chain_leaving_the_registry_does_not_terminate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(
                tmp, "| a | merge | `not-in-this-registry` | 2026-01-01 | x |",
            )
            rows = [
                x for x in _findings(root, "a")
                if x["surface"] == "registry-row"
            ]
            self.assertEqual(
                [x["kind"] for x in rows], [ia.CODE_SUCCESSOR_UNRESOLVABLE],
            )
            self.assertIn("leaves this registry", rows[0]["reason"])


class SplitTests(unittest.TestCase):
    ROWS = "| both | split | `alpha-app`, `beta-service` | 2026-01-02 | two |"

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _declared_registry(root, self.ROWS)
        return root

    def test_split_parses_both_successors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            entry = parse_project_registry(root)["both"]
            self.assertEqual(entry.kind, "split")
            self.assertEqual(entry.successors, ("alpha-app", "beta-service"))
            # No single successor — offering one would be the scanner choosing
            # on the owner's behalf.
            self.assertIsNone(entry.successor)

    def test_split_surfaces_are_residue_but_never_autofixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/n.md", projects=["both"],
                        tags=["project/both"], body="[[both]]\n")
            f = _findings(root, "both")
            self.assertTrue(f)
            for x in f:
                self.assertEqual(x["kind"], ia.CODE_SPLIT_UNDECIDED)
                self.assertEqual(x["severity"], "weak")
                self.assertFalse(x["autofixable"])
                self.assertEqual(x["action"], "decide")
                self.assertIn("one of:", x["target"])
            self.assertFalse(_audit(root)["clean"])


# -----------------------------------------------------------------------------
# The owner exclusion belongs to the people registry, not to the slug
# -----------------------------------------------------------------------------

class OwnerScopeTests(unittest.TestCase):
    def test_a_project_named_like_the_owner_is_still_audited(self):
        """Applied to every registry, the exclusion silently un-audits a
        project whose identifier collides with a slug transliterated out of
        prose in SOUL.md."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            (root / "_system").mkdir(parents=True, exist_ok=True)
            (root / "_system" / "SOUL.md").write_text(
                "---\nid: soul\n---\n\n## Identity\n\n- **Name:** Growth Arc\n",
                encoding="utf-8",
            )
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "2_areas/a.md", tags=["project/growth-arc"])
            result = _audit(root)
            self.assertEqual(result["owner"], "growth-arc")
            bucket = next(
                i for i in result["identities"] if i["id"] == "growth-arc"
            )
            self.assertIsNone(bucket["excluded"])
            self.assertEqual(bucket["residue_count"], 1)


# -----------------------------------------------------------------------------
# hub_kind must agree with the registry
# -----------------------------------------------------------------------------

class HubKindTests(unittest.TestCase):
    def _events(self, root: Path) -> list[dict]:
        return [
            e for e in _run_stream(root)
            if e["kind"] == "identity-hub-kind-mismatch"
        ]

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def test_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "alpha-app", hub_kind="domain")
            ev = self._events(root)
            self.assertEqual(len(ev), 1)
            self.assertEqual(ev[0]["identity"], "alpha-app")
            self.assertEqual(ev[0]["hub_kind"], "domain")
            self.assertEqual(ev[0]["registry_category"], "project")
            self.assertEqual(ev[0]["severity"], "strong")

    def test_agreement_is_silent_including_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "alpha-app")              # absent → project
            _write_hub(root, "growth-arc", hub_kind="trajectory")
            self.assertEqual(self._events(root), [])

    def test_hub_absent_from_the_registry_is_out_of_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_hub(root, "some-theme", hub_kind="domain")
            self.assertEqual(self._events(root), [])


# -----------------------------------------------------------------------------
# `--identity` — the gate is per-identity while the audit is global
# -----------------------------------------------------------------------------

class IdentityFilterTests(unittest.TestCase):
    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, _REGISTRY)
        return root

    def _run(self, root: Path, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = ia.main(["--root", str(root)] + argv)
        return code, buf.getvalue()

    def test_other_identities_are_dropped_from_the_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            _write_note(root, "2_areas/b.md", tags=["project/old-tool"])
            code, out = self._run(
                root, ["--identity", "old-tool", "--json", "--fail-on-residue"],
            )
            data = json.loads(out)
            self.assertEqual(code, 2)
            self.assertEqual([i["id"] for i in data["identities"]], ["old-tool"])
            self.assertEqual(data["residue_count"], 1)
            self.assertNotIn("legacy-thing", out)

    def test_clean_identity_passes_while_the_base_is_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            code, _ = self._run(
                root, ["--identity", "old-tool", "--json", "--fail-on-residue"],
            )
            self.assertEqual(code, 0)

    def test_unknown_identifier_exits_one_not_zero(self):
        """A typo and a retirement row that never landed are the ordinary
        causes. Reading "unknown" as "clean" closes a change against nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            code, _ = self._run(
                root, ["--identity", "never-existed", "--fail-on-residue"],
            )
            self.assertEqual(code, 1)

    def test_coverage_gaps_do_not_fail_one_identitys_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            (root / "7_experiments").mkdir()
            (root / "7_experiments" / "n.md").write_text("x\n", encoding="utf-8")
            code, _ = self._run(
                root, ["--identity", "old-tool", "--fail-on-residue"],
            )
            self.assertEqual(code, 0)

    # -- scope: what exit 0 actually means -------------------------------

    def test_audited_identity_reports_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            code, out = self._run(root, ["--identity", "old-tool", "--json"])
            data = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(data["identity_scope"], "audited")
            self.assertIsNone(data["identity_scope_reason"])
            self.assertTrue(data["clean"])

            _, text = self._run(root, ["--identity", "old-tool"])
            self.assertIn("clean: True", text)
            self.assertNotIn("NOT AUDITED", text)

    def test_live_identity_is_out_of_scope_not_clean(self):
        """A live project is outside `audited_categories`, so nothing about it
        is examined. Exit 0 stays right; the word «clean» does not."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            code, out = self._run(root, ["--identity", "alpha-app", "--json"])
            data = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(data["identity_scope"], "out-of-scope")
            self.assertEqual(data["identity_count"], 0)
            self.assertIn("`alpha-app` is live", data["identity_scope_reason"])

            _, text = self._run(root, ["--identity", "alpha-app"])
            self.assertIn("NOT AUDITED (out-of-scope)", text)
            self.assertNotIn("clean:", text)
            self.assertIn("no check applies", text)

    def test_void_identity_is_set_aside_not_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _TEMPLATE_REGISTRY)   # declares `void`
            code, out = self._run(root, ["--identity", "ghost-entry", "--json"])
            data = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(data["identity_scope"], "set-aside")
            self.assertIn("set aside", data["identity_scope_reason"])

            _, text = self._run(root, ["--identity", "ghost-entry"])
            self.assertIn("NOT AUDITED (set-aside)", text)

    def test_unfiltered_run_is_always_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _, out = self._run(root, ["--report", "--json"])
            data = json.loads(out)
            self.assertEqual(data["identity_scope"], "audited")
            self.assertIsNone(data["identity_scope_reason"])


# -----------------------------------------------------------------------------
# Every finding carries a machine code
# -----------------------------------------------------------------------------

class ReasonCodeTests(unittest.TestCase):
    """The consumer keys deduplication on the code.

    A code the consumer has to mint for itself differs between nights, so the
    same finding re-surfaces as new forever. Prose cannot carry that weight.
    """

    def test_every_finding_carries_a_known_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "_records/meetings/m.md", projects=["legacy-thing"])
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"],
                        body="[[legacy-thing]]\n")
            _write_note(root, "2_areas/b.md", tags=["project/growth-arc"])
            _write_note(root, "1_projects/legacy-thing.md")
            _write_note(root, "_system/views/INDEX.md", body="[[legacy-thing]]\n")
            _write_tag_registry(root, ["project/legacy-thing"])
            (root / "7_new").mkdir()
            (root / "7_new" / "n.md").write_text("x\n", encoding="utf-8")
            result = _audit(root)
            everything = (
                [f for i in result["identities"] for f in i["findings"]]
                + result["unclassified"] + result["registry_defects"]
            )
            self.assertTrue(everything)
            for f in everything:
                self.assertIn(f["kind"], ia.REASON_CODES, f)

    def test_codes_distinguish_the_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "_records/meetings/m.md", projects=["legacy-thing"])
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"],
                        body="[[legacy-thing]]\n")
            _write_note(root, "2_areas/b.md", tags=["project/growth-arc"])
            _write_note(root, "1_projects/legacy-thing.md")
            _write_note(root, "_system/views/INDEX.md", body="[[legacy-thing]]\n")
            codes = {
                (f["surface"], f["kind"])
                for i in _audit(root)["identities"] for f in i["findings"]
            }
            self.assertIn(("field", ia.CODE_FIELD_RETIRED), codes)
            self.assertIn(("tag", ia.CODE_TAG_RETIRED), codes)
            self.assertIn(("tag", ia.CODE_TAG_NAMESPACE), codes)
            self.assertIn(("wikilink", ia.CODE_WIKILINK_RETIRED), codes)
            self.assertIn(("node-card", ia.CODE_NODE_RELOCATE), codes)
            # a derived surface is stale output, whatever role it sits in
            self.assertIn(("wikilink", ia.CODE_DERIVED_STALE), codes)

    def test_repoint_has_its_own_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "1_projects/growth-arc.md")
            _write_hub(root, "growth-arc", hub_kind="trajectory")
            _write_note(root, "2_areas/a.md", body="[[growth-arc]]\n")
            codes = {
                f["kind"] for f in _findings(root, "growth-arc")
                if f["surface"] == "wikilink"
            }
            self.assertEqual(codes, {ia.CODE_WIKILINK_REPOINT})


# -----------------------------------------------------------------------------
# A renamed section heading must not un-retire everything under it
# -----------------------------------------------------------------------------

class RegistrySectionTests(unittest.TestCase):
    """The guard the old docstring asked for and did not get.

    An unrecognised heading used to fall through to `project`. Rename `##
    Retired Identifiers` — a friend tidying up, a translation, a future engine
    rename — and every retired identifier reads as an active one, while the
    audit reports clean because there is nothing retired left to have residue.
    """

    RENAMED = _DECLARED.replace(
        "## Retired Identifiers", "## Old identifiers we no longer use",
    ).format(rows="| legacy-thing | merge | `alpha-app` | 2026-01-02 | folded |")

    def _base(self, tmp: str) -> Path:
        root = Path(tmp)
        _scaffold(root)
        _write_projects_md(root, self.RENAMED)
        return root

    def test_unknown_heading_does_not_become_a_project_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            cats = registry_ids_by_category(parse_project_registry(root))
            self.assertNotIn("legacy-thing", cats["project"])
            self.assertNotIn("legacy-thing", cats["consolidated"])

    def test_unknown_heading_is_reported_once_for_the_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            result = _audit(root)
            defects = [
                d for d in result["registry_defects"]
                if d["kind"] == ia.CODE_SECTION_UNKNOWN
            ]
            self.assertEqual(len(defects), 1)
            self.assertEqual(defects[0]["current"],
                             "Old identifiers we no longer use")
            self.assertEqual(defects[0]["path"], "1_projects/PROJECTS.md")
            self.assertFalse(result["clean"])

    def test_the_renamed_registry_does_not_pass_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._base(tmp)
            _write_note(root, "2_areas/a.md", tags=["project/legacy-thing"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = ia.main([
                    "--root", str(root), "--report", "--fail-on-residue",
                ])
            self.assertEqual(code, 2)

    def test_both_retirement_headings_still_resolve(self):
        for heading in (
            "## Retired Identifiers",
            "## Consolidated / superseded",
            "## Retired identifiers (merge / rename / void)",
            "### Superseded",
        ):
            self.assertEqual(
                registry_section_category(heading), "consolidated", heading,
            )

    def test_the_real_registries_have_no_unknown_section(self):
        """The shipped registry and the owner's own must both classify whole —
        the whitelist is only safe if the sections in the wild are in it."""
        root = repo_root()
        if not (root / "1_projects" / "PROJECTS.md").is_file():  # pragma: no cover
            self.skipTest("no project registry in this checkout")
        result = ia.audit(root)
        self.assertEqual(
            [
                d["current"] for d in result["registry_defects"]
                if d["kind"] == ia.CODE_SECTION_UNKNOWN
            ],
            [],
        )

    def test_a_merge_naming_two_successors_is_a_defect_not_a_silent_choice(self):
        """The arity rule cannot catch what the parser already discarded.

        Reading only the first identifier makes a `merge` naming two look
        exactly like a `merge` naming one — and the scanner then migrates every
        reference to whichever happened to be written first.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _declared_registry(
                root,
                "| gone | merge | `alpha-app`, `beta-service` | 2026-01-02 | ? |",
            )
            entry = parse_project_registry(root)["gone"]
            self.assertEqual(entry.successors, ("alpha-app", "beta-service"))
            self.assertIsNone(entry.successor)
            _write_note(root, "2_areas/a.md", tags=["project/gone"])
            f = _findings(root, "gone")
            self.assertIn(
                ia.CODE_SUCCESSOR_FORBIDDEN, [x["kind"] for x in f],
            )
            for x in f:
                self.assertIsNone(x["target"])

    def test_no_node_surface_is_ever_autofixable(self):
        """Where a node belongs depends on what it CONTAINS, which no registry
        knows. The registry decides the identifier, never the home."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold(root)
            _write_projects_md(root, _REGISTRY)
            _write_note(root, "1_projects/legacy-thing.md")
            (root / "1_projects" / "legacy-thing").mkdir()
            (root / "1_projects" / "legacy-thing" / "README.md").write_text(
                "readme\n", encoding="utf-8",
            )
            _write_hub(root, "legacy-thing")
            nodes = [
                x for x in _findings(root, "legacy-thing")
                if x["kind"] == ia.CODE_NODE_RELOCATE
            ]
            self.assertEqual(len(nodes), 3)
            for x in nodes:
                self.assertFalse(x["autofixable"], x["surface"])
