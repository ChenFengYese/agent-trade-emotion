"""Deterministic conservative matcher; it has no network or order authority."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from ..common import DomainError, DomainResult, ReducerStatus
from .model import (
    BarrierOrder,
    BarrierType,
    ClosedBar,
    LimitTouchPolicy,
    MatchResult,
    MatchingPolicy,
    OrderSide,
)


PRIORITY = {
    BarrierType.KILL: 0,
    BarrierType.ACCOUNT_MISMATCH: 0,
    BarrierType.STOP_MARKET: 1,
    BarrierType.PROTECTION_REPAIR: 2,
    BarrierType.STRUCTURE_EXIT_MARKET: 3,
    BarrierType.TARGET_LIMIT: 4,
    BarrierType.TIMEOUT: 5,
    BarrierType.ENTRY_STOP_MARKET: 6,
    BarrierType.ENTRY_LIMIT: 7,
    BarrierType.BARRIER_UPDATE: 8,
}


def _error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> DomainResult[MatchResult]:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if retryable else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="MATCHING",
            retryability="AFTER_INPUT_REPAIR" if retryable else "NEVER",
            message=message,
        ),
    )


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _aligned(value: Decimal, quantum: Decimal) -> bool:
    return value % quantum == 0


def _snap_adverse(
    value: Decimal,
    tick: Decimal,
    side: OrderSide,
) -> Decimal:
    rounding = ROUND_CEILING if side is OrderSide.BUY else ROUND_FLOOR
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _market_fill(
    base: Decimal,
    policy: MatchingPolicy,
    side: OrderSide,
) -> tuple[Decimal, Decimal]:
    assert policy.adverse_slippage_bps is not None
    assert policy.price_tick is not None
    fraction = policy.adverse_slippage_bps / Decimal("10000")
    raw = base * (
        Decimal("1") + fraction
        if side is OrderSide.BUY
        else Decimal("1") - fraction
    )
    fill = _snap_adverse(raw, policy.price_tick, side)
    return fill, abs(fill - base)


def _stop_touched(order: BarrierOrder, bar: ClosedBar) -> bool:
    assert order.trigger_price is not None
    if order.side is OrderSide.SELL:
        return bar.low <= order.trigger_price
    return bar.high >= order.trigger_price


def _limit_state(
    order: BarrierOrder,
    bar: ClosedBar,
    tick: Decimal,
    policy: MatchingPolicy,
) -> str:
    assert order.limit_price is not None
    if policy.limit_touch_policy is LimitTouchPolicy.ACTUAL_FILL_ONLY:
        touched = (
            bar.high >= order.limit_price
            if order.side is OrderSide.SELL
            else bar.low <= order.limit_price
        )
        return "INSUFFICIENT" if touched else "NONE"
    if order.side is OrderSide.SELL:
        if bar.high >= order.limit_price + tick:
            return "CROSSED"
        if bar.high >= order.limit_price:
            return "INSUFFICIENT"
    else:
        if bar.low <= order.limit_price - tick:
            return "CROSSED"
        if bar.low <= order.limit_price:
            return "INSUFFICIENT"
    return "NONE"


def _market_base(order: BarrierOrder, bar: ClosedBar) -> Decimal:
    if order.barrier_type in {
        BarrierType.STOP_MARKET,
        BarrierType.ENTRY_STOP_MARKET,
    }:
        assert order.trigger_price is not None
        if order.side is OrderSide.SELL and bar.open <= order.trigger_price:
            return bar.open
        if order.side is OrderSide.BUY and bar.open >= order.trigger_price:
            return bar.open
        return order.trigger_price
    return bar.open


def match_closed_bar(
    *,
    bar: ClosedBar,
    orders: tuple[BarrierOrder, ...],
    policy: MatchingPolicy,
    decision_cutoff: datetime,
) -> DomainResult[MatchResult]:
    """Evaluate one lineage-valid bar available at the current PIT cutoff."""

    if not _is_utc(decision_cutoff):
        return _error(
            "MATCHING_FUTURE_BAR_FORBIDDEN",
            "decision cutoff must be a UTC timestamp",
        )
    if policy.price_tick is None or policy.quantity_step is None:
        return _error(
            "MATCHING_TICK_OR_STEP_UNKNOWN",
            "tick and quantity step are mandatory",
            retryable=True,
        )
    if policy.contract_multiplier is None:
        return _error(
            "MATCHING_MULTIPLIER_UNKNOWN",
            "contract multiplier is mandatory",
            retryable=True,
        )
    if policy.fee_rate is None or policy.adverse_slippage_bps is None:
        return _error(
            "MATCHING_COST_POLICY_UNKNOWN",
            "fee and adverse slippage policy are mandatory",
            retryable=True,
        )
    if (
        bar.close_time > decision_cutoff
        or bar.available_at > decision_cutoff
        or bar.ingested_at > decision_cutoff
        or bar.source_committed_at > decision_cutoff
    ):
        return _error(
            "MATCHING_FUTURE_BAR_FORBIDDEN",
            "matching cannot read an unclosed or not-yet-available bar",
        )
    if not bar.source_commit_receipt_valid or not bar.lineage_digest_valid:
        return _error(
            "MATCHING_BAR_LINEAGE_INVALID",
            "bar lineage or source commit receipt is invalid",
        )
    if (
        bar.instrument_id != policy.instrument_id
        or bar.venue_id != policy.venue_id
    ):
        return _error(
            "MATCHING_POLICY_MISSING",
            "policy does not own this instrument and venue",
            retryable=True,
        )
    if not orders:
        return DomainResult(status=ReducerStatus.NO_CHANGE)

    touched: list[BarrierOrder] = []
    insufficient_limits: list[BarrierOrder] = []
    for order in orders:
        if (
            order.instrument_id != policy.instrument_id
            or order.venue_id != policy.venue_id
        ):
            return _error(
                "MATCHING_POLICY_MISSING",
                f"order {order.order_id} does not match policy identity",
                retryable=True,
            )
        # A partially covered bar has unknown intrabar activation ordering.
        if (
            order.active_from > bar.open_time
            or order.active_until < bar.close_time
        ):
            return _error(
                "MATCHING_BARRIER_INACTIVE",
                f"order {order.order_id} was not active for the whole closed bar",
            )
        if (
            not _aligned(order.quantity, policy.quantity_step)
            or not _aligned(order.remaining_quantity, policy.quantity_step)
            or (
                order.trigger_price is not None
                and not _aligned(order.trigger_price, policy.price_tick)
            )
            or (
                order.limit_price is not None
                and not _aligned(order.limit_price, policy.price_tick)
            )
        ):
            return _error(
                "MATCHING_TICK_OR_STEP_UNKNOWN",
                f"order {order.order_id} is not aligned to frozen tick/step",
            )
        if order.remaining_quantity == 0:
            continue
        if order.barrier_type in {
            BarrierType.STOP_MARKET,
            BarrierType.ENTRY_STOP_MARKET,
        }:
            if _stop_touched(order, bar):
                touched.append(order)
        elif order.barrier_type in {
            BarrierType.TARGET_LIMIT,
            BarrierType.ENTRY_LIMIT,
        }:
            limit_state = _limit_state(order, bar, policy.price_tick, policy)
            if limit_state == "CROSSED":
                touched.append(order)
            elif limit_state == "INSUFFICIENT":
                insufficient_limits.append(order)
        elif order.barrier_type is not BarrierType.BARRIER_UPDATE:
            if order.event_triggered:
                touched.append(order)

    if not touched:
        if insufficient_limits:
            return _error(
                "MATCHING_LIMIT_TOUCH_INSUFFICIENT",
                "a limit was touched but did not cross by the registered tick",
            )
        return DomainResult(status=ReducerStatus.NO_CHANGE)

    touched.sort(key=lambda order: (PRIORITY[order.barrier_type], order.order_id))
    winner = touched[0]
    same_priority = [
        order
        for order in touched
        if PRIORITY[order.barrier_type] == PRIORITY[winner.barrier_type]
    ]
    if len(same_priority) > 1:
        return _error(
            "MATCHING_AMBIGUOUS_BARRIER_ORDER",
            "two unorderable barriers share the same highest priority",
        )

    stop_touched = next(
        (
            order
            for order in touched
            if order.barrier_type is BarrierType.STOP_MARKET
        ),
        None,
    )
    target_touched = next(
        (
            order
            for order in touched
            if order.barrier_type is BarrierType.TARGET_LIMIT
        ),
        None,
    )
    ambiguous_stop_target = (
        stop_touched is not None
        and target_touched is not None
        and (
            stop_touched.lot_id == target_touched.lot_id
            or (
                stop_touched.lot_id is None
                and stop_touched.stage_id == target_touched.stage_id
            )
        )
    )
    # STOP_FIRST is the authoritative fail-closed accounting branch.
    if ambiguous_stop_target:
        winner = stop_touched

    if winner.barrier_type in {
        BarrierType.TARGET_LIMIT,
        BarrierType.ENTRY_LIMIT,
    }:
        assert winner.limit_price is not None
        fill_price = winner.limit_price
        slippage = Decimal("0")
    else:
        fill_price, slippage = _market_fill(
            _market_base(winner, bar), policy, winner.side
        )

    fill_quantity = winner.remaining_quantity
    if policy.volume_participation_cap is not None:
        if bar.volume is None:
            return _error(
                "MATCHING_PARTIAL_FILL_UNIDENTIFIED",
                "volume-model cap is registered but bar volume is unknown",
            )
        available = bar.volume * policy.volume_participation_cap
        available = (
            available / policy.quantity_step
        ).to_integral_value(rounding=ROUND_FLOOR) * policy.quantity_step
        fill_quantity = min(fill_quantity, available)
        if fill_quantity <= 0:
            return _error(
                "MATCHING_PARTIAL_FILL_UNIDENTIFIED",
                "frozen volume model provides no aligned fill quantity",
            )

    notional = (
        fill_price * fill_quantity * policy.contract_multiplier
    )
    fee = abs(notional) * policy.fee_rate
    adverse = fill_price if ambiguous_stop_target else None
    favorable = (
        target_touched.limit_price
        if ambiguous_stop_target and target_touched is not None
        else None
    )
    diagnostics = (
        ("MATCHING_AMBIGUOUS_BARRIER_ORDER",)
        if ambiguous_stop_target
        else ()
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=MatchResult(
            order_id=winner.order_id,
            barrier_type=winner.barrier_type,
            bar_id=bar.bar_id,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            notional=notional,
            fee=fee,
            slippage_amount=slippage,
            ambiguous_barrier_order=ambiguous_stop_target,
            adverse_bound_price=adverse,
            favorable_bound_price=favorable,
            diagnostic_codes=diagnostics,
        ),
        evaluated_event_id="BARRIER_EVALUATED",
    )
