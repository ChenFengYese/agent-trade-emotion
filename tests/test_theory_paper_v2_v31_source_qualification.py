from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from trade_system.theory_paper_v2.application.v31_source_qualification import (
    COMPLETION_REF,
    FAILURE_REF,
    PLAN_REF,
    RESERVATION_REF,
    V31SourceQualificationWorkflowError,
    execute_v31_source_qualification,
    initialize_v31_source_qualification,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v31_source_qualification import (
    APPROVED_V31_THEORY_SHA256,
    OPTIONAL_FAILURE_KEYS,
    OPTIONAL_REQUEST_IDS,
    REQUIRED_REQUEST_IDS,
    REQUEST_SPECS,
    V31SourceQualificationError,
    seal_v31_source_qualification_plan,
    transition_v31_source_qualification_checkpoint,
    validate_v31_source_qualification_collection,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    HttpCapture,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.okx_public import (
    OkxPublicCollectionError,
    OkxPublicFreshCollector,
)
from trade_system.theory_paper_v2.infrastructure.native_market_collector import (
    OkxNativeMarketCollector,
)
from trade_system.theory_paper_v2.infrastructure.v31_market_adapter import (
    V31MarketAdapterError,
    adapt_native_public_snapshot,
    native_financial_market_economics_input,
)
from trade_system.theory_paper_v2.infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
    V31SourceQualificationStoreError,
)
from trade_system.theory_paper_v2.presentation.v31_source_qualification_composition import (
    initialize_local_v31_source_qualification,
    local_v31_source_qualification_status,
)


QUALIFICATION_ID = "v31-source-qualification-unit-20260806"
CREATED_AT = "2026-08-06T11:59:59Z"
WORKFLOW_TIME = "2026-08-06T12:01:00Z"
MILLISECOND_WORKFLOW_TIME = "2026-08-06T12:01:00.871Z"
SERVER_TIME_MS = 1_786_017_600_000


class _AdvancingClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 6, 12, 0, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(milliseconds=250)
        return value


def _okx_payload(data: list[object]) -> bytes:
    return json.dumps(
        {"code": "0", "msg": "", "data": data},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _candle_rows(*, interval_ms: int) -> list[list[str]]:
    current_bucket = (SERVER_TIME_MS // interval_ms) * interval_ms
    rows: list[list[str]] = []
    for index in range(20):
        timestamp_ms = current_bucket - ((20 - index) * interval_ms)
        close = 60_000 + index
        rows.append(
            [
                str(timestamp_ms),
                str(close - 2),
                str(close + 4),
                str(close - 5),
                str(close),
                str(100 + index),
                str(100 + index),
                str((100 + index) * close),
                "1",
            ]
        )
    return rows


class _NoNetworkOkxTransport:
    """Deterministic public-transport fixture; it never opens a socket."""

    def __init__(self, *, clock: _AdvancingClock) -> None:
        self.clock = clock
        self.urls: list[str] = []
        self.instrument_row = {
            "instId": "BTC-USDT-SWAP",
            "state": "live",
            "ctVal": "0.01",
            "ctValCcy": "BTC",
            "ctMult": "1",
            "lotSz": "0.01",
            "minSz": "0.01",
            "tickSz": "0.1",
            "ctType": "linear",
            "settleCcy": "USDT",
        }

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.urls.append(url)
        if timeout != 15.0:
            raise AssertionError("qualification timeout drifted")
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        if parsed.path in {
            "/api/v5/public/open-interest",
            "/api/v5/public/funding-rate",
            "/api/v5/market/books",
            "/api/v5/market/trades",
        }:
            raise OkxPublicCollectionError("FIXTURE_OPTIONAL_SOURCE_UNAVAILABLE")
        if parsed.path == "/api/v5/public/time":
            body = _okx_payload([{"ts": str(SERVER_TIME_MS)}])
        elif parsed.path == "/api/v5/public/instruments":
            body = _okx_payload([self.instrument_row])
        elif parsed.path == "/api/v5/market/ticker":
            body = _okx_payload(
                [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "last": "60000",
                        "bidPx": "59999",
                        "askPx": "60001",
                        "vol24h": "1000",
                        "volCcy24h": "200",
                        "ts": str(SERVER_TIME_MS),
                    }
                ]
            )
        elif parsed.path == "/api/v5/public/mark-price":
            body = _okx_payload(
                [{"instId": "BTC-USDT-SWAP", "markPx": "60000", "ts": str(SERVER_TIME_MS)}]
            )
        elif parsed.path == "/api/v5/market/history-candles":
            bar = query.get("bar", [""])[0]
            interval_ms = {
                "15m": 900_000,
                "1H": 3_600_000,
                "4H": 14_400_000,
                "1Dutc": 86_400_000,
            }[bar]
            body = _okx_payload(_candle_rows(interval_ms=interval_ms))
        else:  # pragma: no cover - the production collector owns this allowlist
            raise AssertionError(f"unexpected fixture URL: {url}")
        return HttpCapture(
            status=200,
            headers={"Content-Type": "application/json"},
            body=body,
            received_at=self.clock(),
            final_url=url,
        )


class _LeaseAssertingCollector:
    def __init__(
        self,
        *,
        store: LocalV31SourceQualificationStore,
        fail: bool = False,
    ) -> None:
        transport_clock = _AdvancingClock()
        transport = _NoNetworkOkxTransport(clock=transport_clock)
        self.delegate = OkxNativeMarketCollector(
            collector=OkxPublicFreshCollector(
                transport=transport,
                clock=transport_clock,
                timeout=15.0,
            )
        )
        self.transport = transport
        self.store = store
        self.fail = fail
        self.calls = 0

    def collect(
        self,
        *,
        run_id: str,
        cycle_index: int,
        prior_market_snapshot: Mapping[str, Any] | None = None,
    ) -> Any:
        self.calls += 1
        checkpoint = self.store.load_checkpoint(qualification_id=run_id)
        if not self.store.lease_held:
            raise AssertionError("collector called without exclusive lease")
        if checkpoint["status"] != "COLLECTING" or checkpoint["attempt_count"] != 1:
            raise AssertionError("collector called before durable reservation")
        if self.fail:
            raise RuntimeError("fixture collector failure")
        return self.delegate.collect(
            run_id=run_id,
            cycle_index=cycle_index,
            prior_market_snapshot=prior_market_snapshot,
        )


class _CrashBeforeFinalCheckpointStore(LocalV31SourceQualificationStore):
    def __init__(self, qualification_root: Path) -> None:
        super().__init__(qualification_root)
        self.crash_once = True

    def replace_checkpoint(
        self,
        *,
        qualification_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if checkpoint.get("status") == "SEALED" and self.crash_once:
            self.crash_once = False
            raise SystemExit("simulated process loss after completion receipt")
        return super().replace_checkpoint(
            qualification_id=qualification_id,
            expected_checkpoint_digest=expected_checkpoint_digest,
            checkpoint=checkpoint,
        )


class V31SourceQualificationTests(unittest.TestCase):
    def _store(
        self, root: Path, *, crash_before_seal: bool = False
    ) -> LocalV31SourceQualificationStore:
        store_type = (
            _CrashBeforeFinalCheckpointStore
            if crash_before_seal
            else LocalV31SourceQualificationStore
        )
        return store_type(root)

    def _initialize(self, store: LocalV31SourceQualificationStore) -> None:
        status = initialize_v31_source_qualification(
            store=store,
            qualification_id=QUALIFICATION_ID,
            created_at=CREATED_AT,
            theory_sha256=APPROVED_V31_THEORY_SHA256,
        )
        self.assertEqual("RESERVED", status["status"])
        self.assertEqual(0, status["attempt_count"])

    def _assert_no_external_authority(self, document: Mapping[str, Any]) -> None:
        self.assertFalse(document["account_access"])
        self.assertFalse(document["paper_trading"])
        self.assertFalse(document["live_trading"])
        self.assertFalse(document["order_submission"])
        self.assertFalse(document["credential_access"])
        self.assertFalse(document["funds_access"])
        self.assertEqual(
            "NONE_LOCAL_SIMULATION", document["external_execution_authority"]
        )
        self.assertFalse(document["executable"])

    def test_success_is_one_reserved_call_with_write_once_raw_and_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory) / "qualification")
            self._initialize(store)
            collector = _LeaseAssertingCollector(store=store)

            result = execute_v31_source_qualification(
                store=store,
                qualification_id=QUALIFICATION_ID,
                collector=collector,
                adapter=adapt_native_public_snapshot,
                clock=lambda: WORKFLOW_TIME,
            )

            self.assertEqual("SEALED", result["status"])
            self.assertEqual(1, result["collector_attempt_count"])
            self.assertTrue(result["collector_called_this_invocation"])
            self.assertEqual(1, collector.calls)
            self.assertEqual(12, len(collector.transport.urls))
            checkpoint = store.load_checkpoint(qualification_id=QUALIFICATION_ID)
            self.assertEqual("SEALED", checkpoint["status"])
            self.assertEqual(1, checkpoint["attempt_count"])
            plan = store.read_document(
                relative_ref=PLAN_REF,
                digest_field="source_qualification_plan_digest",
            )
            reservation = store.read_document(
                relative_ref=RESERVATION_REF,
                digest_field="source_qualification_reservation_digest",
            )
            completion = store.read_document(
                relative_ref=COMPLETION_REF,
                digest_field="source_qualification_completion_digest",
            )
            snapshot = store.read_document(
                relative_ref="source/native-market-snapshot.json",
                digest_field="native_market_snapshot_digest",
            )
            dataset = store.read_document(
                relative_ref="adapted/pit-dataset.json",
                digest_field="dataset_digest",
            )
            self.assertEqual(list(REQUIRED_REQUEST_IDS), plan["required_request_ids"])
            self.assertEqual(list(OPTIONAL_REQUEST_IDS), plan["optional_request_ids"])
            self.assertEqual(8, len(plan["required_request_ids"]))
            self.assertEqual(4, len(plan["optional_request_ids"]))
            self.assertEqual(0, plan["retry_count"])
            self.assertEqual(1, plan["attempt_limit"])
            self.assertEqual(
                set(OPTIONAL_FAILURE_KEYS.values()),
                set(completion["optional_failures"]),
            )
            self.assertGreater(completion["unknown_count"], 0)
            self.assertFalse(completion["missing_is_zero"])
            self.assertEqual("1.1.0", snapshot["schema_version"])
            self.assertEqual(
                "0.01",
                snapshot["contract_specification"]["contract_multiplier"],
            )
            specification = snapshot["contract_specification"]
            self.assertEqual("ctVal", specification["contract_multiplier_source_field"])
            self.assertEqual("0.01", specification["okx_ct_val"])
            self.assertEqual("1", specification["okx_ct_mult"])
            self.assertEqual("0.01", specification["quantity_step_contracts"])
            self.assertEqual("0.01", specification["minimum_quantity_contracts"])
            self.assertEqual("0.1", specification["price_tick_usdt"])
            expected_contract_data = {
                "instrument-contract-multiplier": ("0.01", "BTC_PER_CONTRACT"),
                "instrument-okx-ct-mult": ("1", "OKX_CT_MULT"),
                "instrument-quantity-step-contracts": ("0.01", "CONTRACTS"),
                "instrument-minimum-quantity-contracts": ("0.01", "CONTRACTS"),
                "instrument-price-tick-usdt": ("0.1", "USDT_PER_BTC"),
            }
            for metric, expected in expected_contract_data.items():
                rows = [row for row in dataset["data"] if row["metric"] == metric]
                self.assertEqual(1, len(rows))
                self.assertEqual(expected, (rows[0]["value"], rows[0]["unit"]))
                self.assertIn("okx-native-instrument", rows[0]["raw_ref"])
            adaptation = adapt_native_public_snapshot(
                snapshot, decision_at=WORKFLOW_TIME
            )
            financial_input = native_financial_market_economics_input(
                snapshot=snapshot,
                adaptation=adaptation,
                long_protective_stop_price="59000",
                short_protective_stop_price="61000",
            )
            self.assertEqual("60000", financial_input["mark_price"])
            self.assertEqual("0.01", financial_input["contract_multiplier"])
            self.assertEqual("1", financial_input["contract_size_multiplier"])
            self.assertEqual("0.01", financial_input["quantity_step_contracts"])
            self.assertEqual("0.01", financial_input["minimum_quantity_contracts"])
            self.assertEqual("0.1", financial_input["price_tick_usdt"])

            tampered = copy.deepcopy(snapshot)
            tampered["contract_specification"]["quantity_step_contracts"] = "0.005"
            tampered.pop("native_market_snapshot_digest")
            tampered = self_digest(tampered, "native_market_snapshot_digest")
            with self.assertRaisesRegex(
                V31MarketAdapterError, "CONTRACT_FACT_BINDING_INVALID"
            ):
                adapt_native_public_snapshot(tampered, decision_at=WORKFLOW_TIME)
            self.assertEqual(set(REQUIRED_REQUEST_IDS), set(completion["raw_bindings"]))
            for request_id, binding in completion["raw_bindings"].items():
                payload = store.read_raw(
                    relative_ref=binding["relative_ref"],
                    expected_sha256=binding["semantic_digest"],
                )
                self.assertTrue(payload)
                self.assertEqual(binding["semantic_digest"], binding["physical_sha256"])
                self.assertIn(request_id, binding["relative_ref"])
            for document in (plan, reservation, checkpoint, completion):
                self._assert_no_external_authority(document)
            self.assertFalse((store.qualification_root / "checkpoint.json").exists())

    def test_missing_public_contract_multiplier_fails_closed_before_adaptation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory) / "qualification")
            self._initialize(store)
            collector = _LeaseAssertingCollector(store=store)
            collector.transport.instrument_row.pop("ctVal")

            with self.assertRaisesRegex(
                V31SourceQualificationWorkflowError,
                "SOURCE_COLLECTION_FAILED_NATIVEMARKETCOLLECTIONERROR",
            ):
                execute_v31_source_qualification(
                    store=store,
                    qualification_id=QUALIFICATION_ID,
                    collector=collector,
                    adapter=adapt_native_public_snapshot,
                    clock=lambda: WORKFLOW_TIME,
                )
            self.assertEqual(
                "FAILED_CLOSED",
                store.load_checkpoint(qualification_id=QUALIFICATION_ID)["status"],
            )
            self.assertFalse(
                store.document_exists(relative_ref="adapted/pit-dataset.json")
            )

    def test_production_initialization_entrypoint_is_network_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "qualification"
            initialized = initialize_local_v31_source_qualification(
                qualification_root=root,
                qualification_id=QUALIFICATION_ID,
            )
            observed = local_v31_source_qualification_status(
                qualification_root=root,
                qualification_id=QUALIFICATION_ID,
            )
            self.assertEqual("RESERVED", initialized["status"])
            self.assertEqual(initialized, observed)
            self.assertEqual([], list((root / "cycles").glob("**/*")))

    def test_millisecond_clock_binds_equivalent_microsecond_dataset_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory) / "qualification")
            self._initialize(store)
            collector = _LeaseAssertingCollector(store=store)

            result = execute_v31_source_qualification(
                store=store,
                qualification_id=QUALIFICATION_ID,
                collector=collector,
                adapter=adapt_native_public_snapshot,
                clock=lambda: MILLISECOND_WORKFLOW_TIME,
            )

            self.assertEqual("SEALED", result["status"])
            dataset = store.read_document(
                relative_ref="adapted/pit-dataset.json",
                digest_field="dataset_digest",
            )
            completion = store.read_document(
                relative_ref=COMPLETION_REF,
                digest_field="source_qualification_completion_digest",
            )
            self.assertEqual(
                "2026-08-06T12:01:00.871000Z", dataset["decision_at"]
            )
            self.assertEqual(MILLISECOND_WORKFLOW_TIME, completion["decision_at"])

    def test_collector_failure_is_permanent_and_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory) / "qualification")
            self._initialize(store)
            collector = _LeaseAssertingCollector(store=store, fail=True)

            with self.assertRaisesRegex(
                V31SourceQualificationWorkflowError,
                "SOURCE_COLLECTION_FAILED_RUNTIMEERROR",
            ):
                execute_v31_source_qualification(
                    store=store,
                    qualification_id=QUALIFICATION_ID,
                    collector=collector,
                    adapter=adapt_native_public_snapshot,
                    clock=lambda: WORKFLOW_TIME,
                )
            self.assertEqual(1, collector.calls)
            checkpoint = store.load_checkpoint(qualification_id=QUALIFICATION_ID)
            self.assertEqual("FAILED_CLOSED", checkpoint["status"])
            failure = store.read_document(
                relative_ref=FAILURE_REF,
                digest_field="source_qualification_failure_digest",
            )
            self.assertFalse(failure["retry_allowed"])
            self.assertEqual("1.1.0", failure["schema_version"])
            self.assertEqual(
                "UNAVAILABLE_RUNTIMEERROR", failure["root_cause_code"]
            )
            self._assert_no_external_authority(failure)

            with self.assertRaisesRegex(
                V31SourceQualificationWorkflowError, "PERMANENTLY_FAILED"
            ):
                execute_v31_source_qualification(
                    store=store,
                    qualification_id=QUALIFICATION_ID,
                    collector=collector,
                    adapter=adapt_native_public_snapshot,
                    clock=lambda: WORKFLOW_TIME,
                )
            self.assertEqual(1, collector.calls)

    def test_interrupted_collecting_without_delivery_fails_without_recall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory) / "qualification")
            self._initialize(store)
            with store.exclusive_lease(qualification_id=QUALIFICATION_ID):
                checkpoint = store.load_checkpoint(qualification_id=QUALIFICATION_ID)
                collecting = transition_v31_source_qualification_checkpoint(
                    current=checkpoint,
                    status="COLLECTING",
                    updated_at=WORKFLOW_TIME,
                )
                store.replace_checkpoint(
                    qualification_id=QUALIFICATION_ID,
                    expected_checkpoint_digest=checkpoint[
                        "source_qualification_checkpoint_digest"
                    ],
                    checkpoint=collecting,
                )
            collector = _LeaseAssertingCollector(store=store)

            with self.assertRaisesRegex(
                V31SourceQualificationWorkflowError, "INTERRUPTED_NO_RETRY"
            ):
                execute_v31_source_qualification(
                    store=store,
                    qualification_id=QUALIFICATION_ID,
                    collector=collector,
                    adapter=adapt_native_public_snapshot,
                    clock=lambda: WORKFLOW_TIME,
                )
            self.assertEqual(0, collector.calls)
            checkpoint = store.load_checkpoint(qualification_id=QUALIFICATION_ID)
            self.assertEqual("FAILED_CLOSED", checkpoint["status"])

    def test_complete_receipt_recovers_only_deterministic_tail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(
                Path(directory) / "qualification", crash_before_seal=True
            )
            self._initialize(store)
            collector = _LeaseAssertingCollector(store=store)

            with self.assertRaises(SystemExit):
                execute_v31_source_qualification(
                    store=store,
                    qualification_id=QUALIFICATION_ID,
                    collector=collector,
                    adapter=adapt_native_public_snapshot,
                    clock=lambda: WORKFLOW_TIME,
                )
            self.assertEqual(1, collector.calls)
            self.assertEqual(
                "COLLECTING",
                store.load_checkpoint(qualification_id=QUALIFICATION_ID)["status"],
            )
            self.assertTrue(store.document_exists(relative_ref=COMPLETION_REF))

            recovered = execute_v31_source_qualification(
                store=store,
                qualification_id=QUALIFICATION_ID,
                collector=collector,
                adapter=adapt_native_public_snapshot,
                clock=lambda: WORKFLOW_TIME,
            )
            self.assertEqual("SEALED", recovered["status"])
            self.assertTrue(recovered["recovered_deterministic_tail"])
            self.assertFalse(recovered["collector_called_this_invocation"])
            self.assertEqual(1, collector.calls)

    def test_second_store_cannot_enter_while_lease_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "qualification"
            owner = self._store(root)
            contender = self._store(root)
            self._initialize(owner)
            collector = _LeaseAssertingCollector(store=contender)

            with owner.exclusive_lease(qualification_id=QUALIFICATION_ID):
                with self.assertRaisesRegex(
                    V31SourceQualificationStoreError, "LEASE_ALREADY_HELD"
                ):
                    execute_v31_source_qualification(
                        store=contender,
                        qualification_id=QUALIFICATION_ID,
                        collector=collector,
                        adapter=adapt_native_public_snapshot,
                        clock=lambda: WORKFLOW_TIME,
                    )
            self.assertEqual(0, collector.calls)
            checkpoint = owner.load_checkpoint(qualification_id=QUALIFICATION_ID)
            self.assertEqual("RESERVED", checkpoint["status"])

    def test_state_and_evidence_mutations_require_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory) / "qualification")
            with self.assertRaisesRegex(
                V31SourceQualificationStoreError, "MUTATION_REQUIRES_LEASE"
            ):
                store.write_raw(relative_ref="raw/body", payload=b"payload")
            with self.assertRaisesRegex(
                V31SourceQualificationStoreError, "MUTATION_REQUIRES_LEASE"
            ):
                store.write_document(
                    relative_ref="evidence/document.json",
                    document={"value": "not-written"},
                    digest_field="digest",
                )
            with self.assertRaisesRegex(
                V31SourceQualificationStoreError, "MUTATION_REQUIRES_LEASE"
            ):
                store.initialize_checkpoint(
                    qualification_id=QUALIFICATION_ID,
                    plan_binding={},
                    reservation_binding={},
                    created_at=CREATED_AT,
                )
            self.assertEqual([], list(store.qualification_root.rglob("*.json")))

    def test_existing_symlink_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "qualification"
            outside = base / "outside"
            outside.mkdir()
            store = self._store(root)
            (root / "escape").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(
                V31SourceQualificationStoreError, "SYMLINK_FORBIDDEN"
            ):
                store.document_exists(relative_ref="escape/document.json")
            with store.exclusive_lease(qualification_id=QUALIFICATION_ID):
                with self.assertRaisesRegex(
                    V31SourceQualificationStoreError, "SYMLINK_FORBIDDEN"
                ):
                    store.write_raw(
                        relative_ref="escape/body", payload=b"must-not-escape"
                    )
            self.assertEqual([], list(outside.iterdir()))

            linked_root = base / "linked-root"
            linked_root.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(
                V31SourceQualificationStoreError, "SYMLINK_FORBIDDEN"
            ):
                LocalV31SourceQualificationStore(linked_root)

            checkpoint_root = base / "checkpoint-root"
            checkpoint_store = self._store(checkpoint_root)
            (checkpoint_root / "qualification-checkpoint.json").symlink_to(
                outside / "foreign-checkpoint.json"
            )
            with self.assertRaisesRegex(
                V31SourceQualificationStoreError, "SYMLINK_FORBIDDEN"
            ):
                checkpoint_store.load_checkpoint(
                    qualification_id=QUALIFICATION_ID
                )

    def test_capture_query_cannot_change_instrument_or_request_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(Path(directory) / "qualification")
            collector = _LeaseAssertingCollector(store=store)
            # This test exercises only the deterministic source contract, so
            # establish the checkpoint state expected by the fixture collector.
            self._initialize(store)
            with store.exclusive_lease(qualification_id=QUALIFICATION_ID):
                checkpoint = store.load_checkpoint(qualification_id=QUALIFICATION_ID)
                collecting = transition_v31_source_qualification_checkpoint(
                    current=checkpoint,
                    status="COLLECTING",
                    updated_at=WORKFLOW_TIME,
                )
                store.replace_checkpoint(
                    qualification_id=QUALIFICATION_ID,
                    expected_checkpoint_digest=checkpoint[
                        "source_qualification_checkpoint_digest"
                    ],
                    checkpoint=collecting,
                )
                collection = collector.collect(
                    run_id=QUALIFICATION_ID,
                    cycle_index=1,
                    prior_market_snapshot=None,
                )
            snapshot = copy.deepcopy(collection.snapshot)
            capture = next(
                row
                for row in snapshot["source_captures"]
                if row["request_id"] == "okx-native-ticker"
            )
            capture["query"] = [
                {"name": "instId", "value": "ETH-USDT-SWAP"}
            ]
            capture["final_url"] = (
                f"{capture['base_url']}{capture['path']}?"
                f"{urlencode([('instId', 'ETH-USDT-SWAP')])}"
            )
            capture["request_identity_digest"] = canonical_digest(
                {
                    "method": capture["method"],
                    "base_url": capture["base_url"],
                    "path": capture["path"],
                    "query": capture["query"],
                }
            )
            capture.pop("record_digest")
            capture["record_digest"] = canonical_digest(capture)
            snapshot.pop("native_market_snapshot_digest")
            snapshot = self_digest(snapshot, "native_market_snapshot_digest")
            plan = seal_v31_source_qualification_plan(
                qualification_id=QUALIFICATION_ID,
                created_at=CREATED_AT,
                theory_sha256=APPROVED_V31_THEORY_SHA256,
            )

            with self.assertRaisesRegex(
                V31SourceQualificationError, "CAPTURE_QUERY_NOT_FROZEN"
            ):
                validate_v31_source_qualification_collection(
                    plan=plan,
                    snapshot=snapshot,
                    raw_body_by_request_id=collection.raw_body_by_request_id,
                    decision_at=WORKFLOW_TIME,
                )

        self.assertEqual(12, len(REQUEST_SPECS))


if __name__ == "__main__":
    unittest.main()
