"""Pure construction for the sole V3.1 qualification and authority freeze.

The module intentionally separates the pre-qualification subject from the
post-qualification authority chain.  It performs no file IO and grants no
market, account, order, credential, or funds capability.
"""

from __future__ import annotations

import copy
import hashlib
import re
from datetime import UTC, datetime
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    self_digest,
    verify_self_digest,
)
from ..domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_active_authority,
    validate_v31_document_binding,
    validate_v31_experiment_authorization,
    validate_v31_frozen_experiment_manifest,
    validate_v31_qualification_receipt,
    validate_v31_theory_approval,
)
from ..domain.governance.v31_experiment_qualification import (
    manifest_qualification_subject_digest,
    validate_manifest_experiment_contract_alignment,
)
from ..domain.v31_experiment_contracts import (
    EXPERIMENT_SCHEMA_ID,
    verify_minimal_experiment_contract,
)


class V31AuthorityFreezeError(ValueError):
    """A V3.1 authority-freeze input or chronology is invalid."""


QUALIFICATION_SUBJECT_SCHEMA_ID = (
    "theory_paper_v31_qualification_manifest_subject_freeze"
)
QUALIFICATION_SUBJECT_SCHEMA_VERSION = "1.0.0"
QUALIFICATION_SUBJECT_DIGEST_FIELD = "subject_freeze_digest"

GATE_IDS = tuple(f"Q{index}" for index in range(9))
EXECUTION_FALSE = {
    "account_access": False,
    "paper_trading": False,
    "live_trading": False,
    "order_submission": False,
    "credential_access": False,
    "funds_access": False,
}

# This is deliberately an explicit, reviewable runtime set rather than a
# computed union of qualification evidence.  A new runtime dependency requires
# an intentional edit and a new subject freeze; otherwise the loader detects
# physical drift or the missing binding before a run can start.
V31_PRODUCTION_RUNTIME_PATHS = (
    "tests/test_theory_paper_v2_dynamic_research.py",
    "tests/test_theory_paper_v2_v31_agent_contract.py",
    "tests/test_theory_paper_v2_v31_agent_transport.py",
    "tests/test_theory_paper_v2_v31_association_estimation.py",
    "tests/test_theory_paper_v2_v31_authority_freeze_composition.py",
    "tests/test_theory_paper_v2_v31_authorization.py",
    "tests/test_theory_paper_v2_v31_behavior_planning.py",
    "tests/test_theory_paper_v2_v31_cycle.py",
    "tests/test_theory_paper_v2_v31_cycle_authoring.py",
    "tests/test_theory_paper_v2_v31_cycle_source_admission.py",
    "tests/test_theory_paper_v2_v31_durable_bundle.py",
    "tests/test_theory_paper_v2_v31_experiment_contracts.py",
    "tests/test_theory_paper_v2_v31_experiment_qualification.py",
    "tests/test_theory_paper_v2_v31_external_qualification.py",
    "tests/test_theory_paper_v2_v31_financial_shadow.py",
    "tests/test_theory_paper_v2_v31_formal_cycle_composition.py",
    "tests/test_theory_paper_v2_v31_monitor_runtime.py",
    "tests/test_theory_paper_v2_v31_probability_path.py",
    "tests/test_theory_paper_v2_v31_public_outcome_adapter.py",
    "tests/test_theory_paper_v2_v31_research_store.py",
    "tests/test_theory_paper_v2_v31_run_genesis.py",
    "tests/test_theory_paper_v2_v31_semantic_compiler.py",
    "tests/test_theory_paper_v2_v31_source_qualification.py",
    "trade_system/theory_paper_v2/application/ports.py",
    "trade_system/theory_paper_v2/application/v31_agent_transport.py",
    "trade_system/theory_paper_v2/application/v31_authority_freeze.py",
    "trade_system/theory_paper_v2/application/v31_cycle_authoring.py",
    "trade_system/theory_paper_v2/application/v31_cycle_source_admission.py",
    "trade_system/theory_paper_v2/application/v31_durable_bundle.py",
    "trade_system/theory_paper_v2/application/v31_durable_cycle.py",
    "trade_system/theory_paper_v2/application/v31_external_qualification.py",
    "trade_system/theory_paper_v2/application/v31_formal_cycle.py",
    "trade_system/theory_paper_v2/application/v31_monitor_runtime.py",
    "trade_system/theory_paper_v2/application/v31_research_cycle.py",
    "trade_system/theory_paper_v2/application/v31_run_genesis.py",
    "trade_system/theory_paper_v2/application/v31_source_qualification.py",
    "trade_system/theory_paper_v2/domain/agent_research_contract.py",
    "trade_system/theory_paper_v2/domain/association_estimation.py",
    "trade_system/theory_paper_v2/domain/association_model.py",
    "trade_system/theory_paper_v2/domain/behavior_planning.py",
    "trade_system/theory_paper_v2/domain/contracts/canonical.py",
    "trade_system/theory_paper_v2/domain/data_model.py",
    "trade_system/theory_paper_v2/domain/dynamic_research.py",
    "trade_system/theory_paper_v2/domain/financial_evaluation.py",
    "trade_system/theory_paper_v2/domain/governance/v31_authorization.py",
    "trade_system/theory_paper_v2/domain/governance/v31_experiment_qualification.py",
    "trade_system/theory_paper_v2/domain/governance/v31_external_qualification.py",
    "trade_system/theory_paper_v2/domain/information_model.py",
    "trade_system/theory_paper_v2/domain/market_knowledge_graph.py",
    "trade_system/theory_paper_v2/domain/portfolio_truth.py",
    "trade_system/theory_paper_v2/domain/probability_cloud.py",
    "trade_system/theory_paper_v2/domain/scenario_path.py",
    "trade_system/theory_paper_v2/domain/v31_agent_transport.py",
    "trade_system/theory_paper_v2/domain/v31_cycle_authoring.py",
    "trade_system/theory_paper_v2/domain/v31_cycle_source_admission.py",
    "trade_system/theory_paper_v2/domain/v31_experiment_contracts.py",
    "trade_system/theory_paper_v2/domain/v31_financial_shadow.py",
    "trade_system/theory_paper_v2/domain/v31_monitor_runtime.py",
    "trade_system/theory_paper_v2/domain/v31_run_genesis.py",
    "trade_system/theory_paper_v2/domain/v31_source_qualification.py",
    "trade_system/theory_paper_v2/infrastructure/authority/v31_current_research.py",
    "trade_system/theory_paper_v2/infrastructure/native_market_collector.py",
    "trade_system/theory_paper_v2/infrastructure/v31_agent_transport_store.py",
    "trade_system/theory_paper_v2/infrastructure/v31_authority_freeze_store.py",
    "trade_system/theory_paper_v2/infrastructure/v31_market_adapter.py",
    "trade_system/theory_paper_v2/infrastructure/v31_monitor_store.py",
    "trade_system/theory_paper_v2/infrastructure/v31_public_outcome_adapter.py",
    "trade_system/theory_paper_v2/infrastructure/v31_research_store.py",
    "trade_system/theory_paper_v2/infrastructure/v31_semantic_compiler.py",
    "trade_system/theory_paper_v2/infrastructure/v31_source_qualification_store.py",
    "trade_system/theory_paper_v2/presentation/v31_agent_transport_worker.py",
    "trade_system/theory_paper_v2/presentation/v31_authority_freeze_composition.py",
    "trade_system/theory_paper_v2/presentation/v31_formal_cycle_composition.py",
    "trade_system/theory_paper_v2/presentation/v31_source_qualification_composition.py",
)

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise V31AuthorityFreezeError(code)
    return value


def _safe_id(value: Any, code: str) -> str:
    result = _text(value, code)
    if _SAFE_ID.fullmatch(result) is None:
        raise V31AuthorityFreezeError(code)
    return result


def _timestamp(value: Any, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31AuthorityFreezeError(code) from exc
    if parsed.tzinfo is None:
        raise V31AuthorityFreezeError(code)
    parsed = parsed.astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != text:
        raise V31AuthorityFreezeError(code)
    return parsed


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31AuthorityFreezeError(code)
    return value


def canonical_document_physical_sha256(document: Mapping[str, Any]) -> str:
    """Return the SHA-256 used by write-once JSON files in this chronology."""

    try:
        return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_DOCUMENT_INVALID") from exc


def document_binding(
    *, path: str, document: Mapping[str, Any], digest_field: str
) -> dict[str, str]:
    try:
        semantic_digest = verify_self_digest(document, digest_field)
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_DOCUMENT_BINDING_INVALID") from exc
    return {
        "path": _text(path, "V31_FREEZE_DOCUMENT_PATH_INVALID"),
        "schema_id": _text(
            document.get("schema_id"), "V31_FREEZE_DOCUMENT_SCHEMA_INVALID"
        ),
        "digest_field": digest_field,
        "semantic_digest": semantic_digest,
        "physical_sha256": canonical_document_physical_sha256(document),
    }


def build_v31_qualification_manifest_subject(
    *,
    run_id: str,
    manifest_id: str,
    created_at: str,
    theory_binding: Mapping[str, Any],
    theory_approval_binding: Mapping[str, Any],
    experiment_contract_binding: Mapping[str, Any],
    implementation_bindings: Mapping[str, str],
    experiment_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the immutable manifest subject used by every Q0-Q8 receipt."""

    run = _safe_id(run_id, "V31_FREEZE_RUN_ID_INVALID")
    _safe_id(manifest_id, "V31_FREEZE_MANIFEST_ID_INVALID")
    _timestamp(created_at, "V31_FREEZE_MANIFEST_TIME_INVALID")
    try:
        contract_digest = verify_minimal_experiment_contract(experiment_contract)
    except ValueError as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_CONTRACT_INVALID") from exc
    if (
        experiment_contract.get("run_id") != run
        or experiment_contract_binding.get("semantic_digest") != contract_digest
        or experiment_contract_binding.get("physical_sha256")
        != canonical_document_physical_sha256(experiment_contract)
        or tuple(implementation_bindings) != V31_PRODUCTION_RUNTIME_PATHS
        or any(
            not isinstance(value, str) or _HEX_64.fullmatch(value) is None
            for value in implementation_bindings.values()
        )
    ):
        raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_BINDINGS_INVALID")
    if (
        not isinstance(theory_binding, Mapping)
        or set(theory_binding)
        != {"path", "version", "review_status", "physical_sha256"}
        or theory_binding.get("version") != "3.1"
        or theory_binding.get("review_status") != "FROZEN_APPROVED"
        or not isinstance(theory_binding.get("path"), str)
        or not theory_binding["path"]
        or _HEX_64.fullmatch(str(theory_binding.get("physical_sha256") or ""))
        is None
    ):
        raise V31AuthorityFreezeError("V31_FREEZE_THEORY_BINDING_INVALID")
    try:
        validate_v31_document_binding(
            theory_approval_binding,
            code="V31_FREEZE_APPROVAL_BINDING_INVALID",
            expected_schema_id="theory_paper_v31_user_approval_receipt",
            expected_digest_field="approval_receipt_digest",
        )
        validate_v31_document_binding(
            experiment_contract_binding,
            code="V31_FREEZE_CONTRACT_BINDING_INVALID",
            expected_schema_id=EXPERIMENT_SCHEMA_ID,
            expected_digest_field="experiment_contract_digest",
        )
    except V31AuthorizationError as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_BINDINGS_INVALID") from exc
    capability_matrix = experiment_contract["capability_matrix"]
    subject = {
        "schema_id": "theory_paper_v31_frozen_experiment_manifest",
        "schema_version": "1.1.0",
        "manifest_id": manifest_id,
        "created_at": created_at,
        "run_id": run,
        "operation": "RUN_V31_PROSPECTIVE",
        "theory_binding": copy.deepcopy(dict(theory_binding)),
        "theory_approval_binding": copy.deepcopy(dict(theory_approval_binding)),
        "experiment_contract_binding": copy.deepcopy(
            dict(experiment_contract_binding)
        ),
        "symbol": "BTC-USDT",
        "instrument": {
            "venue": "OKX",
            "instrument_id": "BTC-USDT-SWAP",
            "market_type": "PERPETUAL_SWAP",
            "underlying_symbol": "BTC-USDT",
        },
        "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "source_plan": {
            "allowed_source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "raw_capture_required": True,
            "pit_available_at_required": True,
            "missing_is_unknown": True,
        },
        "agent_plan": {
            "agent_id": "CURRENT_CODEX_TASK",
            "proposal_then_postseal_selection": True,
            "durable_before_adapter_return": True,
            "reinvocation_after_accept": False,
            "sub_agents_allowed": False,
        },
        "fresh_run": True,
        "predecessor_run_id": None,
        "qualification_gates": {},
        "experiment_used_capabilities": sorted(
            row["capability_id"] for row in capability_matrix if row["used_or_evaluated"]
        ),
        "implemented_and_verified_capabilities": sorted(
            row["capability_id"]
            for row in capability_matrix
            if row["status"] == "IMPLEMENTED_AND_VERIFIED"
        ),
        "excluded_no_claim_capabilities": sorted(
            row["capability_id"]
            for row in capability_matrix
            if row["status"] == "EXCLUDED_NO_CLAIM"
        ),
        "portfolio_scope": copy.deepcopy(experiment_contract["portfolio_scope"]),
        "association_preregistration": copy.deepcopy(
            experiment_contract["association_scope"]
        ),
        "evaluation_contract": copy.deepcopy(experiment_contract["evaluation"]),
        "total_cycles": 8,
        "cadence_seconds": 3600,
        "legal_action_classes": ["OPEN_LONG", "OPEN_SHORT", "WAIT"],
        "stop_rules": copy.deepcopy(
            experiment_contract["evaluation"]["stop_rules"]["stop_immediately_on"]
        ),
        "implementation_bindings": dict(implementation_bindings),
        "assembly_bundle_contract": {
            "schema_id": "theory_paper_v2_v31_durable_assembly_bundle",
            "schema_version": "1.0.0",
            "content_addressed": True,
            "chat_history_is_authority": False,
        },
        "checkpoint_contract": {
            "schema_id": "theory_paper_v31_research_checkpoint",
            "schema_version": "1.2.0",
            "genesis_bindings_required": True,
        },
        "event_order": [
            "INPUTS_ADMITTED",
            "PROPOSAL_SEALED",
            "EVALUATION_SEALED",
            "SELECTION_SEALED",
            "STATE_ACCEPTED",
            "COMPLETION_SEALED",
        ],
        "authorization_cardinality": "EXACTLY_ONE_FRESH_RUN",
        "legacy_runs_resumable": False,
        "chat_history_is_authority": False,
        "authority_boundary": copy.deepcopy(experiment_contract["authority_boundary"]),
        **EXECUTION_FALSE,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    try:
        validate_manifest_experiment_contract_alignment(subject, experiment_contract)
    except ValueError as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_INVALID") from exc
    return subject


def build_v31_qualification_subject_freeze(
    *, manifest_subject: Mapping[str, Any], frozen_at: str
) -> dict[str, Any]:
    """Seal the exact pre-qualification subject without creating authority."""

    _timestamp(frozen_at, "V31_FREEZE_SUBJECT_TIME_INVALID")
    subject_digest = manifest_qualification_subject_digest(manifest_subject)
    document = {
        "schema_id": QUALIFICATION_SUBJECT_SCHEMA_ID,
        "schema_version": QUALIFICATION_SUBJECT_SCHEMA_VERSION,
        "frozen_at": frozen_at,
        "run_id": manifest_subject["run_id"],
        "manifest_qualification_subject_digest": subject_digest,
        "manifest_subject": copy.deepcopy(dict(manifest_subject)),
        "authority_status": "NOT_CREATED_QUALIFICATION_PENDING",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, QUALIFICATION_SUBJECT_DIGEST_FIELD)


def verify_v31_qualification_subject_freeze(
    document: Mapping[str, Any], *, experiment_contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify and return the immutable manifest subject."""

    try:
        supplied = verify_self_digest(document, QUALIFICATION_SUBJECT_DIGEST_FIELD)
        if (
            set(document)
            != {
                "schema_id",
                "schema_version",
                "frozen_at",
                "run_id",
                "manifest_qualification_subject_digest",
                "manifest_subject",
                "authority_status",
                "external_execution_authority",
                "executable",
                QUALIFICATION_SUBJECT_DIGEST_FIELD,
            }
            or document.get("schema_id") != QUALIFICATION_SUBJECT_SCHEMA_ID
            or document.get("schema_version") != QUALIFICATION_SUBJECT_SCHEMA_VERSION
            or document.get("authority_status")
            != "NOT_CREATED_QUALIFICATION_PENDING"
            or document.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or document.get("executable") is not False
        ):
            raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_RECEIPT_INVALID")
        _timestamp(document.get("frozen_at"), "V31_FREEZE_SUBJECT_TIME_INVALID")
        subject = document.get("manifest_subject")
        if not isinstance(subject, Mapping):
            raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_RECEIPT_INVALID")
        subject_digest = validate_manifest_experiment_contract_alignment(
            subject, experiment_contract
        )
        if (
            subject.get("run_id") != document.get("run_id")
            or subject_digest
            != document.get("manifest_qualification_subject_digest")
            or supplied != document[QUALIFICATION_SUBJECT_DIGEST_FIELD]
        ):
            raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_RECEIPT_INVALID")
        if tuple(subject.get("implementation_bindings", {})) != V31_PRODUCTION_RUNTIME_PATHS:
            raise V31AuthorityFreezeError("V31_FREEZE_RUNTIME_PATH_SET_INVALID")
    except V31AuthorityFreezeError:
        raise
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_RECEIPT_INVALID") from exc
    return copy.deepcopy(dict(subject))


def build_v31_final_authority_documents(
    *,
    manifest_subject: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
    theory_approval: Mapping[str, Any],
    qualification_receipts: Mapping[str, Mapping[str, Any]],
    qualification_receipt_paths: Mapping[str, str],
    final_manifest_path: str,
    authorization_receipt_path: str,
    active_authority_path: str,
    predecessor_authority_binding: Mapping[str, Any],
    authorization_id: str,
    authority_id: str,
    issued_at: str,
    recorded_at: str,
) -> dict[str, dict[str, Any]]:
    """Build the post-Q0-Q8 manifest, authorization receipt and ACTIVE authority."""

    if set(qualification_receipts) != set(GATE_IDS) or set(
        qualification_receipt_paths
    ) != set(GATE_IDS):
        raise V31AuthorityFreezeError("V31_FREEZE_Q0_Q8_SET_INCOMPLETE")
    if manifest_subject.get("qualification_gates") != {}:
        raise V31AuthorityFreezeError("V31_FREEZE_SUBJECT_ALREADY_FINALIZED")
    try:
        validate_v31_theory_approval(theory_approval)
        verify_minimal_experiment_contract(experiment_contract)
        subject_created = _timestamp(
            manifest_subject.get("created_at"), "V31_FREEZE_MANIFEST_TIME_INVALID"
        )
        gate_times: list[datetime] = []
        for gate_id in GATE_IDS:
            receipt = qualification_receipts[gate_id]
            validate_v31_qualification_receipt(
                receipt,
                expected_gate_id=gate_id,
                experiment_contract=experiment_contract,
                manifest=manifest_subject,
                theory_approval=theory_approval,
            )
            gate_time = _timestamp(
                receipt.get("evaluated_at"), "V31_FREEZE_GATE_TIME_INVALID"
            )
            if gate_time < subject_created:
                raise V31AuthorityFreezeError(
                    "V31_FREEZE_GATE_PRECEDES_SUBJECT"
                )
            gate_times.append(gate_time)
        issued = _timestamp(issued_at, "V31_FREEZE_AUTHORIZATION_TIME_INVALID")
        recorded = _timestamp(recorded_at, "V31_FREEZE_AUTHORITY_TIME_INVALID")
        if issued < max(gate_times) or recorded < issued:
            raise V31AuthorityFreezeError("V31_FREEZE_AUTHORITY_CHRONOLOGY_INVALID")
    except V31AuthorityFreezeError:
        raise
    except (V31AuthorizationError, ValueError) as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_Q0_Q8_VALIDATION_FAILED") from exc

    gates: dict[str, Any] = {}
    for gate_id in GATE_IDS:
        receipt = qualification_receipts[gate_id]
        gates[gate_id] = {
            "status": "PASS",
            "receipt_binding": document_binding(
                path=qualification_receipt_paths[gate_id],
                document=receipt,
                digest_field="qualification_receipt_digest",
            ),
        }
    manifest_base = copy.deepcopy(dict(manifest_subject))
    manifest_base["qualification_gates"] = gates
    manifest = self_digest(manifest_base, "manifest_digest")
    try:
        validate_v31_frozen_experiment_manifest(
            manifest,
            experiment_contract=experiment_contract,
            theory_approval=theory_approval,
        )
        for gate_id in GATE_IDS:
            validate_v31_qualification_receipt(
                qualification_receipts[gate_id],
                expected_gate_id=gate_id,
                experiment_contract=experiment_contract,
                manifest=manifest,
                theory_approval=theory_approval,
            )
    except V31AuthorizationError as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_FINAL_MANIFEST_INVALID") from exc
    manifest_binding = document_binding(
        path=final_manifest_path,
        document=manifest,
        digest_field="manifest_digest",
    )

    approval_binding = manifest["theory_approval_binding"]
    contract_binding = manifest["experiment_contract_binding"]
    authorization = self_digest(
        {
            "schema_id": "theory_paper_v31_experiment_authorization_receipt",
            "schema_version": "1.1.0",
            "authorization_id": _safe_id(
                authorization_id, "V31_FREEZE_AUTHORIZATION_ID_INVALID"
            ),
            "authority_id": _safe_id(authority_id, "V31_FREEZE_AUTHORITY_ID_INVALID"),
            "issued_at": issued_at,
            "theory_approval_binding": copy.deepcopy(approval_binding),
            "theory_physical_sha256": theory_approval["theory_physical_sha256"],
            "operation": "RUN_V31_PROSPECTIVE",
            "run_id": manifest["run_id"],
            "manifest_binding": manifest_binding,
            "experiment_contract_binding": copy.deepcopy(contract_binding),
            "symbol": "BTC-USDT",
            "instrument": copy.deepcopy(manifest["instrument"]),
            "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "total_cycles": 8,
            "authorization_cardinality": "EXACTLY_ONE_FRESH_RUN",
            "legacy_runs_resumable": False,
            "chat_history_is_authority": False,
            **EXECUTION_FALSE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "authorization_receipt_digest",
    )
    try:
        validate_v31_experiment_authorization(
            authorization,
            manifest=manifest,
            experiment_contract=experiment_contract,
            theory_approval=theory_approval,
        )
    except V31AuthorizationError as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_AUTHORIZATION_INVALID") from exc
    authorization_binding = document_binding(
        path=authorization_receipt_path,
        document=authorization,
        digest_field="authorization_receipt_digest",
    )
    predecessor = {
        "path": _text(
            predecessor_authority_binding.get("path"),
            "V31_FREEZE_PREDECESSOR_BINDING_INVALID",
        ),
        "physical_sha256": _digest(
            predecessor_authority_binding.get("physical_sha256"),
            "V31_FREEZE_PREDECESSOR_BINDING_INVALID",
        ),
        "expected_status": "FROZEN_V3_1_QUALIFICATION_PENDING",
    }
    authority = self_digest(
        {
            "schema_id": "theory_paper_v31_current_research_authority",
            "schema_version": "2.1.0",
            "authority_id": authority_id,
            "recorded_at": recorded_at,
            "status": "ACTIVE_FROZEN_RESEARCH",
            "reason": (
                "One frozen, qualified, public-data-only V3.1 run is authorized."
            ),
            "predecessor_authority_binding": predecessor,
            "current_theory": copy.deepcopy(manifest["theory_binding"]),
            "theory_approval_binding": copy.deepcopy(approval_binding),
            "experiment_start_authorized": True,
            "authorized_operation": "RUN_V31_PROSPECTIVE",
            "authorized_run_id": manifest["run_id"],
            "manifest_binding": manifest_binding,
            "authorization_receipt_binding": authorization_binding,
            "experiment_contract_binding": copy.deepcopy(contract_binding),
            "authorization_cardinality": "EXACTLY_ONE_FRESH_RUN",
            "symbol": "BTC-USDT",
            "instrument": copy.deepcopy(manifest["instrument"]),
            "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "total_cycles": 8,
            "legacy_runs_resumable": False,
            "chat_history_is_authority": False,
            **EXECUTION_FALSE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "authority_digest",
    )
    try:
        validate_v31_active_authority(
            authority,
            theory_approval=theory_approval,
            manifest=manifest,
            experiment_contract=experiment_contract,
            authorization_receipt=authorization,
        )
    except V31AuthorizationError as exc:
        raise V31AuthorityFreezeError("V31_FREEZE_ACTIVE_AUTHORITY_INVALID") from exc
    if active_authority_path != "config/theory_paper_v31.current_research_authority.v2.json":
        raise V31AuthorityFreezeError("V31_FREEZE_ACTIVE_AUTHORITY_PATH_INVALID")
    return {
        "manifest": manifest,
        "authorization_receipt": authorization,
        "active_authority": authority,
    }


__all__ = [
    "EXECUTION_FALSE",
    "GATE_IDS",
    "QUALIFICATION_SUBJECT_DIGEST_FIELD",
    "QUALIFICATION_SUBJECT_SCHEMA_ID",
    "V31AuthorityFreezeError",
    "V31_PRODUCTION_RUNTIME_PATHS",
    "build_v31_final_authority_documents",
    "build_v31_qualification_manifest_subject",
    "build_v31_qualification_subject_freeze",
    "canonical_document_physical_sha256",
    "document_binding",
    "verify_v31_qualification_subject_freeze",
]
