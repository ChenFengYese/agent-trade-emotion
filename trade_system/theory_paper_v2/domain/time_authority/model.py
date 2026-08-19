"""Explicit review clock without ambient-time access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReviewClock:
    clock_id: str
    next_review_at: datetime
    mandatory_review_at: datetime

    def __post_init__(self) -> None:
        if self.next_review_at.tzinfo is None or self.mandatory_review_at.tzinfo is None:
            raise ValueError("CLOCK_TIME_INVALID")
        if self.mandatory_review_at < self.next_review_at:
            raise ValueError("CLOCK_REVIEW_ORDER_INVALID")

    def due(self, supplied_time: datetime) -> bool:
        if supplied_time.tzinfo is None:
            raise ValueError("CLOCK_TIME_INVALID")
        return supplied_time >= self.next_review_at

    def overdue(self, supplied_time: datetime) -> bool:
        if supplied_time.tzinfo is None:
            raise ValueError("CLOCK_TIME_INVALID")
        return supplied_time >= self.mandatory_review_at

