"""Pure V3.1 v2 contracts for raw-first public outcome capture.

This module deliberately has no network, filesystem, account, order, paper, or
live-trading capability.  It owns three deterministic documents:

* a frozen provider-clock policy;
* a capture record that binds exact response bytes without interpreting them;
* a parse receipt reconstructed solely from the committed capture and policy.

The parser uses the local response-receive time for evaluation.  The provider
timestamp is retained unchanged (both as its raw millisecond text and its exact
UTC rendering) and is never silently clamped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import hashlib
import re
from typing import Any, Mapping

from .contracts.canonical import (
    CanonicalContractError,
    canonical_decimal,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)


OUTCOME_CAPTURE_SCHEMA_ID = "theory_paper_v31_public_outcome_capture_v2"
OUTCOME_CLOCK_POLICY_SCHEMA_ID = "theory_paper_v31_outcome_clock_policy_v2"
OUTCOME_PARSE_RECEIPT_SCHEMA_ID = (
    "theory_paper_v31_public_outcome_parse_receipt_v2"
)
OUTCOME_TRANSPORT_FAILURE_SCHEMA_ID = (
    "theory_paper_v31_public_outcome_transport_failure_v2"
)
OUTCOME_CAPTURE_SCHEMA_VERSION = "2.0.0"
OUTCOME_PARSER_VERSION = "V31_PUBLIC_OUTCOME_PARSER_2_0_0"

DEFAULT_MAX_PROVIDER_CLOCK_LEAD_MS = 2_000
DEFAULT_MAX_PROVIDER_AGE_MS = 5_000
OKX_MARK_PRICE_URL = (
    "https://www.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)
MAX_RAW_CAPTURE_BYTES = 1024 * 1024
PUBLIC_OUTCOME_TRANSPORT_FAILURE_CODES = frozenset(
    {
        "PUBLIC_CONNECTION_FAILURE",
        "PUBLIC_DNS_UNAVAILABLE",
        "PUBLIC_RESPONSE_BODY_LIMIT_EXCEEDED",
        "PUBLIC_TIMEOUT",
        "PUBLIC_TLS_FAILURE",
        "PUBLIC_TRANSPORT_IO_FAILURE",
    }
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class V31OutcomeCaptureContractError(ValueError):
    """A v2 capture, policy, or parse-receipt contract was not reconstructible."""


class OutcomeCaptureParseStatus(StrEnum):
    ADMITTED_OBSERVED = "ADMITTED_OBSERVED"
    ADMITTED_UNKNOWN = "ADMITTED_UNKNOWN"
    REJECTED = "REJECTED"


class OutcomeClockClass(StrEnum):
    EXACT = "EXACT"
    PROVIDER_LAG_WITHIN_BOUND = "PROVIDER_LAG_WITHIN_BOUND"
    PROVIDER_LEAD_WITHIN_BOUND = "PROVIDER_LEAD_WITHIN_BOUND"
    CLOCK_BOUND_EXCEEDED = "CLOCK_BOUND_EXCEEDED"
    UNAVAILABLE = "UNAVAILABLE"


def _authority_boundary() -> dict[str, Any]:
    return {
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
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


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31OutcomeCaptureContractError(code)
    return value


def _string(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise V31OutcomeCaptureContractError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31OutcomeCaptureContractError(code)
    return value


def _bounded_int(
    value: Any, *, minimum: int, maximum: int, code: str
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise V31OutcomeCaptureContractError(code)
    return value


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31OutcomeCaptureContractError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31OutcomeCaptureContractError(code) from exc
    if parsed.tzinfo is None:
        raise V31OutcomeCaptureContractError(code)
    return parsed.astimezone(UTC)


def _time_text(value: Any, code: str) -> str:
    parsed = _time(value, code)
    return parsed.isoformat().replace("+00:00", "Z")


def _milliseconds_since_epoch(value: datetime) -> Decimal:
    delta = value - _EPOCH
    return (
        Decimal(delta.days) * Decimal(86_400_000)
        + Decimal(delta.seconds) * Decimal(1_000)
        + Decimal(delta.microseconds) / Decimal(1_000)
    )


def build_outcome_clock_policy(
    *,
    max_provider_clock_lead_ms: int = DEFAULT_MAX_PROVIDER_CLOCK_LEAD_MS,
    max_provider_age_ms: int = DEFAULT_MAX_PROVIDER_AGE_MS,
) -> dict[str, Any]:
    """Build the preregistered, outcome-independent provider-clock policy."""

    lead = _bounded_int(
        max_provider_clock_lead_ms,
        minimum=0,
        maximum=60_000,
        code="V31_CAPTURE_CLOCK_LEAD_BOUND_INVALID",
    )
    age = _bounded_int(
        max_provider_age_ms,
        minimum=0,
        maximum=60_000,
        code="V31_CAPTURE_PROVIDER_AGE_BOUND_INVALID",
    )
    return self_digest(
        {
            "schema_id": OUTCOME_CLOCK_POLICY_SCHEMA_ID,
            "schema_version": OUTCOME_CAPTURE_SCHEMA_VERSION,
            "max_provider_clock_lead_ms": lead,
            "max_provider_age_ms": age,
            "evaluation_time_basis": "LOCAL_RESPONSE_RECEIVED_AT",
            "provider_time_handling": "PRESERVE_ORIGINAL_UNCLAMPED",
            "out_of_bound_valid_time_policy": "ADMITTED_UNKNOWN",
            "invalid_structure_time_value_policy": "REJECTED",
        },
        "clock_policy_digest",
    )


def verify_outcome_clock_policy(policy: Mapping[str, Any]) -> str:
    if not isinstance(policy, Mapping):
        raise V31OutcomeCaptureContractError("V31_CAPTURE_CLOCK_POLICY_INVALID")
    try:
        supplied = verify_self_digest(policy, "clock_policy_digest")
        rebuilt = build_outcome_clock_policy(
            max_provider_clock_lead_ms=policy["max_provider_clock_lead_ms"],
            max_provider_age_ms=policy["max_provider_age_ms"],
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31OutcomeCaptureContractError):
            raise
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_CLOCK_POLICY_INVALID"
        ) from exc
    if rebuilt != dict(policy) or supplied != rebuilt["clock_policy_digest"]:
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_CLOCK_POLICY_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_public_outcome_capture(
    *,
    run_id: str,
    cycle_index: int,
    monitor_plan_digest: str,
    monitor_attempt_digest: str,
    source_request_id: str,
    requested_at: str,
    request_started_at: str,
    response_received_at: str,
    monotonic_elapsed_ms: int,
    status_code: int,
    content_type: str,
    final_url: str,
    raw_payload: bytes,
) -> dict[str, Any]:
    """Bind exact response bytes and transport metadata without parsing the body."""

    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31OutcomeCaptureContractError("V31_CAPTURE_CYCLE_INDEX_INVALID")
    elapsed = _bounded_int(
        monotonic_elapsed_ms,
        minimum=0,
        maximum=60_000,
        code="V31_CAPTURE_MONOTONIC_ELAPSED_INVALID",
    )
    status = _bounded_int(
        status_code,
        minimum=100,
        maximum=599,
        code="V31_CAPTURE_HTTP_STATUS_INVALID",
    )
    if not isinstance(raw_payload, bytes) or len(raw_payload) > MAX_RAW_CAPTURE_BYTES:
        raise V31OutcomeCaptureContractError("V31_CAPTURE_RAW_BYTES_INVALID")
    raw_sha = hashlib.sha256(raw_payload).hexdigest()
    document = {
        "schema_id": OUTCOME_CAPTURE_SCHEMA_ID,
        "schema_version": OUTCOME_CAPTURE_SCHEMA_VERSION,
        "run_id": _text(run_id, "V31_CAPTURE_RUN_ID_INVALID"),
        "cycle_index": cycle_index,
        "monitor_plan_digest": _digest(
            monitor_plan_digest, "V31_CAPTURE_MONITOR_PLAN_DIGEST_INVALID"
        ),
        "monitor_attempt_digest": _digest(
            monitor_attempt_digest, "V31_CAPTURE_MONITOR_ATTEMPT_DIGEST_INVALID"
        ),
        "source_request_id": _text(
            source_request_id, "V31_CAPTURE_SOURCE_REQUEST_ID_INVALID"
        ),
        "request_method": "GET",
        "request_url": OKX_MARK_PRICE_URL,
        "final_url": _string(final_url, "V31_CAPTURE_FINAL_URL_INVALID"),
        "status_code": status,
        "content_type": _string(
            content_type, "V31_CAPTURE_CONTENT_TYPE_INVALID"
        ),
        "requested_at": _time_text(
            requested_at, "V31_CAPTURE_REQUESTED_AT_INVALID"
        ),
        "request_started_at": _time_text(
            request_started_at, "V31_CAPTURE_REQUEST_STARTED_AT_INVALID"
        ),
        "response_received_at": _time_text(
            response_received_at, "V31_CAPTURE_RESPONSE_RECEIVED_AT_INVALID"
        ),
        "monotonic_elapsed_ms": elapsed,
        "raw_capture_sha256": raw_sha,
        "raw_size_bytes": len(raw_payload),
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, "capture_digest")


def verify_public_outcome_capture(
    capture: Mapping[str, Any], *, raw_payload: bytes
) -> str:
    if not isinstance(capture, Mapping):
        raise V31OutcomeCaptureContractError("V31_CAPTURE_INVALID")
    try:
        supplied = verify_self_digest(capture, "capture_digest")
        if (
            capture.get("schema_id") != OUTCOME_CAPTURE_SCHEMA_ID
            or capture.get("schema_version") != OUTCOME_CAPTURE_SCHEMA_VERSION
            or capture.get("request_method") != "GET"
            or capture.get("request_url") != OKX_MARK_PRICE_URL
            or capture.get("authority_boundary") != _authority_boundary()
        ):
            raise V31OutcomeCaptureContractError("V31_CAPTURE_INVALID")
        rebuilt = build_public_outcome_capture(
            run_id=capture["run_id"],
            cycle_index=capture["cycle_index"],
            monitor_plan_digest=capture["monitor_plan_digest"],
            monitor_attempt_digest=capture["monitor_attempt_digest"],
            source_request_id=capture["source_request_id"],
            requested_at=capture["requested_at"],
            request_started_at=capture["request_started_at"],
            response_received_at=capture["response_received_at"],
            monotonic_elapsed_ms=capture["monotonic_elapsed_ms"],
            status_code=capture["status_code"],
            content_type=capture["content_type"],
            final_url=capture["final_url"],
            raw_payload=raw_payload,
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31OutcomeCaptureContractError):
            raise
        raise V31OutcomeCaptureContractError("V31_CAPTURE_INVALID") from exc
    if rebuilt != dict(capture) or supplied != rebuilt["capture_digest"]:
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_public_outcome_transport_failure(
    *,
    run_id: str,
    cycle_index: int,
    monitor_plan_digest: str,
    monitor_attempt_digest: str,
    source_request_id: str,
    requested_at: str,
    request_started_at: str,
    failure_at: str,
    monotonic_elapsed_ms: int,
    failure_code: str,
) -> dict[str, Any]:
    """Build a typed no-response receipt without persisting exception text."""

    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_TRANSPORT_FAILURE_CYCLE_INVALID"
        )
    elapsed = _bounded_int(
        monotonic_elapsed_ms,
        minimum=0,
        maximum=60_000,
        code="V31_CAPTURE_TRANSPORT_FAILURE_ELAPSED_INVALID",
    )
    if failure_code not in PUBLIC_OUTCOME_TRANSPORT_FAILURE_CODES:
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_TRANSPORT_FAILURE_CODE_INVALID"
        )
    requested_text = _time_text(
        requested_at, "V31_CAPTURE_TRANSPORT_FAILURE_TIME_INVALID"
    )
    started_text = _time_text(
        request_started_at, "V31_CAPTURE_TRANSPORT_FAILURE_TIME_INVALID"
    )
    failed_text = _time_text(
        failure_at, "V31_CAPTURE_TRANSPORT_FAILURE_TIME_INVALID"
    )
    if not (
        _time(requested_text, "V31_CAPTURE_TRANSPORT_FAILURE_TIME_INVALID")
        <= _time(started_text, "V31_CAPTURE_TRANSPORT_FAILURE_TIME_INVALID")
        <= _time(failed_text, "V31_CAPTURE_TRANSPORT_FAILURE_TIME_INVALID")
    ):
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_TRANSPORT_FAILURE_TIME_ORDER_INVALID"
        )
    document = {
        "schema_id": OUTCOME_TRANSPORT_FAILURE_SCHEMA_ID,
        "schema_version": OUTCOME_CAPTURE_SCHEMA_VERSION,
        "run_id": _text(run_id, "V31_CAPTURE_RUN_ID_INVALID"),
        "cycle_index": cycle_index,
        "monitor_plan_digest": _digest(
            monitor_plan_digest,
            "V31_CAPTURE_MONITOR_PLAN_DIGEST_INVALID",
        ),
        "monitor_attempt_digest": _digest(
            monitor_attempt_digest,
            "V31_CAPTURE_MONITOR_ATTEMPT_DIGEST_INVALID",
        ),
        "source_request_id": _text(
            source_request_id, "V31_CAPTURE_SOURCE_REQUEST_ID_INVALID"
        ),
        "request_method": "GET",
        "request_url": OKX_MARK_PRICE_URL,
        "requested_at": requested_text,
        "request_started_at": started_text,
        "failure_at": failed_text,
        "monotonic_elapsed_ms": elapsed,
        "failure_code": failure_code,
        "no_response_received": True,
        "raw_capture_available": False,
        "retry_allowed": False,
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, "transport_failure_digest")


def verify_public_outcome_transport_failure(
    receipt: Mapping[str, Any],
) -> str:
    if not isinstance(receipt, Mapping):
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_TRANSPORT_FAILURE_INVALID"
        )
    try:
        supplied = verify_self_digest(receipt, "transport_failure_digest")
        if (
            receipt.get("schema_id") != OUTCOME_TRANSPORT_FAILURE_SCHEMA_ID
            or receipt.get("schema_version") != OUTCOME_CAPTURE_SCHEMA_VERSION
            or receipt.get("request_method") != "GET"
            or receipt.get("request_url") != OKX_MARK_PRICE_URL
            or receipt.get("no_response_received") is not True
            or receipt.get("raw_capture_available") is not False
            or receipt.get("retry_allowed") is not False
            or receipt.get("authority_boundary") != _authority_boundary()
        ):
            raise V31OutcomeCaptureContractError(
                "V31_CAPTURE_TRANSPORT_FAILURE_INVALID"
            )
        rebuilt = build_public_outcome_transport_failure(
            run_id=receipt["run_id"],
            cycle_index=receipt["cycle_index"],
            monitor_plan_digest=receipt["monitor_plan_digest"],
            monitor_attempt_digest=receipt["monitor_attempt_digest"],
            source_request_id=receipt["source_request_id"],
            requested_at=receipt["requested_at"],
            request_started_at=receipt["request_started_at"],
            failure_at=receipt["failure_at"],
            monotonic_elapsed_ms=receipt["monotonic_elapsed_ms"],
            failure_code=receipt["failure_code"],
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31OutcomeCaptureContractError):
            raise
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_TRANSPORT_FAILURE_INVALID"
        ) from exc
    if (
        rebuilt != dict(receipt)
        or supplied != rebuilt["transport_failure_digest"]
    ):
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_TRANSPORT_FAILURE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _parse_receipt(
    *,
    capture: Mapping[str, Any],
    clock_policy_digest: str,
    observable_ref: str,
    parse_status: OutcomeCaptureParseStatus,
    error_code: str | None,
    value: str | None,
    provider_timestamp_raw: str | None,
    provider_as_of: str | None,
    provider_clock_delta_ms: str | None,
    clock_class: OutcomeClockClass,
    missingness: str,
    quality: str,
    coverage: str,
    conflict_state: str,
) -> dict[str, Any]:
    received = capture["response_received_at"]
    document = {
        "schema_id": OUTCOME_PARSE_RECEIPT_SCHEMA_ID,
        "schema_version": OUTCOME_CAPTURE_SCHEMA_VERSION,
        "parser_version": OUTCOME_PARSER_VERSION,
        "run_id": capture["run_id"],
        "cycle_index": capture["cycle_index"],
        "capture_digest": capture["capture_digest"],
        "clock_policy_digest": clock_policy_digest,
        "source_request_id": capture["source_request_id"],
        "observable_ref": observable_ref,
        "parse_status": parse_status.value,
        "error_code": error_code,
        "value": value,
        "provider_timestamp_raw": provider_timestamp_raw,
        "provider_as_of": provider_as_of,
        "evaluation_as_of": received,
        "available_at": received,
        "provider_clock_delta_ms": provider_clock_delta_ms,
        "clock_class": clock_class.value,
        "missingness": missingness,
        "quality": quality,
        "coverage": coverage,
        "conflict_state": conflict_state,
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, "parse_receipt_digest")


def _rejected(
    *,
    capture: Mapping[str, Any],
    policy_digest: str,
    observable_ref: str,
    error_code: str,
    provider_timestamp_raw: str | None = None,
    provider_as_of: str | None = None,
) -> dict[str, Any]:
    return _parse_receipt(
        capture=capture,
        clock_policy_digest=policy_digest,
        observable_ref=observable_ref,
        parse_status=OutcomeCaptureParseStatus.REJECTED,
        error_code=error_code,
        value=None,
        provider_timestamp_raw=provider_timestamp_raw,
        provider_as_of=provider_as_of,
        provider_clock_delta_ms=None,
        clock_class=OutcomeClockClass.UNAVAILABLE,
        missingness="UNKNOWN",
        quality="UNKNOWN",
        coverage="0",
        conflict_state="REJECTED",
    )


def _unknown(
    *,
    capture: Mapping[str, Any],
    policy_digest: str,
    observable_ref: str,
    error_code: str,
    conflict_state: str,
    provider_timestamp_raw: str | None = None,
    provider_as_of: str | None = None,
    provider_clock_delta_ms: str | None = None,
    clock_class: OutcomeClockClass = OutcomeClockClass.UNAVAILABLE,
) -> dict[str, Any]:
    return _parse_receipt(
        capture=capture,
        clock_policy_digest=policy_digest,
        observable_ref=observable_ref,
        parse_status=OutcomeCaptureParseStatus.ADMITTED_UNKNOWN,
        error_code=error_code,
        value=None,
        provider_timestamp_raw=provider_timestamp_raw,
        provider_as_of=provider_as_of,
        provider_clock_delta_ms=provider_clock_delta_ms,
        clock_class=clock_class,
        missingness="UNKNOWN",
        quality="UNKNOWN",
        coverage="0",
        conflict_state=conflict_state,
    )


def parse_public_outcome_capture(
    *,
    capture: Mapping[str, Any],
    raw_payload: bytes,
    clock_policy: Mapping[str, Any],
    observable_ref: str,
) -> dict[str, Any]:
    """Deterministically parse one already committed OKX mark-price capture."""

    verify_public_outcome_capture(capture, raw_payload=raw_payload)
    policy_digest = verify_outcome_clock_policy(clock_policy)
    observable = _text(observable_ref, "V31_CAPTURE_OBSERVABLE_REF_INVALID")

    requested = _time(
        capture["requested_at"], "V31_CAPTURE_REQUESTED_AT_INVALID"
    )
    started = _time(
        capture["request_started_at"], "V31_CAPTURE_REQUEST_STARTED_AT_INVALID"
    )
    received = _time(
        capture["response_received_at"],
        "V31_CAPTURE_RESPONSE_RECEIVED_AT_INVALID",
    )
    if not requested <= started <= received:
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="CAPTURE_LOCAL_TIME_ORDER_INVALID",
        )
    if capture["final_url"] != OKX_MARK_PRICE_URL:
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_FINAL_URL_INVALID",
        )
    if capture["status_code"] != 200:
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_STATUS_INVALID",
        )
    if "json" not in capture["content_type"].casefold():
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_CONTENT_TYPE_INVALID",
        )

    try:
        decoded = loads_json_strict(raw_payload)
    except (CanonicalContractError, ValueError):
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_JSON_INVALID",
        )
    data = decoded.get("data")
    if not isinstance(decoded.get("code"), str) or not isinstance(data, list):
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_SCHEMA_INVALID",
        )
    if decoded["code"] != "0":
        return _unknown(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PROVIDER_REPORTED_UNAVAILABLE",
            conflict_state="PROVIDER_UNAVAILABLE",
        )
    if not data:
        return _unknown(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PROVIDER_DATA_EMPTY",
            conflict_state="PROVIDER_DATA_EMPTY",
        )
    if len(data) != 1 or not isinstance(data[0], Mapping):
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_SCHEMA_INVALID",
        )
    row = data[0]
    if row.get("instId") != "BTC-USDT-SWAP" or row.get("instType") != "SWAP":
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_INSTRUMENT_MISMATCH",
        )
    mark_raw = row.get("markPx")
    timestamp_raw = row.get("ts")
    if (
        not isinstance(mark_raw, str)
        or not mark_raw
        or mark_raw != mark_raw.strip()
        or not isinstance(timestamp_raw, str)
        or not timestamp_raw
        or timestamp_raw != timestamp_raw.strip()
    ):
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_SCHEMA_INVALID",
        )
    try:
        mark = Decimal(mark_raw)
    except InvalidOperation:
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_VALUE_INVALID",
            provider_timestamp_raw=timestamp_raw,
        )
    if not mark.is_finite() or mark <= 0:
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_VALUE_INVALID",
            provider_timestamp_raw=timestamp_raw,
        )
    if not timestamp_raw.isdigit():
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_TIME_INVALID",
            provider_timestamp_raw=timestamp_raw,
        )
    try:
        provider_ms = int(timestamp_raw)
        provider_time = _EPOCH + timedelta(milliseconds=provider_ms)
    except (OverflowError, ValueError):
        return _rejected(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="PUBLIC_TIME_INVALID",
            provider_timestamp_raw=timestamp_raw,
        )
    provider_as_of = provider_time.isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    delta_ms = Decimal(provider_ms) - _milliseconds_since_epoch(received)
    delta_text = canonical_decimal(delta_ms)
    lead = Decimal(clock_policy["max_provider_clock_lead_ms"])
    age = Decimal(clock_policy["max_provider_age_ms"])
    if delta_ms > lead or delta_ms < -age:
        return _unknown(
            capture=capture,
            policy_digest=policy_digest,
            observable_ref=observable,
            error_code="CLOCK_BOUND_EXCEEDED",
            conflict_state="CLOCK_BOUND_EXCEEDED",
            provider_timestamp_raw=timestamp_raw,
            provider_as_of=provider_as_of,
            provider_clock_delta_ms=delta_text,
            clock_class=OutcomeClockClass.CLOCK_BOUND_EXCEEDED,
        )
    if delta_ms > 0:
        clock_class = OutcomeClockClass.PROVIDER_LEAD_WITHIN_BOUND
        quality = "MEDIUM"
    elif delta_ms < 0:
        clock_class = OutcomeClockClass.PROVIDER_LAG_WITHIN_BOUND
        quality = "HIGH"
    else:
        clock_class = OutcomeClockClass.EXACT
        quality = "HIGH"
    return _parse_receipt(
        capture=capture,
        clock_policy_digest=policy_digest,
        observable_ref=observable,
        parse_status=OutcomeCaptureParseStatus.ADMITTED_OBSERVED,
        error_code=None,
        value=canonical_decimal(mark),
        provider_timestamp_raw=timestamp_raw,
        provider_as_of=provider_as_of,
        provider_clock_delta_ms=delta_text,
        clock_class=clock_class,
        missingness="OBSERVED",
        quality=quality,
        coverage="1",
        conflict_state="NONE",
    )


def verify_public_outcome_parse_receipt(
    receipt: Mapping[str, Any],
    *,
    capture: Mapping[str, Any],
    raw_payload: bytes,
    clock_policy: Mapping[str, Any],
    observable_ref: str,
) -> str:
    """Verify a parse receipt by recomputing it from exact raw bytes."""

    if not isinstance(receipt, Mapping):
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_PARSE_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(receipt, "parse_receipt_digest")
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_PARSE_RECEIPT_DIGEST_INVALID"
        ) from exc
    try:
        rebuilt = parse_public_outcome_capture(
            capture=capture,
            raw_payload=raw_payload,
            clock_policy=clock_policy,
            observable_ref=observable_ref,
        )
    except (CanonicalContractError, TypeError, ValueError) as exc:
        if isinstance(exc, V31OutcomeCaptureContractError):
            raise
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_PARSE_RECEIPT_INVALID"
        ) from exc
    if rebuilt != dict(receipt) or supplied != rebuilt["parse_receipt_digest"]:
        raise V31OutcomeCaptureContractError(
            "V31_CAPTURE_PARSE_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "DEFAULT_MAX_PROVIDER_AGE_MS",
    "DEFAULT_MAX_PROVIDER_CLOCK_LEAD_MS",
    "MAX_RAW_CAPTURE_BYTES",
    "OKX_MARK_PRICE_URL",
    "OUTCOME_CAPTURE_SCHEMA_ID",
    "OUTCOME_CAPTURE_SCHEMA_VERSION",
    "OUTCOME_CLOCK_POLICY_SCHEMA_ID",
    "OUTCOME_PARSE_RECEIPT_SCHEMA_ID",
    "OUTCOME_TRANSPORT_FAILURE_SCHEMA_ID",
    "OUTCOME_PARSER_VERSION",
    "PUBLIC_OUTCOME_TRANSPORT_FAILURE_CODES",
    "OutcomeCaptureParseStatus",
    "OutcomeClockClass",
    "V31OutcomeCaptureContractError",
    "build_outcome_clock_policy",
    "build_public_outcome_capture",
    "build_public_outcome_transport_failure",
    "parse_public_outcome_capture",
    "verify_outcome_clock_policy",
    "verify_public_outcome_capture",
    "verify_public_outcome_parse_receipt",
    "verify_public_outcome_transport_failure",
]
