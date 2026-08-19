"""V3.4 scheduled FORECAST_ONLY qualification service.

This is deliberately not a trading runtime.  It accepts already-admitted PIT
summaries, builds one bounded 4H committee context, seals the Agent's forecast,
and later seals objective outcome/evaluation facts.  It never collects market
or account data and never creates paper/testnet/live orders.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any, Mapping, Sequence

from ...domain.contracts.canonical import canonical_bytes
from ...domain.market_cycle.scheduled_strategy import (
    DEFAULT_CONTEXT_MAX_UTF8_BYTES,
    MIN_DECISION_HORIZON_HOURS,
    ScheduledStrategyError,
    assess_forecast_semantics,
    build_low_token_context,
    evaluate_forecast_outcome,
    next_committee_at,
    require_committee_slot,
    verify_low_token_context,
)


_FORECAST_RECORD_SCHEMA_ID = "agent-trade-emotion.v340-forecast-record"
_FORECAST_RECORD_SCHEMA_VERSION = "1.0.0"
_OUTCOME_RECORD_SCHEMA_ID = "agent-trade-emotion.v340-forecast-outcome-record"
_OUTCOME_RECORD_SCHEMA_VERSION = "1.0.0"
_EVALUATION_RECORD_SCHEMA_ID = "agent-trade-emotion.v340-forecast-evaluation-record"
_EVALUATION_RECORD_SCHEMA_VERSION = "1.0.0"
_MAX_AGENT_TEXT_BYTES = 256 * 1024


class ForecastQualificationError(ValueError):
    """The V3.4 forecast-only qualification contract was violated."""


def _parse(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ForecastQualificationError(f"{field}:REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForecastQualificationError(f"{field}:INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ForecastQualificationError(f"{field}:UTC_OFFSET_REQUIRED")
    return parsed.astimezone(UTC)


def _decimal_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForecastQualificationError(f"{field}:REQUIRED_DECIMAL_STRING")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ForecastQualificationError(f"{field}:INVALID_DECIMAL") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ForecastQualificationError(f"{field}:MUST_BE_POSITIVE_FINITE")
    return format(parsed, "f")


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(value))).hexdigest()


def _model_usage(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {"status": "UNKNOWN"}
    if not isinstance(value, Mapping):
        raise ForecastQualificationError("model_usage:INVALID")
    status = value.get("status")
    if status == "UNKNOWN":
        return {"status": "UNKNOWN"}
    if status not in (None, "OBSERVED"):
        raise ForecastQualificationError("model_usage.status:EXPECTED_OBSERVED_OR_UNKNOWN")
    model_id = value.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ForecastQualificationError("model_usage.model_id:REQUIRED")
    usage_ref = value.get("source_ref")
    if not isinstance(usage_ref, str) or not usage_ref.strip():
        raise ForecastQualificationError("model_usage.source_ref:REQUIRED")
    result: dict[str, Any] = {"status": "OBSERVED", "model_id": model_id.strip(), "source_ref": usage_ref.strip()}
    total = 0
    for field in ("input_tokens", "output_tokens", "cached_input_tokens"):
        raw = value.get(field, 0 if field == "cached_input_tokens" else None)
        if type(raw) is not int or raw < 0:
            raise ForecastQualificationError(f"model_usage.{field}:NONNEGATIVE_INTEGER_REQUIRED")
        result[field] = raw
        if field != "cached_input_tokens":
            total += raw
    result["total_tokens"] = total
    return result


class V340ForecastQualificationService:
    """One bounded scheduled cognition cycle per asset per fixed 4H UTC slot."""

    def __init__(self, repository: object, *, context_max_utf8_bytes: int = DEFAULT_CONTEXT_MAX_UTF8_BYTES) -> None:
        required = ("latest_forecast", "seal_forecast", "load_forecast", "seal_outcome", "seal_evaluation")
        if any(not callable(getattr(repository, name, None)) for name in required):
            raise ForecastQualificationError("repository:INVALID")
        self._repository = repository
        self._context_max_utf8_bytes = context_max_utf8_bytes

    @staticmethod
    def _previous_summary(previous: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
        if previous is None:
            return None
        forecast = previous.get("forecast")
        if not isinstance(forecast, Mapping):
            raise ForecastQualificationError("previous_state:FORECAST_INVALID")
        return {
            "committee_slot_at": previous.get("committee_slot_at"),
            "record_sha256": previous.get("record_sha256") or _sha(previous),
            "state_change": forecast.get("state_change"),
            "directional_bias": forecast.get("directional_bias"),
            "trend_phase": forecast.get("trend_phase"),
            "causal_thesis": forecast.get("causal_thesis"),
            "alternative_thesis": forecast.get("alternative_thesis"),
            "if_then_paths": forecast.get("if_then_paths"),
            "participant_analysis": forecast.get("participant_analysis"),
            "catalyst_analysis": forecast.get("catalyst_analysis"),
            "sentiment_analysis": forecast.get("sentiment_analysis"),
            "data_quality_analysis": forecast.get("data_quality_analysis"),
            "data_conflicts": forecast.get("data_conflicts"),
            "future_space_analysis": forecast.get("future_space_analysis"),
            "timeframe_zones": forecast.get("timeframe_zones"),
            "horizons": forecast.get("horizons"),
            "next_discriminating_observation": forecast.get("next_discriminating_observation"),
        }

    def build_context(
        self,
        *,
        asset_id: str,
        committee_slot_at: str,
        input_cutoff_at: str,
        reference_price: str,
        theory_identity: str,
        shared_context_summary: Mapping[str, Any],
        asset_delta_summary: Mapping[str, Any],
        portfolio_summary: Mapping[str, Any],
        source_refs: Sequence[str],
    ) -> dict[str, Any]:
        try:
            slot = require_committee_slot(committee_slot_at)
        except ScheduledStrategyError as exc:
            raise ForecastQualificationError(str(exc)) from exc
        previous = self._repository.latest_forecast(asset_id)
        if previous is not None:
            previous_at = _parse(str(previous.get("committee_slot_at")), field="previous.committee_slot_at")
            current_at = _parse(slot, field="committee_slot_at")
            if previous_at >= current_at:
                raise ForecastQualificationError("committee_slot_at:NOT_AFTER_LATEST_STATE")
            if current_at - previous_at < timedelta(hours=MIN_DECISION_HORIZON_HOURS):
                raise ForecastQualificationError("committee_slot_at:MINIMUM_4H_INTERVAL_VIOLATED")
        try:
            return build_low_token_context(
                asset_id=asset_id,
                committee_slot_at=slot,
                input_cutoff_at=input_cutoff_at,
                reference_price=reference_price,
                theory_identity=theory_identity,
                shared_context_summary=shared_context_summary,
                asset_delta_summary=asset_delta_summary,
                portfolio_summary=portfolio_summary,
                previous_state_summary=self._previous_summary(previous),
                source_refs=source_refs,
                max_utf8_bytes=self._context_max_utf8_bytes,
            )
        except ScheduledStrategyError as exc:
            raise ForecastQualificationError(str(exc)) from exc

    def seal_forecast(
        self,
        *,
        asset_id: str,
        context: Mapping[str, Any],
        agent_text: str,
        forecast: Mapping[str, Any],
        model_usage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(context, Mapping) or context.get("mode") != "FORECAST_ONLY":
            raise ForecastQualificationError("context:INVALID")
        try:
            verify_low_token_context(context)
        except ScheduledStrategyError as exc:
            raise ForecastQualificationError(str(exc)) from exc
        if context.get("asset_id") != asset_id:
            raise ForecastQualificationError("context:ASSET_ID_MISMATCH")
        slot = require_committee_slot(str(context.get("committee_slot_at")))
        if context.get("next_committee_at") != next_committee_at(slot):
            raise ForecastQualificationError("context:NEXT_COMMITTEE_MISMATCH")
        if not isinstance(agent_text, str) or not agent_text.strip():
            raise ForecastQualificationError("agent_text:REQUIRED")
        raw_agent = agent_text.encode("utf-8")
        if len(raw_agent) > _MAX_AGENT_TEXT_BYTES:
            raise ForecastQualificationError("agent_text:BYTE_LIMIT_EXCEEDED")
        assessment = assess_forecast_semantics(forecast)
        if not assessment.ready:
            raise ForecastQualificationError("forecast:SEMANTICS_NOT_READY:" + "|".join(assessment.errors))

        previous = self._repository.latest_forecast(asset_id)
        previous_ref = None
        if previous is None:
            if forecast.get("state_change") != "INITIALIZE":
                raise ForecastQualificationError("forecast.state_change:INITIAL_STATE_REQUIRES_INITIALIZE")
        else:
            if forecast.get("state_change") == "INITIALIZE":
                raise ForecastQualificationError("forecast.state_change:INITIALIZE_ONLY_FOR_FIRST_STATE")
            previous_slot = _parse(str(previous.get("committee_slot_at")), field="previous.committee_slot_at")
            current_slot = _parse(slot, field="committee_slot_at")
            if current_slot - previous_slot < timedelta(hours=MIN_DECISION_HORIZON_HOURS):
                raise ForecastQualificationError("forecast:MINIMUM_4H_STATE_INTERVAL_VIOLATED")
            previous_ref = {
                "committee_slot_at": previous.get("committee_slot_at"),
                "record_path": previous.get("record_path"),
                "record_sha256": previous.get("record_sha256") or _sha(previous),
            }

        record = {
            "schema_id": _FORECAST_RECORD_SCHEMA_ID,
            "schema_version": _FORECAST_RECORD_SCHEMA_VERSION,
            "mode": "FORECAST_ONLY",
            "asset_id": asset_id,
            "theory_identity": context.get("theory_identity"),
            "committee_slot_at": slot,
            "next_committee_at": next_committee_at(slot),
            "input_cutoff_at": context.get("input_cutoff_at"),
            "reference_price": _decimal_text(context.get("reference_price"), field="context.reference_price"),
            "context_sha256": context.get("context_sha256"),
            "context_size_bytes": context.get("context_size_bytes"),
            "previous_state_ref": previous_ref,
            "agent_text": agent_text,
            "agent_text_sha256": hashlib.sha256(raw_agent).hexdigest(),
            "model_usage": _model_usage(model_usage),
            "forecast": dict(forecast),
            "semantic_assessment": assessment.to_dict(),
            "execution_authority": "NONE",
        }
        self._repository.seal_forecast(asset_id, slot, record)
        return record

    def seal_outcome(
        self,
        *,
        asset_id: str,
        committee_slot_at: str,
        observed_through_at: str,
        outcome: Mapping[str, Any],
    ) -> dict[str, Any]:
        slot = require_committee_slot(committee_slot_at)
        forecast_record = self._repository.load_forecast(asset_id, slot)
        slot_dt = _parse(slot, field="committee_slot_at")
        observed = _parse(observed_through_at, field="observed_through_at")
        if observed < slot_dt + timedelta(hours=24):
            raise ForecastQualificationError("observed_through_at:FULL_24H_OUTCOME_REQUIRED")
        forecast = forecast_record.get("forecast")
        if not isinstance(forecast, Mapping):
            raise ForecastQualificationError("forecast_record:INVALID")
        outcome_reference = _decimal_text(outcome.get("reference_price"), field="outcome.reference_price")
        if outcome_reference != forecast_record.get("reference_price"):
            raise ForecastQualificationError("outcome.reference_price:FORECAST_REFERENCE_MISMATCH")
        horizons = outcome.get("horizons")
        if not isinstance(horizons, Mapping):
            raise ForecastQualificationError("outcome.horizons:REQUIRED")
        for name, hours in (("4h", 4), ("12h", 12), ("24h", 24)):
            item = horizons.get(name)
            if not isinstance(item, Mapping):
                raise ForecastQualificationError(f"outcome.horizons.{name}:REQUIRED")
            observed_at = _parse(str(item.get("observed_at")), field=f"outcome.horizons.{name}.observed_at")
            expected_at = slot_dt + timedelta(hours=hours)
            if observed_at != expected_at:
                raise ForecastQualificationError(f"outcome.horizons.{name}.observed_at:EXPECTED_EXACT_HORIZON")
        try:
            evaluation = evaluate_forecast_outcome(forecast, outcome)
        except ScheduledStrategyError as exc:
            raise ForecastQualificationError(str(exc)) from exc
        outcome_record = {
            "schema_id": _OUTCOME_RECORD_SCHEMA_ID,
            "schema_version": _OUTCOME_RECORD_SCHEMA_VERSION,
            "asset_id": asset_id,
            "committee_slot_at": slot,
            "observed_through_at": observed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "forecast_record_sha256": hashlib.sha256(canonical_bytes(forecast_record) + b"\n").hexdigest(),
            "outcome": dict(outcome),
            "execution_authority": "NONE",
        }
        evaluation_record = {
            "schema_id": _EVALUATION_RECORD_SCHEMA_ID,
            "schema_version": _EVALUATION_RECORD_SCHEMA_VERSION,
            "asset_id": asset_id,
            "committee_slot_at": slot,
            "forecast_record_sha256": outcome_record["forecast_record_sha256"],
            "evaluation": evaluation,
        }
        self._repository.seal_outcome(asset_id, slot, outcome_record)
        self._repository.seal_evaluation(asset_id, slot, evaluation_record)
        return evaluation_record


__all__ = ["ForecastQualificationError", "V340ForecastQualificationService"]
