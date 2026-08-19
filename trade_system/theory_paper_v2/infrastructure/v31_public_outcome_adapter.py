"""Production public-only OKX mark-price adapter for the V3.1 monitor.

The adapter exposes exactly one GET boundary and has no account, credential,
order, paper, live, or portfolio interface.  It returns the absolute public
mark price; monitor rules own any pre-registered price-level interpretation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from ..domain.contracts.canonical import loads_json_strict
from ..domain.v31_experiment_contracts import (
    ObservationMissingness,
    ObservationQuality,
)
from ..domain.v31_monitor_runtime import PublicOutcomeReading
from .fresh_market.binance_usdm import PublicHttpTransport
from .fresh_market.okx_public import OkxUrllibPublicHttpTransport


OKX_MARK_PRICE_URL = (
    "https://www.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)
ABSOLUTE_MARK_OBSERVABLE = "metric:mark-price-usdt"
_MAX_MARK_RESPONSE_BYTES = 1024 * 1024


class V31PublicOutcomeAdapterError(ValueError):
    """The sole public outcome observation could not be trusted."""


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31PublicOutcomeAdapterError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31PublicOutcomeAdapterError(code) from exc
    if parsed.tzinfo is None:
        raise V31PublicOutcomeAdapterError(code)
    return parsed.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _unknown_reading(
    *, raw: bytes, captured_at: datetime, requested_at: datetime, request_id: str
) -> PublicOutcomeReading:
    return PublicOutcomeReading(
        raw_payload=raw,
        source_locator=OKX_MARK_PRICE_URL,
        captured_at=_timestamp(captured_at),
        observable_ref=ABSOLUTE_MARK_OBSERVABLE,
        value=None,
        as_of=_timestamp(requested_at),
        available_at=_timestamp(captured_at),
        missingness=ObservationMissingness.UNKNOWN,
        quality=ObservationQuality.UNKNOWN,
        coverage="0",
        conflict_state="UNKNOWN",
        source_request_id=request_id,
    )


class OkxPublicMarkPriceOutcomeAdapter:
    """Perform one exact public mark-price GET for a due monitor plan."""

    def __init__(
        self,
        *,
        transport: PublicHttpTransport | None = None,
        clock: Callable[[], datetime] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._transport = transport or OkxUrllibPublicHttpTransport(
            clock=self._clock,
            max_response_bytes=_MAX_MARK_RESPONSE_BYTES,
        )
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_ADAPTER_TIMEOUT_INVALID"
            )
        if timeout <= 0 or timeout > 60:
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_ADAPTER_TIMEOUT_INVALID"
            )
        self._timeout = float(timeout)

    @staticmethod
    def _validate_plan(
        monitor_plan: Mapping[str, Any], *, requested_at: datetime
    ) -> str:
        if not isinstance(monitor_plan, Mapping):
            raise V31PublicOutcomeAdapterError("V31_OUTCOME_PLAN_INVALID")
        observable = monitor_plan.get("observable")
        if (
            not isinstance(observable, Mapping)
            or observable.get("observable_ref") != ABSOLUTE_MARK_OBSERVABLE
            or observable.get("venue") != "OKX"
            or observable.get("instrument_id") != "BTC-USDT-SWAP"
            or observable.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
            or observable.get("request_method") != "GET"
            or observable.get("source_endpoint")
            != "https://www.okx.com/api/v5/public/mark-price"
            or observable.get("source_parameters")
            != {"instType": "SWAP", "instId": "BTC-USDT-SWAP"}
            or not isinstance(observable.get("source_request_id"), str)
            or not observable["source_request_id"]
        ):
            raise V31PublicOutcomeAdapterError("V31_OUTCOME_PLAN_SCOPE_INVALID")
        not_before = _time(
            monitor_plan.get("outcome_not_before"),
            "V31_OUTCOME_PLAN_TIME_INVALID",
        )
        expires_at = _time(
            monitor_plan.get("expires_at"), "V31_OUTCOME_PLAN_TIME_INVALID"
        )
        if requested_at < not_before or requested_at > expires_at:
            raise V31PublicOutcomeAdapterError("V31_OUTCOME_REQUEST_NOT_DUE")
        boundary = monitor_plan.get("authority_boundary")
        if (
            not isinstance(boundary, Mapping)
            or boundary.get("data_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
            or boundary.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or boundary.get("executable") is not False
            or any(
                boundary.get(field) is not False
                for field in (
                    "account_access",
                    "paper_trading",
                    "live_trading",
                    "order_submission",
                    "credential_use",
                    "funds_access",
                    "portfolio_mutation",
                )
            )
        ):
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PLAN_AUTHORITY_INVALID"
            )
        return str(observable["source_request_id"])

    def observe_public_outcome(
        self, *, monitor_plan: Mapping[str, Any], requested_at: str
    ) -> PublicOutcomeReading:
        requested = _time(requested_at, "V31_OUTCOME_REQUEST_TIME_INVALID")
        request_id = self._validate_plan(
            monitor_plan, requested_at=requested
        )
        response = self._transport.get(OKX_MARK_PRICE_URL, self._timeout)
        captured = response.received_at.astimezone(UTC)
        if (
            response.final_url != OKX_MARK_PRICE_URL
            or response.status != 200
            or captured < requested
            or not isinstance(response.body, bytes)
            or not response.body
            or len(response.body) > _MAX_MARK_RESPONSE_BYTES
        ):
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_RESPONSE_INVALID"
            )
        content_type = next(
            (
                value
                for name, value in response.headers.items()
                if name.casefold() == "content-type"
            ),
            "",
        )
        if "json" not in content_type.casefold():
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_CONTENT_TYPE_INVALID"
            )
        try:
            decoded = loads_json_strict(response.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_JSON_INVALID"
            ) from exc
        if not isinstance(decoded, Mapping):
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_SCHEMA_INVALID"
            )
        data = decoded.get("data")
        if decoded.get("code") != "0" or not isinstance(data, list) or len(data) != 1:
            return _unknown_reading(
                raw=response.body,
                captured_at=captured,
                requested_at=requested,
                request_id=request_id,
            )
        row = data[0]
        if not isinstance(row, Mapping):
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_SCHEMA_INVALID"
            )
        if row.get("instId") != "BTC-USDT-SWAP" or row.get("instType") != "SWAP":
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_INSTRUMENT_MISMATCH"
            )
        mark = row.get("markPx")
        timestamp_ms = row.get("ts")
        if (
            not isinstance(mark, str)
            or not isinstance(timestamp_ms, str)
            or not timestamp_ms.isdigit()
        ):
            return _unknown_reading(
                raw=response.body,
                captured_at=captured,
                requested_at=requested,
                request_id=request_id,
            )
        try:
            mark_value = Decimal(mark)
            milliseconds = int(timestamp_ms)
            as_of = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
                milliseconds=milliseconds
            )
        except (InvalidOperation, OverflowError, ValueError) as exc:
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_VALUE_INVALID"
            ) from exc
        if not mark_value.is_finite() or mark_value <= 0 or as_of > captured:
            raise V31PublicOutcomeAdapterError(
                "V31_OUTCOME_PUBLIC_VALUE_INVALID"
            )
        return PublicOutcomeReading(
            raw_payload=response.body,
            source_locator=OKX_MARK_PRICE_URL,
            captured_at=_timestamp(captured),
            observable_ref=ABSOLUTE_MARK_OBSERVABLE,
            value=mark,
            as_of=_timestamp(as_of),
            available_at=_timestamp(captured),
            missingness=ObservationMissingness.OBSERVED,
            quality=ObservationQuality.HIGH,
            coverage="1",
            conflict_state="NONE",
            source_request_id=request_id,
        )


__all__ = [
    "ABSOLUTE_MARK_OBSERVABLE",
    "OKX_MARK_PRICE_URL",
    "OkxPublicMarkPriceOutcomeAdapter",
    "V31PublicOutcomeAdapterError",
]
