"""Read-only V3.3.2 workbench models; facts remain in their owning ledgers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from ...domain.contracts.canonical import canonical_decimal
from ...domain.market_cycle.data import AssetDataSliceV1
from ...domain.market_cycle.paper import PaperAccountVersionV1, PaperLedgerRecordV1
from .attention import AttentionProjection
from .paper_valuation import PaperValuationProjectionV1


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class DataCoverageViewV1:
    profile_id: str
    instrument_key: str
    venue: str
    cutoff_at: str
    sealed_at: str
    health: str
    core_families: tuple[str, ...]
    optional_families: tuple[str, ...]
    unknowns: tuple[Mapping[str, Any], ...]
    raw_refs: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return _plain({field: getattr(self, field) for field in self.__dataclass_fields__})


@dataclass(frozen=True, slots=True)
class AgentStateViewV1:
    logical_agent_id: str
    symbol: str | None
    generation: int | None
    physical_task_id: str | None
    registry_status: str
    revision: int
    active_request_id: str | None
    attention_mode: str | None
    earliest_review_at: str | None
    latest_useful_at: str | None
    request_status: str | None

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class PaperAccountViewV1:
    account_id: str
    symbol: str
    version: int
    cash_balance: str
    reserved_margin: str
    available_balance: str
    realized_pnl: str
    fees_paid: str
    funding_paid: str
    borrow_paid: str
    funding_coverage_status: str
    borrow_coverage_status: str
    carry_coverage_status: str
    funding_coverage_end_at: str | None
    borrow_coverage_end_at: str | None
    valuation: Mapping[str, Any]
    cost_effect: Mapping[str, Any]
    positions: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return _plain({field: getattr(self, field) for field in self.__dataclass_fields__})


@dataclass(frozen=True, slots=True)
class OrdersAndFillsViewV1:
    account_id: str
    open_orders: tuple[Mapping[str, Any], ...]
    order_history: tuple[Mapping[str, Any], ...]
    fills: tuple[Mapping[str, Any], ...]
    unresolved: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return _plain({field: getattr(self, field) for field in self.__dataclass_fields__})


@dataclass(frozen=True, slots=True)
class PaperCostEffectViewV1:
    """Read-only explanation of how recorded cost fields affect paper cash.

    Spread and impact are already embedded in each fill's execution price, so
    they are reported for attribution and are never deducted a second time.
    Fees and sourced carry are the only explicit cash-cost totals here.
    """

    account_id: str
    fill_count: int
    fee_cash_cost: str
    funding_cash_cost: str
    borrow_cash_cost: str
    known_cash_cost_total: str
    complete_cash_cost: str | None
    known_realized_pnl_after_cash_costs: str
    complete_realized_pnl_after_cash_costs: str | None
    spread_embedded_in_fill_price: str
    impact_embedded_in_fill_price: str
    spread_cash_deduction: str
    impact_cash_deduction: str
    timing_cost: str | None
    timing_cost_status: str
    paper_execution_statuses: tuple[str, ...]
    venue_feasibility_status: str
    embedded_execution_cost_treatment: str
    fee_treatment: str
    carry_treatment: str
    funding_coverage_status: str
    borrow_coverage_status: str
    carry_coverage_status: str
    funding_coverage_end_at: str | None
    borrow_coverage_end_at: str | None
    coverage_status: str
    actual_execution_effect_status: str = "UNKNOWN_NOT_EVALUATED"

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class FactTimelineViewV1:
    items: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"items": _plain(self.items)}


@dataclass(frozen=True, slots=True)
class PortfolioAggregateViewV1:
    account_count: int
    total_cash_balance: str
    total_reserved_margin: str
    total_available_balance: str
    total_realized_pnl: str
    total_fees_paid: str
    total_funding_paid: str
    total_borrow_paid: str
    total_known_cash_cost: str
    total_complete_cash_cost: str | None
    total_complete_realized_pnl_after_cash_costs: str | None
    total_unrealized_pnl: str | None
    total_equity_before_unknown_costs: str | None
    total_complete_equity: str | None
    total_gross_exposure: str | None
    effective_leverage: str | None
    valuation_observed_at: str | None
    valuation_status: str
    peak_equity: str | None
    current_drawdown: str | None
    observed_max_drawdown: str | None
    drawdown_status: str
    drawdown_unit: str
    cost_effect_status: str
    actual_execution_effect_status: str
    symbols: tuple[str, ...]
    shared_risk_status: str = "UNKNOWN_NOT_MODELED"

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class WorkbenchSnapshotV1:
    data_coverage: tuple[DataCoverageViewV1, ...]
    agent_states: tuple[AgentStateViewV1, ...]
    paper_accounts: tuple[PaperAccountViewV1, ...]
    orders_and_fills: tuple[OrdersAndFillsViewV1, ...]
    timeline: FactTimelineViewV1
    portfolio: PortfolioAggregateViewV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.v332-workbench-snapshot",
            "schema_version": "1.0.0",
            "data_coverage": [item.to_dict() for item in self.data_coverage],
            "agent_states": [item.to_dict() for item in self.agent_states],
            "paper_accounts": [item.to_dict() for item in self.paper_accounts],
            "orders_and_fills": [item.to_dict() for item in self.orders_and_fills],
            "timeline": self.timeline.to_dict(),
            "portfolio": self.portfolio.to_dict(),
        }


def project_data_coverage(data_slice: AssetDataSliceV1) -> DataCoverageViewV1:
    document = data_slice.to_dict()
    health = "DEGRADED" if document["typed_unknowns"] else "OBSERVED"
    return DataCoverageViewV1(
        profile_id=data_slice.asset_profile_id,
        instrument_key=data_slice.instrument_identity.instrument_key,
        venue=data_slice.instrument_identity.venue,
        cutoff_at=data_slice.cutoff_at,
        sealed_at=data_slice.sealed_at,
        health=health,
        core_families=tuple(document["core_observations"]),
        optional_families=tuple(document["optional_observations"]),
        unknowns=tuple(document["typed_unknowns"]),
        raw_refs=tuple(document["raw_refs"]),
    )


def project_agent_state(projection: AttentionProjection) -> AgentStateViewV1:
    registry = projection.registry
    active = (
        None
        if projection.active_request_id is None
        else projection.requests[projection.active_request_id]
    )
    return AgentStateViewV1(
        logical_agent_id=projection.logical_agent_id,
        symbol=None if registry is None else registry.symbol,
        generation=None if registry is None else registry.generation,
        physical_task_id=None if registry is None else registry.physical_task_id,
        registry_status="UNREGISTERED" if registry is None else registry.status,
        revision=projection.revision,
        active_request_id=projection.active_request_id,
        attention_mode=None if active is None else active.mode,
        earliest_review_at=None if active is None else active.earliest,
        latest_useful_at=None if active is None else active.latest,
        request_status=(
            None
            if projection.active_request_id is None
            else projection.request_statuses[projection.active_request_id]
        ),
    )


def project_paper_account(
    account: PaperAccountVersionV1,
    valuation: PaperValuationProjectionV1 | None = None,
    cost_effect: PaperCostEffectViewV1 | None = None,
) -> PaperAccountViewV1:
    return PaperAccountViewV1(
        account_id=account.account_id,
        symbol=account.permitted_symbol,
        version=account.version,
        cash_balance=account.cash_balance,
        reserved_margin=account.reserved_margin,
        available_balance=account.available_balance,
        realized_pnl=account.realized_pnl,
        fees_paid=account.fees_paid,
        funding_paid=account.funding_paid,
        borrow_paid=account.borrow_paid,
        funding_coverage_status=account.funding_coverage_status,
        borrow_coverage_status=account.borrow_coverage_status,
        carry_coverage_status=account.carry_coverage_status,
        funding_coverage_end_at=account.funding_coverage_end_at,
        borrow_coverage_end_at=account.borrow_coverage_end_at,
        valuation=(
            {
                "status": "UNKNOWN_NO_MARK",
                "actual_cost_effect_status": "UNKNOWN_NOT_EVALUATED",
            }
            if valuation is None
            else valuation.to_dict()
        ),
        cost_effect=(
            {
                "coverage_status": "UNKNOWN_NO_LEDGER_PROJECTION",
                "actual_execution_effect_status": "UNKNOWN_NOT_EVALUATED",
            }
            if cost_effect is None
            else cost_effect.to_dict()
        ),
        positions=tuple(position.to_dict() for position in account.positions),
    )


def project_paper_cost_effect(
    account: PaperAccountVersionV1,
    records: Sequence[PaperLedgerRecordV1],
    *,
    evaluation_cutoff_at: str | None = None,
) -> PaperCostEffectViewV1:
    fills = tuple(
        record.payload["fill"]
        for record in records
        if record.event_type == "FILL_RECORDED"
    )

    def fill_total(field: str) -> Decimal:
        values: list[Decimal] = []
        for fill in fills:
            if not isinstance(fill, Mapping) or not isinstance(fill.get(field), str):
                raise ValueError(f"paper fill {field} is unavailable")
            values.append(Decimal(fill[field]))
        return sum(values, Decimal("0"))

    fee = fill_total("fee")
    if fee != Decimal(account.fees_paid):
        raise ValueError("paper fee facts do not reconcile with account")
    funding = Decimal(account.funding_paid)
    borrow = Decimal(account.borrow_paid)
    known_cash_cost = fee + funding + borrow
    known_result = Decimal(account.realized_pnl) - known_cash_cost
    if evaluation_cutoff_at is None:
        economic_times = [records[0].occurred_at] if records else []
        for record in records:
            if record.event_type == "MARKET_OBSERVED":
                market = record.payload.get("market")
                observed_at = (
                    market.get("observed_at")
                    if isinstance(market, Mapping)
                    else record.payload.get("observed_at")
                )
                if isinstance(observed_at, str):
                    economic_times.append(observed_at)
            elif record.event_type == "FILL_RECORDED":
                fill = record.payload.get("fill")
                if isinstance(fill, Mapping) and isinstance(
                    fill.get("observed_at"), str
                ):
                    economic_times.append(fill["observed_at"])
            elif record.event_type == "CARRY_ACCRUED":
                accrual = record.payload.get("accrual")
                if isinstance(accrual, Mapping) and accrual.get("status") in {
                    "MODELED",
                    "OBSERVED",
                } and isinstance(accrual.get("effective_at"), str):
                    economic_times.append(accrual["effective_at"])
        evaluation_cutoff_at = max(
            economic_times,
            key=lambda value: datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ),
        )
    cutoff = datetime.fromisoformat(
        evaluation_cutoff_at.replace("Z", "+00:00")
    )
    def component_complete(prefix: str) -> bool:
        status = getattr(account, f"{prefix}_coverage_status")
        if status == "NOT_APPLICABLE":
            return True
        end_at = getattr(account, f"{prefix}_coverage_end_at")
        return (
            status == "COMPLETE"
            and end_at is not None
            and datetime.fromisoformat(end_at.replace("Z", "+00:00"))
            >= cutoff
        )

    carry_complete = all(
        component_complete(prefix) for prefix in ("funding", "borrow")
    )
    timing_statuses = {
        str(fill.get("timing_cost_status"))
        for fill in fills
        if isinstance(fill, Mapping)
    }
    if not fills:
        timing_cost = "0"
        timing_status = "NOT_APPLICABLE_NO_FILLS"
    elif timing_statuses == {"MODELED"}:
        timing_cost = canonical_decimal(
            sum((Decimal(fill["timing_cost"]) for fill in fills), Decimal("0"))
        )
        timing_status = "MODELED"
    else:
        timing_cost = None
        timing_status = "UNKNOWN_INCOMPLETE_ARRIVAL_BENCHMARK"
    return PaperCostEffectViewV1(
        account_id=account.account_id,
        fill_count=len(fills),
        fee_cash_cost=canonical_decimal(fee),
        funding_cash_cost=canonical_decimal(funding),
        borrow_cash_cost=canonical_decimal(borrow),
        known_cash_cost_total=canonical_decimal(known_cash_cost),
        complete_cash_cost=(
            canonical_decimal(known_cash_cost) if carry_complete else None
        ),
        known_realized_pnl_after_cash_costs=canonical_decimal(known_result),
        complete_realized_pnl_after_cash_costs=(
            canonical_decimal(known_result) if carry_complete else None
        ),
        spread_embedded_in_fill_price=canonical_decimal(fill_total("spread_cost")),
        impact_embedded_in_fill_price=canonical_decimal(fill_total("impact_cost")),
        spread_cash_deduction="0",
        impact_cash_deduction="0",
        timing_cost=timing_cost,
        timing_cost_status=timing_status,
        paper_execution_statuses=tuple(
            sorted({str(fill.get("execution_status")) for fill in fills})
        ),
        venue_feasibility_status="UNKNOWN_TICK_LOT_MINIMUM_NOT_ENFORCED",
        embedded_execution_cost_treatment=(
            "INFORMATIONAL_ALREADY_IN_EXECUTION_PRICE_NO_SECOND_DEDUCTION"
        ),
        fee_treatment="DEDUCTED_FROM_CASH_ON_FILL",
        carry_treatment="DEDUCTED_FROM_CASH_ONLY_WHEN_SOURCED",
        funding_coverage_status=account.funding_coverage_status,
        borrow_coverage_status=account.borrow_coverage_status,
        carry_coverage_status=account.carry_coverage_status,
        funding_coverage_end_at=account.funding_coverage_end_at,
        borrow_coverage_end_at=account.borrow_coverage_end_at,
        coverage_status=(
            "COMPLETE_RECORDED_CASH_COSTS"
            if carry_complete
            else "INCOMPLETE_UNKNOWN_CARRY_COSTS"
        ),
    )


def project_orders_and_fills(
    account: PaperAccountVersionV1,
    records: Sequence[PaperLedgerRecordV1],
) -> OrdersAndFillsViewV1:
    open_orders = tuple(
        order.to_dict()
        for order in account.orders
        if order.state in {"OPEN", "PARTIALLY_FILLED"}
    )
    order_history = tuple(
        order.to_dict()
        for order in account.orders
        if order.state not in {"OPEN", "PARTIALLY_FILLED"}
    )
    fills = tuple(
        _plain(record.payload["fill"])
        for record in records
        if record.event_type == "FILL_RECORDED"
    )
    unresolved = tuple(
        order.to_dict() for order in account.orders if order.state == "UNRESOLVED"
    )
    return OrdersAndFillsViewV1(
        account_id=account.account_id,
        open_orders=open_orders,
        order_history=order_history,
        fills=fills,
        unresolved=unresolved,
    )


def project_fact_timeline(
    attention_events: Sequence[Any],
    paper_records: Sequence[PaperLedgerRecordV1],
    cycle_artifacts: Sequence[Mapping[str, Any]] = (),
) -> FactTimelineViewV1:
    items = [
        {
            "owner": "attention",
            "stream_id": event.logical_agent_id,
            "revision": event.revision,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at,
        }
        for event in attention_events
    ]
    items.extend(
        {
            "owner": "paper",
            "stream_id": record.account_id,
            "revision": record.revision,
            "event_id": record.event_id,
            "event_type": record.event_type,
            "occurred_at": record.occurred_at,
        }
        for record in paper_records
    )
    items.extend(
        {
            "owner": "market_cycle",
            "stream_id": str(item["cycle_id"]),
            "revision": int(item["revision"]),
            "event_id": str(item["artifact_ref"]["sha256"]),
            "event_type": str(item["artifact_ref"]["artifact_type"]),
            "occurred_at": str(item["sealed_at"]),
            "artifact_ref": _plain(item["artifact_ref"]),
        }
        for item in cycle_artifacts
    )
    return FactTimelineViewV1(
        items=tuple(
            sorted(
                items,
                key=lambda item: (
                    item["occurred_at"],
                    item["owner"],
                    item["stream_id"],
                    item["revision"],
                ),
            )
        )
    )


def project_portfolio(
    accounts: Sequence[PaperAccountVersionV1],
    valuations: Sequence[PaperValuationProjectionV1 | None] = (),
    cost_effects: Sequence[PaperCostEffectViewV1] = (),
) -> PortfolioAggregateViewV1:
    def total(field: str) -> str:
        return canonical_decimal(
            sum((Decimal(getattr(account, field)) for account in accounts), Decimal("0"))
        )

    supplied = tuple(valuations) if valuations else tuple(None for _ in accounts)
    if len(supplied) != len(accounts):
        raise ValueError("portfolio valuations must align with accounts")
    supplied_costs = tuple(cost_effects)
    if supplied_costs and len(supplied_costs) != len(accounts):
        raise ValueError("portfolio cost effects must align with accounts")
    all_valued = bool(accounts) and all(
        item is not None
        and item.unrealized_pnl is not None
        and item.equity_before_unknown_costs is not None
        and item.gross_exposure is not None
        and item.observed_at is not None
        for item in supplied
    )
    known = tuple(item for item in supplied if item is not None)
    observed_times = {
        item.observed_at for item in known if item.observed_at is not None
    }
    synchronized = all_valued and len(observed_times) == 1
    all_costs = synchronized and all(
        item.complete_equity is not None for item in known
    )
    costs_complete = bool(accounts) and len(supplied_costs) == len(accounts) and all(
        item.complete_cash_cost is not None for item in supplied_costs
    )
    total_unrealized = (
        canonical_decimal(sum((Decimal(item.unrealized_pnl) for item in known), Decimal("0")))
        if synchronized
        else None
    )
    total_equity_before = (
        canonical_decimal(
            sum((Decimal(item.equity_before_unknown_costs) for item in known), Decimal("0"))
        )
        if synchronized
        else None
    )
    total_complete_equity = (
        canonical_decimal(sum((Decimal(item.complete_equity) for item in known), Decimal("0")))
        if all_costs
        else None
    )
    total_gross = (
        canonical_decimal(sum((Decimal(item.gross_exposure) for item in known), Decimal("0")))
        if synchronized
        else None
    )
    portfolio_leverage = (
        canonical_decimal(Decimal(total_gross) / Decimal(total_equity_before))
        if synchronized and Decimal(total_equity_before) > 0
        else None
    )
    total_known_cash_cost = canonical_decimal(
        sum(
            (Decimal(item.known_cash_cost_total) for item in supplied_costs),
            Decimal("0"),
        )
    )
    total_complete_cash_cost = (
        total_known_cash_cost if costs_complete else None
    )
    total_complete_realized_after_costs = (
        canonical_decimal(
            sum(
                (
                    Decimal(item.complete_realized_pnl_after_cash_costs)
                    for item in supplied_costs
                ),
                Decimal("0"),
            )
        )
        if costs_complete
        else None
    )
    if not accounts:
        valuation_status = "UNKNOWN_NO_ACCOUNTS"
    elif not all_valued:
        valuation_status = "UNKNOWN_INCOMPLETE_MARKS"
    elif not synchronized:
        valuation_status = "UNKNOWN_UNSYNCHRONIZED_MARKS"
    else:
        valuation_status = "VALUED_SYNCHRONIZED"

    if len(accounts) == 1 and synchronized:
        valuation = known[0]
        portfolio_peak = valuation.peak_equity
        portfolio_current_drawdown = valuation.current_drawdown
        portfolio_max_drawdown = valuation.observed_max_drawdown
        portfolio_drawdown_status = valuation.drawdown_status
    elif len(accounts) > 1 and not synchronized:
        portfolio_peak = portfolio_current_drawdown = portfolio_max_drawdown = None
        portfolio_drawdown_status = "UNKNOWN_UNSYNCHRONIZED_MARKS"
    elif len(accounts) > 1:
        portfolio_peak = portfolio_current_drawdown = portfolio_max_drawdown = None
        portfolio_drawdown_status = "UNKNOWN_SYNCHRONIZED_EQUITY_CURVE_REQUIRED"
    else:
        portfolio_peak = portfolio_current_drawdown = portfolio_max_drawdown = None
        portfolio_drawdown_status = "UNKNOWN_NO_KNOWN_VALUATION_POINT"
    return PortfolioAggregateViewV1(
        account_count=len(accounts),
        total_cash_balance=total("cash_balance"),
        total_reserved_margin=total("reserved_margin"),
        total_available_balance=canonical_decimal(
            sum((Decimal(account.available_balance) for account in accounts), Decimal("0"))
        ),
        total_realized_pnl=total("realized_pnl"),
        total_fees_paid=total("fees_paid"),
        total_funding_paid=total("funding_paid"),
        total_borrow_paid=total("borrow_paid"),
        total_known_cash_cost=total_known_cash_cost,
        total_complete_cash_cost=total_complete_cash_cost,
        total_complete_realized_pnl_after_cash_costs=(
            total_complete_realized_after_costs
        ),
        total_unrealized_pnl=total_unrealized,
        total_equity_before_unknown_costs=total_equity_before,
        total_complete_equity=total_complete_equity,
        total_gross_exposure=total_gross,
        effective_leverage=portfolio_leverage,
        valuation_observed_at=(next(iter(observed_times)) if synchronized else None),
        valuation_status=valuation_status,
        peak_equity=portfolio_peak,
        current_drawdown=portfolio_current_drawdown,
        observed_max_drawdown=portfolio_max_drawdown,
        drawdown_status=portfolio_drawdown_status,
        drawdown_unit="FRACTION",
        cost_effect_status=(
            "COMPLETE_RECORDED_CASH_COSTS"
            if costs_complete
            else "INCOMPLETE_UNKNOWN_COST"
        ),
        actual_execution_effect_status="UNKNOWN_NOT_EVALUATED",
        symbols=tuple(sorted(account.permitted_symbol for account in accounts)),
    )
