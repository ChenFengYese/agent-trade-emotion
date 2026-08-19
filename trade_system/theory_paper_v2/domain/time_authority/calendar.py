"""Deterministic trading-calendar materialization.

The calendar owns *when* a market can have expected slots.  It has no access to
an ambient clock and does not infer holidays, venue conventions, or daylight
saving policies.  Session boundaries are resolved through the registered IANA
timezone and fail closed when a local boundary is ambiguous or nonexistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CalendarError(ValueError):
    """A typed fail-closed calendar or slot-enumeration error."""


class MarketClockType(StrEnum):
    CONTINUOUS_24_7 = "CONTINUOUS_24_7"
    SESSION_CALENDAR = "SESSION_CALENDAR"


class BarAlignmentPolicy(StrEnum):
    UTC_EPOCH = "UTC_EPOCH"
    SESSION_OPEN = "SESSION_OPEN"


class Weekday(StrEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


_WEEKDAY_NUMBER = {
    Weekday.MON: 0,
    Weekday.TUE: 1,
    Weekday.WED: 2,
    Weekday.THU: 3,
    Weekday.FRI: 4,
    Weekday.SAT: 5,
    Weekday.SUN: 6,
}


def require_utc(value: datetime, *, code: str = "CLOCK_TIME_INVALID") -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise CalendarError(code)


@dataclass(frozen=True, slots=True)
class WeeklySessionSpec:
    weekday: Weekday
    local_open_time: time
    local_close_time: time
    session_label: str

    def __post_init__(self) -> None:
        if not self.session_label:
            raise CalendarError("SCHEDULE_CALENDAR_PROFILE_MISSING")
        if (
            self.local_open_time.tzinfo is not None
            or self.local_close_time.tzinfo is not None
        ):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        if self.local_open_time == self.local_close_time:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")


@dataclass(frozen=True, slots=True)
class SpecialSession:
    local_date: date
    local_open_time: time
    local_close_time: time
    session_label: str

    def __post_init__(self) -> None:
        if (
            not self.session_label
            or self.local_open_time.tzinfo is not None
            or self.local_close_time.tzinfo is not None
            or self.local_open_time == self.local_close_time
        ):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")


@dataclass(frozen=True, slots=True)
class UtcInterval:
    start_at: datetime
    end_at: datetime
    reason: str

    def __post_init__(self) -> None:
        require_utc(self.start_at)
        require_utc(self.end_at)
        if self.end_at <= self.start_at or not self.reason:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")


@dataclass(frozen=True, slots=True)
class TradingSessionCalendarProfile:
    calendar_profile_id: str
    instrument_id: str
    venue_id: str
    market_clock_type: MarketClockType
    iana_timezone: str
    weekly_session_specs: tuple[WeeklySessionSpec, ...]
    holiday_closures: tuple[date, ...]
    special_sessions: tuple[SpecialSession, ...]
    halt_intervals: tuple[UtcInterval, ...]
    bar_alignment_policy: BarAlignmentPolicy
    calendar_source_id: str
    calendar_source_authoritative: bool
    source_available_at: datetime
    source_committed_at: datetime
    source_commit_receipt_valid: bool
    valid_from: datetime
    valid_until: datetime
    profile_digest: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.calendar_profile_id,
                self.instrument_id,
                self.venue_id,
                self.iana_timezone,
                self.calendar_source_id,
                self.profile_digest,
            )
        ):
            raise CalendarError("SCHEDULE_CALENDAR_PROFILE_MISSING")
        try:
            ZoneInfo(self.iana_timezone)
        except ZoneInfoNotFoundError as exc:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS") from exc
        for value in (
            self.source_available_at,
            self.source_committed_at,
            self.valid_from,
            self.valid_until,
        ):
            require_utc(value)
        if self.valid_until <= self.valid_from:
            raise CalendarError("SCHEDULE_CALENDAR_PROFILE_MISSING")
        if len(set(self.holiday_closures)) != len(self.holiday_closures):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        special_dates = [item.local_date for item in self.special_sessions]
        if len(set(special_dates)) != len(special_dates):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        if set(special_dates).intersection(self.holiday_closures):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        halt_keys = [(item.start_at, item.end_at) for item in self.halt_intervals]
        if len(set(halt_keys)) != len(halt_keys):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        weekly_keys = [
            (item.weekday, item.session_label) for item in self.weekly_session_specs
        ]
        if len(set(weekly_keys)) != len(weekly_keys):
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
        if self.market_clock_type is MarketClockType.CONTINUOUS_24_7:
            if (
                self.weekly_session_specs
                or self.holiday_closures
                or self.special_sessions
                or self.bar_alignment_policy is not BarAlignmentPolicy.UTC_EPOCH
            ):
                raise CalendarError("SCHEDULE_CALENDAR_PROFILE_MISSING")
        elif (
            not self.weekly_session_specs
            or self.bar_alignment_policy is not BarAlignmentPolicy.SESSION_OPEN
        ):
            raise CalendarError("SCHEDULE_CALENDAR_PROFILE_MISSING")


@dataclass(frozen=True, slots=True)
class TradingInterval:
    start_at: datetime
    end_at: datetime
    session_label: str

    def __post_init__(self) -> None:
        require_utc(self.start_at)
        require_utc(self.end_at)
        if self.end_at <= self.start_at or not self.session_label:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")


def validate_calendar_at(
    profile: TradingSessionCalendarProfile,
    *,
    decision_cutoff: datetime,
    interval_start: datetime,
    interval_end: datetime,
) -> None:
    """Validate that the exact calendar revision was lawful at the cutoff."""

    for value in (decision_cutoff, interval_start, interval_end):
        require_utc(value)
    if interval_end < interval_start:
        raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
    if (
        not profile.calendar_source_authoritative
        or not profile.source_commit_receipt_valid
        or profile.source_available_at > decision_cutoff
        or profile.source_committed_at > decision_cutoff
    ):
        raise CalendarError("SCHEDULE_CALENDAR_PROFILE_MISSING")
    if interval_start < profile.valid_from or interval_end > profile.valid_until:
        raise CalendarError("SCHEDULE_CALENDAR_PROFILE_MISSING")


def _resolve_local_boundary(
    value: datetime,
    timezone: ZoneInfo,
) -> datetime:
    """Resolve one naive local boundary or reject DST ambiguity/gaps.

    PEP 495 ``fold`` is intentionally not defaulted.  A venue calendar that
    schedules a boundary inside a repeated or nonexistent local-time interval
    must publish an explicit special session in a future contract revision.
    """

    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        aware = value.replace(tzinfo=timezone, fold=fold)
        utc_value = aware.astimezone(UTC)
        roundtrip = utc_value.astimezone(timezone)
        if roundtrip.replace(tzinfo=None) == value:
            candidates[utc_value] = aware
    if len(candidates) != 1:
        raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
    return next(iter(candidates)).astimezone(UTC)


def _local_session_interval(
    *,
    local_date: date,
    open_time: time,
    close_time: time,
    session_label: str,
    timezone: ZoneInfo,
) -> TradingInterval:
    open_naive = datetime.combine(local_date, open_time)
    close_date = local_date if close_time > open_time else local_date + timedelta(days=1)
    close_naive = datetime.combine(close_date, close_time)
    return TradingInterval(
        start_at=_resolve_local_boundary(open_naive, timezone),
        end_at=_resolve_local_boundary(close_naive, timezone),
        session_label=f"{session_label}:{local_date.isoformat()}",
    )


def enumerate_trading_intervals(
    profile: TradingSessionCalendarProfile,
    *,
    interval_start: datetime,
    interval_end: datetime,
    decision_cutoff: datetime,
) -> tuple[TradingInterval, ...]:
    """Return accepted open-market intervals intersecting ``[start, end]``."""

    validate_calendar_at(
        profile,
        decision_cutoff=decision_cutoff,
        interval_start=interval_start,
        interval_end=interval_end,
    )
    if interval_end == interval_start:
        return ()
    if profile.market_clock_type is MarketClockType.CONTINUOUS_24_7:
        return (
            TradingInterval(
                start_at=interval_start,
                end_at=interval_end,
                session_label="CONTINUOUS_24_7",
            ),
        )

    timezone = ZoneInfo(profile.iana_timezone)
    local_start = interval_start.astimezone(timezone).date() - timedelta(days=1)
    local_end = interval_end.astimezone(timezone).date() + timedelta(days=1)
    special_by_date = {
        item.local_date: item for item in profile.special_sessions
    }
    sessions_by_weekday: dict[int, list[WeeklySessionSpec]] = {}
    for specification in profile.weekly_session_specs:
        sessions_by_weekday.setdefault(
            _WEEKDAY_NUMBER[specification.weekday], []
        ).append(specification)

    intervals: list[TradingInterval] = []
    local_date = local_start
    while local_date <= local_end:
        if local_date in profile.holiday_closures:
            local_date += timedelta(days=1)
            continue
        special = special_by_date.get(local_date)
        if special is not None:
            candidates = (
                (
                    special.local_open_time,
                    special.local_close_time,
                    special.session_label,
                ),
            )
        else:
            candidates = tuple(
                (
                    item.local_open_time,
                    item.local_close_time,
                    item.session_label,
                )
                for item in sessions_by_weekday.get(local_date.weekday(), ())
            )
        for open_time, close_time, label in candidates:
            interval = _local_session_interval(
                local_date=local_date,
                open_time=open_time,
                close_time=close_time,
                session_label=label,
                timezone=timezone,
            )
            if interval.end_at > interval_start and interval.start_at < interval_end:
                intervals.append(interval)
        local_date += timedelta(days=1)
    intervals.sort(key=lambda item: (item.start_at, item.end_at, item.session_label))
    for prior, current in zip(intervals, intervals[1:]):
        if current.start_at < prior.end_at:
            raise CalendarError("SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS")
    return tuple(intervals)


def interval_intersects_halt(
    profile: TradingSessionCalendarProfile,
    *,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    """Return whether any registered halt overlaps a candidate slot interval."""

    return any(
        halt.start_at < end_at and start_at < halt.end_at
        for halt in profile.halt_intervals
    )
