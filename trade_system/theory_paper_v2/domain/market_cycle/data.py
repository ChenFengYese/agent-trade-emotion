"""Immutable V3.3.2 asset-data admission contracts.

These values sit beside the existing five market-cycle artifacts.  They do
not create another repository or raw-reference type: every byte-bearing link
is the existing :class:`ArtifactRef` owned by the market-cycle domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ..contracts.canonical import canonical_bytes
from .contracts import ArtifactRef


ASSET_DATA_SLICE_SCHEMA_ID = "agent_trade_emotion_asset_data_slice"
ASSET_DATA_SLICE_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ADMITTED_STATUSES = frozenset({"ACTIVE", "INACTIVE", "UNKNOWN"})


class AssetDataContractError(ValueError):
    """A V3.3.2 asset-data value violates its frozen contract."""


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AssetDataContractError(f"V332_DATA_{field}_INVALID")
    return value


def _moment(value: object, *, field: str) -> datetime:
    text = _text(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssetDataContractError(f"V332_DATA_{field}_INVALID") from exc
    if parsed.tzinfo is None:
        raise AssetDataContractError(f"V332_DATA_{field}_INVALID")
    return parsed.astimezone(UTC)


def _time_text(value: object, *, field: str) -> str:
    return _moment(value, field=field).isoformat().replace("+00:00", "Z")


def _freeze_json(value: Any, *, field: str) -> Any:
    """Freeze the project's canonical JSON subset without changing values."""

    try:
        canonical_bytes(value)
    except (TypeError, ValueError) as exc:
        raise AssetDataContractError(f"V332_DATA_{field}_INVALID") from exc
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_json(item, field=field)
                for key, item in sorted(value.items())
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, field=field) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _artifact(value: ArtifactRef | Mapping[str, Any], *, field: str) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    if not isinstance(value, Mapping):
        raise AssetDataContractError(f"V332_DATA_{field}_INVALID")
    try:
        return ArtifactRef.from_dict(value)
    except ValueError as exc:
        raise AssetDataContractError(f"V332_DATA_{field}_INVALID") from exc


@dataclass(frozen=True, slots=True)
class InstrumentIdentityV1:
    """Strong identity for one venue product; aliases are not admitted."""

    instrument_key: str
    venue: str
    market_type: str
    venue_symbol: str
    base_asset: str
    quote_asset: str
    settle_asset: str
    underlying_identity: str
    product_identity: str
    contract_semantics: str
    quantity_basis: str
    session_semantics: str
    status: str
    discovered_at: str
    effective_at: str
    source_ref: ArtifactRef

    def __post_init__(self) -> None:
        for field in (
            "instrument_key",
            "venue",
            "market_type",
            "venue_symbol",
            "base_asset",
            "quote_asset",
            "settle_asset",
            "underlying_identity",
            "product_identity",
            "contract_semantics",
            "quantity_basis",
            "session_semantics",
        ):
            _text(getattr(self, field), field=f"INSTRUMENT_{field.upper()}")
        if self.status not in _ADMITTED_STATUSES:
            raise AssetDataContractError("V332_DATA_INSTRUMENT_STATUS_INVALID")
        effective = _moment(
            self.effective_at, field="INSTRUMENT_EFFECTIVE_AT"
        )
        discovered = _moment(
            self.discovered_at, field="INSTRUMENT_DISCOVERED_AT"
        )
        if effective > discovered:
            raise AssetDataContractError(
                "V332_DATA_INSTRUMENT_EFFECTIVE_AFTER_DISCOVERY"
            )
        source_ref = _artifact(
            self.source_ref, field="INSTRUMENT_SOURCE_REF"
        )
        if source_ref.artifact_type != "RawCapture":
            raise AssetDataContractError(
                "V332_DATA_INSTRUMENT_SOURCE_NOT_RAW_CAPTURE"
            )
        object.__setattr__(
            self,
            "effective_at",
            effective.isoformat().replace("+00:00", "Z"),
        )
        object.__setattr__(
            self,
            "discovered_at",
            discovered.isoformat().replace("+00:00", "Z"),
        )
        object.__setattr__(self, "source_ref", source_ref)

    def to_dict(self) -> dict[str, object]:
        return {
            "instrument_key": self.instrument_key,
            "venue": self.venue,
            "market_type": self.market_type,
            "venue_symbol": self.venue_symbol,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "settle_asset": self.settle_asset,
            "underlying_identity": self.underlying_identity,
            "product_identity": self.product_identity,
            "contract_semantics": self.contract_semantics,
            "quantity_basis": self.quantity_basis,
            "session_semantics": self.session_semantics,
            "status": self.status,
            "discovered_at": self.discovered_at,
            "effective_at": self.effective_at,
            "source_ref": self.source_ref.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InstrumentIdentityV1":
        expected = {
            "instrument_key",
            "venue",
            "market_type",
            "venue_symbol",
            "base_asset",
            "quote_asset",
            "settle_asset",
            "underlying_identity",
            "product_identity",
            "contract_semantics",
            "quantity_basis",
            "session_semantics",
            "status",
            "discovered_at",
            "effective_at",
            "source_ref",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise AssetDataContractError(
                "V332_DATA_INSTRUMENT_IDENTITY_FIELDS_INVALID"
            )
        return cls(
            **{
                **{key: value[key] for key in expected - {"source_ref"}},
                "source_ref": _artifact(
                    value["source_ref"], field="INSTRUMENT_SOURCE_REF"
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class SourceContractV1:
    """One bounded public source and the highest claim it can support."""

    source_id: str
    provider: str
    dataset: str
    transport: str
    access_mode: str
    official_endpoint: str
    terms_ref: str
    instrument_scope: str
    cadence: str
    history_window: str
    event_time_semantics: str
    publish_time_semantics: str
    claim_ceiling: str
    required_parameters: Mapping[str, str]
    rate_limit_policy: str
    retry_policy: str
    max_staleness_seconds: int

    def __post_init__(self) -> None:
        for field in (
            "source_id",
            "provider",
            "dataset",
            "transport",
            "access_mode",
            "official_endpoint",
            "terms_ref",
            "instrument_scope",
            "cadence",
            "history_window",
            "event_time_semantics",
            "publish_time_semantics",
            "claim_ceiling",
            "rate_limit_policy",
            "retry_policy",
        ):
            _text(getattr(self, field), field=f"SOURCE_{field.upper()}")
        if (
            type(self.max_staleness_seconds) is not int
            or self.max_staleness_seconds < 0
        ):
            raise AssetDataContractError(
                "V332_DATA_SOURCE_MAX_STALENESS_INVALID"
            )
        if not isinstance(self.required_parameters, Mapping) or any(
            not isinstance(key, str)
            or not key
            or not isinstance(item, str)
            or not item
            for key, item in self.required_parameters.items()
        ):
            raise AssetDataContractError(
                "V332_DATA_SOURCE_REQUIRED_PARAMETERS_INVALID"
            )
        object.__setattr__(
            self,
            "required_parameters",
            MappingProxyType(dict(sorted(self.required_parameters.items()))),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "provider": self.provider,
            "dataset": self.dataset,
            "transport": self.transport,
            "access_mode": self.access_mode,
            "official_endpoint": self.official_endpoint,
            "terms_ref": self.terms_ref,
            "instrument_scope": self.instrument_scope,
            "cadence": self.cadence,
            "history_window": self.history_window,
            "event_time_semantics": self.event_time_semantics,
            "publish_time_semantics": self.publish_time_semantics,
            "claim_ceiling": self.claim_ceiling,
            "required_parameters": dict(self.required_parameters),
            "rate_limit_policy": self.rate_limit_policy,
            "retry_policy": self.retry_policy,
            "max_staleness_seconds": self.max_staleness_seconds,
        }


@dataclass(frozen=True, slots=True)
class CaptureRefV1:
    """Timing and request binding around one existing raw ``ArtifactRef``."""

    capture_id: str
    source_id: str
    request_binding: Mapping[str, Any]
    request_started_at: str
    response_received_at: str
    captured_at: str
    raw_ref: ArtifactRef
    parser_version: str
    source_health: str = "OBSERVED"
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        _text(self.capture_id, field="CAPTURE_ID")
        _text(self.source_id, field="CAPTURE_SOURCE_ID")
        _text(self.parser_version, field="CAPTURE_PARSER_VERSION")
        started = _moment(self.request_started_at, field="CAPTURE_REQUESTED_AT")
        received = _moment(
            self.response_received_at, field="CAPTURE_RESPONSE_RECEIVED_AT"
        )
        captured = _moment(self.captured_at, field="CAPTURE_CAPTURED_AT")
        if not started <= received <= captured:
            raise AssetDataContractError("V332_DATA_CAPTURE_CHRONOLOGY_INVALID")
        raw_ref = _artifact(self.raw_ref, field="CAPTURE_RAW_REF")
        if raw_ref.artifact_type != "RawCapture":
            raise AssetDataContractError("V332_DATA_CAPTURE_RAW_REF_INVALID")
        if raw_ref.path != f"raw/{self.capture_id}/body.bin":
            raise AssetDataContractError(
                "V332_DATA_CAPTURE_RAW_REF_IDENTITY_MISMATCH"
            )
        if self.source_health not in {"OBSERVED", "UNKNOWN", "MISSING"}:
            raise AssetDataContractError("V332_DATA_CAPTURE_HEALTH_INVALID")
        if self.source_health == "OBSERVED" and self.failure_reason is not None:
            raise AssetDataContractError(
                "V332_DATA_CAPTURE_OBSERVED_WITH_FAILURE"
            )
        binding = _freeze_json(
            self.request_binding, field="CAPTURE_REQUEST_BINDING"
        )
        if not isinstance(binding, Mapping):
            raise AssetDataContractError(
                "V332_DATA_CAPTURE_REQUEST_BINDING_INVALID"
            )
        object.__setattr__(self, "request_binding", binding)
        object.__setattr__(
            self,
            "request_started_at",
            started.isoformat().replace("+00:00", "Z"),
        )
        object.__setattr__(
            self,
            "response_received_at",
            received.isoformat().replace("+00:00", "Z"),
        )
        object.__setattr__(
            self, "captured_at", captured.isoformat().replace("+00:00", "Z")
        )
        object.__setattr__(self, "raw_ref", raw_ref)

    def to_dict(self) -> dict[str, object]:
        return {
            "capture_id": self.capture_id,
            "source_id": self.source_id,
            "request_binding": _thaw_json(self.request_binding),
            "request_started_at": self.request_started_at,
            "response_received_at": self.response_received_at,
            "captured_at": self.captured_at,
            "raw_ref": self.raw_ref.to_dict(),
            "parser_version": self.parser_version,
            "source_health": self.source_health,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True, slots=True)
class SharedContextRefV1:
    """One versioned shared fact snapshot; never copied into each asset raw."""

    context_id: str
    version: int
    available_at: str
    claim_ceiling: str
    artifact_ref: ArtifactRef

    def __post_init__(self) -> None:
        _text(self.context_id, field="SHARED_CONTEXT_ID")
        _text(self.claim_ceiling, field="SHARED_CONTEXT_CLAIM_CEILING")
        if type(self.version) is not int or self.version < 1:
            raise AssetDataContractError(
                "V332_DATA_SHARED_CONTEXT_VERSION_INVALID"
            )
        object.__setattr__(
            self,
            "available_at",
            _time_text(self.available_at, field="SHARED_CONTEXT_AVAILABLE_AT"),
        )
        object.__setattr__(
            self,
            "artifact_ref",
            _artifact(self.artifact_ref, field="SHARED_CONTEXT_REF"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "context_id": self.context_id,
            "version": self.version,
            "available_at": self.available_at,
            "claim_ceiling": self.claim_ceiling,
            "artifact_ref": self.artifact_ref.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class TypedUnknownV1:
    """An optional absence that is explicitly not a numeric zero."""

    component_id: str
    source_id: str
    missing_reason: str
    claim_ceiling: str
    available_at: str | None = None
    raw_ref: ArtifactRef | None = None
    status: str = "UNKNOWN"
    missing_is_zero: bool = False

    def __post_init__(self) -> None:
        for field in (
            "component_id",
            "source_id",
            "missing_reason",
            "claim_ceiling",
        ):
            _text(getattr(self, field), field=f"UNKNOWN_{field.upper()}")
        if self.status != "UNKNOWN" or self.missing_is_zero is not False:
            raise AssetDataContractError("V332_DATA_TYPED_UNKNOWN_INVALID")
        if self.available_at is not None:
            object.__setattr__(
                self,
                "available_at",
                _time_text(self.available_at, field="UNKNOWN_AVAILABLE_AT"),
            )
        if self.raw_ref is not None:
            object.__setattr__(
                self,
                "raw_ref",
                _artifact(self.raw_ref, field="UNKNOWN_RAW_REF"),
            )

    @property
    def code(self) -> str:
        return f"{self.component_id}:{self.missing_reason}"

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "code": self.code,
            "component_id": self.component_id,
            "source_id": self.source_id,
            "status": self.status,
            "missing_reason": self.missing_reason,
            "missing_is_zero": self.missing_is_zero,
            "claim_ceiling": self.claim_ceiling,
        }
        if self.available_at is not None:
            result["available_at"] = self.available_at
        if self.raw_ref is not None:
            result["raw_ref"] = self.raw_ref.to_dict()
        return result


def _validate_observation(
    name: str,
    value: object,
    *,
    cutoff: datetime,
    raw_refs: tuple[ArtifactRef, ...],
    raw_hashes: frozenset[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssetDataContractError(
            f"V332_DATA_OBSERVATION_OBJECT_REQUIRED:{name}"
        )
    required = {
        "value",
        "available_at",
        "raw_ref",
        "raw_sha256",
        "source_id",
        "venue",
        "market_type",
        "population",
        "window",
        "unit",
        "claim_ceiling",
    }
    if not required.issubset(value):
        raise AssetDataContractError(
            f"V332_DATA_OBSERVATION_METADATA_INCOMPLETE:{name}"
        )
    for field in required - {
        "value",
        "available_at",
        "raw_ref",
        "raw_sha256",
    }:
        _text(value[field], field=f"OBSERVATION_{field.upper()}")
    available = _moment(
        value["available_at"], field=f"OBSERVATION_{name}_AVAILABLE_AT"
    )
    if available > cutoff:
        raise AssetDataContractError(f"V332_DATA_PIT_VIOLATION:{name}")
    digest = value["raw_sha256"]
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise AssetDataContractError(
            f"V332_DATA_OBSERVATION_RAW_SHA_INVALID:{name}"
        )
    if digest not in raw_hashes:
        raise AssetDataContractError(
            f"V332_DATA_OBSERVATION_RAW_NOT_SEALED:{name}"
        )
    observation_raw_ref = _artifact(
        value["raw_ref"], field=f"OBSERVATION_{name}_RAW_REF"
    )
    if observation_raw_ref.sha256 != digest or observation_raw_ref not in raw_refs:
        raise AssetDataContractError(
            f"V332_DATA_OBSERVATION_RAW_REF_MISMATCH:{name}"
        )
    if "observed_at" in value:
        observed = _moment(
            value["observed_at"], field=f"OBSERVATION_{name}_OBSERVED_AT"
        )
        if observed > available:
            raise AssetDataContractError(
                f"V332_DATA_OBSERVATION_AVAILABLE_BEFORE_EVENT:{name}"
            )
    frozen = _freeze_json(value, field=f"OBSERVATION_{name}")
    if not isinstance(frozen, Mapping):
        raise AssetDataContractError(
            f"V332_DATA_OBSERVATION_OBJECT_REQUIRED:{name}"
        )
    return frozen


@dataclass(frozen=True, slots=True)
class AssetDataSliceV1:
    """One admitted, raw-bound point-in-time slice for exactly one asset."""

    asset_profile_id: str
    instrument_identity: InstrumentIdentityV1
    cutoff_at: str
    slice_start_at: str
    slice_end_at: str
    data_cursor: str
    core_observations: Mapping[str, Any]
    optional_observations: Mapping[str, Any]
    shared_context_ref: SharedContextRefV1 | None
    source_health: Sequence[Mapping[str, Any]]
    coverage: Mapping[str, Any]
    staleness: Mapping[str, Any]
    typed_unknowns: Sequence[TypedUnknownV1]
    raw_refs: Sequence[ArtifactRef]
    capture_refs: Sequence[CaptureRefV1]
    sealed_at: str
    schema_id: str = ASSET_DATA_SLICE_SCHEMA_ID
    schema_version: str = ASSET_DATA_SLICE_SCHEMA_VERSION
    status: str = "ADMITTED"

    def __post_init__(self) -> None:
        _text(self.asset_profile_id, field="SLICE_PROFILE_ID")
        if not isinstance(self.instrument_identity, InstrumentIdentityV1):
            raise AssetDataContractError(
                "V332_DATA_SLICE_INSTRUMENT_IDENTITY_INVALID"
            )
        if (
            self.schema_id != ASSET_DATA_SLICE_SCHEMA_ID
            or self.schema_version != ASSET_DATA_SLICE_SCHEMA_VERSION
            or self.status != "ADMITTED"
        ):
            raise AssetDataContractError("V332_DATA_SLICE_SCHEMA_INVALID")
        cutoff = _moment(self.cutoff_at, field="SLICE_CUTOFF_AT")
        start = _moment(self.slice_start_at, field="SLICE_START_AT")
        end = _moment(self.slice_end_at, field="SLICE_END_AT")
        sealed = _moment(self.sealed_at, field="SLICE_SEALED_AT")
        if not start <= end <= cutoff <= sealed:
            raise AssetDataContractError("V332_DATA_SLICE_CHRONOLOGY_INVALID")
        if not isinstance(self.data_cursor, str) or _SHA256.fullmatch(
            self.data_cursor
        ) is None:
            raise AssetDataContractError("V332_DATA_SLICE_CURSOR_INVALID")

        raw_refs = tuple(
            _artifact(item, field="SLICE_RAW_REF") for item in self.raw_refs
        )
        if not raw_refs or len(set(raw_refs)) != len(raw_refs):
            raise AssetDataContractError("V332_DATA_SLICE_RAW_REFS_INVALID")
        raw_hashes = frozenset(item.sha256 for item in raw_refs)
        if self.instrument_identity.source_ref.sha256 not in raw_hashes:
            raise AssetDataContractError(
                "V332_DATA_SLICE_INSTRUMENT_RAW_NOT_BOUND"
            )

        required_core = {
            "server_time",
            "instrument",
            "mark_price",
            "closed_15m_bars",
        }
        if not isinstance(self.core_observations, Mapping) or set(
            self.core_observations
        ) != required_core:
            raise AssetDataContractError(
                "V332_DATA_SLICE_CORE_OBSERVATIONS_INCOMPLETE"
            )
        core = MappingProxyType(
            {
                name: _validate_observation(
                    name,
                    item,
                    cutoff=cutoff,
                    raw_refs=raw_refs,
                    raw_hashes=raw_hashes,
                )
                for name, item in sorted(self.core_observations.items())
            }
        )
        if not isinstance(self.optional_observations, Mapping):
            raise AssetDataContractError(
                "V332_DATA_SLICE_OPTIONAL_OBSERVATIONS_INVALID"
            )
        optional = MappingProxyType(
            {
                name: _validate_observation(
                    name,
                    item,
                    cutoff=cutoff,
                    raw_refs=raw_refs,
                    raw_hashes=raw_hashes,
                )
                for name, item in sorted(self.optional_observations.items())
            }
        )
        shared = self.shared_context_ref
        if shared is not None:
            if not isinstance(shared, SharedContextRefV1):
                raise AssetDataContractError(
                    "V332_DATA_SLICE_SHARED_CONTEXT_INVALID"
                )
            if _moment(
                shared.available_at, field="SLICE_SHARED_CONTEXT_AVAILABLE_AT"
            ) > cutoff:
                raise AssetDataContractError(
                    "V332_DATA_SLICE_SHARED_CONTEXT_PIT_VIOLATION"
                )

        unknowns = tuple(self.typed_unknowns)
        if not all(isinstance(item, TypedUnknownV1) for item in unknowns):
            raise AssetDataContractError(
                "V332_DATA_SLICE_TYPED_UNKNOWNS_INVALID"
            )
        if len({item.component_id for item in unknowns}) != len(unknowns):
            raise AssetDataContractError(
                "V332_DATA_SLICE_TYPED_UNKNOWNS_DUPLICATE"
            )
        for item in unknowns:
            if item.available_at is not None and _moment(
                item.available_at, field="SLICE_UNKNOWN_AVAILABLE_AT"
            ) > cutoff:
                raise AssetDataContractError(
                    "V332_DATA_SLICE_UNKNOWN_PIT_VIOLATION"
                )
            if item.raw_ref is not None and item.raw_ref not in raw_refs:
                raise AssetDataContractError(
                    "V332_DATA_SLICE_UNKNOWN_RAW_NOT_BOUND"
                )

        captures = tuple(self.capture_refs)
        if not all(isinstance(item, CaptureRefV1) for item in captures):
            raise AssetDataContractError(
                "V332_DATA_SLICE_CAPTURE_REFS_INVALID"
            )
        capture_raw = {item.raw_ref for item in captures}
        if capture_raw != set(raw_refs):
            raise AssetDataContractError(
                "V332_DATA_SLICE_CAPTURE_RAW_SET_MISMATCH"
            )
        source_health = tuple(
            _freeze_json(item, field=f"SOURCE_HEALTH_{index}")
            for index, item in enumerate(self.source_health)
        )
        if not all(
            isinstance(item, Mapping)
            and isinstance(item.get("component_id"), str)
            and item.get("status") in {"OBSERVED", "UNKNOWN", "MISSING"}
            for item in source_health
        ):
            raise AssetDataContractError("V332_DATA_SOURCE_HEALTH_INVALID")
        coverage = _freeze_json(self.coverage, field="SLICE_COVERAGE")
        staleness = _freeze_json(self.staleness, field="SLICE_STALENESS")
        if not isinstance(coverage, Mapping) or not isinstance(
            staleness, Mapping
        ):
            raise AssetDataContractError(
                "V332_DATA_SLICE_MEASUREMENT_OBJECT_INVALID"
            )

        object.__setattr__(self, "cutoff_at", cutoff.isoformat().replace("+00:00", "Z"))
        object.__setattr__(
            self, "slice_start_at", start.isoformat().replace("+00:00", "Z")
        )
        object.__setattr__(
            self, "slice_end_at", end.isoformat().replace("+00:00", "Z")
        )
        object.__setattr__(
            self, "sealed_at", sealed.isoformat().replace("+00:00", "Z")
        )
        object.__setattr__(self, "core_observations", core)
        object.__setattr__(self, "optional_observations", optional)
        object.__setattr__(self, "typed_unknowns", unknowns)
        object.__setattr__(self, "raw_refs", raw_refs)
        object.__setattr__(self, "capture_refs", captures)
        object.__setattr__(self, "source_health", source_health)
        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "staleness", staleness)

    @property
    def instrument_identity_ref(self) -> ArtifactRef:
        return self.instrument_identity.source_ref

    @property
    def observations(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {**self.core_observations, **self.optional_observations}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "status": self.status,
            "asset_profile_id": self.asset_profile_id,
            "instrument_identity": self.instrument_identity.to_dict(),
            "instrument_identity_ref": self.instrument_identity_ref.to_dict(),
            "cutoff_at": self.cutoff_at,
            "slice_start_at": self.slice_start_at,
            "slice_end_at": self.slice_end_at,
            "data_cursor": self.data_cursor,
            "core_observations": _thaw_json(self.core_observations),
            "optional_observations": _thaw_json(self.optional_observations),
            "shared_context_ref": (
                None
                if self.shared_context_ref is None
                else self.shared_context_ref.to_dict()
            ),
            "source_health": _thaw_json(self.source_health),
            "coverage": _thaw_json(self.coverage),
            "staleness": _thaw_json(self.staleness),
            "typed_unknowns": [item.to_dict() for item in self.typed_unknowns],
            "raw_refs": [item.to_dict() for item in self.raw_refs],
            "capture_refs": [item.to_dict() for item in self.capture_refs],
            "sealed_at": self.sealed_at,
        }


__all__ = [
    "ASSET_DATA_SLICE_SCHEMA_ID",
    "ASSET_DATA_SLICE_SCHEMA_VERSION",
    "AssetDataContractError",
    "AssetDataSliceV1",
    "CaptureRefV1",
    "InstrumentIdentityV1",
    "SharedContextRefV1",
    "SourceContractV1",
    "TypedUnknownV1",
]
