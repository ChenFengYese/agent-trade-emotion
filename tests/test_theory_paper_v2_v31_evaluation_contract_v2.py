from __future__ import annotations

from copy import deepcopy
import unittest

from trade_system.theory_paper_v2.domain.v31_association_preregistration_v2 import (
    build_v31_association_preregistration_v2,
)
from trade_system.theory_paper_v2.domain.v31_evaluation_contract_v2 import (
    V31EvaluationContractError,
    build_current_scope_evaluation_status_v2,
    build_v31_evaluation_contract_v2,
    verify_current_scope_evaluation_status_v2,
    verify_v31_evaluation_contract_v2,
)


class V31EvaluationContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.preregistration = build_v31_association_preregistration_v2(
            run_scope_id="v31-successor-test",
            frozen_at="2026-08-07T00:00:00Z",
        )
        self.contract = build_v31_evaluation_contract_v2(
            association_preregistration=self.preregistration,
            run_scope_id="v31-successor-test",
            frozen_at="2026-08-07T00:00:01Z",
        )

    def test_contract_freezes_unknown_and_excluded_boundaries(self) -> None:
        self.assertEqual(
            self.contract["predictive_increment"]["current_status"],
            "UNKNOWN_NOT_EVALUATED",
        )
        self.assertEqual(
            self.contract["probability_calibration"]["current_status"],
            "NOT_APPLICABLE_ORDINAL_ONLY",
        )
        self.assertFalse(
            self.contract["probability_calibration"]["brier_log_ece_allowed_now"]
        )
        self.assertEqual(
            self.contract["cost_after_return"]["current_claim_scope"],
            "EXCLUDED_NO_CLAIM",
        )
        self.assertEqual(
            self.contract["cross_regime_generalization"]["current_status"],
            "UNKNOWN_NOT_EVALUATED",
        )
        self.assertFalse(
            self.contract["association_evaluation"]["ordinary_bh_enabled"]
        )
        self.assertEqual(
            self.contract["portfolio_and_reentry_boundary"],
            {
                "portfolio": "EXCLUDED_NO_CLAIM",
                "reentry": "EXCLUDED_NO_CLAIM",
                "static_flat_shadow": "ALLOWED_CONTEXT_ONLY",
                "portfolio_writeback": False,
                "portfolio_performance_claim": False,
                "reentry_performance_claim": False,
            },
        )
        self.assertFalse(self.contract["global_claim_boundary"]["ev_allowed"])
        verify_v31_evaluation_contract_v2(
            self.contract, self.preregistration
        )

    def test_eight_of_eight_still_cannot_promote_market_claims(self) -> None:
        status = build_current_scope_evaluation_status_v2(
            evaluation_contract=self.contract,
            association_preregistration=self.preregistration,
            accepted_cycle_count=8,
            resolved_outcome_count=8,
            assessed_at="2026-08-08T12:00:00Z",
        )
        self.assertTrue(status["current_scope_complete"])
        states = {item["question"]: item for item in status["evidence_states"]}
        self.assertEqual(
            states["PREDICTIVE_INCREMENT"]["status"],
            "UNKNOWN_NOT_EVALUATED",
        )
        self.assertEqual(
            states["PROBABILITY_CALIBRATION"]["status"],
            "NOT_APPLICABLE_ORDINAL_ONLY",
        )
        self.assertEqual(
            states["COST_AFTER_RETURN"]["claim_scope"],
            "EXCLUDED_NO_CLAIM",
        )
        self.assertEqual(
            states["CROSS_REGIME_GENERALIZATION"]["status"],
            "UNKNOWN_NOT_EVALUATED",
        )
        self.assertEqual(
            states["ASSOCIATION_FAMILY_DISCOVERY"]["status"],
            "UNKNOWN_NOT_EVALUATED",
        )
        self.assertIsNone(status["forecast_probability_output"])
        self.assertIsNone(status["ev_output"])
        self.assertFalse(status["local_contract_pass_may_promote_market_claim"])
        verify_current_scope_evaluation_status_v2(
            status, self.contract, self.preregistration
        )

    def test_current_scope_cannot_be_expanded_by_count_only(self) -> None:
        with self.assertRaisesRegex(
            V31EvaluationContractError,
            "EVALUATION_CURRENT_SCOPE_COUNT_OUT_OF_RANGE",
        ):
            build_current_scope_evaluation_status_v2(
                evaluation_contract=self.contract,
                association_preregistration=self.preregistration,
                accepted_cycle_count=9,
                resolved_outcome_count=9,
                assessed_at="2026-08-08T12:00:00Z",
            )

    def test_contract_or_status_tampering_is_rejected(self) -> None:
        changed_contract = deepcopy(self.contract)
        changed_contract["predictive_increment"][
            "minimum_resolved_prospective_outcomes"
        ] = 8
        with self.assertRaises(V31EvaluationContractError):
            verify_v31_evaluation_contract_v2(
                changed_contract, self.preregistration
            )

        status = build_current_scope_evaluation_status_v2(
            evaluation_contract=self.contract,
            association_preregistration=self.preregistration,
            accepted_cycle_count=8,
            resolved_outcome_count=8,
            assessed_at="2026-08-08T12:00:00Z",
        )
        status["evidence_states"][0]["status"] = "VALIDATED"
        with self.assertRaises(V31EvaluationContractError):
            verify_current_scope_evaluation_status_v2(
                status, self.contract, self.preregistration
            )

    def test_evaluation_contract_cannot_precede_preregistration(self) -> None:
        with self.assertRaisesRegex(
            V31EvaluationContractError,
            "EVALUATION_PRECEDES_ASSOCIATION_PREREGISTRATION",
        ):
            build_v31_evaluation_contract_v2(
                association_preregistration=self.preregistration,
                run_scope_id="v31-successor-test",
                frozen_at="2026-08-06T23:59:59Z",
            )


if __name__ == "__main__":
    unittest.main()
