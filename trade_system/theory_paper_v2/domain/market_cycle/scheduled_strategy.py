"""V3.4 scheduled strategic-cognition and forecast-only contracts.

The module makes the current V3.4 time-authority boundary explicit:

* LLM market decisions are admitted only on fixed UTC four-hour committee slots.
* 1h/15m information may be read as evidence, but it cannot wake the LLM or
  create a new thesis between committee slots.
* A local executor may only carry out actions already authorized by the last
  committee plan.  A safety system may only reduce risk.
* FORECAST_ONLY records contain no paper/testnet/live execution authority.

The code intentionally does not choose market direction or synthesize missing
Agent reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ..contracts.canonical import canonical_bytes


MIN_DECISION_HORIZON_HOURS = 4
COMMITTEE_INTERVAL_HOURS = 4
COMMITTEE_HOURS_UTC = (0, 4, 8, 12, 16, 20)
FORECAST_SCHEMA_ID = "agent-trade-emotion.v340-forecast-only"
FORECAST_SCHEMA_VERSION = "1.0.0"
FORECAST_OUTCOME_SCHEMA_ID = "agent-trade-emotion.v340-forecast-outcome"
FORECAST_OUTCOME_SCHEMA_VERSION = "1.1.0"
LOW_TOKEN_CONTEXT_SCHEMA_ID = "agent-trade-emotion.v340-low-token-context"
LOW_TOKEN_CONTEXT_SCHEMA_VERSION = "1.0.0"
DEFAULT_CONTEXT_MAX_UTF8_BYTES = 64 * 1024
V340_THEORY_REVISION = "3.4.0-low-frequency-strategic-agent-candidate.2"
V340_THEORY_MANIFEST_SHA256 = "1e7c3512c0cbd7de07d0b4c648bb65a9e668c27917297ee2ddc1c6b62a7bfe56"
V340_THEORY_IDENTITY = f"{V340_THEORY_REVISION}@{V340_THEORY_MANIFEST_SHA256}"
FORECAST_HORIZONS = ("4h", "12h", "24h")
FORECAST_DIRECTIONS = frozenset({"UP", "DOWN", "FLAT", "MIXED", "UNKNOWN"})
STATE_CHANGES = frozenset(
    {"INITIALIZE", "KEEP", "STRENGTHEN", "WEAKEN", "INVALIDATE", "REPLACE"}
)
SCHEDULED_TIMEFRAME_AUTHORITIES = MappingProxyType(
    {
        "15m": "EVIDENCE",
        "1h": "EVIDENCE",
        "4h": "DECISION",
        "1d": "REGIME",
    }
)


class ScheduledStrategyError(ValueError):
    """The V3.4 scheduled-cognition contract was violated."""


@dataclass(frozen=True, slots=True)
class ForecastSemanticAssessment:
    status: str
    errors: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status == "FORECAST_SEMANTICS_READY"

    def to_dict(self) -> dict[str, object]:
        return {"status": self.status, "errors": list(self.errors)}


@dataclass(frozen=True, slots=True)
class IntraWindowAuthorityAssessment:
    allowed: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reason": self.reason}


def _parse_utc(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ScheduledStrategyError(f"{field}:REQUIRED_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScheduledStrategyError(f"{field}:INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScheduledStrategyError(f"{field}:UTC_OFFSET_REQUIRED")
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_committee_slot(value: str) -> str:
    """Return canonical UTC text only for exact 00/04/08/12/16/20 UTC slots."""

    parsed = _parse_utc(value, field="committee_slot_at")
    if (
        parsed.hour not in COMMITTEE_HOURS_UTC
        or parsed.minute != 0
        or parsed.second != 0
        or parsed.microsecond != 0
    ):
        raise ScheduledStrategyError("committee_slot_at:NOT_FIXED_4H_UTC_SLOT")
    return _utc_text(parsed)


def next_committee_at(value: str) -> str:
    """Return the first fixed four-hour committee slot strictly after ``value``."""

    parsed = _parse_utc(value, field="observed_at")
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    interval = COMMITTEE_INTERVAL_HOURS * 3600
    elapsed = int((parsed - epoch).total_seconds())
    next_seconds = ((elapsed // interval) + 1) * interval
    return _utc_text(epoch + timedelta(seconds=next_seconds))


def _nonempty_text(value: object, *, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field}:REQUIRED_NONEMPTY_TEXT")


def _text_array(value: object, *, field: str, errors: list[str], minimum: int = 1) -> None:
    if not isinstance(value, (list, tuple)):
        errors.append(f"{field}:REQUIRED_TEXT_ARRAY")
        return
    valid = [item for item in value if isinstance(item, str) and item.strip()]
    if len(valid) != len(value) or len(valid) < minimum:
        errors.append(f"{field}:INSUFFICIENT_OR_INVALID_TEXT_ITEMS")


def _mapping(value: object, *, field: str, errors: list[str]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        errors.append(f"{field}:REQUIRED_OBJECT")
        return None
    return value


def _decimal(value: object, *, field: str, errors: list[str]) -> Decimal | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field}:REQUIRED_DECIMAL_STRING")
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        errors.append(f"{field}:INVALID_DECIMAL")
        return None
    if not parsed.is_finite():
        errors.append(f"{field}:NONFINITE_DECIMAL")
        return None
    return parsed


def _assess_timeframe_zones(payload: Mapping[str, Any], *, errors: list[str]) -> None:
    zones = _mapping(payload.get("timeframe_zones"), field="timeframe_zones", errors=errors)
    if zones is None:
        return
    for timeframe, authority in SCHEDULED_TIMEFRAME_AUTHORITIES.items():
        zone = _mapping(zones.get(timeframe), field=f"timeframe_zones.{timeframe}", errors=errors)
        if zone is None:
            continue
        lower = _decimal(zone.get("lower"), field=f"timeframe_zones.{timeframe}.lower", errors=errors)
        upper = _decimal(zone.get("upper"), field=f"timeframe_zones.{timeframe}.upper", errors=errors)
        if lower is not None and upper is not None and lower >= upper:
            errors.append(f"timeframe_zones.{timeframe}:LOWER_MUST_BE_BELOW_UPPER")
        if zone.get("authority") != authority:
            errors.append(f"timeframe_zones.{timeframe}.authority:EXPECTED_{authority}")
        _nonempty_text(zone.get("meaning"), field=f"timeframe_zones.{timeframe}.meaning", errors=errors)
        _nonempty_text(
            zone.get("break_effect"),
            field=f"timeframe_zones.{timeframe}.break_effect",
            errors=errors,
        )


def assess_forecast_semantics(payload: Mapping[str, Any]) -> ForecastSemanticAssessment:
    """Validate the minimum Stage-A forecast semantics without creating a trade action."""

    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ForecastSemanticAssessment("FORECAST_SEMANTICS_NOT_READY", ("payload:REQUIRED_OBJECT",))
    if payload.get("schema_id") != FORECAST_SCHEMA_ID:
        errors.append("schema_id:UNEXPECTED")
    if payload.get("schema_version") != FORECAST_SCHEMA_VERSION:
        errors.append("schema_version:UNEXPECTED")
    horizon = payload.get("strategic_horizon_hours")
    if type(horizon) is not int or horizon < MIN_DECISION_HORIZON_HOURS:
        errors.append("strategic_horizon_hours:MUST_BE_INTEGER_AT_LEAST_4")
    if payload.get("directional_bias") not in FORECAST_DIRECTIONS:
        errors.append("directional_bias:UNSUPPORTED")
    if payload.get("state_change") not in STATE_CHANGES:
        errors.append("state_change:UNSUPPORTED")

    for field in (
        "trend_phase",
        "causal_thesis",
        "alternative_thesis",
        "catalyst_analysis",
        "sentiment_analysis",
        "data_quality_analysis",
        "future_space_analysis",
        "next_discriminating_observation",
    ):
        _nonempty_text(payload.get(field), field=field, errors=errors)
    _text_array(payload.get("if_then_paths"), field="if_then_paths", errors=errors, minimum=2)
    _text_array(payload.get("participant_analysis"), field="participant_analysis", errors=errors)
    _text_array(payload.get("data_conflicts"), field="data_conflicts", errors=errors)
    _assess_timeframe_zones(payload, errors=errors)

    forecasts = _mapping(payload.get("horizons"), field="horizons", errors=errors)
    if forecasts is not None:
        for horizon_name in FORECAST_HORIZONS:
            item = _mapping(forecasts.get(horizon_name), field=f"horizons.{horizon_name}", errors=errors)
            if item is None:
                continue
            if item.get("expected_direction") not in FORECAST_DIRECTIONS:
                errors.append(f"horizons.{horizon_name}.expected_direction:UNSUPPORTED")
            _nonempty_text(item.get("path"), field=f"horizons.{horizon_name}.path", errors=errors)
            _nonempty_text(
                item.get("invalidation_condition"),
                field=f"horizons.{horizon_name}.invalidation_condition",
                errors=errors,
            )
            lower = _decimal(item.get("target_lower"), field=f"horizons.{horizon_name}.target_lower", errors=errors)
            upper = _decimal(item.get("target_upper"), field=f"horizons.{horizon_name}.target_upper", errors=errors)
            if lower is not None and upper is not None and lower > upper:
                errors.append(f"horizons.{horizon_name}:TARGET_LOWER_MUST_NOT_EXCEED_UPPER")

    return ForecastSemanticAssessment(
        status="FORECAST_SEMANTICS_READY" if not errors else "FORECAST_SEMANTICS_NOT_READY",
        errors=tuple(errors),
    )


def build_low_token_context(
    *,
    asset_id: str,
    committee_slot_at: str,
    input_cutoff_at: str,
    reference_price: str,
    theory_identity: str,
    shared_context_summary: Mapping[str, Any],
    asset_delta_summary: Mapping[str, Any],
    portfolio_summary: Mapping[str, Any],
    previous_state_summary: Mapping[str, Any] | None,
    source_refs: Sequence[str],
    max_utf8_bytes: int = DEFAULT_CONTEXT_MAX_UTF8_BYTES,
) -> dict[str, Any]:
    """Build one bounded context packet containing state + delta, never full history.

    The function does not summarize raw data itself.  Callers must pass already
    admitted compact summaries and immutable source references.  This keeps the
    token-control boundary deterministic and auditable.
    """

    slot = require_committee_slot(committee_slot_at)
    cutoff = _parse_utc(input_cutoff_at, field="input_cutoff_at")
    slot_dt = _parse_utc(slot, field="committee_slot_at")
    if cutoff > slot_dt:
        raise ScheduledStrategyError("input_cutoff_at:AFTER_COMMITTEE_SLOT")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise ScheduledStrategyError("asset_id:REQUIRED")
    reference_errors: list[str] = []
    reference = _decimal(reference_price, field="reference_price", errors=reference_errors)
    if reference_errors or reference is None or reference <= 0:
        raise ScheduledStrategyError("reference_price:POSITIVE_DECIMAL_STRING_REQUIRED")
    if theory_identity != V340_THEORY_IDENTITY:
        raise ScheduledStrategyError("theory_identity:CURRENT_V340_IDENTITY_REQUIRED")
    if type(max_utf8_bytes) is not int or not 4096 <= max_utf8_bytes <= 256 * 1024:
        raise ScheduledStrategyError("max_utf8_bytes:OUT_OF_RANGE")
    if not source_refs or not all(isinstance(item, str) and item.strip() for item in source_refs):
        raise ScheduledStrategyError("source_refs:NONEMPTY_VALID_REFS_REQUIRED")
    for name, value in (
        ("shared_context_summary", shared_context_summary),
        ("asset_delta_summary", asset_delta_summary),
        ("portfolio_summary", portfolio_summary),
    ):
        if not isinstance(value, Mapping):
            raise ScheduledStrategyError(f"{name}:REQUIRED_OBJECT")
    if previous_state_summary is not None and not isinstance(previous_state_summary, Mapping):
        raise ScheduledStrategyError("previous_state_summary:REQUIRED_OBJECT_OR_NULL")

    packet: dict[str, Any] = {
        "schema_id": LOW_TOKEN_CONTEXT_SCHEMA_ID,
        "schema_version": LOW_TOKEN_CONTEXT_SCHEMA_VERSION,
        "mode": "FORECAST_ONLY",
        "asset_id": asset_id.strip(),
        "committee_slot_at": slot,
        "next_committee_at": next_committee_at(slot),
        "minimum_decision_horizon_hours": MIN_DECISION_HORIZON_HOURS,
        "input_cutoff_at": _utc_text(cutoff),
        "reference_price": format(reference, "f"),
        "theory_identity": theory_identity,
        "time_authority": {
            "15m": "EVIDENCE_ONLY",
            "1h": "EVIDENCE_ONLY",
            "4h": "DECISION_MINIMUM",
            "1d": "REGIME",
            "intra_window_llm_market_revisions": "DENIED",
        },
        "shared_context_summary": dict(shared_context_summary),
        "asset_delta_summary": dict(asset_delta_summary),
        "portfolio_summary": dict(portfolio_summary),
        "previous_strategic_state": None if previous_state_summary is None else dict(previous_state_summary),
        "source_refs": list(source_refs),
    }
    raw = canonical_bytes(packet)
    if len(raw) > max_utf8_bytes:
        raise ScheduledStrategyError(
            f"low_token_context:BYTE_BUDGET_EXCEEDED:{len(raw)}>{max_utf8_bytes}"
        )
    packet["context_size_bytes"] = len(raw)
    packet["context_sha256"] = sha256(raw).hexdigest()
    return packet


def verify_low_token_context(packet: Mapping[str, Any]) -> None:
    """Verify that a previously built context packet has not drifted or crossed assets."""

    if not isinstance(packet, Mapping):
        raise ScheduledStrategyError("low_token_context:REQUIRED_OBJECT")
    if packet.get("schema_id") != LOW_TOKEN_CONTEXT_SCHEMA_ID:
        raise ScheduledStrategyError("low_token_context:SCHEMA_ID_MISMATCH")
    if packet.get("schema_version") != LOW_TOKEN_CONTEXT_SCHEMA_VERSION:
        raise ScheduledStrategyError("low_token_context:SCHEMA_VERSION_MISMATCH")
    if packet.get("mode") != "FORECAST_ONLY":
        raise ScheduledStrategyError("low_token_context:MODE_MISMATCH")
    stored_size = packet.get("context_size_bytes")
    stored_sha = packet.get("context_sha256")
    if type(stored_size) is not int or stored_size < 0:
        raise ScheduledStrategyError("low_token_context:SIZE_INVALID")
    if not isinstance(stored_sha, str) or len(stored_sha) != 64:
        raise ScheduledStrategyError("low_token_context:SHA_INVALID")
    unsigned = dict(packet)
    unsigned.pop("context_size_bytes", None)
    unsigned.pop("context_sha256", None)
    raw = canonical_bytes(unsigned)
    if len(raw) != stored_size:
        raise ScheduledStrategyError("low_token_context:SIZE_MISMATCH")
    if sha256(raw).hexdigest() != stored_sha:
        raise ScheduledStrategyError("low_token_context:SHA_MISMATCH")
    require_committee_slot(str(packet.get("committee_slot_at")))
    if packet.get("next_committee_at") != next_committee_at(str(packet.get("committee_slot_at"))):
        raise ScheduledStrategyError("low_token_context:NEXT_COMMITTEE_MISMATCH")


def assess_intra_window_authority(
    *,
    actor: str,
    action: str,
    preauthorized_by_committee: bool = False,
    emergency: bool = False,
) -> IntraWindowAuthorityAssessment:
    """Enforce the no-new-thesis interval between two 4H committees."""

    if actor == "LLM":
        if action in {"WAIT", "HOLD"}:
            return IntraWindowAuthorityAssessment(True, "LLM_INTRA_WINDOW_NO_POSITION_CHANGE")
        return IntraWindowAuthorityAssessment(False, "LLM_MARKET_ACTION_DENIED_UNTIL_NEXT_4H_COMMITTEE")

    if actor == "LOCAL_EXECUTOR":
        if action in {"WAIT", "HOLD"}:
            return IntraWindowAuthorityAssessment(True, "NO_CHANGE")
        if action in {"OPEN", "ADD", "REDUCE", "HARVEST", "EXIT"} and preauthorized_by_committee:
            return IntraWindowAuthorityAssessment(True, "FROZEN_4H_PLAN_PREAUTHORIZED")
        return IntraWindowAuthorityAssessment(False, "LOCAL_EXECUTOR_CANNOT_CREATE_OR_REVISE_THESIS")

    if actor == "SAFETY_SYSTEM":
        if not emergency:
            return IntraWindowAuthorityAssessment(False, "SAFETY_ACTION_REQUIRES_EMERGENCY")
        if action in {"HALT", "CANCEL", "REDUCE", "EXIT"}:
            return IntraWindowAuthorityAssessment(True, "EMERGENCY_DE_RISK_ONLY")
        return IntraWindowAuthorityAssessment(False, "SAFETY_SYSTEM_CANNOT_INCREASE_EXPOSURE")

    return IntraWindowAuthorityAssessment(False, "UNKNOWN_ACTOR")


def evaluate_forecast_outcome(
    forecast: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate objective direction/target/MFE/MAE facts for Stage-A forecasts."""

    assessment = assess_forecast_semantics(forecast)
    if not assessment.ready:
        raise ScheduledStrategyError("forecast:SEMANTICS_NOT_READY")
    if outcome.get("schema_id") != FORECAST_OUTCOME_SCHEMA_ID or outcome.get("schema_version") != FORECAST_OUTCOME_SCHEMA_VERSION:
        raise ScheduledStrategyError("outcome:IDENTITY_INVALID")
    refs = outcome.get("source_refs")
    if not isinstance(refs, (list, tuple)) or not refs or not all(isinstance(item, str) and item.strip() for item in refs):
        raise ScheduledStrategyError("outcome.source_refs:NONEMPTY_VALID_REFS_REQUIRED")
    errors: list[str] = []
    reference = _decimal(outcome.get("reference_price"), field="outcome.reference_price", errors=errors)
    horizons = _mapping(outcome.get("horizons"), field="outcome.horizons", errors=errors)
    if reference is None or horizons is None or errors:
        raise ScheduledStrategyError("outcome:INVALID:" + ",".join(errors))

    results: dict[str, Any] = {}
    for name in FORECAST_HORIZONS:
        observed = _mapping(horizons.get(name), field=f"outcome.horizons.{name}", errors=errors)
        if observed is None:
            continue
        close = _decimal(observed.get("close"), field=f"outcome.horizons.{name}.close", errors=errors)
        high = _decimal(observed.get("high"), field=f"outcome.horizons.{name}.high", errors=errors)
        low = _decimal(observed.get("low"), field=f"outcome.horizons.{name}.low", errors=errors)
        if any(value is None for value in (close, high, low)):
            continue
        assert close is not None and high is not None and low is not None
        if low > high or not low <= close <= high:
            errors.append(f"outcome.horizons.{name}:OHLC_RANGE_INVALID")
            continue
        observed_direction = "UP" if close > reference else "DOWN" if close < reference else "FLAT"
        expected = forecast["horizons"][name]["expected_direction"]
        direction_match = "UNKNOWN" if expected in {"MIXED", "UNKNOWN"} else ("MATCH" if expected == observed_direction else "MISS")
        target_lower = Decimal(forecast["horizons"][name]["target_lower"])
        target_upper = Decimal(forecast["horizons"][name]["target_upper"])
        target_touched = not (high < target_lower or low > target_upper)
        if expected == "UP":
            mfe = high - reference
            mae = reference - low
        elif expected == "DOWN":
            mfe = reference - low
            mae = high - reference
        else:
            mfe = None
            mae = None
        results[name] = {
            "expected_direction": expected,
            "observed_direction": observed_direction,
            "direction_match": direction_match,
            "target_touched": target_touched,
            "mfe": None if mfe is None else format(mfe, "f"),
            "mae": None if mae is None else format(mae, "f"),
            "close": format(close, "f"),
            "high": format(high, "f"),
            "low": format(low, "f"),
        }
    if errors:
        raise ScheduledStrategyError("outcome:INVALID:" + ",".join(errors))
    return {
        "schema_id": "agent-trade-emotion.v340-forecast-evaluation",
        "schema_version": "1.0.0",
        "results": results,
    }


__all__ = [
    "COMMITTEE_HOURS_UTC",
    "COMMITTEE_INTERVAL_HOURS",
    "DEFAULT_CONTEXT_MAX_UTF8_BYTES",
    "FORECAST_DIRECTIONS",
    "FORECAST_HORIZONS",
    "FORECAST_OUTCOME_SCHEMA_ID",
    "FORECAST_OUTCOME_SCHEMA_VERSION",
    "FORECAST_SCHEMA_ID",
    "FORECAST_SCHEMA_VERSION",
    "ForecastSemanticAssessment",
    "IntraWindowAuthorityAssessment",
    "LOW_TOKEN_CONTEXT_SCHEMA_ID",
    "LOW_TOKEN_CONTEXT_SCHEMA_VERSION",
    "MIN_DECISION_HORIZON_HOURS",
    "SCHEDULED_TIMEFRAME_AUTHORITIES",
    "STATE_CHANGES",
    "V340_THEORY_IDENTITY",
    "V340_THEORY_MANIFEST_SHA256",
    "V340_THEORY_REVISION",
    "ScheduledStrategyError",
    "assess_forecast_semantics",
    "assess_intra_window_authority",
    "build_low_token_context",
    "verify_low_token_context",
    "evaluate_forecast_outcome",
    "next_committee_at",
    "require_committee_slot",
]
