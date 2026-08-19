"""Application use cases for the versioned V3.1 experiment supervisor.

This module coordinates only public store contracts.  It never calls a market
adapter or Agent and never edits the research or monitor checkpoints.  Its sole
authority is to open/close the next-cycle barrier around those two owners.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Protocol

from .ports import V31MonitorStorePort, V31ResearchStorePort
from ..domain.contracts.canonical import verify_self_digest
from ..domain.v31_experiment_supervisor_v2 import (
    COMMIT_INTENT_DIGEST_FIELD,
    CYCLE_PERMIT_DIGEST_FIELD,
    SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    SUPERVISOR_FAILURE_DIGEST_FIELD,
    build_bootstrapped_supervisor_checkpoint_v2,
    build_commit_intent_v2,
    build_cycle_permit_v2,
    build_supervisor_failure_v2,
    commit_intent_ref_v2,
    cycle_permit_ref_v2,
    supervisor_failure_ref_v2,
    transition_supervisor_checkpoint_v2,
    validate_cycle_permit_v2,
    validate_permitted_operation_v2,
    validate_supervisor_checkpoint_v2,
)


class V31ExperimentSupervisorV2WorkflowError(ValueError):
    """The unified barrier could not advance without weakening chronology."""


class V31SupervisorStoreV2Port(Protocol):
    """Write-once supervisor artifacts plus one compare-and-swap checkpoint."""

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...

    def document_exists(self, *, relative_ref: str) -> bool: ...

    def initialize_checkpoint(
        self, *, checkpoint: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTATION_OUTCOMES = frozenset(
    {"FULFILLED", "PARTIAL", "FALSIFIED", "EXPIRED", "UNKNOWN"}
)
_PATH_OUTCOMES = frozenset({"SUPPORTED", "FALSIFIED", "UNRESOLVED", "OTHER"})


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 8:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_CYCLE_INVALID"
        )
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31ExperimentSupervisorV2WorkflowError(code)
    return value


def _lists(checkpoint: Mapping[str, Any]) -> tuple[list[Any], list[Any], list[Any]]:
    plans = checkpoint.get("plan_bindings")
    attempts = checkpoint.get("resolution_attempt_bindings")
    outcomes = checkpoint.get("outcome_bindings")
    if (
        not isinstance(plans, list)
        or not isinstance(attempts, list)
        or not isinstance(outcomes, list)
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_MONITOR_COUNTS_INVALID"
        )
    return plans, attempts, outcomes


def _checkpoint_digest(checkpoint: Mapping[str, Any], *, owner: str) -> str:
    return _digest(
        checkpoint.get("checkpoint_digest"),
        f"V31_SUPERVISOR_V2_{owner}_CHECKPOINT_DIGEST_INVALID",
    )


def _load_owner_checkpoints(
    *,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    try:
        research = research_store.load_checkpoint(run_id=run_id)
        monitor = monitor_store.load_checkpoint(run_id=run_id)
    except Exception as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_OWNER_CHECKPOINT_UNAVAILABLE"
        ) from exc
    if (
        research.get("run_id") != run_id
        or monitor.get("run_id") != run_id
        or research.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or monitor.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or research.get("executable") is not False
        or monitor.get("executable") is not False
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_OWNER_SCOPE_INVALID"
        )
    _checkpoint_digest(research, owner="RESEARCH")
    _checkpoint_digest(monitor, owner="MONITOR")
    return research, monitor


def _assert_identity_bindings(
    *,
    supervisor: Mapping[str, Any],
    research: Mapping[str, Any],
    monitor: Mapping[str, Any],
) -> None:
    if (
        monitor.get("experiment_contract_digest")
        != supervisor.get("experiment_contract_digest")
        or (
            research.get("current_authority_digest") is not None
            and research.get("current_authority_digest")
            != supervisor.get("active_authority_digest")
        )
        or research.get("total_cycles") != 8
        or monitor.get("total_cycles") != 8
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_OWNER_IDENTITY_MISMATCH"
        )


def _replay_outcomes(
    *,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    monitor: Mapping[str, Any],
) -> str | None:
    """Replay every outcome binding; UNKNOWN receipts remain legitimate receipts."""

    _plans, _attempts, outcomes = _lists(monitor)
    previous_digest: str | None = None
    for cycle_index, binding in enumerate(outcomes, start=1):
        if not isinstance(binding, Mapping) or binding.get("cycle_index") != cycle_index:
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_OUTCOME_SEQUENCE_INVALID"
            )
        ref = binding.get("outcome_receipt_ref")
        digest = _digest(
            binding.get("outcome_receipt_digest"),
            "V31_SUPERVISOR_V2_OUTCOME_BINDING_INVALID",
        )
        if not isinstance(ref, str) or not ref:
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_OUTCOME_BINDING_INVALID"
            )
        try:
            receipt = monitor_store.read_document(
                relative_ref=ref,
                digest_field="outcome_receipt_digest",
                expected_semantic_digest=digest,
            )
            supplied = verify_self_digest(receipt, "outcome_receipt_digest")
            physical = monitor_store.artifact_binding(
                relative_ref=ref,
                digest_field="outcome_receipt_digest",
                expected_semantic_digest=digest,
            )
        except Exception as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_OUTCOME_REPLAY_INVALID"
            ) from exc
        if (
            supplied != digest
            or receipt.get("run_id") != run_id
            or receipt.get("cycle_index") != cycle_index
            or receipt.get("previous_outcome_receipt_digest") != previous_digest
            or receipt.get("expectation_outcome") not in _EXPECTATION_OUTCOMES
            or receipt.get("path_outcome") not in _PATH_OUTCOMES
            or physical.get("semantic_digest") != digest
            or (
                binding.get("outcome_receipt_physical_sha256") is not None
                and physical.get("physical_sha256")
                != binding.get("outcome_receipt_physical_sha256")
            )
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_OUTCOME_REPLAY_INVALID"
            )
        if receipt.get("expectation_outcome") == "UNKNOWN" and (
            receipt.get("path_outcome") != "UNRESOLVED"
            or receipt.get("coverage_loss") is not True
            or receipt.get("unknown_counted_as_coverage_loss") is not True
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_UNKNOWN_OUTCOME_INVALID"
            )
        previous_digest = digest
    if monitor.get("last_outcome_receipt_digest") != previous_digest:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_OUTCOME_HEAD_INVALID"
        )
    return previous_digest


def _validate_permit_snapshot(
    *,
    supervisor: Mapping[str, Any],
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    research: Mapping[str, Any],
    monitor: Mapping[str, Any],
    cycle_index: int,
) -> str | None:
    cycle = _cycle(cycle_index)
    _assert_identity_bindings(
        supervisor=supervisor, research=research, monitor=monitor
    )
    plans, attempts, outcomes = _lists(monitor)
    expected_prior = cycle - 1
    if monitor.get("status") == "FAILED_CLOSED" or monitor.get("resume_allowed") is not True:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_MONITOR_FAILED_CLOSED"
        )
    if len(attempts) > len(outcomes):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_RESERVED_ATTEMPT_WITHOUT_OUTCOME"
        )
    if len(plans) > len(outcomes):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_PRIOR_OUTCOME_MISSING"
        )
    if (
        research.get("status") != "READY_FOR_CYCLE"
        or research.get("completed_cycles") != expected_prior
        or research.get("next_cycle_index") != cycle
        or research.get("active_cycle_index") is not None
        or research.get("resume_allowed") is not True
        or research.get("failure_digest") is not None
        or monitor.get("status") != "ACTIVE"
        or len(plans) != expected_prior
        or len(attempts) != expected_prior
        or len(outcomes) != expected_prior
        or monitor.get("failure_digest") is not None
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_PERMIT_OWNER_STATE_INVALID"
        )
    last_outcome = _replay_outcomes(
        monitor_store=monitor_store, run_id=str(supervisor["run_id"]), monitor=monitor
    )
    if cycle == 1:
        if last_outcome is not None:
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_GENESIS_OUTCOME_FORBIDDEN"
            )
    else:
        last_plan = plans[-1]
        if (
            not isinstance(last_plan, Mapping)
            or last_plan.get("cycle_index") != cycle - 1
            or last_plan.get("accepted_state_digest")
            != research.get("accepted_state_digest")
            or last_outcome is None
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_RESEARCH_MONITOR_CROSS_BINDING_INVALID"
            )
        accepted_ref = research.get("accepted_state_ref")
        accepted_digest = research.get("accepted_state_digest")
        if not isinstance(accepted_ref, str) or not isinstance(accepted_digest, str):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_RESEARCH_MONITOR_CROSS_BINDING_INVALID"
            )
        try:
            accepted = research_store.read_document(
                relative_ref=accepted_ref,
                digest_field="accepted_state_digest",
                expected_semantic_digest=accepted_digest,
            )
        except Exception as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_ACCEPTED_STATE_REPLAY_INVALID"
            ) from exc
        if (
            accepted.get("run_id") != supervisor.get("run_id")
            or accepted.get("cycle_index") != cycle - 1
            or accepted.get("accepted_state_digest") != accepted_digest
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_ACCEPTED_STATE_REPLAY_INVALID"
            )
    return last_outcome


def _validate_committed_snapshot(
    *,
    supervisor: Mapping[str, Any],
    monitor_store: V31MonitorStorePort,
    research: Mapping[str, Any],
    monitor: Mapping[str, Any],
    cycle_index: int,
) -> str | None:
    cycle = _cycle(cycle_index)
    _assert_identity_bindings(
        supervisor=supervisor, research=research, monitor=monitor
    )
    plans, attempts, outcomes = _lists(monitor)
    expected_research_status = "TERMINAL" if cycle == 8 else "READY_FOR_CYCLE"
    if monitor.get("status") == "FAILED_CLOSED" or monitor.get("resume_allowed") is not True:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_MONITOR_FAILED_CLOSED"
        )
    if (
        research.get("status") != expected_research_status
        or research.get("completed_cycles") != cycle
        or research.get("next_cycle_index") != cycle + 1
        or research.get("active_cycle_index") is not None
        or research.get("failure_digest") is not None
        or research.get("resume_allowed") is not True
        or monitor.get("status") != "ACTIVE"
        or len(plans) != cycle
        or len(attempts) != cycle - 1
        or len(outcomes) != cycle - 1
        or monitor.get("failure_digest") is not None
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_COMMIT_OWNER_STATE_INVALID"
        )
    if (
        not isinstance(plans[-1], Mapping)
        or plans[-1].get("cycle_index") != cycle
        or plans[-1].get("accepted_state_digest")
        != research.get("accepted_state_digest")
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_COMMIT_CROSS_BINDING_INVALID"
        )
    previous = _replay_outcomes(
        monitor_store=monitor_store,
        run_id=str(supervisor["run_id"]),
        monitor=monitor,
    )
    if previous != supervisor.get("last_outcome_receipt_digest"):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_COMMIT_OUTCOME_PREFIX_DRIFT"
        )
    return previous


def _validate_terminal_snapshot(
    *,
    supervisor: Mapping[str, Any],
    monitor_store: V31MonitorStorePort,
    research: Mapping[str, Any],
    monitor: Mapping[str, Any],
) -> str:
    _assert_identity_bindings(
        supervisor=supervisor, research=research, monitor=monitor
    )
    plans, attempts, outcomes = _lists(monitor)
    if (
        research.get("status") != "TERMINAL"
        or research.get("completed_cycles") != 8
        or research.get("next_cycle_index") != 9
        or research.get("failure_digest") is not None
        or research.get("resume_allowed") is not True
        or monitor.get("status") != "TERMINAL"
        or monitor.get("failure_digest") is not None
        or monitor.get("resume_allowed") is not True
        or len(plans) != 8
        or len(attempts) != 8
        or len(outcomes) != 8
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_TERMINAL_EVIDENCE_INCOMPLETE"
        )
    last = _replay_outcomes(
        monitor_store=monitor_store,
        run_id=str(supervisor["run_id"]),
        monitor=monitor,
    )
    if last is None:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_TERMINAL_EVIDENCE_INCOMPLETE"
        )
    return last


def initialize_v31_experiment_supervisor_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    experiment_contract_digest: str,
    active_authority_digest: str,
    created_at: str,
) -> Mapping[str, Any]:
    """Bootstrap only after both owner checkpoints are valid cycle-1 genesis."""

    research, monitor = _load_owner_checkpoints(
        research_store=research_store, monitor_store=monitor_store, run_id=run_id
    )
    seed = {
        "run_id": run_id,
        "experiment_contract_digest": _digest(
            experiment_contract_digest,
            "V31_SUPERVISOR_V2_CONTRACT_DIGEST_INVALID",
        ),
        "active_authority_digest": _digest(
            active_authority_digest,
            "V31_SUPERVISOR_V2_AUTHORITY_DIGEST_INVALID",
        ),
    }
    # Use the same owner rule used for later permits; cycle one admits no outcome.
    _validate_permit_snapshot(
        supervisor=seed,
        research_store=research_store,
        monitor_store=monitor_store,
        research=research,
        monitor=monitor,
        cycle_index=1,
    )
    checkpoint = build_bootstrapped_supervisor_checkpoint_v2(
        run_id=run_id,
        experiment_contract_digest=experiment_contract_digest,
        active_authority_digest=active_authority_digest,
        research_checkpoint_digest=_checkpoint_digest(
            research, owner="RESEARCH"
        ),
        monitor_checkpoint_digest=_checkpoint_digest(monitor, owner="MONITOR"),
        created_at=created_at,
    )
    return supervisor_store.initialize_checkpoint(checkpoint=checkpoint)


def v31_experiment_supervisor_status_v2(
    *, supervisor_store: V31SupervisorStoreV2Port, run_id: str
) -> Mapping[str, Any]:
    """Return the durable cross-owner cursor without advancing either owner."""

    checkpoint = supervisor_store.load_checkpoint(run_id=run_id)
    validate_supervisor_checkpoint_v2(checkpoint)
    return {
        "run_id": run_id,
        "status": checkpoint["status"],
        "current_cycle_index": checkpoint["current_cycle_index"],
        "completed_research_cycles": checkpoint["completed_research_cycles"],
        "resolved_outcome_cycles": checkpoint["resolved_outcome_cycles"],
        "resume_allowed": checkpoint["resume_allowed"],
        "supervisor_checkpoint_digest": checkpoint[
            SUPERVISOR_CHECKPOINT_DIGEST_FIELD
        ],
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def open_v31_cycle_permit_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    issued_at: str,
) -> Mapping[str, Any]:
    """Open the next pipeline only when research and monitor counts are equal."""

    checkpoint = supervisor_store.load_checkpoint(run_id=run_id)
    validate_supervisor_checkpoint_v2(checkpoint)
    if checkpoint["status"] == "CYCLE_PERMIT_OPEN":
        cycle = int(checkpoint["current_cycle_index"])
        binding = supervisor_store.artifact_binding(
            relative_ref=cycle_permit_ref_v2(cycle),
            digest_field=CYCLE_PERMIT_DIGEST_FIELD,
            expected_semantic_digest=str(checkpoint["active_permit_digest"]),
        )
        verified = verify_v31_cycle_permit_live_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            permit_binding=binding,
            operation="FORMAL_PREPARE",
        )
        return {
            "status": "CYCLE_PERMIT_OPEN",
            "cycle_index": cycle,
            "cycle_permit": verified["cycle_permit"],
            "cycle_permit_binding": binding,
            "supervisor_checkpoint": dict(checkpoint),
        }
    if checkpoint["status"] not in {"BOOTSTRAPPED", "AWAITING_OUTCOME"}:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_NOT_READY_FOR_PERMIT"
        )
    cycle = (
        1
        if checkpoint["status"] == "BOOTSTRAPPED"
        else int(checkpoint["completed_research_cycles"]) + 1
    )
    research, monitor = _load_owner_checkpoints(
        research_store=research_store, monitor_store=monitor_store, run_id=run_id
    )
    if monitor.get("status") == "FAILED_CLOSED" or monitor.get("resume_allowed") is False:
        fail_v31_experiment_supervisor_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            failure_code="MONITOR_FAILED_CLOSED",
            failure_summary=(
                "The monitor owner is permanently closed; no successor cycle "
                "permit can be issued."
            ),
            occurred_at=issued_at,
        )
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_MONITOR_FAILED_CLOSED"
        )
    previous = _validate_permit_snapshot(
        supervisor=checkpoint,
        research_store=research_store,
        monitor_store=monitor_store,
        research=research,
        monitor=monitor,
        cycle_index=cycle,
    )
    if checkpoint["status"] == "BOOTSTRAPPED" and (
        _checkpoint_digest(research, owner="RESEARCH")
        != checkpoint["research_checkpoint_digest"]
        or _checkpoint_digest(monitor, owner="MONITOR")
        != checkpoint["monitor_checkpoint_digest"]
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_BOOTSTRAP_DIGEST_STALE"
        )
    if checkpoint["status"] == "AWAITING_OUTCOME":
        _plans, _attempts, outcomes = _lists(monitor)
        prefix_head = (
            None
            if len(outcomes) == 1
            else outcomes[-2].get("outcome_receipt_digest")
        )
        if (
            _checkpoint_digest(research, owner="RESEARCH")
            != checkpoint["research_checkpoint_digest"]
            or prefix_head != checkpoint["last_outcome_receipt_digest"]
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_AWAITING_PREFIX_STALE"
            )
    permit_ref = cycle_permit_ref_v2(cycle)
    research_digest = _checkpoint_digest(research, owner="RESEARCH")
    monitor_digest = _checkpoint_digest(monitor, owner="MONITOR")
    if supervisor_store.document_exists(relative_ref=permit_ref):
        permit = supervisor_store.read_document(
            relative_ref=permit_ref,
            digest_field=CYCLE_PERMIT_DIGEST_FIELD,
        )
        validate_cycle_permit_v2(permit)
        if (
            permit.get("run_id") != run_id
            or permit.get("cycle_index") != cycle
            or permit.get("supervisor_checkpoint_digest_before_permit")
            != checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
            or permit.get("research_checkpoint_digest") != research_digest
            or permit.get("monitor_checkpoint_digest") != monitor_digest
            or permit.get("previous_outcome_receipt_digest") != previous
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_ORPHAN_PERMIT_CONFLICT"
            )
        permit_binding = supervisor_store.artifact_binding(
            relative_ref=permit_ref,
            digest_field=CYCLE_PERMIT_DIGEST_FIELD,
            expected_semantic_digest=str(permit[CYCLE_PERMIT_DIGEST_FIELD]),
        )
    else:
        permit = build_cycle_permit_v2(
            checkpoint=checkpoint,
            cycle_index=cycle,
            research_checkpoint_digest=research_digest,
            monitor_checkpoint_digest=monitor_digest,
            previous_outcome_receipt_digest=previous,
            issued_at=issued_at,
        )
        permit_binding = supervisor_store.write_document(
            relative_ref=permit_ref,
            document=permit,
            digest_field=CYCLE_PERMIT_DIGEST_FIELD,
        )
    candidate = transition_supervisor_checkpoint_v2(
        checkpoint,
        status="CYCLE_PERMIT_OPEN",
        current_cycle_index=cycle,
        completed_research_cycles=cycle - 1,
        resolved_outcome_cycles=cycle - 1,
        active_permit_digest=permit[CYCLE_PERMIT_DIGEST_FIELD],
        active_commit_intent_digest=None,
        research_checkpoint_digest=research_digest,
        monitor_checkpoint_digest=monitor_digest,
        last_outcome_receipt_digest=previous,
        failure_ref=None,
        failure_digest=None,
        resume_allowed=True,
        updated_at=str(permit["issued_at"]),
    )
    durable = supervisor_store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(
            checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
        ),
        checkpoint=candidate,
    )
    return {
        "status": "CYCLE_PERMIT_OPEN",
        "cycle_index": cycle,
        "cycle_permit": permit,
        "cycle_permit_binding": dict(permit_binding),
        "supervisor_checkpoint": dict(durable),
    }


def verify_v31_cycle_permit_live_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    permit_binding: Mapping[str, Any],
    operation: str,
) -> Mapping[str, Any]:
    """Replay a permit and reject any owner-checkpoint drift before a stage."""

    try:
        permit = supervisor_store.read_document(
            relative_ref=str(permit_binding["relative_ref"]),
            digest_field=CYCLE_PERMIT_DIGEST_FIELD,
            expected_semantic_digest=str(permit_binding["semantic_digest"]),
        )
        permit_digest = validate_cycle_permit_v2(permit)
        validate_permitted_operation_v2(permit, operation=operation)
    except (KeyError, TypeError, ValueError) as exc:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_PERMIT_REPLAY_INVALID"
        ) from exc
    checkpoint = supervisor_store.load_checkpoint(run_id=run_id)
    if (
        checkpoint.get("status") != "CYCLE_PERMIT_OPEN"
        or checkpoint.get("active_permit_digest") != permit_digest
        or permit.get("run_id") != run_id
        or permit.get("cycle_index") != checkpoint.get("current_cycle_index")
        or permit.get("experiment_contract_digest")
        != checkpoint.get("experiment_contract_digest")
        or permit.get("active_authority_digest")
        != checkpoint.get("active_authority_digest")
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_PERMIT_NOT_LIVE"
        )
    research, monitor = _load_owner_checkpoints(
        research_store=research_store, monitor_store=monitor_store, run_id=run_id
    )
    previous = _validate_permit_snapshot(
        supervisor=checkpoint,
        research_store=research_store,
        monitor_store=monitor_store,
        research=research,
        monitor=monitor,
        cycle_index=int(permit["cycle_index"]),
    )
    if (
        permit.get("research_checkpoint_digest")
        != _checkpoint_digest(research, owner="RESEARCH")
        or permit.get("monitor_checkpoint_digest")
        != _checkpoint_digest(monitor, owner="MONITOR")
        or permit.get("previous_outcome_receipt_digest") != previous
        or checkpoint.get("research_checkpoint_digest")
        != permit.get("research_checkpoint_digest")
        or checkpoint.get("monitor_checkpoint_digest")
        != permit.get("monitor_checkpoint_digest")
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_PERMIT_STALE"
        )
    return {
        "status": "PERMIT_LIVE",
        "operation": operation,
        "cycle_permit": dict(permit),
        "supervisor_checkpoint": dict(checkpoint),
        "research_checkpoint": dict(research),
        "monitor_checkpoint": dict(monitor),
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def reserve_v31_cycle_commit_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    permit_binding: Mapping[str, Any],
    commit_material_digest: str,
    reserved_at: str,
) -> Mapping[str, Any]:
    """Persist the recovery material before either owner checkpoint advances."""

    live = verify_v31_cycle_permit_live_v2(
        supervisor_store=supervisor_store,
        research_store=research_store,
        monitor_store=monitor_store,
        run_id=run_id,
        permit_binding=permit_binding,
        operation="AGENT_ATTEMPT_RESERVATION",
    )
    checkpoint = live["supervisor_checkpoint"]
    cycle = int(checkpoint["current_cycle_index"])
    intent_ref = commit_intent_ref_v2(cycle)
    if supervisor_store.document_exists(relative_ref=intent_ref):
        intent = supervisor_store.read_document(
            relative_ref=intent_ref,
            digest_field=COMMIT_INTENT_DIGEST_FIELD,
        )
        if (
            intent.get("run_id") != run_id
            or intent.get("cycle_index") != cycle
            or intent.get("cycle_permit_digest")
            != checkpoint["active_permit_digest"]
            or intent.get("supervisor_checkpoint_digest_before_reservation")
            != checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
            or intent.get("research_checkpoint_digest_before_commit")
            != checkpoint["research_checkpoint_digest"]
            or intent.get("monitor_checkpoint_digest_before_commit")
            != checkpoint["monitor_checkpoint_digest"]
            or intent.get("commit_material_digest") != commit_material_digest
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_ORPHAN_COMMIT_INTENT_CONFLICT"
            )
        binding = supervisor_store.artifact_binding(
            relative_ref=intent_ref,
            digest_field=COMMIT_INTENT_DIGEST_FIELD,
            expected_semantic_digest=str(intent[COMMIT_INTENT_DIGEST_FIELD]),
        )
    else:
        intent = build_commit_intent_v2(
            checkpoint=checkpoint,
            cycle_permit_digest=str(checkpoint["active_permit_digest"]),
            commit_material_digest=commit_material_digest,
            reserved_at=reserved_at,
        )
        binding = supervisor_store.write_document(
            relative_ref=intent_ref,
            document=intent,
            digest_field=COMMIT_INTENT_DIGEST_FIELD,
        )
    candidate = transition_supervisor_checkpoint_v2(
        checkpoint,
        status="COMMIT_RESERVED",
        current_cycle_index=cycle,
        completed_research_cycles=int(checkpoint["completed_research_cycles"]),
        resolved_outcome_cycles=int(checkpoint["resolved_outcome_cycles"]),
        active_permit_digest=str(checkpoint["active_permit_digest"]),
        active_commit_intent_digest=intent[COMMIT_INTENT_DIGEST_FIELD],
        research_checkpoint_digest=str(checkpoint["research_checkpoint_digest"]),
        monitor_checkpoint_digest=str(checkpoint["monitor_checkpoint_digest"]),
        last_outcome_receipt_digest=checkpoint["last_outcome_receipt_digest"],
        failure_ref=None,
        failure_digest=None,
        resume_allowed=True,
        updated_at=str(intent["reserved_at"]),
    )
    durable = supervisor_store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(
            checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
        ),
        checkpoint=candidate,
    )
    return {
        "status": "COMMIT_RESERVED",
        "cycle_index": cycle,
        "commit_intent": intent,
        "commit_intent_binding": dict(binding),
        "supervisor_checkpoint": dict(durable),
        "agent_reinvocation_allowed": False,
        "outcome_collection_allowed": False,
    }


def record_v31_cycle_commit_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    committed_at: str,
) -> Mapping[str, Any]:
    """Close a reserved commit only after accepted state and plan both exist."""

    checkpoint = supervisor_store.load_checkpoint(run_id=run_id)
    if checkpoint.get("status") not in {"COMMIT_RESERVED"}:
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_COMMIT_NOT_RESERVED"
        )
    cycle = int(checkpoint["current_cycle_index"])
    research, monitor = _load_owner_checkpoints(
        research_store=research_store, monitor_store=monitor_store, run_id=run_id
    )
    if monitor.get("status") == "FAILED_CLOSED" or monitor.get("resume_allowed") is False:
        fail_v31_experiment_supervisor_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            failure_code="MONITOR_FAILED_DURING_COMMIT",
            failure_summary=(
                "The monitor owner failed while the deterministic cycle commit "
                "was reserved."
            ),
            occurred_at=committed_at,
        )
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_MONITOR_FAILED_CLOSED"
        )
    previous = _validate_committed_snapshot(
        supervisor=checkpoint,
        monitor_store=monitor_store,
        research=research,
        monitor=monitor,
        cycle_index=cycle,
    )
    target_status = "AWAITING_FINAL_OUTCOME" if cycle == 8 else "AWAITING_OUTCOME"
    candidate = transition_supervisor_checkpoint_v2(
        checkpoint,
        status=target_status,
        current_cycle_index=cycle,
        completed_research_cycles=cycle,
        resolved_outcome_cycles=cycle - 1,
        active_permit_digest=None,
        active_commit_intent_digest=None,
        research_checkpoint_digest=_checkpoint_digest(research, owner="RESEARCH"),
        monitor_checkpoint_digest=_checkpoint_digest(monitor, owner="MONITOR"),
        last_outcome_receipt_digest=previous,
        failure_ref=None,
        failure_digest=None,
        resume_allowed=True,
        updated_at=committed_at,
    )
    durable = supervisor_store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(
            checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
        ),
        checkpoint=candidate,
    )
    return {
        "status": target_status,
        "cycle_index": cycle,
        "supervisor_checkpoint": dict(durable),
        "next_cycle_permitted": False,
        "outcome_required": True,
    }


def complete_v31_experiment_supervisor_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    completed_at: str,
) -> Mapping[str, Any]:
    """Seal terminal completion only for 8/8 accepted plus 8/8 outcomes."""

    checkpoint = supervisor_store.load_checkpoint(run_id=run_id)
    if checkpoint.get("status") == "TERMINAL_COMPLETE":
        return checkpoint
    if checkpoint.get("status") != "AWAITING_FINAL_OUTCOME":
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_NOT_AWAITING_FINAL_OUTCOME"
        )
    research, monitor = _load_owner_checkpoints(
        research_store=research_store, monitor_store=monitor_store, run_id=run_id
    )
    if monitor.get("status") == "FAILED_CLOSED" or monitor.get("resume_allowed") is False:
        fail_v31_experiment_supervisor_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            failure_code="FINAL_MONITOR_FAILED_CLOSED",
            failure_summary="The final monitor outcome cannot be completed.",
            occurred_at=completed_at,
        )
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_MONITOR_FAILED_CLOSED"
        )
    last = _validate_terminal_snapshot(
        supervisor=checkpoint,
        monitor_store=monitor_store,
        research=research,
        monitor=monitor,
    )
    _plans, _attempts, outcomes = _lists(monitor)
    if (
        _checkpoint_digest(research, owner="RESEARCH")
        != checkpoint["research_checkpoint_digest"]
        or outcomes[-2].get("outcome_receipt_digest")
        != checkpoint["last_outcome_receipt_digest"]
    ):
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_FINAL_PREFIX_STALE"
        )
    candidate = transition_supervisor_checkpoint_v2(
        checkpoint,
        status="TERMINAL_COMPLETE",
        current_cycle_index=None,
        completed_research_cycles=8,
        resolved_outcome_cycles=8,
        active_permit_digest=None,
        active_commit_intent_digest=None,
        research_checkpoint_digest=_checkpoint_digest(research, owner="RESEARCH"),
        monitor_checkpoint_digest=_checkpoint_digest(monitor, owner="MONITOR"),
        last_outcome_receipt_digest=last,
        failure_ref=None,
        failure_digest=None,
        resume_allowed=True,
        updated_at=completed_at,
    )
    return supervisor_store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(
            checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
        ),
        checkpoint=candidate,
    )


def fail_v31_experiment_supervisor_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    failure_code: str,
    failure_summary: str,
    occurred_at: str,
) -> Mapping[str, Any]:
    """Persist one permanent failure and clear every live permit/intention."""

    checkpoint = supervisor_store.load_checkpoint(run_id=run_id)
    if checkpoint.get("status") == "FAILED_CLOSED":
        return checkpoint
    if checkpoint.get("status") == "TERMINAL_COMPLETE":
        raise V31ExperimentSupervisorV2WorkflowError(
            "V31_SUPERVISOR_V2_TERMINAL_FAILURE_FORBIDDEN"
        )
    try:
        research, monitor = _load_owner_checkpoints(
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
        )
        research_digest = _checkpoint_digest(research, owner="RESEARCH")
        monitor_digest = _checkpoint_digest(monitor, owner="MONITOR")
    except V31ExperimentSupervisorV2WorkflowError:
        research_digest = str(checkpoint["research_checkpoint_digest"])
        monitor_digest = str(checkpoint["monitor_checkpoint_digest"])
    failure_ref = supervisor_failure_ref_v2(int(checkpoint["revision"]))
    if supervisor_store.document_exists(relative_ref=failure_ref):
        failure = supervisor_store.read_document(
            relative_ref=failure_ref,
            digest_field=SUPERVISOR_FAILURE_DIGEST_FIELD,
        )
        if (
            failure.get("run_id") != run_id
            or failure.get("supervisor_checkpoint_digest_before_failure")
            != checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
            or failure.get("research_checkpoint_digest") != research_digest
            or failure.get("monitor_checkpoint_digest") != monitor_digest
        ):
            raise V31ExperimentSupervisorV2WorkflowError(
                "V31_SUPERVISOR_V2_ORPHAN_FAILURE_CONFLICT"
            )
        binding = supervisor_store.artifact_binding(
            relative_ref=failure_ref,
            digest_field=SUPERVISOR_FAILURE_DIGEST_FIELD,
            expected_semantic_digest=str(
                failure[SUPERVISOR_FAILURE_DIGEST_FIELD]
            ),
        )
    else:
        failure = build_supervisor_failure_v2(
            checkpoint=checkpoint,
            failure_code=failure_code,
            failure_summary=failure_summary,
            occurred_at=occurred_at,
            research_checkpoint_digest=research_digest,
            monitor_checkpoint_digest=monitor_digest,
        )
        binding = supervisor_store.write_document(
            relative_ref=failure_ref,
            document=failure,
            digest_field=SUPERVISOR_FAILURE_DIGEST_FIELD,
        )
    candidate = transition_supervisor_checkpoint_v2(
        checkpoint,
        status="FAILED_CLOSED",
        current_cycle_index=checkpoint["current_cycle_index"],
        completed_research_cycles=int(checkpoint["completed_research_cycles"]),
        resolved_outcome_cycles=int(checkpoint["resolved_outcome_cycles"]),
        active_permit_digest=None,
        active_commit_intent_digest=None,
        research_checkpoint_digest=research_digest,
        monitor_checkpoint_digest=monitor_digest,
        last_outcome_receipt_digest=checkpoint["last_outcome_receipt_digest"],
        failure_ref=failure_ref,
        failure_digest=failure[SUPERVISOR_FAILURE_DIGEST_FIELD],
        resume_allowed=False,
        updated_at=str(failure["occurred_at"]),
    )
    durable = supervisor_store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(
            checkpoint[SUPERVISOR_CHECKPOINT_DIGEST_FIELD]
        ),
        checkpoint=candidate,
    )
    return {
        "status": "FAILED_CLOSED",
        "failure": failure,
        "failure_binding": dict(binding),
        "supervisor_checkpoint": dict(durable),
        "resume_allowed": False,
    }


__all__ = [
    "V31ExperimentSupervisorV2WorkflowError",
    "V31SupervisorStoreV2Port",
    "complete_v31_experiment_supervisor_v2",
    "fail_v31_experiment_supervisor_v2",
    "initialize_v31_experiment_supervisor_v2",
    "open_v31_cycle_permit_v2",
    "record_v31_cycle_commit_v2",
    "reserve_v31_cycle_commit_v2",
    "verify_v31_cycle_permit_live_v2",
    "v31_experiment_supervisor_status_v2",
]
