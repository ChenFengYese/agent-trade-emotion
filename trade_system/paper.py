"""Visible-book, marketable-limit IOC simulation for research and paper tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from .order_book import OrderBook
from .risk import OrderManager
from .types import OrderStatus, PaperFill


class PaperBroker:
    def __init__(self, fee_rate: Decimal) -> None:
        if fee_rate < 0:
            raise ValueError("fee_rate must be non-negative")
        self.fee_rate = fee_rate

    def execute_ioc(self, order_manager: OrderManager, intent_id: str, book: OrderBook, now: datetime) -> List[PaperFill]:
        order = order_manager.orders_by_intent[intent_id]
        if order.status != OrderStatus.ACKNOWLEDGED:
            raise RuntimeError("order must be acknowledged before execution")
        estimate = book.estimate_ioc(order.intent.side, order.intent.quantity, order.intent.limit_price)
        fills: List[PaperFill] = []
        if estimate.filled_quantity > 0 and estimate.average_price is not None:
            fee = estimate.filled_quantity * estimate.average_price * self.fee_rate
            fill = PaperFill(
                quantity=estimate.filled_quantity,
                price=estimate.average_price,
                fee=fee,
                filled_at=now,
            )
            order_manager.apply_fill(intent_id, fill, terminal=estimate.remaining_quantity == 0)
            fills.append(fill)
        order_manager.finalize_ioc(intent_id, now=now)
        return fills
