import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trade_system.paper_audit import (
    PaperAuditError,
    PaperAuditTrail,
    audit_paper_trail,
    verify_paper_recovery_report,
    write_paper_recovery_report,
)


class PaperAuditTrailTests(unittest.TestCase):
    def test_finalized_trail_is_ordered_and_verifiable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "paper.ndjson"
            trail = PaperAuditTrail(path, run_id="paper-run-1", context={"scope": "TEST"})
            now = datetime(2026, 7, 22, tzinfo=timezone.utc)
            trail.append("INTENT_RECEIVED", {"intent_id": "a"}, observed_at=now)
            trail.finalize({"position_quantity": "0"}, observed_at=now)
            self.assertEqual(3, trail.summary()["event_count"])
            report = audit_paper_trail(path)
            self.assertTrue(report["valid"])
            self.assertEqual("paper-run-1", report["run_id"])
            with self.assertRaises(PaperAuditError):
                trail.append("AFTER_FINAL", {}, observed_at=now)

    def test_tampered_or_unfinalized_trail_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "paper.ndjson"
            trail = PaperAuditTrail(path, run_id="paper-run-2", context={"scope": "TEST"})
            trail.append("INTENT_RECEIVED", {"intent_id": "a"})
            self.assertIn("paper audit trail is not finalized", audit_paper_trail(path)["issues"])
            trail.finalize({"position_quantity": "0"})
            lines = path.read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[1])
            event["payload"]["intent_id"] = "tampered"
            lines[1] = json.dumps(event, sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report = audit_paper_trail(path)
            self.assertFalse(report["valid"])
            self.assertTrue(any("event digest mismatch" in issue for issue in report["issues"]))

    def test_unfinalized_trail_writes_fail_closed_recovery_handoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path, recovery_path = root / "paper.ndjson", root / "recovery.json"
            trail = PaperAuditTrail(audit_path, run_id="paper-run-3", context={"scope": "TEST"})
            trail.append("INTENT_ACKNOWLEDGED", {
                "state": {
                    "position_quantity": "1",
                    "orders": {
                        "intent-1": {
                            "client_order_id": "paper-client-1",
                            "status": "ACKNOWLEDGED",
                            "filled_quantity": "0",
                        },
                    },
                },
            })
            with self.assertRaises(PaperAuditError):
                write_paper_recovery_report(audit_path, recovery_path, confirm_process_stopped=False)
            report = write_paper_recovery_report(audit_path, recovery_path, confirm_process_stopped=True)
            self.assertEqual("HALT_AND_RECONCILE_REQUIRED", report["recovery_status"])
            self.assertEqual(["paper-client-1"], report["expected_open_client_order_ids"])
            self.assertTrue(verify_paper_recovery_report(recovery_path, audit_path)["valid"])

    def test_finalized_trail_cannot_be_recovered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "paper.ndjson"
            trail = PaperAuditTrail(audit_path, run_id="paper-run-4", context={"scope": "TEST"})
            trail.finalize({"position_quantity": "0"})
            with self.assertRaises(PaperAuditError):
                write_paper_recovery_report(audit_path, root / "recovery.json", confirm_process_stopped=True)
