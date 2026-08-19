from __future__ import annotations

from datetime import UTC, datetime, timedelta
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.application.v32_outcome_tick_composition import (
    V32OutcomeTickCompositionError,
    initialize_v32_outcome_tick_runtime,
    run_v32_outcome_tick,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    V32PublicTransportUnavailableError,
    build_v32_outcome_observation_tick,
    build_v32_outcome_schedule_set,
    build_v32_outcome_tick_attempt,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD as SUPERVISOR_PERMIT_DIGEST_FIELD,
    V32TickSupervisorError,
    build_v32_analysis_tick_permit,
    build_v32_outcome_tick_permit,
    build_v32_tick_supervisor_checkpoint,
    complete_v32_analysis_tick,
    complete_v32_outcome_tick,
    open_v32_tick_supervisor_permit,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
    V32OutcomeTickStoreError,
    build_v32_outcome_tick_checkpoint,
    build_v32_public_transport_failure,
)
from trade_system.theory_paper_v2 import (
    v32_durable_json as durable_json_module,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_outcome_adapter import (
    OKX_V32_MARK_PRICE_URL,
)


RUN_ID = "run:v32:outcome-runtime"


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def schedule_set(
    *, cycle: int, decision_time: str, run_id: str = RUN_ID
) -> dict:
    decided = datetime.fromisoformat(decision_time.replace("Z", "+00:00"))
    return build_v32_outcome_schedule_set(
        run_id=run_id,
        decision_id=f"decision:{cycle:04d}",
        cycle_index=cycle,
        decision_time=decision_time,
        scheduled_at=iso(decided + timedelta(seconds=1)),
        sealed_decision_digest=f"{cycle % 10}" * 64,
        evaluation_contract_digest="c" * 64,
    )


def raw_mark(*, value: str = "65000.1", ts: str = "1786064401000") -> bytes:
    return json.dumps(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": "BTC-USDT-SWAP",
                    "markPx": value,
                    "ts": ts,
                }
            ],
        },
        separators=(",", ":"),
    ).encode("utf-8")


class CapturePort:
    def __init__(
        self,
        *,
        raw: bytes | None = None,
        failure: str | None = None,
        response_at: str = "2026-08-07T01:00:02Z",
        captured_at: str | None = None,
        http_status: int = 200,
        final_url: str = OKX_V32_MARK_PRICE_URL,
    ):
        self.raw = raw if raw is not None else raw_mark()
        self.failure = failure
        self.response_at = response_at
        self.captured_at = captured_at or response_at
        self.http_status = http_status
        self.final_url = final_url
        self.calls = 0

    def capture_public_mark(self, *, attempt, requested_at):
        self.calls += 1
        if self.failure is not None:
            return {
                "transport_status": "NO_RESPONSE",
                "source_request_id": attempt["source_request_id"],
                "failure_at": self.response_at,
                "failure_code": self.failure,
            }
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "source_request_id": attempt["source_request_id"],
            "received_at": self.response_at,
            "captured_at": self.captured_at,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "raw_payload": self.raw,
        }


class RaisingCapturePort:
    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    def capture_public_mark(self, *, attempt, requested_at):
        self.calls += 1
        raise self.error


class InjectedCrash(BaseException):
    pass


class CrashAfterFirstReceiptStore(LocalV32OutcomeTickStore):
    def __init__(self, run_root: Path) -> None:
        super().__init__(run_root)
        self.crash_enabled = True
        self.receipt_commits = 0

    def commit_outcome_receipt(self, **kwargs):
        result = super().commit_outcome_receipt(**kwargs)
        self.receipt_commits += 1
        if self.crash_enabled and self.receipt_commits == 1:
            raise InjectedCrash("after first durable receipt")
        return result


class V32OutcomeTickRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.store = LocalV32OutcomeTickStore(self.root)
        outcome_genesis = build_v32_outcome_tick_checkpoint(
            run_id=RUN_ID,
            created_at="2026-08-07T00:00:00Z",
        )
        self.supervisor_checkpoint = build_v32_tick_supervisor_checkpoint(
            run_id=RUN_ID,
            experiment_contract_digest="a" * 64,
            active_authority_digest="b" * 64,
            research_checkpoint_digest="c" * 64,
            outcome_checkpoint_digest=outcome_genesis["checkpoint_digest"],
            timeframe_cache_digest="e" * 64,
            created_at="2026-08-07T00:00:00Z",
        )
        initialize_v32_outcome_tick_runtime(
            store=self.store,
            run_id=RUN_ID,
            created_at="2026-08-07T00:00:00Z",
            supervisor_checkpoint=self.supervisor_checkpoint,
        )
        self._outcome_supervision: dict[int, tuple[dict, dict, dict]] = {}

    def tearDown(self) -> None:
        self.directory.cleanup()

    def register_shared_due_sets(self, *, store=None) -> tuple[dict]:
        owner = store or self.store
        first = schedule_set(cycle=1, decision_time="2026-08-07T00:00:00Z")
        schedule_sets_before = owner.load_schedule_sets(run_id=RUN_ID)
        permit = build_v32_analysis_tick_permit(
            checkpoint=self.supervisor_checkpoint,
            schedule_sets=schedule_sets_before,
            analysis_decision_at="2026-08-07T00:00:00Z",
            issued_at="2026-08-07T00:00:01Z",
            research_checkpoint_digest=self.supervisor_checkpoint[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=self.supervisor_checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=self.supervisor_checkpoint[
                "current_timeframe_cache_digest"
            ],
            prior_dynamic_state_digest=None,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=self.supervisor_checkpoint,
            permit=permit,
            schedule_sets=schedule_sets_before,
            updated_at=permit["issued_at"],
        )
        outcome_after_schedule = owner.register_schedule_set(
            schedule_set=first, registered_at="2026-08-07T00:00:02Z"
        )
        self.supervisor_checkpoint = complete_v32_analysis_tick(
            checkpoint=opened,
            permit=permit,
            schedule_sets_before=schedule_sets_before,
            new_schedule_set=first,
            accepted_state_digest="1" * 64,
            source_admission_digest="2" * 64,
            source_admission_physical_sha256="3" * 64,
            proposal_lifecycle_digest="4" * 64,
            selection_lifecycle_digest="5" * 64,
            final_action_plan_digest="6" * 64,
            commit_envelope_digest="7" * 64,
            shadow_decision_bundle_digest="0" * 64,
            new_research_checkpoint_digest="8" * 64,
            new_outcome_checkpoint_digest=outcome_after_schedule[
                "checkpoint_digest"
            ],
            new_timeframe_cache_digest="9" * 64,
            new_dynamic_state_digest="a" * 64,
            completed_at="2026-08-07T00:00:03Z",
        )
        return (first,)

    def run_tick(self, capture, *, store=None):
        owner = store or self.store
        supervision = self._outcome_supervision.get(id(owner))
        if supervision is None:
            attempt = build_v32_outcome_tick_attempt(
                run_id=RUN_ID,
                tick_index=1,
                planned_tick_at="2026-08-07T01:00:00Z",
                reserved_at="2026-08-07T01:00:01Z",
            )
            schedule_sets = owner.load_schedule_sets(run_id=RUN_ID)
            permit = build_v32_outcome_tick_permit(
                checkpoint=self.supervisor_checkpoint,
                schedule_sets=schedule_sets,
                tick_attempt=attempt,
                issued_at="2026-08-07T01:00:01Z",
            )
            opened = open_v32_tick_supervisor_permit(
                checkpoint=self.supervisor_checkpoint,
                permit=permit,
                schedule_sets=schedule_sets,
                tick_attempt=attempt,
                updated_at="2026-08-07T01:00:01Z",
            )
            supervision = (self.supervisor_checkpoint, opened, permit)
            self._outcome_supervision[id(owner)] = supervision
        before, opened, permit = supervision
        return run_v32_outcome_tick(
            store=owner,
            capture_port=capture,
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            requested_at="2026-08-07T01:00:01Z",
            supervisor_checkpoint_before_permit=before,
            supervisor_open_checkpoint=opened,
            supervisor_permit=permit,
        )

    def reserve_direct_attempt(self) -> dict:
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            reserved_at="2026-08-07T01:00:01Z",
        )
        self.store.reserve_attempt(
            attempt=attempt,
            expected_checkpoint_digest=checkpoint["checkpoint_digest"],
        )
        return attempt

    def test_raw_bundle_short_write_never_publishes_and_existing_replay_fsyncs(self):
        attempt = self.reserve_direct_attempt()
        raw = raw_mark()
        real_fdopen = durable_json_module.os.fdopen

        class ShortWriteHandle:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def write(self, payload):
                return self.handle.write(payload[: max(1, len(payload) // 2)])

            def flush(self):
                self.handle.flush()

            def fileno(self):
                return self.handle.fileno()

        calls = 0

        def short_first_fdopen(*args, **kwargs):
            nonlocal calls
            handle = real_fdopen(*args, **kwargs)
            calls += 1
            if calls == 1:
                return ShortWriteHandle(handle)
            return handle

        with patch.object(
            durable_json_module.os,
            "fdopen",
            side_effect=short_first_fdopen,
        ), self.assertRaises(OSError):
            self.store._publish_raw_bundle(
                attempt=attempt,
                raw_payload=raw,
                recorded_at="2026-08-07T01:00:02Z",
            )
        bundle_path = self.root / "outcome-v32/ticks/0001/raw"
        self.assertFalse(bundle_path.exists())
        self.assertEqual(
            [], list(bundle_path.parent.glob(".v32-write-once-directory-*.tmp"))
        )

        self.store._publish_raw_bundle(
            attempt=attempt,
            raw_payload=raw,
            recorded_at="2026-08-07T01:00:02Z",
        )
        with patch.object(
            durable_json_module.os,
            "fsync",
            side_effect=OSError("injected existing bundle fsync failure"),
        ), self.assertRaises(OSError):
            self.store._publish_raw_bundle(
                attempt=attempt,
                raw_payload=raw,
                recorded_at="2026-08-07T01:00:02Z",
            )
        self.store._publish_raw_bundle(
            attempt=attempt,
            raw_payload=raw,
            recorded_at="2026-08-07T01:00:02Z",
        )

    def test_happy_shared_tick_resolves_all_due_with_one_call(self) -> None:
        self.register_shared_due_sets()
        capture = CapturePort()
        result = self.run_tick(capture)
        self.assertEqual("RESOLVED", result["runtime_status"])
        self.assertEqual(1, result["network_request_count"])
        self.assertEqual(1, capture.calls)
        self.assertEqual(2, len(result["resolved_schedule_ids"]))
        receipts = self.store.load_tick_receipts(run_id=RUN_ID, tick_index=1)
        self.assertEqual(2, len(receipts))
        materials = self.store.load_terminal_receipt_materials(run_id=RUN_ID)
        self.assertEqual(receipts, [row["receipt"] for row in materials])
        self.assertTrue(
            all(
                set(row["receipt_binding"])
                == {
                    "relative_ref",
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                }
                for row in materials
            )
        )
        self.assertNotIn("tick_index", materials[0]["receipt_binding"])
        self.assertNotIn("schedule_id", materials[0]["receipt_binding"])
        self.assertEqual(
            ["OBSERVED_PUBLIC_MARK", "UNKNOWN_COVERAGE_LOSS"],
            result["resolution_statuses"],
        )
        for receipt in receipts:
            self.assertFalse(receipt["trigger_is_fill"])
            self.assertFalse(receipt["fill_claim"])
            self.assertFalse(receipt["position_claim"])
            self.assertFalse(receipt["pnl_claim"])
            self.assertFalse(receipt["executable"])

    def test_duplicate_wake_reads_terminal_prefix_without_second_call(self) -> None:
        self.register_shared_due_sets()
        capture = CapturePort()
        self.run_tick(capture)
        duplicate = self.run_tick(capture)
        self.assertEqual("ALREADY_COMPLETE", duplicate["runtime_status"])
        self.assertEqual(0, duplicate["network_request_count"])
        self.assertEqual(1, capture.calls)

    def test_cross_cycle_batches_replay_their_frozen_schedule_prefix(self) -> None:
        self.register_shared_due_sets()
        first_result = self.run_tick(CapturePort())
        first_prefix = self.store.tick_prefix(run_id=RUN_ID, tick_index=1)
        first_batch = deepcopy(first_prefix["batch_intent"])
        first_completion = deepcopy(first_prefix["batch_completion"])
        _, first_opened, first_permit = self._outcome_supervision[id(self.store)]
        self.supervisor_checkpoint = complete_v32_outcome_tick(
            checkpoint=first_opened,
            permit=first_permit,
            tick_attempt=first_prefix["attempt"],
            observation_tick=first_prefix["observation_tick"],
            schedule_sets=self.store.load_schedule_sets(run_id=RUN_ID),
            prior_terminal_receipts=[],
            batch_intent=first_prefix["batch_intent"],
            outcome_receipts=first_prefix["outcome_receipts"],
            batch_completion=first_prefix["batch_completion"],
            new_outcome_checkpoint_digest=first_result["checkpoint_digest"],
            completed_at="2026-08-07T01:00:03Z",
        )

        second = schedule_set(
            cycle=2, decision_time="2026-08-07T01:15:00Z"
        )
        schedule_sets_before = self.store.load_schedule_sets(run_id=RUN_ID)
        analysis_permit = build_v32_analysis_tick_permit(
            checkpoint=self.supervisor_checkpoint,
            schedule_sets=schedule_sets_before,
            analysis_decision_at="2026-08-07T01:15:00Z",
            issued_at="2026-08-07T01:15:01Z",
            research_checkpoint_digest=self.supervisor_checkpoint[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=self.supervisor_checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=self.supervisor_checkpoint[
                "current_timeframe_cache_digest"
            ],
            prior_dynamic_state_digest=self.supervisor_checkpoint[
                "current_dynamic_state_digest"
            ],
        )
        analysis_opened = open_v32_tick_supervisor_permit(
            checkpoint=self.supervisor_checkpoint,
            permit=analysis_permit,
            schedule_sets=schedule_sets_before,
            updated_at=analysis_permit["issued_at"],
        )
        after_second_schedule = self.store.register_schedule_set(
            schedule_set=second,
            registered_at="2026-08-07T01:15:02Z",
        )
        self.supervisor_checkpoint = complete_v32_analysis_tick(
            checkpoint=analysis_opened,
            permit=analysis_permit,
            schedule_sets_before=schedule_sets_before,
            new_schedule_set=second,
            accepted_state_digest="d" * 64,
            source_admission_digest="e" * 64,
            source_admission_physical_sha256="f" * 64,
            proposal_lifecycle_digest="1" * 64,
            selection_lifecycle_digest="2" * 64,
            final_action_plan_digest="3" * 64,
            commit_envelope_digest="4" * 64,
            shadow_decision_bundle_digest="5" * 64,
            new_research_checkpoint_digest="6" * 64,
            new_outcome_checkpoint_digest=after_second_schedule[
                "checkpoint_digest"
            ],
            new_timeframe_cache_digest="7" * 64,
            new_dynamic_state_digest="8" * 64,
            completed_at="2026-08-07T01:15:03Z",
        )

        self.assertEqual(
            first_batch,
            self.store.load_batch_intent(run_id=RUN_ID, tick_index=1),
        )
        self.assertEqual(
            first_completion,
            self.store.load_batch_completion(run_id=RUN_ID, tick_index=1),
        )
        after_registration = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(
            1,
            after_registration["batch_intent_bindings"][0][
                "schedule_set_prefix_count"
            ],
        )

        schedule_sets = self.store.load_schedule_sets(run_id=RUN_ID)
        second_attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=2,
            planned_tick_at="2026-08-07T02:15:00Z",
            reserved_at="2026-08-07T02:15:01Z",
        )
        second_permit = build_v32_outcome_tick_permit(
            checkpoint=self.supervisor_checkpoint,
            schedule_sets=schedule_sets,
            tick_attempt=second_attempt,
            issued_at="2026-08-07T02:15:01Z",
        )
        second_opened = open_v32_tick_supervisor_permit(
            checkpoint=self.supervisor_checkpoint,
            permit=second_permit,
            schedule_sets=schedule_sets,
            tick_attempt=second_attempt,
            updated_at="2026-08-07T02:15:01Z",
        )
        second_result = run_v32_outcome_tick(
            store=self.store,
            capture_port=CapturePort(
                raw=raw_mark(ts="1786068901000"),
                response_at="2026-08-07T02:15:02Z",
            ),
            run_id=RUN_ID,
            tick_index=2,
            planned_tick_at="2026-08-07T02:15:00Z",
            requested_at="2026-08-07T02:15:01Z",
            supervisor_checkpoint_before_permit=self.supervisor_checkpoint,
            supervisor_open_checkpoint=second_opened,
            supervisor_permit=second_permit,
        )
        second_due = {
            row["schedule_id"] for row in second["schedules"][:2]
        }
        self.assertEqual(second_due, set(second_result["resolved_schedule_ids"]))
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(
            [1, 2],
            [
                binding["schedule_set_prefix_count"]
                for binding in checkpoint["batch_intent_bindings"]
            ],
        )
        self.assertNotEqual(
            checkpoint["batch_intent_bindings"][0][
                "schedule_set_prefix_digest"
            ],
            checkpoint["batch_intent_bindings"][1][
                "schedule_set_prefix_digest"
            ],
        )
        self.assertEqual(
            first_batch,
            self.store.load_batch_intent(run_id=RUN_ID, tick_index=1),
        )

        tampered = deepcopy(checkpoint)
        tampered["batch_intent_bindings"][0][
            "schedule_set_prefix_count"
        ] = 2
        tampered["batch_intent_bindings"][0][
            "schedule_set_prefix_digest"
        ] = tampered["batch_intent_bindings"][1][
            "schedule_set_prefix_digest"
        ]
        tampered = self_digest(tampered, "checkpoint_digest")
        (self.root / "outcome-v32/checkpoint.json").write_bytes(
            canonical_bytes(tampered) + b"\n"
        )
        with self.assertRaisesRegex(
            (V32OutcomeTickStoreError, ValueError),
            "BATCH|RECONSTRUCTION_MISMATCH",
        ):
            self.store.load_checkpoint(run_id=RUN_ID)

    def test_transport_failure_is_terminal_unknown_not_run_failure(self) -> None:
        self.register_shared_due_sets()
        capture = CapturePort(failure="PUBLIC_TIMEOUT")
        result = self.run_tick(capture)
        self.assertEqual("RESOLVED", result["runtime_status"])
        self.assertEqual(["UNKNOWN_COVERAGE_LOSS"], result["resolution_statuses"])
        self.assertEqual(1, capture.calls)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("ACTIVE", checkpoint["status"])
        for receipt in self.store.load_tick_receipts(
            run_id=RUN_ID, tick_index=1
        ):
            self.assertIsNone(receipt["value"])
            self.assertEqual(1, receipt["attempt_count"])
            self.assertFalse(receipt["retry_allowed"])

    def test_valid_empty_public_response_is_durable_unknown_coverage(self) -> None:
        self.register_shared_due_sets()
        raw = b'{"code":"0","msg":"","data":[]}'
        capture = CapturePort(raw=raw)
        result = self.run_tick(capture)
        self.assertEqual(["UNKNOWN_COVERAGE_LOSS"], result["resolution_statuses"])
        self.assertEqual(1, capture.calls)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("ACTIVE", checkpoint["status"])
        self.assertEqual("PUBLIC_RAW_CAPTURE", checkpoint["evidence_bindings"][0]["evidence_kind"])
        self.assertEqual(
            "COVERAGE_FAILURE",
            checkpoint["normalization_bindings"][0]["normalization_kind"],
        )
        self.assertEqual(
            raw,
            (self.root / "outcome-v32/ticks/0001/raw/raw.bin").read_bytes(),
        )

    def test_store_recomputes_coverage_from_durable_raw_before_commit(self) -> None:
        attempt = self.reserve_direct_attempt()
        self.store.commit_raw_capture(
            run_id=RUN_ID,
            tick_index=1,
            raw_payload=b"{not-json",
            recorded_at="2026-08-07T01:00:02Z",
        )
        capture, _, _ = self.store.load_evidence(run_id=RUN_ID, tick_index=1)
        forged = self.store.build_public_coverage_failure(
            attempt=attempt,
            raw_capture=capture,
            failure_code="PUBLIC_DATA_EMPTY",
            recorded_at="2026-08-07T01:00:02Z",
        )
        with self.assertRaisesRegex(
            V32OutcomeTickStoreError,
            "DURABLE_RAW_NORMALIZATION_INVALID.*RAW_JSON_INVALID",
        ):
            self.store.commit_normalization(
                run_id=RUN_ID,
                tick_index=1,
                document=forged,
                normalization_kind="COVERAGE_FAILURE",
                committed_at="2026-08-07T01:00:02Z",
            )
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(0, len(checkpoint["normalization_bindings"]))
        self.assertFalse(
            (self.root / "outcome-v32/ticks/0001/coverage-failure.json").exists()
        )

    def test_store_recomputes_observed_value_from_durable_raw(self) -> None:
        attempt = self.reserve_direct_attempt()
        self.store.commit_raw_capture(
            run_id=RUN_ID,
            tick_index=1,
            raw_payload=raw_mark(),
            recorded_at="2026-08-07T01:00:02Z",
        )
        capture, _, _ = self.store.load_evidence(run_id=RUN_ID, tick_index=1)
        forged = self.store.build_public_mark_parse_receipt(
            attempt=attempt,
            raw_capture=capture,
            value="1",
            provider_as_of="2026-08-07T01:00:01Z",
            available_at="2026-08-07T01:00:02Z",
            recorded_at="2026-08-07T01:00:02Z",
        )
        with self.assertRaisesRegex(
            V32OutcomeTickStoreError, "NORMALIZATION_SEMANTIC_MISMATCH"
        ):
            self.store.commit_normalization(
                run_id=RUN_ID,
                tick_index=1,
                document=forged,
                normalization_kind="OBSERVED_PARSE",
                committed_at="2026-08-07T01:00:02Z",
            )
        self.assertEqual(
            0,
            len(
                self.store.load_checkpoint(run_id=RUN_ID)[
                    "normalization_bindings"
                ]
            ),
        )

    def test_store_rejects_cross_code_observations_for_exact_prefix(self) -> None:
        cases = (
            (
                "response",
                b'{"code":"0","msg":"","data":[]}',
                None,
                "PUBLIC_DATA_EMPTY",
                "PUBLIC_PROVIDER_UNAVAILABLE",
            ),
            (
                "transport",
                None,
                "PUBLIC_DNS_UNAVAILABLE",
                "PUBLIC_DNS_UNAVAILABLE",
                "PUBLIC_TIMEOUT",
            ),
        )
        for index, (label, raw, transport_code, exact_code, forged_code) in enumerate(
            cases
        ):
            with self.subTest(label=label):
                if index:
                    self.tearDown()
                    self.setUp()
                attempt = self.reserve_direct_attempt()
                if raw is not None:
                    self.store.commit_raw_capture(
                        run_id=RUN_ID,
                        tick_index=1,
                        raw_payload=raw,
                        recorded_at="2026-08-07T01:00:02Z",
                    )
                    evidence, _, evidence_binding = self.store.load_evidence(
                        run_id=RUN_ID, tick_index=1
                    )
                    normalization = self.store.build_public_coverage_failure(
                        attempt=attempt,
                        raw_capture=evidence,
                        failure_code=exact_code,
                        recorded_at="2026-08-07T01:00:02Z",
                    )
                    normalization_kind = "COVERAGE_FAILURE"
                else:
                    self.store.commit_transport_failure(
                        run_id=RUN_ID,
                        tick_index=1,
                        failure_code=transport_code,
                        failure_at="2026-08-07T01:00:02Z",
                    )
                    evidence, _, evidence_binding = self.store.load_evidence(
                        run_id=RUN_ID, tick_index=1
                    )
                    normalization = evidence
                    normalization_kind = "TRANSPORT_FAILURE"
                self.store.commit_normalization(
                    run_id=RUN_ID,
                    tick_index=1,
                    document=normalization,
                    normalization_kind=normalization_kind,
                    committed_at="2026-08-07T01:00:02Z",
                )
                _, normalization_binding = self.store.load_normalization(
                    run_id=RUN_ID, tick_index=1
                )
                raw_binding = {
                    "evidence_kind": evidence_binding["evidence_kind"],
                    "schema_id": evidence["schema_id"],
                    "digest_field": evidence_binding["digest_field"],
                    "semantic_digest": evidence_binding["semantic_digest"],
                    "physical_sha256": evidence_binding["physical_sha256"],
                    "recorded_at": evidence["recorded_at"],
                    "raw_payload_sha256": evidence_binding[
                        "raw_payload_sha256"
                    ],
                }
                forged = build_v32_outcome_observation_tick(
                    attempt=attempt,
                    raw_evidence_binding=raw_binding,
                    normalized_at="2026-08-07T01:00:02Z",
                    status="UNKNOWN_COVERAGE_LOSS",
                    value=None,
                    provider_as_of=None,
                    available_at="2026-08-07T01:00:02Z",
                    quality="UNKNOWN",
                    missingness="UNKNOWN",
                    conflict_state=forged_code,
                    parser_receipt_digest=normalization_binding[
                        "semantic_digest"
                    ],
                )
                with self.assertRaisesRegex(
                    V32OutcomeTickStoreError, "OBSERVATION_PREFIX_MISMATCH"
                ):
                    self.store.commit_observation_tick(
                        run_id=RUN_ID,
                        tick_index=1,
                        observation_tick=forged,
                    )

    def test_store_rejects_observation_with_swapped_raw_binding(self) -> None:
        attempt = self.reserve_direct_attempt()
        self.store.commit_raw_capture(
            run_id=RUN_ID,
            tick_index=1,
            raw_payload=raw_mark(),
            recorded_at="2026-08-07T01:00:02Z",
        )
        evidence, _, evidence_binding = self.store.load_evidence(
            run_id=RUN_ID, tick_index=1
        )
        normalization = self.store.build_public_mark_parse_receipt(
            attempt=attempt,
            raw_capture=evidence,
            value="65000.1",
            provider_as_of="2026-08-07T01:00:01Z",
            available_at="2026-08-07T01:00:02Z",
            recorded_at="2026-08-07T01:00:02Z",
        )
        self.store.commit_normalization(
            run_id=RUN_ID,
            tick_index=1,
            document=normalization,
            normalization_kind="OBSERVED_PARSE",
            committed_at="2026-08-07T01:00:02Z",
        )
        _, normalization_binding = self.store.load_normalization(
            run_id=RUN_ID, tick_index=1
        )
        raw_binding = {
            "evidence_kind": "PUBLIC_RAW_CAPTURE",
            "schema_id": evidence["schema_id"],
            "digest_field": evidence_binding["digest_field"],
            "semantic_digest": (
                "0" * 64
                if evidence_binding["semantic_digest"] != "0" * 64
                else "1" * 64
            ),
            "physical_sha256": evidence_binding["physical_sha256"],
            "recorded_at": evidence["recorded_at"],
            "raw_payload_sha256": evidence["raw_payload_sha256"],
        }
        forged = build_v32_outcome_observation_tick(
            attempt=attempt,
            raw_evidence_binding=raw_binding,
            normalized_at="2026-08-07T01:00:02Z",
            status="OBSERVED_PUBLIC_MARK",
            value="65000.1",
            provider_as_of="2026-08-07T01:00:01Z",
            available_at="2026-08-07T01:00:02Z",
            quality="HIGH",
            missingness="OBSERVED",
            conflict_state="NONE",
            parser_receipt_digest=normalization_binding["semantic_digest"],
        )
        with self.assertRaisesRegex(
            V32OutcomeTickStoreError, "OBSERVATION_PREFIX_MISMATCH"
        ):
            self.store.commit_observation_tick(
                run_id=RUN_ID,
                tick_index=1,
                observation_tick=forged,
            )

    def test_durable_replay_rejects_self_resigned_observation_digest_swap(self) -> None:
        self.register_shared_due_sets()
        self.run_tick(CapturePort())
        checkpoint = deepcopy(self.store.load_checkpoint(run_id=RUN_ID))
        observation_path = self.root / "outcome-v32/ticks/0001/observation-tick.json"
        observation = json.loads(observation_path.read_text(encoding="utf-8"))
        observation["parser_receipt_digest"] = (
            "0" * 64
            if observation["parser_receipt_digest"] != "0" * 64
            else "1" * 64
        )
        observation = self_digest(observation, "outcome_observation_tick_digest")
        physical = canonical_bytes(observation) + b"\n"
        observation_path.write_bytes(physical)
        binding = checkpoint["observation_tick_bindings"][0]
        binding["semantic_digest"] = observation[
            "outcome_observation_tick_digest"
        ]
        binding["physical_sha256"] = hashlib.sha256(physical).hexdigest()
        checkpoint = self_digest(checkpoint, "checkpoint_digest")
        (self.root / "outcome-v32/checkpoint.json").write_bytes(
            canonical_bytes(checkpoint) + b"\n"
        )
        with self.assertRaisesRegex(
            V32OutcomeTickStoreError, "OBSERVATION_PREFIX_MISMATCH"
        ):
            self.store.load_checkpoint(run_id=RUN_ID)

    def test_durable_replay_recomputes_self_resigned_normalization(self) -> None:
        self.register_shared_due_sets()
        self.run_tick(CapturePort())
        prefix = self.store.tick_prefix(run_id=RUN_ID, tick_index=1)
        checkpoint = deepcopy(self.store.load_checkpoint(run_id=RUN_ID))
        forged = self.store.build_public_mark_parse_receipt(
            attempt=prefix["attempt"],
            raw_capture=prefix["evidence"][0],
            value="1",
            provider_as_of="2026-08-07T01:00:01Z",
            available_at="2026-08-07T01:00:02Z",
            recorded_at="2026-08-07T01:00:02Z",
        )
        normalization_path = (
            self.root / "outcome-v32/ticks/0001/parse-receipt.json"
        )
        physical = canonical_bytes(forged) + b"\n"
        normalization_path.write_bytes(physical)
        binding = checkpoint["normalization_bindings"][0]
        binding["semantic_digest"] = forged["public_mark_parse_receipt_digest"]
        binding["physical_sha256"] = hashlib.sha256(physical).hexdigest()
        checkpoint = self_digest(checkpoint, "checkpoint_digest")
        (self.root / "outcome-v32/checkpoint.json").write_bytes(
            canonical_bytes(checkpoint) + b"\n"
        )
        with self.assertRaisesRegex(
            V32OutcomeTickStoreError, "NORMALIZATION_SEMANTIC_MISMATCH"
        ):
            self.store.load_checkpoint(run_id=RUN_ID)

    def test_transport_entry_and_builder_admit_only_five_physical_codes(self) -> None:
        physical_codes = (
            "PUBLIC_CONNECTION_FAILURE",
            "PUBLIC_DNS_UNAVAILABLE",
            "PUBLIC_TIMEOUT",
            "PUBLIC_TLS_FAILURE",
            "PUBLIC_TRANSPORT_IO_FAILURE",
        )
        for index, failure_code in enumerate(physical_codes):
            with self.subTest(accepted=failure_code):
                if index:
                    self.tearDown()
                    self.setUp()
                self.register_shared_due_sets()
                result = self.run_tick(CapturePort(failure=failure_code))
                self.assertEqual("RESOLVED", result["runtime_status"])
                self.assertEqual(
                    failure_code,
                    self.store.tick_prefix(run_id=RUN_ID, tick_index=1)[
                        "evidence"
                    ][0]["failure_code"],
                )
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            reserved_at="2026-08-07T01:00:01Z",
        )
        for failure_code in (
            "PUBLIC_PROVIDER_UNAVAILABLE",
            "PUBLIC_DATA_EMPTY",
        ):
            with self.subTest(rejected_by_builder=failure_code):
                with self.assertRaisesRegex(
                    V32OutcomeTickStoreError, "TRANSPORT_FAILURE_CODE_INVALID"
                ):
                    build_v32_public_transport_failure(
                        attempt=attempt,
                        failure_code=failure_code,
                        failure_at="2026-08-07T01:00:02Z",
                    )

    def test_response_backed_codes_are_rejected_as_no_response_envelopes(self) -> None:
        for index, failure_code in enumerate(
            ("PUBLIC_PROVIDER_UNAVAILABLE", "PUBLIC_DATA_EMPTY")
        ):
            with self.subTest(failure_code=failure_code):
                if index:
                    self.tearDown()
                    self.setUp()
                self.register_shared_due_sets()
                with self.assertRaisesRegex(
                    V32OutcomeTickCompositionError,
                    "TRANSPORT_FAILURE_CODE_INVALID",
                ):
                    self.run_tick(CapturePort(failure=failure_code))
                checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
                self.assertEqual("FAILED_CLOSED", checkpoint["status"])
                self.assertEqual(0, len(checkpoint["evidence_bindings"]))

    def test_503_is_raw_bound_coverage_but_400_is_structural(self) -> None:
        with self.subTest(status=503):
            self.register_shared_due_sets()
            raw = b'{"code":"500","msg":"unavailable","data":[]}'
            result = self.run_tick(
                CapturePort(raw=raw, http_status=503)
            )
            self.assertEqual(
                ["UNKNOWN_COVERAGE_LOSS"], result["resolution_statuses"]
            )
            prefix = self.store.tick_prefix(run_id=RUN_ID, tick_index=1)
            capture = prefix["evidence"][0]
            self.assertEqual(503, capture["http_status"])
            self.assertEqual(raw, prefix["evidence"][1])
            self.assertEqual(
                "PUBLIC_RAW_CAPTURE",
                prefix["observation_tick"]["raw_evidence_binding"][
                    "evidence_kind"
                ],
            )

        with self.subTest(status=400):
            self.tearDown()
            self.setUp()
            self.register_shared_due_sets()
            raw = b'{"code":"400","msg":"bad request","data":[]}'
            with self.assertRaisesRegex(
                V32OutcomeTickCompositionError,
                "HTTP_STATUS_STRUCTURAL_FAILURE",
            ):
                self.run_tick(CapturePort(raw=raw, http_status=400))
            prefix = self.store.tick_prefix(run_id=RUN_ID, tick_index=1)
            self.assertEqual(400, prefix["evidence"][0]["http_status"])
            self.assertEqual(raw, prefix["evidence"][1])
            self.assertEqual(
                "FAILED_CLOSED",
                self.store.load_checkpoint(run_id=RUN_ID)["status"],
            )

    def test_redirect_and_response_clock_failure_keep_raw_before_fail_closed(self) -> None:
        cases = (
            (
                "redirect",
                CapturePort(
                    final_url="https://openapi.okx.com/api/v5/public/time"
                ),
                "RESPONSE_IDENTITY_STRUCTURAL_FAILURE",
            ),
            (
                "clock",
                CapturePort(
                    response_at="2026-08-07T01:00:00Z",
                    captured_at="2026-08-07T01:00:02Z",
                ),
                "RESPONSE_CLOCK_STRUCTURAL_FAILURE",
            ),
        )
        for index, (label, capture, code) in enumerate(cases):
            with self.subTest(label=label):
                if index:
                    self.tearDown()
                    self.setUp()
                self.register_shared_due_sets()
                with self.assertRaisesRegex(
                    V32OutcomeTickCompositionError, code
                ):
                    self.run_tick(capture)
                prefix = self.store.tick_prefix(run_id=RUN_ID, tick_index=1)
                self.assertEqual(capture.raw, prefix["evidence"][1])
                self.assertEqual(
                    "FAILED_CLOSED",
                    self.store.load_checkpoint(run_id=RUN_ID)["status"],
                )

    def test_bounded_provider_clock_ahead_is_preserved_as_medium_quality(self) -> None:
        self.register_shared_due_sets()
        capture = CapturePort(raw=raw_mark(ts="1786064405000"))
        result = self.run_tick(capture)
        self.assertEqual("RESOLVED", result["runtime_status"])
        normalization, _ = self.store.load_normalization(
            run_id=RUN_ID, tick_index=1
        )
        self.assertEqual(3000, normalization["provider_clock_ahead_milliseconds"])
        self.assertEqual(
            "WITHIN_BOUND_PROVIDER_AHEAD",
            normalization["clock_uncertainty_status"],
        )
        self.assertEqual("MEDIUM", normalization["quality"])
        prefix = self.store.tick_prefix(run_id=RUN_ID, tick_index=1)
        self.assertEqual("MEDIUM", prefix["observation_tick"]["quality"])

    def test_provider_clock_ahead_beyond_bound_fails_closed(self) -> None:
        self.register_shared_due_sets()
        capture = CapturePort(raw=raw_mark(ts="1786064408001"))
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "FUTURE_DATUM_FORBIDDEN"
        ):
            self.run_tick(capture)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertEqual(1, len(checkpoint["evidence_bindings"]))
        self.assertEqual(0, len(checkpoint["normalization_bindings"]))

    def test_typed_transport_exception_becomes_terminal_coverage_loss(self) -> None:
        self.register_shared_due_sets()
        capture = RaisingCapturePort(
            V32PublicTransportUnavailableError(
                "V32_OKX_PUBLIC_TRANSPORT_UNAVAILABLE:PUBLIC_TIMEOUT",
                coverage_failure_code="PUBLIC_TIMEOUT",
                failure_at="2026-08-07T01:00:02Z",
            )
        )
        result = self.run_tick(capture)
        self.assertEqual("RESOLVED", result["runtime_status"])
        self.assertEqual(["UNKNOWN_COVERAGE_LOSS"], result["resolution_statuses"])
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("ACTIVE", checkpoint["status"])
        self.assertEqual(1, len(checkpoint["evidence_bindings"]))
        self.assertEqual(
            "PUBLIC_TRANSPORT_FAILURE_RECEIPT",
            checkpoint["evidence_bindings"][0]["evidence_kind"],
        )
        prefix = self.store.tick_prefix(run_id=RUN_ID, tick_index=1)
        self.assertEqual("PUBLIC_TIMEOUT", prefix["evidence"][0]["failure_code"])
        self.assertEqual(
            "2026-08-07T01:00:02Z",
            prefix["evidence"][0]["failure_at"],
        )

    def test_untyped_capture_defect_is_structural_and_not_coverage(self) -> None:
        self.register_shared_due_sets()
        capture = RaisingCapturePort(ValueError("adapter contract defect"))
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "UNEXPECTED_STRUCTURAL_FAILURE"
        ):
            self.run_tick(capture)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertEqual(0, len(checkpoint["evidence_bindings"]))
        self.assertEqual(0, len(checkpoint["normalization_bindings"]))

    def test_reserved_without_evidence_fails_closed_and_never_calls_again(self) -> None:
        self.register_shared_due_sets()
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            reserved_at="2026-08-07T01:00:01Z",
        )
        self.store.reserve_attempt(
            attempt=attempt,
            expected_checkpoint_digest=checkpoint["checkpoint_digest"],
        )
        capture = CapturePort()
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "RESERVED_RAW_NOT_BOUND"
        ):
            self.run_tick(capture)
        self.assertEqual(0, capture.calls)
        failed = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", failed["status"])
        self.assertFalse(failed["retry_allowed"])

    def test_durable_raw_prefix_resumes_parse_and_tail_without_network(self) -> None:
        self.register_shared_due_sets()
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            reserved_at="2026-08-07T01:00:01Z",
        )
        self.store.reserve_attempt(
            attempt=attempt,
            expected_checkpoint_digest=checkpoint["checkpoint_digest"],
        )
        self.store.commit_raw_capture(
            run_id=RUN_ID,
            tick_index=1,
            raw_payload=raw_mark(),
            recorded_at="2026-08-07T01:00:02Z",
        )
        capture = CapturePort()
        result = self.run_tick(capture)
        self.assertEqual("RESOLVED", result["runtime_status"])
        self.assertEqual(0, result["network_request_count"])
        self.assertEqual(0, capture.calls)

    def test_partial_receipt_crash_resumes_exact_tail_without_network(self) -> None:
        crash_store = CrashAfterFirstReceiptStore(self.root)
        self.register_shared_due_sets(store=crash_store)
        capture = CapturePort()
        with self.assertRaises(InjectedCrash):
            self.run_tick(capture, store=crash_store)
        checkpoint = crash_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(1, len(checkpoint["outcome_receipt_bindings"]))
        self.assertEqual(0, len(checkpoint["batch_completion_bindings"]))
        crash_store.crash_enabled = False
        recovered = self.run_tick(capture, store=crash_store)
        self.assertEqual("RESOLVED", recovered["runtime_status"])
        self.assertEqual(0, recovered["network_request_count"])
        self.assertEqual(1, capture.calls)
        self.assertEqual(
            2,
            len(crash_store.load_tick_receipts(run_id=RUN_ID, tick_index=1)),
        )

    def test_parse_failure_preserves_raw_and_fails_closed(self) -> None:
        self.register_shared_due_sets()
        capture = CapturePort(raw=b'{"code":"0","data":[')
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "RAW_JSON_INVALID"
        ):
            self.run_tick(capture)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertEqual(1, len(checkpoint["evidence_bindings"]))
        self.assertEqual(0, len(checkpoint["normalization_bindings"]))
        raw_path = self.root / "outcome-v32/ticks/0001/raw/raw.bin"
        self.assertEqual(b'{"code":"0","data":[', raw_path.read_bytes())

    def test_zero_byte_body_is_preserved_before_structural_failure(self) -> None:
        self.register_shared_due_sets()
        capture = CapturePort(raw=b"")
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "RAW_JSON_INVALID"
        ):
            self.run_tick(capture)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertEqual(1, len(checkpoint["evidence_bindings"]))
        self.assertEqual(0, len(checkpoint["normalization_bindings"]))
        raw_path = self.root / "outcome-v32/ticks/0001/raw/raw.bin"
        self.assertTrue(raw_path.is_file())
        self.assertEqual(b"", raw_path.read_bytes())
        self.assertEqual(1, capture.calls)

    def test_required_datum_field_missing_is_structural_after_raw_capture(self) -> None:
        self.register_shared_due_sets()
        raw = (
            b'{"code":"0","msg":"","data":['
            b'{"instType":"SWAP","instId":"BTC-USDT-SWAP","ts":"1786064401000"}]}'
        )
        capture = CapturePort(raw=raw)
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "RAW_DATUM_SCHEMA_INVALID"
        ):
            self.run_tick(capture)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertEqual(1, len(checkpoint["evidence_bindings"]))
        self.assertEqual(
            raw,
            (self.root / "outcome-v32/ticks/0001/raw/raw.bin").read_bytes(),
        )
        self.assertEqual(1, capture.calls)

    def test_http_200_provider_error_code_is_structural_after_raw_capture(self) -> None:
        self.register_shared_due_sets()
        raw = b'{"code":"50011","msg":"provider error","data":[]}'
        capture = CapturePort(raw=raw)
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError,
            "RAW_PROVIDER_CODE_STRUCTURAL_FAILURE",
        ):
            self.run_tick(capture)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertEqual(1, len(checkpoint["evidence_bindings"]))
        self.assertEqual(0, len(checkpoint["normalization_bindings"]))
        self.assertEqual(
            raw,
            (self.root / "outcome-v32/ticks/0001/raw/raw.bin").read_bytes(),
        )
        self.assertEqual(1, capture.calls)

    def test_future_schedule_is_not_captured(self) -> None:
        future = schedule_set(cycle=1, decision_time="2026-08-07T02:00:00Z")
        before_sets = self.store.load_schedule_sets(run_id=RUN_ID)
        analysis_permit = build_v32_analysis_tick_permit(
            checkpoint=self.supervisor_checkpoint,
            schedule_sets=before_sets,
            analysis_decision_at="2026-08-07T02:00:00Z",
            issued_at="2026-08-07T02:00:01Z",
            research_checkpoint_digest=self.supervisor_checkpoint[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=self.supervisor_checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=self.supervisor_checkpoint[
                "current_timeframe_cache_digest"
            ],
            prior_dynamic_state_digest=None,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=self.supervisor_checkpoint,
            permit=analysis_permit,
            schedule_sets=before_sets,
            updated_at=analysis_permit["issued_at"],
        )
        outcome_after_schedule = self.store.register_schedule_set(
            schedule_set=future, registered_at="2026-08-07T02:00:02Z"
        )
        self.supervisor_checkpoint = complete_v32_analysis_tick(
            checkpoint=opened,
            permit=analysis_permit,
            schedule_sets_before=before_sets,
            new_schedule_set=future,
            accepted_state_digest="1" * 64,
            source_admission_digest="2" * 64,
            source_admission_physical_sha256="3" * 64,
            proposal_lifecycle_digest="4" * 64,
            selection_lifecycle_digest="5" * 64,
            final_action_plan_digest="6" * 64,
            commit_envelope_digest="7" * 64,
            shadow_decision_bundle_digest="0" * 64,
            new_research_checkpoint_digest="8" * 64,
            new_outcome_checkpoint_digest=outcome_after_schedule[
                "checkpoint_digest"
            ],
            new_timeframe_cache_digest="9" * 64,
            new_dynamic_state_digest="a" * 64,
            completed_at="2026-08-07T02:00:03Z",
        )
        capture = CapturePort()
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T02:00:00Z",
            reserved_at="2026-08-07T02:00:04Z",
        )
        with self.assertRaisesRegex(V32TickSupervisorError, "NO_DUE"):
            build_v32_outcome_tick_permit(
                checkpoint=self.supervisor_checkpoint,
                schedule_sets=self.store.load_schedule_sets(run_id=RUN_ID),
                tick_attempt=attempt,
                issued_at="2026-08-07T02:00:04Z",
            )
        self.assertEqual(0, capture.calls)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(0, len(checkpoint["attempt_bindings"]))

    def test_stale_outcome_checkpoint_permit_is_rejected(self) -> None:
        self.register_shared_due_sets()
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            reserved_at="2026-08-07T01:00:01Z",
        )
        schedule_sets = self.store.load_schedule_sets(run_id=RUN_ID)
        permit = build_v32_outcome_tick_permit(
            checkpoint=self.supervisor_checkpoint,
            schedule_sets=schedule_sets,
            tick_attempt=attempt,
            issued_at="2026-08-07T01:00:01Z",
        )
        stale = deepcopy(permit)
        stale["outcome_checkpoint_digest"] = build_v32_outcome_tick_checkpoint(
            run_id=RUN_ID, created_at="2026-08-07T00:00:00Z"
        )["checkpoint_digest"]
        stale = self_digest(stale, SUPERVISOR_PERMIT_DIGEST_FIELD)
        opened = deepcopy(
            open_v32_tick_supervisor_permit(
                checkpoint=self.supervisor_checkpoint,
                permit=permit,
                schedule_sets=schedule_sets,
                tick_attempt=attempt,
                updated_at="2026-08-07T01:00:01Z",
            )
        )
        opened["active_permit_digest"] = stale[SUPERVISOR_PERMIT_DIGEST_FIELD]
        opened = self_digest(opened, SUPERVISOR_CHECKPOINT_DIGEST_FIELD)
        capture = CapturePort()
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "SUPERVISOR_PERMIT_INVALID"
        ):
            run_v32_outcome_tick(
                store=self.store,
                capture_port=capture,
                run_id=RUN_ID,
                tick_index=1,
                planned_tick_at="2026-08-07T01:00:00Z",
                requested_at="2026-08-07T01:00:01Z",
                supervisor_checkpoint_before_permit=self.supervisor_checkpoint,
                supervisor_open_checkpoint=opened,
                supervisor_permit=stale,
            )
        self.assertEqual(0, capture.calls)

    def test_schedule_registry_and_outcome_checkpoint_mismatch_is_rejected(
        self,
    ) -> None:
        self.register_shared_due_sets()
        mismatched = deepcopy(self.supervisor_checkpoint)
        mismatched["current_outcome_checkpoint_digest"] = "f" * 64
        mismatched = self_digest(
            mismatched, SUPERVISOR_CHECKPOINT_DIGEST_FIELD
        )
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            reserved_at="2026-08-07T01:00:01Z",
        )
        schedule_sets = self.store.load_schedule_sets(run_id=RUN_ID)
        permit = build_v32_outcome_tick_permit(
            checkpoint=mismatched,
            schedule_sets=schedule_sets,
            tick_attempt=attempt,
            issued_at="2026-08-07T01:00:01Z",
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=mismatched,
            permit=permit,
            schedule_sets=schedule_sets,
            tick_attempt=attempt,
            updated_at="2026-08-07T01:00:01Z",
        )
        capture = CapturePort()
        with self.assertRaisesRegex(
            V32OutcomeTickCompositionError, "SUBSTORE_BINDING_INVALID"
        ):
            run_v32_outcome_tick(
                store=self.store,
                capture_port=capture,
                run_id=RUN_ID,
                tick_index=1,
                planned_tick_at="2026-08-07T01:00:00Z",
                requested_at="2026-08-07T01:00:01Z",
                supervisor_checkpoint_before_permit=mismatched,
                supervisor_open_checkpoint=opened,
                supervisor_permit=permit,
            )
        self.assertEqual(0, capture.calls)

    def test_store_freezes_sixteen_cycles_and_forty_eight_schedules(self) -> None:
        base = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
        for cycle in range(1, 17):
            decided = base + timedelta(minutes=15 * (cycle - 1))
            document = schedule_set(cycle=cycle, decision_time=iso(decided))
            self.store.register_schedule_set(
                schedule_set=document,
                registered_at=iso(decided + timedelta(seconds=2)),
            )
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(16, checkpoint["total_cycles"])
        self.assertEqual(48, checkpoint["total_schedules"])
        self.assertEqual(16, len(checkpoint["schedule_set_bindings"]))
        self.assertEqual(
            48,
            sum(
                len(document["schedules"])
                for document in self.store.load_schedule_sets(run_id=RUN_ID)
            ),
        )

    def test_path_symlink_tamper_and_stale_cas_are_rejected(self) -> None:
        with self.assertRaisesRegex(V32OutcomeTickStoreError, "PATH_INVALID"):
            self.store._safe_path("../escape.json")
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(V32OutcomeTickStoreError, "SYMLINK"):
            self.store._safe_path("linked/escape.json")

        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        first = schedule_set(cycle=1, decision_time="2026-08-07T00:00:00Z")
        self.store.register_schedule_set(
            schedule_set=first, registered_at="2026-08-07T00:00:02Z"
        )
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=1,
            planned_tick_at="2026-08-07T01:00:00Z",
            reserved_at="2026-08-07T01:00:01Z",
        )
        with self.assertRaisesRegex(V32OutcomeTickStoreError, "CAS_CONFLICT"):
            self.store.reserve_attempt(
                attempt=attempt,
                expected_checkpoint_digest=checkpoint["checkpoint_digest"],
            )

        path = self.root / "outcome-v32/schedules/cycle-0001.json"
        path.write_bytes(path.read_bytes().replace(b"decision:0001", b"decision:xxxx"))
        with self.assertRaisesRegex(V32OutcomeTickStoreError, "BINDING|DIGEST"):
            self.store.load_checkpoint(run_id=RUN_ID)


if __name__ == "__main__":
    unittest.main()
