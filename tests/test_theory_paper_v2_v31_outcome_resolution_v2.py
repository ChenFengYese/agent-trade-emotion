from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.application.v31_durable_cycle import (
    persist_completed_v31_cycle,
)
from trade_system.theory_paper_v2.application.v31_monitor_runtime import (
    initialize_v31_monitor_runtime,
    schedule_v31_monitor_plan,
    v31_monitor_status,
)
from trade_system.theory_paper_v2.application.v31_outcome_resolution_v2 import (
    V31OutcomeResolutionV2Error,
    initialize_v31_outcome_evidence_runtime_v2,
    resolve_due_v31_monitor_v2,
)
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    build_minimal_experiment_contract,
)
from trade_system.theory_paper_v2.domain.v31_outcome_capture_v2 import (
    build_outcome_clock_policy,
    build_public_outcome_capture,
    build_public_outcome_transport_failure,
    parse_public_outcome_capture,
)
from trade_system.theory_paper_v2.infrastructure.v31_monitor_store import (
    LocalV31MonitorStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_outcome_evidence_store_v2 import (
    LocalV31OutcomeEvidenceStoreV2,
    V31OutcomeEvidenceStoreV2Error,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)
from tests.test_theory_paper_v2_v31_monitor_runtime import (
    DECISION_AT,
    RUN_ID,
    completed_cycle_fixture,
    monitor_plan,
)


def _timestamp_ms(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


class FakeCapturePort:
    def __init__(self, *, raw: bytes, received_at: str) -> None:
        self.raw = raw
        self.received_at = received_at
        self.calls = 0

    def capture_public_outcome(self, *, monitor_plan, attempt, requested_at):
        self.calls += 1
        capture = build_public_outcome_capture(
            run_id=monitor_plan["run_id"],
            cycle_index=monitor_plan["cycle_index"],
            monitor_plan_digest=monitor_plan["monitor_plan_digest"],
            monitor_attempt_digest=attempt["monitor_attempt_digest"],
            source_request_id=monitor_plan["observable"]["source_request_id"],
            requested_at=requested_at,
            request_started_at=requested_at,
            response_received_at=self.received_at,
            monotonic_elapsed_ms=2,
            status_code=200,
            content_type="application/json",
            final_url=(
                "https://www.okx.com/api/v5/public/mark-price"
                "?instType=SWAP&instId=BTC-USDT-SWAP"
            ),
            raw_payload=self.raw,
        )
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "capture": capture,
            "raw_payload": self.raw,
            "transport_failure": None,
        }


class CrashBeforeResponsePort:
    def __init__(self) -> None:
        self.calls = 0

    def capture_public_outcome(self, **kwargs):
        self.calls += 1
        raise SystemExit("crash before response")


class NoResponsePort:
    def __init__(self) -> None:
        self.calls = 0

    def capture_public_outcome(self, *, monitor_plan, attempt, requested_at):
        self.calls += 1
        failure_at = (
            datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
            + timedelta(milliseconds=10)
        ).isoformat().replace("+00:00", "Z")
        failure = build_public_outcome_transport_failure(
            run_id=monitor_plan["run_id"],
            cycle_index=monitor_plan["cycle_index"],
            monitor_plan_digest=monitor_plan["monitor_plan_digest"],
            monitor_attempt_digest=attempt["monitor_attempt_digest"],
            source_request_id=monitor_plan["observable"]["source_request_id"],
            requested_at=requested_at,
            request_started_at=requested_at,
            failure_at=failure_at,
            monotonic_elapsed_ms=10,
            failure_code="PUBLIC_TIMEOUT",
        )
        return {
            "transport_status": "NO_RESPONSE",
            "capture": None,
            "raw_payload": None,
            "transport_failure": failure,
        }


class BlockingCapturePort(FakeCapturePort):
    def __init__(self, *, raw: bytes, received_at: str) -> None:
        super().__init__(raw=raw, received_at=received_at)
        self.started = threading.Event()
        self.release = threading.Event()

    def capture_public_outcome(self, **kwargs):
        self.started.set()
        if not self.release.wait(timeout=5):
            raise AssertionError("blocking capture was not released")
        return super().capture_public_outcome(**kwargs)


class V31OutcomeResolutionV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        research_store = LocalV31ResearchStore(self.root)
        inputs, documents, event_times = completed_cycle_fixture()
        persist_completed_v31_cycle(
            store=research_store,
            run_id=RUN_ID,
            cycle_index=1,
            total_cycles=8,
            created_at=DECISION_AT,
            documents=documents,
            assembly_inputs=inputs,
            recorded_at_by_event=event_times,
        )
        self.contract = build_minimal_experiment_contract(
            contract_id="v31-outcome-resolution-v2-test",
            run_id=RUN_ID,
            frozen_at="2026-08-06T09:00:00Z",
        )
        self.monitor_store = LocalV31MonitorStore(self.root)
        initialize_v31_monitor_runtime(
            store=self.monitor_store,
            experiment_contract=self.contract,
            created_at="2026-08-06T10:00:08Z",
        )
        self.plan = monitor_plan(self.contract, documents["STATE_ACCEPTED"])
        schedule_v31_monitor_plan(
            store=self.monitor_store,
            research_store=research_store,
            experiment_contract=self.contract,
            accepted_state=documents["STATE_ACCEPTED"],
            monitor_plan=self.plan,
            scheduled_at="2026-08-06T10:00:09Z",
        )
        self.evidence_store = LocalV31OutcomeEvidenceStoreV2(self.root)
        initialize_v31_outcome_evidence_runtime_v2(
            evidence_store=self.evidence_store,
            experiment_contract=self.contract,
            created_at="2026-08-06T10:00:08Z",
        )
        self.requested_at = "2026-08-06T11:00:08Z"
        self.received_at = "2026-08-06T11:00:08.200000Z"
        provider_time = datetime.fromisoformat(
            self.received_at.replace("Z", "+00:00")
        ) - timedelta(milliseconds=500)
        self.valid_raw = (
            "{\"code\":\"0\",\"data\":[{\"instId\":\"BTC-USDT-SWAP\","
            "\"instType\":\"SWAP\",\"markPx\":\"65000.1\",\"ts\":\""
            + _timestamp_ms(provider_time)
            + "\"}]}"
        ).encode()

    def test_parser_runs_only_after_atomic_capture_is_readable(self) -> None:
        port = FakeCapturePort(raw=self.valid_raw, received_at=self.received_at)
        from trade_system.theory_paper_v2.application import (
            v31_outcome_resolution_v2 as workflow,
        )

        real_parser = workflow.parse_public_outcome_capture

        def parser_spy(**kwargs):
            raw_path = self.root / "monitor-v2/cycles/0001/capture/raw.bin"
            record_path = (
                self.root
                / "monitor-v2/cycles/0001/capture/capture-record.json"
            )
            self.assertTrue(raw_path.is_file())
            self.assertTrue(record_path.is_file())
            self.assertEqual(self.valid_raw, raw_path.read_bytes())
            return real_parser(**kwargs)

        with patch.object(workflow, "parse_public_outcome_capture", parser_spy):
            result = resolve_due_v31_monitor_v2(
                monitor_store=self.monitor_store,
                evidence_store=self.evidence_store,
                experiment_contract=self.contract,
                capture_port=port,
                requested_at=self.requested_at,
            )
        self.assertEqual("RESOLVED", result["runtime_status"])
        self.assertEqual(1, port.calls)
        evidence = self.evidence_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(1, len(evidence["attempt_bindings"]))
        self.assertEqual(1, len(evidence["capture_bindings"]))
        self.assertEqual(1, len(evidence["parse_bindings"]))
        self.assertEqual(1, len(evidence["resolution_bindings"]))

    def test_invalid_json_is_rejected_only_after_raw_is_durable(self) -> None:
        port = FakeCapturePort(raw=b"{", received_at=self.received_at)
        with self.assertRaises(V31OutcomeResolutionV2Error):
            resolve_due_v31_monitor_v2(
                monitor_store=self.monitor_store,
                evidence_store=self.evidence_store,
                experiment_contract=self.contract,
                capture_port=port,
                requested_at=self.requested_at,
            )
        self.assertEqual(
            b"{",
            (self.root / "monitor-v2/cycles/0001/capture/raw.bin").read_bytes(),
        )
        parse_receipt = self.evidence_store.read_parse_receipt(
            run_id=RUN_ID, cycle_index=1
        )
        self.assertEqual("REJECTED", parse_receipt["parse_status"])
        self.assertEqual("PUBLIC_JSON_INVALID", parse_receipt["error_code"])
        self.assertEqual(
            "FAILED_CLOSED",
            self.monitor_store.load_checkpoint(run_id=RUN_ID)["status"],
        )
        self.assertEqual(
            "FAILED_CLOSED",
            self.evidence_store.load_checkpoint(run_id=RUN_ID)["status"],
        )

    def test_crash_after_capture_resumes_locally_without_second_get(self) -> None:
        port = FakeCapturePort(raw=self.valid_raw, received_at=self.received_at)
        from trade_system.theory_paper_v2.application import (
            v31_outcome_resolution_v2 as workflow,
        )

        with patch.object(
            workflow,
            "parse_public_outcome_capture",
            side_effect=SystemExit("after capture"),
        ):
            with self.assertRaises(SystemExit):
                resolve_due_v31_monitor_v2(
                    monitor_store=self.monitor_store,
                    evidence_store=self.evidence_store,
                    experiment_contract=self.contract,
                    capture_port=port,
                    requested_at=self.requested_at,
                )
        self.assertEqual(1, port.calls)
        self.assertEqual(
            "ATTEMPT_RESERVED_NO_RETRY",
            v31_monitor_status(
                store=self.monitor_store,
                experiment_contract=self.contract,
                observed_at="2026-08-06T11:00:09Z",
            )["runtime_status"],
        )
        result = resolve_due_v31_monitor_v2(
            monitor_store=self.monitor_store,
            evidence_store=self.evidence_store,
            experiment_contract=self.contract,
            capture_port=port,
            requested_at="2026-08-06T11:00:09Z",
        )
        self.assertEqual("RESOLVED_FROM_COMMITTED_CAPTURE", result["runtime_status"])
        self.assertEqual(1, port.calls)

    def test_attempt_only_crash_never_refetches_and_fails_closed(self) -> None:
        port = CrashBeforeResponsePort()
        with self.assertRaises(SystemExit):
            resolve_due_v31_monitor_v2(
                monitor_store=self.monitor_store,
                evidence_store=self.evidence_store,
                experiment_contract=self.contract,
                capture_port=port,
                requested_at=self.requested_at,
            )
        self.assertEqual(1, port.calls)
        with self.assertRaisesRegex(
            V31OutcomeResolutionV2Error, "LOCAL_RECOVERY_FAILED"
        ):
            resolve_due_v31_monitor_v2(
                monitor_store=self.monitor_store,
                evidence_store=self.evidence_store,
                experiment_contract=self.contract,
                capture_port=port,
                requested_at="2026-08-06T11:00:09Z",
            )
        self.assertEqual(1, port.calls)
        self.assertEqual(
            "FAILED_CLOSED",
            self.evidence_store.load_checkpoint(run_id=RUN_ID)["status"],
        )

    def test_raw_tamper_blocks_evidence_replay(self) -> None:
        port = FakeCapturePort(raw=self.valid_raw, received_at=self.received_at)
        resolve_due_v31_monitor_v2(
            monitor_store=self.monitor_store,
            evidence_store=self.evidence_store,
            experiment_contract=self.contract,
            capture_port=port,
            requested_at=self.requested_at,
        )
        raw_path = self.root / "monitor-v2/cycles/0001/capture/raw.bin"
        raw_path.write_bytes(raw_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V31OutcomeEvidenceStoreV2Error, "CAPTURE_BINDING_INVALID"
        ):
            LocalV31OutcomeEvidenceStoreV2(self.root).load_checkpoint(
                run_id=RUN_ID
            )

    def test_unknown_clock_outcome_is_not_zero_and_resolves(self) -> None:
        received = datetime.fromisoformat(
            self.received_at.replace("Z", "+00:00")
        )
        provider = received + timedelta(milliseconds=2001)
        raw = (
            "{\"code\":\"0\",\"data\":[{\"instId\":\"BTC-USDT-SWAP\","
            "\"instType\":\"SWAP\",\"markPx\":\"65000\",\"ts\":\""
            + _timestamp_ms(provider)
            + "\"}]}"
        ).encode()
        result = resolve_due_v31_monitor_v2(
            monitor_store=self.monitor_store,
            evidence_store=self.evidence_store,
            experiment_contract=self.contract,
            capture_port=FakeCapturePort(raw=raw, received_at=self.received_at),
            requested_at=self.requested_at,
        )
        self.assertEqual("UNKNOWN", result["expectation_outcome"])
        self.assertTrue(result["coverage_loss"])
        receipt = self.evidence_store.read_parse_receipt(
            run_id=RUN_ID, cycle_index=1
        )
        self.assertIsNone(receipt["value"])
        self.assertEqual("CLOCK_BOUND_EXCEEDED", receipt["error_code"])

    def test_orphan_transport_receipt_recovers_without_second_get(self) -> None:
        port = NoResponsePort()
        real_replace = self.evidence_store._replace_checkpoint

        def crash_after_receipt(**kwargs):
            if kwargs["candidate"].get("transport_failure_binding") is not None:
                raise SystemExit("after transport receipt")
            return real_replace(**kwargs)

        with patch.object(
            self.evidence_store,
            "_replace_checkpoint",
            side_effect=crash_after_receipt,
        ):
            with self.assertRaises(SystemExit):
                resolve_due_v31_monitor_v2(
                    monitor_store=self.monitor_store,
                    evidence_store=self.evidence_store,
                    experiment_contract=self.contract,
                    capture_port=port,
                    requested_at=self.requested_at,
                )
        self.assertEqual(1, port.calls)
        self.assertTrue(
            (
                self.root
                / "monitor-v2/cycles/0001/transport-failure.json"
            ).is_file()
        )

        with self.assertRaisesRegex(
            V31OutcomeResolutionV2Error, "NO_RESPONSE_RECOVERED"
        ):
            resolve_due_v31_monitor_v2(
                monitor_store=self.monitor_store,
                evidence_store=self.evidence_store,
                experiment_contract=self.contract,
                capture_port=port,
                requested_at="2026-08-06T11:00:09Z",
            )

        self.assertEqual(1, port.calls)
        evidence = self.evidence_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", evidence["status"])
        self.assertIsNotNone(evidence["transport_failure_binding"])

    def test_clock_policy_drift_rejects_before_attempt_or_get(self) -> None:
        port = CrashBeforeResponsePort()
        changed_policy = build_outcome_clock_policy(
            max_provider_clock_lead_ms=1_999,
            max_provider_age_ms=5_000,
        )

        with self.assertRaisesRegex(
            V31OutcomeResolutionV2Error, "CLOCK_POLICY_BINDING_MISMATCH"
        ):
            resolve_due_v31_monitor_v2(
                monitor_store=self.monitor_store,
                evidence_store=self.evidence_store,
                experiment_contract=self.contract,
                capture_port=port,
                requested_at=self.requested_at,
                clock_policy=changed_policy,
            )

        self.assertEqual(0, port.calls)
        self.assertEqual(
            0,
            len(
                self.monitor_store.load_checkpoint(run_id=RUN_ID)[
                    "resolution_attempt_bindings"
                ]
            ),
        )

    def test_failed_checkpoint_cannot_append_parse_receipt(self) -> None:
        port = FakeCapturePort(raw=self.valid_raw, received_at=self.received_at)
        from trade_system.theory_paper_v2.application import (
            v31_outcome_resolution_v2 as workflow,
        )

        with patch.object(
            workflow,
            "parse_public_outcome_capture",
            side_effect=SystemExit("after capture"),
        ):
            with self.assertRaises(SystemExit):
                resolve_due_v31_monitor_v2(
                    monitor_store=self.monitor_store,
                    evidence_store=self.evidence_store,
                    experiment_contract=self.contract,
                    capture_port=port,
                    requested_at=self.requested_at,
                )
        self.evidence_store.fail_checkpoint(
            run_id=RUN_ID,
            cycle_index=1,
            failure_code="TEST_PERMANENT_FAILURE",
            failed_at="2026-08-06T11:00:09Z",
        )
        capture, raw, _ = self.evidence_store.load_committed_capture(
            run_id=RUN_ID, cycle_index=1
        )
        policy = build_outcome_clock_policy()
        receipt = parse_public_outcome_capture(
            capture=capture,
            raw_payload=raw,
            clock_policy=policy,
            observable_ref=self.plan["observable"]["observable_ref"],
        )

        with self.assertRaisesRegex(
            V31OutcomeEvidenceStoreV2Error, "PARSE_SEQUENCE_INVALID"
        ):
            self.evidence_store.commit_parse_receipt(
                run_id=RUN_ID,
                cycle_index=1,
                receipt=receipt,
                clock_policy=policy,
                observable_ref=self.plan["observable"]["observable_ref"],
                committed_at=self.received_at,
            )

        self.assertFalse(
            (self.root / "monitor-v2/cycles/0001/parse-receipt.json").exists()
        )

    def test_concurrent_wakeup_serializes_to_exactly_one_get(self) -> None:
        port = BlockingCapturePort(
            raw=self.valid_raw,
            received_at=self.received_at,
        )
        results = []
        errors = []

        def run_once():
            try:
                results.append(
                    resolve_due_v31_monitor_v2(
                        monitor_store=self.monitor_store,
                        evidence_store=self.evidence_store,
                        experiment_contract=self.contract,
                        capture_port=port,
                        requested_at=self.requested_at,
                    )
                )
            except BaseException as exc:  # test must surface thread failures
                errors.append(exc)

        first = threading.Thread(target=run_once)
        second = threading.Thread(target=run_once)
        first.start()
        self.assertTrue(port.started.wait(timeout=5))
        second.start()
        port.release.set()
        first.join(timeout=10)
        second.join(timeout=10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(1, port.calls)
        self.assertEqual(2, len(results))
        self.assertIn("RESOLVED", {row["runtime_status"] for row in results})
        self.assertEqual(
            "ACTIVE",
            self.evidence_store.load_checkpoint(run_id=RUN_ID)["status"],
        )


if __name__ == "__main__":
    unittest.main()
