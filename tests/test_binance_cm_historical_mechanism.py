import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from trade_system.binance_cm_historical_mechanism import HistoricalMechanismError, HistoricalMechanismPlan, run_historical_mechanism_experiment, write_historical_mechanism_report


class BinanceCmHistoricalMechanismTests(unittest.TestCase):
    def _archive(self, root: Path, kind: str, header: str, rows: str) -> None:
        name = "BTCUSD_PERP-%s-2025-01-01.zip" % kind
        path = root / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(name[:-4] + ".csv", header + "\n" + rows)
        (root / (name + ".CHECKSUM")).write_text("%s  %s\n" % (hashlib.sha256(path.read_bytes()).hexdigest(), name), encoding="utf-8")

    def _plan(self, root: Path) -> HistoricalMechanismPlan:
        plan = root / "plan.json"
        plan.write_text(json.dumps({"experiment_id": "smoke", "status": "FROZEN_BINANCE_CM_HISTORICAL_MECHANISM_SMOKE_PLAN_V1", "venue": "BINANCE_COINM", "instrument": "BTCUSD_PERP", "dates": ["2025-01-01"], "development_dates": ["2025-01-01"], "evaluation_dates": [], "min_rows_per_side": 1, "liquidity_state_thresholds": {"thin_max_depth": 100, "deep_min_depth": 200}}), encoding="utf-8")
        return HistoricalMechanismPlan.load(plan)

    def _input(self, root: Path) -> None:
        self._archive(root, "aggTrades", "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker", "1,100,1000,1,1,1735689600000,false\n2,100,1000,2,2,1735690200000,false\n3,100.3,1,3,3,1735690200300,false")
        self._archive(root, "bookDepth", "timestamp,percentage,depth,notional", "2025-01-01 00:00:00,-1,100,1\n2025-01-01 00:00:00,1,100,1\n2025-01-01 00:05:00,-1,100,1\n2025-01-01 00:05:00,1,100,1")
        self._archive(root, "metrics", "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio", "2025-01-01 00:00:00,BTCUSD_PERP,100,1,,,,1\n2025-01-01 00:05:00,BTCUSD_PERP,101,1,,,,1")

    def test_smoke_audits_inputs_and_never_becomes_g2_eligible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._input(root)
            report = run_historical_mechanism_experiment(self._plan(root), input_root=root)
            self.assertFalse(report["eligible_for_binance_g2"])
            self.assertEqual("DENIED", report["trading_authorization"])
            self.assertEqual("UNTESTABLE_MISSING_LIQUIDATION", report["hypotheses"]["H-004"]["status"])
            self.assertEqual(3, len(report["input_audit"]["2025-01-01"]))
            aggregate = report["input_audit"]["2025-01-01"]["aggTrades"]
            self.assertEqual(aggregate["archive_sha256"], aggregate["official_declared_archive_sha256"])
            self.assertEqual(64, len(aggregate["checksum_file_sha256"]))
            self.assertIn("source_url", aggregate)
            self.assertIn("checksum_source_url", aggregate)
            self.assertEqual("trade_system.binance_cm_historical_mechanism.run_historical_mechanism_experiment", report["software_bindings"]["entrypoint"])
            self.assertEqual(64, len(report["software_bindings"]["experiment_module"]["sha256"]))
            self.assertEqual("trade_system.research.RegularizedMultinomialLogistic", report["software_bindings"]["model"]["class"])
            output = write_historical_mechanism_report(root / "report.json", report)
            with self.assertRaises(FileExistsError):
                write_historical_mechanism_report(output, report)

    def test_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._input(root)
            (root / "BTCUSD_PERP-metrics-2025-01-01.zip.CHECKSUM").write_text("%s  BTCUSD_PERP-metrics-2025-01-01.zip\n" % ("0" * 64), encoding="utf-8")
            with self.assertRaises(HistoricalMechanismError):
                run_historical_mechanism_experiment(self._plan(root), input_root=root)

    def test_checksum_file_format_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._input(root)
            (root / "BTCUSD_PERP-bookDepth-2025-01-01.zip.CHECKSUM").write_text("not-a-checksum\n", encoding="utf-8")
            with self.assertRaises(HistoricalMechanismError):
                run_historical_mechanism_experiment(self._plan(root), input_root=root)
