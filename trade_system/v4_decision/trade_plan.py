from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Action = Literal["LONG", "SHORT", "WAIT", "NO_TRADE", "REDUCE", "EXIT", "REENTER", "OTHER"]
OrderType = Literal["PASSIVE_LIMIT", "MARKETABLE_LIMIT", "MARKET", "STOP", "STOP_LIMIT", "STAGED", "NONE"]


@dataclass(frozen=True)
class TradePlan:
    instrument: str
    venue: str
    action: Action
    horizon: str
    entry_condition: str
    invalidation: str
    structural_stop: Decimal | None
    notional: Decimal | None
    order_type: OrderType
    time_in_force: str
    max_slippage_pct: Decimal | None
    expected_cost: Decimal | None
    stress_cost: Decimal | None
    evidence_id: str | None = None
    management_events: tuple[str, ...] = field(default_factory=tuple)
    executable: bool = False


def validate_trade_plan(plan: TradePlan) -> list[str]:
    errors: list[str] = []
    if not plan.instrument or not plan.venue or not plan.horizon:
        errors.append("instrument, venue and horizon are required")
    if not plan.entry_condition or not plan.invalidation:
        errors.append("entry condition and invalidation are required")
    if plan.action in {"LONG", "SHORT", "REENTER"}:
        if plan.structural_stop is None:
            errors.append("directional plans require a structural stop")
        if plan.notional is None or plan.notional <= 0:
            errors.append("directional plans require positive notional")
        if not plan.evidence_id:
            errors.append("directional exposure requires a new evidence id")
    if plan.action in {"WAIT", "NO_TRADE"} and plan.order_type != "NONE":
        errors.append("WAIT/NO_TRADE must not carry an order route")
    if plan.max_slippage_pct is not None and plan.max_slippage_pct < 0:
        errors.append("max slippage cannot be negative")
    if plan.executable:
        errors.append("V4 decision plans are non-executable; execution authority is separate")
    return errors
