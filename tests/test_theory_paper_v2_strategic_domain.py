from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from trade_system.theory_paper_v2.domain.common import ReducerStatus
from trade_system.theory_paper_v2.domain.evidence import (
    EvidenceQuality,
    EvidenceRecord,
    EvidenceScope,
    PhysicalExistence,
    SignalClass,
    admit_evidence,
    qualify_promotion,
)
from trade_system.theory_paper_v2.domain.policy import (
    ActionIntent,
    GeometryOperation,
    ProtectiveActionType,
)
from trade_system.theory_paper_v2.domain.strategic import (
    CrossTimescaleLease,
    ExposureStatus,
    StrategicEpisode,
    StrategicStatus,
    WorkflowProjection,
    derive_workflow_projection,
    reduce_strategic_episode,
    validate_fast_action,
)
from trade_system.theory_paper_v2.domain.strategic.reducer import StrategicTransition
from trade_system.theory_paper_v2.domain.time_authority import ReviewClock


class StrategicDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 1, tzinfo=UTC)
        self.clock = ReviewClock(
            "review-1", self.now + timedelta(hours=4), self.now + timedelta(hours=8)
        )
        self.episode = StrategicEpisode(
            episode_id="episode-1",
            revision=1,
            state_digest="a" * 64,
            previous_state_digest=None,
            strategic_status=StrategicStatus.ACTIVE,
            exposure_status=ExposureStatus.EXPOSED,
            strategic_timeframe_seconds=14_400,
            hypothesis_set_id="hyp-set-1",
            premise_ids=("premise-1",),
            hard_invalidator_ids=("invalidator-1",),
            review_clock=self.clock,
            episode_risk_allocation_id="risk-1",
        )

    def evidence(self, timeframe: int = 900) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id="ev-1",
            source_id="source-1",
            available_at=self.now,
            ingested_at=self.now,
            source_committed_at=self.now,
            source_commit_receipt_valid=True,
            physical_existence=PhysicalExistence.PROVEN,
            usage_scope=EvidenceScope.DECISION_CONTEMPORANEOUS,
            quality=EvidenceQuality.OBSERVED,
            signal_class=SignalClass.STRUCTURAL,
            timeframe_seconds=timeframe,
            premise_ids=("premise-1",),
            independent_source_ids=("source-2",),
            observation_count=3,
        )

    def test_future_evidence_is_rejected(self) -> None:
        record = self.evidence()
        record = EvidenceRecord(
            **{
                **{field: getattr(record, field) for field in record.__dataclass_fields__},
                "available_at": self.now + timedelta(seconds=1),
            }
        )
        result = admit_evidence(
            record,
            decision_cutoff=self.now,
            strategic_timeframe_seconds=14_400,
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("PIT_FUTURE_AVAILABLE", result.error.code)

    def test_low_timeframe_requires_promotion_and_cannot_directly_challenge(self) -> None:
        admitted = admit_evidence(
            self.evidence(),
            decision_cutoff=self.now,
            strategic_timeframe_seconds=14_400,
        ).value
        self.assertTrue(admitted.promotion_required)
        transition = StrategicTransition(
            event_id="event-1",
            expected_revision=1,
            expected_state_digest="a" * 64,
            requested_status=StrategicStatus.CHALLENGED,
            next_state_digest="b" * 64,
            next_review_clock=self.clock,
            evidence=admitted,
            exact_premise_id="premise-1",
        )
        result = reduce_strategic_episode(self.episode, transition)
        self.assertEqual(ReducerStatus.REJECTED, result.status)

    def test_preregistered_promotion_can_challenge_but_not_invalidate(self) -> None:
        admitted = admit_evidence(
            self.evidence(),
            decision_cutoff=self.now,
            strategic_timeframe_seconds=14_400,
        ).value
        promotion = qualify_promotion(
            admitted,
            exact_premise_id="premise-1",
            normal_range_exceeded=True,
            independent_confirmation_count=2,
            required_independent_confirmations=2,
            persistent_observation_count=3,
            required_persistent_observations=3,
            mechanism_changed=True,
        ).value
        result = reduce_strategic_episode(
            self.episode,
            StrategicTransition(
                event_id="event-1",
                expected_revision=1,
                expected_state_digest="a" * 64,
                requested_status=StrategicStatus.CHALLENGED,
                next_state_digest="b" * 64,
                next_review_clock=ReviewClock(
                    "review-2",
                    self.now + timedelta(hours=8),
                    self.now + timedelta(hours=12),
                ),
                evidence=admitted,
                promotion=promotion,
                exact_premise_id="premise-1",
            ),
        )
        self.assertEqual(ReducerStatus.APPLIED, result.status)
        self.assertEqual(StrategicStatus.CHALLENGED, result.value.strategic_status)
        invalidation = reduce_strategic_episode(
            self.episode,
            StrategicTransition(
                event_id="event-2",
                expected_revision=1,
                expected_state_digest="a" * 64,
                requested_status=StrategicStatus.INVALIDATED,
                next_state_digest="c" * 64,
                next_review_clock=None,
                hard_invalidator_id=None,
                invalidation_receipt_present=False,
            ),
        )
        self.assertEqual(ReducerStatus.REJECTED, invalidation.status)

    def test_workflow_projection_preserves_reentry_obligation(self) -> None:
        flat = StrategicEpisode(
            **{
                **{
                    field: getattr(self.episode, field)
                    for field in self.episode.__dataclass_fields__
                },
                "exposure_status": ExposureStatus.FLAT,
                "reentry_contract_nonterminal": True,
            }
        )
        self.assertEqual(
            WorkflowProjection.REENTRY_PENDING, derive_workflow_projection(flat)
        )

    def test_fast_lease_is_revision_and_time_bound(self) -> None:
        lease = CrossTimescaleLease(
            lease_id="lease-1",
            strategic_episode_id=self.episode.episode_id,
            strategic_state_digest=self.episode.state_digest,
            strategic_state_revision=self.episode.revision,
            valid_from=self.now,
            valid_until=self.now + timedelta(hours=1),
            next_strategic_review_at=self.now + timedelta(hours=1),
            permitted_fast_action_intents=frozenset(
                {ActionIntent.KEEP_CORE, ActionIntent.REDUCE_TACTICAL}
            ),
            permitted_protective_actions=frozenset(
                {ProtectiveActionType.NONE, ProtectiveActionType.REDUCE_ONLY}
            ),
            permitted_geometry_operations=frozenset({GeometryOperation.KEEP}),
            terminal_safe_action_intent=ActionIntent.REDUCE_TACTICAL,
        )
        valid = validate_fast_action(
            self.episode,
            lease,
            decision_cutoff=self.now,
            action_intent=ActionIntent.KEEP_CORE,
            protective_action=ProtectiveActionType.NONE,
            geometry_operation=GeometryOperation.KEEP,
        )
        self.assertEqual(ReducerStatus.APPLIED, valid.status)
        expired = validate_fast_action(
            self.episode,
            lease,
            decision_cutoff=self.now + timedelta(hours=2),
            action_intent=ActionIntent.KEEP_CORE,
            protective_action=ProtectiveActionType.NONE,
            geometry_operation=GeometryOperation.KEEP,
        )
        self.assertEqual(ReducerStatus.REJECTED, expired.status)
        terminal = validate_fast_action(
            self.episode,
            lease,
            decision_cutoff=self.now + timedelta(hours=2),
            action_intent=ActionIntent.REDUCE_TACTICAL,
            protective_action=ProtectiveActionType.REDUCE_ONLY,
            geometry_operation=GeometryOperation.KEEP,
        )
        self.assertEqual(ReducerStatus.APPLIED, terminal.status)


if __name__ == "__main__":
    unittest.main()
