from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN


@dataclass(frozen=True)
class RiskInputs:
    equity: Decimal
    trade_risk_budget: Decimal
    entry_price: Decimal
    structural_stop: Decimal
    stress_buffer_pct: Decimal = Decimal("0")
    execution_cost: Decimal = Decimal("0")
    stress_risk_limit: Decimal | None = None
    tail_risk_limit: Decimal | None = None
    tail_multiplier: Decimal = Decimal("1.5")


@dataclass(frozen=True)
class RiskResult:
    structural_distance_pct: Decimal
    max_notional_structural: Decimal
    max_notional_stress: Decimal
    selected_notional: Decimal
    structural_loss: Decimal
    stress_loss: Decimal
    tail_loss: Decimal


def _abs_pct(a: Decimal, b: Decimal) -> Decimal:
    if a <= 0 or b <= 0:
        raise ValueError("prices must be positive")
    return abs(a - b) / a


def size_from_risk(inputs: RiskInputs) -> RiskResult:
    if inputs.equity <= 0 or inputs.trade_risk_budget <= 0:
        raise ValueError("equity and risk budget must be positive")
    d = _abs_pct(inputs.entry_price, inputs.structural_stop)
    if d == 0:
        raise ValueError("structural stop must differ from entry")
    if inputs.stress_buffer_pct < 0 or inputs.execution_cost < 0:
        raise ValueError("stress buffer and execution cost cannot be negative")

    max_struct = inputs.trade_risk_budget / d
    stress_limit = inputs.stress_risk_limit or inputs.trade_risk_budget
    stress_per_notional = d + inputs.stress_buffer_pct
    max_stress = (stress_limit - inputs.execution_cost) / stress_per_notional if stress_limit > inputs.execution_cost else Decimal("0")
    selected = min(max_struct, max_stress)
    structural_loss = selected * d
    stress_loss = selected * stress_per_notional + inputs.execution_cost
    tail_loss = stress_loss * inputs.tail_multiplier
    if inputs.tail_risk_limit is not None and tail_loss > inputs.tail_risk_limit:
        tail_cap = inputs.tail_risk_limit / inputs.tail_multiplier
        tail_notional = (tail_cap - inputs.execution_cost) / stress_per_notional if tail_cap > inputs.execution_cost else Decimal("0")
        selected = min(selected, max(Decimal("0"), tail_notional))
        structural_loss = selected * d
        stress_loss = selected * stress_per_notional + inputs.execution_cost
        tail_loss = stress_loss * inputs.tail_multiplier

    return RiskResult(d, max_struct, max_stress, selected, structural_loss, stress_loss, tail_loss)
