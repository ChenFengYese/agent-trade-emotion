from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_system.theory_paper_v2.domain.common import ReducerStatus
from trade_system.theory_paper_v2.domain.geometry import (
    AnalysisGeometry,
    AnalysisGeometryStatus,
    AnalysisGeometryTransition,
    ExecutionBarrierStatus,
    GeometryAggregate,
    PositionSide,
    ProbabilityStatus,
    ProtectionBarrier,
    ProtectionRevision,
    ProtectionStatusTransition,
    reduce_analysis_geometry,
    revise_protection,
    transition_protection_status,
)
from trade_system.theory_paper_v2.domain.matching import (
    BarrierOrder,
    BarrierType,
    ClosedBar,
    MatchResult,
    MatchingPolicy,
    OrderSide,
    match_closed_bar,
)
from trade_system.theory_paper_v2.domain.reentry import (
    EligibilityVerdict,
    ReentryContract,
    ReentryEvaluation,
    ReentryStatus,
    open_reentry_contract,
    reduce_reentry,
    review_obligation,
)
from trade_system.theory_paper_v2.domain.strategic import StrategicStatus


class GeometryDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 1, tzinfo=UTC)
        self.aggregate = GeometryAggregate(
            aggregate_id="geometry-aggregate-1",
            revision=3,
            analysis=AnalysisGeometry(
                geometry_id="analysis-1",
                revision=2,
                side=PositionSide.LONG,
                status=AnalysisGeometryStatus.ACTIVE_ANALYSIS,
                stop_price=Decimal("90"),
                target_price=Decimal("120"),
                horizon_at=self.now + timedelta(hours=12),
                valid_until=self.now + timedelta(hours=4),
            ),
            protection=ProtectionBarrier(
                barrier_id="barrier-1",
                revision=2,
                side=PositionSide.LONG,
                status=ExecutionBarrierStatus.ACTIVE_PROTECTION,
                stop_price=Decimal("90"),
                target_price=Decimal("120"),
                horizon_at=self.now + timedelta(hours=12),
                position_locked=True,
                active_from=self.now - timedelta(hours=1),
                acknowledged_at=self.now - timedelta(hours=1),
            ),
        )

    def revision(self, **changes: object) -> ProtectionRevision:
        values: dict[str, object] = {
            "event_id": "replace-1",
            "expected_aggregate_revision": 3,
            "expected_barrier_revision": 2,
            "replacement_barrier_id": "barrier-2",
            "requested_at": self.now,
            "acknowledged_at": self.now + timedelta(seconds=1),
            "old_barrier_crossed_at": None,
            "new_stop_price": Decimal("95"),
            "new_target_price": Decimal("120"),
            "new_horizon_at": self.now + timedelta(hours=10),
            "probability_status": ProbabilityStatus.ORDINAL_ONLY,
            "t023_core_gates_pass": False,
            "t023_governance_ack_pass": False,
        }
        values.update(changes)
        return ProtectionRevision(**values)

    def test_analysis_expiry_does_not_cancel_active_protection(self) -> None:
        result = reduce_analysis_geometry(
            self.aggregate,
            AnalysisGeometryTransition(
                event_id="analysis-expired",
                expected_aggregate_revision=3,
                expected_analysis_revision=2,
                requested_status=AnalysisGeometryStatus.EXPIRED,
                occurred_at=self.now + timedelta(hours=4),
            ),
        )
        self.assertEqual(ReducerStatus.APPLIED, result.status)
        self.assertEqual(AnalysisGeometryStatus.EXPIRED, result.value.analysis.status)
        self.assertIs(self.aggregate.protection, result.value.protection)
        self.assertEqual(
            ExecutionBarrierStatus.ACTIVE_PROTECTION,
            result.value.protection.status,
        )

    def test_locked_long_stop_cannot_loosen(self) -> None:
        result = revise_protection(
            self.aggregate,
            self.revision(new_stop_price=Decimal("89")),
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("GEOMETRY_STOP_LOOSEN_FORBIDDEN", result.error.code)

    def test_protection_horizon_cannot_lengthen(self) -> None:
        result = revise_protection(
            self.aggregate,
            self.revision(new_horizon_at=self.now + timedelta(hours=13)),
        )
        self.assertEqual("GEOMETRY_HORIZON_EXTENSION_FORBIDDEN", result.error.code)

    def test_uncalibrated_e0_t023_target_extension_is_denied(self) -> None:
        result = revise_protection(
            self.aggregate,
            self.revision(
                new_target_price=Decimal("125"),
                probability_status=ProbabilityStatus.ORDINAL_ONLY,
                t023_core_gates_pass=True,
                t023_governance_ack_pass=True,
            ),
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("GEOMETRY_T023_GATE_UNCALIBRATED", result.error.code)

    def test_calibrated_t023_and_ack_can_replace_with_tighter_protection(self) -> None:
        result = revise_protection(
            self.aggregate,
            self.revision(
                new_target_price=Decimal("125"),
                probability_status=ProbabilityStatus.CALIBRATED_OOS,
                t023_core_gates_pass=True,
                t023_governance_ack_pass=True,
            ),
        )
        self.assertEqual(ReducerStatus.APPLIED, result.status)
        self.assertEqual(Decimal("95"), result.value.protection.stop_price)
        self.assertEqual("barrier-1", result.value.protection.previous_barrier_id)
        self.assertIs(self.aggregate.analysis, result.value.analysis)

    def test_old_barrier_crossing_before_ack_wins(self) -> None:
        result = revise_protection(
            self.aggregate,
            self.revision(
                old_barrier_crossed_at=self.now + timedelta(milliseconds=500)
            ),
        )
        self.assertEqual("GEOMETRY_OLD_BARRIER_ALREADY_CROSSED", result.error.code)

    def test_pending_barrier_needs_ack_before_activation(self) -> None:
        pending = replace(
            self.aggregate,
            protection=replace(
                self.aggregate.protection,
                status=ExecutionBarrierStatus.PENDING_VENUE_ACK,
                active_from=None,
                acknowledged_at=None,
            ),
        )
        result = transition_protection_status(
            pending,
            ProtectionStatusTransition(
                event_id="activation-1",
                expected_aggregate_revision=3,
                expected_barrier_revision=2,
                requested_status=ExecutionBarrierStatus.ACTIVE_PROTECTION,
                occurred_at=self.now,
            ),
        )
        self.assertEqual(ReducerStatus.UNKNOWN, result.status)
        self.assertEqual("GEOMETRY_ACK_MISSING", result.error.code)


class ReentryDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 1, tzinfo=UTC)
        opened = open_reentry_contract(
            contract_id="reentry-1",
            strategic_episode_id="episode-1",
            opened_at=self.now,
            earliest_review_at=self.now + timedelta(hours=1),
            latest_review_at=self.now + timedelta(hours=4),
            expires_at=self.now + timedelta(hours=5),
            maximum_deferrals=1,
            minimum_core_quantity=Decimal("2"),
            strategic_status=StrategicStatus.ACTIVE,
            authoritative_core_quantity=Decimal("0"),
            atomic_create_effect_present=True,
        )
        self.assertEqual(ReducerStatus.APPLIED, opened.status)
        self.contract = opened.value

    def evaluation(
        self,
        prior: ReentryContract,
        requested: ReentryStatus,
        **changes: object,
    ) -> ReentryEvaluation:
        values: dict[str, object] = {
            "event_id": f"reentry-{requested}",
            "expected_revision": prior.revision,
            "decision_cutoff": self.now + timedelta(hours=1),
            "requested_status": requested,
            "strategic_status": StrategicStatus.ACTIVE,
        }
        values.update(changes)
        return ReentryEvaluation(**values)

    def due_contract(self) -> ReentryContract:
        return reduce_reentry(
            self.contract,
            self.evaluation(self.contract, ReentryStatus.DUE),
        ).value

    def eligible_contract(self) -> ReentryContract:
        due = self.due_contract()
        return reduce_reentry(
            due,
            self.evaluation(
                due,
                ReentryStatus.ELIGIBLE,
                eligibility=EligibilityVerdict.PASS,
            ),
        ).value

    def test_open_requires_atomic_zero_core_transition(self) -> None:
        result = open_reentry_contract(
            contract_id="bad",
            strategic_episode_id="episode-1",
            opened_at=self.now,
            earliest_review_at=self.now,
            latest_review_at=self.now + timedelta(hours=1),
            expires_at=self.now + timedelta(hours=2),
            maximum_deferrals=1,
            minimum_core_quantity=Decimal("1"),
            strategic_status=StrategicStatus.ACTIVE,
            authoritative_core_quantity=Decimal("0"),
            atomic_create_effect_present=False,
        )
        self.assertEqual(ReducerStatus.UNKNOWN, result.status)
        self.assertEqual("REENTRY_ATOMIC_OPEN_MISSING", result.error.code)

    def test_due_cannot_be_manufactured_before_earliest_review(self) -> None:
        result = reduce_reentry(
            self.contract,
            self.evaluation(
                self.contract,
                ReentryStatus.DUE,
                decision_cutoff=self.now + timedelta(minutes=59),
            ),
        )
        self.assertEqual("REENTRY_CURRENT_ELIGIBILITY_FAILED", result.error.code)

    def test_due_to_eligible_requires_current_route_pass(self) -> None:
        due = self.due_contract()
        failed = reduce_reentry(
            due,
            self.evaluation(
                due,
                ReentryStatus.ELIGIBLE,
                eligibility=EligibilityVerdict.FAIL,
            ),
        )
        self.assertEqual("REENTRY_CURRENT_ELIGIBILITY_FAILED", failed.error.code)
        passed = reduce_reentry(
            due,
            self.evaluation(
                due,
                ReentryStatus.ELIGIBLE,
                eligibility=EligibilityVerdict.PASS,
            ),
        )
        self.assertEqual(ReentryStatus.ELIGIBLE, passed.value.status)

    def test_unknown_deferral_is_bounded_and_frozen(self) -> None:
        due = self.due_contract()
        deferred = reduce_reentry(
            due,
            self.evaluation(
                due,
                ReentryStatus.OPEN,
                eligibility=EligibilityVerdict.UNKNOWN,
                deferral_frozen=True,
                next_review_at=self.now + timedelta(hours=2),
            ),
        )
        self.assertEqual(ReducerStatus.APPLIED, deferred.status)
        self.assertEqual(1, deferred.value.deferral_count)
        due_again = reduce_reentry(
            deferred.value,
            self.evaluation(
                deferred.value,
                ReentryStatus.DUE,
                decision_cutoff=self.now + timedelta(hours=2),
            ),
        ).value
        exceeded = reduce_reentry(
            due_again,
            self.evaluation(
                due_again,
                ReentryStatus.OPEN,
                decision_cutoff=self.now + timedelta(hours=2),
                eligibility=EligibilityVerdict.UNKNOWN,
                deferral_frozen=True,
                next_review_at=self.now + timedelta(hours=3),
            ),
        )
        self.assertEqual("REENTRY_DEFERRAL_LIMIT_EXCEEDED", exceeded.error.code)

    def test_strategic_invalidation_and_close_cancel_nonterminal_contract(self) -> None:
        invalidated = reduce_reentry(
            self.contract,
            self.evaluation(
                self.contract,
                ReentryStatus.DUE,
                strategic_status=StrategicStatus.INVALIDATED,
            ),
        )
        self.assertEqual(
            ReentryStatus.CANCELLED_INVALIDATED, invalidated.value.status
        )
        closed = reduce_reentry(
            self.contract,
            self.evaluation(
                self.contract,
                ReentryStatus.DUE,
                strategic_status=StrategicStatus.CLOSED,
            ),
        )
        self.assertEqual(ReentryStatus.CANCELLED_CLOSED, closed.value.status)

    def test_execution_requires_new_thi_risk_governance_and_core_fill(self) -> None:
        eligible = self.eligible_contract()
        missing_thi = reduce_reentry(
            eligible,
            self.evaluation(
                eligible,
                ReentryStatus.EXECUTED,
                eligibility=EligibilityVerdict.PASS,
                risk_permission_pass=True,
                governance_pass=True,
                core_fill_reconciled=True,
                reconciled_core_quantity=Decimal("2"),
            ),
        )
        self.assertEqual("REENTRY_NEW_THI_MISSING", missing_thi.error.code)
        too_small = reduce_reentry(
            eligible,
            self.evaluation(
                eligible,
                ReentryStatus.EXECUTED,
                eligibility=EligibilityVerdict.PASS,
                new_thi_present=True,
                risk_permission_pass=True,
                governance_pass=True,
                core_fill_reconciled=True,
                reconciled_core_quantity=Decimal("1"),
            ),
        )
        self.assertEqual("REENTRY_CORE_FILL_UNRECONCILED", too_small.error.code)
        executed = reduce_reentry(
            eligible,
            self.evaluation(
                eligible,
                ReentryStatus.EXECUTED,
                eligibility=EligibilityVerdict.PASS,
                new_thi_present=True,
                risk_permission_pass=True,
                governance_pass=True,
                core_fill_reconciled=True,
                reconciled_core_quantity=Decimal("2"),
            ),
        )
        self.assertEqual(ReentryStatus.EXECUTED, executed.value.status)
        terminal_reuse = reduce_reentry(
            executed.value,
            self.evaluation(executed.value, ReentryStatus.DUE),
        )
        self.assertEqual("REENTRY_PRIOR_STATE_MISMATCH", terminal_reuse.error.code)

    def test_latest_review_silence_is_illegal(self) -> None:
        result = review_obligation(
            self.contract,
            now=self.contract.latest_review_at,
            review_recorded=False,
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("REENTRY_REVIEW_OVERDUE", result.error.code)


class MatchingDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2026, 7, 1, tzinfo=UTC)
        self.policy = MatchingPolicy(
            policy_id="policy-1",
            instrument_id="SNDK",
            venue_id="TEST",
            price_tick=Decimal("1"),
            quantity_step=Decimal("1"),
            contract_multiplier=Decimal("1"),
            fee_rate=Decimal("0.001"),
            adverse_slippage_bps=Decimal("0"),
        )

    def bar(
        self,
        *,
        open_: str = "100",
        high: str = "104",
        low: str = "96",
        close: str = "101",
        lineage: bool = True,
    ) -> ClosedBar:
        close_time = self.start + timedelta(hours=1)
        return ClosedBar(
            bar_id="bar-1",
            instrument_id="SNDK",
            venue_id="TEST",
            open_time=self.start,
            close_time=close_time,
            open=Decimal(open_),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=Decimal("100"),
            observed_at=close_time,
            available_at=close_time + timedelta(seconds=1),
            ingested_at=close_time + timedelta(seconds=2),
            source_committed_at=close_time + timedelta(seconds=3),
            source_commit_receipt_valid=lineage,
            lineage_digest_valid=lineage,
        )

    def order(
        self,
        barrier_type: BarrierType,
        *,
        order_id: str = "order-1",
        side: OrderSide = OrderSide.SELL,
        trigger: str | None = None,
        limit: str | None = None,
        lot_id: str | None = "lot-1",
        stage_id: str | None = None,
        event_triggered: bool = False,
    ) -> BarrierOrder:
        is_entry = barrier_type in {
            BarrierType.ENTRY_LIMIT,
            BarrierType.ENTRY_STOP_MARKET,
        }
        return BarrierOrder(
            order_id=order_id,
            instrument_id="SNDK",
            venue_id="TEST",
            barrier_type=barrier_type,
            side=side,
            quantity=Decimal("5"),
            remaining_quantity=Decimal("5"),
            trigger_price=Decimal(trigger) if trigger is not None else None,
            limit_price=Decimal(limit) if limit is not None else None,
            reduce_only=not is_entry,
            active_from=self.start - timedelta(hours=1),
            active_until=self.start + timedelta(hours=2),
            protection_priority=0,
            lot_id=None if is_entry else lot_id,
            stage_id="stage-1" if is_entry else stage_id,
            geometry_id=(
                None
                if barrier_type
                in {BarrierType.KILL, BarrierType.ACCOUNT_MISMATCH}
                else "geometry-1"
            ),
            event_triggered=event_triggered,
        )

    def cutoff(self) -> datetime:
        return self.start + timedelta(hours=1, seconds=3)

    def test_future_or_unclosed_bar_is_rejected(self) -> None:
        result = match_closed_bar(
            bar=self.bar(low="94"),
            orders=(self.order(BarrierType.STOP_MARKET, trigger="95"),),
            policy=self.policy,
            decision_cutoff=self.start + timedelta(minutes=59),
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("MATCHING_FUTURE_BAR_FORBIDDEN", result.error.code)

    def test_invalid_lineage_is_rejected(self) -> None:
        result = match_closed_bar(
            bar=self.bar(low="94", lineage=False),
            orders=(self.order(BarrierType.STOP_MARKET, trigger="95"),),
            policy=self.policy,
            decision_cutoff=self.cutoff(),
        )
        self.assertEqual("MATCHING_BAR_LINEAGE_INVALID", result.error.code)

    def test_gap_stop_uses_conservative_open(self) -> None:
        result = match_closed_bar(
            bar=self.bar(open_="93", high="96", low="90", close="92"),
            orders=(self.order(BarrierType.STOP_MARKET, trigger="95"),),
            policy=self.policy,
            decision_cutoff=self.cutoff(),
        )
        self.assertEqual(ReducerStatus.APPLIED, result.status)
        self.assertEqual(Decimal("93"), result.value.fill_price)
        self.assertFalse(result.value.executable)

    def test_limit_touch_without_one_tick_cross_is_fail_closed(self) -> None:
        result = match_closed_bar(
            bar=self.bar(high="105"),
            orders=(self.order(BarrierType.TARGET_LIMIT, limit="105"),),
            policy=self.policy,
            decision_cutoff=self.cutoff(),
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("MATCHING_LIMIT_TOUCH_INSUFFICIENT", result.error.code)
        crossed = match_closed_bar(
            bar=self.bar(high="106"),
            orders=(self.order(BarrierType.TARGET_LIMIT, limit="105"),),
            policy=self.policy,
            decision_cutoff=self.cutoff(),
        )
        self.assertEqual(Decimal("105"), crossed.value.fill_price)

    def test_same_bar_stop_and_target_uses_stop_first_and_records_ambiguity(self) -> None:
        result = match_closed_bar(
            bar=self.bar(high="106", low="94"),
            orders=(
                self.order(
                    BarrierType.TARGET_LIMIT,
                    order_id="target",
                    limit="105",
                ),
                self.order(
                    BarrierType.STOP_MARKET,
                    order_id="stop",
                    trigger="95",
                ),
            ),
            policy=self.policy,
            decision_cutoff=self.cutoff(),
        )
        self.assertEqual(ReducerStatus.APPLIED, result.status)
        self.assertEqual("stop", result.value.order_id)
        self.assertTrue(result.value.ambiguous_barrier_order)
        self.assertIn(
            "MATCHING_AMBIGUOUS_BARRIER_ORDER",
            result.value.diagnostic_codes,
        )
        self.assertEqual(Decimal("105"), result.value.favorable_bound_price)

    def test_unorderable_same_priority_barriers_are_rejected(self) -> None:
        result = match_closed_bar(
            bar=self.bar(),
            orders=(
                self.order(
                    BarrierType.KILL,
                    order_id="kill",
                    lot_id=None,
                    event_triggered=True,
                ),
                self.order(
                    BarrierType.ACCOUNT_MISMATCH,
                    order_id="mismatch",
                    lot_id=None,
                    event_triggered=True,
                ),
            ),
            policy=self.policy,
            decision_cutoff=self.cutoff(),
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("MATCHING_AMBIGUOUS_BARRIER_ORDER", result.error.code)

    def test_tick_step_misalignment_is_rejected(self) -> None:
        misaligned = replace(
            self.order(BarrierType.STOP_MARKET, trigger="95"),
            remaining_quantity=Decimal("4.5"),
        )
        result = match_closed_bar(
            bar=self.bar(low="94"),
            orders=(misaligned,),
            policy=self.policy,
            decision_cutoff=self.cutoff(),
        )
        self.assertEqual("MATCHING_TICK_OR_STEP_UNKNOWN", result.error.code)

    def test_models_reject_floats_and_naive_datetimes(self) -> None:
        with self.assertRaises(TypeError):
            replace(self.policy, price_tick=1.0)
        with self.assertRaises(ValueError):
            replace(
                self.order(BarrierType.STOP_MARKET, trigger="95"),
                active_from=datetime(2026, 7, 1),
            )


if __name__ == "__main__":
    unittest.main()
