"""Transparent cost scenarios for research-time expected-value pressure tests.

All figures are quote-currency costs for a proposed quantity.  This module
does not infer exchange fees and deliberately requires every scenario to
declare its assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Tuple

from .decision import ConservativePolicy, DecisionResult, ExecutionForecast, OutcomeForecast
from .types import GateLevel


_BPS = Decimal("10000")


@dataclass(frozen=True)
class CostScenario:
    """Round-trip cost assumptions expressed as fractions or basis points."""

    scenario_id: str
    entry_fee_rate: Decimal
    exit_fee_rate: Decimal
    spread_bps: Decimal
    conditional_slippage_bps: Decimal
    funding_bps: Decimal
    tail_execution_bps: Decimal
    submit_cost: Decimal = Decimal("0")
    no_fill_cost: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ValueError("scenario_id is required")
        if any(value < 0 for value in (
            self.entry_fee_rate,
            self.exit_fee_rate,
            self.spread_bps,
            self.conditional_slippage_bps,
            self.funding_bps,
            self.tail_execution_bps,
            self.submit_cost,
            self.no_fill_cost,
        )):
            raise ValueError("cost assumptions must be non-negative")


@dataclass(frozen=True)
class CostEstimate:
    fee: Decimal
    spread: Decimal
    conditional_slippage: Decimal
    funding: Decimal
    tail_execution: Decimal

    @property
    def total(self) -> Decimal:
        return self.fee + self.spread + self.conditional_slippage + self.funding + self.tail_execution


@dataclass(frozen=True)
class CostPressureResult:
    scenario_id: str
    cost: CostEstimate
    decision: DecisionResult


def estimate_round_trip_cost(*, entry_price: Decimal, quantity: Decimal, scenario: CostScenario) -> CostEstimate:
    """Return explicitly decomposed cost; no invisible multipliers or defaults."""
    if entry_price <= 0 or quantity <= 0:
        raise ValueError("entry_price and quantity must be positive")
    notional = entry_price * quantity
    return CostEstimate(
        fee=notional * (scenario.entry_fee_rate + scenario.exit_fee_rate),
        spread=notional * scenario.spread_bps / _BPS,
        conditional_slippage=notional * scenario.conditional_slippage_bps / _BPS,
        funding=notional * scenario.funding_bps / _BPS,
        tail_execution=notional * scenario.tail_execution_bps / _BPS,
    )


def evaluate_cost_pressure(
    *,
    scenarios: Iterable[CostScenario],
    policy: ConservativePolicy,
    entry_price: Decimal,
    quantity: Decimal,
    outcome: OutcomeForecast,
    execution: ExecutionForecast,
    gain_if_tp: Decimal,
    loss_if_sl: Decimal,
    expected_structure_return: Decimal,
    expected_timeout_return: Decimal,
    gate_level: GateLevel,
    data_healthy: bool,
    model_applicable: bool,
) -> Tuple[CostPressureResult, ...]:
    results = []
    for scenario in scenarios:
        cost = estimate_round_trip_cost(entry_price=entry_price, quantity=quantity, scenario=scenario)
        # Fees/slippage occur only with a fill. Submit/no-fill costs remain
        # execution costs and belong in ExecutionForecast for this scenario.
        execution_for_scenario = ExecutionForecast(
            fill_probability=execution.fill_probability,
            expected_fill_fraction=execution.expected_fill_fraction,
            no_fill_cost=scenario.no_fill_cost,
            submit_cost=scenario.submit_cost,
        )
        decision = policy.evaluate(
            outcome=outcome,
            execution=execution_for_scenario,
            gain_if_tp=gain_if_tp,
            loss_if_sl=loss_if_sl,
            expected_structure_return=expected_structure_return,
            expected_timeout_return=expected_timeout_return,
            trade_cost=cost.total,
            gate_level=gate_level,
            data_healthy=data_healthy,
            model_applicable=model_applicable,
        )
        results.append(CostPressureResult(scenario.scenario_id, cost, decision))
    if not results:
        raise ValueError("at least one cost scenario is required")
    return tuple(results)
