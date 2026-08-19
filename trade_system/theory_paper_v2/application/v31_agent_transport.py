"""Application workflow for the V3.1 two-stage durable Agent transport.

The supplied Agent adapter is called at most once per stage, only after the
attempt, request, claim, and checkpoint reservation are durable.  A restart
without a durable delivery permanently fails the transport; a restart after a
delivery performs only deterministic validation and consume.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol

from ..domain.agent_research_contract import (
    verify_v31_agent_proposal,
    verify_v31_inputs_receipt,
)
from ..domain.behavior_planning import (
    seal_action_selection,
    verify_complete_action_evaluation,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ..domain.v31_agent_transport import (
    V31_LEGACY_PROPOSAL_TRANSPORT_CLASS,
    V31AgentTransportError,
    build_v31_agent_claim,
    build_v31_agent_delivery,
    build_v31_agent_request,
    build_v31_consume_receipt,
    build_v31_transport_failure,
    reserve_v31_agent_attempt,
    seal_v31_transport_evidence,
    validate_v31_agent_attempt,
    validate_v31_agent_claim,
    validate_v31_agent_delivery,
    validate_v31_agent_request,
    validate_v31_consume_receipt,
    validate_v31_transport_evidence,
)
from ..domain.v31_cycle_authoring import (
    AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
    AUTHORING_COMPILATION_ADMISSION_SCHEMA_ID,
    COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
    AUTHORING_ENVELOPE_SCHEMA_ID,
    V31CycleAuthoringError,
    seal_v31_authoring_compilation_admission,
    validate_v31_agent_open_analysis_envelope,
    validate_v31_authoring_compilation_admission,
    validate_v31_authoring_compilation_receipt,
    validate_v31_proposal_authoring_packet,
)
from ..domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_theory_approval,
)
from ..domain.v31_experiment_contracts import (
    V31ExperimentContractError,
    verify_minimal_experiment_contract,
)
from .v31_research_cycle import (
    V31ResearchCycleError,
    verify_v31_cycle_evaluation,
)
from .v31_cycle_authoring import (
    V31CycleAuthoringCompilerPort,
    V31CycleAuthoringWorkflowError,
    compile_v31_agent_open_analysis,
)
from .v31_durable_bundle import (
    V31DurableBundleError,
    decode_v31_compiled_assembly_bundle,
    seal_v31_compiled_assembly_bundle,
)


class V31AgentTransportWorkflowError(ValueError):
    """The V3.1 Agent workflow cannot safely continue."""


class V31AgentTransportStorePort(Protocol):
    def owner_lease(
        self, *, owner_id: str, acquired_at: str, expires_at: str
    ) -> Any: ...

    def document_exists(self, *, relative_ref: str) -> bool: ...

    def write_document(
        self,
        *,
        lease: Any,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> dict[str, str]: ...

    def artifact_binding(
        self, *, relative_ref: str, digest_field: str
    ) -> dict[str, str]: ...

    def read_bound_document(
        self, binding: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> dict[str, Any]: ...

    def initialize_checkpoint(
        self,
        *,
        lease: Any,
        relative_ref: str,
        checkpoint: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def read_checkpoint(self, *, relative_ref: str) -> dict[str, Any]: ...

    def replace_checkpoint(
        self,
        *,
        lease: Any,
        relative_ref: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def write_transport_evidence(
        self, *, lease: Any, evidence: Mapping[str, Any]
    ) -> dict[str, Any]: ...


_STAGES = ("PROPOSAL", "SELECTION")
_KINDS = ("attempt", "request", "claim", "delivery", "consume")
_DIGEST_FIELDS = {
    "attempt": "attempt_digest",
    "request": "request_digest",
    "claim": "claim_digest",
    "delivery": "delivery_digest",
    "consume": "consume_digest",
}
_STAGE_STATE_FIELDS = frozenset(
    {
        "status",
        "attempt_binding",
        "request_binding",
        "claim_binding",
        "delivery_binding",
        "consume_binding",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "revision",
        "status",
        "stage_order",
        "stage_states",
        "max_attempts_per_stage",
        "failure_binding",
        "transport_evidence_binding",
        "resume_allowed",
        "created_at",
        "updated_at",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        "checkpoint_digest",
    }
)
_CHECKPOINT_STATUSES = {
    "READY_FOR_PROPOSAL",
    "PROPOSAL_IN_PROGRESS",
    "READY_FOR_COMPILATION",
    "READY_FOR_SELECTION",
    "SELECTION_IN_PROGRESS",
    "READY_FOR_EVIDENCE",
    "COMPLETED",
    "FAILED_CLOSED",
}


def render_v31_manual_worker_request(request: Mapping[str, Any]) -> str:
    """Render only the canonical public request for the PTY worker."""

    if not isinstance(request, Mapping):
        raise V31AgentTransportWorkflowError("V31_MANUAL_WORKER_REQUEST_INVALID")
    return canonical_bytes(dict(request)).decode("utf-8")


def parse_v31_manual_worker_payload(raw: str) -> dict[str, Any]:
    """Parse one strict JSON object without admitting general JSON drift."""

    try:
        return loads_json_strict(raw)
    except ValueError as exc:
        raise V31AgentTransportWorkflowError(
            "V31_MANUAL_WORKER_PAYLOAD_JSON_INVALID"
        ) from exc


def _checkpoint_ref(cycle_index: int) -> str:
    return f"cycles/{cycle_index:04d}/agent-transport/checkpoint.json"


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31AgentTransportWorkflowError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31AgentTransportWorkflowError(code) from exc
    if parsed.tzinfo is None:
        raise V31AgentTransportWorkflowError(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31AgentTransportWorkflowError(code)
    return normalized


def _validate_stage_times(times: Mapping[str, str]) -> None:
    fields = (
        "reserved_at",
        "requested_at",
        "claimed_at",
        "delivered_at",
        "consumed_at",
    )
    if not isinstance(times, Mapping) or set(times) != set(fields):
        raise V31AgentTransportWorkflowError("V31_TRANSPORT_STAGE_TIMES_INVALID")
    moments = [
        _moment(times[field], "V31_TRANSPORT_STAGE_TIMES_INVALID")
        for field in fields
    ]
    if moments != sorted(moments):
        raise V31AgentTransportWorkflowError("V31_TRANSPORT_STAGE_TIMES_INVALID")


def _artifact_ref(cycle_index: int, stage: str, kind: str) -> str:
    return (
        f"cycles/{cycle_index:04d}/agent-transport/"
        f"{stage.lower()}/{kind}.json"
    )


def _compilation_ref(cycle_index: int, artifact: str) -> str:
    names = {
        "inputs_receipt": "inputs-receipt.json",
        "agent_proposal": "agent-proposal.json",
        "action_evaluation": "action-evaluation.json",
        "preselection": "cycle-preselection.json",
        "compilation_receipt": "compilation-receipt.json",
        "compiled_assembly_bundle": "compiled-assembly-bundle.json",
        "admission": "compilation-admission.json",
    }
    if artifact not in names:
        raise V31AgentTransportWorkflowError(
            "V31_AUTHORING_COMPILATION_ARTIFACT_INVALID"
        )
    return (
        f"cycles/{cycle_index:04d}/agent-transport/compilation/"
        f"{names[artifact]}"
    )


def _empty_stage(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "attempt_binding": None,
        "request_binding": None,
        "claim_binding": None,
        "delivery_binding": None,
        "consume_binding": None,
    }


def _seal_checkpoint(document: Mapping[str, Any]) -> dict[str, Any]:
    candidate = dict(document)
    candidate.pop("checkpoint_digest", None)
    return self_digest(candidate, "checkpoint_digest")


def _validate_checkpoint(
    checkpoint: Mapping[str, Any], *, run_id: str, cycle_index: int
) -> str:
    try:
        digest = verify_self_digest(checkpoint, "checkpoint_digest")
    except (TypeError, ValueError) as exc:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_CHECKPOINT_DIGEST_INVALID"
        ) from exc
    if (
        not isinstance(checkpoint, Mapping)
        or set(checkpoint) != _CHECKPOINT_FIELDS
        or checkpoint.get("schema_id")
        != "theory_paper_v31_agent_transport_checkpoint"
        or checkpoint.get("schema_version") != "1.0.0"
        or checkpoint.get("run_id") != run_id
        or checkpoint.get("cycle_index") != cycle_index
        or isinstance(checkpoint.get("revision"), bool)
        or not isinstance(checkpoint.get("revision"), int)
        or checkpoint.get("revision", -1) < 0
        or checkpoint.get("status") not in _CHECKPOINT_STATUSES
        or checkpoint.get("stage_order") != list(_STAGES)
        or checkpoint.get("max_attempts_per_stage") != 1
        or checkpoint.get("chat_history_is_authority") is not False
        or checkpoint.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or checkpoint.get("executable") is not False
    ):
        raise V31AgentTransportWorkflowError("V31_TRANSPORT_CHECKPOINT_INVALID")
    created = _moment(
        checkpoint.get("created_at"), "V31_TRANSPORT_CHECKPOINT_TIME_INVALID"
    )
    updated = _moment(
        checkpoint.get("updated_at"), "V31_TRANSPORT_CHECKPOINT_TIME_INVALID"
    )
    if updated < created:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_CHECKPOINT_TIME_INVALID"
        )
    stages = checkpoint.get("stage_states")
    if not isinstance(stages, Mapping) or tuple(stages) != _STAGES:
        raise V31AgentTransportWorkflowError("V31_TRANSPORT_CHECKPOINT_INVALID")
    for stage in _STAGES:
        row = stages[stage]
        if (
            not isinstance(row, Mapping)
            or set(row) != _STAGE_STATE_FIELDS
            or row.get("status")
            not in {"BLOCKED", "READY", "REQUESTED", "CLAIMED", "DELIVERED", "CONSUMED"}
        ):
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_CHECKPOINT_STAGE_INVALID"
            )
        for field in (
            "attempt_binding",
            "request_binding",
            "claim_binding",
            "delivery_binding",
            "consume_binding",
        ):
            if row.get(field) is not None and not isinstance(row[field], Mapping):
                raise V31AgentTransportWorkflowError(
                    "V31_TRANSPORT_CHECKPOINT_STAGE_INVALID"
                )
        required_count = {
            "BLOCKED": 0,
            "READY": 0,
            "REQUESTED": 2,
            "CLAIMED": 3,
            "DELIVERED": 4,
            "CONSUMED": 5,
        }[row["status"]]
        ordered_bindings = [row[f"{kind}_binding"] for kind in _KINDS]
        if any(value is None for value in ordered_bindings[:required_count]) or any(
            value is not None for value in ordered_bindings[required_count:]
        ):
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_CHECKPOINT_STAGE_INVALID"
            )
    proposal_status = stages["PROPOSAL"]["status"]
    selection_status = stages["SELECTION"]["status"]
    status = checkpoint["status"]
    top_level_valid = {
        "READY_FOR_PROPOSAL": proposal_status == "READY"
        and selection_status == "BLOCKED",
        "PROPOSAL_IN_PROGRESS": proposal_status
        in {"REQUESTED", "CLAIMED", "DELIVERED"}
        and selection_status == "BLOCKED",
        "READY_FOR_COMPILATION": proposal_status == "CONSUMED"
        and selection_status == "BLOCKED",
        "READY_FOR_SELECTION": proposal_status == "CONSUMED"
        and selection_status == "READY",
        "SELECTION_IN_PROGRESS": proposal_status == "CONSUMED"
        and selection_status in {"REQUESTED", "CLAIMED", "DELIVERED"},
        "READY_FOR_EVIDENCE": proposal_status == "CONSUMED"
        and selection_status == "CONSUMED",
        "COMPLETED": proposal_status == "CONSUMED"
        and selection_status == "CONSUMED",
        "FAILED_CLOSED": True,
    }[status]
    if not top_level_valid:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_CHECKPOINT_STATE_MISMATCH"
        )
    if checkpoint["status"] == "FAILED_CLOSED":
        if checkpoint.get("failure_binding") is None or checkpoint.get(
            "resume_allowed"
        ) is not False:
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_CHECKPOINT_FAILURE_INVALID"
            )
    elif checkpoint.get("failure_binding") is not None:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_CHECKPOINT_FAILURE_INVALID"
        )
    if checkpoint["status"] == "COMPLETED":
        if (
            checkpoint.get("transport_evidence_binding") is None
            or checkpoint.get("resume_allowed") is not False
        ):
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_CHECKPOINT_EVIDENCE_INVALID"
            )
    elif checkpoint.get("transport_evidence_binding") is not None:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_CHECKPOINT_EVIDENCE_INVALID"
        )
    return digest


def initialize_v31_agent_transport(
    *,
    store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
    created_at: str,
    owner_id: str,
    lease_expires_at: str,
) -> dict[str, Any]:
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or run_id != run_id.strip()
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
    ):
        raise V31AgentTransportWorkflowError("V31_TRANSPORT_IDENTITY_INVALID")
    _moment(created_at, "V31_TRANSPORT_CHECKPOINT_TIME_INVALID")
    ref = _checkpoint_ref(cycle_index)
    with store.owner_lease(
        owner_id=owner_id,
        acquired_at=created_at,
        expires_at=lease_expires_at,
    ) as lease:
        if store.document_exists(relative_ref=ref):
            existing = store.read_checkpoint(relative_ref=ref)
            _validate_checkpoint(
                existing, run_id=run_id, cycle_index=cycle_index
            )
            return existing
        checkpoint = _seal_checkpoint(
            {
                "schema_id": "theory_paper_v31_agent_transport_checkpoint",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "revision": 0,
                "status": "READY_FOR_PROPOSAL",
                "stage_order": list(_STAGES),
                "stage_states": {
                    "PROPOSAL": _empty_stage("READY"),
                    "SELECTION": _empty_stage("BLOCKED"),
                },
                "max_attempts_per_stage": 1,
                "failure_binding": None,
                "transport_evidence_binding": None,
                "resume_allowed": True,
                "created_at": created_at,
                "updated_at": created_at,
                "chat_history_is_authority": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            }
        )
        _validate_checkpoint(
            checkpoint, run_id=run_id, cycle_index=cycle_index
        )
        return store.initialize_checkpoint(
            lease=lease, relative_ref=ref, checkpoint=checkpoint
        )


def _replace_checkpoint(
    *,
    store: V31AgentTransportStorePort,
    lease: Any,
    checkpoint: Mapping[str, Any],
    updates: Mapping[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    candidate = dict(checkpoint)
    candidate.update(dict(updates))
    candidate["revision"] = int(checkpoint["revision"]) + 1
    candidate["updated_at"] = updated_at
    candidate = _seal_checkpoint(candidate)
    _validate_checkpoint(
        candidate,
        run_id=str(checkpoint["run_id"]),
        cycle_index=int(checkpoint["cycle_index"]),
    )
    return store.replace_checkpoint(
        lease=lease,
        relative_ref=_checkpoint_ref(int(checkpoint["cycle_index"])),
        expected_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        checkpoint=candidate,
    )


def _stage_states_with(
    checkpoint: Mapping[str, Any], stage: str, **updates: Any
) -> dict[str, Any]:
    stages = {
        key: dict(value) for key, value in checkpoint["stage_states"].items()
    }
    stages[stage].update(updates)
    return stages


def _binding_for_existing(
    store: V31AgentTransportStorePort,
    *,
    cycle_index: int,
    stage: str,
    kind: str,
) -> dict[str, str] | None:
    ref = _artifact_ref(cycle_index, stage, kind)
    if not store.document_exists(relative_ref=ref):
        return None
    return store.artifact_binding(
        relative_ref=ref, digest_field=_DIGEST_FIELDS[kind]
    )


def _load_stage_documents(
    *,
    store: V31AgentTransportStorePort,
    bindings: Mapping[str, Mapping[str, Any]],
    inputs_receipt: Mapping[str, Any] | None,
    authoring_packet: Mapping[str, Any] | None,
    action_evaluation: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    documents = {
        kind: store.read_bound_document(bindings[f"{kind}_binding"])
        for kind in _KINDS
        if bindings.get(f"{kind}_binding") is not None
    }
    if "attempt" in documents:
        validate_v31_agent_attempt(documents["attempt"])
    if "request" in documents:
        validate_v31_agent_request(
            documents["request"], attempt=documents["attempt"]
        )
    if "claim" in documents:
        validate_v31_agent_claim(
            documents["claim"],
            request=documents["request"],
            attempt=documents["attempt"],
        )
    if "delivery" in documents:
        validate_v31_agent_delivery(
            documents["delivery"],
            request=documents["request"],
            attempt=documents["attempt"],
            claim=documents["claim"],
            inputs_receipt=inputs_receipt,
            authoring_packet=authoring_packet,
            action_evaluation=action_evaluation,
        )
    if "consume" in documents:
        validate_v31_consume_receipt(
            documents["consume"],
            request=documents["request"],
            attempt=documents["attempt"],
            claim=documents["claim"],
            delivery=documents["delivery"],
            inputs_receipt=inputs_receipt,
            authoring_packet=authoring_packet,
            action_evaluation=action_evaluation,
        )
    return documents


def _mark_failed(
    *,
    store: V31AgentTransportStorePort,
    lease: Any,
    checkpoint: Mapping[str, Any],
    stage: str,
    failed_at: str,
    failure_code: str,
) -> dict[str, Any]:
    state = checkpoint["stage_states"][stage]
    digests: dict[str, str | None] = {}
    for kind in ("attempt", "request", "claim", "delivery"):
        binding = state.get(f"{kind}_binding") or _binding_for_existing(
            store,
            cycle_index=int(checkpoint["cycle_index"]),
            stage=stage,
            kind=kind,
        )
        digests[f"{kind}_digest"] = (
            None if binding is None else str(binding["semantic_digest"])
        )
    failure = build_v31_transport_failure(
        run_id=str(checkpoint["run_id"]),
        cycle_index=int(checkpoint["cycle_index"]),
        stage=stage,
        failed_at=failed_at,
        failure_code=failure_code,
        **digests,
    )
    failure_ref = (
        f"cycles/{int(checkpoint['cycle_index']):04d}/agent-transport/"
        f"failures/{failure['failure_digest']}.json"
    )
    binding = store.write_document(
        lease=lease,
        relative_ref=failure_ref,
        document=failure,
        digest_field="failure_digest",
    )
    return _replace_checkpoint(
        store=store,
        lease=lease,
        checkpoint=checkpoint,
        updates={
            "status": "FAILED_CLOSED",
            "failure_binding": binding,
            "resume_allowed": False,
        },
        updated_at=failed_at,
    )


def _consume_delivery(
    *,
    store: V31AgentTransportStorePort,
    lease: Any,
    checkpoint: Mapping[str, Any],
    stage: str,
    bindings: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    consumed_at: str,
    inputs_receipt: Mapping[str, Any] | None,
    authoring_packet: Mapping[str, Any] | None,
    action_evaluation: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    consume = build_v31_consume_receipt(
        request=documents["request"],
        attempt=documents["attempt"],
        claim=documents["claim"],
        delivery=documents["delivery"],
        consumed_at=consumed_at,
        inputs_receipt=inputs_receipt,
        authoring_packet=authoring_packet,
        action_evaluation=action_evaluation,
    )
    consume_binding = store.write_document(
        lease=lease,
        relative_ref=_artifact_ref(
            int(checkpoint["cycle_index"]), stage, "consume"
        ),
        document=consume,
        digest_field="consume_digest",
    )
    bindings["consume_binding"] = consume_binding
    stages = _stage_states_with(
        checkpoint, stage, status="CONSUMED", **bindings
    )
    if stage == "PROPOSAL":
        if documents["request"].get("expected_payload_schema_id") == (
            AUTHORING_ENVELOPE_SCHEMA_ID
        ):
            # A durable open-analysis envelope is not a compiled preselection.
            # Keep selection physically blocked until a production compiler
            # and deterministic replay admission are implemented.
            stages["SELECTION"]["status"] = "BLOCKED"
            status = "READY_FOR_COMPILATION"
        else:
            stages["SELECTION"]["status"] = "READY"
            status = "READY_FOR_SELECTION"
    else:
        status = "READY_FOR_EVIDENCE"
    next_checkpoint = _replace_checkpoint(
        store=store,
        lease=lease,
        checkpoint=checkpoint,
        updates={
            "status": status,
            "stage_states": stages,
            "resume_allowed": True,
        },
        updated_at=consumed_at,
    )
    return next_checkpoint, consume


def _run_stage_once(
    *,
    store: V31AgentTransportStorePort,
    lease: Any,
    checkpoint: Mapping[str, Any],
    stage: str,
    source_binding: Mapping[str, Any],
    proposal_consume_binding: Mapping[str, Any] | None,
    preselection_binding: Mapping[str, Any] | None,
    action_evaluation_binding: Mapping[str, Any] | None,
    selectable_candidate_ids: list[str] | None,
    times: Mapping[str, str],
    agent_call: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    inputs_receipt: Mapping[str, Any] | None,
    authoring_packet: Mapping[str, Any] | None,
    action_evaluation: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_stage_times(times)
    state = checkpoint["stage_states"][stage]
    existing_bindings = {
        f"{kind}_binding": _binding_for_existing(
            store,
            cycle_index=int(checkpoint["cycle_index"]),
            stage=stage,
            kind=kind,
        )
        for kind in _KINDS
    }
    if existing_bindings["consume_binding"] is not None:
        documents = _load_stage_documents(
            store=store,
            bindings=existing_bindings,
            inputs_receipt=inputs_receipt,
            authoring_packet=authoring_packet,
            action_evaluation=action_evaluation,
        )
        if state["status"] != "CONSUMED":
            stages = _stage_states_with(
                checkpoint, stage, status="CONSUMED", **existing_bindings
            )
            authoring_proposal = (
                stage == "PROPOSAL"
                and documents["request"].get("expected_payload_schema_id")
                == AUTHORING_ENVELOPE_SCHEMA_ID
            )
            if stage == "PROPOSAL" and not authoring_proposal:
                stages["SELECTION"]["status"] = "READY"
            checkpoint = _replace_checkpoint(
                store=store,
                lease=lease,
                checkpoint=checkpoint,
                updates={
                    "status": (
                        (
                            "READY_FOR_COMPILATION"
                            if authoring_proposal
                            else "READY_FOR_SELECTION"
                        )
                        if stage == "PROPOSAL"
                        else "READY_FOR_EVIDENCE"
                    ),
                    "stage_states": stages,
                    "resume_allowed": True,
                },
                updated_at=documents["consume"]["consumed_at"],
            )
        return checkpoint, documents["consume"]
    if existing_bindings["delivery_binding"] is not None:
        required = ("attempt_binding", "request_binding", "claim_binding")
        if any(existing_bindings[name] is None for name in required):
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_DELIVERY_PREFIX_INCOMPLETE"
            )
        documents = _load_stage_documents(
            store=store,
            bindings=existing_bindings,
            inputs_receipt=inputs_receipt,
            authoring_packet=authoring_packet,
            action_evaluation=action_evaluation,
        )
        stages = _stage_states_with(
            checkpoint, stage, status="DELIVERED", **existing_bindings
        )
        checkpoint = _replace_checkpoint(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            updates={
                "status": f"{stage}_IN_PROGRESS",
                "stage_states": stages,
                "resume_allowed": True,
            },
            updated_at=documents["delivery"]["delivered_at"],
        )
        return _consume_delivery(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            stage=stage,
            bindings=existing_bindings,
            documents=documents,
            consumed_at=times["consumed_at"],
            inputs_receipt=inputs_receipt,
            authoring_packet=authoring_packet,
            action_evaluation=action_evaluation,
        )
    if any(existing_bindings[f"{kind}_binding"] is not None for kind in ("attempt", "request", "claim")):
        _mark_failed(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            stage=stage,
            failed_at=times["consumed_at"],
            failure_code="INCOMPLETE_ATTEMPT_WITHOUT_DURABLE_DELIVERY",
        )
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_INCOMPLETE_ATTEMPT_FAILED_CLOSED"
        )
    if state["status"] != "READY":
        raise V31AgentTransportWorkflowError("V31_TRANSPORT_STAGE_NOT_READY")

    try:
        attempt = reserve_v31_agent_attempt(
            run_id=str(checkpoint["run_id"]),
            cycle_index=int(checkpoint["cycle_index"]),
            stage=stage,
            reserved_at=times["reserved_at"],
            checkpoint_digest_before_reservation=str(
                checkpoint["checkpoint_digest"]
            ),
        )
        attempt_binding = store.write_document(
            lease=lease,
            relative_ref=_artifact_ref(
                int(checkpoint["cycle_index"]), stage, "attempt"
            ),
            document=attempt,
            digest_field="attempt_digest",
        )
        request = build_v31_agent_request(
            attempt=attempt,
            created_at=times["requested_at"],
            inputs_receipt_binding=(
                source_binding
                if stage == "PROPOSAL" and authoring_packet is None
                else None
            ),
            authoring_packet_binding=(
                source_binding
                if stage == "PROPOSAL" and authoring_packet is not None
                else None
            ),
            proposal_consume_binding=proposal_consume_binding,
            preselection_binding=preselection_binding,
            action_evaluation_binding=action_evaluation_binding,
            selectable_candidate_ids=selectable_candidate_ids,
        )
        request_binding = store.write_document(
            lease=lease,
            relative_ref=_artifact_ref(
                int(checkpoint["cycle_index"]), stage, "request"
            ),
            document=request,
            digest_field="request_digest",
        )
        bindings = {
            "attempt_binding": attempt_binding,
            "request_binding": request_binding,
            "claim_binding": None,
            "delivery_binding": None,
            "consume_binding": None,
        }
        checkpoint = _replace_checkpoint(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            updates={
                "status": f"{stage}_IN_PROGRESS",
                "stage_states": _stage_states_with(
                    checkpoint, stage, status="REQUESTED", **bindings
                ),
                "resume_allowed": False,
            },
            updated_at=times["requested_at"],
        )
        claim = build_v31_agent_claim(
            request=request, attempt=attempt, claimed_at=times["claimed_at"]
        )
        claim_binding = store.write_document(
            lease=lease,
            relative_ref=_artifact_ref(
                int(checkpoint["cycle_index"]), stage, "claim"
            ),
            document=claim,
            digest_field="claim_digest",
        )
        bindings["claim_binding"] = claim_binding
        checkpoint = _replace_checkpoint(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            updates={
                "stage_states": _stage_states_with(
                    checkpoint, stage, status="CLAIMED", **bindings
                ),
                "resume_allowed": False,
            },
            updated_at=times["claimed_at"],
        )

        # The only Agent adapter call is below.  Attempt, request, claim, and
        # their checkpoint bindings are already durable before control reaches it.
        payload = agent_call(request)
        if not isinstance(payload, Mapping):
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_AGENT_PAYLOAD_INVALID"
            )
        delivery = build_v31_agent_delivery(
            request=request,
            attempt=attempt,
            claim=claim,
            payload=payload,
            delivered_at=times["delivered_at"],
            inputs_receipt=inputs_receipt,
            authoring_packet=authoring_packet,
            action_evaluation=action_evaluation,
        )
        delivery_binding = store.write_document(
            lease=lease,
            relative_ref=_artifact_ref(
                int(checkpoint["cycle_index"]), stage, "delivery"
            ),
            document=delivery,
            digest_field="delivery_digest",
        )
        bindings["delivery_binding"] = delivery_binding
        checkpoint = _replace_checkpoint(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            updates={
                "stage_states": _stage_states_with(
                    checkpoint, stage, status="DELIVERED", **bindings
                ),
                "resume_allowed": True,
            },
            updated_at=times["delivered_at"],
        )
        documents = {
            "attempt": attempt,
            "request": request,
            "claim": claim,
            "delivery": delivery,
        }
        return _consume_delivery(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            stage=stage,
            bindings=bindings,
            documents=documents,
            consumed_at=times["consumed_at"],
            inputs_receipt=inputs_receipt,
            authoring_packet=authoring_packet,
            action_evaluation=action_evaluation,
        )
    except BaseException as exc:
        durable_tail_exists = any(
            store.document_exists(
                relative_ref=_artifact_ref(
                    int(checkpoint["cycle_index"]), stage, kind
                )
            )
            for kind in ("delivery", "consume")
        )
        if durable_tail_exists:
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_DURABLE_DELIVERY_PENDING_DETERMINISTIC_RECOVERY"
            ) from exc
        latest = store.read_checkpoint(
            relative_ref=_checkpoint_ref(int(checkpoint["cycle_index"]))
        )
        if latest.get("status") != "FAILED_CLOSED":
            try:
                _mark_failed(
                    store=store,
                    lease=lease,
                    checkpoint=latest,
                    stage=stage,
                    failed_at=times["consumed_at"],
                    failure_code=f"AGENT_STAGE_FAILED:{type(exc).__name__}",
                )
            except Exception as failure_exc:
                raise V31AgentTransportWorkflowError(
                    "V31_TRANSPORT_FAILURE_PERSISTENCE_FAILED"
                ) from failure_exc
        if isinstance(exc, V31AgentTransportWorkflowError):
            raise
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_AGENT_STAGE_FAILED_CLOSED"
        ) from exc


def run_v31_proposal_transport(
    *,
    store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
    inputs_receipt_binding: Mapping[str, Any],
    owner_id: str,
    lease_acquired_at: str,
    lease_expires_at: str,
    stage_times: Mapping[str, str],
    agent_call: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    inputs = store.read_bound_document(inputs_receipt_binding)
    inputs_digest = verify_v31_inputs_receipt(inputs)
    if (
        inputs.get("run_id") != run_id
        or inputs.get("cycle_index") != cycle_index
        or inputs_digest != inputs_receipt_binding.get("semantic_digest")
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_PROPOSAL_INPUT_BINDING_INVALID"
        )
    with store.owner_lease(
        owner_id=owner_id,
        acquired_at=lease_acquired_at,
        expires_at=lease_expires_at,
    ) as lease:
        checkpoint = store.read_checkpoint(relative_ref=_checkpoint_ref(cycle_index))
        _validate_checkpoint(checkpoint, run_id=run_id, cycle_index=cycle_index)
        if checkpoint["status"] == "FAILED_CLOSED":
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_PERMANENTLY_FAILED_CLOSED"
            )
        if checkpoint["status"] == "READY_FOR_COMPILATION":
            raise V31AgentTransportWorkflowError(
                "V31_SELECTION_BLOCKED_AUTHORING_COMPILER_REQUIRED"
            )
        checkpoint, consume = _run_stage_once(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            stage="PROPOSAL",
            source_binding=inputs_receipt_binding,
            proposal_consume_binding=None,
            preselection_binding=None,
            action_evaluation_binding=None,
            selectable_candidate_ids=None,
            times=stage_times,
            agent_call=agent_call,
            inputs_receipt=inputs,
            authoring_packet=None,
            action_evaluation=None,
        )
        return {
            "status": checkpoint["status"],
            "consume_receipt": consume,
            "transport_class": V31_LEGACY_PROPOSAL_TRANSPORT_CLASS,
            "q7_run_ready": False,
        }


def run_v31_authoring_transport(
    *,
    store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
    authoring_packet_binding: Mapping[str, Any],
    owner_id: str,
    lease_acquired_at: str,
    lease_expires_at: str,
    stage_times: Mapping[str, str],
    agent_call: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Durably collect one open Agent analysis, then stop before compilation."""

    packet = store.read_bound_document(authoring_packet_binding)
    try:
        packet_digest = validate_v31_proposal_authoring_packet(packet)
    except V31CycleAuthoringError as exc:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_AUTHORING_PACKET_INVALID"
        ) from exc
    if (
        packet.get("run_id") != run_id
        or packet.get("cycle_index") != cycle_index
        or packet_digest != authoring_packet_binding.get("semantic_digest")
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_AUTHORING_PACKET_BINDING_INVALID"
        )
    # Every reference visible to the Agent must physically exist and match its
    # semantic hash before an attempt is reserved.  Deep Domain reconstruction
    # is repeated by the later compiler; this preflight prevents an Agent from
    # being asked to analyze missing or drifted source material.
    completion = store.read_bound_document(
        packet["source_qualification_completion_binding"]
    )
    pit_dataset = store.read_bound_document(packet["pit_dataset_binding"])
    information_records = [
        store.read_bound_document(binding)
        for binding in packet["information_event_bindings"]
    ]
    for binding in packet["association_estimation_receipt_bindings"]:
        store.read_bound_document(binding)
    for binding in packet["previous_head_bindings"].values():
        if binding is not None:
            store.read_bound_document(binding)
    authority_context = packet["authority_context"]
    approval = store.read_bound_document(
        authority_context["theory_approval_binding"]
    )
    experiment_subject = store.read_bound_document(
        authority_context["experiment_subject_binding"]
    )
    try:
        validate_v31_theory_approval(approval)
        verify_minimal_experiment_contract(experiment_subject)
    except (V31AuthorizationError, V31ExperimentContractError) as exc:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_AUTHORING_PRESTART_AUTHORITY_INVALID"
        ) from exc
    active_binding = authority_context["active_authority_binding"]
    authority = (
        None
        if active_binding is None
        else store.read_bound_document(active_binding)
    )
    qualification_only = (
        packet["authoring_purpose"] == "TRANSPORT_QUALIFICATION_ONLY"
    )
    if (
        completion.get("pit_dataset_digest")
        != packet["pit_dataset_binding"]["semantic_digest"]
        or pit_dataset.get("decision_at") != packet["decision_at"]
        or completion.get("information_event_digests")
        != [row.get("information_event_digest") for row in information_records]
        or experiment_subject.get("run_id") != run_id
        or experiment_subject.get("instrument", {}).get("instrument_id")
        != packet["symbol"]
        or (
            qualification_only
            and (
                authority is not None
                or authority_context["experiment_start_authorized"] is not False
            )
        )
        or (
            not qualification_only
            and (
                not isinstance(authority, Mapping)
                or authority.get("status") != "ACTIVE_FROZEN_RESEARCH"
                or authority.get("experiment_start_authorized") is not True
                or authority.get("authorized_run_id") != run_id
                or not isinstance(authority.get("instrument"), Mapping)
                or authority["instrument"].get("instrument_id")
                != packet["symbol"]
                or authority.get("executable") is not False
                or authority_context["experiment_start_authorized"] is not True
            )
        )
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_AUTHORING_SOURCE_OR_AUTHORITY_MISMATCH"
        )
    with store.owner_lease(
        owner_id=owner_id,
        acquired_at=lease_acquired_at,
        expires_at=lease_expires_at,
    ) as lease:
        checkpoint = store.read_checkpoint(relative_ref=_checkpoint_ref(cycle_index))
        _validate_checkpoint(checkpoint, run_id=run_id, cycle_index=cycle_index)
        if checkpoint["status"] == "FAILED_CLOSED":
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_PERMANENTLY_FAILED_CLOSED"
            )
        checkpoint, consume = _run_stage_once(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            stage="PROPOSAL",
            source_binding=authoring_packet_binding,
            proposal_consume_binding=None,
            preselection_binding=None,
            action_evaluation_binding=None,
            selectable_candidate_ids=None,
            times=stage_times,
            agent_call=agent_call,
            inputs_receipt=None,
            authoring_packet=packet,
            action_evaluation=None,
        )
        if checkpoint["status"] != "READY_FOR_COMPILATION" or checkpoint[
            "stage_states"
        ]["SELECTION"]["status"] != "BLOCKED":
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_AUTHORING_DID_NOT_STOP_BEFORE_SELECTION"
            )
        delivery = store.read_bound_document(
            checkpoint["stage_states"]["PROPOSAL"]["delivery_binding"]
        )
        return {
            "status": "READY_FOR_COMPILATION",
            "consume_receipt": consume,
            "agent_authoring_envelope": dict(delivery["payload"]),
            "transport_class": "V31_OPEN_AUTHORING_REQUIRES_COMPILER",
            "q7_run_ready": False,
            "selection_unblocked": False,
        }


def verify_v31_authoring_compilation_bundle(
    *,
    store: V31AgentTransportStorePort,
    admission_binding: Mapping[str, Any],
    expected_run_id: str | None = None,
    expected_cycle_index: int | None = None,
) -> dict[str, Any]:
    """Physically replay the complete authoring-to-preselection admission."""

    try:
        admission = store.read_bound_document(admission_binding)
        admission_digest = validate_v31_authoring_compilation_admission(
            admission
        )
        if admission_digest != admission_binding.get("semantic_digest"):
            raise V31AgentTransportWorkflowError(
                "V31_AUTHORING_COMPILATION_ADMISSION_BINDING_INVALID"
            )
        run_id = str(admission["run_id"])
        cycle_index = int(admission["cycle_index"])
        if (
            (expected_run_id is not None and run_id != expected_run_id)
            or (
                expected_cycle_index is not None
                and cycle_index != expected_cycle_index
            )
        ):
            raise V31AgentTransportWorkflowError(
                "V31_AUTHORING_COMPILATION_ADMISSION_IDENTITY_MISMATCH"
            )
        packet = store.read_bound_document(
            admission["authoring_packet_binding"]
        )
        validate_v31_proposal_authoring_packet(packet)
        proposal_bindings = {
            "attempt_binding": admission["proposal_attempt_binding"],
            "request_binding": admission["proposal_request_binding"],
            "claim_binding": admission["proposal_claim_binding"],
            "delivery_binding": admission["proposal_delivery_binding"],
            "consume_binding": admission["proposal_consume_binding"],
        }
        proposal_documents = _load_stage_documents(
            store=store,
            bindings=proposal_bindings,
            inputs_receipt=None,
            authoring_packet=packet,
            action_evaluation=None,
        )
        request = proposal_documents["request"]
        delivery = proposal_documents["delivery"]
        consume = proposal_documents["consume"]
        envelope = delivery["payload"]
        envelope_digest = validate_v31_agent_open_analysis_envelope(
            envelope, authoring_packet=packet
        )
        if (
            request.get("authoring_packet_binding")
            != admission["authoring_packet_binding"]
            or request.get("expected_payload_schema_id")
            != AUTHORING_ENVELOPE_SCHEMA_ID
            or delivery.get("payload_digest") != envelope_digest
            or consume.get("payload_digest") != envelope_digest
            or consume.get("validation_status")
            != "SEMANTIC_AND_PHYSICAL_BINDINGS_VERIFIED"
        ):
            raise V31AgentTransportWorkflowError(
                "V31_AUTHORING_COMPILATION_PROPOSAL_PREFIX_INVALID"
            )

        inputs = store.read_bound_document(admission["inputs_receipt_binding"])
        proposal = store.read_bound_document(admission["agent_proposal_binding"])
        evaluation = store.read_bound_document(
            admission["action_evaluation_binding"]
        )
        preselection = store.read_bound_document(admission["preselection_binding"])
        compilation = store.read_bound_document(
            admission["compilation_receipt_binding"]
        )
        compiled_assembly_bundle = store.read_bound_document(
            admission["compiled_assembly_bundle_binding"]
        )
        inputs_digest = verify_v31_inputs_receipt(inputs)
        proposal_digest = verify_v31_agent_proposal(
            proposal, inputs_receipt=inputs
        )
        evaluation_digest = verify_complete_action_evaluation(evaluation)
        preselection_digest = verify_v31_cycle_evaluation(preselection)
        compilation_digest = validate_v31_authoring_compilation_receipt(
            compilation,
            authoring_packet=packet,
            authoring_envelope=envelope,
        )
        assembly_inputs, replayed_preselection = (
            decode_v31_compiled_assembly_bundle(compiled_assembly_bundle)
        )
        expected_bindings = (
            ("inputs_receipt_binding", inputs_digest),
            ("agent_proposal_binding", proposal_digest),
            ("action_evaluation_binding", evaluation_digest),
            ("preselection_binding", preselection_digest),
            ("compilation_receipt_binding", compilation_digest),
            (
                "compiled_assembly_bundle_binding",
                str(
                    compiled_assembly_bundle[
                        COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD
                    ]
                ),
            ),
        )
        if any(
            admission[field]["semantic_digest"] != digest
            for field, digest in expected_bindings
        ) or (
            packet.get("run_id") != run_id
            or packet.get("cycle_index") != cycle_index
            or inputs.get("run_id") != run_id
            or inputs.get("cycle_index") != cycle_index
            or preselection.get("run_id") != run_id
            or preselection.get("cycle_index") != cycle_index
            or preselection.get("inputs_receipt_digest") != inputs_digest
            or preselection.get("agent_proposal_digest") != proposal_digest
            or preselection.get("action_evaluation_digest")
            != evaluation_digest
            or compilation.get("inputs_receipt_digest") != inputs_digest
            or compilation.get("agent_proposal_digest") != proposal_digest
            or compilation.get("action_evaluation_digest")
            != evaluation_digest
            or compilation.get("preselection_digest") != preselection_digest
            or compilation.get("compiler_id") != admission["compiler_id"]
            or compiled_assembly_bundle.get("authoring_packet_digest")
            != packet["authoring_packet_digest"]
            or compiled_assembly_bundle.get("agent_authoring_envelope_digest")
            != envelope_digest
            or compiled_assembly_bundle.get("compiler_id")
            != admission["compiler_id"]
            or replayed_preselection != dict(preselection)
            or assembly_inputs.get("inputs_receipt") != dict(inputs)
            or assembly_inputs.get("agent_proposal") != dict(proposal)
            or assembly_inputs.get("action_evaluation") != dict(evaluation)
            or preselection.get("selection_fields_admitted") is not False
            or preselection.get("executable") is not False
        ):
            raise V31AgentTransportWorkflowError(
                "V31_AUTHORING_COMPILATION_REPLAY_MISMATCH"
            )
        return {
            "admission": dict(admission),
            "admission_binding": dict(admission_binding),
            "authoring_packet": dict(packet),
            "agent_authoring_envelope": dict(envelope),
            "proposal_transport_documents": proposal_documents,
            "inputs_receipt": dict(inputs),
            "agent_proposal": dict(proposal),
            "action_evaluation": dict(evaluation),
            "preselection": dict(preselection),
            "compilation_receipt": dict(compilation),
            "compiled_assembly_bundle": dict(compiled_assembly_bundle),
            "assembly_inputs": assembly_inputs,
        }
    except V31AgentTransportWorkflowError:
        raise
    except (
        V31AgentTransportError,
        V31CycleAuthoringError,
        V31DurableBundleError,
        V31ResearchCycleError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V31AgentTransportWorkflowError(
            "V31_AUTHORING_COMPILATION_BUNDLE_INVALID"
        ) from exc


def run_v31_authoring_compilation(
    *,
    store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
    authoring_packet_binding: Mapping[str, Any],
    compiled_at: str,
    compiler: V31CycleAuthoringCompilerPort,
    owner_id: str,
    lease_acquired_at: str,
    lease_expires_at: str,
) -> dict[str, Any]:
    """Compile one consumed open envelope and durably unblock selection."""

    admission_ref = _compilation_ref(cycle_index, "admission")
    artifact_specs = {
        "inputs_receipt": "inputs_receipt_digest",
        "agent_proposal": "agent_proposal_digest",
        "action_evaluation": "action_evaluation_digest",
        "preselection": "preselection_digest",
        "compilation_receipt": "authoring_compilation_receipt_digest",
        "compiled_assembly_bundle": COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
    }
    with store.owner_lease(
        owner_id=owner_id,
        acquired_at=lease_acquired_at,
        expires_at=lease_expires_at,
    ) as lease:
        checkpoint = store.read_checkpoint(relative_ref=_checkpoint_ref(cycle_index))
        _validate_checkpoint(checkpoint, run_id=run_id, cycle_index=cycle_index)
        if checkpoint["status"] == "FAILED_CLOSED":
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_PERMANENTLY_FAILED_CLOSED"
            )
        if store.document_exists(relative_ref=admission_ref):
            binding = store.artifact_binding(
                relative_ref=admission_ref,
                digest_field=AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
            )
            replay = verify_v31_authoring_compilation_bundle(
                store=store,
                admission_binding=binding,
                expected_run_id=run_id,
                expected_cycle_index=cycle_index,
            )
        else:
            partial = [
                name
                for name in artifact_specs
                if store.document_exists(
                    relative_ref=_compilation_ref(cycle_index, name)
                )
            ]
            if partial:
                _mark_failed(
                    store=store,
                    lease=lease,
                    checkpoint=checkpoint,
                    stage="PROPOSAL",
                    failed_at=compiled_at,
                    failure_code="INCOMPLETE_COMPILATION_WITHOUT_ADMISSION",
                )
                raise V31AgentTransportWorkflowError(
                    "V31_AUTHORING_INCOMPLETE_COMPILATION_FAILED_CLOSED"
                )
            if checkpoint["status"] != "READY_FOR_COMPILATION":
                raise V31AgentTransportWorkflowError(
                    "V31_AUTHORING_COMPILATION_NOT_READY"
                )
            proposal_state = checkpoint["stage_states"]["PROPOSAL"]
            request = store.read_bound_document(proposal_state["request_binding"])
            if (
                request.get("expected_payload_schema_id")
                != AUTHORING_ENVELOPE_SCHEMA_ID
                or request.get("authoring_packet_binding")
                != dict(authoring_packet_binding)
            ):
                raise V31AgentTransportWorkflowError(
                    "V31_AUTHORING_COMPILATION_PACKET_PREFIX_MISMATCH"
                )
            packet = store.read_bound_document(authoring_packet_binding)
            validate_v31_proposal_authoring_packet(packet)
            proposal_documents = _load_stage_documents(
                store=store,
                bindings=proposal_state,
                inputs_receipt=None,
                authoring_packet=packet,
                action_evaluation=None,
            )
            envelope = proposal_documents["delivery"]["payload"]
            try:
                compiled = compile_v31_agent_open_analysis(
                    authoring_packet=packet,
                    authoring_envelope=envelope,
                    compiled_at=compiled_at,
                    compiler=compiler,
                )
            except V31CycleAuthoringWorkflowError as exc:
                _mark_failed(
                    store=store,
                    lease=lease,
                    checkpoint=checkpoint,
                    stage="PROPOSAL",
                    failed_at=compiled_at,
                    failure_code="AUTHORING_COMPILATION_FAILED_CLOSED",
                )
                raise V31AgentTransportWorkflowError(
                    "V31_AUTHORING_COMPILATION_FAILED_CLOSED"
                ) from exc
            documents = {
                "inputs_receipt": compiled["inputs_receipt"],
                "agent_proposal": compiled["agent_proposal"],
                "action_evaluation": compiled["action_evaluation"],
                "preselection": compiled["preselection"],
                "compilation_receipt": compiled["compilation_receipt"],
                "compiled_assembly_bundle": seal_v31_compiled_assembly_bundle(
                    assembly_inputs=compiled["assembly_inputs"],
                    authoring_packet_digest=packet["authoring_packet_digest"],
                    agent_authoring_envelope_digest=envelope[
                        "agent_authoring_envelope_digest"
                    ],
                    compiler_id=str(
                        compiled["compilation_receipt"]["compiler_id"]
                    ),
                    preselection=compiled["preselection"],
                ),
            }
            bindings = {
                name: store.write_document(
                    lease=lease,
                    relative_ref=_compilation_ref(cycle_index, name),
                    document=document,
                    digest_field=artifact_specs[name],
                )
                for name, document in documents.items()
            }
            admission = seal_v31_authoring_compilation_admission(
                run_id=run_id,
                cycle_index=cycle_index,
                admitted_at=compiled_at,
                compiler_id=str(compiled["compilation_receipt"]["compiler_id"]),
                authoring_packet_binding=authoring_packet_binding,
                proposal_attempt_binding=proposal_state["attempt_binding"],
                proposal_request_binding=proposal_state["request_binding"],
                proposal_claim_binding=proposal_state["claim_binding"],
                proposal_delivery_binding=proposal_state["delivery_binding"],
                proposal_consume_binding=proposal_state["consume_binding"],
                inputs_receipt_binding=bindings["inputs_receipt"],
                agent_proposal_binding=bindings["agent_proposal"],
                action_evaluation_binding=bindings["action_evaluation"],
                preselection_binding=bindings["preselection"],
                compilation_receipt_binding=bindings["compilation_receipt"],
                compiled_assembly_bundle_binding=bindings[
                    "compiled_assembly_bundle"
                ],
            )
            binding = store.write_document(
                lease=lease,
                relative_ref=admission_ref,
                document=admission,
                digest_field=AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
            )
            replay = verify_v31_authoring_compilation_bundle(
                store=store,
                admission_binding=binding,
                expected_run_id=run_id,
                expected_cycle_index=cycle_index,
            )

        if checkpoint["status"] == "READY_FOR_COMPILATION":
            stages = _stage_states_with(
                checkpoint,
                "SELECTION",
                status="READY",
                attempt_binding=None,
                request_binding=None,
                claim_binding=None,
                delivery_binding=None,
                consume_binding=None,
            )
            checkpoint = _replace_checkpoint(
                store=store,
                lease=lease,
                checkpoint=checkpoint,
                updates={
                    "status": "READY_FOR_SELECTION",
                    "stage_states": stages,
                    "resume_allowed": True,
                },
                updated_at=compiled_at,
            )
        elif checkpoint["status"] != "READY_FOR_SELECTION":
            raise V31AgentTransportWorkflowError(
                "V31_AUTHORING_COMPILATION_CHECKPOINT_STATE_INVALID"
            )
        return {
            "status": "READY_FOR_SELECTION",
            "compilation_admission_binding": dict(binding),
            "inputs_receipt_binding": replay["admission"][
                "inputs_receipt_binding"
            ],
            "agent_proposal_binding": replay["admission"][
                "agent_proposal_binding"
            ],
            "action_evaluation_binding": replay["admission"][
                "action_evaluation_binding"
            ],
            "preselection_binding": replay["admission"]["preselection_binding"],
            "compilation_receipt_binding": replay["admission"][
                "compilation_receipt_binding"
            ],
            "compiled_assembly_bundle_binding": replay["admission"][
                "compiled_assembly_bundle_binding"
            ],
            "selection_unblocked": True,
            "selection_performed": False,
            "q7_compilation_admitted": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }


def _finalize_evidence(
    *,
    store: V31AgentTransportStorePort,
    lease: Any,
    checkpoint: Mapping[str, Any],
    completed_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_rows: dict[str, Any] = {}
    payload_digests: dict[str, str] = {}
    for stage in _STAGES:
        state = checkpoint["stage_states"][stage]
        if state["status"] != "CONSUMED":
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_EVIDENCE_REQUIRES_TWO_CONSUMES"
            )
        stage_rows[stage] = {
            "attempt_binding": state["attempt_binding"],
            "request_binding": state["request_binding"],
            "claim_binding": state["claim_binding"],
            "delivery_binding": state["delivery_binding"],
            "consume_binding": state["consume_binding"],
            "attempt_count": 1,
        }
        delivery = store.read_bound_document(state["delivery_binding"])
        payload_digests[stage] = str(delivery["payload_digest"])
    evidence = seal_v31_transport_evidence(
        run_id=str(checkpoint["run_id"]),
        cycle_index=int(checkpoint["cycle_index"]),
        completed_at=completed_at,
        stages=stage_rows,
        proposal_payload_digest=payload_digests["PROPOSAL"],
        selection_payload_digest=payload_digests["SELECTION"],
    )
    binding = store.write_transport_evidence(lease=lease, evidence=evidence)
    verify_v31_transport_evidence_bundle(store=store, evidence_binding=binding)
    final = _replace_checkpoint(
        store=store,
        lease=lease,
        checkpoint=checkpoint,
        updates={
            "status": "COMPLETED",
            "transport_evidence_binding": binding,
            "resume_allowed": False,
        },
        updated_at=completed_at,
    )
    return final, binding


def verify_v31_transport_evidence_bundle(
    *,
    store: V31AgentTransportStorePort,
    evidence_binding: Mapping[str, Any],
) -> str:
    if (
        not isinstance(evidence_binding, Mapping)
        or set(evidence_binding)
        != {"cycle_index", "relative_ref", "semantic_digest", "physical_sha256"}
        or isinstance(evidence_binding.get("cycle_index"), bool)
        or not isinstance(evidence_binding.get("cycle_index"), int)
        or evidence_binding.get("cycle_index", 0) < 1
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_EVIDENCE_BINDING_INVALID"
        )
    expected_ref = (
        f"cycles/{int(evidence_binding['cycle_index']):04d}/transport-evidence/"
        f"{evidence_binding['semantic_digest']}.json"
    )
    if evidence_binding.get("relative_ref") != expected_ref:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_EVIDENCE_BINDING_INVALID"
        )
    internal = store.artifact_binding(
        relative_ref=str(evidence_binding["relative_ref"]),
        digest_field="transport_evidence_digest",
    )
    if (
        internal["semantic_digest"] != evidence_binding.get("semantic_digest")
        or internal["physical_sha256"] != evidence_binding.get("physical_sha256")
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_EVIDENCE_BINDING_DRIFT"
        )
    evidence = store.read_bound_document(internal)
    digest = validate_v31_transport_evidence(evidence)
    if evidence.get("cycle_index") != evidence_binding.get("cycle_index"):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_EVIDENCE_BINDING_INVALID"
        )

    proposal_bindings = evidence["stages"]["PROPOSAL"]
    proposal_request = store.read_bound_document(
        proposal_bindings["request_binding"]
    )
    authoring_proposal = (
        proposal_request.get("expected_payload_schema_id")
        == AUTHORING_ENVELOPE_SCHEMA_ID
    )
    if authoring_proposal:
        packet = store.read_bound_document(
            proposal_request["authoring_packet_binding"]
        )
        proposal_documents = _load_stage_documents(
            store=store,
            bindings=proposal_bindings,
            inputs_receipt=None,
            authoring_packet=packet,
            action_evaluation=None,
        )
        admission_ref = _compilation_ref(
            int(evidence["cycle_index"]), "admission"
        )
        if not store.document_exists(relative_ref=admission_ref):
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_EVIDENCE_COMPILATION_ADMISSION_MISSING"
            )
        compilation = verify_v31_authoring_compilation_bundle(
            store=store,
            admission_binding=store.artifact_binding(
                relative_ref=admission_ref,
                digest_field=AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
            ),
            expected_run_id=str(evidence["run_id"]),
            expected_cycle_index=int(evidence["cycle_index"]),
        )
        compiled_proposal_digest = compilation["admission"][
            "agent_proposal_binding"
        ]["semantic_digest"]
    else:
        inputs_receipt = store.read_bound_document(
            proposal_request["inputs_receipt_binding"]
        )
        proposal_documents = _load_stage_documents(
            store=store,
            bindings=proposal_bindings,
            inputs_receipt=inputs_receipt,
            authoring_packet=None,
            action_evaluation=None,
        )
        compilation = None
        compiled_proposal_digest = proposal_documents["delivery"][
            "payload_digest"
        ]

    selection_bindings = evidence["stages"]["SELECTION"]
    selection_request = store.read_bound_document(
        selection_bindings["request_binding"]
    )
    preselection = store.read_bound_document(
        selection_request["preselection_binding"]
    )
    action_evaluation = store.read_bound_document(
        selection_request["action_evaluation_binding"]
    )
    try:
        verify_v31_cycle_evaluation(preselection)
        verify_complete_action_evaluation(action_evaluation)
    except (V31ResearchCycleError, ValueError) as exc:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_EVIDENCE_PRESELECTION_INVALID"
        ) from exc
    selection_documents = _load_stage_documents(
        store=store,
        bindings=selection_bindings,
        inputs_receipt=None,
        authoring_packet=None,
        action_evaluation=action_evaluation,
    )
    if (
        (
            compilation is not None
            and (
                compilation["admission"]["preselection_binding"]
                != selection_request["preselection_binding"]
                or compilation["admission"]["action_evaluation_binding"]
                != selection_request["action_evaluation_binding"]
            )
        )
        or
        selection_request["proposal_consume_binding"]
        != proposal_bindings["consume_binding"]
        or selection_request["selectable_candidate_ids"]
        != preselection["selectable_candidate_ids"]
        or preselection["agent_proposal_digest"]
        != compiled_proposal_digest
        or preselection["action_evaluation_digest"]
        != action_evaluation["action_evaluation_digest"]
        or evidence["proposal_payload_digest"]
        != proposal_documents["delivery"]["payload_digest"]
        or evidence["selection_payload_digest"]
        != selection_documents["delivery"]["payload_digest"]
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_EVIDENCE_CROSS_BINDING_INVALID"
        )
    return digest


def verify_completed_v31_agent_transport(
    *,
    store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
) -> Mapping[str, Any]:
    """Replay one completed two-stage Q7 transport without Agent invocation.

    The completed checkpoint and every attempt/request/claim/delivery/consume
    artifact are re-read through their physical bindings.  This helper never
    calls an Agent and cannot turn a partial transport or a bare evidence
    digest into qualification evidence.
    """

    checkpoint = store.read_checkpoint(relative_ref=_checkpoint_ref(cycle_index))
    _validate_checkpoint(checkpoint, run_id=run_id, cycle_index=cycle_index)
    if (
        checkpoint.get("status") != "COMPLETED"
        or checkpoint.get("resume_allowed") is not False
        or checkpoint.get("failure_binding") is not None
        or checkpoint.get("transport_evidence_binding") is None
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_NOT_DURABLY_COMPLETED"
        )
    evidence_binding = dict(checkpoint["transport_evidence_binding"])
    evidence_digest = verify_v31_transport_evidence_bundle(
        store=store, evidence_binding=evidence_binding
    )
    internal_binding = store.artifact_binding(
        relative_ref=str(evidence_binding["relative_ref"]),
        digest_field="transport_evidence_digest",
    )
    evidence = store.read_bound_document(internal_binding)
    if (
        evidence_digest != evidence_binding.get("semantic_digest")
        or internal_binding.get("physical_sha256")
        != evidence_binding.get("physical_sha256")
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_COMPLETION_EVIDENCE_DRIFT"
        )
    return {
        "run_id": run_id,
        "cycle_index": cycle_index,
        "checkpoint": dict(checkpoint),
        "transport_evidence": dict(evidence),
        "transport_evidence_binding": evidence_binding,
    }


def verify_completed_v31_authoring_transport(
    *,
    store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
    expected_authoring_purpose: str | None = None,
) -> Mapping[str, Any]:
    """Replay terminal transport plus its separate compilation admission.

    The generic transport evidence intentionally records the proposal payload
    as the open Agent envelope.  This API additionally replays the compiler's
    durable proposal/preselection chain and proves the postseal selection was
    requested from those exact bindings.
    """

    terminal = verify_completed_v31_agent_transport(
        store=store, run_id=run_id, cycle_index=cycle_index
    )
    proposal_state = terminal["checkpoint"]["stage_states"]["PROPOSAL"]
    request = store.read_bound_document(proposal_state["request_binding"])
    if request.get("expected_payload_schema_id") != AUTHORING_ENVELOPE_SCHEMA_ID:
        raise V31AgentTransportWorkflowError(
            "V31_COMPLETED_AUTHORING_TRANSPORT_REQUIRED"
        )
    admission_ref = _compilation_ref(cycle_index, "admission")
    if not store.document_exists(relative_ref=admission_ref):
        raise V31AgentTransportWorkflowError(
            "V31_COMPLETED_AUTHORING_COMPILATION_ADMISSION_MISSING"
        )
    admission_binding = store.artifact_binding(
        relative_ref=admission_ref,
        digest_field=AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
    )
    compilation = verify_v31_authoring_compilation_bundle(
        store=store,
        admission_binding=admission_binding,
        expected_run_id=run_id,
        expected_cycle_index=cycle_index,
    )
    packet = compilation["authoring_packet"]
    authority = packet["authority_context"]
    subject = store.read_bound_document(
        authority["experiment_subject_binding"]
    )
    verify_minimal_experiment_contract(subject)
    purpose = packet["authoring_purpose"]
    if (
        (expected_authoring_purpose is not None and purpose != expected_authoring_purpose)
        or subject.get("run_id") != run_id
        or packet.get("run_id") != run_id
        or (
            purpose == "TRANSPORT_QUALIFICATION_ONLY"
            and (
                authority.get("active_authority_binding") is not None
                or authority.get("experiment_start_authorized") is not False
                or packet.get("cycle_source_admission_binding") is not None
            )
        )
    ):
        raise V31AgentTransportWorkflowError(
            "V31_COMPLETED_AUTHORING_SUBJECT_OR_AUTHORITY_MISMATCH"
        )
    selection_state = terminal["checkpoint"]["stage_states"]["SELECTION"]
    selection_request = store.read_bound_document(
        selection_state["request_binding"]
    )
    selection_delivery = store.read_bound_document(
        selection_state["delivery_binding"]
    )
    action_selection = selection_delivery.get("payload")
    try:
        if not isinstance(action_selection, Mapping):
            raise ValueError("V31_ACTION_SELECTION_PAYLOAD_REQUIRED")
        replayed_action_selection = seal_action_selection(
            evaluation=compilation["action_evaluation"],
            selected_candidate_id=action_selection["selected_candidate_id"],
            reason=action_selection["reason"],
            alternative_explanations=action_selection[
                "alternative_explanations"
            ],
            failure_conditions=action_selection["failure_conditions"],
            next_review_at=action_selection["next_review_at"],
            selected_at=action_selection["selected_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31AgentTransportWorkflowError(
            "V31_COMPLETED_AUTHORING_ACTION_SELECTION_INVALID"
        ) from exc
    if (
        selection_request.get("preselection_binding")
        != compilation["admission"]["preselection_binding"]
        or selection_request.get("action_evaluation_binding")
        != compilation["admission"]["action_evaluation_binding"]
        or selection_request.get("proposal_consume_binding")
        != compilation["admission"]["proposal_consume_binding"]
        or selection_delivery.get("payload_schema_id")
        != "theory_paper_v2_v31_action_selection"
        or replayed_action_selection != dict(action_selection)
    ):
        raise V31AgentTransportWorkflowError(
            "V31_COMPLETED_AUTHORING_SELECTION_CROSS_BINDING_INVALID"
        )
    return {
        **dict(terminal),
        "compilation_admission": compilation["admission"],
        "compilation_admission_binding": dict(admission_binding),
        "authoring_packet": packet,
        "authoring_packet_binding": compilation["admission"][
            "authoring_packet_binding"
        ],
        "agent_authoring_envelope": compilation[
            "agent_authoring_envelope"
        ],
        "inputs_receipt": compilation["inputs_receipt"],
        "agent_proposal": compilation["agent_proposal"],
        "action_evaluation": compilation["action_evaluation"],
        "preselection": compilation["preselection"],
        "action_selection": dict(action_selection),
        "compilation_receipt": compilation["compilation_receipt"],
        "compiled_assembly_bundle": compilation["compiled_assembly_bundle"],
        "compiled_assembly_bundle_binding": compilation["admission"][
            "compiled_assembly_bundle_binding"
        ],
        "assembly_inputs": compilation["assembly_inputs"],
        "experiment_subject": dict(subject),
        "authoring_purpose": purpose,
        "active_authority_binding": authority["active_authority_binding"],
        "experiment_start_authorized": authority[
            "experiment_start_authorized"
        ],
        "subject_run_id_matches": True,
        "postseal_selection_consumed": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def run_v31_selection_transport(
    *,
    store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
    preselection_binding: Mapping[str, Any],
    action_evaluation_binding: Mapping[str, Any],
    owner_id: str,
    lease_acquired_at: str,
    lease_expires_at: str,
    stage_times: Mapping[str, str],
    agent_call: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    preselection = store.read_bound_document(preselection_binding)
    action_evaluation = store.read_bound_document(action_evaluation_binding)
    try:
        preselection_digest = verify_v31_cycle_evaluation(preselection)
        evaluation_digest = verify_complete_action_evaluation(action_evaluation)
    except (V31ResearchCycleError, ValueError) as exc:
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_PRESELECTION_NOT_SEALED"
        ) from exc
    if (
        preselection.get("run_id") != run_id
        or preselection.get("cycle_index") != cycle_index
        or preselection_digest != preselection_binding.get("semantic_digest")
        or evaluation_digest != action_evaluation_binding.get("semantic_digest")
        or preselection.get("action_evaluation_digest") != evaluation_digest
    ):
        raise V31AgentTransportWorkflowError(
            "V31_TRANSPORT_PRESELECTION_BINDING_INVALID"
        )
    with store.owner_lease(
        owner_id=owner_id,
        acquired_at=lease_acquired_at,
        expires_at=lease_expires_at,
    ) as lease:
        checkpoint = store.read_checkpoint(relative_ref=_checkpoint_ref(cycle_index))
        _validate_checkpoint(checkpoint, run_id=run_id, cycle_index=cycle_index)
        if checkpoint["status"] == "FAILED_CLOSED":
            raise V31AgentTransportWorkflowError(
                "V31_TRANSPORT_PERMANENTLY_FAILED_CLOSED"
            )
        proposal_state = checkpoint["stage_states"]["PROPOSAL"]
        if proposal_state["status"] != "CONSUMED":
            raise V31AgentTransportWorkflowError(
                "V31_SELECTION_REQUIRES_PROPOSAL_CONSUME"
            )
        proposal_request = store.read_bound_document(
            proposal_state["request_binding"]
        )
        authoring_proposal = (
            proposal_request.get("expected_payload_schema_id")
            == AUTHORING_ENVELOPE_SCHEMA_ID
        )
        if authoring_proposal:
            admission_ref = _compilation_ref(cycle_index, "admission")
            if not store.document_exists(relative_ref=admission_ref):
                raise V31AgentTransportWorkflowError(
                    "V31_SELECTION_BLOCKED_AUTHORING_COMPILER_REQUIRED"
                )
            admission_binding = store.artifact_binding(
                relative_ref=admission_ref,
                digest_field=AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
            )
            compilation = verify_v31_authoring_compilation_bundle(
                store=store,
                admission_binding=admission_binding,
                expected_run_id=run_id,
                expected_cycle_index=cycle_index,
            )
            admission = compilation["admission"]
            if (
                admission["preselection_binding"] != dict(preselection_binding)
                or admission["action_evaluation_binding"]
                != dict(action_evaluation_binding)
            ):
                raise V31AgentTransportWorkflowError(
                    "V31_SELECTION_COMPILATION_BINDING_MISMATCH"
                )
            proposal_documents = compilation["proposal_transport_documents"]
            compiled_proposal_digest = admission["agent_proposal_binding"][
                "semantic_digest"
            ]
        else:
            proposal_inputs = store.read_bound_document(
                proposal_request["inputs_receipt_binding"]
            )
            proposal_documents = _load_stage_documents(
                store=store,
                bindings=proposal_state,
                inputs_receipt=proposal_inputs,
                authoring_packet=None,
                action_evaluation=None,
            )
            compiled_proposal_digest = proposal_documents["delivery"].get(
                "payload_digest"
            )
        proposal_consume = proposal_documents["consume"]
        proposal_delivery = proposal_documents["delivery"]
        if (
            proposal_consume.get("payload_digest")
            != proposal_delivery.get("payload_digest")
            or preselection.get("agent_proposal_digest")
            != compiled_proposal_digest
        ):
            raise V31AgentTransportWorkflowError(
                "V31_SELECTION_PROPOSAL_CONSUME_BINDING_INVALID"
            )
        checkpoint, consume = _run_stage_once(
            store=store,
            lease=lease,
            checkpoint=checkpoint,
            stage="SELECTION",
            source_binding=preselection_binding,
            proposal_consume_binding=proposal_state["consume_binding"],
            preselection_binding=preselection_binding,
            action_evaluation_binding=action_evaluation_binding,
            selectable_candidate_ids=list(
                preselection["selectable_candidate_ids"]
            ),
            times=stage_times,
            agent_call=agent_call,
            inputs_receipt=None,
            authoring_packet=None,
            action_evaluation=action_evaluation,
        )
        if checkpoint["status"] == "READY_FOR_EVIDENCE":
            checkpoint, evidence_binding = _finalize_evidence(
                store=store,
                lease=lease,
                checkpoint=checkpoint,
                completed_at=consume["consumed_at"],
            )
        else:
            evidence_binding = checkpoint["transport_evidence_binding"]
        return {
            "status": checkpoint["status"],
            "consume_receipt": consume,
            "transport_evidence_binding": evidence_binding,
        }


__all__ = [
    "V31_LEGACY_PROPOSAL_TRANSPORT_CLASS",
    "V31AgentTransportStorePort",
    "V31AgentTransportWorkflowError",
    "initialize_v31_agent_transport",
    "parse_v31_manual_worker_payload",
    "render_v31_manual_worker_request",
    "run_v31_authoring_compilation",
    "run_v31_authoring_transport",
    "run_v31_proposal_transport",
    "run_v31_selection_transport",
    "verify_v31_transport_evidence_bundle",
    "verify_completed_v31_agent_transport",
    "verify_completed_v31_authoring_transport",
    "verify_v31_authoring_compilation_bundle",
]
