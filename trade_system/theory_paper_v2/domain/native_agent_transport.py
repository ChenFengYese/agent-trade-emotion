"""Contracts for the file-mailbox transport used by the current Codex task.

The transport is intentionally asynchronous: the deterministic controller seals a
request and stops; Codex later claims it and writes one complete delivery; a new
controller process verifies and consumes that durable delivery.  Chat history is
never an authority and Codex never writes controller checkpoints or accepted state.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .contracts.canonical import canonical_bytes, canonical_digest, self_digest, verify_self_digest
from .native_market_cycle import (
    NativeMarketCycleError,
    validate_native_market_payload,
)


NATIVE_AGENT_ID = "CURRENT_CODEX_TASK"
NATIVE_EVIDENCE_LEVEL = "PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT"
NATIVE_STAGES = frozenset({"PROPOSAL", "DELIBERATION"})
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class NativeAgentTransportError(ValueError):
    """A fail-closed native Codex transport contract violation."""


def _required_text(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NativeAgentTransportError(reason)
    return value


def _sha256(value: object, reason: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise NativeAgentTransportError(reason)
    return value


def _stage(value: object) -> str:
    stage = _required_text(value, "NATIVE_STAGE_INVALID")
    if stage not in NATIVE_STAGES:
        raise NativeAgentTransportError("NATIVE_STAGE_INVALID")
    return stage


def _cycle_index(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise NativeAgentTransportError("NATIVE_CYCLE_INDEX_INVALID")
    return value


def validate_artifact_binding(binding: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(binding, Mapping):
        raise NativeAgentTransportError("NATIVE_ARTIFACT_BINDING_INVALID")
    relative_ref = _required_text(
        binding.get("relative_ref"), "NATIVE_ARTIFACT_REF_INVALID"
    )
    if relative_ref.startswith("/") or ".." in relative_ref.split("/"):
        raise NativeAgentTransportError("NATIVE_ARTIFACT_REF_INVALID")
    return {
        "relative_ref": relative_ref,
        "semantic_digest": _sha256(
            binding.get("semantic_digest"), "NATIVE_ARTIFACT_DIGEST_INVALID"
        ),
        "physical_sha256": _sha256(
            binding.get("physical_sha256"), "NATIVE_ARTIFACT_SHA256_INVALID"
        ),
    }


def build_native_agent_request(
    *,
    run_id: str,
    cycle_index: int,
    stage: str,
    created_at: str,
    input_binding: Mapping[str, Any],
    input_schema_id: str,
    expected_output_schema_id: str,
    max_output_bytes: int,
    context_bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run = _required_text(run_id, "NATIVE_RUN_ID_INVALID")
    cycle = _cycle_index(cycle_index)
    stage_id = _stage(stage)
    created = _required_text(created_at, "NATIVE_CREATED_AT_INVALID")
    input_ref = validate_artifact_binding(input_binding)
    input_schema = _required_text(input_schema_id, "NATIVE_INPUT_SCHEMA_INVALID")
    output_schema = _required_text(
        expected_output_schema_id, "NATIVE_OUTPUT_SCHEMA_INVALID"
    )
    if (
        not isinstance(max_output_bytes, int)
        or isinstance(max_output_bytes, bool)
        or max_output_bytes < 1
    ):
        raise NativeAgentTransportError("NATIVE_OUTPUT_BUDGET_INVALID")
    context = dict(context_bindings or {})
    if set(context) - {"market_snapshot_digest", "evaluation_digest"}:
        raise NativeAgentTransportError("NATIVE_REQUEST_CONTEXT_INVALID")
    for value in context.values():
        _sha256(value, "NATIVE_REQUEST_CONTEXT_INVALID")
    request_id = canonical_digest(
        {
            "run_id": run,
            "cycle_index": cycle,
            "stage": stage_id,
            "input_digest": input_ref["semantic_digest"],
            "expected_output_schema_id": output_schema,
            "context_bindings": context,
        }
    )
    document = {
            "schema_id": "native_codex_agent_request",
            "schema_version": "1.0.0",
            "request_id": request_id,
            "run_id": run,
            "cycle_index": cycle,
            "stage": stage_id,
            "created_at": created,
            "input_binding": input_ref,
            "input_schema_id": input_schema,
            "expected_output_schema_id": output_schema,
            "max_output_bytes": max_output_bytes,
            "agent_id": NATIVE_AGENT_ID,
            "evidence_level": NATIVE_EVIDENCE_LEVEL,
            "chat_history_is_authority": False,
            "controller_checkpoint_write_forbidden": True,
            "accepted_state_write_forbidden": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        }
    document.update(context)
    return self_digest(document, "native_agent_request_digest")


def validate_native_agent_request(request: Mapping[str, Any]) -> dict[str, Any]:
    try:
        verify_self_digest(request, "native_agent_request_digest")
    except ValueError as exc:
        raise NativeAgentTransportError("NATIVE_REQUEST_DIGEST_INVALID") from exc
    if (
        request.get("schema_id") != "native_codex_agent_request"
        or request.get("schema_version") != "1.0.0"
        or request.get("agent_id") != NATIVE_AGENT_ID
        or request.get("evidence_level") != NATIVE_EVIDENCE_LEVEL
        or request.get("chat_history_is_authority") is not False
        or request.get("controller_checkpoint_write_forbidden") is not True
        or request.get("accepted_state_write_forbidden") is not True
        or request.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
    ):
        raise NativeAgentTransportError("NATIVE_REQUEST_CONTRACT_INVALID")
    _required_text(request.get("run_id"), "NATIVE_RUN_ID_INVALID")
    _cycle_index(request.get("cycle_index"))
    _stage(request.get("stage"))
    _required_text(request.get("created_at"), "NATIVE_CREATED_AT_INVALID")
    _required_text(request.get("input_schema_id"), "NATIVE_INPUT_SCHEMA_INVALID")
    output_schema = _required_text(
        request.get("expected_output_schema_id"), "NATIVE_OUTPUT_SCHEMA_INVALID"
    )
    binding = validate_artifact_binding(request.get("input_binding", {}))
    if (
        not isinstance(request.get("max_output_bytes"), int)
        or isinstance(request.get("max_output_bytes"), bool)
        or int(request["max_output_bytes"]) < 1
    ):
        raise NativeAgentTransportError("NATIVE_OUTPUT_BUDGET_INVALID")
    context = {
        key: request[key]
        for key in ("market_snapshot_digest", "evaluation_digest")
        if key in request
    }
    for value in context.values():
        _sha256(value, "NATIVE_REQUEST_CONTEXT_INVALID")
    expected_id = canonical_digest(
        {
            "run_id": request["run_id"],
            "cycle_index": request["cycle_index"],
            "stage": request["stage"],
            "input_digest": binding["semantic_digest"],
            "expected_output_schema_id": output_schema,
            "context_bindings": context,
        }
    )
    if request.get("request_id") != expected_id:
        raise NativeAgentTransportError("NATIVE_REQUEST_ID_INVALID")
    return dict(request)


def build_native_agent_claim(
    *, request: Mapping[str, Any], claim_id: str, claimed_at: str
) -> dict[str, Any]:
    validated = validate_native_agent_request(request)
    return self_digest(
        {
            "schema_id": "native_codex_agent_claim",
            "schema_version": "1.0.0",
            "request_id": validated["request_id"],
            "native_agent_request_digest": validated[
                "native_agent_request_digest"
            ],
            "run_id": validated["run_id"],
            "cycle_index": validated["cycle_index"],
            "stage": validated["stage"],
            "claim_id": _required_text(claim_id, "NATIVE_CLAIM_ID_INVALID"),
            "claimed_at": _required_text(
                claimed_at, "NATIVE_CLAIMED_AT_INVALID"
            ),
            "claimant_id": NATIVE_AGENT_ID,
            "single_claimant": True,
            "chat_history_is_authority": False,
        },
        "native_agent_claim_digest",
    )


def validate_native_agent_claim(
    *, request: Mapping[str, Any], claim: Mapping[str, Any]
) -> dict[str, Any]:
    validated_request = validate_native_agent_request(request)
    try:
        verify_self_digest(claim, "native_agent_claim_digest")
    except ValueError as exc:
        raise NativeAgentTransportError("NATIVE_CLAIM_DIGEST_INVALID") from exc
    if (
        claim.get("schema_id") != "native_codex_agent_claim"
        or claim.get("schema_version") != "1.0.0"
        or claim.get("request_id") != validated_request["request_id"]
        or claim.get("native_agent_request_digest")
        != validated_request["native_agent_request_digest"]
        or claim.get("run_id") != validated_request["run_id"]
        or claim.get("cycle_index") != validated_request["cycle_index"]
        or claim.get("stage") != validated_request["stage"]
        or claim.get("claimant_id") != NATIVE_AGENT_ID
        or claim.get("single_claimant") is not True
        or claim.get("chat_history_is_authority") is not False
    ):
        raise NativeAgentTransportError("NATIVE_CLAIM_BINDING_MISMATCH")
    _required_text(claim.get("claim_id"), "NATIVE_CLAIM_ID_INVALID")
    _required_text(claim.get("claimed_at"), "NATIVE_CLAIMED_AT_INVALID")
    return dict(claim)


def _validate_public_analysis(value: object) -> None:
    if not isinstance(value, Mapping):
        raise NativeAgentTransportError("NATIVE_PROPOSAL_ANALYSIS_INVALID")
    for field in (
        "hypothesis",
        "expectation_update",
        "falsifier",
        "next_observation",
    ):
        _required_text(value.get(field), f"NATIVE_PROPOSAL_{field.upper()}_INVALID")
    for field in ("facts", "unknowns"):
        rows = value.get(field)
        if (
            not isinstance(rows, list)
            or not rows
            or any(not isinstance(row, str) or not row.strip() for row in rows)
        ):
            raise NativeAgentTransportError(
                f"NATIVE_PROPOSAL_{field.upper()}_INVALID"
            )


def validate_native_payload(
    *, request: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    validated_request = validate_native_agent_request(request)
    if not isinstance(payload, Mapping):
        raise NativeAgentTransportError("NATIVE_PAYLOAD_INVALID")
    expected_schema = validated_request["expected_output_schema_id"]
    if payload.get("schema_id") != expected_schema:
        raise NativeAgentTransportError("NATIVE_PAYLOAD_SCHEMA_MISMATCH")
    if (
        payload.get("schema_version") != "1.0.0"
        or payload.get("run_id") != validated_request["run_id"]
        or payload.get("cycle_index") != validated_request["cycle_index"]
        or payload.get("input_digest")
        != validated_request["input_binding"]["semantic_digest"]
        or payload.get("private_chain_of_thought_recorded") is not False
    ):
        raise NativeAgentTransportError("NATIVE_PAYLOAD_BINDING_MISMATCH")
    if expected_schema in {
        "native_codex_market_proposal_payload",
        "native_codex_market_deliberation_payload",
    }:
        try:
            return validate_native_market_payload(
                request=validated_request,
                payload=payload,
            )
        except NativeMarketCycleError as exc:
            raise NativeAgentTransportError(str(exc)) from exc
    if validated_request["stage"] == "PROPOSAL":
        if expected_schema != "native_codex_transport_proposal_payload":
            raise NativeAgentTransportError("NATIVE_PROPOSAL_SCHEMA_INVALID")
        _validate_public_analysis(payload.get("public_analysis"))
    else:
        if expected_schema != "native_codex_transport_deliberation_payload":
            raise NativeAgentTransportError("NATIVE_DELIBERATION_SCHEMA_INVALID")
        _sha256(
            payload.get("evaluation_digest"),
            "NATIVE_DELIBERATION_EVALUATION_DIGEST_INVALID",
        )
        if payload.get("selected_action") not in {"WAIT", "OBSERVE"}:
            raise NativeAgentTransportError("NATIVE_DELIBERATION_ACTION_INVALID")
        for field in ("reason", "opportunity_cost", "next_review_condition"):
            _required_text(
                payload.get(field),
                f"NATIVE_DELIBERATION_{field.upper()}_INVALID",
            )
    return dict(payload)


def build_native_agent_delivery(
    *,
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    payload: Mapping[str, Any],
    delivered_at: str,
) -> dict[str, Any]:
    validated_request = validate_native_agent_request(request)
    validated_claim = validate_native_agent_claim(
        request=validated_request, claim=claim
    )
    validated_payload = validate_native_payload(
        request=validated_request, payload=payload
    )
    payload_bytes = len(canonical_bytes(validated_payload))
    if payload_bytes > validated_request["max_output_bytes"]:
        raise NativeAgentTransportError("NATIVE_DELIVERY_TOO_LARGE")
    return self_digest(
        {
            "schema_id": "native_codex_agent_delivery",
            "schema_version": "1.0.0",
            "delivery_status": "COMPLETE",
            "finish_reason": "STOP",
            "truncated": False,
            "complete_json_object": True,
            "request_id": validated_request["request_id"],
            "native_agent_request_digest": validated_request[
                "native_agent_request_digest"
            ],
            "native_agent_claim_digest": validated_claim[
                "native_agent_claim_digest"
            ],
            "run_id": validated_request["run_id"],
            "cycle_index": validated_request["cycle_index"],
            "stage": validated_request["stage"],
            "input_digest": validated_request["input_binding"][
                "semantic_digest"
            ],
            "expected_output_schema_id": validated_request[
                "expected_output_schema_id"
            ],
            "payload": validated_payload,
            "payload_digest": canonical_digest(validated_payload),
            "payload_canonical_bytes": payload_bytes,
            "delivered_at": _required_text(
                delivered_at, "NATIVE_DELIVERED_AT_INVALID"
            ),
            "agent_id": NATIVE_AGENT_ID,
            "evidence_level": NATIVE_EVIDENCE_LEVEL,
            "durable_before_controller_consume": True,
            "service_model_attested": False,
            "exact_token_budget_attested": False,
            "private_chain_of_thought_recorded": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_agent_delivery_digest",
    )


def validate_native_agent_delivery(
    *,
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    delivery: Mapping[str, Any],
) -> dict[str, Any]:
    validated_request = validate_native_agent_request(request)
    validated_claim = validate_native_agent_claim(
        request=validated_request, claim=claim
    )
    try:
        verify_self_digest(delivery, "native_agent_delivery_digest")
    except ValueError as exc:
        raise NativeAgentTransportError("NATIVE_DELIVERY_DIGEST_INVALID") from exc
    if (
        delivery.get("schema_id") != "native_codex_agent_delivery"
        or delivery.get("schema_version") != "1.0.0"
        or delivery.get("delivery_status") != "COMPLETE"
        or delivery.get("finish_reason") != "STOP"
        or delivery.get("truncated") is not False
        or delivery.get("complete_json_object") is not True
        or delivery.get("request_id") != validated_request["request_id"]
        or delivery.get("native_agent_request_digest")
        != validated_request["native_agent_request_digest"]
        or delivery.get("native_agent_claim_digest")
        != validated_claim["native_agent_claim_digest"]
        or delivery.get("run_id") != validated_request["run_id"]
        or delivery.get("cycle_index") != validated_request["cycle_index"]
        or delivery.get("stage") != validated_request["stage"]
        or delivery.get("input_digest")
        != validated_request["input_binding"]["semantic_digest"]
        or delivery.get("expected_output_schema_id")
        != validated_request["expected_output_schema_id"]
        or delivery.get("agent_id") != NATIVE_AGENT_ID
        or delivery.get("evidence_level") != NATIVE_EVIDENCE_LEVEL
        or delivery.get("durable_before_controller_consume") is not True
        or delivery.get("service_model_attested") is not False
        or delivery.get("exact_token_budget_attested") is not False
        or delivery.get("private_chain_of_thought_recorded") is not False
        or delivery.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
    ):
        raise NativeAgentTransportError("NATIVE_DELIVERY_BINDING_MISMATCH")
    payload = validate_native_payload(
        request=validated_request, payload=delivery.get("payload", {})
    )
    payload_bytes = len(canonical_bytes(payload))
    if (
        delivery.get("payload_digest") != canonical_digest(payload)
        or delivery.get("payload_canonical_bytes") != payload_bytes
    ):
        raise NativeAgentTransportError("NATIVE_DELIVERY_PAYLOAD_MISMATCH")
    if payload_bytes > validated_request["max_output_bytes"]:
        raise NativeAgentTransportError("NATIVE_DELIVERY_TOO_LARGE")
    _required_text(delivery.get("delivered_at"), "NATIVE_DELIVERED_AT_INVALID")
    return dict(delivery)


def build_native_consume_receipt(
    *,
    request: Mapping[str, Any],
    request_binding: Mapping[str, Any],
    claim: Mapping[str, Any],
    claim_binding: Mapping[str, Any],
    delivery: Mapping[str, Any],
    delivery_binding: Mapping[str, Any],
    consumed_at: str,
    next_status: str,
) -> dict[str, Any]:
    validated_request = validate_native_agent_request(request)
    validated_claim = validate_native_agent_claim(
        request=validated_request, claim=claim
    )
    validated_delivery = validate_native_agent_delivery(
        request=validated_request,
        claim=validated_claim,
        delivery=delivery,
    )
    request_ref = validate_artifact_binding(request_binding)
    claim_ref = validate_artifact_binding(claim_binding)
    delivery_ref = validate_artifact_binding(delivery_binding)
    if (
        request_ref["semantic_digest"]
        != validated_request["native_agent_request_digest"]
        or claim_ref["semantic_digest"]
        != validated_claim["native_agent_claim_digest"]
        or delivery_ref["semantic_digest"]
        != validated_delivery["native_agent_delivery_digest"]
    ):
        raise NativeAgentTransportError("NATIVE_CONSUME_BINDING_MISMATCH")
    return self_digest(
        {
            "schema_id": "native_codex_transport_consume_receipt",
            "schema_version": "1.0.0",
            "run_id": validated_request["run_id"],
            "cycle_index": validated_request["cycle_index"],
            "stage": validated_request["stage"],
            "request_binding": request_ref,
            "claim_binding": claim_ref,
            "delivery_binding": delivery_ref,
            "payload_digest": validated_delivery["payload_digest"],
            "consumed_at": _required_text(
                consumed_at, "NATIVE_CONSUMED_AT_INVALID"
            ),
            "next_status": _required_text(
                next_status, "NATIVE_NEXT_STATUS_INVALID"
            ),
            "controller_consumed_durable_delivery": True,
            "agent_reinvocation_forbidden": True,
        },
        "native_transport_consume_receipt_digest",
    )


__all__ = [
    "NATIVE_AGENT_ID",
    "NATIVE_EVIDENCE_LEVEL",
    "NATIVE_STAGES",
    "NativeAgentTransportError",
    "build_native_agent_claim",
    "build_native_agent_delivery",
    "build_native_agent_request",
    "build_native_consume_receipt",
    "validate_artifact_binding",
    "validate_native_agent_claim",
    "validate_native_agent_delivery",
    "validate_native_agent_request",
    "validate_native_payload",
]
