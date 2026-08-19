"""Pure V3.2 analysis/outcome clock and shared observation-tick contracts.

The module owns deterministic research documents only.  It deliberately has
no clock, filesystem, network, Agent, account, order, fill, portfolio, paper,
live-trading, or authority-loading capability.

The important boundary is that an analysis cycle and its delayed outcomes are
different clocks.  Every sealed decision schedules 15m/1h/4h observations.
One public observation tick may resolve every schedule that is mature at that
tick, while future schedules remain unreadable and do not block analysis.
Transport and public-coverage failures may become terminal
``UNKNOWN_COVERAGE_LOSS`` outcomes, but structural, time, digest, and run
conflicts fail closed instead of being converted to missing data.

The transaction shape is intentionally recoverable::

    reserve one attempt -> bind already-durable raw/failure evidence
    -> seal one batch intent -> seal one receipt per mature schedule
    -> seal batch completion

After an attempt exists, a recovery directive never permits another GET.  A
crash after the raw binding or batch intent is therefore recoverable only from
that exact immutable prefix.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .v32_runtime_support_contracts import (
    MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS,
)


class V32OutcomeTickError(ValueError):
    """A V3.2 outcome-clock invariant failed closed."""


class V32PublicTransportUnavailableError(OSError):
    """A single public request failed at the transport boundary.

    Only this typed exception may be downgraded to terminal coverage loss by
    the Application layer.  Contract, schema, identity, and adapter defects
    remain structural failures and must never be relabelled as network noise.
    """

    def __init__(
        self,
        failure_code: str,
        *,
        coverage_failure_code: str = "PUBLIC_TRANSPORT_IO_FAILURE",
        failure_at: str,
    ) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.coverage_failure_code = coverage_failure_code
        self.failure_at = failure_at


SCHEMA_VERSION = "1.0.0"

SCHEDULE_SET_SCHEMA_ID = "theory_paper_v32_outcome_schedule_set_v1"
SCHEDULE_SET_DIGEST_FIELD = "outcome_schedule_set_digest"
TICK_ATTEMPT_SCHEMA_ID = "theory_paper_v32_outcome_tick_attempt_v1"
TICK_ATTEMPT_DIGEST_FIELD = "outcome_tick_attempt_digest"
OBSERVATION_TICK_SCHEMA_ID = "theory_paper_v32_outcome_observation_tick_v1"
OBSERVATION_TICK_DIGEST_FIELD = "outcome_observation_tick_digest"
BATCH_INTENT_SCHEMA_ID = "theory_paper_v32_outcome_resolution_batch_intent_v1"
BATCH_INTENT_DIGEST_FIELD = "outcome_resolution_batch_intent_digest"
OUTCOME_RECEIPT_SCHEMA_ID = "theory_paper_v32_public_market_outcome_receipt_v1"
OUTCOME_RECEIPT_DIGEST_FIELD = "public_market_outcome_receipt_digest"
BATCH_COMPLETION_SCHEMA_ID = "theory_paper_v32_outcome_resolution_batch_v1"
BATCH_COMPLETION_DIGEST_FIELD = "outcome_resolution_batch_digest"
ANALYSIS_CLOCK_VIEW_SCHEMA_ID = "theory_paper_v32_analysis_clock_view_v1"
ANALYSIS_CLOCK_VIEW_DIGEST_FIELD = "analysis_clock_view_digest"
RECOVERY_DIRECTIVE_SCHEMA_ID = "theory_paper_v32_outcome_tail_recovery_v1"
RECOVERY_DIRECTIVE_DIGEST_FIELD = "outcome_tail_recovery_digest"

HORIZON_POLICY = (
    ("15M", 900),
    ("1H", 3_600),
    ("4H", 14_400),
)
OUTCOME_GRACE_SECONDS = 900
OBSERVABLE_REF = "metric:okx-public-mark-price-usdt"
INSTRUMENT_ID = "BTC-USDT-SWAP"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

RAW_EVIDENCE_KINDS = (
    "PUBLIC_RAW_CAPTURE",
    "PUBLIC_TRANSPORT_FAILURE_RECEIPT",
    "PUBLIC_COVERAGE_FAILURE_RECEIPT",
)
RAW_EVIDENCE_ROLE_SPEC = {
    "PUBLIC_RAW_CAPTURE": (
        "theory_paper_v32_public_raw_capture_v1",
        "public_raw_capture_digest",
    ),
    "PUBLIC_TRANSPORT_FAILURE_RECEIPT": (
        "theory_paper_v32_public_transport_failure_v1",
        "public_transport_failure_digest",
    ),
    "PUBLIC_COVERAGE_FAILURE_RECEIPT": (
        "theory_paper_v32_public_coverage_failure_v1",
        "public_coverage_failure_digest",
    ),
}
TICK_STATUSES = ("OBSERVED_PUBLIC_MARK", "UNKNOWN_COVERAGE_LOSS")
TRANSPORT_COVERAGE_FAILURE_CODES = (
    "PUBLIC_CONNECTION_FAILURE",
    "PUBLIC_DNS_UNAVAILABLE",
    "PUBLIC_TIMEOUT",
    "PUBLIC_TLS_FAILURE",
    "PUBLIC_TRANSPORT_IO_FAILURE",
)
RESPONSE_BACKED_COVERAGE_FAILURE_CODES = (
    "PUBLIC_PROVIDER_UNAVAILABLE",
    "PUBLIC_DATA_EMPTY",
)
COVERAGE_FAILURE_CODES = (
    *TRANSPORT_COVERAGE_FAILURE_CODES,
    *RESPONSE_BACKED_COVERAGE_FAILURE_CODES,
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

_SCHEDULE_FIELDS = frozenset(
    {
        "schedule_id",
        "run_id",
        "decision_id",
        "cycle_index",
        "horizon",
        "horizon_seconds",
        "decision_time",
        "outcome_not_before",
        "expires_at",
        "observable_ref",
        "instrument_id",
        "observation_semantics",
        "stop_trigger_semantics",
        "fill_claim",
        "pnl_claim",
        "schedule_digest",
    }
)
_SCHEDULE_SET_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "decision_id",
        "cycle_index",
        "decision_time",
        "scheduled_at",
        "sealed_decision_digest",
        "evaluation_contract_digest",
        "analysis_clock_policy",
        "outcome_clock_policy",
        "schedules",
        "source_scope",
        "external_execution_authority",
        "executable",
        SCHEDULE_SET_DIGEST_FIELD,
    }
)
_ATTEMPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "tick_id",
        "planned_tick_at",
        "reserved_at",
        "attempt_id",
        "attempt_number",
        "max_network_requests",
        "retry_allowed",
        "source_request_id",
        "request_operation",
        "source_scope",
        "external_execution_authority",
        "executable",
        TICK_ATTEMPT_DIGEST_FIELD,
    }
)
_RAW_BINDING_FIELDS = frozenset(
    {
        "evidence_kind",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
        "recorded_at",
        "raw_payload_sha256",
    }
)
_TICK_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "tick_id",
        "planned_tick_at",
        "attempt_digest",
        "attempt_number",
        "network_request_count",
        "source_request_id",
        "raw_evidence_binding",
        "normalized_at",
        "status",
        "observable_ref",
        "instrument_id",
        "value",
        "provider_as_of",
        "available_at",
        "quality",
        "missingness",
        "conflict_state",
        "parser_receipt_digest",
        "observation_scope",
        "stop_trigger_semantics",
        "fill_claim",
        "pnl_claim",
        "source_scope",
        "external_execution_authority",
        "executable",
        OBSERVATION_TICK_DIGEST_FIELD,
    }
)
_DISPOSITION_FIELDS = frozenset(
    {
        "schedule_id",
        "schedule_digest",
        "schedule_set_digest",
        "horizon",
        "outcome_not_before",
        "expires_at",
        "timing_class",
        "resolution_status",
        "value_read_allowed",
        "coverage_loss_reason",
    }
)
_BATCH_INTENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "batch_id",
        "created_at",
        "tick_attempt_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "due_schedule_ids",
        "future_schedule_ids",
        "preexisting_terminal_schedule_ids",
        "outcome_dispositions",
        "same_tick_shared_capture",
        "network_request_allowed_during_tail",
        "recovery_policy",
        "source_scope",
        "external_execution_authority",
        "executable",
        BATCH_INTENT_DIGEST_FIELD,
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "schedule_id",
        "schedule_digest",
        "schedule_set_digest",
        "decision_id",
        "cycle_index",
        "horizon",
        "outcome_not_before",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "resolved_at",
        "resolution_status",
        "coverage_loss_reason",
        "observable_ref",
        "value",
        "provider_as_of",
        "available_at",
        "quality",
        "missingness",
        "terminal",
        "attempt_count",
        "retry_allowed",
        "shared_tick_request",
        "observation_scope",
        "stop_trigger_semantics",
        "trigger_is_fill",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "source_scope",
        "external_execution_authority",
        "executable",
        OUTCOME_RECEIPT_DIGEST_FIELD,
    }
)
_COMPLETION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "batch_id",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "completed_at",
        "resolved_schedule_ids",
        "outcome_receipt_digests",
        "network_requests_during_tail",
        "all_due_schedules_terminal",
        "source_scope",
        "external_execution_authority",
        "executable",
        BATCH_COMPLETION_DIGEST_FIELD,
    }
)
_CLOCK_VIEW_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_time",
        "mature_terminal_schedule_ids",
        "mature_unresolved_schedule_ids",
        "future_schedule_ids",
        "available_outcome_receipt_digests",
        "future_outcomes_readable",
        "future_outcomes_block_analysis",
        "analysis_allowed",
        "analysis_gate_reason",
        "source_scope",
        "external_execution_authority",
        "executable",
        ANALYSIS_CLOCK_VIEW_DIGEST_FIELD,
    }
)
_RECOVERY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_attempt_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "batch_intent_digest",
        "existing_outcome_receipt_digests",
        "batch_completion_digest",
        "recovery_state",
        "missing_schedule_ids",
        "network_request_allowed",
        "same_attempt_required",
        "same_raw_evidence_required",
        "deterministic_tail_only",
        "source_scope",
        "external_execution_authority",
        "executable",
        RECOVERY_DIRECTIVE_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32OutcomeTickError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32OutcomeTickError(code)
    return value


def _positive_int(value: Any, code: str, *, maximum: int = 1_000_000) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise V32OutcomeTickError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32OutcomeTickError(code) from exc
    if parsed.tzinfo is None:
        raise V32OutcomeTickError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32OutcomeTickError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _provider_clock_quality(
    *, provider: datetime, available: datetime, code: str
) -> str:
    ahead = provider - available
    ahead_microseconds = max(0, ahead // timedelta(microseconds=1))
    ahead_milliseconds = (ahead_microseconds + 999) // 1000
    if ahead_milliseconds > MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS:
        raise V32OutcomeTickError(code)
    return "MEDIUM" if ahead_milliseconds > 0 else "HIGH"


def _sorted_unique_strings(
    value: Any, code: str, *, allow_empty: bool = True
) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32OutcomeTickError(code)
    rows = [_text(item, code) for item in value]
    if (not allow_empty and not rows) or len(rows) != len(set(rows)):
        raise V32OutcomeTickError(code)
    return sorted(rows)


def _decimal_text(value: Any, code: str, *, positive: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise V32OutcomeTickError(code)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise V32OutcomeTickError(code) from exc
    try:
        canonical = canonical_decimal(parsed)
    except ValueError as exc:
        raise V32OutcomeTickError(code) from exc
    if canonical != value or (positive and parsed <= 0):
        raise V32OutcomeTickError(code)
    return canonical


def _assert_boundary(document: Mapping[str, Any], code: str) -> None:
    if (
        document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
    ):
        raise V32OutcomeTickError(code)


def _schedule_identity(
    *, run_id: str, decision_id: str, cycle_index: int, horizon: str
) -> str:
    return canonical_digest(
        {
            "schema_id": "theory_paper_v32_outcome_schedule_identity_v1",
            "run_id": run_id,
            "decision_id": decision_id,
            "cycle_index": cycle_index,
            "horizon": horizon,
        }
    )


def build_v32_outcome_schedule_set(
    *,
    run_id: str,
    decision_id: str,
    cycle_index: int,
    decision_time: str,
    scheduled_at: str,
    sealed_decision_digest: str,
    evaluation_contract_digest: str,
) -> dict[str, Any]:
    """Schedule exact 15m/1h/4h public-market outcomes for one decision."""

    run = _text(run_id, "V32_OUTCOME_RUN_ID_INVALID")
    decision = _text(decision_id, "V32_OUTCOME_DECISION_ID_INVALID")
    cycle = _positive_int(cycle_index, "V32_OUTCOME_CYCLE_INDEX_INVALID")
    decided = _moment(decision_time, "V32_OUTCOME_DECISION_TIME_INVALID")
    scheduled = _moment(scheduled_at, "V32_OUTCOME_SCHEDULED_AT_INVALID")
    if not (decided <= scheduled < decided + timedelta(seconds=HORIZON_POLICY[0][1])):
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_TIME_ORDER_INVALID")
    schedules: list[dict[str, Any]] = []
    for horizon, seconds in HORIZON_POLICY:
        not_before = decided + timedelta(seconds=seconds)
        expires = not_before + timedelta(seconds=OUTCOME_GRACE_SECONDS)
        row = {
            "schedule_id": _schedule_identity(
                run_id=run,
                decision_id=decision,
                cycle_index=cycle,
                horizon=horizon,
            ),
            "run_id": run,
            "decision_id": decision,
            "cycle_index": cycle,
            "horizon": horizon,
            "horizon_seconds": seconds,
            "decision_time": _time(
                decision_time, "V32_OUTCOME_DECISION_TIME_INVALID"
            ),
            "outcome_not_before": not_before.isoformat().replace("+00:00", "Z"),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "observable_ref": OBSERVABLE_REF,
            "instrument_id": INSTRUMENT_ID,
            "observation_semantics": (
                "FIRST_SHARED_PUBLIC_MARK_TICK_AT_OR_AFTER_HORIZON_WITHIN_GRACE"
            ),
            "stop_trigger_semantics": (
                "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL"
            ),
            "fill_claim": False,
            "pnl_claim": False,
        }
        row["schedule_digest"] = canonical_digest(row)
        schedules.append(row)
    return self_digest(
        {
            "schema_id": SCHEDULE_SET_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run,
            "decision_id": decision,
            "cycle_index": cycle,
            "decision_time": _time(
                decision_time, "V32_OUTCOME_DECISION_TIME_INVALID"
            ),
            "scheduled_at": _time(
                scheduled_at, "V32_OUTCOME_SCHEDULED_AT_INVALID"
            ),
            "sealed_decision_digest": _digest(
                sealed_decision_digest, "V32_OUTCOME_DECISION_DIGEST_INVALID"
            ),
            "evaluation_contract_digest": _digest(
                evaluation_contract_digest,
                "V32_OUTCOME_EVALUATION_DIGEST_INVALID",
            ),
            "analysis_clock_policy": (
                "FUTURE_OUTCOMES_UNREADABLE_AND_DO_NOT_BLOCK_ANALYSIS"
            ),
            "outcome_clock_policy": (
                "15M_1H_4H_RAW_FIRST_ONE_ATTEMPT_SHARED_TICK"
            ),
            "schedules": schedules,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        SCHEDULE_SET_DIGEST_FIELD,
    )


def verify_v32_outcome_schedule_set(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _SCHEDULE_SET_FIELDS:
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_SET_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, SCHEDULE_SET_DIGEST_FIELD)
        rebuilt = build_v32_outcome_schedule_set(
            run_id=document["run_id"],
            decision_id=document["decision_id"],
            cycle_index=document["cycle_index"],
            decision_time=document["decision_time"],
            scheduled_at=document["scheduled_at"],
            sealed_decision_digest=document["sealed_decision_digest"],
            evaluation_contract_digest=document["evaluation_contract_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickError):
            raise
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_SET_INVALID") from exc
    for row in document.get("schedules", ()):
        verify_v32_outcome_schedule(row)
    if dict(document) != rebuilt or supplied != rebuilt[SCHEDULE_SET_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_SET_RECONSTRUCTION_MISMATCH")
    _assert_boundary(document, "V32_OUTCOME_SCHEDULE_AUTHORITY_INVALID")
    return supplied


def verify_v32_outcome_schedule(document: Mapping[str, Any]) -> str:
    """Verify one complete schedule row without trusting its parent set."""

    if not isinstance(document, Mapping) or set(document) != _SCHEDULE_FIELDS:
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_SCHEMA_INVALID")
    run_id = _text(document.get("run_id"), "V32_OUTCOME_SCHEDULE_IDENTITY_INVALID")
    decision_id = _text(
        document.get("decision_id"), "V32_OUTCOME_SCHEDULE_IDENTITY_INVALID"
    )
    cycle_index = _positive_int(
        document.get("cycle_index"), "V32_OUTCOME_SCHEDULE_IDENTITY_INVALID"
    )
    horizon = _text(
        document.get("horizon"), "V32_OUTCOME_SCHEDULE_HORIZON_INVALID"
    )
    horizon_by_name = dict(HORIZON_POLICY)
    if horizon not in horizon_by_name:
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_HORIZON_INVALID")
    horizon_seconds = _positive_int(
        document.get("horizon_seconds"),
        "V32_OUTCOME_SCHEDULE_HORIZON_INVALID",
    )
    if horizon_seconds != horizon_by_name[horizon]:
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_HORIZON_INVALID")

    decision = _moment(
        document.get("decision_time"), "V32_OUTCOME_SCHEDULE_TIME_INVALID"
    )
    not_before = _moment(
        document.get("outcome_not_before"), "V32_OUTCOME_SCHEDULE_TIME_INVALID"
    )
    expires = _moment(
        document.get("expires_at"), "V32_OUTCOME_SCHEDULE_TIME_INVALID"
    )
    if (
        not_before != decision + timedelta(seconds=horizon_seconds)
        or expires != not_before + timedelta(seconds=OUTCOME_GRACE_SECONDS)
    ):
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_TIME_INVALID")

    if (
        document.get("schedule_id")
        != _schedule_identity(
            run_id=run_id,
            decision_id=decision_id,
            cycle_index=cycle_index,
            horizon=horizon,
        )
        or document.get("observable_ref") != OBSERVABLE_REF
        or document.get("instrument_id") != INSTRUMENT_ID
        or document.get("observation_semantics")
        != "FIRST_SHARED_PUBLIC_MARK_TICK_AT_OR_AFTER_HORIZON_WITHIN_GRACE"
        or document.get("stop_trigger_semantics")
        != "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL"
        or document.get("fill_claim") is not False
        or document.get("pnl_claim") is not False
    ):
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_BOUNDARY_INVALID")

    supplied_digest = _digest(
        document.get("schedule_digest"), "V32_OUTCOME_SCHEDULE_DIGEST_INVALID"
    )
    intrinsic = {
        key: value for key, value in document.items() if key != "schedule_digest"
    }
    if supplied_digest != canonical_digest(intrinsic):
        raise V32OutcomeTickError("V32_OUTCOME_SCHEDULE_DIGEST_INVALID")
    return str(supplied_digest)


def classify_v32_outcome_schedule_time(
    schedule: Mapping[str, Any], *, now: str
) -> str:
    """Classify a fully verified schedule at one explicit observation time."""

    verify_v32_outcome_schedule(schedule)
    target = _moment(
        schedule["outcome_not_before"], "V32_OUTCOME_SCHEDULE_TIME_INVALID"
    )
    expires = _moment(schedule["expires_at"], "V32_OUTCOME_SCHEDULE_TIME_INVALID")
    observed = _moment(now, "V32_OUTCOME_SCHEDULE_CLASSIFICATION_TIME_INVALID")
    if observed < target:
        return "FUTURE"
    if observed <= expires:
        return "DUE"
    return "EXPIRED"


def build_v32_outcome_tick_attempt(
    *,
    run_id: str,
    tick_index: int,
    planned_tick_at: str,
    reserved_at: str,
) -> dict[str, Any]:
    """Reserve the sole network side-effect for one aligned outcome tick."""

    run = _text(run_id, "V32_TICK_RUN_ID_INVALID")
    index = _positive_int(tick_index, "V32_TICK_INDEX_INVALID")
    planned = _moment(planned_tick_at, "V32_TICK_PLANNED_TIME_INVALID")
    reserved = _moment(reserved_at, "V32_TICK_RESERVED_TIME_INVALID")
    if not planned <= reserved <= planned + timedelta(seconds=OUTCOME_GRACE_SECONDS):
        raise V32OutcomeTickError("V32_TICK_RESERVATION_TIME_INVALID")
    attempt_id = canonical_digest(
        {
            "schema_id": "theory_paper_v32_outcome_tick_attempt_identity_v1",
            "run_id": run,
            "tick_index": index,
            "planned_tick_at": _time(
                planned_tick_at, "V32_TICK_PLANNED_TIME_INVALID"
            ),
        }
    )
    return self_digest(
        {
            "schema_id": TICK_ATTEMPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run,
            "tick_index": index,
            "tick_id": attempt_id,
            "planned_tick_at": _time(
                planned_tick_at, "V32_TICK_PLANNED_TIME_INVALID"
            ),
            "reserved_at": _time(reserved_at, "V32_TICK_RESERVED_TIME_INVALID"),
            "attempt_id": attempt_id,
            "attempt_number": 1,
            "max_network_requests": 1,
            "retry_allowed": False,
            "source_request_id": f"v32-public-outcome-tick:{attempt_id}",
            "request_operation": "GET_PUBLIC_MARK_OBSERVATION",
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        TICK_ATTEMPT_DIGEST_FIELD,
    )


def verify_v32_outcome_tick_attempt(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _ATTEMPT_FIELDS:
        raise V32OutcomeTickError("V32_TICK_ATTEMPT_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, TICK_ATTEMPT_DIGEST_FIELD)
        rebuilt = build_v32_outcome_tick_attempt(
            run_id=document["run_id"],
            tick_index=document["tick_index"],
            planned_tick_at=document["planned_tick_at"],
            reserved_at=document["reserved_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickError):
            raise
        raise V32OutcomeTickError("V32_TICK_ATTEMPT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[TICK_ATTEMPT_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_TICK_ATTEMPT_RECONSTRUCTION_MISMATCH")
    _assert_boundary(document, "V32_TICK_ATTEMPT_AUTHORITY_INVALID")
    return supplied


def _raw_binding(
    value: Any, *, reserved_at: datetime, normalized_at: datetime
) -> dict[str, Any]:
    code = "V32_TICK_RAW_EVIDENCE_INVALID"
    if not isinstance(value, Mapping) or set(value) != _RAW_BINDING_FIELDS:
        raise V32OutcomeTickError(code)
    kind = _text(value["evidence_kind"], code)
    if kind not in RAW_EVIDENCE_KINDS:
        raise V32OutcomeTickError(code)
    schema_id = _text(value["schema_id"], code)
    digest_field = _text(value["digest_field"], code)
    if (schema_id, digest_field) != RAW_EVIDENCE_ROLE_SPEC[kind]:
        raise V32OutcomeTickError("V32_TICK_RAW_EVIDENCE_ROLE_INVALID")
    recorded = _moment(value["recorded_at"], code)
    if not reserved_at <= recorded <= normalized_at:
        raise V32OutcomeTickError("V32_TICK_RAW_FIRST_TIME_INVALID")
    raw_sha = _digest(value["raw_payload_sha256"], code, nullable=True)
    if (kind == "PUBLIC_RAW_CAPTURE") != (raw_sha is not None):
        raise V32OutcomeTickError("V32_TICK_RAW_BINDING_KIND_INVALID")
    return {
        "evidence_kind": kind,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": _digest(value["semantic_digest"], code),
        "physical_sha256": _digest(value["physical_sha256"], code),
        "recorded_at": _time(value["recorded_at"], code),
        "raw_payload_sha256": raw_sha,
    }


def build_v32_outcome_observation_tick(
    *,
    attempt: Mapping[str, Any],
    raw_evidence_binding: Mapping[str, Any],
    normalized_at: str,
    status: str,
    value: str | None,
    provider_as_of: str | None,
    available_at: str,
    quality: str,
    missingness: str,
    conflict_state: str,
    parser_receipt_digest: str,
) -> dict[str, Any]:
    """Bind normalized public-market semantics to already durable evidence."""

    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    normalized = _moment(normalized_at, "V32_TICK_NORMALIZED_AT_INVALID")
    available = _moment(available_at, "V32_TICK_AVAILABLE_AT_INVALID")
    reserved = _moment(attempt["reserved_at"], "V32_TICK_RESERVED_TIME_INVALID")
    if not reserved <= available <= normalized:
        raise V32OutcomeTickError("V32_TICK_OBSERVATION_TIME_INVALID")
    binding = _raw_binding(
        raw_evidence_binding,
        reserved_at=reserved,
        normalized_at=normalized,
    )
    state = _text(status, "V32_TICK_STATUS_INVALID")
    if state not in TICK_STATUSES:
        raise V32OutcomeTickError("V32_TICK_STATUS_INVALID")
    provider_text: str | None
    if state == "OBSERVED_PUBLIC_MARK":
        if binding["evidence_kind"] != "PUBLIC_RAW_CAPTURE":
            raise V32OutcomeTickError("V32_TICK_OBSERVED_RAW_REQUIRED")
        observed_value = _decimal_text(value, "V32_TICK_VALUE_INVALID", positive=True)
        provider_text = _time(provider_as_of, "V32_TICK_PROVIDER_TIME_INVALID")
        required_quality = _provider_clock_quality(
            provider=_moment(provider_text, "V32_TICK_PROVIDER_TIME_INVALID"),
            available=available,
            code="V32_TICK_PROVIDER_TIME_INVALID",
        )
        if quality != required_quality or missingness != "OBSERVED":
            raise V32OutcomeTickError("V32_TICK_OBSERVED_QUALITY_INVALID")
        if conflict_state != "NONE":
            raise V32OutcomeTickError("V32_TICK_OBSERVED_CONFLICT_INVALID")
    else:
        if value is not None or provider_as_of is not None:
            raise V32OutcomeTickError("V32_TICK_UNKNOWN_VALUE_FORBIDDEN")
        if quality != "UNKNOWN" or missingness != "UNKNOWN":
            raise V32OutcomeTickError("V32_TICK_UNKNOWN_QUALITY_INVALID")
        if conflict_state not in COVERAGE_FAILURE_CODES:
            raise V32OutcomeTickError("V32_TICK_COVERAGE_FAILURE_CODE_INVALID")
        if conflict_state in TRANSPORT_COVERAGE_FAILURE_CODES:
            if binding["evidence_kind"] != "PUBLIC_TRANSPORT_FAILURE_RECEIPT":
                raise V32OutcomeTickError("V32_TICK_FAILURE_RECEIPT_REQUIRED")
        elif binding["evidence_kind"] != "PUBLIC_RAW_CAPTURE":
            raise V32OutcomeTickError("V32_TICK_RESPONSE_RAW_REQUIRED")
        observed_value = None
        provider_text = None
    return self_digest(
        {
            "schema_id": OBSERVATION_TICK_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": attempt["run_id"],
            "tick_index": attempt["tick_index"],
            "tick_id": attempt["tick_id"],
            "planned_tick_at": attempt["planned_tick_at"],
            "attempt_digest": attempt_digest,
            "attempt_number": 1,
            "network_request_count": 1,
            "source_request_id": attempt["source_request_id"],
            "raw_evidence_binding": binding,
            "normalized_at": _time(
                normalized_at, "V32_TICK_NORMALIZED_AT_INVALID"
            ),
            "status": state,
            "observable_ref": OBSERVABLE_REF,
            "instrument_id": INSTRUMENT_ID,
            "value": observed_value,
            "provider_as_of": provider_text,
            "available_at": _time(available_at, "V32_TICK_AVAILABLE_AT_INVALID"),
            "quality": quality,
            "missingness": missingness,
            "conflict_state": conflict_state,
            "parser_receipt_digest": _digest(
                parser_receipt_digest, "V32_TICK_PARSER_RECEIPT_INVALID"
            ),
            "observation_scope": "PUBLIC_MARKET_PATH_ONLY_NO_EXECUTION_STATE",
            "stop_trigger_semantics": (
                "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL"
            ),
            "fill_claim": False,
            "pnl_claim": False,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        OBSERVATION_TICK_DIGEST_FIELD,
    )


def verify_v32_outcome_observation_tick(
    document: Mapping[str, Any], *, attempt: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _TICK_FIELDS:
        raise V32OutcomeTickError("V32_TICK_OBSERVATION_SCHEMA_INVALID")
    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    if (
        document.get("run_id") != attempt.get("run_id")
        or document.get("tick_index") != attempt.get("tick_index")
        or document.get("tick_id") != attempt.get("tick_id")
        or document.get("attempt_digest") != attempt_digest
        or document.get("source_request_id") != attempt.get("source_request_id")
    ):
        raise V32OutcomeTickError("V32_TICK_OBSERVATION_ATTEMPT_MISMATCH")
    try:
        supplied = verify_self_digest(document, OBSERVATION_TICK_DIGEST_FIELD)
        rebuilt = build_v32_outcome_observation_tick(
            attempt=attempt,
            raw_evidence_binding=document["raw_evidence_binding"],
            normalized_at=document["normalized_at"],
            status=document["status"],
            value=document["value"],
            provider_as_of=document["provider_as_of"],
            available_at=document["available_at"],
            quality=document["quality"],
            missingness=document["missingness"],
            conflict_state=document["conflict_state"],
            parser_receipt_digest=document["parser_receipt_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickError):
            raise
        raise V32OutcomeTickError("V32_TICK_OBSERVATION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[OBSERVATION_TICK_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_TICK_OBSERVATION_RECONSTRUCTION_MISMATCH")
    _assert_boundary(document, "V32_TICK_OBSERVATION_AUTHORITY_INVALID")
    return supplied


def _flatten_schedules(
    schedule_sets: Sequence[Mapping[str, Any]], *, run_id: str
) -> tuple[dict[str, tuple[dict[str, Any], str]], list[str]]:
    if isinstance(schedule_sets, (str, bytes)) or not isinstance(
        schedule_sets, Sequence
    ):
        raise V32OutcomeTickError("V32_BATCH_SCHEDULE_SETS_INVALID")
    schedule_map: dict[str, tuple[dict[str, Any], str]] = {}
    set_digests: list[str] = []
    for schedule_set in schedule_sets:
        set_digest = verify_v32_outcome_schedule_set(schedule_set)
        if schedule_set.get("run_id") != run_id:
            raise V32OutcomeTickError("V32_BATCH_RUN_MISMATCH")
        set_digests.append(set_digest)
        for raw_row in schedule_set["schedules"]:
            row = dict(raw_row)
            schedule_id = row["schedule_id"]
            if schedule_id in schedule_map:
                raise V32OutcomeTickError("V32_BATCH_DUPLICATE_SCHEDULE")
            schedule_map[schedule_id] = (row, set_digest)
    return schedule_map, sorted(set_digests)


def _validate_receipt_intrinsic(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, OUTCOME_RECEIPT_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_DIGEST_INVALID") from exc
    _assert_boundary(document, "V32_OUTCOME_RECEIPT_AUTHORITY_INVALID")
    if (
        document.get("schema_id") != OUTCOME_RECEIPT_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("terminal") is not True
        or document.get("attempt_count") != 1
        or document.get("retry_allowed") is not False
        or document.get("shared_tick_request") is not True
        or document.get("trigger_is_fill") is not False
        or document.get("fill_claim") is not False
        or document.get("position_claim") is not False
        or document.get("pnl_claim") is not False
        or document.get("observation_scope")
        != "PUBLIC_MARKET_PATH_ONLY_NO_EXECUTION_STATE"
        or document.get("stop_trigger_semantics")
        != "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL"
    ):
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_BOUNDARY_INVALID")
    _text(document.get("run_id"), "V32_OUTCOME_RECEIPT_RUN_ID_INVALID")
    _text(document.get("schedule_id"), "V32_OUTCOME_RECEIPT_SCHEDULE_ID_INVALID")
    _text(document.get("decision_id"), "V32_OUTCOME_RECEIPT_DECISION_ID_INVALID")
    _positive_int(
        document.get("cycle_index"), "V32_OUTCOME_RECEIPT_CYCLE_INDEX_INVALID"
    )
    for field in (
        "schedule_digest",
        "schedule_set_digest",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
    ):
        _digest(document.get(field), "V32_OUTCOME_RECEIPT_BINDING_INVALID")
    if document.get("horizon") not in {item[0] for item in HORIZON_POLICY}:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_HORIZON_INVALID")
    not_before = _moment(
        document.get("outcome_not_before"), "V32_OUTCOME_RECEIPT_TIME_INVALID"
    )
    available = _moment(
        document.get("available_at"), "V32_OUTCOME_RECEIPT_TIME_INVALID"
    )
    resolved = _moment(
        document.get("resolved_at"), "V32_OUTCOME_RECEIPT_TIME_INVALID"
    )
    if not_before > resolved or available > resolved:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_TIME_INVALID")
    status = document.get("resolution_status")
    if (
        document.get("observable_ref") != OBSERVABLE_REF
        or document.get("source_scope") != SOURCE_SCOPE
    ):
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_OBSERVABLE_INVALID")
    if status == "OBSERVED_PUBLIC_MARK":
        _decimal_text(
            document.get("value"), "V32_OUTCOME_RECEIPT_VALUE_INVALID", positive=True
        )
        provider = _moment(
            document.get("provider_as_of"), "V32_OUTCOME_RECEIPT_TIME_INVALID"
        )
        required_quality = _provider_clock_quality(
            provider=provider,
            available=available,
            code="V32_OUTCOME_RECEIPT_TIME_INVALID",
        )
        if (
            document.get("quality") != required_quality
            or document.get("missingness") != "OBSERVED"
            or document.get("coverage_loss_reason") is not None
        ):
            raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_OBSERVED_INVALID")
    elif status == "UNKNOWN_COVERAGE_LOSS":
        if (
            document.get("value") is not None
            or document.get("provider_as_of") is not None
            or document.get("quality") != "UNKNOWN"
            or document.get("missingness") != "UNKNOWN"
            or not isinstance(document.get("coverage_loss_reason"), str)
            or not document.get("coverage_loss_reason")
        ):
            raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_UNKNOWN_INVALID")
    else:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_STATUS_INVALID")
    return supplied


def _validate_terminal_receipt_intrinsic(
    document: Mapping[str, Any],
) -> tuple[str, str, str]:
    """Validate one durable terminal receipt without conflating its evidence mode.

    The legacy receipt remains strict and observation-backed.  The only
    successor accepted here is the zero-network expiry receipt; it contributes
    terminal schedule identity but never a market value or observation tick.
    """

    if document.get("schema_id") == OUTCOME_RECEIPT_SCHEMA_ID:
        return (
            _validate_receipt_intrinsic(document),
            OUTCOME_RECEIPT_DIGEST_FIELD,
            str(document["available_at"]),
        )
    # Lazy import avoids a module cycle: the aggregate expiry contract reuses
    # this module's fully verified schedule classifier.
    from .v32_outcome_window_expiry import (  # noqa: PLC0415
        EXPIRY_ROW_DIGEST_FIELD,
        EXPIRY_ROW_SCHEMA_ID,
        verify_v32_outcome_window_expiry_row,
    )

    if document.get("schema_id") != EXPIRY_ROW_SCHEMA_ID:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_SCHEMA_INVALID")
    return (
        verify_v32_outcome_window_expiry_row(document),
        EXPIRY_ROW_DIGEST_FIELD,
        str(document["resolved_at"]),
    )


def _prior_terminal_schedule_ids(
    receipts: Sequence[Mapping[str, Any]], *, run_id: str
) -> set[str]:
    if isinstance(receipts, (str, bytes)) or not isinstance(receipts, Sequence):
        raise V32OutcomeTickError("V32_BATCH_PRIOR_RECEIPTS_INVALID")
    seen: set[str] = set()
    for receipt in receipts:
        _validate_terminal_receipt_intrinsic(receipt)
        if receipt.get("run_id") != run_id:
            raise V32OutcomeTickError("V32_BATCH_RUN_MISMATCH")
        schedule_id = receipt.get("schedule_id")
        if not isinstance(schedule_id, str) or schedule_id in seen:
            raise V32OutcomeTickError("V32_BATCH_DUPLICATE_TERMINAL_RECEIPT")
        seen.add(schedule_id)
    return seen


def build_v32_outcome_resolution_batch_intent(
    *,
    attempt: Mapping[str, Any],
    observation_tick: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    created_at: str,
    prior_terminal_receipts: Sequence[Mapping[str, Any]] = (),
    prior_batch_intents: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Freeze every mature schedule resolved by one already captured tick."""

    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    tick_digest = verify_v32_outcome_observation_tick(
        observation_tick, attempt=attempt
    )
    run_id = attempt["run_id"]
    schedule_map, _ = _flatten_schedules(schedule_sets, run_id=run_id)
    terminal_ids = _prior_terminal_schedule_ids(
        prior_terminal_receipts, run_id=run_id
    )
    for receipt in prior_terminal_receipts:
        schedule_id = receipt["schedule_id"]
        if schedule_id not in schedule_map:
            raise V32OutcomeTickError("V32_BATCH_PRIOR_RECEIPT_SCHEDULE_UNKNOWN")
        schedule, set_digest = schedule_map[schedule_id]
        if (
            receipt.get("schedule_digest") != schedule["schedule_digest"]
            or receipt.get("schedule_set_digest") != set_digest
            or receipt.get("decision_id") != schedule["decision_id"]
            or receipt.get("cycle_index") != schedule["cycle_index"]
            or receipt.get("horizon") != schedule["horizon"]
        ):
            raise V32OutcomeTickError("V32_BATCH_PRIOR_RECEIPT_BINDING_MISMATCH")
    prior_reserved: set[str] = set()
    if isinstance(prior_batch_intents, (str, bytes)) or not isinstance(
        prior_batch_intents, Sequence
    ):
        raise V32OutcomeTickError("V32_BATCH_PRIOR_INTENTS_INVALID")
    for prior in prior_batch_intents:
        _validate_batch_intent_intrinsic(prior)
        if prior.get("run_id") != run_id:
            raise V32OutcomeTickError("V32_BATCH_RUN_MISMATCH")
        overlap = prior_reserved.intersection(prior["due_schedule_ids"])
        if overlap:
            raise V32OutcomeTickError("V32_BATCH_SCHEDULE_ATTEMPT_DUPLICATE")
        prior_reserved.update(prior["due_schedule_ids"])

    created = _moment(created_at, "V32_BATCH_CREATED_AT_INVALID")
    normalized = _moment(
        observation_tick["normalized_at"], "V32_TICK_NORMALIZED_AT_INVALID"
    )
    if created < normalized:
        raise V32OutcomeTickError("V32_BATCH_TIME_ORDER_INVALID")

    future_ids: list[str] = []
    dispositions: list[dict[str, Any]] = []
    for schedule_id, (schedule, set_digest) in schedule_map.items():
        if schedule_id in terminal_ids:
            continue
        timing_state = classify_v32_outcome_schedule_time(
            schedule,
            now=observation_tick["raw_evidence_binding"]["recorded_at"],
        )
        if timing_state == "FUTURE":
            future_ids.append(schedule_id)
            continue
        if schedule_id in prior_reserved:
            raise V32OutcomeTickError("V32_BATCH_SCHEDULE_ATTEMPT_DUPLICATE")
        overdue = timing_state == "EXPIRED"
        observed = observation_tick["status"] == "OBSERVED_PUBLIC_MARK"
        if overdue:
            timing_class = "OVERDUE_AFTER_GRACE"
            status = "UNKNOWN_COVERAGE_LOSS"
            readable = False
            reason = "OBSERVATION_WINDOW_MISSED"
        elif observed:
            timing_class = "DUE_WITHIN_GRACE"
            status = "OBSERVED_PUBLIC_MARK"
            readable = True
            reason = None
        else:
            timing_class = "DUE_WITHIN_GRACE"
            status = "UNKNOWN_COVERAGE_LOSS"
            readable = False
            reason = observation_tick["conflict_state"]
        dispositions.append(
            {
                "schedule_id": schedule_id,
                "schedule_digest": schedule["schedule_digest"],
                "schedule_set_digest": set_digest,
                "horizon": schedule["horizon"],
                "outcome_not_before": schedule["outcome_not_before"],
                "expires_at": schedule["expires_at"],
                "timing_class": timing_class,
                "resolution_status": status,
                "value_read_allowed": readable,
                "coverage_loss_reason": reason,
            }
        )
    dispositions.sort(key=lambda row: row["schedule_id"])
    if not dispositions:
        raise V32OutcomeTickError("V32_BATCH_NO_MATURE_SCHEDULES")
    due_ids = [row["schedule_id"] for row in dispositions]
    batch_id = canonical_digest(
        {
            "schema_id": "theory_paper_v32_outcome_batch_identity_v1",
            "run_id": run_id,
            "observation_tick_digest": tick_digest,
            "due_schedule_ids": due_ids,
        }
    )
    return self_digest(
        {
            "schema_id": BATCH_INTENT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "batch_id": batch_id,
            "created_at": _time(created_at, "V32_BATCH_CREATED_AT_INVALID"),
            "tick_attempt_digest": attempt_digest,
            "observation_tick_digest": tick_digest,
            "raw_evidence_digest": observation_tick["raw_evidence_binding"][
                "semantic_digest"
            ],
            "due_schedule_ids": due_ids,
            "future_schedule_ids": sorted(future_ids),
            "preexisting_terminal_schedule_ids": sorted(terminal_ids),
            "outcome_dispositions": dispositions,
            "same_tick_shared_capture": True,
            "network_request_allowed_during_tail": False,
            "recovery_policy": (
                "SAME_ATTEMPT_SAME_RAW_DETERMINISTIC_TAIL_NO_SECOND_GET"
            ),
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        BATCH_INTENT_DIGEST_FIELD,
    )


def _validate_batch_intent_intrinsic(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _BATCH_INTENT_FIELDS:
        raise V32OutcomeTickError("V32_BATCH_INTENT_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, BATCH_INTENT_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32OutcomeTickError("V32_BATCH_INTENT_DIGEST_INVALID") from exc
    _assert_boundary(document, "V32_BATCH_INTENT_AUTHORITY_INVALID")
    if (
        document.get("schema_id") != BATCH_INTENT_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("same_tick_shared_capture") is not True
        or document.get("network_request_allowed_during_tail") is not False
        or document.get("recovery_policy")
        != "SAME_ATTEMPT_SAME_RAW_DETERMINISTIC_TAIL_NO_SECOND_GET"
    ):
        raise V32OutcomeTickError("V32_BATCH_INTENT_POLICY_INVALID")
    _text(document.get("run_id"), "V32_BATCH_RUN_ID_INVALID")
    _time(document.get("created_at"), "V32_BATCH_CREATED_AT_INVALID")
    for field in (
        "tick_attempt_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
    ):
        _digest(document.get(field), "V32_BATCH_BINDING_INVALID")
    due = _sorted_unique_strings(
        document.get("due_schedule_ids"),
        "V32_BATCH_DUE_SCHEDULES_INVALID",
        allow_empty=False,
    )
    future = _sorted_unique_strings(
        document.get("future_schedule_ids"), "V32_BATCH_FUTURE_SCHEDULES_INVALID"
    )
    prior = _sorted_unique_strings(
        document.get("preexisting_terminal_schedule_ids"),
        "V32_BATCH_TERMINAL_SCHEDULES_INVALID",
    )
    if set(due) & (set(future) | set(prior)) or set(future) & set(prior):
        raise V32OutcomeTickError("V32_BATCH_SCHEDULE_PARTITION_INVALID")
    dispositions = document.get("outcome_dispositions")
    if isinstance(dispositions, (str, bytes)) or not isinstance(
        dispositions, Sequence
    ):
        raise V32OutcomeTickError("V32_BATCH_DISPOSITIONS_INVALID")
    if any(
        not isinstance(row, Mapping) or set(row) != _DISPOSITION_FIELDS
        for row in dispositions
    ):
        raise V32OutcomeTickError("V32_BATCH_DISPOSITIONS_INVALID")
    if [row["schedule_id"] for row in dispositions] != due:
        raise V32OutcomeTickError("V32_BATCH_DISPOSITION_SET_INVALID")
    expected_batch_id = canonical_digest(
        {
            "schema_id": "theory_paper_v32_outcome_batch_identity_v1",
            "run_id": document["run_id"],
            "observation_tick_digest": document["observation_tick_digest"],
            "due_schedule_ids": due,
        }
    )
    if document.get("batch_id") != expected_batch_id:
        raise V32OutcomeTickError("V32_BATCH_IDENTITY_INVALID")
    for row in dispositions:
        for field in ("schedule_id", "horizon"):
            _text(row.get(field), "V32_BATCH_DISPOSITION_INVALID")
        for field in (
            "schedule_digest",
            "schedule_set_digest",
        ):
            _digest(row.get(field), "V32_BATCH_DISPOSITION_INVALID")
        not_before = _moment(
            row.get("outcome_not_before"), "V32_BATCH_DISPOSITION_TIME_INVALID"
        )
        expires = _moment(
            row.get("expires_at"), "V32_BATCH_DISPOSITION_TIME_INVALID"
        )
        if expires - not_before != timedelta(seconds=OUTCOME_GRACE_SECONDS):
            raise V32OutcomeTickError("V32_BATCH_DISPOSITION_TIME_INVALID")
        timing = row.get("timing_class")
        status = row.get("resolution_status")
        readable = row.get("value_read_allowed")
        reason = row.get("coverage_loss_reason")
        if timing == "OVERDUE_AFTER_GRACE":
            valid = (
                status == "UNKNOWN_COVERAGE_LOSS"
                and readable is False
                and reason == "OBSERVATION_WINDOW_MISSED"
            )
        elif timing == "DUE_WITHIN_GRACE" and status == "OBSERVED_PUBLIC_MARK":
            valid = readable is True and reason is None
        elif timing == "DUE_WITHIN_GRACE" and status == "UNKNOWN_COVERAGE_LOSS":
            valid = readable is False and reason in COVERAGE_FAILURE_CODES
        else:
            valid = False
        if not valid:
            raise V32OutcomeTickError("V32_BATCH_DISPOSITION_INVALID")
    return supplied


def verify_v32_outcome_resolution_batch_intent(
    document: Mapping[str, Any],
    *,
    attempt: Mapping[str, Any],
    observation_tick: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    prior_terminal_receipts: Sequence[Mapping[str, Any]] = (),
    prior_batch_intents: Sequence[Mapping[str, Any]] = (),
) -> str:
    supplied = _validate_batch_intent_intrinsic(document)
    rebuilt = build_v32_outcome_resolution_batch_intent(
        attempt=attempt,
        observation_tick=observation_tick,
        schedule_sets=schedule_sets,
        created_at=document["created_at"],
        prior_terminal_receipts=prior_terminal_receipts,
        prior_batch_intents=prior_batch_intents,
    )
    if dict(document) != rebuilt or supplied != rebuilt[BATCH_INTENT_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_BATCH_INTENT_RECONSTRUCTION_MISMATCH")
    return supplied


def _schedule_from_sets(
    *,
    schedule_sets: Sequence[Mapping[str, Any]],
    run_id: str,
    schedule_id: str,
) -> tuple[dict[str, Any], str]:
    schedule_map, _ = _flatten_schedules(schedule_sets, run_id=run_id)
    try:
        return schedule_map[schedule_id]
    except KeyError as exc:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_SCHEDULE_UNKNOWN") from exc


def build_v32_public_market_outcome_receipt(
    *,
    batch_intent: Mapping[str, Any],
    attempt: Mapping[str, Any],
    observation_tick: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    schedule_id: str,
    resolved_at: str,
) -> dict[str, Any]:
    """Resolve one scheduled public-market path without inventing a fill."""

    batch_digest = _validate_batch_intent_intrinsic(batch_intent)
    tick_digest = verify_v32_outcome_observation_tick(
        observation_tick, attempt=attempt
    )
    if (
        batch_intent.get("run_id") != attempt.get("run_id")
        or batch_intent.get("tick_attempt_digest")
        != attempt.get(TICK_ATTEMPT_DIGEST_FIELD)
        or batch_intent.get("observation_tick_digest") != tick_digest
        or batch_intent.get("raw_evidence_digest")
        != observation_tick["raw_evidence_binding"]["semantic_digest"]
    ):
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_BATCH_TICK_MISMATCH")
    schedule_key = _text(schedule_id, "V32_OUTCOME_RECEIPT_SCHEDULE_ID_INVALID")
    disposition_map = {
        row["schedule_id"]: row for row in batch_intent["outcome_dispositions"]
    }
    if schedule_key not in disposition_map:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_SCHEDULE_NOT_RESERVED")
    schedule, set_digest = _schedule_from_sets(
        schedule_sets=schedule_sets,
        run_id=attempt["run_id"],
        schedule_id=schedule_key,
    )
    disposition = disposition_map[schedule_key]
    if (
        disposition["schedule_digest"] != schedule["schedule_digest"]
        or disposition["schedule_set_digest"] != set_digest
    ):
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_SCHEDULE_BINDING_MISMATCH")
    resolved = _moment(resolved_at, "V32_OUTCOME_RECEIPT_TIME_INVALID")
    if resolved < _moment(batch_intent["created_at"], "V32_BATCH_CREATED_AT_INVALID"):
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_TIME_INVALID")
    observed = disposition["resolution_status"] == "OBSERVED_PUBLIC_MARK"
    if observed != bool(disposition["value_read_allowed"]):
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_VALUE_POLICY_INVALID")
    return self_digest(
        {
            "schema_id": OUTCOME_RECEIPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": attempt["run_id"],
            "schedule_id": schedule_key,
            "schedule_digest": schedule["schedule_digest"],
            "schedule_set_digest": set_digest,
            "decision_id": schedule["decision_id"],
            "cycle_index": schedule["cycle_index"],
            "horizon": schedule["horizon"],
            "outcome_not_before": schedule["outcome_not_before"],
            "batch_intent_digest": batch_digest,
            "observation_tick_digest": tick_digest,
            "raw_evidence_digest": batch_intent["raw_evidence_digest"],
            "resolved_at": _time(resolved_at, "V32_OUTCOME_RECEIPT_TIME_INVALID"),
            "resolution_status": disposition["resolution_status"],
            "coverage_loss_reason": disposition["coverage_loss_reason"],
            "observable_ref": OBSERVABLE_REF,
            "value": observation_tick["value"] if observed else None,
            "provider_as_of": observation_tick["provider_as_of"] if observed else None,
            "available_at": observation_tick["available_at"],
            "quality": observation_tick["quality"] if observed else "UNKNOWN",
            "missingness": observation_tick["missingness"] if observed else "UNKNOWN",
            "terminal": True,
            "attempt_count": 1,
            "retry_allowed": False,
            "shared_tick_request": True,
            "observation_scope": "PUBLIC_MARKET_PATH_ONLY_NO_EXECUTION_STATE",
            "stop_trigger_semantics": (
                "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL"
            ),
            "trigger_is_fill": False,
            "fill_claim": False,
            "position_claim": False,
            "pnl_claim": False,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        OUTCOME_RECEIPT_DIGEST_FIELD,
    )


def verify_v32_public_market_outcome_receipt(
    document: Mapping[str, Any],
    *,
    batch_intent: Mapping[str, Any],
    attempt: Mapping[str, Any],
    observation_tick: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
) -> str:
    supplied = _validate_receipt_intrinsic(document)
    rebuilt = build_v32_public_market_outcome_receipt(
        batch_intent=batch_intent,
        attempt=attempt,
        observation_tick=observation_tick,
        schedule_sets=schedule_sets,
        schedule_id=document["schedule_id"],
        resolved_at=document["resolved_at"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[OUTCOME_RECEIPT_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_OUTCOME_RECEIPT_RECONSTRUCTION_MISMATCH")
    return supplied


def build_v32_outcome_resolution_batch(
    *,
    batch_intent: Mapping[str, Any],
    outcome_receipts: Sequence[Mapping[str, Any]],
    completed_at: str,
) -> dict[str, Any]:
    """Seal a complete deterministic tail; no external request is permitted."""

    intent_digest = _validate_batch_intent_intrinsic(batch_intent)
    if isinstance(outcome_receipts, (str, bytes)) or not isinstance(
        outcome_receipts, Sequence
    ):
        raise V32OutcomeTickError("V32_BATCH_RECEIPTS_INVALID")
    receipt_by_schedule: dict[str, str] = {}
    for receipt in outcome_receipts:
        digest = _validate_receipt_intrinsic(receipt)
        if (
            receipt.get("run_id") != batch_intent.get("run_id")
            or receipt.get("batch_intent_digest") != intent_digest
            or receipt.get("observation_tick_digest")
            != batch_intent.get("observation_tick_digest")
            or receipt.get("raw_evidence_digest")
            != batch_intent.get("raw_evidence_digest")
        ):
            raise V32OutcomeTickError("V32_BATCH_RECEIPT_BINDING_MISMATCH")
        schedule_id = receipt["schedule_id"]
        if schedule_id in receipt_by_schedule:
            raise V32OutcomeTickError("V32_BATCH_RECEIPT_DUPLICATE")
        receipt_by_schedule[schedule_id] = digest
    due_ids = list(batch_intent["due_schedule_ids"])
    if set(receipt_by_schedule) != set(due_ids):
        raise V32OutcomeTickError("V32_BATCH_RECEIPT_SET_INCOMPLETE")
    completed = _moment(completed_at, "V32_BATCH_COMPLETED_AT_INVALID")
    if completed < _moment(batch_intent["created_at"], "V32_BATCH_CREATED_AT_INVALID"):
        raise V32OutcomeTickError("V32_BATCH_COMPLETED_AT_INVALID")
    return self_digest(
        {
            "schema_id": BATCH_COMPLETION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": batch_intent["run_id"],
            "batch_id": batch_intent["batch_id"],
            "batch_intent_digest": intent_digest,
            "observation_tick_digest": batch_intent["observation_tick_digest"],
            "raw_evidence_digest": batch_intent["raw_evidence_digest"],
            "completed_at": _time(completed_at, "V32_BATCH_COMPLETED_AT_INVALID"),
            "resolved_schedule_ids": sorted(receipt_by_schedule),
            "outcome_receipt_digests": [
                receipt_by_schedule[schedule_id]
                for schedule_id in sorted(receipt_by_schedule)
            ],
            "network_requests_during_tail": 0,
            "all_due_schedules_terminal": True,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        BATCH_COMPLETION_DIGEST_FIELD,
    )


def verify_v32_outcome_resolution_batch(
    document: Mapping[str, Any],
    *,
    batch_intent: Mapping[str, Any],
    outcome_receipts: Sequence[Mapping[str, Any]],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _COMPLETION_FIELDS:
        raise V32OutcomeTickError("V32_BATCH_COMPLETION_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, BATCH_COMPLETION_DIGEST_FIELD)
        rebuilt = build_v32_outcome_resolution_batch(
            batch_intent=batch_intent,
            outcome_receipts=outcome_receipts,
            completed_at=document["completed_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickError):
            raise
        raise V32OutcomeTickError("V32_BATCH_COMPLETION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[BATCH_COMPLETION_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_BATCH_COMPLETION_RECONSTRUCTION_MISMATCH")
    _assert_boundary(document, "V32_BATCH_COMPLETION_AUTHORITY_INVALID")
    return supplied


def build_v32_analysis_clock_view(
    *,
    run_id: str,
    cycle_index: int,
    decision_time: str,
    schedule_sets: Sequence[Mapping[str, Any]],
    terminal_outcome_receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose only already mature receipts to a new independent analysis cycle."""

    run = _text(run_id, "V32_ANALYSIS_CLOCK_RUN_ID_INVALID")
    cycle = _positive_int(cycle_index, "V32_ANALYSIS_CLOCK_CYCLE_INVALID")
    decision = _moment(decision_time, "V32_ANALYSIS_CLOCK_TIME_INVALID")
    schedule_map, _ = _flatten_schedules(schedule_sets, run_id=run)
    receipt_by_schedule: dict[str, Mapping[str, Any]] = {}
    receipt_digests: dict[str, str] = {}
    for receipt in terminal_outcome_receipts:
        digest, _, available_at = _validate_terminal_receipt_intrinsic(receipt)
        schedule_id = receipt["schedule_id"]
        if receipt.get("run_id") != run or schedule_id not in schedule_map:
            raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_RECEIPT_IDENTITY_INVALID")
        schedule, schedule_set_digest = schedule_map[schedule_id]
        if receipt.get("schema_id") != OUTCOME_RECEIPT_SCHEMA_ID and (
            receipt.get("schedule_digest") != schedule["schedule_digest"]
            or receipt.get("schedule_set_digest") != schedule_set_digest
        ):
            raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_RECEIPT_IDENTITY_INVALID")
        if schedule_id in receipt_by_schedule:
            raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_DUPLICATE_RECEIPT")
        if (
            _moment(available_at, "V32_ANALYSIS_CLOCK_TIME_INVALID")
            > decision
            or _moment(receipt["resolved_at"], "V32_ANALYSIS_CLOCK_TIME_INVALID")
            > decision
        ):
            raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_FUTURE_RECEIPT_FORBIDDEN")
        if not digest:
            raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_RECEIPT_INVALID")
        receipt_by_schedule[schedule_id] = receipt
        receipt_digests[schedule_id] = digest
    mature_terminal: list[str] = []
    mature_unresolved: list[str] = []
    future: list[str] = []
    for schedule_id, (schedule, _) in schedule_map.items():
        timing_state = classify_v32_outcome_schedule_time(
            schedule, now=decision_time
        )
        if timing_state == "FUTURE":
            if schedule_id in receipt_by_schedule:
                raise V32OutcomeTickError(
                    "V32_ANALYSIS_CLOCK_FUTURE_RECEIPT_FORBIDDEN"
                )
            future.append(schedule_id)
        elif schedule_id in receipt_by_schedule:
            mature_terminal.append(schedule_id)
        else:
            mature_unresolved.append(schedule_id)
    allowed = not mature_unresolved
    available_digests = sorted(
        receipt_digests[schedule_id] for schedule_id in mature_terminal
    )
    return self_digest(
        {
            "schema_id": ANALYSIS_CLOCK_VIEW_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run,
            "cycle_index": cycle,
            "decision_time": _time(
                decision_time, "V32_ANALYSIS_CLOCK_TIME_INVALID"
            ),
            "mature_terminal_schedule_ids": sorted(mature_terminal),
            "mature_unresolved_schedule_ids": sorted(mature_unresolved),
            "future_schedule_ids": sorted(future),
            "available_outcome_receipt_digests": available_digests,
            "future_outcomes_readable": False,
            "future_outcomes_block_analysis": False,
            "analysis_allowed": allowed,
            "analysis_gate_reason": (
                "READY_FUTURE_OUTCOMES_NON_BLOCKING"
                if allowed
                else "DUE_OUTCOME_DETERMINISTIC_TAIL_REQUIRED_FIRST"
            ),
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        ANALYSIS_CLOCK_VIEW_DIGEST_FIELD,
    )


def verify_v32_analysis_clock_view(
    document: Mapping[str, Any],
    *,
    schedule_sets: Sequence[Mapping[str, Any]],
    terminal_outcome_receipts: Sequence[Mapping[str, Any]],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _CLOCK_VIEW_FIELDS:
        raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_VIEW_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, ANALYSIS_CLOCK_VIEW_DIGEST_FIELD)
        rebuilt = build_v32_analysis_clock_view(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            decision_time=document["decision_time"],
            schedule_sets=schedule_sets,
            terminal_outcome_receipts=terminal_outcome_receipts,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickError):
            raise
        raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_VIEW_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[ANALYSIS_CLOCK_VIEW_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_ANALYSIS_CLOCK_VIEW_RECONSTRUCTION_MISMATCH")
    _assert_boundary(document, "V32_ANALYSIS_CLOCK_VIEW_AUTHORITY_INVALID")
    return supplied


def build_v32_outcome_tail_recovery(
    *,
    attempt: Mapping[str, Any],
    observation_tick: Mapping[str, Any] | None,
    batch_intent: Mapping[str, Any] | None,
    outcome_receipts: Sequence[Mapping[str, Any]] = (),
    batch_completion: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe the only legal post-crash continuation without side effects."""

    attempt_digest = verify_v32_outcome_tick_attempt(attempt)
    run_id = attempt["run_id"]
    tick_digest: str | None = None
    raw_digest: str | None = None
    intent_digest: str | None = None
    completion_digest: str | None = None
    receipt_digests: list[str] = []
    missing: list[str] = []

    if observation_tick is None:
        if batch_intent is not None or outcome_receipts or batch_completion is not None:
            raise V32OutcomeTickError("V32_RECOVERY_PREFIX_INVALID")
        state = "FAILED_CLOSED_ATTEMPT_RESERVED_RAW_NOT_BOUND"
    else:
        tick_digest = verify_v32_outcome_observation_tick(
            observation_tick, attempt=attempt
        )
        raw_digest = observation_tick["raw_evidence_binding"]["semantic_digest"]
        if batch_intent is None:
            if outcome_receipts or batch_completion is not None:
                raise V32OutcomeTickError("V32_RECOVERY_PREFIX_INVALID")
            state = "BUILD_BATCH_INTENT_FROM_SAME_BOUND_TICK"
        else:
            intent_digest = _validate_batch_intent_intrinsic(batch_intent)
            if (
                batch_intent.get("run_id") != run_id
                or batch_intent.get("tick_attempt_digest") != attempt_digest
                or batch_intent.get("observation_tick_digest") != tick_digest
                or batch_intent.get("raw_evidence_digest") != raw_digest
            ):
                raise V32OutcomeTickError("V32_RECOVERY_PREFIX_BINDING_MISMATCH")
            receipt_by_schedule: dict[str, str] = {}
            for receipt in outcome_receipts:
                digest = _validate_receipt_intrinsic(receipt)
                if (
                    receipt.get("run_id") != run_id
                    or receipt.get("batch_intent_digest") != intent_digest
                    or receipt.get("observation_tick_digest") != tick_digest
                    or receipt.get("raw_evidence_digest") != raw_digest
                    or receipt["schedule_id"] in receipt_by_schedule
                ):
                    raise V32OutcomeTickError("V32_RECOVERY_RECEIPT_PREFIX_INVALID")
                receipt_by_schedule[receipt["schedule_id"]] = digest
            if not set(receipt_by_schedule).issubset(batch_intent["due_schedule_ids"]):
                raise V32OutcomeTickError("V32_RECOVERY_RECEIPT_PREFIX_INVALID")
            receipt_digests = [
                receipt_by_schedule[key] for key in sorted(receipt_by_schedule)
            ]
            missing = sorted(
                set(batch_intent["due_schedule_ids"]) - set(receipt_by_schedule)
            )
            if batch_completion is None:
                state = "BUILD_MISSING_RECEIPTS" if missing else "SEAL_BATCH_COMPLETION"
            else:
                if missing:
                    raise V32OutcomeTickError("V32_RECOVERY_COMPLETION_PREMATURE")
                completion_digest = verify_v32_outcome_resolution_batch(
                    batch_completion,
                    batch_intent=batch_intent,
                    outcome_receipts=outcome_receipts,
                )
                state = "NOOP_TERMINAL_COMPLETE"
    return self_digest(
        {
            "schema_id": RECOVERY_DIRECTIVE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "tick_attempt_digest": attempt_digest,
            "observation_tick_digest": tick_digest,
            "raw_evidence_digest": raw_digest,
            "batch_intent_digest": intent_digest,
            "existing_outcome_receipt_digests": receipt_digests,
            "batch_completion_digest": completion_digest,
            "recovery_state": state,
            "missing_schedule_ids": missing,
            "network_request_allowed": False,
            "same_attempt_required": True,
            "same_raw_evidence_required": observation_tick is not None,
            "deterministic_tail_only": True,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        RECOVERY_DIRECTIVE_DIGEST_FIELD,
    )


def verify_v32_outcome_tail_recovery(
    document: Mapping[str, Any],
    *,
    attempt: Mapping[str, Any],
    observation_tick: Mapping[str, Any] | None,
    batch_intent: Mapping[str, Any] | None,
    outcome_receipts: Sequence[Mapping[str, Any]] = (),
    batch_completion: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _RECOVERY_FIELDS:
        raise V32OutcomeTickError("V32_RECOVERY_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, RECOVERY_DIRECTIVE_DIGEST_FIELD)
        rebuilt = build_v32_outcome_tail_recovery(
            attempt=attempt,
            observation_tick=observation_tick,
            batch_intent=batch_intent,
            outcome_receipts=outcome_receipts,
            batch_completion=batch_completion,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32OutcomeTickError):
            raise
        raise V32OutcomeTickError("V32_RECOVERY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[RECOVERY_DIRECTIVE_DIGEST_FIELD]:
        raise V32OutcomeTickError("V32_RECOVERY_RECONSTRUCTION_MISMATCH")
    _assert_boundary(document, "V32_RECOVERY_AUTHORITY_INVALID")
    return supplied


__all__ = [
    "ANALYSIS_CLOCK_VIEW_DIGEST_FIELD",
    "BATCH_COMPLETION_DIGEST_FIELD",
    "BATCH_INTENT_DIGEST_FIELD",
    "HORIZON_POLICY",
    "OBSERVATION_TICK_DIGEST_FIELD",
    "OUTCOME_RECEIPT_DIGEST_FIELD",
    "RECOVERY_DIRECTIVE_DIGEST_FIELD",
    "SCHEDULE_SET_DIGEST_FIELD",
    "TICK_ATTEMPT_DIGEST_FIELD",
    "V32OutcomeTickError",
    "V32PublicTransportUnavailableError",
    "classify_v32_outcome_schedule_time",
    "build_v32_analysis_clock_view",
    "build_v32_outcome_observation_tick",
    "build_v32_outcome_resolution_batch",
    "build_v32_outcome_resolution_batch_intent",
    "build_v32_outcome_schedule_set",
    "build_v32_outcome_tail_recovery",
    "build_v32_outcome_tick_attempt",
    "build_v32_public_market_outcome_receipt",
    "verify_v32_analysis_clock_view",
    "verify_v32_outcome_observation_tick",
    "verify_v32_outcome_resolution_batch",
    "verify_v32_outcome_resolution_batch_intent",
    "verify_v32_outcome_schedule_set",
    "verify_v32_outcome_schedule",
    "verify_v32_outcome_tail_recovery",
    "verify_v32_outcome_tick_attempt",
    "verify_v32_public_market_outcome_receipt",
]
