"""Shared credential-free public HTTPS route for the V3.2 OKX adapters.

The current local environment may require its system HTTPS proxy for public
Internet access.  This adapter resolves that route lazily, rejects proxy
userinfo before a request is dispatched, disables redirects, and never
exposes the proxy address in its public state or errors.  It does not retry or
fall back to another route.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import threading
from typing import Any, Protocol
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from ..application.v32_public_evidence_port import OKX_PUBLIC_HOST
from ..domain.v32_runtime_support_contracts import (
    V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
    V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
    V32_PUBLIC_REQUEST_HEADERS,
    V32_PUBLIC_REQUEST_HEADERS_DIGEST,
)

_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "ok-access-key",
        "ok-access-passphrase",
        "ok-access-sign",
        "proxy-authorization",
    }
)
_ALLOWED_OKX_PUBLIC_PATHS = frozenset(
    {
        "/api/v5/public/time",
        "/api/v5/public/instruments",
        "/api/v5/market/ticker",
        "/api/v5/public/mark-price",
        "/api/v5/market/history-candles",
        "/api/v5/public/open-interest",
        "/api/v5/public/funding-rate",
        "/api/v5/market/books",
        "/api/v5/market/trades",
    }
)


class V32PublicHttpsRouteError(OSError):
    """A public HTTPS route was unsafe or could not be resolved."""

    def __init__(self, failure_code: str, *, request_dispatched: bool = False) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.request_dispatched = request_dispatched
        self.route_policy_id = V32_PUBLIC_HTTPS_ROUTE_POLICY_ID


def classify_v32_public_https_failure_v1(exc: BaseException) -> str:
    """Classify known public transport failures without using error prose."""

    current: BaseException | object = exc
    url_error = isinstance(current, urllib.error.URLError)
    if url_error and not isinstance(current, urllib.error.HTTPError):
        current = current.reason
    if isinstance(current, V32PublicHttpsRouteError):
        return current.failure_code
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
    if isinstance(current, urllib.error.HTTPError):
        status = int(current.code)
        if 300 <= status < 400:
            return "PUBLIC_REDIRECT_FORBIDDEN"
        if status == 429 or 500 <= status <= 599:
            return "PUBLIC_PROVIDER_UNAVAILABLE"
        return "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE"
    if isinstance(current, (ConnectionError, OSError)) or url_error:
        return "PUBLIC_TRANSPORT_IO_FAILURE"
    return "UNCLASSIFIED_STRUCTURAL_FAILURE"


class _Response(Protocol):
    def __enter__(self) -> "_Response": ...
    def __exit__(self, *args: object) -> None: ...


class _Opener(Protocol):
    def open(
        self, request: urllib.request.Request, timeout: float
    ) -> _Response: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class _FrozenHttpsProxyHandler(urllib.request.ProxyHandler):
    """Apply one validated proxy in the protocol chain without re-bypass."""

    def __init__(self, *, scheme: str, authority: str) -> None:
        self._frozen_scheme = scheme
        self._frozen_authority = authority
        super().__init__({"https": f"{scheme}://{authority}"})

    def proxy_open(self, request, proxy, proxy_type):  # noqa: ANN001
        if (
            proxy_type != "https"
            or request.type != "https"
            or request.host != OKX_PUBLIC_HOST
            or getattr(request, "_tunnel_host", None) is not None
            or proxy
            != f"{self._frozen_scheme}://{self._frozen_authority}"
        ):
            raise V32PublicHttpsRouteError(
                "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_INVALID"
            )
        request.set_proxy(self._frozen_authority, self._frozen_scheme)
        return None


ProxySupplier = Callable[[], Mapping[str, str]]
BypassChecker = Callable[[str], bool]


def _public_okx_request(request: urllib.request.Request) -> None:
    url = request.full_url
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_TARGET_INVALID"
        ) from None
    header_rows = tuple(
        sorted(
            (name.casefold(), value)
            for name, value in request.header_items()
        )
    )
    if (
        request.get_method() != "GET"
        or parsed.scheme != "https"
        or parsed.hostname != OKX_PUBLIC_HOST
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path not in _ALLOWED_OKX_PUBLIC_PATHS
        or len(header_rows) != len(V32_PUBLIC_REQUEST_HEADERS)
        or header_rows != V32_PUBLIC_REQUEST_HEADERS
        or {name for name, _ in header_rows} & _FORBIDDEN_REQUEST_HEADERS
        or request.host != parsed.netloc
        or getattr(request, "_tunnel_host", None) is not None
    ):
        raise V32PublicHttpsRouteError("V32_PUBLIC_HTTPS_TARGET_INVALID")


def build_v32_public_get_request_v1(url: str) -> urllib.request.Request:
    """Build the only V3.2 public GET shape; no caller headers are accepted."""

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "agent-trade-emotion-v3.2-public-research/1.0",
        },
    )
    _public_okx_request(request)
    return request


def _validated_https_proxy(
    proxies: Mapping[str, str], *, bypass_checker: BypassChecker
) -> tuple[str, str] | None:
    if not isinstance(proxies, Mapping):
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_INVALID"
        )
    raw = proxies.get("https")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_INVALID"
        )
    parsed = urllib.parse.urlsplit(raw)
    try:
        port = parsed.port
    except ValueError:
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_INVALID"
        ) from None
    if parsed.username is not None or parsed.password is not None:
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_PROXY_CREDENTIALS_FORBIDDEN"
        )
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_INVALID"
        )
    try:
        bypassed = bypass_checker(OKX_PUBLIC_HOST)
    except Exception:
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_INVALID"
        ) from None
    if bypassed is not False:
        raise V32PublicHttpsRouteError(
            "V32_PUBLIC_HTTPS_PROXY_BYPASS_FORBIDDEN"
        )
    return parsed.scheme, parsed.netloc


class V32SystemPublicHttpsOpener:
    """Lazily resolve one system public-HTTPS route with no fallback."""

    route_policy_id = V32_PUBLIC_HTTPS_ROUTE_POLICY_ID

    def __init__(
        self,
        *,
        proxy_supplier: ProxySupplier = urllib.request.getproxies,
        bypass_checker: BypassChecker = urllib.request.proxy_bypass,
    ) -> None:
        if not callable(proxy_supplier) or not callable(bypass_checker):
            raise V32PublicHttpsRouteError(
                "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_INVALID"
            )
        self._proxy_supplier = proxy_supplier
        self._bypass_checker = bypass_checker
        self._opener: _Opener | None = None
        self._proxy_target: tuple[str, str] | None = None
        self._route_mode: str | None = None
        self._lock = threading.Lock()

    @property
    def route_mode(self) -> str:
        return self._route_mode or "NOT_RESOLVED"

    def _resolve(self) -> _Opener:
        if self._opener is not None:
            return self._opener
        with self._lock:
            if self._opener is not None:
                return self._opener
            try:
                proxies = self._proxy_supplier()
            except Exception:
                raise V32PublicHttpsRouteError(
                    "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_UNAVAILABLE"
                ) from None
            proxy_target = _validated_https_proxy(
                proxies, bypass_checker=self._bypass_checker
            )
            proxy_handler: urllib.request.ProxyHandler
            if proxy_target is None:
                proxy_handler = urllib.request.ProxyHandler({})
            else:
                scheme, authority = proxy_target
                proxy_handler = _FrozenHttpsProxyHandler(
                    scheme=scheme, authority=authority
                )
            self._opener = urllib.request.build_opener(
                proxy_handler,
                _NoRedirect(),
                urllib.request.HTTPSHandler(),
            )
            self._proxy_target = proxy_target
            self._route_mode = (
                "DIRECT_NO_SYSTEM_HTTPS_PROXY"
                if proxy_target is None
                else "SYSTEM_HTTPS_PROXY_NON_CREDENTIAL"
            )
            return self._opener

    def open(
        self, request: urllib.request.Request, timeout: float
    ) -> Any:
        _public_okx_request(request)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < float(timeout) <= 60
        ):
            raise V32PublicHttpsRouteError("V32_PUBLIC_HTTPS_TIMEOUT_INVALID")
        opener = self._resolve()
        return opener.open(request, timeout=float(timeout))


__all__ = [
    "V32_PUBLIC_HTTPS_ROUTE_POLICY_ID",
    "V32_PUBLIC_REQUEST_HEADER_POLICY_ID",
    "V32_PUBLIC_REQUEST_HEADERS",
    "V32_PUBLIC_REQUEST_HEADERS_DIGEST",
    "V32PublicHttpsRouteError",
    "V32SystemPublicHttpsOpener",
    "build_v32_public_get_request_v1",
    "classify_v32_public_https_failure_v1",
]
