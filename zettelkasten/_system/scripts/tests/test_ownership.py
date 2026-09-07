"""`scripts/lib/ownership.py` — the one home of the engine/owner name boundary.

Seven walkthroughs of the rename produced defects of a single shape: a boundary
between engine-owned and owner-owned names, drawn one notch too narrow, fixed
where it was found, and then restated in two or three files that had to be
pinned equal by tests. This module is the fix for the class, and this suite is
the audit's own findings turned into a standing question.

Every case here is one the eighth walkthrough actually found.
"""
# minder-memory-rebrand: keep-legacy-tokens — the former names are this suite's subject.

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from lib import ownership  # noqa: E402

IV = "\u0438\u0432\u0430\u043d\u043e\u0432"                       # иванов
SKILL = "\u043c\u043e\u0439-\u0441\u043a\u0438\u043b\u043b"       # мой-скилл


def _spans(text: str, base: Path | None = None) -> list[str]:
    return [text[a:b] for a, b in ownership.own_name_spans(text, base)]


class EnvNameTests(unittest.TestCase):
    def test_the_engines_own_variables_are_the_engines(self):
        for name in ("ZTN_BASE", "ZTN_ROLES_KEY", "MINDER_ZTN_BASE", "ZTN_SECRET_MASTER_KEY"):
            self.assertTrue(ownership.is_engine_env_name(name), name)

    def test_anything_else_shaped_like_one_is_the_owners(self):
        # No `[A-Z]` anchor after the underscore: these are names people write.
        for name in ("ZTN_TELEGRAM_TOKEN", "ZTN_2FA_SECRET", "ZTN_Telegram_Token"):
            self.assertFalse(ownership.is_engine_env_name(name), name)
            self.assertEqual(_spans(f"secrets:\n  - {name}\n"), [name])

    def test_a_name_the_owner_declared_is_theirs_even_when_it_collides(self):
        """The engine's list is not the last word — a declaration outranks it.

        A friend may have called their token `ZTN_PATH` years ago. Renaming it
        because the engine once used that name breaks their role and names a
        variable they never wrote.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "zettelkasten"
            (base / "_system" / "roles" / "digest").mkdir(parents=True)
            (base / "_system" / "state").mkdir(parents=True)
            (base / "_system" / "roles" / "digest" / "role.md").write_text(
                "---\nid: digest\nsecrets:\n  - ZTN_PATH\n---\n", encoding="utf-8")
            self.assertTrue(ownership.is_engine_env_name("ZTN_PATH"))
            self.assertFalse(ownership.is_engine_env_name("ZTN_PATH", base))

            (base / "_system" / "state" / "secrets.enc.json").write_text(
                '{"ZTN_DEV":"' + "x" * 40 + '"}\n', encoding="utf-8")
            self.assertFalse(ownership.is_engine_env_name("ZTN_DEV", base))


class OwnNameSpanTests(unittest.TestCase):
    def test_a_tail_may_be_joined_by_hyphen_or_underscore_in_any_script(self):
        self.assertEqual(_spans(f"~/minder-ztn-{IV}/zettelkasten"), [f"minder-ztn-{IV}"])
        self.assertEqual(_spans(f"deploy@box:/srv/minder_ztn_{IV}"), [f"minder_ztn_{IV}"])

    def test_the_engines_own_identifiers_keep_their_shape(self):
        for engine in ("minder_ztn_session", "minder-ztn-platform", "MINDER_ZTN_BASE"):
            self.assertEqual(_spans(engine), [], engine)

    def test_a_skill_name_with_the_owners_tail_is_theirs(self):
        self.assertEqual(_spans(f"ztn-process-{IV}"), [f"ztn-process-{IV}"])

    def test_the_engines_own_compounds_are_not(self):
        for engine in ("ztn-process", "ztn-agent-lens-add", "ztn-process-skill",
                       "ztn-update-distribution-mechanism", "ztn-roles-abc123"):
            self.assertEqual(_spans(engine), [], engine)


class HarnessEntryTests(unittest.TestCase):
    def test_only_what_the_engine_shipped_is_the_engines(self):
        self.assertTrue(ownership.is_engine_legacy_harness_entry("ztn.md", "rules"))
        self.assertTrue(ownership.is_engine_legacy_harness_entry("ztn-process", "skills"))
        self.assertTrue(ownership.is_engine_legacy_harness_entry("ztn-role.md", "agents"))

    def test_an_owners_own_harness_file_is_never_the_engines(self):
        """The old test was a `ztn-` prefix, and this migration DELETES what it matches."""
        self.assertFalse(ownership.is_engine_legacy_harness_entry(f"ztn-{SKILL}", "skills"))
        self.assertFalse(ownership.is_engine_legacy_harness_entry("my-ztn-notes.md", "rules"))
        self.assertFalse(ownership.is_engine_legacy_harness_entry("ztn-notes.md", "rules"))


class PathTests(unittest.TestCase):
    def test_owner_space_reads_the_manifests_own_exclusions(self):
        """Two lists answering «whose file is this» drift the moment one is edited."""
        self.assertTrue(ownership.in_owner_space("zettelkasten/1_projects/x.md", _REPO_ROOT))
        self.assertTrue(ownership.in_owner_space("platform/design.md", _REPO_ROOT),
                        "the manifest excludes platform/, so it is not the engine's")
        self.assertFalse(ownership.in_owner_space("integrations/claude-code/install.sh",
                                                  _REPO_ROOT))

    def test_a_tail_is_the_engines_only_when_the_whole_path_is(self):
        self.assertTrue(ownership.is_engine_owned_name("integrations/minder-memory-mcp",
                                                       _REPO_ROOT))
        self.assertFalse(ownership.is_engine_owned_name("~/repos/minder-memory-mcp", _REPO_ROOT),
                         "in an owner's note this names something of theirs")
        self.assertTrue(ownership.is_engine_owned_name(
            "$CLAUDE_HOME/.minder-memory-backup-20260101", _REPO_ROOT))


class OneHomeTests(unittest.TestCase):
    def test_no_consumer_restates_the_rule(self):
        """The property that replaced four releases' worth of parity tests."""
        roots = [str(_REPO_ROOT / "scripts"), str(_REPO_ROOT / "zettelkasten/_system/scripts")]
        for symbol in ("ENGINE_ENV_NAMES", "ENGINE_SKILL_NAMES", "ENGINE_LEGACY_HARNESS",
                       "OWNER_DATA_PREFIXES"):
            found = subprocess.run(["grep", "-rn", "--include=*.py", f"^{symbol}", *roots],
                                   capture_output=True, text=True, encoding="utf-8").stdout
            lines = [ln for ln in found.splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1, f"{symbol} defined {len(lines)}x:\n{found}")
            self.assertIn("lib/ownership.py", lines[0])


if __name__ == "__main__":
    unittest.main()
