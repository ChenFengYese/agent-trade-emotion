import json
import tempfile
import unittest
from pathlib import Path

from trade_system.shadow import compare_decision_artifacts, compare_feature_artifacts


class ShadowTests(unittest.TestCase):
    def _write(self, path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_equal_artifacts_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            offline, online = Path(temp_dir) / "offline.ndjson", Path(temp_dir) / "online.ndjson"
            rows = [{"event_id": "a", "feature_version": "v1", "values": {"D": "0.1"}}]
            self._write(offline, rows)
            self._write(online, rows)
            comparison = compare_feature_artifacts(offline, online)
            self.assertTrue(comparison.passed)
            self.assertEqual(1, comparison.matched_rows)

    def test_mismatch_is_evidence_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            offline, online = Path(temp_dir) / "offline.ndjson", Path(temp_dir) / "online.ndjson"
            self._write(offline, [{"event_id": "a", "feature_version": "v1", "values": {"D": "0.1"}}])
            self._write(online, [{"event_id": "a", "feature_version": "v1", "values": {"D": "0.5"}}])
            comparison = compare_feature_artifacts(offline, online)
            self.assertFalse(comparison.passed)
            self.assertEqual(["a:D"], comparison.value_mismatches)

    def test_feature_shadow_requires_matching_point_in_time_episode_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            offline, online = Path(temp_dir) / "offline.ndjson", Path(temp_dir) / "online.ndjson"
            self._write(offline, [{"event_id": "a", "feature_version": "v1", "episode_state": "OBSERVE", "values": {"D": "0.1"}}])
            self._write(online, [{"event_id": "a", "feature_version": "v1", "episode_state": "FAILED", "values": {"D": "0.1"}}])
            comparison = compare_feature_artifacts(offline, online)
            self.assertFalse(comparison.passed)
            self.assertEqual(["a:episode_state"], comparison.context_mismatches)

    @staticmethod
    def _decision(event_id="a", *, reason="TRADE", ev_submit="1.2", model_version="m1"):
        return {
            "event_id": event_id,
            "decision_at": "2026-07-22T00:00:00Z",
            "feature_version": "features-v1",
            "model_version": model_version,
            "policy_version": "policy-v1",
            "risk_profile_digest": "a" * 64,
            "decision": {"trade": True, "reason": reason, "ev_fill": "1.5", "ev_submit": ev_submit},
        }

    def test_equal_decision_artifacts_pass_only_with_same_bindings_and_ev(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            offline, online = Path(temp_dir) / "offline.ndjson", Path(temp_dir) / "online.ndjson"
            row = self._decision()
            self._write(offline, [row])
            self._write(online, [row])
            comparison = compare_decision_artifacts(offline, online)
            self.assertTrue(comparison.passed)
            self.assertEqual(1, comparison.matched_rows)

    def test_decision_shadow_reports_reason_ev_and_version_mismatches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            offline, online = Path(temp_dir) / "offline.ndjson", Path(temp_dir) / "online.ndjson"
            self._write(offline, [self._decision("reason"), self._decision("version", model_version="m1"), self._decision("ev")])
            self._write(online, [self._decision("reason", reason="RISK_GATE_NO_NEW_RISK"), self._decision("version", model_version="m2"), self._decision("ev", ev_submit="1.8")])
            comparison = compare_decision_artifacts(offline, online)
            self.assertFalse(comparison.passed)
            self.assertEqual(["reason:reason"], comparison.decision_mismatches)
            self.assertEqual(["version:model_version"], comparison.version_mismatches)
            self.assertEqual(["ev:ev_submit"], comparison.value_mismatches)
