"""Read-only full loader for a future V3.2 target authority.

The historical V3.1 loader and permanent-failure replay always run before any
V3.2 file is opened.  After complete verification, only five target semantic
documents are projected to Application; Q0-Q8 and qualification bodies remain
inside this infrastructure boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol

from ...domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    verify_self_digest,
)
from ...domain.governance.v31_authorization import V31AuthorizationError
from ...domain.governance.v32_authorization import (
    ACTUAL_CAPABILITY_RECEIPT_SPECS,
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    AUTHORIZATION_RECEIPT_SCHEMA_ID,
    CAPABILITY_GATE_MAP,
    CAPABILITY_KEYS,
    GATE_EVIDENCE_DIGEST_FIELD,
    GATE_EVIDENCE_SCHEMA_ID,
    PHASE_A_DIGEST_FIELD,
    PHASE_A_SCHEMA_ID,
    Q0_Q8_GATE_IDS,
    QUALIFICATION_PHASE_PROFILE,
    QUALIFICATION_PROFILE,
    QUALIFICATION_RECEIPT_DIGEST_FIELD,
    QUALIFICATION_RECEIPT_SCHEMA_ID,
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_SCHEMA_ID,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    RUNTIME_MANIFEST_SCHEMA_ID,
    RUNTIME_MANIFEST_V2_SCHEMA_VERSION,
    SUPPORT_DOCUMENT_BINDING_SPECS,
    TARGET_PHASE_PROFILE,
    TARGET_PROFILE,
    THEORY_APPROVAL_DIGEST_FIELD,
    THEORY_APPROVAL_SCHEMA_ID,
    THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
    THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
    V32AuthorizationError,
    verify_v32_authority_v1,
    verify_v32_actual_capability_receipt_v1,
    verify_v32_authorization_receipt_v1,
    verify_v32_fresh_capability_qualification_receipt_v1,
    verify_v32_phase_a_qualification_receipt_v1,
    verify_v32_qualification_gate_evidence_v1,
    verify_v32_qualification_retirement_receipt_v1,
    verify_v32_runtime_manifest,
    verify_v32_theory_approval_receipt_v1,
)
from ...domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
    SCHEMA_ID as EXPERIMENT_CONTRACT_SCHEMA_ID,
    SUPPORT_BINDING_KEYS,
    THEORY_VERSION,
    V32ExperimentContractError,
    verify_v32_experiment_contract_v1,
)
from ...domain.governance.v32_preflight_gate_subject import (
    DIGEST_FIELD as PREFLIGHT_SUBJECT_DIGEST_FIELD,
    GATE_ANCHOR_ROLES as PREFLIGHT_GATE_ANCHOR_ROLES,
    SCHEMA_ID as PREFLIGHT_SUBJECT_SCHEMA_ID,
    verify_v32_typed_preflight_gate_subject_v1,
)
from ...domain.governance.v32_workspace_freeze import (
    SCHEMA_VERSION_POSTCOMMIT as WORKSPACE_POSTCOMMIT_SCHEMA_VERSION,
)
from ...domain.governance.v311_fresh_process_trace_v2 import (
    FRESH_PROCESS_TRACE_DIGEST_FIELD,
    FRESH_PROCESS_TRACE_SCHEMA_ID,
    verify_v311_fresh_process_trace_receipt_v2,
)
from ...domain.governance.v32_qualification_identity import (
    TOMBSTONED_V32_RUN_IDS,
    V32QualificationIdentityError,
    validate_v32_active_qualification_identity_v1,
    validate_v32_run_id_syntax_v1,
)
from ...domain.v32_agent_lifecycle import (
    build_v32_theory_semantic_document_v1,
    verify_v32_theory_semantic_document_v1,
)
from ...application.v32_authorized_revision_orchestration import (
    verify_v32_authorized_revision_support_bundle_v1,
)
from ...domain.v31_sentiment_native_projection_v2 import (
    verify_v31_native_sentiment_source_registry,
)
from ...domain.v32_association_preregistration import (
    verify_v32_association_preregistration,
)
from ...domain.v32_context_compaction import (
    POLICY_DIGEST_FIELD as CONTEXT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as CONTEXT_POLICY_SCHEMA_ID,
    verify_v32_context_compaction_policy_v1,
)
from ...domain.v32_cycle_audit_narrative import (
    POLICY_DIGEST_FIELD as AUDIT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as AUDIT_POLICY_SCHEMA_ID,
    verify_v32_cycle_audit_policy_v1,
)
from ...domain.v32_data_gap_escalation import (
    POLICY_DIGEST_FIELD as DATA_GAP_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as DATA_GAP_POLICY_SCHEMA_ID,
    verify_v32_data_gap_manual_policy_v1,
)
from ...domain.v32_environment_capability import (
    DIGEST_FIELD as ENVIRONMENT_DIGEST_FIELD,
    SCHEMA_ID as ENVIRONMENT_SCHEMA_ID,
    verify_v32_environment_capability_profile_v1,
)
from ...domain.v32_evaluation_contract import verify_v32_evaluation_contract
from ...domain.v32_recovery_supervision import (
    verify_v32_recovery_supervision_policy_v1,
)
from ...domain.v32_runtime_support_contracts import (
    verify_v32_clock_and_tick_policy_v1,
    verify_v32_public_outcome_adapter_contract_v1,
)
from ...domain.v32_unknown_assessment import (
    POLICY_DIGEST_FIELD as UNKNOWN_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as UNKNOWN_POLICY_SCHEMA_ID,
    verify_v32_unknown_subjective_policy_v1,
)
from .v31_current_research import (
    V31_CURRENT_RESEARCH_AUTHORITY_PATH,
    load_v31_active_authorization_chain,
)
from .v31_runtime_closure_v2 import (
    V31RuntimeClosureError,
    verify_v31_runtime_closure_bindings_v2,
)
from .v311_successor_current_research_v2 import (
    load_v311_legacy_failure_evidence_v2,
)
from .v32_workspace_freeze import verify_live_v32_workspace_freeze_v1
from .v32_qualification_runtime_namespace import (
    RUNTIME_BASE,
    V32QualificationRuntimeNamespaceError,
    assert_v32_qualification_runtime_namespace_v1,
    build_v32_qualification_runtime_paths_v1,
)
from ...domain.governance.v311_successor_authority_envelope_v2 import (
    V311_LEGACY_RUN_ID,
    V311SuccessorAuthorityEnvelopeV2Error,
)


class V32CurrentResearchAuthorityError(ValueError):
    """The old lineage or future V3.2 authority failed closed."""


class V32ActualCapabilityFullReplayVerifier(Protocol):
    """Owning full-replay port for one post-authority capability receipt."""

    def __call__(
        self,
        *,
        project_root: Path,
        capability_receipt: Mapping[str, Any],
        evidence_root_binding: Mapping[str, str],
        qualification_authority: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


V32_CURRENT_RESEARCH_AUTHORITY_PATH = Path(
    "config/theory_paper_v32.current_research_authority.v1.json"
)
V32_APPLICATION_PROJECTION_KEYS = (
    "theory_approval",
    "experiment_contract",
    "manifest",
    "authorization_receipt",
    "authority",
)
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_REVISION_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_REVISION_COMPONENT_SPECS = {
    "context_compaction_policy": (
        CONTEXT_POLICY_SCHEMA_ID,
        CONTEXT_POLICY_DIGEST_FIELD,
        verify_v32_context_compaction_policy_v1,
    ),
    "unknown_subjective_policy": (
        UNKNOWN_POLICY_SCHEMA_ID,
        UNKNOWN_POLICY_DIGEST_FIELD,
        verify_v32_unknown_subjective_policy_v1,
    ),
    "data_gap_manual_policy": (
        DATA_GAP_POLICY_SCHEMA_ID,
        DATA_GAP_POLICY_DIGEST_FIELD,
        verify_v32_data_gap_manual_policy_v1,
    ),
    "cycle_audit_policy": (
        AUDIT_POLICY_SCHEMA_ID,
        AUDIT_POLICY_DIGEST_FIELD,
        verify_v32_cycle_audit_policy_v1,
    ),
    "environment_capability_profile": (
        ENVIRONMENT_SCHEMA_ID,
        ENVIRONMENT_DIGEST_FIELD,
        verify_v32_environment_capability_profile_v1,
    ),
}
_HEX = frozenset("0123456789abcdef")
_CAPABILITY_REPLAY_RESULT_FIELDS = frozenset(
    {
        "capability",
        "evidence_root_semantic_digest",
        "full_replay_verified",
        "replay_network_calls",
    }
)
_SUPPORT_PATH_SUFFIXES = {
    "association_preregistration_digest": "support/association.json",
    "authorized_revision_support_bundle_digest": "support/revision-bundle.json",
    "clock_policy_digest": "support/clock.json",
    "evaluation_contract_digest": "support/evaluation.json",
    "outcome_adapter_contract_digest": "support/outcome-adapter.json",
    "recovery_supervision_policy_digest": "support/recovery.json",
    "twelve_axis_source_registry_digest": "support/twelve-axis.json",
    "workspace_freeze_receipt_digest": "support/workspace-freeze.json",
}
_REVISION_PATH_SUFFIXES = {
    "context_compaction_policy": "support/revision/context.json",
    "unknown_subjective_policy": "support/revision/unknown.json",
    "data_gap_manual_policy": "support/revision/data-gap.json",
    "cycle_audit_policy": "support/revision/audit.json",
    "environment_capability_profile": "support/revision/environment.json",
}


def _runtime_ref(runtime_root: str, suffix: str) -> str:
    return PurePosixPath(runtime_root, suffix).as_posix()


def _qualification_from_exact_binding_path(
    binding_value: Any,
    *,
    suffix: str,
    code: str,
) -> str:
    if not isinstance(binding_value, Mapping):
        raise V32CurrentResearchAuthorityError(code)
    path = binding_value.get("path")
    prefix = f"{RUNTIME_BASE}/"
    tail = f"/{suffix}"
    if (
        not isinstance(path, str)
        or not path.startswith(prefix)
        or not path.endswith(tail)
    ):
        raise V32CurrentResearchAuthorityError(code)
    qualification = path[len(prefix) : -len(tail)]
    try:
        qualification = validate_v32_run_id_syntax_v1(qualification)
    except V32QualificationIdentityError as exc:
        raise V32CurrentResearchAuthorityError(code) from exc
    if qualification in TOMBSTONED_V32_RUN_IDS or "/" in qualification:
        raise V32CurrentResearchAuthorityError(code)
    expected = build_v32_qualification_runtime_paths_v1(qualification)
    if path != _runtime_ref(expected["root"], suffix):
        raise V32CurrentResearchAuthorityError(code)
    return qualification


def _assert_exact_runtime_namespace(
    project: Path, *, target_run_id: Any, qualification_run_id: Any
) -> dict[str, str]:
    try:
        target, qualification = validate_v32_active_qualification_identity_v1(
            target_run_id=target_run_id,
            qualification_run_id=qualification_run_id,
        )
        paths = dict(
            assert_v32_qualification_runtime_namespace_v1(
                project_root=project,
                qualification_run_id=qualification,
                require_root=True,
            )
        )
    except (V32QualificationIdentityError, V32QualificationRuntimeNamespaceError) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_RUNTIME_NAMESPACE_INVALID"
        ) from exc
    if target != target_run_id:
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_RUNTIME_NAMESPACE_INVALID"
        )
    return paths


def _project_root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise V32CurrentResearchAuthorityError("V32_AUTHORITY_ROOT_SYMLINK")
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError("V32_AUTHORITY_ROOT_INVALID") from exc
    if not root.is_dir():
        raise V32CurrentResearchAuthorityError("V32_AUTHORITY_ROOT_INVALID")
    return root


def _relative(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32CurrentResearchAuthorityError(code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32CurrentResearchAuthorityError(code)
    return value


def _contained_file(project: Path, relative_ref: Any, code: str) -> Path:
    relative = _relative(relative_ref, code)
    cursor = project
    try:
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V32CurrentResearchAuthorityError(code)
        target = cursor.resolve(strict=True)
        target.relative_to(project)
    except V32CurrentResearchAuthorityError:
        raise
    except (OSError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError(code) from exc
    if not target.is_file() or target.is_symlink():
        raise V32CurrentResearchAuthorityError(code)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_document(path: Path, code: str) -> dict[str, Any]:
    try:
        document = load_json_strict(path)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError(code) from exc
    if not isinstance(document, dict):
        raise V32CurrentResearchAuthorityError(code)
    return document


def _binding_shape(
    value: Any,
    *,
    schema_id: str | None,
    digest_field: str | None,
    code: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32CurrentResearchAuthorityError(code)
    result = {key: value.get(key) for key in _BINDING_FIELDS}
    if (
        not all(isinstance(result[key], str) and result[key] for key in result)
        or len(result["semantic_digest"]) != 64
        or len(result["physical_sha256"]) != 64
        or any(char not in _HEX for char in result["semantic_digest"])
        or any(char not in _HEX for char in result["physical_sha256"])
        or (schema_id is not None and result["schema_id"] != schema_id)
        or (digest_field is not None and result["digest_field"] != digest_field)
    ):
        raise V32CurrentResearchAuthorityError(code)
    result["path"] = _relative(result["path"], code)
    return {key: str(result[key]) for key in (
        "path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"
    )}


def _file_binding(
    project: Path,
    *,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    path = _contained_file(project, relative_ref, "V32_AUTHORITY_BINDING_PATH_INVALID")
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_AUTHORITY_BINDING_DOCUMENT_INVALID"
        ) from exc
    return {
        "path": relative_ref,
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": _sha256(path),
    }


def _load_bound_document(
    project: Path,
    binding_value: Any,
    *,
    schema_id: str,
    digest_field: str,
    verifier: Any,
    code: str,
    expected_path: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    binding = _binding_shape(
        binding_value,
        schema_id=schema_id,
        digest_field=digest_field,
        code=code,
    )
    if expected_path is not None and binding["path"] != expected_path:
        raise V32CurrentResearchAuthorityError(code)
    path = _contained_file(project, binding["path"], code)
    document = _strict_document(path, code)
    if document.get("schema_id") != schema_id:
        raise V32CurrentResearchAuthorityError(code)
    try:
        semantic = verifier(document)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentResearchAuthorityError):
            raise
        raise V32CurrentResearchAuthorityError(code) from exc
    if (
        semantic != binding["semantic_digest"]
        or _sha256(path) != binding["physical_sha256"]
    ):
        raise V32CurrentResearchAuthorityError(code)
    return document, binding


def _load_subject_document(
    project: Path,
    binding_value: Any,
    *,
    code: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Open one gate subject and prove its exact typed physical binding."""

    binding = _binding_shape(
        binding_value,
        schema_id=None,
        digest_field=None,
        code=code,
    )
    path = _contained_file(project, binding["path"], code)
    document = _strict_document(path, code)
    if document.get("schema_id") != binding["schema_id"]:
        raise V32CurrentResearchAuthorityError(code)
    try:
        semantic = verify_self_digest(document, binding["digest_field"])
    except (TypeError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError(code) from exc
    if (
        semantic != binding["semantic_digest"]
        or _sha256(path) != binding["physical_sha256"]
    ):
        raise V32CurrentResearchAuthorityError(code)
    return document, binding


def _capability_verifier_registry(
    value: Any,
) -> dict[str, V32ActualCapabilityFullReplayVerifier]:
    if value is None:
        # Production callers cannot weaken or replace the owning replayers.
        # The local import avoids a module cycle during schema initialization.
        from .v32_actual_capability_replay import (
            build_v32_actual_capability_full_replay_registry,
        )

        value = build_v32_actual_capability_full_replay_registry()
    if not isinstance(value, Mapping) or set(value) != set(CAPABILITY_KEYS):
        raise V32CurrentResearchAuthorityError(
            "V32_CAPABILITY_FULL_REPLAY_VERIFIER_REGISTRY_REQUIRED"
        )
    result: dict[str, V32ActualCapabilityFullReplayVerifier] = {}
    for capability in CAPABILITY_KEYS:
        verifier = value.get(capability)
        if not callable(verifier):
            raise V32CurrentResearchAuthorityError(
                "V32_CAPABILITY_FULL_REPLAY_VERIFIER_REGISTRY_REQUIRED"
            )
        result[capability] = verifier
    return result


def _load_actual_capability_receipts(
    project: Path,
    *,
    qualification_receipt: Mapping[str, Any],
    qualification_authority: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    runtime_root: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Load the three typed receipts without treating them as replay proof."""

    bindings = qualification_receipt.get("capability_evidence_bindings")
    if not isinstance(bindings, Mapping) or tuple(bindings) != CAPABILITY_KEYS:
        raise V32CurrentResearchAuthorityError(
            "V32_ACTUAL_CAPABILITY_RECEIPT_SET_INVALID"
        )
    documents: dict[str, dict[str, Any]] = {}
    normalized: dict[str, dict[str, str]] = {}
    for capability in CAPABILITY_KEYS:
        schema_id, digest_field = ACTUAL_CAPABILITY_RECEIPT_SPECS[capability]
        document, binding = _load_bound_document(
            project,
            bindings[capability],
            schema_id=schema_id,
            digest_field=digest_field,
            verifier=verify_v32_actual_capability_receipt_v1,
            code=f"V32_ACTUAL_CAPABILITY_RECEIPT_INVALID:{capability}",
            expected_path=_runtime_ref(
                runtime_root,
                "evidence/seal-bundle/receipts/"
                f"{capability.lower().replace('_', '-')}.json",
            ),
        )
        if (
            document.get("capability") != capability
            or document.get("qualification_run_id")
            != qualification_authority.get("run_id")
            or document.get("target_run_id")
            != qualification_authority.get("target_run_id")
            or document.get("qualification_authority_binding")
            != qualification_authority_binding
        ):
            raise V32CurrentResearchAuthorityError(
                f"V32_ACTUAL_CAPABILITY_RECEIPT_CHAIN_INVALID:{capability}"
            )
        documents[capability] = document
        normalized[capability] = binding
    return documents, normalized


def _replay_actual_capability_evidence(
    project: Path,
    *,
    capability_receipts: Mapping[str, Mapping[str, Any]],
    qualification_authority: Mapping[str, Any],
    verifier_registry: Mapping[str, V32ActualCapabilityFullReplayVerifier],
    runtime_root: str,
) -> None:
    """Invoke each owning verifier; self-digest-only evidence is insufficient."""

    registry = _capability_verifier_registry(verifier_registry)
    for capability in CAPABILITY_KEYS:
        receipt = capability_receipts[capability]
        binding = _binding_shape(
            receipt.get("evidence_root_binding"),
            schema_id=None,
            digest_field=None,
            code=f"V32_CAPABILITY_EVIDENCE_ROOT_INVALID:{capability}",
        )
        if binding["path"] != _runtime_ref(
            runtime_root,
            f"evidence/roots/{capability.lower().replace('_', '-')}.json",
        ):
            raise V32CurrentResearchAuthorityError(
                f"V32_CAPABILITY_EVIDENCE_ROOT_INVALID:{capability}"
            )
        path = _contained_file(
            project,
            binding["path"],
            f"V32_CAPABILITY_EVIDENCE_ROOT_INVALID:{capability}",
        )
        if _sha256(path) != binding["physical_sha256"]:
            raise V32CurrentResearchAuthorityError(
                f"V32_CAPABILITY_EVIDENCE_ROOT_INVALID:{capability}"
            )
        try:
            replay = registry[capability](
                project_root=project,
                capability_receipt=receipt,
                evidence_root_binding=binding,
                qualification_authority=qualification_authority,
            )
        except Exception as exc:
            if isinstance(exc, V32CurrentResearchAuthorityError):
                raise
            raise V32CurrentResearchAuthorityError(
                f"V32_CAPABILITY_FULL_REPLAY_INVALID:{capability}"
            ) from exc
        if (
            not isinstance(replay, Mapping)
            or set(replay) != _CAPABILITY_REPLAY_RESULT_FIELDS
            or replay.get("capability") != capability
            or replay.get("evidence_root_semantic_digest")
            != binding["semantic_digest"]
            or replay.get("full_replay_verified") is not True
            or replay.get("replay_network_calls") != 0
        ):
            raise V32CurrentResearchAuthorityError(
                f"V32_CAPABILITY_FULL_REPLAY_INVALID:{capability}"
            )


def replay_v32_actual_capability_qualification_receipt(
    project_root: Path,
    *,
    qualification_authority_binding: Mapping[str, Any],
    qualification_receipt_binding: Mapping[str, Any],
    capability_verifiers: Mapping[
        str, V32ActualCapabilityFullReplayVerifier
    ],
) -> dict[str, Any]:
    """Fully replay one post-authority qualification before retirement.

    Phase-B evidence is not opened until the complete Phase-A authorization
    base has been replayed.  The authority binding is used only to locate the
    immutable per-qualification namespace after the legacy predecessor has
    already passed; it cannot replace or weaken that base replay.
    """

    project = _project_root(project_root)
    qualification = _qualification_from_exact_binding_path(
        qualification_authority_binding,
        suffix="qualification/authority.json",
        code="V32_QUALIFICATION_AUTHORITY_BINDING_INVALID",
    )
    runtime_root = build_v32_qualification_runtime_paths_v1(qualification)[
        "root"
    ]

    # Preserve the hard predecessor-first boundary even though the target id
    # needed by the full Phase-A loader lives inside this bound authority.
    # No Phase-B receipt or evidence path is touched before the base succeeds.
    replay_v32_legacy_predecessor(project)
    located_authority, located_binding = _load_bound_document(
        project,
        qualification_authority_binding,
        schema_id=AUTHORITY_SCHEMA_ID,
        digest_field=AUTHORITY_DIGEST_FIELD,
        verifier=verify_v32_authority_v1,
        code="V32_QUALIFICATION_AUTHORITY_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "qualification/authority.json"
        ),
    )
    base = load_v32_qualification_phase_a_authority(
        project,
        expected_target_run_id=str(located_authority.get("target_run_id")),
        expected_qualification_run_id=qualification,
    )
    authority = base["qualification_authority"]
    authority_binding = base["qualification_authority_binding"]
    if located_binding != authority_binding:
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_AUTHORITY_BINDING_INVALID"
        )
    receipt, receipt_binding = _load_bound_document(
        project,
        qualification_receipt_binding,
        schema_id=QUALIFICATION_RECEIPT_SCHEMA_ID,
        digest_field=QUALIFICATION_RECEIPT_DIGEST_FIELD,
        verifier=verify_v32_fresh_capability_qualification_receipt_v1,
        code="V32_QUALIFICATION_RECEIPT_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root,
            "evidence/seal-bundle/qualification-receipt.json",
        ),
    )
    if (
        authority.get("profile") != QUALIFICATION_PROFILE
        or authority.get("run_id") == authority.get("target_run_id")
        or receipt.get("qualification_run_id") != authority.get("run_id")
        or receipt.get("target_run_id") != authority.get("target_run_id")
        or receipt.get("qualification_authority_binding") != authority_binding
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_CAPABILITY_QUALIFICATION_CHAIN_INVALID"
        )
    documents, bindings = _load_actual_capability_receipts(
        project,
        qualification_receipt=receipt,
        qualification_authority=authority,
        qualification_authority_binding=authority_binding,
        runtime_root=runtime_root,
    )
    started = _moment(receipt.get("started_at"), "V32_CHRONOLOGY_INVALID")
    completed = _moment(receipt.get("completed_at"), "V32_CHRONOLOGY_INVALID")
    recorded = _moment(authority.get("recorded_at"), "V32_CHRONOLOGY_INVALID")
    if not recorded < started <= completed or any(
        not (
            started
            <= _moment(document.get("started_at"), "V32_CHRONOLOGY_INVALID")
            <= _moment(document.get("completed_at"), "V32_CHRONOLOGY_INVALID")
            <= completed
        )
        for document in documents.values()
    ):
        raise V32CurrentResearchAuthorityError("V32_CHRONOLOGY_INVALID")
    _replay_actual_capability_evidence(
        project,
        capability_receipts=documents,
        qualification_authority=authority,
        verifier_registry=capability_verifiers,
        runtime_root=runtime_root,
    )
    return {
        "qualification_authority": authority,
        "qualification_authority_binding": authority_binding,
        "qualification_receipt": receipt,
        "qualification_receipt_binding": receipt_binding,
        "actual_capability_receipts": documents,
        "actual_capability_receipt_bindings": bindings,
        "full_replay_verified": True,
        "replay_network_calls": 0,
    }


def _load_revision_component(
    project: Path,
    binding_value: Any,
    *,
    role: str,
    runtime_root: str,
) -> dict[str, Any]:
    """Replay one relative-ref component through its owning Domain verifier."""

    code = f"V32_REVISION_SUPPORT_COMPONENT_INVALID:{role}"
    if role not in _REVISION_COMPONENT_SPECS:
        raise V32CurrentResearchAuthorityError(code)
    if not isinstance(binding_value, Mapping) or set(binding_value) != _REVISION_BINDING_FIELDS:
        raise V32CurrentResearchAuthorityError(code)
    schema_id, digest_field, verifier = _REVISION_COMPONENT_SPECS[role]
    relative_ref = _relative(binding_value.get("relative_ref"), code)
    if relative_ref != _runtime_ref(
        runtime_root, _REVISION_PATH_SUFFIXES[role]
    ):
        raise V32CurrentResearchAuthorityError(code)
    binding = {
        "relative_ref": relative_ref,
        "schema_id": binding_value.get("schema_id"),
        "digest_field": binding_value.get("digest_field"),
        "semantic_digest": binding_value.get("semantic_digest"),
        "physical_sha256": binding_value.get("physical_sha256"),
    }
    if (
        binding["schema_id"] != schema_id
        or binding["digest_field"] != digest_field
        or not all(
            isinstance(binding[field], str)
            and len(binding[field]) == 64
            and not (set(binding[field]) - _HEX)
            for field in ("semantic_digest", "physical_sha256")
        )
    ):
        raise V32CurrentResearchAuthorityError(code)
    path = _contained_file(project, relative_ref, code)
    document = _strict_document(path, code)
    if document.get("schema_id") != schema_id:
        raise V32CurrentResearchAuthorityError(code)
    try:
        semantic = verifier(document)
    except (TypeError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError(code) from exc
    if semantic != binding["semantic_digest"] or _sha256(path) != binding[
        "physical_sha256"
    ]:
        raise V32CurrentResearchAuthorityError(code)
    return document


def _verify_revision_support_bundle(
    project: Path, document: Mapping[str, Any], *, runtime_root: str
) -> str:
    code = "V32_AUTHORIZED_REVISION_SUPPORT_BUNDLE_INVALID"
    rows = document.get("components")
    if not isinstance(rows, list) or len(rows) != len(_REVISION_COMPONENT_SPECS):
        raise V32CurrentResearchAuthorityError(code)
    by_role: dict[str, Any] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"role", "binding"}
            or row.get("role") in by_role
        ):
            raise V32CurrentResearchAuthorityError(code)
        by_role[str(row["role"])] = row["binding"]
    if set(by_role) != set(_REVISION_COMPONENT_SPECS):
        raise V32CurrentResearchAuthorityError(code)
    components = {
        role: _load_revision_component(
            project, by_role[role], role=role, runtime_root=runtime_root
        )
        for role in _REVISION_COMPONENT_SPECS
    }
    try:
        return verify_v32_authorized_revision_support_bundle_v1(
            document,
            context_compaction_policy=components["context_compaction_policy"],
            unknown_subjective_policy=components["unknown_subjective_policy"],
            data_gap_manual_policy=components["data_gap_manual_policy"],
            cycle_audit_policy=components["cycle_audit_policy"],
            environment_capability_profile=components[
                "environment_capability_profile"
            ],
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, V32CurrentResearchAuthorityError):
            raise
        raise V32CurrentResearchAuthorityError(code) from exc


def _load_support_documents(
    project: Path,
    *,
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    runtime_root: str,
) -> dict[str, dict[str, Any]]:
    """Load all eight physical supports and compare owning digests to contract."""

    bindings = manifest.get("support_document_bindings")
    contract_digests = contract.get("support_bindings")
    if (
        not isinstance(bindings, Mapping)
        or tuple(bindings) != SUPPORT_BINDING_KEYS
        or not isinstance(contract_digests, Mapping)
        or set(contract_digests) != set(SUPPORT_BINDING_KEYS)
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_SUPPORT_DOCUMENT_BINDINGS_INVALID"
        )

    documents: dict[str, dict[str, Any]] = {}

    def load(key: str, verifier: Any) -> dict[str, Any]:
        schema_id, digest_field = SUPPORT_DOCUMENT_BINDING_SPECS[key]
        document, binding = _load_bound_document(
            project,
            bindings[key],
            schema_id=schema_id,
            digest_field=digest_field,
            verifier=verifier,
            code=f"V32_SUPPORT_DOCUMENT_INVALID:{key}",
            expected_path=_runtime_ref(
                runtime_root, _SUPPORT_PATH_SUFFIXES[key]
            ),
        )
        if binding["semantic_digest"] != contract_digests[key]:
            raise V32CurrentResearchAuthorityError(
                f"V32_SUPPORT_CONTRACT_DIGEST_MISMATCH:{key}"
            )
        documents[key] = document
        return document

    association = load(
        "association_preregistration_digest",
        verify_v32_association_preregistration,
    )
    load(
        "authorized_revision_support_bundle_digest",
        lambda document: _verify_revision_support_bundle(
            project, document, runtime_root=runtime_root
        ),
    )
    load("clock_policy_digest", verify_v32_clock_and_tick_policy_v1)
    load(
        "evaluation_contract_digest",
        lambda document: verify_v32_evaluation_contract(document, association),
    )
    load(
        "outcome_adapter_contract_digest",
        verify_v32_public_outcome_adapter_contract_v1,
    )
    load(
        "recovery_supervision_policy_digest",
        verify_v32_recovery_supervision_policy_v1,
    )
    load(
        "twelve_axis_source_registry_digest",
        verify_v31_native_sentiment_source_registry,
    )
    workspace = load(
        "workspace_freeze_receipt_digest",
        lambda document: verify_live_v32_workspace_freeze_v1(
            project_root=project, receipt=document
        ),
    )

    if (
        workspace.get("schema_version") != WORKSPACE_POSTCOMMIT_SCHEMA_VERSION
        or workspace.get("postcommit_regression_target_run_id")
        != contract.get("run_id")
        or workspace.get("postcommit_regression_qualification_run_id")
        != manifest.get("qualification_run_id")
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_POSTCOMMIT_WORKSPACE_SUPPORT_REQUIRED"
        )

    target_run_id = contract.get("run_id")
    for key in (
        "association_preregistration_digest",
        "authorized_revision_support_bundle_digest",
        "clock_policy_digest",
        "evaluation_contract_digest",
        "outcome_adapter_contract_digest",
    ):
        if documents[key].get("run_scope_id") != target_run_id:
            raise V32CurrentResearchAuthorityError(
                f"V32_SUPPORT_RUN_SCOPE_MISMATCH:{key}"
            )
    return documents


def _load_manifest_fresh_process_trace(
    project: Path, *, manifest: Mapping[str, Any], runtime_root: str
) -> dict[str, Any]:
    """Replay the physical child-process trace bound by the manifest."""

    trace, recovered_binding = _load_bound_document(
        project,
        manifest.get("fresh_process_trace_binding"),
        schema_id=FRESH_PROCESS_TRACE_SCHEMA_ID,
        digest_field=FRESH_PROCESS_TRACE_DIGEST_FIELD,
        verifier=verify_v311_fresh_process_trace_receipt_v2,
        code="V32_FRESH_PROCESS_TRACE_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "support/fresh-process-trace.json"
        ),
    )
    if (
        recovered_binding != manifest.get("fresh_process_trace_binding")
        or trace.get("production_root_paths")
        != manifest.get("production_root_paths")
        or trace.get("observed_project_python_paths")
        != manifest.get("fresh_trace_paths")
        or trace.get("fresh_process_proven") is not True
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_FRESH_PROCESS_TRACE_BINDING_INVALID"
        )
    return trace


def _replay_manifest_fresh_process_trace_if_required(
    project: Path, *, manifest: Mapping[str, Any], runtime_root: str
) -> dict[str, Any] | None:
    """Replay the V2 trace while preserving exact sealed V1 compatibility.

    The six historical qualification trees predate the physical trace child
    document and therefore have no such binding.  Their exact 1.0.0 shape is
    still verified by the strict manifest router.  Every 2.0.0 manifest must
    carry and physically replay the trace receipt; no unknown version reaches
    this point because ``verify_v32_runtime_manifest`` already rejects it.
    """

    version = manifest.get("schema_version")
    if version == "1.0.0":
        return None
    if version != RUNTIME_MANIFEST_V2_SCHEMA_VERSION:
        raise V32CurrentResearchAuthorityError(
            "V32_RUNTIME_MANIFEST_VERSION_UNSUPPORTED"
        )
    return _load_manifest_fresh_process_trace(
        project, manifest=manifest, runtime_root=runtime_root
    )


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32CurrentResearchAuthorityError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32CurrentResearchAuthorityError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32CurrentResearchAuthorityError(code)
    return parsed.astimezone(UTC)


def _load_phase_gate_evidence(
    project: Path,
    phase: Mapping[str, Any],
    *,
    must_postdate: datetime | None,
    code: str,
    manifest: Mapping[str, Any],
    expected_preflight_anchors: Mapping[str, Mapping[str, Any]],
    actual_capability_bindings: Mapping[str, Mapping[str, Any]] | None = None,
    runtime_root: str,
    directory: str,
) -> dict[str, dict[str, Any]]:
    """Replay all nine gate envelopes and every subject they physically bind."""

    bindings = phase.get("q0_q8_evidence_bindings")
    if not isinstance(bindings, Mapping) or tuple(bindings) != Q0_Q8_GATE_IDS:
        raise V32CurrentResearchAuthorityError(code)
    phase_time = _moment(phase.get("evaluated_at"), code)
    documents: dict[str, dict[str, Any]] = {}
    for gate_id in Q0_Q8_GATE_IDS:
        gate, gate_binding = _load_bound_document(
            project,
            bindings[gate_id],
            schema_id=GATE_EVIDENCE_SCHEMA_ID,
            digest_field=GATE_EVIDENCE_DIGEST_FIELD,
            verifier=verify_v32_qualification_gate_evidence_v1,
            code=code,
            expected_path=_runtime_ref(
                runtime_root, f"{directory}/gates/{gate_id.lower()}.json"
            ),
        )
        gate_time = _moment(gate.get("evaluated_at"), code)
        if (
            gate_binding != bindings[gate_id]
            or gate.get("gate_id") != gate_id
            or gate.get("profile") != phase.get("profile")
            or gate.get("run_id") != phase.get("run_id")
            or gate.get("target_run_id") != phase.get("target_run_id")
            or gate_time > phase_time
            or (must_postdate is not None and gate_time <= must_postdate)
        ):
            raise V32CurrentResearchAuthorityError(code)
        subjects = gate.get("subject_bindings")
        if not isinstance(subjects, list) or not subjects:
            raise V32CurrentResearchAuthorityError(code)
        capability = next(
            (
                name
                for name, mapped_gate in CAPABILITY_GATE_MAP.items()
                if mapped_gate == gate_id
            ),
            None,
        )
        if phase.get("profile") == TARGET_PHASE_PROFILE and capability is not None:
            if (
                actual_capability_bindings is None
                or subjects != [actual_capability_bindings.get(capability)]
            ):
                raise V32CurrentResearchAuthorityError(code)
            # The exact typed receipt was already loaded through its Domain
            # verifier and its evidence root is replayed by the owning port.
            # Do not downgrade it to the generic self-digest subject path.
        else:
            if len(subjects) != 1:
                raise V32CurrentResearchAuthorityError(code)
            subject, _ = _load_bound_document(
                project,
                subjects[0],
                schema_id=PREFLIGHT_SUBJECT_SCHEMA_ID,
                digest_field=PREFLIGHT_SUBJECT_DIGEST_FIELD,
                verifier=verify_v32_typed_preflight_gate_subject_v1,
                code=code,
                expected_path=_runtime_ref(
                    runtime_root,
                    f"{directory}/subjects/{gate_id.lower()}.json",
                ),
            )
            required_roles = PREFLIGHT_GATE_ANCHOR_ROLES[gate_id]
            expected_anchors = {
                role: expected_preflight_anchors.get(role)
                for role in required_roles
            }
            expected_paths = tuple(subject["implementation_bindings"])
            manifest_bindings = manifest.get("implementation_bindings")
            if (
                subject.get("gate_id") != gate_id
                or subject.get("profile") != phase.get("profile")
                or subject.get("run_id") != phase.get("run_id")
                or subject.get("target_run_id") != phase.get("target_run_id")
                or _moment(subject.get("evaluated_at"), code) != gate_time
                or tuple(subject.get("anchor_bindings", {})) != required_roles
                or subject.get("anchor_bindings") != expected_anchors
                or not isinstance(manifest_bindings, Mapping)
                or any(
                    manifest_bindings.get(path)
                    != subject["implementation_bindings"].get(path)
                    for path in expected_paths
                )
            ):
                raise V32CurrentResearchAuthorityError(code)
            for relative_ref, expected_sha in subject[
                "implementation_bindings"
            ].items():
                path = _contained_file(project, relative_ref, code)
                if _sha256(path) != expected_sha:
                    raise V32CurrentResearchAuthorityError(code)
        documents[gate_id] = gate
    return documents


def _validate_legacy_replay(
    chain: Mapping[str, Any], failure: Mapping[str, Any]
) -> None:
    try:
        authority = chain["authority"]
        receipts = chain["qualification_receipts"]
        implementations = chain["manifest"]["implementation_bindings"]
        research = failure["research_checkpoint"]
        monitor = failure["monitor_checkpoint"]
        failure_document = failure["monitor_failure"]
        attempt = failure["resolution_attempt"]
    except (KeyError, TypeError) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_LEGACY_REPLAY_INCOMPLETE"
        ) from exc
    if (
        authority.get("authorized_run_id") != V311_LEGACY_RUN_ID
        or tuple(receipts) != Q0_Q8_GATE_IDS
        or len(implementations) != 74
        or research.get("status") != "READY_FOR_CYCLE"
        or research.get("completed_cycles") != 1
        or monitor.get("status") != "FAILED_CLOSED"
        or monitor.get("resume_allowed") is not False
        or monitor.get("outcome_bindings") != []
        or failure_document.get("resume_allowed") is not False
        or failure_document.get("reserved_attempts") != 1
        or failure_document.get("resolved_cycles") != 0
        or attempt.get("attempt_number") != 1
        or attempt.get("retry_allowed") is not False
    ):
        raise V32CurrentResearchAuthorityError("V32_LEGACY_REPLAY_NOT_EXACT")


def replay_v32_legacy_predecessor(
    project_root: Path,
) -> dict[str, Any]:
    """Replay the real V3.1 chain and permanent failure before V3.2 Phase A."""

    project = _project_root(project_root)
    try:
        legacy_chain = load_v31_active_authorization_chain(project)
        legacy_failure = load_v311_legacy_failure_evidence_v2(
            project, legacy_active_chain=legacy_chain
        )
    except (
        V31AuthorizationError,
        V311SuccessorAuthorityEnvelopeV2Error,
        TypeError,
        ValueError,
    ) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_LEGACY_FULL_LOADER_FAILED"
        ) from exc
    _validate_legacy_replay(legacy_chain, legacy_failure)
    binding = _file_binding(
        project,
        relative_ref=V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
        document=legacy_chain["authority"],
        digest_field="authority_digest",
    )
    return {
        "legacy_active_chain": legacy_chain,
        "legacy_failure_evidence": legacy_failure,
        "predecessor_authority_binding": binding,
        "full_replay_verified": True,
        "replay_network_calls": 0,
    }


def _verify_theory_bytes(
    project: Path,
    approval: Mapping[str, Any],
    contract: Mapping[str, Any],
    theory_semantic_document: Mapping[str, Any],
    theory_semantic_binding: Mapping[str, Any],
) -> None:
    approval_binding = approval["theory_binding"]
    contract_binding = contract["theory_binding"]
    if (
        contract_binding.get("relative_ref") != approval_binding.get("relative_ref")
        or contract_binding.get("theory_version") != THEORY_VERSION
        or contract_binding.get("physical_sha256")
        != approval_binding.get("physical_sha256")
        or contract_binding.get("semantic_digest")
        != approval_binding.get("semantic_digest")
    ):
        raise V32CurrentResearchAuthorityError("V32_THEORY_BINDING_MISMATCH")
    path = _contained_file(
        project,
        approval_binding.get("relative_ref"),
        "V32_THEORY_PATH_INVALID",
    )
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise V32CurrentResearchAuthorityError("V32_THEORY_UTF8_INVALID") from exc
    if text.startswith("\ufeff") or hashlib.sha256(payload).hexdigest() != approval_binding.get(
        "physical_sha256"
    ):
        raise V32CurrentResearchAuthorityError("V32_THEORY_PHYSICAL_DRIFT")
    try:
        rebuilt = build_v32_theory_semantic_document_v1(
            theory_source_binding={
                "path": approval_binding["relative_ref"],
                "version": approval_binding["theory_version"],
                "review_status": "FROZEN_APPROVED",
                "physical_sha256": approval_binding["physical_sha256"],
            },
            markdown_utf8=text,
        )
        semantic = verify_v32_theory_semantic_document_v1(
            theory_semantic_document
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_THEORY_SEMANTIC_DOCUMENT_INVALID"
        ) from exc
    if (
        dict(theory_semantic_document) != rebuilt
        or semantic != approval_binding.get("semantic_digest")
        or theory_semantic_binding.get("semantic_digest") != semantic
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_THEORY_SEMANTIC_DOCUMENT_INVALID"
        )


def _same_common_bindings(
    document: Mapping[str, Any],
    *,
    approval_binding: Mapping[str, Any],
    contract_binding: Mapping[str, Any],
    manifest_binding: Mapping[str, Any],
) -> bool:
    return (
        document.get("theory_approval_binding") == approval_binding
        and document.get("experiment_contract_binding") == contract_binding
        and document.get("runtime_manifest_binding") == manifest_binding
    )


def load_v32_qualification_phase_a_authority(
    project_root: Path,
    *,
    expected_target_run_id: str,
    expected_qualification_run_id: str,
) -> dict[str, Any]:
    """Replay the immutable qualification authority before any runtime port.

    This is the sole Phase-A admission loader for qualification wakeups.  It
    deliberately returns the verified internal documents needed by the
    composition root rather than the five-document target projection exposed
    after Phase B.
    """

    project = _project_root(project_root)
    try:
        target, qualification = validate_v32_active_qualification_identity_v1(
            target_run_id=expected_target_run_id,
            qualification_run_id=expected_qualification_run_id,
        )
    except V32QualificationIdentityError as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_IDENTITY_INVALID"
        ) from exc

    # Nothing in the V3.2 namespace is opened before the complete historical
    # authority and permanent-failure lineage has passed.
    legacy = replay_v32_legacy_predecessor(project)
    legacy_authority_binding = legacy["predecessor_authority_binding"]
    runtime_paths = _assert_exact_runtime_namespace(
        project,
        target_run_id=target,
        qualification_run_id=qualification,
    )
    runtime_root = runtime_paths["root"]

    authority_ref = _runtime_ref(
        runtime_root, "qualification/authority.json"
    )
    authority_path = _contained_file(
        project,
        authority_ref,
        "V32_QUALIFICATION_AUTHORITY_FILE_INVALID",
    )
    authority = _strict_document(
        authority_path, "V32_QUALIFICATION_AUTHORITY_JSON_INVALID"
    )
    try:
        verify_v32_authority_v1(authority)
        canonical_authority = canonical_bytes(authority) + b"\n"
    except (TypeError, ValueError) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_AUTHORITY_INVALID"
        ) from exc
    if authority_path.read_bytes() != canonical_authority:
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_AUTHORITY_BYTES_INVALID"
        )
    authority_binding = _file_binding(
        project,
        relative_ref=authority_ref,
        document=authority,
        digest_field=AUTHORITY_DIGEST_FIELD,
    )
    if (
        authority.get("profile") != QUALIFICATION_PROFILE
        or authority.get("run_id") != qualification
        or authority.get("target_run_id") != target
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_AUTHORITY_PROFILE_OR_RUN_INVALID"
        )

    approval, approval_binding = _load_bound_document(
        project,
        authority.get("theory_approval_binding"),
        schema_id=THEORY_APPROVAL_SCHEMA_ID,
        digest_field=THEORY_APPROVAL_DIGEST_FIELD,
        verifier=verify_v32_theory_approval_receipt_v1,
        code="V32_THEORY_APPROVAL_BINDING_INVALID",
        expected_path=_runtime_ref(runtime_root, "theory-approval.json"),
    )
    contract, contract_binding = _load_bound_document(
        project,
        authority.get("experiment_contract_binding"),
        schema_id=EXPERIMENT_CONTRACT_SCHEMA_ID,
        digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
        verifier=verify_v32_experiment_contract_v1,
        code="V32_EXPERIMENT_CONTRACT_BINDING_INVALID",
        expected_path=_runtime_ref(runtime_root, "experiment-contract.json"),
    )
    manifest, manifest_binding = _load_bound_document(
        project,
        authority.get("runtime_manifest_binding"),
        schema_id=RUNTIME_MANIFEST_SCHEMA_ID,
        digest_field=RUNTIME_MANIFEST_DIGEST_FIELD,
        verifier=verify_v32_runtime_manifest,
        code="V32_RUNTIME_MANIFEST_BINDING_INVALID",
        expected_path=_runtime_ref(runtime_root, "runtime-manifest.json"),
    )
    theory_semantic_document, theory_semantic_binding = _load_bound_document(
        project,
        manifest.get("theory_semantic_document_binding"),
        schema_id=THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
        digest_field=THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
        verifier=verify_v32_theory_semantic_document_v1,
        code="V32_THEORY_SEMANTIC_DOCUMENT_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "theory-semantic-document.json"
        ),
    )
    phase, phase_binding = _load_bound_document(
        project,
        authority.get("phase_a_receipt_binding"),
        schema_id=PHASE_A_SCHEMA_ID,
        digest_field=PHASE_A_DIGEST_FIELD,
        verifier=verify_v32_phase_a_qualification_receipt_v1,
        code="V32_QUALIFICATION_PHASE_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "qualification/phase-a.json"
        ),
    )
    authorization, authorization_binding = _load_bound_document(
        project,
        authority.get("authorization_receipt_binding"),
        schema_id=AUTHORIZATION_RECEIPT_SCHEMA_ID,
        digest_field=AUTHORIZATION_RECEIPT_DIGEST_FIELD,
        verifier=verify_v32_authorization_receipt_v1,
        code="V32_QUALIFICATION_AUTHORIZATION_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "qualification/authorization.json"
        ),
    )

    fresh_process_trace = _replay_manifest_fresh_process_trace_if_required(
        project, manifest=manifest, runtime_root=runtime_root
    )
    try:
        verify_v31_runtime_closure_bindings_v2(
            project_root=project,
            production_root_paths=manifest["production_root_paths"],
            trace_paths=manifest["fresh_trace_paths"],
            frozen_bindings=manifest["implementation_bindings"],
        )
    except (KeyError, TypeError, ValueError, V31RuntimeClosureError) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_RUNTIME_CLOSURE_PHYSICAL_REPLAY_INVALID"
        ) from exc
    _verify_theory_bytes(
        project,
        approval,
        contract,
        theory_semantic_document,
        theory_semantic_binding,
    )
    support_documents = _load_support_documents(
        project,
        manifest=manifest,
        contract=contract,
        runtime_root=runtime_root,
    )

    approval_digest = approval[THEORY_APPROVAL_DIGEST_FIELD]
    contract_digest = contract[EXPERIMENT_CONTRACT_DIGEST_FIELD]
    manifest_digest = manifest[RUNTIME_MANIFEST_DIGEST_FIELD]
    if (
        contract.get("run_id") != target
        or manifest.get("target_run_id") != target
        or manifest.get("qualification_run_id") != qualification
        or manifest.get("theory_approval_binding") != approval_binding
        or manifest.get("experiment_contract_binding") != contract_binding
        or authority.get("predecessor_authority_binding")
        != legacy_authority_binding
        or not _same_common_bindings(
            authority,
            approval_binding=approval_binding,
            contract_binding=contract_binding,
            manifest_binding=manifest_binding,
        )
        or authority.get("phase_a_receipt_binding") != phase_binding
        or authority.get("authorization_receipt_binding")
        != authorization_binding
        or authority.get("qualification_retirement_binding") is not None
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_AUTHORITY_CHAIN_DISCONNECTED"
        )
    if (
        phase.get("profile") != QUALIFICATION_PHASE_PROFILE
        or phase.get("run_id") != qualification
        or phase.get("target_run_id") != target
        or phase.get("theory_approval_digest") != approval_digest
        or phase.get("experiment_contract_digest") != contract_digest
        or phase.get("runtime_manifest_digest") != manifest_digest
        or tuple(phase.get("q0_q8_evidence_bindings", {}))
        != Q0_Q8_GATE_IDS
        or phase.get("predecessor_retirement_digest") is not None
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_PHASE_CHAIN_DISCONNECTED"
        )
    if (
        authorization.get("profile") != QUALIFICATION_PROFILE
        or authorization.get("run_id") != qualification
        or authorization.get("target_run_id") != target
        or not _same_common_bindings(
            authorization,
            approval_binding=approval_binding,
            contract_binding=contract_binding,
            manifest_binding=manifest_binding,
        )
        or authorization.get("phase_a_receipt_binding") != phase_binding
        or authorization.get("qualification_retirement_binding") is not None
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_AUTHORIZATION_CHAIN_DISCONNECTED"
        )

    manifest_created = _moment(
        manifest.get("created_at"), "V32_CHRONOLOGY_INVALID"
    )
    common_preflight_anchors = {
        "theory_approval": approval_binding,
        "experiment_contract": contract_binding,
        "runtime_manifest": manifest_binding,
        "clock_policy": manifest["support_document_bindings"][
            "clock_policy_digest"
        ],
        "outcome_adapter_contract": manifest["support_document_bindings"][
            "outcome_adapter_contract_digest"
        ],
        "predecessor_authority": legacy_authority_binding,
    }
    gates = _load_phase_gate_evidence(
        project,
        phase,
        must_postdate=manifest_created,
        code="V32_QUALIFICATION_GATE_EVIDENCE_INVALID",
        manifest=manifest,
        expected_preflight_anchors=common_preflight_anchors,
        runtime_root=runtime_root,
        directory="qualification",
    )

    workspace_observed = _moment(
        support_documents["workspace_freeze_receipt_digest"].get(
            "observed_at"
        ),
        "V32_CHRONOLOGY_INVALID",
    )
    fresh_trace_completed = (
        None
        if fresh_process_trace is None
        else _moment(
            fresh_process_trace.get("completed_at"),
            "V32_CHRONOLOGY_INVALID",
        )
    )
    contract_frozen = _moment(
        contract.get("frozen_at"), "V32_CHRONOLOGY_INVALID"
    )
    runtime_frozen = _moment(
        manifest.get("runtime_frozen_at"), "V32_CHRONOLOGY_INVALID"
    )
    approved = _moment(
        approval.get("approved_at"), "V32_CHRONOLOGY_INVALID"
    )
    phase_evaluated = _moment(
        phase.get("evaluated_at"), "V32_CHRONOLOGY_INVALID"
    )
    authorization_issued = _moment(
        authorization.get("issued_at"), "V32_CHRONOLOGY_INVALID"
    )
    authority_recorded = _moment(
        authority.get("recorded_at"), "V32_CHRONOLOGY_INVALID"
    )
    if not (
        (fresh_trace_completed is None or fresh_trace_completed <= workspace_observed)
        and workspace_observed
        <= contract_frozen
        <= runtime_frozen
        <= approved
        <= manifest_created
        < phase_evaluated
        <= authorization_issued
        <= authority_recorded
    ):
        raise V32CurrentResearchAuthorityError("V32_CHRONOLOGY_INVALID")

    # Close a possible replacement/symlink race after every bound file and
    # transitive implementation path has been reopened.
    _assert_exact_runtime_namespace(
        project,
        target_run_id=target,
        qualification_run_id=qualification,
    )
    return {
        "legacy_predecessor": legacy,
        "runtime_paths": runtime_paths,
        "runtime_root_relative_ref": runtime_root,
        "theory_approval": approval,
        "theory_approval_binding": approval_binding,
        "experiment_contract": contract,
        "experiment_contract_binding": contract_binding,
        "runtime_manifest": manifest,
        "runtime_manifest_binding": manifest_binding,
        "theory_semantic_document": theory_semantic_document,
        "theory_semantic_document_binding": theory_semantic_binding,
        "support_documents": support_documents,
        "qualification_phase": phase,
        "qualification_phase_binding": phase_binding,
        "qualification_gates": gates,
        "qualification_authorization": authorization,
        "qualification_authorization_binding": authorization_binding,
        "qualification_authority": authority,
        "qualification_authority_binding": authority_binding,
        "full_replay_verified": True,
        "replay_network_calls": 0,
    }


def load_v32_current_research_authority(
    project_root: Path,
    *,
    expected_run_id: str,
    authority_relative_path: str | None = None,
    capability_verifiers: Mapping[
        str, V32ActualCapabilityFullReplayVerifier
    ] | None = None,
) -> dict[str, dict[str, Any]]:
    """Verify the full old+V3.2 chain and return the exact five-doc projection."""

    project = _project_root(project_root)
    try:
        expected_run_id = validate_v32_run_id_syntax_v1(expected_run_id)
    except V32QualificationIdentityError as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_EXPECTED_RUN_ID_INVALID"
        ) from exc
    if expected_run_id in TOMBSTONED_V32_RUN_IDS:
        raise V32CurrentResearchAuthorityError("V32_EXPECTED_RUN_ID_INVALID")

    # P0 ordering: complete historical semantic/physical/failure proof first.
    legacy = replay_v32_legacy_predecessor(project)
    legacy_authority_binding = legacy["predecessor_authority_binding"]
    verifier_registry = _capability_verifier_registry(capability_verifiers)

    expected_authority_ref = V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix()
    if authority_relative_path is not None and _relative(
        authority_relative_path, "V32_AUTHORITY_PATH_INVALID"
    ) != expected_authority_ref:
        raise V32CurrentResearchAuthorityError(
            "V32_ALTERNATE_AUTHORITY_ROOT_FORBIDDEN"
        )
    authority_path = _contained_file(
        project, expected_authority_ref, "V32_TARGET_AUTHORITY_FILE_INVALID"
    )
    target_authority = _strict_document(
        authority_path, "V32_TARGET_AUTHORITY_JSON_INVALID"
    )
    try:
        verify_v32_authority_v1(target_authority)
    except V32AuthorizationError as exc:
        raise V32CurrentResearchAuthorityError("V32_TARGET_AUTHORITY_INVALID") from exc
    if (
        target_authority.get("profile") != TARGET_PROFILE
        or target_authority.get("run_id") != expected_run_id
        or target_authority.get("target_run_id") != expected_run_id
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_TARGET_AUTHORITY_PROFILE_OR_RUN_INVALID"
        )

    qualification_run_id = _qualification_from_exact_binding_path(
        target_authority.get("runtime_manifest_binding"),
        suffix="runtime-manifest.json",
        code="V32_RUNTIME_MANIFEST_BINDING_INVALID",
    )
    runtime_paths = _assert_exact_runtime_namespace(
        project,
        target_run_id=expected_run_id,
        qualification_run_id=qualification_run_id,
    )
    runtime_root = runtime_paths["root"]

    approval, approval_binding = _load_bound_document(
        project,
        target_authority["theory_approval_binding"],
        schema_id=THEORY_APPROVAL_SCHEMA_ID,
        digest_field=THEORY_APPROVAL_DIGEST_FIELD,
        verifier=verify_v32_theory_approval_receipt_v1,
        code="V32_THEORY_APPROVAL_BINDING_INVALID",
        expected_path=_runtime_ref(runtime_root, "theory-approval.json"),
    )
    contract, contract_binding = _load_bound_document(
        project,
        target_authority["experiment_contract_binding"],
        schema_id=EXPERIMENT_CONTRACT_SCHEMA_ID,
        digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
        verifier=verify_v32_experiment_contract_v1,
        code="V32_EXPERIMENT_CONTRACT_BINDING_INVALID",
        expected_path=_runtime_ref(runtime_root, "experiment-contract.json"),
    )
    manifest, manifest_binding = _load_bound_document(
        project,
        target_authority["runtime_manifest_binding"],
        schema_id=RUNTIME_MANIFEST_SCHEMA_ID,
        digest_field=RUNTIME_MANIFEST_DIGEST_FIELD,
        verifier=verify_v32_runtime_manifest,
        code="V32_RUNTIME_MANIFEST_BINDING_INVALID",
        expected_path=_runtime_ref(runtime_root, "runtime-manifest.json"),
    )
    theory_semantic_document, theory_semantic_binding = _load_bound_document(
        project,
        manifest["theory_semantic_document_binding"],
        schema_id=THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
        digest_field=THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
        verifier=verify_v32_theory_semantic_document_v1,
        code="V32_THEORY_SEMANTIC_DOCUMENT_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "theory-semantic-document.json"
        ),
    )
    target_phase, target_phase_binding = _load_bound_document(
        project,
        target_authority["phase_a_receipt_binding"],
        schema_id=PHASE_A_SCHEMA_ID,
        digest_field=PHASE_A_DIGEST_FIELD,
        verifier=verify_v32_phase_a_qualification_receipt_v1,
        code="V32_TARGET_PHASE_BINDING_INVALID",
        expected_path=_runtime_ref(runtime_root, "target/phase-a.json"),
    )
    target_authorization, target_authorization_binding = _load_bound_document(
        project,
        target_authority["authorization_receipt_binding"],
        schema_id=AUTHORIZATION_RECEIPT_SCHEMA_ID,
        digest_field=AUTHORIZATION_RECEIPT_DIGEST_FIELD,
        verifier=verify_v32_authorization_receipt_v1,
        code="V32_TARGET_AUTHORIZATION_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "target/authorization.json"
        ),
    )
    retirement, retirement_binding = _load_bound_document(
        project,
        target_authority["qualification_retirement_binding"],
        schema_id=QUALIFICATION_RETIREMENT_SCHEMA_ID,
        digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        verifier=verify_v32_qualification_retirement_receipt_v1,
        code="V32_RETIREMENT_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "qualification/retirement.json"
        ),
    )
    qualification_authority, qualification_authority_binding = _load_bound_document(
        project,
        retirement["qualification_authority_binding"],
        schema_id=AUTHORITY_SCHEMA_ID,
        digest_field=AUTHORITY_DIGEST_FIELD,
        verifier=verify_v32_authority_v1,
        code="V32_QUALIFICATION_AUTHORITY_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "qualification/authority.json"
        ),
    )
    qualification_receipt, qualification_receipt_binding = _load_bound_document(
        project,
        retirement["qualification_receipt_binding"],
        schema_id=QUALIFICATION_RECEIPT_SCHEMA_ID,
        digest_field=QUALIFICATION_RECEIPT_DIGEST_FIELD,
        verifier=verify_v32_fresh_capability_qualification_receipt_v1,
        code="V32_QUALIFICATION_RECEIPT_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root,
            "evidence/seal-bundle/qualification-receipt.json",
        ),
    )
    qualification_phase, qualification_phase_binding = _load_bound_document(
        project,
        qualification_authority["phase_a_receipt_binding"],
        schema_id=PHASE_A_SCHEMA_ID,
        digest_field=PHASE_A_DIGEST_FIELD,
        verifier=verify_v32_phase_a_qualification_receipt_v1,
        code="V32_QUALIFICATION_PHASE_BINDING_INVALID",
        expected_path=_runtime_ref(
            runtime_root, "qualification/phase-a.json"
        ),
    )
    qualification_authorization, qualification_authorization_binding = (
        _load_bound_document(
            project,
            qualification_authority["authorization_receipt_binding"],
            schema_id=AUTHORIZATION_RECEIPT_SCHEMA_ID,
            digest_field=AUTHORIZATION_RECEIPT_DIGEST_FIELD,
            verifier=verify_v32_authorization_receipt_v1,
            code="V32_QUALIFICATION_AUTHORIZATION_BINDING_INVALID",
            expected_path=_runtime_ref(
                runtime_root, "qualification/authorization.json"
            ),
        )
    )
    capability_receipts, capability_receipt_bindings = (
        _load_actual_capability_receipts(
            project,
            qualification_receipt=qualification_receipt,
            qualification_authority=qualification_authority,
            qualification_authority_binding=qualification_authority_binding,
            runtime_root=runtime_root,
        )
    )

    fresh_process_trace = _replay_manifest_fresh_process_trace_if_required(
        project, manifest=manifest, runtime_root=runtime_root
    )
    try:
        verify_v31_runtime_closure_bindings_v2(
            project_root=project,
            production_root_paths=manifest["production_root_paths"],
            trace_paths=manifest["fresh_trace_paths"],
            frozen_bindings=manifest["implementation_bindings"],
        )
    except (KeyError, TypeError, ValueError, V31RuntimeClosureError) as exc:
        raise V32CurrentResearchAuthorityError(
            "V32_RUNTIME_CLOSURE_PHYSICAL_REPLAY_INVALID"
        ) from exc
    _verify_theory_bytes(
        project,
        approval,
        contract,
        theory_semantic_document,
        theory_semantic_binding,
    )
    support_documents = _load_support_documents(
        project,
        manifest=manifest,
        contract=contract,
        runtime_root=runtime_root,
    )

    approval_digest = approval[THEORY_APPROVAL_DIGEST_FIELD]
    contract_digest = contract[EXPERIMENT_CONTRACT_DIGEST_FIELD]
    manifest_digest = manifest[RUNTIME_MANIFEST_DIGEST_FIELD]
    if (
        contract.get("run_id") != expected_run_id
        or manifest.get("target_run_id") != expected_run_id
        or qualification_run_id == expected_run_id
        or manifest.get("theory_approval_binding") != approval_binding
        or manifest.get("experiment_contract_binding") != contract_binding
        or target_authority.get("predecessor_authority_binding")
        != qualification_authority_binding
        or qualification_authority.get("predecessor_authority_binding")
        != legacy_authority_binding
        or qualification_authority.get("profile") != QUALIFICATION_PROFILE
        or qualification_authority.get("run_id") != qualification_run_id
        or qualification_authority.get("target_run_id") != expected_run_id
        or not _same_common_bindings(
            qualification_authority,
            approval_binding=approval_binding,
            contract_binding=contract_binding,
            manifest_binding=manifest_binding,
        )
        or not _same_common_bindings(
            target_authority,
            approval_binding=approval_binding,
            contract_binding=contract_binding,
            manifest_binding=manifest_binding,
        )
        or qualification_authority.get("phase_a_receipt_binding")
        != qualification_phase_binding
        or qualification_authority.get("authorization_receipt_binding")
        != qualification_authorization_binding
        or qualification_authority.get("qualification_retirement_binding")
        is not None
        or target_authority.get("phase_a_receipt_binding") != target_phase_binding
        or target_authority.get("authorization_receipt_binding")
        != target_authorization_binding
        or target_authority.get("qualification_retirement_binding")
        != retirement_binding
    ):
        raise V32CurrentResearchAuthorityError("V32_AUTHORITY_CHAIN_DISCONNECTED")

    for phase, expected_profile, expected_phase_run in (
        (qualification_phase, QUALIFICATION_PHASE_PROFILE, qualification_run_id),
        (target_phase, TARGET_PHASE_PROFILE, expected_run_id),
    ):
        if (
            phase.get("profile") != expected_profile
            or phase.get("run_id") != expected_phase_run
            or phase.get("target_run_id") != expected_run_id
            or phase.get("theory_approval_digest") != approval_digest
            or phase.get("experiment_contract_digest") != contract_digest
            or phase.get("runtime_manifest_digest") != manifest_digest
            or tuple(phase.get("q0_q8_evidence_bindings", {}))
            != Q0_Q8_GATE_IDS
        ):
            raise V32CurrentResearchAuthorityError("V32_PHASE_CHAIN_DISCONNECTED")
    if (
        qualification_phase.get("predecessor_retirement_digest") is not None
        or target_phase.get("predecessor_retirement_digest")
        != retirement[QUALIFICATION_RETIREMENT_DIGEST_FIELD]
    ):
        raise V32CurrentResearchAuthorityError("V32_PHASE_PREDECESSOR_INVALID")

    retired_time = _moment(retirement["retired_at"], "V32_CHRONOLOGY_INVALID")
    common_preflight_anchors = {
        "theory_approval": approval_binding,
        "experiment_contract": contract_binding,
        "runtime_manifest": manifest_binding,
        "clock_policy": manifest["support_document_bindings"][
            "clock_policy_digest"
        ],
        "outcome_adapter_contract": manifest["support_document_bindings"][
            "outcome_adapter_contract_digest"
        ],
    }
    _load_phase_gate_evidence(
        project,
        qualification_phase,
        must_postdate=_moment(
            manifest["created_at"], "V32_CHRONOLOGY_INVALID"
        ),
        code="V32_QUALIFICATION_GATE_EVIDENCE_INVALID",
        manifest=manifest,
        expected_preflight_anchors={
            **common_preflight_anchors,
            "predecessor_authority": legacy_authority_binding,
        },
        runtime_root=runtime_root,
        directory="qualification",
    )
    _load_phase_gate_evidence(
        project,
        target_phase,
        must_postdate=retired_time,
        code="V32_TARGET_GATE_EVIDENCE_INVALID",
        manifest=manifest,
        expected_preflight_anchors={
            **common_preflight_anchors,
            "predecessor_authority": qualification_authority_binding,
        },
        actual_capability_bindings=capability_receipt_bindings,
        runtime_root=runtime_root,
        directory="target",
    )

    for authorization, profile, phase_binding in (
        (
            qualification_authorization,
            QUALIFICATION_PROFILE,
            qualification_phase_binding,
        ),
        (target_authorization, TARGET_PROFILE, target_phase_binding),
    ):
        if (
            authorization.get("profile") != profile
            or authorization.get("target_run_id") != expected_run_id
            or authorization.get("run_id")
            != (qualification_run_id if profile == QUALIFICATION_PROFILE else expected_run_id)
            or not _same_common_bindings(
                authorization,
                approval_binding=approval_binding,
                contract_binding=contract_binding,
                manifest_binding=manifest_binding,
            )
            or authorization.get("phase_a_receipt_binding") != phase_binding
            or (
                profile == QUALIFICATION_PROFILE
                and authorization.get("qualification_retirement_binding") is not None
            )
            or (
                profile == TARGET_PROFILE
                and authorization.get("qualification_retirement_binding")
                != retirement_binding
            )
        ):
            raise V32CurrentResearchAuthorityError(
                "V32_AUTHORIZATION_CHAIN_DISCONNECTED"
            )

    if qualification_receipt.get(
        "capability_evidence_bindings"
    ) != capability_receipt_bindings:
        raise V32CurrentResearchAuthorityError(
            "V32_CAPABILITY_GATE_MAPPING_INVALID"
        )

    if (
        qualification_receipt.get("qualification_run_id") != qualification_run_id
        or qualification_receipt.get("target_run_id") != expected_run_id
        or qualification_receipt.get("qualification_authority_binding")
        != qualification_authority_binding
        or retirement.get("qualification_run_id") != qualification_run_id
        or retirement.get("target_run_id") != expected_run_id
        or retirement.get("qualification_authority_binding")
        != qualification_authority_binding
        or retirement.get("qualification_receipt_binding")
        != qualification_receipt_binding
    ):
        raise V32CurrentResearchAuthorityError(
            "V32_QUALIFICATION_RETIREMENT_CHAIN_DISCONNECTED"
        )

    contract_frozen = _moment(contract["frozen_at"], "V32_CHRONOLOGY_INVALID")
    runtime_frozen = _moment(
        manifest["runtime_frozen_at"], "V32_CHRONOLOGY_INVALID"
    )
    approved = _moment(approval["approved_at"], "V32_CHRONOLOGY_INVALID")
    manifest_created = _moment(manifest["created_at"], "V32_CHRONOLOGY_INVALID")
    qualification_phase_time = _moment(
        qualification_phase["evaluated_at"], "V32_CHRONOLOGY_INVALID"
    )
    workspace_observed = _moment(
        support_documents["workspace_freeze_receipt_digest"]["observed_at"],
        "V32_CHRONOLOGY_INVALID",
    )
    fresh_trace_completed = (
        None
        if fresh_process_trace is None
        else _moment(
            fresh_process_trace.get("completed_at"),
            "V32_CHRONOLOGY_INVALID",
        )
    )
    qualification_authorized = _moment(
        qualification_authorization["issued_at"], "V32_CHRONOLOGY_INVALID"
    )
    qualification_recorded = _moment(
        qualification_authority["recorded_at"], "V32_CHRONOLOGY_INVALID"
    )
    qualification_started = _moment(
        qualification_receipt["started_at"], "V32_CHRONOLOGY_INVALID"
    )
    qualification_completed = _moment(
        qualification_receipt["completed_at"], "V32_CHRONOLOGY_INVALID"
    )
    capability_windows = {
        capability: (
            _moment(receipt["started_at"], "V32_CHRONOLOGY_INVALID"),
            _moment(receipt["completed_at"], "V32_CHRONOLOGY_INVALID"),
        )
        for capability, receipt in capability_receipts.items()
    }
    retired = retired_time
    target_phase_time = _moment(
        target_phase["evaluated_at"], "V32_CHRONOLOGY_INVALID"
    )
    target_authorized = _moment(
        target_authorization["issued_at"], "V32_CHRONOLOGY_INVALID"
    )
    target_recorded = _moment(
        target_authority["recorded_at"], "V32_CHRONOLOGY_INVALID"
    )
    if not (
        (fresh_trace_completed is None or fresh_trace_completed <= workspace_observed)
        and workspace_observed
        <= contract_frozen
        <= runtime_frozen
        <= approved
        <= manifest_created
        < qualification_phase_time
        <= qualification_authorized
        <= qualification_recorded
        < qualification_started
        <= qualification_completed
        <= retired
        < target_phase_time
        <= target_authorized
        <= target_recorded
        and all(
            qualification_started <= started <= completed <= qualification_completed
            for started, completed in capability_windows.values()
        )
    ):
        raise V32CurrentResearchAuthorityError("V32_CHRONOLOGY_INVALID")

    _replay_actual_capability_evidence(
        project,
        capability_receipts=capability_receipts,
        qualification_authority=qualification_authority,
        verifier_registry=verifier_registry,
        runtime_root=runtime_root,
    )

    # A final physical namespace pass makes post-load symlink insertion or
    # component replacement fail closed before Application sees any document.
    _assert_exact_runtime_namespace(
        project,
        target_run_id=expected_run_id,
        qualification_run_id=qualification_run_id,
    )

    projection = {
        "theory_approval": approval,
        "experiment_contract": contract,
        "manifest": manifest,
        "authorization_receipt": target_authorization,
        "authority": target_authority,
    }
    if tuple(projection) != V32_APPLICATION_PROJECTION_KEYS:
        raise V32CurrentResearchAuthorityError("V32_PROJECTION_INVALID")
    return projection


__all__ = [
    "V32ActualCapabilityFullReplayVerifier",
    "V32_APPLICATION_PROJECTION_KEYS",
    "V32_CURRENT_RESEARCH_AUTHORITY_PATH",
    "V32CurrentResearchAuthorityError",
    "load_v32_current_research_authority",
    "load_v32_qualification_phase_a_authority",
    "replay_v32_actual_capability_qualification_receipt",
    "replay_v32_legacy_predecessor",
]
