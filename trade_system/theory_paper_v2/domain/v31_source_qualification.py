"""V3.1 public-source qualification contracts.

These contracts describe one qualification-only acquisition attempt.  They do
not create a research run, authorize an experiment, or grant account/order
access.  The sole admitted source is the fixed OKX BTC-USDT perpetual public
snapshot used by :mod:`native_market_collector`.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode

from .contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .data_model import DataModelError, verify_point_in_time_dataset


class V31SourceQualificationError(ValueError):
    """A source-qualification contract failed closed."""


APPROVED_V31_THEORY_SHA256 = (
    "ceee2b5fdb6962e4ae42ba32cdf980e44830b69a2c833289e472593cf3d92553"
)
OKX_PUBLIC_BASE_URL = "https://www.okx.com"
OKX_QUALIFICATION_INSTRUMENT_ID = "BTC-USDT-SWAP"
QUALIFICATION_TIMEOUT_SECONDS = 15
QUALIFICATION_MAX_RESPONSE_BYTES = 10 * 1024 * 1024

REQUEST_SPECS: tuple[dict[str, Any], ...] = (
    {
        "request_id": "okx-native-server-time",
        "path": "/api/v5/public/time",
        "required": True,
        "query_policy": "NONE",
    },
    {
        "request_id": "okx-native-instrument",
        "path": "/api/v5/public/instruments",
        "required": True,
        "query_policy": "FIXED_INSTRUMENT_AND_SWAP_TYPE",
    },
    {
        "request_id": "okx-native-ticker",
        "path": "/api/v5/market/ticker",
        "required": True,
        "query_policy": "FIXED_INSTRUMENT",
    },
    {
        "request_id": "okx-native-mark-price",
        "path": "/api/v5/public/mark-price",
        "required": True,
        "query_policy": "FIXED_INSTRUMENT_AND_SWAP_TYPE",
    },
    {
        "request_id": "okx-native-candles-15m",
        "path": "/api/v5/market/history-candles",
        "required": True,
        "query_policy": "SERVER_TIME_CLOSED_BUCKET_15M",
    },
    {
        "request_id": "okx-native-candles-1h",
        "path": "/api/v5/market/history-candles",
        "required": True,
        "query_policy": "SERVER_TIME_CLOSED_BUCKET_1H",
    },
    {
        "request_id": "okx-native-candles-4h",
        "path": "/api/v5/market/history-candles",
        "required": True,
        "query_policy": "SERVER_TIME_CLOSED_BUCKET_4H",
    },
    {
        "request_id": "okx-native-candles-1d",
        "path": "/api/v5/market/history-candles",
        "required": True,
        "query_policy": "SERVER_TIME_CLOSED_BUCKET_1D_UTC",
    },
    {
        "request_id": "okx-native-open-interest",
        "path": "/api/v5/public/open-interest",
        "required": False,
        "query_policy": "FIXED_INSTRUMENT_AND_SWAP_TYPE",
    },
    {
        "request_id": "okx-native-funding-rate",
        "path": "/api/v5/public/funding-rate",
        "required": False,
        "query_policy": "FIXED_INSTRUMENT",
    },
    {
        "request_id": "okx-native-books",
        "path": "/api/v5/market/books",
        "required": False,
        "query_policy": "FIXED_INSTRUMENT_TOP_50",
    },
    {
        "request_id": "okx-native-trades",
        "path": "/api/v5/market/trades",
        "required": False,
        "query_policy": "FIXED_INSTRUMENT_LAST_100",
    },
)
REQUIRED_REQUEST_IDS = tuple(
    row["request_id"] for row in REQUEST_SPECS if row["required"]
)
OPTIONAL_REQUEST_IDS = tuple(
    row["request_id"] for row in REQUEST_SPECS if not row["required"]
)
OPTIONAL_FAILURE_KEYS = {
    "okx-native-open-interest": "open-interest",
    "okx-native-funding-rate": "funding-rate",
    "okx-native-books": "books",
    "okx-native-trades": "trades",
}

_SPEC_BY_ID = {str(row["request_id"]): row for row in REQUEST_SPECS}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CONTRACT_SPECIFICATION_FIELDS = frozenset(
    {
        "instrument_id",
        "contract_multiplier",
        "contract_multiplier_unit",
        "contract_multiplier_source_field",
        "okx_ct_val",
        "okx_ct_mult",
        "contract_value_currency",
        "contract_type",
        "settlement_currency",
        "quantity_step_contracts",
        "minimum_quantity_contracts",
        "price_tick_usdt",
        "source_request_id",
        "source_raw_body_sha256",
        "available_at",
    }
)
_CAPTURE_FIELDS = frozenset(
    {
        "request_id",
        "method",
        "base_url",
        "path",
        "query",
        "request_started_at",
        "response_received_at",
        "final_url",
        "http_status",
        "selected_response_headers",
        "response_headers_digest",
        "raw_body_sha256",
        "raw_body_byte_length",
        "request_identity_digest",
        "record_digest",
    }
)
_CHECKPOINT_STATUSES = frozenset(
    {"RESERVED", "COLLECTING", "SEALED", "FAILED_CLOSED"}
)
_FAILURE_V1_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "failed_at",
        "failed_phase",
        "reason_code",
        "source_qualification_plan_digest",
        "source_qualification_reservation_digest",
        "attempt_count",
        "retry_allowed",
        "partial_evidence_preserved",
        "qualification_only",
        "research_run_created",
        "experiment_start_authorized",
        "account_access",
        "paper_trading",
        "live_trading",
        "order_submission",
        "credential_access",
        "funds_access",
        "external_execution_authority",
        "executable",
        "source_qualification_failure_digest",
    }
)
_FAILURE_V1_1_FIELDS = _FAILURE_V1_FIELDS | {"root_cause_code"}


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31SourceQualificationError(code)
    return value.strip()


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31SourceQualificationError(code)
    return value


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or not value.endswith("Z"):
        raise V31SourceQualificationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SourceQualificationError(code) from exc
    if parsed.tzinfo is None:
        raise V31SourceQualificationError(code)
    normalized = parsed.astimezone(UTC)
    # Frozen documents use second precision, PublicRequestCapture uses an
    # explicit millisecond field (including ``.000``), and the V3.1 PIT model
    # emits Python's canonical microsecond representation.  All three are
    # canonical project outputs for the same UTC instant; arbitrary offsets or
    # free-form fractional precision remain forbidden.
    canonical_seconds = normalized.isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    canonical_milliseconds = normalized.isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    canonical_microseconds = normalized.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    if value not in {
        canonical_seconds,
        canonical_milliseconds,
        canonical_microseconds,
    }:
        raise V31SourceQualificationError(code)
    return normalized


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "relative_ref",
        "semantic_digest",
        "physical_sha256",
    }:
        raise V31SourceQualificationError(code)
    relative_ref = _text(value.get("relative_ref"), code)
    if relative_ref.startswith("/") or any(
        part in {"", ".", ".."} for part in relative_ref.split("/")
    ):
        raise V31SourceQualificationError(code)
    return {
        "relative_ref": relative_ref,
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def _expected_query(
    *, request_id: str, server_time_ms: int
) -> list[dict[str, str]]:
    """Return the exact query emitted by the frozen native collector.

    Paths alone are not a sufficient source boundary: several admitted OKX
    endpoints can return other instruments, instrument classes, bucket
    conventions, or response sizes.  Bind every capture to the sole approved
    BTC perpetual request, including the server-time-derived closed-candle
    cutoff.
    """

    fixed_instrument = [
        {"name": "instId", "value": OKX_QUALIFICATION_INSTRUMENT_ID}
    ]
    fixed_instrument_and_type = fixed_instrument + [
        {"name": "instType", "value": "SWAP"}
    ]
    if request_id == "okx-native-server-time":
        return []
    if request_id in {
        "okx-native-instrument",
        "okx-native-mark-price",
        "okx-native-open-interest",
    }:
        return fixed_instrument_and_type
    if request_id in {"okx-native-ticker", "okx-native-funding-rate"}:
        return fixed_instrument
    if request_id == "okx-native-books":
        return fixed_instrument + [{"name": "sz", "value": "50"}]
    if request_id == "okx-native-trades":
        return fixed_instrument + [{"name": "limit", "value": "100"}]
    candle_specs = {
        "okx-native-candles-15m": (900_000, "15m", "96"),
        "okx-native-candles-1h": (3_600_000, "1H", "168"),
        "okx-native-candles-4h": (14_400_000, "4H", "90"),
        "okx-native-candles-1d": (86_400_000, "1Dutc", "60"),
    }
    candle = candle_specs.get(request_id)
    if candle is None:  # pragma: no cover - request id is checked by caller
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_ID_INVALID"
        )
    bucket_ms, bar, limit = candle
    return [
        {"name": "after", "value": str((server_time_ms // bucket_ms) * bucket_ms)},
        {"name": "bar", "value": bar},
        {"name": "instId", "value": OKX_QUALIFICATION_INSTRUMENT_ID},
        {"name": "limit", "value": limit},
    ]


def seal_v31_source_qualification_plan(
    *, qualification_id: str, created_at: str, theory_sha256: str
) -> dict[str, Any]:
    """Freeze the only source access that one Q6 qualification may perform."""

    identifier = _text(qualification_id, "V31_SOURCE_QUALIFICATION_ID_INVALID")
    if not identifier.startswith("v31-source-qualification-"):
        raise V31SourceQualificationError("V31_SOURCE_QUALIFICATION_ID_INVALID")
    _time(created_at, "V31_SOURCE_QUALIFICATION_TIME_INVALID")
    if theory_sha256 != APPROVED_V31_THEORY_SHA256:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_THEORY_NOT_APPROVED"
        )
    return self_digest(
        {
            "schema_id": "theory_paper_v31_source_qualification_plan",
            "schema_version": "1.0.0",
            "qualification_id": identifier,
            "created_at": created_at,
            "theory_sha256": theory_sha256,
            "venue": "OKX",
            "base_url": OKX_PUBLIC_BASE_URL,
            "instrument_id": OKX_QUALIFICATION_INSTRUMENT_ID,
            "instrument_type": "SWAP_PERPETUAL",
            "method": "GET",
            "request_specs": [dict(row) for row in REQUEST_SPECS],
            "required_request_ids": list(REQUIRED_REQUEST_IDS),
            "optional_request_ids": list(OPTIONAL_REQUEST_IDS),
            "timeout_seconds": QUALIFICATION_TIMEOUT_SECONDS,
            "max_response_bytes_per_request": QUALIFICATION_MAX_RESPONSE_BYTES,
            "retry_count": 0,
            "attempt_limit": 1,
            "raw_retention": "FULL_RESPONSE_BYTES_WRITE_ONCE_AND_READBACK",
            "raw_relative_ref_template": (
                "cycles/0001/market/raw/{request_id}.body"
            ),
            "decision_at_policy": "AFTER_LAST_RESPONSE_BEFORE_ADAPTER",
            "source_quality_ceiling": "VERIFIED_SECONDARY",
            "missing_is_zero": False,
            "qualification_only": True,
            "research_run_created": False,
            "experiment_start_authorized": False,
            "account_access": False,
            "paper_trading": False,
            "live_trading": False,
            "order_access": False,
            "order_submission": False,
            "credential_access": False,
            "funds_access": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "source_qualification_plan_digest",
    )


def verify_v31_source_qualification_plan(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, "source_qualification_plan_digest")
        rebuilt = seal_v31_source_qualification_plan(
            qualification_id=document["qualification_id"],
            created_at=document["created_at"],
            theory_sha256=document["theory_sha256"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SourceQualificationError):
            raise
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_PLAN_INVALID"
        ) from exc
    if rebuilt != dict(document):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_PLAN_NOT_CANONICAL"
        )
    return supplied


def seal_v31_source_qualification_reservation(
    *, plan: Mapping[str, Any], reserved_at: str
) -> dict[str, Any]:
    plan_digest = verify_v31_source_qualification_plan(plan)
    _time(reserved_at, "V31_SOURCE_QUALIFICATION_RESERVATION_TIME_INVALID")
    return self_digest(
        {
            "schema_id": "theory_paper_v31_source_qualification_reservation",
            "schema_version": "1.0.0",
            "qualification_id": plan["qualification_id"],
            "reserved_at": reserved_at,
            "source_qualification_plan_digest": plan_digest,
            "attempt_index": 1,
            "attempt_limit": 1,
            "retry_count": 0,
            "durable_before_collector_call": True,
            "cas_checkpoint_required_before_collector_call": True,
            "exclusive_lease_required_before_collector_call": True,
            "qualification_only": True,
            "research_run_created": False,
            "experiment_start_authorized": False,
            "account_access": False,
            "paper_trading": False,
            "live_trading": False,
            "order_submission": False,
            "credential_access": False,
            "funds_access": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "source_qualification_reservation_digest",
    )


def verify_v31_source_qualification_reservation(
    document: Mapping[str, Any], *, plan: Mapping[str, Any]
) -> str:
    try:
        supplied = verify_self_digest(
            document, "source_qualification_reservation_digest"
        )
        rebuilt = seal_v31_source_qualification_reservation(
            plan=plan, reserved_at=document["reserved_at"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SourceQualificationError):
            raise
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_RESERVATION_INVALID"
        ) from exc
    if rebuilt != dict(document):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_RESERVATION_NOT_CANONICAL"
        )
    return supplied


def _checkpoint_document(
    *,
    qualification_id: str,
    revision: int,
    status: str,
    attempt_count: int,
    plan_binding: Mapping[str, Any],
    reservation_binding: Mapping[str, Any],
    completion_binding: Mapping[str, Any] | None,
    failure_binding: Mapping[str, Any] | None,
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 0
        or isinstance(attempt_count, bool)
        or not isinstance(attempt_count, int)
        or attempt_count not in {0, 1}
        or status not in _CHECKPOINT_STATUSES
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CHECKPOINT_STATE_INVALID"
        )
    identifier = _text(
        qualification_id, "V31_SOURCE_QUALIFICATION_CHECKPOINT_ID_INVALID"
    )
    _time(created_at, "V31_SOURCE_QUALIFICATION_CHECKPOINT_TIME_INVALID")
    _time(updated_at, "V31_SOURCE_QUALIFICATION_CHECKPOINT_TIME_INVALID")
    plan_ref = _binding(
        plan_binding, "V31_SOURCE_QUALIFICATION_PLAN_BINDING_INVALID"
    )
    reservation_ref = _binding(
        reservation_binding,
        "V31_SOURCE_QUALIFICATION_RESERVATION_BINDING_INVALID",
    )
    completion_ref = (
        None
        if completion_binding is None
        else _binding(
            completion_binding,
            "V31_SOURCE_QUALIFICATION_COMPLETION_BINDING_INVALID",
        )
    )
    failure_ref = (
        None
        if failure_binding is None
        else _binding(
            failure_binding, "V31_SOURCE_QUALIFICATION_FAILURE_BINDING_INVALID"
        )
    )
    if (
        (status == "RESERVED" and attempt_count != 0)
        or (status != "RESERVED" and attempt_count != 1)
        or (status == "SEALED" and (completion_ref is None or failure_ref is not None))
        or (status == "FAILED_CLOSED" and (failure_ref is None or completion_ref is not None))
        or (status in {"RESERVED", "COLLECTING"} and (completion_ref or failure_ref))
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CHECKPOINT_STATE_INVALID"
        )
    return self_digest(
        {
            "schema_id": "theory_paper_v31_source_qualification_checkpoint",
            "schema_version": "1.0.0",
            "qualification_id": identifier,
            "revision": revision,
            "status": status,
            "attempt_count": attempt_count,
            "attempt_limit": 1,
            "plan_binding": plan_ref,
            "reservation_binding": reservation_ref,
            "completion_binding": completion_ref,
            "failure_binding": failure_ref,
            "collector_retry_allowed": False,
            "chat_history_is_authority": False,
            "qualification_only": True,
            "research_run_created": False,
            "experiment_start_authorized": False,
            "account_access": False,
            "paper_trading": False,
            "live_trading": False,
            "order_submission": False,
            "credential_access": False,
            "funds_access": False,
            "created_at": created_at,
            "updated_at": updated_at,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "source_qualification_checkpoint_digest",
    )


def initialize_v31_source_qualification_checkpoint(
    *,
    qualification_id: str,
    plan_binding: Mapping[str, Any],
    reservation_binding: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    return _checkpoint_document(
        qualification_id=qualification_id,
        revision=0,
        status="RESERVED",
        attempt_count=0,
        plan_binding=plan_binding,
        reservation_binding=reservation_binding,
        completion_binding=None,
        failure_binding=None,
        created_at=created_at,
        updated_at=created_at,
    )


def transition_v31_source_qualification_checkpoint(
    *,
    current: Mapping[str, Any],
    status: str,
    updated_at: str,
    completion_binding: Mapping[str, Any] | None = None,
    failure_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    verify_v31_source_qualification_checkpoint(current)
    allowed = {
        "RESERVED": {"COLLECTING"},
        "COLLECTING": {"SEALED", "FAILED_CLOSED"},
        "SEALED": set(),
        "FAILED_CLOSED": set(),
    }
    if status not in allowed[str(current["status"])]:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CHECKPOINT_TRANSITION_INVALID"
        )
    return _checkpoint_document(
        qualification_id=str(current["qualification_id"]),
        revision=int(current["revision"]) + 1,
        status=status,
        attempt_count=1,
        plan_binding=current["plan_binding"],
        reservation_binding=current["reservation_binding"],
        completion_binding=completion_binding,
        failure_binding=failure_binding,
        created_at=str(current["created_at"]),
        updated_at=updated_at,
    )


def verify_v31_source_qualification_checkpoint(
    document: Mapping[str, Any],
) -> str:
    try:
        supplied = verify_self_digest(
            document, "source_qualification_checkpoint_digest"
        )
        rebuilt = _checkpoint_document(
            qualification_id=document["qualification_id"],
            revision=document["revision"],
            status=document["status"],
            attempt_count=document["attempt_count"],
            plan_binding=document["plan_binding"],
            reservation_binding=document["reservation_binding"],
            completion_binding=document["completion_binding"],
            failure_binding=document["failure_binding"],
            created_at=document["created_at"],
            updated_at=document["updated_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SourceQualificationError):
            raise
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CHECKPOINT_INVALID"
        ) from exc
    if rebuilt != dict(document):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CHECKPOINT_NOT_CANONICAL"
        )
    return supplied


def _validate_capture(
    capture: Mapping[str, Any], *, decision_at: datetime, server_time_ms: int
) -> dict[str, Any]:
    if not isinstance(capture, Mapping) or set(capture) != _CAPTURE_FIELDS:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_SCHEMA_INVALID"
        )
    request_id = _text(
        capture.get("request_id"), "V31_SOURCE_QUALIFICATION_CAPTURE_ID_INVALID"
    )
    spec = _SPEC_BY_ID.get(request_id)
    query = capture.get("query")
    headers = capture.get("selected_response_headers")
    if (
        spec is None
        or capture.get("method") != "GET"
        or capture.get("base_url") != OKX_PUBLIC_BASE_URL
        or capture.get("path") != spec["path"]
        or capture.get("http_status") != 200
        or not isinstance(query, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"name", "value"}
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("value"), str)
            for row in query
        )
        or query != sorted(query, key=lambda row: str(row["name"]))
        or len({str(row["name"]) for row in query}) != len(query)
        or not isinstance(headers, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"name", "value"}
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("value"), str)
            for row in headers
        )
        or headers != sorted(headers, key=lambda row: str(row["name"]))
        or not isinstance(capture.get("raw_body_byte_length"), int)
        or isinstance(capture.get("raw_body_byte_length"), bool)
        or capture["raw_body_byte_length"] < 0
        or capture["raw_body_byte_length"] > QUALIFICATION_MAX_RESPONSE_BYTES
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_SEMANTICS_INVALID"
        )
    if query != _expected_query(
        request_id=request_id, server_time_ms=server_time_ms
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_QUERY_NOT_FROZEN"
        )
    started = _time(
        capture["request_started_at"],
        "V31_SOURCE_QUALIFICATION_CAPTURE_TIME_INVALID",
    )
    received = _time(
        capture["response_received_at"],
        "V31_SOURCE_QUALIFICATION_CAPTURE_TIME_INVALID",
    )
    if started > received or received > decision_at:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_NOT_POINT_IN_TIME"
        )
    for field in (
        "response_headers_digest",
        "raw_body_sha256",
        "request_identity_digest",
        "record_digest",
    ):
        _digest(capture.get(field), "V31_SOURCE_QUALIFICATION_CAPTURE_DIGEST_INVALID")
    if canonical_digest(headers) != capture["response_headers_digest"]:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_HEADERS_INVALID"
        )
    if canonical_digest(
        {
            "method": "GET",
            "base_url": OKX_PUBLIC_BASE_URL,
            "path": spec["path"],
            "query": query,
        }
    ) != capture["request_identity_digest"]:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_REQUEST_INVALID"
        )
    expected_url = f"{OKX_PUBLIC_BASE_URL}{spec['path']}"
    if query:
        expected_url = f"{expected_url}?{urlencode([(row['name'], row['value']) for row in query])}"
    if capture.get("final_url") != expected_url:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_FINAL_URL_INVALID"
        )
    payload = dict(capture)
    payload.pop("record_digest")
    if canonical_digest(payload) != capture["record_digest"]:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_RECORD_INVALID"
        )
    return dict(capture)


def _validate_v11_contract_specification(
    *,
    snapshot: Mapping[str, Any],
    information: Mapping[str, Any],
    captures_by_id: Mapping[str, Mapping[str, Any]],
    raw_body_by_request_id: Mapping[str, bytes],
) -> None:
    """Require the formal contract multiplier to equal public OKX ``ctVal``."""

    specification = snapshot.get("contract_specification")
    if (
        not isinstance(specification, Mapping)
        or set(specification) != _CONTRACT_SPECIFICATION_FIELDS
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_SPECIFICATION_INVALID"
        )
    numeric_fields: dict[str, Decimal] = {}
    try:
        for field in (
            "contract_multiplier",
            "okx_ct_val",
            "okx_ct_mult",
            "quantity_step_contracts",
            "minimum_quantity_contracts",
            "price_tick_usdt",
        ):
            raw_value = specification.get(field)
            parsed = Decimal(str(raw_value))
            if (
                not isinstance(raw_value, str)
                or not parsed.is_finite()
                or parsed <= 0
                or canonical_decimal(parsed) != raw_value
            ):
                raise ValueError(field)
            numeric_fields[field] = parsed
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_NUMERIC_INVALID"
        ) from exc
    multiplier_raw = str(specification["contract_multiplier"])
    request_id = specification.get("source_request_id")
    capture = captures_by_id.get(str(request_id))
    if (
        specification.get("instrument_id")
        != OKX_QUALIFICATION_INSTRUMENT_ID
        or specification.get("contract_multiplier_unit")
        != "BTC_PER_CONTRACT"
        or specification.get("contract_multiplier_source_field") != "ctVal"
        or specification.get("okx_ct_val") != multiplier_raw
        or specification.get("contract_value_currency") != "BTC"
        or specification.get("contract_type") != "linear"
        or specification.get("settlement_currency") != "USDT"
        or request_id != "okx-native-instrument"
        or capture is None
        or specification.get("source_raw_body_sha256")
        != capture.get("raw_body_sha256")
        or specification.get("available_at")
        != capture.get("response_received_at")
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_SPECIFICATION_INVALID"
        )
    if (
        numeric_fields["minimum_quantity_contracts"]
        % numeric_fields["quantity_step_contracts"]
        != 0
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_QUANTITY_CONSTRAINTS_INVALID"
        )
    try:
        decoded = json.loads(raw_body_by_request_id[str(request_id)].decode("utf-8"))
        rows = decoded["data"]
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_RAW_INVALID"
        ) from exc
    instrument_rows = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("instId") == OKX_QUALIFICATION_INSTRUMENT_ID
    ] if isinstance(rows, list) else []
    if len(instrument_rows) != 1:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_RAW_INVALID"
        )
    instrument = instrument_rows[0]
    if (
        decoded.get("code") != "0"
        or decoded.get("msg") not in {"", None}
        or instrument.get("state") != "live"
        or instrument.get("ctVal") != multiplier_raw
        or instrument.get("ctMult") != specification.get("okx_ct_mult")
        or instrument.get("ctValCcy") != "BTC"
        or instrument.get("ctType") != "linear"
        or instrument.get("settleCcy") != "USDT"
        or instrument.get("lotSz")
        != specification.get("quantity_step_contracts")
        or instrument.get("minSz")
        != specification.get("minimum_quantity_contracts")
        or instrument.get("tickSz") != specification.get("price_tick_usdt")
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_RAW_MISMATCH"
        )
    normalized_facts = information.get("facts")
    fact_specs = {
        "instrument-contract-multiplier": (
            specification["contract_multiplier"],
            "BTC_PER_CONTRACT",
        ),
        "instrument-okx-ct-mult": (
            specification["okx_ct_mult"],
            "OKX_CT_MULT",
        ),
        "instrument-quantity-step-contracts": (
            specification["quantity_step_contracts"],
            "CONTRACTS",
        ),
        "instrument-minimum-quantity-contracts": (
            specification["minimum_quantity_contracts"],
            "CONTRACTS",
        ),
        "instrument-price-tick-usdt": (
            specification["price_tick_usdt"],
            "USDT_PER_BTC",
        ),
    }
    if not isinstance(normalized_facts, list):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CONTRACT_FACT_MISSING"
        )
    for fact_id, (expected_value, expected_unit) in fact_specs.items():
        rows = [
            row
            for row in normalized_facts
            if isinstance(row, Mapping) and row.get("fact_id") == fact_id
        ]
        if len(rows) != 1:
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_CONTRACT_FACT_MISSING"
            )
        fact = rows[0]
        if (
            fact.get("kind") != "RAW_FACT"
            or fact.get("metric") != fact_id
            or fact.get("value") != expected_value
            or fact.get("unit") != expected_unit
            or fact.get("source_ref") != request_id
            or fact.get("raw_sha256") != capture.get("raw_body_sha256")
            or fact.get("available_at") != capture.get("response_received_at")
            or fact.get("missing_reason") is not None
        ):
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_CONTRACT_FACT_MISMATCH"
            )


def validate_v31_source_qualification_collection(
    *,
    plan: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    raw_body_by_request_id: Mapping[str, bytes],
    decision_at: str,
) -> dict[str, Mapping[str, Any]]:
    """Validate the collector result before any raw byte is persisted."""

    verify_v31_source_qualification_plan(plan)
    cutoff = _time(decision_at, "V31_SOURCE_QUALIFICATION_DECISION_TIME_INVALID")
    try:
        snapshot_digest = verify_self_digest(
            snapshot, "native_market_snapshot_digest"
        )
        information = snapshot["market_information_snapshot"]
        verify_self_digest(information, "market_information_snapshot_digest")
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_SNAPSHOT_DIGEST_INVALID"
        ) from exc
    if (
        snapshot.get("schema_id") != "native_btc_public_market_snapshot"
        or snapshot.get("schema_version") not in {"1.0.0", "1.1.0"}
        or snapshot.get("run_id") != plan["qualification_id"]
        or snapshot.get("cycle_index") != 1
        or snapshot.get("instrument_id") != OKX_QUALIFICATION_INSTRUMENT_ID
        or snapshot.get("point_in_time") is not True
        or snapshot.get("missing_is_zero") is not False
        or snapshot.get("account_data_accessed") is not False
        or snapshot.get("order_data_accessed") is not False
        or snapshot.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or snapshot.get("data_scope") != "OFFICIAL_PUBLIC_MARKET_ONLY"
        or information.get("run_id") != plan["qualification_id"]
        or information.get("cycle_index") != 1
        or information.get("symbol") != OKX_QUALIFICATION_INSTRUMENT_ID
        or information.get("missing_values_are_zero") is not False
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_SNAPSHOT_BOUNDARY_INVALID"
        )
    captured_through = _time(
        snapshot.get("captured_through"),
        "V31_SOURCE_QUALIFICATION_CAPTURE_TIME_INVALID",
    )
    if captured_through > cutoff:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_SNAPSHOT_NOT_POINT_IN_TIME"
        )
    captures = snapshot.get("source_captures")
    if not isinstance(captures, list) or not captures:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURES_MISSING"
        )
    server_time_ms = snapshot.get("server_time_ms")
    if (
        isinstance(server_time_ms, bool)
        or not isinstance(server_time_ms, int)
        or server_time_ms <= 0
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_SERVER_TIME_INVALID"
        )
    validated = [
        _validate_capture(
            row, decision_at=cutoff, server_time_ms=server_time_ms
        )
        for row in captures
    ]
    if captured_through != max(
        _time(
            row["response_received_at"],
            "V31_SOURCE_QUALIFICATION_CAPTURE_TIME_INVALID",
        )
        for row in validated
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_CUTOFF_MISMATCH"
        )
    by_id = {str(row["request_id"]): row for row in validated}
    if len(by_id) != len(validated):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_CAPTURE_ID_DUPLICATE"
        )
    capture_ids = set(by_id)
    required = set(REQUIRED_REQUEST_IDS)
    optional = set(OPTIONAL_REQUEST_IDS)
    if (
        not required.issubset(capture_ids)
        or not capture_ids.issubset(required | optional)
        or snapshot.get("required_request_ids") != list(REQUIRED_REQUEST_IDS)
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_REQUIRED_CAPTURE_INCOMPLETE"
        )
    failures = snapshot.get("optional_failures")
    if not isinstance(failures, Mapping):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_OPTIONAL_FAILURES_INVALID"
        )
    for request_id in OPTIONAL_REQUEST_IDS:
        failure_key = OPTIONAL_FAILURE_KEYS[request_id]
        captured = request_id in capture_ids
        failed = failure_key in failures
        if captured == failed or (
            failed
            and (
                not isinstance(failures[failure_key], str)
                or not str(failures[failure_key]).strip()
            )
        ):
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_OPTIONAL_COVERAGE_INVALID"
            )
    if set(failures) - set(OPTIONAL_FAILURE_KEYS.values()):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_OPTIONAL_FAILURES_INVALID"
        )
    if set(raw_body_by_request_id) != capture_ids:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_RAW_COVERAGE_INVALID"
        )
    for request_id, capture in by_id.items():
        raw = raw_body_by_request_id.get(request_id)
        if (
            not isinstance(raw, bytes)
            or len(raw) != capture["raw_body_byte_length"]
            or sha256(raw).hexdigest() != capture["raw_body_sha256"]
        ):
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_RAW_DIGEST_INVALID"
            )
    if snapshot.get("schema_version") == "1.1.0":
        _validate_v11_contract_specification(
            snapshot=snapshot,
            information=information,
            captures_by_id=by_id,
            raw_body_by_request_id=raw_body_by_request_id,
        )
    raw_facts = snapshot.get("facts")
    if not isinstance(raw_facts, list) or not raw_facts:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_FACTS_INVALID"
        )
    for fact in raw_facts:
        if not isinstance(fact, Mapping):
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_FACTS_INVALID"
            )
        fact_status = fact.get("status")
        if fact_status == "UNKNOWN":
            if (
                fact.get("value") is not None
                or fact.get("source_request_id") is not None
                or fact.get("source_raw_body_sha256") is not None
                or not isinstance(fact.get("unknown_reason"), str)
                or not str(fact["unknown_reason"]).strip()
            ):
                raise V31SourceQualificationError(
                    "V31_SOURCE_QUALIFICATION_UNKNOWN_IMPUTED"
                )
            continue
        if fact_status != "OBSERVED" or fact.get("value") is None:
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_FACTS_INVALID"
            )
        source_request_id = fact.get("source_request_id")
        source_capture = by_id.get(str(source_request_id))
        if (
            source_capture is None
            or fact.get("source_raw_body_sha256")
            != source_capture["raw_body_sha256"]
            or fact.get("available_at")
            != source_capture["response_received_at"]
            or fact.get("unknown_reason") is not None
        ):
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_FACT_SOURCE_BINDING_INVALID"
            )
    return by_id


def seal_v31_source_qualification_information_event_record(
    *, qualification_id: str, event_document: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(event_document, Mapping):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_INFORMATION_EVENT_INVALID"
        )
    event_digest = canonical_digest(event_document)
    sources = event_document.get("source_artifacts")
    if not isinstance(sources, list) or len(sources) != 1:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_INFORMATION_SOURCE_INVALID"
        )
    source = sources[0]
    acquisition = source.get("acquisition_receipt") if isinstance(source, Mapping) else None
    if (
        not isinstance(source, Mapping)
        or source.get("evidence_boundary") != "SOURCE_ATTESTED"
        or source.get("quality") != "VERIFIED_SECONDARY"
        or not isinstance(acquisition, Mapping)
        or acquisition.get("evidence_boundary") != "SOURCE_ATTESTED"
        or acquisition.get("acquisition_method") != "PUBLIC_HTTP_CAPTURE"
        or acquisition.get("external_verifier_refs") != []
        or acquisition.get("external_verification_digests") != []
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_INFORMATION_SOURCE_INVALID"
        )
    return self_digest(
        {
            "schema_id": "theory_paper_v31_source_qualification_information_event",
            "schema_version": "1.0.0",
            "qualification_id": qualification_id,
            "information_event_digest": event_digest,
            "event_document": dict(event_document),
            "source_evidence_boundary": "SOURCE_ATTESTED",
            "source_quality": "VERIFIED_SECONDARY",
            "externally_verified": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "source_qualification_information_event_record_digest",
    )


def verify_v31_source_qualification_information_event_record(
    document: Mapping[str, Any], *, qualification_id: str
) -> str:
    try:
        supplied = verify_self_digest(
            document, "source_qualification_information_event_record_digest"
        )
        rebuilt = seal_v31_source_qualification_information_event_record(
            qualification_id=qualification_id,
            event_document=document["event_document"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SourceQualificationError):
            raise
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_INFORMATION_RECORD_INVALID"
        ) from exc
    if rebuilt != dict(document):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_INFORMATION_RECORD_NOT_CANONICAL"
        )
    return supplied


def seal_v31_source_qualification_completion(
    *,
    plan: Mapping[str, Any],
    reservation: Mapping[str, Any],
    completed_at: str,
    decision_at: str,
    snapshot: Mapping[str, Any],
    snapshot_binding: Mapping[str, Any],
    raw_bindings: Mapping[str, Mapping[str, Any]],
    pit_dataset: Mapping[str, Any],
    pit_dataset_binding: Mapping[str, Any],
    information_event_records: Sequence[Mapping[str, Any]],
    information_event_bindings: Sequence[Mapping[str, Any]],
    adapter_id: str,
) -> dict[str, Any]:
    plan_digest = verify_v31_source_qualification_plan(plan)
    reservation_digest = verify_v31_source_qualification_reservation(
        reservation, plan=plan
    )
    completion_time = _time(
        completed_at, "V31_SOURCE_QUALIFICATION_COMPLETION_TIME_INVALID"
    )
    decision_time = _time(
        decision_at, "V31_SOURCE_QUALIFICATION_DECISION_TIME_INVALID"
    )
    if completion_time < decision_time:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_COMPLETION_PRECEDES_DECISION"
        )
    try:
        snapshot_digest = verify_self_digest(
            snapshot, "native_market_snapshot_digest"
        )
        verify_point_in_time_dataset(pit_dataset)
    except (DataModelError, ValueError) as exc:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_ADAPTATION_INVALID"
        ) from exc
    snapshot_ref = _binding(
        snapshot_binding, "V31_SOURCE_QUALIFICATION_SNAPSHOT_BINDING_INVALID"
    )
    dataset_ref = _binding(
        pit_dataset_binding,
        "V31_SOURCE_QUALIFICATION_DATASET_BINDING_INVALID",
    )
    if (
        snapshot_ref["semantic_digest"] != snapshot_digest
        or dataset_ref["semantic_digest"] != pit_dataset.get("dataset_digest")
        or _time(
            pit_dataset.get("decision_at"),
            "V31_SOURCE_QUALIFICATION_DATASET_DECISION_TIME_INVALID",
        )
        != decision_time
        or pit_dataset.get("missing_is_zero") is not False
        or pit_dataset.get("point_in_time") is not True
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_ADAPTATION_BINDING_INVALID"
        )
    captures = {
        str(row["request_id"]): row for row in snapshot["source_captures"]
    }
    raw_refs: dict[str, dict[str, str]] = {}
    for request_id in sorted(raw_bindings):
        binding = _binding(
            raw_bindings[request_id],
            "V31_SOURCE_QUALIFICATION_RAW_BINDING_INVALID",
        )
        capture = captures.get(request_id)
        if (
            capture is None
            or binding["relative_ref"]
            != f"cycles/0001/market/raw/{request_id}.body"
            or binding["semantic_digest"] != capture["raw_body_sha256"]
            or binding["physical_sha256"] != capture["raw_body_sha256"]
        ):
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_RAW_BINDING_INVALID"
            )
        raw_refs[request_id] = binding
    if set(raw_refs) != set(captures):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_RAW_BINDING_INVALID"
        )
    records = list(information_event_records)
    bindings = list(information_event_bindings)
    if not records or len(records) != len(bindings):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_INFORMATION_BINDING_INVALID"
        )
    event_digests: list[str] = []
    event_refs: list[dict[str, str]] = []
    for index, (record, raw_binding) in enumerate(zip(records, bindings)):
        record_digest = verify_v31_source_qualification_information_event_record(
            record, qualification_id=str(plan["qualification_id"])
        )
        binding = _binding(
            raw_binding,
            "V31_SOURCE_QUALIFICATION_INFORMATION_BINDING_INVALID",
        )
        if (
            binding["relative_ref"]
            != f"adapted/information-event-{index + 1:04d}.json"
            or binding["semantic_digest"] != record_digest
        ):
            raise V31SourceQualificationError(
                "V31_SOURCE_QUALIFICATION_INFORMATION_BINDING_INVALID"
            )
        event_digests.append(str(record["information_event_digest"]))
        event_refs.append(binding)
    failures = dict(snapshot.get("optional_failures", {}))
    return self_digest(
        {
            "schema_id": "theory_paper_v31_source_qualification_completion",
            "schema_version": "1.0.0",
            "qualification_id": plan["qualification_id"],
            "completed_at": completed_at,
            "decision_at": decision_at,
            "source_qualification_plan_digest": plan_digest,
            "source_qualification_reservation_digest": reservation_digest,
            "snapshot_binding": snapshot_ref,
            "native_market_snapshot_digest": snapshot_digest,
            "raw_bindings": raw_refs,
            "source_capture_record_digests": {
                request_id: str(captures[request_id]["record_digest"])
                for request_id in sorted(captures)
            },
            "required_request_ids": list(REQUIRED_REQUEST_IDS),
            "optional_request_ids": list(OPTIONAL_REQUEST_IDS),
            "optional_failures": dict(sorted(failures.items())),
            "pit_dataset_binding": dataset_ref,
            "pit_dataset_digest": pit_dataset["dataset_digest"],
            "information_event_bindings": event_refs,
            "information_event_digests": event_digests,
            "adapter_id": _text(
                adapter_id, "V31_SOURCE_QUALIFICATION_ADAPTER_ID_INVALID"
            ),
            "source_evidence_boundary": "SOURCE_ATTESTED",
            "source_quality_ceiling": "VERIFIED_SECONDARY",
            "required_requests_complete": True,
            "raw_bytes_read_back_and_verified": True,
            "missing_is_zero": False,
            "unknown_count": pit_dataset["unknown_count"],
            "retry_count": 0,
            "attempt_count": 1,
            "qualification_only": True,
            "research_run_created": False,
            "experiment_start_authorized": False,
            "account_access": False,
            "paper_trading": False,
            "live_trading": False,
            "order_submission": False,
            "credential_access": False,
            "funds_access": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
            "credentials_accessed": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "source_qualification_completion_digest",
    )


def verify_v31_source_qualification_completion(
    document: Mapping[str, Any]
) -> str:
    try:
        supplied = verify_self_digest(
            document, "source_qualification_completion_digest"
        )
    except ValueError as exc:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_COMPLETION_DIGEST_INVALID"
        ) from exc
    if (
        document.get("schema_id")
        != "theory_paper_v31_source_qualification_completion"
        or document.get("schema_version") != "1.0.0"
        or document.get("required_request_ids") != list(REQUIRED_REQUEST_IDS)
        or document.get("optional_request_ids") != list(OPTIONAL_REQUEST_IDS)
        or document.get("source_evidence_boundary") != "SOURCE_ATTESTED"
        or document.get("source_quality_ceiling") != "VERIFIED_SECONDARY"
        or document.get("required_requests_complete") is not True
        or document.get("raw_bytes_read_back_and_verified") is not True
        or document.get("missing_is_zero") is not False
        or document.get("retry_count") != 0
        or document.get("attempt_count") != 1
        or document.get("qualification_only") is not True
        or document.get("research_run_created") is not False
        or document.get("experiment_start_authorized") is not False
        or document.get("account_access") is not False
        or document.get("paper_trading") is not False
        or document.get("live_trading") is not False
        or document.get("order_submission") is not False
        or document.get("credential_access") is not False
        or document.get("funds_access") is not False
        or document.get("account_data_accessed") is not False
        or document.get("order_data_accessed") is not False
        or document.get("credentials_accessed") is not False
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_COMPLETION_BOUNDARY_INVALID"
        )
    _text(document.get("qualification_id"), "V31_SOURCE_QUALIFICATION_ID_INVALID")
    _time(document.get("decision_at"), "V31_SOURCE_QUALIFICATION_DECISION_TIME_INVALID")
    if _time(
        document.get("completed_at"),
        "V31_SOURCE_QUALIFICATION_COMPLETION_TIME_INVALID",
    ) < _time(
        document.get("decision_at"),
        "V31_SOURCE_QUALIFICATION_DECISION_TIME_INVALID",
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_COMPLETION_PRECEDES_DECISION"
        )
    for field in (
        "source_qualification_plan_digest",
        "source_qualification_reservation_digest",
        "native_market_snapshot_digest",
        "pit_dataset_digest",
    ):
        _digest(document.get(field), "V31_SOURCE_QUALIFICATION_COMPLETION_BINDING_INVALID")
    if not isinstance(document.get("raw_bindings"), Mapping) or not document[
        "raw_bindings"
    ]:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_COMPLETION_BINDING_INVALID"
        )
    return supplied


def seal_v31_source_qualification_failure(
    *,
    plan: Mapping[str, Any],
    reservation: Mapping[str, Any],
    failed_at: str,
    failed_phase: str,
    reason_code: str,
    root_cause_code: str,
) -> dict[str, Any]:
    plan_digest = verify_v31_source_qualification_plan(plan)
    reservation_digest = verify_v31_source_qualification_reservation(
        reservation, plan=plan
    )
    _time(failed_at, "V31_SOURCE_QUALIFICATION_FAILURE_TIME_INVALID")
    return self_digest(
        {
            "schema_id": "theory_paper_v31_source_qualification_failure",
            "schema_version": "1.1.0",
            "qualification_id": plan["qualification_id"],
            "failed_at": failed_at,
            "failed_phase": _text(
                failed_phase, "V31_SOURCE_QUALIFICATION_FAILURE_PHASE_INVALID"
            ),
            "reason_code": _text(
                reason_code, "V31_SOURCE_QUALIFICATION_FAILURE_REASON_INVALID"
            ),
            "root_cause_code": _text(
                root_cause_code,
                "V31_SOURCE_QUALIFICATION_FAILURE_ROOT_CAUSE_INVALID",
            ),
            "source_qualification_plan_digest": plan_digest,
            "source_qualification_reservation_digest": reservation_digest,
            "attempt_count": 1,
            "retry_allowed": False,
            "partial_evidence_preserved": True,
            "qualification_only": True,
            "research_run_created": False,
            "experiment_start_authorized": False,
            "account_access": False,
            "paper_trading": False,
            "live_trading": False,
            "order_submission": False,
            "credential_access": False,
            "funds_access": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "source_qualification_failure_digest",
    )


def verify_v31_source_qualification_failure(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(
            document, "source_qualification_failure_digest"
        )
    except ValueError as exc:
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_FAILURE_DIGEST_INVALID"
        ) from exc
    version = document.get("schema_version")
    expected_fields = (
        _FAILURE_V1_FIELDS
        if version == "1.0.0"
        else _FAILURE_V1_1_FIELDS
        if version == "1.1.0"
        else frozenset()
    )
    if (
        set(document) != expected_fields
        or document.get("schema_id")
        != "theory_paper_v31_source_qualification_failure"
        or document.get("attempt_count") != 1
        or document.get("retry_allowed") is not False
        or document.get("partial_evidence_preserved") is not True
        or document.get("qualification_only") is not True
        or document.get("research_run_created") is not False
        or document.get("experiment_start_authorized") is not False
        or document.get("account_access") is not False
        or document.get("paper_trading") is not False
        or document.get("live_trading") is not False
        or document.get("order_submission") is not False
        or document.get("credential_access") is not False
        or document.get("funds_access") is not False
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V31SourceQualificationError(
            "V31_SOURCE_QUALIFICATION_FAILURE_BOUNDARY_INVALID"
        )
    _text(document.get("failed_phase"), "V31_SOURCE_QUALIFICATION_FAILURE_PHASE_INVALID")
    _text(document.get("reason_code"), "V31_SOURCE_QUALIFICATION_FAILURE_REASON_INVALID")
    if version == "1.1.0":
        _text(
            document.get("root_cause_code"),
            "V31_SOURCE_QUALIFICATION_FAILURE_ROOT_CAUSE_INVALID",
        )
    _time(document.get("failed_at"), "V31_SOURCE_QUALIFICATION_FAILURE_TIME_INVALID")
    return supplied


__all__ = [
    "APPROVED_V31_THEORY_SHA256",
    "OKX_PUBLIC_BASE_URL",
    "OKX_QUALIFICATION_INSTRUMENT_ID",
    "OPTIONAL_FAILURE_KEYS",
    "OPTIONAL_REQUEST_IDS",
    "QUALIFICATION_MAX_RESPONSE_BYTES",
    "QUALIFICATION_TIMEOUT_SECONDS",
    "REQUEST_SPECS",
    "REQUIRED_REQUEST_IDS",
    "V31SourceQualificationError",
    "initialize_v31_source_qualification_checkpoint",
    "seal_v31_source_qualification_completion",
    "seal_v31_source_qualification_failure",
    "seal_v31_source_qualification_information_event_record",
    "seal_v31_source_qualification_plan",
    "seal_v31_source_qualification_reservation",
    "transition_v31_source_qualification_checkpoint",
    "validate_v31_source_qualification_collection",
    "verify_v31_source_qualification_checkpoint",
    "verify_v31_source_qualification_completion",
    "verify_v31_source_qualification_failure",
    "verify_v31_source_qualification_information_event_record",
    "verify_v31_source_qualification_plan",
    "verify_v31_source_qualification_reservation",
]
