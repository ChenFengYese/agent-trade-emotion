"""Closed reentry state machine with bounded reviews and deferrals."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from ..common import DomainError, DomainResult, ReducerStatus
from ..strategic import StrategicStatus
from .model import (
    EligibilityVerdict,
    ReentryContract,
    ReentryEvaluation,
    ReentryStatus,
    TERMINAL_REENTRY_STATUSES,
)


def _error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> DomainResult[ReentryContract]:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if retryable else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="REENTRY",
            retryability="AFTER_INPUT_REPAIR" if retryable else "NEVER",
            message=message,
        ),
    )


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def open_reentry_contract(
    *,
    contract_id: str,
    strategic_episode_id: str,
    opened_at: datetime,
    earliest_review_at: datetime,
    latest_review_at: datetime,
    expires_at: datetime,
    maximum_deferrals: int | None,
    minimum_core_quantity: Decimal,
    strategic_status: StrategicStatus,
    authoritative_core_quantity: Decimal,
    atomic_create_effect_present: bool,
) -> DomainResult[ReentryContract]:
    """Open only as the atomic consequence of CORE exposure reaching zero."""

    if any(
        not _is_utc(value)
        for value in (
            opened_at,
            earliest_review_at,
            latest_review_at,
            expires_at,
        )
    ):
        return _error("CLOCK_TIME_INVALID", "reentry clocks must be UTC")
    if (
        not isinstance(authoritative_core_quantity, Decimal)
        or not authoritative_core_quantity.is_finite()
    ):
        return _error(
            "REENTRY_CORE_FILL_UNRECONCILED",
            "authoritative CORE quantity must be a finite Decimal",
            retryable=True,
        )
    if (
        not atomic_create_effect_present
        or authoritative_core_quantity != Decimal("0")
        or strategic_status
        not in {StrategicStatus.ACTIVE, StrategicStatus.CHALLENGED}
    ):
        return _error(
            "REENTRY_ATOMIC_OPEN_MISSING",
            "OPEN requires atomic creation when reconciled CORE reaches zero "
            "and the strategic thesis survives",
            retryable=not atomic_create_effect_present,
        )
    if maximum_deferrals is None:
        return _error(
            "REENTRY_DEFERRAL_LIMIT_MISSING",
            "the contract must freeze a maximum deferral count",
            retryable=True,
        )
    try:
        value = ReentryContract(
            contract_id=contract_id,
            strategic_episode_id=strategic_episode_id,
            revision=1,
            status=ReentryStatus.OPEN,
            opened_at=opened_at,
            earliest_review_at=earliest_review_at,
            latest_review_at=latest_review_at,
            expires_at=expires_at,
            maximum_deferrals=maximum_deferrals,
            deferral_count=0,
            minimum_core_quantity=minimum_core_quantity,
        )
    except (TypeError, ValueError) as exc:
        return _error(
            str(exc),
            "invalid reentry contract clocks or quantities",
        )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=value,
        evaluated_event_id="REENTRY_OPENED",
    )


def review_obligation(
    contract: ReentryContract,
    *,
    now: datetime,
    review_recorded: bool,
) -> DomainResult[ReentryStatus]:
    """Detect illegal silence at the mandatory latest-review boundary."""

    if not _is_utc(now):
        return DomainResult(
            status=ReducerStatus.UNKNOWN,
            error=DomainError(
                "CLOCK_TIME_INVALID",
                "REENTRY",
                "AFTER_INPUT_REPAIR",
                "review clock must be UTC",
            ),
        )
    if contract.status in TERMINAL_REENTRY_STATUSES or now < contract.latest_review_at:
        return DomainResult(status=ReducerStatus.NO_CHANGE)
    if not review_recorded:
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                "REENTRY_REVIEW_OVERDUE",
                "REENTRY",
                "NEVER",
                "latest_review_at requires an evaluation, bounded deferral, or terminal result",
            ),
        )
    return DomainResult(status=ReducerStatus.APPLIED, value=contract.status)


def reduce_reentry(
    prior: ReentryContract,
    evaluation: ReentryEvaluation,
) -> DomainResult[ReentryContract]:
    if evaluation.expected_revision != prior.revision:
        return _error(
            "REENTRY_PRIOR_STATE_MISMATCH",
            "evaluation does not target the current contract revision",
            retryable=True,
        )
    if prior.status in TERMINAL_REENTRY_STATUSES:
        return _error(
            "REENTRY_PRIOR_STATE_MISMATCH",
            "terminal reentry contracts have no outgoing transitions",
        )

    # Strategic termination has precedence over every tactical request.
    if evaluation.strategic_status is StrategicStatus.INVALIDATED:
        return _apply(prior, evaluation, ReentryStatus.CANCELLED_INVALIDATED)
    if evaluation.strategic_status is StrategicStatus.CLOSED:
        return _apply(prior, evaluation, ReentryStatus.CANCELLED_CLOSED)

    cutoff = evaluation.decision_cutoff
    requested = evaluation.requested_status
    current = prior.status
    if cutoff >= prior.expires_at:
        if requested is not ReentryStatus.EXPIRED:
            return _error(
                "REENTRY_REVIEW_OVERDUE",
                "expired contract requires terminal EXPIRED disposition",
            )
        return _apply(prior, evaluation, ReentryStatus.EXPIRED)
    if cutoff > prior.latest_review_at and requested not in {
        ReentryStatus.EXECUTED,
        ReentryStatus.EXPIRED,
        ReentryStatus.CANCELLED_INVALIDATED,
        ReentryStatus.CANCELLED_CLOSED,
    }:
        return _error(
            "REENTRY_REVIEW_OVERDUE",
            "latest review passed without a terminal result",
        )

    if current is ReentryStatus.OPEN and requested is ReentryStatus.DUE:
        if cutoff < prior.earliest_review_at:
            return _error(
                "REENTRY_CURRENT_ELIGIBILITY_FAILED",
                "earliest review clock has not been reached",
            )
        return _apply(prior, evaluation, requested)

    if current is ReentryStatus.DUE and requested is ReentryStatus.ELIGIBLE:
        if evaluation.eligibility is not EligibilityVerdict.PASS:
            return _error(
                "REENTRY_CURRENT_ELIGIBILITY_FAILED",
                "the frozen pullback, continuation, or time-review route did not pass",
            )
        return _apply(prior, evaluation, requested)

    if current is ReentryStatus.DUE and requested is ReentryStatus.OPEN:
        if evaluation.eligibility is not EligibilityVerdict.UNKNOWN:
            return _error(
                "REENTRY_CURRENT_ELIGIBILITY_FAILED",
                "only UNKNOWN eligibility may use a deferral",
            )
        if prior.maximum_deferrals is None:
            return _error(
                "REENTRY_DEFERRAL_LIMIT_MISSING",
                "maximum deferrals were not frozen",
                retryable=True,
            )
        if prior.deferral_count >= prior.maximum_deferrals:
            return _error(
                "REENTRY_DEFERRAL_LIMIT_EXCEEDED",
                "the frozen deferral limit has been consumed",
            )
        if (
            not evaluation.deferral_frozen
            or evaluation.next_review_at is None
            or evaluation.next_review_at <= cutoff
            or evaluation.next_review_at > prior.latest_review_at
        ):
            return _error(
                "REENTRY_DEFERRAL_LIMIT_EXCEEDED",
                "deferral needs a frozen future review no later than latest_review_at",
            )
        return _apply(
            prior,
            evaluation,
            requested,
            deferral_count=prior.deferral_count + 1,
            earliest_review_at=evaluation.next_review_at,
        )

    if current is ReentryStatus.ELIGIBLE and requested is ReentryStatus.DUE:
        if evaluation.eligibility is EligibilityVerdict.PASS:
            return _error(
                "REENTRY_CURRENT_ELIGIBILITY_FAILED",
                "passing current predicates cannot revoke eligibility",
            )
        return _apply(prior, evaluation, requested)

    if current is ReentryStatus.ELIGIBLE and requested is ReentryStatus.EXECUTED:
        if evaluation.eligibility is not EligibilityVerdict.PASS:
            return _error(
                "REENTRY_CURRENT_ELIGIBILITY_FAILED",
                "execution requires current-cutoff eligibility",
            )
        if not evaluation.new_thi_present:
            return _error(
                "REENTRY_NEW_THI_MISSING",
                "execution requires a new current THI",
                retryable=True,
            )
        if not evaluation.risk_permission_pass or not evaluation.governance_pass:
            return _error(
                "REENTRY_RISK_PERMISSION_MISSING",
                "risk and governance must both authorize the current reentry",
                retryable=True,
            )
        if (
            not evaluation.core_fill_reconciled
            or evaluation.reconciled_core_quantity < prior.minimum_core_quantity
        ):
            return _error(
                "REENTRY_CORE_FILL_UNRECONCILED",
                "reconciled CORE fill is below the frozen minimum",
                retryable=True,
            )
        return _apply(prior, evaluation, requested)

    if requested is ReentryStatus.EXPIRED:
        if (
            evaluation.eligibility is EligibilityVerdict.UNKNOWN
            and (
                prior.maximum_deferrals is None
                or prior.deferral_count >= prior.maximum_deferrals
                or cutoff >= prior.latest_review_at
            )
        ):
            return _apply(prior, evaluation, requested)
        return _error(
            "REENTRY_CURRENT_ELIGIBILITY_FAILED",
            "EXPIRED requires expiry or an un-deferrable UNKNOWN",
        )

    return _error(
        "REENTRY_PRIOR_STATE_MISMATCH",
        f"transition {current}->{requested} is not registered",
    )


def _apply(
    prior: ReentryContract,
    evaluation: ReentryEvaluation,
    requested: ReentryStatus,
    **changes: object,
) -> DomainResult[ReentryContract]:
    value = replace(
        prior,
        revision=prior.revision + 1,
        status=requested,
        last_reviewed_at=evaluation.decision_cutoff,
        **changes,
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=value,
        evaluated_event_id=evaluation.event_id,
    )
