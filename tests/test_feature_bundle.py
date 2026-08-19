import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.event_store import EventStore
from trade_system.feature_bundle import FeatureBundleError, build_feature_bundle
from trade_system.g1_acceptance import G1AcceptancePolicy, validate_g1_stores
from trade_system.g1_report import write_g1_report
from trade_system.replay import DeterministicReplay
from trade_system.types import AvailabilityKind, AvailabilityRecord


class FeatureBundleTests(unittest.TestCase):
    def _policy(self, path: Path):
        path.write_text(json.dumps({
            "policy_id": "g1-feature.v1", "status": "FROZEN_G1_DATA_ACCEPTANCE", "instrument": "BTCUSDT",
            "required_streams": ["btcusdt@depth@100ms", "snapshot", "btcusdt@aggTrade", "btcusdt@markPrice@1s", "openInterest", "exchangeInfo"],
            "required_configured_streams": ["btcusdt@forceOrder"],
            "required_source_registry_id": "source-registry.v3", "required_source_registry_sha256": "a" * 64,
            "min_total_observed_seconds": 1, "min_qualified_collections": 2,
            "min_distinct_utc_days": 1, "min_distinct_utc_hour_buckets": 1,
            "min_exchange_info_observations": 2, "max_exchange_info_gap_seconds": 120,
            "min_stream_observations": {"btcusdt@depth@100ms": 1, "snapshot": 1, "btcusdt@aggTrade": 1, "btcusdt@markPrice@1s": 1, "openInterest": 1},
            "max_stream_gap_seconds": {"btcusdt@depth@100ms": 120, "btcusdt@aggTrade": 120, "btcusdt@markPrice@1s": 120, "openInterest": 120},
            "require_exchange_info_trading": True, "max_parse_errors": 0, "max_book_gaps": 0,
            "require_actual_only": True, "require_sealed_raw_segments": True, "allow_reconnects": False,
        }), encoding="utf-8")

    def _episode_policy(self, path: Path):
        path.write_text(json.dumps({
            "policy_id": "episode-g1.v1", "status": "FROZEN_EPISODE_POLICY", "frozen_at": "2026-01-01T00:00:00Z",
            "feature_version": "five-factor-proxy-v1", "trigger_feature": "D_directional_pressure",
            "trigger_threshold": "0.00001", "min_seconds_between_episodes": 1,
            "state_machine": {"pressure_threshold": "0.00001", "resilience_threshold": "0", "response_fraction": "0.0001", "max_observation_seconds": 60, "confirmation_updates": 2},
        }), encoding="utf-8")

    def _store(self, root: Path, collection_id: str, offset_seconds: int):
        store = EventStore(root)
        start = datetime(2026, 1, 2, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)
        events = [
            ("exchangeInfo", "-metadata", {"kind": "exchange_info", "status": "TRADING"}),
            ("snapshot", "-depth", {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]}),
            ("btcusdt@aggTrade", "-market", {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"}),
            ("btcusdt@depth@100ms", "-depth", {"kind": "delta", "U": 11, "u": 11, "pu": 10, "bids": [["99", "3"]], "asks": []}),
            ("btcusdt@markPrice@1s", "-market", {"kind": "mark_price", "mark_price": "100", "index_price": "100", "funding_rate": "0"}),
            ("openInterest", "-oi", {"kind": "oi", "value": "10"}),
            ("exchangeInfo", "-metadata", {"kind": "exchange_info", "status": "TRADING"}),
        ]
        per_connection = {}
        for index, (stream, suffix, normalized) in enumerate(events):
            connection = collection_id + suffix
            per_connection[connection] = per_connection.get(connection, 0) + 1
            received = start + timedelta(seconds=index * 10)
            raw = store.append_raw(
                source="BINANCE_USDM", venue="BINANCE_USDM", instrument="BTCUSDT", stream=stream,
                connection_id=connection, ingest_seq=per_connection[connection], payload={"n": index}, receive_time=received,
            )
            store.append_availability(raw, AvailabilityRecord(
                event_id=raw.event_id, schema_version="v1", derived_at=received, available_at=received,
                availability_kind=AvailabilityKind.ACTUAL, normalized=normalized,
            ))
        store.seal_raw_segment("2026-01-02")
        audit_valid, audit_issues, audit_digest = store.audit()
        self.assertTrue(audit_valid, audit_issues)
        store.write_collection_manifest(collection_id, {
            "collection_result": "QUALIFIED_SMOKE", "instrument": "BTCUSDT", "raw_captured": len(events),
            "availability_written": len(events), "parse_errors": 0, "book_gaps": 0, "errors": [], "reconnects": {},
            "configured_streams": ["btcusdt@forceOrder"],
            "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
            "audit_digest": audit_digest, "replay_digest": DeterministicReplay(store).digest(),
        })
        return store

    def _passed_report(self, root: Path):
        first, second = self._store(root / "first", "collection-a", 0), self._store(root / "second", "collection-b", 200)
        policy_path = root / "policy.json"
        self._policy(policy_path)
        report = validate_g1_stores((first, second), G1AcceptancePolicy.load(policy_path))
        self.assertTrue(report["passed"], report)
        report_path = root / "g1.json"
        write_g1_report(report_path, report)
        return first, second, report_path

    def test_bundle_is_collection_isolated_namespaced_and_manifest_bound(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, second, g1_report = self._passed_report(root)
            output, manifest = root / "features.ndjson", root / "features.manifest.json"
            episode_policy = root / "episode-policy.json"
            self._episode_policy(episode_policy)
            report = build_feature_bundle(
                data_dirs=(first.root, second.root), g1_report_path=g1_report, output_path=output,
                manifest_path=manifest, bundle_id="features-g1.v1", episode_policy_path=episode_policy,
            )
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertGreater(len(rows), 0)
            self.assertEqual(len(rows), len({row["event_id"] for row in rows}))
            self.assertEqual(2, len(report["collections"]))
            self.assertEqual(report["feature_artifact_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual("episode-g1.v1", report["episode_policy_id"])
            self.assertTrue(all(row["episode_policy_id"] == "episode-g1.v1" for row in rows))
            self.assertTrue(all("evidence" in row and "source_event_id" in row for row in rows))

    def test_bundle_rejects_evidence_that_no_longer_matches_its_pass_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, second, g1_report = self._passed_report(root)
            manifest_path = first.collection_manifest_root / "collection-a.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["replay_digest"] = "tampered"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            episode_policy = root / "episode-policy.json"
            self._episode_policy(episode_policy)
            with self.assertRaises(FeatureBundleError):
                build_feature_bundle(
                    data_dirs=(first.root, second.root), g1_report_path=g1_report,
                    output_path=root / "features.ndjson", manifest_path=root / "features.manifest.json", bundle_id="features-g1.v1", episode_policy_path=episode_policy,
                )
