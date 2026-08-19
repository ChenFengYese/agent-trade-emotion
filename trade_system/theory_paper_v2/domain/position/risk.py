"""Episode-level risk accounting in account-risk units."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from ..common import DomainError, DomainResult, ReducerStatus


ZERO = Decimal("0")


class RiskTransitionKind(StrEnum):
    ALLOCATE = "ALLOCATE"
    RESERVE_STAGE = "RESERVE_STAGE"
    RELEASE_UNUSED_STAGE = "RELEASE_UNUSED_STAGE"
    OPEN_RISK = "OPEN_RISK"
    PENDING_RISK = "PENDING_RISK"
    REALIZE_LOSS = "REALIZE_LOSS"
    REALIZE_COST = "REALIZE_COST"
    CLOSE_RISK = "CLOSE_RISK"
    RECONCILE = "RECONCILE"


@dataclass(frozen=True, slots=True)
class EpisodeRiskBudget:
    budget_id: str
    episode_id: str
    revision: int
    account_cap: Decimal
    episode_cap: Decimal
    core_cap: Decimal
    tactical_cap: Decimal
    hedge_cap: Decimal
    realized_loss: Decimal
    realized_cost: Decimal
    open_risk: Decimal
    pending_risk: Decimal
    reserved_stage_risk: Decimal
    tail_reserve: Decimal
    stage_reservations: tuple[tuple[str, Decimal], ...]
    previous_budget_id: str | None = None

    @property
    def committed_risk(self) -> Decimal:
        return (
            self.realized_loss
            + self.realized_cost
            + self.open_risk
            + self.pending_risk
            + self.reserved_stage_risk
            + self.tail_reserve
        )

    @property
    def remaining_capacity(self) -> Decimal:
        return self.episode_cap - self.committed_risk

    def __post_init__(self) -> None:
        components = (
            self.account_cap,
            self.episode_cap,
            self.core_cap,
            self.tactical_cap,
            self.hedge_cap,
            self.realized_loss,
            self.realized_cost,
            self.open_risk,
            self.pending_risk,
            self.reserved_stage_risk,
            self.tail_reserve,
        )
        if any(not isinstance(value, Decimal) for value in components):
            raise TypeError("RISK_COMPONENT_UNIT_MISMATCH")
        if any(value < ZERO for value in components):
            raise ValueError("RISK_COMPONENT_NEGATIVE")
        if self.episode_cap > self.account_cap:
            raise ValueError("RISK_ACCOUNT_CAP_BREACH")
        if self.core_cap + self.tactical_cap + self.hedge_cap > self.episode_cap:
            raise ValueError("RISK_EPISODE_CAP_BREACH")
        if self.hedge_cap != ZERO:
            raise ValueError("STAGE_HEDGE_FORBIDDEN_E0")
        reservations = dict(self.stage_reservations)
        if len(reservations) != len(self.stage_reservations):
            raise ValueError("RISK_STAGE_RESERVATION_DUPLICATE")
        if any(value < ZERO for value in reservations.values()):
            raise ValueError("RISK_STAGE_RESERVATION_BREACH")
        if sum(reservations.values(), ZERO) != self.reserved_stage_risk:
            raise ValueError("RISK_STAGE_RESERVATION_BREACH")
        if self.committed_risk > self.episode_cap:
            raise ValueError("RISK_EPISODE_CAP_BREACH")


def _risk_failure(code: str, message: str) -> DomainResult[EpisodeRiskBudget]:
    return DomainResult(
        status=ReducerStatus.REJECTED,
        error=DomainError(code, "RISK", "NEVER", message),
    )


def _positive(amount: Decimal) -> bool:
    return isinstance(amount, Decimal) and amount > ZERO


def apply_risk_transition(
    prior: EpisodeRiskBudget,
    *,
    kind: RiskTransitionKind,
    amount: Decimal,
    next_budget_id: str,
    stage_id: str | None = None,
    portfolio_truth_proven: bool = True,
    reconciled_open_risk: Decimal | None = None,
    reconciled_pending_risk: Decimal | None = None,
) -> DomainResult[EpisodeRiskBudget]:
    """Move risk between mutually exclusive components without recycling loss."""

    if kind is RiskTransitionKind.ALLOCATE:
        return _risk_failure(
            "RISK_CROSS_EPISODE_REALLOCATION_UNAUTHORIZED",
            "an existing episode budget cannot be reallocated",
        )
    if kind is RiskTransitionKind.RECONCILE:
        if (
            not portfolio_truth_proven
            or reconciled_open_risk is None
            or reconciled_pending_risk is None
        ):
            return DomainResult(
                status=ReducerStatus.UNKNOWN,
                error=DomainError(
                    "RISK_PORTFOLIO_TRUTH_UNKNOWN",
                    "RISK",
                    "AFTER_INPUT_REPAIR",
                    "portfolio truth is required for risk reconciliation",
                ),
            )
        if reconciled_open_risk < ZERO or reconciled_pending_risk < ZERO:
            return _risk_failure(
                "RISK_COMPONENT_UNIT_MISMATCH", "reconciled risk must be nonnegative"
            )
        candidate = replace(
            prior,
            budget_id=next_budget_id,
            revision=prior.revision + 1,
            previous_budget_id=prior.budget_id,
            open_risk=reconciled_open_risk,
            pending_risk=reconciled_pending_risk,
        )
    else:
        if not _positive(amount):
            return _risk_failure(
                "RISK_COMPONENT_UNIT_MISMATCH", "transition amount must be positive Decimal"
            )
        reservations = dict(prior.stage_reservations)
        updates: dict[str, Decimal] = {}
        if kind is RiskTransitionKind.RESERVE_STAGE:
            if not stage_id:
                return _risk_failure(
                    "RISK_STAGE_RESERVATION_BREACH", "stage id is required"
                )
            reservations[stage_id] = reservations.get(stage_id, ZERO) + amount
            updates["reserved_stage_risk"] = prior.reserved_stage_risk + amount
        elif kind is RiskTransitionKind.RELEASE_UNUSED_STAGE:
            if not stage_id or reservations.get(stage_id, ZERO) < amount:
                return _risk_failure(
                    "RISK_STAGE_RESERVATION_BREACH",
                    "only an existing unused reservation may be released",
                )
            reservations[stage_id] -= amount
            if reservations[stage_id] == ZERO:
                del reservations[stage_id]
            updates["reserved_stage_risk"] = prior.reserved_stage_risk - amount
        elif kind is RiskTransitionKind.PENDING_RISK:
            if not stage_id or reservations.get(stage_id, ZERO) < amount:
                return _risk_failure(
                    "RISK_STAGE_RESERVATION_BREACH",
                    "pending risk must consume an exact stage reservation",
                )
            reservations[stage_id] -= amount
            if reservations[stage_id] == ZERO:
                del reservations[stage_id]
            updates.update(
                reserved_stage_risk=prior.reserved_stage_risk - amount,
                pending_risk=prior.pending_risk + amount,
            )
        elif kind is RiskTransitionKind.OPEN_RISK:
            if prior.pending_risk < amount:
                return _risk_failure(
                    "RISK_STAGE_RESERVATION_BREACH",
                    "open risk cannot exceed pending risk",
                )
            updates.update(
                pending_risk=prior.pending_risk - amount,
                open_risk=prior.open_risk + amount,
            )
        elif kind is RiskTransitionKind.CLOSE_RISK:
            if prior.open_risk < amount:
                return _risk_failure(
                    "RISK_COMPONENT_UNIT_MISMATCH",
                    "closed risk cannot exceed open risk",
                )
            updates["open_risk"] = prior.open_risk - amount
        elif kind is RiskTransitionKind.REALIZE_LOSS:
            if prior.open_risk < amount:
                return _risk_failure(
                    "RISK_REALIZED_LOSS_RESET",
                    "realized loss must transfer from reconciled open risk",
                )
            updates.update(
                open_risk=prior.open_risk - amount,
                realized_loss=prior.realized_loss + amount,
            )
        elif kind is RiskTransitionKind.REALIZE_COST:
            updates["realized_cost"] = prior.realized_cost + amount
        else:
            return _risk_failure("RISK_COMPONENT_UNIT_MISMATCH", "unsupported transition")
        try:
            candidate = replace(
                prior,
                budget_id=next_budget_id,
                revision=prior.revision + 1,
                previous_budget_id=prior.budget_id,
                stage_reservations=tuple(sorted(reservations.items())),
                **updates,
            )
        except (TypeError, ValueError) as exc:
            code = str(exc)
            if code not in {
                "RISK_ACCOUNT_CAP_BREACH",
                "RISK_EPISODE_CAP_BREACH",
                "RISK_STAGE_RESERVATION_BREACH",
            }:
                code = "RISK_EPISODE_CAP_BREACH"
            return _risk_failure(code, str(exc))
    try:
        # replace() already runs __post_init__; this explicit access documents the gate.
        _ = candidate.remaining_capacity
    except (TypeError, ValueError) as exc:
        return _risk_failure("RISK_EPISODE_CAP_BREACH", str(exc))
    if candidate.realized_loss < prior.realized_loss:
        return _risk_failure("RISK_REALIZED_LOSS_RESET", "realized loss is monotonic")
    if candidate.realized_cost < prior.realized_cost:
        return _risk_failure("RISK_REALIZED_LOSS_RESET", "realized cost is monotonic")
    return DomainResult(status=ReducerStatus.APPLIED, value=candidate)

