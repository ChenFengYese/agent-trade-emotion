"""Fact-only Review construction for an Agent-first market cycle."""

from __future__ import annotations

from .contracts import (
    ArtifactRef,
    BehaviorPlan,
    MarketCycleContractError,
    Outcome,
    Review,
    _parse_timestamp,
)
from .theory import TheoryIdentity


def build_review(
    plan: BehaviorPlan,
    behavior_plan_ref: ArtifactRef,
    outcome: Outcome,
    outcome_ref: ArtifactRef,
    *,
    review_id: str,
    reviewed_at: str,
    agent_review_delivered_at: str,
    agent_review_request_sha256: str,
    agent_review_delivery_path: str,
    agent_review_delivery_sha256: str,
    agent_review_text: str,
    agent_review_size_bytes: int,
    agent_review_sha256: str,
    agent_review_theory_identity: TheoryIdentity,
) -> Review:
    """Seal Outcome facts without inventing an Agent semantic assessment.

    The system-owned section is a faithful projection of the immutable
    ``Outcome``.  The Agent owns all review semantics, which remain in separate
    verbatim provenance fields.  Missing decision structure never prevents
    creation of the Review.
    """

    if behavior_plan_ref.artifact_type != "BehaviorPlan":
        raise MarketCycleContractError(
            "behavior_plan_ref must identify BehaviorPlan"
        )
    if behavior_plan_ref.artifact_id != plan.plan_id:
        raise MarketCycleContractError(
            "behavior_plan_ref does not identify supplied plan"
        )
    if outcome_ref.artifact_type != "Outcome":
        raise MarketCycleContractError("outcome_ref must identify Outcome")
    if outcome_ref.artifact_id != outcome.outcome_id:
        raise MarketCycleContractError(
            "outcome_ref does not identify supplied outcome"
        )
    if outcome.behavior_plan_ref != behavior_plan_ref:
        raise MarketCycleContractError(
            "Outcome is not bound to the supplied BehaviorPlan"
        )
    if plan.cycle_id != outcome.cycle_id:
        raise MarketCycleContractError(
            "Review inputs must belong to the same cycle"
        )
    if plan.theory_identity != outcome.theory_identity:
        raise MarketCycleContractError(
            "Review inputs must bind the same theory identity"
        )
    if (
        not isinstance(agent_review_theory_identity, TheoryIdentity)
        or agent_review_theory_identity != plan.theory_identity
    ):
        raise MarketCycleContractError(
            "Agent Review must bind the same theory identity"
        )
    reviewed = _parse_timestamp(reviewed_at, field_name="reviewed_at")
    delivered = _parse_timestamp(
        agent_review_delivered_at,
        field_name="agent_review_delivered_at",
    )
    outcome_sealed = _parse_timestamp(
        outcome.sealed_at, field_name="outcome.sealed_at"
    )
    if reviewed != delivered:
        raise MarketCycleContractError(
            "reviewed_at must equal agent_review_delivered_at"
        )
    if delivered < outcome_sealed:
        raise MarketCycleContractError("Review cannot precede sealed Outcome")

    system_facts = {
        "outcome_status": outcome.terminal_status,
        "typed_missing": outcome.typed_missing,
        "endpoint_observation": outcome.endpoint_observation,
        "path_observations": outcome.path_observations,
        "outcome_raw_refs": [reference.to_dict() for reference in outcome.raw_refs],
    }

    return Review(
        review_id=review_id,
        cycle_id=plan.cycle_id,
        behavior_plan_ref=behavior_plan_ref,
        outcome_ref=outcome_ref,
        reviewed_at=reviewed_at,
        outcome_status=outcome.terminal_status,
        agent_decision_sha256=plan.agent_decision_sha256,
        projection_status=plan.projection_status,
        projection_reason=plan.projection_reason,
        system_facts=system_facts,
        agent_review_delivered_at=agent_review_delivered_at,
        agent_review_request_sha256=agent_review_request_sha256,
        agent_review_delivery_path=agent_review_delivery_path,
        agent_review_delivery_sha256=agent_review_delivery_sha256,
        agent_review_text=agent_review_text,
        agent_review_size_bytes=agent_review_size_bytes,
        agent_review_sha256=agent_review_sha256,
        theory_writeback=False,
        theory_identity=plan.theory_identity,
    )


__all__ = ["build_review"]
