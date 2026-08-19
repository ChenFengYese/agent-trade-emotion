from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_observation_tick,
    build_v32_outcome_resolution_batch,
    build_v32_outcome_resolution_batch_intent,
    build_v32_outcome_schedule_set,
    build_v32_outcome_tick_attempt,
    build_v32_public_market_outcome_receipt,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    V32TickSupervisorError,
    build_v32_analysis_tick_permit,
    build_v32_outcome_tick_permit,
    build_v32_tick_supervisor_checkpoint,
    build_v32_tick_supervisor_failure,
    complete_v32_analysis_tick,
    complete_v32_outcome_tick,
    fail_v32_tick_supervisor,
    open_v32_tick_supervisor_permit,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_permit,
    verify_v32_tick_supervisor_transition,
)


RUN_ID = "run:v32:tick-supervisor-domain"


def ts(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def digest(seed: int | str) -> str:
    text = str(seed)
    return (text.encode().hex() * 64)[:64].ljust(64, "a")


def bootstrap() -> dict:
    return build_v32_tick_supervisor_checkpoint(
        run_id=RUN_ID,
        experiment_contract_digest="a" * 64,
        active_authority_digest="b" * 64,
        research_checkpoint_digest="c" * 64,
        outcome_checkpoint_digest="d" * 64,
        timeframe_cache_digest="e" * 64,
        created_at="2026-08-07T00:00:00Z",
    )


def analysis_cycle(
    checkpoint: dict,
    schedule_sets: list[dict],
    *,
    decision_at: datetime,
) -> tuple[dict, dict, dict]:
    issued = decision_at + timedelta(seconds=1)
    permit = build_v32_analysis_tick_permit(
        checkpoint=checkpoint,
        schedule_sets=schedule_sets,
        analysis_decision_at=ts(decision_at),
        issued_at=ts(issued),
        research_checkpoint_digest=checkpoint["current_research_checkpoint_digest"],
        outcome_checkpoint_digest=checkpoint["current_outcome_checkpoint_digest"],
        timeframe_cache_digest=checkpoint["current_timeframe_cache_digest"],
        prior_dynamic_state_digest=checkpoint["current_dynamic_state_digest"],
    )
    opened = open_v32_tick_supervisor_permit(
        checkpoint=checkpoint,
        permit=permit,
        schedule_sets=schedule_sets,
        updated_at=ts(issued),
    )
    cycle = permit["analysis_cycle_index"]
    new_set = build_v32_outcome_schedule_set(
        run_id=RUN_ID,
        decision_id=f"decision:{cycle:04d}",
        cycle_index=cycle,
        decision_time=ts(decision_at),
        scheduled_at=ts(decision_at + timedelta(seconds=2)),
        sealed_decision_digest=digest(f"sealed-{cycle}"),
        evaluation_contract_digest="f" * 64,
    )
    completed = complete_v32_analysis_tick(
        checkpoint=opened,
        permit=permit,
        schedule_sets_before=schedule_sets,
        new_schedule_set=new_set,
        accepted_state_digest=digest(f"accepted-{cycle}"),
        source_admission_digest=digest(f"source-{cycle}"),
        source_admission_physical_sha256=digest(f"source-physical-{cycle}"),
        proposal_lifecycle_digest=digest(f"proposal-{cycle}"),
        selection_lifecycle_digest=digest(f"selection-{cycle}"),
        final_action_plan_digest=digest(f"action-plan-{cycle}"),
        commit_envelope_digest=digest(f"commit-{cycle}"),
        shadow_decision_bundle_digest=digest(f"shadow-{cycle}"),
        new_research_checkpoint_digest=digest(f"research-{cycle}"),
        new_outcome_checkpoint_digest=digest(f"outcome-{cycle}"),
        new_timeframe_cache_digest=digest(f"cache-{cycle}"),
        new_dynamic_state_digest=digest(f"state-{cycle}"),
        completed_at=ts(decision_at + timedelta(seconds=3)),
    )
    return completed, permit, new_set


def raw_binding(*, recorded_at: datetime, coverage: bool) -> dict:
    if coverage:
        return {
            "evidence_kind": "PUBLIC_TRANSPORT_FAILURE_RECEIPT",
            "schema_id": "theory_paper_v32_public_transport_failure_v1",
            "digest_field": "public_transport_failure_digest",
            "semantic_digest": "1" * 64,
            "physical_sha256": "2" * 64,
            "recorded_at": ts(recorded_at),
            "raw_payload_sha256": None,
        }
    return {
        "evidence_kind": "PUBLIC_RAW_CAPTURE",
        "schema_id": "theory_paper_v32_public_raw_capture_v1",
        "digest_field": "public_raw_capture_digest",
        "semantic_digest": "3" * 64,
        "physical_sha256": "4" * 64,
        "recorded_at": ts(recorded_at),
        "raw_payload_sha256": "5" * 64,
    }


def outcome_tick(
    checkpoint: dict,
    schedule_sets: list[dict],
    prior_receipts: list[dict],
    *,
    planned_at: datetime,
    reserved_at: datetime | None = None,
    coverage: bool = False,
    instant: bool = False,
) -> tuple[dict, dict, list[dict], dict, dict]:
    reserved = reserved_at or planned_at + timedelta(seconds=0 if instant else 1)
    attempt = build_v32_outcome_tick_attempt(
        run_id=RUN_ID,
        tick_index=checkpoint["next_outcome_tick_index"],
        planned_tick_at=ts(planned_at),
        reserved_at=ts(reserved),
    )
    permit = build_v32_outcome_tick_permit(
        checkpoint=checkpoint,
        schedule_sets=schedule_sets,
        tick_attempt=attempt,
        issued_at=ts(reserved),
    )
    opened = open_v32_tick_supervisor_permit(
        checkpoint=checkpoint,
        permit=permit,
        schedule_sets=schedule_sets,
        tick_attempt=attempt,
        updated_at=ts(reserved),
    )
    recorded = reserved + timedelta(seconds=0 if instant else 1)
    normalized = reserved + timedelta(seconds=0 if instant else 2)
    created = reserved + timedelta(seconds=0 if instant else 3)
    resolved = reserved + timedelta(seconds=0 if instant else 4)
    batch_completed = reserved + timedelta(seconds=0 if instant else 5)
    supervisor_completed = reserved + timedelta(seconds=0 if instant else 6)
    if coverage:
        observation = build_v32_outcome_observation_tick(
            attempt=attempt,
            raw_evidence_binding=raw_binding(recorded_at=recorded, coverage=True),
            normalized_at=ts(normalized),
            status="UNKNOWN_COVERAGE_LOSS",
            value=None,
            provider_as_of=None,
            available_at=ts(recorded),
            quality="UNKNOWN",
            missingness="UNKNOWN",
            conflict_state="PUBLIC_TIMEOUT",
            parser_receipt_digest="6" * 64,
        )
    else:
        observation = build_v32_outcome_observation_tick(
            attempt=attempt,
            raw_evidence_binding=raw_binding(recorded_at=recorded, coverage=False),
            normalized_at=ts(normalized),
            status="OBSERVED_PUBLIC_MARK",
            value="65000",
            provider_as_of=ts(reserved),
            available_at=ts(recorded),
            quality="HIGH",
            missingness="OBSERVED",
            conflict_state="NONE",
            parser_receipt_digest="7" * 64,
        )
    batch = build_v32_outcome_resolution_batch_intent(
        attempt=attempt,
        observation_tick=observation,
        schedule_sets=schedule_sets,
        created_at=ts(created),
        prior_terminal_receipts=prior_receipts,
    )
    receipts = [
        build_v32_public_market_outcome_receipt(
            batch_intent=batch,
            attempt=attempt,
            observation_tick=observation,
            schedule_sets=schedule_sets,
            schedule_id=schedule_id,
            resolved_at=ts(resolved),
        )
        for schedule_id in batch["due_schedule_ids"]
    ]
    completion = build_v32_outcome_resolution_batch(
        batch_intent=batch,
        outcome_receipts=receipts,
        completed_at=ts(batch_completed),
    )
    completed = complete_v32_outcome_tick(
        checkpoint=opened,
        permit=permit,
        tick_attempt=attempt,
        observation_tick=observation,
        schedule_sets=schedule_sets,
        prior_terminal_receipts=prior_receipts,
        batch_intent=batch,
        outcome_receipts=receipts,
        batch_completion=completion,
        new_outcome_checkpoint_digest=digest(
            f"outcome-head-{checkpoint['next_outcome_tick_index']}"
        ),
        completed_at=ts(supervisor_completed),
    )
    return completed, permit, receipts, batch, completion


class V32TickSupervisorTests(unittest.TestCase):
    def test_successor_analysis_completion_uses_sealed_decision_clock(self) -> None:
        checkpoint = bootstrap()
        permit = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=[],
            analysis_decision_at="2026-08-07T00:00:00.123000Z",
            issued_at="2026-08-07T00:00:01.456000Z",
            research_checkpoint_digest=checkpoint[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=checkpoint["current_timeframe_cache_digest"],
            prior_dynamic_state_digest=None,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=checkpoint,
            permit=permit,
            schedule_sets=[],
            updated_at=permit["issued_at"],
        )
        sealed_at = "2026-08-07T00:00:07.789000Z"
        schedule = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision:0001:successor",
            cycle_index=1,
            decision_time=sealed_at,
            scheduled_at=sealed_at,
            sealed_decision_digest="8" * 64,
            evaluation_contract_digest="9" * 64,
        )
        kwargs = {
            "checkpoint": opened,
            "permit": permit,
            "schedule_sets_before": [],
            "new_schedule_set": schedule,
            "accepted_state_digest": "1" * 64,
            "source_admission_digest": "2" * 64,
            "source_admission_physical_sha256": "a" * 64,
            "proposal_lifecycle_digest": "b" * 64,
            "selection_lifecycle_digest": "c" * 64,
            "final_action_plan_digest": "d" * 64,
            "commit_envelope_digest": "3" * 64,
            "shadow_decision_bundle_digest": "0" * 64,
            "new_research_checkpoint_digest": "4" * 64,
            "new_outcome_checkpoint_digest": "7" * 64,
            "new_timeframe_cache_digest": "5" * 64,
            "new_dynamic_state_digest": "6" * 64,
            "completed_at": "2026-08-07T00:00:08.001000Z",
            "source_admission_schema_version": "2.0.0",
            "decision_sealed_at": sealed_at,
        }
        completed = complete_v32_analysis_tick(**kwargs)
        self.assertEqual(sealed_at, completed["last_analysis_decision_at"])

        wrong_schedule = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision:0001:wrong-clock",
            cycle_index=1,
            decision_time=permit["analysis_decision_at"],
            scheduled_at=sealed_at,
            sealed_decision_digest="8" * 64,
            evaluation_contract_digest="9" * 64,
        )
        with self.assertRaisesRegex(
            V32TickSupervisorError, "SCHEDULE_SET_IDENTITY_INVALID"
        ):
            complete_v32_analysis_tick(
                **{**kwargs, "new_schedule_set": wrong_schedule}
            )
        with self.assertRaisesRegex(
            V32TickSupervisorError, "DECISION_SEALED_TIME_INVALID"
        ):
            complete_v32_analysis_tick(
                **{
                    **kwargs,
                    "decision_sealed_at": "2026-08-07T00:00:01.455000Z",
                }
            )

    def test_pending_future_outcomes_do_not_block_next_analysis(self) -> None:
        checkpoint = bootstrap()
        schedules: list[dict] = []
        start = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
        checkpoint, _, first = analysis_cycle(
            checkpoint, schedules, decision_at=start
        )
        schedules.append(first)
        checkpoint, _, receipts, _, _ = outcome_tick(
            checkpoint,
            schedules,
            [],
            planned_at=start + timedelta(minutes=15),
        )
        self.assertEqual(1, checkpoint["terminal_outcomes"])
        permit = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=schedules,
            analysis_decision_at="2026-08-07T00:15:10Z",
            issued_at="2026-08-07T00:15:11Z",
            research_checkpoint_digest=checkpoint[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=checkpoint["current_timeframe_cache_digest"],
            prior_dynamic_state_digest=checkpoint["current_dynamic_state_digest"],
        )
        self.assertEqual("ANALYSIS_TICK", permit["permit_kind"])
        self.assertEqual(
            {"PROPOSAL": 1, "SELECTION": 1},
            permit["agent_stage_attempt_limits"],
        )
        self.assertEqual(1, permit["source_collection_transactions_allowed"])
        self.assertEqual(1, len(permit["mature_terminal_schedule_ids"]))
        self.assertEqual(2, len(permit["future_schedule_ids"]))
        self.assertEqual([], permit["due_schedule_ids"])
        self.assertFalse(permit["future_outcomes_block_analysis"])
        self.assertEqual("OBSERVED_PUBLIC_MARK", receipts[0]["resolution_status"])

    def test_matured_outstanding_schedule_blocks_analysis(self) -> None:
        checkpoint = bootstrap()
        checkpoint, _, first = analysis_cycle(
            checkpoint,
            [],
            decision_at=datetime(2026, 8, 7, 0, 0, tzinfo=UTC),
        )
        with self.assertRaisesRegex(V32TickSupervisorError, "CADENCE_INVALID"):
            build_v32_analysis_tick_permit(
                checkpoint=checkpoint,
                schedule_sets=[first],
                analysis_decision_at="2026-08-07T00:14:59Z",
                issued_at="2026-08-07T00:14:59Z",
                research_checkpoint_digest=checkpoint[
                    "current_research_checkpoint_digest"
                ],
                outcome_checkpoint_digest=checkpoint[
                    "current_outcome_checkpoint_digest"
                ],
                timeframe_cache_digest=checkpoint[
                    "current_timeframe_cache_digest"
                ],
                prior_dynamic_state_digest=checkpoint[
                    "current_dynamic_state_digest"
                ],
            )
        with self.assertRaisesRegex(
            V32TickSupervisorError, "DUE_OUTCOME_REQUIRED_FIRST"
        ):
            build_v32_analysis_tick_permit(
                checkpoint=checkpoint,
                schedule_sets=[first],
                analysis_decision_at="2026-08-07T00:15:00Z",
                issued_at="2026-08-07T00:15:01Z",
                research_checkpoint_digest=checkpoint[
                    "current_research_checkpoint_digest"
                ],
                outcome_checkpoint_digest=checkpoint[
                    "current_outcome_checkpoint_digest"
                ],
                timeframe_cache_digest=checkpoint[
                    "current_timeframe_cache_digest"
                ],
                prior_dynamic_state_digest=checkpoint[
                    "current_dynamic_state_digest"
                ],
            )
        checkpoint, _, _, _, _ = outcome_tick(
            checkpoint,
            [first],
            [],
            planned_at=datetime(2026, 8, 7, 0, 15, tzinfo=UTC),
            reserved_at=datetime(2026, 8, 7, 0, 15, tzinfo=UTC),
            instant=True,
        )
        exact_boundary_permit = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=[first],
            analysis_decision_at="2026-08-07T00:15:00Z",
            issued_at="2026-08-07T00:15:00Z",
            research_checkpoint_digest=checkpoint[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=checkpoint["current_timeframe_cache_digest"],
            prior_dynamic_state_digest=checkpoint["current_dynamic_state_digest"],
        )
        self.assertEqual(2, exact_boundary_permit["analysis_cycle_index"])
        self.assertEqual("2026-08-07T00:15:00Z", exact_boundary_permit["analysis_decision_at"])

    def test_unknown_coverage_loss_is_terminal_without_killing_run(self) -> None:
        checkpoint = bootstrap()
        checkpoint, _, first = analysis_cycle(
            checkpoint,
            [],
            decision_at=datetime(2026, 8, 7, 0, 0, tzinfo=UTC),
        )
        checkpoint, _, receipts, _, _ = outcome_tick(
            checkpoint,
            [first],
            [],
            planned_at=datetime(2026, 8, 7, 0, 15, tzinfo=UTC),
            coverage=True,
        )
        self.assertEqual("READY", checkpoint["status"])
        self.assertTrue(checkpoint["resume_allowed"])
        self.assertEqual(1, checkpoint["terminal_outcomes"])
        self.assertEqual("UNKNOWN_COVERAGE_LOSS", receipts[0]["resolution_status"])
        self.assertIsNone(checkpoint["failure_digest"])

    def test_sixteen_cycles_finish_only_after_outcome_only_tail(self) -> None:
        checkpoint = bootstrap()
        schedules: list[dict] = []
        terminal_receipts: list[dict] = []
        base = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
        last_decision = base
        checkpoint, _, schedule_set = analysis_cycle(
            checkpoint,
            schedules,
            decision_at=last_decision,
        )
        schedules.append(schedule_set)
        # Every subsequent 15m cycle first terminalizes the exact due set, then
        # opens one fresh analysis permit.  The small wall-clock offset models
        # raw-first capture and deterministic receipt/commit time without
        # shortening the frozen >=900 second analysis cadence.
        for cycle in range(2, 17):
            boundary = base + timedelta(minutes=15 * (cycle - 1))
            prior_15m_due = last_decision + timedelta(minutes=15)
            checkpoint, _, new_receipts, _, _ = outcome_tick(
                checkpoint,
                schedules,
                terminal_receipts,
                planned_at=boundary,
                reserved_at=prior_15m_due + timedelta(seconds=1),
            )
            terminal_receipts.extend(new_receipts)
            last_decision = prior_15m_due + timedelta(seconds=8)
            checkpoint, _, schedule_set = analysis_cycle(
                checkpoint,
                schedules,
                decision_at=last_decision,
            )
            schedules.append(schedule_set)
        self.assertEqual("OUTCOME_ONLY_TAIL", checkpoint["status"])
        self.assertEqual(16, checkpoint["accepted_analysis_cycles"])
        self.assertEqual(48, checkpoint["scheduled_outcomes"])
        self.assertEqual(27, checkpoint["terminal_outcomes"])
        self.assertEqual(16, len(checkpoint["analysis_completion_binding_digests"]))
        self.assertIsNotNone(checkpoint["last_source_admission_digest"])
        self.assertIsNotNone(
            checkpoint["last_source_admission_physical_sha256"]
        )
        self.assertIsNone(checkpoint["next_analysis_cycle_index"])
        with self.assertRaisesRegex(V32TickSupervisorError, "ANALYSIS_PERMIT_STATE"):
            build_v32_analysis_tick_permit(
                checkpoint=checkpoint,
                schedule_sets=schedules,
                analysis_decision_at="2026-08-07T05:00:00Z",
                issued_at="2026-08-07T05:00:01Z",
                research_checkpoint_digest=checkpoint[
                    "current_research_checkpoint_digest"
                ],
                outcome_checkpoint_digest=checkpoint[
                    "current_outcome_checkpoint_digest"
                ],
                timeframe_cache_digest=checkpoint[
                    "current_timeframe_cache_digest"
                ],
                prior_dynamic_state_digest=checkpoint[
                    "current_dynamic_state_digest"
                ],
            )
        checkpoint, _, tail_receipts, _, _ = outcome_tick(
            checkpoint,
            schedules,
            terminal_receipts,
            planned_at=datetime(2026, 8, 7, 8, 0, tzinfo=UTC),
        )
        terminal_receipts.extend(tail_receipts)
        self.assertEqual(48, len(terminal_receipts))
        self.assertEqual(21, len(tail_receipts))
        self.assertEqual("TERMINAL_COMPLETE", checkpoint["status"])
        self.assertEqual(48, checkpoint["terminal_outcomes"])
        self.assertFalse(checkpoint["resume_allowed"])
        self.assertIsNone(checkpoint["next_outcome_tick_index"])
        self.assertEqual("COMPLETE", checkpoint["lane_states"]["OUTCOME_LANE"])

    def test_single_permit_cas_rejects_duplicate_replay_and_concurrency(self) -> None:
        checkpoint = bootstrap()
        permit = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=[],
            analysis_decision_at="2026-08-07T00:00:00Z",
            issued_at="2026-08-07T00:00:01Z",
            research_checkpoint_digest="c" * 64,
            outcome_checkpoint_digest="d" * 64,
            timeframe_cache_digest="e" * 64,
            prior_dynamic_state_digest=None,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=checkpoint,
            permit=permit,
            schedule_sets=[],
            updated_at="2026-08-07T00:00:01Z",
        )
        self.assertEqual("ANALYSIS_TICK", opened["active_permit_kind"])
        self.assertEqual("ACTIVE", opened["lane_states"]["ANALYSIS_LANE"])
        with self.assertRaisesRegex(V32TickSupervisorError, "PERMIT_STATE_INVALID"):
            build_v32_analysis_tick_permit(
                checkpoint=opened,
                schedule_sets=[],
                analysis_decision_at="2026-08-07T00:00:02Z",
                issued_at="2026-08-07T00:00:03Z",
                research_checkpoint_digest="c" * 64,
                outcome_checkpoint_digest="d" * 64,
                timeframe_cache_digest="e" * 64,
                prior_dynamic_state_digest=None,
            )
        schedule_set = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision:0001",
            cycle_index=1,
            decision_time="2026-08-07T00:00:00Z",
            scheduled_at="2026-08-07T00:00:02Z",
            sealed_decision_digest="8" * 64,
            evaluation_contract_digest="9" * 64,
        )
        completed = complete_v32_analysis_tick(
            checkpoint=opened,
            permit=permit,
            schedule_sets_before=[],
            new_schedule_set=schedule_set,
            accepted_state_digest="1" * 64,
            source_admission_digest="2" * 64,
            source_admission_physical_sha256="a" * 64,
            proposal_lifecycle_digest="b" * 64,
            selection_lifecycle_digest="c" * 64,
            final_action_plan_digest="d" * 64,
            commit_envelope_digest="3" * 64,
            shadow_decision_bundle_digest="0" * 64,
            new_research_checkpoint_digest="4" * 64,
            new_outcome_checkpoint_digest="7" * 64,
            new_timeframe_cache_digest="5" * 64,
            new_dynamic_state_digest="6" * 64,
            completed_at="2026-08-07T00:00:03Z",
        )
        with self.assertRaisesRegex(V32TickSupervisorError, "ACTIVE_PERMIT_MISMATCH"):
            complete_v32_analysis_tick(
                checkpoint=completed,
                permit=permit,
                schedule_sets_before=[schedule_set],
                new_schedule_set=schedule_set,
                accepted_state_digest="1" * 64,
                source_admission_digest="2" * 64,
                source_admission_physical_sha256="a" * 64,
                proposal_lifecycle_digest="b" * 64,
                selection_lifecycle_digest="c" * 64,
                final_action_plan_digest="d" * 64,
                commit_envelope_digest="3" * 64,
                shadow_decision_bundle_digest="0" * 64,
                new_research_checkpoint_digest="4" * 64,
                new_outcome_checkpoint_digest="7" * 64,
                new_timeframe_cache_digest="5" * 64,
                new_dynamic_state_digest="6" * 64,
                completed_at="2026-08-07T00:00:04Z",
            )

    def test_analysis_completion_requires_advanced_outcome_store_head(self) -> None:
        checkpoint = bootstrap()
        permit = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=[],
            analysis_decision_at="2026-08-07T00:00:00Z",
            issued_at="2026-08-07T00:00:01Z",
            research_checkpoint_digest=checkpoint[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=checkpoint[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=checkpoint["current_timeframe_cache_digest"],
            prior_dynamic_state_digest=None,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=checkpoint,
            permit=permit,
            schedule_sets=[],
            updated_at=permit["issued_at"],
        )
        schedule = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision:0001",
            cycle_index=1,
            decision_time=permit["analysis_decision_at"],
            scheduled_at="2026-08-07T00:00:02Z",
            sealed_decision_digest="8" * 64,
            evaluation_contract_digest="9" * 64,
        )
        with self.assertRaisesRegex(
            V32TickSupervisorError, "OUTCOME_CHECKPOINT_NOT_ADVANCED"
        ):
            complete_v32_analysis_tick(
                checkpoint=opened,
                permit=permit,
                schedule_sets_before=[],
                new_schedule_set=schedule,
                accepted_state_digest="1" * 64,
                source_admission_digest="2" * 64,
                source_admission_physical_sha256="a" * 64,
                proposal_lifecycle_digest="b" * 64,
                selection_lifecycle_digest="c" * 64,
                final_action_plan_digest="d" * 64,
                commit_envelope_digest="3" * 64,
                shadow_decision_bundle_digest="0" * 64,
                new_research_checkpoint_digest="4" * 64,
                new_outcome_checkpoint_digest=checkpoint[
                    "current_outcome_checkpoint_digest"
                ],
                new_timeframe_cache_digest="5" * 64,
                new_dynamic_state_digest="6" * 64,
                completed_at="2026-08-07T00:00:03Z",
            )

    def test_tamper_wrong_counters_and_wrong_live_bindings_fail_closed(self) -> None:
        checkpoint = bootstrap()
        tampered = copy.deepcopy(checkpoint)
        tampered["accepted_analysis_cycles"] = 1
        tampered = self_digest(tampered, CHECKPOINT_DIGEST_FIELD)
        with self.assertRaisesRegex(V32TickSupervisorError, "COUNTER_RELATION"):
            verify_v32_tick_supervisor_checkpoint(tampered)
        with self.assertRaisesRegex(V32TickSupervisorError, "LIVE_BINDING_DRIFT"):
            build_v32_analysis_tick_permit(
                checkpoint=checkpoint,
                schedule_sets=[],
                analysis_decision_at="2026-08-07T00:00:00Z",
                issued_at="2026-08-07T00:00:01Z",
                research_checkpoint_digest="0" * 64,
                outcome_checkpoint_digest="d" * 64,
                timeframe_cache_digest="e" * 64,
                prior_dynamic_state_digest=None,
            )
        permit = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=[],
            analysis_decision_at="2026-08-07T00:00:00Z",
            issued_at="2026-08-07T00:00:01Z",
            research_checkpoint_digest="c" * 64,
            outcome_checkpoint_digest="d" * 64,
            timeframe_cache_digest="e" * 64,
            prior_dynamic_state_digest=None,
        )
        forged = copy.deepcopy(permit)
        forged["agent_stage_attempt_limits"] = {"PROPOSAL": 2, "SELECTION": 1}
        forged = self_digest(forged, PERMIT_DIGEST_FIELD)
        with self.assertRaisesRegex(V32TickSupervisorError, "PERMIT_KIND_INVALID"):
            verify_v32_tick_supervisor_permit(
                forged, checkpoint=checkpoint, schedule_sets=[]
            )

    def test_integrity_failure_preserves_prefix_and_coverage_is_not_failure_code(self) -> None:
        checkpoint = bootstrap()
        permit = build_v32_analysis_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=[],
            analysis_decision_at="2026-08-07T00:00:00Z",
            issued_at="2026-08-07T00:00:01Z",
            research_checkpoint_digest="c" * 64,
            outcome_checkpoint_digest="d" * 64,
            timeframe_cache_digest="e" * 64,
            prior_dynamic_state_digest=None,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=checkpoint,
            permit=permit,
            schedule_sets=[],
            updated_at="2026-08-07T00:00:01Z",
        )
        with self.assertRaisesRegex(V32TickSupervisorError, "FAILURE_CLASS_INVALID"):
            build_v32_tick_supervisor_failure(
                checkpoint=opened,
                failure_lane="OUTCOME_LANE",
                failure_code="UNKNOWN_COVERAGE_LOSS",
                failure_summary="public source timeout",
                failure_evidence_digest="f" * 64,
                occurred_at="2026-08-07T00:00:02Z",
            )
        failure = build_v32_tick_supervisor_failure(
            checkpoint=opened,
            failure_lane="AGENT_LANE",
            failure_code="AGENT_DELIVERY_OR_SCHEMA_INVALID",
            failure_summary="sealed Agent response failed exact schema validation",
            failure_evidence_digest="f" * 64,
            occurred_at="2026-08-07T00:00:02Z",
        )
        failed = fail_v32_tick_supervisor(
            checkpoint=opened,
            failure=failure,
        )
        self.assertEqual("FAILED_CLOSED", failed["status"])
        self.assertEqual("FAILED_CLOSED", failed["lane_states"]["AGENT_LANE"])
        self.assertIsNone(failed["active_permit_digest"])
        self.assertFalse(failed["resume_allowed"])
        self.assertEqual(
            opened["accepted_analysis_cycles"], failed["accepted_analysis_cycles"]
        )
        verify_v32_tick_supervisor_transition(opened, failed)
        with self.assertRaisesRegex(V32TickSupervisorError, "FAILURE_STATE_INVALID"):
            build_v32_tick_supervisor_failure(
                checkpoint=failed,
                failure_lane="AGENT_LANE",
                failure_code="AGENT_ATTEMPT_DUPLICATE",
                failure_summary="replay",
                failure_evidence_digest="0" * 64,
                occurred_at="2026-08-07T00:00:03Z",
            )


if __name__ == "__main__":
    unittest.main()
