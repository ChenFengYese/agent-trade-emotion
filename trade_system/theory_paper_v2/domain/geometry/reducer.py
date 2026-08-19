"""Pure reducers for analytical geometry and protective barriers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal

from ..common import DomainError, DomainResult, ReducerStatus
from .model import (
    AnalysisGeometryStatus,
    ExecutionBarrierStatus,
    GeometryAggregate,
    PositionSide,
    ProbabilityStatus,
)


ANALYSIS_TERMINAL = frozenset(
    {
        AnalysisGeometryStatus.STALE_FOR_NEW_DECISIONS,
        AnalysisGeometryStatus.SUPERSEDED,
        AnalysisGeometryStatus.EXPIRED,
    }
)
PROTECTION_TERMINAL = frozenset(
    {
        ExecutionBarrierStatus.SUPERSEDED,
        ExecutionBarrierStatus.TRIGGERED,
        ExecutionBarrierStatus.CANCELLED,
        ExecutionBarrierStatus.REJECTED,
        ExecutionBarrierStatus.ACK_TIMEOUT,
        ExecutionBarrierStatus.HALTED_RECONCILE,
    }
)


@dataclass(frozen=True, slots=True)
class AnalysisGeometryTransition:
    event_id: str
    expected_aggregate_revision: int
    expected_analysis_revision: int
    requested_status: AnalysisGeometryStatus
    occurred_at: datetime
    schema_and_pit_pass: bool = False
    governance_activation_pass: bool = False
    stale_cause_registered: bool = False
    replacement_active: bool = False


@dataclass(frozen=True, slots=True)
class ProtectionStatusTransition:
    event_id: str
    expected_aggregate_revision: int
    expected_barrier_revision: int
    requested_status: ExecutionBarrierStatus
    occurred_at: datetime
    simulated_ack_at: datetime | None = None
    crossing_at: datetime | None = None
    corresponding_result_proven: bool = False
    lot_closed_or_cancellation_proven: bool = False
    atomic_replacement_proven: bool = False


@dataclass(frozen=True, slots=True)
class ProtectionRevision:
    event_id: str
    expected_aggregate_revision: int
    expected_barrier_revision: int
    replacement_barrier_id: str
    requested_at: datetime
    acknowledged_at: datetime | None
    old_barrier_crossed_at: datetime | None
    new_stop_price: Decimal
    new_target_price: Decimal | None
    new_horizon_at: datetime
    probability_status: ProbabilityStatus
    t023_core_gates_pass: bool
    t023_governance_ack_pass: bool


def _aware_utc(value: datetime | None) -> bool:
    return (
        value is not None
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> DomainResult[GeometryAggregate]:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if retryable else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="GEOMETRY",
            retryability="AFTER_INPUT_REPAIR" if retryable else "NEVER",
            message=message,
        ),
    )


def _head_matches(
    aggregate: GeometryAggregate,
    expected_aggregate_revision: int,
    expected_child_revision: int,
    *,
    analysis: bool,
) -> bool:
    child_revision = (
        aggregate.analysis.revision if analysis else aggregate.protection.revision
    )
    return (
        aggregate.revision == expected_aggregate_revision
        and child_revision == expected_child_revision
    )


def reduce_analysis_geometry(
    prior: GeometryAggregate,
    transition: AnalysisGeometryTransition,
) -> DomainResult[GeometryAggregate]:
    """Advance analysis only; active protection is never changed here."""

    if not _head_matches(
        prior,
        transition.expected_aggregate_revision,
        transition.expected_analysis_revision,
        analysis=True,
    ):
        return _error(
            "GEOMETRY_PRIOR_VERSION_MISMATCH",
            "analysis command does not target the accepted aggregate head",
            retryable=True,
        )
    if not _aware_utc(transition.occurred_at):
        return _error("CLOCK_TIME_INVALID", "transition time must be UTC")
    current = prior.analysis.status
    requested = transition.requested_status
    if current in ANALYSIS_TERMINAL:
        return _error(
            "GEOMETRY_ANALYSIS_TRANSITION_ILLEGAL",
            "terminal analysis geometry cannot be reactivated",
        )
    allowed = False
    if (
        current is AnalysisGeometryStatus.DRAFT
        and requested is AnalysisGeometryStatus.PROPOSED
    ):
        allowed = transition.schema_and_pit_pass
    elif (
        current is AnalysisGeometryStatus.PROPOSED
        and requested is AnalysisGeometryStatus.ACTIVE_ANALYSIS
    ):
        allowed = transition.governance_activation_pass
    elif current is AnalysisGeometryStatus.ACTIVE_ANALYSIS:
        if requested is AnalysisGeometryStatus.STALE_FOR_NEW_DECISIONS:
            allowed = transition.stale_cause_registered
        elif requested is AnalysisGeometryStatus.SUPERSEDED:
            allowed = transition.replacement_active
        elif requested is AnalysisGeometryStatus.EXPIRED:
            allowed = transition.occurred_at >= prior.analysis.valid_until
    if not allowed:
        return _error(
            "GEOMETRY_ANALYSIS_TRANSITION_ILLEGAL",
            f"transition {current}->{requested} lacks its registered cause",
        )
    next_analysis = replace(
        prior.analysis,
        revision=prior.analysis.revision + 1,
        status=requested,
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=replace(
            prior,
            revision=prior.revision + 1,
            analysis=next_analysis,
        ),
        evaluated_event_id=transition.event_id,
    )


def transition_protection_status(
    prior: GeometryAggregate,
    transition: ProtectionStatusTransition,
) -> DomainResult[GeometryAggregate]:
    if not _head_matches(
        prior,
        transition.expected_aggregate_revision,
        transition.expected_barrier_revision,
        analysis=False,
    ):
        return _error(
            "GEOMETRY_PRIOR_VERSION_MISMATCH",
            "protection command does not target the accepted aggregate head",
            retryable=True,
        )
    times = (
        transition.occurred_at,
        transition.simulated_ack_at,
        transition.crossing_at,
    )
    if any(value is not None and not _aware_utc(value) for value in times):
        return _error("CLOCK_TIME_INVALID", "all barrier times must be UTC")
    current = prior.protection.status
    requested = transition.requested_status
    if current in PROTECTION_TERMINAL:
        return _error(
            "GEOMETRY_PROTECTION_TRANSITION_ILLEGAL",
            "terminal protection cannot transition",
        )
    next_fields: dict[str, object] = {}
    allowed = False
    if (
        current is ExecutionBarrierStatus.NONE
        and requested is ExecutionBarrierStatus.PENDING_VENUE_ACK
    ):
        allowed = True
    elif current is ExecutionBarrierStatus.PENDING_VENUE_ACK:
        if requested is ExecutionBarrierStatus.ACTIVE_PROTECTION:
            if transition.simulated_ack_at is None:
                return _error(
                    "GEOMETRY_ACK_MISSING",
                    "protection activation requires a simulated ACK",
                    retryable=True,
                )
            if (
                transition.crossing_at is not None
                and transition.crossing_at <= transition.simulated_ack_at
            ):
                return _error(
                    "GEOMETRY_OLD_BARRIER_ALREADY_CROSSED",
                    "crossing preceded replacement ACK",
                )
            allowed = transition.simulated_ack_at <= transition.occurred_at
            next_fields = {
                "acknowledged_at": transition.simulated_ack_at,
                "active_from": transition.simulated_ack_at,
            }
        elif requested in {
            ExecutionBarrierStatus.REJECTED,
            ExecutionBarrierStatus.ACK_TIMEOUT,
            ExecutionBarrierStatus.HALTED_RECONCILE,
        }:
            allowed = transition.corresponding_result_proven
    elif current is ExecutionBarrierStatus.ACTIVE_PROTECTION:
        if requested is ExecutionBarrierStatus.TRIGGERED:
            allowed = transition.crossing_at is not None
        elif requested is ExecutionBarrierStatus.CANCELLED:
            allowed = transition.lot_closed_or_cancellation_proven
        elif requested is ExecutionBarrierStatus.SUPERSEDED:
            if (
                transition.crossing_at is not None
                and (
                    transition.simulated_ack_at is None
                    or transition.crossing_at <= transition.simulated_ack_at
                )
            ):
                return _error(
                    "GEOMETRY_OLD_BARRIER_ALREADY_CROSSED",
                    "old protection crossed before replacement ACK",
                )
            allowed = (
                transition.atomic_replacement_proven
                and transition.simulated_ack_at is not None
            )
    if not allowed:
        return _error(
            "GEOMETRY_PROTECTION_TRANSITION_ILLEGAL",
            f"transition {current}->{requested} lacks its registered cause",
        )
    next_protection = replace(
        prior.protection,
        revision=prior.protection.revision + 1,
        status=requested,
        **next_fields,
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=replace(
            prior,
            revision=prior.revision + 1,
            protection=next_protection,
        ),
        evaluated_event_id=transition.event_id,
    )


def _is_stop_looser(
    side: PositionSide,
    old_stop: Decimal,
    new_stop: Decimal,
) -> bool:
    if side is PositionSide.LONG:
        return new_stop < old_stop
    return new_stop > old_stop


def _is_target_extension(
    side: PositionSide,
    old_target: Decimal | None,
    new_target: Decimal | None,
) -> bool:
    if old_target is None:
        return new_target is not None
    if new_target is None:
        return False
    if side is PositionSide.LONG:
        return new_target > old_target
    return new_target < old_target


def revise_protection(
    prior: GeometryAggregate,
    command: ProtectionRevision,
) -> DomainResult[GeometryAggregate]:
    """Atomically replace protection without changing analytical geometry."""

    if not _head_matches(
        prior,
        command.expected_aggregate_revision,
        command.expected_barrier_revision,
        analysis=False,
    ):
        return _error(
            "GEOMETRY_PRIOR_VERSION_MISMATCH",
            "replacement does not target the accepted barrier",
            retryable=True,
        )
    if prior.protection.status is not ExecutionBarrierStatus.ACTIVE_PROTECTION:
        return _error(
            "GEOMETRY_PROTECTION_TRANSITION_ILLEGAL",
            "only active protection can be revised",
        )
    for value in (
        command.requested_at,
        command.acknowledged_at,
        command.old_barrier_crossed_at,
        command.new_horizon_at,
    ):
        if value is not None and not _aware_utc(value):
            return _error("CLOCK_TIME_INVALID", "all replacement times must be UTC")
    for value in (command.new_stop_price, command.new_target_price):
        if value is not None and (
            not isinstance(value, Decimal) or not value.is_finite()
        ):
            return _error(
                "GEOMETRY_PROTECTION_TRANSITION_ILLEGAL",
                "prices must be finite Decimal values",
            )
    if command.acknowledged_at is None:
        return _error(
            "GEOMETRY_ACK_MISSING",
            "replacement cannot activate without an ACK",
            retryable=True,
        )
    if command.acknowledged_at < command.requested_at:
        return _error(
            "GEOMETRY_ACK_MISSING",
            "ACK cannot precede the replacement request",
        )
    if (
        command.old_barrier_crossed_at is not None
        and command.old_barrier_crossed_at <= command.acknowledged_at
    ):
        return _error(
            "GEOMETRY_OLD_BARRIER_ALREADY_CROSSED",
            "the old barrier executes because it crossed before replacement ACK",
        )
    if _is_stop_looser(
        prior.protection.side,
        prior.protection.stop_price,
        command.new_stop_price,
    ):
        return _error(
            "GEOMETRY_STOP_LOOSEN_FORBIDDEN",
            "a PositionLock stop may only tighten",
        )
    if command.new_horizon_at > prior.protection.horizon_at:
        return _error(
            "GEOMETRY_HORIZON_EXTENSION_FORBIDDEN",
            "protection horizon may shorten but never lengthen",
        )
    if _is_target_extension(
        prior.protection.side,
        prior.protection.target_price,
        command.new_target_price,
    ):
        if command.probability_status is not ProbabilityStatus.CALIBRATED_OOS:
            return _error(
                "GEOMETRY_T023_GATE_UNCALIBRATED",
                "T-023 target extension is denied without calibrated OOS value gates",
            )
        if not (
            command.t023_core_gates_pass and command.t023_governance_ack_pass
        ):
            return _error(
                "GEOMETRY_T023_GATE_UNCALIBRATED",
                "T-023 target extension gates or governance ACK did not pass",
            )
    replacement = replace(
        prior.protection,
        barrier_id=command.replacement_barrier_id,
        revision=prior.protection.revision + 1,
        status=ExecutionBarrierStatus.ACTIVE_PROTECTION,
        stop_price=command.new_stop_price,
        target_price=command.new_target_price,
        horizon_at=command.new_horizon_at,
        active_from=command.acknowledged_at,
        acknowledged_at=command.acknowledged_at,
        previous_barrier_id=prior.protection.barrier_id,
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=replace(
            prior,
            revision=prior.revision + 1,
            protection=replacement,
        ),
        evaluated_event_id=command.event_id,
    )
