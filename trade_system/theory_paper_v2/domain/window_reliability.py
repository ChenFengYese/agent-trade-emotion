"""Pure reliability contracts for long-running and cross-window Agent work.

The module owns no files, models, automations, or trading permissions.  It
turns durable references, bounded Agent inputs, complete delivery envelopes,
current-cycle grounding, and pre-accept validation into canonical receipts.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .dynamic_research import (
    TERMINAL_EXPECTATION_STATUSES,
    TERMINAL_HYPOTHESIS_STATES,
)
from .portfolio_truth import build_lot_position_truth


class WindowReliabilityError(ValueError):
    """A cross-window or Agent-delivery invariant failed closed."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CYCLE_LABELS = (
    re.compile(r"\bcycle\s*[-#:]?\s*(\d+)\b", flags=re.IGNORECASE),
    re.compile(r"第\s*(\d+)\s*轮"),
)
_UNSTRUCTURED_POSITION_PATTERNS = (
    re.compile(r"mark\s*名义\s*[=:：]?\s*[+-]?\d", flags=re.IGNORECASE),
    re.compile(r"mark[ _-]*notional\s*[=:：]?\s*[+-]?\d", flags=re.IGNORECASE),
    re.compile(r"open[ _-]*risk\s*[=:：]?\s*[+-]?\d", flags=re.IGNORECASE),
    re.compile(r"remaining[ _-]*quantity\s*[=:：]?\s*[+-]?\d", flags=re.IGNORECASE),
    re.compile(r"(?:CORE|TACTICAL|HEDGE)\s*[=:：]?\s*[+-]?\d", flags=re.IGNORECASE),
)
_LOT_ID_PATTERN = re.compile(r"\blot:[A-Za-z0-9._:-]+\b")
_INLINE_CONTEXT_FIELDS = (
    "market_information_snapshot",
    "previous_research_state_view",
    "previous_research_state_refs",
    "portfolio_truth",
    "risk_policy",
    "legal_action_contract",
    "research_capability_contract",
    "unknown_market_categories",
)
_FORBIDDEN_CONTEXT_FIELDS = frozenset(
    {
        "chat_summary",
        "conversation_history",
        "old_window_context",
        "private_chain_of_thought",
        "future_outcomes",
    }
)


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise WindowReliabilityError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WindowReliabilityError(code) from exc
    if parsed.tzinfo is None:
        raise WindowReliabilityError(code)
    return parsed.astimezone(UTC)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise WindowReliabilityError(code)
    return value


def _verified(document: Mapping[str, Any], field: str, code: str) -> str:
    if not isinstance(document, Mapping):
        raise WindowReliabilityError(code)
    try:
        return verify_self_digest(document, field)
    except ValueError as exc:
        raise WindowReliabilityError(code) from exc


def _strings(value: Any, code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise WindowReliabilityError(code)
    rows = tuple(value)
    if (
        (not allow_empty and not rows)
        or any(not isinstance(row, str) or not row for row in rows)
        or len(rows) != len(set(rows))
    ):
        raise WindowReliabilityError(code)
    return rows


def _artifact_ref(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "relative_ref",
        "semantic_digest",
        "physical_sha256",
    }:
        raise WindowReliabilityError(code)
    relative_ref = str(value.get("relative_ref") or "")
    path = PurePosixPath(relative_ref)
    if (
        not relative_ref
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
    ):
        raise WindowReliabilityError(code)
    return {
        "relative_ref": relative_ref,
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def build_resume_capsule(
    *,
    run_id: str,
    created_at: str,
    manifest_ref: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    checkpoint_ref: Mapping[str, Any],
    accepted_state_ref: Mapping[str, Any] | None,
    completion_receipt_ref: Mapping[str, Any] | None,
    prior_state_refs: Mapping[str, Mapping[str, Any]],
    current_cycle_stage_refs: Mapping[str, Mapping[str, Any]] | None = None,
    pending_accepted_state_ref: Mapping[str, Any] | None = None,
    allowed_read_refs: Sequence[str],
    forbidden_read_prefixes: Sequence[str],
    authority_status: str,
) -> dict[str, Any]:
    """Build the only cross-window authority packet for a durable checkpoint."""

    if not run_id or not authority_status:
        raise WindowReliabilityError("RESUME_CAPSULE_IDENTITY_INVALID")
    _timestamp(created_at, "RESUME_CAPSULE_TIME_INVALID")
    checkpoint_digest = _verified(
        checkpoint, "checkpoint_digest", "RESUME_CHECKPOINT_DIGEST_INVALID"
    )
    checkpoint_binding = _artifact_ref(
        checkpoint_ref, "RESUME_CHECKPOINT_REF_INVALID"
    )
    manifest_binding = _artifact_ref(manifest_ref, "RESUME_MANIFEST_REF_INVALID")
    if checkpoint_binding["semantic_digest"] != checkpoint_digest:
        raise WindowReliabilityError("RESUME_CHECKPOINT_BINDING_MISMATCH")
    completed = checkpoint.get("completed_cycles")
    next_cycle = checkpoint.get("next_cycle_index")
    checkpoint_status = str(checkpoint.get("status") or "")
    resumable_statuses = {
        "READY_FOR_CYCLE",
        "RUNNING_OUTCOMES_SEALED",
        "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED",
        "PRE_ACCEPT_RECOVERABLE_FAILURE",
        "POST_ACCEPT_FINALIZATION",
        "POST_ACCEPT_RECOVERABLE_FAILURE",
    }
    terminal_statuses = {
        "PRE_ACCEPT_FAILED_CLOSED",
        "POST_ACCEPT_FAILED_CLOSED",
    }
    if (
        checkpoint.get("run_id") != run_id
        or checkpoint_status not in resumable_statuses | terminal_statuses
        or isinstance(completed, bool)
        or not isinstance(completed, int)
        or completed < 0
        or isinstance(next_cycle, bool)
        or not isinstance(next_cycle, int)
        or next_cycle != completed + 1
        or checkpoint.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or checkpoint.get("executable") is not False
    ):
        raise WindowReliabilityError("RESUME_CHECKPOINT_NOT_DURABLE")

    normalized_accepted = (
        None
        if accepted_state_ref is None
        else _artifact_ref(accepted_state_ref, "RESUME_ACCEPTED_STATE_REF_INVALID")
    )
    normalized_completion = (
        None
        if completion_receipt_ref is None
        else _artifact_ref(
            completion_receipt_ref, "RESUME_COMPLETION_RECEIPT_REF_INVALID"
        )
    )
    normalized_pending = (
        None
        if pending_accepted_state_ref is None
        else _artifact_ref(
            pending_accepted_state_ref,
            "RESUME_PENDING_ACCEPTED_STATE_REF_INVALID",
        )
    )
    if completed == 0:
        if (
            normalized_accepted is not None
            or normalized_completion is not None
            or checkpoint.get("accepted_state_path") is not None
            or checkpoint.get("accepted_state_digest") is not None
            or checkpoint.get("last_completion_receipt_digest") is not None
        ):
            raise WindowReliabilityError("RESUME_GENESIS_BINDING_INVALID")
    elif (
        normalized_accepted is None
        or normalized_completion is None
        or normalized_accepted["relative_ref"]
        != checkpoint.get("accepted_state_path")
        or normalized_accepted["semantic_digest"]
        != checkpoint.get("accepted_state_digest")
        or normalized_completion["semantic_digest"]
        != checkpoint.get("last_completion_receipt_digest")
    ):
        raise WindowReliabilityError("RESUME_ACCEPTED_HEAD_BINDING_MISMATCH")

    if checkpoint_status in {
        "POST_ACCEPT_FINALIZATION",
        "POST_ACCEPT_RECOVERABLE_FAILURE",
        "POST_ACCEPT_FAILED_CLOSED",
    }:
        if (
            normalized_pending is None
            or normalized_pending["relative_ref"]
            != checkpoint.get("pending_accepted_state_path")
            or normalized_pending["semantic_digest"]
            != checkpoint.get("pending_accepted_state_digest")
            or checkpoint.get("pending_finalization_cycle") != next_cycle
        ):
            raise WindowReliabilityError(
                "RESUME_PENDING_ACCEPTED_STATE_BINDING_MISMATCH"
            )
    elif (
        normalized_pending is not None
        or checkpoint.get("pending_accepted_state_path") is not None
        or checkpoint.get("pending_accepted_state_digest") is not None
        or checkpoint.get("pending_finalization_cycle") is not None
    ):
        raise WindowReliabilityError("RESUME_PENDING_ACCEPTED_STATE_FORBIDDEN")

    normalized_prior_refs: dict[str, dict[str, str]] = {}
    for name, value in sorted(prior_state_refs.items()):
        if name not in {
            "hypothesis_registry",
            "expectation_ledger",
            "belief_state",
            "accepted_state",
            "cycle_evidence_receipt",
            "completion_receipt",
        }:
            raise WindowReliabilityError("RESUME_PRIOR_STATE_REF_INVALID")
        normalized_prior_refs[name] = _artifact_ref(
            value, "RESUME_PRIOR_STATE_REF_INVALID"
        )
    if completed > 0 and set(normalized_prior_refs) != {
        "hypothesis_registry",
        "expectation_ledger",
        "belief_state",
        "accepted_state",
        "cycle_evidence_receipt",
        "completion_receipt",
    }:
        raise WindowReliabilityError("RESUME_PRIOR_STATE_REFS_INCOMPLETE")
    if completed == 0 and normalized_prior_refs:
        raise WindowReliabilityError("RESUME_GENESIS_PRIOR_STATE_FORBIDDEN")

    normalized_stage_refs = {
        str(name): _artifact_ref(value, "RESUME_CURRENT_STAGE_REF_INVALID")
        for name, value in sorted((current_cycle_stage_refs or {}).items())
    }
    if any(not name for name in normalized_stage_refs):
        raise WindowReliabilityError("RESUME_CURRENT_STAGE_REF_INVALID")

    allowed = _strings(
        allowed_read_refs, "RESUME_ALLOWED_REFS_INVALID", allow_empty=False
    )
    forbidden = _strings(
        forbidden_read_prefixes,
        "RESUME_FORBIDDEN_PREFIXES_INVALID",
        allow_empty=False,
    )
    required_allowed = {
        manifest_binding["relative_ref"],
        checkpoint_binding["relative_ref"],
        *(row["relative_ref"] for row in normalized_prior_refs.values()),
        *(row["relative_ref"] for row in normalized_stage_refs.values()),
    }
    if normalized_accepted is not None:
        required_allowed.add(normalized_accepted["relative_ref"])
    if normalized_completion is not None:
        required_allowed.add(normalized_completion["relative_ref"])
    if normalized_pending is not None:
        required_allowed.add(normalized_pending["relative_ref"])
    if not required_allowed.issubset(set(allowed)):
        raise WindowReliabilityError("RESUME_ALLOWED_REFS_INCOMPLETE")

    if checkpoint_status in {
        "POST_ACCEPT_FINALIZATION",
        "POST_ACCEPT_RECOVERABLE_FAILURE",
    }:
        recovery_mode = "DETERMINISTIC_POST_ACCEPT_FINALIZATION"
        agent_reinvocation_policy = "FORBIDDEN"
    elif checkpoint_status == "PRE_ACCEPT_RECOVERABLE_FAILURE":
        recovery_mode = "PRE_ACCEPT_CONTINUE_FROM_SEALED_INPUTS"
        agent_reinvocation_policy = "ONLY_UNSEALED_AGENT_PHASE_FROM_EVENT_CHAIN"
    elif checkpoint_status in terminal_statuses:
        recovery_mode = "FAILURE_CLOSED_AUDIT_ONLY"
        agent_reinvocation_policy = "FORBIDDEN"
    else:
        recovery_mode = "CYCLE_BOUNDARY_OR_EVENT_CHAIN_REPLAY"
        agent_reinvocation_policy = "ONLY_UNSEALED_AGENT_PHASE_FROM_EVENT_CHAIN"
    resume_allowed = checkpoint_status in resumable_statuses
    capsule = {
        "schema_id": "cross_window_resume_capsule",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "created_at": created_at,
        "completed_cycles": completed,
        "next_cycle_index": next_cycle,
        "checkpoint_status": checkpoint_status,
        "manifest_ref": manifest_binding,
        "checkpoint_ref": checkpoint_binding,
        "accepted_state_ref": normalized_accepted,
        "completion_receipt_ref": normalized_completion,
        "pending_accepted_state_ref": normalized_pending,
        "prior_state_refs": normalized_prior_refs,
        "current_cycle_stage_refs": normalized_stage_refs,
        "allowed_read_refs": sorted(allowed),
        "forbidden_read_prefixes": sorted(forbidden),
        "authority_status": authority_status,
        "resume_allowed": resume_allowed,
        "recovery_mode": recovery_mode,
        "agent_reinvocation_policy": agent_reinvocation_policy,
        "chat_history_is_authority": False,
        "conversation_summary_is_authority": False,
        "future_outcome_access": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(capsule, "resume_capsule_digest")


def build_bounded_prior_state_view(
    *,
    previous_registry: Mapping[str, Any] | None,
    previous_ledger: Mapping[str, Any] | None,
    previous_beliefs: Mapping[str, Any] | None,
    previous_accepted_state: Mapping[str, Any] | None,
    prior_state_refs: Mapping[str, Mapping[str, Any]],
    max_nonterminal_hypotheses: int = 20,
    max_open_expectations: int = 20,
    max_recent_closed_expectations: int = 5,
    max_active_evidence: int = 100,
) -> dict[str, Any]:
    """Project active research state while binding the complete history by ref."""

    limits = (
        max_nonterminal_hypotheses,
        max_open_expectations,
        max_recent_closed_expectations,
        max_active_evidence,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in limits):
        raise WindowReliabilityError("PRIOR_STATE_VIEW_LIMIT_INVALID")
    documents = (
        previous_registry,
        previous_ledger,
        previous_beliefs,
        previous_accepted_state,
    )
    if all(document is None for document in documents):
        if prior_state_refs:
            raise WindowReliabilityError("PRIOR_STATE_VIEW_GENESIS_REF_INVALID")
        return self_digest(
            {
                "schema_id": "bounded_prior_research_state_view",
                "schema_version": "1.0.0",
                "status": "GENESIS_NO_PRIOR_STATE",
                "hypothesis_registry": None,
                "expectation_ledger": None,
                "belief_state": None,
                "accepted_state": None,
                "full_history_refs": {},
                "omitted_counts": {
                    "hypotheses": 0,
                    "expectations": 0,
                    "active_evidence": 0,
                },
            },
            "prior_state_view_digest",
        )
    if any(document is None for document in documents):
        raise WindowReliabilityError("PRIOR_STATE_VIEW_DOCUMENTS_INCOMPLETE")
    normalized_refs = {
        name: _artifact_ref(value, "PRIOR_STATE_VIEW_REF_INVALID")
        for name, value in sorted(prior_state_refs.items())
        if name in {"hypothesis_registry", "expectation_ledger", "belief_state", "accepted_state"}
    }
    if set(normalized_refs) != {
        "hypothesis_registry",
        "expectation_ledger",
        "belief_state",
        "accepted_state",
    }:
        raise WindowReliabilityError("PRIOR_STATE_VIEW_REFS_INCOMPLETE")
    registry_digest = _verified(
        previous_registry,
        "hypothesis_registry_digest",
        "PRIOR_REGISTRY_DIGEST_INVALID",
    )
    ledger_digest = _verified(
        previous_ledger,
        "expectation_ledger_digest",
        "PRIOR_LEDGER_DIGEST_INVALID",
    )
    belief_digest = _verified(
        previous_beliefs,
        "belief_state_digest",
        "PRIOR_BELIEF_DIGEST_INVALID",
    )
    accepted_digest = _verified(
        previous_accepted_state,
        "accepted_state_digest",
        "PRIOR_ACCEPTED_STATE_DIGEST_INVALID",
    )
    expected_digests = {
        "hypothesis_registry": registry_digest,
        "expectation_ledger": ledger_digest,
        "belief_state": belief_digest,
        "accepted_state": accepted_digest,
    }
    if any(
        normalized_refs[name]["semantic_digest"] != digest
        for name, digest in expected_digests.items()
    ):
        raise WindowReliabilityError("PRIOR_STATE_VIEW_REF_DIGEST_MISMATCH")

    nonterminal = [
        dict(row)
        for row in previous_registry.get("hypotheses", [])
        if isinstance(row, Mapping)
        and row.get("state") not in TERMINAL_HYPOTHESIS_STATES
    ]
    state_rank = {"ACTIVE": 0, "CANDIDATE": 1, "WATCH": 2, "DORMANT": 3}
    nonterminal.sort(
        key=lambda row: (
            state_rank.get(str(row.get("state")), 99),
            str(row.get("updated_at") or ""),
            str(row.get("hypothesis_id") or ""),
        )
    )
    included_hypotheses = nonterminal[:max_nonterminal_hypotheses]

    expectations = [
        dict(row)
        for row in previous_ledger.get("expectations", [])
        if isinstance(row, Mapping)
    ]
    open_rows = sorted(
        (
            row
            for row in expectations
            if row.get("status") not in TERMINAL_EXPECTATION_STATUSES
        ),
        key=lambda row: (
            str(row.get("observation_deadline") or ""),
            str(row.get("expectation_id") or ""),
        ),
    )
    closed_rows = sorted(
        (
            row
            for row in expectations
            if row.get("status") in TERMINAL_EXPECTATION_STATUSES
        ),
        key=lambda row: (
            str(row.get("updated_at") or ""),
            str(row.get("expectation_id") or ""),
        ),
        reverse=True,
    )
    included_expectations = (
        open_rows[:max_open_expectations]
        + closed_rows[:max_recent_closed_expectations]
    )
    active_evidence = [
        dict(row)
        for row in previous_beliefs.get("active_evidence", [])
        if isinstance(row, Mapping)
    ]
    active_evidence.sort(
        key=lambda row: (
            str(row.get("path_id") or ""),
            str(row.get("lineage_key") or ""),
            str(row.get("evidence_id") or ""),
        )
    )
    included_evidence = active_evidence[:max_active_evidence]
    accepted_summary = {
        key: previous_accepted_state.get(key)
        for key in (
            "run_id",
            "cycle_index",
            "decision_digest",
            "selected_candidate_id",
            "operational_lead_path_id",
            "market_information_snapshot_digest",
            "sentiment_state_digest",
            "hypothesis_registry_digest",
            "expectation_ledger_digest",
            "public_inference_trace_digest",
            "belief_state_digest",
            "accepted_state_digest",
        )
    }
    return self_digest(
        {
            "schema_id": "bounded_prior_research_state_view",
            "schema_version": "1.0.0",
            "status": "BOUNDED_VIEW_WITH_CONTENT_ADDRESSED_FULL_HISTORY",
            "hypothesis_registry": {
                "revision": previous_registry.get("revision"),
                "decision_at": previous_registry.get("decision_at"),
                "active_hypothesis_ids": list(
                    previous_registry.get("active_hypothesis_ids", [])
                ),
                "hypotheses": included_hypotheses,
                "complete_registry_digest": registry_digest,
            },
            "expectation_ledger": {
                "revision": previous_ledger.get("revision"),
                "decision_at": previous_ledger.get("decision_at"),
                "open_expectation_ids": list(
                    previous_ledger.get("open_expectation_ids", [])
                ),
                "expectations": included_expectations,
                "complete_ledger_digest": ledger_digest,
            },
            "belief_state": {
                "revision": previous_beliefs.get("revision"),
                "decision_at": previous_beliefs.get("decision_at"),
                "path_beliefs": dict(previous_beliefs.get("path_beliefs", {})),
                "active_evidence": included_evidence,
                "complete_belief_state_digest": belief_digest,
            },
            "accepted_state": accepted_summary,
            "full_history_refs": normalized_refs,
            "omitted_counts": {
                "hypotheses": len(nonterminal) - len(included_hypotheses),
                "expectations": len(expectations) - len(included_expectations),
                "active_evidence": len(active_evidence) - len(included_evidence),
            },
            "history_fetch_required_before_using_omitted_item": True,
            "chat_history_is_authority": False,
        },
        "prior_state_view_digest",
    )


def build_agent_input_plan(
    *,
    agent_context: Mapping[str, Any],
    max_input_bytes: int,
    max_output_bytes: int,
    model_invocation_expected: bool,
    measured_input_tokens: int | None = None,
    max_input_tokens: int | None = None,
    tokenizer_id: str | None = None,
) -> dict[str, Any]:
    """Preflight one exact Agent payload; never permit implicit truncation."""

    context_digest = _verified(
        agent_context, "agent_context_digest", "AGENT_INPUT_CONTEXT_DIGEST_INVALID"
    )
    if (
        isinstance(max_input_bytes, bool)
        or not isinstance(max_input_bytes, int)
        or max_input_bytes <= 0
        or isinstance(max_output_bytes, bool)
        or not isinstance(max_output_bytes, int)
        or max_output_bytes <= 0
    ):
        raise WindowReliabilityError("AGENT_INPUT_BUDGET_INVALID")
    if _FORBIDDEN_CONTEXT_FIELDS.intersection(agent_context):
        raise WindowReliabilityError("AGENT_CONTEXT_CHAT_OR_FUTURE_STATE_FORBIDDEN")
    if any(field not in agent_context for field in _INLINE_CONTEXT_FIELDS):
        raise WindowReliabilityError("AGENT_INPUT_REQUIRED_SECTION_MISSING")
    if (
        agent_context.get("context_payload_mode")
        != "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE"
        or agent_context.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or agent_context.get("executable") is not False
    ):
        raise WindowReliabilityError("AGENT_INPUT_CONTEXT_MODE_INVALID")
    context_bytes = len(canonical_bytes(agent_context))
    sections = []
    for field in _INLINE_CONTEXT_FIELDS:
        payload = agent_context[field]
        sections.append(
            {
                "section_id": field,
                "required": True,
                "delivery_mode": (
                    "CONTENT_ADDRESSED_REFERENCE_SET"
                    if field == "previous_research_state_refs"
                    else "INLINE_CANONICAL"
                ),
                "canonical_byte_length": len(canonical_bytes(payload)),
                "wire_byte_length": len(canonical_bytes(payload)),
                "content_digest": canonical_digest(payload),
            }
        )
    if context_bytes > max_input_bytes:
        raise WindowReliabilityError("AGENT_INPUT_BUDGET_EXCEEDED")

    token_measurement: dict[str, Any]
    if model_invocation_expected:
        if (
            isinstance(measured_input_tokens, bool)
            or not isinstance(measured_input_tokens, int)
            or measured_input_tokens <= 0
            or isinstance(max_input_tokens, bool)
            or not isinstance(max_input_tokens, int)
            or max_input_tokens <= 0
            or not isinstance(tokenizer_id, str)
            or not tokenizer_id
        ):
            raise WindowReliabilityError("AGENT_TOKEN_PREFLIGHT_REQUIRED")
        if measured_input_tokens > max_input_tokens:
            raise WindowReliabilityError("AGENT_INPUT_TOKEN_BUDGET_EXCEEDED")
        token_measurement = {
            "status": "MEASURED_BY_REGISTERED_TOKENIZER",
            "tokenizer_id": tokenizer_id,
            "measured_input_tokens": measured_input_tokens,
            "max_input_tokens": max_input_tokens,
        }
    else:
        if any(
            value is not None
            for value in (measured_input_tokens, max_input_tokens, tokenizer_id)
        ):
            raise WindowReliabilityError("AGENT_SYNTHETIC_TOKEN_FIELDS_FORBIDDEN")
        token_measurement = {
            "status": "NOT_APPLICABLE_SYNTHETIC_NO_MODEL_INVOCATION",
            "tokenizer_id": None,
            "measured_input_tokens": None,
            "max_input_tokens": None,
        }
    return self_digest(
        {
            "schema_id": "agent_input_delivery_plan",
            "schema_version": "1.0.0",
            "run_id": agent_context.get("run_id"),
            "cycle_index": agent_context.get("cycle_index"),
            "agent_context_digest": context_digest,
            "context_canonical_byte_length": context_bytes,
            "context_wire_byte_length": context_bytes,
            "max_input_bytes": max_input_bytes,
            "reserved_max_output_bytes": max_output_bytes,
            "sections": sections,
            "token_measurement": token_measurement,
            "preflight_verdict": "PASS",
            "implicit_truncation_allowed": False,
            "chat_history_dependency": False,
            "full_history_delivery": "CONTENT_ADDRESSED_REFERENCES_PLUS_BOUNDED_VIEW",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "agent_input_plan_digest",
    )


def validate_agent_delivery(
    *,
    delivery: Mapping[str, Any],
    run_id: str,
    cycle_index: int,
    input_digest: str,
    expected_schema_id: str,
    max_output_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Accept only one complete canonical object with a bounded output size."""

    required = {
        "delivery_status",
        "finish_reason",
        "truncated",
        "complete_json_object",
        "run_id",
        "cycle_index",
        "input_digest",
        "expected_schema_id",
        "payload",
        "payload_digest",
        "payload_canonical_bytes",
        "adapter_receipt_id",
        "transport_record_ref",
        "transport_record_digest",
        "transport_record_sha256",
        "durable_before_adapter_return",
    }
    if not isinstance(delivery, Mapping) or set(delivery) != required:
        raise WindowReliabilityError("AGENT_DELIVERY_ENVELOPE_INVALID")
    _digest(input_digest, "AGENT_DELIVERY_INPUT_DIGEST_INVALID")
    payload = delivery.get("payload")
    if not isinstance(payload, Mapping):
        raise WindowReliabilityError("AGENT_DELIVERY_PAYLOAD_INVALID")
    payload_document = dict(payload)
    payload_bytes = canonical_bytes(payload_document)
    transport_ref = str(delivery.get("transport_record_ref") or "")
    transport_path = PurePosixPath(transport_ref)
    if (
        delivery.get("delivery_status") != "COMPLETE"
        or delivery.get("finish_reason") != "STOP"
        or delivery.get("truncated") is not False
        or delivery.get("complete_json_object") is not True
        or delivery.get("run_id") != run_id
        or delivery.get("cycle_index") != cycle_index
        or delivery.get("input_digest") != input_digest
        or delivery.get("expected_schema_id") != expected_schema_id
        or delivery.get("payload_digest") != canonical_digest(payload_document)
        or delivery.get("payload_canonical_bytes") != len(payload_bytes)
        or not isinstance(delivery.get("adapter_receipt_id"), str)
        or not delivery.get("adapter_receipt_id")
        or not transport_ref
        or transport_path.is_absolute()
        or ".." in transport_path.parts
        or "." in transport_path.parts
        or _HEX_64.fullmatch(
            str(delivery.get("transport_record_digest") or "")
        )
        is None
        or _HEX_64.fullmatch(
            str(delivery.get("transport_record_sha256") or "")
        )
        is None
        or delivery.get("durable_before_adapter_return") is not True
    ):
        raise WindowReliabilityError("AGENT_DELIVERY_INCOMPLETE_OR_MISMATCHED")
    if (
        isinstance(max_output_bytes, bool)
        or not isinstance(max_output_bytes, int)
        or max_output_bytes <= 0
        or len(payload_bytes) > max_output_bytes
    ):
        raise WindowReliabilityError("AGENT_OUTPUT_BUDGET_EXCEEDED")
    receipt = self_digest(
        {
            "schema_id": "complete_agent_delivery_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "input_digest": input_digest,
            "expected_schema_id": expected_schema_id,
            "payload_digest": delivery["payload_digest"],
            "payload_canonical_bytes": len(payload_bytes),
            "adapter_receipt_id": delivery["adapter_receipt_id"],
            "transport_record_ref": transport_ref,
            "transport_record_digest": delivery["transport_record_digest"],
            "transport_record_sha256": delivery["transport_record_sha256"],
            "durable_before_adapter_return": True,
            "delivery_status": "COMPLETE",
            "finish_reason": "STOP",
            "truncated": False,
            "complete_json_object": True,
        },
        "agent_delivery_receipt_digest",
    )
    return payload_document, receipt


def _cycle_labels(text: str) -> set[int]:
    return {
        int(match)
        for pattern in _CYCLE_LABELS
        for match in pattern.findall(text)
    }


def _reject_position_numbers(*texts: str) -> None:
    joined = " ".join(texts)
    if any(pattern.search(joined) for pattern in _UNSTRUCTURED_POSITION_PATTERNS):
        raise WindowReliabilityError(
            "CURRENT_CYCLE_UNSTRUCTURED_POSITION_TRUTH_FORBIDDEN"
        )


def _public_text_values(value: Any, *, excluded_keys: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """Collect public Agent-authored strings without treating identifiers as prose."""

    if isinstance(value, Mapping):
        rows: list[str] = []
        for key, nested in value.items():
            if key in excluded_keys or key.endswith("_digest") or key.endswith("_id"):
                continue
            rows.extend(_public_text_values(nested, excluded_keys=excluded_keys))
        return tuple(rows)
    if isinstance(value, (list, tuple)):
        return tuple(
            text
            for nested in value
            for text in _public_text_values(nested, excluded_keys=excluded_keys)
        )
    return (value,) if isinstance(value, str) else ()


def build_current_cycle_grounding_receipt(
    *,
    agent_context: Mapping[str, Any],
    agent_proposal: Mapping[str, Any],
    public_inference_trace: Mapping[str, Any],
    action_evaluation: Mapping[str, Any],
    deliberation: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    """Mechanically reject stale-cycle and stale-lot Agent content."""

    context_digest = _verified(
        agent_context, "agent_context_digest", "GROUNDING_CONTEXT_DIGEST_INVALID"
    )
    proposal_digest = _verified(
        agent_proposal, "agent_proposal_digest", "GROUNDING_PROPOSAL_DIGEST_INVALID"
    )
    inference_digest = _verified(
        public_inference_trace,
        "public_inference_trace_digest",
        "GROUNDING_INFERENCE_DIGEST_INVALID",
    )
    evaluation_digest = _verified(
        action_evaluation,
        "action_evaluation_digest",
        "GROUNDING_EVALUATION_DIGEST_INVALID",
    )
    deliberation_digest = _verified(
        deliberation, "deliberation_digest", "GROUNDING_DELIBERATION_DIGEST_INVALID"
    )
    selection_digest = _verified(
        selection, "action_selection_digest", "GROUNDING_SELECTION_DIGEST_INVALID"
    )
    run_id = str(agent_context.get("run_id") or "")
    cycle_index = agent_context.get("cycle_index")
    if (
        not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
        or any(
            document.get("run_id") != run_id
            or document.get("cycle_index") != cycle_index
            for document in (
                agent_proposal,
                public_inference_trace,
                action_evaluation,
                deliberation,
                selection,
            )
        )
        or agent_proposal.get("agent_context_digest") != context_digest
        or deliberation.get("action_evaluation_digest") != evaluation_digest
        or selection.get("action_evaluation_digest") != evaluation_digest
        or selection.get("agent_proposal_digest") != proposal_digest
    ):
        raise WindowReliabilityError("CURRENT_CYCLE_IDENTITY_MISMATCH")
    expected_prior = cycle_index - 1
    prior_index = agent_proposal.get("dynamic_update_from_cycle_index")
    summary = str(agent_proposal.get("dynamic_update_summary") or "").strip()
    if (
        isinstance(prior_index, bool)
        or prior_index != expected_prior
        or not summary
    ):
        raise WindowReliabilityError("CURRENT_CYCLE_PRIOR_LABEL_INVALID")
    labels = _cycle_labels(summary)
    if labels and labels != {expected_prior}:
        raise WindowReliabilityError("CURRENT_CYCLE_PRIOR_LABEL_CONFLICT")

    current_cycle_text = _public_text_values(
        agent_proposal,
        excluded_keys=frozenset({"dynamic_update_summary"}),
    ) + _public_text_values(public_inference_trace) + _public_text_values(
        deliberation
    ) + _public_text_values(selection)
    current_labels = {
        label for text in current_cycle_text for label in _cycle_labels(text)
    }
    if current_labels and current_labels != {cycle_index}:
        raise WindowReliabilityError("CURRENT_CYCLE_LABEL_CONFLICT")

    context_truth = build_lot_position_truth(
        symbol=str(action_evaluation.get("symbol") or ""),
        position_truth=agent_context.get("portfolio_truth", {}),
    )
    evaluation_truth = action_evaluation.get("position_truth")
    evaluation_truth_digest = _verified(
        evaluation_truth,
        "position_truth_digest",
        "CURRENT_CYCLE_POSITION_TRUTH_INVALID",
    )
    if evaluation_truth_digest != context_truth["position_truth_digest"]:
        raise WindowReliabilityError("CURRENT_CYCLE_POSITION_TRUTH_MISMATCH")
    valid_lot_ids = {str(row["lot_id"]) for row in evaluation_truth["lots"]}
    narrative_lot_ids = {
        lot_id
        for text in current_cycle_text
        for lot_id in _LOT_ID_PATTERN.findall(text)
    }
    if not narrative_lot_ids.issubset(valid_lot_ids):
        raise WindowReliabilityError("CURRENT_CYCLE_LOT_REFERENCE_STALE")
    _reject_position_numbers(*current_cycle_text)

    candidate_rows = agent_proposal.get("candidate_proposals")
    if not isinstance(candidate_rows, list) or not candidate_rows:
        raise WindowReliabilityError("CURRENT_CYCLE_CANDIDATES_MISSING")
    outcome_count = 0
    for candidate in candidate_rows:
        if (
            not isinstance(candidate, Mapping)
            or candidate.get("source_cycle_index") != cycle_index
        ):
            raise WindowReliabilityError("CURRENT_CYCLE_CANDIDATE_STALE")
        outcomes = candidate.get("path_outcomes")
        if not isinstance(outcomes, list) or not outcomes:
            raise WindowReliabilityError("CURRENT_CYCLE_OUTCOMES_MISSING")
        for outcome in outcomes:
            if (
                not isinstance(outcome, Mapping)
                or outcome.get("source_cycle_index") != cycle_index
                or outcome.get("position_truth_digest") != evaluation_truth_digest
            ):
                raise WindowReliabilityError("CURRENT_CYCLE_OUTCOME_STALE")
            texts = tuple(
                str(outcome.get(field) or "")
                for field in (
                    "position_consequence",
                    "market_process",
                    "failure_process",
                    "opportunity_cost",
                    "cost_risk_tradeoff",
                )
            )
            _reject_position_numbers(*texts)
            outcome_count += 1
    evaluation_by_id = {
        row.get("candidate_id"): row
        for row in action_evaluation.get("candidates", [])
        if isinstance(row, Mapping)
    }
    if set(evaluation_by_id) != {
        str(row.get("candidate_id") or "") for row in candidate_rows
    } or any(
        row.get("source_cycle_index") != cycle_index
        or row.get("position_truth_digest") != evaluation_truth_digest
        for row in evaluation_by_id.values()
    ):
        raise WindowReliabilityError("CURRENT_CYCLE_EVALUATION_GROUNDING_INVALID")
    return self_digest(
        {
            "schema_id": "current_cycle_semantic_grounding_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "expected_prior_cycle_index": expected_prior,
            "agent_context_digest": context_digest,
            "agent_proposal_digest": proposal_digest,
            "public_inference_trace_digest": inference_digest,
            "action_evaluation_digest": evaluation_digest,
            "deliberation_digest": deliberation_digest,
            "action_selection_digest": selection_digest,
            "position_truth_digest": evaluation_truth_digest,
            "candidate_count": len(candidate_rows),
            "path_outcome_count": outcome_count,
            "stale_cycle_reference_count": 0,
            "unstructured_position_fact_count": 0,
            "verdict": "PASS",
        },
        "current_cycle_grounding_digest",
    )


def build_preaccept_validation_receipt(
    *,
    resume_capsule: Mapping[str, Any],
    input_plan: Mapping[str, Any],
    agent_context: Mapping[str, Any],
    proposal_delivery_receipt: Mapping[str, Any],
    agent_proposal: Mapping[str, Any],
    public_inference_trace: Mapping[str, Any],
    action_evaluation: Mapping[str, Any],
    deliberation_delivery_receipt: Mapping[str, Any],
    deliberation: Mapping[str, Any],
    selection: Mapping[str, Any],
    risk_decision: Mapping[str, Any],
    decision: Mapping[str, Any],
    grounding_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the mandatory atomic gate immediately before STATE_ACCEPTED."""

    bindings = {
        "resume_capsule_digest": _verified(
            resume_capsule,
            "resume_capsule_digest",
            "PREACCEPT_RESUME_CAPSULE_INVALID",
        ),
        "agent_input_plan_digest": _verified(
            input_plan,
            "agent_input_plan_digest",
            "PREACCEPT_INPUT_PLAN_INVALID",
        ),
        "agent_context_digest": _verified(
            agent_context,
            "agent_context_digest",
            "PREACCEPT_CONTEXT_INVALID",
        ),
        "proposal_delivery_receipt_digest": _verified(
            proposal_delivery_receipt,
            "agent_delivery_receipt_digest",
            "PREACCEPT_PROPOSAL_DELIVERY_INVALID",
        ),
        "agent_proposal_digest": _verified(
            agent_proposal,
            "agent_proposal_digest",
            "PREACCEPT_PROPOSAL_INVALID",
        ),
        "public_inference_trace_digest": _verified(
            public_inference_trace,
            "public_inference_trace_digest",
            "PREACCEPT_INFERENCE_INVALID",
        ),
        "action_evaluation_digest": _verified(
            action_evaluation,
            "action_evaluation_digest",
            "PREACCEPT_EVALUATION_INVALID",
        ),
        "deliberation_delivery_receipt_digest": _verified(
            deliberation_delivery_receipt,
            "agent_delivery_receipt_digest",
            "PREACCEPT_DELIBERATION_DELIVERY_INVALID",
        ),
        "deliberation_digest": _verified(
            deliberation,
            "deliberation_digest",
            "PREACCEPT_DELIBERATION_INVALID",
        ),
        "action_selection_digest": _verified(
            selection,
            "action_selection_digest",
            "PREACCEPT_SELECTION_INVALID",
        ),
        "risk_decision_digest": _verified(
            risk_decision,
            "risk_decision_digest",
            "PREACCEPT_RISK_INVALID",
        ),
        "decision_digest": _verified(
            decision, "decision_digest", "PREACCEPT_DECISION_INVALID"
        ),
        "current_cycle_grounding_digest": _verified(
            grounding_receipt,
            "current_cycle_grounding_digest",
            "PREACCEPT_GROUNDING_INVALID",
        ),
    }
    run_id = str(agent_context.get("run_id") or "")
    cycle_index = agent_context.get("cycle_index")
    if (
        not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or resume_capsule.get("run_id") != run_id
        or resume_capsule.get("next_cycle_index") != cycle_index
        or input_plan.get("agent_context_digest") != bindings["agent_context_digest"]
        or agent_proposal.get("agent_context_digest")
        != bindings["agent_context_digest"]
        or agent_proposal.get("agent_delivery_receipt_digest")
        != bindings["proposal_delivery_receipt_digest"]
        or proposal_delivery_receipt.get("payload_digest")
        != canonical_digest(
            {
                key: value
                for key, value in agent_proposal.items()
                if key
                not in {
                    "schema_id",
                    "schema_version",
                    "run_id",
                    "cycle_index",
                    "agent_context_digest",
                    "agent_delivery_receipt_digest",
                    "agent_delivery_receipt_ref",
                    "agent_delivery_receipt",
                    "selection_present_before_evaluation",
                    "external_execution_authority",
                    "executable",
                    "agent_proposal_digest",
                }
            }
        )
        or deliberation.get("action_evaluation_digest")
        != bindings["action_evaluation_digest"]
        or deliberation.get("agent_delivery_receipt_digest")
        != bindings["deliberation_delivery_receipt_digest"]
        or deliberation_delivery_receipt.get("payload_digest")
        != canonical_digest(
            {
                key: value
                for key, value in deliberation.items()
                if key
                not in {
                    "schema_id",
                    "schema_version",
                    "run_id",
                    "cycle_index",
                    "action_evaluation_digest",
                    "agent_delivery_receipt_digest",
                    "agent_delivery_receipt_ref",
                    "agent_delivery_receipt",
                    "deliberation_digest",
                }
            }
        )
        or selection.get("action_evaluation_digest")
        != bindings["action_evaluation_digest"]
        or risk_decision.get("action_selection_digest")
        != bindings["action_selection_digest"]
        or decision.get("action_selection_digest")
        != bindings["action_selection_digest"]
        or decision.get("risk_decision_digest") != bindings["risk_decision_digest"]
        or risk_decision.get("approved") is not True
        or grounding_receipt.get("verdict") != "PASS"
        or input_plan.get("preflight_verdict") != "PASS"
        or resume_capsule.get("chat_history_is_authority") is not False
    ):
        raise WindowReliabilityError("PREACCEPT_BINDING_OR_VERDICT_INVALID")
    return self_digest(
        {
            "schema_id": "preaccept_atomic_validation_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "artifact_bindings": dict(sorted(bindings.items())),
            "all_agent_deliveries_complete": True,
            "current_cycle_grounding_verified": True,
            "risk_approved": True,
            "accepted_head_mutation_authorized": True,
            "report_or_review_required_for_semantic_acceptance": False,
            "post_accept_agent_reinvocation_allowed": False,
            "verdict": "PASS",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "preaccept_validation_receipt_digest",
    )


def build_controller_reconciliation(
    *,
    controller_id: str,
    command_id: str,
    observed_at: str,
    desired_state: str,
    actual_state: str,
    lease_id: str | None,
    lease_expires_at: str | None,
    kill_switch_engaged: bool,
) -> dict[str, Any]:
    """Separate controller intent from observed control-plane reality."""

    observed = _timestamp(observed_at, "CONTROLLER_OBSERVED_TIME_INVALID")
    if (
        not controller_id
        or not command_id
        or desired_state not in {"RUNNING", "PAUSED", "DELETED"}
        or actual_state not in {"ACTIVE", "PAUSED", "ABSENT", "UNKNOWN"}
        or not isinstance(kill_switch_engaged, bool)
    ):
        raise WindowReliabilityError("CONTROLLER_STATE_INVALID")
    lease_valid = False
    if desired_state == "RUNNING":
        if not lease_id or not lease_expires_at:
            raise WindowReliabilityError("CONTROLLER_RUNNING_LEASE_REQUIRED")
        lease_valid = _timestamp(
            lease_expires_at, "CONTROLLER_LEASE_TIME_INVALID"
        ) > observed
    elif lease_id is not None or lease_expires_at is not None:
        raise WindowReliabilityError("CONTROLLER_STOPPED_LEASE_FORBIDDEN")
    expected_actual = {
        "RUNNING": "ACTIVE",
        "PAUSED": "PAUSED",
        "DELETED": "ABSENT",
    }[desired_state]
    converged = actual_state == expected_actual
    run_permission = (
        desired_state == "RUNNING"
        and actual_state == "ACTIVE"
        and lease_valid
        and not kill_switch_engaged
    )
    if run_permission:
        next_action = "NOOP_LEASE_VALID"
    elif desired_state == "DELETED" and actual_state != "ABSENT":
        next_action = "REISSUE_IDEMPOTENT_DELETE_AND_VERIFY"
    elif desired_state == "PAUSED" and actual_state not in {"PAUSED", "ABSENT"}:
        next_action = "REISSUE_IDEMPOTENT_PAUSE_AND_VERIFY"
    elif desired_state == "RUNNING" and actual_state != "ACTIVE":
        next_action = "DO_NOT_RUN_RECONCILE_CONTROLLER"
    else:
        next_action = "NOOP_STOPPED"
    return self_digest(
        {
            "schema_id": "controller_desired_actual_reconciliation",
            "schema_version": "1.0.0",
            "controller_id": controller_id,
            "command_id": command_id,
            "observed_at": observed_at,
            "desired_state": desired_state,
            "actual_state": actual_state,
            "expected_actual_state": expected_actual,
            "state_converged": converged,
            "lease_id": lease_id,
            "lease_expires_at": lease_expires_at,
            "lease_valid": lease_valid,
            "kill_switch_engaged": kill_switch_engaged,
            "run_permission": run_permission,
            "next_action": next_action,
            "idempotency_key": canonical_digest(
                {
                    "controller_id": controller_id,
                    "command_id": command_id,
                    "desired_state": desired_state,
                }
            ),
            "actual_state_is_not_inferred_from_desired_state": True,
        },
        "controller_reconciliation_digest",
    )


def classify_reliability_failure(
    *,
    run_id: str,
    cycle_index: int,
    phase: str,
    reason_code: str,
    accepted_state_exists: bool,
) -> dict[str, Any]:
    """Return a stable failure class and legal recovery disposition."""

    if not run_id or cycle_index < 1 or not phase or not reason_code:
        raise WindowReliabilityError("RELIABILITY_FAILURE_IDENTITY_INVALID")
    if reason_code.startswith("AGENT_INPUT_"):
        failure_type = "INPUT_BUDGET_OR_REQUIRED_SECTION_FAILURE"
        recoverable_class = True
    elif reason_code.startswith("RESUME_"):
        failure_type = "RESUME_AUTHORITY_CONTRACT_FAILURE"
        recoverable_class = False
    elif reason_code.startswith(("AGENT_DELIVERY_", "AGENT_OUTPUT_")):
        failure_type = "AGENT_DELIVERY_INCOMPLETE"
        recoverable_class = True
    elif reason_code.startswith(("CURRENT_CYCLE_", "PREACCEPT_")):
        failure_type = "CURRENT_CYCLE_GROUNDING_OR_PREACCEPT_FAILURE"
        recoverable_class = False
    elif reason_code.startswith("POST_ACCEPT_"):
        failure_type = "POST_ACCEPT_DETERMINISTIC_TAIL_FAILURE"
        recoverable_class = True
    elif reason_code.startswith("CONTROLLER_"):
        failure_type = "CONTROLLER_STATE_DIVERGENCE"
        recoverable_class = False
    else:
        failure_type = "TYPED_UNCLASSIFIED_RELIABILITY_FAILURE"
        recoverable_class = False
    resume_allowed = recoverable_class and (
        not accepted_state_exists
        or failure_type == "POST_ACCEPT_DETERMINISTIC_TAIL_FAILURE"
    )
    return self_digest(
        {
            "schema_id": "typed_reliability_failure",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "phase": phase,
            "reason_code": reason_code,
            "failure_type": failure_type,
            "accepted_state_exists": accepted_state_exists,
            "resume_allowed": resume_allowed,
            "recovery_disposition": (
                "DETERMINISTIC_TAIL_ONLY_AGENT_REINVOCATION_FORBIDDEN"
                if resume_allowed and accepted_state_exists
                else "CONTINUE_ONLY_FROM_SEALED_INPUTS"
                if resume_allowed
                else "FAIL_CLOSED_NO_AGENT_REINVOCATION"
            ),
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "reliability_failure_digest",
    )


__all__ = [
    "WindowReliabilityError",
    "build_agent_input_plan",
    "build_bounded_prior_state_view",
    "build_controller_reconciliation",
    "build_current_cycle_grounding_receipt",
    "build_preaccept_validation_receipt",
    "build_resume_capsule",
    "classify_reliability_failure",
    "validate_agent_delivery",
]
