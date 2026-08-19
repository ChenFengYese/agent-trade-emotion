"""Agent-owned review use case over a sealed plan and outcome."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from typing import Any, Mapping, Sequence

from ...domain.contracts.canonical import canonical_bytes
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
    MarketCycleContractError,
    Outcome,
    Review,
    VerifiedMemoryItem,
    snapshot_bound_memory_context,
)
from ...domain.market_cycle.evidence import calculate_multitimeframe_context
from ...domain.market_cycle.review import build_review
from ...domain.market_cycle.theory import TheoryIdentity
from .analysis import select_analysis_theory_fragments
from .ports import (
    AgentPort,
    AgentDecision,
    AgentReview,
    AgentReviewPacket,
    AgentReviewPending,
    ClockPort,
)


_REVIEW_TIME_BUDGET_SECONDS = 600


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise MarketCycleContractError(
            "review chronology requires ISO-8601 timestamps"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketCycleContractError("review timestamps require a UTC offset")
    return parsed


def review_cycle(
    plan: BehaviorPlan,
    plan_ref: ArtifactRef,
    outcome: Outcome,
    outcome_ref: ArtifactRef,
    *,
    input_snapshot: InputSnapshot,
    input_snapshot_ref: ArtifactRef,
    hypothesis_record: HypothesisRecord,
    hypothesis_record_ref: ArtifactRef,
    agent: AgentPort,
    clock: ClockPort,
    theory_fragments: Mapping[str, str],
    analysis_profile: str,
    decision_context: object | None = None,
    verified_memory: Sequence[VerifiedMemoryItem | Mapping[str, Any]] = (),
    token_budget: int = 8_000,
) -> Review:
    """Request and seal one verbatim Agent review without system conclusions."""

    if (
        input_snapshot.cycle_id != plan.cycle_id
        or hypothesis_record.cycle_id != plan.cycle_id
        or outcome.cycle_id != plan.cycle_id
        or analysis_profile != input_snapshot.analysis_profile
        or input_snapshot_ref.artifact_type != "InputSnapshot"
        or input_snapshot_ref.artifact_id != input_snapshot.snapshot_id
        or hypothesis_record_ref.artifact_type != "HypothesisRecord"
        or hypothesis_record_ref.artifact_id != hypothesis_record.record_id
        or plan_ref.artifact_type != "BehaviorPlan"
        or plan_ref.artifact_id != plan.plan_id
        or outcome_ref.artifact_type != "Outcome"
        or outcome_ref.artifact_id != outcome.outcome_id
        or hypothesis_record.input_snapshot_ref != input_snapshot_ref
        or plan.hypothesis_record_ref != hypothesis_record_ref
        or outcome.behavior_plan_ref != plan_ref
        or input_snapshot.theory_identity != hypothesis_record.theory_identity
        or hypothesis_record.theory_identity != plan.theory_identity
        or plan.theory_identity != outcome.theory_identity
        or plan.agent_delivered_at != hypothesis_record.agent_delivered_at
        or plan.agent_request_sha256 != hypothesis_record.agent_request_sha256
        or plan.agent_delivery_path != hypothesis_record.agent_delivery_path
        or plan.agent_delivery_sha256 != hypothesis_record.agent_delivery_sha256
        or plan.agent_decision_text != hypothesis_record.agent_decision_text
        or plan.agent_decision_size_bytes
        != hypothesis_record.agent_decision_size_bytes
        or plan.agent_decision_sha256 != hypothesis_record.agent_decision_sha256
        or plan.projection_status != hypothesis_record.projection_status
        or plan.projection_reason != hypothesis_record.projection_reason
        or plan.hypothesis_index != hypothesis_record.hypothesis_index
        or plan.agent_action_text != hypothesis_record.agent_action_text
        or plan.agent_position_text != hypothesis_record.agent_position_text
        or plan.outcome_tolerance_seconds
        != hypothesis_record.outcome_tolerance_seconds
    ):
        raise MarketCycleContractError(
            "AgentReview context chain does not match the sealed cycle"
        )
    agent_decision = AgentDecision(
        cycle_id=hypothesis_record.cycle_id,
        request_sha256=hypothesis_record.agent_request_sha256,
        theory_identity=hypothesis_record.theory_identity.to_dict(),
        delivered_at=hypothesis_record.agent_delivered_at,
        decision_text=hypothesis_record.agent_decision_text,
        decision_size_bytes=hypothesis_record.agent_decision_size_bytes,
        decision_sha256=hypothesis_record.agent_decision_sha256,
        delivery_path=hypothesis_record.agent_delivery_path,
        delivery_sha256=hypothesis_record.agent_delivery_sha256,
    )
    paper_review_context = None
    if decision_context is not None:
        builder = getattr(decision_context, "review_context", None)
        if not callable(builder):
            raise MarketCycleContractError(
                "AgentReview paper context provider is invalid"
            )
        paper_review_context = builder(
            input_snapshot,
            input_snapshot_ref,
            review_cutoff_at=outcome.sealed_at,
        )
    packet = AgentReviewPacket(
        cycle_id=plan.cycle_id,
        theory_identity=plan.theory_identity.to_dict(),
        theory_fragments=select_analysis_theory_fragments(
            theory_fragments,
            analysis_profile=analysis_profile,
            theory_identity=plan.theory_identity,
        ),
        input_snapshot_ref=input_snapshot_ref.to_dict(),
        input_snapshot=input_snapshot.to_dict(),
        agent_decision_ref={
            "transport_path": hypothesis_record.agent_delivery_path,
            "transport_sha256": hypothesis_record.agent_delivery_sha256,
            "decision_sha256": hypothesis_record.agent_decision_sha256,
        },
        agent_decision=agent_decision.to_dict(),
        hypothesis_record_ref=hypothesis_record_ref.to_dict(),
        hypothesis_record=hypothesis_record.to_dict(),
        behavior_plan_ref=plan_ref.to_dict(),
        behavior_plan=plan.to_dict(),
        outcome_ref=outcome_ref.to_dict(),
        outcome=outcome.to_dict(),
        memory_context=snapshot_bound_memory_context(
            input_snapshot, verified_memory
        ),
        deterministic_calculations=calculate_multitimeframe_context(
            input_snapshot, input_snapshot_ref
        ).to_dict(),
        paper_review_context=paper_review_context,
        token_budget=token_budget,
        time_budget_seconds=_REVIEW_TIME_BUDGET_SECONDS,
    )
    try:
        delivery = agent.review(packet)
    except AgentReviewPending:
        raise
    if not isinstance(delivery, AgentReview):
        raise MarketCycleContractError("AgentPort.review must return AgentReview")
    if (
        delivery.cycle_id != plan.cycle_id
        or delivery.theory_identity != plan.theory_identity.to_dict()
        or delivery.delivery_path != "transport/agent-review-delivery.json"
    ):
        raise MarketCycleContractError("AgentReview binding does not match plan")
    review_requested = _timestamp(delivery.review_requested_at)
    review_due = _timestamp(delivery.review_due_at)
    if (
        review_requested < _timestamp(outcome.sealed_at)
        or review_due
        != review_requested + timedelta(seconds=_REVIEW_TIME_BUDGET_SECONDS)
    ):
        raise MarketCycleContractError("AgentReview request window is invalid")
    expected_packet = {
        **packet.to_dict(),
        "review_requested_at": delivery.review_requested_at,
        "review_due_at": delivery.review_due_at,
    }
    expected_request_sha256 = hashlib.sha256(
        canonical_bytes(expected_packet)
    ).hexdigest()
    if delivery.request_sha256 != expected_request_sha256:
        raise MarketCycleContractError("AgentReview request binding is invalid")
    delivered_at = _timestamp(delivery.delivered_at)
    if not review_requested <= delivered_at < review_due:
        raise MarketCycleContractError(
            "AgentReview must be delivered after Outcome sealing and before review_due_at"
        )
    try:
        delivery_identity = TheoryIdentity.from_dict(delivery.theory_identity)
    except ValueError as exc:
        raise MarketCycleContractError("AgentReview theory identity is invalid") from exc
    return build_review(
        plan,
        plan_ref,
        outcome,
        outcome_ref,
        review_id=f"{plan.cycle_id}.review",
        reviewed_at=delivery.delivered_at,
        agent_review_delivered_at=delivery.delivered_at,
        agent_review_request_sha256=delivery.request_sha256,
        agent_review_delivery_path=delivery.delivery_path,
        agent_review_delivery_sha256=delivery.delivery_sha256,
        agent_review_text=delivery.review_text,
        agent_review_size_bytes=delivery.review_size_bytes,
        agent_review_sha256=delivery.review_sha256,
        agent_review_theory_identity=delivery_identity,
    )


__all__ = ["review_cycle"]
