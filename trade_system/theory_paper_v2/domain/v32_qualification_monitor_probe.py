"""Typed one-shot public-mark probe used only by V3.2 qualification.

The probe proves that the frozen runtime can wait for an absolute 15 minute
boundary, perform one public OKX mark request, durably retain the raw response,
and replay the resulting observation.  It is deliberately not an experiment
outcome schedule and cannot be counted toward the target run's 48 outcomes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import base64
import hashlib
import re
from typing import Any, Mapping

from .contracts.canonical import self_digest, verify_self_digest
from .governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    QUALIFICATION_PROFILE,
    verify_v32_authority_v1,
)
from .v32_outcome_tick import TRANSPORT_COVERAGE_FAILURE_CODES


class V32QualificationMonitorProbeError(ValueError):
    """A qualification monitor probe document failed closed."""


SCHEMA_VERSION = "1.1.0"
SCHEDULE_SCHEMA_ID = "theory_paper_v32_qualification_monitor_probe_v1"
SCHEDULE_DIGEST_FIELD = "qualification_monitor_probe_digest"
ATTEMPT_SCHEMA_ID = "theory_paper_v32_qualification_monitor_probe_attempt_v1"
ATTEMPT_DIGEST_FIELD = "qualification_monitor_probe_attempt_digest"
CAPTURE_SCHEMA_ID = "theory_paper_v32_qualification_monitor_probe_capture_v1"
CAPTURE_DIGEST_FIELD = "qualification_monitor_probe_capture_digest"
OBSERVATION_SCHEMA_ID = (
    "theory_paper_v32_qualification_monitor_probe_observation_v1"
)
OBSERVATION_DIGEST_FIELD = "qualification_monitor_probe_observation_digest"
COMPLETION_SCHEMA_ID = (
    "theory_paper_v32_qualification_monitor_probe_completion_v1"
)
COMPLETION_DIGEST_FIELD = "qualification_monitor_probe_completion_digest"
FAILURE_SCHEMA_ID = "theory_paper_v32_qualification_monitor_probe_failure_v1"
FAILURE_DIGEST_FIELD = "qualification_monitor_probe_failure_digest"

INSTRUMENT_ID = "BTC-USDT-SWAP"
OBSERVABLE_REF = "metric:okx-public-mark-price-usdt"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
PROBE_DELAY_SECONDS = 15 * 60
PROBE_GRACE_SECONDS = 15 * 60

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SCHEDULE_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "probe_id", "qualification_run_id",
        "target_run_id", "qualification_authority_digest",
        "final_action_plan_digest", "selection_consumption_digest",
        "decision_time", "due_at", "grace_seconds", "expires_at",
        "observable_ref", "instrument_id",
        "attempt_limit", "retry_allowed", "outcome_schedule_count",
        "counted_toward_target", "probe_purpose", "source_scope",
        "external_execution_authority", "executable", "account_access",
        "order_submission", SCHEDULE_DIGEST_FIELD,
    }
)
_ATTEMPT_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "probe_id", "qualification_run_id",
        "target_run_id", "schedule_digest", "due_at", "expires_at", "reserved_at",
        "attempt_number", "max_network_requests", "retry_allowed",
        "source_request_id", "request_operation", "source_scope",
        "external_execution_authority", "executable", "account_access",
        "order_submission", ATTEMPT_DIGEST_FIELD,
    }
)
_CAPTURE_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "probe_id", "attempt_digest",
        "requested_at", "captured_at", "transport_status", "network_request_count",
        "response_received_at", "http_status", "final_url",
        "raw_payload_base64", "raw_payload_sha256", "failure_code",
        "retry_allowed", "source_scope", "external_execution_authority",
        "executable", "account_access", "order_submission",
        CAPTURE_DIGEST_FIELD,
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "probe_id", "attempt_digest",
        "capture_digest", "normalized_at", "status", "observable_ref",
        "instrument_id", "value", "provider_as_of", "available_at",
        "quality", "missingness", "raw_payload_sha256", "attempt_count",
        "retry_allowed", "source_scope", "external_execution_authority",
        "executable", "account_access", "order_submission",
        OBSERVATION_DIGEST_FIELD,
    }
)
_COMPLETION_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "probe_id", "qualification_run_id",
        "target_run_id", "schedule_digest", "attempt_digest",
        "capture_digest", "observation_digest", "started_at", "completed_at",
        "attempt_count", "network_request_count", "retry_allowed",
        "full_replay_required", "outcome_schedule_count",
        "counted_toward_target", "source_scope",
        "external_execution_authority", "executable", "account_access",
        "order_submission", COMPLETION_DIGEST_FIELD,
    }
)
_FAILURE_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "probe_id", "qualification_run_id",
        "target_run_id", "schedule_digest", "attempt_digest", "capture_digest",
        "failed_at", "failure_code", "attempt_count", "network_request_count",
        "retry_allowed", "terminal", "outcome_schedule_count",
        "counted_toward_target", "source_scope", "external_execution_authority",
        "executable", "account_access", "order_submission", FAILURE_DIGEST_FIELD,
    }
)


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "account_access": False,
        "order_submission": False,
    }


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32QualificationMonitorProbeError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32QualificationMonitorProbeError(code)
    return value


def _moment(value: Any, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32QualificationMonitorProbeError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text
    ):
        raise V32QualificationMonitorProbeError(code)
    return parsed.astimezone(UTC)


def _time(value: Any, code: str) -> str:
    _moment(value, code)
    return str(value)


def _assert_fields(document: Mapping[str, Any], fields: frozenset[str], code: str) -> None:
    if not isinstance(document, Mapping) or set(document) != fields:
        raise V32QualificationMonitorProbeError(code)


def _assert_boundary(document: Mapping[str, Any], code: str) -> None:
    if any(document.get(key) != value for key, value in _boundary().items()):
        raise V32QualificationMonitorProbeError(code)


def build_v32_qualification_monitor_probe_v1(
    *,
    probe_id: str,
    qualification_authority: Mapping[str, Any],
    final_action_plan_digest: str,
    selection_consumption_digest: str,
    decision_time: str,
) -> dict[str, Any]:
    authority_digest = verify_v32_authority_v1(qualification_authority)
    if (
        qualification_authority.get("profile") != QUALIFICATION_PROFILE
        or qualification_authority.get("outcome_schedules") != 0
        or qualification_authority.get("qualification_monitor_probes") != 1
    ):
        raise V32QualificationMonitorProbeError("V32_PROBE_AUTHORITY_INVALID")
    decided = _moment(decision_time, "V32_PROBE_DECISION_TIME_INVALID")
    due = decided + timedelta(seconds=PROBE_DELAY_SECONDS)
    expires = due + timedelta(seconds=PROBE_GRACE_SECONDS)
    return self_digest(
        {
            "schema_id": SCHEDULE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "probe_id": _text(probe_id, "V32_PROBE_ID_INVALID"),
            "qualification_run_id": qualification_authority["run_id"],
            "target_run_id": qualification_authority["target_run_id"],
            "qualification_authority_digest": authority_digest,
            "final_action_plan_digest": _digest(
                final_action_plan_digest, "V32_PROBE_PLAN_DIGEST_INVALID"
            ),
            "selection_consumption_digest": _digest(
                selection_consumption_digest, "V32_PROBE_SELECTION_DIGEST_INVALID"
            ),
            "decision_time": _time(decision_time, "V32_PROBE_DECISION_TIME_INVALID"),
            "due_at": due.isoformat().replace("+00:00", "Z"),
            "grace_seconds": PROBE_GRACE_SECONDS,
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "observable_ref": OBSERVABLE_REF,
            "instrument_id": INSTRUMENT_ID,
            "attempt_limit": 1,
            "retry_allowed": False,
            "outcome_schedule_count": 0,
            "counted_toward_target": False,
            "probe_purpose": "QUALIFICATION_MONITOR_PROBE_ONLY_NOT_OUTCOME_EVALUATION",
            **_boundary(),
        },
        SCHEDULE_DIGEST_FIELD,
    )


def verify_v32_qualification_monitor_probe_v1(document: Mapping[str, Any]) -> str:
    _assert_fields(document, _SCHEDULE_FIELDS, "V32_PROBE_SCHEDULE_INVALID")
    try:
        supplied = verify_self_digest(document, SCHEDULE_DIGEST_FIELD)
        if (
            _moment(document["due_at"], "V32_PROBE_DUE_INVALID")
            != _moment(document["decision_time"], "V32_PROBE_TIME_INVALID")
            + timedelta(seconds=PROBE_DELAY_SECONDS)
            or document["grace_seconds"] != PROBE_GRACE_SECONDS
            or _moment(document["expires_at"], "V32_PROBE_EXPIRES_INVALID")
            != _moment(document["due_at"], "V32_PROBE_DUE_INVALID")
            + timedelta(seconds=PROBE_GRACE_SECONDS)
            or document["observable_ref"] != OBSERVABLE_REF
            or document["instrument_id"] != INSTRUMENT_ID
            or document["attempt_limit"] != 1
            or document["retry_allowed"] is not False
            or document["outcome_schedule_count"] != 0
            or document["counted_toward_target"] is not False
            or document["probe_purpose"]
            != "QUALIFICATION_MONITOR_PROBE_ONLY_NOT_OUTCOME_EVALUATION"
        ):
            raise V32QualificationMonitorProbeError("V32_PROBE_SCHEDULE_INVALID")
        for key in (
            "qualification_authority_digest",
            "final_action_plan_digest",
            "selection_consumption_digest",
        ):
            _digest(document[key], "V32_PROBE_SCHEDULE_INVALID")
        _assert_boundary(document, "V32_PROBE_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32QualificationMonitorProbeError):
            raise
        raise V32QualificationMonitorProbeError("V32_PROBE_SCHEDULE_INVALID") from exc
    return supplied


def build_v32_qualification_monitor_probe_attempt_v1(
    *, schedule: Mapping[str, Any], reserved_at: str
) -> dict[str, Any]:
    schedule_digest = verify_v32_qualification_monitor_probe_v1(schedule)
    reserved = _moment(reserved_at, "V32_PROBE_RESERVED_AT_INVALID")
    if not (
        _moment(schedule["due_at"], "V32_PROBE_DUE_INVALID")
        <= reserved
        <= _moment(schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID")
    ):
        raise V32QualificationMonitorProbeError("V32_PROBE_NOT_DUE")
    source_request_id = f"v32-qualification-monitor-probe:{schedule_digest}"
    return self_digest(
        {
            "schema_id": ATTEMPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "probe_id": schedule["probe_id"],
            "qualification_run_id": schedule["qualification_run_id"],
            "target_run_id": schedule["target_run_id"],
            "schedule_digest": schedule_digest,
            "due_at": schedule["due_at"],
            "expires_at": schedule["expires_at"],
            "reserved_at": _time(reserved_at, "V32_PROBE_RESERVED_AT_INVALID"),
            "attempt_number": 1,
            "max_network_requests": 1,
            "retry_allowed": False,
            "source_request_id": source_request_id,
            "request_operation": "GET_PUBLIC_MARK_OBSERVATION",
            **_boundary(),
        },
        ATTEMPT_DIGEST_FIELD,
    )


def verify_v32_qualification_monitor_probe_attempt_v1(
    document: Mapping[str, Any], *, schedule: Mapping[str, Any]
) -> str:
    _assert_fields(document, _ATTEMPT_FIELDS, "V32_PROBE_ATTEMPT_INVALID")
    try:
        supplied = verify_self_digest(document, ATTEMPT_DIGEST_FIELD)
        rebuilt = build_v32_qualification_monitor_probe_attempt_v1(
            schedule=schedule, reserved_at=document["reserved_at"]
        )
        if dict(document) != rebuilt:
            raise V32QualificationMonitorProbeError("V32_PROBE_ATTEMPT_INVALID")
        _assert_boundary(document, "V32_PROBE_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32QualificationMonitorProbeError):
            raise
        raise V32QualificationMonitorProbeError("V32_PROBE_ATTEMPT_INVALID") from exc
    return supplied


def verify_v32_qualification_monitor_probe_attempt_intrinsic_v1(
    document: Mapping[str, Any],
) -> str:
    """Verify the exact public-capture request without loading its schedule."""

    _assert_fields(document, _ATTEMPT_FIELDS, "V32_PROBE_ATTEMPT_INVALID")
    try:
        supplied = verify_self_digest(document, ATTEMPT_DIGEST_FIELD)
        if (
            document["schema_id"] != ATTEMPT_SCHEMA_ID
            or document["schema_version"] != SCHEMA_VERSION
            or document["attempt_number"] != 1
            or document["max_network_requests"] != 1
            or document["retry_allowed"] is not False
            or document["request_operation"] != "GET_PUBLIC_MARK_OBSERVATION"
            or document["source_request_id"]
            != f"v32-qualification-monitor-probe:{document['schedule_digest']}"
            or _moment(document["reserved_at"], "V32_PROBE_RESERVED_AT_INVALID")
            < _moment(document["due_at"], "V32_PROBE_DUE_INVALID")
            or _moment(document["reserved_at"], "V32_PROBE_RESERVED_AT_INVALID")
            > _moment(document["expires_at"], "V32_PROBE_EXPIRES_INVALID")
        ):
            raise V32QualificationMonitorProbeError("V32_PROBE_ATTEMPT_INVALID")
        _digest(document["schedule_digest"], "V32_PROBE_ATTEMPT_INVALID")
        _assert_boundary(document, "V32_PROBE_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32QualificationMonitorProbeError):
            raise
        raise V32QualificationMonitorProbeError("V32_PROBE_ATTEMPT_INVALID") from exc
    return supplied


def build_v32_qualification_monitor_probe_capture_v1(
    *,
    attempt: Mapping[str, Any],
    schedule: Mapping[str, Any],
    requested_at: str,
    captured_at: str,
    transport_status: str,
    response_received_at: str | None,
    http_status: int | None,
    final_url: str | None,
    raw_payload: bytes | None,
    failure_code: str | None,
) -> dict[str, Any]:
    attempt_digest = verify_v32_qualification_monitor_probe_attempt_v1(
        attempt, schedule=schedule
    )
    requested = _moment(requested_at, "V32_PROBE_REQUEST_TIME_INVALID")
    captured = _moment(captured_at, "V32_PROBE_CAPTURE_TIME_INVALID")
    if not (
        _moment(attempt["reserved_at"], "V32_PROBE_RESERVED_AT_INVALID")
        <= requested
        <= _moment(attempt["expires_at"], "V32_PROBE_EXPIRES_INVALID")
    ):
        raise V32QualificationMonitorProbeError("V32_PROBE_CAPTURE_TIME_INVALID")
    if transport_status == "RESPONSE_CAPTURED":
        response_received = _moment(
            response_received_at, "V32_PROBE_RESPONSE_TIME_INVALID"
        )
        if (
            not isinstance(http_status, int)
            or isinstance(http_status, bool)
            or not 100 <= http_status <= 599
            or not isinstance(final_url, str)
            or not final_url
            or final_url != final_url.strip()
            or not isinstance(raw_payload, bytes)
            or failure_code is not None
        ):
            raise V32QualificationMonitorProbeError("V32_PROBE_CAPTURE_INVALID")
        encoded = base64.b64encode(raw_payload).decode("ascii")
        raw_sha = hashlib.sha256(raw_payload).hexdigest()
    elif transport_status == "NO_RESPONSE":
        if (
            response_received_at is not None
            or http_status is not None
            or final_url is not None
            or raw_payload is not None
            or not isinstance(failure_code, str)
            or failure_code not in TRANSPORT_COVERAGE_FAILURE_CODES
        ):
            raise V32QualificationMonitorProbeError("V32_PROBE_CAPTURE_INVALID")
        response_received = None
        encoded = None
        raw_sha = None
    else:
        raise V32QualificationMonitorProbeError("V32_PROBE_CAPTURE_INVALID")
    return self_digest(
        {
            "schema_id": CAPTURE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "probe_id": attempt["probe_id"],
            "attempt_digest": attempt_digest,
            "requested_at": _time(requested_at, "V32_PROBE_REQUEST_TIME_INVALID"),
            "captured_at": _time(captured_at, "V32_PROBE_CAPTURE_TIME_INVALID"),
            "transport_status": transport_status,
            "network_request_count": 1,
            "response_received_at": (
                None
                if response_received is None
                else _time(
                    response_received_at, "V32_PROBE_RESPONSE_TIME_INVALID"
                )
            ),
            "http_status": http_status,
            "final_url": final_url,
            "raw_payload_base64": encoded,
            "raw_payload_sha256": raw_sha,
            "failure_code": failure_code,
            "retry_allowed": False,
            **_boundary(),
        },
        CAPTURE_DIGEST_FIELD,
    )


def verify_v32_qualification_monitor_probe_capture_v1(
    document: Mapping[str, Any], *, attempt: Mapping[str, Any], schedule: Mapping[str, Any]
) -> str:
    _assert_fields(document, _CAPTURE_FIELDS, "V32_PROBE_CAPTURE_INVALID")
    try:
        supplied = verify_self_digest(document, CAPTURE_DIGEST_FIELD)
        encoded = document["raw_payload_base64"]
        raw = None if encoded is None else base64.b64decode(encoded, validate=True)
        rebuilt = build_v32_qualification_monitor_probe_capture_v1(
            attempt=attempt,
            schedule=schedule,
            requested_at=document["requested_at"],
            captured_at=document["captured_at"],
            transport_status=document["transport_status"],
            response_received_at=document["response_received_at"],
            http_status=document["http_status"],
            final_url=document["final_url"],
            raw_payload=raw,
            failure_code=document["failure_code"],
        )
        if dict(document) != rebuilt:
            raise V32QualificationMonitorProbeError("V32_PROBE_CAPTURE_INVALID")
        _assert_boundary(document, "V32_PROBE_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError, base64.binascii.Error) as exc:
        if isinstance(exc, V32QualificationMonitorProbeError):
            raise
        raise V32QualificationMonitorProbeError("V32_PROBE_CAPTURE_INVALID") from exc
    return supplied


def decode_v32_qualification_monitor_probe_raw_v1(
    capture: Mapping[str, Any], *, attempt: Mapping[str, Any], schedule: Mapping[str, Any]
) -> bytes | None:
    verify_v32_qualification_monitor_probe_capture_v1(
        capture, attempt=attempt, schedule=schedule
    )
    if capture["raw_payload_base64"] is None:
        return None
    return base64.b64decode(capture["raw_payload_base64"], validate=True)


def build_v32_qualification_monitor_probe_observation_v1(
    *,
    schedule: Mapping[str, Any],
    attempt: Mapping[str, Any],
    capture: Mapping[str, Any],
    normalized_at: str,
    value: str | None,
    provider_as_of: str | None,
    quality: str | None,
) -> dict[str, Any]:
    attempt_digest = verify_v32_qualification_monitor_probe_attempt_v1(
        attempt, schedule=schedule
    )
    capture_digest = verify_v32_qualification_monitor_probe_capture_v1(
        capture, attempt=attempt, schedule=schedule
    )
    normalized = _moment(normalized_at, "V32_PROBE_NORMALIZED_AT_INVALID")
    if not (
        _moment(capture["captured_at"], "V32_PROBE_CAPTURE_TIME_INVALID")
        <= normalized
        <= _moment(schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID")
    ):
        raise V32QualificationMonitorProbeError("V32_PROBE_NORMALIZED_AT_INVALID")
    if capture["transport_status"] == "RESPONSE_CAPTURED":
        try:
            price = Decimal(_text(value, "V32_PROBE_VALUE_INVALID"))
        except (InvalidOperation, ValueError) as exc:
            raise V32QualificationMonitorProbeError("V32_PROBE_VALUE_INVALID") from exc
        if not price.is_finite() or price <= 0:
            raise V32QualificationMonitorProbeError("V32_PROBE_VALUE_INVALID")
        provider = _time(provider_as_of, "V32_PROBE_PROVIDER_TIME_INVALID")
        if quality not in {"HIGH", "MEDIUM"}:
            raise V32QualificationMonitorProbeError("V32_PROBE_QUALITY_INVALID")
        status, observed_quality, missingness = (
            "OBSERVED_PUBLIC_MARK", quality, "OBSERVED"
        )
        value_text = format(price, "f")
    else:
        if value is not None or provider_as_of is not None:
            raise V32QualificationMonitorProbeError("V32_PROBE_UNKNOWN_VALUE_INVALID")
        provider = None
        if quality is not None:
            raise V32QualificationMonitorProbeError("V32_PROBE_QUALITY_INVALID")
        status, observed_quality, missingness = "COVERAGE_LOSS", "UNKNOWN", "UNKNOWN"
        value_text = None
    return self_digest(
        {
            "schema_id": OBSERVATION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "probe_id": schedule["probe_id"],
            "attempt_digest": attempt_digest,
            "capture_digest": capture_digest,
            "normalized_at": _time(normalized_at, "V32_PROBE_NORMALIZED_AT_INVALID"),
            "status": status,
            "observable_ref": OBSERVABLE_REF,
            "instrument_id": INSTRUMENT_ID,
            "value": value_text,
            "provider_as_of": provider,
            "available_at": capture["captured_at"],
            "quality": observed_quality,
            "missingness": missingness,
            "raw_payload_sha256": capture["raw_payload_sha256"],
            "attempt_count": 1,
            "retry_allowed": False,
            **_boundary(),
        },
        OBSERVATION_DIGEST_FIELD,
    )


def verify_v32_qualification_monitor_probe_observation_v1(
    document: Mapping[str, Any], *, schedule: Mapping[str, Any], attempt: Mapping[str, Any], capture: Mapping[str, Any]
) -> str:
    _assert_fields(document, _OBSERVATION_FIELDS, "V32_PROBE_OBSERVATION_INVALID")
    try:
        supplied = verify_self_digest(document, OBSERVATION_DIGEST_FIELD)
        rebuilt = build_v32_qualification_monitor_probe_observation_v1(
            schedule=schedule,
            attempt=attempt,
            capture=capture,
            normalized_at=document["normalized_at"],
            value=document["value"],
            provider_as_of=document["provider_as_of"],
            quality=document["quality"] if document["status"] == "OBSERVED_PUBLIC_MARK" else None,
        )
        if dict(document) != rebuilt:
            raise V32QualificationMonitorProbeError("V32_PROBE_OBSERVATION_INVALID")
        _assert_boundary(document, "V32_PROBE_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32QualificationMonitorProbeError):
            raise
        raise V32QualificationMonitorProbeError("V32_PROBE_OBSERVATION_INVALID") from exc
    return supplied


def build_v32_qualification_monitor_probe_completion_v1(
    *, schedule: Mapping[str, Any], attempt: Mapping[str, Any], capture: Mapping[str, Any], observation: Mapping[str, Any], completed_at: str
) -> dict[str, Any]:
    schedule_digest = verify_v32_qualification_monitor_probe_v1(schedule)
    attempt_digest = verify_v32_qualification_monitor_probe_attempt_v1(attempt, schedule=schedule)
    capture_digest = verify_v32_qualification_monitor_probe_capture_v1(capture, attempt=attempt, schedule=schedule)
    observation_digest = verify_v32_qualification_monitor_probe_observation_v1(
        observation, schedule=schedule, attempt=attempt, capture=capture
    )
    if not (
        _moment(observation["normalized_at"], "V32_PROBE_NORMALIZED_AT_INVALID")
        <= _moment(completed_at, "V32_PROBE_COMPLETED_AT_INVALID")
        <= _moment(schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID")
    ):
        raise V32QualificationMonitorProbeError("V32_PROBE_COMPLETED_AT_INVALID")
    return self_digest(
        {
            "schema_id": COMPLETION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "probe_id": schedule["probe_id"],
            "qualification_run_id": schedule["qualification_run_id"],
            "target_run_id": schedule["target_run_id"],
            "schedule_digest": schedule_digest,
            "attempt_digest": attempt_digest,
            "capture_digest": capture_digest,
            "observation_digest": observation_digest,
            "started_at": attempt["reserved_at"],
            "completed_at": _time(completed_at, "V32_PROBE_COMPLETED_AT_INVALID"),
            "attempt_count": 1,
            "network_request_count": 1,
            "retry_allowed": False,
            "full_replay_required": True,
            "outcome_schedule_count": 0,
            "counted_toward_target": False,
            **_boundary(),
        },
        COMPLETION_DIGEST_FIELD,
    )


def verify_v32_qualification_monitor_probe_completion_v1(
    document: Mapping[str, Any], *, schedule: Mapping[str, Any], attempt: Mapping[str, Any], capture: Mapping[str, Any], observation: Mapping[str, Any]
) -> str:
    _assert_fields(document, _COMPLETION_FIELDS, "V32_PROBE_COMPLETION_INVALID")
    try:
        supplied = verify_self_digest(document, COMPLETION_DIGEST_FIELD)
        rebuilt = build_v32_qualification_monitor_probe_completion_v1(
            schedule=schedule,
            attempt=attempt,
            capture=capture,
            observation=observation,
            completed_at=document["completed_at"],
        )
        if dict(document) != rebuilt:
            raise V32QualificationMonitorProbeError("V32_PROBE_COMPLETION_INVALID")
        _assert_boundary(document, "V32_PROBE_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32QualificationMonitorProbeError):
            raise
        raise V32QualificationMonitorProbeError("V32_PROBE_COMPLETION_INVALID") from exc
    return supplied


def build_v32_qualification_monitor_probe_failure_v1(
    *,
    schedule: Mapping[str, Any],
    failed_at: str,
    failure_code: str,
    attempt: Mapping[str, Any] | None = None,
    capture: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    schedule_digest = verify_v32_qualification_monitor_probe_v1(schedule)
    when = _moment(failed_at, "V32_PROBE_FAILURE_TIME_INVALID")
    attempt_digest = None
    capture_digest = None
    network_requests = 0
    attempt_count = 0
    code = _text(failure_code, "V32_PROBE_FAILURE_CODE_INVALID")
    if attempt is None:
        if capture is not None or code != "QUALIFICATION_MONITOR_PROBE_WINDOW_EXPIRED":
            raise V32QualificationMonitorProbeError("V32_PROBE_FAILURE_INVALID")
        if when <= _moment(schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID"):
            raise V32QualificationMonitorProbeError("V32_PROBE_FAILURE_TIME_INVALID")
    else:
        attempt_digest = verify_v32_qualification_monitor_probe_attempt_v1(
            attempt, schedule=schedule
        )
        if capture is None:
            if code not in {
                "QUALIFICATION_MONITOR_PROBE_PUBLIC_SOURCE_UNAVAILABLE",
                "QUALIFICATION_MONITOR_PROBE_RESPONSE_AFTER_WINDOW",
                "QUALIFICATION_MONITOR_PROBE_WINDOW_EXPIRED_AFTER_RESERVATION",
            }:
                raise V32QualificationMonitorProbeError("V32_PROBE_FAILURE_INVALID")
            if when < _moment(attempt["reserved_at"], "V32_PROBE_RESERVED_AT_INVALID"):
                raise V32QualificationMonitorProbeError("V32_PROBE_FAILURE_TIME_INVALID")
        else:
            capture_digest = verify_v32_qualification_monitor_probe_capture_v1(
                capture, attempt=attempt, schedule=schedule
            )
            if when < _moment(capture["captured_at"], "V32_PROBE_CAPTURE_TIME_INVALID"):
                raise V32QualificationMonitorProbeError("V32_PROBE_FAILURE_TIME_INVALID")
        network_requests = (
            0
            if capture is None
            and code == "QUALIFICATION_MONITOR_PROBE_WINDOW_EXPIRED_AFTER_RESERVATION"
            else 1
        )
        attempt_count = 1
    return self_digest(
        {
            "schema_id": FAILURE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "probe_id": schedule["probe_id"],
            "qualification_run_id": schedule["qualification_run_id"],
            "target_run_id": schedule["target_run_id"],
            "schedule_digest": schedule_digest,
            "attempt_digest": attempt_digest,
            "capture_digest": capture_digest,
            "failed_at": _time(failed_at, "V32_PROBE_FAILURE_TIME_INVALID"),
            "failure_code": code,
            "attempt_count": attempt_count,
            "network_request_count": network_requests,
            "retry_allowed": False,
            "terminal": True,
            "outcome_schedule_count": 0,
            "counted_toward_target": False,
            **_boundary(),
        },
        FAILURE_DIGEST_FIELD,
    )


def verify_v32_qualification_monitor_probe_failure_v1(
    document: Mapping[str, Any],
    *,
    schedule: Mapping[str, Any],
    attempt: Mapping[str, Any] | None = None,
    capture: Mapping[str, Any] | None = None,
) -> str:
    _assert_fields(document, _FAILURE_FIELDS, "V32_PROBE_FAILURE_INVALID")
    try:
        supplied = verify_self_digest(document, FAILURE_DIGEST_FIELD)
        rebuilt = build_v32_qualification_monitor_probe_failure_v1(
            schedule=schedule,
            failed_at=document["failed_at"],
            failure_code=document["failure_code"],
            attempt=attempt,
            capture=capture,
        )
        if dict(document) != rebuilt:
            raise V32QualificationMonitorProbeError("V32_PROBE_FAILURE_INVALID")
        _assert_boundary(document, "V32_PROBE_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32QualificationMonitorProbeError):
            raise
        raise V32QualificationMonitorProbeError("V32_PROBE_FAILURE_INVALID") from exc
    return supplied


__all__ = [
    "ATTEMPT_DIGEST_FIELD", "ATTEMPT_SCHEMA_ID", "CAPTURE_DIGEST_FIELD",
    "CAPTURE_SCHEMA_ID", "COMPLETION_DIGEST_FIELD", "COMPLETION_SCHEMA_ID",
    "FAILURE_DIGEST_FIELD", "FAILURE_SCHEMA_ID",
    "OBSERVATION_DIGEST_FIELD", "OBSERVATION_SCHEMA_ID", "PROBE_DELAY_SECONDS",
    "PROBE_GRACE_SECONDS",
    "SCHEDULE_DIGEST_FIELD", "SCHEDULE_SCHEMA_ID", "V32QualificationMonitorProbeError",
    "build_v32_qualification_monitor_probe_attempt_v1",
    "build_v32_qualification_monitor_probe_capture_v1",
    "build_v32_qualification_monitor_probe_completion_v1",
    "build_v32_qualification_monitor_probe_failure_v1",
    "build_v32_qualification_monitor_probe_observation_v1",
    "build_v32_qualification_monitor_probe_v1",
    "decode_v32_qualification_monitor_probe_raw_v1",
    "verify_v32_qualification_monitor_probe_attempt_v1",
    "verify_v32_qualification_monitor_probe_attempt_intrinsic_v1",
    "verify_v32_qualification_monitor_probe_capture_v1",
    "verify_v32_qualification_monitor_probe_completion_v1",
    "verify_v32_qualification_monitor_probe_failure_v1",
    "verify_v32_qualification_monitor_probe_observation_v1",
    "verify_v32_qualification_monitor_probe_v1",
]
