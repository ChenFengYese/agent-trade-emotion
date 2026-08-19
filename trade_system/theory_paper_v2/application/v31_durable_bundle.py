"""Portable, strictly typed durable input plan for one V3.1 cycle.

The bundle is deliberately not pickle, an import path, or an opaque Agent
transcript.  It is canonical JSON over a small tagged value language whose
dataclass and enum types are explicitly whitelisted below.  A fresh process can
therefore reconstruct the exact domain objects, replay the full application
assembly, and reproduce every one of the six chronology documents without chat
history or process-local objects.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from inspect import signature
import re
from typing import Any, Mapping

from .v31_research_cycle import (
    assemble_v31_cycle_evaluation,
    complete_v31_research_cycle,
    select_v31_cycle_action,
)
from ..domain.behavior_planning import (
    ActionCandidate,
    ActionEvaluation,
    ActionType,
    LegalActionKey,
    PortfolioDecisionContext,
    PositionRole,
    PositionSide,
    ReversibilityClass,
    seal_action_selection,
)
from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.information_model import (
    ActorKind,
    ActorRole,
    ActorRoleAssignment,
    AdmittedInformationEvent,
    AudienceKind,
    AudienceSegment,
    BehaviorResponseHypothesis,
    CommitmentLevel,
    InformationActor,
    InformationChannel,
    InformationEvent,
    InformationForm,
    InformationNovelty,
    InformationScope,
    InstitutionalStatus,
    IntentInference,
    ObservedFactKind,
    ObservedInformationFact,
    PropagationClass,
    Reversibility,
    RoleAssignmentBasis,
    SourceAcquisitionMethod,
    SourceAcquisitionReceipt,
    SourceArtifactRef,
    SourceCoverage,
    SourceEvidenceBoundary,
    SourceQuality,
    SourceType,
)
from ..domain.probability_cloud import (
    CloudComponent,
    CloudUpdateEvidence,
    EvidenceEffect,
    FrozenPredictionOutcome,
    FrozenPredictiveForecast,
    PlausibilityLevel,
    PredictiveValidationReceipt,
    ProbabilityCloud,
    ProbabilityMode,
    ProperScoringRule,
)
from ..domain.scenario_path import (
    ActionImplication,
    EpistemicStage,
    EpistemicTransition,
    ExpectedObservation,
    ImplicationEffect,
    PathFactSnapshot,
    PathPredicate,
    PredicateOperator,
    PredicateQuality,
    PredicateTiming,
    PredicateTruth,
    ScenarioPathRule,
    ScenarioPathSet,
)
from ..domain.v31_cycle_authoring import (
    COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
    COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID,
)


class V31DurableBundleError(ValueError):
    """The durable typed plan is malformed, drifted, or not replayable."""


EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)
EVENT_DIGEST_FIELDS = {
    "INPUTS_ADMITTED": "inputs_receipt_digest",
    "PROPOSAL_SEALED": "agent_proposal_digest",
    "EVALUATION_SEALED": "preselection_digest",
    "SELECTION_SEALED": "action_selection_digest",
    "STATE_ACCEPTED": "accepted_state_digest",
    "COMPLETION_SEALED": "completion_receipt_digest",
}
ASSEMBLY_BUNDLE_DIRECTORY = "assembly-bundles"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_DECODE_DEPTH = 128
_MAX_DECODE_NODES = 1_000_000

_BUNDLE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "assembly_parameter_names",
        "assembly_signature_digest",
        "typed_assembly_inputs",
        "typed_assembly_inputs_digest",
        "selection_plan",
        "completed_at",
        "recorded_at_by_event",
        "expected_artifact_digests",
        "source_boundary",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        "assembly_bundle_digest",
    }
)
_COMPILED_ASSEMBLY_BUNDLE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "authoring_packet_digest",
        "agent_authoring_envelope_digest",
        "compiler_id",
        "assembly_parameter_names",
        "assembly_signature_digest",
        "typed_assembly_inputs",
        "typed_assembly_inputs_digest",
        "inputs_receipt_digest",
        "agent_proposal_digest",
        "action_evaluation_digest",
        "preselection_digest",
        "deterministic_replay_required",
        "selection_fields_admitted",
        "source_boundary",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
    }
)
_SELECTION_PLAN_FIELDS = frozenset(
    {
        "selected_candidate_id",
        "reason",
        "alternative_explanations",
        "failure_conditions",
        "next_review_at",
        "selected_at",
    }
)


def _type_id(value: type[Any]) -> str:
    return f"{value.__module__}.{value.__qualname__}"


_DATACLASS_TYPES = (
    SourceAcquisitionReceipt,
    InformationActor,
    ActorRoleAssignment,
    AudienceSegment,
    SourceArtifactRef,
    ObservedInformationFact,
    IntentInference,
    BehaviorResponseHypothesis,
    InformationEvent,
    AdmittedInformationEvent,
    CloudComponent,
    FrozenPredictiveForecast,
    FrozenPredictionOutcome,
    PredictiveValidationReceipt,
    CloudUpdateEvidence,
    ProbabilityCloud,
    PathFactSnapshot,
    PathPredicate,
    EpistemicTransition,
    ExpectedObservation,
    ActionImplication,
    ScenarioPathRule,
    ScenarioPathSet,
    PortfolioDecisionContext,
    LegalActionKey,
    ActionCandidate,
    ActionEvaluation,
)
_ENUM_TYPES = (
    ActorKind,
    ActorRole,
    RoleAssignmentBasis,
    AudienceKind,
    InformationScope,
    InformationForm,
    InstitutionalStatus,
    InformationNovelty,
    CommitmentLevel,
    Reversibility,
    PropagationClass,
    InformationChannel,
    SourceType,
    SourceQuality,
    SourceCoverage,
    SourceEvidenceBoundary,
    SourceAcquisitionMethod,
    ObservedFactKind,
    ProbabilityMode,
    PlausibilityLevel,
    EvidenceEffect,
    ProperScoringRule,
    PredicateOperator,
    EpistemicStage,
    ImplicationEffect,
    PredicateTruth,
    PredicateTiming,
    PredicateQuality,
    PositionSide,
    ActionType,
    ReversibilityClass,
    PositionRole,
)
_DATACLASS_BY_ID = {_type_id(value): value for value in _DATACLASS_TYPES}
_ENUM_BY_ID = {_type_id(value): value for value in _ENUM_TYPES}


def assembly_bundle_relative_ref(*, cycle_index: int, bundle_digest: str) -> str:
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
        or _HEX_64.fullmatch(bundle_digest) is None
    ):
        raise V31DurableBundleError("V31_BUNDLE_CONTENT_ADDRESS_INVALID")
    return (
        f"cycles/{cycle_index:04d}/{ASSEMBLY_BUNDLE_DIRECTORY}/"
        f"{bundle_digest}.json"
    )


def _timestamp(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise V31DurableBundleError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31DurableBundleError(code) from exc
    if parsed.tzinfo is None:
        raise V31DurableBundleError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31DurableBundleError(code)
    return canonical


def _encode_typed(value: Any) -> dict[str, Any]:
    if value is None:
        return {"kind": "NONE"}
    if isinstance(value, Enum):
        enum_id = _type_id(type(value))
        if enum_id not in _ENUM_BY_ID:
            raise V31DurableBundleError("V31_BUNDLE_ENUM_TYPE_FORBIDDEN")
        return {"kind": "ENUM", "type_id": enum_id, "value": value.value}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise V31DurableBundleError("V31_BUNDLE_DATETIME_NAIVE")
        return {
            "kind": "DATETIME_UTC",
            "value": value.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
    if isinstance(value, Decimal):
        return {"kind": "DECIMAL", "value": canonical_decimal(value)}
    if isinstance(value, bool):
        return {"kind": "BOOLEAN", "value": value}
    if isinstance(value, int):
        # canonical_digest below also enforces the I-JSON safe integer range.
        return {"kind": "INTEGER", "value": value}
    if isinstance(value, str):
        return {"kind": "STRING", "value": value}
    if isinstance(value, float):
        raise V31DurableBundleError("V31_BUNDLE_BINARY_FLOAT_FORBIDDEN")
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_id = _type_id(type(value))
        if dataclass_id not in _DATACLASS_BY_ID:
            raise V31DurableBundleError("V31_BUNDLE_DATACLASS_TYPE_FORBIDDEN")
        return {
            "kind": "DATACLASS",
            "type_id": dataclass_id,
            "fields": {
                field.name: _encode_typed(getattr(value, field.name))
                for field in fields(value)
                if field.init
            },
        }
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise V31DurableBundleError("V31_BUNDLE_MAPPING_KEY_INVALID")
        return {
            "kind": "MAPPING",
            "items": {
                key: _encode_typed(value[key]) for key in sorted(value)
            },
        }
    if isinstance(value, tuple):
        return {"kind": "TUPLE", "items": [_encode_typed(item) for item in value]}
    if isinstance(value, list):
        return {"kind": "LIST", "items": [_encode_typed(item) for item in value]}
    raise V31DurableBundleError(
        f"V31_BUNDLE_VALUE_TYPE_FORBIDDEN:{type(value).__name__}"
    )


class _DecodeBudget:
    def __init__(self) -> None:
        self.nodes = 0

    def consume(self, depth: int) -> None:
        self.nodes += 1
        if depth > _MAX_DECODE_DEPTH or self.nodes > _MAX_DECODE_NODES:
            raise V31DurableBundleError("V31_BUNDLE_TYPED_TREE_LIMIT_EXCEEDED")


def _decode_typed(
    document: Any, *, budget: _DecodeBudget, depth: int = 0
) -> Any:
    budget.consume(depth)
    if not isinstance(document, Mapping) or not isinstance(document.get("kind"), str):
        raise V31DurableBundleError("V31_BUNDLE_TYPED_NODE_INVALID")
    kind = document["kind"]
    if kind == "NONE":
        if set(document) != {"kind"}:
            raise V31DurableBundleError("V31_BUNDLE_TYPED_NODE_SCHEMA_INVALID")
        return None
    if kind in {"BOOLEAN", "INTEGER", "STRING"}:
        if set(document) != {"kind", "value"}:
            raise V31DurableBundleError("V31_BUNDLE_TYPED_NODE_SCHEMA_INVALID")
        value = document["value"]
        expected = {"BOOLEAN": bool, "INTEGER": int, "STRING": str}[kind]
        if not isinstance(value, expected) or (kind == "INTEGER" and isinstance(value, bool)):
            raise V31DurableBundleError("V31_BUNDLE_TYPED_PRIMITIVE_INVALID")
        return value
    if kind == "DECIMAL":
        if set(document) != {"kind", "value"} or not isinstance(document["value"], str):
            raise V31DurableBundleError("V31_BUNDLE_DECIMAL_INVALID")
        try:
            value = Decimal(document["value"])
        except (InvalidOperation, ValueError) as exc:
            raise V31DurableBundleError("V31_BUNDLE_DECIMAL_INVALID") from exc
        if not value.is_finite() or canonical_decimal(value) != document["value"]:
            raise V31DurableBundleError("V31_BUNDLE_DECIMAL_INVALID")
        return value
    if kind == "DATETIME_UTC":
        if set(document) != {"kind", "value"}:
            raise V31DurableBundleError("V31_BUNDLE_DATETIME_INVALID")
        canonical = _timestamp(document["value"], "V31_BUNDLE_DATETIME_INVALID")
        return datetime.fromisoformat(canonical.replace("Z", "+00:00"))
    if kind == "ENUM":
        if set(document) != {"kind", "type_id", "value"}:
            raise V31DurableBundleError("V31_BUNDLE_ENUM_SCHEMA_INVALID")
        enum_type = _ENUM_BY_ID.get(document.get("type_id"))
        if enum_type is None:
            raise V31DurableBundleError("V31_BUNDLE_ENUM_TYPE_FORBIDDEN")
        try:
            return enum_type(document["value"])
        except (TypeError, ValueError) as exc:
            raise V31DurableBundleError("V31_BUNDLE_ENUM_VALUE_INVALID") from exc
    if kind in {"LIST", "TUPLE"}:
        if set(document) != {"kind", "items"} or not isinstance(document["items"], list):
            raise V31DurableBundleError("V31_BUNDLE_SEQUENCE_SCHEMA_INVALID")
        values = [
            _decode_typed(item, budget=budget, depth=depth + 1)
            for item in document["items"]
        ]
        return values if kind == "LIST" else tuple(values)
    if kind == "MAPPING":
        if set(document) != {"kind", "items"} or not isinstance(document["items"], Mapping):
            raise V31DurableBundleError("V31_BUNDLE_MAPPING_SCHEMA_INVALID")
        if any(not isinstance(key, str) for key in document["items"]):
            raise V31DurableBundleError("V31_BUNDLE_MAPPING_KEY_INVALID")
        return {
            key: _decode_typed(value, budget=budget, depth=depth + 1)
            for key, value in document["items"].items()
        }
    if kind == "DATACLASS":
        if set(document) != {"kind", "type_id", "fields"} or not isinstance(
            document["fields"], Mapping
        ):
            raise V31DurableBundleError("V31_BUNDLE_DATACLASS_SCHEMA_INVALID")
        dataclass_type = _DATACLASS_BY_ID.get(document.get("type_id"))
        if dataclass_type is None:
            raise V31DurableBundleError("V31_BUNDLE_DATACLASS_TYPE_FORBIDDEN")
        expected_fields = {field.name for field in fields(dataclass_type) if field.init}
        if set(document["fields"]) != expected_fields:
            raise V31DurableBundleError("V31_BUNDLE_DATACLASS_FIELDS_INVALID")
        values = {
            name: _decode_typed(value, budget=budget, depth=depth + 1)
            for name, value in document["fields"].items()
        }
        try:
            return dataclass_type(**values)
        except (KeyError, TypeError, ValueError) as exc:
            raise V31DurableBundleError("V31_BUNDLE_DATACLASS_REBUILD_FAILED") from exc
    raise V31DurableBundleError("V31_BUNDLE_TYPED_KIND_INVALID")


def _assembly_parameter_names() -> tuple[str, ...]:
    return tuple(signature(assemble_v31_cycle_evaluation).parameters)


def _normalize_assembly_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(inputs, Mapping):
        raise V31DurableBundleError("V31_BUNDLE_ASSEMBLY_INPUTS_REQUIRED")
    try:
        bound = signature(assemble_v31_cycle_evaluation).bind(**dict(inputs))
    except TypeError as exc:
        raise V31DurableBundleError("V31_BUNDLE_ASSEMBLY_SIGNATURE_INVALID") from exc
    bound.apply_defaults()
    normalized = dict(bound.arguments)
    if tuple(normalized) != _assembly_parameter_names():
        raise V31DurableBundleError("V31_BUNDLE_ASSEMBLY_SIGNATURE_INVALID")
    if normalized.get("selection") is not None:
        raise V31DurableBundleError("V31_BUNDLE_PRESELECTION_BOUNDARY_INVALID")
    return normalized


def _assert_non_executable(value: Any) -> None:
    if isinstance(value, Mapping):
        if "executable" in value and value["executable"] is not False:
            raise V31DurableBundleError("V31_BUNDLE_EXECUTABLE_INPUT_FORBIDDEN")
        if "authorized" in value and value["authorized"] is not False:
            raise V31DurableBundleError("V31_BUNDLE_AUTHORIZED_INPUT_FORBIDDEN")
        if "external_execution_authority" in value and value[
            "external_execution_authority"
        ] != "NONE_LOCAL_SIMULATION":
            raise V31DurableBundleError("V31_BUNDLE_AUTHORITY_INPUT_FORBIDDEN")
        for nested in value.values():
            _assert_non_executable(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_non_executable(nested)
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            if field.init:
                nested = getattr(value, field.name)
                if field.name == "executable" and nested is not False:
                    raise V31DurableBundleError(
                        "V31_BUNDLE_EXECUTABLE_INPUT_FORBIDDEN"
                    )
                if field.name == "authorized" and nested is not False:
                    raise V31DurableBundleError(
                        "V31_BUNDLE_AUTHORIZED_INPUT_FORBIDDEN"
                    )
                if (
                    field.name == "external_execution_authority"
                    and nested != "NONE_LOCAL_SIMULATION"
                ):
                    raise V31DurableBundleError(
                        "V31_BUNDLE_AUTHORITY_INPUT_FORBIDDEN"
                    )
                _assert_non_executable(nested)


def seal_v31_compiled_assembly_bundle(
    *,
    assembly_inputs: Mapping[str, Any],
    authoring_packet_digest: str,
    agent_authoring_envelope_digest: str,
    compiler_id: str,
    preselection: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal complete typed preselection inputs for fresh-process replay.

    This artifact contains no selection plan and grants no start or execution
    authority.  Its sole purpose is to prevent a successful compiler process
    from becoming an unavailable, unverified in-memory dependency.
    """

    normalized_inputs = _normalize_assembly_inputs(assembly_inputs)
    _assert_non_executable(normalized_inputs)
    run_id = normalized_inputs["run_id"]
    cycle_index = normalized_inputs["cycle_index"]
    decision_at = normalized_inputs["decision_at"]
    symbol = normalized_inputs["symbol"]
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
        or not isinstance(symbol, str)
        or not symbol.strip()
        or not isinstance(compiler_id, str)
        or not compiler_id.strip()
        or _HEX_64.fullmatch(str(authoring_packet_digest or "")) is None
        or _HEX_64.fullmatch(str(agent_authoring_envelope_digest or "")) is None
    ):
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_BUNDLE_IDENTITY_INVALID"
        )
    _timestamp(decision_at, "V31_COMPILED_ASSEMBLY_DECISION_TIME_INVALID")
    try:
        replayed = assemble_v31_cycle_evaluation(**normalized_inputs)
        inputs_digest = verify_self_digest(
            normalized_inputs["inputs_receipt"], "inputs_receipt_digest"
        )
        proposal_digest = verify_self_digest(
            normalized_inputs["agent_proposal"], "agent_proposal_digest"
        )
        evaluation_digest = verify_self_digest(
            normalized_inputs["action_evaluation"], "action_evaluation_digest"
        )
        preselection_digest = verify_self_digest(
            preselection, "preselection_digest"
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_SEMANTIC_REPLAY_FAILED"
        ) from exc
    if replayed != dict(preselection):
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_PRESELECTION_REPLAY_MISMATCH"
        )
    typed_inputs = _encode_typed(normalized_inputs)
    parameters = list(_assembly_parameter_names())
    return self_digest(
        {
            "schema_id": COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "symbol": symbol,
            "authoring_packet_digest": authoring_packet_digest,
            "agent_authoring_envelope_digest": agent_authoring_envelope_digest,
            "compiler_id": compiler_id,
            "assembly_parameter_names": parameters,
            "assembly_signature_digest": canonical_digest(parameters),
            "typed_assembly_inputs": typed_inputs,
            "typed_assembly_inputs_digest": canonical_digest(typed_inputs),
            "inputs_receipt_digest": inputs_digest,
            "agent_proposal_digest": proposal_digest,
            "action_evaluation_digest": evaluation_digest,
            "preselection_digest": preselection_digest,
            "deterministic_replay_required": True,
            "selection_fields_admitted": False,
            "source_boundary": (
                "DURABLE_TYPED_PRESELECTION_INPUTS_ONLY_NO_CHAT_AUTHORITY"
            ),
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
    )


def decode_v31_compiled_assembly_bundle(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decode and replay one durable compiled preselection input bundle."""

    if (
        not isinstance(document, Mapping)
        or set(document) != _COMPILED_ASSEMBLY_BUNDLE_FIELDS
    ):
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_BUNDLE_SCHEMA_INVALID"
        )
    try:
        verify_self_digest(document, COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD)
    except (CanonicalContractError, ValueError) as exc:
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_BUNDLE_DIGEST_INVALID"
        ) from exc
    parameters = list(_assembly_parameter_names())
    if (
        document.get("schema_id") != COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID
        or document.get("schema_version") != "1.0.0"
        or document.get("assembly_parameter_names") != parameters
        or document.get("assembly_signature_digest")
        != canonical_digest(parameters)
        or document.get("typed_assembly_inputs_digest")
        != canonical_digest(document.get("typed_assembly_inputs"))
        or _HEX_64.fullmatch(
            str(document.get("authoring_packet_digest") or "")
        )
        is None
        or _HEX_64.fullmatch(
            str(document.get("agent_authoring_envelope_digest") or "")
        )
        is None
        or document.get("deterministic_replay_required") is not True
        or document.get("selection_fields_admitted") is not False
        or document.get("source_boundary")
        != "DURABLE_TYPED_PRESELECTION_INPUTS_ONLY_NO_CHAT_AUTHORITY"
        or document.get("chat_history_is_authority") is not False
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_BUNDLE_BOUNDARY_OR_SCHEMA_DRIFT"
        )
    decoded = _decode_typed(
        document["typed_assembly_inputs"], budget=_DecodeBudget()
    )
    if not isinstance(decoded, Mapping):
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_INPUTS_INVALID"
        )
    normalized_inputs = _normalize_assembly_inputs(decoded)
    if _encode_typed(normalized_inputs) != document["typed_assembly_inputs"]:
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_TYPED_INPUTS_NOT_CANONICAL"
        )
    _assert_non_executable(normalized_inputs)
    if any(
        normalized_inputs.get(field) != document.get(field)
        for field in ("run_id", "cycle_index", "decision_at", "symbol")
    ):
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_INPUT_IDENTITY_MISMATCH"
        )
    try:
        preselection = assemble_v31_cycle_evaluation(**normalized_inputs)
        actual = {
            "inputs_receipt_digest": verify_self_digest(
                normalized_inputs["inputs_receipt"], "inputs_receipt_digest"
            ),
            "agent_proposal_digest": verify_self_digest(
                normalized_inputs["agent_proposal"], "agent_proposal_digest"
            ),
            "action_evaluation_digest": verify_self_digest(
                normalized_inputs["action_evaluation"],
                "action_evaluation_digest",
            ),
            "preselection_digest": verify_self_digest(
                preselection, "preselection_digest"
            ),
        }
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_SEMANTIC_REPLAY_FAILED"
        ) from exc
    if any(document.get(field) != digest for field, digest in actual.items()):
        raise V31DurableBundleError(
            "V31_COMPILED_ASSEMBLY_REBUILT_DIGEST_MISMATCH"
        )
    return normalized_inputs, preselection


def _selection_plan(document: Mapping[str, Any]) -> dict[str, Any]:
    plan = {
        "selected_candidate_id": document.get("selected_candidate_id"),
        "reason": document.get("reason"),
        "alternative_explanations": document.get("alternative_explanations"),
        "failure_conditions": document.get("failure_conditions"),
        "next_review_at": document.get("next_review_at"),
        "selected_at": document.get("selected_at"),
    }
    _verify_selection_plan(plan)
    return plan


def _verify_selection_plan(plan: Any) -> None:
    if not isinstance(plan, Mapping) or set(plan) != _SELECTION_PLAN_FIELDS:
        raise V31DurableBundleError("V31_BUNDLE_SELECTION_PLAN_SCHEMA_INVALID")
    if any(
        not isinstance(plan.get(field), str) or not str(plan[field]).strip()
        for field in ("selected_candidate_id", "reason")
    ):
        raise V31DurableBundleError("V31_BUNDLE_SELECTION_PLAN_INVALID")
    alternatives = plan.get("alternative_explanations")
    failures = plan.get("failure_conditions")
    if (
        not isinstance(alternatives, Mapping)
        or any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
            for key, value in alternatives.items()
        )
        or not isinstance(failures, list)
        or not failures
        or any(not isinstance(value, str) or not value.strip() for value in failures)
    ):
        raise V31DurableBundleError("V31_BUNDLE_SELECTION_PLAN_INVALID")
    _timestamp(plan.get("selected_at"), "V31_BUNDLE_SELECTION_TIME_INVALID")
    _timestamp(plan.get("next_review_at"), "V31_BUNDLE_REVIEW_TIME_INVALID")


def seal_v31_durable_assembly_bundle(
    *,
    assembly_inputs: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    recorded_at_by_event: Mapping[str, str],
) -> dict[str, Any]:
    """Seal the complete constructor inputs and deterministic completion plan."""

    if set(documents) != set(EVENT_ORDER):
        raise V31DurableBundleError("V31_BUNDLE_ARTIFACT_SET_INVALID")
    if set(recorded_at_by_event) != set(EVENT_ORDER):
        raise V31DurableBundleError("V31_BUNDLE_EVENT_TIMES_INVALID")
    normalized_inputs = _normalize_assembly_inputs(assembly_inputs)
    _assert_non_executable(normalized_inputs)
    run_id = normalized_inputs["run_id"]
    cycle_index = normalized_inputs["cycle_index"]
    decision_at = normalized_inputs["decision_at"]
    symbol = normalized_inputs["symbol"]
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
        or not isinstance(symbol, str)
        or not symbol.strip()
    ):
        raise V31DurableBundleError("V31_BUNDLE_IDENTITY_INVALID")
    _timestamp(decision_at, "V31_BUNDLE_DECISION_TIME_INVALID")
    event_times = {
        event_type: _timestamp(
            recorded_at_by_event[event_type], "V31_BUNDLE_EVENT_TIME_INVALID"
        )
        for event_type in EVENT_ORDER
    }
    if any(
        event_times[current] < event_times[prior]
        for prior, current in zip(EVENT_ORDER, EVENT_ORDER[1:])
    ):
        raise V31DurableBundleError("V31_BUNDLE_EVENT_TIME_ORDER_INVALID")
    expected_digests: dict[str, str] = {}
    for event_type in EVENT_ORDER:
        document = documents[event_type]
        digest_field = EVENT_DIGEST_FIELDS[event_type]
        try:
            digest = verify_self_digest(document, digest_field)
        except (CanonicalContractError, ValueError) as exc:
            raise V31DurableBundleError("V31_BUNDLE_ARTIFACT_DIGEST_INVALID") from exc
        if (
            document.get("run_id") != run_id
            or document.get("cycle_index") != cycle_index
            or document.get("executable") is not False
        ):
            raise V31DurableBundleError("V31_BUNDLE_ARTIFACT_IDENTITY_INVALID")
        expected_digests[event_type] = digest
    typed_inputs = _encode_typed(normalized_inputs)
    parameters = list(_assembly_parameter_names())
    selection_plan = _selection_plan(documents["SELECTION_SEALED"])
    completed_at = _timestamp(
        documents["COMPLETION_SEALED"].get("completed_at"),
        "V31_BUNDLE_COMPLETION_TIME_INVALID",
    )
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_durable_assembly_bundle",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "symbol": symbol,
            "assembly_parameter_names": parameters,
            "assembly_signature_digest": canonical_digest(parameters),
            "typed_assembly_inputs": typed_inputs,
            "typed_assembly_inputs_digest": canonical_digest(typed_inputs),
            "selection_plan": selection_plan,
            "completed_at": completed_at,
            "recorded_at_by_event": event_times,
            "expected_artifact_digests": expected_digests,
            "source_boundary": "DURABLE_TYPED_INPUTS_ONLY_NO_CHAT_AUTHORITY",
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "assembly_bundle_digest",
    )


def decode_v31_durable_assembly_bundle(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Strictly decode a bundle and fail closed on code/schema drift."""

    if not isinstance(document, Mapping) or set(document) != _BUNDLE_FIELDS:
        raise V31DurableBundleError("V31_BUNDLE_SCHEMA_INVALID")
    try:
        verify_self_digest(document, "assembly_bundle_digest")
    except (CanonicalContractError, ValueError) as exc:
        raise V31DurableBundleError("V31_BUNDLE_DIGEST_INVALID") from exc
    current_parameters = list(_assembly_parameter_names())
    if (
        document.get("schema_id")
        != "theory_paper_v2_v31_durable_assembly_bundle"
        or document.get("schema_version") != "1.0.0"
        or document.get("assembly_parameter_names") != current_parameters
        or document.get("assembly_signature_digest")
        != canonical_digest(current_parameters)
        or document.get("typed_assembly_inputs_digest")
        != canonical_digest(document.get("typed_assembly_inputs"))
        or document.get("source_boundary")
        != "DURABLE_TYPED_INPUTS_ONLY_NO_CHAT_AUTHORITY"
        or document.get("chat_history_is_authority") is not False
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V31DurableBundleError("V31_BUNDLE_BOUNDARY_OR_SCHEMA_DRIFT")
    decoded = _decode_typed(
        document["typed_assembly_inputs"], budget=_DecodeBudget()
    )
    if not isinstance(decoded, Mapping):
        raise V31DurableBundleError("V31_BUNDLE_ASSEMBLY_INPUTS_INVALID")
    normalized_inputs = _normalize_assembly_inputs(decoded)
    if _encode_typed(normalized_inputs) != document["typed_assembly_inputs"]:
        raise V31DurableBundleError("V31_BUNDLE_TYPED_INPUTS_NOT_CANONICAL")
    _assert_non_executable(normalized_inputs)
    if (
        normalized_inputs.get("run_id") != document.get("run_id")
        or normalized_inputs.get("cycle_index") != document.get("cycle_index")
        or normalized_inputs.get("decision_at") != document.get("decision_at")
        or normalized_inputs.get("symbol") != document.get("symbol")
    ):
        raise V31DurableBundleError("V31_BUNDLE_INPUT_IDENTITY_MISMATCH")
    _verify_selection_plan(document.get("selection_plan"))
    _timestamp(document.get("completed_at"), "V31_BUNDLE_COMPLETION_TIME_INVALID")
    event_times = document.get("recorded_at_by_event")
    expected = document.get("expected_artifact_digests")
    if (
        not isinstance(event_times, Mapping)
        or set(event_times) != set(EVENT_ORDER)
        or not isinstance(expected, Mapping)
        or set(expected) != set(EVENT_ORDER)
        or any(
            _HEX_64.fullmatch(str(expected.get(event_type) or "")) is None
            for event_type in EVENT_ORDER
        )
    ):
        raise V31DurableBundleError("V31_BUNDLE_COMPLETION_PLAN_INVALID")
    normalized_times = {
        event_type: _timestamp(
            event_times[event_type], "V31_BUNDLE_EVENT_TIME_INVALID"
        )
        for event_type in EVENT_ORDER
    }
    if any(
        normalized_times[current] < normalized_times[prior]
        for prior, current in zip(EVENT_ORDER, EVENT_ORDER[1:])
    ):
        raise V31DurableBundleError("V31_BUNDLE_EVENT_TIME_ORDER_INVALID")
    return normalized_inputs, dict(document["selection_plan"]), normalized_times


def rebuild_v31_documents_from_bundle(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]], dict[str, str]]:
    """Reconstruct typed inputs and replay all six semantic artifacts."""

    assembly_inputs, plan, event_times = decode_v31_durable_assembly_bundle(
        document
    )
    try:
        preselection = assemble_v31_cycle_evaluation(**assembly_inputs)
        action_evaluation = assembly_inputs["action_evaluation"]
        selection = seal_action_selection(
            evaluation=action_evaluation,
            selected_candidate_id=plan["selected_candidate_id"],
            reason=plan["reason"],
            alternative_explanations=plan["alternative_explanations"],
            failure_conditions=plan["failure_conditions"],
            next_review_at=plan["next_review_at"],
            selected_at=plan["selected_at"],
        )
        accepted = select_v31_cycle_action(
            preselection=preselection,
            action_evaluation=action_evaluation,
            selected_candidate_id=plan["selected_candidate_id"],
            alternative_explanations=plan["alternative_explanations"],
            selection_rationale=plan["reason"],
            failure_conditions=plan["failure_conditions"],
            next_review_at=plan["next_review_at"],
            selected_at=plan["selected_at"],
        )
        completion = complete_v31_research_cycle(
            accepted_state=accepted,
            completed_at=document["completed_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31DurableBundleError("V31_BUNDLE_SEMANTIC_REPLAY_FAILED") from exc
    documents: dict[str, Mapping[str, Any]] = {
        "INPUTS_ADMITTED": assembly_inputs["inputs_receipt"],
        "PROPOSAL_SEALED": assembly_inputs["agent_proposal"],
        "EVALUATION_SEALED": preselection,
        "SELECTION_SEALED": selection,
        "STATE_ACCEPTED": accepted,
        "COMPLETION_SEALED": completion,
    }
    expected = document["expected_artifact_digests"]
    for event_type, artifact in documents.items():
        try:
            digest = verify_self_digest(
                artifact, EVENT_DIGEST_FIELDS[event_type]
            )
        except (CanonicalContractError, ValueError) as exc:
            raise V31DurableBundleError(
                "V31_BUNDLE_REBUILT_ARTIFACT_INVALID"
            ) from exc
        if digest != expected[event_type]:
            raise V31DurableBundleError(
                "V31_BUNDLE_REBUILT_ARTIFACT_DIGEST_MISMATCH"
            )
    return assembly_inputs, documents, event_times


__all__ = [
    "ASSEMBLY_BUNDLE_DIRECTORY",
    "COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD",
    "COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID",
    "EVENT_DIGEST_FIELDS",
    "EVENT_ORDER",
    "V31DurableBundleError",
    "assembly_bundle_relative_ref",
    "decode_v31_durable_assembly_bundle",
    "decode_v31_compiled_assembly_bundle",
    "rebuild_v31_documents_from_bundle",
    "seal_v31_durable_assembly_bundle",
    "seal_v31_compiled_assembly_bundle",
]
