"""Pure, fail-closed aggregation of explicitly finalized UTC one-minute bars."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Tuple

from .types import iso_utc


UTC = timezone.utc
SUPPORTED_TARGET_INTERVALS = ("15m", "1h", "4h", "1d")
_INTERVAL_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}


class BarResamplerError(ValueError):
    """Raised when a source series cannot safely form complete target bars."""


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise BarResamplerError("%s must be timezone-aware UTC time" % field)
    result = value.astimezone(UTC)
    if result.second or result.microsecond:
        raise BarResamplerError("%s must be aligned to an exact minute" % field)
    return result


def _decimal(value: Any, field: str, *, positive: bool = False, non_negative: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise BarResamplerError("%s must not be binary float or bool" % field)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BarResamplerError("%s must be decimal-compatible" % field) from exc
    if not result.is_finite():
        raise BarResamplerError("%s must be finite" % field)
    if positive and result <= 0:
        raise BarResamplerError("%s must be positive" % field)
    if non_negative and result < 0:
        raise BarResamplerError("%s must be non-negative" % field)
    return result


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BarResamplerError("%s must be a non-empty string" % field)
    return value


@dataclass(frozen=True)
class FinalizedMinuteBar:
    """A complete one-minute source bar that may be used only after close."""

    source_id: str
    instrument_id: str
    open_at: datetime
    close_at: datetime
    open: Any
    high: Any
    low: Any
    close: Any
    volume: Any
    available_at: datetime

    def validated(self) -> "FinalizedMinuteBar":
        source_id = _non_empty(self.source_id, "source_id")
        instrument_id = _non_empty(self.instrument_id, "instrument_id")
        open_at = _utc(self.open_at, "open_at")
        close_at = _utc(self.close_at, "close_at")
        available_at = _utc(self.available_at, "available_at")
        if close_at != open_at + timedelta(minutes=1):
            raise BarResamplerError("source bar must have exact one-minute half-open interval")
        if available_at < close_at:
            raise BarResamplerError("source bar is not available after its close")
        opening = _decimal(self.open, "open", positive=True)
        high = _decimal(self.high, "high", positive=True)
        low = _decimal(self.low, "low", positive=True)
        closing = _decimal(self.close, "close", positive=True)
        volume = _decimal(self.volume, "volume", non_negative=True)
        if low > min(opening, closing) or high < max(opening, closing) or low > high:
            raise BarResamplerError("OHLC ordering is invalid")
        return FinalizedMinuteBar(
            source_id=source_id,
            instrument_id=instrument_id,
            open_at=open_at,
            close_at=close_at,
            open=opening,
            high=high,
            low=low,
            close=closing,
            volume=volume,
            available_at=available_at,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FinalizedMinuteBar":
        required = {
            "source_id", "instrument_id", "open_at", "close_at", "open", "high", "low", "close", "volume", "available_at",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise BarResamplerError("source bar schema is invalid")
        return cls(**dict(value)).validated()

    def to_dict(self) -> dict[str, Any]:
        value = self.validated()
        return {
            "source_id": value.source_id,
            "instrument_id": value.instrument_id,
            "open_at": iso_utc(value.open_at),
            "close_at": iso_utc(value.close_at),
            "open": str(value.open),
            "high": str(value.high),
            "low": str(value.low),
            "close": str(value.close),
            "volume": str(value.volume),
            "available_at": iso_utc(value.available_at),
        }


@dataclass(frozen=True)
class ClosedBar:
    """A complete target bar; it is unavailable before the target close."""

    target_interval: str
    instrument_id: str
    open_at: datetime
    close_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    available_at: datetime
    source_ids: Tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_interval": self.target_interval,
            "instrument_id": self.instrument_id,
            "open_at": iso_utc(self.open_at),
            "close_at": iso_utc(self.close_at),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "available_at": iso_utc(self.available_at),
            "source_ids": list(self.source_ids),
        }

    def canonical_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _bucket_start(value: datetime, target_interval: str) -> datetime:
    if target_interval == "15m":
        return value.replace(minute=(value.minute // 15) * 15, second=0, microsecond=0)
    if target_interval == "1h":
        return value.replace(minute=0, second=0, microsecond=0)
    if target_interval == "4h":
        return value.replace(hour=(value.hour // 4) * 4, minute=0, second=0, microsecond=0)
    if target_interval == "1d":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    raise BarResamplerError("unsupported target interval")


def resample_closed_bars(source_bars: Iterable[FinalizedMinuteBar], target_interval: str) -> Tuple[ClosedBar, ...]:
    """Return only complete target bars, rejecting gaps, duplicates and partial tails."""

    if target_interval not in SUPPORTED_TARGET_INTERVALS:
        raise BarResamplerError("unsupported target interval")
    bars = tuple(item.validated() if isinstance(item, FinalizedMinuteBar) else FinalizedMinuteBar.from_mapping(item) for item in source_bars)
    if not bars:
        return ()
    instrument_id = bars[0].instrument_id
    previous_open = None
    previous_available = None
    source_ids = set()
    for bar in bars:
        if bar.instrument_id != instrument_id:
            raise BarResamplerError("all source bars must have one instrument")
        if bar.source_id in source_ids:
            raise BarResamplerError("duplicate source_id")
        source_ids.add(bar.source_id)
        if previous_open is not None and bar.open_at != previous_open + timedelta(minutes=1):
            raise BarResamplerError("source bars are duplicate, out of order, or gapped")
        if previous_available is not None and bar.available_at < previous_available:
            raise BarResamplerError("source bars are out of availability order")
        previous_open = bar.open_at
        previous_available = bar.available_at

    minutes = _INTERVAL_MINUTES[target_interval]
    outputs = []
    index = 0
    while index < len(bars):
        first = bars[index]
        target_open = _bucket_start(first.open_at, target_interval)
        target_close = target_open + timedelta(minutes=minutes)
        if first.open_at != target_open:
            raise BarResamplerError("partial target window must not emit a normal bar")
        window = bars[index:index + minutes]
        if len(window) != minutes:
            raise BarResamplerError("partial target window must not emit a normal bar")
        expected_open = target_open
        for bar in window:
            if bar.open_at != expected_open or bar.close_at > target_close:
                raise BarResamplerError("target source window is incomplete or crosses boundary")
            expected_open += timedelta(minutes=1)
        if expected_open != target_close:
            raise BarResamplerError("target source window is incomplete")
        available_at = max(bar.available_at for bar in window)
        if available_at < target_close:
            raise BarResamplerError("target bar cannot be visible before close")
        outputs.append(ClosedBar(
            target_interval=target_interval,
            instrument_id=instrument_id,
            open_at=target_open,
            close_at=target_close,
            open=window[0].open,
            high=max(bar.high for bar in window),
            low=min(bar.low for bar in window),
            close=window[-1].close,
            volume=sum((bar.volume for bar in window), Decimal("0")),
            available_at=available_at,
            source_ids=tuple(bar.source_id for bar in window),
        ))
        index += minutes
    return tuple(outputs)


__all__ = [
    "BarResamplerError", "ClosedBar", "FinalizedMinuteBar", "SUPPORTED_TARGET_INTERVALS", "resample_closed_bars",
]
