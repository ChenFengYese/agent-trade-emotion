"""Pure application orchestration for deterministic schedule catch-up."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Iterable

from ..domain.contracts.canonical import canonical_digest
from ..domain.time_authority.calendar import (
    CalendarError,
    TradingSessionCalendarProfile,
    require_utc,
)
from ..domain.time_authority.scheduler import (
    CompletedSlot,
    CorporateActionStatus,
    CursorAdvanceReceipt,
    ExpectedSlot,
    ExpectedSlotPolicy,
    RecoveryEvidence,
    ScheduleGapReceipt,
    ScheduleGapStatus,
    SchedulerCursor,
    SlotAssessment,
    SlotKind,
    TimelineCatchupResult,
    enumerate_expected_slots,
    make_slot_id,
)


class ScheduleCatchupError(ValueError):
    """A scheduler session cannot produce an authoritative catch-up result."""


def _cursor_key(cursor: SchedulerCursor) -> tuple[SlotKind, int]:
    return cursor.kind, cursor.interval_seconds


def _policy_keys(policy: ExpectedSlotPolicy) -> set[tuple[SlotKind, int]]:
    return {
        (SlotKind.WAKE, int(policy.wake_interval.total_seconds())),
        *{
            (SlotKind.BAR, int(item.total_seconds()))
            for item in policy.bar_timeframes
        },
        *{
            (SlotKind.STRATEGIC_REVIEW, int(item.total_seconds()))
            for item in policy.strategic_review_intervals
        },
    }


def _validate_cursor(
    *,
    cursor: SchedulerCursor,
    profile: TradingSessionCalendarProfile,
    policy: ExpectedSlotPolicy,
    decision_cutoff: datetime,
) -> None:
    if (
        cursor.calendar_profile_id != profile.calendar_profile_id
        or cursor.instrument_id != profile.instrument_id
        or not cursor.aggregate_head_receipt_valid
        or _cursor_key(cursor) not in _policy_keys(policy)
    ):
        raise ScheduleCatchupError("SCHEDULE_CURSOR_NONCONTIGUOUS")
    if cursor.is_genesis:
        if cursor.revision != 0:
            raise ScheduleCatchupError("SCHEDULE_CURSOR_NONCONTIGUOUS")
        return
    expected_id = make_slot_id(
        kind=cursor.kind,
        calendar_profile_id=cursor.calendar_profile_id,
        instrument_id=cursor.instrument_id,
        interval_seconds=cursor.interval_seconds,
        due_at=cursor.last_slot_at,
    )
    if cursor.last_slot_id != expected_id:
        raise ScheduleCatchupError("SCHEDULE_CURSOR_NONCONTIGUOUS")
    cadence = timedelta(seconds=cursor.interval_seconds)
    classification_lag = policy.grace_period + (
        policy.source_lateness
        if cursor.kind in {SlotKind.BAR, SlotKind.STRATEGIC_REVIEW}
        else timedelta(0)
    )
    try:
        prior_slots = enumerate_expected_slots(
            profile=profile,
            policy=policy,
            kind=cursor.kind,
            interval=cadence,
            after_exclusive=cursor.last_slot_at - cadence,
            through_inclusive=cursor.last_slot_at + classification_lag,
            decision_cutoff=decision_cutoff,
        )
    except CalendarError as exc:
        raise ScheduleCatchupError("SCHEDULE_CURSOR_NONCONTIGUOUS") from exc
    if not any(item.slot_id == cursor.last_slot_id for item in prior_slots):
        raise ScheduleCatchupError("SCHEDULE_CURSOR_NONCONTIGUOUS")


def _terminal_gap(
    slot: ExpectedSlot,
    evidence: RecoveryEvidence | None,
    *,
    decision_cutoff: datetime,
) -> ScheduleGapReceipt:
    reason_codes: tuple[str, ...]
    status: ScheduleGapStatus
    if evidence is None:
        status = ScheduleGapStatus.UNRECOVERABLE
        reason_codes = ("SOURCE_ARTIFACT_MISSING",)
    else:
        if evidence.slot_id != slot.slot_id:
            raise ScheduleCatchupError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        if (
            evidence.available_at > decision_cutoff
            or evidence.ingested_at > decision_cutoff
            or evidence.source_committed_at > decision_cutoff
        ):
            raise ScheduleCatchupError("PIT_FUTURE_AVAILABLE")
        pit_valid = evidence.pit_valid(decision_cutoff)
        if slot.kind is SlotKind.BAR:
            if evidence.corporate_action_status is CorporateActionStatus.UNKNOWN:
                status = ScheduleGapStatus.UNRECOVERABLE
                reason_codes = ("SCHEDULE_CORPORATE_ACTION_UNKNOWN",)
            elif not pit_valid:
                status = ScheduleGapStatus.UNRECOVERABLE
                reason_codes = ("BAR_LINEAGE_OR_SOURCE_COMMIT_INVALID",)
            else:
                status = ScheduleGapStatus.BAR_RECOVERED
                reason_codes = ("CONTIGUOUS_BAR_RECOVERED",)
        # A missed wake/review can be reconstructed only from evidence that
        # itself satisfied PIT at that original slot.  Evidence first ingested
        # at the later catch-up cutoff may support barrier replay, but it cannot
        # manufacture a historical strategic review.
        elif (
            evidence.pit_valid(slot.terminal_classification_at)
            and evidence.fully_pit_recoverable
        ):
            status = ScheduleGapStatus.RECOVERED_FULL
            reason_codes = ("FULL_PIT_CONTEXT_RECOVERED",)
        elif pit_valid:
            status = ScheduleGapStatus.PARTIAL_SOURCE_GAP
            reason_codes = ("NON_BAR_CONTEXT_PARTIALLY_IDENTIFIED",)
        else:
            status = ScheduleGapStatus.UNRECOVERABLE
            reason_codes = ("SOURCE_LINEAGE_INVALID",)
    receipt_key = "|".join(
        (slot.slot_id, status.value, ",".join(reason_codes))
    )
    return ScheduleGapReceipt(
        receipt_id=f"schedule-gap-{hashlib.sha256(receipt_key.encode()).hexdigest()}",
        slot_id=slot.slot_id,
        kind=slot.kind,
        status=status,
        reason_codes=reason_codes,
        evidence_id=None if evidence is None else evidence.evidence_id,
        terminal=True,
    )


def _may_advance(assessment: SlotAssessment) -> bool:
    if assessment.completed:
        return True
    assert assessment.gap_receipt is not None
    status = assessment.gap_receipt.status
    if assessment.expected_slot.kind is SlotKind.WAKE:
        return status is not ScheduleGapStatus.DETECTED
    if assessment.expected_slot.kind is SlotKind.BAR:
        return status in {
            ScheduleGapStatus.BAR_RECOVERED,
            ScheduleGapStatus.RECOVERED_FULL,
        }
    return status is ScheduleGapStatus.RECOVERED_FULL


def _advance_cursor(
    cursor: SchedulerCursor,
    assessments: tuple[SlotAssessment, ...],
) -> CursorAdvanceReceipt:
    advanced: list[ExpectedSlot] = []
    blocked: str | None = None
    for assessment in assessments:
        if not _may_advance(assessment):
            blocked = assessment.expected_slot.slot_id
            break
        advanced.append(assessment.expected_slot)
    next_last = advanced[-1].due_at if advanced else cursor.last_slot_at
    next_revision = cursor.revision + 1 if advanced else cursor.revision
    next_digest = canonical_digest(
        {
            "cursor_id": cursor.cursor_id,
            "kind": cursor.kind.value,
            "calendar_profile_id": cursor.calendar_profile_id,
            "instrument_id": cursor.instrument_id,
            "interval_seconds": cursor.interval_seconds,
            "prior_revision": cursor.revision,
            "next_revision": next_revision,
            "prior_state_digest": cursor.state_digest,
            "next_last_slot_at": next_last.isoformat().replace("+00:00", "Z"),
            "advanced_slot_ids": [item.slot_id for item in advanced],
            "blocked_at_slot_id": blocked,
        }
    )
    return CursorAdvanceReceipt(
        cursor_id=cursor.cursor_id,
        prior_revision=cursor.revision,
        next_revision=next_revision,
        prior_last_slot_at=cursor.last_slot_at,
        next_last_slot_at=next_last,
        advanced_slot_ids=tuple(item.slot_id for item in advanced),
        blocked_at_slot_id=blocked,
        next_state_digest=next_digest,
    )


def assess_schedule_catchup(
    *,
    profile: TradingSessionCalendarProfile,
    policy: ExpectedSlotPolicy,
    cursors: tuple[SchedulerCursor, ...],
    completed_slots: tuple[CompletedSlot, ...],
    recovery_evidence: tuple[RecoveryEvidence, ...],
    decision_cutoff: datetime,
) -> TimelineCatchupResult:
    """Classify every expected slot and propose only contiguous cursor advances.

    The returned receipts are precommit artifacts.  The sole UnitOfWork remains
    responsible for atomically committing cursor, gap, barrier, and portfolio
    state.
    """

    require_utc(decision_cutoff)
    if policy.calendar_profile_id != profile.calendar_profile_id:
        raise ScheduleCatchupError("SCHEDULE_EXPECTED_SLOT_POLICY_MISSING")
    cursor_by_key = {_cursor_key(item): item for item in cursors}
    if len(cursor_by_key) != len(cursors) or set(cursor_by_key) != _policy_keys(policy):
        raise ScheduleCatchupError("SCHEDULE_CURSOR_NONCONTIGUOUS")
    for cursor in cursors:
        _validate_cursor(
            cursor=cursor,
            profile=profile,
            policy=policy,
            decision_cutoff=decision_cutoff,
        )

    completed_by_id = {item.slot_id: item for item in completed_slots}
    evidence_by_id = {item.slot_id: item for item in recovery_evidence}
    if (
        len(completed_by_id) != len(completed_slots)
        or len(evidence_by_id) != len(recovery_evidence)
    ):
        raise ScheduleCatchupError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")

    assessments_by_key: dict[
        tuple[SlotKind, int], tuple[SlotAssessment, ...]
    ] = {}
    all_expected_ids: set[str] = set()
    for key in sorted(cursor_by_key, key=lambda item: (item[0].value, item[1])):
        cursor = cursor_by_key[key]
        expected = enumerate_expected_slots(
            profile=profile,
            policy=policy,
            kind=cursor.kind,
            interval=timedelta(seconds=cursor.interval_seconds),
            after_exclusive=cursor.last_slot_at,
            through_inclusive=decision_cutoff,
            decision_cutoff=decision_cutoff,
        )
        current_assessments: list[SlotAssessment] = []
        for slot in expected:
            all_expected_ids.add(slot.slot_id)
            completion = completed_by_id.get(slot.slot_id)
            if completion is not None:
                if (
                    not completion.completion_receipt_valid
                    or completion.completed_at > decision_cutoff
                    or completion.completed_at < slot.due_at
                ):
                    raise ScheduleCatchupError("SCHEDULE_CURSOR_NONCONTIGUOUS")
                current_assessments.append(
                    SlotAssessment(
                        expected_slot=slot,
                        completed=True,
                        gap_receipt=None,
                    )
                )
            else:
                current_assessments.append(
                    SlotAssessment(
                        expected_slot=slot,
                        completed=False,
                        gap_receipt=_terminal_gap(
                            slot,
                            evidence_by_id.get(slot.slot_id),
                            decision_cutoff=decision_cutoff,
                        ),
                    )
                )
        assessments_by_key[key] = tuple(current_assessments)

    if (
        set(completed_by_id).difference(all_expected_ids)
        or set(evidence_by_id).difference(all_expected_ids)
    ):
        raise ScheduleCatchupError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")

    advances = tuple(
        _advance_cursor(cursor_by_key[key], assessments_by_key[key])
        for key in sorted(cursor_by_key, key=lambda item: (item[0].value, item[1]))
    )
    advance_by_cursor = {item.cursor_id: item for item in advances}
    replay_slots: list[str] = []
    censored_reviews: list[str] = []
    all_assessments: list[SlotAssessment] = []
    for key in sorted(assessments_by_key, key=lambda item: (item[0].value, item[1])):
        cursor = cursor_by_key[key]
        assessments = assessments_by_key[key]
        all_assessments.extend(assessments)
        advanced_ids = set(advance_by_cursor[cursor.cursor_id].advanced_slot_ids)
        if cursor.kind is SlotKind.BAR:
            replay_slots.extend(
                item.expected_slot.slot_id
                for item in assessments
                if item.expected_slot.slot_id in advanced_ids
            )
        elif cursor.kind is SlotKind.STRATEGIC_REVIEW:
            censored_reviews.extend(
                item.expected_slot.slot_id
                for item in assessments
                if not _may_advance(item)
            )
    all_assessments.sort(
        key=lambda item: (
            item.expected_slot.due_at,
            item.expected_slot.kind.value,
            item.expected_slot.interval_seconds,
        )
    )
    return TimelineCatchupResult(
        assessments=tuple(all_assessments),
        cursor_advance_receipts=advances,
        bar_replay_slot_ids=tuple(replay_slots),
        censored_strategic_review_slot_ids=tuple(censored_reviews),
    )
