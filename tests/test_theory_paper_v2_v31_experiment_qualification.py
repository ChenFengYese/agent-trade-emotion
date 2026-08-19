from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_qualification_receipt,
)
from trade_system.theory_paper_v2.domain.governance.v31_experiment_qualification import (
    TYPED_QUALIFICATION_GATE_IDS,
    V31ExperimentQualificationError,
    build_typed_qualification_receipt,
    manifest_qualification_subject_digest,
    required_gate_evidence_paths,
    verify_typed_qualification_receipt,
)
from tests.test_theory_paper_v2_v31_authorization import _make_chain


class V31ExperimentQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.chain = _make_chain(Path(self.directory.name))
        self.contract = self.chain["experiment_contract"]
        self.manifest = self.chain["manifest"]

    def test_all_seven_local_typed_gates_bind_contract_subject_checks_and_exact_evidence(self) -> None:
        for gate_id in TYPED_QUALIFICATION_GATE_IDS:
            receipt = self.chain["qualification_receipts"][gate_id]
            self.assertEqual(
                receipt["qualification_receipt_digest"],
                verify_typed_qualification_receipt(
                    receipt,
                    expected_gate_id=gate_id,
                    experiment_contract=self.contract,
                    manifest=self.manifest,
                    theory_approval=self.chain["approval"],
                ),
            )
            self.assertEqual(
                self.contract["experiment_contract_digest"],
                receipt["experiment_contract_digest"],
            )
            self.assertEqual(
                manifest_qualification_subject_digest(self.manifest),
                receipt["manifest_qualification_subject_digest"],
            )
            self.assertTrue(receipt["checks"])
            self.assertTrue(
                all(check["status"] == "PASS" for check in receipt["checks"])
            )
            receipt_paths = [
                binding["path"] for binding in receipt["evidence_bindings"]
            ]
            self.assertTrue(
                set(required_gate_evidence_paths(gate_id)).issubset(
                    receipt_paths
                )
            )
            if gate_id == "Q1":
                self.assertIn(
                    self.chain["approval"]["theory_path"], receipt_paths
                )
                self.assertIn("config/theory-approval.json", receipt_paths)

    def test_old_arbitrary_64hex_q0_receipt_cannot_pass(self) -> None:
        legacy = self_digest(
            {
                "schema_id": "theory_paper_v31_qualification_gate_receipt",
                "schema_version": "1.0.0",
                "gate_id": "Q0",
                "evaluated_at": "2026-08-06T16:00:00Z",
                "verdict": "PASS",
                "evidence_digests": ["a" * 64],
                "limitations": [],
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "qualification_receipt_digest",
        )
        with self.assertRaisesRegex(
            V31AuthorizationError, "TYPED_QUALIFICATION_RECEIPT_INVALID"
        ):
            validate_v31_qualification_receipt(
                legacy,
                expected_gate_id="Q0",
                experiment_contract=self.contract,
                manifest=self.manifest,
            )

    def test_old_arbitrary_64hex_q1_q2_q4_receipts_cannot_pass(self) -> None:
        for gate_id in ("Q1", "Q2", "Q4"):
            legacy = self_digest(
                {
                    "schema_id": "theory_paper_v31_qualification_gate_receipt",
                    "schema_version": "1.0.0",
                    "gate_id": gate_id,
                    "evaluated_at": f"2026-08-06T16:0{gate_id[1]}:00Z",
                    "verdict": "PASS",
                    "evidence_digests": [gate_id[1] * 64],
                    "limitations": [],
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "qualification_receipt_digest",
            )
            with self.subTest(gate_id=gate_id):
                with self.assertRaisesRegex(
                    V31AuthorizationError,
                    "TYPED_QUALIFICATION_RECEIPT_INVALID",
                ):
                    validate_v31_qualification_receipt(
                        legacy,
                        expected_gate_id=gate_id,
                        experiment_contract=self.contract,
                        manifest=self.manifest,
                        theory_approval=self.chain["approval"],
                    )

    def test_q1_reconstructs_actual_approval_and_exact_frozen_theory_sha(self) -> None:
        receipt = self.chain["qualification_receipts"]["Q1"]
        checks = {row["check_id"]: row for row in receipt["checks"]}
        self.assertEqual(
            {
                "Q1_APPROVAL_RECEIPT_RECONSTRUCTED",
                "Q1_FROZEN_THEORY_SHA_EXACT",
                "Q1_MANIFEST_THEORY_BINDINGS_EXACT",
                "Q1_AUTHORITY_REMAINS_NON_EXECUTABLE",
            },
            set(checks),
        )
        kinds = {row["evidence_kind"] for row in receipt["evidence_bindings"]}
        self.assertIn("FROZEN_THEORY_DOCUMENT", kinds)
        self.assertIn("THEORY_APPROVAL_RECEIPT", kinds)

        changed_approval = copy.deepcopy(self.chain["approval"])
        changed_approval.pop("approval_receipt_digest")
        changed_approval["user_statement"] = "批准其他范围"
        changed_approval = self_digest(
            changed_approval, "approval_receipt_digest"
        )
        with self.assertRaisesRegex(
            V31ExperimentQualificationError, "Q1_THEORY_APPROVAL_INVALID"
        ):
            build_typed_qualification_receipt(
                gate_id="Q1",
                evaluated_at="2026-08-06T16:01:00Z",
                experiment_contract=self.contract,
                manifest=self.manifest,
                theory_approval=changed_approval,
            )

        changed_manifest = copy.deepcopy(self.manifest)
        changed_manifest["theory_binding"]["physical_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            V31ExperimentQualificationError,
            "Q1_THEORY_APPROVAL_OR_MANIFEST_BINDING_MISMATCH",
        ):
            build_typed_qualification_receipt(
                gate_id="Q1",
                evaluated_at="2026-08-06T16:01:00Z",
                experiment_contract=self.contract,
                manifest=changed_manifest,
                theory_approval=self.chain["approval"],
            )

    def test_q2_binds_twelve_axis_local_chain_without_native_scope_claim(self) -> None:
        receipt = self.chain["qualification_receipts"]["Q2"]
        self.assertTrue(
            any("ten-to-twelve-axis" in value for value in receipt["limitations"])
        )
        self.assertTrue(
            any("Native twelve-axis" in value for value in receipt["limitations"])
        )
        expected_paths = set(required_gate_evidence_paths("Q2"))
        self.assertEqual(
            expected_paths,
            {
                row["path"]
                for row in receipt["evidence_bindings"]
            },
        )

        missing_chain = copy.deepcopy(self.manifest)
        missing_chain["implementation_bindings"].pop(
            "trade_system/theory_paper_v2/application/v31_durable_cycle.py"
        )
        with self.assertRaisesRegex(
            V31ExperimentQualificationError,
            "REQUIRED_IMPLEMENTATION_OR_TEST_EVIDENCE_MISSING",
        ):
            build_typed_qualification_receipt(
                gate_id="Q2",
                evaluated_at="2026-08-06T16:02:00Z",
                experiment_contract=self.contract,
                manifest=missing_chain,
            )

    def test_q4_binds_exact_bundle_replay_store_and_checkpoint_contracts(self) -> None:
        receipt = self.chain["qualification_receipts"]["Q4"]
        self.assertTrue(
            any("deterministic local bundle replay" in value for value in receipt["limitations"])
        )
        self.assertEqual(
            set(required_gate_evidence_paths("Q4")),
            {row["path"] for row in receipt["evidence_bindings"]},
        )
        self.assertIn(
            "Q4_DURABLE_CROSS_CYCLE_MONITOR_RUNTIME_BOUND",
            {row["check_id"] for row in receipt["checks"]},
        )
        evidence_paths = set(required_gate_evidence_paths("Q4"))
        self.assertIn(
            "trade_system/theory_paper_v2/application/v31_monitor_runtime.py",
            evidence_paths,
        )
        self.assertIn(
            "trade_system/theory_paper_v2/infrastructure/v31_monitor_store.py",
            evidence_paths,
        )
        self.assertIn(
            "tests/test_theory_paper_v2_v31_monitor_runtime.py", evidence_paths
        )

        for field, mutation in (
            (
                "assembly_bundle_contract",
                {
                    "schema_id": "theory_paper_v2_v31_durable_assembly_bundle",
                    "schema_version": "0.9.0",
                    "content_addressed": True,
                    "chat_history_is_authority": False,
                },
            ),
            (
                "checkpoint_contract",
                {
                    "schema_id": "theory_paper_v31_research_checkpoint",
                    "schema_version": "1.1.0",
                    "genesis_bindings_required": False,
                },
            ),
        ):
            manifest = copy.deepcopy(self.manifest)
            manifest[field] = mutation
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    V31ExperimentQualificationError,
                    "Q4_DURABLE_REPLAY_SCOPE_INVALID",
                ):
                    build_typed_qualification_receipt(
                        gate_id="Q4",
                        evaluated_at="2026-08-06T16:04:00Z",
                        experiment_contract=self.contract,
                        manifest=manifest,
                    )

    def test_resigned_check_or_evidence_drift_fails_reconstruction(self) -> None:
        receipt = copy.deepcopy(self.chain["qualification_receipts"]["Q5"])
        receipt["checks"][0]["status"] = "PASS_BUT_UNVERIFIED"
        receipt = self_digest(receipt, "qualification_receipt_digest")
        with self.assertRaisesRegex(
            V31ExperimentQualificationError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_typed_qualification_receipt(
                receipt,
                expected_gate_id="Q5",
                experiment_contract=self.contract,
                manifest=self.manifest,
            )

        evidence_drift = copy.deepcopy(
            self.chain["qualification_receipts"]["Q5"]
        )
        evidence_drift["evidence_bindings"][0]["physical_sha256"] = "f" * 64
        evidence_drift = self_digest(
            evidence_drift, "qualification_receipt_digest"
        )
        with self.assertRaisesRegex(
            V31ExperimentQualificationError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_typed_qualification_receipt(
                evidence_drift,
                expected_gate_id="Q5",
                experiment_contract=self.contract,
                manifest=self.manifest,
            )

    def test_missing_required_implementation_or_test_evidence_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["implementation_bindings"].pop(
            "trade_system/theory_paper_v2/domain/association_estimation.py"
        )
        with self.assertRaisesRegex(
            V31ExperimentQualificationError,
            "REQUIRED_IMPLEMENTATION_OR_TEST_EVIDENCE_MISSING",
        ):
            build_typed_qualification_receipt(
                gate_id="Q5",
                evaluated_at="2026-08-06T16:05:00Z",
                experiment_contract=self.contract,
                manifest=manifest,
            )

    def test_contract_binding_instrument_and_capability_drift_fail(self) -> None:
        mutations = []

        wrong_binding = copy.deepcopy(self.manifest)
        wrong_binding["experiment_contract_binding"]["semantic_digest"] = "0" * 64
        mutations.append(wrong_binding)

        wrong_instrument = copy.deepcopy(self.manifest)
        wrong_instrument["instrument"]["instrument_id"] = "BTC-USDT"
        mutations.append(wrong_instrument)

        wrong_capability = copy.deepcopy(self.manifest)
        moved = wrong_capability["excluded_no_claim_capabilities"].pop(0)
        wrong_capability["experiment_used_capabilities"].append(moved)
        wrong_capability["experiment_used_capabilities"].sort()
        mutations.append(wrong_capability)

        execution_expansion = copy.deepcopy(self.manifest)
        execution_expansion["paper_trading"] = True
        mutations.append(execution_expansion)

        for manifest in mutations:
            with self.subTest(manifest=manifest["instrument"]):
                with self.assertRaises(V31ExperimentQualificationError):
                    build_typed_qualification_receipt(
                        gate_id="Q0",
                        evaluated_at="2026-08-06T16:00:00Z",
                        experiment_contract=self.contract,
                        manifest=manifest,
                    )

    def test_q3_q5_q8_scope_drift_each_fails_closed(self) -> None:
        q3 = copy.deepcopy(self.manifest)
        q3["portfolio_scope"]["next_cycle_portfolio_writeback"] = True

        q5 = copy.deepcopy(self.manifest)
        q5["association_preregistration"]["window"]["sample_count"] = 24

        q8 = copy.deepcopy(self.manifest)
        q8["evaluation_contract"]["excluded_metrics_and_claims"].remove(
            "PROFITABILITY"
        )

        q8_financial = copy.deepcopy(self.manifest)
        q8_financial["portfolio_scope"]["financial_shadow"]["risk_policy"][
            "fee_rate"
        ] = "0"

        for gate_id, manifest in (
            ("Q3", q3),
            ("Q5", q5),
            ("Q8", q8),
            ("Q8", q8_financial),
        ):
            with self.subTest(gate_id=gate_id):
                with self.assertRaisesRegex(
                    V31ExperimentQualificationError,
                    "MANIFEST_CONTRACT_MISMATCH",
                ):
                    build_typed_qualification_receipt(
                        gate_id=gate_id,
                        evaluated_at=f"2026-08-06T16:0{gate_id[1]}:00Z",
                        experiment_contract=self.contract,
                        manifest=manifest,
                    )

    def test_acyclic_subject_ignores_gate_receipts_but_not_scope(self) -> None:
        baseline = manifest_qualification_subject_digest(self.manifest)
        changed_gate_binding = copy.deepcopy(self.manifest)
        changed_gate_binding["qualification_gates"]["Q0"]["receipt_binding"][
            "physical_sha256"
        ] = "f" * 64
        self.assertEqual(
            baseline, manifest_qualification_subject_digest(changed_gate_binding)
        )

        changed_scope = copy.deepcopy(self.manifest)
        changed_scope["cadence_seconds"] = 60
        self.assertNotEqual(
            baseline, manifest_qualification_subject_digest(changed_scope)
        )


if __name__ == "__main__":
    unittest.main()
