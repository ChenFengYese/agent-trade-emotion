from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.v32_cycle_composition import (
    run_v32_single_boundary_wake,
)
from trade_system.theory_paper_v2.application.v32_outcome_tick_composition import (
    initialize_v32_outcome_tick_runtime,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    _verify_matured_receipts,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_outcome_window_expiry import (
    build_v32_outcome_window_expiry_terminal,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.v32_local_outcome_lane import (
    LocalV32OutcomeLane,
    STORE_ROOT,
    V32LocalOutcomeLaneError,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
    V32OutcomeTickStoreError,
    build_v32_outcome_tick_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_outcome_adapter import (
    OKX_V32_MARK_PRICE_URL,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)


RUN_ID = "run:v32:local-outcome-lane"


def _schedule_set(
    *,
    cycle: int = 1,
    decision_time: str = "2026-08-07T00:00:00Z",
    scheduled_at: str = "2026-08-07T00:00:01Z",
) -> dict:
    return build_v32_outcome_schedule_set(
        run_id=RUN_ID,
        decision_id=f"decision:{cycle:04d}",
        cycle_index=cycle,
        decision_time=decision_time,
        scheduled_at=scheduled_at,
        sealed_decision_digest=str(cycle % 10) * 64,
        evaluation_contract_digest="2" * 64,
    )


def _raw_mark() -> bytes:
    return json.dumps(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": "BTC-USDT-SWAP",
                    "markPx": "65000.1",
                    "ts": "1786061701000",
                }
            ],
        },
        separators=(",", ":"),
    ).encode("utf-8")


class CapturePort:
    def __init__(
        self,
        raw: bytes | None = None,
        *,
        received_at: str = "2026-08-07T00:15:02Z",
    ) -> None:
        self.raw = _raw_mark() if raw is None else raw
        self.received_at = received_at
        self.calls = 0

    def capture_public_mark(self, *, attempt, requested_at):
        self.calls += 1
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "source_request_id": attempt["source_request_id"],
            "received_at": self.received_at,
            "captured_at": self.received_at,
            "final_url": OKX_V32_MARK_PRICE_URL,
            "http_status": 200,
            "raw_payload": self.raw,
        }


class InjectedCrash(BaseException):
    pass


class CrashAfterFirstReceiptStore(LocalV32OutcomeTickStore):
    def __init__(self, run_root: Path) -> None:
        super().__init__(run_root)
        self.crash_once = True

    def commit_outcome_receipt(self, **kwargs):
        result = super().commit_outcome_receipt(**kwargs)
        if self.crash_once:
            self.crash_once = False
            raise InjectedCrash("crash after one durable outcome receipt")
        return result


class CrashAfterExpiryCommitStore(LocalV32OutcomeTickStore):
    def __init__(self, run_root: Path) -> None:
        super().__init__(run_root)
        self.crash_once = True

    def commit_outcome_window_expiry(self, **kwargs):
        result = super().commit_outcome_window_expiry(**kwargs)
        if self.crash_once:
            self.crash_once = False
            raise InjectedCrash("crash after durable expiry aggregate commit")
        return result


class V32LocalOutcomeLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self._initialize(LocalV32OutcomeTickStore)

    def _initialize(self, store_type) -> None:
        self.outcome_store = store_type(self.root)
        outcome_genesis = build_v32_outcome_tick_checkpoint(
            run_id=RUN_ID,
            created_at="2026-08-07T00:00:00Z",
        )
        supervisor_genesis = build_v32_tick_supervisor_checkpoint(
            run_id=RUN_ID,
            experiment_contract_digest="a" * 64,
            active_authority_digest="b" * 64,
            research_checkpoint_digest="c" * 64,
            outcome_checkpoint_digest=outcome_genesis["checkpoint_digest"],
            timeframe_cache_digest="e" * 64,
            created_at="2026-08-07T00:00:00Z",
        )
        self.supervisor_store = LocalV32TickSupervisorStore(self.root)
        self.supervisor_store.initialize_checkpoint(
            checkpoint=supervisor_genesis
        )
        initialize_v32_outcome_tick_runtime(
            store=self.outcome_store,
            run_id=RUN_ID,
            created_at="2026-08-07T00:00:00Z",
            supervisor_checkpoint=supervisor_genesis,
        )
        schedule = _schedule_set()
        before = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        schedule_sets_before = self.outcome_store.load_schedule_sets(run_id=RUN_ID)
        analysis_permit = build_v32_analysis_tick_permit(
            checkpoint=before,
            schedule_sets=schedule_sets_before,
            analysis_decision_at="2026-08-07T00:00:00Z",
            issued_at="2026-08-07T00:00:01Z",
            research_checkpoint_digest=before["current_research_checkpoint_digest"],
            outcome_checkpoint_digest=before["current_outcome_checkpoint_digest"],
            timeframe_cache_digest=before["current_timeframe_cache_digest"],
            prior_dynamic_state_digest=None,
        )
        opened = self.supervisor_store.open_permit(
            permit=analysis_permit,
            schedule_sets=schedule_sets_before,
            expected_checkpoint_digest=before[CHECKPOINT_DIGEST_FIELD],
            opened_at="2026-08-07T00:00:01Z",
        )
        outcome_after_schedule = self.outcome_store.register_schedule_set(
            schedule_set=schedule,
            registered_at="2026-08-07T00:00:02Z",
        )
        self.supervisor_store.complete_analysis_tick(
            permit=analysis_permit,
            completion={
                "schedule_sets_before": schedule_sets_before,
                "new_schedule_set": schedule,
                "accepted_state_digest": "3" * 64,
                "shadow_decision_bundle_digest": "4" * 64,
                "source_admission_digest": "5" * 64,
                "source_admission_physical_sha256": "6" * 64,
                "proposal_lifecycle_digest": "7" * 64,
                "selection_lifecycle_digest": "8" * 64,
                "final_action_plan_digest": "9" * 64,
                "commit_envelope_digest": "a" * 64,
                "new_research_checkpoint_digest": "b" * 64,
                "new_outcome_checkpoint_digest": outcome_after_schedule[
                    "checkpoint_digest"
                ],
                "new_timeframe_cache_digest": "c" * 64,
                "new_dynamic_state_digest": "d" * 64,
                "completed_at": "2026-08-07T00:00:03Z",
            },
            expected_checkpoint_digest=opened[CHECKPOINT_DIGEST_FIELD],
        )
        self.schedule_sets = self.outcome_store.load_schedule_sets(run_id=RUN_ID)
        self.request = {
            "lane": "OUTCOME",
            "planned_tick_at": "2026-08-07T00:15:00Z",
            "requested_at": "2026-08-07T00:15:01Z",
        }

    def _wake(self, lane):
        return run_v32_single_boundary_wake(
            supervisor_store=self.supervisor_store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=self.schedule_sets,
            outcome_port=lane,
        )

    def test_real_local_port_opens_advances_and_completes_exact_envelope(self) -> None:
        capture = CapturePort()
        lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=capture
        )

        opened = self._wake(lane)
        self.assertEqual("SUPERVISOR_PERMIT_OPENED", opened["boundary_kind"])
        advanced = self._wake(lane)
        self.assertEqual("OUTCOME_SUBSTAGE_ADVANCED", advanced["boundary_kind"])
        self.assertEqual("COMPLETION_SEALED", advanced["lane_advance_status"])
        self.assertEqual(1, capture.calls)

        active = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID, permit_digest=active["active_permit_digest"]
        )
        envelope = lane.load_durable_outcome_completion(permit=permit)
        self.assertIsNotNone(envelope)
        verified = lane.verify_durable_outcome_completion(
            permit=permit, completion_envelope=envelope
        )
        self.assertEqual(
            verified["batch_completion_digest"],
            verified["completion"]["batch_completion"][
                "outcome_resolution_batch_digest"
            ],
        )

        completed = self._wake(lane)
        self.assertEqual("SUPERVISOR_OUTCOME_COMPLETED", completed["boundary_kind"])
        self.assertEqual("COMPLETED", completed["runtime_status"])
        checkpoint = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(1, checkpoint["terminal_outcomes"])
        self.assertEqual(1, len(verified["completion"]["outcome_receipts"]))

    def test_crash_reentry_replays_prefix_without_second_network_request(self) -> None:
        # Rebuild the same authorized state on a crash-injecting concrete store.
        self.root = Path(self.directory.name) / "crash-runtime"
        self.root.mkdir()
        self._initialize(CrashAfterFirstReceiptStore)
        capture = CapturePort()
        lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=capture
        )
        self._wake(lane)
        with self.assertRaises(InjectedCrash):
            self._wake(lane)
        self.assertEqual(1, capture.calls)
        prefix = self.outcome_store.tick_prefix(run_id=RUN_ID, tick_index=1)
        self.assertIsNotNone(prefix["batch_intent"])
        self.assertIsNone(prefix["batch_completion"])

        recovered = self._wake(lane)
        self.assertEqual("COMPLETION_SEALED", recovered["lane_advance_status"])
        self.assertEqual(1, capture.calls)
        completed = self._wake(lane)
        self.assertEqual("COMPLETED", completed["runtime_status"])

    def test_completion_envelope_tamper_is_rejected_by_full_replay(self) -> None:
        capture = CapturePort()
        lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=capture
        )
        self._wake(lane)
        self._wake(lane)
        active = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID, permit_digest=active["active_permit_digest"]
        )
        envelope = lane.load_durable_outcome_completion(permit=permit)
        tampered = deepcopy(envelope)
        tampered["completion"]["new_outcome_checkpoint_digest"] = "f" * 64
        with self.assertRaisesRegex(
            V32LocalOutcomeLaneError, "DURABILITY_MISMATCH"
        ):
            lane.verify_durable_outcome_completion(
                permit=permit, completion_envelope=tampered
            )

        # External physical mutation is also caught against the replayed store.
        path = (
            self.root
            / STORE_ROOT
            / "permits"
            / permit["tick_supervisor_permit_digest"]
            / "completion-envelope.json"
        )
        path.write_bytes(canonical_bytes(tampered) + b"\n")
        durable_tamper = lane.load_durable_outcome_completion(permit=permit)
        with self.assertRaisesRegex(
            V32LocalOutcomeLaneError, "REPLAY_MISMATCH"
        ):
            lane.verify_durable_outcome_completion(
                permit=permit, completion_envelope=durable_tamper
            )

    def test_completion_replays_after_later_outcome_checkpoint_advance(self) -> None:
        lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=CapturePort()
        )
        self._wake(lane)
        self._wake(lane)
        active = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID, permit_digest=active["active_permit_digest"]
        )
        envelope = lane.load_durable_outcome_completion(permit=permit)
        sealed_checkpoint_digest = envelope["completion"][
            "new_outcome_checkpoint_digest"
        ]

        self._wake(lane)  # close tick 1 in the Supervisor before tick 2
        self.request = {
            "lane": "OUTCOME",
            "planned_tick_at": "2026-08-07T04:00:00Z",
            "requested_at": "2026-08-07T04:00:01Z",
        }
        later_lane = LocalV32OutcomeLane(
            store=self.outcome_store,
            capture_port=CapturePort(received_at="2026-08-07T04:00:02Z"),
        )
        self._wake(later_lane)
        self._wake(later_lane)
        self.assertNotEqual(
            sealed_checkpoint_digest,
            self.outcome_store.load_checkpoint(run_id=RUN_ID)["checkpoint_digest"],
        )
        replayed = lane.verify_durable_outcome_completion(
            permit=permit, completion_envelope=envelope
        )
        self.assertEqual(
            sealed_checkpoint_digest,
            replayed["completion"]["new_outcome_checkpoint_digest"],
        )

    def test_future_schedule_is_not_read_or_resolved(self) -> None:
        capture = CapturePort()
        lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=capture
        )
        self._wake(lane)
        active = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID, permit_digest=active["active_permit_digest"]
        )
        self.assertEqual(2, len(permit["future_schedule_ids"]))
        future_id = permit["future_schedule_ids"][0]
        self._wake(lane)
        envelope = lane.load_durable_outcome_completion(permit=permit)
        resolved = {
            row["schedule_id"]
            for row in envelope["completion"]["outcome_receipts"]
        }
        self.assertNotIn(future_id, resolved)
        self.assertEqual(set(permit["due_schedule_ids"]), resolved)
        self.assertEqual(1, capture.calls)

    def test_structural_failure_is_write_once_and_never_retried(self) -> None:
        capture = CapturePort(raw=b'{"code":"0","data":[')
        lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=capture
        )
        self._wake(lane)
        sealed = self._wake(lane)
        self.assertEqual("FAILURE_SEALED", sealed["lane_advance_status"])
        self.assertEqual(1, capture.calls)
        active = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID, permit_digest=active["active_permit_digest"]
        )
        failure = lane.load_durable_outcome_failure(permit=permit)
        lane.verify_durable_outcome_failure(
            permit=permit, failure_envelope=failure
        )

        completed = self._wake(lane)
        self.assertEqual("FAILED_CLOSED", completed["runtime_status"])
        self.assertEqual(1, capture.calls)
        self.assertEqual(
            "FAILED_CLOSED",
            self.supervisor_store.load_checkpoint(run_id=RUN_ID)["status"],
        )

    def test_not_due_is_durable_pending_not_completion(self) -> None:
        capture = CapturePort()
        runner_calls = []

        def not_due_runner(**kwargs):
            runner_calls.append(kwargs["tick_index"])
            checkpoint = kwargs["store"].load_checkpoint(run_id=RUN_ID)
            return {
                "run_id": RUN_ID,
                "tick_index": kwargs["tick_index"],
                "runtime_status": "NOT_DUE",
                "network_request_count": 0,
                "checkpoint_digest": checkpoint["checkpoint_digest"],
                "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            }

        lane = LocalV32OutcomeLane(
            store=self.outcome_store,
            capture_port=capture,
            transaction_runner=not_due_runner,
        )
        self._wake(lane)
        pending = self._wake(lane)
        self.assertEqual("PENDING", pending["lane_advance_status"])
        self.assertEqual(0, capture.calls)
        self.assertEqual([1], runner_calls)
        active = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID, permit_digest=active["active_permit_digest"]
        )
        self.assertIsNone(lane.load_durable_outcome_completion(permit=permit))
        self.assertIsNone(lane.load_durable_outcome_failure(permit=permit))

        repeated = self._wake(lane)
        self.assertEqual("PENDING", repeated["lane_advance_status"])
        self.assertEqual([1], runner_calls)
        self.assertEqual(0, capture.calls)

    def test_expired_window_is_zero_network_durable_and_idempotent(self) -> None:
        self.request = {
            "lane": "OUTCOME",
            "planned_tick_at": "2026-08-07T00:15:00Z",
            "requested_at": "2026-08-07T04:15:00.000001Z",
        }
        capture = CapturePort()
        lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=capture
        )
        outcome_before = self.outcome_store.load_checkpoint(run_id=RUN_ID)

        opened = self._wake(lane)
        self.assertEqual("SUPERVISOR_PERMIT_OPENED", opened["boundary_kind"])
        active = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID, permit_digest=active["active_permit_digest"]
        )
        self.assertEqual("OUTCOME_WINDOW_EXPIRY", permit["permit_kind"])
        self.assertEqual(0, permit["network_requests_allowed"])
        self.assertIsNone(permit["tick_attempt_digest"])

        advanced = self._wake(lane)
        self.assertEqual("OUTCOME_SUBSTAGE_ADVANCED", advanced["boundary_kind"])
        self.assertEqual("COMPLETION_SEALED", advanced["lane_advance_status"])
        self.assertEqual(0, capture.calls)
        outcome_after = self.outcome_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(
            outcome_before["attempt_bindings"], outcome_after["attempt_bindings"]
        )
        self.assertEqual(1, len(outcome_after["expiry_terminal_bindings"]))
        terminal_receipts = self.outcome_store.load_terminal_receipts(
            run_id=RUN_ID
        )
        self.assertEqual(3, len(terminal_receipts))
        self.assertTrue(
            all(
                receipt["resolution_status"] == "UNKNOWN_COVERAGE_LOSS"
                and receipt["coverage_loss_reason"]
                == "OBSERVATION_WINDOW_MISSED"
                and receipt["attempt_count"] == 0
                for receipt in terminal_receipts
            )
        )
        materials = self.outcome_store.load_terminal_receipt_materials(
            run_id=RUN_ID
        )
        self.assertEqual(3, len(materials))
        self.assertEqual(
            "EXPIRY_AGGREGATE_MEMBER",
            materials[0]["receipt_binding"]["binding_kind"],
        )
        self.assertEqual(
            1,
            sum(
                "aggregate_document" in material["receipt_binding"]
                for material in materials
            ),
        )
        matured, matured_bindings = _verify_matured_receipts(
            receipts=[material["receipt"] for material in materials],
            bindings=[material["receipt_binding"] for material in materials],
            run_id=RUN_ID,
            cycle_index=2,
            decision_time="2026-08-07T04:15:00.000001Z",
        )
        self.assertEqual(terminal_receipts, matured)
        self.assertEqual(
            "EXPIRY_AGGREGATE_MEMBER",
            matured_bindings[0]["binding_kind"],
        )
        self.assertTrue(
            all(
                binding["binding_kind"] == "EXPIRY_AGGREGATE_MEMBER_REF"
                for binding in matured_bindings[1:]
            )
        )

        predecessor = self.supervisor_store.load_checkpoint_by_digest(
            run_id=RUN_ID,
            checkpoint_digest=active["predecessor_checkpoint_digest"],
        )
        repeated = lane.advance_outcome(
            permit=permit,
            supervisor_checkpoint_before_permit=predecessor,
            supervisor_open_checkpoint=active,
        )
        self.assertEqual("COMPLETION_SEALED", repeated["advance_status"])
        self.assertEqual(0, capture.calls)
        replayed_outcome = self.outcome_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(
            outcome_after["checkpoint_digest"], replayed_outcome["checkpoint_digest"]
        )
        self.assertEqual(1, len(replayed_outcome["expiry_terminal_bindings"]))

        wrong_cas = "f" * 64
        second_terminal = build_v32_outcome_window_expiry_terminal(
            run_id=RUN_ID,
            classified_at="2026-08-07T01:15:00.000001Z",
            schedule_sets=self.schedule_sets,
            prior_terminal_schedule_ids=[],
            permit_digest=permit["tick_supervisor_permit_digest"],
            supervisor_checkpoint_digest_before_permit=active[
                CHECKPOINT_DIGEST_FIELD
            ],
            outcome_checkpoint_digest_before=wrong_cas,
            experiment_contract_digest=permit["experiment_contract_digest"],
            active_authority_digest=permit["active_authority_digest"],
        )
        with self.assertRaisesRegex(
            V32OutcomeTickStoreError, "V32_TICK_STORE_CAS_CONFLICT"
        ):
            self.outcome_store.commit_outcome_window_expiry(
                run_id=RUN_ID,
                expiry_terminal=second_terminal,
                expected_checkpoint_digest=wrong_cas,
            )
        cas_failed_outcome = self.outcome_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(
            outcome_after["checkpoint_digest"],
            cas_failed_outcome["checkpoint_digest"],
        )
        self.assertEqual(1, len(cas_failed_outcome["expiry_terminal_bindings"]))
        self.assertEqual(0, capture.calls)

        completed = self._wake(lane)
        self.assertEqual("SUPERVISOR_OUTCOME_COMPLETED", completed["boundary_kind"])
        self.assertEqual("COMPLETED", completed["runtime_status"])
        supervisor_after = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(3, supervisor_after["terminal_outcomes"])
        self.assertEqual(1, supervisor_after["next_outcome_tick_index"])
        self.assertEqual(0, capture.calls)

    def test_expiry_commit_reloads_after_process_interrupt_without_second_write(
        self,
    ) -> None:
        self.root = Path(self.directory.name) / "expiry-crash-runtime"
        self.root.mkdir()
        self._initialize(CrashAfterExpiryCommitStore)
        self.request = {
            "lane": "OUTCOME",
            "planned_tick_at": "2026-08-07T00:15:00Z",
            "requested_at": "2026-08-07T04:15:00.000001Z",
        }
        first_capture = CapturePort()
        first_lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=first_capture
        )
        self._wake(first_lane)
        supervisor_open = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        permit = self.supervisor_store.load_permit(
            run_id=RUN_ID,
            permit_digest=supervisor_open["active_permit_digest"],
        )
        with self.assertRaises(InjectedCrash):
            self._wake(first_lane)
        self.assertEqual(0, first_capture.calls)

        committed = self.outcome_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(1, len(committed["expiry_terminal_bindings"]))
        aggregate_binding = committed["expiry_terminal_bindings"][0]
        aggregate_path = self.root / aggregate_binding["relative_ref"]
        checkpoint_path = self.root / "outcome-v32/checkpoint.json"
        aggregate_bytes = aggregate_path.read_bytes()
        checkpoint_bytes = checkpoint_path.read_bytes()
        aggregate_mtime = aggregate_path.stat().st_mtime_ns
        checkpoint_mtime = checkpoint_path.stat().st_mtime_ns
        completion_path = (
            self.root
            / STORE_ROOT
            / "permits"
            / permit["tick_supervisor_permit_digest"]
            / "completion-envelope.json"
        )
        self.assertFalse(completion_path.exists())

        self.outcome_store = LocalV32OutcomeTickStore(self.root)
        self.supervisor_store = LocalV32TickSupervisorStore(self.root)
        self.schedule_sets = self.outcome_store.load_schedule_sets(run_id=RUN_ID)
        second_capture = CapturePort()
        recovered_lane = LocalV32OutcomeLane(
            store=self.outcome_store, capture_port=second_capture
        )
        history_root = self.root / "v32-tick-supervisor-v1/checkpoints"
        history_before_recovery = sorted(history_root.glob("*.json"))

        recovered = self._wake(recovered_lane)
        self.assertEqual("OUTCOME_SUBSTAGE_ADVANCED", recovered["boundary_kind"])
        self.assertEqual("COMPLETION_SEALED", recovered["lane_advance_status"])
        self.assertEqual(0, second_capture.calls)
        replayed = self.outcome_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(committed["checkpoint_digest"], replayed["checkpoint_digest"])
        self.assertEqual(1, len(replayed["expiry_terminal_bindings"]))
        self.assertEqual(aggregate_bytes, aggregate_path.read_bytes())
        self.assertEqual(checkpoint_bytes, checkpoint_path.read_bytes())
        self.assertEqual(aggregate_mtime, aggregate_path.stat().st_mtime_ns)
        self.assertEqual(checkpoint_mtime, checkpoint_path.stat().st_mtime_ns)
        self.assertTrue(completion_path.is_file())
        self.assertEqual(history_before_recovery, sorted(history_root.glob("*.json")))

        before_terminal = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        completed = self._wake(recovered_lane)
        self.assertEqual("SUPERVISOR_OUTCOME_COMPLETED", completed["boundary_kind"])
        self.assertEqual("COMPLETED", completed["runtime_status"])
        after_terminal = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(before_terminal["revision"] + 1, after_terminal["revision"])
        self.assertEqual(3, after_terminal["terminal_outcomes"])
        self.assertIsNone(after_terminal["active_permit_digest"])
        self.assertEqual(
            len(history_before_recovery) + 1,
            len(list(history_root.glob("*.json"))),
        )
        reloaded_terminal = LocalV32TickSupervisorStore(self.root).load_checkpoint(
            run_id=RUN_ID
        )
        self.assertEqual(
            after_terminal[CHECKPOINT_DIGEST_FIELD],
            reloaded_terminal[CHECKPOINT_DIGEST_FIELD],
        )
        self.assertEqual(0, second_capture.calls)


if __name__ == "__main__":
    unittest.main()
