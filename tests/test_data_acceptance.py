import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trade_system.capture_plan import ForwardCapturePlan
from trade_system.data_acceptance import DataAcceptanceError, assert_equal_or_stricter_than_g1, load_verified_data_acceptance_report, write_data_acceptance_report
from trade_system.event_store import EventStore
from trade_system.g1_acceptance import G1AcceptancePolicy


class DataAcceptanceTests(unittest.TestCase):
    def _policy(self, path, *, plan_id, plan_sha="b" * 64, max_gap=5):
        raw = {
            "policy_id": path.stem, "status": "FROZEN_G1_DATA_ACCEPTANCE", "instrument": "BTCUSDT",
            "required_streams": ["depth", "exchangeInfo"], "required_configured_streams": ["btcusdt@forceOrder"],
            "required_source_registry_id": "registry", "required_source_registry_sha256": "a" * 64,
            "required_capture_plan_id": plan_id, "required_capture_plan_sha256": plan_sha,
            "min_total_observed_seconds": 10, "min_qualified_collections": 1, "min_distinct_utc_days": 1,
            "min_distinct_utc_hour_buckets": 1, "min_exchange_info_observations": 1, "max_exchange_info_gap_seconds": max_gap,
            "min_stream_observations": {"depth": 2}, "max_stream_gap_seconds": {"depth": max_gap},
            "require_exchange_info_trading": True, "max_parse_errors": 0, "max_book_gaps": 0,
            "require_actual_only": True, "require_sealed_raw_segments": True, "allow_reconnects": False,
        }
        path.write_text(json.dumps(raw), encoding="utf-8")
        return G1AcceptancePolicy.load(path)

    def _plan(self, path):
        raw = {"plan_id": "role-plan", "status": "FROZEN_FORWARD_CAPTURE_PLAN", "frozen_at": "2026-01-01T00:00:00Z", "instrument": "BTCUSDT", "source_registry": {"registry_id": "registry", "sha256": "a" * 64}, "slots": [{"slot_id": "slot-1", "start": "2026-01-01T01:00:00Z", "end": "2026-01-01T02:00:00Z", "min_duration_seconds": 60, "coverage_intent": ["role"]}]}
        path.write_text(json.dumps(raw), encoding="utf-8")
        return ForwardCapturePlan.load(path)

    def test_policy_equivalence_is_directional_and_plan_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = self._policy(root / "baseline.json", plan_id="g1-plan", max_gap=5)
            stronger = self._policy(root / "stronger.json", plan_id="role-plan", max_gap=4)
            assert_equal_or_stricter_than_g1(stronger, baseline)
            weaker = self._policy(root / "weaker.json", plan_id="role-plan", max_gap=6)
            with self.assertRaises(DataAcceptanceError):
                assert_equal_or_stricter_than_g1(weaker, baseline)

    def test_role_pass_report_is_write_once_and_plan_bound(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root / "plan.json")
            policy = self._policy(root / "policy.json", plan_id=plan.plan_id, plan_sha=plan.digest)
            validation = {"passed": True, "status": "PASS", "policy_id": policy.policy_id, "policy_sha256": policy.digest, "collections": [{"qualified": True, "data_dir": str(root / "store"), "collection_id": "c1", "collection_audit_digest": "c" * 64, "collection_replay_digest": "d" * 64, "capture_plan": {"plan_id": plan.plan_id, "plan_sha256": plan.digest, "slot_id": "slot-1"}}]}
            output = root / "acceptance.json"
            EventStore(root / "store")
            with patch("trade_system.data_acceptance.validate_g1_stores", return_value=validation) as validate:
                written = write_data_acceptance_report(output, report_id="dev.v1", role="DEVELOPMENT", policy=policy, plan=plan, data_dirs=(root / "store",))
                validate.assert_called_once()
            verified = load_verified_data_acceptance_report(output, role="DEVELOPMENT", policy=policy, plan=plan)
            self.assertEqual(written["report_sha256"], verified["report_sha256"])
            with self.assertRaises(DataAcceptanceError):
                with patch("trade_system.data_acceptance.validate_g1_stores", return_value=validation):
                    write_data_acceptance_report(output, report_id="dev.v1", role="DEVELOPMENT", policy=policy, plan=plan, data_dirs=(root / "store",))

    def test_forged_pass_is_ignored_when_revalidation_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root / "plan.json")
            policy = self._policy(root / "policy.json", plan_id=plan.plan_id, plan_sha=plan.digest)
            forged = {"passed": True, "status": "PASS", "policy_id": policy.policy_id, "policy_sha256": policy.digest, "collections": []}
            recomputed = {"passed": False, "status": "WAIT_DATA", "policy_id": policy.policy_id, "policy_sha256": policy.digest, "collections": []}
            # A hand-written PASS has no call path into the writer. Only the
            # fresh store validation decides whether an immutable PASS exists.
            EventStore(root / "store")
            with patch("trade_system.data_acceptance.validate_g1_stores", return_value=recomputed):
                with self.assertRaisesRegex(DataAcceptanceError, "revalidated"):
                    write_data_acceptance_report(root / "forged.json", report_id="forged", role="DEVELOPMENT", policy=policy, plan=plan, data_dirs=(root / "store",))
            self.assertTrue(forged["passed"])
