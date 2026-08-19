"""Fixed, single-pass V2 decision-session orchestration.

Application owns ordering.  Generative roles may propose, challenge and request
one feasible candidate, but they cannot calculate risk, delete candidates,
mutate state, replay fills or commit events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from ..domain.common import ReducerStatus
from ..domain.deliberation import (
    AgentSelection,
    CandidateBundleSet,
    CandidateDecisionMetrics,
    ChallengeDisposition,
    ChallengeEnvelope,
    ChallengeMode,
    DecisionContext,
    DecisionCriterionPolicy,
    ProposedActionPlan,
    assemble_candidate_bundles,
    select_by_frozen_policy,
)
from ..domain.evaluation import (
    ContinuationBranch,
    PathPayoffMatrix,
    RecursiveFeasibilityReceipt,
    RecedingHorizonPlan,
    authorize_current_plan_action,
    build_receding_horizon_plan,
)
from ..domain.governance import (
    ConstraintEvaluation,
    ConstraintVerdictSet,
    FeasibleActionSet,
    GovernanceAssessmentReceipt,
    assess_selection,
    build_feasible_action_set,
    evaluate_hard_constraints,
)
from .commit import (
    CommitContext,
    ReplayOutcome,
    SessionCommitResult,
    commit_e0_session,
)


class DecisionSessionError(ValueError):
    """A typed no-commit terminal condition."""


@dataclass(frozen=True, slots=True)
class FrozenProposal:
    proposal_ref: str
    proposed_plans: tuple[ProposedActionPlan, ...]
    no_action_plan: ProposedActionPlan
    required_meaningful_plan_refs: frozenset[str]
    artifact_digest: str


@dataclass(frozen=True, slots=True)
class FrozenChallenge:
    envelope: ChallengeEnvelope
    disposition: ChallengeDisposition
    artifact_digest: str


@dataclass(frozen=True, slots=True)
class DeterministicCalculation:
    hard_constraint_evaluations: Mapping[
        str, Mapping[str, ConstraintEvaluation]
    ]
    decision_metrics: tuple[CandidateDecisionMetrics, ...]
    path_payoff_matrix: PathPayoffMatrix
    recursive_feasibility_by_candidate: Mapping[
        str, RecursiveFeasibilityReceipt
    ]
    hard_constraint_result_refs: tuple[str, ...]
    schema_pit_state_verdict_refs: tuple[str, ...]
    artifact_digests: tuple[str, ...]


class ProposalPort(Protocol):
    def propose_once(self, context: DecisionContext) -> FrozenProposal: ...


class ChallengePort(Protocol):
    def challenge_once(
        self,
        context: DecisionContext,
        proposal: FrozenProposal | None,
    ) -> FrozenChallenge: ...


class CalculationPort(Protocol):
    def calculate_once(
        self,
        context: DecisionContext,
        candidates: CandidateBundleSet,
    ) -> DeterministicCalculation: ...


class SelectorPort(Protocol):
    def select_once(
        self,
        context: DecisionContext,
        feasible_set: FeasibleActionSet,
        metrics: tuple[CandidateDecisionMetrics, ...],
    ) -> str | None: ...


class ReplayPort(Protocol):
    def replay_once(
        self,
        context: DecisionContext,
        selection: AgentSelection,
        plan: RecedingHorizonPlan,
    ) -> ReplayOutcome: ...


class CommitPort(Protocol):
    def commit(self, plan: object) -> object: ...


@dataclass(frozen=True, slots=True)
class PlanningSettings:
    plan_id: str
    strategic_episode_ref: str
    revision: int
    continuation_branches: tuple[ContinuationBranch, ...]
    planned_review_points: tuple[datetime, ...]
    terminal_fallback_action_ref: str
    cost_model_ref: str
    previous_revision_ref: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionSessionRequest:
    decision_session_id: str
    context: DecisionContext
    policy: DecisionCriterionPolicy
    planning: PlanningSettings
    challenge_mode: ChallengeMode
    constraint_engine_version: str
    selection_reason: str
    challenge_disposition_ref: str
    expected_head_ref: str
    commit: CommitContext


@dataclass(frozen=True, slots=True)
class DecisionSessionPorts:
    proposer: ProposalPort
    challenger: ChallengePort
    calculator: CalculationPort
    selector: SelectorPort
    replay: ReplayPort
    unit_of_work: CommitPort


@dataclass(frozen=True, slots=True)
class DecisionSessionResult:
    proposal: FrozenProposal
    challenge: FrozenChallenge
    candidate_set: CandidateBundleSet
    constraint_verdicts: ConstraintVerdictSet
    feasible_set: FeasibleActionSet
    selection: AgentSelection
    governance: GovernanceAssessmentReceipt
    receding_horizon_plan: RecedingHorizonPlan
    replay: ReplayOutcome
    commit: SessionCommitResult


def _applied(result: object, code: str):
    status = getattr(result, "status", None)
    if status is not ReducerStatus.APPLIED:
        error = getattr(result, "error", None)
        error_code = getattr(error, "code", code)
        raise DecisionSessionError(error_code)
    value = getattr(result, "value", None)
    if value is None:
        raise DecisionSessionError(code)
    return value


def run_decision_session(
    request: DecisionSessionRequest,
    ports: DecisionSessionPorts,
) -> DecisionSessionResult:
    """Run the exact fixed DAG once or leave no committed state.

    No retry, role substitution, hidden second proposal or future-branch
    authorization occurs inside this use case.
    """

    proposal = ports.proposer.propose_once(request.context)
    challenge_input = (
        None
        if request.challenge_mode is ChallengeMode.BLIND_CONTEXT_ONLY
        else proposal
    )
    challenge = ports.challenger.challenge_once(
        request.context, challenge_input
    )
    if challenge.envelope.challenge_mode is not request.challenge_mode:
        raise DecisionSessionError("CHALLENGE_MODE_MISMATCH_NO_COMMIT")

    candidate_set = _applied(
        assemble_candidate_bundles(
            proposal_ref=proposal.proposal_ref,
            challenge=challenge.envelope,
            disposition=challenge.disposition,
            proposed_plans=proposal.proposed_plans,
            no_action_plan=proposal.no_action_plan,
            required_meaningful_plan_refs=(
                proposal.required_meaningful_plan_refs
            ),
        ),
        "CANDIDATE_ASSEMBLY_FAILED_NO_COMMIT",
    )

    calculation = ports.calculator.calculate_once(
        request.context, candidate_set
    )
    verdicts = _applied(
        evaluate_hard_constraints(
            candidate_set=candidate_set,
            evaluations_by_candidate=(
                calculation.hard_constraint_evaluations
            ),
            constraint_engine_version=request.constraint_engine_version,
        ),
        "CONSTRAINT_EVALUATION_FAILED_NO_COMMIT",
    )
    feasible_set = _applied(
        build_feasible_action_set(
            candidate_set=candidate_set,
            hard_verdict_set=verdicts,
            decision_criterion_policy_ref=request.policy.policy_id,
            decision_criterion_policy_digest=request.policy.policy_digest,
        ),
        "FEASIBLE_SET_BUILD_FAILED_NO_COMMIT",
    )

    feasible_refs = {
        candidate.candidate_ref
        for candidate in feasible_set.feasible_candidates
    }
    metrics = tuple(
        metric
        for metric in calculation.decision_metrics
        if metric.candidate_ref in feasible_refs
    )
    requested_candidate_ref = ports.selector.select_once(
        request.context, feasible_set, metrics
    )
    selection = _applied(
        select_by_frozen_policy(
            feasible_set=feasible_set,
            context=request.context,
            policy=request.policy,
            metrics=metrics,
            requested_candidate_ref=requested_candidate_ref,
            selection_reason=request.selection_reason,
        ),
        "SELECTION_FAILED_NO_COMMIT",
    )

    governance = _applied(
        assess_selection(
            selection=selection,
            feasible_set=feasible_set,
            challenge_disposition_ref=(
                request.challenge_disposition_ref
            ),
            expected_head_ref=request.expected_head_ref,
            schema_pit_state_verdict_refs=(
                calculation.schema_pit_state_verdict_refs
            ),
            hard_constraint_verdict_refs=(
                calculation.hard_constraint_result_refs
            ),
        ),
        "GOVERNANCE_REJECTED_NO_COMMIT",
    )

    recursive = calculation.recursive_feasibility_by_candidate.get(
        selection.selected_candidate_ref
    )
    if recursive is None:
        raise DecisionSessionError(
            "RECURSIVE_FEASIBILITY_NOT_PASS"
        )
    receding_plan = _applied(
        build_receding_horizon_plan(
            plan_id=request.planning.plan_id,
            strategic_episode_ref=(
                request.planning.strategic_episode_ref
            ),
            revision=request.planning.revision,
            decision_cutoff=request.context.decision_cutoff,
            selected_candidate_ref=selection.selected_candidate_ref,
            feasible_set=feasible_set,
            matrix=calculation.path_payoff_matrix,
            recursive_feasibility=recursive,
            continuation_branches=(
                request.planning.continuation_branches
            ),
            planned_review_points=(
                request.planning.planned_review_points
            ),
            terminal_fallback_action_ref=(
                request.planning.terminal_fallback_action_ref
            ),
            cost_model_ref=request.planning.cost_model_ref,
            previous_revision_ref=(
                request.planning.previous_revision_ref
            ),
        ),
        "RECEDING_HORIZON_PLAN_INVALID",
    )
    _applied(
        authorize_current_plan_action(
            receding_plan, selection.selected_candidate_ref
        ),
        "RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED",
    )

    replay = ports.replay.replay_once(
        request.context, selection, receding_plan
    )
    commit_context = request.commit.with_session_outputs(
        decision_session_id=request.decision_session_id,
        accepted_artifact_digests=tuple(
            sorted(
                {
                    *request.commit.accepted_artifact_digests,
                    proposal.artifact_digest,
                    challenge.artifact_digest,
                    *calculation.artifact_digests,
                    candidate_set.candidate_set_digest,
                    verdicts.verdict_set_digest,
                    feasible_set.feasible_set_digest,
                    selection.selection_digest,
                    receding_plan.plan_digest,
                    replay.result_digest,
                }
            )
        ),
    )
    committed = commit_e0_session(
        context=commit_context,
        selection=selection,
        governance=governance,
        receding_horizon_plan=receding_plan,
        replay=replay,
        unit_of_work=ports.unit_of_work,
    )
    return DecisionSessionResult(
        proposal=proposal,
        challenge=challenge,
        candidate_set=candidate_set,
        constraint_verdicts=verdicts,
        feasible_set=feasible_set,
        selection=selection,
        governance=governance,
        receding_horizon_plan=receding_plan,
        replay=replay,
        commit=committed,
    )
