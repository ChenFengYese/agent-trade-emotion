"""Application use cases for Agent-owned commands and isolated paper facts."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Protocol, Sequence

from ...domain.contracts.canonical import canonical_decimal, canonical_digest
from ...domain.market_cycle.paper import (
    CarryAccrualV1,
    FillEventV1,
    FundingCoverageAdvanceV1,
    FundingSettlementModelV1,
    InstrumentSpecV1,
    OrderTruthV1,
    PAPER_TERMINAL_ORDER_STATES,
    PaperAccountVersionV1,
    PaperCommandV1,
    PaperContractError,
    PaperCostModelV1,
    PaperBracketV1,
    PaperExecutionIntentV1,
    PaperLedgerRecordV1,
    PaperMarketSliceV1,
    PaperPositionV1,
    StaticNoTransitionComparatorV1,
    StaticNoTransitionEpisodeLinkV1,
)


class PaperTradingError(RuntimeError):
    """A paper command or market observation cannot be applied safely."""


class PaperLedgerPort(Protocol):
    def load_records(self, account_id: str) -> tuple[PaperLedgerRecordV1, ...]: ...

    def append_many(
        self,
        *,
        account_id: str,
        expected_revision: int,
        events: Sequence[Mapping[str, Any]],
    ) -> tuple[PaperLedgerRecordV1, ...]: ...


class PaperDecisionAuthorityPort(Protocol):
    """Read-only proof that a command came from the current sealed Agent decision."""

    def current_generation(self, logical_agent_id: str) -> int | None: ...

    def verifies_decision(self, command: PaperCommandV1) -> bool: ...

    def verifies_execution_intent(
        self, execution_intent: PaperExecutionIntentV1
    ) -> bool: ...


class PaperMarketEvidencePort(Protocol):
    """Read-only proof that a paper slice is bound to admitted market evidence."""

    def verifies_market_slice(self, market: PaperMarketSliceV1) -> bool: ...

    def verifies_instrument_spec(
        self,
        instrument_spec: InstrumentSpecV1,
        *,
        available_by: str,
    ) -> bool: ...


class PaperCarryEvidencePort(Protocol):
    """Read-only proof for a sourced funding or borrow accrual."""

    def verifies_carry_accrual(self, accrual: CarryAccrualV1) -> bool: ...

    def verifies_funding_coverage(
        self, advance: FundingCoverageAdvanceV1
    ) -> bool: ...


def _d(value: Decimal) -> str:
    return canonical_decimal(value)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event_id(prefix: str, value: Mapping[str, Any]) -> str:
    return f"{prefix}-{canonical_digest(value)[:32]}"


def _initial_carry_coverage(account_mode: str) -> tuple[str, str, str]:
    if account_mode == "LINEAR_PERP":
        return "UNKNOWN", "NOT_APPLICABLE", "UNKNOWN"
    if account_mode == "CASH_SPOT":
        return "NOT_APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE"
    raise PaperTradingError("PAPER_ACCOUNT_MODE_INVALID")


def _aggregate_carry_coverage(funding: str, borrow: str) -> str:
    if funding == borrow == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    if funding in {"COMPLETE", "NOT_APPLICABLE"} and borrow in {
        "COMPLETE",
        "NOT_APPLICABLE",
    }:
        return "COMPLETE"
    if "PARTIAL" in {funding, borrow}:
        return "PARTIAL"
    return "UNKNOWN"


def _advance_component_coverage(
    *,
    current_status: str,
    current_start_at: str | None,
    current_end_at: str | None,
    accrual: CarryAccrualV1,
    account_opened_at: str,
) -> tuple[str, str | None, str | None]:
    """Merge one explicitly bounded source window without hiding a gap."""

    if accrual.coverage_status == "NOT_APPLICABLE":
        return "NOT_APPLICABLE", None, None
    start = accrual.coverage_start_at
    end = accrual.coverage_end_at
    if _dt(end) < _dt(accrual.effective_at):
        raise PaperTradingError("PAPER_CARRY_COVERAGE_DOES_NOT_REACH_EFFECTIVE_TIME")
    if accrual.coverage_status == "UNKNOWN":
        return "UNKNOWN", start, end
    if current_end_at is None:
        if accrual.coverage_status == "COMPLETE" and _dt(start) > _dt(
            account_opened_at
        ):
            raise PaperTradingError("PAPER_CARRY_COVERAGE_INITIAL_GAP")
        return accrual.coverage_status, start, end
    if _dt(end) < _dt(current_end_at):
        raise PaperTradingError("PAPER_CARRY_COVERAGE_REGRESSION")
    if accrual.coverage_status == "COMPLETE" and _dt(start) > _dt(current_end_at):
        raise PaperTradingError("PAPER_CARRY_COVERAGE_GAP")
    merged_start = min(_dt(current_start_at), _dt(start)).isoformat()
    merged_end = max(_dt(current_end_at), _dt(end)).isoformat()
    next_status = (
        "COMPLETE"
        if current_status == "COMPLETE" and accrual.coverage_status == "COMPLETE"
        else "PARTIAL"
    )
    return next_status, merged_start, merged_end


def _position_by_symbol(
    positions: tuple[PaperPositionV1, ...], symbol: str
) -> PaperPositionV1:
    return next(
        (position for position in positions if position.symbol == symbol),
        PaperPositionV1(
            symbol=symbol,
            quantity="0",
            average_entry_price="0",
            margin_allocated="0",
            realized_pnl="0",
        ),
    )


def _project_event(
    records: Sequence[PaperLedgerRecordV1],
    *,
    account_id: str,
    event: Mapping[str, Any],
) -> tuple[PaperLedgerRecordV1, ...]:
    """Project one already-validated event without touching the ledger."""

    previous_sha = records[-1].record_sha256 if records else None
    return (
        *records,
        PaperLedgerRecordV1.create(
            account_id=account_id,
            revision=len(records) + 1,
            previous_record_sha256=previous_sha,
            event_id=event["event_id"],
            event_type=event["event_type"],
            occurred_at=event["occurred_at"],
            payload=event["payload"],
        ),
    )


def _root_static_comparator(
    records: Sequence[PaperLedgerRecordV1], *, episode_id: str
) -> StaticNoTransitionComparatorV1 | None:
    roots: list[StaticNoTransitionComparatorV1] = []
    for record in records:
        if record.event_type != "STATIC_NO_TRANSITION_PREREGISTERED":
            continue
        value = record.payload.get("comparator")
        if not isinstance(value, Mapping):
            raise PaperTradingError("PAPER_STATIC_COMPARATOR_EVENT_INVALID")
        comparator = StaticNoTransitionComparatorV1.from_dict(value)
        root_intent = PaperExecutionIntentV1.from_dict(
            comparator.execution_intent
        )
        if root_intent.episode_id == episode_id:
            roots.append(comparator)
    if len(roots) > 1:
        raise PaperTradingError("PAPER_STATIC_COMPARATOR_EPISODE_DUPLICATE")
    return roots[0] if roots else None


def _episode_linkage_for_intent(
    records: Sequence[PaperLedgerRecordV1],
    *,
    execution_intent: PaperExecutionIntentV1,
) -> StaticNoTransitionEpisodeLinkV1 | None:
    root = _root_static_comparator(
        records, episode_id=execution_intent.episode_id
    )
    if root is None:
        return None
    prior_continuations = sum(
        1
        for record in records
        if record.event_type in {"INTENT_RECORDED", "COMMAND_ACCEPTED"}
        and isinstance(record.payload.get("static_comparator_linkage"), Mapping)
        and record.payload["static_comparator_linkage"].get(
            "root_comparator_id"
        )
        == root.comparator_id
    )
    return StaticNoTransitionEpisodeLinkV1.create(
        root_comparator=root,
        current_intent=execution_intent,
        continuation_index=prior_continuations + 1,
    )


def replay_paper_account(
    records: Sequence[PaperLedgerRecordV1],
) -> PaperAccountVersionV1:
    if not records or records[0].event_type != "ACCOUNT_OPENED":
        raise PaperTradingError("PAPER_ACCOUNT_NOT_FOUND")
    opened = records[0].payload
    account_id = records[0].account_id
    account_mode = opened.get("account_mode")
    owner = opened.get("owner_logical_agent_id")
    base_currency = opened.get("base_currency")
    permitted_symbol = opened.get("permitted_symbol")
    max_leverage = opened.get("max_leverage")
    instrument_payload = opened.get("instrument_spec")
    if not isinstance(instrument_payload, Mapping):
        raise PaperTradingError("PAPER_INSTRUMENT_SPEC_MISSING")
    instrument_spec = InstrumentSpecV1(**dict(instrument_payload))
    owner_agent_generation = opened.get("owner_agent_generation")
    if type(owner_agent_generation) is not int or owner_agent_generation < 1:
        raise PaperTradingError("PAPER_OWNER_AGENT_GENERATION_INVALID")
    if (
        instrument_spec.symbol != permitted_symbol
        or instrument_spec.account_mode != account_mode
        or instrument_spec.quote_currency != base_currency
    ):
        raise PaperTradingError("PAPER_INSTRUMENT_SPEC_ACCOUNT_MISMATCH")
    initial_balance = opened.get("initial_balance")
    cash_balance = initial_balance
    realized_pnl = "0"
    fees_paid = "0"
    funding_paid = "0"
    borrow_paid = "0"
    funding_coverage_status, borrow_coverage_status, carry_coverage_status = (
        _initial_carry_coverage(account_mode)
    )
    funding_coverage_start_at = funding_coverage_end_at = None
    funding_complete_start_at = funding_complete_end_at = None
    borrow_coverage_start_at = borrow_coverage_end_at = None
    reserved_margin = "0"
    positions: dict[str, PaperPositionV1] = {}
    orders: dict[str, OrderTruthV1] = {}
    applied_commands: list[str] = []
    recorded_intent_ids: set[str] = set()
    accepted_execution_intents: dict[str, PaperExecutionIntentV1] = {}
    accepted_bracket_episode_counts: dict[str, int] = {}
    static_comparator_episodes: set[str] = set()
    static_comparators_by_episode: dict[
        str, StaticNoTransitionComparatorV1
    ] = {}
    static_continuation_counts: dict[str, int] = {}
    last_fact_at = records[0].occurred_at
    last_market_observed_at: str | None = None
    last_market_available_at: str | None = None
    last_market_source_sha256: str | None = None
    sourced_carry_economic_keys: set[tuple[str, str, str, str]] = set()
    sourced_funding_by_effective: dict[str, CarryAccrualV1] = {}

    def verify_static_episode_linkage(
        payload: Mapping[str, Any], intent: PaperExecutionIntentV1
    ) -> None:
        root = static_comparators_by_episode.get(intent.episode_id)
        linkage_value = payload.get("static_comparator_linkage")
        if root is None:
            if linkage_value is not None:
                raise PaperTradingError(
                    "PAPER_STATIC_COMPARATOR_LINKAGE_WITHOUT_ROOT"
                )
            return
        if not isinstance(linkage_value, Mapping):
            raise PaperTradingError("PAPER_STATIC_COMPARATOR_LINKAGE_MISSING")
        try:
            linkage = StaticNoTransitionEpisodeLinkV1.from_dict(
                linkage_value
            )
        except PaperContractError as exc:
            raise PaperTradingError(
                "PAPER_STATIC_COMPARATOR_LINKAGE_INVALID"
            ) from exc
        expected_index = static_continuation_counts.get(root.comparator_id, 0) + 1
        if not linkage.verifies(
            root_comparator=root,
            current_intent=intent,
            continuation_index=expected_index,
        ):
            raise PaperTradingError("PAPER_STATIC_COMPARATOR_LINKAGE_INVALID")
        static_continuation_counts[root.comparator_id] = expected_index

    for record_index, record in enumerate(records[1:], start=1):
        previous_record = records[record_index - 1]
        if record.account_id != account_id:
            raise PaperTradingError("PAPER_RECORD_ACCOUNT_MISMATCH")
        if _dt(record.occurred_at) < _dt(last_fact_at):
            raise PaperTradingError("PAPER_EVENT_TIME_REGRESSION")
        last_fact_at = record.occurred_at
        payload = record.payload
        if record.event_type == "INTENT_RECORDED":
            intent_payload = payload.get("execution_intent")
            if not isinstance(intent_payload, Mapping):
                raise PaperTradingError("PAPER_EXECUTION_INTENT_EVENT_INVALID")
            try:
                execution_intent = PaperExecutionIntentV1.from_dict(intent_payload)
            except PaperContractError as exc:
                raise PaperTradingError(
                    "PAPER_EXECUTION_INTENT_EVENT_INVALID"
                ) from exc
            if (
                execution_intent.command is not None
                or execution_intent.account_id != account_id
                or execution_intent.logical_agent_id != owner
                or execution_intent.symbol != permitted_symbol
                or execution_intent.expected_account_version != record.revision - 1
                or execution_intent.ledger_head_record_sha256
                != record.previous_record_sha256
                or execution_intent.intent_id in recorded_intent_ids
            ):
                raise PaperTradingError("PAPER_EXECUTION_INTENT_EVENT_INVALID")
            verify_static_episode_linkage(payload, execution_intent)
            generation = execution_intent.agent_generation
            if generation < owner_agent_generation:
                raise PaperTradingError("PAPER_AGENT_GENERATION_REGRESSION")
            owner_agent_generation = generation
            recorded_intent_ids.add(execution_intent.intent_id)
        if record.event_type == "COMMAND_ACCEPTED":
            command = payload.get("command")
            if not isinstance(command, Mapping) or not isinstance(command.get("command_id"), str):
                raise PaperTradingError("PAPER_COMMAND_EVENT_INVALID")
            if command.get("account_id") != account_id:
                raise PaperTradingError("PAPER_COMMAND_ACCOUNT_MISMATCH")
            if command.get("logical_agent_id") != owner:
                raise PaperTradingError("PAPER_COMMAND_AGENT_MISMATCH")
            if command.get("symbol") != permitted_symbol:
                raise PaperTradingError("PAPER_COMMAND_SYMBOL_MISMATCH")
            intent_payload = payload.get("execution_intent")
            accepted_at = payload.get("accepted_at")
            if intent_payload is None:
                if accepted_at is not None or command.get("submitted_at") != record.occurred_at:
                    raise PaperTradingError("PAPER_COMMAND_TIME_MISMATCH")
            elif (
                accepted_at != record.occurred_at
                or _dt(accepted_at) < _dt(command.get("submitted_at"))
            ):
                raise PaperTradingError("PAPER_COMMAND_RECEIPT_TIME_MISMATCH")
            generation = command.get("agent_generation")
            if type(generation) is not int or generation < owner_agent_generation:
                raise PaperTradingError("PAPER_AGENT_GENERATION_REGRESSION")
            owner_agent_generation = generation
            commands_payload = payload.get("commands", (command,))
            if not isinstance(commands_payload, tuple) or not all(
                isinstance(item, Mapping) for item in commands_payload
            ):
                raise PaperTradingError("PAPER_COMMAND_EVENT_INVALID")
            for accepted_command in commands_payload:
                parsed_command = PaperCommandV1.from_dict(accepted_command)
                if (
                    parsed_command.account_id != account_id
                    or parsed_command.logical_agent_id != owner
                    or parsed_command.symbol != permitted_symbol
                ):
                    raise PaperTradingError("PAPER_COMMAND_EVENT_INVALID")
                if parsed_command.command_id not in applied_commands:
                    applied_commands.append(parsed_command.command_id)
            if intent_payload is not None:
                if not isinstance(intent_payload, Mapping):
                    raise PaperTradingError("PAPER_EXECUTION_INTENT_EVENT_INVALID")
                try:
                    execution_intent = PaperExecutionIntentV1.from_dict(
                        intent_payload
                    )
                except PaperContractError as exc:
                    raise PaperTradingError(
                        "PAPER_EXECUTION_INTENT_EVENT_INVALID"
                    ) from exc
                if execution_intent.command is None or (
                    execution_intent.command.to_dict() != dict(command)
                ):
                    raise PaperTradingError(
                        "PAPER_EXECUTION_INTENT_COMMAND_MISMATCH"
                    )
                verify_static_episode_linkage(payload, execution_intent)
                if execution_intent.intent_id in recorded_intent_ids:
                    raise PaperTradingError("PAPER_EXECUTION_INTENT_ID_DUPLICATE")
                recorded_intent_ids.add(execution_intent.intent_id)
                accepted_execution_intents[execution_intent.intent_id] = (
                    execution_intent
                )
                if execution_intent.bracket is not None:
                    episode_id = execution_intent.episode_id
                    accepted_bracket_episode_counts[episode_id] = (
                        accepted_bracket_episode_counts.get(episode_id, 0) + 1
                    )
        if record.event_type == "STATIC_NO_TRANSITION_PREREGISTERED":
            value = payload.get("comparator")
            if not isinstance(value, Mapping):
                raise PaperTradingError("PAPER_STATIC_COMPARATOR_EVENT_INVALID")
            try:
                comparator = StaticNoTransitionComparatorV1.from_dict(value)
                intent = PaperExecutionIntentV1.from_dict(
                    comparator.execution_intent
                )
            except PaperContractError as exc:
                raise PaperTradingError(
                    "PAPER_STATIC_COMPARATOR_EVENT_INVALID"
                ) from exc
            accepted_intent = accepted_execution_intents.get(intent.intent_id)
            if (
                previous_record.event_type != "COMMAND_ACCEPTED"
                or not isinstance(
                    previous_record.payload.get("execution_intent"), Mapping
                )
                or canonical_digest(
                    previous_record.payload["execution_intent"]
                )
                != intent.intent_sha256
                or accepted_intent != intent
                or comparator.account_pre_version != previous_record.revision - 1
                or comparator.account_pre_head_record_sha256
                != previous_record.previous_record_sha256
                or comparator.preregistered_at != previous_record.occurred_at
                or record.occurred_at != previous_record.occurred_at
                or accepted_bracket_episode_counts.get(intent.episode_id) != 1
                or intent.episode_id in static_comparator_episodes
            ):
                raise PaperTradingError("PAPER_STATIC_COMPARATOR_EVENT_INVALID")
            static_comparator_episodes.add(intent.episode_id)
            static_comparators_by_episode[intent.episode_id] = comparator
        if record.event_type == "MARKET_OBSERVED":
            market_payload = payload.get("market")
            if market_payload is not None:
                if not isinstance(market_payload, Mapping):
                    raise PaperTradingError("PAPER_MARKET_PAYLOAD_INVALID")
                market_fact = PaperMarketSliceV1(**dict(market_payload))
                observed_at = market_fact.observed_at
                available_at = market_fact.available_at
                source_sha256 = market_fact.source_sha256
                if market_fact.symbol != permitted_symbol:
                    raise PaperTradingError("PAPER_MARKET_SYMBOL_MISMATCH")
            else:
                observed_at = payload.get("observed_at")
                available_at = payload.get("available_at")
                source_sha256 = payload.get("source_sha256")
            if not all(isinstance(value, str) for value in (observed_at, available_at, source_sha256)):
                raise PaperTradingError("PAPER_MARKET_CURSOR_INVALID")
            if payload.get("symbol") != permitted_symbol:
                raise PaperTradingError("PAPER_MARKET_SYMBOL_MISMATCH")
            if record.occurred_at != available_at or _dt(available_at) < _dt(observed_at):
                raise PaperTradingError("PAPER_MARKET_CURSOR_INVALID")
            if last_market_observed_at is not None and (
                _dt(observed_at) <= _dt(last_market_observed_at)
                or _dt(available_at) <= _dt(last_market_available_at)
            ):
                raise PaperTradingError("PAPER_MARKET_SLICE_NOT_FORWARD")
            last_market_observed_at = observed_at
            last_market_available_at = available_at
            last_market_source_sha256 = source_sha256
        if record.event_type in {
            "ORDER_OPENED",
            "ORDER_HELD",
            "ORDER_ACTIVATED",
            "ORDER_UPDATED",
            "ORDER_CANCELLED",
            "ORDER_REJECTED",
            "ORDER_EXPIRED",
            "ORDER_UNRESOLVED",
            "FILL_RECORDED",
        }:
            order_payload = payload.get("order")
            if not isinstance(order_payload, Mapping):
                raise PaperTradingError("PAPER_ORDER_EVENT_INVALID")
            order = OrderTruthV1(**dict(order_payload))
            if order.account_id != account_id:
                raise PaperTradingError("PAPER_ORDER_ACCOUNT_MISMATCH")
            if order.logical_agent_id != owner:
                raise PaperTradingError("PAPER_ORDER_AGENT_MISMATCH")
            if order.symbol != permitted_symbol:
                raise PaperTradingError("PAPER_ORDER_SYMBOL_MISMATCH")
            if order.command_id not in applied_commands:
                raise PaperTradingError("PAPER_ORDER_COMMAND_NOT_ACCEPTED")
            prior_order = orders.get(order.order_id)
            if prior_order is not None and (
                prior_order.command_id != order.command_id
                or prior_order.account_id != order.account_id
                or prior_order.logical_agent_id != order.logical_agent_id
                or prior_order.symbol != order.symbol
            ):
                raise PaperTradingError("PAPER_ORDER_IDENTITY_CHANGED")
            orders[order.order_id] = order
        if record.event_type == "FILL_RECORDED":
            fill_payload = payload.get("fill")
            if not isinstance(fill_payload, Mapping):
                raise PaperTradingError("PAPER_FILL_EVENT_INVALID")
            fill = FillEventV1(**dict(fill_payload))
            if fill.account_id != account_id:
                raise PaperTradingError("PAPER_FILL_ACCOUNT_MISMATCH")
            if fill.symbol != permitted_symbol or fill.order_id not in orders:
                raise PaperTradingError("PAPER_FILL_ORDER_MISMATCH")
            if fill.command_id != orders[fill.order_id].command_id:
                raise PaperTradingError("PAPER_FILL_COMMAND_MISMATCH")
            if (
                fill.instrument_spec_id != instrument_spec.instrument_spec_id
                or fill.quantity_basis != instrument_spec.quantity_basis
                or fill.contract_multiplier != instrument_spec.contract_multiplier
            ):
                raise PaperTradingError("PAPER_FILL_INSTRUMENT_SPEC_MISMATCH")
            if (
                last_market_source_sha256 is None
                or fill.source_sha256 != last_market_source_sha256
                or fill.observed_at != last_market_observed_at
                or record.occurred_at != last_market_available_at
            ):
                raise PaperTradingError("PAPER_FILL_MARKET_CURSOR_MISMATCH")
            position_payload = payload.get("position")
            if not isinstance(position_payload, Mapping):
                raise PaperTradingError("PAPER_FILL_POSITION_INVALID")
            position = PaperPositionV1(**dict(position_payload))
            if position.symbol != permitted_symbol:
                raise PaperTradingError("PAPER_POSITION_SYMBOL_MISMATCH")
            positions[position.symbol] = position
            cash_balance = payload.get("cash_balance")
            realized_pnl = payload.get("account_realized_pnl")
            fees_paid = payload.get("fees_paid")
            reserved_margin = payload.get("reserved_margin")
        if record.event_type == "CARRY_ACCRUED":
            accrual_payload = payload.get("accrual")
            if not isinstance(accrual_payload, Mapping):
                raise PaperTradingError("PAPER_CARRY_EVENT_INVALID")
            accrual = CarryAccrualV1(**dict(accrual_payload))
            if accrual.account_id != account_id or accrual.symbol != permitted_symbol:
                raise PaperTradingError("PAPER_CARRY_ACCOUNT_MISMATCH")
            if record.occurred_at != accrual.available_at:
                raise PaperTradingError("PAPER_CARRY_TIME_MISMATCH")
            if accrual.status in {"MODELED", "OBSERVED"}:
                economic_key = (
                    accrual.account_id,
                    accrual.symbol,
                    accrual.kind,
                    accrual.effective_at,
                )
                if economic_key in sourced_carry_economic_keys:
                    raise PaperTradingError(
                        "PAPER_CARRY_ECONOMIC_EVENT_DUPLICATE_IN_LEDGER"
                    )
                sourced_carry_economic_keys.add(economic_key)
                if accrual.kind == "FUNDING":
                    sourced_funding_by_effective[accrual.effective_at] = accrual
            if _dt(accrual.effective_at) < _dt(records[0].occurred_at):
                raise PaperTradingError("PAPER_CARRY_PRECEDES_ACCOUNT")
            if (
                account_mode == "LINEAR_PERP"
                and accrual.kind == "BORROW"
                and accrual.status != "NOT_APPLICABLE"
            ):
                raise PaperTradingError("PAPER_PERP_BORROW_MUST_BE_NOT_APPLICABLE")
            if (
                account_mode == "LINEAR_PERP"
                and accrual.kind == "FUNDING"
                and accrual.status == "NOT_APPLICABLE"
            ):
                raise PaperTradingError("PAPER_PERP_FUNDING_CANNOT_BE_NOT_APPLICABLE")
            if account_mode == "CASH_SPOT" and accrual.status != "NOT_APPLICABLE":
                raise PaperTradingError("PAPER_CASH_SPOT_CARRY_MUST_BE_NOT_APPLICABLE")
            amount = Decimal(accrual.amount) if accrual.amount is not None else Decimal("0")
            if accrual.status in {"MODELED", "OBSERVED"}:
                expected_cash = _d(Decimal(cash_balance) - amount)
                if accrual.kind == "FUNDING":
                    expected_funding = _d(Decimal(funding_paid) + amount)
                    expected_borrow = borrow_paid
                else:
                    expected_funding = funding_paid
                    expected_borrow = _d(Decimal(borrow_paid) + amount)
                if (
                    payload.get("cash_balance") != expected_cash
                    or payload.get("funding_paid") != expected_funding
                    or payload.get("borrow_paid") != expected_borrow
                ):
                    raise PaperTradingError("PAPER_CARRY_BALANCE_RECONCILIATION_FAILED")
                cash_balance = expected_cash
                funding_paid = expected_funding
                borrow_paid = expected_borrow
            elif any(key in payload for key in ("cash_balance", "funding_paid", "borrow_paid")):
                raise PaperTradingError("PAPER_UNSOURCED_CARRY_CANNOT_CHANGE_BALANCE")
            if accrual.kind == "FUNDING":
                (
                    funding_coverage_status,
                    funding_coverage_start_at,
                    funding_coverage_end_at,
                ) = _advance_component_coverage(
                    current_status=funding_coverage_status,
                    current_start_at=funding_coverage_start_at,
                    current_end_at=funding_coverage_end_at,
                    accrual=accrual,
                    account_opened_at=records[0].occurred_at,
                )
            else:
                (
                    borrow_coverage_status,
                    borrow_coverage_start_at,
                    borrow_coverage_end_at,
                ) = _advance_component_coverage(
                    current_status=borrow_coverage_status,
                    current_start_at=borrow_coverage_start_at,
                    current_end_at=borrow_coverage_end_at,
                    accrual=accrual,
                    account_opened_at=records[0].occurred_at,
                )
            carry_coverage_status = _aggregate_carry_coverage(
                funding_coverage_status, borrow_coverage_status
            )
        if record.event_type == "FUNDING_COVERAGE_ADVANCED":
            if set(payload) != {"advance"} or not isinstance(
                payload.get("advance"), Mapping
            ):
                raise PaperTradingError("PAPER_FUNDING_COVERAGE_EVENT_INVALID")
            advance = FundingCoverageAdvanceV1(**dict(payload["advance"]))
            expected_segment_start = (
                records[0].occurred_at
                if funding_complete_end_at is None
                else funding_complete_end_at
            )
            if (
                account_mode != "LINEAR_PERP"
                or advance.account_id != account_id
                or advance.symbol != permitted_symbol
                or advance.coverage_start_at != expected_segment_start
                or record.occurred_at != advance.available_at
            ):
                raise PaperTradingError("PAPER_FUNDING_COVERAGE_ACCOUNT_MISMATCH")
            start = _dt(advance.coverage_start_at)
            end = _dt(advance.coverage_end_at)
            actual = tuple(
                sorted(
                    (
                        effective_at,
                        canonical_digest(accrual.to_dict()),
                    )
                    for effective_at, accrual in sourced_funding_by_effective.items()
                    if start <= _dt(effective_at) <= end
                )
            )
            expected = tuple(
                zip(
                    advance.event_effective_ats,
                    advance.event_accrual_sha256s,
                )
            )
            if actual != expected:
                raise PaperTradingError(
                    "PAPER_FUNDING_COVERAGE_LEDGER_BINDING_MISMATCH"
                )
            if funding_complete_end_at is not None and _dt(
                advance.coverage_end_at
            ) <= _dt(funding_complete_end_at):
                raise PaperTradingError("PAPER_FUNDING_COVERAGE_REGRESSION")
            funding_complete_start_at = (
                advance.coverage_start_at
                if funding_complete_start_at is None
                else funding_complete_start_at
            )
            funding_complete_end_at = advance.coverage_end_at
            funding_coverage_status = "COMPLETE"
            funding_coverage_start_at = funding_complete_start_at
            funding_coverage_end_at = funding_complete_end_at
            carry_coverage_status = _aggregate_carry_coverage(
                funding_coverage_status, borrow_coverage_status
            )

    return PaperAccountVersionV1(
        account_id=account_id,
        version=records[-1].revision,
        account_mode=account_mode,
        owner_logical_agent_id=owner,
        base_currency=base_currency,
        permitted_symbol=permitted_symbol,
        max_leverage=max_leverage,
        instrument_spec=instrument_spec,
        owner_agent_generation=owner_agent_generation,
        initial_balance=initial_balance,
        cash_balance=cash_balance,
        reserved_margin=reserved_margin,
        realized_pnl=realized_pnl,
        fees_paid=fees_paid,
        funding_paid=funding_paid,
        borrow_paid=borrow_paid,
        carry_coverage_status=carry_coverage_status,
        funding_coverage_status=funding_coverage_status,
        borrow_coverage_status=borrow_coverage_status,
        funding_coverage_start_at=funding_coverage_start_at,
        funding_coverage_end_at=funding_coverage_end_at,
        borrow_coverage_start_at=borrow_coverage_start_at,
        borrow_coverage_end_at=borrow_coverage_end_at,
        positions=tuple(sorted(positions.values(), key=lambda item: item.symbol)),
        orders=tuple(sorted(orders.values(), key=lambda item: item.order_id)),
        applied_command_ids=tuple(applied_commands),
        last_event_id=records[-1].event_id,
        last_fact_at=last_fact_at,
        last_market_observed_at=last_market_observed_at,
        last_market_available_at=last_market_available_at,
        last_market_source_sha256=last_market_source_sha256,
    )


class PaperTradingService:
    """Apply explicit Agent commands; never choose a market action itself."""

    def __init__(
        self,
        ledger: PaperLedgerPort,
        *,
        cost_models: Sequence[PaperCostModelV1],
        decision_authority: PaperDecisionAuthorityPort | None = None,
        market_evidence: PaperMarketEvidencePort | None = None,
        carry_evidence: PaperCarryEvidencePort | None = None,
        require_execution_intent: bool = False,
        max_position_notional: str | Decimal | None = None,
    ) -> None:
        self._ledger = ledger
        self._decision_authority = decision_authority
        self._market_evidence = market_evidence
        self._carry_evidence = carry_evidence
        if type(require_execution_intent) is not bool:
            raise PaperTradingError("PAPER_EXECUTION_INTENT_MODE_INVALID")
        self._require_execution_intent = require_execution_intent
        if isinstance(max_position_notional, bool):
            raise PaperTradingError("PAPER_MAX_POSITION_NOTIONAL_INVALID")
        try:
            parsed_position_cap = (
                None
                if max_position_notional is None
                else Decimal(max_position_notional)
            )
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise PaperTradingError("PAPER_MAX_POSITION_NOTIONAL_INVALID") from exc
        if parsed_position_cap is not None and (
            not parsed_position_cap.is_finite() or parsed_position_cap <= 0
        ):
            raise PaperTradingError("PAPER_MAX_POSITION_NOTIONAL_INVALID")
        self._max_position_notional = parsed_position_cap
        self._cost_models = {model.model_id: model for model in cost_models}
        if not self._cost_models:
            raise PaperTradingError("PAPER_COST_MODEL_REQUIRED")
        if len(self._cost_models) != len(tuple(cost_models)):
            raise PaperTradingError("PAPER_COST_MODEL_ID_DUPLICATE")

    def open_account(
        self,
        *,
        account_id: str,
        account_mode: str,
        owner_logical_agent_id: str,
        base_currency: str,
        permitted_symbol: str,
        max_leverage: str,
        initial_balance: str,
        opened_at: str,
        owner_agent_generation: int = 1,
        instrument_spec: InstrumentSpecV1 | None = None,
    ) -> PaperAccountVersionV1:
        existing = self._ledger.load_records(account_id)
        if instrument_spec is None:
            if account_mode == "LINEAR_PERP":
                raise PaperTradingError(
                    "PAPER_LINEAR_PERP_INSTRUMENT_SPEC_REQUIRED"
                )
            instrument_spec = InstrumentSpecV1(
                instrument_spec_id=f"{permitted_symbol.lower()}-base-unit-v1",
                symbol=permitted_symbol,
                account_mode=account_mode,
                quote_currency=base_currency,
                contract_multiplier="1",
                quantity_basis="BASE_UNITS",
            )
        if (
            account_mode == "LINEAR_PERP"
            and instrument_spec.parameter_status != "OBSERVED_RAW_BOUND"
        ):
            raise PaperTradingError(
                "PAPER_LINEAR_PERP_INSTRUMENT_SPEC_RAW_BOUND_REQUIRED"
            )
        if instrument_spec.parameter_status == "OBSERVED_RAW_BOUND":
            verifier = getattr(self._market_evidence, "verifies_instrument_spec", None)
            if verifier is None or not verifier(
                instrument_spec,
                available_by=opened_at,
            ):
                raise PaperTradingError("PAPER_INSTRUMENT_SPEC_EVIDENCE_UNVERIFIED")
        payload = {
            "account_mode": account_mode,
            "owner_logical_agent_id": owner_logical_agent_id,
            "base_currency": base_currency,
            "permitted_symbol": permitted_symbol,
            "max_leverage": max_leverage,
            "instrument_spec": instrument_spec.to_dict(),
            "owner_agent_generation": owner_agent_generation,
            "initial_balance": initial_balance,
        }
        # Validate the complete initial projection before any append.  This keeps
        # an invalid account request from leaving a durable partial fact.
        funding_coverage, borrow_coverage, carry_coverage = _initial_carry_coverage(
            account_mode
        )
        PaperAccountVersionV1(
            account_id=account_id,
            version=1,
            account_mode=account_mode,
            owner_logical_agent_id=owner_logical_agent_id,
            base_currency=base_currency,
            permitted_symbol=permitted_symbol,
            max_leverage=max_leverage,
            instrument_spec=instrument_spec,
            owner_agent_generation=owner_agent_generation,
            initial_balance=initial_balance,
            cash_balance=initial_balance,
            reserved_margin="0",
            realized_pnl="0",
            fees_paid="0",
            funding_paid="0",
            borrow_paid="0",
            carry_coverage_status=carry_coverage,
            funding_coverage_status=funding_coverage,
            borrow_coverage_status=borrow_coverage,
            funding_coverage_start_at=None,
            funding_coverage_end_at=None,
            borrow_coverage_start_at=None,
            borrow_coverage_end_at=None,
            positions=(),
            orders=(),
            applied_command_ids=(),
            last_event_id="account-opened-validation",
            last_fact_at=opened_at,
            last_market_observed_at=None,
            last_market_available_at=None,
            last_market_source_sha256=None,
        )
        if existing:
            if existing[0].payload != payload:
                raise PaperTradingError("PAPER_ACCOUNT_ID_CONFLICT")
            return replay_paper_account(existing)
        self._ledger.append_many(
            account_id=account_id,
            expected_revision=0,
            events=(
                {
                    "event_id": _event_id("account-opened", {"account_id": account_id, **payload}),
                    "event_type": "ACCOUNT_OPENED",
                    "occurred_at": opened_at,
                    "payload": payload,
                },
            ),
        )
        return self.load_account(account_id)

    def load_account(self, account_id: str) -> PaperAccountVersionV1:
        return replay_paper_account(self._ledger.load_records(account_id))

    def submit(self, command: PaperCommandV1) -> PaperAccountVersionV1:
        if self._require_execution_intent:
            raise PaperTradingError("PAPER_EXECUTION_INTENT_REQUIRED")
        return self._submit(
            command,
            execution_intent=None,
            accepted_at=command.submitted_at,
        )

    def submit_intent(
        self,
        execution_intent: PaperExecutionIntentV1,
        *,
        received_at: str | None = None,
    ) -> PaperAccountVersionV1:
        if not isinstance(execution_intent, PaperExecutionIntentV1):
            raise PaperTradingError("PAPER_EXECUTION_INTENT_INVALID")
        trusted_received_at = (
            (
                execution_intent.authored_at
                if execution_intent.command is None
                else execution_intent.command.submitted_at
            )
            if received_at is None
            else received_at
        )
        if received_at is None and self._require_execution_intent:
            raise PaperTradingError("PAPER_EXECUTION_INTENT_RECEIPT_TIME_REQUIRED")
        try:
            receipt_time = _dt(trusted_received_at)
        except (AttributeError, ValueError) as exc:
            raise PaperTradingError(
                "PAPER_EXECUTION_INTENT_RECEIPT_TIME_INVALID"
            ) from exc
        if receipt_time.tzinfo is None or receipt_time.utcoffset() is None:
            raise PaperTradingError(
                "PAPER_EXECUTION_INTENT_RECEIPT_TIME_INVALID"
            )
        if (
            receipt_time < _dt(execution_intent.authored_at)
            or receipt_time > _dt(execution_intent.valid_until)
        ):
            raise PaperTradingError("PAPER_EXECUTION_INTENT_EXPIRED")
        if execution_intent.command is None:
            return self._record_non_executable_intent(
                execution_intent,
                received_at=trusted_received_at,
            )
        if execution_intent.bracket is not None:
            return self._submit_bracket(
                execution_intent,
                accepted_at=trusted_received_at,
            )
        return self._submit(
            execution_intent.command,
            execution_intent=execution_intent,
            accepted_at=trusted_received_at,
        )

    def _record_non_executable_intent(
        self,
        execution_intent: PaperExecutionIntentV1,
        *,
        received_at: str,
    ) -> PaperAccountVersionV1:
        """Persist Agent-owned WAIT/HOLD/WATCH semantics without an order."""

        records = self._ledger.load_records(execution_intent.account_id)
        state = replay_paper_account(records)
        prior_records = tuple(
            record
            for record in records
            if record.event_type in {"INTENT_RECORDED", "COMMAND_ACCEPTED"}
            and isinstance(record.payload.get("execution_intent"), Mapping)
            and record.payload["execution_intent"].get("intent_id")
            == execution_intent.intent_id
        )
        if prior_records:
            if len(prior_records) != 1:
                raise PaperTradingError("PAPER_EXECUTION_INTENT_ID_CONFLICT")
            prior = prior_records[0]
            if (
                prior.event_type != "INTENT_RECORDED"
                or prior.payload.get("execution_intent")
                != execution_intent.to_dict()
                or prior.occurred_at != received_at
            ):
                raise PaperTradingError("PAPER_EXECUTION_INTENT_ID_CONFLICT")
            return state
        if state.version != execution_intent.expected_account_version:
            raise PaperTradingError("PAPER_ACCOUNT_VERSION_CONFLICT")
        if execution_intent.logical_agent_id != state.owner_logical_agent_id:
            raise PaperTradingError("PAPER_AGENT_ACCOUNT_OWNERSHIP_MISMATCH")
        if self._decision_authority is None:
            raise PaperTradingError("PAPER_DECISION_AUTHORITY_UNCONFIGURED")
        current_generation = self._decision_authority.current_generation(
            execution_intent.logical_agent_id
        )
        if (
            current_generation is None
            or execution_intent.agent_generation != current_generation
            or execution_intent.agent_generation != state.owner_agent_generation
        ):
            raise PaperTradingError("PAPER_AGENT_GENERATION_NOT_CURRENT")
        verifier = getattr(
            self._decision_authority, "verifies_execution_intent", None
        )
        if not callable(verifier) or not verifier(execution_intent):
            raise PaperTradingError("PAPER_EXECUTION_INTENT_CONTEXT_UNVERIFIED")
        if _dt(received_at) < _dt(state.last_fact_at):
            raise PaperTradingError("PAPER_INTENT_TIME_REGRESSION")
        if execution_intent.symbol != state.permitted_symbol:
            raise PaperTradingError("PAPER_ACCOUNT_SYMBOL_MISMATCH")
        intent_payload: dict[str, Any] = {
            "execution_intent": execution_intent.to_dict()
        }
        linkage = _episode_linkage_for_intent(
            records, execution_intent=execution_intent
        )
        if linkage is not None:
            intent_payload["static_comparator_linkage"] = linkage.to_dict()
        self._ledger.append_many(
            account_id=execution_intent.account_id,
            expected_revision=state.version,
            events=(
                {
                    "event_id": _event_id(
                        "intent-recorded", execution_intent.to_dict()
                    ),
                    "event_type": "INTENT_RECORDED",
                    "occurred_at": received_at,
                    "payload": intent_payload,
                },
            ),
        )
        return self.load_account(execution_intent.account_id)

    def _submit_bracket(
        self,
        execution_intent: PaperExecutionIntentV1,
        *,
        accepted_at: str,
    ) -> PaperAccountVersionV1:
        """Atomically accept one flat-entry bracket and hold every exit leg."""

        bracket = execution_intent.bracket
        if bracket is None or execution_intent.command != bracket.entry:
            raise PaperTradingError("PAPER_BRACKET_INVALID")
        command = bracket.entry
        records = self._ledger.load_records(command.account_id)
        state = replay_paper_account(records)
        prior = next(
            (
                record
                for record in records
                if record.event_type == "COMMAND_ACCEPTED"
                and isinstance(record.payload.get("execution_intent"), Mapping)
                and record.payload["execution_intent"].get("intent_id")
                == execution_intent.intent_id
            ),
            None,
        )
        if prior is not None:
            expected_payload: dict[str, Any] = {
                "command": command.to_dict(),
                "commands": tuple(item.to_dict() for item in bracket.commands),
                "execution_intent": execution_intent.to_dict(),
                "accepted_at": accepted_at,
            }
            if (
                any(
                    prior.payload.get(key) != value
                    for key, value in expected_payload.items()
                )
                or set(prior.payload)
                not in (
                    set(expected_payload),
                    {*expected_payload, "static_comparator_linkage"},
                )
                or prior.occurred_at != accepted_at
            ):
                raise PaperTradingError("PAPER_EXECUTION_INTENT_ID_CONFLICT")
            return state
        if any(
            item.command_id in state.applied_command_ids for item in bracket.commands
        ):
            raise PaperTradingError("PAPER_COMMAND_ID_CONFLICT")
        if state.version != command.expected_account_version:
            raise PaperTradingError("PAPER_ACCOUNT_VERSION_CONFLICT")
        if command.logical_agent_id != state.owner_logical_agent_id:
            raise PaperTradingError("PAPER_AGENT_ACCOUNT_OWNERSHIP_MISMATCH")
        if self._decision_authority is None:
            raise PaperTradingError("PAPER_DECISION_AUTHORITY_UNCONFIGURED")
        current_generation = self._decision_authority.current_generation(
            command.logical_agent_id
        )
        if current_generation is None or command.agent_generation != current_generation:
            raise PaperTradingError("PAPER_AGENT_GENERATION_NOT_CURRENT")
        if not all(
            self._decision_authority.verifies_decision(item)
            for item in bracket.commands
        ):
            raise PaperTradingError("PAPER_DECISION_REFERENCE_UNVERIFIED")
        verifier = getattr(
            self._decision_authority, "verifies_execution_intent", None
        )
        if not callable(verifier) or not verifier(execution_intent):
            raise PaperTradingError("PAPER_EXECUTION_INTENT_CONTEXT_UNVERIFIED")
        if _dt(accepted_at) < _dt(command.submitted_at):
            raise PaperTradingError("PAPER_COMMAND_ACCEPTED_BEFORE_AUTHORED")
        if _dt(accepted_at) < _dt(state.last_fact_at):
            raise PaperTradingError("PAPER_COMMAND_TIME_REGRESSION")
        if command.symbol != state.permitted_symbol:
            raise PaperTradingError("PAPER_ACCOUNT_SYMBOL_MISMATCH")
        if state.account_mode == "CASH_SPOT" and command.side == "SELL":
            raise PaperTradingError("PAPER_CASH_SPOT_SHORT_FORBIDDEN")
        if command.cost_model_id not in self._cost_models:
            raise PaperTradingError("PAPER_COST_MODEL_UNKNOWN")
        model = self._cost_models[command.cost_model_id]
        if model.effective_from is not None and _dt(accepted_at) < _dt(
            model.effective_from
        ):
            raise PaperTradingError("PAPER_COST_MODEL_NOT_YET_EFFECTIVE")
        if model.effective_to is not None and _dt(accepted_at) >= _dt(
            model.effective_to
        ):
            raise PaperTradingError("PAPER_COST_MODEL_EXPIRED")

        multiplier = Decimal(state.instrument_spec.contract_multiplier)
        entry_quantity = Decimal(command.quantity or "0")
        entry_price = Decimal(command.limit_price or "0")
        stop_price = Decimal(bracket.protective_stop.trigger_price or "0")
        entry_notional = entry_quantity * entry_price * multiplier
        planned_stop_loss = abs(stop_price - entry_price) * entry_quantity * multiplier
        if entry_notional > Decimal(execution_intent.risk_budget["notional_cap"]):
            raise PaperTradingError("PAPER_INTENT_NOTIONAL_CAP_EXCEEDED")
        if planned_stop_loss > Decimal(execution_intent.risk_budget["maximum_loss"]):
            raise PaperTradingError("PAPER_INTENT_PLANNED_STOP_LOSS_EXCEEDED")

        linkage = _episode_linkage_for_intent(
            records, execution_intent=execution_intent
        )
        accepted_payload: dict[str, Any] = {
            "command": command.to_dict(),
            "commands": tuple(item.to_dict() for item in bracket.commands),
            "execution_intent": execution_intent.to_dict(),
            "accepted_at": accepted_at,
        }
        if linkage is not None:
            accepted_payload["static_comparator_linkage"] = linkage.to_dict()
        events: list[Mapping[str, Any]] = [
            {
                "event_id": _event_id("command-accepted", accepted_payload),
                "event_type": "COMMAND_ACCEPTED",
                "occurred_at": accepted_at,
                "payload": accepted_payload,
            }
        ]
        prior_bracket_in_episode = any(
            record.event_type == "COMMAND_ACCEPTED"
            and isinstance(record.payload.get("execution_intent"), Mapping)
            and record.payload["execution_intent"].get("episode_id")
            == execution_intent.episode_id
            and isinstance(
                record.payload["execution_intent"].get("bracket"), Mapping
            )
            for record in records
        )
        current_position = _position_by_symbol(state.positions, command.symbol)
        if (
            not prior_bracket_in_episode
            and Decimal(current_position.quantity) == 0
        ):
            comparator = StaticNoTransitionComparatorV1.create(
                execution_intent=execution_intent,
                preregistered_at=accepted_at,
                account_pre_version=state.version,
                account_pre_head_record_sha256=records[-1].record_sha256,
                instrument_spec=state.instrument_spec,
                cost_model=model,
            )
            comparator_payload = {"comparator": comparator.to_dict()}
            events.append(
                {
                    "event_id": _event_id(
                        "static-no-transition-preregistered",
                        comparator_payload,
                    ),
                    "event_type": "STATIC_NO_TRANSITION_PREREGISTERED",
                    "occurred_at": accepted_at,
                    "payload": comparator_payload,
                }
            )
        for index, item in enumerate(bracket.commands):
            order = OrderTruthV1(
                order_id=item.command_id,
                command_id=item.command_id,
                account_id=item.account_id,
                logical_agent_id=item.logical_agent_id,
                symbol=item.symbol,
                command_type=item.command_type,
                side=item.side,
                original_quantity=item.quantity,
                filled_quantity="0",
                remaining_quantity=item.quantity,
                limit_price=item.limit_price,
                trigger_price=item.trigger_price,
                reduce_only=item.reduce_only,
                time_in_force=item.time_in_force,
                expires_at=item.expires_at,
                cost_model_id=item.cost_model_id,
                cost_model_digest=model.model_digest,
                state="OPEN" if index == 0 else "HELD",
                created_at=accepted_at,
                updated_at=accepted_at,
                resolution_reason=(None if index == 0 else "BRACKET_ENTRY_NOT_FILLED"),
            )
            event_type = "ORDER_OPENED" if index == 0 else "ORDER_HELD"
            events.append(
                {
                    "event_id": _event_id(
                        event_type.lower().replace("_", "-"),
                        {"order": order.to_dict()},
                    ),
                    "event_type": event_type,
                    "occurred_at": accepted_at,
                    "payload": {"order": order.to_dict()},
                }
            )

        projected: tuple[PaperLedgerRecordV1, ...] = tuple(records)
        for event in events:
            projected = _project_event(
                projected,
                account_id=command.account_id,
                event=event,
            )
        replay_paper_account(projected)
        self._ledger.append_many(
            account_id=command.account_id,
            expected_revision=state.version,
            events=tuple(events),
        )
        return self.load_account(command.account_id)

    def _submit(
        self,
        command: PaperCommandV1,
        *,
        execution_intent: PaperExecutionIntentV1 | None,
        accepted_at: str,
    ) -> PaperAccountVersionV1:
        records = self._ledger.load_records(command.account_id)
        state = replay_paper_account(records)
        prior = next(
            (
                record.payload.get("command")
                for record in records
                if record.event_type == "COMMAND_ACCEPTED"
                and isinstance(record.payload.get("command"), Mapping)
                and record.payload["command"].get("command_id") == command.command_id
            ),
            None,
        )
        if prior is not None:
            if dict(prior) != command.to_dict():
                raise PaperTradingError("PAPER_COMMAND_ID_CONFLICT")
            prior_intent = next(
                (
                    record.payload.get("execution_intent")
                    for record in records
                    if record.event_type == "COMMAND_ACCEPTED"
                    and isinstance(record.payload.get("command"), Mapping)
                    and record.payload["command"].get("command_id")
                    == command.command_id
                ),
                None,
            )
            supplied_intent = (
                None
                if execution_intent is None
                else execution_intent.to_dict()
            )
            if prior_intent != supplied_intent:
                raise PaperTradingError("PAPER_EXECUTION_INTENT_ID_CONFLICT")
            prior_record = next(
                record
                for record in records
                if record.event_type == "COMMAND_ACCEPTED"
                and isinstance(record.payload.get("command"), Mapping)
                and record.payload["command"].get("command_id")
                == command.command_id
            )
            prior_accepted_at = prior_record.payload.get(
                "accepted_at", command.submitted_at
            )
            if prior_accepted_at != accepted_at:
                raise PaperTradingError("PAPER_EXECUTION_INTENT_RECEIPT_CONFLICT")
            return state
        if state.version != command.expected_account_version:
            raise PaperTradingError("PAPER_ACCOUNT_VERSION_CONFLICT")
        if command.logical_agent_id != state.owner_logical_agent_id:
            raise PaperTradingError("PAPER_AGENT_ACCOUNT_OWNERSHIP_MISMATCH")
        if self._decision_authority is None:
            raise PaperTradingError("PAPER_DECISION_AUTHORITY_UNCONFIGURED")
        current_generation = self._decision_authority.current_generation(
            command.logical_agent_id
        )
        if current_generation is None or command.agent_generation != current_generation:
            raise PaperTradingError("PAPER_AGENT_GENERATION_NOT_CURRENT")
        if not self._decision_authority.verifies_decision(command):
            raise PaperTradingError("PAPER_DECISION_REFERENCE_UNVERIFIED")
        if execution_intent is not None:
            verifier = getattr(
                self._decision_authority, "verifies_execution_intent", None
            )
            if not callable(verifier) or not verifier(execution_intent):
                raise PaperTradingError(
                    "PAPER_EXECUTION_INTENT_CONTEXT_UNVERIFIED"
                )
        if _dt(accepted_at) < _dt(command.submitted_at):
            raise PaperTradingError("PAPER_COMMAND_ACCEPTED_BEFORE_AUTHORED")
        if _dt(accepted_at) < _dt(state.last_fact_at):
            raise PaperTradingError("PAPER_COMMAND_TIME_REGRESSION")
        if command.symbol != state.permitted_symbol:
            raise PaperTradingError("PAPER_ACCOUNT_SYMBOL_MISMATCH")
        if command.cost_model_id not in self._cost_models:
            raise PaperTradingError("PAPER_COST_MODEL_UNKNOWN")
        model = self._cost_models[command.cost_model_id]
        if model.effective_from is not None and _dt(accepted_at) < _dt(model.effective_from):
            raise PaperTradingError("PAPER_COST_MODEL_NOT_YET_EFFECTIVE")
        if model.effective_to is not None and _dt(accepted_at) >= _dt(model.effective_to):
            raise PaperTradingError("PAPER_COST_MODEL_EXPIRED")

        accepted_payload: dict[str, Any] = {"command": command.to_dict()}
        if execution_intent is not None:
            accepted_payload["execution_intent"] = execution_intent.to_dict()
            accepted_payload["accepted_at"] = accepted_at
            linkage = _episode_linkage_for_intent(
                records, execution_intent=execution_intent
            )
            if linkage is not None:
                accepted_payload["static_comparator_linkage"] = linkage.to_dict()
        accepted = {
            "event_id": _event_id("command-accepted", accepted_payload),
            "event_type": "COMMAND_ACCEPTED",
            "occurred_at": accepted_at,
            "payload": accepted_payload,
        }
        if command.command_type == "CANCEL":
            order = next(
                (order for order in state.orders if order.order_id == command.target_order_id),
                None,
            )
            if order is None or order.state in PAPER_TERMINAL_ORDER_STATES:
                raise PaperTradingError("PAPER_CANCEL_TARGET_NOT_OPEN")
            cancelled = replace(
                order,
                state="CANCELLED",
                updated_at=accepted_at,
                resolution_reason="AGENT_CANCEL",
            )
            order_event = {
                "event_id": _event_id("order-cancelled", {"command": command.to_dict(), "order": cancelled.to_dict()}),
                "event_type": "ORDER_CANCELLED",
                "occurred_at": accepted_at,
                "payload": {"order": cancelled.to_dict()},
            }
            order_events: list[Mapping[str, Any]] = [order_event]
            bracket = self._brackets_by_order(records).get(order.order_id)
            if (
                bracket is not None
                and order.order_id == bracket.entry.command_id
                and Decimal(order.filled_quantity) == 0
                and Decimal(
                    _position_by_symbol(state.positions, order.symbol).quantity
                )
                == 0
            ):
                working = self._with_order(state, cancelled)
                sibling_events, _ = self._cancel_bracket_orders(
                    state=working,
                    bracket=bracket,
                    order_ids={
                        item.command_id
                        for item in (
                            bracket.protective_stop,
                            *bracket.take_profits,
                        )
                    },
                    occurred_at=accepted_at,
                    reason="BRACKET_ENTRY_CANCELLED_WITHOUT_FILL",
                )
                order_events.extend(sibling_events)
        else:
            rejection_reason = self._pretrade_rejection(state, command)
            order = OrderTruthV1(
                order_id=command.command_id,
                command_id=command.command_id,
                account_id=command.account_id,
                logical_agent_id=command.logical_agent_id,
                symbol=command.symbol,
                command_type=command.command_type,
                side=command.side,
                original_quantity=command.quantity,
                filled_quantity="0",
                remaining_quantity=command.quantity,
                limit_price=command.limit_price,
                trigger_price=command.trigger_price,
                reduce_only=command.reduce_only,
                time_in_force=command.time_in_force,
                expires_at=command.expires_at,
                cost_model_id=command.cost_model_id,
                cost_model_digest=model.model_digest,
                state="REJECTED" if rejection_reason else "OPEN",
                created_at=accepted_at,
                updated_at=accepted_at,
                resolution_reason=rejection_reason,
            )
            event_type = "ORDER_REJECTED" if rejection_reason else "ORDER_OPENED"
            order_event = {
                "event_id": _event_id(event_type.lower().replace("_", "-"), {"order": order.to_dict()}),
                "event_type": event_type,
                "occurred_at": accepted_at,
                "payload": {"order": order.to_dict()},
            }
            order_events = [order_event]
        self._ledger.append_many(
            account_id=command.account_id,
            expected_revision=state.version,
            events=(accepted, *order_events),
        )
        return self.load_account(command.account_id)

    def _prepare_carry_event(
        self,
        *,
        records: Sequence[PaperLedgerRecordV1],
        state: PaperAccountVersionV1,
        accrual: CarryAccrualV1,
    ) -> Mapping[str, Any] | None:
        """Validate one carry event completely and return its immutable fact."""

        prior = next(
            (record for record in records if record.event_id == accrual.accrual_id),
            None,
        )
        if prior is not None:
            if (
                prior.event_type != "CARRY_ACCRUED"
                or prior.payload.get("accrual") != accrual.to_dict()
            ):
                raise PaperTradingError("PAPER_CARRY_ID_CONFLICT")
            return None
        if accrual.status in {"MODELED", "OBSERVED"}:
            current_document = accrual.to_dict()
            economic_fields = ("account_id", "symbol", "kind", "effective_at")
            current_economic_key = tuple(
                current_document[field] for field in economic_fields
            )
            current_content = {
                key: value
                for key, value in current_document.items()
                if key not in {"accrual_id", "reason"}
            }
            for record in records:
                if record.event_type != "CARRY_ACCRUED":
                    continue
                prior_document = record.payload.get("accrual")
                if not isinstance(prior_document, Mapping) or prior_document.get(
                    "status"
                ) not in {"MODELED", "OBSERVED"}:
                    continue
                prior_economic_key = tuple(
                    prior_document.get(field) for field in economic_fields
                )
                if prior_economic_key != current_economic_key:
                    continue
                prior_content = {
                    key: value
                    for key, value in prior_document.items()
                    if key not in {"accrual_id", "reason"}
                }
                if prior_content == current_content:
                    return None
                raise PaperTradingError("PAPER_CARRY_ECONOMIC_EVENT_CONFLICT")
        if (
            accrual.account_id != state.account_id
            or accrual.symbol != state.permitted_symbol
        ):
            raise PaperTradingError("PAPER_CARRY_ACCOUNT_MISMATCH")
        if _dt(accrual.available_at) < _dt(state.last_fact_at):
            raise PaperTradingError("PAPER_CARRY_TIME_REGRESSION")
        if (
            state.account_mode == "LINEAR_PERP"
            and accrual.kind == "BORROW"
            and accrual.status != "NOT_APPLICABLE"
        ):
            raise PaperTradingError("PAPER_PERP_BORROW_MUST_BE_NOT_APPLICABLE")
        if (
            state.account_mode == "LINEAR_PERP"
            and accrual.kind == "FUNDING"
            and accrual.status == "NOT_APPLICABLE"
        ):
            raise PaperTradingError("PAPER_PERP_FUNDING_CANNOT_BE_NOT_APPLICABLE")
        if (
            state.account_mode == "CASH_SPOT"
            and accrual.status != "NOT_APPLICABLE"
        ):
            raise PaperTradingError("PAPER_CASH_SPOT_CARRY_MUST_BE_NOT_APPLICABLE")
        prefix = accrual.kind.lower()
        _advance_component_coverage(
            current_status=getattr(state, f"{prefix}_coverage_status"),
            current_start_at=getattr(state, f"{prefix}_coverage_start_at"),
            current_end_at=getattr(state, f"{prefix}_coverage_end_at"),
            accrual=accrual,
            account_opened_at=records[0].occurred_at,
        )
        if accrual.status in {"MODELED", "OBSERVED"}:
            model = accrual.settlement_model
            if model is not None:
                if not isinstance(model, FundingSettlementModelV1):
                    raise PaperTradingError("PAPER_FUNDING_MODEL_INVALID")
                cost_model = self._cost_models.get(model.cost_model_id)
                if (
                    cost_model is None
                    or cost_model.model_digest != model.cost_model_digest
                ):
                    raise PaperTradingError("PAPER_FUNDING_COST_MODEL_MISMATCH")
            if self._carry_evidence is None:
                raise PaperTradingError("PAPER_CARRY_EVIDENCE_UNCONFIGURED")
            if not self._carry_evidence.verifies_carry_accrual(accrual):
                raise PaperTradingError("PAPER_CARRY_EVIDENCE_UNVERIFIED")
        if (
            accrual.status in {"MODELED", "OBSERVED"}
            and state.account_mode == "LINEAR_PERP"
        ):
            effective_records = tuple(
                record
                for record in records
                if _dt(record.occurred_at) <= _dt(accrual.effective_at)
            )
            if not effective_records:
                raise PaperTradingError("PAPER_CARRY_EFFECTIVE_STATE_UNKNOWN")
            effective_state = replay_paper_account(effective_records)
            position = _position_by_symbol(
                effective_state.positions, effective_state.permitted_symbol
            )
            if (
                accrual.kind != "FUNDING"
                or Decimal(accrual.position_quantity) != Decimal(position.quantity)
            ):
                raise PaperTradingError(
                    "PAPER_FUNDING_POSITION_SNAPSHOT_MISMATCH"
                )
            expected_amount = (
                Decimal(accrual.position_quantity)
                * Decimal(effective_state.instrument_spec.contract_multiplier)
                * Decimal(accrual.reference_price)
                * Decimal(accrual.rate)
            )
            if Decimal(accrual.amount) != expected_amount:
                raise PaperTradingError("PAPER_FUNDING_AMOUNT_MISMATCH")
        amount = (
            Decimal(accrual.amount)
            if accrual.amount is not None
            else Decimal("0")
        )
        carry_payload: dict[str, Any] = {"accrual": accrual.to_dict()}
        if accrual.status in {"MODELED", "OBSERVED"}:
            carry_payload["cash_balance"] = _d(
                Decimal(state.cash_balance) - amount
            )
            carry_payload["funding_paid"] = _d(
                Decimal(state.funding_paid)
                + (amount if accrual.kind == "FUNDING" else Decimal("0"))
            )
            carry_payload["borrow_paid"] = _d(
                Decimal(state.borrow_paid)
                + (amount if accrual.kind == "BORROW" else Decimal("0"))
            )
        return {
            "event_id": accrual.accrual_id,
            "event_type": "CARRY_ACCRUED",
            "occurred_at": accrual.available_at,
            "payload": carry_payload,
        }

    def accrue_carry(
        self,
        *,
        account_id: str,
        expected_account_version: int,
        accrual: CarryAccrualV1,
    ) -> PaperAccountVersionV1:
        """Append one explicit carry fact; never infer a missing funding interval."""

        records = self._ledger.load_records(account_id)
        state = replay_paper_account(records)
        event = self._prepare_carry_event(
            records=records,
            state=state,
            accrual=accrual,
        )
        if event is None:
            return state
        if state.version != expected_account_version:
            raise PaperTradingError("PAPER_ACCOUNT_VERSION_CONFLICT")
        self._ledger.append_many(
            account_id=account_id,
            expected_revision=state.version,
            events=(event,),
        )
        return self.load_account(account_id)

    def _prepare_funding_coverage_event(
        self,
        *,
        records: Sequence[PaperLedgerRecordV1],
        state: PaperAccountVersionV1,
        advance: FundingCoverageAdvanceV1,
    ) -> Mapping[str, Any] | None:
        """Validate one COMPLETE-window proof without writing it."""

        prior = next(
            (record for record in records if record.event_id == advance.advance_id),
            None,
        )
        if prior is not None:
            if (
                prior.event_type != "FUNDING_COVERAGE_ADVANCED"
                or prior.payload.get("advance") != advance.to_dict()
            ):
                raise PaperTradingError("PAPER_FUNDING_COVERAGE_ID_CONFLICT")
            return None
        prior_advance_record = next(
            (
                record
                for record in reversed(records)
                if record.event_type == "FUNDING_COVERAGE_ADVANCED"
                and isinstance(record.payload.get("advance"), Mapping)
            ),
            None,
        )
        expected_segment_start = (
            records[0].occurred_at
            if prior_advance_record is None
            else FundingCoverageAdvanceV1(
                **dict(prior_advance_record.payload["advance"])
            ).coverage_end_at
        )
        if (
            state.account_mode != "LINEAR_PERP"
            or state.borrow_coverage_status != "NOT_APPLICABLE"
            or advance.account_id != state.account_id
            or advance.symbol != state.permitted_symbol
            or advance.coverage_start_at != expected_segment_start
        ):
            raise PaperTradingError("PAPER_FUNDING_COVERAGE_ACCOUNT_MISMATCH")
        if _dt(advance.available_at) < _dt(state.last_fact_at):
            raise PaperTradingError("PAPER_FUNDING_COVERAGE_TIME_REGRESSION")
        model = advance.settlement_model
        cost_model = self._cost_models.get(model.cost_model_id)
        if cost_model is None or cost_model.model_digest != model.cost_model_digest:
            raise PaperTradingError("PAPER_FUNDING_COST_MODEL_MISMATCH")
        verifier = getattr(
            self._carry_evidence, "verifies_funding_coverage", None
        )
        if not callable(verifier) or not verifier(advance):
            raise PaperTradingError("PAPER_FUNDING_COVERAGE_EVIDENCE_UNVERIFIED")
        start = _dt(advance.coverage_start_at)
        end = _dt(advance.coverage_end_at)
        actual: list[tuple[str, str]] = []
        for record in records:
            if record.event_type != "CARRY_ACCRUED":
                continue
            value = record.payload.get("accrual")
            if not isinstance(value, Mapping):
                raise PaperTradingError("PAPER_CARRY_EVENT_INVALID")
            accrual = CarryAccrualV1(**dict(value))
            if (
                accrual.kind != "FUNDING"
                or accrual.status not in {"MODELED", "OBSERVED"}
                or not start <= _dt(accrual.effective_at) <= end
            ):
                continue
            if (
                accrual.status != "OBSERVED"
                or accrual.coverage_status != "PARTIAL"
                or accrual.coverage_start_at != accrual.effective_at
                or accrual.coverage_end_at != accrual.effective_at
                or accrual.settlement_model != model
                or accrual.rate_source_sha256
                != advance.funding_history_source_sha256
                or accrual.price_source_sha256
                != advance.price_proxy_source_sha256
            ):
                raise PaperTradingError(
                    "PAPER_FUNDING_COVERAGE_ACCRUAL_NOT_SCHEDULER_BOUND"
                )
            actual.append(
                (accrual.effective_at, canonical_digest(accrual.to_dict()))
            )
        actual.sort()
        if tuple(actual) != tuple(
            zip(advance.event_effective_ats, advance.event_accrual_sha256s)
        ):
            raise PaperTradingError(
                "PAPER_FUNDING_COVERAGE_LEDGER_BINDING_MISMATCH"
            )
        return {
            "event_id": advance.advance_id,
            "event_type": "FUNDING_COVERAGE_ADVANCED",
            "occurred_at": advance.available_at,
            "payload": {"advance": advance.to_dict()},
        }

    def advance_funding_coverage(
        self,
        *,
        account_id: str,
        expected_account_version: int,
        advance: FundingCoverageAdvanceV1,
    ) -> PaperAccountVersionV1:
        """Record a non-cash COMPLETE window only after every point is booked."""

        records = self._ledger.load_records(account_id)
        state = replay_paper_account(records)
        event = self._prepare_funding_coverage_event(
            records=records,
            state=state,
            advance=advance,
        )
        if event is None:
            return state
        if state.version != expected_account_version:
            raise PaperTradingError("PAPER_ACCOUNT_VERSION_CONFLICT")
        self._ledger.append_many(
            account_id=account_id,
            expected_revision=state.version,
            events=(event,),
        )
        return self.load_account(account_id)

    def settle_funding_window(
        self,
        *,
        account_id: str,
        expected_account_version: int,
        accruals: Sequence[CarryAccrualV1],
        advance: FundingCoverageAdvanceV1,
    ) -> PaperAccountVersionV1:
        """Atomically append every funding point and its COMPLETE proof.

        All evidence, amount, effective-position, coverage, and replay checks run
        against an in-memory projection first.  The ledger then receives one CAS
        batch, so a failed call cannot expose a partially booked window.
        """

        records = self._ledger.load_records(account_id)
        state = replay_paper_account(records)
        prior_advance = next(
            (
                record
                for record in records
                if record.event_id == advance.advance_id
            ),
            None,
        )
        if prior_advance is not None:
            if (
                prior_advance.event_type != "FUNDING_COVERAGE_ADVANCED"
                or prior_advance.payload.get("advance") != advance.to_dict()
            ):
                raise PaperTradingError("PAPER_FUNDING_COVERAGE_ID_CONFLICT")
            expected_points = tuple(
                (item.effective_at, canonical_digest(item.to_dict()))
                for item in accruals
            )
            if expected_points != tuple(
                zip(
                    advance.event_effective_ats,
                    advance.event_accrual_sha256s,
                )
            ):
                raise PaperTradingError(
                    "PAPER_FUNDING_TRANSACTION_BINDING_MISMATCH"
                )
            return state
        if state.version != expected_account_version:
            raise PaperTradingError("PAPER_ACCOUNT_VERSION_CONFLICT")
        if any(
            any(record.event_id == accrual.accrual_id for record in records)
            for accrual in accruals
        ):
            raise PaperTradingError("PAPER_FUNDING_TRANSACTION_PARTIAL")
        expected_points = tuple(
            (item.effective_at, canonical_digest(item.to_dict()))
            for item in accruals
        )
        if expected_points != tuple(
            zip(
                advance.event_effective_ats,
                advance.event_accrual_sha256s,
            )
        ):
            raise PaperTradingError("PAPER_FUNDING_TRANSACTION_BINDING_MISMATCH")

        projected_records = tuple(records)
        projected_state = state
        events: list[Mapping[str, Any]] = []
        for accrual in accruals:
            event = self._prepare_carry_event(
                records=projected_records,
                state=projected_state,
                accrual=accrual,
            )
            if event is None:
                raise PaperTradingError("PAPER_FUNDING_TRANSACTION_PARTIAL")
            events.append(event)
            projected_records = _project_event(
                projected_records,
                account_id=account_id,
                event=event,
            )
            projected_state = replay_paper_account(projected_records)
        coverage_event = self._prepare_funding_coverage_event(
            records=projected_records,
            state=projected_state,
            advance=advance,
        )
        if coverage_event is None:
            raise PaperTradingError("PAPER_FUNDING_TRANSACTION_PARTIAL")
        events.append(coverage_event)
        projected_records = _project_event(
            projected_records,
            account_id=account_id,
            event=coverage_event,
        )
        replay_paper_account(projected_records)

        self._ledger.append_many(
            account_id=account_id,
            expected_revision=state.version,
            events=tuple(events),
        )
        return self.load_account(account_id)

    @staticmethod
    def _pretrade_rejection(
        state: PaperAccountVersionV1, command: PaperCommandV1
    ) -> str | None:
        if not command.reduce_only:
            return None
        position = _position_by_symbol(state.positions, command.symbol)
        held = Decimal(position.quantity)
        requested = Decimal(command.quantity)
        if held == 0:
            return "REDUCE_ONLY_WITHOUT_POSITION"
        if (held > 0 and command.side != "SELL") or (held < 0 and command.side != "BUY"):
            return "REDUCE_ONLY_WRONG_SIDE"
        if requested > abs(held):
            return "REDUCE_ONLY_QUANTITY_EXCEEDS_POSITION"
        return None

    def _cost_model_effective_at(self, order: OrderTruthV1, when: str) -> bool:
        model = self._cost_models[order.cost_model_id]
        return not (
            (model.effective_from is not None and _dt(when) < _dt(model.effective_from))
            or (model.effective_to is not None and _dt(when) >= _dt(model.effective_to))
        )

    def observe(
        self,
        *,
        account_id: str,
        expected_account_version: int,
        market: PaperMarketSliceV1,
    ) -> PaperAccountVersionV1:
        records = self._ledger.load_records(account_id)
        state = replay_paper_account(records)
        if state.version != expected_account_version:
            raise PaperTradingError("PAPER_ACCOUNT_VERSION_CONFLICT")
        if self._market_evidence is None:
            raise PaperTradingError("PAPER_MARKET_EVIDENCE_UNCONFIGURED")
        if not self._market_evidence.verifies_market_slice(market):
            raise PaperTradingError("PAPER_MARKET_EVIDENCE_UNVERIFIED")
        if market.symbol != state.permitted_symbol:
            raise PaperTradingError("PAPER_MARKET_SYMBOL_MISMATCH")
        if _dt(market.available_at) < _dt(state.last_fact_at):
            raise PaperTradingError("PAPER_MARKET_TIME_REGRESSION")
        if state.last_market_observed_at is not None and (
            _dt(market.observed_at) <= _dt(state.last_market_observed_at)
            or _dt(market.available_at) <= _dt(state.last_market_available_at)
        ):
            raise PaperTradingError("PAPER_MARKET_SLICE_NOT_FORWARD")
        open_orders = [
            order
            for order in state.orders
            if order.state in {"OPEN", "PARTIALLY_FILLED"}
        ]
        cursor_payload = {
            "symbol": market.symbol,
            "observed_at": market.observed_at,
            "available_at": market.available_at,
            "source_sha256": market.source_sha256,
            "market": market.to_dict(),
        }
        events: list[Mapping[str, Any]] = [
            {
                "event_id": _event_id("market-observed", cursor_payload),
                "event_type": "MARKET_OBSERVED",
                "occurred_at": market.available_at,
                "payload": cursor_payload,
            }
        ]
        unresolved_ids = self._unordered_protective_conflicts(open_orders, market)
        bracket_by_order = self._brackets_by_order(records)
        bracket_exit_ids = {
            item.command_id
            for bracket in set(bracket_by_order.values())
            for item in (bracket.protective_stop, *bracket.take_profits)
        }
        working = state
        visible_by_side: dict[str, Decimal | None] = {
            "BUY": (
                Decimal(market.available_quantity)
                if market.available_quantity is not None
                else None
            ),
            "SELL": (
                Decimal(market.available_quantity)
                if market.available_quantity is not None
                else None
            ),
        }
        for order in sorted(open_orders, key=lambda item: (item.created_at, item.order_id)):
            order = next(item for item in working.orders if item.order_id == order.order_id)
            if order.state not in {"OPEN", "PARTIALLY_FILLED"}:
                continue
            if order.expires_at is not None and _dt(market.available_at) >= _dt(order.expires_at):
                expired = replace(
                    order,
                    state="EXPIRED",
                    updated_at=market.available_at,
                    resolution_reason="ORDER_EXPIRY_REACHED",
                )
                events.append(self._order_fact("ORDER_EXPIRED", expired, market))
                working = self._with_order(working, expired)
                continue
            if order.order_id in unresolved_ids:
                unresolved = replace(
                    order,
                    state="UNRESOLVED",
                    updated_at=market.available_at,
                    resolution_reason="SAME_BAR_PROTECTIVE_PATH_UNKNOWN",
                )
                events.append(self._order_fact("ORDER_UNRESOLVED", unresolved, market))
                working = self._with_order(working, unresolved)
                continue
            runtime_reduce_reason = self._runtime_reduce_reason(working, order)
            if runtime_reduce_reason is not None:
                unresolved = replace(
                    order,
                    state="UNRESOLVED",
                    updated_at=market.available_at,
                    resolution_reason=runtime_reduce_reason,
                )
                events.append(self._order_fact("ORDER_UNRESOLVED", unresolved, market))
                working = self._with_order(working, unresolved)
                continue
            if not self._cost_model_effective_at(order, market.observed_at):
                unresolved = replace(
                    order,
                    state="UNRESOLVED",
                    updated_at=market.available_at,
                    resolution_reason="COST_MODEL_NOT_EFFECTIVE_AT_FILL",
                )
                events.append(self._order_fact("ORDER_UNRESOLVED", unresolved, market))
                working = self._with_order(working, unresolved)
                continue
            disposition = self._disposition(
                order,
                market,
                visible_quantity=visible_by_side[order.side],
            )
            if disposition is None:
                if (
                    order.time_in_force == "IOC"
                    and _dt(market.observed_at) > _dt(order.created_at)
                ):
                    expired = replace(
                        order,
                        state="EXPIRED",
                        updated_at=market.available_at,
                        resolution_reason="IOC_NOT_FILLED",
                    )
                    events.append(self._order_fact("ORDER_EXPIRED", expired, market))
                    working = self._with_order(working, expired)
                continue
            if isinstance(disposition, str):
                unresolved = replace(
                    order,
                    state="UNRESOLVED",
                    updated_at=market.available_at,
                    resolution_reason=disposition,
                )
                events.append(self._order_fact("ORDER_UNRESOLVED", unresolved, market))
                working = self._with_order(working, unresolved)
                continue
            price, liquidity, maker = disposition
            working, event = self._apply_fill(
                state=working,
                order=next(item for item in working.orders if item.order_id == order.order_id),
                market=market,
                base_price=price,
                available_quantity=liquidity,
                maker=maker,
            )
            if event is None:
                # A GTC limit remains live when the modeled execution price
                # would violate the Agent's limit.  MARKET_OBSERVED is still
                # persisted, so a later strictly-forward slice may fill it.
                continue
            events.append(event)
            if event["event_type"] == "FILL_RECORDED":
                filled_now = Decimal(event["payload"]["fill"]["quantity"])
                if visible_by_side[order.side] is not None:
                    visible_by_side[order.side] -= filled_now
                updated = next(
                    item for item in working.orders if item.order_id == order.order_id
                )
                bracket = bracket_by_order.get(order.order_id)
                if bracket is not None:
                    bracket_events, working = self._after_bracket_fill(
                        state=working,
                        filled_order=updated,
                        bracket=bracket,
                        market=market,
                    )
                    events.extend(bracket_events)
                    updated = next(
                        item for item in working.orders
                        if item.order_id == order.order_id
                    )
                if Decimal(updated.remaining_quantity) > 0:
                    terminal: OrderTruthV1 | None = None
                    event_type: str | None = None
                    if updated.time_in_force == "IOC":
                        terminal = replace(
                            updated,
                            state="EXPIRED",
                            updated_at=market.available_at,
                            resolution_reason="IOC_REMAINDER_CANCELLED",
                        )
                        event_type = "ORDER_EXPIRED"
                    elif updated.command_type in {"MARKET", "REDUCE"}:
                        terminal = replace(
                            updated,
                            state="UNRESOLVED",
                            updated_at=market.available_at,
                            resolution_reason=(
                                "REDUCE_ONLY_REMAINDER_EXCEEDS_POSITION"
                                if updated.reduce_only
                                and self._runtime_reduce_reason(working, updated) is not None
                                else "UNFILLED_REMAINDER_AFTER_FIRST_ELIGIBLE_SLICE"
                            ),
                        )
                        event_type = "ORDER_UNRESOLVED"
                    elif (
                        updated.reduce_only
                        and updated.order_id not in bracket_exit_ids
                        and self._runtime_reduce_reason(working, updated) is not None
                    ):
                        terminal = replace(
                            updated,
                            state="UNRESOLVED",
                            updated_at=market.available_at,
                            resolution_reason="REDUCE_ONLY_REMAINDER_EXCEEDS_POSITION",
                        )
                        event_type = "ORDER_UNRESOLVED"
                    if terminal is not None and event_type is not None:
                        events.append(self._order_fact(event_type, terminal, market))
                        working = self._with_order(working, terminal)
        for bracket in {item for item in bracket_by_order.values()}:
            entry = next(
                item for item in working.orders
                if item.order_id == bracket.entry.command_id
            )
            if (
                entry.state in PAPER_TERMINAL_ORDER_STATES
                and Decimal(entry.filled_quantity) == 0
                and Decimal(
                    _position_by_symbol(working.positions, entry.symbol).quantity
                )
                == 0
            ):
                sibling_events, working = self._cancel_bracket_orders(
                    state=working,
                    bracket=bracket,
                    order_ids={
                        item.command_id
                        for item in (
                            bracket.protective_stop,
                            *bracket.take_profits,
                        )
                    },
                    occurred_at=market.available_at,
                    reason="BRACKET_ENTRY_TERMINAL_WITHOUT_FILL",
                    source_sha256=market.source_sha256,
                )
                events.extend(sibling_events)
        projected: tuple[PaperLedgerRecordV1, ...] = tuple(records)
        for event in events:
            projected = _project_event(
                projected,
                account_id=account_id,
                event=event,
            )
        replay_paper_account(projected)
        self._ledger.append_many(
            account_id=account_id,
            expected_revision=state.version,
            events=tuple(events),
        )
        return self.load_account(account_id)

    @staticmethod
    def _brackets_by_order(
        records: Sequence[PaperLedgerRecordV1],
    ) -> dict[str, PaperBracketV1]:
        result: dict[str, PaperBracketV1] = {}
        for record in records:
            if record.event_type != "COMMAND_ACCEPTED":
                continue
            value = record.payload.get("execution_intent")
            if not isinstance(value, Mapping):
                continue
            intent = PaperExecutionIntentV1.from_dict(value)
            if intent.bracket is None:
                continue
            for command in intent.bracket.commands:
                result[command.command_id] = intent.bracket
        return result

    def _after_bracket_fill(
        self,
        *,
        state: PaperAccountVersionV1,
        filled_order: OrderTruthV1,
        bracket: PaperBracketV1,
        market: PaperMarketSliceV1,
    ) -> tuple[list[Mapping[str, Any]], PaperAccountVersionV1]:
        events: list[Mapping[str, Any]] = []
        working = state
        if filled_order.order_id == bracket.entry.command_id:
            for command in (
                bracket.protective_stop,
                *bracket.take_profits,
            ):
                order = next(
                    item for item in working.orders
                    if item.order_id == command.command_id
                )
                if order.state != "HELD":
                    continue
                activated = replace(
                    order,
                    state="OPEN",
                    updated_at=market.available_at,
                    resolution_reason=None,
                )
                events.append(self._order_fact("ORDER_ACTIVATED", activated, market))
                working = self._with_order(working, activated)
            return events, working

        is_stop = filled_order.order_id == bracket.protective_stop.command_id
        remaining_position = Decimal(
            _position_by_symbol(working.positions, filled_order.symbol).quantity
        )
        cancel_ids = {bracket.entry.command_id}
        if is_stop:
            cancel_ids.update(
                item.command_id for item in bracket.take_profits
            )
        if remaining_position == 0:
            cancel_ids.update(
                item.command_id
                for item in (
                    bracket.protective_stop,
                    *bracket.take_profits,
                )
            )
        sibling_events, working = self._cancel_bracket_orders(
            state=working,
            bracket=bracket,
            order_ids=cancel_ids,
            occurred_at=market.available_at,
            reason=(
                "BRACKET_STOP_OCO"
                if is_stop
                else "BRACKET_EXPOSURE_CLOSED"
            ),
            source_sha256=market.source_sha256,
        )
        events.extend(sibling_events)
        return events, working

    @staticmethod
    def _cancel_bracket_orders(
        *,
        state: PaperAccountVersionV1,
        bracket: PaperBracketV1,
        order_ids: set[str],
        occurred_at: str,
        reason: str,
        source_sha256: str | None = None,
    ) -> tuple[list[Mapping[str, Any]], PaperAccountVersionV1]:
        events: list[Mapping[str, Any]] = []
        working = state
        known_ids = {item.command_id for item in bracket.commands}
        if not order_ids.issubset(known_ids):
            raise PaperTradingError("PAPER_BRACKET_CANCEL_SCOPE_INVALID")
        for order_id in sorted(order_ids):
            order = next(item for item in working.orders if item.order_id == order_id)
            if order.state in PAPER_TERMINAL_ORDER_STATES:
                continue
            cancelled = replace(
                order,
                state="CANCELLED",
                updated_at=occurred_at,
                resolution_reason=reason,
            )
            payload: dict[str, Any] = {"order": cancelled.to_dict()}
            if source_sha256 is not None:
                payload["source_sha256"] = source_sha256
            events.append(
                {
                    "event_id": _event_id("order-cancelled", payload),
                    "event_type": "ORDER_CANCELLED",
                    "occurred_at": occurred_at,
                    "payload": payload,
                }
            )
            working = PaperTradingService._with_order(working, cancelled)
        return events, working

    @staticmethod
    def _runtime_reduce_reason(
        state: PaperAccountVersionV1, order: OrderTruthV1
    ) -> str | None:
        if not order.reduce_only:
            return None
        held = Decimal(_position_by_symbol(state.positions, order.symbol).quantity)
        if held == 0:
            return "REDUCE_ONLY_NO_REMAINING_POSITION"
        if (held > 0 and order.side != "SELL") or (held < 0 and order.side != "BUY"):
            return "REDUCE_ONLY_POSITION_DIRECTION_CHANGED"
        return None

    @staticmethod
    def _with_order(
        state: PaperAccountVersionV1, order: OrderTruthV1
    ) -> PaperAccountVersionV1:
        orders = {item.order_id: item for item in state.orders}
        orders[order.order_id] = order
        return replace(state, orders=tuple(sorted(orders.values(), key=lambda item: item.order_id)))

    @staticmethod
    def _order_fact(
        event_type: str, order: OrderTruthV1, market: PaperMarketSliceV1
    ) -> Mapping[str, Any]:
        payload = {"order": order.to_dict(), "source_sha256": market.source_sha256}
        return {
            "event_id": _event_id(event_type.lower().replace("_", "-"), payload),
            "event_type": event_type,
            "occurred_at": market.available_at,
            "payload": payload,
        }

    @staticmethod
    def _unordered_protective_conflicts(
        orders: Sequence[OrderTruthV1], market: PaperMarketSliceV1
    ) -> set[str]:
        if market.granularity != "BAR" or market.path_status != "UNORDERED":
            return set()
        protective = [
            order
            for order in orders
            if order.command_type in {"STOP_LOSS", "TAKE_PROFIT"}
            and order.trigger_price is not None
        ]
        result: set[str] = set()
        for side in ("BUY", "SELL"):
            same_side = [order for order in protective if order.side == side]
            stop_touched = [
                order
                for order in same_side
                if order.command_type == "STOP_LOSS"
                and (
                    (side == "SELL" and Decimal(market.low) <= Decimal(order.trigger_price))
                    or (side == "BUY" and Decimal(market.high) >= Decimal(order.trigger_price))
                )
            ]
            target_touched = [
                order
                for order in same_side
                if order.command_type == "TAKE_PROFIT"
                and (
                    (side == "SELL" and Decimal(market.high) >= Decimal(order.trigger_price))
                    or (side == "BUY" and Decimal(market.low) <= Decimal(order.trigger_price))
                )
            ]
            if stop_touched and target_touched:
                result.update(order.order_id for order in stop_touched + target_touched)
        return result

    @staticmethod
    def _disposition(
        order: OrderTruthV1,
        market: PaperMarketSliceV1,
        *,
        visible_quantity: Decimal | None,
    ) -> tuple[Decimal, Decimal, bool] | str | None:
        if _dt(market.observed_at) <= _dt(order.created_at):
            return None
        remaining = Decimal(order.remaining_quantity)
        liquidity = visible_quantity
        if order.command_type in {"MARKET", "REDUCE"}:
            quote = market.ask if order.side == "BUY" else market.bid
            if quote is None or liquidity is None:
                return "NO_EXECUTABLE_QUOTE_OR_SIZE"
            if liquidity <= 0:
                return "VISIBLE_LIQUIDITY_EXHAUSTED"
            return Decimal(quote), min(remaining, liquidity), False
        if order.command_type in {"LIMIT", "LIMIT_REDUCE"}:
            limit = Decimal(order.limit_price)
            quote = market.ask if order.side == "BUY" else market.bid
            crossed = quote is not None and (
                (order.side == "BUY" and Decimal(quote) <= limit)
                or (order.side == "SELL" and Decimal(quote) >= limit)
            )
            if crossed:
                if liquidity is None:
                    return "LIMIT_CROSSED_WITHOUT_OBSERVABLE_SIZE"
                if liquidity <= 0:
                    return None
                execution = min(Decimal(quote), limit) if order.side == "BUY" else max(Decimal(quote), limit)
                # A crossed quote proves executable liquidity, not passive
                # queue priority.  Without venue fill evidence, charge taker
                # costs conservatively.
                return execution, min(remaining, liquidity), False
            if market.granularity == "BAR" and (
                (order.side == "BUY" and Decimal(market.low) <= limit)
                or (order.side == "SELL" and Decimal(market.high) >= limit)
            ):
                return "COARSE_BAR_LIMIT_PATH_UNKNOWN"
            return None
        trigger = Decimal(order.trigger_price)
        quote = market.bid if order.side == "SELL" else market.ask
        observed = Decimal(quote) if quote is not None else (Decimal(market.last) if market.last is not None else None)
        if order.command_type == "STOP_LOSS":
            triggered = observed is not None and (
                (order.side == "SELL" and observed <= trigger)
                or (order.side == "BUY" and observed >= trigger)
            )
        else:
            triggered = observed is not None and (
                (order.side == "SELL" and observed >= trigger)
                or (order.side == "BUY" and observed <= trigger)
            )
        if triggered:
            if quote is None or liquidity is None:
                return "PROTECTIVE_TRIGGER_WITHOUT_EXECUTABLE_QUOTE_OR_SIZE"
            if liquidity <= 0:
                return "VISIBLE_LIQUIDITY_EXHAUSTED"
            return Decimal(quote), min(remaining, liquidity), False
        if market.granularity == "BAR":
            touched = (
                order.command_type == "STOP_LOSS"
                and ((order.side == "SELL" and Decimal(market.low) <= trigger) or (order.side == "BUY" and Decimal(market.high) >= trigger))
            ) or (
                order.command_type == "TAKE_PROFIT"
                and ((order.side == "SELL" and Decimal(market.high) >= trigger) or (order.side == "BUY" and Decimal(market.low) <= trigger))
            )
            if touched:
                return "COARSE_BAR_PROTECTIVE_PATH_UNKNOWN"
        return None

    def _apply_fill(
        self,
        *,
        state: PaperAccountVersionV1,
        order: OrderTruthV1,
        market: PaperMarketSliceV1,
        base_price: Decimal,
        available_quantity: Decimal,
        maker: bool,
    ) -> tuple[PaperAccountVersionV1, Mapping[str, Any] | None]:
        if available_quantity <= 0:
            raise PaperTradingError("PAPER_OBSERVED_LIQUIDITY_NONPOSITIVE")
        model = self._cost_models[order.cost_model_id]
        if order.cost_model_digest != model.model_digest:
            raise PaperTradingError("PAPER_COST_MODEL_DIGEST_MISMATCH")
        quantity = min(Decimal(order.remaining_quantity), available_quantity)
        if order.reduce_only:
            held = Decimal(_position_by_symbol(state.positions, order.symbol).quantity)
            if held == 0 or (held > 0 and order.side != "SELL") or (
                held < 0 and order.side != "BUY"
            ):
                unresolved = replace(
                    order,
                    state="UNRESOLVED",
                    updated_at=market.available_at,
                    resolution_reason="REDUCE_ONLY_NO_REMAINING_POSITION",
                )
                return self._with_order(state, unresolved), self._order_fact(
                    "ORDER_UNRESOLVED", unresolved, market
                )
            quantity = min(quantity, abs(held))
        impact_rate = Decimal(model.market_impact_bps) / Decimal("10000")
        impact_per_unit = Decimal("0") if maker else base_price * impact_rate
        execution_price = base_price + impact_per_unit if order.side == "BUY" else base_price - impact_per_unit
        if order.command_type in {"LIMIT", "LIMIT_REDUCE"}:
            limit = Decimal(order.limit_price)
            if (order.side == "BUY" and execution_price > limit) or (
                order.side == "SELL" and execution_price < limit
            ):
                if order.time_in_force == "IOC":
                    expired = replace(
                        order,
                        state="EXPIRED",
                        updated_at=market.available_at,
                        resolution_reason="IOC_NOT_FILLED",
                    )
                    return self._with_order(state, expired), self._order_fact(
                        "ORDER_EXPIRED", expired, market
                    )
                return state, None
        fee_rate = Decimal(model.maker_fee_bps if maker else model.taker_fee_bps) / Decimal("10000")
        multiplier = Decimal(state.instrument_spec.contract_multiplier)
        notional = execution_price * quantity * multiplier
        fee = notional * fee_rate
        spread_cost = Decimal("0")
        execution_mid: Decimal | None = None
        if market.bid is not None and market.ask is not None and not maker:
            execution_mid = (Decimal(market.ask) + Decimal(market.bid)) / Decimal("2")
            spread_cost = (
                (Decimal(market.ask) - Decimal(market.bid))
                * quantity
                * multiplier
                / Decimal("2")
            )
        impact_cost = impact_per_unit * quantity * multiplier
        prior_position = _position_by_symbol(state.positions, order.symbol)
        position, fill_realized = self._position_after(
            prior=prior_position,
            side=order.side,
            quantity=quantity,
            price=execution_price,
            reduce_only=order.reduce_only,
            account_mode=state.account_mode,
            max_leverage=Decimal(state.max_leverage),
            contract_multiplier=multiplier,
        )
        resultant_position_notional = (
            execution_price * abs(Decimal(position.quantity)) * multiplier
        )
        if (
            self._max_position_notional is not None
            and resultant_position_notional > self._max_position_notional
        ):
            unresolved = replace(
                order,
                state="UNRESOLVED",
                updated_at=market.available_at,
                resolution_reason="MAX_POSITION_NOTIONAL_EXCEEDED_AT_FILL",
            )
            return self._with_order(state, unresolved), self._order_fact(
                "ORDER_UNRESOLVED", unresolved, market
            )
        account_realized = Decimal(state.realized_pnl) + fill_realized
        fees_paid = Decimal(state.fees_paid) + fee
        if state.account_mode == "LINEAR_PERP":
            cash = Decimal(state.cash_balance) + fill_realized - fee
        elif order.side == "BUY":
            cash = Decimal(state.cash_balance) - notional - fee
            if cash < 0:
                unresolved = replace(
                    order,
                    state="UNRESOLVED",
                    updated_at=market.available_at,
                    resolution_reason="CASH_SPOT_BALANCE_INSUFFICIENT_AT_FILL",
                )
                return self._with_order(state, unresolved), self._order_fact("ORDER_UNRESOLVED", unresolved, market)
        else:
            cash = Decimal(state.cash_balance) + notional - fee
        reserved_margin = sum(
            (
                Decimal(item.margin_allocated)
                for item in state.positions
                if item.symbol != position.symbol
            ),
            Decimal("0"),
        ) + Decimal(position.margin_allocated)
        if cash - reserved_margin < 0 and not order.reduce_only:
            unresolved = replace(
                order,
                state="UNRESOLVED",
                updated_at=market.available_at,
                resolution_reason="AVAILABLE_COLLATERAL_INSUFFICIENT_AT_FILL",
            )
            return self._with_order(state, unresolved), self._order_fact("ORDER_UNRESOLVED", unresolved, market)
        filled = Decimal(order.filled_quantity) + quantity
        remaining = Decimal(order.original_quantity) - filled
        updated_order = replace(
            order,
            filled_quantity=_d(filled),
            remaining_quantity=_d(remaining),
            state="FILLED" if remaining == 0 else "PARTIALLY_FILLED",
            updated_at=market.available_at,
            resolution_reason=None,
        )
        fill_payload = {
            "order_id": order.order_id,
            "source_sha256": market.source_sha256,
            "observed_at": market.observed_at,
            "available_at": market.available_at,
            "instrument_spec_id": state.instrument_spec.instrument_spec_id,
            "quantity": _d(quantity),
            "price": _d(execution_price),
        }
        fill = FillEventV1(
            fill_id=_event_id("fill", fill_payload),
            order_id=order.order_id,
            command_id=order.command_id,
            account_id=order.account_id,
            symbol=order.symbol,
            side=order.side,
            quantity=_d(quantity),
            price=_d(execution_price),
            fee=_d(fee),
            spread_cost=_d(spread_cost),
            impact_cost=_d(impact_cost),
            funding_cost=None,
            funding_cost_status=(
                "UNKNOWN" if state.account_mode == "LINEAR_PERP" else "NOT_APPLICABLE"
            ),
            borrow_cost=None,
            borrow_cost_status="NOT_APPLICABLE",
            realized_pnl=_d(fill_realized),
            observed_at=market.observed_at,
            source_sha256=market.source_sha256,
            cost_model_id=model.model_id,
            instrument_spec_id=state.instrument_spec.instrument_spec_id,
            quantity_basis=state.instrument_spec.quantity_basis,
            contract_multiplier=state.instrument_spec.contract_multiplier,
            notional=_d(notional),
            execution_status="PAPER_MODELED_ARITHMETIC",
            cost_model_digest=model.model_digest,
            execution_mid_price=None if execution_mid is None else _d(execution_mid),
            touch_price=_d(base_price),
            fee_status="MODELED",
            spread_cost_status="MODELED",
            impact_cost_status="MODELED",
        )
        positions = {item.symbol: item for item in state.positions}
        positions[position.symbol] = position
        orders = {item.order_id: item for item in state.orders}
        orders[updated_order.order_id] = updated_order
        next_state = replace(
            state,
            cash_balance=_d(cash),
            realized_pnl=_d(account_realized),
            fees_paid=_d(fees_paid),
            funding_paid=state.funding_paid,
            borrow_paid=state.borrow_paid,
            carry_coverage_status=state.carry_coverage_status,
            reserved_margin=_d(reserved_margin),
            positions=tuple(sorted(positions.values(), key=lambda item: item.symbol)),
            orders=tuple(sorted(orders.values(), key=lambda item: item.order_id)),
        )
        payload = {
            "fill": fill.to_dict(),
            "order": updated_order.to_dict(),
            "position": position.to_dict(),
            "cash_balance": next_state.cash_balance,
            "account_realized_pnl": next_state.realized_pnl,
            "fees_paid": next_state.fees_paid,
            "reserved_margin": next_state.reserved_margin,
        }
        return next_state, {
            "event_id": fill.fill_id,
            "event_type": "FILL_RECORDED",
            "occurred_at": market.available_at,
            "payload": payload,
        }

    @staticmethod
    def _position_after(
        *,
        prior: PaperPositionV1,
        side: str,
        quantity: Decimal,
        price: Decimal,
        reduce_only: bool,
        account_mode: str,
        max_leverage: Decimal,
        contract_multiplier: Decimal,
    ) -> tuple[PaperPositionV1, Decimal]:
        old_quantity = Decimal(prior.quantity)
        old_average = Decimal(prior.average_entry_price)
        delta = quantity if side == "BUY" else -quantity
        new_quantity = old_quantity + delta
        if reduce_only and (
            old_quantity == 0
            or old_quantity * delta >= 0
            or abs(new_quantity) > abs(old_quantity)
            or old_quantity * new_quantity < 0
        ):
            raise PaperTradingError("PAPER_REDUCE_ONLY_FILL_WOULD_INCREASE_RISK")
        if account_mode == "CASH_SPOT" and new_quantity < 0:
            raise PaperTradingError("PAPER_CASH_SPOT_SHORT_FORBIDDEN")
        realized = Decimal("0")
        if old_quantity == 0 or old_quantity * delta > 0:
            total = abs(old_quantity) + abs(delta)
            average = (
                (abs(old_quantity) * old_average + abs(delta) * price) / total
                if total
                else Decimal("0")
            )
        else:
            closed = min(abs(old_quantity), abs(delta))
            realized = (
                (price - old_average) * closed * contract_multiplier
                if old_quantity > 0
                else (old_average - price) * closed * contract_multiplier
            )
            if new_quantity == 0:
                average = Decimal("0")
            elif old_quantity * new_quantity > 0:
                average = old_average
            else:
                average = price
        return (
            PaperPositionV1(
                symbol=prior.symbol,
                quantity=_d(new_quantity),
                average_entry_price=_d(average),
                margin_allocated=(
                    _d(
                        abs(new_quantity)
                        * average
                        * contract_multiplier
                        / max_leverage
                    )
                    if account_mode == "LINEAR_PERP"
                    else "0"
                ),
                realized_pnl=_d(Decimal(prior.realized_pnl) + realized),
            ),
            realized,
        )
