#!/usr/bin/env python3
"""The role file, the `writes:` allowlist, and every role-relative path.

Owns two things and nothing else:

1. Reading and validating `<base>/_system/roles/{id}/role.md` — frontmatter
   only. The prose body is the owner's own language and is never parsed,
   never split into sections, never inspected for headings. It is carried
   verbatim on ``RoleConfig.body``.
2. Every path a role owns — its directory, its ``state/`` tree, its
   ``log.jsonl``, its ``role.md`` — plus the repo-relative prefix shapes the
   ``writes:`` sugar expands to and the one home of the secrets file. No
   other module rebuilds any of them.

An unknown frontmatter key is refused. Silently ignoring one is how a role
ends up with no credential and reports success: a typo'd or stale key must
fail loudly at validate time, not produce a 401 at 07:00.

``secrets:`` is a **declaration** for preflight and for the diff scan, never
an isolation **boundary** — the role reads the secrets file itself, in its
own shell, so any role with a shell can read every credential in it. The
field exists so preflight can tell the owner a declared credential is
missing and so the leak scan knows what to look for; it grants and withholds
nothing.

Every read passes ``encoding="utf-8"`` explicitly. The locale default is
cp1252 on a Western Windows install, and a Cyrillic role body decoded
through it comes back as mojibake that the role would then rewrite into its
own memory.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

import roles_cadence

# --------------------------------------------------------------------------
# path shapes — the single home for every role-relative and engine path
# --------------------------------------------------------------------------

# Base-relative POSIX shapes. Their repo-relative forms are built at call
# time from `base.name`: `writes:` prefixes are compared against `git status`
# output, which is repo-relative, and an owner who renames their base would
# get sugar expanding to a prefix that matches nothing if the leading
# component were a constant.
ROLES_REL_TO_BASE = "_system/roles"
INBOX_REL_TO_BASE = "_sources/inbox/roles"
# The ENCRYPTED store, committed on purpose (§6.2): a gitignored plaintext
# file does not exist in a cloud clone, so a role that reaches an
# authenticated service could never run there.
SECRETS_STORE_REL_TO_BASE = "_system/state/secrets.enc.json"

# The DECRYPTED file a role sources lives in the OS temp directory, never in
# the repository (§6.4) — so `git status` cannot see it, staging cannot pick
# it up, and it cannot survive into a commit by any path.
SECRETS_TEMP_DIR_PREFIX = "minder-mem-roles-"
SECRETS_TEMP_NAME = "secrets.env"

# What makes a directory THIS subsystem's base: it carries the roles CLI.
# The marker is the CLI itself because it cannot be absent while the code
# looking for it is running, and because every other candidate can legitimately
# be missing — `_system/roles/` is absent on a base with no roles yet, which
# §1 calls normal.
ROLES_CLI_REL_TO_BASE = "_system/scripts/roles_run.py"

ROLE_FILENAME = "role.md"
STATE_DIRNAME = "state"
LOG_FILENAME = "log.jsonl"

DEFAULT_TIMEOUT_SECONDS = 900
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 86400

KNOWN_KEYS = (
    "id",
    "name",
    "cadence",
    "status",
    "writes",
    "secrets",
    "constitution",
    "timeout_seconds",
)
STATUSES = ("active", "paused")
SUGAR_STATE = "state"
SUGAR_INBOX = "inbox"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SECRETS_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n(.*)\Z", re.DOTALL)
_DRIVE_RE = re.compile(r"^[A-Za-z]:")

# Notepad and PowerShell both emit a byte-order mark; a role written there
# must not be dead on arrival.
_BOM = "\ufeff"


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that REFUSES a duplicate mapping key instead of last-wins.

    PyYAML's default is silent last-wins, and the key that makes it dangerous
    is `status`. A role written `status: paused` with an `status: active` line
    left below it parses as ACTIVE: the owner reads the file, sees the word
    `paused`, and the role runs anyway — reaching outward on a schedule the
    owner believes they stopped. Unknown keys are already a loud error; a
    REPEATED known key was the quiet one.
    """


def _no_duplicate_keys(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"duplicate key {key!r} — the second one would silently win",
                key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


class RoleConfigError(Exception):
    """A role file (or the secrets file) is unusable. Names file and defect."""


def roles_root(base: Path) -> Path:
    """`<base>/_system/roles` — where role directories and engine files live."""
    return base.joinpath(*ROLES_REL_TO_BASE.split("/"))


def secrets_store(base: Path) -> Path:
    """The encrypted, committed credential store (§6.2)."""
    return base.joinpath(*SECRETS_STORE_REL_TO_BASE.split("/"))


def secrets_file(base: Path) -> Path:
    """The DECRYPTED file a role sources — outside the repository (§6.4).

    Derived from the base path so the tick can materialise it, `check` can
    read values from it, and `secrets-close` can find it again without being
    told where it is. `{{SECRETS_FILE}}` renders this, and the role's
    contract is unchanged: `set -a; . "$SECRETS_FILE"; set +a`.
    """
    key = hashlib.blake2s(
        str(base.resolve()).encode("utf-8"), digest_size=8
    ).hexdigest()
    return (Path(tempfile.gettempdir()) / f"{SECRETS_TEMP_DIR_PREFIX}{key}"
            / SECRETS_TEMP_NAME)


def repo_root(base: Path) -> Path:
    """The repository that contains the base (§1.1)."""
    return base.parent


def resolve_base(base: Path) -> Path:
    """Absolute, normalised base — the one place a base becomes a real path.

    Every repo-relative prefix in this module is built from `base.name`, and
    `Path(".").name` is the empty string. Passed through unresolved, the
    `state` sugar expands to `/_system/roles/{id}/state/`, which matches
    nothing: every file the role writes to its own memory is then classified
    out of zone and reverted, on every run, while every surface reports
    success. `--base .` is the engine's own house convention elsewhere
    (`reconcile_tasks.py`, `reconcile_calendar.py`), so resolving is the fix,
    not refusing.

    Two shapes cannot be resolved into a usable base, and both are loud:
    a filesystem root has no name for the sugar to expand from, and a base
    whose parent is not a directory has no repository to be relative to.
    """
    resolved = base.resolve()
    if not resolved.name:
        raise RoleConfigError(
            f"--base {base} resolves to {resolved}, a filesystem root: the "
            f"`writes` sugar expands from the base directory's name, so a "
            f"role could never write to its own state"
        )
    if not resolved.parent.is_dir():
        raise RoleConfigError(
            f"--base {base} resolves to {resolved}, whose parent {resolved.parent} "
            f"is not a directory: the repository containing the base is where "
            f"every write prefix is relative to, and it does not exist"
        )
    return resolved


def _repo_prefix(base: Path, rel_to_base: str) -> str:
    """A base-relative POSIX shape as a repo-relative prefix."""
    return f"{base.name}/{rel_to_base}"


def roles_prefix(base: Path) -> str:
    """Repo-relative prefix of the roles tree."""
    return _repo_prefix(base, ROLES_REL_TO_BASE)


def inbox_prefix(base: Path) -> str:
    """Repo-relative prefix the `inbox` sugar expands to."""
    return _repo_prefix(base, INBOX_REL_TO_BASE) + "/"


def secrets_prefix(base: Path) -> str:
    """Repo-relative path of the encrypted store — the in-repo artifact a
    role must never be allowed to write."""
    return _repo_prefix(base, SECRETS_STORE_REL_TO_BASE)


def state_prefix_for(base: Path, role_id: str) -> str:
    """Repo-relative prefix the `state` sugar expands to, for one role."""
    return f"{roles_prefix(base)}/{role_id}/{STATE_DIRNAME}/"


def discover_base(repo: Path) -> Path:
    """The one Minder Memory base in `repo`. Raises when it is not exactly one.

    «Where is the base» is a fact, and a fact has one home. The base
    directory name is not a constant — the `writes` sugar expands from
    `base.name` and an owner may rename it — so every caller has to derive
    it, and three prose files each derived it differently, with a different
    behaviour when the derivation failed.

    Zero matches and more than one are both loud. Never an empty answer: an
    empty base is how a renamed base becomes a tick that reports «no roles
    due» every night forever, with every surface green.

    The scan is one level deep, because the base is a directory OF the
    repository — `base.parent` is the repo root (§1.1). It is not derived
    from this file's own location: `--repo` names the tree being asked
    about, which need not be the tree this code was installed into.
    """
    marker = ROLES_CLI_REL_TO_BASE.split("/")
    try:
        children = sorted(repo.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        raise RoleConfigError(f"cannot read the repository at {repo} ({exc})") from exc
    found = [
        child for child in children
        if child.is_dir() and child.joinpath(*marker).is_file()
    ]
    if len(found) == 1:
        return found[0]
    if not found:
        raise RoleConfigError(
            f"no Minder Memory base in {repo}: no directory there contains "
            f"{ROLES_CLI_REL_TO_BASE}"
        )
    raise RoleConfigError(
        f"{len(found)} candidate bases in {repo}: "
        f"{', '.join(child.name for child in found)} — each contains "
        f"{ROLES_CLI_REL_TO_BASE}, so which one is the base cannot be decided here"
    )


def to_repo_relative(repo: Path, path: Path) -> str | None:
    """POSIX repo-relative form of `path`, or `None` when it is outside `repo`.

    The single home for this conversion, so no module does it by hand and no
    two modules disagree about what "outside" means. It is a pure path
    operation, not a filesystem probe: the guard calls it for deleted paths,
    which by definition are not on disk.

    Comparison is component-based, never a string prefix — `/tmp/repo-backup`
    merely starts with the characters of `/tmp/repo`, and a string test would
    hand the guard a stranger's file as though it were the owner's.

    Each caller decides what `None` means: the guard, that the path is
    outside `git status` entirely (§3.4 rule 10); the context, that a header
    line falls back to the absolute POSIX path.
    """
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# the write allowlist
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class WritePrefix:
    """One entry of the `writes:` allowlist, already expanded.

    ``path`` is POSIX and repo-relative and is stored VERBATIM: nothing
    appends a trailing slash, because the motivating case is a FILE the
    owner actually reads (`zettelkasten/2_areas/architecture.md`) and a
    slash welded onto it would match nothing at all.

    ``flat`` says no subdirectory may exist beneath the prefix. It rides on
    the prefix rather than being a case the guard knows about, so the guard
    never needs its own copy of a path this module already owns.
    """

    path: str
    flat: bool = False

    def covers(self, candidate: str) -> bool:
        """The §1.1 matching rule, one rule for both a file and a directory.

        A path `p` is under prefix `q` when ``p == q`` or
        ``p.startswith(q + "/")``. That single rule keeps
        `architecture.md.bak` correctly out of zone, which a bare
        ``startswith`` would not, and keeps `state-extra/` out of a
        `state/` zone.
        """
        anchor = self.path.rstrip("/")
        if not anchor:
            return False
        if candidate == anchor:
            return True
        if not candidate.startswith(anchor + "/"):
            return False
        if self.flat and "/" in candidate[len(anchor) + 1:]:
            return False
        return True


@dataclass(frozen=True)
class RoleConfig:
    """One validated role. The only home for that role's paths."""

    id: str
    name: str
    cadence: str
    status: str
    write_prefixes: tuple
    secrets: tuple
    constitution: bool
    timeout_seconds: int
    body: str
    dir: Path

    @property
    def state_dir(self) -> Path:
        return self.dir / STATE_DIRNAME

    @property
    def log_path(self) -> Path:
        return self.dir / LOG_FILENAME

    @property
    def role_file(self) -> Path:
        return self.dir / ROLE_FILENAME


# --------------------------------------------------------------------------
# reading role.md
# --------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    """Read UTF-8, tolerate a BOM and CRLF, refuse anything undecodable."""
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RoleConfigError(f"{path}: not valid UTF-8 ({exc.reason})") from exc
    except OSError as exc:
        raise RoleConfigError(f"{path}: cannot be read ({exc})") from exc
    return raw.lstrip(_BOM).replace("\r\n", "\n").replace("\r", "\n")


def _split_frontmatter(path: Path, text: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise RoleConfigError(
            f"{path}: no closing frontmatter fence — a role file starts with "
            f"`---`, a YAML block, and a closing `---`"
        )
    try:
        parsed = yaml.load(match.group(1), Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise RoleConfigError(f"{path}: frontmatter is not valid YAML ({exc})") from exc
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise RoleConfigError(f"{path}: frontmatter must be a YAML mapping")
    return parsed, match.group(2)


def _require_str(path: Path, key: str, value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoleConfigError(f"{path}: `{key}` must be a non-empty string")
    return value


def _parse_timeout(path: Path, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoleConfigError(
            f"{path}: `timeout_seconds` must be a whole number of seconds"
        )
    if not MIN_TIMEOUT_SECONDS <= value <= MAX_TIMEOUT_SECONDS:
        raise RoleConfigError(
            f"{path}: `timeout_seconds` must be between {MIN_TIMEOUT_SECONDS} "
            f"and {MAX_TIMEOUT_SECONDS}, got {value}"
        )
    return value


def _parse_secret_names(path: Path, value) -> tuple:
    if not isinstance(value, list):
        raise RoleConfigError(f"{path}: `secrets` must be a list of names")
    names = []
    for entry in value:
        if not isinstance(entry, str) or not _SECRET_NAME_RE.match(entry):
            raise RoleConfigError(
                f"{path}: secret name {entry!r} must match [A-Z][A-Z0-9_]*"
            )
        names.append(entry)
    return tuple(names)


def _covers_a_role_log(base: Path, anchor: str) -> bool:
    """True when this prefix would let a role write a role's tick log.

    The tick owns `log.jsonl`; a role writing its own log is a defect worth
    catching (§3.4 rule 9). A prefix at or above a role directory covers
    every role's log, so it is refused too.
    """
    parts = anchor.split("/")
    roles_parts = roles_prefix(base).split("/")
    if (
        len(parts) == len(roles_parts) + 2
        and parts[: len(roles_parts)] == roles_parts
        and parts[-1] == LOG_FILENAME
    ):
        return True
    if len(parts) <= len(roles_parts):
        return parts == roles_parts[: len(parts)]
    if len(parts) == len(roles_parts) + 1:
        return parts[: len(roles_parts)] == roles_parts
    return False


def normalize_prefix(entry: str) -> str:
    """Collapse `.` and empty components, keeping any trailing slash.

    §1.1 says an entry must not contain `..` AFTER NORMALISATION, which
    presumes this step. Without it `zettelkasten/./2_areas` and
    `zettelkasten//2_areas` validate cleanly and then match nothing: every
    write the role makes is reverted, nightly, while `validate` says ok.
    """
    trailing = entry.endswith("/")
    parts = [part for part in entry.split("/") if part not in ("", ".")]
    joined = "/".join(parts)
    return joined + "/" if trailing and joined else joined


def _validate_explicit_prefix(path: Path, base: Path, entry: str) -> str:
    if not entry.strip():
        raise RoleConfigError(f"{path}: a `writes` entry may not be empty")
    # Absoluteness is judged on what the owner WROTE — normalising first
    # would turn `/etc/cron.d/` into an innocent relative prefix.
    if entry.startswith("/") or entry.startswith("\\") or _DRIVE_RE.match(entry):
        raise RoleConfigError(
            f"{path}: `writes` entry {entry!r} must be repo-relative"
        )
    entry = normalize_prefix(entry)
    anchor = entry.rstrip("/")
    if not anchor:
        raise RoleConfigError(f"{path}: a `writes` entry may not be empty")
    parts = anchor.split("/")
    if ".." in parts:
        raise RoleConfigError(
            f"{path}: `writes` entry {entry!r} escapes the repository"
        )
    if parts[0] == ".git":
        raise RoleConfigError(
            f"{path}: `writes` entry {entry!r} points inside git internals"
        )
    secrets = secrets_prefix(base)
    if secrets == anchor or secrets.startswith(anchor + "/"):
        raise RoleConfigError(
            f"{path}: `writes` entry {entry!r} covers the secrets file"
        )
    if _covers_a_role_log(base, anchor):
        raise RoleConfigError(
            f"{path}: `writes` entry {entry!r} covers a role's {LOG_FILENAME}, "
            f"which the tick owns"
        )
    owned = _owner_authored_breadth(base, anchor)
    if owned:
        raise RoleConfigError(
            f"{path}: `writes` entry {entry!r} is a directory holding {owned} file(s) "
            f"the owner wrote. Name the ONE file the job maintains, or write into "
            f"the inbox and let the ordinary processing run fold it in — a role does "
            f"not edit records and notes directly. Granting a whole knowledge "
            f"directory hands a role blanket rewrite over work it did not author, "
            f"and the guard cannot tell an intended edit from a destroyed note"
        )
    governing = _governing_surface(base, anchor)
    if governing:
        raise RoleConfigError(
            f"{path}: `writes` entry {entry!r} covers {governing}, which decides "
            f"how roles are run or judged. A role may write anything in the base "
            f"except the machinery that bounds it"
        )
    return entry


def _owner_authored_breadth(base: Path, anchor: str) -> int:
    """How many owner-authored files an explicit prefix would hand over, if many.

    Returns 0 when the prefix is fine — a named file, a directory that does not
    exist yet, the role's own state, or the roles inbox door.

    The case this exists for: `writes: [<base>/2_areas]` validated clean and
    granted blanket rewrite over hundreds of the owner's own notes. A role then
    replaced a long reflection note with one line, IN ZONE, and every surface
    reported a clean run — because the guard's question is «did it write where
    it said it would», not «was that its work to rewrite».

    The design already answers this: a role that finds something worth keeping
    drops a note in the inbox and the ordinary processing run folds it in. It
    does not edit records and notes directly. A role that genuinely maintains
    ONE living document names that document.

    Judged on what is on disk, deliberately. A prefix is dangerous in
    proportion to what it actually reaches, and that is a fact about this base
    — not about the string.
    """
    target = base.parent.joinpath(*anchor.split("/"))
    if target.is_file() or not target.exists():
        # A named file is the shape being asked for; a path that does not exist
        # yet is the role's own new territory and holds nothing of the owner's.
        return 0
    if not target.is_dir():
        return 0
    roles_tree = roles_root(base)
    inbox = base.joinpath(*INBOX_REL_TO_BASE.split("/"))
    for exempt in (roles_tree, inbox):
        try:
            target.relative_to(exempt)
            return 0
        except ValueError:
            pass
    count = 0
    for child in target.rglob("*.md"):
        if child.is_file():
            count += 1
            if count > 1:
                # One file in a directory is not «breadth» — an owner may keep a
                # single document in a folder of its own. Two is a collection.
                return _count_all(target)
    return 0


def _count_all(target: Path) -> int:
    return sum(1 for c in target.rglob("*.md") if c.is_file())


def _governing_surface(base: Path, anchor: str) -> str | None:
    """The name of a run-governing surface `anchor` would cover, if any.

    Everything else in this validator refuses a path for being OUTSIDE the
    repository or owned by the tick. This one refuses paths that are squarely
    inside the base and perfectly ordinary to write — and that is the point.

    Without it, `writes: [<base>/_system/scripts]` is accepted, and the role
    rewrites `roles_guard.py` **in zone**: the tick commits it as that role's
    own legitimate output, pushes it, and the next night the role is judged by
    code it wrote itself. The same holds for the tick's prompt under
    `integrations/`, the subagent definition under `.claude/`, the staging
    helpers under `scripts/`, and the ignore rules that decide what `git
    status` is even allowed to report.

    The rule is one sentence — **a role may not write what decides how roles
    are run or judged** — and it is enforced in both directions: an entry that
    covers a governing surface is refused, and so is one nested inside it.
    """
    prefix = f"{base.name}/" if base.name else ""
    surfaces = {
        f"{prefix}_system/scripts": "the engine's own scripts, including the guard",
        f"{prefix}_system/docs": "the system contract",
        f"{prefix}_system/roles/_run-frame.md": "the run frame every role is handed",
        f"{prefix}_system/roles/_minder.md": "the base conventions every role is handed",
        ".claude": "the subagent definition and the tool allowlist",
        "scripts": "the scheduler helpers that stage and deliver",
        "integrations": "the skills, including the tick that runs roles",
        ".github/workflows": "CI, which can run anything",
        ".gitattributes": "how git transforms files on checkout",
        ".gitignore": "what `git status` is allowed to report",
    }
    for surface, why in surfaces.items():
        if anchor == surface or anchor.startswith(surface + "/") \
                or surface.startswith(anchor + "/"):
            return why
    return None


def _parse_writes(path: Path, base: Path, value, role_id: str) -> tuple:
    if not isinstance(value, list):
        raise RoleConfigError(
            f"{path}: `writes` must be a list of prefixes, not a bare value"
        )
    prefixes: list[WritePrefix] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, str):
            raise RoleConfigError(f"{path}: `writes` entry {entry!r} must be a string")
        if entry == SUGAR_STATE:
            prefix = WritePrefix(path=state_prefix_for(base, role_id), flat=False)
        elif entry == SUGAR_INBOX:
            # SOURCES.md registers the `roles` source as flat-md.
            prefix = WritePrefix(path=inbox_prefix(base), flat=True)
        else:
            prefix = WritePrefix(
                path=_validate_explicit_prefix(path, base, entry), flat=False
            )
        # Compared without the trailing slash: `state` and the same path
        # spelled longhand without one are the same zone, and letting both
        # through would also let an explicit non-flat twin of `inbox` past
        # the flat rule.
        anchor = prefix.path.rstrip("/")
        if anchor in seen:
            raise RoleConfigError(
                f"{path}: `writes` expands to a duplicate prefix {prefix.path!r}"
            )
        seen.add(anchor)
        prefixes.append(prefix)
    return tuple(prefixes)


def load_role(role_dir: Path, base: Path) -> RoleConfig:
    """Read and validate one role directory. Raises `RoleConfigError`."""
    role_file = role_dir / ROLE_FILENAME
    if not role_file.is_file():
        raise RoleConfigError(f"{role_file}: no {ROLE_FILENAME} in {role_dir.name}")

    fm, body = _split_frontmatter(role_file, _read_text(role_file))

    unknown = [key for key in fm if key not in KNOWN_KEYS]
    if unknown:
        raise RoleConfigError(
            f"{role_file}: unknown frontmatter key(s) {', '.join(sorted(unknown))} — "
            f"known keys are {', '.join(KNOWN_KEYS)}"
        )
    for key in ("id", "name", "cadence"):
        if key not in fm:
            raise RoleConfigError(f"{role_file}: required key `{key}` is missing")

    role_id = _require_str(role_file, "id", fm["id"])
    if not _ID_RE.match(role_id):
        raise RoleConfigError(
            f"{role_file}: `id` {role_id!r} must match [a-z0-9][a-z0-9-]*"
        )
    if role_id != role_dir.name:
        raise RoleConfigError(
            f"{role_file}: `id` {role_id!r} must equal the directory name "
            f"{role_dir.name!r}"
        )

    name = _require_str(role_file, "name", fm["name"])

    cadence = _require_str(role_file, "cadence", fm["cadence"])
    try:
        roles_cadence.parse_cadence(cadence)
    except roles_cadence.CadenceError as exc:
        raise RoleConfigError(f"{role_file}: `cadence` {cadence!r} — {exc}") from exc

    status = fm.get("status", STATUSES[0])
    if status not in STATUSES:
        raise RoleConfigError(
            f"{role_file}: `status` must be one of {', '.join(STATUSES)}"
        )

    constitution = fm.get("constitution", False)
    if not isinstance(constitution, bool):
        raise RoleConfigError(f"{role_file}: `constitution` must be true or false")

    timeout_seconds = _parse_timeout(role_file, fm.get("timeout_seconds",
                                                       DEFAULT_TIMEOUT_SECONDS))
    secrets = _parse_secret_names(role_file, fm.get("secrets", []))
    write_prefixes = _parse_writes(role_file, base, fm.get("writes", []), role_id)

    if not body.strip():
        raise RoleConfigError(
            f"{role_file}: the body is empty — a role needs instructions"
        )

    return RoleConfig(
        id=role_id,
        name=name,
        cadence=cadence,
        status=status,
        write_prefixes=write_prefixes,
        secrets=secrets,
        constitution=constitution,
        timeout_seconds=timeout_seconds,
        body=body,
        dir=role_dir,
    )


def discover_roles(base: Path) -> list:
    """Every role directory under `<base>/_system/roles`, sorted by name.

    Tolerant by design: a directory whose `role.md` is malformed is still
    listed, because one broken role must never blind the whole tick. Names
    starting with `_` are engine files, not roles. A base with no roles
    directory at all is normal, not an error.
    """
    root = roles_root(base)
    if not root.is_dir():
        return []
    found = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if child.name.startswith("_") or not child.is_dir():
            continue
        if not (child / ROLE_FILENAME).is_file():
            continue
        found.append(child)
    return found


# --------------------------------------------------------------------------
# the secrets file (CORE-SPEC §6)
# --------------------------------------------------------------------------

def parse_secrets_file(path: Path) -> dict:
    """Parse the DECRYPTED credential file into `{KEY: raw value}` (§6.6).

    Its shape is unchanged from the plaintext store it replaces, so nothing
    downstream learns that the store on disk is encrypted.

    UTF-8, LF, one `KEY=VALUE` per line. `KEY` matches `[A-Z][A-Z0-9_]*`;
    the value is the raw remainder of the line — not unquoted, not
    unescaped. A line whose first non-space character is `#` is a comment
    and blank lines are ignored. A malformed line raises, naming the line
    number: skipping it silently is how a role ends up running without the
    credential it declared.
    """
    text = _read_text(path)
    values: dict = {}
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _SECRETS_LINE_RE.match(line)
        if match is None:
            raise RoleConfigError(
                f"{path}: line {number} is not a `KEY=VALUE` pair with "
                f"KEY matching [A-Z][A-Z0-9_]*"
            )
        values[match.group(1)] = match.group(2)
    return values
