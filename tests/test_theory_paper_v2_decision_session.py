from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_system.theory_paper_v2.application import (
    AggregateMutation,
    CommitContext,
    DecisionSessionError,
    DecisionSessionPorts,
    DecisionSessionRequest,
    DeterministicCalculation,
    FrozenChallenge,
    FrozenProposal,
    PlanningSettings,
    ReplayOutcome,
    run_decision_session,
)
from trade_system.theory_paper_v2.domain.deliberation import (
    CandidateDecisionMetrics,
    ChallengeCategory,
    ChallengeClaim,
    ChallengeDisposition,
    ChallengeEnvelope,
    ChallengeMode,
    ChallengeResult,
    ChallengeTerminalEffect,
    DecisionContext,
    ProposedActionPlan,
    make_decision_criterion_policy,
    make_no_action_plan,
)
from trade_system.theory_paper_v2.domain.evaluation import (
    CoverageVerdict,
    DataStatus,
    DecimalInterval,
    PathKind,
    PathPayoffCell,
    ProbabilityStatus,
    assess_recursive_feasibility,
    build_path_payoff_matrix,
    make_stress_scenario_set,
)
from trade_system.theory_paper_v2.domain.governance import (
    REQUIRED_HARD_CONSTRAINT_IDS,
    ConstraintDecision,
    ConstraintEvaluation,
)
from trade_system.theory_paper_v2.domain.policy import (
    ActionIntent,
    GeometryOperation,
    ProtectiveActionType,
)


class _Proposer:
    def __init__(self, trace, proposal):
        self.trace = trace
        self.proposal = proposal

    def propose_once(self, context):
        self.trace.append("PROPOSER")
        return self.proposal


class _Challenger:
    def __init__(self, trace, challenge):
        self.trace = trace
        self.challenge = challenge

    def challenge_once(self, context, proposal):
        self.trace.append("CHALLENGER")
        return self.challenge


class _Calculator:
    def __init__(self, trace, now):
        self.trace = trace
        self.now = now

    def calculate_once(self, context, candidates):
        self.trace.append("CALCULATOR")
        evaluations = {
            candidate.candidate_ref: {
                constraint_id: ConstraintEvaluation(
                    constraint_id=constraint_id,
                    verdict=ConstraintDecision.PASS,
                    evidence_or_calculation_refs=("evidence:fixture",),
                )
                for constraint_id in REQUIRED_HARD_CONSTRAINT_IDS
            }
            for candidate in candidates.candidates
        }
        metrics = tuple(
            CandidateDecisionMetrics(
                candidate_ref=candidate.candidate_ref,
                robust_dominated=False,
                minimax_regret=(
                    Decimal("0.2")
                    if candidate.is_no_action
                    else Decimal("0.1")
                ),
                worst_case_loss=(
                    Decimal("0")
                    if candidate.is_no_action
                    else Decimal("1")
                ),
                tail_loss=(
                    Decimal("0")
                    if candidate.is_no_action
                    else Decimal("1")
                ),
                cost=Decimal("0"),
                turnover=Decimal("0"),
                obligation_review_at=(
                    self.now + timedelta(hours=1)
                    if candidate.is_no_action
                    else None
                ),
            )
            for candidate in candidates.candidates
        )
        plan_refs = tuple(
            candidate.proposed_action_plan_ref
            for candidate in candidates.candidates
        )
        interval = DecimalInterval(
            Decimal("0"), Decimal("1"), "ACCOUNT_USD"
        )
        cells = tuple(
            PathPayoffCell(
                path=path,
                action_plan_ref=plan_ref,
                account_pnl_interval=DecimalInterval(
                    Decimal("-1"), Decimal("2"), "ACCOUNT_USD"
                ),
                total_account_risk=interval,
                marginal_account_risk=interval,
                max_drawdown=interval,
                stress_loss=interval,
                tail_loss=interval,
                intermediate_state_refs=("state:fixture",),
                data_status=DataStatus.PARTIALLY_IDENTIFIED,
            )
            for path in (
                PathKind.FAILURE,
                PathKind.NORMAL_REBOUND,
                PathKind.TREND_CONTINUATION,
                PathKind.REBOUND_EXHAUSTION,
                PathKind.OTHER,
                PathKind.UNKNOWN,
            )
            for plan_ref in plan_refs
        )
        matrix = build_path_payoff_matrix(
            matrix_id="matrix:session",
            strategic_episode_ref="episode:1",
            revision=1,
            decision_cutoff=self.now,
            decision_horizon_ref="horizon:1",
            planning_context_id="planning:1",
            candidate_action_set_digest=candidates.candidate_set_digest,
            action_plan_refs=plan_refs,
            cells=cells,
            probability_status=ProbabilityStatus.ORDINAL_ONLY,
            ordinal_path_ranks=(
                (PathKind.FAILURE, 5),
                (PathKind.NORMAL_REBOUND, 2),
                (PathKind.TREND_CONTINUATION, 1),
                (PathKind.REBOUND_EXHAUSTION, 4),
                (PathKind.OTHER, 3),
            ),
        ).value
        stress = make_stress_scenario_set(
            scenario_set_id="stress:session",
            frozen_at=self.now,
            scenario_refs=("scenario:gap", "scenario:reversal"),
            required_scenario_class_refs=("GAP", "REVERSAL"),
            coverage_verdict=CoverageVerdict.PASS,
        )
        recursive = {
            candidate.candidate_ref: assess_recursive_feasibility(
                receipt_id=f"recursive:{candidate.candidate_ref}",
                candidate_action_ref=candidate.candidate_ref,
                decision_cutoff=self.now,
                starting_aggregate_head_refs=("head:episode",),
                planning_horizon_ref="horizon:1",
                next_review_at=self.now + timedelta(hours=1),
                stress_scenario_set=stress,
                reachable_state_summary_refs=("state:safe",),
                scenario_continuation_refs={
                    "scenario:gap": ("action:terminal",),
                    "scenario:reversal": ("action:reduce",),
                },
                terminal_safe_action_ref="action:terminal",
                hard_constraint_result_refs=("constraints:all",),
                solver_or_evaluator_version="1.0.0",
                solver_or_evaluator_digest="b" * 64,
            ).value
            for candidate in candidates.candidates
        }
        return DeterministicCalculation(
            hard_constraint_evaluations=evaluations,
            decision_metrics=metrics,
            path_payoff_matrix=matrix,
            recursive_feasibility_by_candidate=recursive,
            hard_constraint_result_refs=("constraints:all",),
            schema_pit_state_verdict_refs=("pit:pass", "state:pass"),
            artifact_digests=("c" * 64,),
        )


class _Selector:
    def __init__(self, trace, *, outside=False):
        self.trace = trace
        self.outside = outside

    def select_once(self, context, feasible_set, metrics):
        self.trace.append("SELECTOR")
        if self.outside:
            return "candidate:invented"
        return min(metrics, key=lambda item: item.minimax_regret).candidate_ref


class _Replay:
    def __init__(self, trace):
        self.trace = trace

    def replay_once(self, context, selection, plan):
        self.trace.append("REPLAY")
        return ReplayOutcome(
            result_ref="portfolio-replay:1",
            result_digest="d" * 64,
            counterfactual_policy_ref="policy:counterfactual",
            aggregate_mutations=(
                AggregateMutation(
                    aggregate_id="portfolio:1",
                    aggregate_type="PORTFOLIO",
                    expected_revision=0,
                    expected_state_digest=None,
                    next_revision=1,
                    state_ref="portfolio-state:1",
                    state_digest="e" * 64,
                ),
            ),
        )


class _UnitOfWork:
    def __init__(self, trace):
        self.trace = trace
        self.plans = []

    def commit(self, plan):
        self.trace.append("UNIT_OF_WORK")
        self.plans.append(plan)
        return {"receipt": "committed"}


class DecisionSessionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 31, 12, tzinfo=UTC)
        self.policy = make_decision_criterion_policy(
            policy_id="policy:1",
            revision=1,
            valid_from=self.now - timedelta(hours=1),
            valid_until=self.now + timedelta(days=1),
            tie_break_order=(
                "LOWER_WORST_CASE_LOSS",
                "LOWER_TAIL_LOSS",
                "LOWER_COST",
                "LOWER_TURNOVER",
                "EARLIER_OBLIGATION_REVIEW",
                "CANONICAL_ACTION_ID",
            ),
        )
        self.context = DecisionContext(
            context_id="context:1",
            decision_cutoff=self.now,
            probability_status=ProbabilityStatus.ORDINAL_ONLY,
            decision_criterion_policy_ref=self.policy.policy_id,
            decision_criterion_policy_digest=self.policy.policy_digest,
        )
        keep = ProposedActionPlan(
            plan_id="plan:keep",
            strategic_episode_ref="episode:1",
            decision_cutoff=self.now,
            path_ref="path:continuation",
            cross_timescale_control_envelope_ref="lease:1",
            strategic_delta_facet_ref="strategic:keep",
            position_facet_ref="position:keep",
            action_intent=ActionIntent.KEEP_CORE,
            protective_action_type=ProtectiveActionType.NONE,
            geometry_operation=GeometryOperation.KEEP,
            atomic_effect_types=(),
            position_delta=Decimal("0"),
            risk_delta=Decimal("0"),
        )
        no_action = make_no_action_plan(
            strategic_episode_ref="episode:1",
            decision_cutoff=self.now,
            path_ref="path:unknown",
            envelope_ref="lease:1",
            next_review_at=self.now + timedelta(hours=1),
            unmet_dependency_refs=("dependency:volume",),
        )
        self.proposal = FrozenProposal(
            proposal_ref="proposal:1",
            proposed_plans=(keep,),
            no_action_plan=no_action,
            required_meaningful_plan_refs=frozenset({"plan:keep"}),
            artifact_digest="a" * 64,
        )
        claim = ChallengeClaim(
            claim_id="claim:1",
            proposal_ref="proposal:1",
            subject_object_refs=("context:1",),
            category=ChallengeCategory.OMITTED_COMPETING_PATH,
            requested_disposition=ChallengeResult.SOFT,
        )
        envelope = ChallengeEnvelope(
            challenge_id="challenge:1",
            challenge_mode=ChallengeMode.POST_PROPOSAL,
            proposal_ref="proposal:1",
            reasoning_strategy_contract_ref="reasoning:challenger",
            role_context_view_ref="view:challenger",
            role_context_proposal_ref="proposal:1",
            claims=(claim,),
        )
        disposition = ChallengeDisposition(
            disposition_id="disposition:1",
            proposal_ref="proposal:1",
            challenge_ref="challenge:1",
            result=ChallengeResult.SOFT,
            verified_claim_refs=(),
            verified_constraint_or_invariant_refs=(),
            affected_proposed_plan_refs=(),
            terminal_effect=ChallengeTerminalEffect.NONE,
            deterministic_validator_version="1.0.0",
        )
        self.challenge = FrozenChallenge(
            envelope=envelope,
            disposition=disposition,
            artifact_digest="f" * 64,
        )
        self.request = DecisionSessionRequest(
            decision_session_id="session:1",
            context=self.context,
            policy=self.policy,
            planning=PlanningSettings(
                plan_id="rolling-plan:1",
                strategic_episode_ref="episode:1",
                revision=1,
                continuation_branches=(),
                planned_review_points=(self.now + timedelta(hours=1),),
                terminal_fallback_action_ref="action:terminal",
                cost_model_ref="cost:1",
            ),
            challenge_mode=ChallengeMode.POST_PROPOSAL,
            constraint_engine_version="1.0.0",
            selection_reason="frozen ordinal minimax-regret",
            challenge_disposition_ref="disposition:1",
            expected_head_ref="head:episode:0",
            commit=CommitContext(
                commit_id="commit-1",
                offline_run_id="run-1",
                decision_session_id="session:1",
                committed_at="2026-07-31T12:00:00Z",
                idempotent_command_id="command-1",
                idempotency_key="key-1",
                expected_previous_event_sequence=None,
                expected_previous_event_digest=None,
            ),
        )

    def ports(self, trace, *, outside=False):
        unit = _UnitOfWork(trace)
        return (
            DecisionSessionPorts(
                proposer=_Proposer(trace, self.proposal),
                challenger=_Challenger(trace, self.challenge),
                calculator=_Calculator(trace, self.now),
                selector=_Selector(trace, outside=outside),
                replay=_Replay(trace),
                unit_of_work=unit,
            ),
            unit,
        )

    def test_fixed_dag_commits_only_current_first_step(self):
        trace = []
        ports, unit = self.ports(trace)
        result = run_decision_session(self.request, ports)
        self.assertEqual(
            [
                "PROPOSER",
                "CHALLENGER",
                "CALCULATOR",
                "SELECTOR",
                "REPLAY",
                "UNIT_OF_WORK",
            ],
            trace,
        )
        self.assertEqual(1, len(unit.plans))
        plan = result.commit.plan
        self.assertEqual(
            result.selection.selected_candidate_ref,
            plan.authorized_first_step_action_ref,
        )
        self.assertFalse(plan.executable)
        self.assertEqual("NONE_E0", plan.external_execution_authority)
        self.assertEqual((), plan.conditional_future_action_refs)

    def test_selector_escape_leaves_no_replay_or_commit(self):
        trace = []
        ports, unit = self.ports(trace, outside=True)
        with self.assertRaisesRegex(
            DecisionSessionError, "SELECTOR_OUTSIDE_FEASIBLE_SET"
        ):
            run_decision_session(self.request, ports)
        self.assertEqual(
            ["PROPOSER", "CHALLENGER", "CALCULATOR", "SELECTOR"],
            trace,
        )
        self.assertEqual([], unit.plans)


if __name__ == "__main__":
    unittest.main()
