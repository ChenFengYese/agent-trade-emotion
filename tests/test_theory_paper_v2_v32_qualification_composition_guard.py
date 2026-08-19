from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_runtime_namespace import (
    create_v32_qualification_runtime_namespace_v1,
)
from trade_system.theory_paper_v2.presentation import (
    v32_qualification_composition as qualification_composition,
)


class V32QualificationCompositionGuardTests(unittest.TestCase):
    def test_advance_and_submit_cannot_interleave_one_qualification(self) -> None:
        target = "v32-prospective-btcusdt-guard-concurrency"
        qualification = "v32-qualification-btcusdt-guard-concurrency"
        with TemporaryDirectory() as folder:
            project = Path(folder)
            paths = create_v32_qualification_runtime_namespace_v1(
                project_root=project,
                qualification_run_id=qualification,
            )
            first_entered = threading.Event()
            second_started = threading.Event()
            second_entered = threading.Event()
            release_first = threading.Event()
            state_lock = threading.Lock()
            active = 0
            maximum_active = 0
            revision = 0
            observed_submit_revisions: list[int] = []
            errors: list[BaseException] = []

            def enter(operation: str):
                nonlocal active, maximum_active, revision
                with state_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                try:
                    if operation == "advance":
                        first_entered.set()
                        if not release_first.wait(timeout=2):
                            raise AssertionError("guard test release timed out")
                        revision = 1
                    else:
                        observed_submit_revisions.append(revision)
                        second_entered.set()
                    return {"operation": operation}
                finally:
                    with state_lock:
                        active -= 1

            def advance_worker() -> None:
                try:
                    qualification_composition.advance_v32_qualification_once_v1(
                        target_run_id=target,
                        qualification_run_id=qualification,
                    )
                except BaseException as exc:
                    errors.append(exc)

            def submit_worker() -> None:
                second_started.set()
                try:
                    qualification_composition.submit_v32_qualification_agent_delivery_v1(
                        target_run_id=target,
                        qualification_run_id=qualification,
                        stage="PROPOSAL",
                        expected_request_digest="a" * 64,
                        expected_current_codex_presentation_digest="b" * 64,
                        payload_utf8="{}",
                    )
                except BaseException as exc:
                    errors.append(exc)

            with patch.object(
                qualification_composition, "PROJECT_ROOT", project
            ), patch.object(
                qualification_composition,
                "_advance_v32_qualification_once_unguarded_v1",
                side_effect=lambda **_: enter("advance"),
            ), patch.object(
                qualification_composition,
                "_submit_v32_qualification_agent_delivery_unguarded_v1",
                side_effect=lambda **_: enter("submit"),
            ):
                first = threading.Thread(target=advance_worker, daemon=True)
                second = threading.Thread(target=submit_worker, daemon=True)
                first.start()
                self.assertTrue(first_entered.wait(timeout=2))
                second.start()
                self.assertTrue(second_started.wait(timeout=2))
                try:
                    self.assertFalse(second_entered.wait(timeout=0.2))
                finally:
                    release_first.set()
                first.join(timeout=2)
                second.join(timeout=2)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual([], errors)
            self.assertTrue(second_entered.is_set())
            self.assertEqual(1, maximum_active)
            self.assertEqual([1], observed_submit_revisions)
            self.assertTrue(
                (
                    project
                    / ".runtime/v32/qualifications/.composition-locks"
                    / f"{qualification}.lock"
                ).is_file()
            )
            self.assertFalse((project / paths["root"] / ".locks").exists())

    def test_guard_serializes_a_separate_process(self) -> None:
        qualification = "v32-qualification-btcusdt-guard-process"
        with TemporaryDirectory() as folder:
            project = Path(folder)
            create_v32_qualification_runtime_namespace_v1(
                project_root=project,
                qualification_run_id=qualification,
            )
            child_holds = project / "child-holds"
            release_child = project / "release-child"
            repository = Path(__file__).resolve().parents[1]
            script = """
import sys
import time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from trade_system.theory_paper_v2.presentation import v32_qualification_composition as module
module.PROJECT_ROOT = Path(sys.argv[2])
held = Path(sys.argv[3])
release = Path(sys.argv[4])
with module._qualification_composition_guard_v1(sys.argv[5]):
    held.write_text("held", encoding="utf-8")
    deadline = time.monotonic() + 10
    while not release.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("child guard release timed out")
        time.sleep(0.01)
"""
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    script,
                    str(repository),
                    str(project),
                    str(child_holds),
                    str(release_child),
                    qualification,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            parent_entered = threading.Event()
            parent_errors: list[BaseException] = []

            def parent_contender() -> None:
                try:
                    with qualification_composition._qualification_composition_guard_v1(
                        qualification
                    ):
                        parent_entered.set()
                except BaseException as exc:
                    parent_errors.append(exc)

            contender: threading.Thread | None = None
            try:
                deadline = time.monotonic() + 5
                while not child_holds.exists() and time.monotonic() < deadline:
                    if child.poll() is not None:
                        break
                    time.sleep(0.01)
                self.assertTrue(child_holds.is_file())
                with patch.object(
                    qualification_composition, "PROJECT_ROOT", project
                ):
                    contender = threading.Thread(
                        target=parent_contender, daemon=True
                    )
                    contender.start()
                    self.assertFalse(parent_entered.wait(timeout=0.2))
                    release_child.write_text("release", encoding="utf-8")
                    self.assertTrue(parent_entered.wait(timeout=5))
                    contender.join(timeout=2)
                stdout, stderr = child.communicate(timeout=5)
                self.assertEqual(0, child.returncode, (stdout, stderr))
                self.assertEqual([], parent_errors)
                self.assertIsNotNone(contender)
                self.assertFalse(contender.is_alive())
            finally:
                release_child.touch(exist_ok=True)
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=2)

    def test_guard_preserves_the_unguarded_domain_failure(self) -> None:
        target = "v32-prospective-btcusdt-guard-domain-error"
        qualification = "v32-qualification-btcusdt-guard-domain-error"
        with TemporaryDirectory() as folder:
            project = Path(folder)
            create_v32_qualification_runtime_namespace_v1(
                project_root=project,
                qualification_run_id=qualification,
            )
            with patch.object(
                qualification_composition, "PROJECT_ROOT", project
            ), patch.object(
                qualification_composition,
                "_advance_v32_qualification_once_unguarded_v1",
                side_effect=ValueError("V32_DOMAIN_FAILURE_MUST_SURVIVE"),
            ), self.assertRaisesRegex(
                ValueError, "V32_DOMAIN_FAILURE_MUST_SURVIVE"
            ):
                qualification_composition.advance_v32_qualification_once_v1(
                    target_run_id=target,
                    qualification_run_id=qualification,
                )

    def test_guard_normalizes_lock_errors_but_preserves_a_primary_failure(self) -> None:
        target = "v32-prospective-btcusdt-guard-errors"
        qualification = "v32-qualification-btcusdt-guard-errors"

        class BrokenLock:
            def __init__(self, *, fail_enter: bool) -> None:
                self.fail_enter = fail_enter

            def __enter__(self):
                if self.fail_enter:
                    raise OSError("injected lock enter failure")
                return None

            def __exit__(self, exc_type, exc, traceback):
                raise OSError("injected lock exit failure")

        with TemporaryDirectory() as folder:
            project = Path(folder)
            create_v32_qualification_runtime_namespace_v1(
                project_root=project,
                qualification_run_id=qualification,
            )
            for fail_enter in (True, False):
                helper = Mock(return_value={"status": "SHOULD_NOT_SURVIVE_EXIT"})
                with self.subTest(fail_enter=fail_enter), patch.object(
                    qualification_composition, "PROJECT_ROOT", project
                ), patch.object(
                    qualification_composition,
                    "exclusive_lock_file",
                    return_value=BrokenLock(fail_enter=fail_enter),
                ), patch.object(
                    qualification_composition,
                    "_advance_v32_qualification_once_unguarded_v1",
                    helper,
                ), self.assertRaisesRegex(
                    qualification_composition.V32QualificationCompositionError,
                    "V32_QUALIFICATION_COMPOSITION_GUARD_FAILED",
                ):
                    qualification_composition.advance_v32_qualification_once_v1(
                        target_run_id=target,
                        qualification_run_id=qualification,
                    )
                if fail_enter:
                    helper.assert_not_called()
                else:
                    helper.assert_called_once()

            with patch.object(
                qualification_composition, "PROJECT_ROOT", project
            ), patch.object(
                qualification_composition,
                "exclusive_lock_file",
                return_value=BrokenLock(fail_enter=False),
            ), patch.object(
                qualification_composition,
                "_advance_v32_qualification_once_unguarded_v1",
                side_effect=ValueError("V32_PRIMARY_DOMAIN_FAILURE"),
            ):
                with self.assertRaisesRegex(
                    ValueError, "V32_PRIMARY_DOMAIN_FAILURE"
                ) as captured:
                    qualification_composition.advance_v32_qualification_once_v1(
                        target_run_id=target,
                        qualification_run_id=qualification,
                    )
            self.assertIn(
                "V32_QUALIFICATION_COMPOSITION_GUARD_RELEASE_FAILED:OSError",
                getattr(captured.exception, "__notes__", ()),
            )

    def test_all_live_public_mutations_use_the_same_qualification_guard(self) -> None:
        target = "v32-prospective-btcusdt-guard-surface"
        qualification = "v32-qualification-btcusdt-guard-surface"
        operations = (
            (
                "_advance_v32_qualification_once_unguarded_v1",
                lambda: qualification_composition.advance_v32_qualification_once_v1(
                    target_run_id=target,
                    qualification_run_id=qualification,
                ),
            ),
            (
                "_read_and_claim_v32_qualification_agent_request_unguarded_v1",
                lambda: qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                    target_run_id=target,
                    qualification_run_id=qualification,
                ),
            ),
            (
                "_submit_v32_qualification_agent_delivery_unguarded_v1",
                lambda: qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=target,
                    qualification_run_id=qualification,
                    stage="PROPOSAL",
                    expected_request_digest="a" * 64,
                    expected_current_codex_presentation_digest="b" * 64,
                    payload_utf8="{}",
                ),
            ),
            (
                "_finalize_v32_target_authority_from_completed_qualification_unguarded_v1",
                lambda: qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1(
                    target_run_id=target,
                    qualification_run_id=qualification,
                ),
            ),
        )

        for helper_name, invoke in operations:
            observed: list[tuple[str, str]] = []

            @contextmanager
            def guard(value: str):
                observed.append(("enter", value))
                yield
                observed.append(("exit", value))

            helper = Mock(return_value={"helper": helper_name})
            with self.subTest(helper=helper_name), patch.object(
                qualification_composition,
                "_qualification_composition_guard_v1",
                side_effect=guard,
            ), patch.object(
                qualification_composition,
                helper_name,
                helper,
            ):
                self.assertEqual({"helper": helper_name}, invoke())
            self.assertEqual(
                [("enter", qualification), ("exit", qualification)],
                observed,
            )
            helper.assert_called_once()


if __name__ == "__main__":
    unittest.main()
