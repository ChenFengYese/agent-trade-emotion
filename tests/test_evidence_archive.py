import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.evidence_archive import (
    EvidenceArchiveError,
    archive_sealed_collection,
    build_hot_retirement_plan,
    execute_hot_retirement_plan,
    load_cold_evidence_records,
    replay_cold_evidence,
    verify_evidence_archive,
    verify_hot_cold_equivalence,
)
from trade_system.event_store import EventStore
from trade_system.replay import DeterministicReplay
from trade_system.pipeline import FeaturePipeline
from trade_system.types import AvailabilityKind, AvailabilityRecord


class EvidenceArchiveTests(unittest.TestCase):
    def _sealed_store(self, root: Path, *, availability=True, seal=True, terminal=True):
        store = EventStore(root / "hot")
        received = datetime(2026, 7, 22, tzinfo=timezone.utc)
        raw = store.append_raw(
            source="TEST", venue="BINANCE_USDM", instrument="BTCUSDT", stream="snapshot",
            connection_id="archive-1-depth", ingest_seq=1, payload={"event": 1}, receive_time=received,
        )
        if availability:
            store.append_availability(raw, AvailabilityRecord(
                event_id=raw.event_id, schema_version="test-v1", derived_at=received + timedelta(milliseconds=1),
                available_at=received + timedelta(milliseconds=1), availability_kind=AvailabilityKind.ACTUAL,
                normalized={"kind": "snapshot", "last_update_id": 1, "bids": [["99", "1"]], "asks": [["101", "1"]]},
            ))
        valid, issues, audit = store.audit()
        self.assertTrue(valid, issues)
        if terminal:
            store.write_collection_manifest("archive-1", {
                "collection_result": "QUALIFIED_SMOKE", "audit_digest": audit,
                "replay_digest": DeterministicReplay(store).digest(),
                "capture_plan": {"plan_id": "plan-v1", "plan_sha256": "a" * 64},
                "source_registry": {"registry_id": "registry-v1", "sha256": "b" * 64},
                "collector_software": {"package_source_sha256": "c" * 64},
            })
        if seal:
            store.seal_raw_segment("2026-07-22")
        return store

    def test_archives_raw_and_availability_and_proves_hot_cold_equivalence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root)
            receipt = archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="archive-sidecar-1")
            self.assertTrue(receipt["non_destructive"])
            self.assertEqual(1, len(receipt["raw_seal"]["segments"]))
            self.assertEqual(1, len(receipt["availability_seal"]["segments"]))
            cold = verify_evidence_archive(Path(receipt["receipt_path"]))
            self.assertTrue(cold["valid"])
            equivalent = verify_hot_cold_equivalence(store=store, collection_id="archive-1", receipt_path=Path(receipt["receipt_path"]))
            self.assertTrue(equivalent["hot_cold_equivalent"])

    def test_tampered_compressed_file_or_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root)
            receipt = archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="archive-sidecar-2")
            object_path = root / "cold" / receipt["raw_seal"]["segments"][0]["cold_path"]
            object_path.write_bytes(b"tampered")
            with self.assertRaises(EvidenceArchiveError):
                verify_evidence_archive(Path(receipt["receipt_path"]))

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root)
            receipt = archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="archive-sidecar-3")
            receipt_path = Path(receipt["receipt_path"])
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            value["collection_id"] = "forged"
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(EvidenceArchiveError):
                verify_evidence_archive(receipt_path)

    def test_rejects_missing_availability_nonterminal_or_unsealed_raw(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root, availability=False)
            with self.assertRaises(EvidenceArchiveError):
                archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="missing-availability")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root, terminal=False)
            with self.assertRaises(EvidenceArchiveError):
                archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="nonterminal")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root, seal=False)
            with self.assertRaises(EvidenceArchiveError):
                archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="unsealed")

    def test_stale_partial_cannot_be_accepted_as_a_cold_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root)
            objects = root / "cold" / "objects" / "raw"
            objects.mkdir(parents=True)
            (objects / "orphan.ndjson.gz.partial").write_bytes(b"partial")
            # The v1 archiver refuses stale sidecar partials rather than making
            # an unverifiable recovery decision on behalf of an operator.
            with self.assertRaises(EvidenceArchiveError):
                archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="partial")

    def test_verified_cold_replay_matches_hot_deterministic_replay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root)
            receipt = archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="cold-replay")
            raws, availability, loaded = load_cold_evidence_records(Path(receipt["receipt_path"]))
            self.assertEqual(receipt["receipt_sha256"], loaded["receipt_sha256"])
            self.assertEqual(DeterministicReplay(store).digest(), DeterministicReplay.digest_from_records(raws, availability))
            self.assertEqual(
                [(event.raw.event_id, event.availability.available_at) for event in DeterministicReplay(store).events()],
                [(event.raw.event_id, event.availability.available_at) for event in replay_cold_evidence(Path(receipt["receipt_path"]))],
            )
            self.assertTrue(list(FeaturePipeline().replay_events(replay_cold_evidence(Path(receipt["receipt_path"])))))

    def test_retirement_plan_is_proven_but_execution_is_permanently_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root)
            receipt = archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="retirement")
            plan = build_hot_retirement_plan(
                store=store, collection_id="archive-1", receipt_path=Path(receipt["receipt_path"]),
                output_path=root / "plans" / "retirement.json", retirement_id="retire-1",
            )
            self.assertIn("DISABLED", plan["retirement_execution"])
            self.assertTrue((store.raw_root / "2026-07-22.ndjson").exists())
            with self.assertRaises(EvidenceArchiveError):
                execute_hot_retirement_plan(plan_path=Path(plan["plan_path"]), confirmation_token="wrong")
            with self.assertRaises(EvidenceArchiveError):
                execute_hot_retirement_plan(plan_path=Path(plan["plan_path"]), confirmation_token=plan["confirmation_token"])
            self.assertTrue((store.raw_root / "2026-07-22.ndjson").exists())

    def test_retirement_refuses_g1_binding_and_receipt_path_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = self._sealed_store(root)
            receipt = archive_sealed_collection(store=store, collection_id="archive-1", cold_root=root / "cold", archive_id="protected")
            terminal_path = store.collection_manifest_root / "archive-1.json"
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            terminal["capture_plan"] = {"plan_id": "btc-g1-active-v1", "plan_sha256": "a" * 64}
            # Rewriting the terminal manifest makes the hot/cold digest binding
            # stale; G1 is rejected before any retirement plan can be written.
            terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
            with self.assertRaises(EvidenceArchiveError):
                build_hot_retirement_plan(store=store, collection_id="archive-1", receipt_path=Path(receipt["receipt_path"]), output_path=root / "g1.json", retirement_id="retire-g1")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = self._sealed_store(root / "first")
            receipt = archive_sealed_collection(store=first, collection_id="archive-1", cold_root=root / "cold", archive_id="wrong-store")
            second = self._sealed_store(root / "second")
            with self.assertRaises(EvidenceArchiveError):
                build_hot_retirement_plan(store=second, collection_id="archive-1", receipt_path=Path(receipt["receipt_path"]), output_path=root / "wrong.json", retirement_id="retire-wrong")
