"""Frozen long-only E0 portfolio and strategic-state reducer.

This module is intentionally narrower than the production-facing V2 domains.
It exists only for the frozen TA2 formal E0 counterfactual experiment.  Model
prose never mutates state: the only admitted mutation is an exact, pre-
registered ``action_id`` passed through this deterministic reducer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_digest,
    self_digest,
    verify_self_digest,
)


ZERO = Decimal("0")
ONE = Decimal("1")

ACTION_WAIT_FLAT = "WAIT_FLAT"
ACTION_WAIT_REENTRY = "WAIT_REENTRY"
ACTION_HOLD = "HOLD_STATE"
ACTION_OPEN_CORE = "OPEN_CORE_6_25"
ACTION_REENTER_CORE = "REENTER_CORE_6_25"
ACTION_ADD_STAGE = "ADD_STAGE_3_125"
ACTION_TRIM_STAGE = "TRIM_STAGE_3_125"
ACTION_EXIT_REENTRY = "EXIT_ALL_OPEN_REENTRY"
ACTION_INVALIDATE_EXIT = "INVALIDATE_THESIS_AND_EXIT"
ACTION_INVALIDATE_FLAT = "INVALIDATE_THESIS_STAY_FLAT"

ALL_ACTION_IDS = (
    ACTION_WAIT_FLAT,
    ACTION_WAIT_REENTRY,
    ACTION_HOLD,
    ACTION_OPEN_CORE,
    ACTION_REENTER_CORE,
    ACTION_ADD_STAGE,
    ACTION_TRIM_STAGE,
    ACTION_EXIT_REENTRY,
    ACTION_INVALIDATE_EXIT,
    ACTION_INVALIDATE_FLAT,
)


class FormalE0ReplayError(ValueError):
    """A fail-closed frozen replay contract violation."""


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = Decimal(value)
        except Exception as exc:  # pragma: no cover - defensive
            raise FormalE0ReplayError(code) from exc
    else:
        raise FormalE0ReplayError(code)
    if not parsed.is_finite():
        raise FormalE0ReplayError(code)
    return parsed


@dataclass(frozen=True, slots=True)
class FrozenAccountPolicy:
    initial_equity: Decimal
    core_fraction: Decimal
    stage_fraction: Decimal
    max_gross_fraction: Decimal
    hard_stop_fraction: Decimal
    taker_fee_rate: Decimal
    adverse_slippage_rate: Decimal

    def __post_init__(self) -> None:
        values = (
            self.initial_equity,
            self.core_fraction,
            self.stage_fraction,
            self.max_gross_fraction,
            self.hard_stop_fraction,
            self.taker_fee_rate,
            self.adverse_slippage_rate,
        )
        if (
            any(not isinstance(value, Decimal) or not value.is_finite() for value in values)
            or self.initial_equity <= ZERO
            or self.core_fraction != Decimal("0.0625")
            or self.stage_fraction != Decimal("0.03125")
            or self.max_gross_fraction != Decimal("0.125")
            or self.hard_stop_fraction != Decimal("0.10")
            or self.taker_fee_rate != Decimal("0.0005")
            or self.adverse_slippage_rate != Decimal("0.0002")
        ):
            raise FormalE0ReplayError("FORMAL_E0_ACCOUNT_POLICY_MISMATCH")


@dataclass(frozen=True, slots=True)
class StrategicEpisodeState:
    episode_id: str
    cohort: str
    revision: int
    prior_accepted_head: str
    thesis_status: str
    position_state: str
    reentry_status: str
    nominal_core_fraction: Decimal
    nominal_stage_fraction: Decimal
    quantity: Decimal
    average_entry: Decimal | None
    hard_stop: Decimal | None
    realized_pnl_before_cost: Decimal
    fee_cost: Decimal
    slippage_cost: Decimal
    equity_peak: Decimal
    max_drawdown_fraction: Decimal
    last_mark: Decimal
    last_sample_index: int | None

    def __post_init__(self) -> None:
        decimals = (
            self.nominal_core_fraction,
            self.nominal_stage_fraction,
            self.quantity,
            self.realized_pnl_before_cost,
            self.fee_cost,
            self.slippage_cost,
            self.equity_peak,
            self.max_drawdown_fraction,
            self.last_mark,
        )
        if (
            not self.episode_id
            or self.cohort
            not in {
                "TOPOLOGY_SELECTION",
                "POLICY_QUALIFICATION",
                "FORMAL_EXPERIMENT",
            }
            or type(self.revision) is not int
            or self.revision < 0
            or len(self.prior_accepted_head) != 64
            or self.thesis_status not in {"ACTIVE", "INVALIDATED"}
            or self.position_state
            not in {"FLAT", "CORE_LONG", "CORE_PLUS_STAGE"}
            or self.reentry_status not in {"NONE", "OPEN", "FULFILLED"}
            or any(not isinstance(value, Decimal) or not value.is_finite() for value in decimals)
            or self.nominal_core_fraction < ZERO
            or self.nominal_stage_fraction < ZERO
            or self.quantity < ZERO
            or self.fee_cost < ZERO
            or self.slippage_cost < ZERO
            or self.equity_peak <= ZERO
            or not (ZERO <= self.max_drawdown_fraction <= ONE)
            or self.last_mark <= ZERO
            or (
                self.last_sample_index is not None
                and (
                    type(self.last_sample_index) is not int
                    or self.last_sample_index < 0
                )
            )
        ):
            raise FormalE0ReplayError("STRATEGIC_EPISODE_STATE_INVALID")
        if self.quantity == ZERO:
            if (
                self.position_state != "FLAT"
                or self.average_entry is not None
                or self.hard_stop is not None
                or self.nominal_core_fraction != ZERO
                or self.nominal_stage_fraction != ZERO
            ):
                raise FormalE0ReplayError("FLAT_STATE_POSITION_FIELDS_INVALID")
        else:
            if (
                self.position_state == "FLAT"
                or self.average_entry is None
                or self.hard_stop is None
                or self.average_entry <= ZERO
                or self.hard_stop <= ZERO
                or self.hard_stop >= self.average_entry
                or self.nominal_core_fraction <= ZERO
            ):
                raise FormalE0ReplayError("LONG_STATE_POSITION_FIELDS_INVALID")
        if self.thesis_status == "INVALIDATED" and (
            self.quantity != ZERO or self.reentry_status == "OPEN"
        ):
            raise FormalE0ReplayError("INVALIDATED_THESIS_CANNOT_HOLD_OR_REENTER")

    @property
    def nominal_gross_fraction(self) -> Decimal:
        return self.nominal_core_fraction + self.nominal_stage_fraction

    def mark_equity(
        self,
        *,
        mark: Decimal,
        account: FrozenAccountPolicy,
    ) -> Decimal:
        mark = _decimal(mark, "MARK_INVALID")
        unrealized = (
            ZERO
            if self.quantity == ZERO or self.average_entry is None
            else (mark - self.average_entry) * self.quantity
        )
        return (
            account.initial_equity
            + self.realized_pnl_before_cost
            + unrealized
            - self.fee_cost
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_id": "formal_e0_strategic_episode_state",
            "schema_version": "1.0.0",
            "episode_id": self.episode_id,
            "cohort": self.cohort,
            "revision": self.revision,
            "prior_accepted_head": self.prior_accepted_head,
            "thesis_status": self.thesis_status,
            "position_state": self.position_state,
            "reentry_status": self.reentry_status,
            "nominal_core_fraction": self.nominal_core_fraction,
            "nominal_stage_fraction": self.nominal_stage_fraction,
            "nominal_gross_fraction": self.nominal_gross_fraction,
            "quantity": self.quantity,
            "average_entry": self.average_entry,
            "hard_stop": self.hard_stop,
            "realized_pnl_before_cost": self.realized_pnl_before_cost,
            "fee_cost": self.fee_cost,
            "slippage_cost": self.slippage_cost,
            "equity_peak": self.equity_peak,
            "max_drawdown_fraction": self.max_drawdown_fraction,
            "last_mark": self.last_mark,
            "last_sample_index": self.last_sample_index,
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        }

    def document(self) -> dict[str, Any]:
        return self_digest(self.payload(), "state_digest")

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> "StrategicEpisodeState":
        verify_self_digest(value, "state_digest")
        if (
            value.get("schema_id") != "formal_e0_strategic_episode_state"
            or value.get("schema_version") != "1.0.0"
            or value.get("system_mode") != "E0_OFFLINE_COUNTERFACTUAL"
            or value.get("external_execution_authority") != "NONE_E0"
            or value.get("executable") is not False
        ):
            raise FormalE0ReplayError("STRATEGIC_EPISODE_STATE_DOCUMENT_INVALID")
        return cls(
            episode_id=str(value["episode_id"]),
            cohort=str(value["cohort"]),
            revision=int(value["revision"]),
            prior_accepted_head=str(value["prior_accepted_head"]),
            thesis_status=str(value["thesis_status"]),
            position_state=str(value["position_state"]),
            reentry_status=str(value["reentry_status"]),
            nominal_core_fraction=_decimal(
                value["nominal_core_fraction"], "STATE_DECIMAL_INVALID"
            ),
            nominal_stage_fraction=_decimal(
                value["nominal_stage_fraction"], "STATE_DECIMAL_INVALID"
            ),
            quantity=_decimal(value["quantity"], "STATE_DECIMAL_INVALID"),
            average_entry=(
                None
                if value["average_entry"] is None
                else _decimal(value["average_entry"], "STATE_DECIMAL_INVALID")
            ),
            hard_stop=(
                None
                if value["hard_stop"] is None
                else _decimal(value["hard_stop"], "STATE_DECIMAL_INVALID")
            ),
            realized_pnl_before_cost=_decimal(
                value["realized_pnl_before_cost"], "STATE_DECIMAL_INVALID"
            ),
            fee_cost=_decimal(value["fee_cost"], "STATE_DECIMAL_INVALID"),
            slippage_cost=_decimal(
                value["slippage_cost"], "STATE_DECIMAL_INVALID"
            ),
            equity_peak=_decimal(
                value["equity_peak"], "STATE_DECIMAL_INVALID"
            ),
            max_drawdown_fraction=_decimal(
                value["max_drawdown_fraction"], "STATE_DECIMAL_INVALID"
            ),
            last_mark=_decimal(value["last_mark"], "STATE_DECIMAL_INVALID"),
            last_sample_index=(
                None
                if value["last_sample_index"] is None
                else int(value["last_sample_index"])
            ),
        )


@dataclass(frozen=True, slots=True)
class ActionPreview:
    requested_action_id: str | None
    admitted_action_id: str | None
    feasible_action_ids: tuple[str, ...]
    action_exactly_feasible: bool
    risk_budget_valid: bool
    reentry_symmetry_valid: bool
    projected_marked_gross_fraction: Decimal
    projected_open_risk_fraction: Decimal
    error_codes: tuple[str, ...]

    @property
    def admitted(self) -> bool:
        return (
            self.action_exactly_feasible
            and self.risk_budget_valid
            and self.reentry_symmetry_valid
            and not self.error_codes
        )

    def payload(self) -> dict[str, Any]:
        return {
            "requested_action_id": self.requested_action_id,
            "admitted_action_id": self.admitted_action_id,
            "feasible_action_ids": self.feasible_action_ids,
            "action_exactly_feasible": self.action_exactly_feasible,
            "risk_budget_valid": self.risk_budget_valid,
            "reentry_symmetry_valid": self.reentry_symmetry_valid,
            "projected_marked_gross_fraction": (
                self.projected_marked_gross_fraction
            ),
            "projected_open_risk_fraction": (
                self.projected_open_risk_fraction
            ),
            "error_codes": self.error_codes,
        }


@dataclass(frozen=True, slots=True)
class ReplayTransition:
    state_before: StrategicEpisodeState
    state_after: StrategicEpisodeState
    preview: ActionPreview
    requested_action_id: str | None
    executed_action_id: str
    control_mode: str
    fills: tuple[Mapping[str, Any], ...]
    forced_events: tuple[str, ...]
    equity_before: Decimal
    equity_after: Decimal
    net_pnl_after_cost_fraction: Decimal
    transaction_cost_fraction: Decimal
    max_drawdown_fraction: Decimal
    primary_path_capture: Decimal
    transition_head_digest: str

    def receipt(self) -> dict[str, Any]:
        value = {
            "schema_id": "formal_e0_state_transition_receipt",
            "schema_version": "1.0.0",
            "state_before": self.state_before.document(),
            "state_after": self.state_after.document(),
            "governance_preview": self.preview.payload(),
            "requested_action_id": self.requested_action_id,
            "executed_action_id": self.executed_action_id,
            "control_mode": self.control_mode,
            "fills": list(self.fills),
            "forced_events": self.forced_events,
            "portfolio": {
                "equity_before": self.equity_before,
                "equity_after": self.equity_after,
                "net_pnl_after_cost_fraction": (
                    self.net_pnl_after_cost_fraction
                ),
                "transaction_cost_fraction": (
                    self.transaction_cost_fraction
                ),
                "max_drawdown_fraction": self.max_drawdown_fraction,
                "primary_path_capture": self.primary_path_capture,
                "funding": None,
                "funding_status": "UNKNOWN_EXCLUDED",
            },
            "transition_head_digest": self.transition_head_digest,
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        }
        return self_digest(value, "receipt_digest")


def initial_episode_state(
    *,
    cohort: str,
    first_mark: Decimal,
    account: FrozenAccountPolicy,
    episode_id: str,
) -> StrategicEpisodeState:
    first_mark = _decimal(first_mark, "INITIAL_MARK_INVALID")
    genesis = canonical_digest(
        {
            "schema_id": "formal_e0_episode_genesis",
            "schema_version": "1.0.0",
            "episode_id": episode_id,
            "cohort": cohort,
            "initial_equity": account.initial_equity,
            "first_mark": first_mark,
            "state_isolation": "NO_CROSS_COHORT_INHERITANCE",
        }
    )
    return StrategicEpisodeState(
        episode_id=episode_id,
        cohort=cohort,
        revision=0,
        prior_accepted_head=genesis,
        thesis_status="ACTIVE",
        position_state="FLAT",
        reentry_status="NONE",
        nominal_core_fraction=ZERO,
        nominal_stage_fraction=ZERO,
        quantity=ZERO,
        average_entry=None,
        hard_stop=None,
        realized_pnl_before_cost=ZERO,
        fee_cost=ZERO,
        slippage_cost=ZERO,
        equity_peak=account.initial_equity,
        max_drawdown_fraction=ZERO,
        last_mark=first_mark,
        last_sample_index=None,
    )


def _action_document(action_id: str) -> dict[str, Any]:
    descriptions = {
        ACTION_WAIT_FLAT: (
            "Remain flat while an active thesis has no reentry obligation."
        ),
        ACTION_WAIT_REENTRY: (
            "Remain flat for one review while preserving the open reentry obligation."
        ),
        ACTION_HOLD: "Keep the currently admitted long exposure unchanged.",
        ACTION_OPEN_CORE: "Open one 6.25 percent CORE long allocation.",
        ACTION_REENTER_CORE: (
            "Fulfil an open reentry contract with one 6.25 percent CORE long allocation."
        ),
        ACTION_ADD_STAGE: "Add one 3.125 percent tactical trend stage.",
        ACTION_TRIM_STAGE: "Remove one 3.125 percent tactical stage.",
        ACTION_EXIT_REENTRY: (
            "Exit all long exposure while the thesis survives and atomically open reentry."
        ),
        ACTION_INVALIDATE_EXIT: (
            "Invalidate the thesis and exit all long exposure without reentry."
        ),
        ACTION_INVALIDATE_FLAT: (
            "Invalidate the thesis while already flat and close any reentry obligation."
        ),
    }
    return {
        "action_id": action_id,
        "description": descriptions[action_id],
        "long_only": True,
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }


def feasible_action_documents(
    state: StrategicEpisodeState,
    *,
    current_mark: Decimal,
    account: FrozenAccountPolicy,
) -> tuple[dict[str, Any], ...]:
    current_mark = _decimal(current_mark, "MARK_INVALID")
    if state.thesis_status == "INVALIDATED":
        return (_action_document(ACTION_WAIT_FLAT),)
    if state.quantity == ZERO:
        if state.reentry_status == "OPEN":
            action_ids = (
                ACTION_WAIT_REENTRY,
                ACTION_REENTER_CORE,
                ACTION_INVALIDATE_FLAT,
            )
        else:
            action_ids = (
                ACTION_WAIT_FLAT,
                ACTION_OPEN_CORE,
                ACTION_INVALIDATE_FLAT,
            )
        return tuple(_action_document(item) for item in action_ids)

    marked_gross = state.quantity * current_mark / account.initial_equity
    if marked_gross > account.max_gross_fraction:
        action_ids = [
            ACTION_EXIT_REENTRY,
            ACTION_INVALIDATE_EXIT,
        ]
        if state.nominal_stage_fraction >= account.stage_fraction:
            action_ids.insert(0, ACTION_TRIM_STAGE)
        return tuple(_action_document(item) for item in action_ids)

    action_ids: list[str] = [
        ACTION_HOLD,
        ACTION_EXIT_REENTRY,
        ACTION_INVALIDATE_EXIT,
    ]
    if (
        marked_gross + account.stage_fraction
        <= account.max_gross_fraction
        and state.nominal_gross_fraction + account.stage_fraction
        <= account.max_gross_fraction
    ):
        action_ids.insert(1, ACTION_ADD_STAGE)
    if state.nominal_stage_fraction >= account.stage_fraction:
        action_ids.insert(2, ACTION_TRIM_STAGE)
    return tuple(_action_document(item) for item in action_ids)


def preview_action(
    state: StrategicEpisodeState,
    *,
    selected_action_id: str | None,
    current_mark: Decimal,
    account: FrozenAccountPolicy,
) -> ActionPreview:
    current_mark = _decimal(current_mark, "MARK_INVALID")
    feasible = feasible_action_documents(
        state, current_mark=current_mark, account=account
    )
    feasible_ids = tuple(item["action_id"] for item in feasible)
    exact = (
        isinstance(selected_action_id, str)
        and selected_action_id in feasible_ids
    )
    errors: list[str] = []
    if not exact:
        errors.append("SELECTED_ACTION_NOT_EXACT_FEASIBLE_ID")
    marked_gross = (
        state.quantity * current_mark / account.initial_equity
        if state.quantity > ZERO
        else ZERO
    )
    projected = marked_gross
    if exact and selected_action_id in {ACTION_OPEN_CORE, ACTION_REENTER_CORE}:
        projected = account.core_fraction
    elif exact and selected_action_id == ACTION_ADD_STAGE:
        projected = marked_gross + account.stage_fraction
    elif exact and selected_action_id == ACTION_TRIM_STAGE:
        projected = max(ZERO, marked_gross - account.stage_fraction)
    elif exact and selected_action_id in {
        ACTION_EXIT_REENTRY,
        ACTION_INVALIDATE_EXIT,
        ACTION_INVALIDATE_FLAT,
    }:
        projected = ZERO
    projected_risk = projected * account.hard_stop_fraction
    risk_valid = (
        projected <= account.max_gross_fraction
        and projected_risk
        <= account.max_gross_fraction * account.hard_stop_fraction
    )
    if not risk_valid:
        errors.append("PROJECTED_RISK_BUDGET_EXCEEDED")
    reentry_valid = not (
        exact
        and selected_action_id == ACTION_EXIT_REENTRY
        and state.thesis_status != "ACTIVE"
    )
    if not reentry_valid:
        errors.append("SURVIVING_THESIS_EXIT_REENTRY_INVALID")
    return ActionPreview(
        requested_action_id=selected_action_id,
        admitted_action_id=selected_action_id if exact else None,
        feasible_action_ids=feasible_ids,
        action_exactly_feasible=exact,
        risk_budget_valid=risk_valid,
        reentry_symmetry_valid=reentry_valid,
        projected_marked_gross_fraction=projected,
        projected_open_risk_fraction=projected_risk,
        error_codes=tuple(errors),
    )


def frozen_reference_action(state: StrategicEpisodeState) -> str:
    """Pre-registered state-control action for paired topology selection."""

    if state.thesis_status == "INVALIDATED":
        return ACTION_WAIT_FLAT
    if state.quantity > ZERO:
        return ACTION_HOLD
    if state.reentry_status == "OPEN":
        return ACTION_REENTER_CORE
    return ACTION_OPEN_CORE


def _bar_price(bar: Mapping[str, Any], field: str) -> Decimal:
    return _decimal(bar.get(field), f"BAR_{field.upper()}_INVALID")


def _fill(
    *,
    action_id: str,
    side: str,
    reference_price: Decimal,
    fill_price: Decimal,
    quantity: Decimal,
    fee: Decimal,
    slippage_cost: Decimal,
    reason: str,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "side": side,
        "reference_price": reference_price,
        "fill_price": fill_price,
        "quantity": quantity,
        "notional": quantity * fill_price,
        "fee": fee,
        "slippage_cost": slippage_cost,
        "reason": reason,
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }


def replay_action_one_hour(
    state: StrategicEpisodeState,
    *,
    selected_action_id: str | None,
    sample_index: int,
    current_bar: Mapping[str, Any],
    next_bar: Mapping[str, Any],
    account: FrozenAccountPolicy,
    control_mode: str,
) -> ReplayTransition:
    """Apply one admitted action at current close, then replay one closed bar."""

    if (
        type(sample_index) is not int
        or sample_index < 0
        or control_mode
        not in {"MODEL_SELECTED", "PAIRED_REFERENCE_CONTROL", "FROZEN_BASELINE"}
    ):
        raise FormalE0ReplayError("REPLAY_REQUEST_INVALID")
    current_mark = _bar_price(current_bar, "close")
    next_close = _bar_price(next_bar, "close")
    next_low = _bar_price(next_bar, "low")
    preview = preview_action(
        state,
        selected_action_id=selected_action_id,
        current_mark=current_mark,
        account=account,
    )
    admitted = preview.admitted
    action_id = (
        str(selected_action_id) if admitted else "NO_CHANGE_FAIL_CLOSED"
    )
    before_equity = state.mark_equity(mark=current_mark, account=account)
    before_fee = state.fee_cost
    before_slippage = state.slippage_cost

    quantity = state.quantity
    average_entry = state.average_entry
    hard_stop = state.hard_stop
    core = state.nominal_core_fraction
    stage = state.nominal_stage_fraction
    realized = state.realized_pnl_before_cost
    fees = state.fee_cost
    slippage_total = state.slippage_cost
    thesis = state.thesis_status
    reentry = state.reentry_status
    fills: list[Mapping[str, Any]] = []
    forced: list[str] = []

    def buy(fraction: Decimal, reason: str) -> None:
        nonlocal quantity, average_entry, hard_stop, fees, slippage_total
        reference = current_mark
        fill_price = reference * (ONE + account.adverse_slippage_rate)
        notional = account.initial_equity * fraction
        added = notional / fill_price
        fee = notional * account.taker_fee_rate
        slippage = added * (fill_price - reference)
        combined_cost = (
            ZERO if quantity == ZERO or average_entry is None else quantity * average_entry
        ) + added * fill_price
        quantity += added
        average_entry = combined_cost / quantity
        hard_stop = average_entry * (ONE - account.hard_stop_fraction)
        fees += fee
        slippage_total += slippage
        fills.append(
            _fill(
                action_id=action_id,
                side="BUY",
                reference_price=reference,
                fill_price=fill_price,
                quantity=added,
                fee=fee,
                slippage_cost=slippage,
                reason=reason,
            )
        )

    def sell(close_quantity: Decimal, reason: str, reference: Decimal) -> None:
        nonlocal quantity, average_entry, hard_stop, fees, slippage_total, realized
        if close_quantity <= ZERO or average_entry is None:
            raise FormalE0ReplayError("REPLAY_SELL_WITHOUT_POSITION")
        fill_price = reference * (ONE - account.adverse_slippage_rate)
        fee = close_quantity * fill_price * account.taker_fee_rate
        slippage = close_quantity * (reference - fill_price)
        realized += (fill_price - average_entry) * close_quantity
        quantity -= close_quantity
        if quantity <= Decimal("0.000000000000000001"):
            quantity = ZERO
            average_entry = None
            hard_stop = None
        fees += fee
        slippage_total += slippage
        fills.append(
            _fill(
                action_id=action_id,
                side="SELL",
                reference_price=reference,
                fill_price=fill_price,
                quantity=close_quantity,
                fee=fee,
                slippage_cost=slippage,
                reason=reason,
            )
        )

    if admitted:
        if action_id == ACTION_OPEN_CORE:
            buy(account.core_fraction, "OPEN_CORE")
            core = account.core_fraction
            stage = ZERO
            reentry = "NONE"
        elif action_id == ACTION_REENTER_CORE:
            buy(account.core_fraction, "REENTRY_CORE")
            core = account.core_fraction
            stage = ZERO
            reentry = "FULFILLED"
        elif action_id == ACTION_ADD_STAGE:
            buy(account.stage_fraction, "ADD_STAGE")
            stage += account.stage_fraction
        elif action_id == ACTION_TRIM_STAGE:
            trim = min(
                quantity,
                account.initial_equity
                * account.stage_fraction
                / current_mark,
            )
            sell(trim, "TRIM_STAGE", current_mark)
            stage = max(ZERO, stage - account.stage_fraction)
        elif action_id in {ACTION_EXIT_REENTRY, ACTION_INVALIDATE_EXIT}:
            sell(quantity, "FULL_EXIT", current_mark)
            core = ZERO
            stage = ZERO
            if action_id == ACTION_EXIT_REENTRY:
                reentry = "OPEN"
            else:
                thesis = "INVALIDATED"
                reentry = "NONE"
        elif action_id == ACTION_INVALIDATE_FLAT:
            thesis = "INVALIDATED"
            reentry = "NONE"

    # The next bar is never part of the model input for ``sample_index``.  It
    # enters only this post-decision counterfactual matcher and the next
    # sample's now-observable state.
    if (
        quantity > ZERO
        and hard_stop is not None
        and next_low <= hard_stop
    ):
        stopped_quantity = quantity
        sell(stopped_quantity, "HARD_STOP_10_PERCENT", hard_stop)
        core = ZERO
        stage = ZERO
        if thesis == "ACTIVE":
            reentry = "OPEN"
        forced.append("HARD_STOP_TRIGGERED_REENTRY_OPENED")

    if quantity == ZERO:
        position_state = "FLAT"
        core = ZERO
        stage = ZERO
    elif stage > ZERO:
        position_state = "CORE_PLUS_STAGE"
    else:
        position_state = "CORE_LONG"

    provisional = StrategicEpisodeState(
        episode_id=state.episode_id,
        cohort=state.cohort,
        revision=state.revision + 1,
        prior_accepted_head="0" * 64,
        thesis_status=thesis,
        position_state=position_state,
        reentry_status=reentry,
        nominal_core_fraction=core,
        nominal_stage_fraction=stage,
        quantity=quantity,
        average_entry=average_entry,
        hard_stop=hard_stop,
        realized_pnl_before_cost=realized,
        fee_cost=fees,
        slippage_cost=slippage_total,
        equity_peak=state.equity_peak,
        max_drawdown_fraction=state.max_drawdown_fraction,
        last_mark=next_close,
        last_sample_index=sample_index,
    )
    after_equity_unpeaked = provisional.mark_equity(
        mark=next_close, account=account
    )
    peak = max(state.equity_peak, before_equity, after_equity_unpeaked)
    drawdown = (
        ZERO
        if peak <= ZERO
        else max(ZERO, (peak - after_equity_unpeaked) / peak)
    )
    maximum_drawdown = max(state.max_drawdown_fraction, drawdown)
    exposure_after_action = preview.projected_marked_gross_fraction
    primary_capture = (
        min(ONE, exposure_after_action / account.max_gross_fraction)
        if next_close > current_mark
        else ZERO
    )
    transition_core = {
        "episode_id": state.episode_id,
        "cohort": state.cohort,
        "sample_index": sample_index,
        "prior_accepted_head": state.prior_accepted_head,
        "state_before_digest": state.document()["state_digest"],
        "requested_action_id": selected_action_id,
        "executed_action_id": action_id,
        "control_mode": control_mode,
        "current_bar_id": current_bar.get("bar_id"),
        "next_bar_id": next_bar.get("bar_id"),
        "fills": fills,
        "forced_events": forced,
        "thesis_status_after": thesis,
        "position_state_after": position_state,
        "reentry_status_after": reentry,
    }
    head = canonical_digest(transition_core)
    after = replace(
        provisional,
        prior_accepted_head=head,
        equity_peak=peak,
        max_drawdown_fraction=maximum_drawdown,
    )
    after_equity = after.mark_equity(mark=next_close, account=account)
    return ReplayTransition(
        state_before=state,
        state_after=after,
        preview=preview,
        requested_action_id=selected_action_id,
        executed_action_id=action_id,
        control_mode=control_mode,
        fills=tuple(fills),
        forced_events=tuple(forced),
        equity_before=before_equity,
        equity_after=after_equity,
        net_pnl_after_cost_fraction=(
            (after_equity - before_equity) / account.initial_equity
        ),
        transaction_cost_fraction=(
            (fees - before_fee + slippage_total - before_slippage)
            / account.initial_equity
        ),
        max_drawdown_fraction=maximum_drawdown,
        primary_path_capture=primary_capture,
        transition_head_digest=head,
    )


def account_policy_from_documents(
    account_document: Mapping[str, Any],
    cost_document: Mapping[str, Any],
) -> FrozenAccountPolicy:
    verify_self_digest(account_document, "account_digest")
    verify_self_digest(cost_document, "policy_digest")
    if (
        account_document.get("schema_id") != "formal_e0_initial_account"
        or cost_document.get("schema_id") != "formal_e0_cost_policy"
        or account_document.get("long_only") is not True
        or cost_document.get("funding_status") != "UNKNOWN_EXCLUDED"
    ):
        raise FormalE0ReplayError("FORMAL_E0_POLICY_DOCUMENT_INVALID")
    return FrozenAccountPolicy(
        initial_equity=_decimal(
            account_document["initial_equity"], "ACCOUNT_VALUE_INVALID"
        ),
        core_fraction=_decimal(
            account_document["core_fraction"], "ACCOUNT_VALUE_INVALID"
        ),
        stage_fraction=_decimal(
            account_document["stage_fraction"], "ACCOUNT_VALUE_INVALID"
        ),
        max_gross_fraction=_decimal(
            account_document["max_gross_fraction"], "ACCOUNT_VALUE_INVALID"
        ),
        hard_stop_fraction=_decimal(
            account_document["hard_stop_fraction"], "ACCOUNT_VALUE_INVALID"
        ),
        taker_fee_rate=_decimal(
            cost_document["taker_fee_rate"], "COST_VALUE_INVALID"
        ),
        adverse_slippage_rate=_decimal(
            cost_document["adverse_slippage_rate"], "COST_VALUE_INVALID"
        ),
    )


__all__ = [
    "ACTION_ADD_STAGE",
    "ACTION_EXIT_REENTRY",
    "ACTION_HOLD",
    "ACTION_INVALIDATE_EXIT",
    "ACTION_INVALIDATE_FLAT",
    "ACTION_OPEN_CORE",
    "ACTION_REENTER_CORE",
    "ACTION_TRIM_STAGE",
    "ACTION_WAIT_FLAT",
    "ACTION_WAIT_REENTRY",
    "ALL_ACTION_IDS",
    "ActionPreview",
    "FormalE0ReplayError",
    "FrozenAccountPolicy",
    "ReplayTransition",
    "StrategicEpisodeState",
    "account_policy_from_documents",
    "feasible_action_documents",
    "frozen_reference_action",
    "initial_episode_state",
    "preview_action",
    "replay_action_one_hour",
]
