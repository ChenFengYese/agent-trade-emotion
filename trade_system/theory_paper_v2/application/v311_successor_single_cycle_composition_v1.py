"""Minimal V3.1.1 glue for one recoverable successor research cycle.

This module composes existing, separately tested owners.  It does not replace
their state machines and it never invokes an Agent or observes an outcome.

Preparation projects the target five-document authority through an injected
full-loader boundary, initializes the target genesis/monitor/supervisor,
opens one permit, admits an already completed fresh public qualification,
persists the run-local twelve-axis projection and immutable support documents,
then initializes the existing one-attempt Agent transport.

Commit first freezes the existing successor commit material.  Re-entry with a
material already present replays only local support bytes and the deterministic
commit tail, so neither an Agent nor an outcome adapter can be called twice.
"""

from __future__ import annotations

import copy
import hashlib
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence

from .ports import V31MonitorStorePort, V31ResearchStorePort
from .v31_agent_transport import (
    V31AgentTransportStorePort,
    initialize_v31_agent_transport,
    run_v31_authoring_transport,
    verify_completed_v31_authoring_transport,
)
from .v31_cycle_source_admission import (
    V31SourceQualificationStorePort,
    admit_fresh_v31_source_to_authorized_cycle,
)
from .v31_experiment_supervisor_v2 import (
    V31SupervisorStoreV2Port,
    complete_v31_experiment_supervisor_v2,
    fail_v31_experiment_supervisor_v2,
    initialize_v31_experiment_supervisor_v2,
    open_v31_cycle_permit_v2,
    verify_v31_cycle_permit_live_v2,
)
from .v31_formal_cycle import prepare_v31_formal_authoring_cycle
from .v31_monitor_runtime import initialize_v31_monitor_runtime
from .v31_monitor_runtime import v31_monitor_status
from .v31_outcome_resolution_v2 import (
    V31OutcomeEvidenceStorePortV2,
    V31PublicOutcomeCapturePortV2,
    initialize_v31_outcome_evidence_runtime_v2,
    resolve_due_v31_monitor_v2,
)
from .v31_run_genesis import initialize_v31_run_genesis
from .v31_sentiment_projection_composition_v2 import (
    V31SentimentProjectionOutputStoreV2,
    compose_and_persist_v31_sentiment_projection_v2,
)
from .v31_successor_cycle_commit_v2 import (
    V31SuccessorCommitStoreV2Port,
    commit_or_recover_v31_successor_cycle_v2,
    persist_v31_successor_commit_material_v2,
    prepare_v31_successor_cycle_commit_material_v2,
)
from ..domain.contracts.canonical import self_digest, verify_self_digest
from ..domain.governance.v31_application_authority_projection_v2 import (
    V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS,
)
from ..domain.governance.v31_successor_qualification_v2 import (
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
    verify_successor_monitor_qualification_v2,
    verify_successor_public_source_qualification_v2,
)
from ..domain.governance.v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    verify_successor_codex_durable_qualification_v3,
)
from ..domain.governance.v311_successor_authority_envelope_v2 import (
    ENVELOPE_DIGEST_FIELD,
    ENVELOPE_SCHEMA_ID,
    RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD,
    RUNTIME_CLOSURE_RECEIPT_SCHEMA_ID,
    SUPERVISOR_POLICY_DIGEST_FIELD,
    SUPERVISOR_POLICY_SCHEMA_ID,
    V311_FRESH_QUALIFICATION_KEYS,
    verify_v311_runtime_closure_receipt_v2,
    verify_v311_supervisor_policy_v2,
)
from ..domain.v311_agent_lifecycle_v1 import (
    AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    V311_TARGET_AGENT_SUPPORT_KEYS,
    V311_TARGET_AGENT_SUPPORT_SPECS,
    V311_TARGET_CONTEXT_PROFILE,
    V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
    agent_context_consumption_ref_v1,
    agent_input_context_ref_v1,
    build_v311_agent_context_consumption_v1,
    build_v311_agent_input_context_v1,
    build_v311_successor_commit_envelope_v1,
    build_v311_theory_addendum_semantic_document_v1,
    successor_commit_envelope_ref_v1,
    verify_v311_agent_input_context_with_packet_v1,
    verify_v311_successor_commit_envelope_full_v1,
)
from ..domain.v31_association_preregistration_v2 import (
    verify_v31_association_preregistration_v2,
)
from ..domain.v31_evaluation_contract_v2 import (
    verify_v31_evaluation_contract_v2,
)
from ..domain.v31_experiment_contracts import FrozenMonitorRule
from ..domain.v31_experiment_supervisor_v2 import cycle_permit_ref_v2
from ..domain.v31_outcome_capture_v2 import verify_outcome_clock_policy
from ..domain.v31_run_genesis import (
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_REF,
    RUN_GENESIS_SCHEMA_ID,
    verify_v31_run_genesis_receipt,
)
from ..domain.v31_sentiment_native_projection_v2 import (
    verify_v31_native_sentiment_source_registry,
)
from ..domain.v31_successor_cycle_commit_v2 import (
    DIGEST_FIELD as COMMIT_MATERIAL_DIGEST_FIELD,
    SUPPORT_BINDING_KEYS,
    successor_commit_material_ref_v2,
)
from ..infrastructure.v31_sentiment_projection_store_v2 import (
    sentiment_projection_receipt_ref_v2,
    sentiment_source_registry_ref_v2,
)


class V311SuccessorSingleCycleV1Error(ValueError):
    """The V3.1.1 composition could not preserve its single-cycle boundary."""


class V311TargetAuthorityProjectorV1(Protocol):
    """Injection boundary implemented by the complete successor loader."""

    def __call__(
        self, loaded_context: Mapping[str, Any]
    ) -> Mapping[str, Mapping[str, Any]]: ...


V311_FRESH_QUALIFICATION_BUNDLE_SCHEMA_ID = (
    "theory_paper_v311_run_local_fresh_qualification_bundle_v1"
)
V311_FRESH_QUALIFICATION_BUNDLE_DIGEST_FIELD = (
    "fresh_qualification_bundle_digest"
)
V311_SUPPORT_ROOT_V1 = "successor-v311-support-v1"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_TYPED_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_QUALIFICATION_SPECS = {
    "public_source": (
        SOURCE_QUALIFICATION_DIGEST_FIELD,
        verify_successor_public_source_qualification_v2,
    ),
    "codex_durable_delivery": (
        CODEX_QUALIFICATION_V3_DIGEST_FIELD,
        verify_successor_codex_durable_qualification_v3,
    ),
    "outcome_monitor": (
        MONITOR_QUALIFICATION_DIGEST_FIELD,
        verify_successor_monitor_qualification_v2,
    ),
}
V311_TARGET_SUPPORT_STORE_OWNERS = MappingProxyType(
    {
        name: (
            "projection_run_root"
            if name in {"sentiment_source_registry", "sentiment_projection"}
            else "research_run_root"
        )
        for name in sorted(V311_TARGET_AGENT_SUPPORT_KEYS)
    }
)
_GENESIS_ROLE_FROM_ACTIVE_CHAIN = {
    "theory_approval": "theory_approval",
    "experiment_contract": "experiment_contract",
    "experiment_manifest": "manifest",
    "experiment_authorization": "authorization_receipt",
    "current_authority": "authority",
}


def _cycle(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 8
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_INDEX_INVALID"
        )
    return value


def _support_ref(cycle_index: int, name: str) -> str:
    cycle = _cycle(cycle_index)
    if not isinstance(name, str) or not name or "/" in name or "\\" in name:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SUPPORT_NAME_INVALID"
        )
    return f"{V311_SUPPORT_ROOT_V1}/cycles/{cycle:04d}/{name}.json"


def _assert_typed_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _TYPED_BINDING_FIELDS:
        raise V311SuccessorSingleCycleV1Error(code)
    result = {field: str(value[field]) for field in _TYPED_BINDING_FIELDS}
    if (
        any(
            not result[field]
            for field in ("relative_ref", "schema_id", "digest_field")
        )
        or _HEX_64.fullmatch(result["semantic_digest"]) is None
        or _HEX_64.fullmatch(result["physical_sha256"]) is None
    ):
        raise V311SuccessorSingleCycleV1Error(code)
    return result


def _project_target(
    *,
    loaded_context: Mapping[str, Any],
    authority_projector: V311TargetAuthorityProjectorV1,
    run_id: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(loaded_context, Mapping):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_LOADED_CONTEXT_INVALID"
        )
    try:
        projected = authority_projector(loaded_context)
    except Exception as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_FULL_LOADER_PROJECTION_FAILED"
        ) from exc
    if (
        not isinstance(projected, Mapping)
        or tuple(projected) != V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
        or any(not isinstance(projected.get(name), Mapping) for name in projected)
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_TARGET_PROJECTION_INVALID"
        )
    result = {
        name: copy.deepcopy(dict(projected[name]))
        for name in V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
    }
    if (
        result["experiment_contract"].get("run_id") != run_id
        or result["manifest"].get("run_id") != run_id
        or result["authority"].get("authorized_run_id") != run_id
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_TARGET_RUN_ID_MISMATCH"
        )
    return result


def _genesis_role_projection(
    *,
    target_documents: Mapping[str, Mapping[str, Any]],
    target_global_bindings: Mapping[str, Mapping[str, Any]],
    target_global_raw_bytes: Mapping[str, bytes] | None = None,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, bytes] | None,
]:
    """Translate standard active-chain names only at the genesis boundary."""

    active_keys = set(V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS)
    if (
        not isinstance(target_documents, Mapping)
        or set(target_documents) != active_keys
        or not isinstance(target_global_bindings, Mapping)
        or set(target_global_bindings) != active_keys
        or (
            target_global_raw_bytes is not None
            and (
                not isinstance(target_global_raw_bytes, Mapping)
                or set(target_global_raw_bytes) != active_keys
                or any(
                    not isinstance(value, bytes)
                    for value in target_global_raw_bytes.values()
                )
            )
        )
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_GENESIS_ROLE_INPUT_INVALID"
        )
    documents = {
        genesis_role: copy.deepcopy(
            dict(target_documents[active_role])
        )
        for genesis_role, active_role in _GENESIS_ROLE_FROM_ACTIVE_CHAIN.items()
    }
    bindings = {
        genesis_role: copy.deepcopy(
            dict(target_global_bindings[active_role])
        )
        for genesis_role, active_role in _GENESIS_ROLE_FROM_ACTIVE_CHAIN.items()
    }
    raw_bytes = (
        None
        if target_global_raw_bytes is None
        else {
            genesis_role: target_global_raw_bytes[active_role]
            for genesis_role, active_role in _GENESIS_ROLE_FROM_ACTIVE_CHAIN.items()
        }
    )
    return documents, bindings, raw_bytes


def _typed_existing_document(
    *,
    store: V31ResearchStorePort | V31SentimentProjectionOutputStoreV2,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
    expected_semantic_digest: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        document = store.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        raw_binding = store.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        semantic = verify_self_digest(document, digest_field)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SUPPORT_READBACK_FAILED"
        ) from exc
    binding = {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": str(raw_binding.get("physical_sha256") or ""),
    }
    if (
        document.get("schema_id") != schema_id
        or raw_binding.get("relative_ref") != relative_ref
        or raw_binding.get("semantic_digest") != semantic
        or raw_binding.get("schema_id", schema_id) != schema_id
        or raw_binding.get("digest_field", digest_field) != digest_field
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SUPPORT_BINDING_DRIFT"
        )
    return dict(document), _assert_typed_binding(
        binding, "V311_SINGLE_CYCLE_SUPPORT_BINDING_INVALID"
    )


def _persist_document(
    *,
    store: V31ResearchStorePort,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    try:
        semantic = verify_self_digest(document, digest_field)
        store.write_document(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SUPPORT_WRITE_FAILED"
        ) from exc
    _document, binding = _typed_existing_document(
        store=store,
        relative_ref=relative_ref,
        schema_id=str(document["schema_id"]),
        digest_field=digest_field,
        expected_semantic_digest=semantic,
    )
    if _document != dict(document):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SUPPORT_READBACK_DRIFT"
        )
    return binding


def _validate_loaded_support_documents(
    loaded_context: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        clock = loaded_context["clock_policy"]
        supervisor_policy = loaded_context["supervisor_policy"]
        runtime_closure = loaded_context["runtime_closure"]
        theory_addendum_binding = loaded_context["theory_addendum_binding"]
        registry = loaded_context["sentiment_source_registry"]
        association = loaded_context["association_preregistration"]
        evaluation = loaded_context["evaluation_contract"]
        qualifications = loaded_context["successor_qualifications"]
        envelope = loaded_context["envelope"]
        verify_outcome_clock_policy(clock)
        verify_v311_supervisor_policy_v2(supervisor_policy)
        verify_v311_runtime_closure_receipt_v2(runtime_closure)
        verify_v31_native_sentiment_source_registry(registry)
        verify_v31_association_preregistration_v2(association)
        verify_v31_evaluation_contract_v2(evaluation, association)
        envelope_digest = verify_self_digest(envelope, ENVELOPE_DIGEST_FIELD)
    except (KeyError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_LOADED_SUPPORT_INVALID"
        ) from exc
    if (
        envelope.get("schema_id") != ENVELOPE_SCHEMA_ID
        or not isinstance(qualifications, Mapping)
        or tuple(qualifications) != V311_FRESH_QUALIFICATION_KEYS
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_LOADED_SUPPORT_INVALID"
        )
    qualification_digests: dict[str, str] = {}
    try:
        for name in V311_FRESH_QUALIFICATION_KEYS:
            digest_field, verifier = _QUALIFICATION_SPECS[name]
            document = qualifications[name]
            qualification_digests[name] = verifier(document)
            if document.get(digest_field) != qualification_digests[name]:
                raise ValueError("qualification digest mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_FRESH_QUALIFICATION_INVALID"
        ) from exc
    envelope_bindings = envelope.get("fresh_qualification_bindings")
    if not isinstance(envelope_bindings, Mapping):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_FRESH_QUALIFICATION_BINDING_INVALID"
        )
    for name, digest in qualification_digests.items():
        binding = envelope_bindings.get(name)
        if (
            not isinstance(binding, Mapping)
            or binding.get("semantic_digest") != digest
            or binding.get("digest_field") != _QUALIFICATION_SPECS[name][0]
        ):
            raise V311SuccessorSingleCycleV1Error(
                "V311_SINGLE_CYCLE_FRESH_QUALIFICATION_BINDING_INVALID"
            )
    return {
        "clock_policy": dict(clock),
        "supervisor_policy": dict(supervisor_policy),
        "runtime_closure": dict(runtime_closure),
        "theory_addendum_binding": dict(theory_addendum_binding),
        "sentiment_source_registry": dict(registry),
        "association_preregistration": dict(association),
        "evaluation_contract": dict(evaluation),
        "successor_qualifications": {
            name: dict(qualifications[name])
            for name in V311_FRESH_QUALIFICATION_KEYS
        },
        "envelope": dict(envelope),
        "envelope_digest": envelope_digest,
        "qualification_digests": qualification_digests,
    }


def _persist_static_supports(
    *,
    research_store: V31ResearchStorePort,
    loaded_support: Mapping[str, Any],
    run_id: str,
    cycle_index: int,
    authority_projection_binding: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    clock = loaded_support["clock_policy"]
    association = loaded_support["association_preregistration"]
    evaluation = loaded_support["evaluation_contract"]
    result = {
        "clock_policy": _persist_document(
            store=research_store,
            relative_ref=_support_ref(cycle_index, "clock-policy"),
            document=clock,
            digest_field="clock_policy_digest",
        ),
        "association_preregistration": _persist_document(
            store=research_store,
            relative_ref=_support_ref(
                cycle_index, "association-preregistration"
            ),
            document=association,
            digest_field="association_preregistration_digest",
        ),
        "evaluation_contract": _persist_document(
            store=research_store,
            relative_ref=_support_ref(cycle_index, "evaluation-contract"),
            document=evaluation,
            digest_field="evaluation_contract_digest",
        ),
        "supervisor_policy": _persist_document(
            store=research_store,
            relative_ref=_support_ref(cycle_index, "supervisor-policy"),
            document=loaded_support["supervisor_policy"],
            digest_field=SUPERVISOR_POLICY_DIGEST_FIELD,
        ),
        "runtime_closure": _persist_document(
            store=research_store,
            relative_ref=_support_ref(cycle_index, "runtime-closure"),
            document=loaded_support["runtime_closure"],
            digest_field=RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD,
        ),
    }
    envelope_binding = _persist_document(
        store=research_store,
        relative_ref=_support_ref(cycle_index, "successor-authority-envelope"),
        document=loaded_support["envelope"],
        digest_field=ENVELOPE_DIGEST_FIELD,
    )
    result["successor_authority_envelope"] = envelope_binding
    qualification_bindings: dict[str, dict[str, str]] = {}
    for name in V311_FRESH_QUALIFICATION_KEYS:
        digest_field, _verifier = _QUALIFICATION_SPECS[name]
        qualification_bindings[name] = _persist_document(
            store=research_store,
            relative_ref=_support_ref(cycle_index, f"qualification-{name}"),
            document=loaded_support["successor_qualifications"][name],
            digest_field=digest_field,
        )
    result["qualification_public_source"] = qualification_bindings[
        "public_source"
    ]
    result["qualification_codex_durable_delivery"] = (
        qualification_bindings["codex_durable_delivery"]
    )
    result["qualification_outcome_monitor"] = qualification_bindings[
        "outcome_monitor"
    ]
    bundle = self_digest(
        {
            "schema_id": V311_FRESH_QUALIFICATION_BUNDLE_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "successor_authority_envelope_binding": envelope_binding,
            "qualification_bindings": qualification_bindings,
            "qualification_digests": dict(
                loaded_support["qualification_digests"]
            ),
            "full_successor_loader_required": True,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        V311_FRESH_QUALIFICATION_BUNDLE_DIGEST_FIELD,
    )
    result["fresh_qualification_bundle"] = _persist_document(
        store=research_store,
        relative_ref=_support_ref(cycle_index, "fresh-qualification-bundle"),
        document=bundle,
        digest_field=V311_FRESH_QUALIFICATION_BUNDLE_DIGEST_FIELD,
    )
    result["application_authority_projection"] = _assert_typed_binding(
        authority_projection_binding,
        "V311_SINGLE_CYCLE_AUTHORITY_PROJECTION_BINDING_INVALID",
    )
    return result


def _run_genesis_binding(
    *,
    research_store: V31ResearchStorePort,
    target_documents: Mapping[str, Mapping[str, Any]],
    target_global_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    genesis_documents, genesis_bindings, _raw = _genesis_role_projection(
        target_documents=target_documents,
        target_global_bindings=target_global_bindings,
    )
    receipt, binding = _typed_existing_document(
        store=research_store,
        relative_ref=RUN_GENESIS_REF,
        schema_id=RUN_GENESIS_SCHEMA_ID,
        digest_field=RUN_GENESIS_DIGEST_FIELD,
    )
    try:
        verify_v31_run_genesis_receipt(
            receipt,
            documents=genesis_documents,
            global_bindings=genesis_bindings,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_AUTHORITY_PROJECTION_REPLAY_FAILED"
        ) from exc
    return binding


def _sentiment_bindings(
    *,
    projection_store: V31SentimentProjectionOutputStoreV2,
    loaded_registry: Mapping[str, Any],
    cycle_index: int,
) -> dict[str, dict[str, str]]:
    registry, registry_binding = _typed_existing_document(
        store=projection_store,
        relative_ref=sentiment_source_registry_ref_v2(cycle_index),
        schema_id="theory_paper_v2_v31_native_sentiment_source_registry",
        digest_field="registry_digest",
    )
    if registry != dict(loaded_registry):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SENTIMENT_REGISTRY_DRIFT"
        )
    receipt, receipt_binding = _typed_existing_document(
        store=projection_store,
        relative_ref=sentiment_projection_receipt_ref_v2(cycle_index),
        schema_id=(
            "theory_paper_v2_v31_sentiment_native_projection_receipt"
        ),
        digest_field="projection_receipt_digest",
    )
    if (
        receipt.get("cycle_index") != cycle_index
        or receipt.get("native_source_registry_digest")
        != registry.get("registry_digest")
        or any(
            row.get("ordinal_value") is not None
            for row in receipt.get("projection", {}).get(
                "axis_projections", []
            )
        )
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SENTIMENT_PROJECTION_INVALID"
        )
    return {
        "sentiment_source_registry": registry_binding,
        "sentiment_projection": receipt_binding,
    }


def _recover_support_bindings(
    *,
    research_store: V31ResearchStorePort,
    projection_store: V31SentimentProjectionOutputStoreV2,
    loaded_context: Mapping[str, Any],
    target_documents: Mapping[str, Mapping[str, Any]],
    target_global_bindings: Mapping[str, Mapping[str, Any]],
    run_id: str,
    cycle_index: int,
) -> dict[str, dict[str, str]]:
    loaded_support = _validate_loaded_support_documents(loaded_context)
    authority_binding = _run_genesis_binding(
        research_store=research_store,
        target_documents=target_documents,
        target_global_bindings=target_global_bindings,
    )
    support = _persist_static_supports(
        research_store=research_store,
        loaded_support=loaded_support,
        run_id=run_id,
        cycle_index=cycle_index,
        authority_projection_binding=authority_binding,
    )
    support.update(
        _sentiment_bindings(
            projection_store=projection_store,
            loaded_registry=loaded_support["sentiment_source_registry"],
            cycle_index=cycle_index,
        )
    )
    base_support = {
        name: support[name] for name in sorted(SUPPORT_BINDING_KEYS)
    }
    if set(base_support) != SUPPORT_BINDING_KEYS:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_SUPPORT_SET_INVALID"
        )
    return {
        name: _assert_typed_binding(
        base_support[name], "V311_SINGLE_CYCLE_SUPPORT_BINDING_INVALID"
        )
        for name in sorted(SUPPORT_BINDING_KEYS)
    }


def _target_context_support_set(
    *,
    research_store: V31ResearchStorePort,
    projection_store: V31SentimentProjectionOutputStoreV2,
    loaded_support: Mapping[str, Any],
    cycle_index: int,
    theory_addendum_raw_bytes: bytes,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Load the exact run-local support graph delivered to the root Agent."""

    if not isinstance(theory_addendum_raw_bytes, bytes):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_ADDENDUM_BYTES_REQUIRED"
        )
    try:
        addendum_text = theory_addendum_raw_bytes.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_ADDENDUM_UTF8_INVALID"
        ) from exc
    if hashlib.sha256(theory_addendum_raw_bytes).hexdigest() != str(
        loaded_support["theory_addendum_binding"].get("physical_sha256")
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_ADDENDUM_PHYSICAL_DRIFT"
        )
    try:
        addendum = build_v311_theory_addendum_semantic_document_v1(
            theory_addendum_binding=loaded_support[
                "theory_addendum_binding"
            ],
            markdown_utf8=addendum_text,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_ADDENDUM_SEMANTIC_INVALID"
        ) from exc
    _persist_document(
        store=research_store,
        relative_ref=_support_ref(cycle_index, "theory-addendum-semantic"),
        document=addendum,
        digest_field=V311_TARGET_AGENT_SUPPORT_SPECS["theory_addendum"][1],
    )

    research_refs = {
        "application_authority_projection": RUN_GENESIS_REF,
        "theory_addendum": _support_ref(
            cycle_index, "theory-addendum-semantic"
        ),
        "clock_policy": _support_ref(cycle_index, "clock-policy"),
        "supervisor_policy": _support_ref(cycle_index, "supervisor-policy"),
        "runtime_closure": _support_ref(cycle_index, "runtime-closure"),
        "successor_authority_envelope": _support_ref(
            cycle_index, "successor-authority-envelope"
        ),
        "association_preregistration": _support_ref(
            cycle_index, "association-preregistration"
        ),
        "evaluation_contract": _support_ref(
            cycle_index, "evaluation-contract"
        ),
        "fresh_qualification_bundle": _support_ref(
            cycle_index, "fresh-qualification-bundle"
        ),
        "qualification_public_source": _support_ref(
            cycle_index, "qualification-public_source"
        ),
        "qualification_codex_durable_delivery": _support_ref(
            cycle_index, "qualification-codex_durable_delivery"
        ),
        "qualification_outcome_monitor": _support_ref(
            cycle_index, "qualification-outcome_monitor"
        ),
    }
    projection_refs = {
        "sentiment_source_registry": sentiment_source_registry_ref_v2(
            cycle_index
        ),
        "sentiment_projection": sentiment_projection_receipt_ref_v2(
            cycle_index
        ),
    }
    documents: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, str]] = {}
    for name in sorted(V311_TARGET_AGENT_SUPPORT_KEYS):
        schema_id, digest_field = V311_TARGET_AGENT_SUPPORT_SPECS[name]
        store = (
            projection_store
            if name in projection_refs
            else research_store
        )
        relative_ref = (
            projection_refs[name]
            if name in projection_refs
            else research_refs[name]
        )
        document, binding = _typed_existing_document(
            store=store,
            relative_ref=relative_ref,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        documents[name] = document
        bindings[name] = binding
    return documents, bindings


def _same_binding_semantics(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    return all(
        left.get(field) == right.get(field)
        for field in ("schema_id", "digest_field", "semantic_digest")
    )


def verify_v311_agent_input_context_durable_v1(
    *,
    agent_input_context: Mapping[str, Any],
    base_authoring_packet: Mapping[str, Any],
    research_store: V31ResearchStorePort,
    projection_store: V31SentimentProjectionOutputStoreV2,
) -> str:
    """Replay every inline support from its declared run-root owner.

    ``artifact_binding`` is deliberately called after ``read_document`` so the
    current physical bytes are hashed by the owning store.  A caller cannot
    satisfy this function with only an inline document and a fabricated
    ``physical_sha256`` value.
    """

    try:
        context_digest = verify_v311_agent_input_context_with_packet_v1(
            agent_input_context,
            base_authoring_packet=base_authoring_packet,
        )
        context_documents = agent_input_context["support_documents"]
        context_bindings = agent_input_context["support_bindings"]
        if (
            set(context_documents) != V311_TARGET_AGENT_SUPPORT_KEYS
            or set(context_bindings) != V311_TARGET_AGENT_SUPPORT_KEYS
        ):
            raise ValueError("support set drift")
        for name in sorted(V311_TARGET_AGENT_SUPPORT_KEYS):
            schema_id, digest_field = V311_TARGET_AGENT_SUPPORT_SPECS[name]
            expected = context_bindings[name]
            store = (
                projection_store
                if V311_TARGET_SUPPORT_STORE_OWNERS[name]
                == "projection_run_root"
                else research_store
            )
            durable, observed = _typed_existing_document(
                store=store,
                relative_ref=str(expected["relative_ref"]),
                schema_id=schema_id,
                digest_field=digest_field,
                expected_semantic_digest=str(expected["semantic_digest"]),
            )
            if durable != dict(context_documents[name]) or observed != dict(
                expected
            ):
                raise ValueError(f"support physical drift:{name}")

        envelope = context_documents["successor_authority_envelope"]
        envelope_aux = envelope.get("auxiliary_contract_bindings")
        envelope_qualifications = envelope.get(
            "fresh_qualification_bindings"
        )
        bundle = context_documents["fresh_qualification_bundle"]
        if (
            envelope.get("theory_addendum_binding")
            != agent_input_context.get("theory_addendum_binding")
            or not isinstance(envelope_aux, Mapping)
            or not isinstance(envelope_qualifications, Mapping)
            or bundle.get("successor_authority_envelope_binding")
            != context_bindings["successor_authority_envelope"]
        ):
            raise ValueError("envelope root cross binding drift")
        for name in (
            "clock_policy",
            "supervisor_policy",
            "runtime_closure",
            "sentiment_source_registry",
            "association_preregistration",
            "evaluation_contract",
        ):
            if not _same_binding_semantics(
                envelope_aux.get(name, {}), context_bindings[name]
            ):
                raise ValueError(f"envelope auxiliary drift:{name}")
        qualification_names = {
            "public_source": "qualification_public_source",
            "codex_durable_delivery": (
                "qualification_codex_durable_delivery"
            ),
            "outcome_monitor": "qualification_outcome_monitor",
        }
        bundle_qualifications = bundle.get("qualification_bindings")
        if not isinstance(bundle_qualifications, Mapping):
            raise ValueError("bundle qualification bindings invalid")
        for envelope_name, context_name in qualification_names.items():
            if (
                not _same_binding_semantics(
                    envelope_qualifications.get(envelope_name, {}),
                    context_bindings[context_name],
                )
                or bundle_qualifications.get(envelope_name)
                != context_bindings[context_name]
            ):
                raise ValueError(
                    f"qualification cross binding drift:{envelope_name}"
                )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, V311SuccessorSingleCycleV1Error):
            raise
        raise V311SuccessorSingleCycleV1Error(
            "V311_AGENT_INPUT_DURABLE_REPLAY_FAILED"
        ) from exc
    return context_digest


def run_v311_current_root_authoring_transport_v1(
    *,
    research_store: V31ResearchStorePort,
    projection_store: V31SentimentProjectionOutputStoreV2,
    transport_store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
    owner_id: str,
    lease_acquired_at: str,
    lease_expires_at: str,
    stage_times: Mapping[str, str],
    current_root_agent_call: Callable[
        [Mapping[str, Any]], Mapping[str, Any]
    ],
) -> Mapping[str, Any]:
    """Pass the complete frozen context unchanged to the current root Agent."""

    cycle = _cycle(cycle_index)
    context, context_binding = _typed_existing_document(
        store=research_store,
        relative_ref=agent_input_context_ref_v1(cycle),
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    try:
        packet = transport_store.read_bound_document(
            context["base_authoring_packet_binding"]
        )
        verify_v311_agent_input_context_durable_v1(
            agent_input_context=context,
            base_authoring_packet=packet,
            research_store=research_store,
            projection_store=projection_store,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_CURRENT_ROOT_CONTEXT_PREFLIGHT_FAILED"
        ) from exc

    called = False

    def direct_context_call(_legacy_request: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal called
        if called:
            raise V311SuccessorSingleCycleV1Error(
                "V311_CURRENT_ROOT_AGENT_REINVOCATION_FORBIDDEN"
            )
        called = True
        delivered_context = copy.deepcopy(context)
        result = current_root_agent_call(delivered_context)
        if delivered_context != context:
            raise V311SuccessorSingleCycleV1Error(
                "V311_CURRENT_ROOT_CONTEXT_MUTATED_BY_ADAPTER"
            )
        return result

    try:
        authored = run_v31_authoring_transport(
            store=transport_store,
            run_id=run_id,
            cycle_index=cycle,
            authoring_packet_binding=context[
                "base_authoring_packet_binding"
            ],
            owner_id=owner_id,
            lease_acquired_at=lease_acquired_at,
            lease_expires_at=lease_expires_at,
            stage_times=stage_times,
            agent_call=direct_context_call,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_CURRENT_ROOT_AUTHORING_TRANSPORT_FAILED_CLOSED"
        ) from exc
    if (
        authored.get("status") != "READY_FOR_COMPILATION"
        or called is not True
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_CURRENT_ROOT_AUTHORING_RESULT_INVALID"
        )
    return {
        **dict(authored),
        "agent_input_context_binding": context_binding,
        "direct_context_input_declared_by_controller": True,
        "current_root_role_contract_verified": True,
        "transport_attestation_level": "PRACTICAL_CODEX_NOT_MODEL_ATTESTED",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def persist_v311_agent_context_consumption_from_completed_transport_v1(
    *,
    research_store: V31ResearchStorePort,
    projection_store: V31SentimentProjectionOutputStoreV2,
    transport_store: V31AgentTransportStorePort,
    run_id: str,
    cycle_index: int,
) -> Mapping[str, Any]:
    """Write the fixed-ref consumption only after terminal transport replay."""

    cycle = _cycle(cycle_index)
    context, context_binding = _typed_existing_document(
        store=research_store,
        relative_ref=agent_input_context_ref_v1(cycle),
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    try:
        packet = transport_store.read_bound_document(
            context["base_authoring_packet_binding"]
        )
        verify_v311_agent_input_context_durable_v1(
            agent_input_context=context,
            base_authoring_packet=packet,
            research_store=research_store,
            projection_store=projection_store,
        )
        completed = verify_completed_v31_authoring_transport(
            store=transport_store,
            run_id=run_id,
            cycle_index=cycle,
            expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
        )
        proposal = completed["checkpoint"]["stage_states"]["PROPOSAL"]
        artifacts = {
            name: transport_store.read_bound_document(
                proposal[f"{name}_binding"]
            )
            for name in ("attempt", "request", "claim", "delivery", "consume")
        }
        consumption = build_v311_agent_context_consumption_v1(
            agent_input_context=context,
            agent_input_context_binding=context_binding,
            base_authoring_packet=packet,
            proposal_attempt=artifacts["attempt"],
            proposal_attempt_binding=proposal["attempt_binding"],
            proposal_request=artifacts["request"],
            proposal_request_binding=proposal["request_binding"],
            proposal_claim=artifacts["claim"],
            proposal_delivery=artifacts["delivery"],
            proposal_delivery_binding=proposal["delivery_binding"],
            proposal_consume=artifacts["consume"],
            proposal_consume_binding=proposal["consume_binding"],
            transport_evidence=completed["transport_evidence"],
            transport_evidence_binding=completed[
                "transport_evidence_binding"
            ],
        )
        binding = _persist_document(
            store=research_store,
            relative_ref=agent_context_consumption_ref_v1(cycle),
            document=consumption,
            digest_field=AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, V311SuccessorSingleCycleV1Error):
            raise
        raise V311SuccessorSingleCycleV1Error(
            "V311_AGENT_CONTEXT_CONSUMPTION_PERSIST_FAILED"
        ) from exc
    return {
        "status": "V311_AGENT_CONTEXT_CONSUMPTION_DURABLE",
        "run_id": run_id,
        "cycle_index": cycle,
        "agent_context_consumption": consumption,
        "agent_context_consumption_binding": binding,
        "agent_reinvoked": False,
        "outcome_collection_performed": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def _persist_v311_successor_commit_envelope_from_durable_lifecycle(
    *,
    research_store: V31ResearchStorePort,
    projection_store: V31SentimentProjectionOutputStoreV2,
    transport_store: V31AgentTransportStorePort,
    base_successor_commit_material: Mapping[str, Any],
    base_successor_commit_material_binding: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
    run_id: str,
    cycle_index: int,
    sealed_at: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    cycle = _cycle(cycle_index)
    context, context_binding = _typed_existing_document(
        store=research_store,
        relative_ref=agent_input_context_ref_v1(cycle),
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    consumption, consumption_binding = _typed_existing_document(
        store=research_store,
        relative_ref=agent_context_consumption_ref_v1(cycle),
        schema_id=AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
        digest_field=AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    )
    packet = transport_store.read_bound_document(
        context["base_authoring_packet_binding"]
    )
    verify_v311_agent_input_context_durable_v1(
        agent_input_context=context,
        base_authoring_packet=packet,
        research_store=research_store,
        projection_store=projection_store,
    )
    completed = verify_completed_v31_authoring_transport(
        store=transport_store,
        run_id=run_id,
        cycle_index=cycle,
        expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
    )
    proposal = completed["checkpoint"]["stage_states"]["PROPOSAL"]
    artifacts = {
        name: transport_store.read_bound_document(proposal[f"{name}_binding"])
        for name in ("attempt", "request", "claim", "delivery", "consume")
    }
    envelope = build_v311_successor_commit_envelope_v1(
        base_successor_commit_material=base_successor_commit_material,
        base_successor_commit_material_binding=(
            base_successor_commit_material_binding
        ),
        experiment_contract=experiment_contract,
        agent_input_context=context,
        agent_input_context_binding=context_binding,
        agent_context_consumption=consumption,
        agent_context_consumption_binding=consumption_binding,
        sealed_at=sealed_at,
    )
    verify_v311_successor_commit_envelope_full_v1(
        envelope,
        base_successor_commit_material=base_successor_commit_material,
        experiment_contract=experiment_contract,
        agent_input_context=context,
        agent_context_consumption=consumption,
        base_authoring_packet=packet,
        proposal_attempt=artifacts["attempt"],
        proposal_request=artifacts["request"],
        proposal_claim=artifacts["claim"],
        proposal_delivery=artifacts["delivery"],
        proposal_consume=artifacts["consume"],
        transport_evidence=completed["transport_evidence"],
    )
    binding = _persist_document(
        store=research_store,
        relative_ref=successor_commit_envelope_ref_v1(cycle),
        document=envelope,
        digest_field=V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    )
    return envelope, binding


def _initialize_or_replay_owner_checkpoints(
    *,
    cycle_index: int,
    run_id: str,
    target_documents: Mapping[str, Mapping[str, Any]],
    genesis_documents: Mapping[str, Mapping[str, Any]],
    genesis_bindings: Mapping[str, Mapping[str, Any]],
    genesis_raw_bytes: Mapping[str, bytes],
    loaded_clock_policy: Mapping[str, Any],
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    outcome_evidence_store: V31OutcomeEvidenceStorePortV2,
    supervisor_store: V31SupervisorStoreV2Port,
    genesis_created_at: str,
    monitor_created_at: str,
    outcome_evidence_created_at: str,
    supervisor_created_at: str,
) -> dict[str, Mapping[str, Any]]:
    cycle = _cycle(cycle_index)
    contract = target_documents["experiment_contract"]
    authority = target_documents["authority"]
    contract_digest = str(contract["experiment_contract_digest"])
    authority_digest = str(authority["authority_digest"])
    clock_digest = verify_outcome_clock_policy(loaded_clock_policy)
    if cycle == 1:
        genesis = initialize_v31_run_genesis(
            store=research_store,
            created_at=genesis_created_at,
            documents=genesis_documents,
            global_bindings=genesis_bindings,
            global_raw_bytes=genesis_raw_bytes,
        )
        research = genesis["checkpoint"]
        monitor = initialize_v31_monitor_runtime(
            store=monitor_store,
            experiment_contract=contract,
            created_at=monitor_created_at,
        )
        evidence = initialize_v31_outcome_evidence_runtime_v2(
            evidence_store=outcome_evidence_store,
            experiment_contract=contract,
            created_at=outcome_evidence_created_at,
            clock_policy=loaded_clock_policy,
        )
        supervisor = initialize_v31_experiment_supervisor_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            experiment_contract_digest=contract_digest,
            active_authority_digest=authority_digest,
            created_at=supervisor_created_at,
        )
    else:
        try:
            research = research_store.load_checkpoint(run_id=run_id)
            monitor = monitor_store.load_checkpoint(run_id=run_id)
            evidence = outcome_evidence_store.load_checkpoint(run_id=run_id)
            supervisor = supervisor_store.load_checkpoint(run_id=run_id)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise V311SuccessorSingleCycleV1Error(
                "V311_SINGLE_CYCLE_PRIOR_OWNER_REPLAY_FAILED"
            ) from exc
        genesis = {"checkpoint": research}
    plans = monitor.get("plan_bindings")
    attempts = monitor.get("resolution_attempt_bindings")
    outcomes = monitor.get("outcome_bindings")
    evidence_attempts = evidence.get("attempt_bindings")
    captures = evidence.get("capture_bindings")
    parses = evidence.get("parse_bindings")
    resolutions = evidence.get("resolution_bindings")
    expected_prior = cycle - 1
    expected_idle_supervisor_resolved = max(cycle - 2, 0)
    expected_idle_supervisor_status = (
        "BOOTSTRAPPED" if cycle == 1 else "AWAITING_OUTCOME"
    )
    supervisor_status = supervisor.get("status")
    permit_open_reentry = supervisor_status == "CYCLE_PERMIT_OPEN"
    expected_supervisor_resolved = (
        expected_prior
        if permit_open_reentry
        else expected_idle_supervisor_resolved
    )
    if (
        research.get("run_id") != run_id
        or research.get("status") != "READY_FOR_CYCLE"
        or research.get("completed_cycles") != expected_prior
        or research.get("next_cycle_index") != cycle
        or research.get("active_cycle_index") is not None
        or research.get("current_authority_digest") != authority_digest
        or research.get("resume_allowed") is not True
        or research.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or research.get("executable") is not False
        or monitor.get("run_id") != run_id
        or monitor.get("status") != "ACTIVE"
        or monitor.get("experiment_contract_digest") != contract_digest
        or monitor.get("resume_allowed") is not True
        or not all(isinstance(rows, list) for rows in (plans, attempts, outcomes))
        or any(len(rows) != expected_prior for rows in (plans, attempts, outcomes))
        or evidence.get("run_id") != run_id
        or evidence.get("status") != "ACTIVE"
        or evidence.get("clock_policy_digest") != clock_digest
        or evidence.get("resume_allowed") is not True
        or not all(
            isinstance(rows, list)
            for rows in (evidence_attempts, captures, parses, resolutions)
        )
        or any(
            len(rows) != expected_prior
            for rows in (evidence_attempts, captures, parses, resolutions)
        )
        or supervisor.get("run_id") != run_id
        or supervisor_status
        not in {expected_idle_supervisor_status, "CYCLE_PERMIT_OPEN"}
        or supervisor.get("completed_research_cycles") != expected_prior
        or supervisor.get("resolved_outcome_cycles")
        != expected_supervisor_resolved
        or supervisor.get("experiment_contract_digest") != contract_digest
        or supervisor.get("active_authority_digest") != authority_digest
        or (
            permit_open_reentry
            and (
                supervisor.get("current_cycle_index") != cycle
                or not isinstance(
                    supervisor.get("active_permit_digest"), str
                )
                or _HEX_64.fullmatch(
                    str(supervisor.get("active_permit_digest"))
                )
                is None
                or supervisor.get("research_checkpoint_digest")
                != research.get("checkpoint_digest")
                or supervisor.get("monitor_checkpoint_digest")
                != monitor.get("checkpoint_digest")
            )
        )
        or (
            not permit_open_reentry
            and supervisor.get("active_permit_digest") is not None
        )
        or supervisor.get("active_commit_intent_digest") is not None
        or supervisor.get("resume_allowed") is not True
        or supervisor.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or supervisor.get("executable") is not False
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_OWNER_CHECKPOINT_IDENTITY_INVALID"
        )
    return {
        "genesis": genesis,
        "research": dict(research),
        "monitor": dict(monitor),
        "outcome_evidence": dict(evidence),
        "supervisor": dict(supervisor),
        "permit_open_reentry": permit_open_reentry,
    }


def prepare_v311_successor_single_cycle_v1(
    *,
    loaded_context: Mapping[str, Any],
    authority_projector: V311TargetAuthorityProjectorV1,
    target_global_bindings: Mapping[str, Mapping[str, Any]],
    target_global_raw_bytes: Mapping[str, bytes],
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    supervisor_store: V31SupervisorStoreV2Port,
    source_store: V31SourceQualificationStorePort,
    projection_store: V31SentimentProjectionOutputStoreV2,
    transport_store: V31AgentTransportStorePort,
    outcome_evidence_store: V31OutcomeEvidenceStorePortV2,
    commit_store: V31SuccessorCommitStoreV2Port,
    run_id: str,
    cycle_index: int,
    qualification_id: str,
    genesis_created_at: str,
    monitor_created_at: str,
    outcome_evidence_created_at: str,
    supervisor_created_at: str,
    permit_issued_at: str,
    source_admitted_at: str,
    agent_context_created_at: str,
    theory_addendum_raw_bytes: bytes,
    transport_created_at: str,
    transport_owner_id: str,
    transport_lease_expires_at: str,
    previous_cycle_source_admission_binding: Mapping[str, Any] | None = None,
    prior_snapshot_binding: Mapping[str, Any] | None = None,
    prior_open_interest_datum_digest: str | None = None,
) -> Mapping[str, Any]:
    """Prepare exactly one target cycle; invoke neither Agent nor outcome."""

    cycle = _cycle(cycle_index)
    target_documents = _project_target(
        loaded_context=loaded_context,
        authority_projector=authority_projector,
        run_id=run_id,
    )
    material_ref = successor_commit_material_ref_v2(cycle)
    if commit_store.material_exists(relative_ref=material_ref):
        material = commit_store.read_material(relative_ref=material_ref)
        binding = commit_store.artifact_binding(
            relative_ref=material_ref,
            expected_semantic_digest=str(
                material[COMMIT_MATERIAL_DIGEST_FIELD]
            ),
        )
        return {
            "status": "V311_COMMIT_MATERIAL_ALREADY_FROZEN_RECOVERY_REQUIRED",
            "run_id": run_id,
            "cycle_index": cycle,
            "commit_material_binding": dict(binding),
            "agent_invoked": False,
            "outcome_collection_performed": False,
            "state_boundary_advanced": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }

    permit_opened = False
    try:
        loaded_support = _validate_loaded_support_documents(loaded_context)
        (
            genesis_documents,
            genesis_bindings,
            genesis_raw_bytes,
        ) = _genesis_role_projection(
            target_documents=target_documents,
            target_global_bindings=target_global_bindings,
            target_global_raw_bytes=target_global_raw_bytes,
        )
        if genesis_raw_bytes is None:
            raise V311SuccessorSingleCycleV1Error(
                "V311_SINGLE_CYCLE_GENESIS_RAW_BYTES_REQUIRED"
            )
        owners = _initialize_or_replay_owner_checkpoints(
            cycle_index=cycle,
            run_id=run_id,
            target_documents=target_documents,
            genesis_documents=genesis_documents,
            genesis_bindings=genesis_bindings,
            genesis_raw_bytes=genesis_raw_bytes,
            loaded_clock_policy=loaded_support["clock_policy"],
            research_store=research_store,
            monitor_store=monitor_store,
            outcome_evidence_store=outcome_evidence_store,
            supervisor_store=supervisor_store,
            genesis_created_at=genesis_created_at,
            monitor_created_at=monitor_created_at,
            outcome_evidence_created_at=outcome_evidence_created_at,
            supervisor_created_at=supervisor_created_at,
        )
        permit = open_v31_cycle_permit_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            issued_at=permit_issued_at,
        )
        permit_opened = True
        if permit.get("cycle_index") != cycle:
            raise V311SuccessorSingleCycleV1Error(
                "V311_SINGLE_CYCLE_PERMIT_INDEX_MISMATCH"
            )
        verify_v31_cycle_permit_live_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            permit_binding=permit["cycle_permit_binding"],
            operation="SOURCE_QUALIFICATION",
        )
        source = admit_fresh_v31_source_to_authorized_cycle(
            source_store=source_store,
            run_store=research_store,
            active_chain=target_documents,
            qualification_id=qualification_id,
            run_id=run_id,
            cycle_index=cycle,
            admitted_at=source_admitted_at,
            previous_cycle_source_admission_binding=(
                previous_cycle_source_admission_binding
            ),
            prior_snapshot_binding=prior_snapshot_binding,
            prior_open_interest_datum_digest=(
                prior_open_interest_datum_digest
            ),
        )
        verify_v31_cycle_permit_live_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            permit_binding=permit["cycle_permit_binding"],
            operation="FORMAL_PREPARE",
        )
        sentiment = compose_and_persist_v31_sentiment_projection_v2(
            run_store=research_store,
            projection_store=projection_store,
            run_id=run_id,
            cycle_index=cycle,
        )
        support = _recover_support_bindings(
            research_store=research_store,
            projection_store=projection_store,
            loaded_context=loaded_context,
            target_documents=target_documents,
            target_global_bindings=target_global_bindings,
            run_id=run_id,
            cycle_index=cycle,
        )
        if support["sentiment_source_registry"] != sentiment[
            "support_bindings"
        ]["sentiment_source_registry"] or support[
            "sentiment_projection"
        ] != sentiment["support_bindings"]["sentiment_projection"]:
            raise V311SuccessorSingleCycleV1Error(
                "V311_SINGLE_CYCLE_SENTIMENT_BINDING_DRIFT"
            )
        formal = prepare_v31_formal_authoring_cycle(
            store=research_store, active_chain=target_documents
        )
        context_documents, context_bindings = _target_context_support_set(
            research_store=research_store,
            projection_store=projection_store,
            loaded_support=loaded_support,
            cycle_index=cycle,
            theory_addendum_raw_bytes=theory_addendum_raw_bytes,
        )
        agent_input_context = build_v311_agent_input_context_v1(
            run_id=run_id,
            cycle_index=cycle,
            context_profile=V311_TARGET_CONTEXT_PROFILE,
            created_at=agent_context_created_at,
            base_authoring_packet=formal["authoring_packet"],
            base_authoring_packet_binding=formal[
                "authoring_packet_binding"
            ],
            current_authority_binding=formal["authoring_packet"][
                "authority_context"
            ]["active_authority_binding"],
            theory_addendum_binding=loaded_support[
                "theory_addendum_binding"
            ],
            support_documents=context_documents,
            support_bindings=context_bindings,
        )
        agent_input_context_binding = _persist_document(
            store=research_store,
            relative_ref=agent_input_context_ref_v1(cycle),
            document=agent_input_context,
            digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        )
        verify_v311_agent_input_context_durable_v1(
            agent_input_context=agent_input_context,
            base_authoring_packet=formal["authoring_packet"],
            research_store=research_store,
            projection_store=projection_store,
        )
        transport = initialize_v31_agent_transport(
            store=transport_store,
            run_id=run_id,
            cycle_index=cycle,
            created_at=transport_created_at,
            owner_id=transport_owner_id,
            lease_expires_at=transport_lease_expires_at,
        )
    except Exception as exc:
        if isinstance(exc, KeyboardInterrupt):  # pragma: no cover
            raise
        if permit_opened:
            try:
                fail_v31_experiment_supervisor_v2(
                    supervisor_store=supervisor_store,
                    research_store=research_store,
                    monitor_store=monitor_store,
                    run_id=run_id,
                    failure_code="V311_SINGLE_CYCLE_PREPARATION_FAILED",
                    failure_summary=f"{type(exc).__name__}:{exc}",
                    occurred_at=permit_issued_at,
                )
            except Exception as failure_exc:
                if isinstance(failure_exc, KeyboardInterrupt):  # pragma: no cover
                    raise
                raise V311SuccessorSingleCycleV1Error(
                    "V311_SINGLE_CYCLE_PREPARATION_AND_SUPERVISOR_FAILURE:"
                    f"{type(failure_exc).__name__}:{failure_exc}"
                ) from exc
            raise V311SuccessorSingleCycleV1Error(
                "V311_SINGLE_CYCLE_PREPARATION_FAILED_SUPERVISOR_CLOSED"
            ) from exc
        if isinstance(exc, V311SuccessorSingleCycleV1Error):
            raise
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_PREPARATION_FAILED"
        ) from exc
    return {
        "status": "V311_SINGLE_CYCLE_READY_FOR_ONE_ATTEMPT_TRANSPORT",
        "run_id": run_id,
        "cycle_index": cycle,
        "target_active_chain": target_documents,
        "run_genesis_binding": support["application_authority_projection"],
        "cycle_permit_binding": dict(permit["cycle_permit_binding"]),
        "cycle_source_admission_binding": dict(
            source["cycle_source_admission_binding"]
        ),
        "support_bindings": support,
        "authoring_packet_binding": dict(formal["authoring_packet_binding"]),
        "agent_input_context": dict(agent_input_context),
        "agent_input_context_binding": dict(agent_input_context_binding),
        "transport_checkpoint": dict(transport),
        "research_checkpoint": dict(owners["research"]),
        "monitor_checkpoint": dict(owners["monitor"]),
        "outcome_evidence_checkpoint": dict(owners["outcome_evidence"]),
        "supervisor_before_permit_checkpoint": dict(owners["supervisor"]),
        "supervisor_checkpoint": dict(permit["supervisor_checkpoint"]),
        "agent_invoked": False,
        "outcome_collection_performed": False,
        "accepted_state_boundary_advanced": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def commit_or_recover_v311_successor_single_cycle_v1(
    *,
    loaded_context: Mapping[str, Any],
    authority_projector: V311TargetAuthorityProjectorV1,
    target_global_bindings: Mapping[str, Mapping[str, Any]],
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    supervisor_store: V31SupervisorStoreV2Port,
    projection_store: V31SentimentProjectionOutputStoreV2,
    transport_store: V31AgentTransportStorePort,
    commit_store: V31SuccessorCommitStoreV2Port,
    run_id: str,
    cycle_index: int,
    prepared_at: str,
    completed_at: str,
    recorded_at: str,
    monitor_runtime_created_at: str,
    committed_at: str,
    monitor_rules: Sequence[FrozenMonitorRule],
) -> Mapping[str, Any]:
    """Freeze or replay one commit tail with no Agent or outcome capability."""

    cycle = _cycle(cycle_index)
    target_documents = _project_target(
        loaded_context=loaded_context,
        authority_projector=authority_projector,
        run_id=run_id,
    )
    material_ref = successor_commit_material_ref_v2(cycle)
    try:
        if commit_store.material_exists(relative_ref=material_ref):
            material = commit_store.read_material(relative_ref=material_ref)
            material_binding = commit_store.artifact_binding(
                relative_ref=material_ref,
                expected_semantic_digest=str(
                    material[COMMIT_MATERIAL_DIGEST_FIELD]
                ),
            )
            support = {
                name: _assert_typed_binding(
                    material["support_bindings"][name],
                    "V311_SINGLE_CYCLE_FROZEN_SUPPORT_BINDING_INVALID",
                )
                for name in sorted(SUPPORT_BINDING_KEYS)
            }
        else:
            support = _recover_support_bindings(
                research_store=research_store,
                projection_store=projection_store,
                loaded_context=loaded_context,
                target_documents=target_documents,
                target_global_bindings=target_global_bindings,
                run_id=run_id,
                cycle_index=cycle,
            )
            supervisor = supervisor_store.load_checkpoint(run_id=run_id)
            if (
                supervisor.get("status") != "CYCLE_PERMIT_OPEN"
                or supervisor.get("current_cycle_index") != cycle
            ):
                raise V311SuccessorSingleCycleV1Error(
                    "V311_SINGLE_CYCLE_PERMIT_NOT_OPEN_FOR_COMMIT"
                )
            permit_binding = supervisor_store.artifact_binding(
                relative_ref=cycle_permit_ref_v2(cycle),
                digest_field="cycle_permit_digest",
                expected_semantic_digest=str(
                    supervisor["active_permit_digest"]
                ),
            )
            material = prepare_v31_successor_cycle_commit_material_v2(
                supervisor_store=supervisor_store,
                research_store=research_store,
                monitor_store=monitor_store,
                transport_store=transport_store,
                active_chain=target_documents,
                permit_binding=permit_binding,
                prepared_at=prepared_at,
                completed_at=completed_at,
                recorded_at=recorded_at,
                monitor_runtime_created_at=monitor_runtime_created_at,
                monitor_rules=monitor_rules,
                support_bindings=support,
            )
            material_binding = persist_v31_successor_commit_material_v2(
                commit_store=commit_store,
                material=material,
                experiment_contract=target_documents[
                    "experiment_contract"
                ],
            )
        replayed_support = _recover_support_bindings(
            research_store=research_store,
            projection_store=projection_store,
            loaded_context=loaded_context,
            target_documents=target_documents,
            target_global_bindings=target_global_bindings,
            run_id=run_id,
            cycle_index=cycle,
        )
        if replayed_support != support:
            raise V311SuccessorSingleCycleV1Error(
                "V311_SINGLE_CYCLE_FROZEN_SUPPORT_DRIFT"
            )
        (
            successor_commit_envelope,
            successor_commit_envelope_binding,
        ) = _persist_v311_successor_commit_envelope_from_durable_lifecycle(
            research_store=research_store,
            projection_store=projection_store,
            transport_store=transport_store,
            base_successor_commit_material=material,
            base_successor_commit_material_binding=material_binding,
            experiment_contract=target_documents["experiment_contract"],
            run_id=run_id,
            cycle_index=cycle,
            sealed_at=committed_at,
        )
        result = commit_or_recover_v31_successor_cycle_v2(
            supervisor_store=supervisor_store,
            commit_store=commit_store,
            research_store=research_store,
            monitor_store=monitor_store,
            active_chain=target_documents,
            material_binding=material_binding,
            committed_at=committed_at,
        )
    except V311SuccessorSingleCycleV1Error:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_COMMIT_OR_RECOVERY_FAILED"
        ) from exc
    if (
        result.get("agent_reinvoked") is not False
        or result.get("outcome_collection_performed") is not False
        or result.get("cycle_index") != cycle
    ):
        raise V311SuccessorSingleCycleV1Error(
            "V311_SINGLE_CYCLE_COMMIT_BOUNDARY_INVALID"
        )
    return {
        **dict(result),
        "support_bindings": support,
        "successor_commit_envelope": successor_commit_envelope,
        "successor_commit_envelope_binding": (
            successor_commit_envelope_binding
        ),
        "agent_invoked_by_v311_glue": False,
        "outcome_collection_performed_by_v311_glue": False,
        "state_boundary_advanced": (
            result.get("status")
            == "SUCCESSOR_CYCLE_ACCEPTED_MONITOR_SCHEDULED"
        ),
    }


def resolve_v311_successor_outcome_boundary_v1(
    *,
    loaded_context: Mapping[str, Any],
    authority_projector: V311TargetAuthorityProjectorV1,
    monitor_store: V31MonitorStorePort,
    evidence_store: V31OutcomeEvidenceStorePortV2,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    capture_port: V31PublicOutcomeCapturePortV2,
    run_id: str,
    requested_at: str,
) -> Mapping[str, Any]:
    """Handle at most one monitor boundary and never open another cycle.

    ``NOT_DUE`` and ``AWAITING_ACCEPTED_STATE`` are strictly read-only.  A
    ``DUE`` or already-reserved attempt enters the existing raw-first resolver
    exactly once.  Any deadline, monitor, capture, parse, or persistence fault
    permanently closes the Supervisor and is re-raised to the caller.
    """

    target_documents = _project_target(
        loaded_context=loaded_context,
        authority_projector=authority_projector,
        run_id=run_id,
    )
    try:
        loaded_support = _validate_loaded_support_documents(loaded_context)
        status = v31_monitor_status(
            store=monitor_store,
            experiment_contract=target_documents["experiment_contract"],
            observed_at=requested_at,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_OUTCOME_BOUNDARY_STATUS_INVALID"
        ) from exc
    runtime_status = status.get("runtime_status")
    if runtime_status == "NOT_DUE":
        return {
            **dict(status),
            "status": "V311_OUTCOME_BOUNDARY_NO_WRITE",
            "capture_attempted": False,
            "next_cycle_opened": False,
            "state_boundary_advanced": False,
        }
    if runtime_status == "AWAITING_ACCEPTED_STATE":
        try:
            evidence = evidence_store.load_checkpoint(run_id=run_id)
            monitor_resolved = status.get("resolved_cycles")
            evidence_resolutions = evidence.get("resolution_bindings")
            if (
                isinstance(monitor_resolved, bool)
                or not isinstance(monitor_resolved, int)
                or not isinstance(evidence_resolutions, list)
            ):
                raise ValueError("awaiting evidence counts invalid")
            evidence_resolved = len(evidence_resolutions)
        except (KeyError, OSError, TypeError, ValueError):
            runtime_status = "AWAITING_EVIDENCE_COUNT_INVALID"
        else:
            if monitor_resolved == evidence_resolved:
                return {
                    **dict(status),
                    "status": "V311_OUTCOME_BOUNDARY_NO_WRITE",
                    "evidence_resolved_cycles": evidence_resolved,
                    "capture_attempted": False,
                    "next_cycle_opened": False,
                    "state_boundary_advanced": False,
                }
            if monitor_resolved == evidence_resolved + 1:
                try:
                    recovered = resolve_due_v31_monitor_v2(
                        monitor_store=monitor_store,
                        evidence_store=evidence_store,
                        experiment_contract=target_documents[
                            "experiment_contract"
                        ],
                        capture_port=capture_port,
                        requested_at=requested_at,
                        clock_policy=loaded_support["clock_policy"],
                    )
                except Exception as exc:
                    if isinstance(exc, KeyboardInterrupt):
                        raise
                    try:
                        fail_v31_experiment_supervisor_v2(
                            supervisor_store=supervisor_store,
                            research_store=research_store,
                            monitor_store=monitor_store,
                            run_id=run_id,
                            failure_code=(
                                "V311_OUTCOME_AWAITING_BIND_RECOVERY_FAILED"
                            ),
                            failure_summary=f"{type(exc).__name__}:{exc}",
                            occurred_at=requested_at,
                        )
                    except Exception as failure_exc:
                        if isinstance(failure_exc, KeyboardInterrupt):
                            raise
                        raise V311SuccessorSingleCycleV1Error(
                            "V311_OUTCOME_AWAITING_BIND_AND_SUPERVISOR_FAILURE:"
                            f"{type(failure_exc).__name__}:{failure_exc}"
                        ) from exc
                    raise V311SuccessorSingleCycleV1Error(
                        "V311_OUTCOME_AWAITING_BIND_FAILED_SUPERVISOR_CLOSED"
                    ) from exc
                if recovered.get("run_id") != run_id:
                    raise V311SuccessorSingleCycleV1Error(
                        "V311_OUTCOME_AWAITING_BIND_RESULT_INVALID"
                    )
                return {
                    **dict(recovered),
                    "status": "V311_OUTCOME_EVIDENCE_BINDING_RECOVERED",
                    "capture_attempted": False,
                    "next_cycle_opened": False,
                    "state_boundary_advanced": True,
                }
            runtime_status = "AWAITING_EVIDENCE_COUNT_DRIFT"
    if runtime_status == "TERMINAL":
        return {
            **dict(status),
            "status": "V311_FINAL_OUTCOME_DURABLE_TERMINAL_WAKE_REQUIRED",
            "capture_attempted": False,
            "next_cycle_opened": False,
            "state_boundary_advanced": False,
        }
    if runtime_status in {"DUE", "ATTEMPT_RESERVED_NO_RETRY"}:
        try:
            result = resolve_due_v31_monitor_v2(
                monitor_store=monitor_store,
                evidence_store=evidence_store,
                experiment_contract=target_documents[
                    "experiment_contract"
                ],
                capture_port=capture_port,
                requested_at=requested_at,
                clock_policy=loaded_support["clock_policy"],
            )
        except Exception as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            try:
                fail_v31_experiment_supervisor_v2(
                    supervisor_store=supervisor_store,
                    research_store=research_store,
                    monitor_store=monitor_store,
                    run_id=run_id,
                    failure_code="V311_OUTCOME_BOUNDARY_FAILED",
                    failure_summary=f"{type(exc).__name__}:{exc}",
                    occurred_at=requested_at,
                )
            except Exception as failure_exc:
                if isinstance(failure_exc, KeyboardInterrupt):
                    raise
                raise V311SuccessorSingleCycleV1Error(
                    "V311_OUTCOME_BOUNDARY_AND_SUPERVISOR_FAILURE:"
                    f"{type(failure_exc).__name__}:{failure_exc}"
                ) from exc
            raise V311SuccessorSingleCycleV1Error(
                "V311_OUTCOME_BOUNDARY_FAILED_SUPERVISOR_CLOSED"
            ) from exc
        if result.get("run_id") != run_id:
            raise V311SuccessorSingleCycleV1Error(
                "V311_OUTCOME_BOUNDARY_RESULT_IDENTITY_INVALID"
            )
        return {
            **dict(result),
            "status": "V311_ONE_OUTCOME_BOUNDARY_RESOLVED",
            "capture_attempted": runtime_status == "DUE",
            "next_cycle_opened": False,
            "state_boundary_advanced": True,
        }
    try:
        failed = fail_v31_experiment_supervisor_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            failure_code=f"V311_OUTCOME_STATUS_{runtime_status}",
            failure_summary=(
                "The monitor boundary was not safely resolvable from its "
                f"durable status: {runtime_status}."
            ),
            occurred_at=requested_at,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_OUTCOME_BOUNDARY_SUPERVISOR_FAIL_CLOSED_FAILED"
        ) from exc
    return {
        "status": "V311_OUTCOME_BOUNDARY_SUPERVISOR_FAILED_CLOSED",
        "run_id": run_id,
        "runtime_status": runtime_status,
        "supervisor_failure": dict(failed),
        "capture_attempted": False,
        "next_cycle_opened": False,
        "state_boundary_advanced": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def complete_v311_successor_terminal_boundary_v1(
    *,
    loaded_context: Mapping[str, Any],
    authority_projector: V311TargetAuthorityProjectorV1,
    supervisor_store: V31SupervisorStoreV2Port,
    research_store: V31ResearchStorePort,
    monitor_store: V31MonitorStorePort,
    run_id: str,
    completed_at: str,
) -> Mapping[str, Any]:
    """Complete 8/8 only on a wake after the final outcome became durable."""

    target_documents = _project_target(
        loaded_context=loaded_context,
        authority_projector=authority_projector,
        run_id=run_id,
    )
    status = v31_monitor_status(
        store=monitor_store,
        experiment_contract=target_documents["experiment_contract"],
        observed_at=completed_at,
    )
    if status.get("runtime_status") != "TERMINAL":
        raise V311SuccessorSingleCycleV1Error(
            "V311_TERMINAL_BOUNDARY_FINAL_OUTCOME_NOT_DURABLE"
        )
    try:
        completed = complete_v31_experiment_supervisor_v2(
            supervisor_store=supervisor_store,
            research_store=research_store,
            monitor_store=monitor_store,
            run_id=run_id,
            completed_at=completed_at,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorSingleCycleV1Error(
            "V311_TERMINAL_BOUNDARY_COMPLETION_FAILED"
        ) from exc
    return {
        "status": "V311_SUCCESSOR_TERMINAL_COMPLETE",
        "run_id": run_id,
        "supervisor_checkpoint": dict(completed),
        "capture_attempted": False,
        "next_cycle_opened": False,
        "state_boundary_advanced": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


__all__ = [
    "V311_FRESH_QUALIFICATION_BUNDLE_DIGEST_FIELD",
    "V311_FRESH_QUALIFICATION_BUNDLE_SCHEMA_ID",
    "V311_SUPPORT_ROOT_V1",
    "V311SuccessorSingleCycleV1Error",
    "V311TargetAuthorityProjectorV1",
    "complete_v311_successor_terminal_boundary_v1",
    "commit_or_recover_v311_successor_single_cycle_v1",
    "prepare_v311_successor_single_cycle_v1",
    "resolve_v311_successor_outcome_boundary_v1",
]
