import json
import tempfile
import unittest
from pathlib import Path

from trade_system.holdout_ledger import (
    HoldoutLedgerError,
    consume_final_holdout_release,
    open_final_holdout,
    verify_final_holdout_release,
)
from trade_system.protocol import ResearchProtocol
from trade_system.research_report import sha256_file


class HoldoutLedgerTests(unittest.TestCase):
    @staticmethod
    def _protocol() -> dict:
        return {
            "protocol_id": "frozen-v1", "status": "FROZEN_RESEARCH_PROTOCOL", "notice": "fixed", "frozen_at": "2026-01-01T00:00:00Z",
            "availability_policy": {"allow_actual": True, "allow_reconstructed_for_g2": False},
            "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
            "risk_gate_profile": {"profile_id": "paper-risk-gate-profile.v1", "digest": "b" * 64},
            "data_eligibility": {"required_g1_policy_id": "g1.v1", "required_g1_report_sha256": "c" * 64, "require_g1_pass": True},
            "action_contract": {"labels": ["TP", "SL", "STRUCTURE_EXIT", "TIMEOUT"]},
            "execution_priors": {"latency_ms": 10, "fee_rate": 0, "funding_policy": "recorded", "cost_scenarios": ["normal"]},
            "data_sources": [{"source_id": "SRC", "endpoint_or_channel": "x", "schema_version": "v1", "instrument": "BTCUSDT", "allowed_availability": "ACTUAL_ONLY"}],
            "episode_policy": {"trigger": "x", "decision_frequency_seconds": 1, "max_holding_seconds": 60, "overlap_policy": "no overlap"},
            "label_policy": {"barrier_rules": "fixed", "same_timestamp_rule": "worst case", "operational_override_rule": "censor"},
            "evaluation_policy": {"primary_metrics": ["log_loss"], "min_effective_episodes": 2, "calibration_rule": "fixed", "cost_after_utility_rule": "fixed", "confidence_interval_rule": "fixed", "concentration_limits": "fixed"},
            "state_coverage_policy": {"classifier_id": "regime-v1", "classifier_digest": "d" * 64, "required_state_ids": ["CALM", "STRESSED"], "min_effective_episodes_per_state": 1, "insufficient_coverage_result": "INCONCLUSIVE/WAIT_DATA"},
            "split_policy": {"folds": 1, "embargo_seconds": 60, "training_calibration_policy": "walk-forward", "final_holdout": {"holdout_id": "final-2026q2", "start": "2026-04-01T00:00:00Z", "end": "2026-06-01T00:00:00Z", "opened_at": None, "reuse_policy": "ONE_TIME_ONLY"}},
            "hypotheses": [{"hypothesis_id": "H-001", "pass_condition": "fixed", "failure_condition": "fixed"}],
        }

    def test_final_holdout_is_opened_once_and_bound_to_exact_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protocol_path, labels_path = root / "protocol.json", root / "labels.ndjson"
            protocol_path.write_text(json.dumps(self._protocol()), encoding="utf-8")
            labels_path.write_text("\n".join(json.dumps(row) for row in [
                {"episode_id": "pre", "decision_at": "2026-03-01T00:00:00Z", "label_end_at": "2026-03-01T00:01:00Z", "outcome": "TP", "censored": False},
                {"episode_id": "holdout", "decision_at": "2026-04-02T00:00:00Z", "label_end_at": "2026-04-02T00:01:00Z", "outcome": "SL", "censored": False},
                {"episode_id": "after", "decision_at": "2026-06-02T00:00:00Z", "label_end_at": "2026-06-02T00:01:00Z", "outcome": "TP", "censored": False},
            ]) + "\n", encoding="utf-8")
            protocol = ResearchProtocol.load(protocol_path)
            report = open_final_holdout(
                protocol=protocol, labels_path=labels_path, registry_dir=root / "ledger", output_path=root / "release.json",
                confirm_release_candidate=True, confirm_no_other_writers=True,
            )
            self.assertEqual("FINAL_HOLDOUT_OPENED_ONCE", report["release_status"])
            self.assertEqual(1, report["counts"]["released_eligible_rows"])
            self.assertEqual(1, report["counts"]["pre_holdout_eligible_rows"])
            verification = verify_final_holdout_release(
                protocol=protocol, labels_path=labels_path, registry_dir=root / "ledger", release_path=root / "release.json",
            )
            self.assertTrue(verification["valid"])
            evaluation = root / "evaluation.json"
            evaluation.write_text('{"result":"inconclusive"}\n', encoding="utf-8")
            consumption = consume_final_holdout_release(
                protocol=protocol, labels_path=labels_path, registry_dir=root / "ledger", release_path=root / "release.json",
                evaluation_report_path=evaluation, evaluation_report_sha256=sha256_file(evaluation),
            )
            self.assertTrue(Path(consumption["evaluation_report_path"]).exists())
            with self.assertRaisesRegex(HoldoutLedgerError, "already consumed"):
                consume_final_holdout_release(
                    protocol=protocol, labels_path=labels_path, registry_dir=root / "ledger", release_path=root / "release.json",
                    evaluation_report_path=evaluation, evaluation_report_sha256=sha256_file(evaluation),
                )
            with self.assertRaisesRegex(HoldoutLedgerError, "already opened"):
                open_final_holdout(
                    protocol=protocol, labels_path=labels_path, registry_dir=root / "ledger", output_path=root / "second-release.json",
                    confirm_release_candidate=True, confirm_no_other_writers=True,
                )
            labels_path.write_text(labels_path.read_text(encoding="utf-8") + json.dumps({"episode_id": "tamper", "decision_at": "2026-04-03T00:00:00Z", "label_end_at": "2026-04-03T00:01:00Z", "outcome": "TP", "censored": False}) + "\n", encoding="utf-8")
            self.assertFalse(verify_final_holdout_release(
                protocol=protocol, labels_path=labels_path, registry_dir=root / "ledger", release_path=root / "release.json",
            )["valid"])

    def test_empty_final_holdout_does_not_consume_the_registry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protocol_path, labels_path = root / "protocol.json", root / "labels.ndjson"
            protocol_path.write_text(json.dumps(self._protocol()), encoding="utf-8")
            labels_path.write_text(json.dumps({"episode_id": "pre", "decision_at": "2026-03-01T00:00:00Z", "label_end_at": "2026-03-01T00:01:00Z", "outcome": "TP", "censored": False}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(HoldoutLedgerError, "no eligible"):
                open_final_holdout(
                    protocol=ResearchProtocol.load(protocol_path), labels_path=labels_path, registry_dir=root / "ledger", output_path=root / "release.json",
                    confirm_release_candidate=True, confirm_no_other_writers=True,
                )
            self.assertFalse((root / "release.json").exists())
            self.assertFalse((root / "ledger").exists())
