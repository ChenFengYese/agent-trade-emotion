from __future__ import annotations

from copy import deepcopy
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_association_preregistration import (
    CANDIDATE_COUNT,
    V32AssociationPreregistrationError,
    V32_ASSOCIATION_AXES,
    build_v32_association_preregistration,
    verify_v32_association_preregistration,
)


RUN_ID = "v32-association-test"
FROZEN_AT = "2026-08-07T01:02:03Z"


class V32AssociationPreregistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = build_v32_association_preregistration(
            run_scope_id=RUN_ID,
            frozen_at=FROZEN_AT,
        )

    def _resign(self, document: dict) -> dict:
        return self_digest(document, "association_preregistration_digest")

    def test_exact_cartesian_universe_is_frozen(self) -> None:
        self.assertEqual(12, len(V32_ASSOCIATION_AXES))
        self.assertEqual(CANDIDATE_COUNT, len(self.document["candidates"]))
        self.assertEqual(
            CANDIDATE_COUNT,
            len({row["candidate_id"] for row in self.document["candidates"]}),
        )
        combinations = {
            (
                row["source_axis"],
                row["target_id"],
                row["window"]["eligible_pair_count"],
                row["horizon"]["horizon_id"],
            )
            for row in self.document["candidates"]
        }
        self.assertEqual(CANDIDATE_COUNT, len(combinations))
        self.assertEqual({96, 384}, {item[2] for item in combinations})
        self.assertEqual({"15M", "1H", "4H"}, {item[3] for item in combinations})
        self.assertEqual(
            "12_AXES_X_2_TARGETS_X_2_WINDOWS_X_3_HORIZONS",
            self.document["registry_summary"]["cartesian_product_rule"],
        )
        self.assertEqual(
            self.document["association_preregistration_digest"],
            verify_v32_association_preregistration(self.document),
        )

    def test_dependent_families_use_by_and_holm_not_bh(self) -> None:
        self.assertEqual(2, len(self.document["families"]))
        for family in self.document["families"]:
            self.assertEqual(72, family["family_size"])
            self.assertEqual(
                "BENJAMINI_YEKUTIELI_STEP_UP_V1",
                family["fdr_procedure"],
            )
            self.assertEqual("HOLM_STEP_DOWN_V1", family["confirmatory_fwer_procedure"])
            self.assertFalse(family["ordinary_bh_enabled"])
        multiplicity = self.document["multiplicity_contract"]
        self.assertTrue(multiplicity["families_are_dependent"])
        self.assertFalse(multiplicity["ordinary_bh_enabled"])

    def test_pit_missingness_estimator_and_claim_boundaries_are_exact(self) -> None:
        self.assertTrue(self.document["data_contract"]["point_in_time_required"])
        self.assertTrue(self.document["data_contract"]["closed_source_state_only"])
        self.assertEqual(
            "PAIRWISE_COMPLETE_WITHOUT_IMPUTATION",
            self.document["missingness_contract"]["method"],
        )
        self.assertEqual(
            "KENDALL_TAU_B_MOVING_BLOCK_BOOTSTRAP_V1",
            self.document["estimator_contract"]["estimator"],
        )
        boundary = self.document["downstream_boundary"]
        self.assertFalse(boundary["action_input"])
        self.assertFalse(boundary["probability_cloud_input"])
        self.assertFalse(boundary["causal_claim"])
        self.assertFalse(boundary["ev_allowed"])
        self.assertFalse(self.document["executable"])

    def test_candidate_change_after_freeze_fails_even_if_outer_digest_is_rebuilt(self) -> None:
        changed = deepcopy(self.document)
        changed["candidates"][0]["source_axis"] = "POST_HOC_AXIS"
        changed = self._resign(changed)
        with self.assertRaises(V32AssociationPreregistrationError):
            verify_v32_association_preregistration(changed)

    def test_window_horizon_or_lag_change_after_freeze_fails(self) -> None:
        for field, value in (("window", 95), ("horizon", 16), ("lag", 16)):
            with self.subTest(field=field):
                changed = deepcopy(self.document)
                if field == "window":
                    changed["candidates"][0]["window"]["eligible_pair_count"] = value
                elif field == "horizon":
                    changed["candidates"][0]["horizon"]["value"] = value
                else:
                    changed["candidates"][0]["lag"][
                        "forward_target_lag_minutes"
                    ] = value
                changed = self._resign(changed)
                with self.assertRaises(V32AssociationPreregistrationError):
                    verify_v32_association_preregistration(changed)

    def test_multiplicity_cannot_be_switched_to_bh(self) -> None:
        changed = deepcopy(self.document)
        changed["multiplicity_contract"]["primary_fdr"] = (
            "BENJAMINI_HOCHBERG_STEP_UP"
        )
        changed["multiplicity_contract"]["ordinary_bh_enabled"] = True
        changed = self._resign(changed)
        with self.assertRaises(V32AssociationPreregistrationError):
            verify_v32_association_preregistration(changed)

    def test_full_self_digest_laundering_still_fails_reconstruction(self) -> None:
        changed = deepcopy(self.document)
        changed["candidates"].pop()
        changed["registry_summary"]["candidate_count"] = 143
        changed["registry_summary"] = self_digest(
            changed["registry_summary"], "registry_summary_digest"
        )
        changed = self._resign(changed)
        with self.assertRaises(V32AssociationPreregistrationError):
            verify_v32_association_preregistration(changed)

    def test_noncanonical_equivalent_time_and_extra_field_fail(self) -> None:
        changed_time = deepcopy(self.document)
        changed_time["frozen_at"] = "2026-08-07T09:02:03+08:00"
        changed_time = self._resign(changed_time)
        with self.assertRaises(V32AssociationPreregistrationError):
            verify_v32_association_preregistration(changed_time)

        changed_schema = deepcopy(self.document)
        changed_schema["post_hoc_note"] = "harmless-looking"
        changed_schema = self._resign(changed_schema)
        with self.assertRaises(V32AssociationPreregistrationError):
            verify_v32_association_preregistration(changed_schema)

    def test_wrong_instrument_and_naive_time_fail_closed(self) -> None:
        with self.assertRaises(V32AssociationPreregistrationError):
            build_v32_association_preregistration(
                run_scope_id=RUN_ID,
                frozen_at=FROZEN_AT,
                instrument_id="ETH-USDT-SWAP",
            )
        with self.assertRaises(V32AssociationPreregistrationError):
            build_v32_association_preregistration(
                run_scope_id=RUN_ID,
                frozen_at="2026-08-07T01:02:03",
            )


if __name__ == "__main__":
    unittest.main()
