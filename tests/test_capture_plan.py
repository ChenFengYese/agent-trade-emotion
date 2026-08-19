import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.capture_plan import CapturePlanError, ForwardCapturePlan


class CapturePlanTests(unittest.TestCase):
    def _write(self, path: Path):
        path.write_text(json.dumps({
            "plan_id": "capture-plan.v1",
            "status": "FROZEN_FORWARD_CAPTURE_PLAN",
            "frozen_at": "2026-01-01T00:00:00Z",
            "instrument": "BTCUSDT",
            "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
            "slots": [{
                "slot_id": "utc-00", "start": "2026-01-02T00:00:00Z", "end": "2026-01-02T00:30:00Z",
                "min_duration_seconds": 900, "coverage_intent": ["UTC_HOUR_00", "FORWARD_ONLY"],
            }],
        }), encoding="utf-8")

    def test_plan_binds_only_declared_time_registry_and_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            self._write(path)
            plan = ForwardCapturePlan.load(path)
            binding = plan.bind_slot(
                slot_id="utc-00", now=datetime(2026, 1, 2, 0, 1, tzinfo=timezone.utc),
                requested_duration_seconds=900, instrument="BTCUSDT",
                registry_id="source-registry.v3", registry_sha256="a" * 64,
            )
            self.assertEqual("capture-plan.v1", binding["plan_id"])
            self.assertEqual("utc-00", binding["slot_id"])
            with self.assertRaises(CapturePlanError):
                plan.bind_slot(
                    slot_id="utc-00", now=datetime(2026, 1, 2, 0, 25, tzinfo=timezone.utc),
                    requested_duration_seconds=900, instrument="BTCUSDT",
                    registry_id="source-registry.v3", registry_sha256="a" * 64,
                )
            with self.assertRaises(CapturePlanError):
                plan.bind_slot(
                    slot_id="utc-00", now=datetime(2026, 1, 2, 0, 1, tzinfo=timezone.utc),
                    requested_duration_seconds=900, instrument="BTCUSDT",
                    registry_id="source-registry.v2", registry_sha256="a" * 64,
                )

    def test_plan_rejects_overlapping_slots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            self._write(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["slots"].append({
                "slot_id": "overlap", "start": "2026-01-02T00:20:00Z", "end": "2026-01-02T00:40:00Z",
                "min_duration_seconds": 60, "coverage_intent": ["TEST"],
            })
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(CapturePlanError):
                ForwardCapturePlan.load(path)

    def test_plan_requires_each_slot_to_be_declared_before_its_start(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            self._write(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["frozen_at"] = "2026-01-02T00:01:00Z"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(CapturePlanError):
                ForwardCapturePlan.load(path)

    def test_plan_rejects_path_like_plan_or_slot_identifiers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            self._write(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["plan_id"] = "../not-a-plan"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(CapturePlanError):
                ForwardCapturePlan.load(path)

    def test_plan_can_freeze_exact_collector_software_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            self._write(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["collector_software_sha256"] = "c" * 64
            path.write_text(json.dumps(raw), encoding="utf-8")
            plan = ForwardCapturePlan.load(path)
            kwargs = {
                "slot_id": "utc-00",
                "now": datetime(2026, 1, 2, 0, 1, tzinfo=timezone.utc),
                "requested_duration_seconds": 900,
                "instrument": "BTCUSDT",
                "registry_id": "source-registry.v3",
                "registry_sha256": "a" * 64,
            }
            with self.assertRaises(CapturePlanError):
                plan.bind_slot(**kwargs, collector_software_sha256="d" * 64)
            binding = plan.bind_slot(**kwargs, collector_software_sha256="c" * 64)
            self.assertEqual("c" * 64, binding["collector_software_sha256"])
