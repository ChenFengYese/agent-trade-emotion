"""Action-specific labels and conservative expected-value policy.

The module deliberately separates market-path outcomes from fill outcomes and
from operational overrides. It does not train or claim a predictive model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Iterable, Optional

from .types import GateLevel, PositionStage, Side


class MarketOutcome(str, Enum):
    TP = "TP"
    SL = "SL"
    STRUCTURE_EXIT = "STRUCTURE_EXIT"
    TIMEOUT = "TIMEOUT"


class ExecutionOutcome(str, Enum):
    NO_FILL = "NO_FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"


@dataclass(frozen=True)
class ActionContract:
    side: Side
    stage: PositionStage
    entry_price: Decimal
    take_profit: Decimal
    stop_loss: Decimal
    horizon: timedelta
    structure_exit_fraction: Decimal

    def __post_init__(self) -> None:
        if self.entry_price <= 0 or self.take_profit <= 0 or self.stop_loss <= 0:
            raise ValueError("prices must be positive")
        if self.horizon <= timedelta(0):
            raise ValueError("horizon must be positive")
        if self.side == Side.BUY and not (self.stop_loss < self.entry_price < self.take_profit):
            raise ValueError("long barriers must satisfy stop < entry < target")
        if self.side == Side.SELL and not (self.take_profit < self.entry_price < self.stop_loss):
            raise ValueError("short barriers must satisfy target < entry < stop")


@dataclass(frozen=True)
class PathPoint:
    observed_at: datetime
    price: Decimal
    structure_invalidated: bool = False
    operational_override: Optional[str] = None


@dataclass(frozen=True)
class LabelResult:
    market_outcome: Optional[MarketOutcome]
    observed_at: datetime
    operational_override: Optional[str] = None

    @property
    def is_censored(self) -> bool:
        return self.operational_override is not None


def label_market_path(contract: ActionContract, filled_at: datetime, points: Iterable[PathPoint]) -> LabelResult:
    """First event wins; overrides censor rather than become market labels."""
    deadline = filled_at + contract.horizon
    last_seen = filled_at
    for point in points:
        if point.observed_at < filled_at:
            continue
        if point.operational_override:
            return LabelResult(None, point.observed_at, point.operational_override)
        if point.observed_at >= deadline:
            return LabelResult(MarketOutcome.TIMEOUT, deadline)
        last_seen = point.observed_at
        if contract.side == Side.BUY:
            if point.price >= contract.take_profit:
                return LabelResult(MarketOutcome.TP, point.observed_at)
            if point.price <= contract.stop_loss:
                return LabelResult(MarketOutcome.SL, point.observed_at)
        else:
            if point.price <= contract.take_profit:
                return LabelResult(MarketOutcome.TP, point.observed_at)
            if point.price >= contract.stop_loss:
                return LabelResult(MarketOutcome.SL, point.observed_at)
        if point.structure_invalidated:
            return LabelResult(MarketOutcome.STRUCTURE_EXIT, point.observed_at)
    return LabelResult(MarketOutcome.TIMEOUT, max(deadline, last_seen))


@dataclass(frozen=True)
class OutcomeForecast:
    tp: Decimal
    sl: Decimal
    structure_exit: Decimal
    timeout: Decimal

    def __post_init__(self) -> None:
        probabilities = (self.tp, self.sl, self.structure_exit, self.timeout)
        if any(item < 0 or item > 1 for item in probabilities):
            raise ValueError("probabilities must be within [0, 1]")
        if abs(sum(probabilities, Decimal("0")) - Decimal("1")) > Decimal("0.000001"):
            raise ValueError("competing-risk probabilities must sum to 1")


@dataclass(frozen=True)
class ExecutionForecast:
    fill_probability: Decimal
    expected_fill_fraction: Decimal
    no_fill_cost: Decimal
    submit_cost: Decimal

    def __post_init__(self) -> None:
        if not (Decimal("0") <= self.fill_probability <= Decimal("1")):
            raise ValueError("fill_probability must be in [0, 1]")
        if not (Decimal("0") <= self.expected_fill_fraction <= Decimal("1")):
            raise ValueError("expected_fill_fraction must be in [0, 1]")


@dataclass(frozen=True)
class DecisionResult:
    trade: bool
    reason: str
    ev_fill: Decimal
    ev_submit: Decimal


class ConservativePolicy:
    def __init__(self, minimum_submit_ev: Decimal) -> None:
        self.minimum_submit_ev = minimum_submit_ev

    def evaluate(
        self,
        *,
        outcome: OutcomeForecast,
        execution: ExecutionForecast,
        gain_if_tp: Decimal,
        loss_if_sl: Decimal,
        expected_structure_return: Decimal,
        expected_timeout_return: Decimal,
        trade_cost: Decimal,
        gate_level: GateLevel,
        data_healthy: bool,
        model_applicable: bool,
    ) -> DecisionResult:
        ev_fill = (
            outcome.tp * gain_if_tp
            - outcome.sl * loss_if_sl
            + outcome.structure_exit * expected_structure_return
            + outcome.timeout * expected_timeout_return
            - trade_cost
        )
        ev_submit = (
            execution.fill_probability * execution.expected_fill_fraction * ev_fill
            - (Decimal("1") - execution.fill_probability) * execution.no_fill_cost
            - execution.submit_cost
        )
        if not data_healthy:
            return DecisionResult(False, "DATA_UNHEALTHY", ev_fill, ev_submit)
        if not model_applicable:
            return DecisionResult(False, "OUT_OF_DISTRIBUTION", ev_fill, ev_submit)
        if gate_level != GateLevel.OPEN:
            return DecisionResult(False, "RISK_GATE_%s" % gate_level.name, ev_fill, ev_submit)
        if ev_submit < self.minimum_submit_ev:
            return DecisionResult(False, "NEGATIVE_OR_INSUFFICIENT_EV", ev_fill, ev_submit)
        return DecisionResult(True, "TRADE", ev_fill, ev_submit)
