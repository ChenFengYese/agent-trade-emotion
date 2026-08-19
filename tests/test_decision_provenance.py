import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from trade_system.cli import main
from trade_system.risk_gate_profile import RiskGateProfile


class DecisionProvenanceTests(unittest.TestCase):
    def _inputs(self, root: Path):
        model = root / "model.json"
        policy = root / "policy.json"
        features = root / "features.ndjson"
        decisions = root / "decisions.ndjson"
        model.write_text(json.dumps({"model_id": "model.v1", "required_sources": []}), encoding="utf-8")
        policy.write_text(json.dumps({
            "policy_id": "policy.v1", "status": "FROZEN_RESEARCH_ACTION_POLICY", "frozen_at": "2026-07-22T00:00:00Z",
            "feature_bundle_manifest_sha256": "a" * 64, "min_seconds_between_actions": 10,
            "rules": [{"rule_id": "rule", "side": "BUY", "feature": "D", "operator": "GTE", "threshold": 0,
                       "take_profit_bps": 10, "stop_loss_bps": 10, "horizon_seconds": 60}],
        }), encoding="utf-8")
        risk_path = Path(__file__).resolve().parents[1] / "config" / "risk_gate_profile.paper.v1.json"
        risk = RiskGateProfile.load(risk_path)
        features.write_text(json.dumps({
            "event_id": "event-1", "available_at": "2026-07-22T00:00:00Z", "availability_kind": "ACTUAL",
            "feature_version": "five-factor-proxy-v1", "episode_id": "episode-1", "episode_state": "OBSERVE",
            "quality_flags": [], "values": {"D": "0.1"},
        }) + "\n", encoding="utf-8")
        decisions.write_text(json.dumps({
            "event_id": "event-1", "decision_at": "2026-07-22T00:00:01Z", "feature_version": "five-factor-proxy-v1",
            "model_version": "model.v1", "policy_version": "policy.v1", "risk_profile_digest": risk.digest,
            "decision": {"trade": False, "reason": "NEGATIVE_OR_INSUFFICIENT_EV", "ev_fill": "-1", "ev_submit": "-1"},
        }) + "\n", encoding="utf-8")
        return decisions, features, model, policy, risk_path

    def test_cli_binds_decision_to_actual_feature_and_declared_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            decisions, features, model, policy, risk = self._inputs(Path(temp_dir))
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main([
                    "verify-shadow-decision-artifact", "--decisions", str(decisions), "--features", str(features),
                    "--model-artifact", str(model), "--action-policy", str(policy), "--risk-gate-profile", str(risk),
                ])
            self.assertEqual(0, result)
            report = json.loads(stdout.getvalue())
            self.assertTrue(report["valid"])
            self.assertEqual("policy.v1", report["policy_id"])

    def test_cli_rejects_future_leakage_or_wrong_artifact_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            decisions, features, model, policy, risk = self._inputs(Path(temp_dir))
            row = json.loads(decisions.read_text(encoding="utf-8"))
            row["decision_at"] = "2026-07-21T23:59:59Z"
            row["model_version"] = "other-model"
            decisions.write_text(json.dumps(row) + "\n", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main([
                    "verify-shadow-decision-artifact", "--decisions", str(decisions), "--features", str(features),
                    "--model-artifact", str(model), "--action-policy", str(policy), "--risk-gate-profile", str(risk),
                ])
            self.assertEqual(1, result)
            self.assertEqual(["event-1:decision_before_feature_available", "event-1:model_version"], json.loads(stdout.getvalue())["issues"])
