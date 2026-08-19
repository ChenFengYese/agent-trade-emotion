"""Expected-slot, gap, catch-up, and cursor continuity primitives."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from ..common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from .calendar import (
    BarAlignmentPolicy,
    CalendarError,
    MarketClockType,
    TradingSessionCalendarProfile,
    enumerate_trading_intervals,
    interval_intersects_halt,
    require_utc,
)


class SlotKind(StrEnum):
    WAKE = "WAKE"
    BAR = "BAR"
    STRATEGIC_REVIEW = "STRATEGIC_REVIEW"


class ScheduleGapStatus(StrEnum):
    DETECTED = "DETECTED"
    BAR_RECOVERED = "BAR_RECOVERED"
    RECOVERED_FULL = "RECOVERED_FULL"
    PARTIAL_SOURCE_GAP = "PARTIAL_SOURCE_GAP"
    UNRECOVERABLE = "UNRECOVERABLE"


class CorporateActionStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PASS = "PASS"
    UNKNOWN = "UNKNOWN"


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _positive_whole_seconds(value: timedelta, code: str) -> int:
    if value <= timedelta(0) or value.microseconds:
        raise CalendarError(code)
    seconds = int(value.total_seconds())
    if seconds <= 0:
        raise CalendarError(code)
    return seconds


@dataclass(frozen=True, slots=True)
class ExpectedSlotPolicy:
    expected_slot_policy_id: str
    calendar_profile_id: str
    wake_interval: timedelta
    bar_timeframes: tuple[timedelta, ...]
    strategic_review_intervals: tuple[timedelta, ...]
    grace_period: timedelta
    source_lateness: timedelta
    gap_terminal_policy: str
    policy_digest: str

    def __post_init__(self) -> None:
        if (
            not self.expected_slot_policy_id
            or not self.calendar_profile_id
            or not self.bar_timeframes
            or not self.strategic_review_intervals
            or self.gap_terminal_policy != "STOP_AT_FIRST_UNRECOVERABLE_BAR"
            or _SHA256.fullmatch(self.policy_digest) is None
        ):
            raise CalendarError("SCHEDULE_EXPECTED_SLOT_POLICY_MISSING")
        _positive_whole_seconds(
            self.wake_interval, "SCHEDULE_EXPECTED_SLOT_POLICY_MISSING"
        )
        bar_seconds = tuple(
            _positive_whole_seconds(
                item, "SCHEDULE_EXPECTED_SLOT_POLICY_MISSING"
            )
            for item in self.bar_timeframes
        )
        review_seconds = tuple(
            _positive_whole_seconds(
                item, "SCHEDULE_EXPECTED_SLOT_POLICY_MISSING"
            )
            for item in self.strategic_review_intervals
        )
        if (
            len(set(bar_seconds)) != len(bar_seconds)
            or len(set(review_seconds)) != len(review_seconds)
            or self.grace_period < timedelta(0)
            or self.source_lateness < timedelta(0)
        ):
            raise CalendarError("SCHEDULE_EXPECTED_SLOT_POLICY_MISSING")

    def intervals_for(self, kind: SlotKind) -> tuple[timedelta, ...]:
        if kind is SlotKind.WAKE:
            return (self.wake_interval,)
        if kind is SlotKind.BAR:
            return self.bar_timeframes
        return self.strategic_review_intervals


@dataclass(frozen=True, slots=True)
class ExpectedSlot:
    slot_id: str
    kind: SlotKind
    calendar_profile_id: str
    instrument_id: str
    interval_seconds: int
    period_start: datetime
    due_at: datetime
    terminal_classification_at: datetime
    session_label: str

    def __post_init__(self) -> None:
        for value in (
            self.period_start,
            self.due_at,
            self.terminal_classification_at,
        ):
            require_utc(value)
        if (
            not self.slot_id
            or not self.calendar_profile_id
            or not self.instrument_id
            or not self.session_label
            or self.interval_seconds <= 0
            or self.period_start >= self.due_at
            or self.terminal_classification_at < self.due_at
        ):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")


def make_slot_id(
    *,
    kind: SlotKind,
    calendar_profile_id: str,
    instrument_id: str,
    interval_seconds: int,
    due_at: datetime,
) -> str:
    require_utc(due_at)
    logical_key = "|".join(
        (
            kind.value,
            calendar_profile_id,
            instrument_id,
            str(interval_seconds),
            due_at.isoformat().replace("+00:00", "Z"),
        )
    )
    return f"slot-{hashlib.sha256(logical_key.encode('utf-8')).hexdigest()}"


def _slot(
    *,
    profile: TradingSessionCalendarProfile,
    policy: ExpectedSlotPolicy,
    kind: SlotKind,
    interval_seconds: int,
    period_start: datetime,
    due_at: datetime,
    session_label: str,
) -> ExpectedSlot:
    lateness = (
        policy.source_lateness
        if kind in {SlotKind.BAR, SlotKind.STRATEGIC_REVIEW}
        else timedelta(0)
    )
    return ExpectedSlot(
        slot_id=make_slot_id(
            kind=kind,
            calendar_profile_id=profile.calendar_profile_id,
            instrument_id=profile.instrument_id,
            interval_seconds=interval_seconds,
            due_at=due_at,
        ),
        kind=kind,
        calendar_profile_id=profile.calendar_profile_id,
        instrument_id=profile.instrument_id,
        interval_seconds=interval_seconds,
        period_start=period_start,
        due_at=due_at,
        terminal_classification_at=due_at + policy.grace_period + lateness,
        session_label=session_label,
    )


def _first_epoch_boundary_after(value: datetime, interval_seconds: int) -> datetime:
    elapsed = value - _EPOCH
    elapsed_microseconds = (
        elapsed.days * 86_400_000_000
        + elapsed.seconds * 1_000_000
        + elapsed.microseconds
    )
    quantum = interval_seconds * 1_000_000
    next_multiple = (elapsed_microseconds // quantum + 1) * quantum
    return _EPOCH + timedelta(microseconds=next_multiple)


def enumerate_expected_slots(
    *,
    profile: TradingSessionCalendarProfile,
    policy: ExpectedSlotPolicy,
    kind: SlotKind,
    interval: timedelta,
    after_exclusive: datetime,
    through_inclusive: datetime,
    decision_cutoff: datetime,
) -> tuple[ExpectedSlot, ...]:
    """Enumerate due slots; closed sessions, holidays, and halts are omitted."""

    for value in (after_exclusive, through_inclusive, decision_cutoff):
        require_utc(value)
    if policy.calendar_profile_id != profile.calendar_profile_id:
        raise CalendarError("SCHEDULE_EXPECTED_SLOT_POLICY_MISSING")
    if interval not in policy.intervals_for(kind):
        raise CalendarError("SCHEDULE_EXPECTED_SLOT_POLICY_MISSING")
    if through_inclusive < after_exclusive:
        raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
    interval_seconds = _positive_whole_seconds(
        interval, "SCHEDULE_EXPECTED_SLOT_POLICY_MISSING"
    )
    # Validates the profile revision and source at the explicit cutoff.
    intervals = enumerate_trading_intervals(
        profile,
        interval_start=after_exclusive,
        interval_end=through_inclusive,
        decision_cutoff=decision_cutoff,
    )
    candidates: list[ExpectedSlot] = []
    if profile.market_clock_type is MarketClockType.CONTINUOUS_24_7:
        if profile.bar_alignment_policy is not BarAlignmentPolicy.UTC_EPOCH:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        due_at = _first_epoch_boundary_after(after_exclusive, interval_seconds)
        while due_at <= through_inclusive:
            period_start = due_at - interval
            slot = _slot(
                profile=profile,
                policy=policy,
                kind=kind,
                interval_seconds=interval_seconds,
                period_start=period_start,
                due_at=due_at,
                session_label="CONTINUOUS_24_7",
            )
            if (
                slot.terminal_classification_at <= through_inclusive
                and not interval_intersects_halt(
                    profile, start_at=period_start, end_at=due_at
                )
            ):
                candidates.append(slot)
            due_at += interval
    else:
        if profile.bar_alignment_policy is not BarAlignmentPolicy.SESSION_OPEN:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        for trading_interval in intervals:
            due_at = trading_interval.start_at + interval
            while due_at <= trading_interval.end_at:
                period_start = due_at - interval
                slot = _slot(
                    profile=profile,
                    policy=policy,
                    kind=kind,
                    interval_seconds=interval_seconds,
                    period_start=period_start,
                    due_at=due_at,
                    session_label=trading_interval.session_label,
                )
                if (
                    due_at > after_exclusive
                    and slot.terminal_classification_at <= through_inclusive
                    and not interval_intersects_halt(
                        profile, start_at=period_start, end_at=due_at
                    )
                ):
                    candidates.append(slot)
                due_at += interval
    candidates.sort(key=lambda item: (item.due_at, item.slot_id))
    if len({item.slot_id for item in candidates}) != len(candidates):
        raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
    return tuple(candidates)


@dataclass(frozen=True, slots=True)
class SchedulerCursor:
    cursor_id: str
    kind: SlotKind
    calendar_profile_id: str
    instrument_id: str
    interval_seconds: int
    last_slot_at: datetime
    last_slot_id: str | None
    revision: int
    state_digest: str
    aggregate_head_receipt_valid: bool
    is_genesis: bool = False

    def __post_init__(self) -> None:
        require_utc(self.last_slot_at)
        if (
            not self.cursor_id
            or not self.calendar_profile_id
            or not self.instrument_id
            or self.interval_seconds <= 0
            or self.revision < 0
            or _SHA256.fullmatch(self.state_digest) is None
            or (self.is_genesis and self.last_slot_id is not None)
            or (not self.is_genesis and not self.last_slot_id)
        ):
            raise CalendarError("SCHEDULE_CURSOR_NONCONTIGUOUS")


@dataclass(frozen=True, slots=True)
class CompletedSlot:
    slot_id: str
    completed_at: datetime
    completion_receipt_valid: bool

    def __post_init__(self) -> None:
        require_utc(self.completed_at)
        if not self.slot_id:
            raise CalendarError("SCHEDULE_CURSOR_NONCONTIGUOUS")


@dataclass(frozen=True, slots=True)
class RecoveryEvidence:
    slot_id: str
    evidence_id: str
    available_at: datetime
    ingested_at: datetime
    source_committed_at: datetime
    source_commit_receipt_valid: bool
    lineage_valid: bool
    physical_existence_proven: bool
    fully_pit_recoverable: bool
    corporate_action_status: CorporateActionStatus

    def __post_init__(self) -> None:
        for value in (
            self.available_at,
            self.ingested_at,
            self.source_committed_at,
        ):
            require_utc(value)
        if not self.slot_id or not self.evidence_id:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")

    def pit_valid(self, decision_cutoff: datetime) -> bool:
        require_utc(decision_cutoff)
        return (
            self.available_at <= decision_cutoff
            and self.ingested_at <= decision_cutoff
            and self.source_committed_at <= decision_cutoff
            and self.source_commit_receipt_valid
            and self.lineage_valid
            and self.physical_existence_proven
        )


@dataclass(frozen=True, slots=True)
class ScheduleGapReceipt:
    receipt_id: str
    slot_id: str
    kind: SlotKind
    status: ScheduleGapStatus
    reason_codes: tuple[str, ...]
    evidence_id: str | None
    terminal: bool
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False

    def __post_init__(self) -> None:
        if (
            not self.receipt_id
            or not self.slot_id
            or not self.reason_codes
            or self.system_mode != SYSTEM_MODE
            or self.external_execution_authority
            != EXTERNAL_EXECUTION_AUTHORITY
            or self.executable
            or self.terminal != (self.status is not ScheduleGapStatus.DETECTED)
        ):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")


@dataclass(frozen=True, slots=True)
class SlotAssessment:
    expected_slot: ExpectedSlot
    completed: bool
    gap_receipt: ScheduleGapReceipt | None

    def __post_init__(self) -> None:
        if self.completed == (self.gap_receipt is not None):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")


@dataclass(frozen=True, slots=True)
class CursorAdvanceReceipt:
    cursor_id: str
    prior_revision: int
    next_revision: int
    prior_last_slot_at: datetime
    next_last_slot_at: datetime
    advanced_slot_ids: tuple[str, ...]
    blocked_at_slot_id: str | None
    next_state_digest: str
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False

    def __post_init__(self) -> None:
        require_utc(self.prior_last_slot_at)
        require_utc(self.next_last_slot_at)
        if (
            not self.cursor_id
            or self.next_revision not in {self.prior_revision, self.prior_revision + 1}
            or self.next_last_slot_at < self.prior_last_slot_at
            or _SHA256.fullmatch(self.next_state_digest) is None
            or self.system_mode != SYSTEM_MODE
            or self.external_execution_authority
            != EXTERNAL_EXECUTION_AUTHORITY
            or self.executable
        ):
            raise CalendarError("SCHEDULE_CURSOR_NONCONTIGUOUS")


@dataclass(frozen=True, slots=True)
class TimelineCatchupResult:
    assessments: tuple[SlotAssessment, ...]
    cursor_advance_receipts: tuple[CursorAdvanceReceipt, ...]
    bar_replay_slot_ids: tuple[str, ...]
    censored_strategic_review_slot_ids: tuple[str, ...]
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False

    def __post_init__(self) -> None:
        if (
            self.system_mode != SYSTEM_MODE
            or self.external_execution_authority
            != EXTERNAL_EXECUTION_AUTHORITY
            or self.executable
        ):
            raise CalendarError("AUTHORITY_STATUS_MISMATCH")
