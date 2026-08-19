import tempfile
import unittest
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import trade_system.historical_diagnostic_application as diagnostic_application
from trade_system.historical_diagnostic_application import HistoricalDiagnosticApplicationError, _fresh_gate, _fresh_rows, execute_authorized_fresh_diagnostic, verify_receipt_bound_application
from trade_system.historical_diagnostic_authorization import get_authorization_registry_entry, sha256_file
from trade_system.binance_cm_historical_diagnostic import HistoricalDiagnosticPlan
from trade_system.binance_cm_historical_mechanism import _HEADERS
from tests.test_historical_diagnostic_authorization import HistoricalDiagnosticAuthorizationTests


class HistoricalDiagnosticApplicationTests(unittest.TestCase):
    def _passing_gate_inputs(self):
        coverage = {
            "effective_episodes": 600,
            "utc_days": 7,
            "by_side": {"BUY": 300, "SELL": 300},
            "by_state": {"THIN_BOOK": 200, "NORMAL_BOOK": 200, "DEEP_BOOK": 200},
            "max_day_concentration": 0.40,
            "max_state_concentration": 0.40,
            "max_direction_concentration": 0.70,
        }
        predictive = {
            side: {
                "candidate": {"log_loss": 0.80, "multiclass_brier": 0.10},
                "control": {"log_loss": 1.00, "multiclass_brier": 0.20},
            }
            for side in ("BUY", "SELL")
        }
        return coverage, predictive, {"candidate_base_lower95": 1.0, "incremental_lower95": 1.0}, 0.0

    def _frozen_plan(self):
        return HistoricalDiagnosticPlan.load(Path(__file__).resolve().parents[1] / "config/binance_cm_historical_diagnostic.v2.frozen_before_download.json")

    def test_fresh_gate_zero_episodes_stops_data_invalid(self):
        coverage, predictive, bootstrap, stress = self._passing_gate_inputs()
        coverage["effective_episodes"] = 0
        self.assertEqual("STOP_DATA_INVALID", _fresh_gate(coverage, predictive, bootstrap, stress, self._frozen_plan())["decision"])

    def test_fresh_gate_day_concentration_over_limit_waits(self):
        coverage, predictive, bootstrap, stress = self._passing_gate_inputs()
        coverage["max_day_concentration"] = 0.41
        self.assertEqual("WAIT_DATA_COVERAGE", _fresh_gate(coverage, predictive, bootstrap, stress, self._frozen_plan())["decision"])

    def test_fresh_gate_state_concentration_over_limit_waits(self):
        coverage, predictive, bootstrap, stress = self._passing_gate_inputs()
        coverage["max_state_concentration"] = 0.41
        self.assertEqual("WAIT_DATA_COVERAGE", _fresh_gate(coverage, predictive, bootstrap, stress, self._frozen_plan())["decision"])

    def test_fresh_gate_direction_concentration_over_limit_waits(self):
        coverage, predictive, bootstrap, stress = self._passing_gate_inputs()
        coverage["max_direction_concentration"] = 0.71
        self.assertEqual("WAIT_DATA_COVERAGE", _fresh_gate(coverage, predictive, bootstrap, stress, self._frozen_plan())["decision"])

    def _zip(self, root, kind, day, rows):
        name="BTCUSD_PERP-%s-%s.zip"%(kind,day); path=root/name; data=io.StringIO(); writer=csv.DictWriter(data,fieldnames=_HEADERS[kind]); writer.writeheader();writer.writerows(rows)
        with zipfile.ZipFile(path,"w") as z:z.writestr(name[:-4]+".csv",data.getvalue())
        Path(str(path)+".CHECKSUM").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"  "+name)
        return path

    def test_fresh_zip_fixture_parses_all_receipt_days_with_no_model_fit(self):
        plan=HistoricalDiagnosticPlan.load(Path(__file__).resolve().parents[1]/"config/binance_cm_historical_diagnostic.v2.frozen_before_download.json")
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); inputs=[]
            for day in plan.dates:
                def ms(t): return int(datetime.fromisoformat(day+"T"+t).replace(tzinfo=timezone.utc).timestamp()*1000)
                stamps=["00:04:59","00:09:59","00:10:30","00:11:01","00:11:31","00:12:31","00:13:31","00:14:31","00:15:31","00:16:01"]
                trades=[{"agg_trade_id":str(i+1),"price":"100","quantity":"50000" if i==1 else "1","first_trade_id":str(i+1),"last_trade_id":str(i+1),"transact_time":str(ms(t)),"is_buyer_maker":"false"} for i,t in enumerate(stamps)]
                depth=[]
                for t in ("00:09:30","00:10:00","00:10:30","00:11:00"):
                    depth += [{"timestamp":day+" "+t,"percentage":"-1","depth":"1400000","notional":"1"},{"timestamp":day+" "+t,"percentage":"1","depth":"1400000","notional":"1"}]
                metrics=[{"create_time":day+" 00:05:00","symbol":"BTCUSD_PERP","sum_open_interest":"100","sum_open_interest_value":"1","count_toptrader_long_short_ratio":"1","sum_toptrader_long_short_ratio":"1","count_long_short_ratio":"1","sum_taker_long_short_vol_ratio":"1"},{"create_time":day+" 00:10:00","symbol":"BTCUSD_PERP","sum_open_interest":"101","sum_open_interest_value":"1","count_toptrader_long_short_ratio":"1","sum_toptrader_long_short_ratio":"1","count_long_short_ratio":"1","sum_taker_long_short_vol_ratio":"1"}]
                for kind,rows in (("aggTrades",trades),("bookDepth",depth),("metrics",metrics)):
                    path=self._zip(root,kind,day,rows); inputs.append({"date":day,"kind":kind,"archive_path":path.name})
            rows=_fresh_rows(plan,{"inputs":inputs},root)
            self.assertEqual(28,len(rows)); self.assertTrue(all(x["data_role"]=="FRESH_SCORE_ONLY" and x["pressure_side"]=="BUY" and x["side"]=="SELL" for x in rows))
    def test_missing_receipt_and_contract_are_hard_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "frozen.json"; plan.write_text("{}", encoding="utf-8")
            with self.assertRaises(HistoricalDiagnosticApplicationError):
                verify_receipt_bound_application(plan_path=plan, contract_path=None, receipt_path=None, workspace_root=root)

    def test_raw_fixture_quality_passes_before_receipt_bound_score_only_handoff(self):
        fixture = HistoricalDiagnosticAuthorizationTests("test_exact_absence_inventory_refuses_existing_target_and_summary_drift")
        fixture.setUp()
        try:
            receipt_path, receipt = fixture._authorization_fixture()
            acquisition_path = fixture._acquisition_fixture(receipt_path, receipt)
            rows=[]
            for side in ("BUY","SELL"):
                for i in range(2): rows.append({"date":"2025-02-01","side":side,"state_id":"NORMAL_BOOK","features":{"D":1.0,"R":0.0,"response_persistent":1.0,"price_decelerates":1.0},"label":{"outcome":"TP","gross_return_bps":20.0}})
            with patch("trade_system.historical_diagnostic_application._fresh_rows", return_value=rows):
                report = execute_authorized_fresh_diagnostic(
                    plan_path=fixture.plan_path, contract_path=fixture.root / "evidence/contract.json", receipt_path=receipt_path,
                    acquisition_path=acquisition_path, registry_path=fixture.root / "evidence/registry.json", workspace_root=fixture.root,
                    report_path=fixture.root / "evidence/fresh-report.json", scoring_attempt_id="fixture-score-once",
                )
            self.assertEqual("INCONCLUSIVE_CONSUMED", report["status"])
            self.assertFalse(report["model_fit_performed"])
            self.assertTrue(report["fresh_inputs_scored"])
        finally:
            fixture.tearDown()

    def test_unpatched_84_zip_receipt_builder_execute_completes_once(self):
        fixture=HistoricalDiagnosticAuthorizationTests("test_exact_absence_inventory_refuses_existing_target_and_summary_drift"); fixture.setUp()
        try:
            receipt_path,receipt=fixture._authorization_fixture(); acquisition=fixture._acquisition_fixture(receipt_path,receipt)
            registry_path=fixture.root/"evidence/real-registry.json"; report_path=fixture.root/"evidence/real-report.json"
            report=execute_authorized_fresh_diagnostic(plan_path=fixture.plan_path,contract_path=fixture.root/"evidence/contract.json",receipt_path=receipt_path,acquisition_path=acquisition,registry_path=registry_path,workspace_root=fixture.root,report_path=report_path,scoring_attempt_id="real-zip-fixture")
            self.assertIn(report["status"],{"INCONCLUSIVE_CONSUMED","STOP_CURRENT_V2_PROXY","E0-X_COMPLETE_DESCRIPTIVE"}); self.assertFalse(report["model_fit_performed"]); self.assertFalse(report["calibration_fit_performed"]); self.assertIn("side_state_outcome",report)
            self.assertTrue(report["fresh_inputs_scored"]); self.assertEqual(84, len(report["acquisition"]["inputs"])); self.assertEqual(28, report["rows"]); self.assertEqual("WAIT_DATA_COVERAGE", report["gate"]["decision"])
            self.assertIn("SELL", report["evaluation_by_side"]); self.assertEqual(28, report["evaluation_by_side"]["SELL"]["candidate"]["observations"]); self.assertIsNotNone(report["evaluation_by_side"]["SELL"]["candidate"]["log_loss"]); self.assertIsNotNone(report["evaluation_by_side"]["SELL"]["control"]["log_loss"])
            entry=get_authorization_registry_entry(registry_path,receipt_id=receipt["receipt_id"],receipt_scope_sha256=receipt["receipt_scope_sha256"])
            self.assertEqual("SCORING_COMPLETE",entry["status"]); self.assertEqual(sha256_file(report_path),entry["final_report_sha256"])
            with self.assertRaises(HistoricalDiagnosticApplicationError): execute_authorized_fresh_diagnostic(plan_path=fixture.plan_path,contract_path=fixture.root/"evidence/contract.json",receipt_path=receipt_path,acquisition_path=acquisition,registry_path=registry_path,workspace_root=fixture.root,report_path=report_path,scoring_attempt_id="repeat")
        finally: fixture.tearDown()

    def test_post_consume_model_deletion_seals_failed_registry_and_refuses_repeat(self):
        fixture=HistoricalDiagnosticAuthorizationTests("test_exact_absence_inventory_refuses_existing_target_and_summary_drift"); fixture.setUp()
        try:
            receipt_path,receipt=fixture._authorization_fixture(); acquisition=fixture._acquisition_fixture(receipt_path,receipt)
            registry_path=fixture.root/"evidence/failure-registry.json"; report_path=fixture.root/"evidence/failure-report.json"
            model_path=fixture.root/receipt["january_v2_development_evidence"]["model"]["path"]
            original_consume=diagnostic_application.consume_fresh_scoring_authorization
            def consume_then_delete(*args,**kwargs):
                consumed=original_consume(*args,**kwargs)
                model_path.unlink()
                return consumed
            with patch.object(diagnostic_application,"consume_fresh_scoring_authorization",side_effect=consume_then_delete):
                with self.assertRaises(HistoricalDiagnosticApplicationError):
                    execute_authorized_fresh_diagnostic(plan_path=fixture.plan_path,contract_path=fixture.root/"evidence/contract.json",receipt_path=receipt_path,acquisition_path=acquisition,registry_path=registry_path,workspace_root=fixture.root,report_path=report_path,scoring_attempt_id="delete-after-consume")
            failure=json.loads(report_path.read_text(encoding="utf-8")); self.assertEqual("SCORING_FAILED_CONSUMED",failure["status"])
            entry=get_authorization_registry_entry(registry_path,receipt_id=receipt["receipt_id"],receipt_scope_sha256=receipt["receipt_scope_sha256"])
            self.assertEqual("SCORING_FAILED_CONSUMED",entry["status"]); self.assertEqual(sha256_file(report_path),entry["final_report_sha256"])
            with self.assertRaises(HistoricalDiagnosticApplicationError):
                execute_authorized_fresh_diagnostic(plan_path=fixture.plan_path,contract_path=fixture.root/"evidence/contract.json",receipt_path=receipt_path,acquisition_path=acquisition,registry_path=registry_path,workspace_root=fixture.root,report_path=report_path,scoring_attempt_id="repeat-after-consume-failure")
        finally: fixture.tearDown()

    def test_zero_fresh_rows_records_stop_data_invalid_and_completed_registry(self):
        fixture=HistoricalDiagnosticAuthorizationTests("test_exact_absence_inventory_refuses_existing_target_and_summary_drift"); fixture.setUp()
        try:
            receipt_path,receipt=fixture._authorization_fixture(); acquisition=fixture._acquisition_fixture(receipt_path,receipt)
            registry_path=fixture.root/"evidence/zero-registry.json"; report_path=fixture.root/"evidence/zero-report.json"
            with patch("trade_system.historical_diagnostic_application._fresh_rows",return_value=[]):
                report=execute_authorized_fresh_diagnostic(plan_path=fixture.plan_path,contract_path=fixture.root/"evidence/contract.json",receipt_path=receipt_path,acquisition_path=acquisition,registry_path=registry_path,workspace_root=fixture.root,report_path=report_path,scoring_attempt_id="zero-fresh-rows")
            self.assertEqual("STOP_CURRENT_V2_PROXY",report["status"]); self.assertEqual("STOP_DATA_INVALID",report["gate"]["decision"])
            entry=get_authorization_registry_entry(registry_path,receipt_id=receipt["receipt_id"],receipt_scope_sha256=receipt["receipt_scope_sha256"])
            self.assertEqual("SCORING_COMPLETE",entry["status"]); self.assertEqual(sha256_file(report_path),entry["final_report_sha256"])
        finally: fixture.tearDown()

    def test_incomplete_raw_fixture_records_wait_without_loading_model(self):
        fixture = HistoricalDiagnosticAuthorizationTests("test_exact_absence_inventory_refuses_existing_target_and_summary_drift")
        fixture.setUp()
        try:
            receipt_path, _ = fixture._authorization_fixture()
            report = execute_authorized_fresh_diagnostic(
                plan_path=fixture.plan_path, contract_path=fixture.root / "evidence/contract.json", receipt_path=receipt_path,
                acquisition_path=fixture.root / "evidence/missing-acquisition.json", registry_path=fixture.root / "evidence/wait-registry.json", workspace_root=fixture.root,
                report_path=fixture.root / "evidence/wait-report.json", scoring_attempt_id="must-not-score",
            )
            self.assertEqual("WAIT_DATA_NOT_SCORED", report["status"]); self.assertFalse(report["model_loaded"])
        finally:
            fixture.tearDown()
