"""Production composition for the sole non-executable V3.1 authority chain.

Phase A freezes only the experiment contract and the receipt-independent
manifest subject.  Phase B is unreachable until all nine typed receipts pass
the central Domain validator and Q6/Q7 durable physical replay.  Run genesis is
an explicit later call and is never created by either freeze phase.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ..application.v31_authority_freeze import (
    GATE_IDS,
    QUALIFICATION_SUBJECT_DIGEST_FIELD,
    V31AuthorityFreezeError,
    V31_PRODUCTION_RUNTIME_PATHS,
    build_v31_final_authority_documents,
    build_v31_qualification_manifest_subject,
    build_v31_qualification_subject_freeze,
    document_binding,
    verify_v31_qualification_subject_freeze,
)
from ..application.v31_external_qualification import (
    V31ExternalQualificationWorkflowError,
    verify_q6_receipt_durable_artifacts,
)
from ..application.v31_run_genesis import initialize_v31_run_genesis
from ..domain.contracts.canonical import verify_self_digest
from ..domain.governance.research_authority import (
    ResearchAuthorityError,
    validate_research_authority,
)
from ..domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_qualification_receipt,
    validate_v31_theory_approval,
)
from ..domain.v31_experiment_contracts import (
    build_minimal_experiment_contract,
    verify_minimal_experiment_contract,
)
from ..infrastructure.authority.v31_current_research import (
    V31_CURRENT_RESEARCH_AUTHORITY_PATH,
    load_v31_active_authorization_chain,
)
from ..infrastructure.v31_authority_freeze_store import (
    V31AuthorityFreezeStoreError,
    binding_for_existing_document,
    collect_exact_implementation_bindings,
    load_json_document,
    load_self_digested_document,
    preflight_write_once_json,
    read_bytes,
    sha256_file,
    verify_exact_implementation_bindings,
    write_once_json,
)
from ..infrastructure.v31_research_store import LocalV31ResearchStore


class V31AuthorityFreezeCompositionError(ValueError):
    """The two-phase V3.1 authority composition failed closed."""


THEORY_APPROVAL_PATH = "config/theory_paper_v31.theory_approval.20260806.json"
PREDECESSOR_AUTHORITY_PATH = (
    "config/theory_paper_v2.current_research_authority.v1.json"
)
ACTIVE_AUTHORITY_PATH = V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix()


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31AuthorityFreezeCompositionError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31AuthorityFreezeCompositionError(code) from exc
    if parsed.tzinfo is None:
        raise V31AuthorityFreezeCompositionError(code)
    parsed = parsed.astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise V31AuthorityFreezeCompositionError(code)
    return parsed


def v31_authority_freeze_paths(run_id: str) -> dict[str, Any]:
    """Return the one deterministic, run-scoped write set."""

    if (
        not isinstance(run_id, str)
        or len(run_id) < 8
        or len(run_id) > 128
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in run_id)
    ):
        raise V31AuthorityFreezeCompositionError("V31_FREEZE_RUN_ID_INVALID")
    root = f"config/v31-authority/{run_id}"
    return {
        "root": root,
        "experiment_contract": f"{root}/experiment-contract.json",
        "qualification_subject": f"{root}/qualification-manifest-subject.json",
        "qualification_receipts": {
            gate_id: f"{root}/qualification-{gate_id.lower()}.json"
            for gate_id in GATE_IDS
        },
        "final_manifest": f"{root}/frozen-experiment-manifest.json",
        "authorization_receipt": f"{root}/experiment-authorization.json",
        "active_authority": ACTIVE_AUTHORITY_PATH,
    }


def _load_and_verify_predecessor(
    project_root: Path, *, theory_approval: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    predecessor = load_json_document(project_root, PREDECESSOR_AUTHORITY_PATH)
    try:
        validate_research_authority(predecessor)
    except ResearchAuthorityError as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_PREDECESSOR_INVALID"
        ) from exc
    current = predecessor.get("current_theory")
    candidate = predecessor.get("candidate_theory")
    if (
        predecessor.get("status") != "FROZEN_V3_1_QUALIFICATION_PENDING"
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
        or current.get("path") != theory_approval.get("theory_path")
        or current.get("version") != "3.1"
        or current.get("review_status") != "FROZEN_APPROVED"
        or current.get("physical_sha256")
        != theory_approval.get("theory_physical_sha256")
        or not isinstance(candidate, Mapping)
        or candidate.get("path") != current.get("path")
        or candidate.get("version") != "3.1"
        or candidate.get("review_status") != "FROZEN_APPROVED_CURRENT"
        or candidate.get("physical_sha256") != current.get("physical_sha256")
    ):
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_PREDECESSOR_NOT_PENDING"
        )
    return predecessor, {
        "path": PREDECESSOR_AUTHORITY_PATH,
        "physical_sha256": sha256_file(project_root, PREDECESSOR_AUTHORITY_PATH),
        "expected_status": "FROZEN_V3_1_QUALIFICATION_PENDING",
    }


def _load_phase_a(
    project_root: Path, *, run_id: str
) -> dict[str, Any]:
    paths = v31_authority_freeze_paths(run_id)
    approval = load_self_digested_document(
        project_root, THEORY_APPROVAL_PATH, digest_field="approval_receipt_digest"
    )
    try:
        validate_v31_theory_approval(approval)
    except V31AuthorizationError as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_APPROVAL_INVALID"
        ) from exc
    theory_path = approval["theory_path"]
    if sha256_file(project_root, theory_path) != approval["theory_physical_sha256"]:
        raise V31AuthorityFreezeCompositionError("V31_FREEZE_THEORY_PHYSICAL_DRIFT")
    predecessor, predecessor_binding = _load_and_verify_predecessor(
        project_root, theory_approval=approval
    )
    contract = load_self_digested_document(
        project_root,
        paths["experiment_contract"],
        digest_field="experiment_contract_digest",
    )
    try:
        verify_minimal_experiment_contract(contract)
    except ValueError as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_CONTRACT_INVALID"
        ) from exc
    subject_freeze = load_self_digested_document(
        project_root,
        paths["qualification_subject"],
        digest_field=QUALIFICATION_SUBJECT_DIGEST_FIELD,
    )
    try:
        subject = verify_v31_qualification_subject_freeze(
            subject_freeze, experiment_contract=contract
        )
    except V31AuthorityFreezeError as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_SUBJECT_INVALID"
        ) from exc
    if contract.get("run_id") != run_id or subject.get("run_id") != run_id:
        raise V31AuthorityFreezeCompositionError("V31_FREEZE_RUN_BINDING_MISMATCH")
    approval_time = _timestamp(
        approval.get("approved_at"), "V31_FREEZE_APPROVAL_TIME_INVALID"
    )
    predecessor_time = _timestamp(
        predecessor.get("recorded_at"), "V31_FREEZE_PREDECESSOR_TIME_INVALID"
    )
    contract_time = _timestamp(
        contract.get("frozen_at"), "V31_FREEZE_CONTRACT_TIME_INVALID"
    )
    subject_time = _timestamp(
        subject.get("created_at"), "V31_FREEZE_SUBJECT_TIME_INVALID"
    )
    if (
        predecessor_time > contract_time
        or approval_time > contract_time
        or contract_time > subject_time
        or subject_freeze.get("frozen_at") != subject.get("created_at")
    ):
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_PHASE_A_CHRONOLOGY_INVALID"
        )
    if subject["theory_approval_binding"] != binding_for_existing_document(
        project_root,
        THEORY_APPROVAL_PATH,
        digest_field="approval_receipt_digest",
    ):
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_APPROVAL_BINDING_DRIFT"
        )
    contract_binding = binding_for_existing_document(
        project_root,
        paths["experiment_contract"],
        digest_field="experiment_contract_digest",
    )
    if subject["experiment_contract_binding"] != contract_binding:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_CONTRACT_BINDING_DRIFT"
        )
    verify_exact_implementation_bindings(
        project_root,
        subject["implementation_bindings"],
        exact_paths=V31_PRODUCTION_RUNTIME_PATHS,
    )
    return {
        "paths": paths,
        "theory_approval": approval,
        "experiment_contract": contract,
        "manifest_subject": subject,
        "subject_freeze": subject_freeze,
        "predecessor_authority": predecessor,
        "predecessor_authority_binding": predecessor_binding,
    }


def freeze_v31_qualification_subject(
    *,
    project_root: Path,
    run_id: str,
    contract_id: str,
    manifest_id: str,
    contract_frozen_at: str,
    subject_created_at: str,
) -> dict[str, Any]:
    """Phase A: write-once freeze the contract and receipt-independent subject."""

    try:
        paths = v31_authority_freeze_paths(run_id)
        project = Path(project_root).resolve(strict=True)
        active = project / ACTIVE_AUTHORITY_PATH
        if active.exists():
            raise V31AuthorityFreezeCompositionError(
                "V31_FREEZE_ACTIVE_AUTHORITY_ALREADY_EXISTS"
            )
        authority_root = project / "config/v31-authority"
        if authority_root.exists():
            foreign_entries = [
                path for path in authority_root.iterdir() if path.name != run_id
            ]
            if foreign_entries:
                raise V31AuthorityFreezeCompositionError(
                    "V31_FREEZE_ANOTHER_RUN_ALREADY_FROZEN"
                )
        approval = load_self_digested_document(
            project,
            THEORY_APPROVAL_PATH,
            digest_field="approval_receipt_digest",
        )
        validate_v31_theory_approval(approval)
        theory_sha = sha256_file(project, approval["theory_path"])
        if theory_sha != approval["theory_physical_sha256"]:
            raise V31AuthorityFreezeCompositionError(
                "V31_FREEZE_THEORY_PHYSICAL_DRIFT"
            )
        predecessor, _ = _load_and_verify_predecessor(
            project, theory_approval=approval
        )
        approved_at = _timestamp(
            approval["approved_at"], "V31_FREEZE_APPROVAL_TIME_INVALID"
        )
        contract_time = _timestamp(
            contract_frozen_at, "V31_FREEZE_CONTRACT_TIME_INVALID"
        )
        subject_time = _timestamp(
            subject_created_at, "V31_FREEZE_SUBJECT_TIME_INVALID"
        )
        predecessor_time = _timestamp(
            predecessor.get("recorded_at"), "V31_FREEZE_PREDECESSOR_TIME_INVALID"
        )
        if (
            contract_time < approved_at
            or contract_time < predecessor_time
            or subject_time < contract_time
        ):
            raise V31AuthorityFreezeCompositionError(
                "V31_FREEZE_PHASE_A_CHRONOLOGY_INVALID"
            )
        contract = build_minimal_experiment_contract(
            contract_id=contract_id,
            run_id=run_id,
            frozen_at=contract_frozen_at,
        )
        contract_binding = document_binding(
            path=paths["experiment_contract"],
            document=contract,
            digest_field="experiment_contract_digest",
        )
        approval_binding = binding_for_existing_document(
            project,
            THEORY_APPROVAL_PATH,
            digest_field="approval_receipt_digest",
        )
        implementation_bindings = collect_exact_implementation_bindings(
            project, exact_paths=V31_PRODUCTION_RUNTIME_PATHS
        )
        subject = build_v31_qualification_manifest_subject(
            run_id=run_id,
            manifest_id=manifest_id,
            created_at=subject_created_at,
            theory_binding=predecessor["current_theory"],
            theory_approval_binding=approval_binding,
            experiment_contract_binding=contract_binding,
            implementation_bindings=implementation_bindings,
            experiment_contract=contract,
        )
        subject_freeze = build_v31_qualification_subject_freeze(
            manifest_subject=subject, frozen_at=subject_created_at
        )
        preflight_write_once_json(project, paths["experiment_contract"], contract)
        preflight_write_once_json(
            project, paths["qualification_subject"], subject_freeze
        )
        written_contract_binding = write_once_json(
            project,
            paths["experiment_contract"],
            contract,
            digest_field="experiment_contract_digest",
        )
        if written_contract_binding != contract_binding:
            raise V31AuthorityFreezeCompositionError(
                "V31_FREEZE_CONTRACT_WRITE_BINDING_DRIFT"
            )
        write_once_json(
            project,
            paths["qualification_subject"],
            subject_freeze,
            digest_field=QUALIFICATION_SUBJECT_DIGEST_FIELD,
        )
        loaded = _load_phase_a(project, run_id=run_id)
        return {
            **loaded,
            "status": "QUALIFICATION_SUBJECT_FROZEN_AUTHORITY_NOT_CREATED",
        }
    except V31AuthorityFreezeCompositionError:
        raise
    except (
        V31AuthorityFreezeError,
        V31AuthorityFreezeStoreError,
        V31AuthorizationError,
        OSError,
        ValueError,
    ) as exc:
        raise V31AuthorityFreezeCompositionError(
            f"V31_FREEZE_PHASE_A_FAILED:{exc}"
        ) from exc


def verify_external_qualification_physical_replay(
    *, project_root: Path, receipts: Mapping[str, Mapping[str, Any]]
) -> None:
    try:
        verify_q6_receipt_durable_artifacts(
            project_root=project_root, receipt=receipts["Q6"]
        )
    except (V31ExternalQualificationWorkflowError, KeyError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_Q6_DURABLE_REPLAY_INVALID"
        ) from exc

    # Q7 is deliberately discovered at call time.  Until the production
    # authoring -> compiler -> post-seal selection replay hook exists, Phase B
    # must fail before writing even one receipt.
    try:
        from ..application import v31_external_qualification as external_workflow

        verifier = getattr(
            external_workflow, "verify_q7_receipt_durable_artifacts"
        )
    except (AttributeError, ImportError) as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_Q7_DURABLE_REPLAY_NOT_AVAILABLE"
        ) from exc
    if not callable(verifier):
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_Q7_DURABLE_REPLAY_NOT_AVAILABLE"
        )
    try:
        verifier(project_root=project_root, receipt=receipts["Q7"])
    except (KeyError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_Q7_DURABLE_REPLAY_INVALID"
        ) from exc


def finalize_v31_active_authority(
    *,
    project_root: Path,
    run_id: str,
    qualification_receipts: Mapping[str, Mapping[str, Any]],
    authorization_id: str,
    authority_id: str,
    issued_at: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Phase B: publish Q0-Q8 -> manifest -> authorization -> ACTIVE authority."""

    try:
        project = Path(project_root).resolve(strict=True)
        phase_a = _load_phase_a(project, run_id=run_id)
        subject = phase_a["manifest_subject"]
        contract = phase_a["experiment_contract"]
        approval = phase_a["theory_approval"]
        if set(qualification_receipts) != set(GATE_IDS):
            raise V31AuthorityFreezeCompositionError(
                "V31_FREEZE_Q0_Q8_SET_INCOMPLETE"
            )
        receipts = {
            gate_id: copy.deepcopy(dict(qualification_receipts[gate_id]))
            for gate_id in GATE_IDS
        }
        for gate_id in GATE_IDS:
            validate_v31_qualification_receipt(
                receipts[gate_id],
                expected_gate_id=gate_id,
                experiment_contract=contract,
                manifest=subject,
                theory_approval=approval,
            )
        verify_external_qualification_physical_replay(
            project_root=project, receipts=receipts
        )
        paths = phase_a["paths"]
        documents = build_v31_final_authority_documents(
            manifest_subject=subject,
            experiment_contract=contract,
            theory_approval=approval,
            qualification_receipts=receipts,
            qualification_receipt_paths=paths["qualification_receipts"],
            final_manifest_path=paths["final_manifest"],
            authorization_receipt_path=paths["authorization_receipt"],
            active_authority_path=paths["active_authority"],
            predecessor_authority_binding=phase_a["predecessor_authority_binding"],
            authorization_id=authorization_id,
            authority_id=authority_id,
            issued_at=issued_at,
            recorded_at=recorded_at,
        )

        write_set: list[tuple[str, Mapping[str, Any], str]] = [
            (
                paths["qualification_receipts"][gate_id],
                receipts[gate_id],
                "qualification_receipt_digest",
            )
            for gate_id in GATE_IDS
        ]
        write_set.extend(
            [
                (paths["final_manifest"], documents["manifest"], "manifest_digest"),
                (
                    paths["authorization_receipt"],
                    documents["authorization_receipt"],
                    "authorization_receipt_digest",
                ),
                (
                    paths["active_authority"],
                    documents["active_authority"],
                    "authority_digest",
                ),
            ]
        )
        # Re-read every Phase-A byte immediately before publication so drift
        # during an external replay cannot leave a newly ACTIVE file behind.
        rechecked = _load_phase_a(project, run_id=run_id)
        if (
            rechecked["experiment_contract"] != contract
            or rechecked["manifest_subject"] != subject
            or rechecked["theory_approval"] != approval
            or rechecked["predecessor_authority_binding"]
            != phase_a["predecessor_authority_binding"]
        ):
            raise V31AuthorityFreezeCompositionError(
                "V31_FREEZE_PHASE_A_RECHECK_DRIFT"
            )
        for path, document, _ in write_set:
            preflight_write_once_json(project, path, document)
        for path, document, digest_field in write_set:
            binding = write_once_json(
                project, path, document, digest_field=digest_field
            )
            expected = document_binding(
                path=path, document=document, digest_field=digest_field
            )
            if binding != expected:
                raise V31AuthorityFreezeCompositionError(
                    "V31_FREEZE_PUBLISHED_BINDING_DRIFT"
                )
        loaded = load_v31_active_authorization_chain(project)
        if (
            loaded["authority"] != documents["active_authority"]
            or loaded["authorization_receipt"]
            != documents["authorization_receipt"]
            or loaded["manifest"] != documents["manifest"]
            or loaded["experiment_contract"] != contract
            or loaded["theory_approval"] != approval
            or loaded["qualification_receipts"]
            != {gate_id: receipts[gate_id] for gate_id in GATE_IDS}
        ):
            raise V31AuthorityFreezeCompositionError(
                "V31_FREEZE_FORMAL_LOADER_REPLAY_MISMATCH"
            )
        return {
            "status": "ACTIVE_FROZEN_RESEARCH_NOT_YET_GENESIS_INITIALIZED",
            "paths": paths,
            "loaded_chain": loaded,
        }
    except V31AuthorityFreezeCompositionError:
        raise
    except (
        V31AuthorityFreezeError,
        V31AuthorityFreezeStoreError,
        V31AuthorizationError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise V31AuthorityFreezeCompositionError(
            f"V31_FREEZE_PHASE_B_FAILED:{exc}"
        ) from exc


def prepare_v31_run_genesis_inputs_from_loaded_chain(
    *, project_root: Path, loaded_chain: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive the exact five immutable genesis sources from loader output."""

    try:
        authority = loaded_chain["authority"]
        documents = {
            "theory_approval": copy.deepcopy(loaded_chain["theory_approval"]),
            "experiment_contract": copy.deepcopy(
                loaded_chain["experiment_contract"]
            ),
            "experiment_manifest": copy.deepcopy(loaded_chain["manifest"]),
            "experiment_authorization": copy.deepcopy(
                loaded_chain["authorization_receipt"]
            ),
            "current_authority": copy.deepcopy(authority),
        }
        current_authority_binding = binding_for_existing_document(
            project_root, ACTIVE_AUTHORITY_PATH, digest_field="authority_digest"
        )
        global_bindings = {
            "theory_approval": copy.deepcopy(authority["theory_approval_binding"]),
            "experiment_contract": copy.deepcopy(
                authority["experiment_contract_binding"]
            ),
            "experiment_manifest": copy.deepcopy(authority["manifest_binding"]),
            "experiment_authorization": copy.deepcopy(
                authority["authorization_receipt_binding"]
            ),
            "current_authority": current_authority_binding,
        }
        global_raw_bytes = {
            role: read_bytes(project_root, binding["path"])
            for role, binding in global_bindings.items()
        }
        for role, document in documents.items():
            binding = global_bindings[role]
            if (
                document.get("schema_id") != binding.get("schema_id")
                or verify_self_digest(document, binding["digest_field"])
                != binding["semantic_digest"]
            ):
                raise V31AuthorityFreezeCompositionError(
                    "V31_FREEZE_GENESIS_SOURCE_BINDING_INVALID"
                )
        return {
            "documents": documents,
            "global_bindings": global_bindings,
            "global_raw_bytes": global_raw_bytes,
        }
    except V31AuthorityFreezeCompositionError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeCompositionError(
            "V31_FREEZE_GENESIS_INPUTS_INVALID"
        ) from exc


def initialize_v31_run_genesis_from_active_authority(
    *, project_root: Path, run_root: Path, created_at: str
) -> dict[str, Any]:
    """Explicitly initialize genesis after, and only after, the formal loader passes."""

    loaded = load_v31_active_authorization_chain(project_root)
    inputs = prepare_v31_run_genesis_inputs_from_loaded_chain(
        project_root=project_root, loaded_chain=loaded
    )
    return initialize_v31_run_genesis(
        store=LocalV31ResearchStore(run_root), created_at=created_at, **inputs
    )


__all__ = [
    "ACTIVE_AUTHORITY_PATH",
    "PREDECESSOR_AUTHORITY_PATH",
    "THEORY_APPROVAL_PATH",
    "V31AuthorityFreezeCompositionError",
    "finalize_v31_active_authority",
    "freeze_v31_qualification_subject",
    "initialize_v31_run_genesis_from_active_authority",
    "prepare_v31_run_genesis_inputs_from_loaded_chain",
    "verify_external_qualification_physical_replay",
    "v31_authority_freeze_paths",
]
