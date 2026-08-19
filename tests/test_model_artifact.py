import unittest
from datetime import timedelta

from trade_system.model_artifact import MissingPolicy, ModelArtifact, SourceRequirement
from trade_system.types import utc_now


class ModelArtifactTests(unittest.TestCase):
    def test_stale_required_source_abstains(self):
        artifact = ModelArtifact("v1", (SourceRequirement("DATA-001", timedelta(seconds=1), MissingPolicy.ABSTAIN),))
        now = utc_now()
        decision = artifact.check_inputs(decision_at=now, source_available_at={"DATA-001": now - timedelta(seconds=2)})
        self.assertFalse(decision.allowed)
        self.assertEqual("SOURCE_STALE_DATA-001", decision.reason)

    def test_optional_source_disables_feature_not_silently_fills(self):
        artifact = ModelArtifact("v1", (SourceRequirement("DATA-005", timedelta(seconds=1), MissingPolicy.DISABLE_FEATURE),))
        decision = artifact.check_inputs(decision_at=utc_now(), source_available_at={})
        self.assertTrue(decision.allowed)
        self.assertEqual(("DATA-005",), decision.disabled_sources)

    def test_configured_artifact_loads(self):
        artifact = ModelArtifact.load("config/model_artifact.baseline.v1.json")
        self.assertEqual("baseline-five-factor-v1", artifact.model_id)
