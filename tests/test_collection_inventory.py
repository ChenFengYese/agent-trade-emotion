import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trade_system.collection_inventory import inventory_collections
from trade_system.event_store import EventStore
from trade_system.replay import DeterministicReplay
from trade_system.types import AvailabilityKind, AvailabilityRecord


class CollectionInventoryTests(unittest.TestCase):
    def test_reports_only_current_qualified_and_sealed_collection_as_current(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "root"
            store = EventStore(root / "evidence")
            received = datetime(2026, 7, 22, tzinfo=timezone.utc)
            raw = store.append_raw(
                source="TEST", venue="BINANCE_USDM", instrument="BTCUSDT", stream="snapshot",
                connection_id="inventory-1-depth", ingest_seq=1, payload={"ok": True}, receive_time=received,
            )
            store.append_availability(raw, AvailabilityRecord(
                event_id=raw.event_id, schema_version="test", derived_at=received, available_at=received,
                availability_kind=AvailabilityKind.ACTUAL, normalized={"kind": "snapshot", "last_update_id": 1, "bids": [["99", "1"]], "asks": [["101", "1"]]},
            ))
            valid, issues, digest = store.audit()
            self.assertTrue(valid, issues)
            store.write_collection_manifest("inventory-1", {
                "collection_result": "QUALIFIED_SMOKE", "duration_seconds": 60,
                "audit_digest": digest, "replay_digest": DeterministicReplay(store).digest(),
            })
            store.seal_raw_segment("2026-07-22")
            missing = root / "missing"
            report = inventory_collections((root, missing))
            self.assertFalse(missing.exists())
            self.assertEqual(1, report["summary"]["sealed_current_collections"])
            self.assertEqual(60.0, report["summary"]["descriptive_duration_seconds"])
            self.assertEqual("SEALED_CURRENT", report["collections"][0]["status"])

    def test_marks_terminal_digest_drift_without_claiming_g1_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root)
            received = datetime(2026, 7, 22, tzinfo=timezone.utc)
            raw = store.append_raw(
                source="TEST", venue="BINANCE_USDM", instrument="BTCUSDT", stream="snapshot",
                connection_id="inventory-drift-depth", ingest_seq=1, payload={"ok": True}, receive_time=received,
            )
            store.append_availability(raw, AvailabilityRecord(
                event_id=raw.event_id, schema_version="test", derived_at=received, available_at=received,
                availability_kind=AvailabilityKind.ACTUAL, normalized={"kind": "snapshot", "last_update_id": 1, "bids": [["99", "1"]], "asks": [["101", "1"]]},
            ))
            store.write_collection_manifest("inventory-drift", {
                "collection_result": "QUALIFIED_SMOKE", "duration_seconds": 60,
                "audit_digest": "a" * 64, "replay_digest": "b" * 64,
            })
            store.seal_raw_segment("2026-07-22")
            report = inventory_collections((root,))
            row = report["collections"][0]
            self.assertEqual("QUALIFIED_BUT_NOT_CURRENT", row["status"])
            self.assertIn("current audit digest differs from terminal manifest", row["issues"])
            self.assertIn("G1/G2/G3", report["limitation"])
