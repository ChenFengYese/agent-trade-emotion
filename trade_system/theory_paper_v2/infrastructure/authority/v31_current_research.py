"""Read-only loader for the V3.1 mechanical authorization chronology.

The loader follows and verifies four immutable layers:

    approved theory -> frozen experiment contract -> frozen manifest
    -> typed qualification receipts -> authorization receipt -> active authority v2.1

It never creates a run, checkpoint, adapter, account connection, or order.
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
from ...domain.contracts.canonical import (
    CanonicalContractError,
    load_json_strict,
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
from ...domain.v31_experiment_contracts import (
    EXPERIMENT_SCHEMA_ID,
    V31ExperimentContractError,
    verify_minimal_experiment_contract,
)


V31_CURRENT_RESEARCH_AUTHORITY_PATH = Path(
    "config/theory_paper_v31.current_research_authority.v2.json"
)
_V1_PREDECESSOR_PATH = "config/theory_paper_v2.current_research_authority.v1.json"
_GATE_IDS = tuple(f"Q{index}" for index in range(9))
_EXTERNAL_TYPED_GATE_IDS = ("Q6", "Q7")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_regular_file(project: Path, relative_path: Any, code: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise V31AuthorizationError(code)
    lexical = PurePosixPath(relative_path)
    if (
        "\\" in relative_path
        or lexical.as_posix() != relative_path
        or lexical.is_absolute()
        or any(part in {"", ".", ".."} for part in lexical.parts)
    ):
        raise V31AuthorizationError(code)
    candidate = project.joinpath(*lexical.parts)
    try:
        if candidate.is_symlink():
            raise V31AuthorizationError(code)
        target = candidate.resolve(strict=True)
        target.relative_to(project)
    except (OSError, ValueError) as exc:
        raise V31AuthorizationError(code) from exc
    if not target.is_file():
        raise V31AuthorizationError(code)
    return target


def _load_strict(path: Path, code: str) -> dict[str, Any]:
    try:
        return load_json_strict(path)
    except CanonicalContractError as exc:
        raise V31AuthorizationError(code) from exc


def _verify_document_self_digest(
    document: Mapping[str, Any], *, digest_field: str, code: str
) -> str:
    try:
        return verify_self_digest(document, digest_field)
    except (AttributeError, CanonicalContractError, TypeError, ValueError) as exc:
        raise V31AuthorizationError(code) from exc


def _load_bound_document(
    project: Path,
    binding: Any,
    *,
    schema_id: str,
    digest_field: str,
    code: str,
) -> dict[str, Any]:
    validate_v31_document_binding(
        binding,
        code=code,
        expected_schema_id=schema_id,
        expected_digest_field=digest_field,
    )
    path = _contained_regular_file(project, binding["path"], f"{code}_PATH")
    if _sha256_file(path) != binding["physical_sha256"]:
        raise V31AuthorizationError(f"{code}_PHYSICAL_DRIFT")
    document = _load_strict(path, f"{code}_JSON_INVALID")
    if document.get("schema_id") != schema_id:
        raise V31AuthorizationError(f"{code}_SCHEMA_MISMATCH")
    semantic_digest = _verify_document_self_digest(
        document,
        digest_field=digest_field,
        code=f"{code}_SEMANTIC_DIGEST_INVALID",
    )
    if semantic_digest != binding["semantic_digest"]:
        raise V31AuthorizationError(f"{code}_SEMANTIC_DRIFT")
    return document


def _validate_frozen_predecessor(
    project: Path,
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    binding = authority.get("predecessor_authority_binding")
    if (
        not isinstance(binding, Mapping)
        or binding.get("path") != _V1_PREDECESSOR_PATH
        or binding.get("expected_status")
        != "FROZEN_V3_1_QUALIFICATION_PENDING"
    ):
        raise V31AuthorizationError("V31_PREDECESSOR_BINDING_INVALID")
    path = _contained_regular_file(
        project, binding.get("path"), "V31_PREDECESSOR_PATH_INVALID"
    )
    if _sha256_file(path) != binding.get("physical_sha256"):
        raise V31AuthorizationError("V31_PREDECESSOR_PHYSICAL_DRIFT")
    predecessor = _load_strict(path, "V31_PREDECESSOR_JSON_INVALID")
    try:
        validate_research_authority(predecessor)
    except ResearchAuthorityError as exc:
        raise V31AuthorizationError("V31_PREDECESSOR_SEMANTICS_INVALID") from exc
    current = predecessor.get("current_theory")
    candidate = predecessor.get("candidate_theory")
    if (
        predecessor.get("status") != binding.get("expected_status")
        or predecessor.get("experiment_start_authorized") is not False
        or predecessor.get("authorized_operations") != []
        or predecessor.get("authorized_run_ids") != []
        or predecessor.get("authorized_template_sha256s") != []
        or predecessor.get("authorization_receipt_path") is not None
        or predecessor.get("authorization_receipt_digest") is not None
        or predecessor.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or predecessor.get("executable") is not False
        or not isinstance(current, Mapping)
        or current.get("version") != "3.1"
        or current.get("review_status") != "FROZEN_APPROVED"
        or current.get("path") != authority.get("current_theory", {}).get("path")
        or current.get("physical_sha256")
        != authority.get("current_theory", {}).get("physical_sha256")
        or not isinstance(candidate, Mapping)
        or candidate.get("path") != current.get("path")
        or candidate.get("version") != "3.1"
        or candidate.get("review_status") != "FROZEN_APPROVED_CURRENT"
        or candidate.get("physical_sha256") != current.get("physical_sha256")
    ):
        raise V31AuthorizationError("V31_PREDECESSOR_NOT_FROZEN_PENDING")
    return predecessor


def _verify_theory_file(
    project: Path,
    authority: Mapping[str, Any],
    approval: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> Path:
    active_binding = authority.get("current_theory")
    if not isinstance(active_binding, Mapping):
        raise V31AuthorizationError("V31_ACTIVE_THEORY_BINDING_INVALID")
    path = _contained_regular_file(
        project, active_binding.get("path"), "V31_ACTIVE_THEORY_PATH_INVALID"
    )
    physical_sha256 = _sha256_file(path)
    if (
        physical_sha256 != active_binding.get("physical_sha256")
        or approval.get("theory_path") != active_binding.get("path")
        or approval.get("theory_physical_sha256") != physical_sha256
        or manifest.get("theory_binding") != active_binding
    ):
        raise V31AuthorizationError("V31_ACTIVE_THEORY_PHYSICAL_DRIFT")
    return path


def load_v31_active_authorization_chain(
    project_root: Path,
) -> dict[str, Any]:
    """Load the exact V3.1 start authority, without starting the experiment."""

    try:
        project = Path(project_root).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V31AuthorizationError("V31_PROJECT_ROOT_INVALID") from exc
    if not project.is_dir():
        raise V31AuthorizationError("V31_PROJECT_ROOT_INVALID")

    authority_path = _contained_regular_file(
        project,
        V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
        "V31_ACTIVE_AUTHORITY_FILE_INVALID",
    )
    authority = _load_strict(authority_path, "V31_ACTIVE_AUTHORITY_JSON_INVALID")
    if (
        authority.get("schema_id")
        != "theory_paper_v31_current_research_authority"
        or authority.get("schema_version") != "2.1.0"
    ):
        raise V31AuthorizationError("V31_ACTIVE_AUTHORITY_SCHEMA_INVALID")
    _verify_document_self_digest(
        authority,
        digest_field="authority_digest",
        code="V31_ACTIVE_AUTHORITY_DIGEST_INVALID",
    )

    predecessor = _validate_frozen_predecessor(project, authority)
    approval = _load_bound_document(
        project,
        authority.get("theory_approval_binding"),
        schema_id="theory_paper_v31_user_approval_receipt",
        digest_field="approval_receipt_digest",
        code="V31_APPROVAL_BINDING_INVALID",
    )
    validate_v31_theory_approval(approval)
    manifest = _load_bound_document(
        project,
        authority.get("manifest_binding"),
        schema_id="theory_paper_v31_frozen_experiment_manifest",
        digest_field="manifest_digest",
        code="V31_MANIFEST_BINDING_INVALID",
    )
    experiment_contract = _load_bound_document(
        project,
        manifest.get("experiment_contract_binding"),
        schema_id=EXPERIMENT_SCHEMA_ID,
        digest_field="experiment_contract_digest",
        code="V31_EXPERIMENT_CONTRACT_BINDING_INVALID",
    )
    try:
        verify_minimal_experiment_contract(experiment_contract)
    except V31ExperimentContractError as exc:
        raise V31AuthorizationError(
            "V31_EXPERIMENT_CONTRACT_SEMANTICS_INVALID"
        ) from exc
    validate_v31_frozen_experiment_manifest(
        manifest,
        experiment_contract=experiment_contract,
        theory_approval=approval,
    )
    _verify_theory_file(project, authority, approval, manifest)

    qualification_receipts: dict[str, dict[str, Any]] = {}
    gates = manifest["qualification_gates"]
    for gate_id in _GATE_IDS:
        if gate_id in TYPED_QUALIFICATION_GATE_IDS:
            receipt_schema = TYPED_QUALIFICATION_SCHEMA_ID
        elif gate_id in _EXTERNAL_TYPED_GATE_IDS:
            receipt_schema = EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID
        else:  # pragma: no cover - all Q0-Q8 gates are strict typed gates
            receipt_schema = "theory_paper_v31_qualification_gate_receipt"
        receipt = _load_bound_document(
            project,
            gates[gate_id]["receipt_binding"],
            schema_id=receipt_schema,
            digest_field="qualification_receipt_digest",
            code=f"V31_{gate_id}_BINDING_INVALID",
        )
        validate_v31_qualification_receipt(
            receipt,
            expected_gate_id=gate_id,
            experiment_contract=experiment_contract,
            manifest=manifest,
            theory_approval=approval,
        )
        if gate_id == "Q6":
            try:
                verify_q6_receipt_durable_artifacts(
                    project_root=project,
                    receipt=receipt,
                )
            except (V31ExternalQualificationWorkflowError, ValueError) as exc:
                raise V31AuthorizationError(
                    "V31_Q6_DURABLE_EVIDENCE_REPLAY_INVALID"
                ) from exc
        elif gate_id == "Q7":
            try:
                verify_q7_receipt_durable_artifacts(
                    project_root=project,
                    receipt=receipt,
                )
            except (V31ExternalQualificationWorkflowError, ValueError) as exc:
                raise V31AuthorizationError(
                    "V31_Q7_DURABLE_EVIDENCE_REPLAY_INVALID"
                ) from exc
            q6 = qualification_receipts.get("Q6")
            q6_evidence = (
                q6.get("qualification_evidence")
                if isinstance(q6, Mapping)
                else None
            )
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
                raise V31AuthorizationError(
                    "V31_Q7_Q6_SOURCE_COMPLETION_BINDING_MISMATCH"
                )
        qualification_receipts[gate_id] = receipt

    for relative_path, expected_sha256 in manifest[
        "implementation_bindings"
    ].items():
        implementation_path = _contained_regular_file(
            project,
            relative_path,
            "V31_IMPLEMENTATION_BINDING_PATH_INVALID",
        )
        if _sha256_file(implementation_path) != expected_sha256:
            raise V31AuthorizationError("V31_IMPLEMENTATION_BINDING_DRIFT")

    authorization_receipt = _load_bound_document(
        project,
        authority.get("authorization_receipt_binding"),
        schema_id="theory_paper_v31_experiment_authorization_receipt",
        digest_field="authorization_receipt_digest",
        code="V31_AUTHORIZATION_RECEIPT_BINDING_INVALID",
    )
    validate_v31_experiment_authorization(
        authorization_receipt,
        manifest=manifest,
        experiment_contract=experiment_contract,
        theory_approval=approval,
    )
    validate_v31_active_authority(
        authority,
        theory_approval=approval,
        manifest=manifest,
        experiment_contract=experiment_contract,
        authorization_receipt=authorization_receipt,
    )
    return {
        "authority": authority,
        "authorization_receipt": authorization_receipt,
        "manifest": manifest,
        "experiment_contract": experiment_contract,
        "predecessor_authority": predecessor,
        "qualification_receipts": qualification_receipts,
        "theory_approval": approval,
    }


__all__ = [
    "V31_CURRENT_RESEARCH_AUTHORITY_PATH",
    "load_v31_active_authorization_chain",
]
