import tempfile
import unittest
import json
from datetime import timedelta

from trade_system.event_store import EventStore, EventStoreError
from trade_system.replay import DeterministicReplay
from trade_system.types import AvailabilityKind, AvailabilityRecord, utc_now


class EventStoreTests(unittest.TestCase):
    def test_raw_and_actual_availability_are_append_only_and_replayable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            received = utc_now()
            raw = store.append_raw(
                source="TEST",
                venue="TEST",
                instrument="BTCUSDT",
                stream="trade",
                connection_id="connection-a",
                ingest_seq=1,
                payload={"price": "100"},
                receive_time=received,
            )
            derived = received + timedelta(milliseconds=1)
            store.append_availability(
                raw,
                AvailabilityRecord(
                    event_id=raw.event_id,
                    schema_version="v1",
                    derived_at=derived,
                    available_at=derived,
                    availability_kind=AvailabilityKind.ACTUAL,
                    normalized={"kind": "trade"},
                ),
            )
            valid, issues, first_digest = store.audit()
            self.assertTrue(valid, issues)
            self.assertEqual(1, sum(1 for _ in DeterministicReplay(store).events()))
            self.assertEqual(first_digest, store.audit()[2])
            audited_valid, audited_issues, audited_digest, raws, availability = store.audit_with_records()
            self.assertTrue(audited_valid, audited_issues)
            self.assertEqual(first_digest, audited_digest)
            self.assertEqual(DeterministicReplay(store).digest(), DeterministicReplay.digest_from_records(raws, availability))
            persisted = list(store.iter_raw())[0]
            self.assertEqual(raw.raw_offset, persisted.raw_offset)

    def test_reconstructed_record_is_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            received = utc_now()
            raw = store.append_raw(
                source="TEST",
                venue="TEST",
                instrument="BTCUSDT",
                stream="trade",
                connection_id="connection-a",
                ingest_seq=1,
                payload={"price": "100"},
                receive_time=received,
            )
            store.append_availability(
                raw,
                AvailabilityRecord(
                    event_id=raw.event_id,
                    schema_version="v2",
                    derived_at=received + timedelta(seconds=1),
                    available_at=received + timedelta(milliseconds=5),
                    availability_kind=AvailabilityKind.RECONSTRUCTED,
                    reconstruction_basis={"parser": "v2", "latency_model": "fixed"},
                    normalized={"kind": "trade"},
                ),
            )
            self.assertEqual(0, sum(1 for _ in DeterministicReplay(store).events()))
            self.assertEqual(1, sum(1 for _ in DeterministicReplay(store, allow_reconstructed=True).events()))

    def test_actual_record_cannot_be_backdated(self):
        now = utc_now()
        with self.assertRaises(ValueError):
            AvailabilityRecord(
                event_id="x",
                schema_version="v1",
                derived_at=now,
                available_at=now - timedelta(microseconds=1),
                availability_kind=AvailabilityKind.ACTUAL,
            )

    def test_same_connection_and_ingest_sequence_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            arguments = dict(
                source="TEST",
                venue="TEST",
                instrument="BTCUSDT",
                stream="trade",
                connection_id="connection-a",
                ingest_seq=1,
                payload={"price": "100"},
                receive_time=utc_now(),
            )
            store.append_raw(**arguments)
            with self.assertRaises(EventStoreError):
                store.append_raw(**arguments)

    def test_sealed_raw_segment_cannot_be_appended_and_is_audited(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            received = utc_now()
            store.append_raw(
                source="TEST",
                venue="TEST",
                instrument="BTCUSDT",
                stream="trade",
                connection_id="seal-test",
                ingest_seq=1,
                payload={"price": "100"},
                receive_time=received,
            )
            store.seal_raw_segment(received.strftime("%Y-%m-%d"))
            valid, issues, _ = store.audit()
            self.assertTrue(valid, issues)
            with self.assertRaises(EventStoreError):
                store.append_raw(
                    source="TEST",
                    venue="TEST",
                    instrument="BTCUSDT",
                    stream="trade",
                    connection_id="seal-test",
                    ingest_seq=2,
                    payload={"price": "101"},
                    receive_time=received,
                )

    def test_audit_detects_raw_offset_tampering_while_reusing_parsed_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            received = utc_now()
            store.append_raw(
                source="TEST", venue="TEST", instrument="BTCUSDT", stream="trade", connection_id="offset-test",
                ingest_seq=1, payload={"price": "100"}, receive_time=received,
            )
            raw_path = store.raw_root / (received.strftime("%Y-%m-%d") + ".ndjson")
            record = json.loads(raw_path.read_text(encoding="utf-8"))
            record["raw_offset"] = 1
            raw_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            valid, issues, _digest, raws, _availability = store.audit_with_records()
            self.assertFalse(valid)
            self.assertTrue(any("raw_offset mismatch" in issue for issue in issues))
            self.assertEqual(1, len(raws))

    def test_collection_manifest_is_write_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            manifest = store.write_collection_manifest("forward-001", {"collection_result": "UNQUALIFIED"})
            self.assertTrue(manifest.exists())
            with self.assertRaises(EventStoreError):
                store.write_collection_manifest("forward-001", {"collection_result": "UNQUALIFIED"})
