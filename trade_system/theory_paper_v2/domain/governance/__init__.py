"""Pure hard-constraint and governance domain."""
from .constraints import (
    REQUIRED_HARD_CONSTRAINT_IDS,
    build_feasible_action_set,
    evaluate_hard_constraints,
)
from .model import (
    ConstraintClass,
    ConstraintDecision,
    ConstraintEvaluation,
    ConstraintVerdict,
    ConstraintVerdictSet,
    FeasibleActionSet,
    GovernanceAssessmentReceipt,
    GovernanceVerdict,
    RemovedCandidate,
)
from .research_authority import (
    ResearchAuthorityError,
    assert_research_start_authorized,
    validate_research_authorization_receipt,
    validate_research_authority,
)


def assess_selection(*args, **kwargs):
    """Import lazily to keep Domain package initialization acyclic."""

    from .assessment import assess_selection as _assess_selection

    return _assess_selection(*args, **kwargs)

__all__ = [
    "ConstraintClass",
    "ConstraintDecision",
    "ConstraintEvaluation",
    "ConstraintVerdict",
    "ConstraintVerdictSet",
    "FeasibleActionSet",
    "GovernanceAssessmentReceipt",
    "GovernanceVerdict",
    "REQUIRED_HARD_CONSTRAINT_IDS",
    "RemovedCandidate",
    "ResearchAuthorityError",
    "assess_selection",
    "assert_research_start_authorized",
    "build_feasible_action_set",
    "evaluate_hard_constraints",
    "validate_research_authorization_receipt",
    "validate_research_authority",
]
