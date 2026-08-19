from __future__ import annotations

from copy import deepcopy
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v31_association_preregistration_v2 import (
    build_v31_association_preregistration_v2,
)
from trade_system.theory_paper_v2.domain.v32_association_preregistration import (
    build_v32_association_preregistration,
)
from trade_system.theory_paper_v2.domain.v32_evaluation_contract import (
    V32EvaluationContractError,
    build_v32_current_scope_evaluation_status,
    build_v32_evaluation_contract,
    verify_v32_current_scope_evaluation_status,
    verify_v32_evaluation_contract,
)


RUN_ID = "v32-evaluation-test"


class V32EvaluationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preregistration = build_v32_association_preregistration(
            run_scope_id=RUN_ID,
            frozen_at="2026-08-07T01:00:00Z",
        )
        self.contract = build_v32_evaluation_contract(
            association_preregistration=self.preregistration,
            run_scope_id=RUN_ID,
            frozen_at="2026-08-07T01:01:00Z",
        )

    def test_process_pilot_scope_and_evidence_gates_are_exact(self) -> None:
        scope = self.contract["current_pilot_scope"]
        self.assertEqual(16, scope["analysis_cycle_count"])
        self.assertEqual(48, scope["scheduled_outcome_count"])
        self.assertEqual(["15M", "1H", "4H"], scope["outcome_horizons"])
        self.assertTrue(scope["three_horizons_do_not_create_three_independent_decisions"])

        self.assertEqual(
            240,
            self.contract["predictive_increment"][
                "minimum_resolved_prospective_decisions"
            ],
        )
        self.assertEqual(
            500,
            self.contract["probability_calibration"][
                "minimum_prospective_probability_forecasts"
            ],
        )
        regime = self.contract["cross_regime_generalization"]
        self.assertEqual(480, regime["minimum_resolved_prospective_decisions"])
        self.assertEqual(3, regime["minimum_pre_registered_regimes"])
        self.assertEqual(96, regime["minimum_decisions_per_regime"])
        self.assertEqual(
            self.contract["evaluation_contract_digest"],
            verify_v32_evaluation_contract(self.contract, self.preregistration),
        )

    def test_all_unproven_market_questions_remain_unknown(self) -> None:
        for key in (
            "predictive_increment",
            "probability_calibration",
            "cost_after_return",
            "cross_regime_generalization",
            "association_evaluation",
        ):
            self.assertEqual(
                "UNKNOWN_NOT_EVALUATED", self.contract[key]["current_status"]
            )
            self.assertFalse(self.contract[key]["current_pilot_eligible"])
        self.assertFalse(
            self.contract["probability_calibration"][
                "brier_log_ece_allowed_in_current_pilot"
            ]
        )
        self.assertFalse(self.contract["global_claim_boundary"]["ev_allowed"])

    def test_cost_return_requires_independent_fill_cost_and_episode_contracts(self) -> None:
        cost = self.contract["cost_after_return"]
        self.assertEqual(100, cost["minimum_completed_prospective_episodes"])
        self.assertEqual(4, len(cost["independent_contracts_required"]))
        self.assertIn(
            "LEGAL_FILL_MODEL_OR_OBSERVED_FILL_CONTRACT",
            cost["independent_contracts_required"],
        )
        self.assertFalse(cost["touch_is_fill"])
        self.assertFalse(cost["limit_or_stop_touch_is_realized_pnl"])

    def test_complete_process_counts_do_not_promote_market_claims(self) -> None:
        status = build_v32_current_scope_evaluation_status(
            evaluation_contract=self.contract,
            association_preregistration=self.preregistration,
            accepted_analysis_cycle_count=16,
            terminal_outcome_schedule_count=48,
            assessed_at="2026-08-08T00:00:00Z",
        )
        self.assertTrue(status["current_scope_complete"])
        self.assertEqual("COMPLETE_COUNTS_OBSERVED", status["process_completion_fact"])
        self.assertEqual(
            {"UNKNOWN_NOT_EVALUATED"},
            {item["status"] for item in status["evidence_states"]},
        )
        self.assertIsNone(status["forecast_probability_output"])
        self.assertIsNone(status["brier_log_ece_output"])
        self.assertIsNone(status["ev_output"])
        self.assertEqual(
            status["evaluation_status_digest"],
            verify_v32_current_scope_evaluation_status(
                status, self.contract, self.preregistration
            ),
        )

    def test_impossible_current_counts_fail_closed(self) -> None:
        for accepted, terminal in ((17, 0), (16, 49), (1, 4), (0, 1)):
            with self.subTest(accepted=accepted, terminal=terminal):
                with self.assertRaises(V32EvaluationContractError):
                    build_v32_current_scope_evaluation_status(
                        evaluation_contract=self.contract,
                        association_preregistration=self.preregistration,
                        accepted_analysis_cycle_count=accepted,
                        terminal_outcome_schedule_count=terminal,
                        assessed_at="2026-08-08T00:00:00Z",
                    )

    def test_threshold_or_claim_change_fails_even_after_redigest(self) -> None:
        changed = deepcopy(self.contract)
        changed["predictive_increment"]["minimum_resolved_prospective_decisions"] = 16
        changed["predictive_increment"]["current_status"] = "EVALUATED"
        changed = self_digest(changed, "evaluation_contract_digest")
        with self.assertRaises(V32EvaluationContractError):
            verify_v32_evaluation_contract(changed, self.preregistration)

    def test_status_overclaim_fails_even_after_redigest(self) -> None:
        status = build_v32_current_scope_evaluation_status(
            evaluation_contract=self.contract,
            association_preregistration=self.preregistration,
            accepted_analysis_cycle_count=16,
            terminal_outcome_schedule_count=48,
            assessed_at="2026-08-08T00:00:00Z",
        )
        changed = deepcopy(status)
        changed["evidence_states"][0]["status"] = "PROVEN_INCREMENTAL"
        changed["forecast_probability_output"] = "0.75"
        changed = self_digest(changed, "evaluation_status_digest")
        with self.assertRaises(V32EvaluationContractError):
            verify_v32_current_scope_evaluation_status(
                changed, self.contract, self.preregistration
            )

    def test_noncanonical_time_extra_field_and_pre_freeze_contract_fail(self) -> None:
        changed = deepcopy(self.contract)
        changed["frozen_at"] = "2026-08-07T09:01:00+08:00"
        changed = self_digest(changed, "evaluation_contract_digest")
        with self.assertRaises(V32EvaluationContractError):
            verify_v32_evaluation_contract(changed, self.preregistration)

        extra = deepcopy(self.contract)
        extra["convenience_metric"] = "PROFIT"
        extra = self_digest(extra, "evaluation_contract_digest")
        with self.assertRaises(V32EvaluationContractError):
            verify_v32_evaluation_contract(extra, self.preregistration)

        with self.assertRaises(V32EvaluationContractError):
            build_v32_evaluation_contract(
                association_preregistration=self.preregistration,
                run_scope_id=RUN_ID,
                frozen_at="2026-08-07T00:59:59Z",
            )
        with self.assertRaises(V32EvaluationContractError):
            build_v32_current_scope_evaluation_status(
                evaluation_contract=self.contract,
                association_preregistration=self.preregistration,
                accepted_analysis_cycle_count=0,
                terminal_outcome_schedule_count=0,
                assessed_at="2026-08-07T01:00:59Z",
            )

    def test_v31_eight_cycle_contract_cannot_enter_v32_evaluation(self) -> None:
        legacy = build_v31_association_preregistration_v2(
            run_scope_id=RUN_ID,
            frozen_at="2026-08-07T01:00:00Z",
        )
        with self.assertRaises((V32EvaluationContractError, ValueError)):
            build_v32_evaluation_contract(
                association_preregistration=legacy,
                run_scope_id=RUN_ID,
                frozen_at="2026-08-07T01:01:00Z",
            )


if __name__ == "__main__":
    unittest.main()
