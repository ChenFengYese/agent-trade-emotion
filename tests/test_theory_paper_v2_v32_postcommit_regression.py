from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.application.v31_authority_freeze import (
    document_binding,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.governance.v32_postcommit_regression import (
    AGGREGATE_DIGEST_FIELD,
    EXECUTION_DIGEST_FIELD,
    FIXED_ENVIRONMENT,
    FIXED_MAX_STREAM_BYTES,
    FIXED_PYTHON_EXECUTABLE,
    RESERVATION_DIGEST_FIELD,
    SUITE_IDS,
    V32PostCommitRegressionError,
    build_v32_postcommit_regression_aggregate_support_v1,
    build_v32_postcommit_regression_execution_receipt_v1,
    build_v32_postcommit_regression_reservation_v1,
    fixed_argv_for_suite_v1,
    qualification_support_paths_v1,
    verify_v32_postcommit_regression_execution_receipt_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_workspace_freeze import (
    build_v32_workspace_freeze_receipt_v1_1,
)
from trade_system.theory_paper_v2.infrastructure.authority import (
    v32_postcommit_regression as implementation,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_postcommit_regression import (
    V32PostCommitRegressionInfrastructureError,
    load_v32_postcommit_regression_prequalification_support_v1,
    replay_v32_postcommit_regression_aggregate_support_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_secure_write_once_store import (
    secure_write_once_json,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_workspace_freeze import (
    V32WorkspaceFreezeInfrastructureError,
    verify_live_v32_workspace_freeze_v1,
)
from tests.v32_postcommit_regression_support import (
    write_valid_postcommit_regression_support,
)

TARGET = "v32-prospective-btcusdt-20260809t120000z"
QUALIFICATION = "v32-qualification-btcusdt-20260809t120000z"


def git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    )
    return result.stdout if binary else result.stdout.decode().strip()


def binding(path: str, document: dict, digest_field: str) -> dict[str, str]:
    return {
        **document_binding(path=path, document=document, digest_field=digest_field),
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }


class V32PostCommitRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / ".gitignore").write_text(".runtime/\n", encoding="utf-8")
        (self.root / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
        git(self.root, "init", "-b", "codex/postcommit-test")
        git(self.root, "config", "user.email", "test@example.invalid")
        git(self.root, "config", "user.name", "V32 Test")
        git(self.root, "add", ".gitignore", "runtime.py")
        git(self.root, "commit", "-m", "postcommit fixture")

    def identity(self) -> dict[str, str]:
        executable = Path(FIXED_PYTHON_EXECUTABLE).resolve(strict=True)
        return {
            "target_run_id": TARGET,
            "qualification_run_id": QUALIFICATION,
            "branch": str(git(self.root, "branch", "--show-current")),
            "frozen_commit_sha": str(git(self.root, "rev-parse", "HEAD")),
            "frozen_tree_sha": str(git(self.root, "show", "-s", "--format=%T", "HEAD")),
            "python_executable": FIXED_PYTHON_EXECUTABLE,
            "python_realpath": executable.as_posix(),
            "python_physical_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "python_version": platform.python_version(),
            "cwd": self.root.as_posix(),
        }

    def execution(
        self,
        suite_id: str,
        *,
        stderr: str = "Ran 3 tests in 0.001s\n\nOK\n",
        started_at: str = "2026-08-09T12:00:01Z",
        completed_at: str = "2026-08-09T12:00:02Z",
    ) -> dict:
        empty_status = hashlib.sha256(b"").hexdigest()
        return build_v32_postcommit_regression_execution_receipt_v1(
            receipt_id=f"{QUALIFICATION}:{suite_id}:attempt-1",
            suite_id=suite_id,
            started_at=started_at,
            completed_at=completed_at,
            **self.identity(),
            status="PASS",
            runner_outcome="COMPLETED",
            exit_code=0,
            stdout_utf8="",
            stderr_utf8=stderr,
            workspace_porcelain_sha256_before=empty_status,
            workspace_porcelain_sha256_after=empty_status,
        )

    def test_legacy_reader_preserves_historical_fixed_patterns(self) -> None:
        for suite_id, pattern in zip(
            SUITE_IDS,
            ("test_theory_paper_v2_v32*.py", "test_theory_paper*.py"),
        ):
            argv = fixed_argv_for_suite_v1(suite_id)
            self.assertEqual(FIXED_PYTHON_EXECUTABLE, argv[0])
            self.assertIn("-I", argv)
            self.assertEqual(["-s", "tests", "-t", ".", "-p", pattern], argv[-6:])
        self.assertNotIn("PYTHONPATH", FIXED_ENVIRONMENT)
        self.assertNotIn("PYTHONHOME", FIXED_ENVIRONMENT)

    def test_skipped_or_forged_pass_and_raw_log_tamper_are_rejected(self) -> None:
        with self.assertRaisesRegex(V32PostCommitRegressionError, "PASS_STATUS"):
            self.execution(
                SUITE_IDS[0],
                stderr="Ran 3 tests in 0.001s\n\nOK (skipped=1)\n",
            )
        receipt = self.execution(SUITE_IDS[0])
        forged = deepcopy(receipt)
        forged["fixed_argv"][-1] = "one_test.py"
        forged = self_digest(forged, EXECUTION_DIGEST_FIELD)
        with self.assertRaises(V32PostCommitRegressionError):
            verify_v32_postcommit_regression_execution_receipt_v1(forged)
        tampered = deepcopy(receipt)
        tampered["stderr_utf8"] += "forged\n"
        with self.assertRaises(V32PostCommitRegressionError):
            verify_v32_postcommit_regression_execution_receipt_v1(tampered)

    def test_legacy_aggregate_still_requires_its_historical_two_receipts(self) -> None:
        support = write_valid_postcommit_regression_support(
            self.root, target_run_id=TARGET, qualification_run_id=QUALIFICATION
        )
        paths = qualification_support_paths_v1(QUALIFICATION)
        with self.assertRaisesRegex(V32PostCommitRegressionError, "SUITE_SET"):
            build_v32_postcommit_regression_aggregate_support_v1(
                aggregate_id="single-suite",
                reservation=support["reservation"],
                reservation_binding=binding(
                    paths["reservation"],
                    support["reservation"],
                    RESERVATION_DIGEST_FIELD,
                ),
                execution_receipts={SUITE_IDS[0]: support["receipts"][SUITE_IDS[0]]},
                execution_receipt_bindings={
                    SUITE_IDS[0]: binding(
                        paths[f"receipt:{SUITE_IDS[0]}"],
                        support["receipts"][SUITE_IDS[0]],
                        EXECUTION_DIGEST_FIELD,
                    )
                },
            )

    def test_aggregate_uses_parsed_time_and_enforces_fixed_suite_order(self) -> None:
        empty_status = hashlib.sha256(b"").hexdigest()
        reservation = build_v32_postcommit_regression_reservation_v1(
            reservation_id=f"{QUALIFICATION}:postcommit-regression:attempt-1",
            reserved_at="2026-08-09T12:00:00Z",
            **self.identity(),
            workspace_status="CLEAN_EXACT_ALLOWLIST",
            workspace_porcelain_sha256=empty_status,
            allowed_untracked_user_artifacts=[],
        )
        receipts = {
            SUITE_IDS[0]: self.execution(
                SUITE_IDS[0],
                started_at="2026-08-09T12:00:00.100000Z",
                completed_at="2026-08-09T12:00:00.200000Z",
            ),
            SUITE_IDS[1]: self.execution(
                SUITE_IDS[1],
                started_at="2026-08-09T12:00:00.300000Z",
                completed_at="2026-08-09T12:00:00.400000Z",
            ),
        }
        paths = qualification_support_paths_v1(QUALIFICATION)
        receipt_bindings = {
            suite_id: binding(
                paths[f"receipt:{suite_id}"],
                receipt,
                EXECUTION_DIGEST_FIELD,
            )
            for suite_id, receipt in receipts.items()
        }
        kwargs = {
            "aggregate_id": f"{QUALIFICATION}:postcommit-regression:aggregate",
            "reservation": reservation,
            "reservation_binding": binding(
                paths["reservation"], reservation, RESERVATION_DIGEST_FIELD
            ),
            "execution_receipts": receipts,
            "execution_receipt_bindings": receipt_bindings,
        }
        aggregate = build_v32_postcommit_regression_aggregate_support_v1(**kwargs)
        self.assertEqual("2026-08-09T12:00:00.100000Z", aggregate["started_at"])
        self.assertEqual("2026-08-09T12:00:00.400000Z", aggregate["completed_at"])
        self.assertEqual(
            "TRUSTED_LOCAL_CONTROLLER_POSTCOMMIT_AUDIT_ONLY_"
            "NOT_INDEPENDENT_PROVIDER_OR_HARDWARE_ATTESTATION_"
            "NOT_PREDICTION_PROFIT_OR_TRADING_EXECUTION",
            aggregate["claim_ceiling"],
        )

        overlapping = dict(receipts)
        overlapping[SUITE_IDS[1]] = self.execution(
            SUITE_IDS[1],
            started_at="2026-08-09T12:00:00.150000Z",
            completed_at="2026-08-09T12:00:00.400000Z",
        )
        overlapping_bindings = dict(receipt_bindings)
        overlapping_bindings[SUITE_IDS[1]] = binding(
            paths[f"receipt:{SUITE_IDS[1]}"],
            overlapping[SUITE_IDS[1]],
            EXECUTION_DIGEST_FIELD,
        )
        with self.assertRaisesRegex(V32PostCommitRegressionError, "TIME_INVALID"):
            build_v32_postcommit_regression_aggregate_support_v1(
                **{
                    **kwargs,
                    "execution_receipts": overlapping,
                    "execution_receipt_bindings": overlapping_bindings,
                }
            )

    def test_commit_or_tree_drift_blocks_prequalification_copy(self) -> None:
        write_valid_postcommit_regression_support(
            self.root, target_run_id=TARGET, qualification_run_id=QUALIFICATION
        )
        (self.root / "runtime.py").write_text("VALUE = 2\n", encoding="utf-8")
        git(self.root, "add", "runtime.py")
        git(self.root, "commit", "-m", "drift")
        with self.assertRaisesRegex(
            V32PostCommitRegressionInfrastructureError, "DRIFT"
        ):
            load_v32_postcommit_regression_prequalification_support_v1(
                project_root=self.root,
                target_run_id=TARGET,
                qualification_run_id=QUALIFICATION,
            )

    def test_git_identity_ignores_caller_git_dir_and_path(self) -> None:
        write_valid_postcommit_regression_support(
            self.root, target_run_id=TARGET, qualification_run_id=QUALIFICATION
        )
        with patch.dict(
            os.environ,
            {"GIT_DIR": "/definitely/not/the/repository", "PATH": "/no/git"},
            clear=False,
        ):
            replay = load_v32_postcommit_regression_prequalification_support_v1(
                project_root=self.root,
                target_run_id=TARGET,
                qualification_run_id=QUALIFICATION,
            )
        self.assertEqual("PASS", replay["aggregate"]["verdict"])

    def test_legacy_writer_is_retired_before_runtime_access(self) -> None:
        with patch.object(
            implementation,
            "_root",
            side_effect=AssertionError("retired writer must not inspect the project"),
        ), patch.object(
            implementation,
            "_ids",
            side_effect=AssertionError("retired writer must not validate run identity"),
        ), patch.object(
            implementation,
            "_run_fixed_suite_bounded",
            side_effect=AssertionError("retired writer must not execute a suite"),
        ):
            with self.assertRaisesRegex(
                V32PostCommitRegressionInfrastructureError,
                "^V32_POSTCOMMIT_LEGACY_WRITER_RETIRED$",
            ):
                implementation.run_v32_postcommit_regressions_once_v1(
                    project_root=self.root,
                    target_run_id=TARGET,
                    qualification_run_id=QUALIFICATION,
                )

    def test_bounded_runner_kills_background_descendant_holding_pipes(self) -> None:
        command = [
            FIXED_PYTHON_EXECUTABLE,
            "-I",
            "-c",
            (
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(30)'],"
                "stdout=sys.stdout,stderr=sys.stderr);"
                "sys.stdout.write('done\\n');sys.stdout.flush()"
            ),
        ]
        started = time.monotonic()
        with patch.object(
            implementation, "fixed_argv_for_suite_v1", return_value=command
        ):
            result = implementation._run_fixed_suite_bounded(
                self.root, SUITE_IDS[0]
            )
        self.assertEqual("DESCENDANT_PROCESS_LEAK", result.outcome)
        self.assertFalse(result.stdout_complete)
        self.assertFalse(result.stderr_complete)
        self.assertLess(time.monotonic() - started, 5.0)

    def test_bounded_runner_allows_normal_dual_pipe_eof(self) -> None:
        command = [
            FIXED_PYTHON_EXECUTABLE,
            "-I",
            "-c",
            "import sys;print('out');print('err', file=sys.stderr)",
        ]
        with patch.object(
            implementation, "fixed_argv_for_suite_v1", return_value=command
        ):
            result = implementation._run_fixed_suite_bounded(
                self.root, SUITE_IDS[0]
            )
        self.assertEqual("COMPLETED", result.outcome)
        self.assertEqual(0, result.exit_code)
        self.assertEqual(b"out\n", result.stdout)
        self.assertEqual(b"err\n", result.stderr)
        self.assertTrue(result.stdout_complete)
        self.assertTrue(result.stderr_complete)

    def test_bounded_runner_times_out_after_direct_child_closes_both_pipes(self) -> None:
        command = [
            FIXED_PYTHON_EXECUTABLE,
            "-I",
            "-c",
            "import os,time;os.close(1);os.close(2);time.sleep(30)",
        ]
        started = time.monotonic()
        with patch.object(
            implementation, "fixed_argv_for_suite_v1", return_value=command
        ), patch.object(implementation, "FIXED_TIMEOUT_SECONDS", 0.2):
            result = implementation._run_fixed_suite_bounded(
                self.root, SUITE_IDS[0]
            )
        self.assertEqual("TIMEOUT", result.outcome)
        self.assertLess(time.monotonic() - started, 3.0)

    def test_bounded_runner_interrupt_preserves_captured_prefix(self) -> None:
        command = [
            FIXED_PYTHON_EXECUTABLE,
            "-I",
            "-c",
            "import sys,time;sys.stdout.write('prefix\\n');sys.stdout.flush();time.sleep(30)",
        ]
        real_read = implementation.os.read
        real_select = implementation.selectors.DefaultSelector.select
        captured = False

        def remember_read(fd, size):
            nonlocal captured
            chunk = real_read(fd, size)
            if chunk:
                captured = True
            return chunk

        def interrupt_after_capture(selector, timeout=None):
            if captured:
                raise KeyboardInterrupt
            return real_select(selector, timeout)

        with patch.object(
            implementation, "fixed_argv_for_suite_v1", return_value=command
        ), patch.object(implementation.os, "read", side_effect=remember_read), patch.object(
            implementation.selectors.DefaultSelector,
            "select",
            new=interrupt_after_capture,
        ):
            result = implementation._run_fixed_suite_bounded(
                self.root, SUITE_IDS[0]
            )
        self.assertEqual("INTERRUPTED", result.outcome)
        self.assertEqual(b"prefix\n", result.stdout)
        self.assertFalse(result.stdout_complete)
        self.assertFalse(result.stderr_complete)

    def test_bounded_runner_oserror_preserves_captured_prefix(self) -> None:
        command = [
            FIXED_PYTHON_EXECUTABLE,
            "-I",
            "-c",
            "import sys,time;sys.stderr.write('error-prefix\\n');sys.stderr.flush();time.sleep(30)",
        ]
        real_read = implementation.os.read
        real_select = implementation.selectors.DefaultSelector.select
        captured = False

        def remember_read(fd, size):
            nonlocal captured
            chunk = real_read(fd, size)
            if chunk:
                captured = True
            return chunk

        def fail_after_capture(selector, timeout=None):
            if captured:
                raise OSError("simulated selector failure")
            return real_select(selector, timeout)

        with patch.object(
            implementation, "fixed_argv_for_suite_v1", return_value=command
        ), patch.object(implementation.os, "read", side_effect=remember_read), patch.object(
            implementation.selectors.DefaultSelector,
            "select",
            new=fail_after_capture,
        ):
            result = implementation._run_fixed_suite_bounded(
                self.root, SUITE_IDS[0]
            )
        self.assertEqual("RUNNER_ERROR", result.outcome)
        self.assertEqual(b"error-prefix\n", result.stderr)
        self.assertFalse(result.stdout_complete)
        self.assertFalse(result.stderr_complete)

    def test_bounded_runner_terminates_at_physical_output_limit(self) -> None:
        command = [
            FIXED_PYTHON_EXECUTABLE,
            "-I",
            "-c",
            "import sys,time;sys.stdout.write('x'*100000);sys.stdout.flush();time.sleep(30)",
        ]
        with patch.object(
            implementation, "fixed_argv_for_suite_v1", return_value=command
        ), patch.object(implementation, "FIXED_MAX_STREAM_BYTES", 64):
            result = implementation._run_fixed_suite_bounded(
                self.root, SUITE_IDS[0]
            )
        self.assertEqual("OUTPUT_LIMIT_EXCEEDED", result.outcome)
        self.assertLessEqual(len(result.stdout), 65)

    def test_physical_receipt_drift_breaks_aggregate_replay(self) -> None:
        support = write_valid_postcommit_regression_support(
            self.root, target_run_id=TARGET, qualification_run_id=QUALIFICATION
        )
        paths = qualification_support_paths_v1(QUALIFICATION)
        reservation_binding = secure_write_once_json(
            self.root,
            paths["reservation"],
            support["reservation"],
            digest_field=RESERVATION_DIGEST_FIELD,
            require_new=True,
        )
        for suite_id in SUITE_IDS:
            secure_write_once_json(
                self.root,
                paths[f"receipt:{suite_id}"],
                support["receipts"][suite_id],
                digest_field=EXECUTION_DIGEST_FIELD,
                require_new=True,
            )
        aggregate_binding = secure_write_once_json(
            self.root,
            paths["aggregate"],
            support["aggregate"],
            digest_field=AGGREGATE_DIGEST_FIELD,
            require_new=True,
        )
        self.assertEqual(
            support["reservation"][RESERVATION_DIGEST_FIELD],
            reservation_binding["semantic_digest"],
        )
        replay = replay_v32_postcommit_regression_aggregate_support_v1(
            project_root=self.root,
            aggregate_binding=aggregate_binding,
            expected_target_run_id=TARGET,
            expected_qualification_run_id=QUALIFICATION,
        )
        self.assertTrue(replay["full_physical_replay_verified"])
        self.assertEqual(set(SUITE_IDS), set(replay["execution_receipts"]))
        self.assertEqual(TARGET, replay["aggregate"]["target_run_id"])
        self.assertEqual(
            QUALIFICATION, replay["aggregate"]["qualification_run_id"]
        )
        receipt_path = self.root / paths[f"receipt:{SUITE_IDS[0]}"]
        receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
        with self.assertRaises(V32PostCommitRegressionInfrastructureError):
            replay_v32_postcommit_regression_aggregate_support_v1(
                project_root=self.root,
                aggregate_binding=aggregate_binding,
                expected_target_run_id=TARGET,
                expected_qualification_run_id=QUALIFICATION,
            )

    def test_workspace_replay_enforces_identity_and_postcommit_chronology(self) -> None:
        support = write_valid_postcommit_regression_support(
            self.root, target_run_id=TARGET, qualification_run_id=QUALIFICATION
        )
        paths = qualification_support_paths_v1(QUALIFICATION)
        secure_write_once_json(
            self.root,
            paths["reservation"],
            support["reservation"],
            digest_field=RESERVATION_DIGEST_FIELD,
            require_new=True,
        )
        for suite_id in SUITE_IDS:
            secure_write_once_json(
                self.root,
                paths[f"receipt:{suite_id}"],
                support["receipts"][suite_id],
                digest_field=EXECUTION_DIGEST_FIELD,
                require_new=True,
            )
        aggregate_binding = secure_write_once_json(
            self.root,
            paths["aggregate"],
            support["aggregate"],
            digest_field=AGGREGATE_DIGEST_FIELD,
            require_new=True,
        )
        relevant = str(git(self.root, "ls-files")).splitlines()
        kwargs = {
            "receipt_id": "workspace-v1.1",
            "branch": str(git(self.root, "branch", "--show-current")),
            "frozen_commit_sha": str(git(self.root, "rev-parse", "HEAD")),
            "frozen_tree_sha": str(git(self.root, "show", "-s", "--format=%T", "HEAD")),
            "relevant_paths": relevant,
            "relevant_path_sha256": {
                path: hashlib.sha256((self.root / path).read_bytes()).hexdigest()
                for path in relevant
            },
            "allowed_untracked_user_artifacts": [],
            "ignored_runtime_roots": [".runtime"],
            "postcommit_regression_aggregate_binding": aggregate_binding,
            "postcommit_regression_target_run_id": TARGET,
            "postcommit_regression_qualification_run_id": QUALIFICATION,
        }
        too_early = build_v32_workspace_freeze_receipt_v1_1(
            **kwargs, observed_at="2026-08-06T23:57:00Z"
        )
        with self.assertRaisesRegex(
            V32WorkspaceFreezeInfrastructureError, "TIME_INVALID"
        ):
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=too_early
            )
        wrong_identity = build_v32_workspace_freeze_receipt_v1_1(
            **{
                **kwargs,
                "postcommit_regression_target_run_id": (
                    "v32-prospective-btcusdt-20260809t120100z"
                ),
            },
            observed_at="2026-08-06T23:59:00Z",
        )
        with self.assertRaisesRegex(
            V32WorkspaceFreezeInfrastructureError, "REPLAY_FAILED"
        ):
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=wrong_identity
            )


if __name__ == "__main__":
    unittest.main()
