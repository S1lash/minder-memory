"""Tests for roles_secrets — the encrypted store (CORE-SPEC §6).

The store is COMMITTED and the key is not: a plaintext file has to be
gitignored, and a gitignored file does not exist in a cloud clone, so an
outward-reaching role could never run on a Routine. The ciphertext travelling
in the owner's private repo is the named trade that buys the only
configuration where a scheduled outward role works at all.

Three properties carry that trade, and each has its own class below:

  - the DECRYPTED file is never inside the repository (`MaterialiseTests`),
    asserted through `git status` rather than through the path string,
    because being invisible to git is what stops it being staged;
  - a wrong key fails LOUDLY and COMPLETELY (`WrongKeyTests`) — never an
    empty store, never a partial one, never a silent «no secrets», which
    would turn a key mistake into a role that reports success while doing
    nothing;
  - each value is encrypted INDEPENDENTLY (`IndependenceTests`), so adding a
    credential leaves the others' ciphertext byte-identical and the diff is
    one line.

Lineage: this replaces a module the engine had and lost. The `secret://<ref>`
indirection is gone — a role now sources a file and uses `$NAME` — so the ref
parsing and the lowercase-slug name shape do not carry over. The key handling,
per-value independence, fail-closed decryption and blob I/O do, and the tests
for them are adapted rather than rewritten.

API NAMES: written before the module landed. `MINDER_MEMORY_ROLES_KEY` and the store
path are quoted verbatim from §6 and are not guesses; the function names
follow the recovered module wherever it still applies, and use §6.4's own
verbs (materialise / destroy) where it does not. Flagged for reconciliation.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from tests._roles_fixture import (  # type: ignore
    KEY_ENV,
    encrypt_value,
    generate_key,
    git,
    have_cryptography,
    init_repo,
    key_env,
    make_base,
    porcelain_z,
    read_store,
    repo_base,
    store_path,
    write_encrypted_store,
    write_text,
)
import roles_secrets as rs  # type: ignore

HAVE_CRYPTO = have_cryptography()
NOTION = "notion-token-value-9876"
SLACK = "slack-token-value-5432"

crypto_only = unittest.skipUnless(HAVE_CRYPTO, "cryptography is not installed")


def _target(tmp) -> Path:
    """Where the decrypted file goes for a module-level test.

    The MODULE writes wherever it is told; choosing a path outside the
    repository is the CALLER's job (`roles_config.secrets_file`), and
    `test_roles_run.py` is where that choice is pinned. Here the target is
    deliberately outside the fixture's repo so a module test never depends on
    the caller getting it right.
    """
    return Path(tmp) / "outside-the-repo" / "secrets.env"


def _holds(path: Path, needle: str) -> bool:
    """True when `path`'s bytes contain `needle` as UTF-8 text."""
    try:
        return needle in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


# ==========================================================================
# 1. the decrypted file is never inside the repository
# ==========================================================================

@crypto_only
class MaterialiseTests(unittest.TestCase):
    """§6.4 — the tick decrypts the whole store once, into a file in the OS
    temp directory, OUTSIDE the repository.

    Outside is load-bearing three times over: `git status` never sees it, so
    the guard cannot mistake it for a role's write; `stage.sh` can never stage
    it; and it cannot survive into a commit by any path.

    Asserted through git, not through the path string. «Starts with tempdir»
    is a proxy for the property; «git cannot see it» IS the property, and a
    symlink, a bind mount or a repo that happens to live under the temp
    directory would satisfy the proxy while failing the property.
    """

    def _repo_with_store(self, tmp):
        """A repo whose encrypted store is COMMITTED, as §6.2 requires.

        Committing it matters for the assertion: with the store left
        untracked, `git status` is non-empty for a reason that has nothing to
        do with the decrypted file, and the test would fail without saying
        anything about the property.
        """
        repo = init_repo(Path(tmp))
        base = repo_base(repo)
        key = generate_key()
        write_encrypted_store(base, key, {"NOTION_TOKEN": NOTION})
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "commit the encrypted store")
        return repo, base, key

    def test_the_decrypted_file_is_invisible_to_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._repo_with_store(tmp)
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                self.assertTrue(path.is_file())
                self.assertIn(NOTION, path.read_text(encoding="utf-8"))
                self.assertEqual(porcelain_z(repo), "",
                                 "git can see the decrypted store")
            finally:
                rs.destroy(path)

    def test_the_decrypted_file_cannot_be_staged_or_committed(self):
        """The load-bearing invariant of §6, asserted the whole way to a
        commit rather than at the first step.

        `git status` not seeing it is what stops it being staged; this goes
        further and proves the outcome — `git add -A` picks up nothing, and a
        commit attempt has nothing to record. That is the property the entire
        «encrypted and committed» trade rests on: the ciphertext travels, the
        plaintext never does."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._repo_with_store(tmp)
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                git(repo, "add", "-A")
                staged = git(repo, "diff", "--cached", "--name-only").stdout.strip()
                self.assertEqual(staged, "", "the decrypted store was staged")
                tracked = git(repo, "ls-files").stdout
                self.assertNotIn("secrets.env", tracked)
                self.assertNotIn(str(path.name), tracked)
            finally:
                rs.destroy(path)

    def test_no_plaintext_value_exists_anywhere_under_the_repository(self):
        """The same invariant from the other direction: not «that one file is
        outside», but «no file inside holds the value». A cache, a log line or
        a report that quoted a credential would land somewhere the path check
        never looks."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._repo_with_store(tmp)
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                offenders = [
                    p for p in repo.rglob("*")
                    if p.is_file() and ".git" not in p.parts and _holds(p, NOTION)
                ]
                self.assertEqual(offenders, [],
                                 "a plaintext credential is inside the repository")
            finally:
                rs.destroy(path)

    def test_the_decrypted_file_is_not_under_the_repository(self):
        """The proxy, kept as a second signal: even a git that ignored it must
        not put plaintext inside the tree."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, key = self._repo_with_store(tmp)
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                self.assertNotIn(str(repo.resolve()), str(path.resolve()))
            finally:
                rs.destroy(path)

    def test_the_decrypted_file_carries_every_stored_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            base = repo_base(repo)
            key = generate_key()
            write_encrypted_store(base, key,
                                  {"NOTION_TOKEN": NOTION, "SLACK_TOKEN": SLACK})
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                text = path.read_text(encoding="utf-8")
                self.assertIn(f"NOTION_TOKEN={NOTION}", text)
                self.assertIn(f"SLACK_TOKEN={SLACK}", text)
            finally:
                rs.destroy(path)

    def test_the_decrypted_file_is_lf_and_utf8(self):
        """SIBLING — §6.6 keeps the format of the plaintext store it replaces,
        and the role sources it with `.` in a shell."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp))
            base = repo_base(repo)
            key = generate_key()
            write_encrypted_store(base, key, {"NOTION_TOKEN": "значение-с-кириллицей"})
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                raw = path.read_bytes()
                self.assertNotIn(b"\r\n", raw)
                self.assertIn("значение-с-кириллицей", raw.decode("utf-8"))
            finally:
                rs.destroy(path)


# ==========================================================================
# 2. a wrong key fails loudly and completely
# ==========================================================================

@crypto_only
class WrongKeyTests(unittest.TestCase):
    """Fernet is authenticated, so a wrong key cannot silently produce
    garbage — it raises. What must be pinned is that the engine turns that
    into a loud, complete failure rather than an empty or partial store.

    A silent «no secrets» is the worst outcome available: the role runs, gets
    an empty variable, gets a 401, and reports success. That is the failure
    shape this whole subsystem exists to prevent.
    """

    def _store(self, base, key, pairs=None):
        return write_encrypted_store(base, key, pairs or {"NOTION_TOKEN": NOTION})

    def test_a_wrong_key_raises_rather_than_returning_an_empty_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            self._store(base, generate_key())
            with key_env(generate_key()):
                with self.assertRaises(rs.SecretError):
                    rs.materialise(store_path(base), _target(tmp))

    def test_a_wrong_key_leaves_no_partial_file_behind(self):
        """«Completely» — a store of several values must not materialise the
        ones that happen to decrypt first."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            good = generate_key()
            blob = {"A_TOKEN": encrypt_value(good, "aaa-value-1234"),
                    "B_TOKEN": encrypt_value(generate_key(), "bbb-value-5678")}
            write_text(store_path(base),
                       json.dumps(blob, indent=2, sort_keys=True) + "\n")
            with key_env(good):
                with self.assertRaises(rs.SecretError):
                    rs.materialise(store_path(base), _target(tmp))
            leaked = [p for p in Path(tempfile.gettempdir()).glob("*")
                      if p.is_file() and _contains(p, "aaa-value-1234")]
            self.assertEqual(leaked, [], "a partial decryption was left on disk")

    def test_the_error_names_the_env_var(self):
        """The owner has to know WHICH thing to fix, and the key is the one
        piece of configuration that lives outside the repo entirely."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            self._store(base, generate_key())
            with key_env(generate_key()):
                with self.assertRaises(rs.SecretError) as ctx:
                    rs.materialise(store_path(base), _target(tmp))
            self.assertIn(KEY_ENV, str(ctx.exception))

    def test_the_error_carries_neither_plaintext_nor_ciphertext(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            self._store(base, key)
            ciphertext = read_store(base)["NOTION_TOKEN"]
            with key_env(generate_key()):
                with self.assertRaises(rs.SecretError) as ctx:
                    rs.materialise(store_path(base), _target(tmp))
            message = str(ctx.exception)
            self.assertNotIn(NOTION, message)
            self.assertNotIn(ciphertext, message)

    def test_a_malformed_key_raises_rather_than_crashing(self):
        """SIBLING of the wrong-key case — a key that is not Fernet-shaped at
        all is an owner typo, and must be as actionable as a wrong one."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            self._store(base, generate_key())
            for bad in ("not-a-key", "", "   ", "a" * 43):
                with self.subTest(key=bad):
                    with key_env(bad):
                        with self.assertRaises(rs.SecretError) as ctx:
                            rs.materialise(store_path(base), _target(tmp))
                    self.assertIn(KEY_ENV, str(ctx.exception))

    def test_an_absent_key_raises_naming_the_env_var(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            self._store(base, generate_key())
            with key_env(None):
                with self.assertRaises(rs.SecretError) as ctx:
                    rs.materialise(store_path(base), _target(tmp))
            self.assertIn(KEY_ENV, str(ctx.exception))

    def test_a_tampered_ciphertext_raises(self):
        """Fernet is authenticated: an edited store is a wrong key by another
        name, and must not decrypt to anything."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            self._store(base, key)
            blob = read_store(base)
            token = blob["NOTION_TOKEN"]
            blob["NOTION_TOKEN"] = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
            write_text(store_path(base), json.dumps(blob, indent=2) + "\n")
            with key_env(key):
                with self.assertRaises(rs.SecretError):
                    rs.materialise(store_path(base), _target(tmp))

    def test_a_corrupt_store_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_text(store_path(base), "not json {{{")
            with key_env(generate_key()):
                with self.assertRaises(rs.SecretError):
                    rs.materialise(store_path(base), _target(tmp))

    def test_the_right_key_still_works(self):
        """SIBLING — the failure paths must not have made success unreachable."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            self._store(base, key)
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                self.assertIn(NOTION, path.read_text(encoding="utf-8"))
            finally:
                rs.destroy(path)


# ==========================================================================
# 3. per-value independence
# ==========================================================================

@crypto_only
class IndependenceTests(unittest.TestCase):
    """§6.2 — each value encrypted independently, so adding one credential
    never re-encrypts the rest.

    Asserted on the untouched value's CIPHERTEXT being byte-identical, not on
    both values decrypting. A whole-store re-encrypt decrypts perfectly well
    and still rewrites every line of the committed file — which is what the
    property is about: a one-line diff the owner can read, and no need for the
    other credentials' plaintext in order to add one.
    """

    def test_storing_a_second_secret_leaves_the_first_ciphertext_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            with key_env(key):
                rs.store_secret(store_path(base), "NOTION_TOKEN", NOTION)
                first = read_store(base)["NOTION_TOKEN"]
                rs.store_secret(store_path(base), "SLACK_TOKEN", SLACK)
                after = read_store(base)
            self.assertEqual(after["NOTION_TOKEN"], first,
                             "adding a credential re-encrypted an untouched one")
            self.assertEqual(set(after), {"NOTION_TOKEN", "SLACK_TOKEN"})

    def test_overwriting_one_secret_leaves_the_others_ciphertext_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            with key_env(key):
                rs.store_secret(store_path(base), "NOTION_TOKEN", NOTION)
                rs.store_secret(store_path(base), "SLACK_TOKEN", SLACK)
                untouched = read_store(base)["SLACK_TOKEN"]
                rs.store_secret(store_path(base), "NOTION_TOKEN", "rotated-value-2222")
                after = read_store(base)
            self.assertEqual(after["SLACK_TOKEN"], untouched)

    def test_two_values_have_different_ciphertexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                rs.store_secret(store_path(base), "A_TOKEN", "same-value-here-1234")
                rs.store_secret(store_path(base), "B_TOKEN", "same-value-here-1234")
                blob = read_store(base)
            self.assertNotEqual(blob["A_TOKEN"], blob["B_TOKEN"],
                                "identical plaintexts must not share a token")

    def test_the_store_holds_no_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                rs.store_secret(store_path(base), "NOTION_TOKEN", "PLAINTEXT-MARKER-9999")
            raw = store_path(base).read_text(encoding="utf-8")
            self.assertNotIn("PLAINTEXT-MARKER-9999", raw)

    def test_the_store_is_a_flat_name_to_ciphertext_map(self):
        """§6.2's shape, which is what makes a per-credential diff readable."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                rs.store_secret(store_path(base), "NOTION_TOKEN", NOTION)
            blob = read_store(base)
            self.assertIsInstance(blob, dict)
            self.assertIsInstance(blob["NOTION_TOKEN"], str)

    def test_the_store_is_written_sorted_for_a_stable_diff(self):
        """SIBLING — key order must not depend on insertion order, or every
        addition churns the file even when the ciphertexts are stable."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                rs.store_secret(store_path(base), "Z_TOKEN", "zzz-value-1234")
                rs.store_secret(store_path(base), "A_TOKEN", "aaa-value-1234")
            text = store_path(base).read_text(encoding="utf-8")
            self.assertLess(text.index("A_TOKEN"), text.index("Z_TOKEN"))

    def test_a_round_trip_returns_the_stored_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                rs.store_secret(store_path(base), "NOTION_TOKEN", NOTION)
                path = rs.materialise(store_path(base), _target(tmp))
                try:
                    self.assertIn(f"NOTION_TOKEN={NOTION}",
                                  path.read_text(encoding="utf-8"))
                finally:
                    rs.destroy(path)


# ==========================================================================
# names without the key — what `validate` rests on
# ==========================================================================

@crypto_only
class NameResolutionTests(unittest.TestCase):
    """§6.5 — `validate` resolves NAMES and never decrypts a value, so a
    preflight runs with no key present and still says «this credential is not
    in the store».

    That is what keeps the concierge's gate usable on a laptop that has never
    held the key.
    """

    def test_names_resolve_without_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_encrypted_store(base, generate_key(),
                                  {"NOTION_TOKEN": NOTION, "SLACK_TOKEN": SLACK})
            with key_env(None):
                self.assertEqual(sorted(rs.names(store_path(base))),
                                 ["NOTION_TOKEN", "SLACK_TOKEN"])

    def test_names_resolve_with_a_wrong_key(self):
        """SIBLING — names come from the JSON structure, so even a key that
        cannot decrypt anything must not stop the preflight from listing."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_encrypted_store(base, generate_key(), {"NOTION_TOKEN": NOTION})
            with key_env(generate_key()):
                self.assertEqual(rs.names(store_path(base)), ["NOTION_TOKEN"])

    def test_an_absent_store_yields_no_names_rather_than_an_error(self):
        """SIBLING — a base with no credentials is the common case, and
        listing must not be where it fails."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(None):
                self.assertEqual(list(rs.names(store_path(base))), [])

    def test_listing_never_writes_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_encrypted_store(base, generate_key(), {"NOTION_TOKEN": NOTION})
            before = store_path(base).read_bytes()
            with key_env(None):
                rs.names(store_path(base))
            self.assertEqual(store_path(base).read_bytes(), before)


# ==========================================================================
# destroy — it runs from a `finally`
# ==========================================================================

@crypto_only
class DestroyTests(unittest.TestCase):
    """§6.4 — the tick removes the decrypted file in the same `finally` that
    releases the lock, so `destroy` is called on paths that may never have
    existed and may already be gone. It must be safe in both cases, because a
    `finally` that raises masks the original exception.
    """

    def _materialised(self, tmp):
        base = make_base(Path(tmp))
        key = generate_key()
        write_encrypted_store(base, key, {"NOTION_TOKEN": NOTION})
        with key_env(key):
            return base, rs.materialise(store_path(base), _target(tmp))

    def test_destroy_removes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, path = self._materialised(tmp)
            rs.destroy(path)
            self.assertFalse(path.exists())

    def test_destroy_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, path = self._materialised(tmp)
            rs.destroy(path)
            rs.destroy(path)
            self.assertFalse(path.exists())

    def test_destroy_reports_whether_there_was_anything_to_remove(self):
        """Nothing was materialised — a base with no secrets, or a tick that
        died before it got that far. The `finally` still runs, and the return
        value distinguishes «removed it» from «there was nothing», so a caller
        can log the difference without probing the filesystem itself."""
        with tempfile.TemporaryDirectory() as tmp:
            _, path = self._materialised(tmp)
            self.assertTrue(rs.destroy(path))
            self.assertFalse(rs.destroy(path))

    def test_destroy_tolerates_a_path_that_never_existed(self):
        with tempfile.TemporaryDirectory() as tmp:
            rs.destroy(Path(tmp) / "never-created.env")

    def test_a_crash_after_materialise_still_leaves_nothing_decrypted(self):
        """The shape the tick actually has: materialise, work, explode, and
        the `finally` cleans up regardless."""
        with tempfile.TemporaryDirectory() as tmp:
            base, path = self._materialised(tmp)
            self.assertTrue(path.is_file())
            try:
                try:
                    raise RuntimeError("the role agent crashed")
                finally:
                    rs.destroy(path)
            except RuntimeError:
                pass
            self.assertFalse(path.exists(), "a crash left the plaintext on disk")

    def test_destroy_does_not_mask_the_original_exception(self):
        """SIBLING — if `destroy` raised on an already-gone path, the tick
        would report a cleanup error instead of the role's real failure."""
        with tempfile.TemporaryDirectory() as tmp:
            _, path = self._materialised(tmp)
            rs.destroy(path)
            with self.assertRaises(RuntimeError):
                try:
                    raise RuntimeError("the real failure")
                finally:
                    rs.destroy(path)

    def test_destroy_leaves_the_encrypted_store_alone(self):
        """SIBLING — cleanup removes the DECRYPTED copy, never the committed
        store. Deleting that would lose every credential the owner has."""
        with tempfile.TemporaryDirectory() as tmp:
            base, path = self._materialised(tmp)
            rs.destroy(path)
            self.assertTrue(store_path(base).is_file())
            self.assertIn("NOTION_TOKEN", read_store(base))


# ==========================================================================
# the format contract with roles_config.parse_secrets_file
# ==========================================================================

@crypto_only
class DecryptedFormatTests(unittest.TestCase):
    """§6.6 — the decrypted file is byte-compatible with the plaintext store
    it replaces, so nothing downstream learns that the store is encrypted.

    Asserted by handing the materialised file to the REAL parser rather than
    by re-describing the format here: a second description would be a second
    source of truth for the same fact.
    """

    def _parse(self, path):
        import roles_config
        return roles_config.parse_secrets_file(path)

    def test_the_materialised_file_parses_with_the_existing_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            write_encrypted_store(base, key,
                                  {"NOTION_TOKEN": NOTION, "SLACK_TOKEN": SLACK})
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                self.assertEqual(self._parse(path),
                                 {"NOTION_TOKEN": NOTION, "SLACK_TOKEN": SLACK})
            finally:
                rs.destroy(path)

    def test_a_value_with_spaces_and_punctuation_round_trips(self):
        """SIBLING — §6.6 keeps «the value is the raw remainder of the line»,
        so a credential with `=` or spaces in it must survive."""
        tricky = "Bearer abc=def ghi/jkl+mno=="
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            write_encrypted_store(base, key, {"NOTION_TOKEN": tricky})
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                self.assertEqual(self._parse(path), {"NOTION_TOKEN": tricky})
            finally:
                rs.destroy(path)

    def test_a_cyrillic_value_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            write_encrypted_store(base, key, {"NOTION_TOKEN": "секрет-значение"})
            with key_env(key):
                path = rs.materialise(store_path(base), _target(tmp))
            try:
                self.assertEqual(self._parse(path), {"NOTION_TOKEN": "секрет-значение"})
            finally:
                rs.destroy(path)

    def test_a_value_containing_a_newline_is_refused_at_store_time(self):
        """§6.6: no newline inside a value.

        The engine refuses it at MATERIALISE time (pinned by the sibling
        below), which is correct as a backstop but late as the only gate: by
        then the credential is committed, and the whole store fails to
        materialise at 07:00 rather than the one bad value being rejected
        while the owner is still there to retype it. Refusing at store time is
        what makes the error actionable."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                with self.assertRaises(rs.SecretError):
                    rs.store_secret(store_path(base), "NOTION_TOKEN", "line one\nline two")

    def test_a_value_containing_a_newline_is_refused_at_materialise_time(self):
        """SIBLING — the backstop that exists today, and must keep existing: a
        store hand-edited outside `store_secret` cannot produce a decrypted
        file whose second line is a malformed-line error."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            key = generate_key()
            write_encrypted_store(base, key, {"NOTION_TOKEN": "line one\nline two"})
            with key_env(key):
                with self.assertRaises(rs.SecretError) as ctx:
                    rs.materialise(store_path(base), _target(tmp))
            self.assertIn("newline", str(ctx.exception).lower())

    def test_the_parser_still_accepts_comments_and_blank_lines(self):
        """§6.6 — the parser keeps them, because it is the same parser and
        narrowing it would buy nothing.

        This lives at the PARSER now, not at `validate`: `validate` reads the
        store and never sees this format. The acceptance still matters —
        `render_env` is free to emit a header comment, and an owner may read
        the decrypted file while debugging — so the rule is pinned where it is
        actually exercised."""
        import roles_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decrypted.env"
            write_text(path,
                       "# notion, rotated 2026-07\n\n  # indented comment\n"
                       f"NOTION_TOKEN={NOTION}\n\n")
            self.assertEqual(roles_config.parse_secrets_file(path),
                             {"NOTION_TOKEN": NOTION})

    def test_the_rendered_file_round_trips_through_its_own_parser(self):
        """SIBLING — whatever `render_env` emits, the parser reads back. The
        two are one contract and must not drift apart."""
        import roles_config
        with tempfile.TemporaryDirectory() as tmp:
            values = {"NOTION_TOKEN": NOTION, "SLACK_TOKEN": SLACK}
            path = Path(tmp) / "decrypted.env"
            write_text(path, rs.render_env(values))
            self.assertEqual(roles_config.parse_secrets_file(path), values)

    def test_a_malformed_decrypted_line_still_names_its_line_number(self):
        """The parser's own contract, exercised through this path: a store
        whose value somehow carried a newline must produce the SAME
        line-numbered error the plaintext store did, not a new failure mode."""
        import roles_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decrypted.env"
            write_text(path, "NOTION_TOKEN=ok\nthis line has no equals sign\n")
            with self.assertRaises(roles_config.RoleConfigError) as ctx:
                roles_config.parse_secrets_file(path)
            self.assertIn("2", str(ctx.exception))

    def test_a_name_outside_the_env_var_shape_is_refused(self):
        """§6.6 keeps `KEY` matching `[A-Z][A-Z0-9_]*`, which is also §1's
        `secrets:` shape — the two must not drift, or a role could declare a
        name the store can never hold."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                for bad in ("lower_case", "1LEADING", "_LEADING", "WITH-DASH", ""):
                    with self.subTest(name=bad):
                        with self.assertRaises(rs.SecretError):
                            rs.store_secret(store_path(base), bad, "value-long-enough-1234")

    def test_a_legal_name_with_digits_and_underscores_is_accepted(self):
        """SIBLING — `NOTION_TOKEN_2` is legal in §1 and must be legal here."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(generate_key()):
                rs.store_secret(store_path(base), "NOTION_TOKEN_2", NOTION)
                self.assertIn("NOTION_TOKEN_2", read_store(base))


# ==========================================================================
# cryptography is imported lazily
# ==========================================================================

class LazyImportTests(unittest.TestCase):
    """§6.2 — `cryptography` is imported LAZILY, so a base with no secrets
    neither needs the package nor fails without it. PyYAML stays the engine's
    only hard dependency.

    Simulated by blocking the import rather than by assuming: an
    `import cryptography` at module scope would satisfy every other test in
    this file and still break every friend who never stores a credential.
    """

    def _without_cryptography(self):
        blocked = {name: None for name in list(sys.modules)
                   if name == "cryptography" or name.startswith("cryptography.")}
        return unittest.mock.patch.dict(sys.modules, blocked)

    def test_the_module_imports_with_cryptography_absent(self):
        with self._without_cryptography():
            import importlib
            importlib.reload(rs)
        import importlib
        importlib.reload(rs)      # restore for the rest of the suite

    def test_listing_names_works_with_cryptography_absent(self):
        """Names come from JSON, so a preflight needs no crypto at all."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_text(store_path(base), json.dumps({"NOTION_TOKEN": "x"}) + "\n")
            with self._without_cryptography():
                self.assertEqual(rs.names(store_path(base)), ["NOTION_TOKEN"])

    def test_an_absent_store_needs_no_crypto(self):
        """The whole point of the lazy import: a base with no credentials runs
        every path with the package absent."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with self._without_cryptography():
                self.assertEqual(list(rs.names(store_path(base))), [])
                target = rs.materialise(store_path(base), _target(tmp))
                self.assertTrue(rs.destroy(target))

    def test_materialising_without_cryptography_raises_an_actionable_error(self):
        """When a credential IS present the package is genuinely required, and
        the failure must say so — not surface a bare ImportError."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_text(store_path(base), json.dumps({"NOTION_TOKEN": "x"}) + "\n")
            with self._without_cryptography():
                with key_env("a" * 44):
                    with self.assertRaises(rs.SecretError) as ctx:
                        rs.materialise(store_path(base), _target(tmp))
            self.assertIn("cryptography", str(ctx.exception).lower())


# ==========================================================================
# a base with no secrets pays nothing
# ==========================================================================

class NoSecretsBaseTests(unittest.TestCase):
    """The accepts-sibling for the whole feature. Most owners will never store
    a credential, and none of this may become a gate on them: no store file,
    no key, no `cryptography`, and everything behaves exactly as before.
    """

    def test_an_absent_store_materialises_an_empty_file_not_an_error(self):
        """A role still sources `$SECRETS_FILE` unconditionally, and sourcing
        a file that does not exist is a shell error — so the no-secrets case
        produces an EMPTY file rather than nothing at all."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(None):
                path = rs.materialise(store_path(base), _target(tmp))
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_text(encoding="utf-8").strip(), "")

    def test_an_emptied_store_behaves_like_an_absent_one(self):
        """SIBLING — a store emptied of its last credential is the same
        situation as never having had one."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            write_text(store_path(base), "{}\n")
            with key_env(None):
                path = rs.materialise(store_path(base), _target(tmp))
            self.assertEqual(path.read_text(encoding="utf-8").strip(), "")

    def test_no_key_is_needed_when_there_is_no_store(self):
        """The accepts-sibling in one line: names, materialise and destroy all
        work with `MINDER_MEMORY_ROLES_KEY` unset. Most owners will never hold a key."""
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            with key_env(None):
                self.assertEqual(list(rs.names(store_path(base))), [])
                target = rs.materialise(store_path(base), _target(tmp))
                self.assertTrue(rs.destroy(target))

    def test_an_absent_store_writes_nothing_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_base(Path(tmp))
            before = sorted(p.name for p in base.rglob("*") if p.is_file())
            with key_env(None):
                rs.materialise(store_path(base), _target(tmp))
            self.assertEqual(sorted(p.name for p in base.rglob("*") if p.is_file()),
                             before)


def _contains(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


if __name__ == "__main__":
    unittest.main()
