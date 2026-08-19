from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import run_theory_tests
from trade_system.theory_paper_v2.presentation import v32_qualification_composition


class TheoryTestRunnerTests(unittest.TestCase):
    def identity(self) -> dict[str, str]:
        return {
            "commit": "1" * 40,
            "tree": "2" * 40,
            "python": "/fixed/python",
            "python_realpath": "/fixed/python",
            "python_sha256": "3" * 64,
            "python_version": "Python 3.12.0",
            "environment_digest": "4" * 64,
        }

    def plan(self) -> dict[str, object]:
        return {
            "v32": ("tests.v32.Case.test_one",),
            "theory": (
                "tests.other.Case.test_two",
                "tests.v32.Case.test_one",
            ),
            "unique": (
                "tests.other.Case.test_two",
                "tests.v32.Case.test_one",
            ),
            "catalog_digest": "a" * 64,
        }

    def passed_result(self) -> dict[str, object]:
        return {
            "status": "PASS",
            "exit_code": 0,
            "tests_run": 2,
            "skips": 0,
            "duration_seconds": 1.0,
            "output_tail": "Ran 2 tests in 1.000s\nOK",
        }

    def test_static_plan_is_the_old_union_with_each_test_id_once(self) -> None:
        plan = run_theory_tests.build_unique_plan(
            Path(__file__).resolve().parents[1]
        )
        v32 = set(plan["v32"])
        theory = set(plan["theory"])
        self.assertTrue(v32)
        self.assertLess(v32, theory)
        self.assertEqual(tuple(sorted(v32 | theory)), plan["unique"])
        self.assertEqual(plan["theory"], plan["unique"])
        self.assertEqual(len(plan["unique"]), len(set(plan["unique"])))

    def test_code_identity_key_has_no_run_identity_and_invalidates_on_inputs(self) -> None:
        identity = self.identity()
        original = run_theory_tests.build_code_key(identity, "a" * 64)
        self.assertEqual(
            original,
            run_theory_tests.build_code_key(identity, "a" * 64),
        )
        for changed in (
            {**identity, "tree": "5" * 40},
            {**identity, "python_sha256": "6" * 64},
            {**identity, "environment_digest": "7" * 64},
        ):
            with self.subTest(changed=changed):
                self.assertNotEqual(
                    original,
                    run_theory_tests.build_code_key(changed, "a" * 64),
                )
        self.assertNotEqual(
            original,
            run_theory_tests.build_code_key(identity, "b" * 64),
        )
        self.assertFalse(
            {"run_id", "target_run_id", "qualification_run_id"}
            & set(identity)
        )
        with self.assertRaisesRegex(
            run_theory_tests.TheoryTestRunnerError, "CODE_IDENTITY_INVALID"
        ):
            run_theory_tests.build_code_key(
                {**identity, "qualification_run_id": "forbidden"}, "a" * 64
            )

    def test_unchanged_code_reuses_disk_cache_without_second_suite_execution(self) -> None:
        result = self.passed_result()
        with TemporaryDirectory() as folder, patch.object(
            run_theory_tests, "build_unique_plan", return_value=self.plan()
        ), patch.object(
            run_theory_tests, "_identity", return_value=self.identity()
        ), patch.object(
            run_theory_tests, "_execute", return_value=result
        ) as execute:
            root = Path(folder)
            first = run_theory_tests.ensure_unique_result(root)
            second = run_theory_tests.ensure_unique_result(root)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["cache_key"], second["cache_key"])
            self.assertEqual(1, execute.call_count)
            persisted = json.loads(
                next((root / run_theory_tests.CACHE_BASE).glob("*.json")).read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(
                {"run_id", "target_run_id", "qualification_run_id"}
                & (
                    set(persisted["subject"])
                    | set(persisted["subject"]["identity"])
                )
            )
            self.assertEqual(run_theory_tests.CLAIM_SCOPE, persisted["claim_scope"])
            self.assertEqual(
                run_theory_tests._record_digest(persisted),
                persisted[run_theory_tests.CACHE_DIGEST_FIELD],
            )

    def test_existing_lock_stops_duplicate_execution(self) -> None:
        with TemporaryDirectory() as folder, patch.object(
            run_theory_tests, "build_unique_plan", return_value=self.plan()
        ), patch.object(
            run_theory_tests, "_identity", return_value=self.identity()
        ), patch.object(run_theory_tests, "_execute") as execute:
            root = Path(folder)
            key = run_theory_tests.build_code_key(
                self.identity(), str(self.plan()["catalog_digest"])
            )
            lock = root / run_theory_tests.CACHE_BASE / f"{key}.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text("existing\n", encoding="utf-8")
            with self.assertRaisesRegex(
                run_theory_tests.TheoryTestRunnerError,
                "ALREADY_RUNNING_OR_INTERRUPTED",
            ):
                run_theory_tests.ensure_unique_result(root)
            execute.assert_not_called()

    def test_unchanged_failed_result_is_not_retried(self) -> None:
        failed = {
            "status": "FAIL",
            "exit_code": 1,
            "tests_run": 2,
            "skips": 0,
            "duration_seconds": 1.0,
            "output_tail": "FAILED (failures=1)",
        }
        with TemporaryDirectory() as folder, patch.object(
            run_theory_tests, "build_unique_plan", return_value=self.plan()
        ), patch.object(
            run_theory_tests, "_identity", return_value=self.identity()
        ), patch.object(
            run_theory_tests, "_execute", return_value=failed
        ) as execute:
            root = Path(folder)
            first = run_theory_tests.ensure_unique_result(root)
            second = run_theory_tests.ensure_unique_result(root)
            self.assertEqual("FAIL", first["status"])
            self.assertEqual("FAIL", second["status"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(1, execute.call_count)

    def test_discovery_count_mismatch_cannot_be_cached_as_pass(self) -> None:
        incomplete = {
            "status": "PASS",
            "exit_code": 0,
            "tests_run": 1,
            "skips": 0,
            "duration_seconds": 1.0,
            "output_tail": "Ran 1 test in 1.000s\nOK",
        }
        with TemporaryDirectory() as folder, patch.object(
            run_theory_tests, "build_unique_plan", return_value=self.plan()
        ), patch.object(
            run_theory_tests, "_identity", return_value=self.identity()
        ), patch.object(run_theory_tests, "_execute", return_value=incomplete):
            result = run_theory_tests.ensure_unique_result(Path(folder))
            self.assertEqual("RUNNER_ERROR", result["status"])
            self.assertIn("DISCOVERY_COUNT_MISMATCH", result["output_tail"])

    def test_workspace_drift_during_execution_cannot_be_cached_as_pass(self) -> None:
        passed = self.passed_result()
        changed = {**self.identity(), "tree": "5" * 40}
        with TemporaryDirectory() as folder, patch.object(
            run_theory_tests, "build_unique_plan", return_value=self.plan()
        ), patch.object(
            run_theory_tests,
            "_identity",
            side_effect=(self.identity(), changed),
        ), patch.object(run_theory_tests, "_execute", return_value=passed):
            result = run_theory_tests.ensure_unique_result(Path(folder))
            self.assertEqual("RUNNER_ERROR", result["status"])
            self.assertIn("WORKSPACE_DRIFT", result["output_tail"])

    def test_nul_status_accepts_the_unicode_allowlist_without_git_quoting(self) -> None:
        allowed = (
            f"?? {run_theory_tests._ALLOWED_UNTRACKED_USER_ARTIFACT}\0".encode(
                "utf-8"
            )
        )
        self.assertTrue(run_theory_tests._workspace_status_is_allowed(b""))
        self.assertTrue(run_theory_tests._workspace_status_is_allowed(allowed))
        self.assertFalse(
            run_theory_tests._workspace_status_is_allowed(
                b"?? archive/user-preserved/other.md\0"
            )
        )
        self.assertFalse(
            run_theory_tests._workspace_status_is_allowed(
                b'?? "archive/user-preserved/quoted.md"\0'
            )
        )

    def test_bounded_runner_runs_the_full_theory_suite_once_and_uses_last_summary(self) -> None:
        bounded = SimpleNamespace(
            outcome="COMPLETED",
            exit_code=0,
            stdout=b"Ran 999 tests in 0.1s\nOK (skipped=7)\n",
            stderr=b"Ran 2 tests in 1.0s\nOK\n",
            stdout_complete=True,
            stderr_complete=True,
        )
        with patch.object(
            run_theory_tests.postcommit_runner,
            "_run_fixed_suite_bounded",
            return_value=bounded,
        ) as execute:
            result = run_theory_tests._execute(Path("/fixed/root"))
        execute.assert_called_once_with(
            Path("/fixed/root"), run_theory_tests.THEORY_SUITE_ID
        )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(2, result["tests_run"])
        self.assertEqual(0, result["skips"])

    def test_cache_tamper_is_rejected_without_rerunning(self) -> None:
        with TemporaryDirectory() as folder, patch.object(
            run_theory_tests, "build_unique_plan", return_value=self.plan()
        ), patch.object(
            run_theory_tests, "_identity", return_value=self.identity()
        ), patch.object(
            run_theory_tests, "_execute", return_value=self.passed_result()
        ) as execute:
            root = Path(folder)
            first = run_theory_tests.ensure_unique_result(root)
            cache = root / run_theory_tests.CACHE_BASE / f"{first['cache_key']}.json"
            record = json.loads(cache.read_text(encoding="utf-8"))
            record["status"] = "FAIL"
            cache.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(
                run_theory_tests.TheoryTestRunnerError,
                "CACHE_INVALID_NO_RERUN",
            ):
                run_theory_tests.ensure_unique_result(root)
            self.assertEqual(1, execute.call_count)

    def test_resigned_cache_still_cannot_claim_pass_with_wrong_count(self) -> None:
        with TemporaryDirectory() as folder, patch.object(
            run_theory_tests, "build_unique_plan", return_value=self.plan()
        ), patch.object(
            run_theory_tests, "_identity", return_value=self.identity()
        ), patch.object(
            run_theory_tests, "_execute", return_value=self.passed_result()
        ) as execute:
            root = Path(folder)
            first = run_theory_tests.ensure_unique_result(root)
            cache = root / run_theory_tests.CACHE_BASE / f"{first['cache_key']}.json"
            record = json.loads(cache.read_text(encoding="utf-8"))
            record["tests_run"] = 1
            record[run_theory_tests.CACHE_DIGEST_FIELD] = (
                run_theory_tests._record_digest(record)
            )
            cache.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(
                run_theory_tests.TheoryTestRunnerError,
                "CACHE_INVALID_NO_RERUN",
            ):
                run_theory_tests.ensure_unique_result(root)
            self.assertEqual(1, execute.call_count)

    def test_each_cache_status_has_a_strict_exit_code_invariant(self) -> None:
        valid = (
            self.passed_result(),
            {**self.passed_result(), "status": "FAIL", "exit_code": 1},
            {**self.passed_result(), "status": "TIMEOUT", "exit_code": None},
            {
                **self.passed_result(),
                "status": "RUNNER_ERROR",
                "exit_code": None,
            },
        )
        for result in valid:
            with self.subTest(status=result["status"]):
                self.assertTrue(
                    run_theory_tests._validate_result_shape(
                        result, expected_tests=2
                    )
                )
        invalid = (
            {**self.passed_result(), "tests_run": 1},
            {**self.passed_result(), "status": "FAIL", "exit_code": 0},
            {**self.passed_result(), "status": "TIMEOUT", "exit_code": 1},
            {
                **self.passed_result(),
                "status": "RUNNER_ERROR",
                "exit_code": 0,
            },
        )
        for result in invalid:
            with self.subTest(result=result):
                self.assertFalse(
                    run_theory_tests._validate_result_shape(
                        result, expected_tests=2
                    )
                )

    def test_legacy_qualification_writer_is_retired_before_runtime_access(self) -> None:
        with patch.object(
            v32_qualification_composition,
            "PROJECT_ROOT",
            side_effect=AssertionError("legacy writer must not access runtime"),
        ):
            with self.assertRaisesRegex(
                v32_qualification_composition.V32QualificationCompositionError,
                "LEGACY_WRITER_RETIRED",
            ):
                v32_qualification_composition.run_v32_postcommit_regressions_for_qualification_once_v1(
                    target_run_id="v32-prospective-btcusdt-20260811t235959z",
                    qualification_run_id="v32-qualification-btcusdt-20260811t235959z",
                )


if __name__ == "__main__":
    unittest.main()
