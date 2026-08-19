"""Immutable dual-state geometry model.

Analytical geometry is decision support.  Protection barriers are executable
replay state.  They intentionally do not share a lifecycle status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum


class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class ProbabilityStatus(StrEnum):
    CALIBRATED_OOS = "CALIBRATED_OOS"
    ORDINAL_ONLY = "ORDINAL_ONLY"
    UNKNOWN = "UNKNOWN"


class AnalysisGeometryStatus(StrEnum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    ACTIVE_ANALYSIS = "ACTIVE_ANALYSIS"
    STALE_FOR_NEW_DECISIONS = "STALE_FOR_NEW_DECISIONS"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class ExecutionBarrierStatus(StrEnum):
    NONE = "NONE"
    PENDING_VENUE_ACK = "PENDING_VENUE_ACK"
    ACTIVE_PROTECTION = "ACTIVE_PROTECTION"
    SUPERSEDED = "SUPERSEDED"
    TRIGGERED = "TRIGGERED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ACK_TIMEOUT = "ACK_TIMEOUT"
    HALTED_RECONCILE = "HALTED_RECONCILE"


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("CLOCK_TIME_INVALID")


def _require_decimal(value: Decimal | None, name: str) -> None:
    if value is not None and (
        not isinstance(value, Decimal) or not value.is_finite()
    ):
        raise TypeError(f"{name}_MUST_BE_FINITE_DECIMAL")


@dataclass(frozen=True, slots=True)
class AnalysisGeometry:
    geometry_id: str
    revision: int
    side: PositionSide
    status: AnalysisGeometryStatus
    stop_price: Decimal
    target_price: Decimal | None
    horizon_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if not self.geometry_id or self.revision < 1:
            raise ValueError("GEOMETRY_PRIOR_VERSION_MISMATCH")
        _require_decimal(self.stop_price, "stop_price")
        _require_decimal(self.target_price, "target_price")
        if self.stop_price <= 0 or (
            self.target_price is not None and self.target_price <= 0
        ):
            raise ValueError("GEOMETRY_PRICE_INVALID")
        _require_utc(self.horizon_at)
        _require_utc(self.valid_until)
        if self.valid_until > self.horizon_at:
            raise ValueError("GEOMETRY_VALIDITY_AFTER_HORIZON")


@dataclass(frozen=True, slots=True)
class ProtectionBarrier:
    barrier_id: str
    revision: int
    side: PositionSide
    status: ExecutionBarrierStatus
    stop_price: Decimal
    target_price: Decimal | None
    horizon_at: datetime
    position_locked: bool
    active_from: datetime | None = None
    acknowledged_at: datetime | None = None
    previous_barrier_id: str | None = None

    def __post_init__(self) -> None:
        if not self.barrier_id or self.revision < 1:
            raise ValueError("GEOMETRY_PRIOR_VERSION_MISMATCH")
        _require_decimal(self.stop_price, "stop_price")
        _require_decimal(self.target_price, "target_price")
        if self.stop_price <= 0 or (
            self.target_price is not None and self.target_price <= 0
        ):
            raise ValueError("GEOMETRY_PRICE_INVALID")
        _require_utc(self.horizon_at)
        for value in (self.active_from, self.acknowledged_at):
            if value is not None:
                _require_utc(value)
        if (
            self.status is ExecutionBarrierStatus.ACTIVE_PROTECTION
            and (self.active_from is None or self.acknowledged_at is None)
        ):
            raise ValueError("GEOMETRY_ACK_MISSING")


@dataclass(frozen=True, slots=True)
class GeometryAggregate:
    """The two lifecycles at one accepted aggregate revision."""

    aggregate_id: str
    revision: int
    analysis: AnalysisGeometry
    protection: ProtectionBarrier

    def __post_init__(self) -> None:
        if not self.aggregate_id or self.revision < 1:
            raise ValueError("GEOMETRY_PRIOR_VERSION_MISMATCH")
        if self.analysis.side is not self.protection.side:
            raise ValueError("GEOMETRY_SIDE_MISMATCH")
