"""Create one terminal outcome from the preregistered public mark-price window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ...domain.market_cycle.contracts import ArtifactRef, BehaviorPlan, Outcome
from ...domain.market_cycle.theory import V332_THEORY_IDENTITY
from .ports import ClockPort, OutcomeObservation, OutcomePort, OutcomeRequest


class MarketCycleOutcomeError(ValueError):
    """An outcome adapter returned a structurally unsafe observation."""


def _v332_censored_path(
    plan: BehaviorPlan,
    observation: OutcomeObservation,
) -> dict[str, object]:
    """Keep the preregistered V3.3.2 path explicit when capture is absent."""

    start = datetime.fromisoformat(plan.agent_delivered_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(plan.outcome_due_at.replace("Z", "+00:00"))
    interval = timedelta(minutes=15)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    first_open = epoch + (
        ((start - epoch) + interval - timedelta(microseconds=1)) // interval
    ) * interval
    expected_count = max(0, (end - first_open) // interval)
    return {
        "schema_id": "agent_trade_emotion_v332_ordered_outcome_path",
        "schema_version": "1.0.0",
        "status": "CENSORED",
        "path_start_at": plan.agent_delivered_at,
        "path_end_at": plan.outcome_due_at,
        "interval": "15m",
        "intrabar_order": "UNRESOLVED_WITHIN_BAR",
        "points": [],
        "coverage": {
            "expected_point_count": expected_count,
            "observed_point_count": 0,
            "gap_count": expected_count,
            "covers_all_closed_intervals": False,
        },
        "missing_reason": (
            observation.missing_reason or "ORDERED_PATH_CAPTURE_UNAVAILABLE"
        ),
        "source_health": list(observation.source_health),
    }


def _terminal_outcome(
    plan: BehaviorPlan,
    plan_ref: ArtifactRef,
    observation: OutcomeObservation,
    *,
    clock: ClockPort,
    sealed_at: str | None = None,
) -> Outcome:
    status = observation.terminal_status
    if status not in {"OBSERVED", "MISSING"}:
        raise MarketCycleOutcomeError(f"unsupported terminal outcome status: {status}")
    raw_ref_values = []
    if observation.raw_ref is not None:
        raw_ref_values.append(observation.raw_ref)
    raw_ref_values.extend(observation.additional_raw_refs)
    raw_refs_list: list[ArtifactRef] = []
    raw_hashes: set[str] = set()
    for raw_ref_value in raw_ref_values:
        reference = ArtifactRef.from_dict(raw_ref_value)
        if reference.sha256 not in raw_hashes:
            raw_refs_list.append(reference)
            raw_hashes.add(reference.sha256)
    raw_refs = tuple(raw_refs_list)
    if status == "OBSERVED":
        if (
            observation.value is None
            or observation.unit is None
            or observation.effective_at is None
            or observation.available_at is None
            or not raw_refs
        ):
            raise MarketCycleOutcomeError(
                "observed outcome lacks value, timing, unit or raw ref"
            )
        endpoint = {
            "value": observation.value,
            "unit": observation.unit,
            "price_field": "MARK_PRICE",
            "effective_at": observation.effective_at,
            "available_at": observation.available_at,
            "raw_sha256": raw_refs[0].sha256,
        }
        terminal_status = "OBSERVED"
        typed_missing = None
    else:
        endpoint = None
        terminal_status = "TYPED_MISSING"
        typed_missing = observation.missing_reason or "UNKNOWN_COVERAGE_LOSS"
    return Outcome(
        outcome_id=f"{plan.cycle_id}.outcome",
        cycle_id=plan.cycle_id,
        behavior_plan_ref=plan_ref,
        due_at=plan.outcome_due_at,
        tolerance_seconds=plan.outcome_tolerance_seconds,
        observed_at=observation.observed_at,
        sealed_at=sealed_at or clock(),
        terminal_status=terminal_status,
        endpoint_observation=endpoint,
        typed_missing=typed_missing,
        path_observations=(
            _v332_censored_path(plan, observation)
            if observation.path_observations is None
            and plan.theory_identity == V332_THEORY_IDENTITY
            else {"source_health": list(observation.source_health)}
            if observation.path_observations is None
            else {
                **dict(observation.path_observations),
                "source_health": list(observation.source_health),
            }
        ),
        raw_refs=raw_refs,
        theory_identity=plan.theory_identity,
    )


def capture_outcome(
    plan: BehaviorPlan,
    plan_ref: ArtifactRef,
    *,
    venue_id: str,
    instrument_id: str,
    outcome_port: OutcomePort,
    clock: ClockPort,
) -> Outcome | None:
    """Return ``None`` while not due, otherwise seal observed or typed missing."""

    observation = outcome_port.observe(
        OutcomeRequest(
            cycle_id=plan.cycle_id,
            venue_id=venue_id,
            instrument_id=instrument_id,
            price_field="MARK_PRICE",
            due_at=plan.outcome_due_at,
            tolerance_seconds=plan.outcome_tolerance_seconds,
            path_start_at=(
                plan.agent_delivered_at
                if plan.theory_identity == V332_THEORY_IDENTITY
                else None
            ),
        )
    )
    if observation.terminal_status == "PENDING":
        return None
    return _terminal_outcome(plan, plan_ref, observation, clock=clock)


__all__ = [
    "MarketCycleOutcomeError",
    "capture_outcome",
]
