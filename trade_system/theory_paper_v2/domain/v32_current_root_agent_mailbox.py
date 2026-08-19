"""Pure contracts for the V3.2 current-root Codex durable mailbox.

The mailbox carries an already-built V3.2 Agent input context.  Small contexts
embed the complete packet; oversized contexts bind a durable original and a
complete ordered lossless shard set.  These contracts
never invoke an Agent, a model endpoint, a network transport, an account, or an
order API; they only bind one current-root claim, delivery, and consumption to
one write-once attempt per stage.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from typing import Any, Mapping

from .contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .v32_agent_lifecycle import (
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONSUMPTION_SCHEMA_ID,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_DELIVERY_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    V32_CURRENT_ROOT_AGENT_ID,
    V32_CURRENT_ROOT_DELIVERY_ORIGIN,
    build_v32_embedded_document_binding_v1,
    resolve_v32_agent_canonical_packet_v1,
    verify_v32_agent_consumption_v1,
    verify_v32_agent_delivery_v1,
    verify_v32_agent_input_context_descriptor_v1,
    verify_v32_agent_input_context_v1,
)


class V32CurrentRootAgentMailboxError(ValueError):
    """A mailbox contract or transition violated the frozen boundary."""


SCHEMA_VERSION = "1.0.0"
CHECKPOINT_SCHEMA_ID = "theory_paper_v32_current_root_agent_mailbox_checkpoint_v1"
CHECKPOINT_DIGEST_FIELD = "current_root_agent_mailbox_checkpoint_digest"
REQUEST_SCHEMA_ID = "theory_paper_v32_current_root_agent_mailbox_request_v1"
REQUEST_DIGEST_FIELD = "current_root_agent_mailbox_request_digest"
CLAIM_SCHEMA_ID = "theory_paper_v32_current_root_agent_mailbox_claim_v1"
CLAIM_DIGEST_FIELD = "current_root_agent_mailbox_claim_digest"
DELIVERY_RECEIPT_SCHEMA_ID = (
    "theory_paper_v32_current_root_agent_mailbox_delivery_receipt_v1"
)
DELIVERY_RECEIPT_DIGEST_FIELD = "current_root_agent_mailbox_delivery_receipt_digest"
CONSUMPTION_RECEIPT_SCHEMA_ID = (
    "theory_paper_v32_current_root_agent_mailbox_consumption_receipt_v1"
)
CONSUMPTION_RECEIPT_DIGEST_FIELD = (
    "current_root_agent_mailbox_consumption_receipt_digest"
)
CURRENT_CODEX_PRESENTATION_SCHEMA_ID = (
    "theory_paper_v32_current_codex_presentation_envelope_v1"
)
CURRENT_CODEX_PRESENTATION_DIGEST_FIELD = (
    "current_codex_presentation_envelope_digest"
)
MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES = 1024 * 1024

STAGES = ("PROPOSAL", "SELECTION")
MAILBOX_STATUSES = (
    "READY_FOR_PROPOSAL",
    "WAITING_FOR_PROPOSAL",
    "READY_FOR_SELECTION",
    "WAITING_FOR_SELECTION",
    "COMPLETE",
)
STAGE_STATUSES = (
    "BLOCKED",
    "READY",
    "REQUESTED",
    "CLAIMED",
    "DELIVERED",
    "CONSUMED",
)
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_PRESENTATION_CONTROL_FIELDS_BY_KIND = {
    "READ_ONLY_PENDING_AGENT_REQUEST": frozenset(
        {"presentation_kind", "stage", "stage_status", "next_action", "read_only"}
    ),
    "QUALIFICATION_AGENT_CLAIM": frozenset(
        {"presentation_kind", "stage", "stage_status", "next_action"}
    ),
    "MAILBOX_AGENT_CLAIM": frozenset(
        {"presentation_kind", "stage", "stage_status", "next_action"}
    ),
    "TARGET_AGENT_CLAIM": frozenset(
        {
            "presentation_kind",
            "stage",
            "stage_status",
            "next_action",
            "active_analysis_permit_digest",
            "supervisor_checkpoint_digest",
            "permit_deadline_at",
            "agent_boundary_at",
        }
    ),
    "PROSPECTIVE_PENDING_AGENT_ACTION": frozenset(
        {
            "presentation_kind",
            "request_kind",
            "stage",
            "stage_status",
            "next_action",
        }
    ),
}
_PRESENTATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "mailbox_checkpoint",
        "request",
        "claim",
        "canonical_packet_original_binding",
        "lossless_context_package",
        "input_document_representation",
        "control_context",
        "current_root_codex_only",
        "complete_packet_exactly_once",
        "private_chain_of_thought_requested",
        "network_request_count",
        "account_access",
        "order_submission",
        "retry_allowed",
        "executable",
        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    }
)
_STAGE_STATE_FIELDS = frozenset(
    {
        "status",
        "attempt_count",
        "request_digest",
        "claim_digest",
        "delivery_receipt_digest",
        "consumption_receipt_digest",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "mailbox_id",
        "run_id",
        "cycle_index",
        "revision",
        "predecessor_checkpoint_digest",
        "status",
        "active_stage",
        "stage_states",
        "max_attempts_per_stage",
        "network_request_count",
        "account_access",
        "order_submission",
        "chat_history_is_authority",
        "created_at",
        "updated_at",
        "source_scope",
        "external_execution_authority",
        "executable",
        CHECKPOINT_DIGEST_FIELD,
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "request_id",
        "mailbox_id",
        "run_id",
        "cycle_index",
        "stage",
        "reserved_at",
        "attempt_number",
        "max_attempts",
        "retry_allowed",
        "agent_id",
        "delivery_origin",
        "agent_input_context",
        "agent_input_context_binding",
        "agent_input_context_digest",
        "canonical_packet_digest",
        "context_delivery_mode",
        "ordered_input_delivery_units",
        "ordered_input_delivery_units_digest",
        "ordered_input_delivery_unit_count",
        "complete_ordered_input_required",
        "full_canonical_packet_persisted",
        "network_request_count",
        "account_access",
        "order_submission",
        "private_chain_of_thought_requested",
        "source_scope",
        "external_execution_authority",
        "executable",
        REQUEST_DIGEST_FIELD,
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "request_id",
        "request_digest",
        "mailbox_id",
        "run_id",
        "cycle_index",
        "stage",
        "claimed_at",
        "agent_id",
        "attempt_number",
        "retry_allowed",
        "claim_status",
        "network_request_count",
        "account_access",
        "order_submission",
        "source_scope",
        "external_execution_authority",
        "executable",
        CLAIM_DIGEST_FIELD,
    }
)
_DELIVERY_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "request_digest",
        "claim_digest",
        "mailbox_id",
        "run_id",
        "cycle_index",
        "stage",
        "delivered_at",
        "current_codex_presentation_digest",
        "agent_delivery_digest",
        "agent_delivery_binding",
        "attempt_number",
        "retry_allowed",
        "terminal_delivery",
        "network_request_count",
        "account_access",
        "order_submission",
        "source_scope",
        "external_execution_authority",
        "executable",
        DELIVERY_RECEIPT_DIGEST_FIELD,
    }
)
_CONSUMPTION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "request_digest",
        "claim_digest",
        "delivery_receipt_digest",
        "mailbox_id",
        "run_id",
        "cycle_index",
        "stage",
        "consumed_at",
        "agent_consumption_digest",
        "agent_consumption_binding",
        "context_delivery_mode",
        "ordered_input_delivery_units",
        "ordered_input_delivery_units_digest",
        "ordered_input_delivery_unit_count",
        "complete_ordered_input_consumed",
        "attempt_number",
        "retry_allowed",
        "terminal_consumption",
        "network_request_count",
        "account_access",
        "order_submission",
        "source_scope",
        "external_execution_authority",
        "executable",
        CONSUMPTION_RECEIPT_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32CurrentRootAgentMailboxError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32CurrentRootAgentMailboxError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32CurrentRootAgentMailboxError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text
    ):
        raise V32CurrentRootAgentMailboxError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CYCLE_INVALID")
    return value


def _boundary() -> dict[str, Any]:
    return {
        "network_request_count": 0,
        "account_access": False,
        "order_submission": False,
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
    }


def _assert_boundary(document: Mapping[str, Any], code: str) -> None:
    expected = _boundary()
    if any(document.get(key) != value for key, value in expected.items()):
        raise V32CurrentRootAgentMailboxError(code)


def _binding(
    value: Any,
    *,
    document: Mapping[str, Any],
    schema_id: str,
    digest_field: str,
    code: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32CurrentRootAgentMailboxError(code)
    try:
        expected = build_v32_embedded_document_binding_v1(
            relative_ref=value["relative_ref"],
            document=document,
            schema_id=schema_id,
            digest_field=digest_field,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32CurrentRootAgentMailboxError(code) from exc
    if dict(value) != expected:
        raise V32CurrentRootAgentMailboxError(code)
    return expected


def _empty_stage(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "attempt_count": 0,
        "request_digest": None,
        "claim_digest": None,
        "delivery_receipt_digest": None,
        "consumption_receipt_digest": None,
    }


def _stage_state(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _STAGE_STATE_FIELDS:
        raise V32CurrentRootAgentMailboxError(code)
    status = value.get("status")
    attempt = value.get("attempt_count")
    if status not in STAGE_STATUSES or attempt not in {0, 1}:
        raise V32CurrentRootAgentMailboxError(code)
    fields = (
        "request_digest",
        "claim_digest",
        "delivery_receipt_digest",
        "consumption_receipt_digest",
    )
    digests = [
        _digest(value.get(field), code, nullable=True)
        for field in fields
    ]
    required_count = {
        "BLOCKED": 0,
        "READY": 0,
        "REQUESTED": 1,
        "CLAIMED": 2,
        "DELIVERED": 3,
        "CONSUMED": 4,
    }[status]
    if attempt != (0 if required_count == 0 else 1) or any(
        (index < required_count) != (digest is not None)
        for index, digest in enumerate(digests)
    ):
        raise V32CurrentRootAgentMailboxError(code)
    return {
        "status": status,
        "attempt_count": attempt,
        **dict(zip(fields, digests, strict=True)),
    }


def _checkpoint_state_valid(document: Mapping[str, Any]) -> bool:
    states = document["stage_states"]
    proposal = states["PROPOSAL"]["status"]
    selection = states["SELECTION"]["status"]
    status = document["status"]
    active = document["active_stage"]
    if status == "READY_FOR_PROPOSAL":
        return proposal == "READY" and selection == "BLOCKED" and active is None
    if status == "WAITING_FOR_PROPOSAL":
        return (
            proposal in {"REQUESTED", "CLAIMED", "DELIVERED"}
            and selection == "BLOCKED"
            and active == "PROPOSAL"
        )
    if status == "READY_FOR_SELECTION":
        return proposal == "CONSUMED" and selection == "READY" and active is None
    if status == "WAITING_FOR_SELECTION":
        return (
            proposal == "CONSUMED"
            and selection in {"REQUESTED", "CLAIMED", "DELIVERED"}
            and active == "SELECTION"
        )
    return status == "COMPLETE" and proposal == selection == "CONSUMED" and active is None


def build_v32_current_root_agent_mailbox_checkpoint_v1(
    *, mailbox_id: str, run_id: str, cycle_index: int, created_at: str
) -> dict[str, Any]:
    created = _time(created_at, "V32_MAILBOX_TIME_INVALID")
    return self_digest(
        {
            "schema_id": CHECKPOINT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "mailbox_id": _text(mailbox_id, "V32_MAILBOX_ID_INVALID"),
            "run_id": _text(run_id, "V32_MAILBOX_RUN_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "revision": 0,
            "predecessor_checkpoint_digest": None,
            "status": "READY_FOR_PROPOSAL",
            "active_stage": None,
            "stage_states": {
                "PROPOSAL": _empty_stage("READY"),
                "SELECTION": _empty_stage("BLOCKED"),
            },
            "max_attempts_per_stage": 1,
            "chat_history_is_authority": False,
            "created_at": created,
            "updated_at": created,
            **_boundary(),
        },
        CHECKPOINT_DIGEST_FIELD,
    )


def verify_v32_current_root_agent_mailbox_checkpoint_v1(
    document: Mapping[str, Any],
) -> str:
    if (
        not isinstance(document, Mapping)
        or set(document) != _CHECKPOINT_FIELDS
        or document.get("schema_id") != CHECKPOINT_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("status") not in MAILBOX_STATUSES
        or document.get("active_stage") not in {None, *STAGES}
        or document.get("max_attempts_per_stage") != 1
        or document.get("chat_history_is_authority") is not False
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CHECKPOINT_INVALID")
    try:
        supplied = verify_self_digest(document, CHECKPOINT_DIGEST_FIELD)
        _text(document["mailbox_id"], "V32_MAILBOX_CHECKPOINT_INVALID")
        _text(document["run_id"], "V32_MAILBOX_CHECKPOINT_INVALID")
        _cycle(document["cycle_index"])
        revision = document["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CHECKPOINT_INVALID")
        predecessor = _digest(
            document["predecessor_checkpoint_digest"],
            "V32_MAILBOX_CHECKPOINT_INVALID",
            nullable=True,
        )
        if (revision == 0) != (predecessor is None):
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CHECKPOINT_INVALID")
        created = _moment(document["created_at"], "V32_MAILBOX_CHECKPOINT_INVALID")
        updated = _moment(document["updated_at"], "V32_MAILBOX_CHECKPOINT_INVALID")
        if updated < created:
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CHECKPOINT_INVALID")
        states = document["stage_states"]
        if not isinstance(states, Mapping) or tuple(states) != STAGES:
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CHECKPOINT_INVALID")
        normalized = {
            stage: _stage_state(states[stage], "V32_MAILBOX_CHECKPOINT_INVALID")
            for stage in STAGES
        }
        if normalized != states or not _checkpoint_state_valid(document):
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CHECKPOINT_INVALID")
        _assert_boundary(document, "V32_MAILBOX_CHECKPOINT_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError(
            "V32_MAILBOX_CHECKPOINT_INVALID"
        ) from exc
    return supplied


def build_v32_current_root_agent_mailbox_request_v1(
    *,
    mailbox_id: str,
    agent_input_context: Mapping[str, Any],
    agent_input_context_binding: Mapping[str, Any],
    reserved_at: str,
) -> dict[str, Any]:
    try:
        context_digest = verify_v32_agent_input_context_descriptor_v1(
            agent_input_context
        )
        binding = _binding(
            agent_input_context_binding,
            document=agent_input_context,
            schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
            digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
            code="V32_MAILBOX_REQUEST_CONTEXT_BINDING_INVALID",
        )
        stage = agent_input_context["agent_stage"]
        if stage not in STAGES:
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_STAGE_INVALID")
        reserved = _time(reserved_at, "V32_MAILBOX_REQUEST_TIME_INVALID")
        if _moment(reserved, "V32_MAILBOX_REQUEST_TIME_INVALID") < _moment(
            agent_input_context["created_at"], "V32_MAILBOX_REQUEST_TIME_INVALID"
        ):
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_REQUEST_TIME_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_REQUEST_INVALID") from exc
    request_id = canonical_digest(
        {
            "schema_id": "theory_paper_v32_current_root_agent_mailbox_request_identity_v1",
            "mailbox_id": mailbox_id,
            "run_id": agent_input_context["run_id"],
            "cycle_index": agent_input_context["cycle_index"],
            "stage": stage,
            "agent_input_context_digest": context_digest,
            "attempt_number": 1,
        }
    )
    return self_digest(
        {
            "schema_id": REQUEST_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "mailbox_id": _text(mailbox_id, "V32_MAILBOX_ID_INVALID"),
            "run_id": agent_input_context["run_id"],
            "cycle_index": agent_input_context["cycle_index"],
            "stage": stage,
            "reserved_at": reserved,
            "attempt_number": 1,
            "max_attempts": 1,
            "retry_allowed": False,
            "agent_id": V32_CURRENT_ROOT_AGENT_ID,
            "delivery_origin": V32_CURRENT_ROOT_DELIVERY_ORIGIN,
            "agent_input_context": deepcopy(dict(agent_input_context)),
            "agent_input_context_binding": binding,
            "agent_input_context_digest": context_digest,
            "canonical_packet_digest": agent_input_context[
                "canonical_packet_digest"
            ],
            "context_delivery_mode": agent_input_context[
                "context_delivery_mode"
            ],
            "ordered_input_delivery_units": deepcopy(
                agent_input_context["ordered_input_delivery_units"]
            ),
            "ordered_input_delivery_units_digest": agent_input_context[
                "ordered_input_delivery_units_digest"
            ],
            "ordered_input_delivery_unit_count": agent_input_context[
                "ordered_input_delivery_unit_count"
            ],
            "complete_ordered_input_required": True,
            "full_canonical_packet_persisted": True,
            "private_chain_of_thought_requested": False,
            **_boundary(),
        },
        REQUEST_DIGEST_FIELD,
    )


def verify_v32_current_root_agent_mailbox_request_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _REQUEST_FIELDS:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_REQUEST_INVALID")
    try:
        supplied = verify_self_digest(document, REQUEST_DIGEST_FIELD)
        rebuilt = build_v32_current_root_agent_mailbox_request_v1(
            mailbox_id=document["mailbox_id"],
            agent_input_context=document["agent_input_context"],
            agent_input_context_binding=document["agent_input_context_binding"],
            reserved_at=document["reserved_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_REQUEST_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[REQUEST_DIGEST_FIELD]:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_REQUEST_INVALID")
    if (
        document.get("agent_id") != V32_CURRENT_ROOT_AGENT_ID
        or document.get("delivery_origin") != V32_CURRENT_ROOT_DELIVERY_ORIGIN
        or document.get("attempt_number") != 1
        or document.get("max_attempts") != 1
        or document.get("retry_allowed") is not False
        or document.get("full_canonical_packet_persisted") is not True
        or document.get("complete_ordered_input_required") is not True
        or document.get("private_chain_of_thought_requested") is not False
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_REQUEST_INVALID")
    _assert_boundary(document, "V32_MAILBOX_REQUEST_BOUNDARY_INVALID")
    return supplied


def build_v32_current_root_agent_mailbox_claim_v1(
    *, request: Mapping[str, Any], claimed_at: str
) -> dict[str, Any]:
    request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
    claimed = _time(claimed_at, "V32_MAILBOX_CLAIM_TIME_INVALID")
    if _moment(claimed, "V32_MAILBOX_CLAIM_TIME_INVALID") < _moment(
        request["reserved_at"], "V32_MAILBOX_CLAIM_TIME_INVALID"
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CLAIM_TIME_INVALID")
    return self_digest(
        {
            "schema_id": CLAIM_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "request_id": request["request_id"],
            "request_digest": request_digest,
            "mailbox_id": request["mailbox_id"],
            "run_id": request["run_id"],
            "cycle_index": request["cycle_index"],
            "stage": request["stage"],
            "claimed_at": claimed,
            "agent_id": V32_CURRENT_ROOT_AGENT_ID,
            "attempt_number": 1,
            "retry_allowed": False,
            "claim_status": "CLAIMED_BY_CURRENT_ROOT_CODEX",
            **_boundary(),
        },
        CLAIM_DIGEST_FIELD,
    )


def verify_v32_current_root_agent_mailbox_claim_v1(
    document: Mapping[str, Any], *, request: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _CLAIM_FIELDS:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CLAIM_INVALID")
    try:
        supplied = verify_self_digest(document, CLAIM_DIGEST_FIELD)
        rebuilt = build_v32_current_root_agent_mailbox_claim_v1(
            request=request, claimed_at=document["claimed_at"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CLAIM_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[CLAIM_DIGEST_FIELD]:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CLAIM_INVALID")
    _assert_boundary(document, "V32_MAILBOX_CLAIM_BOUNDARY_INVALID")
    return supplied


def build_v32_current_codex_presentation_envelope_v1(
    *,
    mailbox_checkpoint: Mapping[str, Any],
    request: Mapping[str, Any],
    claim: Mapping[str, Any] | None,
    lossless_context_package: Mapping[str, Any] | None,
    control_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the exact bounded object exposed to the current Codex.

    The durable mailbox may retain several physical views of the same packet,
    but this presentation carries every input document exactly once.  INLINE
    delivery uses the packet already embedded in ``request``.  SHARDED
    delivery uses the one package while the request carries bindings/order
    only.  Callers must build this object before the claim CAS and return the
    same object after the CAS succeeds.
    """

    try:
        checkpoint_digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(
            mailbox_checkpoint
        )
        request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
        claim_digest = None
        if claim is not None:
            claim_digest = verify_v32_current_root_agent_mailbox_claim_v1(
                claim, request=request
            )
        stage = request["stage"]
        state = mailbox_checkpoint["stage_states"][stage]
        expected_status = "CLAIMED" if claim is not None else "REQUESTED"
        if (
            mailbox_checkpoint["run_id"] != request["run_id"]
            or mailbox_checkpoint["cycle_index"] != request["cycle_index"]
            or mailbox_checkpoint["active_stage"] != stage
            or state["status"] != expected_status
            or state["request_digest"] != request_digest
            or state["claim_digest"] != claim_digest
        ):
            raise V32CurrentRootAgentMailboxError(
                "V32_CURRENT_CODEX_PRESENTATION_CHECKPOINT_INVALID"
            )
        context = request["agent_input_context"]
        mode = context["context_delivery_mode"]
        if mode == "INLINE":
            if lossless_context_package is not None:
                raise V32CurrentRootAgentMailboxError(
                    "V32_CURRENT_CODEX_PRESENTATION_PACKAGE_INVALID"
                )
            verify_v32_agent_input_context_v1(context)
            resolve_v32_agent_canonical_packet_v1(context)
            representation = "INLINE_REQUEST_CONTEXT_PACKET_ONCE"
        elif mode == "LOSSLESS_SHARDED":
            if lossless_context_package is None:
                raise V32CurrentRootAgentMailboxError(
                    "V32_CURRENT_CODEX_PRESENTATION_PACKAGE_REQUIRED"
                )
            verify_v32_agent_input_context_v1(
                context,
                lossless_context_package=lossless_context_package,
            )
            resolve_v32_agent_canonical_packet_v1(
                context,
                lossless_context_package=lossless_context_package,
            )
            representation = "SHARDED_PACKAGE_DOCUMENTS_ONCE"
        else:
            raise V32CurrentRootAgentMailboxError(
                "V32_CURRENT_CODEX_PRESENTATION_MODE_INVALID"
            )
        kind = control_context.get("presentation_kind") if isinstance(
            control_context, Mapping
        ) else None
        expected_control_fields = _PRESENTATION_CONTROL_FIELDS_BY_KIND.get(kind)
        if (
            expected_control_fields is None
            or set(control_context) != expected_control_fields
            or any(
                not isinstance(value, (str, int, bool)) or isinstance(value, float)
                for value in control_context.values()
            )
        ):
            raise V32CurrentRootAgentMailboxError(
                "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID"
            )
        expected_action = {
            "REQUESTED": "CURRENT_ROOT_CODEX_CLAIM",
            "CLAIMED": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
        }[expected_status]
        if (
            control_context.get("stage") != stage
            or control_context.get("stage_status") != expected_status
            or control_context.get("next_action") != expected_action
            or (
                kind
                in {
                    "MAILBOX_AGENT_CLAIM",
                    "QUALIFICATION_AGENT_CLAIM",
                    "TARGET_AGENT_CLAIM",
                }
                and claim is None
            )
            or (
                kind == "READ_ONLY_PENDING_AGENT_REQUEST"
                and control_context.get("read_only") is not True
            )
            or (
                kind == "PROSPECTIVE_PENDING_AGENT_ACTION"
                and control_context.get("request_kind")
                != "CURRENT_ROOT_CODEX_AGENT_ACTION_REQUIRED"
            )
        ):
            raise V32CurrentRootAgentMailboxError(
                "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID"
            )
        if kind == "TARGET_AGENT_CLAIM":
            _digest(
                control_context["active_analysis_permit_digest"],
                "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID",
            )
            _digest(
                control_context["supervisor_checkpoint_digest"],
                "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID",
            )
            boundary_at = _moment(
                control_context["agent_boundary_at"],
                "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID",
            )
            deadline_at = _moment(
                control_context["permit_deadline_at"],
                "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID",
            )
            if (
                boundary_at >= deadline_at
                or claim is None
                or claim["claimed_at"] != control_context["agent_boundary_at"]
            ):
                raise V32CurrentRootAgentMailboxError(
                    "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID"
                )
        # Force a deterministic JSON-domain check before self-digesting.
        canonical_bytes(dict(control_context))
        candidate = self_digest(
            {
                "schema_id": CURRENT_CODEX_PRESENTATION_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "mailbox_checkpoint": deepcopy(dict(mailbox_checkpoint)),
                "request": deepcopy(dict(request)),
                "claim": None if claim is None else deepcopy(dict(claim)),
                "canonical_packet_original_binding": deepcopy(
                    dict(context["canonical_packet_binding"])
                ),
                "lossless_context_package": (
                    None
                    if lossless_context_package is None
                    else deepcopy(dict(lossless_context_package))
                ),
                "input_document_representation": representation,
                "control_context": deepcopy(dict(control_context)),
                "current_root_codex_only": True,
                "complete_packet_exactly_once": True,
                "private_chain_of_thought_requested": False,
                "network_request_count": 0,
                "account_access": False,
                "order_submission": False,
                "retry_allowed": False,
                "executable": False,
            },
            CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError(
            "V32_CURRENT_CODEX_PRESENTATION_INVALID"
        ) from exc
    if len(canonical_bytes(candidate)) > MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES:
        raise V32CurrentRootAgentMailboxError(
            "V32_CURRENT_CODEX_PRESENTATION_CAPACITY_UNRESOLVED"
        )
    return candidate


def verify_v32_current_codex_presentation_envelope_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _PRESENTATION_FIELDS:
        raise V32CurrentRootAgentMailboxError(
            "V32_CURRENT_CODEX_PRESENTATION_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
        )
        rebuilt = build_v32_current_codex_presentation_envelope_v1(
            mailbox_checkpoint=document["mailbox_checkpoint"],
            request=document["request"],
            claim=document["claim"],
            lossless_context_package=document["lossless_context_package"],
            control_context=document["control_context"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError(
            "V32_CURRENT_CODEX_PRESENTATION_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[
        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
    ]:
        raise V32CurrentRootAgentMailboxError(
            "V32_CURRENT_CODEX_PRESENTATION_INVALID"
        )
    return supplied


def build_v32_current_root_agent_mailbox_delivery_receipt_v1(
    *,
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    current_codex_presentation_digest: str,
    agent_delivery: Mapping[str, Any],
    agent_delivery_binding: Mapping[str, Any],
) -> dict[str, Any]:
    request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
    claim_digest = verify_v32_current_root_agent_mailbox_claim_v1(
        claim, request=request
    )
    try:
        presentation_digest = _digest(
            current_codex_presentation_digest,
            "V32_MAILBOX_PRESENTATION_DIGEST_INVALID",
        )
        delivery_digest = verify_v32_agent_delivery_v1(
            agent_delivery, agent_input_context=request["agent_input_context"]
        )
        delivery_binding = _binding(
            agent_delivery_binding,
            document=agent_delivery,
            schema_id=AGENT_DELIVERY_SCHEMA_ID,
            digest_field=AGENT_DELIVERY_DIGEST_FIELD,
            code="V32_MAILBOX_DELIVERY_BINDING_INVALID",
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_DELIVERY_INVALID") from exc
    if (
        agent_delivery.get("agent_stage") != request["stage"]
        or agent_delivery.get("run_id") != request["run_id"]
        or agent_delivery.get("cycle_index") != request["cycle_index"]
        or agent_delivery.get("agent_input_context_digest")
        != request["agent_input_context_digest"]
        or agent_delivery.get("reserved_at") != claim["claimed_at"]
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_DELIVERY_INVALID")
    return self_digest(
        {
            "schema_id": DELIVERY_RECEIPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "request_digest": request_digest,
            "claim_digest": claim_digest,
            "mailbox_id": request["mailbox_id"],
            "run_id": request["run_id"],
            "cycle_index": request["cycle_index"],
            "stage": request["stage"],
            "delivered_at": agent_delivery["delivered_at"],
            "current_codex_presentation_digest": presentation_digest,
            "agent_delivery_digest": delivery_digest,
            "agent_delivery_binding": delivery_binding,
            "attempt_number": 1,
            "retry_allowed": False,
            "terminal_delivery": True,
            **_boundary(),
        },
        DELIVERY_RECEIPT_DIGEST_FIELD,
    )


def verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
    document: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    agent_delivery: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _DELIVERY_RECEIPT_FIELDS:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_DELIVERY_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, DELIVERY_RECEIPT_DIGEST_FIELD)
        rebuilt = build_v32_current_root_agent_mailbox_delivery_receipt_v1(
            request=request,
            claim=claim,
            current_codex_presentation_digest=document[
                "current_codex_presentation_digest"
            ],
            agent_delivery=agent_delivery,
            agent_delivery_binding=document["agent_delivery_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError(
            "V32_MAILBOX_DELIVERY_RECEIPT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[DELIVERY_RECEIPT_DIGEST_FIELD]:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_DELIVERY_RECEIPT_INVALID")
    _assert_boundary(document, "V32_MAILBOX_DELIVERY_BOUNDARY_INVALID")
    return supplied


def build_v32_current_root_agent_mailbox_consumption_receipt_v1(
    *,
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    delivery_receipt: Mapping[str, Any],
    agent_delivery: Mapping[str, Any],
    agent_consumption: Mapping[str, Any],
    agent_consumption_binding: Mapping[str, Any],
) -> dict[str, Any]:
    request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
    claim_digest = verify_v32_current_root_agent_mailbox_claim_v1(
        claim, request=request
    )
    delivery_receipt_digest = (
        verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
            delivery_receipt,
            request=request,
            claim=claim,
            agent_delivery=agent_delivery,
        )
    )
    try:
        consumption_digest = verify_v32_agent_consumption_v1(
            agent_consumption,
            agent_input_context=request["agent_input_context"],
            agent_delivery=agent_delivery,
        )
        consumption_binding = _binding(
            agent_consumption_binding,
            document=agent_consumption,
            schema_id=AGENT_CONSUMPTION_SCHEMA_ID,
            digest_field=AGENT_CONSUMPTION_DIGEST_FIELD,
            code="V32_MAILBOX_CONSUMPTION_BINDING_INVALID",
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError(
            "V32_MAILBOX_CONSUMPTION_INVALID"
        ) from exc
    if (
        agent_consumption.get("agent_stage") != request["stage"]
        or agent_consumption.get("run_id") != request["run_id"]
        or agent_consumption.get("cycle_index") != request["cycle_index"]
        or agent_consumption.get("agent_input_context_digest")
        != request["agent_input_context_digest"]
        or agent_consumption.get("agent_delivery_digest")
        != delivery_receipt["agent_delivery_digest"]
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CONSUMPTION_INVALID")
    return self_digest(
        {
            "schema_id": CONSUMPTION_RECEIPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "request_digest": request_digest,
            "claim_digest": claim_digest,
            "delivery_receipt_digest": delivery_receipt_digest,
            "mailbox_id": request["mailbox_id"],
            "run_id": request["run_id"],
            "cycle_index": request["cycle_index"],
            "stage": request["stage"],
            "consumed_at": agent_consumption["consumed_at"],
            "agent_consumption_digest": consumption_digest,
            "agent_consumption_binding": consumption_binding,
            "context_delivery_mode": request["context_delivery_mode"],
            "ordered_input_delivery_units": deepcopy(
                request["ordered_input_delivery_units"]
            ),
            "ordered_input_delivery_units_digest": request[
                "ordered_input_delivery_units_digest"
            ],
            "ordered_input_delivery_unit_count": request[
                "ordered_input_delivery_unit_count"
            ],
            "complete_ordered_input_consumed": True,
            "attempt_number": 1,
            "retry_allowed": False,
            "terminal_consumption": True,
            **_boundary(),
        },
        CONSUMPTION_RECEIPT_DIGEST_FIELD,
    )


def verify_v32_current_root_agent_mailbox_consumption_receipt_v1(
    document: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    delivery_receipt: Mapping[str, Any],
    agent_delivery: Mapping[str, Any],
    agent_consumption: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _CONSUMPTION_RECEIPT_FIELDS:
        raise V32CurrentRootAgentMailboxError(
            "V32_MAILBOX_CONSUMPTION_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, CONSUMPTION_RECEIPT_DIGEST_FIELD)
        rebuilt = build_v32_current_root_agent_mailbox_consumption_receipt_v1(
            request=request,
            claim=claim,
            delivery_receipt=delivery_receipt,
            agent_delivery=agent_delivery,
            agent_consumption=agent_consumption,
            agent_consumption_binding=document["agent_consumption_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentRootAgentMailboxError):
            raise
        raise V32CurrentRootAgentMailboxError(
            "V32_MAILBOX_CONSUMPTION_RECEIPT_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[CONSUMPTION_RECEIPT_DIGEST_FIELD]
    ):
        raise V32CurrentRootAgentMailboxError(
            "V32_MAILBOX_CONSUMPTION_RECEIPT_INVALID"
        )
    _assert_boundary(document, "V32_MAILBOX_CONSUMPTION_BOUNDARY_INVALID")
    return supplied


def _successor(
    checkpoint: Mapping[str, Any],
    *,
    status: str,
    active_stage: str | None,
    stage_states: Mapping[str, Mapping[str, Any]],
    updated_at: str,
) -> dict[str, Any]:
    predecessor = verify_v32_current_root_agent_mailbox_checkpoint_v1(checkpoint)
    updated = _time(updated_at, "V32_MAILBOX_TRANSITION_TIME_INVALID")
    if _moment(updated, "V32_MAILBOX_TRANSITION_TIME_INVALID") < _moment(
        checkpoint["updated_at"], "V32_MAILBOX_TRANSITION_TIME_INVALID"
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_TRANSITION_TIME_INVALID")
    candidate = dict(checkpoint)
    candidate.pop(CHECKPOINT_DIGEST_FIELD, None)
    candidate.update(
        {
            "revision": checkpoint["revision"] + 1,
            "predecessor_checkpoint_digest": predecessor,
            "status": status,
            "active_stage": active_stage,
            "stage_states": deepcopy(dict(stage_states)),
            "updated_at": updated,
        }
    )
    result = self_digest(candidate, CHECKPOINT_DIGEST_FIELD)
    verify_v32_current_root_agent_mailbox_checkpoint_v1(result)
    verify_v32_current_root_agent_mailbox_transition_v1(checkpoint, result)
    return result


def open_v32_current_root_agent_mailbox_request_v1(
    *, checkpoint: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    verify_v32_current_root_agent_mailbox_checkpoint_v1(checkpoint)
    request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
    stage = request["stage"]
    expected_status = "READY_FOR_PROPOSAL" if stage == "PROPOSAL" else "READY_FOR_SELECTION"
    if (
        checkpoint["status"] != expected_status
        or checkpoint["active_stage"] is not None
        or checkpoint["stage_states"][stage]["status"] != "READY"
        or request["mailbox_id"] != checkpoint["mailbox_id"]
        or request["run_id"] != checkpoint["run_id"]
        or request["cycle_index"] != checkpoint["cycle_index"]
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_REQUEST_STATE_INVALID")
    states = deepcopy(checkpoint["stage_states"])
    states[stage] = {
        "status": "REQUESTED",
        "attempt_count": 1,
        "request_digest": request_digest,
        "claim_digest": None,
        "delivery_receipt_digest": None,
        "consumption_receipt_digest": None,
    }
    return _successor(
        checkpoint,
        status=f"WAITING_FOR_{stage}",
        active_stage=stage,
        stage_states=states,
        updated_at=request["reserved_at"],
    )


def claim_v32_current_root_agent_mailbox_request_v1(
    *,
    checkpoint: Mapping[str, Any],
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
) -> dict[str, Any]:
    verify_v32_current_root_agent_mailbox_checkpoint_v1(checkpoint)
    request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
    claim_digest = verify_v32_current_root_agent_mailbox_claim_v1(
        claim, request=request
    )
    stage = request["stage"]
    state = checkpoint["stage_states"][stage]
    if (
        checkpoint["status"] != f"WAITING_FOR_{stage}"
        or checkpoint["active_stage"] != stage
        or state["status"] != "REQUESTED"
        or state["request_digest"] != request_digest
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_CLAIM_STATE_INVALID")
    states = deepcopy(checkpoint["stage_states"])
    states[stage]["status"] = "CLAIMED"
    states[stage]["claim_digest"] = claim_digest
    return _successor(
        checkpoint,
        status=checkpoint["status"],
        active_stage=stage,
        stage_states=states,
        updated_at=claim["claimed_at"],
    )


def deliver_v32_current_root_agent_mailbox_request_v1(
    *,
    checkpoint: Mapping[str, Any],
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    delivery_receipt: Mapping[str, Any],
    agent_delivery: Mapping[str, Any],
) -> dict[str, Any]:
    verify_v32_current_root_agent_mailbox_checkpoint_v1(checkpoint)
    request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
    claim_digest = verify_v32_current_root_agent_mailbox_claim_v1(
        claim, request=request
    )
    receipt_digest = verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
        delivery_receipt,
        request=request,
        claim=claim,
        agent_delivery=agent_delivery,
    )
    stage = request["stage"]
    state = checkpoint["stage_states"][stage]
    if (
        checkpoint["status"] != f"WAITING_FOR_{stage}"
        or checkpoint["active_stage"] != stage
        or state["status"] != "CLAIMED"
        or state["request_digest"] != request_digest
        or state["claim_digest"] != claim_digest
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_DELIVERY_STATE_INVALID")
    states = deepcopy(checkpoint["stage_states"])
    states[stage]["status"] = "DELIVERED"
    states[stage]["delivery_receipt_digest"] = receipt_digest
    return _successor(
        checkpoint,
        status=checkpoint["status"],
        active_stage=stage,
        stage_states=states,
        updated_at=delivery_receipt["delivered_at"],
    )


def consume_v32_current_root_agent_mailbox_request_v1(
    *,
    checkpoint: Mapping[str, Any],
    request: Mapping[str, Any],
    claim: Mapping[str, Any],
    delivery_receipt: Mapping[str, Any],
    agent_delivery: Mapping[str, Any],
    consumption_receipt: Mapping[str, Any],
    agent_consumption: Mapping[str, Any],
) -> dict[str, Any]:
    verify_v32_current_root_agent_mailbox_checkpoint_v1(checkpoint)
    request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
    claim_digest = verify_v32_current_root_agent_mailbox_claim_v1(
        claim, request=request
    )
    delivery_digest = verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
        delivery_receipt,
        request=request,
        claim=claim,
        agent_delivery=agent_delivery,
    )
    consumption_digest = (
        verify_v32_current_root_agent_mailbox_consumption_receipt_v1(
            consumption_receipt,
            request=request,
            claim=claim,
            delivery_receipt=delivery_receipt,
            agent_delivery=agent_delivery,
            agent_consumption=agent_consumption,
        )
    )
    stage = request["stage"]
    state = checkpoint["stage_states"][stage]
    if (
        checkpoint["status"] != f"WAITING_FOR_{stage}"
        or checkpoint["active_stage"] != stage
        or state["status"] != "DELIVERED"
        or state["request_digest"] != request_digest
        or state["claim_digest"] != claim_digest
        or state["delivery_receipt_digest"] != delivery_digest
    ):
        raise V32CurrentRootAgentMailboxError(
            "V32_MAILBOX_CONSUMPTION_STATE_INVALID"
        )
    states = deepcopy(checkpoint["stage_states"])
    states[stage]["status"] = "CONSUMED"
    states[stage]["consumption_receipt_digest"] = consumption_digest
    if stage == "PROPOSAL":
        states["SELECTION"] = _empty_stage("READY")
        status = "READY_FOR_SELECTION"
    else:
        status = "COMPLETE"
    return _successor(
        checkpoint,
        status=status,
        active_stage=None,
        stage_states=states,
        updated_at=consumption_receipt["consumed_at"],
    )


def verify_v32_current_root_agent_mailbox_transition_v1(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> str:
    before_digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(before)
    after_digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(after)
    if (
        after["revision"] != before["revision"] + 1
        or after["predecessor_checkpoint_digest"] != before_digest
        or any(
            after[field] != before[field]
            for field in ("mailbox_id", "run_id", "cycle_index", "created_at")
        )
        or _moment(after["updated_at"], "V32_MAILBOX_TRANSITION_INVALID")
        < _moment(before["updated_at"], "V32_MAILBOX_TRANSITION_INVALID")
        or after["network_request_count"] != 0
    ):
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_TRANSITION_INVALID")
    changed_stages = [
        stage
        for stage in STAGES
        if before["stage_states"][stage] != after["stage_states"][stage]
    ]
    proposal_consumed = changed_stages == ["PROPOSAL", "SELECTION"]
    if len(changed_stages) != 1 and not proposal_consumed:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_TRANSITION_INVALID")
    stage = "PROPOSAL" if proposal_consumed else changed_stages[0]
    old = before["stage_states"][stage]["status"]
    new = after["stage_states"][stage]["status"]
    allowed = {
        ("READY", "REQUESTED"),
        ("REQUESTED", "CLAIMED"),
        ("CLAIMED", "DELIVERED"),
        ("DELIVERED", "CONSUMED"),
    }
    if (old, new) not in allowed:
        raise V32CurrentRootAgentMailboxError("V32_MAILBOX_TRANSITION_INVALID")
    if stage == "PROPOSAL" and new == "CONSUMED":
        # The Selection READY flip is part of the same Proposal consumption
        # boundary, so it is the sole permitted second stage-state difference.
        if (
            not proposal_consumed
            or before["stage_states"]["SELECTION"] != _empty_stage("BLOCKED")
            or after["stage_states"]["SELECTION"] != _empty_stage("READY")
        ):
            raise V32CurrentRootAgentMailboxError("V32_MAILBOX_TRANSITION_INVALID")
    return after_digest


__all__ = [
    "CHECKPOINT_DIGEST_FIELD",
    "CHECKPOINT_SCHEMA_ID",
    "CLAIM_DIGEST_FIELD",
    "CLAIM_SCHEMA_ID",
    "CURRENT_CODEX_PRESENTATION_DIGEST_FIELD",
    "CURRENT_CODEX_PRESENTATION_SCHEMA_ID",
    "CONSUMPTION_RECEIPT_DIGEST_FIELD",
    "CONSUMPTION_RECEIPT_SCHEMA_ID",
    "DELIVERY_RECEIPT_DIGEST_FIELD",
    "DELIVERY_RECEIPT_SCHEMA_ID",
    "MAILBOX_STATUSES",
    "MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES",
    "REQUEST_DIGEST_FIELD",
    "REQUEST_SCHEMA_ID",
    "STAGES",
    "V32CurrentRootAgentMailboxError",
    "build_v32_current_codex_presentation_envelope_v1",
    "build_v32_current_root_agent_mailbox_checkpoint_v1",
    "build_v32_current_root_agent_mailbox_claim_v1",
    "build_v32_current_root_agent_mailbox_consumption_receipt_v1",
    "build_v32_current_root_agent_mailbox_delivery_receipt_v1",
    "build_v32_current_root_agent_mailbox_request_v1",
    "claim_v32_current_root_agent_mailbox_request_v1",
    "consume_v32_current_root_agent_mailbox_request_v1",
    "deliver_v32_current_root_agent_mailbox_request_v1",
    "open_v32_current_root_agent_mailbox_request_v1",
    "verify_v32_current_root_agent_mailbox_checkpoint_v1",
    "verify_v32_current_root_agent_mailbox_claim_v1",
    "verify_v32_current_root_agent_mailbox_consumption_receipt_v1",
    "verify_v32_current_root_agent_mailbox_delivery_receipt_v1",
    "verify_v32_current_root_agent_mailbox_request_v1",
    "verify_v32_current_root_agent_mailbox_transition_v1",
    "verify_v32_current_codex_presentation_envelope_v1",
]
