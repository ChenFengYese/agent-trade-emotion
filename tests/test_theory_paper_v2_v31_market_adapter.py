from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.data_model import (
    Missingness,
    PointInTimeDatum,
)
from trade_system.theory_paper_v2.domain.dynamic_research import (
    MARKET_CATEGORIES,
    build_market_information_snapshot,
)
from trade_system.theory_paper_v2.domain.information_model import (
    InformationEvent,
    SourceEvidenceBoundary,
    SourceQuality,
    information_event_digest,
)
from trade_system.theory_paper_v2.infrastructure.v31_market_adapter import (
    V31MarketAdapterError,
    adapt_native_public_snapshot,
    adapt_synthetic_fixture_snapshot,
)


class V31MarketAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.as_of = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        self.as_of_text = "2026-08-06T12:00:00Z"
        self.raw_sha = "a" * 64

    def fact(
        self,
        *,
        fact_id: str,
        category: str,
        observed: bool,
        symbol: str,
        source_ref: str,
    ) -> dict:
        return {
            "fact_id": fact_id,
            "kind": "RAW_FACT",
            "category": category,
            "metric": fact_id,
            "value": "100" if observed else None,
            "unit": "SYNTHETIC_INDEX" if symbol == "SYNTHUSDT" else "USDT_PER_BTC",
            "symbol": symbol,
            "timeframe": "SNAPSHOT",
            "window": "CURRENT_CAPTURE",
            "source_ref": source_ref if observed else "NO_AUTHORIZED_SOURCE",
            "raw_ref": f"raw/{source_ref}.json" if observed else "UNAVAILABLE",
            "raw_sha256": self.raw_sha if observed else None,
            "observed_at": self.as_of_text,
            "available_at": self.as_of_text,
            "quality": "GOOD" if observed else "UNKNOWN",
            "coverage": "1" if observed else "0",
            "dependency_group": f"dependency:{category.lower()}",
            "lineage": [],
            "transform": None,
            "limitations": "fixture observation with explicit source limits",
            "missing_reason": None if observed else "SOURCE_UNAVAILABLE",
        }

    def legacy_facts(self, *, symbol: str, source_ref: str) -> list[dict]:
        missing_categories = {
            "LIQUIDATION",
            "NEWS_EVENTS_AND_REACTION",
            "CROSS_MARKET_AND_MACRO",
        }
        rows = [
            self.fact(
                fact_id=f"fact:{index}",
                category=category,
                observed=category not in missing_categories,
                symbol=symbol,
                source_ref=source_ref,
            )
            for index, category in enumerate(MARKET_CATEGORIES)
        ]
        rows.append(
            {
                "fact_id": "derived:return",
                "kind": "DERIVED_FEATURE",
                "category": "PRICE_AND_RETURNS",
                "metric": "closed-window-return",
                "value": "1.5",
                "unit": "PERCENT",
                "symbol": symbol,
                "timeframe": "1h",
                "window": "LATEST_CLOSED_WINDOW",
                "source_ref": source_ref,
                "raw_ref": f"raw/{source_ref}.json",
                "raw_sha256": self.raw_sha,
                "observed_at": self.as_of_text,
                "available_at": self.as_of_text,
                "quality": "GOOD",
                "coverage": "1",
                "dependency_group": "dependency:price_and_returns",
                "lineage": ["fact:0"],
                "transform": "DETERMINISTIC_FIXTURE_RETURN_V1",
                "limitations": "derived from the source-bound price fixture",
                "missing_reason": None,
            }
        )
        return rows

    def synthetic_snapshot(self) -> dict:
        facts = self.legacy_facts(
            symbol="SYNTHUSDT", source_ref="fixture-price-source"
        )
        return {
            "facts": facts,
            "attempt_count": len(MARKET_CATEGORIES),
            "observed_count": 7,
            "unknown_count": 3,
            "derived_feature_count": 1,
            "collector_id": "SYNTHETIC_TEN_CATEGORY_COLLECTOR_V1",
        }

    def public_capture(self) -> dict:
        headers = [{"name": "content-type", "value": "application/json"}]
        query: list[dict[str, str]] = []
        capture = {
            "request_id": "okx-native-ticker",
            "method": "GET",
            "base_url": "https://www.okx.com",
            "path": "/api/v5/market/ticker",
            "query": query,
            "request_started_at": "2026-08-06T11:59:59Z",
            "response_received_at": self.as_of_text,
            "final_url": "https://www.okx.com/api/v5/market/ticker",
            "http_status": 200,
            "selected_response_headers": headers,
            "response_headers_digest": canonical_digest(headers),
            "raw_body_sha256": self.raw_sha,
            "raw_body_byte_length": 128,
            "request_identity_digest": canonical_digest(
                {
                    "method": "GET",
                    "base_url": "https://www.okx.com",
                    "path": "/api/v5/market/ticker",
                    "query": query,
                }
            ),
        }
        return {
            **capture,
            "record_digest": canonical_digest(capture),
        }

    def native_snapshot(self, *, attested: bool = False) -> dict:
        run_id = "native-adapter-fixture"
        cycle_index = 1
        facts = self.legacy_facts(
            symbol="BTC-USDT-SWAP", source_ref="okx-native-ticker"
        )
        information = build_market_information_snapshot(
            run_id=run_id,
            cycle_index=cycle_index,
            symbol="BTC-USDT-SWAP",
            as_of=self.as_of_text,
            facts=facts,
        )
        return self_digest(
            {
                "schema_id": "native_btc_public_market_snapshot",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "instrument_id": "BTC-USDT-SWAP",
                "server_time_ms": 1786017600000,
                "captured_through": self.as_of_text,
                "mark_price": "100",
                "facts": [],
                "market_information_snapshot": information,
                "prior_market_snapshot_digest": None,
                "source_captures": [self.public_capture()] if attested else [],
                "required_request_ids": ["okx-native-ticker"] if attested else [],
                "optional_failures": {},
                "data_scope": "OFFICIAL_PUBLIC_MARKET_ONLY",
                "point_in_time": True,
                "missing_is_zero": False,
                "account_data_accessed": False,
                "order_data_accessed": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
            },
            "native_market_snapshot_digest",
        )

    def test_synthetic_and_native_emit_the_same_domain_contracts(self) -> None:
        raw_synthetic = self.synthetic_snapshot()
        synthetic = adapt_synthetic_fixture_snapshot(
            raw_synthetic,
            run_id="synthetic-adapter-fixture",
            cycle_index=1,
            as_of=self.as_of,
            decision_at=self.as_of,
        )
        sealed_synthetic_snapshot = build_market_information_snapshot(
            run_id="synthetic-adapter-fixture",
            cycle_index=1,
            symbol="SYNTHUSDT",
            as_of=self.as_of_text,
            facts=raw_synthetic["facts"],
        )
        sealed_synthetic = adapt_synthetic_fixture_snapshot(
            sealed_synthetic_snapshot,
            run_id="synthetic-adapter-fixture",
            cycle_index=1,
            as_of=self.as_of,
            decision_at=self.as_of,
        )
        native = adapt_native_public_snapshot(
            self.native_snapshot(), decision_at=self.as_of
        )

        for result in (synthetic, sealed_synthetic, native):
            self.assertTrue(all(isinstance(row, PointInTimeDatum) for row in result.data))
            self.assertTrue(
                all(isinstance(event, InformationEvent) for event in result.information_events)
            )
            self.assertEqual(
                "theory_paper_v2_v31_point_in_time_dataset",
                result.dataset_document["schema_id"],
            )
            self.assertFalse(result.dataset_document["missing_is_zero"])
            self.assertEqual(
                64, len(information_event_digest(result.information_events[0]))
            )

        native_price = next(row for row in native.data if row.metric == "fact:0")
        self.assertEqual("raw/okx-native-ticker.json", native_price.raw_ref)
        self.assertEqual(self.raw_sha, native_price.raw_sha256)
        self.assertEqual("OKX", native_price.venue_id)
        synthetic_price = next(
            row for row in synthetic.data if row.metric == "fact:0"
        )
        self.assertEqual("SYNTHETIC", synthetic_price.asset_class)

    def test_source_evidence_boundary_never_upgrades_a_self_digest(self) -> None:
        unattested = adapt_native_public_snapshot(
            self.native_snapshot(), decision_at=self.as_of
        )
        unattested_source = unattested.information_events[0].source_artifacts[0]
        self.assertEqual(
            SourceEvidenceBoundary.LOCAL_INPUT_UNATTESTED,
            unattested_source.evidence_boundary,
        )
        self.assertEqual(SourceQuality.UNVERIFIED, unattested_source.quality)

        attested = adapt_native_public_snapshot(
            self.native_snapshot(attested=True), decision_at=self.as_of
        )
        attested_source = attested.information_events[0].source_artifacts[0]
        self.assertEqual(
            SourceEvidenceBoundary.SOURCE_ATTESTED,
            attested_source.evidence_boundary,
        )
        self.assertEqual(SourceQuality.VERIFIED_SECONDARY, attested_source.quality)
        self.assertIsNotNone(attested_source.acquisition_receipt)
        self.assertNotEqual(SourceQuality.VERIFIED_PRIMARY, attested_source.quality)

        malformed = self.native_snapshot(attested=True)
        malformed["source_captures"][0]["record_digest"] = "f" * 64
        malformed.pop("native_market_snapshot_digest")
        malformed = self_digest(malformed, "native_market_snapshot_digest")
        with self.assertRaisesRegex(
            V31MarketAdapterError, "SOURCE_CAPTURE_RECORD_DIGEST_INVALID"
        ):
            adapt_native_public_snapshot(malformed, decision_at=self.as_of)

        unrelated = self.native_snapshot(attested=True)
        capture = unrelated["source_captures"][0]
        capture["raw_body_sha256"] = "b" * 64
        capture.pop("record_digest")
        capture["record_digest"] = canonical_digest(capture)
        unrelated.pop("native_market_snapshot_digest")
        unrelated = self_digest(unrelated, "native_market_snapshot_digest")
        with self.assertRaisesRegex(
            V31MarketAdapterError, "SOURCE_ATTESTATION_FACT_BINDING_INVALID"
        ):
            adapt_native_public_snapshot(unrelated, decision_at=self.as_of)

    def test_lagged_closed_market_fact_keeps_its_reference_time(self) -> None:
        snapshot = self.native_snapshot(attested=True)
        facts = [dict(row) for row in snapshot["market_information_snapshot"]["facts"]]
        target = next(row for row in facts if row["fact_id"] == "fact:0")
        target["observed_at"] = "2026-08-06T11:00:00Z"
        information = build_market_information_snapshot(
            run_id=snapshot["run_id"],
            cycle_index=snapshot["cycle_index"],
            symbol=snapshot["instrument_id"],
            as_of=self.as_of_text,
            facts=facts,
        )
        snapshot["market_information_snapshot"] = information
        snapshot.pop("native_market_snapshot_digest")
        snapshot = self_digest(snapshot, "native_market_snapshot_digest")

        adapted = adapt_native_public_snapshot(snapshot, decision_at=self.as_of)
        datum = next(row for row in adapted.data if row.metric == "fact:0")
        self.assertEqual(datum.as_of, datum.observed_at)
        self.assertLess(datum.as_of, datum.available_at)

    def test_adapter_ids_are_deterministic_content_addressed_genesis(self) -> None:
        snapshot = self.synthetic_snapshot()
        first = adapt_synthetic_fixture_snapshot(
            snapshot,
            run_id="genesis-series",
            cycle_index=1,
            as_of=self.as_of,
            decision_at=self.as_of,
        )
        repeated = adapt_synthetic_fixture_snapshot(
            snapshot,
            run_id="genesis-series",
            cycle_index=1,
            as_of=self.as_of,
            decision_at=self.as_of,
        )
        next_cycle = adapt_synthetic_fixture_snapshot(
            snapshot,
            run_id="genesis-series",
            cycle_index=2,
            as_of=self.as_of,
            decision_at=self.as_of,
        )
        changed_snapshot = dict(snapshot)
        changed_snapshot["collector_id"] = "SYNTHETIC_TEN_CATEGORY_COLLECTOR_V2"
        changed_same_cycle = adapt_synthetic_fixture_snapshot(
            changed_snapshot,
            run_id="genesis-series",
            cycle_index=1,
            as_of=self.as_of,
            decision_at=self.as_of,
        )
        first_event = first.information_events[0]
        repeated_event = repeated.information_events[0]
        next_event = next_cycle.information_events[0]
        self.assertEqual(first_event.event_id, repeated_event.event_id)
        self.assertEqual(
            information_event_digest(first_event),
            information_event_digest(repeated_event),
        )
        self.assertNotEqual(first_event.event_id, next_event.event_id)
        self.assertNotEqual(
            first_event.event_id, changed_same_cycle.information_events[0].event_id
        )
        self.assertIn("capture-genesis", first_event.event_id)
        for result in (first, repeated, next_cycle, changed_same_cycle):
            self.assertEqual(
                "GENESIS_PER_IMMUTABLE_SNAPSHOT", result.revision_semantics
            )
            event = result.information_events[0]
            self.assertEqual(1, event.revision)
            self.assertIsNone(event.previous_revision_digest)
            self.assertIsNone(event.revised_at)
            self.assertTrue(all(row.revision == 1 for row in result.data))
            self.assertTrue(all("genesis" in row.datum_id for row in result.data))

    def test_liquidation_news_and_macro_are_unknown_not_zero(self) -> None:
        result = adapt_native_public_snapshot(
            self.native_snapshot(), decision_at=self.as_of
        )
        required = {
            "LIQUIDATION",
            "NEWS_EVENTS_AND_REACTION",
            "CROSS_MARKET_AND_MACRO",
        }
        unknowns = [row for row in result.data if row.category in required]
        self.assertEqual(required, {row.category for row in unknowns})
        self.assertTrue(all(row.value is None for row in unknowns))
        self.assertTrue(all(row.missingness is Missingness.SOURCE_UNAVAILABLE for row in unknowns))
        self.assertTrue(all(row.raw_ref is None and row.raw_sha256 is None for row in unknowns))
        self.assertNotIn("0", {row.value for row in unknowns})

    def test_absent_categories_are_materialized_as_explicit_unknown(self) -> None:
        snapshot = self.synthetic_snapshot()
        snapshot["facts"] = [snapshot["facts"][0]]
        result = adapt_synthetic_fixture_snapshot(
            snapshot,
            run_id="synthetic-sparse",
            cycle_index=1,
            as_of=self.as_of,
            decision_at=self.as_of,
        )
        statuses = {
            row.category: row
            for row in result.data
            if row.datum_id.find("v31-adapter-unknown") >= 0
        }
        self.assertIn("LIQUIDATION", statuses)
        self.assertIn("NEWS_EVENTS_AND_REACTION", statuses)
        self.assertIn("CROSS_MARKET_AND_MACRO", statuses)
        self.assertTrue(all(row.value is None for row in statuses.values()))
        self.assertTrue(
            all(
                row.missing_reason == "CATEGORY_NOT_PRESENT_IN_SOURCE_SNAPSHOT"
                for row in statuses.values()
            )
        )

    def test_future_snapshot_and_digest_drift_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            V31MarketAdapterError, "INFORMATION_EVENT_PIT_FUTURE_AVAILABLE"
        ):
            adapt_synthetic_fixture_snapshot(
                self.synthetic_snapshot(),
                run_id="synthetic-future",
                cycle_index=1,
                as_of=self.as_of,
                decision_at=self.as_of - timedelta(seconds=1),
            )

        native = self.native_snapshot()
        native["mark_price"] = "999"
        with self.assertRaisesRegex(
            V31MarketAdapterError, "V31_NATIVE_SNAPSHOT_DIGEST_INVALID"
        ):
            adapt_native_public_snapshot(native, decision_at=self.as_of)


if __name__ == "__main__":
    unittest.main()
