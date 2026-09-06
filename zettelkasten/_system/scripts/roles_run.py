#!/usr/bin/env python3
"""The roles CLI — one verb per step of a tick. Composes, owns no domain logic.

Cadence arithmetic lives in `roles_cadence`, the role schema and every path
in `roles_config`, git plumbing in `roles_guard`, the prompt in
`roles_context`, the run line in `roles_log`. This module parses arguments,
calls them in order, and prints. Anything here that reasoned about a date or
a diff would be a second home for a fact one of those modules owns.

    roles_run.py base       --repo R
    roles_run.py secrets-open  --base B   → decrypts the store, prints the path
    roles_run.py secrets-close --base B   → removes it; safe if never opened
    roles_run.py due        --base B --repo R [--now ISO]
    roles_run.py context    --base B --repo R --role ID [--now ISO]
    roles_run.py tick-begin --base B --repo R
    roles_run.py role-begin --base B --repo R --role ID
    roles_run.py check      --base B --repo R --role ID
    roles_run.py log        --base B --role ID --outcome O --ms N
                            [--writes N] [--note TEXT] [--ts ISO]
                            [--reverted JSON] [--reported-only JSON]
    roles_run.py validate   --base B --repo R [--role ID]
                            → {"ok":bool,"findings":[...],"notes":[...]}

Every verb prints JSON except `context`, which prints the prompt itself, and
`base`, which prints one path. `base` exists because «where is the base» is a
fact and a fact has one home: the base directory name is not a constant, so
every caller had to derive it, and three prose files derived it three ways
with three different behaviours on failure. Zero candidates or several is a
loud error here, never an empty string — an empty base is how a renamed base
becomes a tick reporting «no roles due» every night with every surface green.

`due` reports EVERY role with an explicit `due` boolean, so "not due" and
"missing" are never confused. A role whose file is malformed comes back
`due: false` with the error as its reason: the tick surfaces it and carries
on, because one broken role must never abort a tick.

Snapshots live in a per-tick directory under the OS temp directory, whose
name is derived from the repository path — so `check` finds the role
snapshot by convention, and nothing about them lands in the repo. `check`
deletes the role snapshot once it has used it; the tick removes the
directory when it finishes.

`validate` is deterministic and offline by design. Whether a credential
actually works is the creation-time trial run's job; a preflight that
reached out over the network would be non-deterministic and would fail on a
plane. Its findings are unconditional (§7.2): a declared secret with no
resolvable value is named whether the secrets file is missing a key or
missing entirely, because a clean result is the concierge's gate and a
silence here becomes a role that reports success while doing nothing. A role
declaring no secrets on a base with no secrets file is clean — the rule is
about a declared name having no value, never about the file's existence.

`validate` separates blockers from notes. `findings` are blockers and `ok` is
`not findings`, unchanged; `notes` is advisory and never moves `ok`. The one
note today is the unreachable time anchor (§2.1): a `daily 14:00` role never
fires under a once-daily 07:00 tick, but the same cadence is correct on a
scheduler that ticks more often, and this engine cannot see the owner's cron.
A warning that blocked would refuse a working shape; a warning folded into
`findings` would flip the concierge's gate on the commonest cadence there is.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _common import configure_std_streams  # type: ignore
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import roles_cadence
import roles_config
import roles_context
import roles_guard
import roles_log
import roles_secrets

SNAPSHOT_DIR_PREFIX = "minder-mem-roles-"
SNAPSHOT_DIR_KEY_LENGTH = 8
TICK_BASELINE_NAME = "tick.json"
ROLE_SNAPSHOT_NAME = "role-{role_id}.json"

STATUS_UNKNOWN = "unknown"
EXIT_OK = 0
# A blocker is a legitimate result, not a crash: distinct from EXIT_ERROR so a
# caller can tell «this base has a problem» from «the verb could not run».
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class UsageError(Exception):
    """A verb could not run — reported on stderr, never as a stack trace."""


# --------------------------------------------------------------------------
# small helpers — argument shapes and snapshot files
# --------------------------------------------------------------------------

def _host_zone():
    """The host's IANA zone, or `None` when it cannot be named.

    §2 says the caller attaches the host ZONE, and the difference is not
    academic: `astimezone()` yields a fixed OFFSET, so on the day after a DST
    change the cadence re-reads yesterday's timestamp with today's offset,
    moves its local date across the boundary, and a daily role silently skips
    a day — or runs twice — while the reason string says it already ran.

    `zoneinfo` needs the `tzdata` package on Windows, where there is no
    system zone database; without it this returns `None` and the fixed offset
    is used, which is correct except across a DST change.
    """
    key = os.environ.get("TZ")
    if not key:
        try:
            parts = Path("/etc/localtime").resolve().parts
            if "zoneinfo" in parts:
                key = "/".join(parts[parts.index("zoneinfo") + 1:])
        except OSError:
            key = None
    if not key:
        return None
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _resolve_now(raw: str | None) -> datetime:
    """The injected `--now`, or the host clock with the host zone attached."""
    zone = _host_zone()
    if raw is None:
        return datetime.now(zone) if zone else datetime.now(timezone.utc).astimezone()
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UsageError(f"--now {raw!r} is not an ISO-8601 timestamp") from exc
    if value.tzinfo is not None:
        # An injected instant keeps the wall clock the caller wrote. When the
        # host zone agrees with the offset they gave, the ZONE is attached in
        # place of the bare offset — same wall clock, but `last_run` now
        # converts under real DST rules instead of being re-read with today's
        # offset and landing on the wrong local date. A different offset means
        # a different zone was meant, and that choice is left alone.
        if zone is not None and value.astimezone(zone).utcoffset() == value.utcoffset():
            return value.astimezone(zone)
        return value
    return value.replace(tzinfo=zone) if zone else value.astimezone()


def _tick_dir(repo: Path) -> Path:
    key = hashlib.blake2s(
        str(repo.resolve()).encode("utf-8"), digest_size=SNAPSHOT_DIR_KEY_LENGTH
    ).hexdigest()
    return Path(tempfile.gettempdir()) / f"{SNAPSHOT_DIR_PREFIX}{key}"


def _tick_baseline_path(repo: Path) -> Path:
    return _tick_dir(repo) / TICK_BASELINE_NAME


def _role_snapshot_path(repo: Path, role_id: str) -> Path:
    return _tick_dir(repo) / ROLE_SNAPSHOT_NAME.format(role_id=role_id)


def _write_snapshot(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_snapshot(path: Path, what: str) -> dict:
    """Load a snapshot, refusing anything that is not one.

    Parseability is not shape: a valid-JSON list reaches the guard and
    tracebacks, and integer digests attribute garbage and then REVERT on it.
    `UsageError` promises the owner an error, never a stack trace.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"{what} is missing or unreadable at {path}") from exc
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("head"), str)
        or not isinstance(entries, dict)
        or not all(isinstance(k, str) and isinstance(v, str)
                   for k, v in entries.items())
    ):
        raise UsageError(
            f"{what} at {path} is not a snapshot: it needs a string `head` and "
            f"an `entries` mapping of path to digest"
        )
    return payload


def _path_list(flag: str, raw: str | None) -> list:
    """Decode a `--reverted` / `--reported-only` JSON list.

    The tick passes `check`'s own output straight through, so the wire form
    is JSON rather than repeated flags: a reverted path may carry spaces or
    any script, and JSON is the one encoding both sides already agree on.
    Omitting the flag yields `[]`.
    """
    if raw is None:
        return []
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise UsageError(f"{flag} must be a JSON list of paths") from exc
    if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
        raise UsageError(f"{flag} must be a JSON list of paths")
    return value


def _secret_values(base: Path) -> list:
    """Every credential value, for redaction and the leak scan (§6.5).

    Decrypted IN MEMORY from the committed store and written nowhere. Falls
    back to the decrypted file the tick materialised when the key is not in
    this process's environment, and to nothing at all when neither is
    available — a base with no credentials is the ordinary case, and failing
    here would turn «no secrets» into «no run».
    """
    store = roles_config.secrets_store(base)
    if store.is_file() and roles_secrets.key_present():
        try:
            return list(roles_secrets.decrypt_all(store).values())
        except roles_secrets.SecretError:
            # A wrong key must not silence redaction; fall through to the
            # materialised file, which the tick decrypted with the right one.
            pass
    return roles_guard.secret_values(roles_config.secrets_file(base))


def _load_role(base: Path, role_id: str):
    return roles_config.load_role(roles_config.roles_root(base) / role_id, base)


def _last_run_time(cfg) -> datetime | None:
    line = roles_log.last_run(cfg)
    return roles_log.parse_ts(line["ts"]) if line else None


def _emit(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False))


# --------------------------------------------------------------------------
# verbs
# --------------------------------------------------------------------------

def cmd_due(args) -> int:
    now = _resolve_now(args.now)
    rows = []
    for role_dir in roles_config.discover_roles(args.base):
        try:
            cfg = _load_role(args.base, role_dir.name)
        except roles_config.RoleConfigError as exc:
            rows.append({
                "id": role_dir.name,
                "name": role_dir.name,
                "due": False,
                "reason": str(exc),
                "status": STATUS_UNKNOWN,
            })
            continue
        if cfg.status != roles_config.STATUSES[0]:
            due, reason = False, f"status is {cfg.status}"
        else:
            due, reason = roles_cadence.is_due(
                roles_cadence.parse_cadence(cfg.cadence), _last_run_time(cfg), now
            )
        rows.append({
            "id": cfg.id,
            "name": cfg.name,
            "due": due,
            "reason": reason,
            "status": cfg.status,
        })
    _emit(rows)
    return EXIT_OK


def cmd_context(args) -> int:
    cfg = _load_role(args.base, args.role)
    text = roles_context.build_context(
        args.base,
        args.repo,
        cfg,
        now=_resolve_now(args.now),
        last_run_line=roles_log.last_run(cfg),
    )
    print(text)
    return EXIT_OK


def cmd_tick_begin(args) -> int:
    snapshot = roles_guard.capture_snapshot(
        args.repo, roles_config.secrets_file(args.base)
    )
    path = _tick_baseline_path(args.repo)
    _write_snapshot(path, snapshot)
    print(path)
    return EXIT_OK


def cmd_role_begin(args) -> int:
    cfg = _load_role(args.base, args.role)
    snapshot = roles_guard.capture_snapshot(
        args.repo, roles_config.secrets_file(args.base)
    )
    path = _role_snapshot_path(args.repo, cfg.id)
    _write_snapshot(path, snapshot)
    print(path)
    return EXIT_OK


def cmd_check(args) -> int:
    cfg = _load_role(args.base, args.role)
    tick_baseline = _read_snapshot(_tick_baseline_path(args.repo), "the tick baseline")
    snapshot_path = _role_snapshot_path(args.repo, cfg.id)
    role_snapshot = _read_snapshot(snapshot_path, f"the snapshot of role {cfg.id}")
    result = roles_guard.check(
        args.repo,
        tick_baseline,
        role_snapshot,
        cfg.write_prefixes,
        roles_config.secrets_file(args.base),
    )
    _emit(result)
    snapshot_path.unlink(missing_ok=True)
    return EXIT_OK


def cmd_log(args) -> int:
    """Append one run line, with every credential form redacted out of it.

    The run line is written after `check`, so nothing has scanned it: a token
    in the role's own `note:`, or used as a filename so it arrives as a path
    in `reverted`, would be committed and pushed in plain text. The audit
    trail must not be the channel.
    """
    cfg = _load_role(args.base, args.role)
    values = _secret_values(args.base)
    roles_log.append_run(
        cfg,
        ts=_resolve_now(args.ts),
        outcome=args.outcome,
        writes=args.writes,
        reverted=roles_guard.redact_paths(
            _path_list("--reverted", args.reverted), values),
        reported_only=roles_guard.redact_paths(
            _path_list("--reported-only", args.reported_only), values),
        ms=args.ms,
        note=roles_guard.redact(args.note, values) if args.note else args.note,
    )
    return EXIT_OK


def _secret_findings(cfg, values, secrets_path: Path) -> list:
    """Findings for one role's declared credentials (§7.2).

    `values` is `None` when the secrets file does not exist. That case is a
    finding, not a pass: a fresh clone is exactly where a declared name has
    no resolvable value, and staying silent there inverts the gate — the
    role gets created, and at 07:00 it receives an empty variable, takes a
    401, and reports success.

    Values are read only to be measured; none is ever put in a finding.
    """
    findings = []
    for name in cfg.secrets:
        if values is None:
            issue = (
                f"declared secret {name} has no value: the credential store "
                f"does not exist at {secrets_path}"
            )
        elif name not in values:
            issue = f"declared secret {name} is not in the credential store"
        elif isinstance(values, dict) and (
            len(values[name]) < roles_guard.SECRET_SCAN_MIN_LENGTH
        ):
            # Only reachable with the key: a value can be measured only when
            # it has been decrypted. Keyless preflight skips this and the
            # missing-key finding says which checks it skipped.
            issue = (
                f"the value of {name} is shorter than "
                f"{roles_guard.SECRET_SCAN_MIN_LENGTH} characters, so it "
                f"cannot be leak-scanned"
            )
        else:
            continue
        findings.append({"role": cfg.id, "secret": name, "issue": issue})
    return findings


def cmd_base(args) -> int:
    """Print the repository's one Minder Memory base, so no caller derives it itself.

    Every role skill's prelude calls this. Their shell loop only locates a copy
    of this CLI — which directory is the base is decided here, once, and zero
    bases and two bases are loud in the same message everywhere. A caller that
    decided it in shell is a second implementation of a one-home fact, and the
    two diverge in exactly the case that matters: failure.
    """
    print(roles_config.discover_base(args.repo))
    return EXIT_OK


def cmd_secrets_open(args) -> int:
    """Decrypt the store into the OS temp directory and print the path.

    The tick calls this once, before any role runs. Nothing downstream learns
    the store is encrypted: `{{SECRETS_FILE}}` points here and the role's
    `set -a; . "$SECRETS_FILE"; set +a` contract is unchanged.
    """
    target = roles_config.secrets_file(args.base)
    store = roles_config.secrets_store(args.base)
    if not store.is_file():
        # Nothing to open. Printing the path anyway would invite a role to
        # source a file that does not exist; printing nothing says so.
        return EXIT_OK
    roles_secrets.materialise(store, target)
    print(target)
    return EXIT_OK


def cmd_secrets_close(args) -> int:
    """Remove the decrypted file. Safe when nothing was materialised.

    The tick calls this from the same `finally` that releases the lock: a
    tick that crashes must not leave the decrypted store behind, and a tick
    that never opened one must not fail on the way out.
    """
    roles_secrets.destroy(roles_config.secrets_file(args.base))
    return EXIT_OK


def cmd_validate(args) -> int:
    findings = []
    notes = []
    declared_any = False
    role_dirs = roles_config.discover_roles(args.base)
    if args.role:
        role_dirs = [d for d in role_dirs if d.name == args.role]
        if not role_dirs:
            findings.append({"role": args.role, "issue": "no such role"})

    # Names are resolved WITHOUT decrypting, so a preflight runs on a machine
    # that has no key and still reports a credential missing from the store.
    # `None` = the store could not be read at all, which is reported once and
    # suppresses the per-role checks it made unanswerable.
    secrets_path = roles_config.secrets_store(args.base)
    values = None
    unparseable = False
    if secrets_path.is_file():
        try:
            if roles_secrets.key_present():
                # The key is here, so measure as well as resolve. A dict of
                # plaintexts unlocks the value-dependent checks; a list of
                # names is all a keyless preflight can honestly answer.
                values = roles_secrets.decrypt_all(secrets_path)
            else:
                values = roles_secrets.names(secrets_path)
        except roles_secrets.SecretError as exc:
            unparseable = True
            findings.append({"role": None, "issue": str(exc)})


    for role_dir in role_dirs:
        try:
            cfg = _load_role(args.base, role_dir.name)
        except roles_config.RoleConfigError as exc:
            findings.append({"role": role_dir.name, "issue": str(exc)})
            continue
        declared_any = declared_any or bool(cfg.secrets)
        note = roles_cadence.anchor_note(roles_cadence.parse_cadence(cfg.cadence))
        if note is not None:
            notes.append({"role": cfg.id, "cadence": cfg.cadence, "note": note})
        if not unparseable:
            findings.extend(_secret_findings(cfg, values, secrets_path))

    # `ok` reflects blockers only. A note must never flip the concierge's
    # gate: the shape it warns about is correct on a scheduler that ticks
    # more than once a day, and this engine cannot see the owner's cron.
    # A missing key is its own finding, distinct from a missing name: every
    # credential can be present in the store and the run still cannot decrypt
    # one. Only raised when a role actually declares something to decrypt.
    if declared_any and not roles_secrets.key_present():
        findings.append({
            "role": None,
            "issue": (
                f"{roles_secrets.KEY_ENV} is not set, so no credential can be "
                f"decrypted at run time — set it in the scheduler routine's "
                f"env config. Names were still checked against the store; the "
                f"value-dependent check was SKIPPED (scan-length floor), so "
                f"re-run this with the key to see it."
            ),
        })

    ok = not findings
    _emit({"ok": ok, "findings": findings, "notes": notes})
    # Non-zero on a blocker, zero when the only output is notes. Every skill
    # reads the JSON, so this is latent today — but a caller testing `$?`
    # would otherwise read a role with an unresolvable credential as clean,
    # and that is exactly the check the concierge's first gate rests on.
    return EXIT_OK if ok else EXIT_FINDINGS


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minder Memory roles runner")
    verbs = parser.add_subparsers(dest="verb", required=True)

    def add(name, handler, *, base=True, repo=True, role=False, now=False):
        sub = verbs.add_parser(name)
        if base:
            sub.add_argument("--base", type=Path, required=True,
                             help="Minder Memory base directory")
        if repo:
            sub.add_argument("--repo", type=Path, required=True, help="repository root")
        if role:
            sub.add_argument("--role", required=True, help="role id")
        if now:
            sub.add_argument("--now", default=None, help="ISO-8601 instant to judge by")
        sub.set_defaults(handler=handler)
        return sub

    add("base", cmd_base, base=False)
    add("secrets-open", cmd_secrets_open, repo=False)
    add("secrets-close", cmd_secrets_close, repo=False)
    add("due", cmd_due, now=True)
    add("context", cmd_context, role=True, now=True)
    add("tick-begin", cmd_tick_begin)
    add("role-begin", cmd_role_begin, role=True)
    add("check", cmd_check, role=True)

    log = add("log", cmd_log, repo=False, role=True)
    log.add_argument("--outcome", required=True, choices=roles_log.OUTCOMES)
    log.add_argument("--ms", type=int, required=True, help="wall-clock of the run")
    log.add_argument("--writes", type=int, default=0, help="in-zone paths touched")
    log.add_argument("--note", default=None, help="short reason, or nothing")
    log.add_argument("--ts", dest="ts", default=None, help="ISO-8601 run timestamp")
    log.add_argument("--reverted", default=None,
                     help="JSON list of out-of-zone paths reverted by check")
    log.add_argument("--reported-only", dest="reported_only", default=None,
                     help="JSON list of paths left alone because they held owner work")

    validate = add("validate", cmd_validate)
    validate.add_argument("--role", default=None, help="limit to one role")
    return parser


def main(argv: list | None = None) -> int:
    # Owner text is not ASCII; std streams must not use the platform default.
    configure_std_streams()
    args = _build_parser().parse_args(argv)
    try:
        # The one place a path from the command line becomes a real path,
        # before any verb sees it. `--base .` is the engine's house
        # convention elsewhere, and unresolved it leaves `base.name` empty:
        # the state sugar expands to a prefix matching nothing and every
        # write a role makes to its own memory is reverted, silently.
        if getattr(args, "base", None) is not None:
            args.base = roles_config.resolve_base(args.base)
        if getattr(args, "repo", None) is not None:
            args.repo = args.repo.resolve()
        return args.handler(args)
    except (UsageError, roles_config.RoleConfigError, roles_cadence.CadenceError,
            roles_secrets.SecretError, roles_guard.SnapshotError,
            OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
