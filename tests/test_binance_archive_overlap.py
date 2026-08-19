import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from trade_system.binance_archive_overlap import (
    BinanceArchiveOverlapError,
    BinanceArchiveOverlapPlan,
    audit_binance_aggtrade_overlap,
)
from trade_system.cli import main
from trade_system.event_store import EventStore
from trade_system.replay import DeterministicReplay
from trade_system.source_registry import SourceRegistry
from trade_system.types import AvailabilityKind, AvailabilityRecord


REPOSITORY = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPOSITORY / "config" / "source_registry.v3.json"


class BinanceArchiveOverlapTests(unittest.TestCase):
    def _create_forward_collection(self, root: Path, *, price: str = "100.5") -> Path:
        evidence = root / "evidence"
        store = EventStore(evidence)
        event_time = datetime(2026, 7, 22, 12, 0, 1, tzinfo=timezone.utc)
        raw = store.append_raw(
            source="BINANCE_USDM", venue="BINANCE_USDM", instrument="BTCUSDT", stream="btcusdt@aggTrade",
            connection_id="overlap-1-market", ingest_seq=1, payload={"a": 42}, receive_time=event_time,
            exchange_event_time=event_time,
        )
        store.append_availability(raw, AvailabilityRecord(
            event_id=raw.event_id, schema_version="binance-usdm-public-v1", derived_at=event_time,
            available_at=event_time, availability_kind=AvailabilityKind.ACTUAL,
            normalized={"kind": "trade", "exchange_trade_id": 42, "price": price, "quantity": "2.0", "side": "SELL"},
        ))
        valid, issues, digest = store.audit()
        self.assertTrue(valid, issues)
        registry = SourceRegistry.load(REGISTRY_PATH)
        store.write_collection_manifest("overlap-1", {
            "collection_result": "QUALIFIED_SMOKE", "duration_seconds": 60,
            "audit_digest": digest, "replay_digest": DeterministicReplay(store).digest(),
            "source_registry": registry.manifest_binding("BTCUSDT", ("btcusdt@aggTrade",)),
        })
        store.seal_raw_segment("2026-07-22")
        return evidence

    def _plan(self, root: Path, evidence: Path, archive: Path) -> Path:
        registry = SourceRegistry.load(REGISTRY_PATH)
        checksum = root / (archive.name + ".CHECKSUM")
        archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksum.write_text("%s  %s\n" % (archive_sha, archive.name), encoding="utf-8")
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps({
            "audit_id": "binance-overlap-v1", "status": "FROZEN_BINANCE_ARCHIVE_OVERLAP_PLAN",
            "source_registry": {"registry_id": registry.registry_id, "sha256": registry.sha256},
            "instrument": "BTCUSDT",
            "archive": {
                "date": "2026-07-22", "source_id": "SRC-BIN-ARCHIVE",
                "source_url": "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-07-22.zip",
                "path": archive.name, "checksum_path": checksum.name,
                "checksum_source_url": "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-07-22.zip.CHECKSUM",
                "sha256": archive_sha,
                "columns": ["agg_trade_id", "price", "qty", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"],
            },
            "forward_collection": {"data_dir": evidence.name, "collection_id": "overlap-1"},
        }), encoding="utf-8")
        return plan_path

    def _archive(self, root: Path, *, matching_price: str = "100.5") -> Path:
        archive = root / "BTCUSDT-aggTrades-2026-07-22.csv"
        archive.write_text(
            "agg_trade_id,price,qty,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
            "41,100.0,1.0,1,1,1784721600000,true\n"
            "42,%s,2.0,2,2,1784721601000,true\n" % matching_price,
            encoding="utf-8",
        )
        return archive

    def test_audits_exact_archive_trade_overlap_against_current_sealed_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = self._create_forward_collection(root)
            archive = self._archive(root)
            plan = BinanceArchiveOverlapPlan.load(self._plan(root, evidence, archive))
            report = audit_binance_aggtrade_overlap(plan, base_dir=root, source_registry_path=REGISTRY_PATH)
            self.assertTrue(report["complete"])
            self.assertTrue(report["overlap"]["verified"])
            self.assertEqual(1, report["overlap"]["matching_aggregate_trade_ids"])
            self.assertEqual(0, report["overlap"]["payload_mismatches"])

    def test_payload_difference_is_not_treated_as_an_overlap_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = self._create_forward_collection(root)
            archive = self._archive(root, matching_price="100.6")
            plan = BinanceArchiveOverlapPlan.load(self._plan(root, evidence, archive))
            report = audit_binance_aggtrade_overlap(plan, base_dir=root, source_registry_path=REGISTRY_PATH)
            self.assertFalse(report["complete"])
            self.assertEqual(1, report["overlap"]["payload_mismatches"])

    def test_rejects_archive_when_official_checksum_is_not_the_frozen_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = self._create_forward_collection(root)
            archive = self._archive(root)
            plan_path = self._plan(root, evidence, archive)
            (root / (archive.name + ".CHECKSUM")).write_text("%s  %s\n" % ("0" * 64, archive.name), encoding="utf-8")
            with self.assertRaises(BinanceArchiveOverlapError):
                audit_binance_aggtrade_overlap(BinanceArchiveOverlapPlan.load(plan_path), base_dir=root, source_registry_path=REGISTRY_PATH)

    def test_cli_writes_a_write_once_overlap_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = self._create_forward_collection(root)
            archive = self._archive(root)
            plan = self._plan(root, evidence, archive)
            output = root / "overlap-report.json"
            with redirect_stdout(StringIO()):
                self.assertEqual(0, main([
                    "audit-binance-aggtrade-overlap", "--plan", str(plan), "--base-dir", str(root),
                    "--source-registry", str(REGISTRY_PATH), "--output", str(output),
                ]))
            self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["complete"])
            with redirect_stderr(StringIO()):
                self.assertEqual(2, main([
                    "audit-binance-aggtrade-overlap", "--plan", str(plan), "--base-dir", str(root),
                    "--source-registry", str(REGISTRY_PATH), "--output", str(output),
                ]))
