from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.behavior_planning import (
    seal_action_selection,
)
from trade_system.theory_paper_v2.application.v31_external_qualification import (
    build_q6_receipt_from_durable_qualification,
    build_q7_receipt_from_completed_authoring_transport,
)
from trade_system.theory_paper_v2.application.v31_agent_transport import (
    initialize_v31_agent_transport,
    run_v31_authoring_compilation,
    run_v31_authoring_transport,
    run_v31_selection_transport,
    verify_v31_authoring_compilation_bundle,
)
from trade_system.theory_paper_v2.application.v31_source_qualification import (
    execute_v31_source_qualification,
    initialize_v31_source_qualification,
)
from trade_system.theory_paper_v2.domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_active_authority,
    validate_v31_experiment_authorization,
    validate_v31_frozen_experiment_manifest,
    validate_v31_qualification_receipt,
    validate_v31_theory_approval,
)
from trade_system.theory_paper_v2.domain.governance.v31_experiment_qualification import (
    TYPED_QUALIFICATION_GATE_IDS,
    build_typed_qualification_receipt,
    required_gate_evidence_paths,
)
from trade_system.theory_paper_v2.domain.governance.v31_external_qualification import (
    EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID,
    required_external_gate_evidence_paths,
)
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    build_minimal_experiment_contract,
)
from trade_system.theory_paper_v2.domain.v31_source_qualification import (
    APPROVED_V31_THEORY_SHA256,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    V31_CURRENT_RESEARCH_AUTHORITY_PATH,
    load_v31_active_authorization_chain,
)
from trade_system.theory_paper_v2.infrastructure.v31_market_adapter import (
    adapt_native_public_snapshot,
)
from trade_system.theory_paper_v2.infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_semantic_compiler import (
    LocalV31SemanticCompiler,
)
from tests.test_theory_paper_v2_v31_source_qualification import (
    _LeaseAssertingCollector,
)
from tests.test_theory_paper_v2_v31_semantic_compiler import (
    _envelope as _q7_envelope,
    _materials as _q7_materials,
)


_RUN_ID = "v31-prospective-btcusdt-20260806t160000z"
_THEORY_PATH = "theory/history/RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md"
_APPROVAL_PATH = "config/theory-approval.json"
_MANIFEST_PATH = "config/frozen-manifest.json"
_AUTHORIZATION_PATH = "config/experiment-authorization.json"
_EXPERIMENT_CONTRACT_PATH = "config/experiment-contract.json"
_PREDECESSOR_PATH = "config/theory_paper_v2.current_research_authority.v1.json"
_EXECUTION_FALSE = {
    "account_access": False,
    "paper_trading": False,
    "live_trading": False,
    "order_submission": False,
    "credential_access": False,
    "funds_access": False,
}
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_Q6_QUALIFICATION_ID = "v31-source-qualification-semantic-compiler-fixture"
_Q6_ROOT_REF = (
    "agent-cluster/experiments/v31-qualifications/"
    f"{_Q6_QUALIFICATION_ID}"
)
_Q7_ROOT_REF = (
    "agent-cluster/experiments/v31-qualifications/"
    "q7-open-analysis-compiler-selection-unit"
)


def _write_bytes(project: Path, relative_path: str, payload: bytes) -> str:
    path = project / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _write_json(project: Path, relative_path: str, value: Mapping[str, Any]) -> str:
    return _write_bytes(project, relative_path, canonical_bytes(value) + b"\n")


def _binding(
    *,
    path: str,
    document: Mapping[str, Any],
    digest_field: str,
    physical_sha256: str,
) -> dict[str, Any]:
    return {
        "path": path,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": physical_sha256,
    }


def _create_no_network_q6_fixture(project: Path) -> None:
    """Create fresh Q6 evidence without a socket or a research-run start."""

    store = LocalV31SourceQualificationStore(project / _Q6_ROOT_REF)
    initialize_v31_source_qualification(
        store=store,
        qualification_id=_Q6_QUALIFICATION_ID,
        created_at="2026-08-06T11:59:59Z",
        theory_sha256=APPROVED_V31_THEORY_SHA256,
    )
    result = execute_v31_source_qualification(
        store=store,
        qualification_id=_Q6_QUALIFICATION_ID,
        collector=_LeaseAssertingCollector(store=store),
        adapter=adapt_native_public_snapshot,
        clock=lambda: "2026-08-06T12:01:00Z",
    )
    if (
        result.get("status") != "SEALED"
        or result.get("qualification_only") is not True
        or result.get("experiment_started") is not False
    ):
        raise AssertionError("fresh no-network Q6 fixture did not seal safely")


def _create_no_network_q7_fixture(
    project: Path,
    *,
    experiment_contract: Mapping[str, Any],
    theory_approval: Mapping[str, Any],
) -> None:
    """Complete the real open-analysis/compiler/postseal-selection Q7 path."""

    store = LocalV31AgentTransportStore(project / _Q7_ROOT_REF)
    packet, dataset, mark_id = _q7_materials(
        store,
        qualification_root=project / _Q6_ROOT_REF,
        run_id=_RUN_ID,
        experiment_contract=experiment_contract,
        theory_approval=theory_approval,
    )
    with store.owner_lease(
        owner_id="q7-packet-writer",
        acquired_at="2026-08-06T12:01:30Z",
        expires_at="2026-08-06T12:01:59Z",
    ) as lease:
        packet_binding = store.write_document(
            lease=lease,
            relative_ref="cycles/0001/proposal-authoring-packet.json",
            document=packet,
            digest_field="authoring_packet_digest",
        )
    initialize_v31_agent_transport(
        store=store,
        run_id=_RUN_ID,
        cycle_index=1,
        created_at="2026-08-06T12:02:00Z",
        owner_id="q7-initializer",
        lease_expires_at="2026-08-06T12:02:30Z",
    )
    run_v31_authoring_transport(
        store=store,
        run_id=_RUN_ID,
        cycle_index=1,
        authoring_packet_binding=packet_binding,
        owner_id="q7-authoring-owner",
        lease_acquired_at="2026-08-06T12:03:00Z",
        lease_expires_at="2026-08-06T12:09:59Z",
        stage_times={
            "reserved_at": "2026-08-06T12:03:01Z",
            "requested_at": "2026-08-06T12:03:02Z",
            "claimed_at": "2026-08-06T12:03:03Z",
            "delivered_at": "2026-08-06T12:03:04Z",
            "consumed_at": "2026-08-06T12:03:05Z",
        },
        agent_call=lambda _: _q7_envelope(packet, dataset, mark_id),
    )
    compiled = run_v31_authoring_compilation(
        store=store,
        run_id=_RUN_ID,
        cycle_index=1,
        authoring_packet_binding=packet_binding,
        compiled_at="2026-08-06T12:10:00Z",
        compiler=LocalV31SemanticCompiler(store=store),
        owner_id="q7-compiler-owner",
        lease_acquired_at="2026-08-06T12:10:00Z",
        lease_expires_at="2026-08-06T12:10:30Z",
    )
    replay = verify_v31_authoring_compilation_bundle(
        store=store,
        admission_binding=compiled["compilation_admission_binding"],
        expected_run_id=_RUN_ID,
        expected_cycle_index=1,
    )
    evaluation = replay["action_evaluation"]
    wait = next(
        row for row in evaluation["candidates"] if row["action"] == "WAIT"
    )

    def select_wait(_: Mapping[str, Any]) -> Mapping[str, Any]:
        other_ids = {
            row["candidate_id"] for row in evaluation["candidates"]
        } - {wait["candidate_id"]}
        return seal_action_selection(
            evaluation=evaluation,
            selected_candidate_id=wait["candidate_id"],
            reason="Uncalibrated uncertainty keeps WAIT reversible.",
            alternative_explanations={
                candidate_id: "The competing registered path remains possible."
                for candidate_id in other_ids
            },
            failure_conditions=("The registered WAIT premise changes.",),
            next_review_at=wait["next_review_at"],
            selected_at="2026-08-06T12:11:02Z",
        )

    completed = run_v31_selection_transport(
        store=store,
        run_id=_RUN_ID,
        cycle_index=1,
        preselection_binding=compiled["preselection_binding"],
        action_evaluation_binding=compiled["action_evaluation_binding"],
        owner_id="q7-selection-owner",
        lease_acquired_at="2026-08-06T12:11:00Z",
        lease_expires_at="2026-08-06T12:11:30Z",
        stage_times={
            "reserved_at": "2026-08-06T12:11:00Z",
            "requested_at": "2026-08-06T12:11:01Z",
            "claimed_at": "2026-08-06T12:11:02Z",
            "delivered_at": "2026-08-06T12:11:03Z",
            "consumed_at": "2026-08-06T12:11:04Z",
        },
        agent_call=select_wait,
    )
    if completed.get("status") != "COMPLETED":
        raise AssertionError("fresh no-network Q7 fixture did not complete")


def _make_chain(project: Path) -> dict[str, Any]:
    theory_sha256 = _write_bytes(
        project, _THEORY_PATH, (_PROJECT_ROOT / _THEORY_PATH).read_bytes()
    )
    experiment_contract = build_minimal_experiment_contract(
        contract_id="v31-minimal-experiment-contract",
        run_id=_RUN_ID,
        frozen_at="2026-08-06T15:50:00Z",
    )
    experiment_contract_sha256 = _write_json(
        project, _EXPERIMENT_CONTRACT_PATH, experiment_contract
    )
    experiment_contract_binding = _binding(
        path=_EXPERIMENT_CONTRACT_PATH,
        document=experiment_contract,
        digest_field="experiment_contract_digest",
        physical_sha256=experiment_contract_sha256,
    )

    approval = self_digest(
        {
            "schema_id": "theory_paper_v31_user_approval_receipt",
            "schema_version": "1.0.0",
            "approval_id": "v31-approval-20260806t154026z",
            "approved_at": "2026-08-06T15:40:26Z",
            "approval_source": "CURRENT_CODEX_TASK_USER_MESSAGE",
            "user_statement": "我批准，并授权实验",
            "theory_path": _THEORY_PATH,
            "theory_version": "3.1",
            "theory_physical_sha256": theory_sha256,
            "approval_scope": [
                "FROZEN_V3_1_THEORY_AUTHORITY",
                "SOLE_FRESH_BTC_USDT_PUBLIC_DATA_NON_EXECUTABLE_PROSPECTIVE_EXPERIMENT_AFTER_Q0_Q8",
            ],
            "experiment_authorization_status": (
                "CONDITIONAL_ON_Q0_Q8_AND_EXACT_RUN_MANIFEST_RECEIPT_BINDING"
            ),
            "excluded_authority": [
                "RESUME_LEGACY_RUN",
                "ACCOUNT_ACCESS",
                "PAPER_TRADING",
                "LIVE_TRADING",
                "ORDER_SUBMISSION",
                "CREDENTIAL_ACCESS",
                "FUNDS_ACCESS",
            ],
            "legacy_runs_resumable": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "approval_receipt_digest",
    )
    approval_sha256 = _write_json(project, _APPROVAL_PATH, approval)
    approval_binding = _binding(
        path=_APPROVAL_PATH,
        document=approval,
        digest_field="approval_receipt_digest",
        physical_sha256=approval_sha256,
    )

    theory_binding = {
        "path": _THEORY_PATH,
        "version": "3.1",
        "review_status": "FROZEN_APPROVED",
        "physical_sha256": theory_sha256,
    }
    evidence_paths = sorted(
        {
            path
            for gate_id in TYPED_QUALIFICATION_GATE_IDS
            for path in required_gate_evidence_paths(gate_id)
        }
        | set(required_external_gate_evidence_paths("Q6"))
        | set(required_external_gate_evidence_paths("Q7"))
    )
    implementation_bindings = {
        path: _write_bytes(
            project,
            path,
            f"# frozen evidence for {path}\n".encode("utf-8"),
        )
        for path in evidence_paths
    }
    capability_matrix = experiment_contract["capability_matrix"]
    manifest_document = {
        "schema_id": "theory_paper_v31_frozen_experiment_manifest",
            "schema_version": "1.1.0",
            "manifest_id": "v31-frozen-manifest-20260806t161000z",
            "created_at": "2026-08-06T16:10:00Z",
            "run_id": _RUN_ID,
            "operation": "RUN_V31_PROSPECTIVE",
            "theory_binding": theory_binding,
            "theory_approval_binding": approval_binding,
            "experiment_contract_binding": experiment_contract_binding,
            "symbol": "BTC-USDT",
            "instrument": {
                "venue": "OKX",
                "instrument_id": "BTC-USDT-SWAP",
                "market_type": "PERPETUAL_SWAP",
                "underlying_symbol": "BTC-USDT",
            },
            "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "source_plan": {
                "allowed_source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
                "raw_capture_required": True,
                "pit_available_at_required": True,
                "missing_is_unknown": True,
            },
            "agent_plan": {
                "agent_id": "CURRENT_CODEX_TASK",
                "proposal_then_postseal_selection": True,
                "durable_before_adapter_return": True,
                "reinvocation_after_accept": False,
                "sub_agents_allowed": False,
            },
            "fresh_run": True,
            "predecessor_run_id": None,
            "qualification_gates": {},
            "experiment_used_capabilities": sorted(
                row["capability_id"]
                for row in capability_matrix
                if row["used_or_evaluated"]
            ),
            "implemented_and_verified_capabilities": sorted(
                row["capability_id"]
                for row in capability_matrix
                if row["status"] == "IMPLEMENTED_AND_VERIFIED"
            ),
            "excluded_no_claim_capabilities": sorted(
                row["capability_id"]
                for row in capability_matrix
                if row["status"] == "EXCLUDED_NO_CLAIM"
            ),
            "portfolio_scope": copy.deepcopy(experiment_contract["portfolio_scope"]),
            "association_preregistration": copy.deepcopy(
                experiment_contract["association_scope"]
            ),
            "evaluation_contract": copy.deepcopy(experiment_contract["evaluation"]),
            "total_cycles": 8,
            "cadence_seconds": 3600,
            "legal_action_classes": [
                "OPEN_LONG",
                "OPEN_SHORT",
                "WAIT",
            ],
            "stop_rules": copy.deepcopy(
                experiment_contract["evaluation"]["stop_rules"][
                    "stop_immediately_on"
                ]
            ),
            "implementation_bindings": implementation_bindings,
            "assembly_bundle_contract": {
                "schema_id": "theory_paper_v2_v31_durable_assembly_bundle",
                "schema_version": "1.0.0",
                "content_addressed": True,
                "chat_history_is_authority": False,
            },
            "checkpoint_contract": {
                "schema_id": "theory_paper_v31_research_checkpoint",
                "schema_version": "1.2.0",
                "genesis_bindings_required": True,
            },
            "event_order": [
                "INPUTS_ADMITTED",
                "PROPOSAL_SEALED",
                "EVALUATION_SEALED",
                "SELECTION_SEALED",
                "STATE_ACCEPTED",
                "COMPLETION_SEALED",
            ],
            "authorization_cardinality": "EXACTLY_ONE_FRESH_RUN",
            "legacy_runs_resumable": False,
            "chat_history_is_authority": False,
            "authority_boundary": copy.deepcopy(
                experiment_contract["authority_boundary"]
            ),
            **_EXECUTION_FALSE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
    }
    qualification_receipts: dict[str, dict[str, Any]] = {}
    qualification_gates: dict[str, dict[str, Any]] = {}
    _create_no_network_q7_fixture(
        project,
        experiment_contract=experiment_contract,
        theory_approval=approval,
    )
    for index in range(9):
        gate_id = f"Q{index}"
        if gate_id in TYPED_QUALIFICATION_GATE_IDS:
            receipt = build_typed_qualification_receipt(
                gate_id=gate_id,
                evaluated_at=f"2026-08-06T16:0{index}:00Z",
                experiment_contract=experiment_contract,
                manifest=manifest_document,
                theory_approval=approval,
            )
        elif gate_id == "Q6":
            receipt = build_q6_receipt_from_durable_qualification(
                project_root=project,
                qualification_root_ref=_Q6_ROOT_REF,
                qualification_id=_Q6_QUALIFICATION_ID,
                evaluated_at="2026-08-06T16:20:00Z",
                experiment_contract=experiment_contract,
                manifest=manifest_document,
            )
        else:
            receipt = build_q7_receipt_from_completed_authoring_transport(
                project_root=project,
                qualification_root_ref=_Q7_ROOT_REF,
                subject_run_id=_RUN_ID,
                evaluated_at="2026-08-06T16:21:00Z",
                experiment_contract=experiment_contract,
                manifest=manifest_document,
            )
        receipt_path = f"config/qualification-{gate_id.lower()}.json"
        receipt_sha256 = _write_json(project, receipt_path, receipt)
        qualification_receipts[gate_id] = receipt
        qualification_gates[gate_id] = {
            "status": "PASS",
            "receipt_binding": _binding(
                path=receipt_path,
                document=receipt,
                digest_field="qualification_receipt_digest",
                physical_sha256=receipt_sha256,
            ),
        }
    manifest_document["qualification_gates"] = qualification_gates
    manifest = self_digest(manifest_document, "manifest_digest")
    manifest_sha256 = _write_json(project, _MANIFEST_PATH, manifest)
    manifest_binding = _binding(
        path=_MANIFEST_PATH,
        document=manifest,
        digest_field="manifest_digest",
        physical_sha256=manifest_sha256,
    )

    authority_id = "v31-active-frozen-research-20260806t161500z"
    authorization_receipt = self_digest(
        {
            "schema_id": "theory_paper_v31_experiment_authorization_receipt",
            "schema_version": "1.1.0",
            "authorization_id": "v31-experiment-authorization-20260806t161500z",
            "authority_id": authority_id,
            "issued_at": "2026-08-06T16:15:00Z",
            "theory_approval_binding": approval_binding,
            "theory_physical_sha256": theory_sha256,
            "operation": "RUN_V31_PROSPECTIVE",
            "run_id": _RUN_ID,
            "manifest_binding": manifest_binding,
            "experiment_contract_binding": experiment_contract_binding,
            "symbol": "BTC-USDT",
            "instrument": copy.deepcopy(manifest["instrument"]),
            "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "total_cycles": 8,
            "authorization_cardinality": "EXACTLY_ONE_FRESH_RUN",
            "legacy_runs_resumable": False,
            "chat_history_is_authority": False,
            **_EXECUTION_FALSE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "authorization_receipt_digest",
    )
    authorization_sha256 = _write_json(
        project, _AUTHORIZATION_PATH, authorization_receipt
    )
    authorization_binding = _binding(
        path=_AUTHORIZATION_PATH,
        document=authorization_receipt,
        digest_field="authorization_receipt_digest",
        physical_sha256=authorization_sha256,
    )

    predecessor = {
        "schema_id": "theory_paper_v2_current_research_authority",
        "schema_version": "1.0.0",
        "authority_id": "v31-frozen-qualification-pending",
        "recorded_at": "2026-08-06T15:40:26Z",
        "status": "FROZEN_V3_1_QUALIFICATION_PENDING",
        "reason": "Frozen theory; start denied until the exact chain is complete.",
        "current_theory": theory_binding,
        "candidate_theory": {
            **theory_binding,
            "review_status": "FROZEN_APPROVED_CURRENT",
        },
        "experiment_start_authorized": False,
        "authorized_operations": [],
        "authorized_run_ids": [],
        "authorized_template_sha256s": [],
        "authorization_receipt_path": None,
        "authorization_receipt_digest": None,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    predecessor_sha256 = _write_json(project, _PREDECESSOR_PATH, predecessor)

    authority = self_digest(
        {
            "schema_id": "theory_paper_v31_current_research_authority",
            "schema_version": "2.1.0",
            "authority_id": authority_id,
            "recorded_at": "2026-08-06T16:16:00Z",
            "status": "ACTIVE_FROZEN_RESEARCH",
            "reason": "One frozen, qualified, public-data-only V3.1 run is authorized.",
            "predecessor_authority_binding": {
                "path": _PREDECESSOR_PATH,
                "physical_sha256": predecessor_sha256,
                "expected_status": "FROZEN_V3_1_QUALIFICATION_PENDING",
            },
            "current_theory": theory_binding,
            "theory_approval_binding": approval_binding,
            "experiment_start_authorized": True,
            "authorized_operation": "RUN_V31_PROSPECTIVE",
            "authorized_run_id": _RUN_ID,
            "manifest_binding": manifest_binding,
            "authorization_receipt_binding": authorization_binding,
            "experiment_contract_binding": experiment_contract_binding,
            "authorization_cardinality": "EXACTLY_ONE_FRESH_RUN",
            "symbol": "BTC-USDT",
            "instrument": copy.deepcopy(manifest["instrument"]),
            "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "total_cycles": 8,
            "legacy_runs_resumable": False,
            "chat_history_is_authority": False,
            **_EXECUTION_FALSE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "authority_digest",
    )
    _write_json(
        project, V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(), authority
    )
    return {
        "approval": approval,
        "experiment_contract": experiment_contract,
        "authorization_receipt": authorization_receipt,
        "authority": authority,
        "manifest": manifest,
        "predecessor": predecessor,
        "qualification_receipts": qualification_receipts,
    }


class V31AuthorizationTests(unittest.TestCase):
    def test_q6_q7_generic_opaque_pass_receipts_are_permanently_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chain = _make_chain(Path(directory))
            for gate_id in ("Q6", "Q7"):
                generic = self_digest(
                    {
                        "schema_id": "theory_paper_v31_qualification_gate_receipt",
                        "schema_version": "1.0.0",
                        "gate_id": gate_id,
                        "evaluated_at": "2026-08-06T16:30:00Z",
                        "verdict": "PASS",
                        "evidence_digests": ["a" * 64],
                        "limitations": [],
                        "external_execution_authority": (
                            "NONE_LOCAL_SIMULATION"
                        ),
                        "executable": False,
                    },
                    "qualification_receipt_digest",
                )
                with self.subTest(gate_id=gate_id), self.assertRaisesRegex(
                    V31AuthorizationError,
                    "V31_EXTERNAL_TYPED_QUALIFICATION_RECEIPT_INVALID",
                ):
                    validate_v31_qualification_receipt(
                        generic,
                        expected_gate_id=gate_id,
                        experiment_contract=chain["experiment_contract"],
                        manifest=chain["manifest"],
                        theory_approval=chain["approval"],
                    )

    def test_manifest_requires_typed_schema_for_q6_and_q7(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chain = _make_chain(Path(directory))
            for gate_id in ("Q6", "Q7"):
                manifest = {
                    key: value
                    for key, value in copy.deepcopy(chain["manifest"]).items()
                    if key != "manifest_digest"
                }
                manifest["qualification_gates"][gate_id]["receipt_binding"][
                    "schema_id"
                ] = "theory_paper_v31_qualification_gate_receipt"
                manifest = self_digest(manifest, "manifest_digest")
                with self.subTest(gate_id=gate_id), self.assertRaisesRegex(
                    V31AuthorizationError,
                    "V31_MANIFEST_QUALIFICATION_GATES_INVALID",
                ):
                    validate_v31_frozen_experiment_manifest(
                        manifest,
                        experiment_contract=chain["experiment_contract"],
                        theory_approval=chain["approval"],
                    )

    def test_q6_typed_receipt_passes_and_loader_replays_retained_raw_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            chain = _make_chain(project)
            receipt = chain["qualification_receipts"]["Q6"]
            self.assertEqual(
                receipt["qualification_receipt_digest"],
                validate_v31_qualification_receipt(
                    receipt,
                    expected_gate_id="Q6",
                    experiment_contract=chain["experiment_contract"],
                    manifest=chain["manifest"],
                    theory_approval=chain["approval"],
                ),
            )
            raw = (
                project
                / _Q6_ROOT_REF
                / "cycles/0001/market/raw/okx-native-ticker.body"
            )
            raw.write_bytes(raw.read_bytes() + b" ")
            with self.assertRaisesRegex(
                V31AuthorizationError,
                "V31_Q6_DURABLE_EVIDENCE_REPLAY_INVALID",
            ):
                load_v31_active_authorization_chain(project)

    def test_q7_typed_receipt_passes_and_loader_replays_compiled_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            chain = _make_chain(project)
            receipt = chain["qualification_receipts"]["Q7"]
            self.assertEqual(
                receipt["qualification_receipt_digest"],
                validate_v31_qualification_receipt(
                    receipt,
                    expected_gate_id="Q7",
                    experiment_contract=chain["experiment_contract"],
                    manifest=chain["manifest"],
                    theory_approval=chain["approval"],
                ),
            )
            bundle = (
                project
                / _Q7_ROOT_REF
                / "cycles/0001/agent-transport/compilation/compiled-assembly-bundle.json"
            )
            bundle.write_bytes(bundle.read_bytes() + b" ")
            with self.assertRaisesRegex(
                V31AuthorizationError,
                "V31_Q7_DURABLE_EVIDENCE_REPLAY_INVALID",
            ):
                load_v31_active_authorization_chain(project)

    def test_complete_chain_passes_domain_and_physical_loader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            chain = _make_chain(project)
            validate_v31_theory_approval(chain["approval"])
            for gate_id, receipt in chain["qualification_receipts"].items():
                validate_v31_qualification_receipt(
                    receipt,
                    expected_gate_id=gate_id,
                    experiment_contract=chain["experiment_contract"],
                    manifest=chain["manifest"],
                    theory_approval=chain["approval"],
                )
            validate_v31_frozen_experiment_manifest(
                chain["manifest"],
                experiment_contract=chain["experiment_contract"],
                theory_approval=chain["approval"],
            )
            validate_v31_experiment_authorization(
                chain["authorization_receipt"],
                manifest=chain["manifest"],
                experiment_contract=chain["experiment_contract"],
                theory_approval=chain["approval"],
            )
            validate_v31_active_authority(
                chain["authority"],
                theory_approval=chain["approval"],
                manifest=chain["manifest"],
                experiment_contract=chain["experiment_contract"],
                authorization_receipt=chain["authorization_receipt"],
            )
            loaded = load_v31_active_authorization_chain(project)
            self.assertEqual(_RUN_ID, loaded["authority"]["authorized_run_id"])
            self.assertEqual(set(f"Q{i}" for i in range(9)), set(loaded["qualification_receipts"]))

    def test_manifest_rejects_missing_q8_even_after_resigning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chain = _make_chain(Path(directory))
            manifest = copy.deepcopy(chain["manifest"])
            manifest.pop("manifest_digest")
            manifest["qualification_gates"].pop("Q8")
            manifest = self_digest(manifest, "manifest_digest")
            with self.assertRaisesRegex(
                V31AuthorizationError, "V31_MANIFEST_QUALIFICATION_GATES_INVALID"
            ):
                validate_v31_frozen_experiment_manifest(
                    manifest,
                    experiment_contract=chain["experiment_contract"],
                    theory_approval=chain["approval"],
                )

    def test_manifest_rejects_old_operation_and_execution_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chain = _make_chain(Path(directory))
            for changes in (
                {"operation": "RUN_NATIVE_MARKET_PILOT"},
                {"paper_trading": True},
            ):
                manifest = {
                    key: value
                    for key, value in copy.deepcopy(chain["manifest"]).items()
                    if key != "manifest_digest"
                }
                manifest.update(changes)
                manifest = self_digest(manifest, "manifest_digest")
                with self.assertRaises(V31AuthorizationError):
                    validate_v31_frozen_experiment_manifest(
                        manifest,
                        experiment_contract=chain["experiment_contract"],
                        theory_approval=chain["approval"],
                    )

    def test_active_authority_rejects_run_mismatch_and_schema_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chain = _make_chain(Path(directory))
            for changes in (
                {"authorized_run_id": "different-run"},
                {"authorized_run_ids": [_RUN_ID]},
                {
                    "instrument": {
                        "venue": "OKX",
                        "instrument_id": "BTC-USDT",
                        "market_type": "SPOT",
                        "underlying_symbol": "BTC-USDT",
                    }
                },
            ):
                authority = {
                    key: value
                    for key, value in copy.deepcopy(chain["authority"]).items()
                    if key != "authority_digest"
                }
                authority.update(changes)
                authority = self_digest(authority, "authority_digest")
                with self.assertRaises(V31AuthorizationError):
                    validate_v31_active_authority(
                        authority,
                        theory_approval=chain["approval"],
                        manifest=chain["manifest"],
                        experiment_contract=chain["experiment_contract"],
                        authorization_receipt=chain["authorization_receipt"],
                    )

    def test_loader_rejects_bound_file_physical_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _make_chain(project)
            approval_path = project / _APPROVAL_PATH
            approval_path.write_bytes(approval_path.read_bytes() + b" ")
            with self.assertRaisesRegex(
                V31AuthorizationError, "V31_APPROVAL_BINDING_INVALID_PHYSICAL_DRIFT"
            ):
                load_v31_active_authorization_chain(project)

    def test_loader_rejects_experiment_contract_and_gate_evidence_drift(self) -> None:
        for relative_path, expected_error in (
            (
                _EXPERIMENT_CONTRACT_PATH,
                "V31_EXPERIMENT_CONTRACT_BINDING_INVALID_PHYSICAL_DRIFT",
            ),
            (
                "trade_system/theory_paper_v2/domain/association_estimation.py",
                "V31_IMPLEMENTATION_BINDING_DRIFT",
            ),
        ):
            with self.subTest(relative_path=relative_path):
                with tempfile.TemporaryDirectory() as directory:
                    project = Path(directory)
                    _make_chain(project)
                    target = project / relative_path
                    target.write_bytes(target.read_bytes() + b"# drift\n")
                    with self.assertRaisesRegex(
                        V31AuthorizationError, expected_error
                    ):
                        load_v31_active_authorization_chain(project)

    def test_loader_rejects_predecessor_that_is_no_longer_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            chain = _make_chain(project)
            predecessor = copy.deepcopy(chain["predecessor"])
            predecessor["status"] = "ACTIVE_FROZEN_RESEARCH"
            predecessor_sha256 = _write_json(
                project, _PREDECESSOR_PATH, predecessor
            )
            authority = {
                key: value
                for key, value in copy.deepcopy(chain["authority"]).items()
                if key != "authority_digest"
            }
            authority["predecessor_authority_binding"][
                "physical_sha256"
            ] = predecessor_sha256
            authority = self_digest(authority, "authority_digest")
            _write_json(
                project,
                V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
                authority,
            )
            with self.assertRaisesRegex(
                V31AuthorizationError, "V31_PREDECESSOR_NOT_FROZEN_PENDING"
            ):
                load_v31_active_authorization_chain(project)


if __name__ == "__main__":
    unittest.main()
