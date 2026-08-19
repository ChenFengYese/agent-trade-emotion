"""Crash-safe write-once JSON publication for the V3.2 runtime.

This V3.2-owned adapter intentionally leaves the V3.1-frozen canonical module
unchanged.  A complete, fsynced private file is linked into place without
replacement; every successful return also fsyncs the parent directory.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
import fcntl
import os
from pathlib import Path
import secrets
import stat
import sys
import threading
from typing import Any, Callable, Iterator, Mapping

from .domain.contracts.canonical import CanonicalContractError, canonical_bytes


_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_CREATE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_LOCK_OPEN_FLAGS = (
    os.O_RDWR
    | os.O_CREAT
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_DIRECTORY_IDENTITY_LOCK = threading.Lock()
_DIRECTORY_IDENTITIES: dict[tuple[int, int, str], tuple[int, int]] = {}
_PROCESS_LOCK_REGISTRY_GUARD = threading.Lock()
_PROCESS_LOCK_REGISTRY: dict[str, threading.RLock] = {}
_RENAME_EXCL = 0x00000004
_RENAMEATX_NP_LOCK = threading.Lock()
_RENAMEATX_NP: Any | None = None


def _process_lock_for(path: Path) -> threading.RLock:
    key = os.fspath(path)
    with _PROCESS_LOCK_REGISTRY_GUARD:
        return _PROCESS_LOCK_REGISTRY.setdefault(key, threading.RLock())


def _renameatx_np() -> Any:
    """Load Darwin's dirfd-relative exclusive rename or fail closed."""

    global _RENAMEATX_NP
    with _RENAMEATX_NP_LOCK:
        if _RENAMEATX_NP is not None:
            return _RENAMEATX_NP
        if sys.platform != "darwin":
            raise CanonicalContractError(
                "V32_DIRECTORY_NOREPLACE_RENAME_UNAVAILABLE"
            )
        try:
            function = ctypes.CDLL(None, use_errno=True).renameatx_np
        except (AttributeError, OSError) as exc:
            raise CanonicalContractError(
                "V32_DIRECTORY_NOREPLACE_RENAME_UNAVAILABLE"
            ) from exc
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        _RENAMEATX_NP = function
        return function


def rename_directory_noreplace_at(
    *,
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    """Atomically activate one directory only when the final name is absent.

    Ordinary POSIX ``rename`` may silently replace an existing empty directory.
    V3.2 directory bundles are write-once, so Darwin ``renameatx_np`` with
    ``RENAME_EXCL`` is mandatory.  An unavailable primitive fails closed; it
    must never fall back to replacement rename semantics.
    """

    if (
        not isinstance(source_name, str)
        or not source_name
        or source_name in {".", ".."}
        or os.path.sep in source_name
        or not isinstance(destination_name, str)
        or not destination_name
        or destination_name in {".", ".."}
        or os.path.sep in destination_name
    ):
        raise CanonicalContractError("V32_DIRECTORY_NOREPLACE_NAME_INVALID")
    function = _renameatx_np()
    ctypes.set_errno(0)
    result = function(
        source_parent_fd,
        os.fsencode(source_name),
        destination_parent_fd,
        os.fsencode(destination_name),
        _RENAME_EXCL,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            os.strerror(error_number),
            destination_name,
        )
    raise OSError(
        error_number or errno.EIO,
        os.strerror(error_number or errno.EIO),
        destination_name,
    )


def _unlink_at_missing_ok(parent_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=parent_fd)
    except FileNotFoundError:
        pass


def _rmdir_at_missing_ok(parent_fd: int, name: str) -> None:
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except FileNotFoundError:
        pass


def _cleanup_preserving_primary(
    operations: list[tuple[str, Callable[[], None]]],
) -> None:
    """Run every cleanup; never replace an already-active primary failure."""

    primary = sys.exception()
    first_cleanup_error: BaseException | None = None
    first_label = ""
    for label, operation in operations:
        try:
            operation()
        except BaseException as exc:  # Cleanup must continue through every fd.
            if first_cleanup_error is None:
                first_cleanup_error = exc
                first_label = label
    if first_cleanup_error is None:
        return
    if primary is not None:
        try:
            primary.add_note(
                f"V32_DURABLE_CLEANUP_FAILURE:{first_label}:"
                f"{type(first_cleanup_error).__name__}"
            )
        except (AttributeError, TypeError):
            pass
        return
    raise first_cleanup_error


def _absolute_lexical(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    # macOS exposes system temporary directories through root-owned aliases
    # such as /var -> /private/var.  Canonicalize only that first, root-owned
    # platform component; all lower components remain lexical and are opened
    # one-by-one with O_NOFOLLOW below.
    if len(absolute.parts) > 1:
        first = Path(os.path.sep) / absolute.parts[1]
        try:
            first_stat = first.lstat()
        except FileNotFoundError:
            first_stat = None
        if first_stat is not None and stat.S_ISLNK(first_stat.st_mode):
            if first_stat.st_uid != 0:
                raise CanonicalContractError(
                    f"WRITE_ONCE_ROOT_ALIAS_UNSAFE:{first}"
                )
            resolved = first.resolve(strict=True)
            absolute = resolved.joinpath(*absolute.parts[2:])
    return absolute


def _bind_and_sync_directory_entry(
    *, parent_fd: int, name: str, child_fd: int, absolute: Path
) -> None:
    parent_stat = os.fstat(parent_fd)
    child_stat = os.fstat(child_fd)
    key = (parent_stat.st_dev, parent_stat.st_ino, name)
    identity = (child_stat.st_dev, child_stat.st_ino)
    with _DIRECTORY_IDENTITY_LOCK:
        previous = _DIRECTORY_IDENTITIES.get(key)
        if previous is not None and previous != identity:
            raise CanonicalContractError(
                f"WRITE_ONCE_DIRECTORY_IDENTITY_CHANGED:{absolute}"
            )
        # Always sync the parent entry.  The same child inode can be renamed
        # away and back between calls, so identity equality alone is not proof
        # that the current directory entry has reached stable storage.
        os.fsync(parent_fd)
        if previous is None:
            _DIRECTORY_IDENTITIES[key] = identity


def _open_directory_fd(path: Path, *, create: bool) -> int:
    absolute = _absolute_lexical(path)
    descriptor = os.open(os.path.sep, _DIRECTORY_OPEN_FLAGS)
    try:
        for part in absolute.parts[1:]:
            try:
                child = os.open(
                    part,
                    _DIRECTORY_OPEN_FLAGS,
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    # A concurrent creator may win.  Fsync the observed parent
                    # before opening the winner through the same anchored fd.
                    pass
                try:
                    child = os.open(
                        part,
                        _DIRECTORY_OPEN_FLAGS,
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise CanonicalContractError(
                        f"WRITE_ONCE_DIRECTORY_UNSAFE:{absolute}"
                    ) from exc
            except OSError as exc:
                raise CanonicalContractError(
                    f"WRITE_ONCE_DIRECTORY_UNSAFE:{absolute}"
                ) from exc
            try:
                _bind_and_sync_directory_entry(
                    parent_fd=descriptor,
                    name=part,
                    child_fd=child,
                    absolute=absolute,
                )
            except BaseException:
                _cleanup_preserving_primary(
                    [("OPEN_DIRECTORY_CHILD_CLOSE", lambda: os.close(child))]
                )
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        _cleanup_preserving_primary(
            [("OPEN_DIRECTORY_FD_CLOSE", lambda: os.close(descriptor))]
        )
        raise


def _read_regular_file_at(parent_fd: int, name: str) -> bytes:
    try:
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise CanonicalContractError(
            f"WRITE_ONCE_TARGET_UNSAFE:{name}"
        ) from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CanonicalContractError(f"WRITE_ONCE_TARGET_NOT_REGULAR:{name}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _verify_lexical_publication(
    *, target: Path, anchored_parent_fd: int, payload: bytes
) -> None:
    """Reopen the lexical path and prove it still names the anchored winner."""

    reopened_parent_fd = _open_directory_fd(target.parent, create=False)
    try:
        anchored = os.fstat(anchored_parent_fd)
        reopened = os.fstat(reopened_parent_fd)
        if (anchored.st_dev, anchored.st_ino) != (
            reopened.st_dev,
            reopened.st_ino,
        ) or _read_regular_file_at(reopened_parent_fd, target.name) != payload:
            raise CanonicalContractError(
                f"WRITE_ONCE_POST_PUBLISH_VERIFY_FAILED:{target}"
            )
        os.fsync(reopened_parent_fd)
    except (OSError, CanonicalContractError) as exc:
        if isinstance(exc, CanonicalContractError) and str(exc).startswith(
            "WRITE_ONCE_POST_PUBLISH_VERIFY_FAILED:"
        ):
            raise
        raise CanonicalContractError(
            f"WRITE_ONCE_POST_PUBLISH_VERIFY_FAILED:{target}"
        ) from exc
    finally:
        _cleanup_preserving_primary(
            [
                (
                    "VERIFY_PUBLICATION_PARENT_CLOSE",
                    lambda: os.close(reopened_parent_fd),
                )
            ]
        )


def _verify_lexical_file_identity(
    *, target: Path, anchored_parent_fd: int, anchored_file_fd: int
) -> None:
    """Prove a lexical lock path still names the opened regular file."""

    reopened_parent_fd = _open_directory_fd(target.parent, create=False)
    reopened_file_fd = -1
    try:
        anchored_parent = os.fstat(anchored_parent_fd)
        reopened_parent = os.fstat(reopened_parent_fd)
        if (anchored_parent.st_dev, anchored_parent.st_ino) != (
            reopened_parent.st_dev,
            reopened_parent.st_ino,
        ):
            raise CanonicalContractError(
                f"V32_LOCK_POST_OPEN_VERIFY_FAILED:{target}"
            )
        reopened_file_fd = os.open(
            target.name,
            _FILE_READ_FLAGS,
            dir_fd=reopened_parent_fd,
        )
        anchored_file = os.fstat(anchored_file_fd)
        reopened_file = os.fstat(reopened_file_fd)
        if not stat.S_ISREG(anchored_file.st_mode) or not stat.S_ISREG(
            reopened_file.st_mode
        ) or (anchored_file.st_dev, anchored_file.st_ino) != (
            reopened_file.st_dev,
            reopened_file.st_ino,
        ):
            raise CanonicalContractError(
                f"V32_LOCK_POST_OPEN_VERIFY_FAILED:{target}"
            )
        os.fsync(reopened_parent_fd)
    except (OSError, CanonicalContractError) as exc:
        if isinstance(exc, CanonicalContractError) and str(exc).startswith(
            "V32_LOCK_POST_OPEN_VERIFY_FAILED:"
        ):
            raise
        raise CanonicalContractError(
            f"V32_LOCK_POST_OPEN_VERIFY_FAILED:{target}"
        ) from exc
    finally:
        operations = []
        if reopened_file_fd >= 0:
            operations.append(
                ("VERIFY_LOCK_FILE_CLOSE", lambda: os.close(reopened_file_fd))
            )
        operations.append(
            ("VERIFY_LOCK_PARENT_CLOSE", lambda: os.close(reopened_parent_fd))
        )
        _cleanup_preserving_primary(operations)


def _bundle_files(files: Mapping[str, bytes]) -> dict[str, bytes]:
    if not isinstance(files, Mapping) or not files:
        raise TypeError("V32_WRITE_ONCE_DIRECTORY_FILES_REQUIRED")
    result: dict[str, bytes] = {}
    for name, payload in files.items():
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or os.path.sep in name
            or (os.path.altsep is not None and os.path.altsep in name)
        ):
            raise CanonicalContractError(
                f"WRITE_ONCE_DIRECTORY_CHILD_INVALID:{name}"
            )
        if not isinstance(payload, bytes):
            raise TypeError("V32_WRITE_ONCE_DIRECTORY_BYTES_REQUIRED")
        result[name] = payload
    return result


def _verify_exact_directory_fd(
    descriptor: int, *, target: Path, files: Mapping[str, bytes]
) -> None:
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_TARGET_NOT_DIRECTORY:{target}"
        )
    try:
        actual_names = set(os.listdir(descriptor))
    except OSError as exc:
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_TARGET_UNSAFE:{target}"
        ) from exc
    if actual_names != set(files):
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_CONFLICT:{target}"
        )
    for name, payload in files.items():
        try:
            actual = _read_regular_file_at(descriptor, name)
        except (FileNotFoundError, CanonicalContractError) as exc:
            raise CanonicalContractError(
                f"WRITE_ONCE_DIRECTORY_CONFLICT:{target}"
            ) from exc
        if actual != payload:
            raise CanonicalContractError(
                f"WRITE_ONCE_DIRECTORY_CONFLICT:{target}"
            )
    os.fsync(descriptor)


def _open_exact_directory_at(
    parent_fd: int, *, target: Path, files: Mapping[str, bytes]
) -> int:
    try:
        descriptor = os.open(target.name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_TARGET_UNSAFE:{target}"
        ) from exc
    try:
        _verify_exact_directory_fd(descriptor, target=target, files=files)
        return descriptor
    except BaseException:
        _cleanup_preserving_primary(
            [("OPEN_EXACT_DIRECTORY_CLOSE", lambda: os.close(descriptor))]
        )
        raise


def _verify_lexical_directory_publication(
    *,
    target: Path,
    anchored_parent_fd: int,
    anchored_directory_fd: int,
    files: Mapping[str, bytes],
) -> None:
    reopened_parent_fd = _open_directory_fd(target.parent, create=False)
    reopened_directory_fd = -1
    try:
        anchored_parent = os.fstat(anchored_parent_fd)
        reopened_parent = os.fstat(reopened_parent_fd)
        if (anchored_parent.st_dev, anchored_parent.st_ino) != (
            reopened_parent.st_dev,
            reopened_parent.st_ino,
        ):
            raise CanonicalContractError(
                f"WRITE_ONCE_DIRECTORY_POST_PUBLISH_VERIFY_FAILED:{target}"
            )
        reopened_directory_fd = _open_exact_directory_at(
            reopened_parent_fd, target=target, files=files
        )
        anchored_directory = os.fstat(anchored_directory_fd)
        reopened_directory = os.fstat(reopened_directory_fd)
        if (anchored_directory.st_dev, anchored_directory.st_ino) != (
            reopened_directory.st_dev,
            reopened_directory.st_ino,
        ):
            raise CanonicalContractError(
                f"WRITE_ONCE_DIRECTORY_POST_PUBLISH_VERIFY_FAILED:{target}"
            )
        os.fsync(reopened_parent_fd)
    except (OSError, CanonicalContractError) as exc:
        if isinstance(exc, CanonicalContractError) and str(exc).startswith(
            "WRITE_ONCE_DIRECTORY_POST_PUBLISH_VERIFY_FAILED:"
        ):
            raise
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_POST_PUBLISH_VERIFY_FAILED:{target}"
        ) from exc
    finally:
        operations = []
        if reopened_directory_fd >= 0:
            operations.append(
                (
                    "VERIFY_DIRECTORY_CLOSE",
                    lambda: os.close(reopened_directory_fd),
                )
            )
        operations.append(
            (
                "VERIFY_DIRECTORY_PARENT_CLOSE",
                lambda: os.close(reopened_parent_fd),
            )
        )
        _cleanup_preserving_primary(operations)


def ensure_directory_tree(path: Path) -> None:
    """Create a durable directory chain without following symlink components."""

    descriptor = _open_directory_fd(Path(path), create=True)
    os.close(descriptor)


def confirm_existing_bytes(path: Path, expected: bytes) -> None:
    """Durably confirm exact existing bytes without creating the target."""

    if not isinstance(expected, bytes):
        raise TypeError("V32_CONFIRM_EXISTING_BYTES_REQUIRED")
    target = _absolute_lexical(Path(path))
    if target == target.parent or target.name in {"", ".", ".."}:
        raise CanonicalContractError(f"WRITE_ONCE_TARGET_INVALID:{target}")
    try:
        parent_fd = _open_directory_fd(target.parent, create=False)
    except FileNotFoundError as exc:
        raise CanonicalContractError(
            f"WRITE_ONCE_TARGET_MISSING:{target}"
        ) from exc
    try:
        try:
            actual = _read_regular_file_at(parent_fd, target.name)
        except FileNotFoundError as exc:
            raise CanonicalContractError(
                f"WRITE_ONCE_TARGET_MISSING:{target}"
            ) from exc
        if actual != expected:
            raise CanonicalContractError(f"WRITE_ONCE_CONFLICT:{target}")
        os.fsync(parent_fd)
        _verify_lexical_publication(
            target=target,
            anchored_parent_fd=parent_fd,
            payload=expected,
        )
    finally:
        _cleanup_preserving_primary(
            [("CONFIRM_PARENT_CLOSE", lambda: os.close(parent_fd))]
        )


def confirm_existing_json(path: Path, value: Mapping[str, Any]) -> None:
    """Durably confirm one canonical JSON document without creating it."""

    confirm_existing_bytes(path, canonical_bytes(dict(value)) + b"\n")


@contextmanager
def _exclusive_lock_file_anchored(path: Path) -> Iterator[None]:
    """Hold one nofollow regular-file lock and revalidate after acquisition."""

    target = _absolute_lexical(Path(path))
    if target == target.parent or target.name in {"", ".", ".."}:
        raise CanonicalContractError(f"V32_LOCK_TARGET_INVALID:{target}")
    ensure_directory_tree(target.parent)
    parent_fd = _open_directory_fd(target.parent, create=False)
    descriptor = -1
    locked = False
    try:
        try:
            descriptor = os.open(
                target.name,
                _LOCK_OPEN_FLAGS,
                0o600,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise CanonicalContractError(
                f"V32_LOCK_TARGET_UNSAFE:{target}"
            ) from exc
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CanonicalContractError(
                f"V32_LOCK_TARGET_NOT_REGULAR:{target}"
            )
        os.fsync(parent_fd)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        _verify_lexical_file_identity(
            target=target,
            anchored_parent_fd=parent_fd,
            anchored_file_fd=descriptor,
        )
        yield
        _verify_lexical_file_identity(
            target=target,
            anchored_parent_fd=parent_fd,
            anchored_file_fd=descriptor,
        )
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
def exclusive_lock_file(path: Path) -> Iterator[None]:
    """Serialize threads, then hold and revalidate one OS-level lock."""

    target = _absolute_lexical(Path(path))
    with _process_lock_for(target):
        with _exclusive_lock_file_anchored(target):
            yield


def atomic_replace_bytes(
    path: Path,
    payload: bytes,
    *,
    short_write_error: str = "V32_ATOMIC_REPLACE_SHORT_WRITE",
) -> None:
    """Crash-safe mutable publication anchored to one nofollow parent fd."""

    if not isinstance(payload, bytes):
        raise TypeError("V32_ATOMIC_REPLACE_BYTES_REQUIRED")
    target = _absolute_lexical(Path(path))
    if target == target.parent or target.name in {"", ".", ".."}:
        raise CanonicalContractError(f"V32_ATOMIC_REPLACE_TARGET_INVALID:{target}")
    ensure_directory_tree(target.parent)
    parent_fd = _open_directory_fd(target.parent, create=False)
    descriptor = -1
    temporary_name: str | None = None
    try:
        for _ in range(128):
            candidate = f".v32-atomic-replace-{secrets.token_hex(16)}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    _FILE_CREATE_FLAGS,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if descriptor < 0 or temporary_name is None:
            raise OSError("V32_ATOMIC_REPLACE_TEMP_NAME_EXHAUSTED")
        handle = os.fdopen(descriptor, "wb")
        descriptor = -1
        with handle:
            written = handle.write(payload)
            if written != len(payload):
                raise OSError(short_write_error)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = None
        os.fsync(parent_fd)
        _verify_lexical_publication(
            target=target,
            anchored_parent_fd=parent_fd,
            payload=payload,
        )
    finally:
        operations = []
        if descriptor >= 0:
            operations.append(("ATOMIC_TEMP_FD_CLOSE", lambda: os.close(descriptor)))
        if temporary_name is not None:
            operations.append(
                (
                    "ATOMIC_TEMP_UNLINK",
                    lambda: _unlink_at_missing_ok(parent_fd, temporary_name),
                )
            )
        operations.append(("ATOMIC_PARENT_CLOSE", lambda: os.close(parent_fd)))
        _cleanup_preserving_primary(operations)


def atomic_replace_json(
    path: Path,
    value: Mapping[str, Any],
    *,
    short_write_error: str = "V32_ATOMIC_REPLACE_SHORT_WRITE",
) -> None:
    """Crash-safe mutable canonical JSON publication."""

    atomic_replace_bytes(
        path,
        canonical_bytes(dict(value)) + b"\n",
        short_write_error=short_write_error,
    )


def confirm_existing_directory(path: Path, files: Mapping[str, bytes]) -> None:
    """Durably confirm one exact directory bundle without creating it."""

    expected = _bundle_files(files)
    target = _absolute_lexical(Path(path))
    if target == target.parent or target.name in {"", ".", ".."}:
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_TARGET_INVALID:{target}"
        )
    try:
        parent_fd = _open_directory_fd(target.parent, create=False)
    except FileNotFoundError as exc:
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_TARGET_MISSING:{target}"
        ) from exc
    directory_fd = -1
    try:
        try:
            directory_fd = _open_exact_directory_at(
                parent_fd, target=target, files=expected
            )
        except FileNotFoundError as exc:
            raise CanonicalContractError(
                f"WRITE_ONCE_DIRECTORY_TARGET_MISSING:{target}"
            ) from exc
        os.fsync(parent_fd)
        _verify_lexical_directory_publication(
            target=target,
            anchored_parent_fd=parent_fd,
            anchored_directory_fd=directory_fd,
            files=expected,
        )
    finally:
        operations = []
        if directory_fd >= 0:
            operations.append(
                ("CONFIRM_DIRECTORY_CLOSE", lambda: os.close(directory_fd))
            )
        operations.append(
            ("CONFIRM_DIRECTORY_PARENT_CLOSE", lambda: os.close(parent_fd))
        )
        _cleanup_preserving_primary(operations)


def _write_once_directory_locked(path: Path, files: Mapping[str, bytes]) -> str:
    """Atomically publish a finite exact directory bundle without path following."""

    expected = _bundle_files(files)
    target = _absolute_lexical(Path(path))
    if target == target.parent or target.name in {"", ".", ".."}:
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_TARGET_INVALID:{target}"
        )
    ensure_directory_tree(target.parent)
    parent_fd = _open_directory_fd(target.parent, create=False)
    temporary_name: str | None = None
    temporary_fd = -1
    published = False
    try:
        try:
            existing_fd = _open_exact_directory_at(
                parent_fd, target=target, files=expected
            )
        except FileNotFoundError:
            existing_fd = -1
        if existing_fd >= 0:
            try:
                os.fsync(parent_fd)
                _verify_lexical_directory_publication(
                    target=target,
                    anchored_parent_fd=parent_fd,
                    anchored_directory_fd=existing_fd,
                    files=expected,
                )
                return "EXISTING_IDENTICAL"
            finally:
                os.close(existing_fd)

        for _ in range(128):
            candidate = f".v32-write-once-directory-{secrets.token_hex(16)}.tmp"
            try:
                os.mkdir(candidate, mode=0o700, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temporary_name = candidate
            temporary_fd = os.open(
                candidate, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd
            )
            break
        if temporary_name is None or temporary_fd < 0:
            raise OSError("V32_WRITE_ONCE_DIRECTORY_TEMP_NAME_EXHAUSTED")

        for name in sorted(expected):
            child_fd = os.open(
                name,
                _FILE_CREATE_FLAGS,
                0o600,
                dir_fd=temporary_fd,
            )
            try:
                handle = os.fdopen(child_fd, "wb")
                child_fd = -1
                with handle:
                    written = handle.write(expected[name])
                    if written != len(expected[name]):
                        raise OSError(
                            f"V32_WRITE_ONCE_DIRECTORY_SHORT_WRITE:{name}"
                        )
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                if child_fd >= 0:
                    os.close(child_fd)
        os.fsync(temporary_fd)

        # Recheck immediately before rename.  Legitimate writers serialize on
        # the store lock; a concurrent identical winner is adopted exactly.
        try:
            existing_fd = _open_exact_directory_at(
                parent_fd, target=target, files=expected
            )
        except FileNotFoundError:
            existing_fd = -1
        if existing_fd >= 0:
            try:
                os.fsync(parent_fd)
                _verify_lexical_directory_publication(
                    target=target,
                    anchored_parent_fd=parent_fd,
                    anchored_directory_fd=existing_fd,
                    files=expected,
                )
                return "EXISTING_IDENTICAL"
            finally:
                os.close(existing_fd)

        try:
            rename_directory_noreplace_at(
                source_parent_fd=parent_fd,
                source_name=temporary_name,
                destination_parent_fd=parent_fd,
                destination_name=target.name,
            )
        except FileExistsError:
            try:
                existing_fd = _open_exact_directory_at(
                    parent_fd, target=target, files=expected
                )
            except (FileNotFoundError, CanonicalContractError) as conflict:
                raise CanonicalContractError(
                    f"WRITE_ONCE_DIRECTORY_CONFLICT:{target}"
                ) from conflict
            try:
                os.fsync(parent_fd)
                _verify_lexical_directory_publication(
                    target=target,
                    anchored_parent_fd=parent_fd,
                    anchored_directory_fd=existing_fd,
                    files=expected,
                )
                return "EXISTING_IDENTICAL"
            finally:
                os.close(existing_fd)
        published = True
        temporary_name = None
        os.fsync(parent_fd)
        _verify_lexical_directory_publication(
            target=target,
            anchored_parent_fd=parent_fd,
            anchored_directory_fd=temporary_fd,
            files=expected,
        )
        return "CREATED"
    finally:
        operations = []
        if temporary_fd >= 0 and not published and temporary_name is not None:
            for child_name in expected:
                operations.append(
                    (
                        f"DIRECTORY_TEMP_CHILD_UNLINK:{child_name}",
                        lambda child_name=child_name: _unlink_at_missing_ok(
                            temporary_fd, child_name
                        ),
                    )
                )
        if temporary_fd >= 0:
            operations.append(
                ("DIRECTORY_TEMP_FD_CLOSE", lambda: os.close(temporary_fd))
            )
        if not published and temporary_name is not None:
            operations.append(
                (
                    "DIRECTORY_TEMP_RMDIR",
                    lambda: _rmdir_at_missing_ok(parent_fd, temporary_name),
                )
            )
        operations.append(("DIRECTORY_PARENT_CLOSE", lambda: os.close(parent_fd)))
        _cleanup_preserving_primary(operations)


def write_once_directory(path: Path, files: Mapping[str, bytes]) -> str:
    """Serialize and atomically publish one exact write-once directory bundle."""

    expected = _bundle_files(files)
    target = _absolute_lexical(Path(path))
    if target == target.parent or target.name in {"", ".", ".."}:
        raise CanonicalContractError(
            f"WRITE_ONCE_DIRECTORY_TARGET_INVALID:{target}"
        )
    lock_path = target.parent / f".{target.name}.v32-directory-publish.lock"
    with exclusive_lock_file(lock_path):
        return _write_once_directory_locked(target, expected)


def write_once_bytes(path: Path, payload: bytes) -> str:
    """Publish arbitrary bytes once, or durably confirm an identical winner."""

    if not isinstance(payload, bytes):
        raise TypeError("V32_WRITE_ONCE_BYTES_REQUIRED")
    target = _absolute_lexical(Path(path))
    if target == target.parent or target.name in {"", ".", ".."}:
        raise CanonicalContractError(f"WRITE_ONCE_TARGET_INVALID:{target}")
    ensure_directory_tree(target.parent)
    parent_fd = _open_directory_fd(target.parent, create=False)
    descriptor = -1
    temporary_name: str | None = None
    try:
        try:
            existing = _read_regular_file_at(parent_fd, target.name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != payload:
                raise CanonicalContractError(f"WRITE_ONCE_CONFLICT:{target}")
            os.fsync(parent_fd)
            _verify_lexical_publication(
                target=target,
                anchored_parent_fd=parent_fd,
                payload=payload,
            )
            return "EXISTING_IDENTICAL"

        for _ in range(128):
            candidate = f".v32-write-once-{secrets.token_hex(16)}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    _FILE_CREATE_FLAGS,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if descriptor < 0 or temporary_name is None:
            raise OSError("V32_WRITE_ONCE_TEMP_NAME_EXHAUSTED")
        handle = os.fdopen(descriptor, "wb")
        descriptor = -1
        with handle:
            written = handle.write(payload)
            if written != len(payload):
                raise OSError("V32_WRITE_ONCE_SHORT_WRITE")
            handle.flush()
            os.fsync(handle.fileno())

        try:
            os.link(
                temporary_name,
                target.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            if _read_regular_file_at(parent_fd, target.name) == payload:
                os.unlink(temporary_name, dir_fd=parent_fd)
                temporary_name = None
                os.fsync(parent_fd)
                _verify_lexical_publication(
                    target=target,
                    anchored_parent_fd=parent_fd,
                    payload=payload,
                )
                return "EXISTING_IDENTICAL"
            raise CanonicalContractError(f"WRITE_ONCE_RACE:{target}") from exc
        os.unlink(temporary_name, dir_fd=parent_fd)
        temporary_name = None
        os.fsync(parent_fd)
        _verify_lexical_publication(
            target=target,
            anchored_parent_fd=parent_fd,
            payload=payload,
        )
        return "CREATED"
    finally:
        operations = []
        if descriptor >= 0:
            operations.append(("WRITE_ONCE_TEMP_FD_CLOSE", lambda: os.close(descriptor)))
        if temporary_name is not None:
            operations.append(
                (
                    "WRITE_ONCE_TEMP_UNLINK",
                    lambda: _unlink_at_missing_ok(parent_fd, temporary_name),
                )
            )
        operations.append(("WRITE_ONCE_PARENT_CLOSE", lambda: os.close(parent_fd)))
        _cleanup_preserving_primary(operations)


def write_once_json(path: Path, value: Mapping[str, Any]) -> str:
    """Publish canonical JSON once, or durably confirm an identical winner."""

    return write_once_bytes(path, canonical_bytes(dict(value)) + b"\n")


__all__ = [
    "atomic_replace_bytes",
    "atomic_replace_json",
    "confirm_existing_bytes",
    "confirm_existing_directory",
    "confirm_existing_json",
    "ensure_directory_tree",
    "exclusive_lock_file",
    "rename_directory_noreplace_at",
    "write_once_directory",
    "write_once_bytes",
    "write_once_json",
]
