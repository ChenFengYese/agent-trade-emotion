"""Stable domain types shared by capture, replay, research and paper execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(UTC)


class AvailabilityKind(str, Enum):
    ACTUAL = "ACTUAL"
    RECONSTRUCTED = "RECONSTRUCTED"


class BookHealth(str, Enum):
    INVALID = "INVALID"
    VALID = "VALID"


class GateLevel(int, Enum):
    OPEN = 0
    NO_NEW_RISK = 1
    HALT_AND_RECONCILE = 2


class SystemHealth(str, Enum):
    WARMUP = "WARMUP"
    READY = "READY"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"


class EpisodeState(str, Enum):
    OBSERVE = "OBSERVE"
    EXPANDING = "EXPANDING"
    DECELERATING = "DECELERATING"
    ABSORBING = "ABSORBING"
    RESPONDING = "RESPONDING"
    REVERSAL_CONFIRMED = "REVERSAL_CONFIRMED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    UNKNOWN = "UNKNOWN"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionStage(str, Enum):
    ENTER_PROBE = "ENTER_PROBE"
    ADD_POSITION_CONFIRMED = "ADD_POSITION_CONFIRMED"


class OrderStatus(str, Enum):
    INTENT = "INTENT"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    PROTECTION_REQUIRED = "PROTECTION_REQUIRED"
    PROTECTED = "PROTECTED"
    RECONCILED = "RECONCILED"


@dataclass(frozen=True)
class RawCapture:
    event_id: str
    source: str
    venue: str
    instrument: str
    stream: str
    connection_id: str
    ingest_seq: int
    capture_seq: int
    receive_time: datetime
    receive_monotonic_ns: int
    payload: Dict[str, Any]
    payload_hash: str
    raw_segment: str
    raw_offset: int
    exchange_event_time: Optional[datetime] = None
    venue_trade_date: Optional[str] = None
    source_as_of: Optional[datetime] = None
    publish_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_type": "raw_capture",
            "event_id": self.event_id,
            "source": self.source,
            "venue": self.venue,
            "instrument": self.instrument,
            "stream": self.stream,
            "connection_id": self.connection_id,
            "ingest_seq": self.ingest_seq,
            "capture_seq": self.capture_seq,
            "receive_time": iso_utc(self.receive_time),
            "receive_monotonic_ns": self.receive_monotonic_ns,
            "payload": self.payload,
            "payload_hash": self.payload_hash,
            "raw_segment": self.raw_segment,
            "raw_offset": self.raw_offset,
            "exchange_event_time": iso_utc(self.exchange_event_time) if self.exchange_event_time else None,
            "venue_trade_date": self.venue_trade_date,
            "source_as_of": iso_utc(self.source_as_of) if self.source_as_of else None,
            "publish_time": iso_utc(self.publish_time) if self.publish_time else None,
        }


@dataclass(frozen=True)
class AvailabilityRecord:
    event_id: str
    schema_version: str
    derived_at: datetime
    available_at: datetime
    availability_kind: AvailabilityKind
    quality_flags: List[str] = field(default_factory=list)
    sequence_start: Optional[int] = None
    sequence_end: Optional[int] = None
    normalized: Dict[str, Any] = field(default_factory=dict)
    reconstruction_basis: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.available_at < self.derived_at and self.availability_kind == AvailabilityKind.ACTUAL:
            raise ValueError("ACTUAL available_at cannot precede derived_at")
        if self.availability_kind == AvailabilityKind.RECONSTRUCTED and not self.reconstruction_basis:
            raise ValueError("RECONSTRUCTED records require reconstruction_basis")
        if self.availability_kind == AvailabilityKind.ACTUAL and self.reconstruction_basis:
            raise ValueError("ACTUAL records must not contain reconstruction_basis")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_type": "availability_record",
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "derived_at": iso_utc(self.derived_at),
            "available_at": iso_utc(self.available_at),
            "availability_kind": self.availability_kind.value,
            "quality_flags": list(self.quality_flags),
            "sequence_start": self.sequence_start,
            "sequence_end": self.sequence_end,
            "normalized": self.normalized,
            "reconstruction_basis": self.reconstruction_basis,
        }


@dataclass(frozen=True)
class TradePrint:
    available_at: datetime
    price: Decimal
    quantity: Decimal
    aggressor_side: Side

    @property
    def signed_notional(self) -> Decimal:
        sign = Decimal("1") if self.aggressor_side == Side.BUY else Decimal("-1")
        return sign * self.price * self.quantity


@dataclass(frozen=True)
class FeatureSnapshot:
    available_at: datetime
    availability_kind: AvailabilityKind
    feature_version: str
    values: Dict[str, Decimal]
    quality_flags: List[str]
    book_health: BookHealth


@dataclass
class OrderIntent:
    intent_id: str
    episode_id: str
    side: Side
    stage: PositionStage
    quantity: Decimal
    limit_price: Decimal
    stop_price: Decimal
    created_at: datetime
    model_version: str
    policy_version: str
    # Exit intents must be explicitly reduce-only.  This is a local paper
    # contract; a future venue adapter must additionally obtain the venue's
    # own reduce-only acknowledgement before treating an exit as protected.
    reduce_only: bool = False


@dataclass
class PaperFill:
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime


@dataclass
class ManagedOrder:
    client_order_id: str
    intent: OrderIntent
    status: OrderStatus = OrderStatus.INTENT
    fills: List[PaperFill] = field(default_factory=list)
    protection_quantity: Decimal = Decimal("0")
    rejection_reason: Optional[str] = None
    status_history: List[OrderStatus] = field(default_factory=lambda: [OrderStatus.INTENT])

    @property
    def filled_quantity(self) -> Decimal:
        return sum((item.quantity for item in self.fills), Decimal("0"))

    def transition(self, status: OrderStatus) -> None:
        self.status = status
        self.status_history.append(status)
