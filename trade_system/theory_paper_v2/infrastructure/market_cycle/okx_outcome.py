"""Single-call, parameterized OKX public mark outcome adapter."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import re
from typing import Any, Callable, Mapping

from ...application.market_cycle.ports import (
    MarketCyclePortError,
    OutcomeObservation,
    OutcomeRequest,
)
from ..market_data.okx_snapshot import (
    BAR_INTERVAL_MILLISECONDS,
    BASELINE_CANDLE_LIMIT,
    OKX_VENUE_ID,
    OkxSnapshotError,
    parse_okx_closed_candles_response,
    parse_okx_mark_response,
    validate_okx_swap_instrument,
)
from ..market_data.okx_transport import (
    CLOSED_CANDLES_15M_PATH,
    MARK_PRICE_PATH,
    OkxPublicTransport,
    OkxPublicTransportError,
)


OUTCOME_PRICE_FIELD = "MARK_PRICE"
OUTCOME_PARSER_VERSION = "okx-public-mark-outcome-v1"
OUTCOME_PATH_SCHEMA_ID = "agent_trade_emotion_v332_ordered_outcome_path"
OUTCOME_PATH_SCHEMA_VERSION = "1.0.0"
_SAFE_CYCLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class OkxOutcomeError(MarketCyclePortError):
    """The outcome request or captured datum was structurally invalid."""


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OkxOutcomeError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OkxOutcomeError(code) from exc
    if parsed.tzinfo is None:
        raise OkxOutcomeError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _no_request_health(status: str, reason: str) -> tuple[Mapping[str, Any], ...]:
    return (
        {
            "component_id": "OUTCOME_MARK_PRICE",
            "status": status,
            "requested": False,
            "missing_reason": reason,
            "attempt_number": 0,
            "retry_allowed": False,
            "account_data_accessed": False,
            "credential_used": False,
            "executable": False,
        },
    )


def _milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _path_document(
    *,
    request: OutcomeRequest,
    rows: tuple[Mapping[str, Any], ...] = (),
    raw_sha256: str | None = None,
    available_at: str | None = None,
    missing_reason: str | None = None,
) -> Mapping[str, Any]:
    if request.path_start_at is None:
        return {}
    start = _moment(request.path_start_at, code="OUTCOME_PATH_START_TIME_INVALID")
    due = _moment(request.due_at, code="OUTCOME_DUE_TIME_INVALID")
    if start >= due:
        raise OkxOutcomeError("OUTCOME_PATH_WINDOW_INVALID")
    start_ms = _milliseconds(start)
    if start.microsecond % 1000:
        start_ms += 1
    first_open_ms = (
        (start_ms + BAR_INTERVAL_MILLISECONDS - 1)
        // BAR_INTERVAL_MILLISECONDS
    ) * BAR_INTERVAL_MILLISECONDS
    expected = tuple(
        range(
            first_open_ms + BAR_INTERVAL_MILLISECONDS,
            _milliseconds(due) + 1,
            BAR_INTERVAL_MILLISECONDS,
        )
    )
    observed = tuple(
        _milliseconds(
            _moment(row.get("closed_at"), code="OUTCOME_PATH_POINT_TIME_INVALID")
        )
        for row in rows
    )
    unexpected = tuple(value for value in observed if value not in set(expected))
    gaps = tuple(value for value in expected if value not in set(observed))
    if (
        unexpected
        or len(observed) != len(set(observed))
        or tuple(sorted(observed)) != observed
    ):
        rows = ()
        observed = ()
        gaps = expected
        missing_reason = "OUTCOME_PATH_SEQUENCE_INVALID"
    if missing_reason is not None:
        status = "PARTIAL" if rows else "CENSORED"
    elif not expected:
        status = "CENSORED"
        missing_reason = "NO_FULLY_CLOSED_15M_INTERVAL_IN_WINDOW"
    elif observed == expected:
        status = "ORDERED"
    else:
        status = "PARTIAL" if rows else "CENSORED"
        missing_reason = "ORDERED_PATH_COVERAGE_GAP"
    points = []
    for index, row in enumerate(rows):
        point = {
            "sequence_index": index,
            "opened_at": row["opened_at"],
            "closed_at": row["closed_at"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "confirmed_closed": row["confirmed_closed"],
            "available_at": available_at,
            "raw_sha256": raw_sha256,
        }
        points.append(point)
    return {
        "schema_id": OUTCOME_PATH_SCHEMA_ID,
        "schema_version": OUTCOME_PATH_SCHEMA_VERSION,
        "status": status,
        "path_start_at": request.path_start_at,
        "path_end_at": request.due_at,
        "interval": "15m",
        "intrabar_order": "UNRESOLVED_WITHIN_BAR",
        "points": points,
        "coverage": {
            "expected_point_count": len(expected),
            "observed_point_count": len(observed),
            "gap_count": len(gaps),
            "covers_all_closed_intervals": observed == expected and bool(expected),
        },
        "missing_reason": missing_reason,
    }


class OkxMarkOutcome:
    """Implement ``OutcomePort`` for one registered mark-price window."""

    def __init__(
        self,
        *,
        transport: OkxPublicTransport,
        clock: Callable[[], str],
        allow_public_collection: bool = True,
    ) -> None:
        if not callable(clock):
            raise OkxOutcomeError("OUTCOME_CLOCK_INVALID")
        if type(allow_public_collection) is not bool:
            raise OkxOutcomeError("OUTCOME_PUBLIC_COLLECTION_MODE_INVALID")
        self._transport = transport
        self._clock = clock
        self._allow_public_collection = allow_public_collection

    @staticmethod
    def _validate_request(request: OutcomeRequest) -> tuple[datetime, datetime]:
        if not isinstance(request, OutcomeRequest):
            raise OkxOutcomeError("OUTCOME_REQUEST_INVALID")
        if (
            not isinstance(request.cycle_id, str)
            or _SAFE_CYCLE_ID.fullmatch(request.cycle_id) is None
        ):
            raise OkxOutcomeError("OUTCOME_CYCLE_ID_INVALID")
        if (
            request.venue_id != OKX_VENUE_ID
            or request.price_field != OUTCOME_PRICE_FIELD
        ):
            raise OkxOutcomeError("OUTCOME_SCOPE_INVALID")
        try:
            validate_okx_swap_instrument(request.instrument_id)
        except OkxSnapshotError as exc:
            raise OkxOutcomeError("OUTCOME_INSTRUMENT_INVALID") from exc
        if (
            type(request.tolerance_seconds) is not int
            or request.tolerance_seconds < 0
        ):
            raise OkxOutcomeError("OUTCOME_TOLERANCE_INVALID")
        due = _moment(request.due_at, code="OUTCOME_DUE_TIME_INVALID")
        try:
            closes = due + timedelta(seconds=request.tolerance_seconds)
        except OverflowError as exc:
            raise OkxOutcomeError("OUTCOME_TOLERANCE_INVALID") from exc
        if request.path_start_at is not None:
            path_start = _moment(
                request.path_start_at, code="OUTCOME_PATH_START_TIME_INVALID"
            )
            if path_start >= due:
                raise OkxOutcomeError("OUTCOME_PATH_WINDOW_INVALID")
        return due, closes

    def _attach_ordered_path(
        self,
        request: OutcomeRequest,
        observation: OutcomeObservation,
        *,
        due: datetime,
        closes: datetime,
    ) -> OutcomeObservation:
        """Capture the path independently of the endpoint's terminal status."""

        if request.path_start_at is None or observation.terminal_status == "PENDING":
            return observation
        path, raw_refs, health, path_observed_at = self._observe_ordered_path(
            request,
            due=due,
            closes=closes,
            fallback_observed_at=observation.observed_at,
        )
        endpoint_observed = _moment(
            observation.observed_at, code="OUTCOME_OBSERVED_TIME_INVALID"
        )
        path_observed = _moment(
            path_observed_at, code="OUTCOME_PATH_OBSERVED_TIME_INVALID"
        )
        return replace(
            observation,
            observed_at=_time_text(max(endpoint_observed, path_observed)),
            source_health=observation.source_health + health,
            path_observations=path,
            additional_raw_refs=raw_refs,
        )

    def observe(self, request: OutcomeRequest) -> OutcomeObservation:
        due, closes = self._validate_request(request)
        capture_suffix = hashlib.sha256(
            request.due_at.encode("utf-8")
        ).hexdigest()[:16]
        transport_request = {
            "cycle_id": request.cycle_id,
            "capture_id": f"outcome-mark-{capture_suffix}",
            "component_id": "OUTCOME_MARK_PRICE",
            "path": MARK_PRICE_PATH,
            "query": {"instId": request.instrument_id, "instType": "SWAP"},
        }
        observed_text: str | None = None
        try:
            load_sealed = getattr(self._transport, "load_sealed", None)
            response = (
                load_sealed(**transport_request)
                if callable(load_sealed)
                else None
            )
            if response is None:
                observed = _moment(
                    self._clock(), code="OUTCOME_OBSERVED_TIME_INVALID"
                )
                observed_text = _time_text(observed)
                if observed < due:
                    return OutcomeObservation(
                        observed_at=observed_text,
                        effective_at=None,
                        available_at=None,
                        terminal_status="PENDING",
                        value=None,
                        unit=None,
                        missing_reason="OUTCOME_WINDOW_NOT_OPEN",
                        raw_ref=None,
                        source_health=_no_request_health(
                            "PENDING", "OUTCOME_WINDOW_NOT_OPEN"
                        ),
                    )
                if observed > closes:
                    return self._attach_ordered_path(
                        request,
                        OutcomeObservation(
                            observed_at=observed_text,
                            effective_at=None,
                            available_at=None,
                            terminal_status="MISSING",
                            value=None,
                            unit=None,
                            missing_reason="OUTCOME_WINDOW_EXPIRED",
                            raw_ref=None,
                            source_health=_no_request_health(
                                "MISSING", "OUTCOME_WINDOW_EXPIRED"
                            ),
                        ),
                        due=due,
                        closes=closes,
                    )
                if not self._allow_public_collection:
                    return self._attach_ordered_path(
                        request,
                        OutcomeObservation(
                            observed_at=observed_text,
                            effective_at=None,
                            available_at=None,
                            terminal_status="MISSING",
                            value=None,
                            unit=None,
                            missing_reason=(
                                "OUTCOME_PUBLIC_COLLECTION_NOT_AUTHORIZED"
                            ),
                            raw_ref=None,
                            source_health=_no_request_health(
                                "MISSING",
                                "OUTCOME_PUBLIC_COLLECTION_NOT_AUTHORIZED",
                            ),
                        ),
                        due=due,
                        closes=closes,
                    )
                response = self._transport.get_once(**transport_request)
        except OkxPublicTransportError as exc:
            if not exc.coverage_eligible:
                raise
            if exc.failure_at is not None:
                failure_at = exc.failure_at
            elif observed_text is not None:
                failure_at = observed_text
            else:
                failure_at = _time_text(
                    _moment(self._clock(), code="OUTCOME_OBSERVED_TIME_INVALID")
                )
            return self._attach_ordered_path(
                request,
                OutcomeObservation(
                    observed_at=failure_at,
                    effective_at=None,
                    available_at=None,
                    terminal_status="MISSING",
                    value=None,
                    unit=None,
                    missing_reason=exc.failure_code,
                    raw_ref=exc.raw_ref,
                    source_health=(
                        {
                            "component_id": "OUTCOME_MARK_PRICE",
                            "status": "MISSING",
                            "requested": True,
                            "missing_reason": exc.failure_code,
                            "raw_ref": exc.raw_ref,
                            "attempt_number": 1,
                            "retry_allowed": False,
                            "account_data_accessed": False,
                            "credential_used": False,
                            "executable": False,
                        },
                    ),
                ),
                due=due,
                closes=closes,
            )

        response_started = _moment(
            response.request_started_at, code="OUTCOME_CAPTURE_TIME_INVALID"
        )
        response_completed = _moment(
            response.capture_completed_at, code="OUTCOME_CAPTURE_TIME_INVALID"
        )
        if response_started < due or response_completed > closes:
            raw_ref = dict(response.raw_ref)
            return self._attach_ordered_path(
                request,
                OutcomeObservation(
                    observed_at=response.capture_completed_at,
                    effective_at=None,
                    available_at=None,
                    terminal_status="MISSING",
                    value=None,
                    unit=None,
                    missing_reason="OUTCOME_CAPTURE_OUTSIDE_WINDOW",
                    raw_ref=raw_ref,
                    source_health=(
                        {
                            "component_id": "OUTCOME_MARK_PRICE",
                            "status": "MISSING",
                            "requested": True,
                            "requested_at": response.request_started_at,
                            "responded_at": response.response_received_at,
                            "available_at": response.capture_completed_at,
                            "missing_reason": "OUTCOME_CAPTURE_OUTSIDE_WINDOW",
                            "raw_ref": raw_ref,
                            "parser_version": OUTCOME_PARSER_VERSION,
                            "attempt_number": 1,
                            "retry_allowed": False,
                            "account_data_accessed": False,
                            "credential_used": False,
                            "executable": False,
                        },
                    ),
                ),
                due=due,
                closes=closes,
            )

        try:
            mark = parse_okx_mark_response(
                raw=response.body,
                instrument_id=request.instrument_id,
                available_at=response.response_received_at,
            )
        except OkxSnapshotError as exc:
            raise OkxOutcomeError("OUTCOME_MARK_RESPONSE_INVALID") from exc
        raw_ref = dict(response.raw_ref)
        health = (
            {
                "component_id": "OUTCOME_MARK_PRICE",
                "status": mark["status"],
                "requested": True,
                "requested_at": response.request_started_at,
                "responded_at": response.response_received_at,
                "available_at": response.capture_completed_at,
                "raw_ref": raw_ref,
                "parser_version": OUTCOME_PARSER_VERSION,
                "attempt_number": 1,
                "retry_allowed": False,
                "account_data_accessed": False,
                "credential_used": False,
                "executable": False,
            },
        )
        if mark["status"] == "MISSING":
            return self._attach_ordered_path(
                request,
                OutcomeObservation(
                    observed_at=response.capture_completed_at,
                    effective_at=None,
                    available_at=None,
                    terminal_status="MISSING",
                    value=None,
                    unit=None,
                    missing_reason=str(mark["missing_reason"]),
                    raw_ref=raw_ref,
                    source_health=health,
                ),
                due=due,
                closes=closes,
            )

        mark_effective = _moment(
            mark["observed_at"], code="OUTCOME_MARK_EFFECTIVE_TIME_INVALID"
        )
        if abs((mark_effective - due).total_seconds()) > request.tolerance_seconds:
            missing_health = (
                {
                    **health[0],
                    "status": "MISSING",
                    "missing_reason": (
                        "OUTCOME_MARK_EFFECTIVE_TIME_OUTSIDE_WINDOW"
                    ),
                },
            )
            return self._attach_ordered_path(
                request,
                OutcomeObservation(
                    observed_at=response.capture_completed_at,
                    effective_at=None,
                    available_at=None,
                    terminal_status="MISSING",
                    value=None,
                    unit=None,
                    missing_reason=(
                        "OUTCOME_MARK_EFFECTIVE_TIME_OUTSIDE_WINDOW"
                    ),
                    raw_ref=raw_ref,
                    source_health=missing_health,
                ),
                due=due,
                closes=closes,
            )

        base, quote = validate_okx_swap_instrument(request.instrument_id)
        return self._attach_ordered_path(
            request,
            OutcomeObservation(
                observed_at=response.capture_completed_at,
                effective_at=str(mark["observed_at"]),
                available_at=response.capture_completed_at,
                terminal_status="OBSERVED",
                value=str(mark["value"]),
                unit=f"{quote}_PER_{base}",
                missing_reason=None,
                raw_ref=raw_ref,
                source_health=health,
            ),
            due=due,
            closes=closes,
        )

    def _observe_ordered_path(
        self,
        request: OutcomeRequest,
        *,
        due: datetime,
        closes: datetime,
        fallback_observed_at: str,
    ) -> tuple[
        Mapping[str, Any],
        tuple[Mapping[str, Any], ...],
        tuple[Mapping[str, Any], ...],
        str,
    ]:
        capture_suffix = hashlib.sha256(
            request.due_at.encode("utf-8")
        ).hexdigest()[:16]
        boundary_ms = (
            _milliseconds(due) // BAR_INTERVAL_MILLISECONDS
        ) * BAR_INTERVAL_MILLISECONDS
        transport_request = {
            "cycle_id": request.cycle_id,
            "capture_id": f"outcome-closed-candles-15m-{capture_suffix}",
            "component_id": "CLOSED_CANDLES_15M",
            "path": CLOSED_CANDLES_15M_PATH,
            "query": {
                "after": str(boundary_ms),
                "bar": "15m",
                "instId": request.instrument_id,
                "limit": str(BASELINE_CANDLE_LIMIT),
            },
        }
        response = None
        try:
            load_sealed = getattr(self._transport, "load_sealed", None)
            response = (
                load_sealed(**transport_request)
                if callable(load_sealed)
                else None
            )
            if response is None:
                if not self._allow_public_collection:
                    reason = "OUTCOME_PATH_PUBLIC_COLLECTION_NOT_AUTHORIZED"
                    return (
                        _path_document(request=request, missing_reason=reason),
                        (),
                        ({
                            "component_id": "OUTCOME_CLOSED_CANDLES_15M",
                            "status": "MISSING",
                            "requested": False,
                            "missing_reason": reason,
                            "attempt_number": 0,
                            "retry_allowed": False,
                            "account_data_accessed": False,
                            "credential_used": False,
                            "executable": False,
                        },),
                        fallback_observed_at,
                    )
                now_text = self._clock()
                now = _moment(now_text, code="OUTCOME_OBSERVED_TIME_INVALID")
                if now < due or now > closes:
                    reason = (
                        "OUTCOME_PATH_WINDOW_NOT_OPEN"
                        if now < due
                        else "OUTCOME_PATH_WINDOW_EXPIRED"
                    )
                    return (
                        _path_document(request=request, missing_reason=reason),
                        (),
                        ({
                            "component_id": "OUTCOME_CLOSED_CANDLES_15M",
                            "status": "MISSING",
                            "requested": False,
                            "missing_reason": reason,
                            "attempt_number": 0,
                            "retry_allowed": False,
                            "account_data_accessed": False,
                            "credential_used": False,
                            "executable": False,
                        },),
                        now_text,
                    )
                response = self._transport.get_once(**transport_request)
        except OkxPublicTransportError as exc:
            try:
                observed_at = _time_text(
                    _moment(
                        exc.failure_at or fallback_observed_at,
                        code="OUTCOME_PATH_FAILURE_TIME_INVALID",
                    )
                )
            except OkxOutcomeError:
                observed_at = fallback_observed_at
            reason = exc.failure_code
            return (
                _path_document(request=request, missing_reason=reason),
                () if exc.raw_ref is None else (dict(exc.raw_ref),),
                ({
                    "component_id": "OUTCOME_CLOSED_CANDLES_15M",
                    "status": "MISSING",
                    "requested": True,
                    "missing_reason": reason,
                    "raw_ref": exc.raw_ref,
                    "attempt_number": 1,
                    "retry_allowed": False,
                    "account_data_accessed": False,
                    "credential_used": False,
                    "executable": False,
                },),
                observed_at,
            )
        assert response is not None
        raw_ref = dict(response.raw_ref)
        reason = None
        rows: tuple[Mapping[str, Any], ...] = ()
        observed_at = fallback_observed_at
        try:
            started = _moment(
                response.request_started_at, code="OUTCOME_CAPTURE_TIME_INVALID"
            )
            completed = _moment(
                response.capture_completed_at, code="OUTCOME_CAPTURE_TIME_INVALID"
            )
            observed_at = response.capture_completed_at
            if started < due or completed > closes:
                reason = "OUTCOME_PATH_CAPTURE_OUTSIDE_WINDOW"
            else:
                parsed = parse_okx_closed_candles_response(
                    response,
                    cutoff_at=response.response_received_at,
                )
                start = _moment(
                    request.path_start_at, code="OUTCOME_PATH_START_TIME_INVALID"
                )
                rows = tuple(
                    row
                    for row in parsed["rows"]
                    if _moment(
                        row["opened_at"], code="OUTCOME_PATH_POINT_TIME_INVALID"
                    )
                    >= start
                    and _moment(
                        row["closed_at"], code="OUTCOME_PATH_POINT_TIME_INVALID"
                    )
                    <= due
                )
        except (AttributeError, KeyError, OkxOutcomeError, OkxSnapshotError, TypeError):
            reason = "OUTCOME_PATH_RESPONSE_INVALID"
            rows = ()
        document = _path_document(
            request=request,
            rows=rows,
            raw_sha256=raw_ref["sha256"],
            available_at=(
                response.capture_completed_at
                if reason != "OUTCOME_PATH_RESPONSE_INVALID"
                else None
            ),
            missing_reason=reason,
        )
        health = ({
            "component_id": "OUTCOME_CLOSED_CANDLES_15M",
            "status": "OBSERVED" if document["status"] == "ORDERED" else "MISSING",
            "requested": True,
            "requested_at": response.request_started_at,
            "responded_at": response.response_received_at,
            "available_at": response.capture_completed_at,
            "missing_reason": document["missing_reason"],
            "raw_ref": raw_ref,
            "parser_version": OUTCOME_PARSER_VERSION,
            "attempt_number": 1,
            "retry_allowed": False,
            "account_data_accessed": False,
            "credential_used": False,
            "executable": False,
        },)
        return document, (raw_ref,), health, observed_at


OkxMarkOutcomeAdapter = OkxMarkOutcome


__all__ = [
    "OUTCOME_PARSER_VERSION",
    "OUTCOME_PRICE_FIELD",
    "OUTCOME_PATH_SCHEMA_ID",
    "OUTCOME_PATH_SCHEMA_VERSION",
    "OkxMarkOutcome",
    "OkxMarkOutcomeAdapter",
    "OkxOutcomeError",
]
