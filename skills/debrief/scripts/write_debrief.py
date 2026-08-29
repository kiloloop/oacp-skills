#!/usr/bin/env python3
"""Publish a session debrief into the OACP org-memory debrief store.

Implements the writer contract in the OACP protocol spec
(``docs/protocol/org_memory.md`` -> "Debrief Store"). The kernel owns the
layout and schema and validates *setup* only; everything below -- schema
completeness, the content hash, and failure-atomic publication -- is the
writer's responsibility.

Canonical path::

    <oacp-dir>/org-memory/debriefs/<project>/<YYYY>/<MM>/<YYYYMMDD>-<agent>-<session>.md

Publication is failure-atomic: the canonical path only ever holds a
complete, verified record, never partial bytes. The record is staged in a
writer-owned private file, verified through the descriptor that created it,
then published with an atomic no-replace primitive (``os.link``). A failure
before publication leaves the canonical namespace clean.

Staging ownership is a single invariant: **this writer only ever publishes an
inode it created itself.** The staging nonce is unpredictable, the staging
file is created with ``O_CREAT|O_EXCL|O_NOFOLLOW``, its bytes are verified
through that same descriptor, and the published name is confirmed to resolve
to that same ``(st_dev, st_ino)``. A pre-existing path is never read, adopted,
or linked -- doing so would let an outside file become the canonical record
and stay mutable through the shared inode. Stale staging artifacts are swept
*after* the record is published, when no writer of it can still need one.

Exit codes:
    0  published (or idempotent re-publish of a byte-identical record)
    1  usage / validation error
    2  publication failure (collision, read-back mismatch, hostile target)
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import hashlib
import os
import re
import stat as stat_mod
import sys
from pathlib import Path
from typing import Dict, NamedTuple, Optional, Tuple

SCHEMA_VERSION = 1

# Mirrors the protocol's canonical agent-name rule; hyphens, dots,
# underscores and mixed case are all representable in the agent segment.
AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# The session identifier is the substring after the FINAL hyphen, so it must
# never contain one -- that is what keeps the three-part filename uniquely
# parseable for any valid agent name.
SESSION_RE = re.compile(r"^[a-z0-9]{1,32}$")

FRONTMATTER_DELIM = b"---\n"

# The leading dot keeps staging files outside the canonical namespace; the
# prefix is scoped to one canonical record, so every file matching it belongs
# to a writer of that exact record.
STAGE_PREFIX = ".stage."

REQUIRED_FRONTMATTER_ORDER = (
    "schema_version",
    "project",
    "agent",
    "runtime",
    "session",
    "started_utc",
    "ended_utc",
    "content_sha256",
    "immutable",
)

# A staging file can only vanish before publication if a concurrent writer of
# the identical record published and swept it, which normally means the
# canonical record is already there. Retry a bounded number of times to cover
# the window where the sweep beat the publish into visibility.
PUBLISH_ATTEMPTS = 3


class WriterError(Exception):
    """A validation or publication failure. Never leaves partial bytes."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


class _StageVanished(Exception):
    """Internal: the staging file disappeared before it could be published."""


class DebriefResult(NamedTuple):
    """Outcome of one debrief write."""

    path: Path
    status: str
    content_sha256: str
    record: bytes


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


# A control character in any identity field would break out of the frontmatter
# block it is serialized into and corrupt the path segment it names, so every
# identity value is screened for them before composition.
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

# Runtime family names follow the same shape as agent names.
RUNTIME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def valid_project_segment(name: str) -> bool:
    """Workspace project-name rule: no leading dot, no path separators.

    Control characters are rejected on top of the protocol rule: they cannot
    appear in a usable path segment, and a newline would inject extra lines
    into the frontmatter block the name is serialized into.
    """
    return (
        bool(name)
        and not name.startswith(".")
        and "/" not in name
        and "\\" not in name
        and not CONTROL_CHARS_RE.search(name)
    )


def parse_utc(label: str, value: str) -> dt.datetime:
    """Parse an ISO 8601 UTC timestamp that ends in ``Z``."""
    if not value.endswith("Z"):
        raise WriterError(f"{label} must be ISO 8601 UTC ending in 'Z': {value!r}", 1)
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise WriterError(f"{label} is not a valid UTC timestamp: {value!r} ({exc})", 1) from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def validate_identity(project: str, agent: str, runtime: str, session: str) -> None:
    if not valid_project_segment(project):
        raise WriterError(
            f"project {project!r} is not a valid workspace name "
            "(must not start with '.' or contain '/' or '\\')",
            1,
        )
    if not AGENT_RE.match(agent):
        raise WriterError(
            f"agent {agent!r} does not match the protocol agent-name rule "
            f"{AGENT_RE.pattern}",
            1,
        )
    if not SESSION_RE.match(session):
        raise WriterError(
            f"session {session!r} must be 1-32 lowercase letters/digits with no "
            "hyphens (the identifier is parsed as the substring after the final hyphen)",
            1,
        )
    if not RUNTIME_RE.match(runtime):
        raise WriterError(
            f"runtime {runtime!r} must match {RUNTIME_RE.pattern}", 1
        )


def validate_body(body: bytes) -> None:
    """The record is a Markdown file, so the body must be valid UTF-8.

    Checked before the store is touched: a record whose body cannot be decoded
    is unreadable to every consumer, and the post-publication read-back cannot
    catch it because it compares the file against the same bytes that composed
    it.
    """
    if not body:
        raise WriterError("refusing to publish a debrief with an empty body", 1)
    try:
        body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WriterError(
            f"debrief body is not valid UTF-8 at byte {exc.start}: {exc.reason}", 1
        ) from exc


# --------------------------------------------------------------------------
# record composition
# --------------------------------------------------------------------------


def content_sha256(body: bytes) -> str:
    """Lowercase-hex SHA-256 over the exact body bytes -- no normalization."""
    return hashlib.sha256(body).hexdigest()


def _yaml_scalar(value: object) -> str:
    """Serialize one frontmatter value.

    ``schema_version`` is an integer and ``immutable`` a boolean; every other
    field is a string, and strings are emitted in YAML single-quoted style
    unconditionally.

    Conditional quoting is not safe here. Identifiers the protocol grammar
    accepts -- ``true``, ``false``, ``null``, ``no``, ``on``, ``y`` -- are
    plain-scalar keywords that a YAML reader re-types to a bool or None,
    silently changing the record's identity, and leading indicators such as
    ``*`` or ``&`` produce a record no parser will read at all. Single-quoted
    style preserves any control-character-free string exactly, escaping an
    embedded quote by doubling it.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if not text or text != text.strip():
        raise WriterError(f"refusing to emit an untrimmed/empty frontmatter scalar: {text!r}")
    if CONTROL_CHARS_RE.search(text):
        # Defense in depth: identity fields are screened before composition, so
        # reaching here means a caller bypassed validation.
        raise WriterError(f"refusing to emit a frontmatter scalar with control characters: {text!r}")
    # YAML single-quoted style escapes an embedded quote by doubling it.
    return "'" + text.replace("'", "''") + "'"


def compose_record(
    *,
    project: str,
    agent: str,
    runtime: str,
    session: str,
    started_utc: str,
    ended_utc: str,
    body: bytes,
) -> bytes:
    """Build the full record: frontmatter block + verbatim body bytes."""
    fields: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "agent": agent,
        "runtime": runtime,
        "session": session,
        "started_utc": started_utc,
        "ended_utc": ended_utc,
        "content_sha256": content_sha256(body),
        "immutable": True,
    }
    lines = [f"{key}: {_yaml_scalar(fields[key])}" for key in REQUIRED_FRONTMATTER_ORDER]
    head = FRONTMATTER_DELIM + ("\n".join(lines) + "\n").encode("utf-8") + FRONTMATTER_DELIM
    record = head + body
    _assert_record_roundtrips(record, fields, body)
    return record


def _assert_record_roundtrips(record: bytes, fields: Dict[str, object], body: bytes) -> None:
    """Re-parse the composed record and assert it says what it was asked to say.

    Composition is the one step that can silently change a record's identity,
    and nothing downstream can catch it: ``oacp doctor`` never opens debrief
    files, and the post-publication read-back compares the stored file against
    these same composed bytes. So the writer closes the loop itself, here,
    before the store is touched.
    """
    parsed, parsed_body = split_record(record)
    if list(parsed) != list(REQUIRED_FRONTMATTER_ORDER):
        raise WriterError(
            "composed frontmatter does not carry exactly the required fields in "
            f"canonical order: {list(parsed)}"
        )
    for key, expected in fields.items():
        if isinstance(expected, bool):
            want = "true" if expected else "false"
        elif isinstance(expected, int):
            want = str(expected)
        else:
            want = str(expected)
        if parsed[key] != want:
            raise WriterError(
                f"composed frontmatter field {key!r} did not round-trip: "
                f"{parsed[key]!r} != {want!r}"
            )
    if parsed_body != body:
        raise WriterError("composed record body did not round-trip byte-for-byte")


def split_record(raw: bytes) -> Tuple[Dict[str, str], bytes]:
    """Split a stored record into (frontmatter mapping, body bytes).

    The body is every byte after the line that closes the frontmatter block --
    the second ``---`` line including its trailing newline -- exactly as
    stored. This is the definition the ``content_sha256`` field is computed
    over, so it must not normalize anything.
    """
    if not raw.startswith(FRONTMATTER_DELIM):
        raise WriterError("record does not begin with a '---' frontmatter delimiter")
    rest = raw[len(FRONTMATTER_DELIM):]
    end = rest.find(b"\n" + FRONTMATTER_DELIM)
    if end == -1:
        raise WriterError("record frontmatter block is not closed by a '---' line")
    head = rest[:end]
    body = rest[end + 1 + len(FRONTMATTER_DELIM):]

    frontmatter: Dict[str, str] = {}
    for line in head.decode("utf-8").splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            quote = value[0]
            value = value[1:-1]
            if quote == "'":
                # Undo YAML single-quoted escaping.
                value = value.replace("''", "'")
        frontmatter[key.strip()] = value
    return frontmatter, body


def canonical_name(started: dt.datetime, agent: str, session: str) -> str:
    return f"{started.strftime('%Y%m%d')}-{agent}-{session}.md"


def canonical_path(oacp_dir: Path, project: str, started: dt.datetime, agent: str, session: str) -> Path:
    return (
        oacp_dir
        / "org-memory"
        / "debriefs"
        / project
        / started.strftime("%Y")
        / started.strftime("%m")
        / canonical_name(started, agent, session)
    )


def staging_path(target: Path) -> Path:
    """Writer-unique private staging name for ``target``.

    The nonce is unpredictable, which is what makes the ownership invariant
    hold: no other process can pre-create the path this writer is about to
    claim, so the ``O_EXCL`` create below always produces a fresh inode that
    this writer alone has ever written to.
    """
    nonce = f"{os.getpid():x}{os.urandom(8).hex()}"
    return target.with_name(f"{STAGE_PREFIX}{target.name}.{nonce}")


# --------------------------------------------------------------------------
# publication
# --------------------------------------------------------------------------


def _pread_all(fd: int, size: int) -> bytes:
    chunks = []
    offset = 0
    while offset < size:
        chunk = os.pread(fd, size - offset, offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _identity(path: Path) -> Tuple[int, int]:
    """The (device, inode) pair naming one filesystem object, without following."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise WriterError(f"cannot inspect {path}: {exc}") from exc
    return (st.st_dev, st.st_ino)


def _unlink_quietly(path: Path) -> None:
    """Best-effort removal of a staging name. Never fatal, by design.

    Every call site is cleanup: an error path that is already raising the real
    failure, the ``finally`` that releases the staging name after publication,
    or the post-publication sweep. Re-raising from any of them would replace an
    accurate outcome with an incidental one -- a successful publish reported as
    a failure because the stage could not be removed.

    Suppressing the error is therefore correct, but it must not be the only
    thing standing between a failed unlink and a broken guarantee. It is not:
    a stage that survives the ``finally`` leaves the published inode with a
    second name, and the caller asserts ``st_nlink == 1`` immediately after,
    turning exactly that case into a reported failure. What is left over is a
    stray file, which the next publication of this record sweeps and
    ``oacp doctor`` reports.
    """
    try:
        os.unlink(path)
    except OSError:
        # Deliberate: see the docstring. Cleanup is never allowed to replace
        # the caller's real outcome, and the st_nlink == 1 assertion after
        # publication is what catches the case where this mattered.
        pass


def _read_publishable_target(target: Path) -> Optional[bytes]:
    """Return the existing canonical bytes, or None when the path is free.

    Never follows symlinks: a symlink or any non-regular file at the canonical
    path is a hard failure, not something to read through. The read is bound
    to the inode that was inspected -- a file swapped in between the inspection
    and the open is reported rather than silently accepted.
    """
    try:
        lst = os.lstat(target)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WriterError(f"cannot inspect canonical path {target}: {exc}") from exc

    if stat_mod.S_ISLNK(lst.st_mode):
        raise WriterError(
            f"canonical path {target} is a symlink; the debrief store holds regular "
            "files only and the writer must not follow links"
        )
    if not stat_mod.S_ISREG(lst.st_mode):
        raise WriterError(f"canonical path {target} exists and is not a regular file")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if getattr(exc, "errno", None) == errno.ELOOP:
            raise WriterError(
                f"canonical path {target} became a symlink while it was being read"
            ) from exc
        raise WriterError(f"cannot open canonical path {target}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat_mod.S_ISREG(st.st_mode):
            raise WriterError(f"canonical path {target} exists and is not a regular file")
        if (st.st_dev, st.st_ino) != (lst.st_dev, lst.st_ino):
            raise WriterError(
                f"canonical path {target} was replaced while it was being read"
            )
        return _pread_all(fd, st.st_size)
    finally:
        os.close(fd)


def _sweep_own_stages(target: Path, canonical: Optional[Tuple[int, int]] = None) -> None:
    """Remove staging artifacts for ``target`` left by writers of this record.

    Called only once the canonical record is published and verified. From that
    point no writer of this record can still need a staging file: every
    concurrent publisher is on the idempotent path, and one whose ``link()``
    finds its stage gone resolves against the canonical record instead. That
    ordering is what lets the sweep be unconditional without ever removing a
    file that is still about to be published from -- and it is what keeps a
    crashed run's partial stage from accumulating for ``oacp doctor`` to
    report.

    The staging prefix is scoped to exactly one canonical record, so a match is
    by construction another attempt at the record just published. Two kinds of
    match are removable, and only those two:

    - a **single-link** regular file owned by this euid -- an ordinary stale or
      partial stage;
    - a regular file owned by this euid that **shares** ``canonical``, the
      inode of the record itself. That is not another writer's file at all: it
      is an alias of the published record, left behind when the ``finally``
      unlink failed, and it keeps the "immutable" record writable under a
      second name. Removing it destroys nothing -- the canonical name still
      holds the inode -- and it is the only way the retry path can honestly
      report success.

    Anything else -- a symlink, a directory, a multi-link file that is *not*
    the record, another user's file -- is left in place. It was never this
    writer's to delete.
    """
    prefix = f"{STAGE_PREFIX}{target.name}."
    euid = os.geteuid()
    try:
        entries = os.listdir(target.parent)
    except OSError:
        # The record is already published and verified; the sweep is tidying
        # only. An unreadable directory leaves stray staging files for
        # `oacp doctor`, which is exactly what it reports.
        return
    for name in entries:
        if not name.startswith(prefix):
            continue
        candidate = target.parent / name
        try:
            st = os.lstat(candidate)
        except OSError:
            # Vanished under us, or unreadable. Either way it is not a file
            # this writer can prove it owns, so it is not one to remove.
            continue
        if not stat_mod.S_ISREG(st.st_mode) or st.st_uid != euid:
            continue
        is_record_alias = canonical is not None and (st.st_dev, st.st_ino) == canonical
        if st.st_nlink != 1 and not is_record_alias:
            continue
        _unlink_quietly(candidate)


def _stage(target: Path, record: bytes) -> Tuple[Path, Tuple[int, int]]:
    """Create, write and verify a staging file this writer owns outright.

    Returns ``(path, (st_dev, st_ino))``. The identity pair is what binds
    verification to publication: the caller confirms the canonical name lands
    on this exact inode, so the bytes that were checked here are provably the
    bytes that became the record.
    """
    stage = staging_path(target)
    # O_RDWR, not O_WRONLY: the staged bytes are read back through this same
    # descriptor, which is what binds the verification to the published inode.
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(stage, flags, 0o644)
    except OSError as exc:
        raise WriterError(f"cannot create staging file {stage}: {exc}") from exc

    try:
        written = os.write(fd, record)
        if written != len(record):
            raise WriterError(
                f"short write staging {stage}: {written} of {len(record)} bytes"
            )
        os.fsync(fd)

        st = os.fstat(fd)
        if not stat_mod.S_ISREG(st.st_mode):
            raise WriterError(f"staging file {stage} is not a regular file")
        if st.st_nlink != 1:
            raise WriterError(
                f"staging file {stage} has {st.st_nlink} links; it must be the only "
                "name for its inode or publication would share it with another path"
            )

        # Verify through the descriptor that created the file, never by
        # reopening the path: the bytes checked and the inode published are
        # then provably the same object.
        staged = _pread_all(fd, st.st_size)
        if len(staged) != len(record) or staged != record:
            raise WriterError(f"staged bytes at {stage} do not match the composed record")
        _, staged_body = split_record(staged)
        expected = split_record(record)[0]["content_sha256"]
        if content_sha256(staged_body) != expected:
            raise WriterError(f"staged content hash mismatch at {stage}")
        ident = (st.st_dev, st.st_ino)
    except BaseException:
        os.close(fd)
        _unlink_quietly(stage)
        raise
    os.close(fd)
    return stage, ident


def _collision_error(target: Path) -> WriterError:
    return WriterError(
        f"canonical path {target} already holds a different record; "
        "never replace a published debrief -- re-publish under a new "
        "session identifier instead"
    )


def _attempt_publish(target: Path, record: bytes) -> str:
    stage, ident = _stage(target, record)
    try:
        try:
            # Atomic no-replace publication. os.link fails if the target
            # exists, which is exactly the collision guard the contract wants;
            # a replacing rename would be forbidden here.
            os.link(stage, target)
        except FileExistsError:
            landed = _read_publishable_target(target)
            if landed == record:
                return "idempotent"
            raise _collision_error(target)
        except FileNotFoundError:
            # A concurrent writer published and swept this stage. Its record is
            # normally ours byte-for-byte; if the canonical path is not yet
            # visible, the caller retries.
            landed = _read_publishable_target(target)
            if landed == record:
                return "idempotent"
            if landed is not None:
                raise _collision_error(target)
            raise _StageVanished()
    finally:
        # The staging name is always released: on success the canonical path is
        # the surviving link, on failure the namespace is left clean.
        _unlink_quietly(stage)

    # The canonical name must resolve to the inode that was verified above --
    # not to some other file that appeared at that name in the meantime.
    try:
        landed_st = os.lstat(target)
    except OSError as exc:
        raise WriterError(f"cannot inspect published record {target}: {exc}") from exc
    if (landed_st.st_dev, landed_st.st_ino) != ident:
        raise WriterError(
            f"published record {target} does not resolve to the staged inode; "
            "the canonical name was taken by another file"
        )
    # Link count and read-back are proved in _finalize, which every successful
    # return -- published and idempotent alike -- passes through.
    return "published"


def _finalize(target: Path, record: bytes) -> None:
    """Sweep staging artifacts, then prove the landed record stands alone.

    Every successful return from :func:`publish` passes through here, published
    and idempotent alike. The idempotent path needs it just as much: a previous
    run can have landed the record and then failed to release its staging name,
    which leaves a second, writable name for the canonical inode. Finding the
    bytes already correct says nothing about that -- so the retry sweeps the
    alias and re-proves the invariant rather than reporting success on the
    strength of a byte comparison.

    If the alias cannot be removed, this raises. A retained publication failure
    is the honest outcome; "idempotent" while the record is still mutable
    through another path is not.
    """
    canonical = _identity(target)
    _sweep_own_stages(target, canonical)

    st = os.lstat(target)
    if (st.st_dev, st.st_ino) != canonical:
        raise WriterError(f"published record {target} was replaced during cleanup")
    if st.st_nlink != 1:
        raise WriterError(
            f"published record {target} still has {st.st_nlink} links; the staging "
            "name could not be released and the record is reachable -- and "
            "writable -- under another path"
        )

    landed = _read_publishable_target(target)
    if landed is None:
        raise WriterError(f"published record {target} disappeared before read-back")
    landed_fm, landed_body = split_record(landed)
    if content_sha256(landed_body) != landed_fm.get("content_sha256"):
        raise WriterError(
            f"read-back mismatch at {target}: body does not match content_sha256"
        )
    if landed != record:
        raise WriterError(f"read-back mismatch at {target}: bytes differ from the record")


def publish(target: Path, record: bytes) -> str:
    """Publish ``record`` at ``target``. Returns 'published' or 'idempotent'.

    Failure-atomic: on any error before publication the canonical path is left
    absent and the staging file is removed.
    """
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_publishable_target(target)
    if existing is not None:
        if existing != record:
            raise _collision_error(target)
        # Idempotent retry after a success: nothing to write, but the previous
        # run's invariants still have to hold before this one calls it success.
        _finalize(target, record)
        return "idempotent"

    for attempt in range(PUBLISH_ATTEMPTS):
        try:
            status = _attempt_publish(target, record)
        except _StageVanished:
            if attempt == PUBLISH_ATTEMPTS - 1:
                raise WriterError(
                    f"staging file for {target} was removed before publication on "
                    f"{PUBLISH_ATTEMPTS} consecutive attempts"
                )
            continue
        _finalize(target, record)
        return status
    raise AssertionError("unreachable")  # pragma: no cover


def write_debrief(
    *,
    oacp_dir: Path,
    project: str,
    agent: str,
    runtime: str,
    session: str,
    started_utc: str,
    ended_utc: str,
    body: bytes,
    dry_run: bool = False,
) -> DebriefResult:
    """Validate, compose and publish one debrief.

    With ``dry_run`` the record is validated and composed exactly as it would
    be published, and the store is not touched -- no directories created, no
    files written. The status is then ``dry-run``.
    """
    validate_identity(project, agent, runtime, session)
    started = parse_utc("started_utc", started_utc)
    ended = parse_utc("ended_utc", ended_utc)
    if ended < started:
        raise WriterError(
            f"ended_utc ({ended_utc}) is before started_utc ({started_utc})", 1
        )
    validate_body(body)

    record = compose_record(
        project=project,
        agent=agent,
        runtime=runtime,
        session=session,
        started_utc=started_utc,
        ended_utc=ended_utc,
        body=body,
    )
    target = canonical_path(oacp_dir, project, started, agent, session)
    digest = content_sha256(body)
    if dry_run:
        return DebriefResult(target, "dry-run", digest, record)
    status = publish(target, record)
    return DebriefResult(target, status, digest, record)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def default_oacp_dir() -> Path:
    """Match the OACP CLI's documented fallback: $OACP_HOME, else ~/oacp."""
    env = os.environ.get("OACP_HOME")
    return Path(env).expanduser() if env else Path.home() / "oacp"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="write_debrief.py",
        description="Publish a session debrief into the OACP org-memory debrief store.",
    )
    parser.add_argument("--project", required=True, help="Workspace project name")
    parser.add_argument("--agent", required=True, help="Writing agent name")
    parser.add_argument("--runtime", required=True, help="Runtime family (claude, codex, ...)")
    parser.add_argument(
        "--session",
        required=True,
        help="Short session id: 1-32 lowercase alphanumerics, no hyphens",
    )
    parser.add_argument("--started-utc", required=True, help="Session start, ISO 8601 UTC (Z)")
    parser.add_argument("--ended-utc", required=True, help="Session end, ISO 8601 UTC (Z)")
    parser.add_argument(
        "--body-file",
        required=True,
        help="Path to the debrief body in Markdown, or '-' to read stdin",
    )
    parser.add_argument(
        "--oacp-dir",
        default=None,
        help="OACP home directory (default: $OACP_HOME, else ~/oacp)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and compose the record, print it, and write nothing",
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable result")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    oacp_dir = Path(args.oacp_dir).expanduser() if args.oacp_dir else default_oacp_dir()

    try:
        if args.body_file == "-":
            body = sys.stdin.buffer.read()
        else:
            body = Path(args.body_file).expanduser().read_bytes()
    except OSError as exc:
        print(f"ERROR: cannot read body: {exc}", file=sys.stderr)
        return 1

    try:
        result = write_debrief(
            oacp_dir=oacp_dir,
            project=args.project,
            agent=args.agent,
            runtime=args.runtime,
            session=args.session,
            started_utc=args.started_utc,
            ended_utc=args.ended_utc,
            body=body,
            dry_run=args.dry_run,
        )
    except WriterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"ERROR: publication failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        import json

        print(json.dumps({
            "path": str(result.path),
            "status": result.status,
            "content_sha256": result.content_sha256,
            "schema_version": SCHEMA_VERSION,
        }, indent=2))
    else:
        print(f"{result.status}: {result.path}")
        print(f"content_sha256: {result.content_sha256}")

    if args.dry_run:
        print("--- record preview (nothing was written) ---", file=sys.stderr)
        sys.stderr.buffer.write(result.record)
        sys.stderr.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
