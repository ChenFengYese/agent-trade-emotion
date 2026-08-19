"""Pure V3.1.1 contracts for direct Agent context and durable consumption.

The historical V3.1 authoring packet and transport remain immutable.  These
documents add a versioned, write-once layer that makes the complete successor
context directly deliverable to the current root Codex and later cross-binds
that context to the single durable proposal delivery.  They prove only direct
input selection and durable delivery, never attention, cognition, prediction,
profitability, or execution authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Mapping

from .contracts.canonical import canonical_digest, self_digest, verify_self_digest
from .v31_agent_transport import (
    V31_AGENT_ID,
    validate_v31_agent_attempt,
    validate_v31_agent_claim,
    validate_v31_agent_delivery,
    validate_v31_agent_request,
    validate_v31_consume_receipt,
    validate_v31_transport_evidence,
)
from .v31_cycle_authoring import (
    AUTHORING_ENVELOPE_DIGEST_FIELD,
    AUTHORING_PACKET_DIGEST_FIELD,
    AUTHORING_PACKET_SCHEMA_ID,
    validate_v31_agent_open_analysis_envelope,
    validate_v31_proposal_authoring_packet,
)
from .v31_successor_cycle_commit_v2 import (
    DIGEST_FIELD as BASE_COMMIT_DIGEST_FIELD,
    SCHEMA_ID as BASE_COMMIT_SCHEMA_ID,
    verify_v31_successor_cycle_commit_material_v2,
)


class V311AgentLifecycleV1Error(ValueError):
    """A direct-input or durable-consumption lifecycle binding drifted."""


AGENT_INPUT_CONTEXT_SCHEMA_ID = "theory_paper_v311_agent_input_context_v1"
AGENT_INPUT_CONTEXT_SCHEMA_VERSION = "1.0.0"
AGENT_INPUT_CONTEXT_DIGEST_FIELD = "agent_input_context_digest"

AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID = (
    "theory_paper_v311_agent_context_consumption_v1"
)
AGENT_CONTEXT_CONSUMPTION_SCHEMA_VERSION = "1.0.0"
AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD = "agent_context_consumption_digest"

V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID = (
    "theory_paper_v311_successor_cycle_commit_envelope_v1"
)
V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_VERSION = "1.0.0"
V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD = (
    "successor_commit_envelope_digest"
)

THEORY_ADDENDUM_SEMANTIC_DOCUMENT_SCHEMA_ID = (
    "theory_paper_v311_theory_addendum_semantic_document_v1"
)
THEORY_ADDENDUM_SEMANTIC_DOCUMENT_SCHEMA_VERSION = "1.0.0"
THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD = (
    "theory_addendum_semantic_document_digest"
)

V311_AGENT_CONTEXT_ROOT = "successor-v311-agent-context"
V311_CURRENT_ROOT_DELIVERY_ORIGIN = (
    "CURRENT_ROOT_CODEX_DIRECT_AGENT_INPUT_CONTEXT"
)
V311_DIRECT_INPUT_CLAIM = (
    "DIRECT_INPUT_AND_DURABLE_DELIVERY_ONLY_NOT_COGNITIVE_PROOF"
)
V311_TARGET_CONTEXT_PROFILE = "V311_TARGET_FORMAL_CYCLE"
V311_QUALIFICATION_CONTEXT_PROFILE = "V311_QUALIFICATION_PRE_AGENT"

V311_TARGET_AGENT_SUPPORT_KEYS = frozenset(
    {
        "application_authority_projection",
        "theory_addendum",
        "clock_policy",
        "supervisor_policy",
        "runtime_closure",
        "successor_authority_envelope",
        "sentiment_source_registry",
        "sentiment_projection",
        "association_preregistration",
        "evaluation_contract",
        "fresh_qualification_bundle",
        "qualification_public_source",
        "qualification_codex_durable_delivery",
        "qualification_outcome_monitor",
    }
)
V311_QUALIFICATION_AGENT_SUPPORT_KEYS = frozenset(
    {
        "clock_policy",
        "theory_addendum",
        "supervisor_policy",
        "runtime_closure",
        "sentiment_source_registry",
        "sentiment_projection",
        "association_preregistration",
        "evaluation_contract",
        "public_source_qualification",
        "outcome_monitor_qualification",
        "schema_compatibility",
    }
)

# Every named support is a typed protocol slot, not a free-form self-digested
# attachment.  Keep these maps versioned with the context profile: a future
# theory version must define a new profile/map rather than silently accepting a
# differently typed document under an old name.
V311_TARGET_AGENT_SUPPORT_SPECS = MappingProxyType(
    {
        "application_authority_projection": (
            "theory_paper_v31_run_genesis",
            "run_genesis_digest",
        ),
        "theory_addendum": (
            THEORY_ADDENDUM_SEMANTIC_DOCUMENT_SCHEMA_ID,
            THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD,
        ),
        "clock_policy": (
            "theory_paper_v31_outcome_clock_policy_v2",
            "clock_policy_digest",
        ),
        "supervisor_policy": (
            "theory_paper_v311_successor_supervisor_policy_v2",
            "supervisor_policy_digest",
        ),
        "runtime_closure": (
            "theory_paper_v311_successor_runtime_closure_receipt_v2",
            "runtime_closure_receipt_digest",
        ),
        "successor_authority_envelope": (
            "theory_paper_v311_successor_authority_envelope_v2",
            "successor_authority_envelope_digest",
        ),
        "sentiment_source_registry": (
            "theory_paper_v2_v31_native_sentiment_source_registry",
            "registry_digest",
        ),
        "sentiment_projection": (
            "theory_paper_v2_v31_sentiment_native_projection_receipt",
            "projection_receipt_digest",
        ),
        "association_preregistration": (
            "theory_paper_v2_v31_association_preregistration_v2",
            "association_preregistration_digest",
        ),
        "evaluation_contract": (
            "theory_paper_v2_v31_evaluation_contract_v2",
            "evaluation_contract_digest",
        ),
        "fresh_qualification_bundle": (
            "theory_paper_v311_run_local_fresh_qualification_bundle_v1",
            "fresh_qualification_bundle_digest",
        ),
        "qualification_public_source": (
            "theory_paper_v31_successor_public_source_qualification_v2",
            "source_qualification_v2_digest",
        ),
        "qualification_codex_durable_delivery": (
            "theory_paper_v311_codex_durable_delivery_qualification_v3",
            "codex_qualification_v3_digest",
        ),
        "qualification_outcome_monitor": (
            "theory_paper_v31_successor_outcome_monitor_qualification_v2",
            "monitor_qualification_v2_digest",
        ),
    }
)
V311_QUALIFICATION_AGENT_SUPPORT_SPECS = MappingProxyType(
    {
        "clock_policy": V311_TARGET_AGENT_SUPPORT_SPECS["clock_policy"],
        "theory_addendum": V311_TARGET_AGENT_SUPPORT_SPECS["theory_addendum"],
        "supervisor_policy": V311_TARGET_AGENT_SUPPORT_SPECS[
            "supervisor_policy"
        ],
        "runtime_closure": V311_TARGET_AGENT_SUPPORT_SPECS[
            "runtime_closure"
        ],
        "sentiment_source_registry": V311_TARGET_AGENT_SUPPORT_SPECS[
            "sentiment_source_registry"
        ],
        "sentiment_projection": V311_TARGET_AGENT_SUPPORT_SPECS[
            "sentiment_projection"
        ],
        "association_preregistration": V311_TARGET_AGENT_SUPPORT_SPECS[
            "association_preregistration"
        ],
        "evaluation_contract": V311_TARGET_AGENT_SUPPORT_SPECS[
            "evaluation_contract"
        ],
        "public_source_qualification": (
            "theory_paper_v31_successor_public_source_qualification_v2",
            "source_qualification_v2_digest",
        ),
        "outcome_monitor_qualification": (
            "theory_paper_v31_successor_outcome_monitor_qualification_v2",
            "monitor_qualification_v2_digest",
        ),
        "schema_compatibility": (
            "theory_paper_v311_official_outcome_schema_compatibility_v3",
            "schema_compatibility_receipt_digest",
        ),
    }
)

_PROFILE_SUPPORT_SPECS = MappingProxyType(
    {
        V311_TARGET_CONTEXT_PROFILE: V311_TARGET_AGENT_SUPPORT_SPECS,
        V311_QUALIFICATION_CONTEXT_PROFILE: (
            V311_QUALIFICATION_AGENT_SUPPORT_SPECS
        ),
    }
)
_PROFILE_PURPOSE = {
    V311_TARGET_CONTEXT_PROFILE: "AUTHORIZED_RESEARCH_CYCLE",
    V311_QUALIFICATION_CONTEXT_PROFILE: "AUTHORIZED_RESEARCH_CYCLE",
}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_ADDENDUM_BINDING_FIELDS = frozenset(
    {"path", "version", "review_status", "physical_sha256"}
)
_ADDENDUM_DOCUMENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "path",
        "version",
        "review_status",
        "physical_sha256",
        "content_encoding",
        "markdown_utf8",
        "source_binding",
        "semantic_role",
        "claim",
        THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD,
    }
)
_LIMITATIONS = [
    "DIRECT_INPUT_ARTIFACT_DOES_NOT_PROVE_ATTENTION_OR_COGNITION",
    "DURABLE_DELIVERY_DOES_NOT_PROVE_FORECAST_VALIDITY_OR_PROFITABILITY",
    "SERVICE_MODEL_IDENTITY_AND_EXACT_TOKEN_BUDGET_ARE_NOT_MACHINE_ATTESTED",
]
_INPUT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "context_profile",
        "created_at",
        "agent_id",
        "delivery_origin",
        "delivery_purpose",
        "base_authoring_packet_digest",
        "base_authoring_packet_binding",
        "current_authority_digest",
        "current_authority_binding",
        "theory_addendum_binding",
        "support_documents",
        "support_bindings",
        "support_bindings_digest",
        "direct_context_input_required",
        "controller_must_pass_document_unchanged",
        "private_chain_of_thought_requested",
        "claim",
        "limitations",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    }
)
_CONSUMPTION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "consumed_at",
        "agent_id",
        "delivery_origin",
        "delivery_purpose",
        "agent_input_context_digest",
        "agent_input_context_binding",
        "base_authoring_packet_digest",
        "proposal_attempt_digest",
        "proposal_attempt_binding",
        "proposal_request_digest",
        "proposal_request_binding",
        "proposal_delivery_digest",
        "proposal_delivery_binding",
        "proposal_consume_digest",
        "proposal_consume_binding",
        "agent_authoring_envelope_digest",
        "agent_authoring_envelope",
        "transport_evidence_digest",
        "transport_evidence_binding",
        "proposal_attempt_count",
        "proposal_max_attempts",
        "proposal_retry_count",
        "direct_context_input_declared_by_controller",
        "durable_delivery_verified",
        "single_attempt_verified",
        "current_root_role_contract_verified",
        "transport_attestation_level",
        "claim",
        "limitations",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    }
)
_COMMIT_ENVELOPE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "sealed_at",
        "base_successor_commit_material_digest",
        "base_successor_commit_material_binding",
        "agent_input_context_digest",
        "agent_input_context_binding",
        "agent_context_consumption_digest",
        "agent_context_consumption_binding",
        "base_authoring_packet_digest",
        "transport_evidence_digest",
        "accepted_state_digest",
        "base_support_bindings_digest",
        "agent_lifecycle_bindings_required",
        "recovery_policy",
        "claim",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    }
)
_SENTIMENT_PROJECTION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "adapter_id",
        "projection_id",
        "run_id",
        "cycle_index",
        "instrument_id",
        "decision_at",
        "cycle_source_admission_binding",
        "pit_dataset_binding",
        "information_revision_registry_binding",
        "previous_context_verification",
        "native_source_registry",
        "native_source_registry_digest",
        "information_datum_binding_materials",
        "derived_evidence_materials",
        "excluded_candidates",
        "projection",
        "projection_digest",
        "source_observation_count",
        "axis_count",
        "missing_is_zero",
        "public_data_only",
        "external_execution_authority",
        "executable",
        "claim_boundaries",
        "projection_receipt_digest",
    }
)
_SUCCESSOR_ENVELOPE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "envelope_id",
        "created_at",
        "status",
        "qualification_run_id",
        "qualification_run_root_ref",
        "target_run_id",
        "predecessor_failure_lineage",
        "qualification_v3_authority",
        "target_v4_authority",
        "theory_addendum_binding",
        "successor_user_approval_binding",
        "successor_user_approval_digest",
        "auxiliary_contract_bindings",
        "fresh_qualification_bindings",
        "fresh_qualification_digests",
        "qualification_retirement_binding",
        "qualification_retirement_digest",
        "immutable_contract",
        "claim_boundary",
        "authority_boundary",
        "successor_authority_envelope_digest",
    }
)
_FRESH_QUALIFICATION_BUNDLE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "successor_authority_envelope_binding",
        "qualification_bindings",
        "qualification_digests",
        "full_successor_loader_required",
        "source_scope",
        "external_execution_authority",
        "executable",
        "fresh_qualification_bundle_digest",
    }
)
_SCHEMA_COMPATIBILITY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "qualification_id",
        "sealed_at",
        "source_qualification_v2_digest",
        "source_qualification_root_ref",
        "clock_policy_digest",
        "source_raw_binding",
        "source_capture_record_digest",
        "source_transport",
        "frozen_parser_projection",
        "capture",
        "parse_receipt",
        "verdict",
        "schema_compatible",
        "outcome_admitted",
        "monitor_resolution_created",
        "historical_source_replay",
        "additional_network_get_count",
        "limitations",
        "authority_boundary",
        "schema_compatibility_receipt_digest",
    }
)


def agent_input_context_ref_v1(cycle_index: int) -> str:
    cycle = _cycle(cycle_index)
    return (
        f"{V311_AGENT_CONTEXT_ROOT}/cycles/{cycle:04d}/"
        "agent-input-context.json"
    )


def agent_context_consumption_ref_v1(cycle_index: int) -> str:
    cycle = _cycle(cycle_index)
    return (
        f"{V311_AGENT_CONTEXT_ROOT}/cycles/{cycle:04d}/"
        "agent-context-consumption.json"
    )


def successor_commit_envelope_ref_v1(cycle_index: int) -> str:
    cycle = _cycle(cycle_index)
    return (
        f"{V311_AGENT_CONTEXT_ROOT}/cycles/{cycle:04d}/"
        "successor-commit-envelope.json"
    )


def _cycle(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 8
    ):
        raise V311AgentLifecycleV1Error("V311_AGENT_LIFECYCLE_CYCLE_INVALID")
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V311AgentLifecycleV1Error(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V311AgentLifecycleV1Error(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311AgentLifecycleV1Error(code) from exc
    if parsed.tzinfo is None:
        raise V311AgentLifecycleV1Error(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V311AgentLifecycleV1Error(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    text = _time(value, code)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _binding(
    value: Any,
    code: str,
    *,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V311AgentLifecycleV1Error(code)
    result = {field: _text(value.get(field), code) for field in _BINDING_FIELDS}
    _digest(result["semantic_digest"], code)
    _digest(result["physical_sha256"], code)
    path = PurePosixPath(result["relative_ref"])
    if (
        "\\" in result["relative_ref"]
        or path.is_absolute()
        or path.as_posix() != result["relative_ref"]
        or any(part in {"", ".", ".."} for part in path.parts)
        or (schema_id is not None and result["schema_id"] != schema_id)
        or (digest_field is not None and result["digest_field"] != digest_field)
    ):
        raise V311AgentLifecycleV1Error(code)
    return result


def _addendum_binding(value: Any) -> dict[str, str]:
    code = "V311_AGENT_INPUT_ADDENDUM_BINDING_INVALID"
    if not isinstance(value, Mapping) or set(value) != _ADDENDUM_BINDING_FIELDS:
        raise V311AgentLifecycleV1Error(code)
    result = {
        field: _text(value.get(field), code)
        for field in _ADDENDUM_BINDING_FIELDS
    }
    _digest(result["physical_sha256"], code)
    path = PurePosixPath(result["path"])
    if path.is_absolute() or path.as_posix() != result["path"] or "\\" in result["path"]:
        raise V311AgentLifecycleV1Error(code)
    return result


def build_v311_theory_addendum_semantic_document_v1(
    *,
    theory_addendum_binding: Mapping[str, Any],
    markdown_utf8: str,
) -> dict[str, Any]:
    """Wrap the exact frozen UTF-8 addendum bytes as a typed Agent input."""

    binding = _addendum_binding(theory_addendum_binding)
    if not isinstance(markdown_utf8, str) or not markdown_utf8:
        raise V311AgentLifecycleV1Error(
            "V311_ADDENDUM_SEMANTIC_TEXT_INVALID"
        )
    try:
        payload = markdown_utf8.encode("utf-8", errors="strict")
    except UnicodeError as exc:  # pragma: no cover - str normally encodes
        raise V311AgentLifecycleV1Error(
            "V311_ADDENDUM_SEMANTIC_TEXT_INVALID"
        ) from exc
    if hashlib.sha256(payload).hexdigest() != binding["physical_sha256"]:
        raise V311AgentLifecycleV1Error(
            "V311_ADDENDUM_SEMANTIC_PHYSICAL_MISMATCH"
        )
    return self_digest(
        {
            "schema_id": THEORY_ADDENDUM_SEMANTIC_DOCUMENT_SCHEMA_ID,
            "schema_version": THEORY_ADDENDUM_SEMANTIC_DOCUMENT_SCHEMA_VERSION,
            "path": binding["path"],
            "version": binding["version"],
            "review_status": binding["review_status"],
            "physical_sha256": binding["physical_sha256"],
            "content_encoding": "UTF-8",
            "markdown_utf8": markdown_utf8,
            "source_binding": binding,
            "semantic_role": "COMPLETE_FROZEN_THEORY_ADDENDUM_DIRECT_AGENT_INPUT",
            "claim": "EXACT_UTF8_CONTENT_AND_PHYSICAL_SHA256_ONLY",
        },
        THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD,
    )


def verify_v311_theory_addendum_semantic_document_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _ADDENDUM_DOCUMENT_FIELDS:
        raise V311AgentLifecycleV1Error(
            "V311_ADDENDUM_SEMANTIC_DOCUMENT_INVALID"
        )
    supplied = verify_self_digest(
        document, THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD
    )
    rebuilt = build_v311_theory_addendum_semantic_document_v1(
        theory_addendum_binding=document["source_binding"],
        markdown_utf8=document["markdown_utf8"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[
        THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD
    ]:
        raise V311AgentLifecycleV1Error(
            "V311_ADDENDUM_SEMANTIC_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _verify_typed_support_document(
    *,
    name: str,
    document: Mapping[str, Any],
    support_documents: Mapping[str, Mapping[str, Any]],
) -> str:
    """Use each support contract's reconstructor, never schema text alone."""

    if name == "theory_addendum":
        return verify_v311_theory_addendum_semantic_document_v1(document)
    if name == "clock_policy":
        from .v31_outcome_capture_v2 import verify_outcome_clock_policy

        return verify_outcome_clock_policy(document)
    if name in {"supervisor_policy", "runtime_closure"}:
        # Lazy to avoid the authority-envelope -> codex-v3 -> lifecycle import
        # cycle while still using the authoritative pure reconstructors.
        from .governance.v311_successor_authority_envelope_v2 import (
            verify_v311_runtime_closure_receipt_v2,
            verify_v311_supervisor_policy_v2,
        )

        return (
            verify_v311_supervisor_policy_v2(document)
            if name == "supervisor_policy"
            else verify_v311_runtime_closure_receipt_v2(document)
        )
    if name == "sentiment_source_registry":
        from .v31_sentiment_native_projection_v2 import (
            verify_v31_native_sentiment_source_registry,
        )

        return verify_v31_native_sentiment_source_registry(document)
    if name == "sentiment_projection":
        from .v31_sentiment_native_projection_v2 import (
            verify_v31_native_sentiment_projection,
            verify_v31_native_sentiment_source_registry,
        )

        if set(document) != _SENTIMENT_PROJECTION_RECEIPT_FIELDS:
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SENTIMENT_RECEIPT_INVALID"
            )
        supplied = verify_self_digest(document, "projection_receipt_digest")
        registry = document.get("native_source_registry")
        projection = document.get("projection")
        registry_digest = verify_v31_native_sentiment_source_registry(registry)
        projection_digest = verify_v31_native_sentiment_projection(
            projection, registry=registry
        )
        if (
            registry != support_documents.get("sentiment_source_registry")
            or document.get("native_source_registry_digest")
            != registry_digest
            or document.get("projection_digest") != projection_digest
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SENTIMENT_RECEIPT_INVALID"
            )
        return supplied
    if name == "association_preregistration":
        from .v31_association_preregistration_v2 import (
            verify_v31_association_preregistration_v2,
        )

        return verify_v31_association_preregistration_v2(document)
    if name == "evaluation_contract":
        from .v31_evaluation_contract_v2 import (
            verify_v31_evaluation_contract_v2,
        )

        return verify_v31_evaluation_contract_v2(
            document, support_documents["association_preregistration"]
        )
    if name in {
        "public_source_qualification",
        "qualification_public_source",
    }:
        from .governance.v31_successor_qualification_v2 import (
            verify_successor_public_source_qualification_v2,
        )

        return verify_successor_public_source_qualification_v2(document)
    if name in {
        "outcome_monitor_qualification",
        "qualification_outcome_monitor",
    }:
        from .governance.v31_successor_qualification_v2 import (
            verify_successor_monitor_qualification_v2,
        )

        return verify_successor_monitor_qualification_v2(document)
    if name == "qualification_codex_durable_delivery":
        from .governance.v311_codex_durable_qualification_v3 import (
            verify_successor_codex_durable_qualification_v3,
        )

        return verify_successor_codex_durable_qualification_v3(document)
    if name == "application_authority_projection":
        from .v31_run_genesis import _RUN_GENESIS_FIELDS

        supplied = verify_self_digest(document, "run_genesis_digest")
        if (
            set(document) != _RUN_GENESIS_FIELDS
            or document.get("schema_version") != "1.0.0"
            or document.get("operation") != "INITIALIZE_NEW_V31_RUN_ONLY"
            or document.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or document.get("executable") is not False
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_RUN_GENESIS_INVALID"
            )
        return supplied
    if name == "successor_authority_envelope":
        supplied = verify_self_digest(
            document, "successor_authority_envelope_digest"
        )
        if (
            set(document) != _SUCCESSOR_ENVELOPE_FIELDS
            or document.get("schema_version") != "2.0.0"
            or document.get("status") != "ACTIVE_FROZEN_RESEARCH_SUCCESSOR"
            or document.get("authority_boundary", {}).get("executable")
            is not False
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SUCCESSOR_ENVELOPE_INVALID"
            )
        return supplied
    if name == "fresh_qualification_bundle":
        supplied = verify_self_digest(
            document, "fresh_qualification_bundle_digest"
        )
        if (
            set(document) != _FRESH_QUALIFICATION_BUNDLE_FIELDS
            or document.get("schema_version") != "1.0.0"
            or document.get("full_successor_loader_required") is not True
            or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
            or document.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or document.get("executable") is not False
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_QUALIFICATION_BUNDLE_INVALID"
            )
        return supplied
    if name == "schema_compatibility":
        supplied = verify_self_digest(
            document, "schema_compatibility_receipt_digest"
        )
        if (
            set(document) != _SCHEMA_COMPATIBILITY_FIELDS
            or document.get("schema_version") != "3.0.0"
            or document.get("source_qualification_v2_digest")
            != support_documents["public_source_qualification"].get(
                "source_qualification_v2_digest"
            )
            or document.get("clock_policy_digest")
            != support_documents["clock_policy"].get("clock_policy_digest")
            or document.get("schema_compatible") is not True
            or document.get("outcome_admitted") is not False
            or document.get("monitor_resolution_created") is not False
            or document.get("historical_source_replay") is not True
            or document.get("additional_network_get_count") != 0
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SCHEMA_COMPATIBILITY_INVALID"
            )
        return supplied
    raise V311AgentLifecycleV1Error(
        "V311_AGENT_INPUT_SUPPORT_TYPED_VERIFIER_MISSING"
    )


def _verify_support_cross_bindings(
    *,
    context_profile: str,
    documents: Mapping[str, Mapping[str, Any]],
    bindings: Mapping[str, Mapping[str, Any]],
) -> None:
    if context_profile != V311_TARGET_CONTEXT_PROFILE:
        return
    envelope = documents["successor_authority_envelope"]
    auxiliary = envelope.get("auxiliary_contract_bindings")
    qualifications = envelope.get("fresh_qualification_bindings")
    bundle = documents["fresh_qualification_bundle"]
    if (
        envelope.get("theory_addendum_binding")
        != documents["theory_addendum"].get("source_binding")
        or not isinstance(auxiliary, Mapping)
        or not isinstance(qualifications, Mapping)
        or bundle.get("successor_authority_envelope_binding")
        != bindings["successor_authority_envelope"]
    ):
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_INPUT_SUPPORT_CROSS_BINDING_INVALID"
        )
    for name in (
        "clock_policy",
        "supervisor_policy",
        "runtime_closure",
        "sentiment_source_registry",
        "association_preregistration",
        "evaluation_contract",
    ):
        value = auxiliary.get(name)
        if not isinstance(value, Mapping) or any(
            value.get(field) != bindings[name].get(field)
            for field in ("schema_id", "digest_field", "semantic_digest")
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SUPPORT_CROSS_BINDING_INVALID"
            )
    names = {
        "public_source": "qualification_public_source",
        "codex_durable_delivery": "qualification_codex_durable_delivery",
        "outcome_monitor": "qualification_outcome_monitor",
    }
    bundle_bindings = bundle.get("qualification_bindings")
    if not isinstance(bundle_bindings, Mapping):
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_INPUT_SUPPORT_CROSS_BINDING_INVALID"
        )
    for envelope_name, context_name in names.items():
        value = qualifications.get(envelope_name)
        if (
            not isinstance(value, Mapping)
            or any(
                value.get(field) != bindings[context_name].get(field)
                for field in ("schema_id", "digest_field", "semantic_digest")
            )
            or bundle_bindings.get(envelope_name) != bindings[context_name]
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SUPPORT_CROSS_BINDING_INVALID"
            )


def _support(
    *,
    context_profile: str,
    support_documents: Mapping[str, Mapping[str, Any]],
    support_bindings: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    expected_specs = _PROFILE_SUPPORT_SPECS.get(context_profile)
    expected = None if expected_specs is None else frozenset(expected_specs)
    if (
        expected is None
        or not isinstance(support_documents, Mapping)
        or set(support_documents) != expected
        or not isinstance(support_bindings, Mapping)
        or set(support_bindings) != expected
    ):
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_INPUT_SUPPORT_SET_INVALID"
        )
    documents: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, str]] = {}
    for name in sorted(expected):
        schema_id, digest_field = expected_specs[name]
        document = support_documents[name]
        if not isinstance(document, Mapping):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SUPPORT_DOCUMENT_INVALID"
            )
        binding = _binding(
            support_bindings[name],
            "V311_AGENT_INPUT_SUPPORT_BINDING_INVALID",
            schema_id=schema_id,
            digest_field=digest_field,
        )
        try:
            semantic = _verify_typed_support_document(
                name=name,
                document=document,
                support_documents=support_documents,
            )
        except V311AgentLifecycleV1Error:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SUPPORT_DOCUMENT_INVALID"
            ) from exc
        if (
            document.get("schema_id") != schema_id
            or semantic != binding["semantic_digest"]
        ):
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_SUPPORT_BINDING_INVALID"
            )
        documents[name] = dict(document)
        bindings[name] = binding
    _verify_support_cross_bindings(
        context_profile=context_profile,
        documents=documents,
        bindings=bindings,
    )
    return documents, bindings


def build_v311_agent_input_context_v1(
    *,
    run_id: str,
    cycle_index: int,
    context_profile: str,
    created_at: str,
    base_authoring_packet: Mapping[str, Any],
    base_authoring_packet_binding: Mapping[str, Any],
    current_authority_binding: Mapping[str, Any],
    theory_addendum_binding: Mapping[str, Any],
    support_documents: Mapping[str, Mapping[str, Any]],
    support_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal the complete document the controller must pass to root Codex."""

    run = _text(run_id, "V311_AGENT_INPUT_RUN_ID_INVALID")
    cycle = _cycle(cycle_index)
    created = _time(created_at, "V311_AGENT_INPUT_TIME_INVALID")
    try:
        packet_digest = validate_v31_proposal_authoring_packet(
            base_authoring_packet
        )
    except (TypeError, ValueError) as exc:
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_INPUT_BASE_PACKET_INVALID"
        ) from exc
    packet_binding = _binding(
        base_authoring_packet_binding,
        "V311_AGENT_INPUT_BASE_PACKET_BINDING_INVALID",
        schema_id=AUTHORING_PACKET_SCHEMA_ID,
        digest_field=AUTHORING_PACKET_DIGEST_FIELD,
    )
    authority_binding = _binding(
        current_authority_binding,
        "V311_AGENT_INPUT_AUTHORITY_BINDING_INVALID",
        schema_id="theory_paper_v31_current_research_authority",
        digest_field="authority_digest",
    )
    documents, bindings = _support(
        context_profile=context_profile,
        support_documents=support_documents,
        support_bindings=support_bindings,
    )
    purpose = _PROFILE_PURPOSE.get(context_profile)
    addendum_binding = _addendum_binding(theory_addendum_binding)
    if (
        purpose is None
        or
        base_authoring_packet.get("run_id") != run
        or base_authoring_packet.get("cycle_index") != cycle
        or base_authoring_packet.get("authoring_purpose") != purpose
        or packet_binding["semantic_digest"] != packet_digest
        or base_authoring_packet.get("authority_context", {}).get(
            "active_authority_binding"
        )
        != authority_binding
        or documents["theory_addendum"].get("source_binding")
        != addendum_binding
    ):
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_INPUT_IDENTITY_INVALID"
        )
    document = {
        "schema_id": AGENT_INPUT_CONTEXT_SCHEMA_ID,
        "schema_version": AGENT_INPUT_CONTEXT_SCHEMA_VERSION,
        "run_id": run,
        "cycle_index": cycle,
        "context_profile": context_profile,
        "created_at": created,
        "agent_id": V31_AGENT_ID,
        "delivery_origin": V311_CURRENT_ROOT_DELIVERY_ORIGIN,
        "delivery_purpose": purpose,
        "base_authoring_packet_digest": packet_digest,
        "base_authoring_packet_binding": packet_binding,
        "current_authority_digest": authority_binding["semantic_digest"],
        "current_authority_binding": authority_binding,
        "theory_addendum_binding": addendum_binding,
        "support_documents": documents,
        "support_bindings": bindings,
        "support_bindings_digest": canonical_digest(bindings),
        "direct_context_input_required": True,
        "controller_must_pass_document_unchanged": True,
        "private_chain_of_thought_requested": False,
        "claim": V311_DIRECT_INPUT_CLAIM,
        "limitations": list(_LIMITATIONS),
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, AGENT_INPUT_CONTEXT_DIGEST_FIELD)


def verify_v311_agent_input_context_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _INPUT_FIELDS:
        raise V311AgentLifecycleV1Error("V311_AGENT_INPUT_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, AGENT_INPUT_CONTEXT_DIGEST_FIELD)
        rebuilt = build_v311_agent_input_context_v1(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            context_profile=document["context_profile"],
            created_at=document["created_at"],
            base_authoring_packet=document["support_documents"].get(
                "__forbidden_base_packet__", {}
            ),
            base_authoring_packet_binding=document[
                "base_authoring_packet_binding"
            ],
            current_authority_binding=document["current_authority_binding"],
            theory_addendum_binding=document["theory_addendum_binding"],
            support_documents=document["support_documents"],
            support_bindings=document["support_bindings"],
        )
    except (KeyError, TypeError, ValueError):
        rebuilt = None
    if rebuilt is None:
        # The packet itself is deliberately not duplicated inside this
        # document; verify all remaining canonical fields directly and require
        # callers of the stronger overload below to replay the packet.
        try:
            _text(document["run_id"], "V311_AGENT_INPUT_RUN_ID_INVALID")
            _cycle(document["cycle_index"])
            _time(document["created_at"], "V311_AGENT_INPUT_TIME_INVALID")
            packet_binding = _binding(
                document["base_authoring_packet_binding"],
                "V311_AGENT_INPUT_BASE_PACKET_BINDING_INVALID",
                schema_id=AUTHORING_PACKET_SCHEMA_ID,
                digest_field=AUTHORING_PACKET_DIGEST_FIELD,
            )
            authority_binding = _binding(
                document["current_authority_binding"],
                "V311_AGENT_INPUT_AUTHORITY_BINDING_INVALID",
                schema_id="theory_paper_v31_current_research_authority",
                digest_field="authority_digest",
            )
            documents, bindings = _support(
                context_profile=document["context_profile"],
                support_documents=document["support_documents"],
                support_bindings=document["support_bindings"],
            )
            addendum_binding = _addendum_binding(
                document["theory_addendum_binding"]
            )
            if (
                documents["theory_addendum"].get("source_binding")
                != addendum_binding
            ):
                raise V311AgentLifecycleV1Error(
                    "V311_AGENT_INPUT_ADDENDUM_CROSS_BINDING_INVALID"
                )
        except V311AgentLifecycleV1Error:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_DOCUMENT_INVALID"
            ) from exc
        expected = {
            **{key: document[key] for key in _INPUT_FIELDS if key != AGENT_INPUT_CONTEXT_DIGEST_FIELD},
            "schema_id": AGENT_INPUT_CONTEXT_SCHEMA_ID,
            "schema_version": AGENT_INPUT_CONTEXT_SCHEMA_VERSION,
            "agent_id": V31_AGENT_ID,
            "delivery_origin": V311_CURRENT_ROOT_DELIVERY_ORIGIN,
            "delivery_purpose": _PROFILE_PURPOSE[document["context_profile"]],
            "base_authoring_packet_digest": packet_binding["semantic_digest"],
            "current_authority_digest": authority_binding["semantic_digest"],
            "theory_addendum_binding": addendum_binding,
            "support_documents": documents,
            "support_bindings": bindings,
            "support_bindings_digest": canonical_digest(bindings),
            "direct_context_input_required": True,
            "controller_must_pass_document_unchanged": True,
            "private_chain_of_thought_requested": False,
            "claim": V311_DIRECT_INPUT_CLAIM,
            "limitations": list(_LIMITATIONS),
            "chat_history_is_authority": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
        expected = self_digest(expected, AGENT_INPUT_CONTEXT_DIGEST_FIELD)
        if dict(document) != expected or supplied != expected[AGENT_INPUT_CONTEXT_DIGEST_FIELD]:
            raise V311AgentLifecycleV1Error(
                "V311_AGENT_INPUT_RECONSTRUCTION_MISMATCH"
            )
        return supplied
    raise V311AgentLifecycleV1Error("V311_AGENT_INPUT_DOCUMENT_INVALID")


def verify_v311_agent_input_context_with_packet_v1(
    document: Mapping[str, Any], *, base_authoring_packet: Mapping[str, Any]
) -> str:
    supplied = verify_v311_agent_input_context_v1(document)
    packet_digest = validate_v31_proposal_authoring_packet(base_authoring_packet)
    if (
        base_authoring_packet.get("run_id") != document.get("run_id")
        or base_authoring_packet.get("cycle_index") != document.get("cycle_index")
        or packet_digest != document.get("base_authoring_packet_digest")
        or packet_digest
        != document.get("base_authoring_packet_binding", {}).get(
            "semantic_digest"
        )
        or base_authoring_packet.get("authority_context", {}).get(
            "active_authority_binding"
        )
        != document.get("current_authority_binding")
    ):
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_INPUT_PACKET_CROSS_BINDING_INVALID"
        )
    return supplied


def build_v311_agent_context_consumption_v1(
    *,
    agent_input_context: Mapping[str, Any],
    agent_input_context_binding: Mapping[str, Any],
    base_authoring_packet: Mapping[str, Any],
    proposal_attempt: Mapping[str, Any],
    proposal_attempt_binding: Mapping[str, Any],
    proposal_request: Mapping[str, Any],
    proposal_request_binding: Mapping[str, Any],
    proposal_claim: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_delivery_binding: Mapping[str, Any],
    proposal_consume: Mapping[str, Any],
    proposal_consume_binding: Mapping[str, Any],
    transport_evidence: Mapping[str, Any],
    transport_evidence_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one direct context to the sole durable proposal delivery."""

    context_digest = verify_v311_agent_input_context_with_packet_v1(
        agent_input_context, base_authoring_packet=base_authoring_packet
    )
    context_binding = _binding(
        agent_input_context_binding,
        "V311_AGENT_CONSUMPTION_CONTEXT_BINDING_INVALID",
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    attempt_digest = validate_v31_agent_attempt(proposal_attempt)
    request_digest = validate_v31_agent_request(
        proposal_request, attempt=proposal_attempt
    )
    claim_digest = validate_v31_agent_claim(
        proposal_claim, request=proposal_request, attempt=proposal_attempt
    )
    delivery_digest = validate_v31_agent_delivery(
        proposal_delivery,
        request=proposal_request,
        attempt=proposal_attempt,
        claim=proposal_claim,
        authoring_packet=base_authoring_packet,
    )
    consume_digest = validate_v31_consume_receipt(
        proposal_consume,
        request=proposal_request,
        attempt=proposal_attempt,
        claim=proposal_claim,
        delivery=proposal_delivery,
        authoring_packet=base_authoring_packet,
    )
    evidence_digest = validate_v31_transport_evidence(transport_evidence)
    envelope = proposal_delivery.get("payload")
    if not isinstance(envelope, Mapping):
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_CONSUMPTION_ENVELOPE_INVALID"
        )
    envelope_digest = validate_v31_agent_open_analysis_envelope(
        envelope, authoring_packet=base_authoring_packet
    )
    typed = {
        "proposal_attempt_binding": _binding(
            proposal_attempt_binding,
            "V311_AGENT_CONSUMPTION_TRANSPORT_BINDING_INVALID",
            schema_id="theory_paper_v31_agent_attempt",
            digest_field="attempt_digest",
        ),
        "proposal_request_binding": _binding(
            proposal_request_binding,
            "V311_AGENT_CONSUMPTION_TRANSPORT_BINDING_INVALID",
            schema_id="theory_paper_v31_agent_request",
            digest_field="request_digest",
        ),
        "proposal_delivery_binding": _binding(
            proposal_delivery_binding,
            "V311_AGENT_CONSUMPTION_TRANSPORT_BINDING_INVALID",
            schema_id="theory_paper_v31_agent_delivery",
            digest_field="delivery_digest",
        ),
        "proposal_consume_binding": _binding(
            proposal_consume_binding,
            "V311_AGENT_CONSUMPTION_TRANSPORT_BINDING_INVALID",
            schema_id="theory_paper_v31_agent_consume_receipt",
            digest_field="consume_digest",
        ),
        "transport_evidence_binding": _binding(
            transport_evidence_binding,
            "V311_AGENT_CONSUMPTION_TRANSPORT_BINDING_INVALID",
            schema_id="theory_paper_v31_agent_transport_evidence",
            digest_field="transport_evidence_digest",
        ),
    }
    proposal_evidence = transport_evidence.get("stages", {}).get("PROPOSAL")
    expected_semantics = {
        "proposal_attempt_binding": attempt_digest,
        "proposal_request_binding": request_digest,
        "proposal_delivery_binding": delivery_digest,
        "proposal_consume_binding": consume_digest,
        "transport_evidence_binding": evidence_digest,
    }
    run_id = agent_input_context.get("run_id")
    cycle = agent_input_context.get("cycle_index")
    if (
        context_binding["semantic_digest"] != context_digest
        or any(
            typed[name]["semantic_digest"] != semantic
            for name, semantic in expected_semantics.items()
        )
        or not isinstance(proposal_evidence, Mapping)
        or proposal_evidence.get("attempt_count") != 1
        or any(
            proposal_evidence.get(evidence_field) != typed[typed_field]
            for evidence_field, typed_field in (
                ("attempt_binding", "proposal_attempt_binding"),
                ("request_binding", "proposal_request_binding"),
                ("delivery_binding", "proposal_delivery_binding"),
                ("consume_binding", "proposal_consume_binding"),
            )
        )
        or proposal_attempt.get("run_id") != run_id
        or proposal_attempt.get("cycle_index") != cycle
        or proposal_attempt.get("stage") != "PROPOSAL"
        or _moment(
            agent_input_context.get("created_at"),
            "V311_AGENT_CONSUMPTION_TIME_INVALID",
        )
        > _moment(
            proposal_attempt.get("reserved_at"),
            "V311_AGENT_CONSUMPTION_TIME_INVALID",
        )
        or _moment(
            proposal_attempt.get("reserved_at"),
            "V311_AGENT_CONSUMPTION_TIME_INVALID",
        )
        > _moment(
            proposal_request.get("created_at"),
            "V311_AGENT_CONSUMPTION_TIME_INVALID",
        )
        or _moment(
            proposal_request.get("created_at"),
            "V311_AGENT_CONSUMPTION_TIME_INVALID",
        )
        > _moment(
            proposal_consume.get("consumed_at"),
            "V311_AGENT_CONSUMPTION_TIME_INVALID",
        )
        or proposal_attempt.get("attempt_number") != 1
        or proposal_attempt.get("max_attempts") != 1
        or proposal_attempt.get("retry_allowed") is not False
        or proposal_request.get("agent_id") != V31_AGENT_ID
        or proposal_request.get("authoring_packet_binding")
        != agent_input_context.get("base_authoring_packet_binding")
        or proposal_delivery.get("payload_digest") != envelope_digest
        or proposal_consume.get("payload_digest") != envelope_digest
        or transport_evidence.get("run_id") != run_id
        or transport_evidence.get("cycle_index") != cycle
        or transport_evidence.get("agent_id") != V31_AGENT_ID
        or transport_evidence.get("proposal_payload_digest") != envelope_digest
        or transport_evidence.get("attempt_limit_per_stage") != 1
    ):
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_CONSUMPTION_CROSS_BINDING_INVALID"
        )
    document = {
        "schema_id": AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
        "schema_version": AGENT_CONTEXT_CONSUMPTION_SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle,
        "consumed_at": _time(
            proposal_consume["consumed_at"],
            "V311_AGENT_CONSUMPTION_TIME_INVALID",
        ),
        "agent_id": V31_AGENT_ID,
        "delivery_origin": V311_CURRENT_ROOT_DELIVERY_ORIGIN,
        "delivery_purpose": agent_input_context["delivery_purpose"],
        "agent_input_context_digest": context_digest,
        "agent_input_context_binding": context_binding,
        "base_authoring_packet_digest": agent_input_context[
            "base_authoring_packet_digest"
        ],
        "proposal_attempt_digest": attempt_digest,
        "proposal_attempt_binding": typed["proposal_attempt_binding"],
        "proposal_request_digest": request_digest,
        "proposal_request_binding": typed["proposal_request_binding"],
        "proposal_delivery_digest": delivery_digest,
        "proposal_delivery_binding": typed["proposal_delivery_binding"],
        "proposal_consume_digest": consume_digest,
        "proposal_consume_binding": typed["proposal_consume_binding"],
        "agent_authoring_envelope_digest": envelope_digest,
        "agent_authoring_envelope": dict(envelope),
        "transport_evidence_digest": evidence_digest,
        "transport_evidence_binding": typed["transport_evidence_binding"],
        "proposal_attempt_count": 1,
        "proposal_max_attempts": 1,
        "proposal_retry_count": 0,
        "direct_context_input_declared_by_controller": True,
        "durable_delivery_verified": True,
        "single_attempt_verified": True,
        "current_root_role_contract_verified": True,
        "transport_attestation_level": "PRACTICAL_CODEX_NOT_MODEL_ATTESTED",
        "claim": V311_DIRECT_INPUT_CLAIM,
        "limitations": list(_LIMITATIONS),
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD)


def verify_v311_agent_context_consumption_v1(
    document: Mapping[str, Any],
    *,
    agent_input_context: Mapping[str, Any],
    base_authoring_packet: Mapping[str, Any],
    proposal_attempt: Mapping[str, Any],
    proposal_request: Mapping[str, Any],
    proposal_claim: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_consume: Mapping[str, Any],
    transport_evidence: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _CONSUMPTION_FIELDS:
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_CONSUMPTION_DOCUMENT_INVALID"
        )
    supplied = verify_self_digest(
        document, AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD
    )
    rebuilt = build_v311_agent_context_consumption_v1(
        agent_input_context=agent_input_context,
        agent_input_context_binding=document["agent_input_context_binding"],
        base_authoring_packet=base_authoring_packet,
        proposal_attempt=proposal_attempt,
        proposal_attempt_binding=document["proposal_attempt_binding"],
        proposal_request=proposal_request,
        proposal_request_binding=document["proposal_request_binding"],
        proposal_claim=proposal_claim,
        proposal_delivery=proposal_delivery,
        proposal_delivery_binding=document["proposal_delivery_binding"],
        proposal_consume=proposal_consume,
        proposal_consume_binding=document["proposal_consume_binding"],
        transport_evidence=transport_evidence,
        transport_evidence_binding=document["transport_evidence_binding"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD]:
        raise V311AgentLifecycleV1Error(
            "V311_AGENT_CONSUMPTION_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_v311_successor_commit_envelope_v1(
    *,
    base_successor_commit_material: Mapping[str, Any],
    base_successor_commit_material_binding: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
    agent_input_context: Mapping[str, Any],
    agent_input_context_binding: Mapping[str, Any],
    agent_context_consumption: Mapping[str, Any],
    agent_context_consumption_binding: Mapping[str, Any],
    sealed_at: str,
) -> dict[str, Any]:
    base_digest = verify_v31_successor_cycle_commit_material_v2(
        base_successor_commit_material,
        experiment_contract=experiment_contract,
    )
    context_digest = verify_v311_agent_input_context_v1(agent_input_context)
    consumption_digest = verify_self_digest(
        agent_context_consumption, AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD
    )
    base_binding = _binding(
        base_successor_commit_material_binding,
        "V311_COMMIT_ENVELOPE_BASE_BINDING_INVALID",
        schema_id=BASE_COMMIT_SCHEMA_ID,
        digest_field=BASE_COMMIT_DIGEST_FIELD,
    )
    context_binding = _binding(
        agent_input_context_binding,
        "V311_COMMIT_ENVELOPE_CONTEXT_BINDING_INVALID",
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    consumption_binding = _binding(
        agent_context_consumption_binding,
        "V311_COMMIT_ENVELOPE_CONSUMPTION_BINDING_INVALID",
        schema_id=AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
        digest_field=AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    )
    run_id = base_successor_commit_material.get("run_id")
    cycle = base_successor_commit_material.get("cycle_index")
    accepted_digest = (
        base_successor_commit_material.get("assembly_bundle", {})
        .get("expected_artifact_digests", {})
        .get("STATE_ACCEPTED")
    )
    base_support = base_successor_commit_material.get("support_bindings")
    if (
        base_binding["semantic_digest"] != base_digest
        or context_binding["semantic_digest"] != context_digest
        or consumption_binding["semantic_digest"] != consumption_digest
        or agent_input_context.get("run_id") != run_id
        or agent_input_context.get("cycle_index") != cycle
        or agent_context_consumption.get("run_id") != run_id
        or agent_context_consumption.get("cycle_index") != cycle
        or agent_context_consumption.get("agent_input_context_digest")
        != context_digest
        or base_successor_commit_material.get("authoring_packet_digest")
        != agent_input_context.get("base_authoring_packet_digest")
        or base_successor_commit_material.get("transport_evidence_binding")
        != agent_context_consumption.get("transport_evidence_binding")
        or not isinstance(base_support, Mapping)
    ):
        raise V311AgentLifecycleV1Error(
            "V311_COMMIT_ENVELOPE_CROSS_BINDING_INVALID"
        )
    accepted = _digest(
        accepted_digest, "V311_COMMIT_ENVELOPE_ACCEPTED_DIGEST_INVALID"
    )
    document = {
        "schema_id": V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
        "schema_version": V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle,
        "sealed_at": _time(sealed_at, "V311_COMMIT_ENVELOPE_TIME_INVALID"),
        "base_successor_commit_material_digest": base_digest,
        "base_successor_commit_material_binding": base_binding,
        "agent_input_context_digest": context_digest,
        "agent_input_context_binding": context_binding,
        "agent_context_consumption_digest": consumption_digest,
        "agent_context_consumption_binding": consumption_binding,
        "base_authoring_packet_digest": agent_input_context[
            "base_authoring_packet_digest"
        ],
        "transport_evidence_digest": agent_context_consumption[
            "transport_evidence_digest"
        ],
        "accepted_state_digest": accepted,
        "base_support_bindings_digest": canonical_digest(base_support),
        "agent_lifecycle_bindings_required": True,
        "recovery_policy": "BASE_V2_DETERMINISTIC_TAIL_ONLY_NO_AGENT_NO_OUTCOME",
        "claim": V311_DIRECT_INPUT_CLAIM,
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD)


def verify_v311_successor_commit_envelope_v1(
    document: Mapping[str, Any],
    *,
    base_successor_commit_material: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
    agent_input_context: Mapping[str, Any],
    agent_context_consumption: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _COMMIT_ENVELOPE_FIELDS:
        raise V311AgentLifecycleV1Error(
            "V311_COMMIT_ENVELOPE_DOCUMENT_INVALID"
        )
    supplied = verify_self_digest(
        document, V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD
    )
    rebuilt = build_v311_successor_commit_envelope_v1(
        base_successor_commit_material=base_successor_commit_material,
        base_successor_commit_material_binding=document[
            "base_successor_commit_material_binding"
        ],
        experiment_contract=experiment_contract,
        agent_input_context=agent_input_context,
        agent_input_context_binding=document["agent_input_context_binding"],
        agent_context_consumption=agent_context_consumption,
        agent_context_consumption_binding=document[
            "agent_context_consumption_binding"
        ],
        sealed_at=document["sealed_at"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[
        V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD
    ]:
        raise V311AgentLifecycleV1Error(
            "V311_COMMIT_ENVELOPE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def verify_v311_successor_commit_envelope_full_v1(
    document: Mapping[str, Any],
    *,
    base_successor_commit_material: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
    agent_input_context: Mapping[str, Any],
    agent_context_consumption: Mapping[str, Any],
    base_authoring_packet: Mapping[str, Any],
    proposal_attempt: Mapping[str, Any],
    proposal_request: Mapping[str, Any],
    proposal_claim: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_consume: Mapping[str, Any],
    transport_evidence: Mapping[str, Any],
) -> str:
    """Replay the complete context-to-delivery chain before commit admission."""

    consumption_digest = verify_v311_agent_context_consumption_v1(
        agent_context_consumption,
        agent_input_context=agent_input_context,
        base_authoring_packet=base_authoring_packet,
        proposal_attempt=proposal_attempt,
        proposal_request=proposal_request,
        proposal_claim=proposal_claim,
        proposal_delivery=proposal_delivery,
        proposal_consume=proposal_consume,
        transport_evidence=transport_evidence,
    )
    supplied = verify_v311_successor_commit_envelope_v1(
        document,
        base_successor_commit_material=base_successor_commit_material,
        experiment_contract=experiment_contract,
        agent_input_context=agent_input_context,
        agent_context_consumption=agent_context_consumption,
    )
    if (
        document.get("agent_context_consumption_digest")
        != consumption_digest
        or document.get("transport_evidence_digest")
        != transport_evidence.get("transport_evidence_digest")
    ):
        raise V311AgentLifecycleV1Error(
            "V311_COMMIT_ENVELOPE_FULL_REPLAY_MISMATCH"
        )
    return supplied


__all__ = [
    "AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD",
    "AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID",
    "AGENT_INPUT_CONTEXT_DIGEST_FIELD",
    "AGENT_INPUT_CONTEXT_SCHEMA_ID",
    "THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD",
    "THEORY_ADDENDUM_SEMANTIC_DOCUMENT_SCHEMA_ID",
    "V311_AGENT_CONTEXT_ROOT",
    "V311_CURRENT_ROOT_DELIVERY_ORIGIN",
    "V311_DIRECT_INPUT_CLAIM",
    "V311_QUALIFICATION_AGENT_SUPPORT_KEYS",
    "V311_QUALIFICATION_AGENT_SUPPORT_SPECS",
    "V311_QUALIFICATION_CONTEXT_PROFILE",
    "V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD",
    "V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID",
    "V311_TARGET_AGENT_SUPPORT_KEYS",
    "V311_TARGET_AGENT_SUPPORT_SPECS",
    "V311_TARGET_CONTEXT_PROFILE",
    "V311AgentLifecycleV1Error",
    "agent_context_consumption_ref_v1",
    "agent_input_context_ref_v1",
    "build_v311_agent_context_consumption_v1",
    "build_v311_agent_input_context_v1",
    "build_v311_successor_commit_envelope_v1",
    "build_v311_theory_addendum_semantic_document_v1",
    "successor_commit_envelope_ref_v1",
    "verify_v311_agent_context_consumption_v1",
    "verify_v311_agent_input_context_v1",
    "verify_v311_agent_input_context_with_packet_v1",
    "verify_v311_successor_commit_envelope_v1",
    "verify_v311_successor_commit_envelope_full_v1",
    "verify_v311_theory_addendum_semantic_document_v1",
]
