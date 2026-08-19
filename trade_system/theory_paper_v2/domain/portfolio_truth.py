"""Lot-owned portfolio truth for the continuous research core.

The caller supplies atomic lots, pending orders, and account margin fields.  All
aggregates used by action evaluation are derived here; no caller-supplied gross,
net, risk, quantity, or leverage total is trusted.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .contracts.canonical import canonical_decimal, self_digest, verify_self_digest


class PortfolioTruthError(ValueError):
    """Atomic position, order, margin, or leverage truth is inconsistent."""


_POSITION_FIELDS = frozenset(
    {
        "intended_side",
        "mark_price",
        "contract_multiplier",
        "reentry_contract_active",
        "account",
        "lots",
        "pending_orders",
    }
)
_ACCOUNT_FIELDS = frozenset(
    {
        "equity_usdt",
        "margin_used_usdt",
        "margin_available_usdt",
        "max_gross_leverage",
    }
)
_LOT_FIELDS = frozenset(
    {
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
    }
)
_ORDER_FIELDS = frozenset(
    {
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
    }
)
_ROLES = frozenset({"CORE", "TACTICAL"})
_SIDES = frozenset({"LONG", "SHORT"})
_POSITION_SIDES = _SIDES | {"FLAT"}
_ORDER_INTENTS = frozenset(
    {"OPEN", "ADD", "REDUCE", "EXIT", "PROTECTIVE_STOP", "REENTER"}
)
_ZERO = Decimal("0")


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise PortfolioTruthError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PortfolioTruthError(code) from exc
    if not result.is_finite():
        raise PortfolioTruthError(code)
    return result


def _ids(value: Any, code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise PortfolioTruthError(code)
    result = tuple(value)
    if len(result) != len(set(result)) or (not allow_empty and not result):
        raise PortfolioTruthError(code)
    return result


def _risk(side: str, quantity: Decimal, mark: Decimal, stop: Decimal) -> Decimal:
    if (side == "LONG" and stop >= mark) or (side == "SHORT" and stop <= mark):
        raise PortfolioTruthError("PORTFOLIO_STOP_WRONG_SIDE")
    return quantity * abs(mark - stop)


def build_lot_position_truth(
    *, symbol: str, position_truth: Mapping[str, Any]
) -> dict[str, Any]:
    """Normalize atomic portfolio facts and derive every aggregate once."""

    if (
        not symbol
        or not isinstance(position_truth, Mapping)
        or set(position_truth) != _POSITION_FIELDS
    ):
        raise PortfolioTruthError("PORTFOLIO_TRUTH_SCHEMA_INVALID")
    intended_side = str(position_truth.get("intended_side") or "")
    if intended_side not in _POSITION_SIDES:
        raise PortfolioTruthError("PORTFOLIO_SIDE_INVALID")
    target_mark = _decimal(position_truth.get("mark_price"), "PORTFOLIO_MARK_INVALID")
    target_multiplier = _decimal(
        position_truth.get("contract_multiplier"),
        "PORTFOLIO_MULTIPLIER_INVALID",
    )
    if target_mark <= 0 or target_multiplier <= 0:
        raise PortfolioTruthError("PORTFOLIO_MARK_INVALID")
    if not isinstance(position_truth.get("reentry_contract_active"), bool):
        raise PortfolioTruthError("PORTFOLIO_REENTRY_FLAG_INVALID")

    account = position_truth.get("account")
    if not isinstance(account, Mapping) or set(account) != _ACCOUNT_FIELDS:
        raise PortfolioTruthError("PORTFOLIO_ACCOUNT_SCHEMA_INVALID")
    equity = _decimal(account.get("equity_usdt"), "PORTFOLIO_ACCOUNT_INVALID")
    margin_used = _decimal(
        account.get("margin_used_usdt"), "PORTFOLIO_ACCOUNT_INVALID"
    )
    margin_available = _decimal(
        account.get("margin_available_usdt"), "PORTFOLIO_ACCOUNT_INVALID"
    )
    leverage_cap = _decimal(
        account.get("max_gross_leverage"), "PORTFOLIO_ACCOUNT_INVALID"
    )
    if (
        equity <= 0
        or min(margin_used, margin_available) < 0
        or leverage_cap <= 0
        or margin_used + margin_available != equity
    ):
        raise PortfolioTruthError("PORTFOLIO_ACCOUNT_INVALID")

    raw_lots = position_truth.get("lots")
    if not isinstance(raw_lots, list):
        raise PortfolioTruthError("PORTFOLIO_LOTS_INVALID")
    lots: list[dict[str, Any]] = []
    lot_by_id: dict[str, dict[str, Any]] = {}
    gross = _ZERO
    net = _ZERO
    open_risk = _ZERO
    lot_margin = _ZERO
    target_quantity = _ZERO
    target_open_risk = _ZERO
    target_open_notional = _ZERO
    for raw in raw_lots:
        if not isinstance(raw, Mapping) or set(raw) != _LOT_FIELDS:
            raise PortfolioTruthError("PORTFOLIO_LOT_SCHEMA_INVALID")
        lot_id = str(raw.get("lot_id") or "")
        lot_symbol = str(raw.get("symbol") or "")
        side = str(raw.get("side") or "")
        role = str(raw.get("role") or "")
        if (
            not lot_id
            or lot_id in lot_by_id
            or not lot_symbol
            or side not in _SIDES
            or role not in _ROLES
        ):
            raise PortfolioTruthError("PORTFOLIO_LOT_IDENTITY_INVALID")
        quantity = _decimal(raw.get("quantity"), "PORTFOLIO_LOT_VALUE_INVALID")
        entry = _decimal(raw.get("entry_price"), "PORTFOLIO_LOT_VALUE_INVALID")
        mark = _decimal(raw.get("mark_price"), "PORTFOLIO_LOT_VALUE_INVALID")
        stop = _decimal(raw.get("stop_price"), "PORTFOLIO_LOT_VALUE_INVALID")
        multiplier = _decimal(
            raw.get("contract_multiplier"), "PORTFOLIO_LOT_VALUE_INVALID"
        )
        margin = _decimal(
            raw.get("margin_used_usdt"), "PORTFOLIO_LOT_VALUE_INVALID"
        )
        if min(quantity, entry, mark, stop, multiplier) <= 0 or margin < 0:
            raise PortfolioTruthError("PORTFOLIO_LOT_VALUE_INVALID")
        lot_risk = _risk(side, quantity, mark, stop) * multiplier
        notional = quantity * mark * multiplier
        normalized = {
            "lot_id": lot_id,
            "symbol": lot_symbol,
            "side": side,
            "role": role,
            "quantity": canonical_decimal(quantity),
            "entry_price": canonical_decimal(entry),
            "mark_price": canonical_decimal(mark),
            "stop_price": canonical_decimal(stop),
            "contract_multiplier": canonical_decimal(multiplier),
            "margin_used_usdt": canonical_decimal(margin),
            "notional_usdt": canonical_decimal(notional),
            "open_risk_usdt": canonical_decimal(lot_risk),
        }
        lots.append(normalized)
        lot_by_id[lot_id] = normalized
        gross += notional
        net += notional if side == "LONG" else -notional
        open_risk += lot_risk
        lot_margin += margin
        if lot_symbol == symbol:
            if intended_side == "FLAT":
                raise PortfolioTruthError(
                    "PORTFOLIO_FLAT_TARGET_LOT_FORBIDDEN"
                )
            if side != intended_side or mark != target_mark or multiplier != target_multiplier:
                raise PortfolioTruthError("PORTFOLIO_TARGET_LOT_MISMATCH")
            target_quantity += quantity
            target_open_risk += lot_risk
            target_open_notional += notional

    raw_orders = position_truth.get("pending_orders")
    if not isinstance(raw_orders, list):
        raise PortfolioTruthError("PORTFOLIO_ORDERS_INVALID")
    orders: list[dict[str, Any]] = []
    order_ids: set[str] = set()
    order_margin = _ZERO
    pending_open_notional = _ZERO
    pending_open_risk = _ZERO
    target_pending_notional = _ZERO
    target_pending_risk = _ZERO
    for raw in raw_orders:
        if not isinstance(raw, Mapping) or set(raw) != _ORDER_FIELDS:
            raise PortfolioTruthError("PORTFOLIO_ORDER_SCHEMA_INVALID")
        order_id = str(raw.get("order_id") or "")
        order_symbol = str(raw.get("symbol") or "")
        side = str(raw.get("side") or "")
        intent = str(raw.get("intent") or "")
        reduce_only = raw.get("reduce_only")
        targets = _ids(
            raw.get("target_lot_ids"),
            "PORTFOLIO_ORDER_TARGET_INVALID",
            allow_empty=True,
        )
        if (
            not order_id
            or order_id in order_ids
            or not order_symbol
            or side not in _SIDES
            or intent not in _ORDER_INTENTS
            or not isinstance(reduce_only, bool)
            or any(target not in lot_by_id for target in targets)
        ):
            raise PortfolioTruthError("PORTFOLIO_ORDER_IDENTITY_INVALID")
        if intended_side == "FLAT" and order_symbol == symbol:
            raise PortfolioTruthError(
                "PORTFOLIO_FLAT_TARGET_ORDER_FORBIDDEN"
            )
        quantity = _decimal(raw.get("quantity"), "PORTFOLIO_ORDER_VALUE_INVALID")
        reference = _decimal(
            raw.get("reference_price"), "PORTFOLIO_ORDER_VALUE_INVALID"
        )
        multiplier = _decimal(
            raw.get("contract_multiplier"), "PORTFOLIO_ORDER_VALUE_INVALID"
        )
        reserved_margin = _decimal(
            raw.get("reserved_margin_usdt"), "PORTFOLIO_ORDER_VALUE_INVALID"
        )
        stop_raw = raw.get("stop_price")
        stop = (
            None
            if stop_raw is None
            else _decimal(stop_raw, "PORTFOLIO_ORDER_VALUE_INVALID")
        )
        if quantity <= 0 or reference <= 0 or multiplier <= 0 or reserved_margin < 0:
            raise PortfolioTruthError("PORTFOLIO_ORDER_VALUE_INVALID")
        if reduce_only:
            if not targets or reserved_margin != 0:
                raise PortfolioTruthError("PORTFOLIO_REDUCE_ORDER_INVALID")
            target_rows = [lot_by_id[target] for target in targets]
            if any(
                row["symbol"] != order_symbol
                or row["side"] != side
                or _decimal(
                    row["contract_multiplier"], "PORTFOLIO_ORDER_VALUE_INVALID"
                )
                != multiplier
                for row in target_rows
            ) or quantity > sum(
                (_decimal(row["quantity"], "PORTFOLIO_ORDER_VALUE_INVALID") for row in target_rows),
                _ZERO,
            ):
                raise PortfolioTruthError("PORTFOLIO_REDUCE_ORDER_INVALID")
            if stop is not None and stop <= 0:
                raise PortfolioTruthError("PORTFOLIO_ORDER_VALUE_INVALID")
            order_risk = _ZERO
            order_notional = _ZERO
        else:
            if targets or stop is None or stop <= 0:
                raise PortfolioTruthError("PORTFOLIO_OPEN_ORDER_INVALID")
            order_risk = _risk(side, quantity, reference, stop) * multiplier
            order_notional = quantity * reference * multiplier
            pending_open_risk += order_risk
            pending_open_notional += order_notional
            if order_symbol == symbol:
                if side != intended_side or multiplier != target_multiplier:
                    raise PortfolioTruthError("PORTFOLIO_TARGET_ORDER_MISMATCH")
                target_pending_risk += order_risk
                target_pending_notional += order_notional
        order_margin += reserved_margin
        orders.append(
            {
                "order_id": order_id,
                "symbol": order_symbol,
                "side": side,
                "intent": intent,
                "quantity": canonical_decimal(quantity),
                "reference_price": canonical_decimal(reference),
                "stop_price": None if stop is None else canonical_decimal(stop),
                "contract_multiplier": canonical_decimal(multiplier),
                "reduce_only": reduce_only,
                "target_lot_ids": list(targets),
                "reserved_margin_usdt": canonical_decimal(reserved_margin),
                "pending_open_notional_usdt": canonical_decimal(order_notional),
                "pending_open_risk_usdt": canonical_decimal(order_risk),
            }
        )
        order_ids.add(order_id)

    if lot_margin + order_margin != margin_used:
        raise PortfolioTruthError("PORTFOLIO_MARGIN_RECONCILIATION_FAILED")
    committed_gross = gross + pending_open_notional
    committed_risk = open_risk + pending_open_risk
    gross_leverage = committed_gross / equity
    if gross_leverage > leverage_cap:
        raise PortfolioTruthError("PORTFOLIO_LEVERAGE_CAP_BREACH")

    document = {
        "schema_id": "continuous_lot_position_truth",
        "schema_version": "1.0.0",
        "symbol": symbol,
        "intended_side": intended_side,
        "mark_price": canonical_decimal(target_mark),
        "contract_multiplier": canonical_decimal(target_multiplier),
        "reentry_contract_active": position_truth.get("reentry_contract_active")
        is True,
        "account": {
            "equity_usdt": canonical_decimal(equity),
            "margin_used_usdt": canonical_decimal(margin_used),
            "margin_available_usdt": canonical_decimal(margin_available),
            "max_gross_leverage": canonical_decimal(leverage_cap),
            "gross_notional_usdt": canonical_decimal(gross),
            "net_notional_usdt": canonical_decimal(net),
            "pending_open_notional_usdt": canonical_decimal(pending_open_notional),
            "committed_gross_notional_usdt": canonical_decimal(committed_gross),
            "open_risk_usdt": canonical_decimal(open_risk),
            "pending_order_risk_usdt": canonical_decimal(pending_open_risk),
            "committed_risk_usdt": canonical_decimal(committed_risk),
            "gross_leverage": canonical_decimal(gross_leverage),
        },
        "target_symbol": {
            "current_quantity": canonical_decimal(target_quantity),
            "open_notional_usdt": canonical_decimal(target_open_notional),
            "pending_open_notional_usdt": canonical_decimal(target_pending_notional),
            "open_risk_usdt": canonical_decimal(target_open_risk),
            "pending_order_risk_usdt": canonical_decimal(target_pending_risk),
        },
        "lots": sorted(lots, key=lambda row: row["lot_id"]),
        "pending_orders": sorted(orders, key=lambda row: row["order_id"]),
    }
    return self_digest(document, "position_truth_digest")


def candidate_lot_scope(
    *,
    position_truth: Mapping[str, Any],
    action_class: str,
    target_lot_ids: Any,
    target_lot_role: Any,
) -> tuple[tuple[str, ...], str, Decimal]:
    """Validate candidate ownership and return its exact target quantity."""

    try:
        verify_self_digest(position_truth, "position_truth_digest")
    except ValueError as exc:
        raise PortfolioTruthError("PORTFOLIO_TRUTH_DIGEST_INVALID") from exc
    targets = _ids(
        target_lot_ids, "ACTION_TARGET_LOTS_INVALID", allow_empty=True
    )
    role = str(target_lot_role or "")
    if role not in _ROLES:
        raise PortfolioTruthError("ACTION_TARGET_ROLE_INVALID")
    lots = {str(row["lot_id"]): row for row in position_truth["lots"]}
    symbol = str(position_truth["symbol"])
    side = str(position_truth["intended_side"])
    if action_class in {"OPEN", "REENTER"}:
        if targets:
            raise PortfolioTruthError("ACTION_NEW_EXPOSURE_TARGETS_EXISTING_LOT")
        return (), role, _ZERO
    if any(target not in lots for target in targets):
        raise PortfolioTruthError("ACTION_TARGET_LOTS_INVALID")
    target_rows = [lots[target] for target in targets]
    if any(
        row["symbol"] != symbol or row["side"] != side or row["role"] != role
        for row in target_rows
    ):
        raise PortfolioTruthError("ACTION_TARGET_LOT_SCOPE_MISMATCH")
    if action_class in {"ADD", "REDUCE", "PARTIAL_TAKE_PROFIT", "EXIT"} and not targets:
        role_lot_ids = {
            lot_id
            for lot_id, row in lots.items()
            if row["symbol"] == symbol and row["side"] == side and row["role"] == role
        }
        if role_lot_ids:
            raise PortfolioTruthError("ACTION_TARGET_LOTS_REQUIRED")
    if action_class in {"HOLD", "WAIT"}:
        role_lot_ids = {
            lot_id
            for lot_id, row in lots.items()
            if row["symbol"] == symbol and row["side"] == side and row["role"] == role
        }
        if set(targets) != role_lot_ids:
            raise PortfolioTruthError("ACTION_HOLD_WAIT_SCOPE_INCOMPLETE")
    quantity = sum(
        (_decimal(row["quantity"], "ACTION_TARGET_QUANTITY_INVALID") for row in target_rows),
        _ZERO,
    )
    return targets, role, quantity


__all__ = [
    "PortfolioTruthError",
    "build_lot_position_truth",
    "candidate_lot_scope",
]
