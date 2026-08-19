import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trade_system.action_bundle import ActionBundleError, _context_allows_enter_probe, build_action_bundle


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ActionBundleTests(unittest.TestCase):
    def test_context_gate_is_fail_closed_for_missing_anchor_veto_or_invalid_book(self):
        binding = {"policy_id": "context.v1", "policy_sha256": "a" * 64, "artifact_sha256": "b" * 64}
        row = {
            "quality_flags": [], "context": {"context_policy_id": "context.v1", "context_policy_sha256": "a" * 64,
                "context_status": "READY", "decision_permission": "ELIGIBLE", "reason_codes": [],
                "directional_resilience_feature": "R_sell_bid_resilience_1s",
                "values": {"Z_episode_anchor_distance_bps": "1", "R_directional": "0", "R_directional_improvement": "0", "price_impact_1s": "0"}},
        }
        self.assertTrue(_context_allows_enter_probe(row, binding))
        for mutation in (
            {"context": dict(row["context"], decision_permission="ABSTAIN")},
            {"context": dict(row["context"], reason_codes=["TREND_CONTINUATION_OR_CONTEXT_UNAVAILABLE"])},
            {"context": dict(row["context"], values=dict(row["context"]["values"], Z_episode_anchor_distance_bps=None))},
            {"quality_flags": ["book_invalid"]},
        ):
            candidate = dict(row); candidate.update(mutation)
            self.assertFalse(_context_allows_enter_probe(candidate, binding))

    def test_context_bound_v2_action_uses_declared_episode_side_when_both_rules_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features = root / "features.ndjson"
            context = {"context_policy_id": "context.v1", "context_policy_sha256": "c" * 64,
                       "context_status": "READY", "decision_permission": "ELIGIBLE", "reason_codes": [],
                       "directional_resilience_feature": "R_sell_bid_resilience_1s",
                       "values": {"Z_episode_anchor_distance_bps": "1", "R_directional": "0", "R_directional_improvement": "0", "price_impact_1s": "0"}}
            row = {"event_id": "e1/decision", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_decision_eligible": True, "episode_reversal_side": "BUY", "episode_id": "e1/buy", "episode_state": "RESPONDING", "quality_flags": [], "context": context, "values": {"mid_price": "100", "D_directional_pressure": "0"}, "evidence": {"evidence_id": "e1"}}
            features.write_text(json.dumps(row) + "\n", encoding="utf-8")
            context_binding = {"policy_id": "context.v1", "policy_sha256": "c" * 64, "artifact_sha256": "d" * 64, "context_manifest_sha256": "e" * 64, "role_window": {"id": "window.v1", "sha256": "f" * 64}}
            manifest = {"record_type": "feature_bundle_manifest", "bundle_id": "features.v2", "g1_policy_id": "g1.v1", "g1_report_sha256": "a" * 64, "feature_artifact": str(features), "feature_artifact_sha256": hashlib.sha256(features.read_bytes()).hexdigest(), "feature_rows": 1, "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "collections": [{"evidence_id": "e1"}], "context_binding": context_binding}
            manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
            feature_manifest = root / "features.manifest.json"; feature_manifest.write_text(_canonical(manifest), encoding="utf-8")
            rules = []
            for rule_id, side, operator, threshold in (("buy", "BUY", "LTE", "1"), ("sell", "SELL", "GTE", "-1")):
                rules.append({"rule_id": rule_id, "side": side, "stage": "ENTER_PROBE", "eligible_episode_states": ["RESPONDING"], "feature": "D_directional_pressure", "operator": operator, "threshold": threshold, "entry_policy": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "take_profit_bps": 20, "stop_loss_bps": 12, "horizon_seconds": 300, "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True}})
            policy = root / "policy.json"
            policy.write_text(json.dumps({"schema_version": "research-action-policy-v2", "policy_id": "actions.v2", "status": "FROZEN_RESEARCH_ACTION_POLICY", "frozen_at": "2026-01-01T00:00:00Z", "research_scope": "PROBE_ONLY", "feature_bundle_manifest_sha256": manifest["manifest_sha256"], "min_seconds_between_actions": 1, "episode_binding": {"policy_id": "episode.v2", "sha256": "b" * 64, "feature_version": "features.v2", "derived_semantics_version": "v2", "decision_frequency_seconds": 1}, "context_binding": {"policy_id": "context.v1", "policy_sha256": "c" * 64, "artifact_sha256": "d" * 64}, "rules": rules}), encoding="utf-8")
            output, output_manifest = root / "actions.ndjson", root / "actions.manifest.json"
            build_action_bundle(feature_path=features, feature_manifest_path=feature_manifest, policy_path=policy, output_path=output, manifest_path=output_manifest, actions_id="actions.v2")
            actions = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["BUY"], [item["side"] for item in actions])

    def _features_and_manifest(self, root: Path):
        features = root / "features.ndjson"
        rows = [
            {"event_id": "e1/1", "available_at": "2026-01-01T00:00:00Z", "availability_kind": "ACTUAL", "episode_id": "e1/episode-1", "values": {"mid_price": "100", "D_directional_pressure": "-1"}, "evidence": {"evidence_id": "e1"}},
            {"event_id": "e1/2", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "episode_id": "e1/episode-1", "values": {"mid_price": "99", "D_directional_pressure": "-2"}, "evidence": {"evidence_id": "e1"}},
        ]
        features.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        manifest = {
            "record_type": "feature_bundle_manifest", "bundle_id": "features.v1", "g1_policy_id": "g1.v1", "g1_report_sha256": "a" * 64,
            "feature_artifact": str(features), "feature_artifact_sha256": hashlib.sha256(features.read_bytes()).hexdigest(), "feature_rows": len(rows),
            "episode_policy_id": "episode.v1", "episode_policy_sha256": "b" * 64,
            "collections": [{"evidence_id": "e1"}],
        }
        manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
        manifest_path = root / "features.manifest.json"
        manifest_path.write_text(_canonical(manifest), encoding="utf-8")
        return features, manifest_path, manifest

    def _policy(self, root: Path, feature_manifest_sha: str):
        path = root / "policy.json"
        path.write_text(json.dumps({
            "policy_id": "actions.v1", "status": "FROZEN_RESEARCH_ACTION_POLICY", "frozen_at": "2026-01-01T00:00:00Z",
            "feature_bundle_manifest_sha256": feature_manifest_sha, "min_seconds_between_actions": 60,
            "rules": [{
                "rule_id": "buy-pressure", "side": "BUY", "feature": "D_directional_pressure", "operator": "LTE", "threshold": "-0.5",
                "take_profit_bps": 100, "stop_loss_bps": 50, "horizon_seconds": 60,
            }],
        }), encoding="utf-8")
        return path

    def test_frozen_policy_generates_one_counterfactual_action_per_episode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features, feature_manifest, manifest = self._features_and_manifest(root)
            policy = self._policy(root, manifest["manifest_sha256"])
            output, output_manifest = root / "actions.ndjson", root / "actions.manifest.json"
            report = build_action_bundle(
                feature_path=features, feature_manifest_path=feature_manifest, policy_path=policy,
                output_path=output, manifest_path=output_manifest, actions_id="actions.g1.v1",
            )
            actions = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(1, len(actions))
            self.assertEqual("BUY", actions[0]["side"])
            self.assertEqual("COUNTERFACTUAL_FILLED_FOR_MARKET_LABEL_ONLY", actions[0]["execution_assumption"])
            self.assertEqual(1, report["actions_written"])

    def test_policy_rejects_a_different_feature_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features, feature_manifest, _manifest = self._features_and_manifest(root)
            policy = self._policy(root, "b" * 64)
            with self.assertRaises(ActionBundleError):
                build_action_bundle(
                    feature_path=features, feature_manifest_path=feature_manifest, policy_path=policy,
                    output_path=root / "actions.ndjson", manifest_path=root / "actions.manifest.json", actions_id="actions.g1.v1",
                )

    def test_v2_probe_only_actions_require_responding_decision_rows_and_never_claim_fills(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features = root / "features.ndjson"
            rows = [
                {"event_id": "e1/ignored", "available_at": "2026-01-01T00:00:00.100000Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_decision_eligible": False, "episode_id": "e1/buy", "episode_state": "RESPONDING", "values": {"mid_price": "100", "D_directional_pressure": "-2"}, "evidence": {"evidence_id": "e1"}},
                {"event_id": "e1/buy", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_decision_eligible": True, "episode_id": "e1/buy", "episode_state": "RESPONDING", "values": {"mid_price": "100", "D_directional_pressure": "-2"}, "evidence": {"evidence_id": "e1"}},
                {"event_id": "e1/sell", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_decision_eligible": True, "episode_id": "e1/sell", "episode_state": "RESPONDING", "values": {"mid_price": "100", "D_directional_pressure": "2"}, "evidence": {"evidence_id": "e1"}},
                {"event_id": "e1/failed", "available_at": "2026-01-01T00:00:02Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_decision_eligible": True, "episode_id": "e1/buy", "episode_state": "FAILED", "values": {"mid_price": "99", "D_directional_pressure": "-2"}, "evidence": {"evidence_id": "e1"}},
            ]
            features.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            manifest = {
                "record_type": "feature_bundle_manifest", "bundle_id": "features.v2", "g1_policy_id": "g1.v1", "g1_report_sha256": "a" * 64,
                "feature_artifact": str(features), "feature_artifact_sha256": hashlib.sha256(features.read_bytes()).hexdigest(), "feature_rows": len(rows),
                "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "collections": [{"evidence_id": "e1"}],
            }
            manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
            feature_manifest = root / "features.manifest.json"
            feature_manifest.write_text(_canonical(manifest), encoding="utf-8")
            policy = root / "policy.v2.json"
            policy.write_text(json.dumps({
                "schema_version": "research-action-policy-v2", "policy_id": "actions.v2", "status": "FROZEN_RESEARCH_ACTION_POLICY", "frozen_at": "2026-01-01T00:00:00Z",
                "research_scope": "PROBE_ONLY", "feature_bundle_manifest_sha256": manifest["manifest_sha256"], "min_seconds_between_actions": 1,
                "episode_binding": {"policy_id": "episode.v2", "sha256": "b" * 64, "feature_version": "features.v2", "derived_semantics_version": "episode-feature-v2", "decision_frequency_seconds": 1},
                "rules": [
                    {"rule_id": "buy", "side": "BUY", "stage": "ENTER_PROBE", "eligible_episode_states": ["RESPONDING"], "feature": "D_directional_pressure", "operator": "LTE", "threshold": "-0.5", "entry_policy": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "take_profit_bps": 20, "stop_loss_bps": 12, "horizon_seconds": 300, "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"}},
                    {"rule_id": "sell", "side": "SELL", "stage": "ENTER_PROBE", "eligible_episode_states": ["RESPONDING"], "feature": "D_directional_pressure", "operator": "GTE", "threshold": "0.5", "entry_policy": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "take_profit_bps": 20, "stop_loss_bps": 12, "horizon_seconds": 300, "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"}},
                ],
            }), encoding="utf-8")
            output, output_manifest = root / "actions.ndjson", root / "actions.manifest.json"
            report = build_action_bundle(feature_path=features, feature_manifest_path=feature_manifest, policy_path=policy, output_path=output, manifest_path=output_manifest, actions_id="actions.v2")
            actions = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["BUY", "SELL"], [action["side"] for action in actions])
            self.assertTrue(all(action["execution_evidence"] is False for action in actions))
            self.assertTrue(all("execution_outcome" not in action and "fill_fraction" not in action and "structure_invalidated_at" not in action for action in actions))
            self.assertTrue(all(action["market_path_entry_assumption"] == "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY" for action in actions))
            self.assertEqual(["e1/buy", "e1/sell"], [action["feature_event_id"] for action in actions])
            self.assertEqual("PROBE_ONLY", report["research_scope"])
