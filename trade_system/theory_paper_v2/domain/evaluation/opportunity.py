"""Ex-ante opportunity comparison without realized-loss contamination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common import DomainError, DomainResult, ReducerStatus
from ..contracts.canonical import canonical_digest
from .model import DecimalInterval, require_aware
from .planning import FeasibilityStatus, RecursiveFeasibilityReceipt


class CounterfactualTier(StrEnum):
    OBSERVABLE_ACCOUNTING = "OBSERVABLE_ACCOUNTING"
    MODEL_CONDITIONAL = "MODEL_CONDITIONAL"
    CAUSAL_OPE = "CAUSAL_OPE"


class FormalMetricEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    UNKNOWN = "UNKNOWN"


class OpportunityStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIALLY_IDENTIFIED = "PARTIALLY_IDENTIFIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class OpportunityCostReceipt:
    receipt_id: str
    candidate_ref: str
    evaluated_action_ref: str
    comparator_action_ref: str
    comparator_policy_ref: str
    comparator_policy_digest: str
    comparator_frozen_at: datetime
    decision_cutoff: datetime
    comparator_recursive_feasibility_receipt_ref: str
    same_risk_and_authority_constraints: str
    comparison_horizon_ref: str
    path_complexity_or_switch_count: int
    fill_slippage_and_fee_model_ref: str
    support_overlap_status: str
    identification_contract_ref: str | None
    counterfactual_tier: CounterfactualTier
    evaluated_value_interval: DecimalInterval
    comparator_value_interval: DecimalInterval
    conditional_difference_interval: DecimalInterval
    uncertainty_interval: DecimalInterval
    not_realized_loss: bool
    issued_before_selection: bool
    formal_metric_eligibility: FormalMetricEligibility
    status: OpportunityStatus
    assumption_refs: tuple[str, ...]
    calculator_contract_version: str
    receipt_digest: str


def _error(code: str, message: str) -> DomainResult:
    return DomainResult(
        status=ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="OPPORTUNITY_COST",
            retryability="NEVER",
            message=message,
        ),
    )


def issue_ex_ante_opportunity_cost(
    *,
    receipt_id: str,
    candidate_ref: str,
    evaluated_action_ref: str,
    comparator_action_ref: str,
    comparator_policy_ref: str,
    comparator_policy_digest: str,
    comparator_frozen_at: datetime,
    decision_cutoff: datetime,
    comparator_feasibility: RecursiveFeasibilityReceipt,
    same_risk_and_authority_constraints: bool,
    comparison_horizon_ref: str,
    path_complexity_or_switch_count: int,
    fill_slippage_and_fee_model_ref: str,
    support_overlap_status: str,
    identification_contract_ref: str | None,
    counterfactual_tier: CounterfactualTier,
    evaluated_value_interval: DecimalInterval,
    comparator_value_interval: DecimalInterval,
    uncertainty_interval: DecimalInterval,
    status: OpportunityStatus,
    assumption_refs: tuple[str, ...],
    calculator_contract_version: str,
) -> DomainResult[OpportunityCostReceipt]:
    """Compare only a frozen, then-feasible policy before selection."""

    require_aware(comparator_frozen_at)
    require_aware(decision_cutoff)
    if comparator_frozen_at > decision_cutoff:
        return _error(
            "OPPORTUNITY_COMPARATOR_NOT_FROZEN",
            "hindsight-aware comparator cannot populate formal opportunity cost",
        )
    if (
        comparator_feasibility.candidate_action_ref != comparator_action_ref
        or comparator_feasibility.status is not FeasibilityStatus.PASS
        or not same_risk_and_authority_constraints
    ):
        return _error(
            "OPPORTUNITY_COMPARATOR_FROZEN_AND_FEASIBLE",
            "comparator must be feasible under identical then-current constraints",
        )
    if candidate_ref != evaluated_action_ref:
        return _error(
            "OPPORTUNITY_EVALUATED_PAIR_MISMATCH",
            "candidate and evaluated action must be the same pair",
        )
    if path_complexity_or_switch_count < 0:
        return _error(
            "OPPORTUNITY_PATH_COMPLEXITY_INVALID",
            "switch count cannot be negative",
        )
    if support_overlap_status not in {"PASS", "PARTIAL", "UNKNOWN"}:
        return _error(
            "OPPORTUNITY_SUPPORT_OVERLAP_INVALID",
            "support overlap must use the closed PASS/PARTIAL/UNKNOWN set",
        )
    if status is OpportunityStatus.UNKNOWN:
        eligibility = FormalMetricEligibility.UNKNOWN
    elif status is OpportunityStatus.PARTIALLY_IDENTIFIED:
        eligibility = FormalMetricEligibility.DIAGNOSTIC_ONLY
    elif counterfactual_tier is CounterfactualTier.MODEL_CONDITIONAL:
        eligibility = FormalMetricEligibility.DIAGNOSTIC_ONLY
    elif counterfactual_tier is CounterfactualTier.CAUSAL_OPE and not (
        support_overlap_status == "PASS"
        and identification_contract_ref is not None
    ):
        eligibility = FormalMetricEligibility.DIAGNOSTIC_ONLY
    else:
        eligibility = FormalMetricEligibility.ELIGIBLE
    difference = comparator_value_interval.subtract(evaluated_value_interval)
    digest = canonical_digest(
        {
            "receipt_id": receipt_id,
            "candidate_ref": candidate_ref,
            "evaluated_action_ref": evaluated_action_ref,
            "comparator_action_ref": comparator_action_ref,
            "comparator_policy_digest": comparator_policy_digest,
            "comparator_frozen_at": comparator_frozen_at.isoformat(),
            "decision_cutoff": decision_cutoff.isoformat(),
            "comparator_feasibility": comparator_feasibility.receipt_digest,
            "same_risk_and_authority_constraints": "PASS",
            "comparison_horizon_ref": comparison_horizon_ref,
            "path_complexity_or_switch_count": path_complexity_or_switch_count,
            "fill_slippage_and_fee_model_ref": fill_slippage_and_fee_model_ref,
            "support_overlap_status": support_overlap_status,
            "identification_contract_ref": identification_contract_ref,
            "counterfactual_tier": counterfactual_tier.value,
            "evaluated_value": (
                evaluated_value_interval.lower,
                evaluated_value_interval.upper,
            ),
            "comparator_value": (
                comparator_value_interval.lower,
                comparator_value_interval.upper,
            ),
            "difference": (difference.lower, difference.upper),
            "uncertainty": (
                uncertainty_interval.lower,
                uncertainty_interval.upper,
            ),
            "not_realized_loss": True,
            "issued_before_selection": True,
            "formal_metric_eligibility": eligibility.value,
            "status": status.value,
            "assumptions": assumption_refs,
            "calculator_contract_version": calculator_contract_version,
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=OpportunityCostReceipt(
            receipt_id=receipt_id,
            candidate_ref=candidate_ref,
            evaluated_action_ref=evaluated_action_ref,
            comparator_action_ref=comparator_action_ref,
            comparator_policy_ref=comparator_policy_ref,
            comparator_policy_digest=comparator_policy_digest,
            comparator_frozen_at=comparator_frozen_at,
            decision_cutoff=decision_cutoff,
            comparator_recursive_feasibility_receipt_ref=(
                comparator_feasibility.receipt_digest
            ),
            same_risk_and_authority_constraints="PASS",
            comparison_horizon_ref=comparison_horizon_ref,
            path_complexity_or_switch_count=path_complexity_or_switch_count,
            fill_slippage_and_fee_model_ref=fill_slippage_and_fee_model_ref,
            support_overlap_status=support_overlap_status,
            identification_contract_ref=identification_contract_ref,
            counterfactual_tier=counterfactual_tier,
            evaluated_value_interval=evaluated_value_interval,
            comparator_value_interval=comparator_value_interval,
            conditional_difference_interval=difference,
            uncertainty_interval=uncertainty_interval,
            not_realized_loss=True,
            issued_before_selection=True,
            formal_metric_eligibility=eligibility,
            status=status,
            assumption_refs=assumption_refs,
            calculator_contract_version=calculator_contract_version,
            receipt_digest=digest,
        ),
    )
