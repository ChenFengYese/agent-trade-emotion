from __future__ import annotations

import copy
import unittest

from trade_system.theory_paper_v2.domain.v31_sentiment_native_projection_v2 import (
    V31_NATIVE_SENTIMENT_AXES,
    V31SentimentNativeProjectionError,
    build_v31_native_sentiment_projection,
    build_v31_native_sentiment_source_registry,
    verify_v31_native_sentiment_projection,
    verify_v31_native_sentiment_source_registry,
)


DECISION = "2026-08-07T00:00:00Z"


def observation(
    *,
    evidence_id: str = "price-evidence",
    source_kind: str = "PUBLIC_MARK_OR_INDEX_PRICE",
    axis_bindings: list[dict] | None = None,
    datum_ref: str = "datum:mark",
    information_ref: str = "capture:mark",
) -> dict:
    return {
        "evidence_id": evidence_id,
        "source_kind": source_kind,
        "axis_bindings": axis_bindings
        or [
            {
                "axis_id": "PRICE_DIRECTIONAL_PRESSURE",
                "evidence_role": "DIRECT",
            }
        ],
        "information_bindings": [
            {"information_ref": information_ref, "information_digest": "a" * 64}
        ],
        "datum_ref": datum_ref,
        "datum_digest": "b" * 64,
        "input_datum_bindings": [],
        "dependency_group_id": f"dependency:{evidence_id}",
        "observed_at": "2026-08-06T23:59:58Z",
        "available_at": "2026-08-06T23:59:59Z",
        "admission_status": "ADMITTED",
        "clock_status": "VALID",
        "quality_status": "HIGH",
        "coverage_status": "SUFFICIENT",
        "source_observation_status": "OBSERVED",
        "is_closed": None,
        "timeframes": [],
        "limitations": ["single public venue"],
    }


def projection(*, source_observations: list[dict], axis_state_bindings=()) -> dict:
    return build_v31_native_sentiment_projection(
        projection_id="projection:cycle-1",
        instrument_id="BTC-USDT-SWAP",
        decision_at=DECISION,
        source_observations=source_observations,
        axis_state_bindings=axis_state_bindings,
    )


class V31NativeSentimentProjectionTests(unittest.TestCase):
    def test_registry_has_exact_twelve_axes_and_explicit_unknown_policy(self) -> None:
        registry = build_v31_native_sentiment_source_registry()
        self.assertEqual(
            V31_NATIVE_SENTIMENT_AXES,
            tuple(row["axis_id"] for row in registry["axes"]),
        )
        self.assertEqual(12, registry["axis_count"])
        for row in registry["axes"]:
            self.assertIn("direct_source_kinds", row)
            self.assertIn("proxy_source_kinds", row)
            self.assertIn("derived_source_kinds", row)
            self.assertEqual("UNKNOWN", row["unknown_source_policy"]["status"])
            self.assertFalse(row["unknown_source_policy"]["missing_is_zero"])
        self.assertEqual(
            registry["registry_digest"],
            verify_v31_native_sentiment_source_registry(registry),
        )
        registry["source_kind_rules"]["PUBLIC_MARK_OR_INDEX_PRICE"][
            "limitations"
        ].append("caller mutation")
        rebuilt = build_v31_native_sentiment_source_registry()
        self.assertNotIn(
            "caller mutation",
            rebuilt["source_kind_rules"]["PUBLIC_MARK_OR_INDEX_PRICE"][
                "limitations"
            ],
        )

    def test_empty_sources_keep_every_axis_unknown_and_project_no_fake_data(self) -> None:
        document = projection(source_observations=[])
        self.assertEqual(12, len(document["axis_projections"]))
        self.assertTrue(
            all(row["source_evidence_status"] == "UNKNOWN" for row in document["axis_projections"])
        )
        self.assertTrue(all(row["ordinal_value"] is None for row in document["axis_projections"]))
        self.assertTrue(all(not row["missing_is_zero"] for row in document["axis_projections"]))
        self.assertEqual(12, document["graph_projection"]["node_count"])
        self.assertEqual(0, document["graph_projection"]["edge_count"])
        verify_v31_native_sentiment_projection(document)

    def test_statuses_missing_remain_unknown_and_are_not_graph_evidence(self) -> None:
        candidate = observation()
        for field in (
            "admission_status",
            "clock_status",
            "quality_status",
            "coverage_status",
        ):
            candidate.pop(field)
        document = projection(source_observations=[candidate])
        price = document["axis_projections"][0]
        self.assertEqual("UNKNOWN", price["source_evidence_status"])
        self.assertIn("ADMISSION_UNKNOWN", price["unknown_reasons"])
        self.assertIn("CLOCK_UNKNOWN", price["unknown_reasons"])
        self.assertIn("QUALITY_UNKNOWN", price["unknown_reasons"])
        self.assertEqual(12, document["graph_projection"]["node_count"])

    def test_admitted_source_is_projected_but_does_not_invent_direction(self) -> None:
        document = projection(source_observations=[observation()])
        price = document["axis_projections"][0]
        self.assertEqual("AVAILABLE", price["source_evidence_status"])
        self.assertEqual(["price-evidence"], price["admitted_direct_evidence_ids"])
        self.assertEqual("UNKNOWN_NOT_COMPUTED", price["state_label"])
        self.assertIsNone(price["ordinal_value"])
        self.assertEqual(14, document["graph_projection"]["node_count"])
        self.assertEqual(2, document["graph_projection"]["edge_count"])

    def test_non_unknown_axis_state_requires_and_binds_admitted_evidence(self) -> None:
        state = {
            "axis_id": "PRICE_DIRECTIONAL_PRESSURE",
            "state_ref": "sentiment-state:cycle-1:price",
            "state_digest": "c" * 64,
            "state_label": "NEGATIVE_AXIS_STATE",
            "ordinal_value": -1,
            "evidence_ids": ["price-evidence"],
            "observed_at": "2026-08-06T23:59:59Z",
            "available_at": DECISION,
            "limitations": ["ordinal state is not a forecast"],
        }
        document = projection(
            source_observations=[observation()], axis_state_bindings=[state]
        )
        price = document["axis_projections"][0]
        self.assertEqual(-1, price["ordinal_value"])
        self.assertEqual([], price["unknown_reasons"])
        verify_v31_native_sentiment_projection(document)

        missing_status = observation()
        missing_status.pop("quality_status")
        with self.assertRaisesRegex(
            V31SentimentNativeProjectionError,
            "NON_UNKNOWN_STATE_WITHOUT_ADMITTED_EVIDENCE",
        ):
            projection(
                source_observations=[missing_status], axis_state_bindings=[state]
            )

    def test_price_cannot_substitute_for_forced_deleveraging_or_attention(self) -> None:
        for axis in (
            "FORCED_DELEVERAGING_PRESSURE",
            "ATTENTION_AND_AUDIENCE_RESPONSE",
        ):
            candidate = observation(
                axis_bindings=[{"axis_id": axis, "evidence_role": "DIRECT"}]
            )
            with self.assertRaisesRegex(
                V31SentimentNativeProjectionError,
                "SOURCE_KIND_AXIS_ROLE_FORBIDDEN",
            ):
                projection(source_observations=[candidate])

    def test_single_book_snapshot_cannot_claim_liquidity_resilience(self) -> None:
        candidate = observation(
            source_kind="PUBLIC_ORDER_BOOK_SNAPSHOT",
            axis_bindings=[
                {"axis_id": "LIQUIDITY_RESILIENCE", "evidence_role": "DIRECT"}
            ],
        )
        with self.assertRaisesRegex(
            V31SentimentNativeProjectionError,
            "SOURCE_KIND_AXIS_ROLE_FORBIDDEN",
        ):
            projection(source_observations=[candidate])

    def test_timeframe_coherence_requires_exact_closed_multitimeframe_inputs(self) -> None:
        candidate = observation(
            evidence_id="coherence",
            source_kind="CLOSED_MULTI_TIMEFRAME_COHERENCE",
            axis_bindings=[
                {"axis_id": "TIMEFRAME_COHERENCE", "evidence_role": "DERIVED"}
            ],
            datum_ref="datum:coherence",
            information_ref="capture:candles",
        )
        candidate["is_closed"] = True
        candidate["timeframes"] = ["15m", "1h", "4h", "1d"]
        candidate["input_datum_bindings"] = [
            {
                "datum_ref": f"datum:return:{timeframe}",
                "datum_digest": character * 64,
                "metric_kind": "CLOSED_CANDLE_RETURN",
                "timeframe": timeframe,
                "is_closed": True,
            }
            for timeframe, character in zip(
                ("15m", "1h", "4h", "1d"), ("1", "2", "3", "4"), strict=True
            )
        ]
        document = projection(source_observations=[candidate])
        coherence = document["axis_projections"][-1]
        self.assertEqual("AVAILABLE", coherence["source_evidence_status"])
        self.assertEqual(["coherence"], coherence["admitted_derived_evidence_ids"])

        open_input = copy.deepcopy(candidate)
        open_input["input_datum_bindings"][0]["is_closed"] = False
        rejected = projection(source_observations=[open_input])
        coherence = rejected["axis_projections"][-1]
        self.assertEqual("UNKNOWN", coherence["source_evidence_status"])
        self.assertIn("CLOSED_INPUT_PROOF_MISSING", coherence["unknown_reasons"])

    def test_one_evidence_object_projects_to_multiple_axes_without_copying_nodes(self) -> None:
        candidate = observation(
            evidence_id="closed-candles",
            source_kind="PUBLIC_CLOSED_CANDLE_SERIES",
            datum_ref="datum:closed-candles",
            information_ref="capture:closed-candles",
            axis_bindings=[
                {"axis_id": "PRICE_DIRECTIONAL_PRESSURE", "evidence_role": "DIRECT"},
                {"axis_id": "STRUCTURE_PERSISTENCE", "evidence_role": "PROXY"},
                {"axis_id": "VOLATILITY_AND_TAIL_STRESS", "evidence_role": "DIRECT"},
            ],
        )
        candidate["is_closed"] = True
        document = projection(source_observations=[candidate])
        graph = document["graph_projection"]
        source_nodes = [row for row in graph["nodes"] if row["node_type"] == "SOURCE_ARTIFACT"]
        data_nodes = [row for row in graph["nodes"] if row["node_type"] == "MARKET_FACT"]
        self.assertEqual(1, len(source_nodes))
        self.assertEqual(1, len(data_nodes))
        self.assertEqual(4, graph["edge_count"])

    def test_input_order_is_canonical_and_nested_tampering_is_detected(self) -> None:
        first = observation()
        second = observation(
            evidence_id="attention",
            source_kind="PUBLIC_SEARCH_INTEREST_SERIES",
            datum_ref="datum:attention",
            information_ref="capture:attention",
            axis_bindings=[
                {
                    "axis_id": "ATTENTION_AND_AUDIENCE_RESPONSE",
                    "evidence_role": "DIRECT",
                }
            ],
        )
        forward = projection(source_observations=[first, second])
        reverse = projection(source_observations=[second, first])
        self.assertEqual(forward, reverse)
        tampered = copy.deepcopy(forward)
        tampered["graph_projection"]["nodes"][0]["label"] = "tampered"
        with self.assertRaisesRegex(
            V31SentimentNativeProjectionError, "PROJECTION_DIGEST_INVALID"
        ):
            verify_v31_native_sentiment_projection(tampered)

    def test_future_information_fails_closed(self) -> None:
        candidate = observation()
        candidate["available_at"] = "2026-08-07T00:00:01Z"
        with self.assertRaisesRegex(
            V31SentimentNativeProjectionError, "FUTURE_SOURCE_FORBIDDEN"
        ):
            projection(source_observations=[candidate])


if __name__ == "__main__":
    unittest.main()
