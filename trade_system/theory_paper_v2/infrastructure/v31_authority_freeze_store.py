"""Contained, write-once filesystem primitives for the V3.1 authority freeze."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..application.v31_authority_freeze import (
    V31AuthorityFreezeError,
    canonical_document_physical_sha256,
    document_binding,
)
from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    load_json_strict,
    verify_self_digest,
)


class V31AuthorityFreezeStoreError(ValueError):
    """The local write-once authority store failed closed."""


def _project_root(value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_PROJECT_ROOT_INVALID") from exc
    if not root.is_dir():
        raise V31AuthorityFreezeStoreError("V31_FREEZE_PROJECT_ROOT_INVALID")
    return root


def _relative(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise V31AuthorityFreezeStoreError(code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.as_posix() != value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31AuthorityFreezeStoreError(code)
    return value


def _contained_path(root: Path, relative_path: str, *, require_file: bool) -> Path:
    relative = _relative(relative_path, "V31_FREEZE_PATH_INVALID")
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        if candidate.is_symlink():
            raise V31AuthorityFreezeStoreError("V31_FREEZE_SYMLINK_FORBIDDEN")
        if require_file:
            target = candidate.resolve(strict=True)
        else:
            target = candidate.resolve(strict=False)
        target.relative_to(root)
    except (OSError, ValueError) as exc:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_PATH_ESCAPE") from exc
    if require_file and (not target.is_file() or target.is_symlink()):
        raise V31AuthorityFreezeStoreError("V31_FREEZE_FILE_REQUIRED")
    return target


def sha256_file(project_root: Path, relative_path: str) -> str:
    root = _project_root(project_root)
    path = _contained_path(root, relative_path, require_file=True)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_bytes(project_root: Path, relative_path: str) -> bytes:
    root = _project_root(project_root)
    return _contained_path(root, relative_path, require_file=True).read_bytes()


def load_json_document(project_root: Path, relative_path: str) -> dict[str, Any]:
    root = _project_root(project_root)
    path = _contained_path(root, relative_path, require_file=True)
    try:
        return load_json_strict(path)
    except CanonicalContractError as exc:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_JSON_INVALID") from exc


def load_self_digested_document(
    project_root: Path, relative_path: str, *, digest_field: str
) -> dict[str, Any]:
    document = load_json_document(project_root, relative_path)
    try:
        verify_self_digest(document, digest_field)
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_SELF_DIGEST_INVALID") from exc
    return document


def binding_for_existing_document(
    project_root: Path,
    relative_path: str,
    *,
    digest_field: str,
) -> dict[str, str]:
    document = load_self_digested_document(
        project_root, relative_path, digest_field=digest_field
    )
    try:
        binding = document_binding(
            path=relative_path, document=document, digest_field=digest_field
        )
    except V31AuthorityFreezeError as exc:
        raise V31AuthorityFreezeStoreError(
            "V31_FREEZE_EXISTING_DOCUMENT_INVALID"
        ) from exc
    physical = sha256_file(project_root, relative_path)
    return {**binding, "physical_sha256": physical}


def collect_exact_implementation_bindings(
    project_root: Path, *, exact_paths: tuple[str, ...]
) -> dict[str, str]:
    """Hash every explicitly frozen runtime path; absence fails closed."""

    if not exact_paths or tuple(sorted(set(exact_paths))) != exact_paths:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_RUNTIME_PATH_SET_INVALID")
    return {path: sha256_file(project_root, path) for path in exact_paths}


def preflight_write_once_json(
    project_root: Path, relative_path: str, document: Mapping[str, Any]
) -> None:
    """Reject a conflicting target before any chronology write begins."""

    root = _project_root(project_root)
    target = _contained_path(root, relative_path, require_file=False)
    try:
        payload = canonical_bytes(document) + b"\n"
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_DOCUMENT_INVALID") from exc
    if target.exists():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
            raise V31AuthorityFreezeStoreError("V31_FREEZE_WRITE_ONCE_CONFLICT")


def write_once_json(
    project_root: Path,
    relative_path: str,
    document: Mapping[str, Any],
    *,
    digest_field: str,
) -> dict[str, str]:
    """Atomically publish canonical JSON, allowing exact idempotent re-entry."""

    root = _project_root(project_root)
    relative = _relative(relative_path, "V31_FREEZE_PATH_INVALID")
    target = _contained_path(root, relative, require_file=False)
    try:
        semantic = verify_self_digest(document, digest_field)
        payload = canonical_bytes(document) + b"\n"
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_DOCUMENT_INVALID") from exc
    expected_physical = canonical_document_physical_sha256(document)
    if hashlib.sha256(payload).hexdigest() != expected_physical:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_PHYSICAL_DIGEST_INVALID")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
            raise V31AuthorityFreezeStoreError("V31_FREEZE_WRITE_ONCE_CONFLICT")
    else:
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
                    raise V31AuthorityFreezeStoreError(
                        "V31_FREEZE_WRITE_ONCE_CONFLICT"
                    )
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    readback = target.read_bytes()
    if readback != payload or hashlib.sha256(readback).hexdigest() != expected_physical:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_READBACK_DRIFT")
    loaded = load_json_document(root, relative)
    try:
        if verify_self_digest(loaded, digest_field) != semantic or loaded != dict(document):
            raise V31AuthorityFreezeStoreError("V31_FREEZE_READBACK_DRIFT")
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_READBACK_DRIFT") from exc
    return {
        "path": relative,
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": expected_physical,
    }


def verify_exact_implementation_bindings(
    project_root: Path, implementation_bindings: Mapping[str, str], *, exact_paths: tuple[str, ...]
) -> None:
    if tuple(implementation_bindings) != exact_paths:
        raise V31AuthorityFreezeStoreError("V31_FREEZE_RUNTIME_PATH_SET_INVALID")
    actual = collect_exact_implementation_bindings(
        project_root, exact_paths=exact_paths
    )
    if actual != dict(implementation_bindings):
        raise V31AuthorityFreezeStoreError("V31_FREEZE_RUNTIME_PHYSICAL_DRIFT")


__all__ = [
    "V31AuthorityFreezeStoreError",
    "binding_for_existing_document",
    "collect_exact_implementation_bindings",
    "load_json_document",
    "load_self_digested_document",
    "preflight_write_once_json",
    "read_bytes",
    "sha256_file",
    "verify_exact_implementation_bindings",
    "write_once_json",
]
