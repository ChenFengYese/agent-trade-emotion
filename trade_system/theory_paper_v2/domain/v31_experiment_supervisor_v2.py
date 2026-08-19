"""Pure contracts for the versioned V3.1 experiment supervisor.

The supervisor does not own research or delayed-outcome semantics.  It owns the
cross-module ordering rule: a new cycle can open only after the preceding
accepted cycle has one durable, legal outcome receipt.  All documents in this
module are non-executable local-research evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest


class V31ExperimentSupervisorV2Error(ValueError):
    """A supervisor document or transition violated the frozen ordering rule."""


SUPERVISOR_CHECKPOINT_SCHEMA_ID = (
    "theory_paper_v31_experiment_supervisor_checkpoint"
)
SUPERVISOR_CHECKPOINT_SCHEMA_VERSION = "2.0.0"
SUPERVISOR_CHECKPOINT_DIGEST_FIELD = "supervisor_checkpoint_digest"

CYCLE_PERMIT_SCHEMA_ID = "theory_paper_v31_experiment_cycle_permit"
CYCLE_PERMIT_SCHEMA_VERSION = "2.0.0"
CYCLE_PERMIT_DIGEST_FIELD = "cycle_permit_digest"

COMMIT_INTENT_SCHEMA_ID = "theory_paper_v31_experiment_cycle_commit_intent"
COMMIT_INTENT_SCHEMA_VERSION = "2.0.0"
COMMIT_INTENT_DIGEST_FIELD = "commit_intent_digest"

SUPERVISOR_FAILURE_SCHEMA_ID = "theory_paper_v31_experiment_supervisor_failure"
SUPERVISOR_FAILURE_SCHEMA_VERSION = "2.0.0"
SUPERVISOR_FAILURE_DIGEST_FIELD = "supervisor_failure_digest"

TOTAL_CYCLES = 8
SUPERVISOR_STATUSES = frozenset(
    {
        "BOOTSTRAPPED",
        "CYCLE_PERMIT_OPEN",
        "COMMIT_RESERVED",
        "AWAITING_OUTCOME",
        "AWAITING_FINAL_OUTCOME",
        "TERMINAL_COMPLETE",
        "FAILED_CLOSED",
    }
)
PERMITTED_OPERATIONS = (
    "SOURCE_QUALIFICATION",
    "FORMAL_PREPARE",
    "AGENT_ATTEMPT_RESERVATION",
)
SUPERVISOR_ROOT_V2 = "supervisor-v2"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "experiment_contract_digest",
        "active_authority_digest",
        "revision",
        "status",
        "total_cycles",
        "current_cycle_index",
        "completed_research_cycles",
        "resolved_outcome_cycles",
        "active_permit_digest",
        "active_commit_intent_digest",
        "research_checkpoint_digest",
        "monitor_checkpoint_digest",
        "last_outcome_receipt_digest",
        "failure_ref",
        "failure_digest",
        "resume_allowed",
        "created_at",
        "updated_at",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    }
)
_PERMIT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "issued_at",
        "supervisor_checkpoint_digest_before_permit",
        "experiment_contract_digest",
        "active_authority_digest",
        "research_checkpoint_digest",
        "monitor_checkpoint_digest",
        "previous_outcome_receipt_digest",
        "resolved_outcomes_before_cycle",
        "decision",
        "permitted_operations",
        "source_scope",
        "external_execution_authority",
        "executable",
        CYCLE_PERMIT_DIGEST_FIELD,
    }
)
_COMMIT_INTENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "reserved_at",
        "cycle_permit_digest",
        "supervisor_checkpoint_digest_before_reservation",
        "research_checkpoint_digest_before_commit",
        "monitor_checkpoint_digest_before_commit",
        "commit_material_digest",
        "recovery_policy",
        "agent_reinvocation_allowed",
        "outcome_collection_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        COMMIT_INTENT_DIGEST_FIELD,
    }
)
_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "occurred_at",
        "status_before_failure",
        "failure_code",
        "failure_summary",
        "supervisor_checkpoint_digest_before_failure",
        "research_checkpoint_digest",
        "monitor_checkpoint_digest",
        "resume_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        SUPERVISOR_FAILURE_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise V31ExperimentSupervisorV2Error(code)
    return value


def _digest(value: Any, code: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31ExperimentSupervisorV2Error(code)
    return value


def _cycle(value: Any, code: str, *, optional: bool = False) -> int | None:
    if optional and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 8:
        raise V31ExperimentSupervisorV2Error(code)
    return value


def _counter(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 8:
        raise V31ExperimentSupervisorV2Error(code)
    return value


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31ExperimentSupervisorV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31ExperimentSupervisorV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31ExperimentSupervisorV2Error(code)
    parsed = parsed.astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise V31ExperimentSupervisorV2Error(code)
    return parsed


def _assert_non_executable_boundary(document: Mapping[str, Any], code: str) -> None:
    if (
        document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V31ExperimentSupervisorV2Error(code)


def cycle_permit_ref_v2(cycle_index: int) -> str:
    cycle = _cycle(cycle_index, "V31_SUPERVISOR_V2_PERMIT_CYCLE_INVALID")
    return f"{SUPERVISOR_ROOT_V2}/cycles/{cycle:04d}/cycle-permit.json"


def commit_intent_ref_v2(cycle_index: int) -> str:
    cycle = _cycle(cycle_index, "V31_SUPERVISOR_V2_COMMIT_CYCLE_INVALID")
    return f"{SUPERVISOR_ROOT_V2}/cycles/{cycle:04d}/commit-intent.json"


def supervisor_failure_ref_v2(revision: int) -> str:
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_FAILURE_REVISION_INVALID"
        )
    return f"{SUPERVISOR_ROOT_V2}/failures/revision-{revision:04d}.json"


def build_bootstrapped_supervisor_checkpoint_v2(
    *,
    run_id: str,
    experiment_contract_digest: str,
    active_authority_digest: str,
    research_checkpoint_digest: str,
    monitor_checkpoint_digest: str,
    created_at: str,
) -> dict[str, Any]:
    """Create the initial cross-store cursor after both owners are initialized."""

    _timestamp(created_at, "V31_SUPERVISOR_V2_CREATED_AT_INVALID")
    checkpoint = self_digest(
        {
            "schema_id": SUPERVISOR_CHECKPOINT_SCHEMA_ID,
            "schema_version": SUPERVISOR_CHECKPOINT_SCHEMA_VERSION,
            "run_id": _text(run_id, "V31_SUPERVISOR_V2_RUN_ID_INVALID"),
            "experiment_contract_digest": _digest(
                experiment_contract_digest,
                "V31_SUPERVISOR_V2_CONTRACT_DIGEST_INVALID",
            ),
            "active_authority_digest": _digest(
                active_authority_digest,
                "V31_SUPERVISOR_V2_AUTHORITY_DIGEST_INVALID",
            ),
            "revision": 0,
            "status": "BOOTSTRAPPED",
            "total_cycles": TOTAL_CYCLES,
            "current_cycle_index": 1,
            "completed_research_cycles": 0,
            "resolved_outcome_cycles": 0,
            "active_permit_digest": None,
            "active_commit_intent_digest": None,
            "research_checkpoint_digest": _digest(
                research_checkpoint_digest,
                "V31_SUPERVISOR_V2_RESEARCH_DIGEST_INVALID",
            ),
            "monitor_checkpoint_digest": _digest(
                monitor_checkpoint_digest,
                "V31_SUPERVISOR_V2_MONITOR_DIGEST_INVALID",
            ),
            "last_outcome_receipt_digest": None,
            "failure_ref": None,
            "failure_digest": None,
            "resume_allowed": True,
            "created_at": created_at,
            "updated_at": created_at,
            "chat_history_is_authority": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    )
    validate_supervisor_checkpoint_v2(checkpoint)
    return checkpoint


def validate_supervisor_checkpoint_v2(document: Mapping[str, Any]) -> str:
    """Validate one exact supervisor checkpoint and all status invariants."""

    try:
        digest = verify_self_digest(document, SUPERVISOR_CHECKPOINT_DIGEST_FIELD)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_DIGEST_INVALID"
        ) from exc
    if (
        not isinstance(document, Mapping)
        or set(document) != _CHECKPOINT_FIELDS
        or document.get("schema_id") != SUPERVISOR_CHECKPOINT_SCHEMA_ID
        or document.get("schema_version") != SUPERVISOR_CHECKPOINT_SCHEMA_VERSION
        or document.get("status") not in SUPERVISOR_STATUSES
        or document.get("total_cycles") != TOTAL_CYCLES
        or document.get("chat_history_is_authority") is not False
    ):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_SCHEMA_INVALID"
        )
    _text(document.get("run_id"), "V31_SUPERVISOR_V2_RUN_ID_INVALID")
    for field in (
        "experiment_contract_digest",
        "active_authority_digest",
        "research_checkpoint_digest",
        "monitor_checkpoint_digest",
    ):
        _digest(document.get(field), "V31_SUPERVISOR_V2_CHECKPOINT_BINDING_INVALID")
    revision = document.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_REVISION_INVALID"
        )
    created = _timestamp(
        document.get("created_at"), "V31_SUPERVISOR_V2_CHECKPOINT_TIME_INVALID"
    )
    updated = _timestamp(
        document.get("updated_at"), "V31_SUPERVISOR_V2_CHECKPOINT_TIME_INVALID"
    )
    if updated < created:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_TIME_INVALID"
        )
    completed = _counter(
        document.get("completed_research_cycles"),
        "V31_SUPERVISOR_V2_CHECKPOINT_COUNTER_INVALID",
    )
    resolved = _counter(
        document.get("resolved_outcome_cycles"),
        "V31_SUPERVISOR_V2_CHECKPOINT_COUNTER_INVALID",
    )
    if resolved > completed:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_COUNTER_INVALID"
        )
    current_cycle = _cycle(
        document.get("current_cycle_index"),
        "V31_SUPERVISOR_V2_CHECKPOINT_CYCLE_INVALID",
        optional=True,
    )
    permit = _digest(
        document.get("active_permit_digest"),
        "V31_SUPERVISOR_V2_CHECKPOINT_PERMIT_INVALID",
        optional=True,
    )
    intent = _digest(
        document.get("active_commit_intent_digest"),
        "V31_SUPERVISOR_V2_CHECKPOINT_INTENT_INVALID",
        optional=True,
    )
    last_outcome = _digest(
        document.get("last_outcome_receipt_digest"),
        "V31_SUPERVISOR_V2_CHECKPOINT_OUTCOME_INVALID",
        optional=True,
    )
    if (resolved == 0) != (last_outcome is None):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_OUTCOME_INVALID"
        )
    status = str(document["status"])
    if status == "BOOTSTRAPPED":
        valid_state = (
            completed == resolved == 0
            and current_cycle == 1
            and permit is None
            and intent is None
        )
    elif status == "CYCLE_PERMIT_OPEN":
        valid_state = (
            completed == resolved
            and current_cycle == completed + 1
            and permit is not None
            and intent is None
        )
    elif status == "COMMIT_RESERVED":
        valid_state = (
            completed == resolved
            and current_cycle == completed + 1
            and permit is not None
            and intent is not None
        )
    elif status == "AWAITING_OUTCOME":
        valid_state = (
            1 <= completed <= 7
            and resolved == completed - 1
            and current_cycle == completed
            and permit is None
            and intent is None
        )
    elif status == "AWAITING_FINAL_OUTCOME":
        valid_state = (
            completed == 8
            and resolved == 7
            and current_cycle == 8
            and permit is None
            and intent is None
        )
    elif status == "TERMINAL_COMPLETE":
        valid_state = (
            completed == resolved == 8
            and current_cycle is None
            and permit is None
            and intent is None
        )
    else:  # FAILED_CLOSED preserves the exact prefix at which failure occurred.
        valid_state = permit is None and intent is None
    if not valid_state:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_STATE_INVALID"
        )
    failure_ref = document.get("failure_ref")
    failure_digest = _digest(
        document.get("failure_digest"),
        "V31_SUPERVISOR_V2_CHECKPOINT_FAILURE_INVALID",
        optional=True,
    )
    if status == "FAILED_CLOSED":
        if (
            not isinstance(failure_ref, str)
            or not failure_ref
            or failure_digest is None
            or document.get("resume_allowed") is not False
        ):
            raise V31ExperimentSupervisorV2Error(
                "V31_SUPERVISOR_V2_CHECKPOINT_FAILURE_INVALID"
            )
    elif (
        failure_ref is not None
        or failure_digest is not None
        or document.get("resume_allowed") is not True
    ):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_CHECKPOINT_FAILURE_INVALID"
        )
    _assert_non_executable_boundary(
        document, "V31_SUPERVISOR_V2_CHECKPOINT_SCOPE_INVALID"
    )
    return digest


def transition_supervisor_checkpoint_v2(
    checkpoint: Mapping[str, Any],
    *,
    status: str,
    current_cycle_index: int | None,
    completed_research_cycles: int,
    resolved_outcome_cycles: int,
    active_permit_digest: str | None,
    active_commit_intent_digest: str | None,
    research_checkpoint_digest: str,
    monitor_checkpoint_digest: str,
    last_outcome_receipt_digest: str | None,
    failure_ref: str | None,
    failure_digest: str | None,
    resume_allowed: bool,
    updated_at: str,
) -> dict[str, Any]:
    """Build and validate one legal CAS successor checkpoint."""

    validate_supervisor_checkpoint_v2(checkpoint)
    candidate = dict(checkpoint)
    candidate.pop(SUPERVISOR_CHECKPOINT_DIGEST_FIELD, None)
    candidate.update(
        {
            "revision": int(checkpoint["revision"]) + 1,
            "status": status,
            "current_cycle_index": current_cycle_index,
            "completed_research_cycles": completed_research_cycles,
            "resolved_outcome_cycles": resolved_outcome_cycles,
            "active_permit_digest": active_permit_digest,
            "active_commit_intent_digest": active_commit_intent_digest,
            "research_checkpoint_digest": research_checkpoint_digest,
            "monitor_checkpoint_digest": monitor_checkpoint_digest,
            "last_outcome_receipt_digest": last_outcome_receipt_digest,
            "failure_ref": failure_ref,
            "failure_digest": failure_digest,
            "resume_allowed": resume_allowed,
            "updated_at": updated_at,
        }
    )
    result = self_digest(candidate, SUPERVISOR_CHECKPOINT_DIGEST_FIELD)
    validate_supervisor_transition_v2(checkpoint, result)
    return result


def validate_supervisor_transition_v2(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> None:
    """Validate monotone state-machine movement without touching persistence."""

    validate_supervisor_checkpoint_v2(before)
    validate_supervisor_checkpoint_v2(after)
    immutable = (
        "schema_id",
        "schema_version",
        "run_id",
        "experiment_contract_digest",
        "active_authority_digest",
        "total_cycles",
        "created_at",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
    )
    if (
        any(before[field] != after[field] for field in immutable)
        or after["revision"] != before["revision"] + 1
        or _timestamp(
            after["updated_at"], "V31_SUPERVISOR_V2_TRANSITION_TIME_INVALID"
        )
        < _timestamp(
            before["updated_at"], "V31_SUPERVISOR_V2_TRANSITION_TIME_INVALID"
        )
    ):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_TRANSITION_INVALID"
        )
    allowed = {
        "BOOTSTRAPPED": {"CYCLE_PERMIT_OPEN", "FAILED_CLOSED"},
        "CYCLE_PERMIT_OPEN": {"COMMIT_RESERVED", "FAILED_CLOSED"},
        "COMMIT_RESERVED": {
            "AWAITING_OUTCOME",
            "AWAITING_FINAL_OUTCOME",
            "FAILED_CLOSED",
        },
        "AWAITING_OUTCOME": {"CYCLE_PERMIT_OPEN", "FAILED_CLOSED"},
        "AWAITING_FINAL_OUTCOME": {"TERMINAL_COMPLETE", "FAILED_CLOSED"},
        "TERMINAL_COMPLETE": set(),
        "FAILED_CLOSED": set(),
    }
    if after["status"] not in allowed[str(before["status"])]:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_TRANSITION_INVALID"
        )
    if after["status"] == "FAILED_CLOSED":
        if (
            after["completed_research_cycles"]
            != before["completed_research_cycles"]
            or after["resolved_outcome_cycles"]
            != before["resolved_outcome_cycles"]
        ):
            raise V31ExperimentSupervisorV2Error(
                "V31_SUPERVISOR_V2_FAILURE_PREFIX_MUTATION_FORBIDDEN"
            )
        return
    transition = (before["status"], after["status"])
    if transition == ("BOOTSTRAPPED", "CYCLE_PERMIT_OPEN"):
        valid = (
            after["current_cycle_index"] == 1
            and after["completed_research_cycles"] == 0
            and after["resolved_outcome_cycles"] == 0
        )
    elif transition == ("AWAITING_OUTCOME", "CYCLE_PERMIT_OPEN"):
        valid = (
            after["current_cycle_index"]
            == int(before["current_cycle_index"]) + 1
            and after["completed_research_cycles"]
            == before["completed_research_cycles"]
            and after["resolved_outcome_cycles"]
            == before["resolved_outcome_cycles"] + 1
        )
    elif transition == ("CYCLE_PERMIT_OPEN", "COMMIT_RESERVED"):
        valid = (
            after["current_cycle_index"] == before["current_cycle_index"]
            and after["completed_research_cycles"]
            == before["completed_research_cycles"]
            and after["resolved_outcome_cycles"]
            == before["resolved_outcome_cycles"]
            and after["active_permit_digest"] == before["active_permit_digest"]
        )
    elif transition in {
        ("COMMIT_RESERVED", "AWAITING_OUTCOME"),
        ("COMMIT_RESERVED", "AWAITING_FINAL_OUTCOME"),
    }:
        valid = (
            after["current_cycle_index"] == before["current_cycle_index"]
            and after["completed_research_cycles"]
            == before["completed_research_cycles"] + 1
            and after["resolved_outcome_cycles"]
            == before["resolved_outcome_cycles"]
        )
    else:  # AWAITING_FINAL_OUTCOME -> TERMINAL_COMPLETE
        valid = (
            before["completed_research_cycles"] == 8
            and before["resolved_outcome_cycles"] == 7
            and after["completed_research_cycles"] == 8
            and after["resolved_outcome_cycles"] == 8
            and after["current_cycle_index"] is None
        )
    if not valid:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_TRANSITION_INVALID"
        )


def build_cycle_permit_v2(
    *,
    checkpoint: Mapping[str, Any],
    cycle_index: int,
    research_checkpoint_digest: str,
    monitor_checkpoint_digest: str,
    previous_outcome_receipt_digest: str | None,
    issued_at: str,
) -> dict[str, Any]:
    """Seal the sole cycle permit against exact live owner checkpoints."""

    validate_supervisor_checkpoint_v2(checkpoint)
    cycle = _cycle(cycle_index, "V31_SUPERVISOR_V2_PERMIT_CYCLE_INVALID")
    if checkpoint["status"] not in {"BOOTSTRAPPED", "AWAITING_OUTCOME"}:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_PERMIT_STATE_INVALID"
        )
    # An AWAITING_OUTCOME checkpoint intentionally trails the just-resolved
    # monitor by one receipt until this permit transition commits.  The next
    # research cycle is therefore derived from the accepted-cycle counter.
    expected_cycle = int(checkpoint["completed_research_cycles"]) + 1
    if cycle != expected_cycle:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_PERMIT_CYCLE_INVALID"
        )
    previous = _digest(
        previous_outcome_receipt_digest,
        "V31_SUPERVISOR_V2_PERMIT_OUTCOME_INVALID",
        optional=True,
    )
    if (cycle == 1) != (previous is None):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_PERMIT_OUTCOME_INVALID"
        )
    _timestamp(issued_at, "V31_SUPERVISOR_V2_PERMIT_TIME_INVALID")
    permit = self_digest(
        {
            "schema_id": CYCLE_PERMIT_SCHEMA_ID,
            "schema_version": CYCLE_PERMIT_SCHEMA_VERSION,
            "run_id": checkpoint["run_id"],
            "cycle_index": cycle,
            "issued_at": issued_at,
            "supervisor_checkpoint_digest_before_permit": checkpoint[
                SUPERVISOR_CHECKPOINT_DIGEST_FIELD
            ],
            "experiment_contract_digest": checkpoint[
                "experiment_contract_digest"
            ],
            "active_authority_digest": checkpoint["active_authority_digest"],
            "research_checkpoint_digest": _digest(
                research_checkpoint_digest,
                "V31_SUPERVISOR_V2_PERMIT_RESEARCH_DIGEST_INVALID",
            ),
            "monitor_checkpoint_digest": _digest(
                monitor_checkpoint_digest,
                "V31_SUPERVISOR_V2_PERMIT_MONITOR_DIGEST_INVALID",
            ),
            "previous_outcome_receipt_digest": previous,
            "resolved_outcomes_before_cycle": cycle - 1,
            "decision": "ALLOW_CYCLE_PIPELINE",
            "permitted_operations": list(PERMITTED_OPERATIONS),
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        CYCLE_PERMIT_DIGEST_FIELD,
    )
    validate_cycle_permit_v2(permit)
    return permit


def validate_cycle_permit_v2(document: Mapping[str, Any]) -> str:
    try:
        digest = verify_self_digest(document, CYCLE_PERMIT_DIGEST_FIELD)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_PERMIT_DIGEST_INVALID"
        ) from exc
    if (
        not isinstance(document, Mapping)
        or set(document) != _PERMIT_FIELDS
        or document.get("schema_id") != CYCLE_PERMIT_SCHEMA_ID
        or document.get("schema_version") != CYCLE_PERMIT_SCHEMA_VERSION
        or document.get("decision") != "ALLOW_CYCLE_PIPELINE"
        or document.get("permitted_operations") != list(PERMITTED_OPERATIONS)
    ):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_PERMIT_SCHEMA_INVALID"
        )
    _text(document.get("run_id"), "V31_SUPERVISOR_V2_PERMIT_RUN_INVALID")
    cycle = _cycle(document.get("cycle_index"), "V31_SUPERVISOR_V2_PERMIT_CYCLE_INVALID")
    _timestamp(document.get("issued_at"), "V31_SUPERVISOR_V2_PERMIT_TIME_INVALID")
    for field in (
        "supervisor_checkpoint_digest_before_permit",
        "experiment_contract_digest",
        "active_authority_digest",
        "research_checkpoint_digest",
        "monitor_checkpoint_digest",
    ):
        _digest(document.get(field), "V31_SUPERVISOR_V2_PERMIT_BINDING_INVALID")
    previous = _digest(
        document.get("previous_outcome_receipt_digest"),
        "V31_SUPERVISOR_V2_PERMIT_OUTCOME_INVALID",
        optional=True,
    )
    if (
        (cycle == 1) != (previous is None)
        or document.get("resolved_outcomes_before_cycle") != cycle - 1
    ):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_PERMIT_OUTCOME_INVALID"
        )
    _assert_non_executable_boundary(
        document, "V31_SUPERVISOR_V2_PERMIT_SCOPE_INVALID"
    )
    return digest


def build_commit_intent_v2(
    *,
    checkpoint: Mapping[str, Any],
    cycle_permit_digest: str,
    commit_material_digest: str,
    reserved_at: str,
) -> dict[str, Any]:
    """Seal deterministic commit material before either owner checkpoint moves."""

    validate_supervisor_checkpoint_v2(checkpoint)
    if checkpoint["status"] != "CYCLE_PERMIT_OPEN":
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_COMMIT_STATE_INVALID"
        )
    permit_digest = _digest(
        cycle_permit_digest, "V31_SUPERVISOR_V2_COMMIT_PERMIT_INVALID"
    )
    if permit_digest != checkpoint["active_permit_digest"]:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_COMMIT_PERMIT_INVALID"
        )
    _timestamp(reserved_at, "V31_SUPERVISOR_V2_COMMIT_TIME_INVALID")
    intent = self_digest(
        {
            "schema_id": COMMIT_INTENT_SCHEMA_ID,
            "schema_version": COMMIT_INTENT_SCHEMA_VERSION,
            "run_id": checkpoint["run_id"],
            "cycle_index": checkpoint["current_cycle_index"],
            "reserved_at": reserved_at,
            "cycle_permit_digest": permit_digest,
            "supervisor_checkpoint_digest_before_reservation": checkpoint[
                SUPERVISOR_CHECKPOINT_DIGEST_FIELD
            ],
            "research_checkpoint_digest_before_commit": checkpoint[
                "research_checkpoint_digest"
            ],
            "monitor_checkpoint_digest_before_commit": checkpoint[
                "monitor_checkpoint_digest"
            ],
            "commit_material_digest": _digest(
                commit_material_digest,
                "V31_SUPERVISOR_V2_COMMIT_MATERIAL_INVALID",
            ),
            "recovery_policy": "LOCAL_IDEMPOTENT_WRITES_ONLY",
            "agent_reinvocation_allowed": False,
            "outcome_collection_allowed": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        COMMIT_INTENT_DIGEST_FIELD,
    )
    validate_commit_intent_v2(intent)
    return intent


def validate_commit_intent_v2(document: Mapping[str, Any]) -> str:
    try:
        digest = verify_self_digest(document, COMMIT_INTENT_DIGEST_FIELD)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_COMMIT_DIGEST_INVALID"
        ) from exc
    if (
        not isinstance(document, Mapping)
        or set(document) != _COMMIT_INTENT_FIELDS
        or document.get("schema_id") != COMMIT_INTENT_SCHEMA_ID
        or document.get("schema_version") != COMMIT_INTENT_SCHEMA_VERSION
        or document.get("recovery_policy") != "LOCAL_IDEMPOTENT_WRITES_ONLY"
        or document.get("agent_reinvocation_allowed") is not False
        or document.get("outcome_collection_allowed") is not False
    ):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_COMMIT_SCHEMA_INVALID"
        )
    _text(document.get("run_id"), "V31_SUPERVISOR_V2_COMMIT_RUN_INVALID")
    _cycle(document.get("cycle_index"), "V31_SUPERVISOR_V2_COMMIT_CYCLE_INVALID")
    _timestamp(document.get("reserved_at"), "V31_SUPERVISOR_V2_COMMIT_TIME_INVALID")
    for field in (
        "cycle_permit_digest",
        "supervisor_checkpoint_digest_before_reservation",
        "research_checkpoint_digest_before_commit",
        "monitor_checkpoint_digest_before_commit",
        "commit_material_digest",
    ):
        _digest(document.get(field), "V31_SUPERVISOR_V2_COMMIT_BINDING_INVALID")
    _assert_non_executable_boundary(
        document, "V31_SUPERVISOR_V2_COMMIT_SCOPE_INVALID"
    )
    return digest


def build_supervisor_failure_v2(
    *,
    checkpoint: Mapping[str, Any],
    failure_code: str,
    failure_summary: str,
    occurred_at: str,
    research_checkpoint_digest: str,
    monitor_checkpoint_digest: str,
) -> dict[str, Any]:
    """Seal the permanent failure prefix; a failed supervisor cannot resume."""

    validate_supervisor_checkpoint_v2(checkpoint)
    if checkpoint["status"] in {"TERMINAL_COMPLETE", "FAILED_CLOSED"}:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_FAILURE_TRANSITION_FORBIDDEN"
        )
    _timestamp(occurred_at, "V31_SUPERVISOR_V2_FAILURE_TIME_INVALID")
    failure = self_digest(
        {
            "schema_id": SUPERVISOR_FAILURE_SCHEMA_ID,
            "schema_version": SUPERVISOR_FAILURE_SCHEMA_VERSION,
            "run_id": checkpoint["run_id"],
            "cycle_index": checkpoint["current_cycle_index"],
            "occurred_at": occurred_at,
            "status_before_failure": checkpoint["status"],
            "failure_code": _text(
                failure_code, "V31_SUPERVISOR_V2_FAILURE_CODE_INVALID"
            ),
            "failure_summary": _text(
                failure_summary, "V31_SUPERVISOR_V2_FAILURE_SUMMARY_INVALID"
            ),
            "supervisor_checkpoint_digest_before_failure": checkpoint[
                SUPERVISOR_CHECKPOINT_DIGEST_FIELD
            ],
            "research_checkpoint_digest": _digest(
                research_checkpoint_digest,
                "V31_SUPERVISOR_V2_FAILURE_RESEARCH_DIGEST_INVALID",
            ),
            "monitor_checkpoint_digest": _digest(
                monitor_checkpoint_digest,
                "V31_SUPERVISOR_V2_FAILURE_MONITOR_DIGEST_INVALID",
            ),
            "resume_allowed": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        SUPERVISOR_FAILURE_DIGEST_FIELD,
    )
    validate_supervisor_failure_v2(failure)
    return failure


def validate_supervisor_failure_v2(document: Mapping[str, Any]) -> str:
    try:
        digest = verify_self_digest(document, SUPERVISOR_FAILURE_DIGEST_FIELD)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_FAILURE_DIGEST_INVALID"
        ) from exc
    if (
        not isinstance(document, Mapping)
        or set(document) != _FAILURE_FIELDS
        or document.get("schema_id") != SUPERVISOR_FAILURE_SCHEMA_ID
        or document.get("schema_version") != SUPERVISOR_FAILURE_SCHEMA_VERSION
        or document.get("status_before_failure") not in SUPERVISOR_STATUSES
        - {"TERMINAL_COMPLETE", "FAILED_CLOSED"}
        or document.get("resume_allowed") is not False
    ):
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_FAILURE_SCHEMA_INVALID"
        )
    _text(document.get("run_id"), "V31_SUPERVISOR_V2_FAILURE_RUN_INVALID")
    _cycle(
        document.get("cycle_index"),
        "V31_SUPERVISOR_V2_FAILURE_CYCLE_INVALID",
    )
    _timestamp(document.get("occurred_at"), "V31_SUPERVISOR_V2_FAILURE_TIME_INVALID")
    _text(document.get("failure_code"), "V31_SUPERVISOR_V2_FAILURE_CODE_INVALID")
    _text(
        document.get("failure_summary"),
        "V31_SUPERVISOR_V2_FAILURE_SUMMARY_INVALID",
    )
    for field in (
        "supervisor_checkpoint_digest_before_failure",
        "research_checkpoint_digest",
        "monitor_checkpoint_digest",
    ):
        _digest(document.get(field), "V31_SUPERVISOR_V2_FAILURE_BINDING_INVALID")
    _assert_non_executable_boundary(
        document, "V31_SUPERVISOR_V2_FAILURE_SCOPE_INVALID"
    )
    return digest


def validate_permitted_operation_v2(
    permit: Mapping[str, Any], *, operation: str
) -> None:
    """Pure operation-level guard used before each successor pipeline stage."""

    validate_cycle_permit_v2(permit)
    if operation not in PERMITTED_OPERATIONS:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_OPERATION_INVALID"
        )
    if operation not in permit["permitted_operations"]:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_OPERATION_NOT_PERMITTED"
        )


def exact_supervisor_document_fields_v2(schema_id: str) -> Sequence[str]:
    """Expose stable field names for strict adapters without exposing internals."""

    fields = {
        SUPERVISOR_CHECKPOINT_SCHEMA_ID: _CHECKPOINT_FIELDS,
        CYCLE_PERMIT_SCHEMA_ID: _PERMIT_FIELDS,
        COMMIT_INTENT_SCHEMA_ID: _COMMIT_INTENT_FIELDS,
        SUPERVISOR_FAILURE_SCHEMA_ID: _FAILURE_FIELDS,
    }.get(schema_id)
    if fields is None:
        raise V31ExperimentSupervisorV2Error(
            "V31_SUPERVISOR_V2_SCHEMA_ID_INVALID"
        )
    return tuple(sorted(fields))


__all__ = [
    "COMMIT_INTENT_DIGEST_FIELD",
    "COMMIT_INTENT_SCHEMA_ID",
    "COMMIT_INTENT_SCHEMA_VERSION",
    "CYCLE_PERMIT_DIGEST_FIELD",
    "CYCLE_PERMIT_SCHEMA_ID",
    "CYCLE_PERMIT_SCHEMA_VERSION",
    "PERMITTED_OPERATIONS",
    "SUPERVISOR_CHECKPOINT_DIGEST_FIELD",
    "SUPERVISOR_CHECKPOINT_SCHEMA_ID",
    "SUPERVISOR_CHECKPOINT_SCHEMA_VERSION",
    "SUPERVISOR_FAILURE_DIGEST_FIELD",
    "SUPERVISOR_FAILURE_SCHEMA_ID",
    "SUPERVISOR_FAILURE_SCHEMA_VERSION",
    "SUPERVISOR_ROOT_V2",
    "SUPERVISOR_STATUSES",
    "TOTAL_CYCLES",
    "V31ExperimentSupervisorV2Error",
    "build_bootstrapped_supervisor_checkpoint_v2",
    "build_commit_intent_v2",
    "build_cycle_permit_v2",
    "build_supervisor_failure_v2",
    "commit_intent_ref_v2",
    "cycle_permit_ref_v2",
    "exact_supervisor_document_fields_v2",
    "transition_supervisor_checkpoint_v2",
    "supervisor_failure_ref_v2",
    "validate_commit_intent_v2",
    "validate_cycle_permit_v2",
    "validate_permitted_operation_v2",
    "validate_supervisor_checkpoint_v2",
    "validate_supervisor_failure_v2",
    "validate_supervisor_transition_v2",
]
