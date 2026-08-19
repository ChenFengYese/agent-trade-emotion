"""Read-only collection from OKX official public market-data endpoints."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit

from ...domain.contracts.canonical import canonical_digest
from .binance_usdm import HttpCapture, PublicHttpTransport
from .model import CollectedPublicResponses, PublicRequestCapture, require_utc


OKX_PUBLIC_BASE_URL = "https://www.okx.com"
OKX_INSTRUMENT_ID = "BTC-USDT-SWAP"
FORMAL_REQUESTED_CLOSED_BAR_COUNT = 256
_HOUR_MS = 3_600_000
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_ALLOWED_PATHS = frozenset(
    {
        "/api/v5/public/time",
        "/api/v5/public/instruments",
        "/api/v5/market/ticker",
        "/api/v5/market/index-tickers",
        "/api/v5/market/books",
        "/api/v5/market/trades",
        "/api/v5/market/candles",
        "/api/v5/market/history-candles",
        "/api/v5/public/mark-price",
        "/api/v5/public/open-interest",
        "/api/v5/public/funding-rate",
        "/api/v5/public/funding-rate-history",
        "/api/v5/public/liquidation-orders",
        "/api/v5/rubik/stat/contracts/open-interest-history",
        "/api/v5/rubik/stat/contracts/long-short-account-ratio",
        "/api/v5/rubik/stat/taker-volume",
    }
)


class OkxPublicCollectionError(ValueError):
    """A fail-closed OKX public collection error."""


class _PublicOpener(Protocol):
    def open(self, request: urllib.request.Request, timeout: float) -> Any: ...


def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.okx.com"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path not in _ALLOWED_PATHS
    ):
        raise OkxPublicCollectionError("EVIDENCE_SOURCE_UNREGISTERED")


class OkxUrllibPublicHttpTransport:
    """Standard-library transport restricted to OKX public market data."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
        opener: _PublicOpener | None = None,
        capture_http_errors: bool = False,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if max_response_bytes < 1 or max_response_bytes > _MAX_RESPONSE_BYTES:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        self._max_response_bytes = max_response_bytes
        self._opener = opener
        if not isinstance(capture_http_errors, bool):
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        self._capture_http_errors = capture_http_errors

    def get(self, url: str, timeout: float) -> HttpCapture:
        _validate_public_url(url)
        if timeout <= 0:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "agent-trade-emotion-offline-research/2",
            },
        )
        try:
            opened = (
                urllib.request.urlopen(request, timeout=timeout)
                if self._opener is None
                else self._opener.open(request, timeout=timeout)
            )
            with opened as response:
                final_url = response.geturl()
                body = response.read(self._max_response_bytes + 1)
                if len(body) > self._max_response_bytes:
                    raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
                received_at = self._clock()
                require_utc(received_at)
                if not self._capture_http_errors:
                    _validate_public_url(final_url)
                    if final_url != url:
                        raise OkxPublicCollectionError(
                            "EVIDENCE_LINEAGE_INVALID"
                        )
                return HttpCapture(
                    status=int(response.status),
                    headers={key: value for key, value in response.headers.items()},
                    body=body,
                    received_at=received_at,
                    final_url=final_url,
                )
        except urllib.error.HTTPError as exc:
            if not self._capture_http_errors:
                raise OkxPublicCollectionError(
                    "EVIDENCE_SOURCE_UNAVAILABLE"
                ) from None
            body = exc.read(self._max_response_bytes + 1)
            if len(body) > self._max_response_bytes:
                raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID") from None
            received_at = self._clock()
            require_utc(received_at)
            return HttpCapture(
                status=int(exc.code),
                headers={
                    key: value
                    for key, value in (
                        exc.headers.items() if exc.headers is not None else ()
                    )
                },
                body=body,
                received_at=received_at,
                final_url=exc.geturl(),
            )
        except OkxPublicCollectionError:
            raise
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            raise OkxPublicCollectionError("EVIDENCE_SOURCE_UNAVAILABLE") from exc


class OkxCurlPublicHttpTransport:
    """Curl fallback with the same public-host/path allowlist and byte cap."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        curl_path: str = "/usr/bin/curl",
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if (
            curl_path != "/usr/bin/curl"
            or not os.path.isfile(curl_path)
            or not os.access(curl_path, os.X_OK)
            or max_response_bytes < 1
            or max_response_bytes > _MAX_RESPONSE_BYTES
        ):
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        self._curl_path = curl_path
        self._max_response_bytes = max_response_bytes

    @staticmethod
    def _headers(raw: bytes) -> dict[str, str]:
        blocks = [block for block in raw.replace(b"\r\n", b"\n").split(b"\n\n") if block.strip()]
        selected = next(
            (block for block in reversed(blocks) if block.startswith(b"HTTP/")),
            b"",
        )
        output: dict[str, str] = {}
        for line in selected.splitlines()[1:]:
            if b":" not in line:
                continue
            name, value = line.split(b":", 1)
            try:
                output[name.decode("ascii").strip()] = value.decode("utf-8").strip()
            except UnicodeError:
                continue
        return output

    def get(self, url: str, timeout: float) -> HttpCapture:
        _validate_public_url(url)
        if timeout <= 0 or timeout > 60:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        with tempfile.TemporaryDirectory(prefix="okx-public-curl-") as directory:
            body_path = os.path.join(directory, "body")
            header_path = os.path.join(directory, "headers")
            marker = "__OKX_CAPTURE__"
            command = [
                self._curl_path,
                "--silent",
                "--show-error",
                "--http1.1",
                "--request",
                "GET",
                "--header",
                "Accept: application/json",
                "--user-agent",
                "agent-trade-emotion-offline-research/2",
                "--connect-timeout",
                str(min(timeout, 15.0)),
                "--max-time",
                str(timeout),
                "--max-filesize",
                str(self._max_response_bytes),
                "--dump-header",
                header_path,
                "--output",
                body_path,
                "--write-out",
                f"{marker}%{{http_code}}|%{{url_effective}}",
                url,
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout + 5,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise OkxPublicCollectionError(
                    f"EVIDENCE_SOURCE_UNAVAILABLE:CURL_PROCESS:{type(exc).__name__}"
                ) from exc
            if completed.returncode != 0:
                try:
                    detail = " ".join(
                        completed.stderr.decode("utf-8", errors="replace").split()
                    )[:400]
                except Exception:
                    detail = "STDERR_UNREADABLE"
                raise OkxPublicCollectionError(
                    f"EVIDENCE_SOURCE_UNAVAILABLE:CURL_EXIT_{completed.returncode}:"
                    f"{detail or 'NO_STDERR'}"
                )
            try:
                metadata = completed.stdout.decode("utf-8")
                if not metadata.startswith(marker):
                    raise ValueError
                status_raw, final_url = metadata.removeprefix(marker).split("|", 1)
                status = int(status_raw)
                with open(body_path, "rb") as body_handle:
                    body = body_handle.read(self._max_response_bytes + 1)
                with open(header_path, "rb") as header_handle:
                    headers_raw = header_handle.read(256 * 1024)
            except (OSError, UnicodeError, ValueError) as exc:
                raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID") from exc
            if len(body) > self._max_response_bytes:
                raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
            final_url = final_url.strip()
            _validate_public_url(final_url)
            if final_url != url:
                raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
            received_at = self._clock()
            require_utc(received_at)
            return HttpCapture(
                status=status,
                headers=self._headers(headers_raw),
                body=body,
                received_at=received_at,
                final_url=final_url,
            )


def _decode_json(raw: bytes) -> object:
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OkxPublicCollectionError("JSON_UTF8_INVALID") from exc

    def reject_float(_: str) -> None:
        raise OkxPublicCollectionError("BINARY_FLOAT_FORBIDDEN")

    def reject_constant(_: str) -> None:
        raise OkxPublicCollectionError("NONFINITE_NUMBER_FORBIDDEN")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, value in pairs:
            if key in output:
                raise OkxPublicCollectionError("JSON_DUPLICATE_KEY")
            output[key] = value
        return output

    try:
        return json.loads(
            source,
            object_pairs_hook=unique,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except OkxPublicCollectionError:
        raise
    except json.JSONDecodeError as exc:
        raise OkxPublicCollectionError("JSON_INVALID") from exc


def _selected_headers(headers: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    wanted = {"content-type", "date", "server", "x-ratelimit-limit"}
    selected = {
        name.strip().lower(): value.strip()
        for name, value in headers.items()
        if name.strip().lower() in wanted
    }
    return tuple(sorted(selected.items()))


def _request_identity_payload(
    *, path: str, query: tuple[tuple[str, str], ...]
) -> dict[str, object]:
    return {
        "method": "GET",
        "base_url": OKX_PUBLIC_BASE_URL,
        "path": path,
        "query": [{"name": name, "value": value} for name, value in query],
    }


class OkxPublicFreshCollector:
    """Collect one coherent normalized-input snapshot for BTC-USDT-SWAP."""

    def __init__(
        self,
        *,
        transport: PublicHttpTransport | None = None,
        clock: Callable[[], datetime] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._transport = transport or OkxUrllibPublicHttpTransport(clock=self._clock)
        if timeout <= 0:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        self._timeout = timeout

    def _get(
        self,
        *,
        request_id: str,
        path: str,
        query_items: Mapping[str, str | int] | None = None,
    ) -> tuple[PublicRequestCapture, bytes]:
        if path not in _ALLOWED_PATHS:
            raise OkxPublicCollectionError("EVIDENCE_SOURCE_UNREGISTERED")
        query = tuple(
            sorted(
                (str(name), str(value))
                for name, value in (query_items or {}).items()
            )
        )
        url = f"{OKX_PUBLIC_BASE_URL}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        _validate_public_url(url)
        started_at = self._clock()
        require_utc(started_at)
        response = self._transport.get(url, self._timeout)
        _validate_public_url(response.final_url)
        if response.final_url != url or response.received_at < started_at:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        if response.status != 200:
            raise OkxPublicCollectionError(
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
            raise OkxPublicCollectionError("EVIDENCE_SOURCE_CONTENT_TYPE_INVALID")
        if tuple(sorted(parse_qsl(urlsplit(url).query))) != query:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        selected_headers = _selected_headers(response.headers)
        capture = PublicRequestCapture(
            request_id=request_id,
            method="GET",
            base_url=OKX_PUBLIC_BASE_URL,
            path=path,
            query=query,
            request_started_at=started_at,
            response_received_at=response.received_at,
            final_url=response.final_url,
            http_status=response.status,
            selected_response_headers=selected_headers,
            response_headers_digest=canonical_digest(
                [
                    {"name": name, "value": value}
                    for name, value in selected_headers
                ]
            ),
            raw_body_sha256=hashlib.sha256(response.body).hexdigest(),
            raw_body_byte_length=len(response.body),
            request_identity_digest=canonical_digest(
                _request_identity_payload(path=path, query=query)
            ),
            record_digest="0" * 64,
        )
        payload = capture.to_dict()
        payload.pop("record_digest")
        return replace(capture, record_digest=canonical_digest(payload)), response.body

    def collect(
        self,
        *,
        requested_closed_bar_count: int = FORMAL_REQUESTED_CLOSED_BAR_COUNT,
    ) -> CollectedPublicResponses:
        if requested_closed_bar_count != FORMAL_REQUESTED_CLOSED_BAR_COUNT:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        server_capture, server_raw = self._get(
            request_id="okx-public-server-time", path="/api/v5/public/time"
        )
        root = _decode_json(server_raw)
        if (
            not isinstance(root, dict)
            or root.get("code") != "0"
            or root.get("msg") != ""
            or not isinstance(root.get("data"), list)
            or len(root["data"]) != 1
            or not isinstance(root["data"][0], dict)
            or not isinstance(root["data"][0].get("ts"), str)
        ):
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        try:
            server_time_ms = int(root["data"][0]["ts"])
        except ValueError as exc:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID") from exc
        if server_time_ms <= 0:
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        exchange_capture, exchange_raw = self._get(
            request_id="okx-public-btc-usdt-swap-instrument",
            path="/api/v5/public/instruments",
            query_items={"instId": OKX_INSTRUMENT_ID, "instType": "SWAP"},
        )
        current_hour_open_ms = (server_time_ms // _HOUR_MS) * _HOUR_MS
        klines_capture, klines_raw = self._get(
            request_id="okx-public-btc-usdt-swap-1h-candles",
            path="/api/v5/market/history-candles",
            query_items={
                "after": current_hour_open_ms,
                "bar": "1H",
                "instId": OKX_INSTRUMENT_ID,
                "limit": requested_closed_bar_count,
            },
        )
        for raw in (exchange_raw, klines_raw):
            payload = _decode_json(raw)
            if (
                not isinstance(payload, dict)
                or payload.get("code") != "0"
                or not isinstance(payload.get("data"), list)
            ):
                raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
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
        self, *, start_time_ms: int, end_time_ms: int, limit: int = 400
    ) -> tuple[PublicRequestCapture, bytes]:
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
            or limit > 400
        ):
            raise OkxPublicCollectionError("EVIDENCE_LINEAGE_INVALID")
        return self._get(
            request_id="okx-public-btc-usdt-swap-funding-history",
            path="/api/v5/public/funding-rate-history",
            query_items={
                "after": end_time_ms + 1,
                "instId": OKX_INSTRUMENT_ID,
                "limit": limit,
            },
        )


__all__ = [
    "OKX_INSTRUMENT_ID",
    "OKX_PUBLIC_BASE_URL",
    "OkxPublicCollectionError",
    "OkxCurlPublicHttpTransport",
    "OkxPublicFreshCollector",
    "OkxUrllibPublicHttpTransport",
]
