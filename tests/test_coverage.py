from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from trade_system.coverage import build_coverage_report
from trade_system.event_store import EventStore
from trade_system.types import AvailabilityKind, AvailabilityRecord


class CoverageTests(unittest.TestCase):
    def test_reports_unparsed_raw_and_only_observable_ingest_gap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(Path(temp_dir))
            received = datetime(2026, 1, 1, tzinfo=timezone.utc)
            first = store.append_raw(source="BINANCE", venue="BINANCE_USDM", instrument="BTCUSDT", stream="aggTrade", connection_id="conn-a", ingest_seq=1, payload={"x": 1}, receive_time=received)
            store.append_raw(source="BINANCE", venue="BINANCE_USDM", instrument="BTCUSDT", stream="aggTrade", connection_id="conn-a", ingest_seq=3, payload={"x": 3}, receive_time=received)
            store.append_availability(first, AvailabilityRecord(event_id=first.event_id, schema_version="v1", derived_at=received, available_at=received, availability_kind=AvailabilityKind.ACTUAL, normalized={"kind": "trade"}))
            report = build_coverage_report(store)
            self.assertTrue(report["audit_valid"])
            self.assertEqual(2, report["raw_records"])
            self.assertEqual(1, report["streams"][0]["raw_without_availability"])
            self.assertEqual([[2, 2]], report["connections"][0]["observable_ingest_seq_gaps"])
            self.assertEqual([], report["collection_manifests"])
            self.assertIn("cannot infer", report["limitation"])
