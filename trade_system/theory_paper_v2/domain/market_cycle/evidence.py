"""Frozen evidence contracts for the four bounded V3.3 UNKNOWN gates.

This module deliberately owns no runner, persistence, market adapter, account
data, or experiment authority.  Its two evaluators consume caller-supplied,
already structured cycle summaries and return bounded readiness decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from ..contracts.canonical import canonical_bytes
from .theory import THEORY_REVISION, V332_THEORY_REVISION
from .contracts import (
    ArtifactRef,
    InputSnapshot,
    MarketCycleContractError,
    _freeze_json,
    _parse_timestamp,
    _require_sha256,
    _thaw_json,
)


class EvidenceContractError(ValueError):
    """A value violates the frozen minimal evidence contract."""


UNKNOWN_INCONCLUSIVE = "UNKNOWN_INCONCLUSIVE"
KNOWN_PASS = "KNOWN_PASS"
KNOWN_FAIL = "KNOWN_FAIL"
KNOWN_SOURCE_INSUFFICIENT = "KNOWN_SOURCE_INSUFFICIENT"
UNOBSERVABLE = "UNOBSERVABLE"
INCREMENT_NOT_DEMONSTRATED = "INCREMENT_NOT_DEMONSTRATED"
TARGET_NOT_MET = "TARGET_NOT_MET"
NEEDS_SEPARATE_AUTHORITY = "NEEDS_SEPARATE_AUTHORITY"

EVIDENCE_STATUSES = frozenset(
    {
        UNKNOWN_INCONCLUSIVE,
        KNOWN_PASS,
        KNOWN_FAIL,
        KNOWN_SOURCE_INSUFFICIENT,
        UNOBSERVABLE,
        INCREMENT_NOT_DEMONSTRATED,
        TARGET_NOT_MET,
        NEEDS_SEPARATE_AUTHORITY,
    }
)

U_SPEED = "U-SPEED"
U_COVERAGE = "U-COVERAGE"
U_PREDICTION = "U-PREDICTION"
U_POSITION = "U-POSITION"

COLD = "COLD"
DELTA = "DELTA"
EVENT_FAST = "EVENT_FAST"
SPEED_ROUTES = (COLD, DELTA, EVENT_FAST)

CORE_4 = (
    "SERVER_TIME",
    "INSTRUMENT",
    "MARK_PRICE",
    "CLOSED_15M_BARS",
)

PREDICTION_ARMS = (
    "V330_CANDIDATE",
    "PRICE_ONLY_DETERMINISTIC",
    "ALWAYS_LONG",
    "ALWAYS_SHORT",
    "WAIT_ONLY",
)
PREDICTION_PHASES = ("CALIBRATION", "UNTOUCHED_CONFIRMATION")

POSITION_POLICY_DIMENSIONS = (
    "PROFIT_MANAGEMENT",
    "DYNAMIC_STOP",
    "POSITION_SCALING",
    "REENTRY",
)
PUBLIC_REFERENCE_ONLY = "PUBLIC_REFERENCE_ONLY"

PREDICTION_ACTIONS = ("LONG", "SHORT", "WAIT")
PREDICTION_OUTCOMES = ("UP", "DOWN", "FLAT")
_ORDINAL_LOSS = {
    ("LONG", "UP"): 0,
    ("LONG", "DOWN"): 2,
    ("LONG", "FLAT"): 1,
    ("SHORT", "UP"): 2,
    ("SHORT", "DOWN"): 0,
    ("SHORT", "FLAT"): 1,
    ("WAIT", "UP"): 1,
    ("WAIT", "DOWN"): 1,
    ("WAIT", "FLAT"): 0,
}

PUBLIC_DIRECT = "PUBLIC_DIRECT"
SOURCE_INSUFFICIENT = "SOURCE_INSUFFICIENT"
SOURCE_UNOBSERVABLE = "UNOBSERVABLE"
SOURCE_PROHIBITED = "PROHIBITED"
SOURCE_CLASSIFICATIONS = frozenset(
    {PUBLIC_DIRECT, SOURCE_INSUFFICIENT, SOURCE_UNOBSERVABLE, SOURCE_PROHIBITED}
)

_PLAN_SEALED = "PLAN_SEALED"
_SEVEN_DAYS_SECONDS = 7 * 24 * 60 * 60
V332_EVIDENCE_POLICY_ID = "v332-market-cycle-evidence-v1"
_POLICY_ID_BY_THEORY_REVISION = {
    THEORY_REVISION: "market-cycle-evidence-v1",
    V332_THEORY_REVISION: V332_EVIDENCE_POLICY_ID,
}

MULTITIMEFRAME_CALCULATION_TOOL_ID = "CLOSED_15M_MULTITIMEFRAME_CONTEXT"
MULTITIMEFRAME_CALCULATION_ALGORITHM_VERSION = "1.0.0"
MULTITIMEFRAME_REQUIRED_15M_BARS = 96
_MULTITIMEFRAME_FORMULAS = (
    "aggregate.open=first(source.open)",
    "aggregate.high=max(source.high)",
    "aggregate.low=min(source.low)",
    "aggregate.close=last(source.close)",
    "statistics.absolute_change=last_close-first_open",
    "statistics.change_ratio=(last_close-first_open)/first_open",
    "statistics.high_low_range=max(high)-min(low)",
    "statistics.close_mean=sum(close)/96",
)


@dataclass(frozen=True, slots=True)
class DeterministicCalculationResult:
    """Non-authoritative calculation context derived from one sealed snapshot."""

    input_snapshot_ref: ArtifactRef
    source_raw_sha256: str
    source_bars_sha256: str
    source_bar_count: int
    status: str
    typed_unknown: str | None
    result: Mapping[str, Any]
    tool_id: str = MULTITIMEFRAME_CALCULATION_TOOL_ID
    algorithm_version: str = MULTITIMEFRAME_CALCULATION_ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.input_snapshot_ref, ArtifactRef)
            or self.input_snapshot_ref.artifact_type != "InputSnapshot"
        ):
            raise MarketCycleContractError(
                "calculation input_snapshot_ref must identify InputSnapshot"
            )
        _require_sha256(
            self.source_raw_sha256,
            field_name="calculation.source_raw_sha256",
        )
        _require_sha256(
            self.source_bars_sha256,
            field_name="calculation.source_bars_sha256",
        )
        if type(self.source_bar_count) is not int or self.source_bar_count < 0:
            raise MarketCycleContractError(
                "calculation.source_bar_count must be a nonnegative integer"
            )
        if self.status not in {"AVAILABLE", "UNKNOWN"}:
            raise MarketCycleContractError(
                "calculation.status must be AVAILABLE or UNKNOWN"
            )
        if self.tool_id != MULTITIMEFRAME_CALCULATION_TOOL_ID:
            raise MarketCycleContractError("calculation tool_id is not frozen")
        if self.algorithm_version != MULTITIMEFRAME_CALCULATION_ALGORITHM_VERSION:
            raise MarketCycleContractError(
                "calculation algorithm_version is not frozen"
            )
        if self.status == "AVAILABLE":
            if self.typed_unknown is not None:
                raise MarketCycleContractError(
                    "AVAILABLE calculation cannot contain typed_unknown"
                )
        elif not isinstance(self.typed_unknown, str) or not self.typed_unknown:
            raise MarketCycleContractError(
                "UNKNOWN calculation requires typed_unknown"
            )
        frozen = _freeze_json(self.result, path="calculation.result")
        if not isinstance(frozen, Mapping):
            raise MarketCycleContractError("calculation.result must be an object")
        if self.status == "UNKNOWN" and frozen:
            raise MarketCycleContractError(
                "UNKNOWN calculation must not manufacture result values"
            )
        object.__setattr__(self, "result", frozen)

    def to_dict(self) -> dict[str, object]:
        return {
            "authority": "NON_AUTHORITATIVE_CALCULATION_ONLY",
            "tool_id": self.tool_id,
            "algorithm_version": self.algorithm_version,
            "status": self.status,
            "typed_unknown": self.typed_unknown,
            "input_snapshot_ref": self.input_snapshot_ref.to_dict(),
            "source_raw_sha256": self.source_raw_sha256,
            "source_bars_sha256": self.source_bars_sha256,
            "source_bar_count": self.source_bar_count,
            "required_source_bar_count": MULTITIMEFRAME_REQUIRED_15M_BARS,
            "aggregation_basis": "CONTIGUOUS_96_BAR_WINDOW_NOT_CALENDAR_BUCKET",
            "decimal_context": {
                "precision": 50,
                "rounding": "ROUND_HALF_EVEN",
            },
            "formulas": list(_MULTITIMEFRAME_FORMULAS),
            "result": _thaw_json(self.result),
        }


def _calculation_unknown(
    snapshot_ref: ArtifactRef,
    *,
    source_raw_sha256: str,
    source_bars_sha256: str,
    source_bar_count: int,
    code: str,
) -> DeterministicCalculationResult:
    return DeterministicCalculationResult(
        input_snapshot_ref=snapshot_ref,
        source_raw_sha256=source_raw_sha256,
        source_bars_sha256=source_bars_sha256,
        source_bar_count=source_bar_count,
        status="UNKNOWN",
        typed_unknown=code,
        result={},
    )


def _decimal_value(value: object) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError("decimal source value is unavailable")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("decimal source value is invalid") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("decimal source value must be finite and positive")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _aggregate_bar(
    rows: Sequence[tuple[str, str, Decimal, Decimal, Decimal, Decimal]],
) -> dict[str, object]:
    return {
        "opened_at": rows[0][0],
        "closed_at": rows[-1][1],
        "open": _decimal_text(rows[0][2]),
        "high": _decimal_text(max(row[3] for row in rows)),
        "low": _decimal_text(min(row[4] for row in rows)),
        "close": _decimal_text(rows[-1][5]),
        "source_bar_count": len(rows),
    }


def calculate_multitimeframe_context(
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
) -> DeterministicCalculationResult:
    """Aggregate 96 closed 15m bars without choosing or scoring an action.

    Auxiliary insufficiency and schema variation produce a typed ``UNKNOWN``
    result.  Snapshot/ref identity mismatch remains a hard binding error.
    """

    if not isinstance(snapshot, InputSnapshot):
        raise MarketCycleContractError("calculation snapshot must be InputSnapshot")
    if (
        snapshot_ref.artifact_type != "InputSnapshot"
        or snapshot_ref.artifact_id != snapshot.snapshot_id
    ):
        raise MarketCycleContractError(
            "calculation snapshot ref does not identify the supplied InputSnapshot"
        )
    observation = snapshot.core_observations.get("closed_15m_bars")
    if not isinstance(observation, Mapping):
        raise MarketCycleContractError("sealed snapshot lacks closed_15m_bars")
    source_raw_sha256 = _require_sha256(
        observation.get("raw_sha256"),
        field_name="closed_15m_bars.raw_sha256",
    )
    supplied = observation.get("value")
    source_bars_sha256 = hashlib.sha256(canonical_bytes(supplied)).hexdigest()
    source_bar_count = len(supplied) if isinstance(supplied, (list, tuple)) else 0
    if source_bar_count != MULTITIMEFRAME_REQUIRED_15M_BARS:
        return _calculation_unknown(
            snapshot_ref,
            source_raw_sha256=source_raw_sha256,
            source_bars_sha256=source_bars_sha256,
            source_bar_count=source_bar_count,
            code="INSUFFICIENT_96_CLOSED_15M_BARS",
        )

    parsed: list[tuple[str, str, Decimal, Decimal, Decimal, Decimal]] = []
    try:
        previous_closed: datetime | None = None
        cutoff = _parse_timestamp(
            snapshot.source_cutoff_at, field_name="source_cutoff_at"
        )
        for index, row in enumerate(supplied):
            if not isinstance(row, Mapping) or row.get("confirmed_closed") is not True:
                raise ValueError("bar is not confirmed closed")
            opened_text = row.get("opened_at")
            closed_text = row.get("closed_at")
            opened = _parse_timestamp(
                opened_text, field_name=f"closed_15m_bars[{index}].opened_at"
            )
            closed = _parse_timestamp(
                closed_text, field_name=f"closed_15m_bars[{index}].closed_at"
            )
            if (
                closed - opened != timedelta(minutes=15)
                or (previous_closed is not None and opened != previous_closed)
                or closed > cutoff
            ):
                raise ValueError("bars are not one contiguous closed 15m window")
            opened_value = _decimal_value(row.get("open"))
            high = _decimal_value(row.get("high"))
            low = _decimal_value(row.get("low"))
            close = _decimal_value(row.get("close"))
            if high < max(opened_value, close) or low > min(opened_value, close):
                raise ValueError("bar OHLC geometry is invalid")
            parsed.append(
                (
                    str(opened_text),
                    str(closed_text),
                    opened_value,
                    high,
                    low,
                    close,
                )
            )
            previous_closed = closed
    except (MarketCycleContractError, ValueError, TypeError):
        return _calculation_unknown(
            snapshot_ref,
            source_raw_sha256=source_raw_sha256,
            source_bars_sha256=source_bars_sha256,
            source_bar_count=source_bar_count,
            code="CLOSED_15M_BARS_SCHEMA_UNAVAILABLE",
        )

    frames: dict[str, object] = {}
    for label, group_size in (("1D", 96), ("4H", 16), ("1H", 4), ("15m", 1)):
        bars = [
            _aggregate_bar(parsed[start : start + group_size])
            for start in range(0, len(parsed), group_size)
        ]
        frames[label] = {
            "source_bars_per_bar": group_size,
            "bar_count": len(bars),
            "bars": bars,
        }
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        first_open = parsed[0][2]
        last_close = parsed[-1][5]
        absolute_change = last_close - first_open
        statistics = {
            "first_open": _decimal_text(first_open),
            "last_close": _decimal_text(last_close),
            "absolute_change": _decimal_text(absolute_change),
            "change_ratio": _decimal_text(absolute_change / first_open),
            "high_low_range": _decimal_text(
                max(row[3] for row in parsed) - min(row[4] for row in parsed)
            ),
            "close_mean": _decimal_text(
                sum((row[5] for row in parsed), Decimal("0"))
                / Decimal(MULTITIMEFRAME_REQUIRED_15M_BARS)
            ),
        }
    return DeterministicCalculationResult(
        input_snapshot_ref=snapshot_ref,
        source_raw_sha256=source_raw_sha256,
        source_bars_sha256=source_bars_sha256,
        source_bar_count=source_bar_count,
        status="AVAILABLE",
        typed_unknown=None,
        result={"timeframes": frames, "statistics": statistics},
    )


def _nonempty(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EvidenceContractError(f"{field_name} must be a non-empty trimmed string")
    return value


def _optional_nonempty(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name=field_name)


def _integer(value: object, *, field_name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EvidenceContractError(f"{field_name} must be an integer >= {minimum}")
    return value


def _optional_integer(
    value: object, *, field_name: str, minimum: int = 0
) -> int | None:
    if value is None:
        return None
    return _integer(value, field_name=field_name, minimum=minimum)


def _optional_signed_integer(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise EvidenceContractError(f"{field_name} must be an integer or None")
    return value


def _optional_boolean(value: object, *, field_name: str) -> bool | None:
    if value is not None and type(value) is not bool:
        raise EvidenceContractError(f"{field_name} must be bool or None")
    return value


def _timestamp(value: object, *, field_name: str) -> datetime:
    text = _nonempty(value, field_name=field_name)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceContractError(f"{field_name} must be ISO-8601") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise EvidenceContractError(f"{field_name} must include an explicit UTC offset")
    return moment


def _status(value: object) -> str:
    if value not in EVIDENCE_STATUSES:
        raise EvidenceContractError("unsupported evidence status")
    return str(value)


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    """The immutable minimum policy shared by all four evidence gates."""

    policy_id: str = "market-cycle-evidence-v1"
    theory_revision: str = THEORY_REVISION
    cold_budget_seconds: int = 900
    delta_budget_seconds: int = 120
    event_fast_budget_seconds: None = None
    coverage_core_components: tuple[str, ...] = CORE_4
    coverage_required_window_count: int = 2
    coverage_window_seconds: int = _SEVEN_DAYS_SECONDS
    prediction_arms: tuple[str, ...] = PREDICTION_ARMS
    prediction_phases: tuple[str, ...] = PREDICTION_PHASES
    position_dimensions: tuple[str, ...] = POSITION_POLICY_DIMENSIONS
    position_phases: tuple[str, ...] = PREDICTION_PHASES
    position_reference_authority: str = PUBLIC_REFERENCE_ONLY
    position_execution_status: str = NEEDS_SEPARATE_AUTHORITY

    def __post_init__(self) -> None:
        _nonempty(self.policy_id, field_name="policy_id")
        expected_policy_id = _POLICY_ID_BY_THEORY_REVISION.get(
            self.theory_revision
        )
        if expected_policy_id is None or self.policy_id != expected_policy_id:
            raise EvidenceContractError(
                "EvidencePolicy identity must bind one supported frozen theory revision"
            )
        if self.cold_budget_seconds != 900 or self.delta_budget_seconds != 120:
            raise EvidenceContractError("COLD/DELTA budgets are frozen at 900/120 seconds")
        if self.event_fast_budget_seconds is not None:
            raise EvidenceContractError("EVENT_FAST has no frozen speed budget")
        if self.coverage_core_components != CORE_4:
            raise EvidenceContractError("U-COVERAGE must use the exact CORE_4")
        if self.coverage_required_window_count != 2:
            raise EvidenceContractError("U-COVERAGE requires exactly two windows")
        if self.coverage_window_seconds != _SEVEN_DAYS_SECONDS:
            raise EvidenceContractError("each U-COVERAGE window must be seven days")
        if self.prediction_arms != PREDICTION_ARMS:
            raise EvidenceContractError("U-PREDICTION comparison arms are frozen")
        if self.prediction_phases != PREDICTION_PHASES:
            raise EvidenceContractError(
                "U-PREDICTION must proceed calibration then untouched confirmation"
            )
        if self.position_dimensions != POSITION_POLICY_DIMENSIONS:
            raise EvidenceContractError("U-POSITION must isolate exactly four dimensions")
        if self.position_phases != PREDICTION_PHASES:
            raise EvidenceContractError(
                "U-POSITION must proceed calibration then untouched confirmation"
            )
        if self.position_reference_authority != PUBLIC_REFERENCE_ONLY:
            raise EvidenceContractError("position evidence is public reference only")
        if self.position_execution_status != NEEDS_SEPARATE_AUTHORITY:
            raise EvidenceContractError("execution effects need separate authority")

    def speed_budget(self, analysis_profile: str) -> int | None:
        if analysis_profile == COLD:
            return self.cold_budget_seconds
        if analysis_profile == DELTA:
            return self.delta_budget_seconds
        if analysis_profile == EVENT_FAST:
            return None
        raise EvidenceContractError("unsupported speed analysis_profile")

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "theory_revision": self.theory_revision,
            "speed_budgets_seconds": {
                COLD: self.cold_budget_seconds,
                DELTA: self.delta_budget_seconds,
                EVENT_FAST: None,
            },
            "coverage_core_components": list(self.coverage_core_components),
            "coverage_required_window_count": self.coverage_required_window_count,
            "coverage_window_seconds": self.coverage_window_seconds,
            "prediction_arms": list(self.prediction_arms),
            "prediction_phases": list(self.prediction_phases),
            "position_dimensions": list(self.position_dimensions),
            "position_phases": list(self.position_phases),
            "position_reference_authority": self.position_reference_authority,
            "position_execution_status": self.position_execution_status,
        }


@dataclass(frozen=True, slots=True)
class SpeedCycleSummary:
    """One preregistered attempt; failed attempts are summaries, not omissions."""

    cycle_id: str
    cohort_id: str
    analysis_profile: str
    attempt_ordinal: int
    expected_attempts: int
    elapsed_seconds: int | None
    terminal_status: str | None
    failure_stage: str | None
    data_profile: str | None
    environment_identity: str | None
    theory_revision: str | None
    source_done_elapsed_seconds: int | None = None
    deterministic_preparation_done_elapsed_seconds: int | None = None
    agent_done_elapsed_seconds: int | None = None
    position_and_selection_done_elapsed_seconds: int | None = None
    request_count: int | None = None
    agent_round_trips: int | None = None
    packet_size_bytes: int | None = None

    def __post_init__(self) -> None:
        _nonempty(self.cycle_id, field_name="cycle_id")
        _nonempty(self.cohort_id, field_name="cohort_id")
        if self.analysis_profile not in SPEED_ROUTES:
            raise EvidenceContractError(
                "unsupported SpeedCycleSummary analysis_profile"
            )
        _integer(self.attempt_ordinal, field_name="attempt_ordinal", minimum=1)
        _integer(self.expected_attempts, field_name="expected_attempts", minimum=1)
        if self.attempt_ordinal > self.expected_attempts:
            raise EvidenceContractError("attempt_ordinal exceeds expected_attempts")
        _optional_integer(self.elapsed_seconds, field_name="elapsed_seconds")
        _optional_nonempty(self.terminal_status, field_name="terminal_status")
        _optional_nonempty(self.failure_stage, field_name="failure_stage")
        _optional_nonempty(self.data_profile, field_name="data_profile")
        _optional_nonempty(
            self.environment_identity, field_name="environment_identity"
        )
        _optional_nonempty(self.theory_revision, field_name="theory_revision")
        stage_endpoints = (
            self.source_done_elapsed_seconds,
            self.deterministic_preparation_done_elapsed_seconds,
            self.agent_done_elapsed_seconds,
            self.position_and_selection_done_elapsed_seconds,
        )
        for name in (
            "source_done_elapsed_seconds",
            "deterministic_preparation_done_elapsed_seconds",
            "agent_done_elapsed_seconds",
            "position_and_selection_done_elapsed_seconds",
            "request_count",
            "agent_round_trips",
            "packet_size_bytes",
        ):
            _optional_integer(getattr(self, name), field_name=name)
        if all(value is not None for value in stage_endpoints):
            exact_endpoints = tuple(int(value) for value in stage_endpoints)
            if exact_endpoints != tuple(sorted(exact_endpoints)):
                raise EvidenceContractError("speed stage endpoints must be monotonic")
            if (
                self.elapsed_seconds is not None
                and exact_endpoints[-1] > self.elapsed_seconds
            ):
                raise EvidenceContractError("stage endpoint exceeds total elapsed_seconds")
        if self.terminal_status == _PLAN_SEALED and self.failure_stage is not None:
            raise EvidenceContractError("a sealed plan cannot also have failure_stage")


@dataclass(frozen=True, slots=True)
class SpeedReadiness:
    gate: str
    analysis_profile: str
    status: str
    denominator: int
    sealed_count: int
    failed_count: int
    p50_seconds: int | None
    p95_seconds: int | None
    max_seconds: int | None
    budget_seconds: int | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.gate != U_SPEED or self.analysis_profile not in SPEED_ROUTES:
            raise EvidenceContractError("invalid SpeedReadiness identity")
        _status(self.status)
        for name in ("denominator", "sealed_count", "failed_count"):
            _integer(getattr(self, name), field_name=name)
        for name in ("p50_seconds", "p95_seconds", "max_seconds", "budget_seconds"):
            _optional_integer(getattr(self, name), field_name=name)
        if self.sealed_count + self.failed_count > self.denominator:
            raise EvidenceContractError("speed counts exceed denominator")
        reasons = tuple(self.reasons)
        if not all(isinstance(reason, str) and reason for reason in reasons):
            raise EvidenceContractError("SpeedReadiness reasons must be non-empty strings")
        object.__setattr__(self, "reasons", reasons)


def _nearest_rank(values: Sequence[int], percentile: int) -> int:
    if not values:
        raise EvidenceContractError("cannot rank an empty speed cohort")
    ordered = sorted(values)
    rank = (percentile * len(ordered) + 99) // 100
    return ordered[max(0, rank - 1)]


def assess_speed_readiness(
    policy: EvidencePolicy,
    summaries: Iterable[SpeedCycleSummary],
    *,
    analysis_profile: str,
) -> SpeedReadiness:
    """Evaluate one analysis-profile cohort without dropping failed attempts."""

    if not isinstance(policy, EvidencePolicy):
        raise EvidenceContractError("policy must be EvidencePolicy")
    budget = policy.speed_budget(analysis_profile)
    supplied = tuple(summaries)
    if not all(isinstance(item, SpeedCycleSummary) for item in supplied):
        raise EvidenceContractError("speed summaries must be SpeedCycleSummary values")
    cycle_ids = tuple(item.cycle_id for item in supplied)
    if len(cycle_ids) != len(set(cycle_ids)):
        raise EvidenceContractError("speed cycle_id values must be unique")
    cohort = tuple(
        item for item in supplied if item.analysis_profile == analysis_profile
    )
    denominator = len(cohort)
    elapsed = tuple(
        item.elapsed_seconds for item in cohort if item.elapsed_seconds is not None
    )
    p50 = _nearest_rank(elapsed, 50) if len(elapsed) == denominator and elapsed else None
    p95 = _nearest_rank(elapsed, 95) if len(elapsed) == denominator and elapsed else None
    maximum = max(elapsed) if len(elapsed) == denominator and elapsed else None
    sealed = sum(item.terminal_status == _PLAN_SEALED for item in cohort)
    failed = sum(
        item.terminal_status is not None and item.terminal_status != _PLAN_SEALED
        for item in cohort
    )
    reasons: list[str] = []
    if not cohort:
        reasons.append("NO_STRUCTURED_ATTEMPTS")
    else:
        expected_values = {item.expected_attempts for item in cohort}
        expected = next(iter(expected_values)) if len(expected_values) == 1 else None
        if expected is None:
            reasons.append("EXPECTED_ATTEMPTS_DRIFT")
        elif len(cohort) != expected or {
            item.attempt_ordinal for item in cohort
        } != set(range(1, expected + 1)):
            reasons.append("PREREGISTERED_ATTEMPTS_INCOMPLETE")
        if len({item.cohort_id for item in cohort}) != 1:
            reasons.append("MIXED_COHORTS")
        if any(
            item.data_profile is None
            or item.environment_identity is None
            or item.theory_revision is None
            for item in cohort
        ):
            reasons.append("COHORT_IDENTITY_MISSING")
        elif (
            len({item.data_profile for item in cohort}) != 1
            or len({item.environment_identity for item in cohort}) != 1
            or {item.theory_revision for item in cohort} != {policy.theory_revision}
        ):
            reasons.append("COHORT_IDENTITY_DRIFT")
        if len(elapsed) != denominator:
            reasons.append("ELAPSED_TIME_MISSING")
        if any(item.terminal_status is None for item in cohort):
            reasons.append("TERMINAL_STATUS_MISSING")
        if any(
            any(
                value is None
                for value in (
                    item.source_done_elapsed_seconds,
                    item.deterministic_preparation_done_elapsed_seconds,
                    item.agent_done_elapsed_seconds,
                    item.position_and_selection_done_elapsed_seconds,
                    item.request_count,
                    item.agent_round_trips,
                    item.packet_size_bytes,
                )
            )
            for item in cohort
        ):
            reasons.append("STAGE_TIMING_OR_SCALE_MISSING")
        if any(
            item.terminal_status not in {None, _PLAN_SEALED}
            and item.failure_stage is None
            for item in cohort
        ):
            reasons.append("FAILURE_STAGE_MISSING")

    if analysis_profile == EVENT_FAST:
        reasons.append("EVENT_FAST_BUDGET_NOT_FROZEN")
    if reasons:
        status = UNKNOWN_INCONCLUSIVE
    elif p95 is None or budget is None:
        status = UNKNOWN_INCONCLUSIVE
    elif failed or p95 > budget:
        status = TARGET_NOT_MET
    else:
        status = KNOWN_PASS
    return SpeedReadiness(
        gate=U_SPEED,
        analysis_profile=analysis_profile,
        status=status,
        denominator=denominator,
        sealed_count=sealed,
        failed_count=failed,
        p50_seconds=p50,
        p95_seconds=p95,
        max_seconds=maximum,
        budget_seconds=budget,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class CoverageComponentSummary:
    """One component's explicit acquisition/admission result for one cycle."""

    component_id: str
    source_classification: str | None
    scheduled: bool | None
    requested: bool | None
    responded: bool | None
    raw_saved: bool | None
    parsed: bool | None
    admitted: bool | None
    fresh: bool | None
    replayable: bool | None
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.component_id, field_name="component_id")
        if (
            self.source_classification is not None
            and self.source_classification not in SOURCE_CLASSIFICATIONS
        ):
            raise EvidenceContractError("unsupported source_classification")
        for name in (
            "scheduled",
            "requested",
            "responded",
            "raw_saved",
            "parsed",
            "admitted",
            "fresh",
            "replayable",
        ):
            _optional_boolean(getattr(self, name), field_name=name)
        _optional_nonempty(self.missing_reason, field_name="missing_reason")
        if self.admitted is True and any(
            value is not True
            for value in (
                self.scheduled,
                self.requested,
                self.responded,
                self.raw_saved,
                self.parsed,
            )
        ):
            raise EvidenceContractError("admitted requires every preceding stage")
        if self.fresh is True and self.admitted is not True:
            raise EvidenceContractError("fresh requires admitted")
        if self.replayable is True and self.raw_saved is not True:
            raise EvidenceContractError("replayable requires raw_saved")


@dataclass(frozen=True, slots=True)
class CoverageCycleSummary:
    """One scheduled opportunity inside one frozen coverage window."""

    cycle_id: str
    window_id: str
    window_start_at: str
    window_end_at: str
    cycle_ordinal: int
    expected_cycles: int
    coverage_scope_id: str | None
    venue_id: str | None
    instrument_id: str | None
    analysis_profile: str | None
    data_profile: str | None
    theory_revision: str | None
    terminal: bool | None
    failure_stage: str | None
    pit_violation: bool | None
    instrument_identity_valid: bool | None
    closed_bar_valid: bool | None
    components: tuple[CoverageComponentSummary, ...]

    def __post_init__(self) -> None:
        _nonempty(self.cycle_id, field_name="cycle_id")
        _nonempty(self.window_id, field_name="window_id")
        start = _timestamp(self.window_start_at, field_name="window_start_at")
        end = _timestamp(self.window_end_at, field_name="window_end_at")
        if end <= start:
            raise EvidenceContractError("coverage window end must follow start")
        _integer(self.cycle_ordinal, field_name="cycle_ordinal", minimum=1)
        _integer(self.expected_cycles, field_name="expected_cycles", minimum=1)
        if self.cycle_ordinal > self.expected_cycles:
            raise EvidenceContractError("cycle_ordinal exceeds expected_cycles")
        for name in (
            "coverage_scope_id",
            "venue_id",
            "instrument_id",
            "analysis_profile",
            "data_profile",
            "theory_revision",
            "failure_stage",
        ):
            _optional_nonempty(getattr(self, name), field_name=name)
        for name in (
            "terminal",
            "pit_violation",
            "instrument_identity_valid",
            "closed_bar_valid",
        ):
            _optional_boolean(getattr(self, name), field_name=name)
        components = tuple(self.components)
        if not all(isinstance(item, CoverageComponentSummary) for item in components):
            raise EvidenceContractError(
                "components must contain CoverageComponentSummary values"
            )
        component_ids = tuple(item.component_id for item in components)
        if len(component_ids) != len(set(component_ids)):
            raise EvidenceContractError("component_id values must be unique per cycle")
        object.__setattr__(self, "components", components)


@dataclass(frozen=True, slots=True)
class CoverageReadiness:
    gate: str
    status: str
    denominator: int
    terminal_count: int
    usable_core4_count: int
    failed_cycle_count: int
    window_count: int
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.gate != U_COVERAGE:
            raise EvidenceContractError("invalid CoverageReadiness gate")
        _status(self.status)
        for name in (
            "denominator",
            "terminal_count",
            "usable_core4_count",
            "failed_cycle_count",
            "window_count",
        ):
            _integer(getattr(self, name), field_name=name)
        if self.usable_core4_count + self.failed_cycle_count > self.denominator:
            raise EvidenceContractError("coverage counts exceed denominator")
        reasons = tuple(self.reasons)
        if not all(isinstance(reason, str) and reason for reason in reasons):
            raise EvidenceContractError("CoverageReadiness reasons must be strings")
        object.__setattr__(self, "reasons", reasons)


def assess_coverage_readiness(
    policy: EvidencePolicy,
    summaries: Iterable[CoverageCycleSummary],
) -> CoverageReadiness:
    """Evaluate CORE_4 readiness over two complete, disjoint seven-day windows."""

    if not isinstance(policy, EvidencePolicy):
        raise EvidenceContractError("policy must be EvidencePolicy")
    cycles = tuple(summaries)
    if not all(isinstance(item, CoverageCycleSummary) for item in cycles):
        raise EvidenceContractError(
            "coverage summaries must be CoverageCycleSummary values"
        )
    cycle_ids = tuple(item.cycle_id for item in cycles)
    if len(cycle_ids) != len(set(cycle_ids)):
        raise EvidenceContractError("coverage cycle_id values must be unique")
    denominator = len(cycles)
    terminal_count = sum(item.terminal is True for item in cycles)
    reasons: list[str] = []
    windows: dict[str, list[CoverageCycleSummary]] = {}
    for item in cycles:
        windows.setdefault(item.window_id, []).append(item)
    if not cycles:
        reasons.append("NO_STRUCTURED_COVERAGE_CYCLES")
    if len(windows) != policy.coverage_required_window_count:
        reasons.append("TWO_COVERAGE_WINDOWS_REQUIRED")

    intervals: list[tuple[datetime, datetime]] = []
    for window_id, group in sorted(windows.items()):
        starts = {item.window_start_at for item in group}
        ends = {item.window_end_at for item in group}
        expected_values = {item.expected_cycles for item in group}
        if len(starts) != 1 or len(ends) != 1 or len(expected_values) != 1:
            reasons.append(f"WINDOW_CONTRACT_DRIFT:{window_id}")
            continue
        start = _timestamp(next(iter(starts)), field_name="window_start_at")
        end = _timestamp(next(iter(ends)), field_name="window_end_at")
        if end - start != timedelta(seconds=policy.coverage_window_seconds):
            reasons.append(f"WINDOW_NOT_SEVEN_DAYS:{window_id}")
        intervals.append((start, end))
        expected = next(iter(expected_values))
        if len(group) != expected or {item.cycle_ordinal for item in group} != set(
            range(1, expected + 1)
        ):
            reasons.append(f"SCHEDULED_CYCLES_INCOMPLETE:{window_id}")
    intervals.sort(key=lambda item: item[0])
    if len(intervals) == policy.coverage_required_window_count and any(
        left[1] > right[0] for left, right in zip(intervals, intervals[1:])
    ):
        reasons.append("COVERAGE_WINDOWS_OVERLAP")

    identity_fields = (
        "coverage_scope_id",
        "venue_id",
        "instrument_id",
        "analysis_profile",
        "data_profile",
        "theory_revision",
    )
    if any(getattr(item, name) is None for item in cycles for name in identity_fields):
        reasons.append("COVERAGE_SCOPE_IDENTITY_MISSING")
    elif cycles and (
        any(len({getattr(item, name) for item in cycles}) != 1 for name in identity_fields[:-1])
        or {item.theory_revision for item in cycles} != {policy.theory_revision}
    ):
        reasons.append("COVERAGE_SCOPE_IDENTITY_DRIFT")
    if any(item.terminal is not True for item in cycles):
        reasons.append("NONTERMINAL_SCHEDULED_CYCLE")

    explicit_unobservable = False
    explicit_source_insufficient = False
    usable = 0
    explicit_failed = 0
    for cycle in cycles:
        components = {item.component_id: item for item in cycle.components}
        missing_core = tuple(
            component for component in policy.coverage_core_components if component not in components
        )
        if missing_core:
            reasons.append(f"CORE_COMPONENT_SUMMARY_MISSING:{cycle.cycle_id}")
            continue
        cycle_unknown = False
        cycle_failed = False
        for component_id in policy.coverage_core_components:
            component = components[component_id]
            if component.source_classification in {
                SOURCE_UNOBSERVABLE,
                SOURCE_PROHIBITED,
            }:
                explicit_unobservable = True
                cycle_failed = True
                continue
            if component.source_classification == SOURCE_INSUFFICIENT:
                explicit_source_insufficient = True
                cycle_failed = True
                continue
            if component.source_classification is None:
                cycle_unknown = True
                continue
            stages = (
                component.scheduled,
                component.requested,
                component.responded,
                component.raw_saved,
                component.parsed,
                component.admitted,
                component.fresh,
                component.replayable,
            )
            if any(value is None for value in stages):
                cycle_unknown = True
            elif not all(stages):
                if component.missing_reason is None:
                    cycle_unknown = True
                else:
                    cycle_failed = True
        boundary_values = (
            cycle.pit_violation,
            cycle.instrument_identity_valid,
            cycle.closed_bar_valid,
        )
        if any(value is None for value in boundary_values):
            cycle_unknown = True
        elif (
            cycle.pit_violation is True
            or cycle.instrument_identity_valid is False
            or cycle.closed_bar_valid is False
        ):
            cycle_failed = True
        if cycle_unknown:
            reasons.append(f"COVERAGE_FIELDS_MISSING:{cycle.cycle_id}")
        elif cycle_failed:
            explicit_failed += 1
        else:
            usable += 1

    if reasons:
        status = UNKNOWN_INCONCLUSIVE
    elif explicit_unobservable:
        status = UNOBSERVABLE
    elif explicit_source_insufficient:
        status = KNOWN_SOURCE_INSUFFICIENT
    elif explicit_failed:
        status = KNOWN_FAIL
    elif usable == denominator and denominator > 0:
        status = KNOWN_PASS
    else:
        status = UNKNOWN_INCONCLUSIVE
    return CoverageReadiness(
        gate=U_COVERAGE,
        status=status,
        denominator=denominator,
        terminal_count=terminal_count,
        usable_core4_count=usable,
        failed_cycle_count=explicit_failed,
        window_count=len(windows),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class PredictionArmSummary:
    """One action sealed before the shared future outcome became available."""

    arm_id: str
    policy_id: str
    action: str
    sealed_at: str

    def __post_init__(self) -> None:
        if self.arm_id not in PREDICTION_ARMS:
            raise EvidenceContractError("unsupported prediction arm_id")
        _nonempty(self.policy_id, field_name="policy_id")
        if self.action not in PREDICTION_ACTIONS:
            raise EvidenceContractError("prediction action must be LONG, SHORT or WAIT")
        _timestamp(self.sealed_at, field_name="sealed_at")


@dataclass(frozen=True, slots=True)
class PredictionCycleSummary:
    """A same-PIT candidate/baseline decision paired to one future outcome."""

    cycle_id: str
    phase: str
    window_id: str
    window_start_at: str
    window_end_at: str
    pair_ordinal: int
    expected_pairs: int
    pit_snapshot_ref: str | None
    instrument_id: str | None
    analysis_profile: str | None
    data_profile: str | None
    theory_revision: str | None
    horizon_seconds: int | None
    outcome_definition_id: str | None
    decision_at: str
    outcome_available_at: str | None
    outcome: str | None
    eligible: bool | None
    arms: tuple[PredictionArmSummary, ...]

    def __post_init__(self) -> None:
        _nonempty(self.cycle_id, field_name="cycle_id")
        if self.phase not in PREDICTION_PHASES:
            raise EvidenceContractError("unsupported prediction phase")
        _nonempty(self.window_id, field_name="window_id")
        start = _timestamp(self.window_start_at, field_name="window_start_at")
        end = _timestamp(self.window_end_at, field_name="window_end_at")
        if end <= start:
            raise EvidenceContractError("prediction window end must follow start")
        _integer(self.pair_ordinal, field_name="pair_ordinal", minimum=1)
        _integer(self.expected_pairs, field_name="expected_pairs", minimum=1)
        if self.pair_ordinal > self.expected_pairs:
            raise EvidenceContractError("pair_ordinal exceeds expected_pairs")
        for name in (
            "pit_snapshot_ref",
            "instrument_id",
            "analysis_profile",
            "data_profile",
            "theory_revision",
            "outcome_definition_id",
        ):
            _optional_nonempty(getattr(self, name), field_name=name)
        _optional_integer(
            self.horizon_seconds, field_name="horizon_seconds", minimum=1
        )
        decision = _timestamp(self.decision_at, field_name="decision_at")
        if not start <= decision < end:
            raise EvidenceContractError("prediction decision must fall inside its window")
        if self.outcome_available_at is not None:
            available = _timestamp(
                self.outcome_available_at, field_name="outcome_available_at"
            )
            if available <= decision:
                raise EvidenceContractError("future outcome must become available after decision")
        if self.outcome is not None and self.outcome not in PREDICTION_OUTCOMES:
            raise EvidenceContractError("outcome must be UP, DOWN, FLAT or None")
        _optional_boolean(self.eligible, field_name="eligible")
        arms = tuple(self.arms)
        if not all(isinstance(item, PredictionArmSummary) for item in arms):
            raise EvidenceContractError("arms must contain PredictionArmSummary values")
        arm_ids = tuple(item.arm_id for item in arms)
        if len(arm_ids) != len(set(arm_ids)) or set(arm_ids) != set(PREDICTION_ARMS):
            raise EvidenceContractError("each prediction cycle must seal all five arms once")
        actions = {item.arm_id: item.action for item in arms}
        if (
            actions["ALWAYS_LONG"] != "LONG"
            or actions["ALWAYS_SHORT"] != "SHORT"
            or actions["WAIT_ONLY"] != "WAIT"
        ):
            raise EvidenceContractError("fixed prediction controls have incorrect actions")
        if any(
            _timestamp(item.sealed_at, field_name="sealed_at") < decision
            for item in arms
        ):
            raise EvidenceContractError("prediction arms cannot be sealed before decision")
        object.__setattr__(self, "arms", arms)


@dataclass(frozen=True, slots=True)
class PredictionReadiness:
    gate: str
    status: str
    denominator: int
    resolved_pairs: int
    calibration_pairs: int
    confirmation_pairs: int
    calibration_candidate_loss: int | None
    calibration_price_only_loss: int | None
    confirmation_candidate_loss: int | None
    confirmation_price_only_loss: int | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.gate != U_PREDICTION:
            raise EvidenceContractError("invalid PredictionReadiness gate")
        _status(self.status)
        for name in (
            "denominator",
            "resolved_pairs",
            "calibration_pairs",
            "confirmation_pairs",
        ):
            _integer(getattr(self, name), field_name=name)
        for name in (
            "calibration_candidate_loss",
            "calibration_price_only_loss",
            "confirmation_candidate_loss",
            "confirmation_price_only_loss",
        ):
            _optional_integer(getattr(self, name), field_name=name)
        if self.resolved_pairs > self.denominator:
            raise EvidenceContractError("resolved prediction pairs exceed denominator")
        reasons = tuple(self.reasons)
        if not all(isinstance(reason, str) and reason for reason in reasons):
            raise EvidenceContractError("PredictionReadiness reasons must be strings")
        object.__setattr__(self, "reasons", reasons)


def _phase_increment_passes(losses: dict[str, int]) -> bool:
    candidate = losses["V330_CANDIDATE"]
    return candidate < losses["PRICE_ONLY_DETERMINISTIC"] and all(
        candidate <= losses[control]
        for control in ("ALWAYS_LONG", "ALWAYS_SHORT", "WAIT_ONLY")
    )


def assess_prediction_readiness(
    policy: EvidencePolicy,
    summaries: Iterable[PredictionCycleSummary],
) -> PredictionReadiness:
    """Assess paired ordinal increment across calibration and untouched windows."""

    if not isinstance(policy, EvidencePolicy):
        raise EvidenceContractError("policy must be EvidencePolicy")
    pairs = tuple(summaries)
    if not all(isinstance(item, PredictionCycleSummary) for item in pairs):
        raise EvidenceContractError(
            "prediction summaries must be PredictionCycleSummary values"
        )
    cycle_ids = tuple(item.cycle_id for item in pairs)
    if len(cycle_ids) != len(set(cycle_ids)):
        raise EvidenceContractError("prediction cycle_id values must be unique")
    reasons: list[str] = []
    if not pairs:
        reasons.append("NO_FORWARD_PAIRS")
    groups = {
        phase: tuple(item for item in pairs if item.phase == phase)
        for phase in PREDICTION_PHASES
    }
    phase_intervals: dict[str, tuple[datetime, datetime]] = {}
    for phase, group in groups.items():
        if not group:
            reasons.append(f"PHASE_MISSING:{phase}")
            continue
        windows = {item.window_id for item in group}
        starts = {item.window_start_at for item in group}
        ends = {item.window_end_at for item in group}
        expected_values = {item.expected_pairs for item in group}
        if (
            len(windows) != 1
            or len(starts) != 1
            or len(ends) != 1
            or len(expected_values) != 1
        ):
            reasons.append(f"PHASE_CONTRACT_DRIFT:{phase}")
            continue
        expected = next(iter(expected_values))
        if len(group) != expected or {item.pair_ordinal for item in group} != set(
            range(1, expected + 1)
        ):
            reasons.append(f"PHASE_PAIRS_INCOMPLETE:{phase}")
        phase_intervals[phase] = (
            _timestamp(next(iter(starts)), field_name="window_start_at"),
            _timestamp(next(iter(ends)), field_name="window_end_at"),
        )
    if set(phase_intervals) == set(PREDICTION_PHASES) and (
        phase_intervals["CALIBRATION"][1]
        > phase_intervals["UNTOUCHED_CONFIRMATION"][0]
    ):
        reasons.append("CONFIRMATION_NOT_UNTOUCHED_OR_ORDERED")

    identity_fields = (
        "pit_snapshot_ref",
        "instrument_id",
        "analysis_profile",
        "data_profile",
        "theory_revision",
        "horizon_seconds",
        "outcome_definition_id",
    )
    if any(getattr(item, name) is None for item in pairs for name in identity_fields):
        reasons.append("PREDICTION_SCOPE_OR_PIT_MISSING")
    elif pairs and (
        any(
            len({getattr(item, name) for item in pairs}) != 1
            for name in identity_fields[1:-3]
        )
        or {item.theory_revision for item in pairs} != {policy.theory_revision}
        or len({item.horizon_seconds for item in pairs}) != 1
        or len({item.outcome_definition_id for item in pairs}) != 1
    ):
        reasons.append("PREDICTION_SCOPE_IDENTITY_DRIFT")
    if any(item.eligible is not True for item in pairs):
        reasons.append("ELIGIBILITY_MISSING_OR_FALSE")
    if any(
        len(
            {
                arm.policy_id
                for item in pairs
                for arm in item.arms
                if arm.arm_id == arm_id
            }
        )
        != 1
        for arm_id in PREDICTION_ARMS
    ):
        reasons.append("PREDICTION_ARM_POLICY_DRIFT")
    if any(item.outcome is None or item.outcome_available_at is None for item in pairs):
        reasons.append("PAIRED_FUTURE_OUTCOME_MISSING")
    if any(
        item.outcome_available_at is not None
        and any(
            _timestamp(arm.sealed_at, field_name="sealed_at")
            >= _timestamp(item.outcome_available_at, field_name="outcome_available_at")
            for arm in item.arms
        )
        for item in pairs
    ):
        reasons.append("ARM_NOT_SEALED_BEFORE_OUTCOME")

    losses_by_phase: dict[str, dict[str, int]] = {}
    if not reasons:
        for phase, group in groups.items():
            totals = {arm_id: 0 for arm_id in PREDICTION_ARMS}
            for item in group:
                actions = {arm.arm_id: arm.action for arm in item.arms}
                if item.outcome is None:
                    raise EvidenceContractError("resolved prediction pair lacks outcome")
                for arm_id, action in actions.items():
                    totals[arm_id] += _ORDINAL_LOSS[(action, item.outcome)]
            losses_by_phase[phase] = totals
    resolved = sum(
        item.outcome is not None and item.outcome_available_at is not None
        for item in pairs
    )
    if reasons:
        status = UNKNOWN_INCONCLUSIVE
    elif all(_phase_increment_passes(losses_by_phase[phase]) for phase in PREDICTION_PHASES):
        status = KNOWN_PASS
    else:
        status = INCREMENT_NOT_DEMONSTRATED
    calibration = losses_by_phase.get("CALIBRATION", {})
    confirmation = losses_by_phase.get("UNTOUCHED_CONFIRMATION", {})
    return PredictionReadiness(
        gate=U_PREDICTION,
        status=status,
        denominator=len(pairs),
        resolved_pairs=resolved,
        calibration_pairs=len(groups["CALIBRATION"]),
        confirmation_pairs=len(groups["UNTOUCHED_CONFIRMATION"]),
        calibration_candidate_loss=calibration.get("V330_CANDIDATE"),
        calibration_price_only_loss=calibration.get("PRICE_ONLY_DETERMINISTIC"),
        confirmation_candidate_loss=confirmation.get("V330_CANDIDATE"),
        confirmation_price_only_loss=confirmation.get("PRICE_ONLY_DETERMINISTIC"),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class PositionPairSummary:
    """One single-dimension public-reference policy comparison."""

    cycle_id: str
    dimension: str
    phase: str | None
    window_id: str | None
    window_start_at: str | None
    window_end_at: str | None
    pair_ordinal: int | None
    expected_pairs: int | None
    changed_dimensions: tuple[str, ...]
    forecast_ref: str | None
    path_ref: str | None
    baseline_policy_id: str | None
    candidate_policy_id: str | None
    baseline_reference_score: int | None
    candidate_reference_score: int | None
    baseline_guardrail_breached: bool | None
    candidate_guardrail_breached: bool | None
    authority: str
    theory_revision: str | None

    def __post_init__(self) -> None:
        _nonempty(self.cycle_id, field_name="cycle_id")
        if self.dimension not in POSITION_POLICY_DIMENSIONS:
            raise EvidenceContractError("unsupported position dimension")
        if self.phase is not None and self.phase not in PREDICTION_PHASES:
            raise EvidenceContractError("unsupported position evidence phase")
        _optional_nonempty(self.window_id, field_name="window_id")
        start = (
            _timestamp(self.window_start_at, field_name="window_start_at")
            if self.window_start_at is not None
            else None
        )
        end = (
            _timestamp(self.window_end_at, field_name="window_end_at")
            if self.window_end_at is not None
            else None
        )
        if start is not None and end is not None and end <= start:
            raise EvidenceContractError("position evidence window end must follow start")
        _optional_integer(self.pair_ordinal, field_name="pair_ordinal", minimum=1)
        _optional_integer(self.expected_pairs, field_name="expected_pairs", minimum=1)
        if (
            self.pair_ordinal is not None
            and self.expected_pairs is not None
            and self.pair_ordinal > self.expected_pairs
        ):
            raise EvidenceContractError("position pair_ordinal exceeds expected_pairs")
        if self.changed_dimensions != (self.dimension,):
            raise EvidenceContractError("position pair must change exactly one dimension")
        for name in (
            "forecast_ref",
            "path_ref",
            "baseline_policy_id",
            "candidate_policy_id",
            "theory_revision",
        ):
            _optional_nonempty(getattr(self, name), field_name=name)
        _optional_signed_integer(
            self.baseline_reference_score, field_name="baseline_reference_score"
        )
        _optional_signed_integer(
            self.candidate_reference_score, field_name="candidate_reference_score"
        )
        _optional_boolean(
            self.baseline_guardrail_breached,
            field_name="baseline_guardrail_breached",
        )
        _optional_boolean(
            self.candidate_guardrail_breached,
            field_name="candidate_guardrail_breached",
        )
        if self.authority != PUBLIC_REFERENCE_ONLY:
            raise EvidenceContractError("position pair must remain reference-only")


@dataclass(frozen=True, slots=True)
class PositionReadiness:
    gate: str
    status: str
    execution_status: str
    denominator: int
    covered_dimensions: tuple[str, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.gate != U_POSITION:
            raise EvidenceContractError("invalid PositionReadiness gate")
        _status(self.status)
        if self.execution_status != NEEDS_SEPARATE_AUTHORITY:
            raise EvidenceContractError("execution status cannot be inferred from reference data")
        _integer(self.denominator, field_name="denominator")
        covered = tuple(self.covered_dimensions)
        if not set(covered).issubset(POSITION_POLICY_DIMENSIONS):
            raise EvidenceContractError("unsupported covered position dimension")
        if len(covered) != len(set(covered)):
            raise EvidenceContractError("covered position dimensions must be unique")
        reasons = tuple(self.reasons)
        if not all(isinstance(reason, str) and reason for reason in reasons):
            raise EvidenceContractError("PositionReadiness reasons must be strings")
        object.__setattr__(self, "covered_dimensions", covered)
        object.__setattr__(self, "reasons", reasons)


def assess_position_readiness(
    policy: EvidencePolicy,
    summaries: Iterable[PositionPairSummary],
) -> PositionReadiness:
    """Assess four isolated reference comparisons; never infer execution effects."""

    if not isinstance(policy, EvidencePolicy):
        raise EvidenceContractError("policy must be EvidencePolicy")
    pairs = tuple(summaries)
    if not all(isinstance(item, PositionPairSummary) for item in pairs):
        raise EvidenceContractError("position summaries must be PositionPairSummary values")
    identities = tuple((item.cycle_id, item.dimension) for item in pairs)
    if len(identities) != len(set(identities)):
        raise EvidenceContractError("position cycle/dimension pairs must be unique")
    covered = tuple(
        dimension
        for dimension in policy.position_dimensions
        if any(item.dimension == dimension for item in pairs)
    )
    reasons: list[str] = []
    if set(covered) != set(policy.position_dimensions):
        reasons.append("FOUR_POSITION_DIMENSIONS_REQUIRED")
    if any(
        item.phase is None
        or item.window_id is None
        or item.window_start_at is None
        or item.window_end_at is None
        or item.pair_ordinal is None
        or item.expected_pairs is None
        for item in pairs
    ):
        reasons.append("POSITION_PAIR_METADATA_MISSING")
    phase_groups: dict[tuple[str, str], tuple[PositionPairSummary, ...]] = {}
    phase_intervals: dict[tuple[str, str], tuple[datetime, datetime, str]] = {}
    for dimension in policy.position_dimensions:
        for phase in policy.position_phases:
            group = tuple(
                item
                for item in pairs
                if item.dimension == dimension and item.phase == phase
            )
            phase_groups[(dimension, phase)] = group
            if not group:
                reasons.append(f"POSITION_PHASE_MISSING:{dimension}:{phase}")
                continue
            if any(
                item.window_id is None
                or item.window_start_at is None
                or item.window_end_at is None
                or item.pair_ordinal is None
                or item.expected_pairs is None
                for item in group
            ):
                continue
            windows = {item.window_id for item in group}
            starts = {item.window_start_at for item in group}
            ends = {item.window_end_at for item in group}
            expected_values = {item.expected_pairs for item in group}
            if (
                len(windows) != 1
                or len(starts) != 1
                or len(ends) != 1
                or len(expected_values) != 1
            ):
                reasons.append(f"POSITION_PHASE_CONTRACT_DRIFT:{dimension}:{phase}")
                continue
            expected = next(iter(expected_values))
            if len(group) != expected or {item.pair_ordinal for item in group} != set(
                range(1, expected + 1)
            ):
                reasons.append(f"POSITION_PHASE_PAIRS_INCOMPLETE:{dimension}:{phase}")
            phase_intervals[(dimension, phase)] = (
                _timestamp(next(iter(starts)), field_name="window_start_at"),
                _timestamp(next(iter(ends)), field_name="window_end_at"),
                next(iter(windows)),
            )
        calibration = phase_intervals.get((dimension, "CALIBRATION"))
        confirmation = phase_intervals.get(
            (dimension, "UNTOUCHED_CONFIRMATION")
        )
        if calibration is not None and confirmation is not None and (
            calibration[1] > confirmation[0] or calibration[2] == confirmation[2]
        ):
            reasons.append(f"POSITION_CONFIRMATION_NOT_UNTOUCHED:{dimension}")
    if any(
        item.forecast_ref is None
        or item.path_ref is None
        or item.baseline_policy_id is None
        or item.candidate_policy_id is None
        or item.theory_revision is None
        or item.baseline_reference_score is None
        or item.candidate_reference_score is None
        or item.baseline_guardrail_breached is None
        or item.candidate_guardrail_breached is None
        for item in pairs
    ):
        reasons.append("POSITION_PAIR_DATA_MISSING")
    elif {item.theory_revision for item in pairs} != {policy.theory_revision}:
        reasons.append("POSITION_THEORY_IDENTITY_DRIFT")
    if any(
        len({item.baseline_policy_id for item in pairs if item.dimension == dimension})
        != 1
        or len(
            {item.candidate_policy_id for item in pairs if item.dimension == dimension}
        )
        != 1
        for dimension in covered
    ):
        reasons.append("POSITION_POLICY_ID_DRIFT")
    if reasons:
        status = UNKNOWN_INCONCLUSIVE
    else:
        demonstrated = True
        for dimension in policy.position_dimensions:
            for phase in policy.position_phases:
                group = phase_groups[(dimension, phase)]
                baseline_score = sum(
                    int(item.baseline_reference_score) for item in group
                )
                candidate_score = sum(
                    int(item.candidate_reference_score) for item in group
                )
                guardrail_worsened = any(
                    item.baseline_guardrail_breached is False
                    and item.candidate_guardrail_breached is True
                    for item in group
                )
                if (
                    candidate_score <= baseline_score
                    or guardrail_worsened
                ):
                    demonstrated = False
        status = KNOWN_PASS if demonstrated else INCREMENT_NOT_DEMONSTRATED
    return PositionReadiness(
        gate=U_POSITION,
        status=status,
        execution_status=NEEDS_SEPARATE_AUTHORITY,
        denominator=len(pairs),
        covered_dimensions=covered,
        reasons=tuple(reasons),
    )


__all__ = [
    "COLD",
    "CORE_4",
    "DELTA",
    "EVENT_FAST",
    "EVIDENCE_STATUSES",
    "INCREMENT_NOT_DEMONSTRATED",
    "KNOWN_FAIL",
    "KNOWN_PASS",
    "KNOWN_SOURCE_INSUFFICIENT",
    "NEEDS_SEPARATE_AUTHORITY",
    "POSITION_POLICY_DIMENSIONS",
    "PREDICTION_ACTIONS",
    "PREDICTION_ARMS",
    "PREDICTION_OUTCOMES",
    "PREDICTION_PHASES",
    "PUBLIC_DIRECT",
    "PUBLIC_REFERENCE_ONLY",
    "SOURCE_INSUFFICIENT",
    "SOURCE_CLASSIFICATIONS",
    "SOURCE_PROHIBITED",
    "SOURCE_UNOBSERVABLE",
    "TARGET_NOT_MET",
    "UNKNOWN_INCONCLUSIVE",
    "UNOBSERVABLE",
    "U_COVERAGE",
    "U_POSITION",
    "U_PREDICTION",
    "V332_EVIDENCE_POLICY_ID",
    "U_SPEED",
    "CoverageComponentSummary",
    "CoverageCycleSummary",
    "CoverageReadiness",
    "EvidenceContractError",
    "EvidencePolicy",
    "PositionPairSummary",
    "PositionReadiness",
    "PredictionArmSummary",
    "PredictionCycleSummary",
    "PredictionReadiness",
    "SpeedCycleSummary",
    "SpeedReadiness",
    "assess_coverage_readiness",
    "assess_position_readiness",
    "assess_prediction_readiness",
    "assess_speed_readiness",
]
