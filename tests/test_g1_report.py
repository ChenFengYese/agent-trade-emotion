import json
import tempfile
import unittest
from pathlib import Path

from trade_system.g1_report import G1ReportError, load_passed_g1_report, write_g1_report


class G1ReportTests(unittest.TestCase):
    def test_passed_report_is_write_once_and_digest_bound(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "g1.json"
            persisted = write_g1_report(path, {
                "passed": True, "status": "PASS", "policy_id": "g1.v1", "audit_digest": "a" * 64,
            })
            loaded = load_passed_g1_report(path, policy_id="g1.v1", expected_sha256=persisted["report_sha256"])
            self.assertEqual("PASS", loaded["status"])
            with self.assertRaises(G1ReportError):
                write_g1_report(path, {"passed": True, "status": "PASS", "policy_id": "g1.v1"})

    def test_tampered_or_non_pass_report_cannot_bind_research(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "g1.json"
            persisted = write_g1_report(path, {"passed": False, "status": "FAILED", "policy_id": "g1.v1"})
            with self.assertRaises(G1ReportError):
                load_passed_g1_report(path, policy_id="g1.v1", expected_sha256=persisted["report_sha256"])
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["status"] = "PASS"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(G1ReportError):
                load_passed_g1_report(path, policy_id="g1.v1", expected_sha256=persisted["report_sha256"])
