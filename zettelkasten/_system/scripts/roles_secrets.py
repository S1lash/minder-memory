#!/usr/bin/env python3
"""The encrypted credential store, and the decrypted file a role sources.

A plaintext store has to be gitignored, and a gitignored file DOES NOT EXIST
in a cloud clone. Cloud Routines start from a fresh checkout, so a role that
reaches an authenticated service could never run there — while a local
scheduler only runs while the machine is on. That combination made the
most-wanted capability unreachable in the only environment an owner without
an always-on machine can use.

So the store is **encrypted and committed**, and the key arrives per run from
the scheduler's own environment. The trade is named rather than implied: the
ciphertext lives in the owner's private repository, so a repo leak hands an
attacker ciphertext and not the key. That is a deliberate step down from «the
secret never leaves the machine», and it buys the only configuration in which
a scheduled outward-reaching role works at all.

Four properties, all load-bearing:

1. **Each value is encrypted independently**, so adding one credential never
   re-encrypts the rest and a diff shows exactly one changed line.
2. **The key is one env var**, `MINDER_MEMORY_ROLES_KEY`, one per base — never in git,
   never in a prompt body, never in a file this engine writes.
3. **`cryptography` is imported lazily**, so a base with no secrets neither
   needs the package nor breaks without it. PyYAML stays the only hard
   dependency.
4. **Fail-closed.** Every failure raises `SecretError`; nothing here ever
   returns an empty or partial store. Fernet is authenticated, so a wrong key
   fails immediately rather than yielding garbage — and the message says
   which variable is wrong and what to do, never echoing ciphertext or
   plaintext.

Names are resolvable WITHOUT the key: `names()` reads the store's keys, so a
preflight runs on a machine that has no key and still reports a credential
that is missing from the store.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# The env var the key arrives in. One per base: per-role keys would mean the
# owner pasting N values into a routine, and the isolation they would buy is
# already absent — `secrets:` is a declaration, not a boundary, so any role
# with a shell can read the whole store either way.
KEY_ENV = "MINDER_MEMORY_ROLES_KEY"

# A credential name, the same shape as `secrets:` in role frontmatter and as
# `KEY` in the decrypted file. One shape, three surfaces.
NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")


class SecretError(Exception):
    """A credential could not be read, written or decrypted. Fail-closed.

    Raised — never a wrong or empty value returned quietly — when the key is
    absent, the store is missing or corrupt, a name is absent or malformed,
    `cryptography` is not installed, or decryption fails. Messages are
    actionable and never carry ciphertext or plaintext.
    """


# --------------------------------------------------------------------------
# the key
# --------------------------------------------------------------------------

def _key_from_env() -> str:
    """The key from `MINDER_MEMORY_ROLES_KEY`; empty when it is not set."""
    return os.environ.get(KEY_ENV, "").strip()


def key_present() -> bool:
    """True when `MINDER_MEMORY_ROLES_KEY` is set and non-empty."""
    return bool(_key_from_env())


def _require_key() -> str:
    key = _key_from_env()
    if not key:
        raise SecretError(
            f"{KEY_ENV} is not set: the credential store is encrypted and the "
            f"key arrives from the environment. Set {KEY_ENV} in the scheduler "
            f"routine's env config — never in the prompt body and never in git."
        )
    return key


def _fernet(key: str):
    """Build a Fernet from the key, lazy-importing `cryptography`."""
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise SecretError(
            "the 'cryptography' package is needed to read or write credentials "
            "but is not installed. A clone that updated in place will not have "
            "it yet — install every engine dependency at once with: "
            "pip install -r _system/scripts/requirements.txt"
        ) from exc
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SecretError(
            f"{KEY_ENV} is not a valid key (expected 44 characters of "
            f"urlsafe-base64). Generate one with `generate_key()` and set it in "
            f"the scheduler routine's env config."
        ) from exc


def generate_key() -> str:
    """A fresh key. Shown to the owner once; a lost key is not recoverable."""
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise SecretError(
            "the 'cryptography' package is needed to generate a key but is not "
            "installed — run: pip install 'cryptography>=41.0'"
        ) from exc
    return Fernet.generate_key().decode("utf-8")


# --------------------------------------------------------------------------
# the store — a flat {name: ciphertext} map, committed
# --------------------------------------------------------------------------

def _valid_name(name) -> bool:
    return isinstance(name, str) and NAME_RE.fullmatch(name) is not None


def _require_name(name) -> str:
    if not _valid_name(name):
        raise SecretError(
            f"invalid credential name {name!r}: expected {NAME_RE.pattern}"
        )
    return name


def load_store(path: Path) -> dict:
    """The `{name: ciphertext}` map. No key needed, nothing decrypted.

    A missing store is `{}` rather than an error: a base with no credentials
    is the ordinary case, and every caller distinguishes «no store» from «not
    in the store» by the name it was looking for.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise SecretError(f"cannot read the credential store at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SecretError(
            f"the credential store at {path} is corrupt (not valid JSON): {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise SecretError(
            f"the credential store at {path} is corrupt: expected an object of "
            f"{{name: ciphertext}}, got {type(data).__name__}"
        )
    for name, token in data.items():
        if not _valid_name(name) or not isinstance(token, str):
            raise SecretError(
                f"the credential store at {path} is corrupt: entry {name!r} is "
                f"not a name/ciphertext pair"
            )
    return data


def names(path: Path) -> list:
    """Credential names in the store, sorted. Resolvable WITHOUT the key.

    This is what lets a preflight run on a machine with no key and still say
    «this credential is not in the store» — a missing name and a missing key
    are different problems and get different findings.
    """
    return sorted(load_store(path))


def decrypt_all(path: Path) -> dict:
    """Every credential as `{name: plaintext}`, decrypted in memory.

    Nothing is written. A wrong key raises immediately on the first value
    rather than yielding a partial store, because Fernet is authenticated.
    """
    store = load_store(path)
    if not store:
        return {}
    fernet = _fernet(_require_key())
    from cryptography.fernet import InvalidToken

    out = {}
    for name in sorted(store):
        try:
            out[name] = fernet.decrypt(store[name].encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise SecretError(
                f"cannot decrypt {name!r}: the key in {KEY_ENV} is not the key "
                f"this store was written with, or the store was tampered with. "
                f"Check the value set in the scheduler routine's env config."
            ) from exc
        except UnicodeDecodeError as exc:
            raise SecretError(
                f"cannot decode {name!r} after decryption: the stored value is "
                f"not UTF-8 text"
            ) from exc
    return out


def _atomic_write(path: Path, text: str, *, private: bool = False) -> None:
    """Write via a sibling temp file and one rename — never a partial store.

    `private=True` is for content that is plaintext for its whole life: the
    decrypted store. Three things change, and each closes a real gap that a
    plain `open("w")` left:

    - **`O_EXCL`, so an existing path is never opened.** The temp directory
      name is derived from the base path and is therefore predictable. On a
      shared `/tmp` — a Linux box, a cloud runner — another local account can
      pre-create the `.tmp` sibling as a symlink, and an ordinary open would
      follow it and write every credential into their file. `O_EXCL` refuses
      an existing path outright, symlink or not.
    - **mode 0600 at creation, not after.** Creating world-readable and
      chmod-ing afterwards leaves a window in which the plaintext is readable
      by anything on the machine.
    - **the temp file is removed if anything fails**, so an interruption
      between write and rename cannot strand a full plaintext store under a
      name nothing ever cleans up.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if not private:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        tmp.replace(path)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_BINARY"):
        # Windows only, and load-bearing there. Without it this descriptor is
        # opened in text mode and every `\n` becomes `\r\n`, so each credential
        # gains a trailing CR. `parse_secrets_file` strips it — but the ROLE
        # does not: it sources the file in its shell, where `$TOKEN` then ends
        # in CR. The two halves of the subsystem would hold different values,
        # and the leak scan builds its needles from the stripped one — so a
        # role leaking the credential it is actually using would not match.
        # An authentication failure would be the visible symptom; the scan
        # going quiet is the dangerous one.
        flags |= os.O_BINARY
    try:
        fd = os.open(str(tmp), flags, 0o600)
    except FileExistsError as exc:
        raise SecretError(
            f"refusing to write the decrypted store: {tmp} already exists. "
            "It is removed on every normal path, so its presence means either "
            "a crashed run or another process claiming the name. Inspect and "
            "remove it by hand."
        ) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(str(tmp), str(path))
    except BaseException:
        # BaseException, not Exception: a KeyboardInterrupt here would
        # otherwise leave the plaintext behind, which is the exact outcome
        # this branch exists to prevent.
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise


def store_secret(path: Path, name: str, plaintext: str) -> None:
    """Encrypt one credential and upsert it, leaving the others untouched.

    Reads the existing store, replaces exactly one entry, writes atomically.
    Because each value is encrypted independently, the diff is one line and
    no other credential is re-encrypted.
    """
    name = _require_name(name)
    if not isinstance(plaintext, str) or not plaintext:
        raise SecretError(f"the value for {name} must be a non-empty string")
    # Refused at STORE time, not only at render time: a newline would split
    # into a second line that parses as another credential, and finding that
    # out when the tick materialises is finding out too late — the owner is
    # not there at 07:00 to re-enter it.
    if "\n" in plaintext or "\r" in plaintext:
        raise SecretError(
            f"the value for {name} contains a newline, which cannot be "
            f"represented in the KEY=VALUE file a role sources"
        )
    fernet = _fernet(_require_key())
    store = load_store(path)
    store[name] = fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    _atomic_write(
        path, json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


# --------------------------------------------------------------------------
# the decrypted file a role sources
# --------------------------------------------------------------------------

def render_env(values: dict) -> str:
    """The `KEY=VALUE` text of the decrypted file (§6.6).

    A value may not contain a newline: it would produce a second line that
    parses as another credential, or as a malformed one.
    """
    lines = []
    for name in sorted(values):
        value = values[name]
        if "\n" in value or "\r" in value:
            raise SecretError(
                f"the value of {name} contains a newline, which cannot be "
                f"represented in the KEY=VALUE file a role sources"
            )
        lines.append(f"{name}={value}")
    return "".join(line + "\n" for line in lines)


def materialise(store_path: Path, target: Path) -> Path:
    """Decrypt the whole store into `target`, outside the repository.

    Outside the repository is load-bearing three times over: `git status`
    never sees it, so the guard cannot mistake it for a role's write; staging
    can never pick it up; and it cannot survive into a commit by any path.

    Permissions, stated plainly because a friend should not learn from a
    docstring that a protection applies when it does not:

    - On POSIX the file is chmod 0600 — readable by this account only.
    - **On Windows the chmod is a no-op.** Python's `chmod` cannot express a
      POSIX mode there, so the file inherits the temp directory's ACL: it is
      readable by any process running as the same account. Nothing here
      narrows that.

    What bounds it on every platform is lifetime, not permission: `destroy()`
    removes it, and the tick calls that from the same `finally` that releases
    the lock. On a cloud runner the sandbox is discarded with it; on a local
    machine `destroy()` is the only bound there is.
    """
    values = decrypt_all(store_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, render_env(values), private=True)
    try:
        target.chmod(0o600)
    except OSError:
        # Windows has no POSIX mode bits; the file is still outside the repo.
        pass
    return target


def destroy(target: Path) -> bool:
    """Remove the decrypted file. Safe when it was never materialised.

    Callable from a `finally`: a tick that crashes must not leave the
    decrypted store behind, and a tick that never materialised one must not
    fail on the way out.
    """
    # The `.tmp` sibling first, and unconditionally: a run interrupted between
    # write and rename leaves the WHOLE decrypted store under that name, and
    # nothing else in the engine would ever remove it. Removing only `target`
    # made the docstring's «lifetime is what bounds it» false in exactly the
    # case — a crash — where it is the only thing bounding it.
    sibling = target.with_name(target.name + ".tmp")
    try:
        sibling.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise SecretError(
            f"cannot remove the partial decrypted store at {sibling}: {exc}") from exc
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SecretError(f"cannot remove the decrypted store at {target}: {exc}") from exc
