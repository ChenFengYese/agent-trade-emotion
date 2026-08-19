from __future__ import annotations

import inspect
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from trade_system.theory_paper_v2.application.v32_prospective_runtime import (
    initialize_v32_prospective_runtime_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    RUNTIME_MANIFEST_DIGEST_FIELD,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.infrastructure.v32_dynamic_store import (
    LocalV32DynamicStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)
from trade_system.theory_paper_v2.infrastructure import v32_read_only_status as status
from trade_system.theory_paper_v2.presentation import (
    v32_target_wake_composition as composition,
)


RUN_ID = "v32-read-status-test"
CREATED_AT = "2026-08-10T00:00:00Z"


def _policy() -> dict:
    return build_v32_cycle_audit_policy_v1(
        policy_id="v32-read-status-test-policy",
        run_scope_id=RUN_ID,
        frozen_at=CREATED_AT,
    )


def _initialize(run_root: Path) -> None:
    initialize_v32_prospective_runtime_v1(
        dynamic_store=LocalV32DynamicStore(run_root),
        outcome_store=LocalV32OutcomeTickStore(run_root),
        supervisor_store=LocalV32TickSupervisorStore(run_root),
        run_id=RUN_ID,
        experiment_contract_digest="a" * 64,
        active_authority_digest="b" * 64,
        initial_timeframe_cache_digest="c" * 64,
        cycle_audit_policy=_policy(),
        created_at=CREATED_AT,
    )


def _tree_bytes(root: Path) -> dict[str, bytes | None]:
    result: dict[str, bytes | None] = {".": None}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        result[relative] = path.read_bytes() if path.is_file() else None
    return result


class _Clock:
    adapter_id = "V32_TEST_SYSTEM_UTC"

    def __call__(self) -> str:
        return "2026-08-10T00:01:00Z"


class V32ReadOnlyStatusTests(unittest.TestCase):
    def test_genesis_status_is_byte_for_byte_read_only_and_mailbox_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "run"
            run_root.mkdir()
            _initialize(run_root)
            before = _tree_bytes(run_root)

            result = status.read_v32_read_only_status_snapshot_v1(
                run_root=run_root,
                run_id=RUN_ID,
                observed_at="2026-08-10T00:01:00Z",
            )

            self.assertEqual(before, _tree_bytes(run_root))
            self.assertEqual("STABLE", result["status"])
            self.assertEqual("READY", result["current_boundary"])
            self.assertEqual("TARGET_WAKE_ONCE", result["next_legal_action"])
            self.assertEqual(
                "NOT_INITIALIZED",
                result["boundaries"]["mailbox"]["status"],
            )
            self.assertFalse(result["same_process_poll_required"])
            self.assertFalse(result["outcome_values_read"])
            self.assertEqual(0, result["state_mutation_count"])
            self.assertEqual(0, result["network_request_count"])

    def test_schedule_projection_keeps_four_timing_states_at_arbitrary_seconds(self) -> None:
        first = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision-1",
            cycle_index=1,
            decision_time="2026-08-10T00:00:00.123000Z",
            scheduled_at="2026-08-10T00:00:01.123000Z",
            sealed_decision_digest="d" * 64,
            evaluation_contract_digest="e" * 64,
        )
        second = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision-2",
            cycle_index=2,
            decision_time="2026-08-10T00:15:10.123000Z",
            scheduled_at="2026-08-10T00:15:11.123000Z",
            sealed_decision_digest="f" * 64,
            evaluation_contract_digest="1" * 64,
        )
        rows = status.project_v32_outcome_schedule_states_v1(
            schedule_sets=[first, second],
            terminal_schedule_ids=[first["schedules"][0]["schedule_id"]],
            observed_at="2026-08-10T01:15:00.123000Z",
        )
        self.assertEqual(
            {"FUTURE", "DUE", "EXPIRED", "TERMINAL"},
            {row["state"] for row in rows},
        )
        self.assertTrue(all("value" not in row for row in rows))
        expired_schedule_id = next(
            row["schedule_id"] for row in rows if row["state"] == "EXPIRED"
        )
        self.assertEqual(
            "TARGET_WAKE_ONCE_FAIL_CLOSE_EXPIRED_OUTCOME_TICK",
            status._next_legal_action(
                supervisor_status="OUTCOME_TICK_OPEN",
                permit_kind="OUTCOME_TICK",
                analysis_window_open=None,
                active_stage_status=None,
                active_due_schedule_ids=[expired_schedule_id],
                outcome_states=rows,
            ),
        )

    def test_changed_mutable_head_returns_busy_without_mutation(self) -> None:
        regular_heads = (
            ("supervisor", status.SUPERVISOR_HEAD_REF),
            ("dynamic", status.DYNAMIC_HEAD_REF),
            ("outcome", status.OUTCOME_HEAD_REF),
        )
        for label, relative_ref in regular_heads:
            with self.subTest(head=label), tempfile.TemporaryDirectory() as directory:
                run_root = Path(directory) / "run"
                run_root.mkdir()
                _initialize(run_root)
                before = _tree_bytes(run_root)
                original = status._read_regular_bytes
                target = (run_root / relative_ref).resolve()
                calls = 0

                def unstable(path: Path) -> bytes:
                    nonlocal calls
                    payload = original(path)
                    if path == target:
                        calls += 1
                        if calls == 2:
                            return payload + b" "
                    return payload

                with mock.patch.object(
                    status, "_read_regular_bytes", side_effect=unstable
                ):
                    result = status.read_v32_read_only_status_snapshot_v1(
                        run_root=run_root,
                        run_id=RUN_ID,
                        observed_at="2026-08-10T00:01:00Z",
                    )
                self.assertEqual("BUSY_UNSTABLE", result["status"])
                self.assertEqual("READ_STATUS_AGAIN", result["next_legal_action"])
                self.assertEqual(before, _tree_bytes(run_root))

        with self.subTest(head="mailbox-absent-to-created"):
            with tempfile.TemporaryDirectory() as directory:
                run_root = Path(directory) / "run"
                run_root.mkdir()
                _initialize(run_root)
                before = _tree_bytes(run_root)
                calls = 0

                def mailbox_created(_: Path) -> bytes | None:
                    nonlocal calls
                    calls += 1
                    return None if calls == 1 else b"created"

                with mock.patch.object(
                    status,
                    "_read_optional_regular_bytes",
                    side_effect=mailbox_created,
                ):
                    result = status.read_v32_read_only_status_snapshot_v1(
                        run_root=run_root,
                        run_id=RUN_ID,
                        observed_at="2026-08-10T00:01:00Z",
                    )
                self.assertEqual("BUSY_UNSTABLE", result["status"])
                self.assertEqual("READ_STATUS_AGAIN", result["next_legal_action"])
                self.assertEqual(before, _tree_bytes(run_root))

    def test_public_entry_uses_full_loader_and_fixed_system_clock(self) -> None:
        self.assertEqual(
            ["project_root", "expected_run_id"],
            list(inspect.signature(composition.read_v32_target_status_v1).parameters),
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            run_root = project / "run"
            run_root.mkdir()
            manifest = {
                "qualification_run_id": "v32-qualification-test",
                "manifest_id": "manifest-test",
                "schema_version": "2.0.0",
                RUNTIME_MANIFEST_DIGEST_FIELD: "9" * 64,
            }
            replay = {"authority_projection": {"manifest": manifest}}
            projected = {"run_id": RUN_ID, "status": "STABLE"}
            with (
                mock.patch.object(
                    composition,
                    "_load_verified_target_context",
                    return_value=(project, replay, run_root),
                ) as loader,
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_Clock(),
                ),
                mock.patch.object(
                    composition,
                    "read_v32_read_only_status_snapshot_v1",
                    return_value=projected,
                ) as reader,
                mock.patch.object(
                    composition,
                    "LocalV32RunControlStore",
                    side_effect=AssertionError("status must not create a lock"),
                ),
            ):
                result = composition.read_v32_target_status_v1(
                    project_root=project, expected_run_id=RUN_ID
                )
            loader.assert_called_once_with(
                project_root=project, expected_run_id=RUN_ID
            )
            reader.assert_called_once_with(
                run_root=run_root,
                run_id=RUN_ID,
                observed_at="2026-08-10T00:01:00Z",
            )
            self.assertEqual("v32-qualification-test", result["qualification_run_id"])
            self.assertEqual("V3.2", result["engine_version"]["theory"])
            self.assertTrue(result["full_authority_and_genesis_replayed"])


if __name__ == "__main__":
    unittest.main()
