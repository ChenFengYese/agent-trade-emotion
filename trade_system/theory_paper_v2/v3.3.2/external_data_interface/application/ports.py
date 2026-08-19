"""Public module boundaries used by the V3.3.2 application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..domain.contracts import SourceDefinition


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    stored_url: str
    headers: Mapping[str, str]
    stored_headers: Mapping[str, str]
    body: bytes | None
    max_bytes: int


@dataclass(frozen=True, slots=True)
class WebSocketRequest:
    url: str
    stored_url: str
    initial_messages: tuple[bytes, ...]
    duration_seconds: float
    max_messages: int
    max_bytes: int


TransportRequest = HttpRequest | WebSocketRequest


@dataclass(frozen=True, slots=True)
class TransportResponse:
    protocol: str
    status_code: int | None
    final_url: str
    stored_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str
    capture_completed_at: str
    error_code: str | None = None
    backend: str | None = None


class RegisteredSource(Protocol):
    definition: SourceDefinition

    def build_request(
        self,
        *,
        parameters: Mapping[str, str],
        environment: Mapping[str, str],
        now: datetime,
    ) -> TransportRequest: ...

    def normalize(
        self,
        *,
        body: bytes,
        response: TransportResponse,
    ) -> Mapping[str, Any]: ...


class CatalogPort(Protocol):
    def list(self) -> tuple[RegisteredSource, ...]: ...
    def get(self, source_id: str) -> RegisteredSource: ...


class TransportPort(Protocol):
    def execute(self, request: TransportRequest) -> TransportResponse: ...


class RawStorePort(Protocol):
    root: Path

    def seal_transport(
        self,
        *,
        definition: SourceDefinition,
        request: TransportRequest,
        response: TransportResponse,
    ) -> Mapping[str, Any]: ...

    def load_raw(self, reference: Mapping[str, Any]) -> bytes: ...

    def seal_observation(
        self,
        *,
        reference: Mapping[str, Any],
        observation: Mapping[str, Any],
    ) -> str: ...

    def import_manual_file(
        self,
        *,
        definition: SourceDefinition,
        source_file: Path,
        observed_at: str,
        available_at: str,
        captured_at: str,
        source_url: str | None,
    ) -> tuple[Mapping[str, Any], bytes]: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


__all__ = [
    "CatalogPort",
    "ClockPort",
    "HttpRequest",
    "RawStorePort",
    "RegisteredSource",
    "TransportPort",
    "TransportRequest",
    "TransportResponse",
    "WebSocketRequest",
]
