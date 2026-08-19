from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.application.v31_successor_cycle_commit_v2 import (
    commit_or_recover_v31_successor_cycle_v2,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
    build_minimal_experiment_contract,
    build_typed_path_monitor_plan,
)
from trade_system.theory_paper_v2.domain.v31_successor_cycle_commit_v2 import (
    V31SuccessorCycleCommitV2Error,
    build_v31_successor_cycle_commit_material_v2,
    successor_commit_material_ref_v2,
    verify_v31_successor_cycle_commit_material_v2,
)
from trade_system.theory_paper_v2.infrastructure.v31_successor_commit_store_v2 import (
    LocalV31SuccessorCommitStoreV2,
    V31SuccessorCommitStoreV2Error,
)


RUN_ID = "v31-successor-commit-test"


def _binding(name: str, character: str) -> dict[str, str]:
    return {
        "relative_ref": f"support/{name}.json",
        "schema_id": f"schema:{name}",
        "digest_field": f"{name}_digest",
        "semantic_digest": character * 64,
        "physical_sha256": character * 64,
    }


def _contract() -> dict:
    return build_minimal_experiment_contract(
        contract_id="v31-successor-commit-contract",
        run_id=RUN_ID,
        frozen_at="2026-08-07T00:00:00Z",
    )


def _material() -> tuple[dict, dict]:
    contract = _contract()
    accepted_digest = "7" * 64
    origins = {
        "accepted_state": {
            "ref": "cycles/0001/accepted-research-state.json",
            "digest": accepted_digest,
        },
        "path_set": {"ref": "path-set:1", "digest": "8" * 64},
        "path": {"ref": "path:lead", "digest": "9" * 64},
        "hypothesis_revision": {
            "ref": "hypothesis:1:r1",
            "digest": "a" * 64,
        },
        "expectation_revision": {
            "ref": "expectation:1:r1",
            "digest": "b" * 64,
        },
    }
    observable = "metric:mark-price-usdt"
    plan = build_typed_path_monitor_plan(
        experiment_contract=contract,
        monitor_plan_id=f"monitor:{RUN_ID}:0001:absolute-mark-1h",
        cycle_id=f"{RUN_ID}:cycle:0001",
        cycle_index=1,
        origin_bindings=origins,
        decision_at="2026-08-07T01:00:00Z",
        observable_ref=observable,
        source_request_id=f"okx-public-mark-price:{RUN_ID}:0001:1h",
        rules=(
            FrozenMonitorRule(
                rule_id="confirmation",
                role=MonitorRuleRole.CONFIRMATION,
                observable_ref=observable,
                operator=MonitorOperator.GT,
                expected="65000",
                unit="USDT_PER_BTC",
            ),
            FrozenMonitorRule(
                rule_id="contradiction",
                role=MonitorRuleRole.CONTRADICTION,
                observable_ref=observable,
                operator=MonitorOperator.LT,
                expected="64500",
                unit="USDT_PER_BTC",
            ),
            FrozenMonitorRule(
                rule_id="falsifier",
                role=MonitorRuleRole.FALSIFIER,
                observable_ref=observable,
                operator=MonitorOperator.LTE,
                expected="64000",
                unit="USDT_PER_BTC",
            ),
        ),
    )
    assembly = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_durable_assembly_bundle",
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "expected_artifact_digests": {
                "STATE_ACCEPTED": accepted_digest
            },
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "assembly_bundle_digest",
    )
    support = {
        "clock_policy": _binding("clock-policy", "c"),
        "sentiment_source_registry": _binding("axis-registry", "d"),
        "sentiment_projection": _binding("axis-projection", "e"),
        "association_preregistration": _binding("association", "f"),
        "evaluation_contract": _binding("evaluation", "1"),
        "fresh_qualification_bundle": _binding("qualification", "2"),
        "application_authority_projection": _binding("projection", "3"),
    }
    material = build_v31_successor_cycle_commit_material_v2(
        run_id=RUN_ID,
        cycle_index=1,
        prepared_at="2026-08-07T01:05:00Z",
        cycle_permit_binding={
            "relative_ref": "supervisor-v2/cycles/0001/permit.json",
            "schema_id": "theory_paper_v31_experiment_cycle_permit",
            "digest_field": "cycle_permit_digest",
            "semantic_digest": "4" * 64,
            "physical_sha256": "5" * 64,
        },
        active_authority_digest="6" * 64,
        experiment_contract=contract,
        research_checkpoint_digest_before_commit="8" * 64,
        monitor_checkpoint_digest_before_commit="9" * 64,
        authoring_packet_digest="a" * 64,
        transport_evidence_binding={
            "relative_ref": "cycles/0001/transport-evidence/a.json",
            "schema_id": "theory_paper_v31_agent_transport_evidence",
            "digest_field": "transport_evidence_digest",
            "semantic_digest": "b" * 64,
            "physical_sha256": "c" * 64,
        },
        assembly_bundle=assembly,
        monitor_plan=plan,
        monitor_runtime_created_at="2026-08-07T01:00:01Z",
        scheduled_at="2026-08-07T01:06:00Z",
        support_bindings=support,
    )
    return contract, material


class V31SuccessorCycleCommitV2Tests(unittest.TestCase):
    def test_reconstructs_complete_material(self) -> None:
        contract, material = _material()
        digest = verify_v31_successor_cycle_commit_material_v2(
            material, experiment_contract=contract
        )
        self.assertEqual(material["successor_commit_material_digest"], digest)
        self.assertFalse(material["agent_reinvocation_allowed"])
        self.assertFalse(material["outcome_collection_allowed"])

    def test_embedded_plan_drift_fails_closed(self) -> None:
        contract, material = _material()
        tampered = copy.deepcopy(material)
        tampered["monitor_plan"]["rules"][0]["expected"] = "99999"
        with self.assertRaises(V31SuccessorCycleCommitV2Error):
            verify_v31_successor_cycle_commit_material_v2(
                tampered, experiment_contract=contract
            )

    def test_store_is_write_once_and_physically_replayed(self) -> None:
        contract, material = _material()
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31SuccessorCommitStoreV2(
                Path(directory), experiment_contract=contract
            )
            ref = successor_commit_material_ref_v2(1)
            binding = store.write_material(
                relative_ref=ref, document=material
            )
            self.assertEqual(
                material["successor_commit_material_digest"],
                binding["semantic_digest"],
            )
            self.assertEqual(
                material,
                store.read_material(
                    relative_ref=ref,
                    expected_semantic_digest=binding["semantic_digest"],
                ),
            )
            path = Path(directory) / ref
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(V31SuccessorCommitStoreV2Error):
                store.read_material(relative_ref=ref)

    def test_store_rejects_escape(self) -> None:
        contract, material = _material()
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31SuccessorCommitStoreV2(
                Path(directory), experiment_contract=contract
            )
            with self.assertRaises(V31SuccessorCommitStoreV2Error):
                store.write_material(
                    relative_ref="successor-commit-v2/../escape.json",
                    document=material,
                )

    def test_crash_after_research_commit_recovers_without_agent_or_outcome(
        self,
    ) -> None:
        contract, material = _material()

        class Supervisor:
            def __init__(self) -> None:
                self.checkpoint = {
                    "status": "CYCLE_PERMIT_OPEN",
                    "completed_research_cycles": 0,
                }
                self.intent = None

            def load_checkpoint(self, *, run_id: str):
                self.assert_run(run_id)
                return copy.deepcopy(self.checkpoint)

            def assert_run(self, run_id: str) -> None:
                if run_id != RUN_ID:
                    raise ValueError("wrong run")

            def read_document(
                self,
                *,
                relative_ref: str,
                digest_field: str,
                expected_semantic_digest: str | None = None,
            ):
                if self.intent is None:
                    raise ValueError("missing intent")
                return copy.deepcopy(self.intent)

        class Research:
            def __init__(self) -> None:
                self.completed = 0

            def load_checkpoint(self, *, run_id: str):
                if run_id != RUN_ID:
                    raise ValueError("wrong run")
                return {
                    "created_at": "2026-08-07T00:00:00Z",
                    "completed_cycles": self.completed,
                }

        supervisor = Supervisor()
        research = Research()
        monitor = object()
        crash_once = {"pending": True}
        calls = {"persist": 0, "schedule": 0, "record": 0}

        def reserve(**kwargs):
            supervisor.intent = self_digest(
                {
                    "schema_id": (
                        "theory_paper_v31_experiment_cycle_commit_intent"
                    ),
                    "schema_version": "2.0.0",
                    "run_id": RUN_ID,
                    "cycle_index": 1,
                    "commit_material_digest": material[
                        "successor_commit_material_digest"
                    ],
                    "cycle_permit_digest": material[
                        "cycle_permit_digest"
                    ],
                    "research_checkpoint_digest_before_commit": material[
                        "research_checkpoint_digest_before_commit"
                    ],
                    "monitor_checkpoint_digest_before_commit": material[
                        "monitor_checkpoint_digest_before_commit"
                    ],
                },
                "commit_intent_digest",
            )
            supervisor.checkpoint = {
                "status": "COMMIT_RESERVED",
                "active_commit_intent_digest": supervisor.intent[
                    "commit_intent_digest"
                ],
                "completed_research_cycles": 0,
            }
            return {"supervisor_checkpoint": copy.deepcopy(supervisor.checkpoint)}

        def persist(**kwargs):
            calls["persist"] += 1
            research.completed = 1
            if crash_once["pending"]:
                crash_once["pending"] = False
                raise SystemExit("simulated process death after research CAS")
            return {"completed_cycles": 1}

        def schedule(**kwargs):
            calls["schedule"] += 1
            return {"plan_bindings": [{"cycle_index": 1}]}

        def record(**kwargs):
            calls["record"] += 1
            supervisor.checkpoint = {
                "status": "AWAITING_OUTCOME",
                "completed_research_cycles": 1,
            }
            return {"supervisor_checkpoint": copy.deepcopy(supervisor.checkpoint)}

        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31SuccessorCommitStoreV2(
                Path(directory), experiment_contract=contract
            )
            ref = successor_commit_material_ref_v2(1)
            binding = store.write_material(
                relative_ref=ref, document=material
            )
            patches = (
                patch(
                    "trade_system.theory_paper_v2.application."
                    "v31_successor_cycle_commit_v2._validate_active_chain",
                    return_value=(
                        RUN_ID,
                        contract["experiment_contract_digest"],
                        "6" * 64,
                        contract,
                        {},
                    ),
                ),
                patch(
                    "trade_system.theory_paper_v2.application."
                    "v31_successor_cycle_commit_v2."
                    "reserve_v31_cycle_commit_v2",
                    side_effect=reserve,
                ),
                patch(
                    "trade_system.theory_paper_v2.application."
                    "v31_successor_cycle_commit_v2."
                    "rebuild_v31_documents_from_bundle",
                    return_value=(
                        {},
                        {"STATE_ACCEPTED": {}},
                        {},
                    ),
                ),
                patch(
                    "trade_system.theory_paper_v2.application."
                    "v31_successor_cycle_commit_v2."
                    "persist_completed_v31_cycle",
                    side_effect=persist,
                ),
                patch(
                    "trade_system.theory_paper_v2.application."
                    "v31_successor_cycle_commit_v2."
                    "initialize_v31_monitor_runtime",
                    return_value={},
                ),
                patch(
                    "trade_system.theory_paper_v2.application."
                    "v31_successor_cycle_commit_v2.schedule_v31_monitor_plan",
                    side_effect=schedule,
                ),
                patch(
                    "trade_system.theory_paper_v2.application."
                    "v31_successor_cycle_commit_v2."
                    "record_v31_cycle_commit_v2",
                    side_effect=record,
                ),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
                with self.assertRaises(SystemExit):
                    commit_or_recover_v31_successor_cycle_v2(
                        supervisor_store=supervisor,
                        commit_store=store,
                        research_store=research,
                        monitor_store=monitor,
                        active_chain={},
                        material_binding=binding,
                        committed_at="2026-08-07T01:07:00Z",
                    )
                result = commit_or_recover_v31_successor_cycle_v2(
                    supervisor_store=supervisor,
                    commit_store=store,
                    research_store=research,
                    monitor_store=monitor,
                    active_chain={},
                    material_binding=binding,
                    committed_at="2026-08-07T01:08:00Z",
                )

        self.assertEqual(
            "SUCCESSOR_CYCLE_ACCEPTED_MONITOR_SCHEDULED", result["status"]
        )
        self.assertEqual(2, calls["persist"])
        self.assertEqual(1, calls["schedule"])
        self.assertEqual(1, calls["record"])
        self.assertFalse(result["agent_reinvoked"])
        self.assertFalse(result["outcome_collection_performed"])


if __name__ == "__main__":
    unittest.main()
