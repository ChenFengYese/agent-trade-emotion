"""Read-only collection from the official Binance USD-M public API.

This adapter deliberately exposes only three unauthenticated market-data
endpoints.  It never accepts credentials and never constructs an order or
account endpoint.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit

from ...domain.contracts.canonical import canonical_digest
from .model import (
    CollectedPublicResponses,
    PublicRequestCapture,
    require_utc,
)


BINANCE_USDM_BASE_URL = "https://fapi.binance.com"
_ALLOWED_PATHS = frozenset(
    {
        "/fapi/v1/time",
        "/fapi/v1/exchangeInfo",
        "/fapi/v1/klines",
        "/fapi/v1/fundingRate",
    }
)
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_HOUR_MS = 3_600_000
FORMAL_REQUESTED_CLOSED_BAR_COUNT = 256


class BinanceUsdmCollectionError(ValueError):
    """A fail-closed public collection error."""


@dataclass(frozen=True, slots=True)
class HttpCapture:
    status: int
    headers: Mapping[str, str]
    body: bytes
    received_at: datetime
    final_url: str

    def __post_init__(self) -> None:
        require_utc(self.received_at)
        if (
            self.status < 100
            or self.status > 599
            or not isinstance(self.body, bytes)
            or len(self.body) > _MAX_RESPONSE_BYTES
        ):
            raise BinanceUsdmCollectionError("EVIDENCE_LINEAGE_INVALID")


class PublicHttpTransport(Protocol):
    """Small injectable boundary for a public, credential-free HTTP GET."""

    def get(self, url: str, timeout: float) -> HttpCapture:
        ...


def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "fapi.binance.com"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path not in _ALLOWED_PATHS
    ):
        raise BinanceUsdmCollectionError("EVIDENCE_SOURCE_UNREGISTERED")


class UrllibPublicHttpTransport:
    """Standard-library transport restricted to Binance public market data."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if max_response_bytes < 1 or max_response_bytes > _MAX_RESPONSE_BYTES:
            raise BinanceUsdmCollectionError("EVIDENCE_LINEAGE_INVALID")
        self._max_response_bytes = max_response_bytes

    def get(self, url: str, timeout: float) -> HttpCapture:
        _validate_public_url(url)
        if timeout <= 0:
            raise BinanceUsdmCollectionError("EVIDENCE_LINEAGE_INVALID")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "agent-trade-emotion-e0-research/2",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                final_url = response.geturl()
                _validate_public_url(final_url)
                # Redirects are rejected even when they remain on the allowlist:
                # the committed request identity must match the bytes retrieved.
                if final_url != url:
                    raise BinanceUsdmCollectionError(
                        "EVIDENCE_LINEAGE_INVALID"
                    )
                body = response.read(self._max_response_bytes + 1)
                if len(body) > self._max_response_bytes:
                    raise BinanceUsdmCollectionError(
                        "EVIDENCE_LINEAGE_INVALID"
                    )
                received_at = self._clock()
                require_utc(received_at)
                return HttpCapture(
                    status=int(response.status),
                    headers={key: value for key, value in response.headers.items()},
                    body=body,
                    received_at=received_at,
                    final_url=final_url,
                )
        except BinanceUsdmCollectionError:
            raise
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            raise BinanceUsdmCollectionError(
                "EVIDENCE_SOURCE_UNAVAILABLE"
            ) from exc


def _decode_json_any(raw: bytes) -> object:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BinanceUsdmCollectionError("JSON_UTF8_INVALID") from exc

    def reject_float(_: str) -> None:
        raise BinanceUsdmCollectionError("BINARY_FLOAT_FORBIDDEN")

    def reject_constant(_: str) -> None:
        raise BinanceUsdmCollectionError("NONFINITE_NUMBER_FORBIDDEN")

    def unique_object(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise BinanceUsdmCollectionError("JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except BinanceUsdmCollectionError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise BinanceUsdmCollectionError("JSON_INVALID") from exc


def _selected_headers(
    headers: Mapping[str, str],
) -> tuple[tuple[str, str], ...]:
    wanted = {
        "content-type",
        "date",
        "server",
        "x-mbx-used-weight-1m",
    }
    selected: dict[str, str] = {}
    for name, value in headers.items():
        lowered = name.strip().lower()
        if lowered in wanted:
            selected[lowered] = value.strip()
    return tuple(sorted(selected.items()))


def _request_identity_payload(
    *,
    path: str,
    query: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    return {
        "method": "GET",
        "base_url": BINANCE_USDM_BASE_URL,
        "path": path,
        "query": [
            {"name": name, "value": value} for name, value in query
        ],
    }


class BinanceUsdmFreshCollector:
    """Collect one coherent BTCUSDT 1h public-market snapshot."""

    def __init__(
        self,
        *,
        transport: PublicHttpTransport | None = None,
        clock: Callable[[], datetime] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._transport = transport or UrllibPublicHttpTransport(
            clock=self._clock
        )
        if timeout <= 0:
            raise BinanceUsdmCollectionError("EVIDENCE_LINEAGE_INVALID")
        self._timeout = timeout

    def _get(
        self,
        *,
        request_id: str,
        path: str,
        query_items: Mapping[str, str | int] | None = None,
    ) -> tuple[PublicRequestCapture, bytes]:
        if path not in _ALLOWED_PATHS:
            raise BinanceUsdmCollectionError(
                "EVIDENCE_SOURCE_UNREGISTERED"
            )
        query = tuple(
            sorted(
                (str(name), str(value))
                for name, value in (query_items or {}).items()
            )
        )
        query_string = urlencode(query)
        url = f"{BINANCE_USDM_BASE_URL}{path}"
        if query_string:
            url = f"{url}?{query_string}"
        _validate_public_url(url)
        started_at = self._clock()
        require_utc(started_at)
        response = self._transport.get(url, self._timeout)
        _validate_public_url(response.final_url)
        if response.final_url != url:
            raise BinanceUsdmCollectionError("EVIDENCE_LINEAGE_INVALID")
        if response.received_at < started_at:
            raise BinanceUsdmCollectionError("CLOCK_TIME_INVALID")
        if response.status != 200:
            raise BinanceUsdmCollectionError(
                f"EVIDENCE_SOURCE_HTTP_STATUS:{response.status}"
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
            raise BinanceUsdmCollectionError(
                "EVIDENCE_SOURCE_CONTENT_TYPE_INVALID"
            )
        # The final URL must carry the same exact normalized query identity.
        parsed_query = tuple(sorted(parse_qsl(urlsplit(url).query)))
        if parsed_query != query:
            raise BinanceUsdmCollectionError("EVIDENCE_LINEAGE_INVALID")
        selected_headers = _selected_headers(response.headers)
        raw_digest = hashlib.sha256(response.body).hexdigest()
        identity_digest = canonical_digest(
            _request_identity_payload(path=path, query=query)
        )
        header_digest = canonical_digest(
            [
                {"name": name, "value": value}
                for name, value in selected_headers
            ]
        )
        capture = PublicRequestCapture(
            request_id=request_id,
            method="GET",
            base_url=BINANCE_USDM_BASE_URL,
            path=path,
            query=query,
            request_started_at=started_at,
            response_received_at=response.received_at,
            final_url=response.final_url,
            http_status=response.status,
            selected_response_headers=selected_headers,
            response_headers_digest=header_digest,
            raw_body_sha256=raw_digest,
            raw_body_byte_length=len(response.body),
            request_identity_digest=identity_digest,
            record_digest="0" * 64,
        )
        record_payload = capture.to_dict()
        record_payload.pop("record_digest")
        return (
            replace(
                capture,
                record_digest=canonical_digest(record_payload),
            ),
            response.body,
        )

    def collect(
        self,
        *,
        requested_closed_bar_count: int = FORMAL_REQUESTED_CLOSED_BAR_COUNT,
    ) -> CollectedPublicResponses:
        if requested_closed_bar_count != FORMAL_REQUESTED_CLOSED_BAR_COUNT:
            raise BinanceUsdmCollectionError(
                "EVIDENCE_LINEAGE_INVALID"
            )
        server_capture, server_raw = self._get(
            request_id="binance-usdm-server-time",
            path="/fapi/v1/time",
        )
        server_payload = _decode_json_any(server_raw)
        if (
            not isinstance(server_payload, dict)
            or set(server_payload) != {"serverTime"}
            or not isinstance(server_payload["serverTime"], int)
            or isinstance(server_payload["serverTime"], bool)
            or server_payload["serverTime"] <= 0
        ):
            raise BinanceUsdmCollectionError(
                "EVIDENCE_LINEAGE_INVALID"
            )
        server_time_ms = server_payload["serverTime"]
        exchange_capture, exchange_raw = self._get(
            request_id="binance-usdm-exchange-info",
            path="/fapi/v1/exchangeInfo",
        )
        current_hour_open_ms = (server_time_ms // _HOUR_MS) * _HOUR_MS
        closed_end_time_ms = current_hour_open_ms - 1
        start_time_ms = (
            current_hour_open_ms
            - requested_closed_bar_count * _HOUR_MS
        )
        klines_capture, klines_raw = self._get(
            request_id="binance-usdm-btcusdt-1h-klines",
            path="/fapi/v1/klines",
            query_items={
                "endTime": closed_end_time_ms,
                "interval": "1h",
                "limit": requested_closed_bar_count,
                "startTime": start_time_ms,
                "symbol": "BTCUSDT",
            },
        )
        # Syntax/root checks happen before bytes are accepted into the bundle.
        exchange_payload = _decode_json_any(exchange_raw)
        klines_payload = _decode_json_any(klines_raw)
        if not isinstance(exchange_payload, dict) or not isinstance(
            klines_payload, list
        ):
            raise BinanceUsdmCollectionError(
                "EVIDENCE_LINEAGE_INVALID"
            )
        return CollectedPublicResponses(
            server_time=server_capture,
            exchange_info=exchange_capture,
            klines=klines_capture,
            raw_body_by_request_id={
                server_capture.request_id: server_raw,
                exchange_capture.request_id: exchange_raw,
                klines_capture.request_id: klines_raw,
            },
        )

    def collect_funding_history(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1000,
    ) -> tuple[PublicRequestCapture, bytes]:
        """Collect bounded, public BTCUSDT funding settlements.

        This remains separate from ``collect`` so the existing three-response
        bundle stays byte-compatible.  The method accepts neither credentials
        nor account/order parameters.
        """

        if (
            not isinstance(start_time_ms, int)
            or isinstance(start_time_ms, bool)
            or not isinstance(end_time_ms, int)
            or isinstance(end_time_ms, bool)
            or start_time_ms < 0
            or end_time_ms < start_time_ms
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > 1000
        ):
            raise BinanceUsdmCollectionError("EVIDENCE_LINEAGE_INVALID")
        return self._get(
            request_id="binance-usdm-btcusdt-funding-history",
            path="/fapi/v1/fundingRate",
            query_items={
                "endTime": end_time_ms,
                "limit": limit,
                "startTime": start_time_ms,
                "symbol": "BTCUSDT",
            },
        )


__all__ = [
    "BINANCE_USDM_BASE_URL",
    "BinanceUsdmCollectionError",
    "BinanceUsdmFreshCollector",
    "FORMAL_REQUESTED_CLOSED_BAR_COUNT",
    "HttpCapture",
    "PublicHttpTransport",
    "UrllibPublicHttpTransport",
]
