import csv
import hashlib
import io
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from trade_system.binance_cm_historical_diagnostic import HistoricalDiagnosticPlan
from trade_system.binance_cm_historical_mechanism import _HEADERS, _load_day
from trade_system.historical_diagnostic_development import _decision, _scores, build_day_rows


class HistoricalDiagnosticDevelopmentTests(unittest.TestCase):
    def test_candidate_selection_requires_both_outcome_free_response_predicates_and_predictive_gate_precedes_economic(self):
        class HighEv:
            def predict(self, row): return {"TP": .9, "SL": .05, "TIMEOUT": .05}
        row={"features":{"response_persistent":0.0,"price_decelerates":1.0},"label":{"outcome":"TP","gross_return_bps":20.0}}
        candidate=_scores([row],HighEv(),0.0,10.0,candidate=True)
        control=_scores([row],HighEv(),0.0,10.0,candidate=False)
        self.assertEqual(0,candidate["eligible_count"]); self.assertEqual(0,candidate["selected_count"]); self.assertEqual(1,control["selected_count"])
        plan=HistoricalDiagnosticPlan.load(Path(__file__).resolve().parents[1] / "config/binance_cm_historical_diagnostic.v2.jan_development.json")
        coverage={"effective_episodes":600,"utc_days":7,"by_side":{"BUY":300,"SELL":300},"by_state":{"THIN_BOOK":100,"NORMAL_BOOK":400,"DEEP_BOOK":100},"max_day_concentration":.1,"max_state_concentration":.4,"max_direction_concentration":.5}
        predictive={"BUY":{"candidate":{"log_loss":1.0,"multiclass_brier":.5},"control":{"log_loss":.9,"multiclass_brier":.4}}}
        self.assertEqual("STOP_PREDICTIVE",_decision(coverage,predictive,{"candidate_base_lower95":1,"incremental_lower95":1},{"stress_mean_bps":1},plan)["decision"])
    def _archive(self, root, kind, day, rows):
        name = "BTCUSD_PERP-%s-%s.zip" % (kind, day.isoformat())
        path = root / name
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=_HEADERS[kind]); writer.writeheader(); writer.writerows(rows)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(name[:-4] + ".csv", stream.getvalue())
        path.with_name(path.name + ".CHECKSUM").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + name, encoding="utf-8")

    def test_checksum_validated_raw_fixture_reaches_post_pressure_three_class_row(self):
        plan = HistoricalDiagnosticPlan.load(Path(__file__).resolve().parents[1] / "config/binance_cm_historical_diagnostic.v2.jan_development.json")
        day = date(2025, 1, 1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def ms(text): return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)
            trades=[]
            for index, stamp in enumerate(["2025-01-01T00:04:59", "2025-01-01T00:09:59", "2025-01-01T00:10:30", "2025-01-01T00:11:01", "2025-01-01T00:11:31", "2025-01-01T00:12:31", "2025-01-01T00:13:31", "2025-01-01T00:14:31", "2025-01-01T00:15:31", "2025-01-01T00:16:01"]):
                trades.append({"agg_trade_id":str(index+1),"price":"100","quantity":"50000" if index==1 else "1","first_trade_id":str(index+1),"last_trade_id":str(index+1),"transact_time":str(ms(stamp)),"is_buyer_maker":"false"})
            depth=[]
            for stamp in ("2025-01-01 00:09:30", "2025-01-01 00:10:00", "2025-01-01 00:10:30", "2025-01-01 00:11:00"):
                depth.extend(({"timestamp":stamp,"percentage":"-1","depth":"1400000","notional":"1"},{"timestamp":stamp,"percentage":"1","depth":"1400000","notional":"1"}))
            metrics=[]
            for stamp, oi in (("2025-01-01 00:05:00","100"),("2025-01-01 00:10:00","101")):
                metrics.append({"create_time":stamp,"symbol":"BTCUSD_PERP","sum_open_interest":oi,"sum_open_interest_value":"1","count_toptrader_long_short_ratio":"1","sum_toptrader_long_short_ratio":"1","count_long_short_ratio":"1","sum_taker_long_short_vol_ratio":"1"})
            self._archive(root,"aggTrades",day,trades); self._archive(root,"bookDepth",day,depth); self._archive(root,"metrics",day,metrics)
            rows=build_day_rows(_load_day(SimpleNamespace(instrument="BTCUSD_PERP"),root,day),plan)
        self.assertEqual(1,len(rows)); row=rows[0]
        self.assertEqual("WATCH",row["stage"]); self.assertEqual("BUY",row["pressure_side"]); self.assertEqual("SELL",row["side"]); self.assertIn(row["label"]["outcome"],{"TP","SL","TIMEOUT"})
        self.assertEqual(30.0,row["actual_timestamp_quality"]["pressure_book_gap_seconds"])
        self.assertEqual(300.0,row["actual_timestamp_quality"]["oi_gap_seconds"])
