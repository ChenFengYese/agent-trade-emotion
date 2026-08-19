"""Formal, paired generative topology orchestration.

This use case is deliberately separate from ``run_decision_session``.  It
produces immutable experimental evidence only; it cannot reduce trading state,
commit a decision, or dispatch an order.

The model sees semantic transport documents.  Identifiers, references,
authority fields and digests on the archived wrapper are injected
deterministically after the untrusted model output has passed the semantic
schema.  Synthetic and mock transports may exercise this module, but their
receipts are never admissible as formal topology observations.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ..domain.contracts.validation import validate_schema_value


FORMAL_CONTRACT_ID = "TA2-FORMAL-E0-20260731"
FORMAL_CONTRACT_DIGEST = (
    "92a3ef3cfb150e6f17bbc0ded71bdb5674531effab05990084e366397344ec3a"
)
FORMAL_TOPOLOGY_IDS = (
    "SINGLE_STRONG",
    "CLUSTER_POST_PROPOSAL",
    "CLUSTER_BLIND",
)
LEGACY_ROLE_INPUT_SCHEMA_CANONICAL_DIGEST = (
    "e98a5e6fe6bb9f4bfaa7dee40c2778879e792ef22b315a0ecfd67b8bc66fe7be"
)
ROLE_INPUT_TRANSPORT_VERSION = "1.2.0"


class GenerativeTopologyRunError(ValueError):
    """A typed, fail-closed paired-run error."""


class RunEvidenceClass(StrEnum):
    FORMAL_GENERATIVE = "FORMAL_GENERATIVE"
    NON_FORMAL_MOCK = "NON_FORMAL_MOCK"
    NON_FORMAL_SYNTHETIC = "NON_FORMAL_SYNTHETIC"


class ModelAttemptStatus(StrEnum):
    COMPLETE = "COMPLETE"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class TurnStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class UsageRecord:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int

    def __post_init__(self) -> None:
        values = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_output_tokens,
            self.total_tokens,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise GenerativeTopologyRunError("MODEL_USAGE_INVALID")
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise GenerativeTopologyRunError("MODEL_USAGE_TOTAL_INVALID")


@dataclass(frozen=True, slots=True)
class ModelTransportCapability:
    adapter_id: str
    transport_evidence_class: str
    provider_transport: str
    cli_version: str
    authenticated: bool
    real_generative: bool
    ephemeral_sessions: bool
    read_only_workspace: bool
    empty_temporary_workspace: bool
    tool_calls_detectable: bool
    usage_available: bool
    hard_token_limit_available: bool
    served_model_attestation_available: bool
    reason_codes: tuple[str, ...] = ()

    def formal_ready(self, contract: Mapping[str, Any]) -> bool:
        topology = contract["topology_contract"]
        return (
            self.transport_evidence_class == "REAL_GENERATIVE"
            and self.provider_transport == topology["provider_transport"]
            and self.cli_version == topology["cli_version_required"]
            and self.authenticated
            and self.real_generative
            and self.ephemeral_sessions
            and self.read_only_workspace
            and self.empty_temporary_workspace
            and self.tool_calls_detectable
            and self.usage_available
            and self.hard_token_limit_available
            and not self.reason_codes
        )


@dataclass(frozen=True, slots=True)
class ModelCallRequest:
    paired_session_id: str
    topology_id: str
    turn_ordinal: int
    phase_id: str
    role_id: str
    expected_output_kind: str
    provider_input_bytes: bytes
    provider_input_digest: str
    semantic_output_schema_bytes: bytes
    model: str
    reasoning_effort: str
    token_limit: int
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ModelAttemptResult:
    status: ModelAttemptStatus
    raw_event_bytes: bytes
    raw_stderr_bytes: bytes
    raw_output_bytes: bytes | None
    requested_model: str
    served_model_attestation: str | None
    usage: UsageRecord | None
    tool_call_names: tuple[str, ...]
    retry_count: int
    latency_ms: int
    error_code: str | None = None
    model_rerouted: bool = False

    def __post_init__(self) -> None:
        if (
            self.retry_count < 0
            or self.latency_ms < 0
            or not self.requested_model
            or (
                self.status is ModelAttemptStatus.COMPLETE
                and self.raw_output_bytes is None
            )
            or (
                self.status is not ModelAttemptStatus.COMPLETE
                and not self.error_code
            )
        ):
            raise GenerativeTopologyRunError("MODEL_ATTEMPT_RESULT_INVALID")


class GenerativeModelPort(Protocol):
    def capability(self) -> ModelTransportCapability: ...

    def invoke(self, request: ModelCallRequest) -> ModelAttemptResult: ...


class PairedRunArchivePort(Protocol):
    @property
    def run_ref(self) -> str: ...

    def write_bytes(self, relative_path: str, payload: bytes) -> str: ...

    def write_json(self, relative_path: str, value: Mapping[str, Any]) -> str: ...


@dataclass(frozen=True, slots=True)
class ProjectionValue:
    source_object_ref: Mapping[str, Any]
    json_pointer: str
    value: Any

    def __post_init__(self) -> None:
        _validate_object_ref(self.source_object_ref)
        if not isinstance(self.json_pointer, str) or (
            self.json_pointer and not self.json_pointer.startswith("/")
        ):
            raise GenerativeTopologyRunError("ROLE_INPUT_JSON_POINTER_INVALID")
        canonical_bytes(self.value)


@dataclass(frozen=True, slots=True)
class FrozenInstruction:
    instruction_id: str
    instruction_bytes: bytes
    instruction_digest: str

    def __post_init__(self) -> None:
        if (
            not self.instruction_id
            or not isinstance(self.instruction_bytes, bytes)
            or not self.instruction_bytes
            or hashlib.sha256(self.instruction_bytes).hexdigest()
            != self.instruction_digest
        ):
            raise GenerativeTopologyRunError(
                "REASONING_STRATEGY_DIGEST_MISMATCH"
            )
        try:
            self.instruction_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GenerativeTopologyRunError(
                "REASONING_STRATEGY_NOT_UTF8"
            ) from exc


@dataclass(frozen=True, slots=True)
class PairedGenerativeRunRequest:
    paired_session_id: str
    evidence_class: RunEvidenceClass
    dataset_kind: str
    sample_cohort: str
    sample_index: int
    requested_topology_ids: tuple[str, ...]
    selected_topology_id: str | None
    topology_selection_result_digest: str | None
    dataset_manifest_ref: Mapping[str, Any]
    dataset_transport_contract_verdict: str
    dataset_transport_schema_digest: str
    decision_context_ref: Mapping[str, Any]
    common_projection_values: tuple[ProjectionValue, ...]
    formal_contract: Mapping[str, Any]
    reasoning_instructions: Mapping[str, FrozenInstruction]

    def __post_init__(self) -> None:
        if not self.paired_session_id:
            raise GenerativeTopologyRunError("PAIRED_SESSION_ID_MISSING")
        validate_formal_experiment_contract(self.formal_contract)
        _validate_object_ref(self.dataset_manifest_ref)
        _validate_object_ref(self.decision_context_ref)
        if (
            self.dataset_transport_contract_verdict != "PASS"
            or self.dataset_transport_schema_digest
            != canonical_digest(ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA)
        ):
            raise GenerativeTopologyRunError(
                "ROLE_INPUT_TRANSPORT_REPAIR_NOT_BOUND"
            )
        if not self.common_projection_values:
            raise GenerativeTopologyRunError(
                "COMMON_CONTEXT_PROJECTIONS_MISSING"
            )
        cohort_ranges = {
            "TOPOLOGY_SELECTION": range(96, 128),
            "POLICY_QUALIFICATION": range(128, 160),
            "FORMAL_EXPERIMENT": range(160, 192),
        }
        cohort_range = cohort_ranges.get(self.sample_cohort)
        if cohort_range is None or self.sample_index not in cohort_range:
            raise GenerativeTopologyRunError(
                "FORMAL_SAMPLE_COHORT_INDEX_MISMATCH"
            )
        if self.sample_cohort == "TOPOLOGY_SELECTION":
            if (
                self.requested_topology_ids != FORMAL_TOPOLOGY_IDS
                or self.selected_topology_id is not None
                or self.topology_selection_result_digest is not None
            ):
                raise GenerativeTopologyRunError(
                    "TOPOLOGY_SELECTION_REQUIRES_ALL_THREE_ARMS"
                )
        elif (
            self.selected_topology_id not in FORMAL_TOPOLOGY_IDS
            or self.requested_topology_ids
            != (self.selected_topology_id,)
            or not _is_sha256_digest(
                self.topology_selection_result_digest
            )
        ):
            raise GenerativeTopologyRunError(
                "POST_SELECTION_REQUIRES_FROZEN_SELECTED_TOPOLOGY"
            )
        required = {"SINGLE_STRONG", "PROPOSER", "CHALLENGER", "SELECTOR"}
        if set(self.reasoning_instructions) != required:
            raise GenerativeTopologyRunError(
                "REASONING_STRATEGY_SET_INCOMPLETE"
            )


_OBJECT_REF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_id",
        "schema_version",
        "object_id",
        "payload_digest",
        "object_digest",
    ],
    "properties": {
        "schema_id": {"type": "string", "minLength": 1},
        "schema_version": {
            "type": "string",
            "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$",
        },
        "object_id": {"type": "string", "minLength": 1},
        "payload_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "object_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
    },
}


def _is_sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA = {
    "$id": "urn:theory-agent-v2:resolved_role_input_document:1.2.0",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "resolved_role_input_document.v1_2_deduplicated",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_id",
        "schema_version",
        "decision_context_ref",
        "role_context_view_ref",
        "role_id",
        "common_context_digest",
        "projection_bindings",
    ],
    "properties": {
        "schema_id": {
            "type": "string",
            "const": "resolved_role_input_document",
        },
        "schema_version": {
            "type": "string",
            "const": ROLE_INPUT_TRANSPORT_VERSION,
        },
        "decision_context_ref": _OBJECT_REF_SCHEMA,
        "role_context_view_ref": _OBJECT_REF_SCHEMA,
        "role_id": {
            "type": "string",
            "enum": ["PROPOSER", "CHALLENGER", "SELECTOR"],
        },
        "common_context_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "projection_bindings": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_object_ref",
                    "json_pointer",
                    "value_digest",
                ],
                "properties": {
                    "source_object_ref": _OBJECT_REF_SCHEMA,
                    "json_pointer": {"type": "string"},
                    "value_digest": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
            },
        },
    },
}


SEMANTIC_MODEL_OUTPUT_SCHEMA = {
    "$id": "urn:theory-agent-v2:topology-semantic-payload:1.0.0",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "topology_semantic_payload.v1",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_id",
        "schema_version",
        "output_kind",
        "analysis_summary",
        "primary_path",
        "alternative_paths",
        "null_path",
        "other_or_unknown_path",
        "challenge_claims",
        "selected_action",
        "unknowns",
    ],
    "properties": {
        "schema_id": {
            "type": "string",
            "const": "topology_semantic_payload",
        },
        "schema_version": {"type": "string", "const": "1.0.0"},
        "output_kind": {
            "type": "string",
            "enum": [
                "PROPOSAL",
                "SELF_REVIEW",
                "CHALLENGE_POST_PROPOSAL",
                "CHALLENGE_BLIND",
                "SELECTION",
            ],
        },
        "analysis_summary": {
            "type": "string",
            "minLength": 1,
            "maxLength": 8192,
        },
        "primary_path": {
            "anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 2048},
                {"type": "null"},
            ]
        },
        "alternative_paths": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 2048,
            },
        },
        "null_path": {
            "anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 2048},
                {"type": "null"},
            ]
        },
        "other_or_unknown_path": {
            "anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 2048},
                {"type": "null"},
            ]
        },
        "challenge_claims": {
            "type": "array",
            "maxItems": 32,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["category", "summary"],
                "properties": {
                    "category": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 128,
                    },
                    "summary": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 2048,
                    },
                },
            },
        },
        "selected_action": {
            "anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 2048},
                {"type": "null"},
            ]
        },
        "unknowns": {
            "type": "array",
            "maxItems": 32,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 2048,
            },
        },
    },
}


def _validate_object_ref(value: Mapping[str, Any]) -> None:
    validate_schema_value(dict(value), _OBJECT_REF_SCHEMA)


def _object_ref(
    *,
    schema_id: str,
    schema_version: str,
    object_id: str,
    payload_digest: str,
    object_digest: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "object_id": object_id,
        "payload_digest": payload_digest,
        "object_digest": object_digest or payload_digest,
    }


def make_deterministic_object_ref(
    *,
    schema_id: str,
    schema_version: str,
    object_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a canonical inline ObjectRef for a deterministic payload."""

    digest = canonical_digest(dict(payload))
    value = _object_ref(
        schema_id=schema_id,
        schema_version=schema_version,
        object_id=object_id,
        payload_digest=digest,
    )
    _validate_object_ref(value)
    return value


def validate_formal_experiment_contract(
    contract: Mapping[str, Any],
) -> str:
    supplied = verify_self_digest(contract, "contract_digest")
    topology = contract.get("topology_contract")
    if (
        supplied != FORMAL_CONTRACT_DIGEST
        or contract.get("contract_id") != FORMAL_CONTRACT_ID
        or contract.get("frozen_before_first_generative_call") is not True
        or contract.get("system_mode") != "E0_OFFLINE_COUNTERFACTUAL"
        or contract.get("external_execution_authority") != "NONE_E0"
        or contract.get("executable") is not False
        or not isinstance(topology, Mapping)
        or tuple(topology.get("topology_ids", ())) != FORMAL_TOPOLOGY_IDS
        or topology.get("model") != "gpt-5.6-sol"
        or topology.get("reasoning_effort") != "medium"
        or topology.get("provider_transport")
        != "CODEX_EXEC_CHATGPT_LOGIN"
        or topology.get("cli_version_required")
        != "codex-cli 0.146.0-alpha.3.1"
        or topology.get("calls_per_topology_limit") != 3
        or topology.get("total_token_limit_per_topology") != 90_000
        or topology.get("timeout_seconds_per_call") != 120
        or topology.get("tool_policy") != "NO_TOOLS"
        or topology.get("thread_policy") != "EPHEMERAL_NO_RESUME"
        or topology.get("workspace_policy")
        != "EMPTY_TEMP_DIRECTORY_READ_ONLY"
        or topology.get("input_equality")
        != "BYTE_IDENTICAL_COMMON_CONTEXT"
        or topology.get("formal_output_requires_usage") is not True
        or topology.get("synthetic_or_mock_disposition")
        != "NOT_FORMAL_EVIDENCE"
    ):
        raise GenerativeTopologyRunError(
            "FORMAL_EXPERIMENT_CONTRACT_MISMATCH"
        )
    return supplied


def role_input_transport_repair_receipt() -> dict[str, Any]:
    """Describe the versioned repair without mutating the frozen v1 schema."""

    receipt = {
        "schema_id": "role_input_transport_repair_receipt",
        "schema_version": "1.0.0",
        "legacy_schema_id": "resolved_role_input_document",
        "legacy_schema_version": "1.0.0",
        "legacy_schema_canonical_digest": (
            LEGACY_ROLE_INPUT_SCHEMA_CANONICAL_DIGEST
        ),
        "legacy_verdict": (
            "INCOMPATIBLE_MISSING_INLINE_PROJECTION_VALUES"
        ),
        "superseded_schema_version": "1.1.0-repair",
        "superseded_verdict": (
            "VALID_BINDING_BUT_DUPLICATED_FULL_PROJECTION_VALUES"
        ),
        "repair_schema_id": "resolved_role_input_document",
        "repair_schema_version": ROLE_INPUT_TRANSPORT_VERSION,
        "repair_schema_digest": canonical_digest(
            ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
        ),
        "model_output_authority": "SEMANTIC_PAYLOAD_ONLY",
        "deterministic_wrapper_authority": (
            "IDENTIFIERS_REFERENCES_AUTHORITY_FIELDS_DIGESTS"
        ),
        "full_projection_value_authority": (
            "SHARED_BYTE_IDENTICAL_COMMON_CONTEXT_ONLY"
        ),
        "role_input_value_authority": (
            "SOURCE_REF_JSON_POINTER_AND_VALUE_DIGEST_ONLY"
        ),
        "verdict": "PASS_VERSIONED_TRANSPORT_REPAIR_REQUIRED",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(receipt, "receipt_digest")


def build_resolved_role_input_document(
    *,
    decision_context_ref: Mapping[str, Any],
    role_context_view_ref: Mapping[str, Any],
    role_id: str,
    common_context_digest: str,
    projection_values: Sequence[ProjectionValue],
) -> bytes:
    document = {
        "schema_id": "resolved_role_input_document",
        "schema_version": ROLE_INPUT_TRANSPORT_VERSION,
        "decision_context_ref": dict(decision_context_ref),
        "role_context_view_ref": dict(role_context_view_ref),
        "role_id": role_id,
        "common_context_digest": common_context_digest,
        "projection_bindings": [
            {
                "source_object_ref": dict(item.source_object_ref),
                "json_pointer": item.json_pointer,
                "value_digest": canonical_digest(item.value),
            }
            for item in projection_values
        ],
    }
    validate_schema_value(document, ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA)
    return canonical_bytes(document)


def _validate_semantic_model_output(
    raw_output: bytes, expected_output_kind: str
) -> dict[str, Any]:
    parsed = loads_json_strict(raw_output)
    validate_schema_value(parsed, SEMANTIC_MODEL_OUTPUT_SCHEMA)
    bounded_strings = [
        (parsed["analysis_summary"], 8192),
        *((value, 2048) for value in parsed["alternative_paths"]),
        *((value, 2048) for value in parsed["unknowns"]),
        *(
            (value, 2048)
            for value in (
                parsed["primary_path"],
                parsed["null_path"],
                parsed["other_or_unknown_path"],
                parsed["selected_action"],
            )
            if value is not None
        ),
        *(
            item
            for claim in parsed["challenge_claims"]
            for item in (
                (claim["category"], 128),
                (claim["summary"], 2048),
            )
        ),
    ]
    if (
        len(parsed["alternative_paths"]) > 16
        or len(parsed["challenge_claims"]) > 32
        or len(parsed["unknowns"]) > 32
        or any(len(value) > limit for value, limit in bounded_strings)
    ):
        raise GenerativeTopologyRunError(
            "MODEL_SEMANTIC_OUTPUT_STRUCTURAL_CAP_EXCEEDED"
        )
    if parsed["output_kind"] != expected_output_kind:
        raise GenerativeTopologyRunError(
            "MODEL_SEMANTIC_OUTPUT_KIND_MISMATCH"
        )
    return parsed


def wrap_semantic_model_output(
    *,
    paired_session_id: str,
    topology_id: str,
    turn_ordinal: int,
    role_id: str,
    role_context_view_ref: Mapping[str, Any],
    source_input_digest: str,
    expected_output_kind: str,
    raw_output: bytes,
) -> dict[str, Any]:
    semantic = _validate_semantic_model_output(
        raw_output, expected_output_kind
    )
    wrapper = {
        "schema_id": "deterministic_semantic_agent_envelope",
        "schema_version": "1.0.0",
        "record_id": (
            f"semantic-envelope:{paired_session_id}:"
            f"{topology_id}:{turn_ordinal:02d}"
        ),
        "role_id": role_id,
        "role_context_view_ref": dict(role_context_view_ref),
        "source_input_digest": source_input_digest,
        "output_kind": expected_output_kind,
        "semantic_payload": semantic,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(wrapper, "record_digest")


@dataclass(frozen=True, slots=True)
class _TurnTemplate:
    phase_id: str
    role_id: str
    expected_output_kind: str
    instruction_key: str
    visible_prior_turns: tuple[int, ...]


_TURN_PROGRAMS: dict[str, tuple[_TurnTemplate, ...]] = {
    "SINGLE_STRONG": (
        _TurnTemplate(
            "PROPOSE",
            "PROPOSER",
            "PROPOSAL",
            "SINGLE_STRONG",
            (),
        ),
        _TurnTemplate(
            "SELF_REVIEW",
            "CHALLENGER",
            "SELF_REVIEW",
            "SINGLE_STRONG",
            (0,),
        ),
        _TurnTemplate(
            "SELECT",
            "SELECTOR",
            "SELECTION",
            "SINGLE_STRONG",
            (0, 1),
        ),
    ),
    "CLUSTER_POST_PROPOSAL": (
        _TurnTemplate(
            "PROPOSE",
            "PROPOSER",
            "PROPOSAL",
            "PROPOSER",
            (),
        ),
        _TurnTemplate(
            "CHALLENGE_POST",
            "CHALLENGER",
            "CHALLENGE_POST_PROPOSAL",
            "CHALLENGER",
            (0,),
        ),
        _TurnTemplate(
            "SELECT",
            "SELECTOR",
            "SELECTION",
            "SELECTOR",
            (0, 1),
        ),
    ),
    "CLUSTER_BLIND": (
        _TurnTemplate(
            "PROPOSE",
            "PROPOSER",
            "PROPOSAL",
            "PROPOSER",
            (),
        ),
        _TurnTemplate(
            "CHALLENGE_BLIND",
            "CHALLENGER",
            "CHALLENGE_BLIND",
            "CHALLENGER",
            (),
        ),
        _TurnTemplate(
            "SELECT",
            "SELECTOR",
            "SELECTION",
            "SELECTOR",
            (0, 1),
        ),
    ),
}


def _common_context_bytes(
    projections: Sequence[ProjectionValue],
) -> bytes:
    return canonical_bytes(
        {
            "schema_id": "paired_common_context_projection",
            "schema_version": "1.0.0",
            "projection_values": [
                {
                    "source_object_ref": dict(item.source_object_ref),
                    "json_pointer": item.json_pointer,
                    "value": item.value,
                }
                for item in projections
            ],
        }
    )


def _compile_provider_input(
    *,
    instruction: FrozenInstruction,
    phase_id: str,
    expected_output_kind: str,
    role_input_bytes: bytes,
    common_context_bytes: bytes,
    prior_envelopes: Sequence[bytes],
) -> tuple[bytes, int, int]:
    phase = (
        "\n\nFORMAL PHASE: "
        f"{phase_id}\nREQUIRED output_kind: {expected_output_kind}\n"
        "Return only JSON matching the supplied semantic output schema. "
        "Use no tools, repository, network, memory, or execution.\n"
    ).encode("utf-8")
    role_header = b"\n<resolved-role-input>\n"
    role_footer = b"\n</resolved-role-input>\n"
    common_header = b"<byte-identical-common-context>\n"
    common_footer = b"\n</byte-identical-common-context>\n"
    prefix = (
        instruction.instruction_bytes
        + phase
        + role_header
        + role_input_bytes
        + role_footer
        + common_header
    )
    common_start = len(prefix)
    suffix_parts = [common_footer]
    for index, envelope in enumerate(prior_envelopes):
        suffix_parts.extend(
            (
                f"<prior-semantic-envelope ordinal=\"{index}\">\n".encode(
                    "utf-8"
                ),
                envelope,
                b"\n</prior-semantic-envelope>\n",
            )
        )
    payload = prefix + common_context_bytes + b"".join(suffix_parts)
    return payload, common_start, common_start + len(common_context_bytes)


def _usage_payload(usage: UsageRecord | None) -> dict[str, int] | None:
    return asdict(usage) if usage is not None else None


def _archive_artifact_ref(
    archive: PairedRunArchivePort,
    relative_path: str,
    digest: str,
) -> str:
    return f"{archive.run_ref}:{relative_path}:{digest}"


def _aggregate_usage(
    values: Sequence[UsageRecord],
) -> dict[str, int]:
    return {
        field: sum(getattr(value, field) for value in values)
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "total_tokens",
        )
    }


def _terminal_receipt(
    *,
    request: PairedGenerativeRunRequest,
    archive: PairedRunArchivePort,
    contract_digest: str,
    capability: ModelTransportCapability,
    common_context_digest: str,
    model_configuration_digest: str,
    budget_limit_digest: str,
    arm_receipts: Sequence[Mapping[str, Any]],
    reason_codes: Sequence[str],
    started_at: datetime,
    completed_at: datetime,
) -> dict[str, Any]:
    formal = (
        request.evidence_class is RunEvidenceClass.FORMAL_GENERATIVE
        and request.dataset_kind == "FROZEN_REAL_MARKET"
        and not reason_codes
        and len(arm_receipts) == len(request.requested_topology_ids)
        and all(item.get("status") == "COMPLETE" for item in arm_receipts)
    )
    receipt = {
        "schema_id": "paired_generative_topology_run_receipt",
        "schema_version": "1.0.0",
        "paired_session_id": request.paired_session_id,
        "sample_cohort": request.sample_cohort,
        "sample_index": request.sample_index,
        "formal_contract_digest": contract_digest,
        "dataset_digest": request.dataset_manifest_ref["object_digest"],
        "selected_topology_id": request.selected_topology_id,
        "topology_selection_result_digest": (
            request.topology_selection_result_digest
        ),
        "evidence_class": request.evidence_class.value,
        "dataset_kind": request.dataset_kind,
        "dataset_manifest_ref": dict(request.dataset_manifest_ref),
        "dataset_transport_contract_verdict": (
            request.dataset_transport_contract_verdict
        ),
        "dataset_transport_schema_digest": (
            request.dataset_transport_schema_digest
        ),
        "topology_ids": list(request.requested_topology_ids),
        "arm_order": list(request.requested_topology_ids),
        "provider_transport": capability.provider_transport,
        "transport_adapter_id": capability.adapter_id,
        "requested_model": request.formal_contract["topology_contract"][
            "model"
        ],
        "served_model_attestation": None,
        "served_model_attestation_status": (
            "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT"
        ),
        "model_configuration_digest": model_configuration_digest,
        "budget_limit_digest": budget_limit_digest,
        "common_context_digest": common_context_digest,
        "raw_input_ref": _archive_artifact_ref(
            archive,
            "shared/byte-identical-common-context.json",
            common_context_digest,
        ),
        "role_input_transport_repair_receipt": (
            role_input_transport_repair_receipt()
        ),
        "arm_receipts": list(arm_receipts),
        "started_at": started_at.astimezone(UTC).isoformat(),
        "completed_at": completed_at.astimezone(UTC).isoformat(),
        "formal_evidence": formal,
        "formal_observation_eligible": formal,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "write_once_run_ref": archive.run_ref,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(receipt, "receipt_digest")


def run_paired_generative_topologies(
    request: PairedGenerativeRunRequest,
    *,
    model_port: GenerativeModelPort,
    archive: PairedRunArchivePort,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """Run all frozen topology programs once and archive every exact byte.

    Formal admission is fail-closed.  A blocked or partial run still receives
    an immutable terminal receipt, but never a formal observation.
    """

    started_at = clock()
    if started_at.tzinfo is None:
        raise GenerativeTopologyRunError("RUN_CLOCK_NAIVE")
    contract_digest = validate_formal_experiment_contract(
        request.formal_contract
    )
    topology_contract = request.formal_contract["topology_contract"]
    capability = model_port.capability()
    common_bytes = _common_context_bytes(request.common_projection_values)
    common_digest = archive.write_bytes(
        "shared/byte-identical-common-context.json", common_bytes
    )
    archive.write_json(
        "shared/role-input-transport-repair-receipt.json",
        role_input_transport_repair_receipt(),
    )
    archive.write_json(
        "shared/transport-capability.json",
        {
            **asdict(capability),
            "formal_ready": capability.formal_ready(
                request.formal_contract
            ),
        },
    )
    model_configuration = {
        "model": topology_contract["model"],
        "reasoning_effort": topology_contract["reasoning_effort"],
        "temperature": topology_contract["temperature"],
        "provider_transport": topology_contract["provider_transport"],
        "thread_policy": topology_contract["thread_policy"],
        "tool_policy": topology_contract["tool_policy"],
        "workspace_policy": topology_contract["workspace_policy"],
        "semantic_output_schema_digest": canonical_digest(
            SEMANTIC_MODEL_OUTPUT_SCHEMA
        ),
        "reasoning_instruction_digests": {
            key: value.instruction_digest
            for key, value in sorted(request.reasoning_instructions.items())
        },
    }
    model_configuration_digest = canonical_digest(model_configuration)
    budget = {
        "calls_per_topology_limit": topology_contract[
            "calls_per_topology_limit"
        ],
        "total_token_limit_per_topology": topology_contract[
            "total_token_limit_per_topology"
        ],
        "per_call_token_limits": [30_000, 30_000, 30_000],
        "timeout_seconds_per_call": topology_contract[
            "timeout_seconds_per_call"
        ],
        "retry_policy": "NO_APPLICATION_RETRY_THREE_CALLS_EXHAUST_BUDGET",
    }
    budget_limit_digest = canonical_digest(budget)
    archive.write_json(
        "shared/frozen-run-bindings.json",
        {
            "formal_contract_digest": contract_digest,
            "sample_cohort": request.sample_cohort,
            "sample_index": request.sample_index,
            "requested_topology_ids": list(
                request.requested_topology_ids
            ),
            "selected_topology_id": request.selected_topology_id,
            "topology_selection_result_digest": (
                request.topology_selection_result_digest
            ),
            "dataset_manifest_ref": dict(request.dataset_manifest_ref),
            "dataset_transport_contract_verdict": (
                request.dataset_transport_contract_verdict
            ),
            "dataset_transport_schema_digest": (
                request.dataset_transport_schema_digest
            ),
            "common_context_digest": common_digest,
            "model_configuration": model_configuration,
            "model_configuration_digest": model_configuration_digest,
            "budget": budget,
            "budget_limit_digest": budget_limit_digest,
            "evidence_class": request.evidence_class.value,
            "dataset_kind": request.dataset_kind,
        },
    )

    admission_reasons: list[str] = []
    blocking_reasons: list[str] = []
    if request.evidence_class is not RunEvidenceClass.FORMAL_GENERATIVE:
        admission_reasons.append("NON_FORMAL_EVIDENCE_EXCLUDED")
    elif request.dataset_kind != "FROZEN_REAL_MARKET":
        blocking_reasons.append("FORMAL_DATASET_KIND_INVALID")
    if (
        request.evidence_class is RunEvidenceClass.FORMAL_GENERATIVE
        and not capability.formal_ready(request.formal_contract)
    ):
        blocking_reasons.extend(
            capability.reason_codes
            or ("REAL_MODEL_TRANSPORT_CAPABILITY_BLOCKED",)
        )

    arm_receipts: list[dict[str, Any]] = []
    if not blocking_reasons:
        for topology_id in request.requested_topology_ids:
            turn_receipts: list[dict[str, Any]] = []
            wrapped_envelopes: list[bytes] = []
            arm_usage: list[UsageRecord] = []
            arm_errors: list[str] = []
            for ordinal, template in enumerate(
                _TURN_PROGRAMS[topology_id]
            ):
                instruction = request.reasoning_instructions[
                    template.instruction_key
                ]
                role_context_payload = {
                    "schema_id": "paired_role_context_binding",
                    "schema_version": "1.0.0",
                    "paired_session_id": request.paired_session_id,
                    "sample_cohort": request.sample_cohort,
                    "sample_index": request.sample_index,
                    "topology_id": topology_id,
                    "selected_topology_id": (
                        request.selected_topology_id
                    ),
                    "topology_selection_result_digest": (
                        request.topology_selection_result_digest
                    ),
                    "turn_ordinal": ordinal,
                    "role_id": template.role_id,
                    "common_context_digest": common_digest,
                    "instruction_digest": instruction.instruction_digest,
                    "repository_access": "DENIED",
                    "evidence_refresh": "DENIED",
                    "external_execution": "DENIED",
                }
                role_context_digest = canonical_digest(
                    role_context_payload
                )
                role_context_view_ref = _object_ref(
                    schema_id="paired_role_context_binding",
                    schema_version="1.0.0",
                    object_id=(
                        f"role-context:{request.paired_session_id}:"
                        f"{topology_id}:{ordinal:02d}"
                    ),
                    payload_digest=role_context_digest,
                )
                role_input_bytes = build_resolved_role_input_document(
                    decision_context_ref=request.decision_context_ref,
                    role_context_view_ref=role_context_view_ref,
                    role_id=template.role_id,
                    common_context_digest=common_digest,
                    projection_values=request.common_projection_values,
                )
                prior = tuple(
                    wrapped_envelopes[index]
                    for index in template.visible_prior_turns
                )
                provider_input, common_start, common_end = (
                    _compile_provider_input(
                        instruction=instruction,
                        phase_id=template.phase_id,
                        expected_output_kind=(
                            template.expected_output_kind
                        ),
                        role_input_bytes=role_input_bytes,
                        common_context_bytes=common_bytes,
                        prior_envelopes=prior,
                    )
                )
                if provider_input[common_start:common_end] != common_bytes:
                    raise GenerativeTopologyRunError(
                        "COMMON_CONTEXT_BYTE_EQUALITY_BROKEN"
                    )
                turn_root = (
                    f"arms/{topology_id}/turn-{ordinal:02d}-"
                    f"{template.phase_id.lower()}"
                )
                role_input_digest = archive.write_bytes(
                    f"{turn_root}/resolved-role-input.json",
                    role_input_bytes,
                )
                archive.write_json(
                    f"{turn_root}/role-context-binding.json",
                    role_context_payload,
                )
                provider_input_digest = archive.write_bytes(
                    f"{turn_root}/provider-input.bin", provider_input
                )
                schema_bytes = canonical_bytes(
                    SEMANTIC_MODEL_OUTPUT_SCHEMA
                )
                archive.write_bytes(
                    f"{turn_root}/semantic-output-schema.json",
                    schema_bytes,
                )
                call = ModelCallRequest(
                    paired_session_id=request.paired_session_id,
                    topology_id=topology_id,
                    turn_ordinal=ordinal,
                    phase_id=template.phase_id,
                    role_id=template.role_id,
                    expected_output_kind=(
                        template.expected_output_kind
                    ),
                    provider_input_bytes=provider_input,
                    provider_input_digest=provider_input_digest,
                    semantic_output_schema_bytes=schema_bytes,
                    model=topology_contract["model"],
                    reasoning_effort=topology_contract[
                        "reasoning_effort"
                    ],
                    token_limit=budget["per_call_token_limits"][ordinal],
                    timeout_seconds=topology_contract[
                        "timeout_seconds_per_call"
                    ],
                )
                attempt = model_port.invoke(call)
                raw_event_digest = archive.write_bytes(
                    f"{turn_root}/attempt-00/raw-events.jsonl",
                    attempt.raw_event_bytes,
                )
                raw_stderr_digest = archive.write_bytes(
                    f"{turn_root}/attempt-00/raw-stderr.bin",
                    attempt.raw_stderr_bytes,
                )
                raw_output_digest = None
                if attempt.raw_output_bytes is not None:
                    raw_output_digest = archive.write_bytes(
                        f"{turn_root}/attempt-00/raw-output.bin",
                        attempt.raw_output_bytes,
                    )
                error_code = attempt.error_code
                wrapped_digest = None
                if (
                    attempt.status is ModelAttemptStatus.COMPLETE
                    and attempt.raw_output_bytes is not None
                ):
                    if attempt.requested_model != topology_contract["model"]:
                        error_code = "REQUESTED_MODEL_BINDING_MISMATCH"
                    elif attempt.model_rerouted:
                        error_code = "MODEL_REROUTE_FORBIDDEN"
                    elif attempt.tool_call_names:
                        error_code = "MODEL_TOOL_CALL_FORBIDDEN"
                    elif attempt.usage is None:
                        error_code = "MODEL_USAGE_MISSING"
                    else:
                        try:
                            wrapped = wrap_semantic_model_output(
                                paired_session_id=(
                                    request.paired_session_id
                                ),
                                topology_id=topology_id,
                                turn_ordinal=ordinal,
                                role_id=template.role_id,
                                role_context_view_ref=(
                                    role_context_view_ref
                                ),
                                source_input_digest=(
                                    provider_input_digest
                                ),
                                expected_output_kind=(
                                    template.expected_output_kind
                                ),
                                raw_output=attempt.raw_output_bytes,
                            )
                        except ValueError as exc:
                            error_code = (
                                str(exc)
                                or "MODEL_SEMANTIC_OUTPUT_INVALID"
                            )
                        else:
                            wrapped_bytes = canonical_bytes(wrapped)
                            wrapped_digest = archive.write_bytes(
                                f"{turn_root}/deterministic-wrapper.json",
                                wrapped_bytes,
                            )
                            wrapped_envelopes.append(wrapped_bytes)
                            arm_usage.append(attempt.usage)
                if error_code is None and attempt.status is not ModelAttemptStatus.COMPLETE:
                    error_code = "MODEL_ATTEMPT_INCOMPLETE"
                turn_status = (
                    TurnStatus.COMPLETE
                    if error_code is None
                    else TurnStatus.FAILED
                )
                turn_receipt = {
                    "turn_ordinal": ordinal,
                    "phase_id": template.phase_id,
                    "role_id": template.role_id,
                    "expected_output_kind": (
                        template.expected_output_kind
                    ),
                    "visible_prior_turns": list(
                        template.visible_prior_turns
                    ),
                    "role_input_digest": role_input_digest,
                    "provider_input_digest": provider_input_digest,
                    "common_context_digest": common_digest,
                    "common_context_byte_range": [
                        common_start,
                        common_end,
                    ],
                    "requested_model": attempt.requested_model,
                    "served_model_attestation": (
                        attempt.served_model_attestation
                    ),
                    "served_model_attestation_status": (
                        "ATTESTED"
                        if attempt.served_model_attestation is not None
                        else (
                            "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT"
                        )
                    ),
                    "model_configuration_digest": (
                        model_configuration_digest
                    ),
                    "budget_limit_digest": budget_limit_digest,
                    "attempt_count": 1,
                    "retry_count": attempt.retry_count,
                    "raw_event_digest": raw_event_digest,
                    "raw_event_ref": _archive_artifact_ref(
                        archive,
                        f"{turn_root}/attempt-00/raw-events.jsonl",
                        raw_event_digest,
                    ),
                    "raw_stderr_digest": raw_stderr_digest,
                    "raw_output_digest": raw_output_digest,
                    "raw_output_ref": (
                        _archive_artifact_ref(
                            archive,
                            f"{turn_root}/attempt-00/raw-output.bin",
                            raw_output_digest,
                        )
                        if raw_output_digest is not None
                        else None
                    ),
                    "deterministic_wrapper_digest": wrapped_digest,
                    "usage": _usage_payload(attempt.usage),
                    "tool_call_names": list(attempt.tool_call_names),
                    "latency_ms": attempt.latency_ms,
                    "status": turn_status.value,
                    "error_code": error_code,
                }
                turn_receipt = self_digest(
                    turn_receipt, "receipt_digest"
                )
                archive.write_json(
                    f"{turn_root}/turn-receipt.json", turn_receipt
                )
                turn_receipts.append(turn_receipt)
                if error_code is not None:
                    arm_errors.append(error_code)
                    break
            aggregate = _aggregate_usage(arm_usage)
            if aggregate["total_tokens"] > budget[
                "total_token_limit_per_topology"
            ]:
                arm_errors.append("TOPOLOGY_TOKEN_BUDGET_EXCEEDED")
            usage_receipt = self_digest(
                {
                    "schema_id": "topology_usage_receipt",
                    "schema_version": "1.0.0",
                    "paired_session_id": request.paired_session_id,
                    "topology_id": topology_id,
                    "model_calls": len(turn_receipts),
                    "retry_count": sum(
                        item["retry_count"] for item in turn_receipts
                    ),
                    "tokens": aggregate,
                    "latency_ms": sum(
                        item["latency_ms"] for item in turn_receipts
                    ),
                    "cost_microunits": None,
                    "cost_status": "UNKNOWN_NOT_EXPOSED_BY_CODEX_JSONL",
                    "timeout_count": sum(
                        item["error_code"] == "CODEX_EXEC_TIMEOUT"
                        for item in turn_receipts
                    ),
                    "missing_role_count": max(
                        0,
                        topology_contract["calls_per_topology_limit"]
                        - len(turn_receipts),
                    ),
                },
                "receipt_digest",
            )
            archive.write_json(
                f"arms/{topology_id}/usage-receipt.json",
                usage_receipt,
            )
            arm_receipt = {
                "topology_id": topology_id,
                "status": (
                    "COMPLETE"
                    if (
                        len(turn_receipts)
                        == topology_contract["calls_per_topology_limit"]
                        and not arm_errors
                    )
                    else "INCOMPLETE"
                ),
                "requested_model": topology_contract["model"],
                "served_model_attestation": None,
                "served_model_attestation_status": (
                    "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT"
                ),
                "model_configuration_digest": model_configuration_digest,
                "budget_limit_digest": budget_limit_digest,
                "common_context_digest": common_digest,
                "raw_input_ref": _archive_artifact_ref(
                    archive,
                    "shared/byte-identical-common-context.json",
                    common_digest,
                ),
                "raw_output_refs": [
                    item["raw_output_ref"]
                    for item in turn_receipts
                    if item["raw_output_ref"] is not None
                ],
                "calls_attempted": len(turn_receipts),
                "retry_count": sum(
                    item["retry_count"] for item in turn_receipts
                ),
                "usage": aggregate,
                "usage_receipt_digest": usage_receipt["receipt_digest"],
                "latency_ms": usage_receipt["latency_ms"],
                "cost_microunits": None,
                "cost_status": usage_receipt["cost_status"],
                "timeout_count": usage_receipt["timeout_count"],
                "missing_role_count": usage_receipt[
                    "missing_role_count"
                ],
                "turn_receipts": turn_receipts,
                "error_codes": list(dict.fromkeys(arm_errors)),
            }
            arm_receipt = self_digest(arm_receipt, "receipt_digest")
            archive.write_json(
                f"arms/{topology_id}/arm-receipt.json", arm_receipt
            )
            arm_receipts.append(arm_receipt)

    run_reasons = [*admission_reasons, *blocking_reasons]
    for arm in arm_receipts:
        run_reasons.extend(arm["error_codes"])
    completed_at = clock()
    if completed_at.tzinfo is None:
        raise GenerativeTopologyRunError("RUN_CLOCK_NAIVE")
    receipt = _terminal_receipt(
        request=request,
        archive=archive,
        contract_digest=contract_digest,
        capability=capability,
        common_context_digest=common_digest,
        model_configuration_digest=model_configuration_digest,
        budget_limit_digest=budget_limit_digest,
        arm_receipts=arm_receipts,
        reason_codes=run_reasons,
        started_at=started_at,
        completed_at=completed_at,
    )
    archive.write_json("paired-run-receipt.json", receipt)
    return receipt


def admit_formal_generation_receipt(
    receipt: Mapping[str, Any],
) -> Mapping[str, Any]:
    verify_self_digest(receipt, "receipt_digest")
    if (
        receipt.get("schema_id")
        != "paired_generative_topology_run_receipt"
        or receipt.get("formal_evidence") is not True
        or receipt.get("formal_observation_eligible") is not True
        or receipt.get("evidence_class")
        != RunEvidenceClass.FORMAL_GENERATIVE.value
        or receipt.get("reason_codes") != []
    ):
        raise GenerativeTopologyRunError(
            "NON_FORMAL_GENERATION_RECEIPT_NOT_ADMISSIBLE"
        )
    return receipt


@dataclass(frozen=True, slots=True)
class FormalObservationScores:
    sample_index: int
    sample_cohort: str
    qualification_verdict: str
    dynamic_candidate_coverage: Decimal
    material_challenge_coverage: Decimal
    action_quality_score: Decimal
    safety_state_pit_authority_failures: int
    role_overreach_failures: int
    hard_constraint_error_count: int
    state_continuity_error_count: int
    reproducibility_difference_count: int
    net_pnl_after_cost: Decimal | None = None
    transaction_cost: Decimal | None = None
    max_drawdown_fraction: Decimal | None = None
    primary_path_capture: Decimal | None = None
    frozen_baseline_net_pnl_after_cost: Decimal | None = None
    frozen_baseline_max_drawdown_fraction: Decimal | None = None
    frozen_baseline_primary_path_capture: Decimal | None = None


def build_paired_observation_from_generation(
    *,
    generation_receipt: Mapping[str, Any],
    topology_id: str,
    scores: FormalObservationScores,
    scoring_policy_digest: str,
    cost_policy_digest: str,
    initial_account_digest: str,
    termination_policy_digest: str,
):
    """Adapt one complete arm only after independent deterministic scoring."""

    admit_formal_generation_receipt(generation_receipt)
    arms = {
        item["topology_id"]: item
        for item in generation_receipt["arm_receipts"]
    }
    arm = arms.get(topology_id)
    if arm is None or arm.get("status") != "COMPLETE":
        raise GenerativeTopologyRunError(
            "FORMAL_GENERATIVE_ARM_INCOMPLETE"
        )
    if (
        scores.sample_cohort != generation_receipt["sample_cohort"]
        or scores.sample_index != generation_receipt["sample_index"]
    ):
        raise GenerativeTopologyRunError(
            "GENERATION_SCORE_SAMPLE_BINDING_MISMATCH"
        )
    from .formal_experiment import build_paired_observation_receipt

    return build_paired_observation_receipt(
        session_id=generation_receipt["paired_session_id"],
        topology_id=topology_id,
        input_digest=generation_receipt["common_context_digest"],
        model_class=generation_receipt["requested_model"],
        total_budget_digest=generation_receipt["budget_limit_digest"],
        dynamic_candidate_coverage=scores.dynamic_candidate_coverage,
        material_challenge_coverage=(
            scores.material_challenge_coverage
        ),
        action_quality_score=scores.action_quality_score,
        safety_state_pit_authority_failures=(
            scores.safety_state_pit_authority_failures
        ),
        role_overreach_failures=scores.role_overreach_failures,
        model_calls=arm["calls_attempted"],
        tokens=arm["usage"]["total_tokens"],
        latency_ms=arm["latency_ms"],
        cost_microunits=None,
        timeout_count=arm["timeout_count"],
        missing_role_count=arm["missing_role_count"],
        sample_index=scores.sample_index,
        sample_cohort=scores.sample_cohort,
        qualification_verdict=scores.qualification_verdict,
        formal_evidence=True,
        requested_model=generation_receipt["requested_model"],
        served_model_attestation=None,
        served_model_attestation_status=(
            "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT"
        ),
        parameter_digest=generation_receipt[
            "model_configuration_digest"
        ],
        budget_limit_digest=generation_receipt[
            "budget_limit_digest"
        ],
        transport_contract_verdict="PASS",
        transport_schema_digest=canonical_digest(
            ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
        ),
        dataset_digest=generation_receipt["dataset_digest"],
        formal_contract_digest=generation_receipt[
            "formal_contract_digest"
        ],
        scoring_policy_digest=scoring_policy_digest,
        cost_policy_digest=cost_policy_digest,
        initial_account_digest=initial_account_digest,
        termination_policy_digest=termination_policy_digest,
        raw_input_ref=arm["raw_input_ref"],
        raw_output_refs=tuple(arm["raw_output_refs"]),
        usage_receipt_digest=arm["usage_receipt_digest"],
        hard_constraint_error_count=(
            scores.hard_constraint_error_count
        ),
        state_continuity_error_count=(
            scores.state_continuity_error_count
        ),
        reproducibility_difference_count=(
            scores.reproducibility_difference_count
        ),
        net_pnl_after_cost=scores.net_pnl_after_cost,
        transaction_cost=scores.transaction_cost,
        max_drawdown_fraction=scores.max_drawdown_fraction,
        primary_path_capture=scores.primary_path_capture,
        frozen_baseline_net_pnl_after_cost=(
            scores.frozen_baseline_net_pnl_after_cost
        ),
        frozen_baseline_max_drawdown_fraction=(
            scores.frozen_baseline_max_drawdown_fraction
        ),
        frozen_baseline_primary_path_capture=(
            scores.frozen_baseline_primary_path_capture
        ),
    )


__all__ = [
    "FORMAL_CONTRACT_DIGEST",
    "FORMAL_CONTRACT_ID",
    "FORMAL_TOPOLOGY_IDS",
    "FormalObservationScores",
    "FrozenInstruction",
    "GenerativeModelPort",
    "GenerativeTopologyRunError",
    "LEGACY_ROLE_INPUT_SCHEMA_CANONICAL_DIGEST",
    "ModelAttemptResult",
    "ModelAttemptStatus",
    "ModelCallRequest",
    "ModelTransportCapability",
    "PairedGenerativeRunRequest",
    "PairedRunArchivePort",
    "ProjectionValue",
    "ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA",
    "ROLE_INPUT_TRANSPORT_VERSION",
    "RunEvidenceClass",
    "SEMANTIC_MODEL_OUTPUT_SCHEMA",
    "UsageRecord",
    "admit_formal_generation_receipt",
    "build_paired_observation_from_generation",
    "build_resolved_role_input_document",
    "make_deterministic_object_ref",
    "role_input_transport_repair_receipt",
    "run_paired_generative_topologies",
    "validate_formal_experiment_contract",
    "wrap_semantic_model_output",
]
