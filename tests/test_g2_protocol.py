import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from trade_system.g2_protocol import G2ProtocolError, _policy, _sha, _verify_context_evidence, evaluate_protocol_g2
from trade_system.protocol import ResearchProtocol


class G2ProtocolTests(unittest.TestCase):
    def test_context_artifact_manifest_and_receipt_are_rehashed_and_exact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir); artifact = root / "context.ndjson"; artifact.write_text("{}\n", encoding="utf-8")
            receipt_path = root / "receipt.json"; receipt_path.write_text("{}", encoding="utf-8")
            binding = {"policy_id": "ctx", "policy_sha256": "a" * 64, "artifact": str(artifact), "artifact_sha256": __import__("hashlib").sha256(artifact.read_bytes()).hexdigest(), "context_manifest": str(root / "context.json"), "role_window": {"id": "w", "sha256": "b" * 64}}
            feature = {"feature_artifact_sha256": "c" * 64, "collections": [{"evidence_id": "e", "collection_id": "col", "data_dir": str(root / "store"), "archive_receipt": {"archive_id": "ar", "receipt_sha256": "d" * 64, "receipt_path": str(receipt_path)}}]}
            context = {"record_type": "feature_context_artifact_manifest", "context_artifact_sha256": binding["artifact_sha256"], "feature_artifact_sha256": "c" * 64, "context_policy": {"id": "ctx", "sha256": "a" * 64}, "role_window": binding["role_window"], "collections": [{"evidence_id": "e", "collection_id": "col", "archive_receipt": feature["collections"][0]["archive_receipt"]}]}; context["manifest_sha256"] = _sha(context)
            Path(binding["context_manifest"]).write_text(json.dumps(context), encoding="utf-8"); binding["context_manifest_sha256"] = context["manifest_sha256"]
            feature["context_binding"] = binding
            required = {"policy": {"id": "ctx", "sha256": "a" * 64}, "artifact": {"sha256": binding["artifact_sha256"], "manifest_sha256": context["manifest_sha256"]}, "role_window": binding["role_window"]}
            receipt = {"archive_id": "ar", "receipt_sha256": "d" * 64, "collection_id": "col", "source_evidence_root": str(root / "store")}
            with patch("trade_system.g2_protocol.load_verified_evidence_archive_receipt", return_value=receipt), patch("trade_system.g2_protocol.verify_evidence_archive", return_value={"valid": True}):
                _verify_context_evidence(feature_manifest=feature, required=required)
            artifact.write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(G2ProtocolError):
                _verify_context_evidence(feature_manifest=feature, required=required)
    def test_draft_machine_config_maps_real_fields_and_waits_for_required_response_features(self):
        protocol = ResearchProtocol.load(Path(__file__).resolve().parents[1] / "config" / "research_protocol.v2.draft.json")
        policy = _policy(protocol, as_of="2026-01-01T00:00:00Z")
        h3 = policy.feature_groups["d_l_state_interaction"]
        self.assertIn(("D_directional_pressure", "L_log_oi_change", "STATE:THIN_BOOK"), [term.sources for term in h3])
        self.assertEqual(("F_forced_pressure", "L_log_oi_change", "R_directional_improvement"), policy.feature_groups["forced_oi_r_improvement"][-1].sources)
        self.assertTrue(policy.separate_models)
    def test_draft_protocol_cannot_run_formal_g2_or_write_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protocol = Path(__file__).resolve().parents[1] / "config" / "research_protocol.v2.draft.json"
            with self.assertRaises(G2ProtocolError):
                evaluate_protocol_g2(protocol_path=protocol, evidence_admission_path=root / "admission.json", state_labels_path=root / "state.ndjson", state_manifest_path=root / "state.json", classifier_path=root / "classifier.json", feature_path=root / "features.ndjson", feature_manifest_path=root / "features.json", output_path=root / "g2.json", as_of="2026-01-01T00:00:00Z")
            self.assertFalse((root / "g2.json").exists())

    def test_report_binds_exact_development_admission_and_state_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            labels = root / "state.ndjson"; labels.write_text(json.dumps({"episode_id": "e"}) + "\n", encoding="utf-8")
            context = {"policy": {"id": "ctx", "sha256": "c" * 64}, "artifact": {"sha256": "d" * 64, "manifest_sha256": "e" * 64}, "role_window": {"id": "window", "sha256": "f" * 64}, "archive_receipts": {"schema_version": "evidence-archive-receipt.v1", "require_verified_per_collection": True}}
            protocol = SimpleNamespace(protocol_id="p", digest="a" * 64, raw={"schema_version": "research-protocol.v2", "state_coverage_policy": {"classifier_id": "c", "classifier_digest": "b" * 64}, "context_evidence": context}, assert_frozen_for_research=lambda: None)
            classifier = SimpleNamespace(classifier_id="c", digest="b" * 64)
            state_manifest = {"manifest_sha256": "d" * 64}
            admission = {"manifest_sha256": "e" * 64}
            result = {"overall_status": "INCONCLUSIVE/WAIT_DATA", "gates": {}, "coverage": {}}
            feature = root / "features.ndjson"; feature.write_text("{}\n", encoding="utf-8")
            feature_manifest = {"manifest_sha256": "g" * 64, "context_binding": {"policy_id": "ctx", "policy_sha256": "c" * 64, "artifact_sha256": "d" * 64, "context_manifest_sha256": "e" * 64, "role_window": {"id": "window", "sha256": "f" * 64}}, "collections": [{"archive_receipt": {"archive_id": "x"}}]}
            admission["feature_bundle_manifest_sha256"] = "g" * 64
            with patch("trade_system.g2_protocol.ResearchProtocol.load", return_value=protocol), patch("trade_system.g2_protocol.StateClassifier.load", return_value=classifier), patch("trade_system.g2_protocol.load_verified_state_label_bundle_manifest", return_value=state_manifest), patch("trade_system.g2_protocol.load_verified_research_evidence_admission", return_value=admission), patch("trade_system.g2_protocol.load_verified_feature_bundle_manifest", return_value=feature_manifest), patch("trade_system.g2_protocol._verify_context_evidence", return_value={"context_binding": feature_manifest["context_binding"], "archive_receipts": []}), patch("trade_system.g2_protocol._policy"), patch("trade_system.g2_protocol.evaluate_g2", return_value=result) as evaluate:
                report = evaluate_protocol_g2(protocol_path=root / "protocol.json", evidence_admission_path=root / "admission.json", state_labels_path=labels, state_manifest_path=root / "state.json", classifier_path=root / "classifier.json", feature_path=feature, feature_manifest_path=root / "features.json", output_path=root / "g2.json", as_of="2026-01-01T00:00:00Z")
            self.assertEqual("e" * 64, report["development_evidence_admission_sha256"])
            self.assertEqual("d" * 64, report["state_label_manifest_sha256"])
            self.assertEqual("a" * 64, report["protocol"]["sha256"])
            self.assertEqual("ACTUAL", next(evaluate.call_args.args[0])["availability_kind"])
            self.assertTrue((root / "g2.json").exists())
