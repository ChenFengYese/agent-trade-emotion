import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trade_system.label_bundle import LabelBundleError, build_label_bundle


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class LabelBundleTests(unittest.TestCase):
    def _features_and_manifest(self, root: Path):
        features = root / "features.ndjson"
        rows = [
            {"event_id": "e1/0", "available_at": "2026-01-01T00:00:00Z", "availability_kind": "ACTUAL", "values": {"mid_price": "100"}, "evidence": {"evidence_id": "e1"}},
            {"event_id": "e2/1", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "values": {"mid_price": "98"}, "evidence": {"evidence_id": "e2"}},
            {"event_id": "e1/1", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "values": {"mid_price": "102"}, "evidence": {"evidence_id": "e1"}},
        ]
        features.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        manifest = {
            "record_type": "feature_bundle_manifest", "bundle_id": "features.v1", "g1_policy_id": "g1.v1",
            "g1_report_sha256": "a" * 64, "feature_artifact": str(features),
            "feature_artifact_sha256": hashlib.sha256(features.read_bytes()).hexdigest(), "feature_rows": len(rows),
            "episode_policy_id": "episode.v1", "episode_policy_sha256": "b" * 64,
            "collections": [{"evidence_id": "e1"}, {"evidence_id": "e2"}],
        }
        manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
        manifest_path = root / "features.manifest.json"
        manifest_path.write_text(_canonical(manifest), encoding="utf-8")
        return features, manifest_path

    def _action(self, evidence_id="e1"):
        return {
            "decision_id": "d-1", "episode_id": "episode-1", "decision_at": "2026-01-01T00:00:00Z",
            "filled_at": "2026-01-01T00:00:00Z", "side": "BUY", "stage": "ENTER_PROBE",
            "entry_price": "100", "take_profit": "102", "stop_loss": "98", "horizon_seconds": 60,
            "features": {"x": 1}, "evidence_id": evidence_id,
        }

    def _action_manifest(self, root: Path, actions: Path, feature_manifest: Path):
        feature = json.loads(feature_manifest.read_text(encoding="utf-8"))
        manifest = {
            "record_type": "research_action_bundle_manifest", "actions_id": "actions.v1", "actions_artifact": str(actions),
            "actions_artifact_sha256": hashlib.sha256(actions.read_bytes()).hexdigest(), "actions_written": 1,
            "feature_bundle_manifest_sha256": feature["manifest_sha256"], "feature_artifact_sha256": feature["feature_artifact_sha256"],
            "g1_policy_id": feature["g1_policy_id"], "g1_report_sha256": feature["g1_report_sha256"],
            "action_policy_id": "policy.v1", "action_policy_sha256": "a" * 64, "rules": ["rule"],
            "execution_assumption": "COUNTERFACTUAL_FILLED_FOR_MARKET_LABEL_ONLY",
        }
        manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
        path = root / "actions.manifest.json"
        path.write_text(_canonical(manifest), encoding="utf-8")
        return path

    def test_labels_use_only_the_action_evidence_path_and_write_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features, feature_manifest = self._features_and_manifest(root)
            actions = root / "actions.ndjson"
            actions.write_text(json.dumps(self._action()) + "\n", encoding="utf-8")
            action_manifest = self._action_manifest(root, actions, feature_manifest)
            output, manifest = root / "labels.ndjson", root / "labels.manifest.json"
            report = build_label_bundle(
                actions_path=actions, action_manifest_path=action_manifest, feature_path=features, feature_manifest_path=feature_manifest,
                output_path=output, manifest_path=manifest, labels_id="labels.v1",
            )
            label = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("TP", label["outcome"])
            self.assertEqual("e1", label["evidence_id"])
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), report["labels_artifact_sha256"])

    def test_labels_reject_unknown_action_evidence_or_tampered_features(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features, feature_manifest = self._features_and_manifest(root)
            actions = root / "actions.ndjson"
            actions.write_text(json.dumps(self._action("missing")) + "\n", encoding="utf-8")
            action_manifest = self._action_manifest(root, actions, feature_manifest)
            with self.assertRaises(LabelBundleError):
                build_label_bundle(
                    actions_path=actions, action_manifest_path=action_manifest, feature_path=features, feature_manifest_path=feature_manifest,
                    output_path=root / "labels.ndjson", manifest_path=root / "labels.manifest.json", labels_id="labels.v1",
                )
            actions.write_text(json.dumps(self._action()) + "\n", encoding="utf-8")
            action_manifest = self._action_manifest(root, actions, feature_manifest)
            with features.open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            with self.assertRaises(LabelBundleError):
                build_label_bundle(
                    actions_path=actions, action_manifest_path=action_manifest, feature_path=features, feature_manifest_path=feature_manifest,
                    output_path=root / "other-labels.ndjson", manifest_path=root / "other-labels.manifest.json", labels_id="labels.v1",
                )

    def test_v2_labels_derive_structure_exit_from_bound_feature_episode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features = root / "features.ndjson"
            feature_rows = [
                {"event_id": "e1/0", "available_at": "2026-01-01T00:00:00Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_id": "e1/episode-1", "episode_state": "RESPONDING", "episode_decision_eligible": True, "quality_flags": [], "values": {"mid_price": "100", "D_directional_pressure": "-1"}, "evidence": {"evidence_id": "e1"}},
                {"event_id": "e1/1", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "feature_version": "features.v2", "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "episode_id": "e1/episode-1", "episode_state": "FAILED", "episode_decision_eligible": True, "quality_flags": [], "values": {"mid_price": "100", "D_directional_pressure": "-1"}, "evidence": {"evidence_id": "e1"}},
            ]
            features.write_text("".join(json.dumps(row) + "\n" for row in feature_rows), encoding="utf-8")
            feature = {
                "record_type": "feature_bundle_manifest", "bundle_id": "features.v2", "g1_policy_id": "g1.v1", "g1_report_sha256": "a" * 64,
                "feature_artifact": str(features), "feature_artifact_sha256": hashlib.sha256(features.read_bytes()).hexdigest(), "feature_rows": 2,
                "episode_policy_id": "episode.v2", "episode_policy_sha256": "b" * 64, "collections": [{"evidence_id": "e1"}],
            }
            feature["manifest_sha256"] = hashlib.sha256(_canonical(feature).encode("utf-8")).hexdigest()
            feature_manifest = root / "features.manifest.json"
            feature_manifest.write_text(_canonical(feature), encoding="utf-8")
            action = {
                "action_schema_version": "research-action-v2", "decision_id": "d-v2", "episode_id": "e1/episode-1", "decision_at": "2026-01-01T00:00:00Z",
                "market_path_entry_at": "2026-01-01T00:00:00Z", "market_path_entry_assumption": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "execution_evidence": False,
                "feature_event_id": "e1/0",
                "side": "BUY", "stage": "ENTER_PROBE", "entry_price": "100", "take_profit": "102", "stop_loss": "98", "horizon_seconds": 60,
                "features": {"D_directional_pressure": -1, "mid_price": 100.0}, "evidence_id": "e1",
                "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"},
            }
            actions = root / "actions.ndjson"
            actions.write_text(json.dumps(action) + "\n", encoding="utf-8")
            action_manifest = self._action_manifest(root, actions, feature_manifest)
            legacy_output, legacy_manifest = root / "legacy-labels.ndjson", root / "legacy-labels.manifest.json"
            with self.assertRaises(LabelBundleError):
                build_label_bundle(actions_path=actions, action_manifest_path=action_manifest, feature_path=features, feature_manifest_path=feature_manifest, output_path=legacy_output, manifest_path=legacy_manifest, labels_id="labels.v2")
            manifest_value = json.loads(action_manifest.read_text(encoding="utf-8"))
            manifest_value.update({
                "action_schema_version": "research-action-v2", "research_scope": "PROBE_ONLY", "execution_evidence": False,
                "market_path_entry_assumption": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY",
                "episode_binding": {"policy_id": "episode.v2", "sha256": "b" * 64, "feature_version": "features.v2", "derived_semantics_version": "episode-feature-v2", "decision_frequency_seconds": "1"},
            })
            manifest_value.pop("manifest_sha256")
            manifest_value["manifest_sha256"] = hashlib.sha256(_canonical(manifest_value).encode("utf-8")).hexdigest()
            action_manifest.write_text(_canonical(manifest_value), encoding="utf-8")
            output, manifest = root / "labels.ndjson", root / "labels.manifest.json"
            build_label_bundle(actions_path=actions, action_manifest_path=action_manifest, feature_path=features, feature_manifest_path=feature_manifest, output_path=output, manifest_path=manifest, labels_id="labels.v2")
            label = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("STRUCTURE_EXIT", label["outcome"])
            self.assertNotIn("execution_outcome", label)

    def test_v2_labels_reject_action_not_bound_to_exact_decision_feature(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features, feature_manifest = self._features_and_manifest(root)
            action = {
                "action_schema_version": "research-action-v2", "decision_id": "d-v2", "episode_id": "episode-1", "decision_at": "2026-01-01T00:00:00Z",
                "market_path_entry_at": "2026-01-01T00:00:00Z", "feature_event_id": "e1/not-the-decision", "market_path_entry_assumption": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "execution_evidence": False,
                "side": "BUY", "stage": "ENTER_PROBE", "entry_price": "100", "take_profit": "102", "stop_loss": "98", "horizon_seconds": 60,
                "features": {"x": 1}, "evidence_id": "e1",
                "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"},
            }
            actions = root / "actions.ndjson"
            actions.write_text(json.dumps(action) + "\n", encoding="utf-8")
            action_manifest = self._action_manifest(root, actions, feature_manifest)
            manifest_value = json.loads(action_manifest.read_text(encoding="utf-8"))
            manifest_value.update({
                "action_schema_version": "research-action-v2", "research_scope": "PROBE_ONLY", "execution_evidence": False,
                "market_path_entry_assumption": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY",
                "episode_binding": {"policy_id": "episode.v1", "sha256": "b" * 64, "feature_version": "features.v1", "derived_semantics_version": "episode-feature-v2", "decision_frequency_seconds": "1"},
            })
            manifest_value.pop("manifest_sha256")
            manifest_value["manifest_sha256"] = hashlib.sha256(_canonical(manifest_value).encode("utf-8")).hexdigest()
            action_manifest.write_text(_canonical(manifest_value), encoding="utf-8")
            with self.assertRaises(LabelBundleError):
                build_label_bundle(
                    actions_path=actions, action_manifest_path=action_manifest, feature_path=features, feature_manifest_path=feature_manifest,
                    output_path=root / "labels.ndjson", manifest_path=root / "labels.manifest.json", labels_id="labels.v2",
                )
