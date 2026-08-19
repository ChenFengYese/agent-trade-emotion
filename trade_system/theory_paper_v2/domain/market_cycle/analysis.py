"""Pure Agent-first record and plan construction for market cycles.

The Agent's UTF-8 decision text is the semantic authority.  Structured hints
are optional, non-authoritative projections: an incomplete or unparseable
projection becomes ``UNKNOWN`` and never rejects an otherwise valid delivery.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .contracts import (
    AGENT_OUTPUT_INCOMPLETE,
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
    MarketCycleContractError,
    _agent_text_bytes,
    _parse_timestamp,
)


def _projection(
    decision_text: str,
    *,
    hypothesis_index: Any = (),
    agent_action_text: Any = None,
    agent_position_text: Any = None,
) -> tuple[str, str | None, tuple[str, ...], str | None, str | None]:
    """Return a best-effort non-authoritative projection without raising.

    Action and position hints are retained only when they are exact spans of
    the authoritative decision text.  Missing or malformed hints degrade the
    whole projection to ``UNKNOWN`` while any independently verified span is
    still preserved for quality review.
    """

    if isinstance(hypothesis_index, (list, tuple)):
        index_values = tuple(
            item
            for item in hypothesis_index
            if isinstance(item, str) and item.strip()
        )
        index_complete = len(index_values) == len(hypothesis_index)
    else:
        index_values = ()
        index_complete = False

    action_text = (
        agent_action_text
        if isinstance(agent_action_text, str)
        and agent_action_text.strip()
        and agent_action_text in decision_text
        else None
    )
    position_text = (
        agent_position_text
        if isinstance(agent_position_text, str)
        and agent_position_text.strip()
        and agent_position_text in decision_text
        else None
    )
    if index_complete and index_values and action_text is not None and position_text is not None:
        return "AVAILABLE", None, index_values, action_text, position_text
    return (
        "UNKNOWN",
        AGENT_OUTPUT_INCOMPLETE,
        index_values if index_complete else (),
        action_text,
        position_text,
    )


def _unknowns(value: Any, *, projection_status: str) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        normalized = {
            item for item in value if isinstance(item, str) and item.strip()
        }
    else:
        normalized = set()
    if projection_status == "UNKNOWN":
        normalized.add(AGENT_OUTPUT_INCOMPLETE)
    return tuple(sorted(normalized))


def record_agent_decision(
    snapshot: InputSnapshot,
    input_snapshot_ref: ArtifactRef,
    *,
    record_id: str,
    sealed_at: str,
    agent_delivered_at: str,
    agent_request_sha256: str,
    agent_delivery_path: str,
    agent_delivery_sha256: str,
    agent_decision_text: str,
    agent_decision_size_bytes: int,
    agent_decision_sha256: str,
    hypothesis_index: Any = (),
    agent_action_text: Any = None,
    agent_position_text: Any = None,
    unresolved_unknowns: Any = (),
) -> HypothesisRecord:
    """Seal one verbatim Agent decision and a best-effort optional index."""

    if input_snapshot_ref.artifact_type != "InputSnapshot":
        raise MarketCycleContractError(
            "input_snapshot_ref must identify InputSnapshot"
        )
    if input_snapshot_ref.artifact_id != snapshot.snapshot_id:
        raise MarketCycleContractError(
            "input_snapshot_ref does not identify the supplied snapshot"
        )
    _agent_text_bytes(agent_decision_text, field_name="agent_decision_text")
    (
        projection_status,
        projection_reason,
        normalized_index,
        normalized_action,
        normalized_position,
    ) = _projection(
        agent_decision_text,
        hypothesis_index=hypothesis_index,
        agent_action_text=agent_action_text,
        agent_position_text=agent_position_text,
    )
    return HypothesisRecord(
        record_id=record_id,
        cycle_id=snapshot.cycle_id,
        input_snapshot_ref=input_snapshot_ref,
        decision_at=snapshot.decision_at,
        agent_delivered_at=agent_delivered_at,
        sealed_at=sealed_at,
        outcome_horizon_seconds=snapshot.outcome_horizon_seconds,
        outcome_tolerance_seconds=snapshot.outcome_tolerance_seconds,
        agent_request_sha256=agent_request_sha256,
        agent_delivery_path=agent_delivery_path,
        agent_delivery_sha256=agent_delivery_sha256,
        agent_decision_text=agent_decision_text,
        agent_decision_size_bytes=agent_decision_size_bytes,
        agent_decision_sha256=agent_decision_sha256,
        projection_status=projection_status,
        projection_reason=projection_reason,
        hypothesis_index=normalized_index,
        agent_action_text=normalized_action,
        agent_position_text=normalized_position,
        lawful_actions=snapshot.lawful_actions,
        unresolved_unknowns=_unknowns(
            unresolved_unknowns, projection_status=projection_status
        ),
        theory_identity=snapshot.theory_identity,
    )


def copy_agent_decision_to_behavior_plan(
    record: HypothesisRecord,
    hypothesis_record_ref: ArtifactRef,
    *,
    plan_id: str,
    sealed_at: str,
) -> BehaviorPlan:
    """Copy the Agent decision byte-for-byte into a non-executable plan.

    This function does not compare, normalize, select, or manufacture an
    action or position.  It binds only immutable provenance, the verbatim
    decision, optional exact-span hints, and the preregistered outcome window.
    """

    if hypothesis_record_ref.artifact_type != "HypothesisRecord":
        raise MarketCycleContractError(
            "hypothesis_record_ref must identify HypothesisRecord"
        )
    if hypothesis_record_ref.artifact_id != record.record_id:
        raise MarketCycleContractError(
            "hypothesis_record_ref does not identify the supplied record"
        )
    decision_at = _parse_timestamp(record.decision_at, field_name="decision_at")
    outcome_due_at = (
        decision_at + timedelta(seconds=record.outcome_horizon_seconds)
    ).isoformat()
    return BehaviorPlan(
        plan_id=plan_id,
        cycle_id=record.cycle_id,
        hypothesis_record_ref=hypothesis_record_ref,
        decision_at=record.decision_at,
        agent_delivered_at=record.agent_delivered_at,
        sealed_at=sealed_at,
        risk_mode="REFERENCE",
        execution_mapping="NOT_READY",
        executable_quantity=None,
        agent_request_sha256=record.agent_request_sha256,
        agent_delivery_path=record.agent_delivery_path,
        agent_delivery_sha256=record.agent_delivery_sha256,
        agent_decision_text=record.agent_decision_text,
        agent_decision_size_bytes=record.agent_decision_size_bytes,
        agent_decision_sha256=record.agent_decision_sha256,
        projection_status=record.projection_status,
        projection_reason=record.projection_reason,
        hypothesis_index=record.hypothesis_index,
        agent_action_text=record.agent_action_text,
        agent_position_text=record.agent_position_text,
        outcome_due_at=outcome_due_at,
        outcome_tolerance_seconds=record.outcome_tolerance_seconds,
        theory_identity=record.theory_identity,
    )


__all__ = ["copy_agent_decision_to_behavior_plan", "record_agent_decision"]
