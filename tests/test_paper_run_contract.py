import json
import tempfile
import unittest
from pathlib import Path

from trade_system.action_policy import ResearchActionPolicy
from trade_system.model_artifact import ModelArtifact
from trade_system.paper_audit import PaperAuditTrail
from trade_system.paper_run_contract import (
    PaperRunContract,
    PaperRunContractError,
    seal_paper_run,
    verify_paper_run_binding,
    verify_paper_run_evidence,
)
from trade_system.research_report import sha256_file
from trade_system.risk_gate_profile import RiskGateProfile
from trade_system.source_registry import SourceRegistry
from trade_system.state_classifier import StateClassifier


class PaperRunContractTests(unittest.TestCase):
    @staticmethod
    def _contract() -> dict:
        digest_char = {"model": "a", "action_policy": "b", "risk_gate_profile": "c", "source_registry": "d", "state_classifier": "e", "input_evidence": "f"}
        binding = lambda name: {"id": name + ".v1", "sha256": (digest_char[name] * 64)}
        return {
            "contract_id": "paper-run-contract.v1", "schema_version": "paper-run-contract.v1", "status": "FROZEN_PAPER_RUN_CONTRACT", "frozen_at": "2026-07-22T00:00:00Z",
            "scope": "PAPER_ONLY", "permissions": {"credentials": "FORBIDDEN", "orders": "FORBIDDEN", "withdrawals": "FORBIDDEN"},
            "bindings": {name: binding(name) for name in ("model", "action_policy", "risk_gate_profile", "source_registry", "state_classifier", "input_evidence")},
            "execution": {"broker": "LOCAL_PAPER_IOC", "allow_live_execution": False, "allow_testnet_execution": False},
        }

    def test_finalized_paper_audit_is_sealed_only_with_exact_contract_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path, audit_path, manifest_path = root / "contract.json", root / "audit.ndjson", root / "manifest.json"
            contract_path.write_text(json.dumps(self._contract()), encoding="utf-8")
            contract = PaperRunContract.load(contract_path)
            trail = PaperAuditTrail(audit_path, run_id="paper-bound-1", context=contract.audit_context())
            trail.append("INTENT_ACKNOWLEDGED", {"state": {"position_quantity": "0", "orders": {}}})
            trail.finalize({"position_quantity": "0", "orders": {}})
            verification = verify_paper_run_binding(audit_path, contract)
            self.assertTrue(verification["valid"])
            manifest = seal_paper_run(audit_path, contract, manifest_path)
            self.assertEqual(contract.digest, manifest["contract_sha256"])
            self.assertTrue(manifest_path.exists())
            with self.assertRaises(PaperRunContractError):
                seal_paper_run(audit_path, contract, manifest_path)

    def test_context_or_permissions_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path, audit_path = root / "contract.json", root / "audit.ndjson"
            raw = self._contract()
            raw["permissions"]["orders"] = "ALLOWED"
            contract_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(PaperRunContractError, "order-free"):
                PaperRunContract.load(contract_path)
            contract_path.write_text(json.dumps(self._contract()), encoding="utf-8")
            contract = PaperRunContract.load(contract_path)
            trail = PaperAuditTrail(audit_path, run_id="paper-bound-2", context={"scope": "SYNTHETIC_DEMO_ONLY"})
            trail.finalize({"position_quantity": "0", "orders": {}})
            self.assertFalse(verify_paper_run_binding(audit_path, contract)["valid"])

    def test_evidence_verifier_rehashes_every_bound_local_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            action_path, state_path, evidence_path, contract_path = root / "action.json", root / "state.json", root / "evidence.ndjson", root / "contract.json"
            action_path.write_text(json.dumps({
                "policy_id": "action.v1", "status": "FROZEN_RESEARCH_ACTION_POLICY", "frozen_at": "2026-01-01T00:00:00Z", "feature_bundle_manifest_sha256": "a" * 64, "min_seconds_between_actions": 1,
                "rules": [{"rule_id": "r1", "side": "BUY", "feature": "pressure", "operator": "GTE", "threshold": 0, "take_profit_bps": 1, "stop_loss_bps": 1, "horizon_seconds": 60}],
            }), encoding="utf-8")
            state_path.write_text(json.dumps({
                "classifier_id": "state.v1", "status": "FROZEN_STATE_CLASSIFIER", "fallback_state_id": "STRESSED", "rules": [{"state_id": "CALM", "all": [{"feature": "pressure", "min": 0}]}],
            }), encoding="utf-8")
            evidence_path.write_text('{"event_id":"e1"}\n', encoding="utf-8")
            project = Path(__file__).resolve().parents[1]
            model_path = project / "config" / "model_artifact.baseline.v1.json"
            risk_path = project / "config" / "risk_gate_profile.paper.v1.json"
            source_path = project / "config" / "source_registry.v3.json"
            model, action = ModelArtifact.load(model_path), ResearchActionPolicy.load(action_path)
            risk, source, state = RiskGateProfile.load(risk_path), SourceRegistry.load(source_path), StateClassifier.load(state_path)
            raw = self._contract()
            raw["bindings"] = {
                "model": {"id": model.model_id, "sha256": sha256_file(model_path)},
                "action_policy": {"id": action.policy_id, "sha256": action.digest},
                "risk_gate_profile": {"id": risk.profile_id, "sha256": risk.digest},
                "source_registry": {"id": source.registry_id, "sha256": source.sha256},
                "state_classifier": {"id": state.classifier_id, "sha256": state.digest},
                "input_evidence": {"id": "labels.v1", "sha256": sha256_file(evidence_path)},
            }
            contract_path.write_text(json.dumps(raw), encoding="utf-8")
            contract = PaperRunContract.load(contract_path)
            report = verify_paper_run_evidence(
                contract, model_artifact_path=model_path, action_policy_path=action_path, risk_gate_profile_path=risk_path,
                source_registry_path=source_path, state_classifier_path=state_path, input_evidence_path=evidence_path, input_evidence_id="labels.v1",
            )
            self.assertTrue(report["valid"])
            evidence_path.write_text('{"event_id":"changed"}\n', encoding="utf-8")
            self.assertFalse(verify_paper_run_evidence(
                contract, model_artifact_path=model_path, action_policy_path=action_path, risk_gate_profile_path=risk_path,
                source_registry_path=source_path, state_classifier_path=state_path, input_evidence_path=evidence_path, input_evidence_id="labels.v1",
            )["valid"])
