"""Invoke one resolved role once and archive exact untrusted bytes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ...application.ports import ContentStorePort
from ...domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
    verify_self_digest,
)
from ...domain.contracts.validation import validate_schema_value


class AgentAdapterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentTransportResult:
    output_bytes: bytes
    tool_call_names: tuple[str, ...] = ()
    reused_thread: bool = False
    repository_accessed: bool = False
    evidence_refreshed: bool = False
    execution_attempted: bool = False


@dataclass(frozen=True, slots=True)
class RawAgentResult:
    role_id: str
    input_digest: str
    output_digest: str
    output_schema_id: str
    archived_blob_digest: str
    parsed_output: Mapping[str, Any]
    tool_call_names: tuple[str, ...]
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False


class OneShotAgentAdapter:
    def __init__(
        self,
        *,
        content_store: ContentStorePort,
        transport: Callable[[str, bytes, str], AgentTransportResult],
    ) -> None:
        self._content_store = content_store
        self._transport = transport

    def invoke(
        self,
        *,
        decision_session_id: str,
        role_id: str,
        canonical_input: bytes,
        expected_input_digest: str,
        expected_output_schema_id: str,
        output_schema: Mapping[str, Any],
        skill_resolution_receipt: Mapping[str, Any],
    ) -> RawAgentResult:
        verify_self_digest(skill_resolution_receipt, "receipt_digest")
        if (
            skill_resolution_receipt.get("verdict") != "PASS"
            or skill_resolution_receipt.get("callable") is not True
            or skill_resolution_receipt.get("allowed_caller")
            != "APPLICATION_DECISION_SESSION"
            or skill_resolution_receipt.get("role_id") != role_id
            or skill_resolution_receipt.get("execution_kind")
            != "GENERATIVE_AGENT_ROLE"
        ):
            raise AgentAdapterError("ROLE_UNAVAILABLE_SESSION_INCOMPLETE")
        actual_input_digest = hashlib.sha256(canonical_input).hexdigest()
        if actual_input_digest != expected_input_digest:
            raise AgentAdapterError("ROLE_INPUT_BYTES_DIGEST_MISMATCH_NO_COMMIT")
        result = self._transport(
            role_id, canonical_input, expected_output_schema_id
        )
        if (
            result.tool_call_names
            or result.reused_thread
            or result.repository_accessed
            or result.evidence_refreshed
            or result.execution_attempted
        ):
            raise AgentAdapterError("ROLE_INPUT_PROJECTION_INVALID_NO_COMMIT")
        parsed = loads_json_strict(result.output_bytes)
        validate_schema_value(parsed, output_schema)
        if parsed.get("schema_id") != expected_output_schema_id:
            raise AgentAdapterError("SCHEMA_INVALID")
        archived_digest = self._content_store.put(
            f"{decision_session_id}/{role_id}",
            f"raw-agent-result-{actual_input_digest}",
            result.output_bytes,
        )
        # Re-encoding is a validation only; exact output bytes remain archived.
        canonical_bytes(parsed)
        return RawAgentResult(
            role_id=role_id,
            input_digest=actual_input_digest,
            output_digest=hashlib.sha256(result.output_bytes).hexdigest(),
            output_schema_id=expected_output_schema_id,
            archived_blob_digest=archived_digest,
            parsed_output=parsed,
            tool_call_names=result.tool_call_names,
        )

