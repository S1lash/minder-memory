"""Shared fixtures for the roles-core suites.

Used by `test_roles_config`, `test_roles_cadence`, `test_roles_guard`,
`test_roles_context`, `test_roles_log` and `test_roles_run`. Pure filesystem +
git helpers: this module imports **no** roles module, so it stays importable
while the implementation is still red. The one place a roles module is needed
(`role_config`, a `RoleConfig` factory) imports it lazily inside the function,
so the failure surfaces inside the test that asked for it.

Cross-platform contract this fixture holds itself to (CORE-SPEC §0):

- every path is built with `pathlib`; no separator is ever hardcoded and no
  path is interpolated into a shell string;
- every read and write passes `encoding="utf-8"` explicitly — the fixture must
  not rely on the locale encoding any more than the engine may;
- every text file is written with `newline="\\n"`, so fixtures are LF on
  Windows too — the LF assertions in the log suite assert the writer's pin,
  not the platform's default;
- git is driven through `subprocess` argument lists (never `shell=True`), with
  identity, `core.autocrlf=false` and `core.quotepath` left at its DEFAULT so
  the `-z` requirement in §3.4 rule 1 is actually exercised.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Make scripts/ importable — same shape as the rest of the suite.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# --------------------------------------------------------------------------
# plain files
# --------------------------------------------------------------------------

def write_text(path: Path, text: str) -> Path:
    """Write `text` as UTF-8 with LF endings, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# a Minder Memory base
# --------------------------------------------------------------------------

DEFAULT_BODY = (
    "## Проверка\n"
    "\n"
    "Посмотри state/seen.txt и сравни с доской.\n"
    "\n"
    "## Задача\n"
    "\n"
    "Сверь доску с базой и занеси расхождения.\n"
    "\n"
    "## Завершение\n"
    "\n"
    "Обнови state/seen.txt.\n"
)

BASE_DIRNAME = "zettelkasten"


def make_base(tmp: Path, dirname: str = BASE_DIRNAME) -> Path:
    """Create `<tmp>/<dirname>` with the folders the roles core reads.

    `dirname` is a parameter, not a constant, because §1.1 derives the sugar
    prefix from `base.name` — an owner who renames their base must still get
    working sugar, and a fixture that can only build `zettelkasten/` could
    never catch a hardcoded constant.
    """
    base = Path(tmp) / dirname
    for sub in (
        "_system/roles",
        "_system/state",
        "_system/views",
        "_sources/inbox/roles",
    ):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def roles_dir(base: Path) -> Path:
    return base / "_system" / "roles"


def role_md_text(
    role_id: str | None = "notion-sync",
    name: str | None = "Ноушн-сверщик",
    cadence: str | None = "daily 07:00",
    *,
    status: str | None = None,
    writes: str | None = None,
    secrets: str | None = None,
    constitution: str | None = None,
    timeout_seconds: str | None = None,
    extra: str | None = None,
    body: str = DEFAULT_BODY,
) -> str:
    """Render a role.md.

    Every frontmatter key is an *optional raw line* so a test can omit a
    required key, or supply a deliberately malformed value, without the
    fixture second-guessing it. `writes` / `secrets` / `constitution` are
    passed as raw YAML text (e.g. `"[state, inbox]"`), not python objects.
    """
    lines = ["---"]
    if role_id is not None:
        lines.append(f"id: {role_id}")
    if name is not None:
        lines.append(f"name: {name}")
    if cadence is not None:
        lines.append(f"cadence: {cadence}")
    if status is not None:
        lines.append(f"status: {status}")
    if writes is not None:
        lines.append(f"writes: {writes}")
    if secrets is not None:
        lines.append(f"secrets: {secrets}")
    if constitution is not None:
        lines.append(f"constitution: {constitution}")
    if timeout_seconds is not None:
        lines.append(f"timeout_seconds: {timeout_seconds}")
    if extra is not None:
        lines.append(extra)
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body


def write_role(base: Path, dir_name: str, **kwargs) -> Path:
    """Write `<base>/_system/roles/<dir_name>/role.md`; returns the role dir."""
    role_dir = roles_dir(base) / dir_name
    write_text(role_dir / "role.md", role_md_text(**kwargs))
    return role_dir


def write_state(base: Path, dir_name: str, relpath: str, text: str) -> Path:
    """Write a file under a role's `state/`. `relpath` uses `/` separators."""
    target = roles_dir(base) / dir_name / "state"
    for part in relpath.split("/"):
        target = target / part
    return write_text(target, text)


RUN_FRAME = (
    "# Run frame\n"
    "\n"
    "role_id: {{ROLE_ID}}\n"
    "role_name: {{ROLE_NAME}}\n"
    "repo_root: {{REPO_ROOT}}\n"
    "base: {{BASE}}\n"
    "state_dir: {{STATE_DIR}}\n"
    "allowed_writes: {{ALLOWED_WRITES}}\n"
    "secrets_file: {{SECRETS_FILE}}\n"
    "secret_names: {{SECRET_NAMES}}\n"
    "now_local: {{NOW_LOCAL}}\n"
    "last_run: {{LAST_RUN}}\n"
)

PLACEHOLDERS = (
    "{{ROLE_ID}}",
    "{{ROLE_NAME}}",
    "{{REPO_ROOT}}",
    "{{BASE}}",
    "{{STATE_DIR}}",
    "{{ALLOWED_WRITES}}",
    "{{SECRETS_FILE}}",
    "{{SECRET_NAMES}}",
    "{{NOW_LOCAL}}",
    "{{LAST_RUN}}",
)

MINDER_TEXT = "# How the base works\n\nRecords, knowledge, hubs.\n"

CONSTITUTION_TEXT = (
    "# Constitution core\n"
    "\n"
    "## `axiom-identity-001` — If it can be better, it should be better\n"
)


def write_run_frame(base: Path, text: str = RUN_FRAME) -> Path:
    return write_text(roles_dir(base) / "_run-frame.md", text)


def write_minder(base: Path, text: str = MINDER_TEXT) -> Path:
    return write_text(roles_dir(base) / "_minder.md", text)


def write_constitution_view(base: Path, text: str = CONSTITUTION_TEXT) -> Path:
    return write_text(base / "_system" / "views" / "constitution-core.md", text)


def secrets_path(base: Path) -> Path:
    """The DECRYPTED file for a fixture base — outside the repository (§6.4).

    Paired with `write_secrets`: the two must name the same file, or a test
    would hand the guard a path to credentials nobody wrote. Outside the repo
    is the property that matters and is asserted directly in the store suite;
    inside the caller's tmp dir is this fixture's own hygiene.
    """
    return base.parent.parent / "roles-decrypted-secrets.env"


# --------------------------------------------------------------------------
# the encrypted store (§6)
# --------------------------------------------------------------------------
#
# `<base>/_system/state/secrets.enc.json` is COMMITTED — a flat
# `{name: ciphertext}` map, each value encrypted independently. The key lives
# only in `MINDER_MEMORY_ROLES_KEY`, per run, from the scheduler's environment.
#
# These helpers build a store WITHOUT going through the module under test, so
# a test can assert on real ciphertext that the engine did not produce — and
# so a broken writer cannot make its own reader look correct.

KEY_ENV = "MINDER_MEMORY_ROLES_KEY"                       # §6.3, verbatim
STORE_RELPATH = "zettelkasten/_system/state/secrets.enc.json"


def store_path(base: Path) -> Path:
    """`<base>/_system/state/secrets.enc.json` — §6.2."""
    return base / "_system" / "state" / "secrets.enc.json"


def have_cryptography() -> bool:
    try:
        import cryptography.fernet
        return bool(cryptography.fernet)
    except ImportError:
        return False


def generate_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("utf-8")


def encrypt_value(key: str, plaintext: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(key.encode("utf-8")).encrypt(
        plaintext.encode("utf-8")).decode("utf-8")


def write_encrypted_store(base: Path, key: str, pairs: dict) -> Path:
    """Build a store directly, bypassing the engine's writer."""
    blob = {name: encrypt_value(key, value) for name, value in pairs.items()}
    return write_text(store_path(base),
                      json.dumps(blob, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n")


def read_store(base: Path) -> dict:
    return json.loads(store_path(base).read_text(encoding="utf-8"))


def key_env(value: str | None):
    """Context manager setting (or clearing) `MINDER_MEMORY_ROLES_KEY` for a block."""
    import unittest.mock
    env = {k: v for k, v in os.environ.items() if k != KEY_ENV}
    if value is not None:
        env[KEY_ENV] = value
    return unittest.mock.patch.dict(os.environ, env, clear=True)


def write_secrets(base: Path, pairs: dict) -> Path:
    """Give a base real, USABLE credentials, and return the decrypted file.

    Since §6 a credential is usable only when three things line up: the
    encrypted store is committed, `MINDER_MEMORY_ROLES_KEY` is set, and the tick has
    materialised the decrypted file the guard and the role both read. This
    does all three, because every caller wants «this base has working
    credentials» and none of them wants to know that it now takes three steps.

    Deliberately NOT a plaintext fallback. Resurrecting the gitignored file
    would make these tests pass against a store that cannot exist in a cloud
    clone — the exact defect §6 removed — and each test would then assert a
    property of a world the engine no longer has.

    The decrypted file goes OUTSIDE the repo but INSIDE the caller's tmp dir,
    so a test that never runs under `RolesCliTestCase` still leaves no
    plaintext behind in the real OS temp directory.
    """
    import roles_secrets

    key = generate_key()
    os.environ[KEY_ENV] = key
    write_encrypted_store(base, key, pairs)
    target = base.parent.parent / "roles-decrypted-secrets.env"
    return roles_secrets.materialise(store_path(base), target)


def write_prefix(path: str, flat: bool = False):
    """Build a `WritePrefix` (§1.1). Lazy import keeps this module red-safe."""
    import roles_config  # noqa: PLC0415  (deliberate: keeps the fixture red-safe)

    return roles_config.WritePrefix(path=path, flat=flat)


def role_config(base: Path, **overrides):
    """Build a `RoleConfig` without going through disk.

    Imports `roles_config` lazily so this fixture module stays importable
    while the implementation does not exist yet.
    """
    import roles_config  # noqa: PLC0415  (deliberate: keeps the fixture red-safe)

    role_id = overrides.pop("id", "notion-sync")
    fields = {
        "id": role_id,
        "name": "Ноушн-сверщик",
        "cadence": "daily 07:00",
        "status": "active",
        # derived from base.name, never a constant — see make_base
        "write_prefixes": (
            write_prefix(f"{base.name}/_system/roles/{role_id}/state/"),
        ),
        "secrets": (),
        "constitution": False,
        "timeout_seconds": 900,
        "body": DEFAULT_BODY,
        "dir": roles_dir(base) / role_id,
    }
    fields.update(overrides)
    return roles_config.RoleConfig(**fields)


# --------------------------------------------------------------------------
# a throwaway git repo
# --------------------------------------------------------------------------

def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in `cwd` with a pinned identity. Never uses a shell."""
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "roles-test",
        "GIT_AUTHOR_EMAIL": "roles-test@example.com",
        "GIT_COMMITTER_NAME": "roles-test",
        "GIT_COMMITTER_EMAIL": "roles-test@example.com",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


COMMITTED_TREE = {
    # §6: the store is COMMITTED ciphertext, so nothing about it is ignored.
    # The decrypted file lives outside the repo entirely.
    ".gitignore": "*.tmp\n",
    "README.md": "# throwaway\n",
    "zettelkasten/1_projects/PROJECTS.md": "# Projects\n",
    "zettelkasten/2_areas/architecture.md": "# Architecture\n\nowner-facing doc\n",
    "zettelkasten/_sources/inbox/roles/.gitkeep": "",
    "zettelkasten/_system/roles/notion/state/seen.txt": "2026-07-01\n",
    "zettelkasten/_system/roles/other/state/seen.txt": "2026-07-01\n",
}


def init_repo(tmp: Path, base_dirname: str = BASE_DIRNAME) -> Path:
    """A throwaway repo with the zettelkasten skeleton committed.

    Returns the repo root. `<repo>/<base_dirname>` is a usable Minder Memory base, so a
    guard test and a context test can share one fixture. `base_dirname` is a
    parameter for the same reason `make_base`'s is: the sugar derives from
    `base.name`, so a fixture that can only build `zettelkasten/` cannot catch
    a hardcoded constant.
    """
    repo = Path(tmp) / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    # LF in the index on every platform — the guard compares literal paths and
    # the log suite asserts LF bytes; autocrlf would make both machine-dependent.
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "commit.gpgsign", "false")
    for rel, text in COMMITTED_TREE.items():
        # the base name appears in paths AND inside .gitignore's body, so a
        # renamed base must be substituted in both or the fixture stops
        # matching the layout every prefix is derived from
        write_text(repo_path(repo, rel.replace(BASE_DIRNAME, base_dirname, 1)),
                   text.replace(BASE_DIRNAME, base_dirname))
    for sub in ("_system/state", "_system/views"):
        (repo / base_dirname / sub).mkdir(parents=True, exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def repo_base(repo: Path) -> Path:
    return repo / BASE_DIRNAME


def repo_path(repo: Path, relpath: str) -> Path:
    """Resolve a POSIX repo-relative path against the repo root."""
    out = repo
    for part in relpath.split("/"):
        out = out / part
    return out


def head_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def head_content(repo: Path, relpath: str) -> str:
    """The committed content of `relpath` at HEAD.

    Lets a restore test assert the file matches HEAD *exactly* rather than
    merely existing — existence alone passes a restore that wrote the wrong
    bytes, which is the failure mode a guard test must not miss.
    """
    return git(repo, "show", f"HEAD:{relpath}").stdout


def staged_paths(repo: Path) -> list:
    """Paths with staged changes — `git diff --cached --name-only -z`.

    The index is a second place a change can hide. `git checkout -- <path>`
    restores the working tree FROM the index, so a role that staged its work
    makes every revert a silent no-op; a test that only reads file content
    cannot see it.
    """
    out = git(repo, "diff", "--cached", "--name-only", "-z").stdout
    return [p for p in out.split("\0") if p]


def index_paths(repo: Path) -> list:
    """Every path git currently tracks in the index (`git ls-files -z`)."""
    out = git(repo, "ls-files", "-z").stdout
    return [p for p in out.split("\0") if p]


def can_create(path: Path) -> bool:
    """Whether this filesystem tolerates the name at all.

    Windows rejects `* ? : " < > |` and newlines in filenames outright, so the
    pathspec battery has to ask rather than assume. Returning False means the
    OS refused, never that the engine did.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("probe\n", encoding="utf-8")
        path.unlink()
        return True
    except (OSError, ValueError):
        return False


def porcelain_z(repo: Path) -> str:
    """Raw `git status --porcelain -uall -z` output — for fixture assertions
    only. Production code owns its own invocation; this exists so a test can
    state what git itself reports without importing the module under test."""
    return git(repo, "status", "--porcelain", "-uall", "-z").stdout


def write_json(path: Path, payload) -> Path:
    return write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# OS temp-dir hygiene
# --------------------------------------------------------------------------
#
# `tick-begin` / `role-begin` write their snapshots to a per-tick subdirectory
# of the OS temp dir (§7). The tick removes that directory in wave 2, but the
# TEST SUITE must not depend on wave 2 to stay clean: a suite that leaves a
# `minder-mem-roles-*` directory behind on every run silently fills the developer's
# temp dir and, worse, leaves state a later run could read. These helpers let
# a TestCase record what existed before and remove only what it created.

ROLES_TMP_GLOB = "minder-mem-roles-*"


def roles_tmp_entries() -> set:
    """Every `minder-mem-roles-*` entry currently in the OS temp directory."""
    return set(Path(tempfile.gettempdir()).glob(ROLES_TMP_GLOB))


def purge_roles_tmp(known: set) -> list:
    """Remove every `minder-mem-roles-*` entry that is NOT in `known`.

    Returns what it removed, so a test can assert the suite created some
    litter and then assert it is gone.
    """
    removed = []
    for entry in sorted(roles_tmp_entries() - set(known)):
        shutil.rmtree(entry, ignore_errors=True)
        removed.append(entry)
    return removed
