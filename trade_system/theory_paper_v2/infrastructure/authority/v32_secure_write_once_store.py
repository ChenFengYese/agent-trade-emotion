"""Race-safe, write-once filesystem primitives for V3.2 qualification.

Every path component is opened relative to an already-open parent directory
with ``O_DIRECTORY | O_NOFOLLOW``.  Publication and readback use that same
anchored parent descriptor, so swapping a lexical parent for a symlink cannot
redirect bytes into another qualification or the frozen failed runtime.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import threading
from typing import Any, Callable, Iterator, Mapping
import uuid

from ...application.v31_authority_freeze import document_binding
from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
    verify_self_digest,
)
from ...v32_durable_json import rename_directory_noreplace_at


class V32SecureWriteOnceStoreError(ValueError):
    """A V3.2 anchored filesystem operation failed closed."""


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_OPEN_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
_FILE_READ_FLAGS = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
_PROCESS_LOCK_REGISTRY_GUARD = threading.Lock()
_PROCESS_LOCK_REGISTRY: dict[tuple[str, str], threading.RLock] = {}


def _process_lock_for(root: Path, relative_ref: str) -> threading.RLock:
    key = (os.fspath(root), relative_ref)
    with _PROCESS_LOCK_REGISTRY_GUARD:
        return _PROCESS_LOCK_REGISTRY.setdefault(key, threading.RLock())


def _unlink_at_missing_ok(parent_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=parent_fd)
    except FileNotFoundError:
        pass


def _cleanup_preserving_primary(
    operations: list[tuple[str, Callable[[], None]]],
) -> None:
    primary = sys.exception()
    first_cleanup_error: BaseException | None = None
    first_label = ""
    for label, operation in operations:
        try:
            operation()
        except BaseException as exc:
            if first_cleanup_error is None:
                first_cleanup_error = exc
                first_label = label
    if first_cleanup_error is None:
        return
    if primary is not None:
        try:
            primary.add_note(
                f"V32_SECURE_CLEANUP_FAILURE:{first_label}:"
                f"{type(first_cleanup_error).__name__}"
            )
        except (AttributeError, TypeError):
            pass
        return
    raise first_cleanup_error


def _root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_PROJECT_ROOT_INVALID"
            )
        root = supplied.resolve(strict=True)
    except V32SecureWriteOnceStoreError:
        raise
    except (OSError, ValueError) as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PROJECT_ROOT_INVALID"
        )
    return root


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32SecureWriteOnceStoreError("V32_SECURE_STORE_PATH_INVALID")
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32SecureWriteOnceStoreError("V32_SECURE_STORE_PATH_INVALID")
    return value


def _require_secure_dirfd() -> None:
    if not _NOFOLLOW or not _DIRECTORY:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_DIRFD_UNAVAILABLE"
        )


def _open_parent(
    root: Path, relative_ref: str, *, create: bool
) -> tuple[int | None, str]:
    _require_secure_dirfd()
    parts = PurePosixPath(_relative(relative_ref)).parts
    descriptor: int | None = None
    try:
        descriptor = os.open(root, _DIRECTORY_OPEN_FLAGS)
        for part in parts[:-1]:
            try:
                next_descriptor = os.open(
                    part, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
                )
            except FileNotFoundError:
                if not create:
                    os.close(descriptor)
                    return None, parts[-1]
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                os.fsync(descriptor)
                next_descriptor = os.open(
                    part, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
                )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, parts[-1]
    except V32SecureWriteOnceStoreError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PARENT_INVALID"
        ) from exc


def _read_at(parent_fd: int, leaf: str, *, missing_ok: bool) -> bytes | None:
    descriptor: int | None = None
    try:
        descriptor = os.open(leaf, _FILE_READ_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise V32SecureWriteOnceStoreError("V32_SECURE_STORE_FILE_REQUIRED")
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_FILE_INVALID"
        ) from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_FILE_REQUIRED"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def secure_ensure_directory(project_root: Path, relative_ref: str) -> None:
    """Create one directory chain without following a lexical component."""

    root = _root(project_root)
    relative = _relative(relative_ref)
    parent_fd, _ = _open_parent(
        root, f"{relative}/.v32-directory-anchor", create=True
    )
    if parent_fd is None:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PARENT_REQUIRED"
        )
    try:
        if not stat.S_ISDIR(os.fstat(parent_fd).st_mode):
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_PARENT_INVALID"
            )
    finally:
        os.close(parent_fd)


def _verify_open_lock_identity(
    root: Path,
    relative_ref: str,
    *,
    anchored_parent_fd: int,
    anchored_file_fd: int,
) -> None:
    reopened_parent_fd, leaf = _open_parent(root, relative_ref, create=False)
    if reopened_parent_fd is None:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_LOCK_IDENTITY_CHANGED"
        )
    reopened_file_fd = -1
    try:
        anchored_parent = os.fstat(anchored_parent_fd)
        reopened_parent = os.fstat(reopened_parent_fd)
        if (anchored_parent.st_dev, anchored_parent.st_ino) != (
            reopened_parent.st_dev,
            reopened_parent.st_ino,
        ):
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_LOCK_IDENTITY_CHANGED"
            )
        reopened_file_fd = os.open(
            leaf, _FILE_READ_FLAGS, dir_fd=reopened_parent_fd
        )
        anchored_file = os.fstat(anchored_file_fd)
        reopened_file = os.fstat(reopened_file_fd)
        if not stat.S_ISREG(reopened_file.st_mode) or (
            anchored_file.st_dev,
            anchored_file.st_ino,
        ) != (reopened_file.st_dev, reopened_file.st_ino):
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_LOCK_IDENTITY_CHANGED"
            )
        os.fsync(reopened_parent_fd)
    except V32SecureWriteOnceStoreError:
        raise
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_LOCK_IDENTITY_CHANGED"
        ) from exc
    finally:
        operations: list[tuple[str, Callable[[], None]]] = []
        if reopened_file_fd >= 0:
            operations.append(
                ("VERIFY_LOCK_FILE_CLOSE", lambda: os.close(reopened_file_fd))
            )
        operations.append(
            ("VERIFY_LOCK_PARENT_CLOSE", lambda: os.close(reopened_parent_fd))
        )
        _cleanup_preserving_primary(operations)


@contextmanager
def _secure_exclusive_lock_file_anchored(
    project_root: Path, relative_ref: str
) -> Iterator[None]:
    """Acquire and post-acquisition verify one anchored qualification lock."""

    root = _root(project_root)
    parent_fd, leaf = _open_parent(root, relative_ref, create=True)
    if parent_fd is None:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PARENT_REQUIRED"
        )
    descriptor = -1
    locked = False
    try:
        descriptor = os.open(
            leaf,
            os.O_RDWR | os.O_CREAT | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_FILE_REQUIRED"
            )
        os.fsync(parent_fd)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        _verify_open_lock_identity(
            root,
            relative_ref,
            anchored_parent_fd=parent_fd,
            anchored_file_fd=descriptor,
        )
        yield
        _verify_open_lock_identity(
            root,
            relative_ref,
            anchored_parent_fd=parent_fd,
            anchored_file_fd=descriptor,
        )
    except V32SecureWriteOnceStoreError:
        raise
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_LOCK_INVALID"
        ) from exc
    finally:
        operations: list[tuple[str, Callable[[], None]]] = []
        if locked:
            operations.append(
                ("LOCK_UN", lambda: fcntl.flock(descriptor, fcntl.LOCK_UN))
            )
        if descriptor >= 0:
            operations.append(("LOCK_FD_CLOSE", lambda: os.close(descriptor)))
        operations.append(("LOCK_PARENT_CLOSE", lambda: os.close(parent_fd)))
        _cleanup_preserving_primary(operations)


@contextmanager
def secure_exclusive_lock_file(
    project_root: Path, relative_ref: str
) -> Iterator[None]:
    """Serialize threads, then hold one anchored cross-process lock."""

    root = _root(project_root)
    relative = _relative(relative_ref)
    with _process_lock_for(root, relative):
        with _secure_exclusive_lock_file_anchored(root, relative):
            yield


def secure_read_bytes(
    project_root: Path, relative_ref: str, *, missing_ok: bool = False
) -> bytes | None:
    root = _root(project_root)
    parent_fd, leaf = _open_parent(root, relative_ref, create=False)
    if parent_fd is None:
        if missing_ok:
            return None
        raise V32SecureWriteOnceStoreError("V32_SECURE_STORE_FILE_REQUIRED")
    try:
        return _read_at(parent_fd, leaf, missing_ok=missing_ok)
    finally:
        os.close(parent_fd)


def secure_load_json_document(
    project_root: Path, relative_ref: str
) -> dict[str, Any]:
    payload = secure_read_bytes(project_root, relative_ref)
    if payload is None:
        raise V32SecureWriteOnceStoreError("V32_SECURE_STORE_FILE_REQUIRED")
    try:
        return loads_json_strict(payload)
    except CanonicalContractError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_JSON_INVALID"
        ) from exc


def secure_preflight_write_once_json(
    project_root: Path,
    relative_ref: str,
    document: Mapping[str, Any],
) -> None:
    try:
        payload = canonical_bytes(document) + b"\n"
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_DOCUMENT_INVALID"
        ) from exc
    existing = secure_read_bytes(
        project_root, relative_ref, missing_ok=True
    )
    if existing is not None and existing != payload:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_WRITE_ONCE_CONFLICT"
        )


def secure_write_once_json(
    project_root: Path,
    relative_ref: str,
    document: Mapping[str, Any],
    *,
    digest_field: str,
    require_new: bool = False,
) -> dict[str, str]:
    """Publish canonical JSON through one anchored parent directory fd."""

    root = _root(project_root)
    relative = _relative(relative_ref)
    try:
        semantic = verify_self_digest(document, digest_field)
        payload = canonical_bytes(document) + b"\n"
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_DOCUMENT_INVALID"
        ) from exc
    expected_physical = hashlib.sha256(payload).hexdigest()
    parent_fd, leaf = _open_parent(root, relative, create=True)
    if parent_fd is None:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PARENT_REQUIRED"
        )
    try:
        existing = _read_at(parent_fd, leaf, missing_ok=True)
        if existing is not None:
            if require_new or existing != payload:
                raise V32SecureWriteOnceStoreError(
                    "V32_SECURE_STORE_WRITE_ONCE_CONFLICT"
                )
            os.fsync(parent_fd)
        else:
            temporary = f".{leaf}.{uuid.uuid4().hex}.tmp"
            descriptor: int | None = None
            try:
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | _NOFOLLOW
                    | _CLOEXEC,
                    0o600,
                    dir_fd=parent_fd,
                )
                with os.fdopen(descriptor, "wb", closefd=True) as handle:
                    descriptor = None
                    written = handle.write(payload)
                    if written != len(payload):
                        raise OSError("V32_SECURE_STORE_SHORT_WRITE")
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(
                        temporary,
                        leaf,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    raced = _read_at(parent_fd, leaf, missing_ok=False)
                    if require_new or raced != payload:
                        raise V32SecureWriteOnceStoreError(
                            "V32_SECURE_STORE_WRITE_ONCE_CONFLICT"
                        )
            finally:
                operations: list[tuple[str, Callable[[], None]]] = []
                if descriptor is not None:
                    operations.append(
                        ("WRITE_ONCE_TEMP_FD_CLOSE", lambda: os.close(descriptor))
                    )
                operations.append(
                    (
                        "WRITE_ONCE_TEMP_UNLINK",
                        lambda: _unlink_at_missing_ok(parent_fd, temporary),
                    )
                )
                _cleanup_preserving_primary(operations)
            os.fsync(parent_fd)
        readback = _read_at(parent_fd, leaf, missing_ok=False)
    except V32SecureWriteOnceStoreError:
        raise
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PUBLICATION_FAILED"
        ) from exc
    finally:
        _cleanup_preserving_primary(
            [("WRITE_ONCE_PARENT_CLOSE", lambda: os.close(parent_fd))]
        )
    if readback != payload:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_READBACK_DRIFT"
        )
    # Re-open from the project root after publication.  The anchored write
    # prevents redirection; this second traversal makes a concurrent lexical
    # parent swap visible to the caller instead of returning a stale binding.
    lexical_readback = secure_read_bytes(root, relative)
    if lexical_readback != payload:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_READBACK_DRIFT"
        )
    try:
        loaded = loads_json_strict(readback)
        if verify_self_digest(loaded, digest_field) != semantic or loaded != dict(
            document
        ):
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_READBACK_DRIFT"
            )
        binding = document_binding(
            path=relative, document=document, digest_field=digest_field
        )
    except V32SecureWriteOnceStoreError:
        raise
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_READBACK_DRIFT"
        ) from exc
    return {**binding, "physical_sha256": expected_physical}


def secure_binding_for_existing_document(
    project_root: Path, relative_ref: str, *, digest_field: str
) -> dict[str, str]:
    payload = secure_read_bytes(project_root, relative_ref)
    if payload is None:
        raise V32SecureWriteOnceStoreError("V32_SECURE_STORE_FILE_REQUIRED")
    try:
        document = loads_json_strict(payload)
        semantic = verify_self_digest(document, digest_field)
        binding = document_binding(
            path=_relative(relative_ref),
            document=document,
            digest_field=digest_field,
        )
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_EXISTING_DOCUMENT_INVALID"
        ) from exc
    if semantic != binding["semantic_digest"]:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_EXISTING_DOCUMENT_INVALID"
        )
    return {**binding, "physical_sha256": hashlib.sha256(payload).hexdigest()}


def _open_directory_at(parent_fd: int, name: str) -> int:
    try:
        return os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_INVALID"
        ) from exc


def _ensure_relative_directory(base_fd: int, parts: tuple[str, ...]) -> int:
    descriptor = os.dup(base_fd)
    try:
        for part in parts:
            try:
                next_descriptor = os.open(
                    part, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
                )
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                os.fsync(descriptor)
                next_descriptor = os.open(
                    part, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
                )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _write_new_payload_at(parent_fd: int, leaf: str, payload: bytes) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            leaf,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            written = handle.write(payload)
            if written != len(payload):
                raise OSError("V32_SECURE_STORE_BUNDLE_SHORT_WRITE")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_WRITE_FAILED"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _scan_bundle(directory_fd: int) -> tuple[dict[str, bytes], set[str]]:
    files: dict[str, bytes] = {}
    directories: set[str] = set()

    def visit(current_fd: int, prefix: str) -> None:
        try:
            names = os.listdir(current_fd)
        except OSError as exc:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_INVALID"
            ) from exc
        for name in names:
            relative = f"{prefix}/{name}" if prefix else name
            try:
                mode = os.stat(
                    name, dir_fd=current_fd, follow_symlinks=False
                ).st_mode
            except OSError as exc:
                raise V32SecureWriteOnceStoreError(
                    "V32_SECURE_STORE_BUNDLE_INVALID"
                ) from exc
            if stat.S_ISDIR(mode):
                directories.add(relative)
                child_fd = _open_directory_at(current_fd, name)
                try:
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(mode):
                payload = _read_at(current_fd, name, missing_ok=False)
                if payload is None:
                    raise V32SecureWriteOnceStoreError(
                        "V32_SECURE_STORE_BUNDLE_INVALID"
                    )
                files[relative] = payload
            else:
                raise V32SecureWriteOnceStoreError(
                    "V32_SECURE_STORE_BUNDLE_INVALID"
                )

    visit(directory_fd, "")
    return files, directories


def _verify_bundle(
    directory_fd: int,
    *,
    expected_files: Mapping[str, bytes],
    expected_directories: set[str],
) -> None:
    files, directories = _scan_bundle(directory_fd)
    if files != dict(expected_files) or directories != expected_directories:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_CONFLICT"
        )


def _remove_directory_tree_at(
    parent_fd: int,
    name: str,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    try:
        directory_fd = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        return
    opened = os.fstat(directory_fd)
    opened_identity = (opened.st_dev, opened.st_ino)
    if expected_identity is not None and opened_identity != expected_identity:
        os.close(directory_fd)
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_STAGE_IDENTITY_CHANGED"
        )
    try:
        for child in os.listdir(directory_fd):
            mode = os.stat(
                child, dir_fd=directory_fd, follow_symlinks=False
            ).st_mode
            if stat.S_ISDIR(mode):
                _remove_directory_tree_at(directory_fd, child)
            else:
                os.unlink(child, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    verification_fd = _open_directory_at(parent_fd, name)
    try:
        verified = os.fstat(verification_fd)
        if (verified.st_dev, verified.st_ino) != opened_identity:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_STAGE_IDENTITY_CHANGED"
            )
    finally:
        os.close(verification_fd)
    os.rmdir(name, dir_fd=parent_fd)


def _discover_recoverable_bundle_stage(
    parent_fd: int,
    *,
    leaf: str,
    expected_files: Mapping[str, bytes],
    expected_directories: set[str],
) -> tuple[str, tuple[int, int]] | None:
    """Return one exact recoverable stage or discard one safe stale stage.

    A stage name is controller-owned only when it has the exact UUID-hex shape
    emitted below.  Multiple candidates, a non-directory candidate, an unsafe
    object inside the directory, or any identity drift remain fail-closed.  A
    directory whose complete anchored scan is merely partial or byte-different
    is safe to remove and rebuild because it has never crossed the final-name
    publication boundary.
    """

    prefix = f".{leaf}-stage-"
    try:
        candidates = sorted(
            name for name in os.listdir(parent_fd) if name.startswith(prefix)
        )
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_STAGE_UNSAFE"
        ) from exc
    if not candidates:
        return None
    if len(candidates) != 1:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_STAGE_AMBIGUOUS"
        )
    candidate = candidates[0]
    suffix = candidate[len(prefix) :]
    if len(suffix) != 32 or any(
        character not in "0123456789abcdef" for character in suffix
    ):
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_STAGE_UNSAFE"
        )
    try:
        candidate_stat = os.stat(
            candidate, dir_fd=parent_fd, follow_symlinks=False
        )
    except OSError as exc:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_STAGE_UNSAFE"
        ) from exc
    if not stat.S_ISDIR(candidate_stat.st_mode):
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_STAGE_UNSAFE"
        )
    candidate_fd = _open_directory_at(parent_fd, candidate)
    identity = (candidate_stat.st_dev, candidate_stat.st_ino)
    exact = False
    try:
        opened = os.fstat(candidate_fd)
        if (opened.st_dev, opened.st_ino) != identity:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_STAGE_IDENTITY_CHANGED"
            )
        try:
            _verify_bundle(
                candidate_fd,
                expected_files=expected_files,
                expected_directories=expected_directories,
            )
            os.fsync(candidate_fd)
            exact = True
        except V32SecureWriteOnceStoreError as exc:
            if str(exc) != "V32_SECURE_STORE_BUNDLE_CONFLICT":
                raise
    finally:
        os.close(candidate_fd)
    if exact:
        return candidate, identity
    _remove_directory_tree_at(
        parent_fd,
        candidate,
        expected_identity=identity,
    )
    os.fsync(parent_fd)
    return None


def _adopt_recoverable_bundle_stage(
    parent_fd: int,
    *,
    candidate: str,
    candidate_identity: tuple[int, int],
    leaf: str,
    expected_files: Mapping[str, bytes],
    expected_directories: set[str],
) -> None:
    """Publish one already complete stage and prove the same inode won."""

    candidate_fd = _open_directory_at(parent_fd, candidate)
    try:
        reopened = os.fstat(candidate_fd)
        if (reopened.st_dev, reopened.st_ino) != candidate_identity:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_STAGE_IDENTITY_CHANGED"
            )
        _verify_bundle(
            candidate_fd,
            expected_files=expected_files,
            expected_directories=expected_directories,
        )
        os.fsync(candidate_fd)
        try:
            rename_directory_noreplace_at(
                source_parent_fd=parent_fd,
                source_name=candidate,
                destination_parent_fd=parent_fd,
                destination_name=leaf,
            )
        except FileExistsError:
            # A non-cooperating writer won the final name.  Exclusive rename
            # guarantees that its directory was not replaced; only an exact
            # complete winner is replayable.
            final_fd = _open_directory_at(parent_fd, leaf)
            try:
                _verify_bundle(
                    final_fd,
                    expected_files=expected_files,
                    expected_directories=expected_directories,
                )
                os.fsync(final_fd)
            finally:
                os.close(final_fd)
            _remove_directory_tree_at(
                parent_fd,
                candidate,
                expected_identity=candidate_identity,
            )
            os.fsync(parent_fd)
            return
        except CanonicalContractError as exc:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_WRITE_FAILED"
            ) from exc

        final_fd = _open_directory_at(parent_fd, leaf)
        try:
            published = os.fstat(final_fd)
            if (published.st_dev, published.st_ino) != candidate_identity:
                raise V32SecureWriteOnceStoreError(
                    "V32_SECURE_STORE_BUNDLE_STAGE_IDENTITY_CHANGED"
                )
            _verify_bundle(
                final_fd,
                expected_files=expected_files,
                expected_directories=expected_directories,
            )
            os.fsync(final_fd)
        finally:
            os.close(final_fd)
        os.fsync(parent_fd)
    finally:
        os.close(candidate_fd)


def _secure_publish_json_directory_bundle_locked(
    project_root: Path,
    *,
    bundle_relative_ref: str,
    documents: list[Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    """Atomically publish one exact JSON directory bundle via renameat."""

    root = _root(project_root)
    bundle_ref = _relative(bundle_relative_ref)
    bundle_path = PurePosixPath(bundle_ref)
    if not documents:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_INVALID"
        )
    prepared: dict[str, dict[str, Any]] = {}
    expected_directories: set[str] = set()
    for item in documents:
        if not isinstance(item, Mapping) or set(item) != {
            "relative_ref",
            "document",
            "schema_id",
            "digest_field",
        }:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_INVALID"
            )
        relative_ref = _relative(item["relative_ref"])
        try:
            inside = PurePosixPath(relative_ref).relative_to(bundle_path)
        except ValueError as exc:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_INVALID"
            ) from exc
        if not inside.parts or inside.as_posix() == "." or relative_ref in prepared:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_INVALID"
            )
        document = item["document"]
        schema_id = item["schema_id"]
        digest_field = item["digest_field"]
        if (
            not isinstance(document, Mapping)
            or document.get("schema_id") != schema_id
            or not isinstance(schema_id, str)
            or not isinstance(digest_field, str)
        ):
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_INVALID"
            )
        try:
            semantic = verify_self_digest(document, digest_field)
            payload = canonical_bytes(document) + b"\n"
            binding = document_binding(
                path=relative_ref,
                document=document,
                digest_field=digest_field,
            )
        except (CanonicalContractError, TypeError, ValueError) as exc:
            raise V32SecureWriteOnceStoreError(
                "V32_SECURE_STORE_BUNDLE_INVALID"
            ) from exc
        parent_parts = inside.parts[:-1]
        for index in range(1, len(parent_parts) + 1):
            expected_directories.add(
                PurePosixPath(*parent_parts[:index]).as_posix()
            )
        prepared[relative_ref] = {
            "inside": inside.as_posix(),
            "payload": payload,
            "binding": {
                **binding,
                "semantic_digest": semantic,
                "physical_sha256": hashlib.sha256(payload).hexdigest(),
            },
        }

    parent_fd, leaf = _open_parent(root, bundle_ref, create=True)
    if parent_fd is None:
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_PARENT_REQUIRED"
        )
    stage = f".{leaf}-stage-{uuid.uuid4().hex}"
    expected_files = {
        row["inside"]: row["payload"] for row in prepared.values()
    }
    try:
        recoverable_stage = _discover_recoverable_bundle_stage(
            parent_fd,
            leaf=leaf,
            expected_files=expected_files,
            expected_directories=expected_directories,
        )
        try:
            final_fd = os.open(leaf, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            final_fd = None
        if final_fd is not None:
            try:
                _verify_bundle(
                    final_fd,
                    expected_files=expected_files,
                    expected_directories=expected_directories,
                )
                os.fsync(final_fd)
            finally:
                os.close(final_fd)
            if recoverable_stage is not None:
                candidate, candidate_identity = recoverable_stage
                _remove_directory_tree_at(
                    parent_fd,
                    candidate,
                    expected_identity=candidate_identity,
                )
            os.fsync(parent_fd)
        elif recoverable_stage is not None:
            candidate, candidate_identity = recoverable_stage
            _adopt_recoverable_bundle_stage(
                parent_fd,
                candidate=candidate,
                candidate_identity=candidate_identity,
                leaf=leaf,
                expected_files=expected_files,
                expected_directories=expected_directories,
            )
        else:
            os.mkdir(stage, mode=0o700, dir_fd=parent_fd)
            stage_fd = _open_directory_at(parent_fd, stage)
            try:
                for row in prepared.values():
                    inside = PurePosixPath(row["inside"])
                    file_parent_fd = _ensure_relative_directory(
                        stage_fd, inside.parts[:-1]
                    )
                    try:
                        _write_new_payload_at(
                            file_parent_fd, inside.parts[-1], row["payload"]
                        )
                        os.fsync(file_parent_fd)
                    finally:
                        os.close(file_parent_fd)
                _verify_bundle(
                    stage_fd,
                    expected_files=expected_files,
                    expected_directories=expected_directories,
                )
                os.fsync(stage_fd)
            finally:
                os.close(stage_fd)
            stage_stat = os.stat(stage, dir_fd=parent_fd, follow_symlinks=False)
            stage_identity = (stage_stat.st_dev, stage_stat.st_ino)
            try:
                rename_directory_noreplace_at(
                    source_parent_fd=parent_fd,
                    source_name=stage,
                    destination_parent_fd=parent_fd,
                    destination_name=leaf,
                )
            except FileExistsError:
                raced_fd = _open_directory_at(parent_fd, leaf)
                try:
                    _verify_bundle(
                        raced_fd,
                        expected_files=expected_files,
                        expected_directories=expected_directories,
                    )
                    os.fsync(raced_fd)
                finally:
                    os.close(raced_fd)
                _remove_directory_tree_at(
                    parent_fd,
                    stage,
                    expected_identity=stage_identity,
                )
            except CanonicalContractError as exc:
                raise V32SecureWriteOnceStoreError(
                    "V32_SECURE_STORE_BUNDLE_WRITE_FAILED"
                ) from exc
            else:
                published_fd = _open_directory_at(parent_fd, leaf)
                try:
                    published = os.fstat(published_fd)
                    if (published.st_dev, published.st_ino) != stage_identity:
                        raise V32SecureWriteOnceStoreError(
                            "V32_SECURE_STORE_BUNDLE_STAGE_IDENTITY_CHANGED"
                        )
                    _verify_bundle(
                        published_fd,
                        expected_files=expected_files,
                        expected_directories=expected_directories,
                    )
                    os.fsync(published_fd)
                finally:
                    os.close(published_fd)
            os.fsync(parent_fd)
        for relative_ref, row in prepared.items():
            if secure_read_bytes(root, relative_ref) != row["payload"]:
                raise V32SecureWriteOnceStoreError(
                    "V32_SECURE_STORE_BUNDLE_READBACK_DRIFT"
                )
    except V32SecureWriteOnceStoreError:
        _cleanup_preserving_primary(
            [
                (
                    "BUNDLE_STAGE_REMOVE",
                    lambda: _remove_directory_tree_at(parent_fd, stage),
                )
            ]
        )
        raise
    except OSError as exc:
        _cleanup_preserving_primary(
            [
                (
                    "BUNDLE_STAGE_REMOVE",
                    lambda: _remove_directory_tree_at(parent_fd, stage),
                )
            ]
        )
        raise V32SecureWriteOnceStoreError(
            "V32_SECURE_STORE_BUNDLE_WRITE_FAILED"
        ) from exc
    finally:
        _cleanup_preserving_primary(
            [("BUNDLE_PARENT_CLOSE", lambda: os.close(parent_fd))]
        )
    return {
        relative_ref: dict(row["binding"])
        for relative_ref, row in prepared.items()
    }


def secure_publish_json_directory_bundle(
    project_root: Path,
    *,
    bundle_relative_ref: str,
    documents: list[Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    """Serialize helper writers before the anchored directory publication."""

    root = _root(project_root)
    bundle_ref = _relative(bundle_relative_ref)
    bundle_path = PurePosixPath(bundle_ref)
    lock_name = f".{bundle_path.name}.v32-bundle-publish.lock"
    lock_ref = (
        lock_name
        if bundle_path.parent.as_posix() == "."
        else f"{bundle_path.parent.as_posix()}/{lock_name}"
    )
    with secure_exclusive_lock_file(root, lock_ref):
        return _secure_publish_json_directory_bundle_locked(
            root,
            bundle_relative_ref=bundle_ref,
            documents=documents,
        )


__all__ = [
    "V32SecureWriteOnceStoreError",
    "secure_binding_for_existing_document",
    "secure_ensure_directory",
    "secure_exclusive_lock_file",
    "secure_load_json_document",
    "secure_preflight_write_once_json",
    "secure_publish_json_directory_bundle",
    "secure_read_bytes",
    "secure_write_once_json",
]
