"""Compose four bounded OKX public observations around the unchanged core."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping

from ...application.market_cycle.ports import (
    MarketCaptureRequest,
    MarketDataObservation,
    MarketDataPort,
)
from .okx_derivatives import (
    PARSER_VERSION as DERIVATIVES_PARSER_VERSION,
    OkxDerivativesError,
    OkxDerivativesIntegrityError,
    parse_okx_funding_rate_history,
    parse_okx_open_interest,
)
from .okx_microstructure import (
    PARSER_VERSION as MICROSTRUCTURE_PARSER_VERSION,
    OkxMicrostructureError,
    OkxMicrostructureIntegrityError,
    parse_okx_order_book,
    parse_okx_recent_trades,
)
from .okx_snapshot import BASELINE_PRICE_PROFILE
from .okx_transport import (
    FUNDING_RATE_HISTORY_PATH,
    OPEN_INTEREST_PATH,
    ORDER_BOOK_PATH,
    RECENT_TRADES_PATH,
    CapturedPublicResponse,
    OkxPublicTransport,
    OkxPublicTransportError,
)


OKX_PUBLIC_OPTIONAL_PROFILE = "BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1"

_OPTIONAL_TRANSPORT_UNKNOWN_CODES = frozenset(
    {
        "PUBLIC_TIMEOUT",
        "PUBLIC_DNS_UNAVAILABLE",
        "PUBLIC_TLS_FAILURE",
        "PUBLIC_CONNECTION_FAILURE",
        "PUBLIC_TRANSPORT_IO_FAILURE",
        "PUBLIC_PROVIDER_UNAVAILABLE",
        "PUBLIC_REDIRECT_FORBIDDEN",
        "PUBLIC_RESPONSE_TOO_LARGE",
        "PUBLIC_HTTP_STATUS_INVALID",
        "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE",
        "PUBLIC_RESPONSE_EMPTY",
        "PUBLIC_RESPONSE_BODY_READ_FAILED",
        "PUBLIC_RESPONSE_STRUCTURAL_FAILURE",
        "PUBLIC_PREVIOUS_ATTEMPT_INDETERMINATE",
    }
)


class OkxOptionalContextError(ValueError):
    """The optional context composition violates identity or time integrity."""


@dataclass(frozen=True, slots=True)
class _OptionalSpec:
    observation_name: str
    capture_id: str
    component_id: str
    path: str
    query: Callable[[str], Mapping[str, str]]
    parser: Callable[..., object]
    parser_version: str


_SPECS = (
    _OptionalSpec(
        observation_name="okx_order_book",
        capture_id="order-book",
        component_id="ORDER_BOOK",
        path=ORDER_BOOK_PATH,
        query=lambda instrument_id: {"instId": instrument_id, "sz": "20"},
        parser=parse_okx_order_book,
        parser_version=MICROSTRUCTURE_PARSER_VERSION,
    ),
    _OptionalSpec(
        observation_name="okx_recent_trades",
        capture_id="recent-trades",
        component_id="RECENT_TRADES",
        path=RECENT_TRADES_PATH,
        query=lambda instrument_id: {"instId": instrument_id, "limit": "100"},
        parser=parse_okx_recent_trades,
        parser_version=MICROSTRUCTURE_PARSER_VERSION,
    ),
    _OptionalSpec(
        observation_name="okx_open_interest",
        capture_id="open-interest",
        component_id="OPEN_INTEREST",
        path=OPEN_INTEREST_PATH,
        query=lambda instrument_id: {"instId": instrument_id, "instType": "SWAP"},
        parser=parse_okx_open_interest,
        parser_version=DERIVATIVES_PARSER_VERSION,
    ),
    _OptionalSpec(
        observation_name="okx_funding_rate_history",
        capture_id="funding-rate-history",
        component_id="FUNDING_RATE_HISTORY",
        path=FUNDING_RATE_HISTORY_PATH,
        query=lambda instrument_id: {"instId": instrument_id, "limit": "10"},
        parser=parse_okx_funding_rate_history,
        parser_version=DERIVATIVES_PARSER_VERSION,
    ),
)

_DEFERRED_UNKNOWNS = (
    "OKX_ORDER_BOOK_STREAM",
    "OKX_LIQUIDATION_STREAM",
    "OKX_TAKER_VOLUME",
    "OKX_LONG_SHORT_RATIO",
)


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OkxOptionalContextError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OkxOptionalContextError(code) from exc
    if parsed.tzinfo is None:
        raise OkxOptionalContextError(code)
    return parsed.astimezone(UTC)


def _later(left: str, right: str) -> str:
    return right if _moment(right, code="OPTIONAL_CAPTURE_TIME_INVALID") > _moment(
        left, code="OPTIONAL_CAPTURE_TIME_INVALID"
    ) else left


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _epoch_milliseconds(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return (value - epoch) // timedelta(milliseconds=1)


def _optional_timing(
    value: object, *, response_received_at: str
) -> dict[str, object]:
    """Separate a provider event time from the local knowledge timestamp."""

    provider_values: list[object]
    if isinstance(value, Mapping):
        provider_values = [value.get("provider_as_of")]
    elif isinstance(value, (list, tuple)) and value:
        provider_values = [
            item.get("provider_as_of") if isinstance(item, Mapping) else None
            for item in value
        ]
    else:
        raise OkxOptionalContextError("OPTIONAL_PROVIDER_TIME_INVALID")
    provider_times = [
        _moment(item, code="OPTIONAL_PROVIDER_TIME_INVALID")
        for item in provider_values
    ]
    latest_provider = max(provider_times)
    received = _moment(
        response_received_at, code="OPTIONAL_RESPONSE_TIME_INVALID"
    )
    observed = min(latest_provider, received)
    ahead = max(
        0,
        _epoch_milliseconds(latest_provider)
        - _epoch_milliseconds(received),
    )
    return {
        "observed_at": _time_text(observed),
        "provider_clock_ahead_milliseconds": ahead,
    }


def _unknown(component_id: str, reason: str) -> dict[str, object]:
    return {
        "code": f"{component_id}:{reason}",
        "component_id": component_id,
        "status": "UNKNOWN",
        "missing_reason": reason,
        "missing_is_zero": False,
    }


def _observed_health(
    response: CapturedPublicResponse, *, parser_version: str
) -> dict[str, object]:
    return {
        "component_id": response.component_id,
        "status": "OBSERVED",
        "requested_at": response.request_started_at,
        "responded_at": response.response_received_at,
        "available_at": response.capture_completed_at,
        "http_status": response.http_status,
        "raw_ref": dict(response.raw_ref),
        "parser_version": parser_version,
        "attempt_number": 1,
        "retry_allowed": False,
        "account_data_accessed": False,
        "credential_used": False,
        "executable": False,
    }


def _unknown_health(
    component_id: str,
    reason: str,
    *,
    available_at: str | None,
    raw_ref: Mapping[str, Any] | None,
    response: CapturedPublicResponse | None = None,
) -> dict[str, object]:
    health: dict[str, object] = {
        "component_id": component_id,
        "status": "UNKNOWN",
        "missing_reason": reason,
        "missing_is_zero": False,
        "attempt_number": 1,
        "retry_allowed": False,
        "account_data_accessed": False,
        "credential_used": False,
        "executable": False,
    }
    if available_at is not None:
        health["available_at"] = available_at
    if raw_ref is not None:
        health["raw_ref"] = dict(raw_ref)
    if response is not None:
        health["requested_at"] = response.request_started_at
        health["responded_at"] = response.response_received_at
        health["http_status"] = response.http_status
    return health


def _transport_failure_is_optional(exc: OkxPublicTransportError) -> bool:
    return exc.failure_code in _OPTIONAL_TRANSPORT_UNKNOWN_CODES


class OkxOptionalContextMarketData:
    """Decorate CORE_4 with four independent credential-free REST observations."""

    def __init__(self, *, core: MarketDataPort, transport: OkxPublicTransport) -> None:
        if not callable(getattr(core, "capture", None)):
            raise OkxOptionalContextError("OPTIONAL_CORE_PORT_INVALID")
        if not callable(getattr(transport, "get_once", None)):
            raise OkxOptionalContextError("OPTIONAL_TRANSPORT_INVALID")
        self._core = core
        self._transport = transport

    def capture(self, request: MarketCaptureRequest) -> MarketDataObservation:
        if not isinstance(request, MarketCaptureRequest):
            raise OkxOptionalContextError("OPTIONAL_CAPTURE_REQUEST_INVALID")
        if request.data_profile == BASELINE_PRICE_PROFILE:
            return self._core.capture(request)
        if request.data_profile != OKX_PUBLIC_OPTIONAL_PROFILE or request.venue_id != "OKX":
            raise OkxOptionalContextError("OPTIONAL_CAPTURE_SCOPE_INVALID")

        core = self._core.capture(replace(request, data_profile=BASELINE_PRICE_PROFILE))
        optional: dict[str, object] = {}
        raw_refs = [dict(reference) for reference in core.raw_refs]
        health = [dict(item) for item in core.source_health]
        unknowns = [
            dict(item)
            for item in core.unknowns
            if item.get("component_id") not in {"DERIVATIVES", "MICROSTRUCTURE"}
        ]
        captured_at = core.captured_at

        for spec in _SPECS:
            response: CapturedPublicResponse | None = None
            try:
                response = self._transport.get_once(
                    cycle_id=request.cycle_id,
                    capture_id=spec.capture_id,
                    component_id=spec.component_id,
                    path=spec.path,
                    query=spec.query(request.instrument_id),
                )
            except OkxPublicTransportError as exc:
                if not _transport_failure_is_optional(exc):
                    raise
                if exc.failure_at is not None:
                    captured_at = _later(captured_at, exc.failure_at)
                if exc.raw_ref is not None:
                    raw_refs.append(dict(exc.raw_ref))
                unknowns.append(_unknown(spec.component_id, exc.failure_code))
                health.append(
                    _unknown_health(
                        spec.component_id,
                        exc.failure_code,
                        available_at=exc.failure_at,
                        raw_ref=exc.raw_ref,
                    )
                )
                continue

            if _moment(response.request_started_at, code="OPTIONAL_CHRONOLOGY_INVALID") < _moment(
                captured_at, code="OPTIONAL_CHRONOLOGY_INVALID"
            ) or _moment(response.capture_completed_at, code="OPTIONAL_CHRONOLOGY_INVALID") < _moment(
                response.request_started_at, code="OPTIONAL_CHRONOLOGY_INVALID"
            ):
                raise OkxOptionalContextError("OPTIONAL_CAPTURE_CHRONOLOGY_INVALID")
            captured_at = response.capture_completed_at
            raw_refs.append(dict(response.raw_ref))
            try:
                value = spec.parser(
                    raw=response.body,
                    instrument_id=request.instrument_id,
                    available_at=response.capture_completed_at,
                )
            except (OkxMicrostructureIntegrityError, OkxDerivativesIntegrityError):
                raise
            except (OkxMicrostructureError, OkxDerivativesError) as exc:
                reason = str(exc) or "OPTIONAL_PARSER_INVALID"
                unknowns.append(_unknown(spec.component_id, reason))
                health.append(
                    _unknown_health(
                        spec.component_id,
                        reason,
                        available_at=response.capture_completed_at,
                        raw_ref=response.raw_ref,
                        response=response,
                    )
                )
                continue

            optional[spec.observation_name] = {
                "value": value,
                **_optional_timing(
                    value,
                    response_received_at=response.response_received_at,
                ),
                "available_at": response.capture_completed_at,
                "raw_sha256": response.raw_ref["sha256"],
            }
            health.append(
                _observed_health(response, parser_version=spec.parser_version)
            )

        unknowns.extend(
            _unknown(component_id, "NOT_IMPLEMENTED_IN_OPTIONAL_V1")
            for component_id in _DEFERRED_UNKNOWNS
        )
        return MarketDataObservation(
            captured_at=captured_at,
            cutoff_at=captured_at,
            core_observations=dict(core.core_observations),
            optional_observations=optional,
            unknowns=tuple(unknowns),
            raw_refs=tuple(raw_refs),
            source_health=tuple(health),
        )


__all__ = [
    "OKX_PUBLIC_OPTIONAL_PROFILE",
    "OkxOptionalContextError",
    "OkxOptionalContextMarketData",
]
