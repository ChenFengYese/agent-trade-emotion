from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import unittest

from trade_system.theory_paper_v2.application.v31_sentiment_native_projection_adapter_v2 import (
    V31SentimentProjectionAdapterV2Error,
    build_v31_sentiment_native_projection_receipt_v2,
    verify_v31_sentiment_native_projection_receipt_v2,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
)
from trade_system.theory_paper_v2.domain.data_model import (
    ConflictState,
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
    point_in_time_datum_from_document,
)
from trade_system.theory_paper_v2.domain.v31_cycle_source_admission import (
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    cycle_source_admission_ref,
    seal_v31_cycle_source_admission,
)


RUN_ID = "v31-successor-axis-adapter-test"
SYMBOL = "BTC-USDT-SWAP"
RAW_SHA = "a" * 64
TIMEFRAMES = ("15m", "1h", "4h", "1d")


def _at(hour: int) -> datetime:
    return datetime(2026, 8, 7, hour, 0, tzinfo=UTC)


def _text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _quality() -> DataQuality:
    return DataQuality(
        source_reliability=QualityLevel.HIGH,
        completeness=QualityLevel.HIGH,
        timeliness=QualityLevel.HIGH,
        semantic_fidelity=QualityLevel.HIGH,
        measurement_error=QualityLevel.UNKNOWN,
        revision_risk=QualityLevel.UNKNOWN,
        cross_source_consistency=QualityLevel.UNKNOWN,
        lineage_integrity=QualityLevel.HIGH,
        dependency_independence=QualityLevel.UNKNOWN,
        regime_applicability=QualityLevel.UNKNOWN,
        limitations=("Official public fixture with frozen lineage.",),
    )


def _datum(
    *,
    cycle: int,
    event_id: str,
    decision: datetime,
    metric: str,
    value: str,
    unit: str,
    category: str,
    timeframe: str,
    window: str,
    dependency_group: str,
    inputs: tuple[PointInTimeDatum, ...] = (),
    raw_sha: str = RAW_SHA,
    source_ref: str = "okx-test",
    raw_ref: str | None = None,
    observed_at: datetime | None = None,
    available_at: datetime | None = None,
) -> PointInTimeDatum:
    derived = bool(inputs)
    observed = observed_at or decision - timedelta(minutes=1)
    available = available_at or decision
    value_type = (
        DatumValueType.DIGEST if unit == "SHA256" else DatumValueType.NUMERIC
    )
    return PointInTimeDatum(
        datum_id=f"datum:test:{cycle}:{metric}",
        epistemic_type=(
            DatumEpistemicType.DERIVED_MEASURE
            if derived
            else DatumEpistemicType.OBSERVED_FACT
        ),
        data_kind=("MARKET_DERIVED_MEASURE" if derived else "MARKET_FACT"),
        category=category,
        metric=metric,
        value=value,
        value_type=value_type,
        unit=unit,
        currency="USDT" if unit == "USDT_PER_BTC" else None,
        frequency=timeframe,
        timeframe=timeframe,
        window=window,
        instrument_id=SYMBOL,
        asset_class="CRYPTO_DERIVATIVE",
        venue_id="OKX",
        entity_ids=(),
        actor_ids=(),
        audience_ids=(),
        event_ids=(event_id,),
        source_id=f"source:test:{source_ref}",
        source_type="OKX_OFFICIAL_PUBLIC",
        source_ref=source_ref,
        raw_ref=raw_ref or f"raw/{source_ref}.body",
        raw_sha256=raw_sha,
        as_of=observed,
        observed_at=observed,
        published_at=None,
        available_at=available,
        effective_at=observed,
        revised_at=None,
        vintage_id=f"vintage:test:{cycle}:{metric}",
        revision=1,
        revision_of_digest=None,
        formula_version=("FROZEN_TEST_TRANSFORM_V1" if derived else None),
        input_refs=tuple(row.datum_id for row in inputs),
        input_digests=tuple(row.to_document()["datum_digest"] for row in inputs),
        quality=_quality(),
        coverage="1",
        missingness=Missingness.OBSERVED,
        missing_reason=None,
        staleness="CURRENT_AT_CAPTURE",
        conflict_state=ConflictState.NONE,
        proxy_level=(ProxyLevel.MODEL_DERIVED if derived else ProxyLevel.DIRECT),
        uncertainty=UncertaintyRepresentation(
            kind=UncertaintyKind.NONE_DECLARED,
            assumptions=("No numerical uncertainty supplied.",),
        ),
        regime_ref=None,
        dependency_group=dependency_group,
        lineage=tuple(row.datum_id for row in inputs),
        limitations=("Public fixture for exact successor adapter verification.",),
    )


def _dataset(
    *,
    cycle: int,
    decision: datetime,
    include_1d: bool = True,
    previous_oi: PointInTimeDatum | None = None,
    mismatched_prior_copy: bool = False,
) -> tuple[dict, str, str]:
    event_id = f"event:test:{cycle}"
    event_digest = canonical_digest({"event_id": event_id, "cycle": cycle})
    rows: list[PointInTimeDatum] = []
    mark = _datum(
        cycle=cycle,
        event_id=event_id,
        decision=decision,
        metric="mark-price",
        value="100",
        unit="USDT_PER_BTC",
        category="PRICE_AND_RETURNS",
        timeframe="SNAPSHOT",
        window="CURRENT_CAPTURE",
        dependency_group="MARK_PRICE",
    )
    rows.append(mark)
    for timeframe in TIMEFRAMES:
        if timeframe == "1d" and not include_1d:
            continue
        anchor = _datum(
            cycle=cycle,
            event_id=event_id,
            decision=decision,
            metric=f"SOURCE_RESPONSE_SHA256_{timeframe}",
            value=RAW_SHA,
            unit="SHA256",
            category="INSTRUMENT_AND_DATA_QUALITY",
            timeframe=timeframe,
            window="LATEST_CLOSED_AND_20_BAR_CONTEXT",
            dependency_group=f"SOURCE_ANCHOR_CANDLE_{timeframe.upper()}",
        )
        rows.append(anchor)
        for suffix, value, category, unit in (
            ("return-pct", "1", "PRICE_AND_RETURNS", "PERCENT"),
            ("range-pct", "2", "TREND_VOLATILITY_AND_STRUCTURE", "PERCENT"),
            (
                "volume-vs-20bar-median",
                "1.2",
                "VOLUME_AND_ACTIVE_FLOW",
                "RATIO",
            ),
        ):
            rows.append(
                _datum(
                    cycle=cycle,
                    event_id=event_id,
                    decision=decision,
                    metric=f"candle-{timeframe}-{suffix}",
                    value=value,
                    unit=unit,
                    category=category,
                    timeframe=timeframe,
                    window="LATEST_CLOSED_AND_20_BAR_CONTEXT",
                    dependency_group=f"CANDLE_{timeframe.upper()}",
                    inputs=(anchor,),
                )
            )
    micro_anchor = _datum(
        cycle=cycle,
        event_id=event_id,
        decision=decision,
        metric="SOURCE_RESPONSE_SHA256_MICRO",
        value=RAW_SHA,
        unit="SHA256",
        category="INSTRUMENT_AND_DATA_QUALITY",
        timeframe="SNAPSHOT",
        window="SINGLE_REST_CAPTURE",
        dependency_group="SOURCE_ANCHOR_MICRO",
    )
    rows.extend(
        [
            micro_anchor,
            _datum(
                cycle=cycle,
                event_id=event_id,
                decision=decision,
                metric="book-top5-imbalance",
                value="0.1",
                unit="RATIO_NEG1_TO_1",
                category="ORDER_BOOK_AND_LIQUIDITY",
                timeframe="SNAPSHOT",
                window="SINGLE_REST_CAPTURE",
                dependency_group="ORDER_BOOK",
                inputs=(micro_anchor,),
            ),
            _datum(
                cycle=cycle,
                event_id=event_id,
                decision=decision,
                metric="recent-trade-side-imbalance",
                value="0.2",
                unit="RATIO_NEG1_TO_1",
                category="VOLUME_AND_ACTIVE_FLOW",
                timeframe="SNAPSHOT",
                window="SINGLE_REST_CAPTURE",
                dependency_group="RECENT_TRADES",
                inputs=(micro_anchor,),
            ),
            _datum(
                cycle=cycle,
                event_id=event_id,
                decision=decision,
                metric="funding-rate",
                value="0.0001",
                unit="RATE",
                category="FUNDING_BASIS_AND_POSITIONING",
                timeframe="SNAPSHOT",
                window="CURRENT_CAPTURE",
                dependency_group="FUNDING_RATE",
            ),
        ]
    )
    current_oi = _datum(
        cycle=cycle,
        event_id=event_id,
        decision=decision,
        metric="open-interest-btc",
        value="1100" if cycle > 1 else "1000",
        unit="BTC",
        category="OPEN_INTEREST_AND_LEVERAGE",
        timeframe="SNAPSHOT",
        window="CURRENT_CAPTURE",
        dependency_group="OPEN_INTEREST",
        raw_sha=RAW_SHA,
        source_ref="okx-test",
    )
    rows.append(current_oi)
    if previous_oi is not None:
        previous_document = previous_oi.to_document()
        prior_copy = _datum(
            cycle=cycle,
            event_id=event_id,
            decision=decision,
            metric="prior-cycle-open-interest-btc",
            value=("999" if mismatched_prior_copy else str(previous_oi.value)),
            unit=str(previous_oi.unit),
            category="OPEN_INTEREST_AND_LEVERAGE",
            timeframe=str(previous_oi.timeframe),
            window="PREVIOUS_ACCEPTED_CYCLE",
            dependency_group="PRIOR_OPEN_INTEREST",
            raw_sha=str(previous_oi.raw_sha256),
            source_ref=str(previous_oi.source_ref),
            raw_ref=str(previous_oi.raw_ref),
            observed_at=previous_oi.observed_at,
            available_at=previous_oi.available_at,
        )
        self_check = prior_copy.to_document()
        for field in (
            "unit",
            "instrument_id",
            "venue_id",
            "source_type",
            "source_ref",
            "raw_ref",
            "raw_sha256",
            "as_of",
            "observed_at",
            "available_at",
            "coverage",
            "missingness",
        ):
            if self_check[field] != previous_document[field]:
                raise AssertionError(field)
        rows.extend(
            [
                prior_copy,
                _datum(
                    cycle=cycle,
                    event_id=event_id,
                    decision=decision,
                    metric="open-interest-change-pct",
                    value="10",
                    unit="PERCENT",
                    category="OPEN_INTEREST_AND_LEVERAGE",
                    timeframe="SNAPSHOT",
                    window="PREVIOUS_ACCEPTED_CYCLE_TO_CURRENT_CAPTURE",
                    dependency_group="OPEN_INTEREST_CHANGE",
                    inputs=(current_oi, prior_copy),
                    raw_sha=str(current_oi.raw_sha256),
                    source_ref=str(current_oi.source_ref),
                ),
            ]
        )
    dataset = admit_point_in_time_dataset(
        dataset_id=f"dataset:test:{cycle}",
        decision_at=decision,
        data=rows,
    )
    return dataset, event_id, event_digest


def _information_registry(
    *,
    cycle: int,
    decision: datetime,
    event_id: str,
    event_digest: str,
    previous: dict | None = None,
) -> dict:
    latest = [] if previous is None else [dict(row) for row in previous["latest_revisions"]]
    latest.append(
        {
            "event_id": event_id,
            "revision": 1,
            "event_digest": event_digest,
            "available_at": _text(decision),
        }
    )
    latest.sort(key=lambda row: row["event_id"])
    document = {
        "schema_id": "theory_paper_v2_v31_information_revision_registry",
        "schema_version": "1.0.0",
        "run_id": RUN_ID,
        "cycle_index": cycle,
        "decision_at": _text(decision),
        "previous_registry_digest": (
            None if previous is None else previous["information_revision_registry_digest"]
        ),
        "known_event_ids": [row["event_id"] for row in latest],
        "latest_revisions": latest,
        "current_cycle_event_digests": [event_digest],
        "history_retention": "ALL_KNOWN_IDS_LATEST_REVISION_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return {
        **document,
        "information_revision_registry_digest": canonical_digest(document),
    }


def _artifact_rows(
    *,
    cycle: int,
    dataset_digest: str,
    snapshot_digest: str,
    plan_digest: str,
    checkpoint_digest: str,
    completion_digest: str,
    event_record_digest: str,
) -> list[dict]:
    values = {
        "QUALIFICATION_PLAN": plan_digest,
        "QUALIFICATION_RESERVATION": canonical_digest({"reservation": cycle}),
        "QUALIFICATION_CHECKPOINT": checkpoint_digest,
        "QUALIFICATION_COMPLETION": completion_digest,
        "MARKET_SNAPSHOT": snapshot_digest,
        "PIT_DATASET": dataset_digest,
        "INFORMATION_EVENT": event_record_digest,
    }
    rows = []
    for role, semantic in values.items():
        artifact_id = "0001" if role == "INFORMATION_EVENT" else role.lower()
        rows.append(
            {
                "artifact_role": role,
                "artifact_id": artifact_id,
                "source_relative_ref": f"source/{cycle}/{role.lower()}.json",
                "target_relative_ref": (
                    f"cycles/{cycle:04d}/market/source-admission/"
                    f"{role.lower()}.json"
                ),
                "schema_id": f"schema:{role.lower()}",
                "digest_field": f"{role.lower()}_digest",
                "semantic_digest": semantic,
                "source_physical_sha256": "f" * 64,
                "target_physical_sha256": "f" * 64,
                "exact_bytes_copied": True,
            }
        )
    rows.append(
        {
            "artifact_role": "RAW_RESPONSE",
            "artifact_id": "okx-test",
            "source_relative_ref": f"source/{cycle}/okx-test.body",
            "target_relative_ref": (
                f"cycles/{cycle:04d}/market/source-admission/okx-test.body"
            ),
            "schema_id": None,
            "digest_field": None,
            "semantic_digest": RAW_SHA,
            "source_physical_sha256": RAW_SHA,
            "target_physical_sha256": RAW_SHA,
            "exact_bytes_copied": True,
        }
    )
    return sorted(rows, key=lambda row: (row["artifact_role"], row["artifact_id"]))


def _admission(
    *,
    cycle: int,
    decision: datetime,
    dataset: dict,
    event_digest: str,
    prior_admission: dict | None = None,
    prior_oi_digest: str | None = None,
) -> dict:
    plan = canonical_digest({"plan": cycle})
    checkpoint = canonical_digest({"checkpoint": cycle})
    completion = canonical_digest({"completion": cycle})
    snapshot = canonical_digest({"snapshot": cycle})
    event_record = canonical_digest({"event-record": cycle})
    if cycle == 1:
        previous_context = {
            "status": "GENESIS_NO_PRIOR_SOURCE_CONTEXT",
            "previous_cycle_source_admission_binding": None,
            "prior_snapshot_binding": None,
            "prior_open_interest_datum_digest": None,
            "prior_open_interest_status": "NOT_APPLICABLE_GENESIS",
            "prior_open_interest_zero_imputed": False,
            "previous_decision_at": None,
            "previous_admitted_at": None,
            "previous_closed_1h_as_of": None,
        }
    else:
        assert prior_admission is not None and prior_oi_digest is not None
        previous_context = {
            "status": "BOUND_TO_PREVIOUS_ACCEPTED_CYCLE",
            "previous_cycle_source_admission_binding": {
                "relative_ref": cycle_source_admission_ref(cycle - 1),
                "schema_id": SOURCE_ADMISSION_SCHEMA_ID,
                "digest_field": SOURCE_ADMISSION_DIGEST_FIELD,
                "semantic_digest": prior_admission[SOURCE_ADMISSION_DIGEST_FIELD],
                "physical_sha256": "e" * 64,
            },
            "prior_snapshot_binding": {
                "relative_ref": (
                    f"cycles/{cycle - 1:04d}/market/source-admission/"
                    "market_snapshot.json"
                ),
                "schema_id": "native_btc_public_market_snapshot",
                "digest_field": "native_market_snapshot_digest",
                "semantic_digest": prior_admission["native_market_snapshot_digest"],
                "physical_sha256": "d" * 64,
            },
            "prior_open_interest_datum_digest": prior_oi_digest,
            "prior_open_interest_status": "OBSERVED",
            "prior_open_interest_zero_imputed": False,
            "previous_decision_at": prior_admission["decision_at"],
            "previous_admitted_at": prior_admission["admitted_at"],
            "previous_closed_1h_as_of": prior_admission["closed_1h_as_of"],
        }
    return seal_v31_cycle_source_admission(
        run_id=RUN_ID,
        cycle_index=cycle,
        admitted_at=_text(decision + timedelta(seconds=1)),
        decision_at=_text(decision),
        closed_1h_as_of=_text(decision - timedelta(hours=1)),
        active_authority_digest="1" * 64,
        active_authority_recorded_at="2026-08-07T09:00:00Z",
        experiment_contract_digest="2" * 64,
        source_qualification_id=f"qualification-test-{cycle}",
        source_qualification_plan_digest=plan,
        source_qualification_checkpoint_digest=checkpoint,
        source_qualification_completion_digest=completion,
        source_qualification_decision_at=_text(decision),
        native_market_snapshot_digest=snapshot,
        pit_dataset_digest=dataset["dataset_digest"],
        information_event_digests=[event_digest],
        information_event_record_digests=[event_record],
        source_capture_record_digests={
            "okx-test": canonical_digest({"capture": cycle})
        },
        raw_physical_sha256_by_request_id={"okx-test": RAW_SHA},
        earliest_capture_started_at=_text(decision - timedelta(minutes=30)),
        latest_capture_received_at=_text(decision - timedelta(seconds=1)),
        artifact_copies=_artifact_rows(
            cycle=cycle,
            dataset_digest=dataset["dataset_digest"],
            snapshot_digest=snapshot,
            plan_digest=plan,
            checkpoint_digest=checkpoint,
            completion_digest=completion,
            event_record_digest=event_record,
        ),
        previous_source_context=previous_context,
    )


def _bundle(
    *,
    cycle: int,
    include_1d: bool = True,
    previous_bundle: tuple[dict, dict, dict] | None = None,
    mismatched_prior_copy: bool = False,
) -> tuple[dict, dict, dict]:
    decision = _at(10 + cycle)
    previous_dataset = None if previous_bundle is None else previous_bundle[0]
    previous_registry = None if previous_bundle is None else previous_bundle[1]
    previous_admission = None if previous_bundle is None else previous_bundle[2]
    previous_oi = None
    if previous_dataset is not None:
        previous_oi_document = next(
            row for row in previous_dataset["data"] if row["metric"] == "open-interest-btc"
        )
        previous_oi = point_in_time_datum_from_document(previous_oi_document)
    dataset, event_id, event_digest = _dataset(
        cycle=cycle,
        decision=decision,
        include_1d=include_1d,
        previous_oi=previous_oi,
        mismatched_prior_copy=mismatched_prior_copy,
    )
    registry = _information_registry(
        cycle=cycle,
        decision=decision,
        event_id=event_id,
        event_digest=event_digest,
        previous=previous_registry,
    )
    admission = _admission(
        cycle=cycle,
        decision=decision,
        dataset=dataset,
        event_digest=event_digest,
        prior_admission=previous_admission,
        prior_oi_digest=(
            None if previous_oi is None else previous_oi.to_document()["datum_digest"]
        ),
    )
    return dataset, registry, admission


def _axis(receipt: dict, axis_id: str) -> dict:
    return next(
        row
        for row in receipt["projection"]["axis_projections"]
        if row["axis_id"] == axis_id
    )


class V31SentimentNativeProjectionAdapterV2Tests(unittest.TestCase):
    def test_maps_only_contract_roles_and_keeps_unsupported_axes_unknown(self) -> None:
        dataset, registry, admission = _bundle(cycle=1)
        receipt = build_v31_sentiment_native_projection_receipt_v2(
            projection_id="projection:test:1",
            pit_dataset=dataset,
            information_revision_registry=registry,
            cycle_source_admission=admission,
        )

        self.assertEqual(12, receipt["axis_count"])
        self.assertEqual(
            "AVAILABLE", _axis(receipt, "PRICE_DIRECTIONAL_PRESSURE")["source_evidence_status"]
        )
        self.assertEqual(
            "AVAILABLE", _axis(receipt, "STRUCTURE_PERSISTENCE")["source_evidence_status"]
        )
        self.assertEqual(
            "AVAILABLE",
            _axis(receipt, "PARTICIPATION_AND_ACTIVE_FLOW")["source_evidence_status"],
        )
        self.assertEqual(
            "AVAILABLE", _axis(receipt, "CROWDING_DIRECTION")["source_evidence_status"]
        )
        self.assertEqual(
            "AVAILABLE", _axis(receipt, "LEVERAGE_CHANGE")["source_evidence_status"]
        )
        self.assertEqual(
            "AVAILABLE",
            _axis(receipt, "VOLATILITY_AND_TAIL_STRESS")["source_evidence_status"],
        )
        self.assertEqual(
            "AVAILABLE", _axis(receipt, "TIMEFRAME_COHERENCE")["source_evidence_status"]
        )
        for axis_id in (
            "FORCED_DELEVERAGING_PRESSURE",
            "LIQUIDITY_RESILIENCE",
            "EVENT_AND_NARRATIVE_REACTION",
            "ATTENTION_AND_AUDIENCE_RESPONSE",
            "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
        ):
            self.assertEqual("UNKNOWN", _axis(receipt, axis_id)["source_evidence_status"])
        self.assertTrue(
            all(row["ordinal_value"] is None for row in receipt["projection"]["axis_projections"])
        )

        by_ref = {row["datum_id"]: row for row in dataset["data"]}
        book_observation = next(
            row
            for row in receipt["projection"]["source_observations"]
            if row["datum_ref"] in by_ref
            and by_ref[row["datum_ref"]]["metric"] == "book-top5-imbalance"
        )
        self.assertEqual(
            [{"axis_id": "PRICE_DIRECTIONAL_PRESSURE", "evidence_role": "PROXY"}],
            book_observation["axis_bindings"],
        )
        self.assertEqual(
            receipt["projection_receipt_digest"],
            verify_v31_sentiment_native_projection_receipt_v2(
                receipt,
                pit_dataset=dataset,
                information_revision_registry=registry,
                cycle_source_admission=admission,
            ),
        )

    def test_coherence_requires_the_exact_four_closed_timeframes(self) -> None:
        dataset, registry, admission = _bundle(cycle=1, include_1d=False)
        receipt = build_v31_sentiment_native_projection_receipt_v2(
            projection_id="projection:test:missing-1d",
            pit_dataset=dataset,
            information_revision_registry=registry,
            cycle_source_admission=admission,
        )
        coherence = _axis(receipt, "TIMEFRAME_COHERENCE")
        self.assertEqual("UNKNOWN", coherence["source_evidence_status"])
        self.assertEqual([], receipt["derived_evidence_materials"])
        self.assertIn(
            "CLOSED_15M_1H_4H_1D_RETURN_SET_INCOMPLETE",
            {row["reason"] for row in receipt["excluded_candidates"]},
        )

    def test_oi_change_requires_exact_previous_admission_dataset_and_datum(self) -> None:
        previous = _bundle(cycle=1)
        current = _bundle(cycle=2, previous_bundle=previous)
        dataset, registry, admission = current

        without_previous = build_v31_sentiment_native_projection_receipt_v2(
            projection_id="projection:test:2:no-previous",
            pit_dataset=dataset,
            information_revision_registry=registry,
            cycle_source_admission=admission,
        )
        self.assertEqual(
            "NOT_SUPPLIED_OI_CHANGE_EXCLUDED",
            without_previous["previous_context_verification"]["status"],
        )
        self.assertIn(
            "PREVIOUS_EXACT_OI_BINDING_NOT_VERIFIED",
            {row["reason"] for row in without_previous["excluded_candidates"]},
        )

        exact = build_v31_sentiment_native_projection_receipt_v2(
            projection_id="projection:test:2:exact",
            pit_dataset=dataset,
            information_revision_registry=registry,
            cycle_source_admission=admission,
            previous_pit_dataset=previous[0],
            previous_cycle_source_admission=previous[2],
        )
        self.assertEqual(
            "VERIFIED_EXACT_PREVIOUS_OI_BINDING",
            exact["previous_context_verification"]["status"],
        )
        leverage = _axis(exact, "LEVERAGE_CHANGE")
        self.assertEqual(1, len(leverage["admitted_derived_evidence_ids"]))

        mismatched = _bundle(
            cycle=2,
            previous_bundle=previous,
            mismatched_prior_copy=True,
        )
        excluded = build_v31_sentiment_native_projection_receipt_v2(
            projection_id="projection:test:2:mismatch",
            pit_dataset=mismatched[0],
            information_revision_registry=mismatched[1],
            cycle_source_admission=mismatched[2],
            previous_pit_dataset=previous[0],
            previous_cycle_source_admission=previous[2],
        )
        self.assertIn(
            "PRIOR_OI_COPY_DOES_NOT_MATCH_PREVIOUS_ACCEPTED_DATUM",
            {row["reason"] for row in excluded["excluded_candidates"]},
        )

    def test_input_digest_or_admission_drift_fails_closed(self) -> None:
        dataset, registry, admission = _bundle(cycle=1)
        drifted = copy.deepcopy(registry)
        changed = "9" * 64
        drifted["latest_revisions"][-1]["event_digest"] = changed
        drifted["current_cycle_event_digests"] = [changed]
        payload = dict(drifted)
        payload.pop("information_revision_registry_digest")
        drifted["information_revision_registry_digest"] = canonical_digest(payload)
        with self.assertRaisesRegex(
            V31SentimentProjectionAdapterV2Error,
            "SOURCE_INPUT_BINDING_INVALID",
        ):
            build_v31_sentiment_native_projection_receipt_v2(
                projection_id="projection:test:drift",
                pit_dataset=dataset,
                information_revision_registry=drifted,
                cycle_source_admission=admission,
            )

        receipt = build_v31_sentiment_native_projection_receipt_v2(
            projection_id="projection:test:tamper",
            pit_dataset=dataset,
            information_revision_registry=registry,
            cycle_source_admission=admission,
        )
        receipt["projection"]["axis_projections"][0]["state_label"] = "FORGED"
        with self.assertRaisesRegex(
            V31SentimentProjectionAdapterV2Error,
            "RECEIPT_DIGEST_INVALID",
        ):
            verify_v31_sentiment_native_projection_receipt_v2(
                receipt,
                pit_dataset=dataset,
                information_revision_registry=registry,
                cycle_source_admission=admission,
            )


if __name__ == "__main__":
    unittest.main()
