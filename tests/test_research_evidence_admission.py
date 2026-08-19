import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from trade_system.action_bundle import build_action_bundle
from trade_system.label_bundle import build_label_bundle
from trade_system.research_evidence_admission import (
    ResearchEvidenceAdmissionError,
    _assert_manifest_chain,
    admit_research_evidence,
    load_verified_research_evidence_admission,
)
from trade_system.research_report import sha256_file
from trade_system.state_label_bundle import build_state_label_bundle
from trade_system.state_classifier import StateClassifier


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest(value):
    value["manifest_sha256"] = hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
    return value


class ResearchEvidenceAdmissionTests(unittest.TestCase):
    def _chain(self, labels):
        feature = {"manifest_sha256": "f" * 64}
        action = {"manifest_sha256": "a" * 64, "feature_bundle_manifest_sha256": feature["manifest_sha256"]}
        label = {"manifest_sha256": "l" * 64, "feature_bundle_manifest_sha256": feature["manifest_sha256"], "action_bundle_manifest_sha256": action["manifest_sha256"]}
        state = {"manifest_sha256": "s" * 64, "feature_bundle_manifest_sha256": feature["manifest_sha256"], "label_bundle_manifest_sha256": label["manifest_sha256"], "labels_artifact_sha256": sha256_file(labels)}
        return feature, action, label, state

    def test_exact_feature_action_label_state_chain_is_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            labels = Path(temp_dir) / "labels.ndjson"
            labels.write_text('{"row":1}\n', encoding="utf-8")
            feature, action, label, state = self._chain(labels)
            _assert_manifest_chain(feature=feature, action=action, label=label, state=state, labels_path=labels)
            for manifest, key in ((action, "feature_bundle_manifest_sha256"), (label, "action_bundle_manifest_sha256"), (state, "label_bundle_manifest_sha256"), (state, "feature_bundle_manifest_sha256")):
                original = manifest[key]
                manifest[key] = "x" * 64
                with self.assertRaises(ResearchEvidenceAdmissionError):
                    _assert_manifest_chain(feature=feature, action=action, label=label, state=state, labels_path=labels)
                manifest[key] = original
            state["labels_artifact_sha256"] = "y" * 64
            with self.assertRaises(ResearchEvidenceAdmissionError):
                _assert_manifest_chain(feature=feature, action=action, label=label, state=state, labels_path=labels)

    def test_real_v2_action_label_state_chain_admits_and_rejects_manifest_drift(self):
        """Build the actual downstream artifacts; only raw-capture fixtures are stubbed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features = root / "features.ndjson"
            feature_rows = [
                {"event_id": "e1/decision", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_decision_eligible": True, "episode_id": "e1/buy", "episode_state": "RESPONDING", "values": {"mid_price": "100", "D_directional_pressure": "-2", "visible_depth_notional": 1000000}, "evidence": {"evidence_id": "e1"}},
                {"event_id": "e1/tp", "available_at": "2026-01-01T00:00:02Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_decision_eligible": True, "episode_id": "e1/buy", "episode_state": "RESPONDING", "values": {"mid_price": "100.3", "D_directional_pressure": "-2", "visible_depth_notional": 1000000}, "evidence": {"evidence_id": "e1"}},
            ]
            features.write_text("".join(json.dumps(row) + "\n" for row in feature_rows), encoding="utf-8")
            binding = {"protocol": {"id": "protocol.v2", "sha256": "9" * 64}, "role": "DEVELOPMENT", "capture_plan": {"id": "dev-plan", "sha256": "c" * 64}, "acceptance_policy": {"id": "dev-policy", "sha256": "d" * 64}, "acceptance_report": {"id": "dev-report", "sha256": "e" * 64}, "allowed_availability": "ACTUAL_ONLY"}
            feature_manifest = _manifest({"record_type": "feature_bundle_manifest", "bundle_id": "features.v2", "feature_artifact": str(features), "feature_artifact_sha256": sha256_file(features), "feature_rows": len(feature_rows), "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "collections": [{"evidence_id": "e1", "data_dir": str(root / "store"), "collection_id": "collection-1", "collection_audit_digest": "a" * 64, "collection_replay_digest": "b" * 64}], "evidence_binding": binding})
            feature_manifest_path = root / "features.manifest.json"; feature_manifest_path.write_text(_canonical(feature_manifest), encoding="utf-8")
            action_policy = root / "action-policy.json"
            rules = [
                {"rule_id": "buy", "side": "BUY", "stage": "ENTER_PROBE", "eligible_episode_states": ["RESPONDING"], "feature": "D_directional_pressure", "operator": "LTE", "threshold": "-0.5", "entry_policy": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "take_profit_bps": 20, "stop_loss_bps": 12, "horizon_seconds": 300, "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"}},
                {"rule_id": "sell", "side": "SELL", "stage": "ENTER_PROBE", "eligible_episode_states": ["RESPONDING"], "feature": "D_directional_pressure", "operator": "GTE", "threshold": "0.5", "entry_policy": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "take_profit_bps": 20, "stop_loss_bps": 12, "horizon_seconds": 300, "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"}},
            ]
            action_policy.write_text(json.dumps({"schema_version": "research-action-policy-v2", "policy_id": "actions.v2", "status": "FROZEN_RESEARCH_ACTION_POLICY", "frozen_at": "2026-01-01T00:00:00Z", "research_scope": "PROBE_ONLY", "feature_bundle_manifest_sha256": feature_manifest["manifest_sha256"], "min_seconds_between_actions": 1, "episode_binding": {"policy_id": "episode.v2", "sha256": "b" * 64, "feature_version": "features.v2", "derived_semantics_version": "episode-feature-v2", "decision_frequency_seconds": 1}, "rules": rules}), encoding="utf-8")
            actions, action_manifest = root / "actions.ndjson", root / "actions.manifest.json"
            build_action_bundle(feature_path=features, feature_manifest_path=feature_manifest_path, policy_path=action_policy, output_path=actions, manifest_path=action_manifest, actions_id="actions.v2")
            labels, label_manifest = root / "labels.ndjson", root / "labels.manifest.json"
            build_label_bundle(actions_path=actions, action_manifest_path=action_manifest, feature_path=features, feature_manifest_path=feature_manifest_path, output_path=labels, manifest_path=label_manifest, labels_id="labels.v2")
            classifier_path = root / "classifier.json"
            classifier_path.write_text(json.dumps({"classifier_id": "states.v1", "status": "FROZEN_STATE_CLASSIFIER", "frozen_at": "2026-01-01T00:00:00Z", "fallback_state_id": "STRESSED", "rules": [{"state_id": "NORMAL", "all": [{"feature": "visible_depth_notional", "min": 0}]}]}), encoding="utf-8")
            state_labels, state_manifest = root / "state.ndjson", root / "state.manifest.json"
            build_state_label_bundle(labels_path=labels, label_manifest_path=label_manifest, classifier_path=classifier_path, output_path=state_labels, manifest_path=state_manifest, state_labels_id="state.v1")
            fake_protocol = SimpleNamespace(protocol_id="protocol.v2", digest="9" * 64, raw={"schema_version": "research-protocol.v2", "data_eligibility": {"admitted_collection_roles": [{"role": "DEVELOPMENT", "capture_plan": {"id": "dev-plan", "sha256": "c" * 64}, "acceptance_policy": {"id": "dev-policy", "sha256": "d" * 64}, "time_window": {"decision_start": "2026-01-01T00:00:00Z", "decision_end": "2026-01-02T00:00:00Z", "label_horizon_seconds": 300}}]}, "g1_qualification": {"required_g1_policy_id": "g1", "required_g1_report_sha256": "a" * 64}}, assert_frozen_for_research=lambda: None, g1_qualification={"required_g1_policy_id": "g1", "required_g1_report_sha256": "a" * 64})
            plan = SimpleNamespace(plan_id="dev-plan", digest="c" * 64, slots=(SimpleNamespace(slot_id="slot-1"),))
            policy = SimpleNamespace(policy_id="dev-policy", digest="d" * 64)
            accepted = {"report_id": "dev-report", "report_sha256": "e" * 64, "qualified_collections": [{"data_dir": str(root / "store"), "collection_id": "collection-1", "collection_audit_digest": "a" * 64, "collection_replay_digest": "b" * 64}]}
            output = root / "admission.json"
            patches = [
                patch("trade_system.research_evidence_admission.ResearchProtocol.load", return_value=fake_protocol),
                patch("trade_system.research_evidence_admission.ForwardCapturePlan.load", return_value=plan),
                patch("trade_system.research_evidence_admission.G1AcceptancePolicy.load", side_effect=[policy, SimpleNamespace()]),
                patch("trade_system.research_evidence_admission.assert_equal_or_stricter_than_g1"),
                patch("trade_system.research_evidence_admission.load_verified_data_acceptance_report", return_value=accepted),
                patch("trade_system.research_evidence_admission.load_passed_g1_report"),
                patch("trade_system.research_evidence_admission._verify_collection", return_value={"collection_id": "collection-1"}),
            ]
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
                admitted = admit_research_evidence(protocol_path=root / "protocol.json", role="DEVELOPMENT", capture_plan_path=root / "plan.json", acceptance_policy_path=root / "policy.json", acceptance_report_path=root / "acceptance.json", baseline_g1_policy_path=root / "g1-policy.json", g1_report_path=root / "g1.json", feature_path=features, feature_manifest_path=feature_manifest_path, actions_path=actions, action_manifest_path=action_manifest, labels_path=labels, label_manifest_path=label_manifest, state_labels_path=state_labels, state_manifest_path=state_manifest, classifier_path=classifier_path, output_path=output, admission_id="development.v1")
            self.assertEqual("ADMITTED", admitted["status"])
            state_value = json.loads(state_manifest.read_text(encoding="utf-8"))
            verified = load_verified_research_evidence_admission(output, state_labels_path=state_labels, protocol=fake_protocol, role="DEVELOPMENT", state_label_manifest_sha256=state_value["manifest_sha256"])
            self.assertEqual(admitted["manifest_sha256"], verified["manifest_sha256"])
            with self.assertRaises(ResearchEvidenceAdmissionError):
                load_verified_research_evidence_admission(output, state_labels_path=state_labels, protocol=fake_protocol, role="DEVELOPMENT", state_label_manifest_sha256="x" * 64)
            manifest_value = state_value
            manifest_value["label_bundle_manifest_sha256"] = "x" * 64
            manifest_value.pop("manifest_sha256")
            manifest_value = _manifest(manifest_value)
            state_manifest.write_text(_canonical(manifest_value), encoding="utf-8")
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], self.assertRaises(ResearchEvidenceAdmissionError):
                admit_research_evidence(protocol_path=root / "protocol.json", role="DEVELOPMENT", capture_plan_path=root / "plan.json", acceptance_policy_path=root / "policy.json", acceptance_report_path=root / "acceptance.json", baseline_g1_policy_path=root / "g1-policy.json", g1_report_path=root / "g1.json", feature_path=features, feature_manifest_path=feature_manifest_path, actions_path=actions, action_manifest_path=action_manifest, labels_path=labels, label_manifest_path=label_manifest, state_labels_path=state_labels, state_manifest_path=state_manifest, classifier_path=classifier_path, output_path=root / "drift.json", admission_id="development.drift")
