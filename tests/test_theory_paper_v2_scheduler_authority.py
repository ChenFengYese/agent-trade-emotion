from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

from trade_system.theory_paper_v2.application.schedule_catchup import (
    ScheduleCatchupError,
    assess_schedule_catchup,
)
from trade_system.theory_paper_v2.domain.evidence.model import EvidenceScope
from trade_system.theory_paper_v2.domain.time_authority.calendar import (
    BarAlignmentPolicy,
    CalendarError,
    MarketClockType,
    TradingSessionCalendarProfile,
    Weekday,
    WeeklySessionSpec,
)
from trade_system.theory_paper_v2.domain.time_authority.scheduler import (
    CompletedSlot,
    CorporateActionStatus,
    ExpectedSlotPolicy,
    RecoveryEvidence,
    ScheduleGapStatus,
    SchedulerCursor,
    SlotKind,
    enumerate_expected_slots,
    make_slot_id,
)
from trade_system.theory_paper_v2.infrastructure.authority import (
    AuthorityAdapterError,
    AuthorityExpectation,
    ClockSourceKind,
    E0AuthorityAdapter,
    TrustedTimestampInput,
    build_e0_authority_receipt,
)
from trade_system.theory_paper_v2.infrastructure.frozen_replay import (
    DatasetType,
    FrozenReplayBundleError,
    ReplayRecordKind,
    SourceKind,
    build_frozen_replay_item,
    build_frozen_replay_manifest,
    build_source_provenance,
    validate_frozen_replay_bundle,
)


class CalendarAndSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_from = datetime(2026, 1, 1, tzinfo=UTC)
        self.valid_until = datetime(2027, 1, 1, tzinfo=UTC)
        self.continuous = TradingSessionCalendarProfile(
            calendar_profile_id="calendar-hype",
            instrument_id="HYPEUSDT",
            venue_id="BINANCE_UM",
            market_clock_type=MarketClockType.CONTINUOUS_24_7,
            iana_timezone="America/New_York",
            weekly_session_specs=(),
            holiday_closures=(),
            special_sessions=(),
            halt_intervals=(),
            bar_alignment_policy=BarAlignmentPolicy.UTC_EPOCH,
            calendar_source_id="source-binance-calendar",
            calendar_source_authoritative=True,
            source_available_at=self.valid_from,
            source_committed_at=self.valid_from,
            source_commit_receipt_valid=True,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            profile_digest="a" * 64,
        )
        self.policy = ExpectedSlotPolicy(
            expected_slot_policy_id="slots-hype",
            calendar_profile_id=self.continuous.calendar_profile_id,
            wake_interval=timedelta(hours=1),
            bar_timeframes=(timedelta(hours=1),),
            strategic_review_intervals=(timedelta(hours=4),),
            grace_period=timedelta(0),
            source_lateness=timedelta(0),
            gap_terminal_policy="STOP_AT_FIRST_UNRECOVERABLE_BAR",
            policy_digest="b" * 64,
        )

    def _cursor(
        self,
        kind: SlotKind,
        interval_seconds: int,
        last: datetime,
        suffix: str,
    ) -> SchedulerCursor:
        return SchedulerCursor(
            cursor_id=f"cursor-{suffix}",
            kind=kind,
            calendar_profile_id=self.continuous.calendar_profile_id,
            instrument_id=self.continuous.instrument_id,
            interval_seconds=interval_seconds,
            last_slot_at=last,
            last_slot_id=None,
            revision=0,
            state_digest="c" * 64,
            aggregate_head_receipt_valid=True,
            is_genesis=True,
        )

    def _all_cursors(self, start: datetime) -> tuple[SchedulerCursor, ...]:
        return (
            self._cursor(SlotKind.WAKE, 3600, start, "wake"),
            self._cursor(SlotKind.BAR, 3600, start, "bar"),
            self._cursor(
                SlotKind.STRATEGIC_REVIEW, 14_400, start, "review"
            ),
        )

    def _recovery(
        self,
        slot_id: str,
        cutoff: datetime,
        *,
        available_at: datetime | None = None,
        fully: bool = True,
    ) -> RecoveryEvidence:
        return RecoveryEvidence(
            slot_id=slot_id,
            evidence_id=f"evidence-{slot_id}",
            available_at=available_at or cutoff,
            ingested_at=cutoff,
            source_committed_at=cutoff,
            source_commit_receipt_valid=True,
            lineage_valid=True,
            physical_existence_proven=True,
            fully_pit_recoverable=fully,
            corporate_action_status=CorporateActionStatus.PASS,
        )

    def test_continuous_slots_remain_utc_epoch_aligned_across_dst(self) -> None:
        start = datetime(2026, 11, 1, 4, tzinfo=UTC)
        end = datetime(2026, 11, 1, 9, tzinfo=UTC)
        slots = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.BAR,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=end,
            decision_cutoff=end,
        )
        self.assertEqual(
            tuple(datetime(2026, 11, 1, hour, tzinfo=UTC) for hour in range(5, 10)),
            tuple(item.due_at for item in slots),
        )

    def test_session_calendar_uses_iana_dst_and_closed_weekend_is_not_gap(self) -> None:
        profile = TradingSessionCalendarProfile(
            calendar_profile_id="calendar-equity",
            instrument_id="SNDK",
            venue_id="NASDAQ",
            market_clock_type=MarketClockType.SESSION_CALENDAR,
            iana_timezone="America/New_York",
            weekly_session_specs=tuple(
                WeeklySessionSpec(
                    weekday=weekday,
                    local_open_time=time(9, 30),
                    local_close_time=time(16),
                    session_label="REGULAR",
                )
                for weekday in (
                    Weekday.MON,
                    Weekday.TUE,
                    Weekday.WED,
                    Weekday.THU,
                    Weekday.FRI,
                )
            ),
            holiday_closures=(),
            special_sessions=(),
            halt_intervals=(),
            bar_alignment_policy=BarAlignmentPolicy.SESSION_OPEN,
            calendar_source_id="nasdaq-calendar",
            calendar_source_authoritative=True,
            source_available_at=self.valid_from,
            source_committed_at=self.valid_from,
            source_commit_receipt_valid=True,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            profile_digest="d" * 64,
        )
        policy = replace(
            self.policy,
            calendar_profile_id=profile.calendar_profile_id,
            expected_slot_policy_id="slots-equity",
        )
        slots = enumerate_expected_slots(
            profile=profile,
            policy=policy,
            kind=SlotKind.BAR,
            interval=timedelta(hours=1),
            after_exclusive=datetime(2026, 3, 6, 14, 30, tzinfo=UTC),
            through_inclusive=datetime(2026, 3, 9, 20, tzinfo=UTC),
            decision_cutoff=datetime(2026, 3, 9, 20, tzinfo=UTC),
        )
        friday = [item for item in slots if "2026-03-06" in item.session_label]
        monday = [item for item in slots if "2026-03-09" in item.session_label]
        self.assertEqual(datetime(2026, 3, 6, 15, 30, tzinfo=UTC), friday[0].due_at)
        self.assertEqual(datetime(2026, 3, 9, 14, 30, tzinfo=UTC), monday[0].due_at)
        self.assertFalse(
            any(item.due_at.date() in {date(2026, 3, 7), date(2026, 3, 8)} for item in slots)
        )

    def test_ambiguous_dst_session_boundary_fails_closed(self) -> None:
        profile = TradingSessionCalendarProfile(
            calendar_profile_id="calendar-ambiguous",
            instrument_id="TEST",
            venue_id="TEST",
            market_clock_type=MarketClockType.SESSION_CALENDAR,
            iana_timezone="America/New_York",
            weekly_session_specs=(
                WeeklySessionSpec(
                    weekday=Weekday.SUN,
                    local_open_time=time(1, 30),
                    local_close_time=time(3),
                    session_label="AMBIGUOUS",
                ),
            ),
            holiday_closures=(),
            special_sessions=(),
            halt_intervals=(),
            bar_alignment_policy=BarAlignmentPolicy.SESSION_OPEN,
            calendar_source_id="test-calendar",
            calendar_source_authoritative=True,
            source_available_at=self.valid_from,
            source_committed_at=self.valid_from,
            source_commit_receipt_valid=True,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            profile_digest="e" * 64,
        )
        policy = replace(
            self.policy,
            calendar_profile_id=profile.calendar_profile_id,
            expected_slot_policy_id="slots-ambiguous",
        )
        with self.assertRaisesRegex(
            CalendarError, "SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS"
        ):
            enumerate_expected_slots(
                profile=profile,
                policy=policy,
                kind=SlotKind.BAR,
                interval=timedelta(hours=1),
                after_exclusive=datetime(2026, 11, 1, 4, tzinfo=UTC),
                through_inclusive=datetime(2026, 11, 1, 9, tzinfo=UTC),
                decision_cutoff=datetime(2026, 11, 1, 9, tzinfo=UTC),
            )

    def test_missing_bar_stops_only_bar_cursor_at_contiguous_prefix(self) -> None:
        start = datetime(2026, 7, 1, tzinfo=UTC)
        cutoff = start + timedelta(hours=3)
        bars = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.BAR,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )
        wakes = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.WAKE,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )
        result = assess_schedule_catchup(
            profile=self.continuous,
            policy=self.policy,
            cursors=self._all_cursors(start),
            completed_slots=tuple(
                CompletedSlot(item.slot_id, item.due_at, True) for item in wakes
            ),
            recovery_evidence=(
                self._recovery(bars[0].slot_id, cutoff),
                self._recovery(bars[2].slot_id, cutoff),
            ),
            decision_cutoff=cutoff,
        )
        bar_advance = next(
            item
            for item in result.cursor_advance_receipts
            if item.cursor_id == "cursor-bar"
        )
        self.assertEqual((bars[0].slot_id,), bar_advance.advanced_slot_ids)
        self.assertEqual(bars[1].slot_id, bar_advance.blocked_at_slot_id)
        self.assertEqual((bars[0].slot_id,), result.bar_replay_slot_ids)
        status_by_slot = {
            item.expected_slot.slot_id: (
                None if item.gap_receipt is None else item.gap_receipt.status
            )
            for item in result.assessments
        }
        self.assertEqual(
            ScheduleGapStatus.UNRECOVERABLE, status_by_slot[bars[1].slot_id]
        )
        self.assertEqual(
            ScheduleGapStatus.BAR_RECOVERED, status_by_slot[bars[2].slot_id]
        )

    def test_missed_review_is_censored_while_wake_cursor_can_advance(self) -> None:
        start = datetime(2026, 7, 1, tzinfo=UTC)
        cutoff = start + timedelta(hours=4)
        wakes = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.WAKE,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )
        bars = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.BAR,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )
        result = assess_schedule_catchup(
            profile=self.continuous,
            policy=self.policy,
            cursors=self._all_cursors(start),
            completed_slots=tuple(
                CompletedSlot(item.slot_id, item.due_at, True)
                for item in (*wakes, *bars)
            ),
            recovery_evidence=(),
            decision_cutoff=cutoff,
        )
        wake_advance = next(
            item
            for item in result.cursor_advance_receipts
            if item.cursor_id == "cursor-wake"
        )
        review_advance = next(
            item
            for item in result.cursor_advance_receipts
            if item.cursor_id == "cursor-review"
        )
        self.assertEqual(cutoff, wake_advance.next_last_slot_at)
        self.assertEqual(start, review_advance.next_last_slot_at)
        self.assertEqual(1, len(result.censored_strategic_review_slot_ids))

    def test_late_ingestion_cannot_manufacture_a_historical_review(self) -> None:
        start = datetime(2026, 7, 1, tzinfo=UTC)
        cutoff = start + timedelta(hours=5)
        reviews = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.STRATEGIC_REVIEW,
            interval=timedelta(hours=4),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )
        wakes = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.WAKE,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )
        bars = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.BAR,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )
        late = RecoveryEvidence(
            slot_id=reviews[0].slot_id,
            evidence_id="late-review-evidence",
            available_at=reviews[0].due_at,
            ingested_at=cutoff,
            source_committed_at=cutoff,
            source_commit_receipt_valid=True,
            lineage_valid=True,
            physical_existence_proven=True,
            fully_pit_recoverable=True,
            corporate_action_status=CorporateActionStatus.NOT_APPLICABLE,
        )
        result = assess_schedule_catchup(
            profile=self.continuous,
            policy=self.policy,
            cursors=self._all_cursors(start),
            completed_slots=tuple(
                CompletedSlot(item.slot_id, item.due_at, True)
                for item in (*wakes, *bars)
            ),
            recovery_evidence=(late,),
            decision_cutoff=cutoff,
        )
        review = next(
            item
            for item in result.assessments
            if item.expected_slot.kind is SlotKind.STRATEGIC_REVIEW
        )
        self.assertEqual(
            ScheduleGapStatus.PARTIAL_SOURCE_GAP, review.gap_receipt.status
        )
        self.assertIn(
            review.expected_slot.slot_id,
            result.censored_strategic_review_slot_ids,
        )

    def test_future_recovery_and_cursor_mismatch_fail_closed(self) -> None:
        start = datetime(2026, 7, 1, tzinfo=UTC)
        cutoff = start + timedelta(hours=1)
        bar = enumerate_expected_slots(
            profile=self.continuous,
            policy=self.policy,
            kind=SlotKind.BAR,
            interval=timedelta(hours=1),
            after_exclusive=start,
            through_inclusive=cutoff,
            decision_cutoff=cutoff,
        )[0]
        with self.assertRaisesRegex(ScheduleCatchupError, "PIT_FUTURE_AVAILABLE"):
            assess_schedule_catchup(
                profile=self.continuous,
                policy=self.policy,
                cursors=self._all_cursors(start),
                completed_slots=(),
                recovery_evidence=(
                    self._recovery(
                        bar.slot_id,
                        cutoff,
                        available_at=cutoff + timedelta(seconds=1),
                    ),
                ),
                decision_cutoff=cutoff,
            )
        mismatched_bar = SchedulerCursor(
            cursor_id="cursor-bar",
            kind=SlotKind.BAR,
            calendar_profile_id=self.continuous.calendar_profile_id,
            instrument_id=self.continuous.instrument_id,
            interval_seconds=3600,
            last_slot_at=start + timedelta(minutes=30),
            last_slot_id=make_slot_id(
                kind=SlotKind.BAR,
                calendar_profile_id=self.continuous.calendar_profile_id,
                instrument_id=self.continuous.instrument_id,
                interval_seconds=3600,
                due_at=start + timedelta(minutes=30),
            ),
            revision=1,
            state_digest="f" * 64,
            aggregate_head_receipt_valid=True,
            is_genesis=False,
        )
        cursors = tuple(
            mismatched_bar if item.kind is SlotKind.BAR else item
            for item in self._all_cursors(start)
        )
        with self.assertRaisesRegex(
            ScheduleCatchupError, "SCHEDULE_CURSOR_NONCONTIGUOUS"
        ):
            assess_schedule_catchup(
                profile=self.continuous,
                policy=self.policy,
                cursors=cursors,
                completed_slots=(),
                recovery_evidence=(),
                decision_cutoff=cutoff,
            )


class AuthorityAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cutoff = datetime(2026, 7, 1, 1, tzinfo=UTC)
        self.expectation = AuthorityExpectation(
            offline_run_id="run-e0-1",
            runtime_id="runtime-e0-1",
            manifest_id="manifest-e0-1",
            authorization_envelope_id="authority-envelope-e0-1",
            decision_session_id="session-e0-1",
        )
        self.clock = TrustedTimestampInput(
            timestamp=self.cutoff,
            source_id="trusted-clock-1",
            source_kind=ClockSourceKind.FROZEN_LOCAL_AUTHORITY,
            source_available_at=self.cutoff,
            source_committed_at=self.cutoff,
            source_commit_receipt_digest="1" * 64,
            source_commit_receipt_valid=True,
            authoritative=True,
        )
        self.receipt = build_e0_authority_receipt(
            authority_receipt_id="authority-receipt-1",
            expectation=self.expectation,
            decision_cutoff=self.cutoff,
            issued_at=self.cutoff,
            trusted_time=self.clock,
        )

    def test_exact_e0_tuple_and_explicit_clock_validate(self) -> None:
        validated = E0AuthorityAdapter().validate(
            expectation=self.expectation,
            receipt=self.receipt,
            trusted_time=self.clock,
        )
        self.assertEqual(self.cutoff, validated.decision_cutoff)
        self.assertFalse(validated.executable)
        self.assertEqual("NONE_E0", validated.external_execution_authority)

    def test_authority_identity_execution_or_untrusted_clock_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            AuthorityAdapterError, "AUTHORITY_STATUS_MISMATCH"
        ):
            E0AuthorityAdapter().validate(
                expectation=self.expectation,
                receipt=replace(self.receipt, runtime_id="different-runtime"),
                trusted_time=self.clock,
            )
        with self.assertRaisesRegex(
            AuthorityAdapterError, "E0_ACTION_AUTHORITY_NONE"
        ):
            E0AuthorityAdapter().validate(
                expectation=self.expectation,
                receipt=replace(self.receipt, executable=True),
                trusted_time=self.clock,
            )
        with self.assertRaisesRegex(AuthorityAdapterError, "CLOCK_UNTRUSTED"):
            E0AuthorityAdapter().validate(
                expectation=self.expectation,
                receipt=self.receipt,
                trusted_time=replace(self.clock, authoritative=False),
            )


class FrozenReplayBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cutoff = datetime(2026, 7, 1, 1, tzinfo=UTC)
        self.captured = self.cutoff + timedelta(days=1)
        self.payload = b'{"bar":"closed"}'
        self.source = build_source_provenance(
            source_id="official-archive-1",
            source_kind=SourceKind.PUBLIC_OFFICIAL_ARCHIVE,
            provider_id="official-provider",
            source_locator="https://example.com/official/archive",
            source_revision="revision-1",
            released_at=self.cutoff,
            captured_at=self.captured,
            committed_at=self.captured,
            source_commit_receipt_digest="2" * 64,
            source_content_digest="3" * 64,
        )
        self.item = build_frozen_replay_item(
            item_id="bar-item-1",
            logical_key="HYPEUSDT|1h|2026-07-01T01:00:00Z",
            record_kind=ReplayRecordKind.CLOSED_BAR,
            source=self.source,
            payload=self.payload,
            observed_at=self.cutoff,
            available_at=self.cutoff,
            ingested_at=self.captured,
            source_committed_at=self.captured,
            usage_scope=EvidenceScope.COUNTERFACTUAL_MARKET_REPLAY,
            decision_bearing=False,
        )
        self.manifest = build_frozen_replay_manifest(
            bundle_id="bundle-historical-1",
            dataset_type=DatasetType.HISTORICAL_COUNTERFACTUAL_REPLAY,
            source_cohort_id="cohort-1",
            decision_cutoff=self.cutoff,
            frozen_at=self.captured,
            sources=(self.source,),
            items=(self.item,),
        )

    def test_archive_ingestion_after_cutoff_is_replay_only_not_decision_data(self) -> None:
        validated = validate_frozen_replay_bundle(
            manifest=self.manifest,
            sources=(self.source,),
            items=(self.item,),
            payload_by_item_id={self.item.item_id: self.payload},
        )
        self.assertEqual((self.item.item_id,), validated.market_replay_item_ids)
        self.assertEqual((), validated.decision_item_ids)
        self.assertFalse(validated.executable)
        with self.assertRaises(TypeError):
            validated.payload_by_item_id[self.item.item_id] = b"rewrite"

    def test_missing_payload_and_ambiguous_logical_key_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            FrozenReplayBundleError, "OFFLINE_REPLAY_FAILED_NO_COMMIT"
        ):
            validate_frozen_replay_bundle(
                manifest=self.manifest,
                sources=(self.source,),
                items=(self.item,),
                payload_by_item_id={},
            )
        second_payload = b'{"bar":"other"}'
        second = build_frozen_replay_item(
            item_id="bar-item-2",
            logical_key=self.item.logical_key,
            record_kind=ReplayRecordKind.CLOSED_BAR,
            source=self.source,
            payload=second_payload,
            observed_at=self.cutoff,
            available_at=self.cutoff,
            ingested_at=self.captured,
            source_committed_at=self.captured,
            usage_scope=EvidenceScope.COUNTERFACTUAL_MARKET_REPLAY,
            decision_bearing=False,
        )
        manifest = build_frozen_replay_manifest(
            bundle_id="bundle-ambiguous",
            dataset_type=DatasetType.HISTORICAL_COUNTERFACTUAL_REPLAY,
            source_cohort_id="cohort-1",
            decision_cutoff=self.cutoff,
            frozen_at=self.captured,
            sources=(self.source,),
            items=(self.item, second),
        )
        with self.assertRaisesRegex(
            FrozenReplayBundleError, "OFFLINE_REPLAY_FAILED_NO_COMMIT"
        ):
            validate_frozen_replay_bundle(
                manifest=manifest,
                sources=(self.source,),
                items=(self.item, second),
                payload_by_item_id={
                    self.item.item_id: self.payload,
                    second.item_id: second_payload,
                },
            )

    def test_future_market_data_tampered_payload_and_bad_source_are_rejected(self) -> None:
        future = build_frozen_replay_item(
            item_id="bar-item-future",
            logical_key="HYPEUSDT|1h|future",
            record_kind=ReplayRecordKind.CLOSED_BAR,
            source=self.source,
            payload=self.payload,
            observed_at=self.cutoff,
            available_at=self.cutoff + timedelta(seconds=1),
            ingested_at=self.captured,
            source_committed_at=self.captured,
            usage_scope=EvidenceScope.COUNTERFACTUAL_MARKET_REPLAY,
            decision_bearing=False,
        )
        future_manifest = build_frozen_replay_manifest(
            bundle_id="bundle-future",
            dataset_type=DatasetType.HISTORICAL_COUNTERFACTUAL_REPLAY,
            source_cohort_id="cohort-1",
            decision_cutoff=self.cutoff,
            frozen_at=self.captured,
            sources=(self.source,),
            items=(future,),
        )
        with self.assertRaisesRegex(
            FrozenReplayBundleError, "PIT_FUTURE_AVAILABLE"
        ):
            validate_frozen_replay_bundle(
                manifest=future_manifest,
                sources=(self.source,),
                items=(future,),
                payload_by_item_id={future.item_id: self.payload},
            )
        with self.assertRaisesRegex(
            FrozenReplayBundleError, "EVIDENCE_LINEAGE_INVALID"
        ):
            validate_frozen_replay_bundle(
                manifest=self.manifest,
                sources=(self.source,),
                items=(self.item,),
                payload_by_item_id={self.item.item_id: b"tampered"},
            )
        bad_source = build_source_provenance(
            source_id="bad-public-source",
            source_kind=SourceKind.PUBLIC_OFFICIAL_ARCHIVE,
            provider_id="provider",
            source_locator="http://not-accepted.example/archive",
            source_revision="revision-1",
            released_at=self.cutoff,
            captured_at=self.captured,
            committed_at=self.captured,
            source_commit_receipt_digest="4" * 64,
            source_content_digest="5" * 64,
        )
        bad_item = build_frozen_replay_item(
            item_id="bad-item",
            logical_key="bad|bar",
            record_kind=ReplayRecordKind.CLOSED_BAR,
            source=bad_source,
            payload=self.payload,
            observed_at=self.cutoff,
            available_at=self.cutoff,
            ingested_at=self.captured,
            source_committed_at=self.captured,
            usage_scope=EvidenceScope.COUNTERFACTUAL_MARKET_REPLAY,
            decision_bearing=False,
        )
        bad_manifest = build_frozen_replay_manifest(
            bundle_id="bundle-bad-source",
            dataset_type=DatasetType.HISTORICAL_COUNTERFACTUAL_REPLAY,
            source_cohort_id="cohort-1",
            decision_cutoff=self.cutoff,
            frozen_at=self.captured,
            sources=(bad_source,),
            items=(bad_item,),
        )
        with self.assertRaisesRegex(
            FrozenReplayBundleError, "EVIDENCE_LINEAGE_INVALID"
        ):
            validate_frozen_replay_bundle(
                manifest=bad_manifest,
                sources=(bad_source,),
                items=(bad_item,),
                payload_by_item_id={bad_item.item_id: self.payload},
            )


if __name__ == "__main__":
    unittest.main()
