import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trade_system.event_store import EventStore
from trade_system.feature_describe import FeatureDescribeError, describe_sealed_features
from trade_system.replay import DeterministicReplay
from trade_system.types import AvailabilityKind, AvailabilityRecord


class FeatureDescribeTests(unittest.TestCase):
    def _store(self, root: Path):
        store = EventStore(root)
        now = datetime(2026, 7, 22, tzinfo=timezone.utc)
        records = [
            {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]},
            {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"},
            {"kind": "delta", "U": 11, "u": 11, "pu": 10, "bids": [["99", "3"]], "asks": []},
        ]
        for index, normalized in enumerate(records, start=1):
            raw = store.append_raw(
                source="TEST", venue="BINANCE_USDM", instrument="BTCUSDT", stream=normalized["kind"],
                connection_id="describe-1-depth", ingest_seq=index, payload={"index": index}, receive_time=now,
            )
            store.append_availability(raw, AvailabilityRecord(
                event_id=raw.event_id, schema_version="test", derived_at=now, available_at=now,
                availability_kind=AvailabilityKind.ACTUAL, normalized=normalized,
            ))
        valid, issues, digest = store.audit()
        self.assertTrue(valid, issues)
        store.write_collection_manifest("describe-1", {
            "collection_result": "QUALIFIED_SMOKE", "duration_seconds": 60,
            "audit_digest": digest, "replay_digest": DeterministicReplay(store).digest(),
        })
        store.seal_raw_segment("2026-07-22")

    def test_describes_sealed_features_without_labels_or_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "evidence"
            self._store(root)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            report = describe_sealed_features((root,))
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)
            self.assertGreater(report["feature_rows"], 0)
            self.assertIn("mid_price", report["feature_distributions"])
            self.assertIn("does not deduplicate", report["limitation"])

    def test_rejects_when_no_current_collection_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(FeatureDescribeError):
                describe_sealed_features((Path(temp_dir),))
