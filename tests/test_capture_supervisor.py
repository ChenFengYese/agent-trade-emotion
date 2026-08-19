import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from trade_system.capture_plan import ForwardCapturePlan
from trade_system.capture_supervisor import decide_capture_slot


class CaptureSupervisorTests(unittest.TestCase):
    def _plan(self, root: Path, *, budget=None) -> ForwardCapturePlan:
        raw = {
            "plan_id": "supervisor-plan.v1",
            "status": "FROZEN_FORWARD_CAPTURE_PLAN",
            "frozen_at": "2026-01-01T00:00:00Z",
            "instrument": "BTCUSDT",
            "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
            "slots": [
                {
                    "slot_id": "slot-1",
                    "start": "2026-01-02T00:00:00Z",
                    "end": "2026-01-02T00:10:00Z",
                    "min_duration_seconds": 300,
                    "coverage_intent": ["FORWARD_ONLY"],
                },
                {
                    "slot_id": "slot-2",
                    "start": "2026-01-02T01:00:00Z",
                    "end": "2026-01-02T01:10:00Z",
                    "min_duration_seconds": 300,
                    "coverage_intent": ["FORWARD_ONLY"],
                },
            ],
        }
        if budget is not None:
            raw["resource_budget"] = budget
        path = root / "plan.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return ForwardCapturePlan.load(path)

    def test_selects_only_due_slot_and_never_creates_data_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "evidence"
            plan = self._plan(root)
            decision = decide_capture_slot(
                plan, data_root=data_root,
                now=datetime(2026, 1, 2, 0, 2, tzinfo=timezone.utc),
            )
            self.assertEqual("RUN_SLOT", decision.action)
            self.assertEqual("slot-1", decision.slot_id)
            self.assertFalse(data_root.exists())

    def test_late_start_is_missed_but_future_slot_remains_waiting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root)
            decision = decide_capture_slot(
                plan, data_root=root / "evidence",
                now=datetime(2026, 1, 2, 0, 6, tzinfo=timezone.utc),
            )
            self.assertEqual("WAIT", decision.action)
            self.assertEqual(1, decision.missed_slots)
            self.assertEqual(1, decision.pending_slots)
            self.assertIn("MISSED_SLOTS_PRESENT", decision.reason_codes)

    def test_existing_slot_is_reserved_and_not_retried(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root)
            target = root / "evidence" / plan.plan_id / "slot-1"
            target.mkdir(parents=True)
            decision = decide_capture_slot(
                plan, data_root=root / "evidence",
                now=datetime(2026, 1, 2, 0, 2, tzinfo=timezone.utc),
            )
            self.assertEqual("WAIT", decision.action)
            self.assertEqual(1, decision.reserved_slots)

    def test_frozen_disk_guard_blocks_due_slot_without_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "evidence"
            plan = self._plan(root, budget={"min_free_bytes": 100, "max_plan_bytes": 1000})
            fake_usage = shutil._ntuple_diskusage(total=1000, used=950, free=50)
            with patch("trade_system.capture_supervisor.shutil.disk_usage", return_value=fake_usage):
                decision = decide_capture_slot(
                    plan, data_root=data_root,
                    now=datetime(2026, 1, 2, 0, 2, tzinfo=timezone.utc),
                )
            self.assertEqual("RESOURCE_BLOCKED", decision.action)
            self.assertIn("FREE_BYTES_BELOW_FROZEN_MINIMUM", decision.reason_codes)
            self.assertFalse(data_root.exists())
