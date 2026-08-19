"""Deterministic decision-time kernel for action-discrimination E0.

The kernel owns arithmetic, hard safety constraints and typed state.  It does
not infer market probabilities and it never selects between multiple admitted
actions.  That bounded residual choice is intentionally left to an Agent role.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Iterable, Mapping, Sequence

from ..contracts.canonical import canonical_digest, canonical_decimal
from .model import (
    ACTION_BY_ID,
    E0A_FINANCIAL_CONTRACT,
    E0B_FINANCIAL_CONTRACT,
    EXECUTION_AUTHORITY,
    PATH_SLOTS,
    SYSTEM_MODE,
    ActionDiscriminationError,
    ActionId,
    ProfileSpec,
    SupervisionMode,
)


ZERO = Decimal("0")
ONE = Decimal("1")
EQUITY = Decimal("10000")
CORE_FRACTION = Decimal("0.0625")
STAGE_FRACTION = Decimal("0.03125")
MAX_GROSS_FRACTION = Decimal("0.125")
MAX_STOP_RISK_FRACTION = Decimal("0.0125")
FEE_RATE = Decimal("0.0005")
SLIPPAGE_RATE = Decimal("0.0002")
ROUND_TRIP_RATE = (FEE_RATE + SLIPPAGE_RATE) * Decimal("2")
MIN_NET_RR = Decimal("1.5")
TAIL_GAP_FRACTION = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class PositionLot:
    lot_id: str
    role: str
    quantity: Decimal
    entry: Decimal
    stop: Decimal

    @property
    def marked_notional(self) -> Decimal:
        raise ActionDiscriminationError("LOT_MARK_REQUIRED")

    def document(self, mark: Decimal) -> dict[str, Any]:
        return {
            "lot_id": self.lot_id,
            "role": self.role,
            "quantity": canonical_decimal(self.quantity),
            "entry": canonical_decimal(self.entry),
            "stop": canonical_decimal(self.stop),
            "marked_notional": canonical_decimal(self.quantity * mark),
            "marked_gross_fraction": canonical_decimal(
                self.quantity * mark / EQUITY
            ),
        }


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ActionDiscriminationError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ActionDiscriminationError(code) from exc
    if not result.is_finite():
        raise ActionDiscriminationError(code)
    return result


def _price(row: Mapping[str, Any], field: str) -> Decimal:
    result = _decimal(row.get(field), f"BAR_{field.upper()}_INVALID")
    if result <= ZERO:
        raise ActionDiscriminationError(f"BAR_{field.upper()}_INVALID")
    return result


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ActionDiscriminationError("MEAN_EMPTY")
    return sum(values, ZERO) / Decimal(len(values))


def _return(closes: Sequence[Decimal], bars: int) -> Decimal | None:
    if len(closes) <= bars or closes[-bars - 1] <= ZERO:
        return None
    return closes[-1] / closes[-bars - 1] - ONE


def _efficiency(closes: Sequence[Decimal], bars: int) -> Decimal | None:
    if len(closes) <= bars:
        return None
    segment = closes[-bars - 1 :]
    travel = sum(
        (abs(segment[index] - segment[index - 1]) for index in range(1, len(segment))),
        ZERO,
    )
    return ZERO if travel == ZERO else abs(segment[-1] - segment[0]) / travel


def _ema(values: Sequence[Decimal], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    alpha = Decimal("2") / Decimal(period + 1)
    result = _mean(values[:period])
    for value in values[period:]:
        result = value * alpha + result * (ONE - alpha)
    return result


def _ema_slope(closes: Sequence[Decimal], period: int) -> Decimal | None:
    if len(closes) < period + 5:
        return None
    now = _ema(closes, period)
    previous = _ema(closes[:-5], period)
    if now is None or previous is None or previous == ZERO:
        return None
    return now / previous - ONE


def _volume_zscore(volumes: Sequence[Decimal]) -> Decimal | None:
    window = volumes[-24:]
    if len(window) < 24:
        return None
    mean = _mean(window)
    with localcontext() as context:
        context.prec = 34
        variance = _mean([(value - mean) ** 2 for value in window])
        deviation = variance.sqrt()
    return ZERO if deviation == ZERO else (window[-1] - mean) / deviation


def _aggregate_return(
    rows: Sequence[Mapping[str, Any]], decision_at: str
) -> Decimal | None:
    visible = [row for row in rows if str(row.get("available_at", "")) <= decision_at]
    if len(visible) < 2:
        return None
    first = _price(visible[-2], "close")
    last = _price(visible[-1], "close")
    return last / first - ONE


def _evidence(
    evidence_id: str,
    name: str,
    value: Decimal | None,
    *,
    unit: str,
    timeframe: str,
    unknown_reason: str | None = None,
) -> dict[str, Any]:
    result = {
        "evidence_id": evidence_id,
        "name": name,
        "status": "OBSERVED" if value is not None else "UNKNOWN",
        "value": canonical_decimal(value) if value is not None else None,
        "unit": unit,
        "timeframe": timeframe,
        "authority": "FROZEN_PIT_DERIVATION",
    }
    if value is None and unknown_reason is not None:
        result["reason_code"] = unknown_reason
    return result


def market_measurements(
    visible_1h: Sequence[Mapping[str, Any]],
    visible_4h: Sequence[Mapping[str, Any]],
    visible_1d: Sequence[Mapping[str, Any]],
    *,
    decision_at: str,
) -> tuple[dict[str, Any], ...]:
    """Return a closed set of decision-time measurements and evidence IDs."""

    if len(visible_1h) < 96:
        raise ActionDiscriminationError("VISIBLE_1H_HISTORY_INSUFFICIENT")
    if any(str(row.get("available_at", "")) > decision_at for row in visible_1h):
        raise ActionDiscriminationError("FUTURE_BAR_IN_DECISION_VIEW")
    closes = [_price(row, "close") for row in visible_1h]
    highs = [_price(row, "high") for row in visible_1h]
    lows = [_price(row, "low") for row in visible_1h]
    volumes = [_decimal(row.get("volume"), "BAR_VOLUME_INVALID") for row in visible_1h]
    if any(item < ZERO for item in volumes):
        raise ActionDiscriminationError("BAR_VOLUME_INVALID")
    true_ranges: list[Decimal] = []
    for index in range(1, len(visible_1h)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    atr14 = _mean(true_ranges[-14:]) if len(true_ranges) >= 14 else None
    taker_raw = visible_1h[-1].get("taker_buy_base_volume")
    taker = (
        None
        if taker_raw is None
        else _decimal(taker_raw, "TAKER_BUY_VOLUME_INVALID")
    )
    if taker is not None and (taker < ZERO or taker > volumes[-1]):
        raise ActionDiscriminationError("TAKER_BUY_VOLUME_INVALID")
    taker_share = (
        None if taker is None or volumes[-1] == ZERO else taker / volumes[-1]
    )
    rows = (
        _evidence("E-MARK", "decision_close", closes[-1], unit="USDT", timeframe="1h"),
        _evidence("E-R1", "return_1h", _return(closes, 1), unit="fraction", timeframe="1h"),
        _evidence("E-R6", "return_6h", _return(closes, 6), unit="fraction", timeframe="1h"),
        _evidence("E-R24", "return_24h", _return(closes, 24), unit="fraction", timeframe="1h"),
        _evidence("E-R4H", "closed_4h_return", _aggregate_return(visible_4h, decision_at), unit="fraction", timeframe="4h"),
        _evidence("E-R1D", "closed_1d_return", _aggregate_return(visible_1d, decision_at), unit="fraction", timeframe="1d"),
        _evidence("E-ATR14", "atr_14h", atr14, unit="USDT", timeframe="1h"),
        _evidence("E-H24", "high_24h", max(highs[-24:]), unit="USDT", timeframe="1h"),
        _evidence("E-L24", "low_24h", min(lows[-24:]), unit="USDT", timeframe="1h"),
        _evidence("E-H96", "high_96h", max(highs[-96:]), unit="USDT", timeframe="1h"),
        _evidence("E-L96", "low_96h", min(lows[-96:]), unit="USDT", timeframe="1h"),
        _evidence("E-ER6", "efficiency_6h", _efficiency(closes, 6), unit="ratio", timeframe="1h"),
        _evidence("E-ER24", "efficiency_24h", _efficiency(closes, 24), unit="ratio", timeframe="1h"),
        _evidence("E-VOLZ", "volume_zscore_24h", _volume_zscore(volumes), unit="zscore", timeframe="1h"),
        _evidence(
            "E-TAKER",
            "taker_buy_share",
            taker_share,
            unit="ratio",
            timeframe="1h",
            unknown_reason=(
                "UNKNOWN_NOT_PROVIDED_BY_SOURCE"
                if taker_raw is None
                else None
            ),
        ),
        _evidence("E-EMA20", "ema20_slope_5h", _ema_slope(closes, 20), unit="fraction", timeframe="1h"),
        _evidence("E-EMA50", "ema50_slope_5h", _ema_slope(closes, 50), unit="fraction", timeframe="1h"),
    )
    return rows


def _measurement_value(
    measurements: Sequence[Mapping[str, Any]], evidence_id: str
) -> Decimal:
    matches = [item for item in measurements if item.get("evidence_id") == evidence_id]
    if len(matches) != 1 or matches[0].get("status") != "OBSERVED":
        raise ActionDiscriminationError(f"MEASUREMENT_REQUIRED:{evidence_id}")
    return _decimal(matches[0].get("value"), f"MEASUREMENT_INVALID:{evidence_id}")


def geometry_document(
    measurements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    mark = _measurement_value(measurements, "E-MARK")
    atr = _measurement_value(measurements, "E-ATR14")
    low24 = _measurement_value(measurements, "E-L24")
    high24 = _measurement_value(measurements, "E-H24")
    high96 = _measurement_value(measurements, "E-H96")
    stop = max(
        mark * Decimal("0.90"),
        min(low24 - Decimal("0.25") * atr, mark - Decimal("1.50") * atr),
    )
    risk = mark - stop
    target1 = max(high24, mark + Decimal("2.00") * risk)
    target2 = max(high96, mark + Decimal("3.50") * risk)
    valid = ZERO < stop < mark < target1 <= target2 and risk > ZERO
    return {
        "status": "VALID" if valid else "UNKNOWN_INVALID_GEOMETRY",
        "mark": canonical_decimal(mark),
        "stop_new": canonical_decimal(stop) if valid else None,
        "risk_per_unit": canonical_decimal(risk) if valid else None,
        "normal_target": canonical_decimal(target1) if valid else None,
        "trend_target": canonical_decimal(target2) if valid else None,
        "formula_id": "ACTION_E0A_GEOMETRY_V2",
        "not_a_forecast": True,
    }


def state_lots(profile: ProfileSpec, mark: Decimal) -> tuple[PositionLot, ...]:
    def lot(lot_id: str, role: str, fraction: Decimal, entry: Decimal) -> PositionLot:
        return PositionLot(
            lot_id=lot_id,
            role=role,
            quantity=EQUITY * fraction / entry,
            entry=entry,
            stop=entry * Decimal("0.90"),
        )

    template = profile.position_template
    if template == "FLAT":
        return ()
    if template in {"CORE_6_25", "CORE_6_25_HARD_INVALIDATOR_PRESENT"}:
        return (lot("CORE-1", "CORE", CORE_FRACTION, mark),)
    if template == "CORE_6_25_TARGET_REACHED":
        entry = mark / Decimal("1.05")
        return (lot("CORE-1", "CORE", CORE_FRACTION, entry),)
    if template == "CORE_6_25_TACTICAL_3_125":
        return (
            lot("CORE-1", "CORE", CORE_FRACTION, mark),
            lot("TACTICAL-1", "TACTICAL", STAGE_FRACTION, mark * Decimal("1.02")),
        )
    if template == "CORE_6_25_TACTICAL_6_25_PRESSURED":
        entry = mark / Decimal("1.02")
        return (
            lot("CORE-1", "CORE", CORE_FRACTION, entry),
            lot("TACTICAL-1", "TACTICAL", STAGE_FRACTION, entry),
            lot("TACTICAL-2", "TACTICAL", STAGE_FRACTION, entry),
        )
    raise ActionDiscriminationError("POSITION_TEMPLATE_UNKNOWN")


def _marked_gross(lots: Sequence[PositionLot], mark: Decimal) -> Decimal:
    return sum((lot.quantity * mark for lot in lots), ZERO) / EQUITY


def _stop_risk(lots: Sequence[PositionLot], mark: Decimal) -> Decimal:
    return sum(
        (
            lot.quantity * max(ZERO, mark - lot.stop)
            + lot.quantity * lot.stop * (FEE_RATE + SLIPPAGE_RATE)
            for lot in lots
        ),
        ZERO,
    ) / EQUITY


def state_document(
    profile: ProfileSpec,
    supervision: SupervisionMode,
    measurements: Sequence[Mapping[str, Any]],
    *,
    financial_contract_version: str = E0A_FINANCIAL_CONTRACT,
) -> dict[str, Any]:
    mark = _measurement_value(measurements, "E-MARK")
    lots = state_lots(profile, mark)
    value = {
        "schema_id": "counterfactual_state_profile",
        "schema_version": "1.0.0",
        **profile.document(),
        "supervision_mode": supervision.value,
        "lots": [lot.document(mark) for lot in lots],
        "marked_gross_fraction": canonical_decimal(_marked_gross(lots, mark)),
        "open_stop_risk_fraction": canonical_decimal(_stop_risk(lots, mark)),
        "maximum_gross_fraction": canonical_decimal(MAX_GROSS_FRACTION),
        "maximum_stop_risk_fraction": canonical_decimal(MAX_STOP_RISK_FRACTION),
        "hard_invalidator_refs": (
            ["HARD-CONTROL-REGISTERED"]
            if profile.required_action_id is ActionId.INVALIDATE_AND_EXIT
            else []
        ),
        "next_review_rule": "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT",
        "state_is_counterfactual": True,
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    if financial_contract_version == E0B_FINANCIAL_CONTRACT:
        value["schema_version"] = "2.0.0"
        value["financial_contract_version"] = financial_contract_version
        value["reentry_contract"] = (
            {
                "status": "OPEN",
                "created_by_action": "PRIOR_EXIT_WITH_REENTRY",
                "review_deadline": "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT",
                "allowed_fulfilment_action": ActionId.REENTER_CORE.value,
                "maximum_new_stop_risk_fraction": canonical_decimal(
                    MAX_STOP_RISK_FRACTION
                ),
                "execution_in_current_action": False,
            }
            if profile.reentry_status == "OPEN"
            else None
        )
        value["state_continuity_scope"] = (
            "ONE_STEP_COUNTERFACTUAL_PROFILE_NOT_SEQUENTIAL_PROOF"
        )
    value["state_digest"] = canonical_digest(value)
    return value


def _new_lot(action: ActionId, mark: Decimal, stop: Decimal) -> PositionLot:
    fraction = CORE_FRACTION if action in {
        ActionId.OPEN_CORE,
        ActionId.REENTER_CORE,
    } else STAGE_FRACTION
    role = "CORE" if fraction == CORE_FRACTION else "TACTICAL"
    return PositionLot(
        lot_id=f"NEW-{action.value}",
        role=role,
        quantity=EQUITY * fraction / mark,
        entry=mark,
        stop=stop,
    )


def _apply_action_lots(
    action: ActionId,
    lots: Sequence[PositionLot],
    mark: Decimal,
    stop: Decimal,
) -> tuple[tuple[PositionLot, ...], Decimal, str]:
    current = list(lots)
    traded_notional = ZERO
    effect = "NO_CHANGE"
    if action in {ActionId.OPEN_CORE, ActionId.ADD_CONFIRMATION, ActionId.ADD_TREND, ActionId.REENTER_CORE}:
        new_lot = _new_lot(action, mark, stop)
        current.append(new_lot)
        traded_notional = new_lot.quantity * mark
        effect = "BUY"
    elif action is ActionId.REDUCE_TACTICAL:
        tactical = [item for item in current if item.role == "TACTICAL"]
        if tactical:
            removed = tactical[-1]
            current.remove(removed)
            traded_notional = removed.quantity * mark
            effect = "SELL"
    elif action is ActionId.PARTIAL_TAKE_PROFIT:
        retained: list[PositionLot] = []
        for original in current:
            closed_quantity = original.quantity / Decimal("2")
            retained.append(
                PositionLot(
                    original.lot_id,
                    original.role,
                    original.quantity - closed_quantity,
                    original.entry,
                    original.stop,
                )
            )
            traded_notional += closed_quantity * mark
        current = retained
        effect = "SELL"
    elif action in {ActionId.EXIT_WITH_REENTRY, ActionId.INVALIDATE_AND_EXIT}:
        traded_notional = sum((item.quantity * mark for item in current), ZERO)
        current.clear()
        effect = "SELL"
    return tuple(current), traded_notional, effect


def project_action_lots(
    action: ActionId,
    lots: Sequence[PositionLot],
    mark: Decimal,
    stop: Decimal,
) -> tuple[tuple[PositionLot, ...], Decimal, str]:
    """Public deterministic projection used by the outcome-only evaluator."""

    return _apply_action_lots(action, lots, mark, stop)


def _transaction_cost(traded_notional: Decimal) -> Decimal:
    return traded_notional * (FEE_RATE + SLIPPAGE_RATE)


def _new_risk_metrics(mark: Decimal, stop: Decimal, target: Decimal, fraction: Decimal) -> dict[str, Decimal]:
    notional = EQUITY * fraction
    quantity = notional / mark
    entry_cost = notional * (FEE_RATE + SLIPPAGE_RATE)
    stop_exit_cost = quantity * stop * (FEE_RATE + SLIPPAGE_RATE)
    stop_loss = quantity * (mark - stop) + entry_cost + stop_exit_cost
    target_exit_cost = quantity * target * (FEE_RATE + SLIPPAGE_RATE)
    reward = quantity * (target - mark) - entry_cost - target_exit_cost
    rr = reward / stop_loss if stop_loss > ZERO else ZERO
    break_even = stop_loss / (stop_loss + reward) if reward > ZERO else ONE
    return {
        "notional": notional,
        "quantity": quantity,
        "entry_cost": entry_cost,
        "stop_exit_cost": stop_exit_cost,
        "marginal_stop_loss": stop_loss,
        "net_reward": reward,
        "net_rr": rr,
        "break_even_probability": break_even,
    }


def _e0b_action_spec(action: ActionId) -> dict[str, Any]:
    value = ACTION_BY_ID[action].document()
    descriptions = {
        ActionId.HOLD_CORE_TRAIL: (
            "Preserve admitted exposure and arm the frozen next-bar trailing contract."
        ),
        ActionId.PARTIAL_TAKE_PROFIT: (
            "Close 50 percent of every existing lot at the decision mark; each lot may realize a gain or loss."
        ),
        ActionId.EXIT_WITH_REENTRY: (
            "Exit all current exposure and create a future reentry-review obligation; no reentry executes now."
        ),
    }
    if action in descriptions:
        value["description"] = descriptions[action]
    value["financial_contract_version"] = E0B_FINANCIAL_CONTRACT
    return value


def _e0b_action_transition(
    *,
    action: ActionId,
    starting_lots: Sequence[PositionLot],
    post_lots: Sequence[PositionLot],
    mark: Decimal,
    stop: Decimal,
    target1: Decimal,
    reentry_status: str,
) -> dict[str, Any]:
    starting_by_id = {lot.lot_id: lot for lot in starting_lots}
    post_by_id = {lot.lot_id: lot for lot in post_lots}
    closed: list[dict[str, Any]] = []
    for lot_id, before in starting_by_id.items():
        after_quantity = post_by_id.get(
            lot_id,
            PositionLot(lot_id, before.role, ZERO, before.entry, before.stop),
        ).quantity
        closed_quantity = before.quantity - after_quantity
        if closed_quantity > ZERO:
            closed.append(
                {
                    "lot_id": lot_id,
                    "role": before.role,
                    "closed_quantity": canonical_decimal(closed_quantity),
                    "decision_mark": canonical_decimal(mark),
                    "embedded_gross_pnl_realized": canonical_decimal(
                        closed_quantity * (mark - before.entry)
                    ),
                    "modeled_historical_entry_cost_allocated": (
                        canonical_decimal(
                            closed_quantity
                            * before.entry
                            * (FEE_RATE + SLIPPAGE_RATE)
                        )
                    ),
                    "decision_exit_cost": canonical_decimal(
                        closed_quantity
                        * mark
                        * (FEE_RATE + SLIPPAGE_RATE)
                    ),
                    "net_realized_from_entry_after_modeled_costs": (
                        canonical_decimal(
                            closed_quantity * (mark - before.entry)
                            - closed_quantity
                            * before.entry
                            * (FEE_RATE + SLIPPAGE_RATE)
                            - closed_quantity
                            * mark
                            * (FEE_RATE + SLIPPAGE_RATE)
                        )
                    ),
                }
            )
    opened = [
        {
            "lot_id": lot.lot_id,
            "role": lot.role,
            "quantity": canonical_decimal(lot.quantity),
            "entry": canonical_decimal(lot.entry),
            "stop": canonical_decimal(lot.stop),
        }
        for lot in post_lots
        if lot.lot_id not in starting_by_id
    ]
    transition: dict[str, Any] = {
        "contract_id": f"E0B_TRANSITION_{action.value}",
        "closed_lots": closed,
        "opened_lots": opened,
        "retained_lots": [lot.document(mark) for lot in post_lots],
        "reentry_obligation_created": None,
        "reentry_obligation_after": None,
        "review_obligation_after": None,
        "prior_reentry_obligation_effect": "PRESERVE_OR_NOT_APPLICABLE",
        "trail_contract": None,
        "execution_is_counterfactual": True,
    }
    if action is ActionId.HOLD_CORE_TRAIL:
        transition["trail_contract"] = {
            "trigger": "FIRST_FUTURE_BAR_HIGH_GTE_NORMAL_TARGET",
            "trigger_price": canonical_decimal(target1),
            "trail_distance": canonical_decimal(mark - stop),
            "ratchet_rule": "MAX_OLD_STOP_AND_TARGET1_MINUS_DECISION_RISK",
            "ohlc_ambiguity_policy": "OHLC_ORDER_UNKNOWN_TRAIL_EFFECTIVE_NEXT_BAR",
            "same_bar_new_stop_execution": False,
        }
    if action is ActionId.EXIT_WITH_REENTRY:
        transition["reentry_obligation_created"] = {
            "status": "OPEN",
            "created_by_action": action.value,
            "review_deadline": "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT",
            "allowed_fulfilment_action": ActionId.REENTER_CORE.value,
            "maximum_new_stop_risk_fraction": canonical_decimal(
                MAX_STOP_RISK_FRACTION
            ),
            "execution_in_current_action": False,
            "future_trigger_price": None,
            "future_fill_price": None,
            "future_quantity": None,
            "future_payoff_in_current_matrix": None,
        }
        transition["review_obligation_after"] = {
            "status": "OPEN",
            "created_by_action": action.value,
            "purpose": "REENTRY_CONTRACT_REVIEW",
            "review_deadline": (
                "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT"
            ),
            "execution_in_current_action": False,
        }
    if action is ActionId.REENTER_CORE:
        transition["prior_reentry_obligation_effect"] = "FULFILLED"
        transition["reentry_obligation_after"] = {
            "status": "FULFILLED",
            "fulfilled_by_action": action.value,
            "fill_price": canonical_decimal(mark),
            "execution_is_counterfactual": True,
        }
    if action is ActionId.WAIT_WITH_REVIEW:
        transition["review_obligation_after"] = {
            "status": "OPEN",
            "created_by_action": action.value,
            "purpose": "REFRESH_STATE_AND_REASSESS_FEASIBLE_SET",
            "review_deadline": (
                "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT"
            ),
            "execution_in_current_action": False,
        }
        transition["reentry_obligation_after"] = (
            {
                "status": "OPEN",
                "effect": "PRESERVED_PENDING_NEXT_REVIEW",
                "review_deadline": (
                    "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT"
                ),
                "execution_in_current_action": False,
            }
            if reentry_status == "OPEN"
            else None
        )
    return transition


def candidate_bundle(
    profile: ProfileSpec,
    supervision: SupervisionMode,
    state: Mapping[str, Any],
    geometry: Mapping[str, Any],
    measurements: Sequence[Mapping[str, Any]],
    *,
    financial_contract_version: str = E0A_FINANCIAL_CONTRACT,
) -> dict[str, Any]:
    """Calculate every registered action and form the hard-feasible choice set."""

    mark = _measurement_value(measurements, "E-MARK")
    lots = state_lots(profile, mark)
    geometry_valid = geometry.get("status") == "VALID"
    stop = _decimal(geometry.get("stop_new"), "GEOMETRY_STOP_INVALID") if geometry_valid else mark
    target1 = _decimal(geometry.get("normal_target"), "GEOMETRY_T1_INVALID") if geometry_valid else mark
    target2 = _decimal(geometry.get("trend_target"), "GEOMETRY_T2_INVALID") if geometry_valid else mark
    rows: list[dict[str, Any]] = []
    for action in profile.registered_action_ids:
        spec = ACTION_BY_ID[action]
        reasons: list[str] = []
        new_metrics: dict[str, Decimal] | None = None
        target = target2 if action is ActionId.ADD_TREND else target1
        if spec.introduces_new_risk:
            if not geometry_valid:
                reasons.append("NEW_RISK_GEOMETRY_UNKNOWN")
            if supervision is SupervisionMode.UNATTENDED_NO_NEW_RISK:
                reasons.append("SUPERVISION_FORBIDS_NEW_RISK")
            if geometry_valid:
                fraction = CORE_FRACTION if action in {ActionId.OPEN_CORE, ActionId.REENTER_CORE} else STAGE_FRACTION
                new_metrics = _new_risk_metrics(mark, stop, target, fraction)
                if new_metrics["net_rr"] < MIN_NET_RR:
                    reasons.append("MARGINAL_NET_RR_BELOW_FLOOR")
        if spec.required_position_role and not any(
            lot.role == spec.required_position_role for lot in lots
        ):
            reasons.append("REQUIRED_POSITION_ROLE_MISSING")
        post_lots, traded_notional, trade_side = _apply_action_lots(action, lots, mark, stop)
        gross_after = _marked_gross(post_lots, mark)
        risk_after = _stop_risk(post_lots, mark)
        cost = _transaction_cost(traded_notional)
        action_worst_loss_after = (
            risk_after + cost / EQUITY
            if financial_contract_version == E0B_FINANCIAL_CONTRACT
            else risk_after
        )
        if gross_after > MAX_GROSS_FRACTION:
            reasons.append("MARKED_GROSS_CAP_EXCEEDED")
        if (
            action_worst_loss_after > MAX_STOP_RISK_FRACTION
            and (
                financial_contract_version != E0B_FINANCIAL_CONTRACT
                or bool(post_lots)
            )
        ):
            reasons.append("TOTAL_STOP_RISK_CAP_EXCEEDED")
        if profile.required_action_id is not None and action is not profile.required_action_id:
            reasons.append("POLICY_CONTROL_REQUIRES_DIFFERENT_ACTION")
        tail_loss = sum(
            (
                lot.quantity * max(ZERO, mark - lot.stop * (ONE - TAIL_GAP_FRACTION))
                + lot.quantity * lot.stop * (ONE - TAIL_GAP_FRACTION) * (FEE_RATE + SLIPPAGE_RATE)
                for lot in post_lots
            ),
            ZERO,
        ) / EQUITY
        row = {
                "action_id": action.value,
                "action_spec": (
                    _e0b_action_spec(action)
                    if financial_contract_version == E0B_FINANCIAL_CONTRACT
                    else spec.document()
                ),
                "hard_feasible": not reasons,
                "rejection_reason_codes": sorted(set(reasons)),
                "marked_gross_fraction_after": canonical_decimal(gross_after),
                "total_stop_risk_fraction_after": canonical_decimal(risk_after),
                "remaining_stop_risk_fraction": canonical_decimal(
                    max(ZERO, MAX_STOP_RISK_FRACTION - action_worst_loss_after)
                ),
                "tail_gap_loss_fraction": canonical_decimal(tail_loss),
                "immediate_transaction_cost_fraction": canonical_decimal(cost / EQUITY),
                "trade_side": trade_side,
                "marginal_new_risk": (
                    {
                        key: canonical_decimal(value)
                        for key, value in new_metrics.items()
                    }
                    if new_metrics is not None
                    else None
                ),
                "dominance_status": "NOT_APPLIED_OTHER_OR_UNKNOWN_PATH_UNBOUNDED",
                "post_lot_count": len(post_lots),
            }
        if financial_contract_version == E0B_FINANCIAL_CONTRACT:
            row["open_stop_risk_fraction_after"] = canonical_decimal(
                risk_after
            )
            row["action_worst_loss_including_immediate_cost_fraction"] = (
                canonical_decimal(action_worst_loss_after)
            )
            row["action_transition_contract"] = _e0b_action_transition(
                action=action,
                starting_lots=lots,
                post_lots=post_lots,
                mark=mark,
                stop=stop,
                target1=target1,
                reentry_status=profile.reentry_status,
            )
        rows.append(row)
    choice = tuple(row["action_id"] for row in rows if row["hard_feasible"])
    if not choice:
        raise ActionDiscriminationError("SELECTOR_CHOICE_SET_EMPTY")
    if profile.required_action_id is not None and choice != (profile.required_action_id.value,):
        raise ActionDiscriminationError("CONTROL_SINGLETON_INVALID")
    value = {
        "schema_id": "candidate_financial_calculation",
        "schema_version": "1.0.0",
        "profile_id": profile.profile_id.value,
        "supervision_mode": supervision.value,
        "candidate_rows": rows,
        "selector_choice_set": list(choice),
        "selector_policy_id": "BOUNDED_SELECTOR_POLICY_V2",
        "funding_status": "UNKNOWN_EXCLUDED",
        "numeric_probability_status": "NOT_CLAIMED",
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    if financial_contract_version == E0B_FINANCIAL_CONTRACT:
        value["schema_version"] = "2.0.0"
        value["financial_contract_version"] = financial_contract_version
        value["selector_policy_id"] = "BOUNDED_SELECTOR_POLICY_E0B_V2"
    value["calculation_digest"] = canonical_digest(value)
    return value


def _candidate_by_id(bundle: Mapping[str, Any], action_id: str) -> Mapping[str, Any]:
    matches = [row for row in bundle["candidate_rows"] if row.get("action_id") == action_id]
    if len(matches) != 1:
        raise ActionDiscriminationError("CANDIDATE_ROW_MISSING")
    return matches[0]


def path_payoff_matrix(
    profile: ProfileSpec,
    geometry: Mapping[str, Any],
    measurements: Sequence[Mapping[str, Any]],
    candidate_calculations: Mapping[str, Any],
    *,
    financial_contract_version: str = E0A_FINANCIAL_CONTRACT,
) -> dict[str, Any]:
    """Create deterministic path diagnostics without probabilities or EV."""

    mark = _measurement_value(measurements, "E-MARK")
    stop = _decimal(geometry.get("stop_new"), "GEOMETRY_STOP_INVALID")
    target1 = _decimal(geometry.get("normal_target"), "GEOMETRY_T1_INVALID")
    target2 = _decimal(geometry.get("trend_target"), "GEOMETRY_T2_INVALID")
    starting = state_lots(profile, mark)
    paths = (
        ("FAILURE_TO_STOP", stop),
        ("NORMAL_REBOUND_TO_T1", target1),
        ("TREND_CONTINUATION_T1_TO_T2", target2),
        ("EXHAUSTION_T1_THEN_RETURN", mark),
    )
    rows: list[dict[str, Any]] = []
    for action_id in candidate_calculations["selector_choice_set"]:
        action = ActionId(action_id)
        post_lots, traded_notional, _ = _apply_action_lots(action, starting, mark, stop)
        immediate_cost = _transaction_cost(traded_notional)
        for path_id, terminal in paths:
            if path_id == "FAILURE_TO_STOP":
                pnl = -immediate_cost + sum(
                    (
                        lot.quantity * (lot.stop - mark)
                        - lot.quantity * lot.stop * (FEE_RATE + SLIPPAGE_RATE)
                        for lot in post_lots
                    ),
                    ZERO,
                )
            elif path_id == "EXHAUSTION_T1_THEN_RETURN" and action is ActionId.HOLD_CORE_TRAIL:
                if financial_contract_version == E0B_FINANCIAL_CONTRACT:
                    pnl = None
                else:
                    risk = mark - stop
                    pnl = -immediate_cost + sum(
                        (
                            lot.quantity
                            * (max(lot.stop, target1 - risk) - mark)
                            - lot.quantity
                            * max(lot.stop, target1 - risk)
                            * (FEE_RATE + SLIPPAGE_RATE)
                            for lot in post_lots
                        ),
                        ZERO,
                    )
            else:
                pnl = -immediate_cost + sum(
                    (lot.quantity * (terminal - mark) for lot in post_lots),
                    ZERO,
                )
            row = {
                    "action_id": action_id,
                    "path_id": path_id,
                    "terminal_reference": (
                        None
                        if financial_contract_version == E0B_FINANCIAL_CONTRACT
                        and (
                            path_id == "FAILURE_TO_STOP"
                            or (
                                path_id == "EXHAUSTION_T1_THEN_RETURN"
                                and action is ActionId.HOLD_CORE_TRAIL
                            )
                        )
                        else canonical_decimal(terminal)
                    ),
                    "net_account_change": (
                        canonical_decimal(pnl) if pnl is not None else None
                    ),
                    "net_account_change_fraction": (
                        canonical_decimal(pnl / EQUITY)
                        if pnl is not None
                        else None
                    ),
                    "probability": None,
                }
            if financial_contract_version == E0B_FINANCIAL_CONTRACT:
                row["terminal_policy"] = (
                    "EACH_POST_ACTION_LOT_AT_REGISTERED_STOP"
                    if path_id == "FAILURE_TO_STOP"
                    else (
                        "UNKNOWN_T1_RETURN_SEQUENCE_NEXT_BAR_TRAIL"
                        if path_id == "EXHAUSTION_T1_THEN_RETURN"
                        and action is ActionId.HOLD_CORE_TRAIL
                        else "COMMON_TERMINAL_REFERENCE"
                    )
                )
                row["lot_exit_references"] = (
                    [
                        {
                            "lot_id": lot.lot_id,
                            "role": lot.role,
                            "quantity": canonical_decimal(lot.quantity),
                            "exit_price": canonical_decimal(lot.stop),
                            "exit_cost": canonical_decimal(
                                lot.quantity
                                * lot.stop
                                * (FEE_RATE + SLIPPAGE_RATE)
                            ),
                        }
                        for lot in post_lots
                    ]
                    if path_id == "FAILURE_TO_STOP"
                    else []
                )
                row["accounting_scope"] = (
                    "NO_NUMERIC_PAYOFF_PATH_SEQUENCE_UNKNOWN"
                    if pnl is None
                    else "DECISION_TIME_INCREMENTAL_EXCLUDES_COMMON_PREDECISION_EMBEDDED_PNL"
                )
                row["terminal_cost_policy"] = (
                    "REGISTERED_STOP_EXIT_COST_INCLUDED"
                    if path_id == "FAILURE_TO_STOP"
                    else (
                        "NOT_APPLICABLE_PATH_SEQUENCE_UNKNOWN"
                        if path_id == "EXHAUSTION_T1_THEN_RETURN"
                        and action is ActionId.HOLD_CORE_TRAIL
                        else "MARK_TO_MARKET_NO_TERMINAL_EXIT_COST"
                    )
                )
            rows.append(row)
        unknown_rows = [
                {
                    "action_id": action_id,
                    "path_id": "OTHER",
                    "terminal_reference": None,
                    "net_account_change": None,
                    "net_account_change_fraction": None,
                    "probability": None,
                },
                {
                    "action_id": action_id,
                    "path_id": "UNKNOWN",
                    "terminal_reference": None,
                    "net_account_change": None,
                    "net_account_change_fraction": None,
                    "probability": None,
                },
            ]
        if financial_contract_version == E0B_FINANCIAL_CONTRACT:
            for row in unknown_rows:
                row["terminal_policy"] = "UNBOUNDED_UNKNOWN"
                row["lot_exit_references"] = []
                row["accounting_scope"] = (
                    "NO_NUMERIC_PAYOFF_UNKNOWN_PATH"
                )
                row["terminal_cost_policy"] = "NOT_APPLICABLE"
        rows.extend(unknown_rows)
    value = {
        "schema_id": "action_path_payoff_matrix",
        "schema_version": "1.0.0",
        "path_ids": [
            "FAILURE_TO_STOP",
            "NORMAL_REBOUND_TO_T1",
            "TREND_CONTINUATION_T1_TO_T2",
            "EXHAUSTION_T1_THEN_RETURN",
            "OTHER",
            "UNKNOWN",
        ],
        "path_slots": list(PATH_SLOTS),
        "rows": rows,
        "numeric_probability_status": "NOT_CLAIMED",
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    if financial_contract_version == E0B_FINANCIAL_CONTRACT:
        value["schema_version"] = "2.0.0"
        value["financial_contract_version"] = financial_contract_version
        value["failure_terminal_policy"] = (
            "EACH_POST_ACTION_LOT_AT_REGISTERED_STOP"
        )
    value["matrix_digest"] = canonical_digest(value)
    return value


def build_decision_context(
    *,
    sample_index: int,
    profile: ProfileSpec,
    supervision: SupervisionMode,
    decision_slot: Mapping[str, Any],
    visible_1h: Sequence[Mapping[str, Any]],
    visible_4h: Sequence[Mapping[str, Any]],
    visible_1d: Sequence[Mapping[str, Any]],
    source_bindings: Mapping[str, Any],
    financial_contract_version: str = E0A_FINANCIAL_CONTRACT,
) -> dict[str, Any]:
    decision_at = str(decision_slot.get("decision_at", ""))
    measurements = market_measurements(
        visible_1h,
        visible_4h,
        visible_1d,
        decision_at=decision_at,
    )
    geometry = geometry_document(measurements)
    if geometry["status"] != "VALID":
        raise ActionDiscriminationError("DECISION_GEOMETRY_INVALID")
    if financial_contract_version == E0B_FINANCIAL_CONTRACT:
        geometry = dict(geometry)
        geometry["formula_id"] = "ACTION_E0B_GEOMETRY_V2_SAME_PARAMETERS"
    state = state_document(
        profile,
        supervision,
        measurements,
        financial_contract_version=financial_contract_version,
    )
    candidates = candidate_bundle(
        profile,
        supervision,
        state,
        geometry,
        measurements,
        financial_contract_version=financial_contract_version,
    )
    payoff = path_payoff_matrix(
        profile,
        geometry,
        measurements,
        candidates,
        financial_contract_version=financial_contract_version,
    )
    allowed_evidence = [item["evidence_id"] for item in measurements]
    value = {
        "schema_id": "action_choice_context",
        "schema_version": "1.0.0",
        "sample_index": sample_index,
        "decision_at": decision_at,
        "visible_through_bar_id": decision_slot.get("visible_through_bar_id"),
        "source_bindings": dict(source_bindings),
        "market_measurements": list(measurements),
        "allowed_evidence_ids": allowed_evidence,
        "typed_unknowns": [
            "funding_rate",
            "open_interest",
            "order_book",
            "liquidation_flow",
            "participant_psychology",
            "path_probabilities",
        ],
        "state": state,
        "geometry": geometry,
        "candidate_calculations": candidates,
        "path_payoff_matrix": payoff,
        "autonomy_envelope": {
            "selector_may_choose_only_from": candidates["selector_choice_set"],
            "kernel_owns": ["PIT", "STATE", "RISK", "SUPERVISION", "PERMISSION"],
            "agent_owns": ["PATH_INTERPRETATION", "ORDINAL_TRADEOFF", "BOUNDED_SELECTION"],
            "state_write_authority": "CONTROLLER_ONLY",
            "external_execution_authority": EXECUTION_AUTHORITY,
        },
        "semantic_output_contract": {
            "schema_id": "action_discrimination_semantic_output",
            "schema_version": "1.0.0",
            "required_path_slots": list(PATH_SLOTS),
            "required_action_ids": candidates["selector_choice_set"],
            "required_selection_axes": [
                "STRATEGIC_CONTINUITY",
                "PATH_EVIDENCE",
                "MARGINAL_REWARD_RISK",
                "TOTAL_ACCOUNT_RISK",
                "OPPORTUNITY_COST",
                "SUPERVISION",
                "REENTRY_SYMMETRY",
                "EXECUTION_COST",
            ],
            "numeric_probability_status": "NOT_CLAIMED",
        },
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    if financial_contract_version == E0B_FINANCIAL_CONTRACT:
        value["schema_version"] = "2.0.0"
        value["financial_contract_version"] = financial_contract_version
        value["autonomy_envelope"]["kernel_owns"] = [
            "PIT",
            "STATE",
            "RISK",
            "SUPERVISION",
            "PERMISSION",
            "ACTION_TRANSITION",
            "OUTCOME_ACCOUNTING",
        ]
        value["outcome_execution_policy"] = {
            "ohlc_order_status": "UNKNOWN",
            "trailing_policy": "OHLC_ORDER_UNKNOWN_TRAIL_EFFECTIVE_NEXT_BAR",
            "same_bar_new_trail_stop_execution": False,
            "reentry_scope": "OBLIGATION_ONLY_UNLESS_REENTER_CORE_IS_SELECTED",
        }
        value["semantic_output_contract"].update(
            {
                "known_path_slot_policy": (
                    "PRIMARY_ALTERNATIVE_NULL_DISTINCT_AND_NOT_OTHER_UNKNOWN"
                ),
                "hard_falsifier_ref_allowlist": state[
                    "hard_invalidator_refs"
                ],
                "ordinal_ranking_order": [
                    "PREFERRED",
                    "VIABLE",
                    "UNKNOWN",
                    "AVOID",
                ],
                "selector_selected_ordinal": "PREFERRED",
            }
        )
    value["context_digest"] = canonical_digest(value)
    return value


__all__ = [
    "CORE_FRACTION",
    "EQUITY",
    "MAX_GROSS_FRACTION",
    "MAX_STOP_RISK_FRACTION",
    "MIN_NET_RR",
    "STAGE_FRACTION",
    "PositionLot",
    "build_decision_context",
    "candidate_bundle",
    "geometry_document",
    "market_measurements",
    "path_payoff_matrix",
    "project_action_lots",
    "state_document",
    "state_lots",
]
