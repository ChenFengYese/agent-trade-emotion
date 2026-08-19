"""Independent local store for one V3.1 source qualification.

The store deliberately does not inherit the research-run store.  It owns a
separate checkpoint, a non-blocking process lease, write-once evidence, and
raw-byte readback.  No method can start or advance a research experiment.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.v31_source_qualification import (
    V31SourceQualificationError,
    initialize_v31_source_qualification_checkpoint,
    verify_v31_source_qualification_checkpoint,
)


class V31SourceQualificationStoreError(ValueError):
    """A qualification-store durability or ownership invariant failed."""


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    payload = canonical_bytes(dict(document)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


class LocalV31SourceQualificationStore:
    """Qualification-only write-once artifacts plus one CAS cursor."""

    checkpoint_ref = "qualification-checkpoint.json"

    def __init__(self, qualification_root: Path) -> None:
        supplied_root = Path(qualification_root)
        if supplied_root.is_symlink():
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_SYMLINK_FORBIDDEN"
            )
        self.qualification_root = supplied_root.resolve()
        self.qualification_root.mkdir(parents=True, exist_ok=True)
        self._lease_handle: Any = None

    @property
    def lease_held(self) -> bool:
        return self._lease_handle is not None

    @property
    def checkpoint_path(self) -> Path:
        # Re-evaluate on every access so a symlink introduced after store
        # construction cannot become an implicit checkpoint authority.
        return self._safe_path(self.checkpoint_ref)

    def _safe_path(self, relative_ref: str) -> Path:
        candidate = Path(relative_ref)
        if candidate.is_absolute() or not candidate.parts or any(
            part in {"", ".", ".."} for part in candidate.parts
        ):
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_ARTIFACT_REF_INVALID"
            )
        cursor = self.qualification_root
        for part in candidate.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V31SourceQualificationStoreError(
                    "V31_SOURCE_QUALIFICATION_SYMLINK_FORBIDDEN"
                )
        target = (self.qualification_root / candidate).resolve()
        try:
            target.relative_to(self.qualification_root)
        except ValueError as exc:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_ARTIFACT_REF_INVALID"
            ) from exc
        return target

    def _require_lease(self) -> None:
        if self._lease_handle is None:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_MUTATION_REQUIRES_LEASE"
            )

    @contextmanager
    def exclusive_lease(self, *, qualification_id: str) -> Iterator[None]:
        if not isinstance(qualification_id, str) or not qualification_id:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_LEASE_ID_INVALID"
            )
        if self._lease_handle is not None:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_LEASE_ALREADY_HELD"
            )
        lock_path = self._safe_path("controller/qualification.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_LEASE_ALREADY_HELD"
            ) from exc
        self._lease_handle = handle
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
            self._lease_handle = None

    def document_exists(self, *, relative_ref: str) -> bool:
        return self._safe_path(relative_ref).is_file()

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]:
        self._require_lease()
        target = self._safe_path(relative_ref)
        payload = dict(document)
        try:
            if digest_field in payload:
                semantic_digest = verify_self_digest(payload, digest_field)
            else:
                payload = self_digest(payload, digest_field)
                semantic_digest = str(payload[digest_field])
        except ValueError as exc:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_DOCUMENT_DIGEST_INVALID"
            ) from exc
        write_once_json(target, payload)
        directory_descriptor = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return {
            "relative_ref": relative_ref,
            "semantic_digest": semantic_digest,
            "physical_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        target = self._safe_path(relative_ref)
        try:
            document = load_json_strict(target)
            digest = verify_self_digest(document, digest_field)
        except ValueError as exc:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_DOCUMENT_INVALID"
            ) from exc
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_DOCUMENT_DIGEST_MISMATCH"
            )
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        target = self._safe_path(relative_ref)
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        return {
            "relative_ref": relative_ref,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }

    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]:
        self._require_lease()
        if not isinstance(payload, bytes):
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_RAW_BYTES_INVALID"
            )
        target = self._safe_path(relative_ref)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.read_bytes() != payload:
                raise V31SourceQualificationStoreError(
                    "V31_SOURCE_QUALIFICATION_RAW_WRITE_ONCE_CONFLICT"
                )
        else:
            try:
                descriptor = os.open(
                    target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
            except FileExistsError as exc:
                if not target.is_file() or target.read_bytes() != payload:
                    raise V31SourceQualificationStoreError(
                        "V31_SOURCE_QUALIFICATION_RAW_WRITE_ONCE_CONFLICT"
                    ) from exc
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                directory_descriptor = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
        digest = hashlib.sha256(payload).hexdigest()
        readback = self.read_raw(relative_ref=relative_ref, expected_sha256=digest)
        if readback != payload:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_RAW_READBACK_MISMATCH"
            )
        return {
            "relative_ref": relative_ref,
            "semantic_digest": digest,
            "physical_sha256": digest,
        }

    def read_raw(
        self, *, relative_ref: str, expected_sha256: str | None = None
    ) -> bytes:
        target = self._safe_path(relative_ref)
        try:
            payload = target.read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError) as exc:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_RAW_MISSING"
            ) from exc
        digest = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_RAW_DIGEST_MISMATCH"
            )
        return payload

    def initialize_checkpoint(
        self,
        *,
        qualification_id: str,
        plan_binding: Mapping[str, Any],
        reservation_binding: Mapping[str, Any],
        created_at: str,
    ) -> Mapping[str, Any]:
        self._require_lease()
        if self.checkpoint_path.exists():
            existing = self.load_checkpoint(qualification_id=qualification_id)
            if (
                existing.get("plan_binding") != dict(plan_binding)
                or existing.get("reservation_binding") != dict(reservation_binding)
            ):
                raise V31SourceQualificationStoreError(
                    "V31_SOURCE_QUALIFICATION_CHECKPOINT_BINDING_CONFLICT"
                )
            return existing
        checkpoint = initialize_v31_source_qualification_checkpoint(
            qualification_id=qualification_id,
            plan_binding=plan_binding,
            reservation_binding=reservation_binding,
            created_at=created_at,
        )
        _atomic_json(self.checkpoint_path, checkpoint)
        return checkpoint

    def load_checkpoint(self, *, qualification_id: str) -> Mapping[str, Any]:
        checkpoint_path = self.checkpoint_path
        try:
            checkpoint = load_json_strict(checkpoint_path)
            verify_v31_source_qualification_checkpoint(checkpoint)
        except (ValueError, V31SourceQualificationError) as exc:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_CHECKPOINT_INVALID"
            ) from exc
        if checkpoint.get("qualification_id") != qualification_id:
            raise V31SourceQualificationStoreError(
                "V31_SOURCE_QUALIFICATION_CHECKPOINT_ID_MISMATCH"
            )
        return checkpoint

    def replace_checkpoint(
        self,
        *,
        qualification_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self._require_lease()
        lock_path = self._safe_path("controller/checkpoint-cas.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                current = self.load_checkpoint(qualification_id=qualification_id)
                if (
                    current["source_qualification_checkpoint_digest"]
                    != expected_checkpoint_digest
                ):
                    raise V31SourceQualificationStoreError(
                        "V31_SOURCE_QUALIFICATION_CHECKPOINT_CAS_FAILED"
                    )
                try:
                    verify_v31_source_qualification_checkpoint(checkpoint)
                except V31SourceQualificationError as exc:
                    raise V31SourceQualificationStoreError(
                        "V31_SOURCE_QUALIFICATION_CHECKPOINT_REPLACEMENT_INVALID"
                    ) from exc
                allowed = {
                    "RESERVED": {"COLLECTING"},
                    "COLLECTING": {"SEALED", "FAILED_CLOSED"},
                    "SEALED": set(),
                    "FAILED_CLOSED": set(),
                }
                if (
                    checkpoint.get("qualification_id") != qualification_id
                    or checkpoint.get("revision") != current["revision"] + 1
                    or checkpoint.get("status") not in allowed[current["status"]]
                    or checkpoint.get("plan_binding") != current["plan_binding"]
                    or checkpoint.get("reservation_binding")
                    != current["reservation_binding"]
                ):
                    raise V31SourceQualificationStoreError(
                        "V31_SOURCE_QUALIFICATION_CHECKPOINT_TRANSITION_INVALID"
                    )
                _atomic_json(self.checkpoint_path, checkpoint)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return self.load_checkpoint(qualification_id=qualification_id)


__all__ = [
    "LocalV31SourceQualificationStore",
    "V31SourceQualificationStoreError",
]
