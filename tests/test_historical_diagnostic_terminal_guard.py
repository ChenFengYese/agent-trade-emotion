import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trade_system import historical_diagnostic_terminal_guard as terminal_guard
from trade_system.historical_diagnostic_application import (
    HistoricalDiagnosticApplicationError,
    execute_authorized_fresh_diagnostic,
    verify_receipt_bound_application,
)
from trade_system.historical_diagnostic_authorization import (
    HistoricalDiagnosticAuthorizationError,
    build_input_acquisition_receipt,
    consume_fresh_scoring_authorization,
    register_ready_to_score,
    register_wait_data_not_scored,
    verify_acquisition_receipt,
)


PROJECT = Path(__file__).resolve().parents[1]
PLAN = PROJECT / "config/binance_cm_historical_diagnostic.v2.frozen_before_download.json"
RECEIPT = PROJECT / ".runtime/historical-diagnostic-s0-009-release/authorization-receipt.v1.json"
CONTRACT = PROJECT / ".runtime/historical-diagnostic-s0-009-release/authorized-execution-contract.v2.json"
R1_SCOPE_SHA256 = "9de4bd089835ec5e9b9ece4242a5d87015bb34f2e24ccc1e9e4dcfbb5b2d795f"
R1_RECEIPT_ID = "S0-009-FEB2025-FRESH-FALSIFICATION-85A95D08-R1-ONE-TIME"


class FebruaryTerminalSeenGuardTests(unittest.TestCase):
    def _reject(self, **kwargs):
        defaults = {
            "plan_path": PLAN,
            "receipt_path": RECEIPT,
            "workspace_root": PROJECT,
        }
        defaults.update(kwargs)
        with self.assertRaisesRegex(terminal_guard.FebruaryTerminalSeenError, "terminal"):
            terminal_guard.reject_february_terminal_seen_attempt(**defaults)

    def test_rejects_before_any_market_zip_or_checksum_probe(self):
        touched = []
        original_open = Path.open
        original_stat = Path.stat
        original_exists = Path.exists

        def market(path):
            name = str(path)
            return name.endswith(".zip") or name.endswith(".CHECKSUM")

        def checked_open(path, *args, **kwargs):
            if market(path):
                touched.append(("open", str(path)))
                raise AssertionError("terminal guard must not open a market input")
            return original_open(path, *args, **kwargs)

        def checked_stat(path, *args, **kwargs):
            if market(path):
                touched.append(("stat", str(path)))
                raise AssertionError("terminal guard must not stat a market input")
            return original_stat(path, *args, **kwargs)

        def checked_exists(path):
            if market(path):
                touched.append(("exists", str(path)))
                raise AssertionError("terminal guard must not probe a market input")
            return original_exists(path)

        with mock.patch.object(Path, "open", checked_open), mock.patch.object(Path, "stat", checked_stat), mock.patch.object(Path, "exists", checked_exists):
            self._reject(output_path=PROJECT / "alternate.zip", registry_path=PROJECT / "alternate.CHECKSUM")
        self.assertEqual([], touched)

    def test_output_registry_and_root_local_copy_paths_cannot_bypass(self):
        for output, registry in (
            (PROJECT / "runtime/a.json", PROJECT / "runtime/r.json"),
            (PROJECT / ".runtime/historical-diagnostic-authorized-download-root/february-2025/other.zip", PROJECT / "other-registry.json"),
        ):
            self._reject(output_path=output, registry_path=registry)

        with tempfile.TemporaryDirectory() as directory:
            copied_root = Path(directory) / "copied-workspace"
            copied_root.mkdir()
            self._reject(workspace_root=copied_root)

    def test_symlinked_plan_or_workspace_cannot_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            plan_link = temp / "plan-link.json"
            plan_link.symlink_to(PLAN)
            self._reject(plan_path=plan_link)

            root_link = temp / "workspace-link"
            root_link.symlink_to(PROJECT, target_is_directory=True)
            self._reject(workspace_root=root_link)

    def test_missing_or_sha_drifted_authority_fails_closed(self):
        with mock.patch.object(terminal_guard, "_sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(terminal_guard.FebruaryTerminalSeenError, "A3E1 policy SHA-256 drifted"):
                terminal_guard.reject_february_terminal_seen_attempt(
                    plan_path=PLAN,
                    receipt_path=RECEIPT,
                    workspace_root=PROJECT,
                )

    def test_shared_authorization_and_application_paths_reject_before_market_access(self):
        touched = []
        original_open = Path.open
        original_stat = Path.stat
        original_exists = Path.exists

        def market(path):
            name = str(path)
            return name.endswith(".zip") or name.endswith(".CHECKSUM")

        def checked_open(path, *args, **kwargs):
            if market(path):
                touched.append(("open", str(path)))
                raise AssertionError("terminal guard must precede market input open")
            return original_open(path, *args, **kwargs)

        def checked_stat(path, *args, **kwargs):
            if market(path):
                touched.append(("stat", str(path)))
                raise AssertionError("terminal guard must precede market input stat")
            return original_stat(path, *args, **kwargs)

        def checked_exists(path):
            if market(path):
                touched.append(("exists", str(path)))
                raise AssertionError("terminal guard must precede market input exists")
            return original_exists(path)

        never_acquisition = PROJECT / ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/a3e1-never-acquisition.json"
        never_registry = PROJECT / ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/a3e1-never-registry.json"
        never_report = PROJECT / ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/a3e1-never-report.json"
        with mock.patch.object(Path, "open", checked_open), mock.patch.object(Path, "stat", checked_stat), mock.patch.object(Path, "exists", checked_exists):
            for action in (
                lambda: build_input_acquisition_receipt(PLAN, RECEIPT, never_acquisition, workspace_root=PROJECT),
                lambda: verify_acquisition_receipt(never_acquisition, RECEIPT, plan_path=PLAN, workspace_root=PROJECT),
                lambda: register_ready_to_score(never_registry, never_acquisition, RECEIPT, plan_path=PLAN, workspace_root=PROJECT, summary_sha256="a" * 64),
                lambda: consume_fresh_scoring_authorization(never_registry, never_acquisition, RECEIPT, plan_path=PLAN, workspace_root=PROJECT, summary_sha256="a" * 64, scoring_attempt_id="a3e1-never"),
                lambda: register_wait_data_not_scored(never_registry, receipt_id=R1_RECEIPT_ID, receipt_scope_sha256=R1_SCOPE_SHA256, summary_sha256="a" * 64),
            ):
                with self.assertRaisesRegex(HistoricalDiagnosticAuthorizationError, "terminal"):
                    action()
            with self.assertRaisesRegex(HistoricalDiagnosticApplicationError, "terminal"):
                verify_receipt_bound_application(plan_path=PLAN, contract_path=CONTRACT, receipt_path=RECEIPT, workspace_root=PROJECT)
            with self.assertRaisesRegex(HistoricalDiagnosticApplicationError, "terminal"):
                execute_authorized_fresh_diagnostic(plan_path=PLAN, contract_path=CONTRACT, receipt_path=RECEIPT, acquisition_path=never_acquisition, registry_path=never_registry, workspace_root=PROJECT, report_path=never_report, scoring_attempt_id="a3e1-never")
        self.assertEqual([], touched)
        self.assertFalse(never_acquisition.exists())
        self.assertFalse(never_registry.exists())
        self.assertFalse(never_report.exists())


if __name__ == "__main__":
    unittest.main()
