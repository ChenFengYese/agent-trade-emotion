"""Deterministic challenge validation and candidate assembly."""

from __future__ import annotations

from dataclasses import replace
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
from ..policy import ActionIntent, GeometryOperation, ProtectiveActionType
from .model import (
    BLIND_REQUIRED_OMISSIONS,
    AtomicEffectType,
    CandidateBundle,
    CandidateBundleSet,
    ChallengeDisposition,
    ChallengeEnvelope,
    ChallengeMode,
    ChallengeTerminalEffect,
    ProposedActionPlan,
)


def _error(code: str, message: str, *, unknown: bool = False) -> DomainResult:
    return DomainResult(
        status=ReducerStatus.UNKNOWN if unknown else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="DELIBERATION",
            retryability="AFTER_INPUT_REPAIR" if unknown else "NEVER",
            message=message,
        ),
    )


def validate_challenge_boundary(
    envelope: ChallengeEnvelope,
    *,
    exact_proposal_ref: str,
) -> DomainResult[ChallengeEnvelope]:
    """Prove proposal visibility or blindness without inferring either."""

    if envelope.challenge_mode is ChallengeMode.POST_PROPOSAL:
        if (
            envelope.proposal_ref != exact_proposal_ref
            or envelope.role_context_proposal_ref != exact_proposal_ref
            or envelope.blinding_proof_ref is not None
            or any(claim.proposal_ref != exact_proposal_ref for claim in envelope.claims)
        ):
            return _error(
                "CHALLENGE_POST_PROPOSAL_LINK_MISMATCH",
                "post-proposal challenge must bind the exact proposal everywhere",
            )
    elif envelope.challenge_mode is ChallengeMode.BLIND_CONTEXT_ONLY:
        if (
            envelope.proposal_ref is not None
            or envelope.role_context_proposal_ref is not None
            or envelope.blinding_proof_ref is None
            or not BLIND_REQUIRED_OMISSIONS.issubset(
                envelope.omitted_projection_classes
            )
            or any(claim.proposal_ref is not None for claim in envelope.claims)
            or any(claim.claims_proposal_byte_defect for claim in envelope.claims)
        ):
            return _error(
                "BLIND_CHALLENGE_PROPOSAL_HIDDEN",
                "blind challenge leaked or claimed unseen proposal bytes",
            )
    else:
        return _error("CHALLENGE_MODE_UNKNOWN", "challenge mode is not registered")
    return DomainResult(status=ReducerStatus.APPLIED, value=envelope)


def _exact_enum(value: object, enum_type: type) -> bool:
    return isinstance(value, enum_type)


def validate_proposed_action_plan(
    plan: ProposedActionPlan,
) -> DomainResult[ProposedActionPlan]:
    """Validate semantic facets; this still grants no action authority."""

    if (
        plan.system_mode != SYSTEM_MODE
        or plan.external_execution_authority != EXTERNAL_EXECUTION_AUTHORITY
        or plan.executable
    ):
        return _error(
            "CANDIDATE_E0_AUTHORITY_OVERREACH",
            "proposal attempted to change E0 authority or executability",
        )
    if not _exact_enum(plan.action_intent, ActionIntent):
        return _error("ACTION_INTENT_UNKNOWN", "action intent is not closed")
    if not _exact_enum(plan.protective_action_type, ProtectiveActionType):
        return _error(
            "PROTECTIVE_ACTION_TYPE_UNKNOWN",
            "protective action is not closed",
        )
    if not _exact_enum(plan.geometry_operation, GeometryOperation):
        return _error("GEOMETRY_OPERATION_UNKNOWN", "geometry operation is not closed")
    if (
        len(plan.atomic_effect_types) != len(set(plan.atomic_effect_types))
        or any(
            not _exact_enum(effect, AtomicEffectType)
            for effect in plan.atomic_effect_types
        )
    ):
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "atomic effects must be unique registered effects",
        )
    if plan.requested_lot_role == "HEDGE":
        return _error(
            "CANDIDATE_HEDGE_FORBIDDEN_E0",
            "HEDGE remains auditable but cannot become an E0 candidate",
        )
    if plan.action_intent in {
        ActionIntent.KEEP_CORE,
        ActionIntent.REDUCE_TACTICAL,
        ActionIntent.PARTIAL_PROFIT,
        ActionIntent.EXIT_STRATEGIC,
        ActionIntent.EXIT_TO_REENTRY_PENDING,
        ActionIntent.NO_ACTION_WITH_OBLIGATION,
    } and (plan.position_delta > 0 or plan.risk_delta > 0):
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "non-add intent concealed a positive position or risk delta",
        )
    if plan.action_intent is ActionIntent.NO_ACTION_WITH_OBLIGATION and (
        plan.position_delta != 0 or plan.risk_delta != 0
    ):
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "no-action cannot conceal any position or risk mutation",
        )
    create_reentry = AtomicEffectType.CREATE_REENTRY_CONTRACT in set(
        plan.atomic_effect_types
    )
    if plan.action_intent is ActionIntent.EXIT_TO_REENTRY_PENDING:
        if not create_reentry or plan.strategic_status not in {"ACTIVE", "CHALLENGED"}:
            return _error(
                "REENTRY_CREATION_ATOMIC_EFFECT_REQUIRED",
                "surviving thesis exit requires one atomic reentry creation effect",
            )
    elif create_reentry:
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "only exit-to-reentry-pending may create a reentry contract",
        )
    effects = set(plan.atomic_effect_types)
    if AtomicEffectType.RESERVE_STAGE_RISK in effects and plan.action_intent not in {
        ActionIntent.ACTIVATE_REGISTERED_STAGE,
        ActionIntent.REENTER_PARTIAL,
    }:
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "stage-risk reservation requires stage activation or reentry",
        )
    if AtomicEffectType.RELEASE_STAGE_RISK in effects and plan.action_intent not in {
        ActionIntent.REDUCE_TACTICAL,
        ActionIntent.PARTIAL_PROFIT,
        ActionIntent.EXIT_STRATEGIC,
        ActionIntent.EXIT_TO_REENTRY_PENDING,
    }:
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "stage-risk release requires an explicit reduction or exit intent",
        )
    if (
        AtomicEffectType.REQUEST_PORTFOLIO_RECONCILIATION in effects
        and plan.protective_action_type is not ProtectiveActionType.RECONCILIATION
    ):
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "portfolio reconciliation effect requires the reconciliation facet",
        )
    if plan.action_intent in {
        ActionIntent.ACTIVATE_REGISTERED_STAGE,
        ActionIntent.REENTER_PARTIAL,
    }:
        if (
            plan.registered_stage_ref is None
            or plan.requested_lot_role not in {"CORE", "TACTICAL"}
        ):
            return _error(
                "CANDIDATE_STAGE_REF_MISSING",
                "stage activation or reentry requires an exact CORE/TACTICAL stage",
            )
    if plan.action_intent is ActionIntent.EXIT_STRATEGIC and not (
        plan.strategic_invalidation_receipt_ref
        or plan.terminal_close_receipt_ref
    ):
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "strategic exit requires independent invalidation or terminal close",
        )
    if plan.geometry_operation is GeometryOperation.REVISE_PROTECTION and (
        plan.protective_action_type is ProtectiveActionType.NONE
        or plan.barrier_revision_ref is None
        or plan.ack_ordering_policy_ref is None
    ):
        return _error(
            "ACTION_FACET_INCOMPATIBLE",
            "protection revision requires protective action, barrier, and ACK policy",
        )
    if plan.action_intent is ActionIntent.NO_ACTION_WITH_OBLIGATION and (
        plan.position_delta > 0
        or plan.risk_delta > 0
        or plan.next_review_at is None
        or (
            not plan.unmet_dependency_refs
            and plan.no_opportunity_reason_ref is None
        )
    ):
        return _error(
            "SELECTION_ABSTAIN_OBLIGATION_MISSING",
            "no-action must carry no new risk and an exact review obligation",
        )
    if (
        plan.action_intent is ActionIntent.NO_ACTION_WITH_OBLIGATION
        and plan.next_review_at is not None
        and plan.next_review_at < plan.decision_cutoff
    ):
        return _error(
            "SELECTION_ABSTAIN_OBLIGATION_MISSING",
            "no-action review clock cannot already be overdue",
        )
    if plan.action_intent is not ActionIntent.NO_ACTION_WITH_OBLIGATION and (
        plan.next_review_at is not None
        and plan.next_review_at < plan.decision_cutoff
    ):
        return _error("CLOCK_TIME_INVALID", "review cannot precede decision cutoff")
    return DomainResult(status=ReducerStatus.APPLIED, value=plan)


def _plan_semantic_fingerprint(plan: ProposedActionPlan) -> str:
    return canonical_digest(
        {
            "episode": plan.strategic_episode_ref,
            "cutoff": plan.decision_cutoff.isoformat(),
            "path": plan.path_ref,
            "envelope": plan.cross_timescale_control_envelope_ref,
            "strategic_facet": plan.strategic_delta_facet_ref,
            "position_facet": plan.position_facet_ref,
            "reentry_facet": plan.reentry_facet_ref,
            "execution_facet": plan.execution_tactic_facet_ref,
            "intent": plan.action_intent.value,
            "protective": plan.protective_action_type.value,
            "geometry": plan.geometry_operation.value,
            "effects": tuple(effect.value for effect in plan.atomic_effect_types),
            "position_delta": plan.position_delta,
            "risk_delta": plan.risk_delta,
            "stage_ref": plan.registered_stage_ref,
            "lot_role": plan.requested_lot_role,
            "strategic_status": plan.strategic_status,
            "invalidation_ref": plan.strategic_invalidation_receipt_ref,
            "terminal_close_ref": plan.terminal_close_receipt_ref,
            "barrier_revision_ref": plan.barrier_revision_ref,
            "ack_policy_ref": plan.ack_ordering_policy_ref,
            "next_review_at": (
                plan.next_review_at.isoformat()
                if plan.next_review_at is not None
                else None
            ),
            "unmet_dependencies": plan.unmet_dependency_refs,
            "no_opportunity_reason": plan.no_opportunity_reason_ref,
        }
    )


def make_no_action_plan(
    *,
    strategic_episode_ref: str,
    decision_cutoff: datetime,
    path_ref: str,
    envelope_ref: str,
    next_review_at: datetime,
    unmet_dependency_refs: tuple[str, ...] = (),
    no_opportunity_reason_ref: str | None = None,
) -> ProposedActionPlan:
    """Construct the mandatory explicit no-action candidate."""

    seed = {
        "episode": strategic_episode_ref,
        "cutoff": decision_cutoff.isoformat(),
        "path": path_ref,
        "review": next_review_at.isoformat(),
        "dependencies": unmet_dependency_refs,
        "reason": no_opportunity_reason_ref,
    }
    fingerprint = canonical_digest(seed)
    return ProposedActionPlan(
        plan_id=f"no-action:{fingerprint}",
        strategic_episode_ref=strategic_episode_ref,
        decision_cutoff=decision_cutoff,
        path_ref=path_ref,
        cross_timescale_control_envelope_ref=envelope_ref,
        strategic_delta_facet_ref=f"strategic-no-change:{fingerprint}",
        position_facet_ref=f"position-no-change:{fingerprint}",
        action_intent=ActionIntent.NO_ACTION_WITH_OBLIGATION,
        protective_action_type=ProtectiveActionType.NONE,
        geometry_operation=GeometryOperation.KEEP,
        atomic_effect_types=(),
        position_delta=Decimal("0"),
        risk_delta=Decimal("0"),
        next_review_at=next_review_at,
        unmet_dependency_refs=unmet_dependency_refs,
        no_opportunity_reason_ref=no_opportunity_reason_ref,
        # The assembler independently computes the complete semantic
        # fingerprint.  Agent-supplied fingerprints are never trusted.
        semantic_fingerprint="",
    )


def assemble_candidate_bundles(
    *,
    proposal_ref: str,
    challenge: ChallengeEnvelope,
    disposition: ChallengeDisposition,
    proposed_plans: tuple[ProposedActionPlan, ...],
    no_action_plan: ProposedActionPlan,
    required_meaningful_plan_refs: frozenset[str],
) -> DomainResult[CandidateBundleSet]:
    """Assemble the complete registered action space or emit no set at all."""

    boundary = validate_challenge_boundary(
        challenge, exact_proposal_ref=proposal_ref
    )
    if boundary.status is not ReducerStatus.APPLIED:
        return boundary
    if disposition.proposal_ref != proposal_ref or disposition.challenge_ref != (
        challenge.challenge_id
    ):
        return _error(
            "CHALLENGE_DISPOSITION_LINK_MISMATCH",
            "disposition must join the exact frozen proposal and challenge",
        )
    if disposition.terminal_effect is ChallengeTerminalEffect.REPROPOSAL_REQUIRED:
        return _error(
            "CHALLENGE_REPROPOSAL_REQUIRED",
            "hard structural defect forbids candidate assembly",
        )
    if no_action_plan.action_intent is not ActionIntent.NO_ACTION_WITH_OBLIGATION:
        return _error(
            "FEASIBLE_SET_NO_ACTION_MISSING",
            "declared no-action plan is not a lawful no-action obligation",
        )
    supplied = {plan.plan_id for plan in proposed_plans}
    if not required_meaningful_plan_refs.issubset(supplied):
        return _error(
            "CANDIDATE_THEORY_ACTION_OMITTED",
            "one or more theory-defined meaningful actions were omitted",
        )
    all_plans = (*proposed_plans, no_action_plan)
    if len({plan.plan_id for plan in all_plans}) != len(all_plans):
        return _error("CANDIDATE_DUPLICATE_PLAN", "plan identity is not unique")
    candidates: list[CandidateBundle] = []
    fingerprints: set[str] = set()
    for plan in all_plans:
        validated = validate_proposed_action_plan(plan)
        if validated.status is not ReducerStatus.APPLIED:
            # Fail the assembly atomically.  In particular, no candidate can
            # escape from an invocation that contained an E0 HEDGE request.
            return validated
        fingerprint = _plan_semantic_fingerprint(plan)
        if plan.semantic_fingerprint and plan.semantic_fingerprint != fingerprint:
            return _error(
                "PROPOSED_ACTION_SEMANTIC_FINGERPRINT_MISMATCH",
                "Agent-supplied semantic fingerprint differs from domain recomputation",
            )
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        candidate_digest = canonical_digest(
            {
                "proposal_ref": proposal_ref,
                "plan_ref": plan.plan_id,
                "semantic_fingerprint": fingerprint,
            }
        )
        candidates.append(
            CandidateBundle(
                candidate_ref=f"candidate:{candidate_digest}",
                proposal_ref=proposal_ref,
                proposed_action_plan_ref=plan.plan_id,
                plan=replace(plan, semantic_fingerprint=fingerprint),
                semantic_fingerprint=fingerprint,
                candidate_digest=candidate_digest,
            )
        )
    no_action = next(
        (
            candidate
            for candidate in candidates
            if candidate.proposed_action_plan_ref == no_action_plan.plan_id
        ),
        None,
    )
    if no_action is None:
        return _error(
            "FEASIBLE_SET_NO_ACTION_MISSING",
            "mandatory no-action candidate was deduplicated or absent",
        )
    set_digest = canonical_digest(
        {
            "proposal_ref": proposal_ref,
            "challenge_ref": challenge.challenge_id,
            "disposition_ref": disposition.disposition_id,
            "candidate_digests": tuple(
                sorted(candidate.candidate_digest for candidate in candidates)
            ),
            "no_action_candidate_ref": no_action.candidate_ref,
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=CandidateBundleSet(
            proposal_ref=proposal_ref,
            challenge_ref=challenge.challenge_id,
            challenge_disposition_ref=disposition.disposition_id,
            candidates=tuple(sorted(candidates, key=lambda item: item.candidate_ref)),
            no_action_candidate_ref=no_action.candidate_ref,
            rejected_plans=(),
            candidate_set_digest=set_digest,
        ),
    )
