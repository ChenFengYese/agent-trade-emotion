from __future__ import annotations

import unittest
from pathlib import Path

from trade_system.theory_paper.common import digest_json
from trade_system.theory_paper.inference_v2.infrastructure import (
    read_json_object,
)
from trade_system.theory_paper_v2.application.round1_evaluation import (
    ARMS,
    COUNTERFACTUAL_POLICIES,
    build_frozen_cost_policy,
    evaluate_frozen_round1,
)
from trade_system.theory_paper_v2.application.round1_run import (
    execute_frozen_round1,
)


ROOT = Path(__file__).resolve().parents[1]
V1_ROOT = ROOT / ".runtime/theory-paper-v1/current"


@unittest.skipUnless(V1_ROOT.is_dir(), "frozen V1 runtime unavailable")
class Round1EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = read_json_object(V1_ROOT / "manifest.json")
        cls.cost_policy = build_frozen_cost_policy(
            maker_fee_rate="0.0002",
            taker_fee_rate="0.0005",
            market_slippage_bps="2",
            stop_slippage_bps="3",
        )
        cls.frozen_run = execute_frozen_round1(
            run_root=V1_ROOT,
            expected_run_id=manifest["run_id"],
            expected_manifest_digest=digest_json(manifest),
            cost_policy=cls.cost_policy,
        )
        cls.round1_result = cls.frozen_run.evaluation

    def test_exact_a_i_and_shared_point_in_time_bundle(self):
        result = self.round1_result
        self.assertEqual(tuple("ABCDEFGHI"), tuple(ARMS))
        self.assertEqual(9, len(result.arms))
        self.assertEqual(
            {result.point_in_time_bundle_digest},
            {arm.point_in_time_bundle_digest for arm in result.arms},
        )
        self.assertEqual(
            "UNKNOWN_LEGACY_UNDECLARED",
            result.proposal_stream_status,
        )
        self.assertTrue(result.a_replayed_accounting_match)
        self.assertEqual(24, len(result.cycle_ids))

    def test_observed_accounting_is_recomputed_from_committed_stream(self):
        accounting = self.round1_result.a_observed
        self.assertEqual("10000", str(accounting.initial_equity))
        self.assertEqual("9929.53084768", str(accounting.cash_balance))
        self.assertEqual("-65.25657428", str(accounting.realized_pnl_gross))
        self.assertEqual("5.21257804", str(accounting.fees))
        self.assertEqual("-70.46915232", str(accounting.total_net_pnl))
        self.assertEqual(0, accounting.unrealized_pnl)
        self.assertEqual("NOT_SIMULATED_V0_1", accounting.funding_status)

    def test_counterfactuals_preserve_identifiability_boundary(self):
        result = self.round1_result
        self.assertEqual(
            COUNTERFACTUAL_POLICIES,
            tuple(item.policy_id for item in result.counterfactuals),
        )
        thesis = result.counterfactuals[1]
        tactical = result.counterfactuals[2]
        self.assertEqual("SENSITIVITY_ONLY", thesis.identifiability)
        self.assertEqual("PARAMETRIC_ALPHA_UNKNOWN", tactical.identifiability)
        self.assertIsNone(tactical.terminal_mark_net_pnl)

    def test_round_two_does_not_advance_without_identified_i_economics(self):
        first = self.round1_result
        manifest = read_json_object(V1_ROOT / "manifest.json")
        second = evaluate_frozen_round1(
            run_root=V1_ROOT,
            expected_run_id=manifest["run_id"],
            expected_manifest_digest=digest_json(manifest),
            cost_policy=self.cost_policy,
            canonical_scenario_suite_digest=(
                first.canonical_scenario_suite_digest
            ),
            canonical_scenarios_passed=True,
        )
        self.assertEqual(first.result_digest, second.result_digest)
        self.assertEqual("PASS_ENGINEERING", first.hard_functional_gate_status)
        self.assertEqual(
            "INCONCLUSIVE_NOT_IDENTIFIABLE",
            first.behavior_economic_gate_status,
        )
        self.assertEqual("INCONCLUSIVE_NO_ADVANCE", first.terminal_status)
        self.assertIn(
            "I_ARM_ECONOMIC_RESULT_NOT_IDENTIFIABLE",
            first.terminal_reason_codes,
        )

    def test_read_only_run_binds_scenarios_and_preserves_source_tree(self):
        self.assertTrue(self.frozen_run.source_tree_unchanged)
        self.assertEqual(
            self.frozen_run.source_tree_digest_before,
            self.frozen_run.source_tree_digest_after,
        )
        self.assertEqual(32, self.frozen_run.scenario_report.pass_count)
        self.assertEqual(0, self.frozen_run.scenario_report.fail_count)
        self.assertFalse(self.frozen_run.round2_authorized)


if __name__ == "__main__":
    unittest.main()
