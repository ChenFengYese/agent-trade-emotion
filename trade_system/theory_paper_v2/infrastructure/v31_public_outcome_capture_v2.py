"""Capture-only OKX transport for the V3.1 successor outcome workflow.

The adapter performs exactly one allowlisted public GET after validating the
sealed monitor/attempt identity.  It does not decode JSON or inspect market
values.  Response bytes and transport metadata are returned for immediate
atomic persistence; no-response failures are converted to a typed receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime
import socket
import ssl
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.request

from ..domain.contracts.canonical import verify_self_digest
from ..domain.v31_monitor_runtime import verify_monitor_resolution_attempt
from ..domain.v31_outcome_capture_v2 import (
    OKX_MARK_PRICE_URL,
    build_public_outcome_capture,
    build_public_outcome_transport_failure,
)
from .fresh_market.binance_usdm import HttpCapture, PublicHttpTransport


class V31PublicOutcomeCaptureV2Error(ValueError):
    """The capture-only public transport boundary was invalid."""


class _ResponseBodyLimitExceeded(V31PublicOutcomeCaptureV2Error):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OkxRawResponseHttpTransportV2:
    """Return bounded bytes for every HTTP response, including 3xx/4xx/5xx."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        max_response_bytes: int = 1024 * 1024,
    ) -> None:
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= 1024 * 1024
        ):
            raise V31PublicOutcomeCaptureV2Error(
                "V31_CAPTURE_RESPONSE_LIMIT_INVALID"
            )
        self._clock = clock
        self._max_response_bytes = max_response_bytes
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def _capture(self, response: Any) -> HttpCapture:
        body = response.read(self._max_response_bytes + 1)
        if len(body) > self._max_response_bytes:
            raise _ResponseBodyLimitExceeded(
                "V31_CAPTURE_RESPONSE_BODY_LIMIT_EXCEEDED"
            )
        return HttpCapture(
            status=int(response.status if hasattr(response, "status") else response.code),
            headers={key: value for key, value in response.headers.items()},
            body=body,
            received_at=self._clock(),
            final_url=str(response.geturl()),
        )

    def get(self, url: str, timeout: float) -> HttpCapture:
        if url != OKX_MARK_PRICE_URL or timeout <= 0 or timeout > 60:
            raise V31PublicOutcomeCaptureV2Error("V31_CAPTURE_HTTP_SCOPE_INVALID")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "agent-trade-emotion-v31-successor-research/1",
            },
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return self._capture(response)
        except urllib.error.HTTPError as response:
            # HTTPError is still a received HTTP response.  Preserve its exact
            # bounded body; semantic status/redirect rejection happens later.
            return self._capture(response)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31PublicOutcomeCaptureV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31PublicOutcomeCaptureV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31PublicOutcomeCaptureV2Error(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31PublicOutcomeCaptureV2Error(code)
    return normalized


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise V31PublicOutcomeCaptureV2Error("V31_CAPTURE_CLOCK_INVALID")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, _ResponseBodyLimitExceeded):
        return "PUBLIC_RESPONSE_BODY_LIMIT_EXCEEDED"
    if isinstance(exc, TimeoutError):
        return "PUBLIC_TIMEOUT"
    if isinstance(exc, socket.gaierror):
        return "PUBLIC_DNS_UNAVAILABLE"
    if isinstance(exc, ssl.SSLError):
        return "PUBLIC_TLS_FAILURE"
    if isinstance(exc, ConnectionError):
        return "PUBLIC_CONNECTION_FAILURE"
    return "PUBLIC_TRANSPORT_IO_FAILURE"


def _validate_scope(
    *, monitor_plan: Mapping[str, Any], attempt: Mapping[str, Any], requested_at: str
) -> tuple[str, int]:
    try:
        plan_digest = verify_self_digest(monitor_plan, "monitor_plan_digest")
        attempt_digest = verify_monitor_resolution_attempt(attempt)
    except (TypeError, ValueError) as exc:
        raise V31PublicOutcomeCaptureV2Error(
            "V31_CAPTURE_PLAN_OR_ATTEMPT_INVALID"
        ) from exc
    observable = monitor_plan.get("observable")
    boundary = monitor_plan.get("authority_boundary")
    requested = _time(requested_at, "V31_CAPTURE_REQUEST_TIME_INVALID")
    not_before = _time(
        monitor_plan.get("outcome_not_before"), "V31_CAPTURE_PLAN_TIME_INVALID"
    )
    expires = _time(
        monitor_plan.get("expires_at"), "V31_CAPTURE_PLAN_TIME_INVALID"
    )
    cycle_index = monitor_plan.get("cycle_index")
    if (
        not isinstance(observable, Mapping)
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
        or not isinstance(boundary, Mapping)
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
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
        or monitor_plan.get("run_id") != attempt.get("run_id")
        or cycle_index != attempt.get("cycle_index")
        or plan_digest != attempt.get("monitor_plan_digest")
        or attempt.get("attempt_number") != 1
        or attempt.get("retry_allowed") is not False
        or attempt.get("requested_at") != requested_at
        or not not_before <= requested <= expires
    ):
        raise V31PublicOutcomeCaptureV2Error("V31_CAPTURE_SCOPE_INVALID")
    return attempt_digest, cycle_index


class OkxPublicOutcomeCaptureAdapterV2:
    """Perform the sole GET and return unparsed response evidence."""

    def __init__(
        self,
        *,
        transport: PublicHttpTransport | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        timeout: float = 15.0,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise V31PublicOutcomeCaptureV2Error("V31_CAPTURE_TIMEOUT_INVALID")
        if timeout <= 0 or timeout > 60:
            raise V31PublicOutcomeCaptureV2Error("V31_CAPTURE_TIMEOUT_INVALID")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._transport = transport or OkxRawResponseHttpTransportV2(
            clock=self._clock,
            max_response_bytes=1024 * 1024,
        )
        self._timeout = float(timeout)

    def capture_public_outcome(
        self,
        *,
        monitor_plan: Mapping[str, Any],
        attempt: Mapping[str, Any],
        requested_at: str,
    ) -> Mapping[str, Any]:
        attempt_digest, cycle_index = _validate_scope(
            monitor_plan=monitor_plan,
            attempt=attempt,
            requested_at=requested_at,
        )
        started_wall = self._clock()
        started_at = _timestamp(started_wall)
        started_monotonic = self._monotonic_ns()
        try:
            response = self._transport.get(OKX_MARK_PRICE_URL, self._timeout)
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            failed_wall = self._clock()
            elapsed = max(0, (self._monotonic_ns() - started_monotonic) // 1_000_000)
            failure = build_public_outcome_transport_failure(
                run_id=str(monitor_plan["run_id"]),
                cycle_index=cycle_index,
                monitor_plan_digest=str(monitor_plan["monitor_plan_digest"]),
                monitor_attempt_digest=attempt_digest,
                source_request_id=str(
                    monitor_plan["observable"]["source_request_id"]
                ),
                requested_at=requested_at,
                request_started_at=started_at,
                failure_at=_timestamp(failed_wall),
                monotonic_elapsed_ms=int(min(elapsed, 60_000)),
                failure_code=_failure_code(exc),
            )
            return {
                "transport_status": "NO_RESPONSE",
                "capture": None,
                "raw_payload": None,
                "transport_failure": failure,
            }
        elapsed = max(0, (self._monotonic_ns() - started_monotonic) // 1_000_000)
        content_type = next(
            (
                value
                for name, value in response.headers.items()
                if name.casefold() == "content-type"
            ),
            "",
        )
        capture = build_public_outcome_capture(
            run_id=str(monitor_plan["run_id"]),
            cycle_index=cycle_index,
            monitor_plan_digest=str(monitor_plan["monitor_plan_digest"]),
            monitor_attempt_digest=attempt_digest,
            source_request_id=str(monitor_plan["observable"]["source_request_id"]),
            requested_at=requested_at,
            request_started_at=started_at,
            response_received_at=_timestamp(response.received_at),
            monotonic_elapsed_ms=int(min(elapsed, 60_000)),
            status_code=int(response.status),
            content_type=str(content_type),
            final_url=str(response.final_url),
            raw_payload=response.body,
        )
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "capture": capture,
            "raw_payload": response.body,
            "transport_failure": None,
        }


__all__ = [
    "OkxRawResponseHttpTransportV2",
    "OkxPublicOutcomeCaptureAdapterV2",
    "V31PublicOutcomeCaptureV2Error",
]
