"""Recoverable two-owner commit for one authorized V3.1 successor cycle.

The module deliberately reuses the frozen semantic compiler and durable cycle
core.  Its new responsibility is to freeze a complete commit material artifact
before the legacy research or monitor owner advances, then make both writes
idempotently recoverable without another Agent call or market observation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Protocol, Sequence

from .ports import V31MonitorStorePort, V31ResearchStorePort
from .v31_agent_transport import (
    V31AgentTransportStorePort,
    verify_completed_v31_authoring_transport,
)
from .v31_durable_bundle import (
    rebuild_v31_documents_from_bundle,
    seal_v31_durable_assembly_bundle,
)
from .v31_durable_cycle import persist_completed_v31_cycle
from .v31_experiment_supervisor_v2 import (
    V31SupervisorStoreV2Port,
    record_v31_cycle_commit_v2,
    reserve_v31_cycle_commit_v2,
    verify_v31_cycle_permit_live_v2,
)
from .v31_formal_cycle import (
    ABSOLUTE_MARK_PRICE_OBSERVABLE,
    _absolute_monitor_rules,
    _assert_non_executable,
    _build_formal_authoring_packet,
    _monitor_origin_bindings,
    _validate_active_chain,
)
from .v31_monitor_runtime import (
    initialize_v31_monitor_runtime,
    schedule_v31_monitor_plan,
)
from .v31_research_cycle import (
    complete_v31_research_cycle,
    select_v31_cycle_action,
)
from ..domain.behavior_planning import seal_action_selection
from ..domain.contracts.canonical import verify_self_digest
from ..domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    build_typed_path_monitor_plan,
    verify_typed_path_monitor_plan,
)
from ..domain.v31_cycle_authoring import AUTHORING_PACKET_DIGEST_FIELD
from ..domain.v31_experiment_supervisor_v2 import (
    COMMIT_INTENT_DIGEST_FIELD,
    commit_intent_ref_v2,
)
from ..domain.v31_successor_cycle_commit_v2 import (
    DIGEST_FIELD,
    SUPPORT_BINDING_KEYS,
    build_v31_successor_cycle_commit_material_v2,
    successor_commit_material_ref_v2,
    verify_v31_successor_cycle_commit_material_v2,
)


class V31SuccessorCycleCommitV2WorkflowError(ValueError):
    """The deterministic successor commit could not safely converge."""


class V31SuccessorCommitStoreV2Port(Protocol):
    def write_material(
        self, *, relative_ref: str, document: Mapping[str, Any]
    ) -> Mapping[str, str]: ...

    def read_material(
        self,
        *,
        relative_ref: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...

    def material_exists(self, *, relative_ref: str) -> bool: ...


_EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31SuccessorCycleCommitV2WorkflowError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SuccessorCycleCommitV2WorkflowError(code) from exc
    if parsed.tzinfo is None:
        raise V31SuccessorCycleCommitV2WorkflowError(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31SuccessorCycleCommitV2WorkflowError(code)
    return normalized


def _normalized_support_bindings(
    support_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    if not isinstance(support_bindings, Mapping) or set(
        support_bindings
    ) != SUPPORT_BINDING_KEYS:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_SUPPORT_BINDINGS_INVALID"
        )
    fields = {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
    result: dict[str, dict[str, str]] = {}
    for key in sorted(SUPPORT_BINDING_KEYS):
        binding = support_bindings[key]
        if not isinstance(binding, Mapping) or set(binding) != fields:
            raise V31SuccessorCycleCommitV2WorkflowError(
                "V31_SUCCESSOR_COMMIT_SUPPORT_BINDINGS_INVALID"
            )
        result[key] = {field: str(binding[field]) for field in fields}
    return result


def prepare_v31_successor_cycle_commit_material_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    transport_store: V31AgentTransportStorePort,
    active_chain: Mapping[str, Any],
    permit_binding: Mapping[str, Any],
    prepared_at: str,
    completed_at: str,
    recorded_at: str,
    monitor_runtime_created_at: str,
    monitor_rules: Sequence[FrozenMonitorRule],
    support_bindings: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Build, but do not persist, the deterministic cross-owner material."""

    _time(prepared_at, "V31_SUCCESSOR_COMMIT_PREPARED_AT_INVALID")
    completed = _time(
        completed_at, "V31_SUCCESSOR_COMMIT_COMPLETED_AT_INVALID"
    )
    recorded = _time(
        recorded_at, "V31_SUCCESSOR_COMMIT_RECORDED_AT_INVALID"
    )
    monitor_created = _time(
        monitor_runtime_created_at,
        "V31_SUCCESSOR_COMMIT_MONITOR_CREATED_AT_INVALID",
    )
    if recorded < completed or monitor_created > recorded:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_TIME_ORDER_INVALID"
        )
    try:
        run_id, contract_digest, authority_digest, contract, _authority = (
            _validate_active_chain(active_chain)
        )
        live = verify_v31_cycle_permit_live_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            permit_binding=permit_binding,
            operation="AGENT_ATTEMPT_RESERVATION",
        )
        expected_packet, checkpoint_before = _build_formal_authoring_packet(
            store=research_store, active_chain=active_chain
        )
        cycle_index = int(expected_packet["cycle_index"])
        if live["cycle_permit"].get("cycle_index") != cycle_index:
            raise V31SuccessorCycleCommitV2WorkflowError(
                "V31_SUCCESSOR_COMMIT_PERMIT_CYCLE_MISMATCH"
            )
        terminal = verify_completed_v31_authoring_transport(
            store=transport_store,
            run_id=run_id,
            cycle_index=cycle_index,
            expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
        )
    except V31SuccessorCycleCommitV2WorkflowError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_TERMINAL_INPUT_INVALID"
        ) from exc
    if (
        terminal.get("authoring_packet") != expected_packet
        or terminal.get("authoring_purpose")
        != "AUTHORIZED_RESEARCH_CYCLE"
        or terminal.get("experiment_start_authorized") is not True
        or terminal.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or terminal.get("executable") is not False
    ):
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_TRANSPORT_PACKET_MISMATCH"
        )
    assembly_inputs = terminal.get("assembly_inputs")
    action_selection = terminal.get("action_selection")
    if not isinstance(assembly_inputs, Mapping) or not isinstance(
        action_selection, Mapping
    ):
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_ASSEMBLY_INVALID"
        )
    try:
        action_evaluation = terminal["action_evaluation"]
        preselection = terminal["preselection"]
        selection = seal_action_selection(
            evaluation=action_evaluation,
            selected_candidate_id=action_selection["selected_candidate_id"],
            reason=action_selection["reason"],
            alternative_explanations=action_selection[
                "alternative_explanations"
            ],
            failure_conditions=action_selection["failure_conditions"],
            next_review_at=action_selection["next_review_at"],
            selected_at=action_selection["selected_at"],
        )
        if selection != dict(action_selection):
            raise V31SuccessorCycleCommitV2WorkflowError(
                "V31_SUCCESSOR_COMMIT_SELECTION_REPLAY_MISMATCH"
            )
        accepted = select_v31_cycle_action(
            preselection=preselection,
            action_evaluation=action_evaluation,
            selected_candidate_id=selection["selected_candidate_id"],
            alternative_explanations=selection["alternative_explanations"],
            selection_rationale=selection["reason"],
            failure_conditions=selection["failure_conditions"],
            next_review_at=selection["next_review_at"],
            selected_at=selection["selected_at"],
        )
        completion = complete_v31_research_cycle(
            accepted_state=accepted, completed_at=completed_at
        )
    except V31SuccessorCycleCommitV2WorkflowError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_SIX_OBJECT_REPLAY_FAILED"
        ) from exc
    documents = {
        "INPUTS_ADMITTED": terminal["inputs_receipt"],
        "PROPOSAL_SEALED": terminal["agent_proposal"],
        "EVALUATION_SEALED": preselection,
        "SELECTION_SEALED": selection,
        "STATE_ACCEPTED": accepted,
        "COMPLETION_SEALED": completion,
    }
    if (
        assembly_inputs.get("inputs_receipt") != documents["INPUTS_ADMITTED"]
        or assembly_inputs.get("agent_proposal")
        != documents["PROPOSAL_SEALED"]
    ):
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_ASSEMBLY_SOURCE_MISMATCH"
        )
    _assert_non_executable(documents)
    origin_bindings = _monitor_origin_bindings(
        accepted_state=accepted, assembly_inputs=assembly_inputs
    )
    rules = _absolute_monitor_rules(monitor_rules)
    plan = build_typed_path_monitor_plan(
        experiment_contract=contract,
        monitor_plan_id=(
            f"monitor:{run_id}:{cycle_index:04d}:absolute-mark-1h"
        ),
        cycle_id=f"{run_id}:cycle:{cycle_index:04d}",
        cycle_index=cycle_index,
        origin_bindings=origin_bindings,
        decision_at=str(accepted["decision_at"]),
        observable_ref=ABSOLUTE_MARK_PRICE_OBSERVABLE,
        source_request_id=(
            f"okx-public-mark-price:{run_id}:{cycle_index:04d}:1h"
        ),
        rules=rules,
    )
    verify_typed_path_monitor_plan(
        plan,
        experiment_contract=contract,
        expected_origin_bindings=origin_bindings,
    )
    evidence_binding = terminal.get("transport_evidence_binding")
    if not isinstance(evidence_binding, Mapping):
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_TRANSPORT_BINDING_INVALID"
        )
    try:
        durable_evidence = research_store.read_document(
            relative_ref=str(evidence_binding["relative_ref"]),
            digest_field="transport_evidence_digest",
            expected_semantic_digest=str(
                evidence_binding["semantic_digest"]
            ),
        )
        local_binding = research_store.artifact_binding(
            relative_ref=str(evidence_binding["relative_ref"]),
            digest_field="transport_evidence_digest",
            expected_semantic_digest=str(
                evidence_binding["semantic_digest"]
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_TRANSPORT_NOT_RUN_LOCAL"
        ) from exc
    if (
        dict(durable_evidence) != terminal.get("transport_evidence")
        or any(
            local_binding.get(field) != evidence_binding.get(field)
            for field in (
                "relative_ref",
                "semantic_digest",
                "physical_sha256",
            )
        )
    ):
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_TRANSPORT_BINDING_MISMATCH"
        )
    event_times = {event_type: recorded_at for event_type in _EVENT_ORDER}
    try:
        assembly_bundle = seal_v31_durable_assembly_bundle(
            assembly_inputs=assembly_inputs,
            documents=documents,
            recorded_at_by_event=event_times,
        )
        packet_digest = verify_self_digest(
            expected_packet, AUTHORING_PACKET_DIGEST_FIELD
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_BUNDLE_BUILD_FAILED"
        ) from exc
    support = _normalized_support_bindings(support_bindings)
    material = build_v31_successor_cycle_commit_material_v2(
        run_id=run_id,
        cycle_index=cycle_index,
        prepared_at=prepared_at,
        cycle_permit_binding=permit_binding,
        active_authority_digest=authority_digest,
        experiment_contract=contract,
        research_checkpoint_digest_before_commit=str(
            checkpoint_before["checkpoint_digest"]
        ),
        monitor_checkpoint_digest_before_commit=str(
            live["monitor_checkpoint"]["checkpoint_digest"]
        ),
        authoring_packet_digest=packet_digest,
        transport_evidence_binding=local_binding,
        assembly_bundle=assembly_bundle,
        monitor_plan=plan,
        monitor_runtime_created_at=monitor_runtime_created_at,
        scheduled_at=recorded_at,
        support_bindings=support,
    )
    if material["experiment_contract_digest"] != contract_digest:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_CONTRACT_DIGEST_MISMATCH"
        )
    return material


def persist_v31_successor_commit_material_v2(
    *,
    commit_store: V31SuccessorCommitStoreV2Port,
    material: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
) -> Mapping[str, str]:
    """Publish complete recovery material before a supervisor reservation."""

    digest = verify_v31_successor_cycle_commit_material_v2(
        material, experiment_contract=experiment_contract
    )
    ref = successor_commit_material_ref_v2(int(material["cycle_index"]))
    binding = commit_store.write_material(relative_ref=ref, document=material)
    if (
        binding.get("semantic_digest") != digest
        or binding.get("digest_field") != DIGEST_FIELD
    ):
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_MATERIAL_BINDING_INVALID"
        )
    return dict(binding)


def commit_or_recover_v31_successor_cycle_v2(
    *,
    supervisor_store: V31SupervisorStoreV2Port,
    commit_store: V31SuccessorCommitStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    active_chain: Mapping[str, Any],
    material_binding: Mapping[str, Any],
    committed_at: str,
) -> Mapping[str, Any]:
    """Converge research, monitor and supervisor from frozen local material."""

    _time(committed_at, "V31_SUCCESSOR_COMMIT_COMMITTED_AT_INVALID")
    try:
        run_id, _contract_digest, authority_digest, contract, _authority = (
            _validate_active_chain(active_chain)
        )
        material = commit_store.read_material(
            relative_ref=str(material_binding["relative_ref"]),
            expected_semantic_digest=str(
                material_binding["semantic_digest"]
            ),
        )
        actual_material_binding = commit_store.artifact_binding(
            relative_ref=str(material_binding["relative_ref"]),
            expected_semantic_digest=str(
                material_binding["semantic_digest"]
            ),
        )
        material_digest = verify_v31_successor_cycle_commit_material_v2(
            material, experiment_contract=contract
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_MATERIAL_REPLAY_INVALID"
        ) from exc
    cycle_index = int(material["cycle_index"])
    if (
        material.get("run_id") != run_id
        or material.get("active_authority_digest") != authority_digest
        or dict(actual_material_binding) != dict(material_binding)
        or material_binding.get("semantic_digest") != material_digest
        or material_binding.get("digest_field") != DIGEST_FIELD
    ):
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_MATERIAL_IDENTITY_MISMATCH"
        )
    supervisor = supervisor_store.load_checkpoint(run_id=run_id)
    if supervisor.get("status") == "CYCLE_PERMIT_OPEN":
        reservation = reserve_v31_cycle_commit_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            permit_binding=material["cycle_permit_binding"],
            commit_material_digest=material_digest,
            reserved_at=str(material["prepared_at"]),
        )
        supervisor = reservation["supervisor_checkpoint"]
    if supervisor.get("status") == "COMMIT_RESERVED":
        try:
            intent = supervisor_store.read_document(
                relative_ref=commit_intent_ref_v2(cycle_index),
                digest_field=COMMIT_INTENT_DIGEST_FIELD,
                expected_semantic_digest=str(
                    supervisor["active_commit_intent_digest"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V31SuccessorCycleCommitV2WorkflowError(
                "V31_SUCCESSOR_COMMIT_INTENT_REPLAY_INVALID"
            ) from exc
        if (
            intent.get("run_id") != run_id
            or intent.get("cycle_index") != cycle_index
            or intent.get("commit_material_digest") != material_digest
            or intent.get("cycle_permit_digest")
            != material["cycle_permit_digest"]
            or intent.get("research_checkpoint_digest_before_commit")
            != material["research_checkpoint_digest_before_commit"]
            or intent.get("monitor_checkpoint_digest_before_commit")
            != material["monitor_checkpoint_digest_before_commit"]
        ):
            raise V31SuccessorCycleCommitV2WorkflowError(
                "V31_SUCCESSOR_COMMIT_INTENT_MATERIAL_MISMATCH"
            )
    elif supervisor.get("status") in {
        "AWAITING_OUTCOME",
        "AWAITING_FINAL_OUTCOME",
    }:
        try:
            closed_intent = supervisor_store.read_document(
                relative_ref=commit_intent_ref_v2(cycle_index),
                digest_field=COMMIT_INTENT_DIGEST_FIELD,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V31SuccessorCycleCommitV2WorkflowError(
                "V31_SUCCESSOR_COMMIT_CLOSED_INTENT_MISSING"
            ) from exc
        if (
            supervisor.get("completed_research_cycles") != cycle_index
            or closed_intent.get("run_id") != run_id
            or closed_intent.get("cycle_index") != cycle_index
            or closed_intent.get("commit_material_digest")
            != material_digest
        ):
            raise V31SuccessorCycleCommitV2WorkflowError(
                "V31_SUCCESSOR_COMMIT_ALREADY_CLOSED_CONFLICT"
            )
        return {
            "status": "SUCCESSOR_CYCLE_COMMIT_ALREADY_CLOSED",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "supervisor_checkpoint": dict(supervisor),
            "agent_reinvoked": False,
            "outcome_collection_performed": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
    else:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_SUPERVISOR_STATE_INVALID"
        )
    try:
        assembly_inputs, documents, event_times = (
            rebuild_v31_documents_from_bundle(material["assembly_bundle"])
        )
        research_checkpoint = persist_completed_v31_cycle(
            store=research_store,
            run_id=run_id,
            cycle_index=cycle_index,
            total_cycles=8,
            created_at=str(
                research_store.load_checkpoint(run_id=run_id)["created_at"]
            ),
            documents=documents,
            assembly_inputs=assembly_inputs,
            recorded_at_by_event=event_times,
            transport_evidence_binding=material[
                "transport_evidence_binding"
            ],
        )
        initialize_v31_monitor_runtime(
            store=monitor_store,
            experiment_contract=contract,
            created_at=str(material["monitor_runtime_created_at"]),
        )
        monitor_checkpoint = schedule_v31_monitor_plan(
            store=monitor_store,
            research_store=research_store,
            experiment_contract=contract,
            accepted_state=documents["STATE_ACCEPTED"],
            monitor_plan=material["monitor_plan"],
            scheduled_at=str(material["scheduled_at"]),
        )
        supervisor_result = record_v31_cycle_commit_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            committed_at=committed_at,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorCycleCommitV2WorkflowError(
            "V31_SUCCESSOR_COMMIT_RECOVERY_FAILED"
        ) from exc
    return {
        "status": "SUCCESSOR_CYCLE_ACCEPTED_MONITOR_SCHEDULED",
        "run_id": run_id,
        "cycle_index": cycle_index,
        "commit_material_binding": dict(material_binding),
        "research_checkpoint": dict(research_checkpoint),
        "monitor_checkpoint": dict(monitor_checkpoint),
        "supervisor_checkpoint": dict(
            supervisor_result["supervisor_checkpoint"]
        ),
        "agent_reinvoked": False,
        "outcome_collection_performed": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


__all__ = [
    "V31SuccessorCommitStoreV2Port",
    "V31SuccessorCycleCommitV2WorkflowError",
    "commit_or_recover_v31_successor_cycle_v2",
    "persist_v31_successor_commit_material_v2",
    "prepare_v31_successor_cycle_commit_material_v2",
]
