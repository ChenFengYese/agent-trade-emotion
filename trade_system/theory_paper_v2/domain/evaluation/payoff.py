"""Pure payoff calculations and complete path/action matrix construction."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from ..common import DomainError, DomainResult, ReducerStatus
from ..contracts.canonical import canonical_digest
from .model import (
    REQUIRED_PATHS,
    DataStatus,
    DecimalInterval,
    PathKind,
    PathPayoffCell,
    PathPayoffMatrix,
    ProbabilityStatus,
    require_decimal,
)


def _error(code: str, message: str, *, unknown: bool = False) -> DomainResult:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if unknown else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="EVALUATION",
            retryability="AFTER_INPUT_REPAIR" if unknown else "NEVER",
            message=message,
        ),
    )


def calculate_linear_pnl_interval(
    *,
    side: str,
    entry_price: Decimal,
    terminal_price: DecimalInterval,
    quantity: Decimal,
    fees: DecimalInterval,
    slippage: DecimalInterval,
    funding: DecimalInterval,
    account_unit_ref: str,
) -> DecimalInterval:
    """Calculate a conservative linear P&L interval with explicit costs."""

    require_decimal(entry_price)
    require_decimal(quantity)
    if quantity < 0 or entry_price <= 0:
        raise ValueError("PAYOFF_INPUT_OUT_OF_RANGE")
    if any(
        interval.unit_ref != account_unit_ref
        for interval in (fees, slippage, funding)
    ):
        raise ValueError("PAYOFF_COST_UNIT_MISMATCH")
    if terminal_price.unit_ref != "PRICE":
        raise ValueError("PAYOFF_PRICE_UNIT_REQUIRED")
    if side == "LONG":
        gross = DecimalInterval(
            (terminal_price.lower - entry_price) * quantity,
            (terminal_price.upper - entry_price) * quantity,
            account_unit_ref,
        )
    elif side == "SHORT":
        gross = DecimalInterval(
            (entry_price - terminal_price.upper) * quantity,
            (entry_price - terminal_price.lower) * quantity,
            account_unit_ref,
        )
    else:
        raise ValueError("PAYOFF_SIDE_UNKNOWN")
    total_cost = fees.add(slippage).add(funding)
    return gross.subtract(total_cost)


def build_path_payoff_matrix(
    *,
    matrix_id: str,
    strategic_episode_ref: str,
    revision: int,
    decision_cutoff: datetime,
    decision_horizon_ref: str,
    planning_context_id: str,
    candidate_action_set_digest: str,
    action_plan_refs: tuple[str, ...],
    cells: tuple[PathPayoffCell, ...],
    probability_status: ProbabilityStatus,
    ordinal_path_ranks: tuple[tuple[PathKind, int], ...] = (),
    probability_use_authorization_ref: str | None = None,
    forecast_coherence_receipt_ref: str | None = None,
    expected_value_ref: str | None = None,
    kelly_size_ref: str | None = None,
) -> DomainResult[PathPayoffMatrix]:
    """Build the exact four-path plus OTHER/UNKNOWN Cartesian matrix."""

    if decision_cutoff.tzinfo is None or revision < 1:
        return _error("PATH_PAYOFF_MATRIX_IDENTITY_INVALID", "invalid time or revision")
    if (
        not action_plan_refs
        or len(action_plan_refs) != len(set(action_plan_refs))
        or not candidate_action_set_digest
    ):
        return _error(
            "PATH_PAYOFF_MATRIX_ACTION_SET_INVALID",
            "matrix action columns must be exact and unique",
        )
    required_keys = {
        (path, action_ref)
        for path in REQUIRED_PATHS
        for action_ref in action_plan_refs
    }
    actual_keys = {(cell.path, cell.action_plan_ref) for cell in cells}
    if len(cells) != len(actual_keys) or actual_keys != required_keys:
        return _error(
            "PATH_PAYOFF_MATRIX_COVERAGE_INCOMPLETE",
            "matrix must cover all four paths plus distinct OTHER and UNKNOWN",
        )
    if probability_status is ProbabilityStatus.CALIBRATED_OOS:
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "E0 cannot accept calibration or numeric probability authority",
        )
    if (
        probability_use_authorization_ref is not None
        or expected_value_ref is not None
        or kelly_size_ref is not None
    ):
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "ordinal/unknown matrix cannot carry authorization, EV, or Kelly",
        )
    rank_map = dict(ordinal_path_ranks)
    if len(rank_map) != len(ordinal_path_ranks) or any(
        not isinstance(rank, int) or isinstance(rank, bool) or rank < 1
        for rank in rank_map.values()
    ):
        return _error("ORDINAL_PATH_RANK_INVALID", "ordinal ranks must be unique keys")
    if probability_status is ProbabilityStatus.UNKNOWN and ordinal_path_ranks:
        return _error(
            "PROBABILITY_STATUS_UNKNOWN_HAS_RANKS",
            "UNKNOWN probability state cannot claim ordinal ranking",
        )
    if probability_status is ProbabilityStatus.ORDINAL_ONLY and rank_map:
        rankable = set(REQUIRED_PATHS) - {PathKind.UNKNOWN}
        if set(rank_map) != rankable:
            return _error(
                "ORDINAL_PATH_RANK_INCOMPLETE",
                "ordinal ranks must cover known paths while preserving UNKNOWN",
            )
    materialized_cells: list[PathPayoffCell] = []
    for cell in sorted(cells, key=lambda item: (item.path.value, item.action_plan_ref)):
        calculated_cell_digest = canonical_digest(
            {
                "path": cell.path.value,
                "action": cell.action_plan_ref,
                "intermediate_states": cell.intermediate_state_refs,
                "continuation_actions": cell.continuation_action_refs,
                "triggered_stages": cell.triggered_stage_refs,
                "fill_outcome_ref": cell.fill_outcome_ref,
                "slippage_ref": cell.slippage_ref,
                "fee_ref": cell.fee_ref,
                "funding_status_ref": cell.funding_status_ref,
                "offline_risk_ref": cell.offline_risk_ref,
                "terminal_outcome_ref": cell.terminal_outcome_ref,
                "pnl": (
                    cell.account_pnl_interval.lower,
                    cell.account_pnl_interval.upper,
                ),
                "total_risk": (
                    cell.total_account_risk.lower,
                    cell.total_account_risk.upper,
                ),
                "marginal_risk": (
                    cell.marginal_account_risk.lower,
                    cell.marginal_account_risk.upper,
                ),
                "max_drawdown": (
                    cell.max_drawdown.lower,
                    cell.max_drawdown.upper,
                ),
                "stress_loss": (
                    cell.stress_loss.lower,
                    cell.stress_loss.upper,
                ),
                "tail_loss": (
                    cell.tail_loss.lower,
                    cell.tail_loss.upper,
                ),
                "time_to_outcome_ref": cell.time_to_outcome_ref,
                "data_status": cell.data_status.value,
                "assumptions": cell.assumption_refs,
            }
        )
        if cell.cell_digest and cell.cell_digest != calculated_cell_digest:
            return _error(
                "PATH_PAYOFF_CELL_DIGEST_MISMATCH",
                "supplied payoff cell digest differs from deterministic calculation",
            )
        materialized_cells.append(
            replace(cell, cell_digest=calculated_cell_digest)
        )
    matrix_digest = canonical_digest(
        {
            "matrix_id": matrix_id,
            "episode": strategic_episode_ref,
            "revision": revision,
            "decision_cutoff": decision_cutoff.isoformat(),
            "decision_horizon_ref": decision_horizon_ref,
            "planning_context_id": planning_context_id,
            "candidate_action_set_digest": candidate_action_set_digest,
            "actions": action_plan_refs,
            "paths": tuple(path.value for path in REQUIRED_PATHS),
            "cells": tuple(cell.cell_digest for cell in materialized_cells),
            "probability_status": probability_status.value,
            "ordinal_ranks": tuple(
                (path.value, rank) for path, rank in ordinal_path_ranks
            ),
            "probability_use_authorization_ref": None,
            "forecast_coherence_receipt_ref": forecast_coherence_receipt_ref,
            "expected_value_ref": None,
            "kelly_size_ref": None,
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=PathPayoffMatrix(
            matrix_id=matrix_id,
            strategic_episode_ref=strategic_episode_ref,
            revision=revision,
            decision_cutoff=decision_cutoff,
            decision_horizon_ref=decision_horizon_ref,
            planning_context_id=planning_context_id,
            candidate_action_set_digest=candidate_action_set_digest,
            actions=action_plan_refs,
            paths=REQUIRED_PATHS,
            cells=tuple(materialized_cells),
            probability_status=probability_status,
            ordinal_path_ranks=ordinal_path_ranks,
            probability_use_authorization_ref=None,
            forecast_coherence_receipt_ref=forecast_coherence_receipt_ref,
            expected_value_ref=None,
            kelly_size_ref=None,
            matrix_digest=matrix_digest,
        ),
    )
