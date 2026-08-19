"""Complete V3.1 legal-action and ambiguity-aware planning contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    CanonicalContractError,
    canonical_decimal,
    self_digest,
    verify_self_digest,
)
from .probability_cloud import ProbabilityMode
from .financial_evaluation import (
    FinancialEvaluationError,
    verify_financial_evaluation_receipt,
)


class BehaviorPlanningError(ValueError):
    """An action set, evaluation, or selection is incomplete or overclaims."""


class PositionSide(StrEnum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class ActionType(StrEnum):
    HOLD = "HOLD"
    OPEN_LONG = "OPEN_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    ADD_25 = "ADD_25"
    ADD_50 = "ADD_50"
    ADD_75 = "ADD_75"
    ADD_100 = "ADD_100"
    REDUCE_25 = "REDUCE_25"
    REDUCE_50 = "REDUCE_50"
    REDUCE_75 = "REDUCE_75"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    EXIT_100 = "EXIT_100"
    REENTER_LONG = "REENTER_LONG"
    REENTER_SHORT = "REENTER_SHORT"
    WAIT = "WAIT"


class ReversibilityClass(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PositionRole(StrEnum):
    CORE = "CORE"
    TACTICAL = "TACTICAL"


_ACTION_SCALE = {
    ActionType.ADD_25: 25,
    ActionType.ADD_50: 50,
    ActionType.ADD_75: 75,
    ActionType.ADD_100: 100,
    ActionType.REDUCE_25: 25,
    ActionType.REDUCE_50: 50,
    ActionType.REDUCE_75: 75,
    ActionType.EXIT_100: 100,
}

_VARIABLE_SCALE_ACTIONS = frozenset(
    {
        ActionType.OPEN_LONG,
        ActionType.OPEN_SHORT,
        ActionType.PARTIAL_EXIT,
        ActionType.REENTER_LONG,
        ActionType.REENTER_SHORT,
    }
)


def _time(value: str, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise BehaviorPlanningError(code)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BehaviorPlanningError(code) from exc
    if result.tzinfo is None:
        raise BehaviorPlanningError(code)
    return result.astimezone(UTC)


def _strings(values: Sequence[str], code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise BehaviorPlanningError(code)
    result = tuple(values)
    if (not allow_empty and not result) or any(
        not isinstance(value, str) or not value.strip() for value in result
    ) or len(result) != len(set(result)):
        raise BehaviorPlanningError(code)
    return result


def _money(value: Decimal | str, code: str) -> Decimal:
    if isinstance(value, float):
        raise BehaviorPlanningError("BEHAVIOR_BINARY_FLOAT_FORBIDDEN")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BehaviorPlanningError(code) from exc
    if not result.is_finite() or result < 0:
        raise BehaviorPlanningError(code)
    return result


def _signed_money(value: Decimal | str, code: str) -> Decimal:
    """Parse a finite signed amount; expected value may legitimately be negative."""

    if isinstance(value, float):
        raise BehaviorPlanningError("BEHAVIOR_BINARY_FLOAT_FORBIDDEN")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BehaviorPlanningError(code) from exc
    if not result.is_finite():
        raise BehaviorPlanningError(code)
    return result


@dataclass(frozen=True, slots=True)
class PortfolioDecisionContext:
    decision_at: str
    position_side: PositionSide
    lot_ids: tuple[str, ...]
    pending_reentry_side: PositionSide | None
    portfolio_truth_digest: str
    risk_policy_digest: str
    probability_mode: ProbabilityMode
    probability_cloud_digest: str
    calibration_receipt_digests: tuple[str, ...] = ()
    proper_scoring_receipt_digests: tuple[str, ...] = ()
    oos_evaluation_receipt_digests: tuple[str, ...] = ()
    entry_scale_grid_pct: tuple[int, ...] = (25, 50, 75, 100)
    partial_exit_scale_grid_pct: tuple[int, ...] = (10, 40, 90)
    allowed_entry_roles: tuple[PositionRole, ...] = (
        PositionRole.CORE,
        PositionRole.TACTICAL,
    )

    def __post_init__(self) -> None:
        _time(self.decision_at, "BEHAVIOR_DECISION_AT_INVALID")
        if not isinstance(self.position_side, PositionSide) or not isinstance(
            self.probability_mode, ProbabilityMode
        ):
            raise BehaviorPlanningError("BEHAVIOR_CONTEXT_ENUM_INVALID")
        object.__setattr__(
            self, "lot_ids", _strings(self.lot_ids, "BEHAVIOR_LOTS_INVALID", allow_empty=True)
        )
        if self.position_side is PositionSide.FLAT and self.lot_ids:
            raise BehaviorPlanningError("BEHAVIOR_FLAT_WITH_LOTS_INVALID")
        if self.position_side is not PositionSide.FLAT and not self.lot_ids:
            raise BehaviorPlanningError("BEHAVIOR_POSITION_WITHOUT_LOTS_INVALID")
        if self.pending_reentry_side is not None and not isinstance(
            self.pending_reentry_side, PositionSide
        ):
            raise BehaviorPlanningError("BEHAVIOR_REENTRY_SIDE_INVALID")
        if self.pending_reentry_side is PositionSide.FLAT:
            raise BehaviorPlanningError("BEHAVIOR_REENTRY_SIDE_INVALID")
        for digest in (
            self.portfolio_truth_digest,
            self.risk_policy_digest,
            self.probability_cloud_digest,
        ):
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise BehaviorPlanningError("BEHAVIOR_CONTEXT_DIGEST_INVALID")
        for field_name in (
            "calibration_receipt_digests",
            "proper_scoring_receipt_digests",
            "oos_evaluation_receipt_digests",
        ):
            values = _strings(
                getattr(self, field_name),
                "BEHAVIOR_CALIBRATION_BINDINGS_INVALID",
                allow_empty=True,
            )
            if any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in values):
                raise BehaviorPlanningError("BEHAVIOR_CALIBRATION_BINDINGS_INVALID")
            object.__setattr__(self, field_name, values)
        calibration_sets = (
            self.calibration_receipt_digests,
            self.proper_scoring_receipt_digests,
            self.oos_evaluation_receipt_digests,
        )
        if self.probability_mode is ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION:
            if any(not values for values in calibration_sets):
                raise BehaviorPlanningError("BEHAVIOR_CALIBRATED_CLOUD_BINDING_REQUIRED")
        elif any(calibration_sets):
            raise BehaviorPlanningError("BEHAVIOR_UNCALIBRATED_RECEIPTS_FORBIDDEN")
        for field_name, upper in (
            ("entry_scale_grid_pct", 100),
            ("partial_exit_scale_grid_pct", 99),
        ):
            values = tuple(getattr(self, field_name))
            if (
                not values
                or len(values) != len(set(values))
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or not 1 <= value <= upper
                    for value in values
                )
            ):
                raise BehaviorPlanningError("BEHAVIOR_SCALE_GRID_INVALID")
            object.__setattr__(self, field_name, tuple(sorted(values)))
        roles = tuple(self.allowed_entry_roles)
        if (
            not roles
            or len(roles) != len(set(roles))
            or any(not isinstance(role, PositionRole) for role in roles)
        ):
            raise BehaviorPlanningError("BEHAVIOR_ENTRY_ROLES_INVALID")
        object.__setattr__(self, "allowed_entry_roles", roles)


def legal_action_types(context: PortfolioDecisionContext) -> tuple[ActionType, ...]:
    """Return every action legal for the current portfolio truth."""

    if context.position_side is PositionSide.FLAT:
        actions = [ActionType.WAIT, ActionType.OPEN_LONG, ActionType.OPEN_SHORT]
        if context.pending_reentry_side is PositionSide.LONG:
            actions.append(ActionType.REENTER_LONG)
        elif context.pending_reentry_side is PositionSide.SHORT:
            actions.append(ActionType.REENTER_SHORT)
        return tuple(actions)
    return (
        ActionType.HOLD,
        ActionType.ADD_25,
        ActionType.ADD_50,
        ActionType.ADD_75,
        ActionType.ADD_100,
        ActionType.REDUCE_25,
        ActionType.REDUCE_50,
        ActionType.REDUCE_75,
        ActionType.PARTIAL_EXIT,
        ActionType.EXIT_100,
        ActionType.WAIT,
    )


@dataclass(frozen=True, slots=True)
class LegalActionKey:
    action: ActionType
    target_lot_ids: tuple[str, ...]
    scale_pct: int | None
    target_role: PositionRole | None

    def as_tuple(self) -> tuple[str, tuple[str, ...], int | None, str | None]:
        return (
            self.action.value,
            self.target_lot_ids,
            self.scale_pct,
            None if self.target_role is None else self.target_role.value,
        )


def legal_action_keys(context: PortfolioDecisionContext) -> tuple[LegalActionKey, ...]:
    """Finite, deterministic action grid used by the complete comparison gate."""

    keys: list[LegalActionKey] = [LegalActionKey(ActionType.WAIT, (), None, None)]
    if context.position_side is PositionSide.FLAT:
        entry_actions = [ActionType.OPEN_LONG, ActionType.OPEN_SHORT]
        if context.pending_reentry_side is PositionSide.LONG:
            entry_actions.append(ActionType.REENTER_LONG)
        elif context.pending_reentry_side is PositionSide.SHORT:
            entry_actions.append(ActionType.REENTER_SHORT)
        for action in entry_actions:
            for scale in context.entry_scale_grid_pct:
                for role in context.allowed_entry_roles:
                    keys.append(LegalActionKey(action, (), scale, role))
        return tuple(keys)

    all_lots = tuple(sorted(context.lot_ids))
    target_groups = sorted(
        {*(tuple((lot_id,)) for lot_id in all_lots), all_lots}
    )
    keys.append(LegalActionKey(ActionType.HOLD, all_lots, None, None))
    for action, scale in (
        (ActionType.ADD_25, 25),
        (ActionType.ADD_50, 50),
        (ActionType.ADD_75, 75),
        (ActionType.ADD_100, 100),
    ):
        for role in context.allowed_entry_roles:
            keys.append(LegalActionKey(action, (), scale, role))
    for action, scale in (
        (ActionType.REDUCE_25, 25),
        (ActionType.REDUCE_50, 50),
        (ActionType.REDUCE_75, 75),
    ):
        for target in target_groups:
            keys.append(LegalActionKey(action, target, scale, None))
    for scale in context.partial_exit_scale_grid_pct:
        for target in target_groups:
            keys.append(LegalActionKey(ActionType.PARTIAL_EXIT, target, scale, None))
    for target in target_groups:
        keys.append(LegalActionKey(ActionType.EXIT_100, target, 100, None))
    return tuple(keys)


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    candidate_id: str
    action: ActionType
    target_lot_ids: tuple[str, ...]
    scale_pct: int | None
    target_role: PositionRole | None
    trigger_conditions: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    path_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    risk_refs: tuple[str, ...]
    thesis: str
    wait_reason: str | None = None
    opportunity_cost: str | None = None
    next_observation: str | None = None
    next_review_at: str | None = None
    information_not_arrived_default: str | None = None
    position_protection_responsibility: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise BehaviorPlanningError("BEHAVIOR_CANDIDATE_ID_INVALID")
        if not isinstance(self.action, ActionType) or not isinstance(self.thesis, str) or not self.thesis.strip():
            raise BehaviorPlanningError("BEHAVIOR_CANDIDATE_INVALID")
        for field_name in (
            "target_lot_ids",
            "trigger_conditions",
            "invalidation_conditions",
            "path_refs",
            "evidence_refs",
            "risk_refs",
        ):
            object.__setattr__(
                self,
                field_name,
                _strings(
                    getattr(self, field_name),
                    "BEHAVIOR_CANDIDATE_REFS_INVALID",
                    allow_empty=field_name == "target_lot_ids",
                ),
            )
        expected_scale = _ACTION_SCALE.get(self.action)
        if expected_scale is not None and self.scale_pct != expected_scale:
            raise BehaviorPlanningError("BEHAVIOR_ACTION_SCALE_MISMATCH")
        if self.action in _VARIABLE_SCALE_ACTIONS:
            upper_bound = 99 if self.action is ActionType.PARTIAL_EXIT else 100
            if (
                isinstance(self.scale_pct, bool)
                or not isinstance(self.scale_pct, int)
                or not 1 <= self.scale_pct <= upper_bound
            ):
                raise BehaviorPlanningError("BEHAVIOR_VARIABLE_ACTION_SCALE_INVALID")
        elif expected_scale is None and self.scale_pct is not None:
            raise BehaviorPlanningError("BEHAVIOR_ACTION_SCALE_FORBIDDEN")
        role_required = self.action in {
            ActionType.OPEN_LONG,
            ActionType.OPEN_SHORT,
            ActionType.REENTER_LONG,
            ActionType.REENTER_SHORT,
            ActionType.ADD_25,
            ActionType.ADD_50,
            ActionType.ADD_75,
            ActionType.ADD_100,
        }
        if role_required and not isinstance(self.target_role, PositionRole):
            raise BehaviorPlanningError("BEHAVIOR_TARGET_ROLE_REQUIRED")
        if not role_required and self.target_role is not None:
            raise BehaviorPlanningError("BEHAVIOR_TARGET_ROLE_FORBIDDEN")
        if self.action is ActionType.WAIT:
            if any(
                not isinstance(value, str) or not value.strip()
                for value in (
                    self.wait_reason,
                    self.opportunity_cost,
                    self.next_observation,
                    self.next_review_at,
                    self.information_not_arrived_default,
                    self.position_protection_responsibility,
                )
            ):
                raise BehaviorPlanningError("BEHAVIOR_WAIT_OBLIGATIONS_REQUIRED")
            _time(str(self.next_review_at), "BEHAVIOR_WAIT_REVIEW_INVALID")
        elif any(
            value is not None
            for value in (
                self.wait_reason,
                self.opportunity_cost,
                self.next_observation,
                self.next_review_at,
                self.information_not_arrived_default,
                self.position_protection_responsibility,
            )
        ):
            raise BehaviorPlanningError("BEHAVIOR_WAIT_FIELDS_FORBIDDEN")

    def to_document(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "action": self.action.value,
            "target_lot_ids": list(self.target_lot_ids),
            "scale_pct": self.scale_pct,
            "target_role": (
                None if self.target_role is None else self.target_role.value
            ),
            "trigger_conditions": list(self.trigger_conditions),
            "invalidation_conditions": list(self.invalidation_conditions),
            "path_refs": list(self.path_refs),
            "evidence_refs": list(self.evidence_refs),
            "risk_refs": list(self.risk_refs),
            "thesis": self.thesis,
            "wait_reason": self.wait_reason,
            "opportunity_cost": self.opportunity_cost,
            "next_observation": self.next_observation,
            "next_review_at": self.next_review_at,
            "information_not_arrived_default": self.information_not_arrived_default,
            "position_protection_responsibility": self.position_protection_responsibility,
            "authorized": False,
        }


@dataclass(frozen=True, slots=True)
class ActionEvaluation:
    candidate_id: str
    feasible: bool
    infeasible_reasons: tuple[str, ...]
    transaction_cost_usdt: Decimal | str
    liquidity_cost_usdt: Decimal | str
    worst_case_loss_usdt: Decimal | str
    maximum_regret_usdt: Decimal | str | None
    regret_status: str
    reversibility: ReversibilityClass
    scenario_refs: tuple[str, ...]
    robustness_notes: tuple[str, ...]
    economics: Mapping[str, Any]
    expected_value_lower_usdt: Decimal | str | None = None
    expected_value_upper_usdt: Decimal | str | None = None
    expected_value_usdt: Decimal | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise BehaviorPlanningError("BEHAVIOR_EVALUATION_ID_INVALID")
        if not isinstance(self.feasible, bool):
            raise BehaviorPlanningError("BEHAVIOR_FEASIBILITY_INVALID")
        object.__setattr__(
            self,
            "infeasible_reasons",
            _strings(
                self.infeasible_reasons,
                "BEHAVIOR_INFEASIBLE_REASONS_INVALID",
                allow_empty=self.feasible,
            ),
        )
        if self.feasible and self.infeasible_reasons:
            raise BehaviorPlanningError("BEHAVIOR_FEASIBILITY_CONTRADICTION")
        for field_name in (
            "transaction_cost_usdt",
            "liquidity_cost_usdt",
            "worst_case_loss_usdt",
        ):
            object.__setattr__(
                self, field_name, _money(getattr(self, field_name), "BEHAVIOR_MONEY_INVALID")
            )
        if self.maximum_regret_usdt is None:
            if self.regret_status != "UNAVAILABLE_NO_FROZEN_PRICE_PATH_PAYOFF_MATRIX":
                raise BehaviorPlanningError("BEHAVIOR_REGRET_STATUS_INVALID")
        else:
            object.__setattr__(
                self,
                "maximum_regret_usdt",
                _money(self.maximum_regret_usdt, "BEHAVIOR_MONEY_INVALID"),
            )
            if self.regret_status != "AVAILABLE_FROM_FROZEN_PRICE_PATH_PAYOFF_MATRIX":
                raise BehaviorPlanningError("BEHAVIOR_REGRET_STATUS_INVALID")
        for field_name in (
            "expected_value_lower_usdt",
            "expected_value_upper_usdt",
            "expected_value_usdt",
        ):
            if getattr(self, field_name) is None:
                continue
            object.__setattr__(
                self,
                field_name,
                _signed_money(
                    getattr(self, field_name), "BEHAVIOR_EXPECTED_VALUE_INVALID"
                ),
            )
        lower = self.expected_value_lower_usdt
        upper = self.expected_value_upper_usdt
        point = self.expected_value_usdt
        if (lower is None) != (upper is None):
            raise BehaviorPlanningError("BEHAVIOR_EXPECTED_VALUE_INTERVAL_INCOMPLETE")
        if lower is not None and lower > upper:
            raise BehaviorPlanningError("BEHAVIOR_EXPECTED_VALUE_INTERVAL_INVALID")
        if point is not None and (lower is None or lower != upper or point != lower):
            raise BehaviorPlanningError("BEHAVIOR_EXPECTED_VALUE_POINT_UNJUSTIFIED")
        if not isinstance(self.reversibility, ReversibilityClass):
            raise BehaviorPlanningError("BEHAVIOR_REVERSIBILITY_INVALID")
        for field_name in ("scenario_refs", "robustness_notes"):
            object.__setattr__(
                self,
                field_name,
                _strings(getattr(self, field_name), "BEHAVIOR_EVALUATION_REFS_INVALID"),
            )
        required_economics = frozenset(
            {
                "quantity_delta",
                "unrounded_quantity_delta",
                "quantity_rounding_loss_contracts",
                "estimated_fill_price",
                "turnover_notional_usdt",
                "symbol_notional_after_usdt",
                "symbol_risk_after_usdt",
                "portfolio_risk_after_usdt",
                "gross_notional_after_usdt",
                "margin_used_after_usdt",
                "gross_leverage_after",
                "protective_stop_after",
            }
        )
        if not isinstance(self.economics, Mapping) or set(self.economics) != required_economics:
            raise BehaviorPlanningError("BEHAVIOR_ECONOMICS_SCHEMA_INVALID")
        normalized_economics = dict(self.economics)
        for field_name in (
            "quantity_delta",
            "unrounded_quantity_delta",
        ):
            normalized_economics[field_name] = canonical_decimal(
                _signed_money(
                    normalized_economics[field_name],
                    "BEHAVIOR_ECONOMICS_VALUE_INVALID",
                )
            )
        for field_name in required_economics - {
            "quantity_delta",
            "unrounded_quantity_delta",
            "protective_stop_after",
        }:
            normalized_economics[field_name] = canonical_decimal(
                _money(
                    normalized_economics[field_name],
                    "BEHAVIOR_ECONOMICS_VALUE_INVALID",
                )
            )
        stop = normalized_economics["protective_stop_after"]
        normalized_economics["protective_stop_after"] = (
            None
            if stop is None
            else canonical_decimal(
                _money(stop, "BEHAVIOR_ECONOMICS_VALUE_INVALID")
            )
        )
        object.__setattr__(self, "economics", normalized_economics)

    def to_document(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "feasible": self.feasible,
            "infeasible_reasons": list(self.infeasible_reasons),
            "transaction_cost_usdt": canonical_decimal(self.transaction_cost_usdt),
            "liquidity_cost_usdt": canonical_decimal(self.liquidity_cost_usdt),
            "worst_case_loss_usdt": canonical_decimal(self.worst_case_loss_usdt),
            "maximum_regret_usdt": (
                None
                if self.maximum_regret_usdt is None
                else canonical_decimal(self.maximum_regret_usdt)
            ),
            "regret_status": self.regret_status,
            "reversibility": self.reversibility.value,
            "scenario_refs": list(self.scenario_refs),
            "robustness_notes": list(self.robustness_notes),
            "economics": dict(self.economics),
            "expected_value_lower_usdt": (
                None
                if self.expected_value_lower_usdt is None
                else canonical_decimal(self.expected_value_lower_usdt)
            ),
            "expected_value_upper_usdt": (
                None
                if self.expected_value_upper_usdt is None
                else canonical_decimal(self.expected_value_upper_usdt)
            ),
            "expected_value_usdt": (
                None
                if self.expected_value_usdt is None
                else canonical_decimal(self.expected_value_usdt)
            ),
        }


def action_evaluations_from_financial_receipt(
    *,
    financial_evaluation_receipt: Mapping[str, Any],
    candidates: Sequence[ActionCandidate],
) -> tuple[ActionEvaluation, ...]:
    """Construct typed evaluations only from a semantically verified receipt."""

    candidate_rows = tuple(candidates)
    if any(not isinstance(row, ActionCandidate) for row in candidate_rows):
        raise BehaviorPlanningError("BEHAVIOR_EVALUATION_ROWS_INVALID")
    try:
        verify_financial_evaluation_receipt(
            financial_evaluation_receipt,
            candidates=[row.to_document() for row in candidate_rows],
        )
        by_id = {
            row["candidate_id"]: row
            for row in financial_evaluation_receipt["evaluations"]
        }
        if set(by_id) != {row.candidate_id for row in candidate_rows}:
            raise BehaviorPlanningError("BEHAVIOR_FINANCIAL_EVALUATION_MISMATCH")
        return tuple(
            ActionEvaluation(
                candidate_id=raw["candidate_id"],
                feasible=raw["feasible"],
                infeasible_reasons=tuple(raw["infeasible_reasons"]),
                transaction_cost_usdt=raw["transaction_cost_usdt"],
                liquidity_cost_usdt=raw["liquidity_cost_usdt"],
                worst_case_loss_usdt=raw["worst_case_loss_usdt"],
                maximum_regret_usdt=raw["maximum_regret_usdt"],
                regret_status=raw["regret_status"],
                reversibility=ReversibilityClass(raw["reversibility"]),
                scenario_refs=tuple(raw["scenario_refs"]),
                robustness_notes=tuple(raw["robustness_notes"]),
                economics=raw["economics"],
                expected_value_lower_usdt=raw[
                    "expected_value_lower_usdt"
                ],
                expected_value_upper_usdt=raw[
                    "expected_value_upper_usdt"
                ],
                expected_value_usdt=raw["expected_value_usdt"],
            )
            for raw in (by_id[row.candidate_id] for row in candidate_rows)
        )
    except (KeyError, TypeError, ValueError, FinancialEvaluationError) as exc:
        if isinstance(exc, BehaviorPlanningError):
            raise
        raise BehaviorPlanningError("BEHAVIOR_FINANCIAL_RECEIPT_INVALID") from exc


def seal_complete_action_evaluation(
    *,
    run_id: str,
    cycle_index: int,
    context: PortfolioDecisionContext,
    candidates: Sequence[ActionCandidate],
    evaluations: Sequence[ActionEvaluation],
    financial_evaluation_receipt: Mapping[str, Any],
    evaluated_at: str,
) -> dict[str, Any]:
    """Seal the complete legal action comparison before any selection."""

    if (
        not isinstance(run_id, str)
        or not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
    ):
        raise BehaviorPlanningError("BEHAVIOR_EVALUATION_IDENTITY_INVALID")
    evaluated_time = _time(evaluated_at, "BEHAVIOR_EVALUATED_AT_INVALID")
    if evaluated_time < _time(context.decision_at, "BEHAVIOR_DECISION_AT_INVALID"):
        raise BehaviorPlanningError("BEHAVIOR_EVALUATION_PRECEDES_DECISION")
    candidate_rows = tuple(candidates)
    evaluation_rows = tuple(evaluations)
    if any(not isinstance(row, ActionCandidate) for row in candidate_rows) or any(
        not isinstance(row, ActionEvaluation) for row in evaluation_rows
    ):
        raise BehaviorPlanningError("BEHAVIOR_EVALUATION_ROWS_INVALID")
    candidate_ids = [row.candidate_id for row in candidate_rows]
    evaluation_ids = [row.candidate_id for row in evaluation_rows]
    if (
        len(candidate_ids) != len(set(candidate_ids))
        or len(evaluation_ids) != len(set(evaluation_ids))
        or set(candidate_ids) != set(evaluation_ids)
    ):
        raise BehaviorPlanningError("BEHAVIOR_EVALUATION_CANDIDATE_BINDING_INVALID")
    legal = {key.as_tuple() for key in legal_action_keys(context)}
    supplied_keys = {
        (
            row.action.value,
            tuple(sorted(row.target_lot_ids)),
            row.scale_pct,
            None if row.target_role is None else row.target_role.value,
        )
        for row in candidate_rows
    }
    if supplied_keys != legal or len(candidate_rows) != len(legal):
        raise BehaviorPlanningError("BEHAVIOR_LEGAL_ACTION_SET_INCOMPLETE")
    by_evaluation = {row.candidate_id: row for row in evaluation_rows}
    if context.probability_mode is not ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION and any(
        row.expected_value_usdt is not None
        or row.expected_value_lower_usdt is not None
        or row.expected_value_upper_usdt is not None
        for row in evaluation_rows
    ):
        raise BehaviorPlanningError("BEHAVIOR_UNCALIBRATED_EXPECTED_VALUE_FORBIDDEN")
    if context.probability_mode is ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION and any(
        not values
        for values in (
            context.calibration_receipt_digests,
            context.proper_scoring_receipt_digests,
            context.oos_evaluation_receipt_digests,
        )
    ):
        raise BehaviorPlanningError("BEHAVIOR_CALIBRATED_CLOUD_BINDING_REQUIRED")
    if context.position_side is PositionSide.FLAT and any(row.target_lot_ids for row in candidate_rows):
        raise BehaviorPlanningError("BEHAVIOR_FLAT_ACTION_TARGET_LOT_FORBIDDEN")
    if context.position_side is not PositionSide.FLAT:
        for row in candidate_rows:
            if row.action not in {
                ActionType.WAIT,
                ActionType.ADD_25,
                ActionType.ADD_50,
                ActionType.ADD_75,
                ActionType.ADD_100,
            } and (
                not row.target_lot_ids
                or not set(row.target_lot_ids).issubset(set(context.lot_ids))
            ):
                raise BehaviorPlanningError("BEHAVIOR_TARGET_LOT_INVALID")
            if row.action in {
                ActionType.ADD_25,
                ActionType.ADD_50,
                ActionType.ADD_75,
                ActionType.ADD_100,
            } and row.target_lot_ids:
                raise BehaviorPlanningError("BEHAVIOR_ADD_TARGET_LOT_FORBIDDEN")
    for row in candidate_rows:
        if row.action is ActionType.WAIT and _time(
            str(row.next_review_at), "BEHAVIOR_WAIT_REVIEW_INVALID"
        ) < _time(context.decision_at, "BEHAVIOR_DECISION_AT_INVALID"):
            raise BehaviorPlanningError("BEHAVIOR_WAIT_REVIEW_PRECEDES_DECISION")
    candidate_documents = [row.to_document() for row in candidate_rows]
    try:
        financial_receipt_digest = verify_financial_evaluation_receipt(
            financial_evaluation_receipt,
            candidates=candidate_documents,
        )
    except FinancialEvaluationError as exc:
        raise BehaviorPlanningError("BEHAVIOR_FINANCIAL_RECEIPT_INVALID") from exc
    receipt_bindings = {
        "run_id": run_id,
        "cycle_index": cycle_index,
        "decision_at": context.decision_at,
        "evaluated_at": evaluated_at,
        "portfolio_truth_digest": context.portfolio_truth_digest,
        "risk_policy_digest": context.risk_policy_digest,
        "probability_mode": context.probability_mode.value,
        "probability_cloud_digest": context.probability_cloud_digest,
        "calibration_receipt_digests": list(context.calibration_receipt_digests),
        "proper_scoring_receipt_digests": list(
            context.proper_scoring_receipt_digests
        ),
        "oos_evaluation_receipt_digests": list(
            context.oos_evaluation_receipt_digests
        ),
    }
    if any(
        financial_evaluation_receipt.get(field_name) != expected
        for field_name, expected in receipt_bindings.items()
    ):
        raise BehaviorPlanningError("BEHAVIOR_FINANCIAL_RECEIPT_BINDING_MISMATCH")
    position_document = financial_evaluation_receipt.get("position_truth")
    if not isinstance(position_document, Mapping):
        raise BehaviorPlanningError("BEHAVIOR_FINANCIAL_POSITION_BINDING_INVALID")
    try:
        current_quantity = _money(
            position_document["target_symbol"]["current_quantity"],
            "BEHAVIOR_FINANCIAL_POSITION_BINDING_INVALID",
        )
        intended_side = str(position_document["intended_side"])
    except (KeyError, TypeError) as exc:
        raise BehaviorPlanningError(
            "BEHAVIOR_FINANCIAL_POSITION_BINDING_INVALID"
        ) from exc
    if (
        context.position_side is PositionSide.FLAT
        and (current_quantity != 0 or intended_side != PositionSide.FLAT.value)
    ) or (
        context.position_side is not PositionSide.FLAT
        and (
            current_quantity <= 0
            or intended_side != context.position_side.value
        )
    ):
        raise BehaviorPlanningError("BEHAVIOR_FINANCIAL_POSITION_BINDING_INVALID")
    supplied_evaluation_documents = [
        by_evaluation[row.candidate_id].to_document() for row in candidate_rows
    ]
    receipt_evaluations = {
        row.get("candidate_id"): row
        for row in financial_evaluation_receipt.get("evaluations", ())
        if isinstance(row, Mapping)
    }
    expected_evaluation_documents = [
        receipt_evaluations.get(row.candidate_id) for row in candidate_rows
    ]
    if (
        len(receipt_evaluations) != len(candidate_rows)
        or supplied_evaluation_documents != expected_evaluation_documents
    ):
        raise BehaviorPlanningError("BEHAVIOR_FINANCIAL_EVALUATION_MISMATCH")
    document = {
        "schema_id": "theory_paper_v2_v31_complete_action_evaluation",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "cycle_index": cycle_index,
        "decision_at": context.decision_at,
        "evaluated_at": evaluated_at,
        "portfolio_truth_digest": context.portfolio_truth_digest,
        "risk_policy_digest": context.risk_policy_digest,
        "probability_mode": context.probability_mode.value,
        "probability_cloud_digest": context.probability_cloud_digest,
        "calibration_receipt_digests": list(context.calibration_receipt_digests),
        "proper_scoring_receipt_digests": list(
            context.proper_scoring_receipt_digests
        ),
        "oos_evaluation_receipt_digests": list(
            context.oos_evaluation_receipt_digests
        ),
        "position_side": context.position_side.value,
        "lot_ids": list(context.lot_ids),
        "pending_reentry_side": (
            None
            if context.pending_reentry_side is None
            else context.pending_reentry_side.value
        ),
        "entry_scale_grid_pct": list(context.entry_scale_grid_pct),
        "partial_exit_scale_grid_pct": list(context.partial_exit_scale_grid_pct),
        "allowed_entry_roles": [role.value for role in context.allowed_entry_roles],
        "candidates": candidate_documents,
        "financial_evaluation_receipt_digest": financial_receipt_digest,
        "financial_evaluation_receipt": dict(financial_evaluation_receipt),
        "evaluations": supplied_evaluation_documents,
        "selection_present": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, "action_evaluation_digest")


_SEALED_EVALUATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "evaluated_at",
        "portfolio_truth_digest",
        "risk_policy_digest",
        "probability_mode",
        "probability_cloud_digest",
        "calibration_receipt_digests",
        "proper_scoring_receipt_digests",
        "oos_evaluation_receipt_digests",
        "position_side",
        "lot_ids",
        "pending_reentry_side",
        "entry_scale_grid_pct",
        "partial_exit_scale_grid_pct",
        "allowed_entry_roles",
        "candidates",
        "financial_evaluation_receipt_digest",
        "financial_evaluation_receipt",
        "evaluations",
        "selection_present",
        "external_execution_authority",
        "executable",
        "action_evaluation_digest",
    }
)
_CANDIDATE_DOCUMENT_FIELDS = frozenset(
    {
        "candidate_id",
        "action",
        "target_lot_ids",
        "scale_pct",
        "target_role",
        "trigger_conditions",
        "invalidation_conditions",
        "path_refs",
        "evidence_refs",
        "risk_refs",
        "thesis",
        "wait_reason",
        "opportunity_cost",
        "next_observation",
        "next_review_at",
        "information_not_arrived_default",
        "position_protection_responsibility",
        "authorized",
    }
)
_EVALUATION_DOCUMENT_FIELDS = frozenset(
    {
        "candidate_id",
        "feasible",
        "infeasible_reasons",
        "transaction_cost_usdt",
        "liquidity_cost_usdt",
        "worst_case_loss_usdt",
        "maximum_regret_usdt",
        "regret_status",
        "reversibility",
        "scenario_refs",
        "robustness_notes",
        "economics",
        "expected_value_lower_usdt",
        "expected_value_upper_usdt",
        "expected_value_usdt",
    }
)


def verify_complete_action_evaluation(evaluation: Mapping[str, Any]) -> str:
    """Reconstruct and re-run the complete sealer, not merely its hash check."""

    if not isinstance(evaluation, Mapping) or set(evaluation) != _SEALED_EVALUATION_FIELDS:
        raise BehaviorPlanningError("BEHAVIOR_SEALED_EVALUATION_SCHEMA_INVALID")
    try:
        supplied_digest = verify_self_digest(evaluation, "action_evaluation_digest")
        pending_side = evaluation["pending_reentry_side"]
        context = PortfolioDecisionContext(
            decision_at=str(evaluation["decision_at"]),
            position_side=PositionSide(str(evaluation["position_side"])),
            lot_ids=tuple(evaluation["lot_ids"]),
            pending_reentry_side=(
                None if pending_side is None else PositionSide(str(pending_side))
            ),
            portfolio_truth_digest=str(evaluation["portfolio_truth_digest"]),
            risk_policy_digest=str(evaluation["risk_policy_digest"]),
            probability_mode=ProbabilityMode(str(evaluation["probability_mode"])),
            probability_cloud_digest=str(evaluation["probability_cloud_digest"]),
            calibration_receipt_digests=tuple(
                evaluation["calibration_receipt_digests"]
            ),
            proper_scoring_receipt_digests=tuple(
                evaluation["proper_scoring_receipt_digests"]
            ),
            oos_evaluation_receipt_digests=tuple(
                evaluation["oos_evaluation_receipt_digests"]
            ),
            entry_scale_grid_pct=tuple(evaluation["entry_scale_grid_pct"]),
            partial_exit_scale_grid_pct=tuple(
                evaluation["partial_exit_scale_grid_pct"]
            ),
            allowed_entry_roles=tuple(
                PositionRole(value) for value in evaluation["allowed_entry_roles"]
            ),
        )
        candidate_rows: list[ActionCandidate] = []
        for raw in evaluation["candidates"]:
            if (
                not isinstance(raw, Mapping)
                or set(raw) != _CANDIDATE_DOCUMENT_FIELDS
                or raw.get("authorized") is not False
            ):
                raise BehaviorPlanningError("BEHAVIOR_CANDIDATE_DOCUMENT_INVALID")
            candidate_rows.append(
                ActionCandidate(
                    candidate_id=raw["candidate_id"],
                    action=ActionType(raw["action"]),
                    target_lot_ids=tuple(raw["target_lot_ids"]),
                    scale_pct=raw["scale_pct"],
                    target_role=(
                        None
                        if raw["target_role"] is None
                        else PositionRole(raw["target_role"])
                    ),
                    trigger_conditions=tuple(raw["trigger_conditions"]),
                    invalidation_conditions=tuple(raw["invalidation_conditions"]),
                    path_refs=tuple(raw["path_refs"]),
                    evidence_refs=tuple(raw["evidence_refs"]),
                    risk_refs=tuple(raw["risk_refs"]),
                    thesis=raw["thesis"],
                    wait_reason=raw["wait_reason"],
                    opportunity_cost=raw["opportunity_cost"],
                    next_observation=raw["next_observation"],
                    next_review_at=raw["next_review_at"],
                    information_not_arrived_default=raw[
                        "information_not_arrived_default"
                    ],
                    position_protection_responsibility=raw[
                        "position_protection_responsibility"
                    ],
                )
            )
        evaluation_rows: list[ActionEvaluation] = []
        for raw in evaluation["evaluations"]:
            if not isinstance(raw, Mapping) or set(raw) != _EVALUATION_DOCUMENT_FIELDS:
                raise BehaviorPlanningError("BEHAVIOR_EVALUATION_DOCUMENT_INVALID")
            evaluation_rows.append(
                ActionEvaluation(
                    candidate_id=raw["candidate_id"],
                    feasible=raw["feasible"],
                    infeasible_reasons=tuple(raw["infeasible_reasons"]),
                    transaction_cost_usdt=raw["transaction_cost_usdt"],
                    liquidity_cost_usdt=raw["liquidity_cost_usdt"],
                    worst_case_loss_usdt=raw["worst_case_loss_usdt"],
                    maximum_regret_usdt=raw["maximum_regret_usdt"],
                    regret_status=raw["regret_status"],
                    reversibility=ReversibilityClass(raw["reversibility"]),
                    scenario_refs=tuple(raw["scenario_refs"]),
                    robustness_notes=tuple(raw["robustness_notes"]),
                    economics=raw["economics"],
                    expected_value_lower_usdt=raw[
                        "expected_value_lower_usdt"
                    ],
                    expected_value_upper_usdt=raw[
                        "expected_value_upper_usdt"
                    ],
                    expected_value_usdt=raw["expected_value_usdt"],
                )
            )
        rebuilt = seal_complete_action_evaluation(
            run_id=str(evaluation["run_id"]),
            cycle_index=evaluation["cycle_index"],
            context=context,
            candidates=tuple(candidate_rows),
            evaluations=tuple(evaluation_rows),
            financial_evaluation_receipt=evaluation[
                "financial_evaluation_receipt"
            ],
            evaluated_at=str(evaluation["evaluated_at"]),
        )
    except (KeyError, TypeError, ValueError, CanonicalContractError) as exc:
        if isinstance(exc, BehaviorPlanningError):
            raise
        raise BehaviorPlanningError("BEHAVIOR_SEALED_EVALUATION_INVALID") from exc
    if rebuilt != dict(evaluation):
        raise BehaviorPlanningError("BEHAVIOR_SEALED_EVALUATION_RECONSTRUCTION_MISMATCH")
    return supplied_digest


def seal_action_selection(
    *,
    evaluation: Mapping[str, Any],
    selected_candidate_id: str,
    reason: str,
    alternative_explanations: Mapping[str, str],
    failure_conditions: Sequence[str],
    next_review_at: str,
    selected_at: str,
) -> dict[str, Any]:
    """Bind an Agent choice to an already sealed, complete evaluation."""

    try:
        verify_complete_action_evaluation(evaluation)
    except (BehaviorPlanningError, CanonicalContractError) as exc:
        raise BehaviorPlanningError(
            "BEHAVIOR_SELECTION_REQUIRES_SEALED_EVALUATION"
        ) from exc
    candidates = {
        row["candidate_id"]: row for row in evaluation.get("candidates", [])
    }
    evaluations = {
        row["candidate_id"]: row for row in evaluation.get("evaluations", [])
    }
    if selected_candidate_id not in candidates or not evaluations.get(
        selected_candidate_id, {}
    ).get("feasible"):
        raise BehaviorPlanningError("BEHAVIOR_SELECTED_CANDIDATE_NOT_FEASIBLE")
    alternatives = set(candidates) - {selected_candidate_id}
    if set(alternative_explanations) != alternatives or any(
        not isinstance(value, str) or not value.strip()
        for value in alternative_explanations.values()
    ):
        raise BehaviorPlanningError("BEHAVIOR_ALTERNATIVE_EXPLANATIONS_INCOMPLETE")
    if not isinstance(reason, str) or not reason.strip():
        raise BehaviorPlanningError("BEHAVIOR_SELECTION_REASON_REQUIRED")
    failures = _strings(failure_conditions, "BEHAVIOR_SELECTION_FAILURES_REQUIRED")
    selected_time = _time(selected_at, "BEHAVIOR_SELECTION_TIME_INVALID")
    if selected_time < _time(
        str(evaluation.get("evaluated_at")), "BEHAVIOR_EVALUATED_AT_INVALID"
    ):
        raise BehaviorPlanningError("BEHAVIOR_SELECTION_PRECEDES_EVALUATION")
    if _time(next_review_at, "BEHAVIOR_SELECTION_REVIEW_INVALID") < selected_time:
        raise BehaviorPlanningError("BEHAVIOR_SELECTION_REVIEW_PRECEDES_SELECTION")
    if candidates[selected_candidate_id]["action"] == ActionType.WAIT.value and (
        next_review_at != candidates[selected_candidate_id]["next_review_at"]
    ):
        raise BehaviorPlanningError("BEHAVIOR_WAIT_REVIEW_MUST_MATCH_CANDIDATE")
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_action_selection",
            "schema_version": "1.0.0",
            "run_id": evaluation["run_id"],
            "cycle_index": evaluation["cycle_index"],
            "action_evaluation_digest": evaluation["action_evaluation_digest"],
            "selected_candidate_id": selected_candidate_id,
            "selected_action": candidates[selected_candidate_id]["action"],
            "reason": reason,
            "alternative_explanations": dict(sorted(alternative_explanations.items())),
            "failure_conditions": list(failures),
            "next_review_at": next_review_at,
            "selected_at": selected_at,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "action_selection_digest",
    )


__all__ = [
    "ActionCandidate",
    "ActionEvaluation",
    "ActionType",
    "BehaviorPlanningError",
    "LegalActionKey",
    "PortfolioDecisionContext",
    "PositionRole",
    "PositionSide",
    "ReversibilityClass",
    "action_evaluations_from_financial_receipt",
    "legal_action_types",
    "legal_action_keys",
    "seal_action_selection",
    "seal_complete_action_evaluation",
    "verify_complete_action_evaluation",
]
