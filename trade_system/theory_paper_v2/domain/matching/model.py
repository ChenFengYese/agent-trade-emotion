"""Strict Decimal models for closed-bar E0 matching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum


class BarrierType(StrEnum):
    KILL = "KILL"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    STOP_MARKET = "STOP_MARKET"
    PROTECTION_REPAIR = "PROTECTION_REPAIR"
    STRUCTURE_EXIT_MARKET = "STRUCTURE_EXIT_MARKET"
    TARGET_LIMIT = "TARGET_LIMIT"
    TIMEOUT = "TIMEOUT"
    ENTRY_STOP_MARKET = "ENTRY_STOP_MARKET"
    ENTRY_LIMIT = "ENTRY_LIMIT"
    BARRIER_UPDATE = "BARRIER_UPDATE"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class LimitTouchPolicy(StrEnum):
    REQUIRE_CROSS_BEYOND_ONE_TICK = "REQUIRE_CROSS_BEYOND_ONE_TICK"
    ACTUAL_FILL_ONLY = "ACTUAL_FILL_ONLY"


class PartialFillPolicy(StrEnum):
    ACTUAL_OR_VOLUME_MODEL_ONLY = "ACTUAL_OR_VOLUME_MODEL_ONLY"


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("CLOCK_TIME_INVALID")


def _require_decimal(
    value: Decimal | None,
    name: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"{name}_MUST_BE_FINITE_DECIMAL")
    if positive and value <= 0:
        raise ValueError(f"{name}_MUST_BE_POSITIVE")
    if nonnegative and value < 0:
        raise ValueError(f"{name}_MUST_BE_NONNEGATIVE")


@dataclass(frozen=True, slots=True)
class MatchingPolicy:
    policy_id: str
    instrument_id: str
    venue_id: str
    price_tick: Decimal | None
    quantity_step: Decimal | None
    contract_multiplier: Decimal | None
    fee_rate: Decimal | None
    adverse_slippage_bps: Decimal | None
    limit_touch_policy: LimitTouchPolicy = (
        LimitTouchPolicy.REQUIRE_CROSS_BEYOND_ONE_TICK
    )
    partial_fill_policy: PartialFillPolicy = (
        PartialFillPolicy.ACTUAL_OR_VOLUME_MODEL_ONLY
    )
    volume_participation_cap: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.policy_id or not self.instrument_id or not self.venue_id:
            raise ValueError("MATCHING_POLICY_MISSING")
        _require_decimal(self.price_tick, "price_tick", positive=True)
        _require_decimal(self.quantity_step, "quantity_step", positive=True)
        _require_decimal(
            self.contract_multiplier, "contract_multiplier", positive=True
        )
        _require_decimal(self.fee_rate, "fee_rate", nonnegative=True)
        _require_decimal(
            self.adverse_slippage_bps,
            "adverse_slippage_bps",
            nonnegative=True,
        )
        _require_decimal(
            self.volume_participation_cap,
            "volume_participation_cap",
            positive=True,
        )
        if (
            self.volume_participation_cap is not None
            and self.volume_participation_cap > Decimal("1")
        ):
            raise ValueError("MATCHING_PARTICIPATION_CAP_INVALID")


@dataclass(frozen=True, slots=True)
class BarrierOrder:
    order_id: str
    instrument_id: str
    venue_id: str
    barrier_type: BarrierType
    side: OrderSide
    quantity: Decimal
    remaining_quantity: Decimal
    trigger_price: Decimal | None
    limit_price: Decimal | None
    reduce_only: bool
    active_from: datetime
    active_until: datetime
    protection_priority: int
    lot_id: str | None = None
    stage_id: str | None = None
    geometry_id: str | None = None
    event_triggered: bool = False

    def __post_init__(self) -> None:
        if not self.order_id or not self.instrument_id or not self.venue_id:
            raise ValueError("MATCHING_BARRIER_INACTIVE")
        _require_decimal(self.quantity, "quantity", positive=True)
        _require_decimal(
            self.remaining_quantity, "remaining_quantity", nonnegative=True
        )
        _require_decimal(self.trigger_price, "trigger_price", positive=True)
        _require_decimal(self.limit_price, "limit_price", positive=True)
        if self.remaining_quantity > self.quantity:
            raise ValueError("MATCHING_PARTIAL_FILL_UNIDENTIFIED")
        _require_utc(self.active_from)
        _require_utc(self.active_until)
        if self.active_until <= self.active_from or self.protection_priority < 0:
            raise ValueError("MATCHING_BARRIER_INACTIVE")
        if self.barrier_type in {
            BarrierType.STOP_MARKET,
            BarrierType.ENTRY_STOP_MARKET,
        } and self.trigger_price is None:
            raise ValueError("MATCHING_BARRIER_INACTIVE")
        if self.barrier_type in {
            BarrierType.TARGET_LIMIT,
            BarrierType.ENTRY_LIMIT,
        } and self.limit_price is None:
            raise ValueError("MATCHING_BARRIER_INACTIVE")
        if (
            self.lot_id is None
            and self.stage_id is None
            and self.barrier_type
            not in {BarrierType.KILL, BarrierType.ACCOUNT_MISMATCH}
        ):
            raise ValueError("MATCHING_BARRIER_INACTIVE")
        if self.barrier_type in {
            BarrierType.STOP_MARKET,
            BarrierType.PROTECTION_REPAIR,
            BarrierType.STRUCTURE_EXIT_MARKET,
            BarrierType.TARGET_LIMIT,
            BarrierType.TIMEOUT,
        } and (not self.reduce_only or self.geometry_id is None):
            raise ValueError("MATCHING_BARRIER_INACTIVE")
        if self.barrier_type in {
            BarrierType.ENTRY_STOP_MARKET,
            BarrierType.ENTRY_LIMIT,
        } and (self.stage_id is None or self.geometry_id is None):
            raise ValueError("MATCHING_BARRIER_INACTIVE")


@dataclass(frozen=True, slots=True)
class ClosedBar:
    bar_id: str
    instrument_id: str
    venue_id: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    observed_at: datetime
    available_at: datetime
    ingested_at: datetime
    source_committed_at: datetime
    source_commit_receipt_valid: bool
    lineage_digest_valid: bool

    def __post_init__(self) -> None:
        if not self.bar_id or not self.instrument_id or not self.venue_id:
            raise ValueError("MATCHING_BAR_LINEAGE_INVALID")
        for value in (
            self.open_time,
            self.close_time,
            self.observed_at,
            self.available_at,
            self.ingested_at,
            self.source_committed_at,
        ):
            _require_utc(value)
        if not (
            self.open_time
            < self.close_time
            <= self.observed_at
            <= self.available_at
            <= self.ingested_at
            <= self.source_committed_at
        ):
            raise ValueError("MATCHING_BAR_LINEAGE_INVALID")
        for name, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
            ("volume", self.volume),
        ):
            _require_decimal(value, name, nonnegative=name == "volume")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("MATCHING_BAR_LINEAGE_INVALID")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("MATCHING_BAR_LINEAGE_INVALID")
        if self.high < self.low:
            raise ValueError("MATCHING_BAR_LINEAGE_INVALID")


@dataclass(frozen=True, slots=True)
class MatchResult:
    order_id: str
    barrier_type: BarrierType
    bar_id: str
    fill_price: Decimal
    fill_quantity: Decimal
    notional: Decimal
    fee: Decimal
    slippage_amount: Decimal
    ambiguous_barrier_order: bool
    adverse_bound_price: Decimal | None
    favorable_bound_price: Decimal | None
    diagnostic_codes: tuple[str, ...]
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False
