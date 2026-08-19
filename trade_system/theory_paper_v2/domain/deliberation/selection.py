"""Frozen-policy selection from, and only from, a complete feasible set."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..common import (
    EXTERNAL_EXECUTION_AUTHORITY,
    SYSTEM_MODE,
    DomainError,
    DomainResult,
    ReducerStatus,
)
from ..contracts.canonical import canonical_digest
from ..evaluation.model import ProbabilityStatus, require_aware, require_decimal
from ..governance.model import FeasibleActionSet


FROZEN_TIE_BREAK_TOKENS = frozenset(
    {
        "LOWER_WORST_CASE_LOSS",
        "LOWER_TAIL_LOSS",
        "LOWER_COST",
        "LOWER_TURNOVER",
        "EARLIER_OBLIGATION_REVIEW",
        "CANONICAL_ACTION_ID",
    }
)


def _decision_policy_digest_payload(
    *,
    policy_id: str,
    revision: int,
    valid_from: datetime,
    valid_until: datetime,
    tie_break_order: tuple[str, ...],
    robust_dominance_policy_ref: str,
    regret_policy_ref: str,
    opportunity_comparison_policy_ref: str,
    maximum_supported_uncertainty_ref: str,
    previous_revision_ref: str | None,
) -> dict:
    return {
        "policy_id": policy_id,
        "revision": revision,
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat(),
        "hard_constraints_precedence": True,
        "calibrated_mode_rule": "FROZEN_EXPECTED_UTILITY",
        "ordinal_mode_rule": "ROBUST_DOMINANCE_THEN_MINIMAX_REGRET",
        "unknown_mode_rule": "NO_NEW_RISK_WITH_OBLIGATION",
        "calibrated_mode_authorization_required": True,
        "ordinal_numeric_probability_use": "FORBIDDEN",
        "unknown_numeric_probability_use": "FORBIDDEN",
        "no_action_comparison_rule": "COMPARE_AS_EXPLICIT_FEASIBLE_ACTION",
        "tie_break_order": tie_break_order,
        "utility_function_ref": None,
        "robust_dominance_policy_ref": robust_dominance_policy_ref,
        "regret_policy_ref": regret_policy_ref,
        "opportunity_comparison_policy_ref": opportunity_comparison_policy_ref,
        "maximum_supported_uncertainty_ref": maximum_supported_uncertainty_ref,
        "previous_revision_ref": previous_revision_ref,
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
    }


@dataclass(frozen=True, slots=True)
class DecisionCriterionPolicy:
    policy_id: str
    revision: int
    policy_digest: str
    valid_from: datetime
    valid_until: datetime
    tie_break_order: tuple[str, ...]
    hard_constraints_precedence: bool = True
    calibrated_mode_rule: str = "FROZEN_EXPECTED_UTILITY"
    ordinal_mode_rule: str = "ROBUST_DOMINANCE_THEN_MINIMAX_REGRET"
    unknown_mode_rule: str = "NO_NEW_RISK_WITH_OBLIGATION"
    calibrated_mode_authorization_required: bool = True
    ordinal_numeric_probability_use: str = "FORBIDDEN"
    unknown_numeric_probability_use: str = "FORBIDDEN"
    no_action_comparison_rule: str = "COMPARE_AS_EXPLICIT_FEASIBLE_ACTION"
    utility_function_ref: str | None = None
    robust_dominance_policy_ref: str = "policy:robust-dominance:e0"
    regret_policy_ref: str = "policy:minimax-regret:e0"
    opportunity_comparison_policy_ref: str = "policy:opportunity-comparison:e0"
    maximum_supported_uncertainty_ref: str = "policy:max-uncertainty:e0"
    previous_revision_ref: str | None = None
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False

    def __post_init__(self) -> None:
        require_aware(self.valid_from)
        require_aware(self.valid_until)
        if (
            not self.policy_id
            or self.revision < 1
            or self.valid_until <= self.valid_from
            or not self.tie_break_order
            or len(self.tie_break_order) != len(set(self.tie_break_order))
            or not set(self.tie_break_order).issubset(FROZEN_TIE_BREAK_TOKENS)
            or not self.hard_constraints_precedence
            or self.calibrated_mode_rule != "FROZEN_EXPECTED_UTILITY"
            or self.ordinal_mode_rule != "ROBUST_DOMINANCE_THEN_MINIMAX_REGRET"
            or self.unknown_mode_rule != "NO_NEW_RISK_WITH_OBLIGATION"
            or not self.calibrated_mode_authorization_required
            or self.ordinal_numeric_probability_use != "FORBIDDEN"
            or self.unknown_numeric_probability_use != "FORBIDDEN"
            or self.no_action_comparison_rule
            != "COMPARE_AS_EXPLICIT_FEASIBLE_ACTION"
            or self.utility_function_ref is not None
            or not self.robust_dominance_policy_ref
            or not self.regret_policy_ref
            or not self.opportunity_comparison_policy_ref
            or not self.maximum_supported_uncertainty_ref
            or self.system_mode != SYSTEM_MODE
            or self.external_execution_authority != EXTERNAL_EXECUTION_AUTHORITY
            or self.executable
            or self.policy_digest
            != canonical_digest(
                _decision_policy_digest_payload(
                    policy_id=self.policy_id,
                    revision=self.revision,
                    valid_from=self.valid_from,
                    valid_until=self.valid_until,
                    tie_break_order=self.tie_break_order,
                    robust_dominance_policy_ref=self.robust_dominance_policy_ref,
                    regret_policy_ref=self.regret_policy_ref,
                    opportunity_comparison_policy_ref=(
                        self.opportunity_comparison_policy_ref
                    ),
                    maximum_supported_uncertainty_ref=(
                        self.maximum_supported_uncertainty_ref
                    ),
                    previous_revision_ref=self.previous_revision_ref,
                )
            )
        ):
            raise ValueError("DECISION_CRITERION_POLICY_INVALID")


def make_decision_criterion_policy(
    *,
    policy_id: str,
    revision: int,
    valid_from: datetime,
    valid_until: datetime,
    tie_break_order: tuple[str, ...],
    robust_dominance_policy_ref: str = "policy:robust-dominance:e0",
    regret_policy_ref: str = "policy:minimax-regret:e0",
    opportunity_comparison_policy_ref: str = "policy:opportunity-comparison:e0",
    maximum_supported_uncertainty_ref: str = "policy:max-uncertainty:e0",
    previous_revision_ref: str | None = None,
) -> DecisionCriterionPolicy:
    digest = canonical_digest(
        _decision_policy_digest_payload(
            policy_id=policy_id,
            revision=revision,
            valid_from=valid_from,
            valid_until=valid_until,
            tie_break_order=tie_break_order,
            robust_dominance_policy_ref=robust_dominance_policy_ref,
            regret_policy_ref=regret_policy_ref,
            opportunity_comparison_policy_ref=opportunity_comparison_policy_ref,
            maximum_supported_uncertainty_ref=maximum_supported_uncertainty_ref,
            previous_revision_ref=previous_revision_ref,
        )
    )
    return DecisionCriterionPolicy(
        policy_id=policy_id,
        revision=revision,
        policy_digest=digest,
        valid_from=valid_from,
        valid_until=valid_until,
        tie_break_order=tie_break_order,
        robust_dominance_policy_ref=robust_dominance_policy_ref,
        regret_policy_ref=regret_policy_ref,
        opportunity_comparison_policy_ref=opportunity_comparison_policy_ref,
        maximum_supported_uncertainty_ref=maximum_supported_uncertainty_ref,
        previous_revision_ref=previous_revision_ref,
    )


@dataclass(frozen=True, slots=True)
class DecisionContext:
    context_id: str
    decision_cutoff: datetime
    probability_status: ProbabilityStatus
    decision_criterion_policy_ref: str
    decision_criterion_policy_digest: str

    def __post_init__(self) -> None:
        require_aware(self.decision_cutoff)


@dataclass(frozen=True, slots=True)
class CandidateDecisionMetrics:
    candidate_ref: str
    robust_dominated: bool
    minimax_regret: Decimal
    worst_case_loss: Decimal
    tail_loss: Decimal
    cost: Decimal
    turnover: Decimal
    obligation_review_at: datetime | None
    expected_utility: Decimal | None = None

    def __post_init__(self) -> None:
        for value in (
            self.minimax_regret,
            self.worst_case_loss,
            self.tail_loss,
            self.cost,
            self.turnover,
        ):
            require_decimal(value)
        if self.expected_utility is not None:
            require_decimal(self.expected_utility)
        require_aware(self.obligation_review_at)


@dataclass(frozen=True, slots=True)
class AgentSelection:
    selection_ref: str
    feasible_action_set_ref: str
    selection_disposition: str
    selected_candidate_ref: str
    ranked_alternative_refs: tuple[str, ...]
    no_action_candidate_ref: str
    retained_soft_warning_refs: tuple[str, ...]
    residual_unknown_refs: tuple[str, ...]
    selection_reason: str
    decision_criterion_policy_ref: str
    decision_criterion_policy_digest: str
    no_action_despite_non_abstain_feasible: bool
    selection_digest: str


def _error(code: str, message: str) -> DomainResult:
    return DomainResult(
        status=ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="SELECTION",
            retryability="NEVER",
            message=message,
        ),
    )


def _tie_key(
    metric: CandidateDecisionMetrics,
    tie_break_order: tuple[str, ...],
) -> tuple:
    fields = {
        "LOWER_WORST_CASE_LOSS": metric.worst_case_loss,
        "LOWER_TAIL_LOSS": metric.tail_loss,
        "LOWER_COST": metric.cost,
        "LOWER_TURNOVER": metric.turnover,
        "EARLIER_OBLIGATION_REVIEW": (
            metric.obligation_review_at.isoformat()
            if metric.obligation_review_at is not None
            else "9999-12-31T23:59:59.999999+00:00"
        ),
        "CANONICAL_ACTION_ID": metric.candidate_ref,
    }
    return tuple(fields[token] for token in tie_break_order) + (
        metric.candidate_ref,
    )


def select_by_frozen_policy(
    *,
    feasible_set: FeasibleActionSet,
    context: DecisionContext,
    policy: DecisionCriterionPolicy,
    metrics: tuple[CandidateDecisionMetrics, ...],
    requested_candidate_ref: str | None = None,
    selection_reason: str = "deterministic frozen-policy selection",
) -> DomainResult[AgentSelection]:
    """Compute and validate the winner without creating a candidate or target."""

    if not (policy.valid_from <= context.decision_cutoff < policy.valid_until):
        return _error(
            "SELECTION_CRITERION_POLICY_MISMATCH",
            "decision cutoff is outside frozen policy validity",
        )
    bindings = {
        (policy.policy_id, policy.policy_digest),
        (
            context.decision_criterion_policy_ref,
            context.decision_criterion_policy_digest,
        ),
        (
            feasible_set.decision_criterion_policy_ref,
            feasible_set.decision_criterion_policy_digest,
        ),
    }
    if len(bindings) != 1:
        return _error(
            "SELECTION_CRITERION_POLICY_MISMATCH",
            "context, feasible set, and selector policy differ",
        )
    feasible_refs = {item.candidate_ref for item in feasible_set.feasible_candidates}
    metrics_by_ref = {metric.candidate_ref: metric for metric in metrics}
    if len(metrics_by_ref) != len(metrics) or set(metrics_by_ref) != feasible_refs:
        return _error(
            "FEASIBLE_SET_INCOMPLETE",
            "selection metrics must cover the exact feasible set",
        )
    if requested_candidate_ref is not None and requested_candidate_ref not in feasible_refs:
        return _error(
            "SELECTOR_OUTSIDE_FEASIBLE_SET",
            "Agent selector requested a candidate outside the feasible set",
        )
    if context.probability_status is ProbabilityStatus.CALIBRATED_OOS:
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "calibrated expected utility is unreachable in E0",
        )
    if context.probability_status is ProbabilityStatus.UNKNOWN:
        winner_ref = feasible_set.no_action_candidate_ref
        ranked_refs = tuple(
            sorted(feasible_refs - {winner_ref})
        )
    else:
        if any(metric.expected_utility is not None for metric in metrics):
            return _error(
                "PROBABILITY_USE_UNAUTHORIZED_E0",
                "ordinal selection cannot consume expected utility",
            )
        nondominated = [metric for metric in metrics if not metric.robust_dominated]
        if not nondominated:
            nondominated = [metrics_by_ref[feasible_set.no_action_candidate_ref]]
        minimum_regret = min(metric.minimax_regret for metric in nondominated)
        regret_tied = [
            metric
            for metric in nondominated
            if metric.minimax_regret == minimum_regret
        ]
        ordered = sorted(
            regret_tied,
            key=lambda metric: _tie_key(metric, policy.tie_break_order),
        )
        winner_ref = ordered[0].candidate_ref
        ranked_refs = tuple(
            metric.candidate_ref
            for metric in sorted(
                (metric for metric in metrics if metric.candidate_ref != winner_ref),
                key=lambda metric: (
                    metric.robust_dominated,
                    metric.minimax_regret,
                    _tie_key(metric, policy.tie_break_order),
                ),
            )
        )
    if requested_candidate_ref is not None and requested_candidate_ref != winner_ref:
        return _error(
            "SELECTION_CRITERION_POLICY_MISMATCH",
            "Agent suggestion cannot override the deterministic frozen criterion",
        )
    is_no_action = winner_ref == feasible_set.no_action_candidate_ref
    digest = canonical_digest(
        {
            "feasible_set_digest": feasible_set.feasible_set_digest,
            "winner": winner_ref,
            "ranked_alternatives": ranked_refs,
            "no_action_candidate_ref": feasible_set.no_action_candidate_ref,
            "retained_soft_warnings": feasible_set.retained_soft_verdict_refs,
            "residual_unknowns": (),
            "selection_reason": selection_reason,
            "policy_ref": policy.policy_id,
            "policy_digest": policy.policy_digest,
            "no_action_despite_non_abstain": (
                winner_ref == feasible_set.no_action_candidate_ref
                and feasible_set.non_abstain_feasible_count > 0
            ),
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=AgentSelection(
            selection_ref=f"selection:{digest}",
            feasible_action_set_ref=feasible_set.feasible_set_digest,
            selection_disposition=(
                "SELECT_NO_ACTION" if is_no_action else "SELECT_ACTION"
            ),
            selected_candidate_ref=winner_ref,
            ranked_alternative_refs=ranked_refs,
            no_action_candidate_ref=feasible_set.no_action_candidate_ref,
            retained_soft_warning_refs=feasible_set.retained_soft_verdict_refs,
            residual_unknown_refs=(),
            selection_reason=selection_reason,
            decision_criterion_policy_ref=policy.policy_id,
            decision_criterion_policy_digest=policy.policy_digest,
            no_action_despite_non_abstain_feasible=(
                is_no_action and feasible_set.non_abstain_feasible_count > 0
            ),
            selection_digest=digest,
        ),
    )
