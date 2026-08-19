"""Pre-outcome, single-capability assessment contracts for V3.3.2.

The contracts in this module assess whether one sealed Agent decision visibly
demonstrates a bounded analysis capability.  They do not score price outcomes,
generalization, profitability, or the five-artifact market-cycle workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from types import MappingProxyType
from typing import Any, Mapping

from ..contracts.canonical import canonical_bytes, canonical_digest


CAPABILITY_EVALUATION_SCHEMA_ID = (
    "agent-trade-emotion.v332-pre-outcome-capability-assessment"
)
CAPABILITY_EVALUATION_SCHEMA_VERSION = "1.1.0"
CAPABILITY_IDS = frozenset({"MARKET_ANALYSIS", "HYPOTHESIS_GENERATION"})
CAPABILITY_CRITERIA: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "MARKET_ANALYSIS": (
            "IDENTITY_AND_COVERAGE",
            "FACT_INFERENCE_BOUNDARY",
            "MULTIFRAME_STATE_ANALYSIS",
            "ACTOR_HYPOTHESIS_DISCIPLINE",
        ),
        "HYPOTHESIS_GENERATION": (
            "COMPETING_HYPOTHESES",
            "FALSIFIABILITY",
            "DISCRIMINATING_OBSERVATION",
        ),
    }
)


def _capability_rubric(
    capability_id: str,
    *,
    source_path: str,
    source_section: str,
    criterion_instructions: tuple[tuple[str, str], ...],
) -> Mapping[str, Any]:
    criteria = tuple(
        MappingProxyType(
            {
                "criterion_id": criterion_id,
                "assessment_instruction": instruction,
            }
        )
        for criterion_id, instruction in criterion_instructions
    )
    base: dict[str, Any] = {
        "capability_id": capability_id,
        "source_path": source_path,
        "source_section": source_section,
        "criteria": criteria,
    }
    return MappingProxyType({**base, "rubric_sha256": canonical_digest(base)})


CAPABILITY_RUBRICS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "MARKET_ANALYSIS": _capability_rubric(
            "MARKET_ANALYSIS",
            source_path="theory/versions/v3.3.2/01_MARKET_COGNITION.md",
            source_section=(
                "§24.1 Cold完整分析; §24.4 建议的可读决策结构"
            ),
            criterion_instructions=(
                (
                    "IDENTITY_AND_COVERAGE",
                    "DEMONSTRATED only when the decision identifies the instrument, "
                    "contract, venue, cutoff and horizon and distinguishes actually "
                    "available data from stale, missing or UNKNOWN coverage.",
                ),
                (
                    "FACT_INFERENCE_BOUNDARY",
                    "DEMONSTRATED only when observed facts and transparent measurements "
                    "are separated from inferred state, actor or intent claims, with "
                    "missing evidence left UNKNOWN.",
                ),
                (
                    "MULTIFRAME_STATE_ANALYSIS",
                    "DEMONSTRATED only when structure, decision and trigger timeframes "
                    "and their conflicts are used to explain state, transition, "
                    "volatility or key areas from admitted evidence.",
                ),
                (
                    "ACTOR_HYPOTHESIS_DISCIPLINE",
                    "DEMONSTRATED only when actor or intent explanations remain "
                    "hypotheses and include a materially different alternative or OTHER "
                    "plus an observable discriminator or invalidation.",
                ),
            ),
        ),
        "HYPOTHESIS_GENERATION": _capability_rubric(
            "HYPOTHESIS_GENERATION",
            source_path="theory/versions/v3.3.2/03_HYPOTHESIS_SYSTEM.md",
            source_section=(
                "§4 竞争集合由 Agent 生成与收缩; §7 区分性观察和信息价值; "
                "§12 质量期望与封存边界"
            ),
            criterion_instructions=(
                (
                    "COMPETING_HYPOTHESES",
                    "DEMONSTRATED only when the decision states a leading explanation, "
                    "a materially different competing mechanism and OTHER or noise, "
                    "rather than relabeling one story.",
                ),
                (
                    "FALSIFIABILITY",
                    "DEMONSTRATED only when each decision-relevant hypothesis states a "
                    "prospective conditional path and a bounded invalidation or expiry "
                    "that could prove it wrong.",
                ),
                (
                    "DISCRIMINATING_OBSERVATION",
                    "DEMONSTRATED only when the next observable fact, legal availability "
                    "time or source, differing hypothesis expectations and resulting "
                    "decision change are identified.",
                ),
            ),
        ),
    }
)
FINDING_STATUSES = frozenset(
    {"DEMONSTRATED", "NOT_DEMONSTRATED", "UNRESOLVED"}
)
ASSESSMENT_VECTOR_KEYS = (
    "operational",
    "capability",
    "prediction",
    "generalization",
    "profitability",
)
BLINDNESS_BASIS = (
    "PRE_OUTCOME_TASK_AND_DECISION_ASSIGNED_OUTCOME_NOT_PROVIDED_"
    "EXTERNAL_INFORMATION_IS_NOT_TECHNICALLY_BLOCKED"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-/]{0,255}\Z")
_PHYSICAL_GOAL_ID_RE = re.compile(
    r"codex-thread:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}\Z"
)


class CapabilityEvaluationContractError(ValueError):
    """A capability-assessment binding is malformed or inconsistent."""


def is_physical_goal_identity(value: object) -> bool:
    return type(value) is str and _PHYSICAL_GOAL_ID_RE.fullmatch(value) is not None


def _identifier(value: object, *, field: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise CapabilityEvaluationContractError(f"{field} must be a safe identifier")
    return value


def _sha256(value: object, *, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CapabilityEvaluationContractError(f"{field} must be a SHA-256 digest")
    return value


def _timestamp(value: object, *, field: str) -> datetime:
    if type(value) is not str or not value:
        raise CapabilityEvaluationContractError(
            f"{field} must be an offset ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapabilityEvaluationContractError(
            f"{field} must be an offset ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapabilityEvaluationContractError(
            f"{field} must be an offset ISO-8601 timestamp"
        )
    return parsed


def _text(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or "\x00" in value
        or len(value.encode("utf-8")) > 16_384
    ):
        raise CapabilityEvaluationContractError(f"{field} must be readable UTF-8 text")
    return value


def _exact_mapping(
    value: object, *, fields: frozenset[str], document_type: str | None = None
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != fields:
        raise CapabilityEvaluationContractError("capability document fields are invalid")
    if document_type is not None and (
        value.get("schema_id") != CAPABILITY_EVALUATION_SCHEMA_ID
        or value.get("schema_version") != CAPABILITY_EVALUATION_SCHEMA_VERSION
        or value.get("document_type") != document_type
    ):
        raise CapabilityEvaluationContractError("capability document schema is invalid")
    return value


def _sequence(value: object, *, field: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise CapabilityEvaluationContractError(f"{field} must be an array")
    return tuple(value)


def _rubric_document(capability_id: str) -> dict[str, Any]:
    rubric = CAPABILITY_RUBRICS[capability_id]
    return {
        "capability_id": rubric["capability_id"],
        "source_path": rubric["source_path"],
        "source_section": rubric["source_section"],
        "criteria": [dict(item) for item in rubric["criteria"]],
        "rubric_sha256": rubric["rubric_sha256"],
    }


def _verified_rubric(value: object, *, capability_id: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CapabilityEvaluationContractError("rubric must be an object")
    expected = _rubric_document(capability_id)
    try:
        exact = canonical_bytes(value) == canonical_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise CapabilityEvaluationContractError("rubric is invalid") from exc
    if not exact:
        raise CapabilityEvaluationContractError(
            "rubric does not match the frozen capability rubric"
        )
    return CAPABILITY_RUBRICS[capability_id]


@dataclass(frozen=True, slots=True)
class Utf8DecisionSpanV1:
    """A half-open byte range into the exact UTF-8 Agent decision."""

    start_byte: int
    end_byte: int
    utf8_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.start_byte) is not int
            or type(self.end_byte) is not int
            or self.start_byte < 0
            or self.end_byte <= self.start_byte
        ):
            raise CapabilityEvaluationContractError(
                "UTF-8 span must be a non-empty half-open byte range"
            )
        _sha256(self.utf8_sha256, field="utf8_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "utf8_sha256": self.utf8_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Utf8DecisionSpanV1":
        document = _exact_mapping(
            value,
            fields=frozenset({"start_byte", "end_byte", "utf8_sha256"}),
        )
        return cls(
            start_byte=document["start_byte"],
            end_byte=document["end_byte"],
            utf8_sha256=document["utf8_sha256"],
        )


@dataclass(frozen=True, slots=True)
class CapabilityFindingV1:
    """One criterion judgment with exact decision-byte evidence when present."""

    criterion_id: str
    status: str
    rationale: str
    evidence_spans: tuple[Utf8DecisionSpanV1, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.criterion_id, field="criterion_id")
        if self.status not in FINDING_STATUSES:
            raise CapabilityEvaluationContractError("finding status is unsupported")
        _text(self.rationale, field="rationale")
        spans = tuple(self.evidence_spans)
        if not all(isinstance(span, Utf8DecisionSpanV1) for span in spans):
            raise CapabilityEvaluationContractError(
                "evidence_spans must contain Utf8DecisionSpanV1"
            )
        if self.status == "DEMONSTRATED" and not spans:
            raise CapabilityEvaluationContractError(
                "DEMONSTRATED finding requires an exact decision-byte span"
            )
        object.__setattr__(self, "evidence_spans", spans)

    def to_dict(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "status": self.status,
            "rationale": self.rationale,
            "evidence_spans": [span.to_dict() for span in self.evidence_spans],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CapabilityFindingV1":
        document = _exact_mapping(
            value,
            fields=frozenset(
                {"criterion_id", "status", "rationale", "evidence_spans"}
            ),
        )
        spans = _sequence(document["evidence_spans"], field="evidence_spans")
        try:
            parsed_spans = tuple(Utf8DecisionSpanV1.from_dict(item) for item in spans)
        except (TypeError, CapabilityEvaluationContractError) as exc:
            raise CapabilityEvaluationContractError(
                "evidence_spans contain an invalid span"
            ) from exc
        return cls(
            criterion_id=document["criterion_id"],
            status=document["status"],
            rationale=document["rationale"],
            evidence_spans=parsed_spans,
        )


@dataclass(frozen=True, slots=True)
class BlindCapabilityTaskV1:
    """A preregistered task binding policy, request, snapshot and assessor."""

    task_id: str
    capability_id: str
    policy_sha256: str
    cycle_id: str
    snapshot_id: str
    snapshot_sha256: str
    request_sha256: str
    request_document_sha256: str
    decision_delivery_sha256: str
    subject_agent_id: str
    assessor_id: str
    created_at: str
    assessment_due_at: str
    criteria: tuple[str, ...]
    rubric: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field in (
            "task_id",
            "cycle_id",
            "snapshot_id",
            "subject_agent_id",
            "assessor_id",
        ):
            _identifier(getattr(self, field), field=field)
        if self.capability_id not in CAPABILITY_IDS:
            raise CapabilityEvaluationContractError("capability_id is unsupported")
        for field in (
            "policy_sha256",
            "snapshot_sha256",
            "request_sha256",
            "request_document_sha256",
            "decision_delivery_sha256",
        ):
            _sha256(getattr(self, field), field=field)
        if not is_physical_goal_identity(self.subject_agent_id):
            raise CapabilityEvaluationContractError(
                "subject_agent_id must be a physical Codex Goal identity"
            )
        if self.assessor_id != "pending-capability-assessor" and not (
            is_physical_goal_identity(self.assessor_id)
        ):
            raise CapabilityEvaluationContractError(
                "assessor_id must be a physical Codex Goal identity"
            )
        if self.subject_agent_id == self.assessor_id:
            raise CapabilityEvaluationContractError(
                "assessor must be independent from the subject Agent identity"
            )
        created = _timestamp(self.created_at, field="created_at")
        due = _timestamp(self.assessment_due_at, field="assessment_due_at")
        if due <= created:
            raise CapabilityEvaluationContractError(
                "assessment_due_at must follow task creation"
            )
        criteria = tuple(self.criteria)
        if criteria != CAPABILITY_CRITERIA[self.capability_id]:
            raise CapabilityEvaluationContractError(
                "task criteria do not match the selected capability"
            )
        object.__setattr__(self, "criteria", criteria)
        object.__setattr__(
            self,
            "rubric",
            _verified_rubric(self.rubric, capability_id=self.capability_id),
        )

    @property
    def task_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_id": CAPABILITY_EVALUATION_SCHEMA_ID,
            "schema_version": CAPABILITY_EVALUATION_SCHEMA_VERSION,
            "document_type": "BLIND_CAPABILITY_TASK",
            "task_id": self.task_id,
            "capability_id": self.capability_id,
            "policy_sha256": self.policy_sha256,
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_sha256": self.snapshot_sha256,
            "request_sha256": self.request_sha256,
            "request_document_sha256": self.request_document_sha256,
            "decision_delivery_sha256": self.decision_delivery_sha256,
            "subject_agent_id": self.subject_agent_id,
            "assessor_id": self.assessor_id,
            "created_at": self.created_at,
            "assessment_due_at": self.assessment_due_at,
            "criteria": list(self.criteria),
            "rubric": _rubric_document(self.capability_id),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BlindCapabilityTaskV1":
        fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "document_type",
                "task_id",
                "capability_id",
                "policy_sha256",
                "cycle_id",
                "snapshot_id",
                "snapshot_sha256",
                "request_sha256",
                "request_document_sha256",
                "decision_delivery_sha256",
                "subject_agent_id",
                "assessor_id",
                "created_at",
                "assessment_due_at",
                "criteria",
                "rubric",
            }
        )
        document = _exact_mapping(
            value, fields=fields, document_type="BLIND_CAPABILITY_TASK"
        )
        criteria = _sequence(document["criteria"], field="criteria")
        return cls(
            task_id=document["task_id"],
            capability_id=document["capability_id"],
            policy_sha256=document["policy_sha256"],
            cycle_id=document["cycle_id"],
            snapshot_id=document["snapshot_id"],
            snapshot_sha256=document["snapshot_sha256"],
            request_sha256=document["request_sha256"],
            request_document_sha256=document["request_document_sha256"],
            decision_delivery_sha256=document["decision_delivery_sha256"],
            subject_agent_id=document["subject_agent_id"],
            assessor_id=document["assessor_id"],
            created_at=document["created_at"],
            assessment_due_at=document["assessment_due_at"],
            criteria=criteria,
            rubric=document["rubric"],
        )


def capability_vector_for(
    findings: tuple[CapabilityFindingV1, ...],
) -> Mapping[str, str]:
    if not findings or not all(
        isinstance(finding, CapabilityFindingV1) for finding in findings
    ):
        raise CapabilityEvaluationContractError(
            "capability vector requires explicit typed findings"
        )
    statuses = tuple(finding.status for finding in findings)
    if "NOT_DEMONSTRATED" in statuses:
        capability = "NOT_DEMONSTRATED_ON_THIS_SAMPLE"
    elif "UNRESOLVED" in statuses:
        capability = "UNRESOLVED_ON_THIS_SAMPLE"
    else:
        capability = "DEMONSTRATED_ON_THIS_SAMPLE"
    return MappingProxyType(
        {
            "operational": "PRE_OUTCOME_BINDINGS_VERIFIED",
            "capability": capability,
            "prediction": "NOT_EVALUATED_PRE_OUTCOME",
            "generalization": "NOT_EVALUATED_SINGLE_SAMPLE",
            "profitability": "NOT_EVALUATED_NO_COSTED_TRADING_EVIDENCE",
        }
    )


@dataclass(frozen=True, slots=True)
class PreOutcomeCapabilityAssessmentV1:
    """One pre-outcome qualitative vector; deliberately contains no total score."""

    assessment_id: str
    task_id: str
    task_sha256: str
    capability_id: str
    policy_sha256: str
    cycle_id: str
    snapshot_id: str
    snapshot_sha256: str
    request_sha256: str
    request_document_sha256: str
    decision_delivery_sha256: str
    decision_sha256: str
    decision_size_bytes: int
    subject_agent_id: str
    assessor_id: str
    assessed_at: str
    outcome_due_at: str
    blindness_basis: str
    findings: tuple[CapabilityFindingV1, ...]
    assessment_vector: Mapping[str, str]
    limitations: tuple[str, ...]
    rubric: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field in (
            "assessment_id",
            "task_id",
            "cycle_id",
            "snapshot_id",
            "subject_agent_id",
            "assessor_id",
        ):
            _identifier(getattr(self, field), field=field)
        if self.capability_id not in CAPABILITY_IDS:
            raise CapabilityEvaluationContractError("capability_id is unsupported")
        for field in (
            "task_sha256",
            "policy_sha256",
            "snapshot_sha256",
            "request_sha256",
            "request_document_sha256",
            "decision_delivery_sha256",
            "decision_sha256",
        ):
            _sha256(getattr(self, field), field=field)
        if type(self.decision_size_bytes) is not int or self.decision_size_bytes < 1:
            raise CapabilityEvaluationContractError(
                "decision_size_bytes must be a positive integer"
            )
        if self.subject_agent_id == self.assessor_id:
            raise CapabilityEvaluationContractError(
                "assessor must be independent from the subject Agent identity"
            )
        if not is_physical_goal_identity(self.subject_agent_id):
            raise CapabilityEvaluationContractError(
                "subject_agent_id must be a physical Codex Goal identity"
            )
        if not is_physical_goal_identity(self.assessor_id):
            raise CapabilityEvaluationContractError(
                "assessor_id must be a physical Codex Goal identity"
            )
        assessed = _timestamp(self.assessed_at, field="assessed_at")
        outcome_due = _timestamp(self.outcome_due_at, field="outcome_due_at")
        if assessed >= outcome_due:
            raise CapabilityEvaluationContractError(
                "capability assessment must be sealed before Outcome is due"
            )
        if self.blindness_basis != BLINDNESS_BASIS:
            raise CapabilityEvaluationContractError("blindness_basis is invalid")
        findings = tuple(self.findings)
        if not all(isinstance(item, CapabilityFindingV1) for item in findings):
            raise CapabilityEvaluationContractError(
                "findings must contain CapabilityFindingV1"
            )
        if tuple(item.criterion_id for item in findings) != CAPABILITY_CRITERIA[
            self.capability_id
        ]:
            raise CapabilityEvaluationContractError(
                "findings are incomplete, duplicated, or out of preregistered order"
            )
        expected_vector = capability_vector_for(findings)
        if (
            not isinstance(self.assessment_vector, Mapping)
            or tuple(self.assessment_vector) != ASSESSMENT_VECTOR_KEYS
            or dict(self.assessment_vector) != dict(expected_vector)
        ):
            raise CapabilityEvaluationContractError("assessment_vector is invalid")
        limitations = tuple(self.limitations)
        if not limitations or any(
            type(item) is not str or not item.strip() for item in limitations
        ):
            raise CapabilityEvaluationContractError("limitations must be non-empty text")
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "assessment_vector", expected_vector)
        object.__setattr__(self, "limitations", limitations)
        object.__setattr__(
            self,
            "rubric",
            _verified_rubric(self.rubric, capability_id=self.capability_id),
        )

    @property
    def assessment_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": CAPABILITY_EVALUATION_SCHEMA_ID,
            "schema_version": CAPABILITY_EVALUATION_SCHEMA_VERSION,
            "document_type": "PRE_OUTCOME_CAPABILITY_ASSESSMENT",
            "assessment_id": self.assessment_id,
            "task_id": self.task_id,
            "task_sha256": self.task_sha256,
            "capability_id": self.capability_id,
            "policy_sha256": self.policy_sha256,
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_sha256": self.snapshot_sha256,
            "request_sha256": self.request_sha256,
            "request_document_sha256": self.request_document_sha256,
            "decision_delivery_sha256": self.decision_delivery_sha256,
            "decision_sha256": self.decision_sha256,
            "decision_size_bytes": self.decision_size_bytes,
            "subject_agent_id": self.subject_agent_id,
            "assessor_id": self.assessor_id,
            "assessed_at": self.assessed_at,
            "outcome_due_at": self.outcome_due_at,
            "blindness_basis": self.blindness_basis,
            "findings": [finding.to_dict() for finding in self.findings],
            "assessment_vector": dict(self.assessment_vector),
            "limitations": list(self.limitations),
            "rubric": _rubric_document(self.capability_id),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "PreOutcomeCapabilityAssessmentV1":
        fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "document_type",
                "assessment_id",
                "task_id",
                "task_sha256",
                "capability_id",
                "policy_sha256",
                "cycle_id",
                "snapshot_id",
                "snapshot_sha256",
                "request_sha256",
                "request_document_sha256",
                "decision_delivery_sha256",
                "decision_sha256",
                "decision_size_bytes",
                "subject_agent_id",
                "assessor_id",
                "assessed_at",
                "outcome_due_at",
                "blindness_basis",
                "findings",
                "assessment_vector",
                "limitations",
                "rubric",
            }
        )
        document = _exact_mapping(
            value,
            fields=fields,
            document_type="PRE_OUTCOME_CAPABILITY_ASSESSMENT",
        )
        finding_values = _sequence(document["findings"], field="findings")
        try:
            findings = tuple(
                CapabilityFindingV1.from_dict(item) for item in finding_values
            )
        except (TypeError, CapabilityEvaluationContractError) as exc:
            raise CapabilityEvaluationContractError(
                "findings contain an invalid capability finding"
            ) from exc
        limitations = _sequence(document["limitations"], field="limitations")
        vector = document["assessment_vector"]
        if not isinstance(vector, Mapping):
            raise CapabilityEvaluationContractError(
                "assessment_vector must be an object"
            )
        ordered_vector = {key: vector[key] for key in ASSESSMENT_VECTOR_KEYS if key in vector}
        return cls(
            assessment_id=document["assessment_id"],
            task_id=document["task_id"],
            task_sha256=document["task_sha256"],
            capability_id=document["capability_id"],
            policy_sha256=document["policy_sha256"],
            cycle_id=document["cycle_id"],
            snapshot_id=document["snapshot_id"],
            snapshot_sha256=document["snapshot_sha256"],
            request_sha256=document["request_sha256"],
            request_document_sha256=document["request_document_sha256"],
            decision_delivery_sha256=document["decision_delivery_sha256"],
            decision_sha256=document["decision_sha256"],
            decision_size_bytes=document["decision_size_bytes"],
            subject_agent_id=document["subject_agent_id"],
            assessor_id=document["assessor_id"],
            assessed_at=document["assessed_at"],
            outcome_due_at=document["outcome_due_at"],
            blindness_basis=document["blindness_basis"],
            findings=findings,
            assessment_vector=ordered_vector,
            limitations=limitations,
            rubric=document["rubric"],
        )


__all__ = [
    "ASSESSMENT_VECTOR_KEYS",
    "BLINDNESS_BASIS",
    "CAPABILITY_CRITERIA",
    "CAPABILITY_EVALUATION_SCHEMA_ID",
    "CAPABILITY_EVALUATION_SCHEMA_VERSION",
    "CAPABILITY_IDS",
    "CAPABILITY_RUBRICS",
    "FINDING_STATUSES",
    "BlindCapabilityTaskV1",
    "CapabilityEvaluationContractError",
    "CapabilityFindingV1",
    "PreOutcomeCapabilityAssessmentV1",
    "Utf8DecisionSpanV1",
    "capability_vector_for",
    "is_physical_goal_identity",
]
