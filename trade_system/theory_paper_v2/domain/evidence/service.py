"""Pure admission and lower-timeframe promotion predicates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..common import DomainError, DomainResult, ReducerStatus
from .model import (
    AdmittedEvidence,
    EvidenceQuality,
    EvidenceRecord,
    EvidenceScope,
    PhysicalExistence,
    SignalClass,
)


@dataclass(frozen=True, slots=True)
class PromotionRequest:
    evidence_id: str
    exact_premise_id: str
    independent_confirmation_count: int
    persistent_observation_count: int
    normal_range_exceeded: bool
    mechanism_changed: bool
    promoted: bool
    reason_codes: tuple[str, ...]


def _pit_error(code: str, message: str) -> DomainResult[AdmittedEvidence]:
    return DomainResult(
        status=ReducerStatus.REJECTED,
        error=DomainError(code, "PIT", "NEVER", message),
    )


def admit_evidence(
    record: EvidenceRecord,
    *,
    decision_cutoff: datetime,
    strategic_timeframe_seconds: int,
) -> DomainResult[AdmittedEvidence]:
    """Apply the six-part contemporaneous point-in-time admission rule."""

    if decision_cutoff.tzinfo is None:
        return _pit_error("CLOCK_TIME_INVALID", "decision cutoff must be timezone-aware")
    if any(
        moment.tzinfo is None
        for moment in (
            record.available_at,
            record.ingested_at,
            record.source_committed_at,
        )
    ):
        return _pit_error("CLOCK_TIME_INVALID", "evidence timestamps must be timezone-aware")
    if record.available_at > decision_cutoff:
        return _pit_error("PIT_FUTURE_AVAILABLE", "available_at exceeds decision cutoff")
    if record.ingested_at > decision_cutoff:
        return _pit_error("PIT_FUTURE_AVAILABLE", "ingested_at exceeds decision cutoff")
    if record.source_committed_at > decision_cutoff:
        return _pit_error("PIT_SOURCE_NOT_COMMITTED", "source committed after cutoff")
    if not record.source_commit_receipt_valid:
        return _pit_error("PIT_SOURCE_NOT_COMMITTED", "source commit receipt is invalid")
    if record.physical_existence is not PhysicalExistence.PROVEN:
        return _pit_error(
            "PIT_PHYSICAL_EXISTENCE_UNPROVEN",
            "physical existence at source time is not proven",
        )
    if record.usage_scope is not EvidenceScope.DECISION_CONTEMPORANEOUS:
        return _pit_error(
            "PIT_MIXED_CUTOFF",
            "non-contemporaneous evidence cannot carry decision authority",
        )
    if record.quality in {
        EvidenceQuality.MISSING,
        EvidenceQuality.CONFLICTED,
        EvidenceQuality.STALE,
    }:
        return DomainResult(
            status=ReducerStatus.UNKNOWN,
            error=DomainError(
                "EVIDENCE_LINEAGE_INVALID",
                "EVIDENCE",
                "AFTER_INPUT_REPAIR",
                f"evidence quality is {record.quality}",
            ),
        )
    strategic_authority = (
        record.signal_class in {SignalClass.STRATEGIC, SignalClass.STRUCTURAL}
        and record.timeframe_seconds >= strategic_timeframe_seconds
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=AdmittedEvidence(
            record=record,
            decision_cutoff=decision_cutoff,
            strategic_authority=strategic_authority,
            promotion_required=not strategic_authority,
        ),
    )


def qualify_promotion(
    evidence: AdmittedEvidence,
    *,
    exact_premise_id: str | None,
    normal_range_exceeded: bool,
    independent_confirmation_count: int,
    required_independent_confirmations: int,
    persistent_observation_count: int,
    required_persistent_observations: int,
    mechanism_changed: bool,
) -> DomainResult[PromotionRequest]:
    """Promote lower-timeframe evidence only through preregistered predicates."""

    if evidence.strategic_authority:
        return DomainResult(
            status=ReducerStatus.APPLIED,
            value=PromotionRequest(
                evidence_id=evidence.record.evidence_id,
                exact_premise_id=exact_premise_id or "",
                independent_confirmation_count=independent_confirmation_count,
                persistent_observation_count=persistent_observation_count,
                normal_range_exceeded=normal_range_exceeded,
                mechanism_changed=mechanism_changed,
                promoted=True,
                reason_codes=("NATIVE_STRATEGIC_AUTHORITY",),
            ),
        )
    reasons: list[str] = []
    if exact_premise_id is None or exact_premise_id not in evidence.record.premise_ids:
        reasons.append("EXACT_PREMISE_MAPPING_MISSING")
    if not normal_range_exceeded:
        reasons.append("NORMAL_RANGE_NOT_EXCEEDED")
    if independent_confirmation_count < required_independent_confirmations:
        reasons.append("INDEPENDENT_CONFIRMATION_INSUFFICIENT")
    if persistent_observation_count < required_persistent_observations:
        reasons.append("PERSISTENCE_INSUFFICIENT")
    if not mechanism_changed:
        reasons.append("CORE_MECHANISM_UNCHANGED")
    request = PromotionRequest(
        evidence_id=evidence.record.evidence_id,
        exact_premise_id=exact_premise_id or "",
        independent_confirmation_count=independent_confirmation_count,
        persistent_observation_count=persistent_observation_count,
        normal_range_exceeded=normal_range_exceeded,
        mechanism_changed=mechanism_changed,
        promoted=not reasons,
        reason_codes=tuple(reasons) if reasons else ("PROMOTION_PREDICATES_PASSED",),
    )
    return DomainResult(status=ReducerStatus.APPLIED, value=request)

