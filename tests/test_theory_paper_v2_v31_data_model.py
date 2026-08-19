from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_system.theory_paper_v2.domain.data_model import (
    ConflictState,
    DataModelError,
    DataQuality,
    DatumEpistemicType,
    DatumValueType,
    Missingness,
    PointInTimeDatum,
    ProxyLevel,
    QualityLevel,
    UncertaintyKind,
    UncertaintyRepresentation,
    admit_point_in_time_dataset,
    build_point_in_time_datum_revision_registry,
)


DECISION = datetime(2026, 8, 6, 10, tzinfo=UTC)


def quality() -> DataQuality:
    return DataQuality(
        source_reliability=QualityLevel.HIGH,
        completeness=QualityLevel.MEDIUM,
        timeliness=QualityLevel.HIGH,
        semantic_fidelity=QualityLevel.HIGH,
        measurement_error=QualityLevel.MEDIUM,
        revision_risk=QualityLevel.LOW,
        cross_source_consistency=QualityLevel.UNKNOWN,
        lineage_integrity=QualityLevel.HIGH,
        dependency_independence=QualityLevel.MEDIUM,
        regime_applicability=QualityLevel.UNKNOWN,
        limitations=("single venue",),
    )


def observed(*, datum_id: str = "mark-price", value: str | None = "65000") -> PointInTimeDatum:
    return PointInTimeDatum(
        datum_id=datum_id,
        epistemic_type=DatumEpistemicType.OBSERVED_FACT,
        data_kind="MARKET_FACT",
        category="PRICE_AND_RETURNS",
        metric="MARK_PRICE",
        value=value,
        value_type=DatumValueType.NUMERIC,
        unit="USDT_PER_BTC",
        currency="USDT",
        frequency="SNAPSHOT",
        timeframe="INSTANT",
        window="POINT",
        instrument_id="BTC-USDT-SWAP",
        asset_class="CRYPTO_DERIVATIVE",
        venue_id="OKX",
        entity_ids=(),
        actor_ids=("okx-market-data",),
        audience_ids=(),
        event_ids=(),
        source_id="okx-public-api",
        source_type="PRIMARY_MARKET_DATA",
        source_ref="capture:mark",
        raw_ref="raw/mark.json",
        raw_sha256="a" * 64,
        as_of=DECISION - timedelta(seconds=2),
        observed_at=DECISION - timedelta(seconds=2),
        published_at=DECISION - timedelta(seconds=1),
        available_at=DECISION,
        effective_at=None,
        revised_at=None,
        vintage_id="2026-08-06T10:00Z",
        revision=1,
        revision_of_digest=None,
        formula_version=None,
        input_refs=(),
        input_digests=(),
        quality=quality(),
        coverage=Decimal("0.9333"),
        missingness=(Missingness.OBSERVED if value is not None else Missingness.UNKNOWN),
        missing_reason=(None if value is not None else "SOURCE_UNAVAILABLE"),
        staleness="2s",
        conflict_state=ConflictState.NONE,
        proxy_level=ProxyLevel.DIRECT,
        uncertainty=UncertaintyRepresentation(kind=UncertaintyKind.NONE_DECLARED),
        regime_ref=None,
        dependency_group="OKX_MARK",
        lineage=("capture:mark",),
        limitations=("single venue",),
    )


class PointInTimeDataModelTests(unittest.TestCase):
    def test_complete_datum_contract_and_dataset_digest(self) -> None:
        row = observed()
        document = admit_point_in_time_dataset(
            dataset_id="dataset-1", decision_at=DECISION, data=(row,)
        )
        self.assertEqual(1, document["observed_count"])
        self.assertEqual(0, document["unknown_count"])
        self.assertFalse(document["missing_is_zero"])
        self.assertEqual(64, len(document["dataset_digest"]))
        self.assertEqual("0.9333", document["data"][0]["coverage"])

    def test_missing_value_stays_unknown_and_requires_reason(self) -> None:
        missing = observed(datum_id="liquidations", value=None)
        document = missing.to_document()
        self.assertIsNone(document["value"])
        self.assertEqual("UNKNOWN", document["missingness"])
        with self.assertRaisesRegex(DataModelError, "DATA_MISSINGNESS_CONTRACT_INVALID"):
            replace(missing, missing_reason=None)

    def test_derived_measure_requires_formula_and_input_lineage(self) -> None:
        base = observed()
        with self.assertRaisesRegex(DataModelError, "DATA_DERIVED_LINEAGE_REQUIRED"):
            replace(
                base,
                datum_id="return-1h",
                epistemic_type=DatumEpistemicType.DERIVED_MEASURE,
                raw_ref=None,
                raw_sha256=None,
            )
        derived = replace(
            base,
            datum_id="return-1h",
            epistemic_type=DatumEpistemicType.DERIVED_MEASURE,
            metric="RETURN_1H",
            value="0.5",
            unit="PERCENT",
            raw_ref=None,
            raw_sha256=None,
            formula_version="return-v1",
            input_refs=("close-t", "close-t-1"),
            input_digests=("c" * 64, "d" * 64),
            proxy_level=ProxyLevel.MODEL_DERIVED,
            uncertainty=UncertaintyRepresentation(
                kind=UncertaintyKind.INTERVAL, lower="0.45", upper="0.55"
            ),
            )
        self.assertEqual("DERIVED_MEASURE", derived.to_document()["epistemic_type"])
        with self.assertRaisesRegex(DataModelError, "DATASET_DERIVED_INPUT_MISSING"):
            admit_point_in_time_dataset(
                dataset_id="orphan-derived", decision_at=DECISION, data=(derived,)
            )

    def test_future_available_data_fail_closed(self) -> None:
        row = replace(observed(), available_at=DECISION + timedelta(microseconds=1))
        with self.assertRaisesRegex(DataModelError, "DATASET_FUTURE_INFORMATION_FORBIDDEN"):
            admit_point_in_time_dataset(
                dataset_id="future", decision_at=DECISION, data=(row,)
            )

    def test_revision_is_digest_bound_and_does_not_overwrite_prior(self) -> None:
        prior = observed()
        revised = replace(
            prior,
            revision=2,
            revision_of_digest=prior.to_document()["datum_digest"],
            value="65001",
            observed_at=DECISION + timedelta(seconds=45),
            published_at=DECISION + timedelta(seconds=30),
            available_at=DECISION + timedelta(minutes=1),
            revised_at=DECISION + timedelta(seconds=30),
            vintage_id="2026-08-06T10:01Z",
        )
        document = admit_point_in_time_dataset(
            dataset_id="revision",
            decision_at=DECISION + timedelta(minutes=1),
            data=(revised,),
            prior_revisions={prior.datum_id: prior},
        )
        self.assertEqual(2, document["data"][0]["revision"])
        with self.assertRaisesRegex(DataModelError, "DATASET_REVISION_DIGEST_MISMATCH"):
            admit_point_in_time_dataset(
                dataset_id="bad-revision",
                decision_at=DECISION + timedelta(minutes=1),
                data=(replace(revised, revision_of_digest="b" * 64),),
                prior_revisions={prior.datum_id: prior},
            )

    def test_clock_order_and_hex_bindings_fail_closed(self) -> None:
        with self.assertRaisesRegex(DataModelError, "DATA_AVAILABLE_PRECEDES_OBSERVATION"):
            replace(
                observed(),
                observed_at=DECISION + timedelta(seconds=1),
                available_at=DECISION,
            )
        with self.assertRaisesRegex(DataModelError, "DATA_RAW_BINDING_INVALID"):
            replace(observed(), raw_sha256="z" * 64)
        with self.assertRaisesRegex(DataModelError, "DATA_PRIOR_REVISION_DIGEST_REQUIRED"):
            replace(
                observed(),
                revision=2,
                revision_of_digest="z" * 64,
                revised_at=DECISION - timedelta(seconds=2),
            )

    def test_revision_cannot_change_semantic_identity(self) -> None:
        prior = observed()
        revised = replace(
            prior,
            revision=2,
            revision_of_digest=prior.to_document()["datum_digest"],
            metric="A_DIFFERENT_METRIC",
            observed_at=DECISION + timedelta(seconds=30),
            published_at=DECISION + timedelta(seconds=20),
            revised_at=DECISION + timedelta(seconds=20),
            available_at=DECISION + timedelta(minutes=1),
        )
        with self.assertRaisesRegex(DataModelError, "DATASET_REVISION_IDENTITY_CHANGED"):
            admit_point_in_time_dataset(
                dataset_id="identity-change",
                decision_at=DECISION + timedelta(minutes=1),
                data=(revised,),
                prior_revisions={prior.datum_id: prior},
            )

    def test_cumulative_registry_retains_omitted_id_and_blocks_resurrection(self) -> None:
        first = observed()
        dataset_1 = admit_point_in_time_dataset(
            dataset_id="cycle-1", decision_at=DECISION, data=(first,)
        )
        registry_1 = build_point_in_time_datum_revision_registry(
            run_id="run:datum-registry",
            cycle_index=1,
            decision_at=DECISION,
            dataset=dataset_1,
        )

        other = observed(datum_id="unrelated")
        cycle_2_at = DECISION + timedelta(minutes=1)
        dataset_2 = admit_point_in_time_dataset(
            dataset_id="cycle-2", decision_at=cycle_2_at, data=(other,)
        )
        registry_2 = build_point_in_time_datum_revision_registry(
            run_id="run:datum-registry",
            cycle_index=2,
            decision_at=cycle_2_at,
            dataset=dataset_2,
            previous_registry=registry_1,
        )
        self.assertIn(first.datum_id, registry_2["known_datum_ids"])
        self.assertNotIn(
            first.to_document()["datum_digest"],
            registry_2["current_cycle_datum_digests"],
        )

        cycle_3_at = DECISION + timedelta(minutes=2)
        resurrected_dataset = admit_point_in_time_dataset(
            dataset_id="cycle-3-resurrection",
            decision_at=cycle_3_at,
            data=(first,),
        )
        with self.assertRaisesRegex(
            DataModelError, "DATASET_GENESIS_PRIOR_CONFLICT"
        ):
            build_point_in_time_datum_revision_registry(
                run_id="run:datum-registry",
                cycle_index=3,
                decision_at=cycle_3_at,
                dataset=resurrected_dataset,
                previous_registry=registry_2,
            )

        revised = replace(
            first,
            revision=2,
            revision_of_digest=first.to_document()["datum_digest"],
            value="65001",
            observed_at=DECISION + timedelta(seconds=90),
            published_at=DECISION + timedelta(seconds=80),
            available_at=cycle_3_at,
            revised_at=DECISION + timedelta(seconds=80),
            vintage_id="2026-08-06T10:02Z",
        )
        revised_dataset = admit_point_in_time_dataset(
            dataset_id="cycle-3-revision",
            decision_at=cycle_3_at,
            data=(revised,),
            prior_revisions={first.datum_id: first},
        )
        registry_3 = build_point_in_time_datum_revision_registry(
            run_id="run:datum-registry",
            cycle_index=3,
            decision_at=cycle_3_at,
            dataset=revised_dataset,
            previous_registry=registry_2,
        )
        latest = {
            row["datum_id"]: row for row in registry_3["latest_revisions"]
        }
        self.assertEqual(2, latest[first.datum_id]["revision"])

    def test_numeric_value_type_rejects_arbitrary_text(self) -> None:
        with self.assertRaisesRegex(DataModelError, "DATA_NUMERIC_VALUE_INVALID"):
            replace(observed(), value="not-a-number")

    def test_quality_conflict_and_coverage_set_an_explicit_claim_ceiling(self) -> None:
        partial = observed().to_document()
        self.assertTrue(partial["hypothesis_admissible"])
        self.assertFalse(partial["inference_admissible"])
        self.assertEqual(
            "DESCRIPTIVE_OR_HYPOTHESIS_ONLY", partial["claim_ceiling"]
        )

        conflicted = replace(
            observed(), conflict_state=ConflictState.SOURCE_CONFLICT
        ).to_document()
        self.assertFalse(conflicted["inference_admissible"])
        self.assertFalse(conflicted["hypothesis_admissible"])
        self.assertEqual("NO_INFERENCE", conflicted["claim_ceiling"])

        unusable_quality = replace(
            quality(), lineage_integrity=QualityLevel.UNUSABLE
        )
        unusable = replace(observed(), quality=unusable_quality).to_document()
        self.assertFalse(unusable["inference_admissible"])
        self.assertFalse(unusable["hypothesis_admissible"])
        self.assertEqual("NO_INFERENCE", unusable["claim_ceiling"])

    def test_revision_timestamp_cannot_precede_the_described_vintage(self) -> None:
        with self.assertRaisesRegex(DataModelError, "DATA_REVISION_TIME_INVALID"):
            replace(
                observed(),
                revision=2,
                revision_of_digest="a" * 64,
                revised_at=DECISION - timedelta(seconds=3),
            )


if __name__ == "__main__":
    unittest.main()
