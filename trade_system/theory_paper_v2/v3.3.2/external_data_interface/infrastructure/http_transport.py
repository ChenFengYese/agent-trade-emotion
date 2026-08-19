"""No-retry HTTPS transport plus the finite WSS transport."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
from typing import Mapping
import urllib.error
import urllib.parse
import urllib.request

from ..application.ports import (
    HttpRequest,
    TransportRequest,
    TransportResponse,
    WebSocketRequest,
)
from .websocket_transport import execute_websocket


_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "date", "etag", "last-modified", "server"}
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _headers(values: Mapping[str, str]) -> dict[str, str]:
    return {
        name.lower(): value
        for name, value in values.items()
        if name.lower() in _RESPONSE_HEADERS
    }


def _read_bounded(response, limit: int) -> tuple[bytes, str | None]:  # noqa: ANN001
    body = response.read(limit + 1)
    if len(body) > limit:
        return body, "V332_HTTP_RESPONSE_TOO_LARGE"
    return body, None


def _network_failure(exc: BaseException) -> str:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLError):
        return "V332_HTTP_TLS_FAILURE"
    if isinstance(reason, socket.gaierror):
        return "V332_HTTP_DNS_FAILURE"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "V332_HTTP_TIMEOUT"
    return "V332_HTTP_CONNECTION_FAILURE"


class HttpsTransport:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("V332_HTTP_TIMEOUT_INVALID")
        self._timeout = timeout_seconds
        self._opener = urllib.request.build_opener(_NoRedirect())

    def execute(self, request: HttpRequest) -> TransportResponse:
        parsed = urllib.parse.urlsplit(request.url)
        stored = urllib.parse.urlsplit(request.stored_url)
        if (
            parsed.scheme != "https"
            or stored.scheme != "https"
            or not parsed.hostname
            or not stored.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or request.method not in {"GET", "POST"}
            or request.max_bytes <= 0
        ):
            raise ValueError("V332_HTTP_REQUEST_INVALID")
        started_at = _now()
        response_at = started_at
        body = b""
        status: int | None = None
        final_url = request.url
        response_headers: dict[str, str] = {}
        error_code: str | None = None
        try:
            message = urllib.request.Request(
                request.url,
                data=request.body,
                headers=dict(request.headers),
                method=request.method,
            )
            response = self._opener.open(message, timeout=self._timeout)
            try:
                response_at = _now()
                status = int(response.status)
                final_url = response.geturl()
                response_headers = _headers(response.headers)
                body, error_code = _read_bounded(response, request.max_bytes)
            finally:
                response.close()
        except urllib.error.HTTPError as exc:
            response_at = _now()
            status = int(exc.code)
            final_url = exc.geturl()
            response_headers = _headers(exc.headers)
            body, size_error = _read_bounded(exc, request.max_bytes)
            error_code = size_error or f"V332_HTTP_STATUS_{status}"
            exc.close()
        except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            error_code = _network_failure(exc)
        completed_at = _now()
        stored_final_url = request.stored_url if final_url == request.url else "REDIRECTED_REDACTED"
        return TransportResponse(
            protocol="HTTP",
            status_code=status,
            final_url=final_url,
            stored_url=stored_final_url,
            headers=response_headers,
            body=body,
            request_started_at=started_at,
            response_received_at=response_at,
            capture_completed_at=completed_at,
            error_code=error_code,
            backend="python-urllib",
        )


def _curl_error(returncode: int) -> str:
    if returncode == 6:
        return "V332_HTTP_DNS_FAILURE"
    if returncode == 28:
        return "V332_HTTP_TIMEOUT"
    if returncode in {35, 51, 58, 60}:
        return "V332_HTTP_TLS_FAILURE"
    if returncode == 63:
        return "V332_HTTP_RESPONSE_TOO_LARGE"
    return "V332_HTTP_CONNECTION_FAILURE"


def _curl_headers(payload: bytes) -> tuple[int | None, dict[str, str]]:
    status: int | None = None
    result: dict[str, str] = {}
    try:
        text = payload.decode("iso-8859-1")
    except UnicodeDecodeError:
        return None, {}
    current: dict[str, str] = {}
    current_status: int | None = None
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if line.startswith("HTTP/"):
            parts = line.split()
            try:
                current_status = int(parts[1])
            except (IndexError, ValueError):
                current_status = None
            current = {}
            continue
        if not line:
            if current_status is not None and current_status != 200:
                status = current_status
                result = current
            elif current_status is not None:
                status = current_status
                result = current
            continue
        if ":" in line:
            name, value = line.split(":", 1)
            current[name.strip().lower()] = value.strip()
    if current_status is not None:
        status = current_status
        result = current
    return status, _headers(result)


class CurlHttpsTransport:
    """Single-attempt curl backend for public requests on proxy-sensitive hosts."""

    def __init__(self, executable: str, *, timeout_seconds: float) -> None:
        self._executable = executable
        self._timeout = timeout_seconds

    def execute(self, request: HttpRequest) -> TransportResponse:
        if request.url != request.stored_url or dict(request.headers) != dict(request.stored_headers):
            raise ValueError("V332_CURL_SECRET_REQUEST_PROHIBITED")
        for name, value in request.headers.items():
            if any(character in str(name) + str(value) for character in ("\r", "\n")):
                raise ValueError("V332_CURL_HEADER_INVALID")
        descriptor, header_name = tempfile.mkstemp(prefix="v332-curl-headers-")
        os.close(descriptor)
        header_path = Path(header_name)
        started_at = _now()
        args = [
            self._executable,
            "--silent",
            "--show-error",
            "--max-time",
            str(self._timeout),
            "--connect-timeout",
            str(min(10.0, self._timeout)),
            "--proto",
            "=https",
            "--max-filesize",
            str(request.max_bytes),
            "--request",
            request.method,
            "--dump-header",
            str(header_path),
            "--url",
            request.url,
        ]
        for name, value in sorted(request.headers.items()):
            args.extend(("--header", f"{name}: {value}"))
        if request.body is not None:
            args.extend(("--data-binary", "@-"))
        try:
            completed = subprocess.run(
                args,
                input=request.body,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self._timeout + 3.0,
            )
            response_at = _now()
            header_payload = header_path.read_bytes()
            status, response_headers = _curl_headers(header_payload)
            body = completed.stdout
            error_code = None if completed.returncode == 0 else _curl_error(completed.returncode)
            if len(body) > request.max_bytes:
                body = body[: request.max_bytes + 1]
                error_code = "V332_HTTP_RESPONSE_TOO_LARGE"
        except subprocess.TimeoutExpired as exc:
            response_at = _now()
            status = None
            response_headers = {}
            body = bytes(exc.stdout or b"")
            error_code = "V332_HTTP_TIMEOUT"
        finally:
            header_path.unlink(missing_ok=True)
        completed_at = _now()
        return TransportResponse(
            protocol="HTTP",
            status_code=status,
            final_url=request.url,
            stored_url=request.stored_url,
            headers=response_headers,
            body=body,
            request_started_at=started_at,
            response_received_at=response_at,
            capture_completed_at=completed_at,
            error_code=error_code,
            backend="curl-public-no-secret",
        )


class CompositeTransport:
    """Route only by the public transport contract type."""

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self._http = HttpsTransport(timeout_seconds=timeout_seconds)
        executable = shutil.which("curl")
        self._curl = (
            CurlHttpsTransport(executable, timeout_seconds=timeout_seconds)
            if executable
            else None
        )

    def execute(self, request: TransportRequest) -> TransportResponse:
        if isinstance(request, HttpRequest):
            if (
                self._curl is not None
                and request.url == request.stored_url
                and dict(request.headers) == dict(request.stored_headers)
            ):
                return self._curl.execute(request)
            return self._http.execute(request)
        if isinstance(request, WebSocketRequest):
            return execute_websocket(request)
        raise TypeError("V332_TRANSPORT_REQUEST_UNSUPPORTED")


__all__ = ["CompositeTransport", "CurlHttpsTransport", "HttpsTransport"]
