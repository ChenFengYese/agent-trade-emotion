"""Immutable offline portfolio values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ...domain.position import LotRole


class LotSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class Attribution(StrEnum):
    EXOGENOUS = "EXOGENOUS"
    STRATEGY = "STRATEGY"


@dataclass(frozen=True, slots=True)
class OfflineLot:
    lot_id: str
    instrument_id: str
    side: LotSide
    role: LotRole
    attribution: Attribution
    quantity: Decimal
    remaining_quantity: Decimal
    entry_price: Decimal
    stop_price: Decimal | None
    target_price: Decimal | None
    opened_at: datetime
    episode_id: str | None
    stage_id: str | None
    geometry_id: str | None
    contract_multiplier: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        decimals = (
            self.quantity,
            self.remaining_quantity,
            self.entry_price,
            self.contract_multiplier,
        )
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in decimals):
            raise TypeError("PORTFOLIO_DECIMAL_REQUIRED")
        if (
            self.quantity <= 0
            or self.remaining_quantity < 0
            or self.remaining_quantity > self.quantity
            or self.entry_price <= 0
            or self.contract_multiplier <= 0
        ):
            raise ValueError("PORTFOLIO_LOT_INVALID")
        for value in (self.stop_price, self.target_price):
            if value is not None and (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or value <= 0
            ):
                raise ValueError("PORTFOLIO_PROTECTION_INVALID")
        if self.opened_at.tzinfo is None:
            raise ValueError("CLOCK_TIME_INVALID")
        if self.attribution is Attribution.STRATEGY and (
            not self.episode_id or not self.stage_id or not self.geometry_id
        ):
            raise ValueError("PORTFOLIO_STRATEGY_LINEAGE_MISSING")


@dataclass(frozen=True, slots=True)
class FillRecord:
    fill_id: str
    lot_id: str
    instrument_id: str
    side: str
    quantity: Decimal
    fill_price: Decimal
    notional: Decimal
    fee: Decimal
    realized_pnl_before_fee: Decimal
    occurred_at: datetime
    reason: str
    attribution: Attribution


@dataclass(frozen=True, slots=True)
class PortfolioState:
    portfolio_id: str
    revision: int
    initial_equity: Decimal
    realized_pnl_before_cost: Decimal
    total_fees: Decimal
    lots: tuple[OfflineLot, ...]
    fills: tuple[FillRecord, ...]


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    portfolio_id: str
    revision: int
    marked_at: datetime
    marks: tuple[tuple[str, Decimal], ...]
    realized_pnl_before_cost: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    equity: Decimal
    gross_notional: Decimal
    open_risk_to_stop: Decimal | None
    unprotected_lot_ids: tuple[str, ...]
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False

