"""Pure V3.2 supervisor contracts for independent analysis and outcome ticks.

This module owns only deterministic state and permit invariants.  It has no
clock, filesystem, network, Agent, account, order, fill, portfolio, authority
loader, or automation capability.  The supervisor admits exactly one active
permit at a time, and that permit opens exactly one of two boundaries:
``ANALYSIS_TICK`` or ``OUTCOME_TICK``.

The analysis clock may advance while older outcomes are still in the future.
It may not advance past an outcome that is already mature unless that schedule
has a terminal public-market receipt, including a legal
``UNKNOWN_COVERAGE_LOSS`` receipt.  The final three-horizon outcomes continue
in an outcome-only tail after all sixteen analysis cycles are accepted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_digest, self_digest, verify_self_digest
from .governance.v32_experiment_contract import (
    TOTAL_ANALYSIS_CYCLES,
    TOTAL_OUTCOME_SCHEDULES,
)
from .v32_outcome_tick import (
    BATCH_COMPLETION_DIGEST_FIELD,
    BATCH_INTENT_DIGEST_FIELD,
    OUTCOME_RECEIPT_DIGEST_FIELD,
    SCHEDULE_SET_DIGEST_FIELD,
    TICK_ATTEMPT_DIGEST_FIELD,
    build_v32_analysis_clock_view,
    classify_v32_outcome_schedule_time,
    verify_v32_outcome_observation_tick,
    verify_v32_outcome_resolution_batch,
    verify_v32_outcome_resolution_batch_intent,
    verify_v32_outcome_schedule_set,
    verify_v32_outcome_tick_attempt,
    verify_v32_public_market_outcome_receipt,
)
from .v32_cycle_source_admission import (
    LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION,
    SOURCE_ADMISSION_SCHEMA_VERSION,
)
from .v32_outcome_window_expiry import (
    EXPIRY_TERMINAL_DIGEST_FIELD,
    verify_v32_outcome_window_expiry_terminal,
)


class V32TickSupervisorError(ValueError):
    """A V3.2 supervisor invariant failed closed."""


SCHEMA_VERSION = "1.0.0"

CHECKPOINT_SCHEMA_ID = "theory_paper_v32_tick_supervisor_checkpoint_v1"
CHECKPOINT_DIGEST_FIELD = "tick_supervisor_checkpoint_digest"
PERMIT_SCHEMA_ID = "theory_paper_v32_tick_supervisor_permit_v1"
EXPIRY_PERMIT_SCHEMA_ID = (
    "theory_paper_v32_tick_supervisor_outcome_window_expiry_permit_v1"
)
PERMIT_DIGEST_FIELD = "tick_supervisor_permit_digest"
FAILURE_SCHEMA_ID = "theory_paper_v32_tick_supervisor_failure_v1"
FAILURE_DIGEST_FIELD = "tick_supervisor_failure_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

TICK_KINDS = ("ANALYSIS_TICK", "OUTCOME_TICK", "OUTCOME_WINDOW_EXPIRY")
SUPERVISOR_STATUSES = (
    "READY",
    "ANALYSIS_TICK_OPEN",
    "OUTCOME_TICK_OPEN",
    "OUTCOME_ONLY_TAIL",
    "TERMINAL_COMPLETE",
    "FAILED_CLOSED",
)
LANES = (
    "AUTHORITY_LANE",
    "SOURCE_LANE",
    "ANALYSIS_LANE",
    "AGENT_LANE",
    "COMMIT_LANE",
    "OUTCOME_LANE",
    "AUTOMATION_LANE",
)

FAILURE_CODES_BY_LANE = {
    "AUTHORITY_LANE": (
        "AUTHORITY_OR_THEORY_DRIFT",
        "AUTHORITY_SCHEMA_OR_DIGEST_INVALID",
    ),
    "SOURCE_LANE": (
        "SOURCE_SCHEMA_OR_DIGEST_INVALID",
        "SOURCE_CLOCK_OR_PIT_INVALID",
        "SOURCE_STALE_AFTER_AGENT",
    ),
    "ANALYSIS_LANE": (
        "ANALYSIS_CLOCK_CONFLICT",
        "ANALYSIS_SCHEMA_OR_DIGEST_INVALID",
        "CACHE_OR_PRIOR_STATE_DRIFT",
        "CONCURRENT_PERMIT_CONFLICT",
        "WRONG_RUN_CYCLE_OR_COUNTER",
    ),
    "AGENT_LANE": (
        "AGENT_ATTEMPT_DUPLICATE",
        "AGENT_DELIVERY_OR_SCHEMA_INVALID",
    ),
    "COMMIT_LANE": (
        "COMMIT_SCHEMA_OR_DIGEST_INVALID",
        "COMMIT_STATE_CONFLICT",
    ),
    "OUTCOME_LANE": (
        "OUTCOME_ATTEMPT_DUPLICATE",
        "OUTCOME_CLOCK_CONFLICT",
        "OUTCOME_SCHEMA_OR_DIGEST_INVALID",
        "RAW_PARSE_BINDING_MISMATCH",
    ),
    "AUTOMATION_LANE": (
        "AUTOMATION_CONCURRENCY_CONFLICT",
        "AUTOMATION_SCOPE_OR_BINDING_INVALID",
    ),
}

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "experiment_contract_digest",
        "active_authority_digest",
        "revision",
        "predecessor_checkpoint_digest",
        "status",
        "total_analysis_cycles",
        "total_outcome_schedules",
        "accepted_analysis_cycles",
        "scheduled_outcomes",
        "terminal_outcomes",
        "next_analysis_cycle_index",
        "next_outcome_tick_index",
        "accepted_state_digests",
        "shadow_decision_bundle_digests",
        "outcome_schedule_set_digests",
        "scheduled_schedule_ids",
        "terminal_schedule_ids",
        "current_research_checkpoint_digest",
        "current_outcome_checkpoint_digest",
        "current_timeframe_cache_digest",
        "current_dynamic_state_digest",
        "last_analysis_decision_at",
        "last_source_admission_digest",
        "last_source_admission_physical_sha256",
        "last_proposal_lifecycle_digest",
        "last_selection_lifecycle_digest",
        "last_action_plan_digest",
        "last_commit_envelope_digest",
        "last_shadow_decision_bundle_digest",
        "analysis_completion_binding_digests",
        "last_outcome_batch_digest",
        "active_permit_kind",
        "active_permit_digest",
        "lane_states",
        "failure_lane",
        "failure_ref",
        "failure_digest",
        "resume_allowed",
        "created_at",
        "updated_at",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        CHECKPOINT_DIGEST_FIELD,
    }
)

_PERMIT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "permit_id",
        "permit_kind",
        "run_id",
        "analysis_cycle_index",
        "outcome_tick_index",
        "analysis_decision_at",
        "planned_outcome_tick_at",
        "issued_at",
        "supervisor_checkpoint_digest_before_permit",
        "experiment_contract_digest",
        "active_authority_digest",
        "research_checkpoint_digest",
        "outcome_checkpoint_digest",
        "timeframe_cache_digest",
        "prior_dynamic_state_digest",
        "prior_source_admission_digest",
        "prior_source_admission_physical_sha256",
        "outcome_schedule_set_digests",
        "scheduled_schedule_ids",
        "terminal_schedule_ids",
        "mature_terminal_schedule_ids",
        "due_schedule_ids",
        "due_schedule_digests",
        "future_schedule_ids",
        "tick_attempt_digest",
        "opened_lane",
        "single_state_change_boundary",
        "future_outcomes_readable",
        "future_outcomes_block_analysis",
        "agent_stage_attempt_limits",
        "source_collection_transactions_allowed",
        "network_requests_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        PERMIT_DIGEST_FIELD,
    }
)

_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "occurred_at",
        "failure_lane",
        "failure_code",
        "failure_summary",
        "failure_evidence_digest",
        "supervisor_checkpoint_digest_before_failure",
        "active_permit_digest",
        "accepted_analysis_cycles",
        "scheduled_outcomes",
        "terminal_outcomes",
        "coverage_loss_is_run_failure",
        "retry_allowed",
        "resume_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        FAILURE_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32TickSupervisorError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32TickSupervisorError(code)
    return value


def _counter(value: Any, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise V32TickSupervisorError(code)
    return value


def _positive(value: Any, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise V32TickSupervisorError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32TickSupervisorError(code) from exc
    if parsed.tzinfo is None:
        raise V32TickSupervisorError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32TickSupervisorError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _digest_list(value: Any, code: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32TickSupervisorError(code)
    return [str(_digest(item, code)) for item in value]


def _sorted_unique_texts(value: Any, code: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32TickSupervisorError(code)
    result = [_text(item, code) for item in value]
    if result != sorted(result) or len(result) != len(set(result)):
        raise V32TickSupervisorError(code)
    return result


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "account_access": False,
        "order_submission": False,
        "fill_claim": False,
        "pnl_claim": False,
    }


def _assert_boundary(document: Mapping[str, Any], code: str) -> None:
    if any(document.get(key) != value for key, value in _boundary().items()):
        raise V32TickSupervisorError(code)


def _ready_lane_states(*, tail: bool = False, terminal: bool = False) -> dict[str, str]:
    if terminal:
        return {
            "AUTHORITY_LANE": "BOUND",
            "SOURCE_LANE": "COMPLETE",
            "ANALYSIS_LANE": "COMPLETE",
            "AGENT_LANE": "COMPLETE",
            "COMMIT_LANE": "COMPLETE",
            "OUTCOME_LANE": "COMPLETE",
            "AUTOMATION_LANE": "DISABLED",
        }
    return {
        "AUTHORITY_LANE": "BOUND",
        "SOURCE_LANE": "COMPLETE" if tail else "READY",
        "ANALYSIS_LANE": "COMPLETE" if tail else "READY",
        "AGENT_LANE": "COMPLETE" if tail else "READY",
        "COMMIT_LANE": "COMPLETE" if tail else "READY",
        "OUTCOME_LANE": "READY",
        "AUTOMATION_LANE": "DISABLED",
    }


def _lane_states(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(LANES):
        raise V32TickSupervisorError(code)
    allowed = {"BOUND", "READY", "ACTIVE", "COMPLETE", "DISABLED", "FAILED_CLOSED"}
    result = {lane: value[lane] for lane in LANES}
    if any(state not in allowed for state in result.values()):
        raise V32TickSupervisorError(code)
    return result


def _checkpoint_digest(document: Mapping[str, Any]) -> str:
    try:
        return verify_self_digest(document, CHECKPOINT_DIGEST_FIELD)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V32TickSupervisorError("V32_SUPERVISOR_CHECKPOINT_DIGEST_INVALID") from exc


def build_v32_tick_supervisor_checkpoint(
    *,
    run_id: str,
    experiment_contract_digest: str,
    active_authority_digest: str,
    research_checkpoint_digest: str,
    outcome_checkpoint_digest: str,
    timeframe_cache_digest: str,
    created_at: str,
) -> dict[str, Any]:
    """Create the zero-progress CAS root after external authority loading."""

    created = _time(created_at, "V32_SUPERVISOR_CREATED_AT_INVALID")
    document = {
        "schema_id": CHECKPOINT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": _text(run_id, "V32_SUPERVISOR_RUN_ID_INVALID"),
        "experiment_contract_digest": _digest(
            experiment_contract_digest, "V32_SUPERVISOR_CONTRACT_DIGEST_INVALID"
        ),
        "active_authority_digest": _digest(
            active_authority_digest, "V32_SUPERVISOR_AUTHORITY_DIGEST_INVALID"
        ),
        "revision": 0,
        "predecessor_checkpoint_digest": None,
        "status": "READY",
        "total_analysis_cycles": TOTAL_ANALYSIS_CYCLES,
        "total_outcome_schedules": TOTAL_OUTCOME_SCHEDULES,
        "accepted_analysis_cycles": 0,
        "scheduled_outcomes": 0,
        "terminal_outcomes": 0,
        "next_analysis_cycle_index": 1,
        "next_outcome_tick_index": 1,
        "accepted_state_digests": [],
        "shadow_decision_bundle_digests": [],
        "outcome_schedule_set_digests": [],
        "scheduled_schedule_ids": [],
        "terminal_schedule_ids": [],
        "current_research_checkpoint_digest": _digest(
            research_checkpoint_digest,
            "V32_SUPERVISOR_RESEARCH_CHECKPOINT_DIGEST_INVALID",
        ),
        "current_outcome_checkpoint_digest": _digest(
            outcome_checkpoint_digest,
            "V32_SUPERVISOR_OUTCOME_CHECKPOINT_DIGEST_INVALID",
        ),
        "current_timeframe_cache_digest": _digest(
            timeframe_cache_digest, "V32_SUPERVISOR_CACHE_DIGEST_INVALID"
        ),
        "current_dynamic_state_digest": None,
        "last_analysis_decision_at": None,
        "last_source_admission_digest": None,
        "last_source_admission_physical_sha256": None,
        "last_proposal_lifecycle_digest": None,
        "last_selection_lifecycle_digest": None,
        "last_action_plan_digest": None,
        "last_commit_envelope_digest": None,
        "last_shadow_decision_bundle_digest": None,
        "analysis_completion_binding_digests": [],
        "last_outcome_batch_digest": None,
        "active_permit_kind": None,
        "active_permit_digest": None,
        "lane_states": _ready_lane_states(),
        "failure_lane": None,
        "failure_ref": None,
        "failure_digest": None,
        "resume_allowed": True,
        "created_at": created,
        "updated_at": created,
        "chat_history_is_authority": False,
        **_boundary(),
    }
    result = self_digest(document, CHECKPOINT_DIGEST_FIELD)
    verify_v32_tick_supervisor_checkpoint(result)
    return result


def verify_v32_tick_supervisor_checkpoint(document: Mapping[str, Any]) -> str:
    """Validate exact counters, identities, lanes, and terminal semantics."""

    if not isinstance(document, Mapping) or set(document) != _CHECKPOINT_FIELDS:
        raise V32TickSupervisorError("V32_SUPERVISOR_CHECKPOINT_SCHEMA_INVALID")
    digest = _checkpoint_digest(document)
    if (
        document.get("schema_id") != CHECKPOINT_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("status") not in SUPERVISOR_STATUSES
        or document.get("total_analysis_cycles") != TOTAL_ANALYSIS_CYCLES
        or document.get("total_outcome_schedules") != TOTAL_OUTCOME_SCHEDULES
        or document.get("chat_history_is_authority") is not False
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_CHECKPOINT_SCHEMA_INVALID")
    _assert_boundary(document, "V32_SUPERVISOR_CHECKPOINT_BOUNDARY_INVALID")
    _text(document.get("run_id"), "V32_SUPERVISOR_RUN_ID_INVALID")
    for field in (
        "experiment_contract_digest",
        "active_authority_digest",
        "current_research_checkpoint_digest",
        "current_outcome_checkpoint_digest",
        "current_timeframe_cache_digest",
    ):
        _digest(document.get(field), "V32_SUPERVISOR_CHECKPOINT_BINDING_INVALID")
    revision = document.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise V32TickSupervisorError("V32_SUPERVISOR_REVISION_INVALID")
    predecessor = _digest(
        document.get("predecessor_checkpoint_digest"),
        "V32_SUPERVISOR_PREDECESSOR_INVALID",
        nullable=True,
    )
    if (revision == 0) != (predecessor is None):
        raise V32TickSupervisorError("V32_SUPERVISOR_PREDECESSOR_INVALID")
    if revision == 0 and document.get("status") != "READY":
        raise V32TickSupervisorError("V32_SUPERVISOR_GENESIS_STATUS_INVALID")
    created = _moment(document.get("created_at"), "V32_SUPERVISOR_TIME_INVALID")
    updated = _moment(document.get("updated_at"), "V32_SUPERVISOR_TIME_INVALID")
    if updated < created:
        raise V32TickSupervisorError("V32_SUPERVISOR_TIME_INVALID")

    accepted = _counter(
        document.get("accepted_analysis_cycles"),
        TOTAL_ANALYSIS_CYCLES,
        "V32_SUPERVISOR_ANALYSIS_COUNTER_INVALID",
    )
    scheduled = _counter(
        document.get("scheduled_outcomes"),
        TOTAL_OUTCOME_SCHEDULES,
        "V32_SUPERVISOR_SCHEDULE_COUNTER_INVALID",
    )
    terminal = _counter(
        document.get("terminal_outcomes"),
        TOTAL_OUTCOME_SCHEDULES,
        "V32_SUPERVISOR_OUTCOME_COUNTER_INVALID",
    )
    if scheduled != accepted * 3 or terminal > scheduled:
        raise V32TickSupervisorError("V32_SUPERVISOR_COUNTER_RELATION_INVALID")
    accepted_digests = _digest_list(
        document.get("accepted_state_digests"),
        "V32_SUPERVISOR_ACCEPTED_DIGESTS_INVALID",
    )
    shadow_digests = _digest_list(
        document.get("shadow_decision_bundle_digests"),
        "V32_SUPERVISOR_SHADOW_DECISION_DIGESTS_INVALID",
    )
    set_digests = _digest_list(
        document.get("outcome_schedule_set_digests"),
        "V32_SUPERVISOR_SCHEDULE_SET_DIGESTS_INVALID",
    )
    scheduled_ids = _sorted_unique_texts(
        document.get("scheduled_schedule_ids"),
        "V32_SUPERVISOR_SCHEDULE_IDS_INVALID",
    )
    terminal_ids = _sorted_unique_texts(
        document.get("terminal_schedule_ids"),
        "V32_SUPERVISOR_TERMINAL_IDS_INVALID",
    )
    if (
        len(accepted_digests) != accepted
        or len(shadow_digests) != accepted
        or len(set_digests) != accepted
        or len(set(accepted_digests)) != len(accepted_digests)
        or len(set(shadow_digests)) != len(shadow_digests)
        or len(set(set_digests)) != len(set_digests)
        or len(scheduled_ids) != scheduled
        or len(terminal_ids) != terminal
        or not set(terminal_ids).issubset(scheduled_ids)
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_IDENTITY_COUNTER_INVALID")
    dynamic = _digest(
        document.get("current_dynamic_state_digest"),
        "V32_SUPERVISOR_DYNAMIC_STATE_INVALID",
        nullable=True,
    )
    last_decision_value = document.get("last_analysis_decision_at")
    last_decision = (
        None
        if last_decision_value is None
        else _moment(last_decision_value, "V32_SUPERVISOR_LAST_DECISION_INVALID")
    )
    source_admission = _digest(
        document.get("last_source_admission_digest"),
        "V32_SUPERVISOR_SOURCE_ADMISSION_INVALID",
        nullable=True,
    )
    source_physical = _digest(
        document.get("last_source_admission_physical_sha256"),
        "V32_SUPERVISOR_SOURCE_ADMISSION_INVALID",
        nullable=True,
    )
    proposal_lifecycle = _digest(
        document.get("last_proposal_lifecycle_digest"),
        "V32_SUPERVISOR_PROPOSAL_LIFECYCLE_INVALID",
        nullable=True,
    )
    selection_lifecycle = _digest(
        document.get("last_selection_lifecycle_digest"),
        "V32_SUPERVISOR_SELECTION_LIFECYCLE_INVALID",
        nullable=True,
    )
    action_plan = _digest(
        document.get("last_action_plan_digest"),
        "V32_SUPERVISOR_ACTION_PLAN_INVALID",
        nullable=True,
    )
    last_commit = _digest(
        document.get("last_commit_envelope_digest"),
        "V32_SUPERVISOR_COMMIT_DIGEST_INVALID",
        nullable=True,
    )
    last_shadow = _digest(
        document.get("last_shadow_decision_bundle_digest"),
        "V32_SUPERVISOR_SHADOW_DECISION_DIGEST_INVALID",
        nullable=True,
    )
    completion_bindings = _digest_list(
        document.get("analysis_completion_binding_digests"),
        "V32_SUPERVISOR_ANALYSIS_COMPLETION_BINDINGS_INVALID",
    )
    last_batch = _digest(
        document.get("last_outcome_batch_digest"),
        "V32_SUPERVISOR_BATCH_DIGEST_INVALID",
        nullable=True,
    )
    analysis_heads = (
        dynamic,
        last_decision,
        source_admission,
        source_physical,
        proposal_lifecycle,
        selection_lifecycle,
        action_plan,
        last_commit,
        last_shadow,
    )
    if (
        any((accepted == 0) != (head is None) for head in analysis_heads)
        or len(completion_bindings) != accepted
        or len(set(completion_bindings)) != len(completion_bindings)
        or (
            accepted > 0
            and last_shadow != shadow_digests[-1]
        )
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_ANALYSIS_HEAD_INVALID")
    if (terminal == 0) != (last_batch is None):
        raise V32TickSupervisorError("V32_SUPERVISOR_OUTCOME_HEAD_INVALID")

    next_cycle = document.get("next_analysis_cycle_index")
    expected_cycle = accepted + 1 if accepted < TOTAL_ANALYSIS_CYCLES else None
    if next_cycle != expected_cycle:
        raise V32TickSupervisorError("V32_SUPERVISOR_NEXT_ANALYSIS_INVALID")
    next_tick = document.get("next_outcome_tick_index")
    if document["status"] == "TERMINAL_COMPLETE":
        if next_tick is not None:
            raise V32TickSupervisorError("V32_SUPERVISOR_NEXT_OUTCOME_INVALID")
    else:
        _positive(next_tick, 1_000_000, "V32_SUPERVISOR_NEXT_OUTCOME_INVALID")

    active_kind = document.get("active_permit_kind")
    active_digest = _digest(
        document.get("active_permit_digest"),
        "V32_SUPERVISOR_ACTIVE_PERMIT_INVALID",
        nullable=True,
    )
    if active_kind is not None and active_kind not in TICK_KINDS:
        raise V32TickSupervisorError("V32_SUPERVISOR_ACTIVE_PERMIT_INVALID")
    if (active_kind is None) != (active_digest is None):
        raise V32TickSupervisorError("V32_SUPERVISOR_ACTIVE_PERMIT_INVALID")

    lanes = _lane_states(document.get("lane_states"), "V32_SUPERVISOR_LANES_INVALID")
    status = document["status"]
    failure_lane = document.get("failure_lane")
    failure_ref = document.get("failure_ref")
    failure_digest = _digest(
        document.get("failure_digest"),
        "V32_SUPERVISOR_FAILURE_INVALID",
        nullable=True,
    )
    if status == "READY":
        valid = (
            accepted < TOTAL_ANALYSIS_CYCLES
            and active_kind is None
            and lanes == _ready_lane_states()
        )
    elif status == "ANALYSIS_TICK_OPEN":
        expected_lanes = _ready_lane_states()
        expected_lanes["ANALYSIS_LANE"] = "ACTIVE"
        valid = (
            accepted < TOTAL_ANALYSIS_CYCLES
            and active_kind == "ANALYSIS_TICK"
            and lanes == expected_lanes
        )
    elif status == "OUTCOME_TICK_OPEN":
        expected_lanes = _ready_lane_states(tail=accepted == TOTAL_ANALYSIS_CYCLES)
        expected_lanes["OUTCOME_LANE"] = "ACTIVE"
        valid = (
            terminal < scheduled
            and active_kind in {"OUTCOME_TICK", "OUTCOME_WINDOW_EXPIRY"}
            and lanes == expected_lanes
        )
    elif status == "OUTCOME_ONLY_TAIL":
        valid = (
            accepted == TOTAL_ANALYSIS_CYCLES
            and terminal < TOTAL_OUTCOME_SCHEDULES
            and active_kind is None
            and lanes == _ready_lane_states(tail=True)
        )
    elif status == "TERMINAL_COMPLETE":
        valid = (
            accepted == TOTAL_ANALYSIS_CYCLES
            and scheduled == terminal == TOTAL_OUTCOME_SCHEDULES
            and active_kind is None
            and lanes == _ready_lane_states(terminal=True)
        )
    else:
        valid = (
            active_kind is None
            and failure_lane in LANES
            and isinstance(failure_ref, str)
            and bool(failure_ref)
            and failure_digest is not None
            and lanes.get(failure_lane) == "FAILED_CLOSED"
            and all(state != "ACTIVE" for state in lanes.values())
        )
    if not valid:
        raise V32TickSupervisorError("V32_SUPERVISOR_STATUS_STATE_INVALID")
    if status == "FAILED_CLOSED":
        if document.get("resume_allowed") is not False:
            raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_INVALID")
    elif status == "TERMINAL_COMPLETE":
        if (
            failure_lane is not None
            or failure_ref is not None
            or failure_digest is not None
            or document.get("resume_allowed") is not False
        ):
            raise V32TickSupervisorError("V32_SUPERVISOR_TERMINAL_INVALID")
    elif (
        failure_lane is not None
        or failure_ref is not None
        or failure_digest is not None
        or document.get("resume_allowed") is not True
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_INVALID")
    return digest


def _schedule_registry(
    checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    verify_v32_tick_supervisor_checkpoint(checkpoint)
    if isinstance(schedule_sets, (str, bytes)) or not isinstance(schedule_sets, Sequence):
        raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_SETS_INVALID")
    if len(schedule_sets) != checkpoint["accepted_analysis_cycles"]:
        raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_SET_COUNT_INVALID")
    by_cycle: dict[int, Mapping[str, Any]] = {}
    rows: dict[str, dict[str, Any]] = {}
    set_digests: list[str] = []
    try:
        for schedule_set in schedule_sets:
            digest = verify_v32_outcome_schedule_set(schedule_set)
            if schedule_set.get("run_id") != checkpoint.get("run_id"):
                raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_RUN_INVALID")
            cycle = schedule_set.get("cycle_index")
            if cycle in by_cycle:
                raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_CYCLE_DUPLICATE")
            by_cycle[cycle] = schedule_set
            for row in schedule_set["schedules"]:
                if row["schedule_id"] in rows:
                    raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_ID_DUPLICATE")
                rows[row["schedule_id"]] = dict(row)
        for cycle in range(1, checkpoint["accepted_analysis_cycles"] + 1):
            if cycle not in by_cycle:
                raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_CYCLE_MISSING")
            set_digests.append(by_cycle[cycle][SCHEDULE_SET_DIGEST_FIELD])
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32TickSupervisorError):
            raise
        raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_REGISTRY_INVALID") from exc
    if (
        set_digests != list(checkpoint["outcome_schedule_set_digests"])
        or sorted(rows) != list(checkpoint["scheduled_schedule_ids"])
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_SCHEDULE_REGISTRY_DRIFT")
    return rows


def _schedule_partition(
    checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    *,
    at: str,
) -> tuple[list[str], list[str], list[str], dict[str, dict[str, Any]]]:
    rows = _schedule_registry(checkpoint, schedule_sets)
    point = _moment(at, "V32_SUPERVISOR_CLOCK_INVALID")
    terminal = set(checkpoint["terminal_schedule_ids"])
    mature = sorted(
        schedule_id
        for schedule_id, row in rows.items()
        if _moment(row["outcome_not_before"], "V32_SUPERVISOR_SCHEDULE_TIME_INVALID")
        <= point
    )
    due = sorted(set(mature) - terminal)
    future = sorted(set(rows) - set(mature))
    mature_terminal = sorted(set(mature) & terminal)
    return mature_terminal, due, future, rows


def _schedule_window_partition(
    checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    *,
    at: str,
) -> tuple[list[str], list[str], list[str], list[str], dict[str, dict[str, Any]]]:
    """Partition outstanding schedules by their fully verified grace window."""

    rows = _schedule_registry(checkpoint, schedule_sets)
    terminal = set(checkpoint["terminal_schedule_ids"])
    mature_terminal: list[str] = []
    due: list[str] = []
    expired: list[str] = []
    future: list[str] = []
    for schedule_id, row in rows.items():
        timing = classify_v32_outcome_schedule_time(row, now=at)
        if schedule_id in terminal:
            if timing != "FUTURE":
                mature_terminal.append(schedule_id)
            continue
        if timing == "FUTURE":
            future.append(schedule_id)
        elif timing == "DUE":
            due.append(schedule_id)
        else:
            expired.append(schedule_id)
    return (
        sorted(mature_terminal),
        sorted(due),
        sorted(expired),
        sorted(future),
        rows,
    )


def classify_v32_outcome_permit_mode(
    *,
    checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    issued_at: str,
) -> str:
    """Select the only legal outcome mode after complete schedule validation."""

    _, due, expired, _, _ = _schedule_window_partition(
        checkpoint, schedule_sets, at=issued_at
    )
    if expired:
        return "OUTCOME_WINDOW_EXPIRY"
    if due:
        return "OUTCOME_TICK"
    raise V32TickSupervisorError("V32_OUTCOME_PERMIT_NO_DUE_SCHEDULES")


def _permit_id(
    *, predecessor_digest: str, kind: str, analysis_cycle: int | None, outcome_tick: int | None
) -> str:
    return canonical_digest(
        {
            "schema_id": "theory_paper_v32_tick_supervisor_permit_identity_v1",
            "predecessor_checkpoint_digest": predecessor_digest,
            "permit_kind": kind,
            "analysis_cycle_index": analysis_cycle,
            "outcome_tick_index": outcome_tick,
        }
    )


def build_v32_analysis_tick_permit(
    *,
    checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    analysis_decision_at: str,
    issued_at: str,
    research_checkpoint_digest: str,
    outcome_checkpoint_digest: str,
    timeframe_cache_digest: str,
    prior_dynamic_state_digest: str | None,
) -> dict[str, Any]:
    """Permit one analysis boundary only when every already-due outcome is terminal."""

    predecessor = verify_v32_tick_supervisor_checkpoint(checkpoint)
    if checkpoint["status"] != "READY" or checkpoint["active_permit_digest"] is not None:
        raise V32TickSupervisorError("V32_ANALYSIS_PERMIT_STATE_INVALID")
    cycle = _positive(
        checkpoint["next_analysis_cycle_index"],
        TOTAL_ANALYSIS_CYCLES,
        "V32_ANALYSIS_PERMIT_CYCLE_INVALID",
    )
    decided = _moment(analysis_decision_at, "V32_ANALYSIS_PERMIT_TIME_INVALID")
    issued = _moment(issued_at, "V32_ANALYSIS_PERMIT_TIME_INVALID")
    if decided < _moment(checkpoint["updated_at"], "V32_ANALYSIS_PERMIT_TIME_INVALID") or issued < decided:
        raise V32TickSupervisorError("V32_ANALYSIS_PERMIT_TIME_INVALID")
    if cycle > 1:
        previous_decision = _moment(
            checkpoint["last_analysis_decision_at"],
            "V32_ANALYSIS_PERMIT_CADENCE_INVALID",
        )
        if decided < previous_decision + timedelta(seconds=900):
            raise V32TickSupervisorError("V32_ANALYSIS_PERMIT_CADENCE_INVALID")
    live_bindings = {
        "research_checkpoint_digest": research_checkpoint_digest,
        "outcome_checkpoint_digest": outcome_checkpoint_digest,
        "timeframe_cache_digest": timeframe_cache_digest,
        "prior_dynamic_state_digest": prior_dynamic_state_digest,
        "prior_source_admission_digest": checkpoint[
            "last_source_admission_digest"
        ],
        "prior_source_admission_physical_sha256": checkpoint[
            "last_source_admission_physical_sha256"
        ],
    }
    expected_bindings = {
        "research_checkpoint_digest": checkpoint["current_research_checkpoint_digest"],
        "outcome_checkpoint_digest": checkpoint["current_outcome_checkpoint_digest"],
        "timeframe_cache_digest": checkpoint["current_timeframe_cache_digest"],
        "prior_dynamic_state_digest": checkpoint["current_dynamic_state_digest"],
        "prior_source_admission_digest": checkpoint[
            "last_source_admission_digest"
        ],
        "prior_source_admission_physical_sha256": checkpoint[
            "last_source_admission_physical_sha256"
        ],
    }
    if live_bindings != expected_bindings:
        raise V32TickSupervisorError("V32_ANALYSIS_PERMIT_LIVE_BINDING_DRIFT")
    mature_terminal, due, future, rows = _schedule_partition(
        checkpoint, schedule_sets, at=analysis_decision_at
    )
    if due:
        raise V32TickSupervisorError("V32_ANALYSIS_PERMIT_DUE_OUTCOME_REQUIRED_FIRST")
    permit_id = _permit_id(
        predecessor_digest=predecessor,
        kind="ANALYSIS_TICK",
        analysis_cycle=cycle,
        outcome_tick=None,
    )
    result = self_digest(
        {
            "schema_id": PERMIT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "permit_id": permit_id,
            "permit_kind": "ANALYSIS_TICK",
            "run_id": checkpoint["run_id"],
            "analysis_cycle_index": cycle,
            "outcome_tick_index": None,
            "analysis_decision_at": _time(
                analysis_decision_at, "V32_ANALYSIS_PERMIT_TIME_INVALID"
            ),
            "planned_outcome_tick_at": None,
            "issued_at": _time(issued_at, "V32_ANALYSIS_PERMIT_TIME_INVALID"),
            "supervisor_checkpoint_digest_before_permit": predecessor,
            "experiment_contract_digest": checkpoint["experiment_contract_digest"],
            "active_authority_digest": checkpoint["active_authority_digest"],
            **live_bindings,
            "outcome_schedule_set_digests": list(
                checkpoint["outcome_schedule_set_digests"]
            ),
            "scheduled_schedule_ids": list(checkpoint["scheduled_schedule_ids"]),
            "terminal_schedule_ids": list(checkpoint["terminal_schedule_ids"]),
            "mature_terminal_schedule_ids": mature_terminal,
            "due_schedule_ids": [],
            "due_schedule_digests": [],
            "future_schedule_ids": future,
            "tick_attempt_digest": None,
            "opened_lane": "ANALYSIS_LANE",
            "single_state_change_boundary": True,
            "future_outcomes_readable": False,
            "future_outcomes_block_analysis": False,
            "agent_stage_attempt_limits": {"PROPOSAL": 1, "SELECTION": 1},
            "source_collection_transactions_allowed": 1,
            "network_requests_allowed": (
                "ONLY_WITHIN_ONE_FROZEN_SOURCE_COLLECTION_TRANSACTION"
            ),
            **_boundary(),
        },
        PERMIT_DIGEST_FIELD,
    )
    _validate_permit_intrinsic(result)
    return result


def build_v32_outcome_tick_permit(
    *,
    checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    tick_attempt: Mapping[str, Any] | None,
    issued_at: str,
) -> dict[str, Any]:
    """Build either a public-tick permit or its zero-network expiry variant."""

    predecessor = verify_v32_tick_supervisor_checkpoint(checkpoint)
    if checkpoint["status"] not in {"READY", "OUTCOME_ONLY_TAIL"} or checkpoint["active_permit_digest"] is not None:
        raise V32TickSupervisorError("V32_OUTCOME_PERMIT_STATE_INVALID")
    issued = _moment(issued_at, "V32_OUTCOME_PERMIT_TIME_INVALID")
    if issued < _moment(
        checkpoint["updated_at"], "V32_OUTCOME_PERMIT_TIME_INVALID"
    ):
        raise V32TickSupervisorError("V32_OUTCOME_PERMIT_TIME_INVALID")
    if tick_attempt is None:
        mature_terminal, due, expired, future, rows = _schedule_window_partition(
            checkpoint, schedule_sets, at=issued_at
        )
        if not expired:
            raise V32TickSupervisorError("V32_EXPIRY_PERMIT_NO_EXPIRED_SCHEDULES")
        kind = "OUTCOME_WINDOW_EXPIRY"
        targets = expired
        attempt_digest = None
        planned_at = min(rows[schedule_id]["outcome_not_before"] for schedule_id in expired)
        unhandled = sorted([*due, *future])
        network_requests = 0
    else:
        # Preserve strict replay of the frozen v1 explicit-attempt permit.  The
        # application router selects the successor before constructing an
        # attempt whenever a verified schedule is already expired.
        mature_terminal, due, future, rows = _schedule_partition(
            checkpoint, schedule_sets, at=issued_at
        )
        attempt_digest = verify_v32_outcome_tick_attempt(tick_attempt)
        if (
            tick_attempt.get("run_id") != checkpoint.get("run_id")
            or tick_attempt.get("tick_index")
            != checkpoint.get("next_outcome_tick_index")
            or issued < _moment(
                tick_attempt["reserved_at"], "V32_OUTCOME_PERMIT_TIME_INVALID"
            )
        ):
            raise V32TickSupervisorError(
                "V32_OUTCOME_PERMIT_ATTEMPT_IDENTITY_INVALID"
            )
        kind = "OUTCOME_TICK"
        targets = due
        planned_at = tick_attempt["planned_tick_at"]
        unhandled = future
        network_requests = 1
    if not targets:
        raise V32TickSupervisorError("V32_OUTCOME_PERMIT_NO_DUE_SCHEDULES")
    due_digests = [rows[schedule_id]["schedule_digest"] for schedule_id in targets]
    tick_index = _positive(
        checkpoint["next_outcome_tick_index"],
        1_000_000,
        "V32_OUTCOME_PERMIT_TICK_INDEX_INVALID",
    )
    permit_id = _permit_id(
        predecessor_digest=predecessor,
        kind=kind,
        analysis_cycle=None,
        outcome_tick=tick_index,
    )
    result = self_digest(
        {
            "schema_id": (
                EXPIRY_PERMIT_SCHEMA_ID
                if kind == "OUTCOME_WINDOW_EXPIRY"
                else PERMIT_SCHEMA_ID
            ),
            "schema_version": SCHEMA_VERSION,
            "permit_id": permit_id,
            "permit_kind": kind,
            "run_id": checkpoint["run_id"],
            "analysis_cycle_index": None,
            "outcome_tick_index": tick_index,
            "analysis_decision_at": None,
            "planned_outcome_tick_at": planned_at,
            "issued_at": _time(issued_at, "V32_OUTCOME_PERMIT_TIME_INVALID"),
            "supervisor_checkpoint_digest_before_permit": predecessor,
            "experiment_contract_digest": checkpoint["experiment_contract_digest"],
            "active_authority_digest": checkpoint["active_authority_digest"],
            "research_checkpoint_digest": checkpoint[
                "current_research_checkpoint_digest"
            ],
            "outcome_checkpoint_digest": checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            "timeframe_cache_digest": checkpoint["current_timeframe_cache_digest"],
            "prior_dynamic_state_digest": checkpoint["current_dynamic_state_digest"],
            "prior_source_admission_digest": checkpoint[
                "last_source_admission_digest"
            ],
            "prior_source_admission_physical_sha256": checkpoint[
                "last_source_admission_physical_sha256"
            ],
            "outcome_schedule_set_digests": list(
                checkpoint["outcome_schedule_set_digests"]
            ),
            "scheduled_schedule_ids": list(checkpoint["scheduled_schedule_ids"]),
            "terminal_schedule_ids": list(checkpoint["terminal_schedule_ids"]),
            "mature_terminal_schedule_ids": mature_terminal,
            "due_schedule_ids": targets,
            "due_schedule_digests": due_digests,
            "future_schedule_ids": unhandled,
            "tick_attempt_digest": attempt_digest,
            "opened_lane": "OUTCOME_LANE",
            "single_state_change_boundary": True,
            "future_outcomes_readable": False,
            "future_outcomes_block_analysis": False,
            "agent_stage_attempt_limits": {"PROPOSAL": 0, "SELECTION": 0},
            "source_collection_transactions_allowed": 0,
            "network_requests_allowed": network_requests,
            **_boundary(),
        },
        PERMIT_DIGEST_FIELD,
    )
    _validate_permit_intrinsic(result)
    return result


def _validate_permit_intrinsic(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _PERMIT_FIELDS:
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_SCHEMA_INVALID")
    try:
        digest = verify_self_digest(document, PERMIT_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_DIGEST_INVALID") from exc
    expected_schema = (
        EXPIRY_PERMIT_SCHEMA_ID
        if document.get("permit_kind") == "OUTCOME_WINDOW_EXPIRY"
        else PERMIT_SCHEMA_ID
    )
    if (
        document.get("schema_id") != expected_schema
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("permit_kind") not in TICK_KINDS
        or document.get("single_state_change_boundary") is not True
        or document.get("future_outcomes_readable") is not False
        or document.get("future_outcomes_block_analysis") is not False
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_POLICY_INVALID")
    _assert_boundary(document, "V32_SUPERVISOR_PERMIT_BOUNDARY_INVALID")
    _text(document.get("run_id"), "V32_SUPERVISOR_PERMIT_RUN_INVALID")
    _text(document.get("permit_id"), "V32_SUPERVISOR_PERMIT_ID_INVALID")
    _time(document.get("issued_at"), "V32_SUPERVISOR_PERMIT_TIME_INVALID")
    for field in (
        "supervisor_checkpoint_digest_before_permit",
        "experiment_contract_digest",
        "active_authority_digest",
        "research_checkpoint_digest",
        "outcome_checkpoint_digest",
        "timeframe_cache_digest",
    ):
        _digest(document.get(field), "V32_SUPERVISOR_PERMIT_BINDING_INVALID")
    _digest(
        document.get("prior_dynamic_state_digest"),
        "V32_SUPERVISOR_PERMIT_BINDING_INVALID",
        nullable=True,
    )
    _digest(
        document.get("prior_source_admission_digest"),
        "V32_SUPERVISOR_PERMIT_SOURCE_HEAD_INVALID",
        nullable=True,
    )
    _digest(
        document.get("prior_source_admission_physical_sha256"),
        "V32_SUPERVISOR_PERMIT_SOURCE_HEAD_INVALID",
        nullable=True,
    )
    if (document.get("prior_source_admission_digest") is None) != (
        document.get("prior_source_admission_physical_sha256") is None
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_SOURCE_HEAD_INVALID")
    _digest_list(
        document.get("outcome_schedule_set_digests"),
        "V32_SUPERVISOR_PERMIT_SCHEDULE_BINDINGS_INVALID",
    )
    for field in (
        "scheduled_schedule_ids",
        "terminal_schedule_ids",
        "mature_terminal_schedule_ids",
        "due_schedule_ids",
        "future_schedule_ids",
    ):
        _sorted_unique_texts(
            document.get(field), "V32_SUPERVISOR_PERMIT_SCHEDULE_IDS_INVALID"
        )
    _digest_list(
        document.get("due_schedule_digests"),
        "V32_SUPERVISOR_PERMIT_DUE_DIGESTS_INVALID",
    )
    if len(document["due_schedule_ids"]) != len(document["due_schedule_digests"]):
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_DUE_BINDING_INVALID")
    if document["permit_kind"] == "ANALYSIS_TICK":
        cycle = document.get("analysis_cycle_index")
        valid = (
            document.get("opened_lane") == "ANALYSIS_LANE"
            and not isinstance(cycle, bool)
            and isinstance(cycle, int)
            and 1 <= cycle <= TOTAL_ANALYSIS_CYCLES
            and document.get("outcome_tick_index") is None
            and document.get("analysis_decision_at") is not None
            and document.get("planned_outcome_tick_at") is None
            and document.get("tick_attempt_digest") is None
            and document.get("due_schedule_ids") == []
            and document.get("due_schedule_digests") == []
            and document.get("agent_stage_attempt_limits")
            == {"PROPOSAL": 1, "SELECTION": 1}
            and document.get("source_collection_transactions_allowed") == 1
            and document.get("network_requests_allowed")
            == "ONLY_WITHIN_ONE_FROZEN_SOURCE_COLLECTION_TRANSACTION"
        )
        _time(document.get("analysis_decision_at"), "V32_SUPERVISOR_PERMIT_TIME_INVALID")
    else:
        tick_index = document.get("outcome_tick_index")
        expiry = document["permit_kind"] == "OUTCOME_WINDOW_EXPIRY"
        valid = (
            document.get("opened_lane") == "OUTCOME_LANE"
            and document.get("analysis_cycle_index") is None
            and not isinstance(tick_index, bool)
            and isinstance(tick_index, int)
            and 1 <= tick_index <= 1_000_000
            and document.get("analysis_decision_at") is None
            and document.get("planned_outcome_tick_at") is not None
            and (document.get("tick_attempt_digest") is None) is expiry
            and bool(document.get("due_schedule_ids"))
            and document.get("agent_stage_attempt_limits")
            == {"PROPOSAL": 0, "SELECTION": 0}
            and document.get("source_collection_transactions_allowed") == 0
            and document.get("network_requests_allowed") == (0 if expiry else 1)
        )
        _time(
            document.get("planned_outcome_tick_at"),
            "V32_SUPERVISOR_PERMIT_TIME_INVALID",
        )
        if not expiry:
            _digest(
                document.get("tick_attempt_digest"),
                "V32_SUPERVISOR_PERMIT_ATTEMPT_INVALID",
            )
    if not valid:
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_KIND_INVALID")
    expected_id = _permit_id(
        predecessor_digest=document["supervisor_checkpoint_digest_before_permit"],
        kind=document["permit_kind"],
        analysis_cycle=document["analysis_cycle_index"],
        outcome_tick=document["outcome_tick_index"],
    )
    if document["permit_id"] != expected_id:
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_IDENTITY_INVALID")
    return digest


def verify_v32_tick_supervisor_permit(
    document: Mapping[str, Any],
    *,
    checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    tick_attempt: Mapping[str, Any] | None = None,
) -> str:
    """Reconstruct a permit against its exact predecessor and live registries."""

    supplied = _validate_permit_intrinsic(document)
    if document["permit_kind"] == "ANALYSIS_TICK":
        if tick_attempt is not None:
            raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_ATTEMPT_UNEXPECTED")
        rebuilt = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=schedule_sets,
            analysis_decision_at=document["analysis_decision_at"],
            issued_at=document["issued_at"],
            research_checkpoint_digest=document["research_checkpoint_digest"],
            outcome_checkpoint_digest=document["outcome_checkpoint_digest"],
            timeframe_cache_digest=document["timeframe_cache_digest"],
            prior_dynamic_state_digest=document["prior_dynamic_state_digest"],
        )
    else:
        if (document["permit_kind"] == "OUTCOME_TICK") != (
            tick_attempt is not None
        ):
            raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_ATTEMPT_MISMATCH")
        rebuilt = build_v32_outcome_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=schedule_sets,
            tick_attempt=tick_attempt,
            issued_at=document["issued_at"],
        )
    if dict(document) != rebuilt or supplied != rebuilt[PERMIT_DIGEST_FIELD]:
        raise V32TickSupervisorError("V32_SUPERVISOR_PERMIT_RECONSTRUCTION_MISMATCH")
    return supplied


def _successor_base(
    checkpoint: Mapping[str, Any], *, updated_at: str
) -> dict[str, Any]:
    before_digest = verify_v32_tick_supervisor_checkpoint(checkpoint)
    updated = _moment(updated_at, "V32_SUPERVISOR_TRANSITION_TIME_INVALID")
    if updated < _moment(checkpoint["updated_at"], "V32_SUPERVISOR_TRANSITION_TIME_INVALID"):
        raise V32TickSupervisorError("V32_SUPERVISOR_TRANSITION_TIME_INVALID")
    candidate = dict(checkpoint)
    candidate.pop(CHECKPOINT_DIGEST_FIELD, None)
    candidate.update(
        {
            "revision": checkpoint["revision"] + 1,
            "predecessor_checkpoint_digest": before_digest,
            "updated_at": _time(updated_at, "V32_SUPERVISOR_TRANSITION_TIME_INVALID"),
        }
    )
    return candidate


def open_v32_tick_supervisor_permit(
    *,
    checkpoint: Mapping[str, Any],
    permit: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    updated_at: str,
    tick_attempt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """CAS-open exactly one analysis or outcome boundary."""

    permit_digest = verify_v32_tick_supervisor_permit(
        permit,
        checkpoint=checkpoint,
        schedule_sets=schedule_sets,
        tick_attempt=tick_attempt,
    )
    if _moment(updated_at, "V32_SUPERVISOR_TRANSITION_TIME_INVALID") < _moment(
        permit["issued_at"], "V32_SUPERVISOR_TRANSITION_TIME_INVALID"
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_TRANSITION_TIME_INVALID")
    candidate = _successor_base(checkpoint, updated_at=updated_at)
    kind = permit["permit_kind"]
    lanes = dict(checkpoint["lane_states"])
    lane = "ANALYSIS_LANE" if kind == "ANALYSIS_TICK" else "OUTCOME_LANE"
    lanes[lane] = "ACTIVE"
    candidate.update(
        {
            "status": "ANALYSIS_TICK_OPEN" if kind == "ANALYSIS_TICK" else "OUTCOME_TICK_OPEN",
            "active_permit_kind": kind,
            "active_permit_digest": permit_digest,
            "lane_states": lanes,
        }
    )
    result = self_digest(candidate, CHECKPOINT_DIGEST_FIELD)
    verify_v32_tick_supervisor_transition(checkpoint, result)
    return result


def _assert_active_permit(
    checkpoint: Mapping[str, Any],
    permit: Mapping[str, Any],
    *,
    kind: str,
) -> str:
    verify_v32_tick_supervisor_checkpoint(checkpoint)
    permit_digest = _validate_permit_intrinsic(permit)
    expected_status = "ANALYSIS_TICK_OPEN" if kind == "ANALYSIS_TICK" else "OUTCOME_TICK_OPEN"
    if (
        checkpoint["status"] != expected_status
        or checkpoint["active_permit_kind"] != kind
        or checkpoint["active_permit_digest"] != permit_digest
        or checkpoint["predecessor_checkpoint_digest"]
        != permit["supervisor_checkpoint_digest_before_permit"]
        or checkpoint["run_id"] != permit["run_id"]
        or checkpoint["experiment_contract_digest"]
        != permit["experiment_contract_digest"]
        or checkpoint["active_authority_digest"] != permit["active_authority_digest"]
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_ACTIVE_PERMIT_MISMATCH")
    return permit_digest


def complete_v32_analysis_tick(
    *,
    checkpoint: Mapping[str, Any],
    permit: Mapping[str, Any],
    schedule_sets_before: Sequence[Mapping[str, Any]],
    new_schedule_set: Mapping[str, Any],
    accepted_state_digest: str,
    source_admission_digest: str,
    source_admission_physical_sha256: str,
    proposal_lifecycle_digest: str,
    selection_lifecycle_digest: str,
    final_action_plan_digest: str,
    commit_envelope_digest: str,
    shadow_decision_bundle_digest: str,
    new_research_checkpoint_digest: str,
    new_outcome_checkpoint_digest: str,
    new_timeframe_cache_digest: str,
    new_dynamic_state_digest: str,
    completed_at: str,
    source_admission_schema_version: str = (
        LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION
    ),
    decision_sealed_at: str | None = None,
) -> dict[str, Any]:
    """Accept one analysis cycle and its exact three-schedule identity."""

    _assert_active_permit(checkpoint, permit, kind="ANALYSIS_TICK")
    _schedule_registry(checkpoint, schedule_sets_before)
    completed = _moment(completed_at, "V32_ANALYSIS_COMPLETE_TIME_INVALID")
    if (
        completed
        < _moment(checkpoint["updated_at"], "V32_ANALYSIS_COMPLETE_TIME_INVALID")
        or completed
        < _moment(new_schedule_set.get("scheduled_at"), "V32_ANALYSIS_COMPLETE_TIME_INVALID")
    ):
        raise V32TickSupervisorError("V32_ANALYSIS_COMPLETE_TIME_INVALID")
    cycle = checkpoint["accepted_analysis_cycles"] + 1
    if permit["analysis_cycle_index"] != cycle:
        raise V32TickSupervisorError("V32_ANALYSIS_COMPLETE_CYCLE_INVALID")
    try:
        set_digest = verify_v32_outcome_schedule_set(new_schedule_set)
    except (TypeError, ValueError) as exc:
        raise V32TickSupervisorError("V32_ANALYSIS_SCHEDULE_SET_INVALID") from exc
    source_schema_version = _text(
        source_admission_schema_version,
        "V32_ANALYSIS_SOURCE_ADMISSION_SCHEMA_VERSION_INVALID",
    )
    if source_schema_version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION:
        if decision_sealed_at is not None:
            raise V32TickSupervisorError(
                "V32_ANALYSIS_DECISION_SEALED_TIME_INVALID"
            )
        effective_decision_at = permit["analysis_decision_at"]
    elif source_schema_version == SOURCE_ADMISSION_SCHEMA_VERSION:
        if decision_sealed_at is None:
            raise V32TickSupervisorError(
                "V32_ANALYSIS_DECISION_SEALED_TIME_INVALID"
            )
        effective_decision_at = _time(
            decision_sealed_at,
            "V32_ANALYSIS_DECISION_SEALED_TIME_INVALID",
        )
        if (
            _moment(
                effective_decision_at,
                "V32_ANALYSIS_DECISION_SEALED_TIME_INVALID",
            )
            < _moment(
                permit["issued_at"],
                "V32_ANALYSIS_DECISION_SEALED_TIME_INVALID",
            )
            or _moment(
                effective_decision_at,
                "V32_ANALYSIS_DECISION_SEALED_TIME_INVALID",
            )
            > completed
        ):
            raise V32TickSupervisorError(
                "V32_ANALYSIS_DECISION_SEALED_TIME_INVALID"
            )
    else:
        raise V32TickSupervisorError(
            "V32_ANALYSIS_SOURCE_ADMISSION_SCHEMA_VERSION_INVALID"
        )
    if (
        new_schedule_set.get("run_id") != checkpoint["run_id"]
        or new_schedule_set.get("cycle_index") != cycle
        or new_schedule_set.get("decision_time") != effective_decision_at
        or len(new_schedule_set.get("schedules", ())) != 3
    ):
        raise V32TickSupervisorError("V32_ANALYSIS_SCHEDULE_SET_IDENTITY_INVALID")
    new_ids = sorted(row["schedule_id"] for row in new_schedule_set["schedules"])
    if set(new_ids) & set(checkpoint["scheduled_schedule_ids"]):
        raise V32TickSupervisorError("V32_ANALYSIS_SCHEDULE_DUPLICATE")
    accepted_digest = _digest(
        accepted_state_digest, "V32_ANALYSIS_ACCEPTED_STATE_DIGEST_INVALID"
    )
    source_digest = _digest(
        source_admission_digest, "V32_ANALYSIS_SOURCE_ADMISSION_INVALID"
    )
    source_physical = _digest(
        source_admission_physical_sha256,
        "V32_ANALYSIS_SOURCE_ADMISSION_PHYSICAL_INVALID",
    )
    proposal_digest = _digest(
        proposal_lifecycle_digest, "V32_ANALYSIS_PROPOSAL_LIFECYCLE_INVALID"
    )
    selection_digest = _digest(
        selection_lifecycle_digest, "V32_ANALYSIS_SELECTION_LIFECYCLE_INVALID"
    )
    action_plan_digest = _digest(
        final_action_plan_digest, "V32_ANALYSIS_ACTION_PLAN_INVALID"
    )
    commit_digest = _digest(
        commit_envelope_digest, "V32_ANALYSIS_COMMIT_DIGEST_INVALID"
    )
    shadow_digest = _digest(
        shadow_decision_bundle_digest,
        "V32_ANALYSIS_SHADOW_DECISION_BUNDLE_DIGEST_INVALID",
    )
    research_digest = _digest(
        new_research_checkpoint_digest,
        "V32_ANALYSIS_RESEARCH_CHECKPOINT_DIGEST_INVALID",
    )
    outcome_digest = _digest(
        new_outcome_checkpoint_digest,
        "V32_ANALYSIS_OUTCOME_CHECKPOINT_DIGEST_INVALID",
    )
    if outcome_digest == checkpoint["current_outcome_checkpoint_digest"]:
        raise V32TickSupervisorError(
            "V32_ANALYSIS_OUTCOME_CHECKPOINT_NOT_ADVANCED"
        )
    cache_digest = _digest(
        new_timeframe_cache_digest, "V32_ANALYSIS_CACHE_DIGEST_INVALID"
    )
    dynamic_digest = _digest(
        new_dynamic_state_digest, "V32_ANALYSIS_DYNAMIC_STATE_DIGEST_INVALID"
    )
    completion_binding = {
        "schema_id": (
            "theory_paper_v32_analysis_completion_binding_v1"
            if source_schema_version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION
            else "theory_paper_v32_analysis_completion_binding_v2"
        ),
        "run_id": checkpoint["run_id"],
        "cycle_index": cycle,
        "analysis_decision_at": permit["analysis_decision_at"],
        "source_admission_digest": source_digest,
        "source_admission_physical_sha256": source_physical,
        "proposal_lifecycle_digest": proposal_digest,
        "selection_lifecycle_digest": selection_digest,
        "final_action_plan_digest": action_plan_digest,
        "commit_envelope_digest": commit_digest,
        "shadow_decision_bundle_digest": shadow_digest,
        "accepted_state_digest": accepted_digest,
        "outcome_schedule_set_digest": set_digest,
        "new_research_checkpoint_digest": research_digest,
        "new_outcome_checkpoint_digest": outcome_digest,
        "new_timeframe_cache_digest": cache_digest,
        "new_dynamic_state_digest": dynamic_digest,
    }
    if source_schema_version == SOURCE_ADMISSION_SCHEMA_VERSION:
        completion_binding.update(
            {
                "source_admission_schema_version": source_schema_version,
                "source_cutoff_at": permit["analysis_decision_at"],
                "decision_sealed_at": effective_decision_at,
            }
        )
    completion_binding_digest = canonical_digest(completion_binding)
    candidate = _successor_base(checkpoint, updated_at=completed_at)
    accepted_count = cycle
    status = "READY" if accepted_count < TOTAL_ANALYSIS_CYCLES else "OUTCOME_ONLY_TAIL"
    candidate.update(
        {
            "status": status,
            "accepted_analysis_cycles": accepted_count,
            "scheduled_outcomes": checkpoint["scheduled_outcomes"] + 3,
            "next_analysis_cycle_index": (
                accepted_count + 1 if accepted_count < TOTAL_ANALYSIS_CYCLES else None
            ),
            "accepted_state_digests": [
                *checkpoint["accepted_state_digests"],
                accepted_digest,
            ],
            "shadow_decision_bundle_digests": [
                *checkpoint["shadow_decision_bundle_digests"],
                shadow_digest,
            ],
            "outcome_schedule_set_digests": [
                *checkpoint["outcome_schedule_set_digests"],
                set_digest,
            ],
            "scheduled_schedule_ids": sorted(
                [*checkpoint["scheduled_schedule_ids"], *new_ids]
            ),
            "current_research_checkpoint_digest": research_digest,
            "current_outcome_checkpoint_digest": outcome_digest,
            "current_timeframe_cache_digest": cache_digest,
            "current_dynamic_state_digest": dynamic_digest,
            "last_analysis_decision_at": effective_decision_at,
            "last_source_admission_digest": source_digest,
            "last_source_admission_physical_sha256": source_physical,
            "last_proposal_lifecycle_digest": proposal_digest,
            "last_selection_lifecycle_digest": selection_digest,
            "last_action_plan_digest": action_plan_digest,
            "last_commit_envelope_digest": commit_digest,
            "last_shadow_decision_bundle_digest": shadow_digest,
            "analysis_completion_binding_digests": [
                *checkpoint["analysis_completion_binding_digests"],
                completion_binding_digest,
            ],
            "active_permit_kind": None,
            "active_permit_digest": None,
            "lane_states": _ready_lane_states(
                tail=accepted_count == TOTAL_ANALYSIS_CYCLES
            ),
        }
    )
    result = self_digest(candidate, CHECKPOINT_DIGEST_FIELD)
    verify_v32_tick_supervisor_transition(checkpoint, result)
    return result


def _complete_outcome_transition(
    checkpoint: Mapping[str, Any], *, permit: Mapping[str, Any],
    terminal_schedule_ids: Sequence[str], evidence_digest: str,
    new_outcome_checkpoint_digest: str, completed_at: str,
    attempt_advanced: bool,
) -> dict[str, Any]:
    added = _sorted_unique_texts(
        terminal_schedule_ids, "V32_OUTCOME_COMPLETE_TERMINAL_SET_INVALID"
    )
    terminal_ids = sorted([*checkpoint["terminal_schedule_ids"], *added])
    if len(terminal_ids) != len(set(terminal_ids)):
        raise V32TickSupervisorError("V32_OUTCOME_COMPLETE_DUPLICATE_TERMINAL")
    terminal_count = len(terminal_ids)
    accepted = checkpoint["accepted_analysis_cycles"]
    terminal_run = (
        accepted == TOTAL_ANALYSIS_CYCLES
        and terminal_count == TOTAL_OUTCOME_SCHEDULES
    )
    tail = accepted == TOTAL_ANALYSIS_CYCLES and not terminal_run
    candidate = _successor_base(checkpoint, updated_at=completed_at)
    candidate.update(
        {
            "status": (
                "TERMINAL_COMPLETE" if terminal_run else "OUTCOME_ONLY_TAIL" if tail else "READY"
            ),
            "terminal_outcomes": terminal_count,
            "terminal_schedule_ids": terminal_ids,
            "next_outcome_tick_index": (
                None
                if terminal_run
                else checkpoint["next_outcome_tick_index"] + (1 if attempt_advanced else 0)
            ),
            "current_outcome_checkpoint_digest": _digest(
                new_outcome_checkpoint_digest,
                "V32_OUTCOME_CHECKPOINT_DIGEST_INVALID",
            ),
            "last_outcome_batch_digest": _digest(
                evidence_digest, "V32_OUTCOME_COMPLETE_EVIDENCE_DIGEST_INVALID"
            ),
            "active_permit_kind": None,
            "active_permit_digest": None,
            "lane_states": _ready_lane_states(tail=tail, terminal=terminal_run),
            "resume_allowed": not terminal_run,
        }
    )
    result = self_digest(candidate, CHECKPOINT_DIGEST_FIELD)
    verify_v32_tick_supervisor_transition(checkpoint, result)
    return result


def complete_v32_outcome_tick(
    *,
    checkpoint: Mapping[str, Any],
    permit: Mapping[str, Any],
    tick_attempt: Mapping[str, Any],
    observation_tick: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    prior_terminal_receipts: Sequence[Mapping[str, Any]],
    batch_intent: Mapping[str, Any],
    outcome_receipts: Sequence[Mapping[str, Any]],
    batch_completion: Mapping[str, Any],
    new_outcome_checkpoint_digest: str,
    completed_at: str,
) -> dict[str, Any]:
    """Close one exact shared tick; legal coverage loss remains terminal, not fatal."""

    _assert_active_permit(checkpoint, permit, kind="OUTCOME_TICK")
    _schedule_registry(checkpoint, schedule_sets)
    attempt_digest = verify_v32_outcome_tick_attempt(tick_attempt)
    if (
        permit["tick_attempt_digest"] != attempt_digest
        or permit["outcome_tick_index"] != tick_attempt.get("tick_index")
    ):
        raise V32TickSupervisorError("V32_OUTCOME_COMPLETE_ATTEMPT_MISMATCH")
    tick_digest = verify_v32_outcome_observation_tick(
        observation_tick, attempt=tick_attempt
    )
    # The clock-view builder performs intrinsic validation of every prior
    # receipt without exposing any future value to this supervisor.
    try:
        prior_view = build_v32_analysis_clock_view(
            run_id=checkpoint["run_id"],
            cycle_index=max(1, min(TOTAL_ANALYSIS_CYCLES, checkpoint["accepted_analysis_cycles"])),
            decision_time=permit["issued_at"],
            schedule_sets=schedule_sets,
            terminal_outcome_receipts=prior_terminal_receipts,
        )
    except (TypeError, ValueError) as exc:
        raise V32TickSupervisorError("V32_OUTCOME_PRIOR_RECEIPTS_INVALID") from exc
    if sorted(receipt["schedule_id"] for receipt in prior_terminal_receipts) != list(
        checkpoint["terminal_schedule_ids"]
    ):
        raise V32TickSupervisorError("V32_OUTCOME_PRIOR_RECEIPT_SET_MISMATCH")
    if set(prior_view["mature_terminal_schedule_ids"]) - set(
        checkpoint["terminal_schedule_ids"]
    ):
        raise V32TickSupervisorError("V32_OUTCOME_PRIOR_RECEIPT_SET_MISMATCH")
    try:
        intent_digest = verify_v32_outcome_resolution_batch_intent(
            batch_intent,
            attempt=tick_attempt,
            observation_tick=observation_tick,
            schedule_sets=schedule_sets,
            prior_terminal_receipts=prior_terminal_receipts,
        )
        for receipt in outcome_receipts:
            verify_v32_public_market_outcome_receipt(
                receipt,
                batch_intent=batch_intent,
                attempt=tick_attempt,
                observation_tick=observation_tick,
                schedule_sets=schedule_sets,
            )
        batch_digest = verify_v32_outcome_resolution_batch(
            batch_completion,
            batch_intent=batch_intent,
            outcome_receipts=outcome_receipts,
        )
    except (TypeError, ValueError) as exc:
        raise V32TickSupervisorError("V32_OUTCOME_COMPLETE_EVIDENCE_INVALID") from exc
    due_ids = list(permit["due_schedule_ids"])
    if (
        batch_intent.get(BATCH_INTENT_DIGEST_FIELD) != intent_digest
        or batch_intent.get("tick_attempt_digest") != attempt_digest
        or batch_intent.get("observation_tick_digest") != tick_digest
        or list(batch_intent.get("due_schedule_ids", ())) != due_ids
        or list(batch_completion.get("resolved_schedule_ids", ())) != due_ids
        or sorted(receipt["schedule_id"] for receipt in outcome_receipts) != due_ids
    ):
        raise V32TickSupervisorError("V32_OUTCOME_COMPLETE_DUE_SET_MISMATCH")
    completed = _moment(completed_at, "V32_OUTCOME_COMPLETE_TIME_INVALID")
    if (
        completed
        < _moment(checkpoint["updated_at"], "V32_OUTCOME_COMPLETE_TIME_INVALID")
        or completed
        < _moment(
            batch_completion.get("completed_at"),
            "V32_OUTCOME_COMPLETE_TIME_INVALID",
        )
    ):
        raise V32TickSupervisorError("V32_OUTCOME_COMPLETE_TIME_INVALID")
    return _complete_outcome_transition(
        checkpoint,
        permit=permit,
        terminal_schedule_ids=due_ids,
        evidence_digest=batch_digest,
        new_outcome_checkpoint_digest=new_outcome_checkpoint_digest,
        completed_at=completed_at,
        attempt_advanced=True,
    )


def complete_v32_outcome_window_expiry(
    *, checkpoint: Mapping[str, Any], permit: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    expiry_terminal: Mapping[str, Any],
    new_outcome_checkpoint_digest: str, completed_at: str,
) -> dict[str, Any]:
    """Close one aggregate zero-network terminal via the common transition."""

    _assert_active_permit(checkpoint, permit, kind="OUTCOME_WINDOW_EXPIRY")
    try:
        terminal_digest = verify_v32_outcome_window_expiry_terminal(
            expiry_terminal, schedule_sets=schedule_sets
        )
    except (TypeError, ValueError) as exc:
        raise V32TickSupervisorError("V32_EXPIRY_COMPLETE_EVIDENCE_INVALID") from exc
    target_ids = list(permit["due_schedule_ids"])
    if (
        expiry_terminal.get("permit_digest") != permit[PERMIT_DIGEST_FIELD]
        or expiry_terminal.get("supervisor_checkpoint_digest_before_permit")
        != permit["supervisor_checkpoint_digest_before_permit"]
        or expiry_terminal.get("outcome_checkpoint_digest_before")
        != permit["outcome_checkpoint_digest"]
        or expiry_terminal.get("experiment_contract_digest")
        != permit["experiment_contract_digest"]
        or expiry_terminal.get("active_authority_digest")
        != permit["active_authority_digest"]
        or expiry_terminal.get("prior_terminal_schedule_ids")
        != list(checkpoint["terminal_schedule_ids"])
        or expiry_terminal.get("terminal_schedule_ids") != target_ids
        or [row["schedule_digest"] for row in expiry_terminal["rows"]]
        != list(permit["due_schedule_digests"])
        or _moment(completed_at, "V32_EXPIRY_COMPLETE_TIME_INVALID")
        < _moment(expiry_terminal["classified_at"], "V32_EXPIRY_COMPLETE_TIME_INVALID")
    ):
        raise V32TickSupervisorError("V32_EXPIRY_COMPLETE_BINDING_MISMATCH")
    return _complete_outcome_transition(
        checkpoint,
        permit=permit,
        terminal_schedule_ids=target_ids,
        evidence_digest=terminal_digest,
        new_outcome_checkpoint_digest=new_outcome_checkpoint_digest,
        completed_at=completed_at,
        attempt_advanced=False,
    )


def build_v32_tick_supervisor_failure(
    *,
    checkpoint: Mapping[str, Any],
    failure_lane: str,
    failure_code: str,
    failure_summary: str,
    failure_evidence_digest: str,
    occurred_at: str,
) -> dict[str, Any]:
    """Seal an integrity failure.  Coverage loss is intentionally not a code."""

    checkpoint_digest = verify_v32_tick_supervisor_checkpoint(checkpoint)
    if checkpoint["status"] in {"TERMINAL_COMPLETE", "FAILED_CLOSED"}:
        raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_STATE_INVALID")
    if failure_lane not in LANES or failure_code not in FAILURE_CODES_BY_LANE[failure_lane]:
        raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_CLASS_INVALID")
    occurred = _moment(occurred_at, "V32_SUPERVISOR_FAILURE_TIME_INVALID")
    if occurred < _moment(checkpoint["updated_at"], "V32_SUPERVISOR_FAILURE_TIME_INVALID"):
        raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_TIME_INVALID")
    return self_digest(
        {
            "schema_id": FAILURE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": checkpoint["run_id"],
            "occurred_at": _time(occurred_at, "V32_SUPERVISOR_FAILURE_TIME_INVALID"),
            "failure_lane": failure_lane,
            "failure_code": failure_code,
            "failure_summary": _text(
                failure_summary, "V32_SUPERVISOR_FAILURE_SUMMARY_INVALID"
            ),
            "failure_evidence_digest": _digest(
                failure_evidence_digest,
                "V32_SUPERVISOR_FAILURE_EVIDENCE_INVALID",
            ),
            "supervisor_checkpoint_digest_before_failure": checkpoint_digest,
            "active_permit_digest": checkpoint["active_permit_digest"],
            "accepted_analysis_cycles": checkpoint["accepted_analysis_cycles"],
            "scheduled_outcomes": checkpoint["scheduled_outcomes"],
            "terminal_outcomes": checkpoint["terminal_outcomes"],
            "coverage_loss_is_run_failure": False,
            "retry_allowed": False,
            "resume_allowed": False,
            **_boundary(),
        },
        FAILURE_DIGEST_FIELD,
    )


def verify_v32_tick_supervisor_failure(
    document: Mapping[str, Any], *, checkpoint: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _FAILURE_FIELDS:
        raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, FAILURE_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_DIGEST_INVALID") from exc
    rebuilt = build_v32_tick_supervisor_failure(
        checkpoint=checkpoint,
        failure_lane=document["failure_lane"],
        failure_code=document["failure_code"],
        failure_summary=document["failure_summary"],
        failure_evidence_digest=document["failure_evidence_digest"],
        occurred_at=document["occurred_at"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[FAILURE_DIGEST_FIELD]:
        raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_RECONSTRUCTION_MISMATCH")
    _assert_boundary(document, "V32_SUPERVISOR_FAILURE_BOUNDARY_INVALID")
    return supplied


def fail_v32_tick_supervisor(
    *,
    checkpoint: Mapping[str, Any],
    failure: Mapping[str, Any],
) -> dict[str, Any]:
    """CAS-transition to an immutable failure prefix without changing progress."""

    failure_digest = verify_v32_tick_supervisor_failure(
        failure, checkpoint=checkpoint
    )
    candidate = _successor_base(checkpoint, updated_at=failure["occurred_at"])
    lane = failure["failure_lane"]
    lanes = dict(checkpoint["lane_states"])
    for key, state in tuple(lanes.items()):
        if state == "ACTIVE":
            lanes[key] = "READY"
    lanes[lane] = "FAILED_CLOSED"
    candidate.update(
        {
            "status": "FAILED_CLOSED",
            "active_permit_kind": None,
            "active_permit_digest": None,
            "lane_states": lanes,
            "failure_lane": lane,
            "failure_ref": f"tick-supervisor/failures/revision-{checkpoint['revision'] + 1:04d}.json",
            "failure_digest": failure_digest,
            "resume_allowed": False,
        }
    )
    result = self_digest(candidate, CHECKPOINT_DIGEST_FIELD)
    verify_v32_tick_supervisor_transition(checkpoint, result)
    return result


def verify_v32_tick_supervisor_transition(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> None:
    """Verify one CAS successor and forbid multi-boundary/counter jumps."""

    before_digest = verify_v32_tick_supervisor_checkpoint(before)
    verify_v32_tick_supervisor_checkpoint(after)
    immutable = (
        "schema_id",
        "schema_version",
        "run_id",
        "experiment_contract_digest",
        "active_authority_digest",
        "total_analysis_cycles",
        "total_outcome_schedules",
        "created_at",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
    )
    if (
        any(before[field] != after[field] for field in immutable)
        or after["revision"] != before["revision"] + 1
        or after["predecessor_checkpoint_digest"] != before_digest
        or _moment(after["updated_at"], "V32_SUPERVISOR_TRANSITION_TIME_INVALID")
        < _moment(before["updated_at"], "V32_SUPERVISOR_TRANSITION_TIME_INVALID")
    ):
        raise V32TickSupervisorError("V32_SUPERVISOR_TRANSITION_CAS_INVALID")
    if after["status"] == "FAILED_CLOSED":
        progress = (
            "accepted_analysis_cycles",
            "scheduled_outcomes",
            "terminal_outcomes",
            "accepted_state_digests",
            "shadow_decision_bundle_digests",
            "outcome_schedule_set_digests",
            "scheduled_schedule_ids",
            "terminal_schedule_ids",
            "current_research_checkpoint_digest",
            "current_outcome_checkpoint_digest",
            "current_timeframe_cache_digest",
            "current_dynamic_state_digest",
            "last_analysis_decision_at",
            "last_source_admission_digest",
            "last_source_admission_physical_sha256",
            "last_proposal_lifecycle_digest",
            "last_selection_lifecycle_digest",
            "last_action_plan_digest",
            "last_commit_envelope_digest",
            "last_shadow_decision_bundle_digest",
            "analysis_completion_binding_digests",
            "last_outcome_batch_digest",
            "next_analysis_cycle_index",
            "next_outcome_tick_index",
        )
        if any(before[field] != after[field] for field in progress):
            raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_PREFIX_MUTATED")
        expected_lanes = dict(before["lane_states"])
        for lane, state in tuple(expected_lanes.items()):
            if state == "ACTIVE":
                expected_lanes[lane] = "READY"
        expected_lanes[after["failure_lane"]] = "FAILED_CLOSED"
        if after["lane_states"] != expected_lanes:
            raise V32TickSupervisorError("V32_SUPERVISOR_FAILURE_LANES_INVALID")
        return
    transition = (before["status"], after["status"])
    allowed = {
        "READY": {"ANALYSIS_TICK_OPEN", "OUTCOME_TICK_OPEN"},
        "ANALYSIS_TICK_OPEN": {"READY", "OUTCOME_ONLY_TAIL"},
        "OUTCOME_TICK_OPEN": {"READY", "OUTCOME_ONLY_TAIL", "TERMINAL_COMPLETE"},
        "OUTCOME_ONLY_TAIL": {"OUTCOME_TICK_OPEN"},
        "TERMINAL_COMPLETE": set(),
        "FAILED_CLOSED": set(),
    }
    if after["status"] not in allowed[before["status"]]:
        raise V32TickSupervisorError("V32_SUPERVISOR_TRANSITION_STATE_INVALID")
    if transition[1] in {"ANALYSIS_TICK_OPEN", "OUTCOME_TICK_OPEN"}:
        counter_fields = (
            "accepted_analysis_cycles",
            "scheduled_outcomes",
            "terminal_outcomes",
            "accepted_state_digests",
            "shadow_decision_bundle_digests",
            "outcome_schedule_set_digests",
            "scheduled_schedule_ids",
            "terminal_schedule_ids",
            "current_research_checkpoint_digest",
            "current_outcome_checkpoint_digest",
            "current_timeframe_cache_digest",
            "current_dynamic_state_digest",
            "last_analysis_decision_at",
            "last_source_admission_digest",
            "last_source_admission_physical_sha256",
            "last_proposal_lifecycle_digest",
            "last_selection_lifecycle_digest",
            "last_action_plan_digest",
            "last_commit_envelope_digest",
            "last_shadow_decision_bundle_digest",
            "analysis_completion_binding_digests",
            "last_outcome_batch_digest",
            "next_analysis_cycle_index",
            "next_outcome_tick_index",
        )
        if any(before[field] != after[field] for field in counter_fields):
            raise V32TickSupervisorError("V32_SUPERVISOR_OPEN_MUTATED_PROGRESS")
        return
    if transition[0] == "ANALYSIS_TICK_OPEN":
        if (
            after["accepted_analysis_cycles"] != before["accepted_analysis_cycles"] + 1
            or after["scheduled_outcomes"] != before["scheduled_outcomes"] + 3
            or after["terminal_outcomes"] != before["terminal_outcomes"]
            or after["terminal_schedule_ids"] != before["terminal_schedule_ids"]
            or after["current_outcome_checkpoint_digest"]
            == before["current_outcome_checkpoint_digest"]
            or after["last_outcome_batch_digest"]
            != before["last_outcome_batch_digest"]
            or after["next_outcome_tick_index"]
            != before["next_outcome_tick_index"]
            or after["accepted_state_digests"][:-1]
            != before["accepted_state_digests"]
            or after["shadow_decision_bundle_digests"][:-1]
            != before["shadow_decision_bundle_digests"]
            or after["outcome_schedule_set_digests"][:-1]
            != before["outcome_schedule_set_digests"]
            or after["analysis_completion_binding_digests"][:-1]
            != before["analysis_completion_binding_digests"]
            or not set(before["scheduled_schedule_ids"]).issubset(
                after["scheduled_schedule_ids"]
            )
        ):
            raise V32TickSupervisorError("V32_SUPERVISOR_ANALYSIS_PROGRESS_INVALID")
    elif transition[0] == "OUTCOME_TICK_OPEN":
        if (
            after["accepted_analysis_cycles"] != before["accepted_analysis_cycles"]
            or after["scheduled_outcomes"] != before["scheduled_outcomes"]
            or not before["terminal_outcomes"] < after["terminal_outcomes"]
            or after["accepted_state_digests"] != before["accepted_state_digests"]
            or after["shadow_decision_bundle_digests"]
            != before["shadow_decision_bundle_digests"]
            or after["outcome_schedule_set_digests"]
            != before["outcome_schedule_set_digests"]
            or after["scheduled_schedule_ids"]
            != before["scheduled_schedule_ids"]
            or after["current_research_checkpoint_digest"]
            != before["current_research_checkpoint_digest"]
            or after["current_timeframe_cache_digest"]
            != before["current_timeframe_cache_digest"]
            or after["current_dynamic_state_digest"]
            != before["current_dynamic_state_digest"]
            or after["last_analysis_decision_at"]
            != before["last_analysis_decision_at"]
            or after["last_source_admission_digest"]
            != before["last_source_admission_digest"]
            or after["last_source_admission_physical_sha256"]
            != before["last_source_admission_physical_sha256"]
            or after["last_proposal_lifecycle_digest"]
            != before["last_proposal_lifecycle_digest"]
            or after["last_selection_lifecycle_digest"]
            != before["last_selection_lifecycle_digest"]
            or after["last_action_plan_digest"]
            != before["last_action_plan_digest"]
            or after["last_commit_envelope_digest"]
            != before["last_commit_envelope_digest"]
            or after["last_shadow_decision_bundle_digest"]
            != before["last_shadow_decision_bundle_digest"]
            or after["analysis_completion_binding_digests"]
            != before["analysis_completion_binding_digests"]
            or after["next_analysis_cycle_index"]
            != before["next_analysis_cycle_index"]
        ):
            raise V32TickSupervisorError("V32_SUPERVISOR_OUTCOME_PROGRESS_INVALID")


__all__ = [
    "CHECKPOINT_DIGEST_FIELD",
    "CHECKPOINT_SCHEMA_ID",
    "FAILURE_CODES_BY_LANE",
    "FAILURE_DIGEST_FIELD",
    "FAILURE_SCHEMA_ID",
    "EXPIRY_PERMIT_SCHEMA_ID",
    "LANES",
    "PERMIT_DIGEST_FIELD",
    "PERMIT_SCHEMA_ID",
    "SUPERVISOR_STATUSES",
    "TICK_KINDS",
    "V32TickSupervisorError",
    "build_v32_analysis_tick_permit",
    "build_v32_outcome_tick_permit",
    "classify_v32_outcome_permit_mode",
    "build_v32_tick_supervisor_checkpoint",
    "build_v32_tick_supervisor_failure",
    "complete_v32_analysis_tick",
    "complete_v32_outcome_tick",
    "complete_v32_outcome_window_expiry",
    "fail_v32_tick_supervisor",
    "open_v32_tick_supervisor_permit",
    "verify_v32_tick_supervisor_checkpoint",
    "verify_v32_tick_supervisor_failure",
    "verify_v32_tick_supervisor_permit",
    "verify_v32_tick_supervisor_transition",
]
