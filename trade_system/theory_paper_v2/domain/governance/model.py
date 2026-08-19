"""Constraint, feasible-set, and governance records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..common import EXTERNAL_EXECUTION_AUTHORITY
from ..deliberation.model import CandidateBundle, CandidateBundleSet


class ConstraintClass(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    INFORMATIONAL = "INFORMATIONAL"
    UNKNOWN_DEPENDENCY = "UNKNOWN_DEPENDENCY"


class ConstraintDecision(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ConstraintEvaluation:
    constraint_id: str
    verdict: ConstraintDecision
    evidence_or_calculation_refs: tuple[str, ...]
    failed_field_json_pointers: tuple[str, ...] = ()
    protective_actions_remain_allowed: bool = True
    next_lawful_evidence_or_review_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.constraint_id
            or not self.evidence_or_calculation_refs
            or not isinstance(self.verdict, ConstraintDecision)
        ):
            raise ValueError("CONSTRAINT_EVALUATION_INCOMPLETE")


@dataclass(frozen=True, slots=True)
class ConstraintVerdict:
    verdict_ref: str
    candidate_ref: str
    constraint_id: str
    constraint_class: ConstraintClass
    verdict: ConstraintDecision
    failed_field_json_pointers: tuple[str, ...]
    evidence_or_calculation_refs: tuple[str, ...]
    affected_candidate_ref: str
    protective_actions_remain_allowed: bool
    next_lawful_evidence_or_review_refs: tuple[str, ...]
    verdict_digest: str


@dataclass(frozen=True, slots=True)
class ConstraintVerdictSet:
    candidate_bundle_set_ref: str
    verdicts: tuple[ConstraintVerdict, ...]
    required_constraint_ids: frozenset[str]
    constraint_engine_version: str
    verdict_set_digest: str


@dataclass(frozen=True, slots=True)
class RemovedCandidate:
    candidate_ref: str
    removing_verdict_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeasibleActionSet:
    candidate_bundle_set: CandidateBundleSet
    feasible_candidates: tuple[CandidateBundle, ...]
    removed_candidates: tuple[RemovedCandidate, ...]
    no_action_candidate_ref: str
    non_abstain_feasible_count: int
    no_hard_feasible_action: bool
    unexpectedly_empty_before_no_action: bool
    retained_soft_verdict_refs: tuple[str, ...]
    retained_informational_verdict_refs: tuple[str, ...]
    decision_criterion_policy_ref: str
    decision_criterion_policy_digest: str
    feasible_set_digest: str

    def __post_init__(self) -> None:
        refs = tuple(candidate.candidate_ref for candidate in self.feasible_candidates)
        if not refs or self.no_action_candidate_ref not in refs:
            raise ValueError("FEASIBLE_SET_NO_ACTION_MISSING")
        if len(refs) != len(set(refs)):
            raise ValueError("FEASIBLE_SET_DUPLICATE_CANDIDATE")

    def by_ref(self) -> dict[str, CandidateBundle]:
        return {
            candidate.candidate_ref: candidate
            for candidate in self.feasible_candidates
        }


class GovernanceVerdict(StrEnum):
    PASS = "PASS"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class GovernanceAssessmentReceipt:
    selection_ref: str
    selection_valid: GovernanceVerdict
    market_feasibility: str
    counterfactual_permission: str
    schema_pit_state_verdict_refs: tuple[str, ...]
    hard_constraint_verdict_refs: tuple[str, ...]
    challenge_disposition_ref: str
    expected_head_ref: str
    adapter_allowlist: tuple[str, ...] = ("OFFLINE_REPLAY_ADAPTER",)
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False
