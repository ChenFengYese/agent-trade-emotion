from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Scenario:
    name: str
    probability: Decimal
    gross_pnl: Decimal
    fees: Decimal = Decimal("0")
    funding: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    impact: Decimal = Decimal("0")
    execution_penalty: Decimal = Decimal("0")

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.fees - self.funding - self.slippage - self.impact - self.execution_penalty


@dataclass(frozen=True)
class EVResult:
    gross_ev: Decimal
    net_ev: Decimal
    probability_sum: Decimal


def net_ev(scenarios: list[Scenario], require_probability_sum: bool = True) -> EVResult:
    if not scenarios:
        raise ValueError("at least one scenario is required")
    total_p = sum((s.probability for s in scenarios), Decimal("0"))
    if any(s.probability < 0 for s in scenarios):
        raise ValueError("scenario probabilities cannot be negative")
    if require_probability_sum and total_p != Decimal("1"):
        raise ValueError("calibrated EV requires probabilities summing to 1")
    gross = sum((s.probability * s.gross_pnl for s in scenarios), Decimal("0"))
    net = sum((s.probability * s.net_pnl for s in scenarios), Decimal("0"))
    return EVResult(gross, net, total_p)
