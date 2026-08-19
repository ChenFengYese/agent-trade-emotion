"""Pure fail-closed contracts for the sole fresh V3.1 research run.

The chronology is deliberately acyclic:

    theory approval -> frozen experiment contract -> frozen manifest
    -> typed qualification receipts -> experiment authorization
    -> active authority -> run genesis checkpoint

This module grants no runtime capability.  It validates immutable documents
only; contained-path and physical-byte verification belong to Infrastructure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ..contracts.canonical import verify_self_digest
from ..v31_experiment_contracts import EXPERIMENT_SCHEMA_ID
from .v31_external_qualification import (
    EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID,
    V31ExternalQualificationError,
    verify_external_typed_qualification_receipt,
)
from .v31_experiment_qualification import (
    TYPED_QUALIFICATION_GATE_IDS,
    TYPED_QUALIFICATION_SCHEMA_ID,
    V31ExperimentQualificationError,
    validate_manifest_experiment_contract_alignment,
    verify_typed_qualification_receipt,
)


class V31AuthorizationError(ValueError):
    """A V3.1 theory or experiment authority contract is invalid."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_GATE_IDS = tuple(f"Q{index}" for index in range(9))
_EXTERNAL_TYPED_GATE_IDS = ("Q6", "Q7")
_EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)
_LEGAL_ACTION_CLASSES = (
    "OPEN_LONG",
    "OPEN_SHORT",
    "WAIT",
)
_EXECUTION_FALSE_FIELDS = (
    "account_access",
    "paper_trading",
    "live_trading",
    "order_submission",
    "credential_access",
    "funds_access",
)
_DOCUMENT_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_EXACT_INSTRUMENT = {
    "venue": "OKX",
    "instrument_id": "BTC-USDT-SWAP",
    "market_type": "PERPETUAL_SWAP",
    "underlying_symbol": "BTC-USDT",
}
_THEORY_BINDING_FIELDS = frozenset(
    {"path", "version", "review_status", "physical_sha256"}
)
_PREDECESSOR_BINDING_FIELDS = frozenset(
    {"path", "physical_sha256", "expected_status"}
)
_APPROVAL_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "approval_id",
        "approved_at",
        "approval_source",
        "user_statement",
        "theory_path",
        "theory_version",
        "theory_physical_sha256",
        "approval_scope",
        "experiment_authorization_status",
        "excluded_authority",
        "legacy_runs_resumable",
        "external_execution_authority",
        "executable",
        "approval_receipt_digest",
    }
)
_QUALIFICATION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "gate_id",
        "evaluated_at",
        "verdict",
        "evidence_digests",
        "limitations",
        "external_execution_authority",
        "executable",
        "qualification_receipt_digest",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "manifest_id",
        "created_at",
        "run_id",
        "operation",
        "theory_binding",
        "theory_approval_binding",
        "experiment_contract_binding",
        "symbol",
        "instrument",
        "data_scope",
        "source_plan",
        "agent_plan",
        "fresh_run",
        "predecessor_run_id",
        "qualification_gates",
        "experiment_used_capabilities",
        "implemented_and_verified_capabilities",
        "excluded_no_claim_capabilities",
        "portfolio_scope",
        "association_preregistration",
        "evaluation_contract",
        "total_cycles",
        "cadence_seconds",
        "legal_action_classes",
        "stop_rules",
        "implementation_bindings",
        "assembly_bundle_contract",
        "checkpoint_contract",
        "event_order",
        "authorization_cardinality",
        "legacy_runs_resumable",
        "chat_history_is_authority",
        "authority_boundary",
        *_EXECUTION_FALSE_FIELDS,
        "external_execution_authority",
        "executable",
        "manifest_digest",
    }
)
_AUTHORIZATION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "authorization_id",
        "authority_id",
        "issued_at",
        "theory_approval_binding",
        "theory_physical_sha256",
        "operation",
        "run_id",
        "manifest_binding",
        "experiment_contract_binding",
        "symbol",
        "instrument",
        "data_scope",
        "total_cycles",
        "authorization_cardinality",
        "legacy_runs_resumable",
        "chat_history_is_authority",
        *_EXECUTION_FALSE_FIELDS,
        "external_execution_authority",
        "executable",
        "authorization_receipt_digest",
    }
)
_ACTIVE_AUTHORITY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "authority_id",
        "recorded_at",
        "status",
        "reason",
        "predecessor_authority_binding",
        "current_theory",
        "theory_approval_binding",
        "experiment_start_authorized",
        "authorized_operation",
        "authorized_run_id",
        "manifest_binding",
        "authorization_receipt_binding",
        "experiment_contract_binding",
        "authorization_cardinality",
        "symbol",
        "instrument",
        "data_scope",
        "total_cycles",
        "legacy_runs_resumable",
        "chat_history_is_authority",
        *_EXECUTION_FALSE_FIELDS,
        "external_execution_authority",
        "executable",
        "authority_digest",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise V31AuthorizationError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31AuthorizationError(code)
    return value


def _timestamp(value: Any, code: str) -> str:
    value = _text(value, code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31AuthorizationError(code) from exc
    if parsed.tzinfo is None:
        raise V31AuthorizationError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31AuthorizationError(code)
    return value


def _relative_path(value: Any, code: str) -> str:
    value = _text(value, code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.as_posix() != value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31AuthorizationError(code)
    return value


def _strings(
    values: Any,
    code: str,
    *,
    allow_empty: bool = False,
    require_sorted: bool = True,
) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise V31AuthorizationError(code)
    result = tuple(_text(value, code) for value in values)
    if (
        (not allow_empty and not result)
        or len(result) != len(set(result))
        or (require_sorted and list(result) != sorted(result))
    ):
        raise V31AuthorizationError(code)
    return result


def _verify_self(document: Any, field: str, code: str) -> str:
    if not isinstance(document, Mapping):
        raise V31AuthorizationError(code)
    try:
        return verify_self_digest(document, field)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31AuthorizationError(code) from exc


def validate_v31_document_binding(
    binding: Any,
    *,
    code: str = "V31_DOCUMENT_BINDING_INVALID",
    expected_schema_id: str | None = None,
    expected_digest_field: str | None = None,
) -> None:
    if not isinstance(binding, Mapping) or set(binding) != _DOCUMENT_BINDING_FIELDS:
        raise V31AuthorizationError(code)
    _relative_path(binding.get("path"), code)
    schema_id = _text(binding.get("schema_id"), code)
    digest_field = _text(binding.get("digest_field"), code)
    _digest(binding.get("semantic_digest"), code)
    _digest(binding.get("physical_sha256"), code)
    if (
        (expected_schema_id is not None and schema_id != expected_schema_id)
        or (
            expected_digest_field is not None
            and digest_field != expected_digest_field
        )
    ):
        raise V31AuthorizationError(code)


def _validate_exact_instrument(value: Any, *, code: str) -> None:
    if value != _EXACT_INSTRUMENT:
        raise V31AuthorizationError(code)


def _validate_theory_binding(binding: Any, *, code: str) -> None:
    if not isinstance(binding, Mapping) or set(binding) != _THEORY_BINDING_FIELDS:
        raise V31AuthorizationError(code)
    _relative_path(binding.get("path"), code)
    if (
        binding.get("version") != "3.1"
        or binding.get("review_status") != "FROZEN_APPROVED"
    ):
        raise V31AuthorizationError(code)
    _digest(binding.get("physical_sha256"), code)


def _validate_execution_boundary(document: Mapping[str, Any], *, code: str) -> None:
    if (
        any(document.get(field) is not False for field in _EXECUTION_FALSE_FIELDS)
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("chat_history_is_authority") is not False
    ):
        raise V31AuthorizationError(code)


def validate_v31_theory_approval(receipt: Mapping[str, Any]) -> str:
    """Validate the already-recorded explicit V3.1 theory approval."""

    digest = _verify_self(
        receipt, "approval_receipt_digest", "V31_THEORY_APPROVAL_DIGEST_INVALID"
    )
    if (
        not isinstance(receipt, Mapping)
        or set(receipt) != _APPROVAL_FIELDS
        or receipt.get("schema_id") != "theory_paper_v31_user_approval_receipt"
        or receipt.get("schema_version") != "1.0.0"
        or receipt.get("approval_source") != "CURRENT_CODEX_TASK_USER_MESSAGE"
        or receipt.get("user_statement") != "我批准，并授权实验"
        or receipt.get("theory_version") != "3.1"
        or receipt.get("approval_scope")
        != [
            "FROZEN_V3_1_THEORY_AUTHORITY",
            "SOLE_FRESH_BTC_USDT_PUBLIC_DATA_NON_EXECUTABLE_PROSPECTIVE_EXPERIMENT_AFTER_Q0_Q8",
        ]
        or receipt.get("experiment_authorization_status")
        != "CONDITIONAL_ON_Q0_Q8_AND_EXACT_RUN_MANIFEST_RECEIPT_BINDING"
        or receipt.get("excluded_authority")
        != [
            "RESUME_LEGACY_RUN",
            "ACCOUNT_ACCESS",
            "PAPER_TRADING",
            "LIVE_TRADING",
            "ORDER_SUBMISSION",
            "CREDENTIAL_ACCESS",
            "FUNDS_ACCESS",
        ]
        or receipt.get("legacy_runs_resumable") is not False
        or receipt.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or receipt.get("executable") is not False
    ):
        raise V31AuthorizationError("V31_THEORY_APPROVAL_INVALID")
    _text(receipt.get("approval_id"), "V31_THEORY_APPROVAL_INVALID")
    _timestamp(receipt.get("approved_at"), "V31_THEORY_APPROVAL_TIME_INVALID")
    _relative_path(receipt.get("theory_path"), "V31_THEORY_APPROVAL_INVALID")
    _digest(
        receipt.get("theory_physical_sha256"), "V31_THEORY_APPROVAL_INVALID"
    )
    return digest


def validate_v31_qualification_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_gate_id: str,
    experiment_contract: Mapping[str, Any] | None = None,
    manifest: Mapping[str, Any] | None = None,
    theory_approval: Mapping[str, Any] | None = None,
) -> str:
    """Validate one standardized PASS receipt for Q0 through Q8."""

    if expected_gate_id in TYPED_QUALIFICATION_GATE_IDS:
        if experiment_contract is None or manifest is None:
            raise V31AuthorizationError(
                "V31_TYPED_QUALIFICATION_CONTEXT_REQUIRED"
            )
        try:
            return verify_typed_qualification_receipt(
                receipt,
                expected_gate_id=expected_gate_id,
                experiment_contract=experiment_contract,
                manifest=manifest,
                theory_approval=theory_approval,
            )
        except V31ExperimentQualificationError as exc:
            raise V31AuthorizationError(
                "V31_TYPED_QUALIFICATION_RECEIPT_INVALID"
            ) from exc

    if expected_gate_id in _EXTERNAL_TYPED_GATE_IDS:
        if experiment_contract is None or manifest is None:
            raise V31AuthorizationError(
                "V31_EXTERNAL_TYPED_QUALIFICATION_CONTEXT_REQUIRED"
            )
        try:
            return verify_external_typed_qualification_receipt(
                receipt,
                expected_gate_id=expected_gate_id,
                experiment_contract=experiment_contract,
                manifest=manifest,
            )
        except V31ExternalQualificationError as exc:
            raise V31AuthorizationError(
                "V31_EXTERNAL_TYPED_QUALIFICATION_RECEIPT_INVALID"
            ) from exc

    digest = _verify_self(
        receipt,
        "qualification_receipt_digest",
        "V31_QUALIFICATION_RECEIPT_DIGEST_INVALID",
    )
    if (
        expected_gate_id not in _GATE_IDS
        or not isinstance(receipt, Mapping)
        or set(receipt) != _QUALIFICATION_RECEIPT_FIELDS
        or receipt.get("schema_id")
        != "theory_paper_v31_qualification_gate_receipt"
        or receipt.get("schema_version") != "1.0.0"
        or receipt.get("gate_id") != expected_gate_id
        or receipt.get("verdict") != "PASS"
        or receipt.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or receipt.get("executable") is not False
    ):
        raise V31AuthorizationError("V31_QUALIFICATION_RECEIPT_INVALID")
    _timestamp(
        receipt.get("evaluated_at"), "V31_QUALIFICATION_RECEIPT_TIME_INVALID"
    )
    evidence = _strings(
        receipt.get("evidence_digests"), "V31_QUALIFICATION_EVIDENCE_INVALID"
    )
    for value in evidence:
        _digest(value, "V31_QUALIFICATION_EVIDENCE_INVALID")
    _strings(
        receipt.get("limitations"),
        "V31_QUALIFICATION_LIMITATIONS_INVALID",
        allow_empty=True,
    )
    return digest


def _validate_source_plan(value: Any) -> None:
    fields = {
        "allowed_source_scope",
        "raw_capture_required",
        "pit_available_at_required",
        "missing_is_unknown",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("allowed_source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or any(
            value.get(field) is not True
            for field in (
                "raw_capture_required",
                "pit_available_at_required",
                "missing_is_unknown",
            )
        )
    ):
        raise V31AuthorizationError("V31_MANIFEST_SOURCE_PLAN_INVALID")


def _validate_agent_plan(value: Any) -> None:
    fields = {
        "agent_id",
        "proposal_then_postseal_selection",
        "durable_before_adapter_return",
        "reinvocation_after_accept",
        "sub_agents_allowed",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("agent_id") != "CURRENT_CODEX_TASK"
        or value.get("proposal_then_postseal_selection") is not True
        or value.get("durable_before_adapter_return") is not True
        or value.get("reinvocation_after_accept") is not False
        or value.get("sub_agents_allowed") is not False
    ):
        raise V31AuthorizationError("V31_MANIFEST_AGENT_PLAN_INVALID")


def _validate_association_plan(value: Any, *, expected: Any) -> None:
    if not isinstance(value, Mapping) or value != expected:
        raise V31AuthorizationError("V31_MANIFEST_ASSOCIATION_PLAN_INVALID")


def _validate_evaluation_contract(value: Any, *, expected: Any) -> None:
    if not isinstance(value, Mapping) or value != expected:
        raise V31AuthorizationError("V31_MANIFEST_EVALUATION_INVALID")


def _validate_contract_versions(manifest: Mapping[str, Any]) -> None:
    assembly = manifest.get("assembly_bundle_contract")
    checkpoint = manifest.get("checkpoint_contract")
    if (
        not isinstance(assembly, Mapping)
        or set(assembly)
        != {"schema_id", "schema_version", "content_addressed", "chat_history_is_authority"}
        or assembly.get("schema_id")
        != "theory_paper_v2_v31_durable_assembly_bundle"
        or assembly.get("schema_version") != "1.0.0"
        or assembly.get("content_addressed") is not True
        or assembly.get("chat_history_is_authority") is not False
        or not isinstance(checkpoint, Mapping)
        or set(checkpoint)
        != {"schema_id", "schema_version", "genesis_bindings_required"}
        or checkpoint.get("schema_id")
        != "theory_paper_v31_research_checkpoint"
        or checkpoint.get("schema_version") != "1.2.0"
        or checkpoint.get("genesis_bindings_required") is not True
    ):
        raise V31AuthorizationError("V31_MANIFEST_DURABLE_CONTRACT_INVALID")


def validate_v31_frozen_experiment_manifest(
    manifest: Mapping[str, Any],
    *,
    experiment_contract: Mapping[str, Any],
    theory_approval: Mapping[str, Any] | None = None,
) -> str:
    """Validate the one pre-authorization, self-contained experiment manifest."""

    digest = _verify_self(manifest, "manifest_digest", "V31_MANIFEST_DIGEST_INVALID")
    if (
        not isinstance(manifest, Mapping)
        or set(manifest) != _MANIFEST_FIELDS
        or manifest.get("schema_id")
        != "theory_paper_v31_frozen_experiment_manifest"
        or manifest.get("schema_version") != "1.1.0"
        or manifest.get("operation") != "RUN_V31_PROSPECTIVE"
        or manifest.get("symbol") != "BTC-USDT"
        or manifest.get("data_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or manifest.get("fresh_run") is not True
        or manifest.get("predecessor_run_id") is not None
        or manifest.get("authorization_cardinality")
        != "EXACTLY_ONE_FRESH_RUN"
        or manifest.get("legacy_runs_resumable") is not False
        or manifest.get("legal_action_classes") != list(_LEGAL_ACTION_CLASSES)
        or manifest.get("event_order") != list(_EVENT_ORDER)
    ):
        raise V31AuthorizationError("V31_MANIFEST_INVALID")
    _text(manifest.get("manifest_id"), "V31_MANIFEST_INVALID")
    _timestamp(manifest.get("created_at"), "V31_MANIFEST_TIME_INVALID")
    _text(manifest.get("run_id"), "V31_MANIFEST_RUN_ID_INVALID")
    _validate_theory_binding(
        manifest.get("theory_binding"), code="V31_MANIFEST_THEORY_BINDING_INVALID"
    )
    validate_v31_document_binding(
        manifest.get("theory_approval_binding"),
        code="V31_MANIFEST_APPROVAL_BINDING_INVALID",
        expected_schema_id="theory_paper_v31_user_approval_receipt",
        expected_digest_field="approval_receipt_digest",
    )
    validate_v31_document_binding(
        manifest.get("experiment_contract_binding"),
        code="V31_MANIFEST_EXPERIMENT_CONTRACT_BINDING_INVALID",
        expected_schema_id=EXPERIMENT_SCHEMA_ID,
        expected_digest_field="experiment_contract_digest",
    )
    _validate_exact_instrument(
        manifest.get("instrument"), code="V31_MANIFEST_INSTRUMENT_INVALID"
    )
    _validate_source_plan(manifest.get("source_plan"))
    _validate_agent_plan(manifest.get("agent_plan"))
    gates = manifest.get("qualification_gates")
    if not isinstance(gates, Mapping) or tuple(gates) != _GATE_IDS:
        raise V31AuthorizationError("V31_MANIFEST_QUALIFICATION_GATES_INVALID")
    for gate_id in _GATE_IDS:
        row = gates[gate_id]
        if (
            not isinstance(row, Mapping)
            or set(row) != {"status", "receipt_binding"}
            or row.get("status") != "PASS"
        ):
            raise V31AuthorizationError("V31_MANIFEST_QUALIFICATION_GATES_INVALID")
        if gate_id in TYPED_QUALIFICATION_GATE_IDS:
            expected_receipt_schema = TYPED_QUALIFICATION_SCHEMA_ID
        elif gate_id in _EXTERNAL_TYPED_GATE_IDS:
            expected_receipt_schema = EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID
        else:  # pragma: no cover - all Q0-Q8 gates are strict typed gates
            expected_receipt_schema = "theory_paper_v31_qualification_gate_receipt"
        validate_v31_document_binding(
            row.get("receipt_binding"),
            code="V31_MANIFEST_QUALIFICATION_GATES_INVALID",
            expected_schema_id=expected_receipt_schema,
            expected_digest_field="qualification_receipt_digest",
        )
    used = set(
        _strings(
            manifest.get("experiment_used_capabilities"),
            "V31_MANIFEST_CAPABILITY_SCOPE_INVALID",
        )
    )
    implemented = set(
        _strings(
            manifest.get("implemented_and_verified_capabilities"),
            "V31_MANIFEST_CAPABILITY_SCOPE_INVALID",
        )
    )
    excluded = set(
        _strings(
            manifest.get("excluded_no_claim_capabilities"),
            "V31_MANIFEST_CAPABILITY_SCOPE_INVALID",
            allow_empty=True,
        )
    )
    if not used.issubset(implemented) or implemented & excluded or used & excluded:
        raise V31AuthorizationError("V31_MANIFEST_CAPABILITY_SCOPE_INVALID")
    _validate_association_plan(
        manifest.get("association_preregistration"),
        expected=experiment_contract.get("association_scope"),
    )
    _validate_evaluation_contract(
        manifest.get("evaluation_contract"),
        expected=experiment_contract.get("evaluation"),
    )
    if manifest.get("total_cycles") != 8 or manifest.get("cadence_seconds") != 3600:
        raise V31AuthorizationError("V31_MANIFEST_SCHEDULE_INVALID")
    _strings(manifest.get("stop_rules"), "V31_MANIFEST_STOP_RULES_INVALID")
    implementations = manifest.get("implementation_bindings")
    if not isinstance(implementations, Mapping) or not implementations:
        raise V31AuthorizationError("V31_MANIFEST_IMPLEMENTATION_BINDINGS_INVALID")
    if list(implementations) != sorted(implementations):
        raise V31AuthorizationError("V31_MANIFEST_IMPLEMENTATION_BINDINGS_INVALID")
    for path, physical_sha256 in implementations.items():
        _relative_path(path, "V31_MANIFEST_IMPLEMENTATION_BINDINGS_INVALID")
        _digest(physical_sha256, "V31_MANIFEST_IMPLEMENTATION_BINDINGS_INVALID")
    _validate_contract_versions(manifest)
    _validate_execution_boundary(manifest, code="V31_MANIFEST_EXECUTION_BOUNDARY_INVALID")
    try:
        validate_manifest_experiment_contract_alignment(
            manifest, experiment_contract
        )
    except V31ExperimentQualificationError as exc:
        raise V31AuthorizationError(
            "V31_MANIFEST_EXPERIMENT_CONTRACT_MISMATCH"
        ) from exc
    if theory_approval is not None:
        approval_digest = validate_v31_theory_approval(theory_approval)
        if (
            manifest["theory_binding"]["path"] != theory_approval["theory_path"]
            or manifest["theory_binding"]["physical_sha256"]
            != theory_approval["theory_physical_sha256"]
            or manifest["theory_approval_binding"]["semantic_digest"]
            != approval_digest
        ):
            raise V31AuthorizationError("V31_MANIFEST_APPROVAL_BINDING_INVALID")
    return digest


def validate_v31_experiment_authorization(
    receipt: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
    theory_approval: Mapping[str, Any],
) -> str:
    """Validate the post-manifest authorization receipt without a digest cycle."""

    digest = _verify_self(
        receipt,
        "authorization_receipt_digest",
        "V31_EXPERIMENT_AUTHORIZATION_DIGEST_INVALID",
    )
    manifest_digest = validate_v31_frozen_experiment_manifest(
        manifest,
        experiment_contract=experiment_contract,
        theory_approval=theory_approval,
    )
    approval_digest = validate_v31_theory_approval(theory_approval)
    if (
        not isinstance(receipt, Mapping)
        or set(receipt) != _AUTHORIZATION_RECEIPT_FIELDS
        or receipt.get("schema_id")
        != "theory_paper_v31_experiment_authorization_receipt"
        or receipt.get("schema_version") != "1.1.0"
        or receipt.get("operation") != "RUN_V31_PROSPECTIVE"
        or receipt.get("run_id") != manifest.get("run_id")
        or receipt.get("symbol") != manifest.get("symbol")
        or receipt.get("instrument") != manifest.get("instrument")
        or receipt.get("data_scope") != manifest.get("data_scope")
        or receipt.get("total_cycles") != manifest.get("total_cycles")
        or receipt.get("theory_physical_sha256")
        != theory_approval.get("theory_physical_sha256")
        or receipt.get("authorization_cardinality")
        != "EXACTLY_ONE_FRESH_RUN"
        or receipt.get("legacy_runs_resumable") is not False
    ):
        raise V31AuthorizationError("V31_EXPERIMENT_AUTHORIZATION_INVALID")
    _text(receipt.get("authorization_id"), "V31_EXPERIMENT_AUTHORIZATION_INVALID")
    _text(receipt.get("authority_id"), "V31_EXPERIMENT_AUTHORIZATION_INVALID")
    _timestamp(receipt.get("issued_at"), "V31_EXPERIMENT_AUTHORIZATION_TIME_INVALID")
    validate_v31_document_binding(
        receipt.get("theory_approval_binding"),
        code="V31_EXPERIMENT_AUTHORIZATION_APPROVAL_BINDING_INVALID",
        expected_schema_id="theory_paper_v31_user_approval_receipt",
        expected_digest_field="approval_receipt_digest",
    )
    validate_v31_document_binding(
        receipt.get("manifest_binding"),
        code="V31_EXPERIMENT_AUTHORIZATION_MANIFEST_BINDING_INVALID",
        expected_schema_id="theory_paper_v31_frozen_experiment_manifest",
        expected_digest_field="manifest_digest",
    )
    validate_v31_document_binding(
        receipt.get("experiment_contract_binding"),
        code="V31_EXPERIMENT_AUTHORIZATION_CONTRACT_BINDING_INVALID",
        expected_schema_id=EXPERIMENT_SCHEMA_ID,
        expected_digest_field="experiment_contract_digest",
    )
    _validate_exact_instrument(
        receipt.get("instrument"),
        code="V31_EXPERIMENT_AUTHORIZATION_INSTRUMENT_INVALID",
    )
    if (
        receipt["theory_approval_binding"]
        != manifest["theory_approval_binding"]
        or receipt["theory_approval_binding"]["semantic_digest"]
        != approval_digest
        or receipt["manifest_binding"]["semantic_digest"] != manifest_digest
        or receipt["experiment_contract_binding"]
        != manifest["experiment_contract_binding"]
    ):
        raise V31AuthorizationError("V31_EXPERIMENT_AUTHORIZATION_BINDING_MISMATCH")
    _validate_execution_boundary(
        receipt, code="V31_EXPERIMENT_AUTHORIZATION_EXECUTION_BOUNDARY_INVALID"
    )
    return digest


def validate_v31_active_authority(
    authority: Mapping[str, Any],
    *,
    theory_approval: Mapping[str, Any],
    manifest: Mapping[str, Any],
    experiment_contract: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
) -> str:
    """Validate the sole ACTIVE authority after all earlier objects are frozen."""

    digest = _verify_self(authority, "authority_digest", "V31_ACTIVE_AUTHORITY_DIGEST_INVALID")
    manifest_digest = validate_v31_frozen_experiment_manifest(
        manifest,
        experiment_contract=experiment_contract,
        theory_approval=theory_approval,
    )
    approval_digest = validate_v31_theory_approval(theory_approval)
    authorization_digest = validate_v31_experiment_authorization(
        authorization_receipt,
        manifest=manifest,
        experiment_contract=experiment_contract,
        theory_approval=theory_approval,
    )
    if (
        not isinstance(authority, Mapping)
        or set(authority) != _ACTIVE_AUTHORITY_FIELDS
        or authority.get("schema_id")
        != "theory_paper_v31_current_research_authority"
        or authority.get("schema_version") != "2.1.0"
        or authority.get("authority_id")
        != authorization_receipt.get("authority_id")
        or authority.get("status") != "ACTIVE_FROZEN_RESEARCH"
        or authority.get("experiment_start_authorized") is not True
        or authority.get("authorized_operation") != "RUN_V31_PROSPECTIVE"
        or authority.get("authorized_run_id") != manifest.get("run_id")
        or authority.get("authorization_cardinality")
        != "EXACTLY_ONE_FRESH_RUN"
        or authority.get("symbol") != manifest.get("symbol")
        or authority.get("instrument") != manifest.get("instrument")
        or authority.get("data_scope") != manifest.get("data_scope")
        or authority.get("total_cycles") != manifest.get("total_cycles")
        or authority.get("legacy_runs_resumable") is not False
    ):
        raise V31AuthorizationError("V31_ACTIVE_AUTHORITY_INVALID")
    _text(authority.get("reason"), "V31_ACTIVE_AUTHORITY_INVALID")
    _timestamp(authority.get("recorded_at"), "V31_ACTIVE_AUTHORITY_TIME_INVALID")
    predecessor = authority.get("predecessor_authority_binding")
    if (
        not isinstance(predecessor, Mapping)
        or set(predecessor) != _PREDECESSOR_BINDING_FIELDS
        or predecessor.get("expected_status")
        != "FROZEN_V3_1_QUALIFICATION_PENDING"
    ):
        raise V31AuthorizationError("V31_ACTIVE_AUTHORITY_PREDECESSOR_INVALID")
    _relative_path(
        predecessor.get("path"), "V31_ACTIVE_AUTHORITY_PREDECESSOR_INVALID"
    )
    _digest(
        predecessor.get("physical_sha256"),
        "V31_ACTIVE_AUTHORITY_PREDECESSOR_INVALID",
    )
    _validate_theory_binding(
        authority.get("current_theory"),
        code="V31_ACTIVE_AUTHORITY_THEORY_BINDING_INVALID",
    )
    for field, schema_id, digest_field, code in (
        (
            "theory_approval_binding",
            "theory_paper_v31_user_approval_receipt",
            "approval_receipt_digest",
            "V31_ACTIVE_AUTHORITY_APPROVAL_BINDING_INVALID",
        ),
        (
            "manifest_binding",
            "theory_paper_v31_frozen_experiment_manifest",
            "manifest_digest",
            "V31_ACTIVE_AUTHORITY_MANIFEST_BINDING_INVALID",
        ),
        (
            "authorization_receipt_binding",
            "theory_paper_v31_experiment_authorization_receipt",
            "authorization_receipt_digest",
            "V31_ACTIVE_AUTHORITY_AUTHORIZATION_BINDING_INVALID",
        ),
        (
            "experiment_contract_binding",
            EXPERIMENT_SCHEMA_ID,
            "experiment_contract_digest",
            "V31_ACTIVE_AUTHORITY_CONTRACT_BINDING_INVALID",
        ),
    ):
        validate_v31_document_binding(
            authority.get(field),
            code=code,
            expected_schema_id=schema_id,
            expected_digest_field=digest_field,
        )
    if (
        authority["current_theory"] != manifest["theory_binding"]
        or authority["theory_approval_binding"]
        != manifest["theory_approval_binding"]
        or authority["theory_approval_binding"]["semantic_digest"]
        != approval_digest
        or authority["manifest_binding"]
        != authorization_receipt["manifest_binding"]
        or authority["manifest_binding"]["semantic_digest"] != manifest_digest
        or authority["authorization_receipt_binding"]["semantic_digest"]
        != authorization_digest
        or authority["experiment_contract_binding"]
        != manifest["experiment_contract_binding"]
        or authorization_receipt["experiment_contract_binding"]
        != manifest["experiment_contract_binding"]
        or authority["authorized_operation"]
        != authorization_receipt["operation"]
        or authority["authorized_run_id"] != authorization_receipt["run_id"]
    ):
        raise V31AuthorizationError("V31_ACTIVE_AUTHORITY_BINDING_MISMATCH")
    _validate_execution_boundary(
        authority, code="V31_ACTIVE_AUTHORITY_EXECUTION_BOUNDARY_INVALID"
    )
    return digest


__all__ = [
    "V31AuthorizationError",
    "validate_v31_active_authority",
    "validate_v31_document_binding",
    "validate_v31_experiment_authorization",
    "validate_v31_frozen_experiment_manifest",
    "validate_v31_qualification_receipt",
    "validate_v31_theory_approval",
]
