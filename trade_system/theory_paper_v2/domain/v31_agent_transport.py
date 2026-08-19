"""Pure contracts for the V3.1 two-stage current-Codex transport.

The transport owns no market belief or accepted research state.  It only proves
that one PROPOSAL attempt and one post-preselection SELECTION attempt were
reserved before invocation and durably moved through
request -> claim -> delivery -> consume exactly once.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .agent_research_contract import verify_v31_agent_proposal
from .behavior_planning import seal_action_selection
from .contracts.canonical import canonical_digest, self_digest, verify_self_digest
from .v31_cycle_authoring import (
    AUTHORING_ENVELOPE_SCHEMA_ID,
    AUTHORING_PACKET_SCHEMA_ID,
    V31CycleAuthoringError,
    validate_v31_agent_open_analysis_envelope,
    validate_v31_proposal_authoring_packet,
)


class V31AgentTransportError(ValueError):
    """A V3.1 transport artifact violated its frozen boundary."""


V31_AGENT_ID = "CURRENT_CODEX_TASK"
V31_TRANSPORT_EVIDENCE_LEVEL = (
    "PRACTICAL_CODEX_V31_DURABLE_TWO_STAGE_TRANSPORT"
)
V31_TRANSPORT_STAGES = ("PROPOSAL", "SELECTION")
V31_LEGACY_PROPOSAL_TRANSPORT_CLASS = (
    "QUALIFICATION_LEGACY_SHAPE_NOT_RUN_READY"
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_FIELDS = (
    "account_access",
    "paper_trading",
    "live_trading",
    "order_submission",
    "credential_access",
    "funds_access",
)
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_ATTEMPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "attempt_id",
        "run_id",
        "cycle_index",
        "stage",
        "attempt_number",
        "max_attempts",
        "reserved_at",
        "checkpoint_digest_before_reservation",
        "reservation_precedes_agent_invocation",
        "retry_allowed",
        "chat_history_is_authority",
        *_EXECUTION_FIELDS,
        "external_execution_authority",
        "executable",
        "attempt_digest",
    }
)
_COMMON_REQUEST_FIELDS = {
    "schema_id",
    "schema_version",
    "request_id",
    "run_id",
    "cycle_index",
    "stage",
    "created_at",
    "attempt_digest",
    "expected_payload_schema_id",
    "agent_id",
    "max_attempts",
    "chat_history_is_authority",
    *_EXECUTION_FIELDS,
    "external_execution_authority",
    "executable",
    "request_digest",
}
_PROPOSAL_REQUEST_FIELDS = frozenset(
    {*_COMMON_REQUEST_FIELDS, "inputs_receipt_binding"}
)
_AUTHORING_PROPOSAL_REQUEST_FIELDS = frozenset(
    {*_COMMON_REQUEST_FIELDS, "authoring_packet_binding"}
)
_SELECTION_REQUEST_FIELDS = frozenset(
    {
        *_COMMON_REQUEST_FIELDS,
        "proposal_consume_binding",
        "preselection_binding",
        "action_evaluation_binding",
        "selectable_candidate_ids",
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "claim_id",
        "run_id",
        "cycle_index",
        "stage",
        "attempt_digest",
        "request_digest",
        "claimed_at",
        "claimant_id",
        "single_claim",
        "retry_allowed",
        "chat_history_is_authority",
        *_EXECUTION_FIELDS,
        "external_execution_authority",
        "executable",
        "claim_digest",
    }
)
_DELIVERY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "delivery_id",
        "run_id",
        "cycle_index",
        "stage",
        "attempt_digest",
        "request_digest",
        "claim_digest",
        "delivered_at",
        "payload_schema_id",
        "payload_digest_field",
        "payload_digest",
        "payload",
        "private_chain_of_thought_recorded",
        "retry_allowed",
        "chat_history_is_authority",
        *_EXECUTION_FIELDS,
        "external_execution_authority",
        "executable",
        "delivery_digest",
    }
)
_CONSUME_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "consume_id",
        "run_id",
        "cycle_index",
        "stage",
        "attempt_digest",
        "request_digest",
        "claim_digest",
        "delivery_digest",
        "payload_digest",
        "consumed_at",
        "validation_status",
        "retry_allowed",
        "chat_history_is_authority",
        *_EXECUTION_FIELDS,
        "external_execution_authority",
        "executable",
        "consume_digest",
    }
)
_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "stage",
        "failed_at",
        "failure_code",
        "attempt_digest",
        "request_digest",
        "claim_digest",
        "delivery_digest",
        "resume_allowed",
        "retry_allowed",
        "chat_history_is_authority",
        *_EXECUTION_FIELDS,
        "external_execution_authority",
        "executable",
        "failure_digest",
    }
)
_STAGE_EVIDENCE_FIELDS = frozenset(
    {
        "attempt_binding",
        "request_binding",
        "claim_binding",
        "delivery_binding",
        "consume_binding",
        "attempt_count",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "completed_at",
        "agent_id",
        "evidence_level",
        "stage_order",
        "stages",
        "chronology",
        "proposal_payload_digest",
        "selection_payload_digest",
        "attempt_limit_per_stage",
        "all_deliveries_consumed",
        "agent_output_is_execution_authority",
        "experiment_start_authority",
        "chat_history_is_authority",
        *_EXECUTION_FIELDS,
        "external_execution_authority",
        "executable",
        "transport_evidence_digest",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise V31AgentTransportError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31AgentTransportError(code)
    return value


def _timestamp(value: Any, code: str) -> str:
    value = _text(value, code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31AgentTransportError(code) from exc
    if parsed.tzinfo is None:
        raise V31AgentTransportError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31AgentTransportError(code)
    return value


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_timestamp(value, code).replace("Z", "+00:00"))


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise V31AgentTransportError("V31_TRANSPORT_CYCLE_INVALID")
    return value


def _stage(value: Any) -> str:
    value = _text(value, "V31_TRANSPORT_STAGE_INVALID")
    if value not in V31_TRANSPORT_STAGES:
        raise V31AgentTransportError("V31_TRANSPORT_STAGE_INVALID")
    return value


def _verify_self(document: Any, field: str, code: str) -> str:
    if not isinstance(document, Mapping):
        raise V31AgentTransportError(code)
    try:
        return verify_self_digest(document, field)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31AgentTransportError(code) from exc


def _execution_boundary(document: Mapping[str, Any], code: str) -> None:
    if (
        any(document.get(field) is not False for field in _EXECUTION_FIELDS)
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("chat_history_is_authority") is not False
    ):
        raise V31AgentTransportError(code)


def _boundary_fields() -> dict[str, Any]:
    return {
        **{field: False for field in _EXECUTION_FIELDS},
        "chat_history_is_authority": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def validate_v31_transport_binding(
    binding: Any,
    *,
    expected_schema_id: str | None = None,
    expected_digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_FIELDS:
        raise V31AgentTransportError("V31_TRANSPORT_BINDING_INVALID")
    relative_ref = _text(
        binding.get("relative_ref"), "V31_TRANSPORT_BINDING_INVALID"
    )
    path = PurePosixPath(relative_ref)
    if (
        "\\" in relative_ref
        or path.as_posix() != relative_ref
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31AgentTransportError("V31_TRANSPORT_BINDING_INVALID")
    schema_id = _text(binding.get("schema_id"), "V31_TRANSPORT_BINDING_INVALID")
    digest_field = _text(
        binding.get("digest_field"), "V31_TRANSPORT_BINDING_INVALID"
    )
    if (
        expected_schema_id is not None
        and schema_id != expected_schema_id
    ) or (
        expected_digest_field is not None
        and digest_field != expected_digest_field
    ):
        raise V31AgentTransportError("V31_TRANSPORT_BINDING_INVALID")
    return {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": _digest(
            binding.get("semantic_digest"), "V31_TRANSPORT_BINDING_INVALID"
        ),
        "physical_sha256": _digest(
            binding.get("physical_sha256"), "V31_TRANSPORT_BINDING_INVALID"
        ),
    }


def reserve_v31_agent_attempt(
    *,
    run_id: str,
    cycle_index: int,
    stage: str,
    reserved_at: str,
    checkpoint_digest_before_reservation: str,
) -> dict[str, Any]:
    identity = {
        "run_id": _text(run_id, "V31_TRANSPORT_RUN_ID_INVALID"),
        "cycle_index": _cycle(cycle_index),
        "stage": _stage(stage),
        "attempt_number": 1,
    }
    return self_digest(
        {
            "schema_id": "theory_paper_v31_agent_attempt",
            "schema_version": "1.0.0",
            "attempt_id": canonical_digest(identity),
            **identity,
            "max_attempts": 1,
            "reserved_at": _timestamp(
                reserved_at, "V31_TRANSPORT_ATTEMPT_TIME_INVALID"
            ),
            "checkpoint_digest_before_reservation": _digest(
                checkpoint_digest_before_reservation,
                "V31_TRANSPORT_ATTEMPT_CHECKPOINT_INVALID",
            ),
            "reservation_precedes_agent_invocation": True,
            "retry_allowed": False,
            **_boundary_fields(),
        },
        "attempt_digest",
    )


def validate_v31_agent_attempt(document: Mapping[str, Any]) -> str:
    digest = _verify_self(
        document, "attempt_digest", "V31_TRANSPORT_ATTEMPT_DIGEST_INVALID"
    )
    if (
        set(document) != _ATTEMPT_FIELDS
        or document.get("schema_id") != "theory_paper_v31_agent_attempt"
        or document.get("schema_version") != "1.0.0"
        or document.get("attempt_number") != 1
        or document.get("max_attempts") != 1
        or document.get("reservation_precedes_agent_invocation") is not True
        or document.get("retry_allowed") is not False
    ):
        raise V31AgentTransportError("V31_TRANSPORT_ATTEMPT_INVALID")
    run_id = _text(document.get("run_id"), "V31_TRANSPORT_RUN_ID_INVALID")
    cycle = _cycle(document.get("cycle_index"))
    stage = _stage(document.get("stage"))
    _timestamp(document.get("reserved_at"), "V31_TRANSPORT_ATTEMPT_TIME_INVALID")
    _digest(
        document.get("checkpoint_digest_before_reservation"),
        "V31_TRANSPORT_ATTEMPT_CHECKPOINT_INVALID",
    )
    if document.get("attempt_id") != canonical_digest(
        {
            "run_id": run_id,
            "cycle_index": cycle,
            "stage": stage,
            "attempt_number": 1,
        }
    ):
        raise V31AgentTransportError("V31_TRANSPORT_ATTEMPT_ID_INVALID")
    _execution_boundary(document, "V31_TRANSPORT_ATTEMPT_BOUNDARY_INVALID")
    return digest


def build_v31_agent_request(
    *,
    attempt: Mapping[str, Any],
    created_at: str,
    inputs_receipt_binding: Mapping[str, Any] | None = None,
    authoring_packet_binding: Mapping[str, Any] | None = None,
    proposal_consume_binding: Mapping[str, Any] | None = None,
    preselection_binding: Mapping[str, Any] | None = None,
    action_evaluation_binding: Mapping[str, Any] | None = None,
    selectable_candidate_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    attempt_digest = validate_v31_agent_attempt(attempt)
    stage = attempt["stage"]
    base = {
        "schema_id": "theory_paper_v31_agent_request",
        "schema_version": "1.0.0",
        "run_id": attempt["run_id"],
        "cycle_index": attempt["cycle_index"],
        "stage": stage,
        "created_at": _timestamp(
            created_at, "V31_TRANSPORT_REQUEST_TIME_INVALID"
        ),
        "attempt_digest": attempt_digest,
        "expected_payload_schema_id": (
            (
                AUTHORING_ENVELOPE_SCHEMA_ID
                if authoring_packet_binding is not None
                else "theory_paper_v2_v31_agent_proposal"
            )
            if stage == "PROPOSAL"
            else "theory_paper_v2_v31_action_selection"
        ),
        "agent_id": V31_AGENT_ID,
        "max_attempts": 1,
        **_boundary_fields(),
    }
    if stage == "PROPOSAL":
        if any(
            value is not None
            for value in (
                proposal_consume_binding,
                preselection_binding,
                action_evaluation_binding,
                selectable_candidate_ids,
            )
        ) or ((inputs_receipt_binding is None) == (authoring_packet_binding is None)):
            raise V31AgentTransportError("V31_PROPOSAL_REQUEST_SELECTED_FIRST")
        if authoring_packet_binding is not None:
            base["authoring_packet_binding"] = validate_v31_transport_binding(
                authoring_packet_binding,
                expected_schema_id=AUTHORING_PACKET_SCHEMA_ID,
                expected_digest_field="authoring_packet_digest",
            )
        else:
            base["inputs_receipt_binding"] = validate_v31_transport_binding(
                inputs_receipt_binding,
                expected_schema_id="theory_paper_v2_v31_inputs_receipt",
                expected_digest_field="inputs_receipt_digest",
            )
    else:
        if inputs_receipt_binding is not None or authoring_packet_binding is not None:
            raise V31AgentTransportError("V31_SELECTION_REQUEST_CONTEXT_INVALID")
        base["proposal_consume_binding"] = validate_v31_transport_binding(
            proposal_consume_binding,
            expected_schema_id="theory_paper_v31_agent_consume_receipt",
            expected_digest_field="consume_digest",
        )
        base["preselection_binding"] = validate_v31_transport_binding(
            preselection_binding,
            expected_schema_id="theory_paper_v2_v31_cycle_preselection",
            expected_digest_field="preselection_digest",
        )
        base["action_evaluation_binding"] = validate_v31_transport_binding(
            action_evaluation_binding,
            expected_schema_id="theory_paper_v2_v31_complete_action_evaluation",
            expected_digest_field="action_evaluation_digest",
        )
        ids = list(selectable_candidate_ids or ())
        if (
            not ids
            or len(ids) != len(set(ids))
            or any(not isinstance(value, str) or not value.strip() for value in ids)
        ):
            raise V31AgentTransportError("V31_SELECTION_SELECTABLE_SET_INVALID")
        base["selectable_candidate_ids"] = ids
    base["request_id"] = canonical_digest(
        {
            "run_id": base["run_id"],
            "cycle_index": base["cycle_index"],
            "stage": stage,
            "attempt_digest": attempt_digest,
            "request_context": {
                key: value
                for key, value in base.items()
                if key.endswith("_binding") or key == "selectable_candidate_ids"
            },
        }
    )
    return self_digest(base, "request_digest")


def validate_v31_agent_request(
    document: Mapping[str, Any], *, attempt: Mapping[str, Any]
) -> str:
    digest = _verify_self(
        document, "request_digest", "V31_TRANSPORT_REQUEST_DIGEST_INVALID"
    )
    attempt_digest = validate_v31_agent_attempt(attempt)
    stage = attempt["stage"]
    expected_fields = (
        (
            _AUTHORING_PROPOSAL_REQUEST_FIELDS
            if document.get("expected_payload_schema_id")
            == AUTHORING_ENVELOPE_SCHEMA_ID
            else _PROPOSAL_REQUEST_FIELDS
        )
        if stage == "PROPOSAL"
        else _SELECTION_REQUEST_FIELDS
    )
    expected_payload_schema_id = (
        document.get("expected_payload_schema_id")
        if stage == "PROPOSAL"
        else "theory_paper_v2_v31_action_selection"
    )
    if (
        set(document) != expected_fields
        or document.get("schema_id") != "theory_paper_v31_agent_request"
        or document.get("schema_version") != "1.0.0"
        or document.get("run_id") != attempt.get("run_id")
        or document.get("cycle_index") != attempt.get("cycle_index")
        or document.get("stage") != stage
        or document.get("attempt_digest") != attempt_digest
        or document.get("agent_id") != V31_AGENT_ID
        or document.get("max_attempts") != 1
        or document.get("expected_payload_schema_id")
        != expected_payload_schema_id
        or (
            stage == "PROPOSAL"
            and expected_payload_schema_id
            not in {
                "theory_paper_v2_v31_agent_proposal",
                AUTHORING_ENVELOPE_SCHEMA_ID,
            }
        )
    ):
        raise V31AgentTransportError("V31_TRANSPORT_REQUEST_INVALID")
    if _moment(
        document.get("created_at"), "V31_TRANSPORT_REQUEST_TIME_INVALID"
    ) < _moment(
        attempt.get("reserved_at"), "V31_TRANSPORT_ATTEMPT_TIME_INVALID"
    ):
        raise V31AgentTransportError("V31_TRANSPORT_REQUEST_PRECEDES_ATTEMPT")
    if stage == "PROPOSAL":
        if expected_payload_schema_id == AUTHORING_ENVELOPE_SCHEMA_ID:
            validate_v31_transport_binding(
                document.get("authoring_packet_binding"),
                expected_schema_id=AUTHORING_PACKET_SCHEMA_ID,
                expected_digest_field="authoring_packet_digest",
            )
        else:
            validate_v31_transport_binding(
                document.get("inputs_receipt_binding"),
                expected_schema_id="theory_paper_v2_v31_inputs_receipt",
                expected_digest_field="inputs_receipt_digest",
            )
    else:
        validate_v31_transport_binding(
            document.get("proposal_consume_binding"),
            expected_schema_id="theory_paper_v31_agent_consume_receipt",
            expected_digest_field="consume_digest",
        )
        validate_v31_transport_binding(
            document.get("preselection_binding"),
            expected_schema_id="theory_paper_v2_v31_cycle_preselection",
            expected_digest_field="preselection_digest",
        )
        validate_v31_transport_binding(
            document.get("action_evaluation_binding"),
            expected_schema_id="theory_paper_v2_v31_complete_action_evaluation",
            expected_digest_field="action_evaluation_digest",
        )
        ids = document.get("selectable_candidate_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or len(ids) != len(set(ids))
            or any(not isinstance(value, str) or not value.strip() for value in ids)
        ):
            raise V31AgentTransportError("V31_SELECTION_SELECTABLE_SET_INVALID")
    context = {
        key: value
        for key, value in document.items()
        if key.endswith("_binding") or key == "selectable_candidate_ids"
    }
    if document.get("request_id") != canonical_digest(
        {
            "run_id": document["run_id"],
            "cycle_index": document["cycle_index"],
            "stage": stage,
            "attempt_digest": attempt_digest,
            "request_context": context,
        }
    ):
        raise V31AgentTransportError("V31_TRANSPORT_REQUEST_ID_INVALID")
    _execution_boundary(document, "V31_TRANSPORT_REQUEST_BOUNDARY_INVALID")
    return digest


def build_v31_agent_claim(
    *, request: Mapping[str, Any], attempt: Mapping[str, Any], claimed_at: str
) -> dict[str, Any]:
    request_digest = validate_v31_agent_request(request, attempt=attempt)
    attempt_digest = validate_v31_agent_attempt(attempt)
    identity = {
        "run_id": request["run_id"],
        "cycle_index": request["cycle_index"],
        "stage": request["stage"],
        "attempt_digest": attempt_digest,
        "request_digest": request_digest,
    }
    return self_digest(
        {
            "schema_id": "theory_paper_v31_agent_claim",
            "schema_version": "1.0.0",
            "claim_id": canonical_digest(identity),
            **identity,
            "claimed_at": _timestamp(
                claimed_at, "V31_TRANSPORT_CLAIM_TIME_INVALID"
            ),
            "claimant_id": V31_AGENT_ID,
            "single_claim": True,
            "retry_allowed": False,
            **_boundary_fields(),
        },
        "claim_digest",
    )


def validate_v31_agent_claim(
    document: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> str:
    digest = _verify_self(
        document, "claim_digest", "V31_TRANSPORT_CLAIM_DIGEST_INVALID"
    )
    request_digest = validate_v31_agent_request(request, attempt=attempt)
    attempt_digest = validate_v31_agent_attempt(attempt)
    identity = {
        "run_id": request["run_id"],
        "cycle_index": request["cycle_index"],
        "stage": request["stage"],
        "attempt_digest": attempt_digest,
        "request_digest": request_digest,
    }
    if (
        set(document) != _CLAIM_FIELDS
        or document.get("schema_id") != "theory_paper_v31_agent_claim"
        or document.get("schema_version") != "1.0.0"
        or any(document.get(key) != value for key, value in identity.items())
        or document.get("claim_id") != canonical_digest(identity)
        or document.get("claimant_id") != V31_AGENT_ID
        or document.get("single_claim") is not True
        or document.get("retry_allowed") is not False
    ):
        raise V31AgentTransportError("V31_TRANSPORT_CLAIM_INVALID")
    if _moment(
        document.get("claimed_at"), "V31_TRANSPORT_CLAIM_TIME_INVALID"
    ) < _moment(
        request.get("created_at"), "V31_TRANSPORT_REQUEST_TIME_INVALID"
    ):
        raise V31AgentTransportError("V31_TRANSPORT_CLAIM_PRECEDES_REQUEST")
    _execution_boundary(document, "V31_TRANSPORT_CLAIM_BOUNDARY_INVALID")
    return digest


def build_v31_agent_delivery(
    *,
    request: Mapping[str, Any],
    attempt: Mapping[str, Any],
    claim: Mapping[str, Any],
    payload: Mapping[str, Any],
    delivered_at: str,
    inputs_receipt: Mapping[str, Any] | None = None,
    authoring_packet: Mapping[str, Any] | None = None,
    action_evaluation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    request_digest = validate_v31_agent_request(request, attempt=attempt)
    attempt_digest = validate_v31_agent_attempt(attempt)
    claim_digest = validate_v31_agent_claim(
        claim, request=request, attempt=attempt
    )
    stage = request["stage"]
    if stage == "PROPOSAL":
        if action_evaluation is not None or (
            (inputs_receipt is None) == (authoring_packet is None)
        ):
            raise V31AgentTransportError("V31_PROPOSAL_DELIVERY_CONTEXT_INVALID")
        if authoring_packet is not None:
            if request.get("expected_payload_schema_id") != AUTHORING_ENVELOPE_SCHEMA_ID:
                raise V31AgentTransportError(
                    "V31_PROPOSAL_DELIVERY_CONTEXT_INVALID"
                )
            try:
                validate_v31_proposal_authoring_packet(authoring_packet)
                payload_digest = validate_v31_agent_open_analysis_envelope(
                    payload, authoring_packet=authoring_packet
                )
            except V31CycleAuthoringError as exc:
                raise V31AgentTransportError(
                    "V31_AUTHORING_ENVELOPE_PAYLOAD_INVALID"
                ) from exc
            payload_digest_field = "agent_authoring_envelope_digest"
        else:
            if (
                request.get("expected_payload_schema_id")
                != "theory_paper_v2_v31_agent_proposal"
            ):
                raise V31AgentTransportError(
                    "V31_PROPOSAL_DELIVERY_CONTEXT_INVALID"
                )
            payload_digest = verify_v31_agent_proposal(
                payload, inputs_receipt=inputs_receipt
            )
            payload_digest_field = "agent_proposal_digest"
    else:
        if (
            action_evaluation is None
            or inputs_receipt is not None
            or authoring_packet is not None
        ):
            raise V31AgentTransportError("V31_SELECTION_DELIVERY_CONTEXT_INVALID")
        if payload.get("selected_candidate_id") not in request[
            "selectable_candidate_ids"
        ]:
            raise V31AgentTransportError("V31_SELECTION_NOT_SELECTABLE")
        try:
            rebuilt = seal_action_selection(
                evaluation=action_evaluation,
                selected_candidate_id=payload["selected_candidate_id"],
                reason=payload["reason"],
                alternative_explanations=payload["alternative_explanations"],
                failure_conditions=payload["failure_conditions"],
                next_review_at=payload["next_review_at"],
                selected_at=payload["selected_at"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V31AgentTransportError("V31_SELECTION_PAYLOAD_INVALID") from exc
        if rebuilt != dict(payload):
            raise V31AgentTransportError("V31_SELECTION_PAYLOAD_INVALID")
        payload_digest = _verify_self(
            payload,
            "action_selection_digest",
            "V31_SELECTION_PAYLOAD_DIGEST_INVALID",
        )
        payload_digest_field = "action_selection_digest"
    identity = {
        "run_id": request["run_id"],
        "cycle_index": request["cycle_index"],
        "stage": stage,
        "attempt_digest": attempt_digest,
        "request_digest": request_digest,
        "claim_digest": claim_digest,
        "payload_digest": payload_digest,
    }
    return self_digest(
        {
            "schema_id": "theory_paper_v31_agent_delivery",
            "schema_version": "1.0.0",
            "delivery_id": canonical_digest(identity),
            **{key: value for key, value in identity.items() if key != "payload_digest"},
            "delivered_at": _timestamp(
                delivered_at, "V31_TRANSPORT_DELIVERY_TIME_INVALID"
            ),
            "payload_schema_id": request["expected_payload_schema_id"],
            "payload_digest_field": payload_digest_field,
            "payload_digest": payload_digest,
            "payload": dict(payload),
            "private_chain_of_thought_recorded": False,
            "retry_allowed": False,
            **_boundary_fields(),
        },
        "delivery_digest",
    )


def validate_v31_agent_delivery(
    document: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    attempt: Mapping[str, Any],
    claim: Mapping[str, Any],
    inputs_receipt: Mapping[str, Any] | None = None,
    authoring_packet: Mapping[str, Any] | None = None,
    action_evaluation: Mapping[str, Any] | None = None,
) -> str:
    digest = _verify_self(
        document, "delivery_digest", "V31_TRANSPORT_DELIVERY_DIGEST_INVALID"
    )
    rebuilt = build_v31_agent_delivery(
        request=request,
        attempt=attempt,
        claim=claim,
        payload=document.get("payload", {}),
        delivered_at=document.get("delivered_at"),
        inputs_receipt=inputs_receipt,
        authoring_packet=authoring_packet,
        action_evaluation=action_evaluation,
    )
    if set(document) != _DELIVERY_FIELDS or rebuilt != dict(document):
        raise V31AgentTransportError("V31_TRANSPORT_DELIVERY_INVALID")
    if _moment(
        document.get("delivered_at"), "V31_TRANSPORT_DELIVERY_TIME_INVALID"
    ) < _moment(
        claim.get("claimed_at"), "V31_TRANSPORT_CLAIM_TIME_INVALID"
    ):
        raise V31AgentTransportError("V31_TRANSPORT_DELIVERY_PRECEDES_CLAIM")
    _execution_boundary(document, "V31_TRANSPORT_DELIVERY_BOUNDARY_INVALID")
    return digest


def build_v31_consume_receipt(
    *,
    request: Mapping[str, Any],
    attempt: Mapping[str, Any],
    claim: Mapping[str, Any],
    delivery: Mapping[str, Any],
    consumed_at: str,
    inputs_receipt: Mapping[str, Any] | None = None,
    authoring_packet: Mapping[str, Any] | None = None,
    action_evaluation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    delivery_digest = validate_v31_agent_delivery(
        delivery,
        request=request,
        attempt=attempt,
        claim=claim,
        inputs_receipt=inputs_receipt,
        authoring_packet=authoring_packet,
        action_evaluation=action_evaluation,
    )
    identity = {
        "run_id": request["run_id"],
        "cycle_index": request["cycle_index"],
        "stage": request["stage"],
        "attempt_digest": attempt["attempt_digest"],
        "request_digest": request["request_digest"],
        "claim_digest": claim["claim_digest"],
        "delivery_digest": delivery_digest,
        "payload_digest": delivery["payload_digest"],
    }
    return self_digest(
        {
            "schema_id": "theory_paper_v31_agent_consume_receipt",
            "schema_version": "1.0.0",
            "consume_id": canonical_digest(identity),
            **identity,
            "consumed_at": _timestamp(
                consumed_at, "V31_TRANSPORT_CONSUME_TIME_INVALID"
            ),
            "validation_status": "SEMANTIC_AND_PHYSICAL_BINDINGS_VERIFIED",
            "retry_allowed": False,
            **_boundary_fields(),
        },
        "consume_digest",
    )


def validate_v31_consume_receipt(
    document: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    attempt: Mapping[str, Any],
    claim: Mapping[str, Any],
    delivery: Mapping[str, Any],
    inputs_receipt: Mapping[str, Any] | None = None,
    authoring_packet: Mapping[str, Any] | None = None,
    action_evaluation: Mapping[str, Any] | None = None,
) -> str:
    digest = _verify_self(
        document, "consume_digest", "V31_TRANSPORT_CONSUME_DIGEST_INVALID"
    )
    rebuilt = build_v31_consume_receipt(
        request=request,
        attempt=attempt,
        claim=claim,
        delivery=delivery,
        consumed_at=document.get("consumed_at"),
        inputs_receipt=inputs_receipt,
        authoring_packet=authoring_packet,
        action_evaluation=action_evaluation,
    )
    if set(document) != _CONSUME_FIELDS or rebuilt != dict(document):
        raise V31AgentTransportError("V31_TRANSPORT_CONSUME_INVALID")
    if _moment(
        document.get("consumed_at"), "V31_TRANSPORT_CONSUME_TIME_INVALID"
    ) < _moment(
        delivery.get("delivered_at"), "V31_TRANSPORT_DELIVERY_TIME_INVALID"
    ):
        raise V31AgentTransportError("V31_TRANSPORT_CONSUME_PRECEDES_DELIVERY")
    _execution_boundary(document, "V31_TRANSPORT_CONSUME_BOUNDARY_INVALID")
    return digest


def build_v31_transport_failure(
    *,
    run_id: str,
    cycle_index: int,
    stage: str,
    failed_at: str,
    failure_code: str,
    attempt_digest: str | None,
    request_digest: str | None,
    claim_digest: str | None,
    delivery_digest: str | None,
) -> dict[str, Any]:
    for value in (
        attempt_digest,
        request_digest,
        claim_digest,
        delivery_digest,
    ):
        if value is not None:
            _digest(value, "V31_TRANSPORT_FAILURE_BINDING_INVALID")
    return self_digest(
        {
            "schema_id": "theory_paper_v31_agent_transport_failure",
            "schema_version": "1.0.0",
            "run_id": _text(run_id, "V31_TRANSPORT_RUN_ID_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "stage": _stage(stage),
            "failed_at": _timestamp(
                failed_at, "V31_TRANSPORT_FAILURE_TIME_INVALID"
            ),
            "failure_code": _text(
                failure_code, "V31_TRANSPORT_FAILURE_CODE_INVALID"
            ),
            "attempt_digest": attempt_digest,
            "request_digest": request_digest,
            "claim_digest": claim_digest,
            "delivery_digest": delivery_digest,
            "resume_allowed": False,
            "retry_allowed": False,
            **_boundary_fields(),
        },
        "failure_digest",
    )


def validate_v31_transport_failure(document: Mapping[str, Any]) -> str:
    digest = _verify_self(
        document, "failure_digest", "V31_TRANSPORT_FAILURE_DIGEST_INVALID"
    )
    if (
        set(document) != _FAILURE_FIELDS
        or document.get("schema_id")
        != "theory_paper_v31_agent_transport_failure"
        or document.get("schema_version") != "1.0.0"
        or document.get("resume_allowed") is not False
        or document.get("retry_allowed") is not False
    ):
        raise V31AgentTransportError("V31_TRANSPORT_FAILURE_INVALID")
    _text(document.get("run_id"), "V31_TRANSPORT_RUN_ID_INVALID")
    _cycle(document.get("cycle_index"))
    _stage(document.get("stage"))
    _timestamp(document.get("failed_at"), "V31_TRANSPORT_FAILURE_TIME_INVALID")
    _text(document.get("failure_code"), "V31_TRANSPORT_FAILURE_CODE_INVALID")
    for field in (
        "attempt_digest",
        "request_digest",
        "claim_digest",
        "delivery_digest",
    ):
        if document.get(field) is not None:
            _digest(document[field], "V31_TRANSPORT_FAILURE_BINDING_INVALID")
    _execution_boundary(document, "V31_TRANSPORT_FAILURE_BOUNDARY_INVALID")
    return digest


def seal_v31_transport_evidence(
    *,
    run_id: str,
    cycle_index: int,
    completed_at: str,
    stages: Mapping[str, Mapping[str, Any]],
    proposal_payload_digest: str,
    selection_payload_digest: str,
) -> dict[str, Any]:
    if not isinstance(stages, Mapping) or tuple(stages) != V31_TRANSPORT_STAGES:
        raise V31AgentTransportError("V31_TRANSPORT_EVIDENCE_STAGES_INVALID")
    normalized: dict[str, Any] = {}
    chronology: list[dict[str, Any]] = []
    expected = {
        "attempt_binding": ("theory_paper_v31_agent_attempt", "attempt_digest"),
        "request_binding": ("theory_paper_v31_agent_request", "request_digest"),
        "claim_binding": ("theory_paper_v31_agent_claim", "claim_digest"),
        "delivery_binding": ("theory_paper_v31_agent_delivery", "delivery_digest"),
        "consume_binding": (
            "theory_paper_v31_agent_consume_receipt",
            "consume_digest",
        ),
    }
    sequence = 0
    for stage in V31_TRANSPORT_STAGES:
        row = stages[stage]
        if not isinstance(row, Mapping) or set(row) != _STAGE_EVIDENCE_FIELDS:
            raise V31AgentTransportError("V31_TRANSPORT_EVIDENCE_STAGE_INVALID")
        if row.get("attempt_count") != 1:
            raise V31AgentTransportError("V31_TRANSPORT_EVIDENCE_ATTEMPT_INVALID")
        normalized_row: dict[str, Any] = {"attempt_count": 1}
        for field, (schema_id, digest_field) in expected.items():
            binding = validate_v31_transport_binding(
                row.get(field),
                expected_schema_id=schema_id,
                expected_digest_field=digest_field,
            )
            normalized_row[field] = binding
            sequence += 1
            chronology.append(
                {
                    "sequence": sequence,
                    "stage": stage,
                    "kind": field.removesuffix("_binding").upper(),
                    "semantic_digest": binding["semantic_digest"],
                }
            )
        normalized[stage] = normalized_row
    return self_digest(
        {
            "schema_id": "theory_paper_v31_agent_transport_evidence",
            "schema_version": "1.0.0",
            "run_id": _text(run_id, "V31_TRANSPORT_RUN_ID_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "completed_at": _timestamp(
                completed_at, "V31_TRANSPORT_EVIDENCE_TIME_INVALID"
            ),
            "agent_id": V31_AGENT_ID,
            "evidence_level": V31_TRANSPORT_EVIDENCE_LEVEL,
            "stage_order": list(V31_TRANSPORT_STAGES),
            "stages": normalized,
            "chronology": chronology,
            "proposal_payload_digest": _digest(
                proposal_payload_digest,
                "V31_TRANSPORT_EVIDENCE_PAYLOAD_INVALID",
            ),
            "selection_payload_digest": _digest(
                selection_payload_digest,
                "V31_TRANSPORT_EVIDENCE_PAYLOAD_INVALID",
            ),
            "attempt_limit_per_stage": 1,
            "all_deliveries_consumed": True,
            "agent_output_is_execution_authority": False,
            "experiment_start_authority": False,
            **_boundary_fields(),
        },
        "transport_evidence_digest",
    )


def validate_v31_transport_evidence(document: Mapping[str, Any]) -> str:
    digest = _verify_self(
        document,
        "transport_evidence_digest",
        "V31_TRANSPORT_EVIDENCE_DIGEST_INVALID",
    )
    if (
        set(document) != _EVIDENCE_FIELDS
        or document.get("schema_id")
        != "theory_paper_v31_agent_transport_evidence"
        or document.get("schema_version") != "1.0.0"
        or document.get("agent_id") != V31_AGENT_ID
        or document.get("evidence_level") != V31_TRANSPORT_EVIDENCE_LEVEL
        or document.get("stage_order") != list(V31_TRANSPORT_STAGES)
        or document.get("attempt_limit_per_stage") != 1
        or document.get("all_deliveries_consumed") is not True
        or document.get("agent_output_is_execution_authority") is not False
        or document.get("experiment_start_authority") is not False
    ):
        raise V31AgentTransportError("V31_TRANSPORT_EVIDENCE_INVALID")
    rebuilt = seal_v31_transport_evidence(
        run_id=document.get("run_id"),
        cycle_index=document.get("cycle_index"),
        completed_at=document.get("completed_at"),
        stages=document.get("stages", {}),
        proposal_payload_digest=document.get("proposal_payload_digest"),
        selection_payload_digest=document.get("selection_payload_digest"),
    )
    if rebuilt != dict(document):
        raise V31AgentTransportError("V31_TRANSPORT_EVIDENCE_INVALID")
    _execution_boundary(document, "V31_TRANSPORT_EVIDENCE_BOUNDARY_INVALID")
    return digest


__all__ = [
    "V31_AGENT_ID",
    "V31_LEGACY_PROPOSAL_TRANSPORT_CLASS",
    "V31_TRANSPORT_EVIDENCE_LEVEL",
    "V31_TRANSPORT_STAGES",
    "V31AgentTransportError",
    "build_v31_agent_claim",
    "build_v31_agent_delivery",
    "build_v31_agent_request",
    "build_v31_consume_receipt",
    "build_v31_transport_failure",
    "reserve_v31_agent_attempt",
    "seal_v31_transport_evidence",
    "validate_v31_agent_attempt",
    "validate_v31_agent_claim",
    "validate_v31_agent_delivery",
    "validate_v31_agent_request",
    "validate_v31_consume_receipt",
    "validate_v31_transport_binding",
    "validate_v31_transport_evidence",
    "validate_v31_transport_failure",
]
