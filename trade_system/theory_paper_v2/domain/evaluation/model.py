"""Deterministic evaluation value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


def require_decimal(value: Decimal, code: str = "DECIMAL_REQUIRED") -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(code)


def require_aware(value: datetime | None, code: str = "CLOCK_TIME_INVALID") -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(code)


@dataclass(frozen=True, slots=True)
class DecimalInterval:
    lower: Decimal
    upper: Decimal
    unit_ref: str

    def __post_init__(self) -> None:
        require_decimal(self.lower)
        require_decimal(self.upper)
        if self.lower > self.upper:
            raise ValueError("DECIMAL_INTERVAL_REVERSED")
        if not self.unit_ref:
            raise ValueError("DECIMAL_INTERVAL_UNIT_MISSING")

    def subtract(self, other: "DecimalInterval") -> "DecimalInterval":
        if self.unit_ref != other.unit_ref:
            raise ValueError("DECIMAL_INTERVAL_UNIT_MISMATCH")
        return DecimalInterval(
            self.lower - other.upper,
            self.upper - other.lower,
            self.unit_ref,
        )

    def add(self, other: "DecimalInterval") -> "DecimalInterval":
        if self.unit_ref != other.unit_ref:
            raise ValueError("DECIMAL_INTERVAL_UNIT_MISMATCH")
        return DecimalInterval(
            self.lower + other.lower,
            self.upper + other.upper,
            self.unit_ref,
        )


class ProbabilityStatus(StrEnum):
    CALIBRATED_OOS = "CALIBRATED_OOS"
    ORDINAL_ONLY = "ORDINAL_ONLY"
    UNKNOWN = "UNKNOWN"


class ProbabilityUse(StrEnum):
    ORDINAL_PATH_RANKING = "ORDINAL_PATH_RANKING"
    CONDITIONAL_PAYOFF_COMPARISON = "CONDITIONAL_PAYOFF_COMPARISON"
    NUMERIC_DISPLAY = "NUMERIC_DISPLAY"
    EXPECTED_VALUE = "EXPECTED_VALUE"
    KELLY = "KELLY"
    POSITION_SIZING = "POSITION_SIZING"


class PathKind(StrEnum):
    FAILURE = "FAILURE"
    NORMAL_REBOUND = "NORMAL_REBOUND"
    TREND_CONTINUATION = "TREND_CONTINUATION"
    REBOUND_EXHAUSTION = "REBOUND_EXHAUSTION"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


REQUIRED_PATHS = (
    PathKind.FAILURE,
    PathKind.NORMAL_REBOUND,
    PathKind.TREND_CONTINUATION,
    PathKind.REBOUND_EXHAUSTION,
    PathKind.OTHER,
    PathKind.UNKNOWN,
)


class DataStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIALLY_IDENTIFIED = "PARTIALLY_IDENTIFIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PathPayoffCell:
    path: PathKind
    action_plan_ref: str
    account_pnl_interval: DecimalInterval
    total_account_risk: DecimalInterval
    marginal_account_risk: DecimalInterval
    max_drawdown: DecimalInterval
    stress_loss: DecimalInterval
    tail_loss: DecimalInterval
    intermediate_state_refs: tuple[str, ...]
    continuation_action_refs: tuple[str, ...] = ()
    triggered_stage_refs: tuple[str, ...] = ()
    fill_outcome_ref: str = "fill:unknown"
    slippage_ref: str = "slippage:unknown"
    fee_ref: str = "fee:unknown"
    funding_status_ref: str = "funding:unknown"
    offline_risk_ref: str = "risk:offline"
    terminal_outcome_ref: str = "outcome:unknown"
    time_to_outcome_ref: str = "time:unknown"
    data_status: DataStatus = DataStatus.UNKNOWN
    assumption_refs: tuple[str, ...] = ()
    cell_digest: str = ""

    def __post_init__(self) -> None:
        if not self.action_plan_ref or not self.intermediate_state_refs:
            raise ValueError("PATH_PAYOFF_CELL_INCOMPLETE")
        units = {
            self.account_pnl_interval.unit_ref,
            self.total_account_risk.unit_ref,
            self.marginal_account_risk.unit_ref,
            self.max_drawdown.unit_ref,
            self.stress_loss.unit_ref,
            self.tail_loss.unit_ref,
        }
        if len(units) != 1:
            raise ValueError("PATH_PAYOFF_CELL_UNIT_MISMATCH")


@dataclass(frozen=True, slots=True)
class PathPayoffMatrix:
    matrix_id: str
    strategic_episode_ref: str
    revision: int
    decision_cutoff: datetime
    decision_horizon_ref: str
    planning_context_id: str
    candidate_action_set_digest: str
    actions: tuple[str, ...]
    paths: tuple[PathKind, ...]
    cells: tuple[PathPayoffCell, ...]
    probability_status: ProbabilityStatus
    ordinal_path_ranks: tuple[tuple[PathKind, int], ...]
    probability_use_authorization_ref: str | None
    forecast_coherence_receipt_ref: str | None
    expected_value_ref: str | None
    kelly_size_ref: str | None
    matrix_digest: str

    def by_key(self) -> dict[tuple[PathKind, str], PathPayoffCell]:
        return {(cell.path, cell.action_plan_ref): cell for cell in self.cells}

