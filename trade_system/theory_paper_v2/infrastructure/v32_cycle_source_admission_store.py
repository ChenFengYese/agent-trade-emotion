"""Local write-once byte store for V3.2 cycle-source admission evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..application.v32_cycle_source_store_port import (
    V32CycleSourcePersistenceError,
)
from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
    verify_self_digest,
)
from ..v32_durable_json import (
    confirm_existing_bytes,
    ensure_directory_tree,
    write_once_bytes,
)


class V32CycleSourceAdmissionStoreError(V32CycleSourcePersistenceError):
    """A path, byte, digest, symlink, or write-once invariant failed."""


class LocalV32CycleSourceAdmissionStore:
    """Small filesystem adapter; it owns bytes but no admission semantics."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if self.root.exists() and self.root.is_symlink():
            raise V32CycleSourceAdmissionStoreError("V32_SOURCE_STORE_ROOT_SYMLINK")
        ensure_directory_tree(self.root)
        self._root_resolved = self.root.resolve(strict=True)

    def _path(self, relative_ref: str, *, create_parent: bool = False) -> Path:
        if not isinstance(relative_ref, str) or not relative_ref or "\\" in relative_ref:
            raise V32CycleSourceAdmissionStoreError("V32_SOURCE_STORE_PATH_INVALID")
        pure = PurePosixPath(relative_ref)
        if (
            pure.is_absolute()
            or pure.as_posix() != relative_ref
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise V32CycleSourceAdmissionStoreError("V32_SOURCE_STORE_PATH_INVALID")
        cursor = self.root
        for part in pure.parts[:-1]:
            cursor = cursor / part
            if cursor.exists() and cursor.is_symlink():
                raise V32CycleSourceAdmissionStoreError(
                    "V32_SOURCE_STORE_SYMLINK_FORBIDDEN"
                )
        target = self.root.joinpath(*pure.parts)
        if target.exists() and target.is_symlink():
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_SYMLINK_FORBIDDEN"
            )
        if create_parent:
            ensure_directory_tree(target.parent)
            cursor = self.root
            for part in pure.parts[:-1]:
                cursor = cursor / part
                if cursor.is_symlink():
                    raise V32CycleSourceAdmissionStoreError(
                        "V32_SOURCE_STORE_SYMLINK_FORBIDDEN"
                    )
        try:
            parent_resolved = target.parent.resolve(strict=True)
            parent_resolved.relative_to(self._root_resolved)
        except (FileNotFoundError, ValueError) as exc:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_PATH_ESCAPE"
            ) from exc
        return target

    def write_raw(self, *, relative_ref: str, payload: bytes) -> dict[str, str]:
        if not isinstance(payload, bytes):
            raise V32CycleSourceAdmissionStoreError("V32_SOURCE_STORE_BYTES_REQUIRED")
        target = self._path(relative_ref, create_parent=True)
        physical = hashlib.sha256(payload).hexdigest()
        try:
            write_once_bytes(target, payload)
        except CanonicalContractError as exc:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_WRITE_ONCE_CONFLICT"
            ) from exc
        except (OSError, TypeError, ValueError) as exc:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_WRITE_ONCE_FAILED"
            ) from exc
        try:
            confirm_existing_bytes(target, payload)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_WRITE_READBACK_MISMATCH"
            ) from exc
        return {"relative_ref": relative_ref, "physical_sha256": physical}

    def artifact_exists(self, *, relative_ref: str) -> bool:
        """Return whether one safe relative artifact already exists.

        The method deliberately creates only missing parent directories.  This
        lets a raw-first collector reserve a one-shot attempt before touching a
        transport, while retaining the same path/symlink checks as all writes.
        """

        target = self._path(relative_ref, create_parent=True)
        if not target.exists():
            return False
        if not target.is_file() or target.is_symlink():
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_FILE_INVALID"
            )
        return True

    def read_raw(self, *, relative_ref: str, expected_sha256: str | None = None) -> bytes:
        target = self._path(relative_ref)
        if not target.exists() or not target.is_file() or target.is_symlink():
            raise V32CycleSourceAdmissionStoreError("V32_SOURCE_STORE_FILE_MISSING")
        payload = target.read_bytes()
        physical = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and physical != expected_sha256:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_PHYSICAL_SHA_MISMATCH"
            )
        try:
            confirm_existing_bytes(target, payload)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_FILE_INVALID"
            ) from exc
        return payload

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> dict[str, str]:
        try:
            semantic = verify_self_digest(document, digest_field)
            schema_id = document["schema_id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_DOCUMENT_INVALID"
            ) from exc
        if not isinstance(schema_id, str) or not schema_id:
            raise V32CycleSourceAdmissionStoreError("V32_SOURCE_STORE_DOCUMENT_INVALID")
        payload = canonical_bytes(dict(document)) + b"\n"
        physical = self.write_raw(relative_ref=relative_ref, payload=payload)[
            "physical_sha256"
        ]
        return {
            "relative_ref": relative_ref,
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": physical,
        }

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
        expected_physical_sha256: str | None = None,
    ) -> dict[str, Any]:
        payload = self.read_raw(
            relative_ref=relative_ref,
            expected_sha256=expected_physical_sha256,
        )
        try:
            document = loads_json_strict(payload)
            semantic = verify_self_digest(document, digest_field)
        except (TypeError, ValueError) as exc:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_DOCUMENT_READ_INVALID"
            ) from exc
        if expected_semantic_digest is not None and semantic != expected_semantic_digest:
            raise V32CycleSourceAdmissionStoreError(
                "V32_SOURCE_STORE_SEMANTIC_DIGEST_MISMATCH"
            )
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> dict[str, str]:
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        payload = self.read_raw(relative_ref=relative_ref)
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }


__all__ = [
    "LocalV32CycleSourceAdmissionStore",
    "V32CycleSourceAdmissionStoreError",
]
