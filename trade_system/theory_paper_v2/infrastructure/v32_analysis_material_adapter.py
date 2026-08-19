"""Production V3.2 material composition for the local prospective lane.

This adapter is deliberately semantic-output free.  It verifies and composes
already-authorized documents, current public-market material, durable previous
state, and exact outcome receipts.  It never calls a model, fetches a network
resource, reads an account, fabricates an UNKNOWN assessment, or creates an
executable trading instruction.

Subjective UNKNOWN packages, manual evidence revisions, and deterministic
recovery traces may enter only through an injected durable Strategy-Agent
reader.  Production composition injects an explicit local reader; omission is
never interpreted as an observed empty revision input.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Protocol, Sequence

from ..application.v32_authorized_revision_orchestration import (
    build_v32_revision_input_state_v1,
    build_v32_authorized_revision_cycle_registry_v1,
    verify_v32_authorized_revision_cycle_registry_v1,
    verify_v32_authorized_revision_support_bundle_v1,
    verify_v32_revision_input_state_v1,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    verify_self_digest,
)
from ..domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    AUTHORIZATION_RECEIPT_SCHEMA_ID,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    RUNTIME_MANIFEST_SCHEMA_ID,
    QUALIFICATION_PROFILE,
    TARGET_PROFILE,
    THEORY_APPROVAL_DIGEST_FIELD,
    THEORY_APPROVAL_SCHEMA_ID,
    THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
    THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
    verify_v32_authority_v1,
    verify_v32_authorization_receipt_v1,
    verify_v32_runtime_manifest,
    verify_v32_theory_approval_receipt_v1,
)
from ..domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
    SCHEMA_ID as EXPERIMENT_CONTRACT_SCHEMA_ID,
    verify_v32_experiment_contract_v1,
)
from ..domain.v31_sentiment_native_projection_v2 import (
    verify_v31_native_sentiment_source_registry,
)
from ..domain.v32_agent_lifecycle import (
    MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES,
    PROPOSAL_PACKET_DIGEST_FIELD,
    PROPOSAL_PACKET_SCHEMA_ID,
    PROPOSAL_SUPPORT_SPECS,
    SELECTION_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_SCHEMA_ID,
    V32AgentLifecycleError,
    V32_TARGET_CONTEXT_PROFILE,
    V32_QUALIFICATION_CONTEXT_PROFILE,
    build_v32_agent_input_context_v1,
    build_v32_proposal_canonical_packet_v1,
    verify_v32_agent_input_context_v1,
    verify_v32_proposal_canonical_packet_v1,
    verify_v32_selection_canonical_packet_v1,
    verify_v32_theory_semantic_document_v1,
)
from ..domain.v32_association_preregistration import (
    verify_v32_association_preregistration,
)
from ..domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD as CONTEXT_MANIFEST_DIGEST_FIELD,
    MANIFEST_SCHEMA_ID as CONTEXT_MANIFEST_SCHEMA_ID,
    POLICY_DIGEST_FIELD as CONTEXT_POLICY_DIGEST_FIELD,
    SELECTION_DIGEST_FIELD as CONTEXT_SELECTION_DIGEST_FIELD,
    SELECTION_SCHEMA_ID as CONTEXT_SELECTION_SCHEMA_ID,
    SHARD_DIGEST_FIELD as CONTEXT_SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID as CONTEXT_SHARD_SCHEMA_ID,
    build_v32_context_compaction_bundle_v1,
    build_v32_context_shard_selection_v1,
    verify_v32_context_compaction_policy_v1,
)
from ..domain.v32_cycle_audit_narrative import (
    verify_v32_cycle_audit_policy_v1,
)
from ..domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    verify_v32_active_authority_projection,
)
from ..domain.v32_current_root_agent_mailbox import (
    build_v32_current_codex_presentation_envelope_v1,
)
from ..domain.v32_data_gap_escalation import (
    ESCALATION_DIGEST_FIELD,
    ESCALATION_SCHEMA_ID,
    verify_v32_data_gap_escalation_v1,
    verify_v32_data_gap_manual_policy_v1,
)
from ..domain.v32_environment_capability import (
    verify_v32_environment_capability_profile_v1,
)
from ..domain.v32_evaluation_contract import verify_v32_evaluation_contract
from ..domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
    verify_v32_outcome_schedule_set,
)
from ..domain.v32_recovery_supervision import (
    verify_v32_recovery_supervision_policy_v1,
)
from ..domain.v32_runtime_support_contracts import (
    verify_v32_clock_and_tick_policy_v1,
    verify_v32_public_outcome_adapter_contract_v1,
)
from ..domain.v32_timeframe_cache import (
    FRAME_ROLES,
    build_v32_context_frame_v1,
    build_v32_timeframe_context_state_v1,
    project_v32_refreshed_frame_policy_v1,
    project_v32_timeframe_payloads_v1,
    verify_v32_timeframe_invalidation_bindings_v1,
    verify_v32_timeframe_context_state_intrinsic_v1,
    verify_v32_timeframe_context_state_v1,
    verify_v32_timeframe_context_transition_v1,
    verify_v32_timeframe_production_policy_v1,
)
from ..domain.v32_unknown_assessment import (
    verify_v32_unknown_subjective_policy_v1,
)
from .authority.v32_current_research import V32_APPLICATION_PROJECTION_KEYS
from .v32_current_root_agent_mailbox import LocalV32CurrentRootAgentMailbox
from .v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    verify_v32_public_market_analysis_bundle,
)


class V32AnalysisMaterialAdapterError(ValueError):
    """Authorized V3.2 material was incomplete, forged, or cross-bound."""


class V32StrategyRevisionMaterialReader(Protocol):
    """Read Agent-authored revision packages without changing durable state."""

    reader_binding: Mapping[str, str]

    def read_cycle_revision_material(
        self,
        *,
        run_id: str,
        cycle_index: int,
        proposal_packet: Mapping[str, Any],
        selection_packet: Mapping[str, Any],
        observed_at: str,
    ) -> Mapping[str, Any]: ...


_NO_REVISION_INPUT_CONFIGURATION = {
    "revision_source_configured": False,
    "filesystem_read_performed": False,
    "implicit_empty_material_allowed": False,
}


class LocalV32NoRevisionInputMaterialReader:
    """Explicit local no-input reader used until a file importer is configured."""

    reader_binding = {
        "reader_id": "LOCAL_V32_NO_REVISION_INPUT_READER_V1",
        "reader_version": "1.0.0",
        "reader_kind": "LOCAL_EXPLICIT_NO_REVISION_INPUT",
        "configuration_digest": canonical_digest(
            _NO_REVISION_INPUT_CONFIGURATION
        ),
    }

    def read_cycle_revision_material(
        self,
        *,
        run_id: str,
        cycle_index: int,
        proposal_packet: Mapping[str, Any],
        selection_packet: Mapping[str, Any],
        observed_at: str,
    ) -> Mapping[str, Any]:
        del proposal_packet, selection_packet
        return {
            "revision_input_state": build_v32_revision_input_state_v1(
                run_id=run_id,
                cycle_index=cycle_index,
                state="NO_REVISION_INPUT",
                observed_at=observed_at,
                reason="NO_LOCAL_REVISION_INPUT_SOURCE_CONFIGURED",
                reader_binding=self.reader_binding,
            ),
            "unknown_tracks": [],
            "manual_evidence_entries": [],
            "recovery_traces": [],
        }


class EmptyV32StrategyRevisionMaterialReader(LocalV32NoRevisionInputMaterialReader):
    """Compatibility alias; it is explicit-only and is never a default."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_PATH_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_STATIC_SUPPORT_NAMES = frozenset(PROPOSAL_SUPPORT_SPECS).difference(
    {
        "active_authority_projection",
        "experiment_contract",
        "timeframe_context_state",
        "agent_market_graph_view",
        "cycle_source_admission",
    }
)
_MANIFEST_SUPPORT_TO_AGENT = {
    "association_preregistration_digest": "association_preregistration",
    "authorized_revision_support_bundle_digest": (
        "authorized_revision_support_bundle"
    ),
    "clock_policy_digest": "clock_and_tick_policy",
    "evaluation_contract_digest": "evaluation_contract",
    "outcome_adapter_contract_digest": "outcome_adapter_contract",
    "recovery_supervision_policy_digest": "recovery_supervision_policy",
    "twelve_axis_source_registry_digest": "twelve_axis_source_registry",
}
_REVISION_COMPONENT_NAMES = (
    "context_compaction_policy",
    "unknown_subjective_policy",
    "data_gap_manual_policy",
    "cycle_audit_policy",
    "environment_capability_profile",
)
_REVISION_READER_FIELDS = frozenset(
    {
        "revision_input_state",
        "unknown_tracks",
        "manual_evidence_entries",
        "recovery_traces",
    }
)
_REVISION_READER_BINDING_FIELDS = frozenset(
    {"reader_id", "reader_version", "reader_kind", "configuration_digest"}
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32AnalysisMaterialAdapterError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32AnalysisMaterialAdapterError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32AnalysisMaterialAdapterError(code) from exc
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if parsed.tzinfo is None or canonical != text:
        raise V32AnalysisMaterialAdapterError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _revision_reader_binding(value: Any) -> dict[str, str]:
    code = "V32_ANALYSIS_MATERIAL_REVISION_READER_BINDING_INVALID"
    if not isinstance(value, Mapping) or set(value) != _REVISION_READER_BINDING_FIELDS:
        raise V32AnalysisMaterialAdapterError(code)
    normalized = {
        "reader_id": _text(value["reader_id"], code),
        "reader_version": _text(value["reader_version"], code),
        "reader_kind": _text(value["reader_kind"], code),
        "configuration_digest": _digest(value["configuration_digest"], code),
    }
    if normalized["reader_version"] != "1.0.0":
        raise V32AnalysisMaterialAdapterError(code)
    return normalized


def _relative(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32AnalysisMaterialAdapterError(code)
    return text


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _binding(
    value: Any,
    *,
    code: str,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise V32AnalysisMaterialAdapterError(code)
    keys = set(value)
    if keys == _PUBLIC_BINDING_FIELDS:
        relative_ref = value.get("relative_ref")
    elif keys == _PATH_BINDING_FIELDS:
        relative_ref = value.get("path")
    else:
        raise V32AnalysisMaterialAdapterError(code)
    result = {
        "relative_ref": _relative(relative_ref, code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    if (
        (schema_id is not None and result["schema_id"] != schema_id)
        or (digest_field is not None and result["digest_field"] != digest_field)
    ):
        raise V32AnalysisMaterialAdapterError(code)
    return result


def _document_binding(
    *,
    document: Mapping[str, Any],
    supplied: Mapping[str, Any],
    schema_id: str,
    digest_field: str,
    code: str,
) -> dict[str, str]:
    normalized = _binding(
        supplied, code=code, schema_id=schema_id, digest_field=digest_field
    )
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32AnalysisMaterialAdapterError(code) from exc
    if (
        document.get("schema_id") != schema_id
        or normalized["semantic_digest"] != semantic
        or normalized["physical_sha256"] != _physical(document)
    ):
        raise V32AnalysisMaterialAdapterError(code)
    return normalized


def _embedded_binding(
    *, relative_ref: str, document: Mapping[str, Any], schema_id: str, digest_field: str
) -> dict[str, str]:
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_DOCUMENT_INVALID"
        ) from exc
    return {
        "relative_ref": _relative(
            relative_ref, "V32_ANALYSIS_MATERIAL_BINDING_REF_INVALID"
        ),
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": _physical(document),
    }


def _permit_identity(permit: Mapping[str, Any]) -> tuple[str, int, str]:
    if not isinstance(permit, Mapping):
        raise V32AnalysisMaterialAdapterError("V32_ANALYSIS_MATERIAL_PERMIT_INVALID")
    cycle = permit.get("analysis_cycle_index")
    if (
        isinstance(cycle, bool)
        or not isinstance(cycle, int)
        or not 1 <= cycle <= 16
        or permit.get("permit_kind") != "ANALYSIS_TICK"
        or permit.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or permit.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
        or permit.get("executable") is not False
        or permit.get("account_access") is not False
        or permit.get("order_submission") is not False
    ):
        raise V32AnalysisMaterialAdapterError("V32_ANALYSIS_MATERIAL_PERMIT_INVALID")
    return (
        _text(permit.get("run_id"), "V32_ANALYSIS_MATERIAL_PERMIT_INVALID"),
        cycle,
        _time(
            permit.get("analysis_decision_at"),
            "V32_ANALYSIS_MATERIAL_PERMIT_INVALID",
        ),
    )


def _verify_full_loader_projection(
    bundle: Mapping[str, Mapping[str, Any]],
    *,
    active_authority_projection: Mapping[str, Any],
) -> tuple[str, str, str, dict[str, dict[str, Any]]]:
    if (
        not isinstance(bundle, Mapping)
        or tuple(bundle) != V32_APPLICATION_PROJECTION_KEYS
        or any(not isinstance(bundle.get(key), Mapping) for key in bundle)
    ):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_AUTHORITY_BUNDLE_INVALID"
        )
    documents = {key: deepcopy(dict(bundle[key])) for key in bundle}
    try:
        verify_v32_theory_approval_receipt_v1(documents["theory_approval"])
        verify_v32_experiment_contract_v1(documents["experiment_contract"])
        verify_v32_runtime_manifest(documents["manifest"])
        verify_v32_authorization_receipt_v1(documents["authorization_receipt"])
        verify_v32_authority_v1(documents["authority"])
        projection_digest = verify_v32_active_authority_projection(
            active_authority_projection
        )
    except (TypeError, ValueError) as exc:
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_AUTHORITY_BUNDLE_INVALID"
        ) from exc
    authority = documents["authority"]
    contract = documents["experiment_contract"]
    manifest = documents["manifest"]
    authorization = documents["authorization_receipt"]
    run_id = _text(authority.get("run_id"), "V32_ANALYSIS_MATERIAL_RUN_INVALID")
    profile = authority.get("profile")
    support_scope = (
        run_id if profile == TARGET_PROFILE else str(authority.get("target_run_id"))
    )
    context_profile = (
        V32_TARGET_CONTEXT_PROFILE
        if profile == TARGET_PROFILE
        else V32_QUALIFICATION_CONTEXT_PROFILE
    )
    if (
        profile not in {TARGET_PROFILE, QUALIFICATION_PROFILE}
        or authority.get("status") != "ACTIVE"
        or authority.get("target_run_id") != support_scope
        or contract.get("run_id") != support_scope
        or manifest.get("target_run_id") != support_scope
        or (
            profile == TARGET_PROFILE
            and (support_scope != run_id or manifest.get("qualification_run_id") == run_id)
        )
        or (
            profile == QUALIFICATION_PROFILE
            and manifest.get("qualification_run_id") != run_id
        )
        or active_authority_projection.get("authorized_run_id") != run_id
        or active_authority_projection.get("experiment_contract_digest")
        != contract[EXPERIMENT_CONTRACT_DIGEST_FIELD]
        or active_authority_projection.get(
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
        )
        != projection_digest
    ):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_AUTHORITY_SCOPE_INVALID"
        )

    expected = (
        (
            documents["theory_approval"],
            manifest["theory_approval_binding"],
            THEORY_APPROVAL_SCHEMA_ID,
            THEORY_APPROVAL_DIGEST_FIELD,
        ),
        (
            contract,
            manifest["experiment_contract_binding"],
            EXPERIMENT_CONTRACT_SCHEMA_ID,
            EXPERIMENT_CONTRACT_DIGEST_FIELD,
        ),
        (
            documents["theory_approval"],
            authorization["theory_approval_binding"],
            THEORY_APPROVAL_SCHEMA_ID,
            THEORY_APPROVAL_DIGEST_FIELD,
        ),
        (
            contract,
            authorization["experiment_contract_binding"],
            EXPERIMENT_CONTRACT_SCHEMA_ID,
            EXPERIMENT_CONTRACT_DIGEST_FIELD,
        ),
        (
            manifest,
            authorization["runtime_manifest_binding"],
            RUNTIME_MANIFEST_SCHEMA_ID,
            RUNTIME_MANIFEST_DIGEST_FIELD,
        ),
        (
            authorization,
            authority["authorization_receipt_binding"],
            AUTHORIZATION_RECEIPT_SCHEMA_ID,
            AUTHORIZATION_RECEIPT_DIGEST_FIELD,
        ),
        (
            authority,
            active_authority_projection["governing_authority_binding"],
            AUTHORITY_SCHEMA_ID,
            AUTHORITY_DIGEST_FIELD,
        ),
    )
    for document, supplied, schema_id, digest_field in expected:
        _document_binding(
            document=document,
            supplied=supplied,
            schema_id=schema_id,
            digest_field=digest_field,
            code="V32_ANALYSIS_MATERIAL_AUTHORITY_CROSS_BINDING_INVALID",
        )
    for field, document_key, schema_id, digest_field in (
        (
            "theory_approval_binding",
            "theory_approval",
            THEORY_APPROVAL_SCHEMA_ID,
            THEORY_APPROVAL_DIGEST_FIELD,
        ),
        (
            "experiment_contract_binding",
            "experiment_contract",
            EXPERIMENT_CONTRACT_SCHEMA_ID,
            EXPERIMENT_CONTRACT_DIGEST_FIELD,
        ),
        (
            "runtime_manifest_binding",
            "manifest",
            RUNTIME_MANIFEST_SCHEMA_ID,
            RUNTIME_MANIFEST_DIGEST_FIELD,
        ),
    ):
        left = _document_binding(
            document=documents[document_key],
            supplied=authority[field],
            schema_id=schema_id,
            digest_field=digest_field,
            code="V32_ANALYSIS_MATERIAL_AUTHORITY_CROSS_BINDING_INVALID",
        )
        right = _document_binding(
            document=documents[document_key],
            supplied=authorization[field],
            schema_id=schema_id,
            digest_field=digest_field,
            code="V32_ANALYSIS_MATERIAL_AUTHORITY_CROSS_BINDING_INVALID",
        )
        if left != right:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_AUTHORITY_CROSS_BINDING_INVALID"
            )
    return run_id, support_scope, context_profile, documents


def _verify_static_supports(
    *,
    run_id: str,
    authority_documents: Mapping[str, Mapping[str, Any]],
    theory_semantic_document: Mapping[str, Any],
    theory_semantic_document_binding: Mapping[str, Any],
    support_documents: Mapping[str, Mapping[str, Any]],
    support_bindings: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    if (
        not isinstance(support_documents, Mapping)
        or set(support_documents) != _STATIC_SUPPORT_NAMES
        or not isinstance(support_bindings, Mapping)
        or set(support_bindings) != _STATIC_SUPPORT_NAMES
    ):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_SUPPORT_SET_INVALID"
        )
    theory = deepcopy(dict(theory_semantic_document))
    try:
        theory_digest = verify_v32_theory_semantic_document_v1(theory)
    except (TypeError, ValueError) as exc:
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_THEORY_INVALID"
        ) from exc
    theory_binding = _document_binding(
        document=theory,
        supplied=theory_semantic_document_binding,
        schema_id=THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
        digest_field=THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
        code="V32_ANALYSIS_MATERIAL_THEORY_BINDING_INVALID",
    )
    manifest = authority_documents["manifest"]
    approval = authority_documents["theory_approval"]
    contract = authority_documents["experiment_contract"]
    if (
        theory_binding
        != _binding(
            manifest["theory_semantic_document_binding"],
            code="V32_ANALYSIS_MATERIAL_THEORY_BINDING_INVALID",
            schema_id=THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
            digest_field=THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
        )
        or approval.get("theory_binding", {}).get("semantic_digest")
        != theory_digest
        or contract.get("theory_binding", {}).get("semantic_digest")
        != theory_digest
        or approval.get("theory_binding", {}).get("physical_sha256")
        != theory.get("physical_sha256")
        or contract.get("theory_binding", {}).get("physical_sha256")
        != theory.get("physical_sha256")
    ):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_THEORY_CROSS_BINDING_INVALID"
        )

    documents = {
        name: deepcopy(dict(support_documents[name]))
        for name in sorted(_STATIC_SUPPORT_NAMES)
    }
    bindings: dict[str, dict[str, str]] = {}
    for name in sorted(_STATIC_SUPPORT_NAMES):
        schema_id, digest_field = PROPOSAL_SUPPORT_SPECS[name]
        bindings[name] = _document_binding(
            document=documents[name],
            supplied=support_bindings[name],
            schema_id=schema_id,
            digest_field=digest_field,
            code=f"V32_ANALYSIS_MATERIAL_SUPPORT_BINDING_INVALID:{name}",
        )

    try:
        verify_v31_native_sentiment_source_registry(
            documents["twelve_axis_source_registry"]
        )
        verify_v32_association_preregistration(
            documents["association_preregistration"]
        )
        verify_v32_evaluation_contract(
            documents["evaluation_contract"],
            documents["association_preregistration"],
        )
        verify_v32_clock_and_tick_policy_v1(documents["clock_and_tick_policy"])
        verify_v32_public_outcome_adapter_contract_v1(
            documents["outcome_adapter_contract"]
        )
        verify_v32_context_compaction_policy_v1(
            documents["context_compaction_policy"]
        )
        verify_v32_unknown_subjective_policy_v1(
            documents["unknown_subjective_policy"]
        )
        verify_v32_data_gap_manual_policy_v1(documents["data_gap_manual_policy"])
        verify_v32_cycle_audit_policy_v1(documents["cycle_audit_policy"])
        verify_v32_environment_capability_profile_v1(
            documents["environment_capability_profile"]
        )
        verify_v32_recovery_supervision_policy_v1(
            documents["recovery_supervision_policy"]
        )
        verify_v32_authorized_revision_support_bundle_v1(
            documents["authorized_revision_support_bundle"],
            context_compaction_policy=documents["context_compaction_policy"],
            unknown_subjective_policy=documents["unknown_subjective_policy"],
            data_gap_manual_policy=documents["data_gap_manual_policy"],
            cycle_audit_policy=documents["cycle_audit_policy"],
            environment_capability_profile=documents[
                "environment_capability_profile"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_SUPPORT_OWNING_REPLAY_INVALID"
        ) from exc

    manifest_bindings = manifest["support_document_bindings"]
    contract_digests = contract["support_bindings"]
    for manifest_name, agent_name in _MANIFEST_SUPPORT_TO_AGENT.items():
        expected = _binding(
            manifest_bindings[manifest_name],
            code=f"V32_ANALYSIS_MATERIAL_SUPPORT_MANIFEST_INVALID:{agent_name}",
            schema_id=PROPOSAL_SUPPORT_SPECS[agent_name][0],
            digest_field=PROPOSAL_SUPPORT_SPECS[agent_name][1],
        )
        if (
            bindings[agent_name] != expected
            or contract_digests.get(manifest_name)
            != bindings[agent_name]["semantic_digest"]
        ):
            raise V32AnalysisMaterialAdapterError(
                f"V32_ANALYSIS_MATERIAL_SUPPORT_CROSS_BINDING_INVALID:{agent_name}"
            )

    component_rows = documents["authorized_revision_support_bundle"].get(
        "components"
    )
    if not isinstance(component_rows, list):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_REVISION_COMPONENT_SET_INVALID"
        )
    by_role = {
        row.get("role"): row.get("binding")
        for row in component_rows
        if isinstance(row, Mapping)
    }
    if set(by_role) != set(_REVISION_COMPONENT_NAMES):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_REVISION_COMPONENT_SET_INVALID"
        )
    for name in _REVISION_COMPONENT_NAMES:
        if bindings[name] != _binding(
            by_role[name],
            code=f"V32_ANALYSIS_MATERIAL_REVISION_COMPONENT_BINDING_INVALID:{name}",
            schema_id=PROPOSAL_SUPPORT_SPECS[name][0],
            digest_field=PROPOSAL_SUPPORT_SPECS[name][1],
        ):
            raise V32AnalysisMaterialAdapterError(
                f"V32_ANALYSIS_MATERIAL_REVISION_COMPONENT_BINDING_INVALID:{name}"
            )
    for name in (
        "association_preregistration",
        "evaluation_contract",
        "clock_and_tick_policy",
        "outcome_adapter_contract",
        "authorized_revision_support_bundle",
        "twelve_axis_source_registry",
    ):
        if documents[name].get("run_scope_id", run_id) != run_id:
            raise V32AnalysisMaterialAdapterError(
                f"V32_ANALYSIS_MATERIAL_SUPPORT_SCOPE_INVALID:{name}"
            )
    return theory, theory_binding, documents, bindings


class LocalV32AnalysisMaterialAdapter:
    """No-I/O production implementation of ``V32AnalysisMaterialPort``."""

    def __init__(
        self,
        *,
        verified_target_authority_bundle: Mapping[str, Mapping[str, Any]],
        active_authority_projection: Mapping[str, Any],
        theory_semantic_document: Mapping[str, Any],
        theory_semantic_document_binding: Mapping[str, Any],
        frozen_support_documents: Mapping[str, Mapping[str, Any]],
        frozen_support_bindings: Mapping[str, Mapping[str, Any]],
        strategy_revision_material_reader: (
            V32StrategyRevisionMaterialReader | None
        ) = None,
        strategy_revision_observation_clock: Any | None = None,
    ) -> None:
        run_id, support_scope, context_profile, authority_documents = _verify_full_loader_projection(
            verified_target_authority_bundle,
            active_authority_projection=active_authority_projection,
        )
        theory, theory_binding, support_documents, support_bindings = (
            _verify_static_supports(
                run_id=support_scope,
                authority_documents=authority_documents,
                theory_semantic_document=theory_semantic_document,
                theory_semantic_document_binding=theory_semantic_document_binding,
                support_documents=frozen_support_documents,
                support_bindings=frozen_support_bindings,
            )
        )
        reader = strategy_revision_material_reader
        if reader is not None and not callable(
            getattr(reader, "read_cycle_revision_material", None)
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_READER_INVALID"
            )
        if reader is not None and not callable(strategy_revision_observation_clock):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_READER_CLOCK_INVALID"
            )
        reader_binding = (
            None
            if reader is None
            else _revision_reader_binding(getattr(reader, "reader_binding", None))
        )
        self._run_id = run_id
        self._context_profile = context_profile
        self._authority_documents = authority_documents
        self._active_authority_projection = deepcopy(
            dict(active_authority_projection)
        )
        self._theory = theory
        self._theory_binding = theory_binding
        self._supports = support_documents
        self._support_bindings = support_bindings
        self._revision_reader = reader
        self._revision_reader_binding = reader_binding
        self._revision_observation_clock = strategy_revision_observation_clock

    def build_timeframe_context(
        self,
        *,
        permit: Mapping[str, Any],
        public_market_analysis_bundle: Mapping[str, Any],
        previous_timeframe_context: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        run_id, cycle, decision_time = _permit_identity(permit)
        try:
            verify_v32_public_market_analysis_bundle(public_market_analysis_bundle)
        except (TypeError, ValueError) as exc:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_PUBLIC_BUNDLE_INVALID"
            ) from exc
        if (
            run_id != self._run_id
            or public_market_analysis_bundle.get("run_id") != run_id
            or public_market_analysis_bundle.get("cycle_index") != cycle
            or _moment(
                public_market_analysis_bundle.get("available_at"),
                "V32_ANALYSIS_MATERIAL_PUBLIC_BUNDLE_TIME_INVALID",
            )
            > _moment(decision_time, "V32_ANALYSIS_MATERIAL_PUBLIC_BUNDLE_TIME_INVALID")
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_PUBLIC_BUNDLE_SCOPE_INVALID"
            )
        previous = (
            None
            if previous_timeframe_context is None
            else deepcopy(dict(previous_timeframe_context))
        )
        if (cycle == 1) != (previous is None):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_TIMEFRAME_PREVIOUS_INVALID"
            )
        if previous is not None:
            try:
                verify_v32_timeframe_context_state_intrinsic_v1(previous)
            except (TypeError, ValueError) as exc:
                raise V32AnalysisMaterialAdapterError(
                    "V32_ANALYSIS_MATERIAL_TIMEFRAME_PREVIOUS_INVALID"
                ) from exc
            if (
                previous.get("run_id") != run_id
                or previous.get("cycle_index") != cycle - 1
            ):
                raise V32AnalysisMaterialAdapterError(
                    "V32_ANALYSIS_MATERIAL_TIMEFRAME_PREVIOUS_INVALID"
                )

        try:
            payloads = project_v32_timeframe_payloads_v1(
                public_market_analysis_bundle
            )
        except (TypeError, ValueError) as exc:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_PUBLIC_BUNDLE_INVALID"
            ) from exc
        previous_frames = (
            {}
            if previous is None
            else {row["role"]: row for row in previous["frames"]}
        )
        # No non-TTL event enters production until an owning public event
        # schema can prove both the source bytes and the event classification.
        # Treating an arbitrary PIT digest as a macro/regulatory signal would
        # turn a typed invalidation into an Agent-controlled cache bypass.
        invalidation_events: list[dict[str, Any]] = []
        strategic_payload_digest = canonical_digest(payloads["STRATEGIC_CONTEXT"])
        prior_strategic = previous_frames.get("STRATEGIC_CONTEXT")
        strategic_expired = bool(
            prior_strategic is not None
            and _moment(
                prior_strategic["expires_at"],
                "V32_ANALYSIS_MATERIAL_TIMEFRAME_PREVIOUS_INVALID",
            )
            <= _moment(
                decision_time,
                "V32_ANALYSIS_MATERIAL_TIMEFRAME_PREVIOUS_INVALID",
            )
        )
        carry_strategic = bool(
            prior_strategic is not None
            and not strategic_expired
            and prior_strategic["payload_digest"] == strategic_payload_digest
            and not invalidation_events
        )
        if strategic_expired and prior_strategic is not None:
            invalidation_events.append(
                {
                    "event_id": f"v32:{run_id}:strategic-ttl-expired:{cycle:04d}",
                    "event_type": "STRATEGIC_TTL_EXPIRED",
                    "occurred_at": prior_strategic["expires_at"],
                    "available_at": prior_strategic["expires_at"],
                    "evidence_refs": [prior_strategic["frame_digest"]],
                }
            )

        frames = []
        for role in FRAME_ROLES:
            prior_frame = previous_frames.get(role)
            if role == "STRATEGIC_CONTEXT" and carry_strategic:
                assert prior_frame is not None
                frames.append(
                    build_v32_context_frame_v1(
                        frame_id=prior_frame["frame_id"],
                        role=role,
                        update_mode="CARRIED_FORWARD",
                        created_at=prior_frame["created_at"],
                        as_of=prior_frame["as_of"],
                        available_at=prior_frame["available_at"],
                        expires_at=prior_frame["expires_at"],
                        payload_digest=prior_frame["payload_digest"],
                        source_refs=prior_frame["source_refs"],
                        dependency_groups=prior_frame["dependency_groups"],
                        invalidation_event_types=prior_frame[
                            "invalidation_event_types"
                        ],
                        previous_frame=prior_frame,
                        decision_time=decision_time,
                    )
                )
                continue
            policy = project_v32_refreshed_frame_policy_v1(
                role=role,
                run_id=run_id,
                decision_time=decision_time,
                public_market_analysis_bundle=public_market_analysis_bundle,
            )
            frames.append(
                build_v32_context_frame_v1(
                    frame_id=policy["frame_id"],
                    role=role,
                    update_mode="REFRESHED",
                    created_at=policy["created_at"],
                    as_of=policy["as_of"],
                    available_at=policy["available_at"],
                    expires_at=policy["expires_at"],
                    payload_digest=(
                        strategic_payload_digest
                        if role == "STRATEGIC_CONTEXT"
                        else canonical_digest(payloads[role])
                    ),
                    source_refs=policy["source_refs"],
                    dependency_groups=policy["dependency_groups"],
                    invalidation_event_types=policy[
                        "invalidation_event_types"
                    ],
                    previous_frame=prior_frame,
                    decision_time=decision_time,
                )
            )
        state = build_v32_timeframe_context_state_v1(
            run_id=run_id,
            cycle_index=cycle,
            decision_time=decision_time,
            state_mode="FULL_CONTEXT" if cycle == 1 else "DELTA_UPDATE",
            previous_state=previous,
            frames=frames,
            observed_invalidation_events=invalidation_events,
            analysis_clock_interval_seconds=900,
            target_delta_processing_seconds=120,
        )
        if previous is None:
            verify_v32_timeframe_context_state_v1(state)
        else:
            verify_v32_timeframe_context_transition_v1(
                previous_state=previous, current_state=state
            )
        verify_v32_timeframe_production_policy_v1(
            timeframe_context_state=state,
            public_market_analysis_bundle=public_market_analysis_bundle,
        )
        verify_v32_timeframe_invalidation_bindings_v1(
            timeframe_context_state=state,
            public_market_analysis_bundle=public_market_analysis_bundle,
            previous_state=previous,
        )
        return state

    def build_proposal_packet(
        self,
        *,
        permit: Mapping[str, Any],
        active_authority_projection: Mapping[str, Any],
        current_artifacts: Mapping[str, Mapping[str, Any]],
        current_bindings: Mapping[str, Mapping[str, Any]],
        previous_artifacts: Mapping[str, Mapping[str, Any] | None],
        previous_bindings: Mapping[str, Mapping[str, Any] | None],
        matured_outcome_receipts: Sequence[Mapping[str, Any]],
        matured_outcome_receipt_bindings: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        run_id, cycle, decision_time = _permit_identity(permit)
        if (
            run_id != self._run_id
            or dict(active_authority_projection)
            != self._active_authority_projection
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_ACTIVE_AUTHORITY_DRIFT"
            )
        required_current = {
            "active_authority_projection",
            "timeframe_context_state",
            "agent_market_graph_view",
            "cycle_source_admission",
        }
        if not required_current.issubset(current_artifacts) or not required_current.issubset(
            current_bindings
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_CURRENT_SET_INCOMPLETE"
            )
        if (
            dict(current_artifacts["active_authority_projection"])
            != self._active_authority_projection
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_ACTIVE_AUTHORITY_DRIFT"
            )
        support_documents = {
            **deepcopy(self._supports),
            "active_authority_projection": deepcopy(
                dict(active_authority_projection)
            ),
            "experiment_contract": deepcopy(
                self._authority_documents["experiment_contract"]
            ),
            "timeframe_context_state": deepcopy(
                dict(current_artifacts["timeframe_context_state"])
            ),
            "agent_market_graph_view": deepcopy(
                dict(current_artifacts["agent_market_graph_view"])
            ),
            "cycle_source_admission": deepcopy(
                dict(current_artifacts["cycle_source_admission"])
            ),
        }
        support_bindings = {
            **deepcopy(self._support_bindings),
            "active_authority_projection": _binding(
                current_bindings["active_authority_projection"],
                code="V32_ANALYSIS_MATERIAL_CURRENT_BINDING_INVALID",
                schema_id=PROPOSAL_SUPPORT_SPECS[
                    "active_authority_projection"
                ][0],
                digest_field=PROPOSAL_SUPPORT_SPECS[
                    "active_authority_projection"
                ][1],
            ),
            "experiment_contract": _binding(
                self._authority_documents["authority"][
                    "experiment_contract_binding"
                ],
                code="V32_ANALYSIS_MATERIAL_CONTRACT_BINDING_INVALID",
                schema_id=EXPERIMENT_CONTRACT_SCHEMA_ID,
                digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
            ),
            "timeframe_context_state": _binding(
                current_bindings["timeframe_context_state"],
                code="V32_ANALYSIS_MATERIAL_CURRENT_BINDING_INVALID",
                schema_id=PROPOSAL_SUPPORT_SPECS["timeframe_context_state"][0],
                digest_field=PROPOSAL_SUPPORT_SPECS[
                    "timeframe_context_state"
                ][1],
            ),
            "agent_market_graph_view": _binding(
                current_bindings["agent_market_graph_view"],
                code="V32_ANALYSIS_MATERIAL_CURRENT_BINDING_INVALID",
                schema_id=PROPOSAL_SUPPORT_SPECS["agent_market_graph_view"][0],
                digest_field=PROPOSAL_SUPPORT_SPECS[
                    "agent_market_graph_view"
                ][1],
            ),
            "cycle_source_admission": _binding(
                current_bindings["cycle_source_admission"],
                code="V32_ANALYSIS_MATERIAL_CURRENT_BINDING_INVALID",
                schema_id=PROPOSAL_SUPPORT_SPECS["cycle_source_admission"][0],
                digest_field=PROPOSAL_SUPPORT_SPECS[
                    "cycle_source_admission"
                ][1],
            ),
        }
        if set(support_documents) != set(PROPOSAL_SUPPORT_SPECS) or set(
            support_bindings
        ) != set(PROPOSAL_SUPPORT_SPECS):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_PROPOSAL_SUPPORT_SET_INVALID"
            )

        previous_dynamic = previous_artifacts.get("dynamic_state")
        previous_action = previous_artifacts.get("action_plan")
        previous_timeframe = previous_artifacts.get("timeframe_context")
        packet = build_v32_proposal_canonical_packet_v1(
            run_id=run_id,
            cycle_index=cycle,
            context_profile=self._context_profile,
            context_mode="FULL_CONTEXT" if cycle == 1 else "DELTA_CONTEXT",
            prepared_at=decision_time,
            decision_time=decision_time,
            authority_document=self._authority_documents["authority"],
            authority_binding=active_authority_projection[
                "governing_authority_binding"
            ],
            theory_semantic_document=self._theory,
            theory_semantic_document_binding=self._theory_binding,
            support_documents=support_documents,
            support_bindings=support_bindings,
            previous_dynamic_research_state=previous_dynamic,
            previous_dynamic_research_state_binding=previous_bindings.get(
                "dynamic_state"
            ),
            previous_dynamic_action_plan=previous_action,
            previous_dynamic_action_plan_binding=previous_bindings.get(
                "action_plan"
            ),
            previous_timeframe_context_state=previous_timeframe,
            previous_timeframe_context_state_binding=previous_bindings.get(
                "timeframe_context"
            ),
            matured_outcome_receipts=list(matured_outcome_receipts),
            matured_outcome_receipt_bindings=list(
                matured_outcome_receipt_bindings
            ),
        )
        verify_v32_proposal_canonical_packet_v1(packet)
        return packet

    def lossless_context_package(
        self,
        *,
        stage: str,
        canonical_packet: Mapping[str, Any],
        canonical_packet_binding: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Return ``None`` for INLINE or fail immediately at its hard cap.

        The prospective production lane is INLINE-only.  It must never enter
        the expensive all-shard construction path while holding an analysis
        permit; an oversized packet retains the canonical lifecycle error.
        """

        return self._lossless_context_package_v1(
            stage=stage,
            canonical_packet=canonical_packet,
            canonical_packet_binding=canonical_packet_binding,
            future_unqualified_sharded=False,
        )

    def _future_unqualified_sharded_context_package_v1(
        self,
        *,
        stage: str,
        canonical_packet: Mapping[str, Any],
        canonical_packet_binding: Mapping[str, Any],
        acknowledge_future_unqualified: bool,
    ) -> Mapping[str, Any] | None:
        """Exercise unqualified sharding mechanics outside production only."""

        if acknowledge_future_unqualified is not True:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_FUTURE_SHARDING_NOT_ACKNOWLEDGED"
            )
        return self._lossless_context_package_v1(
            stage=stage,
            canonical_packet=canonical_packet,
            canonical_packet_binding=canonical_packet_binding,
            future_unqualified_sharded=True,
        )

    def _lossless_context_package_v1(
        self,
        *,
        stage: str,
        canonical_packet: Mapping[str, Any],
        canonical_packet_binding: Mapping[str, Any],
        future_unqualified_sharded: bool,
    ) -> Mapping[str, Any] | None:
        if stage not in {"PROPOSAL", "SELECTION"}:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_CONTEXT_STAGE_INVALID"
            )
        packet = deepcopy(dict(canonical_packet))
        schema_id, digest_field = (
            (PROPOSAL_PACKET_SCHEMA_ID, PROPOSAL_PACKET_DIGEST_FIELD)
            if stage == "PROPOSAL"
            else (SELECTION_PACKET_SCHEMA_ID, SELECTION_PACKET_DIGEST_FIELD)
        )
        packet_binding = _document_binding(
            document=packet,
            supplied=canonical_packet_binding,
            schema_id=schema_id,
            digest_field=digest_field,
            code="V32_ANALYSIS_MATERIAL_PACKET_BINDING_INVALID",
        )
        try:
            build_v32_agent_input_context_v1(
                agent_stage=stage,
                canonical_packet=packet,
                canonical_packet_binding=packet_binding,
                created_at=packet["prepared_at"],
            )
            return None
        except V32AgentLifecycleError as exc:
            if str(exc) != "CONTEXT_CAPACITY_UNRESOLVED":
                raise V32AnalysisMaterialAdapterError(
                    "V32_ANALYSIS_MATERIAL_PACKET_INVALID"
                ) from exc
            if not future_unqualified_sharded:
                raise V32AnalysisMaterialAdapterError(
                    "CONTEXT_CAPACITY_UNRESOLVED"
                ) from exc

        policy = self._supports["context_compaction_policy"]
        verify_v32_context_compaction_policy_v1(policy)
        bundle = build_v32_context_compaction_bundle_v1(
            run_id=packet["run_id"],
            cycle_index=packet["cycle_index"],
            created_at=packet["prepared_at"],
            source_artifacts=[
                {
                    "artifact_binding": packet_binding,
                    "canonical_bytes": len(canonical_bytes(packet)),
                }
            ],
            original_documents=[packet],
            max_shard_canonical_bytes=policy["max_shard_canonical_bytes"],
            max_manifest_canonical_bytes=policy[
                "max_manifest_canonical_bytes"
            ],
        )
        root = (
            f"v32-dynamic-agent-context/cycles/{packet['cycle_index']:04d}/"
            f"{stage.lower()}/lossless"
        )
        manifest_binding = _embedded_binding(
            relative_ref=f"{root}/manifest.json",
            document=bundle["manifest"],
            schema_id=CONTEXT_MANIFEST_SCHEMA_ID,
            digest_field=CONTEXT_MANIFEST_DIGEST_FIELD,
        )
        shard_bindings = [
            _embedded_binding(
                relative_ref=f"{root}/shards/{index:04d}.json",
                document=shard,
                schema_id=CONTEXT_SHARD_SCHEMA_ID,
                digest_field=CONTEXT_SHARD_DIGEST_FIELD,
            )
            for index, shard in enumerate(bundle["shards"])
        ]
        selection = build_v32_context_shard_selection_v1(
            manifest=bundle["manifest"],
            manifest_binding=manifest_binding,
            shards=bundle["shards"],
            original_documents=[packet],
            caller_required_member_ids=[],
            selected_at=packet["prepared_at"],
            max_agent_context_canonical_bytes=min(
                policy["max_agent_context_canonical_bytes"],
                MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES,
            ),
            shard_bindings=shard_bindings,
        )
        if selection.get("selection_status") != (
            "READY_FORCED_ALL_SHARDS_SEQUENTIAL"
        ):
            raise V32AnalysisMaterialAdapterError("CONTEXT_CAPACITY_UNRESOLVED")
        selection_binding = _embedded_binding(
            relative_ref=f"{root}/selection.json",
            document=selection,
            schema_id=CONTEXT_SELECTION_SCHEMA_ID,
            digest_field=CONTEXT_SELECTION_DIGEST_FIELD,
        )
        package = {
            "manifest": bundle["manifest"],
            "shards": bundle["shards"],
            "original_documents": [packet],
            "selection": selection,
            "manifest_binding": manifest_binding,
            "shard_bindings": shard_bindings,
            "selection_binding": selection_binding,
        }
        context = build_v32_agent_input_context_v1(
            agent_stage=stage,
            canonical_packet=packet,
            canonical_packet_binding=packet_binding,
            created_at=packet["prepared_at"],
            lossless_context_package=package,
        )
        verify_v32_agent_input_context_v1(
            context, lossless_context_package=package
        )
        return package

    def build_authorized_revision_cycle_registry(
        self,
        *,
        permit: Mapping[str, Any],
        proposal_packet: Mapping[str, Any],
        proposal_context_package: Mapping[str, Any] | None,
        selection_packet: Mapping[str, Any],
        selection_context_package: Mapping[str, Any] | None,
        required_data_gap_escalations: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        run_id, cycle, _ = _permit_identity(permit)
        try:
            verify_v32_proposal_canonical_packet_v1(proposal_packet)
            verify_v32_selection_canonical_packet_v1(selection_packet)
        except (TypeError, ValueError) as exc:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_PACKET_INVALID"
            ) from exc
        if any(
            packet.get("run_id") != run_id
            or packet.get("cycle_index") != cycle
            for packet in (proposal_packet, selection_packet)
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_SCOPE_INVALID"
            )
        if (
            self._revision_reader is None
            or self._revision_reader_binding is None
            or not callable(self._revision_observation_clock)
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_READER_REQUIRED"
            )
        observed_at = _time(
            self._revision_observation_clock(),
            "V32_ANALYSIS_MATERIAL_REVISION_OBSERVED_AT_INVALID",
        )
        try:
            supplied = self._revision_reader.read_cycle_revision_material(
                run_id=run_id,
                cycle_index=cycle,
                proposal_packet=deepcopy(dict(proposal_packet)),
                selection_packet=deepcopy(dict(selection_packet)),
                observed_at=observed_at,
            )
        except Exception:
            supplied = {
                "revision_input_state": build_v32_revision_input_state_v1(
                    run_id=run_id,
                    cycle_index=cycle,
                    state="UNKNOWN_READER_UNAVAILABLE",
                    observed_at=observed_at,
                    reason="REVISION_READER_CALL_FAILED",
                    reader_binding=self._revision_reader_binding,
                ),
                "unknown_tracks": [],
                "manual_evidence_entries": [],
                "recovery_traces": [],
            }
        if not isinstance(supplied, Mapping) or set(supplied) != _REVISION_READER_FIELDS:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_READER_RESULT_INVALID"
            )
        revision_input_state = deepcopy(dict(supplied["revision_input_state"]))
        try:
            verify_v32_revision_input_state_v1(
                revision_input_state,
                expected_run_id=run_id,
                expected_cycle_index=cycle,
                expected_observed_at=observed_at,
                expected_reader_binding=self._revision_reader_binding,
            )
        except (TypeError, ValueError) as exc:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_INPUT_STATE_INVALID"
            ) from exc
        reader_material: dict[str, list[Mapping[str, Any]]] = {}
        for name in sorted(_REVISION_READER_FIELDS - {"revision_input_state"}):
            value = supplied[name]
            if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
                raise V32AnalysisMaterialAdapterError(
                    "V32_ANALYSIS_MATERIAL_REVISION_READER_RESULT_INVALID"
                )
            reader_material[name] = [deepcopy(dict(row)) for row in value]
        reader_item_count = sum(len(rows) for rows in reader_material.values())
        if (
            revision_input_state["state"] == "PRESENT" and reader_item_count == 0
        ) or (
            revision_input_state["state"] != "PRESENT" and reader_item_count != 0
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_REVISION_INPUT_STATE_MATERIAL_MISMATCH"
            )

        data_gap_entries = []
        for index, escalation in enumerate(required_data_gap_escalations):
            document = deepcopy(dict(escalation))
            try:
                verify_v32_data_gap_escalation_v1(document)
            except (TypeError, ValueError) as exc:
                raise V32AnalysisMaterialAdapterError(
                    "V32_ANALYSIS_MATERIAL_DATA_GAP_INVALID"
                ) from exc
            data_gap_entries.append(
                {
                    "escalation": document,
                    "escalation_binding": _embedded_binding(
                        relative_ref=(
                            f"v32-authorized-revision/cycles/{cycle:04d}/"
                            f"data-gaps/{index:04d}.json"
                        ),
                        document=document,
                        schema_id=ESCALATION_SCHEMA_ID,
                        digest_field=ESCALATION_DIGEST_FIELD,
                    ),
                }
            )
        inputs = {
            "proposal_context": (
                None
                if proposal_context_package is None
                else deepcopy(dict(proposal_context_package))
            ),
            "selection_context": (
                None
                if selection_context_package is None
                else deepcopy(dict(selection_context_package))
            ),
            "unknown_tracks": reader_material["unknown_tracks"],
            "data_gap_entries": data_gap_entries,
            "manual_evidence_entries": reader_material[
                "manual_evidence_entries"
            ],
            "environment_conformance": {
                "profile": deepcopy(
                    self._supports["environment_capability_profile"]
                ),
                "profile_binding": deepcopy(
                    self._support_bindings["environment_capability_profile"]
                ),
            },
            "recovery_traces": reader_material["recovery_traces"],
            "revision_input_state": revision_input_state,
        }
        registry = build_v32_authorized_revision_cycle_registry_v1(
            registry_id=f"v32-authorized-revision:{run_id}:{cycle:04d}",
            run_id=run_id,
            cycle_index=cycle,
            created_at=observed_at,
            **inputs,
        )
        verify_v32_authorized_revision_cycle_registry_v1(registry, **inputs)
        return {"cycle_registry": registry, **inputs}

    def build_outcome_schedule_set(
        self,
        *,
        permit: Mapping[str, Any],
        final_dynamic_action_plan: Mapping[str, Any],
        proposal_packet: Mapping[str, Any],
        decision_sealed_at: str,
    ) -> Mapping[str, Any]:
        run_id, cycle, source_cutoff_at = _permit_identity(permit)
        decision_time = _time(
            decision_sealed_at,
            "V32_ANALYSIS_MATERIAL_DECISION_SEALED_TIME_INVALID",
        )
        try:
            verify_v32_proposal_canonical_packet_v1(proposal_packet)
            plan_digest = verify_self_digest(
                final_dynamic_action_plan, "dynamic_action_plan_digest"
            )
        except (TypeError, ValueError) as exc:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_SCHEDULE_INPUT_INVALID"
            ) from exc
        if (
            proposal_packet.get("run_id") != run_id
            or proposal_packet.get("cycle_index") != cycle
            or final_dynamic_action_plan.get("run_id") != run_id
            or final_dynamic_action_plan.get("cycle_index") != cycle
            or _moment(decision_time, "V32_ANALYSIS_MATERIAL_DECISION_SEALED_TIME_INVALID")
            < _moment(source_cutoff_at, "V32_ANALYSIS_MATERIAL_DECISION_SEALED_TIME_INVALID")
        ):
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_SCHEDULE_SCOPE_INVALID"
            )
        schedule = build_v32_outcome_schedule_set(
            run_id=run_id,
            decision_id=(
                f"decision:{run_id}:{cycle:04d}:{plan_digest[:16]}"
            ),
            cycle_index=cycle,
            decision_time=decision_time,
            scheduled_at=decision_time,
            sealed_decision_digest=plan_digest,
            evaluation_contract_digest=proposal_packet["support_documents"]
            ["experiment_contract"]["support_bindings"]
            ["evaluation_contract_digest"],
        )
        verify_v32_outcome_schedule_set(schedule)
        if [row["horizon"] for row in schedule["schedules"]] != [
            "15M",
            "1H",
            "4H",
        ]:
            raise V32AnalysisMaterialAdapterError(
                "V32_ANALYSIS_MATERIAL_SCHEDULE_HORIZON_INVALID"
            )
        return schedule


def _read_current_v32_strategy_agent_request_v1(
    *,
    mailbox: LocalV32CurrentRootAgentMailbox,
    run_id: str,
    cycle_index: int,
) -> Mapping[str, Any] | None:
    """Return one bounded current-Codex presentation without claiming it."""

    if not isinstance(mailbox, LocalV32CurrentRootAgentMailbox):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_MAILBOX_INVALID"
        )
    pending = mailbox.next_pending_request(
        run_id=run_id, cycle_index=cycle_index
    )
    if pending is None:
        return None
    if pending.get("stage_status") not in {"REQUESTED", "CLAIMED"}:
        return None
    chain = mailbox.load_stage_chain(
        run_id=run_id, cycle_index=cycle_index, stage=pending["stage"]
    )
    checkpoint = mailbox.load_checkpoint(run_id=run_id, cycle_index=cycle_index)
    request = chain["request"]
    packet = chain["canonical_packet_original"]
    package = chain["lossless_context_package"]
    if request.get("context_delivery_mode") != "INLINE" or package is not None:
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_AGENT_PRESENTATION_MODE_NOT_QUALIFIED"
        )
    try:
        verify_v32_agent_input_context_v1(
            request["agent_input_context"],
            **(
                {"lossless_context_package": package}
                if package is not None
                else {}
            ),
        )
        if pending["stage"] == "PROPOSAL":
            verify_v32_proposal_canonical_packet_v1(packet)
        else:
            verify_v32_selection_canonical_packet_v1(packet)
    except (KeyError, TypeError, ValueError) as exc:
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_MAILBOX_REPLAY_INVALID"
        ) from exc
    if (
        pending["request"] != request
        or pending["checkpoint_digest"] != chain["checkpoint_digest"]
        or pending["stage_status"] != chain["stage_status"]
        or pending["ordered_agent_input_delivery_units"]
        != chain["ordered_agent_input_delivery_units"]
        or request["agent_input_context"]["canonical_packet_digest"]
        != packet[
            PROPOSAL_PACKET_DIGEST_FIELD
            if pending["stage"] == "PROPOSAL"
            else SELECTION_PACKET_DIGEST_FIELD
        ]
    ):
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_MAILBOX_CROSS_BINDING_INVALID"
        )
    return build_v32_current_codex_presentation_envelope_v1(
        mailbox_checkpoint=checkpoint,
        request=request,
        claim=chain["claim"],
        lossless_context_package=package,
        control_context={
            "presentation_kind": "READ_ONLY_PENDING_AGENT_REQUEST",
            "stage": pending["stage"],
            "stage_status": pending["stage_status"],
            "next_action": pending["next_action"],
            "read_only": True,
        },
    )


def read_current_v32_strategy_agent_request_v1(
    *,
    mailbox: LocalV32CurrentRootAgentMailbox,
    run_id: str,
    cycle_index: int,
) -> Mapping[str, Any] | None:
    """Return one bounded INLINE-only current-Codex presentation.

    Every mailbox replay and presentation-construction failure is normalized
    to this adapter's stable error type.  The read never claims a request or
    mutates the durable mailbox.
    """

    try:
        return _read_current_v32_strategy_agent_request_v1(
            mailbox=mailbox,
            run_id=run_id,
            cycle_index=cycle_index,
        )
    except V32AnalysisMaterialAdapterError:
        raise
    except Exception as exc:
        raise V32AnalysisMaterialAdapterError(
            "V32_ANALYSIS_MATERIAL_AGENT_PRESENTATION_FAILED"
        ) from exc


__all__ = [
    "EmptyV32StrategyRevisionMaterialReader",
    "LocalV32NoRevisionInputMaterialReader",
    "LocalV32AnalysisMaterialAdapter",
    "V32AnalysisMaterialAdapterError",
    "V32StrategyRevisionMaterialReader",
    "read_current_v32_strategy_agent_request_v1",
]
