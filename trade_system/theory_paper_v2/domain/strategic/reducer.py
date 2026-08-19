"""Pure strategic reducer and exposure/workflow projections."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from ..common import DomainError, DomainResult, ReducerStatus
from ..evidence import AdmittedEvidence, PromotionRequest, SignalClass
from ..policy import ActionIntent, GeometryOperation, ProtectiveActionType
from ..time_authority import ReviewClock
from .model import (
    CrossTimescaleLease,
    ExposureStatus,
    StrategicEpisode,
    StrategicStatus,
    WorkflowProjection,
)


@dataclass(frozen=True, slots=True)
class StrategicTransition:
    event_id: str
    expected_revision: int
    expected_state_digest: str
    requested_status: StrategicStatus
    next_state_digest: str
    next_review_clock: ReviewClock | None
    evidence: AdmittedEvidence | None = None
    promotion: PromotionRequest | None = None
    exact_premise_id: str | None = None
    hard_invalidator_id: str | None = None
    invalidation_receipt_present: bool = False
    close_rule_passed: bool = False
    orders_terminal: bool = False
    reconciliation_complete: bool = False
    reentry_terminal: bool = False


def derive_workflow_projection(episode: StrategicEpisode) -> WorkflowProjection:
    if episode.strategic_status is StrategicStatus.CLOSED:
        return WorkflowProjection.CLOSED
    if episode.strategic_status is StrategicStatus.INVALIDATED:
        return WorkflowProjection.INVALIDATED
    if (
        episode.exposure_status is ExposureStatus.FLAT
        and episode.reentry_contract_nonterminal
    ):
        return WorkflowProjection.REENTRY_PENDING
    if episode.strategic_status is StrategicStatus.CHALLENGED:
        return WorkflowProjection.CHALLENGED
    if episode.exposure_status is ExposureStatus.RISK_REDUCED:
        return WorkflowProjection.RISK_REDUCED
    return WorkflowProjection.ACTIVE


def derive_exposure_status(
    *,
    portfolio_truth_proven: bool,
    risk_within_reference_or_authorized: bool,
    accepted_nonterminal_exit: bool,
    reconciled_strategy_quantity_is_zero: bool,
    pending_exposure_quantity_is_zero: bool,
    current_frozen_risk_less_than_reference: bool,
) -> ExposureStatus:
    if not portfolio_truth_proven or not risk_within_reference_or_authorized:
        return ExposureStatus.RECONCILE_PENDING
    if accepted_nonterminal_exit:
        return ExposureStatus.EXIT_PENDING
    if reconciled_strategy_quantity_is_zero and pending_exposure_quantity_is_zero:
        return ExposureStatus.FLAT
    if current_frozen_risk_less_than_reference:
        return ExposureStatus.RISK_REDUCED
    return ExposureStatus.EXPOSED


def _failure(
    status: ReducerStatus, code: str, message: str, *, retryable: bool = False
) -> DomainResult[StrategicEpisode]:
    return DomainResult(
        status=status,
        error=DomainError(
            code=code,
            category="STRATEGIC",
            retryability="AFTER_INPUT_REPAIR" if retryable else "NEVER",
            message=message,
        ),
    )


def _challenge_authorized(
    prior: StrategicEpisode, transition: StrategicTransition
) -> bool:
    evidence = transition.evidence
    if evidence is None:
        return False
    if (
        transition.exact_premise_id is None
        or transition.exact_premise_id not in prior.premise_ids
        or transition.exact_premise_id not in evidence.record.premise_ids
    ):
        return False
    if evidence.strategic_authority:
        return True
    return transition.promotion is not None and transition.promotion.promoted


def reduce_strategic_episode(
    prior: StrategicEpisode,
    transition: StrategicTransition,
) -> DomainResult[StrategicEpisode]:
    """Apply only contract-authorized strategic transitions."""

    if (
        transition.expected_revision != prior.revision
        or transition.expected_state_digest != prior.state_digest
    ):
        return _failure(
            ReducerStatus.REJECTED,
            "STRATEGIC_PRIOR_HEAD_MISMATCH",
            "expected strategic head does not match accepted head",
        )
    requested = transition.requested_status
    current = prior.strategic_status
    if current is StrategicStatus.CLOSED or (
        current is StrategicStatus.INVALIDATED
        and requested is not StrategicStatus.CLOSED
    ):
        return _failure(
            ReducerStatus.REJECTED,
            "STRATEGIC_ILLEGAL_TRANSITION",
            "terminal strategic state cannot reactivate",
        )
    next_clock = transition.next_review_clock or prior.review_clock
    if requested is StrategicStatus.CHALLENGED:
        if current not in {StrategicStatus.ACTIVE, StrategicStatus.CHALLENGED}:
            return _failure(
                ReducerStatus.REJECTED,
                "STRATEGIC_ILLEGAL_TRANSITION",
                "challenge is not allowed from current state",
            )
        if not _challenge_authorized(prior, transition):
            return _failure(
                ReducerStatus.REJECTED,
                "STRATEGIC_PREMISE_MAPPING_MISSING",
                "challenge lacks exact strategic premise authority",
            )
        if transition.next_review_clock is None:
            return _failure(
                ReducerStatus.UNKNOWN,
                "STRATEGIC_TIME_AUTHORITY_MISSING",
                "challenge must establish the next strategic review",
                retryable=True,
            )
    elif requested is StrategicStatus.ACTIVE:
        if current is StrategicStatus.CHALLENGED and not _challenge_authorized(
            prior, transition
        ):
            return _failure(
                ReducerStatus.REJECTED,
                "STRATEGIC_PREMISE_MAPPING_MISSING",
                "challenge resolution lacks equal-or-higher authority",
            )
        if current not in {StrategicStatus.ACTIVE, StrategicStatus.CHALLENGED}:
            return _failure(
                ReducerStatus.REJECTED,
                "STRATEGIC_ILLEGAL_TRANSITION",
                "ACTIVE transition is not allowed from current state",
            )
    elif requested is StrategicStatus.INVALIDATED:
        if (
            transition.hard_invalidator_id not in prior.hard_invalidator_ids
            or not transition.invalidation_receipt_present
        ):
            return _failure(
                ReducerStatus.REJECTED,
                "STRATEGIC_INVALIDATOR_UNREGISTERED",
                "registered hard invalidator and receipt are both required",
            )
    elif requested is StrategicStatus.CLOSED:
        if not (
            transition.close_rule_passed
            and prior.exposure_status is ExposureStatus.FLAT
            and transition.orders_terminal
            and transition.reconciliation_complete
            and transition.reentry_terminal
        ):
            return _failure(
                ReducerStatus.REJECTED,
                "STRATEGIC_CLOSE_PRECONDITION_FAILED",
                "close preconditions are incomplete",
            )
    else:
        return _failure(
            ReducerStatus.REJECTED,
            "STRATEGIC_ILLEGAL_TRANSITION",
            "unknown strategic transition",
        )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=replace(
            prior,
            revision=prior.revision + 1,
            previous_state_digest=prior.state_digest,
            state_digest=transition.next_state_digest,
            strategic_status=requested,
            review_clock=next_clock,
        ),
        evaluated_event_id=transition.event_id,
    )


def validate_fast_action(
    episode: StrategicEpisode,
    lease: CrossTimescaleLease,
    *,
    decision_cutoff: datetime,
    action_intent: ActionIntent,
    protective_action: ProtectiveActionType,
    geometry_operation: GeometryOperation,
    requests_strategic_mutation: bool = False,
) -> DomainResult[ActionIntent]:
    """Enforce the one-way strategic-to-fast execution authority boundary."""

    if decision_cutoff.tzinfo is None:
        return DomainResult(
            status=ReducerStatus.UNKNOWN,
            error=DomainError(
                "CLOCK_TIME_INVALID",
                "CLOCK",
                "AFTER_INPUT_REPAIR",
                "decision cutoff must be timezone-aware",
            ),
        )
    valid_identity = (
        lease.strategic_episode_id == episode.episode_id
        and lease.strategic_state_digest == episode.state_digest
        and lease.strategic_state_revision == episode.revision
    )
    valid_time = lease.valid_from <= decision_cutoff < lease.valid_until
    if requests_strategic_mutation:
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                "LOWER_TIMEFRAME_STRATEGIC_MUTATION_FORBIDDEN",
                "STRATEGIC",
                "NEVER",
                "lower timeframe cannot emit a strategic transition",
            ),
        )
    if not valid_identity or not valid_time:
        if action_intent is lease.terminal_safe_action_intent:
            return DomainResult(status=ReducerStatus.APPLIED, value=action_intent)
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                "CROSS_TIMESCALE_LEASE_CURRENT",
                "STRATEGIC",
                "AFTER_INPUT_REPAIR",
                "lease invalid; only the registered nonpositive terminal action is allowed",
            ),
        )
    if (
        action_intent not in lease.permitted_fast_action_intents
        or protective_action not in lease.permitted_protective_actions
        or geometry_operation not in lease.permitted_geometry_operations
    ):
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                "LOWER_TIMEFRAME_STRATEGIC_MUTATION_FORBIDDEN",
                "STRATEGIC",
                "NEVER",
                "requested facets exceed leased permissions",
            ),
        )
    return DomainResult(status=ReducerStatus.APPLIED, value=action_intent)

