"""Public USD-M message normalization and append-only capture session.

The session accepts messages supplied by any transport. Transport lifecycle,
reconnect and credentialed account streams remain separate concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from .event_store import EventStore
from .types import AvailabilityKind, AvailabilityRecord, RawCapture, Side, utc_now


class SchemaError(ValueError):
    pass


def _timestamp_ms(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise SchemaError("invalid exchange timestamp") from exc


def _required(payload: Dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise SchemaError("missing required field %s" % key)
    return payload[key]


class BinanceUsdmNormalizer:
    """Maps official public payloads to venue-neutral, auditable measurements."""

    schema_version = "binance-usdm-public-v1"

    def normalize(self, stream: str, payload: Dict[str, Any], instrument: Optional[str] = None) -> Dict[str, Any]:
        event_type = payload.get("e", stream)
        if event_type == "aggTrade":
            maker_is_buyer = bool(_required(payload, "m"))
            return {
                "kind": "trade",
                "price": str(_required(payload, "p")),
                "quantity": str(_required(payload, "q")),
                "side": Side.SELL.value if maker_is_buyer else Side.BUY.value,
                "exchange_trade_id": payload.get("a"),
                "exchange_event_time": _timestamp_ms(_required(payload, "E")).isoformat(),
                "aggregated": True,
            }
        if event_type == "depthUpdate":
            return {
                "kind": "delta",
                "U": int(_required(payload, "U")),
                "u": int(_required(payload, "u")),
                "pu": int(payload["pu"]) if payload.get("pu") is not None else None,
                "bids": _required(payload, "b"),
                "asks": _required(payload, "a"),
                "exchange_event_time": _timestamp_ms(_required(payload, "E")).isoformat(),
                "rpi_included": False,
            }
        if event_type == "forceOrder":
            order = _required(payload, "o")
            exchange_side = str(_required(order, "S")).upper()
            if exchange_side not in (Side.BUY.value, Side.SELL.value):
                raise SchemaError("unknown forceOrder side")
            return {
                "kind": "liquidation",
                "price": str(_required(order, "ap")),
                "quantity": str(_required(order, "q")),
                "side": exchange_side,
                "censored": True,
                "coverage": "OBSERVED_CENSORED",
                "exchange_event_time": _timestamp_ms(_required(payload, "E")).isoformat(),
                "exchange_order_type": order.get("o"),
            }
        if event_type == "markPriceUpdate":
            normalized = {
                "kind": "mark_price",
                "mark_price": str(_required(payload, "p")),
                "index_price": str(_required(payload, "i")),
                "funding_rate": str(payload.get("r", "0")),
                "next_funding_time": payload.get("T"),
                "exchange_event_time": _timestamp_ms(_required(payload, "E")).isoformat(),
            }
            return normalized
        if stream == "openInterest":
            return {
                "kind": "oi",
                "value": str(_required(payload, "openInterest")),
                "exchange_event_time": _timestamp_ms(_required(payload, "time")).isoformat(),
            }
        if stream == "snapshot":
            return {
                "kind": "snapshot",
                "last_update_id": int(_required(payload, "lastUpdateId")),
                "bids": _required(payload, "bids"),
                "asks": _required(payload, "asks"),
                "rpi_included": False,
            }
        if stream == "exchangeInfo":
            symbols = _required(payload, "symbols")
            if not isinstance(symbols, list):
                raise SchemaError("exchangeInfo symbols must be a list")
            target = next((item for item in symbols if isinstance(item, dict) and item.get("symbol") == instrument), None)
            if target is None:
                raise SchemaError("exchangeInfo does not contain requested instrument")
            filters = _required(target, "filters")
            if not isinstance(filters, list):
                raise SchemaError("exchangeInfo filters must be a list")
            return {
                "kind": "exchange_info",
                "symbol": str(_required(target, "symbol")),
                "status": str(_required(target, "status")),
                "contract_type": target.get("contractType"),
                "base_asset": target.get("baseAsset"),
                "quote_asset": target.get("quoteAsset"),
                "filters": filters,
                "server_time": _timestamp_ms(_required(payload, "serverTime")).isoformat(),
            }
        raise SchemaError("unsupported Binance public stream %s" % stream)


@dataclass(frozen=True)
class CaptureResult:
    raw: RawCapture
    availability_written: bool
    parse_error: Optional[str] = None
    availability: Optional[AvailabilityRecord] = None


class BinanceCaptureSession:
    """Capture raw first, then append ACTUAL availability when parsing succeeds."""

    def __init__(self, store: EventStore, connection_id: str, instrument: str = "BTCUSDT") -> None:
        self.store = store
        self.connection_id = connection_id
        self.instrument = instrument
        self.normalizer = BinanceUsdmNormalizer()
        self._ingest_seq = 0

    @property
    def ingest_count(self) -> int:
        return self._ingest_seq

    def rotate_connection(self, connection_id: str) -> None:
        """Start a new physical-source connection with a fresh local sequence.

        A reconnect is evidence of a coverage boundary.  Reusing the old
        connection ID would make that boundary invisible in append-only raw
        records, so callers must provide a distinct identifier.
        """
        if not connection_id or connection_id == self.connection_id:
            raise ValueError("rotated connection_id must be non-empty and distinct")
        self.connection_id = connection_id
        self._ingest_seq = 0

    def ingest(self, stream: str, payload: Dict[str, Any], received_at: Optional[datetime] = None) -> CaptureResult:
        self._ingest_seq += 1
        received = received_at or utc_now()
        exchange_time = None
        source_time = payload.get("E", payload.get("time", payload.get("serverTime")))
        if source_time is not None:
            try:
                exchange_time = _timestamp_ms(source_time)
            except SchemaError:
                # Invalid source time must not prevent raw preservation.
                exchange_time = None
        raw = self.store.append_raw(
            source="BINANCE_USDM",
            venue="BINANCE_USDM",
            instrument=self.instrument,
            stream=stream,
            connection_id=self.connection_id,
            ingest_seq=self._ingest_seq,
            payload=payload,
            receive_time=received,
            exchange_event_time=exchange_time,
        )
        try:
            normalized = self.normalizer.normalize(stream, payload, self.instrument)
        except SchemaError as exc:
            return CaptureResult(raw=raw, availability_written=False, parse_error=str(exc))
        derived = utc_now()
        flags = ["censored"] if normalized.get("censored") else []
        availability = AvailabilityRecord(
            event_id=raw.event_id,
            schema_version=self.normalizer.schema_version,
            derived_at=derived,
            available_at=derived,
            availability_kind=AvailabilityKind.ACTUAL,
            quality_flags=flags,
            sequence_start=normalized.get("U"),
            sequence_end=normalized.get("u"),
            normalized=normalized,
        )
        self.store.append_availability(raw, availability)
        return CaptureResult(raw=raw, availability_written=True, availability=availability)
