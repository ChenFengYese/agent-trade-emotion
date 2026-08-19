"""Pure builder used after Infrastructure has verified one completed cycle.

This module is deliberately not a provenance boundary.  The public entry point
is Infrastructure's runtime-bound evaluator, which obtains every value from a
verified ``MarketCycleRuntime`` and replays an observed Outcome from sealed raw
bytes before calling this builder.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
from typing import Any, Mapping

from ...domain.contracts.canonical import (
    canonical_bytes,
    canonical_decimal,
    canonical_digest,
)
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
    Outcome,
    Review,
)
from ...domain.market_cycle.evaluation import (
    OPERATIONAL_EVALUATION_DIMENSIONS,
    OperationalEvaluationContractError,
    OperationalEvaluationFactsV1,
)
from ...domain.market_cycle.evidence import EvidencePolicy


def _timestamp(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise OperationalEvaluationContractError(f"{field} is not a timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperationalEvaluationContractError(f"{field} lacks a UTC offset")
    return parsed


def _decimal(value: object, *, field: str, positive: bool = False) -> Decimal:
    if type(value) is not str:
        raise OperationalEvaluationContractError(f"{field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OperationalEvaluationContractError(f"{field} must be a decimal string") from exc
    if not parsed.is_finite() or canonical_decimal(parsed) != value:
        raise OperationalEvaluationContractError(f"{field} must be canonical")
    if positive and parsed <= 0:
        raise OperationalEvaluationContractError(f"{field} must be positive")
    return parsed


def _run_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    """Detach one manifest identity document supplied by the runtime gate."""

    if not isinstance(value, Mapping):
        raise OperationalEvaluationContractError("run_identity must be an object")
    return {str(key): item for key, item in value.items()}


def _require_artifact_ref(
    reference: ArtifactRef, *, artifact_type: str, artifact: object, artifact_id: str
) -> None:
    if (
        not isinstance(reference, ArtifactRef)
        or reference.artifact_type != artifact_type
        or reference.artifact_id != artifact_id
    ):
        raise OperationalEvaluationContractError(
            f"{artifact_type} reference does not bind the supplied artifact"
        )
    to_dict = getattr(artifact, "to_dict", None)
    if not callable(to_dict):
        raise OperationalEvaluationContractError(f"{artifact_type} is not serializable")
    payload = canonical_bytes(to_dict())
    if reference.size_bytes != len(payload) or reference.sha256 != hashlib.sha256(
        payload
    ).hexdigest():
        raise OperationalEvaluationContractError(
            f"{artifact_type} reference digest does not bind the supplied artifact"
        )


def _validate_cycle_chain(
    *,
    cycle_id: str,
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
    hypothesis: HypothesisRecord,
    hypothesis_ref: ArtifactRef,
    plan: BehaviorPlan,
    plan_ref: ArtifactRef,
    outcome: Outcome,
    outcome_ref: ArtifactRef,
    review: Review,
    review_ref: ArtifactRef,
) -> None:
    if any(
        artifact.cycle_id != cycle_id
        for artifact in (snapshot, hypothesis, plan, outcome, review)
    ):
        raise OperationalEvaluationContractError("cycle artifact identity mismatch")
    identities = {
        tuple(artifact.theory_identity.to_dict().items())
        for artifact in (snapshot, hypothesis, plan, outcome, review)
    }
    if len(identities) != 1:
        raise OperationalEvaluationContractError("cycle theory identity mismatch")
    _require_artifact_ref(
        snapshot_ref,
        artifact_type="InputSnapshot",
        artifact=snapshot,
        artifact_id=snapshot.snapshot_id,
    )
    _require_artifact_ref(
        hypothesis_ref,
        artifact_type="HypothesisRecord",
        artifact=hypothesis,
        artifact_id=hypothesis.record_id,
    )
    _require_artifact_ref(
        plan_ref, artifact_type="BehaviorPlan", artifact=plan, artifact_id=plan.plan_id
    )
    _require_artifact_ref(
        outcome_ref, artifact_type="Outcome", artifact=outcome, artifact_id=outcome.outcome_id
    )
    _require_artifact_ref(
        review_ref, artifact_type="Review", artifact=review, artifact_id=review.review_id
    )
    if (
        hypothesis.input_snapshot_ref != snapshot_ref
        or plan.hypothesis_record_ref != hypothesis_ref
        or outcome.behavior_plan_ref != plan_ref
        or review.behavior_plan_ref != plan_ref
        or review.outcome_ref != outcome_ref
    ):
        raise OperationalEvaluationContractError("artifact predecessor chain mismatch")
    if not (
        hypothesis.agent_decision_sha256
        == plan.agent_decision_sha256
        == review.agent_decision_sha256
    ):
        raise OperationalEvaluationContractError("Agent decision binding mismatch")
    if outcome.terminal_status != review.outcome_status:
        raise OperationalEvaluationContractError("Outcome and Review status mismatch")


def _endpoint_measure(snapshot: InputSnapshot, outcome: Outcome) -> dict[str, Any]:
    mark_observation = snapshot.core_observations["mark_price"]
    decision_mark = _decimal(
        mark_observation.get("value"), field="snapshot.mark_price", positive=True
    )
    unit = mark_observation.get("unit")
    if type(unit) is not str or not unit:
        raise OperationalEvaluationContractError("snapshot mark unit is unavailable")
    if outcome.terminal_status == "TYPED_MISSING":
        return {
            "status": "TYPED_MISSING",
            "unit": unit,
            "decision_mark": canonical_decimal(decision_mark),
            "endpoint_mark": None,
            "absolute_change": None,
            "relative_change": None,
            "change_sign": None,
            "typed_missing": outcome.typed_missing,
        }

    endpoint = outcome.endpoint_observation
    assert endpoint is not None
    if endpoint.get("unit") != unit:
        raise OperationalEvaluationContractError("endpoint and decision mark units differ")
    endpoint_mark = _decimal(endpoint.get("value"), field="outcome.endpoint", positive=True)
    change = endpoint_mark - decision_mark
    with localcontext() as context:
        context.prec = 50
        relative_change = change / decision_mark
    return {
        "status": "OBSERVED",
        "unit": unit,
        "decision_mark": canonical_decimal(decision_mark),
        "endpoint_mark": canonical_decimal(endpoint_mark),
        "absolute_change": canonical_decimal(change),
        "relative_change": canonical_decimal(relative_change),
        "change_sign": "UP" if change > 0 else "DOWN" if change < 0 else "FLAT",
        "typed_missing": None,
    }


def _build_operational_evaluation_facts_from_verified_cycle(
    *,
    evaluation_id: str,
    evaluated_at: str,
    run_identity: Mapping[str, Any],
    evidence_policy: EvidencePolicy,
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
    hypothesis: HypothesisRecord,
    hypothesis_ref: ArtifactRef,
    plan: BehaviorPlan,
    plan_ref: ArtifactRef,
    outcome: Outcome,
    outcome_ref: ArtifactRef,
    review: Review,
    review_ref: ArtifactRef,
) -> OperationalEvaluationFactsV1:
    """Build deterministic facts from a provenance-verified cycle envelope."""

    if not isinstance(evidence_policy, EvidencePolicy):
        raise OperationalEvaluationContractError("evidence_policy is invalid")
    cycle_id = snapshot.cycle_id
    _validate_cycle_chain(
        cycle_id=cycle_id,
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
        hypothesis=hypothesis,
        hypothesis_ref=hypothesis_ref,
        plan=plan,
        plan_ref=plan_ref,
        outcome=outcome,
        outcome_ref=outcome_ref,
        review=review,
        review_ref=review_ref,
    )
    if _timestamp(evaluated_at, field="evaluated_at") < _timestamp(
        review.reviewed_at, field="review.reviewed_at"
    ):
        raise OperationalEvaluationContractError("evaluation precedes the sealed Review")

    detached_run_identity = _run_identity(run_identity)
    if detached_run_identity.get("theory_manifest_sha256") != snapshot.theory_identity.manifest_digest:
        raise OperationalEvaluationContractError("run and cycle theory manifests differ")
    if evidence_policy.theory_revision != snapshot.theory_identity.theory_revision:
        raise OperationalEvaluationContractError("policy and cycle theory revisions differ")

    endpoint_measure = _endpoint_measure(snapshot, outcome)
    path_status = outcome.path_observations.get("status")
    if path_status == "ORDERED":
        path_dimension = "ORDERED_CLOSED_15M_PATH_AVAILABLE_NOT_SCORED"
    elif path_status == "PARTIAL":
        path_dimension = "CENSORED_PARTIAL_ORDERED_FUTURE_PATH"
    else:
        path_dimension = "CENSORED_NO_ORDERED_FUTURE_PATH"
    dimension_statuses = {
        "market_state": "AGENT_REVIEW_AVAILABLE_NOT_SCORED",
        "direction": (
            "ENDPOINT_CHANGE_AVAILABLE_PREDICTION_NOT_SCORED"
            if outcome.terminal_status == "OBSERVED"
            else "NOT_EVALUATED_OUTCOME_MISSING"
        ),
        "path": path_dimension,
        "level": "CENSORED_NO_PATH_OR_PREREGISTERED_ZONE",
        "timing": "NOT_EVALUATED_NO_PREREGISTERED_EVENT_WINDOW",
        "mechanism": "NOT_EVALUATED_AGENT_REVIEW_ONLY",
        "action": "NOT_EVALUATED_NO_PREREGISTERED_COMPARATOR",
        "position": "NOT_EVALUATED_NO_PREREGISTERED_COMPARATOR",
        "transition": "NOT_EVALUATED_NO_PREREGISTERED_COMPARATOR",
        "risk": "NOT_EVALUATED_NO_PREREGISTERED_COMPARATOR",
        "churn": "NOT_EVALUATED_NO_PREREGISTERED_COMPARATOR",
        "reference_execution": "NOT_EVALUATED_E0_EXCLUDES_PAPER_FACTS",
        "actual_execution": "NOT_APPLICABLE_NOT_AUTHORIZED",
        "attention_runtime": "NOT_EVALUATED_E0_EXCLUDES_ATTENTION_FACTS",
    }
    if tuple(dimension_statuses) != OPERATIONAL_EVALUATION_DIMENSIONS:
        raise AssertionError("operational evaluation dimensions drifted")

    policy_document = evidence_policy.to_dict()
    return OperationalEvaluationFactsV1(
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at,
        run_identity=detached_run_identity,
        policy_binding={
            "document": policy_document,
            "sha256": canonical_digest(policy_document),
        },
        cycle_id=cycle_id,
        artifact_refs=(snapshot_ref, hypothesis_ref, plan_ref, outcome_ref, review_ref),
        input_raw_refs=snapshot.raw_refs,
        outcome_raw_refs=outcome.raw_refs,
        endpoint_measure=endpoint_measure,
        paper_head=None,
        attention_head=None,
        paper_facts={
            "status": "NOT_INCLUDED_IN_E0_OPERATIONAL_EVALUATION",
        },
        attention_facts={
            "status": "NOT_INCLUDED_IN_E0_OPERATIONAL_EVALUATION",
        },
        dimension_statuses=dimension_statuses,
        limitations=(
            "ENDPOINT_CHANGE_IS_NOT_PREDICTION_ACCURACY",
            (
                "ORDERED_15M_PATH_HAS_UNRESOLVED_INTRABAR_ORDER"
                if path_status == "ORDERED"
                else "NO_COMPLETE_ORDERED_FUTURE_PATH_OR_MAE_MFE"
            ),
            "NO_PREREGISTERED_ACTION_OR_POSITION_COMPARATOR",
            "PAPER_EXECUTION_IS_NOT_ACTUAL_EXECUTION",
            "NO_PROFITABILITY_OR_GENERALIZATION_CLAIM",
        ),
    )


__all__: list[str] = []
