import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from trade_system.capture_plan import ForwardCapturePlan
from trade_system.feature_context import FeatureContextPolicy
from trade_system.role_capture_window import RoleCaptureWindow, RoleCaptureWindowError
from trade_system.types import AvailabilityKind


class RoleCaptureWindowTests(unittest.TestCase):
    def test_contract_requires_single_collection_warmup_decision_and_label_tail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context_path = root / "context.json"
            context_raw = {
                "context_policy_id": "context.v1", "status": "FROZEN_FEATURE_CONTEXT_POLICY",
                "frozen_at": "2026-07-22T00:00:00Z", "instrument": "BTCUSDT", "feature_version": "features.v2",
                "allowed_availability": "ACTUAL_ONLY", "sampling": {"decision_frequency_seconds": 1, "warmup_seconds": 14400, "max_gap_seconds": 1},
                "lookbacks_seconds": [60, 900, 3600, 14400], "trend": {"lookback_seconds": 3600, "volatility_floor": "0.0000001"},
                "trend_continuation_veto": {"min_abs_trend_score": "1", "min_abs_directional_pressure": "1", "min_abs_price_impact": "0.1", "max_directional_resilience": "0"},
            }
            context_path.write_text(json.dumps(context_raw), encoding="utf-8")
            context = FeatureContextPolicy.load(context_path)
            plan_path = root / "plan.json"
            plan_raw = {
                "status": "FROZEN_FORWARD_CAPTURE_PLAN", "plan_id": "plan.v1", "frozen_at": "2026-07-22T00:00:00Z", "instrument": "BTCUSDT",
                "source_registry": {"registry_id": "registry.v1", "sha256": "a" * 64}, "collector_software_sha256": "b" * 64,
                "slots": [{"slot_id": "slot-1", "start": "2026-07-22T01:00:00Z", "end": "2026-07-22T07:00:00Z", "min_duration_seconds": 14760, "coverage_intent": ["future"]}],
            }
            plan_path.write_text(json.dumps(plan_raw), encoding="utf-8")
            plan = ForwardCapturePlan.load(plan_path)
            window_path = root / "window.json"
            window_path.write_text(json.dumps({
                "window_id": "dev.window.v1", "status": "FROZEN_ROLE_CAPTURE_WINDOW", "frozen_at": "2026-07-22T00:00:00Z", "role": "DEVELOPMENT",
                "capture_plan": {"id": plan.plan_id, "sha256": plan.digest}, "context_policy": {"id": context.context_policy_id, "sha256": context.digest},
                "warmup_seconds": 14400, "minimum_eligible_decision_seconds": 60, "label_tail_seconds": 300,
            }), encoding="utf-8")
            window = RoleCaptureWindow.load(window_path)
            window.assert_matches(role="DEVELOPMENT", plan=plan, context_policy=context)
            start = datetime(2026, 7, 22, 1, tzinfo=timezone.utc)
            records = [
                SimpleNamespace(available_at=start, availability_kind=AvailabilityKind.ACTUAL),
                SimpleNamespace(available_at=start + timedelta(seconds=14760), availability_kind=AvailabilityKind.ACTUAL),
            ]
            coverage = window.assert_collection_coverage(records)
            self.assertEqual("2026-07-22T05:00:00+00:00", coverage["eligible_decision_start_at"])
            self.assertEqual("2026-07-22T05:01:00+00:00", coverage["eligible_decision_end_at"])
            with self.assertRaises(RoleCaptureWindowError):
                window.assert_collection_coverage(records[:-1] + [SimpleNamespace(available_at=start + timedelta(seconds=14759), availability_kind=AvailabilityKind.ACTUAL)])

