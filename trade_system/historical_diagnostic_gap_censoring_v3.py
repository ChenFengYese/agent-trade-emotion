"""Future-only cadence-gap evidence and per-slot censoring primitives.

This module is intentionally not wired into any v2 receipt, runner, scorer,
plan, archive downloader, or trading path.  It is a synthetic-data-only v3
contract: cadenced source gaps are recorded canonically and a later v3 runner
must account for every five-minute slot without filling or interpolating data.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence


UTC = timezone.utc
GAP_INDEX_RECORD = "historical_diagnostic_cadence_gap_index.v3"
GAP_SEMANTICS = "OBSERVED_CADENCE_ABSENCE_OPEN_INTERVAL_NO_FILL"
SLOT_STATES = {
    "CENSORED_DATA_QUALITY",
    "CENSORED_LABEL_PATH",
    "ABSTAIN_SIGNAL",
    "ELIGIBLE_ROW",
}


class FutureGapCensoringError(ValueError):
    pass


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise FutureGapCensoringError("%s must be a SHA-256 digest" % field)
    return value.lower()


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise FutureGapCensoringError("%s must be a datetime" % field)
    if value.tzinfo is None:
        raise FutureGapCensoringError("%s must be timezone-aware UTC" % field)
    result = value.astimezone(UTC)
    if result.utcoffset() != timedelta(0):
        raise FutureGapCensoringError("%s must be UTC" % field)
    return result


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    if not isinstance(day, date):
        raise FutureGapCensoringError("day must be an ISO date")
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _thresholds(timing_policy: Mapping[str, Any], kind: str) -> tuple[str, int, str, int]:
    if not isinstance(timing_policy, Mapping):
        raise FutureGapCensoringError("timing policy is required")
    if kind == "bookDepth":
        internal_field, edge_field = "max_book_gap_seconds", "max_book_age_seconds"
    elif kind == "metrics":
        internal_field, edge_field = "max_oi_gap_seconds", "max_oi_age_seconds"
    else:
        raise FutureGapCensoringError("only bookDepth and metrics have acquisition cadence gaps")
    internal, edge = timing_policy.get(internal_field), timing_policy.get(edge_field)
    if not isinstance(internal, int) or internal < 1 or not isinstance(edge, int) or edge < 1:
        raise FutureGapCensoringError("timing policy cadence thresholds are invalid")
    return internal_field, internal, edge_field, edge


def _gap(
    *, archive_sha256: str, kind: str, day: date, affected_file: str,
    interval_type: str, left: datetime, right: datetime, threshold_field: str,
    threshold_seconds: int,
) -> Dict[str, Any]:
    delta_ms = int((right - left).total_seconds() * 1000)
    core = {
        "archive_sha256": archive_sha256,
        "kind": kind,
        "date": day.isoformat(),
        "interval_type": interval_type,
        "left_at": left.isoformat(),
        "right_at": right.isoformat(),
        "delta_ms": delta_ms,
        "threshold_field": threshold_field,
        "threshold_value_seconds": threshold_seconds,
        "affected_file": affected_file,
        "semantics": GAP_SEMANTICS,
    }
    return dict(core, gap_id=_canonical_sha256(core))


def build_canonical_gap_index(
    *, archive_sha256: str, kind: str, day: date, affected_file: str,
    observation_times: Sequence[datetime], timing_policy: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bind observed source cadence gaps to one archive digest.

    Internal intervals use the relevant *gap* threshold.  First/last coverage
    intervals use the relevant *age* threshold.  All gap interiors are open:
    a window ending exactly at ``left_at`` or starting exactly at ``right_at``
    does not intersect the gap.
    """
    archive_sha256 = _sha256(archive_sha256, "archive_sha256")
    if not isinstance(affected_file, str) or not affected_file:
        raise FutureGapCensoringError("affected_file is required")
    internal_field, internal_seconds, edge_field, edge_seconds = _thresholds(timing_policy, kind)
    times = [_utc(value, "observation_times") for value in observation_times]
    if not times or times != sorted(times) or len(set(times)) != len(times):
        raise FutureGapCensoringError("observation times must be non-empty, strictly increasing, and unique")
    start, end = _day_bounds(day)
    if any(value < start or value >= end for value in times):
        raise FutureGapCensoringError("observation timestamps must stay inside the declared UTC day")
    gaps = []
    if (times[0] - start).total_seconds() > edge_seconds:
        gaps.append(_gap(archive_sha256=archive_sha256, kind=kind, day=day, affected_file=affected_file, interval_type="START_AGE", left=start, right=times[0], threshold_field=edge_field, threshold_seconds=edge_seconds))
    for left, right in zip(times, times[1:]):
        if (right - left).total_seconds() > internal_seconds:
            gaps.append(_gap(archive_sha256=archive_sha256, kind=kind, day=day, affected_file=affected_file, interval_type="INTERNAL", left=left, right=right, threshold_field=internal_field, threshold_seconds=internal_seconds))
    if (end - times[-1]).total_seconds() > edge_seconds:
        gaps.append(_gap(archive_sha256=archive_sha256, kind=kind, day=day, affected_file=affected_file, interval_type="END_AGE", left=times[-1], right=end, threshold_field=edge_field, threshold_seconds=edge_seconds))
    result = {
        "record_type": GAP_INDEX_RECORD,
        "archive_sha256": archive_sha256,
        "kind": kind,
        "date": day.isoformat(),
        "affected_file": affected_file,
        "observation_count": len(times),
        "gaps": gaps,
        "gap_count": len(gaps),
        "max_gap_ms": max((gap["delta_ms"] for gap in gaps), default=0),
        "semantics": GAP_SEMANTICS,
    }
    return dict(result, canonical_sha256=_canonical_sha256(result))


def validate_official_book_depth_rows(rows: Iterable[Mapping[str, Any]], *, day: date) -> list[datetime]:
    """Validate the official shape without discarding legitimate extra levels.

    Binance book snapshots may contain 0 and additional percentage levels.  A
    snapshot is usable only when it has exactly one -1 and one +1 level; every
    supplied depth must still be finite and strictly positive.
    """
    start, end = _day_bounds(day)
    groups: Dict[datetime, Dict[float, int]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FutureGapCensoringError("bookDepth row must be an object")
        at = _utc(row.get("timestamp"), "bookDepth.timestamp")
        if at < start or at >= end:
            raise FutureGapCensoringError("bookDepth timestamp is outside declared UTC day")
        try:
            percentage, depth = float(row["percentage"]), float(row["depth"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FutureGapCensoringError("bookDepth percentage/depth is invalid") from exc
        if not math.isfinite(percentage) or not math.isfinite(depth) or depth <= 0:
            raise FutureGapCensoringError("bookDepth levels must have finite positive depth")
        counts = groups.setdefault(at, {})
        counts[percentage] = counts.get(percentage, 0) + 1
    if not groups or any(counts.get(-1.0) != 1 or counts.get(1.0) != 1 for counts in groups.values()):
        raise FutureGapCensoringError("every bookDepth snapshot requires exactly one +/-1 level")
    return sorted(groups)


def validate_official_metrics_rows(rows: Iterable[Mapping[str, Any]], *, day: date, symbol: str = "BTCUSD_PERP") -> list[datetime]:
    start, end = _day_bounds(day)
    times = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise FutureGapCensoringError("metrics row must be an object")
        at = _utc(row.get("create_time"), "metrics.create_time")
        try:
            open_interest = float(row["sum_open_interest"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FutureGapCensoringError("metrics sum_open_interest is invalid") from exc
        if at < start or at >= end or row.get("symbol") != symbol or not math.isfinite(open_interest) or open_interest <= 0:
            raise FutureGapCensoringError("metrics date, symbol, or open interest is invalid")
        times.append(at)
    if not times or times != sorted(times) or len(set(times)) != len(times):
        raise FutureGapCensoringError("metrics timestamps must be non-empty and strictly increasing")
    return times


def _gap_times(gap: Mapping[str, Any]) -> tuple[datetime, datetime]:
    try:
        left = datetime.fromisoformat(str(gap["left_at"]))
        right = datetime.fromisoformat(str(gap["right_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise FutureGapCensoringError("gap boundary is invalid") from exc
    left, right = _utc(left, "gap.left_at"), _utc(right, "gap.right_at")
    if left >= right:
        raise FutureGapCensoringError("gap boundaries must be increasing")
    return left, right


def gap_intersects_window(gap: Mapping[str, Any], *, start: datetime, end: datetime) -> bool:
    """Return whether a closed/open required window overlaps a gap interior.

    The same strict comparison implements [start,end] and (start,end] safely:
    endpoint-only contact has no overlap with the open cadence-gap interval.
    """
    start, end = _utc(start, "window.start"), _utc(end, "window.end")
    if start > end:
        raise FutureGapCensoringError("window start must not exceed window end")
    left, right = _gap_times(gap)
    return end > left and start < right


def intersecting_gap_ids(index: Mapping[str, Any], *, kind: str, day: date, start: datetime, end: datetime) -> list[str]:
    if index.get("record_type") != GAP_INDEX_RECORD or index.get("kind") != kind or index.get("date") != day.isoformat():
        raise FutureGapCensoringError("gap index kind/date binding drifted")
    gaps = index.get("gaps")
    if not isinstance(gaps, list):
        raise FutureGapCensoringError("gap index gaps are invalid")
    return [str(gap["gap_id"]) for gap in gaps if isinstance(gap, Mapping) and gap_intersects_window(gap, start=start, end=end)]


@dataclass(frozen=True)
class SlotEvidence:
    slot_at: datetime
    pressure_book_at: datetime | None
    response_book_times: Sequence[datetime]
    oi_start_at: datetime | None
    oi_end_at: datetime | None
    eligible_trade_at: datetime | None
    path_trade_times: Sequence[datetime]
    signal_present: bool
    row_sha256: str | None = None


def _ages_and_gaps_ok(
    *, pressure_start: datetime, pressure_end: datetime, response_end: datetime,
    evidence: SlotEvidence, timing_policy: Mapping[str, Any], book_index: Mapping[str, Any],
    metrics_index: Mapping[str, Any], day: date,
) -> tuple[list[str], list[Dict[str, str]], list[str]]:
    reasons: list[str] = []
    windows: list[Dict[str, str]] = []
    gap_ids: list[str] = []
    book_age = timing_policy.get("max_book_age_seconds")
    book_gap = timing_policy.get("max_book_gap_seconds")
    oi_age = timing_policy.get("max_oi_age_seconds")
    oi_gap = timing_policy.get("max_oi_gap_seconds")
    for field, value in (("max_book_age_seconds", book_age), ("max_book_gap_seconds", book_gap), ("max_oi_age_seconds", oi_age), ("max_oi_gap_seconds", oi_gap)):
        if not isinstance(value, int) or value < 1:
            raise FutureGapCensoringError("%s is invalid" % field)
    required = (("book_pressure", "bookDepth", pressure_start, pressure_end, book_index), ("book_response", "bookDepth", pressure_end, response_end, book_index), ("metrics", "metrics", pressure_start, pressure_end, metrics_index))
    for name, kind, left, right, index in required:
        intersecting = intersecting_gap_ids(index, kind=kind, day=day, start=left, end=right)
        if intersecting:
            reasons.append("%s_intersects_observed_cadence_gap" % name)
            windows.append({"name": name, "start_at": left.isoformat(), "end_at": right.isoformat()})
            gap_ids.extend(intersecting)
    if evidence.pressure_book_at is None:
        reasons.append("pressure_book_age_exceeds_limit")
        windows.append({"name": "book_pressure", "start_at": pressure_start.isoformat(), "end_at": pressure_end.isoformat()})
    else:
        pressure_book_at = _utc(evidence.pressure_book_at, "pressure_book_at")
        if pressure_book_at.date() != day or pressure_book_at > pressure_end or (pressure_end - pressure_book_at).total_seconds() > book_age:
            reasons.append("pressure_book_age_exceeds_limit")
            windows.append({"name": "book_pressure", "start_at": pressure_start.isoformat(), "end_at": pressure_end.isoformat()})
    response_times = [_utc(value, "response_book_times") for value in evidence.response_book_times]
    if len(response_times) < 2:
        reasons.append("response_book_snapshot_count_insufficient")
    else:
        if response_times != sorted(response_times) or len(set(response_times)) != len(response_times) or any(value.date() != day for value in response_times) or response_times[0] <= pressure_end or response_times[-1] > response_end:
            reasons.append("response_book_times_outside_window")
        if (response_times[0] - pressure_end).total_seconds() > book_age:
            reasons.append("response_book_bridge_exceeds_limit")
        if max((right - left).total_seconds() for left, right in zip(response_times, response_times[1:])) > book_gap:
            reasons.append("response_book_internal_gap_exceeds_limit")
        if (response_end - response_times[-1]).total_seconds() > book_age:
            reasons.append("response_book_tail_exceeds_limit")
    if evidence.oi_start_at is None or evidence.oi_end_at is None:
        reasons.append("oi_required_observation_missing")
    else:
        oi_start, oi_end = _utc(evidence.oi_start_at, "oi_start_at"), _utc(evidence.oi_end_at, "oi_end_at")
        if oi_start.date() != day or oi_start > pressure_start or (pressure_start - oi_start).total_seconds() > oi_age:
            reasons.append("oi_start_age_exceeds_limit")
        if oi_end.date() != day or oi_end > pressure_end or (pressure_end - oi_end).total_seconds() > oi_age:
            reasons.append("oi_end_age_exceeds_limit")
        if oi_end <= oi_start or (oi_end - oi_start).total_seconds() > oi_gap:
            reasons.append("oi_gap_exceeds_limit")
    return reasons, windows, sorted(set(gap_ids))


def classify_five_minute_slot(
    *, day: date, evidence: SlotEvidence, timing_policy: Mapping[str, Any],
    book_index: Mapping[str, Any], metrics_index: Mapping[str, Any],
) -> Dict[str, Any]:
    """Classify one fixed slot using only actual timestamps, never fill data."""
    slot_at = _utc(evidence.slot_at, "slot_at")
    start, end = _day_bounds(day)
    if slot_at.date() != day or slot_at < start + timedelta(minutes=5) or slot_at >= end or slot_at.second or slot_at.microsecond or slot_at.minute % 5:
        raise FutureGapCensoringError("slot_at must be a five-minute UTC slot inside its day")
    pressure_window = timing_policy.get("pressure_window_seconds")
    response_window = timing_policy.get("response_window_seconds")
    delay = timing_policy.get("decision_delay_after_response_seconds")
    entry_latency_ms = timing_policy.get("entry_latency_ms")
    entry_wait = timing_policy.get("max_entry_wait_seconds")
    path_horizon = timing_policy.get("path_horizon_seconds")
    path_age = timing_policy.get("max_path_trade_age_seconds")
    path_gap = timing_policy.get("max_path_trade_gap_seconds")
    if any(not isinstance(value, int) or value < 0 for value in (pressure_window, response_window, delay, entry_latency_ms, entry_wait, path_horizon, path_age, path_gap)):
        raise FutureGapCensoringError("slot timing policy is invalid")
    pressure_end = slot_at
    pressure_start = pressure_end - timedelta(seconds=pressure_window)
    response_end = pressure_end + timedelta(seconds=response_window)
    if response_end >= end:
        return {"slot_at": slot_at.isoformat(), "state": "CENSORED_DATA_QUALITY", "reason": ["response_window_crosses_utc_day"], "windows": [{"name": "book_response", "start_at": pressure_end.isoformat(), "end_at": response_end.isoformat()}], "gap_ids": []}
    reasons, windows, gap_ids = _ages_and_gaps_ok(pressure_start=pressure_start, pressure_end=pressure_end, response_end=response_end, evidence=evidence, timing_policy=timing_policy, book_index=book_index, metrics_index=metrics_index, day=day)
    if reasons:
        return {"slot_at": slot_at.isoformat(), "state": "CENSORED_DATA_QUALITY", "reason": sorted(set(reasons)), "windows": windows, "gap_ids": gap_ids}
    eligible_at = response_end + timedelta(seconds=delay, milliseconds=entry_latency_ms)
    horizon = eligible_at + timedelta(seconds=path_horizon)
    trade = evidence.eligible_trade_at
    path = [_utc(value, "path_trade_times") for value in evidence.path_trade_times]
    label_reasons = []
    if horizon >= end:
        label_reasons.append("label_path_crosses_utc_day")
    if trade is None:
        label_reasons.append("entry_trade_missing")
    else:
        trade = _utc(trade, "eligible_trade_at")
        if trade.date() != day or trade < eligible_at or (trade - eligible_at).total_seconds() > entry_wait:
            label_reasons.append("entry_trade_wait_exceeds_limit")
    if not path:
        label_reasons.append("label_path_missing")
    else:
        if path != sorted(path) or len(set(path)) != len(path) or any(value.date() != day for value in path) or (trade is not None and path[0] < trade) or path[-1] > horizon:
            label_reasons.append("label_path_order_or_range_invalid")
        if trade is not None and (path[0] - trade).total_seconds() > path_age:
            label_reasons.append("label_path_head_age_exceeds_limit")
        if max((right - left).total_seconds() for left, right in zip(path, path[1:])) > path_gap:
            label_reasons.append("label_path_internal_gap_exceeds_limit")
        if (horizon - path[-1]).total_seconds() > path_age:
            label_reasons.append("label_path_tail_age_exceeds_limit")
    if label_reasons:
        return {"slot_at": slot_at.isoformat(), "state": "CENSORED_LABEL_PATH", "reason": sorted(set(label_reasons)), "windows": [{"name": "label_path", "start_at": eligible_at.isoformat(), "end_at": horizon.isoformat()}], "gap_ids": []}
    if not evidence.signal_present:
        return {"slot_at": slot_at.isoformat(), "state": "ABSTAIN_SIGNAL"}
    return {"slot_at": slot_at.isoformat(), "state": "ELIGIBLE_ROW", "row_sha256": _sha256(evidence.row_sha256 or "", "row_sha256")}


class FiveMinuteSlotLedger:
    """One terminal state for every evaluated five-minute slot."""

    def __init__(self, *, day: date):
        self.day = day
        self._records: Dict[datetime, Dict[str, Any]] = {}

    def record(self, outcome: Mapping[str, Any]) -> None:
        if not isinstance(outcome, Mapping) or outcome.get("state") not in SLOT_STATES:
            raise FutureGapCensoringError("slot outcome has an invalid terminal state")
        try:
            slot_at = datetime.fromisoformat(str(outcome["slot_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise FutureGapCensoringError("slot outcome is missing slot_at") from exc
        slot_at = _utc(slot_at, "slot_at")
        if slot_at.date() != self.day or slot_at.minute % 5 or slot_at.second or slot_at.microsecond:
            raise FutureGapCensoringError("slot ledger accepts only day-local five-minute slots")
        if slot_at in self._records:
            raise FutureGapCensoringError("slot ledger permits exactly one terminal state per slot")
        state = outcome["state"]
        if state.startswith("CENSORED"):
            if not isinstance(outcome.get("reason"), list) or not outcome["reason"] or not isinstance(outcome.get("windows"), list) or not isinstance(outcome.get("gap_ids"), list):
                raise FutureGapCensoringError("censored slot requires reason, windows, and gap_ids")
        elif state == "ELIGIBLE_ROW":
            _sha256(outcome.get("row_sha256"), "eligible row_sha256")
        self._records[slot_at] = dict(outcome)

    def records(self) -> list[Dict[str, Any]]:
        return [self._records[key] for key in sorted(self._records)]

    def require_complete(self, *, first_slot: datetime, last_slot: datetime) -> list[Dict[str, Any]]:
        """Prove that every five-minute slot in an evaluated range is terminal."""
        first_slot, last_slot = _utc(first_slot, "first_slot"), _utc(last_slot, "last_slot")
        if first_slot.date() != self.day or last_slot.date() != self.day or first_slot > last_slot or any((value.minute % 5, value.second, value.microsecond) != (0, 0, 0) for value in (first_slot, last_slot)):
            raise FutureGapCensoringError("ledger completeness range must be day-local five-minute slots")
        expected = []
        current = first_slot
        while current <= last_slot:
            expected.append(current)
            current += timedelta(minutes=5)
        if set(self._records) != set(expected):
            raise FutureGapCensoringError("slot ledger is missing or has extra terminal states")
        return self.records()
