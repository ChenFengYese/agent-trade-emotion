"""Raw-first application composition for one V3.2 shared outcome tick.

The injected capture port is called at most once for a newly reserved tick.
If any durable prefix already exists, only the deterministic local tail may
run.  A reserved attempt without durable raw/failure evidence is terminally
failed closed because a second request could observe a different future.

This module never connects to an account and never creates an order, fill,
position, or PnL claim.  Its sole output is delayed public-market evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence

from ..domain.contracts.canonical import canonical_decimal, loads_json_strict
from ..domain.v32_runtime_support_contracts import (
    MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS,
)
from ..domain.v32_outcome_tick import (
    INSTRUMENT_ID,
    RESPONSE_BACKED_COVERAGE_FAILURE_CODES,
    TRANSPORT_COVERAGE_FAILURE_CODES,
    build_v32_outcome_observation_tick,
    build_v32_outcome_resolution_batch,
    build_v32_outcome_resolution_batch_intent,
    build_v32_outcome_tick_attempt,
    build_v32_public_market_outcome_receipt,
    V32PublicTransportUnavailableError,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD as SUPERVISOR_PERMIT_DIGEST_FIELD,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_permit,
    verify_v32_tick_supervisor_transition,
)
from ..domain.v32_outcome_window_expiry import (
    EXPIRY_TERMINAL_DIGEST_FIELD,
    build_v32_outcome_window_expiry_terminal,
    verify_v32_outcome_window_expiry_terminal,
)
from .v32_outcome_tick_port import (
    COVERAGE_FAILURE_DIGEST_FIELD,
    PARSE_RECEIPT_DIGEST_FIELD,
    RAW_CAPTURE_DIGEST_FIELD,
    TRANSPORT_FAILURE_DIGEST_FIELD,
    V32OutcomeTickPersistenceError,
    V32OutcomeTickStorePort,
    V32PublicOutcomeCapturePort,
)


class V32OutcomeTickCompositionError(ValueError):
    """The V3.2 outcome application boundary failed closed."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


class V32OutcomeWindowExpiryStorePort(Protocol):
    """Minimal persistence contract for one zero-network expiry transition."""

    def resolution_guard(self, *, run_id: str): ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def load_schedule_sets(self, *, run_id: str) -> list[Mapping[str, Any]]: ...

    def load_terminal_receipts(self, *, run_id: str) -> list[Mapping[str, Any]]: ...

    def commit_outcome_window_expiry(self, **kwargs: Any) -> Mapping[str, Any]: ...


_OKX_PUBLIC_MARK_PRICE_URL = (
    "https://openapi.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)


def _time(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32OutcomeTickCompositionError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32OutcomeTickCompositionError(code) from exc
    if parsed.tzinfo is None:
        raise V32OutcomeTickCompositionError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        raise V32OutcomeTickCompositionError(code)
    return value


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _millisecond_epoch(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdigit()
        or len(value) != 13
    ):
        raise V32OutcomeTickCompositionError("V32_OUTCOME_PROVIDER_TIME_INVALID")
    numeric = int(value)
    seconds, milliseconds = divmod(numeric, 1000)
    try:
        parsed = datetime.fromtimestamp(seconds, tz=UTC) + timedelta(
            milliseconds=milliseconds
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_PROVIDER_TIME_INVALID"
        ) from exc
    return parsed.isoformat().replace("+00:00", "Z")


def parse_v32_public_mark_raw_v1(
    *, raw_payload: bytes, available_at: str
) -> tuple[str, Mapping[str, Any]]:
    """Parse the small admitted OKX public mark shape from durable bytes only."""

    try:
        payload = loads_json_strict(raw_payload)
    except ValueError as exc:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_RAW_JSON_INVALID") from exc
    if set(payload) not in ({"code", "data"}, {"code", "msg", "data"}):
        raise V32OutcomeTickCompositionError("V32_OUTCOME_RAW_SCHEMA_INVALID")
    code = payload.get("code")
    data = payload.get("data")
    if (
        not isinstance(code, str)
        or not isinstance(data, list)
        or ("msg" in payload and not isinstance(payload.get("msg"), str))
    ):
        raise V32OutcomeTickCompositionError("V32_OUTCOME_RAW_SCHEMA_INVALID")
    if code != "0":
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_RAW_PROVIDER_CODE_STRUCTURAL_FAILURE"
        )
    if not data:
        return "COVERAGE", {"failure_code": "PUBLIC_DATA_EMPTY"}
    if len(data) != 1 or not isinstance(data[0], Mapping):
        raise V32OutcomeTickCompositionError("V32_OUTCOME_RAW_DATA_AMBIGUOUS")
    row = data[0]
    admitted_row_shapes = (
        {"instId", "markPx", "ts"},
        {"instType", "instId", "markPx", "ts"},
    )
    if set(row) not in admitted_row_shapes:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_RAW_DATUM_SCHEMA_INVALID")
    if "instType" in row and row.get("instType") != "SWAP":
        raise V32OutcomeTickCompositionError("V32_OUTCOME_INSTRUMENT_TYPE_MISMATCH")
    if row.get("instId") != INSTRUMENT_ID:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_INSTRUMENT_MISMATCH")
    mark = row.get("markPx")
    if not isinstance(mark, str) or mark != mark.strip():
        raise V32OutcomeTickCompositionError("V32_OUTCOME_MARK_VALUE_INVALID")
    try:
        parsed = Decimal(mark)
        canonical = canonical_decimal(parsed)
    except (InvalidOperation, ValueError) as exc:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_MARK_VALUE_INVALID") from exc
    if canonical != mark or parsed <= 0:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_MARK_VALUE_INVALID")
    provider_as_of = _millisecond_epoch(row.get("ts"))
    provider_moment = _moment(provider_as_of, "V32_OUTCOME_PROVIDER_TIME_INVALID")
    available_moment = _moment(available_at, "V32_OUTCOME_AVAILABLE_TIME_INVALID")
    ahead = provider_moment - available_moment
    ahead_microseconds = max(0, ahead // timedelta(microseconds=1))
    ahead_milliseconds = (ahead_microseconds + 999) // 1000
    if ahead_milliseconds > MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_FUTURE_DATUM_FORBIDDEN")
    return "OBSERVED", {
        "value": canonical,
        "provider_as_of": provider_as_of,
        "provider_clock_ahead_milliseconds": ahead_milliseconds,
        "clock_uncertainty_status": (
            "WITHIN_BOUND_PROVIDER_AHEAD"
            if ahead_milliseconds > 0
            else "PROVIDER_NOT_AHEAD"
        ),
        "quality": "MEDIUM" if ahead_milliseconds > 0 else "HIGH",
    }


def initialize_v32_outcome_tick_runtime(
    *,
    store: V32OutcomeTickStorePort,
    run_id: str,
    created_at: str,
    supervisor_checkpoint: Mapping[str, Any],
) -> Mapping[str, Any]:
    _time(created_at, "V32_OUTCOME_INITIALIZATION_TIME_INVALID")
    try:
        verify_v32_tick_supervisor_checkpoint(supervisor_checkpoint)
    except (TypeError, ValueError) as exc:
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_INITIALIZATION_SUPERVISOR_INVALID"
        ) from exc
    expected = store.build_outcome_tick_checkpoint(
        run_id=run_id, created_at=created_at
    )
    if (
        supervisor_checkpoint.get("run_id") != run_id
        or supervisor_checkpoint.get("revision") != 0
        or supervisor_checkpoint.get("predecessor_checkpoint_digest") is not None
        or supervisor_checkpoint.get("status") != "READY"
        or supervisor_checkpoint.get("accepted_analysis_cycles") != 0
        or supervisor_checkpoint.get("scheduled_outcomes") != 0
        or supervisor_checkpoint.get("terminal_outcomes") != 0
        or supervisor_checkpoint.get("active_permit_digest") is not None
        or supervisor_checkpoint.get("current_outcome_checkpoint_digest")
        != expected["checkpoint_digest"]
    ):
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_INITIALIZATION_SUPERVISOR_BINDING_INVALID"
        )
    initialized = store.initialize_checkpoint(run_id=run_id, created_at=created_at)
    if initialized.get("checkpoint_digest") != supervisor_checkpoint.get(
        "current_outcome_checkpoint_digest"
    ):
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_INITIALIZATION_CHECKPOINT_BINDING_INVALID"
        )
    return initialized


def _verify_exact_outcome_permit(
    *,
    store: V32OutcomeTickStorePort,
    run_id: str,
    tick_index: int,
    planned_tick_at: str,
    requested_at: str,
    supervisor_checkpoint_before_permit: Mapping[str, Any],
    supervisor_open_checkpoint: Mapping[str, Any],
    supervisor_permit: Mapping[str, Any],
) -> None:
    try:
        before_digest = verify_v32_tick_supervisor_checkpoint(
            supervisor_checkpoint_before_permit
        )
        open_digest = verify_v32_tick_supervisor_checkpoint(
            supervisor_open_checkpoint
        )
        attempt = build_v32_outcome_tick_attempt(
            run_id=run_id,
            tick_index=tick_index,
            planned_tick_at=planned_tick_at,
            reserved_at=requested_at,
        )
        verify_v32_tick_supervisor_transition(
            supervisor_checkpoint_before_permit, supervisor_open_checkpoint
        )
        schedule_sets = store.load_schedule_sets(run_id=run_id)
        permit_digest = verify_v32_tick_supervisor_permit(
            supervisor_permit,
            checkpoint=supervisor_checkpoint_before_permit,
            schedule_sets=schedule_sets,
            tick_attempt=attempt,
        )
        outcome_checkpoint = store.load_checkpoint(run_id=run_id)
    except (KeyError, TypeError, ValueError) as exc:
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_SUPERVISOR_PERMIT_INVALID"
        ) from exc
    if (
        supervisor_permit.get("permit_kind") != "OUTCOME_TICK"
        or supervisor_permit.get("run_id") != run_id
        or supervisor_permit.get("outcome_tick_index") != tick_index
        or supervisor_permit.get("planned_outcome_tick_at") != planned_tick_at
        or supervisor_permit.get("issued_at") != requested_at
        or supervisor_permit.get("tick_attempt_digest")
        != attempt["outcome_tick_attempt_digest"]
        or supervisor_permit.get("supervisor_checkpoint_digest_before_permit")
        != before_digest
        or supervisor_open_checkpoint.get("status") != "OUTCOME_TICK_OPEN"
        or supervisor_open_checkpoint.get("active_permit_kind") != "OUTCOME_TICK"
        or supervisor_open_checkpoint.get("active_permit_digest") != permit_digest
        or supervisor_open_checkpoint.get("predecessor_checkpoint_digest")
        != before_digest
        or supervisor_open_checkpoint.get(SUPERVISOR_CHECKPOINT_DIGEST_FIELD)
        != open_digest
        or supervisor_permit.get(SUPERVISOR_PERMIT_DIGEST_FIELD)
        != permit_digest
    ):
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_SUPERVISOR_PERMIT_BINDING_INVALID"
        )
    attempts = outcome_checkpoint.get("attempt_bindings")
    if not isinstance(attempts, list):
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_SUPERVISOR_SUBSTORE_BINDING_INVALID"
        )
    if len(attempts) < tick_index:
        if outcome_checkpoint.get("checkpoint_digest") != supervisor_permit.get(
            "outcome_checkpoint_digest"
        ):
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_SUPERVISOR_SUBSTORE_BINDING_INVALID"
            )
    else:
        prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
        if prefix["attempt"].get("outcome_tick_attempt_digest") != supervisor_permit.get(
            "tick_attempt_digest"
        ):
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_SUPERVISOR_SUBSTORE_BINDING_INVALID"
            )


def _mature_unresolved_schedule_ids(
    *,
    schedule_sets: Sequence[Mapping[str, Any]],
    terminal_receipts: Sequence[Mapping[str, Any]],
    requested_at: str,
) -> list[str]:
    now = _moment(requested_at, "V32_OUTCOME_REQUEST_TIME_INVALID")
    terminal = {str(receipt["schedule_id"]) for receipt in terminal_receipts}
    due: list[str] = []
    for schedule_set in schedule_sets:
        for schedule in schedule_set["schedules"]:
            schedule_id = str(schedule["schedule_id"])
            if schedule_id in terminal:
                continue
            if _moment(
                schedule["outcome_not_before"], "V32_OUTCOME_SCHEDULE_TIME_INVALID"
            ) <= now:
                due.append(schedule_id)
    return sorted(due)


def _domain_raw_binding(
    *,
    evidence_document: Mapping[str, Any],
    evidence_binding: Mapping[str, Any],
    normalization_document: Mapping[str, Any],
    normalization_binding: Mapping[str, Any],
) -> dict[str, Any]:
    kind = normalization_binding["normalization_kind"]
    if kind == "OBSERVED_PARSE":
        return {
            "evidence_kind": "PUBLIC_RAW_CAPTURE",
            "schema_id": evidence_document["schema_id"],
            "digest_field": RAW_CAPTURE_DIGEST_FIELD,
            "semantic_digest": evidence_document[RAW_CAPTURE_DIGEST_FIELD],
            "physical_sha256": evidence_binding["physical_sha256"],
            "recorded_at": evidence_document["recorded_at"],
            "raw_payload_sha256": evidence_document["raw_payload_sha256"],
        }
    if kind == "COVERAGE_FAILURE":
        if evidence_document.get("schema_id", "").endswith(
            "public_raw_capture_v1"
        ):
            return {
                "evidence_kind": "PUBLIC_RAW_CAPTURE",
                "schema_id": evidence_document["schema_id"],
                "digest_field": RAW_CAPTURE_DIGEST_FIELD,
                "semantic_digest": evidence_document[RAW_CAPTURE_DIGEST_FIELD],
                "physical_sha256": evidence_binding["physical_sha256"],
                "recorded_at": evidence_document["recorded_at"],
                "raw_payload_sha256": evidence_document[
                    "raw_payload_sha256"
                ],
            }
        return {
            "evidence_kind": "PUBLIC_COVERAGE_FAILURE_RECEIPT",
            "schema_id": normalization_document["schema_id"],
            "digest_field": COVERAGE_FAILURE_DIGEST_FIELD,
            "semantic_digest": normalization_document[
                COVERAGE_FAILURE_DIGEST_FIELD
            ],
            "physical_sha256": normalization_binding["physical_sha256"],
            "recorded_at": normalization_document["recorded_at"],
            "raw_payload_sha256": None,
        }
    if kind == "TRANSPORT_FAILURE":
        return {
            "evidence_kind": "PUBLIC_TRANSPORT_FAILURE_RECEIPT",
            "schema_id": evidence_document["schema_id"],
            "digest_field": TRANSPORT_FAILURE_DIGEST_FIELD,
            "semantic_digest": evidence_document[TRANSPORT_FAILURE_DIGEST_FIELD],
            "physical_sha256": evidence_binding["physical_sha256"],
            "recorded_at": evidence_document["recorded_at"],
            "raw_payload_sha256": None,
        }
    raise V32OutcomeTickCompositionError("V32_OUTCOME_NORMALIZATION_KIND_INVALID")


def classify_v32_durable_public_mark_raw_v1(
    *,
    attempt: Mapping[str, Any],
    raw_capture: Mapping[str, Any],
    raw_payload: bytes,
) -> tuple[str, Mapping[str, Any]]:
    """Derive the sole admitted normalization from durable response bytes."""

    if not isinstance(raw_payload, bytes):
        raise V32OutcomeTickCompositionError("V32_OUTCOME_DURABLE_RAW_MISSING")
    response_received_at = _moment(
        raw_capture.get("response_received_at"),
        "V32_OUTCOME_CAPTURE_TIME_INVALID",
    )
    capture_completed_at = _moment(
        raw_capture.get("capture_completed_at"),
        "V32_OUTCOME_CAPTURE_TIME_INVALID",
    )
    recorded_at = _time(
        raw_capture.get("recorded_at"),
        "V32_OUTCOME_CAPTURE_TIME_INVALID",
    )
    recorded_moment = _moment(
        recorded_at,
        "V32_OUTCOME_CAPTURE_TIME_INVALID",
    )
    reserved_moment = _moment(
        attempt.get("reserved_at"), "V32_OUTCOME_CAPTURE_TIME_INVALID"
    )
    if raw_capture.get("final_url") != _OKX_PUBLIC_MARK_PRICE_URL:
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_RESPONSE_IDENTITY_STRUCTURAL_FAILURE"
        )
    if not (
        reserved_moment
        <= response_received_at
        <= capture_completed_at
        <= recorded_moment
    ):
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_RESPONSE_CLOCK_STRUCTURAL_FAILURE"
        )
    http_status = raw_capture.get("http_status")
    if http_status != 200:
        if http_status == 429 or (
            isinstance(http_status, int)
            and not isinstance(http_status, bool)
            and 500 <= http_status <= 599
        ):
            return "COVERAGE_FAILURE", {
                "failure_code": "PUBLIC_PROVIDER_UNAVAILABLE",
                "recorded_at": recorded_at,
            }
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_HTTP_STATUS_STRUCTURAL_FAILURE"
        )
    disposition, parsed = parse_v32_public_mark_raw_v1(
        raw_payload=raw_payload,
        available_at=recorded_at,
    )
    if disposition == "OBSERVED":
        return "OBSERVED_PARSE", {
            **parsed,
            "available_at": recorded_at,
            "recorded_at": recorded_at,
        }
    failure_code = parsed.get("failure_code")
    if failure_code not in RESPONSE_BACKED_COVERAGE_FAILURE_CODES:
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_COVERAGE_FAILURE_CODE_INVALID"
        )
    return "COVERAGE_FAILURE", {
        "failure_code": failure_code,
        "recorded_at": recorded_at,
    }


def _normalize_durable_evidence(
    *,
    store: V32OutcomeTickStorePort,
    run_id: str,
    tick_index: int,
    prefix: Mapping[str, Any],
) -> None:
    evidence_document, raw_payload, _ = prefix["evidence"]
    attempt = prefix["attempt"]
    recorded_at = str(evidence_document["recorded_at"])
    if evidence_document["schema_id"].endswith("public_transport_failure_v1"):
        store.commit_normalization(
            run_id=run_id,
            tick_index=tick_index,
            document=evidence_document,
            normalization_kind="TRANSPORT_FAILURE",
            committed_at=recorded_at,
        )
        return
    if not isinstance(raw_payload, bytes):
        raise V32OutcomeTickCompositionError("V32_OUTCOME_DURABLE_RAW_MISSING")
    kind, normalized = classify_v32_durable_public_mark_raw_v1(
        attempt=attempt,
        raw_capture=evidence_document,
        raw_payload=raw_payload,
    )
    if kind == "OBSERVED_PARSE":
        receipt = store.build_public_mark_parse_receipt(
            attempt=attempt,
            raw_capture=evidence_document,
            value=normalized["value"],
            provider_as_of=normalized["provider_as_of"],
            available_at=normalized["available_at"],
            recorded_at=normalized["recorded_at"],
        )
    else:
        receipt = store.build_public_coverage_failure(
            attempt=attempt,
            raw_capture=evidence_document,
            failure_code=normalized["failure_code"],
            recorded_at=normalized["recorded_at"],
        )
    store.commit_normalization(
        run_id=run_id,
        tick_index=tick_index,
        document=receipt,
        normalization_kind=kind,
        committed_at=recorded_at,
    )


def build_v32_outcome_observation_from_durable_prefix_v1(
    *,
    attempt: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    evidence_binding: Mapping[str, Any],
    normalization_document: Mapping[str, Any],
    normalization_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the exact observation admitted by one durable prefix."""

    kind = normalization_binding["normalization_kind"]
    raw_binding = _domain_raw_binding(
        evidence_document=evidence_document,
        evidence_binding=evidence_binding,
        normalization_document=normalization_document,
        normalization_binding=normalization_binding,
    )
    recorded_at = str(normalization_document["recorded_at"])
    if kind == "OBSERVED_PARSE":
        status = "OBSERVED_PUBLIC_MARK"
        value = normalization_document["value"]
        provider_as_of = normalization_document["provider_as_of"]
        quality = normalization_document["quality"]
        missingness = "OBSERVED"
        conflict_state = "NONE"
        parser_digest = normalization_document[PARSE_RECEIPT_DIGEST_FIELD]
    else:
        status = "UNKNOWN_COVERAGE_LOSS"
        value = None
        provider_as_of = None
        quality = "UNKNOWN"
        missingness = "UNKNOWN"
        conflict_state = normalization_document["failure_code"]
        parser_digest = normalization_binding["semantic_digest"]
    return build_v32_outcome_observation_tick(
        attempt=attempt,
        raw_evidence_binding=raw_binding,
        normalized_at=recorded_at,
        status=status,
        value=value,
        provider_as_of=provider_as_of,
        available_at=recorded_at,
        quality=quality,
        missingness=missingness,
        conflict_state=conflict_state,
        parser_receipt_digest=parser_digest,
    )


def _build_observation_from_prefix(
    *,
    store: V32OutcomeTickStorePort,
    run_id: str,
    tick_index: int,
    prefix: Mapping[str, Any],
) -> None:
    attempt = prefix["attempt"]
    evidence_document, _, evidence_binding = prefix["evidence"]
    normalization_document, normalization_binding = prefix["normalization"]
    observation = build_v32_outcome_observation_from_durable_prefix_v1(
        attempt=attempt,
        evidence_document=evidence_document,
        evidence_binding=evidence_binding,
        normalization_document=normalization_document,
        normalization_binding=normalization_binding,
    )
    store.commit_observation_tick(
        run_id=run_id,
        tick_index=tick_index,
        observation_tick=observation,
    )


def _complete_deterministic_tail(
    *,
    store: V32OutcomeTickStorePort,
    run_id: str,
    tick_index: int,
) -> Mapping[str, Any]:
    prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
    if prefix["normalization"] is None:
        _normalize_durable_evidence(
            store=store,
            run_id=run_id,
            tick_index=tick_index,
            prefix=prefix,
        )
        prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
    if prefix["observation_tick"] is None:
        _build_observation_from_prefix(
            store=store,
            run_id=run_id,
            tick_index=tick_index,
            prefix=prefix,
        )
        prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
    normalization_document, _ = prefix["normalization"]
    tail_time = str(normalization_document["recorded_at"])
    if prefix["batch_intent"] is None:
        schedule_sets = store.load_schedule_sets(run_id=run_id)
        prior_receipts = store.load_terminal_receipts(run_id=run_id)
        prior_batches = store.load_batch_intents(run_id=run_id)
        batch = build_v32_outcome_resolution_batch_intent(
            attempt=prefix["attempt"],
            observation_tick=prefix["observation_tick"],
            schedule_sets=schedule_sets,
            created_at=tail_time,
            prior_terminal_receipts=prior_receipts,
            prior_batch_intents=prior_batches,
        )
        store.commit_batch_intent(
            run_id=run_id, tick_index=tick_index, batch_intent=batch
        )
        prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
    batch = prefix["batch_intent"]
    schedule_sets = store.load_schedule_sets(run_id=run_id)
    existing = {receipt["schedule_id"] for receipt in prefix["outcome_receipts"]}
    for schedule_id in batch["due_schedule_ids"]:
        if schedule_id in existing:
            continue
        receipt = build_v32_public_market_outcome_receipt(
            batch_intent=batch,
            attempt=prefix["attempt"],
            observation_tick=prefix["observation_tick"],
            schedule_sets=schedule_sets,
            schedule_id=schedule_id,
            resolved_at=tail_time,
        )
        store.commit_outcome_receipt(
            run_id=run_id, tick_index=tick_index, receipt=receipt
        )
        existing.add(schedule_id)
    prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
    if prefix["batch_completion"] is None:
        completion = build_v32_outcome_resolution_batch(
            batch_intent=batch,
            outcome_receipts=prefix["outcome_receipts"],
            completed_at=tail_time,
        )
        checkpoint = store.commit_batch_completion(
            run_id=run_id,
            tick_index=tick_index,
            batch_completion=completion,
        )
        prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
    else:
        checkpoint = store.load_checkpoint(run_id=run_id)
    statuses = sorted(
        {receipt["resolution_status"] for receipt in prefix["outcome_receipts"]}
    )
    return {
        "run_id": run_id,
        "tick_index": tick_index,
        "runtime_status": "TERMINAL" if checkpoint["status"] == "TERMINAL" else "RESOLVED",
        "resolved_schedule_ids": list(
            prefix["batch_completion"]["resolved_schedule_ids"]
        ),
        "resolution_statuses": statuses,
        "network_request_count": 0,
        "batch_completion_digest": prefix["batch_completion"][
            "outcome_resolution_batch_digest"
        ],
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def _capture_once(
    *,
    store: V32OutcomeTickStorePort,
    capture_port: V32PublicOutcomeCapturePort,
    run_id: str,
    tick_index: int,
    attempt: Mapping[str, Any],
    requested_at: str,
) -> None:
    try:
        envelope = capture_port.capture_public_mark(
            attempt=attempt, requested_at=requested_at
        )
    except V32PublicTransportUnavailableError as exc:
        failure_code = getattr(
            exc, "coverage_failure_code", "PUBLIC_TRANSPORT_IO_FAILURE"
        )
        if failure_code not in TRANSPORT_COVERAGE_FAILURE_CODES:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_TRANSPORT_FAILURE_CODE_INVALID"
            ) from exc
        failure_at = _time(
            getattr(exc, "failure_at", None),
            "V32_OUTCOME_TRANSPORT_FAILURE_TIME_INVALID",
        )
        if _moment(
            failure_at, "V32_OUTCOME_TRANSPORT_FAILURE_TIME_INVALID"
        ) < _moment(
            requested_at, "V32_OUTCOME_TRANSPORT_FAILURE_TIME_INVALID"
        ):
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_TRANSPORT_FAILURE_TIME_INVALID"
            ) from None
        store.commit_transport_failure(
            run_id=run_id,
            tick_index=tick_index,
            failure_code=failure_code,
            failure_at=failure_at,
        )
        return
    if not isinstance(envelope, Mapping):
        raise V32OutcomeTickCompositionError("V32_OUTCOME_CAPTURE_ENVELOPE_INVALID")
    status = envelope.get("transport_status")
    if status == "RESPONSE_CAPTURED":
        if set(envelope) != {
            "transport_status",
            "source_request_id",
            "received_at",
            "captured_at",
            "final_url",
            "raw_payload",
            "http_status",
        }:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_CAPTURE_ENVELOPE_INVALID"
            )
        if envelope.get("source_request_id") != attempt["source_request_id"]:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_CAPTURE_REQUEST_ID_MISMATCH"
            )
        received_at = _time(
            envelope.get("received_at"), "V32_OUTCOME_CAPTURE_TIME_INVALID"
        )
        captured_at = _time(
            envelope.get("captured_at"), "V32_OUTCOME_CAPTURE_TIME_INVALID"
        )
        raw_payload = envelope.get("raw_payload")
        if not isinstance(raw_payload, bytes):
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_CAPTURE_PAYLOAD_INVALID"
            )
        http_status = envelope.get("http_status")
        if (
            isinstance(http_status, bool)
            or not isinstance(http_status, int)
            or not 100 <= http_status <= 599
        ):
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_CAPTURE_HTTP_STATUS_INVALID"
            )
        recorded_at = max(
            _moment(requested_at, "V32_OUTCOME_CAPTURE_TIME_INVALID"),
            _moment(captured_at, "V32_OUTCOME_CAPTURE_TIME_INVALID"),
        ).isoformat().replace("+00:00", "Z")
        store.commit_raw_capture(
            run_id=run_id,
            tick_index=tick_index,
            raw_payload=raw_payload,
            recorded_at=recorded_at,
            http_status=http_status,
            response_received_at=received_at,
            capture_completed_at=captured_at,
            final_url=envelope.get("final_url"),
        )
        return
    if status == "NO_RESPONSE":
        if set(envelope) != {
            "transport_status",
            "source_request_id",
            "failure_at",
            "failure_code",
        }:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_CAPTURE_ENVELOPE_INVALID"
            )
        if envelope.get("source_request_id") != attempt["source_request_id"]:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_CAPTURE_REQUEST_ID_MISMATCH"
            )
        failure_code = envelope.get("failure_code")
        if failure_code not in TRANSPORT_COVERAGE_FAILURE_CODES:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_TRANSPORT_FAILURE_CODE_INVALID"
            )
        failure_at = _time(
            envelope.get("failure_at"), "V32_OUTCOME_TRANSPORT_FAILURE_TIME_INVALID"
        )
        store.commit_transport_failure(
            run_id=run_id,
            tick_index=tick_index,
            failure_code=str(failure_code),
            failure_at=failure_at,
        )
        return
    raise V32OutcomeTickCompositionError("V32_OUTCOME_CAPTURE_ENVELOPE_INVALID")


def _run_v32_outcome_tick_locked(
    *,
    store: V32OutcomeTickStorePort,
    capture_port: V32PublicOutcomeCapturePort,
    run_id: str,
    tick_index: int,
    planned_tick_at: str,
    requested_at: str,
) -> Mapping[str, Any]:
    checkpoint = store.load_checkpoint(run_id=run_id)
    if checkpoint["status"] == "FAILED_CLOSED":
        return {
            "run_id": run_id,
            "tick_index": tick_index,
            "runtime_status": "FAILED_CLOSED",
            "network_request_count": 0,
            "checkpoint_digest": checkpoint["checkpoint_digest"],
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
    existing_attempts = len(checkpoint["attempt_bindings"])
    if tick_index <= existing_attempts:
        prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
        if prefix["attempt"]["planned_tick_at"] != planned_tick_at:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_EXISTING_TICK_IDENTITY_MISMATCH"
            )
        if prefix["batch_completion"] is not None:
            result = _complete_deterministic_tail(
                store=store, run_id=run_id, tick_index=tick_index
            )
            return {**result, "runtime_status": "ALREADY_COMPLETE"}
        if tick_index != existing_attempts:
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_NON_LATEST_PREFIX_INCOMPLETE"
            )
        if prefix["evidence"] is None:
            recovered = store.recover_unbound_evidence(
                run_id=run_id, tick_index=tick_index
            )
            if not recovered:
                store.fail_closed(
                    run_id=run_id,
                    failure_code="V32_OUTCOME_ATTEMPT_RESERVED_RAW_NOT_BOUND",
                    failed_at=requested_at,
                    tick_index=tick_index,
                )
                raise V32OutcomeTickCompositionError(
                    "V32_OUTCOME_ATTEMPT_RESERVED_RAW_NOT_BOUND"
                )
        return _complete_deterministic_tail(
            store=store, run_id=run_id, tick_index=tick_index
        )
    if tick_index != existing_attempts + 1:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_TICK_SEQUENCE_INVALID")
    if len(checkpoint["batch_completion_bindings"]) != existing_attempts:
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_PREVIOUS_TICK_TAIL_INCOMPLETE"
        )
    schedule_sets = store.load_schedule_sets(run_id=run_id)
    terminal_receipts = store.load_terminal_receipts(run_id=run_id)
    due = _mature_unresolved_schedule_ids(
        schedule_sets=schedule_sets,
        terminal_receipts=terminal_receipts,
        requested_at=requested_at,
    )
    if not due:
        return {
            "run_id": run_id,
            "tick_index": tick_index,
            "runtime_status": "NOT_DUE",
            "network_request_count": 0,
            "checkpoint_digest": checkpoint["checkpoint_digest"],
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
    attempt = build_v32_outcome_tick_attempt(
        run_id=run_id,
        tick_index=tick_index,
        planned_tick_at=planned_tick_at,
        reserved_at=requested_at,
    )
    store.reserve_attempt(
        attempt=attempt,
        expected_checkpoint_digest=checkpoint["checkpoint_digest"],
    )
    _capture_once(
        store=store,
        capture_port=capture_port,
        run_id=run_id,
        tick_index=tick_index,
        attempt=attempt,
        requested_at=requested_at,
    )
    prefix = store.tick_prefix(run_id=run_id, tick_index=tick_index)
    if prefix["evidence"] is None:
        raise V32OutcomeTickCompositionError(
            "V32_OUTCOME_CAPTURE_RETURNED_WITHOUT_DURABLE_EVIDENCE"
        )
    result = _complete_deterministic_tail(
        store=store, run_id=run_id, tick_index=tick_index
    )
    return {**result, "network_request_count": 1}


def run_v32_outcome_window_expiry(
    *, store: V32OutcomeWindowExpiryStorePort, run_id: str,
    supervisor_checkpoint_before_permit: Mapping[str, Any],
    supervisor_open_checkpoint: Mapping[str, Any],
    supervisor_permit: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Commit one verified aggregate expiry without a transport capability."""

    with store.resolution_guard(run_id=run_id):
        try:
            before_digest = verify_v32_tick_supervisor_checkpoint(
                supervisor_checkpoint_before_permit
            )
            verify_v32_tick_supervisor_transition(
                supervisor_checkpoint_before_permit, supervisor_open_checkpoint
            )
            schedule_sets = store.load_schedule_sets(run_id=run_id)
            permit_digest = verify_v32_tick_supervisor_permit(
                supervisor_permit,
                checkpoint=supervisor_checkpoint_before_permit,
                schedule_sets=schedule_sets,
                tick_attempt=None,
            )
            current = store.load_checkpoint(run_id=run_id)
            terminal = build_v32_outcome_window_expiry_terminal(
                run_id=run_id,
                classified_at=supervisor_permit["issued_at"],
                schedule_sets=schedule_sets,
                prior_terminal_schedule_ids=supervisor_permit[
                    "terminal_schedule_ids"
                ],
                permit_digest=permit_digest,
                supervisor_checkpoint_digest_before_permit=before_digest,
                outcome_checkpoint_digest_before=supervisor_permit[
                    "outcome_checkpoint_digest"
                ],
                experiment_contract_digest=supervisor_permit[
                    "experiment_contract_digest"
                ],
                active_authority_digest=supervisor_permit[
                    "active_authority_digest"
                ],
            )
            terminal_digest = verify_v32_outcome_window_expiry_terminal(
                terminal, schedule_sets=schedule_sets
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32OutcomeTickCompositionError(
                "V32_EXPIRY_SUPERVISOR_OR_ARTIFACT_INVALID"
            ) from exc
        if (
            supervisor_permit.get("permit_kind") != "OUTCOME_WINDOW_EXPIRY"
            or supervisor_permit.get("network_requests_allowed") != 0
            or supervisor_permit.get("tick_attempt_digest") is not None
            or supervisor_open_checkpoint.get("active_permit_digest") != permit_digest
            or terminal.get("terminal_schedule_ids")
            != supervisor_permit.get("due_schedule_ids")
        ):
            raise V32OutcomeTickCompositionError("V32_EXPIRY_BINDING_INVALID")
        attempts_before = list(current.get("attempt_bindings", ()))
        try:
            updated = store.commit_outcome_window_expiry(
                run_id=run_id,
                expiry_terminal=terminal,
                expected_checkpoint_digest=supervisor_permit[
                    "outcome_checkpoint_digest"
                ],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32OutcomeTickCompositionError(
                "V32_EXPIRY_DURABLE_TRANSITION_INVALID"
            ) from exc
        if (
            updated.get("attempt_bindings") != attempts_before
            or terminal_digest != terminal[EXPIRY_TERMINAL_DIGEST_FIELD]
        ):
            raise V32OutcomeTickCompositionError("V32_EXPIRY_ZERO_NETWORK_INVALID")
        return {
            "run_id": run_id,
            "runtime_status": "RESOLVED",
            "expiry_terminal": terminal,
            "network_request_count": 0,
            "attempt_count": 0,
            "raw_evidence_present": False,
            "observation_tick_present": False,
            "checkpoint_digest": updated["checkpoint_digest"],
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }


def run_v32_outcome_tick(
    *,
    store: V32OutcomeTickStorePort,
    capture_port: V32PublicOutcomeCapturePort,
    run_id: str,
    tick_index: int,
    planned_tick_at: str,
    requested_at: str,
    supervisor_checkpoint_before_permit: Mapping[str, Any],
    supervisor_open_checkpoint: Mapping[str, Any],
    supervisor_permit: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Resolve all schedules mature at one tick with at most one public call."""

    _time(planned_tick_at, "V32_OUTCOME_PLANNED_TICK_TIME_INVALID")
    _time(requested_at, "V32_OUTCOME_REQUEST_TIME_INVALID")
    if isinstance(tick_index, bool) or not isinstance(tick_index, int) or tick_index < 1:
        raise V32OutcomeTickCompositionError("V32_OUTCOME_TICK_INDEX_INVALID")
    with store.resolution_guard(run_id=run_id):
        try:
            _verify_exact_outcome_permit(
                store=store,
                run_id=run_id,
                tick_index=tick_index,
                planned_tick_at=planned_tick_at,
                requested_at=requested_at,
                supervisor_checkpoint_before_permit=(
                    supervisor_checkpoint_before_permit
                ),
                supervisor_open_checkpoint=supervisor_open_checkpoint,
                supervisor_permit=supervisor_permit,
            )
            return _run_v32_outcome_tick_locked(
                store=store,
                capture_port=capture_port,
                run_id=run_id,
                tick_index=tick_index,
                planned_tick_at=planned_tick_at,
                requested_at=requested_at,
            )
        except V32OutcomeTickCompositionError as exc:
            checkpoint: Mapping[str, Any] | None = None
            try:
                checkpoint = store.load_checkpoint(run_id=run_id)
                if checkpoint["status"] == "ACTIVE":
                    failed_at = (
                        checkpoint["updated_at"]
                        if _moment(
                            checkpoint["updated_at"],
                            "V32_OUTCOME_FAILURE_TIME_INVALID",
                        )
                        > _moment(
                            requested_at, "V32_OUTCOME_FAILURE_TIME_INVALID"
                        )
                        else requested_at
                    )
                    store.fail_closed(
                        run_id=run_id,
                        failure_code=(
                            "V32_OUTCOME_COMPOSITION_STRUCTURAL_FAILURE:"
                            f"{exc.failure_code}"
                        ),
                        failed_at=failed_at,
                        tick_index=(
                            tick_index
                            if len(checkpoint["attempt_bindings"]) >= tick_index
                            else None
                        ),
                    )
            except Exception:
                pass
            raise
        except V32OutcomeTickPersistenceError as exc:
            try:
                checkpoint = store.load_checkpoint(run_id=run_id)
                if checkpoint["status"] == "ACTIVE":
                    failed_at = (
                        checkpoint["updated_at"]
                        if _moment(
                            checkpoint["updated_at"],
                            "V32_OUTCOME_FAILURE_TIME_INVALID",
                        )
                        > _moment(
                            requested_at, "V32_OUTCOME_FAILURE_TIME_INVALID"
                        )
                        else requested_at
                    )
                    store.fail_closed(
                        run_id=run_id,
                        failure_code="V32_OUTCOME_STORE_STRUCTURAL_FAILURE",
                        failed_at=failed_at,
                        tick_index=(
                            tick_index
                            if len(checkpoint["attempt_bindings"]) >= tick_index
                            else None
                        ),
                    )
            except Exception:
                pass
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_STORE_STRUCTURAL_FAILURE"
            ) from exc
        except Exception as exc:
            try:
                checkpoint = store.load_checkpoint(run_id=run_id)
                if checkpoint["status"] == "ACTIVE":
                    failed_at = (
                        checkpoint["updated_at"]
                        if _moment(
                            checkpoint["updated_at"],
                            "V32_OUTCOME_FAILURE_TIME_INVALID",
                        )
                        > _moment(
                            requested_at, "V32_OUTCOME_FAILURE_TIME_INVALID"
                        )
                        else requested_at
                    )
                    store.fail_closed(
                        run_id=run_id,
                        failure_code="V32_OUTCOME_UNEXPECTED_STRUCTURAL_FAILURE",
                        failed_at=failed_at,
                        tick_index=(
                            tick_index
                            if len(checkpoint["attempt_bindings"]) >= tick_index
                            else None
                        ),
                    )
            except Exception:
                pass
            raise V32OutcomeTickCompositionError(
                "V32_OUTCOME_UNEXPECTED_STRUCTURAL_FAILURE"
            ) from exc


_parse_public_mark_raw = parse_v32_public_mark_raw_v1


__all__ = [
    "build_v32_outcome_observation_from_durable_prefix_v1",
    "classify_v32_durable_public_mark_raw_v1",
    "parse_v32_public_mark_raw_v1",
    "V32OutcomeTickCompositionError",
    "V32OutcomeTickStorePort",
    "V32OutcomeWindowExpiryStorePort",
    "V32PublicOutcomeCapturePort",
    "initialize_v32_outcome_tick_runtime",
    "run_v32_outcome_tick",
    "run_v32_outcome_window_expiry",
]
