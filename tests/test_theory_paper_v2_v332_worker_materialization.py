from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.controller_state import (
    ControllerStateError,
    FileControllerState,
)


class CountingClock:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls = 0
        self.fail = False

    def __call__(self) -> str:
        self.calls += 1
        if self.fail:
            raise AssertionError("clock must not be read for an existing task")
        return self.value


class WorkerMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "run-materialize"
        self.root.mkdir()
        self.cycle_id = "cycle-1"
        transport = self.root / "cycles" / self.cycle_id / "transport"
        transport.mkdir(parents=True)
        self.identity = {
            "run_id": self.root.name,
            "run_manifest_identity_sha256": "1" * 64,
            "run_manifest_raw_sha256": "2" * 64,
            "theory_manifest_sha256": "3" * 64,
            "implementation_sha256": "4" * 64,
            "contract_identity": "V332_TEST_CONTRACT",
            "market_contract_identity": "OKX:HYPE-USDT-SWAP",
            "experiment_identity": "5" * 64,
        }
        packet = {
            "cycle_id": self.cycle_id,
            "theory_identity": {"manifest_digest": "3" * 64},
            "input_snapshot": {"sealed_at": "2026-08-13T00:00:00+00:00"},
            "decision_deadline_at": "2026-08-13T01:00:00+00:00",
            "time_budget_seconds": 600,
        }
        request = {
            "schema_id": "agent_trade_emotion_market_cycle_agent_decision_request",
            "schema_version": "1.0.0",
            "cycle_id": self.cycle_id,
            "packet": packet,
            "packet_sha256": hashlib.sha256(canonical_bytes(packet)).hexdigest(),
            "packet_size_bytes": len(canonical_bytes(packet)),
        }
        (transport / "agent-request.json").write_bytes(
            canonical_bytes(request) + b"\n"
        )
        binding = {
            "schema_id": "agent_trade_emotion_v331_cycle_run_binding",
            "schema_version": "1.0.0",
            "cycle_id": self.cycle_id,
            "run_manifest_identity_sha256": "1" * 64,
            "run_id": self.root.name,
            "theory_manifest_sha256": "3" * 64,
            "implementation_sha256": "4" * 64,
            "contract_identity": "V332_TEST_CONTRACT",
            "market_contract_identity": "OKX:HYPE-USDT-SWAP",
            "experiment_identity": "5" * 64,
        }
        (transport / "run-binding.json").write_bytes(
            canonical_bytes(binding) + b"\n"
        )
        self.clock = CountingClock("2026-08-13T00:05:00+00:00")
        self.state = FileControllerState(
            self.root,
            **self.identity,
            clock=self.clock,
        )

    def _complete_decision_worker(self, execution_ref: str) -> None:
        task_path = self.state.materialize_worker_task(
            self.cycle_id, "decision-v1"
        )
        prepared = self.state.prepare_worker(
            self.cycle_id, "decision-v1", task_path
        )
        dispatch_id = str(prepared["dispatch_id"])
        self.state.mark_spawn_requested(
            self.cycle_id, "decision-v1", dispatch_id
        )
        self.state.acknowledge_spawn(
            self.cycle_id,
            "decision-v1",
            dispatch_id,
            execution_ref,
        )
        task = loads_json_strict(task_path.read_bytes())
        body = "Hold cash while waiting for a better asymmetric setup."
        result = {
            "schema_id": "agent_trade_emotion_v331_worker_result",
            "schema_version": "1.0.0",
            "run_id": self.root.name,
            "cycle_id": self.cycle_id,
            "worker_id": "decision-v1",
            "status": "COMPLETED",
            "started_at": "2026-08-13T00:05:00+00:00",
            "completed_at": "2026-08-13T00:05:20+00:00",
            "elapsed_seconds": 20,
            "input_refs": task["input_refs"],
            "body_markdown": body,
        }
        (task_path.parent / "result.json").write_bytes(
            canonical_bytes(result) + b"\n"
        )
        request = loads_json_strict(
            (
                self.root
                / "cycles"
                / self.cycle_id
                / "transport"
                / "agent-request.json"
            ).read_bytes()
        )
        body_raw = body.encode("utf-8")
        delivery = {
            "schema_id": (
                "agent_trade_emotion_market_cycle_agent_decision_delivery"
            ),
            "schema_version": "1.0.0",
            "cycle_id": self.cycle_id,
            "request_sha256": request["packet_sha256"],
            "theory_identity": request["packet"]["theory_identity"],
            "delivered_at": "2026-08-13T00:05:20+00:00",
            "media_type": "text/markdown",
            "encoding": "UTF-8",
            "decision_size_bytes": len(body_raw),
            "decision_sha256": hashlib.sha256(body_raw).hexdigest(),
            "decision_text": body,
        }
        delivery_raw = canonical_bytes(delivery) + b"\n"
        (
            self.root
            / "cycles"
            / self.cycle_id
            / "transport"
            / "agent-delivery.json"
        ).write_bytes(delivery_raw)
        self.clock.value = "2026-08-13T00:05:30+00:00"
        self.state.complete_worker(
            self.cycle_id,
            "decision-v1",
            dispatch_id,
            hashlib.sha256(delivery_raw).hexdigest(),
        )

    def test_task_is_derived_and_repeated_materialization_is_byte_identical(self) -> None:
        task_path = self.state.materialize_worker_task(
            self.cycle_id, "decision-v1"
        )
        first = task_path.read_bytes()
        task = loads_json_strict(first)
        receipt_path = task_path.parent / "controller-task-receipt.json"
        receipt = loads_json_strict(receipt_path.read_bytes())
        self.assertEqual(
            hashlib.sha256(first).hexdigest(), receipt["task_sha256"]
        )
        self.assertEqual(task["run_id"], self.root.name)
        self.assertEqual(task["experiment_identity"], "5" * 64)
        self.assertEqual(task["schema_version"], "2.0.0")
        self.assertEqual(
            task["result_contract"]["exact_fields"],
            [
                "schema_id",
                "schema_version",
                "run_id",
                "cycle_id",
                "worker_id",
                "status",
                "started_at",
                "completed_at",
                "elapsed_seconds",
                "input_refs",
                "body_markdown",
            ],
        )
        self.assertFalse(
            task["result_contract"]["input_refs"][
                "additional_fields_allowed"
            ]
        )
        self.assertEqual(
            task["result_contract"]["timing"]["frozen_deadline_at"],
            "2026-08-13T00:15:00+00:00",
        )
        self.assertEqual(
            task["timing"],
            {
                "created_at": "2026-08-13T00:05:00+00:00",
                "not_before_at": "2026-08-13T00:00:00+00:00",
                "frozen_deadline_at": "2026-08-13T00:15:00+00:00",
                "hard_stop_seconds": 600,
            },
        )
        self.assertEqual(self.clock.calls, 1)

        self.clock.fail = True
        repeated = self.state.materialize_worker_task(
            self.cycle_id, "decision-v1"
        )
        self.assertEqual(repeated, task_path)
        self.assertEqual(repeated.read_bytes(), first)
        self.assertEqual(self.clock.calls, 1)

    def test_existing_task_without_controller_receipt_is_rejected(self) -> None:
        task_path = self.state.materialize_worker_task(
            self.cycle_id, "decision-v1"
        )
        (task_path.parent / "controller-task-receipt.json").unlink()
        self.clock.fail = True
        with self.assertRaisesRegex(
            ControllerStateError,
            "CONTROLLER_WORKER_TASK_RECEIPT_MISSING_OR_INVALID",
        ):
            self.state.materialize_worker_task(
                self.cycle_id, "decision-v1"
            )

    def test_daily_deep_deadline_is_truncated_to_request_hard_stop(self) -> None:
        task_path = self.state.materialize_worker_task(
            self.cycle_id, "daily-deep-v1"
        )
        task = loads_json_strict(task_path.read_bytes())
        self.assertEqual(
            {
                "created_at": "2026-08-13T00:05:00+00:00",
                "not_before_at": "2026-08-13T00:00:00+00:00",
                "frozen_deadline_at": "2026-08-13T00:15:00+00:00",
                "hard_stop_seconds": 600,
            },
            task["timing"],
        )

    def test_named_legacy_experiment_identity_gets_deterministic_task_digest(self) -> None:
        legacy_root = self.root.parent / "legacy-named-run"
        legacy_root.mkdir()
        shutil.copytree(self.root / "cycles", legacy_root / "cycles")
        binding_path = (
            legacy_root
            / "cycles"
            / self.cycle_id
            / "transport"
            / "run-binding.json"
        )
        binding = loads_json_strict(binding_path.read_bytes())
        binding["run_id"] = legacy_root.name
        binding["experiment_identity"] = "V332_OFFLINE_SYSTEM_FEASIBILITY"
        binding_path.write_bytes(canonical_bytes(binding) + b"\n")
        identity = {
            **self.identity,
            "run_id": legacy_root.name,
            "experiment_identity": "V332_OFFLINE_SYSTEM_FEASIBILITY",
        }
        state = FileControllerState(
            legacy_root,
            **identity,
            clock=CountingClock("2026-08-13T00:05:00+00:00"),
        )
        task = loads_json_strict(
            state.materialize_worker_task(
                self.cycle_id, "decision-v1"
            ).read_bytes()
        )
        self.assertEqual(
            hashlib.sha256(
                b"V332_OFFLINE_SYSTEM_FEASIBILITY"
            ).hexdigest(),
            task["identities"]["experiment_contract_sha256"],
        )

    def test_caller_has_no_identity_deadline_or_write_boundary_parameters(self) -> None:
        with self.assertRaises(TypeError):
            self.state.materialize_worker_task(  # type: ignore[call-arg]
                self.cycle_id,
                "decision-v1",
                run_id="forged-run",
            )

        binding_path = (
            self.root / "cycles" / self.cycle_id / "transport" / "run-binding.json"
        )
        binding = loads_json_strict(binding_path.read_bytes())
        binding["run_id"] = "forged-run"
        binding_path.write_bytes(canonical_bytes(binding) + b"\n")
        with self.assertRaisesRegex(
            ControllerStateError, "CONTROLLER_RUN_BINDING_INVALID"
        ):
            self.state.materialize_worker_task(self.cycle_id, "decision-v1")

    def test_paper_action_is_not_a_controller_worker(self) -> None:
        with self.assertRaisesRegex(
            ControllerStateError, "CONTROLLER_WORKER_ID_INVALID"
        ):
            self.state.materialize_worker_task(
                self.cycle_id, "paper-action-v1"
            )

if __name__ == "__main__":
    unittest.main()
