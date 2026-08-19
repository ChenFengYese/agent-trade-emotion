import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.event_store import EventStore
from trade_system.g1_acceptance import G1AcceptancePolicy, G1PolicyError, validate_g1_data, validate_g1_stores
from trade_system.types import AvailabilityKind, AvailabilityRecord


class G1AcceptanceTests(unittest.TestCase):
    def _policy(self, path: Path, status="FROZEN_G1_DATA_ACCEPTANCE"):
        path.write_text(json.dumps({
            "policy_id": "g1-v1",
            "status": status,
            "instrument": "BTCUSDT",
            "required_streams": ["btcusdt@depth@100ms", "snapshot", "btcusdt@aggTrade", "btcusdt@markPrice@1s", "openInterest", "exchangeInfo"],
            "required_configured_streams": ["btcusdt@forceOrder"],
            "required_source_registry_id": "source-registry.v1",
            "required_source_registry_sha256": "a" * 64,
            "min_total_observed_seconds": 60,
            "min_qualified_collections": 1,
            "min_distinct_utc_days": 1,
            "min_distinct_utc_hour_buckets": 1,
            "min_exchange_info_observations": 2,
            "max_exchange_info_gap_seconds": 180,
            "min_stream_observations": {
                "btcusdt@depth@100ms": 1,
                "snapshot": 1,
                "btcusdt@aggTrade": 1,
                "btcusdt@markPrice@1s": 1,
                "openInterest": 1
            },
            "max_stream_gap_seconds": {
                "btcusdt@depth@100ms": 180,
                "btcusdt@aggTrade": 180,
                "btcusdt@markPrice@1s": 180,
                "openInterest": 180
            },
            "require_exchange_info_trading": True,
            "max_parse_errors": 0,
            "max_book_gaps": 0,
            "require_actual_only": True,
            "require_sealed_raw_segments": True,
            "allow_reconnects": False,
        }), encoding="utf-8")

    def _qualified_collection(self, store: EventStore, collection_id="collection-1", offset_seconds=0):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)
        streams = ["exchangeInfo", "btcusdt@depth@100ms", "snapshot", "btcusdt@aggTrade", "btcusdt@markPrice@1s", "openInterest", "exchangeInfo"]
        for index, stream in enumerate(streams, start=1):
            received = start + timedelta(seconds=(index - 1) * 20)
            raw = store.append_raw(
                source="BINANCE_USDM", venue="BINANCE_USDM", instrument="BTCUSDT", stream=stream,
                connection_id=collection_id + ("-metadata" if stream == "exchangeInfo" else ("-depth" if stream in {"btcusdt@depth@100ms", "snapshot"} else "-market")),
                ingest_seq=index, payload={"n": index}, receive_time=received,
            )
            store.append_availability(raw, AvailabilityRecord(
                event_id=raw.event_id, schema_version="v1", derived_at=received, available_at=received,
                availability_kind=AvailabilityKind.ACTUAL,
                normalized={"kind": "exchange_info", "status": "TRADING"} if stream == "exchangeInfo" else {"kind": "test"},
            ))
        store.seal_raw_segment("2026-01-01")
        valid, issues, digest = store.audit()
        self.assertTrue(valid, issues)
        store.write_collection_manifest(collection_id, {
            "collection_result": "QUALIFIED_SMOKE", "instrument": "BTCUSDT",
            "raw_captured": 7, "availability_written": 7, "parse_errors": 0, "book_gaps": 0,
            "errors": [], "reconnects": {}, "audit_digest": digest,
            "configured_streams": ["btcusdt@forceOrder"],
            "source_registry": {"registry_id": "source-registry.v1", "sha256": "a" * 64},
        })

    def test_frozen_policy_passes_matching_sealed_collection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            self._qualified_collection(store)
            policy_path = root / "policy.json"
            self._policy(policy_path)
            report = validate_g1_data(store, G1AcceptancePolicy.load(policy_path))
            self.assertTrue(report["passed"], report)
            self.assertEqual("PASS", report["status"])
            self.assertEqual(120.0, report["total_observed_seconds"])
            self.assertEqual(["2026-01-01"], report["distinct_utc_dates"])
            self.assertEqual([0], report["distinct_utc_hour_buckets"])

    def test_draft_policy_never_grants_g1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            self._qualified_collection(store)
            policy_path = root / "policy.json"
            self._policy(policy_path, status="DRAFT_TEMPLATE")
            report = validate_g1_data(store, G1AcceptancePolicy.load(policy_path))
            self.assertFalse(report["passed"])
            self.assertEqual("DRAFT_POLICY", report["status"])

    def test_frozen_policy_rejects_collection_with_other_source_registry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            self._qualified_collection(store)
            manifest_path = store.collection_manifest_root / "collection-1.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # A collection manifest is write-once in production; this is a
            # synthetic tamper fixture for validator behavior only.
            manifest["source_registry"]["sha256"] = "b" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            policy_path = root / "policy.json"
            self._policy(policy_path)
            report = validate_g1_data(store, G1AcceptancePolicy.load(policy_path))
            self.assertFalse(report["passed"])
            self.assertIn("source registry digest mismatch", report["collections"][0]["reasons"])

    def test_frozen_policy_rejects_exchange_info_gap_above_frozen_cadence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            self._qualified_collection(store)
            policy_path = root / "policy.json"
            self._policy(policy_path)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["max_exchange_info_gap_seconds"] = 30
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            report = validate_g1_data(store, G1AcceptancePolicy.load(policy_path))
            self.assertFalse(report["passed"])
            self.assertIn("exchangeInfo observation gap exceeds policy", report["collections"][0]["reasons"])

    def test_frozen_policy_rejects_required_stream_with_excessive_gap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            self._qualified_collection(store)
            policy_path = root / "policy.json"
            self._policy(policy_path)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["max_stream_gap_seconds"]["btcusdt@depth@100ms"] = 99
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            report = validate_g1_data(store, G1AcceptancePolicy.load(policy_path))
            self.assertFalse(report["passed"])
            self.assertIn("btcusdt@depth@100ms observation gap exceeds policy", report["collections"][0]["reasons"])

    def test_frozen_policy_requires_a_coverage_contract_for_every_continuous_stream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policy_path = root / "policy.json"
            self._policy(policy_path)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            del policy["max_stream_gap_seconds"]["openInterest"]
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaises(G1PolicyError):
                G1AcceptancePolicy.load(policy_path)

    def test_frozen_policy_rejects_insufficient_calendar_diversity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            self._qualified_collection(store)
            policy_path = root / "policy.json"
            self._policy(policy_path)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["min_distinct_utc_days"] = 2
            policy["min_distinct_utc_hour_buckets"] = 2
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            report = validate_g1_data(store, G1AcceptancePolicy.load(policy_path))
            self.assertFalse(report["passed"])
            self.assertEqual("WAIT_DATA", report["status"])
            self.assertEqual(1, report["deficits"]["distinct_utc_days"])
            self.assertEqual(1, report["deficits"]["distinct_utc_hour_buckets"])
            self.assertIn("distinct UTC date coverage below policy", report["reasons"])
            self.assertIn("distinct UTC hour-bucket coverage below policy", report["reasons"])

    def test_optional_frozen_capture_plan_binding_rejects_unplanned_collection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            self._qualified_collection(store)
            policy_path = root / "policy.json"
            self._policy(policy_path)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["required_capture_plan_id"] = "plan-v1"
            policy["required_capture_plan_sha256"] = "b" * 64
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            report = validate_g1_data(store, G1AcceptancePolicy.load(policy_path))
            self.assertFalse(report["passed"])
            self.assertIn("required capture plan binding is missing", report["collections"][0]["reasons"])
            self.assertEqual(1, report["collection_failure_counts"]["required capture plan binding is missing"])

    def test_bundle_counts_separately_sealed_evidence_stores_without_copying_raw(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, second = EventStore(root / "first"), EventStore(root / "second")
            self._qualified_collection(first, "collection-1")
            self._qualified_collection(second, "collection-2", offset_seconds=200)
            policy_path = root / "policy.json"
            self._policy(policy_path)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["min_qualified_collections"] = 2
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            report = validate_g1_stores((first, second), G1AcceptancePolicy.load(policy_path))
            self.assertTrue(report["passed"], report)
            self.assertEqual(2, report["qualified_collections"])
            self.assertEqual(2, len({row["data_dir"] for row in report["collections"]}))

    def test_bundle_rejects_duplicate_evidence_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(Path(temp_dir) / "data")
            self._qualified_collection(store)
            policy_path = Path(temp_dir) / "policy.json"
            self._policy(policy_path)
            with self.assertRaises(G1PolicyError):
                validate_g1_stores((store, store), G1AcceptancePolicy.load(policy_path))
