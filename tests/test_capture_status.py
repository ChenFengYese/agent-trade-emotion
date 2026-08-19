import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trade_system.capture_plan import ForwardCapturePlan
from trade_system.capture_status import inspect_forward_capture_plan
from trade_system.event_store import EventStore
from trade_system.types import AvailabilityKind, AvailabilityRecord


class CaptureStatusTests(unittest.TestCase):
    def _plan(self, root: Path, *, slot_id="slot-1", start="2026-01-02T00:00:00Z", end="2026-01-02T00:30:00Z"):
        path = root / "plan.json"
        path.write_text(json.dumps({
            "plan_id": "status-plan.v1", "status": "FROZEN_FORWARD_CAPTURE_PLAN",
            "frozen_at": "2026-01-01T00:00:00Z", "instrument": "BTCUSDT",
            "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
            "slots": [{
                "slot_id": slot_id, "start": start, "end": end, "min_duration_seconds": 60,
                "coverage_intent": ["UTC_SCHEDULED", "FORWARD_ONLY"],
            }],
        }), encoding="utf-8")
        return ForwardCapturePlan.load(path)

    def _write_terminal(self, plan, root: Path, *, result="QUALIFIED_SMOKE", tamper_binding=False):
        slot = plan.slots[0]
        target = root / plan.plan_id / slot.slot_id
        store = EventStore(target)
        connection_id = "%s-%s" % (plan.plan_id, slot.slot_id)
        received = datetime(2026, 1, 2, 0, 10, tzinfo=timezone.utc)
        raw = store.append_raw(
            source="TEST", venue="BINANCE_USDM", instrument="BTCUSDT", stream="test",
            connection_id=connection_id + "-market", ingest_seq=1, payload={"ok": True}, receive_time=received,
        )
        store.append_availability(raw, AvailabilityRecord(
            event_id=raw.event_id, schema_version="test", derived_at=received, available_at=received,
            availability_kind=AvailabilityKind.ACTUAL, normalized={"kind": "test"},
        ))
        audit_valid, audit_issues, audit_digest = store.audit()
        binding = plan.bind_slot(
            slot_id=slot.slot_id, now=datetime(2026, 1, 2, 0, 1, tzinfo=timezone.utc),
            requested_duration_seconds=60, instrument="BTCUSDT",
            registry_id=plan.source_registry_id, registry_sha256=plan.source_registry_sha256,
        )
        if tamper_binding:
            binding["plan_sha256"] = "b" * 64
        store.write_collection_manifest(connection_id, {
            "collection_result": result, "instrument": "BTCUSDT", "capture_plan": binding,
            "source_registry": {"registry_id": plan.source_registry_id, "sha256": plan.source_registry_sha256},
            "raw_captured": 1, "availability_written": 1, "parse_errors": 0, "book_gaps": 0,
            "errors": [] if result == "QUALIFIED_SMOKE" else ["test failure"], "reconnects": {},
            "audit_valid": audit_valid, "audit_issues": audit_issues, "audit_digest": audit_digest,
        })
        store.seal_raw_segment("2026-01-02")
        return target

    def test_status_is_read_only_and_distinguishes_ready_from_missed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root, slot_id="upcoming", start="2026-01-02T01:00:00Z", end="2026-01-02T01:30:00Z")
            data_root = root / "missing-data-root"
            report = inspect_forward_capture_plan(plan, data_root=data_root, now=datetime(2026, 1, 2, 0, 30, tzinfo=timezone.utc))
            self.assertEqual("PENDING", report["slots"][0]["status"])
            self.assertFalse(data_root.exists())
            report = inspect_forward_capture_plan(plan, data_root=data_root, now=datetime(2026, 1, 2, 2, tzinfo=timezone.utc))
            self.assertEqual("MISSED", report["slots"][0]["status"])
            self.assertTrue(report["requires_operator_action"])

    def test_status_marks_window_missed_when_full_minimum_no_longer_fits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root, start="2026-01-02T00:00:00Z", end="2026-01-02T00:30:00Z")
            report = inspect_forward_capture_plan(
                plan, data_root=root / "missing",
                now=datetime(2026, 1, 2, 0, 29, 1, tzinfo=timezone.utc),
            )
            self.assertEqual("MISSED", report["slots"][0]["status"])
            self.assertEqual("INSUFFICIENT_REMAINING_SLOT_TIME", report["slots"][0]["reason_code"])

    def test_status_recognizes_only_matching_qualified_and_sealed_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root)
            self._write_terminal(plan, root)
            report = inspect_forward_capture_plan(plan, data_root=root, now=datetime(2026, 1, 2, 1, tzinfo=timezone.utc))
            self.assertTrue(report["all_slots_sealed"])
            self.assertEqual("QUALIFIED_SMOKE_SEALED", report["slots"][0]["status"])

    def test_status_flags_unqualified_or_plan_mismatched_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root)
            self._write_terminal(plan, root, result="UNQUALIFIED")
            report = inspect_forward_capture_plan(plan, data_root=root, now=datetime(2026, 1, 2, 1, tzinfo=timezone.utc))
            self.assertEqual("UNQUALIFIED", report["slots"][0]["status"])
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self._plan(root)
            self._write_terminal(plan, root, tamper_binding=True)
            report = inspect_forward_capture_plan(plan, data_root=root, now=datetime(2026, 1, 2, 1, tzinfo=timezone.utc))
            self.assertEqual("PLAN_BINDING_MISMATCH", report["slots"][0]["status"])
