import json
import tempfile
import unittest
from pathlib import Path

from trade_system.protocol import ProtocolError, ResearchProtocol
from trade_system.types import AvailabilityKind


class ProtocolTests(unittest.TestCase):
    def test_synthetic_protocol_does_not_allow_reconstructed_g2_or_e3(self):
        path = Path("config/research_protocol.paper.v1.json")
        protocol = ResearchProtocol.load(path)
        self.assertTrue(protocol.eligible(AvailabilityKind.ACTUAL, "E3"))
        self.assertFalse(protocol.eligible(AvailabilityKind.RECONSTRUCTED, "G2"))
        self.assertFalse(protocol.eligible(AvailabilityKind.RECONSTRUCTED, "E3"))

    def test_missing_market_label_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.json"
            path.write_text(json.dumps({
                "protocol_id": "x",
                "status": "SYNTHETIC_DEVELOPMENT_PROFILE",
                "availability_policy": {"allow_actual": True, "allow_reconstructed_for_g2": False},
                "action_contract": {"labels": ["TP", "SL"]},
                "execution_priors": {},
            }), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)

    def test_frozen_protocol_requires_all_preregistration_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "frozen.json"
            path.write_text(json.dumps({
                "protocol_id": "frozen-v1", "status": "FROZEN_RESEARCH_PROTOCOL", "notice": "fixed before holdout", "frozen_at": "2026-01-01T00:00:00Z",
                "availability_policy": {"allow_actual": True, "allow_reconstructed_for_g2": False},
                "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
                "risk_gate_profile": {"profile_id": "paper-risk-gate-profile.v1", "digest": "b" * 64},
                "data_eligibility": {"required_g1_policy_id": "g1.v1", "required_g1_report_sha256": "c" * 64, "require_g1_pass": True},
                "action_contract": {"labels": ["TP", "SL", "STRUCTURE_EXIT", "TIMEOUT"]},
                "execution_priors": {"latency_ms": 10, "fee_rate": 0, "funding_policy": "recorded", "cost_scenarios": ["normal"]},
                "data_sources": [{"source_id": "SRC", "endpoint_or_channel": "x", "schema_version": "v1", "instrument": "BTCUSDT", "allowed_availability": "ACTUAL_ONLY"}],
                "episode_policy": {"trigger": "x", "decision_frequency_seconds": 1, "max_holding_seconds": 60, "overlap_policy": "no overlap"},
                "label_policy": {"barrier_rules": "fixed", "same_timestamp_rule": "worst case", "operational_override_rule": "censor"},
                "evaluation_policy": {"primary_metrics": ["log_loss"], "min_effective_episodes": 10, "calibration_rule": "fixed", "cost_after_utility_rule": "fixed", "confidence_interval_rule": "fixed", "concentration_limits": "fixed"},
                "state_coverage_policy": {"classifier_id": "regime-v1", "classifier_digest": "d" * 64, "required_state_ids": ["CALM", "STRESSED"], "min_effective_episodes_per_state": 5, "insufficient_coverage_result": "INCONCLUSIVE/WAIT_DATA"},
                "split_policy": {"folds": 3, "embargo_seconds": 60, "training_calibration_policy": "walk-forward", "final_holdout": {"holdout_id": "h1", "start": "2026-04-01T00:00:00Z", "end": "2026-06-01T00:00:00Z", "opened_at": None, "reuse_policy": "ONE_TIME_ONLY"}},
                "hypotheses": [{"hypothesis_id": "H-001", "pass_condition": "fixed", "failure_condition": "fixed"}],
            }), encoding="utf-8")
            protocol = ResearchProtocol.load(path)
            self.assertTrue(protocol.is_frozen_for_research)
            protocol.assert_frozen_for_research()
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["split_policy"]["final_holdout"]["opened_at"] = "2026-03-31T00:00:00Z"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)

    def test_frozen_protocol_requires_state_coverage_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "frozen.json"
            valid = {
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
                "evaluation_policy": {"primary_metrics": ["log_loss"], "min_effective_episodes": 10, "calibration_rule": "fixed", "cost_after_utility_rule": "fixed", "confidence_interval_rule": "fixed", "concentration_limits": "fixed"},
                "split_policy": {"folds": 3, "embargo_seconds": 60, "training_calibration_policy": "walk-forward", "final_holdout": {"holdout_id": "h1", "start": "2026-04-01T00:00:00Z", "end": "2026-06-01T00:00:00Z", "opened_at": None, "reuse_policy": "ONE_TIME_ONLY"}},
                "hypotheses": [{"hypothesis_id": "H-001", "pass_condition": "fixed", "failure_condition": "fixed"}],
            }
            path.write_text(json.dumps(valid), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)

    def test_frozen_protocol_rejects_short_embargo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid-frozen.json"
            path.write_text(json.dumps({
                "protocol_id": "x", "status": "FROZEN_RESEARCH_PROTOCOL", "notice": "x", "frozen_at": "x",
                "availability_policy": {"allow_actual": True, "allow_reconstructed_for_g2": False}, "action_contract": {"labels": ["TP", "SL", "STRUCTURE_EXIT", "TIMEOUT"]},
                "execution_priors": {"latency_ms": 1, "fee_rate": 0, "funding_policy": "x", "cost_scenarios": ["x"]}, "data_sources": [{"source_id": "x", "endpoint_or_channel": "x", "schema_version": "x", "instrument": "x", "allowed_availability": "ACTUAL_ONLY"}],
                "episode_policy": {"trigger": "x", "decision_frequency_seconds": 1, "max_holding_seconds": 60, "overlap_policy": "x"}, "label_policy": {"barrier_rules": "x", "same_timestamp_rule": "x", "operational_override_rule": "x"},
                "evaluation_policy": {"primary_metrics": ["x"], "min_effective_episodes": 1, "calibration_rule": "x", "cost_after_utility_rule": "x", "confidence_interval_rule": "x", "concentration_limits": "x"}, "split_policy": {"folds": 1, "embargo_seconds": 59, "final_holdout": "x"}, "hypotheses": [{"hypothesis_id": "x", "pass_condition": "x", "failure_condition": "x"}],
            }), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)

    def test_v2_draft_is_explicitly_not_preregistered_and_binds_episode_v2(self):
        protocol = ResearchProtocol.load(Path("config/research_protocol.v2.draft.json"))
        self.assertEqual("DRAFT_RESEARCH_PROTOCOL_V2", protocol.status)
        self.assertFalse(protocol.is_frozen_for_research)
        self.assertEqual("btc-usdt-absorption-episode-v2", protocol.raw["episode_policy"]["policy_id"])
        self.assertEqual(
            "d919eb5bd8eaf3a01e9a6e316a8d0876f00cbe9a55e14826b4c48f13440b2242",
            protocol.raw["episode_policy"]["digest"],
        )

    def test_v2_requires_theory_development_controls_and_holdout_boundary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path("config/research_protocol.v2.draft.json")
            raw = json.loads(source.read_text(encoding="utf-8"))
            raw["gate_criteria"][-1]["stage"] = "DEVELOPMENT"
            path = Path(temp_dir) / "invalid-v2.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)
            raw = json.loads(source.read_text(encoding="utf-8"))
            raw["gate_criteria"] = [
                gate for gate in raw["gate_criteria"]
                if gate["gate_id"] != "G2-H004-LIQUIDATION-OI-CONDITIONAL-ON-R"
            ]
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)

    def test_v2_rejects_add_stage_or_non_counterfactual_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path("config/research_protocol.v2.draft.json")
            raw = json.loads(source.read_text(encoding="utf-8"))
            raw["action_contract"]["stages"].append("ADD_POSITION_CONFIRMED")
            path = Path(temp_dir) / "invalid-v2-add.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)
            raw = json.loads(source.read_text(encoding="utf-8"))
            raw["action_contract"]["entry_policy"] = "MARKET_ORDER"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                ResearchProtocol.load(path)
