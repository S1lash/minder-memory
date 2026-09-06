"""Tests for roles_context — what the role is given (CORE-SPEC §4).

Proves the six-part ordering, full placeholder substitution, the hard error on
a missing `_run-frame.md` against the tolerated-with-a-marker `_minder.md`, the
`constitution:` gate, the previous-run line, the state inventory, and the
budget rules — including the one that matters most: a single file larger than
the budget is INLINED and marked, never demoted to a name-only listing, because
a role whose job is to maintain one large document would otherwise regenerate
it from scratch and destroy the accumulated work while every surface reported
success.

Three absences, three deliberately different postures (§4): `_run-frame.md`
missing is a HARD ERROR (engine-owned, a broken install), while `_minder.md`
and `constitution-core.md` each yield their own marker and continue. Getting
those three the same way round is the difference between a role that runs
without its mechanics and one that stops for a regenerable view.

The budget counts FILE CONTENT only — header lines are not charged, so the
inventory of a role with many small files cannot be squeezed out by its own
headers.

Determinism: `now` is injected and timezone-aware; no wall clock, no network,
every fixture in a tmp dir.

INFERENCE, flagged (see the report): `{{REPO_ROOT}}` renders `repo` and
`{{BASE}}` renders `base` — the two arguments `build_context` is given.
"""

from __future__ import annotations

import hashlib
import inspect
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests._roles_fixture import (  # type: ignore
    CONSTITUTION_TEXT,
    DEFAULT_BODY,
    MINDER_TEXT,
    PLACEHOLDERS,
    make_base,
    role_config,
    roles_dir,
    write_bytes,
    write_constitution_view,
    write_minder,
    write_prefix,
    write_run_frame,
    write_secrets,
    write_state,
)
import roles_context as ctx  # type: ignore

WEST = timezone(timedelta(hours=-5))
NOW = datetime(2026, 7, 28, 7, 0, tzinfo=WEST)

MINDER_MISSING = "[_minder.md missing — base conventions unavailable]"
CONSTITUTION_MISSING = "[constitution-core.md missing — run /minder:mem:regen-constitution]"
PREV_NONE = "[previous run: none]"

LAST_RUN_LINE = {
    "ts": "2026-07-27T12:00:11Z",
    "role": "notion-sync",
    "outcome": "ok",
    "writes": 2,
    "reverted": [],
    "reported_only": [],
    "ms": 41200,
    "note": None,
}


def _fixture(tmp) -> tuple[Path, Path]:
    """A base with run frame + minder preamble + constitution view present."""
    base = make_base(Path(tmp))
    write_run_frame(base)
    write_minder(base)
    write_constitution_view(base)
    (roles_dir(base) / "notion-sync" / "state").mkdir(parents=True, exist_ok=True)
    return base, base.parent


def _build(base: Path, repo: Path, cfg, **kwargs) -> str:
    payload = {"now": NOW, "last_run_line": None}
    payload.update(kwargs)
    return ctx.build_context(base, repo, cfg, **payload)


def _tree_digest(base: Path) -> dict:
    return {
        str(p.relative_to(base)): hashlib.md5(p.read_bytes()).hexdigest()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


# ==========================================================================
# run frame
# ==========================================================================

class RunFrameTests(unittest.TestCase):
    def test_every_placeholder_is_substituted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base))
            for ph in PLACEHOLDERS:
                with self.subTest(placeholder=ph):
                    self.assertNotIn(ph, out)
            self.assertNotIn("{{", out, "no placeholder may survive unsubstituted")

    def test_role_id_and_name_are_substituted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, name="Ноушн-сверщик"))
            self.assertIn("notion-sync", out)
            self.assertIn("Ноушн-сверщик", out)

    def test_base_repo_root_and_state_dir_are_substituted_with_real_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            cfg = role_config(base)
            out = _build(base, repo, cfg)
            self.assertIn(str(base), out)
            self.assertIn(str(repo), out)
            self.assertIn(str(cfg.state_dir), out)

    def test_allowed_writes_renders_the_expanded_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            cfg = role_config(base, write_prefixes=(
                write_prefix("zettelkasten/_system/roles/notion-sync/state/"),
                write_prefix("zettelkasten/_sources/inbox/roles/", flat=True),
            ))
            out = _build(base, repo, cfg).replace("\\", "/")
            self.assertIn("zettelkasten/_system/roles/notion-sync/state/", out)
            self.assertIn("zettelkasten/_sources/inbox/roles/", out)

    def test_allowed_writes_is_still_substituted_for_a_read_only_role(self):
        """SIBLING — an empty allowlist must render as an explicit nothing,
        never as a leftover `{{ALLOWED_WRITES}}` the model reads as an
        instruction."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, write_prefixes=()))
            self.assertNotIn("{{ALLOWED_WRITES}}", out)
            self.assertNotIn("{{", out)

    def test_now_local_honours_the_injected_now(self):
        """§4: a role whose question is "the last week" must not derive today
        from the ambient harness — under an injected `--now` the runner and the
        role would disagree."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base),
                         now=datetime(2026, 3, 9, 18, 45, tzinfo=WEST))
            self.assertIn("2026-03-09", out)
            self.assertIn("18:45", out)
            self.assertNotIn("2026-07-28", out)

    def test_now_local_renders_local_wall_clock_not_utc(self):
        """SIBLING / the same trap as §2: the owner at UTC-5 must be told their
        own 07:00, not 12:00Z."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base),
                         now=datetime(2026, 7, 28, 7, 0, tzinfo=WEST))
            self.assertIn("07:00", out)
            self.assertNotIn("12:00", out)

    def test_secret_names_are_substituted_but_values_never_appear(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_secrets(base, {"NOTION_TOKEN": "secret-value-do-not-leak"})
            out = _build(base, repo, role_config(base, secrets=("NOTION_TOKEN",)))
            self.assertIn("NOTION_TOKEN", out)
            self.assertNotIn("secret-value-do-not-leak", out)

    def test_the_rendered_secrets_file_is_outside_the_repository(self):
        """§6.4 — the property the whole design rests on, and the one that
        survives a change of temp-dir naming.

        `{{SECRETS_FILE}}` points at a decrypted file in the OS temp
        directory. Outside the repository is load-bearing three times over:
        `git status` never sees it, staging can never pick it up, and it
        cannot survive into a commit by any path. So the assertion is on the
        property — outside the repo — not on a literal path, which would pin
        temp-dir naming and prove nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, secrets=("NOTION_TOKEN",)))
            rendered = [ln.split(": ", 1)[1].strip()
                        for ln in out.splitlines() if ln.startswith("secrets_file: ")]
            self.assertEqual(len(rendered), 1, out)
            path = Path(rendered[0])
            self.assertTrue(path.is_absolute())
            self.assertNotIn(str(repo.resolve()), str(path.resolve()),
                             "the decrypted store would be inside the repository")

    def test_the_rendered_secrets_file_is_not_the_committed_store(self):
        """SIBLING — the role sources plaintext, so the placeholder must never
        resolve to the ciphertext blob it was decrypted from."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, secrets=("NOTION_TOKEN",)))
            self.assertNotIn("secrets.enc.json", out)

    def test_secret_names_substituted_for_a_role_with_no_secrets(self):
        """SIBLING — most roles declare none; the placeholder must still go."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, secrets=()))
            self.assertNotIn("{{SECRET_NAMES}}", out)

    def test_another_roles_secret_value_and_name_never_leak_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_secrets(base, {"OTHER_TOKEN": "another-secret-value"})
            out = _build(base, repo, role_config(base, secrets=()))
            self.assertNotIn("another-secret-value", out)
            self.assertNotIn("OTHER_TOKEN", out)

    def test_missing_run_frame_raises(self):
        """§4: engine-owned; its absence means a broken install, and tolerating
        it would run a role with no mechanics."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_minder(base)
            with self.assertRaises(Exception) as exc:
                _build(base, base.parent, role_config(base))
            self.assertIn("_run-frame", str(exc.exception))

    def test_present_run_frame_with_every_placeholder_is_accepted(self):
        """SIBLING — a placeholder-complete frame is the shipped shape."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            self.assertTrue(_build(base, repo, role_config(base)).strip())


# ==========================================================================
# _minder.md — tolerated absence
# ==========================================================================

class MinderPreambleTests(unittest.TestCase):
    def test_missing_minder_file_yields_the_spec_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            out = _build(base, base.parent, role_config(base))
            self.assertIn(MINDER_MISSING, out)

    def test_missing_minder_file_does_not_stop_the_run(self):
        """It is prose; a role can still do useful work without it."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            out = _build(base, base.parent, role_config(base, body="ТЕЛО-РОЛИ\n"))
            self.assertIn("ТЕЛО-РОЛИ", out)

    def test_present_minder_file_is_included_verbatim(self):
        """SIBLING — wave 2's prose passed through untouched, `---` and all."""
        text = "# How the base works\n\nWrite only to your own folder.\n\n---\n\nAnd inbox.\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            write_minder(base, text)
            out = _build(base, base.parent, role_config(base))
            self.assertIn(text.strip(), out)
            self.assertNotIn(MINDER_MISSING, out)


# ==========================================================================
# constitution gate
# ==========================================================================

class ConstitutionTests(unittest.TestCase):
    def test_constitution_false_omits_the_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, constitution=False))
            self.assertNotIn("axiom-identity-001", out)

    def test_constitution_true_includes_the_view_verbatim(self):
        """SIBLING — the flag's whole purpose."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, constitution=True))
            self.assertIn(CONSTITUTION_TEXT.strip(), out)

    def test_missing_constitution_view_with_flag_false_is_not_an_error(self):
        """SIBLING — a base that never rendered the view is normal for a role
        that does not ask for it."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            write_minder(base)
            out = _build(base, base.parent, role_config(base, constitution=False))
            self.assertTrue(out.strip())

    def test_missing_constitution_view_with_flag_true_yields_the_spec_marker(self):
        """§4: a derived view's absence means the owner never regenerated it,
        not that the install is broken — so it is a marker and the run
        continues, deliberately unlike `_run-frame.md`."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            write_minder(base)
            out = _build(base, base.parent, role_config(base, constitution=True))
            self.assertIn(CONSTITUTION_MISSING, out)

    def test_missing_constitution_view_does_not_stop_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            write_minder(base)
            out = _build(base, base.parent,
                         role_config(base, constitution=True, body="ТЕЛО-РОЛИ\n"))
            self.assertIn("ТЕЛО-РОЛИ", out)

    def test_present_constitution_view_yields_no_missing_marker(self):
        """SIBLING — the marker must not fire when the view is there."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, constitution=True))
            self.assertNotIn(CONSTITUTION_MISSING, out)

    def test_no_constitution_marker_when_the_flag_is_false(self):
        """SIBLING — a role that never asked for the view must not be told the
        view is missing; that would be noise on every single run."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            write_minder(base)
            out = _build(base, base.parent, role_config(base, constitution=False))
            self.assertNotIn(CONSTITUTION_MISSING, out)


# ==========================================================================
# previous-run line
# ==========================================================================

class PreviousRunTests(unittest.TestCase):
    def test_previous_run_line_renders_outcome_ts_and_note(self):
        """§4: without it a role cannot detect that its predecessor died
        mid-flight and will redo an already-performed outward act."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            line = dict(LAST_RUN_LINE, outcome="error", note="notion timeout")
            out = _build(base, repo, role_config(base), last_run_line=line)
            self.assertIn("previous run", out)
            self.assertIn("error", out)
            self.assertIn("2026-07-27T12:00:11Z", out)
            self.assertIn("notion timeout", out)

    def test_absent_previous_run_renders_the_none_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base), last_run_line=None)
            self.assertIn(PREV_NONE, out)

    def test_previous_run_with_a_null_note_still_renders(self):
        """SIBLING — a successful run carries `note: null`, the common case."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base), last_run_line=LAST_RUN_LINE)
            self.assertIn("previous run", out)
            self.assertIn("ok", out)
            self.assertNotIn(PREV_NONE, out)

    def test_previous_run_with_a_cyrillic_note_renders_intact(self):
        """SIBLING — the note may be the owner's language when it came from a
        role's own structured return."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            line = dict(LAST_RUN_LINE, outcome="idle", note="доска не менялась")
            out = _build(base, repo, role_config(base), last_run_line=line)
            self.assertIn("доска не менялась", out)


# ==========================================================================
# ordering
# ==========================================================================

class OrderingTests(unittest.TestCase):
    def test_parts_appear_in_the_documented_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "seen.txt", "МАРКЕР-СОСТОЯНИЯ\n")
            out = _build(
                base, repo,
                role_config(base, constitution=True, body="МАРКЕР-ТЕЛА-РОЛИ\n"),
                last_run_line=LAST_RUN_LINE,
            )
            i_frame = out.index("role_id:")
            i_minder = out.index(MINDER_TEXT.splitlines()[-1])
            i_const = out.index("axiom-identity-001")
            i_prev = out.index("previous run")
            i_body = out.index("МАРКЕР-ТЕЛА-РОЛИ")
            i_state = out.index("МАРКЕР-СОСТОЯНИЯ")
            self.assertLess(i_frame, i_minder)
            self.assertLess(i_minder, i_const)
            self.assertLess(i_const, i_prev)
            self.assertLess(i_prev, i_body)
            self.assertLess(i_body, i_state)

    def test_body_is_included_verbatim_including_horizontal_rules(self):
        """SIBLING — the body goes to the model verbatim; `---` and a fenced
        YAML block inside it must survive untouched."""
        body = "## Задача\n\n---\n\n```yaml\nid: not-a-role\n```\n"
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, body=body))
            self.assertIn(body.strip(), out)

    def test_parts_are_separated_so_they_cannot_run_together(self):
        """Each part starts on its own line — a mechanic and an instruction
        must never share one."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, body="ТЕЛО-РОЛИ\n"))
            body_lines = [ln for ln in out.splitlines() if "ТЕЛО-РОЛИ" in ln]
            self.assertTrue(body_lines)
            for line in body_lines:
                self.assertNotIn("last_run", line)


# ==========================================================================
# state inventory
# ==========================================================================

class StateInventoryTests(unittest.TestCase):
    def test_state_files_are_listed_sorted_by_path_with_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "zebra.txt", "z" * 241)
            write_state(base, "notion-sync", "alpha.txt", "a" * 137)
            out = _build(base, repo, role_config(base))
            self.assertLess(out.index("alpha.txt"), out.index("zebra.txt"))
            self.assertIn("137", out)
            self.assertIn("241", out)

    def test_state_header_line_carries_the_repo_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "seen.txt", "2026-07-28\n")
            out = _build(base, repo, role_config(base)).replace("\\", "/")
            self.assertIn(
                "zettelkasten/_system/roles/notion-sync/state/seen.txt", out
            )

    def test_state_subdirectories_are_walked_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "nested/deep/inner.txt", "ГЛУБОКО\n")
            self.assertIn("ГЛУБОКО", _build(base, repo, role_config(base)))

    def test_cyrillic_state_filename_and_content_are_inlined(self):
        """SIBLING — the owner names their own state files, in their own
        script, and §0 requires the read to be explicit UTF-8."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "расхождения.md", "открытых: 3\n")
            out = _build(base, repo, role_config(base))
            self.assertIn("расхождения.md", out)
            self.assertIn("открытых: 3", out)

    def test_empty_state_dir_produces_no_truncation_marker(self):
        """SIBLING — a role that has not written anything yet is normal."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            self.assertNotIn("state truncated", _build(base, repo, role_config(base)))

    def test_missing_state_dir_is_tolerated(self):
        """SIBLING — a read-only role legitimately has no `state/` at all."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_run_frame(base)
            write_minder(base)
            out = _build(base, base.parent, role_config(base, write_prefixes=()))
            self.assertTrue(out.strip())
            self.assertNotIn("state truncated", out)

    def test_zero_byte_state_file_is_listed_not_skipped(self):
        """SIBLING — an empty file is state too; dropping it silently would
        hide that the role created it."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "empty.txt", "")
            self.assertIn("empty.txt", _build(base, repo, role_config(base)))

    def test_state_file_with_crlf_content_is_inlined_without_mangling(self):
        """SIBLING — a role may write CRLF on Windows; the inventory inlines
        the content rather than refusing it."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_bytes(roles_dir(base) / "notion-sync" / "state" / "crlf.txt",
                        b"first\r\nsecond\r\n")
            out = _build(base, repo, role_config(base))
            self.assertIn("first", out)
            self.assertIn("second", out)

    def test_only_this_roles_state_is_inlined(self):
        """A role must never receive another role's memory."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "mine.txt", "МОЁ\n")
            write_state(base, "other-role", "theirs.txt", "ЧУЖОЕ\n")
            out = _build(base, repo, role_config(base))
            self.assertIn("МОЁ", out)
            self.assertNotIn("ЧУЖОЕ", out)


class BinaryStateTests(unittest.TestCase):
    def test_binary_state_file_is_marked_and_never_inlined(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_bytes(roles_dir(base) / "notion-sync" / "state" / "snapshot.png",
                        b"\x89PNG\r\n\x1a\n\x00\xff\xfe" * 20)
            out = _build(base, repo, role_config(base))
            self.assertIn("snapshot.png", out)
            self.assertIn("(binary,", out)
            self.assertNotIn("\x89PNG", out)

    def test_binary_state_file_reports_its_byte_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_bytes(roles_dir(base) / "notion-sync" / "state" / "snapshot.png",
                        b"\x00" * 123)
            self.assertIn("(binary, 123 bytes)", _build(base, repo, role_config(base)))

    def test_utf8_text_is_not_mistaken_for_binary(self):
        """SIBLING — non-ASCII is not binary. Misclassifying a Cyrillic state
        file would blind the role to its own memory."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "заметки.md", "многобайтный текст\n")
            out = _build(base, repo, role_config(base))
            self.assertIn("многобайтный текст", out)
            self.assertNotIn("(binary,", out)

    def test_a_single_embedded_nul_makes_an_otherwise_valid_text_file_binary(self):
        """§4 — the NUL check is git's own rule and runs BEFORE the decode
        attempt. This file decodes as UTF-8 perfectly well, so a
        decode-only test would inline it and ship a NUL into the model's
        context. Only the ordering of the two checks makes this pass."""
        payload = "hello\x00world, otherwise perfectly readable text\n"
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            path = roles_dir(base) / "notion-sync" / "state" / "sneaky.md"
            write_bytes(path, payload.encode("utf-8"))
            payload.encode("utf-8").decode("utf-8")  # the premise: it decodes
            out = _build(base, repo, role_config(base))
            self.assertIn("sneaky.md", out)
            self.assertIn("(binary,", out)
            self.assertNotIn("otherwise perfectly readable text", out)
            self.assertNotIn("\x00", out)

    def test_a_nul_in_a_cyrillic_file_is_binary_too(self):
        """The two checks must not be order-dependent on the alphabet: a
        multibyte file with a NUL is binary for the NUL, not for the decode."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            path = roles_dir(base) / "notion-sync" / "state" / "заметки.md"
            write_bytes(path, "открытых: 3\x00ещё\n".encode("utf-8"))
            out = _build(base, repo, role_config(base))
            self.assertIn("(binary,", out)
            self.assertNotIn("открытых: 3", out)

    def test_a_file_that_fails_the_utf8_decode_is_also_binary(self):
        """SIBLING of the NUL rule — the second half of the same sentence:
        undecodable bytes are binary even with no NUL in them."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            path = roles_dir(base) / "notion-sync" / "state" / "latin1.md"
            write_bytes(path, "café".encode("latin-1"))  # 0xE9, invalid UTF-8
            self.assertNotIn(b"\x00", path.read_bytes())
            out = _build(base, repo, role_config(base))
            self.assertIn("latin1.md", out)
            self.assertIn("(binary,", out)

    def test_text_with_other_control_characters_is_not_binary(self):
        """SIBLING — only NUL is the marker. A tab, a form feed or an escape
        sequence in a role's own log-style state file is ordinary text, and
        refusing to inline it would blind the role to its memory."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "log.txt", "col1\tcol2\x0c\x1b[0m done\n")
            out = _build(base, repo, role_config(base))
            self.assertIn("col1\tcol2", out)
            self.assertNotIn("(binary,", out)


class BudgetTests(unittest.TestCase):
    A = "A" * 100
    B = "B" * 100

    def _two_files(self, tmp):
        base, repo = _fixture(tmp)
        write_state(base, "notion-sync", "a.txt", self.A)
        write_state(base, "notion-sync", "b.txt", self.B)
        return base, repo

    def test_just_under_budget_inlines_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = self._two_files(tmp)
            out = _build(base, repo, role_config(base), budget=201)
            self.assertIn(self.A, out)
            self.assertIn(self.B, out)
            self.assertNotIn("state truncated", out)
            self.assertNotIn("[truncated:", out)

    def test_exactly_at_budget_inlines_everything(self):
        """Boundary: 200 characters of content against a 200 budget is not
        exhausted, so nothing truncates."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = self._two_files(tmp)
            out = _build(base, repo, role_config(base), budget=200)
            self.assertIn(self.A, out)
            self.assertIn(self.B, out)
            self.assertNotIn("state truncated", out)

    def test_header_lines_are_not_charged_against_the_budget(self):
        """§4: the budget counts file CONTENT only, so the inventory of a role
        with many small files cannot be squeezed out by its own headers. These
        twenty files hold 200 characters between them but their long header
        paths run to several times that."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            for i in range(20):
                write_state(base, "notion-sync",
                            f"a-rather-long-state-file-name-{i:02d}.md", "z" * 10)
            out = _build(base, repo, role_config(base), budget=200)
            self.assertNotIn("state truncated", out)
            self.assertNotIn("[truncated:", out)
            for i in range(20):
                self.assertIn(f"a-rather-long-state-file-name-{i:02d}.md", out)

    def test_just_over_budget_truncates_the_second_file_to_what_remains(self):
        """§4: "larger than the REMAINING budget" — after `a` consumes 100 of
        199, `b` does not fit in the 99 left, so it is inlined up to 99 and
        marked. It is NOT demoted to a listing: some of the file beats none."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = self._two_files(tmp)
            out = _build(base, repo, role_config(base), budget=199)
            self.assertIn(self.A, out)
            self.assertIn("B" * 99, out)
            self.assertNotIn("B" * 100, out)
            self.assertIn("[truncated: 99 of 100 characters shown]", out)
            self.assertNotIn("state truncated", out)

    def test_state_truncated_marker_counts_the_remaining_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
                write_state(base, "notion-sync", name, name[0] * 100)
            out = _build(base, repo, role_config(base), budget=100)
            self.assertIn("a" * 100, out)
            self.assertIn("[state truncated: 3 more files]", out)
            for name in ("b.txt", "c.txt", "d.txt"):
                self.assertIn(name, out)
                self.assertNotIn(name[0] * 100, out)

    def test_an_over_budget_file_is_truncated_to_the_partly_spent_remainder(self):
        """The general case of the clause: 60 characters already spent out of
        100, so the 300-character file is inlined up to the 40 that remain and
        marked with its FULL size, not the remainder."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "a.txt", "A" * 60)
            write_state(base, "notion-sync", "b.txt", "X" * 300)
            out = _build(base, repo, role_config(base), budget=100)
            self.assertIn("A" * 60, out)
            self.assertIn("X" * 40, out)
            self.assertNotIn("X" * 41, out)
            self.assertIn("[truncated: 40 of 300 characters shown]", out)
            self.assertNotIn("state truncated", out)

    def test_when_nothing_remains_the_file_is_listed_not_an_empty_block(self):
        """The other side: with the budget exactly exhausted there is nothing
        to inline, so the file joins the listing rather than emitting a
        `[truncated: 0 of N …]` block with no content under it."""
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "a.txt", "A" * 100)
            write_state(base, "notion-sync", "b.txt", "X" * 300)
            out = _build(base, repo, role_config(base), budget=100)
            self.assertIn("A" * 100, out)
            self.assertNotIn("X", out)
            self.assertNotIn("[truncated: 0 of", out)
            self.assertIn("state truncated", out)
            self.assertIn("b.txt", out)
            self.assertIn("300", out)

    def test_a_single_file_larger_than_the_budget_is_inlined_and_marked(self):
        """§4's load-bearing budget rule. Handing a role the NAME of the one
        document it must maintain and none of its content makes it regenerate
        from scratch and destroy the accumulated work, while every surface
        reports success."""
        payload = "X" * 300
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "big.md", payload)
            out = _build(base, repo, role_config(base), budget=100)
            self.assertIn("X" * 100, out)
            self.assertIn("[truncated: 100 of 300 characters shown]", out)
            self.assertNotIn(payload, out)

    def test_a_single_file_larger_than_the_budget_is_not_demoted_to_a_listing(self):
        payload = "X" * 300
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "big.md", payload)
            out = _build(base, repo, role_config(base), budget=100)
            self.assertNotIn("state truncated", out)

    def test_a_large_file_within_the_default_budget_is_inlined_whole(self):
        """SIBLING — a 30k-character state file is legitimate and must not be
        truncated just for being big."""
        payload = "ы" * 30_000
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "big.md", payload)
            out = _build(base, repo, role_config(base))
            self.assertIn(payload, out)
            self.assertNotIn("[truncated:", out)
            self.assertNotIn("state truncated", out)

    def test_default_budget_is_40000_characters(self):
        self.assertEqual(
            inspect.signature(ctx.build_context).parameters["budget"].default, 40_000
        )

    def test_budget_now_and_last_run_line_are_keyword_only(self):
        params = inspect.signature(ctx.build_context).parameters
        for name in ("now", "last_run_line", "budget"):
            with self.subTest(param=name):
                self.assertEqual(params[name].kind, inspect.Parameter.KEYWORD_ONLY)


# ==========================================================================
# purity, determinism, engine-language
# ==========================================================================

class PurityTests(unittest.TestCase):
    def test_build_context_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "seen.txt", "2026-07-01\n")
            write_secrets(base, {"NOTION_TOKEN": "v"})
            before = _tree_digest(base)
            _build(base, repo,
                   role_config(base, constitution=True, secrets=("NOTION_TOKEN",)),
                   last_run_line=LAST_RUN_LINE)
            self.assertEqual(before, _tree_digest(base))

    def test_run_frame_template_is_not_mutated_by_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            frame = roles_dir(base) / "_run-frame.md"
            before = frame.read_text(encoding="utf-8")
            _build(base, repo, role_config(base))
            self.assertEqual(frame.read_text(encoding="utf-8"), before)
            self.assertIn("{{ROLE_ID}}", before)

    def test_build_context_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            write_state(base, "notion-sync", "seen.txt", "2026-07-01\n")
            cfg = role_config(base)
            self.assertEqual(_build(base, repo, cfg), _build(base, repo, cfg))

    def test_context_is_a_non_empty_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base))
            self.assertIsInstance(out, str)
            self.assertTrue(out.strip())

    def test_default_body_reaches_the_model_unparsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, repo = _fixture(tmp)
            out = _build(base, repo, role_config(base, body=DEFAULT_BODY))
            self.assertIn("## Проверка", out)
            self.assertIn("## Завершение", out)

    def test_module_source_emits_no_owner_language_prose(self):
        """§0: markers and messages produced by these modules are structural
        English. The same reasoning that forbids parsing localized headings
        forbids emitting them."""
        src = inspect.getsource(ctx)
        offending = sorted({ch for ch in src if 0x0400 <= ord(ch) <= 0x04FF})
        self.assertEqual(offending, [], f"Cyrillic in engine source: {offending}")


if __name__ == "__main__":
    unittest.main()
