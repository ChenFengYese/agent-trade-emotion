"""Pure, replayable mark-to-market projection for the V3.3.2 paper ledger.

The paper ledger remains the sole owner of cash, positions, orders, and costs.
This module only derives a view from one immutable account version and explicit
MARK observations.  It never appends a ledger event, invents missing carry, or
claims to reproduce a venue's liquidation engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from ...domain.contracts.canonical import canonical_decimal
from ...domain.market_cycle.paper import (
    PAPER_CARRY_COVERAGE_STATUSES,
    PaperAccountVersionV1,
)


class PaperValuationError(ValueError):
    """The supplied account, MARK path, or risk parameters are inconsistent."""


def _decimal(
    value: object,
    *,
    field: str,
    nonnegative: bool = False,
    positive: bool = False,
) -> Decimal:
    if not isinstance(value, str):
        raise PaperValuationError(f"{field} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PaperValuationError(f"{field} must be a canonical decimal string") from exc
    if not parsed.is_finite() or canonical_decimal(parsed) != value:
        raise PaperValuationError(f"{field} must be a canonical decimal string")
    if nonnegative and parsed < 0:
        raise PaperValuationError(f"{field} must be nonnegative")
    if positive and parsed <= 0:
        raise PaperValuationError(f"{field} must be positive")
    return parsed


def _timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PaperValuationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperValuationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperValuationError(f"{field} must include an explicit UTC offset")
    return parsed


@dataclass(frozen=True, slots=True)
class PaperValuationProjectionV1:
    account_id: str
    account_version: int
    account_mode: str
    symbol: str
    status: str
    observed_at: str | None
    available_at: str | None
    source_sha256: str | None
    mark: str | None
    unrealized_pnl: str | None
    equity_before_unknown_costs: str | None
    carry_coverage_status: str
    carry_coverage_at_mark_status: str
    complete_equity: str | None
    gross_exposure: str | None
    effective_leverage: str | None
    effective_leverage_status: str
    peak_equity: str | None
    current_drawdown: str | None
    observed_max_drawdown: str | None
    drawdown_status: str
    drawdown_unit: str
    liquidation_buffer: str | None
    liquidation_buffer_status: str
    liquidation_parameter_source_ref: str | None
    actual_cost_effect_status: str = "UNKNOWN_NOT_EVALUATED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.paper-valuation-projection",
            "schema_version": "1.0.0",
            **{field: getattr(self, field) for field in self.__dataclass_fields__},
        }


@dataclass(frozen=True, slots=True)
class _KnownMark:
    observed_at: str
    available_at: str
    source_sha256: str
    mark: Decimal
    path_status: str

    @property
    def order_key(self) -> tuple[datetime, datetime, str]:
        return (
            _timestamp(self.observed_at, field="market.observed_at"),
            _timestamp(self.available_at, field="market.available_at"),
            self.source_sha256,
        )


def _extract_known_marks(
    account: PaperAccountVersionV1,
    market_slices: Sequence[object],
) -> tuple[_KnownMark, ...]:
    known: list[_KnownMark] = []
    by_observed_at: dict[str, Decimal] = {}
    for index, market in enumerate(market_slices):
        symbol = getattr(market, "symbol", None)
        if symbol != account.permitted_symbol:
            raise PaperValuationError(
                f"market_slices[{index}].symbol must match account permitted_symbol"
            )
        observed_at = getattr(market, "observed_at", None)
        available_at = getattr(market, "available_at", None)
        observed = _timestamp(observed_at, field=f"market_slices[{index}].observed_at")
        available = _timestamp(available_at, field=f"market_slices[{index}].available_at")
        if available < observed:
            raise PaperValuationError("market available_at must not precede observed_at")
        mark_text = getattr(market, "mark", None)
        if mark_text is None:
            continue
        mark = _decimal(mark_text, field=f"market_slices[{index}].mark", positive=True)
        prior = by_observed_at.get(observed_at)
        if prior is not None and prior != mark:
            raise PaperValuationError(
                "conflicting MARK values share the same observed_at"
            )
        by_observed_at[observed_at] = mark
        source_sha256 = getattr(market, "source_sha256", None)
        if not isinstance(source_sha256, str) or len(source_sha256) != 64:
            raise PaperValuationError("market source_sha256 must be a SHA-256 digest")
        try:
            int(source_sha256, 16)
        except ValueError as exc:
            raise PaperValuationError("market source_sha256 must be a SHA-256 digest") from exc
        path_status = getattr(market, "path_status", None)
        if path_status not in {"ORDERED", "UNORDERED"}:
            raise PaperValuationError("market path_status is unsupported")
        known.append(
            _KnownMark(
                observed_at=observed_at,
                available_at=available_at,
                source_sha256=source_sha256,
                mark=mark,
                path_status=path_status,
            )
        )
    # Exact duplicates do not add a fictitious path point.  Sorting makes
    # replay independent of caller iteration order.
    return tuple(
        sorted(
            {
                (
                    item.observed_at,
                    item.available_at,
                    item.source_sha256,
                    canonical_decimal(item.mark),
                    item.path_status,
                ): item
                for item in known
            }.values(),
            key=lambda item: item.order_key,
        )
    )


def _position_totals(
    account: PaperAccountVersionV1,
    mark: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    multiplier = _decimal(
        account.instrument_spec.contract_multiplier,
        field="instrument_spec.contract_multiplier",
        positive=True,
    )
    unrealized = Decimal("0")
    gross = Decimal("0")
    market_value = Decimal("0")
    for position in account.positions:
        if position.symbol != account.permitted_symbol:
            raise PaperValuationError("position symbol must match account permitted_symbol")
        quantity = _decimal(position.quantity, field="position.quantity")
        entry = _decimal(
            position.average_entry_price,
            field="position.average_entry_price",
            nonnegative=True,
        )
        exposure = quantity * multiplier
        unrealized += (mark - entry) * exposure
        gross += abs(exposure) * mark
        market_value += exposure * mark
    return unrealized, gross, market_value


def _equity_at(
    account: PaperAccountVersionV1,
    mark: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    unrealized, gross, market_value = _position_totals(account, mark)
    cash = _decimal(account.cash_balance, field="account.cash_balance")
    if account.account_mode == "LINEAR_PERP":
        equity = cash + unrealized
    elif account.account_mode == "CASH_SPOT":
        equity = cash + market_value
    else:  # The domain contract already rejects this; retain a local fail-close.
        raise PaperValuationError("account_mode is unsupported")
    return unrealized, equity, gross


def _drawdowns(
    equities: Sequence[Decimal],
) -> tuple[Decimal | None, Decimal | None, Decimal | None, str]:
    if not equities:
        return None, None, None, "UNKNOWN_NO_KNOWN_VALUATION_POINT"
    running_peak = equities[0]
    peak = equities[0]
    current: Decimal | None = None
    maximum: Decimal | None = None
    for equity in equities:
        running_peak = max(running_peak, equity)
        peak = max(peak, running_peak)
        if running_peak <= 0:
            continue
        drawdown = max(Decimal("0"), (running_peak - equity) / running_peak)
        current = drawdown
        maximum = drawdown if maximum is None else max(maximum, drawdown)
    if current is None or maximum is None:
        return peak, None, None, "UNKNOWN_NONPOSITIVE_PEAK_EQUITY"
    return peak, current, maximum, "OBSERVED_KNOWN_MARK_POINTS"


def _account_history(
    current: PaperAccountVersionV1,
    supplied: Sequence[PaperAccountVersionV1],
) -> tuple[PaperAccountVersionV1, ...]:
    values = tuple(supplied) or (current,)
    for item in values:
        if (
            not isinstance(item, PaperAccountVersionV1)
            or item.account_id != current.account_id
            or item.permitted_symbol != current.permitted_symbol
            or item.instrument_spec != current.instrument_spec
        ):
            raise PaperValuationError(
                "account_history must preserve account, symbol, and instrument identity"
            )
    by_version = {item.version: item for item in values}
    by_version[current.version] = current
    return tuple(
        sorted(
            by_version.values(),
            key=lambda item: (
                _timestamp(item.last_fact_at, field="account_history.last_fact_at"),
                item.version,
            ),
        )
    )


def _state_at_mark(
    history: Sequence[PaperAccountVersionV1], mark: _KnownMark
) -> PaperAccountVersionV1 | None:
    available = _timestamp(mark.available_at, field="market.available_at")
    eligible = tuple(
        item
        for item in history
        if _timestamp(item.last_fact_at, field="account_history.last_fact_at")
        <= available
    )
    return None if not eligible else eligible[-1]


def _component_complete_at(
    account: PaperAccountVersionV1, prefix: str, economic_at: str
) -> bool:
    status = getattr(account, f"{prefix}_coverage_status")
    if status == "NOT_APPLICABLE":
        return True
    end_at = getattr(account, f"{prefix}_coverage_end_at")
    return status == "COMPLETE" and end_at is not None and _timestamp(
        end_at, field=f"account.{prefix}_coverage_end_at"
    ) >= _timestamp(economic_at, field="market.observed_at")


def _state_for_current_mark(
    history: Sequence[PaperAccountVersionV1],
    current: PaperAccountVersionV1,
    mark: _KnownMark,
) -> PaperAccountVersionV1 | None:
    """Use the last economic state at the mark plus later non-cash coverage.

    Funding coverage may become provable only after the economic mark time.  A
    later coverage-only ledger version can certify that earlier cutoff, but a
    later order, fill, intent, market observation or carry cash event cannot be
    backfilled into it.
    """

    base = _state_at_mark(history, mark)
    if base is None:
        return None
    if base.version == current.version:
        return current
    later = tuple(item for item in history if item.version > base.version)
    if not later or later[-1].version != current.version:
        return None
    for previous, item in zip((base, *later[:-1]), later, strict=True):
        if (
            item.cash_balance != previous.cash_balance
            or item.reserved_margin != previous.reserved_margin
            or item.realized_pnl != previous.realized_pnl
            or item.fees_paid != previous.fees_paid
            or item.funding_paid != previous.funding_paid
            or item.borrow_paid != previous.borrow_paid
            or item.positions != previous.positions
            or item.orders != previous.orders
            or item.applied_command_ids != previous.applied_command_ids
            or item.last_market_observed_at != previous.last_market_observed_at
            or item.last_market_available_at != previous.last_market_available_at
            or item.last_market_source_sha256 != previous.last_market_source_sha256
        ):
            return None
    return current


def project_paper_valuation(
    account: PaperAccountVersionV1,
    market_slices: Sequence[object],
    *,
    carry_coverage_status: str | None = None,
    account_history: Sequence[PaperAccountVersionV1] = (),
) -> PaperValuationProjectionV1:
    """Project one immutable account across explicit current/historical MARKs.

    When ``account_history`` is supplied, each MARK is paired with the latest
    durable account version available at that point.  Drawdown is therefore a
    replay of observed account/mark points, still only a lower bound between
    samples and never a reproduction of an exchange liquidation engine.
    """

    account_carry_status = account.carry_coverage_status
    if carry_coverage_status is None:
        carry_coverage_status = account_carry_status
    if carry_coverage_status not in PAPER_CARRY_COVERAGE_STATUSES:
        raise PaperValuationError("carry_coverage_status is unsupported")
    if carry_coverage_status != account_carry_status:
        raise PaperValuationError(
            "carry_coverage_status must match the immutable account version"
        )
    marks = _extract_known_marks(account, market_slices)
    history = _account_history(account, account_history)
    spec = account.instrument_spec
    risk_is_complete = (
        spec.risk_parameter_status == "MODELED_EXPLICIT_PARAMETERS"
        and spec.maintenance_margin_rate is not None
        and spec.maintenance_margin_deduction is not None
        and spec.liquidation_fee_reserve is not None
    )
    risk_source_ref = spec.risk_parameter_set_id if risk_is_complete else None
    if not marks:
        return PaperValuationProjectionV1(
            account_id=account.account_id,
            account_version=account.version,
            account_mode=account.account_mode,
            symbol=account.permitted_symbol,
            status="UNKNOWN_NO_EXPLICIT_MARK",
            observed_at=None,
            available_at=None,
            source_sha256=None,
            mark=None,
            unrealized_pnl=None,
            equity_before_unknown_costs=None,
            carry_coverage_status=carry_coverage_status,
            carry_coverage_at_mark_status="UNKNOWN_NO_MARK",
            complete_equity=None,
            gross_exposure=None,
            effective_leverage=None,
            effective_leverage_status="UNKNOWN_EQUITY",
            peak_equity=None,
            current_drawdown=None,
            observed_max_drawdown=None,
            drawdown_status="UNKNOWN_NO_KNOWN_VALUATION_POINT",
            drawdown_unit="FRACTION",
            liquidation_buffer=None,
            liquidation_buffer_status="UNKNOWN_EQUITY",
            liquidation_parameter_source_ref=risk_source_ref,
        )

    current = marks[-1]
    valuation_account = _state_for_current_mark(history, account, current)
    if valuation_account is None:
        return PaperValuationProjectionV1(
            account_id=account.account_id,
            account_version=account.version,
            account_mode=account.account_mode,
            symbol=account.permitted_symbol,
            status="UNKNOWN_MARK_PREDATES_CURRENT_ACCOUNT_VERSION",
            observed_at=current.observed_at,
            available_at=current.available_at,
            source_sha256=current.source_sha256,
            mark=canonical_decimal(current.mark),
            unrealized_pnl=None,
            equity_before_unknown_costs=None,
            carry_coverage_status=carry_coverage_status,
            carry_coverage_at_mark_status="INCOMPLETE_AT_STALE_MARK",
            complete_equity=None,
            gross_exposure=None,
            effective_leverage=None,
            effective_leverage_status="UNKNOWN_STALE_MARK",
            peak_equity=None,
            current_drawdown=None,
            observed_max_drawdown=None,
            drawdown_status="UNKNOWN_STALE_MARK",
            drawdown_unit="FRACTION",
            liquidation_buffer=None,
            liquidation_buffer_status="UNKNOWN_STALE_MARK",
            liquidation_parameter_source_ref=risk_source_ref,
        )

    equities: list[Decimal] = [
        _decimal(history[0].initial_balance, field="account.initial_balance", positive=True)
    ]
    replayed_all = True
    for item in marks:
        historical = _state_at_mark(history, item)
        if historical is None:
            replayed_all = False
            continue
        _, equity, _ = _equity_at(historical, item.mark)
        equities.append(equity)
    unrealized, equity, gross = _equity_at(valuation_account, current.mark)
    carry_is_complete = all(
        _component_complete_at(valuation_account, prefix, current.observed_at)
        for prefix in ("funding", "borrow")
    )
    complete = equity if carry_is_complete else None
    status = (
        "COMPLETE"
        if complete is not None
        else "PARTIAL_UNKNOWN_CARRY_COSTS"
    )

    if equity > 0:
        leverage = gross / equity
        leverage_status = (
            "KNOWN_MARK_TO_MARKET"
            if carry_is_complete
            else "KNOWN_BEFORE_UNKNOWN_CARRY_COSTS"
        )
    else:
        leverage = None
        leverage_status = "UNDEFINED_NONPOSITIVE_EQUITY"

    has_sufficient_account_history = bool(account_history) or account.version == 1
    if any(item.path_status != "ORDERED" for item in marks):
        peak = current_drawdown = observed_max_drawdown = None
        drawdown_status = "UNKNOWN_UNORDERED_MARK_PATH"
    elif not has_sufficient_account_history:
        peak = current_drawdown = observed_max_drawdown = None
        drawdown_status = "UNKNOWN_ACCOUNT_HISTORY_REQUIRED"
    else:
        peak, current_drawdown, observed_max_drawdown, drawdown_status = _drawdowns(
            equities
        )
        if drawdown_status == "OBSERVED_KNOWN_MARK_POINTS" and not carry_is_complete:
            drawdown_status = "OBSERVED_BEFORE_UNKNOWN_CARRY_COSTS"
        elif drawdown_status == "OBSERVED_KNOWN_MARK_POINTS" and account_history:
            drawdown_status = (
                "OBSERVED_REPLAYED_ACCOUNT_MARK_POINTS"
                if replayed_all
                else "OBSERVED_REPLAYED_POINTS_AFTER_ACCOUNT_OPEN"
            )

    if account.account_mode == "CASH_SPOT":
        liquidation_buffer = None
        liquidation_status = "NOT_APPLICABLE_CASH_SPOT"
    elif not risk_is_complete:
        liquidation_buffer = None
        liquidation_status = "UNKNOWN_PARAMETERS_INCOMPLETE"
    elif not carry_is_complete:
        liquidation_buffer = None
        liquidation_status = "UNKNOWN_CARRY_COSTS"
    else:
        rate = _decimal(
            spec.maintenance_margin_rate,
            field="instrument_spec.maintenance_margin_rate",
            nonnegative=True,
        )
        if rate > 1:
            raise PaperValuationError("maintenance_margin_rate must not exceed one")
        deduction = _decimal(
            spec.maintenance_margin_deduction,
            field="instrument_spec.maintenance_margin_deduction",
            nonnegative=True,
        )
        fee_reserve = _decimal(
            spec.liquidation_fee_reserve,
            field="instrument_spec.liquidation_fee_reserve",
            nonnegative=True,
        )
        maintenance_requirement = max(Decimal("0"), gross * rate - deduction)
        liquidation_buffer = equity - maintenance_requirement - fee_reserve
        liquidation_status = (
            "BREACHED_MODELED_EXPLICIT_PARAMETERS"
            if liquidation_buffer <= 0
            else "MODELED_EXPLICIT_PARAMETERS"
        )

    return PaperValuationProjectionV1(
        account_id=account.account_id,
        account_version=account.version,
        account_mode=account.account_mode,
        symbol=account.permitted_symbol,
        status=status,
        observed_at=current.observed_at,
        available_at=current.available_at,
        source_sha256=current.source_sha256,
        mark=canonical_decimal(current.mark),
        unrealized_pnl=canonical_decimal(unrealized),
        equity_before_unknown_costs=canonical_decimal(equity),
        carry_coverage_status=carry_coverage_status,
        carry_coverage_at_mark_status=(
            "COMPLETE_AT_MARK" if carry_is_complete else "INCOMPLETE_AT_MARK"
        ),
        complete_equity=None if complete is None else canonical_decimal(complete),
        gross_exposure=canonical_decimal(gross),
        effective_leverage=None if leverage is None else canonical_decimal(leverage),
        effective_leverage_status=leverage_status,
        peak_equity=None if peak is None else canonical_decimal(peak),
        current_drawdown=(
            None if current_drawdown is None else canonical_decimal(current_drawdown)
        ),
        observed_max_drawdown=(
            None
            if observed_max_drawdown is None
            else canonical_decimal(observed_max_drawdown)
        ),
        drawdown_status=drawdown_status,
        drawdown_unit="FRACTION",
        liquidation_buffer=(
            None
            if liquidation_buffer is None
            else canonical_decimal(liquidation_buffer)
        ),
        liquidation_buffer_status=liquidation_status,
        liquidation_parameter_source_ref=risk_source_ref,
    )
