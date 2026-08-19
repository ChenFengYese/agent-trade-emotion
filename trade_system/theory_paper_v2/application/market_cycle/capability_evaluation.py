"""Pure builders for V3.3.2 pre-outcome capability assessment.

The builders receive sealed domain objects and an exact Agent request document.
They perform no I/O and deliberately accept no ``Outcome`` object.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any, Mapping, Sequence

from ...domain.contracts.canonical import canonical_bytes, canonical_digest
from ...domain.market_cycle.capability_evaluation import (
    BLINDNESS_BASIS,
    CAPABILITY_CRITERIA,
    CAPABILITY_RUBRICS,
    BlindCapabilityTaskV1,
    CapabilityEvaluationContractError,
    CapabilityFindingV1,
    PreOutcomeCapabilityAssessmentV1,
    Utf8DecisionSpanV1,
    capability_vector_for,
)
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    HypothesisRecord,
    InputSnapshot,
)
from ...domain.market_cycle.experiment import ExperimentPolicyV1


def _time(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise CapabilityEvaluationContractError(
            f"{field} must be an offset ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapabilityEvaluationContractError(
            f"{field} must be an offset ISO-8601 timestamp"
        )
    return parsed


def _verify_snapshot_ref(snapshot: InputSnapshot, snapshot_ref: ArtifactRef) -> None:
    if not isinstance(snapshot, InputSnapshot) or not isinstance(snapshot_ref, ArtifactRef):
        raise CapabilityEvaluationContractError(
            "snapshot and snapshot_ref must be sealed market-cycle contracts"
        )
    raw = canonical_bytes(snapshot.to_dict())
    if (
        snapshot_ref.artifact_type != "InputSnapshot"
        or snapshot_ref.artifact_id != snapshot.snapshot_id
        or snapshot_ref.size_bytes != len(raw)
        or snapshot_ref.sha256 != hashlib.sha256(raw).hexdigest()
    ):
        raise CapabilityEvaluationContractError(
            "snapshot_ref does not bind the supplied InputSnapshot"
        )


def _verify_policy_and_request(
    *,
    policy: ExperimentPolicyV1,
    capability_id: str,
    snapshot: InputSnapshot,
    request_document: Mapping[str, Any],
) -> tuple[str, str]:
    if not isinstance(policy, ExperimentPolicyV1):
        raise CapabilityEvaluationContractError("policy must be ExperimentPolicyV1")
    if policy.phase != "CAPABILITY_PILOT":
        raise CapabilityEvaluationContractError(
            "pre-outcome capability task requires CAPABILITY_PILOT policy"
        )
    if (
        capability_id not in CAPABILITY_CRITERIA
        or policy.capability_ids != (capability_id,)
    ):
        raise CapabilityEvaluationContractError(
            "pre-outcome capability pilot requires one matching capability"
        )
    if (
        policy.venue_id != snapshot.venue_id
        or policy.instrument_id != snapshot.instrument_id
        or policy.market_contract_identity != snapshot.contract_identity
        or policy.data_profile != snapshot.data_profile
        or policy.decision_horizon_seconds != snapshot.outcome_horizon_seconds
        or policy.outcome_tolerance_seconds != snapshot.outcome_tolerance_seconds
    ):
        raise CapabilityEvaluationContractError(
            "experiment policy and InputSnapshot identity or horizon differ"
        )
    if not isinstance(request_document, Mapping):
        raise CapabilityEvaluationContractError("request_document must be an object")
    try:
        packet = request_document["packet"]
        packet_sha256 = request_document["packet_sha256"]
        if (
            not isinstance(packet, Mapping)
            or not isinstance(packet_sha256, str)
            or hashlib.sha256(canonical_bytes(packet)).hexdigest()
            != packet_sha256
        ):
            raise CapabilityEvaluationContractError(
                "request packet digest is invalid"
            )
        request_document_sha256 = canonical_digest(request_document)
    except (KeyError, TypeError, ValueError) as exc:
        raise CapabilityEvaluationContractError(
            "request_document must be canonical JSON"
        ) from exc
    return packet_sha256, request_document_sha256


def bind_utf8_decision_span(
    decision_text: str, *, start_byte: int, end_byte: int
) -> Utf8DecisionSpanV1:
    """Bind one human-selected half-open range to strict UTF-8 boundaries."""

    if type(decision_text) is not str:
        raise CapabilityEvaluationContractError("decision_text must be UTF-8 text")
    raw = decision_text.encode("utf-8", errors="strict")
    if (
        type(start_byte) is not int
        or type(end_byte) is not int
        or start_byte < 0
        or end_byte <= start_byte
        or end_byte > len(raw)
    ):
        raise CapabilityEvaluationContractError("decision UTF-8 byte span is out of range")
    selected = raw[start_byte:end_byte]
    try:
        selected.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CapabilityEvaluationContractError(
            "decision byte span must start and end on UTF-8 code-point boundaries"
        ) from exc
    return Utf8DecisionSpanV1(
        start_byte=start_byte,
        end_byte=end_byte,
        utf8_sha256=hashlib.sha256(selected).hexdigest(),
    )


def build_blind_capability_task(
    *,
    task_id: str,
    capability_id: str,
    policy: ExperimentPolicyV1,
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
    request_document: Mapping[str, Any],
    subject_agent_id: str,
    decision_delivery_sha256: str,
    assessor_id: str,
    created_at: str,
    assessment_due_at: str,
) -> BlindCapabilityTaskV1:
    """Freeze one assessor assignment after snapshot sealing and before Outcome."""

    _verify_snapshot_ref(snapshot, snapshot_ref)
    request_sha256, request_document_sha256 = _verify_policy_and_request(
        policy=policy,
        capability_id=capability_id,
        snapshot=snapshot,
        request_document=request_document,
    )
    if _time(created_at, field="created_at") < _time(
        snapshot.sealed_at, field="snapshot.sealed_at"
    ):
        raise CapabilityEvaluationContractError(
            "capability task cannot precede the sealed InputSnapshot"
        )
    if _time(assessment_due_at, field="assessment_due_at") >= _time(
        snapshot.outcome_due_at, field="snapshot.outcome_due_at"
    ):
        raise CapabilityEvaluationContractError(
            "assessment deadline must precede Outcome due time"
        )
    return BlindCapabilityTaskV1(
        task_id=task_id,
        capability_id=capability_id,
        policy_sha256=policy.policy_sha256,
        cycle_id=snapshot.cycle_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot_ref.sha256,
        request_sha256=request_sha256,
        request_document_sha256=request_document_sha256,
        decision_delivery_sha256=decision_delivery_sha256,
        subject_agent_id=subject_agent_id,
        assessor_id=assessor_id,
        created_at=created_at,
        assessment_due_at=assessment_due_at,
        criteria=CAPABILITY_CRITERIA[capability_id],
        rubric=CAPABILITY_RUBRICS[capability_id],
    )


def _verify_span(span: Utf8DecisionSpanV1, decision_raw: bytes) -> None:
    if span.end_byte > len(decision_raw):
        raise CapabilityEvaluationContractError(
            "finding span exceeds the exact Agent decision"
        )
    selected = decision_raw[span.start_byte : span.end_byte]
    try:
        selected.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CapabilityEvaluationContractError(
            "finding span splits a UTF-8 code point"
        ) from exc
    if hashlib.sha256(selected).hexdigest() != span.utf8_sha256:
        raise CapabilityEvaluationContractError(
            "finding span digest does not bind the exact Agent decision bytes"
        )


def build_pre_outcome_capability_assessment(
    *,
    assessment_id: str,
    task: BlindCapabilityTaskV1,
    policy: ExperimentPolicyV1,
    request_document: Mapping[str, Any],
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
    hypothesis: HypothesisRecord,
    subject_physical_goal_id: str,
    decision_delivery_sha256: str,
    assessed_at: str,
    findings: Sequence[CapabilityFindingV1],
) -> PreOutcomeCapabilityAssessmentV1:
    """Verify pre-outcome bindings and build a no-total-score capability vector."""

    if not isinstance(task, BlindCapabilityTaskV1):
        raise CapabilityEvaluationContractError("task must be BlindCapabilityTaskV1")
    _verify_snapshot_ref(snapshot, snapshot_ref)
    request_sha256, request_document_sha256 = _verify_policy_and_request(
        policy=policy,
        capability_id=task.capability_id,
        snapshot=snapshot,
        request_document=request_document,
    )
    if (
        task.policy_sha256 != policy.policy_sha256
        or task.cycle_id != snapshot.cycle_id
        or task.snapshot_id != snapshot.snapshot_id
        or task.snapshot_sha256 != snapshot_ref.sha256
        or task.request_sha256 != request_sha256
        or task.request_document_sha256 != request_document_sha256
    ):
        raise CapabilityEvaluationContractError(
            "task does not bind the supplied policy, request, or snapshot"
        )
    if not isinstance(hypothesis, HypothesisRecord):
        raise CapabilityEvaluationContractError(
            "hypothesis must be a sealed HypothesisRecord"
        )
    if (
        hypothesis.cycle_id != snapshot.cycle_id
        or hypothesis.input_snapshot_ref != snapshot_ref
        or hypothesis.agent_request_sha256 != request_sha256
        or task.subject_agent_id != subject_physical_goal_id
        or task.decision_delivery_sha256 != decision_delivery_sha256
        or hypothesis.agent_delivery_sha256 != decision_delivery_sha256
    ):
        raise CapabilityEvaluationContractError(
            "HypothesisRecord does not bind the task request, snapshot, or "
            "physical Goal delivery"
        )
    decision_raw = hypothesis.agent_decision_text.encode("utf-8", errors="strict")
    if (
        hypothesis.agent_decision_size_bytes != len(decision_raw)
        or hypothesis.agent_decision_sha256
        != hashlib.sha256(decision_raw).hexdigest()
    ):
        raise CapabilityEvaluationContractError(
            "HypothesisRecord decision byte binding is invalid"
        )
    assessed = _time(assessed_at, field="assessed_at")
    if assessed < _time(hypothesis.sealed_at, field="hypothesis.sealed_at"):
        raise CapabilityEvaluationContractError(
            "assessment cannot precede the sealed Agent decision"
        )
    if assessed > _time(task.assessment_due_at, field="task.assessment_due_at"):
        raise CapabilityEvaluationContractError(
            "assessment missed the preregistered assessor deadline"
        )
    if assessed >= _time(snapshot.outcome_due_at, field="snapshot.outcome_due_at"):
        raise CapabilityEvaluationContractError(
            "assessment must be completed before Outcome is due"
        )
    task_created = _time(task.created_at, field="task.created_at")
    if task_created < _time(hypothesis.sealed_at, field="hypothesis.sealed_at"):
        raise CapabilityEvaluationContractError(
            "pre-outcome task cannot precede the sealed Agent decision"
        )
    if assessed < task_created:
        raise CapabilityEvaluationContractError(
            "assessment cannot precede the pre-outcome task"
        )

    exact_findings = tuple(findings)
    if not all(isinstance(finding, CapabilityFindingV1) for finding in exact_findings):
        raise CapabilityEvaluationContractError(
            "findings must contain CapabilityFindingV1"
        )
    if tuple(finding.criterion_id for finding in exact_findings) != task.criteria:
        raise CapabilityEvaluationContractError(
            "findings must cover the exact preregistered criteria in order"
        )
    for finding in exact_findings:
        for span in finding.evidence_spans:
            _verify_span(span, decision_raw)

    return PreOutcomeCapabilityAssessmentV1(
        assessment_id=assessment_id,
        task_id=task.task_id,
        task_sha256=task.task_sha256,
        capability_id=task.capability_id,
        policy_sha256=policy.policy_sha256,
        cycle_id=snapshot.cycle_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot_ref.sha256,
        request_sha256=request_sha256,
        request_document_sha256=request_document_sha256,
        decision_delivery_sha256=decision_delivery_sha256,
        decision_sha256=hypothesis.agent_decision_sha256,
        decision_size_bytes=hypothesis.agent_decision_size_bytes,
        subject_agent_id=task.subject_agent_id,
        assessor_id=task.assessor_id,
        assessed_at=assessed_at,
        outcome_due_at=snapshot.outcome_due_at,
        blindness_basis=BLINDNESS_BASIS,
        findings=exact_findings,
        assessment_vector=capability_vector_for(exact_findings),
        limitations=(
            "QUALITY_ASSESSMENT_IS_NOT_PREDICTIVE_ACCURACY",
            "IDENTITY_SEPARATION_IS_NOT_ORGANIZATIONAL_INDEPENDENCE_PROOF",
            "ASSESSOR_EXTERNAL_INFORMATION_ACCESS_IS_NOT_TECHNICALLY_BLOCKED",
            "SINGLE_SAMPLE_IS_NOT_GENERALIZATION",
            "NO_COSTED_FORWARD_TRADING_EVIDENCE",
        ),
        rubric=task.rubric,
    )


__all__ = [
    "bind_utf8_decision_span",
    "build_blind_capability_task",
    "build_pre_outcome_capability_assessment",
]
