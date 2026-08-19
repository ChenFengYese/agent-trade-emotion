"""Typed V3.2 source qualification and per-cycle admission contracts.

This module owns the sole formal ``theory_paper_v32_cycle_source_admission_v1``
shape.  The admission binds the complete loader receipt and every typed source
artifact by both semantic digest and physical SHA-256.  Consumers must call the
application replay verifier; a digest-only projection is not an admission.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest
from .governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD as GOVERNING_AUTHORITY_DOCUMENT_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID as GOVERNING_AUTHORITY_SCHEMA_ID,
)


class V32CycleSourceAdmissionError(ValueError):
    """A typed V3.2 source or admission invariant failed closed."""


SCHEMA_VERSION = "1.0.0"
LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION = "1.0.0"
SOURCE_ADMISSION_SCHEMA_VERSION = "2.0.0"
SOURCE_ADMISSION_SCHEMA_ID = "theory_paper_v32_cycle_source_admission_v1"
SOURCE_ADMISSION_DIGEST_FIELD = "cycle_source_admission_digest"
PIT_REGISTRY_SCHEMA_ID = "theory_paper_v32_verified_pit_evidence_registry_v1"
PIT_REGISTRY_DIGEST_FIELD = "pit_evidence_registry_digest"
AUTHORITY_PROJECTION_SCHEMA_ID = "theory_paper_v32_active_authority_projection_v2"
ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD = "active_authority_projection_digest"
GOVERNING_AUTHORITY_DIGEST_FIELD = "governing_authority_digest"
CAPTURE_SCHEMA_ID = "theory_paper_v32_public_source_capture_v1"
CAPTURE_DIGEST_FIELD = "public_source_capture_digest"
SNAPSHOT_SCHEMA_ID = "native_btc_public_market_snapshot"
SNAPSHOT_DIGEST_FIELD = "native_market_snapshot_digest"
QUALIFICATION_SCHEMA_ID = "theory_paper_v32_formal_source_qualification_v1"
QUALIFICATION_DIGEST_FIELD = "formal_source_qualification_digest"
FULL_LOADER_SCHEMA_ID = "theory_paper_v32_cycle_source_full_loader_receipt_v1"
FULL_LOADER_DIGEST_FIELD = "cycle_source_full_loader_receipt_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
INSTRUMENT = {
    "venue": "OKX",
    "instrument_id": "BTC-USDT-SWAP",
    "market_type": "PERPETUAL_SWAP",
    "underlying_symbol": "BTC-USDT",
}
MAX_SOURCE_AGE_SECONDS = 900
MAX_CLOSED_BAR_AGE_SECONDS = 1800

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {"relative_ref", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_RAW_BINDING_FIELDS = frozenset(
    {"relative_ref", "semantic_digest", "physical_sha256"}
)
_PREVIOUS_FIELDS = frozenset(
    {
        "status",
        "previous_cycle_source_admission_binding",
        "prior_snapshot_binding",
        "prior_open_interest_datum_digest",
        "prior_open_interest_status",
        "prior_open_interest_zero_imputed",
    }
)
_BOUNDARY_FIELDS = frozenset(
    {
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "account_data_accessed",
        "paper_trading",
        "live_trading",
        "order_submission",
        "order_data_accessed",
        "credential_access",
        "funds_access",
        "portfolio_mutation",
    }
)
_AUTHORITY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "authorized_run_id",
        "recorded_at",
        "experiment_contract_digest",
        "governing_authority_binding",
        GOVERNING_AUTHORITY_DIGEST_FIELD,
        "total_cycles",
        "instrument",
        *_BOUNDARY_FIELDS,
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    }
)
_CAPTURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "run_id",
        "cycle_index",
        "attempt_id",
        "attempt_number",
        "retry_allowed",
        "request_id",
        "request_operation",
        "request_started_at",
        "response_received_at",
        "instrument_id",
        "raw_response_binding",
        *_BOUNDARY_FIELDS,
        CAPTURE_DIGEST_FIELD,
    }
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "run_id",
        "cycle_index",
        "instrument_id",
        "capture_attempt_digest",
        "as_of",
        "available_at",
        "closed_bar_timeframe",
        "closed_bar_as_of",
        "closed_bar_confirmed",
        "open_interest_datum_digest",
        "open_interest_status",
        "open_interest_zero_imputed",
        "point_in_time",
        "missing_is_zero",
        *_BOUNDARY_FIELDS,
        SNAPSHOT_DIGEST_FIELD,
    }
)
_PIT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "members",
        "upstream_schema_id",
        "upstream_digest_field",
        "upstream_semantic_digest",
        "full_verification_receipt_digest",
        "source_scope",
        "external_execution_authority",
        "executable",
        PIT_REGISTRY_DIGEST_FIELD,
    }
)
_QUALIFICATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "run_id",
        "cycle_index",
        "started_at",
        "completed_at",
        "decision_time",
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
        GOVERNING_AUTHORITY_DIGEST_FIELD,
        "active_authority_recorded_at",
        "experiment_contract_digest",
        "instrument",
        "attempt_count",
        "retry_allowed",
        "capture_binding",
        "snapshot_binding",
        "pit_registry_binding",
        "formal_source_qualification",
        "qualification_is_start_authority",
        *_BOUNDARY_FIELDS,
        QUALIFICATION_DIGEST_FIELD,
    }
)
_COPY_FIELDS = frozenset(
    {
        "artifact_role",
        "artifact_id",
        "source_relative_ref",
        "target_relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "source_physical_sha256",
        "target_physical_sha256",
        "exact_bytes_copied",
        "readback_verified",
    }
)
_FULL_LOADER_V1_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "admitted_at",
        "decision_time",
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
        GOVERNING_AUTHORITY_DIGEST_FIELD,
        "active_authority_recorded_at",
        "experiment_contract_digest",
        "qualification_binding",
        "capture_binding",
        "current_snapshot_binding",
        "pit_registry_binding",
        "qualification_started_at",
        "qualification_completed_at",
        "earliest_capture_started_at",
        "latest_capture_received_at",
        "closed_bar_as_of",
        "closed_bar_timeframe",
        "current_open_interest_datum_digest",
        "current_open_interest_status",
        "current_open_interest_zero_imputed",
        "previous_source_context",
        "artifact_copies",
        "single_source_collection_transaction",
        "attempt_count",
        "retry_allowed",
        "point_in_time_verified",
        "closed_bar_verified",
        "freshness_verified",
        "exact_bytes_copied_and_read_back",
        "cas_predecessor_admission_digest",
        "qualification_is_start_authority",
        *_BOUNDARY_FIELDS,
        FULL_LOADER_DIGEST_FIELD,
    }
)
_FULL_LOADER_V2_FIELDS = frozenset({*_FULL_LOADER_V1_FIELDS, "source_cutoff_at"})
_ADMISSION_V1_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_time",
        "admitted_at",
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
        GOVERNING_AUTHORITY_DIGEST_FIELD,
        "experiment_contract_digest",
        "qualification_binding",
        "capture_binding",
        "current_snapshot_binding",
        "pit_registry_binding",
        "previous_source_context",
        "full_loader_receipt_binding",
        "current_open_interest_datum_digest",
        "current_open_interest_status",
        "current_open_interest_zero_imputed",
        "single_source_collection_transaction",
        "attempt_count",
        "retry_allowed",
        "point_in_time_verified",
        "closed_bar_verified",
        "freshness_verified",
        "exact_bytes_copied_and_read_back",
        "qualification_is_start_authority",
        *_BOUNDARY_FIELDS,
        SOURCE_ADMISSION_DIGEST_FIELD,
    }
)
_ADMISSION_V2_FIELDS = frozenset({*_ADMISSION_V1_FIELDS, "source_cutoff_at"})


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32CycleSourceAdmissionError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32CycleSourceAdmissionError(code)
    return value


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_CYCLE_INVALID")
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32CycleSourceAdmissionError(code) from exc
    if parsed.tzinfo is None:
        raise V32CycleSourceAdmissionError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V32CycleSourceAdmissionError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _relative(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32CycleSourceAdmissionError(code)
    return text


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "account_access": False,
        "account_data_accessed": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "order_data_accessed": False,
        "credential_access": False,
        "funds_access": False,
        "portfolio_mutation": False,
    }


def _assert_boundary(document: Mapping[str, Any], code: str) -> None:
    if any(document.get(key) != value for key, value in _boundary().items()):
        raise V32CycleSourceAdmissionError(code)


def _binding(
    value: Any,
    code: str,
    *,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32CycleSourceAdmissionError(code)
    result = {
        "relative_ref": _relative(value.get("relative_ref"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": str(_digest(value.get("semantic_digest"), code)),
        "physical_sha256": str(_digest(value.get("physical_sha256"), code)),
    }
    if (
        (schema_id is not None and result["schema_id"] != schema_id)
        or (digest_field is not None and result["digest_field"] != digest_field)
    ):
        raise V32CycleSourceAdmissionError(code)
    return result


def _raw_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _RAW_BINDING_FIELDS:
        raise V32CycleSourceAdmissionError(code)
    result = {
        "relative_ref": _relative(value.get("relative_ref"), code),
        "semantic_digest": str(_digest(value.get("semantic_digest"), code)),
        "physical_sha256": str(_digest(value.get("physical_sha256"), code)),
    }
    if result["semantic_digest"] != result["physical_sha256"]:
        raise V32CycleSourceAdmissionError(code)
    return result


def cycle_source_admission_ref(cycle_index: int) -> str:
    return f"cycles/{_cycle(cycle_index):04d}/market/v32-source-admission/cycle-source-admission.json"


def cycle_source_full_loader_ref(cycle_index: int) -> str:
    return f"cycles/{_cycle(cycle_index):04d}/market/v32-source-admission/full-loader-receipt.json"


def qualification_ref(qualification_id: str) -> str:
    key = _text(qualification_id, "V32_SOURCE_QUALIFICATION_ID_INVALID")
    if "/" in key or "\\" in key or key in {".", ".."}:
        raise V32CycleSourceAdmissionError("V32_SOURCE_QUALIFICATION_ID_INVALID")
    return f"qualifications/{key}/qualification.json"


def build_v32_active_authority_projection(
    *,
    run_id: str,
    recorded_at: str,
    experiment_contract_digest: str,
    governing_authority_binding: Mapping[str, Any],
) -> dict[str, Any]:
    governing_binding = _binding(
        governing_authority_binding,
        "V32_SOURCE_AUTHORITY_GOVERNING_BINDING_INVALID",
        schema_id=GOVERNING_AUTHORITY_SCHEMA_ID,
        digest_field=GOVERNING_AUTHORITY_DOCUMENT_DIGEST_FIELD,
    )
    return self_digest(
        {
            "schema_id": AUTHORITY_PROJECTION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "authorized_run_id": _text(run_id, "V32_SOURCE_AUTHORITY_INVALID"),
            "recorded_at": _time(recorded_at, "V32_SOURCE_AUTHORITY_INVALID"),
            "experiment_contract_digest": _digest(
                experiment_contract_digest, "V32_SOURCE_AUTHORITY_INVALID"
            ),
            "governing_authority_binding": governing_binding,
            GOVERNING_AUTHORITY_DIGEST_FIELD: governing_binding[
                "semantic_digest"
            ],
            "total_cycles": 16,
            "instrument": dict(INSTRUMENT),
            **_boundary(),
        },
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    )


def verify_v32_active_authority_projection(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _AUTHORITY_FIELDS:
        raise V32CycleSourceAdmissionError("V32_SOURCE_AUTHORITY_INVALID")
    try:
        supplied = verify_self_digest(
            document, ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
        )
        rebuilt = build_v32_active_authority_projection(
            run_id=document["authorized_run_id"],
            recorded_at=document["recorded_at"],
            experiment_contract_digest=document["experiment_contract_digest"],
            governing_authority_binding=document["governing_authority_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleSourceAdmissionError):
            raise
        raise V32CycleSourceAdmissionError("V32_SOURCE_AUTHORITY_INVALID") from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD]
    ):
        raise V32CycleSourceAdmissionError("V32_SOURCE_AUTHORITY_INVALID")
    _assert_boundary(document, "V32_SOURCE_AUTHORITY_BOUNDARY_INVALID")
    return supplied


def build_v32_public_source_capture(
    *,
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    attempt_id: str,
    request_id: str,
    request_started_at: str,
    response_received_at: str,
    raw_response_binding: Mapping[str, Any],
) -> dict[str, Any]:
    cycle = _cycle(cycle_index)
    started = _moment(request_started_at, "V32_SOURCE_CAPTURE_TIME_INVALID")
    received = _moment(response_received_at, "V32_SOURCE_CAPTURE_TIME_INVALID")
    if received < started:
        raise V32CycleSourceAdmissionError("V32_SOURCE_CAPTURE_TIME_INVALID")
    return self_digest(
        {
            "schema_id": CAPTURE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "qualification_id": _text(
                qualification_id, "V32_SOURCE_CAPTURE_IDENTITY_INVALID"
            ),
            "run_id": _text(run_id, "V32_SOURCE_CAPTURE_IDENTITY_INVALID"),
            "cycle_index": cycle,
            "attempt_id": _text(attempt_id, "V32_SOURCE_CAPTURE_ATTEMPT_INVALID"),
            "attempt_number": 1,
            "retry_allowed": False,
            "request_id": _text(request_id, "V32_SOURCE_CAPTURE_REQUEST_INVALID"),
            "request_operation": "GET_PUBLIC_MARKET_BUNDLE",
            "request_started_at": _time(
                request_started_at, "V32_SOURCE_CAPTURE_TIME_INVALID"
            ),
            "response_received_at": _time(
                response_received_at, "V32_SOURCE_CAPTURE_TIME_INVALID"
            ),
            "instrument_id": "BTC-USDT-SWAP",
            "raw_response_binding": _raw_binding(
                raw_response_binding, "V32_SOURCE_CAPTURE_RAW_INVALID"
            ),
            **_boundary(),
        },
        CAPTURE_DIGEST_FIELD,
    )


def verify_v32_public_source_capture(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _CAPTURE_FIELDS:
        raise V32CycleSourceAdmissionError("V32_SOURCE_CAPTURE_INVALID")
    try:
        supplied = verify_self_digest(document, CAPTURE_DIGEST_FIELD)
        rebuilt = build_v32_public_source_capture(
            qualification_id=document["qualification_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            attempt_id=document["attempt_id"],
            request_id=document["request_id"],
            request_started_at=document["request_started_at"],
            response_received_at=document["response_received_at"],
            raw_response_binding=document["raw_response_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleSourceAdmissionError):
            raise
        raise V32CycleSourceAdmissionError("V32_SOURCE_CAPTURE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[CAPTURE_DIGEST_FIELD]:
        raise V32CycleSourceAdmissionError("V32_SOURCE_CAPTURE_INVALID")
    _assert_boundary(document, "V32_SOURCE_CAPTURE_BOUNDARY_INVALID")
    return supplied


def build_v32_public_market_snapshot(
    *,
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    capture_attempt_digest: str,
    as_of: str,
    available_at: str,
    closed_bar_as_of: str,
    open_interest_datum_digest: str,
    open_interest_status: str,
) -> dict[str, Any]:
    observed = _moment(as_of, "V32_SOURCE_SNAPSHOT_TIME_INVALID")
    available = _moment(available_at, "V32_SOURCE_SNAPSHOT_TIME_INVALID")
    closed = _moment(closed_bar_as_of, "V32_SOURCE_SNAPSHOT_TIME_INVALID")
    if not closed <= observed <= available:
        raise V32CycleSourceAdmissionError("V32_SOURCE_SNAPSHOT_TIME_INVALID")
    if open_interest_status not in {"OBSERVED", "UNKNOWN"}:
        raise V32CycleSourceAdmissionError("V32_SOURCE_SNAPSHOT_OI_INVALID")
    return self_digest(
        {
            "schema_id": SNAPSHOT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "qualification_id": _text(
                qualification_id, "V32_SOURCE_SNAPSHOT_IDENTITY_INVALID"
            ),
            "run_id": _text(run_id, "V32_SOURCE_SNAPSHOT_IDENTITY_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "instrument_id": "BTC-USDT-SWAP",
            "capture_attempt_digest": _digest(
                capture_attempt_digest, "V32_SOURCE_SNAPSHOT_CAPTURE_INVALID"
            ),
            "as_of": _time(as_of, "V32_SOURCE_SNAPSHOT_TIME_INVALID"),
            "available_at": _time(
                available_at, "V32_SOURCE_SNAPSHOT_TIME_INVALID"
            ),
            "closed_bar_timeframe": "15m",
            "closed_bar_as_of": _time(
                closed_bar_as_of, "V32_SOURCE_SNAPSHOT_TIME_INVALID"
            ),
            "closed_bar_confirmed": True,
            "open_interest_datum_digest": _digest(
                open_interest_datum_digest, "V32_SOURCE_SNAPSHOT_OI_INVALID"
            ),
            "open_interest_status": open_interest_status,
            "open_interest_zero_imputed": False,
            "point_in_time": True,
            "missing_is_zero": False,
            **_boundary(),
        },
        SNAPSHOT_DIGEST_FIELD,
    )


def verify_v32_public_market_snapshot(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _SNAPSHOT_FIELDS:
        raise V32CycleSourceAdmissionError("V32_SOURCE_SNAPSHOT_INVALID")
    try:
        supplied = verify_self_digest(document, SNAPSHOT_DIGEST_FIELD)
        rebuilt = build_v32_public_market_snapshot(
            qualification_id=document["qualification_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            capture_attempt_digest=document["capture_attempt_digest"],
            as_of=document["as_of"],
            available_at=document["available_at"],
            closed_bar_as_of=document["closed_bar_as_of"],
            open_interest_datum_digest=document["open_interest_datum_digest"],
            open_interest_status=document["open_interest_status"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleSourceAdmissionError):
            raise
        raise V32CycleSourceAdmissionError("V32_SOURCE_SNAPSHOT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[SNAPSHOT_DIGEST_FIELD]:
        raise V32CycleSourceAdmissionError("V32_SOURCE_SNAPSHOT_INVALID")
    _assert_boundary(document, "V32_SOURCE_SNAPSHOT_BOUNDARY_INVALID")
    return supplied


def build_v32_pit_evidence_registry(
    *,
    run_id: str,
    cycle_index: int,
    as_of: str,
    members: Sequence[str],
    upstream_snapshot_digest: str,
    capture_digest: str,
) -> dict[str, Any]:
    if isinstance(members, (str, bytes)) or not isinstance(members, Sequence):
        raise V32CycleSourceAdmissionError("V32_SOURCE_PIT_MEMBERS_INVALID")
    member_rows = [str(_digest(item, "V32_SOURCE_PIT_MEMBERS_INVALID")) for item in members]
    if not member_rows or member_rows != sorted(set(member_rows)):
        raise V32CycleSourceAdmissionError("V32_SOURCE_PIT_MEMBERS_INVALID")
    return self_digest(
        {
            "schema_id": PIT_REGISTRY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": _text(run_id, "V32_SOURCE_PIT_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "as_of": _time(as_of, "V32_SOURCE_PIT_INVALID"),
            "members": member_rows,
            "upstream_schema_id": SNAPSHOT_SCHEMA_ID,
            "upstream_digest_field": SNAPSHOT_DIGEST_FIELD,
            "upstream_semantic_digest": _digest(
                upstream_snapshot_digest, "V32_SOURCE_PIT_INVALID"
            ),
            "full_verification_receipt_digest": _digest(
                capture_digest, "V32_SOURCE_PIT_INVALID"
            ),
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        PIT_REGISTRY_DIGEST_FIELD,
    )


def verify_v32_pit_evidence_registry(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _PIT_FIELDS:
        raise V32CycleSourceAdmissionError("V32_SOURCE_PIT_INVALID")
    try:
        supplied = verify_self_digest(document, PIT_REGISTRY_DIGEST_FIELD)
        rebuilt = build_v32_pit_evidence_registry(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            as_of=document["as_of"],
            members=document["members"],
            upstream_snapshot_digest=document["upstream_semantic_digest"],
            capture_digest=document["full_verification_receipt_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleSourceAdmissionError):
            raise
        raise V32CycleSourceAdmissionError("V32_SOURCE_PIT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[PIT_REGISTRY_DIGEST_FIELD]:
        raise V32CycleSourceAdmissionError("V32_SOURCE_PIT_INVALID")
    return supplied


def build_v32_formal_source_qualification(
    *,
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    started_at: str,
    completed_at: str,
    decision_time: str,
    active_authority_projection_digest: str,
    governing_authority_digest: str,
    active_authority_recorded_at: str,
    experiment_contract_digest: str,
    capture_binding: Mapping[str, Any],
    snapshot_binding: Mapping[str, Any],
    pit_registry_binding: Mapping[str, Any],
) -> dict[str, Any]:
    authority_time = _moment(
        active_authority_recorded_at, "V32_SOURCE_QUALIFICATION_TIME_INVALID"
    )
    started = _moment(started_at, "V32_SOURCE_QUALIFICATION_TIME_INVALID")
    completed = _moment(completed_at, "V32_SOURCE_QUALIFICATION_TIME_INVALID")
    decision = _moment(decision_time, "V32_SOURCE_QUALIFICATION_TIME_INVALID")
    if not authority_time < started <= completed <= decision:
        raise V32CycleSourceAdmissionError("V32_SOURCE_QUALIFICATION_TIME_INVALID")
    return self_digest(
        {
            "schema_id": QUALIFICATION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "qualification_id": _text(
                qualification_id, "V32_SOURCE_QUALIFICATION_IDENTITY_INVALID"
            ),
            "run_id": _text(run_id, "V32_SOURCE_QUALIFICATION_IDENTITY_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "started_at": _time(started_at, "V32_SOURCE_QUALIFICATION_TIME_INVALID"),
            "completed_at": _time(
                completed_at, "V32_SOURCE_QUALIFICATION_TIME_INVALID"
            ),
            "decision_time": _time(
                decision_time, "V32_SOURCE_QUALIFICATION_TIME_INVALID"
            ),
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD: _digest(
                active_authority_projection_digest,
                "V32_SOURCE_QUALIFICATION_INVALID",
            ),
            GOVERNING_AUTHORITY_DIGEST_FIELD: _digest(
                governing_authority_digest,
                "V32_SOURCE_QUALIFICATION_INVALID",
            ),
            "active_authority_recorded_at": _time(
                active_authority_recorded_at,
                "V32_SOURCE_QUALIFICATION_TIME_INVALID",
            ),
            "experiment_contract_digest": _digest(
                experiment_contract_digest, "V32_SOURCE_QUALIFICATION_INVALID"
            ),
            "instrument": dict(INSTRUMENT),
            "attempt_count": 1,
            "retry_allowed": False,
            "capture_binding": _binding(
                capture_binding,
                "V32_SOURCE_QUALIFICATION_CAPTURE_INVALID",
                schema_id=CAPTURE_SCHEMA_ID,
                digest_field=CAPTURE_DIGEST_FIELD,
            ),
            "snapshot_binding": _binding(
                snapshot_binding,
                "V32_SOURCE_QUALIFICATION_SNAPSHOT_INVALID",
                schema_id=SNAPSHOT_SCHEMA_ID,
                digest_field=SNAPSHOT_DIGEST_FIELD,
            ),
            "pit_registry_binding": _binding(
                pit_registry_binding,
                "V32_SOURCE_QUALIFICATION_PIT_INVALID",
                schema_id=PIT_REGISTRY_SCHEMA_ID,
                digest_field=PIT_REGISTRY_DIGEST_FIELD,
            ),
            "formal_source_qualification": True,
            "qualification_is_start_authority": False,
            **_boundary(),
        },
        QUALIFICATION_DIGEST_FIELD,
    )


def verify_v32_formal_source_qualification(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _QUALIFICATION_FIELDS:
        raise V32CycleSourceAdmissionError("V32_SOURCE_QUALIFICATION_INVALID")
    try:
        supplied = verify_self_digest(document, QUALIFICATION_DIGEST_FIELD)
        rebuilt = build_v32_formal_source_qualification(
            qualification_id=document["qualification_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            decision_time=document["decision_time"],
            active_authority_projection_digest=document[
                ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
            ],
            governing_authority_digest=document[
                GOVERNING_AUTHORITY_DIGEST_FIELD
            ],
            active_authority_recorded_at=document["active_authority_recorded_at"],
            experiment_contract_digest=document["experiment_contract_digest"],
            capture_binding=document["capture_binding"],
            snapshot_binding=document["snapshot_binding"],
            pit_registry_binding=document["pit_registry_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleSourceAdmissionError):
            raise
        raise V32CycleSourceAdmissionError("V32_SOURCE_QUALIFICATION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[QUALIFICATION_DIGEST_FIELD]:
        raise V32CycleSourceAdmissionError("V32_SOURCE_QUALIFICATION_INVALID")
    _assert_boundary(document, "V32_SOURCE_QUALIFICATION_BOUNDARY_INVALID")
    return supplied


def _previous_context(value: Any, *, cycle_index: int) -> dict[str, Any]:
    code = "V32_CYCLE_SOURCE_PREVIOUS_CONTEXT_INVALID"
    if not isinstance(value, Mapping) or set(value) != _PREVIOUS_FIELDS:
        raise V32CycleSourceAdmissionError(code)
    if cycle_index == 1:
        expected = {
            "status": "GENESIS_NO_PRIOR_SOURCE_CONTEXT",
            "previous_cycle_source_admission_binding": None,
            "prior_snapshot_binding": None,
            "prior_open_interest_datum_digest": None,
            "prior_open_interest_status": "NOT_APPLICABLE_GENESIS",
            "prior_open_interest_zero_imputed": False,
        }
        if dict(value) != expected:
            raise V32CycleSourceAdmissionError(code)
        return expected
    previous_admission = _binding(
        value.get("previous_cycle_source_admission_binding"),
        code,
        schema_id=SOURCE_ADMISSION_SCHEMA_ID,
        digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
    )
    prior_snapshot = _binding(
        value.get("prior_snapshot_binding"),
        code,
        schema_id=SNAPSHOT_SCHEMA_ID,
        digest_field=SNAPSHOT_DIGEST_FIELD,
    )
    component = f"{cycle_index - 1:04d}"
    if (
        value.get("status") != "BOUND_TO_PREVIOUS_ACCEPTED_V32_CYCLE"
        or value.get("prior_open_interest_status") not in {"OBSERVED", "UNKNOWN"}
        or value.get("prior_open_interest_zero_imputed") is not False
        or _digest(value.get("prior_open_interest_datum_digest"), code) is None
        or component not in PurePosixPath(previous_admission["relative_ref"]).parts
        or component not in PurePosixPath(prior_snapshot["relative_ref"]).parts
    ):
        raise V32CycleSourceAdmissionError(code)
    return {
        "status": "BOUND_TO_PREVIOUS_ACCEPTED_V32_CYCLE",
        "previous_cycle_source_admission_binding": previous_admission,
        "prior_snapshot_binding": prior_snapshot,
        "prior_open_interest_datum_digest": value["prior_open_interest_datum_digest"],
        "prior_open_interest_status": value["prior_open_interest_status"],
        "prior_open_interest_zero_imputed": False,
    }


def _copy_row(value: Any, *, cycle_index: int) -> dict[str, Any]:
    code = "V32_CYCLE_SOURCE_COPY_INVALID"
    if not isinstance(value, Mapping) or set(value) != _COPY_FIELDS:
        raise V32CycleSourceAdmissionError(code)
    role = _text(value.get("artifact_role"), code)
    if role not in {
        "SOURCE_QUALIFICATION",
        "SOURCE_CAPTURE",
        "MARKET_SNAPSHOT",
        "PIT_REGISTRY",
        "RAW_RESPONSE",
    }:
        raise V32CycleSourceAdmissionError(code)
    source = _relative(value.get("source_relative_ref"), code)
    target = _relative(value.get("target_relative_ref"), code)
    if not target.startswith(f"cycles/{cycle_index:04d}/market/v32-source-admission/"):
        raise V32CycleSourceAdmissionError(code)
    source_physical = str(_digest(value.get("source_physical_sha256"), code))
    target_physical = str(_digest(value.get("target_physical_sha256"), code))
    semantic = str(_digest(value.get("semantic_digest"), code))
    if (
        source_physical != target_physical
        or value.get("exact_bytes_copied") is not True
        or value.get("readback_verified") is not True
    ):
        raise V32CycleSourceAdmissionError(code)
    schema = value.get("schema_id")
    digest_field = value.get("digest_field")
    if role == "RAW_RESPONSE":
        if schema is not None or digest_field is not None or semantic != source_physical:
            raise V32CycleSourceAdmissionError(code)
    else:
        schema = _text(schema, code)
        digest_field = _text(digest_field, code)
    return {
        "artifact_role": role,
        "artifact_id": _text(value.get("artifact_id"), code),
        "source_relative_ref": source,
        "target_relative_ref": target,
        "schema_id": schema,
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "source_physical_sha256": source_physical,
        "target_physical_sha256": target_physical,
        "exact_bytes_copied": True,
        "readback_verified": True,
    }


def _copy_rows(value: Any, *, cycle_index: int) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_COPY_SET_INVALID")
    rows = [_copy_row(row, cycle_index=cycle_index) for row in value]
    if rows != sorted(rows, key=lambda row: (row["artifact_role"], row["artifact_id"])):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_COPY_SET_INVALID")
    if len({(row["artifact_role"], row["artifact_id"]) for row in rows}) != len(rows):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_COPY_SET_INVALID")
    by_role = {role: [row for row in rows if row["artifact_role"] == role] for role in {
        "SOURCE_QUALIFICATION", "SOURCE_CAPTURE", "MARKET_SNAPSHOT", "PIT_REGISTRY", "RAW_RESPONSE"
    }}
    if any(len(by_role[role]) != 1 for role in by_role):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_COPY_SET_INVALID")
    if (
        len({row["source_relative_ref"] for row in rows}) != len(rows)
        or len({row["target_relative_ref"] for row in rows}) != len(rows)
    ):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_COPY_SET_INVALID")
    return rows


def build_v32_cycle_source_full_loader_receipt(
    *,
    run_id: str,
    cycle_index: int,
    admitted_at: str,
    decision_time: str,
    active_authority_projection_digest: str,
    governing_authority_digest: str,
    active_authority_recorded_at: str,
    experiment_contract_digest: str,
    qualification_binding: Mapping[str, Any],
    capture_binding: Mapping[str, Any],
    current_snapshot_binding: Mapping[str, Any],
    pit_registry_binding: Mapping[str, Any],
    qualification_started_at: str,
    qualification_completed_at: str,
    earliest_capture_started_at: str,
    latest_capture_received_at: str,
    closed_bar_as_of: str,
    current_open_interest_datum_digest: str,
    current_open_interest_status: str,
    previous_source_context: Mapping[str, Any],
    artifact_copies: Sequence[Mapping[str, Any]],
    source_cutoff_at: str | None = None,
) -> dict[str, Any]:
    """Build v2 when a cutoff is supplied; omission is reserved for legacy v1."""

    schema_version = (
        LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION
        if source_cutoff_at is None
        else SOURCE_ADMISSION_SCHEMA_VERSION
    )
    cycle = _cycle(cycle_index)
    authority_time = _moment(
        active_authority_recorded_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
    )
    qualification_start = _moment(
        qualification_started_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
    )
    capture_start = _moment(
        earliest_capture_started_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
    )
    capture_end = _moment(
        latest_capture_received_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
    )
    qualification_end = _moment(
        qualification_completed_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
    )
    admitted = _moment(admitted_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID")
    decision_text = _time(
        decision_time, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
    )
    decision = _moment(decision_text, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID")
    closed = _moment(closed_bar_as_of, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID")
    if schema_version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION:
        if source_cutoff_at is not None:
            raise V32CycleSourceAdmissionError(
                "V32_CYCLE_SOURCE_SCHEMA_VERSION_INVALID"
            )
        chronology_valid = (
            authority_time
            < qualification_start
            <= capture_start
            <= capture_end
            <= qualification_end
            <= admitted
            <= decision
        )
        freshness_clock = decision
        source_cutoff_text = None
    elif schema_version == SOURCE_ADMISSION_SCHEMA_VERSION:
        source_cutoff_text = _time(
            source_cutoff_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
        )
        source_cutoff = _moment(
            source_cutoff_text, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"
        )
        if decision_text != source_cutoff_text:
            raise V32CycleSourceAdmissionError(
                "V32_CYCLE_SOURCE_CUTOFF_ALIAS_INVALID"
            )
        chronology_valid = (
            authority_time
            < qualification_start
            <= capture_start
            <= capture_end
            <= qualification_end
            <= source_cutoff
            <= admitted
        )
        freshness_clock = source_cutoff
    else:
        raise V32CycleSourceAdmissionError(
            "V32_CYCLE_SOURCE_SCHEMA_VERSION_INVALID"
        )
    if not chronology_valid:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_CHRONOLOGY_INVALID")
    if (
        freshness_clock - capture_end > timedelta(seconds=MAX_SOURCE_AGE_SECONDS)
        or not closed <= capture_end
        or freshness_clock - closed > timedelta(seconds=MAX_CLOSED_BAR_AGE_SECONDS)
    ):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_FRESHNESS_INVALID")
    if current_open_interest_status not in {"OBSERVED", "UNKNOWN"}:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_OI_INVALID")
    context = _previous_context(previous_source_context, cycle_index=cycle)
    predecessor = (
        None
        if cycle == 1
        else context["previous_cycle_source_admission_binding"]["semantic_digest"]
    )
    rows = _copy_rows(artifact_copies, cycle_index=cycle)
    role_specs = {
        "SOURCE_QUALIFICATION": (QUALIFICATION_SCHEMA_ID, QUALIFICATION_DIGEST_FIELD, qualification_binding),
        "SOURCE_CAPTURE": (CAPTURE_SCHEMA_ID, CAPTURE_DIGEST_FIELD, capture_binding),
        "MARKET_SNAPSHOT": (SNAPSHOT_SCHEMA_ID, SNAPSHOT_DIGEST_FIELD, current_snapshot_binding),
        "PIT_REGISTRY": (PIT_REGISTRY_SCHEMA_ID, PIT_REGISTRY_DIGEST_FIELD, pit_registry_binding),
    }
    normalized_bindings: dict[str, dict[str, str]] = {}
    for role, (schema, field, binding) in role_specs.items():
        normalized = _binding(binding, "V32_CYCLE_SOURCE_BINDING_INVALID", schema_id=schema, digest_field=field)
        normalized_bindings[role] = normalized
        row = next(item for item in rows if item["artifact_role"] == role)
        if (
            row["schema_id"] != schema
            or row["digest_field"] != field
            or row["semantic_digest"] != normalized["semantic_digest"]
            or row["source_physical_sha256"] != normalized["physical_sha256"]
        ):
            raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_BINDING_INVALID")
    body = {
            "schema_id": FULL_LOADER_SCHEMA_ID,
            "schema_version": schema_version,
            "run_id": _text(run_id, "V32_CYCLE_SOURCE_IDENTITY_INVALID"),
            "cycle_index": cycle,
            "admitted_at": _time(admitted_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"),
            "decision_time": decision_text,
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD: _digest(
                active_authority_projection_digest,
                "V32_CYCLE_SOURCE_AUTHORITY_INVALID",
            ),
            GOVERNING_AUTHORITY_DIGEST_FIELD: _digest(
                governing_authority_digest,
                "V32_CYCLE_SOURCE_AUTHORITY_INVALID",
            ),
            "active_authority_recorded_at": _time(active_authority_recorded_at, "V32_CYCLE_SOURCE_AUTHORITY_INVALID"),
            "experiment_contract_digest": _digest(experiment_contract_digest, "V32_CYCLE_SOURCE_CONTRACT_INVALID"),
            "qualification_binding": normalized_bindings["SOURCE_QUALIFICATION"],
            "capture_binding": normalized_bindings["SOURCE_CAPTURE"],
            "current_snapshot_binding": normalized_bindings["MARKET_SNAPSHOT"],
            "pit_registry_binding": normalized_bindings["PIT_REGISTRY"],
            "qualification_started_at": _time(qualification_started_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"),
            "qualification_completed_at": _time(qualification_completed_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"),
            "earliest_capture_started_at": _time(earliest_capture_started_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"),
            "latest_capture_received_at": _time(latest_capture_received_at, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"),
            "closed_bar_as_of": _time(closed_bar_as_of, "V32_CYCLE_SOURCE_CHRONOLOGY_INVALID"),
            "closed_bar_timeframe": "15m",
            "current_open_interest_datum_digest": _digest(current_open_interest_datum_digest, "V32_CYCLE_SOURCE_OI_INVALID"),
            "current_open_interest_status": current_open_interest_status,
            "current_open_interest_zero_imputed": False,
            "previous_source_context": context,
            "artifact_copies": rows,
            "single_source_collection_transaction": True,
            "attempt_count": 1,
            "retry_allowed": False,
            "point_in_time_verified": True,
            "closed_bar_verified": True,
            "freshness_verified": True,
            "exact_bytes_copied_and_read_back": True,
            "cas_predecessor_admission_digest": predecessor,
            "qualification_is_start_authority": False,
            **_boundary(),
        }
    if source_cutoff_text is not None:
        body["source_cutoff_at"] = source_cutoff_text
    return self_digest(body, FULL_LOADER_DIGEST_FIELD)


def verify_v32_cycle_source_full_loader_receipt(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_FULL_LOADER_INVALID")
    version = document.get("schema_version")
    if version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION:
        fields = _FULL_LOADER_V1_FIELDS
    elif version == SOURCE_ADMISSION_SCHEMA_VERSION:
        fields = _FULL_LOADER_V2_FIELDS
    else:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_FULL_LOADER_INVALID")
    if set(document) != fields:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_FULL_LOADER_INVALID")
    try:
        supplied = verify_self_digest(document, FULL_LOADER_DIGEST_FIELD)
        rebuilt = build_v32_cycle_source_full_loader_receipt(
            source_cutoff_at=document.get("source_cutoff_at"),
            run_id=document["run_id"], cycle_index=document["cycle_index"], admitted_at=document["admitted_at"],
            decision_time=document["decision_time"],
            active_authority_projection_digest=document[
                ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
            ],
            governing_authority_digest=document[
                GOVERNING_AUTHORITY_DIGEST_FIELD
            ],
            active_authority_recorded_at=document["active_authority_recorded_at"],
            experiment_contract_digest=document["experiment_contract_digest"], qualification_binding=document["qualification_binding"],
            capture_binding=document["capture_binding"], current_snapshot_binding=document["current_snapshot_binding"],
            pit_registry_binding=document["pit_registry_binding"], qualification_started_at=document["qualification_started_at"],
            qualification_completed_at=document["qualification_completed_at"], earliest_capture_started_at=document["earliest_capture_started_at"],
            latest_capture_received_at=document["latest_capture_received_at"], closed_bar_as_of=document["closed_bar_as_of"],
            current_open_interest_datum_digest=document["current_open_interest_datum_digest"],
            current_open_interest_status=document["current_open_interest_status"], previous_source_context=document["previous_source_context"],
            artifact_copies=document["artifact_copies"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleSourceAdmissionError):
            raise
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_FULL_LOADER_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[FULL_LOADER_DIGEST_FIELD]:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_FULL_LOADER_INVALID")
    _assert_boundary(document, "V32_CYCLE_SOURCE_FULL_LOADER_BOUNDARY_INVALID")
    return supplied


def seal_v32_cycle_source_admission(
    *,
    run_id: str,
    cycle_index: int,
    decision_time: str,
    admitted_at: str,
    current_snapshot_binding: Mapping[str, Any],
    pit_registry_binding: Mapping[str, Any],
    previous_source_context: Mapping[str, Any],
    full_loader_receipt_binding: Mapping[str, Any],
    active_authority_projection_digest: str,
    governing_authority_digest: str,
    experiment_contract_digest: str,
    qualification_binding: Mapping[str, Any],
    capture_binding: Mapping[str, Any],
    current_open_interest_datum_digest: str,
    current_open_interest_status: str,
    source_cutoff_at: str | None = None,
) -> dict[str, Any]:
    """Seal v2 when a cutoff is supplied; omission is reserved for legacy v1."""

    schema_version = (
        LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION
        if source_cutoff_at is None
        else SOURCE_ADMISSION_SCHEMA_VERSION
    )
    cycle = _cycle(cycle_index)
    decision_text = _time(
        decision_time, "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID"
    )
    decision = _moment(
        decision_text, "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID"
    )
    admitted = _moment(admitted_at, "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID")
    if schema_version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION:
        if source_cutoff_at is not None or admitted > decision:
            raise V32CycleSourceAdmissionError(
                "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID"
            )
        source_cutoff_text = None
    elif schema_version == SOURCE_ADMISSION_SCHEMA_VERSION:
        source_cutoff_text = _time(
            source_cutoff_at, "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID"
        )
        source_cutoff = _moment(
            source_cutoff_text, "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID"
        )
        if decision_text != source_cutoff_text or source_cutoff > admitted:
            raise V32CycleSourceAdmissionError(
                "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID"
            )
    else:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID")
    if current_open_interest_status not in {"OBSERVED", "UNKNOWN"}:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_ADMISSION_OI_INVALID")
    body = {
            "schema_id": SOURCE_ADMISSION_SCHEMA_ID,
            "schema_version": schema_version,
            "run_id": _text(run_id, "V32_CYCLE_SOURCE_ADMISSION_INVALID"),
            "cycle_index": cycle,
            "decision_time": decision_text,
            "admitted_at": _time(admitted_at, "V32_CYCLE_SOURCE_ADMISSION_TIME_INVALID"),
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD: _digest(
                active_authority_projection_digest,
                "V32_CYCLE_SOURCE_ADMISSION_AUTHORITY_INVALID",
            ),
            GOVERNING_AUTHORITY_DIGEST_FIELD: _digest(
                governing_authority_digest,
                "V32_CYCLE_SOURCE_ADMISSION_AUTHORITY_INVALID",
            ),
            "experiment_contract_digest": _digest(experiment_contract_digest, "V32_CYCLE_SOURCE_ADMISSION_CONTRACT_INVALID"),
            "qualification_binding": _binding(qualification_binding, "V32_CYCLE_SOURCE_ADMISSION_QUALIFICATION_INVALID", schema_id=QUALIFICATION_SCHEMA_ID, digest_field=QUALIFICATION_DIGEST_FIELD),
            "capture_binding": _binding(capture_binding, "V32_CYCLE_SOURCE_ADMISSION_CAPTURE_INVALID", schema_id=CAPTURE_SCHEMA_ID, digest_field=CAPTURE_DIGEST_FIELD),
            "current_snapshot_binding": _binding(current_snapshot_binding, "V32_CYCLE_SOURCE_ADMISSION_SNAPSHOT_INVALID", schema_id=SNAPSHOT_SCHEMA_ID, digest_field=SNAPSHOT_DIGEST_FIELD),
            "pit_registry_binding": _binding(pit_registry_binding, "V32_CYCLE_SOURCE_ADMISSION_PIT_INVALID", schema_id=PIT_REGISTRY_SCHEMA_ID, digest_field=PIT_REGISTRY_DIGEST_FIELD),
            "previous_source_context": _previous_context(previous_source_context, cycle_index=cycle),
            "full_loader_receipt_binding": _binding(full_loader_receipt_binding, "V32_CYCLE_SOURCE_ADMISSION_FULL_LOADER_INVALID", schema_id=FULL_LOADER_SCHEMA_ID, digest_field=FULL_LOADER_DIGEST_FIELD),
            "current_open_interest_datum_digest": _digest(current_open_interest_datum_digest, "V32_CYCLE_SOURCE_ADMISSION_OI_INVALID"),
            "current_open_interest_status": current_open_interest_status,
            "current_open_interest_zero_imputed": False,
            "single_source_collection_transaction": True,
            "attempt_count": 1,
            "retry_allowed": False,
            "point_in_time_verified": True,
            "closed_bar_verified": True,
            "freshness_verified": True,
            "exact_bytes_copied_and_read_back": True,
            "qualification_is_start_authority": False,
            **_boundary(),
        }
    if source_cutoff_text is not None:
        body["source_cutoff_at"] = source_cutoff_text
    return self_digest(body, SOURCE_ADMISSION_DIGEST_FIELD)


def verify_v32_cycle_source_admission(document: Mapping[str, Any]) -> str:
    """Reject V3.1, simplified projections, and arbitrary self-digested wrappers."""

    if not isinstance(document, Mapping):
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_ADMISSION_INVALID")
    version = document.get("schema_version")
    if version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION:
        fields = _ADMISSION_V1_FIELDS
    elif version == SOURCE_ADMISSION_SCHEMA_VERSION:
        fields = _ADMISSION_V2_FIELDS
    else:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_ADMISSION_INVALID")
    if set(document) != fields:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_ADMISSION_INVALID")
    try:
        supplied = verify_self_digest(document, SOURCE_ADMISSION_DIGEST_FIELD)
        rebuilt = seal_v32_cycle_source_admission(
            source_cutoff_at=document.get("source_cutoff_at"),
            run_id=document["run_id"], cycle_index=document["cycle_index"], decision_time=document["decision_time"], admitted_at=document["admitted_at"],
            current_snapshot_binding=document["current_snapshot_binding"], pit_registry_binding=document["pit_registry_binding"],
            previous_source_context=document["previous_source_context"], full_loader_receipt_binding=document["full_loader_receipt_binding"],
            active_authority_projection_digest=document[
                ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
            ],
            governing_authority_digest=document[
                GOVERNING_AUTHORITY_DIGEST_FIELD
            ],
            experiment_contract_digest=document["experiment_contract_digest"],
            qualification_binding=document["qualification_binding"], capture_binding=document["capture_binding"],
            current_open_interest_datum_digest=document["current_open_interest_datum_digest"], current_open_interest_status=document["current_open_interest_status"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleSourceAdmissionError):
            raise
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_ADMISSION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[SOURCE_ADMISSION_DIGEST_FIELD]:
        raise V32CycleSourceAdmissionError("V32_CYCLE_SOURCE_ADMISSION_INVALID")
    _assert_boundary(document, "V32_CYCLE_SOURCE_ADMISSION_BOUNDARY_INVALID")
    return supplied


__all__ = [
    "ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD", "AUTHORITY_PROJECTION_SCHEMA_ID",
    "GOVERNING_AUTHORITY_DIGEST_FIELD", "CAPTURE_DIGEST_FIELD", "CAPTURE_SCHEMA_ID",
    "FULL_LOADER_DIGEST_FIELD", "FULL_LOADER_SCHEMA_ID", "INSTRUMENT",
    "LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION", "MAX_SOURCE_AGE_SECONDS",
    "PIT_REGISTRY_DIGEST_FIELD", "PIT_REGISTRY_SCHEMA_ID", "QUALIFICATION_DIGEST_FIELD",
    "QUALIFICATION_SCHEMA_ID", "SNAPSHOT_DIGEST_FIELD", "SNAPSHOT_SCHEMA_ID",
    "SOURCE_ADMISSION_DIGEST_FIELD", "SOURCE_ADMISSION_SCHEMA_ID",
    "SOURCE_ADMISSION_SCHEMA_VERSION", "V32CycleSourceAdmissionError",
    "build_v32_active_authority_projection", "build_v32_cycle_source_full_loader_receipt",
    "build_v32_formal_source_qualification", "build_v32_pit_evidence_registry",
    "build_v32_public_market_snapshot", "build_v32_public_source_capture",
    "cycle_source_admission_ref", "cycle_source_full_loader_ref", "qualification_ref",
    "seal_v32_cycle_source_admission", "verify_v32_active_authority_projection",
    "verify_v32_cycle_source_admission", "verify_v32_cycle_source_full_loader_receipt",
    "verify_v32_formal_source_qualification", "verify_v32_pit_evidence_registry",
    "verify_v32_public_market_snapshot", "verify_v32_public_source_capture",
]
