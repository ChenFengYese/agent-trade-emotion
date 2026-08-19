"""Read-only composition and physical replay for Codex qualification v3."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..domain.contracts.canonical import verify_self_digest
from ..domain.governance.v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    build_successor_codex_durable_qualification_v3,
    verify_successor_codex_durable_qualification_v3,
)
from ..domain.v311_agent_lifecycle_v1 import (
    AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
    agent_context_consumption_ref_v1,
    agent_input_context_ref_v1,
    successor_commit_envelope_ref_v1,
)
from ..domain.v31_successor_cycle_commit_v2 import (
    DIGEST_FIELD as BASE_COMMIT_DIGEST_FIELD,
    SCHEMA_ID as BASE_COMMIT_SCHEMA_ID,
)
from ..infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from ..infrastructure.v31_research_store import LocalV31ResearchStore
from ..infrastructure.v31_successor_commit_store_v2 import (
    LocalV31SuccessorCommitStoreV2,
)
from .v31_agent_transport import verify_completed_v31_authoring_transport
from .v31_successor_qualification_v2 import (
    compose_current_codex_durable_qualification_v2,
)


class V311CodexDurableQualificationV3WorkflowError(ValueError):
    """A bound lifecycle artifact failed physical or semantic replay."""


def _contained_root(project_root: Path, relative_ref: str) -> Path:
    try:
        project = Path(project_root).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_PROJECT_ROOT_INVALID"
        ) from exc
    lexical = PurePosixPath(relative_ref) if isinstance(relative_ref, str) else None
    if (
        lexical is None
        or not relative_ref
        or "\\" in relative_ref
        or lexical.is_absolute()
        or lexical.as_posix() != relative_ref
        or any(part in {"", ".", ".."} for part in lexical.parts)
    ):
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_RUN_ROOT_INVALID"
        )
    cursor = project
    try:
        for part in lexical.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V311CodexDurableQualificationV3WorkflowError(
                    "V311_CODEX_V3_SYMLINK_FORBIDDEN"
                )
        root = cursor.resolve(strict=True)
        root.relative_to(project)
    except V311CodexDurableQualificationV3WorkflowError:
        raise
    except (OSError, ValueError) as exc:
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_RUN_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_RUN_ROOT_INVALID"
        )
    return root


def _research_document_and_binding(
    *,
    store: LocalV31ResearchStore,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        document = dict(
            store.read_document(
                relative_ref=relative_ref, digest_field=digest_field
            )
        )
        semantic = verify_self_digest(document, digest_field)
        partial = store.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=semantic,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_LIFECYCLE_ARTIFACT_INVALID"
        ) from exc
    if document.get("schema_id") != schema_id:
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_LIFECYCLE_SCHEMA_INVALID"
        )
    return document, {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": str(partial["physical_sha256"]),
    }


def _load_lifecycle(
    *,
    project_root: Path,
    root: Path,
    run_id: str,
    cycle_index: int,
) -> dict[str, Any]:
    transport_store = LocalV31AgentTransportStore(root)
    research_store = LocalV31ResearchStore(root)
    terminal = verify_completed_v31_authoring_transport(
        store=transport_store,
        run_id=run_id,
        cycle_index=cycle_index,
        expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
    )
    context, context_binding = _research_document_and_binding(
        store=research_store,
        relative_ref=agent_input_context_ref_v1(cycle_index),
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    consumption, consumption_binding = _research_document_and_binding(
        store=research_store,
        relative_ref=agent_context_consumption_ref_v1(cycle_index),
        schema_id=AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
        digest_field=AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    )
    commit_envelope, commit_envelope_binding = _research_document_and_binding(
        store=research_store,
        relative_ref=successor_commit_envelope_ref_v1(cycle_index),
        schema_id=V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
        digest_field=V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    )
    try:
        support_documents = context["support_documents"]
        support_bindings = context["support_bindings"]
        if (
            not isinstance(support_documents, Mapping)
            or not isinstance(support_bindings, Mapping)
            or set(support_documents) != set(support_bindings)
        ):
            raise ValueError("support set drift")
        for name, raw_binding in support_bindings.items():
            binding = dict(raw_binding)
            durable, durable_binding = _research_document_and_binding(
                store=research_store,
                relative_ref=str(binding["relative_ref"]),
                schema_id=str(binding["schema_id"]),
                digest_field=str(binding["digest_field"]),
            )
            if durable != dict(support_documents[name]) or durable_binding != binding:
                raise ValueError("support physical drift")
        addendum = support_documents["theory_addendum"]
        source_binding = addendum["source_binding"]
        source_ref = str(source_binding["path"])
        lexical = PurePosixPath(source_ref)
        if (
            not source_ref
            or "\\" in source_ref
            or lexical.is_absolute()
            or lexical.as_posix() != source_ref
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise ValueError("addendum source path invalid")
        project = Path(project_root).resolve(strict=True)
        cursor = project
        for part in lexical.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("addendum source symlink forbidden")
        source_path = cursor.resolve(strict=True)
        source_path.relative_to(project)
        source_bytes = source_path.read_bytes()
        if (
            hashlib.sha256(source_bytes).hexdigest()
            != source_binding["physical_sha256"]
            or source_bytes.decode("utf-8") != addendum["markdown_utf8"]
            or source_binding != context["theory_addendum_binding"]
        ):
            raise ValueError("addendum source physical drift")
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as exc:
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_SUPPORT_PHYSICAL_REPLAY_INVALID"
        ) from exc
    proposal_state = terminal["checkpoint"]["stage_states"]["PROPOSAL"]
    try:
        proposal_documents = {
            name: transport_store.read_bound_document(proposal_state[f"{name}_binding"])
            for name in ("attempt", "request", "claim", "delivery", "consume")
        }
        evidence_binding = terminal["transport_evidence_binding"]
        transport_binding = transport_store.artifact_binding(
            relative_ref=str(evidence_binding["relative_ref"]),
            digest_field="transport_evidence_digest",
        )
        if (
            transport_binding["semantic_digest"]
            != terminal["transport_evidence"]["transport_evidence_digest"]
        ):
            raise ValueError("transport evidence drift")
        experiment_contract = terminal["experiment_subject"]
        commit_store = LocalV31SuccessorCommitStoreV2(
            root, experiment_contract=experiment_contract
        )
        base_binding = commit_envelope["base_successor_commit_material_binding"]
        base_material = dict(
            commit_store.read_material(
                relative_ref=str(base_binding["relative_ref"]),
                expected_semantic_digest=str(base_binding["semantic_digest"]),
            )
        )
        durable_base_binding = dict(
            commit_store.artifact_binding(
                relative_ref=str(base_binding["relative_ref"]),
                expected_semantic_digest=str(base_binding["semantic_digest"]),
            )
        )
        permit_binding = dict(base_material["cycle_permit_binding"])
        _permit, durable_permit_binding = _research_document_and_binding(
            store=research_store,
            relative_ref=str(permit_binding["relative_ref"]),
            schema_id=str(permit_binding["schema_id"]),
            digest_field=str(permit_binding["digest_field"]),
        )
        if durable_permit_binding != permit_binding:
            raise ValueError("cycle permit physical drift")
        base_support_bindings = base_material["support_bindings"]
        if not isinstance(base_support_bindings, Mapping):
            raise ValueError("base support set invalid")
        for raw_binding in base_support_bindings.values():
            support_binding = dict(raw_binding)
            _support, durable_support_binding = _research_document_and_binding(
                store=research_store,
                relative_ref=str(support_binding["relative_ref"]),
                schema_id=str(support_binding["schema_id"]),
                digest_field=str(support_binding["digest_field"]),
            )
            if durable_support_binding != support_binding:
                raise ValueError("base support physical drift")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_DURABLE_PREFIX_INVALID"
        ) from exc
    if (
        durable_base_binding != dict(base_binding)
        or durable_base_binding.get("schema_id") != BASE_COMMIT_SCHEMA_ID
        or durable_base_binding.get("digest_field") != BASE_COMMIT_DIGEST_FIELD
        or base_material.get("transport_evidence_binding") != transport_binding
    ):
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_BASE_COMMIT_BINDING_DRIFT"
        )
    return {
        "terminal": terminal,
        "canonical_packet": terminal["authoring_packet"],
        "proposal_attempt": proposal_documents["attempt"],
        "proposal_request": proposal_documents["request"],
        "proposal_claim": proposal_documents["claim"],
        "proposal_delivery": proposal_documents["delivery"],
        "proposal_consume": proposal_documents["consume"],
        "transport_evidence": terminal["transport_evidence"],
        "transport_evidence_binding": transport_binding,
        "experiment_contract": experiment_contract,
        "agent_input_context": context,
        "agent_input_context_binding": context_binding,
        "agent_context_consumption": consumption,
        "agent_context_consumption_binding": consumption_binding,
        "base_successor_commit_material": base_material,
        "base_successor_commit_material_binding": durable_base_binding,
        "successor_commit_envelope": commit_envelope,
        "successor_commit_envelope_binding": commit_envelope_binding,
    }


def compose_current_codex_durable_qualification_v3(
    *,
    project_root: Path,
    run_root_ref: str,
    run_id: str,
    predecessor_run_id: str,
    cycle_index: int,
    authority: Mapping[str, Any],
    authority_binding: Mapping[str, Any],
    validated_authority_digest: str,
    source_qualification_v2_digest: str,
    qualified_at: str,
) -> dict[str, Any]:
    """Rebuild v2 then extend it with the physically durable V3.1.1 chain."""

    root = _contained_root(project_root, run_root_ref)
    base = compose_current_codex_durable_qualification_v2(
        project_root=project_root,
        run_root_ref=run_root_ref,
        run_id=run_id,
        predecessor_run_id=predecessor_run_id,
        cycle_index=cycle_index,
        authority=authority,
        authority_binding=authority_binding,
        validated_authority_digest=validated_authority_digest,
        source_qualification_v2_digest=source_qualification_v2_digest,
        qualified_at=qualified_at,
    )
    lifecycle = _load_lifecycle(
        project_root=project_root,
        root=root,
        run_id=run_id,
        cycle_index=cycle_index,
    )
    artifact_bindings = {
        **{
            name: dict(binding)
            for name, binding in base["artifact_bindings"].items()
        },
        "agent_input_context": lifecycle["agent_input_context_binding"],
        "agent_context_consumption": lifecycle[
            "agent_context_consumption_binding"
        ],
        "base_successor_commit_material": lifecycle[
            "base_successor_commit_material_binding"
        ],
        "successor_commit_envelope": lifecycle[
            "successor_commit_envelope_binding"
        ],
    }
    try:
        return build_successor_codex_durable_qualification_v3(
            base_codex_qualification_v2=base,
            qualified_at=qualified_at,
            experiment_contract=lifecycle["experiment_contract"],
            canonical_packet=lifecycle["canonical_packet"],
            proposal_attempt=lifecycle["proposal_attempt"],
            proposal_request=lifecycle["proposal_request"],
            proposal_claim=lifecycle["proposal_claim"],
            proposal_delivery=lifecycle["proposal_delivery"],
            proposal_consume=lifecycle["proposal_consume"],
            transport_evidence=lifecycle["transport_evidence"],
            agent_input_context=lifecycle["agent_input_context"],
            agent_context_consumption=lifecycle["agent_context_consumption"],
            base_successor_commit_material=lifecycle[
                "base_successor_commit_material"
            ],
            successor_commit_envelope=lifecycle[
                "successor_commit_envelope"
            ],
            artifact_bindings=artifact_bindings,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311CodexDurableQualificationV3WorkflowError):
            raise
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_COMPOSITION_INVALID"
        ) from exc


def verify_current_codex_qualification_durable_v3(
    *,
    project_root: Path,
    run_root_ref: str,
    authority: Mapping[str, Any],
    validated_authority_digest: str,
    document: Mapping[str, Any],
) -> str:
    """Replay every bound artifact and compare the exact receipt bytes."""

    try:
        digest = verify_successor_codex_durable_qualification_v3(document)
        rebuilt = compose_current_codex_durable_qualification_v3(
            project_root=project_root,
            run_root_ref=run_root_ref,
            run_id=str(document["run_id"]),
            predecessor_run_id=str(document["predecessor_run_id"]),
            cycle_index=int(document["cycle_index"]),
            authority=authority,
            authority_binding=document["authority_binding"],
            validated_authority_digest=validated_authority_digest,
            source_qualification_v2_digest=str(
                document["source_qualification_v2_digest"]
            ),
            qualified_at=str(document["qualified_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311CodexDurableQualificationV3WorkflowError):
            raise
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_DURABLE_REPLAY_INVALID"
        ) from exc
    if rebuilt != dict(document):
        raise V311CodexDurableQualificationV3WorkflowError(
            "V311_CODEX_V3_DURABLE_REPLAY_MISMATCH"
        )
    return digest


__all__ = [
    "V311CodexDurableQualificationV3WorkflowError",
    "compose_current_codex_durable_qualification_v3",
    "verify_current_codex_qualification_durable_v3",
]
