"""Stable V3.3.2 contracts for source discovery and finite capture windows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any, Mapping


SCHEMA_VERSION = "3.3.2"
_SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{2,127}\Z")


class AccessMode(StrEnum):
    """The least authority needed to use a source lawfully."""

    NO_AUTH = "NO_AUTH"
    CONTACT_HEADER = "CONTACT_HEADER"
    FREE_KEY = "FREE_KEY"
    MANUAL_PUBLIC_EXPORT = "MANUAL_PUBLIC_EXPORT"
    APPLICATION_REQUIRED = "APPLICATION_REQUIRED"
    SEPARATE_AUTHORITY = "SEPARATE_AUTHORITY"
    UNOBSERVABLE = "UNOBSERVABLE"


class TransportKind(StrEnum):
    HTTP = "HTTP"
    WEBSOCKET = "WEBSOCKET"
    MANUAL_FILE = "MANUAL_FILE"
    UNAVAILABLE = "UNAVAILABLE"


class CaptureStatus(StrEnum):
    """Explicit terminal state for one source attempt."""

    OBSERVED_RAW = "OBSERVED_RAW"
    OBSERVED_EMPTY = "OBSERVED_EMPTY"
    WAITING_USER_CONFIG = "WAITING_USER_CONFIG"
    MANUAL_INPUT_REQUIRED = "MANUAL_INPUT_REQUIRED"
    CAPTURE_FAILED = "CAPTURE_FAILED"
    UNOBSERVABLE = "UNOBSERVABLE"
    PROHIBITED_CURRENT_SCOPE = "PROHIBITED_CURRENT_SCOPE"


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """A source's public, serializable acquisition contract."""

    source_id: str
    family: str
    dataset: str
    provider: str
    access_mode: AccessMode
    transport: TransportKind
    endpoint: str
    terms_url: str
    cadence: str
    history: str
    time_semantics: str
    claim_ceiling: str
    required_env: tuple[str, ...] = ()
    required_parameters: tuple[str, ...] = ()
    default_enabled: bool = False
    stream: bool = False

    def __post_init__(self) -> None:
        if _SOURCE_ID.fullmatch(self.source_id) is None:
            raise ValueError("V332_SOURCE_ID_INVALID")
        for name, value in (
            ("family", self.family),
            ("dataset", self.dataset),
            ("provider", self.provider),
            ("endpoint", self.endpoint),
            ("terms_url", self.terms_url),
            ("cadence", self.cadence),
            ("history", self.history),
            ("time_semantics", self.time_semantics),
            ("claim_ceiling", self.claim_ceiling),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"V332_SOURCE_{name.upper()}_INVALID")
        if len(set(self.required_env)) != len(self.required_env):
            raise ValueError("V332_SOURCE_REQUIRED_ENV_DUPLICATE")
        if len(set(self.required_parameters)) != len(self.required_parameters):
            raise ValueError("V332_SOURCE_REQUIRED_PARAMETER_DUPLICATE")
        if self.stream and self.transport is not TransportKind.WEBSOCKET:
            raise ValueError("V332_SOURCE_STREAM_TRANSPORT_INVALID")
        if self.default_enabled and self.access_mode is not AccessMode.NO_AUTH:
            raise ValueError("V332_SOURCE_DEFAULT_AUTHORITY_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_id": self.source_id,
            "family": self.family,
            "dataset": self.dataset,
            "provider": self.provider,
            "access_mode": self.access_mode.value,
            "transport": self.transport.value,
            "endpoint": self.endpoint,
            "terms_url": self.terms_url,
            "cadence": self.cadence,
            "history": self.history,
            "time_semantics": self.time_semantics,
            "claim_ceiling": self.claim_ceiling,
            "required_env": list(self.required_env),
            "required_parameters": list(self.required_parameters),
            "default_enabled": self.default_enabled,
            "stream": self.stream,
        }


@dataclass(frozen=True, slots=True)
class CaptureResult:
    source_id: str
    status: CaptureStatus
    capture_id: str | None
    captured_at: str
    available_at: str | None
    raw_ref: Mapping[str, Any] | None
    observation_path: str | None
    reason: str | None
    summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_id": self.source_id,
            "status": self.status.value,
            "capture_id": self.capture_id,
            "captured_at": self.captured_at,
            "available_at": self.available_at,
            "raw_ref": None if self.raw_ref is None else dict(self.raw_ref),
            "observation_path": self.observation_path,
            "reason": self.reason,
            "summary": dict(self.summary),
        }


def source_readiness(
    definition: SourceDefinition,
    *,
    environment: Mapping[str, str],
    parameters: Mapping[str, str],
) -> tuple[CaptureStatus | None, str | None]:
    """Return a blocking terminal state, or ``(None, None)`` when runnable."""

    if definition.access_mode is AccessMode.UNOBSERVABLE:
        return CaptureStatus.UNOBSERVABLE, "PUBLIC_SOURCE_CANNOT_OBSERVE_THIS_FACT"
    if definition.access_mode in {
        AccessMode.APPLICATION_REQUIRED,
        AccessMode.SEPARATE_AUTHORITY,
    }:
        return (
            CaptureStatus.PROHIBITED_CURRENT_SCOPE,
            "APPLICATION_OR_SEPARATE_AUTHORITY_REQUIRED",
        )
    if definition.transport is TransportKind.MANUAL_FILE:
        return CaptureStatus.MANUAL_INPUT_REQUIRED, "MANUAL_SOURCE_FILE_REQUIRED"
    missing_env = [name for name in definition.required_env if not environment.get(name)]
    if missing_env:
        return CaptureStatus.WAITING_USER_CONFIG, "MISSING_ENV:" + ",".join(missing_env)
    missing_parameters = [
        name for name in definition.required_parameters if not parameters.get(name)
    ]
    if missing_parameters:
        return (
            CaptureStatus.WAITING_USER_CONFIG,
            "MISSING_PARAMETER:" + ",".join(missing_parameters),
        )
    return None, None


__all__ = [
    "AccessMode",
    "CaptureResult",
    "CaptureStatus",
    "SCHEMA_VERSION",
    "SourceDefinition",
    "TransportKind",
    "source_readiness",
]
