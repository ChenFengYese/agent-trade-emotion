"""Pure V3.4 strategic-semantics checks and deterministic payoff calculations.

The Agent remains the market-decision owner.  This module never chooses a
market direction or action.  It answers a narrower question: has an Agent-
authored decision resolved the semantics and arithmetic required before a
future runtime is allowed to *increase* local-paper exposure?

A decision that is not ready remains valid research text.  Admission failure
must never rewrite the decision into WAIT or manufacture missing semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from types import MappingProxyType
from typing import Any, Mapping


STRATEGIC_SEMANTICS_SCHEMA_ID = "agent-trade-emotion.v340-strategic-semantics"
STRATEGIC_SEMANTICS_SCHEMA_VERSION = "1.1.0"

STRATEGIC_ACTIONS = frozenset(
    {"WAIT", "HOLD", "OPEN", "ADD", "REDUCE", "HARVEST", "EXIT", "REENTER"}
)
ACTION_COMPARISON_REQUIRED = (
    "WAIT",
    "HOLD",
    "ADD",
    "REDUCE",
    "HARVEST",
    "EXIT",
)
TIMEFRAME_AUTHORITIES = MappingProxyType(
    {
        "15m": "EVIDENCE",
        "1h": "EVIDENCE",
        "4h": "DECISION",
        "1d": "REGIME",
    }
)
MANAGEMENT_RESPONSES = frozenset(
    {
        "WAIT",
        "HOLD",
        "FREEZE_ADD",
        "ADD",
        "REDUCE",
        "HARVEST",
        "EXIT_TACTICAL",
        "EXIT_CORE",
        "EXIT_ALL",
        "REVIEW",
        "REBUILD",
    }
)
_EXPOSURE_INCREASING = frozenset({"OPEN", "ADD", "REENTER"})
_POSITION_ACTIONS = frozenset({"HOLD", "ADD", "REDUCE", "HARVEST", "EXIT", "REENTER"})
_POSITION_ROLES = frozenset({"CASH", "CORE", "TACTICAL", "PROBE", "RUNNER", "HEDGE"})
_PAYOFF_SIDES = frozenset({"LONG", "SHORT"})
_ACTIVITY_WEIGHTS = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})


@dataclass(frozen=True, slots=True)
class StrategicSemanticAssessment:
    status: str
    errors: tuple[str, ...]
    metrics: Mapping[str, str]

    @property
    def ready(self) -> bool:
        return self.status == "STRATEGIC_SEMANTICS_READY"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "errors": list(self.errors),
            "metrics": dict(self.metrics),
        }


def _nonempty_text(value: object, *, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field}:REQUIRED_NONEMPTY_TEXT")
        return None
    return value.strip()


def _mapping(value: object, *, field: str, errors: list[str]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        errors.append(f"{field}:REQUIRED_OBJECT")
        return None
    return value


def _decimal(value: object, *, field: str, errors: list[str], nonnegative: bool = False) -> Decimal | None:
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
    if nonnegative and parsed < 0:
        errors.append(f"{field}:MUST_BE_NONNEGATIVE")
        return None
    return parsed


def _text_list(
    value: object,
    *,
    field: str,
    errors: list[str],
    minimum: int = 1,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        errors.append(f"{field}:REQUIRED_TEXT_ARRAY")
        return ()
    normalized = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(normalized) != len(value) or len(normalized) < minimum:
        errors.append(f"{field}:INSUFFICIENT_OR_INVALID_TEXT_ITEMS")
    return normalized


def _ratio(numerator: Decimal, denominator: Decimal) -> str:
    if denominator <= 0:
        return "UNDEFINED"
    return format(
        (numerator / denominator).quantize(Decimal("0.000001"), rounding=ROUND_DOWN),
        "f",
    )


def _assess_timeframes(payload: Mapping[str, Any], *, errors: list[str]) -> None:
    zones = _mapping(payload.get("timeframe_zones"), field="timeframe_zones", errors=errors)
    if zones is None:
        return
    for timeframe, expected_role in TIMEFRAME_AUTHORITIES.items():
        zone = _mapping(zones.get(timeframe), field=f"timeframe_zones.{timeframe}", errors=errors)
        if zone is None:
            continue
        lower = _decimal(zone.get("lower"), field=f"timeframe_zones.{timeframe}.lower", errors=errors)
        upper = _decimal(zone.get("upper"), field=f"timeframe_zones.{timeframe}.upper", errors=errors)
        if lower is not None and upper is not None and not lower < upper:
            errors.append(f"timeframe_zones.{timeframe}:LOWER_MUST_BE_BELOW_UPPER")
        if zone.get("authority") != expected_role:
            errors.append(
                f"timeframe_zones.{timeframe}.authority:EXPECTED_{expected_role}"
            )
        _nonempty_text(zone.get("meaning"), field=f"timeframe_zones.{timeframe}.meaning", errors=errors)
        _nonempty_text(
            zone.get("break_effect"),
            field=f"timeframe_zones.{timeframe}.break_effect",
            errors=errors,
        )


def _assess_action_comparison(payload: Mapping[str, Any], *, errors: list[str]) -> None:
    comparison = _mapping(payload.get("action_comparison"), field="action_comparison", errors=errors)
    if comparison is None:
        return
    for action in ACTION_COMPARISON_REQUIRED:
        _nonempty_text(
            comparison.get(action),
            field=f"action_comparison.{action}",
            errors=errors,
        )


def _assess_management_matrix(
    payload: Mapping[str, Any],
    *,
    position_role: str | None,
    errors: list[str],
) -> None:
    matrix = _mapping(payload.get("management_matrix"), field="management_matrix", errors=errors)
    if matrix is None:
        return
    for timeframe in TIMEFRAME_AUTHORITIES:
        item = _mapping(matrix.get(timeframe), field=f"management_matrix.{timeframe}", errors=errors)
        if item is None:
            continue
        response = item.get("response")
        emergency = item.get("emergency")
        if response not in MANAGEMENT_RESPONSES:
            errors.append(f"management_matrix.{timeframe}.response:UNSUPPORTED")
        if type(emergency) is not bool:
            errors.append(f"management_matrix.{timeframe}.emergency:REQUIRED_BOOLEAN")
            emergency = False
        _nonempty_text(item.get("reason"), field=f"management_matrix.{timeframe}.reason", errors=errors)
        _nonempty_text(
            item.get("size_effect"),
            field=f"management_matrix.{timeframe}.size_effect",
            errors=errors,
        )
        _nonempty_text(
            item.get("risk_if_waiting"),
            field=f"management_matrix.{timeframe}.risk_if_waiting",
            errors=errors,
        )
        if (
            timeframe in {"15m", "1h"}
            and position_role == "CORE"
            and response in {"EXIT_CORE", "EXIT_ALL"}
            and emergency is not True
        ):
            errors.append(
                f"management_matrix.{timeframe}:CORE_EXIT_REQUIRES_EMERGENCY_OR_4H_COMMITTEE"
            )



def _assess_position_plan(payload: Mapping[str, Any], *, require_plan: bool, errors: list[str]) -> dict[str, str]:
    metrics: dict[str, str] = {}
    raw = payload.get("position_plan")
    if raw is None and not require_plan:
        return metrics
    plan = _mapping(raw, field="position_plan", errors=errors)
    if plan is None:
        return metrics

    if plan.get("plan_revision_policy") != "FROZEN_UNTIL_NEXT_4H_COMMITTEE":
        errors.append(
            "position_plan.plan_revision_policy:EXPECTED_FROZEN_UNTIL_NEXT_4H_COMMITTEE"
        )
    _nonempty_text(
        plan.get("intra_window_execution_policy"),
        field="position_plan.intra_window_execution_policy",
        errors=errors,
    )
    for action in ("add", "reduce", "harvest"):
        _nonempty_text(
            plan.get(f"{action}_condition"),
            field=f"position_plan.{action}_condition",
            errors=errors,
        )
    add_quantity = _decimal(
        plan.get("add_quantity"),
        field="position_plan.add_quantity",
        errors=errors,
        nonnegative=True,
    )
    reduce_quantity = _decimal(
        plan.get("reduce_quantity"),
        field="position_plan.reduce_quantity",
        errors=errors,
        nonnegative=True,
    )
    harvest_quantity = _decimal(
        plan.get("harvest_quantity"),
        field="position_plan.harvest_quantity",
        errors=errors,
        nonnegative=True,
    )
    runner_quantity = _decimal(
        plan.get("runner_quantity"),
        field="position_plan.runner_quantity",
        errors=errors,
        nonnegative=True,
    )
    for name, value in (
        ("add_quantity", add_quantity),
        ("reduce_quantity", reduce_quantity),
        ("harvest_quantity", harvest_quantity),
        ("runner_quantity", runner_quantity),
    ):
        if value is not None:
            metrics[name] = format(value, "f")
    return metrics


def _assess_attention(payload: Mapping[str, Any], *, errors: list[str]) -> None:
    attention = _mapping(payload.get("attention"), field="attention", errors=errors)
    if attention is None:
        return
    if attention.get("scheduler_policy") != "FIXED_4H_UTC":
        errors.append("attention.scheduler_policy:EXPECTED_FIXED_4H_UTC")
    _nonempty_text(
        attention.get("next_observation"),
        field="attention.next_observation",
        errors=errors,
    )
    _text_list(
        attention.get("high_value_windows"),
        field="attention.high_value_windows",
        errors=errors,
        minimum=1,
    )
    _text_list(
        attention.get("low_value_conditions"),
        field="attention.low_value_conditions",
        errors=errors,
        minimum=1,
    )
    activity = attention.get("activity_windows")
    if not isinstance(activity, (list, tuple)) or not activity:
        errors.append("attention.activity_windows:REQUIRED_NONEMPTY_ARRAY")
        return
    for index, item in enumerate(activity):
        row = _mapping(item, field=f"attention.activity_windows.{index}", errors=errors)
        if row is None:
            continue
        _nonempty_text(
            row.get("window"),
            field=f"attention.activity_windows.{index}.window",
            errors=errors,
        )
        if row.get("weight") not in _ACTIVITY_WEIGHTS:
            errors.append(
                f"attention.activity_windows.{index}.weight:HIGH_MEDIUM_LOW_OR_UNKNOWN_REQUIRED"
            )
        _nonempty_text(
            row.get("basis"),
            field=f"attention.activity_windows.{index}.basis",
            errors=errors,
        )

def _assess_pnl(payload: Mapping[str, Any], *, action: str | None, errors: list[str]) -> dict[str, str]:
    metrics: dict[str, str] = {}
    pnl = _mapping(payload.get("pnl"), field="pnl", errors=errors)
    if pnl is None:
        return metrics
    realized = _decimal(pnl.get("realized"), field="pnl.realized", errors=errors)
    unrealized = _decimal(pnl.get("unrealized"), field="pnl.unrealized", errors=errors)
    if realized is not None:
        metrics["realized_pnl"] = format(realized, "f")
    if unrealized is not None:
        metrics["unrealized_pnl"] = format(unrealized, "f")
    if realized is not None and unrealized is not None:
        metrics["marked_pnl"] = format(realized + unrealized, "f")
    if action in _POSITION_ACTIONS:
        _nonempty_text(
            pnl.get("realization_effect_of_selected_action"),
            field="pnl.realization_effect_of_selected_action",
            errors=errors,
        )
    return metrics


def _assess_payoff(
    payload: Mapping[str, Any],
    *,
    require_payoff: bool,
    errors: list[str],
) -> dict[str, str]:
    metrics: dict[str, str] = {}
    raw = payload.get("payoff")
    if raw is None and not require_payoff:
        return metrics
    payoff = _mapping(raw, field="payoff", errors=errors)
    if payoff is None:
        return metrics
    side = payoff.get("side")
    if side not in _PAYOFF_SIDES:
        errors.append("payoff.side:LONG_OR_SHORT_REQUIRED")
        side = None
    entry = _decimal(payoff.get("entry_price"), field="payoff.entry_price", errors=errors, nonnegative=True)
    invalidation = _decimal(
        payoff.get("strategic_invalidation_price"),
        field="payoff.strategic_invalidation_price",
        errors=errors,
        nonnegative=True,
    )
    catastrophic = _decimal(
        payoff.get("catastrophic_protection_price"),
        field="payoff.catastrophic_protection_price",
        errors=errors,
        nonnegative=True,
    )
    next_committee_adverse = _decimal(
        payoff.get("maximum_adverse_price_before_next_committee"),
        field="payoff.maximum_adverse_price_before_next_committee",
        errors=errors,
        nonnegative=True,
    )
    target = _decimal(
        payoff.get("primary_target_price"),
        field="payoff.primary_target_price",
        errors=errors,
        nonnegative=True,
    )
    quantity = _decimal(payoff.get("quantity"), field="payoff.quantity", errors=errors, nonnegative=True)
    multiplier = _decimal(
        payoff.get("contract_multiplier"),
        field="payoff.contract_multiplier",
        errors=errors,
        nonnegative=True,
    )
    cost = _decimal(
        payoff.get("round_trip_cost_stress"),
        field="payoff.round_trip_cost_stress",
        errors=errors,
        nonnegative=True,
    )
    gap_impact = _decimal(
        payoff.get("gap_impact_stress"),
        field="payoff.gap_impact_stress",
        errors=errors,
        nonnegative=True,
    )
    risk_budget = _decimal(
        payoff.get("maximum_loss_budget"),
        field="payoff.maximum_loss_budget",
        errors=errors,
        nonnegative=True,
    )
    values = (
        entry,
        invalidation,
        catastrophic,
        next_committee_adverse,
        target,
        quantity,
        multiplier,
        cost,
        gap_impact,
        risk_budget,
    )
    if any(value is None for value in values) or side is None:
        return metrics
    assert entry is not None and invalidation is not None and catastrophic is not None
    assert next_committee_adverse is not None and target is not None
    assert quantity is not None and multiplier is not None and cost is not None
    assert gap_impact is not None and risk_budget is not None
    if quantity <= 0:
        errors.append("payoff.quantity:MUST_BE_POSITIVE")
    if multiplier <= 0:
        errors.append("payoff.contract_multiplier:MUST_BE_POSITIVE")
    if side == "LONG":
        if not (catastrophic <= invalidation < entry < target):
            errors.append(
                "payoff:LONG_GEOMETRY_MUST_BE_CATASTROPHIC_LE_INVALIDATION_LT_ENTRY_LT_TARGET"
            )
        if not (catastrophic <= next_committee_adverse < entry):
            errors.append(
                "payoff:LONG_NEXT_COMMITTEE_ADVERSE_MUST_BE_WITHIN_CATASTROPHIC_AND_ENTRY"
            )
    if side == "SHORT":
        if not (target < entry < invalidation <= catastrophic):
            errors.append(
                "payoff:SHORT_GEOMETRY_MUST_BE_TARGET_LT_ENTRY_LT_INVALIDATION_LE_CATASTROPHIC"
            )
        if not (entry < next_committee_adverse <= catastrophic):
            errors.append(
                "payoff:SHORT_NEXT_COMMITTEE_ADVERSE_MUST_BE_WITHIN_ENTRY_AND_CATASTROPHIC"
            )
    gross_risk = abs(entry - invalidation) * quantity * multiplier
    gross_reward = abs(target - entry) * quantity * multiplier
    strategic_net_risk = gross_risk + cost + gap_impact
    catastrophic_risk = abs(entry - catastrophic) * quantity * multiplier + cost + gap_impact
    wait_to_committee_risk = abs(entry - next_committee_adverse) * quantity * multiplier + cost + gap_impact
    net_reward = gross_reward - cost
    metrics.update(
        {
            "payoff_quantity": format(quantity, "f"),
            "gross_risk": format(gross_risk, "f"),
            "gross_reward": format(gross_reward, "f"),
            "strategic_net_risk_stress": format(strategic_net_risk, "f"),
            "catastrophic_risk_stress": format(catastrophic_risk, "f"),
            "wait_to_next_committee_risk_stress": format(wait_to_committee_risk, "f"),
            "net_reward_reference": format(net_reward, "f"),
            "reward_risk_ratio": _ratio(net_reward, strategic_net_risk),
            "maximum_loss_budget": format(risk_budget, "f"),
        }
    )
    if net_reward <= 0:
        errors.append("payoff:NET_REWARD_MUST_BE_POSITIVE")
    if strategic_net_risk > risk_budget:
        errors.append("payoff:STRATEGIC_NET_RISK_EXCEEDS_MAXIMUM_LOSS_BUDGET")
    if catastrophic_risk > risk_budget:
        errors.append("payoff:CATASTROPHIC_RISK_EXCEEDS_MAXIMUM_LOSS_BUDGET")
    if wait_to_committee_risk > risk_budget:
        errors.append("payoff:WAIT_TO_NEXT_COMMITTEE_RISK_EXCEEDS_MAXIMUM_LOSS_BUDGET")
    return metrics


def assess_strategic_semantics(payload: Mapping[str, Any]) -> StrategicSemanticAssessment:
    """Assess one Agent-authored V3.4 strategic companion object.

    The returned ``SEMANTICS_NOT_READY`` status is a trade-admission result,
    never a rejection of the Agent's original research decision.
    """

    errors: list[str] = []
    metrics: dict[str, str] = {}
    if not isinstance(payload, Mapping):
        return StrategicSemanticAssessment(
            status="SEMANTICS_NOT_READY",
            errors=("payload:REQUIRED_OBJECT",),
            metrics=MappingProxyType({}),
        )
    if payload.get("schema_id") != STRATEGIC_SEMANTICS_SCHEMA_ID:
        errors.append("schema_id:UNEXPECTED")
    if payload.get("schema_version") != STRATEGIC_SEMANTICS_SCHEMA_VERSION:
        errors.append("schema_version:UNEXPECTED")

    horizon = payload.get("strategic_horizon_hours")
    if type(horizon) is not int or horizon < 4:
        errors.append("strategic_horizon_hours:MUST_BE_INTEGER_AT_LEAST_4")

    action = payload.get("action")
    if action not in STRATEGIC_ACTIONS:
        errors.append("action:UNSUPPORTED")
        action = None
    position_role = payload.get("position_role")
    if position_role not in _POSITION_ROLES:
        errors.append("position_role:UNSUPPORTED")
        position_role = None

    for field in (
        "trend_phase",
        "causal_thesis",
        "alternative_thesis",
        "catalyst_analysis",
        "sentiment_analysis",
        "data_quality_analysis",
        "future_space_analysis",
    ):
        _nonempty_text(payload.get(field), field=field, errors=errors)
    _text_list(payload.get("if_then_paths"), field="if_then_paths", errors=errors, minimum=2)
    _text_list(
        payload.get("participant_analysis"),
        field="participant_analysis",
        errors=errors,
        minimum=1,
    )
    _text_list(payload.get("data_conflicts"), field="data_conflicts", errors=errors, minimum=1)

    _assess_timeframes(payload, errors=errors)
    _assess_action_comparison(payload, errors=errors)
    _assess_management_matrix(payload, position_role=position_role, errors=errors)
    metrics.update(_assess_pnl(payload, action=action, errors=errors))
    _assess_attention(payload, errors=errors)

    require_payoff = action in _EXPOSURE_INCREASING or (
        action in _POSITION_ACTIONS and position_role not in {None, "CASH"}
    )
    metrics.update(_assess_payoff(payload, require_payoff=require_payoff, errors=errors))
    metrics.update(_assess_position_plan(payload, require_plan=require_payoff, errors=errors))

    payoff_quantity = metrics.get("payoff_quantity")
    if payoff_quantity is not None:
        current_quantity = Decimal(payoff_quantity)
        for metric_name in ("reduce_quantity", "harvest_quantity", "runner_quantity"):
            raw_quantity = metrics.get(metric_name)
            if raw_quantity is not None and Decimal(raw_quantity) > current_quantity:
                errors.append(f"position_plan.{metric_name}:CANNOT_EXCEED_PAYOFF_QUANTITY")

    # Increasing exposure while claiming CASH is semantically inconsistent.
    if action in _EXPOSURE_INCREASING and position_role == "CASH":
        errors.append("position_role:CASH_CANNOT_OWN_EXPOSURE_INCREASING_ACTION")

    status = "STRATEGIC_SEMANTICS_READY" if not errors else "SEMANTICS_NOT_READY"
    return StrategicSemanticAssessment(
        status=status,
        errors=tuple(errors),
        metrics=MappingProxyType(dict(sorted(metrics.items()))),
    )


__all__ = [
    "ACTION_COMPARISON_REQUIRED",
    "MANAGEMENT_RESPONSES",
    "STRATEGIC_ACTIONS",
    "STRATEGIC_SEMANTICS_SCHEMA_ID",
    "STRATEGIC_SEMANTICS_SCHEMA_VERSION",
    "StrategicSemanticAssessment",
    "TIMEFRAME_AUTHORITIES",
    "assess_strategic_semantics",
]
