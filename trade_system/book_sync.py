"""Snapshot-plus-buffer synchronizer for Binance depth deltas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .order_book import BookGapError, OrderBook


@dataclass(frozen=True)
class BufferedDelta:
    first_update_id: int
    final_update_id: int
    previous_final_update_id: int
    bids: List[List[str]]
    asks: List[List[str]]


class BinanceBookSynchronizer:
    """Buffers live deltas until a REST snapshot establishes a valid sequence."""

    def __init__(self, book: OrderBook) -> None:
        self.book = book
        self._buffer: List[BufferedDelta] = []

    def buffer_delta(self, normalized: Dict[str, Any]) -> None:
        if normalized.get("kind") != "delta":
            raise ValueError("expected normalized depth delta")
        self._buffer.append(
            BufferedDelta(
                first_update_id=int(normalized["U"]),
                final_update_id=int(normalized["u"]),
                previous_final_update_id=int(normalized["pu"]) if normalized.get("pu") is not None else -1,
                bids=list(normalized["bids"]),
                asks=list(normalized["asks"]),
            )
        )

    def apply_snapshot(self, normalized: Dict[str, Any]) -> None:
        if normalized.get("kind") != "snapshot":
            raise ValueError("expected normalized depth snapshot")
        self.book.reset_snapshot(
            last_update_id=int(normalized["last_update_id"]),
            bids=normalized["bids"],
            asks=normalized["asks"],
        )
        expected = self.book.last_update_id + 1 if self.book.last_update_id is not None else None
        buffered = sorted(self._buffer, key=lambda item: (item.first_update_id, item.final_update_id))
        self._buffer = []
        first_index = None
        for index, delta in enumerate(buffered):
            if delta.first_update_id <= expected <= delta.final_update_id:
                first_index = index
                break
        if first_index is None:
            # A snapshot without a matching buffered update is still a usable
            # book at the snapshot instant; later deltas must connect normally.
            return
        for delta in buffered[first_index:]:
            try:
                self.book.apply_delta(
                    first_update_id=delta.first_update_id,
                    final_update_id=delta.final_update_id,
                    previous_final_update_id=None if self.book.last_update_id == expected - 1 else delta.previous_final_update_id,
                    bids=delta.bids,
                    asks=delta.asks,
                )
            except BookGapError:
                self._buffer = []
                raise

    def apply_live_delta(self, normalized: Dict[str, Any]) -> None:
        if normalized.get("kind") != "delta":
            raise ValueError("expected normalized depth delta")
        self.book.apply_delta(
            first_update_id=int(normalized["U"]),
            final_update_id=int(normalized["u"]),
            previous_final_update_id=int(normalized["pu"]) if normalized.get("pu") is not None else None,
            bids=normalized["bids"],
            asks=normalized["asks"],
        )
