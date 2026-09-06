"""Migration 032 — every file in a friend's clone says Minder Memory.

The migration runs the rename engine over the whole clone. These tests pin
what a friend must be able to rely on: their dashboard keeps its edits under
the new name, their notes and state say the current name, `_sources/` is
untouched, a base without `_system/` is refused (heal → retried), and a second
run is a no-op.
"""
# minder-memory-rebrand: keep-legacy-tokens — this module's inputs are the OLD spelling on purpose.

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]
_MIGRATIONS = _REPO_ROOT / "scripts" / "migrations"
_LIB = _REPO_ROOT / "scripts" / "lib"
MIGRATION = "032-minder-memory-owner-surfaces.sh"
HELPER = "_032_minder_memory_rebrand.py"
_OWNER_EDIT = "my custom dashboard line"


def _run(mig: Path, *args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(mig), *args], capture_output=True, text=True, encoding="utf-8",
                          env=env or dict(os.environ), cwd=str(cwd) if cwd else None)


def _tree_md5(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        parts = p.relative_to(root).parts
        if ".git" in parts or "__pycache__" in parts:
            continue
        if p.is_file() and not p.is_symlink():
            out["/".join(parts)] = hashlib.md5(p.read_bytes()).hexdigest()
    return out


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return p


class Migration032Tests(unittest.TestCase):
    NAME = "032-minder-memory-owner-surfaces.sh"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "scripts" / "migrations").mkdir(parents=True)
        shutil.copytree(_LIB, self.root / "scripts" / "lib")
        shutil.copy(_MIGRATIONS / HELPER, self.root / "scripts" / "migrations" / HELPER)
        shutil.copy(_MIGRATIONS / MIGRATION, self.root / "scripts" / "migrations" / MIGRATION)
        self.mig = self.root / "scripts" / "migrations" / MIGRATION

    def tearDown(self):
        self._tmp.cleanup()

    def _clone(self) -> None:
        (self.root / "zettelkasten" / "_system").mkdir(parents=True, exist_ok=True)
        _write(self.root, "zettelkasten/minder-ztn.md", f"# Minder ZTN\n\nRun /ztn:process daily.\n\n{_OWNER_EDIT}\n")
        _write(self.root, "zettelkasten/_system/SOUL.md", "I use Minder ZTN. Nightly I run /ztn:process.\n")
        _write(self.root, "zettelkasten/.obsidian/appearance.json", '{"enabledCssSnippets":["ztn-hide-engine-paths","ztn-note-types"]}\n')
        _write(self.root, "zettelkasten/.obsidian/snippets/ztn-note-types.css", "/* ZTN */\n")
        _write(self.root, "zettelkasten/_records/observations/2026-05-19-demo.md", "Talked about ZTN with the team.\n")
        _write(self.root, "zettelkasten/_sources/inbox/raw.md", "raw ZTN transcript\n")
        _write(self.root, "zettelkasten/_system/state/log_process.md", "ran /ztn:process\n")
        _write(self.root, "zettelkasten/_system/state/agent-lens-runs.jsonl", '{"skill":"ztn:agent-lens"}\n')
        # A credential key is the OWNER's name for something outside the repo.
        _write(self.root, "zettelkasten/_system/state/secrets.enc.json",
               '{"ZTN_TELEGRAM_TOKEN":"<encrypted>","ztn_calendar":"<encrypted>"}\n')

    def test_declared_kind_is_heal(self):
        head = self.mig.read_text(encoding="utf-8").splitlines()[:5]
        self.assertTrue(any("migration-kind: heal" in line for line in head))

    def test_refuses_a_base_without_system(self):
        self._clone()
        shutil.rmtree(self.root / "zettelkasten" / "_system")
        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 1)
        self.assertIn("no _system/", res.stderr)

    def test_renames_the_clone_and_keeps_the_owner_edit(self):
        self._clone()
        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        dash = self.root / "zettelkasten/minder-memory.md"
        self.assertTrue(dash.exists())
        self.assertIn(_OWNER_EDIT, dash.read_text(encoding="utf-8"))
        self.assertIn("/minder:mem:process", dash.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "zettelkasten/minder-ztn.md").exists())
        self.assertEqual((self.root / "zettelkasten/_system/SOUL.md").read_text(encoding="utf-8"),
                         "I use Minder Memory. Nightly I run /minder:mem:process.\n")
        self.assertEqual((self.root / "zettelkasten/.obsidian/appearance.json").read_text(encoding="utf-8"),
                         '{"enabledCssSnippets":["minder-memory-hide-engine-paths","minder-memory-note-types"]}\n')
        self.assertTrue((self.root / "zettelkasten/.obsidian/snippets/minder-memory-note-types.css").exists())
        self.assertEqual((self.root / "zettelkasten/_records/observations/2026-05-19-demo.md").read_text(encoding="utf-8"),
                         "Talked about Minder Memory with the team.\n")
        self.assertEqual((self.root / "zettelkasten/_system/state/log_process.md").read_text(encoding="utf-8"),
                         "ran /minder:mem:process\n")
        self.assertEqual((self.root / "zettelkasten/_system/state/agent-lens-runs.jsonl").read_text(encoding="utf-8"),
                         '{"skill":"minder:mem:agent-lens"}\n')
        self.assertEqual((self.root / "zettelkasten/_sources/inbox/raw.md").read_text(encoding="utf-8"),
                         "raw ZTN transcript\n")

    def test_unsaved_owner_files_are_rewritten_and_the_count_is_reported(self):
        """The rename applies to the clone whole — including work in flight.

        That is the contract, and it is fine: git holds the previous text. What
        was missing is the SAYING of it. An owner who left a note open finds it
        renamed under them and no line anywhere telling them where the old text
        went, which reads as data loss.
        """
        self._clone()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "seed")):
            subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, env=env)
        # One tracked note edited but not committed, one never saved at all.
        _write(self.root, "zettelkasten/_system/SOUL.md",
               "I use Minder ZTN and I am mid-edit.\n")
        _write(self.root, "zettelkasten/_records/observations/2026-06-01-open.md",
               "An unsaved ZTN note.\n")

        res = _run(self.mig, env=env, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.root / "zettelkasten/_system/SOUL.md").read_text(encoding="utf-8"),
                         "I use Minder Memory and I am mid-edit.\n")
        # Named, not counted: a number tells the owner something happened to
        # work of theirs and leaves them to find out what.
        self.assertIn("1 file with uncommitted changes was rewritten in place "
                      "(its previous text is in git under the old name): "
                      "zettelkasten/_system/SOUL.md", res.stdout)
        self.assertIn("1 file git had never seen was also rewritten "
                      "(nothing holds its previous text): "
                      "zettelkasten/_records/observations/2026-06-01-open.md", res.stdout)

    def test_the_credential_store_is_never_rewritten(self):
        """A credential key names something OUTSIDE the repository.

        The engine renames what it owns; a key is the owner's name for a
        service, and renaming one breaks its role's lookup at the next tick
        with an error that names nothing. Byte-identical is the only
        acceptable outcome.
        """
        self._clone()
        store = self.root / "zettelkasten/_system/state/secrets.enc.json"
        before = store.read_bytes()
        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(store.read_bytes(), before)

    def test_a_clone_with_nothing_unsaved_says_nothing_about_unsaved_files(self):
        """The counts exist to warn. A warning that always fires is noise.

        The installer runs before this migration in the same update and seeds
        the vault, so its files arrive untracked — counting them told every
        owner their work had been rewritten when nothing of theirs had.
        """
        self._clone()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "seed")):
            subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, env=env)
        # Exactly what the seeder leaves behind during the same update.
        _write(self.root, "zettelkasten/.obsidian/snippets/ztn-extra.css", "/* ZTN */\n")
        _write(self.root, "zettelkasten/5_meta/help/guide.md", "About ZTN.\n")

        res = _run(self.mig, env=env, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("renamed in place", res.stdout)
        self.assertNotIn("git had never seen", res.stdout)

    def test_engine_seeded_files_are_excluded_from_both_counts(self):
        """The installer runs before this migration, in the same update.

        Whatever it seeds arrives tracked-and-modified or brand new, and both
        shapes look exactly like the owner having left work unsaved. They are
        not the owner's work at all — they are the engine's own doing, and
        reporting them tells the owner something untrue about their notes.
        """
        self._clone()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "seed")):
            subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, env=env)
        # tracked, rewritten by the seeder during this same update
        _write(self.root, "zettelkasten/.obsidian/appearance.json",
               '{"enabledCssSnippets":["ztn-hide-engine-paths"],"theme":"obsidian"}\n')
        # and the dashboard, written fresh and therefore untracked
        _write(self.root, "zettelkasten/minder-ztn.md", "# Minder ZTN\n\nRun /ztn:process.\n")

        res = _run(self.mig, env=env, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("renamed in place", res.stdout)
        self.assertNotIn("git had never seen", res.stdout)

    def test_a_roles_own_credential_name_survives_on_both_sides(self):
        """The declaration and the store must still agree afterwards.

        A role names its credentials; the store holds them under those names.
        The store is never rewritten, so rewriting the declaration renamed one
        half of a pair — and the role's next preflight failed naming a variable
        the owner had never written anywhere.
        """
        self._clone()
        _write(self.root, "zettelkasten/_system/roles/telegram-digest/role.md",
               "---\nid: telegram-digest\nsecrets:\n  - ZTN_TELEGRAM_TOKEN\n---\n\n"
               "Every morning, read ZTN and post a digest. Run /ztn:process first.\n")
        store = self.root / "zettelkasten/_system/state/secrets.enc.json"
        store_before = store.read_bytes()

        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)

        role = (self.root / "zettelkasten/_system/roles/telegram-digest/role.md").read_text(
            encoding="utf-8")
        self.assertIn("- ZTN_TELEGRAM_TOKEN", role, "the owner's credential name is theirs")
        self.assertIn("/minder:mem:process", role, "the engine's own names still move")
        self.assertIn("read Minder Memory and post", role)
        self.assertEqual(store.read_bytes(), store_before)

    def test_the_declared_secret_still_resolves_after_the_rename(self):
        """The pair, checked by the engine's own preflight rather than by eye."""
        self._clone()
        base = self.root / "zettelkasten"
        _write(self.root, "zettelkasten/_system/roles/telegram-digest/role.md",
               "---\nid: telegram-digest\nname: Telegram digest\nstatus: active\n"
               "cadence: daily 07:00\nsecrets:\n  - ZTN_TELEGRAM_TOKEN\n---\n\nDo the thing.\n")
        # `{name: ciphertext}` — the store's real shape; the value is never
        # decrypted here, only its NAME is resolved against the declaration.
        _write(self.root, "zettelkasten/_system/state/secrets.enc.json",
               '{"ZTN_TELEGRAM_TOKEN":"' + "x" * 64 + '"}\n')
        runner = _REPO_ROOT / "zettelkasten" / "_system" / "scripts" / "roles_run.py"
        if not runner.is_file():
            self.skipTest("no roles runner in this engine")

        self.assertEqual(_run(self.mig, cwd=self.root).returncode, 0)

        out = subprocess.run(
            ["python3", str(runner), "validate", "--base", str(base), "--repo", str(self.root)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(self.root))
        report = json.loads(out.stdout or "{}")
        # A finding without a `secret` key is about the checking environment
        # (no decryption key here), not about the pair under test — but a
        # corrupt or unreadable store would hide the real check, so those are
        # asserted away too rather than filtered silently.
        findings = report.get("findings", [])
        self.assertNotIn("corrupt", out.stdout)
        unresolved = [f for f in findings
                      if f.get("secret") and "credential store" in f.get("issue", "")]
        self.assertEqual(unresolved, [], out.stdout)
        self.assertTrue(any(n.get("role") == "telegram-digest" for n in report.get("notes", []))
                        or not findings,
                        f"the role was never discovered, so nothing was checked: {out.stdout}")

    def test_second_run_is_a_no_op(self):
        self._clone()
        self.assertEqual(_run(self.mig, cwd=self.root).returncode, 0)
        before = _tree_md5(self.root)
        res = _run(self.mig, cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(_tree_md5(self.root), before)


if __name__ == "__main__":
    unittest.main()
