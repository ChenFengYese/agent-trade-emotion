from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.formal_experiment import (
    FORMAL_E0_CONTRACT_DIGEST,
    FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST,
    DatasetManifestRef,
    FormalExperimentError,
    PairedObservationReceipt,
    build_paired_observation_receipt,
    execute_formal_experiment,
)
from trade_system.theory_paper_v2.application.generative_topology_run import (
    ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA,
)
from trade_system.theory_paper_v2.application.topology_evaluation import (
    TOPOLOGY_IDS,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    load_json_strict,
    write_once_json,
)
from trade_system.theory_paper_v2.infrastructure.formal_experiment_store import (
    FormalExperimentStoreError,
    load_formal_experiment_contract,
    load_paired_observation_receipt,
    materialize_formal_experiment,
)
from trade_system.theory_paper_v2.presentation.formal_report import (
    build_formal_experiment_markdown_zh,
)


CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "theory_agent_v2.formal_e0_experiment.v1.json"
)


def _dataset(
    *,
    transport_verdict: str = "PASS",
    transport_digest: str = (
        FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST
    ),
) -> DatasetManifestRef:
    return DatasetManifestRef(
        dataset_id="frozen-datasets/btcusdt-1h-256-20260731",
        dataset_digest="d" * 64,
        quality_verdict="PASS",
        decision_slot_count=96,
        transport_contract_verdict=transport_verdict,
        transport_schema_digest=transport_digest,
    )


def _receipt(
    *,
    cohort: str,
    index: int,
    topology_id: str,
    ordinal: int,
) -> PairedObservationReceipt:
    if topology_id == "SINGLE_STRONG":
        coverage, challenge, quality = "0.50", "0.40", "0.10"
    elif topology_id == "CLUSTER_POST_PROPOSAL":
        coverage, challenge, quality = "0.70", "0.70", "0.95"
    else:
        coverage, challenge, quality = "0.51", "0.41", "0.20"
    formal = cohort == "FORMAL_EXPERIMENT"
    return build_paired_observation_receipt(
        session_id=f"{cohort.casefold()}-{index:03d}",
        topology_id=topology_id,
        input_digest=f"{index:064x}",
        model_class="REQUESTED_GPT_5_6_SOL",
        total_budget_digest="b" * 64,
        dynamic_candidate_coverage=Decimal(coverage),
        material_challenge_coverage=Decimal(challenge),
        action_quality_score=Decimal(quality),
        safety_state_pit_authority_failures=0,
        role_overreach_failures=0,
        model_calls=1 if topology_id == "SINGLE_STRONG" else 3,
        tokens=3_000,
        latency_ms=1_000,
        cost_microunits=None,
        timeout_count=0,
        missing_role_count=0,
        sample_index=index,
        sample_cohort=cohort,
        qualification_verdict=(
            "PASS" if cohort == "POLICY_QUALIFICATION"
            else "NOT_APPLICABLE"
        ),
        formal_evidence=True,
        requested_model="gpt-5.6-sol",
        served_model_attestation=None,
        served_model_attestation_status=(
            "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT"
        ),
        parameter_digest="a" * 64,
        budget_limit_digest="c" * 64,
        transport_contract_verdict="PASS",
        transport_schema_digest=(
            FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST
        ),
        dataset_digest="d" * 64,
        formal_contract_digest=FORMAL_E0_CONTRACT_DIGEST,
        scoring_policy_digest="1" * 64,
        cost_policy_digest="2" * 64,
        initial_account_digest="3" * 64,
        termination_policy_digest="4" * 64,
        raw_input_ref=(
            f"runs/source-{index:03d}/shared/common-context.json"
        ),
        raw_output_refs=(
            (
                f"runs/source-{index:03d}/outputs/"
                f"{cohort.casefold()}-{topology_id.casefold()}-{ordinal}.json"
            ),
        ),
        usage_receipt_digest=f"{ordinal + 1:064x}",
        hard_constraint_error_count=0,
        state_continuity_error_count=0,
        reproducibility_difference_count=0,
        net_pnl_after_cost=Decimal("0.02") if formal else None,
        transaction_cost=Decimal("0.001") if formal else None,
        max_drawdown_fraction=Decimal("0.01") if formal else None,
        primary_path_capture=Decimal("0.80") if formal else None,
        frozen_baseline_net_pnl_after_cost=(
            Decimal("0.01") if formal else None
        ),
        frozen_baseline_max_drawdown_fraction=(
            Decimal("0.012") if formal else None
        ),
        frozen_baseline_primary_path_capture=(
            Decimal("0.50") if formal else None
        ),
    )


def _receipts() -> tuple[PairedObservationReceipt, ...]:
    rows: list[PairedObservationReceipt] = []
    ordinal = 0
    for index in range(96, 128):
        for topology_id in TOPOLOGY_IDS:
            rows.append(
                _receipt(
                    cohort="TOPOLOGY_SELECTION",
                    index=index,
                    topology_id=topology_id,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
    for cohort, indices in (
        ("POLICY_QUALIFICATION", range(128, 160)),
        ("FORMAL_EXPERIMENT", range(160, 192)),
    ):
        for index in indices:
            rows.append(
                _receipt(
                    cohort=cohort,
                    index=index,
                    topology_id="CLUSTER_POST_PROPOSAL",
                    ordinal=ordinal,
                )
            )
            ordinal += 1
    return tuple(rows)


def _execute(
    receipts: tuple[PairedObservationReceipt, ...] | None = None,
    dataset: DatasetManifestRef | None = None,
):
    return execute_formal_experiment(
        offline_run_id="formal-e0-test-20260731",
        contract=load_formal_experiment_contract(CONTRACT_PATH),
        dataset_manifest_ref=dataset or _dataset(),
        receipts=receipts or _receipts(),
        scoring_policy_digest="1" * 64,
        cost_policy_digest="2" * 64,
        initial_account_digest="3" * 64,
        termination_policy_digest="4" * 64,
    )


class FormalExperimentTests(unittest.TestCase):
    def test_frozen_contract_and_transport_repair_digest_are_exact(self):
        contract = load_formal_experiment_contract(CONTRACT_PATH)
        self.assertEqual(FORMAL_E0_CONTRACT_DIGEST, contract.contract_digest)
        self.assertEqual(tuple(range(96, 128)), contract.topology_selection_indices)
        self.assertEqual(tuple(range(128, 160)), contract.policy_qualification_indices)
        self.assertEqual(tuple(range(160, 192)), contract.formal_experiment_indices)
        self.assertEqual(
            FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST,
            canonical_digest(ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA),
        )

    def test_full_three_phase_formal_run_is_repeatable_and_never_creates_round2(self):
        result = _execute()
        self.assertEqual(160, result.receipt_count)
        self.assertEqual(
            "CLUSTER_POST_PROPOSAL",
            result.topology_evaluation.selected_topology_id,
        )
        self.assertEqual("PASS", result.behavior_metrics.gate_status)
        self.assertEqual("PASS", result.risk_metrics.gate_status)
        self.assertEqual("PASS", result.profit_metrics.gate_status)
        self.assertEqual("PASS_FORMAL_E0", result.terminal_status)
        self.assertEqual(
            result.first_evaluation_summary_digest,
            result.second_evaluation_summary_digest,
        )
        self.assertTrue(result.deterministic_repeat_match)
        self.assertFalse(result.round2_instance_created)
        self.assertEqual(
            "PASS_SEPARATE_101_GATE_ELIGIBLE",
            result.round2_precondition_status,
        )

    def test_missing_formal_paired_evidence_fails_closed(self):
        receipts = _receipts()
        with self.assertRaisesRegex(
            FormalExperimentError,
            "TOPOLOGY_SELECTION_OBSERVATION_SET_INCOMPLETE",
        ):
            _execute(receipts=receipts[1:])

    def test_run_id_cannot_escape_write_once_root(self):
        with self.assertRaisesRegex(
            FormalExperimentError,
            "EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED",
        ):
            execute_formal_experiment(
                offline_run_id="../escape",
                contract=load_formal_experiment_contract(CONTRACT_PATH),
                dataset_manifest_ref=_dataset(),
                receipts=_receipts(),
                scoring_policy_digest="1" * 64,
                cost_policy_digest="2" * 64,
                initial_account_digest="3" * 64,
                termination_policy_digest="4" * 64,
            )

    def test_legacy_or_unbound_role_transport_fails_closed(self):
        with self.assertRaisesRegex(
            FormalExperimentError,
            "ROLE_INPUT_TRANSPORT_CONTRACT_INVALID",
        ):
            _execute(dataset=_dataset(transport_digest="e" * 64))

    def test_receipt_cannot_be_reused_across_frozen_policy_or_dataset(self):
        receipts = list(_receipts())
        payload = receipts[0].digest_payload()
        payload["scoring_policy_digest"] = "f" * 64
        receipts[0] = build_paired_observation_receipt(**payload)
        with self.assertRaisesRegex(
            FormalExperimentError,
            "FORMAL_RECEIPT_FROZEN_BINDING_MISMATCH",
        ):
            _execute(receipts=tuple(receipts))

    def test_distinct_indices_cannot_reuse_one_decision_input(self):
        receipts = list(_receipts())
        for position, item in enumerate(receipts):
            if (
                item.sample_cohort == "TOPOLOGY_SELECTION"
                and item.sample_index == 97
            ):
                payload = item.digest_payload()
                payload.update(
                    input_digest=f"{96:064x}",
                    raw_input_ref=(
                        "runs/source-096/shared/common-context.json"
                    ),
                    session_id="topology_selection-096",
                )
                receipts[position] = build_paired_observation_receipt(
                    **payload
                )
        with self.assertRaisesRegex(
            FormalExperimentError,
            "FORMAL_DECISION_SAMPLE_REUSED",
        ):
            _execute(receipts=tuple(receipts))

    def test_nonformal_economic_unknown_is_null_but_formal_requires_values(self):
        row = _receipt(
            cohort="TOPOLOGY_SELECTION",
            index=96,
            topology_id="SINGLE_STRONG",
            ordinal=0,
        )
        self.assertIsNone(row.net_pnl_after_cost)
        fields = row.digest_payload()
        fields.update(
            sample_cohort="FORMAL_EXPERIMENT",
            sample_index=160,
        )
        with self.assertRaisesRegex(
            FormalExperimentError,
            "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
        ):
            build_paired_observation_receipt(**fields)

    def test_formal_window_cannot_reselect_topology(self):
        receipts = list(_receipts())
        for position, item in enumerate(receipts):
            if item.sample_cohort == "FORMAL_EXPERIMENT":
                payload = item.digest_payload()
                payload["action_quality_score"] = Decimal("0")
                receipts[position] = build_paired_observation_receipt(
                    **payload
                )
        result = _execute(receipts=tuple(receipts))
        self.assertEqual(
            "CLUSTER_POST_PROPOSAL",
            result.topology_evaluation.selected_topology_id,
        )

    def test_receipt_loader_preserves_null_unknown_and_verifies_digest(self):
        row = _receipt(
            cohort="TOPOLOGY_SELECTION",
            index=96,
            topology_id="SINGLE_STRONG",
            ordinal=0,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            write_once_json(path, asdict(row))
            loaded = load_paired_observation_receipt(path)
            self.assertEqual(row, loaded)
            self.assertIsNone(loaded.served_model_attestation)
            self.assertIsNone(loaded.net_pnl_after_cost)

    def test_write_once_run_contains_all_required_artifacts_and_no_round2(self):
        receipts = _receipts()
        result = _execute(receipts=receipts)
        report = build_formal_experiment_markdown_zh(result)
        with tempfile.TemporaryDirectory() as directory:
            first = materialize_formal_experiment(
                runtime_root=Path(directory),
                result=result,
                receipts=receipts,
                report_markdown=report,
            )
            second = materialize_formal_experiment(
                runtime_root=Path(directory),
                result=result,
                receipts=receipts,
                report_markdown=report,
            )
            self.assertEqual(
                first.artifact_index_digest,
                second.artifact_index_digest,
            )
            self.assertTrue(first.manifest_path.is_file())
            self.assertTrue(first.authority_snapshot_path.is_file())
            self.assertTrue(first.result_path.is_file())
            self.assertTrue(first.markdown_path.is_file())
            self.assertFalse((first.run_root / "round2").exists())
            index = load_json_strict(first.artifact_index_path)
            indexed = {
                item["relative_path"] for item in index["entries"]
            }
            self.assertIn(
                "artifacts/topology-evaluation.json",
                indexed,
            )
            self.assertIn("artifacts/behavior-metrics.json", indexed)
            self.assertIn("artifacts/risk-metrics.json", indexed)
            self.assertIn("artifacts/profit-metrics.json", indexed)
            self.assertIn(
                "reports/zh/formal-e0-experiment.md",
                indexed,
            )
            with self.assertRaisesRegex(
                FormalExperimentStoreError,
                "WRITE_ONCE_CONFLICT",
            ):
                materialize_formal_experiment(
                    runtime_root=Path(directory),
                    result=result,
                    receipts=receipts,
                    report_markdown=report + "\n后见修改",
                )


if __name__ == "__main__":
    unittest.main()
