"""Complete, deterministic evaluation of the frozen hard-constraint registry."""

from __future__ import annotations

from collections.abc import Mapping

from ..common import DomainError, DomainResult, ReducerStatus
from ..contracts.canonical import canonical_digest
from ..contracts.catalog import CONSTRAINT_IDS
from ..deliberation.model import CandidateBundleSet
from .model import (
    ConstraintClass,
    ConstraintDecision,
    ConstraintEvaluation,
    ConstraintVerdict,
    ConstraintVerdictSet,
    FeasibleActionSet,
    RemovedCandidate,
)


REQUIRED_HARD_CONSTRAINT_IDS = frozenset(CONSTRAINT_IDS)


def _error(code: str, message: str, *, unknown: bool = False) -> DomainResult:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if unknown else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="GOVERNANCE",
            retryability="AFTER_INPUT_REPAIR" if unknown else "NEVER",
            message=message,
        ),
    )


def evaluate_hard_constraints(
    *,
    candidate_set: CandidateBundleSet,
    evaluations_by_candidate: Mapping[
        str, Mapping[str, ConstraintEvaluation]
    ],
    constraint_engine_version: str,
) -> DomainResult[ConstraintVerdictSet]:
    """Require one verdict for every one of the frozen 33 constraints."""

    candidate_refs = {candidate.candidate_ref for candidate in candidate_set.candidates}
    if set(evaluations_by_candidate) != candidate_refs:
        return _error(
            "FEASIBLE_SET_INCOMPLETE",
            "constraint candidate coverage differs from the candidate bundle set",
        )
    verdicts: list[ConstraintVerdict] = []
    for candidate_ref in sorted(candidate_refs):
        evaluations = evaluations_by_candidate[candidate_ref]
        if set(evaluations) != REQUIRED_HARD_CONSTRAINT_IDS:
            return _error(
                "CONSTRAINT_UNREGISTERED",
                "constraint coverage must equal the frozen 33-ID registry",
            )
        for constraint_id in sorted(REQUIRED_HARD_CONSTRAINT_IDS):
            evaluation = evaluations[constraint_id]
            if evaluation.constraint_id != constraint_id:
                return _error(
                    "CONSTRAINT_UNREGISTERED",
                    "constraint key and payload identity differ",
                )
            digest = canonical_digest(
                {
                    "candidate_ref": candidate_ref,
                    "constraint_id": constraint_id,
                    "class": ConstraintClass.HARD.value,
                    "verdict": evaluation.verdict.value,
                    "failed_fields": evaluation.failed_field_json_pointers,
                    "evidence": evaluation.evidence_or_calculation_refs,
                }
            )
            verdicts.append(
                ConstraintVerdict(
                    verdict_ref=f"constraint-verdict:{digest}",
                    candidate_ref=candidate_ref,
                    constraint_id=constraint_id,
                    constraint_class=ConstraintClass.HARD,
                    verdict=evaluation.verdict,
                    failed_field_json_pointers=evaluation.failed_field_json_pointers,
                    evidence_or_calculation_refs=evaluation.evidence_or_calculation_refs,
                    affected_candidate_ref=candidate_ref,
                    protective_actions_remain_allowed=(
                        evaluation.protective_actions_remain_allowed
                    ),
                    next_lawful_evidence_or_review_refs=(
                        evaluation.next_lawful_evidence_or_review_refs
                    ),
                    verdict_digest=digest,
                )
            )
    set_digest = canonical_digest(
        {
            "candidate_bundle_set_digest": candidate_set.candidate_set_digest,
            "constraint_engine_version": constraint_engine_version,
            "verdict_digests": tuple(
                verdict.verdict_digest for verdict in verdicts
            ),
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=ConstraintVerdictSet(
            candidate_bundle_set_ref=candidate_set.candidate_set_digest,
            verdicts=tuple(verdicts),
            required_constraint_ids=REQUIRED_HARD_CONSTRAINT_IDS,
            constraint_engine_version=constraint_engine_version,
            verdict_set_digest=set_digest,
        ),
    )


def build_feasible_action_set(
    *,
    candidate_set: CandidateBundleSet,
    hard_verdict_set: ConstraintVerdictSet,
    decision_criterion_policy_ref: str,
    decision_criterion_policy_digest: str,
    candidate_local_unknowns: tuple[ConstraintVerdict, ...] = (),
    soft_or_informational_verdicts: tuple[ConstraintVerdict, ...] = (),
) -> DomainResult[FeasibleActionSet]:
    """Remove candidates only under the two contract-authorized predicates."""

    if hard_verdict_set.candidate_bundle_set_ref != candidate_set.candidate_set_digest:
        return _error(
            "FEASIBLE_SET_INCOMPLETE",
            "constraint verdict set is not bound to this candidate set",
        )
    candidate_refs = {candidate.candidate_ref for candidate in candidate_set.candidates}
    coverage: dict[str, set[str]] = {ref: set() for ref in candidate_refs}
    removals: dict[str, list[str]] = {ref: [] for ref in candidate_refs}
    for verdict in hard_verdict_set.verdicts:
        if (
            verdict.candidate_ref not in candidate_refs
            or verdict.affected_candidate_ref != verdict.candidate_ref
            or verdict.constraint_class is not ConstraintClass.HARD
        ):
            return _error(
                "FEASIBLE_SET_INCOMPLETE",
                "hard verdict is not local to one registered candidate",
            )
        coverage[verdict.candidate_ref].add(verdict.constraint_id)
        if verdict.verdict is ConstraintDecision.FAIL:
            removals[verdict.candidate_ref].append(verdict.verdict_ref)
        elif verdict.verdict is ConstraintDecision.UNKNOWN:
            return _error(
                "CONSTRAINT_REQUIRED_RESULT_UNKNOWN",
                "a frozen hard constraint remained unresolved",
                unknown=True,
            )
    if any(ids != REQUIRED_HARD_CONSTRAINT_IDS for ids in coverage.values()):
        return _error(
            "FEASIBLE_SET_INCOMPLETE",
            "one or more candidates lack complete hard-constraint coverage",
        )
    for verdict in candidate_local_unknowns:
        if (
            verdict.constraint_class is not ConstraintClass.UNKNOWN_DEPENDENCY
            or verdict.verdict is not ConstraintDecision.UNKNOWN
            or verdict.candidate_ref not in candidate_refs
            or verdict.affected_candidate_ref != verdict.candidate_ref
        ):
            return _error(
                "CONSTRAINT_UNREGISTERED",
                "unknown dependency removal must be candidate-local UNKNOWN",
            )
        removals[verdict.candidate_ref].append(verdict.verdict_ref)
    retained_soft: list[str] = []
    retained_informational: list[str] = []
    for verdict in soft_or_informational_verdicts:
        if verdict.candidate_ref not in candidate_refs:
            return _error(
                "CONSTRAINT_UNREGISTERED",
                "soft/informational verdict names an unknown candidate",
            )
        if verdict.constraint_class is ConstraintClass.SOFT:
            retained_soft.append(verdict.verdict_ref)
        elif verdict.constraint_class is ConstraintClass.INFORMATIONAL:
            retained_informational.append(verdict.verdict_ref)
        else:
            return _error(
                "CONSTRAINT_SOFT_REMOVAL_FORBIDDEN",
                "this channel accepts only retained soft/informational findings",
            )
    if removals[candidate_set.no_action_candidate_ref]:
        return _error(
            "FEASIBLE_SET_NO_ACTION_MISSING",
            "the mandatory lawful no-action candidate was removed",
        )
    feasible = tuple(
        candidate
        for candidate in candidate_set.candidates
        if not removals[candidate.candidate_ref]
    )
    if not feasible:
        return _error(
            "FEASIBLE_SET_NO_ACTION_MISSING",
            "no valid feasible action set can be emitted",
        )
    removed = tuple(
        RemovedCandidate(ref, tuple(removals[ref]))
        for ref in sorted(candidate_refs)
        if removals[ref]
    )
    non_abstain = sum(not candidate.is_no_action for candidate in feasible)
    feasible_digest = canonical_digest(
        {
            "candidate_set_digest": candidate_set.candidate_set_digest,
            "verdict_set_digest": hard_verdict_set.verdict_set_digest,
            "feasible_candidate_refs": tuple(
                candidate.candidate_ref for candidate in feasible
            ),
            "removed": tuple(
                (entry.candidate_ref, entry.removing_verdict_refs)
                for entry in removed
            ),
            "no_action_candidate_ref": candidate_set.no_action_candidate_ref,
            "non_abstain_feasible_count": non_abstain,
            "no_hard_feasible_action": non_abstain == 0,
            "unexpectedly_empty_before_no_action": non_abstain == 0,
            "retained_soft": tuple(sorted(retained_soft)),
            "retained_informational": tuple(sorted(retained_informational)),
            "policy_ref": decision_criterion_policy_ref,
            "policy_digest": decision_criterion_policy_digest,
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=FeasibleActionSet(
            candidate_bundle_set=candidate_set,
            feasible_candidates=feasible,
            removed_candidates=removed,
            no_action_candidate_ref=candidate_set.no_action_candidate_ref,
            non_abstain_feasible_count=non_abstain,
            no_hard_feasible_action=non_abstain == 0,
            unexpectedly_empty_before_no_action=non_abstain == 0,
            retained_soft_verdict_refs=tuple(sorted(retained_soft)),
            retained_informational_verdict_refs=tuple(
                sorted(retained_informational)
            ),
            decision_criterion_policy_ref=decision_criterion_policy_ref,
            decision_criterion_policy_digest=decision_criterion_policy_digest,
            feasible_set_digest=feasible_digest,
        ),
    )
