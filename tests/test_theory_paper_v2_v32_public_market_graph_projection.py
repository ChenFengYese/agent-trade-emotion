from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from tests.test_theory_paper_v2_v32_public_source_collector import (
    BundleTransport,
    RUN_ID,
    SERVER_MS,
    SequenceClock,
    authority,
    raw_bundle,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
    self_digest,
)
from trade_system.theory_paper_v2.infrastructure import (
    v32_incremental_market_graph as incremental_graph_module,
)
from trade_system.theory_paper_v2.infrastructure import (
    v32_public_market_graph_projection as graph_projection_module,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_market_graph_projection import (
    EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD,
    GRAPH_PROJECTION_DIGEST_FIELD,
    GRAPH_REGISTRY_DIGEST_FIELD,
    PROJECTION_CLOSURE_DIGEST_FIELD,
    V32PublicMarketGraphProjectionError,
    build_v32_public_market_graph_projection_v1,
    build_v32_verified_graph_dependency_registry_v1,
    v32_public_graph_verification_scope_v1,
    verify_v32_public_market_graph_projection_v1,
    verify_v32_verified_graph_dependency_registry_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    V32RawFirstOkxPublicBundleCollector,
)
from trade_system.theory_paper_v2.infrastructure.v32_incremental_market_graph import (
    verify_v32_market_knowledge_graph_transition,
)


class _StableCustomMapping(Mapping[str, object]):
    def __init__(self, value: Mapping[str, object]) -> None:
        self._value = value

    def __getitem__(self, key: str) -> object:
        return self._value[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._value)

    def __len__(self) -> int:
        return len(self._value)


class V32PublicMarketGraphProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_temp = tempfile.TemporaryDirectory()
        store = LocalV32CycleSourceAdmissionStore(Path(cls.base_temp.name))
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(raw_bundle()),
            clock=SequenceClock(),
            store=store,
        )
        result = collector.collect_and_qualify(
            qualification_id="q-v32-graph-projection",
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=authority(),
        )
        cls.base_analysis = result.public_market_analysis_bundle
        cls.base_projection = build_v32_public_market_graph_projection_v1(
            cls.base_analysis
        )
        cls.base_registry = build_v32_verified_graph_dependency_registry_v1(
            graph_projection=cls.base_projection,
            analysis_bundle=cls.base_analysis,
            decision_time="2026-08-07T00:00:06Z",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.base_temp.cleanup()

    def setUp(self) -> None:
        # The raw bundle, projection and registry are immutable test inputs.
        # Build them once, then copy their pure JSON shapes so every method may
        # mutate a local control without repeating collection and graph build.
        self.analysis = deepcopy(type(self).base_analysis)
        self.projection = deepcopy(type(self).base_projection)
        self.registry = deepcopy(type(self).base_registry)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def _collect_analysis_for_cycle(
        self, *, cycle_index: int, base: datetime, bundle: dict | None = None
    ) -> dict:
        class CycleClock:
            def __init__(self, start: datetime) -> None:
                self.values = iter(
                    [
                        start + timedelta(seconds=1),
                        start + timedelta(seconds=2),
                        start + timedelta(seconds=4),
                        start + timedelta(seconds=5),
                        start + timedelta(seconds=6),
                    ]
                )

            def __call__(self) -> str:
                return next(self.values).isoformat().replace("+00:00", "Z")

        bundle = raw_bundle() if bundle is None else deepcopy(bundle)
        request_started_at = (base + timedelta(seconds=2)).isoformat().replace(
            "+00:00", "Z"
        )
        response_received_at = (base + timedelta(seconds=3)).isoformat().replace(
            "+00:00", "Z"
        )
        for component in bundle["components"]:
            component["request_started_at"] = request_started_at
            component["response_received_at"] = response_received_at
        store = LocalV32CycleSourceAdmissionStore(
            Path(self.temp.name) / f"cycle-{cycle_index:04d}"
        )
        return V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(bundle),
            clock=CycleClock(base),
            store=store,
        ).collect_and_qualify(
            qualification_id=f"q-v32-graph-projection-cycle-{cycle_index:04d}",
            run_id=RUN_ID,
            cycle_index=cycle_index,
            active_authority=authority(),
        ).public_market_analysis_bundle

    def _rolling_bundle(self, *, fifteen_minute_steps: int) -> dict:
        shifted_server_ms = SERVER_MS + (900_000 * fifteen_minute_steps)
        shifted = raw_bundle()
        intervals = {
            "CLOSED_CANDLES_15M": 900_000,
            "CLOSED_CANDLES_1H": 3_600_000,
            "CLOSED_CANDLES_4H": 14_400_000,
            "CLOSED_CANDLES_1D": 86_400_000,
        }

        def shifted_candles(interval_ms: int) -> list[list[str]]:
            bucket = (shifted_server_ms // interval_ms) * interval_ms
            rows: list[list[str]] = []
            for index in range(20):
                opened = bucket - ((20 - index) * interval_ms)
                close = 60_000 + index
                rows.append(
                    [
                        str(opened),
                        str(close - 1),
                        str(close + 3),
                        str(close - 4),
                        str(close),
                        str(100 + index),
                        str(100 + index),
                        str((100 + index) * close),
                        "1",
                    ]
                )
            return rows

        def shift_provider_times(value: object) -> object:
            if isinstance(value, list):
                return [shift_provider_times(item) for item in value]
            if not isinstance(value, dict):
                return value
            result: dict[str, object] = {}
            for key, item in value.items():
                if key in {
                    "ts",
                    "prevFundingTime",
                    "fundingTime",
                    "nextFundingTime",
                } and isinstance(item, str) and item.isdigit():
                    result[key] = str(
                        int(item) + (900_000 * fifteen_minute_steps)
                    )
                else:
                    result[key] = shift_provider_times(item)
            return result

        for component in shifted["components"]:
            component_id = component["component_id"]
            if component_id in intervals:
                interval_ms = intervals[component_id]
                component["query"]["after"] = str(
                    (shifted_server_ms // interval_ms) * interval_ms
                )
                body = {
                    "code": "0",
                    "msg": "",
                    "data": shifted_candles(interval_ms),
                }
            else:
                body = loads_json_strict(component["body_utf8"])
                body = shift_provider_times(body)
            component["body_utf8"] = canonical_bytes(body).decode("utf-8")
        return shifted

    def test_graph_node_presence_is_not_misreported_as_native_axis_coverage(self) -> None:
        self.assertEqual(12, len(self.projection["source_event_node_ids"]))
        self.assertEqual(len(self.analysis["datums"]), len(self.projection["datum_node_ids"]))
        self.assertEqual(13, len(self.projection["axis_node_ids"]))
        self.assertFalse(self.projection["twelve_axes_native"])
        self.assertEqual(
            [
                "CROWDING_DIRECTION",
                "PARTICIPATION_AND_ACTIVE_FLOW",
                "PRICE_DIRECTIONAL_PRESSURE",
                "VOLATILITY_AND_TAIL_STRESS",
            ],
            self.projection["native_axis_ids"],
        )
        self.assertEqual(
            ["STRUCTURE_PERSISTENCE"], self.projection["proxy_axis_ids"]
        )
        self.assertEqual([], self.projection["derived_axis_ids"])
        self.assertEqual(
            [
                "ATTENTION_AND_AUDIENCE_RESPONSE",
                "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
                "EVENT_AND_NARRATIVE_REACTION",
                "FORCED_DELEVERAGING_PRESSURE",
                "LEVERAGE_CHANGE",
                "LIQUIDITY_RESILIENCE",
                "TIMEFRAME_COHERENCE",
            ],
            self.projection["unknown_axis_ids"],
        )
        self.assertTrue(self.projection["unknown_retained"])
        self.assertTrue(self.projection["other_retained"])
        self.assertIn("market-axis:OTHER", self.projection["axis_node_ids"])
        self.assertIn("AXIS:LIQUIDITY_RESILIENCE", self.registry["members"])
        self.assertIn("TIMEFRAME:15M", self.registry["members"])
        self.assertIn("REQUEST:ORDER_BOOK", self.registry["members"])

    def test_rejected_book_snapshot_and_oi_level_remain_explicit_in_graph(self) -> None:
        graph = self.projection["knowledge_graph"]
        latest = {
            row["node_id"]: row
            for row in graph["node_history"]
            if row["node_digest"]
            == graph["latest_node_digests"].get(row["node_id"])
        }
        liquidity = latest["market-axis:LIQUIDITY_RESILIENCE"]
        self.assertIn("ADMISSION:REJECTED", liquidity["dependency_group_ids"])
        self.assertIn("EVIDENCE_ROLE:UNKNOWN", liquidity["dependency_group_ids"])
        self.assertIn(
            "SOURCE_KIND:PUBLIC_ORDER_BOOK_SNAPSHOT",
            liquidity["dependency_group_ids"],
        )
        self.assertIn(
            "SOURCE_CLAIM_CEILING:SINGLE_BOOK_STATE_NOT_RESILIENCE",
            liquidity["limitations"],
        )
        leverage = latest["market-axis:LEVERAGE_CHANGE"]
        self.assertIn("AXIS_ADMISSION:UNKNOWN", leverage["limitations"])
        self.assertIn(
            "SOURCE_CLAIM_CEILING:OPEN_INTEREST_LEVEL_ONLY",
            leverage["limitations"],
        )

    def test_projection_and_registry_reconstruct_exactly(self) -> None:
        self.assertEqual(
            self.projection[GRAPH_PROJECTION_DIGEST_FIELD],
            verify_v32_public_market_graph_projection_v1(
                self.projection, analysis_bundle=self.analysis
            ),
        )
        self.assertEqual(
            self.registry[GRAPH_REGISTRY_DIGEST_FIELD],
            verify_v32_verified_graph_dependency_registry_v1(
                self.registry,
                graph_projection=self.projection,
                analysis_bundle=self.analysis,
            ),
        )
        self.assertEqual(
            self.analysis[ANALYSIS_BUNDLE_DIGEST_FIELD],
            self.projection["analysis_bundle_digest"],
        )

    def test_cycle1_builds_closure_from_complete_graph_once(self) -> None:
        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=graph_projection_module._build_evidence_dependency_closure,
        ) as full_history_builder:
            rebuilt = build_v32_public_market_graph_projection_v1(self.analysis)
        full_history_builder.assert_called_once_with(rebuilt["knowledge_graph"])
        self.assertEqual(
            canonical_digest(rebuilt["evidence_dependency_closure"]),
            rebuilt[PROJECTION_CLOSURE_DIGEST_FIELD],
        )

    def test_registry_build_and_verify_each_rebuild_current_closure_once(
        self,
    ) -> None:
        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=graph_projection_module._build_evidence_dependency_closure,
        ) as full_history_builder:
            registry = build_v32_verified_graph_dependency_registry_v1(
                graph_projection=self.projection,
                analysis_bundle=self.analysis,
                decision_time="2026-08-07T00:00:06Z",
            )
        full_history_builder.assert_called_once_with(
            self.projection["knowledge_graph"]
        )

        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=graph_projection_module._build_evidence_dependency_closure,
        ) as full_history_verifier:
            verify_v32_verified_graph_dependency_registry_v1(
                registry,
                graph_projection=self.projection,
                analysis_bundle=self.analysis,
            )
        full_history_verifier.assert_called_once_with(
            self.projection["knowledge_graph"]
        )

        second = self._collect_analysis_for_cycle(
            cycle_index=2,
            base=datetime(2026, 8, 7, 0, 0, 7, tzinfo=UTC),
        )
        transitioned = build_v32_public_market_graph_projection_v1(
            second,
            previous_projection=self.projection,
        )
        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=graph_projection_module._build_evidence_dependency_closure,
        ) as transitioned_full_history_builder:
            build_v32_verified_graph_dependency_registry_v1(
                graph_projection=transitioned,
                analysis_bundle=second,
                previous_projection=self.projection,
                decision_time="2026-08-07T00:00:13Z",
            )
        transitioned_full_history_builder.assert_called_once_with(
            transitioned["knowledge_graph"]
        )

    def test_verification_scope_reuses_one_success_only_inside_scope(self) -> None:
        original_builder = graph_projection_module._build_evidence_dependency_closure
        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=original_builder,
        ) as full_history_builder:
            with v32_public_graph_verification_scope_v1():
                verify_v32_public_market_graph_projection_v1(
                    self.projection,
                    analysis_bundle=self.analysis,
                )
                verify_v32_verified_graph_dependency_registry_v1(
                    self.registry,
                    graph_projection=self.projection,
                    analysis_bundle=self.analysis,
                )
                self.assertEqual(full_history_builder.call_count, 1)

            verify_v32_public_market_graph_projection_v1(
                self.projection,
                analysis_bundle=self.analysis,
            )
            self.assertEqual(full_history_builder.call_count, 2)

    def test_verification_scope_does_not_cache_failures(self) -> None:
        forged = deepcopy(self.projection)
        forged["unknown_retained"] = not forged["unknown_retained"]
        forged = self_digest(forged, GRAPH_PROJECTION_DIGEST_FIELD)
        original_builder = graph_projection_module._build_evidence_dependency_closure
        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=original_builder,
        ) as full_history_builder, v32_public_graph_verification_scope_v1():
            with self.assertRaises(V32PublicMarketGraphProjectionError):
                verify_v32_public_market_graph_projection_v1(
                    forged,
                    analysis_bundle=self.analysis,
                )
            with self.assertRaises(V32PublicMarketGraphProjectionError):
                verify_v32_public_market_graph_projection_v1(
                    forged,
                    analysis_bundle=self.analysis,
                )
            self.assertEqual(full_history_builder.call_count, 2)

    def test_verification_scope_key_and_verifier_share_strict_snapshot(
        self,
    ) -> None:
        projection = deepcopy(self.projection)
        projection_before_mutation = deepcopy(projection)
        original_builder = graph_projection_module._build_evidence_dependency_closure
        original_canonical_bytes = graph_projection_module.canonical_bytes
        key_completed = False

        def canonicalize_then_mutate_original(value):
            nonlocal key_completed
            encoded = original_canonical_bytes(value)
            if (
                not key_completed
                and type(value) is dict
                and set(value)
                == {"document", "analysis_bundle", "previous_projection"}
            ):
                key_completed = True
                projection["unknown_retained"] = not projection[
                    "unknown_retained"
                ]
            return encoded

        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=original_builder,
        ) as full_history_builder, v32_public_graph_verification_scope_v1(), mock.patch.object(
            graph_projection_module,
            "canonical_bytes",
            side_effect=canonicalize_then_mutate_original,
        ):
            self.assertEqual(
                verify_v32_public_market_graph_projection_v1(
                    projection,
                    analysis_bundle=self.analysis,
                ),
                projection_before_mutation[GRAPH_PROJECTION_DIGEST_FIELD],
            )
            self.assertTrue(key_completed)
            verify_v32_public_market_graph_projection_v1(
                projection_before_mutation,
                analysis_bundle=self.analysis,
            )
            self.assertEqual(full_history_builder.call_count, 1)

            with self.assertRaises(V32PublicMarketGraphProjectionError):
                verify_v32_public_market_graph_projection_v1(
                    projection,
                    analysis_bundle=self.analysis,
                )
            with self.assertRaises(V32PublicMarketGraphProjectionError):
                verify_v32_public_market_graph_projection_v1(
                    projection,
                    analysis_bundle=self.analysis,
                )
            # Both calls reject the caller's new content before a closure
            # rebuild; neither can consume the cached original snapshot.
            self.assertEqual(full_history_builder.call_count, 1)

    def test_custom_mapping_is_never_memoized(self) -> None:
        projection = _StableCustomMapping(self.projection)
        original_builder = graph_projection_module._build_evidence_dependency_closure
        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=original_builder,
        ) as full_history_builder, v32_public_graph_verification_scope_v1():
            verify_v32_public_market_graph_projection_v1(
                projection,
                analysis_bundle=self.analysis,
            )
            verify_v32_public_market_graph_projection_v1(
                projection,
                analysis_bundle=self.analysis,
            )
            self.assertEqual(full_history_builder.call_count, 2)

    def test_async_child_cannot_reuse_parent_verification_scope(self) -> None:
        async def scenario() -> None:
            async def child() -> None:
                verify_v32_public_market_graph_projection_v1(
                    self.projection,
                    analysis_bundle=self.analysis,
                )

            with v32_public_graph_verification_scope_v1():
                verify_v32_public_market_graph_projection_v1(
                    self.projection,
                    analysis_bundle=self.analysis,
                )
                await asyncio.create_task(child())

        original_builder = graph_projection_module._build_evidence_dependency_closure
        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            wraps=original_builder,
        ) as full_history_builder:
            asyncio.run(scenario())
            self.assertEqual(full_history_builder.call_count, 2)

    def test_registry_single_rebuild_still_rejects_self_resigned_closure_tamper(
        self,
    ) -> None:
        forged = deepcopy(self.projection)
        row = forged["evidence_dependency_closure"][0]
        row["evidence_refs"] = sorted(
            [f"{row['evidence_refs'][0]}:SELF_RESIGNED_TAMPER"]
        )
        forged["evidence_dependency_closure"][0] = self_digest(
            row,
            EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD,
        )
        forged[PROJECTION_CLOSURE_DIGEST_FIELD] = canonical_digest(
            forged["evidence_dependency_closure"]
        )
        forged = self_digest(forged, GRAPH_PROJECTION_DIGEST_FIELD)

        with self.assertRaisesRegex(
            V32PublicMarketGraphProjectionError,
            "CLOSURE_RECONSTRUCTION_MISMATCH",
        ):
            build_v32_verified_graph_dependency_registry_v1(
                graph_projection=forged,
                analysis_bundle=self.analysis,
                decision_time="2026-08-07T00:00:06Z",
            )

    def test_graph_edges_are_explicitly_noncausal(self) -> None:
        graph = self.projection["knowledge_graph"]
        self.assertGreater(len(graph["association_history"]), len(self.analysis["datums"]))
        self.assertTrue(
            all(
                row["association_type"] == "OBSERVED_ASSOCIATION"
                and row["interpretation_boundary"] == "ASSOCIATIONAL_NOT_CAUSAL"
                and row["estimate_interval"]["scale"] == "NOT_ESTIMATED"
                for row in graph["association_history"]
            )
        )

    def test_self_resigned_projection_cannot_drop_axis_node(self) -> None:
        forged = deepcopy(self.projection)
        forged["axis_node_ids"] = forged["axis_node_ids"][:-1]
        forged = self_digest(forged, GRAPH_PROJECTION_DIGEST_FIELD)
        with self.assertRaises(V32PublicMarketGraphProjectionError):
            verify_v32_public_market_graph_projection_v1(
                forged, analysis_bundle=self.analysis
            )

    def test_self_resigned_projection_cannot_promote_native_axis_coverage(self) -> None:
        forged = deepcopy(self.projection)
        forged["twelve_axes_native"] = True
        forged["native_axis_ids"] = sorted(
            row["axis_id"]
            for row in self.analysis["axis_source_evidence"]
            if row["axis_id"] != "OTHER"
        )
        forged["unknown_axis_ids"] = []
        forged = self_digest(forged, GRAPH_PROJECTION_DIGEST_FIELD)
        with self.assertRaises(V32PublicMarketGraphProjectionError):
            verify_v32_public_market_graph_projection_v1(
                forged, analysis_bundle=self.analysis
            )

    def test_registry_cannot_add_agent_invented_dependency(self) -> None:
        forged = deepcopy(self.registry)
        forged["members"] = sorted([*forged["members"], "ACTOR:INSTITUTION_PROVEN"])
        forged = self_digest(forged, GRAPH_REGISTRY_DIGEST_FIELD)
        with self.assertRaises(V32PublicMarketGraphProjectionError):
            verify_v32_verified_graph_dependency_registry_v1(
                forged,
                graph_projection=self.projection,
                analysis_bundle=self.analysis,
            )

    def test_registry_closes_each_evidence_digest_over_all_incident_groups(self) -> None:
        graph = self.projection["knowledge_graph"]
        datum_node = next(
            row
            for row in graph["node_history"]
            if row["node_id"] == "market-datum:open-interest-btc"
            and row["node_digest"]
            == graph["latest_node_digests"][row["node_id"]]
        )
        closure = next(
            row
            for row in self.registry["evidence_dependency_closure"]
            if row["evidence_digest"] == datum_node["payload_digest"]
        )
        self.assertEqual(
            ["market-datum:open-interest-btc"], closure["node_ids"]
        )
        self.assertIn(
            "provenance:event-to-datum:open-interest-btc",
            closure["association_ids"],
        )
        self.assertIn("PROJECTION:EVENT_DATUM", closure["dependency_group_ids"])
        self.assertTrue(
            set(datum_node["dependency_group_ids"]).issubset(
                closure["dependency_group_ids"]
            )
        )

    def test_same_datum_cannot_claim_disjoint_dependency_group_subsets(self) -> None:
        forged = deepcopy(self.registry)
        index = next(
            index
            for index, row in enumerate(forged["evidence_dependency_closure"])
            if "market-datum:open-interest-btc" in row["node_ids"]
        )
        original = forged["evidence_dependency_closure"][index]
        midpoint = max(1, len(original["dependency_group_ids"]) // 2)
        left = deepcopy(original)
        right = deepcopy(original)
        left["dependency_group_ids"] = original["dependency_group_ids"][:midpoint]
        right["dependency_group_ids"] = original["dependency_group_ids"][midpoint:]
        self.assertTrue(right["dependency_group_ids"])
        left = self_digest(left, EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD)
        right = self_digest(right, EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD)
        forged["evidence_dependency_closure"][index : index + 1] = [left, right]
        forged = self_digest(forged, GRAPH_REGISTRY_DIGEST_FIELD)
        with self.assertRaises(V32PublicMarketGraphProjectionError):
            verify_v32_verified_graph_dependency_registry_v1(
                forged,
                graph_projection=self.projection,
                analysis_bundle=self.analysis,
            )

    def test_registry_forbids_future_projection(self) -> None:
        with self.assertRaisesRegex(
            V32PublicMarketGraphProjectionError, "FUTURE_PROJECTION_FORBIDDEN"
        ):
            build_v32_verified_graph_dependency_registry_v1(
                graph_projection=self.projection,
                analysis_bundle=self.analysis,
                decision_time="2026-08-07T00:00:02Z",
            )

    def test_second_cycle_appends_graph_revision_and_binds_predecessor(self) -> None:
        second = self._collect_analysis_for_cycle(
            cycle_index=2,
            base=datetime(2026, 8, 7, 0, 0, 7, tzinfo=UTC),
        )
        with self.assertRaisesRegex(
            V32PublicMarketGraphProjectionError,
            "PREVIOUS_PROJECTION_REQUIRED",
        ):
            build_v32_public_market_graph_projection_v1(second)
        transitioned = build_v32_public_market_graph_projection_v1(
            second, previous_projection=self.projection
        )
        self.assertEqual(2, transitioned["knowledge_graph_revision"])
        self.assertEqual(
            self.projection[GRAPH_PROJECTION_DIGEST_FIELD],
            transitioned["previous_graph_projection_digest"],
        )
        self.assertEqual(
            self.projection["knowledge_graph_digest"],
            transitioned["graph_delta"]["base_graph_digest"],
        )
        self.assertEqual(
            transitioned[GRAPH_PROJECTION_DIGEST_FIELD],
            verify_v32_public_market_graph_projection_v1(
                transitioned,
                analysis_bundle=second,
                previous_projection=self.projection,
            ),
        )
        transitioned_registry = build_v32_verified_graph_dependency_registry_v1(
            graph_projection=transitioned,
            analysis_bundle=second,
            previous_projection=self.projection,
            decision_time="2026-08-07T00:00:13Z",
        )
        self.assertEqual(
            transitioned_registry[GRAPH_REGISTRY_DIGEST_FIELD],
            verify_v32_verified_graph_dependency_registry_v1(
                transitioned_registry,
                graph_projection=transitioned,
                analysis_bundle=second,
                previous_projection=self.projection,
            ),
        )
        axis_history = [
            row
            for row in transitioned["knowledge_graph"]["node_history"]
            if row["node_id"] == "market-axis:LIQUIDITY_RESILIENCE"
        ]
        self.assertEqual([1, 2], [row["revision"] for row in axis_history])
        self.assertEqual(
            graph_projection_module._build_evidence_dependency_closure(
                transitioned["knowledge_graph"]
            ),
            transitioned["evidence_dependency_closure"],
        )
        self.assertEqual(
            transitioned["evidence_dependency_closure"],
            transitioned_registry["evidence_dependency_closure"],
        )
        self.assertEqual(
            canonical_digest(transitioned["evidence_dependency_closure"]),
            transitioned[PROJECTION_CLOSURE_DIGEST_FIELD],
        )

    def test_rolling_15m_window_keeps_cumulative_dependencies_complete(
        self,
    ) -> None:
        base = datetime(2026, 8, 7, 0, 15, 0, tzinfo=UTC)
        second = self._collect_analysis_for_cycle(
            cycle_index=2,
            base=base,
            bundle=self._rolling_bundle(fifteen_minute_steps=1),
        )
        transitioned = build_v32_public_market_graph_projection_v1(
            second,
            previous_projection=self.projection,
        )
        self.assertEqual(
            transitioned[GRAPH_PROJECTION_DIGEST_FIELD],
            verify_v32_public_market_graph_projection_v1(
                transitioned,
                analysis_bundle=second,
                previous_projection=self.projection,
            ),
        )
        self.assertEqual(
            sorted(transitioned["knowledge_graph"]["dependency_index"]),
            transitioned["dependency_group_ids"],
        )
        self.assertEqual(
            transitioned["dependency_group_ids"],
            sorted(
                {
                    dependency
                    for row in transitioned["evidence_dependency_closure"]
                    for dependency in row["dependency_group_ids"]
                }
            ),
        )
        registry = build_v32_verified_graph_dependency_registry_v1(
            graph_projection=transitioned,
            analysis_bundle=second,
            previous_projection=self.projection,
            decision_time=(base + timedelta(seconds=6)).isoformat().replace(
                "+00:00", "Z"
            ),
        )
        self.assertEqual(
            registry[GRAPH_REGISTRY_DIGEST_FIELD],
            verify_v32_verified_graph_dependency_registry_v1(
                registry,
                graph_projection=transitioned,
                analysis_bundle=second,
                previous_projection=self.projection,
            ),
        )

    def test_self_resigned_untouched_predecessor_closure_tamper_is_rejected(
        self,
    ) -> None:
        second_base = datetime(2026, 8, 7, 0, 15, 0, tzinfo=UTC)
        second = self._collect_analysis_for_cycle(
            cycle_index=2,
            base=second_base,
            bundle=self._rolling_bundle(fifteen_minute_steps=1),
        )
        transitioned = build_v32_public_market_graph_projection_v1(
            second,
            previous_projection=self.projection,
        )
        delta_node_ids = {
            row["node_id"] for row in transitioned["graph_delta"]["node_revisions"]
        }
        untouched_index = next(
            index
            for index, row in enumerate(
                transitioned["evidence_dependency_closure"]
            )
            if set(row["node_ids"]).isdisjoint(delta_node_ids)
        )
        forged = deepcopy(transitioned)
        original = forged["evidence_dependency_closure"][untouched_index]
        original_node_ids = list(original["node_ids"])
        original_association_ids = list(original["association_ids"])
        original["evidence_refs"] = sorted(
            [f"{original['evidence_refs'][0]}:SELF_RESIGNED_TAMPER"]
        )
        forged["evidence_dependency_closure"][untouched_index] = self_digest(
            original,
            EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD,
        )
        forged[PROJECTION_CLOSURE_DIGEST_FIELD] = canonical_digest(
            forged["evidence_dependency_closure"]
        )
        forged = self_digest(forged, GRAPH_PROJECTION_DIGEST_FIELD)
        self.assertEqual(
            original_node_ids,
            forged["evidence_dependency_closure"][untouched_index]["node_ids"],
        )
        self.assertEqual(
            original_association_ids,
            forged["evidence_dependency_closure"][untouched_index][
                "association_ids"
            ],
        )

        third_base = datetime(2026, 8, 7, 0, 30, 0, tzinfo=UTC)
        third = self._collect_analysis_for_cycle(
            cycle_index=3,
            base=third_base,
            bundle=self._rolling_bundle(fifteen_minute_steps=2),
        )
        with self.assertRaisesRegex(
            V32PublicMarketGraphProjectionError,
            "PREVIOUS_PROJECTION_INVALID",
        ):
            build_v32_public_market_graph_projection_v1(
                third,
                previous_projection=forged,
            )

    def test_v32_transition_rejects_self_resigned_dependency_index_tamper(
        self,
    ) -> None:
        second = self._collect_analysis_for_cycle(
            cycle_index=2,
            base=datetime(2026, 8, 7, 0, 0, 7, tzinfo=UTC),
        )
        transitioned = build_v32_public_market_graph_projection_v1(
            second,
            previous_projection=self.projection,
        )
        forged_graph = deepcopy(transitioned["knowledge_graph"])
        first_group = next(iter(forged_graph["dependency_index"]))
        forged_graph["dependency_index"][first_group][
            "node_revision_refs"
        ].append("market-datum:invented@999")
        forged_graph = self_digest(forged_graph, "graph_digest")
        with self.assertRaises(ValueError):
            verify_v32_market_knowledge_graph_transition(
                self.projection["knowledge_graph"],
                transitioned["graph_delta"],
                forged_graph,
                decision_at=transitioned["available_at"],
            )

    def test_self_resigned_predecessor_closure_tamper_is_rejected(self) -> None:
        second = self._collect_analysis_for_cycle(
            cycle_index=2,
            base=datetime(2026, 8, 7, 0, 0, 7, tzinfo=UTC),
        )
        forged = deepcopy(self.projection)
        closure_row = forged["evidence_dependency_closure"][0]
        invented_dependency = "ACTOR:INVENTED_PREDECESSOR_CLOSURE"
        closure_row["dependency_group_ids"] = sorted(
            [*closure_row["dependency_group_ids"], invented_dependency]
        )
        forged["evidence_dependency_closure"][0] = self_digest(
            closure_row, EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD
        )
        forged["dependency_group_ids"] = sorted(
            [*forged["dependency_group_ids"], invented_dependency]
        )
        forged[PROJECTION_CLOSURE_DIGEST_FIELD] = canonical_digest(
            forged["evidence_dependency_closure"]
        )
        forged = self_digest(forged, GRAPH_PROJECTION_DIGEST_FIELD)

        with self.assertRaisesRegex(
            V32PublicMarketGraphProjectionError,
            "PREVIOUS_PROJECTION_INVALID",
        ):
            build_v32_public_market_graph_projection_v1(
                second, previous_projection=forged
            )

    def test_cycle16_uses_bounded_delta_closure_without_full_history_rebuild(
        self,
    ) -> None:
        class HistoryReadForbidden(list):
            def __iter__(self):
                raise AssertionError(
                    "incremental closure must not inspect cumulative graph history"
                )

        graph_delta = self.projection["graph_delta"]
        accumulated_graph = deepcopy(self.projection["knowledge_graph"])
        accumulated_graph["revision"] = 16
        accumulated_graph["node_history"] = HistoryReadForbidden(
            [
                deepcopy(row)
                for _ in range(16)
                for row in graph_delta["node_revisions"]
            ]
        )
        accumulated_graph["association_history"] = HistoryReadForbidden(
            [
                deepcopy(row)
                for _ in range(16)
                for row in graph_delta["association_revisions"]
            ]
        )

        with mock.patch.object(
            graph_projection_module,
            "_build_evidence_dependency_closure",
            side_effect=AssertionError(
                "cycle 2+ must not rebuild closure from cumulative history"
            ),
        ) as full_history_builder:
            started = time.perf_counter()
            closure = (
                graph_projection_module._build_incremental_evidence_dependency_closure(
                    previous_projection=self.projection,
                    graph=accumulated_graph,
                    graph_delta=graph_delta,
                )
            )
            elapsed = time.perf_counter() - started
            full_history_builder.assert_not_called()

        self.assertEqual(
            16 * len(graph_delta["node_revisions"]),
            len(accumulated_graph["node_history"]),
        )
        self.assertEqual(
            16 * len(graph_delta["association_revisions"]),
            len(accumulated_graph["association_history"]),
        )
        self.assertEqual(
            self.projection["evidence_dependency_closure"],
            closure,
        )
        self.assertLess(elapsed, 1.0)

    def test_complete_cycle16_projection_and_registry_stay_below_120_seconds(
        self,
    ) -> None:
        fixture_started = time.perf_counter()
        origin = datetime(2026, 8, 7, 0, 0, 0, tzinfo=UTC)
        previous = self.projection

        def trusted_fixture_digest(graph, *, decision_at):
            # Cycles 2-15 only prepare an owned predecessor fixture. Repeating
            # both complete history scans at every preparatory cycle made this
            # one cycle-16 contract O(n^2). The unpatched cycle-16 build below
            # completely verifies the resulting cycle-15 graph before use.
            del decision_at
            return graph["graph_digest"]

        def trusted_fixture_transition(
            prior_graph,
            delta,
            graph,
            *,
            decision_at,
            prior_digest,
            prior_node_latest,
            prior_association_latest,
        ):
            # The builder already produced this fixture transition and the
            # final real cycle validates its complete accumulated predecessor.
            del (
                prior_graph,
                delta,
                decision_at,
                prior_digest,
                prior_node_latest,
                prior_association_latest,
            )
            return graph["graph_digest"]

        with (
            mock.patch.object(
                graph_projection_module,
                "verify_market_knowledge_graph",
                side_effect=trusted_fixture_digest,
            ) as projection_fixture_verifier,
            mock.patch.object(
                incremental_graph_module.v31_graph,
                "verify_market_knowledge_graph",
                side_effect=trusted_fixture_digest,
            ) as incremental_fixture_verifier,
            mock.patch.object(
                graph_projection_module,
                "_verify_projection_evidence_dependency_closure",
                wraps=graph_projection_module._verify_projection_evidence_dependency_closure_binding,
            ) as projection_fixture_closure_verifier,
            mock.patch.object(
                incremental_graph_module,
                "_verify_transition_after_verified_prior",
                side_effect=trusted_fixture_transition,
            ) as fixture_transition_verifier,
        ):
            for cycle_index in range(2, 16):
                base = origin + timedelta(seconds=7 * (cycle_index - 1))
                analysis = self._collect_analysis_for_cycle(
                    cycle_index=cycle_index,
                    base=base,
                )
                previous = build_v32_public_market_graph_projection_v1(
                    analysis,
                    previous_projection=previous,
                )
        self.assertEqual(14, projection_fixture_verifier.call_count)
        self.assertEqual(14, incremental_fixture_verifier.call_count)
        self.assertEqual(14, projection_fixture_closure_verifier.call_count)
        self.assertEqual(14, fixture_transition_verifier.call_count)

        final_analysis = self._collect_analysis_for_cycle(
            cycle_index=16,
            base=origin + timedelta(seconds=7 * 15),
        )
        final_predecessor = previous
        cycle_started = time.perf_counter()
        previous = build_v32_public_market_graph_projection_v1(
            final_analysis,
            previous_projection=final_predecessor,
        )
        decision_time = (
            origin + timedelta(seconds=(7 * 15) + 6)
        ).isoformat().replace("+00:00", "Z")
        with v32_public_graph_verification_scope_v1():
            registry = build_v32_verified_graph_dependency_registry_v1(
                graph_projection=previous,
                analysis_bundle=final_analysis,
                previous_projection=final_predecessor,
                decision_time=decision_time,
            )
            self.assertEqual(
                registry[GRAPH_REGISTRY_DIGEST_FIELD],
                verify_v32_verified_graph_dependency_registry_v1(
                    registry,
                    graph_projection=previous,
                    analysis_bundle=final_analysis,
                    previous_projection=final_predecessor,
                ),
            )
        cycle_elapsed = time.perf_counter() - cycle_started
        fixture_elapsed = time.perf_counter() - fixture_started

        graph = previous["knowledge_graph"]
        self.assertEqual(16, graph["revision"])
        self.assertEqual(610, len(self.projection["graph_delta"]["node_revisions"]))
        self.assertEqual(
            605,
            len(self.projection["graph_delta"]["association_revisions"]),
        )
        self.assertEqual(9_760, len(graph["node_history"]))
        self.assertEqual(9_680, len(graph["association_history"]))
        self.assertLess(cycle_elapsed, 120.0)
        self.assertLess(fixture_elapsed, 120.0)


if __name__ == "__main__":
    unittest.main()
