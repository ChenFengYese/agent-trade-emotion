from __future__ import annotations

import copy
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    BATCH_INTENT_DIGEST_FIELD,
    OUTCOME_RECEIPT_DIGEST_FIELD,
    V32OutcomeTickError,
    build_v32_analysis_clock_view,
    build_v32_outcome_observation_tick,
    build_v32_outcome_resolution_batch,
    build_v32_outcome_resolution_batch_intent,
    build_v32_outcome_schedule_set,
    build_v32_outcome_tail_recovery,
    build_v32_outcome_tick_attempt,
    build_v32_public_market_outcome_receipt,
    classify_v32_outcome_schedule_time,
    verify_v32_analysis_clock_view,
    verify_v32_outcome_observation_tick,
    verify_v32_outcome_resolution_batch,
    verify_v32_outcome_resolution_batch_intent,
    verify_v32_outcome_schedule_set,
    verify_v32_outcome_schedule,
    verify_v32_outcome_tail_recovery,
    verify_v32_outcome_tick_attempt,
    verify_v32_public_market_outcome_receipt,
)


RUN_ID = "run:v32:outcome-tick-domain"


def schedule_set(*, cycle: int, decision_time: str, run_id: str = RUN_ID) -> dict:
    return build_v32_outcome_schedule_set(
        run_id=run_id,
        decision_id=f"decision:{cycle:04d}",
        cycle_index=cycle,
        decision_time=decision_time,
        scheduled_at=(
            "2026-08-07T00:00:01Z"
            if cycle == 1
            else "2026-08-07T00:45:01Z"
        ),
        sealed_decision_digest=("a" if cycle == 1 else "b") * 64,
        evaluation_contract_digest="c" * 64,
    )


def attempt(*, run_id: str = RUN_ID, tick_index: int = 1) -> dict:
    return build_v32_outcome_tick_attempt(
        run_id=run_id,
        tick_index=tick_index,
        planned_tick_at="2026-08-07T01:00:00Z",
        reserved_at="2026-08-07T01:00:01Z",
    )


def raw_binding(*, suffix: str = "d") -> dict:
    return {
        "evidence_kind": "PUBLIC_RAW_CAPTURE",
        "schema_id": "theory_paper_v32_public_raw_capture_v1",
        "digest_field": "public_raw_capture_digest",
        "semantic_digest": suffix * 64,
        "physical_sha256": "e" * 64,
        "recorded_at": "2026-08-07T01:00:02Z",
        "raw_payload_sha256": "f" * 64,
    }


def failure_binding(kind: str) -> dict:
    binding = raw_binding()
    if kind == "PUBLIC_TRANSPORT_FAILURE_RECEIPT":
        binding.update(
            {
                "evidence_kind": kind,
                "schema_id": "theory_paper_v32_public_transport_failure_v1",
                "digest_field": "public_transport_failure_digest",
                "raw_payload_sha256": None,
            }
        )
    elif kind == "PUBLIC_COVERAGE_FAILURE_RECEIPT":
        binding.update(
            {
                "evidence_kind": kind,
                "schema_id": "theory_paper_v32_public_coverage_failure_v1",
                "digest_field": "public_coverage_failure_digest",
                "raw_payload_sha256": None,
            }
        )
    return binding


def observed_tick(tick_attempt: dict, *, binding: dict | None = None) -> dict:
    return build_v32_outcome_observation_tick(
        attempt=tick_attempt,
        raw_evidence_binding=binding or raw_binding(),
        normalized_at="2026-08-07T01:00:03Z",
        status="OBSERVED_PUBLIC_MARK",
        value="65000.1",
        provider_as_of="2026-08-07T01:00:01Z",
        available_at="2026-08-07T01:00:02Z",
        quality="HIGH",
        missingness="OBSERVED",
        conflict_state="NONE",
        parser_receipt_digest="1" * 64,
    )


def coverage_tick(tick_attempt: dict) -> dict:
    return build_v32_outcome_observation_tick(
        attempt=tick_attempt,
        raw_evidence_binding=failure_binding(
            "PUBLIC_TRANSPORT_FAILURE_RECEIPT"
        ),
        normalized_at="2026-08-07T01:00:03Z",
        status="UNKNOWN_COVERAGE_LOSS",
        value=None,
        provider_as_of=None,
        available_at="2026-08-07T01:00:02Z",
        quality="UNKNOWN",
        missingness="UNKNOWN",
        conflict_state="PUBLIC_TIMEOUT",
        parser_receipt_digest="2" * 64,
    )


class V32OutcomeTickContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = schedule_set(cycle=1, decision_time="2026-08-07T00:00:00Z")
        self.second = schedule_set(cycle=2, decision_time="2026-08-07T00:45:00Z")
        self.attempt = attempt()
        self.tick = observed_tick(self.attempt)
        self.batch = build_v32_outcome_resolution_batch_intent(
            attempt=self.attempt,
            observation_tick=self.tick,
            schedule_sets=[self.first, self.second],
            created_at="2026-08-07T01:00:04Z",
        )
        self.receipts = [
            build_v32_public_market_outcome_receipt(
                batch_intent=self.batch,
                attempt=self.attempt,
                observation_tick=self.tick,
                schedule_sets=[self.first, self.second],
                schedule_id=schedule_id,
                resolved_at="2026-08-07T01:00:05Z",
            )
            for schedule_id in self.batch["due_schedule_ids"]
        ]

    def test_schedule_set_freezes_exact_three_horizons_and_separate_clocks(self) -> None:
        self.assertEqual(
            self.first["outcome_schedule_set_digest"],
            verify_v32_outcome_schedule_set(self.first),
        )
        self.assertEqual(
            [(row["horizon"], row["horizon_seconds"]) for row in self.first["schedules"]],
            [("15M", 900), ("1H", 3600), ("4H", 14400)],
        )
        self.assertEqual(
            "FUTURE_OUTCOMES_UNREADABLE_AND_DO_NOT_BLOCK_ANALYSIS",
            self.first["analysis_clock_policy"],
        )
        self.assertTrue(all(not row["fill_claim"] for row in self.first["schedules"]))

    def test_attempt_and_tick_are_exactly_once_and_raw_first(self) -> None:
        self.assertEqual(
            self.attempt["outcome_tick_attempt_digest"],
            verify_v32_outcome_tick_attempt(self.attempt),
        )
        self.assertEqual(1, self.attempt["max_network_requests"])
        self.assertFalse(self.attempt["retry_allowed"])
        self.assertEqual(
            self.tick["outcome_observation_tick_digest"],
            verify_v32_outcome_observation_tick(self.tick, attempt=self.attempt),
        )
        self.assertEqual(
            self.tick["raw_evidence_binding"]["semantic_digest"],
            self.batch["raw_evidence_digest"],
        )
        late_raw = raw_binding()
        late_raw["recorded_at"] = "2026-08-07T01:00:04Z"
        with self.assertRaisesRegex(V32OutcomeTickError, "RAW_FIRST"):
            observed_tick(self.attempt, binding=late_raw)

    def test_schedule_time_classification_supports_arbitrary_microseconds(self) -> None:
        schedules = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision:microsecond-boundary",
            cycle_index=1,
            decision_time="2026-08-07T00:00:01.123456Z",
            scheduled_at="2026-08-07T00:00:01.123456Z",
            sealed_decision_digest="a" * 64,
            evaluation_contract_digest="c" * 64,
        )
        schedule = schedules["schedules"][0]
        self.assertEqual(
            schedule["schedule_digest"], verify_v32_outcome_schedule(schedule)
        )
        self.assertEqual(
            "FUTURE",
            classify_v32_outcome_schedule_time(
                schedule, now="2026-08-07T00:15:01.123455Z"
            ),
        )
        self.assertEqual(
            "DUE",
            classify_v32_outcome_schedule_time(
                schedule, now="2026-08-07T00:15:01.123456Z"
            ),
        )
        self.assertEqual(
            "DUE",
            classify_v32_outcome_schedule_time(
                schedule, now="2026-08-07T00:30:01.123456Z"
            ),
        )
        self.assertEqual(
            "EXPIRED",
            classify_v32_outcome_schedule_time(
                schedule, now="2026-08-07T00:30:01.123457Z"
            ),
        )

        tampered = copy.deepcopy(schedule)
        tampered["expires_at"] = "2026-08-07T00:30:01.123457Z"
        with self.assertRaisesRegex(V32OutcomeTickError, "SCHEDULE_TIME_INVALID"):
            classify_v32_outcome_schedule_time(
                tampered, now="2026-08-07T00:15:01.123456Z"
            )

    def test_attempt_accepts_arbitrary_time_and_inclusive_grace_boundaries(self) -> None:
        arbitrary = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=2,
            planned_tick_at="2026-08-07T01:07:13.123456Z",
            reserved_at="2026-08-07T01:07:13.123456Z",
        )
        self.assertEqual(
            arbitrary["outcome_tick_attempt_digest"],
            verify_v32_outcome_tick_attempt(arbitrary),
        )
        at_grace = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=3,
            planned_tick_at="2026-08-07T01:07:13.123456Z",
            reserved_at="2026-08-07T01:22:13.123456Z",
        )
        self.assertEqual(
            at_grace["outcome_tick_attempt_digest"],
            verify_v32_outcome_tick_attempt(at_grace),
        )
        with self.assertRaisesRegex(V32OutcomeTickError, "RESERVATION_TIME_INVALID"):
            build_v32_outcome_tick_attempt(
                run_id=RUN_ID,
                tick_index=4,
                planned_tick_at="2026-08-07T01:07:13.123456Z",
                reserved_at="2026-08-07T01:07:13.123455Z",
            )
        with self.assertRaisesRegex(V32OutcomeTickError, "RESERVATION_TIME_INVALID"):
            build_v32_outcome_tick_attempt(
                run_id=RUN_ID,
                tick_index=5,
                planned_tick_at="2026-08-07T01:07:13.123456Z",
                reserved_at="2026-08-07T01:22:13.123457Z",
            )

    def test_one_tick_resolves_multiple_decisions_and_horizons(self) -> None:
        self.assertEqual(3, len(self.batch["due_schedule_ids"]))
        dispositions = {
            (row["horizon"], row["outcome_not_before"]): row
            for row in self.batch["outcome_dispositions"]
        }
        self.assertEqual(
            "UNKNOWN_COVERAGE_LOSS",
            dispositions[("15M", "2026-08-07T00:15:00Z")]["resolution_status"],
        )
        self.assertEqual(
            "OBSERVATION_WINDOW_MISSED",
            dispositions[("15M", "2026-08-07T00:15:00Z")]["coverage_loss_reason"],
        )
        self.assertEqual(
            "OBSERVED_PUBLIC_MARK",
            dispositions[("1H", "2026-08-07T01:00:00Z")]["resolution_status"],
        )
        self.assertEqual(
            "OBSERVED_PUBLIC_MARK",
            dispositions[("15M", "2026-08-07T01:00:00Z")]["resolution_status"],
        )
        self.assertEqual(3, len(self.batch["future_schedule_ids"]))
        self.assertEqual(
            self.batch[BATCH_INTENT_DIGEST_FIELD],
            verify_v32_outcome_resolution_batch_intent(
                self.batch,
                attempt=self.attempt,
                observation_tick=self.tick,
                schedule_sets=[self.first, self.second],
            ),
        )

    def test_future_schedule_cannot_be_read_or_used_to_build_a_batch(self) -> None:
        early_attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=2,
            planned_tick_at="2026-08-07T00:45:00Z",
            reserved_at="2026-08-07T00:45:01Z",
        )
        binding = raw_binding()
        binding["recorded_at"] = "2026-08-07T00:45:02Z"
        early_tick = build_v32_outcome_observation_tick(
            attempt=early_attempt,
            raw_evidence_binding=binding,
            normalized_at="2026-08-07T00:45:03Z",
            status="OBSERVED_PUBLIC_MARK",
            value="64900",
            provider_as_of="2026-08-07T00:45:01Z",
            available_at="2026-08-07T00:45:02Z",
            quality="HIGH",
            missingness="OBSERVED",
            conflict_state="NONE",
            parser_receipt_digest="3" * 64,
        )
        with self.assertRaisesRegex(V32OutcomeTickError, "NO_MATURE_SCHEDULES"):
            build_v32_outcome_resolution_batch_intent(
                attempt=early_attempt,
                observation_tick=early_tick,
                schedule_sets=[self.second],
                created_at="2026-08-07T00:45:04Z",
            )
        view = build_v32_analysis_clock_view(
            run_id=RUN_ID,
            cycle_index=3,
            decision_time="2026-08-07T00:45:30Z",
            schedule_sets=[self.second],
            terminal_outcome_receipts=[],
        )
        self.assertTrue(view["analysis_allowed"])
        self.assertFalse(view["future_outcomes_readable"])
        self.assertFalse(view["future_outcomes_block_analysis"])
        self.assertEqual(3, len(view["future_schedule_ids"]))
        self.assertEqual(
            view["analysis_clock_view_digest"],
            verify_v32_analysis_clock_view(
                view,
                schedule_sets=[self.second],
                terminal_outcome_receipts=[],
            ),
        )

    def test_due_unresolved_tail_blocks_only_until_terminal_receipt_exists(self) -> None:
        before = build_v32_analysis_clock_view(
            run_id=RUN_ID,
            cycle_index=3,
            decision_time="2026-08-07T01:00:10Z",
            schedule_sets=[self.second],
            terminal_outcome_receipts=[],
        )
        self.assertFalse(before["analysis_allowed"])
        second_15m = next(
            receipt
            for receipt in self.receipts
            if receipt["decision_id"] == "decision:0002"
            and receipt["horizon"] == "15M"
        )
        after = build_v32_analysis_clock_view(
            run_id=RUN_ID,
            cycle_index=3,
            decision_time="2026-08-07T01:00:10Z",
            schedule_sets=[self.second],
            terminal_outcome_receipts=[second_15m],
        )
        self.assertTrue(after["analysis_allowed"])
        self.assertEqual(2, len(after["future_schedule_ids"]))
        self.assertEqual(1, len(after["available_outcome_receipt_digests"]))

    def test_transport_failure_is_terminal_unknown_coverage_not_zero(self) -> None:
        failed_tick = coverage_tick(self.attempt)
        batch = build_v32_outcome_resolution_batch_intent(
            attempt=self.attempt,
            observation_tick=failed_tick,
            schedule_sets=[self.first, self.second],
            created_at="2026-08-07T01:00:04Z",
        )
        receipts = [
            build_v32_public_market_outcome_receipt(
                batch_intent=batch,
                attempt=self.attempt,
                observation_tick=failed_tick,
                schedule_sets=[self.first, self.second],
                schedule_id=schedule_id,
                resolved_at="2026-08-07T01:00:05Z",
            )
            for schedule_id in batch["due_schedule_ids"]
        ]
        self.assertTrue(receipts)
        for receipt in receipts:
            self.assertEqual("UNKNOWN_COVERAGE_LOSS", receipt["resolution_status"])
            self.assertIsNone(receipt["value"])
            self.assertTrue(receipt["terminal"])
            self.assertEqual(1, receipt["attempt_count"])
            self.assertFalse(receipt["retry_allowed"])

    def test_stop_trigger_is_never_a_fill_position_or_pnl_claim(self) -> None:
        for receipt in self.receipts:
            self.assertEqual(
                "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL",
                receipt["stop_trigger_semantics"],
            )
            self.assertFalse(receipt["trigger_is_fill"])
            self.assertFalse(receipt["fill_claim"])
            self.assertFalse(receipt["position_claim"])
            self.assertFalse(receipt["pnl_claim"])
            self.assertEqual(
                receipt[OUTCOME_RECEIPT_DIGEST_FIELD],
                verify_v32_public_market_outcome_receipt(
                    receipt,
                    batch_intent=self.batch,
                    attempt=self.attempt,
                    observation_tick=self.tick,
                    schedule_sets=[self.first, self.second],
                ),
            )

    def test_complete_batch_requires_exactly_one_receipt_per_due_schedule(self) -> None:
        with self.assertRaisesRegex(V32OutcomeTickError, "SET_INCOMPLETE"):
            build_v32_outcome_resolution_batch(
                batch_intent=self.batch,
                outcome_receipts=self.receipts[:-1],
                completed_at="2026-08-07T01:00:06Z",
            )
        with self.assertRaisesRegex(V32OutcomeTickError, "DUPLICATE"):
            build_v32_outcome_resolution_batch(
                batch_intent=self.batch,
                outcome_receipts=self.receipts + [self.receipts[0]],
                completed_at="2026-08-07T01:00:06Z",
            )
        completion = build_v32_outcome_resolution_batch(
            batch_intent=self.batch,
            outcome_receipts=self.receipts,
            completed_at="2026-08-07T01:00:06Z",
        )
        self.assertEqual(0, completion["network_requests_during_tail"])
        self.assertTrue(completion["all_due_schedules_terminal"])
        self.assertEqual(
            completion["outcome_resolution_batch_digest"],
            verify_v32_outcome_resolution_batch(
                completion,
                batch_intent=self.batch,
                outcome_receipts=self.receipts,
            ),
        )

    def test_schedule_attempt_cannot_appear_in_a_second_batch(self) -> None:
        with self.assertRaisesRegex(V32OutcomeTickError, "ATTEMPT_DUPLICATE"):
            build_v32_outcome_resolution_batch_intent(
                attempt=self.attempt,
                observation_tick=self.tick,
                schedule_sets=[self.first, self.second],
                created_at="2026-08-07T01:00:04Z",
                prior_batch_intents=[self.batch],
            )
        with self.assertRaisesRegex(V32OutcomeTickError, "NO_MATURE_SCHEDULES"):
            build_v32_outcome_resolution_batch_intent(
                attempt=self.attempt,
                observation_tick=self.tick,
                schedule_sets=[self.first, self.second],
                created_at="2026-08-07T01:00:04Z",
                prior_terminal_receipts=self.receipts,
            )

    def test_crash_tail_uses_same_attempt_raw_and_batch_without_second_get(self) -> None:
        states = []
        states.append(
            build_v32_outcome_tail_recovery(
                attempt=self.attempt,
                observation_tick=None,
                batch_intent=None,
            )
        )
        states.append(
            build_v32_outcome_tail_recovery(
                attempt=self.attempt,
                observation_tick=self.tick,
                batch_intent=None,
            )
        )
        states.append(
            build_v32_outcome_tail_recovery(
                attempt=self.attempt,
                observation_tick=self.tick,
                batch_intent=self.batch,
                outcome_receipts=self.receipts[:1],
            )
        )
        states.append(
            build_v32_outcome_tail_recovery(
                attempt=self.attempt,
                observation_tick=self.tick,
                batch_intent=self.batch,
                outcome_receipts=self.receipts,
            )
        )
        completion = build_v32_outcome_resolution_batch(
            batch_intent=self.batch,
            outcome_receipts=self.receipts,
            completed_at="2026-08-07T01:00:06Z",
        )
        states.append(
            build_v32_outcome_tail_recovery(
                attempt=self.attempt,
                observation_tick=self.tick,
                batch_intent=self.batch,
                outcome_receipts=self.receipts,
                batch_completion=completion,
            )
        )
        self.assertEqual(
            [
                "FAILED_CLOSED_ATTEMPT_RESERVED_RAW_NOT_BOUND",
                "BUILD_BATCH_INTENT_FROM_SAME_BOUND_TICK",
                "BUILD_MISSING_RECEIPTS",
                "SEAL_BATCH_COMPLETION",
                "NOOP_TERMINAL_COMPLETE",
            ],
            [state["recovery_state"] for state in states],
        )
        for state in states:
            self.assertFalse(state["network_request_allowed"])
            self.assertTrue(state["same_attempt_required"])
            self.assertTrue(state["deterministic_tail_only"])
        final = states[-1]
        self.assertEqual(
            final["outcome_tail_recovery_digest"],
            verify_v32_outcome_tail_recovery(
                final,
                attempt=self.attempt,
                observation_tick=self.tick,
                batch_intent=self.batch,
                outcome_receipts=self.receipts,
                batch_completion=completion,
            ),
        )

    def test_schema_time_digest_and_run_conflicts_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.first)
        tampered["schedules"][0]["outcome_not_before"] = "2026-08-08T00:15:00Z"
        with self.assertRaisesRegex(
            V32OutcomeTickError, "SCHEDULE_SET_INVALID|RECONSTRUCTION"
        ):
            verify_v32_outcome_schedule_set(tampered)

        other_attempt = attempt(run_id="run:v32:other")
        with self.assertRaisesRegex(V32OutcomeTickError, "MISMATCH"):
            verify_v32_outcome_observation_tick(self.tick, attempt=other_attempt)

        wrong_run_set = schedule_set(
            cycle=1,
            decision_time="2026-08-07T00:00:00Z",
            run_id="run:v32:other",
        )
        with self.assertRaisesRegex(V32OutcomeTickError, "RUN_MISMATCH"):
            build_v32_outcome_resolution_batch_intent(
                attempt=self.attempt,
                observation_tick=self.tick,
                schedule_sets=[wrong_run_set],
                created_at="2026-08-07T01:00:04Z",
            )

        forged = copy.deepcopy(self.batch)
        forged["network_request_allowed_during_tail"] = True
        forged = self_digest(forged, BATCH_INTENT_DIGEST_FIELD)
        with self.assertRaisesRegex(V32OutcomeTickError, "POLICY_INVALID"):
            verify_v32_outcome_resolution_batch_intent(
                forged,
                attempt=self.attempt,
                observation_tick=self.tick,
                schedule_sets=[self.first, self.second],
            )

    def test_unknown_is_not_a_backdoor_for_structural_parse_failure(self) -> None:
        def build_unknown(*, binding: dict, conflict_state: str) -> dict:
            return build_v32_outcome_observation_tick(
                attempt=self.attempt,
                raw_evidence_binding=binding,
                normalized_at="2026-08-07T01:00:03Z",
                status="UNKNOWN_COVERAGE_LOSS",
                value=None,
                provider_as_of=None,
                available_at="2026-08-07T01:00:02Z",
                quality="UNKNOWN",
                missingness="UNKNOWN",
                conflict_state=conflict_state,
                parser_receipt_digest="4" * 64,
            )

        transport_codes = (
            "PUBLIC_CONNECTION_FAILURE",
            "PUBLIC_DNS_UNAVAILABLE",
            "PUBLIC_TIMEOUT",
            "PUBLIC_TLS_FAILURE",
            "PUBLIC_TRANSPORT_IO_FAILURE",
        )
        response_codes = (
            "PUBLIC_PROVIDER_UNAVAILABLE",
            "PUBLIC_DATA_EMPTY",
        )
        transport = failure_binding("PUBLIC_TRANSPORT_FAILURE_RECEIPT")
        coverage_receipt = failure_binding("PUBLIC_COVERAGE_FAILURE_RECEIPT")
        for conflict_state in transport_codes:
            with self.subTest(allowed_transport=conflict_state):
                self.assertEqual(
                    conflict_state,
                    build_unknown(
                        binding=transport,
                        conflict_state=conflict_state,
                    )["conflict_state"],
                )
            for invalid_binding in (raw_binding(), coverage_receipt):
                with self.subTest(
                    rejected_transport=conflict_state,
                    evidence_kind=invalid_binding["evidence_kind"],
                ):
                    with self.assertRaisesRegex(
                        V32OutcomeTickError, "FAILURE_RECEIPT_REQUIRED"
                    ):
                        build_unknown(
                            binding=invalid_binding,
                            conflict_state=conflict_state,
                        )
        for conflict_state in response_codes:
            with self.subTest(allowed_response=conflict_state):
                self.assertEqual(
                    conflict_state,
                    build_unknown(
                        binding=raw_binding(),
                        conflict_state=conflict_state,
                    )["conflict_state"],
                )
            for invalid_binding in (transport, coverage_receipt):
                with self.subTest(
                    rejected_response=conflict_state,
                    evidence_kind=invalid_binding["evidence_kind"],
                ):
                    with self.assertRaisesRegex(
                        V32OutcomeTickError, "RESPONSE_RAW_REQUIRED"
                    ):
                        build_unknown(
                            binding=invalid_binding,
                            conflict_state=conflict_state,
                        )
        for structural_failure in (
            "PUBLIC_EMPTY_BODY",
            "PUBLIC_INVALID_JSON",
            "PUBLIC_SCHEMA_INVALID",
            "PUBLIC_INSTRUMENT_MISMATCH",
        ):
            with self.subTest(structural_failure=structural_failure):
                with self.assertRaisesRegex(
                    V32OutcomeTickError, "COVERAGE_FAILURE_CODE_INVALID"
                ):
                    build_unknown(
                        binding=raw_binding(),
                        conflict_state=structural_failure,
                    )
        with self.assertRaisesRegex(V32OutcomeTickError, "OBSERVED_RAW_REQUIRED"):
            observed_tick(self.attempt, binding=transport)


if __name__ == "__main__":
    unittest.main()
