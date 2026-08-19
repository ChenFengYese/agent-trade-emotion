"""Final E0 governance check over an already deterministic selection."""

from __future__ import annotations

from ..common import DomainError, DomainResult, ReducerStatus
from ..deliberation.selection import AgentSelection
from .model import (
    FeasibleActionSet,
    GovernanceAssessmentReceipt,
    GovernanceVerdict,
)


def assess_selection(
    *,
    selection: AgentSelection,
    feasible_set: FeasibleActionSet,
    challenge_disposition_ref: str,
    expected_head_ref: str,
    schema_pit_state_verdict_refs: tuple[str, ...],
    hard_constraint_verdict_refs: tuple[str, ...],
) -> DomainResult[GovernanceAssessmentReceipt]:
    if (
        selection.feasible_action_set_ref != feasible_set.feasible_set_digest
        or selection.selected_candidate_ref not in feasible_set.by_ref()
        or selection.decision_criterion_policy_ref
        != feasible_set.decision_criterion_policy_ref
        or selection.decision_criterion_policy_digest
        != feasible_set.decision_criterion_policy_digest
    ):
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                code="SELECTOR_OUTSIDE_FEASIBLE_SET",
                category="GOVERNANCE",
                retryability="NEVER",
                message="selection is not an exact member of the frozen feasible set",
            ),
        )
    if (
        not schema_pit_state_verdict_refs
        or not hard_constraint_verdict_refs
        or not challenge_disposition_ref
        or not expected_head_ref
    ):
        return DomainResult(
            status=ReducerStatus.UNKNOWN,
            error=DomainError(
                code="GOVERNANCE_ASSESSMENT_INCOMPLETE",
                category="GOVERNANCE",
                retryability="AFTER_INPUT_REPAIR",
                message="required governance evidence is missing",
            ),
        )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=GovernanceAssessmentReceipt(
            selection_ref=selection.selection_ref,
            selection_valid=GovernanceVerdict.PASS,
            market_feasibility="FEASIBLE",
            counterfactual_permission="ALLOWED",
            schema_pit_state_verdict_refs=schema_pit_state_verdict_refs,
            hard_constraint_verdict_refs=hard_constraint_verdict_refs,
            challenge_disposition_ref=challenge_disposition_ref,
            expected_head_ref=expected_head_ref,
        ),
    )

