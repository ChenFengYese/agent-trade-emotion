import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trade_system.historical_evidence_ledger import HistoricalEvidenceLedgerError, verify_historical_evidence_ledger


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HistoricalEvidenceLedgerTests(unittest.TestCase):
    def _ledger(self, root: Path) -> Path:
        (root / "config").mkdir()
        (root / "trade_system").mkdir()
        (root / ".runtime").mkdir()
        plan = root / "config/plan.json"; plan.write_text("{}", encoding="utf-8")
        experiment = root / "trade_system/experiment.py"; experiment.write_text("x=1\n", encoding="utf-8")
        model = root / "trade_system/model.py"; model.write_text("x=2\n", encoding="utf-8")
        software = {"entrypoint": "fixture.run", "experiment_module": {"path": "/fixture/experiment.py", "workspace_path": "trade_system/experiment.py", "sha256": _sha(experiment)}, "model": {"class": "FixtureModel", "module_path": "/fixture/model.py", "workspace_path": "trade_system/model.py", "module_sha256": _sha(model)}}
        report = root / ".runtime/report.json"
        report.write_text(json.dumps({"plan_sha256": "report-plan", "input_manifest_sha256": "input-manifest", "software_bindings": software}), encoding="utf-8")
        plan_value = {"fixture": True}; plan.write_text(json.dumps(plan_value), encoding="utf-8")
        report_value = {"plan_sha256": hashlib.sha256(json.dumps(plan_value, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "input_manifest_sha256": hashlib.sha256(json.dumps({}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "input_audit": {}, "software_bindings": software, "venue": "BINANCE_COINM", "instrument": "BTCUSD_PERP", "plan_status": "FROZEN_BINANCE_CM_HISTORICAL_MECHANISM_PLAN_V1", "eligible_for_binance_g2": False, "trading_authorization": "DENIED", "rows": {"all": 1}, "cost_descriptive": {"locked_evaluation": {"status": "DESCRIPTIVE"}}}; report.write_text(json.dumps(report_value), encoding="utf-8")
        ledger = {"ledger_id": "fixture", "status": "FROZEN_BINANCE_CM_HISTORICAL_EVIDENCE_LEDGER_V1", "evidence_stage": "E0-X", "current_action": "STOP_CURRENT_V1_ACTION", "plan": {"path": "config/plan.json", "file_sha256": _sha(plan), "report_plan_sha256": report_value["plan_sha256"]}, "report": {"path": ".runtime/report.json", "file_sha256": _sha(report), "input_manifest_sha256": report_value["input_manifest_sha256"]}, "expected_report": {"rows": {"all": 1}, "locked_evaluation_cost": {"status": "DESCRIPTIVE"}}, "software_bindings": software, "date_evidence": [{"date": "2025-01-%02d" % day, "status": "SEEN_DEVELOPMENT"} for day in range(1, 29)], "hypothesis_adjudications": {"H-001": "NOT_ADJUDICATED", "H-002": "NOT_ADJUDICATED", "H-003": "WAIT_DATA", "H-004": "NOT_TESTED"}, "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}
        path = root / "config/ledger.json"; path.write_text(json.dumps(ledger), encoding="utf-8")
        return path

    def test_verifies_bounded_non_adjudicating_ledger(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = verify_historical_evidence_ledger(self._ledger(root), workspace_root=root)
            self.assertTrue(report["binding_verified"])
            self.assertFalse(report["eligible_for_binance_g2"])

    def test_report_digest_drift_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir); ledger = self._ledger(root)
            (root / ".runtime/report.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(HistoricalEvidenceLedgerError):
                verify_historical_evidence_ledger(ledger, workspace_root=root)
