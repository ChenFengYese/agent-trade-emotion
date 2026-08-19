import json
import tempfile
import unittest
from pathlib import Path

from trade_system.research_report import ResearchReportError, sha256_file, write_research_report


class ResearchReportTests(unittest.TestCase):
    def test_write_once_report_has_content_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "labels.ndjson"
            input_path.write_text('{"episode_id":"e"}\n', encoding="utf-8")
            report_path = root / "research.json"
            written = write_research_report(report_path, {
                "research_status": "INCONCLUSIVE/WAIT_DATA",
                "evidence_binding": {"input_sha256": sha256_file(input_path)},
            })
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(written["report_sha256"], persisted["report_sha256"])
            with self.assertRaises(ResearchReportError):
                write_research_report(report_path, {"research_status": "INCONCLUSIVE/WAIT_DATA"})
