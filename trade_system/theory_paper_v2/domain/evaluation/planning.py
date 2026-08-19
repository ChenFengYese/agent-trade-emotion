"""Recursive feasibility and first-step-only receding-horizon planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common import DomainError, DomainResult, ReducerStatus
from ..contracts.canonical import canonical_digest
from ..governance.model import FeasibleActionSet
from .model import PathPayoffMatrix, require_aware


class FeasibilityStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CoverageVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class StressScenarioSet:
    scenario_set_id: str
    frozen_at: datetime
    scenario_refs: tuple[str, ...]
    required_scenario_class_refs: tuple[str, ...]
    coverage_verdict: CoverageVerdict
    set_digest: str

    def __post_init__(self) -> None:
        require_aware(self.frozen_at)
        if (
            not self.scenario_refs
            or len(self.scenario_refs) != len(set(self.scenario_refs))
            or not self.required_scenario_class_refs
            or len(self.required_scenario_class_refs)
            != len(set(self.required_scenario_class_refs))
        ):
            raise ValueError("STRESS_SCENARIO_SET_INVALID")


@dataclass(frozen=True, slots=True)
class RecursiveFeasibilityReceipt:
    receipt_id: str
    candidate_action_ref: str
    starting_aggregate_head_refs: tuple[str, ...]
    planning_horizon_ref: str
    next_review_at: datetime
    stress_scenario_set: StressScenarioSet
    reachable_state_summary_refs: tuple[str, ...]
    safe_continuation_action_refs: tuple[str, ...]
    terminal_safe_action_ref: str
    hard_constraint_result_refs: tuple[str, ...]
    solver_or_evaluator_version: str
    solver_or_evaluator_digest: str
    status: FeasibilityStatus
    failure_reason_codes: tuple[str, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        require_aware(self.next_review_at)
        if (
            not self.starting_aggregate_head_refs
            or not self.reachable_state_summary_refs
            or not self.terminal_safe_action_ref
            or not self.hard_constraint_result_refs
        ):
            raise ValueError("RECURSIVE_FEASIBILITY_RECEIPT_INCOMPLETE")
        if self.status is FeasibilityStatus.PASS and (
            not self.safe_continuation_action_refs or self.failure_reason_codes
        ):
            raise ValueError("RECURSIVE_FEASIBILITY_PASS_INVALID")


@dataclass(frozen=True, slots=True)
class ContinuationBranch:
    branch_id: str
    trigger_predicate_refs: tuple[str, ...]
    planned_action_ref: str
    remaining_risk_budget_ref: str
    review_at: datetime
    branch_status: str = "CONDITIONAL_NOT_AUTHORIZED"

    def __post_init__(self) -> None:
        require_aware(self.review_at)
        if (
            not self.branch_id
            or not self.trigger_predicate_refs
            or not self.planned_action_ref
            or self.branch_status != "CONDITIONAL_NOT_AUTHORIZED"
        ):
            raise ValueError("RECEDING_HORIZON_BRANCH_INVALID")


@dataclass(frozen=True, slots=True)
class RecedingHorizonPlan:
    plan_id: str
    strategic_episode_ref: str
    revision: int
    decision_cutoff: datetime
    planning_context_id: str
    candidate_action_set_digest: str
    current_authorized_action_ref: str
    conditional_continuation_branches: tuple[ContinuationBranch, ...]
    planned_review_points: tuple[datetime, ...]
    terminal_fallback_action_ref: str
    cost_model_ref: str
    path_payoff_matrix_ref: str
    recursive_feasibility_receipt_ref: str
    first_step_only: bool
    future_branch_authority: str
    previous_revision_ref: str | None
    plan_digest: str


def _error(code: str, message: str, *, unknown: bool = False) -> DomainResult:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if unknown else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="PLANNING",
            retryability="AFTER_INPUT_REPAIR" if unknown else "NEVER",
            message=message,
        ),
    )


def make_stress_scenario_set(
    *,
    scenario_set_id: str,
    frozen_at: datetime,
    scenario_refs: tuple[str, ...],
    required_scenario_class_refs: tuple[str, ...],
    coverage_verdict: CoverageVerdict,
) -> StressScenarioSet:
    digest = canonical_digest(
        {
            "scenario_set_id": scenario_set_id,
            "frozen_at": frozen_at.isoformat(),
            "scenario_refs": scenario_refs,
            "required_classes": required_scenario_class_refs,
            "coverage": coverage_verdict.value,
        }
    )
    return StressScenarioSet(
        scenario_set_id=scenario_set_id,
        frozen_at=frozen_at,
        scenario_refs=scenario_refs,
        required_scenario_class_refs=required_scenario_class_refs,
        coverage_verdict=coverage_verdict,
        set_digest=digest,
    )


def assess_recursive_feasibility(
    *,
    receipt_id: str,
    candidate_action_ref: str,
    decision_cutoff: datetime,
    starting_aggregate_head_refs: tuple[str, ...],
    planning_horizon_ref: str,
    next_review_at: datetime,
    stress_scenario_set: StressScenarioSet,
    reachable_state_summary_refs: tuple[str, ...],
    scenario_continuation_refs: dict[str, tuple[str, ...]],
    terminal_safe_action_ref: str,
    hard_constraint_result_refs: tuple[str, ...],
    solver_or_evaluator_version: str,
    solver_or_evaluator_digest: str,
) -> DomainResult[RecursiveFeasibilityReceipt]:
    """Derive feasibility; callers cannot assert PASS directly."""

    require_aware(decision_cutoff)
    if stress_scenario_set.frozen_at > decision_cutoff:
        return _error(
            "RECURSIVE_FEASIBILITY_FUTURE_STRESS_SET",
            "stress scenarios must be frozen by the decision cutoff",
        )
    if set(scenario_continuation_refs) != set(stress_scenario_set.scenario_refs):
        status = FeasibilityStatus.UNKNOWN
        reasons = ("STRESS_SCENARIO_CONTINUATION_COVERAGE_UNKNOWN",)
    elif stress_scenario_set.coverage_verdict is CoverageVerdict.UNKNOWN:
        status = FeasibilityStatus.UNKNOWN
        reasons = ("STRESS_SCENARIO_COVERAGE_UNKNOWN",)
    elif stress_scenario_set.coverage_verdict is CoverageVerdict.FAIL:
        status = FeasibilityStatus.FAIL
        reasons = ("STRESS_SCENARIO_COVERAGE_FAILED",)
    elif any(not refs for refs in scenario_continuation_refs.values()):
        status = FeasibilityStatus.FAIL
        reasons = ("SAFE_CONTINUATION_MISSING",)
    else:
        status = FeasibilityStatus.PASS
        reasons = ()
    safe_refs = tuple(
        sorted(
            {
                ref
                for refs in scenario_continuation_refs.values()
                for ref in refs
            }
        )
    )
    if status is FeasibilityStatus.PASS and not safe_refs:
        status = FeasibilityStatus.FAIL
        reasons = ("SAFE_CONTINUATION_MISSING",)
    digest = canonical_digest(
        {
            "receipt_id": receipt_id,
            "candidate": candidate_action_ref,
            "heads": starting_aggregate_head_refs,
            "planning_horizon_ref": planning_horizon_ref,
            "next_review_at": next_review_at.isoformat(),
            "stress_set": stress_scenario_set.set_digest,
            "reachable_states": reachable_state_summary_refs,
            "safe_continuations": safe_refs,
            "terminal_safe": terminal_safe_action_ref,
            "hard_constraint_results": hard_constraint_result_refs,
            "solver_version": solver_or_evaluator_version,
            "solver_digest": solver_or_evaluator_digest,
            "status": status.value,
            "reasons": reasons,
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=RecursiveFeasibilityReceipt(
            receipt_id=receipt_id,
            candidate_action_ref=candidate_action_ref,
            starting_aggregate_head_refs=starting_aggregate_head_refs,
            planning_horizon_ref=planning_horizon_ref,
            next_review_at=next_review_at,
            stress_scenario_set=stress_scenario_set,
            reachable_state_summary_refs=reachable_state_summary_refs,
            safe_continuation_action_refs=safe_refs,
            terminal_safe_action_ref=terminal_safe_action_ref,
            hard_constraint_result_refs=hard_constraint_result_refs,
            solver_or_evaluator_version=solver_or_evaluator_version,
            solver_or_evaluator_digest=solver_or_evaluator_digest,
            status=status,
            failure_reason_codes=reasons,
            receipt_digest=digest,
        ),
    )


def build_receding_horizon_plan(
    *,
    plan_id: str,
    strategic_episode_ref: str,
    revision: int,
    decision_cutoff: datetime,
    selected_candidate_ref: str,
    feasible_set: FeasibleActionSet,
    matrix: PathPayoffMatrix,
    recursive_feasibility: RecursiveFeasibilityReceipt,
    continuation_branches: tuple[ContinuationBranch, ...],
    planned_review_points: tuple[datetime, ...],
    terminal_fallback_action_ref: str,
    cost_model_ref: str,
    previous_revision_ref: str | None = None,
) -> DomainResult[RecedingHorizonPlan]:
    """Materialize one authorized current step and only conditional futures."""

    require_aware(decision_cutoff)
    feasible = feasible_set.by_ref()
    selected = feasible.get(selected_candidate_ref)
    if selected is None:
        return _error(
            "SELECTOR_OUTSIDE_FEASIBLE_SET",
            "receding plan cannot authorize a non-feasible action",
        )
    if (
        matrix.candidate_action_set_digest
        != feasible_set.candidate_bundle_set.candidate_set_digest
        or matrix.planning_context_id == ""
        or selected.proposed_action_plan_ref not in matrix.actions
    ):
        return _error(
            "RECEDING_HORIZON_CONTEXT_MISMATCH",
            "matrix and feasible action set identities differ",
        )
    if recursive_feasibility.candidate_action_ref != selected_candidate_ref:
        return _error(
            "RECURSIVE_FEASIBILITY_CANDIDATE_MISMATCH",
            "feasibility receipt belongs to another candidate",
        )
    if selected.introduces_new_risk and (
        recursive_feasibility.status is not FeasibilityStatus.PASS
    ):
        return _error(
            "RECURSIVE_FEASIBILITY_NOT_PASS",
            "FAIL/UNKNOWN cannot authorize current new risk",
        )
    if (
        not planned_review_points
        or any(point.tzinfo is None for point in planned_review_points)
        or len({branch.branch_id for branch in continuation_branches})
        != len(continuation_branches)
    ):
        return _error(
            "RECEDING_HORIZON_PLAN_INVALID",
            "review points and conditional branch identities must be valid",
        )
    digest = canonical_digest(
        {
            "plan_id": plan_id,
            "episode": strategic_episode_ref,
            "revision": revision,
            "decision_cutoff": decision_cutoff.isoformat(),
            "planning_context_id": matrix.planning_context_id,
            "candidate_action_set_digest": matrix.candidate_action_set_digest,
            "current_action": selected_candidate_ref,
            "conditional_branches": tuple(
                (
                    branch.branch_id,
                    branch.trigger_predicate_refs,
                    branch.planned_action_ref,
                    branch.remaining_risk_budget_ref,
                    branch.review_at.isoformat(),
                    branch.branch_status,
                )
                for branch in continuation_branches
            ),
            "planned_review_points": tuple(
                point.isoformat() for point in planned_review_points
            ),
            "terminal_fallback_action_ref": terminal_fallback_action_ref,
            "cost_model_ref": cost_model_ref,
            "path_payoff_matrix_ref": matrix.matrix_digest,
            "recursive_feasibility_receipt_ref": (
                recursive_feasibility.receipt_digest
            ),
            "first_step_only": True,
            "future_branch_authority": "REQUIRES_CURRENT_DATA_REAPPROVAL",
            "previous_revision_ref": previous_revision_ref,
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=RecedingHorizonPlan(
            plan_id=plan_id,
            strategic_episode_ref=strategic_episode_ref,
            revision=revision,
            decision_cutoff=decision_cutoff,
            planning_context_id=matrix.planning_context_id,
            candidate_action_set_digest=matrix.candidate_action_set_digest,
            current_authorized_action_ref=selected_candidate_ref,
            conditional_continuation_branches=continuation_branches,
            planned_review_points=planned_review_points,
            terminal_fallback_action_ref=terminal_fallback_action_ref,
            cost_model_ref=cost_model_ref,
            path_payoff_matrix_ref=matrix.matrix_digest,
            recursive_feasibility_receipt_ref=(
                recursive_feasibility.receipt_digest
            ),
            first_step_only=True,
            future_branch_authority="REQUIRES_CURRENT_DATA_REAPPROVAL",
            previous_revision_ref=previous_revision_ref,
            plan_digest=digest,
        ),
    )


def authorize_current_plan_action(
    plan: RecedingHorizonPlan, requested_action_ref: str
) -> DomainResult[str]:
    if (
        not plan.first_step_only
        or plan.future_branch_authority != "REQUIRES_CURRENT_DATA_REAPPROVAL"
    ):
        return _error(
            "RECEDING_HORIZON_FIRST_STEP_ONLY",
            "plan attempted to grant future branch authority",
        )
    if requested_action_ref != plan.current_authorized_action_ref:
        return _error(
            "RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED",
            "conditional branch requires a new current-data plan",
        )
    return DomainResult(status=ReducerStatus.APPLIED, value=requested_action_ref)
