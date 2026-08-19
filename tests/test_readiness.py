import tempfile
import unittest
from pathlib import Path

from trade_system.readiness import build_research_readiness


ROOT = Path(__file__).resolve().parents[1]


class ResearchReadinessTests(unittest.TestCase):
    def test_draft_artifacts_and_no_evidence_are_explicit_blockers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = build_research_readiness(
                (Path(temp_dir),),
                g1_policy_path=ROOT / "config" / "g1_data_acceptance.template.json",
                research_protocol_path=ROOT / "config" / "research_protocol.paper.v1.json",
            )
        self.assertEqual("POLICY_PREREGISTRATION_REQUIRED", report["readiness"])
        self.assertEqual(0, report["forward_evidence"]["sealed_current_collections"])
        self.assertEqual(
            ["NO_SEALED_CURRENT_FORWARD_COLLECTION", "G1_POLICY_NOT_FROZEN", "RESEARCH_PROTOCOL_NOT_FROZEN"],
            report["blockers"],
        )

    def test_invalid_artifact_paths_are_never_reported_as_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = build_research_readiness(
                (root,), g1_policy_path=root / "missing-g1.json", research_protocol_path=root / "missing-protocol.json",
            )
        self.assertEqual("POLICY_PREREGISTRATION_REQUIRED", report["readiness"])
        self.assertIn("INVALID_G1_POLICY", report["blockers"])
        self.assertIn("INVALID_RESEARCH_PROTOCOL", report["blockers"])
