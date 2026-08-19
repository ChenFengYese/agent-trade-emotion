"""Local evidence store for the four-cycle native market pilot."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

from ..domain.contracts.canonical import load_json_strict, self_digest, verify_self_digest
from .native_agent_mailbox import (
    LocalNativeAgentTransportStore,
    NativeAgentMailboxError,
    _atomic_json,
)


class NativeMarketPilotStoreError(ValueError):
    """A pilot artifact or cursor violated its durable-store contract."""


class LocalNativeMarketPilotStore(LocalNativeAgentTransportStore):
    def __init__(self, run_root: Path) -> None:
        super().__init__(run_root)
        self.market_checkpoint_path = self.run_root / "market-checkpoint.json"

    def _safe_path(self, relative_ref: str) -> Path:
        candidate = Path(relative_ref)
        if candidate.is_absolute() or not candidate.parts or any(
            part in {"", ".", ".."} for part in candidate.parts
        ):
            raise NativeMarketPilotStoreError("NATIVE_MARKET_ARTIFACT_REF_INVALID")
        path = (self.run_root / candidate).resolve()
        try:
            path.relative_to(self.run_root)
        except ValueError as exc:
            raise NativeMarketPilotStoreError(
                "NATIVE_MARKET_ARTIFACT_REF_INVALID"
            ) from exc
        return path

    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]:
        if not isinstance(payload, bytes):
            raise NativeMarketPilotStoreError("NATIVE_MARKET_RAW_BYTES_INVALID")
        target = self._safe_path(relative_ref)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.read_bytes() != payload:
                raise NativeMarketPilotStoreError("NATIVE_MARKET_RAW_WRITE_ONCE_CONFLICT")
        else:
            try:
                descriptor = os.open(
                    target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
            except FileExistsError as exc:
                if not target.is_file() or target.read_bytes() != payload:
                    raise NativeMarketPilotStoreError(
                        "NATIVE_MARKET_RAW_WRITE_ONCE_CONFLICT"
                    ) from exc
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "relative_ref": relative_ref,
            "semantic_digest": digest,
            "physical_sha256": digest,
        }

    def initialize_market_checkpoint(
        self,
        *,
        run_id: str,
        created_at: str,
        first_due_at: str,
        total_cycles: int,
        cadence_seconds: int,
    ) -> Mapping[str, Any]:
        if self.market_checkpoint_path.exists():
            return self.load_market_checkpoint(run_id=run_id)
        if total_cycles < 1 or cadence_seconds < 1:
            raise NativeMarketPilotStoreError("NATIVE_MARKET_CHECKPOINT_INPUT_INVALID")
        checkpoint = self_digest(
            {
                "schema_id": "native_codex_market_pilot_checkpoint",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "revision": 0,
                "status": "READY_FOR_CYCLE",
                "cycle_index": 1,
                "total_cycles": total_cycles,
                "cadence_seconds": cadence_seconds,
                "next_due_at": first_due_at,
                "active_stage": None,
                "active_request_digest": None,
                "active_market_snapshot_digest": None,
                "last_consume_receipt_digest": None,
                "last_accepted_state_digest": None,
                "last_completion_receipt_digest": None,
                "failure_receipt_digest": None,
                "created_at": created_at,
                "updated_at": created_at,
                "agent_id": "CURRENT_CODEX_TASK",
                "evidence_level": "PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT",
                "chat_history_is_authority": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "native_market_checkpoint_digest",
        )
        _atomic_json(self.market_checkpoint_path, checkpoint)
        return checkpoint

    def load_market_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        checkpoint = load_json_strict(self.market_checkpoint_path)
        try:
            verify_self_digest(checkpoint, "native_market_checkpoint_digest")
        except ValueError as exc:
            raise NativeMarketPilotStoreError(
                "NATIVE_MARKET_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        if (
            checkpoint.get("schema_id")
            != "native_codex_market_pilot_checkpoint"
            or checkpoint.get("schema_version") != "1.0.0"
            or checkpoint.get("run_id") != run_id
            or checkpoint.get("agent_id") != "CURRENT_CODEX_TASK"
            or checkpoint.get("chat_history_is_authority") is not False
            or checkpoint.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or checkpoint.get("executable") is not False
        ):
            raise NativeMarketPilotStoreError("NATIVE_MARKET_CHECKPOINT_INVALID")
        return checkpoint

    def replace_market_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        current = self.load_market_checkpoint(run_id=run_id)
        if current["native_market_checkpoint_digest"] != expected_checkpoint_digest:
            raise NativeMarketPilotStoreError(
                "NATIVE_MARKET_CHECKPOINT_COMPARE_SWAP_FAILED"
            )
        candidate = self_digest(dict(checkpoint), "native_market_checkpoint_digest")
        if (
            candidate.get("run_id") != run_id
            or candidate.get("revision") != int(current["revision"]) + 1
        ):
            raise NativeMarketPilotStoreError(
                "NATIVE_MARKET_CHECKPOINT_TRANSITION_INVALID"
            )
        _atomic_json(self.market_checkpoint_path, candidate)
        return candidate


__all__ = ["LocalNativeMarketPilotStore", "NativeMarketPilotStoreError"]
