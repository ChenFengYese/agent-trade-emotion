from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from trade_system.theory_paper_v2.domain.behavior_planning import (
    ActionCandidate,
    ActionEvaluation,
    ActionType,
    BehaviorPlanningError,
    PortfolioDecisionContext,
    PositionSide,
    PositionRole,
    action_evaluations_from_financial_receipt,
    legal_action_types,
    legal_action_keys,
    seal_action_selection,
    seal_complete_action_evaluation,
)
from trade_system.theory_paper_v2.domain.financial_evaluation import (
    build_financial_evaluation_receipt,
    build_financial_risk_policy,
)
from trade_system.theory_paper_v2.domain.portfolio_truth import (
    PortfolioTruthError,
    build_lot_position_truth,
)
from trade_system.theory_paper_v2.domain.probability_cloud import ProbabilityMode
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest


DECISION_AT = "2026-08-06T10:00:00Z"
SYMBOL = "BTCUSDT"
RISK_POLICY = {
    "fee_rate": "0.001",
    "slippage_rate": "0.002",
    "initial_margin_rate": "0.5",
    "max_gross_leverage": "2",
    "portfolio_risk_cap_usdt": "500",
    "symbol_risk_cap_usdt": "300",
    "gross_notional_cap_usdt": "5000",
    "symbol_notional_cap_usdt": "3000",
}


def raw_position_truth(side: PositionSide) -> dict[str, object]:
    intended = side.value
    if side is PositionSide.FLAT:
        lots = []
        margin_used = Decimal("0")
    else:
        stop = "110" if side is PositionSide.SHORT else "90"
        lots = [
            {
                "lot_id": "lot-1",
                "symbol": SYMBOL,
                "side": intended,
                "role": "CORE",
                "quantity": "1",
                "entry_price": "100",
                "mark_price": "100",
                "stop_price": stop,
                "contract_multiplier": "1",
                "margin_used_usdt": "50",
            },
            {
                "lot_id": "lot-2",
                "symbol": SYMBOL,
                "side": intended,
                "role": "TACTICAL",
                "quantity": "1",
                "entry_price": "100",
                "mark_price": "100",
                "stop_price": stop,
                "contract_multiplier": "1",
                "margin_used_usdt": "50",
            },
        ]
        margin_used = Decimal("100")
    return {
        "intended_side": intended,
        "mark_price": "100",
        "contract_multiplier": "1",
        "reentry_contract_active": False,
        "account": {
            "equity_usdt": "2000",
            "margin_used_usdt": str(margin_used),
            "margin_available_usdt": str(Decimal("2000") - margin_used),
            "max_gross_leverage": "2",
        },
        "lots": lots,
        "pending_orders": [],
    }


def market_economics() -> dict[str, str]:
    return {
        "symbol": SYMBOL,
        "available_at": DECISION_AT,
        "mark_price": "100",
        "contract_multiplier": "1",
        "contract_size_multiplier": "1",
        "quantity_step_contracts": "0.01",
        "minimum_quantity_contracts": "0.01",
        "price_tick_usdt": "0.1",
        "long_protective_stop_price": "90",
        "short_protective_stop_price": "110",
    }


def context(
    *,
    side: PositionSide = PositionSide.FLAT,
    probability_mode: ProbabilityMode = ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
) -> PortfolioDecisionContext:
    position_digest = build_lot_position_truth(
        symbol=SYMBOL, position_truth=raw_position_truth(side)
    )["position_truth_digest"]
    risk_digest = build_financial_risk_policy(RISK_POLICY)["risk_policy_digest"]
    return PortfolioDecisionContext(
        decision_at=DECISION_AT,
        position_side=side,
        lot_ids=() if side is PositionSide.FLAT else ("lot-1", "lot-2"),
        pending_reentry_side=None,
        portfolio_truth_digest=position_digest,
        risk_policy_digest=risk_digest,
        probability_mode=probability_mode,
        probability_cloud_digest="c" * 64,
        calibration_receipt_digests=(
            ("d" * 64,) if probability_mode is ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION else ()
        ),
        proper_scoring_receipt_digests=(
            ("e" * 64,) if probability_mode is ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION else ()
        ),
        oos_evaluation_receipt_digests=(
            ("f" * 64,) if probability_mode is ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION else ()
        ),
    )


FIXED_SCALES = {
    ActionType.ADD_25: 25,
    ActionType.ADD_50: 50,
    ActionType.ADD_75: 75,
    ActionType.ADD_100: 100,
    ActionType.REDUCE_25: 25,
    ActionType.REDUCE_50: 50,
    ActionType.REDUCE_75: 75,
    ActionType.EXIT_100: 100,
}


def candidate(
    action: ActionType,
    ctx: PortfolioDecisionContext,
    *,
    scale: int | None = None,
    target_lot_ids: tuple[str, ...] | None = None,
    target_role: PositionRole | None = None,
) -> ActionCandidate:
    if scale is None:
        if action in {ActionType.OPEN_LONG, ActionType.OPEN_SHORT}:
            scale = 25
        elif action in {ActionType.REENTER_LONG, ActionType.REENTER_SHORT}:
            scale = 25
        elif action is ActionType.PARTIAL_EXIT:
            scale = 40
        else:
            scale = FIXED_SCALES.get(action)
    if target_role is None and action in {
        ActionType.OPEN_LONG,
        ActionType.OPEN_SHORT,
        ActionType.REENTER_LONG,
        ActionType.REENTER_SHORT,
        ActionType.ADD_25,
        ActionType.ADD_50,
        ActionType.ADD_75,
        ActionType.ADD_100,
    }:
        target_role = PositionRole.CORE
    wait = action is ActionType.WAIT
    if target_lot_ids is None:
        target_lot_ids = (
            ctx.lot_ids
            if ctx.position_side is not PositionSide.FLAT
            and not wait
            and not action.value.startswith("ADD_")
            else ()
        )
    return ActionCandidate(
        candidate_id=(
            f"candidate-{action.value.lower()}-{scale or 'none'}-"
            f"{target_role.value.lower() if target_role else 'none'}-"
            f"{'_'.join(target_lot_ids) if target_lot_ids else 'no-lot'}"
        ),
        action=action,
        target_lot_ids=target_lot_ids,
        scale_pct=scale,
        target_role=target_role,
        trigger_conditions=("path and risk gate remain satisfied",),
        invalidation_conditions=("path falsifier becomes true",),
        path_refs=("path-a",),
        evidence_refs=("dataset-digest",),
        risk_refs=("risk-policy",),
        thesis="A non-executable candidate for complete comparison.",
        wait_reason="Evidence remains uncalibrated." if wait else None,
        opportunity_cost="A move may start before confirmation." if wait else None,
        next_observation="Observe the next closed bar." if wait else None,
        next_review_at="2026-08-06T11:00:00Z" if wait else None,
        information_not_arrived_default=(
            "Keep the current non-executable state and preserve UNKNOWN." if wait else None
        ),
        position_protection_responsibility=(
            "Maintain existing deterministic stops and risk limits." if wait else None
        ),
    )


def candidates(ctx: PortfolioDecisionContext) -> tuple[ActionCandidate, ...]:
    return tuple(
        candidate(
            key.action,
            ctx,
            scale=key.scale_pct,
            target_lot_ids=key.target_lot_ids,
            target_role=key.target_role,
        )
        for key in legal_action_keys(ctx)
    )


def financial_artifacts(
    ctx: PortfolioDecisionContext,
    rows: tuple[ActionCandidate, ...],
) -> tuple[dict[str, object], tuple[ActionEvaluation, ...]]:
    receipt = build_financial_evaluation_receipt(
        run_id="v31-run",
        cycle_index=1,
        decision_at=ctx.decision_at,
        evaluated_at="2026-08-06T10:01:00Z",
        symbol=SYMBOL,
        position_truth=raw_position_truth(ctx.position_side),
        risk_policy=RISK_POLICY,
        market_economics=market_economics(),
        probability_mode=ctx.probability_mode,
        probability_cloud_digest=ctx.probability_cloud_digest,
        calibration_receipt_digests=ctx.calibration_receipt_digests,
        proper_scoring_receipt_digests=ctx.proper_scoring_receipt_digests,
        oos_evaluation_receipt_digests=ctx.oos_evaluation_receipt_digests,
        candidates=tuple(row.to_document() for row in rows),
    )
    return receipt, action_evaluations_from_financial_receipt(
        financial_evaluation_receipt=receipt,
        candidates=rows,
    )


def sealed(ctx: PortfolioDecisionContext) -> dict[str, object]:
    rows = candidates(ctx)
    receipt, evaluations = financial_artifacts(ctx, rows)
    return seal_complete_action_evaluation(
        run_id="v31-run",
        cycle_index=1,
        context=ctx,
        candidates=rows,
        evaluations=evaluations,
        financial_evaluation_receipt=receipt,
        evaluated_at="2026-08-06T10:01:00Z",
    )


class BehaviorPlanningTests(unittest.TestCase):
    def test_flat_truth_is_explicit_and_forbids_target_exposure(self) -> None:
        raw_flat = raw_position_truth(PositionSide.FLAT)
        flat = build_lot_position_truth(
            symbol=SYMBOL, position_truth=raw_flat
        )
        self.assertEqual("FLAT", flat["intended_side"])
        self.assertEqual("0", flat["target_symbol"]["current_quantity"])
        self.assertEqual([], flat["lots"])
        self.assertEqual([], flat["pending_orders"])

        flat_with_lot = raw_position_truth(PositionSide.LONG)
        flat_with_lot["intended_side"] = "FLAT"
        with self.assertRaisesRegex(
            PortfolioTruthError, "PORTFOLIO_FLAT_TARGET_LOT_FORBIDDEN"
        ):
            build_lot_position_truth(
                symbol=SYMBOL, position_truth=flat_with_lot
            )

        flat_with_order = raw_position_truth(PositionSide.FLAT)
        flat_with_order["account"] = {
            **flat_with_order["account"],
            "margin_used_usdt": "50",
            "margin_available_usdt": "1950",
        }
        flat_with_order["pending_orders"] = [
            {
                "order_id": "pending-open",
                "symbol": SYMBOL,
                "side": "LONG",
                "intent": "OPEN",
                "quantity": "1",
                "reference_price": "100",
                "stop_price": "90",
                "contract_multiplier": "1",
                "reduce_only": False,
                "target_lot_ids": [],
                "reserved_margin_usdt": "50",
            }
        ]
        with self.assertRaisesRegex(
            PortfolioTruthError, "PORTFOLIO_FLAT_TARGET_ORDER_FORBIDDEN"
        ):
            build_lot_position_truth(
                symbol=SYMBOL, position_truth=flat_with_order
            )

    def test_flat_position_does_not_allow_flat_lot_or_order_sides(self) -> None:
        flat_with_bad_lot = raw_position_truth(PositionSide.LONG)
        flat_with_bad_lot["intended_side"] = "FLAT"
        for row in flat_with_bad_lot["lots"]:
            row["symbol"] = "OTHER"
        flat_with_bad_lot["lots"][0]["side"] = "FLAT"
        with self.assertRaisesRegex(
            PortfolioTruthError, "PORTFOLIO_LOT_IDENTITY_INVALID"
        ):
            build_lot_position_truth(
                symbol=SYMBOL, position_truth=flat_with_bad_lot
            )

        flat_with_bad_order = raw_position_truth(PositionSide.FLAT)
        flat_with_bad_order["pending_orders"] = [
            {
                "order_id": "invalid-flat-side",
                "symbol": "OTHER",
                "side": "FLAT",
                "intent": "OPEN",
                "quantity": "1",
                "reference_price": "100",
                "stop_price": "90",
                "contract_multiplier": "1",
                "reduce_only": False,
                "target_lot_ids": [],
                "reserved_margin_usdt": "0",
            }
        ]
        with self.assertRaisesRegex(
            PortfolioTruthError, "PORTFOLIO_ORDER_IDENTITY_INVALID"
        ):
            build_lot_position_truth(
                symbol=SYMBOL, position_truth=flat_with_bad_order
            )

    def test_flat_behavior_context_rejects_fake_long_empty_truth(self) -> None:
        fake_raw = raw_position_truth(PositionSide.FLAT)
        fake_raw["intended_side"] = "LONG"
        fake_truth = build_lot_position_truth(
            symbol=SYMBOL, position_truth=fake_raw
        )
        fake_context = replace(
            context(),
            portfolio_truth_digest=fake_truth["position_truth_digest"],
        )
        rows = candidates(fake_context)
        receipt = build_financial_evaluation_receipt(
            run_id="v31-run",
            cycle_index=1,
            decision_at=fake_context.decision_at,
            evaluated_at="2026-08-06T10:01:00Z",
            symbol=SYMBOL,
            position_truth=fake_raw,
            risk_policy=RISK_POLICY,
            market_economics=market_economics(),
            probability_mode=fake_context.probability_mode,
            probability_cloud_digest=fake_context.probability_cloud_digest,
            calibration_receipt_digests=(),
            proper_scoring_receipt_digests=(),
            oos_evaluation_receipt_digests=(),
            candidates=tuple(row.to_document() for row in rows),
        )
        evaluations = action_evaluations_from_financial_receipt(
            financial_evaluation_receipt=receipt,
            candidates=rows,
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError,
            "BEHAVIOR_FINANCIAL_POSITION_BINDING_INVALID",
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=fake_context,
                candidates=rows,
                evaluations=evaluations,
                financial_evaluation_receipt=receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )

    def test_flat_and_positioned_legal_sets_are_complete_and_distinct(self) -> None:
        self.assertEqual(
            (ActionType.WAIT, ActionType.OPEN_LONG, ActionType.OPEN_SHORT),
            legal_action_types(context()),
        )
        positioned = legal_action_types(context(side=PositionSide.LONG))
        self.assertIn(ActionType.HOLD, positioned)
        self.assertIn(ActionType.ADD_100, positioned)
        self.assertIn(ActionType.PARTIAL_EXIT, positioned)
        self.assertIn(ActionType.EXIT_100, positioned)
        self.assertIn(ActionType.WAIT, positioned)
        self.assertNotIn(ActionType.OPEN_SHORT, positioned)

    def test_complete_evaluation_has_no_selection_or_execution_authority(self) -> None:
        document = sealed(context())
        self.assertFalse(document["selection_present"])
        self.assertFalse(document["executable"])
        self.assertEqual("NONE_LOCAL_SIMULATION", document["external_execution_authority"])
        self.assertEqual(64, len(document["action_evaluation_digest"]))

    def test_incomplete_or_duplicate_legal_action_set_fails_closed(self) -> None:
        ctx = context()
        rows = candidates(ctx)
        receipt, evaluations = financial_artifacts(ctx, rows)
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_LEGAL_ACTION_SET_INCOMPLETE"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=rows[:-1],
                evaluations=evaluations[:-1],
                financial_evaluation_receipt=receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )
        duplicate = replace(rows[0], candidate_id="duplicate-wait")
        duplicate_evaluation = replace(
            evaluations[0], candidate_id="duplicate-wait"
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_LEGAL_ACTION_SET_INCOMPLETE"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=rows + (duplicate,),
                evaluations=evaluations + (duplicate_evaluation,),
                financial_evaluation_receipt=receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )

    def test_wait_obligations_and_exact_variable_scales_are_required(self) -> None:
        ctx = context()
        wait = candidate(ActionType.WAIT, ctx)
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_WAIT_OBLIGATIONS_REQUIRED"
        ):
            replace(wait, opportunity_cost=None)
        open_long = candidate(ActionType.OPEN_LONG, ctx)
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_VARIABLE_ACTION_SCALE_INVALID"
        ):
            replace(open_long, scale_pct=None)
        partial = candidate(ActionType.PARTIAL_EXIT, context(side=PositionSide.LONG))
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_VARIABLE_ACTION_SCALE_INVALID"
        ):
            replace(partial, scale_pct=100)

    def test_positioned_actions_bind_real_lots(self) -> None:
        ctx = context(side=PositionSide.LONG)
        rows = candidates(ctx)
        receipt, evaluations = financial_artifacts(ctx, rows)
        broken = tuple(
            replace(row, target_lot_ids=()) if row.action is ActionType.HOLD else row
            for row in rows
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_LEGAL_ACTION_SET_INCOMPLETE"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=broken,
                evaluations=evaluations,
                financial_evaluation_receipt=receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )

    def test_uncalibrated_and_calibrated_modes_cannot_invent_ev_without_payoffs(self) -> None:
        subjective = context()
        rows = candidates(subjective)
        receipt, evaluations = financial_artifacts(subjective, rows)
        forged = tuple(
            replace(
                row,
                expected_value_lower_usdt="-3",
                expected_value_upper_usdt="-3",
                expected_value_usdt="-3",
            )
            for row in evaluations
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_UNCALIBRATED_EXPECTED_VALUE_FORBIDDEN"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=subjective,
                candidates=rows,
                evaluations=forged,
                financial_evaluation_receipt=receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )
        calibrated = context(
            probability_mode=ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION
        )
        calibrated_rows = candidates(calibrated)
        calibrated_receipt, calibrated_evaluations = financial_artifacts(
            calibrated, calibrated_rows
        )
        document = seal_complete_action_evaluation(
            run_id="v31-run",
            cycle_index=1,
            context=calibrated,
            candidates=calibrated_rows,
            evaluations=calibrated_evaluations,
            financial_evaluation_receipt=calibrated_receipt,
            evaluated_at="2026-08-06T10:01:00Z",
        )
        self.assertIsNone(document["evaluations"][0]["expected_value_usdt"])
        self.assertIsNone(document["evaluations"][0]["expected_value_lower_usdt"])
        self.assertIsNone(document["evaluations"][0]["expected_value_upper_usdt"])
        self.assertIsNone(document["evaluations"][0]["maximum_regret_usdt"])
        self.assertEqual(
            "ABSENT_NO_NUMERIC_EV_OR_REGRET",
            calibrated_receipt["payoff_matrix_status"],
        )

    def test_financial_fields_are_recomputed_and_semantic_rehash_fails(self) -> None:
        ctx = context()
        rows = candidates(ctx)
        receipt, evaluations = financial_artifacts(ctx, rows)
        forged = list(evaluations)
        forged[0] = replace(
            forged[0],
            feasible=False,
            infeasible_reasons=("CALLER_INVENTED_VETO",),
            transaction_cost_usdt="999",
            worst_case_loss_usdt="999",
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_FINANCIAL_EVALUATION_MISMATCH"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=rows,
                evaluations=tuple(forged),
                financial_evaluation_receipt=receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )
        rehashed = self_digest(
            {
                key: value
                for key, value in receipt.items()
                if key != "financial_evaluation_receipt_digest"
            }
            | {
                "evaluations": [
                    ({**row, "transaction_cost_usdt": "999"} if index == 0 else row)
                    for index, row in enumerate(receipt["evaluations"])
                ]
            },
            "financial_evaluation_receipt_digest",
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_FINANCIAL_RECEIPT_INVALID"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=rows,
                evaluations=evaluations,
                financial_evaluation_receipt=rehashed,
                evaluated_at="2026-08-06T10:01:00Z",
            )

    def test_open_economics_are_derived_and_zero_value_poc_fails(self) -> None:
        ctx = context()
        rows = candidates(ctx)
        receipt, evaluations = financial_artifacts(ctx, rows)
        open_rows = [
            row
            for row in receipt["evaluations"]
            if row["candidate_id"].startswith("candidate-open_")
        ]
        self.assertTrue(open_rows)
        for row in open_rows:
            self.assertNotEqual("0", row["economics"]["quantity_delta"])
            self.assertNotEqual("0", row["economics"]["turnover_notional_usdt"])
            self.assertNotEqual("0", row["economics"]["symbol_risk_after_usdt"])
            self.assertNotEqual("0", row["economics"]["margin_used_after_usdt"])
        forged_evaluations = []
        for row in receipt["evaluations"]:
            if row["candidate_id"].startswith("candidate-open_"):
                economics = dict(row["economics"])
                for field in (
                    "quantity_delta",
                    "turnover_notional_usdt",
                    "symbol_risk_after_usdt",
                    "portfolio_risk_after_usdt",
                    "margin_used_after_usdt",
                ):
                    economics[field] = "0"
                row = {
                    **row,
                    "transaction_cost_usdt": "0",
                    "liquidity_cost_usdt": "0",
                    "worst_case_loss_usdt": "0",
                    "economics": economics,
                }
            forged_evaluations.append(row)
        forged_receipt = self_digest(
            {
                key: value
                for key, value in receipt.items()
                if key != "financial_evaluation_receipt_digest"
            }
            | {"evaluations": forged_evaluations},
            "financial_evaluation_receipt_digest",
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_FINANCIAL_RECEIPT_INVALID"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=rows,
                evaluations=evaluations,
                financial_evaluation_receipt=forged_receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )

    def test_digest_string_cannot_impersonate_loaded_financial_receipt(self) -> None:
        ctx = context()
        rows = candidates(ctx)
        receipt, evaluations = financial_artifacts(ctx, rows)
        self.assertEqual(64, len(receipt["financial_evaluation_receipt_digest"]))
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_FINANCIAL_RECEIPT_INVALID"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=rows,
                evaluations=evaluations,
                financial_evaluation_receipt={
                    "financial_evaluation_receipt_digest": "8" * 64
                },
                evaluated_at="2026-08-06T10:01:00Z",
            )

    def test_selection_requires_untampered_complete_evaluation_and_explains_all(self) -> None:
        evaluation_set = sealed(context())
        selected = next(
            row["candidate_id"]
            for row in evaluation_set["candidates"]
            if row["action"] == ActionType.WAIT.value
        )
        alternatives = {
            row["candidate_id"]: "Rejected after cost, uncertainty, and path comparison."
            for row in evaluation_set["candidates"]
            if row["candidate_id"] != selected
        }
        selection = seal_action_selection(
            evaluation=evaluation_set,
            selected_candidate_id=selected,
            reason="WAIT preserves reversibility while evidence is uncalibrated.",
            alternative_explanations=alternatives,
            failure_conditions=("new data invalidate the wait thesis",),
            next_review_at="2026-08-06T11:00:00Z",
            selected_at="2026-08-06T10:02:00Z",
        )
        self.assertEqual("WAIT", selection["selected_action"])
        self.assertFalse(selection["executable"])
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_ALTERNATIVE_EXPLANATIONS_INCOMPLETE"
        ):
            seal_action_selection(
                evaluation=evaluation_set,
                selected_candidate_id=selected,
                reason="incomplete comparison",
                alternative_explanations={},
                failure_conditions=("failure",),
                next_review_at="2026-08-06T11:00:00Z",
                selected_at="2026-08-06T10:02:00Z",
            )

    def test_rehashed_incomplete_evaluation_and_early_wait_review_are_rejected(self) -> None:
        evaluation_set = sealed(context())
        wait_candidate = next(
            row
            for row in evaluation_set["candidates"]
            if row["action"] == ActionType.WAIT.value
        )
        wait_evaluation = next(
            row
            for row in evaluation_set["evaluations"]
            if row["candidate_id"] == wait_candidate["candidate_id"]
        )
        incomplete = self_digest(
            {
                key: value
                for key, value in evaluation_set.items()
                if key != "action_evaluation_digest"
            }
            | {
                "candidates": [wait_candidate],
                "evaluations": [wait_evaluation],
            },
            "action_evaluation_digest",
        )
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_SELECTION_REQUIRES_SEALED_EVALUATION"
        ):
            seal_action_selection(
                evaluation=incomplete,
                selected_candidate_id=wait_candidate["candidate_id"],
                reason="incomplete but rehashed",
                alternative_explanations={},
                failure_conditions=("failure",),
                next_review_at="2026-08-06T11:00:00Z",
                selected_at="2026-08-06T10:02:00Z",
            )
        ctx = context()
        rows = tuple(
            replace(row, next_review_at="2026-08-06T09:59:00Z")
            if row.action is ActionType.WAIT
            else row
            for row in candidates(ctx)
        )
        original_rows = candidates(ctx)
        receipt, evaluations = financial_artifacts(ctx, original_rows)
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_WAIT_REVIEW_PRECEDES_DECISION"
        ):
            seal_complete_action_evaluation(
                run_id="v31-run",
                cycle_index=1,
                context=ctx,
                candidates=rows,
                evaluations=evaluations,
                financial_evaluation_receipt=receipt,
                evaluated_at="2026-08-06T10:01:00Z",
            )
        tampered = dict(evaluation_set)
        tampered["probability_mode"] = "CALIBRATED_PREDICTIVE_DISTRIBUTION"
        alternatives = {
            row["candidate_id"]: "Rejected after complete comparison."
            for row in evaluation_set["candidates"]
            if row["candidate_id"] != wait_candidate["candidate_id"]
        }
        with self.assertRaisesRegex(
            BehaviorPlanningError, "BEHAVIOR_SELECTION_REQUIRES_SEALED_EVALUATION"
        ):
            seal_action_selection(
                evaluation=tampered,
                selected_candidate_id=wait_candidate["candidate_id"],
                reason="tampered",
                alternative_explanations=alternatives,
                failure_conditions=("failure",),
                next_review_at="2026-08-06T11:00:00Z",
                selected_at="2026-08-06T10:02:00Z",
            )


if __name__ == "__main__":
    unittest.main()
