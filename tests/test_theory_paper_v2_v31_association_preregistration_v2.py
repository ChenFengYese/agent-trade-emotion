from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext
import unittest

from trade_system.theory_paper_v2.domain.v31_association_preregistration_v2 import (
    V31AssociationPreregistrationError,
    apply_by_fdr_holm_family_v2,
    build_v31_association_preregistration_v2,
    verify_by_fdr_holm_family_receipt_v2,
    verify_v31_association_preregistration_v2,
)


class V31AssociationPreregistrationV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.preregistration = build_v31_association_preregistration_v2(
            run_scope_id="v31-successor-test",
            frozen_at="2026-08-07T00:00:00Z",
        )
        self.family = self.preregistration["families"][0]
        self.candidates = {
            item["candidate_id"]: item
            for item in self.preregistration["candidates"]
            if item["family_id"] == self.family["family_id"]
        }

    @staticmethod
    def _evaluated_result(candidate: dict, p_value: str) -> dict:
        planned = candidate["window"]["eligible_pair_count"]
        return {
            "candidate_id": candidate["candidate_id"],
            "status": "EVALUATED",
            "eligible_sample_count": planned,
            "observed_sample_count": planned,
            "missing_sample_count": 0,
            "effect_size": "0.2",
            "interval": {
                "kind": "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95_V1",
                "lower": "0.1",
                "upper": "0.3",
                "confidence_level": "0.95",
            },
            "p_value": p_value,
            "unknown_reason": None,
            "upstream_receipt_digest": "a" * 64,
        }

    def _complete_results(self) -> list[dict]:
        ids = sorted(self.candidates)
        rows = []
        for index, candidate_id in enumerate(ids):
            p_value = "0.0001" if index == 0 else "0.0003" if index == 1 else "0.9"
            rows.append(
                self._evaluated_result(self.candidates[candidate_id], p_value)
            )
        return rows

    def test_registry_is_finite_complete_and_deterministic(self) -> None:
        repeated = build_v31_association_preregistration_v2(
            run_scope_id="v31-successor-test",
            frozen_at="2026-08-07T00:00:00Z",
        )
        self.assertEqual(self.preregistration, repeated)
        self.assertEqual(len(self.preregistration["candidates"]), 96)
        self.assertEqual(
            len(
                {
                    item["candidate_id"]
                    for item in self.preregistration["candidates"]
                }
            ),
            96,
        )
        self.assertEqual(
            [item["family_size"] for item in self.preregistration["families"]],
            [48, 48],
        )
        self.assertEqual(
            {
                item["lag"]["value"]
                for item in self.preregistration["candidates"]
            },
            {1, 4},
        )
        self.assertEqual(
            {
                item["window"]["eligible_pair_count"]
                for item in self.preregistration["candidates"]
            },
            {168, 720},
        )
        self.assertEqual(
            self.preregistration["candidate_search"],
            "FORBIDDEN_AFTER_FREEZE",
        )
        self.assertFalse(
            any(
                item["ordinary_bh_exception"]["enabled"]
                for item in self.preregistration["families"]
            )
        )
        self.assertEqual(
            {item["fdr_rank_threshold_rule"] for item in self.preregistration["families"]},
            {"I_TIMES_Q_DIV_M_TIMES_C_M"},
        )
        self.assertEqual(
            {item["holm_rank_threshold_rule"] for item in self.preregistration["families"]},
            {"ALPHA_DIV_M_MINUS_I_PLUS_1"},
        )
        verify_v31_association_preregistration_v2(self.preregistration)

    def test_registry_mutation_or_post_hoc_addition_is_rejected(self) -> None:
        changed = deepcopy(self.preregistration)
        changed["candidates"][0]["lag"]["value"] = 2
        with self.assertRaises(V31AssociationPreregistrationError):
            verify_v31_association_preregistration_v2(changed)

        added = deepcopy(self.preregistration)
        extra = deepcopy(added["candidates"][0])
        extra["candidate_id"] = "POST_HOC_CANDIDATE"
        added["candidates"].append(extra)
        with self.assertRaises(V31AssociationPreregistrationError):
            verify_v31_association_preregistration_v2(added)

    def test_by_and_holm_use_full_dependent_family(self) -> None:
        receipt = apply_by_fdr_holm_family_v2(
            preregistration=self.preregistration,
            family_id=self.family["family_id"],
            candidate_results=list(reversed(self._complete_results())),
            evaluated_at="2026-08-08T00:00:00Z",
        )
        self.assertEqual(receipt["family_size"], 48)
        self.assertEqual(
            receipt["fdr_procedure"],
            "BENJAMINI_YEKUTIELI_STEP_UP_V1",
        )
        self.assertEqual(receipt["dependency_assumption"], "ARBITRARY_DEPENDENCE_ALLOWED")
        self.assertFalse(receipt["ordinary_bh_enabled"])
        self.assertEqual(receipt["critical_rank"], 2)
        self.assertEqual(len(receipt["by_discovery_candidate_ids"]), 2)
        self.assertEqual(len(receipt["holm_confirmed_candidate_ids"]), 2)
        self.assertEqual(
            [item["candidate_id"] for item in receipt["candidate_results"]],
            sorted(self.candidates),
        )
        self.assertTrue(receipt["multiplicity_decision_available"])
        self.assertFalse(receipt["market_discovery_claim_allowed"])

        with localcontext() as context:
            context.prec = 50
            harmonic = sum(
                (Decimal(1) / Decimal(index) for index in range(1, 49)),
                Decimal(0),
            )
            rank_two_threshold = Decimal("0.05") * 2 / (Decimal(48) * harmonic)
        self.assertEqual(Decimal(receipt["harmonic_constant"]), harmonic)
        self.assertLessEqual(Decimal("0.0003"), rank_two_threshold)
        verify_by_fdr_holm_family_receipt_v2(receipt, self.preregistration)

    def test_cross_family_or_incomplete_candidate_set_is_rejected(self) -> None:
        rows = self._complete_results()
        other_family_id = self.preregistration["families"][1]["candidate_ids"][0]
        rows[-1]["candidate_id"] = other_family_id
        with self.assertRaisesRegex(
            V31AssociationPreregistrationError,
            "ASSOCIATION_BH_COMPLETE_CANDIDATE_SET_REQUIRED",
        ):
            apply_by_fdr_holm_family_v2(
                preregistration=self.preregistration,
                family_id=self.family["family_id"],
                candidate_results=rows,
                evaluated_at="2026-08-08T00:00:00Z",
            )

    def test_any_unknown_blocks_entire_family_decision(self) -> None:
        rows = self._complete_results()
        rows[0] = {
            "candidate_id": rows[0]["candidate_id"],
            "status": "UNKNOWN_NOT_EVALUATED",
            "eligible_sample_count": 8,
            "observed_sample_count": 8,
            "missing_sample_count": 0,
            "effect_size": None,
            "interval": None,
            "p_value": None,
            "unknown_reason": "INSUFFICIENT_SAMPLE",
            "upstream_receipt_digest": "b" * 64,
        }
        receipt = apply_by_fdr_holm_family_v2(
            preregistration=self.preregistration,
            family_id=self.family["family_id"],
            candidate_results=rows,
            evaluated_at="2026-08-08T00:00:00Z",
        )
        self.assertEqual(
            receipt["family_status"],
            "UNKNOWN_NOT_EVALUATED_INCOMPLETE_FAMILY",
        )
        self.assertFalse(receipt["multiplicity_decision_available"])
        self.assertEqual(receipt["by_discovery_candidate_ids"], [])
        self.assertTrue(
            all(
                item["by_decision"] == "UNKNOWN_INCOMPLETE_FAMILY"
                and item["holm_decision"] == "UNKNOWN_INCOMPLETE_FAMILY"
                for item in receipt["candidate_results"]
            )
        )
        verify_by_fdr_holm_family_receipt_v2(receipt, self.preregistration)

    def test_binary_float_p_value_is_rejected(self) -> None:
        rows = self._complete_results()
        rows[0]["p_value"] = 0.0001
        with self.assertRaises(V31AssociationPreregistrationError):
            apply_by_fdr_holm_family_v2(
                preregistration=self.preregistration,
                family_id=self.family["family_id"],
                candidate_results=rows,
                evaluated_at="2026-08-08T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
