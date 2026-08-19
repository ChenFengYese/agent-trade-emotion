"""Production write-once composition for the V3.1.1 successor chronology.

The only supported order is:

legacy v2 failed closed -> qualification v3 -> accepted cycle 1 -> retirement
-> target v4 -> final successor envelope -> full loader -> five-doc projection.

No function in this module creates automation, reads an outcome, or grants an
account, paper, live, order, credential, funds, portfolio, or re-entry scope.
"""

from __future__ import annotations

import copy
import hashlib
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ...application.v31_authority_freeze import (
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
from ...application.v31_external_qualification import (
    V31ExternalQualificationWorkflowError,
    verify_q6_receipt_durable_artifacts,
    verify_q7_receipt_durable_artifacts,
)
from ...application.v31_run_genesis import initialize_v31_run_genesis
from ...application.v31_successor_qualification_v2 import (
    verify_fresh_public_source_qualification_durable_v2,
    verify_monitor_qualification_durable_v2,
)
from ...application.v311_codex_durable_qualification_v3 import (
    verify_current_codex_qualification_durable_v3,
)
from ...domain.contracts.canonical import load_json_strict, verify_self_digest
from ...domain.governance.v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    CODEX_QUALIFICATION_V3_SCHEMA_ID,
)
from ...domain.governance.v31_successor_qualification_v2 import (
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    MONITOR_QUALIFICATION_SCHEMA_ID,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
    SOURCE_QUALIFICATION_SCHEMA_ID,
)
from ...domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_qualification_receipt,
)
from ...domain.governance.v311_qualification_retirement_v2 import (
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_RELATIVE_NAME,
    V311QualificationRetirementV2Error,
    build_v311_qualification_retirement_receipt_v2,
    verify_v311_qualification_retirement_receipt_v2,
)
from ...domain.governance.v311_successor_user_approval_v2 import (
    REQUIRED_USER_APPROVAL_STATEMENTS,
    SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
    SUCCESSOR_USER_APPROVAL_PATH,
    build_v311_successor_user_approval_receipt_v2,
    verify_v311_successor_user_approval_receipt_v2,
)
from ...domain.governance.v311_qualification_genesis_v2 import (
    v311_qualification_genesis_inputs_v2,
)
from ...domain.governance.v311_successor_authority_envelope_v2 import (
    ENVELOPE_DIGEST_FIELD,
    V311_AUXILIARY_DOCUMENT_KEYS,
    V311_FRESH_QUALIFICATION_KEYS,
    V311_LEGACY_RUN_ID,
    V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
    V311_TARGET_ACTIVE_AUTHORITY_PATH,
    V311_THEORY_ADDENDUM_PATH,
    build_v311_runtime_closure_receipt_v2,
    build_v311_successor_authority_envelope_v2,
    project_v311_application_authority_chain_v2,
)
from ...domain.v31_experiment_contracts import build_minimal_experiment_contract
from .v31_current_research import (
    load_v31_active_authorization_chain,
)
from .v31_runtime_closure_v2 import (
    build_v31_runtime_closure_bindings_v2,
)
from .v311_fresh_process_trace_v2 import (
    V311FreshProcessTraceCollectorV2Error,
    collect_v311_fresh_process_trace_v2,
)
from .v311_successor_current_research_v2 import (
    V311_SUCCESSOR_AUTHORITY_ENVELOPE_PATH,
    load_v311_legacy_failure_evidence_v2,
    load_v311_successor_authorization_chain_v2,
    load_v311_versioned_standard_authority_chain_v2,
)
from ..v31_authority_freeze_store import (
    V31AuthorityFreezeStoreError,
    binding_for_existing_document,
    collect_exact_implementation_bindings,
    load_self_digested_document,
    preflight_write_once_json,
    read_bytes,
    sha256_file,
    write_once_json,
)
from ..v31_research_store import (
    LocalV31ResearchStore,
    V31ResearchStoreError,
)
from ..v31_monitor_store import LocalV31MonitorStore, V31MonitorStoreError


class V311SuccessorAuthorityCompositionV2Error(ValueError):
    """The production successor chronology failed closed."""


QUALIFICATION_V3 = "QUALIFICATION_V3"
TARGET_V4 = "TARGET_V4"
_ROLES = (QUALIFICATION_V3, TARGET_V4)
_THEORY_APPROVAL_PATH = "config/theory_paper_v31.theory_approval.20260806.json"
_DIGEST_FIELDS = {
    "theory_approval": "approval_receipt_digest",
    "experiment_contract": "experiment_contract_digest",
    "manifest": "manifest_digest",
    "authorization_receipt": "authorization_receipt_digest",
    "authority": "authority_digest",
}
_AUX_DIGEST_FIELDS = {
    "clock_policy": "clock_policy_digest",
    "supervisor_policy": "supervisor_policy_digest",
    "runtime_closure": "runtime_closure_receipt_digest",
    "sentiment_source_registry": "registry_digest",
    "association_preregistration": "association_preregistration_digest",
    "evaluation_contract": "evaluation_contract_digest",
}
_FRESH_DIGEST_FIELDS = {
    "public_source": "source_qualification_v2_digest",
    "codex_durable_delivery": CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    "outcome_monitor": "monitor_qualification_v2_digest",
}
_FRESH_SCHEMA_IDS = {
    "public_source": SOURCE_QUALIFICATION_SCHEMA_ID,
    "codex_durable_delivery": CODEX_QUALIFICATION_V3_SCHEMA_ID,
    "outcome_monitor": MONITOR_QUALIFICATION_SCHEMA_ID,
}


def _canonical_time() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V311SuccessorAuthorityCompositionV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311SuccessorAuthorityCompositionV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V311SuccessorAuthorityCompositionV2Error(code)
    parsed = parsed.astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise V311SuccessorAuthorityCompositionV2Error(code)
    return parsed


def _project_root(value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_PROJECT_ROOT_INVALID"
        )
    return root


def _role(value: str) -> str:
    if value not in _ROLES:
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_AUTHORITY_VERSION_INVALID"
        )
    return value


def v311_versioned_authority_paths_v2(
    *, authority_version: str, run_id: str
) -> dict[str, Any]:
    """Return the fixed write set for one versioned standard authority."""

    role = _role(authority_version)
    if (
        not isinstance(run_id, str)
        or not 8 <= len(run_id) <= 128
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789._-"
            for character in run_id
        )
    ):
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_RUN_ID_INVALID"
        )
    role_dir = "qualification-v3" if role == QUALIFICATION_V3 else "target-v4"
    root = f"config/v311-authority/{role_dir}/{run_id}"
    return {
        "root": root,
        "experiment_contract": f"{root}/experiment-contract.json",
        "qualification_subject": f"{root}/qualification-manifest-subject.json",
        "qualification_receipts": {
            gate: f"{root}/qualification-{gate.lower()}.json"
            for gate in GATE_IDS
        },
        "final_manifest": f"{root}/frozen-experiment-manifest.json",
        "authorization_receipt": f"{root}/experiment-authorization.json",
        "active_authority": (
            V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH
            if role == QUALIFICATION_V3
            else V311_TARGET_ACTIVE_AUTHORITY_PATH
        ),
    }


def _standard_bindings(
    *, project_root: Path, authority_version: str, loaded_chain: Mapping[str, Any]
) -> dict[str, dict[str, str]]:
    active = (
        V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH
        if authority_version == QUALIFICATION_V3
        else V311_TARGET_ACTIVE_AUTHORITY_PATH
    )
    authority = loaded_chain["authority"]
    return {
        "theory_approval": dict(authority["theory_approval_binding"]),
        "experiment_contract": dict(authority["experiment_contract_binding"]),
        "manifest": dict(authority["manifest_binding"]),
        "authorization_receipt": dict(
            authority["authorization_receipt_binding"]
        ),
        "authority": binding_for_existing_document(
            project_root, active, digest_field="authority_digest"
        ),
    }


def seal_v311_successor_user_approval_v2(
    *, project_root: Path, approval_id: str, approved_at: str
) -> dict[str, Any]:
    """Write the explicit in-thread V3.1.1 approval as a required receipt."""

    try:
        project = _project_root(project_root)
        addendum = project / V311_THEORY_ADDENDUM_PATH
        addendum_binding = {
            "path": V311_THEORY_ADDENDUM_PATH,
            "version": "3.1.1",
            "review_status": "FROZEN_APPROVED_SUCCESSOR",
            "physical_sha256": hashlib.sha256(addendum.read_bytes()).hexdigest(),
        }
        receipt = build_v311_successor_user_approval_receipt_v2(
            approval_id=approval_id,
            approved_at=approved_at,
            theory_addendum_binding=addendum_binding,
            user_statements=REQUIRED_USER_APPROVAL_STATEMENTS,
        )
        binding = write_once_json(
            project,
            SUCCESSOR_USER_APPROVAL_PATH,
            receipt,
            digest_field=SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
        )
        return {"receipt": receipt, "binding": binding}
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            f"V311_COMPOSITION_SUCCESSOR_APPROVAL_FAILED:{exc}"
        ) from exc


def load_v311_successor_user_approval_v2(
    *, project_root: Path
) -> dict[str, Any]:
    project = _project_root(project_root)
    try:
        receipt = load_self_digested_document(
            project,
            SUCCESSOR_USER_APPROVAL_PATH,
            digest_field=SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
        )
        verify_v311_successor_user_approval_receipt_v2(receipt)
        addendum = project / V311_THEORY_ADDENDUM_PATH
        if hashlib.sha256(addendum.read_bytes()).hexdigest() != receipt[
            "theory_addendum_binding"
        ]["physical_sha256"]:
            raise ValueError("addendum drift")
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_SUCCESSOR_APPROVAL_NOT_REPLAYABLE"
        ) from exc
    return receipt


def _phase_a(
    project_root: Path, *, authority_version: str, run_id: str
) -> dict[str, Any]:
    paths = v311_versioned_authority_paths_v2(
        authority_version=authority_version, run_id=run_id
    )
    contract = load_self_digested_document(
        project_root,
        paths["experiment_contract"],
        digest_field="experiment_contract_digest",
    )
    freeze = load_self_digested_document(
        project_root,
        paths["qualification_subject"],
        digest_field=QUALIFICATION_SUBJECT_DIGEST_FIELD,
    )
    subject = verify_v31_qualification_subject_freeze(
        freeze, experiment_contract=contract
    )
    if contract.get("run_id") != run_id or subject.get("run_id") != run_id:
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_PHASE_A_RUN_MISMATCH"
        )
    return {
        "paths": paths,
        "experiment_contract": contract,
        "subject_freeze": freeze,
        "manifest_subject": subject,
    }


def _verify_external_qualification_physical_replay(
    *, project_root: Path, receipts: Mapping[str, Mapping[str, Any]]
) -> None:
    try:
        verify_q6_receipt_durable_artifacts(
            project_root=project_root, receipt=receipts["Q6"]
        )
        verify_q7_receipt_durable_artifacts(
            project_root=project_root, receipt=receipts["Q7"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_EXTERNAL_QUALIFICATION_REPLAY_INVALID"
        ) from exc


def freeze_v311_versioned_authority_subject_v2(
    *,
    project_root: Path,
    authority_version: str,
    run_id: str,
    contract_id: str,
    manifest_id: str,
    contract_frozen_at: str,
    subject_created_at: str,
    qualification_run_id: str | None = None,
) -> dict[str, Any]:
    """Write Phase A for the qualification-v3 or retired-successor target-v4."""

    try:
        project = _project_root(project_root)
        role = _role(authority_version)
        paths = v311_versioned_authority_paths_v2(
            authority_version=role, run_id=run_id
        )
        legacy_chain = load_v31_active_authorization_chain(project)
        legacy_failure = load_v311_legacy_failure_evidence_v2(
            project, legacy_active_chain=legacy_chain
        )
        successor_approval = load_v311_successor_user_approval_v2(
            project_root=project
        )
        lower_bound = _time(
            legacy_failure["monitor_failure"]["occurred_at"],
            "V311_COMPOSITION_LEGACY_FAILURE_TIME_INVALID",
        )
        lower_bound = max(
            lower_bound,
            _time(
                successor_approval["approved_at"],
                "V311_COMPOSITION_SUCCESSOR_APPROVAL_TIME_INVALID",
            ),
        )
        if role == QUALIFICATION_V3:
            if qualification_run_id is not None or (
                project / V311_TARGET_ACTIVE_AUTHORITY_PATH
            ).exists():
                raise V311SuccessorAuthorityCompositionV2Error(
                    "V311_COMPOSITION_QUALIFICATION_ORDER_INVALID"
                )
        else:
            retirement = load_v311_qualification_retirement_v2(
                project_root=project,
                qualification_run_id=str(qualification_run_id or ""),
            )
            if retirement["target_run_id"] != run_id:
                raise V311SuccessorAuthorityCompositionV2Error(
                    "V311_COMPOSITION_RETIREMENT_TARGET_MISMATCH"
                )
            lower_bound = _time(
                retirement["retired_at"],
                "V311_COMPOSITION_RETIREMENT_TIME_INVALID",
            )
        contract_time = _time(
            contract_frozen_at, "V311_COMPOSITION_CONTRACT_TIME_INVALID"
        )
        subject_time = _time(
            subject_created_at, "V311_COMPOSITION_SUBJECT_TIME_INVALID"
        )
        if contract_time <= lower_bound or subject_time < contract_time:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_PHASE_A_CHRONOLOGY_INVALID"
            )
        approval = legacy_chain["theory_approval"]
        approval_binding = binding_for_existing_document(
            project, _THEORY_APPROVAL_PATH, digest_field="approval_receipt_digest"
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
        implementation_bindings = collect_exact_implementation_bindings(
            project, exact_paths=V31_PRODUCTION_RUNTIME_PATHS
        )
        subject = build_v31_qualification_manifest_subject(
            run_id=run_id,
            manifest_id=manifest_id,
            created_at=subject_created_at,
            theory_binding=legacy_chain["predecessor_authority"]["current_theory"],
            theory_approval_binding=approval_binding,
            experiment_contract_binding=contract_binding,
            implementation_bindings=implementation_bindings,
            experiment_contract=contract,
        )
        freeze = build_v31_qualification_subject_freeze(
            manifest_subject=subject, frozen_at=subject_created_at
        )
        for path, document in (
            (paths["experiment_contract"], contract),
            (paths["qualification_subject"], freeze),
        ):
            preflight_write_once_json(project, path, document)
        write_once_json(
            project,
            paths["experiment_contract"],
            contract,
            digest_field="experiment_contract_digest",
        )
        write_once_json(
            project,
            paths["qualification_subject"],
            freeze,
            digest_field=QUALIFICATION_SUBJECT_DIGEST_FIELD,
        )
        loaded = _phase_a(project, authority_version=role, run_id=run_id)
        return {
            **loaded,
            "theory_approval": copy.deepcopy(approval),
            "status": "QUALIFICATION_SUBJECT_FROZEN_AUTHORITY_NOT_CREATED",
        }
    except V311SuccessorAuthorityCompositionV2Error:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            f"V311_COMPOSITION_PHASE_A_FAILED:{exc}"
        ) from exc


def finalize_v311_versioned_standard_authority_v2(
    *,
    project_root: Path,
    authority_version: str,
    run_id: str,
    qualification_receipts: Mapping[str, Mapping[str, Any]],
    authorization_id: str,
    authority_id: str,
    issued_at: str,
    recorded_at: str,
    qualification_run_id: str | None = None,
) -> dict[str, Any]:
    """Publish Q0-Q8, standard documents, and the versioned authority last."""

    try:
        project = _project_root(project_root)
        role = _role(authority_version)
        legacy = load_v31_active_authorization_chain(project)
        failure = load_v311_legacy_failure_evidence_v2(
            project, legacy_active_chain=legacy
        )
        successor_approval = load_v311_successor_user_approval_v2(
            project_root=project
        )
        phase = _phase_a(project, authority_version=role, run_id=run_id)
        if not isinstance(qualification_receipts, Mapping) or tuple(
            qualification_receipts
        ) != GATE_IDS:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_Q0_Q8_INVALID"
            )
        receipts = {
            gate: copy.deepcopy(dict(qualification_receipts[gate]))
            for gate in GATE_IDS
        }
        for gate in GATE_IDS:
            validate_v31_qualification_receipt(
                receipts[gate],
                expected_gate_id=gate,
                experiment_contract=phase["experiment_contract"],
                manifest=phase["manifest_subject"],
                theory_approval=legacy["theory_approval"],
            )
        _verify_external_qualification_physical_replay(
            project_root=project, receipts=receipts
        )
        lower_bound = _time(
            failure["monitor_failure"]["occurred_at"],
            "V311_COMPOSITION_LEGACY_FAILURE_TIME_INVALID",
        )
        lower_bound = max(
            lower_bound,
            _time(
                successor_approval["approved_at"],
                "V311_COMPOSITION_SUCCESSOR_APPROVAL_TIME_INVALID",
            ),
        )
        if role == TARGET_V4:
            retirement = load_v311_qualification_retirement_v2(
                project_root=project,
                qualification_run_id=str(qualification_run_id or ""),
            )
            if retirement["target_run_id"] != run_id:
                raise V311SuccessorAuthorityCompositionV2Error(
                    "V311_COMPOSITION_RETIREMENT_TARGET_MISMATCH"
                )
            lower_bound = _time(
                retirement["retired_at"],
                "V311_COMPOSITION_RETIREMENT_TIME_INVALID",
            )
        if _time(recorded_at, "V311_COMPOSITION_AUTHORITY_TIME_INVALID") <= lower_bound:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_AUTHORITY_CHRONOLOGY_INVALID"
            )
        paths = phase["paths"]
        documents = build_v31_final_authority_documents(
            manifest_subject=phase["manifest_subject"],
            experiment_contract=phase["experiment_contract"],
            theory_approval=legacy["theory_approval"],
            qualification_receipts=receipts,
            qualification_receipt_paths=paths["qualification_receipts"],
            final_manifest_path=paths["final_manifest"],
            authorization_receipt_path=paths["authorization_receipt"],
            # The legacy pure builder's path guard is publication-only; the
            # authority document has no self-path field.  This composition
            # writes and then replays the actual fixed v3/v4 path below.
            active_authority_path=(
                "config/theory_paper_v31.current_research_authority.v2.json"
            ),
            predecessor_authority_binding=legacy["authority"][
                "predecessor_authority_binding"
            ],
            authorization_id=authorization_id,
            authority_id=authority_id,
            issued_at=issued_at,
            recorded_at=recorded_at,
        )
        write_set = [
            (
                paths["qualification_receipts"][gate],
                receipts[gate],
                "qualification_receipt_digest",
            )
            for gate in GATE_IDS
        ] + [
            (paths["final_manifest"], documents["manifest"], "manifest_digest"),
            (
                paths["authorization_receipt"],
                documents["authorization_receipt"],
                "authorization_receipt_digest",
            ),
            (paths["active_authority"], documents["active_authority"], "authority_digest"),
        ]
        for path, document, _digest_field in write_set:
            preflight_write_once_json(project, path, document)
        for path, document, digest_field in write_set:
            write_once_json(
                project, path, document, digest_field=digest_field
            )
        loaded = load_v311_versioned_standard_authority_chain_v2(
            project, authority_version=role
        )
        if loaded["authority"] != documents["active_authority"]:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_STANDARD_LOADER_MISMATCH"
            )
        return {
            "status": "ACTIVE_FROZEN_RESEARCH_VERSIONED",
            "paths": paths,
            "loaded_chain": loaded,
        }
    except V311SuccessorAuthorityCompositionV2Error:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            f"V311_COMPOSITION_FINALIZE_FAILED:{exc}"
        ) from exc


def initialize_v311_qualification_run_genesis_v2(
    *, project_root: Path, qualification_run_id: str, created_at: str
) -> dict[str, Any]:
    """Copy the standard v3 five-document chain into the sole genesis paths."""

    try:
        project = _project_root(project_root)
        load_v311_successor_user_approval_v2(project_root=project)
        chain = load_v311_versioned_standard_authority_chain_v2(
            project, authority_version=QUALIFICATION_V3
        )
        if chain["authority"].get("authorized_run_id") != qualification_run_id:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_QUALIFICATION_RUN_MISMATCH"
            )
        standard_bindings = _standard_bindings(
            project_root=project,
            authority_version=QUALIFICATION_V3,
            loaded_chain=chain,
        )
        documents, global_bindings = v311_qualification_genesis_inputs_v2(
            qualification_v3_chain=chain,
            qualification_v3_document_bindings=standard_bindings,
        )
        global_raw_bytes = {
            role: read_bytes(project, str(binding["path"]))
            for role, binding in global_bindings.items()
        }
        run_root = project / f"agent-cluster/experiments/{qualification_run_id}"
        result = initialize_v31_run_genesis(
            store=LocalV31ResearchStore(run_root),
            created_at=created_at,
            documents=documents,
            global_bindings=global_bindings,
            global_raw_bytes=global_raw_bytes,
        )
        authority_binding = next(
            row
            for row in result["run_genesis"]["genesis_artifacts"]
            if row["source_role"] == "current_authority"
        )
        return {
            **result,
            "authority_copy_binding": {
                "relative_ref": authority_binding["local_ref"],
                "schema_id": authority_binding["schema_id"],
                "digest_field": authority_binding["digest_field"],
                "semantic_digest": authority_binding["semantic_digest"],
                "physical_sha256": authority_binding[
                    "local_physical_sha256"
                ],
            },
            "standard_authority_binding": standard_bindings["authority"],
        }
    except V311SuccessorAuthorityCompositionV2Error:
        raise
    except (OSError, StopIteration, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            f"V311_COMPOSITION_QUALIFICATION_GENESIS_FAILED:{exc}"
        ) from exc


def _load_v311_fresh_qualifications_v3(
    *,
    project: Path,
    qualification_run_id: str,
    qualification_chain: Mapping[str, Any],
    successor_qualification_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Physically replay the v3-only fresh qualification set.

    The historical generic loader accepts the weaker Codex-v2 receipt.  The
    successor chronology must not call it: accepting that receipt would lose
    the direct version-bound context, consumption, and commit-envelope proof.
    """

    if (
        not isinstance(successor_qualification_bindings, Mapping)
        or tuple(successor_qualification_bindings)
        != V311_FRESH_QUALIFICATION_KEYS
    ):
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_FRESH_BINDINGS_INVALID"
        )
    run_root_ref = f"agent-cluster/experiments/{qualification_run_id}"
    run_root = project / run_root_ref
    authority = qualification_chain["authority"]
    authority_digest = str(authority["authority_digest"])
    documents: dict[str, dict[str, Any]] = {}
    for name in V311_FRESH_QUALIFICATION_KEYS:
        supplied = dict(successor_qualification_bindings[name])
        if (
            set(supplied)
            != {
                "path",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
            }
            or supplied.get("schema_id") != _FRESH_SCHEMA_IDS[name]
            or supplied.get("digest_field") != _FRESH_DIGEST_FIELDS[name]
        ):
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_FRESH_BINDING_INVALID"
            )
        document = load_self_digested_document(
            project,
            str(supplied["path"]),
            digest_field=_FRESH_DIGEST_FIELDS[name],
        )
        actual = binding_for_existing_document(
            project,
            str(supplied["path"]),
            digest_field=_FRESH_DIGEST_FIELDS[name],
        )
        if actual != supplied or document.get("schema_id") != _FRESH_SCHEMA_IDS[name]:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_FRESH_BINDING_DRIFT"
            )
        documents[name] = document
    verify_fresh_public_source_qualification_durable_v2(
        project_root=project,
        authority=authority,
        validated_authority_digest=authority_digest,
        document=documents["public_source"],
    )
    verify_current_codex_qualification_durable_v3(
        project_root=project,
        run_root_ref=run_root_ref,
        authority=authority,
        validated_authority_digest=authority_digest,
        document=documents["codex_durable_delivery"],
    )
    verify_monitor_qualification_durable_v2(
        run_root=run_root,
        document=documents["outcome_monitor"],
    )
    return documents


def seal_v311_qualification_retirement_v2(
    *,
    project_root: Path,
    qualification_run_id: str,
    target_run_id: str,
    retirement_id: str,
    retired_at: str,
    successor_qualification_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Durably replay all qualification evidence and retire at cycle one."""

    try:
        project = _project_root(project_root)
        if (project / V311_TARGET_ACTIVE_AUTHORITY_PATH).exists():
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_TARGET_PRECEDES_RETIREMENT"
            )
        legacy = load_v31_active_authorization_chain(project)
        failure = load_v311_legacy_failure_evidence_v2(
            project, legacy_active_chain=legacy
        )
        qualification_chain = load_v311_versioned_standard_authority_chain_v2(
            project, authority_version=QUALIFICATION_V3
        )
        if qualification_chain["authority"]["authorized_run_id"] != qualification_run_id:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_QUALIFICATION_RUN_MISMATCH"
            )
        run_root_ref = f"agent-cluster/experiments/{qualification_run_id}"
        qualifications = _load_v311_fresh_qualifications_v3(
            project=project,
            qualification_run_id=qualification_run_id,
            qualification_chain=qualification_chain,
            successor_qualification_bindings=successor_qualification_bindings,
        )
        research_store = LocalV31ResearchStore(project / run_root_ref)
        checkpoint = dict(
            research_store.load_checkpoint(run_id=qualification_run_id)
        )
        checkpoint_binding = binding_for_existing_document(
            project,
            f"{run_root_ref}/checkpoint.json",
            digest_field="checkpoint_digest",
        )
        standard_bindings = _standard_bindings(
            project_root=project,
            authority_version=QUALIFICATION_V3,
            loaded_chain=qualification_chain,
        )
        run_genesis = research_store.read_document(
            relative_ref="genesis/run-genesis.json",
            digest_field="run_genesis_digest",
            expected_semantic_digest=str(
                checkpoint["run_genesis_digest"]
            ),
        )
        run_genesis_binding = binding_for_existing_document(
            project,
            f"{run_root_ref}/genesis/run-genesis.json",
            digest_field="run_genesis_digest",
        )
        monitor_checkpoint = dict(
            LocalV31MonitorStore(project / run_root_ref).load_checkpoint(
                run_id=qualification_run_id
            )
        )
        monitor_checkpoint_binding = binding_for_existing_document(
            project,
            f"{run_root_ref}/monitor/checkpoint.json",
            digest_field="checkpoint_digest",
        )
        retirement = build_v311_qualification_retirement_receipt_v2(
            retirement_id=retirement_id,
            retired_at=retired_at,
            target_run_id=target_run_id,
            qualification_v3_chain=qualification_chain,
            qualification_v3_document_bindings=standard_bindings,
            qualification_run_genesis=run_genesis,
            qualification_run_genesis_binding=run_genesis_binding,
            research_checkpoint=checkpoint,
            research_checkpoint_binding=checkpoint_binding,
            monitor_checkpoint=monitor_checkpoint,
            monitor_checkpoint_binding=monitor_checkpoint_binding,
            successor_qualifications=qualifications,
            successor_qualification_bindings={
                name: dict(successor_qualification_bindings[name])
                for name in V311_FRESH_QUALIFICATION_KEYS
            },
        )
        path = f"{run_root_ref}/{QUALIFICATION_RETIREMENT_RELATIVE_NAME}"
        binding = write_once_json(
            project,
            path,
            retirement,
            digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        )
        return {"receipt": retirement, "binding": binding}
    except V311SuccessorAuthorityCompositionV2Error:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            f"V311_COMPOSITION_RETIREMENT_FAILED:{exc}"
        ) from exc


def load_v311_qualification_retirement_v2(
    *, project_root: Path, qualification_run_id: str
) -> dict[str, Any]:
    """Read and semantically verify the fixed retirement tombstone."""

    project = _project_root(project_root)
    path = (
        f"agent-cluster/experiments/{qualification_run_id}/"
        f"{QUALIFICATION_RETIREMENT_RELATIVE_NAME}"
    )
    try:
        receipt = load_self_digested_document(
            project, path, digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD
        )
        verify_v311_qualification_retirement_receipt_v2(receipt)
        legacy = load_v31_active_authorization_chain(project)
        failure = load_v311_legacy_failure_evidence_v2(
            project, legacy_active_chain=legacy
        )
        qualification_chain = load_v311_versioned_standard_authority_chain_v2(
            project, authority_version=QUALIFICATION_V3
        )
        run_root_ref = f"agent-cluster/experiments/{qualification_run_id}"
        qualifications = _load_v311_fresh_qualifications_v3(
            project=project,
            qualification_run_id=qualification_run_id,
            qualification_chain=qualification_chain,
            successor_qualification_bindings=receipt[
                "fresh_qualification_bindings"
            ],
        )
        checkpoint = dict(
            LocalV31ResearchStore(project / run_root_ref).load_checkpoint(
                run_id=qualification_run_id
            )
        )
        research_store = LocalV31ResearchStore(project / run_root_ref)
        run_genesis = research_store.read_document(
            relative_ref="genesis/run-genesis.json",
            digest_field="run_genesis_digest",
            expected_semantic_digest=str(
                checkpoint["run_genesis_digest"]
            ),
        )
        monitor_checkpoint = dict(
            LocalV31MonitorStore(project / run_root_ref).load_checkpoint(
                run_id=qualification_run_id
            )
        )
        standard_bindings = _standard_bindings(
            project_root=project,
            authority_version=QUALIFICATION_V3,
            loaded_chain=qualification_chain,
        )
        rebuilt = build_v311_qualification_retirement_receipt_v2(
            retirement_id=str(receipt["retirement_id"]),
            retired_at=str(receipt["retired_at"]),
            target_run_id=str(receipt["target_run_id"]),
            qualification_v3_chain=qualification_chain,
            qualification_v3_document_bindings=standard_bindings,
            qualification_run_genesis=run_genesis,
            qualification_run_genesis_binding=binding_for_existing_document(
                project,
                f"{run_root_ref}/genesis/run-genesis.json",
                digest_field="run_genesis_digest",
            ),
            research_checkpoint=checkpoint,
            research_checkpoint_binding=binding_for_existing_document(
                project,
                f"{run_root_ref}/checkpoint.json",
                digest_field="checkpoint_digest",
            ),
            monitor_checkpoint=monitor_checkpoint,
            monitor_checkpoint_binding=binding_for_existing_document(
                project,
                f"{run_root_ref}/monitor/checkpoint.json",
                digest_field="checkpoint_digest",
            ),
            successor_qualifications={
                name: qualifications[name]
                for name in V311_FRESH_QUALIFICATION_KEYS
            },
            successor_qualification_bindings={
                name: dict(receipt["fresh_qualification_bindings"][name])
                for name in V311_FRESH_QUALIFICATION_KEYS
            },
        )
        if rebuilt != receipt:
            raise ValueError("retirement replay mismatch")
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_RETIREMENT_NOT_REPLAYABLE"
        ) from exc
    if receipt.get("qualification_run_id") != qualification_run_id:
        raise V311SuccessorAuthorityCompositionV2Error(
            "V311_COMPOSITION_RETIREMENT_RUN_MISMATCH"
        )
    return receipt


def seal_v311_runtime_closure_from_fresh_process_v2(
    *,
    project_root: Path,
    python_executable: Path,
    run_scope_id: str,
    trace_id: str,
    trace_relative_path: str,
    closure_relative_path: str,
    production_root_paths: tuple[str, ...],
) -> dict[str, Any]:
    """Collect, persist, and bind an observed trace; no caller trace accepted."""

    try:
        project = _project_root(project_root)
        trace = collect_v311_fresh_process_trace_v2(
            project_root=project,
            python_executable=python_executable,
            trace_id=trace_id,
            invocation_nonce=secrets.token_hex(32),
            production_root_paths=production_root_paths,
        )
        trace_binding = write_once_json(
            project,
            trace_relative_path,
            trace,
            digest_field="fresh_process_trace_digest",
        )
        frozen_bindings = build_v31_runtime_closure_bindings_v2(
            project_root=project,
            production_root_paths=production_root_paths,
            trace_paths=trace["observed_project_python_paths"],
        )
        closure = build_v311_runtime_closure_receipt_v2(
            run_scope_id=run_scope_id,
            frozen_at=_canonical_time(),
            production_root_paths=production_root_paths,
            fresh_process_trace=trace,
            fresh_process_trace_binding=trace_binding,
            frozen_bindings=frozen_bindings,
        )
        closure_binding = write_once_json(
            project,
            closure_relative_path,
            closure,
            digest_field="runtime_closure_receipt_digest",
        )
        return {
            "fresh_process_trace": trace,
            "fresh_process_trace_binding": trace_binding,
            "runtime_closure": closure,
            "runtime_closure_binding": closure_binding,
        }
    except V311SuccessorAuthorityCompositionV2Error:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            f"V311_COMPOSITION_RUNTIME_CLOSURE_FAILED:{exc}"
        ) from exc


def publish_v311_successor_authority_envelope_v2(
    *,
    project_root: Path,
    envelope_id: str,
    created_at: str,
    qualification_run_id: str,
    target_run_id: str,
    auxiliary_document_paths: Mapping[str, str],
    successor_qualification_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Write the final envelope and return its fully replayed target projection."""

    try:
        project = _project_root(project_root)
        legacy = load_v31_active_authorization_chain(project)
        failure = load_v311_legacy_failure_evidence_v2(
            project, legacy_active_chain=legacy
        )
        qualification = load_v311_versioned_standard_authority_chain_v2(
            project, authority_version=QUALIFICATION_V3
        )
        qualification_store = LocalV31ResearchStore(
            project
            / f"agent-cluster/experiments/{qualification_run_id}"
        )
        qualification_checkpoint = dict(
            qualification_store.load_checkpoint(run_id=qualification_run_id)
        )
        qualification_run_genesis = qualification_store.read_document(
            relative_ref="genesis/run-genesis.json",
            digest_field="run_genesis_digest",
            expected_semantic_digest=str(
                qualification_checkpoint["run_genesis_digest"]
            ),
        )
        retirement = load_v311_qualification_retirement_v2(
            project_root=project, qualification_run_id=qualification_run_id
        )
        target = load_v311_versioned_standard_authority_chain_v2(
            project, authority_version=TARGET_V4
        )
        if (
            qualification["authority"]["authorized_run_id"]
            != qualification_run_id
            or target["authority"]["authorized_run_id"] != target_run_id
            or retirement["target_run_id"] != target_run_id
        ):
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_RUN_LINEAGE_MISMATCH"
            )
        if tuple(auxiliary_document_paths) != V311_AUXILIARY_DOCUMENT_KEYS:
            raise V311SuccessorAuthorityCompositionV2Error(
                "V311_COMPOSITION_AUXILIARY_PATHS_INVALID"
            )
        auxiliary = {
            name: load_self_digested_document(
                project,
                auxiliary_document_paths[name],
                digest_field=_AUX_DIGEST_FIELDS[name],
            )
            for name in V311_AUXILIARY_DOCUMENT_KEYS
        }
        auxiliary_bindings = {
            name: binding_for_existing_document(
                project,
                auxiliary_document_paths[name],
                digest_field=_AUX_DIGEST_FIELDS[name],
            )
            for name in V311_AUXILIARY_DOCUMENT_KEYS
        }
        qualifications = _load_v311_fresh_qualifications_v3(
            project=project,
            qualification_run_id=qualification_run_id,
            qualification_chain=qualification,
            successor_qualification_bindings=successor_qualification_bindings,
        )
        retirement_path = (
            f"agent-cluster/experiments/{qualification_run_id}/"
            f"{QUALIFICATION_RETIREMENT_RELATIVE_NAME}"
        )
        retirement_binding = binding_for_existing_document(
            project,
            retirement_path,
            digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        )
        addendum_path = project / V311_THEORY_ADDENDUM_PATH
        addendum_binding = {
            "path": V311_THEORY_ADDENDUM_PATH,
            "version": "3.1.1",
            "review_status": "FROZEN_APPROVED_SUCCESSOR",
            "physical_sha256": hashlib.sha256(addendum_path.read_bytes()).hexdigest(),
        }
        successor_approval = load_v311_successor_user_approval_v2(
            project_root=project
        )
        successor_approval_binding = binding_for_existing_document(
            project,
            SUCCESSOR_USER_APPROVAL_PATH,
            digest_field=SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
        )
        envelope = build_v311_successor_authority_envelope_v2(
            envelope_id=envelope_id,
            created_at=created_at,
            legacy_active_chain=legacy,
            legacy_failure_evidence=failure,
            qualification_v3_chain=qualification,
            qualification_v3_document_bindings=_standard_bindings(
                project_root=project,
                authority_version=QUALIFICATION_V3,
                loaded_chain=qualification,
            ),
            qualification_run_root_ref=(
                f"agent-cluster/experiments/{qualification_run_id}"
            ),
            qualification_run_genesis=qualification_run_genesis,
            qualification_run_genesis_binding=binding_for_existing_document(
                project,
                f"agent-cluster/experiments/{qualification_run_id}/"
                "genesis/run-genesis.json",
                digest_field="run_genesis_digest",
            ),
            target_v4_chain=target,
            target_v4_document_bindings=_standard_bindings(
                project_root=project,
                authority_version=TARGET_V4,
                loaded_chain=target,
            ),
            theory_addendum_binding=addendum_binding,
            successor_user_approval=successor_approval,
            successor_user_approval_binding=successor_approval_binding,
            clock_policy=auxiliary["clock_policy"],
            supervisor_policy=auxiliary["supervisor_policy"],
            runtime_closure=auxiliary["runtime_closure"],
            sentiment_source_registry=auxiliary[
                "sentiment_source_registry"
            ],
            association_preregistration=auxiliary[
                "association_preregistration"
            ],
            evaluation_contract=auxiliary["evaluation_contract"],
            auxiliary_document_bindings=auxiliary_bindings,
            successor_qualifications=qualifications,
            successor_qualification_bindings=successor_qualification_bindings,
            qualification_retirement=retirement,
            qualification_retirement_binding=retirement_binding,
        )
        write_once_json(
            project,
            V311_SUCCESSOR_AUTHORITY_ENVELOPE_PATH.as_posix(),
            envelope,
            digest_field=ENVELOPE_DIGEST_FIELD,
        )
        loaded = load_v311_successor_authorization_chain_v2(project)
        return {
            "envelope": envelope,
            "loaded_chain": loaded,
            "application_authority": project_v311_application_authority_chain_v2(
                loaded
            ),
        }
    except V311SuccessorAuthorityCompositionV2Error:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityCompositionV2Error(
            f"V311_COMPOSITION_ENVELOPE_FAILED:{exc}"
        ) from exc


__all__ = [
    "QUALIFICATION_V3",
    "TARGET_V4",
    "V311SuccessorAuthorityCompositionV2Error",
    "finalize_v311_versioned_standard_authority_v2",
    "freeze_v311_versioned_authority_subject_v2",
    "initialize_v311_qualification_run_genesis_v2",
    "load_v311_qualification_retirement_v2",
    "load_v311_successor_user_approval_v2",
    "publish_v311_successor_authority_envelope_v2",
    "seal_v311_qualification_retirement_v2",
    "seal_v311_runtime_closure_from_fresh_process_v2",
    "seal_v311_successor_user_approval_v2",
    "v311_versioned_authority_paths_v2",
]
