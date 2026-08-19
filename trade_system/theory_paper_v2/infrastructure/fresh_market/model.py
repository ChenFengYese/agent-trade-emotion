"""Closed, deterministic data models for fresh public market bundles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Mapping

from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class FreshMarketModelError(ValueError):
    pass


class QualityStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class FieldStatus(StrEnum):
    OBSERVED = "OBSERVED"
    UNKNOWN = "UNKNOWN"


class AvailabilityBasis(StrEnum):
    PROVIDER_CLOSED_BAR_PROTOCOL = "PROVIDER_CLOSED_BAR_PROTOCOL"


class AvailabilityStatus(StrEnum):
    DERIVED = "DERIVED"


def require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise FreshMarketModelError("CLOCK_TIME_INVALID")


def timestamp(value: datetime) -> str:
    require_utc(value)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def require_id(value: str) -> None:
    if (
        _SAFE_ID.fullmatch(value) is None
        or value.casefold() in {"current", "latest"}
    ):
        raise FreshMarketModelError("OFFLINE_REPLAY_FAILED_NO_COMMIT")


def require_digest(value: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")


@dataclass(frozen=True, slots=True)
class InterfaceField:
    field_name: str
    status: FieldStatus
    value: str | None
    unit: str | None
    reason_code: str | None

    def __post_init__(self) -> None:
        if not self.field_name:
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")
        if self.status is FieldStatus.UNKNOWN:
            if self.value is not None or not self.reason_code:
                raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")
        elif self.value is None or self.reason_code is not None:
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "field_name": self.field_name,
            "status": self.status.value,
            "value": self.value,
            "unit": self.unit,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class PublicRequestCapture:
    request_id: str
    method: str
    base_url: str
    path: str
    query: tuple[tuple[str, str], ...]
    request_started_at: datetime
    response_received_at: datetime
    final_url: str
    http_status: int
    selected_response_headers: tuple[tuple[str, str], ...]
    response_headers_digest: str
    raw_body_sha256: str
    raw_body_byte_length: int
    request_identity_digest: str
    record_digest: str

    def __post_init__(self) -> None:
        require_id(self.request_id)
        require_utc(self.request_started_at)
        require_utc(self.response_received_at)
        for value in (
            self.response_headers_digest,
            self.raw_body_sha256,
            self.request_identity_digest,
            self.record_digest,
        ):
            require_digest(value)
        if (
            self.method != "GET"
            or not self.base_url
            or not self.path.startswith("/")
            or self.response_received_at < self.request_started_at
            or self.http_status < 100
            or self.http_status > 599
            or self.raw_body_byte_length < 0
            or tuple(sorted(self.query)) != self.query
            or len({name for name, _ in self.query}) != len(self.query)
        ):
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "base_url": self.base_url,
            "path": self.path,
            "query": [
                {"name": name, "value": value} for name, value in self.query
            ],
            "request_started_at": timestamp(self.request_started_at),
            "response_received_at": timestamp(self.response_received_at),
            "final_url": self.final_url,
            "http_status": self.http_status,
            "selected_response_headers": [
                {"name": name, "value": value}
                for name, value in self.selected_response_headers
            ],
            "response_headers_digest": self.response_headers_digest,
            "raw_body_sha256": self.raw_body_sha256,
            "raw_body_byte_length": self.raw_body_byte_length,
            "request_identity_digest": self.request_identity_digest,
            "record_digest": self.record_digest,
        }


@dataclass(frozen=True, slots=True)
class NormalizedHourlyBar:
    bar_id: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    quote_asset_volume: str
    trade_count: int | None
    taker_buy_base_volume: str | None
    taker_buy_quote_volume: str | None
    provider_ignored_field: str
    observed_at: datetime
    available_at: datetime
    captured_at: datetime
    availability_status: AvailabilityStatus
    availability_basis: AvailabilityBasis
    source_request_id: str
    source_raw_body_sha256: str
    usage_scope: str
    decision_contemporaneous_status: QualityStatus
    decision_contemporaneous_reason: str
    bar_digest: str

    def __post_init__(self) -> None:
        require_id(self.bar_id)
        for value in (self.observed_at, self.available_at, self.captured_at):
            require_utc(value)
        require_digest(self.source_raw_body_sha256)
        require_digest(self.bar_digest)
        if (
            self.symbol != "BTCUSDT"
            or self.interval != "1h"
            or self.close_time_ms - self.open_time_ms != 3_599_999
            or self.available_at < self.observed_at
            or self.availability_status is not AvailabilityStatus.DERIVED
            or self.usage_scope != "COUNTERFACTUAL_MARKET_REPLAY"
            or self.decision_contemporaneous_status
            is not QualityStatus.UNKNOWN
            or not self.decision_contemporaneous_reason
        ):
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")
        if self.trade_count is not None and (
            not isinstance(self.trade_count, int)
            or isinstance(self.trade_count, bool)
            or self.trade_count < 0
        ):
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")
        taker_values = (
            self.taker_buy_base_volume,
            self.taker_buy_quote_volume,
        )
        if any(value is None for value in taker_values) and not all(
            value is None for value in taker_values
        ):
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")
        if any(
            value is not None and (not isinstance(value, str) or not value)
            for value in taker_values
        ):
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "bar_id": self.bar_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time_ms": self.open_time_ms,
            "close_time_ms": self.close_time_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_asset_volume": self.quote_asset_volume,
            "trade_count": self.trade_count,
            "taker_buy_base_volume": self.taker_buy_base_volume,
            "taker_buy_quote_volume": self.taker_buy_quote_volume,
            "provider_ignored_field": self.provider_ignored_field,
            "observed_at": timestamp(self.observed_at),
            "available_at": timestamp(self.available_at),
            "captured_at": timestamp(self.captured_at),
            "availability_status": self.availability_status.value,
            "availability_basis": self.availability_basis.value,
            "source_request_id": self.source_request_id,
            "source_raw_body_sha256": self.source_raw_body_sha256,
            "usage_scope": self.usage_scope,
            "decision_contemporaneous_status": (
                self.decision_contemporaneous_status.value
            ),
            "decision_contemporaneous_reason": (
                self.decision_contemporaneous_reason
            ),
            "bar_digest": self.bar_digest,
        }


@dataclass(frozen=True, slots=True)
class HourlyDecisionSlot:
    slot_id: str
    slot_index: int
    decision_at: datetime
    visible_bar_ids: tuple[str, ...]
    visible_through_bar_id: str
    source_request_id: str
    source_raw_body_sha256: str
    interface_fields: tuple[InterfaceField, ...]
    usage_scope: str
    contemporaneous_agent_input_status: QualityStatus
    contemporaneous_agent_input_reason: str
    slot_digest: str

    def __post_init__(self) -> None:
        require_id(self.slot_id)
        require_utc(self.decision_at)
        require_digest(self.source_raw_body_sha256)
        require_digest(self.slot_digest)
        if (
            self.slot_index < 0
            or not self.visible_bar_ids
            or self.visible_through_bar_id != self.visible_bar_ids[-1]
            or len(set(self.visible_bar_ids)) != len(self.visible_bar_ids)
            or self.usage_scope != "COUNTERFACTUAL_MARKET_REPLAY"
            or self.contemporaneous_agent_input_status
            is not QualityStatus.UNKNOWN
            or not self.contemporaneous_agent_input_reason
            or len({field.field_name for field in self.interface_fields})
            != len(self.interface_fields)
        ):
            raise FreshMarketModelError("PIT_MIXED_CUTOFF")

    def to_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "slot_index": self.slot_index,
            "decision_at": timestamp(self.decision_at),
            "visible_bar_ids": list(self.visible_bar_ids),
            "visible_through_bar_id": self.visible_through_bar_id,
            "source_request_id": self.source_request_id,
            "source_raw_body_sha256": self.source_raw_body_sha256,
            "interface_fields": [
                item.to_dict() for item in self.interface_fields
            ],
            "usage_scope": self.usage_scope,
            "contemporaneous_agent_input_status": (
                self.contemporaneous_agent_input_status.value
            ),
            "contemporaneous_agent_input_reason": (
                self.contemporaneous_agent_input_reason
            ),
            "slot_digest": self.slot_digest,
        }


@dataclass(frozen=True, slots=True)
class OutcomeBinding:
    binding_id: str
    decision_slot_id: str
    decision_bar_index: int
    horizon_hours: int
    outcome_bar_id: str
    outcome_available_at: datetime
    role_visible: bool
    binding_digest: str

    def __post_init__(self) -> None:
        require_id(self.binding_id)
        require_id(self.decision_slot_id)
        require_id(self.outcome_bar_id)
        require_utc(self.outcome_available_at)
        require_digest(self.binding_digest)
        if (
            self.decision_bar_index < 0
            or self.horizon_hours not in {1, 4, 8, 24}
            or self.role_visible
        ):
            raise FreshMarketModelError("PIT_FUTURE_AVAILABLE")

    def to_dict(self) -> dict[str, object]:
        return {
            "binding_id": self.binding_id,
            "decision_slot_id": self.decision_slot_id,
            "decision_bar_index": self.decision_bar_index,
            "horizon_hours": self.horizon_hours,
            "outcome_bar_id": self.outcome_bar_id,
            "outcome_available_at": timestamp(self.outcome_available_at),
            "role_visible": self.role_visible,
            "binding_digest": self.binding_digest,
        }


@dataclass(frozen=True, slots=True)
class DerivedMarketBar:
    derived_bar_id: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    source_bar_ids: tuple[str, ...]
    available_at: datetime
    derivation_status: str
    derived_bar_digest: str

    def __post_init__(self) -> None:
        require_id(self.derived_bar_id)
        require_utc(self.available_at)
        require_digest(self.derived_bar_digest)
        expected = {"4h": 4, "1d": 24}.get(self.interval)
        if (
            expected is None
            or len(self.source_bar_ids) != expected
            or len(set(self.source_bar_ids)) != expected
            or self.open_time_ms % (expected * 3_600_000) != 0
            or self.close_time_ms - self.open_time_ms
            != expected * 3_600_000 - 1
            or self.derivation_status != "DERIVED_FROM_FROZEN_1H"
        ):
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "derived_bar_id": self.derived_bar_id,
            "symbol": "BTCUSDT",
            "interval": self.interval,
            "open_time_ms": self.open_time_ms,
            "close_time_ms": self.close_time_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source_bar_ids": list(self.source_bar_ids),
            "available_at": timestamp(self.available_at),
            "derivation_status": self.derivation_status,
            "derived_bar_digest": self.derived_bar_digest,
        }


@dataclass(frozen=True, slots=True)
class QualityCheck:
    check_id: str
    status: QualityStatus
    hard_gate: bool
    observed_count: int | None
    required_count: int | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.check_id
            or not self.reason_codes
            or (self.status is QualityStatus.PASS and self.reason_codes != ("PASS",))
        ):
            raise FreshMarketModelError("EVIDENCE_LINEAGE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "hard_gate": self.hard_gate,
            "observed_count": self.observed_count,
            "required_count": self.required_count,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class DatasetQualityReceipt:
    receipt_id: str
    checks: tuple[QualityCheck, ...]
    overall_status: QualityStatus
    hard_failures: tuple[str, ...]
    unknowns: tuple[str, ...]
    system_mode: str
    external_execution_authority: str
    executable: bool
    receipt_digest: str

    def __post_init__(self) -> None:
        require_id(self.receipt_id)
        require_digest(self.receipt_digest)
        if (
            len({item.check_id for item in self.checks}) != len(self.checks)
            or self.system_mode != SYSTEM_MODE
            or self.external_execution_authority
            != EXTERNAL_EXECUTION_AUTHORITY
            or self.executable
        ):
            raise FreshMarketModelError("AUTHORITY_STATUS_MISMATCH")

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "checks": [item.to_dict() for item in self.checks],
            "overall_status": self.overall_status.value,
            "hard_failures": list(self.hard_failures),
            "unknowns": list(self.unknowns),
            "system_mode": self.system_mode,
            "external_execution_authority": (
                self.external_execution_authority
            ),
            "executable": self.executable,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayAdmissibilityReceipt:
    receipt_id: str
    status: QualityStatus
    permitted_usage_scope: str
    availability_status: AvailabilityStatus
    contemporaneous_agent_input_status: QualityStatus
    forbidden_claims: tuple[str, ...]
    system_mode: str
    external_execution_authority: str
    executable: bool
    receipt_digest: str

    def __post_init__(self) -> None:
        require_id(self.receipt_id)
        require_digest(self.receipt_digest)
        if (
            self.status is not QualityStatus.PASS
            or self.permitted_usage_scope
            != "HISTORICAL_COUNTERFACTUAL_REPLAY"
            or self.availability_status is not AvailabilityStatus.DERIVED
            or self.contemporaneous_agent_input_status
            is not QualityStatus.UNKNOWN
            or not self.forbidden_claims
            or self.system_mode != SYSTEM_MODE
            or self.external_execution_authority
            != EXTERNAL_EXECUTION_AUTHORITY
            or self.executable
        ):
            raise FreshMarketModelError("AUTHORITY_STATUS_MISMATCH")

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "status": self.status.value,
            "permitted_usage_scope": self.permitted_usage_scope,
            "availability_status": self.availability_status.value,
            "availability_basis": (
                AvailabilityBasis.PROVIDER_CLOSED_BAR_PROTOCOL.value
            ),
            "contemporaneous_agent_input_status": (
                self.contemporaneous_agent_input_status.value
            ),
            "forbidden_claims": list(self.forbidden_claims),
            "system_mode": self.system_mode,
            "external_execution_authority": (
                self.external_execution_authority
            ),
            "executable": self.executable,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectedPublicResponses:
    server_time: PublicRequestCapture
    exchange_info: PublicRequestCapture
    klines: PublicRequestCapture
    raw_body_by_request_id: Mapping[str, bytes]
