"""Local CAS/write-once store for the versioned V3.1 supervisor.

Only this adapter owns the mutable supervisor checkpoint.  Permit, commit-intent
and failure documents are canonical write-once artifacts and are physically
replayed whenever the live checkpoint points at them.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Callable, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    write_once_json,
)
from ..domain.v31_experiment_supervisor_v2 import (
    COMMIT_INTENT_DIGEST_FIELD,
    COMMIT_INTENT_SCHEMA_ID,
    CYCLE_PERMIT_DIGEST_FIELD,
    CYCLE_PERMIT_SCHEMA_ID,
    SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    SUPERVISOR_ROOT_V2,
    SUPERVISOR_FAILURE_DIGEST_FIELD,
    SUPERVISOR_FAILURE_SCHEMA_ID,
    commit_intent_ref_v2,
    cycle_permit_ref_v2,
    supervisor_failure_ref_v2,
    validate_commit_intent_v2,
    validate_cycle_permit_v2,
    validate_supervisor_checkpoint_v2,
    validate_supervisor_failure_v2,
    validate_supervisor_transition_v2,
)


class V31SupervisorStoreV2Error(ValueError):
    """The local supervisor evidence or compare-and-swap cursor is invalid."""


SUPERVISOR_CHECKPOINT_REF_V2 = f"{SUPERVISOR_ROOT_V2}/checkpoint.json"


_DOCUMENT_SPECS: dict[
    str, tuple[str, Callable[[Mapping[str, Any]], str]]
] = {
    CYCLE_PERMIT_SCHEMA_ID: (CYCLE_PERMIT_DIGEST_FIELD, validate_cycle_permit_v2),
    COMMIT_INTENT_SCHEMA_ID: (
        COMMIT_INTENT_DIGEST_FIELD,
        validate_commit_intent_v2,
    ),
    SUPERVISOR_FAILURE_SCHEMA_ID: (
        SUPERVISOR_FAILURE_DIGEST_FIELD,
        validate_supervisor_failure_v2,
    ),
}


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
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


class LocalV31SupervisorStoreV2:
    """One local supervisor owner for a single successor run root."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self._safe_path(SUPERVISOR_CHECKPOINT_REF_V2)

    @contextmanager
    def _lock(self):
        path = self.run_root / ".locks" / "supervisor-v2.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _safe_path(self, relative_ref: str) -> Path:
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V31SupervisorStoreV2Error("V31_SUPERVISOR_V2_REF_INVALID")
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or any(part in {"", ".", ".."} for part in lexical.parts)
            or not lexical.parts
            or lexical.parts[0] != SUPERVISOR_ROOT_V2
        ):
            raise V31SupervisorStoreV2Error("V31_SUPERVISOR_V2_REF_INVALID")
        cursor = self.run_root
        for part in lexical.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_SYMLINK_FORBIDDEN"
                )
        target = self.run_root.joinpath(*lexical.parts).resolve(strict=False)
        try:
            target.relative_to(self.run_root)
        except ValueError as exc:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_REF_ESCAPE"
            ) from exc
        return target

    @staticmethod
    def _physical_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_known_document(
        document: Mapping[str, Any], *, digest_field: str
    ) -> str:
        if not isinstance(document, Mapping):
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_DOCUMENT_INVALID"
            )
        schema_id = document.get("schema_id")
        spec = _DOCUMENT_SPECS.get(str(schema_id))
        if spec is None or spec[0] != digest_field:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_DOCUMENT_SCHEMA_INVALID"
            )
        try:
            return spec[1](document)
        except (TypeError, ValueError) as exc:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_DOCUMENT_INVALID"
            ) from exc

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]:
        semantic = self._validate_known_document(
            document, digest_field=digest_field
        )
        path = self._safe_path(relative_ref)
        try:
            write_once_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_WRITE_ONCE_CONFLICT"
            ) from exc
        durable = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=semantic,
        )
        if dict(durable) != dict(document):
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_WRITE_READBACK_DRIFT"
            )
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": self._physical_sha256(path),
        }

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        path = self._safe_path(relative_ref)
        try:
            if path.is_symlink() or not path.is_file():
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_DOCUMENT_MISSING"
                )
            document = load_json_strict(path)
            semantic = self._validate_known_document(
                document, digest_field=digest_field
            )
        except V31SupervisorStoreV2Error:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_DOCUMENT_INVALID"
            ) from exc
        if expected_semantic_digest is not None and semantic != expected_semantic_digest:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_DOCUMENT_SEMANTIC_DRIFT"
            )
        expected_payload = canonical_bytes(dict(document)) + b"\n"
        if path.read_bytes() != expected_payload:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_DOCUMENT_PHYSICAL_DRIFT"
            )
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        path = self._safe_path(relative_ref)
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": self._physical_sha256(path),
        }

    def document_exists(self, *, relative_ref: str) -> bool:
        path = self._safe_path(relative_ref)
        return path.is_file() and not path.is_symlink()

    def initialize_checkpoint(
        self, *, checkpoint: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            validate_supervisor_checkpoint_v2(checkpoint)
        except (TypeError, ValueError) as exc:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_CHECKPOINT_INVALID"
            ) from exc
        if checkpoint.get("status") != "BOOTSTRAPPED":
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_INITIAL_STATUS_INVALID"
            )
        with self._lock():
            if self.checkpoint_path.exists():
                current = self.load_checkpoint(run_id=str(checkpoint["run_id"]))
                if dict(current) != dict(checkpoint):
                    raise V31SupervisorStoreV2Error(
                        "V31_SUPERVISOR_V2_INITIALIZATION_CONFLICT"
                    )
                return current
            try:
                write_once_json(self.checkpoint_path, checkpoint)
            except (OSError, TypeError, ValueError) as exc:
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_INITIALIZATION_FAILED"
                ) from exc
            return self.load_checkpoint(run_id=str(checkpoint["run_id"]))

    def _replay_live_artifacts(self, checkpoint: Mapping[str, Any]) -> None:
        status = checkpoint["status"]
        run_id = checkpoint["run_id"]
        cycle = checkpoint["current_cycle_index"]
        if status in {"CYCLE_PERMIT_OPEN", "COMMIT_RESERVED"}:
            permit_ref = cycle_permit_ref_v2(int(cycle))
            permit = self.read_document(
                relative_ref=permit_ref,
                digest_field=CYCLE_PERMIT_DIGEST_FIELD,
                expected_semantic_digest=str(checkpoint["active_permit_digest"]),
            )
            if (
                permit.get("run_id") != run_id
                or permit.get("cycle_index") != cycle
                or permit.get("research_checkpoint_digest")
                != checkpoint["research_checkpoint_digest"]
                or permit.get("monitor_checkpoint_digest")
                != checkpoint["monitor_checkpoint_digest"]
            ):
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_PERMIT_CHECKPOINT_MISMATCH"
                )
        if status == "COMMIT_RESERVED":
            intent = self.read_document(
                relative_ref=commit_intent_ref_v2(int(cycle)),
                digest_field=COMMIT_INTENT_DIGEST_FIELD,
                expected_semantic_digest=str(
                    checkpoint["active_commit_intent_digest"]
                ),
            )
            if (
                intent.get("run_id") != run_id
                or intent.get("cycle_index") != cycle
                or intent.get("cycle_permit_digest")
                != checkpoint["active_permit_digest"]
                or intent.get("research_checkpoint_digest_before_commit")
                != checkpoint["research_checkpoint_digest"]
                or intent.get("monitor_checkpoint_digest_before_commit")
                != checkpoint["monitor_checkpoint_digest"]
            ):
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_INTENT_CHECKPOINT_MISMATCH"
                )
        if status == "FAILED_CLOSED":
            failure = self.read_document(
                relative_ref=str(checkpoint["failure_ref"]),
                digest_field=SUPERVISOR_FAILURE_DIGEST_FIELD,
                expected_semantic_digest=str(checkpoint["failure_digest"]),
            )
            if (
                failure.get("run_id") != run_id
                or failure.get("research_checkpoint_digest")
                != checkpoint["research_checkpoint_digest"]
                or failure.get("monitor_checkpoint_digest")
                != checkpoint["monitor_checkpoint_digest"]
                or failure.get("resume_allowed") is not False
            ):
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_FAILURE_CHECKPOINT_MISMATCH"
                )

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        try:
            if self.checkpoint_path.is_symlink() or not self.checkpoint_path.is_file():
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_CHECKPOINT_MISSING"
                )
            checkpoint = load_json_strict(self.checkpoint_path)
            validate_supervisor_checkpoint_v2(checkpoint)
        except V31SupervisorStoreV2Error:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_CHECKPOINT_INVALID"
            ) from exc
        if checkpoint.get("run_id") != run_id:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_CHECKPOINT_RUN_MISMATCH"
            )
        expected_payload = canonical_bytes(dict(checkpoint)) + b"\n"
        if self.checkpoint_path.read_bytes() != expected_payload:
            raise V31SupervisorStoreV2Error(
                "V31_SUPERVISOR_V2_CHECKPOINT_PHYSICAL_DRIFT"
            )
        self._replay_live_artifacts(checkpoint)
        return checkpoint

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        with self._lock():
            current = self.load_checkpoint(run_id=run_id)
            if current[SUPERVISOR_CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_CHECKPOINT_CAS_FAILED"
                )
            try:
                validate_supervisor_transition_v2(current, checkpoint)
            except (TypeError, ValueError) as exc:
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_CHECKPOINT_TRANSITION_INVALID"
                ) from exc
            # Replay write-once artifacts before the pointer can make them live.
            self._replay_live_artifacts(checkpoint)
            _atomic_json(self.checkpoint_path, checkpoint)
            durable = self.load_checkpoint(run_id=run_id)
            if dict(durable) != dict(checkpoint):
                raise V31SupervisorStoreV2Error(
                    "V31_SUPERVISOR_V2_CHECKPOINT_READBACK_DRIFT"
                )
            return durable


__all__ = [
    "LocalV31SupervisorStoreV2",
    "SUPERVISOR_CHECKPOINT_REF_V2",
    "SUPERVISOR_ROOT_V2",
    "V31SupervisorStoreV2Error",
    "commit_intent_ref_v2",
    "cycle_permit_ref_v2",
    "supervisor_failure_ref_v2",
]
