import json
import tempfile
import unittest
from pathlib import Path

from trade_system.state_classifier import StateClassifier, StateClassifierError


class StateClassifierTests(unittest.TestCase):
    def _write_classifier(self, path: Path):
        path.write_text(json.dumps({
            "classifier_id": "impact-regime.v1",
            "status": "FROZEN_STATE_CLASSIFIER",
            "fallback_state_id": "STRESSED",
            "rules": [{
                "state_id": "CALM",
                "all": [{"feature": "price_impact", "max": 0.001, "absolute": True}],
            }],
        }), encoding="utf-8")

    def test_frozen_classifier_is_digest_bound_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "classifier.json"
            self._write_classifier(path)
            classifier = StateClassifier.load(path)
            self.assertEqual("CALM", classifier.classify({"price_impact": -0.0005}))
            self.assertEqual("STRESSED", classifier.classify({"price_impact": 0.01}))
            self.assertEqual("STRESSED", classifier.classify({}))
            self.assertEqual(("CALM", "STRESSED"), classifier.state_ids)
            self.assertEqual(64, len(classifier.digest))

    def test_classifier_rejects_non_frozen_or_ambiguous_state_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "classifier.json"
            self._write_classifier(path)
            raw = json.loads(path.read_text())
            raw["status"] = "DRAFT_TEMPLATE"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(StateClassifierError):
                StateClassifier.load(path)
