from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_system.theory_paper_v2.domain.common import ReducerStatus
from trade_system.theory_paper_v2.domain.position import (
    EpisodeRiskBudget,
    GateVerdict,
    LotRole,
    RiskTransitionKind,
    StageEvaluation,
    StageKind,
    StageSpec,
    StageState,
    StageStatus,
    SupervisionContract,
    SupervisionMode,
    SupervisionWindow,
    apply_risk_transition,
    assess_supervision,
    reduce_stage,
)
from trade_system.theory_paper_v2.domain.strategic import StrategicStatus


class PositionDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 1, tzinfo=UTC)
        self.budget = EpisodeRiskBudget(
            budget_id="b1",
            episode_id="e1",
            revision=1,
            account_cap=Decimal("0.02"),
            episode_cap=Decimal("0.01"),
            core_cap=Decimal("0.006"),
            tactical_cap=Decimal("0.004"),
            hedge_cap=Decimal("0"),
            realized_loss=Decimal("0"),
            realized_cost=Decimal("0"),
            open_risk=Decimal("0"),
            pending_risk=Decimal("0"),
            reserved_stage_risk=Decimal("0"),
            tail_reserve=Decimal("0.001"),
            stage_reservations=(),
        )
        self.spec = StageSpec(
            stage_id="s1",
            plan_id="p1",
            stage_index=0,
            stage_kind=StageKind.INITIAL,
            lot_role=LotRole.CORE,
            predecessor_stage_id=None,
            expiry=self.now + timedelta(hours=4),
            maximum_retries=1,
            frozen_before_first_fill=True,
        )

    def test_risk_moves_without_creating_capacity(self) -> None:
        reserved = apply_risk_transition(
            self.budget,
            kind=RiskTransitionKind.RESERVE_STAGE,
            amount=Decimal("0.003"),
            next_budget_id="b2",
            stage_id="s1",
        ).value
        pending = apply_risk_transition(
            reserved,
            kind=RiskTransitionKind.PENDING_RISK,
            amount=Decimal("0.002"),
            next_budget_id="b3",
            stage_id="s1",
        ).value
        opened = apply_risk_transition(
            pending,
            kind=RiskTransitionKind.OPEN_RISK,
            amount=Decimal("0.002"),
            next_budget_id="b4",
        ).value
        realized = apply_risk_transition(
            opened,
            kind=RiskTransitionKind.REALIZE_LOSS,
            amount=Decimal("0.001"),
            next_budget_id="b5",
        ).value
        self.assertEqual(Decimal("0.001"), realized.realized_loss)
        self.assertEqual(reserved.committed_risk, pending.committed_risk)
        self.assertEqual(pending.committed_risk, opened.committed_risk)
        self.assertEqual(opened.committed_risk, realized.committed_risk)

    def test_risk_cap_is_fail_closed(self) -> None:
        result = apply_risk_transition(
            self.budget,
            kind=RiskTransitionKind.RESERVE_STAGE,
            amount=Decimal("0.02"),
            next_budget_id="b2",
            stage_id="s1",
        )
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("RISK_EPISODE_CAP_BREACH", result.error.code)

    def eligible_evaluation(self, status: StageStatus) -> StageEvaluation:
        return StageEvaluation(
            decision_cutoff=self.now,
            requested_status=status,
            strategic_status=StrategicStatus.ACTIVE,
            trigger=GateVerdict.PASS,
            predecessor=GateVerdict.PASS,
            evidence=GateVerdict.PASS,
            time_authority=GateVerdict.PASS,
            geometry=GateVerdict.PASS,
            forward_reward_risk=GateVerdict.PASS,
            reserved_risk=GateVerdict.PASS,
            portfolio_stress=GateVerdict.PASS,
            cost_liquidity_margin=GateVerdict.PASS,
            supervision=GateVerdict.PASS,
            protection_atomicity=GateVerdict.PASS,
        )

    def test_stage_requires_all_activation_gates(self) -> None:
        state = StageState(self.spec, StageStatus.REGISTERED, 1)
        eligible = reduce_stage(state, self.eligible_evaluation(StageStatus.ELIGIBLE))
        self.assertEqual(ReducerStatus.APPLIED, eligible.status)
        unknown = self.eligible_evaluation(StageStatus.ELIGIBLE)
        unknown = StageEvaluation(
            **{
                **{
                    field: getattr(unknown, field)
                    for field in unknown.__dataclass_fields__
                },
                "forward_reward_risk": GateVerdict.UNKNOWN,
            }
        )
        result = reduce_stage(state, unknown)
        self.assertEqual(ReducerStatus.NO_CHANGE, result.status)

    def test_e0_rejects_real_add(self) -> None:
        state = StageState(self.spec, StageStatus.ELIGIBLE, 2)
        evaluation = self.eligible_evaluation(StageStatus.ARMED)
        evaluation = StageEvaluation(
            **{
                **{
                    field: getattr(evaluation, field)
                    for field in evaluation.__dataclass_fields__
                },
                "selected_exact_candidate": True,
                "counterfactual_only": False,
            }
        )
        result = reduce_stage(state, evaluation)
        self.assertEqual("STAGE_REAL_ADD_AUTHORITY_NONE", result.error.code)

    def test_unattended_unknown_degrades_to_no_new_risk(self) -> None:
        contract = SupervisionContract(
            "sup1",
            1,
            (
                SupervisionWindow(
                    self.now,
                    self.now + timedelta(hours=8),
                    SupervisionMode.UNATTENDED_PROTECTED,
                ),
            ),
        )
        result = assess_supervision(
            contract,
            effective_at=self.now,
            protection_pass=True,
            ack_freshness_pass=None,
            data_freshness_pass=True,
            account_consistency_pass=True,
            worst_case_loss_pass=True,
        )
        self.assertEqual(SupervisionMode.NO_NEW_RISK, result.value.mode)


if __name__ == "__main__":
    unittest.main()
