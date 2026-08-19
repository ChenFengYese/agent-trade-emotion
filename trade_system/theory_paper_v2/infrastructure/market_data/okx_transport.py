"""Credential-free, no-retry HTTPS transport for the V3.3 OKX baseline.

Only the frozen core and optional endpoint shapes are admitted.  Every received
body is sealed through :class:`RawCaptureSink` before status, redirect, size,
or provider semantics are interpreted by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import http.client
import re
import socket
import ssl
import threading
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.parse
import urllib.request

from .raw_capture import LoadedRawCapture, RawCaptureSink


OKX_PUBLIC_BASE_URL = "https://openapi.okx.com"
OKX_PUBLIC_HOST = "openapi.okx.com"
MAX_PUBLIC_RESPONSE_BYTES = 2 * 1024 * 1024
PUBLIC_ROUTE_POLICY_ID = (
    "V33_OKX_PUBLIC_HTTPS_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V1"
)
PUBLIC_REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "agent-trade-emotion-v3.3-public-research/1.0",
}

SERVER_TIME_PATH = "/api/v5/public/time"
INSTRUMENT_PATH = "/api/v5/public/instruments"
MARK_PRICE_PATH = "/api/v5/public/mark-price"
CLOSED_CANDLES_15M_PATH = "/api/v5/market/history-candles"
ORDER_BOOK_PATH = "/api/v5/market/books"
RECENT_TRADES_PATH = "/api/v5/market/trades"
OPEN_INTEREST_PATH = "/api/v5/public/open-interest"
FUNDING_RATE_HISTORY_PATH = "/api/v5/public/funding-rate-history"
ALLOWED_PUBLIC_PATHS = frozenset(
    {
        SERVER_TIME_PATH,
        INSTRUMENT_PATH,
        MARK_PRICE_PATH,
        CLOSED_CANDLES_15M_PATH,
    }
)
ALLOWED_OPTIONAL_PUBLIC_PATHS = frozenset(
    {
        ORDER_BOOK_PATH,
        RECENT_TRADES_PATH,
        OPEN_INTEREST_PATH,
        FUNDING_RATE_HISTORY_PATH,
    }
)
_ALL_ALLOWED_PUBLIC_PATHS = ALLOWED_PUBLIC_PATHS | ALLOWED_OPTIONAL_PUBLIC_PATHS
_FORBIDDEN_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "ok-access-key",
        "ok-access-passphrase",
        "ok-access-sign",
        "proxy-authorization",
    }
)
_TRANSIENT_HTTP_STATUSES = frozenset({429, *range(500, 600)})
_SAFE_CAPTURE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_COMPONENT_PATHS = {
    "SERVER_TIME": SERVER_TIME_PATH,
    "INSTRUMENT": INSTRUMENT_PATH,
    "MARK_PRICE": MARK_PRICE_PATH,
    "CLOSED_CANDLES_15M": CLOSED_CANDLES_15M_PATH,
    "OUTCOME_MARK_PRICE": MARK_PRICE_PATH,
    "ORDER_BOOK": ORDER_BOOK_PATH,
    "RECENT_TRADES": RECENT_TRADES_PATH,
    "OPEN_INTEREST": OPEN_INTEREST_PATH,
    "FUNDING_RATE_HISTORY": FUNDING_RATE_HISTORY_PATH,
}
_CAPTURE_SUMMARY_FIELDS = frozenset(
    {
        "component_id",
        "method",
        "path",
        "query",
        "request_started_at",
        "response_received_at",
        "capture_completed_at",
        "http_status",
        "final_url",
        "route_policy_id",
        "attempt_number",
        "retry_allowed",
        "response_limit_bytes",
        "body_truncated",
    }
)


class OkxPublicTransportError(OSError):
    """A single public request failed without retry or fallback."""

    def __init__(
        self,
        failure_code: str,
        *,
        coverage_eligible: bool = False,
        failure_at: str | None = None,
        raw_ref: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.coverage_eligible = coverage_eligible
        self.failure_at = failure_at
        self.raw_ref = None if raw_ref is None else dict(raw_ref)


@dataclass(frozen=True, slots=True)
class CapturedPublicResponse:
    component_id: str
    path: str
    query: Mapping[str, str]
    http_status: int
    body: bytes
    request_started_at: str
    response_received_at: str
    capture_completed_at: str
    final_url: str
    raw_ref: Mapping[str, Any]


class _Response(Protocol):
    status: int

    def read(self, amount: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def close(self) -> None: ...


class PublicOpener(Protocol):
    route_policy_id: str

    def open(
        self, request: urllib.request.Request, timeout: float
    ) -> _Response: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _canonical_time(value: object, *, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OkxPublicTransportError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OkxPublicTransportError(code) from exc
    if parsed.tzinfo is None:
        raise OkxPublicTransportError(code)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _time_order_key(value: str) -> datetime:
    """Compare canonical instants, not variable-precision ISO text."""

    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _validated_query(path: str, query: Mapping[str, str]) -> dict[str, str]:
    if path not in _ALL_ALLOWED_PUBLIC_PATHS or not isinstance(query, Mapping):
        raise OkxPublicTransportError("OKX_PUBLIC_ENDPOINT_INVALID")
    if any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or not value
        for key, value in query.items()
    ):
        raise OkxPublicTransportError("OKX_PUBLIC_QUERY_INVALID")
    ordered = {key: query[key] for key in sorted(query)}
    if path == SERVER_TIME_PATH:
        valid = not ordered
    elif path in {INSTRUMENT_PATH, MARK_PRICE_PATH, OPEN_INTEREST_PATH}:
        valid = (
            set(ordered) == {"instId", "instType"}
            and ordered.get("instType") == "SWAP"
            and _valid_instrument_id(ordered.get("instId"))
        )
    elif path == CLOSED_CANDLES_15M_PATH:
        after = ordered.get("after", "")
        valid = (
            set(ordered) == {"after", "bar", "instId", "limit"}
            and ordered.get("bar") == "15m"
            and ordered.get("limit") == "96"
            and _valid_instrument_id(ordered.get("instId"))
            and after.isascii()
            and after.isdigit()
            and int(after) > 0
            and int(after) % 900_000 == 0
        )
    elif path == ORDER_BOOK_PATH:
        valid = (
            set(ordered) == {"instId", "sz"}
            and ordered.get("sz") == "20"
            and _valid_instrument_id(ordered.get("instId"))
        )
    elif path == RECENT_TRADES_PATH:
        valid = (
            set(ordered) == {"instId", "limit"}
            and ordered.get("limit") == "100"
            and _valid_instrument_id(ordered.get("instId"))
        )
    else:
        valid = (
            path == FUNDING_RATE_HISTORY_PATH
            and set(ordered) == {"instId", "limit"}
            and ordered.get("limit") == "10"
            and _valid_instrument_id(ordered.get("instId"))
        )
    if not valid:
        raise OkxPublicTransportError("OKX_PUBLIC_QUERY_INVALID")
    return ordered


def _valid_instrument_id(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 64:
        return False
    parts = value.split("-")
    return (
        len(parts) == 3
        and parts[-1] == "SWAP"
        and all(
            part
            and part.isascii()
            and part.isalnum()
            and part.upper() == part
            for part in parts
        )
    )


def build_public_get_request(
    *, path: str, query: Mapping[str, str]
) -> tuple[urllib.request.Request, str, dict[str, str]]:
    """Build one exact public GET with no caller-supplied headers."""

    ordered = _validated_query(path, query)
    encoded = urllib.parse.urlencode(tuple(ordered.items()))
    url = OKX_PUBLIC_BASE_URL + path + (f"?{encoded}" if encoded else "")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != OKX_PUBLIC_HOST
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise OkxPublicTransportError("OKX_PUBLIC_ENDPOINT_INVALID")
    request = urllib.request.Request(
        url,
        method="GET",
        headers=PUBLIC_REQUEST_HEADERS,
    )
    header_names = {name.casefold() for name, _ in request.header_items()}
    if header_names & _FORBIDDEN_HEADERS:
        raise OkxPublicTransportError("OKX_PUBLIC_CREDENTIAL_HEADER_FORBIDDEN")
    return request, url, ordered


def _validated_system_proxy(
    proxies: Mapping[str, str],
    *,
    bypass_checker: Callable[[str], bool],
) -> tuple[str, str] | None:
    if not isinstance(proxies, Mapping):
        raise OkxPublicTransportError("PUBLIC_ROUTE_CONFIGURATION_INVALID")
    raw = proxies.get("https")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise OkxPublicTransportError("PUBLIC_ROUTE_CONFIGURATION_INVALID")
    parsed = urllib.parse.urlsplit(raw)
    try:
        port = parsed.port
    except ValueError:
        raise OkxPublicTransportError("PUBLIC_ROUTE_CONFIGURATION_INVALID") from None
    if parsed.username is not None or parsed.password is not None:
        raise OkxPublicTransportError("PUBLIC_PROXY_CREDENTIALS_FORBIDDEN")
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or (port is not None and not 1 <= port <= 65535)
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise OkxPublicTransportError("PUBLIC_ROUTE_CONFIGURATION_INVALID")
    try:
        bypassed = bypass_checker(OKX_PUBLIC_HOST)
    except Exception:
        raise OkxPublicTransportError("PUBLIC_ROUTE_CONFIGURATION_INVALID") from None
    if bypassed is not False:
        raise OkxPublicTransportError("PUBLIC_PROXY_BYPASS_FORBIDDEN")
    return parsed.scheme, parsed.netloc


class _FrozenHttpsProxyHandler(urllib.request.ProxyHandler):
    """Apply the validated proxy without a second bypass decision."""

    def __init__(self, *, scheme: str, authority: str) -> None:
        self._scheme = scheme
        self._authority = authority
        super().__init__({"https": f"{scheme}://{authority}"})

    def proxy_open(self, request, proxy, proxy_type):  # noqa: ANN001
        if (
            proxy_type != "https"
            or request.type != "https"
            or request.host != OKX_PUBLIC_HOST
            or proxy != f"{self._scheme}://{self._authority}"
        ):
            raise OkxPublicTransportError("PUBLIC_ROUTE_CONFIGURATION_INVALID")
        request.set_proxy(self._authority, self._scheme)
        return None


class SystemPublicHttpsOpener:
    """Resolve one non-credential system HTTPS route; never redirect or retry."""

    route_policy_id = PUBLIC_ROUTE_POLICY_ID

    def __init__(
        self,
        *,
        proxy_supplier: Callable[[], Mapping[str, str]] = urllib.request.getproxies,
        bypass_checker: Callable[[str], bool] = urllib.request.proxy_bypass,
    ) -> None:
        if not callable(proxy_supplier) or not callable(bypass_checker):
            raise OkxPublicTransportError("PUBLIC_ROUTE_CONFIGURATION_INVALID")
        self._proxy_supplier = proxy_supplier
        self._bypass_checker = bypass_checker
        self._opener: Any | None = None
        self._lock = threading.Lock()

    def _resolve(self):  # noqa: ANN202 - urllib has no stable opener type.
        if self._opener is not None:
            return self._opener
        with self._lock:
            if self._opener is not None:
                return self._opener
            try:
                proxy = _validated_system_proxy(
                    self._proxy_supplier(), bypass_checker=self._bypass_checker
                )
            except OkxPublicTransportError:
                raise
            except Exception:
                raise OkxPublicTransportError(
                    "PUBLIC_ROUTE_CONFIGURATION_UNAVAILABLE"
                ) from None
            handler: urllib.request.ProxyHandler
            if proxy is None:
                handler = urllib.request.ProxyHandler({})
            else:
                handler = _FrozenHttpsProxyHandler(
                    scheme=proxy[0], authority=proxy[1]
                )
            self._opener = urllib.request.build_opener(handler, _NoRedirect())
            return self._opener

    def open(self, request: urllib.request.Request, timeout: float) -> _Response:
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or timeout <= 0
        ):
            raise OkxPublicTransportError("PUBLIC_TIMEOUT_INVALID")
        return self._resolve().open(request, timeout=float(timeout))


def _physical_failure(exc: BaseException) -> str | None:
    current: BaseException | object = exc
    if isinstance(current, urllib.error.URLError) and not isinstance(
        current, urllib.error.HTTPError
    ):
        current = current.reason
    if isinstance(current, (socket.timeout, TimeoutError)):
        return "PUBLIC_TIMEOUT"
    if isinstance(current, socket.gaierror):
        return "PUBLIC_DNS_UNAVAILABLE"
    if isinstance(current, (ssl.SSLError, ssl.CertificateError)):
        return "PUBLIC_TLS_FAILURE"
    if isinstance(
        current,
        (ConnectionRefusedError, ConnectionResetError, BrokenPipeError),
    ):
        return "PUBLIC_CONNECTION_FAILURE"
    if isinstance(current, (ConnectionError, OSError)):
        return "PUBLIC_TRANSPORT_IO_FAILURE"
    return None


def _validated_raw_ref(
    value: object,
    *,
    cycle_id: str,
    capture_id: str,
    payload: bytes,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OkxPublicTransportError("RAW_CAPTURE_REFERENCE_INVALID")
    expected = {
        "artifact_type",
        "artifact_id",
        "path",
        "size_bytes",
        "sha256",
    }
    candidate = dict(value)
    if (
        set(candidate) != expected
        or candidate.get("artifact_type") != "RawCapture"
        or candidate.get("artifact_id") != f"{cycle_id}.{capture_id}.raw"
        or candidate.get("path") != f"raw/{capture_id}/body.bin"
        or candidate.get("size_bytes") != len(payload)
        or candidate.get("sha256") != hashlib.sha256(payload).hexdigest()
    ):
        raise OkxPublicTransportError("RAW_CAPTURE_REFERENCE_INVALID")
    return candidate


def _route_policy_id(opener: object) -> str:
    return str(
        getattr(
            opener,
            "route_policy_id",
            "INJECTED_PUBLIC_OPENER_NO_ROUTE_CLAIM",
        )
    )


def _attempt_binding(
    *,
    component_id: str,
    path: str,
    ordered_query: Mapping[str, str],
    route_policy_id: str,
    response_limit_bytes: int,
) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "method": "GET",
        "path": path,
        "query": dict(ordered_query),
        "route_policy_id": route_policy_id,
        "response_limit_bytes": response_limit_bytes,
        "attempt_number": 1,
        "retry_allowed": False,
    }


def _classify_captured_response(
    response: CapturedPublicResponse,
    *,
    expected_url: str,
    max_response_bytes: int,
) -> CapturedPublicResponse:
    """Apply response-dependent policy only after durable raw availability."""

    raw_ref = response.raw_ref
    if response.final_url != expected_url:
        raise OkxPublicTransportError(
            "PUBLIC_REDIRECT_FORBIDDEN",
            failure_at=response.capture_completed_at,
            raw_ref=raw_ref,
        )
    if len(response.body) > max_response_bytes:
        raise OkxPublicTransportError(
            "PUBLIC_RESPONSE_TOO_LARGE",
            failure_at=response.capture_completed_at,
            raw_ref=raw_ref,
        )
    if not 100 <= response.http_status <= 599:
        raise OkxPublicTransportError(
            "PUBLIC_HTTP_STATUS_INVALID",
            failure_at=response.capture_completed_at,
            raw_ref=raw_ref,
        )
    if response.http_status != 200:
        if response.http_status in _TRANSIENT_HTTP_STATUSES:
            raise OkxPublicTransportError(
                "PUBLIC_PROVIDER_UNAVAILABLE",
                coverage_eligible=True,
                failure_at=response.capture_completed_at,
                raw_ref=raw_ref,
            )
        if 300 <= response.http_status < 400:
            code = "PUBLIC_REDIRECT_FORBIDDEN"
        else:
            code = "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE"
        raise OkxPublicTransportError(
            code,
            failure_at=response.capture_completed_at,
            raw_ref=raw_ref,
        )
    if not response.body:
        raise OkxPublicTransportError(
            "PUBLIC_RESPONSE_EMPTY",
            failure_at=response.capture_completed_at,
            raw_ref=raw_ref,
        )
    return response


class OkxPublicTransport:
    """Issue one bounded GET per capture id and seal any response first."""

    def __init__(
        self,
        *,
        raw_sink: RawCaptureSink,
        clock: Callable[[], str],
        opener: PublicOpener | None = None,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = MAX_PUBLIC_RESPONSE_BYTES,
    ) -> None:
        if not callable(getattr(raw_sink, "seal_response", None)):
            raise OkxPublicTransportError("RAW_CAPTURE_SINK_INVALID")
        if not callable(clock):
            raise OkxPublicTransportError("PUBLIC_CLOCK_INVALID")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 < float(timeout_seconds) <= 60
        ):
            raise OkxPublicTransportError("PUBLIC_TIMEOUT_INVALID")
        if (
            type(max_response_bytes) is not int
            or not 1 <= max_response_bytes <= MAX_PUBLIC_RESPONSE_BYTES
        ):
            raise OkxPublicTransportError("PUBLIC_RESPONSE_LIMIT_INVALID")
        self._raw_sink = raw_sink
        self._clock = clock
        self._opener = opener or SystemPublicHttpsOpener()
        self._timeout = float(timeout_seconds)
        self._max_response_bytes = max_response_bytes
        self._attempted: set[tuple[str, str]] = set()
        self._attempt_lock = threading.Lock()

    def _claim_attempt(self, cycle_id: str, capture_id: str) -> None:
        key = (cycle_id, capture_id)
        with self._attempt_lock:
            if key in self._attempted:
                raise OkxPublicTransportError("PUBLIC_REQUEST_ALREADY_ATTEMPTED")
            self._attempted.add(key)

    def _load_recoverable_response(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        component_id: str,
        path: str,
        ordered_query: Mapping[str, str],
        route_policy_id: str,
    ) -> CapturedPublicResponse | None:
        """Replay an already-sealed response before any second network attempt."""

        loader = getattr(self._raw_sink, "load_response", None)
        if not callable(loader):
            return None
        try:
            loaded = loader(cycle_id=cycle_id, capture_id=capture_id)
        except Exception as exc:
            raise OkxPublicTransportError(
                "RAW_CAPTURE_RECOVERY_INVALID"
            ) from exc
        if loaded is None:
            return None
        if not isinstance(loaded, LoadedRawCapture):
            raise OkxPublicTransportError("RAW_CAPTURE_RECOVERY_INVALID")

        payload = loaded.payload
        summary = loaded.summary
        if not isinstance(payload, bytes) or not isinstance(summary, Mapping):
            raise OkxPublicTransportError("RAW_CAPTURE_RECOVERY_INVALID")
        candidate = dict(summary)
        query_value = candidate.get("query")
        if (
            set(candidate) != _CAPTURE_SUMMARY_FIELDS
            or candidate.get("component_id") != component_id
            or candidate.get("method") != "GET"
            or candidate.get("path") != path
            or not isinstance(query_value, Mapping)
            or dict(query_value) != dict(ordered_query)
            or candidate.get("route_policy_id") != route_policy_id
            or type(candidate.get("attempt_number")) is not int
            or candidate.get("attempt_number") != 1
            or candidate.get("retry_allowed") is not False
            or type(candidate.get("response_limit_bytes")) is not int
            or candidate.get("response_limit_bytes")
            != self._max_response_bytes
            or candidate.get("body_truncated")
            is not (len(payload) > self._max_response_bytes)
            or type(candidate.get("http_status")) is not int
            or not isinstance(candidate.get("final_url"), str)
        ):
            raise OkxPublicTransportError("RAW_CAPTURE_RECOVERY_MISMATCH")

        try:
            started = _canonical_time(
                candidate.get("request_started_at"),
                code="RAW_CAPTURE_RECOVERY_MISMATCH",
            )
            received = _canonical_time(
                candidate.get("response_received_at"),
                code="RAW_CAPTURE_RECOVERY_MISMATCH",
            )
            completed = _canonical_time(
                candidate.get("capture_completed_at"),
                code="RAW_CAPTURE_RECOVERY_MISMATCH",
            )
            raw_ref = _validated_raw_ref(
                loaded.raw_ref,
                cycle_id=cycle_id,
                capture_id=capture_id,
                payload=payload,
            )
        except OkxPublicTransportError as exc:
            raise OkxPublicTransportError(
                "RAW_CAPTURE_RECOVERY_MISMATCH"
            ) from exc
        if (
            candidate.get("request_started_at") != started
            or candidate.get("response_received_at") != received
            or candidate.get("capture_completed_at") != completed
            or not (
                _time_order_key(started)
                <= _time_order_key(received)
                <= _time_order_key(completed)
            )
        ):
            raise OkxPublicTransportError("RAW_CAPTURE_RECOVERY_MISMATCH")

        return CapturedPublicResponse(
            component_id=component_id,
            path=path,
            query=dict(ordered_query),
            http_status=int(candidate["http_status"]),
            body=payload,
            request_started_at=started,
            response_received_at=received,
            capture_completed_at=completed,
            final_url=str(candidate["final_url"]),
            raw_ref=raw_ref,
        )

    @staticmethod
    def _prepare_request(
        *,
        cycle_id: str,
        capture_id: str,
        component_id: str,
        path: str,
        query: Mapping[str, str],
    ) -> tuple[urllib.request.Request, str, dict[str, str]]:
        if (
            not isinstance(cycle_id, str)
            or _SAFE_CAPTURE_ID.fullmatch(cycle_id) is None
            or not isinstance(capture_id, str)
            or _SAFE_CAPTURE_ID.fullmatch(capture_id) is None
            or _COMPONENT_PATHS.get(component_id) != path
        ):
            raise OkxPublicTransportError("PUBLIC_CAPTURE_IDENTITY_INVALID")
        return build_public_get_request(path=path, query=query)

    def load_sealed(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        component_id: str,
        path: str,
        query: Mapping[str, str],
    ) -> CapturedPublicResponse | None:
        """Return only a verified sealed response; never read clock or network."""

        _, expected_url, ordered_query = self._prepare_request(
            cycle_id=cycle_id,
            capture_id=capture_id,
            component_id=component_id,
            path=path,
            query=query,
        )
        recovered = self._load_recoverable_response(
            cycle_id=cycle_id,
            capture_id=capture_id,
            component_id=component_id,
            path=path,
            ordered_query=ordered_query,
            route_policy_id=_route_policy_id(self._opener),
        )
        if recovered is None:
            return None
        return _classify_captured_response(
            recovered,
            expected_url=expected_url,
            max_response_bytes=self._max_response_bytes,
        )

    def get_once(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        component_id: str,
        path: str,
        query: Mapping[str, str],
    ) -> CapturedPublicResponse:
        request, expected_url, ordered_query = self._prepare_request(
            cycle_id=cycle_id,
            capture_id=capture_id,
            component_id=component_id,
            path=path,
            query=query,
        )
        route_policy_id = _route_policy_id(self._opener)
        recovered = self._load_recoverable_response(
            cycle_id=cycle_id,
            capture_id=capture_id,
            component_id=component_id,
            path=path,
            ordered_query=ordered_query,
            route_policy_id=route_policy_id,
        )
        if recovered is not None:
            return _classify_captured_response(
                recovered,
                expected_url=expected_url,
                max_response_bytes=self._max_response_bytes,
            )
        durable_claim = getattr(self._raw_sink, "claim_attempt", None)
        if callable(durable_claim):
            try:
                claim_created = durable_claim(
                    cycle_id=cycle_id,
                    capture_id=capture_id,
                    binding=_attempt_binding(
                        component_id=component_id,
                        path=path,
                        ordered_query=ordered_query,
                        route_policy_id=route_policy_id,
                        response_limit_bytes=self._max_response_bytes,
                    ),
                )
            except Exception as exc:
                raise OkxPublicTransportError(
                    "PUBLIC_ATTEMPT_CLAIM_FAILED"
                ) from exc
            if type(claim_created) is not bool:
                raise OkxPublicTransportError(
                    "PUBLIC_ATTEMPT_CLAIM_RESULT_INVALID"
                )
            if not claim_created:
                raise OkxPublicTransportError(
                    "PUBLIC_PREVIOUS_ATTEMPT_INDETERMINATE",
                    coverage_eligible=True,
                )
        self._claim_attempt(cycle_id, capture_id)
        started = _canonical_time(
            self._clock(), code="PUBLIC_REQUEST_TIME_INVALID"
        )
        response: _Response
        try:
            response = self._opener.open(request, timeout=self._timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        except OkxPublicTransportError:
            raise
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError,
        ) as exc:
            failure_code = _physical_failure(exc)
            if failure_code is None:
                raise OkxPublicTransportError(
                    "PUBLIC_TRANSPORT_STRUCTURAL_FAILURE"
                ) from exc
            failure_at = _canonical_time(
                self._clock(), code="PUBLIC_FAILURE_TIME_INVALID"
            )
            raise OkxPublicTransportError(
                failure_code,
                coverage_eligible=True,
                failure_at=failure_at,
            ) from None

        try:
            received = _canonical_time(
                self._clock(), code="PUBLIC_RESPONSE_TIME_INVALID"
            )
            try:
                status = int(response.status)
                final_url = response.geturl()
                raw = response.read(self._max_response_bytes + 1)
            except (
                AttributeError,
                TypeError,
                ValueError,
                http.client.HTTPException,
                OSError,
            ) as exc:
                raise OkxPublicTransportError(
                    "PUBLIC_RESPONSE_BODY_READ_FAILED"
                ) from exc
            completed = _canonical_time(
                self._clock(), code="PUBLIC_CAPTURE_TIME_INVALID"
            )
            if not (
                _time_order_key(started)
                <= _time_order_key(received)
                <= _time_order_key(completed)
            ):
                raise OkxPublicTransportError("PUBLIC_CAPTURE_CHRONOLOGY_INVALID")
            if not isinstance(final_url, str) or not isinstance(raw, bytes):
                raise OkxPublicTransportError("PUBLIC_RESPONSE_STRUCTURAL_FAILURE")
            summary = {
                "component_id": component_id,
                "method": "GET",
                "path": path,
                "query": ordered_query,
                "request_started_at": started,
                "response_received_at": received,
                "capture_completed_at": completed,
                "http_status": status,
                "final_url": final_url,
                "route_policy_id": route_policy_id,
                "attempt_number": 1,
                "retry_allowed": False,
                "response_limit_bytes": self._max_response_bytes,
                "body_truncated": len(raw) > self._max_response_bytes,
            }
            try:
                sealed = self._raw_sink.seal_response(
                    cycle_id=cycle_id,
                    capture_id=capture_id,
                    payload=raw,
                    summary=summary,
                )
            except Exception as exc:
                raise OkxPublicTransportError("RAW_CAPTURE_WRITE_ONCE_FAILED") from exc
            raw_ref = _validated_raw_ref(
                sealed,
                cycle_id=cycle_id,
                capture_id=capture_id,
                payload=raw,
            )

            captured = CapturedPublicResponse(
                component_id=component_id,
                path=path,
                query=ordered_query,
                http_status=status,
                body=raw,
                request_started_at=started,
                response_received_at=received,
                capture_completed_at=completed,
                final_url=final_url,
                raw_ref=raw_ref,
            )
            # All response-dependent classifications happen after the raw body
            # and summary have been atomically published above.
            return _classify_captured_response(
                captured,
                expected_url=expected_url,
                max_response_bytes=self._max_response_bytes,
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()


__all__ = [
    "ALLOWED_PUBLIC_PATHS",
    "ALLOWED_OPTIONAL_PUBLIC_PATHS",
    "CLOSED_CANDLES_15M_PATH",
    "FUNDING_RATE_HISTORY_PATH",
    "CapturedPublicResponse",
    "INSTRUMENT_PATH",
    "MARK_PRICE_PATH",
    "MAX_PUBLIC_RESPONSE_BYTES",
    "OKX_PUBLIC_BASE_URL",
    "OKX_PUBLIC_HOST",
    "OPEN_INTEREST_PATH",
    "ORDER_BOOK_PATH",
    "OkxPublicTransport",
    "OkxPublicTransportError",
    "PUBLIC_REQUEST_HEADERS",
    "PUBLIC_ROUTE_POLICY_ID",
    "RECENT_TRADES_PATH",
    "PublicOpener",
    "SERVER_TIME_PATH",
    "SystemPublicHttpsOpener",
    "build_public_get_request",
]
