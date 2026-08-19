"""Counterfactual portfolio reducer using the deterministic bar matcher."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from ...domain.common import ReducerStatus
from ...domain.matching import (
    BarrierOrder,
    BarrierType,
    ClosedBar,
    MatchingPolicy,
    OrderSide,
    match_closed_bar,
)
from .model import (
    Attribution,
    FillRecord,
    LotSide,
    OfflineLot,
    PortfolioSnapshot,
    PortfolioState,
)


ZERO = Decimal("0")


class PortfolioReplayError(ValueError):
    pass


def _pnl(side: LotSide, entry: Decimal, exit_price: Decimal, quantity: Decimal, multiplier: Decimal) -> Decimal:
    direction = Decimal("1") if side is LotSide.LONG else Decimal("-1")
    return (exit_price - entry) * quantity * multiplier * direction


def open_lot(
    state: PortfolioState,
    *,
    lot: OfflineLot,
    fee_rate: Decimal,
    fill_id: str,
    charge_entry_fee: bool,
) -> PortfolioState:
    if any(existing.lot_id == lot.lot_id for existing in state.lots):
        raise PortfolioReplayError("PORTFOLIO_DUPLICATE_LOT")
    if not isinstance(fee_rate, Decimal) or fee_rate < ZERO:
        raise PortfolioReplayError("MATCHING_COST_POLICY_UNKNOWN")
    notional = lot.quantity * lot.entry_price * lot.contract_multiplier
    fee = notional * fee_rate if charge_entry_fee else ZERO
    fill = FillRecord(
        fill_id=fill_id,
        lot_id=lot.lot_id,
        instrument_id=lot.instrument_id,
        side="BUY" if lot.side is LotSide.LONG else "SELL",
        quantity=lot.quantity,
        fill_price=lot.entry_price,
        notional=notional,
        fee=fee,
        realized_pnl_before_fee=ZERO,
        occurred_at=lot.opened_at,
        reason=(
            "COUNTERFACTUAL_STAGE_ENTRY"
            if lot.attribution is Attribution.STRATEGY
            else "EXOGENOUS_INITIAL_POSITION_NO_ENTRY_FILL"
        ),
        attribution=lot.attribution,
    )
    return replace(
        state,
        revision=state.revision + 1,
        total_fees=state.total_fees + fee,
        lots=(*state.lots, lot),
        fills=(*state.fills, fill),
    )


def close_lot(
    state: PortfolioState,
    *,
    lot_id: str,
    quantity: Decimal,
    fill_price: Decimal,
    fee: Decimal,
    occurred_at: datetime,
    reason: str,
    fill_id: str,
) -> PortfolioState:
    if occurred_at.tzinfo is None:
        raise PortfolioReplayError("CLOCK_TIME_INVALID")
    selected = next((lot for lot in state.lots if lot.lot_id == lot_id), None)
    if selected is None or quantity <= ZERO or quantity > selected.remaining_quantity:
        raise PortfolioReplayError("PORTFOLIO_RESULT_STALE")
    pnl = _pnl(
        selected.side,
        selected.entry_price,
        fill_price,
        quantity,
        selected.contract_multiplier,
    )
    updated_lots = tuple(
        replace(lot, remaining_quantity=lot.remaining_quantity - quantity)
        if lot.lot_id == lot_id
        else lot
        for lot in state.lots
    )
    fill = FillRecord(
        fill_id=fill_id,
        lot_id=selected.lot_id,
        instrument_id=selected.instrument_id,
        side="SELL" if selected.side is LotSide.LONG else "BUY",
        quantity=quantity,
        fill_price=fill_price,
        notional=quantity * fill_price * selected.contract_multiplier,
        fee=fee,
        realized_pnl_before_fee=pnl,
        occurred_at=occurred_at,
        reason=reason,
        attribution=selected.attribution,
    )
    return replace(
        state,
        revision=state.revision + 1,
        realized_pnl_before_cost=state.realized_pnl_before_cost + pnl,
        total_fees=state.total_fees + fee,
        lots=updated_lots,
        fills=(*state.fills, fill),
    )


def _orders_for_lot(lot: OfflineLot, bar: ClosedBar) -> tuple[BarrierOrder, ...]:
    side = OrderSide.SELL if lot.side is LotSide.LONG else OrderSide.BUY
    orders: list[BarrierOrder] = []
    common = {
        "instrument_id": lot.instrument_id,
        "venue_id": bar.venue_id,
        "side": side,
        "quantity": lot.remaining_quantity,
        "remaining_quantity": lot.remaining_quantity,
        "reduce_only": True,
        "active_from": bar.open_time,
        "active_until": bar.close_time,
        "lot_id": lot.lot_id,
        "stage_id": lot.stage_id,
        "geometry_id": lot.geometry_id or f"legacy-protection:{lot.lot_id}",
    }
    if lot.stop_price is not None:
        orders.append(
            BarrierOrder(
                order_id=f"{lot.lot_id}:stop",
                barrier_type=BarrierType.STOP_MARKET,
                trigger_price=lot.stop_price,
                limit_price=None,
                protection_priority=1,
                **common,
            )
        )
    if lot.target_price is not None:
        orders.append(
            BarrierOrder(
                order_id=f"{lot.lot_id}:target",
                barrier_type=BarrierType.TARGET_LIMIT,
                trigger_price=None,
                limit_price=lot.target_price,
                protection_priority=4,
                **common,
            )
        )
    return tuple(orders)


def replay_protective_bar(
    state: PortfolioState,
    *,
    bar: ClosedBar,
    policy: MatchingPolicy,
    decision_cutoff: datetime,
) -> PortfolioState:
    current = state
    for lot in sorted(
        (
            item
            for item in current.lots
            if item.instrument_id == bar.instrument_id and item.remaining_quantity > ZERO
        ),
        key=lambda item: item.lot_id,
    ):
        result = match_closed_bar(
            bar=bar,
            orders=_orders_for_lot(lot, bar),
            policy=policy,
            decision_cutoff=decision_cutoff,
        )
        if result.status is ReducerStatus.NO_CHANGE:
            continue
        if result.status is not ReducerStatus.APPLIED or result.value is None:
            raise PortfolioReplayError(
                result.error.code if result.error else "OFFLINE_REPLAY_FAILED_NO_COMMIT"
            )
        match = result.value
        current = close_lot(
            current,
            lot_id=lot.lot_id,
            quantity=match.fill_quantity,
            fill_price=match.fill_price,
            fee=match.fee,
            occurred_at=bar.available_at,
            reason=match.barrier_type.value,
            fill_id=f"{bar.bar_id}:{match.order_id}",
        )
    return current


def mark_portfolio(
    state: PortfolioState,
    *,
    marks: dict[str, Decimal],
    marked_at: datetime,
) -> PortfolioSnapshot:
    if marked_at.tzinfo is None:
        raise PortfolioReplayError("CLOCK_TIME_INVALID")
    unrealized = ZERO
    gross = ZERO
    open_risk = ZERO
    unknown_risk = False
    unprotected: list[str] = []
    for lot in state.lots:
        if lot.remaining_quantity == ZERO:
            continue
        mark = marks.get(lot.instrument_id)
        if mark is None or not isinstance(mark, Decimal):
            raise PortfolioReplayError("PORTFOLIO_RESULT_STALE")
        unrealized += _pnl(
            lot.side,
            lot.entry_price,
            mark,
            lot.remaining_quantity,
            lot.contract_multiplier,
        )
        gross += lot.remaining_quantity * mark * lot.contract_multiplier
        if lot.stop_price is None:
            unknown_risk = True
            unprotected.append(lot.lot_id)
        else:
            adverse = (
                max(lot.entry_price - lot.stop_price, ZERO)
                if lot.side is LotSide.LONG
                else max(lot.stop_price - lot.entry_price, ZERO)
            )
            open_risk += adverse * lot.remaining_quantity * lot.contract_multiplier
    net = state.realized_pnl_before_cost + unrealized - state.total_fees
    return PortfolioSnapshot(
        portfolio_id=state.portfolio_id,
        revision=state.revision,
        marked_at=marked_at,
        marks=tuple(sorted(marks.items())),
        realized_pnl_before_cost=state.realized_pnl_before_cost,
        unrealized_pnl=unrealized,
        total_fees=state.total_fees,
        net_pnl=net,
        equity=state.initial_equity + net,
        gross_notional=gross,
        open_risk_to_stop=None if unknown_risk else open_risk,
        unprotected_lot_ids=tuple(sorted(unprotected)),
    )

