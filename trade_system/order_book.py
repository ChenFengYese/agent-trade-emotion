"""Binance-style L2 snapshot/delta book with explicit gap invalidation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .types import BookHealth, Side


class BookGapError(RuntimeError):
    """A delta cannot be safely applied to the current book."""


PriceLevel = Tuple[Decimal, Decimal]


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class FillEstimate:
    requested_quantity: Decimal
    filled_quantity: Decimal
    average_price: Optional[Decimal]
    remaining_quantity: Decimal


class OrderBook:
    """Visible standard book only; RPI and hidden liquidity are never inferred."""

    def __init__(self) -> None:
        self.bids: Dict[Decimal, Decimal] = {}
        self.asks: Dict[Decimal, Decimal] = {}
        # Feature snapshots query the executable five-level depth repeatedly
        # between sparse L2 updates.  Keep those price levels incrementally so
        # a replay does not sort the complete book for every feature row.
        self._default_depth_prices: Dict[Side, Tuple[Decimal, ...]] = {
            Side.BUY: (),
            Side.SELL: (),
        }
        self.last_update_id: Optional[int] = None
        self.health = BookHealth.INVALID
        self.invalid_reason: Optional[str] = "no snapshot"
        self._awaiting_first_delta = True

    def reset_snapshot(
        self,
        *,
        last_update_id: int,
        bids: Iterable[Sequence[object]],
        asks: Iterable[Sequence[object]],
    ) -> None:
        self.bids = self._levels(bids)
        self.asks = self._levels(asks)
        self._refresh_default_depth_prices(Side.BUY)
        self._refresh_default_depth_prices(Side.SELL)
        self.last_update_id = int(last_update_id)
        self.health = BookHealth.VALID
        self.invalid_reason = None
        self._awaiting_first_delta = True
        self._validate_top()

    @staticmethod
    def _levels(levels: Iterable[Sequence[object]]) -> Dict[Decimal, Decimal]:
        parsed: Dict[Decimal, Decimal] = {}
        for level in levels:
            if len(level) < 2:
                raise ValueError("book level needs price and quantity")
            price, quantity = _decimal(level[0]), _decimal(level[1])
            if price <= 0 or quantity < 0:
                raise ValueError("invalid price or quantity")
            if quantity > 0:
                parsed[price] = quantity
        return parsed

    def invalidate(self, reason: str) -> None:
        self.health = BookHealth.INVALID
        self.invalid_reason = reason

    def apply_delta(
        self,
        *,
        first_update_id: int,
        final_update_id: int,
        previous_final_update_id: Optional[int],
        bids: Iterable[Sequence[object]],
        asks: Iterable[Sequence[object]],
    ) -> None:
        if self.health != BookHealth.VALID or self.last_update_id is None:
            raise BookGapError("book is invalid; snapshot required")
        first_update_id, final_update_id = int(first_update_id), int(final_update_id)
        if final_update_id < first_update_id:
            self.invalidate("delta final update precedes first update")
            raise BookGapError(self.invalid_reason or "invalid delta")
        if self._awaiting_first_delta:
            # The snapshot boundary is allowed to be covered by the first
            # buffered event (current Binance documentation) or by its
            # immediate successor (the established futures sequencing form).
            # Either way, do not apply a delta that starts after both.
            snapshot_boundary = self.last_update_id
            if not (
                first_update_id <= snapshot_boundary <= final_update_id
                or first_update_id <= snapshot_boundary + 1 <= final_update_id
            ):
                self.invalidate("first delta does not cover snapshot boundary")
                raise BookGapError(self.invalid_reason or "book gap")
        elif previous_final_update_id is None or int(previous_final_update_id) != self.last_update_id:
            # For subsequent events Binance publishes a `pu` chain. U is the
            # first update inside an aggregated event and need not equal the
            # preceding event's u + 1; requiring that would reject valid live
            # books under active markets.
            self.invalidate("previous final update mismatch")
            raise BookGapError(self.invalid_reason or "book gap")
        bid_changes = self._apply_levels(self.bids, bids)
        ask_changes = self._apply_levels(self.asks, asks)
        self._update_default_depth_prices(Side.SELL, bid_changes)
        self._update_default_depth_prices(Side.BUY, ask_changes)
        self.last_update_id = final_update_id
        self._awaiting_first_delta = False
        self._validate_top()

    @staticmethod
    def _apply_levels(target: Dict[Decimal, Decimal], levels: Iterable[Sequence[object]]) -> Dict[Decimal, Decimal]:
        changed: Dict[Decimal, Decimal] = {}
        for level in levels:
            if len(level) < 2:
                raise ValueError("book level needs price and quantity")
            price, quantity = _decimal(level[0]), _decimal(level[1])
            if price <= 0 or quantity < 0:
                raise ValueError("invalid price or quantity")
            if quantity == 0:
                target.pop(price, None)
            else:
                target[price] = quantity
            changed[price] = quantity
        return changed

    def _book_for_side(self, side: Side) -> Dict[Decimal, Decimal]:
        return self.asks if side == Side.BUY else self.bids

    @staticmethod
    def _ordered_prices(side: Side, book: Dict[Decimal, Decimal]) -> List[Decimal]:
        return sorted(book, reverse=side == Side.SELL)

    def _refresh_default_depth_prices(self, side: Side) -> None:
        self._default_depth_prices[side] = tuple(self._ordered_prices(side, self._book_for_side(side))[:5])

    def _update_default_depth_prices(self, side: Side, changes: Dict[Decimal, Decimal]) -> None:
        """Update cached five-level depth without rescanning an unchanged book."""
        if not changes:
            return
        current = list(self._default_depth_prices[side])
        # Removing an included price may expose any deeper price, so rebuild
        # from the book.  This is deliberately the conservative slow path.
        if any(price in current and quantity == 0 for price, quantity in changes.items()):
            self._refresh_default_depth_prices(side)
            return
        for price, quantity in changes.items():
            if quantity <= 0 or price in current:
                continue
            current.append(price)
        current = self._ordered_prices(side, {price: self._book_for_side(side)[price] for price in current if price in self._book_for_side(side)})[:5]
        self._default_depth_prices[side] = tuple(current)

    def _validate_top(self) -> None:
        if not self.bids or not self.asks:
            self.invalidate("empty visible side")
            return
        if self.best_bid >= self.best_ask:
            self.invalidate("crossed visible book")

    @property
    def best_bid(self) -> Decimal:
        if not self.bids:
            raise BookGapError("no bids")
        return self._default_depth_prices[Side.SELL][0]

    @property
    def best_ask(self) -> Decimal:
        if not self.asks:
            raise BookGapError("no asks")
        return self._default_depth_prices[Side.BUY][0]

    @property
    def mid_price(self) -> Decimal:
        if self.health != BookHealth.VALID:
            raise BookGapError(self.invalid_reason or "book invalid")
        return (self.best_bid + self.best_ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.best_ask - self.best_bid

    def depth_notional(self, side: Side, levels: int = 5) -> Decimal:
        book = self._book_for_side(side)
        if levels == 5:
            prices = self._default_depth_prices[side]
            return sum((price * book[price] for price in prices), Decimal("0"))
        total = Decimal("0")
        for price in self._ordered_prices(side, book)[:levels]:
            total += price * book[price]
        return total

    def microprice(self) -> Decimal:
        bid_qty, ask_qty = self.bids[self.best_bid], self.asks[self.best_ask]
        denominator = bid_qty + ask_qty
        if denominator <= 0:
            raise BookGapError("top depth is empty")
        return (self.best_ask * bid_qty + self.best_bid * ask_qty) / denominator

    def estimate_ioc(self, side: Side, quantity: Decimal, limit_price: Decimal) -> FillEstimate:
        """Consume visible levels without mutating the research book."""
        if self.health != BookHealth.VALID:
            raise BookGapError(self.invalid_reason or "book invalid")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        remaining = quantity
        notional = Decimal("0")
        levels = sorted(self.asks.items()) if side == Side.BUY else sorted(self.bids.items(), reverse=True)
        for price, visible_quantity in levels:
            executable = price <= limit_price if side == Side.BUY else price >= limit_price
            if not executable:
                break
            taken = min(remaining, visible_quantity)
            remaining -= taken
            notional += taken * price
            if remaining == 0:
                break
        filled = quantity - remaining
        average = notional / filled if filled > 0 else None
        return FillEstimate(quantity, filled, average, remaining)

    def checksum(self) -> str:
        canonical: List[str] = ["u=%s" % self.last_update_id, "health=%s" % self.health.value]
        canonical.extend("b:%s:%s" % (price, self.bids[price]) for price in sorted(self.bids, reverse=True))
        canonical.extend("a:%s:%s" % (price, self.asks[price]) for price in sorted(self.asks))
        return hashlib.sha256("|".join(canonical).encode("utf-8")).hexdigest()
