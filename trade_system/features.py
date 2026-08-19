"""Explicit proxy measurements for the documented five-factor theory."""

from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Deque, Dict, List, Optional, Tuple

from .order_book import OrderBook
from .types import AvailabilityKind, BookHealth, FeatureSnapshot, Side, TradePrint


class FeatureEngine:
    """Measurements only; it never infers trader identity or psychology."""

    def __init__(self, window: timedelta = timedelta(seconds=10), feature_version: str = "five-factor-proxy-v1") -> None:
        self.window = window
        self.feature_version = feature_version
        self.trades: Deque[TradePrint] = deque()
        self.liquidations: Deque[Tuple[datetime, Decimal, bool]] = deque()
        self.oi_previous: Optional[Decimal] = None
        self.oi_change = Decimal("0")
        self.crowding: Dict[str, Decimal] = {}
        self._previous_mid: Optional[Decimal] = None
        self._previous_bid_depth: Optional[Decimal] = None
        self._previous_ask_depth: Optional[Decimal] = None

    def add_trade(self, item: TradePrint) -> None:
        self.trades.append(item)
        self._prune(item.available_at)

    def update_open_interest(self, value: Decimal) -> None:
        if value <= 0:
            raise ValueError("open interest must be positive")
        if self.oi_previous is not None:
            self.oi_change = Decimal(str(math.log(float(value / self.oi_previous))))
        self.oi_previous = value

    def update_crowding(self, **components: Decimal) -> None:
        self.crowding.update({key: Decimal(str(value)) for key, value in components.items()})

    def add_liquidation(self, available_at: datetime, side: Side, price: Decimal, quantity: Decimal, censored: bool = True) -> None:
        if quantity <= 0 or price <= 0:
            raise ValueError("liquidation price and quantity must be positive")
        signed = quantity * price * (Decimal("1") if side == Side.BUY else Decimal("-1"))
        self.liquidations.append((available_at, signed, censored))
        self._prune(available_at)

    def _prune(self, now: datetime) -> None:
        cutoff = now - self.window
        while self.trades and self.trades[0].available_at < cutoff:
            self.trades.popleft()
        while self.liquidations and self.liquidations[0][0] < cutoff:
            self.liquidations.popleft()

    def snapshot(
        self,
        *,
        available_at: datetime,
        book: OrderBook,
        availability_kind: AvailabilityKind,
        quality_flags: Optional[List[str]] = None,
    ) -> FeatureSnapshot:
        self._prune(available_at)
        flags = list(quality_flags or [])
        if book.health != BookHealth.VALID:
            flags.append("book_invalid")
            return FeatureSnapshot(available_at, availability_kind, self.feature_version, {}, sorted(set(flags)), book.health)

        signed_notional = sum((trade.signed_notional for trade in self.trades), Decimal("0"))
        visible_depth = book.depth_notional(Side.BUY) + book.depth_notional(Side.SELL)
        directional_pressure = signed_notional / visible_depth if visible_depth > 0 else Decimal("0")
        forced_pressure = sum((item[1] for item in self.liquidations), Decimal("0"))
        censored_count = sum(1 for item in self.liquidations if item[2])
        if censored_count:
            flags.append("liquidation_censored")
        if not self.liquidations:
            # forceOrder is an at-most-one-per-symbol-per-second snapshot
            # stream. Silence is not evidence of a complete zero-liquidation
            # interval, so preserve its absence as a quality condition.
            flags.append("liquidation_unobserved")
        observed_coverage = Decimal(str(1 - censored_count / len(self.liquidations))) if self.liquidations else Decimal("0")
        if self.oi_previous is None:
            flags.append("open_interest_unavailable")
        if "funding_rate" not in self.crowding:
            flags.append("crowding_unavailable")

        mid = book.mid_price
        bid_depth = book.depth_notional(Side.SELL)
        ask_depth = book.depth_notional(Side.BUY)
        impact = Decimal("0") if not self._previous_mid else (mid - self._previous_mid) / self._previous_mid
        bid_replenishment = Decimal("0") if not self._previous_bid_depth else (bid_depth - self._previous_bid_depth) / self._previous_bid_depth
        ask_replenishment = Decimal("0") if not self._previous_ask_depth else (ask_depth - self._previous_ask_depth) / self._previous_ask_depth
        impact_per_flow = abs(impact) / max(abs(signed_notional), Decimal("1"))
        resilience_sell = bid_replenishment - impact_per_flow if signed_notional < 0 else bid_replenishment
        resilience_buy = ask_replenishment - impact_per_flow if signed_notional > 0 else ask_replenishment
        self._previous_mid, self._previous_bid_depth, self._previous_ask_depth = mid, bid_depth, ask_depth

        values: Dict[str, Decimal] = {
            "mid_price": mid,
            "microprice": book.microprice(),
            "spread": book.spread,
            "D_directional_pressure": directional_pressure,
            "L_log_oi_change": self.oi_change,
            "F_forced_pressure": forced_pressure,
            "F_observed_coverage": observed_coverage,
            "R_sell_bid_resilience": resilience_sell,
            "R_buy_ask_resilience": resilience_buy,
            "price_impact": impact,
            "visible_depth_notional": visible_depth,
        }
        for name, value in self.crowding.items():
            values["C_" + name] = value
        return FeatureSnapshot(available_at, availability_kind, self.feature_version, values, sorted(set(flags)), book.health)
