from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from trade_system.theory_paper_v2.application.round1_evaluation import (
    ARMS,
    ArmEvaluation,
    CounterfactualEvaluation,
    IdentifiedAccounting,
    Round1EvaluationResult,
)
from trade_system.theory_paper_v2.application.round1_run import (
    FrozenRound1RunResult,
)
from trade_system.theory_paper_v2.application.runtime import (
    OfflineRunManifestInput,
    initialize_offline_runtime,
)
from trade_system.theory_paper_v2.application.scenarios import (
    run_canonical_scenarios,
)
from trade_system.theory_paper_v2.application.topology_evaluation import (
    evaluate_agent_topologies,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    write_once_json,
)
from trade_system.theory_paper_v2.domain.contracts.validation import (
    validate_schema_value,
)
from trade_system.theory_paper_v2.presentation.report import (
    PresentationError,
    build_round1_markdown_zh,
    materialize_round1_report,
)


ROOT = Path(__file__).resolve().parents[1]


def _result() -> FrozenRound1RunResult:
    scenarios = run_canonical_scenarios()
    accounting = IdentifiedAccounting(
        initial_equity=Decimal("10000"),
        cash_balance=Decimal("9929.53084768"),
        realized_pnl_gross=Decimal("-65.25657428"),
        fees=Decimal("5.21257804"),
        net_realized_pnl=Decimal("-70.46915232"),
        unrealized_pnl=Decimal("0"),
        total_net_pnl=Decimal("-70.46915232"),
        max_drawdown_fraction=Decimal("0.00704692"),
        fill_count=32,
        funding_status="NOT_SIMULATED_V0_1",
    )
    arms = tuple(
        ArmEvaluation(
            arm_id=arm_id,
            enabled_features=features,
            point_in_time_bundle_digest="1" * 64,
            candidate_proposal_stream_digest=None,
            functional_status="PASS_SYNTHETIC_CONTRACT",
            economic_status=(
                "IDENTIFIED_OBSERVED"
                if arm_id == "A"
                else "UNKNOWN_LEGACY_UNDECLARED"
            ),
            accounting=accounting if arm_id == "A" else None,
            primary_path_capture=None,
            unknown_fields=(
                ()
                if arm_id == "A"
                else ("complete_candidate_proposal_stream",)
            ),
        )
        for arm_id, features in ARMS.items()
    )
    counterfactuals = (
        CounterfactualEvaluation(
            policy_id="ORIGINAL_AGENT_RULES",
            identifiability="IDENTIFIED_CONTROL",
            result_status="EXACT",
            terminal_mark_net_pnl=Decimal("1"),
            hypothetical_exit_net_pnl=Decimal("1"),
            formula=None,
            notes=(),
        ),
    )
    evaluation = Round1EvaluationResult(
        legacy_run_id="legacy-run",
        cycle_ids=tuple(f"cycle-{index:04d}" for index in range(1, 25)),
        point_in_time_bundle_digest="1" * 64,
        chronology_digest="2" * 64,
        cost_policy_digest="3" * 64,
        proposal_stream_status="UNKNOWN_LEGACY_UNDECLARED",
        candidate_proposal_stream_digest=None,
        a_observed=accounting,
        a_replayed_accounting_match=True,
        a_replayed_action_fill_identity_match=True,
        arms=arms,
        counterfactuals=counterfactuals,
        canonical_scenario_suite_digest=scenarios.report_digest,
        canonical_scenarios_passed=True,
        hard_functional_gate_status="PASS_ENGINEERING",
        behavior_economic_gate_status="INCONCLUSIVE_NOT_IDENTIFIABLE",
        terminal_status="INCONCLUSIVE_NO_ADVANCE",
        terminal_reason_codes=(
            "I_ARM_ECONOMIC_RESULT_NOT_IDENTIFIABLE",
        ),
        result_digest="4" * 64,
    )
    return FrozenRound1RunResult(
        source_tree_digest_before="5" * 64,
        source_tree_digest_after="5" * 64,
        source_tree_unchanged=True,
        scenario_report=scenarios,
        evaluation=evaluation,
        topology_evaluation=evaluate_agent_topologies(()),
        round2_authorized=False,
        round2_status="NOT_AUTHORIZED",
        run_result_digest="6" * 64,
    )


class PresentationTests(unittest.TestCase):
    def _runtime(self, root: Path) -> None:
        initialize_offline_runtime(
            root,
            OfflineRunManifestInput(
                offline_run_id="round1-test",
                theory_contract_digest="1" * 64,
                code_digest="2" * 64,
                schema_bundle_digest="3" * 64,
                policy_digest="4" * 64,
                dataset_digest="5" * 64,
                automation_status_observed="PAUSED",
                authority_snapshot_digest="6" * 64,
                cluster_bootstrap_receipt_digest="7" * 64,
                project_state_genesis_contract_digest="8" * 64,
            ),
        )

    def test_markdown_states_inconclusive_boundary(self) -> None:
        markdown = build_round1_markdown_zh(_result())
        self.assertIn("INCONCLUSIVE_NO_ADVANCE", markdown)
        self.assertIn("第二轮授权：`false`", markdown)
        self.assertIn("机会差额不计入实际现金亏损", markdown)
        self.assertIn("不能确认 B–I 的经济改进", markdown)

    def test_materialization_is_write_once_and_schema_bound(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            runtime = Path(raw)
            self._runtime(runtime)
            write_once_json(
                runtime / "round1-test/bootstrap/test.json",
                {"kind": "BOUND_BOOTSTRAP_FIXTURE"},
            )
            first = materialize_round1_report(
                runtime_root=runtime,
                offline_run_id="round1-test",
                result=_result(),
            )
            second = materialize_round1_report(
                runtime_root=runtime,
                offline_run_id="round1-test",
                result=_result(),
            )
            self.assertEqual(
                first.artifact_index_digest,
                second.artifact_index_digest,
            )
            index = load_json_strict(first.artifact_index_path)
            indexed = {item["relative_path"] for item in index["entries"]}
            self.assertIn("bootstrap/test.json", indexed)
            self.assertIn(
                "reports/zh/round1-frozen-evaluation.md",
                indexed,
            )
            for name, schema_id in (
                ("hard-gate-result.json", "hard_gate_result"),
                ("ablation-result.json", "ablation_result"),
                ("gap-report.json", "evaluation_snapshot"),
                ("compatibility-report.json", "evaluation_snapshot"),
                ("residual-risk-report.json", "evaluation_snapshot"),
            ):
                value = load_json_strict(
                    first.run_root / "artifacts" / name
                )
                schema = load_json_strict(
                    ROOT
                    / "agent-cluster/contracts/schemas"
                    / f"{schema_id}.schema.json"
                )
                validate_schema_value(value, schema)

    def test_changed_result_cannot_overwrite_frozen_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            runtime = Path(raw)
            self._runtime(runtime)
            result = _result()
            materialize_round1_report(
                runtime_root=runtime,
                offline_run_id="round1-test",
                result=result,
            )
            with self.assertRaisesRegex(
                (PresentationError, ValueError),
                "WRITE_ONCE_CONFLICT",
            ):
                materialize_round1_report(
                    runtime_root=runtime,
                    offline_run_id="round1-test",
                    result=replace(
                        result,
                        run_result_digest="7" * 64,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
