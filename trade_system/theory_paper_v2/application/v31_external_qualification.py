"""Read-only composition helpers for V3.1 Q6/Q7 typed qualification.

These helpers are intentionally unable to collect market data, invoke an
Agent, create a run, or write an authority file.  They replay already-terminal
durable evidence, calculate physical file bindings, and delegate the final
receipt construction to the Domain.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..domain.governance.v31_external_qualification import (
    build_q6_source_qualification_receipt,
    build_q7_agent_transport_receipt,
)
from ..infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from ..infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
)
from .v31_agent_transport import verify_completed_v31_authoring_transport
from .v31_cycle_authoring import compile_v31_agent_open_analysis
from ..infrastructure.v31_semantic_compiler import LocalV31SemanticCompiler
from .v31_source_qualification import (
    COMPLETION_REF,
    PLAN_REF,
    RESERVATION_REF,
    verify_durable_v31_source_qualification_completion,
)


class V31ExternalQualificationWorkflowError(ValueError):
    """Terminal evidence was not safely contained or replayable."""


def _contained_root(project_root: Path, relative_root: str) -> tuple[Path, str]:
    try:
        project = Path(project_root).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V31ExternalQualificationWorkflowError(
            "V31_EXTERNAL_QUALIFICATION_PROJECT_ROOT_INVALID"
        ) from exc
    if not project.is_dir() or not isinstance(relative_root, str):
        raise V31ExternalQualificationWorkflowError(
            "V31_EXTERNAL_QUALIFICATION_ROOT_INVALID"
        )
    lexical = PurePosixPath(relative_root)
    if (
        not relative_root
        or "\\" in relative_root
        or lexical.as_posix() != relative_root
        or lexical.is_absolute()
        or any(part in {"", ".", ".."} for part in lexical.parts)
    ):
        raise V31ExternalQualificationWorkflowError(
            "V31_EXTERNAL_QUALIFICATION_ROOT_INVALID"
        )
    candidate = project.joinpath(*lexical.parts)
    try:
        if candidate.is_symlink():
            raise V31ExternalQualificationWorkflowError(
                "V31_EXTERNAL_QUALIFICATION_SYMLINK_FORBIDDEN"
            )
        root = candidate.resolve(strict=True)
        root.relative_to(project)
    except (OSError, ValueError) as exc:
        raise V31ExternalQualificationWorkflowError(
            "V31_EXTERNAL_QUALIFICATION_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V31ExternalQualificationWorkflowError(
            "V31_EXTERNAL_QUALIFICATION_ROOT_INVALID"
        )
    return root, lexical.as_posix()


def _binding(
    *,
    root: Path,
    root_ref: str,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    path = root.joinpath(*PurePosixPath(relative_ref).parts)
    try:
        if path.is_symlink():
            raise V31ExternalQualificationWorkflowError(
                "V31_EXTERNAL_QUALIFICATION_SYMLINK_FORBIDDEN"
            )
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise V31ExternalQualificationWorkflowError(
            "V31_EXTERNAL_QUALIFICATION_ARTIFACT_INVALID"
        ) from exc
    if not resolved.is_file():
        raise V31ExternalQualificationWorkflowError(
            "V31_EXTERNAL_QUALIFICATION_ARTIFACT_INVALID"
        )
    return {
        "path": f"{root_ref}/{relative_ref}",
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
        "semantic_digest": str(document[digest_field]),
        "physical_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def _q6_information_event_records(
    *,
    store: LocalV31SourceQualificationStore,
    completion: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Re-read every completion-bound event record through its durable binding."""

    bindings = completion.get("information_event_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise V31ExternalQualificationWorkflowError(
            "V31_Q6_INFORMATION_EVENT_BINDINGS_INVALID"
        )
    records: list[dict[str, Any]] = []
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise V31ExternalQualificationWorkflowError(
                "V31_Q6_INFORMATION_EVENT_BINDINGS_INVALID"
            )
        try:
            record = store.read_document(
                relative_ref=str(binding["relative_ref"]),
                digest_field=(
                    "source_qualification_information_event_record_digest"
                ),
                expected_semantic_digest=str(binding["semantic_digest"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V31ExternalQualificationWorkflowError(
                "V31_Q6_INFORMATION_EVENT_BINDINGS_INVALID"
            ) from exc
        if (
            record.get(
                "source_qualification_information_event_record_digest"
            )
            != binding.get("semantic_digest")
        ):
            raise V31ExternalQualificationWorkflowError(
                "V31_Q6_INFORMATION_EVENT_BINDINGS_INVALID"
            )
        records.append(dict(record))
    return records


def build_q6_receipt_from_durable_qualification(
    *,
    project_root: Path,
    qualification_root_ref: str,
    qualification_id: str,
    evaluated_at: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Fully replay one sealed source qualification and build its Q6 receipt."""

    root, root_ref = _contained_root(project_root, qualification_root_ref)
    expected_root = (
        "agent-cluster/experiments/v31-qualifications/" f"{qualification_id}"
    )
    if root_ref != expected_root:
        raise V31ExternalQualificationWorkflowError(
            "V31_Q6_QUALIFICATION_ROOT_IDENTITY_INVALID"
        )
    store = LocalV31SourceQualificationStore(root)
    replay = verify_durable_v31_source_qualification_completion(
        store=store, qualification_id=qualification_id
    )
    information_event_records = _q6_information_event_records(
        store=store, completion=replay["completion"]
    )
    documents = {
        "plan": replay["plan"],
        "reservation": replay["reservation"],
        "checkpoint": replay["checkpoint"],
        "completion": replay["completion"],
    }
    refs = {
        "plan": (PLAN_REF, "source_qualification_plan_digest"),
        "reservation": (
            RESERVATION_REF,
            "source_qualification_reservation_digest",
        ),
        "checkpoint": (
            "qualification-checkpoint.json",
            "source_qualification_checkpoint_digest",
        ),
        "completion": (
            COMPLETION_REF,
            "source_qualification_completion_digest",
        ),
    }
    artifact_bindings = {
        name: _binding(
            root=root,
            root_ref=root_ref,
            relative_ref=relative_ref,
            document=documents[name],
            digest_field=digest_field,
        )
        for name, (relative_ref, digest_field) in refs.items()
    }
    return build_q6_source_qualification_receipt(
        evaluated_at=evaluated_at,
        experiment_contract=experiment_contract,
        manifest=manifest,
        qualification_evidence={
            **documents,
            "information_event_records": information_event_records,
            "artifact_bindings": artifact_bindings,
        },
    )


def verify_q6_receipt_durable_artifacts(
    *, project_root: Path, receipt: Mapping[str, Any]
) -> str:
    """Recheck a Q6 receipt against its bound files and every retained raw byte."""

    if not isinstance(receipt, Mapping) or receipt.get("gate_id") != "Q6":
        raise V31ExternalQualificationWorkflowError(
            "V31_Q6_RECEIPT_EVIDENCE_INVALID"
        )
    evidence = receipt.get("qualification_evidence")
    if not isinstance(evidence, Mapping):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q6_RECEIPT_EVIDENCE_INVALID"
        )
    plan = evidence.get("plan")
    bindings = evidence.get("artifact_bindings")
    if not isinstance(plan, Mapping) or not isinstance(bindings, Mapping):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q6_RECEIPT_EVIDENCE_INVALID"
        )
    qualification_id = str(plan.get("qualification_id") or "")
    root_ref = (
        "agent-cluster/experiments/v31-qualifications/"
        f"{qualification_id}"
    )
    root, normalized_root_ref = _contained_root(project_root, root_ref)
    refs = {
        "plan": (PLAN_REF, "source_qualification_plan_digest"),
        "reservation": (
            RESERVATION_REF,
            "source_qualification_reservation_digest",
        ),
        "checkpoint": (
            "qualification-checkpoint.json",
            "source_qualification_checkpoint_digest",
        ),
        "completion": (
            COMPLETION_REF,
            "source_qualification_completion_digest",
        ),
    }
    for name, (relative_ref, digest_field) in refs.items():
        document = evidence.get(name)
        if not isinstance(document, Mapping) or name not in bindings:
            raise V31ExternalQualificationWorkflowError(
                "V31_Q6_RECEIPT_EVIDENCE_INVALID"
            )
        observed = _binding(
            root=root,
            root_ref=normalized_root_ref,
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )
        if observed != bindings[name]:
            raise V31ExternalQualificationWorkflowError(
                "V31_Q6_RECEIPT_ARTIFACT_PHYSICAL_DRIFT"
            )
    replay = verify_durable_v31_source_qualification_completion(
        store=LocalV31SourceQualificationStore(root),
        qualification_id=qualification_id,
    )
    if any(
        replay[name] != evidence[name]
        for name in ("plan", "reservation", "checkpoint", "completion")
    ):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q6_RECEIPT_ARTIFACT_SEMANTIC_DRIFT"
        )
    durable_records = _q6_information_event_records(
        store=LocalV31SourceQualificationStore(root),
        completion=replay["completion"],
    )
    if durable_records != evidence.get("information_event_records"):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q6_RECEIPT_INFORMATION_EVENT_DRIFT"
        )
    return str(replay["completion"]["source_qualification_completion_digest"])


def _replay_q7_compilation(
    *, store: LocalV31AgentTransportStore, terminal: Mapping[str, Any]
) -> None:
    replay = compile_v31_agent_open_analysis(
        authoring_packet=terminal["authoring_packet"],
        authoring_envelope=terminal["agent_authoring_envelope"],
        compiled_at=terminal["compilation_receipt"]["compiled_at"],
        compiler=LocalV31SemanticCompiler(store=store),
    )
    pairs = {
        "inputs_receipt": "inputs_receipt",
        "agent_proposal": "agent_proposal",
        "action_evaluation": "action_evaluation",
        "preselection": "preselection",
        "compilation_receipt": "compilation_receipt",
    }
    if any(replay[left] != terminal[right] for left, right in pairs.items()):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q7_DETERMINISTIC_COMPILATION_REPLAY_DRIFT"
        )


def _q7_terminal_evidence(
    *,
    root: Path,
    root_ref: str,
    subject_run_id: str,
) -> dict[str, Any]:
    store = LocalV31AgentTransportStore(root)
    terminal = verify_completed_v31_authoring_transport(
        store=store,
        run_id=subject_run_id,
        cycle_index=1,
        expected_authoring_purpose="TRANSPORT_QUALIFICATION_ONLY",
    )
    _replay_q7_compilation(store=store, terminal=terminal)
    admission = terminal["compilation_admission"]
    packet = terminal["authoring_packet"]
    refs = {
        "checkpoint": (
            "cycles/0001/agent-transport/checkpoint.json",
            terminal["checkpoint"],
            "checkpoint_digest",
        ),
        "transport_evidence": (
            terminal["transport_evidence_binding"]["relative_ref"],
            terminal["transport_evidence"],
            "transport_evidence_digest",
        ),
        "authoring_packet": (
            terminal["authoring_packet_binding"]["relative_ref"],
            packet,
            "authoring_packet_digest",
        ),
        "compilation_receipt": (
            admission["compilation_receipt_binding"]["relative_ref"],
            terminal["compilation_receipt"],
            "authoring_compilation_receipt_digest",
        ),
        "compilation_admission": (
            terminal["compilation_admission_binding"]["relative_ref"],
            admission,
            "authoring_compilation_admission_digest",
        ),
        "compiled_assembly_bundle": (
            admission["compiled_assembly_bundle_binding"]["relative_ref"],
            terminal["compiled_assembly_bundle"],
            "compiled_assembly_bundle_digest",
        ),
        "experiment_subject": (
            packet["authority_context"]["experiment_subject_binding"][
                "relative_ref"
            ],
            terminal["experiment_subject"],
            "experiment_contract_digest",
        ),
    }
    artifact_bindings = {
        name: _binding(
            root=root,
            root_ref=root_ref,
            relative_ref=str(relative_ref),
            document=document,
            digest_field=digest_field,
        )
        for name, (relative_ref, document, digest_field) in refs.items()
    }
    return {
        "checkpoint": terminal["checkpoint"],
        "transport_evidence": terminal["transport_evidence"],
        "authoring_packet": packet,
        "agent_authoring_envelope": terminal["agent_authoring_envelope"],
        "compilation_receipt": terminal["compilation_receipt"],
        "compilation_admission": admission,
        "compiled_assembly_bundle": terminal["compiled_assembly_bundle"],
        "experiment_subject": terminal["experiment_subject"],
        "terminal_assertions": {
            "authoring_purpose": terminal["authoring_purpose"],
            "active_authority_binding": terminal["active_authority_binding"],
            "experiment_start_authorized": terminal[
                "experiment_start_authorized"
            ],
            "qualification_evidence_is_start_authority": packet[
                "qualification_evidence_is_start_authority"
            ],
            "subject_run_id_matches": terminal["subject_run_id_matches"],
            "postseal_selection_consumed": terminal[
                "postseal_selection_consumed"
            ],
            "source_qualification_completion_digest": packet[
                "source_qualification_completion_binding"
            ]["semantic_digest"],
            "external_execution_authority": terminal[
                "external_execution_authority"
            ],
            "executable": terminal["executable"],
        },
        "artifact_bindings": artifact_bindings,
    }


def build_q7_receipt_from_completed_authoring_transport(
    *,
    project_root: Path,
    qualification_root_ref: str,
    subject_run_id: str,
    evaluated_at: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Build Q7 only from a physically replayed open-analysis terminal chain."""
    root, root_ref = _contained_root(project_root, qualification_root_ref)
    if experiment_contract.get("run_id") != subject_run_id:
        raise V31ExternalQualificationWorkflowError(
            "V31_Q7_SUBJECT_RUN_IDENTITY_INVALID"
        )
    evidence = _q7_terminal_evidence(
        root=root, root_ref=root_ref, subject_run_id=subject_run_id
    )
    return build_q7_agent_transport_receipt(
        evaluated_at=evaluated_at,
        experiment_contract=experiment_contract,
        manifest=manifest,
        qualification_evidence=evidence,
    )


def verify_q7_receipt_durable_artifacts(
    *, project_root: Path, receipt: Mapping[str, Any]
) -> str:
    if not isinstance(receipt, Mapping) or receipt.get("gate_id") != "Q7":
        raise V31ExternalQualificationWorkflowError(
            "V31_Q7_RECEIPT_EVIDENCE_INVALID"
        )
    evidence = receipt.get("qualification_evidence")
    artifacts = evidence.get("artifact_bindings") if isinstance(evidence, Mapping) else None
    checkpoint = artifacts.get("checkpoint") if isinstance(artifacts, Mapping) else None
    if not isinstance(checkpoint, Mapping):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q7_RECEIPT_EVIDENCE_INVALID"
        )
    suffix = PurePosixPath("cycles/0001/agent-transport/checkpoint.json")
    path = PurePosixPath(str(checkpoint.get("path") or ""))
    if (
        len(path.parts) <= len(suffix.parts)
        or path.parts[-len(suffix.parts) :] != suffix.parts
    ):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q7_RECEIPT_ROOT_INVALID"
        )
    root_ref = PurePosixPath(*path.parts[: -len(suffix.parts)]).as_posix()
    root, normalized = _contained_root(project_root, root_ref)
    packet = evidence.get("authoring_packet")
    if not isinstance(packet, Mapping):
        raise V31ExternalQualificationWorkflowError(
            "V31_Q7_RECEIPT_EVIDENCE_INVALID"
        )
    observed = _q7_terminal_evidence(
        root=root,
        root_ref=normalized,
        subject_run_id=str(packet.get("run_id") or ""),
    )
    if observed != evidence:
        raise V31ExternalQualificationWorkflowError(
            "V31_Q7_RECEIPT_DURABLE_EVIDENCE_DRIFT"
        )
    return str(observed["transport_evidence"]["transport_evidence_digest"])


__all__ = [
    "V31ExternalQualificationWorkflowError",
    "build_q6_receipt_from_durable_qualification",
    "build_q7_receipt_from_completed_authoring_transport",
    "verify_q6_receipt_durable_artifacts",
    "verify_q7_receipt_durable_artifacts",
]
