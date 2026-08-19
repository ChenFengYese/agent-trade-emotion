import json
import tempfile
import unittest
from pathlib import Path

from trade_system.historical_audit import HistoricalAuditPlan, audit_plan, write_audit_report


class HistoricalAuditTests(unittest.TestCase):
    def _plan(self, path: Path, file_name: str):
        path.write_text(json.dumps({
            "audit_id": "okx-sample-v1", "status": "DRAFT_TEMPLATE", "source_id": "SRC-OKX-HIST", "venue": "OKX",
            "purpose": "REPLAY_AND_EXTERNAL_MECHANISM_ONLY",
            "files": [{"date": "2026-01-01", "path": file_name, "instrument": "BTC-USDT-SWAP", "stream": "ORDER_BOOK_L2", "format": "JSONL", "timestamp_path": "ts", "bids_path": "bids", "asks_path": "asks"}],
        }), encoding="utf-8")

    def test_audit_reports_local_file_hash_date_and_actual_depth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample = root / "sample.jsonl"
            sample.write_text("\n".join([
                json.dumps({"ts": "2026-01-01T00:00:00Z", "bids": [["100", "1"], ["99", "2"]], "asks": [["101", "1"]]}),
                json.dumps({"ts": "2026-01-01T00:00:01Z", "bids": [["100", "1"]], "asks": [["101", "1"], ["102", "2"], ["103", "3"]]}),
            ]) + "\n", encoding="utf-8")
            plan_path = root / "plan.json"
            self._plan(plan_path, sample.name)
            report = audit_plan(HistoricalAuditPlan.load(plan_path), base_dir=root)
            item = report["files"][0]
            self.assertTrue(report["complete"])
            self.assertFalse(report["eligible_for_binance_g2"])
            self.assertEqual(2, item["max_bid_levels_in_sample"])
            self.assertEqual(3, item["max_ask_levels_in_sample"])
            self.assertTrue(item["requested_date_observed"])
            output = write_audit_report(root / "report.json", report)
            self.assertTrue(output.exists())
            with self.assertRaises(FileExistsError):
                write_audit_report(output, report)

    def test_missing_declared_file_is_explicit_and_not_zero_filled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "plan.json"
            self._plan(plan_path, "missing.jsonl")
            report = audit_plan(HistoricalAuditPlan.load(plan_path), base_dir=root)
            self.assertFalse(report["complete"])
            self.assertEqual("MISSING", report["files"][0]["status"])
