"""Immutable deliberation objects.

Agent outputs are deliberately represented as untrusted plans.  They do not
become candidates until the deterministic assembler validates all orthogonal
facets and the E0 authority tuple.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ..common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ..policy import ActionIntent, GeometryOperation, ProtectiveActionType


class AtomicEffectType(StrEnum):
    CREATE_REENTRY_CONTRACT = "CREATE_REENTRY_CONTRACT"
    RESERVE_STAGE_RISK = "RESERVE_STAGE_RISK"
    RELEASE_STAGE_RISK = "RELEASE_STAGE_RISK"
    REGISTER_PROTECTIVE_BARRIER = "REGISTER_PROTECTIVE_BARRIER"
    REQUEST_PORTFOLIO_RECONCILIATION = "REQUEST_PORTFOLIO_RECONCILIATION"


class ChallengeMode(StrEnum):
    POST_PROPOSAL = "POST_PROPOSAL"
    BLIND_CONTEXT_ONLY = "BLIND_CONTEXT_ONLY"


class ChallengeCategory(StrEnum):
    PREMISE_CONFLICT = "PREMISE_CONFLICT"
    CLAIMED_FALSIFIER = "CLAIMED_FALSIFIER"
    OMITTED_COMPETING_PATH = "OMITTED_COMPETING_PATH"
    MISSING_SOURCE_OR_DEPENDENCY = "MISSING_SOURCE_OR_DEPENDENCY"
    STATE_CONTINUITY_BREAK = "STATE_CONTINUITY_BREAK"
    TIME_SCALE_OVERREACH = "TIME_SCALE_OVERREACH"
    EXIT_REENTRY_ASYMMETRY = "EXIT_REENTRY_ASYMMETRY"
    ACTION_SPACE_COLLAPSE_RISK = "ACTION_SPACE_COLLAPSE_RISK"
    UNKNOWN_COERCION = "UNKNOWN_COERCION"
    GEOMETRY_POSITION_INCONSISTENCY = "GEOMETRY_POSITION_INCONSISTENCY"
    ROLE_OVERREACH = "ROLE_OVERREACH"


class ChallengeResult(StrEnum):
    VERIFIED_HARD_STRUCTURAL_DEFECT = "VERIFIED_HARD_STRUCTURAL_DEFECT"
    SOFT = "SOFT"
    INFORMATIONAL = "INFORMATIONAL"
    UNVERIFIED = "UNVERIFIED"


class ChallengeTerminalEffect(StrEnum):
    REPROPOSAL_REQUIRED = "REPROPOSAL_REQUIRED"
    NONE = "NONE"


BLIND_REQUIRED_OMISSIONS = frozenset(
    {
        "AGENT_PROPOSAL_ENVELOPE",
        "PROPOSED_ACTION_PLAN",
        "PROPOSAL_EXPLANATION",
        "PROPOSAL_DIGEST",
    }
)


def _require_aware(value: datetime | None, code: str) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(code)


def _require_decimal(value: Decimal, code: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(code)


@dataclass(frozen=True, slots=True)
class ProposedActionPlan:
    """One untrusted action composition with three orthogonal action facets."""

    plan_id: str
    strategic_episode_ref: str
    decision_cutoff: datetime
    path_ref: str
    cross_timescale_control_envelope_ref: str
    strategic_delta_facet_ref: str
    position_facet_ref: str
    action_intent: ActionIntent | str
    protective_action_type: ProtectiveActionType | str
    geometry_operation: GeometryOperation | str
    atomic_effect_types: tuple[AtomicEffectType | str, ...]
    position_delta: Decimal
    risk_delta: Decimal
    reentry_facet_ref: str | None = None
    execution_tactic_facet_ref: str | None = None
    registered_stage_ref: str | None = None
    requested_lot_role: str | None = None
    strategic_status: str = "ACTIVE"
    strategic_invalidation_receipt_ref: str | None = None
    terminal_close_receipt_ref: str | None = None
    barrier_revision_ref: str | None = None
    ack_ordering_policy_ref: str | None = None
    next_review_at: datetime | None = None
    unmet_dependency_refs: tuple[str, ...] = ()
    no_opportunity_reason_ref: str | None = None
    semantic_fingerprint: str = ""
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.plan_id,
            self.strategic_episode_ref,
            self.path_ref,
            self.cross_timescale_control_envelope_ref,
            self.strategic_delta_facet_ref,
            self.position_facet_ref,
        ):
            if not value:
                raise ValueError("PROPOSED_ACTION_PLAN_IDENTITY_MISSING")
        _require_aware(self.decision_cutoff, "CLOCK_TIME_INVALID")
        _require_aware(self.next_review_at, "CLOCK_TIME_INVALID")
        _require_decimal(self.position_delta, "POSITION_DELTA_DECIMAL_REQUIRED")
        _require_decimal(self.risk_delta, "RISK_DELTA_DECIMAL_REQUIRED")

    @property
    def introduces_new_risk(self) -> bool:
        return (
            self.position_delta > 0
            or self.risk_delta > 0
            or self.action_intent
            in {
                ActionIntent.ACTIVATE_REGISTERED_STAGE,
                ActionIntent.REENTER_PARTIAL,
            }
        )


@dataclass(frozen=True, slots=True)
class ChallengeClaim:
    claim_id: str
    proposal_ref: str | None
    subject_object_refs: tuple[str, ...]
    category: ChallengeCategory
    constraint_or_invariant_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    missing_dependency_refs: tuple[str, ...] = ()
    market_preference_only: bool = False
    requested_disposition: ChallengeResult = ChallengeResult.UNVERIFIED
    claims_proposal_byte_defect: bool = False

    def __post_init__(self) -> None:
        if not self.claim_id or not self.subject_object_refs:
            raise ValueError("CHALLENGE_CLAIM_INCOMPLETE")


@dataclass(frozen=True, slots=True)
class ChallengeEnvelope:
    challenge_id: str
    challenge_mode: ChallengeMode
    proposal_ref: str | None
    reasoning_strategy_contract_ref: str
    role_context_view_ref: str
    role_context_proposal_ref: str | None
    claims: tuple[ChallengeClaim, ...]
    omitted_projection_classes: frozenset[str] = frozenset()
    blinding_proof_ref: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.challenge_id
            or not self.reasoning_strategy_contract_ref
            or not self.role_context_view_ref
            or not self.claims
        ):
            raise ValueError("CHALLENGE_ENVELOPE_INCOMPLETE")


@dataclass(frozen=True, slots=True)
class ChallengeDisposition:
    disposition_id: str
    proposal_ref: str
    challenge_ref: str
    result: ChallengeResult
    verified_claim_refs: tuple[str, ...]
    verified_constraint_or_invariant_refs: tuple[str, ...]
    affected_proposed_plan_refs: tuple[str, ...]
    terminal_effect: ChallengeTerminalEffect
    deterministic_validator_version: str

    def __post_init__(self) -> None:
        if not self.disposition_id or not self.proposal_ref or not self.challenge_ref:
            raise ValueError("CHALLENGE_DISPOSITION_INCOMPLETE")
        if (
            self.terminal_effect is ChallengeTerminalEffect.REPROPOSAL_REQUIRED
            and (
                self.result is not ChallengeResult.VERIFIED_HARD_STRUCTURAL_DEFECT
                or not self.verified_claim_refs
                or not self.verified_constraint_or_invariant_refs
            )
        ):
            raise ValueError("CHALLENGE_HARD_DISPOSITION_UNPROVEN")


@dataclass(frozen=True, slots=True)
class CandidateBundle:
    candidate_ref: str
    proposal_ref: str
    proposed_action_plan_ref: str
    plan: ProposedActionPlan
    semantic_fingerprint: str
    candidate_digest: str

    @property
    def is_no_action(self) -> bool:
        return self.plan.action_intent is ActionIntent.NO_ACTION_WITH_OBLIGATION

    @property
    def introduces_new_risk(self) -> bool:
        return self.plan.introduces_new_risk


@dataclass(frozen=True, slots=True)
class CandidateRejection:
    proposed_action_plan_ref: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class CandidateBundleSet:
    proposal_ref: str
    challenge_ref: str
    challenge_disposition_ref: str
    candidates: tuple[CandidateBundle, ...]
    no_action_candidate_ref: str
    rejected_plans: tuple[CandidateRejection, ...]
    candidate_set_digest: str

    def __post_init__(self) -> None:
        refs = tuple(item.candidate_ref for item in self.candidates)
        if not refs or len(refs) != len(set(refs)):
            raise ValueError("CANDIDATE_SET_INVALID")
        if self.no_action_candidate_ref not in refs:
            raise ValueError("FEASIBLE_SET_NO_ACTION_MISSING")

    def by_ref(self) -> dict[str, CandidateBundle]:
        return {candidate.candidate_ref: candidate for candidate in self.candidates}

