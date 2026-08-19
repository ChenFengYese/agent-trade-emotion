"""Concrete public-only OKX aggregate transport for the V3.2 collector.

The collector invokes this adapter once.  Inside that single transaction the
adapter issues the twelve frozen public requests exactly once each, beginning
with provider time so closed-candle pagination is point-in-time reproducible.
Required-component failure aborts the transaction; optional-component failure
is represented as typed UNKNOWN.  No credential, account or order endpoint is
reachable from this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
import http.client
import json
import socket
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.parse
import urllib.request

from ..domain.contracts.canonical import canonical_bytes
from ..application.v32_public_evidence_port import OKX_PUBLIC_HOST
from .v32_public_source_collector import (
    OKX_INSTRUMENT_ID,
    OKX_PUBLIC_BASE_URL,
    MAX_PUBLIC_COMPONENT_CAPTURE_BYTES,
    RAW_BUNDLE_SCHEMA_ID,
    RAW_BUNDLE_SCHEMA_VERSION,
    V32PublicComponentRawSink,
    V32PublicComponentRawSinkError,
)
from .v32_public_https_route import (
    V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
    V32SystemPublicHttpsOpener,
    build_v32_public_get_request_v1,
    classify_v32_public_https_failure_v1,
)


class V32OkxPublicBundleTransportError(OSError):
    """A required public request or the aggregate envelope failed."""

    def __init__(
        self,
        failure_code: str,
        *,
        failure_context: Mapping[str, Any] | None = None,
        failure_response_body: bytes | None = None,
        failure_raw_binding: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.failure_context = (
            None if failure_context is None else dict(failure_context)
        )
        self.failure_response_body = failure_response_body
        self.failure_raw_binding = (
            None if failure_raw_binding is None else dict(failure_raw_binding)
        )


class _Response(Protocol):
    status: int

    def read(self, amount: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def __enter__(self) -> "_Response": ...
    def __exit__(self, *args: object) -> None: ...


class _Opener(Protocol):
    def open(self, request: urllib.request.Request, timeout: float) -> _Response: ...


Clock = Callable[[], str]

_MAX_COMPONENT_BYTES = MAX_PUBLIC_COMPONENT_CAPTURE_BYTES - 1
_TRANSIENT_HTTP_STATUS_CODES = frozenset({429, *range(500, 600)})
_TRANSIENT_PHYSICAL_FAILURE_CODES = frozenset(
    {
        "PUBLIC_CONNECTION_FAILURE",
        "PUBLIC_DNS_UNAVAILABLE",
        "PUBLIC_TIMEOUT",
        "PUBLIC_TLS_FAILURE",
        "PUBLIC_TRANSPORT_IO_FAILURE",
    }
)
_REQUIRED = frozenset(
    {
        "SERVER_TIME",
        "INSTRUMENT",
        "TICKER",
        "MARK_PRICE",
        "CLOSED_CANDLES_15M",
        "CLOSED_CANDLES_1H",
        "CLOSED_CANDLES_4H",
        "CLOSED_CANDLES_1D",
    }
)
_OPTIONAL = frozenset(
    {
        "OPEN_INTEREST",
        "FUNDING_RATE",
        "ORDER_BOOK",
        "RECENT_TRADES",
    }
)
_ORDER = (
    "SERVER_TIME",
    "INSTRUMENT",
    "TICKER",
    "MARK_PRICE",
    "CLOSED_CANDLES_15M",
    "CLOSED_CANDLES_1H",
    "CLOSED_CANDLES_4H",
    "CLOSED_CANDLES_1D",
    "OPEN_INTEREST",
    "FUNDING_RATE",
    "ORDER_BOOK",
    "RECENT_TRADES",
)
_PATHS = {
    "SERVER_TIME": "/api/v5/public/time",
    "INSTRUMENT": "/api/v5/public/instruments",
    "TICKER": "/api/v5/market/ticker",
    "MARK_PRICE": "/api/v5/public/mark-price",
    "CLOSED_CANDLES_15M": "/api/v5/market/history-candles",
    "CLOSED_CANDLES_1H": "/api/v5/market/history-candles",
    "CLOSED_CANDLES_4H": "/api/v5/market/history-candles",
    "CLOSED_CANDLES_1D": "/api/v5/market/history-candles",
    "OPEN_INTEREST": "/api/v5/public/open-interest",
    "FUNDING_RATE": "/api/v5/public/funding-rate",
    "ORDER_BOOK": "/api/v5/market/books",
    "RECENT_TRADES": "/api/v5/market/trades",
}

if (
    len(_ORDER) != 12
    or len(set(_ORDER)) != 12
    or set(_ORDER) != set(_PATHS)
    or _REQUIRED & _OPTIONAL
    or _REQUIRED | _OPTIONAL != set(_ORDER)
):
    raise RuntimeError("V32_OKX_TRANSPORT_STATIC_POLICY_INVALID")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _time(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32OkxPublicBundleTransportError("V32_OKX_TRANSPORT_CLOCK_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32OkxPublicBundleTransportError(
            "V32_OKX_TRANSPORT_CLOCK_INVALID"
        ) from exc
    if parsed.tzinfo is None:
        raise V32OkxPublicBundleTransportError("V32_OKX_TRANSPORT_CLOCK_INVALID")
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V32OkxPublicBundleTransportError("V32_OKX_TRANSPORT_CLOCK_INVALID")
    return value


def _okx_server_time(body: str) -> int:
    try:
        document = json.loads(body)
        if (
            not isinstance(document, Mapping)
            or document.get("code") != "0"
            or not isinstance(document.get("data"), list)
            or len(document["data"]) != 1
            or not isinstance(document["data"][0], Mapping)
        ):
            raise ValueError("shape")
        value = document["data"][0].get("ts")
        if not isinstance(value, str) or not value.isdigit():
            raise ValueError("timestamp")
        milliseconds = int(value)
        if milliseconds <= 0:
            raise ValueError("timestamp")
        return milliseconds
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise V32OkxPublicBundleTransportError(
            "V32_OKX_TRANSPORT_SERVER_TIME_INVALID"
        ) from exc


def _queries(instrument_id: str, server_ms: int) -> dict[str, dict[str, str]]:
    buckets = {
        "15M": (server_ms // 900_000) * 900_000,
        "1H": (server_ms // 3_600_000) * 3_600_000,
        "4H": (server_ms // 14_400_000) * 14_400_000,
        "1D": (server_ms // 86_400_000) * 86_400_000,
    }
    return {
        "SERVER_TIME": {},
        "INSTRUMENT": {"instId": instrument_id, "instType": "SWAP"},
        "TICKER": {"instId": instrument_id},
        "MARK_PRICE": {"instId": instrument_id, "instType": "SWAP"},
        "CLOSED_CANDLES_15M": {
            "after": str(buckets["15M"]),
            "bar": "15m",
            "instId": instrument_id,
            "limit": "96",
        },
        "CLOSED_CANDLES_1H": {
            "after": str(buckets["1H"]),
            "bar": "1H",
            "instId": instrument_id,
            "limit": "168",
        },
        "CLOSED_CANDLES_4H": {
            "after": str(buckets["4H"]),
            "bar": "4H",
            "instId": instrument_id,
            "limit": "90",
        },
        "CLOSED_CANDLES_1D": {
            "after": str(buckets["1D"]),
            "bar": "1Dutc",
            "instId": instrument_id,
            "limit": "60",
        },
        "OPEN_INTEREST": {"instId": instrument_id, "instType": "SWAP"},
        "FUNDING_RATE": {"instId": instrument_id},
        "ORDER_BOOK": {"instId": instrument_id, "sz": "50"},
        "RECENT_TRADES": {"instId": instrument_id, "limit": "100"},
    }


class V32OkxPublicBundleTransport:
    """One-shot HTTPS transport with an injected opener for focused tests."""

    def __init__(
        self,
        *,
        clock: Clock = _utc_now,
        opener: _Opener | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not isinstance(timeout_seconds, (int, float)) or isinstance(
            timeout_seconds, bool
        ) or not 0 < float(timeout_seconds) <= 30:
            raise V32OkxPublicBundleTransportError(
                "V32_OKX_TRANSPORT_TIMEOUT_INVALID"
            )
        self._clock = clock
        self._opener = opener or V32SystemPublicHttpsOpener()
        self._timeout = float(timeout_seconds)
        self._consumed = False

    def _request(
        self,
        component_id: str,
        query: Mapping[str, str],
        *,
        raw_body_sink: V32PublicComponentRawSink,
    ) -> dict[str, Any]:
        started = _time(self._clock())
        encoded = urllib.parse.urlencode(sorted(query.items()))
        url = OKX_PUBLIC_BASE_URL + _PATHS[component_id]
        if encoded:
            url += "?" + encoded
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != OKX_PUBLIC_HOST
            or parsed.port not in {None, 443}
            or not parsed.path.startswith("/api/v5/")
        ):
            raise V32OkxPublicBundleTransportError(
                "V32_OKX_TRANSPORT_ENDPOINT_INVALID"
            )
        request = build_v32_public_get_request_v1(url)
        response_present = False
        response_body: bytes | None = None
        http_status: int | None = None
        raw_binding: Mapping[str, str] | None = None
        final_url: str | None = None
        response_received_at: str | None = None
        capture_completed_at: str | None = None
        route_policy_id = str(
            getattr(
                self._opener,
                "route_policy_id",
                "INJECTED_PUBLIC_OPENER_NO_ROUTE_CLAIM",
            )
        )
        if route_policy_id not in {
            V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
            "INJECTED_PUBLIC_OPENER_NO_ROUTE_CLAIM",
        }:
            raise V32OkxPublicBundleTransportError(
                "V32_OKX_TRANSPORT_ROUTE_POLICY_INVALID"
            )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                response_present = True
                final_url = response.geturl()
                status = int(response.status)
                http_status = status
                try:
                    raw = response.read(_MAX_COMPONENT_BYTES + 1)
                except (OSError, ValueError, http.client.HTTPException):
                    raise V32OkxPublicBundleTransportError(
                        f"V32_OKX_TRANSPORT_{component_id}_BODY_READ_FAILED"
                    ) from None
                response_body = raw
                response_received_at = _time(self._clock())
                capture_completed_at = _time(self._clock())
                raw_binding = raw_body_sink.seal_component_capture(
                    component_id=component_id,
                    payload=raw,
                    method="GET",
                    path=_PATHS[component_id],
                    query=dict(sorted(query.items())),
                    http_status=status,
                    final_url=final_url,
                    request_started_at=started,
                    response_received_at=response_received_at,
                    capture_completed_at=capture_completed_at,
                    route_policy_id=route_policy_id,
                )
            received = capture_completed_at
            assert received is not None
            if not isinstance(final_url, str) or final_url != url:
                raise V32OkxPublicBundleTransportError(
                    f"V32_OKX_TRANSPORT_{component_id}_REDIRECT_FORBIDDEN"
                )
            if status != 200:
                code = (
                    f"V32_OKX_TRANSPORT_{component_id}_PROVIDER_TRANSIENT"
                    if status in _TRANSIENT_HTTP_STATUS_CODES
                    else f"V32_OKX_TRANSPORT_{component_id}_HTTP_STATUS_FORBIDDEN"
                )
                raise V32OkxPublicBundleTransportError(code)
            if not raw or len(raw) > _MAX_COMPONENT_BYTES:
                raise V32OkxPublicBundleTransportError(
                    f"V32_OKX_TRANSPORT_{component_id}_RESPONSE_INVALID"
                )
            body = raw.decode("utf-8", errors="strict")
            # Parse only the public OKX envelope here.  Component semantics are
            # owned by the raw-first collector after durable persistence.
            envelope = json.loads(body)
            if (
                not isinstance(envelope, Mapping)
                or envelope.get("code") != "0"
                or not isinstance(envelope.get("data"), list)
            ):
                raise V32OkxPublicBundleTransportError(
                    f"V32_OKX_TRANSPORT_{component_id}_ENVELOPE_INVALID"
                )
            return {
                "component_id": component_id,
                "method": "GET",
                "path": _PATHS[component_id],
                "query": dict(sorted(query.items())),
                "status": "OBSERVED",
                "http_status": 200,
                "body_utf8": body,
                "error_code": None,
                "request_started_at": started,
                "response_received_at": response_received_at,
                "attempt_number": 1,
                "retry_allowed": False,
                "raw_binding": dict(raw_binding) if raw_binding is not None else None,
                "failure_evidence_binding": None,
                "_capture_metadata": {
                    "final_url": final_url,
                    "response_received_at": response_received_at,
                    "capture_completed_at": capture_completed_at,
                    "route_policy_id": route_policy_id,
                },
            }
        except (
            V32OkxPublicBundleTransportError,
            V32PublicComponentRawSinkError,
            UnicodeError,
            json.JSONDecodeError,
            socket.timeout,
            TimeoutError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            ConnectionError,
            http.client.HTTPException,
            OSError,
        ) as exc:
            if isinstance(exc, urllib.error.HTTPError):
                response_present = True
                http_status = int(exc.code)
                final_url = exc.geturl()
                try:
                    candidate = exc.read(_MAX_COMPONENT_BYTES + 1)
                except (OSError, ValueError, http.client.HTTPException):
                    candidate = None
                    exc = V32OkxPublicBundleTransportError(
                        f"V32_OKX_TRANSPORT_{component_id}_BODY_READ_FAILED"
                    )
                if candidate is not None:
                    response_body = candidate
                    response_received_at = _time(self._clock())
                    capture_completed_at = _time(self._clock())
                    try:
                        raw_binding = raw_body_sink.seal_component_capture(
                            component_id=component_id,
                            payload=candidate,
                            method="GET",
                            path=_PATHS[component_id],
                            query=dict(sorted(query.items())),
                            http_status=http_status,
                            final_url=final_url,
                            request_started_at=started,
                            response_received_at=response_received_at,
                            capture_completed_at=capture_completed_at,
                            route_policy_id=route_policy_id,
                        )
                    except V32PublicComponentRawSinkError as sink_exc:
                        exc = sink_exc
            received = _time(self._clock())
            component_code = (
                exc.failure_code
                if isinstance(
                    exc,
                    (
                        V32OkxPublicBundleTransportError,
                        V32PublicComponentRawSinkError,
                    ),
                )
                else f"V32_OKX_TRANSPORT_{component_id}_FAILED"
            )
            structural_failure_code = (
                exc.failure_code
                if isinstance(exc, V32OkxPublicBundleTransportError)
                else ""
            )
            if isinstance(exc, V32PublicComponentRawSinkError):
                leaf_code = "PUBLIC_RAW_SINK_STRUCTURAL_FAILURE"
            elif response_present and response_body is None:
                leaf_code = "PUBLIC_RESPONSE_BODY_READ_FAILED"
            elif "REDIRECT_FORBIDDEN" in structural_failure_code:
                leaf_code = "PUBLIC_REDIRECT_FORBIDDEN"
            elif isinstance(
                exc,
                (UnicodeError, json.JSONDecodeError),
            ) or any(
                marker in structural_failure_code
                for marker in ("ENVELOPE_INVALID", "RESPONSE_INVALID")
            ):
                leaf_code = "PUBLIC_RESPONSE_STRUCTURAL_FAILURE"
            elif http_status is not None:
                if 300 <= http_status < 400:
                    leaf_code = "PUBLIC_REDIRECT_FORBIDDEN"
                elif http_status in _TRANSIENT_HTTP_STATUS_CODES:
                    leaf_code = "PUBLIC_PROVIDER_UNAVAILABLE"
                else:
                    leaf_code = "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE"
            else:
                leaf_code = classify_v32_public_https_failure_v1(exc)
            coverage_eligible = (
                http_status in _TRANSIENT_HTTP_STATUS_CODES
                if http_status is not None
                else leaf_code in _TRANSIENT_PHYSICAL_FAILURE_CODES
            )
            coverage_eligible = (
                coverage_eligible
                and not isinstance(exc, V32PublicComponentRawSinkError)
                and (not response_present or raw_binding is not None)
            )
            failure_evidence_binding: Mapping[str, str] | None = None
            if component_id in _OPTIONAL and coverage_eligible:
                if raw_binding is not None:
                    failure_evidence_binding = dict(raw_binding)
                else:
                    try:
                        failure_evidence_binding = (
                            raw_body_sink.seal_component_no_response_failure(
                                component_id=component_id,
                                method="GET",
                                path=_PATHS[component_id],
                                query=dict(sorted(query.items())),
                                request_started_at=started,
                                failure_at=received,
                                response_present=False,
                                body_present=False,
                                http_status=None,
                                response_final_url=None,
                                failure_codes=[component_code, leaf_code],
                                route_policy_id=route_policy_id,
                                attempt_number=1,
                                retry_allowed=False,
                            )
                        )
                    except V32PublicComponentRawSinkError as sink_exc:
                        exc = sink_exc
                        component_code = sink_exc.failure_code
                        leaf_code = "PUBLIC_RAW_SINK_STRUCTURAL_FAILURE"
                        coverage_eligible = False
            if component_id in _OPTIONAL and coverage_eligible:
                return {
                    "component_id": component_id,
                    "method": "GET",
                    "path": _PATHS[component_id],
                    "query": dict(sorted(query.items())),
                    "status": "UNKNOWN",
                    "http_status": http_status,
                    "body_utf8": None,
                    "error_code": leaf_code,
                    "request_started_at": started,
                    "response_received_at": response_received_at or received,
                    "attempt_number": 1,
                    "retry_allowed": False,
                    "raw_binding": (
                        dict(raw_binding) if raw_binding is not None else None
                    ),
                    "failure_evidence_binding": dict(
                        failure_evidence_binding
                    ),
                    "_capture_metadata": (
                        None
                        if raw_binding is None
                        else {
                            "final_url": final_url,
                            "response_received_at": response_received_at,
                            "capture_completed_at": capture_completed_at,
                            "route_policy_id": route_policy_id,
                        }
                    ),
                }
            request_dispatched = getattr(exc, "request_dispatched", True)
            raise V32OkxPublicBundleTransportError(
                component_code,
                failure_context={
                    "component_id": component_id,
                    "method": "GET",
                    "path": _PATHS[component_id],
                    "query": dict(sorted(query.items())),
                    "request_started_at": started,
                    "failure_at": received,
                    "response_received_at": response_received_at,
                    "capture_completed_at": capture_completed_at,
                    "final_url": final_url,
                    "request_dispatched": request_dispatched,
                    "response_present": response_present,
                    "body_present": response_body is not None,
                    "http_status": http_status,
                    "route_policy_id": route_policy_id,
                    "failure_codes": [component_code, leaf_code],
                    "attempt_number": 1,
                    "retry_allowed": False,
                },
                failure_response_body=response_body,
                failure_raw_binding=raw_binding,
            ) from None

    def fetch_once(
        self,
        *,
        instrument_id: str,
        raw_body_sink: V32PublicComponentRawSink,
    ) -> bytes:
        if instrument_id != OKX_INSTRUMENT_ID:
            raise V32OkxPublicBundleTransportError(
                "V32_OKX_TRANSPORT_INSTRUMENT_INVALID"
            )
        if self._consumed:
            raise V32OkxPublicBundleTransportError(
                "V32_OKX_TRANSPORT_ATTEMPT_ALREADY_CONSUMED"
            )
        # Set before the first physical request.  Required failure therefore
        # cannot be retried through the same aggregate transport instance.
        self._consumed = True
        if not callable(
            getattr(raw_body_sink, "seal_component_capture", None)
        ) or not callable(
            getattr(
                raw_body_sink,
                "seal_component_no_response_failure",
                None,
            )
        ):
            raise V32OkxPublicBundleTransportError(
                "V32_OKX_TRANSPORT_RAW_SINK_INVALID"
            )
        server = self._request(
            "SERVER_TIME", {}, raw_body_sink=raw_body_sink
        )
        try:
            server_ms = _okx_server_time(server["body_utf8"])
        except V32OkxPublicBundleTransportError as exc:
            server_failure_at = _time(self._clock())
            server_capture = server.get("_capture_metadata")
            if not isinstance(server_capture, Mapping):
                raise V32OkxPublicBundleTransportError(
                    "V32_OKX_TRANSPORT_SERVER_TIME_CAPTURE_MISSING"
                ) from None
            raise V32OkxPublicBundleTransportError(
                exc.failure_code,
                failure_context={
                    "component_id": "SERVER_TIME",
                    "method": "GET",
                    "path": _PATHS["SERVER_TIME"],
                    "query": {},
                    "request_started_at": server["request_started_at"],
                    "failure_at": server_failure_at,
                    "response_received_at": server_capture[
                        "response_received_at"
                    ],
                    "capture_completed_at": server_capture[
                        "capture_completed_at"
                    ],
                    "final_url": server_capture["final_url"],
                    "request_dispatched": True,
                    "response_present": True,
                    "body_present": True,
                    "http_status": 200,
                    "route_policy_id": server_capture["route_policy_id"],
                    "failure_codes": [
                        "V32_OKX_TRANSPORT_SERVER_TIME_INVALID",
                        "UNCLASSIFIED_STRUCTURAL_FAILURE",
                    ],
                    "attempt_number": 1,
                    "retry_allowed": False,
                },
                failure_response_body=str(server["body_utf8"]).encode("utf-8"),
                failure_raw_binding=server["raw_binding"],
            ) from None
        queries = _queries(instrument_id, server_ms)
        components = [server]
        components.extend(
            self._request(
                component_id,
                queries[component_id],
                raw_body_sink=raw_body_sink,
            )
            for component_id in _ORDER[1:]
        )
        if [row["component_id"] for row in components] != list(_ORDER):
            raise V32OkxPublicBundleTransportError(
                "V32_OKX_TRANSPORT_COMPONENT_ORDER_INVALID"
            )
        public_components = [
            {
                key: value
                for key, value in row.items()
                if key != "_capture_metadata"
            }
            for row in components
        ]
        return canonical_bytes(
            {
                "schema_id": RAW_BUNDLE_SCHEMA_ID,
                "schema_version": RAW_BUNDLE_SCHEMA_VERSION,
                "base_url": OKX_PUBLIC_BASE_URL,
                "venue": "OKX",
                "instrument_id": instrument_id,
                "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
                "components": public_components,
            }
        )


__all__ = [
    "V32OkxPublicBundleTransport",
    "V32OkxPublicBundleTransportError",
]
