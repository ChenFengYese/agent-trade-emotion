"""Application workflow for the asynchronous current-Codex file mailbox."""

from __future__ import annotations

from typing import Any, Mapping

from ..domain.contracts.canonical import canonical_digest, self_digest, verify_self_digest
from ..domain.native_agent_transport import (
    NATIVE_AGENT_ID,
    NATIVE_EVIDENCE_LEVEL,
    NativeAgentTransportError,
    build_native_agent_claim,
    build_native_agent_delivery,
    build_native_agent_request,
    build_native_consume_receipt,
    validate_native_agent_claim,
    validate_native_agent_delivery,
    validate_native_agent_request,
)
from .ports import NativeAgentTransportStorePort


class NativeAgentTransportWorkflowError(ValueError):
    """A native transport orchestration or state-machine violation."""


_REQUEST_REFS = {
    "PROPOSAL": "mailbox/requests/proposal.json",
    "DELIBERATION": "mailbox/requests/deliberation.json",
}
_CLAIM_REFS = {
    "PROPOSAL": "mailbox/claims/proposal.json",
    "DELIBERATION": "mailbox/claims/deliberation.json",
}
_DELIVERY_REFS = {
    "PROPOSAL": "mailbox/deliveries/proposal.json",
    "DELIBERATION": "mailbox/deliveries/deliberation.json",
}
_CONSUME_REFS = {
    "PROPOSAL": "transport/receipts/proposal-consumed.json",
    "DELIBERATION": "transport/receipts/deliberation-consumed.json",
}
_SEAL_REFS = {
    ("PROPOSAL", "REQUEST"): "mailbox/seals/proposal-request.json",
    ("PROPOSAL", "CLAIM"): "mailbox/seals/proposal-claim.json",
    ("PROPOSAL", "DELIVERY"): "mailbox/seals/proposal-delivery.json",
    ("DELIBERATION", "REQUEST"): "mailbox/seals/deliberation-request.json",
    ("DELIBERATION", "CLAIM"): "mailbox/seals/deliberation-claim.json",
    ("DELIBERATION", "DELIVERY"): "mailbox/seals/deliberation-delivery.json",
}
_INPUT_DIGEST_FIELDS = {
    "native_codex_transport_proposal_input": "native_proposal_input_digest",
    "native_codex_transport_deliberation_input": "native_deliberation_input_digest",
}
_EXPECTED_WAIT_STATUS = {
    "PROPOSAL": "WAITING_FOR_PROPOSAL",
    "DELIBERATION": "WAITING_FOR_DELIBERATION",
}
_OUTPUT_SCHEMAS = {
    "PROPOSAL": "native_codex_transport_proposal_payload",
    "DELIBERATION": "native_codex_transport_deliberation_payload",
}


def _validate_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    try:
        verify_self_digest(contract, "native_transport_contract_digest")
    except ValueError as exc:
        raise NativeAgentTransportWorkflowError(
            "NATIVE_TRANSPORT_CONTRACT_DIGEST_INVALID"
        ) from exc
    if (
        contract.get("schema_id") != "native_codex_transport_contract"
        or contract.get("schema_version") != "1.0.0"
        or contract.get("agent_id") != NATIVE_AGENT_ID
        or contract.get("evidence_level") != NATIVE_EVIDENCE_LEVEL
        or contract.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or contract.get("chat_history_is_authority") is not False
        or contract.get("api_key_required") is not False
        or contract.get("sub_agents_allowed") is not False
    ):
        raise NativeAgentTransportWorkflowError(
            "NATIVE_TRANSPORT_CONTRACT_INVALID"
        )
    max_output_bytes = contract.get("max_output_bytes")
    if (
        not isinstance(max_output_bytes, int)
        or isinstance(max_output_bytes, bool)
        or max_output_bytes < 1
    ):
        raise NativeAgentTransportWorkflowError(
            "NATIVE_TRANSPORT_OUTPUT_BUDGET_INVALID"
        )
    if contract.get("required_stages") != [
        "PROPOSAL",
        "DELIBERATION",
        "POST_ACCEPT_TAIL",
    ]:
        raise NativeAgentTransportWorkflowError(
            "NATIVE_TRANSPORT_REQUIRED_STAGES_INVALID"
        )
    return dict(contract)


def _manifest(
    *,
    run_id: str,
    created_at: str,
    contract_binding: Mapping[str, Any],
    implementation_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    if not run_id or not created_at or not implementation_bindings:
        raise NativeAgentTransportWorkflowError("NATIVE_MANIFEST_INPUT_INVALID")
    return self_digest(
        {
            "schema_id": "native_codex_transport_manifest",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": 1,
            "created_at": created_at,
            "contract_binding": dict(contract_binding),
            "implementation_bindings": dict(implementation_bindings),
            "agent_id": NATIVE_AGENT_ID,
            "evidence_level": NATIVE_EVIDENCE_LEVEL,
            "service_model_attested": False,
            "exact_token_budget_attested": False,
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "native_transport_manifest_digest",
    )


def initialize_native_transport_run(
    *,
    store: NativeAgentTransportStorePort,
    run_id: str,
    created_at: str,
    contract: Mapping[str, Any],
    implementation_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    validated_contract = _validate_contract(contract)
    contract_binding = store.write_document(
        relative_ref="frozen/native-transport-contract.json",
        document=validated_contract,
        digest_field="native_transport_contract_digest",
    )
    manifest = _manifest(
        run_id=run_id,
        created_at=created_at,
        contract_binding=contract_binding,
        implementation_bindings=implementation_bindings,
    )
    store.write_document(
        relative_ref="manifest.json",
        document=manifest,
        digest_field="native_transport_manifest_digest",
    )
    checkpoint = store.initialize_checkpoint(run_id=run_id, created_at=created_at)
    return {
        "status": checkpoint["status"],
        "run_id": run_id,
        "manifest_digest": manifest["native_transport_manifest_digest"],
        "checkpoint_digest": checkpoint["native_transport_checkpoint_digest"],
        "evidence_level": NATIVE_EVIDENCE_LEVEL,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
    }


def _load_manifest(
    *, store: NativeAgentTransportStorePort, run_id: str
) -> Mapping[str, Any]:
    manifest = store.read_document(
        relative_ref="manifest.json",
        digest_field="native_transport_manifest_digest",
    )
    if (
        manifest.get("schema_id") != "native_codex_transport_manifest"
        or manifest.get("run_id") != run_id
        or manifest.get("agent_id") != NATIVE_AGENT_ID
        or manifest.get("evidence_level") != NATIVE_EVIDENCE_LEVEL
        or manifest.get("chat_history_is_authority") is not False
        or manifest.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or manifest.get("executable") is not False
    ):
        raise NativeAgentTransportWorkflowError("NATIVE_MANIFEST_INVALID")
    return manifest


def _load_contract(
    *, store: NativeAgentTransportStorePort, manifest: Mapping[str, Any]
) -> Mapping[str, Any]:
    binding = manifest.get("contract_binding")
    if not isinstance(binding, Mapping):
        raise NativeAgentTransportWorkflowError(
            "NATIVE_MANIFEST_CONTRACT_BINDING_INVALID"
        )
    contract = store.read_document(
        relative_ref=str(binding.get("relative_ref")),
        digest_field="native_transport_contract_digest",
        expected_semantic_digest=str(binding.get("semantic_digest")),
    )
    physical = store.artifact_binding(
        relative_ref=str(binding.get("relative_ref")),
        digest_field="native_transport_contract_digest",
        expected_semantic_digest=str(binding.get("semantic_digest")),
    )
    if physical.get("physical_sha256") != binding.get("physical_sha256"):
        raise NativeAgentTransportWorkflowError(
            "NATIVE_MANIFEST_CONTRACT_PHYSICAL_DRIFT"
        )
    return _validate_contract(contract)


def _transition(
    *,
    store: NativeAgentTransportStorePort,
    checkpoint: Mapping[str, Any],
    updated_at: str,
    status: str,
    active_stage: str | None,
    active_request_digest: str | None,
    last_consume_receipt_digest: str | None = None,
    accepted_state_digest: str | None = None,
    completion_receipt_digest: str | None = None,
) -> Mapping[str, Any]:
    candidate = dict(checkpoint)
    candidate.update(
        {
            "revision": int(checkpoint["revision"]) + 1,
            "status": status,
            "active_stage": active_stage,
            "active_request_digest": active_request_digest,
            "last_consume_receipt_digest": (
                last_consume_receipt_digest
                if last_consume_receipt_digest is not None
                else checkpoint.get("last_consume_receipt_digest")
            ),
            "accepted_state_digest": (
                accepted_state_digest
                if accepted_state_digest is not None
                else checkpoint.get("accepted_state_digest")
            ),
            "completion_receipt_digest": (
                completion_receipt_digest
                if completion_receipt_digest is not None
                else checkpoint.get("completion_receipt_digest")
            ),
            "updated_at": updated_at,
        }
    )
    return store.replace_checkpoint(
        run_id=str(checkpoint["run_id"]),
        expected_checkpoint_digest=str(
            checkpoint["native_transport_checkpoint_digest"]
        ),
        checkpoint=candidate,
    )


def _seal_artifact_binding(
    *,
    store: NativeAgentTransportStorePort,
    stage: str,
    artifact_kind: str,
    binding: Mapping[str, Any],
    request_digest: str,
) -> Mapping[str, Any]:
    seal = self_digest(
        {
            "schema_id": "native_codex_mailbox_artifact_seal",
            "schema_version": "1.0.0",
            "stage": stage,
            "artifact_kind": artifact_kind,
            "request_digest": request_digest,
            "artifact_binding": dict(binding),
        },
        "native_mailbox_artifact_seal_digest",
    )
    store.write_document(
        relative_ref=_SEAL_REFS[(stage, artifact_kind)],
        document=seal,
        digest_field="native_mailbox_artifact_seal_digest",
    )
    return seal


def _verify_artifact_seal(
    *,
    store: NativeAgentTransportStorePort,
    stage: str,
    artifact_kind: str,
    binding: Mapping[str, Any],
    request_digest: str,
) -> None:
    seal = store.read_document(
        relative_ref=_SEAL_REFS[(stage, artifact_kind)],
        digest_field="native_mailbox_artifact_seal_digest",
    )
    if (
        seal.get("stage") != stage
        or seal.get("artifact_kind") != artifact_kind
        or seal.get("request_digest") != request_digest
        or seal.get("artifact_binding") != dict(binding)
    ):
        raise NativeAgentTransportWorkflowError(
            "NATIVE_MAILBOX_PHYSICAL_BINDING_DRIFT"
        )


def _request_input(
    *,
    store: NativeAgentTransportStorePort,
    run_id: str,
    stage: str,
    now: str,
    contract: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any] | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, str]]:
    if stage == "PROPOSAL":
        document = self_digest(
            {
                "schema_id": "native_codex_transport_proposal_input",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": 1,
                "created_at": now,
                "purpose": "VERIFY_NATIVE_CODEX_DURABLE_TRANSPORT_ONLY",
                "facts": [
                    "The controller sealed this input before Codex authors output.",
                    "The experiment is synthetic and has no market or execution authority.",
                    "A later controller process must consume the durable delivery.",
                ],
                "unknowns": [
                    "The service model identity is not machine attested locally.",
                    "The exact token budget is not machine attested locally.",
                ],
                "required_public_analysis_fields": [
                    "facts",
                    "unknowns",
                    "hypothesis",
                    "expectation_update",
                    "falsifier",
                    "next_observation",
                ],
                "private_chain_of_thought_requested": False,
                "chat_history_is_authority": False,
            },
            "native_proposal_input_digest",
        )
        digest_field = "native_proposal_input_digest"
        relative_ref = "transport/inputs/proposal-input.json"
        input_schema_id = "native_codex_transport_proposal_input"
    else:
        if proposal_delivery is None:
            raise NativeAgentTransportWorkflowError(
                "NATIVE_DELIBERATION_PROPOSAL_REQUIRED"
            )
        evaluation = self_digest(
            {
                "schema_id": "native_codex_transport_deterministic_evaluation",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": 1,
                "proposal_payload_digest": proposal_delivery["payload_digest"],
                "candidate_actions": ["WAIT", "OBSERVE"],
                "financial_effect": "NONE_SYNTHETIC_TRANSPORT_ONLY",
                "both_candidates_feasible": True,
                "selection_owner": NATIVE_AGENT_ID,
            },
            "native_transport_evaluation_digest",
        )
        evaluation_binding = store.write_document(
            relative_ref="transport/evaluation.json",
            document=evaluation,
            digest_field="native_transport_evaluation_digest",
        )
        document = self_digest(
            {
                "schema_id": "native_codex_transport_deliberation_input",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": 1,
                "created_at": now,
                "proposal_payload_digest": proposal_delivery["payload_digest"],
                "evaluation_binding": dict(evaluation_binding),
                "candidate_actions": ["WAIT", "OBSERVE"],
                "required_fields": [
                    "selected_action",
                    "reason",
                    "opportunity_cost",
                    "next_review_condition",
                ],
                "private_chain_of_thought_requested": False,
                "chat_history_is_authority": False,
            },
            "native_deliberation_input_digest",
        )
        digest_field = "native_deliberation_input_digest"
        relative_ref = "transport/inputs/deliberation-input.json"
        input_schema_id = "native_codex_transport_deliberation_input"
    binding = store.write_document(
        relative_ref=relative_ref,
        document=document,
        digest_field=digest_field,
    )
    request = build_native_agent_request(
        run_id=run_id,
        cycle_index=1,
        stage=stage,
        created_at=now,
        input_binding=binding,
        input_schema_id=input_schema_id,
        expected_output_schema_id=_OUTPUT_SCHEMAS[stage],
        max_output_bytes=int(contract["max_output_bytes"]),
    )
    request_binding = store.write_document(
        relative_ref=_REQUEST_REFS[stage],
        document=request,
        digest_field="native_agent_request_digest",
    )
    _seal_artifact_binding(
        store=store,
        stage=stage,
        artifact_kind="REQUEST",
        binding=request_binding,
        request_digest=request["native_agent_request_digest"],
    )
    return request, request_binding


def _read_transport_stage(
    *, store: NativeAgentTransportStorePort, stage: str
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, str],
    Mapping[str, str],
    Mapping[str, str],
]:
    request = store.read_document(
        relative_ref=_REQUEST_REFS[stage],
        digest_field="native_agent_request_digest",
    )
    claim = store.read_document(
        relative_ref=_CLAIM_REFS[stage],
        digest_field="native_agent_claim_digest",
    )
    delivery = store.read_document(
        relative_ref=_DELIVERY_REFS[stage],
        digest_field="native_agent_delivery_digest",
    )
    validate_native_agent_request(request)
    validate_native_agent_claim(request=request, claim=claim)
    validate_native_agent_delivery(
        request=request, claim=claim, delivery=delivery
    )
    input_digest_field = _INPUT_DIGEST_FIELDS.get(str(request["input_schema_id"]))
    if input_digest_field is None:
        raise NativeAgentTransportWorkflowError(
            "NATIVE_INPUT_SCHEMA_BINDING_UNSUPPORTED"
        )
    input_binding = store.artifact_binding(
        relative_ref=str(request["input_binding"]["relative_ref"]),
        digest_field=input_digest_field,
        expected_semantic_digest=str(
            request["input_binding"]["semantic_digest"]
        ),
    )
    if input_binding != request["input_binding"]:
        raise NativeAgentTransportWorkflowError(
            "NATIVE_INPUT_PHYSICAL_BINDING_DRIFT"
        )
    request_binding = store.artifact_binding(
        relative_ref=_REQUEST_REFS[stage],
        digest_field="native_agent_request_digest",
    )
    claim_binding = store.artifact_binding(
        relative_ref=_CLAIM_REFS[stage],
        digest_field="native_agent_claim_digest",
    )
    delivery_binding = store.artifact_binding(
        relative_ref=_DELIVERY_REFS[stage],
        digest_field="native_agent_delivery_digest",
    )
    _verify_artifact_seal(
        store=store,
        stage=stage,
        artifact_kind="REQUEST",
        binding=request_binding,
        request_digest=str(request["native_agent_request_digest"]),
    )
    _verify_artifact_seal(
        store=store,
        stage=stage,
        artifact_kind="CLAIM",
        binding=claim_binding,
        request_digest=str(request["native_agent_request_digest"]),
    )
    _verify_artifact_seal(
        store=store,
        stage=stage,
        artifact_kind="DELIVERY",
        binding=delivery_binding,
        request_digest=str(request["native_agent_request_digest"]),
    )
    return (
        request,
        claim,
        delivery,
        request_binding,
        claim_binding,
        delivery_binding,
    )


def _consume_stage(
    *,
    store: NativeAgentTransportStorePort,
    stage: str,
    now: str,
    next_status: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    (
        request,
        claim,
        delivery,
        request_binding,
        claim_binding,
        delivery_binding,
    ) = _read_transport_stage(store=store, stage=stage)
    receipt = build_native_consume_receipt(
        request=request,
        request_binding=request_binding,
        claim=claim,
        claim_binding=claim_binding,
        delivery=delivery,
        delivery_binding=delivery_binding,
        consumed_at=now,
        next_status=next_status,
    )
    store.write_document(
        relative_ref=_CONSUME_REFS[stage],
        document=receipt,
        digest_field="native_transport_consume_receipt_digest",
    )
    return delivery, receipt


def advance_native_transport(
    *, store: NativeAgentTransportStorePort, run_id: str, now: str
) -> dict[str, Any]:
    manifest = _load_manifest(store=store, run_id=run_id)
    contract = _load_contract(store=store, manifest=manifest)
    checkpoint = store.load_checkpoint(run_id=run_id)
    status = checkpoint["status"]
    if status == "READY_FOR_PROPOSAL":
        request, binding = _request_input(
            store=store,
            run_id=run_id,
            stage="PROPOSAL",
            now=now,
            contract=contract,
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="WAITING_FOR_PROPOSAL",
            active_stage="PROPOSAL",
            active_request_digest=request["native_agent_request_digest"],
        )
        return {
            "status": checkpoint["status"],
            "next_action": "CURRENT_CODEX_CLAIM_AND_SUBMIT_PROPOSAL",
            "request_binding": binding,
            "checkpoint_digest": checkpoint[
                "native_transport_checkpoint_digest"
            ],
        }
    if status == "WAITING_FOR_PROPOSAL":
        if not store.document_exists(relative_ref=_DELIVERY_REFS["PROPOSAL"]):
            return native_transport_status(store=store, run_id=run_id)
        proposal_delivery, consume = _consume_stage(
            store=store,
            stage="PROPOSAL",
            now=now,
            next_status="WAITING_FOR_DELIBERATION",
        )
        request, binding = _request_input(
            store=store,
            run_id=run_id,
            stage="DELIBERATION",
            now=now,
            contract=contract,
            proposal_delivery=proposal_delivery,
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="WAITING_FOR_DELIBERATION",
            active_stage="DELIBERATION",
            active_request_digest=request["native_agent_request_digest"],
            last_consume_receipt_digest=consume[
                "native_transport_consume_receipt_digest"
            ],
        )
        return {
            "status": checkpoint["status"],
            "next_action": "CURRENT_CODEX_CLAIM_AND_SUBMIT_DELIBERATION",
            "request_binding": binding,
            "checkpoint_digest": checkpoint[
                "native_transport_checkpoint_digest"
            ],
        }
    if status == "WAITING_FOR_DELIBERATION":
        if not store.document_exists(
            relative_ref=_DELIVERY_REFS["DELIBERATION"]
        ):
            return native_transport_status(store=store, run_id=run_id)
        deliberation_delivery, consume = _consume_stage(
            store=store,
            stage="DELIBERATION",
            now=now,
            next_status="POST_ACCEPT_PENDING",
        )
        evaluation = store.read_document(
            relative_ref="transport/evaluation.json",
            digest_field="native_transport_evaluation_digest",
        )
        payload = deliberation_delivery["payload"]
        if (
            payload.get("evaluation_digest")
            != evaluation["native_transport_evaluation_digest"]
            or payload.get("selected_action")
            not in evaluation["candidate_actions"]
        ):
            raise NativeAgentTransportWorkflowError(
                "NATIVE_DELIBERATION_EVALUATION_BINDING_MISMATCH"
            )
        proposal_consume = store.read_document(
            relative_ref=_CONSUME_REFS["PROPOSAL"],
            digest_field="native_transport_consume_receipt_digest",
        )
        preaccept = self_digest(
            {
                "schema_id": "native_codex_transport_preaccept_receipt",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": 1,
                "manifest_digest": manifest["native_transport_manifest_digest"],
                "proposal_consume_receipt_digest": proposal_consume[
                    "native_transport_consume_receipt_digest"
                ],
                "deliberation_consume_receipt_digest": consume[
                    "native_transport_consume_receipt_digest"
                ],
                "evaluation_digest": evaluation[
                    "native_transport_evaluation_digest"
                ],
                "selected_action": payload["selected_action"],
                "all_transport_bindings_verified": True,
                "agent_reinvocation_after_accept_forbidden": True,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
            },
            "native_transport_preaccept_receipt_digest",
        )
        preaccept_binding = store.write_document(
            relative_ref="transport/preaccept-receipt.json",
            document=preaccept,
            digest_field="native_transport_preaccept_receipt_digest",
        )
        accepted_state = self_digest(
            {
                "schema_id": "native_codex_transport_accepted_state",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": 1,
                "accepted_at": now,
                "manifest_digest": manifest["native_transport_manifest_digest"],
                "preaccept_binding": dict(preaccept_binding),
                "selected_action": payload["selected_action"],
                "transport_only": True,
                "market_data_accessed": False,
                "model_api_called": False,
                "agent_id": NATIVE_AGENT_ID,
                "evidence_level": NATIVE_EVIDENCE_LEVEL,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "native_transport_accepted_state_digest",
        )
        store.write_document(
            relative_ref="states/state-0001.json",
            document=accepted_state,
            digest_field="native_transport_accepted_state_digest",
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="POST_ACCEPT_PENDING",
            active_stage=None,
            active_request_digest=None,
            last_consume_receipt_digest=consume[
                "native_transport_consume_receipt_digest"
            ],
            accepted_state_digest=accepted_state[
                "native_transport_accepted_state_digest"
            ],
        )
        return {
            "status": checkpoint["status"],
            "next_action": "NEW_CONTROLLER_PROCESS_FINALIZE_DETERMINISTIC_TAIL",
            "accepted_state_digest": accepted_state[
                "native_transport_accepted_state_digest"
            ],
            "checkpoint_digest": checkpoint[
                "native_transport_checkpoint_digest"
            ],
        }
    if status == "POST_ACCEPT_PENDING":
        accepted_state = store.read_document(
            relative_ref="states/state-0001.json",
            digest_field="native_transport_accepted_state_digest",
            expected_semantic_digest=str(checkpoint["accepted_state_digest"]),
        )
        completion = self_digest(
            {
                "schema_id": "native_codex_transport_completion_receipt",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": 1,
                "completed_at": now,
                "accepted_state_digest": accepted_state[
                    "native_transport_accepted_state_digest"
                ],
                "proposal_reinvocation_count_after_consume": 0,
                "deliberation_reinvocation_count_after_consume": 0,
                "postaccept_agent_invocation_count": 0,
                "durable_boundaries_verified": [
                    "PROPOSAL",
                    "DELIBERATION",
                    "POST_ACCEPT_TAIL",
                ],
                "evidence_level": NATIVE_EVIDENCE_LEVEL,
                "market_data_accessed": False,
                "model_api_called": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
            },
            "native_transport_completion_receipt_digest",
        )
        store.write_document(
            relative_ref="completion/receipt.json",
            document=completion,
            digest_field="native_transport_completion_receipt_digest",
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="COMPLETED",
            active_stage=None,
            active_request_digest=None,
            completion_receipt_digest=completion[
                "native_transport_completion_receipt_digest"
            ],
        )
        return {
            "status": checkpoint["status"],
            "next_action": "NOOP_PHASE_B_COMPLETE",
            "completion_receipt_digest": completion[
                "native_transport_completion_receipt_digest"
            ],
            "checkpoint_digest": checkpoint[
                "native_transport_checkpoint_digest"
            ],
            "evidence_level": NATIVE_EVIDENCE_LEVEL,
        }
    if status == "COMPLETED":
        return native_transport_status(store=store, run_id=run_id)
    if status == "FAILED_CLOSED":
        return native_transport_status(store=store, run_id=run_id)
    raise NativeAgentTransportWorkflowError("NATIVE_STAGE_TRANSITION_INVALID")


def claim_native_request(
    *,
    store: NativeAgentTransportStorePort,
    run_id: str,
    stage: str,
    claimed_at: str,
) -> dict[str, Any]:
    checkpoint = store.load_checkpoint(run_id=run_id)
    if (
        checkpoint.get("status") != _EXPECTED_WAIT_STATUS.get(stage)
        or checkpoint.get("active_stage") != stage
    ):
        raise NativeAgentTransportWorkflowError("NATIVE_CLAIM_STAGE_INVALID")
    request = store.read_document(
        relative_ref=_REQUEST_REFS[stage],
        digest_field="native_agent_request_digest",
        expected_semantic_digest=str(checkpoint["active_request_digest"]),
    )
    if store.document_exists(relative_ref=_CLAIM_REFS[stage]):
        existing = store.read_document(
            relative_ref=_CLAIM_REFS[stage],
            digest_field="native_agent_claim_digest",
        )
        validate_native_agent_claim(request=request, claim=existing)
        existing_binding = store.artifact_binding(
            relative_ref=_CLAIM_REFS[stage],
            digest_field="native_agent_claim_digest",
            expected_semantic_digest=str(
                existing["native_agent_claim_digest"]
            ),
        )
        if store.document_exists(relative_ref=_SEAL_REFS[(stage, "CLAIM")]):
            _verify_artifact_seal(
                store=store,
                stage=stage,
                artifact_kind="CLAIM",
                binding=existing_binding,
                request_digest=str(request["native_agent_request_digest"]),
            )
        else:
            _seal_artifact_binding(
                store=store,
                stage=stage,
                artifact_kind="CLAIM",
                binding=existing_binding,
                request_digest=str(request["native_agent_request_digest"]),
            )
        return dict(existing)
    claim_id = canonical_digest(
        {
            "request_digest": request["native_agent_request_digest"],
            "claimant_id": NATIVE_AGENT_ID,
        }
    )
    claim = build_native_agent_claim(
        request=request, claim_id=claim_id, claimed_at=claimed_at
    )
    store.write_document(
        relative_ref=_CLAIM_REFS[stage],
        document=claim,
        digest_field="native_agent_claim_digest",
    )
    claim_binding = store.artifact_binding(
        relative_ref=_CLAIM_REFS[stage],
        digest_field="native_agent_claim_digest",
        expected_semantic_digest=str(claim["native_agent_claim_digest"]),
    )
    _seal_artifact_binding(
        store=store,
        stage=stage,
        artifact_kind="CLAIM",
        binding=claim_binding,
        request_digest=str(request["native_agent_request_digest"]),
    )
    return claim


def submit_native_delivery(
    *,
    store: NativeAgentTransportStorePort,
    run_id: str,
    stage: str,
    payload: Mapping[str, Any],
    delivered_at: str,
) -> dict[str, Any]:
    checkpoint = store.load_checkpoint(run_id=run_id)
    if (
        checkpoint.get("status") != _EXPECTED_WAIT_STATUS.get(stage)
        or checkpoint.get("active_stage") != stage
    ):
        raise NativeAgentTransportWorkflowError("NATIVE_SUBMIT_STAGE_INVALID")
    request = store.read_document(
        relative_ref=_REQUEST_REFS[stage],
        digest_field="native_agent_request_digest",
        expected_semantic_digest=str(checkpoint["active_request_digest"]),
    )
    claim = store.read_document(
        relative_ref=_CLAIM_REFS[stage],
        digest_field="native_agent_claim_digest",
    )
    delivery = build_native_agent_delivery(
        request=request,
        claim=claim,
        payload=payload,
        delivered_at=delivered_at,
    )
    if store.document_exists(relative_ref=_DELIVERY_REFS[stage]):
        existing = store.read_document(
            relative_ref=_DELIVERY_REFS[stage],
            digest_field="native_agent_delivery_digest",
        )
        validate_native_agent_delivery(
            request=request, claim=claim, delivery=existing
        )
        if existing["payload_digest"] != delivery["payload_digest"]:
            raise NativeAgentTransportWorkflowError(
                "NATIVE_DELIVERY_WRITE_ONCE_CONFLICT"
            )
        existing_binding = store.artifact_binding(
            relative_ref=_DELIVERY_REFS[stage],
            digest_field="native_agent_delivery_digest",
            expected_semantic_digest=str(
                existing["native_agent_delivery_digest"]
            ),
        )
        if store.document_exists(
            relative_ref=_SEAL_REFS[(stage, "DELIVERY")]
        ):
            _verify_artifact_seal(
                store=store,
                stage=stage,
                artifact_kind="DELIVERY",
                binding=existing_binding,
                request_digest=str(request["native_agent_request_digest"]),
            )
        else:
            _seal_artifact_binding(
                store=store,
                stage=stage,
                artifact_kind="DELIVERY",
                binding=existing_binding,
                request_digest=str(request["native_agent_request_digest"]),
            )
        return dict(existing)
    store.write_document(
        relative_ref=_DELIVERY_REFS[stage],
        document=delivery,
        digest_field="native_agent_delivery_digest",
    )
    delivery_binding = store.artifact_binding(
        relative_ref=_DELIVERY_REFS[stage],
        digest_field="native_agent_delivery_digest",
        expected_semantic_digest=str(delivery["native_agent_delivery_digest"]),
    )
    _seal_artifact_binding(
        store=store,
        stage=stage,
        artifact_kind="DELIVERY",
        binding=delivery_binding,
        request_digest=str(request["native_agent_request_digest"]),
    )
    return delivery


def record_native_transport_failure(
    *,
    store: NativeAgentTransportStorePort,
    run_id: str,
    failed_at: str,
    reason_code: str,
) -> dict[str, Any]:
    checkpoint = store.load_checkpoint(run_id=run_id)
    if checkpoint["status"] == "COMPLETED":
        raise NativeAgentTransportWorkflowError(
            "NATIVE_COMPLETED_RUN_FAILURE_FORBIDDEN"
        )
    failure = self_digest(
        {
            "schema_id": "native_codex_transport_failure_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": 1,
            "failed_at": failed_at,
            "failed_status": checkpoint["status"],
            "active_stage": checkpoint.get("active_stage"),
            "reason_code": reason_code,
            "resume_allowed": False,
            "accepted_state_exists": checkpoint.get("accepted_state_digest")
            is not None,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_transport_failure_receipt_digest",
    )
    store.write_document(
        relative_ref="failures/terminal-failure.json",
        document=failure,
        digest_field="native_transport_failure_receipt_digest",
    )
    _transition(
        store=store,
        checkpoint=checkpoint,
        updated_at=failed_at,
        status="FAILED_CLOSED",
        active_stage=None,
        active_request_digest=None,
    )
    return failure


def native_transport_status(
    *, store: NativeAgentTransportStorePort, run_id: str
) -> dict[str, Any]:
    manifest = _load_manifest(store=store, run_id=run_id)
    checkpoint = store.load_checkpoint(run_id=run_id)
    stage = checkpoint.get("active_stage")
    request_ref = _REQUEST_REFS.get(str(stage))
    claim_ref = _CLAIM_REFS.get(str(stage))
    delivery_ref = _DELIVERY_REFS.get(str(stage))
    if checkpoint["status"] == "WAITING_FOR_PROPOSAL":
        next_action = "CURRENT_CODEX_CLAIM_AND_SUBMIT_PROPOSAL"
    elif checkpoint["status"] == "WAITING_FOR_DELIBERATION":
        next_action = "CURRENT_CODEX_CLAIM_AND_SUBMIT_DELIBERATION"
    elif checkpoint["status"] == "POST_ACCEPT_PENDING":
        next_action = "NEW_CONTROLLER_PROCESS_FINALIZE_DETERMINISTIC_TAIL"
    elif checkpoint["status"] == "COMPLETED":
        next_action = "NOOP_PHASE_B_COMPLETE"
    elif checkpoint["status"] == "FAILED_CLOSED":
        next_action = "NOOP_PERMANENT_FAILURE"
    else:
        next_action = "CONTROLLER_ADVANCE"
    return {
        "schema_id": "native_codex_transport_status",
        "run_id": run_id,
        "status": checkpoint["status"],
        "revision": checkpoint["revision"],
        "active_stage": stage,
        "request_ref": request_ref,
        "request_exists": bool(
            request_ref and store.document_exists(relative_ref=request_ref)
        ),
        "claim_exists": bool(
            claim_ref and store.document_exists(relative_ref=claim_ref)
        ),
        "delivery_exists": bool(
            delivery_ref and store.document_exists(relative_ref=delivery_ref)
        ),
        "accepted_state_digest": checkpoint.get("accepted_state_digest"),
        "completion_receipt_digest": checkpoint.get(
            "completion_receipt_digest"
        ),
        "checkpoint_digest": checkpoint[
            "native_transport_checkpoint_digest"
        ],
        "manifest_digest": manifest["native_transport_manifest_digest"],
        "next_action": next_action,
        "agent_id": NATIVE_AGENT_ID,
        "evidence_level": NATIVE_EVIDENCE_LEVEL,
        "chat_history_is_authority": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
    }


__all__ = [
    "NativeAgentTransportWorkflowError",
    "advance_native_transport",
    "claim_native_request",
    "initialize_native_transport_run",
    "native_transport_status",
    "record_native_transport_failure",
    "submit_native_delivery",
]
