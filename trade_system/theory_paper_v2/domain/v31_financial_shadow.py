"""Frozen V3.1 flat-shadow financial runtime composition.

This module is the sole bridge from the preregistered experiment contract and
one native PIT market-economics input to portfolio truth, the eight-field risk
policy, and the finite three-action decision context.  It is deterministic,
non-executable, and does not read an account or treat unknown funding as zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Mapping, Sequence

from .behavior_planning import (
    PortfolioDecisionContext,
    PositionRole,
    PositionSide,
    legal_action_keys,
)
from .contracts.canonical import canonical_decimal
from .financial_evaluation import (
    FinancialEvaluationError,
    build_financial_evaluation_receipt,
    build_financial_risk_policy,
    build_market_economics_snapshot,
)
from .portfolio_truth import build_lot_position_truth
from .probability_cloud import ProbabilityMode
from .v31_experiment_contracts import (
    V31ExperimentContractError,
    verify_minimal_experiment_contract,
)


class V31FinancialShadowError(ValueError):
    """The PIT market or runtime inputs drifted from the frozen contract."""


def _decimal(value: Any, code: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, (bool, float)):
        raise V31FinancialShadowError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise V31FinancialShadowError(code) from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise V31FinancialShadowError(code)
    return result


def _snap_price(value: Decimal, tick: Decimal, *, upward: bool) -> Decimal:
    rounding = ROUND_CEILING if upward else ROUND_FLOOR
    return (value / tick).to_integral_value(rounding=rounding) * tick


@dataclass(frozen=True, slots=True)
class FrozenFinancialShadowRuntime:
    """Immutable normalized values used to generate cycle-local documents."""

    experiment_contract_digest: str
    run_id: str
    symbol: str
    decision_at: str
    available_at: str
    mark_price: str
    contract_multiplier: str
    contract_size_multiplier: str
    quantity_step_contracts: str
    minimum_quantity_contracts: str
    price_tick_usdt: str
    long_protective_stop_price: str
    short_protective_stop_price: str
    equity_usdt: str
    margin_used_usdt: str
    margin_available_usdt: str
    account_max_gross_leverage: str
    risk_policy_items: tuple[tuple[str, str], ...]
    entry_scale_grid_pct: tuple[int, ...]
    partial_exit_scale_grid_pct: tuple[int, ...]
    allowed_entry_roles: tuple[str, ...]
    legal_candidate_count: int

    def position_truth_input(self) -> dict[str, Any]:
        effective_multiplier = _decimal(
            self.contract_multiplier,
            "V31_FINANCIAL_RUNTIME_MULTIPLIER_INVALID",
            positive=True,
        ) * _decimal(
            self.contract_size_multiplier,
            "V31_FINANCIAL_RUNTIME_CT_MULT_INVALID",
            positive=True,
        )
        return {
            "intended_side": "FLAT",
            "mark_price": self.mark_price,
            "contract_multiplier": canonical_decimal(effective_multiplier),
            "reentry_contract_active": False,
            "account": {
                "equity_usdt": self.equity_usdt,
                "margin_used_usdt": self.margin_used_usdt,
                "margin_available_usdt": self.margin_available_usdt,
                "max_gross_leverage": self.account_max_gross_leverage,
            },
            "lots": [],
            "pending_orders": [],
        }

    def risk_policy_input(self) -> dict[str, str]:
        return dict(self.risk_policy_items)

    def market_economics_input(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "available_at": self.available_at,
            "mark_price": self.mark_price,
            "contract_multiplier": self.contract_multiplier,
            "contract_size_multiplier": self.contract_size_multiplier,
            "quantity_step_contracts": self.quantity_step_contracts,
            "minimum_quantity_contracts": self.minimum_quantity_contracts,
            "price_tick_usdt": self.price_tick_usdt,
            "long_protective_stop_price": self.long_protective_stop_price,
            "short_protective_stop_price": self.short_protective_stop_price,
        }

    def decision_context(
        self,
        *,
        probability_mode: ProbabilityMode,
        probability_cloud_digest: str,
        calibration_receipt_digests: Sequence[str] = (),
        proper_scoring_receipt_digests: Sequence[str] = (),
        oos_evaluation_receipt_digests: Sequence[str] = (),
    ) -> PortfolioDecisionContext:
        position = build_lot_position_truth(
            symbol=self.symbol, position_truth=self.position_truth_input()
        )
        risk_policy = build_financial_risk_policy(self.risk_policy_input())
        context = PortfolioDecisionContext(
            decision_at=self.decision_at,
            position_side=PositionSide.FLAT,
            lot_ids=(),
            pending_reentry_side=None,
            portfolio_truth_digest=position["position_truth_digest"],
            risk_policy_digest=risk_policy["risk_policy_digest"],
            probability_mode=probability_mode,
            probability_cloud_digest=probability_cloud_digest,
            calibration_receipt_digests=tuple(calibration_receipt_digests),
            proper_scoring_receipt_digests=tuple(
                proper_scoring_receipt_digests
            ),
            oos_evaluation_receipt_digests=tuple(
                oos_evaluation_receipt_digests
            ),
            entry_scale_grid_pct=self.entry_scale_grid_pct,
            partial_exit_scale_grid_pct=self.partial_exit_scale_grid_pct,
            allowed_entry_roles=tuple(
                PositionRole(role) for role in self.allowed_entry_roles
            ),
        )
        if len(legal_action_keys(context)) != self.legal_candidate_count:
            raise V31FinancialShadowError(
                "V31_FINANCIAL_RUNTIME_ACTION_GRID_DRIFT"
            )
        return context


def build_frozen_financial_shadow_runtime(
    *,
    experiment_contract: Mapping[str, Any],
    decision_at: str,
    native_market_economics: Mapping[str, Any],
) -> FrozenFinancialShadowRuntime:
    """Bind a native PIT instrument snapshot to every frozen assumption."""

    try:
        contract_digest = verify_minimal_experiment_contract(
            experiment_contract
        )
        financial = experiment_contract["portfolio_scope"]["financial_shadow"]
        account = financial["initial_shadow_account"]
        policy = financial["risk_policy"]
        grid = financial["candidate_grid"]
        market_policy = financial["market_economics_policy"]
        normalized_market = build_market_economics_snapshot(
            decision_at=decision_at,
            market_economics=native_market_economics,
        )
        normalized_policy = build_financial_risk_policy(policy)
    except (
        FinancialEvaluationError,
        V31ExperimentContractError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_INPUT_INVALID"
        ) from exc

    required_boundary = {
        "mode": "STATIC_COUNTERFACTUAL_FLAT_SHADOW",
        "target_position": "FLAT",
        "funding_cost_policy": (
            "UNKNOWN_UNLESS_SETTLEMENT_WINDOW_AND_RATE_ARE_PIT_BOUND"
        ),
    }
    if (
        financial.get("mode") != required_boundary["mode"]
        or account.get("target_position") != required_boundary["target_position"]
        or account.get("other_lots") != []
        or account.get("pending_orders") != []
        or financial.get("mid_run_financial_assumption_change_forbidden")
        is not True
        or market_policy.get("funding_cost_policy")
        != required_boundary["funding_cost_policy"]
        or market_policy.get("funding_cost_included") is not False
        or normalized_market.get("funding_cost_status")
        != "UNKNOWN_NOT_INCLUDED"
        or normalized_market.get("funding_cost_included") is not False
        or normalized_market.get("funding_cost_usdt") is not None
    ):
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_BOUNDARY_DRIFT"
        )

    expected_market = {
        "symbol": market_policy["instrument_id"],
        "contract_multiplier": market_policy["contract_multiplier"],
        "contract_size_multiplier": market_policy[
            "contract_size_multiplier"
        ],
        "quantity_step_contracts": market_policy[
            "quantity_step_contracts"
        ],
        "minimum_quantity_contracts": market_policy[
            "minimum_quantity_contracts"
        ],
        "price_tick_usdt": market_policy["price_tick_usdt"],
    }
    if any(
        normalized_market.get(field) != expected
        for field, expected in expected_market.items()
    ):
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_PUBLIC_CONTRACT_DRIFT"
        )

    mark = _decimal(
        normalized_market["mark_price"],
        "V31_FINANCIAL_RUNTIME_MARK_INVALID",
        positive=True,
    )
    tick = _decimal(
        normalized_market["price_tick_usdt"],
        "V31_FINANCIAL_RUNTIME_TICK_INVALID",
        positive=True,
    )
    long_multiplier = _decimal(
        market_policy["long_protective_stop_multiplier"],
        "V31_FINANCIAL_RUNTIME_STOP_POLICY_INVALID",
        positive=True,
    )
    short_multiplier = _decimal(
        market_policy["short_protective_stop_multiplier"],
        "V31_FINANCIAL_RUNTIME_STOP_POLICY_INVALID",
        positive=True,
    )
    expected_long_stop = canonical_decimal(
        _snap_price(mark * long_multiplier, tick, upward=False)
    )
    expected_short_stop = canonical_decimal(
        _snap_price(mark * short_multiplier, tick, upward=True)
    )
    if (
        normalized_market["long_protective_stop_price"]
        != expected_long_stop
        or normalized_market["short_protective_stop_price"]
        != expected_short_stop
        or market_policy.get("protective_stop_rounding")
        != "OUTWARD_TO_PUBLIC_PRICE_TICK"
        or market_policy.get("quantity_rounding")
        != "DOWN_TO_PUBLIC_QUANTITY_STEP"
        or market_policy.get("minimum_quantity_result")
        != "INFEASIBLE_NOT_ROUNDED_UP"
    ):
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_PROTECTIVE_STOP_DRIFT"
        )

    account_values = {
        field: canonical_decimal(
            _decimal(
                account[field],
                "V31_FINANCIAL_RUNTIME_ACCOUNT_INVALID",
                positive=field in {"equity_usdt", "max_gross_leverage"},
            )
        )
        for field in (
            "equity_usdt",
            "margin_used_usdt",
            "margin_available_usdt",
            "max_gross_leverage",
        )
    }
    if (
        _decimal(account_values["margin_used_usdt"], "")
        + _decimal(account_values["margin_available_usdt"], "")
        != _decimal(account_values["equity_usdt"], "")
    ):
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_ACCOUNT_INVALID"
        )
    risk_policy_items = tuple(
        sorted(
            (field, str(normalized_policy[field]))
            for field in (
                "fee_rate",
                "slippage_rate",
                "initial_margin_rate",
                "max_gross_leverage",
                "portfolio_risk_cap_usdt",
                "symbol_risk_cap_usdt",
                "gross_notional_cap_usdt",
                "symbol_notional_cap_usdt",
            )
        )
    )
    if len(risk_policy_items) != 8:
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_RISK_POLICY_INVALID"
        )

    entry_grid = tuple(grid["entry_scale_grid_pct"])
    partial_exit_grid = tuple(grid["partial_exit_scale_grid_pct"])
    roles = tuple(grid["allowed_entry_roles"])
    legal_count = grid["legal_candidate_count"]
    if (
        grid.get("position_side") != "FLAT"
        or grid.get("legal_action_classes")
        != ["OPEN_LONG", "OPEN_SHORT", "WAIT"]
        or isinstance(legal_count, bool)
        or not isinstance(legal_count, int)
        or legal_count != 1 + 2 * len(entry_grid) * len(roles)
    ):
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_ACTION_GRID_DRIFT"
        )

    runtime = FrozenFinancialShadowRuntime(
        experiment_contract_digest=contract_digest,
        run_id=str(experiment_contract["run_id"]),
        symbol=str(normalized_market["symbol"]),
        decision_at=decision_at,
        available_at=str(normalized_market["available_at"]),
        mark_price=str(normalized_market["mark_price"]),
        contract_multiplier=str(normalized_market["contract_multiplier"]),
        contract_size_multiplier=str(
            normalized_market["contract_size_multiplier"]
        ),
        quantity_step_contracts=str(
            normalized_market["quantity_step_contracts"]
        ),
        minimum_quantity_contracts=str(
            normalized_market["minimum_quantity_contracts"]
        ),
        price_tick_usdt=str(normalized_market["price_tick_usdt"]),
        long_protective_stop_price=expected_long_stop,
        short_protective_stop_price=expected_short_stop,
        equity_usdt=account_values["equity_usdt"],
        margin_used_usdt=account_values["margin_used_usdt"],
        margin_available_usdt=account_values["margin_available_usdt"],
        account_max_gross_leverage=account_values[
            "max_gross_leverage"
        ],
        risk_policy_items=risk_policy_items,
        entry_scale_grid_pct=entry_grid,
        partial_exit_scale_grid_pct=partial_exit_grid,
        allowed_entry_roles=roles,
        legal_candidate_count=legal_count,
    )
    # Rebuild both documents once at construction so no invalid runtime object
    # escapes this boundary.
    build_lot_position_truth(
        symbol=runtime.symbol, position_truth=runtime.position_truth_input()
    )
    build_market_economics_snapshot(
        decision_at=runtime.decision_at,
        market_economics=runtime.market_economics_input(),
    )
    return runtime


def build_frozen_shadow_financial_evaluation(
    *,
    runtime: FrozenFinancialShadowRuntime,
    experiment_contract: Mapping[str, Any],
    native_market_economics: Mapping[str, Any],
    cycle_index: int,
    evaluated_at: str,
    probability_mode: ProbabilityMode,
    probability_cloud_digest: str,
    candidates: Sequence[Mapping[str, Any]],
    calibration_receipt_digests: Sequence[str] = (),
    proper_scoring_receipt_digests: Sequence[str] = (),
    oos_evaluation_receipt_digests: Sequence[str] = (),
) -> tuple[PortfolioDecisionContext, dict[str, Any]]:
    """Build the official receipt without accepting financial caller fields."""

    if not isinstance(runtime, FrozenFinancialShadowRuntime):
        raise V31FinancialShadowError("V31_FINANCIAL_RUNTIME_REQUIRED")
    verify_frozen_financial_shadow_runtime(
        runtime=runtime,
        experiment_contract=experiment_contract,
        native_market_economics=native_market_economics,
    )
    context = runtime.decision_context(
        probability_mode=probability_mode,
        probability_cloud_digest=probability_cloud_digest,
        calibration_receipt_digests=calibration_receipt_digests,
        proper_scoring_receipt_digests=proper_scoring_receipt_digests,
        oos_evaluation_receipt_digests=oos_evaluation_receipt_digests,
    )
    try:
        receipt = build_financial_evaluation_receipt(
            run_id=runtime.run_id,
            cycle_index=cycle_index,
            decision_at=runtime.decision_at,
            evaluated_at=evaluated_at,
            symbol=runtime.symbol,
            position_truth=runtime.position_truth_input(),
            risk_policy=runtime.risk_policy_input(),
            market_economics=runtime.market_economics_input(),
            probability_mode=probability_mode,
            probability_cloud_digest=probability_cloud_digest,
            calibration_receipt_digests=calibration_receipt_digests,
            proper_scoring_receipt_digests=proper_scoring_receipt_digests,
            oos_evaluation_receipt_digests=oos_evaluation_receipt_digests,
            candidates=candidates,
        )
    except FinancialEvaluationError as exc:
        raise V31FinancialShadowError(
            "V31_FINANCIAL_RUNTIME_EVALUATION_FAILED"
        ) from exc
    return context, receipt


def verify_frozen_financial_shadow_runtime(
    *,
    runtime: FrozenFinancialShadowRuntime,
    experiment_contract: Mapping[str, Any],
    native_market_economics: Mapping[str, Any],
) -> str:
    """Rebuild from the frozen sources and reject any caller-side drift."""

    if not isinstance(runtime, FrozenFinancialShadowRuntime):
        raise V31FinancialShadowError("V31_FINANCIAL_RUNTIME_REQUIRED")
    rebuilt = build_frozen_financial_shadow_runtime(
        experiment_contract=experiment_contract,
        decision_at=runtime.decision_at,
        native_market_economics=native_market_economics,
    )
    if rebuilt != runtime:
        raise V31FinancialShadowError("V31_FINANCIAL_RUNTIME_DRIFT")
    return runtime.experiment_contract_digest


__all__ = [
    "FrozenFinancialShadowRuntime",
    "V31FinancialShadowError",
    "build_frozen_financial_shadow_runtime",
    "build_frozen_shadow_financial_evaluation",
    "verify_frozen_financial_shadow_runtime",
]
