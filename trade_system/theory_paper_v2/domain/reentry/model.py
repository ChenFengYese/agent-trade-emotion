"""Immutable reentry state and current-cutoff evaluation inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from ..strategic import StrategicStatus


class ReentryStatus(StrEnum):
    OPEN = "OPEN"
    DUE = "DUE"
    ELIGIBLE = "ELIGIBLE"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    CANCELLED_INVALIDATED = "CANCELLED_INVALIDATED"
    CANCELLED_CLOSED = "CANCELLED_CLOSED"


class EligibilityVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


TERMINAL_REENTRY_STATUSES = frozenset(
    {
        ReentryStatus.EXECUTED,
        ReentryStatus.EXPIRED,
        ReentryStatus.CANCELLED_INVALIDATED,
        ReentryStatus.CANCELLED_CLOSED,
    }
)


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("CLOCK_TIME_INVALID")


@dataclass(frozen=True, slots=True)
class ReentryContract:
    contract_id: str
    strategic_episode_id: str
    revision: int
    status: ReentryStatus
    opened_at: datetime
    earliest_review_at: datetime
    latest_review_at: datetime
    expires_at: datetime
    maximum_deferrals: int | None
    deferral_count: int
    minimum_core_quantity: Decimal
    last_reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.contract_id or not self.strategic_episode_id or self.revision < 1:
            raise ValueError("REENTRY_PRIOR_STATE_MISMATCH")
        for value in (
            self.opened_at,
            self.earliest_review_at,
            self.latest_review_at,
            self.expires_at,
        ):
            _require_utc(value)
        if self.last_reviewed_at is not None:
            _require_utc(self.last_reviewed_at)
        if not (
            self.opened_at
            <= self.earliest_review_at
            <= self.latest_review_at
            <= self.expires_at
        ):
            raise ValueError("REENTRY_REVIEW_OVERDUE")
        if self.maximum_deferrals is not None and self.maximum_deferrals < 0:
            raise ValueError("REENTRY_DEFERRAL_LIMIT_MISSING")
        if self.deferral_count < 0:
            raise ValueError("REENTRY_DEFERRAL_LIMIT_EXCEEDED")
        if (
            not isinstance(self.minimum_core_quantity, Decimal)
            or not self.minimum_core_quantity.is_finite()
            or self.minimum_core_quantity <= 0
        ):
            raise TypeError("REENTRY_CORE_QUANTITY_MUST_BE_POSITIVE_DECIMAL")


@dataclass(frozen=True, slots=True)
class ReentryEvaluation:
    event_id: str
    expected_revision: int
    decision_cutoff: datetime
    requested_status: ReentryStatus
    strategic_status: StrategicStatus
    eligibility: EligibilityVerdict = EligibilityVerdict.UNKNOWN
    deferral_frozen: bool = False
    next_review_at: datetime | None = None
    new_thi_present: bool = False
    risk_permission_pass: bool = False
    governance_pass: bool = False
    core_fill_reconciled: bool = False
    reconciled_core_quantity: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        _require_utc(self.decision_cutoff)
        if self.next_review_at is not None:
            _require_utc(self.next_review_at)
        if (
            not isinstance(self.reconciled_core_quantity, Decimal)
            or not self.reconciled_core_quantity.is_finite()
            or self.reconciled_core_quantity < 0
        ):
            raise TypeError("REENTRY_CORE_QUANTITY_MUST_BE_DECIMAL")
