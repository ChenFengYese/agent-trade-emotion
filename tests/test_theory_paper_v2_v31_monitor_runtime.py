from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tests.test_theory_paper_v2_v31_durable_bundle import completed_cycle_fixture
from trade_system.theory_paper_v2.application.v31_durable_cycle import (
    persist_completed_v31_cycle,
)
from trade_system.theory_paper_v2.application.v31_monitor_runtime import (
    V31MonitorRuntimeError,
    initialize_v31_monitor_runtime,
    resolve_due_v31_monitor,
    schedule_v31_monitor_plan,
    v31_monitor_status,
)
from trade_system.theory_paper_v2.application.v31_research_cycle import (
    verify_v31_accepted_state,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
    ObservationMissingness,
    ObservationQuality,
    OutcomeObservation,
    build_minimal_experiment_contract,
    build_path_outcome_receipt,
    build_typed_path_monitor_plan,
)
from trade_system.theory_paper_v2.domain.v31_monitor_runtime import (
    PublicOutcomeReading,
)
from trade_system.theory_paper_v2.infrastructure.v31_monitor_store import (
    LocalV31MonitorStore,
    V31MonitorStoreError,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)


RUN_ID = "run:v31"
DECISION_AT = "2026-08-06T10:00:00Z"
PUBLIC_MARK_URL = (
    "https://www.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)


def monitor_rules() -> tuple[FrozenMonitorRule, ...]:
    observable = "metric:mark-price-change-at-1h-horizon"
    return (
        FrozenMonitorRule(
            rule_id="confirm-positive",
            role=MonitorRuleRole.CONFIRMATION,
            observable_ref=observable,
            operator=MonitorOperator.GT,
            expected="0",
            unit="PERCENT",
        ),
        FrozenMonitorRule(
            rule_id="contradict-negative",
            role=MonitorRuleRole.CONTRADICTION,
            observable_ref=observable,
            operator=MonitorOperator.LT,
            expected="0",
            unit="PERCENT",
        ),
        FrozenMonitorRule(
            rule_id="falsify-large-loss",
            role=MonitorRuleRole.FALSIFIER,
            observable_ref=observable,
            operator=MonitorOperator.LTE,
            expected="-5",
            unit="PERCENT",
        ),
    )


def origins(accepted: dict, *, cycle_index: int) -> dict[str, dict[str, str]]:
    return {
        "accepted_state": {
            "ref": f"cycles/{cycle_index:04d}/accepted-research-state.json",
            "digest": accepted["accepted_state_digest"],
        },
        "path_set": {
            "ref": f"scenario-path-set:{cycle_index}",
            "digest": accepted["scenario_path_set_digest"],
        },
        "path": {"ref": f"path:lead:{cycle_index}", "digest": "b" * 64},
        "hypothesis_revision": {
            "ref": f"hypothesis:lead:r{cycle_index}",
            "digest": "c" * 64,
        },
        "expectation_revision": {
            "ref": f"expectation:lead:r{cycle_index}",
            "digest": "d" * 64,
        },
    }


def monitor_plan(contract: dict, accepted: dict) -> dict:
    cycle_index = accepted["cycle_index"]
    return build_typed_path_monitor_plan(
        experiment_contract=contract,
        monitor_plan_id=f"monitor:{cycle_index}",
        cycle_id=f"cycle:{cycle_index}",
        cycle_index=cycle_index,
        origin_bindings=origins(accepted, cycle_index=cycle_index),
        decision_at=accepted["decision_at"],
        observable_ref="metric:mark-price-change-at-1h-horizon",
        source_request_id=f"okx-public-mark-price:{cycle_index}",
        rules=monitor_rules(),
    )


class FakePublicObservationAdapter:
    def __init__(
        self,
        *,
        value: str | None = "1.25",
        missingness: ObservationMissingness = ObservationMissingness.OBSERVED,
        quality: ObservationQuality = ObservationQuality.HIGH,
        captured_at: str = "2026-08-06T11:00:11Z",
        as_of: str = "2026-08-06T11:00:09Z",
        available_at: str = "2026-08-06T11:00:10Z",
    ) -> None:
        self.value = value
        self.missingness = missingness
        self.quality = quality
        self.captured_at = captured_at
        self.as_of = as_of
        self.available_at = available_at
        self.calls = 0

    def observe_public_outcome(self, *, monitor_plan, requested_at):
        self.calls += 1
        return PublicOutcomeReading(
            raw_payload=b'{"code":"0","data":[{"markPx":"65000"}]}',
            source_locator=PUBLIC_MARK_URL,
            captured_at=self.captured_at,
            observable_ref=monitor_plan["observable"]["observable_ref"],
            value=self.value,
            as_of=self.as_of,
            available_at=self.available_at,
            missingness=self.missingness,
            quality=self.quality,
            coverage="1" if self.missingness is ObservationMissingness.OBSERVED else "0",
            conflict_state="NONE",
            source_request_id=monitor_plan["observable"]["source_request_id"],
        )


class CrashAfterReservationAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def observe_public_outcome(self, *, monitor_plan, requested_at):
        self.calls += 1
        raise SystemExit("simulate process death after durable attempt reservation")


class FakeResearchStore:
    def __init__(self, accepted: dict) -> None:
        self.accepted = accepted

    def read_document(self, **kwargs):
        return self.accepted

    def load_checkpoint(self, *, run_id):
        return {"completed_cycles": self.accepted["cycle_index"]}

    def read_events(self, *, run_id, cycle_index):
        return (
            {},
            {},
            {},
            {},
            {
                "event_type": "STATE_ACCEPTED",
                "artifact_ref": (
                    f"cycles/{cycle_index:04d}/accepted-research-state.json"
                ),
                "artifact_semantic_digest": self.accepted[
                    "accepted_state_digest"
                ],
            },
            {},
        )


class V31MonitorRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.research_store = LocalV31ResearchStore(self.root)
        inputs, documents, event_times = completed_cycle_fixture()
        persist_completed_v31_cycle(
            store=self.research_store,
            run_id=RUN_ID,
            cycle_index=1,
            total_cycles=8,
            created_at=DECISION_AT,
            documents=documents,
            assembly_inputs=inputs,
            recorded_at_by_event=event_times,
        )
        self.accepted = documents["STATE_ACCEPTED"]
        self.contract = build_minimal_experiment_contract(
            contract_id="v31-monitor-runtime-test",
            run_id=RUN_ID,
            frozen_at="2026-08-06T09:00:00Z",
        )
        self.monitor_store = LocalV31MonitorStore(self.root)
        initialize_v31_monitor_runtime(
            store=self.monitor_store,
            experiment_contract=self.contract,
            created_at="2026-08-06T10:00:08Z",
        )
        self.plan = monitor_plan(self.contract, self.accepted)
        schedule_v31_monitor_plan(
            store=self.monitor_store,
            research_store=self.research_store,
            experiment_contract=self.contract,
            accepted_state=self.accepted,
            monitor_plan=self.plan,
            scheduled_at="2026-08-06T10:00:09Z",
        )

    def test_pre_horizon_is_read_only_and_adapter_is_not_called(self) -> None:
        before = self.monitor_store.load_checkpoint(run_id=RUN_ID)
        adapter = FakePublicObservationAdapter()
        status = resolve_due_v31_monitor(
            store=self.monitor_store,
            experiment_contract=self.contract,
            observation_port=adapter,
            requested_at="2026-08-06T10:59:59Z",
        )
        after = self.monitor_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("NOT_DUE", status["runtime_status"])
        self.assertEqual(0, adapter.calls)
        self.assertEqual(before["checkpoint_digest"], after["checkpoint_digest"])
        self.assertFalse(
            (self.root / "monitor/cycles/0001/resolution-attempt.json").exists()
        )

    def test_due_public_observation_writes_raw_observation_receipt_and_cas(self) -> None:
        adapter = FakePublicObservationAdapter()
        result = resolve_due_v31_monitor(
            store=self.monitor_store,
            experiment_contract=self.contract,
            observation_port=adapter,
            requested_at="2026-08-06T11:00:08Z",
        )
        self.assertEqual(1, adapter.calls)
        self.assertEqual("RESOLVED", result["runtime_status"])
        self.assertEqual("FULFILLED", result["expectation_outcome"])
        self.assertEqual("SUPPORTED", result["path_outcome"])
        checkpoint = LocalV31MonitorStore(self.root).load_checkpoint(run_id=RUN_ID)
        self.assertEqual(1, len(checkpoint["plan_bindings"]))
        self.assertEqual(1, len(checkpoint["resolution_attempt_bindings"]))
        self.assertEqual(1, len(checkpoint["outcome_bindings"]))
        self.assertFalse(checkpoint["account_access"])
        self.assertFalse(checkpoint["order_submission"])
        outcome = checkpoint["outcome_bindings"][0]
        self.assertTrue((self.root / outcome["raw_capture_ref"]).is_file())
        self.assertTrue((self.root / outcome["source_record_ref"]).is_file())
        self.assertTrue((self.root / outcome["observation_ref"]).is_file())
        self.assertTrue((self.root / outcome["outcome_receipt_ref"]).is_file())

    def test_unknown_remains_unknown_and_is_counted_as_coverage_loss(self) -> None:
        adapter = FakePublicObservationAdapter(
            value=None,
            missingness=ObservationMissingness.UNKNOWN,
            quality=ObservationQuality.UNKNOWN,
        )
        result = resolve_due_v31_monitor(
            store=self.monitor_store,
            experiment_contract=self.contract,
            observation_port=adapter,
            requested_at="2026-08-06T11:00:08Z",
        )
        self.assertEqual("UNKNOWN", result["expectation_outcome"])
        self.assertEqual("UNRESOLVED", result["path_outcome"])
        self.assertTrue(result["coverage_loss"])

    def test_crash_after_attempt_reservation_is_never_reinvoked(self) -> None:
        adapter = CrashAfterReservationAdapter()
        with self.assertRaises(SystemExit):
            resolve_due_v31_monitor(
                store=self.monitor_store,
                experiment_contract=self.contract,
                observation_port=adapter,
                requested_at="2026-08-06T11:00:08Z",
            )
        status = v31_monitor_status(
            store=LocalV31MonitorStore(self.root),
            experiment_contract=self.contract,
            observed_at="2026-08-06T11:00:09Z",
        )
        self.assertEqual("ATTEMPT_RESERVED_NO_RETRY", status["runtime_status"])
        with self.assertRaisesRegex(
            V31MonitorRuntimeError, "ATTEMPT_RESERVED_NO_RETRY"
        ):
            resolve_due_v31_monitor(
                store=LocalV31MonitorStore(self.root),
                experiment_contract=self.contract,
                observation_port=adapter,
                requested_at="2026-08-06T11:00:09Z",
            )
        self.assertEqual(1, adapter.calls)
        failed = LocalV31MonitorStore(self.root).load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", failed["status"])
        self.assertFalse(failed["resume_allowed"])

    def test_physical_raw_tamper_prevents_checkpoint_load(self) -> None:
        resolve_due_v31_monitor(
            store=self.monitor_store,
            experiment_contract=self.contract,
            observation_port=FakePublicObservationAdapter(),
            requested_at="2026-08-06T11:00:08Z",
        )
        raw_path = self.root / "monitor/cycles/0001/outcome-raw.bin"
        raw_path.write_bytes(raw_path.read_bytes() + b" ")
        with self.assertRaisesRegex(V31MonitorStoreError, "RAW_DIGEST_MISMATCH"):
            LocalV31MonitorStore(self.root).load_checkpoint(run_id=RUN_ID)

    def test_outcome_receipts_form_an_exact_immediate_predecessor_chain(self) -> None:
        first_result = resolve_due_v31_monitor(
            store=self.monitor_store,
            experiment_contract=self.contract,
            observation_port=FakePublicObservationAdapter(),
            requested_at="2026-08-06T11:00:08Z",
        )
        accepted_two = copy.deepcopy(self.accepted)
        accepted_two.pop("accepted_state_digest")
        accepted_two["cycle_index"] = 2
        accepted_two["decision_at"] = "2026-08-06T11:00:00Z"
        accepted_two["selected_at"] = "2026-08-06T11:00:01Z"
        accepted_two["dynamic_research_binding_digest"] = canonical_digest(
            {
                "run_id": RUN_ID,
                "cycle_index": 2,
                "decision_at": "2026-08-06T11:00:00Z",
                "hypothesis_registry_digest": accepted_two[
                    "hypothesis_registry_digest"
                ],
                "expectation_ledger_digest": accepted_two[
                    "expectation_ledger_digest"
                ],
            }
        )
        accepted_two = self_digest(accepted_two, "accepted_state_digest")
        verify_v31_accepted_state(accepted_two)
        plan_two = monitor_plan(self.contract, accepted_two)
        schedule_v31_monitor_plan(
            store=self.monitor_store,
            research_store=FakeResearchStore(accepted_two),
            experiment_contract=self.contract,
            accepted_state=accepted_two,
            monitor_plan=plan_two,
            scheduled_at="2026-08-06T11:00:12Z",
        )
        second = FakePublicObservationAdapter(
            captured_at="2026-08-06T12:00:11Z",
            as_of="2026-08-06T12:00:09Z",
            available_at="2026-08-06T12:00:10Z",
        )
        resolve_due_v31_monitor(
            store=self.monitor_store,
            experiment_contract=self.contract,
            observation_port=second,
            requested_at="2026-08-06T12:00:08Z",
        )
        checkpoint = self.monitor_store.load_checkpoint(run_id=RUN_ID)
        second_receipt = self.monitor_store.read_document(
            relative_ref=checkpoint["outcome_bindings"][1]["outcome_receipt_ref"],
            digest_field="outcome_receipt_digest",
        )
        self.assertEqual(
            first_result["outcome_receipt_digest"],
            second_receipt["previous_outcome_receipt_digest"],
        )

    def test_non_hour_boundary_decision_uses_elapsed_horizon_not_candle_boundary(self) -> None:
        contract = build_minimal_experiment_contract(
            contract_id="non-boundary",
            run_id="non-boundary-run",
            frozen_at="2026-08-06T09:00:00Z",
        )
        non_boundary_origins = {
            "accepted_state": {"ref": "accepted:1", "digest": "a" * 64},
            "path_set": {"ref": "path-set:1", "digest": "b" * 64},
            "path": {"ref": "path:1", "digest": "c" * 64},
            "hypothesis_revision": {"ref": "hyp:1", "digest": "d" * 64},
            "expectation_revision": {"ref": "exp:1", "digest": "e" * 64},
        }
        plan = build_typed_path_monitor_plan(
            experiment_contract=contract,
            monitor_plan_id="monitor:1",
            cycle_id="cycle:1",
            cycle_index=1,
            origin_bindings=non_boundary_origins,
            decision_at="2026-08-06T10:17:23Z",
            observable_ref="metric:mark-price-change-at-1h-horizon",
            source_request_id="okx-public-mark-price:1",
            rules=monitor_rules(),
        )
        self.assertEqual("2026-08-06T11:17:23Z", plan["outcome_not_before"])
        self.assertEqual(
            "FIRST_PUBLIC_MARK_OBSERVATION_AT_OR_AFTER_1H_HORIZON",
            plan["observable"]["window"],
        )
        observation = OutcomeObservation(
            observable_ref="metric:mark-price-change-at-1h-horizon",
            value="0.1",
            as_of="2026-08-06T11:17:24Z",
            available_at="2026-08-06T11:17:25Z",
            missingness=ObservationMissingness.OBSERVED,
            quality=ObservationQuality.HIGH,
            coverage="1",
            conflict_state="NONE",
            source_request_id="okx-public-mark-price:1",
            source_record_digest="1" * 64,
            raw_capture_digest="2" * 64,
            datum_digest="3" * 64,
        )
        receipt = build_path_outcome_receipt(
            experiment_contract=contract,
            monitor_plan=plan,
            expected_origin_bindings=non_boundary_origins,
            outcome_receipt_id="outcome:1",
            evaluated_at="2026-08-06T11:17:26Z",
            evaluator_version="test",
            observation=observation,
        )
        self.assertEqual("FULFILLED", receipt["expectation_outcome"])

    def test_public_source_locator_rejects_account_or_wrong_query(self) -> None:
        for locator in (
            "https://www.okx.com/api/v5/account/balance",
            "https://www.okx.com/api/v5/public/mark-price?instType=SPOT&instId=BTC-USDT",
            "https://user:secret@www.okx.com/api/v5/public/mark-price?instType=SWAP&instId=BTC-USDT-SWAP",
        ):
            with self.subTest(locator=locator):
                with self.assertRaisesRegex(
                    ValueError, "PUBLIC_SOURCE_SCOPE_INVALID"
                ):
                    PublicOutcomeReading(
                        raw_payload=b"{}",
                        source_locator=locator,
                        captured_at="2026-08-06T11:00:11Z",
                        observable_ref="metric:test",
                        value="1",
                        as_of="2026-08-06T11:00:09Z",
                        available_at="2026-08-06T11:00:10Z",
                        missingness=ObservationMissingness.OBSERVED,
                        quality=ObservationQuality.HIGH,
                        coverage="1",
                        conflict_state="NONE",
                        source_request_id="request:1",
                    )


if __name__ == "__main__":
    unittest.main()
