"""Deterministic contracts for the durable V3.1 outcome-monitor runtime.

The runtime is research-only.  Its sole external boundary is an explicit
public-market observation adapter; account, credential, portfolio, order,
paper, and live-trading capabilities are absent from these contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from .contracts.canonical import (
    CanonicalContractError,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .v31_experiment_contracts import (
    ObservationMissingness,
    ObservationQuality,
    OutcomeObservation,
    V31ExperimentContractError,
)


MONITOR_CHECKPOINT_SCHEMA_ID = "theory_paper_v31_monitor_checkpoint"
MONITOR_CHECKPOINT_SCHEMA_VERSION = "1.0.0"
MONITOR_ATTEMPT_SCHEMA_ID = "theory_paper_v31_monitor_resolution_attempt"
PUBLIC_SOURCE_RECORD_SCHEMA_ID = "theory_paper_v31_public_outcome_source_record"
MONITOR_FAILURE_SCHEMA_ID = "theory_paper_v31_monitor_failure"
RUNTIME_SCHEMA_VERSION = "1.0.0"
PUBLIC_SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
OUTCOME_EVALUATOR_VERSION = "V3_1_DURABLE_MONITOR_EVALUATOR_1_0_0"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class V31MonitorRuntimeContractError(ValueError):
    """A public reading or durable-monitor contract failed closed."""


def monitor_cycle_root(cycle_index: int) -> str:
    """Return the one canonical durable directory for a monitor cycle."""

    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31MonitorRuntimeContractError("V31_MONITOR_CYCLE_INDEX_INVALID")
    return f"monitor/cycles/{cycle_index:04d}"


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31MonitorRuntimeContractError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31MonitorRuntimeContractError(code)
    return value


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31MonitorRuntimeContractError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31MonitorRuntimeContractError(code) from exc
    if parsed.tzinfo is None:
        raise V31MonitorRuntimeContractError(code)
    return parsed.astimezone(UTC)


def _time_text(value: Any, code: str) -> str:
    return _time(value, code).isoformat().replace("+00:00", "Z")


def _authority_boundary() -> dict[str, Any]:
    return {
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_use": False,
        "funds_access": False,
        "portfolio_mutation": False,
    }


@dataclass(frozen=True, slots=True)
class PublicOutcomeReading:
    """One response returned by the explicit public observation adapter.

    ``raw_payload`` is retained byte-for-byte by Infrastructure before the
    normalized source record and typed outcome observation are sealed.
    """

    raw_payload: bytes
    source_locator: str
    captured_at: str
    observable_ref: str
    value: Any
    as_of: str
    available_at: str
    missingness: ObservationMissingness
    quality: ObservationQuality
    coverage: str
    conflict_state: str
    source_request_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.raw_payload, bytes) or not self.raw_payload:
            raise V31MonitorRuntimeContractError(
                "V31_MONITOR_PUBLIC_RAW_PAYLOAD_INVALID"
            )
        locator = _text(
            self.source_locator, "V31_MONITOR_PUBLIC_SOURCE_LOCATOR_INVALID"
        )
        parsed_locator = urlsplit(locator)
        query_pairs = parse_qsl(
            parsed_locator.query, keep_blank_values=True, strict_parsing=True
        )
        if (
            parsed_locator.scheme != "https"
            or parsed_locator.hostname != "www.okx.com"
            or parsed_locator.port is not None
            or parsed_locator.username is not None
            or parsed_locator.password is not None
            or parsed_locator.path != "/api/v5/public/mark-price"
            or parsed_locator.fragment
            or len(query_pairs) != 2
            or dict(query_pairs)
            != {"instType": "SWAP", "instId": "BTC-USDT-SWAP"}
        ):
            raise V31MonitorRuntimeContractError(
                "V31_MONITOR_PUBLIC_SOURCE_SCOPE_INVALID"
            )
        captured = _time(self.captured_at, "V31_MONITOR_READING_TIME_INVALID")
        as_of = _time(self.as_of, "V31_MONITOR_READING_TIME_INVALID")
        available = _time(self.available_at, "V31_MONITOR_READING_TIME_INVALID")
        if as_of > available or available > captured:
            raise V31MonitorRuntimeContractError(
                "V31_MONITOR_READING_NOT_POINT_IN_TIME"
            )
        _text(self.observable_ref, "V31_MONITOR_OBSERVABLE_INVALID")
        _text(self.conflict_state, "V31_MONITOR_CONFLICT_STATE_INVALID")
        _text(self.source_request_id, "V31_MONITOR_SOURCE_REQUEST_ID_INVALID")
        if not isinstance(self.missingness, ObservationMissingness) or not isinstance(
            self.quality, ObservationQuality
        ):
            raise V31MonitorRuntimeContractError("V31_MONITOR_READING_ENUM_INVALID")
        # OutcomeObservation owns the exact missingness/value/coverage contract.
        try:
            OutcomeObservation(
                observable_ref=self.observable_ref,
                value=self.value,
                as_of=self.as_of,
                available_at=self.available_at,
                missingness=self.missingness,
                quality=self.quality,
                coverage=self.coverage,
                conflict_state=self.conflict_state,
                source_request_id=self.source_request_id,
                source_record_digest="0" * 64,
                raw_capture_digest="0" * 64,
                datum_digest="0" * 64,
            )
        except V31ExperimentContractError as exc:
            raise V31MonitorRuntimeContractError(
                "V31_MONITOR_READING_PAYLOAD_INVALID"
            ) from exc


def build_monitor_resolution_attempt(
    *,
    run_id: str,
    cycle_index: int,
    monitor_plan_digest: str,
    requested_at: str,
    previous_outcome_receipt_digest: str | None,
) -> dict[str, Any]:
    """Reserve the sole public-observation attempt before invoking an adapter."""

    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31MonitorRuntimeContractError("V31_MONITOR_ATTEMPT_CYCLE_INVALID")
    if cycle_index == 1:
        if previous_outcome_receipt_digest is not None:
            raise V31MonitorRuntimeContractError(
                "V31_MONITOR_ATTEMPT_PREDECESSOR_FORBIDDEN"
            )
    else:
        _digest(
            previous_outcome_receipt_digest,
            "V31_MONITOR_ATTEMPT_PREDECESSOR_REQUIRED",
        )
    document = {
        "schema_id": MONITOR_ATTEMPT_SCHEMA_ID,
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "run_id": _text(run_id, "V31_MONITOR_RUN_ID_INVALID"),
        "cycle_index": cycle_index,
        "monitor_plan_digest": _digest(
            monitor_plan_digest, "V31_MONITOR_PLAN_DIGEST_INVALID"
        ),
        "requested_at": _time_text(
            requested_at, "V31_MONITOR_ATTEMPT_TIME_INVALID"
        ),
        "attempt_number": 1,
        "retry_allowed": False,
        "previous_outcome_receipt_digest": previous_outcome_receipt_digest,
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, "monitor_attempt_digest")


def verify_monitor_resolution_attempt(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V31MonitorRuntimeContractError("V31_MONITOR_ATTEMPT_INVALID")
    try:
        supplied = verify_self_digest(document, "monitor_attempt_digest")
        rebuilt = build_monitor_resolution_attempt(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            monitor_plan_digest=document["monitor_plan_digest"],
            requested_at=document["requested_at"],
            previous_outcome_receipt_digest=document[
                "previous_outcome_receipt_digest"
            ],
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31MonitorRuntimeContractError):
            raise
        raise V31MonitorRuntimeContractError("V31_MONITOR_ATTEMPT_INVALID") from exc
    if rebuilt != dict(document) or supplied != rebuilt["monitor_attempt_digest"]:
        raise V31MonitorRuntimeContractError(
            "V31_MONITOR_ATTEMPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_public_outcome_source_record(
    *,
    run_id: str,
    cycle_index: int,
    monitor_plan_digest: str,
    reading: PublicOutcomeReading,
    raw_capture_ref: str,
    raw_capture_sha256: str,
) -> dict[str, Any]:
    """Bind one normalized public reading to its exact raw response bytes."""

    if not isinstance(reading, PublicOutcomeReading):
        raise V31MonitorRuntimeContractError("V31_MONITOR_PUBLIC_READING_REQUIRED")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31MonitorRuntimeContractError("V31_MONITOR_SOURCE_CYCLE_INVALID")
    raw_digest = _digest(
        raw_capture_sha256, "V31_MONITOR_RAW_CAPTURE_DIGEST_INVALID"
    )
    if hashlib.sha256(reading.raw_payload).hexdigest() != raw_digest:
        raise V31MonitorRuntimeContractError(
            "V31_MONITOR_RAW_CAPTURE_BINDING_MISMATCH"
        )
    normalized_observation = {
        "observable_ref": reading.observable_ref,
        "value": reading.value,
        "as_of": _time_text(reading.as_of, "V31_MONITOR_READING_TIME_INVALID"),
        "available_at": _time_text(
            reading.available_at, "V31_MONITOR_READING_TIME_INVALID"
        ),
        "missingness": reading.missingness.value,
        "quality": reading.quality.value,
        "coverage": reading.coverage,
        "conflict_state": reading.conflict_state,
        "source_request_id": reading.source_request_id,
    }
    document = {
        "schema_id": PUBLIC_SOURCE_RECORD_SCHEMA_ID,
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "run_id": _text(run_id, "V31_MONITOR_RUN_ID_INVALID"),
        "cycle_index": cycle_index,
        "monitor_plan_digest": _digest(
            monitor_plan_digest, "V31_MONITOR_PLAN_DIGEST_INVALID"
        ),
        "venue": "OKX",
        "instrument_id": "BTC-USDT-SWAP",
        "timeframe": "1H",
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "request_method": "GET",
        "request_parameters": {
            "instType": "SWAP",
            "instId": "BTC-USDT-SWAP",
        },
        "source_locator": reading.source_locator,
        "captured_at": _time_text(
            reading.captured_at, "V31_MONITOR_READING_TIME_INVALID"
        ),
        "raw_capture_ref": _text(
            raw_capture_ref, "V31_MONITOR_RAW_CAPTURE_REF_INVALID"
        ),
        "raw_capture_sha256": raw_digest,
        "normalized_observation": normalized_observation,
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, "source_record_digest")


def verify_public_outcome_source_record(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V31MonitorRuntimeContractError("V31_MONITOR_SOURCE_RECORD_INVALID")
    try:
        supplied = verify_self_digest(document, "source_record_digest")
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31MonitorRuntimeContractError(
            "V31_MONITOR_SOURCE_RECORD_DIGEST_INVALID"
        ) from exc
    observation = document.get("normalized_observation")
    if (
        set(document)
        != {
            "schema_id",
            "schema_version",
            "run_id",
            "cycle_index",
            "monitor_plan_digest",
            "venue",
            "instrument_id",
            "timeframe",
            "source_scope",
            "request_method",
            "request_parameters",
            "source_locator",
            "captured_at",
            "raw_capture_ref",
            "raw_capture_sha256",
            "normalized_observation",
            "authority_boundary",
            "source_record_digest",
        }
        or
        document.get("schema_id") != PUBLIC_SOURCE_RECORD_SCHEMA_ID
        or document.get("schema_version") != RUNTIME_SCHEMA_VERSION
        or document.get("venue") != "OKX"
        or document.get("instrument_id") != "BTC-USDT-SWAP"
        or document.get("timeframe") != "1H"
        or document.get("source_scope") != PUBLIC_SOURCE_SCOPE
        or document.get("request_method") != "GET"
        or document.get("request_parameters")
        != {"instType": "SWAP", "instId": "BTC-USDT-SWAP"}
        or document.get("authority_boundary") != _authority_boundary()
        or not isinstance(observation, Mapping)
        or set(observation)
        != {
            "observable_ref",
            "value",
            "as_of",
            "available_at",
            "missingness",
            "quality",
            "coverage",
            "conflict_state",
            "source_request_id",
        }
    ):
        raise V31MonitorRuntimeContractError("V31_MONITOR_SOURCE_RECORD_INVALID")
    _text(document.get("run_id"), "V31_MONITOR_RUN_ID_INVALID")
    cycle_index = document.get("cycle_index")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31MonitorRuntimeContractError("V31_MONITOR_SOURCE_CYCLE_INVALID")
    _digest(document.get("monitor_plan_digest"), "V31_MONITOR_PLAN_DIGEST_INVALID")
    _digest(
        document.get("raw_capture_sha256"),
        "V31_MONITOR_RAW_CAPTURE_DIGEST_INVALID",
    )
    _text(document.get("raw_capture_ref"), "V31_MONITOR_RAW_CAPTURE_REF_INVALID")
    captured = _time(document.get("captured_at"), "V31_MONITOR_READING_TIME_INVALID")
    as_of = _time(observation.get("as_of"), "V31_MONITOR_READING_TIME_INVALID")
    available = _time(
        observation.get("available_at"), "V31_MONITOR_READING_TIME_INVALID"
    )
    if as_of > available or available > captured:
        raise V31MonitorRuntimeContractError(
            "V31_MONITOR_READING_NOT_POINT_IN_TIME"
        )
    _text(
        document.get("source_locator"), "V31_MONITOR_PUBLIC_SOURCE_LOCATOR_INVALID"
    )
    locator = urlsplit(str(document["source_locator"]))
    try:
        query_pairs = parse_qsl(
            locator.query, keep_blank_values=True, strict_parsing=True
        )
    except ValueError as exc:
        raise V31MonitorRuntimeContractError(
            "V31_MONITOR_PUBLIC_SOURCE_SCOPE_INVALID"
        ) from exc
    if (
        locator.scheme != "https"
        or locator.hostname != "www.okx.com"
        or locator.port is not None
        or locator.username is not None
        or locator.password is not None
        or locator.path != "/api/v5/public/mark-price"
        or locator.fragment
        or len(query_pairs) != 2
        or dict(query_pairs)
        != {"instType": "SWAP", "instId": "BTC-USDT-SWAP"}
    ):
        raise V31MonitorRuntimeContractError("V31_MONITOR_PUBLIC_SOURCE_SCOPE_INVALID")
    try:
        missingness = ObservationMissingness(observation["missingness"])
        quality = ObservationQuality(observation["quality"])
        provisional = OutcomeObservation(
            observable_ref=observation["observable_ref"],
            value=observation["value"],
            as_of=observation["as_of"],
            available_at=observation["available_at"],
            missingness=missingness,
            quality=quality,
            coverage=observation["coverage"],
            conflict_state=observation["conflict_state"],
            source_request_id=observation["source_request_id"],
            source_record_digest=supplied,
            raw_capture_digest=document["raw_capture_sha256"],
            datum_digest="0" * 64,
        )
    except (KeyError, TypeError, ValueError, V31ExperimentContractError) as exc:
        raise V31MonitorRuntimeContractError(
            "V31_MONITOR_SOURCE_OBSERVATION_INVALID"
        ) from exc
    # Force canonical serializability of the complete normalized payload.
    canonical_digest(provisional.to_document())
    return supplied


def outcome_observation_from_source_record(
    document: Mapping[str, Any],
) -> OutcomeObservation:
    """Create the exact typed observation consumed by the outcome evaluator."""

    source_digest = verify_public_outcome_source_record(document)
    payload = document["normalized_observation"]
    datum_digest = canonical_digest(
        {
            "source_record_digest": source_digest,
            "normalized_observation": payload,
        }
    )
    return OutcomeObservation(
        observable_ref=payload["observable_ref"],
        value=payload["value"],
        as_of=payload["as_of"],
        available_at=payload["available_at"],
        missingness=ObservationMissingness(payload["missingness"]),
        quality=ObservationQuality(payload["quality"]),
        coverage=payload["coverage"],
        conflict_state=payload["conflict_state"],
        source_request_id=payload["source_request_id"],
        source_record_digest=source_digest,
        raw_capture_digest=document["raw_capture_sha256"],
        datum_digest=datum_digest,
    )


__all__ = [
    "MONITOR_ATTEMPT_SCHEMA_ID",
    "MONITOR_CHECKPOINT_SCHEMA_ID",
    "MONITOR_CHECKPOINT_SCHEMA_VERSION",
    "MONITOR_FAILURE_SCHEMA_ID",
    "OUTCOME_EVALUATOR_VERSION",
    "PUBLIC_SOURCE_RECORD_SCHEMA_ID",
    "PUBLIC_SOURCE_SCOPE",
    "PublicOutcomeReading",
    "V31MonitorRuntimeContractError",
    "build_monitor_resolution_attempt",
    "build_public_outcome_source_record",
    "monitor_cycle_root",
    "outcome_observation_from_source_record",
    "verify_monitor_resolution_attempt",
    "verify_public_outcome_source_record",
]
