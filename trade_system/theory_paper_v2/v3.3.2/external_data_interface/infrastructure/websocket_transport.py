"""Small dependency-free WSS client for finite public capture windows."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import os
import socket
import ssl
import struct
import time
from typing import Iterable, Mapping
import urllib.parse

from ..application.ports import TransportResponse, WebSocketRequest


_MAGIC = b"ATE-V332-WS-MESSAGES-1\n"
_MAX_HANDSHAKE_BYTES = 64 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def pack_messages(messages: Iterable[tuple[int, bytes]]) -> bytes:
    output = bytearray(_MAGIC)
    for opcode, payload in messages:
        if opcode not in {1, 2}:
            raise ValueError("V332_WS_MESSAGE_OPCODE_INVALID")
        output.extend(struct.pack("!BQ", opcode, len(payload)))
        output.extend(payload)
    return bytes(output)


def unpack_messages(payload: bytes) -> tuple[tuple[int, bytes], ...]:
    if not payload.startswith(_MAGIC):
        raise ValueError("V332_WS_CONTAINER_INVALID")
    cursor = len(_MAGIC)
    messages: list[tuple[int, bytes]] = []
    while cursor < len(payload):
        if len(payload) - cursor < 9:
            raise ValueError("V332_WS_CONTAINER_TRUNCATED")
        opcode, size = struct.unpack("!BQ", payload[cursor : cursor + 9])
        cursor += 9
        if opcode not in {1, 2} or size > len(payload) - cursor:
            raise ValueError("V332_WS_CONTAINER_FRAME_INVALID")
        messages.append((opcode, payload[cursor : cursor + size]))
        cursor += size
    return tuple(messages)


def _recv_exact(connection: ssl.SSLSocket, size: int) -> bytes:
    output = bytearray()
    while len(output) < size:
        chunk = connection.recv(size - len(output))
        if not chunk:
            raise OSError("V332_WS_CONNECTION_CLOSED")
        output.extend(chunk)
    return bytes(output)


def _read_headers(connection: ssl.SSLSocket) -> tuple[str, dict[str, str]]:
    payload = bytearray()
    while b"\r\n\r\n" not in payload:
        chunk = connection.recv(4096)
        if not chunk:
            raise OSError("V332_WS_HANDSHAKE_CLOSED")
        payload.extend(chunk)
        if len(payload) > _MAX_HANDSHAKE_BYTES:
            raise OSError("V332_WS_HANDSHAKE_TOO_LARGE")
    header_bytes, trailing = bytes(payload).split(b"\r\n\r\n", 1)
    if trailing:
        raise OSError("V332_WS_HANDSHAKE_TRAILING_BYTES_UNSUPPORTED")
    try:
        lines = header_bytes.decode("iso-8859-1").split("\r\n")
    except UnicodeDecodeError as exc:
        raise OSError("V332_WS_HANDSHAKE_INVALID") from exc
    status = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise OSError("V332_WS_HANDSHAKE_INVALID")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return status, headers


def _client_frame(opcode: int, payload: bytes) -> bytes:
    if opcode not in {1, 8, 9, 10}:
        raise ValueError("V332_WS_CLIENT_OPCODE_INVALID")
    key = os.urandom(4)
    size = len(payload)
    first = 0x80 | opcode
    if size < 126:
        header = bytes((first, 0x80 | size))
    elif size <= 0xFFFF:
        header = bytes((first, 0x80 | 126)) + struct.pack("!H", size)
    else:
        header = bytes((first, 0x80 | 127)) + struct.pack("!Q", size)
    masked = bytes(value ^ key[index % 4] for index, value in enumerate(payload))
    return header + key + masked


def _read_frame(connection: ssl.SSLSocket, *, max_bytes: int) -> tuple[bool, int, bytes]:
    first, second = _recv_exact(connection, 2)
    final = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    size = second & 0x7F
    if masked:
        raise OSError("V332_WS_SERVER_FRAME_MASKED")
    if size == 126:
        size = struct.unpack("!H", _recv_exact(connection, 2))[0]
    elif size == 127:
        size = struct.unpack("!Q", _recv_exact(connection, 8))[0]
    if size > max_bytes:
        raise OSError("V332_WS_FRAME_TOO_LARGE")
    return final, opcode, _recv_exact(connection, size)


def _failure_code(exc: BaseException) -> str:
    message = str(exc)
    if message.startswith("V332_"):
        return message
    if isinstance(exc, socket.timeout):
        return "V332_WS_TIMEOUT"
    if isinstance(exc, ssl.SSLError):
        return "V332_WS_TLS_FAILURE"
    if isinstance(exc, socket.gaierror):
        return "V332_WS_DNS_FAILURE"
    return "V332_WS_CONNECTION_FAILURE"


def execute_websocket(request: WebSocketRequest) -> TransportResponse:
    started_at = _now()
    parsed = urllib.parse.urlsplit(request.url)
    if (
        parsed.scheme != "wss"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("V332_WS_URL_INVALID")
    host = parsed.hostname
    port = parsed.port or 443
    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    expected_accept = base64.b64encode(
        hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii"),
            usedforsecurity=False,
        ).digest()
    ).decode("ascii")
    connection: ssl.SSLSocket | None = None
    received: list[tuple[int, bytes]] = []
    response_at = started_at
    response_headers: dict[str, str] = {}
    error_code: str | None = None
    status_code: int | None = None
    try:
        raw = socket.create_connection((host, port), timeout=10.0)
        context = ssl.create_default_context()
        connection = context.wrap_socket(raw, server_hostname=host)
        connection.settimeout(10.0)
        host_header = host if port == 443 else f"{host}:{port}"
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "User-Agent: agent-trade-emotion-v3.3.2-public-research/1.0\r\n"
            "\r\n"
        ).encode("ascii")
        connection.sendall(handshake)
        status, headers = _read_headers(connection)
        response_at = _now()
        response_headers = {
            name: value
            for name, value in headers.items()
            if name in {"date", "server", "upgrade", "connection"}
        }
        if not status.startswith("HTTP/1.1 101 "):
            raise OSError("V332_WS_HANDSHAKE_STATUS_INVALID")
        if headers.get("sec-websocket-accept") != expected_accept:
            raise OSError("V332_WS_HANDSHAKE_ACCEPT_INVALID")
        status_code = 101
        for initial in request.initial_messages:
            connection.sendall(_client_frame(1, initial))

        deadline = time.monotonic() + request.duration_seconds
        fragment_opcode: int | None = None
        fragment = bytearray()
        total = 0
        while len(received) < request.max_messages and time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            connection.settimeout(min(2.0, remaining))
            try:
                final, opcode, payload = _read_frame(
                    connection, max_bytes=request.max_bytes
                )
            except socket.timeout:
                continue
            if opcode == 8:
                break
            if opcode == 9:
                connection.sendall(_client_frame(10, payload))
                continue
            if opcode == 10:
                continue
            if opcode in {1, 2}:
                if fragment_opcode is not None:
                    raise OSError("V332_WS_FRAGMENT_SEQUENCE_INVALID")
                if final:
                    total += len(payload)
                    if total > request.max_bytes:
                        raise OSError("V332_WS_CAPTURE_TOO_LARGE")
                    received.append((opcode, payload))
                else:
                    fragment_opcode = opcode
                    fragment.extend(payload)
                continue
            if opcode == 0 and fragment_opcode is not None:
                fragment.extend(payload)
                if len(fragment) > request.max_bytes:
                    raise OSError("V332_WS_FRAGMENT_TOO_LARGE")
                if final:
                    total += len(fragment)
                    if total > request.max_bytes:
                        raise OSError("V332_WS_CAPTURE_TOO_LARGE")
                    received.append((fragment_opcode, bytes(fragment)))
                    fragment_opcode = None
                    fragment.clear()
                continue
            raise OSError("V332_WS_OPCODE_UNSUPPORTED")
    except (OSError, ssl.SSLError, socket.error) as exc:
        error_code = _failure_code(exc)
    finally:
        if connection is not None:
            try:
                connection.sendall(_client_frame(8, b""))
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass
    completed_at = _now()
    body = pack_messages(received)
    return TransportResponse(
        protocol="WEBSOCKET",
        status_code=status_code,
        final_url=request.url,
        stored_url=request.stored_url,
        headers=response_headers,
        body=body,
        request_started_at=started_at,
        response_received_at=response_at,
        capture_completed_at=completed_at,
        error_code=error_code,
        backend="python-stdlib-websocket",
    )


def summarize_websocket_container(raw: bytes) -> Mapping[str, object]:
    messages = unpack_messages(raw)
    text_messages = 0
    binary_messages = 0
    json_messages = 0
    data_messages = 0
    previews: list[dict[str, object]] = []
    import json

    for opcode, payload in messages:
        if opcode == 1:
            text_messages += 1
            try:
                value = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            json_messages += 1
            if isinstance(value, dict):
                if isinstance(value.get("data"), list):
                    data_messages += 1
                preview = {
                    key: value.get(key)
                    for key in ("event", "code", "msg", "action")
                    if key in value
                }
                argument = value.get("arg")
                if isinstance(argument, dict):
                    preview["arg"] = {
                        key: argument.get(key)
                        for key in ("channel", "instId", "instType")
                        if key in argument
                    }
                if preview:
                    previews.append(preview)
        else:
            binary_messages += 1
    return {
        "format": "v332_websocket_message_container",
        "message_count": len(messages),
        "text_message_count": text_messages,
        "binary_message_count": binary_messages,
        "json_message_count": json_messages,
        "data_message_count": data_messages,
        "preview": previews[:10],
    }


__all__ = [
    "execute_websocket",
    "pack_messages",
    "summarize_websocket_container",
    "unpack_messages",
]
