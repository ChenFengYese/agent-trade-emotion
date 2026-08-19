from __future__ import annotations

import copy
import unittest
from datetime import UTC, datetime, timedelta

from trade_system.theory_paper_v2.domain.association_estimation import (
    AssociationEstimationError,
    PairedNumericObservation,
    build_association_revision_from_estimate,
    compare_disjoint_association_windows,
    estimate_pearson_association,
    verify_pearson_association_receipt,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest


BASE = datetime(2026, 8, 5, tzinfo=UTC)


def pairs(*, start: int, reverse: bool = False, future: bool = False):
    rows = []
    for index in range(8):
        as_of = BASE + timedelta(hours=start + index)
        available = as_of + timedelta(minutes=1)
        if future and index == 7:
            available = BASE + timedelta(hours=80)
        rows.append(
            PairedNumericObservation(
                pair_id=f"pair:{start}:{index}",
                as_of=as_of.isoformat().replace("+00:00", "Z"),
                available_at=available.isoformat().replace("+00:00", "Z"),
                source_value=str(index + 1),
                target_value=str(8 - index if reverse else index + 1),
                source_datum_digest="a" * 64,
                target_datum_digest="b" * 64,
            )
        )
    return tuple(rows)


def receipt(*, start: int, reverse: bool = False) -> dict:
    return estimate_pearson_association(
        association_id="association:btc-risk",
        source_node_id="node:btc-return",
        target_node_id="node:risk-return",
        decision_at=(BASE + timedelta(hours=start + 8)).isoformat().replace(
            "+00:00", "Z"
        ),
        timeframe="1H",
        observations=pairs(start=start, reverse=reverse),
        multiple_testing_control="SINGLE_PRE_REGISTERED_PAIR",
        limitations=("Synthetic numeric qualification only.",),
    )


class V31AssociationEstimationTests(unittest.TestCase):
    def test_pearson_receipt_is_computed_and_translates_to_noncausal_edge(self) -> None:
        estimated = receipt(start=0)
        self.assertEqual(
            estimated["association_estimation_receipt_digest"],
            verify_pearson_association_receipt(estimated),
        )
        self.assertEqual("1", estimated["estimate"]["point"])
        edge = build_association_revision_from_estimate(
            receipt=estimated,
            dependency_group_ids=("dependency:paired-series",),
            regime_ids=(),
            condition_refs=(),
            limitations=("Pearson association is not causal.",),
        )
        self.assertEqual("OBSERVED_ASSOCIATION", edge["association_type"])
        self.assertEqual("ASSOCIATIONAL_NOT_CAUSAL", edge["interpretation_boundary"])

    def test_future_pair_and_resigned_numeric_tampering_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            AssociationEstimationError, "FUTURE_PAIR_FORBIDDEN"
        ):
            estimate_pearson_association(
                association_id="association:future",
                source_node_id="node:x",
                target_node_id="node:y",
                decision_at=(BASE + timedelta(hours=9)).isoformat().replace(
                    "+00:00", "Z"
                ),
                timeframe="1H",
                observations=pairs(start=0, future=True),
                multiple_testing_control="SINGLE_PRE_REGISTERED_PAIR",
                limitations=("Synthetic test.",),
            )
        forged = copy.deepcopy(receipt(start=0))
        forged.pop("association_estimation_receipt_digest")
        forged["paired_observations"][0]["target_value"] = "999"
        forged = self_digest(forged, "association_estimation_receipt_digest")
        with self.assertRaisesRegex(
            AssociationEstimationError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_pearson_association_receipt(forged)

    def test_change_requires_comparable_disjoint_windows(self) -> None:
        prior = receipt(start=0)
        current = receipt(start=9, reverse=True)
        change = compare_disjoint_association_windows(
            prior_receipt=prior, current_receipt=current
        )
        self.assertEqual("DECREASE_DISTINGUISHED", change["direction_claim"])
        with self.assertRaisesRegex(
            AssociationEstimationError,
            "OVERLAPPING_WINDOWS_REQUIRE_JOINT_ESTIMATOR",
        ):
            compare_disjoint_association_windows(
                prior_receipt=prior, current_receipt=receipt(start=7, reverse=True)
            )


if __name__ == "__main__":
    unittest.main()
