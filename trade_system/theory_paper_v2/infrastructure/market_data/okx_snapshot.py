"""Strict raw-bound OKX ``BASELINE_PRICE`` market-data adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping

from ...application.market_cycle.ports import (
    MarketCaptureRequest,
    MarketDataObservation,
)
from ...domain.contracts.canonical import canonical_decimal, loads_json_strict
from .okx_transport import (
    CLOSED_CANDLES_15M_PATH,
    CapturedPublicResponse,
    INSTRUMENT_PATH,
    MARK_PRICE_PATH,
    OkxPublicTransport,
    SERVER_TIME_PATH,
)


BASELINE_PRICE_PROFILE = "BASELINE_PRICE"
OKX_VENUE_ID = "OKX"
OKX_SWAP_CONTRACT_TYPE = "SWAP"
BAR_INTERVAL_MILLISECONDS = 900_000
BASELINE_CANDLE_LIMIT = 96
MIN_BASELINE_CANDLES = 20
MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS = 5_000
MAX_REALTIME_STALENESS_MILLISECONDS = 120_000
MAX_CLOSED_BAR_AGE_MILLISECONDS = 1_800_000
PARSER_VERSION = "okx-baseline-price-v1"
_SAFE_CYCLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_UNSIGNED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


class OkxSnapshotError(ValueError):
    """A captured core response failed deterministic admission."""


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OkxSnapshotError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OkxSnapshotError(code) from exc
    if parsed.tzinfo is None:
        raise OkxSnapshotError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _epoch_milliseconds(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return (value.astimezone(UTC) - epoch) // timedelta(milliseconds=1)


def _provider_milliseconds(value: object, *, code: str) -> int:
    if (
        not isinstance(value, str)
        or len(value) != 13
        or not value.isascii()
        or not value.isdigit()
    ):
        raise OkxSnapshotError(code)
    milliseconds = int(value)
    if milliseconds <= 0:
        raise OkxSnapshotError(code)
    try:
        datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    except (OSError, OverflowError, ValueError) as exc:
        raise OkxSnapshotError(code) from exc
    return milliseconds


def _milliseconds_text(milliseconds: int) -> str:
    seconds, remainder = divmod(milliseconds, 1000)
    return _time_text(
        datetime.fromtimestamp(seconds, tz=UTC)
        + timedelta(milliseconds=remainder)
    )


def _decimal(
    value: object,
    *,
    code: str,
    positive: bool = False,
    nonnegative: bool = False,
) -> str:
    if not isinstance(value, str) or _UNSIGNED_DECIMAL.fullmatch(value) is None:
        raise OkxSnapshotError(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OkxSnapshotError(code) from exc
    if (
        not parsed.is_finite()
        or positive and parsed <= 0
        or nonnegative and parsed < 0
    ):
        raise OkxSnapshotError(code)
    return canonical_decimal(parsed)


def _okx_rows(raw: bytes, *, code: str) -> list[Any]:
    try:
        root = loads_json_strict(raw)
    except ValueError as exc:
        raise OkxSnapshotError(code) from exc
    if (
        not isinstance(root, Mapping)
        or set(root) not in ({"code", "data"}, {"code", "msg", "data"})
    ):
        raise OkxSnapshotError(code)
    if (
        root.get("code") != "0"
        or "msg" in root and root.get("msg") != ""
        or not isinstance(root.get("data"), list)
    ):
        raise OkxSnapshotError(code)
    return list(root["data"])


def _instrument_parts(instrument_id: object) -> tuple[str, str]:
    if not isinstance(instrument_id, str) or len(instrument_id) > 64:
        raise OkxSnapshotError("OKX_INSTRUMENT_ID_INVALID")
    parts = instrument_id.split("-")
    if (
        len(parts) != 3
        or parts[2] != "SWAP"
        or any(
            not part
            or not part.isascii()
            or not part.isalnum()
            or part.upper() != part
            for part in parts
        )
    ):
        raise OkxSnapshotError("OKX_INSTRUMENT_ID_INVALID")
    return parts[0], parts[1]


def validate_okx_swap_instrument(instrument_id: object) -> tuple[str, str]:
    """Return base/quote only for one canonical public OKX SWAP id."""

    return _instrument_parts(instrument_id)


def _provider_time(
    value: object,
    *,
    available_at: str,
    code: str,
    max_staleness_milliseconds: int,
) -> dict[str, Any]:
    provider_ms = _provider_milliseconds(value, code=code)
    available = _moment(available_at, code=code)
    available_ms = _epoch_milliseconds(available)
    ahead_ms = max(0, provider_ms - available_ms)
    if ahead_ms > MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS:
        raise OkxSnapshotError(f"{code}:FUTURE_DATUM")
    observed_ms = min(provider_ms, available_ms)
    freshness_ms = available_ms - observed_ms
    if freshness_ms > max_staleness_milliseconds:
        raise OkxSnapshotError(f"{code}:STALE_DATUM")
    return {
        "provider_as_of": _milliseconds_text(provider_ms),
        "observed_at": _milliseconds_text(observed_ms),
        "provider_clock_ahead_milliseconds": ahead_ms,
        "freshness_milliseconds": freshness_ms,
    }


def parse_okx_mark_response(
    *,
    raw: bytes,
    instrument_id: str,
    available_at: str,
) -> dict[str, Any]:
    """Parse one exact public mark datum from already sealed raw bytes."""

    _instrument_parts(instrument_id)
    rows = _okx_rows(raw, code="OKX_MARK_RESPONSE_INVALID")
    if not rows:
        return {"status": "MISSING", "missing_reason": "PUBLIC_DATA_EMPTY"}
    if len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise OkxSnapshotError("OKX_MARK_RESPONSE_AMBIGUOUS")
    row = rows[0]
    allowed = {"instId", "markPx", "ts"}
    if "instType" in row:
        allowed.add("instType")
    if set(row) != allowed:
        raise OkxSnapshotError("OKX_MARK_DATUM_SCHEMA_INVALID")
    if row.get("instId") != instrument_id:
        raise OkxSnapshotError("OKX_MARK_INSTRUMENT_MISMATCH")
    if "instType" in row and row.get("instType") != "SWAP":
        raise OkxSnapshotError("OKX_MARK_CONTRACT_TYPE_MISMATCH")
    timing = _provider_time(
        row.get("ts"),
        available_at=available_at,
        code="OKX_MARK_PROVIDER_TIME_INVALID",
        max_staleness_milliseconds=MAX_REALTIME_STALENESS_MILLISECONDS,
    )
    return {
        "status": "OBSERVED",
        "value": _decimal(
            row.get("markPx"), code="OKX_MARK_VALUE_INVALID", positive=True
        ),
        **timing,
    }


def _parse_server_time(response: CapturedPublicResponse) -> dict[str, Any]:
    rows = _okx_rows(response.body, code="OKX_SERVER_TIME_RESPONSE_INVALID")
    if (
        len(rows) != 1
        or not isinstance(rows[0], Mapping)
        or set(rows[0]) != {"ts"}
    ):
        raise OkxSnapshotError("OKX_SERVER_TIME_RESPONSE_INVALID")
    timing = _provider_time(
        rows[0].get("ts"),
        available_at=response.response_received_at,
        code="OKX_SERVER_TIME_INVALID",
        max_staleness_milliseconds=MAX_REALTIME_STALENESS_MILLISECONDS,
    )
    return {
        "value": str(
            _provider_milliseconds(
                rows[0].get("ts"), code="OKX_SERVER_TIME_INVALID"
            )
        ),
        "unit": "UNIX_MS",
        **timing,
    }


def _parse_instrument(
    response: CapturedPublicResponse, *, instrument_id: str
) -> dict[str, Any]:
    base, quote = _instrument_parts(instrument_id)
    rows = _okx_rows(response.body, code="OKX_INSTRUMENT_RESPONSE_INVALID")
    if len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise OkxSnapshotError("OKX_INSTRUMENT_RESPONSE_AMBIGUOUS")
    row = rows[0]
    required = {
        "instType",
        "instId",
        "state",
        "ctType",
        "ctValCcy",
        "settleCcy",
        "ctVal",
        "ctMult",
        "lotSz",
        "minSz",
        "tickSz",
    }
    if not required.issubset(row):
        raise OkxSnapshotError("OKX_INSTRUMENT_SCHEMA_INVALID")
    contract_family = row.get("ctType")
    identity_valid = (
        row.get("instType") == "SWAP"
        and row.get("instId") == instrument_id
        and row.get("state") == "live"
        and contract_family in {"linear", "inverse"}
        and (
            contract_family == "linear"
            and row.get("ctValCcy") == base
            and row.get("settleCcy") == quote
            or contract_family == "inverse"
            and row.get("ctValCcy") == quote
            and row.get("settleCcy") == base
        )
    )
    if not identity_valid:
        raise OkxSnapshotError("OKX_INSTRUMENT_IDENTITY_INVALID")
    return {
        "instrument_id": instrument_id,
        "instrument_type": "SWAP",
        "contract_family": contract_family,
        "base_currency": base,
        "quote_currency": quote,
        "contract_value_currency": row["ctValCcy"],
        "settlement_currency": row["settleCcy"],
        "contract_value": _decimal(
            row.get("ctVal"), code="OKX_INSTRUMENT_DECIMAL_INVALID", positive=True
        ),
        "contract_multiplier": _decimal(
            row.get("ctMult"), code="OKX_INSTRUMENT_DECIMAL_INVALID", positive=True
        ),
        "quantity_step": _decimal(
            row.get("lotSz"), code="OKX_INSTRUMENT_DECIMAL_INVALID", positive=True
        ),
        "minimum_quantity": _decimal(
            row.get("minSz"), code="OKX_INSTRUMENT_DECIMAL_INVALID", positive=True
        ),
        "price_tick": _decimal(
            row.get("tickSz"), code="OKX_INSTRUMENT_DECIMAL_INVALID", positive=True
        ),
        "observed_at": response.response_received_at,
    }


def _parse_closed_candles(
    response: CapturedPublicResponse,
    *,
    cutoff_ms: int,
    include_volume: bool = False,
) -> dict[str, Any]:
    rows = _okx_rows(response.body, code="OKX_CLOSED_CANDLES_RESPONSE_INVALID")
    if not MIN_BASELINE_CANDLES <= len(rows) <= BASELINE_CANDLE_LIMIT:
        raise OkxSnapshotError("OKX_CLOSED_CANDLES_COVERAGE_INVALID")
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) != 9
            or any(not isinstance(item, str) for item in row)
            or row[8] != "1"
        ):
            raise OkxSnapshotError("OKX_CLOSED_CANDLE_SCHEMA_INVALID")
        opened_ms = _provider_milliseconds(
            row[0], code="OKX_CLOSED_CANDLE_TIME_INVALID"
        )
        opened = _decimal(
            row[1], code="OKX_CLOSED_CANDLE_DECIMAL_INVALID", positive=True
        )
        high = _decimal(
            row[2], code="OKX_CLOSED_CANDLE_DECIMAL_INVALID", positive=True
        )
        low = _decimal(
            row[3], code="OKX_CLOSED_CANDLE_DECIMAL_INVALID", positive=True
        )
        close = _decimal(
            row[4], code="OKX_CLOSED_CANDLE_DECIMAL_INVALID", positive=True
        )
        volume_contracts = _decimal(
            row[5], code="OKX_CLOSED_CANDLE_DECIMAL_INVALID", nonnegative=True
        )
        volume_base = _decimal(
            row[6], code="OKX_CLOSED_CANDLE_DECIMAL_INVALID", nonnegative=True
        )
        volume_quote = _decimal(
            row[7], code="OKX_CLOSED_CANDLE_DECIMAL_INVALID", nonnegative=True
        )
        if (
            opened_ms % BAR_INTERVAL_MILLISECONDS != 0
            or opened_ms + BAR_INTERVAL_MILLISECONDS > cutoff_ms
            or Decimal(high) < Decimal(low)
            or Decimal(high) < max(Decimal(opened), Decimal(close))
            or Decimal(low) > min(Decimal(opened), Decimal(close))
        ):
            raise OkxSnapshotError("OKX_CLOSED_CANDLE_GEOMETRY_INVALID")
        item = {
                "opened_at": _milliseconds_text(opened_ms),
                "closed_at": _milliseconds_text(
                    opened_ms + BAR_INTERVAL_MILLISECONDS
                ),
                "open": opened,
                "high": high,
                "low": low,
                "close": close,
                "confirmed_closed": True,
                "_opened_ms": opened_ms,
        }
        if include_volume:
            item.update(
                {
                    "volume_contracts": volume_contracts,
                    "volume_base": volume_base,
                    "volume_quote": volume_quote,
                }
            )
        parsed.append(item)
    parsed.sort(key=lambda item: item["_opened_ms"])
    opened_values = [int(item["_opened_ms"]) for item in parsed]
    latest_boundary = (
        cutoff_ms // BAR_INTERVAL_MILLISECONDS
    ) * BAR_INTERVAL_MILLISECONDS
    if (
        len(set(opened_values)) != len(opened_values)
        or any(
            current - previous != BAR_INTERVAL_MILLISECONDS
            for previous, current in zip(opened_values, opened_values[1:])
        )
        or opened_values[-1] + BAR_INTERVAL_MILLISECONDS != latest_boundary
    ):
        raise OkxSnapshotError("OKX_CLOSED_CANDLES_COVERAGE_INVALID")
    public_rows = [
        {key: value for key, value in item.items() if key != "_opened_ms"}
        for item in parsed
    ]
    return {
        "bar": "15m",
        "interval_milliseconds": BAR_INTERVAL_MILLISECONDS,
        "count": len(public_rows),
        "latest_closed_at": _milliseconds_text(latest_boundary),
        "rows": public_rows,
    }


def parse_okx_closed_candles_response(
    response: CapturedPublicResponse,
    *,
    cutoff_at: str,
    include_volume: bool = False,
) -> dict[str, Any]:
    """Parse one sealed OKX 15m history response at a frozen PIT cutoff."""

    cutoff_ms = _epoch_milliseconds(
        _moment(cutoff_at, code="OKX_CLOSED_CANDLE_TIME_INVALID")
    )
    return _parse_closed_candles(
        response,
        cutoff_ms=cutoff_ms,
        include_volume=include_volume,
    )


def _source_health(response: CapturedPublicResponse) -> dict[str, Any]:
    return {
        "component_id": response.component_id,
        "status": "OBSERVED",
        "requested_at": response.request_started_at,
        "responded_at": response.response_received_at,
        "available_at": response.capture_completed_at,
        "http_status": response.http_status,
        "raw_ref": dict(response.raw_ref),
        "parser_version": PARSER_VERSION,
        "attempt_number": 1,
        "retry_allowed": False,
        "account_data_accessed": False,
        "credential_used": False,
        "executable": False,
    }


class OkxBaselineMarketData:
    """Implement ``MarketDataPort`` with exactly the four CORE_4 requests."""

    def __init__(
        self, *, transport: OkxPublicTransport, include_candle_volume: bool = False
    ) -> None:
        if type(include_candle_volume) is not bool:
            raise OkxSnapshotError("OKX_CANDLE_VOLUME_MODE_INVALID")
        self._transport = transport
        self._include_candle_volume = include_candle_volume

    @staticmethod
    def _validate_request(request: MarketCaptureRequest) -> str | None:
        if not isinstance(request, MarketCaptureRequest):
            raise OkxSnapshotError("MARKET_CAPTURE_REQUEST_INVALID")
        if (
            not isinstance(request.cycle_id, str)
            or _SAFE_CYCLE_ID.fullmatch(request.cycle_id) is None
        ):
            raise OkxSnapshotError("MARKET_CAPTURE_CYCLE_ID_INVALID")
        if (
            request.venue_id != OKX_VENUE_ID
            or request.data_profile != BASELINE_PRICE_PROFILE
        ):
            raise OkxSnapshotError("MARKET_CAPTURE_SCOPE_INVALID")
        _instrument_parts(request.instrument_id)
        _moment(request.requested_at, code="MARKET_CAPTURE_REQUEST_TIME_INVALID")
        if not isinstance(request.contract_type, str):
            raise OkxSnapshotError("MARKET_CAPTURE_CONTRACT_IDENTITY_INVALID")
        if request.contract_type == OKX_SWAP_CONTRACT_TYPE:
            return None
        identity = request.contract_type.split(":")
        if (
            len(identity) != 3
            or identity[0] != OKX_VENUE_ID
            or identity[1] != request.instrument_id
            or identity[2] not in {"SWAP", "linear", "inverse"}
        ):
            raise OkxSnapshotError("MARKET_CAPTURE_CONTRACT_IDENTITY_INVALID")
        return None if identity[2] == "SWAP" else identity[2]

    def capture(self, request: MarketCaptureRequest) -> MarketDataObservation:
        expected_contract_family = self._validate_request(request)
        responses: list[CapturedPublicResponse] = []

        server = self._transport.get_once(
            cycle_id=request.cycle_id,
            capture_id="server-time",
            component_id="SERVER_TIME",
            path=SERVER_TIME_PATH,
            query={},
        )
        responses.append(server)
        server_time = _parse_server_time(server)
        cutoff_ms = _epoch_milliseconds(
            _moment(server_time["observed_at"], code="OKX_SERVER_TIME_INVALID")
        )

        instrument_response = self._transport.get_once(
            cycle_id=request.cycle_id,
            capture_id="instrument",
            component_id="INSTRUMENT",
            path=INSTRUMENT_PATH,
            query={"instId": request.instrument_id, "instType": "SWAP"},
        )
        responses.append(instrument_response)
        instrument = _parse_instrument(
            instrument_response, instrument_id=request.instrument_id
        )
        if (
            expected_contract_family is not None
            and instrument["contract_family"] != expected_contract_family
        ):
            raise OkxSnapshotError("OKX_INSTRUMENT_CONTRACT_IDENTITY_MISMATCH")

        mark_response = self._transport.get_once(
            cycle_id=request.cycle_id,
            capture_id="mark-price",
            component_id="MARK_PRICE",
            path=MARK_PRICE_PATH,
            query={"instId": request.instrument_id, "instType": "SWAP"},
        )
        responses.append(mark_response)
        mark = parse_okx_mark_response(
            raw=mark_response.body,
            instrument_id=request.instrument_id,
            available_at=mark_response.response_received_at,
        )
        if mark.get("status") != "OBSERVED":
            raise OkxSnapshotError("OKX_MARK_REQUIRED_DATA_MISSING")

        candles_response = self._transport.get_once(
            cycle_id=request.cycle_id,
            capture_id="closed-candles-15m",
            component_id="CLOSED_CANDLES_15M",
            path=CLOSED_CANDLES_15M_PATH,
            query={
                "after": str(
                    (cutoff_ms // BAR_INTERVAL_MILLISECONDS)
                    * BAR_INTERVAL_MILLISECONDS
                ),
                "bar": "15m",
                "instId": request.instrument_id,
                "limit": str(BASELINE_CANDLE_LIMIT),
            },
        )
        responses.append(candles_response)
        candles = _parse_closed_candles(
            candles_response,
            cutoff_ms=cutoff_ms,
            include_volume=self._include_candle_volume,
        )

        requested = _moment(
            request.requested_at, code="MARKET_CAPTURE_REQUEST_TIME_INVALID"
        )
        previous = requested
        for response in responses:
            started = _moment(
                response.request_started_at, code="MARKET_CAPTURE_CHRONOLOGY_INVALID"
            )
            completed = _moment(
                response.capture_completed_at,
                code="MARKET_CAPTURE_CHRONOLOGY_INVALID",
            )
            if previous > started or started > completed:
                raise OkxSnapshotError("MARKET_CAPTURE_CHRONOLOGY_INVALID")
            previous = completed

        captured_at = responses[-1].capture_completed_at
        captured_ms = _epoch_milliseconds(
            _moment(captured_at, code="MARKET_CAPTURE_TIME_INVALID")
        )
        mark_observed_ms = _epoch_milliseconds(
            _moment(mark["observed_at"], code="OKX_MARK_PROVIDER_TIME_INVALID")
        )
        latest_closed_ms = _epoch_milliseconds(
            _moment(
                candles["latest_closed_at"],
                code="OKX_CLOSED_CANDLE_TIME_INVALID",
            )
        )
        if (
            captured_ms - cutoff_ms > MAX_REALTIME_STALENESS_MILLISECONDS
            or captured_ms - mark_observed_ms
            > MAX_REALTIME_STALENESS_MILLISECONDS
            or captured_ms - latest_closed_ms > MAX_CLOSED_BAR_AGE_MILLISECONDS
        ):
            raise OkxSnapshotError("MARKET_CAPTURE_CORE_DATA_STALE")
        base, quote = _instrument_parts(request.instrument_id)
        core = {
            "server_time": {
                **server_time,
                "available_at": server.capture_completed_at,
                "raw_sha256": server.raw_ref["sha256"],
            },
            "instrument": {
                "value": instrument,
                "available_at": instrument_response.capture_completed_at,
                "raw_sha256": instrument_response.raw_ref["sha256"],
            },
            "mark_price": {
                "value": mark["value"],
                "unit": f"{quote}_PER_{base}",
                "price_field": "MARK_PRICE",
                "provider_as_of": mark["provider_as_of"],
                "observed_at": mark["observed_at"],
                "provider_clock_ahead_milliseconds": mark[
                    "provider_clock_ahead_milliseconds"
                ],
                "freshness_milliseconds": mark["freshness_milliseconds"],
                "available_at": mark_response.capture_completed_at,
                "raw_sha256": mark_response.raw_ref["sha256"],
            },
            "closed_15m_bars": {
                "value": candles["rows"],
                "bar": candles["bar"],
                "interval_milliseconds": candles["interval_milliseconds"],
                "count": candles["count"],
                "last_closed_at": candles["latest_closed_at"],
                "available_at": candles_response.capture_completed_at,
                "raw_sha256": candles_response.raw_ref["sha256"],
            },
        }
        unknowns = tuple(
            {
                "code": f"{component_id}_NOT_REQUESTED_BY_BASELINE_PRICE",
                "component_id": component_id,
                "status": "UNKNOWN",
                "missing_reason": "NOT_REQUESTED_BY_BASELINE_PRICE",
                "missing_is_zero": False,
            }
            for component_id in (
                "MULTI_TIMEFRAME",
                "DERIVATIVES",
                "MICROSTRUCTURE",
                "CONTEXT_EVENT",
            )
        )
        return MarketDataObservation(
            captured_at=captured_at,
            cutoff_at=captured_at,
            core_observations=core,
            optional_observations={},
            unknowns=unknowns,
            raw_refs=tuple(dict(response.raw_ref) for response in responses),
            source_health=tuple(_source_health(response) for response in responses),
        )


OkxBaselineMarketDataAdapter = OkxBaselineMarketData


__all__ = [
    "BAR_INTERVAL_MILLISECONDS",
    "BASELINE_CANDLE_LIMIT",
    "BASELINE_PRICE_PROFILE",
    "MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS",
    "MAX_CLOSED_BAR_AGE_MILLISECONDS",
    "MAX_REALTIME_STALENESS_MILLISECONDS",
    "MIN_BASELINE_CANDLES",
    "parse_okx_closed_candles_response",
    "OKX_SWAP_CONTRACT_TYPE",
    "OKX_VENUE_ID",
    "OkxBaselineMarketData",
    "OkxBaselineMarketDataAdapter",
    "OkxSnapshotError",
    "PARSER_VERSION",
    "parse_okx_mark_response",
    "validate_okx_swap_instrument",
]
