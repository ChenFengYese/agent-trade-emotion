"""One-call public OKX adapter for the V3.2 shared outcome tick.

The adapter deliberately stops at durable transport capture.  It does not
parse a mark price, retry, follow an alternate venue, or expose any account,
credential, order, position, fill, or portfolio method.  Parsing happens only
after the returned bytes have been written by the V3.2 outcome-tick store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Mapping
import urllib.error

from ..domain.v32_outcome_tick import (
    V32PublicTransportUnavailableError,
    verify_v32_outcome_tick_attempt,
)
from ..domain.v32_qualification_monitor_probe import (
    ATTEMPT_SCHEMA_ID as QUALIFICATION_PROBE_ATTEMPT_SCHEMA_ID,
    verify_v32_qualification_monitor_probe_attempt_intrinsic_v1,
)
from .fresh_market.binance_usdm import HttpCapture, PublicHttpTransport
from .v32_public_https_route import (
    V32SystemPublicHttpsOpener,
    build_v32_public_get_request_v1,
    classify_v32_public_https_failure_v1,
)


OKX_V32_MARK_PRICE_URL = (
    "https://openapi.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)
MAX_V32_MARK_RESPONSE_BYTES = 1024 * 1024
_PHYSICAL_COVERAGE_FAILURES = frozenset(
    {
        "PUBLIC_CONNECTION_FAILURE",
        "PUBLIC_DNS_UNAVAILABLE",
        "PUBLIC_TIMEOUT",
        "PUBLIC_TLS_FAILURE",
        "PUBLIC_TRANSPORT_IO_FAILURE",
        "PUBLIC_PROVIDER_UNAVAILABLE",
    }
)


class V32OkxPublicOutcomeAdapterError(ValueError):
    """The sole V3.2 public mark capture boundary was invalid."""


class _V32OpenApiPublicHttpTransport:
    """Small V3.2-only transport for the official Global REST API host."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        max_response_bytes: int,
        opener: V32SystemPublicHttpsOpener,
    ) -> None:
        self._clock = clock
        self._max_response_bytes = max_response_bytes
        self._opener = opener

    def get(self, url: str, timeout: float) -> HttpCapture:
        if url != OKX_V32_MARK_PRICE_URL or timeout <= 0:
            raise V32OkxPublicOutcomeAdapterError(
                "V32_OKX_CAPTURE_TRANSPORT_CONTRACT_INVALID"
            )
        request = build_v32_public_get_request_v1(url)

        def capture(response: Any) -> HttpCapture:
            body = response.read(self._max_response_bytes + 1)
            if len(body) > self._max_response_bytes:
                raise V32OkxPublicOutcomeAdapterError(
                    "V32_OKX_CAPTURE_RESPONSE_BYTES_INVALID"
                )
            return HttpCapture(
                status=int(
                    response.status
                    if hasattr(response, "status")
                    else response.code
                ),
                headers={
                    key: value
                    for key, value in (
                        response.headers.items()
                        if response.headers is not None
                        else ()
                    )
                },
                body=body,
                received_at=self._clock(),
                final_url=response.geturl(),
            )

        try:
            with self._opener.open(request, timeout=timeout) as response:
                return capture(response)
        except urllib.error.HTTPError as exc:
            return capture(exc)


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32OkxPublicOutcomeAdapterError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32OkxPublicOutcomeAdapterError(code) from exc
    if parsed.tzinfo is None:
        raise V32OkxPublicOutcomeAdapterError(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V32OkxPublicOutcomeAdapterError(code)
    return normalized


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise V32OkxPublicOutcomeAdapterError("V32_OKX_CAPTURE_TIME_INVALID")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _transport_unavailable(
    suffix: str, exc: BaseException, *, failure_at: str
) -> V32PublicTransportUnavailableError:
    if suffix not in _PHYSICAL_COVERAGE_FAILURES:
        raise V32OkxPublicOutcomeAdapterError(
            f"V32_OKX_CAPTURE_ROUTE_OR_IDENTITY_INVALID:{suffix}"
        ) from None
    return V32PublicTransportUnavailableError(
        f"V32_OKX_PUBLIC_TRANSPORT_UNAVAILABLE:{suffix}",
        coverage_failure_code=suffix,
        failure_at=failure_at,
    )


class V32OkxPublicMarkCaptureAdapter:
    """Perform the one exact public GET authorized by a V3.2 tick attempt."""

    def __init__(
        self,
        *,
        transport: PublicHttpTransport | None = None,
        clock: Callable[[], datetime] | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= 60
        ):
            raise V32OkxPublicOutcomeAdapterError(
                "V32_OKX_CAPTURE_TIMEOUT_INVALID"
            )
        self._timeout = timeout_seconds
        self._transport = transport or _V32OpenApiPublicHttpTransport(
            clock=self._clock,
            max_response_bytes=MAX_V32_MARK_RESPONSE_BYTES,
            opener=V32SystemPublicHttpsOpener(),
        )

    def capture_public_mark(
        self, *, attempt: Mapping[str, Any], requested_at: str
    ) -> Mapping[str, Any]:
        """Return raw response bytes or a terminal no-response envelope."""

        qualification_probe = (
            attempt.get("schema_id") == QUALIFICATION_PROBE_ATTEMPT_SCHEMA_ID
        )
        try:
            if qualification_probe:
                verify_v32_qualification_monitor_probe_attempt_intrinsic_v1(attempt)
            else:
                verify_v32_outcome_tick_attempt(attempt)
        except (TypeError, ValueError) as exc:
            raise V32OkxPublicOutcomeAdapterError(
                "V32_OKX_CAPTURE_ATTEMPT_INVALID"
            ) from exc
        requested = _moment(requested_at, "V32_OKX_CAPTURE_TIME_INVALID")
        if qualification_probe:
            if not (
                _moment(str(attempt.get("reserved_at")), "V32_OKX_CAPTURE_TIME_INVALID")
                <= requested
                <= _moment(str(attempt.get("expires_at")), "V32_OKX_CAPTURE_TIME_INVALID")
            ):
                raise V32OkxPublicOutcomeAdapterError(
                    "V32_OKX_CAPTURE_ATTEMPT_TIME_MISMATCH"
                )
        elif attempt.get("reserved_at") != requested_at:
            raise V32OkxPublicOutcomeAdapterError(
                "V32_OKX_CAPTURE_ATTEMPT_TIME_MISMATCH"
            )
        request_id = str(attempt["source_request_id"])
        try:
            response = self._transport.get(
                OKX_V32_MARK_PRICE_URL, float(self._timeout)
            )
        except (TimeoutError, ConnectionError, OSError) as exc:
            # Only typed transport unavailability can become coverage loss.
            # Adapter/schema/identity defects remain structural and propagate.
            suffix = classify_v32_public_https_failure_v1(exc)
            failure_at = _timestamp(self._clock())
            raise _transport_unavailable(
                suffix, exc, failure_at=failure_at
            ) from None
        received = response.received_at.astimezone(UTC)
        received_at = _timestamp(received)
        captured_at = _timestamp(self._clock())
        if (
            isinstance(response.status, bool)
            or not isinstance(response.status, int)
            or not 100 <= response.status <= 599
        ):
            raise V32OkxPublicOutcomeAdapterError(
                "V32_OKX_CAPTURE_HTTP_STATUS_INVALID"
            )
        raw = response.body
        if (
            not isinstance(raw, bytes)
            or len(raw) > MAX_V32_MARK_RESPONSE_BYTES
        ):
            raise V32OkxPublicOutcomeAdapterError(
                "V32_OKX_CAPTURE_RESPONSE_BYTES_INVALID"
            )
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "source_request_id": request_id,
            "received_at": received_at,
            "captured_at": captured_at,
            "final_url": response.final_url,
            "http_status": int(response.status),
            "raw_payload": raw,
        }


__all__ = [
    "MAX_V32_MARK_RESPONSE_BYTES",
    "OKX_V32_MARK_PRICE_URL",
    "V32OkxPublicMarkCaptureAdapter",
    "V32OkxPublicOutcomeAdapterError",
]
