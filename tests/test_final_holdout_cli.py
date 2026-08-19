import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from trade_system.cli import main
from trade_system.state_classifier import StateClassifier


class FinalHoldoutCliTests(unittest.TestCase):
    @staticmethod
    def _protocol(classifier: StateClassifier) -> dict:
        return {
            "protocol_id": "frozen-final.v1", "status": "FROZEN_RESEARCH_PROTOCOL", "notice": "fixed", "frozen_at": "2026-01-01T00:00:00Z",
            "availability_policy": {"allow_actual": True, "allow_reconstructed_for_g2": False},
            "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
            "risk_gate_profile": {"profile_id": "paper-risk-gate-profile.v1", "digest": "b" * 64},
            "data_eligibility": {"required_g1_policy_id": "g1.v1", "required_g1_report_sha256": "c" * 64, "require_g1_pass": True},
            "action_contract": {"labels": ["TP", "SL", "STRUCTURE_EXIT", "TIMEOUT"]},
            "execution_priors": {"latency_ms": 10, "fee_rate": 0, "funding_policy": "recorded", "cost_scenarios": ["normal"]},
            "data_sources": [{"source_id": "SRC", "endpoint_or_channel": "x", "schema_version": "v1", "instrument": "BTCUSDT", "allowed_availability": "ACTUAL_ONLY"}],
            "episode_policy": {"trigger": "x", "decision_frequency_seconds": 1, "max_holding_seconds": 60, "overlap_policy": "no overlap"},
            "label_policy": {"barrier_rules": "fixed", "same_timestamp_rule": "worst", "operational_override_rule": "censor"},
            "evaluation_policy": {"primary_metrics": ["log_loss"], "min_effective_episodes": 2, "calibration_rule": "fixed", "cost_after_utility_rule": "fixed", "confidence_interval_rule": "fixed", "concentration_limits": "fixed"},
            "state_coverage_policy": {"classifier_id": classifier.classifier_id, "classifier_digest": classifier.digest, "required_state_ids": ["CALM", "STRESSED"], "min_effective_episodes_per_state": 1, "insufficient_coverage_result": "INCONCLUSIVE/WAIT_DATA"},
            "split_policy": {"folds": 1, "embargo_seconds": 60, "training_calibration_policy": "walk-forward", "final_holdout": {"holdout_id": "final-q2", "start": "2026-04-01T00:00:00Z", "end": "2026-06-01T00:00:00Z", "opened_at": None, "reuse_policy": "ONE_TIME_ONLY"}},
            "hypotheses": [{"hypothesis_id": "H-001", "pass_condition": "fixed", "failure_condition": "fixed"}],
        }

    def test_final_holdout_evaluation_requires_and_consumes_verified_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            classifier_path, protocol_path, labels_path = root / "classifier.json", root / "protocol.json", root / "labels.ndjson"
            classifier_path.write_text(json.dumps({
                "classifier_id": "state.v1", "status": "FROZEN_STATE_CLASSIFIER", "fallback_state_id": "STRESSED",
                "rules": [{"state_id": "CALM", "all": [{"feature": "pressure", "min": 0}]}],
            }), encoding="utf-8")
            classifier = StateClassifier.load(classifier_path)
            protocol_path.write_text(json.dumps(self._protocol(classifier)), encoding="utf-8")
            rows = []
            for prefix, day in (("train", "2026-03"), ("hold", "2026-04")):
                for index, pressure in enumerate((1, -1)):
                    rows.append({
                        "episode_id": "%s-%d" % (prefix, index), "decision_at": "%s-%02dT00:00:00Z" % (day, index + 1), "label_end_at": "%s-%02dT00:01:00Z" % (day, index + 1),
                        "features": {"pressure": pressure}, "outcome": "TP" if pressure > 0 else "SL", "censored": False,
                        "state_id": "CALM" if pressure > 0 else "STRESSED", "state_classifier_id": classifier.classifier_id, "state_classifier_sha256": classifier.digest,
                    })
            labels_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            registry, release, evaluation = root / "registry", root / "release.json", root / "evaluation.json"
            with redirect_stdout(StringIO()):
                self.assertEqual(0, main([
                    "open-final-holdout", "--protocol", str(protocol_path), "--labels", str(labels_path), "--registry-dir", str(registry), "--output", str(release),
                    "--confirm-release-candidate", "--confirm-no-other-writers",
                ]))
            manifest = {"manifest_sha256": "f" * 64, "label_bundle_manifest_sha256": "g" * 64, "g1_policy_id": "g1.v1", "g1_report_sha256": "c" * 64}
            stdout = StringIO()
            with patch("trade_system.cli.load_passed_g1_report", return_value={"report_sha256": "c" * 64}), patch("trade_system.cli.load_verified_state_label_bundle_manifest", return_value=manifest), redirect_stdout(stdout):
                result = main([
                    "evaluate-final-holdout", "--input", str(labels_path), "--protocol", str(protocol_path), "--g1-report", str(root / "g1.json"),
                    "--state-classifier", str(classifier_path), "--labels-manifest", str(root / "labels-manifest.json"),
                    "--holdout-release", str(release), "--holdout-registry", str(registry), "--output", str(evaluation),
                ])
            self.assertEqual(0, result)
            report = json.loads(stdout.getvalue())
            self.assertIn("final_holdout_metrics", report)
            self.assertEqual("final_holdout_evaluation_consumption", report["final_holdout_consumption"]["record_type"])
            self.assertTrue(evaluation.exists())
