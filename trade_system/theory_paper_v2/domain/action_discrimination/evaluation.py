"""Outcome-only, multi-horizon diagnostics for the frozen paired experiment."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from ..contracts.canonical import canonical_decimal, canonical_digest
from .engine import (
    EQUITY,
    FEE_RATE,
    SLIPPAGE_RATE,
    PositionLot,
    project_action_lots,
    state_lots,
)
from .model import (
    E0B_FINANCIAL_CONTRACT,
    EXECUTION_AUTHORITY,
    PROFILE_BY_ID,
    SYSTEM_MODE,
    ActionDiscriminationError,
    ActionId,
    ProfileId,
)


ZERO = Decimal("0")
HORIZONS = (1, 4, 8, 24)


def _d(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ActionDiscriminationError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ActionDiscriminationError(code) from exc
    if not result.is_finite():
        raise ActionDiscriminationError(code)
    return result


def _measurement(context: Mapping[str, Any], evidence_id: str) -> Decimal:
    rows = [
        item
        for item in context.get("market_measurements", [])
        if item.get("evidence_id") == evidence_id
    ]
    if len(rows) != 1 or rows[0].get("status") != "OBSERVED":
        raise ActionDiscriminationError("OUTCOME_CONTEXT_MEASUREMENT_MISSING")
    return _d(rows[0].get("value"), "OUTCOME_CONTEXT_MEASUREMENT_INVALID")


def _profile(context: Mapping[str, Any]):
    try:
        return PROFILE_BY_ID[ProfileId(context["state"]["profile_id"])]
    except (KeyError, ValueError) as exc:
        raise ActionDiscriminationError("OUTCOME_PROFILE_INVALID") from exc


def baseline_action(context: Mapping[str, Any]) -> ActionId:
    profile_id = ProfileId(context["state"]["profile_id"])
    mapping = {
        ProfileId.FLAT_ACTIVE: ActionId.WAIT_WITH_REVIEW,
        ProfileId.CORE_ACTIVE: ActionId.HOLD_CORE,
        ProfileId.CORE_CONFIRMATION_ELIGIBLE: ActionId.HOLD_CORE,
        ProfileId.CORE_PLUS_TACTICAL: ActionId.HOLD_CORE,
        ProfileId.TARGET_REVIEW_ACTIVE: ActionId.HOLD_CORE_TRAIL,
        ProfileId.REENTRY_PENDING: ActionId.WAIT_WITH_REVIEW,
        ProfileId.RISK_BUDGET_PRESSURE: ActionId.REDUCE_TACTICAL,
        ProfileId.HARD_INVALIDATED_CONTROL: ActionId.INVALIDATE_AND_EXIT,
    }
    return mapping[profile_id]


def _simulate(
    *,
    context: Mapping[str, Any],
    action: ActionId,
    bars: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    mark = _measurement(context, "E-MARK")
    stop_new = _d(context["geometry"]["stop_new"], "OUTCOME_STOP_INVALID")
    target1 = _d(context["geometry"]["normal_target"], "OUTCOME_T1_INVALID")
    risk_per_unit = mark - stop_new
    original = state_lots(_profile(context), mark)
    post_lots, traded_notional, _ = project_action_lots(
        action, original, mark, stop_new
    )
    immediate_cost = traded_notional * (FEE_RATE + SLIPPAGE_RATE)
    e0b_contract = (
        context.get("financial_contract_version") == E0B_FINANCIAL_CONTRACT
    )
    review_obligation: Mapping[str, Any] | None = None
    if e0b_contract:
        matching_candidates = [
            row
            for row in context.get("candidate_calculations", {}).get(
                "candidate_rows", []
            )
            if row.get("action_id") == action.value
        ]
        if len(matching_candidates) != 1:
            raise ActionDiscriminationError(
                "OUTCOME_ACTION_TRANSITION_MISSING"
            )
        transition = matching_candidates[0].get(
            "action_transition_contract"
        )
        if not isinstance(transition, Mapping):
            raise ActionDiscriminationError(
                "OUTCOME_ACTION_TRANSITION_MISSING"
            )
        candidate_review = transition.get("review_obligation_after")
        if candidate_review is not None:
            if (
                not isinstance(candidate_review, Mapping)
                or candidate_review.get("status") != "OPEN"
                or candidate_review.get("review_deadline")
                != "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT"
                or candidate_review.get("execution_in_current_action")
                is not False
            ):
                raise ActionDiscriminationError(
                    "OUTCOME_REVIEW_OBLIGATION_INVALID"
                )
            review_obligation = candidate_review
        review_expected = action in {
            ActionId.WAIT_WITH_REVIEW,
            ActionId.EXIT_WITH_REENTRY,
        }
        if review_expected != (review_obligation is not None):
            raise ActionDiscriminationError(
                "OUTCOME_REVIEW_OBLIGATION_ACTION_MISMATCH"
            )
    post_by_id = {lot.lot_id: lot for lot in post_lots}
    predecision_embedded = sum(
        (lot.quantity * (mark - lot.entry) for lot in original), ZERO
    )
    modeled_historical_entry_cost = sum(
        (
            lot.quantity * lot.entry * (FEE_RATE + SLIPPAGE_RATE)
            for lot in original
        ),
        ZERO,
    )
    embedded_realized_immediately = sum(
        (
            (
                lot.quantity
                - (
                    post_by_id[lot.lot_id].quantity
                    if lot.lot_id in post_by_id
                    else ZERO
                )
            )
            * (mark - lot.entry)
            for lot in original
        ),
        ZERO,
    )
    embedded_remaining = predecision_embedded - embedded_realized_immediately
    historical_entry_cost_allocated_to_immediate_closure = sum(
        (
            (
                lot.quantity
                - (
                    post_by_id[lot.lot_id].quantity
                    if lot.lot_id in post_by_id
                    else ZERO
                )
            )
            * lot.entry
            * (FEE_RATE + SLIPPAGE_RATE)
            for lot in original
        ),
        ZERO,
    )
    historical_entry_cost_remaining = (
        modeled_historical_entry_cost
        - historical_entry_cost_allocated_to_immediate_closure
    )
    immediate_existing_close_cost = sum(
        (
            (
                lot.quantity
                - (
                    post_by_id[lot.lot_id].quantity
                    if lot.lot_id in post_by_id
                    else ZERO
                )
            )
            * mark
            * (FEE_RATE + SLIPPAGE_RATE)
            for lot in original
        ),
        ZERO,
    )
    open_lots: dict[str, PositionLot] = {lot.lot_id: lot for lot in post_lots}
    realized = ZERO
    exit_cost = ZERO
    minimum_value_change = -immediate_cost
    peak_value_change = ZERO
    maximum_peak_to_trough_drawdown = max(ZERO, immediate_cost)
    gap_through_stop_count = 0
    trail_armed = False
    trail_armed_bar_offset: int | None = None
    for bar_offset, bar in enumerate(bars, start=1):
        low = _d(bar.get("low"), "OUTCOME_BAR_LOW_INVALID")
        high = _d(bar.get("high"), "OUTCOME_BAR_HIGH_INVALID")
        if e0b_contract:
            bar_open = _d(bar.get("open"), "OUTCOME_BAR_OPEN_INVALID")
            # A gap below an already active stop occurs at the bar open and
            # therefore precedes the bar high.  It is filled at the worse open
            # reference, with the frozen fee/slippage cost added separately.
            for lot_id, lot in tuple(open_lots.items()):
                if bar_open <= lot.stop:
                    realized += lot.quantity * (bar_open - mark)
                    exit_cost += lot.quantity * bar_open * (
                        FEE_RATE + SLIPPAGE_RATE
                    )
                    del open_lots[lot_id]
                    if bar_open < lot.stop:
                        gap_through_stop_count += 1
            open_mark = realized - immediate_cost - exit_cost + sum(
                (
                    lot.quantity * (bar_open - mark)
                    for lot in open_lots.values()
                ),
                ZERO,
            )
            minimum_value_change = min(minimum_value_change, open_mark)
            maximum_peak_to_trough_drawdown = max(
                maximum_peak_to_trough_drawdown,
                peak_value_change - open_mark,
            )
            # For stops touched after the open, assume high-before-low.  This
            # is an explicit conservative OHLC upper bound on long-side
            # peak-to-trough drawdown, not a claim about tick order.
            high_mark = realized - immediate_cost - exit_cost + sum(
                (lot.quantity * (high - mark) for lot in open_lots.values()),
                ZERO,
            )
            peak_value_change = max(peak_value_change, high_mark)
            for lot_id, lot in tuple(open_lots.items()):
                if low <= lot.stop:
                    realized += lot.quantity * (lot.stop - mark)
                    exit_cost += lot.quantity * lot.stop * (
                        FEE_RATE + SLIPPAGE_RATE
                    )
                    del open_lots[lot_id]
        else:
            for lot_id, lot in tuple(open_lots.items()):
                if low <= lot.stop:
                    realized += lot.quantity * (lot.stop - mark)
                    exit_cost += lot.quantity * lot.stop * (
                        FEE_RATE + SLIPPAGE_RATE
                    )
                    del open_lots[lot_id]
        low_mark = realized - immediate_cost - exit_cost + sum(
            (lot.quantity * (low - mark) for lot in open_lots.values()),
            ZERO,
        )
        minimum_value_change = min(minimum_value_change, low_mark)
        if e0b_contract:
            maximum_peak_to_trough_drawdown = max(
                maximum_peak_to_trough_drawdown,
                peak_value_change - low_mark,
            )
        if (
            action is ActionId.HOLD_CORE_TRAIL
            and open_lots
            and not trail_armed
            and high >= target1
        ):
            trail_armed = True
            trail_armed_bar_offset = bar_offset
            for lot_id, lot in tuple(open_lots.items()):
                open_lots[lot_id] = PositionLot(
                    lot.lot_id,
                    lot.role,
                    lot.quantity,
                    lot.entry,
                    max(lot.stop, target1 - risk_per_unit),
                )
    horizon_close = _d(bars[-1].get("close"), "OUTCOME_BAR_CLOSE_INVALID")
    unrealized = sum(
        (lot.quantity * (horizon_close - mark) for lot in open_lots.values()),
        ZERO,
    )
    total_cost = immediate_cost + exit_cost
    net = realized + unrealized - total_cost
    reported_drawdown = (
        maximum_peak_to_trough_drawdown
        if e0b_contract
        else max(ZERO, -minimum_value_change)
    )
    value = {
        "action_id": action.value,
        "decision_incremental_realized_pnl": canonical_decimal(realized),
        "decision_incremental_unrealized_pnl": canonical_decimal(unrealized),
        "transaction_cost": canonical_decimal(total_cost),
        "net_account_value_change": canonical_decimal(net),
        "net_account_value_change_fraction": canonical_decimal(net / EQUITY),
        "maximum_drawdown_from_decision": canonical_decimal(reported_drawdown),
        "maximum_drawdown_fraction": canonical_decimal(
            reported_drawdown / EQUITY
        ),
        "remaining_lot_count": len(open_lots),
        "stop_triggered_lot_count": len(post_lots) - len(open_lots),
        "trailing_protection_armed": trail_armed,
        "predecision_embedded_pnl": None,
        "predecision_embedded_pnl_status": "EXCLUDED_COMMON_STATE",
    }
    if e0b_contract:
        review_dependent_action = review_obligation is not None
        review_overdue = review_dependent_action and len(bars) > 1
        value.update(
            {
                "predecision_embedded_gross_pnl": canonical_decimal(
                    predecision_embedded
                ),
                "predecision_embedded_pnl": canonical_decimal(
                    predecision_embedded
                ),
                "modeled_historical_entry_cost": canonical_decimal(
                    modeled_historical_entry_cost
                ),
                "predecision_embedded_net_pnl_after_modeled_entry_cost": (
                    canonical_decimal(
                        predecision_embedded - modeled_historical_entry_cost
                    )
                ),
                "predecision_embedded_pnl_status": (
                    "REPORTED_COMMON_NOT_INCLUDED_IN_DECISION_INCREMENTAL"
                ),
                "embedded_pnl_realized_immediately": canonical_decimal(
                    embedded_realized_immediately
                ),
                "embedded_pnl_remaining_at_decision": canonical_decimal(
                    embedded_remaining
                ),
                "historical_entry_cost_allocated_to_immediate_closure": (
                    canonical_decimal(
                        historical_entry_cost_allocated_to_immediate_closure
                    )
                ),
                "historical_entry_cost_remaining": canonical_decimal(
                    historical_entry_cost_remaining
                ),
                "embedded_net_pnl_realized_immediately": canonical_decimal(
                    embedded_realized_immediately
                    - historical_entry_cost_allocated_to_immediate_closure
                    - immediate_existing_close_cost
                ),
                "immediate_existing_close_cost": canonical_decimal(
                    immediate_existing_close_cost
                ),
                "embedded_net_pnl_remaining_at_decision": canonical_decimal(
                    embedded_remaining - historical_entry_cost_remaining
                ),
                "full_accounting_net_pnl_from_entry": canonical_decimal(
                    predecision_embedded
                    - modeled_historical_entry_cost
                    + net
                ),
                "historical_entry_cost_status": (
                    "MODELED_WITH_FROZEN_FEE_AND_SLIPPAGE_RATE_NOT_ACTUAL_FILL"
                ),
                "ohlc_order_status": "UNKNOWN",
                "trailing_policy": (
                    "OHLC_ORDER_UNKNOWN_TRAIL_EFFECTIVE_NEXT_BAR"
                ),
                "trailing_armed_bar_offset": trail_armed_bar_offset,
                "same_bar_new_trail_stop_execution": False,
                "maximum_adverse_excursion_from_decision": canonical_decimal(
                    max(ZERO, -minimum_value_change)
                ),
                "maximum_adverse_excursion_fraction": canonical_decimal(
                    max(ZERO, -minimum_value_change) / EQUITY
                ),
                "drawdown_method": (
                    "CONSERVATIVE_OHLC_GAP_AT_OPEN_THEN_HIGH_BEFORE_INTRABAR_LOW"
                ),
                "gap_through_stop_count": gap_through_stop_count,
                "stop_fill_policy": (
                    "MIN_REGISTERED_STOP_AND_BAR_OPEN_PLUS_FROZEN_EXIT_COST"
                ),
                "reentry_execution_status": (
                    "OBLIGATION_CREATED_NOT_EXECUTED_IN_ONE_STEP_EXPERIMENT"
                    if action is ActionId.EXIT_WITH_REENTRY
                    else (
                        "FROZEN_REENTRY_CORE_EXECUTED_AT_DECISION_MARK"
                        if action is ActionId.REENTER_CORE
                        else "NOT_APPLICABLE"
                    )
                ),
                "review_deadline_hours": (
                    1 if review_dependent_action else None
                ),
                "review_obligation_source": (
                    "FROZEN_ACTION_TRANSITION_CONTRACT"
                    if review_dependent_action
                    else "NOT_APPLICABLE"
                ),
                "continuation_policy": (
                    "UNMODELED_MANDATORY_REVIEW"
                    if review_overdue
                    else (
                        "WITHIN_NEXT_REVIEW_WINDOW"
                        if review_dependent_action and len(bars) == 1
                        else "OPEN_LOOP_NO_FURTHER_GENERATIVE_DECISIONS"
                    )
                ),
                "contract_horizon_status": (
                    "REVIEW_DEPENDENT_NOT_CONTRACT_COMPARABLE"
                    if review_overdue
                    else (
                        "WITHIN_REVIEW_WINDOW"
                        if review_dependent_action and len(bars) == 1
                        else "OPEN_LOOP_ACTION_EFFECT_DIAGNOSTIC"
                    )
                ),
                "contract_comparable_for_terminal_advantage": (
                    not review_overdue
                ),
            }
        )
    return value


def evaluate_case_actions(
    *,
    context: Mapping[str, Any],
    single_action_id: str,
    cluster_action_id: str,
    outcome_bars: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(outcome_bars) != 24:
        raise ActionDiscriminationError("OUTCOME_WINDOW_MUST_BE_24")
    choice = tuple(context["candidate_calculations"]["selector_choice_set"])
    if single_action_id not in choice or cluster_action_id not in choice:
        raise ActionDiscriminationError("OUTCOME_ACTION_OUTSIDE_FROZEN_CHOICE")
    baseline = baseline_action(context)
    if baseline.value not in choice:
        raise ActionDiscriminationError("FROZEN_BASELINE_OUTSIDE_CHOICE")
    rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        window = outcome_bars[:horizon]
        all_results = {
            action_id: _simulate(
                context=context,
                action=ActionId(action_id),
                bars=window,
            )
            for action_id in choice
        }
        best_action_id = max(
            choice,
            key=lambda action_id: _d(
                all_results[action_id]["net_account_value_change"],
                "OUTCOME_NET_INVALID",
            ),
        )
        best_net = _d(
            all_results[best_action_id]["net_account_value_change"],
            "OUTCOME_NET_INVALID",
        )
        arms: dict[str, Any] = {}
        for arm, action_id in (
            ("single", single_action_id),
            ("cluster", cluster_action_id),
        ):
            selected = dict(all_results[action_id])
            selected_net = _d(
                selected["net_account_value_change"], "OUTCOME_NET_INVALID"
            )
            baseline_net = _d(
                all_results[baseline.value]["net_account_value_change"],
                "OUTCOME_NET_INVALID",
            )
            selected["explicit_baseline_action_id"] = baseline.value
            selected["explicit_baseline_net_change"] = canonical_decimal(
                baseline_net
            )
            selected["relative_to_baseline"] = canonical_decimal(
                selected_net - baseline_net
            )
            selected["hindsight_best_feasible_action_id"] = best_action_id
            selected["hindsight_best_feasible_net_change"] = canonical_decimal(
                best_net
            )
            selected["opportunity_loss"] = canonical_decimal(
                best_net - selected_net
            )
            selected["opportunity_loss_not_actual_loss"] = True
            arms[arm] = selected
        rows.append(
            {
                "horizon_hours": horizon,
                "horizon_close_time_ms": outcome_bars[horizon - 1][
                    "close_time_ms"
                ],
                "arms": arms,
            }
        )
    value = {
        "schema_id": "action_case_outcome_diagnostic",
        "schema_version": "1.0.0",
        "sample_index": context["sample_index"],
        "context_digest": context["context_digest"],
        "horizons": rows,
        "future_data_used_only_after_output_freeze": True,
        "overlapping_window_inference": "DESCRIPTIVE_ONLY",
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    if context.get("financial_contract_version") == E0B_FINANCIAL_CONTRACT:
        value["schema_version"] = "2.0.0"
        value["financial_contract_version"] = E0B_FINANCIAL_CONTRACT
    value["diagnostic_digest"] = canonical_digest(value)
    return value


def terminal_result(
    *,
    run_id: str,
    manifest_digest: str,
    event_head_digest: str,
    events: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    action_disagreements = sum(
        1
        for event in events
        if event["selected_actions"]["single"]
        != event["selected_actions"]["cluster"]
    )
    beneficial = sum(
        1
        for event in events
        if event["selected_actions"]["single"]
        != event["selected_actions"]["cluster"]
        and event["cluster_arm_score"]["preoutcome_quality_score"]
        > event["single_arm_score"]["preoutcome_quality_score"]
    )
    harmful = sum(
        1
        for event in events
        if event["selected_actions"]["single"]
        != event["selected_actions"]["cluster"]
        and event["cluster_arm_score"]["preoutcome_quality_score"]
        < event["single_arm_score"]["preoutcome_quality_score"]
    )
    horizon_summary: list[dict[str, Any]] = []
    if diagnostics:
        for offset, horizon in enumerate(HORIZONS):
            row: dict[str, Any] = {"horizon_hours": horizon}
            for arm in ("single", "cluster"):
                totals = {
                    field: sum(
                        (
                            _d(
                                item["horizons"][offset]["arms"][arm][field],
                                "RESULT_FIELD_INVALID",
                            )
                            for item in diagnostics
                        ),
                        ZERO,
                    )
                    for field in (
                        "decision_incremental_realized_pnl",
                        "decision_incremental_unrealized_pnl",
                        "transaction_cost",
                        "net_account_value_change",
                        "opportunity_loss",
                    )
                }
                row[arm] = {
                    key: canonical_decimal(value) for key, value in totals.items()
                }
                row[arm]["opportunity_loss_not_actual_loss"] = True
                row[arm]["maximum_case_drawdown_fraction"] = canonical_decimal(
                    max(
                        _d(
                            item["horizons"][offset]["arms"][arm][
                                "maximum_drawdown_fraction"
                            ],
                            "RESULT_DD_INVALID",
                        )
                        for item in diagnostics
                    )
                )
            case_deltas = [
                _d(
                    item["horizons"][offset]["arms"]["cluster"][
                        "net_account_value_change"
                    ],
                    "RESULT_NET_INVALID",
                )
                - _d(
                    item["horizons"][offset]["arms"]["single"][
                        "net_account_value_change"
                    ],
                    "RESULT_NET_INVALID",
                )
                for item in diagnostics
            ]
            row["paired_case_net_comparison"] = {
                "cluster_wins": sum(1 for delta in case_deltas if delta > ZERO),
                "ties": sum(1 for delta in case_deltas if delta == ZERO),
                "single_wins": sum(1 for delta in case_deltas if delta < ZERO),
                "cluster_minus_single_net": canonical_decimal(
                    sum(case_deltas, ZERO)
                ),
            }
            horizon_summary.append(row)
    quality_delta = sum(
        int(event["cluster_arm_score"]["preoutcome_quality_score"])
        - int(event["single_arm_score"]["preoutcome_quality_score"])
        for event in events
    )
    e0b_contract = bool(diagnostics) and all(
        item.get("financial_contract_version") == E0B_FINANCIAL_CONTRACT
        for item in diagnostics
    )
    sequentially_incomparable_disagreements: set[int] = set()
    if e0b_contract:
        event_by_sample = {
            int(event.get("sample_index", offset)): event
            for offset, event in enumerate(events)
        }
        for diagnostic in diagnostics:
            sample_index = int(diagnostic.get("sample_index", -1))
            event = event_by_sample.get(sample_index)
            if not event or (
                event["selected_actions"]["single"]
                == event["selected_actions"]["cluster"]
            ):
                continue
            if any(
                row.get("horizon_hours", 0) > 1
                and any(
                    row["arms"][arm].get(
                        "contract_comparable_for_terminal_advantage"
                    )
                    is not True
                    for arm in ("single", "cluster")
                )
                for row in diagnostic["horizons"]
            ):
                sequentially_incomparable_disagreements.add(sample_index)
    if len(events) != 32 or len(diagnostics) != 32:
        verdict = "INCOMPLETE_NO_DECISION"
    elif action_disagreements == 0:
        verdict = "NO_ACTION_DISCRIMINATION"
    elif e0b_contract and sequentially_incomparable_disagreements:
        verdict = "INCONCLUSIVE_SEQUENTIAL_CONTRACT_NOT_PROVEN"
    elif e0b_contract:
        cluster_net_dominates = all(
            _d(row["cluster"]["net_account_value_change"], "RESULT_NET_INVALID")
            >= _d(row["single"]["net_account_value_change"], "RESULT_NET_INVALID")
            for row in horizon_summary
        ) and any(
            _d(row["cluster"]["net_account_value_change"], "RESULT_NET_INVALID")
            > _d(row["single"]["net_account_value_change"], "RESULT_NET_INVALID")
            for row in horizon_summary
        )
        single_net_dominates = all(
            _d(row["single"]["net_account_value_change"], "RESULT_NET_INVALID")
            >= _d(row["cluster"]["net_account_value_change"], "RESULT_NET_INVALID")
            for row in horizon_summary
        ) and any(
            _d(row["single"]["net_account_value_change"], "RESULT_NET_INVALID")
            > _d(row["cluster"]["net_account_value_change"], "RESULT_NET_INVALID")
            for row in horizon_summary
        )
        max_dd_single = max(
            _d(row["single"]["maximum_case_drawdown_fraction"], "RESULT_DD_INVALID")
            for row in horizon_summary
        )
        max_dd_cluster = max(
            _d(row["cluster"]["maximum_case_drawdown_fraction"], "RESULT_DD_INVALID")
            for row in horizon_summary
        )
        if (
            cluster_net_dominates
            and max_dd_cluster - max_dd_single <= Decimal("0.0025")
        ):
            verdict = "DESCRIPTIVE_CLUSTER_SELECTION_ADVANTAGE"
        elif (
            single_net_dominates
            and max_dd_single - max_dd_cluster <= Decimal("0.0025")
        ):
            verdict = "DESCRIPTIVE_SINGLE_SELECTION_ADVANTAGE"
        else:
            verdict = "INCONCLUSIVE_ACTION_TRADEOFF"
    else:
        one_hour_single = _d(
            horizon_summary[0]["single"]["net_account_value_change"],
            "RESULT_NET_INVALID",
        )
        one_hour_cluster = _d(
            horizon_summary[0]["cluster"]["net_account_value_change"],
            "RESULT_NET_INVALID",
        )
        max_dd_single = max(
            _d(row["single"]["maximum_case_drawdown_fraction"], "RESULT_DD_INVALID")
            for row in horizon_summary
        )
        max_dd_cluster = max(
            _d(row["cluster"]["maximum_case_drawdown_fraction"], "RESULT_DD_INVALID")
            for row in horizon_summary
        )
        if (
            beneficial > harmful
            and quality_delta > 0
            and one_hour_cluster >= one_hour_single
            and max_dd_cluster - max_dd_single <= Decimal("0.0025")
        ):
            verdict = "PRACTICAL_CLUSTER_ACTION_BENEFIT"
        elif (
            harmful > beneficial
            and quality_delta < 0
            and one_hour_single >= one_hour_cluster
            and max_dd_single - max_dd_cluster <= Decimal("0.0025")
        ):
            verdict = "PRACTICAL_SINGLE_ACTION_BENEFIT"
        else:
            verdict = "INCONCLUSIVE_ACTION_TRADEOFF"
    value = {
        "schema_id": "action_experiment_result",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "manifest_digest": manifest_digest,
        "event_head_digest": event_head_digest,
        "completed_case_count": len(events),
        "hard_safety_error_count": 0,
        "terminal_verdict": verdict,
        "primary_kpis": {
            "paired_preoutcome_action_quality_delta": quality_delta,
            "paired_action_disagreement_count": action_disagreements,
            "paired_action_disagreement_rate": canonical_decimal(
                Decimal(action_disagreements) / Decimal(len(events))
                if events
                else ZERO
            ),
            "beneficial_intervention_count": beneficial,
            "harmful_intervention_count": harmful,
            "beneficial_intervention_balance": beneficial - harmful,
        },
        "horizon_summary": horizon_summary,
        "claims": {
            "predictive_validity_proven": False,
            "profitability_proven": False,
            "production_ready": False,
            "paper_or_live_authorized": False,
            "economic_diagnostics_descriptive_only": True,
        },
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    if e0b_contract:
        value["schema_version"] = "2.0.0"
        value["financial_contract_version"] = E0B_FINANCIAL_CONTRACT
        value["primary_kpis"] = {
            "paired_action_disagreement_count": action_disagreements,
            "paired_action_disagreement_rate": canonical_decimal(
                Decimal(action_disagreements) / Decimal(len(events))
                if events
                else ZERO
            ),
            "preoutcome_quality_delta_diagnostic_only": quality_delta,
            "challenge_coverage_value_status": (
                "DIAGNOSTIC_NOT_ACTION_BENEFIT"
            ),
            "beneficial_intervention_count": None,
            "harmful_intervention_count": None,
            "beneficial_intervention_status": (
                "NOT_INFERRED_FROM_LANGUAGE_CHECKLIST"
            ),
            "multi_horizon_rule": (
                "ALL_1_4_8_24_NET_VECTOR_DOMINANCE_WITH_DD_GUARDRAIL"
            ),
            "sequentially_incomparable_disagreement_count": len(
                sequentially_incomparable_disagreements
            ),
            "sequentially_incomparable_sample_indices": sorted(
                sequentially_incomparable_disagreements
            ),
            "opportunity_loss_promotion_status": (
                "ALGEBRAIC_MIRROR_REPORTED_NOT_INDEPENDENT_GATE"
            ),
        }
        value["claims"]["same_bundle_generalization_proven"] = False
        value["claims"]["sequential_reentry_fulfilment_proven"] = False
    value["result_digest"] = canonical_digest(value)
    return value


__all__ = [
    "HORIZONS",
    "baseline_action",
    "evaluate_case_actions",
    "terminal_result",
]
