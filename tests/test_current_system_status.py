from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from trade_system.current_system_status import (
    CurrentSystemStatus,
    CurrentSystemStatusError,
    validate_current_system_status,
)


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "config/current_system_status.v1.json"


class CurrentSystemStatusTests(unittest.TestCase):
    def _raw(self) -> dict:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))

    def _isolated_workspace(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        workspace = Path(temp.name)
        raw = self._raw()
        paths = [item["path"] for item in raw["evidence_bindings"]]
        paths.extend(("pyproject.toml", "setup.py", "config/current_system_status.v1.json"))
        for relative in paths:
            destination = workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        return temp, workspace

    def test_checked_in_overlay_validates_and_keeps_live_trading_denied(self) -> None:
        status = CurrentSystemStatus.load(STATUS_PATH, workspace_root=ROOT)
        self.assertEqual("CORE_TRADING_THEORY.v2.1", status.summary["core_id"])
        self.assertEqual("ACCEPT_P0_1", status.summary["p0_1_state"])
        self.assertEqual("FAILURE", status.summary["har1r4_outcome"])
        self.assertEqual(
            "AUTHORIZE_HAR1R5_STATIC_GATE_ONLY_NO_NETWORK",
            status.summary["har1r5_state"],
        )
        self.assertEqual("TERMINAL_WAIT_DATA_PLAN_UNREACHABLE", status.summary["active_g1_state"])
        self.assertEqual(
            "FEB2025_TERMINAL_WAIT_DATA_NOT_SCORED",
            status.summary["february_state"],
        )
        self.assertEqual("ACTIVE_FAIL_CLOSED", status.summary["february_guard_status"])
        self.assertEqual("SOL_ROUTE_B_ADOPTED", status.summary["rsi_current_route_status"])
        self.assertTrue(status.summary["rsi_v0_2_2_reproducible"])
        self.assertTrue(status.summary["paper_only"])
        self.assertFalse(status.summary["live_trading_authorized"])
        self.assertEqual(">=3.11,<3.14", status.summary["python_requires"])

    def test_current_core_and_frozen_rsi_core_are_distinct_explicit_lineages(self) -> None:
        raw = self._raw()
        current = (ROOT / raw["core"]["versioned_path"]).read_bytes()
        mirror = (ROOT / raw["core"]["root_mirror_path"]).read_bytes()
        legacy = (ROOT / raw["rsi_v0_2_2_lineage"]["archived_core_path"]).read_bytes()
        self.assertEqual(current, mirror)
        self.assertNotEqual(current, legacy)
        self.assertEqual(raw["core"]["raw_sha256"], hashlib.sha256(current).hexdigest())
        self.assertEqual(
            raw["rsi_v0_2_2_lineage"]["declared_core_raw_sha256"],
            hashlib.sha256(legacy).hexdigest(),
        )

    def test_overlay_semantic_tamper_fails_after_valid_baseline(self) -> None:
        baseline = self._raw()
        validate_current_system_status(baseline, ROOT)
        mutations = (
            lambda value: value["decision_timeline"]["dynamic_hypothesis_graph_p0_1"].__setitem__(
                "decision_state", "NOT_ACCEPTED"
            ),
            lambda value: value["lane_boundaries"]["new_theory_paper_experiment"].__setitem__(
                "live_trading_authorized", True
            ),
            lambda value: value["runtime"].__setitem__("python_requires", ">=3.9"),
            lambda value: value["rsi_v0_2_2_lineage"].__setitem__(
                "immutable_contract_bytes_changed", True
            ),
            lambda value: value["decision_timeline"]["har1r4"].__setitem__(
                "aggregate_outcome", "SUCCESS"
            ),
            lambda value: value["decision_timeline"]["har1r5"].__setitem__(
                "decision_state", "NETWORK_AUTHORIZED"
            ),
            lambda value: value["decision_timeline"]["february_historical_diagnostic"].__setitem__(
                "guard_status", "INACTIVE"
            ),
            lambda value: value["rsi_v0_2_2_lineage"].__setitem__(
                "current_route_status", "REVIEW_READY"
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(baseline)
                mutate(changed)
                with self.assertRaises(CurrentSystemStatusError):
                    validate_current_system_status(changed, ROOT)

    def test_bound_file_tamper_fails_after_isolated_baseline_validates(self) -> None:
        temp, workspace = self._isolated_workspace()
        self.addCleanup(temp.cleanup)
        copied_status = workspace / "config/current_system_status.v1.json"
        CurrentSystemStatus.load(copied_status, workspace_root=workspace)
        gate = workspace / "config/sol_decision.research-system-dynamic-hypothesis-graph-p0_1-gate.v1.json"
        gate.write_bytes(gate.read_bytes() + b" ")
        with self.assertRaises(CurrentSystemStatusError):
            CurrentSystemStatus.load(copied_status, workspace_root=workspace)

    def test_duplicate_json_key_is_rejected(self) -> None:
        temp, workspace = self._isolated_workspace()
        self.addCleanup(temp.cleanup)
        path = workspace / "config/duplicate-status.json"
        path.write_text('{"schema_version":"current-system-status.v1","schema_version":"drift"}', encoding="utf-8")
        with self.assertRaises(CurrentSystemStatusError):
            CurrentSystemStatus.load(path, workspace_root=workspace)

    def test_reader_docs_reject_known_stale_current_claims_and_runtime_authority_links(self) -> None:
        current = (ROOT / "archive/docs/logs/SYSTEM_STATUS_2026-08-01.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        governance = (ROOT / "archive/authority/PROGRAM_GOVERNANCE_v1_5_2026-07-30.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "archive/docs/design/SYSTEM_DESIGN_ROADMAP_v1_5_2026-07-30.md").read_text(encoding="utf-8")
        for document in (current, readme, governance, roadmap):
            self.assertIn("TERMINAL_WAIT_DATA_PLAN_UNREACHABLE", document)
        self.assertIn("WAIT_DATA_SOURCE_CONTRACT_MISMATCH", current)
        self.assertIn("AUTHORIZE_HAR1R5_STATIC_GATE_ONLY_NO_NETWORK", current)
        self.assertIn("REVIEW_READY / REJECT_FREEZE", current)
        self.assertIn("HISTORICAL_REWORK_NON_AUTHORITY", current)
        self.assertNotIn("`S1 G1_COLLECTION` 双线并行", governance)
        self.assertNotIn("首个真实计划窗口尚未开始", governance)
        self.assertNotIn("当前 28 个 slot 全部 `PENDING`", roadmap)
        runtime_authority_link = re.compile(r"\]\((?:\./)?\.runtime/")
        self.assertIsNone(runtime_authority_link.search(readme))
        self.assertIsNone(runtime_authority_link.search(governance))


if __name__ == "__main__":
    unittest.main()
