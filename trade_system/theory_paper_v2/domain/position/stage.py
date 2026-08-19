"""Pre-registered staged-position lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ..common import DomainError, DomainResult, ReducerStatus
from ..strategic import StrategicStatus


class StageKind(StrEnum):
    INITIAL = "INITIAL"
    CONFIRMATION = "CONFIRMATION"
    TREND = "TREND"


class LotRole(StrEnum):
    CORE = "CORE"
    TACTICAL = "TACTICAL"


class StageStatus(StrEnum):
    REGISTERED = "REGISTERED"
    ELIGIBLE = "ELIGIBLE"
    ARMED = "ARMED"
    COUNTERFACTUAL_FILLED = "COUNTERFACTUAL_FILLED"
    PROTECTED = "PROTECTED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class GateVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


TERMINAL_STAGES = frozenset(
    {
        StageStatus.CLOSED,
        StageStatus.EXPIRED,
        StageStatus.CANCELLED,
        StageStatus.REJECTED,
    }
)


@dataclass(frozen=True, slots=True)
class StageSpec:
    stage_id: str
    plan_id: str
    stage_index: int
    stage_kind: StageKind
    lot_role: LotRole
    predecessor_stage_id: str | None
    expiry: datetime
    maximum_retries: int
    frozen_before_first_fill: bool

    def __post_init__(self) -> None:
        if self.stage_index < 0 or self.maximum_retries < 0:
            raise ValueError("STAGE_UNREGISTERED")
        if self.expiry.tzinfo is None:
            raise ValueError("CLOCK_TIME_INVALID")
        if self.stage_index == 0 and self.predecessor_stage_id is not None:
            raise ValueError("STAGE_PREDECESSOR_FAILED")
        if self.stage_index > 0 and self.predecessor_stage_id is None:
            raise ValueError("STAGE_PREDECESSOR_FAILED")


@dataclass(frozen=True, slots=True)
class StageState:
    spec: StageSpec
    status: StageStatus
    revision: int
    retry_count: int = 0


@dataclass(frozen=True, slots=True)
class StageEvaluation:
    decision_cutoff: datetime
    requested_status: StageStatus
    strategic_status: StrategicStatus
    registered_before_trigger: bool = True
    trigger: GateVerdict = GateVerdict.NOT_APPLICABLE
    predecessor: GateVerdict = GateVerdict.NOT_APPLICABLE
    evidence: GateVerdict = GateVerdict.NOT_APPLICABLE
    time_authority: GateVerdict = GateVerdict.NOT_APPLICABLE
    geometry: GateVerdict = GateVerdict.NOT_APPLICABLE
    forward_reward_risk: GateVerdict = GateVerdict.NOT_APPLICABLE
    reserved_risk: GateVerdict = GateVerdict.NOT_APPLICABLE
    portfolio_stress: GateVerdict = GateVerdict.NOT_APPLICABLE
    cost_liquidity_margin: GateVerdict = GateVerdict.NOT_APPLICABLE
    supervision: GateVerdict = GateVerdict.NOT_APPLICABLE
    protection_atomicity: GateVerdict = GateVerdict.NOT_APPLICABLE
    selected_exact_candidate: bool = False
    counterfactual_only: bool = True
    matching_fill_candidate: bool = False
    portfolio_fill_reconciled: bool = False
    protection_reconciled: bool = False
    residual_quantity_positive: bool = False
    residual_quantity_below_filled: bool = False
    cancellation_predicate_passed: bool = False


def _stage_error(
    code: str, message: str, *, unknown: bool = False
) -> DomainResult[StageState]:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if unknown else ReducerStatus.REJECTED,
        error=DomainError(
            code,
            "STAGE",
            "AFTER_INPUT_REPAIR" if unknown else "NEVER",
            message,
        ),
    )


def reduce_stage(
    prior: StageState,
    evaluation: StageEvaluation,
) -> DomainResult[StageState]:
    if evaluation.decision_cutoff.tzinfo is None:
        return _stage_error("STRATEGIC_TIME_AUTHORITY_MISSING", "cutoff missing")
    if prior.status in TERMINAL_STAGES:
        return _stage_error("STAGE_TERMINAL_REUSE", "terminal stage cannot transition")
    if evaluation.decision_cutoff >= prior.spec.expiry:
        if evaluation.requested_status is not StageStatus.EXPIRED:
            return _stage_error("STAGE_EXPIRY_REACHED", "stage expiry has been reached")
    if evaluation.cancellation_predicate_passed:
        if evaluation.requested_status is not StageStatus.CANCELLED:
            return _stage_error(
                "STAGE_UNREGISTERED", "registered cancellation must be honored"
            )
    current, requested = prior.status, evaluation.requested_status
    if current is StageStatus.REGISTERED and requested is StageStatus.ELIGIBLE:
        if evaluation.strategic_status is not StrategicStatus.ACTIVE:
            return _stage_error(
                "STAGE_SUPERVISION_FORBIDDEN",
                "new risk requires ACTIVE strategic status",
            )
        if not evaluation.registered_before_trigger:
            return _stage_error("STAGE_UNREGISTERED", "stage was not preregistered")
        gates = (
            evaluation.trigger,
            evaluation.predecessor,
            evaluation.evidence,
            evaluation.time_authority,
            evaluation.geometry,
            evaluation.forward_reward_risk,
            evaluation.reserved_risk,
            evaluation.portfolio_stress,
            evaluation.cost_liquidity_margin,
            evaluation.supervision,
            evaluation.protection_atomicity,
        )
        if GateVerdict.UNKNOWN in gates:
            return DomainResult(
                status=ReducerStatus.NO_CHANGE,
                evaluated_event_id="STAGE_ELIGIBILITY_EVALUATED_UNKNOWN",
            )
        if any(gate is not GateVerdict.PASS for gate in gates):
            code = (
                "STAGE_FORWARD_RR_INELIGIBLE"
                if evaluation.forward_reward_risk is GateVerdict.FAIL
                else (
                    "STAGE_RISK_CAP_FAILED"
                    if evaluation.reserved_risk is GateVerdict.FAIL
                    or evaluation.portfolio_stress is GateVerdict.FAIL
                    else (
                        "STAGE_SUPERVISION_FORBIDDEN"
                        if evaluation.supervision is GateVerdict.FAIL
                        else "STAGE_PREDECESSOR_FAILED"
                    )
                )
            )
            return _stage_error(code, "one or more activation gates failed")
    elif current is StageStatus.ELIGIBLE and requested is StageStatus.ARMED:
        if not (
            evaluation.selected_exact_candidate
            and evaluation.reserved_risk is GateVerdict.PASS
            and evaluation.protection_atomicity is GateVerdict.PASS
        ):
            return _stage_error(
                "STAGE_PROTECTION_ATOMICITY_UNKNOWN",
                "arming requires selected candidate, reservation, and protection",
            )
        if not evaluation.counterfactual_only:
            return _stage_error(
                "STAGE_REAL_ADD_AUTHORITY_NONE", "E0 has no real ADD authority"
            )
    elif current is StageStatus.ARMED and requested is StageStatus.COUNTERFACTUAL_FILLED:
        if not (
            evaluation.matching_fill_candidate
            and evaluation.portfolio_fill_reconciled
        ):
            return _stage_error(
                "STAGE_PROTECTION_ATOMICITY_UNKNOWN",
                "matching evidence and portfolio reconciliation are required",
            )
    elif (
        current is StageStatus.COUNTERFACTUAL_FILLED
        and requested is StageStatus.PROTECTED
    ):
        if not (
            evaluation.protection_reconciled
            and evaluation.portfolio_fill_reconciled
        ):
            return _stage_error(
                "STAGE_PROTECTION_ATOMICITY_UNKNOWN",
                "filled stage must be atomically protected and reconciled",
            )
    elif (
        current in {StageStatus.PROTECTED, StageStatus.PARTIALLY_CLOSED}
        and requested is StageStatus.PARTIALLY_CLOSED
    ):
        if not (
            evaluation.portfolio_fill_reconciled
            and evaluation.residual_quantity_positive
            and evaluation.residual_quantity_below_filled
        ):
            return _stage_error(
                "STAGE_PRIOR_RECEIPT_MISMATCH",
                "partial close requires reconciled positive residual",
            )
    elif (
        current in {StageStatus.PROTECTED, StageStatus.PARTIALLY_CLOSED}
        and requested is StageStatus.CLOSED
    ):
        if not (
            evaluation.portfolio_fill_reconciled
            and not evaluation.residual_quantity_positive
        ):
            return _stage_error(
                "STAGE_PRIOR_RECEIPT_MISMATCH",
                "close requires reconciled zero residual",
            )
    elif requested in {
        StageStatus.EXPIRED,
        StageStatus.CANCELLED,
        StageStatus.REJECTED,
    }:
        pass
    elif current is StageStatus.ELIGIBLE and requested is StageStatus.REGISTERED:
        if evaluation.trigger is GateVerdict.PASS:
            return _stage_error(
                "STAGE_TRIGGER_UNKNOWN", "passing trigger cannot revert to registered"
            )
    else:
        return _stage_error(
            "STAGE_PRIOR_RECEIPT_MISMATCH",
            f"transition {current}->{requested} is not registered",
        )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=replace(prior, status=requested, revision=prior.revision + 1),
    )

