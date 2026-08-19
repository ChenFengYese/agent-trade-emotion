"""Read-only composition and replay for successor V3.1 qualifications.

The functions in this module never collect data, invoke an Agent, schedule a
monitor, or write authority.  They only replay already-durable evidence and
compose the three typed successor qualification documents.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..domain.behavior_planning import seal_action_selection
from ..domain.contracts.canonical import load_json_strict, verify_self_digest
from ..domain.governance.v31_successor_qualification_v2 import (
    RAW_FIRST_PROBE_DIGEST_FIELD,
    SUPERVISOR_PROBE_DIGEST_FIELD,
    build_successor_codex_durable_qualification_v2,
    build_successor_monitor_qualification_v2,
    build_successor_public_source_qualification_v2,
    verify_successor_codex_durable_qualification_v2,
    verify_successor_monitor_qualification_v2,
    verify_successor_public_source_qualification_v2,
)
from ..domain.v31_outcome_capture_v2 import verify_outcome_clock_policy
from ..infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from ..infrastructure.v31_research_store import LocalV31ResearchStore
from ..infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
)
from .v31_agent_transport import verify_completed_v31_authoring_transport
from .v31_research_cycle import verify_v31_accepted_state
from .v31_source_qualification import (
    COMPLETION_REF,
    PLAN_REF,
    SNAPSHOT_REF,
    verify_durable_v31_source_qualification_completion,
)


class V31SuccessorQualificationV2WorkflowError(ValueError):
    """Durable successor qualification evidence could not be replayed."""


def _contained_root(project_root: Path, relative_ref: str) -> tuple[Path, str]:
    try:
        project = Path(project_root).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_PROJECT_ROOT_INVALID"
        ) from exc
    if not project.is_dir() or not isinstance(relative_ref, str):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_EVIDENCE_ROOT_INVALID"
        )
    lexical = PurePosixPath(relative_ref)
    if (
        not relative_ref
        or "\\" in relative_ref
        or lexical.is_absolute()
        or lexical.as_posix() != relative_ref
        or any(part in {"", ".", ".."} for part in lexical.parts)
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_EVIDENCE_ROOT_INVALID"
        )
    cursor = project
    try:
        for part in lexical.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V31SuccessorQualificationV2WorkflowError(
                    "V31_SUCCESSOR_EVIDENCE_SYMLINK_FORBIDDEN"
                )
        root = cursor.resolve(strict=True)
        root.relative_to(project)
    except V31SuccessorQualificationV2WorkflowError:
        raise
    except (OSError, ValueError) as exc:
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_EVIDENCE_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_EVIDENCE_ROOT_INVALID"
        )
    return root, lexical.as_posix()


def _full_binding(
    *,
    partial: Mapping[str, Any],
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    try:
        digest = verify_self_digest(document, digest_field)
    except ValueError as exc:
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_ARTIFACT_DOCUMENT_INVALID"
        ) from exc
    if (
        partial.get("semantic_digest") != digest
        or not isinstance(partial.get("physical_sha256"), str)
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_ARTIFACT_BINDING_INVALID"
        )
    return {
        "relative_ref": str(partial["relative_ref"]),
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
        "semantic_digest": digest,
        "physical_sha256": str(partial["physical_sha256"]),
    }


def _validate_authority_context(
    *,
    authority: Mapping[str, Any],
    authority_binding: Mapping[str, Any],
    validated_authority_digest: str,
    run_id: str,
) -> tuple[str, str]:
    try:
        supplied = verify_self_digest(authority, "authority_digest")
    except ValueError as exc:
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_ACTIVE_AUTHORITY_INVALID"
        ) from exc
    if (
        supplied != validated_authority_digest
        or authority_binding.get("semantic_digest") != supplied
        or authority_binding.get("digest_field") != "authority_digest"
        or authority.get("authorized_run_id") != run_id
        or authority.get("experiment_start_authorized") is not True
        or not str(authority.get("status") or "").startswith("ACTIVE_")
        or authority.get("chat_history_is_authority") is not False
        or authority.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or authority.get("executable") is not False
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_ACTIVE_AUTHORITY_INVALID"
        )
    recorded_at = authority.get("recorded_at")
    if not isinstance(recorded_at, str):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_ACTIVE_AUTHORITY_INVALID"
        )
    return supplied, recorded_at


def compose_fresh_public_source_qualification_v2(
    *,
    project_root: Path,
    qualification_root_ref: str,
    qualification_id: str,
    run_id: str,
    predecessor_run_id: str,
    authority: Mapping[str, Any],
    authority_binding: Mapping[str, Any],
    validated_authority_digest: str,
    qualified_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """Replay a sealed, nonfixture public acquisition and bind it to authority."""

    root, normalized_root = _contained_root(
        project_root, qualification_root_ref
    )
    authority_digest, authority_recorded_at = _validate_authority_context(
        authority=authority,
        authority_binding=authority_binding,
        validated_authority_digest=validated_authority_digest,
        run_id=run_id,
    )
    store = LocalV31SourceQualificationStore(root)
    replay = verify_durable_v31_source_qualification_completion(
        store=store, qualification_id=qualification_id
    )
    plan = replay["plan"]
    checkpoint = replay["checkpoint"]
    completion = replay["completion"]
    snapshot_binding = completion["snapshot_binding"]
    snapshot = store.read_document(
        relative_ref=str(snapshot_binding["relative_ref"]),
        digest_field="native_market_snapshot_digest",
        expected_semantic_digest=str(snapshot_binding["semantic_digest"]),
    )
    refs = {
        "plan": (PLAN_REF, plan, "source_qualification_plan_digest"),
        "checkpoint": (
            "qualification-checkpoint.json",
            checkpoint,
            "source_qualification_checkpoint_digest",
        ),
        "completion": (
            COMPLETION_REF,
            completion,
            "source_qualification_completion_digest",
        ),
        "snapshot": (
            SNAPSHOT_REF,
            snapshot,
            "native_market_snapshot_digest",
        ),
    }
    artifacts = {
        name: _full_binding(
            partial=store.artifact_binding(
                relative_ref=relative_ref,
                digest_field=digest_field,
            ),
            document=document,
            digest_field=digest_field,
        )
        for name, (relative_ref, document, digest_field) in refs.items()
    }
    return build_successor_public_source_qualification_v2(
        run_id=run_id,
        predecessor_run_id=predecessor_run_id,
        authority_digest=authority_digest,
        authority_binding=authority_binding,
        authority_recorded_at=authority_recorded_at,
        qualification_root_ref=normalized_root,
        qualified_at=qualified_at,
        expires_at=expires_at,
        plan=plan,
        completion=completion,
        snapshot=snapshot,
        artifact_bindings=artifacts,
    )


def verify_fresh_public_source_qualification_durable_v2(
    *,
    project_root: Path,
    authority: Mapping[str, Any],
    validated_authority_digest: str,
    document: Mapping[str, Any],
) -> str:
    """Rebuild the source qualification from the bound durable raw bytes."""

    digest = verify_successor_public_source_qualification_v2(document)
    rebuilt = compose_fresh_public_source_qualification_v2(
        project_root=project_root,
        qualification_root_ref=str(document["qualification_root_ref"]),
        qualification_id=str(document["qualification_id"]),
        run_id=str(document["run_id"]),
        predecessor_run_id=str(document["predecessor_run_id"]),
        authority=authority,
        authority_binding=document["authority_binding"],
        validated_authority_digest=validated_authority_digest,
        qualified_at=str(document["qualified_at"]),
        expires_at=str(document["expires_at"]),
    )
    if rebuilt != dict(document):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_SOURCE_DURABLE_REPLAY_MISMATCH"
        )
    return digest


def _research_binding(
    *,
    store: LocalV31ResearchStore,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    return _full_binding(
        partial=store.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=str(document[digest_field]),
        ),
        document=document,
        digest_field=digest_field,
    )


def compose_current_codex_durable_qualification_v2(
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
    """Replay the formal current-Codex chain through the accepted state."""

    root, _normalized = _contained_root(project_root, run_root_ref)
    authority_digest, authority_recorded_at = _validate_authority_context(
        authority=authority,
        authority_binding=authority_binding,
        validated_authority_digest=validated_authority_digest,
        run_id=run_id,
    )
    transport_store = LocalV31AgentTransportStore(root)
    research_store = LocalV31ResearchStore(root)
    terminal = verify_completed_v31_authoring_transport(
        store=transport_store,
        run_id=run_id,
        cycle_index=cycle_index,
        expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
    )
    checkpoint = research_store.load_checkpoint(run_id=run_id)
    if (
        checkpoint.get("completed_cycles", 0) < cycle_index
        or checkpoint.get("accepted_state_ref")
        != f"cycles/{cycle_index:04d}/accepted-research-state.json"
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_CODEX_ACCEPTED_STATE_NOT_DURABLE"
        )
    accepted_ref = str(checkpoint["accepted_state_ref"])
    accepted = research_store.read_document(
        relative_ref=accepted_ref,
        digest_field="accepted_state_digest",
        expected_semantic_digest=str(checkpoint["accepted_state_digest"]),
    )
    try:
        verify_v31_accepted_state(accepted)
        replayed_selection = seal_action_selection(
            evaluation=terminal["action_evaluation"],
            selected_candidate_id=terminal["action_selection"][
                "selected_candidate_id"
            ],
            reason=terminal["action_selection"]["reason"],
            alternative_explanations=terminal["action_selection"][
                "alternative_explanations"
            ],
            failure_conditions=terminal["action_selection"][
                "failure_conditions"
            ],
            next_review_at=terminal["action_selection"]["next_review_at"],
            selected_at=terminal["action_selection"]["selected_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_CODEX_SELECTION_OR_ACCEPT_INVALID"
        ) from exc
    if (
        replayed_selection != terminal["action_selection"]
        or accepted.get("action_selection_digest")
        != replayed_selection["action_selection_digest"]
        or accepted.get("agent_proposal_digest")
        != terminal["agent_proposal"]["agent_proposal_digest"]
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_CODEX_SELECTION_OR_ACCEPT_MISMATCH"
        )
    admission = terminal["compilation_admission"]
    selection_delivery_binding = terminal["checkpoint"]["stage_states"][
        "SELECTION"
    ]["delivery_binding"]
    selection_delivery = transport_store.read_bound_document(
        selection_delivery_binding
    )
    transport_evidence_binding = transport_store.artifact_binding(
        relative_ref=str(terminal["transport_evidence_binding"]["relative_ref"]),
        digest_field="transport_evidence_digest",
    )
    artifacts = {
        "accepted_state": _research_binding(
            store=research_store,
            relative_ref=accepted_ref,
            document=accepted,
            digest_field="accepted_state_digest",
        ),
        "canonical_packet": dict(terminal["authoring_packet_binding"]),
        "compilation_admission": dict(
            terminal["compilation_admission_binding"]
        ),
        "compilation_receipt": dict(
            admission["compilation_receipt_binding"]
        ),
        "postseal_selection_delivery": dict(selection_delivery_binding),
        "proposal": dict(admission["agent_proposal_binding"]),
        "transport_evidence": transport_evidence_binding,
    }
    return build_successor_codex_durable_qualification_v2(
        run_id=run_id,
        predecessor_run_id=predecessor_run_id,
        cycle_index=cycle_index,
        authority_digest=authority_digest,
        authority_binding=authority_binding,
        authority_recorded_at=authority_recorded_at,
        qualified_at=qualified_at,
        source_qualification_v2_digest=source_qualification_v2_digest,
        canonical_packet=terminal["authoring_packet"],
        agent_authoring_envelope=terminal["agent_authoring_envelope"],
        transport_evidence=terminal["transport_evidence"],
        inputs_receipt=terminal["inputs_receipt"],
        agent_proposal=terminal["agent_proposal"],
        compilation_receipt=terminal["compilation_receipt"],
        compilation_admission=admission,
        postseal_selection_delivery=selection_delivery,
        accepted_state=accepted,
        artifact_bindings=artifacts,
    )


def verify_current_codex_qualification_durable_v2(
    *,
    project_root: Path,
    run_root_ref: str,
    authority: Mapping[str, Any],
    validated_authority_digest: str,
    document: Mapping[str, Any],
) -> str:
    digest = verify_successor_codex_durable_qualification_v2(document)
    rebuilt = compose_current_codex_durable_qualification_v2(
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
    if rebuilt != dict(document):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_CODEX_DURABLE_REPLAY_MISMATCH"
        )
    return digest


def compose_monitor_runtime_qualification_v2(
    *,
    run_id: str,
    predecessor_run_id: str,
    authority: Mapping[str, Any],
    authority_binding: Mapping[str, Any],
    validated_authority_digest: str,
    qualified_at: str,
    clock_policy: Mapping[str, Any],
    clock_policy_binding: Mapping[str, Any],
    raw_first_probe: Mapping[str, Any],
    raw_first_probe_binding: Mapping[str, Any],
    supervisor_probe: Mapping[str, Any],
    supervisor_probe_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Compose Q8-v2 from actual focused-test receipts and frozen policy."""

    authority_digest, authority_recorded_at = _validate_authority_context(
        authority=authority,
        authority_binding=authority_binding,
        validated_authority_digest=validated_authority_digest,
        run_id=run_id,
    )
    clock_digest = verify_outcome_clock_policy(clock_policy)
    if (
        raw_first_probe_binding.get("semantic_digest")
        != raw_first_probe.get(RAW_FIRST_PROBE_DIGEST_FIELD)
        or supervisor_probe_binding.get("semantic_digest")
        != supervisor_probe[SUPERVISOR_PROBE_DIGEST_FIELD]
        or raw_first_probe.get("clock_policy_digest") != clock_digest
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_MONITOR_PROBE_BINDING_MISMATCH"
        )
    return build_successor_monitor_qualification_v2(
        run_id=run_id,
        predecessor_run_id=predecessor_run_id,
        authority_digest=authority_digest,
        authority_binding=authority_binding,
        authority_recorded_at=authority_recorded_at,
        qualified_at=qualified_at,
        clock_policy=clock_policy,
        clock_policy_binding=clock_policy_binding,
        raw_first_probe=raw_first_probe,
        raw_first_probe_binding=raw_first_probe_binding,
        supervisor_probe=supervisor_probe,
        supervisor_probe_binding=supervisor_probe_binding,
    )


def _read_bound_document(
    *, root: Path, binding: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        relative = PurePosixPath(str(binding["relative_ref"]))
        target = root.joinpath(*relative.parts)
        if target.is_symlink():
            raise ValueError("symlink")
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
        payload = resolved.read_bytes()
        if hashlib.sha256(payload).hexdigest() != binding["physical_sha256"]:
            raise ValueError("physical drift")
        document = load_json_strict(resolved)
        digest = verify_self_digest(document, str(binding["digest_field"]))
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_BOUND_EVIDENCE_INVALID"
        ) from exc
    if (
        document.get("schema_id") != binding.get("schema_id")
        or digest != binding.get("semantic_digest")
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_BOUND_EVIDENCE_DRIFT"
        )
    return dict(document)


def verify_monitor_qualification_durable_v2(
    *, run_root: Path, document: Mapping[str, Any]
) -> str:
    """Replay all three physical probe/policy files bound by monitor Q-v2."""

    digest = verify_successor_monitor_qualification_v2(document)
    root = Path(run_root).resolve(strict=True)
    bindings = document["artifact_bindings"]
    observed = {
        name: _read_bound_document(root=root, binding=binding)
        for name, binding in bindings.items()
    }
    if (
        observed["clock_policy"] != document["clock_policy"]
        or observed["raw_first_probe"] != document["raw_first_probe"]
        or observed["supervisor_probe"] != document["supervisor_probe"]
    ):
        raise V31SuccessorQualificationV2WorkflowError(
            "V31_SUCCESSOR_MONITOR_DURABLE_REPLAY_MISMATCH"
        )
    return digest


__all__ = [
    "V31SuccessorQualificationV2WorkflowError",
    "compose_current_codex_durable_qualification_v2",
    "compose_fresh_public_source_qualification_v2",
    "compose_monitor_runtime_qualification_v2",
    "verify_current_codex_qualification_durable_v2",
    "verify_fresh_public_source_qualification_durable_v2",
    "verify_monitor_qualification_durable_v2",
]
