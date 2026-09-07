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

    def test_a_skill_name_with_the_owners_tail_is_theirs_in_any_alphabet(self):
        """The old rule claimed only non-ASCII tails, so it protected a Cyrillic
        friend and renamed a Latin one — wrong for most of the people it exists
        for, and wrong on a property that has nothing to do with ownership."""
        for token in (f"ztn-process-{IV}", "ztn-process-ivanov", "ztn-lint-mine"):
            self.assertEqual(_spans(token), [token], token)

    def test_the_engines_own_compounds_are_not(self):
        for engine in ("ztn-process", "ztn-agent-lens-add", "ztn-process-skill",
                       "ztn-update-distribution-mechanism", "ztn-roles-abc123"):
            self.assertEqual(_spans(engine), [], engine)

    def test_the_engine_extension_list_is_re_derived_from_the_shipped_tree(self):
        """A list nothing re-derives is a list that goes stale in silence.

        Any engine artifact that extends a skill name reads today as
        `minder-mem-<skill>-<tail>` or `minder-memory-<skill>-<tail>`; its
        old-name equivalent must stay renameable, or the map will read it as the
        owner's and freeze it. This re-runs that derivation over the shipped
        tree and fails when a new one appears unlisted.
        """
        import re as _re
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
        from lib.manifest import read_section_lite  # noqa: PLC0415

        pattern = _re.compile(r"(?<![\w-])minder-(?:mem|memory)-([a-z][\w-]*)")
        derived = set()
        for entry in read_section_lite(_REPO_ROOT / ".engine-manifest.yml", "engine"):
            target = _REPO_ROOT / entry.rstrip("/")
            files = ([q for q in target.rglob("*") if q.is_file()] if target.is_dir()
                     else ([target] if target.is_file() else []))
            for f in files:
                if "__pycache__" in f.parts:
                    continue
                try:
                    text = f.read_bytes().decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                # A file that opts out of the rename is declaring that its
                # old- and new-name tokens are INPUTS — a test fixture, a
                # matcher, an example in a docstring — not artifacts the engine
                # names. Counting those would make every example a rule.
                if "minder-memory-rebrand: keep-legacy-tokens" in text:
                    continue
                for hit in pattern.finditer(text):
                    tail = hit.group(1).rstrip("-")
                    if not tail or tail in ownership.ENGINE_SKILL_NAMES:
                        continue
                    parts = tail.split("-")
                    for n in range(len(parts) - 1, 0, -1):
                        if "-".join(parts[:n]) in ownership.ENGINE_SKILL_NAMES:
                            derived.add("ztn-" + tail)
                            break

        self.assertTrue(derived, "the derivation found nothing — it has stopped working")
        unlisted = [tok for tok in sorted(derived) if _spans(tok) != []]
        self.assertEqual(unlisted, [],
                         "engine forms the map would now freeze as the owner's: "
                         f"{unlisted}. Add them to ENGINE_EXTENDED_SKILL_TOKENS "
                         "or ENGINE_EXTENDED_SKILL_SUFFIXES.")


class FormerSpellingTests(unittest.TestCase):
    """What a damaged name used to be — proposed here, decided by the old text."""

    def test_both_separators_and_the_doubled_shape(self):
        self.assertEqual(ownership.former_spellings(f"minder-memory-{IV}"),
                         [f"minder-ztn-{IV}"])
        self.assertEqual(ownership.former_spellings(f"minder-minder-memory-{IV}"),
                         [f"minder-ztn-{IV}"])
        # What 1.0.0 made of `minder-ztn_<tail>`: the underscore rule fired
        # inside a name it should never have entered.
        self.assertEqual(ownership.former_spellings(f"minder-minder_memory_{IV}"),
                         [f"minder-ztn_{IV}"],
                         "both separators are captured; they need not be the same")

    def test_a_renamed_skill_extension_offers_its_real_predecessor(self):
        """`minder-memory-process-x` was `ztn-process-x`, not `minder-ztn-process-x`."""
        self.assertEqual(ownership.former_spellings(f"minder-memory-process-{IV}"),
                         [f"minder-ztn-process-{IV}", f"ztn-process-{IV}"])


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
