"""Local write-once mailbox and atomic cursor for the native Codex transport."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from .continuous_fixture import CanonicalContinuousArtifactRepository


class NativeAgentMailboxError(ValueError):
    """A fail-closed local mailbox persistence violation."""


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
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


class LocalNativeAgentTransportStore:
    """Own native mailbox artifacts and the replaceable self-digested cursor."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.artifacts = CanonicalContinuousArtifactRepository(self.run_root)
        self.checkpoint_path = self.run_root / "native-checkpoint.json"

    def document_exists(self, *, relative_ref: str) -> bool:
        return self.artifacts.document_exists(relative_ref=relative_ref)

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str | None,
    ) -> Mapping[str, str]:
        return self.artifacts.write_document(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        return self.artifacts.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        return self.artifacts.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )

    def initialize_checkpoint(
        self, *, run_id: str, created_at: str
    ) -> Mapping[str, Any]:
        if self.checkpoint_path.exists():
            return self.load_checkpoint(run_id=run_id)
        checkpoint = self_digest(
            {
                "schema_id": "native_codex_transport_checkpoint",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "revision": 0,
                "status": "READY_FOR_PROPOSAL",
                "cycle_index": 1,
                "active_stage": None,
                "active_request_digest": None,
                "last_consume_receipt_digest": None,
                "accepted_state_digest": None,
                "completion_receipt_digest": None,
                "created_at": created_at,
                "updated_at": created_at,
                "chat_history_is_authority": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
            },
            "native_transport_checkpoint_digest",
        )
        _atomic_json(self.checkpoint_path, checkpoint)
        return checkpoint

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        checkpoint = load_json_strict(self.checkpoint_path)
        try:
            verify_self_digest(
                checkpoint, "native_transport_checkpoint_digest"
            )
        except ValueError as exc:
            raise NativeAgentMailboxError(
                "NATIVE_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        if (
            checkpoint.get("schema_id")
            != "native_codex_transport_checkpoint"
            or checkpoint.get("schema_version") != "1.0.0"
            or checkpoint.get("run_id") != run_id
            or checkpoint.get("chat_history_is_authority") is not False
            or checkpoint.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
        ):
            raise NativeAgentMailboxError("NATIVE_CHECKPOINT_CONTRACT_INVALID")
        return checkpoint

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        current = self.load_checkpoint(run_id=run_id)
        if (
            current["native_transport_checkpoint_digest"]
            != expected_checkpoint_digest
        ):
            raise NativeAgentMailboxError("NATIVE_CHECKPOINT_COMPARE_SWAP_FAILED")
        candidate = self_digest(
            dict(checkpoint), "native_transport_checkpoint_digest"
        )
        if (
            candidate.get("run_id") != run_id
            or candidate.get("revision") != current.get("revision", -1) + 1
        ):
            raise NativeAgentMailboxError("NATIVE_CHECKPOINT_TRANSITION_INVALID")
        _atomic_json(self.checkpoint_path, candidate)
        return candidate


__all__ = ["LocalNativeAgentTransportStore", "NativeAgentMailboxError"]
