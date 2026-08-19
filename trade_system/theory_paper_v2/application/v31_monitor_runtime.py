"""Durable delayed-outcome workflow for accepted V3.1 research states.

The workflow first seals a typed monitor plan after physical accepted-state
verification.  At the one-hour horizon it durably reserves the sole adapter
attempt before invoking the public observation port, writes raw and normalized
evidence once, seals the typed outcome receipt, and advances a CAS cursor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .ports import (
    V31MonitorStorePort,
    V31PublicOutcomeObservationPort,
    V31ResearchStorePort,
)
from .v31_research_cycle import (
    V31ResearchCycleError,
    verify_v31_accepted_state,
)
from ..domain.v31_experiment_contracts import (
    V31ExperimentContractError,
    build_path_outcome_receipt,
    verify_minimal_experiment_contract,
    verify_path_outcome_receipt,
    verify_typed_path_monitor_plan,
)
from ..domain.v31_monitor_runtime import (
    OUTCOME_EVALUATOR_VERSION,
    PublicOutcomeReading,
    V31MonitorRuntimeContractError,
    build_monitor_resolution_attempt,
    build_public_outcome_source_record,
    monitor_cycle_root,
    outcome_observation_from_source_record,
)


class V31MonitorRuntimeError(ValueError):
    """The monitor workflow could not continue without violating chronology."""


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31MonitorRuntimeError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31MonitorRuntimeError(code) from exc
    if parsed.tzinfo is None:
        raise V31MonitorRuntimeError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31MonitorRuntimeError(code)
    return parsed.astimezone(UTC)


def initialize_v31_monitor_runtime(
    *,
    store: V31MonitorStorePort,
    experiment_contract: Mapping[str, Any],
    created_at: str,
) -> Mapping[str, Any]:
    """Initialize or exactly recover the monitor cursor; no adapter is called."""

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    _time(created_at, "V31_MONITOR_CREATED_AT_INVALID")
    return store.initialize_checkpoint(
        run_id=str(experiment_contract["run_id"]),
        experiment_contract_digest=contract_digest,
        total_cycles=int(
            experiment_contract["cycle_protocol"]["accepted_cycle_count"]
        ),
        created_at=created_at,
    )


def v31_monitor_status(
    *,
    store: V31MonitorStorePort,
    experiment_contract: Mapping[str, Any],
    observed_at: str,
) -> Mapping[str, Any]:
    """Return the read-only state; before the horizon this is the only action."""

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    run_id = str(experiment_contract["run_id"])
    now = _time(observed_at, "V31_MONITOR_STATUS_TIME_INVALID")
    checkpoint = store.load_checkpoint(run_id=run_id)
    if checkpoint["experiment_contract_digest"] != contract_digest:
        raise V31MonitorRuntimeError("V31_MONITOR_CONTRACT_BINDING_MISMATCH")
    plans = checkpoint["plan_bindings"]
    attempts = checkpoint["resolution_attempt_bindings"]
    outcomes = checkpoint["outcome_bindings"]
    if checkpoint["status"] == "FAILED_CLOSED":
        runtime_status = "FAILED_CLOSED"
        due_cycle_index = None
        not_before = None
        expires_at = None
    elif checkpoint["status"] == "TERMINAL":
        runtime_status = "TERMINAL"
        due_cycle_index = None
        not_before = None
        expires_at = None
    elif len(attempts) > len(outcomes):
        runtime_status = "ATTEMPT_RESERVED_NO_RETRY"
        due_cycle_index = len(outcomes) + 1
        plan = store.read_document(
            relative_ref=plans[due_cycle_index - 1]["relative_ref"],
            digest_field="monitor_plan_digest",
            expected_semantic_digest=plans[due_cycle_index - 1][
                "semantic_digest"
            ],
        )
        not_before = plan["outcome_not_before"]
        expires_at = plan["expires_at"]
    elif len(outcomes) < len(plans):
        due_cycle_index = len(outcomes) + 1
        plan = store.read_document(
            relative_ref=plans[due_cycle_index - 1]["relative_ref"],
            digest_field="monitor_plan_digest",
            expected_semantic_digest=plans[due_cycle_index - 1][
                "semantic_digest"
            ],
        )
        not_before = plan["outcome_not_before"]
        expires_at = plan["expires_at"]
        if now < _time(not_before, "V31_MONITOR_PLAN_TIME_INVALID"):
            runtime_status = "NOT_DUE"
        elif now <= _time(expires_at, "V31_MONITOR_PLAN_TIME_INVALID"):
            runtime_status = "DUE"
        else:
            runtime_status = "DEADLINE_MISSED"
    else:
        runtime_status = "AWAITING_ACCEPTED_STATE"
        due_cycle_index = None
        not_before = None
        expires_at = None
    return {
        "run_id": run_id,
        "runtime_status": runtime_status,
        "planned_cycles": len(plans),
        "reserved_attempts": len(attempts),
        "resolved_cycles": len(outcomes),
        "due_cycle_index": due_cycle_index,
        "outcome_not_before": not_before,
        "expires_at": expires_at,
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def _fail_closed(
    *,
    store: V31MonitorStorePort,
    run_id: str,
    failure_code: str,
    failure_summary: str,
    occurred_at: str,
) -> Mapping[str, Any]:
    checkpoint = store.load_checkpoint(run_id=run_id)
    if checkpoint["status"] != "ACTIVE":
        return checkpoint
    return store.fail_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        failure_code=failure_code,
        failure_summary=failure_summary,
        occurred_at=occurred_at,
    )


def schedule_v31_monitor_plan(
    *,
    store: V31MonitorStorePort,
    research_store: V31ResearchStorePort,
    experiment_contract: Mapping[str, Any],
    accepted_state: Mapping[str, Any],
    monitor_plan: Mapping[str, Any],
    scheduled_at: str,
) -> Mapping[str, Any]:
    """Write the sole plan only after its accepted state is durably present."""

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    run_id = str(experiment_contract["run_id"])
    scheduled = _time(scheduled_at, "V31_MONITOR_SCHEDULE_TIME_INVALID")
    checkpoint = store.load_checkpoint(run_id=run_id)
    try:
        if (
            checkpoint["status"] != "ACTIVE"
            or checkpoint["experiment_contract_digest"] != contract_digest
        ):
            raise V31MonitorRuntimeError("V31_MONITOR_NOT_ACTIVE")
        accepted_digest = verify_v31_accepted_state(accepted_state)
        cycle_index = int(accepted_state["cycle_index"])
        expected_cycle = len(checkpoint["plan_bindings"]) + 1
        if cycle_index < expected_cycle:
            existing = checkpoint["plan_bindings"][cycle_index - 1]
            if existing["semantic_digest"] == monitor_plan.get(
                "monitor_plan_digest"
            ):
                return checkpoint
            raise V31MonitorRuntimeError("V31_MONITOR_PLAN_WRITE_ONCE_CONFLICT")
        if cycle_index != expected_cycle:
            raise V31MonitorRuntimeError("V31_MONITOR_PLAN_SEQUENCE_INVALID")
        if (
            accepted_state.get("run_id") != run_id
            or monitor_plan.get("run_id") != run_id
            or monitor_plan.get("cycle_index") != cycle_index
            or monitor_plan.get("decision_at") != accepted_state.get("decision_at")
            or scheduled
            < _time(
                accepted_state.get("selected_at"),
                "V31_MONITOR_ACCEPTED_STATE_TIME_INVALID",
            )
        ):
            raise V31MonitorRuntimeError("V31_MONITOR_ACCEPTED_STATE_MISMATCH")
        accepted_ref = f"cycles/{cycle_index:04d}/accepted-research-state.json"
        origin_bindings = monitor_plan.get("origin_bindings")
        if not isinstance(origin_bindings, Mapping):
            raise V31MonitorRuntimeError("V31_MONITOR_ORIGIN_BINDINGS_INVALID")
        accepted_origin = origin_bindings.get("accepted_state")
        path_set_origin = origin_bindings.get("path_set")
        if (
            not isinstance(accepted_origin, Mapping)
            or accepted_origin.get("ref") != accepted_ref
            or accepted_origin.get("digest") != accepted_digest
            or not isinstance(path_set_origin, Mapping)
            or path_set_origin.get("digest")
            != accepted_state.get("scenario_path_set_digest")
        ):
            raise V31MonitorRuntimeError("V31_MONITOR_ORIGIN_ACCEPTANCE_MISMATCH")
        plan_digest = verify_typed_path_monitor_plan(
            monitor_plan,
            experiment_contract=experiment_contract,
            expected_origin_bindings=origin_bindings,
        )
        durable_accepted = research_store.read_document(
            relative_ref=accepted_ref,
            digest_field="accepted_state_digest",
            expected_semantic_digest=accepted_digest,
        )
        research_checkpoint = research_store.load_checkpoint(run_id=run_id)
        events = research_store.read_events(
            run_id=run_id, cycle_index=cycle_index
        )
        if (
            durable_accepted != dict(accepted_state)
            or int(research_checkpoint.get("completed_cycles", 0)) < cycle_index
            or len(events) != 6
            or events[4].get("event_type") != "STATE_ACCEPTED"
            or events[4].get("artifact_ref") != accepted_ref
            or events[4].get("artifact_semantic_digest") != accepted_digest
        ):
            raise V31MonitorRuntimeError(
                "V31_MONITOR_ACCEPTED_STATE_NOT_DURABLE"
            )
        root = monitor_cycle_root(cycle_index)
        binding = store.write_document(
            relative_ref=f"{root}/monitor-plan.json",
            document=monitor_plan,
            digest_field="monitor_plan_digest",
        )
        candidate = {
            **checkpoint,
            "revision": int(checkpoint["revision"]) + 1,
            "plan_bindings": [
                *checkpoint["plan_bindings"],
                {
                    "cycle_index": cycle_index,
                    "relative_ref": binding["relative_ref"],
                    "semantic_digest": plan_digest,
                    "physical_sha256": binding["physical_sha256"],
                    "accepted_state_digest": accepted_digest,
                },
            ],
            "updated_at": scheduled_at,
        }
        return store.replace_checkpoint(
            run_id=run_id,
            expected_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
            checkpoint=candidate,
        )
    except Exception as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        try:
            _fail_closed(
                store=store,
                run_id=run_id,
                failure_code="V31_MONITOR_PLAN_SCHEDULING_FAILED",
                failure_summary=f"{type(exc).__name__}:{exc}",
                occurred_at=scheduled_at,
            )
        except Exception:
            pass
        if isinstance(exc, V31MonitorRuntimeError):
            raise
        raise V31MonitorRuntimeError("V31_MONITOR_PLAN_SCHEDULING_FAILED") from exc


def resolve_due_v31_monitor(
    *,
    store: V31MonitorStorePort,
    experiment_contract: Mapping[str, Any],
    observation_port: V31PublicOutcomeObservationPort,
    requested_at: str,
) -> Mapping[str, Any]:
    """Resolve the next due plan with one durably reserved public GET attempt."""

    requested = _time(requested_at, "V31_MONITOR_REQUEST_TIME_INVALID")
    run_id = str(experiment_contract["run_id"])
    status = v31_monitor_status(
        store=store,
        experiment_contract=experiment_contract,
        observed_at=requested_at,
    )
    if status["runtime_status"] == "NOT_DUE":
        return status
    if status["runtime_status"] in {"TERMINAL", "FAILED_CLOSED"}:
        return status
    if status["runtime_status"] == "AWAITING_ACCEPTED_STATE":
        raise V31MonitorRuntimeError("V31_MONITOR_NO_DUE_PLAN")
    if status["runtime_status"] in {
        "DEADLINE_MISSED",
        "ATTEMPT_RESERVED_NO_RETRY",
    }:
        _fail_closed(
            store=store,
            run_id=run_id,
            failure_code=f"V31_MONITOR_{status['runtime_status']}",
            failure_summary=(
                "Outcome deadline or no-retry attempt boundary prevents observation."
            ),
            occurred_at=requested_at,
        )
        raise V31MonitorRuntimeError(f"V31_MONITOR_{status['runtime_status']}")
    if status["runtime_status"] != "DUE":
        raise V31MonitorRuntimeError("V31_MONITOR_STATUS_INVALID")

    checkpoint = store.load_checkpoint(run_id=run_id)
    cycle_index = int(status["due_cycle_index"])
    plan_binding = checkpoint["plan_bindings"][cycle_index - 1]
    monitor_plan = store.read_document(
        relative_ref=plan_binding["relative_ref"],
        digest_field="monitor_plan_digest",
        expected_semantic_digest=plan_binding["semantic_digest"],
    )
    origin_bindings = monitor_plan["origin_bindings"]
    verify_typed_path_monitor_plan(
        monitor_plan,
        experiment_contract=experiment_contract,
        expected_origin_bindings=origin_bindings,
    )
    previous_receipt = None
    previous_digest = checkpoint["last_outcome_receipt_digest"]
    if cycle_index > 1:
        previous_binding = checkpoint["outcome_bindings"][cycle_index - 2]
        previous_receipt = store.read_document(
            relative_ref=previous_binding["outcome_receipt_ref"],
            digest_field="outcome_receipt_digest",
            expected_semantic_digest=previous_binding["outcome_receipt_digest"],
        )
    attempt = build_monitor_resolution_attempt(
        run_id=run_id,
        cycle_index=cycle_index,
        monitor_plan_digest=monitor_plan["monitor_plan_digest"],
        requested_at=requested_at,
        previous_outcome_receipt_digest=previous_digest,
    )
    root = monitor_cycle_root(cycle_index)
    attempt_binding = store.write_document(
        relative_ref=f"{root}/resolution-attempt.json",
        document=attempt,
        digest_field="monitor_attempt_digest",
    )
    checkpoint = store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        checkpoint={
            **checkpoint,
            "revision": int(checkpoint["revision"]) + 1,
            "resolution_attempt_bindings": [
                *checkpoint["resolution_attempt_bindings"],
                {
                    "cycle_index": cycle_index,
                    "relative_ref": attempt_binding["relative_ref"],
                    "semantic_digest": attempt_binding["semantic_digest"],
                    "physical_sha256": attempt_binding["physical_sha256"],
                },
            ],
            "updated_at": requested_at,
        },
    )

    try:
        reading = observation_port.observe_public_outcome(
            monitor_plan=monitor_plan, requested_at=requested_at
        )
        if not isinstance(reading, PublicOutcomeReading):
            raise V31MonitorRuntimeError("V31_MONITOR_PUBLIC_READING_INVALID")
        captured = _time(
            reading.captured_at, "V31_MONITOR_PUBLIC_CAPTURE_TIME_INVALID"
        )
        not_before = _time(
            monitor_plan["outcome_not_before"], "V31_MONITOR_PLAN_TIME_INVALID"
        )
        expires = _time(
            monitor_plan["expires_at"], "V31_MONITOR_PLAN_TIME_INVALID"
        )
        as_of = _time(reading.as_of, "V31_MONITOR_PUBLIC_READING_TIME_INVALID")
        available = _time(
            reading.available_at, "V31_MONITOR_PUBLIC_READING_TIME_INVALID"
        )
        if (
            captured < requested
            or captured > expires
            or as_of < not_before
            or as_of > captured
            or available < as_of
            or available > captured
            or reading.observable_ref
            != monitor_plan["observable"]["observable_ref"]
            or reading.source_request_id
            != monitor_plan["observable"]["source_request_id"]
        ):
            raise V31MonitorRuntimeError(
                "V31_MONITOR_PUBLIC_READING_WINDOW_MISMATCH"
            )
        raw_binding = store.write_raw(
            relative_ref=f"{root}/outcome-raw.bin",
            payload=reading.raw_payload,
        )
        source_record = build_public_outcome_source_record(
            run_id=run_id,
            cycle_index=cycle_index,
            monitor_plan_digest=monitor_plan["monitor_plan_digest"],
            reading=reading,
            raw_capture_ref=raw_binding["relative_ref"],
            raw_capture_sha256=raw_binding["physical_sha256"],
        )
        source_binding = store.write_document(
            relative_ref=f"{root}/source-record.json",
            document=source_record,
            digest_field="source_record_digest",
        )
        observation = outcome_observation_from_source_record(source_record)
        observation_document = observation.to_document()
        observation_binding = store.write_document(
            relative_ref=f"{root}/outcome-observation.json",
            document=observation_document,
            digest_field="observation_digest",
        )
        outcome_receipt = build_path_outcome_receipt(
            experiment_contract=experiment_contract,
            monitor_plan=monitor_plan,
            expected_origin_bindings=origin_bindings,
            outcome_receipt_id=f"outcome:{cycle_index}",
            evaluated_at=reading.captured_at,
            evaluator_version=OUTCOME_EVALUATOR_VERSION,
            observation=observation,
            previous_outcome_receipt=previous_receipt,
            expected_previous_outcome_receipt_digest=previous_digest,
        )
        verify_path_outcome_receipt(
            outcome_receipt,
            experiment_contract=experiment_contract,
            monitor_plan=monitor_plan,
            expected_origin_bindings=origin_bindings,
            previous_outcome_receipt=previous_receipt,
            expected_previous_outcome_receipt_digest=previous_digest,
        )
        receipt_binding = store.write_document(
            relative_ref=f"{root}/outcome-receipt.json",
            document=outcome_receipt,
            digest_field="outcome_receipt_digest",
        )
        current = store.load_checkpoint(run_id=run_id)
        if (
            current["checkpoint_digest"] != checkpoint["checkpoint_digest"]
            or len(current["resolution_attempt_bindings"]) != cycle_index
            or len(current["outcome_bindings"]) != cycle_index - 1
        ):
            raise V31MonitorRuntimeError("V31_MONITOR_RESOLUTION_CAS_CONFLICT")
        outcome_binding = {
            "cycle_index": cycle_index,
            "raw_capture_ref": raw_binding["relative_ref"],
            "raw_capture_sha256": raw_binding["physical_sha256"],
            "source_record_ref": source_binding["relative_ref"],
            "source_record_digest": source_binding["semantic_digest"],
            "source_record_physical_sha256": source_binding["physical_sha256"],
            "observation_ref": observation_binding["relative_ref"],
            "observation_digest": observation_binding["semantic_digest"],
            "observation_physical_sha256": observation_binding["physical_sha256"],
            "outcome_receipt_ref": receipt_binding["relative_ref"],
            "outcome_receipt_digest": receipt_binding["semantic_digest"],
            "outcome_receipt_physical_sha256": receipt_binding[
                "physical_sha256"
            ],
        }
        resolved = store.replace_checkpoint(
            run_id=run_id,
            expected_checkpoint_digest=str(current["checkpoint_digest"]),
            checkpoint={
                **current,
                "revision": int(current["revision"]) + 1,
                "status": "TERMINAL" if cycle_index == 8 else "ACTIVE",
                "outcome_bindings": [
                    *current["outcome_bindings"], outcome_binding
                ],
                "last_outcome_receipt_digest": receipt_binding[
                    "semantic_digest"
                ],
                "updated_at": reading.captured_at,
            },
        )
        return {
            "run_id": run_id,
            "runtime_status": "RESOLVED",
            "cycle_index": cycle_index,
            "expectation_outcome": outcome_receipt["expectation_outcome"],
            "path_outcome": outcome_receipt["path_outcome"],
            "coverage_loss": outcome_receipt["coverage_loss"],
            "outcome_receipt_digest": outcome_receipt[
                "outcome_receipt_digest"
            ],
            "checkpoint_digest": resolved["checkpoint_digest"],
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
    except Exception as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        try:
            _fail_closed(
                store=store,
                run_id=run_id,
                failure_code="V31_MONITOR_PUBLIC_OBSERVATION_OR_RESOLUTION_FAILED",
                failure_summary=f"{type(exc).__name__}:{exc}",
                occurred_at=requested_at,
            )
        except Exception:
            pass
        if isinstance(exc, V31MonitorRuntimeError):
            raise
        if isinstance(
            exc,
            (
                V31ExperimentContractError,
                V31MonitorRuntimeContractError,
                V31ResearchCycleError,
            ),
        ):
            raise V31MonitorRuntimeError(
                "V31_MONITOR_PUBLIC_OBSERVATION_OR_RESOLUTION_FAILED"
            ) from exc
        raise V31MonitorRuntimeError(
            "V31_MONITOR_PUBLIC_ADAPTER_FAILED"
        ) from exc


__all__ = [
    "V31MonitorRuntimeError",
    "initialize_v31_monitor_runtime",
    "resolve_due_v31_monitor",
    "schedule_v31_monitor_plan",
    "v31_monitor_status",
]
