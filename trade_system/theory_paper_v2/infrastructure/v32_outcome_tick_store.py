"""Local write-once evidence store for the V3.2 shared outcome tick.

The store is deliberately incapable of making a network request or observing
an account, order, fill, position, or PnL.  It owns only the durable chronology
required by :mod:`trade_system.theory_paper_v2.domain.v32_outcome_tick`::

    schedule sets -> one reserved tick attempt -> raw/failure evidence
    -> normalization receipt -> observation tick -> batch intent
    -> ordered outcome receipts -> batch completion

Every artifact except the checkpoint is canonical and write-once.  The
checkpoint is replaced atomically under a process/thread lock and every
replacement is compare-and-swap guarded by its previous semantic digest.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Mapping, Sequence

from ..application.v32_outcome_tick_port import (
    CHECKPOINT_SCHEMA_ID,
    CHECKPOINT_SCHEMA_VERSION,
    COVERAGE_FAILURE_DIGEST_FIELD,
    COVERAGE_FAILURE_SCHEMA_ID,
    PARSE_RECEIPT_DIGEST_FIELD,
    PARSE_RECEIPT_SCHEMA_ID,
    RAW_CAPTURE_DIGEST_FIELD,
    RAW_CAPTURE_SCHEMA_ID,
    TRANSPORT_FAILURE_DIGEST_FIELD,
    TRANSPORT_FAILURE_SCHEMA_ID,
    V32OutcomeTickPersistenceError,
)
from ..application.v32_outcome_tick_composition import (
    V32OutcomeTickCompositionError,
    build_v32_outcome_observation_from_durable_prefix_v1,
    classify_v32_durable_public_mark_raw_v1,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ..v32_durable_json import (
    atomic_replace_json,
    confirm_existing_directory,
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_directory,
    write_once_json,
)
from ..domain.v32_outcome_tick import (
    BATCH_COMPLETION_DIGEST_FIELD,
    BATCH_INTENT_DIGEST_FIELD,
    OBSERVATION_TICK_DIGEST_FIELD,
    OUTCOME_RECEIPT_DIGEST_FIELD,
    SCHEDULE_SET_DIGEST_FIELD,
    TICK_ATTEMPT_DIGEST_FIELD,
    RESPONSE_BACKED_COVERAGE_FAILURE_CODES,
    TRANSPORT_COVERAGE_FAILURE_CODES,
    verify_v32_outcome_observation_tick,
    verify_v32_outcome_resolution_batch,
    verify_v32_outcome_resolution_batch_intent,
    verify_v32_outcome_schedule_set,
    verify_v32_outcome_tick_attempt,
    verify_v32_public_market_outcome_receipt,
)
from ..domain.v32_outcome_window_expiry import (
    EXPIRY_ROW_DIGEST_FIELD,
    EXPIRY_TERMINAL_DIGEST_FIELD,
    verify_v32_outcome_window_expiry_terminal,
)
from ..domain.v32_runtime_support_contracts import (
    MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS,
)


FAILURE_SCHEMA_ID = "theory_paper_v32_outcome_tick_failure_v1"
FAILURE_DIGEST_FIELD = "outcome_tick_failure_digest"
BATCH_SCHEDULE_PREFIX_SCHEMA_ID = (
    "theory_paper_v32_outcome_batch_schedule_set_prefix_v1"
)

TOTAL_CYCLES = 16
TOTAL_SCHEDULES = 48
MAX_TICKS = 48
MAX_RAW_CAPTURE_BYTES = 1_048_576
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
OKX_PUBLIC_MARK_PRICE_URL = (
    "https://openapi.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
CHECKPOINT_SCHEMA_ID_V2 = "theory_paper_v32_outcome_tick_checkpoint_v2"
CHECKPOINT_SCHEMA_VERSION_V2 = "2.0.0"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}

_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "revision",
        "status",
        "total_cycles",
        "total_schedules",
        "schedule_set_bindings",
        "attempt_bindings",
        "evidence_bindings",
        "normalization_bindings",
        "observation_tick_bindings",
        "batch_intent_bindings",
        "outcome_receipt_bindings",
        "batch_completion_bindings",
        "failure_binding",
        "created_at",
        "updated_at",
        "max_network_requests_per_tick",
        "retry_allowed",
        "raw_before_parse",
        "source_scope",
        "external_execution_authority",
        "executable",
        "checkpoint_digest",
    }
)
_EXPIRY_CHECKPOINT_FIELDS = frozenset(
    {"expiry_terminal_bindings"}
)
_CHECKPOINT_FIELDS_V2 = _CHECKPOINT_FIELDS | _EXPIRY_CHECKPOINT_FIELDS


class V32OutcomeTickStoreError(V32OutcomeTickPersistenceError):
    """A durable V3.2 outcome chronology invariant failed closed."""


def build_v32_outcome_tick_checkpoint(
    *, run_id: str, created_at: str
) -> dict[str, Any]:
    """Build the deterministic zero-progress checkpoint before any write.

    The caller can bind this digest into the Supervisor genesis before the
    outcome store is activated.  This helper grants no authority and performs
    no filesystem or network operation.
    """

    run = _text(run_id, "V32_TICK_STORE_RUN_ID_INVALID")
    created = _time(created_at, "V32_TICK_STORE_TIME_INVALID")
    return self_digest(
        {
            "schema_id": CHECKPOINT_SCHEMA_ID,
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "run_id": run,
            "revision": 0,
            "status": "ACTIVE",
            "total_cycles": TOTAL_CYCLES,
            "total_schedules": TOTAL_SCHEDULES,
            "schedule_set_bindings": [],
            "attempt_bindings": [],
            "evidence_bindings": [],
            "normalization_bindings": [],
            "observation_tick_bindings": [],
            "batch_intent_bindings": [],
            "outcome_receipt_bindings": [],
            "batch_completion_bindings": [],
            "failure_binding": None,
            "created_at": created,
            "updated_at": created,
            "max_network_requests_per_tick": 1,
            "retry_allowed": False,
            "raw_before_parse": True,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        "checkpoint_digest",
    )


def _time(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32OutcomeTickStoreError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32OutcomeTickStoreError(code) from exc
    if parsed.tzinfo is None:
        raise V32OutcomeTickStoreError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        raise V32OutcomeTickStoreError(code)
    return value


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32OutcomeTickStoreError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32OutcomeTickStoreError(code)
    return value


def _positive_int(value: Any, code: str, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise V32OutcomeTickStoreError(code)
    return value


def _schedule_set_prefix_digest(
    schedule_set_bindings: Sequence[Mapping[str, Any]],
) -> str:
    count = _positive_int(
        len(schedule_set_bindings),
        "V32_TICK_STORE_BATCH_SCHEDULE_PREFIX_INVALID",
        maximum=TOTAL_CYCLES,
    )
    if any(not isinstance(binding, Mapping) for binding in schedule_set_bindings):
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_BATCH_SCHEDULE_PREFIX_INVALID"
        )
    return canonical_digest(
        {
            "schema_id": BATCH_SCHEDULE_PREFIX_SCHEMA_ID,
            "schedule_set_prefix_count": count,
            "schedule_set_bindings": [
                dict(binding) for binding in schedule_set_bindings
            ],
        }
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    atomic_replace_json(
        path,
        document,
        short_write_error="V32_OUTCOME_CHECKPOINT_SHORT_WRITE",
    )


def _generic_document_binding(
    *, relative_ref: str, document: Mapping[str, Any], digest_field: str
) -> dict[str, str]:
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32OutcomeTickStoreError("V32_TICK_STORE_DOCUMENT_DIGEST_INVALID") from exc
    return {
        "relative_ref": relative_ref,
        "schema_id": str(document.get("schema_id")),
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": hashlib.sha256(
            canonical_bytes(dict(document)) + b"\n"
        ).hexdigest(),
    }


def build_v32_public_raw_capture(
    *,
    attempt: Mapping[str, Any],
    recorded_at: str,
    raw_payload_ref: str,
    raw_payload_sha256: str,
    http_status: int = 200,
    response_received_at: str | None = None,
    capture_completed_at: str | None = None,
    final_url: str = OKX_PUBLIC_MARK_PRICE_URL,
) -> dict[str, Any]:
    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    if (
        isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or not 100 <= http_status <= 599
    ):
        raise V32OutcomeTickStoreError("V32_RAW_CAPTURE_HTTP_STATUS_INVALID")
    return self_digest(
        {
            "schema_id": RAW_CAPTURE_SCHEMA_ID,
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "run_id": attempt["run_id"],
            "tick_index": attempt["tick_index"],
            "tick_id": attempt["tick_id"],
            "attempt_digest": attempt_digest,
            "source_request_id": attempt["source_request_id"],
            "recorded_at": _time(recorded_at, "V32_RAW_CAPTURE_TIME_INVALID"),
            "raw_payload_ref": _text(
                raw_payload_ref, "V32_RAW_CAPTURE_REFERENCE_INVALID"
            ),
            "raw_payload_sha256": _digest(
                raw_payload_sha256, "V32_RAW_CAPTURE_SHA_INVALID"
            ),
            "http_status": http_status,
            "response_received_at": _time(
                response_received_at or recorded_at,
                "V32_RAW_CAPTURE_RESPONSE_TIME_INVALID",
            ),
            "capture_completed_at": _time(
                capture_completed_at or recorded_at,
                "V32_RAW_CAPTURE_COMPLETION_TIME_INVALID",
            ),
            "final_url": _text(final_url, "V32_RAW_CAPTURE_FINAL_URL_INVALID"),
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        RAW_CAPTURE_DIGEST_FIELD,
    )


def verify_v32_public_raw_capture(
    document: Mapping[str, Any], *, attempt: Mapping[str, Any], raw_payload: bytes
) -> str:
    fields = {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "tick_id",
        "attempt_digest",
        "source_request_id",
        "recorded_at",
        "raw_payload_ref",
        "raw_payload_sha256",
        "http_status",
        "response_received_at",
        "capture_completed_at",
        "final_url",
        "source_scope",
        "external_execution_authority",
        "executable",
        RAW_CAPTURE_DIGEST_FIELD,
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise V32OutcomeTickStoreError("V32_RAW_CAPTURE_SCHEMA_INVALID")
    if not isinstance(raw_payload, bytes):
        raise V32OutcomeTickStoreError("V32_RAW_CAPTURE_PAYLOAD_INVALID")
    try:
        supplied = verify_self_digest(document, RAW_CAPTURE_DIGEST_FIELD)
        rebuilt = build_v32_public_raw_capture(
            attempt=attempt,
            recorded_at=document["recorded_at"],
            raw_payload_ref=document["raw_payload_ref"],
            raw_payload_sha256=_sha256(raw_payload),
            http_status=document["http_status"],
            response_received_at=document["response_received_at"],
            capture_completed_at=document["capture_completed_at"],
            final_url=document["final_url"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickStoreError):
            raise
        raise V32OutcomeTickStoreError("V32_RAW_CAPTURE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[RAW_CAPTURE_DIGEST_FIELD]:
        raise V32OutcomeTickStoreError("V32_RAW_CAPTURE_RECONSTRUCTION_MISMATCH")
    return supplied


def build_v32_public_transport_failure(
    *, attempt: Mapping[str, Any], failure_code: str, failure_at: str
) -> dict[str, Any]:
    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    if failure_code not in TRANSPORT_COVERAGE_FAILURE_CODES:
        raise V32OutcomeTickStoreError("V32_TRANSPORT_FAILURE_CODE_INVALID")
    return self_digest(
        {
            "schema_id": TRANSPORT_FAILURE_SCHEMA_ID,
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "run_id": attempt["run_id"],
            "tick_index": attempt["tick_index"],
            "tick_id": attempt["tick_id"],
            "attempt_digest": attempt_digest,
            "source_request_id": attempt["source_request_id"],
            "failure_code": failure_code,
            "failure_at": _time(failure_at, "V32_TRANSPORT_FAILURE_TIME_INVALID"),
            "recorded_at": _time(failure_at, "V32_TRANSPORT_FAILURE_TIME_INVALID"),
            "retry_allowed": False,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        TRANSPORT_FAILURE_DIGEST_FIELD,
    )


def verify_v32_public_transport_failure(
    document: Mapping[str, Any], *, attempt: Mapping[str, Any]
) -> str:
    fields = {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "tick_id",
        "attempt_digest",
        "source_request_id",
        "failure_code",
        "failure_at",
        "recorded_at",
        "retry_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        TRANSPORT_FAILURE_DIGEST_FIELD,
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise V32OutcomeTickStoreError("V32_TRANSPORT_FAILURE_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, TRANSPORT_FAILURE_DIGEST_FIELD)
        rebuilt = build_v32_public_transport_failure(
            attempt=attempt,
            failure_code=document["failure_code"],
            failure_at=document["failure_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickStoreError):
            raise
        raise V32OutcomeTickStoreError("V32_TRANSPORT_FAILURE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[TRANSPORT_FAILURE_DIGEST_FIELD]:
        raise V32OutcomeTickStoreError(
            "V32_TRANSPORT_FAILURE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_v32_public_coverage_failure(
    *,
    attempt: Mapping[str, Any],
    raw_capture: Mapping[str, Any],
    failure_code: str,
    recorded_at: str,
) -> dict[str, Any]:
    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    if failure_code not in RESPONSE_BACKED_COVERAGE_FAILURE_CODES:
        raise V32OutcomeTickStoreError("V32_COVERAGE_FAILURE_CODE_INVALID")
    raw_digest = verify_self_digest(raw_capture, RAW_CAPTURE_DIGEST_FIELD)
    http_status = raw_capture.get("http_status")
    if failure_code == "PUBLIC_PROVIDER_UNAVAILABLE":
        if http_status != 429 and not (
            isinstance(http_status, int)
            and not isinstance(http_status, bool)
            and 500 <= http_status <= 599
        ):
            raise V32OutcomeTickStoreError(
                "V32_COVERAGE_FAILURE_HTTP_STATUS_MISMATCH"
            )
    elif http_status != 200:
        raise V32OutcomeTickStoreError(
            "V32_COVERAGE_FAILURE_HTTP_STATUS_MISMATCH"
        )
    return self_digest(
        {
            "schema_id": COVERAGE_FAILURE_SCHEMA_ID,
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "run_id": attempt["run_id"],
            "tick_index": attempt["tick_index"],
            "tick_id": attempt["tick_id"],
            "attempt_digest": attempt_digest,
            "source_request_id": attempt["source_request_id"],
            "failure_code": failure_code,
            "recorded_at": _time(recorded_at, "V32_COVERAGE_FAILURE_TIME_INVALID"),
            "raw_capture_digest": raw_digest,
            "raw_payload_sha256": _digest(
                raw_capture.get("raw_payload_sha256"),
                "V32_COVERAGE_FAILURE_RAW_SHA_INVALID",
            ),
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        COVERAGE_FAILURE_DIGEST_FIELD,
    )


def verify_v32_public_coverage_failure(
    document: Mapping[str, Any],
    *,
    attempt: Mapping[str, Any],
    raw_capture: Mapping[str, Any],
) -> str:
    fields = {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "tick_id",
        "attempt_digest",
        "source_request_id",
        "failure_code",
        "recorded_at",
        "raw_capture_digest",
        "raw_payload_sha256",
        "source_scope",
        "external_execution_authority",
        "executable",
        COVERAGE_FAILURE_DIGEST_FIELD,
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise V32OutcomeTickStoreError("V32_COVERAGE_FAILURE_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, COVERAGE_FAILURE_DIGEST_FIELD)
        rebuilt = build_v32_public_coverage_failure(
            attempt=attempt,
            raw_capture=raw_capture,
            failure_code=document["failure_code"],
            recorded_at=document["recorded_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickStoreError):
            raise
        raise V32OutcomeTickStoreError("V32_COVERAGE_FAILURE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[COVERAGE_FAILURE_DIGEST_FIELD]:
        raise V32OutcomeTickStoreError(
            "V32_COVERAGE_FAILURE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_v32_public_mark_parse_receipt(
    *,
    attempt: Mapping[str, Any],
    raw_capture: Mapping[str, Any],
    value: str,
    provider_as_of: str,
    available_at: str,
    recorded_at: str,
) -> dict[str, Any]:
    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    raw_digest = verify_self_digest(raw_capture, RAW_CAPTURE_DIGEST_FIELD)
    provider_moment = _moment(
        provider_as_of, "V32_PARSE_RECEIPT_PROVIDER_TIME_INVALID"
    )
    available_moment = _moment(
        available_at, "V32_PARSE_RECEIPT_AVAILABLE_TIME_INVALID"
    )
    ahead = provider_moment - available_moment
    ahead_microseconds = max(0, ahead // timedelta(microseconds=1))
    ahead_milliseconds = (ahead_microseconds + 999) // 1000
    if ahead_milliseconds > MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS:
        raise V32OutcomeTickStoreError(
            "V32_PARSE_RECEIPT_PROVIDER_CLOCK_AHEAD_BOUND_EXCEEDED"
        )
    quality = "MEDIUM" if ahead_milliseconds > 0 else "HIGH"
    clock_status = (
        "WITHIN_BOUND_PROVIDER_AHEAD"
        if ahead_milliseconds > 0
        else "PROVIDER_NOT_AHEAD"
    )
    return self_digest(
        {
            "schema_id": PARSE_RECEIPT_SCHEMA_ID,
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "run_id": attempt["run_id"],
            "tick_index": attempt["tick_index"],
            "tick_id": attempt["tick_id"],
            "attempt_digest": attempt_digest,
            "source_request_id": attempt["source_request_id"],
            "raw_capture_digest": raw_digest,
            "raw_payload_sha256": _digest(
                raw_capture.get("raw_payload_sha256"),
                "V32_PARSE_RECEIPT_RAW_SHA_INVALID",
            ),
            "recorded_at": _time(recorded_at, "V32_PARSE_RECEIPT_TIME_INVALID"),
            "value": _text(value, "V32_PARSE_RECEIPT_VALUE_INVALID"),
            "provider_as_of": _time(
                provider_as_of, "V32_PARSE_RECEIPT_PROVIDER_TIME_INVALID"
            ),
            "available_at": _time(
                available_at, "V32_PARSE_RECEIPT_AVAILABLE_TIME_INVALID"
            ),
            "provider_clock_ahead_milliseconds": ahead_milliseconds,
            "clock_uncertainty_status": clock_status,
            "quality": quality,
            "missingness": "OBSERVED",
            "conflict_state": "NONE",
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        PARSE_RECEIPT_DIGEST_FIELD,
    )


def verify_v32_public_mark_parse_receipt(
    document: Mapping[str, Any],
    *,
    attempt: Mapping[str, Any],
    raw_capture: Mapping[str, Any],
) -> str:
    fields = {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "tick_id",
        "attempt_digest",
        "source_request_id",
        "raw_capture_digest",
        "raw_payload_sha256",
        "recorded_at",
        "value",
        "provider_as_of",
        "available_at",
        "provider_clock_ahead_milliseconds",
        "clock_uncertainty_status",
        "quality",
        "missingness",
        "conflict_state",
        "source_scope",
        "external_execution_authority",
        "executable",
        PARSE_RECEIPT_DIGEST_FIELD,
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise V32OutcomeTickStoreError("V32_PARSE_RECEIPT_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, PARSE_RECEIPT_DIGEST_FIELD)
        rebuilt = build_v32_public_mark_parse_receipt(
            attempt=attempt,
            raw_capture=raw_capture,
            value=document["value"],
            provider_as_of=document["provider_as_of"],
            available_at=document["available_at"],
            recorded_at=document["recorded_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickStoreError):
            raise
        raise V32OutcomeTickStoreError("V32_PARSE_RECEIPT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[PARSE_RECEIPT_DIGEST_FIELD]:
        raise V32OutcomeTickStoreError("V32_PARSE_RECEIPT_RECONSTRUCTION_MISMATCH")
    if _moment(document["available_at"], "V32_PARSE_RECEIPT_TIME_INVALID") > _moment(
        document["recorded_at"], "V32_PARSE_RECEIPT_TIME_INVALID"
    ):
        raise V32OutcomeTickStoreError("V32_PARSE_RECEIPT_TIME_ORDER_INVALID")
    return supplied


def _verify_v32_normalization_semantics(
    document: Mapping[str, Any],
    *,
    normalization_kind: str,
    attempt: Mapping[str, Any],
    evidence: Mapping[str, Any],
    raw_payload: bytes | None,
) -> None:
    """Recompute normalization from durable evidence and require exact equality."""

    evidence_schema = evidence.get("schema_id")
    if normalization_kind == "TRANSPORT_FAILURE":
        if evidence_schema != TRANSPORT_FAILURE_SCHEMA_ID or raw_payload is not None:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_TRANSPORT_NORMALIZATION_EVIDENCE_INVALID"
            )
        verify_v32_public_transport_failure(document, attempt=attempt)
        if dict(document) != dict(evidence):
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_TRANSPORT_NORMALIZATION_MISMATCH"
            )
        return
    if evidence_schema != RAW_CAPTURE_SCHEMA_ID or not isinstance(
        raw_payload, bytes
    ):
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_RESPONSE_NORMALIZATION_EVIDENCE_INVALID"
        )
    if normalization_kind == "OBSERVED_PARSE":
        verify_v32_public_mark_parse_receipt(
            document, attempt=attempt, raw_capture=evidence
        )
    elif normalization_kind == "COVERAGE_FAILURE":
        verify_v32_public_coverage_failure(
            document, attempt=attempt, raw_capture=evidence
        )
    else:
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_NORMALIZATION_KIND_INVALID"
        )
    try:
        expected_kind, normalized = classify_v32_durable_public_mark_raw_v1(
            attempt=attempt,
            raw_capture=evidence,
            raw_payload=raw_payload,
        )
    except V32OutcomeTickCompositionError as exc:
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_DURABLE_RAW_NORMALIZATION_INVALID:"
            f"{exc.failure_code}"
        ) from exc
    if expected_kind != normalization_kind:
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_NORMALIZATION_KIND_MISMATCH"
        )
    if expected_kind == "OBSERVED_PARSE":
        expected = build_v32_public_mark_parse_receipt(
            attempt=attempt,
            raw_capture=evidence,
            value=normalized["value"],
            provider_as_of=normalized["provider_as_of"],
            available_at=normalized["available_at"],
            recorded_at=normalized["recorded_at"],
        )
    else:
        expected = build_v32_public_coverage_failure(
            attempt=attempt,
            raw_capture=evidence,
            failure_code=normalized["failure_code"],
            recorded_at=normalized["recorded_at"],
        )
    if dict(document) != expected:
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_NORMALIZATION_SEMANTIC_MISMATCH"
        )


def _verify_v32_observation_prefix_semantics(
    observation_tick: Mapping[str, Any],
    *,
    attempt: Mapping[str, Any],
    evidence: Mapping[str, Any],
    evidence_binding: Mapping[str, Any],
    normalization: Mapping[str, Any],
    normalization_binding: Mapping[str, Any],
) -> str:
    """Require the observation to be the exact projection of its prefix."""

    digest = verify_v32_outcome_observation_tick(
        observation_tick, attempt=attempt
    )
    try:
        expected = build_v32_outcome_observation_from_durable_prefix_v1(
            attempt=attempt,
            evidence_document=evidence,
            evidence_binding=evidence_binding,
            normalization_document=normalization,
            normalization_binding=normalization_binding,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_OBSERVATION_PREFIX_INVALID"
        ) from exc
    if dict(observation_tick) != expected:
        raise V32OutcomeTickStoreError(
            "V32_TICK_STORE_OBSERVATION_PREFIX_MISMATCH"
        )
    return digest


class LocalV32OutcomeTickStore:
    """Durable local owner for one V3.2 run's outcome-clock artifacts."""

    @staticmethod
    def build_outcome_tick_checkpoint(**kwargs: Any) -> Mapping[str, Any]:
        return build_v32_outcome_tick_checkpoint(**kwargs)

    @staticmethod
    def build_public_coverage_failure(**kwargs: Any) -> Mapping[str, Any]:
        return build_v32_public_coverage_failure(**kwargs)

    @staticmethod
    def build_public_mark_parse_receipt(**kwargs: Any) -> Mapping[str, Any]:
        return build_v32_public_mark_parse_receipt(**kwargs)

    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root)
        if supplied.exists() and supplied.is_symlink():
            raise V32OutcomeTickStoreError("V32_TICK_STORE_ROOT_SYMLINK_FORBIDDEN")
        self.run_root = supplied.absolute()
        ensure_directory_tree(self.run_root)
        if self.run_root.is_symlink():
            raise V32OutcomeTickStoreError("V32_TICK_STORE_ROOT_SYMLINK_FORBIDDEN")
        self.checkpoint_path = self._safe_path("outcome-v32/checkpoint.json")

    @contextmanager
    def _lock(self):
        path = self._safe_path(".locks/v32-outcome-tick-store.lock")
        ensure_directory_tree(path.parent)
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    @contextmanager
    def resolution_guard(self, *, run_id: str):
        _text(run_id, "V32_TICK_STORE_RUN_ID_INVALID")
        path = self._safe_path(".locks/v32-outcome-composition.lock")
        ensure_directory_tree(path.parent)
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    def _safe_path(self, relative_ref: str) -> Path:
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_PATH_INVALID")
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_PATH_INVALID")
        candidate = self.run_root.joinpath(*lexical.parts)
        current = self.run_root
        try:
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_SYMLINK_FORBIDDEN"
                    )
            candidate.resolve(strict=False).relative_to(
                self.run_root.resolve(strict=True)
            )
        except V32OutcomeTickStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_PATH_INVALID") from exc
        return candidate

    @staticmethod
    def _tick_root(tick_index: int) -> str:
        return f"outcome-v32/ticks/{_positive_int(tick_index, 'V32_TICK_STORE_TICK_INVALID', maximum=MAX_TICKS):04d}"

    @staticmethod
    def _expiry_ref(terminal_digest: str) -> str:
        digest = _digest(
            terminal_digest, "V32_EXPIRY_STORE_TERMINAL_DIGEST_INVALID"
        )
        return f"outcome-v32/expiry/{digest}.json"

    def initialize_checkpoint(
        self, *, run_id: str, created_at: str
    ) -> Mapping[str, Any]:
        run = _text(run_id, "V32_TICK_STORE_RUN_ID_INVALID")
        checkpoint = build_v32_outcome_tick_checkpoint(
            run_id=run, created_at=created_at
        )
        with self._lock():
            if self.checkpoint_path.exists():
                current = self.load_checkpoint(run_id=run, _already_locked=True)
                if dict(current) != checkpoint:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_INITIALIZATION_CONFLICT"
                    )
                confirm_existing_json(self.checkpoint_path, current)
                return current
            self._validate_checkpoint(checkpoint, run_id=run)
            write_once_json(self.checkpoint_path, checkpoint)
            return checkpoint

    def load_checkpoint(
        self, *, run_id: str, _already_locked: bool = False
    ) -> Mapping[str, Any]:
        if not _already_locked:
            with self._lock():
                return self.load_checkpoint(run_id=run_id, _already_locked=True)
        checkpoint_path = self._safe_path("outcome-v32/checkpoint.json")
        if not checkpoint_path.is_file() or checkpoint_path.is_symlink():
            raise V32OutcomeTickStoreError("V32_TICK_STORE_CHECKPOINT_MISSING")
        try:
            checkpoint = load_json_strict(checkpoint_path)
        except ValueError as exc:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_CHECKPOINT_INVALID") from exc
        self._validate_checkpoint(checkpoint, run_id=run_id)
        try:
            confirm_existing_json(checkpoint_path, checkpoint)
        except (OSError, TypeError, ValueError) as exc:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_CHECKPOINT_INVALID"
            ) from exc
        return checkpoint

    def _validate_checkpoint(self, checkpoint: Mapping[str, Any], *, run_id: str) -> None:
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except (TypeError, ValueError) as exc:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        is_v1 = (
            checkpoint.get("schema_id") == CHECKPOINT_SCHEMA_ID
            and checkpoint.get("schema_version") == CHECKPOINT_SCHEMA_VERSION
            and set(checkpoint) == _CHECKPOINT_FIELDS
        )
        is_v2 = (
            checkpoint.get("schema_id") == CHECKPOINT_SCHEMA_ID_V2
            and checkpoint.get("schema_version") == CHECKPOINT_SCHEMA_VERSION_V2
            and set(checkpoint) == _CHECKPOINT_FIELDS_V2
        )
        list_fields = (
            "schedule_set_bindings",
            "attempt_bindings",
            "evidence_bindings",
            "normalization_bindings",
            "observation_tick_bindings",
            "batch_intent_bindings",
            "outcome_receipt_bindings",
            "batch_completion_bindings",
            *(("expiry_terminal_bindings",) if is_v2 else ()),
        )
        if (
            not (is_v1 or is_v2)
            or checkpoint.get("run_id") != run_id
            or checkpoint.get("status") not in {"ACTIVE", "TERMINAL", "FAILED_CLOSED"}
            or checkpoint.get("total_cycles") != TOTAL_CYCLES
            or checkpoint.get("total_schedules") != TOTAL_SCHEDULES
            or isinstance(checkpoint.get("revision"), bool)
            or not isinstance(checkpoint.get("revision"), int)
            or checkpoint.get("revision") < 0
            or any(not isinstance(checkpoint.get(field), list) for field in list_fields)
            or checkpoint.get("max_network_requests_per_tick") != 1
            or checkpoint.get("retry_allowed") is not False
            or checkpoint.get("raw_before_parse") is not True
            or checkpoint.get("source_scope") != SOURCE_SCOPE
            or checkpoint.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or checkpoint.get("executable") is not False
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_CHECKPOINT_INVALID")
        created = _moment(checkpoint["created_at"], "V32_TICK_STORE_TIME_INVALID")
        updated = _moment(checkpoint["updated_at"], "V32_TICK_STORE_TIME_INVALID")
        if updated < created:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_TIME_ROLLBACK")
        schedules = checkpoint["schedule_set_bindings"]
        attempts = checkpoint["attempt_bindings"]
        evidence = checkpoint["evidence_bindings"]
        normalization = checkpoint["normalization_bindings"]
        observations = checkpoint["observation_tick_bindings"]
        batches = checkpoint["batch_intent_bindings"]
        completions = checkpoint["batch_completion_bindings"]
        if (
            len(schedules) > TOTAL_CYCLES
            or len(attempts) > MAX_TICKS
            or not len(completions)
            <= len(batches)
            <= len(observations)
            <= len(normalization)
            <= len(evidence)
            <= len(attempts)
            or any(
                left - right > 1
                for left, right in (
                    (len(attempts), len(evidence)),
                    (len(evidence), len(normalization)),
                    (len(normalization), len(observations)),
                    (len(observations), len(batches)),
                    (len(batches), len(completions)),
                )
            )
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_PREFIX_INVALID")
        schedule_documents = [
            self._verify_schedule_binding(binding, expected_cycle=index)
            for index, binding in enumerate(schedules, start=1)
        ]
        if sum(len(item["schedules"]) for item in schedule_documents) != len(
            schedules
        ) * 3:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_SCHEDULE_COUNT_INVALID")
        attempt_documents = [
            self._verify_attempt_binding(binding, expected_tick=index)
            for index, binding in enumerate(attempts, start=1)
        ]
        evidence_documents: list[tuple[Mapping[str, Any], bytes | None]] = []
        for index, binding in enumerate(evidence, start=1):
            evidence_documents.append(
                self._verify_evidence_binding(
                    binding, attempt=attempt_documents[index - 1], expected_tick=index
                )
            )
        normalization_documents: list[Mapping[str, Any]] = []
        for index, binding in enumerate(normalization, start=1):
            normalization_documents.append(
                self._verify_normalization_binding(
                    binding,
                    attempt=attempt_documents[index - 1],
                    evidence=evidence_documents[index - 1][0],
                    raw_payload=evidence_documents[index - 1][1],
                    expected_tick=index,
                )
            )
        observation_documents: list[Mapping[str, Any]] = []
        for index, binding in enumerate(observations, start=1):
            observation_documents.append(
                self._verify_observation_binding(
                    binding,
                    attempt=attempt_documents[index - 1],
                    evidence=evidence_documents[index - 1][0],
                    evidence_binding=evidence[index - 1],
                    normalization=normalization_documents[index - 1],
                    normalization_binding=normalization[index - 1],
                    expected_tick=index,
                )
            )
        receipt_documents = self._load_receipt_documents(
            checkpoint["outcome_receipt_bindings"]
        )
        expiry_terminals = self._load_expiry_terminals(
            checkpoint=checkpoint,
            schedule_sets=schedule_documents,
        )
        all_expiry_receipts = [
            row for terminal in expiry_terminals for row in terminal["rows"]
        ]
        batch_documents: list[Mapping[str, Any]] = []
        for index, binding in enumerate(batches, start=1):
            prior_receipts = [
                receipt
                for receipt in receipt_documents
                if int(receipt["_binding_tick_index"]) < index
            ]
            clean_prior = [
                {key: value for key, value in receipt.items() if key != "_binding_tick_index"}
                for receipt in prior_receipts
            ]
            batch_preview = self._read_generic_binding(binding)
            clean_prior.extend(
                receipt
                for receipt in all_expiry_receipts
                if _moment(
                    receipt["resolved_at"], "V32_TICK_STORE_TIME_INVALID"
                )
                <= _moment(
                    batch_preview["created_at"], "V32_TICK_STORE_TIME_INVALID"
                )
            )
            clean_prior.sort(key=lambda receipt: str(receipt["schedule_id"]))
            batch_documents.append(
                self._verify_batch_binding(
                    binding,
                    attempt=attempt_documents[index - 1],
                    observation=observation_documents[index - 1],
                    schedule_set_bindings=schedules,
                    schedule_sets=schedule_documents,
                    prior_receipts=clean_prior,
                    prior_batches=batch_documents,
                    expected_tick=index,
                )
            )
        seen_schedules: set[str] = set()
        receipts_by_tick: dict[int, list[Mapping[str, Any]]] = {}
        for receipt_with_tick in receipt_documents:
            tick = int(receipt_with_tick["_binding_tick_index"])
            receipt = {
                key: value
                for key, value in receipt_with_tick.items()
                if key != "_binding_tick_index"
            }
            if tick > len(batch_documents):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_PREFIX_INVALID")
            schedule_id = str(receipt["schedule_id"])
            if schedule_id in seen_schedules:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_DUPLICATE_RECEIPT")
            seen_schedules.add(schedule_id)
            self._verify_receipt_document(
                receipt,
                attempt=attempt_documents[tick - 1],
                observation=observation_documents[tick - 1],
                batch=batch_documents[tick - 1],
                schedule_sets=self._schedule_sets_for_batch_binding(
                    binding=batches[tick - 1],
                    schedule_set_bindings=schedules,
                    schedule_sets=schedule_documents,
                ),
            )
            receipts_by_tick.setdefault(tick, []).append(receipt)
        for tick, rows in receipts_by_tick.items():
            expected = list(batch_documents[tick - 1]["due_schedule_ids"])
            actual = [str(row["schedule_id"]) for row in rows]
            if actual != expected[: len(actual)]:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_ORDER_INVALID")
        for index, binding in enumerate(completions, start=1):
            rows = receipts_by_tick.get(index, [])
            self._verify_completion_binding(
                binding,
                batch=batch_documents[index - 1],
                receipts=rows,
                expected_tick=index,
            )
        for tick in range(1, len(completions) + 1):
            if len(receipts_by_tick.get(tick, [])) != len(
                batch_documents[tick - 1]["due_schedule_ids"]
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_COMPLETION_PREMATURE")
        expiry_schedule_ids: set[str] = set()
        for terminal in expiry_terminals:
            for receipt in terminal["rows"]:
                schedule_id = str(receipt["schedule_id"])
                if schedule_id in seen_schedules or schedule_id in expiry_schedule_ids:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_DUPLICATE_TERMINAL_RECEIPT"
                    )
                expiry_schedule_ids.add(schedule_id)
        failure_binding = checkpoint.get("failure_binding")
        if checkpoint["status"] == "FAILED_CLOSED":
            if not isinstance(failure_binding, Mapping):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_FAILURE_STATE_INVALID")
            self._verify_failure_binding(failure_binding, run_id=run_id)
        elif failure_binding is not None:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_FAILURE_STATE_INVALID")
        if checkpoint["status"] == "TERMINAL":
            if not (
                len(schedules) == TOTAL_CYCLES
                and len(seen_schedules | expiry_schedule_ids) == TOTAL_SCHEDULES
                and len(completions) == len(attempts)
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_TERMINAL_INVALID")

    def _replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        candidate: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        current = self.load_checkpoint(run_id=run_id, _already_locked=True)
        if current["checkpoint_digest"] != expected_checkpoint_digest:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_CAS_CONFLICT")
        if current["status"] in {"TERMINAL", "FAILED_CLOSED"}:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_TERMINAL_IMMUTABLE")
        payload = dict(candidate)
        payload.pop("checkpoint_digest", None)
        if payload.get("revision") != int(current["revision"]) + 1:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_REVISION_INVALID")
        current_is_v1 = current.get("schema_id") == CHECKPOINT_SCHEMA_ID
        payload_is_v2 = payload.get("schema_id") == CHECKPOINT_SCHEMA_ID_V2
        schema_transition_valid = (
            payload.get("schema_id") == current.get("schema_id")
            and payload.get("schema_version") == current.get("schema_version")
        ) or (
            current_is_v1
            and payload_is_v2
            and payload.get("schema_version") == CHECKPOINT_SCHEMA_VERSION_V2
        )
        if not schema_transition_valid:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_SCHEMA_TRANSITION_INVALID")
        immutable = {
            "run_id",
            "total_cycles",
            "total_schedules",
            "created_at",
            "max_network_requests_per_tick",
            "retry_allowed",
            "raw_before_parse",
            "source_scope",
            "external_execution_authority",
            "executable",
        }
        if any(payload.get(field) != current.get(field) for field in immutable):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_IMMUTABLE_FIELD_CHANGED")
        append_fields = (
            "schedule_set_bindings",
            "attempt_bindings",
            "evidence_bindings",
            "normalization_bindings",
            "observation_tick_bindings",
            "batch_intent_bindings",
            "outcome_receipt_bindings",
            "batch_completion_bindings",
        )
        for field in append_fields:
            before = current[field]
            after = payload.get(field)
            if (
                not isinstance(after, list)
                or after[: len(before)] != before
                or len(after) - len(before) not in {0, 1}
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_APPEND_ONLY_TRANSITION_INVALID"
                )
        expiry_append_fields = ("expiry_terminal_bindings",)
        if payload_is_v2:
            for field in expiry_append_fields:
                before = current.get(field, [])
                after = payload.get(field)
                if (
                    not isinstance(before, list)
                    or not isinstance(after, list)
                    or after[: len(before)] != before
                    or len(after) - len(before) not in {0, 1}
                ):
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_EXPIRY_APPEND_ONLY_TRANSITION_INVALID"
                    )
        elif any(field in payload for field in expiry_append_fields):
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_EXPIRY_SCHEMA_REQUIRED"
            )
        if current.get("failure_binding") is not None and payload.get(
            "failure_binding"
        ) != current.get("failure_binding"):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_FAILURE_IMMUTABLE")
        if _moment(payload["updated_at"], "V32_TICK_STORE_TIME_INVALID") < _moment(
            current["updated_at"], "V32_TICK_STORE_TIME_INVALID"
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_TIME_ROLLBACK")
        next_checkpoint = self_digest(payload, "checkpoint_digest")
        self._validate_checkpoint(next_checkpoint, run_id=run_id)
        _atomic_json(self.checkpoint_path, next_checkpoint)
        return next_checkpoint

    def _write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> dict[str, str]:
        path = self._safe_path(relative_ref)
        write_once_json(path, document)
        return _generic_document_binding(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )

    def _read_generic_binding(self, binding: Mapping[str, Any]) -> Mapping[str, Any]:
        fields = {
            "relative_ref",
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
        }
        if not isinstance(binding, Mapping) or not fields.issubset(binding):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_BINDING_INVALID")
        relative_ref = _text(
            binding.get("relative_ref"), "V32_TICK_STORE_BINDING_INVALID"
        )
        path = self._safe_path(relative_ref)
        if not path.is_file() or path.is_symlink():
            raise V32OutcomeTickStoreError("V32_TICK_STORE_BINDING_INVALID")
        try:
            document = load_json_strict(path)
            semantic = verify_self_digest(document, str(binding.get("digest_field")))
        except (OSError, ValueError) as exc:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_BINDING_INVALID") from exc
        if (
            document.get("schema_id") != binding.get("schema_id")
            or semantic
            != _digest(
                binding.get("semantic_digest"), "V32_TICK_STORE_BINDING_INVALID"
            )
            or hashlib.sha256(
                canonical_bytes(dict(document)) + b"\n"
            ).hexdigest()
            != _digest(
                binding.get("physical_sha256"), "V32_TICK_STORE_BINDING_INVALID"
            )
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_BINDING_INVALID")
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_BINDING_INVALID"
            ) from exc
        return document

    def _load_expiry_terminals(
        self, *, checkpoint: Mapping[str, Any],
        schedule_sets: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        if checkpoint.get("schema_id") == CHECKPOINT_SCHEMA_ID:
            return []
        bindings = checkpoint.get("expiry_terminal_bindings")
        if not isinstance(bindings, list) or len(bindings) > TOTAL_SCHEDULES:
            raise V32OutcomeTickStoreError("V32_EXPIRY_STORE_PREFIX_INVALID")
        sets_by_digest = {
            str(schedule_set[SCHEDULE_SET_DIGEST_FIELD]): schedule_set
            for schedule_set in schedule_sets
        }
        old_receipts = [
            {key: value for key, value in receipt.items() if key != "_binding_tick_index"}
            for receipt in self._load_receipt_documents(
                checkpoint["outcome_receipt_bindings"]
            )
        ]
        terminals: list[Mapping[str, Any]] = []
        prior_expiry_ids: set[str] = set()
        for index, binding in enumerate(bindings, start=1):
            if (
                not isinstance(binding, Mapping)
                or set(binding)
                != {
                    "relative_ref", "schema_id", "digest_field", "semantic_digest",
                    "physical_sha256", "expiry_index", "checkpoint_digest_before",
                    "terminal_schedule_ids",
                }
                or binding.get("expiry_index") != index
            ):
                raise V32OutcomeTickStoreError("V32_EXPIRY_STORE_BINDING_INVALID")
            terminal = self._read_generic_binding(binding)
            digest = _digest(
                terminal.get(EXPIRY_TERMINAL_DIGEST_FIELD),
                "V32_EXPIRY_STORE_BINDING_INVALID",
            )
            bound_sets = terminal.get("outcome_schedule_set_digests")
            if (
                binding.get("relative_ref") != self._expiry_ref(digest)
                or binding.get("semantic_digest") != digest
                or binding.get("checkpoint_digest_before")
                != terminal.get("outcome_checkpoint_digest_before")
                or binding.get("terminal_schedule_ids")
                != terminal.get("terminal_schedule_ids")
                or not isinstance(bound_sets, list)
                or any(item not in sets_by_digest for item in bound_sets)
            ):
                raise V32OutcomeTickStoreError("V32_EXPIRY_STORE_BINDING_INVALID")
            try:
                verified = verify_v32_outcome_window_expiry_terminal(
                    terminal,
                    schedule_sets=[sets_by_digest[item] for item in bound_sets],
                )
            except (TypeError, ValueError) as exc:
                raise V32OutcomeTickStoreError(
                    "V32_EXPIRY_STORE_TERMINAL_INVALID"
                ) from exc
            classified = _moment(
                terminal["classified_at"], "V32_EXPIRY_STORE_TIME_INVALID"
            )
            expected_prior = {
                str(receipt["schedule_id"])
                for receipt in old_receipts
                if _moment(receipt["resolved_at"], "V32_EXPIRY_STORE_TIME_INVALID")
                <= classified
            } | prior_expiry_ids
            if (
                verified != digest
                or set(terminal["prior_terminal_schedule_ids"]) != expected_prior
                or set(terminal["terminal_schedule_ids"]) & expected_prior
            ):
                raise V32OutcomeTickStoreError("V32_EXPIRY_STORE_PREFIX_INVALID")
            prior_expiry_ids.update(terminal["terminal_schedule_ids"])
            terminals.append(terminal)
        return terminals

    def register_schedule_set(
        self, *, schedule_set: Mapping[str, Any], registered_at: str
    ) -> Mapping[str, Any]:
        digest = verify_v32_outcome_schedule_set(schedule_set)
        cycle = _positive_int(
            schedule_set.get("cycle_index"),
            "V32_TICK_STORE_CYCLE_INVALID",
            maximum=TOTAL_CYCLES,
        )
        run_id = _text(schedule_set.get("run_id"), "V32_TICK_STORE_RUN_ID_INVALID")
        _time(registered_at, "V32_TICK_STORE_TIME_INVALID")
        relative_ref = f"outcome-v32/schedules/cycle-{cycle:04d}.json"
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            bindings = current["schedule_set_bindings"]
            if cycle <= len(bindings):
                document = self._verify_schedule_binding(
                    bindings[cycle - 1], expected_cycle=cycle
                )
                if document != dict(schedule_set):
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_SCHEDULE_WRITE_ONCE_CONFLICT"
                    )
                return current
            if (
                current["status"] != "ACTIVE"
                or cycle != len(bindings) + 1
                or len(current["attempt_bindings"])
                != len(current["batch_completion_bindings"])
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_SCHEDULE_SEQUENCE_INVALID")
            base = self._write_document(
                relative_ref=relative_ref,
                document=schedule_set,
                digest_field=SCHEDULE_SET_DIGEST_FIELD,
            )
            binding = {
                **base,
                "cycle_index": cycle,
                "schedule_count": len(schedule_set["schedules"]),
            }
            if binding["semantic_digest"] != digest:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_SCHEDULE_DIGEST_INVALID")
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "schedule_set_bindings": [*bindings, binding],
                    "updated_at": registered_at,
                },
            )

    def _verify_schedule_binding(
        self, binding: Mapping[str, Any], *, expected_cycle: int
    ) -> Mapping[str, Any]:
        expected_ref = f"outcome-v32/schedules/cycle-{expected_cycle:04d}.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
                "cycle_index",
                "schedule_count",
            }
            or binding.get("relative_ref") != expected_ref
            or binding.get("cycle_index") != expected_cycle
            or binding.get("schedule_count") != 3
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_SCHEDULE_BINDING_INVALID")
        document = self._read_generic_binding(binding)
        digest = verify_v32_outcome_schedule_set(document)
        if digest != binding["semantic_digest"]:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_SCHEDULE_BINDING_INVALID")
        return document

    def load_schedule_sets(self, *, run_id: str) -> list[Mapping[str, Any]]:
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            return [
                self._verify_schedule_binding(binding, expected_cycle=index)
                for index, binding in enumerate(
                    checkpoint["schedule_set_bindings"], start=1
                )
            ]

    def reserve_attempt(
        self,
        *,
        attempt: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        digest = verify_v32_outcome_tick_attempt(attempt)
        run_id = _text(attempt.get("run_id"), "V32_TICK_STORE_RUN_ID_INVALID")
        tick = _positive_int(
            attempt.get("tick_index"), "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        relative_ref = f"{self._tick_root(tick)}/attempt.json"
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            attempts = current["attempt_bindings"]
            if tick <= len(attempts):
                existing = self._verify_attempt_binding(
                    attempts[tick - 1], expected_tick=tick
                )
                if existing != dict(attempt):
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_ATTEMPT_WRITE_ONCE_CONFLICT"
                    )
                return current
            if current["checkpoint_digest"] != expected_checkpoint_digest:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_CAS_CONFLICT")
            if (
                current["status"] != "ACTIVE"
                or tick != len(attempts) + 1
                or len(current["batch_completion_bindings"]) != len(attempts)
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_ATTEMPT_SEQUENCE_INVALID")
            base = self._write_document(
                relative_ref=relative_ref,
                document=attempt,
                digest_field=TICK_ATTEMPT_DIGEST_FIELD,
            )
            binding = {**base, "tick_index": tick}
            if binding["semantic_digest"] != digest:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_ATTEMPT_DIGEST_INVALID")
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=expected_checkpoint_digest,
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "attempt_bindings": [*attempts, binding],
                    "updated_at": attempt["reserved_at"],
                },
            )

    def _verify_attempt_binding(
        self, binding: Mapping[str, Any], *, expected_tick: int
    ) -> Mapping[str, Any]:
        expected_ref = f"{self._tick_root(expected_tick)}/attempt.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
                "tick_index",
            }
            or binding.get("relative_ref") != expected_ref
            or binding.get("tick_index") != expected_tick
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_ATTEMPT_BINDING_INVALID")
        document = self._read_generic_binding(binding)
        digest = verify_v32_outcome_tick_attempt(document)
        if digest != binding["semantic_digest"]:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_ATTEMPT_BINDING_INVALID")
        return document

    def load_attempt(self, *, run_id: str, tick_index: int) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["attempt_bindings"]) < tick:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_ATTEMPT_MISSING")
            return self._verify_attempt_binding(
                checkpoint["attempt_bindings"][tick - 1], expected_tick=tick
            )

    def _raw_paths(self, tick: int) -> tuple[str, str, str]:
        root = f"{self._tick_root(tick)}/raw"
        return root, f"{root}/raw.bin", f"{root}/capture.json"

    def _publish_raw_bundle(
        self,
        *,
        attempt: Mapping[str, Any],
        raw_payload: bytes,
        recorded_at: str,
        http_status: int = 200,
        response_received_at: str | None = None,
        capture_completed_at: str | None = None,
        final_url: str = OKX_PUBLIC_MARK_PRICE_URL,
    ) -> tuple[Mapping[str, Any], dict[str, Any]]:
        if (
            not isinstance(raw_payload, bytes)
            or len(raw_payload) > MAX_RAW_CAPTURE_BYTES
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_RAW_PAYLOAD_INVALID")
        tick = int(attempt["tick_index"])
        bundle_ref, raw_ref, record_ref = self._raw_paths(tick)
        bundle_path = self._safe_path(bundle_ref)
        capture = build_v32_public_raw_capture(
            attempt=attempt,
            recorded_at=recorded_at,
            raw_payload_ref=raw_ref,
            raw_payload_sha256=_sha256(raw_payload),
            http_status=http_status,
            response_received_at=response_received_at,
            capture_completed_at=capture_completed_at,
            final_url=final_url,
        )
        try:
            write_once_directory(
                bundle_path,
                {
                    "raw.bin": raw_payload,
                    "capture.json": canonical_bytes(capture) + b"\n",
                },
            )
        except ValueError as exc:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_RAW_WRITE_ONCE_CONFLICT"
            ) from exc
        durable, durable_raw = self._load_raw_bundle(
            attempt=attempt, bundle_ref=bundle_ref
        )
        if durable != capture or durable_raw != raw_payload:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_RAW_WRITE_ONCE_CONFLICT"
            )
        binding = {
            "relative_ref": record_ref,
            "schema_id": RAW_CAPTURE_SCHEMA_ID,
            "digest_field": RAW_CAPTURE_DIGEST_FIELD,
            "semantic_digest": capture[RAW_CAPTURE_DIGEST_FIELD],
            "physical_sha256": hashlib.sha256(
                canonical_bytes(capture) + b"\n"
            ).hexdigest(),
            "tick_index": tick,
            "evidence_kind": "PUBLIC_RAW_CAPTURE",
            "raw_payload_ref": raw_ref,
            "raw_payload_sha256": _sha256(raw_payload),
        }
        return capture, binding

    def _load_raw_bundle(
        self, *, attempt: Mapping[str, Any], bundle_ref: str
    ) -> tuple[Mapping[str, Any], bytes]:
        tick = int(attempt["tick_index"])
        expected_bundle, raw_ref, record_ref = self._raw_paths(tick)
        if bundle_ref != expected_bundle:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_RAW_BINDING_INVALID")
        raw_path = self._safe_path(raw_ref)
        record_path = self._safe_path(record_ref)
        if (
            not raw_path.is_file()
            or raw_path.is_symlink()
            or not record_path.is_file()
            or record_path.is_symlink()
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_RAW_BINDING_INVALID")
        raw = raw_path.read_bytes()
        try:
            document = load_json_strict(record_path)
            verify_v32_public_raw_capture(
                document, attempt=attempt, raw_payload=raw
            )
        except ValueError as exc:
            raise V32OutcomeTickStoreError("V32_TICK_STORE_RAW_BINDING_INVALID") from exc
        try:
            confirm_existing_directory(
                self._safe_path(bundle_ref),
                {
                    "raw.bin": raw,
                    "capture.json": canonical_bytes(document) + b"\n",
                },
            )
        except (OSError, TypeError, ValueError) as exc:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_RAW_BINDING_INVALID"
            ) from exc
        return document, raw

    def commit_raw_capture(
        self,
        *,
        run_id: str,
        tick_index: int,
        raw_payload: bytes,
        recorded_at: str,
        http_status: int = 200,
        response_received_at: str | None = None,
        capture_completed_at: str | None = None,
        final_url: str = OKX_PUBLIC_MARK_PRICE_URL,
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        _time(recorded_at, "V32_TICK_STORE_TIME_INVALID")
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or len(current["attempt_bindings"]) != tick
                or len(current["evidence_bindings"]) not in {tick - 1, tick}
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_EVIDENCE_SEQUENCE_INVALID")
            attempt = self._verify_attempt_binding(
                current["attempt_bindings"][tick - 1], expected_tick=tick
            )
            if (
                len(current["evidence_bindings"]) == tick
                and current["evidence_bindings"][tick - 1].get("evidence_kind")
                != "PUBLIC_RAW_CAPTURE"
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_EVIDENCE_WRITE_ONCE_CONFLICT"
                )
            capture, binding = self._publish_raw_bundle(
                attempt=attempt,
                raw_payload=raw_payload,
                recorded_at=recorded_at,
                http_status=http_status,
                response_received_at=response_received_at,
                capture_completed_at=capture_completed_at,
                final_url=final_url,
            )
            if len(current["evidence_bindings"]) == tick:
                if current["evidence_bindings"][tick - 1] != binding:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_EVIDENCE_WRITE_ONCE_CONFLICT"
                    )
                return current
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "evidence_bindings": [*current["evidence_bindings"], binding],
                    "updated_at": recorded_at,
                },
            )

    def commit_transport_failure(
        self,
        *,
        run_id: str,
        tick_index: int,
        failure_code: str,
        failure_at: str,
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or len(current["attempt_bindings"]) != tick
                or len(current["evidence_bindings"]) not in {tick - 1, tick}
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_EVIDENCE_SEQUENCE_INVALID")
            attempt = self._verify_attempt_binding(
                current["attempt_bindings"][tick - 1], expected_tick=tick
            )
            if (
                len(current["evidence_bindings"]) == tick
                and current["evidence_bindings"][tick - 1].get("evidence_kind")
                != "PUBLIC_TRANSPORT_FAILURE_RECEIPT"
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_EVIDENCE_WRITE_ONCE_CONFLICT"
                )
            receipt = build_v32_public_transport_failure(
                attempt=attempt, failure_code=failure_code, failure_at=failure_at
            )
            relative_ref = f"{self._tick_root(tick)}/transport-failure.json"
            base = self._write_document(
                relative_ref=relative_ref,
                document=receipt,
                digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
            )
            binding = {
                **base,
                "tick_index": tick,
                "evidence_kind": "PUBLIC_TRANSPORT_FAILURE_RECEIPT",
                "raw_payload_ref": None,
                "raw_payload_sha256": None,
            }
            if len(current["evidence_bindings"]) == tick:
                if current["evidence_bindings"][tick - 1] != binding:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_EVIDENCE_WRITE_ONCE_CONFLICT"
                    )
                return current
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "evidence_bindings": [*current["evidence_bindings"], binding],
                    "updated_at": failure_at,
                },
            )

    def recover_unbound_evidence(
        self, *, run_id: str, tick_index: int
    ) -> bool:
        """Bind an atomically published raw/failure artifact without a new GET."""

        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(current["evidence_bindings"]) >= tick:
                return True
            if (
                current["status"] != "ACTIVE"
                or len(current["attempt_bindings"]) != tick
                or len(current["evidence_bindings"]) != tick - 1
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_EVIDENCE_RECOVERY_INVALID")
            attempt = self._verify_attempt_binding(
                current["attempt_bindings"][tick - 1], expected_tick=tick
            )
            bundle_ref, _, record_ref = self._raw_paths(tick)
            record_path = self._safe_path(record_ref)
            transport_ref = f"{self._tick_root(tick)}/transport-failure.json"
            transport_path = self._safe_path(transport_ref)
            found_raw = record_path.is_file()
            found_transport = transport_path.is_file()
            if found_raw and found_transport:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_EVIDENCE_AMBIGUOUS")
            if not found_raw and not found_transport:
                return False
            if found_raw:
                capture, raw = self._load_raw_bundle(
                    attempt=attempt, bundle_ref=bundle_ref
                )
                binding = {
                    "relative_ref": record_ref,
                    "schema_id": RAW_CAPTURE_SCHEMA_ID,
                    "digest_field": RAW_CAPTURE_DIGEST_FIELD,
                    "semantic_digest": capture[RAW_CAPTURE_DIGEST_FIELD],
                    "physical_sha256": hashlib.sha256(
                        canonical_bytes(dict(capture)) + b"\n"
                    ).hexdigest(),
                    "tick_index": tick,
                    "evidence_kind": "PUBLIC_RAW_CAPTURE",
                    "raw_payload_ref": capture["raw_payload_ref"],
                    "raw_payload_sha256": _sha256(raw),
                }
                recorded_at = str(capture["recorded_at"])
            else:
                if transport_path.is_symlink():
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_SYMLINK_FORBIDDEN"
                    )
                receipt = load_json_strict(transport_path)
                verify_v32_public_transport_failure(receipt, attempt=attempt)
                base = _generic_document_binding(
                    relative_ref=transport_ref,
                    document=receipt,
                    digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
                )
                binding = {
                    **base,
                    "tick_index": tick,
                    "evidence_kind": "PUBLIC_TRANSPORT_FAILURE_RECEIPT",
                    "raw_payload_ref": None,
                    "raw_payload_sha256": None,
                }
                recorded_at = str(receipt["recorded_at"])
            self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "evidence_bindings": [*current["evidence_bindings"], binding],
                    "updated_at": recorded_at,
                },
            )
            return True

    def _verify_evidence_binding(
        self,
        binding: Mapping[str, Any],
        *,
        attempt: Mapping[str, Any],
        expected_tick: int,
    ) -> tuple[Mapping[str, Any], bytes | None]:
        expected_fields = {
            "relative_ref",
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
            "tick_index",
            "evidence_kind",
            "raw_payload_ref",
            "raw_payload_sha256",
        }
        if (
            not isinstance(binding, Mapping)
            or set(binding) != expected_fields
            or binding.get("tick_index") != expected_tick
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_EVIDENCE_BINDING_INVALID")
        kind = binding.get("evidence_kind")
        if kind == "PUBLIC_RAW_CAPTURE":
            bundle_ref, raw_ref, record_ref = self._raw_paths(expected_tick)
            if (
                binding.get("relative_ref") != record_ref
                or binding.get("raw_payload_ref") != raw_ref
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_EVIDENCE_BINDING_INVALID"
                )
            document, raw = self._load_raw_bundle(
                attempt=attempt, bundle_ref=bundle_ref
            )
            if (
                document[RAW_CAPTURE_DIGEST_FIELD] != binding.get("semantic_digest")
                or _file_sha256(self._safe_path(record_ref))
                != binding.get("physical_sha256")
                or _sha256(raw) != binding.get("raw_payload_sha256")
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_EVIDENCE_BINDING_INVALID"
                )
            return document, raw
        if kind == "PUBLIC_TRANSPORT_FAILURE_RECEIPT":
            expected_ref = f"{self._tick_root(expected_tick)}/transport-failure.json"
            if (
                binding.get("relative_ref") != expected_ref
                or binding.get("raw_payload_ref") is not None
                or binding.get("raw_payload_sha256") is not None
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_EVIDENCE_BINDING_INVALID"
                )
            document = self._read_generic_binding(binding)
            verify_v32_public_transport_failure(document, attempt=attempt)
            return document, None
        raise V32OutcomeTickStoreError("V32_TICK_STORE_EVIDENCE_KIND_INVALID")

    def load_evidence(
        self, *, run_id: str, tick_index: int
    ) -> tuple[Mapping[str, Any], bytes | None, Mapping[str, Any]]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["evidence_bindings"]) < tick:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_EVIDENCE_MISSING")
            attempt = self._verify_attempt_binding(
                checkpoint["attempt_bindings"][tick - 1], expected_tick=tick
            )
            document, raw = self._verify_evidence_binding(
                checkpoint["evidence_bindings"][tick - 1],
                attempt=attempt,
                expected_tick=tick,
            )
            return document, raw, dict(checkpoint["evidence_bindings"][tick - 1])

    def commit_normalization(
        self,
        *,
        run_id: str,
        tick_index: int,
        document: Mapping[str, Any],
        normalization_kind: str,
        committed_at: str,
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        _time(committed_at, "V32_TICK_STORE_TIME_INVALID")
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or len(current["evidence_bindings"]) != tick
                or len(current["normalization_bindings"]) not in {tick - 1, tick}
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_NORMALIZATION_SEQUENCE_INVALID"
                )
            attempt = self._verify_attempt_binding(
                current["attempt_bindings"][tick - 1], expected_tick=tick
            )
            evidence, raw_payload = self._verify_evidence_binding(
                current["evidence_bindings"][tick - 1],
                attempt=attempt,
                expected_tick=tick,
            )
            if normalization_kind == "OBSERVED_PARSE":
                digest_field = PARSE_RECEIPT_DIGEST_FIELD
                relative_ref = f"{self._tick_root(tick)}/parse-receipt.json"
            elif normalization_kind == "COVERAGE_FAILURE":
                digest_field = COVERAGE_FAILURE_DIGEST_FIELD
                relative_ref = f"{self._tick_root(tick)}/coverage-failure.json"
            elif normalization_kind == "TRANSPORT_FAILURE":
                digest_field = TRANSPORT_FAILURE_DIGEST_FIELD
                relative_ref = f"{self._tick_root(tick)}/transport-failure.json"
            else:
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_NORMALIZATION_KIND_INVALID"
                )
            _verify_v32_normalization_semantics(
                document,
                normalization_kind=normalization_kind,
                attempt=attempt,
                evidence=evidence,
                raw_payload=raw_payload,
            )
            base = self._write_document(
                relative_ref=relative_ref,
                document=document,
                digest_field=digest_field,
            )
            binding = {
                **base,
                "tick_index": tick,
                "normalization_kind": normalization_kind,
            }
            if len(current["normalization_bindings"]) == tick:
                if current["normalization_bindings"][tick - 1] != binding:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_NORMALIZATION_WRITE_ONCE_CONFLICT"
                    )
                return current
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "normalization_bindings": [
                        *current["normalization_bindings"],
                        binding,
                    ],
                    "updated_at": committed_at,
                },
            )

    def _verify_normalization_binding(
        self,
        binding: Mapping[str, Any],
        *,
        attempt: Mapping[str, Any],
        evidence: Mapping[str, Any],
        raw_payload: bytes | None,
        expected_tick: int,
    ) -> Mapping[str, Any]:
        expected_fields = {
            "relative_ref",
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
            "tick_index",
            "normalization_kind",
        }
        if (
            not isinstance(binding, Mapping)
            or set(binding) != expected_fields
            or binding.get("tick_index") != expected_tick
        ):
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_NORMALIZATION_BINDING_INVALID"
            )
        document = self._read_generic_binding(binding)
        kind = binding.get("normalization_kind")
        _verify_v32_normalization_semantics(
            document,
            normalization_kind=kind,
            attempt=attempt,
            evidence=evidence,
            raw_payload=raw_payload,
        )
        return document

    def load_normalization(
        self, *, run_id: str, tick_index: int
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["normalization_bindings"]) < tick:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_NORMALIZATION_MISSING")
            attempt = self._verify_attempt_binding(
                checkpoint["attempt_bindings"][tick - 1], expected_tick=tick
            )
            evidence, raw_payload = self._verify_evidence_binding(
                checkpoint["evidence_bindings"][tick - 1],
                attempt=attempt,
                expected_tick=tick,
            )
            binding = checkpoint["normalization_bindings"][tick - 1]
            document = self._verify_normalization_binding(
                binding,
                attempt=attempt,
                evidence=evidence,
                raw_payload=raw_payload,
                expected_tick=tick,
            )
            return document, dict(binding)

    def commit_observation_tick(
        self,
        *,
        run_id: str,
        tick_index: int,
        observation_tick: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or len(current["normalization_bindings"]) != tick
                or len(current["observation_tick_bindings"]) not in {tick - 1, tick}
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_OBSERVATION_SEQUENCE_INVALID"
                )
            attempt = self._verify_attempt_binding(
                current["attempt_bindings"][tick - 1], expected_tick=tick
            )
            evidence_binding = current["evidence_bindings"][tick - 1]
            evidence, raw_payload = self._verify_evidence_binding(
                evidence_binding,
                attempt=attempt,
                expected_tick=tick,
            )
            normalization_binding = current["normalization_bindings"][tick - 1]
            normalization = self._verify_normalization_binding(
                normalization_binding,
                attempt=attempt,
                evidence=evidence,
                raw_payload=raw_payload,
                expected_tick=tick,
            )
            digest = _verify_v32_observation_prefix_semantics(
                observation_tick,
                attempt=attempt,
                evidence=evidence,
                evidence_binding=evidence_binding,
                normalization=normalization,
                normalization_binding=normalization_binding,
            )
            relative_ref = f"{self._tick_root(tick)}/observation-tick.json"
            base = self._write_document(
                relative_ref=relative_ref,
                document=observation_tick,
                digest_field=OBSERVATION_TICK_DIGEST_FIELD,
            )
            binding = {**base, "tick_index": tick}
            if base["semantic_digest"] != digest:
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_OBSERVATION_DIGEST_INVALID"
                )
            if len(current["observation_tick_bindings"]) == tick:
                if current["observation_tick_bindings"][tick - 1] != binding:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_OBSERVATION_WRITE_ONCE_CONFLICT"
                    )
                return current
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "observation_tick_bindings": [
                        *current["observation_tick_bindings"],
                        binding,
                    ],
                    "updated_at": observation_tick["normalized_at"],
                },
            )

    def _verify_observation_binding(
        self,
        binding: Mapping[str, Any],
        *,
        attempt: Mapping[str, Any],
        evidence: Mapping[str, Any],
        evidence_binding: Mapping[str, Any],
        normalization: Mapping[str, Any],
        normalization_binding: Mapping[str, Any],
        expected_tick: int,
    ) -> Mapping[str, Any]:
        expected_ref = f"{self._tick_root(expected_tick)}/observation-tick.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
                "tick_index",
            }
            or binding.get("relative_ref") != expected_ref
            or binding.get("tick_index") != expected_tick
        ):
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_OBSERVATION_BINDING_INVALID"
            )
        document = self._read_generic_binding(binding)
        digest = _verify_v32_observation_prefix_semantics(
            document,
            attempt=attempt,
            evidence=evidence,
            evidence_binding=evidence_binding,
            normalization=normalization,
            normalization_binding=normalization_binding,
        )
        if digest != binding["semantic_digest"]:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_OBSERVATION_BINDING_INVALID"
            )
        return document

    def load_observation_tick(
        self, *, run_id: str, tick_index: int
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["observation_tick_bindings"]) < tick:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_OBSERVATION_MISSING")
            attempt = self._verify_attempt_binding(
                checkpoint["attempt_bindings"][tick - 1], expected_tick=tick
            )
            evidence_binding = checkpoint["evidence_bindings"][tick - 1]
            evidence, raw_payload = self._verify_evidence_binding(
                evidence_binding,
                attempt=attempt,
                expected_tick=tick,
            )
            normalization_binding = checkpoint["normalization_bindings"][tick - 1]
            normalization = self._verify_normalization_binding(
                normalization_binding,
                attempt=attempt,
                evidence=evidence,
                raw_payload=raw_payload,
                expected_tick=tick,
            )
            return self._verify_observation_binding(
                checkpoint["observation_tick_bindings"][tick - 1],
                attempt=attempt,
                evidence=evidence,
                evidence_binding=evidence_binding,
                normalization=normalization,
                normalization_binding=normalization_binding,
                expected_tick=tick,
            )

    def commit_batch_intent(
        self,
        *,
        run_id: str,
        tick_index: int,
        batch_intent: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or len(current["observation_tick_bindings"]) != tick
                or len(current["batch_intent_bindings"]) not in {tick - 1, tick}
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_BATCH_SEQUENCE_INVALID")
            attempt = self._verify_attempt_binding(
                current["attempt_bindings"][tick - 1], expected_tick=tick
            )
            evidence_binding = current["evidence_bindings"][tick - 1]
            evidence, raw_payload = self._verify_evidence_binding(
                evidence_binding,
                attempt=attempt,
                expected_tick=tick,
            )
            normalization_binding = current["normalization_bindings"][tick - 1]
            normalization = self._verify_normalization_binding(
                normalization_binding,
                attempt=attempt,
                evidence=evidence,
                raw_payload=raw_payload,
                expected_tick=tick,
            )
            observation = self._verify_observation_binding(
                current["observation_tick_bindings"][tick - 1],
                attempt=attempt,
                evidence=evidence,
                evidence_binding=evidence_binding,
                normalization=normalization,
                normalization_binding=normalization_binding,
                expected_tick=tick,
            )
            schedule_sets = [
                self._verify_schedule_binding(binding, expected_cycle=index)
                for index, binding in enumerate(
                    current["schedule_set_bindings"], start=1
                )
            ]
            prior_batches = [
                self._read_generic_binding(binding)
                for binding in current["batch_intent_bindings"][: tick - 1]
            ]
            prior_receipts = self._terminal_receipt_documents_from_checkpoint(current)
            digest = verify_v32_outcome_resolution_batch_intent(
                batch_intent,
                attempt=attempt,
                observation_tick=observation,
                schedule_sets=schedule_sets,
                prior_terminal_receipts=prior_receipts,
                prior_batch_intents=prior_batches,
            )
            relative_ref = f"{self._tick_root(tick)}/batch-intent.json"
            base = self._write_document(
                relative_ref=relative_ref,
                document=batch_intent,
                digest_field=BATCH_INTENT_DIGEST_FIELD,
            )
            binding = {
                **base,
                "tick_index": tick,
                "due_schedule_ids": list(batch_intent["due_schedule_ids"]),
                "schedule_set_prefix_count": len(
                    current["schedule_set_bindings"]
                ),
                "schedule_set_prefix_digest": _schedule_set_prefix_digest(
                    current["schedule_set_bindings"]
                ),
            }
            if base["semantic_digest"] != digest:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_BATCH_DIGEST_INVALID")
            if len(current["batch_intent_bindings"]) == tick:
                if current["batch_intent_bindings"][tick - 1] != binding:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_BATCH_WRITE_ONCE_CONFLICT"
                    )
                return current
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "batch_intent_bindings": [
                        *current["batch_intent_bindings"],
                        binding,
                    ],
                    "updated_at": batch_intent["created_at"],
                },
            )

    def _schedule_sets_for_batch_binding(
        self,
        *,
        binding: Mapping[str, Any],
        schedule_set_bindings: Sequence[Mapping[str, Any]],
        schedule_sets: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        count = _positive_int(
            binding.get("schedule_set_prefix_count"),
            "V32_TICK_STORE_BATCH_SCHEDULE_PREFIX_INVALID",
            maximum=TOTAL_CYCLES,
        )
        if (
            count > len(schedule_set_bindings)
            or count > len(schedule_sets)
            or binding.get("schedule_set_prefix_digest")
            != _schedule_set_prefix_digest(schedule_set_bindings[:count])
        ):
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_BATCH_SCHEDULE_PREFIX_INVALID"
            )
        return schedule_sets[:count]

    def _verify_batch_binding(
        self,
        binding: Mapping[str, Any],
        *,
        attempt: Mapping[str, Any],
        observation: Mapping[str, Any],
        schedule_set_bindings: Sequence[Mapping[str, Any]],
        schedule_sets: Sequence[Mapping[str, Any]],
        prior_receipts: Sequence[Mapping[str, Any]],
        prior_batches: Sequence[Mapping[str, Any]],
        expected_tick: int,
    ) -> Mapping[str, Any]:
        expected_ref = f"{self._tick_root(expected_tick)}/batch-intent.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
                "tick_index",
                "due_schedule_ids",
                "schedule_set_prefix_count",
                "schedule_set_prefix_digest",
            }
            or binding.get("relative_ref") != expected_ref
            or binding.get("tick_index") != expected_tick
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_BATCH_BINDING_INVALID")
        frozen_schedule_sets = self._schedule_sets_for_batch_binding(
            binding=binding,
            schedule_set_bindings=schedule_set_bindings,
            schedule_sets=schedule_sets,
        )
        document = self._read_generic_binding(binding)
        digest = verify_v32_outcome_resolution_batch_intent(
            document,
            attempt=attempt,
            observation_tick=observation,
            schedule_sets=frozen_schedule_sets,
            prior_terminal_receipts=prior_receipts,
            prior_batch_intents=prior_batches,
        )
        if (
            digest != binding["semantic_digest"]
            or list(document["due_schedule_ids"]) != binding.get("due_schedule_ids")
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_BATCH_BINDING_INVALID")
        return document

    def load_batch_intent(
        self, *, run_id: str, tick_index: int
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["batch_intent_bindings"]) < tick:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_BATCH_MISSING")
            return self._read_generic_binding(
                checkpoint["batch_intent_bindings"][tick - 1]
            )

    def load_batch_intents(self, *, run_id: str) -> list[Mapping[str, Any]]:
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            return [
                self._read_generic_binding(binding)
                for binding in checkpoint["batch_intent_bindings"]
            ]

    def _receipt_ref(self, tick: int, schedule_id: str) -> str:
        schedule = _digest(schedule_id, "V32_TICK_STORE_SCHEDULE_ID_INVALID")
        return f"{self._tick_root(tick)}/receipts/{schedule}.json"

    def commit_outcome_receipt(
        self,
        *,
        run_id: str,
        tick_index: int,
        receipt: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if current["status"] != "ACTIVE" or len(
                current["batch_intent_bindings"]
            ) != tick:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_SEQUENCE_INVALID")
            batch = self._read_generic_binding(
                current["batch_intent_bindings"][tick - 1]
            )
            existing_for_tick = [
                binding
                for binding in current["outcome_receipt_bindings"]
                if binding.get("tick_index") == tick
            ]
            expected_ids = list(batch["due_schedule_ids"])
            next_index = len(existing_for_tick)
            if next_index >= len(expected_ids):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_SET_COMPLETE")
            schedule_id = str(receipt.get("schedule_id"))
            if schedule_id != expected_ids[next_index]:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_ORDER_INVALID")
            attempt = self._verify_attempt_binding(
                current["attempt_bindings"][tick - 1], expected_tick=tick
            )
            evidence_binding = current["evidence_bindings"][tick - 1]
            evidence, raw_payload = self._verify_evidence_binding(
                evidence_binding,
                attempt=attempt,
                expected_tick=tick,
            )
            normalization_binding = current["normalization_bindings"][tick - 1]
            normalization = self._verify_normalization_binding(
                normalization_binding,
                attempt=attempt,
                evidence=evidence,
                raw_payload=raw_payload,
                expected_tick=tick,
            )
            observation = self._verify_observation_binding(
                current["observation_tick_bindings"][tick - 1],
                attempt=attempt,
                evidence=evidence,
                evidence_binding=evidence_binding,
                normalization=normalization,
                normalization_binding=normalization_binding,
                expected_tick=tick,
            )
            durable_schedule_sets = [
                self._verify_schedule_binding(binding, expected_cycle=index)
                for index, binding in enumerate(
                    current["schedule_set_bindings"], start=1
                )
            ]
            schedule_sets = self._schedule_sets_for_batch_binding(
                binding=current["batch_intent_bindings"][tick - 1],
                schedule_set_bindings=current["schedule_set_bindings"],
                schedule_sets=durable_schedule_sets,
            )
            digest = verify_v32_public_market_outcome_receipt(
                receipt,
                batch_intent=batch,
                attempt=attempt,
                observation_tick=observation,
                schedule_sets=schedule_sets,
            )
            relative_ref = self._receipt_ref(tick, schedule_id)
            base = self._write_document(
                relative_ref=relative_ref,
                document=receipt,
                digest_field=OUTCOME_RECEIPT_DIGEST_FIELD,
            )
            binding = {
                **base,
                "tick_index": tick,
                "schedule_id": schedule_id,
            }
            if base["semantic_digest"] != digest:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_DIGEST_INVALID")
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "outcome_receipt_bindings": [
                        *current["outcome_receipt_bindings"],
                        binding,
                    ],
                    "updated_at": receipt["resolved_at"],
                },
            )

    def _load_receipt_documents(
        self, bindings: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for binding in bindings:
            if (
                not isinstance(binding, Mapping)
                or set(binding)
                != {
                    "relative_ref",
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                    "tick_index",
                    "schedule_id",
                }
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_BINDING_INVALID")
            tick = _positive_int(
                binding.get("tick_index"),
                "V32_TICK_STORE_TICK_INVALID",
                maximum=MAX_TICKS,
            )
            if binding.get("relative_ref") != self._receipt_ref(
                tick, str(binding.get("schedule_id"))
            ):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_BINDING_INVALID")
            document = dict(self._read_generic_binding(binding))
            if document.get("schedule_id") != binding.get("schedule_id"):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_RECEIPT_BINDING_INVALID")
            document["_binding_tick_index"] = tick
            documents.append(document)
        return documents

    def _verify_receipt_document(
        self,
        receipt: Mapping[str, Any],
        *,
        attempt: Mapping[str, Any],
        observation: Mapping[str, Any],
        batch: Mapping[str, Any],
        schedule_sets: Sequence[Mapping[str, Any]],
    ) -> None:
        verify_v32_public_market_outcome_receipt(
            receipt,
            batch_intent=batch,
            attempt=attempt,
            observation_tick=observation,
            schedule_sets=schedule_sets,
        )

    def commit_outcome_window_expiry(
        self, *, run_id: str, expiry_terminal: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        """Write one aggregate expiry artifact and one checkpoint binding."""

        run = _text(run_id, "V32_EXPIRY_STORE_RUN_ID_INVALID")
        with self._lock():
            current = self.load_checkpoint(run_id=run, _already_locked=True)
            schedule_sets = [
                self._verify_schedule_binding(binding, expected_cycle=index)
                for index, binding in enumerate(
                    current["schedule_set_bindings"], start=1
                )
            ]
            try:
                terminal_digest = verify_v32_outcome_window_expiry_terminal(
                    expiry_terminal, schedule_sets=schedule_sets
                )
            except (TypeError, ValueError) as exc:
                raise V32OutcomeTickStoreError(
                    "V32_EXPIRY_STORE_TERMINAL_INVALID"
                ) from exc
            if (
                expiry_terminal.get("run_id") != run
                or expiry_terminal.get("outcome_checkpoint_digest_before")
                != expected_checkpoint_digest
            ):
                raise V32OutcomeTickStoreError("V32_EXPIRY_STORE_BINDING_INVALID")
            for existing in self._load_expiry_terminals(
                checkpoint=current, schedule_sets=schedule_sets
            ):
                if existing.get(EXPIRY_TERMINAL_DIGEST_FIELD) == terminal_digest:
                    if dict(existing) != dict(expiry_terminal):
                        raise V32OutcomeTickStoreError(
                            "V32_EXPIRY_STORE_WRITE_ONCE_CONFLICT"
                        )
                    return current
            if current["checkpoint_digest"] != expected_checkpoint_digest:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_CAS_CONFLICT")
            if current["status"] != "ACTIVE":
                raise V32OutcomeTickStoreError(
                    "V32_EXPIRY_STORE_CHECKPOINT_NOT_ACTIVE"
                )
            prior_ids = sorted(
                str(receipt["schedule_id"])
                for receipt in self._terminal_receipt_documents_from_checkpoint(
                    current
                )
            )
            if prior_ids != list(expiry_terminal["prior_terminal_schedule_ids"]):
                raise V32OutcomeTickStoreError(
                    "V32_EXPIRY_STORE_PRIOR_TERMINAL_SET_INVALID"
                )
            if _moment(
                expiry_terminal["classified_at"], "V32_EXPIRY_STORE_TIME_INVALID"
            ) < _moment(current["updated_at"], "V32_EXPIRY_STORE_TIME_INVALID"):
                raise V32OutcomeTickStoreError("V32_TICK_STORE_TIME_ROLLBACK")
            base = self._write_document(
                relative_ref=self._expiry_ref(terminal_digest),
                document=expiry_terminal,
                digest_field=EXPIRY_TERMINAL_DIGEST_FIELD,
            )
            binding = {
                **base,
                "expiry_index": len(current.get("expiry_terminal_bindings", ())) + 1,
                "checkpoint_digest_before": expected_checkpoint_digest,
                "terminal_schedule_ids": list(
                    expiry_terminal["terminal_schedule_ids"]
                ),
            }
            terminal_ids = {
                *prior_ids, *map(str, expiry_terminal["terminal_schedule_ids"])
            }
            all_schedule_ids = {
                str(schedule["schedule_id"])
                for schedule_set in schedule_sets
                for schedule in schedule_set["schedules"]
            }
            candidate = {
                **current,
                "schema_id": CHECKPOINT_SCHEMA_ID_V2,
                "schema_version": CHECKPOINT_SCHEMA_VERSION_V2,
                "revision": int(current["revision"]) + 1,
                "status": (
                    "TERMINAL"
                    if len(schedule_sets) == TOTAL_CYCLES
                    and terminal_ids == all_schedule_ids
                    else "ACTIVE"
                ),
                "expiry_terminal_bindings": [
                    *current.get("expiry_terminal_bindings", ()), binding
                ],
                "updated_at": expiry_terminal["classified_at"],
            }
            return self._replace_checkpoint(
                run_id=run,
                expected_checkpoint_digest=expected_checkpoint_digest,
                candidate=candidate,
            )

    def _terminal_receipt_documents_from_checkpoint(
        self, checkpoint: Mapping[str, Any]
    ) -> list[Mapping[str, Any]]:
        old = [
            {key: value for key, value in receipt.items() if key != "_binding_tick_index"}
            for receipt in self._load_receipt_documents(
                checkpoint["outcome_receipt_bindings"]
            )
        ]
        if checkpoint.get("schema_id") == CHECKPOINT_SCHEMA_ID:
            return old
        schedule_sets = [
            self._verify_schedule_binding(binding, expected_cycle=index)
            for index, binding in enumerate(
                checkpoint["schedule_set_bindings"], start=1
            )
        ]
        rows = [
            row
            for terminal in self._load_expiry_terminals(
                checkpoint=checkpoint, schedule_sets=schedule_sets
            )
            for row in terminal["rows"]
        ]
        return sorted(
            [*old, *rows],
            key=lambda receipt: (
                str(receipt["resolved_at"]), str(receipt["schedule_id"])
            ),
        )

    def load_terminal_receipts(self, *, run_id: str) -> list[Mapping[str, Any]]:
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            return self._terminal_receipt_documents_from_checkpoint(checkpoint)

    def load_outcome_window_expiry(
        self, *, run_id: str, expiry_terminal_digest: str
    ) -> Mapping[str, Any] | None:
        digest = _digest(
            expiry_terminal_digest, "V32_EXPIRY_STORE_TERMINAL_DIGEST_INVALID"
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            schedule_sets = [
                self._verify_schedule_binding(binding, expected_cycle=index)
                for index, binding in enumerate(
                    checkpoint["schedule_set_bindings"], start=1
                )
            ]
            for terminal in self._load_expiry_terminals(
                checkpoint=checkpoint, schedule_sets=schedule_sets
            ):
                if terminal.get(EXPIRY_TERMINAL_DIGEST_FIELD) == digest:
                    return {
                        "expiry_terminal": dict(terminal),
                        "checkpoint_digest": checkpoint["checkpoint_digest"],
                    }
            return None

    def load_terminal_receipt_materials(
        self, *, run_id: str
    ) -> list[Mapping[str, Any]]:
        """Read terminal receipts with their exact durable public bindings.

        The checkpoint-only ``tick_index`` and ``schedule_id`` routing fields
        are not part of an Agent packet binding.  They are replayed here and
        then removed without changing the underlying document or store state.
        """

        public_fields = (
            "relative_ref",
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            documents = self._load_receipt_documents(
                checkpoint["outcome_receipt_bindings"]
            )
            if len(documents) != len(checkpoint["outcome_receipt_bindings"]):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_RECEIPT_MATERIAL_SET_INVALID"
                )
            materials: list[Mapping[str, Any]] = []
            for document_with_tick, durable_binding in zip(
                documents,
                checkpoint["outcome_receipt_bindings"],
                strict=True,
            ):
                document = {
                    key: value
                    for key, value in document_with_tick.items()
                    if key != "_binding_tick_index"
                }
                if (
                    document.get("run_id") != run_id
                    or document.get("schedule_id")
                    != durable_binding.get("schedule_id")
                    or document_with_tick["_binding_tick_index"]
                    != durable_binding.get("tick_index")
                ):
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_RECEIPT_MATERIAL_BINDING_INVALID"
                    )
                materials.append(
                    {
                        "receipt": document,
                        "receipt_binding": {
                            field: durable_binding[field]
                            for field in public_fields
                        },
                    }
                )
            if checkpoint.get("schema_id") == CHECKPOINT_SCHEMA_ID_V2:
                schedule_sets = [
                    self._verify_schedule_binding(binding, expected_cycle=index)
                    for index, binding in enumerate(
                        checkpoint["schedule_set_bindings"], start=1
                    )
                ]
                terminals = self._load_expiry_terminals(
                    checkpoint=checkpoint, schedule_sets=schedule_sets
                )
                for terminal, durable_binding in zip(
                    terminals,
                    checkpoint["expiry_terminal_bindings"],
                    strict=True,
                ):
                    aggregate_binding = {
                        field: durable_binding[field] for field in public_fields
                    }
                    for row_index, row in enumerate(terminal["rows"]):
                        if row_index == 0:
                            member_binding = {
                                "binding_kind": "EXPIRY_AGGREGATE_MEMBER",
                                "aggregate_document": dict(terminal),
                                "aggregate_binding": aggregate_binding,
                                "member_semantic_digest": row[
                                    EXPIRY_ROW_DIGEST_FIELD
                                ],
                            }
                        else:
                            member_binding = {
                                "binding_kind": "EXPIRY_AGGREGATE_MEMBER_REF",
                                "aggregate_semantic_digest": terminal[
                                    EXPIRY_TERMINAL_DIGEST_FIELD
                                ],
                                "member_semantic_digest": row[
                                    EXPIRY_ROW_DIGEST_FIELD
                                ],
                            }
                        materials.append(
                            {
                                "receipt": dict(row),
                                "receipt_binding": member_binding,
                            }
                        )
            materials.sort(
                key=lambda material: (
                    str(material["receipt"]["resolved_at"]),
                    str(material["receipt"]["schedule_id"]),
                )
            )
            return materials

    def load_tick_receipts(
        self, *, run_id: str, tick_index: int
    ) -> list[Mapping[str, Any]]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            return [
                {
                    key: value
                    for key, value in document.items()
                    if key != "_binding_tick_index"
                }
                for document in self._load_receipt_documents(
                    checkpoint["outcome_receipt_bindings"]
                )
                if document["_binding_tick_index"] == tick
            ]

    def commit_batch_completion(
        self,
        *,
        run_id: str,
        tick_index: int,
        batch_completion: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or len(current["batch_intent_bindings"]) != tick
                or len(current["batch_completion_bindings"]) not in {tick - 1, tick}
            ):
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_COMPLETION_SEQUENCE_INVALID"
                )
            batch = self._read_generic_binding(
                current["batch_intent_bindings"][tick - 1]
            )
            receipts = [
                receipt
                for receipt in self._terminal_receipt_documents_from_checkpoint(current)
                if receipt.get("batch_intent_digest")
                == batch[BATCH_INTENT_DIGEST_FIELD]
            ]
            digest = verify_v32_outcome_resolution_batch(
                batch_completion,
                batch_intent=batch,
                outcome_receipts=receipts,
            )
            relative_ref = f"{self._tick_root(tick)}/batch-completion.json"
            base = self._write_document(
                relative_ref=relative_ref,
                document=batch_completion,
                digest_field=BATCH_COMPLETION_DIGEST_FIELD,
            )
            binding = {**base, "tick_index": tick}
            if base["semantic_digest"] != digest:
                raise V32OutcomeTickStoreError(
                    "V32_TICK_STORE_COMPLETION_DIGEST_INVALID"
                )
            if len(current["batch_completion_bindings"]) == tick:
                if current["batch_completion_bindings"][tick - 1] != binding:
                    raise V32OutcomeTickStoreError(
                        "V32_TICK_STORE_COMPLETION_WRITE_ONCE_CONFLICT"
                    )
                return current
            durable_schedule_sets = [
                self._verify_schedule_binding(binding, expected_cycle=index)
                for index, binding in enumerate(
                    current["schedule_set_bindings"], start=1
                )
            ]
            all_schedule_ids = {
                row["schedule_id"]
                for schedule_set in durable_schedule_sets
                for row in schedule_set["schedules"]
            }
            terminal_ids = {
                receipt["schedule_id"]
                for receipt in self._terminal_receipt_documents_from_checkpoint(current)
            }
            terminal = (
                len(current["schedule_set_bindings"]) == TOTAL_CYCLES
                and len(all_schedule_ids) == TOTAL_SCHEDULES
                and terminal_ids == all_schedule_ids
            )
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "status": "TERMINAL" if terminal else "ACTIVE",
                    "batch_completion_bindings": [
                        *current["batch_completion_bindings"],
                        binding,
                    ],
                    "updated_at": batch_completion["completed_at"],
                },
            )

    def _verify_completion_binding(
        self,
        binding: Mapping[str, Any],
        *,
        batch: Mapping[str, Any],
        receipts: Sequence[Mapping[str, Any]],
        expected_tick: int,
    ) -> Mapping[str, Any]:
        expected_ref = f"{self._tick_root(expected_tick)}/batch-completion.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
                "tick_index",
            }
            or binding.get("relative_ref") != expected_ref
            or binding.get("tick_index") != expected_tick
        ):
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_COMPLETION_BINDING_INVALID"
            )
        document = self._read_generic_binding(binding)
        digest = verify_v32_outcome_resolution_batch(
            document, batch_intent=batch, outcome_receipts=receipts
        )
        if digest != binding["semantic_digest"]:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_COMPLETION_BINDING_INVALID"
            )
        return document

    def load_batch_completion(
        self, *, run_id: str, tick_index: int
    ) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["batch_completion_bindings"]) < tick:
                raise V32OutcomeTickStoreError("V32_TICK_STORE_COMPLETION_MISSING")
            return self._read_generic_binding(
                checkpoint["batch_completion_bindings"][tick - 1]
            )

    def _verify_failure_binding(
        self, binding: Mapping[str, Any], *, run_id: str
    ) -> Mapping[str, Any]:
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
                "failure_code",
            }
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_FAILURE_BINDING_INVALID")
        document = self._read_generic_binding(binding)
        try:
            verify_self_digest(document, FAILURE_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32OutcomeTickStoreError(
                "V32_TICK_STORE_FAILURE_BINDING_INVALID"
            ) from exc
        if (
            document.get("schema_id") != FAILURE_SCHEMA_ID
            or document.get("run_id") != run_id
            or document.get("failure_code") != binding.get("failure_code")
            or document.get("retry_allowed") is not False
            or document.get("resume_allowed") is not False
            or document.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or document.get("executable") is not False
        ):
            raise V32OutcomeTickStoreError("V32_TICK_STORE_FAILURE_BINDING_INVALID")
        return document

    def fail_closed(
        self,
        *,
        run_id: str,
        failure_code: str,
        failed_at: str,
        tick_index: int | None,
    ) -> Mapping[str, Any]:
        code = _text(failure_code, "V32_TICK_STORE_FAILURE_CODE_INVALID")
        _time(failed_at, "V32_TICK_STORE_TIME_INVALID")
        if tick_index is not None:
            _positive_int(
                tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
            )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if current["status"] == "FAILED_CLOSED":
                return current
            if current["status"] == "TERMINAL":
                raise V32OutcomeTickStoreError("V32_TICK_STORE_TERMINAL_IMMUTABLE")
            failure = self_digest(
                {
                    "schema_id": FAILURE_SCHEMA_ID,
                    "schema_version": CHECKPOINT_SCHEMA_VERSION,
                    "run_id": run_id,
                    "tick_index": tick_index,
                    "failure_code": code,
                    "failed_at": failed_at,
                    "checkpoint_before_failure_digest": current[
                        "checkpoint_digest"
                    ],
                    "retry_allowed": False,
                    "resume_allowed": False,
                    "source_scope": SOURCE_SCOPE,
                    "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                    "executable": False,
                },
                FAILURE_DIGEST_FIELD,
            )
            relative_ref = (
                f"outcome-v32/failures/revision-{int(current['revision']) + 1:04d}.json"
            )
            base = self._write_document(
                relative_ref=relative_ref,
                document=failure,
                digest_field=FAILURE_DIGEST_FIELD,
            )
            binding = {**base, "failure_code": code}
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=current["checkpoint_digest"],
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "status": "FAILED_CLOSED",
                    "failure_binding": binding,
                    "updated_at": failed_at,
                },
            )

    def tick_prefix(self, *, run_id: str, tick_index: int) -> Mapping[str, Any]:
        tick = _positive_int(
            tick_index, "V32_TICK_STORE_TICK_INVALID", maximum=MAX_TICKS
        )
        checkpoint = self.load_checkpoint(run_id=run_id)
        if len(checkpoint["attempt_bindings"]) < tick:
            return {
                "attempt": None,
                "evidence": None,
                "normalization": None,
                "observation_tick": None,
                "batch_intent": None,
                "outcome_receipts": [],
                "batch_completion": None,
            }
        return {
            "attempt": self.load_attempt(run_id=run_id, tick_index=tick),
            "evidence": (
                self.load_evidence(run_id=run_id, tick_index=tick)
                if len(checkpoint["evidence_bindings"]) >= tick
                else None
            ),
            "normalization": (
                self.load_normalization(run_id=run_id, tick_index=tick)
                if len(checkpoint["normalization_bindings"]) >= tick
                else None
            ),
            "observation_tick": (
                self.load_observation_tick(run_id=run_id, tick_index=tick)
                if len(checkpoint["observation_tick_bindings"]) >= tick
                else None
            ),
            "batch_intent": (
                self.load_batch_intent(run_id=run_id, tick_index=tick)
                if len(checkpoint["batch_intent_bindings"]) >= tick
                else None
            ),
            "outcome_receipts": self.load_tick_receipts(
                run_id=run_id, tick_index=tick
            ),
            "batch_completion": (
                self.load_batch_completion(run_id=run_id, tick_index=tick)
                if len(checkpoint["batch_completion_bindings"]) >= tick
                else None
            ),
        }


__all__ = [
    "CHECKPOINT_SCHEMA_ID",
    "COVERAGE_FAILURE_DIGEST_FIELD",
    "COVERAGE_FAILURE_SCHEMA_ID",
    "LocalV32OutcomeTickStore",
    "PARSE_RECEIPT_DIGEST_FIELD",
    "PARSE_RECEIPT_SCHEMA_ID",
    "RAW_CAPTURE_DIGEST_FIELD",
    "RAW_CAPTURE_SCHEMA_ID",
    "TOTAL_CYCLES",
    "TOTAL_SCHEDULES",
    "TRANSPORT_FAILURE_DIGEST_FIELD",
    "TRANSPORT_FAILURE_SCHEMA_ID",
    "V32OutcomeTickStoreError",
    "build_v32_outcome_tick_checkpoint",
    "build_v32_public_coverage_failure",
    "build_v32_public_mark_parse_receipt",
    "build_v32_public_raw_capture",
    "build_v32_public_transport_failure",
    "verify_v32_public_coverage_failure",
    "verify_v32_public_mark_parse_receipt",
    "verify_v32_public_raw_capture",
    "verify_v32_public_transport_failure",
]
