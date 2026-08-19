"""Recomputable V3.1 financial evaluation over atomic portfolio truth.

This is deliberately a small, non-executable counterfactual calculator.  It
reuses the lot-owned portfolio truth and risk-policy mathematics from
``research_integrity.build_action_evaluation_set``.  Action quantities, costs,
risk, notional, margin, and feasibility are derived from the candidate's
action/scale/lot scope; the caller cannot submit those outputs.

The contract does not invent scenario prices or probabilities.  Until a
separate frozen price-path/payoff matrix exists, regret and expected value stay
structurally unavailable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    CanonicalContractError,
    canonical_decimal,
    self_digest,
    verify_self_digest,
)
from .portfolio_truth import PortfolioTruthError, build_lot_position_truth
from .probability_cloud import ProbabilityMode


class FinancialEvaluationError(ValueError):
    """A financial input or derived evaluation is not reproducible."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_RISK_POLICY_FIELDS = frozenset(
    {
        "fee_rate",
        "slippage_rate",
        "initial_margin_rate",
        "max_gross_leverage",
        "portfolio_risk_cap_usdt",
        "symbol_risk_cap_usdt",
        "gross_notional_cap_usdt",
        "symbol_notional_cap_usdt",
    }
)
_MARKET_FIELDS = frozenset(
    {
        "symbol",
        "available_at",
        "mark_price",
        "contract_multiplier",
        "contract_size_multiplier",
        "quantity_step_contracts",
        "minimum_quantity_contracts",
        "price_tick_usdt",
        "long_protective_stop_price",
        "short_protective_stop_price",
    }
)
_HIGH_REVERSIBILITY = frozenset({"WAIT", "HOLD"})
_MEDIUM_REVERSIBILITY = frozenset(
    {
        "OPEN_LONG",
        "OPEN_SHORT",
        "ADD_25",
        "ADD_50",
        "ADD_75",
        "ADD_100",
        "REDUCE_25",
        "REDUCE_50",
        "REDUCE_75",
        "PARTIAL_EXIT",
    }
)
_LOW_REVERSIBILITY = frozenset({"EXIT_100", "REENTER_LONG", "REENTER_SHORT"})
_ENTRY_ACTIONS = frozenset(
    {
        "OPEN_LONG",
        "OPEN_SHORT",
        "REENTER_LONG",
        "REENTER_SHORT",
        "ADD_25",
        "ADD_50",
        "ADD_75",
        "ADD_100",
    }
)
_REDUCTION_ACTIONS = frozenset(
    {
        "REDUCE_25",
        "REDUCE_50",
        "REDUCE_75",
        "PARTIAL_EXIT",
        "EXIT_100",
    }
)
_ALL_ACTIONS = _HIGH_REVERSIBILITY | _MEDIUM_REVERSIBILITY | _LOW_REVERSIBILITY


def _decimal(value: Any, code: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, (bool, float)):
        raise FinancialEvaluationError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FinancialEvaluationError(code) from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise FinancialEvaluationError(code)
    return result


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise FinancialEvaluationError(code)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FinancialEvaluationError(code) from exc
    if result.tzinfo is None:
        raise FinancialEvaluationError(code)
    return result.astimezone(UTC)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise FinancialEvaluationError(code)
    return value


def _floor_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    """Snap a non-negative value down without manufacturing quantity."""

    return (value / increment).to_integral_value(rounding=ROUND_FLOOR) * increment


def _price_to_tick(value: Decimal, tick: Decimal, *, upward: bool) -> Decimal:
    """Snap a price in the adverse/conservative direction."""

    rounding = ROUND_CEILING if upward else ROUND_FLOOR
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _is_increment_aligned(value: Decimal, increment: Decimal) -> bool:
    return value % increment == 0


def build_financial_risk_policy(risk_policy: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the existing eight-field deterministic action-risk policy."""

    if not isinstance(risk_policy, Mapping) or set(risk_policy) != _RISK_POLICY_FIELDS:
        raise FinancialEvaluationError("FINANCIAL_RISK_POLICY_SCHEMA_INVALID")
    values = {field: _decimal(risk_policy[field], "FINANCIAL_RISK_POLICY_INVALID") for field in _RISK_POLICY_FIELDS}
    if (
        values["fee_rate"] >= 1
        or values["slippage_rate"] >= 1
        or values["initial_margin_rate"] > 1
        or values["max_gross_leverage"] <= 0
        or min(
            values["portfolio_risk_cap_usdt"],
            values["symbol_risk_cap_usdt"],
            values["gross_notional_cap_usdt"],
            values["symbol_notional_cap_usdt"],
        ) <= 0
    ):
        raise FinancialEvaluationError("FINANCIAL_RISK_POLICY_INVALID")
    return self_digest(
        {
            "schema_id": "continuous_action_risk_policy",
            "schema_version": "1.1.0",
            **{field: canonical_decimal(values[field]) for field in sorted(values)},
        },
        "risk_policy_digest",
    )


def build_market_economics_snapshot(
    *, decision_at: str, market_economics: Mapping[str, Any]
) -> dict[str, Any]:
    """Normalize the PIT mark, multiplier, entry budget, and protective stops."""

    if not isinstance(market_economics, Mapping) or set(market_economics) != _MARKET_FIELDS:
        raise FinancialEvaluationError("FINANCIAL_MARKET_ECONOMICS_SCHEMA_INVALID")
    if _time(market_economics["available_at"], "FINANCIAL_MARKET_TIME_INVALID") > _time(
        decision_at, "FINANCIAL_DECISION_TIME_INVALID"
    ):
        raise FinancialEvaluationError("FINANCIAL_FUTURE_MARKET_INPUT_FORBIDDEN")
    symbol = market_economics["symbol"]
    if not isinstance(symbol, str) or not symbol:
        raise FinancialEvaluationError("FINANCIAL_MARKET_SYMBOL_INVALID")
    mark = _decimal(market_economics["mark_price"], "FINANCIAL_MARKET_VALUE_INVALID", positive=True)
    multiplier = _decimal(
        market_economics["contract_multiplier"],
        "FINANCIAL_MARKET_VALUE_INVALID",
        positive=True,
    )
    contract_size_multiplier = _decimal(
        market_economics["contract_size_multiplier"],
        "FINANCIAL_MARKET_VALUE_INVALID",
        positive=True,
    )
    quantity_step = _decimal(
        market_economics["quantity_step_contracts"],
        "FINANCIAL_MARKET_VALUE_INVALID",
        positive=True,
    )
    minimum_quantity = _decimal(
        market_economics["minimum_quantity_contracts"],
        "FINANCIAL_MARKET_VALUE_INVALID",
        positive=True,
    )
    price_tick = _decimal(
        market_economics["price_tick_usdt"],
        "FINANCIAL_MARKET_VALUE_INVALID",
        positive=True,
    )
    long_stop = _decimal(
        market_economics["long_protective_stop_price"],
        "FINANCIAL_MARKET_VALUE_INVALID",
        positive=True,
    )
    short_stop = _decimal(
        market_economics["short_protective_stop_price"],
        "FINANCIAL_MARKET_VALUE_INVALID",
        positive=True,
    )
    if (
        long_stop >= mark
        or short_stop <= mark
        or not _is_increment_aligned(long_stop, price_tick)
        or not _is_increment_aligned(short_stop, price_tick)
    ):
        raise FinancialEvaluationError("FINANCIAL_PROTECTIVE_STOPS_INVALID")
    if not _is_increment_aligned(minimum_quantity, quantity_step):
        raise FinancialEvaluationError("FINANCIAL_MARKET_QUANTITY_CONSTRAINTS_INVALID")
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_market_economics_snapshot",
            "schema_version": "1.1.0",
            "symbol": symbol,
            "available_at": market_economics["available_at"],
            "mark_price": canonical_decimal(mark),
            "contract_multiplier": canonical_decimal(multiplier),
            "contract_size_multiplier": canonical_decimal(
                contract_size_multiplier
            ),
            "quantity_step_contracts": canonical_decimal(quantity_step),
            "minimum_quantity_contracts": canonical_decimal(minimum_quantity),
            "price_tick_usdt": canonical_decimal(price_tick),
            "long_protective_stop_price": canonical_decimal(long_stop),
            "short_protective_stop_price": canonical_decimal(short_stop),
            "funding_cost_status": "UNKNOWN_NOT_INCLUDED",
            "funding_cost_included": False,
            "funding_cost_usdt": None,
            "claim_ceiling": "PIT_DECLARED_INPUT_NO_EXECUTION",
        },
        "market_economics_digest",
    )


def _reversibility(action: str) -> str:
    if action in _HIGH_REVERSIBILITY:
        return "HIGH"
    if action in _MEDIUM_REVERSIBILITY:
        return "MEDIUM"
    if action in _LOW_REVERSIBILITY:
        return "LOW"
    raise FinancialEvaluationError("FINANCIAL_ACTION_INVALID")


def _lot_projection(position: Mapping[str, Any], lot_ids: Sequence[str]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    lots = {row["lot_id"]: row for row in position["lots"]}
    if (
        not lot_ids
        or len(lot_ids) != len(set(lot_ids))
        or any(lot_id not in lots for lot_id in lot_ids)
    ):
        raise FinancialEvaluationError("FINANCIAL_TARGET_LOTS_INVALID")
    rows = [lots[lot_id] for lot_id in lot_ids]
    if any(
        row["symbol"] != position["symbol"]
        or row["side"] != position["intended_side"]
        for row in rows
    ):
        raise FinancialEvaluationError("FINANCIAL_TARGET_LOT_SCOPE_INVALID")
    return (
        sum((_decimal(row["quantity"], "FINANCIAL_LOT_INVALID") for row in rows), Decimal("0")),
        sum((_decimal(row["notional_usdt"], "FINANCIAL_LOT_INVALID") for row in rows), Decimal("0")),
        sum((_decimal(row["open_risk_usdt"], "FINANCIAL_LOT_INVALID") for row in rows), Decimal("0")),
        sum((_decimal(row["margin_used_usdt"], "FINANCIAL_LOT_INVALID") for row in rows), Decimal("0")),
    )


def build_financial_evaluation_receipt(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    evaluated_at: str,
    symbol: str,
    position_truth: Mapping[str, Any],
    risk_policy: Mapping[str, Any],
    market_economics: Mapping[str, Any],
    probability_mode: ProbabilityMode,
    probability_cloud_digest: str,
    calibration_receipt_digests: Sequence[str],
    proper_scoring_receipt_digests: Sequence[str],
    oos_evaluation_receipt_digests: Sequence[str],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Derive all financial outputs from atomic truth and the legal action grid."""

    if (
        not isinstance(run_id, str)
        or not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
        or not isinstance(symbol, str)
        or not symbol
    ):
        raise FinancialEvaluationError("FINANCIAL_RECEIPT_IDENTITY_INVALID")
    decision_time = _time(decision_at, "FINANCIAL_DECISION_TIME_INVALID")
    if _time(evaluated_at, "FINANCIAL_EVALUATED_TIME_INVALID") < decision_time:
        raise FinancialEvaluationError("FINANCIAL_EVALUATION_PRECEDES_DECISION")
    _digest(probability_cloud_digest, "FINANCIAL_CLOUD_DIGEST_INVALID")
    if not isinstance(probability_mode, ProbabilityMode):
        raise FinancialEvaluationError("FINANCIAL_PROBABILITY_MODE_INVALID")
    receipt_sets = (
        tuple(calibration_receipt_digests),
        tuple(proper_scoring_receipt_digests),
        tuple(oos_evaluation_receipt_digests),
    )
    if any(
        len(values) != len(set(values))
        or any(_HEX_64.fullmatch(value) is None for value in values)
        for values in receipt_sets
    ):
        raise FinancialEvaluationError("FINANCIAL_CALIBRATION_BINDINGS_INVALID")
    if probability_mode is ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION:
        if any(not values for values in receipt_sets):
            raise FinancialEvaluationError("FINANCIAL_CALIBRATION_BINDINGS_REQUIRED")
    elif any(receipt_sets):
        raise FinancialEvaluationError("FINANCIAL_UNCALIBRATED_RECEIPTS_FORBIDDEN")

    try:
        position = build_lot_position_truth(symbol=symbol, position_truth=position_truth)
    except PortfolioTruthError as exc:
        raise FinancialEvaluationError(str(exc)) from exc
    policy = build_financial_risk_policy(risk_policy)
    market = build_market_economics_snapshot(
        decision_at=decision_at, market_economics=market_economics
    )
    market_effective_multiplier = _decimal(
        market["contract_multiplier"], "FINANCIAL_MARKET_VALUE_INVALID"
    ) * _decimal(
        market["contract_size_multiplier"], "FINANCIAL_MARKET_VALUE_INVALID"
    )
    if (
        market["symbol"] != symbol
        or market["mark_price"] != position["mark_price"]
        or canonical_decimal(market_effective_multiplier)
        != position["contract_multiplier"]
    ):
        raise FinancialEvaluationError("FINANCIAL_MARKET_PORTFOLIO_MISMATCH")

    candidate_documents = tuple(candidates)
    if not candidate_documents or any(not isinstance(row, Mapping) for row in candidate_documents):
        raise FinancialEvaluationError("FINANCIAL_CANDIDATES_INVALID")
    candidate_ids: set[str] = set()
    evaluations: list[dict[str, Any]] = []
    mark = _decimal(market["mark_price"], "FINANCIAL_MARKET_VALUE_INVALID")
    multiplier = _decimal(market["contract_multiplier"], "FINANCIAL_MARKET_VALUE_INVALID")
    contract_size_multiplier = _decimal(
        market["contract_size_multiplier"], "FINANCIAL_MARKET_VALUE_INVALID"
    )
    effective_multiplier = multiplier * contract_size_multiplier
    quantity_step = _decimal(
        market["quantity_step_contracts"], "FINANCIAL_MARKET_VALUE_INVALID"
    )
    minimum_quantity = _decimal(
        market["minimum_quantity_contracts"], "FINANCIAL_MARKET_VALUE_INVALID"
    )
    price_tick = _decimal(
        market["price_tick_usdt"], "FINANCIAL_MARKET_VALUE_INVALID"
    )
    for row in (*position["lots"], *position["pending_orders"]):
        if row["symbol"] != symbol:
            continue
        quantity = _decimal(row["quantity"], "FINANCIAL_POSITION_INVALID")
        if (
            quantity < minimum_quantity
            or not _is_increment_aligned(quantity, quantity_step)
        ):
            raise FinancialEvaluationError(
                "FINANCIAL_PORTFOLIO_CONTRACT_QUANTITY_INVALID"
            )
    fee_rate = _decimal(policy["fee_rate"], "FINANCIAL_RISK_POLICY_INVALID")
    slippage_rate = _decimal(policy["slippage_rate"], "FINANCIAL_RISK_POLICY_INVALID")
    initial_margin_rate = _decimal(policy["initial_margin_rate"], "FINANCIAL_RISK_POLICY_INVALID")
    portfolio_cap = _decimal(policy["portfolio_risk_cap_usdt"], "FINANCIAL_RISK_POLICY_INVALID")
    symbol_cap = _decimal(policy["symbol_risk_cap_usdt"], "FINANCIAL_RISK_POLICY_INVALID")
    gross_cap = _decimal(policy["gross_notional_cap_usdt"], "FINANCIAL_RISK_POLICY_INVALID")
    symbol_notional_cap = _decimal(policy["symbol_notional_cap_usdt"], "FINANCIAL_RISK_POLICY_INVALID")
    leverage_cap = _decimal(policy["max_gross_leverage"], "FINANCIAL_RISK_POLICY_INVALID")
    account = position["account"]
    target = position["target_symbol"]
    current_portfolio_risk = _decimal(account["committed_risk_usdt"], "FINANCIAL_POSITION_INVALID")
    current_gross = _decimal(account["committed_gross_notional_usdt"], "FINANCIAL_POSITION_INVALID")
    current_margin = _decimal(account["margin_used_usdt"], "FINANCIAL_POSITION_INVALID")
    equity = _decimal(account["equity_usdt"], "FINANCIAL_POSITION_INVALID")
    account_leverage_cap = _decimal(
        account["max_gross_leverage"], "FINANCIAL_POSITION_INVALID"
    )
    if leverage_cap > account_leverage_cap:
        raise FinancialEvaluationError("FINANCIAL_POLICY_EXCEEDS_ACCOUNT_LEVERAGE_CAP")
    current_symbol_risk = _decimal(target["open_risk_usdt"], "FINANCIAL_POSITION_INVALID") + _decimal(target["pending_order_risk_usdt"], "FINANCIAL_POSITION_INVALID")
    current_symbol_notional = _decimal(target["open_notional_usdt"], "FINANCIAL_POSITION_INVALID") + _decimal(target["pending_open_notional_usdt"], "FINANCIAL_POSITION_INVALID")
    intended_side = position["intended_side"]

    for candidate in candidate_documents:
        candidate_id = candidate.get("candidate_id")
        action = candidate.get("action")
        scale = candidate.get("scale_pct")
        lot_ids = candidate.get("target_lot_ids")
        role = candidate.get("target_role")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or candidate_id in candidate_ids
            or action not in _ALL_ACTIONS
            or candidate.get("authorized") is not False
            or not isinstance(lot_ids, list)
        ):
            raise FinancialEvaluationError("FINANCIAL_CANDIDATES_INVALID")
        candidate_ids.add(candidate_id)
        vetoes: list[str] = []
        quantity_delta = Decimal("0")
        unrounded_quantity_delta = Decimal("0")
        target_quantity = target_notional = target_risk = target_margin = Decimal("0")
        side = intended_side
        stop: Decimal | None = None
        if action in _ENTRY_ACTIONS:
            if lot_ids or role not in {"CORE", "TACTICAL"} or not isinstance(scale, int) or isinstance(scale, bool):
                raise FinancialEvaluationError("FINANCIAL_ENTRY_CANDIDATE_INVALID")
            if action in {"OPEN_LONG", "REENTER_LONG"}:
                side = "LONG"
            elif action in {"OPEN_SHORT", "REENTER_SHORT"}:
                side = "SHORT"
            if action.startswith("ADD_") and side != intended_side:
                raise FinancialEvaluationError("FINANCIAL_ADD_SIDE_INVALID")
            stop = _decimal(
                market[
                    "long_protective_stop_price"
                    if side == "LONG"
                    else "short_protective_stop_price"
                ],
                "FINANCIAL_STOP_INVALID",
            )
            symbol_notional_room = max(
                Decimal("0"), symbol_notional_cap - current_symbol_notional
            )
            gross_notional_room = max(Decimal("0"), gross_cap - current_gross)
            leverage_notional_room = max(
                Decimal("0"),
                equity * min(leverage_cap, account_leverage_cap) - current_gross,
            )
            risk_room = max(
                Decimal("0"),
                min(
                    symbol_cap - current_symbol_risk,
                    portfolio_cap - current_portfolio_risk,
                ),
            )
            risk_notional_room = (
                risk_room * mark / abs(mark - stop)
            )
            capacity_rooms = [
                symbol_notional_room,
                gross_notional_room,
                leverage_notional_room,
                risk_notional_room,
            ]
            if initial_margin_rate > 0:
                capacity_rooms.append(
                    max(Decimal("0"), equity - current_margin)
                    / initial_margin_rate
                )
            entry_notional_capacity = min(capacity_rooms)
            action_notional = (
                entry_notional_capacity * Decimal(scale) / Decimal("100")
            )
            unrounded_quantity_delta = action_notional / (
                mark * effective_multiplier
            )
            quantity_delta = _floor_to_increment(
                unrounded_quantity_delta, quantity_step
            )
            if entry_notional_capacity == 0:
                vetoes.append("NO_ENTRY_CAPACITY")
            elif quantity_delta < minimum_quantity:
                vetoes.append("BELOW_MINIMUM_QUANTITY")
        elif action in _REDUCTION_ACTIONS:
            if role is not None or not isinstance(scale, int) or isinstance(scale, bool):
                raise FinancialEvaluationError("FINANCIAL_REDUCTION_CANDIDATE_INVALID")
            target_quantity, target_notional, target_risk, target_margin = _lot_projection(position, lot_ids)
            raw_reduction = target_quantity * Decimal(scale) / Decimal("100")
            tradable_reduction = _floor_to_increment(
                raw_reduction, quantity_step
            )
            quantity_delta = -tradable_reduction
            unrounded_quantity_delta = -raw_reduction
            if tradable_reduction < minimum_quantity:
                vetoes.append("BELOW_MINIMUM_QUANTITY")
        else:
            if scale is not None or role is not None:
                raise FinancialEvaluationError("FINANCIAL_ZERO_DELTA_CANDIDATE_INVALID")
            if action == "HOLD":
                target_quantity, target_notional, target_risk, target_margin = _lot_projection(position, lot_ids)
            elif lot_ids:
                raise FinancialEvaluationError("FINANCIAL_WAIT_LOTS_INVALID")

        direction = Decimal("1") if side == "LONG" else Decimal("-1")
        trade_direction = direction if quantity_delta > 0 else -direction
        raw_fill = (
            mark
            if quantity_delta == 0
            else mark * (Decimal("1") + trade_direction * slippage_rate)
        )
        fill = (
            mark
            if quantity_delta == 0
            else _price_to_tick(
                raw_fill, price_tick, upward=trade_direction > 0
            )
        )
        if fill <= 0:
            raise FinancialEvaluationError("FINANCIAL_FILL_PRICE_INVALID")
        turnover = abs(quantity_delta) * fill * effective_multiplier
        fee = turnover * fee_rate
        slippage = (
            abs(fill - mark) * abs(quantity_delta) * effective_multiplier
        )
        action_cost = fee + slippage

        if action in _ENTRY_ACTIONS:
            new_notional = quantity_delta * mark * effective_multiplier
            new_risk = (
                quantity_delta * abs(mark - stop) * effective_multiplier
            )
            symbol_notional_after = current_symbol_notional + new_notional
            symbol_risk_after = current_symbol_risk + new_risk
            gross_after = current_gross + new_notional
            portfolio_risk_after = current_portfolio_risk + new_risk
            margin_after = current_margin + new_notional * initial_margin_rate
            if action.startswith("OPEN_") and current_symbol_notional > 0:
                vetoes.append("OPEN_REQUIRES_FLAT_SYMBOL")
            if action.startswith("ADD_") and current_symbol_notional == 0:
                vetoes.append("ADD_REQUIRES_EXISTING_POSITION")
            if action.startswith("REENTER_") and (
                current_symbol_notional > 0 or position["reentry_contract_active"] is not True
            ):
                vetoes.append("REENTRY_CONTRACT_AND_FLAT_STATE_REQUIRED")
        elif action in _REDUCTION_ACTIONS:
            fraction = abs(quantity_delta) / target_quantity
            symbol_notional_after = current_symbol_notional - target_notional * fraction
            symbol_risk_after = current_symbol_risk - target_risk * fraction
            gross_after = current_gross - target_notional * fraction
            portfolio_risk_after = current_portfolio_risk - target_risk * fraction
            margin_after = current_margin - target_margin * fraction
        else:
            symbol_notional_after = current_symbol_notional
            symbol_risk_after = current_symbol_risk
            gross_after = current_gross
            portfolio_risk_after = current_portfolio_risk
            margin_after = current_margin

        if symbol_risk_after > symbol_cap:
            vetoes.append("SYMBOL_RISK_CAP")
        if portfolio_risk_after > portfolio_cap:
            vetoes.append("PORTFOLIO_RISK_CAP")
        if symbol_notional_after > symbol_notional_cap:
            vetoes.append("SYMBOL_NOTIONAL_CAP")
        if gross_after > gross_cap:
            vetoes.append("GROSS_NOTIONAL_CAP")
        if margin_after > equity:
            vetoes.append("MARGIN_CAPACITY_EXCEEDED")
        gross_leverage_after = gross_after / equity
        if gross_leverage_after > leverage_cap:
            vetoes.append("GROSS_LEVERAGE_CAP")

        evaluations.append(
            {
                "candidate_id": candidate_id,
                "feasible": not vetoes,
                "infeasible_reasons": sorted(set(vetoes)),
                "transaction_cost_usdt": canonical_decimal(fee),
                "liquidity_cost_usdt": canonical_decimal(slippage),
                "worst_case_loss_usdt": canonical_decimal(symbol_risk_after + action_cost),
                "maximum_regret_usdt": None,
                "regret_status": "UNAVAILABLE_NO_FROZEN_PRICE_PATH_PAYOFF_MATRIX",
                "reversibility": _reversibility(action),
                "scenario_refs": list(candidate.get("path_refs") or ()),
                "robustness_notes": [
                    "Quantity, cost, risk, notional, margin, and feasibility were recomputed from atomic inputs.",
                    "Funding cost is UNKNOWN and excluded; it is not treated as zero.",
                    "Regret and expected value are unavailable without a frozen price-path payoff matrix.",
                ],
                "expected_value_lower_usdt": None,
                "expected_value_upper_usdt": None,
                "expected_value_usdt": None,
                "economics": {
                    "quantity_delta": canonical_decimal(quantity_delta),
                    "unrounded_quantity_delta": canonical_decimal(
                        unrounded_quantity_delta
                    ),
                    "quantity_rounding_loss_contracts": canonical_decimal(
                        abs(unrounded_quantity_delta) - abs(quantity_delta)
                    ),
                    "estimated_fill_price": canonical_decimal(fill),
                    "turnover_notional_usdt": canonical_decimal(turnover),
                    "symbol_notional_after_usdt": canonical_decimal(symbol_notional_after),
                    "symbol_risk_after_usdt": canonical_decimal(symbol_risk_after),
                    "portfolio_risk_after_usdt": canonical_decimal(portfolio_risk_after),
                    "gross_notional_after_usdt": canonical_decimal(gross_after),
                    "margin_used_after_usdt": canonical_decimal(margin_after),
                    "gross_leverage_after": canonical_decimal(gross_leverage_after),
                    "protective_stop_after": None if stop is None else canonical_decimal(stop),
                },
            }
        )

    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_financial_evaluation_receipt",
            "schema_version": "2.1.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "evaluated_at": evaluated_at,
            "position_truth": position,
            "portfolio_truth_digest": position["position_truth_digest"],
            "risk_policy": policy,
            "risk_policy_digest": policy["risk_policy_digest"],
            "market_economics": market,
            "market_economics_digest": market["market_economics_digest"],
            "probability_mode": probability_mode.value,
            "probability_cloud_digest": probability_cloud_digest,
            "calibration_receipt_digests": list(receipt_sets[0]),
            "proper_scoring_receipt_digests": list(receipt_sets[1]),
            "oos_evaluation_receipt_digests": list(receipt_sets[2]),
            "candidates": [dict(row) for row in candidate_documents],
            "evaluations": sorted(evaluations, key=lambda row: row["candidate_id"]),
            "payoff_matrix_status": "ABSENT_NO_NUMERIC_EV_OR_REGRET",
            "funding_cost_status": "UNKNOWN_NOT_INCLUDED",
            "funding_cost_included": False,
            "funding_cost_usdt": None,
            "claim_ceiling": "DETERMINISTIC_LOCAL_COUNTERFACTUAL_NO_EXECUTION",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "financial_evaluation_receipt_digest",
    )


def verify_financial_evaluation_receipt(
    receipt: Mapping[str, Any], *, candidates: Sequence[Mapping[str, Any]]
) -> str:
    """Rebuild from stored atomic inputs and reject semantic rehashes."""

    try:
        supplied = verify_self_digest(receipt, "financial_evaluation_receipt_digest")
        if (
            receipt.get("claim_ceiling") != "DETERMINISTIC_LOCAL_COUNTERFACTUAL_NO_EXECUTION"
            or receipt.get("payoff_matrix_status") != "ABSENT_NO_NUMERIC_EV_OR_REGRET"
            or receipt.get("funding_cost_status") != "UNKNOWN_NOT_INCLUDED"
            or receipt.get("funding_cost_included") is not False
            or receipt.get("funding_cost_usdt") is not None
            or receipt.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
            or receipt.get("executable") is not False
            or receipt.get("candidates") != [dict(row) for row in candidates]
        ):
            raise FinancialEvaluationError("FINANCIAL_RECEIPT_AUTHORITY_OR_BINDING_INVALID")
        position = receipt["position_truth"]
        policy = receipt["risk_policy"]
        market = receipt["market_economics"]
        verify_self_digest(position, "position_truth_digest")
        verify_self_digest(policy, "risk_policy_digest")
        verify_self_digest(market, "market_economics_digest")
        raw_position = {
            "intended_side": position["intended_side"],
            "mark_price": position["mark_price"],
            "contract_multiplier": position["contract_multiplier"],
            "reentry_contract_active": position["reentry_contract_active"],
            "account": {
                key: position["account"][key]
                for key in (
                    "equity_usdt",
                    "margin_used_usdt",
                    "margin_available_usdt",
                    "max_gross_leverage",
                )
            },
            "lots": [
                {
                    key: row[key]
                    for key in (
                        "lot_id",
                        "symbol",
                        "side",
                        "role",
                        "quantity",
                        "entry_price",
                        "mark_price",
                        "stop_price",
                        "contract_multiplier",
                        "margin_used_usdt",
                    )
                }
                for row in position["lots"]
            ],
            "pending_orders": [
                {
                    key: row[key]
                    for key in (
                        "order_id",
                        "symbol",
                        "side",
                        "intent",
                        "quantity",
                        "reference_price",
                        "stop_price",
                        "contract_multiplier",
                        "reduce_only",
                        "target_lot_ids",
                        "reserved_margin_usdt",
                    )
                }
                for row in position["pending_orders"]
            ],
        }
        raw_policy = {key: policy[key] for key in _RISK_POLICY_FIELDS}
        raw_market = {key: market[key] for key in _MARKET_FIELDS}
        rebuilt = build_financial_evaluation_receipt(
            run_id=receipt["run_id"],
            cycle_index=receipt["cycle_index"],
            decision_at=receipt["decision_at"],
            evaluated_at=receipt["evaluated_at"],
            symbol=position["symbol"],
            position_truth=raw_position,
            risk_policy=raw_policy,
            market_economics=raw_market,
            probability_mode=ProbabilityMode(receipt["probability_mode"]),
            probability_cloud_digest=receipt["probability_cloud_digest"],
            calibration_receipt_digests=receipt["calibration_receipt_digests"],
            proper_scoring_receipt_digests=receipt["proper_scoring_receipt_digests"],
            oos_evaluation_receipt_digests=receipt["oos_evaluation_receipt_digests"],
            candidates=candidates,
        )
    except (KeyError, TypeError, ValueError, PortfolioTruthError, CanonicalContractError) as exc:
        if isinstance(exc, FinancialEvaluationError):
            raise
        raise FinancialEvaluationError("FINANCIAL_RECEIPT_INVALID") from exc
    if rebuilt != dict(receipt):
        raise FinancialEvaluationError("FINANCIAL_RECEIPT_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "FinancialEvaluationError",
    "build_financial_evaluation_receipt",
    "build_financial_risk_policy",
    "build_market_economics_snapshot",
    "verify_financial_evaluation_receipt",
]
