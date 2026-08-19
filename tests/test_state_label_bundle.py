import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trade_system.state_classifier import StateClassifier
from trade_system.state_label_bundle import StateLabelBundleError, build_state_label_bundle, load_verified_state_label_bundle_manifest


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class StateLabelBundleTests(unittest.TestCase):
    def _labels_and_manifest(self, root: Path):
        labels = root / "labels.ndjson"
        labels.write_text(json.dumps({
            "decision_id": "d", "episode_id": "e", "decision_at": "2026-01-01T00:00:00Z",
            "label_end_at": "2026-01-01T00:01:00Z", "features": {"pressure": 1}, "outcome": "TP", "censored": False,
        }) + "\n", encoding="utf-8")
        manifest = {
            "record_type": "label_bundle_manifest", "labels_id": "labels.v1", "labels_artifact": str(labels),
            "labels_artifact_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(), "labels_written": 1,
            "actions_artifact": "actions", "actions_artifact_sha256": "a" * 64,
            "feature_bundle_manifest_sha256": "b" * 64, "feature_artifact_sha256": "c" * 64,
            "g1_policy_id": "g1.v1", "g1_report_sha256": "d" * 64, "action_counts_by_evidence": {"evidence": 1},
        }
        manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
        path = root / "labels.manifest.json"
        path.write_text(_canonical(manifest), encoding="utf-8")
        return labels, path

    def _classifier(self, root: Path):
        path = root / "classifier.json"
        path.write_text(json.dumps({
            "classifier_id": "regime.v1", "status": "FROZEN_STATE_CLASSIFIER", "fallback_state_id": "STRESSED",
            "rules": [{"state_id": "CALM", "all": [{"feature": "pressure", "min": 0}]}],
        }), encoding="utf-8")
        return path

    def test_state_assignment_preserves_label_manifest_and_classifier_binding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            labels, label_manifest = self._labels_and_manifest(root)
            classifier_path = self._classifier(root)
            output, manifest = root / "state-labels.ndjson", root / "state-labels.manifest.json"
            report = build_state_label_bundle(
                labels_path=labels, label_manifest_path=label_manifest, classifier_path=classifier_path,
                output_path=output, manifest_path=manifest, state_labels_id="state-labels.v1",
            )
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("CALM", row["state_id"])
            verified = load_verified_state_label_bundle_manifest(manifest, labels_path=output, classifier=StateClassifier.load(classifier_path))
            self.assertEqual(report["manifest_sha256"], verified["manifest_sha256"])
            self.assertEqual("d" * 64, verified["g1_report_sha256"])

    def test_state_manifest_rejects_tampered_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            labels, label_manifest = self._labels_and_manifest(root)
            classifier_path = self._classifier(root)
            output, manifest = root / "state-labels.ndjson", root / "state-labels.manifest.json"
            build_state_label_bundle(
                labels_path=labels, label_manifest_path=label_manifest, classifier_path=classifier_path,
                output_path=output, manifest_path=manifest, state_labels_id="state-labels.v1",
            )
            with output.open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            with self.assertRaises(StateLabelBundleError):
                load_verified_state_label_bundle_manifest(manifest, labels_path=output, classifier=StateClassifier.load(classifier_path))
