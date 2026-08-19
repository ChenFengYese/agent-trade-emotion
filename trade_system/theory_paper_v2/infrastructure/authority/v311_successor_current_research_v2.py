"""Read-only V3.1.1 successor authority loader.

Validation order is intentional and fail-closed:

1. replay the historical active V3.1 v2 chain, Q0-Q8, durable Q6/Q7
   evidence, and all 74 frozen implementation bytes;
2. prove the historical run is permanently stopped by its monitor failure;
3. load the standard V3 qualification authority and replay its one-cycle
   source/Codex/monitor evidence;
4. only then load the distinct standard V4 target authority for the formal
   eight-cycle run;
5. replay every V3.1.1 contract, import-closure byte, twelve-axis registry,
   preregistration, evaluation contract, and reconstruct the pure envelope.

The loader performs no run creation, network request, checkpoint mutation,
account access, order operation, or credential access.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ...application.v31_external_qualification import (
    V31ExternalQualificationWorkflowError,
    verify_q6_receipt_durable_artifacts,
    verify_q7_receipt_durable_artifacts,
)
from ...application.v31_successor_qualification_v2 import (
    V31SuccessorQualificationV2WorkflowError,
    verify_fresh_public_source_qualification_durable_v2,
    verify_monitor_qualification_durable_v2,
)
from ...application.v311_codex_durable_qualification_v3 import (
    V311CodexDurableQualificationV3WorkflowError,
    verify_current_codex_qualification_durable_v3,
)
from ...domain.contracts.canonical import (
    CanonicalContractError,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ...domain.governance.research_authority import (
    ResearchAuthorityError,
    validate_research_authority,
)
from ...domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_active_authority,
    validate_v31_document_binding,
    validate_v31_experiment_authorization,
    validate_v31_frozen_experiment_manifest,
    validate_v31_qualification_receipt,
    validate_v31_theory_approval,
)
from ...domain.governance.v31_experiment_qualification import (
    TYPED_QUALIFICATION_GATE_IDS,
    TYPED_QUALIFICATION_SCHEMA_ID,
)
from ...domain.governance.v31_external_qualification import (
    EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID,
)
from ...domain.governance.v31_successor_qualification_v2 import (
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    MONITOR_QUALIFICATION_SCHEMA_ID,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
    SOURCE_QUALIFICATION_SCHEMA_ID,
    V31SuccessorQualificationV2Error,
    verify_successor_monitor_qualification_v2,
    verify_successor_public_source_qualification_v2,
)
from ...domain.governance.v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    CODEX_QUALIFICATION_V3_SCHEMA_ID,
    V311CodexDurableQualificationV3Error,
    verify_successor_codex_durable_qualification_v3,
)
from ...domain.governance.v311_successor_authority_envelope_v2 import (
    ENVELOPE_DIGEST_FIELD,
    ENVELOPE_SCHEMA_ID,
    RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD,
    SUPERVISOR_POLICY_DIGEST_FIELD,
    V311_AUXILIARY_DOCUMENT_KEYS,
    V311_FRESH_QUALIFICATION_KEYS,
    V311_LEGACY_RUN_ID,
    V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
    V311_TARGET_ACTIVE_AUTHORITY_PATH,
    V311_THEORY_ADDENDUM_PATH,
    V311SuccessorAuthorityEnvelopeV2Error,
    verify_v311_runtime_closure_receipt_v2,
    verify_v311_successor_authority_envelope_v2,
    verify_v311_supervisor_policy_v2,
)
from ...domain.governance.v311_fresh_process_trace_v2 import (
    FRESH_PROCESS_TRACE_DIGEST_FIELD,
    FRESH_PROCESS_TRACE_SCHEMA_ID,
)
from ...domain.governance.v311_qualification_retirement_v2 import (
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_SCHEMA_ID,
    V311QualificationRetirementV2Error,
    build_v311_qualification_retirement_receipt_v2,
    verify_v311_qualification_retirement_receipt_v2,
)
from ...domain.governance.v311_successor_user_approval_v2 import (
    SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
    SUCCESSOR_USER_APPROVAL_SCHEMA_ID,
    V311SuccessorUserApprovalV2Error,
    verify_v311_successor_user_approval_receipt_v2,
)
from ...domain.governance.v311_qualification_genesis_v2 import (
    V311QualificationGenesisV2Error,
    v311_qualification_genesis_inputs_v2,
    verify_v311_qualification_run_genesis_v2,
)
from ...domain.v31_run_genesis import (
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_SCHEMA_ID,
)
from ...domain.v31_experiment_contracts import (
    EXPERIMENT_SCHEMA_ID,
    V31ExperimentContractError,
    verify_minimal_experiment_contract,
)
from ...domain.v31_outcome_capture_v2 import verify_outcome_clock_policy
from ...domain.v31_sentiment_native_projection_v2 import (
    verify_v31_native_sentiment_source_registry,
)
from ...domain.v31_association_preregistration_v2 import (
    verify_v31_association_preregistration_v2,
)
from ...domain.v31_evaluation_contract_v2 import (
    verify_v31_evaluation_contract_v2,
)
from ..v31_monitor_store import LocalV31MonitorStore, V31MonitorStoreError
from ..v31_research_store import LocalV31ResearchStore, V31ResearchStoreError
from .v31_current_research import load_v31_active_authorization_chain
from .v31_runtime_closure_v2 import (
    V31RuntimeClosureError,
    verify_v31_runtime_closure_bindings_v2,
)


V311_SUCCESSOR_AUTHORITY_ENVELOPE_PATH = Path(
    "config/theory_paper_v311.current_successor_authority_envelope.v2.json"
)

_V1_PREDECESSOR_PATH = "config/theory_paper_v2.current_research_authority.v1.json"
_GATE_IDS = tuple(f"Q{index}" for index in range(9))
_EXTERNAL_TYPED_GATE_IDS = ("Q6", "Q7")
_DOCUMENT_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_QUALIFICATION_ARTIFACT_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_RAW_BINDING_FIELDS = frozenset(
    {"relative_ref", "semantic_digest", "physical_sha256"}
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_PROJECT_ROOT_SYMLINK_FORBIDDEN"
            )
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_PROJECT_ROOT_INVALID"
        )
    return root


def _relative_path(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.as_posix() != value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return value


def _contained_regular_file(project: Path, relative_path: Any, code: str) -> Path:
    relative = _relative_path(relative_path, code)
    cursor = project
    try:
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V311SuccessorAuthorityEnvelopeV2Error(code)
        target = cursor.resolve(strict=True)
        target.relative_to(project)
    except V311SuccessorAuthorityEnvelopeV2Error:
        raise
    except (OSError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc
    if not target.is_file() or target.is_symlink():
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return target


def _contained_directory(project: Path, relative_path: Any, code: str) -> Path:
    relative = _relative_path(relative_path, code)
    cursor = project
    try:
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V311SuccessorAuthorityEnvelopeV2Error(code)
        target = cursor.resolve(strict=True)
        target.relative_to(project)
    except V311SuccessorAuthorityEnvelopeV2Error:
        raise
    except (OSError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc
    if not target.is_dir() or target.is_symlink():
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return target


def _load_strict(path: Path, code: str) -> dict[str, Any]:
    try:
        return load_json_strict(path)
    except (CanonicalContractError, OSError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc


def _load_bound_document(
    project: Path,
    binding: Any,
    *,
    schema_id: str,
    digest_field: str,
    code: str,
) -> dict[str, Any]:
    if not isinstance(binding, Mapping) or set(binding) != _DOCUMENT_BINDING_FIELDS:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    try:
        validate_v31_document_binding(
            binding,
            code=code,
            expected_schema_id=schema_id,
            expected_digest_field=digest_field,
        )
    except V31AuthorizationError as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc
    path = _contained_regular_file(project, binding["path"], f"{code}_PATH")
    if _sha256_file(path) != binding["physical_sha256"]:
        raise V311SuccessorAuthorityEnvelopeV2Error(f"{code}_PHYSICAL_DRIFT")
    document = _load_strict(path, f"{code}_JSON_INVALID")
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code}_SEMANTIC_DIGEST_INVALID"
        ) from exc
    if (
        document.get("schema_id") != schema_id
        or semantic != binding["semantic_digest"]
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code}_SEMANTIC_DRIFT"
        )
    return document


def _file_binding(
    project: Path,
    *,
    relative_path: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    path = _contained_regular_file(
        project, relative_path, "V311_EVIDENCE_BINDING_PATH_INVALID"
    )
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_EVIDENCE_BINDING_DIGEST_INVALID"
        ) from exc
    return {
        "path": relative_path,
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": _sha256_file(path),
    }


def _validate_standard_predecessor(
    project: Path, authority: Mapping[str, Any]
) -> dict[str, Any]:
    binding = authority.get("predecessor_authority_binding")
    if (
        not isinstance(binding, Mapping)
        or set(binding) != {"path", "physical_sha256", "expected_status"}
        or binding.get("path") != _V1_PREDECESSOR_PATH
        or binding.get("expected_status")
        != "FROZEN_V3_1_QUALIFICATION_PENDING"
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_STANDARD_PREDECESSOR_BINDING_INVALID"
        )
    path = _contained_regular_file(
        project, binding["path"], "V311_STANDARD_PREDECESSOR_PATH_INVALID"
    )
    if _sha256_file(path) != binding.get("physical_sha256"):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_STANDARD_PREDECESSOR_PHYSICAL_DRIFT"
        )
    predecessor = _load_strict(
        path, "V311_STANDARD_PREDECESSOR_JSON_INVALID"
    )
    try:
        validate_research_authority(predecessor)
    except ResearchAuthorityError as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_STANDARD_PREDECESSOR_SEMANTICS_INVALID"
        ) from exc
    current = predecessor.get("current_theory")
    if (
        predecessor.get("status") != binding["expected_status"]
        or predecessor.get("experiment_start_authorized") is not False
        or predecessor.get("authorized_operations") != []
        or predecessor.get("authorized_run_ids") != []
        or predecessor.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or predecessor.get("executable") is not False
        or not isinstance(current, Mapping)
        or current.get("version") != "3.1"
        or current.get("review_status") != "FROZEN_APPROVED"
        or current.get("path") != authority.get("current_theory", {}).get("path")
        or current.get("physical_sha256")
        != authority.get("current_theory", {}).get("physical_sha256")
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_STANDARD_PREDECESSOR_NOT_FROZEN_PENDING"
        )
    return predecessor


def _load_standard_chain(
    project: Path,
    envelope: Mapping[str, Any],
    *,
    envelope_section: str,
    expected_active_authority_path: str,
    code_prefix: str,
) -> dict[str, Any]:
    standard = envelope.get(envelope_section)
    if not isinstance(standard, Mapping):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_ENVELOPE_SECTION_INVALID"
        )
    bindings = standard.get("document_bindings")
    if not isinstance(bindings, Mapping):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_DOCUMENT_BINDINGS_INVALID"
        )
    specs = {
        "theory_approval": (
            "theory_paper_v31_user_approval_receipt",
            "approval_receipt_digest",
        ),
        "experiment_contract": (
            EXPERIMENT_SCHEMA_ID,
            "experiment_contract_digest",
        ),
        "manifest": (
            "theory_paper_v31_frozen_experiment_manifest",
            "manifest_digest",
        ),
        "authorization_receipt": (
            "theory_paper_v31_experiment_authorization_receipt",
            "authorization_receipt_digest",
        ),
        "authority": (
            "theory_paper_v31_current_research_authority",
            "authority_digest",
        ),
    }
    documents = {
        name: _load_bound_document(
            project,
            bindings.get(name),
            schema_id=schema_id,
            digest_field=digest_field,
            code=f"{code_prefix}_{name.upper()}_BINDING_INVALID",
        )
        for name, (schema_id, digest_field) in specs.items()
    }
    approval = documents["theory_approval"]
    contract = documents["experiment_contract"]
    manifest = documents["manifest"]
    authorization = documents["authorization_receipt"]
    authority = documents["authority"]
    if bindings["authority"]["path"] != expected_active_authority_path:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_ACTIVE_AUTHORITY_PATH_INVALID"
        )
    predecessor = _validate_standard_predecessor(project, authority)
    try:
        verify_minimal_experiment_contract(contract)
        validate_v31_theory_approval(approval)
        validate_v31_frozen_experiment_manifest(
            manifest,
            experiment_contract=contract,
            theory_approval=approval,
        )
        validate_v31_experiment_authorization(
            authorization,
            manifest=manifest,
            experiment_contract=contract,
            theory_approval=approval,
        )
        validate_v31_active_authority(
            authority,
            theory_approval=approval,
            manifest=manifest,
            experiment_contract=contract,
            authorization_receipt=authorization,
        )
    except (V31AuthorizationError, V31ExperimentContractError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_SEMANTIC_CHAIN_INVALID"
        ) from exc
    if (
        bindings["theory_approval"] != authority["theory_approval_binding"]
        or bindings["theory_approval"] != manifest["theory_approval_binding"]
        or bindings["experiment_contract"]
        != authority["experiment_contract_binding"]
        or bindings["experiment_contract"]
        != manifest["experiment_contract_binding"]
        or bindings["manifest"] != authority["manifest_binding"]
        or bindings["manifest"] != authorization["manifest_binding"]
        or bindings["authorization_receipt"]
        != authority["authorization_receipt_binding"]
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_TOP_LEVEL_BINDING_MISMATCH"
        )

    theory = authority.get("current_theory")
    if not isinstance(theory, Mapping):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_THEORY_BINDING_INVALID"
        )
    theory_path = _contained_regular_file(
        project,
        theory.get("path"),
        f"{code_prefix}_THEORY_PATH_INVALID",
    )
    if (
        _sha256_file(theory_path) != theory.get("physical_sha256")
        or approval.get("theory_path") != theory.get("path")
        or approval.get("theory_physical_sha256")
        != theory.get("physical_sha256")
        or manifest.get("theory_binding") != theory
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_THEORY_PHYSICAL_DRIFT"
        )

    receipts: dict[str, dict[str, Any]] = {}
    gates = manifest.get("qualification_gates")
    if not isinstance(gates, Mapping) or tuple(gates) != _GATE_IDS:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_Q0_Q8_SET_INVALID"
        )
    for gate_id in _GATE_IDS:
        if gate_id in TYPED_QUALIFICATION_GATE_IDS:
            schema_id = TYPED_QUALIFICATION_SCHEMA_ID
        elif gate_id in _EXTERNAL_TYPED_GATE_IDS:
            schema_id = EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID
        else:  # pragma: no cover - Q0-Q8 are currently all typed.
            schema_id = "theory_paper_v31_qualification_gate_receipt"
        receipt = _load_bound_document(
            project,
            gates[gate_id]["receipt_binding"],
            schema_id=schema_id,
            digest_field="qualification_receipt_digest",
            code=f"{code_prefix}_{gate_id}_BINDING_INVALID",
        )
        try:
            validate_v31_qualification_receipt(
                receipt,
                expected_gate_id=gate_id,
                experiment_contract=contract,
                manifest=manifest,
                theory_approval=approval,
            )
            if gate_id == "Q6":
                verify_q6_receipt_durable_artifacts(
                    project_root=project, receipt=receipt
                )
            elif gate_id == "Q7":
                verify_q7_receipt_durable_artifacts(
                    project_root=project, receipt=receipt
                )
                q6_evidence = receipts["Q6"].get("qualification_evidence")
                q7_evidence = receipt.get("qualification_evidence")
                if (
                    not isinstance(q6_evidence, Mapping)
                    or not isinstance(q7_evidence, Mapping)
                    or q7_evidence.get("terminal_assertions", {}).get(
                        "source_qualification_completion_digest"
                    )
                    != q6_evidence.get("completion", {}).get(
                        "source_qualification_completion_digest"
                    )
                ):
                    raise V311SuccessorAuthorityEnvelopeV2Error(
                        f"{code_prefix}_Q7_Q6_BINDING_MISMATCH"
                    )
        except (
            V31AuthorizationError,
            V31ExternalQualificationWorkflowError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, V311SuccessorAuthorityEnvelopeV2Error):
                raise
            raise V311SuccessorAuthorityEnvelopeV2Error(
                f"{code_prefix}_{gate_id}_REPLAY_INVALID"
            ) from exc
        receipts[gate_id] = receipt

    implementations = manifest.get("implementation_bindings")
    if not isinstance(implementations, Mapping) or not implementations:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            f"{code_prefix}_RUNTIME_BINDINGS_INVALID"
        )
    for relative_path, expected_sha256 in implementations.items():
        path = _contained_regular_file(
            project,
            relative_path,
            f"{code_prefix}_RUNTIME_PATH_INVALID",
        )
        if _sha256_file(path) != expected_sha256:
            raise V311SuccessorAuthorityEnvelopeV2Error(
                f"{code_prefix}_RUNTIME_PHYSICAL_DRIFT"
            )
    return {
        "authority": authority,
        "authorization_receipt": authorization,
        "manifest": manifest,
        "experiment_contract": contract,
        "predecessor_authority": predecessor,
        "qualification_receipts": receipts,
        "theory_approval": approval,
    }


def load_v311_versioned_standard_authority_chain_v2(
    project_root: Path, *, authority_version: str
) -> dict[str, Any]:
    """Replay a sealed V3 qualification or V4 target standard chain."""

    project = _project_root(project_root)
    versions = {
        "QUALIFICATION_V3": (
            V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
            "qualification_v3_authority",
            "V311_QUALIFICATION_V3",
        ),
        "TARGET_V4": (
            V311_TARGET_ACTIVE_AUTHORITY_PATH,
            "target_v4_authority",
            "V311_TARGET_V4",
        ),
    }
    if authority_version not in versions:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_STANDARD_AUTHORITY_VERSION_INVALID"
        )
    authority_path, section, prefix = versions[authority_version]
    authority_file = _contained_regular_file(
        project, authority_path, f"{prefix}_ACTIVE_AUTHORITY_PATH_INVALID"
    )
    authority = _load_strict(
        authority_file, f"{prefix}_ACTIVE_AUTHORITY_JSON_INVALID"
    )
    authority_binding = _file_binding(
        project,
        relative_path=authority_path,
        document=authority,
        digest_field="authority_digest",
    )
    bindings = {
        "theory_approval": authority.get("theory_approval_binding"),
        "experiment_contract": authority.get("experiment_contract_binding"),
        "manifest": authority.get("manifest_binding"),
        "authorization_receipt": authority.get(
            "authorization_receipt_binding"
        ),
        "authority": authority_binding,
    }
    return _load_standard_chain(
        project,
        {section: {"document_bindings": bindings}},
        envelope_section=section,
        expected_active_authority_path=authority_path,
        code_prefix=prefix,
    )


def _replay_qualification_run_genesis_physical_v2(
    *,
    project: Path,
    qualification_run_root_ref: str,
    run_genesis: Mapping[str, Any],
    qualification_chain: Mapping[str, Any],
    qualification_document_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Prove all five local genesis files are exact standard-v3 bytes."""

    try:
        evidence = verify_v311_qualification_run_genesis_v2(
            run_genesis=run_genesis,
            qualification_v3_chain=qualification_chain,
            qualification_v3_document_bindings=qualification_document_bindings,
        )
        documents, global_bindings = v311_qualification_genesis_inputs_v2(
            qualification_v3_chain=qualification_chain,
            qualification_v3_document_bindings=qualification_document_bindings,
        )
    except V311QualificationGenesisV2Error as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RUN_GENESIS_SEMANTIC_INVALID"
        ) from exc
    rows = {
        str(row.get("source_role")): row
        for row in run_genesis.get("genesis_artifacts", [])
        if isinstance(row, Mapping)
    }
    if set(rows) != set(documents):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RUN_GENESIS_ARTIFACT_SET_INVALID"
        )
    for role, document in documents.items():
        row = rows[role]
        local_relative = PurePosixPath(
            qualification_run_root_ref, str(row["local_ref"])
        ).as_posix()
        local_path = _contained_regular_file(
            project,
            local_relative,
            "V311_QUALIFICATION_RUN_GENESIS_LOCAL_PATH_INVALID",
        )
        global_path = _contained_regular_file(
            project,
            str(global_bindings[role]["path"]),
            "V311_QUALIFICATION_RUN_GENESIS_GLOBAL_PATH_INVALID",
        )
        local_bytes = local_path.read_bytes()
        global_bytes = global_path.read_bytes()
        if (
            local_bytes != global_bytes
            or hashlib.sha256(local_bytes).hexdigest()
            != row.get("local_physical_sha256")
            or hashlib.sha256(global_bytes).hexdigest()
            != row.get("global_physical_sha256")
            or _load_strict(
                local_path,
                "V311_QUALIFICATION_RUN_GENESIS_LOCAL_JSON_INVALID",
            )
            != dict(document)
        ):
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_QUALIFICATION_RUN_GENESIS_BYTE_MISMATCH"
            )
    forbidden_extra_copy = project.joinpath(
        *PurePosixPath(
            qualification_run_root_ref,
            V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
        ).parts
    )
    if forbidden_extra_copy.exists():
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_EXTRA_AUTHORITY_COPY_FORBIDDEN"
        )
    return evidence


def load_v311_legacy_failure_evidence_v2(
    project_root: Path,
    *,
    legacy_active_chain: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Physically prove that the historical run cannot be resumed."""

    project = _project_root(project_root)
    chain = (
        load_v31_active_authorization_chain(project)
        if legacy_active_chain is None
        else legacy_active_chain
    )
    authority = chain.get("authority") if isinstance(chain, Mapping) else None
    if (
        not isinstance(authority, Mapping)
        or authority.get("authorized_run_id") != V311_LEGACY_RUN_ID
        or len(chain.get("qualification_receipts", {})) != 9
        or len(chain.get("manifest", {}).get("implementation_bindings", {})) != 74
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_ACTIVE_CHAIN_NOT_EXACT"
        )
    run_relative = f"agent-cluster/experiments/{V311_LEGACY_RUN_ID}"
    run_root = _contained_directory(
        project, run_relative, "V311_LEGACY_RUN_ROOT_INVALID"
    )
    try:
        research_store = LocalV31ResearchStore(run_root)
        monitor_store = LocalV31MonitorStore(run_root)
        research = dict(
            research_store.load_checkpoint(run_id=V311_LEGACY_RUN_ID)
        )
        monitor = dict(
            monitor_store.load_checkpoint(run_id=V311_LEGACY_RUN_ID)
        )
        failure = dict(
            monitor_store.read_document(
                relative_ref=str(monitor["failure_ref"]),
                digest_field="failure_digest",
                expected_semantic_digest=str(monitor["failure_digest"]),
            )
        )
        attempt_binding = monitor["resolution_attempt_bindings"][-1]
        attempt = dict(
            monitor_store.read_document(
                relative_ref=str(attempt_binding["relative_ref"]),
                digest_field="monitor_attempt_digest",
                expected_semantic_digest=str(
                    attempt_binding["semantic_digest"]
                ),
            )
        )
    except (
        IndexError,
        KeyError,
        V31MonitorStoreError,
        V31ResearchStoreError,
        ValueError,
    ) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_PHYSICAL_REPLAY_INVALID"
        ) from exc
    if (
        research.get("status") != "READY_FOR_CYCLE"
        or research.get("completed_cycles") != 1
        or research.get("current_authority_digest")
        != authority.get("authority_digest")
        or monitor.get("status") != "FAILED_CLOSED"
        or monitor.get("resume_allowed") is not False
        or monitor.get("outcome_bindings") != []
        or len(monitor.get("plan_bindings", [])) != 1
        or len(monitor.get("resolution_attempt_bindings", [])) != 1
        or failure.get("resume_allowed") is not False
        or failure.get("planned_cycles") != 1
        or failure.get("reserved_attempts") != 1
        or failure.get("resolved_cycles") != 0
        or attempt.get("attempt_number") != 1
        or attempt.get("retry_allowed") is not False
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_STATE_INVALID"
        )

    # The v1 monitor stores only the current checkpoint and the failure's
    # previous digest.  Reconstruct that immediately preceding checkpoint from
    # the append-only attempt timestamp and the single legal failure delta.
    prior = dict(monitor)
    prior.pop("checkpoint_digest", None)
    prior.update(
        {
            "revision": int(monitor["revision"]) - 1,
            "status": "ACTIVE",
            "failure_ref": None,
            "failure_digest": None,
            "resume_allowed": True,
            "updated_at": attempt["requested_at"],
        }
    )
    reconstructed_prior = self_digest(prior, "checkpoint_digest")
    if (
        reconstructed_prior["checkpoint_digest"]
        != failure.get("checkpoint_digest_before_failure")
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_PREDECESSOR_DIGEST_INVALID"
        )
    relative_paths = {
        "research_checkpoint": f"{run_relative}/checkpoint.json",
        "monitor_checkpoint": f"{run_relative}/monitor/checkpoint.json",
        "monitor_failure": f"{run_relative}/{monitor['failure_ref']}",
        "resolution_attempt": (
            f"{run_relative}/{attempt_binding['relative_ref']}"
        ),
    }
    documents = {
        "research_checkpoint": research,
        "monitor_checkpoint": monitor,
        "monitor_failure": failure,
        "resolution_attempt": attempt,
    }
    digest_fields = {
        "research_checkpoint": "checkpoint_digest",
        "monitor_checkpoint": "checkpoint_digest",
        "monitor_failure": "failure_digest",
        "resolution_attempt": "monitor_attempt_digest",
    }
    bindings = {
        name: _file_binding(
            project,
            relative_path=relative_paths[name],
            document=document,
            digest_field=digest_fields[name],
        )
        for name, document in documents.items()
    }
    return {**documents, "bindings": bindings}


def _load_qualification_artifact(
    project: Path,
    binding: Mapping[str, Any],
    *,
    base_relative_ref: str = "",
    code: str,
) -> dict[str, Any]:
    if (
        not isinstance(binding, Mapping)
        or set(binding) != _QUALIFICATION_ARTIFACT_BINDING_FIELDS
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    relative_ref = _relative_path(binding["relative_ref"], code)
    if base_relative_ref:
        base = _relative_path(base_relative_ref, code)
        relative_ref = PurePosixPath(base, relative_ref).as_posix()
    translated = {
        "path": relative_ref,
        "schema_id": binding["schema_id"],
        "digest_field": binding["digest_field"],
        "semantic_digest": binding["semantic_digest"],
        "physical_sha256": binding["physical_sha256"],
    }
    return _load_bound_document(
        project,
        translated,
        schema_id=str(binding["schema_id"]),
        digest_field=str(binding["digest_field"]),
        code=code,
    )


def _replay_qualification_physical_artifacts(
    project: Path,
    *,
    name: str,
    qualification: Mapping[str, Any],
    standard_authority: Mapping[str, Any],
    qualification_run_root_ref: str,
) -> None:
    authority_binding = qualification.get("authority_binding")
    authority_document = _load_qualification_artifact(
        project,
        authority_binding,
        base_relative_ref=qualification_run_root_ref,
        code="V311_FRESH_QUALIFICATION_AUTHORITY_BINDING_INVALID",
    )
    if authority_document != dict(standard_authority):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_FRESH_QUALIFICATION_AUTHORITY_COPY_MISMATCH"
        )
    artifacts = qualification.get("artifact_bindings")
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_FRESH_QUALIFICATION_ARTIFACT_SET_INVALID"
        )
    if name == "public_source":
        artifact_root_ref = _relative_path(
            qualification.get("qualification_root_ref"),
            "V311_SOURCE_QUALIFICATION_ROOT_INVALID",
        )
    else:
        artifact_root_ref = qualification_run_root_ref
    replayed = {
        artifact_name: _load_qualification_artifact(
            project,
            binding,
            base_relative_ref=artifact_root_ref,
            code="V311_FRESH_QUALIFICATION_ARTIFACT_BINDING_INVALID",
        )
        for artifact_name, binding in artifacts.items()
    }
    if name == "public_source":
        for artifact_name in ("plan", "completion", "snapshot"):
            if replayed.get(artifact_name) != qualification.get(artifact_name):
                raise V311SuccessorAuthorityEnvelopeV2Error(
                    "V311_SOURCE_QUALIFICATION_EMBEDDED_ARTIFACT_MISMATCH"
                )
        completion = qualification.get("completion")
        raw_bindings = (
            completion.get("raw_bindings")
            if isinstance(completion, Mapping)
            else None
        )
        if not isinstance(raw_bindings, Mapping) or not raw_bindings:
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_SOURCE_QUALIFICATION_RAW_BINDINGS_INVALID"
            )
        for binding in raw_bindings.values():
            if not isinstance(binding, Mapping) or set(binding) != _RAW_BINDING_FIELDS:
                raise V311SuccessorAuthorityEnvelopeV2Error(
                    "V311_SOURCE_QUALIFICATION_RAW_BINDINGS_INVALID"
                )
            qualification_root = _relative_path(
                qualification.get("qualification_root_ref"),
                "V311_SOURCE_QUALIFICATION_ROOT_INVALID",
            )
            raw_relative = PurePosixPath(
                qualification_root, binding["relative_ref"]
            ).as_posix()
            raw_path = _contained_regular_file(
                project,
                raw_relative,
                "V311_SOURCE_QUALIFICATION_RAW_PATH_INVALID",
            )
            actual = _sha256_file(raw_path)
            if (
                actual != binding.get("physical_sha256")
                or actual != binding.get("semantic_digest")
            ):
                raise V311SuccessorAuthorityEnvelopeV2Error(
                    "V311_SOURCE_QUALIFICATION_RAW_PHYSICAL_DRIFT"
                )
    elif name == "outcome_monitor":
        embedded = {
            "clock_policy": qualification.get("clock_policy"),
            "raw_first_probe": qualification.get("raw_first_probe"),
            "supervisor_probe": qualification.get("supervisor_probe"),
        }
        if any(replayed.get(key) != value for key, value in embedded.items()):
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_MONITOR_QUALIFICATION_EMBEDDED_ARTIFACT_MISMATCH"
            )


def load_v311_successor_authorization_chain_v2(
    project_root: Path,
    *,
    envelope_relative_path: str | None = None,
) -> dict[str, Any]:
    """Load the complete successor authority without creating or advancing a run."""

    project = _project_root(project_root)

    # P0 ordering: no successor document is trusted or even opened before the
    # complete historical loader and immutable failure lineage pass.
    try:
        legacy_chain = load_v31_active_authorization_chain(project)
    except (V31AuthorizationError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FULL_LOADER_FAILED"
        ) from exc
    legacy_failure = load_v311_legacy_failure_evidence_v2(
        project, legacy_active_chain=legacy_chain
    )

    relative_envelope = V311_SUCCESSOR_AUTHORITY_ENVELOPE_PATH.as_posix()
    if envelope_relative_path is not None and _relative_path(
        envelope_relative_path, "V311_ENVELOPE_PATH_INVALID"
    ) != relative_envelope:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_ALTERNATE_AUTHORITY_ROOT_FORBIDDEN"
        )
    envelope_path = _contained_regular_file(
        project, relative_envelope, "V311_ENVELOPE_FILE_INVALID"
    )
    envelope = _load_strict(envelope_path, "V311_ENVELOPE_JSON_INVALID")
    try:
        verify_self_digest(envelope, ENVELOPE_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_DIGEST_INVALID"
        ) from exc
    if envelope.get("schema_id") != ENVELOPE_SCHEMA_ID:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_SCHEMA_INVALID"
        )

    addendum = envelope.get("theory_addendum_binding")
    if (
        not isinstance(addendum, Mapping)
        or addendum.get("path") != V311_THEORY_ADDENDUM_PATH
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ADDENDUM_BINDING_INVALID"
        )
    addendum_path = _contained_regular_file(
        project, addendum["path"], "V311_ADDENDUM_PATH_INVALID"
    )
    if _sha256_file(addendum_path) != addendum.get("physical_sha256"):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ADDENDUM_PHYSICAL_DRIFT"
        )
    successor_approval = _load_bound_document(
        project,
        envelope.get("successor_user_approval_binding"),
        schema_id=SUCCESSOR_USER_APPROVAL_SCHEMA_ID,
        digest_field=SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
        code="V311_SUCCESSOR_USER_APPROVAL_BINDING_INVALID",
    )
    try:
        approval_digest = verify_v311_successor_user_approval_receipt_v2(
            successor_approval
        )
    except V311SuccessorUserApprovalV2Error as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_SUCCESSOR_USER_APPROVAL_INVALID"
        ) from exc
    if (
        approval_digest != envelope.get("successor_user_approval_digest")
        or successor_approval.get("theory_addendum_binding") != dict(addendum)
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_SUCCESSOR_USER_APPROVAL_CROSS_BINDING_INVALID"
        )

    qualification_chain = _load_standard_chain(
        project,
        envelope,
        envelope_section="qualification_v3_authority",
        expected_active_authority_path=V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
        code_prefix="V311_QUALIFICATION_V3",
    )
    qualification_run_root_ref = _relative_path(
        envelope.get("qualification_run_root_ref"),
        "V311_QUALIFICATION_RUN_ROOT_REF_INVALID",
    )
    qualification_run_root = _contained_directory(
        project,
        qualification_run_root_ref,
        "V311_QUALIFICATION_RUN_ROOT_INVALID",
    )
    qualification_section = envelope.get("qualification_v3_authority")
    if not isinstance(qualification_section, Mapping):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_V3_ENVELOPE_SECTION_INVALID"
        )
    qualification_run_genesis = _load_bound_document(
        project,
        qualification_section.get("run_genesis_binding"),
        schema_id=RUN_GENESIS_SCHEMA_ID,
        digest_field=RUN_GENESIS_DIGEST_FIELD,
        code="V311_QUALIFICATION_RUN_GENESIS_BINDING_INVALID",
    )
    genesis_evidence = _replay_qualification_run_genesis_physical_v2(
        project=project,
        qualification_run_root_ref=qualification_run_root_ref,
        run_genesis=qualification_run_genesis,
        qualification_chain=qualification_chain,
        qualification_document_bindings=qualification_section[
            "document_bindings"
        ],
    )
    if genesis_evidence["run_genesis_digest"] != qualification_section.get(
        "run_genesis_digest"
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RUN_GENESIS_DIGEST_MISMATCH"
        )

    auxiliary = envelope.get("auxiliary_contract_bindings")
    if not isinstance(auxiliary, Mapping) or tuple(auxiliary) != V311_AUXILIARY_DOCUMENT_KEYS:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_AUXILIARY_BINDING_SET_INVALID"
        )
    auxiliary_specs = {
        "clock_policy": (
            "theory_paper_v31_outcome_clock_policy_v2",
            "clock_policy_digest",
        ),
        "supervisor_policy": (
            "theory_paper_v311_successor_supervisor_policy_v2",
            SUPERVISOR_POLICY_DIGEST_FIELD,
        ),
        "runtime_closure": (
            "theory_paper_v311_successor_runtime_closure_receipt_v2",
            RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD,
        ),
        "sentiment_source_registry": (
            "theory_paper_v2_v31_native_sentiment_source_registry",
            "registry_digest",
        ),
        "association_preregistration": (
            "theory_paper_v2_v31_association_preregistration_v2",
            "association_preregistration_digest",
        ),
        "evaluation_contract": (
            "theory_paper_v2_v31_evaluation_contract_v2",
            "evaluation_contract_digest",
        ),
    }
    auxiliary_documents = {
        name: _load_bound_document(
            project,
            auxiliary[name],
            schema_id=schema_id,
            digest_field=digest_field,
            code=f"V311_{name.upper()}_BINDING_INVALID",
        )
        for name, (schema_id, digest_field) in auxiliary_specs.items()
    }
    try:
        verify_outcome_clock_policy(auxiliary_documents["clock_policy"])
        verify_v311_supervisor_policy_v2(
            auxiliary_documents["supervisor_policy"]
        )
        verify_v311_runtime_closure_receipt_v2(
            auxiliary_documents["runtime_closure"]
        )
        verify_v31_native_sentiment_source_registry(
            auxiliary_documents["sentiment_source_registry"]
        )
        verify_v31_association_preregistration_v2(
            auxiliary_documents["association_preregistration"]
        )
        verify_v31_evaluation_contract_v2(
            auxiliary_documents["evaluation_contract"],
            auxiliary_documents["association_preregistration"],
        )
        closure = auxiliary_documents["runtime_closure"]
        trace_receipt = _load_bound_document(
            project,
            closure["fresh_process_trace_binding"],
            schema_id=FRESH_PROCESS_TRACE_SCHEMA_ID,
            digest_field=FRESH_PROCESS_TRACE_DIGEST_FIELD,
            code="V311_RUNTIME_FRESH_TRACE_BINDING_INVALID",
        )
        if trace_receipt != closure["fresh_process_trace_receipt"]:
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_RUNTIME_FRESH_TRACE_EMBEDDED_DRIFT"
            )
        verify_v31_runtime_closure_bindings_v2(
            project_root=project,
            production_root_paths=closure["production_root_paths"],
            trace_paths=closure["fresh_process_trace_paths"],
            frozen_bindings=closure["frozen_bindings"],
        )
    except (KeyError, TypeError, ValueError, V31RuntimeClosureError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_AUXILIARY_PHYSICAL_OR_SEMANTIC_REPLAY_INVALID"
        ) from exc

    qualification_bindings = envelope.get("fresh_qualification_bindings")
    if (
        not isinstance(qualification_bindings, Mapping)
        or tuple(qualification_bindings) != V311_FRESH_QUALIFICATION_KEYS
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_FRESH_QUALIFICATION_BINDING_SET_INVALID"
        )
    qualification_specs = {
        "public_source": (
            SOURCE_QUALIFICATION_SCHEMA_ID,
            SOURCE_QUALIFICATION_DIGEST_FIELD,
        ),
        "codex_durable_delivery": (
            CODEX_QUALIFICATION_V3_SCHEMA_ID,
            CODEX_QUALIFICATION_V3_DIGEST_FIELD,
        ),
        "outcome_monitor": (
            MONITOR_QUALIFICATION_SCHEMA_ID,
            MONITOR_QUALIFICATION_DIGEST_FIELD,
        ),
    }
    qualifications = {
        name: _load_bound_document(
            project,
            qualification_bindings[name],
            schema_id=schema_id,
            digest_field=digest_field,
            code=f"V311_FRESH_{name.upper()}_BINDING_INVALID",
        )
        for name, (schema_id, digest_field) in qualification_specs.items()
    }
    try:
        verify_successor_public_source_qualification_v2(
            qualifications["public_source"]
        )
        verify_successor_codex_durable_qualification_v3(
            qualifications["codex_durable_delivery"]
        )
        verify_successor_monitor_qualification_v2(
            qualifications["outcome_monitor"]
        )
        qualification_authority = qualification_chain["authority"]
        qualification_authority_digest = str(
            qualification_authority["authority_digest"]
        )
        verify_fresh_public_source_qualification_durable_v2(
            project_root=project,
            authority=qualification_authority,
            validated_authority_digest=qualification_authority_digest,
            document=qualifications["public_source"],
        )
        verify_current_codex_qualification_durable_v3(
            project_root=project,
            run_root_ref=qualification_run_root_ref,
            authority=qualification_authority,
            validated_authority_digest=qualification_authority_digest,
            document=qualifications["codex_durable_delivery"],
        )
        verify_monitor_qualification_durable_v2(
            run_root=qualification_run_root,
            document=qualifications["outcome_monitor"],
        )
        for name in V311_FRESH_QUALIFICATION_KEYS:
            _replay_qualification_physical_artifacts(
                project,
                name=name,
                qualification=qualifications[name],
                standard_authority=qualification_chain["authority"],
                qualification_run_root_ref=qualification_run_root_ref,
            )
    except (
        V31SuccessorQualificationV2Error,
        V31SuccessorQualificationV2WorkflowError,
        V311CodexDurableQualificationV3Error,
        V311CodexDurableQualificationV3WorkflowError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        if isinstance(exc, V311SuccessorAuthorityEnvelopeV2Error):
            raise
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_FRESH_QUALIFICATION_REPLAY_INVALID"
        ) from exc

    retirement = _load_bound_document(
        project,
        envelope.get("qualification_retirement_binding"),
        schema_id=QUALIFICATION_RETIREMENT_SCHEMA_ID,
        digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        code="V311_QUALIFICATION_RETIREMENT_BINDING_INVALID",
    )
    try:
        retirement_digest = verify_v311_qualification_retirement_receipt_v2(
            retirement
        )
        if retirement_digest != envelope.get(
            "qualification_retirement_digest"
        ):
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_QUALIFICATION_RETIREMENT_DIGEST_MISMATCH"
            )
        retirement_checkpoint = _load_bound_document(
            project,
            retirement["research_checkpoint_binding"],
            schema_id="theory_paper_v31_research_checkpoint",
            digest_field="checkpoint_digest",
            code="V311_QUALIFICATION_RETIREMENT_CHECKPOINT_INVALID",
        )
        durable_checkpoint = dict(
            LocalV31ResearchStore(qualification_run_root).load_checkpoint(
                run_id=str(retirement["qualification_run_id"])
            )
        )
        if retirement_checkpoint != durable_checkpoint:
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_QUALIFICATION_RETIREMENT_CHECKPOINT_DRIFT"
            )
        retirement_monitor_checkpoint = _load_bound_document(
            project,
            retirement["monitor_checkpoint_binding"],
            schema_id="theory_paper_v31_monitor_checkpoint",
            digest_field="checkpoint_digest",
            code="V311_QUALIFICATION_RETIREMENT_MONITOR_CHECKPOINT_INVALID",
        )
        durable_monitor_checkpoint = dict(
            LocalV31MonitorStore(qualification_run_root).load_checkpoint(
                run_id=str(retirement["qualification_run_id"])
            )
        )
        if retirement_monitor_checkpoint != durable_monitor_checkpoint:
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_QUALIFICATION_RETIREMENT_MONITOR_CHECKPOINT_DRIFT"
            )
        rebuilt_retirement = build_v311_qualification_retirement_receipt_v2(
            retirement_id=str(retirement["retirement_id"]),
            retired_at=str(retirement["retired_at"]),
            target_run_id=str(retirement["target_run_id"]),
            qualification_v3_chain=qualification_chain,
            qualification_v3_document_bindings=envelope[
                "qualification_v3_authority"
            ]["document_bindings"],
            qualification_run_genesis=qualification_run_genesis,
            qualification_run_genesis_binding=envelope[
                "qualification_v3_authority"
            ]["run_genesis_binding"],
            research_checkpoint=retirement_checkpoint,
            research_checkpoint_binding=retirement[
                "research_checkpoint_binding"
            ],
            monitor_checkpoint=retirement_monitor_checkpoint,
            monitor_checkpoint_binding=retirement[
                "monitor_checkpoint_binding"
            ],
            successor_qualifications=qualifications,
            successor_qualification_bindings=qualification_bindings,
        )
        if rebuilt_retirement != retirement:
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_QUALIFICATION_RETIREMENT_REPLAY_MISMATCH"
            )
    except (
        KeyError,
        TypeError,
        ValueError,
        V31ResearchStoreError,
        V311QualificationRetirementV2Error,
    ) as exc:
        if isinstance(exc, V311SuccessorAuthorityEnvelopeV2Error):
            raise
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RETIREMENT_REPLAY_INVALID"
        ) from exc

    # The target authority is a second, later chronology.  It is not opened
    # until the qualification authority, all three qualification receipts,
    # and the exact-cycle-one write-once retirement have passed.
    target_chain = _load_standard_chain(
        project,
        envelope,
        envelope_section="target_v4_authority",
        expected_active_authority_path=V311_TARGET_ACTIVE_AUTHORITY_PATH,
        code_prefix="V311_TARGET_V4",
    )

    loaded = {
        "envelope": envelope,
        "legacy_active_chain": legacy_chain,
        "legacy_failure_evidence": legacy_failure,
        "qualification_v3_chain": qualification_chain,
        "qualification_run_genesis": qualification_run_genesis,
        "target_v4_chain": target_chain,
        "theory_addendum_binding": dict(addendum),
        "successor_user_approval": successor_approval,
        "clock_policy": auxiliary_documents["clock_policy"],
        "supervisor_policy": auxiliary_documents["supervisor_policy"],
        "runtime_closure": auxiliary_documents["runtime_closure"],
        "sentiment_source_registry": auxiliary_documents[
            "sentiment_source_registry"
        ],
        "association_preregistration": auxiliary_documents[
            "association_preregistration"
        ],
        "evaluation_contract": auxiliary_documents["evaluation_contract"],
        "successor_qualifications": qualifications,
        "qualification_retirement": retirement,
    }
    verify_v311_successor_authority_envelope_v2(
        envelope,
        legacy_active_chain=legacy_chain,
        legacy_failure_evidence=legacy_failure,
        qualification_v3_chain=qualification_chain,
        qualification_run_genesis=qualification_run_genesis,
        target_v4_chain=target_chain,
        theory_addendum_binding=addendum,
        successor_user_approval=successor_approval,
        clock_policy=loaded["clock_policy"],
        supervisor_policy=loaded["supervisor_policy"],
        runtime_closure=loaded["runtime_closure"],
        sentiment_source_registry=loaded["sentiment_source_registry"],
        association_preregistration=loaded["association_preregistration"],
        evaluation_contract=loaded["evaluation_contract"],
        successor_qualifications=qualifications,
        qualification_retirement=retirement,
    )
    return loaded


__all__ = [
    "V311_SUCCESSOR_AUTHORITY_ENVELOPE_PATH",
    "load_v311_legacy_failure_evidence_v2",
    "load_v311_successor_authorization_chain_v2",
    "load_v311_versioned_standard_authority_chain_v2",
]
