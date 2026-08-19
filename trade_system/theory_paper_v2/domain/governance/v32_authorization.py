"""Pure typed contracts for a future V3.2 authority chain.

These builders grant no authority and perform no file, clock, network, Agent,
account, or order operation.  Physical containment and runtime-closure replay
belong to the infrastructure full loader.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .v311_fresh_process_trace_v2 import (
    FRESH_PROCESS_TRACE_DIGEST_FIELD,
    FRESH_PROCESS_TRACE_SCHEMA_ID,
)

from ..contracts.canonical import self_digest, verify_self_digest
from .v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
    SCHEMA_ID as EXPERIMENT_CONTRACT_SCHEMA_ID,
    SUPPORT_BINDING_KEYS,
    THEORY_VERSION,
    TOTAL_ANALYSIS_CYCLES,
    TOTAL_OUTCOME_SCHEDULES,
)


class V32AuthorizationError(ValueError):
    """A V3.2 authorization document failed an exact invariant."""


SCHEMA_VERSION = "1.0.0"
THEORY_APPROVAL_SCHEMA_ID = "theory_paper_v32_theory_approval_receipt_v1"
THEORY_APPROVAL_DIGEST_FIELD = "theory_approval_digest"
THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID = (
    "theory_paper_v32_complete_theory_semantic_document_v1"
)
THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD = "theory_semantic_document_digest"
RUNTIME_MANIFEST_SCHEMA_ID = "theory_paper_v32_runtime_manifest_v1"
# The schema id is the stable manifest family identifier already embedded in
# downstream bindings.  The exact shape is selected by schema_version so the
# sealed 1.0.0 trees remain replayable without widening any downstream v1
# binding contract.
RUNTIME_MANIFEST_V2_SCHEMA_ID = RUNTIME_MANIFEST_SCHEMA_ID
RUNTIME_MANIFEST_V2_SCHEMA_VERSION = "2.0.0"
RUNTIME_MANIFEST_DIGEST_FIELD = "runtime_manifest_digest"
PHASE_A_SCHEMA_ID = "theory_paper_v32_phase_a_qualification_receipt_v1"
PHASE_A_DIGEST_FIELD = "phase_a_qualification_digest"
AUTHORIZATION_RECEIPT_SCHEMA_ID = "theory_paper_v32_authorization_receipt_v1"
AUTHORIZATION_RECEIPT_DIGEST_FIELD = "authorization_receipt_digest"
AUTHORITY_SCHEMA_ID = "theory_paper_v32_current_research_authority_v1"
AUTHORITY_DIGEST_FIELD = "authority_digest"
QUALIFICATION_RECEIPT_SCHEMA_ID = (
    "theory_paper_v32_fresh_capability_qualification_receipt_v1"
)
QUALIFICATION_RECEIPT_DIGEST_FIELD = "qualification_receipt_digest"
QUALIFICATION_RETIREMENT_SCHEMA_ID = (
    "theory_paper_v32_qualification_retirement_receipt_v1"
)
QUALIFICATION_RETIREMENT_DIGEST_FIELD = "qualification_retirement_digest"
GATE_EVIDENCE_SCHEMA_ID = "theory_paper_v32_qualification_gate_evidence_v1"
GATE_EVIDENCE_DIGEST_FIELD = "qualification_gate_evidence_digest"

QUALIFICATION_PROFILE = "QUALIFICATION"
TARGET_PROFILE = "TARGET"
QUALIFICATION_PHASE_PROFILE = "QUALIFICATION_PHASE_A"
TARGET_PHASE_PROFILE = "TARGET_PHASE_A"
REQUIRED_APPROVAL_STATEMENT = (
    "我批准，并授权 V3.2 唯一 BTC-USDT-SWAP 公开数据、local、"
    "non-executable 前瞻实验"
)
Q0_Q8_GATE_IDS = tuple(f"Q{index}" for index in range(9))
CAPABILITY_KEYS = ("CURRENT_CODEX", "OUTCOME_MONITOR", "PUBLIC_SOURCE")
CAPABILITY_GATE_MAP = {
    "CURRENT_CODEX": "Q3",
    "OUTCOME_MONITOR": "Q6",
    "PUBLIC_SOURCE": "Q2",
}
# A pre-authority phase can prove only that the required path is ready to be
# exercised.  It cannot be used as evidence that the path was actually
# exercised.  The latter is represented by one of these three post-authority
# typed receipts and must be replayed by the owning Infrastructure verifier.
ACTUAL_CAPABILITY_RECEIPT_SPECS = {
    "CURRENT_CODEX": (
        "theory_paper_v32_current_codex_actual_capability_receipt_v1",
        "current_codex_actual_capability_receipt_digest",
    ),
    "OUTCOME_MONITOR": (
        "theory_paper_v32_outcome_monitor_actual_capability_receipt_v1",
        "outcome_monitor_actual_capability_receipt_digest",
    ),
    "PUBLIC_SOURCE": (
        "theory_paper_v32_public_source_actual_capability_receipt_v1",
        "public_source_actual_capability_receipt_digest",
    ),
}
GATE_EVIDENCE_KINDS = {
    "Q0": "LEGACY_ACTIVE_AND_FAILED_RUN_REPLAY",
    "Q1": "RUNTIME_CLOSURE_PHYSICAL_REPLAY",
    "Q2": "PUBLIC_SOURCE_RAW_FIRST_DURABLE_REPLAY",
    "Q3": "CURRENT_CODEX_DURABLE_DELIVERY_REPLAY",
    "Q4": "SEMANTIC_COMPILER_AND_COMPLETE_ACTION_REPLAY",
    "Q5": "ACCEPTANCE_STORE_AND_RECOVERY_REPLAY",
    "Q6": "FIXED_OUTCOME_MONITOR_REPLAY",
    "Q7": "APPLICATION_PROJECTION_AND_TYPED_BUNDLE_REPLAY",
    "Q8": "PUBLIC_ONLY_NON_EXECUTION_BOUNDARY_REPLAY",
}
QUALIFICATION_PREFLIGHT_EVIDENCE_KINDS = {
    "Q2": "PUBLIC_SOURCE_RAW_FIRST_DURABLE_PREFLIGHT_READINESS",
    "Q3": "CURRENT_CODEX_DURABLE_DELIVERY_PREFLIGHT_READINESS",
    "Q6": "FIXED_OUTCOME_MONITOR_PREFLIGHT_READINESS",
}

# Contract support digests are usable only when the runtime manifest also
# identifies one exact typed physical document for every digest.
SUPPORT_DOCUMENT_BINDING_SPECS = {
    "association_preregistration_digest": (
        "theory_paper_v2_v32_association_preregistration_v1",
        "association_preregistration_digest",
    ),
    "authorized_revision_support_bundle_digest": (
        "theory_paper_v32_authorized_revision_support_bundle_v1",
        "authorized_revision_support_bundle_digest",
    ),
    "clock_policy_digest": (
        "theory_paper_v32_clock_and_tick_policy_v1",
        "clock_policy_digest",
    ),
    "evaluation_contract_digest": (
        "theory_paper_v2_v32_evaluation_contract_v1",
        "evaluation_contract_digest",
    ),
    "outcome_adapter_contract_digest": (
        "theory_paper_v32_public_outcome_adapter_contract_v1",
        "outcome_adapter_contract_digest",
    ),
    "recovery_supervision_policy_digest": (
        "theory_paper_v32_recovery_supervision_policy_v1",
        "recovery_supervision_policy_digest",
    ),
    "twelve_axis_source_registry_digest": (
        "theory_paper_v2_v31_native_sentiment_source_registry",
        "registry_digest",
    ),
    "workspace_freeze_receipt_digest": (
        "theory_paper_v32_workspace_freeze_receipt_v1",
        "workspace_freeze_receipt_digest",
    ),
}
if tuple(SUPPORT_DOCUMENT_BINDING_SPECS) != SUPPORT_BINDING_KEYS:
    raise RuntimeError("V32_SUPPORT_DOCUMENT_BINDING_SPECS_INVALID")

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_THEORY_BINDING_FIELDS = frozenset(
    {"relative_ref", "theory_version", "physical_sha256", "semantic_digest"}
)
_BOUNDARY_FIELDS = frozenset(
    {
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "account_data_accessed",
        "paper_trading",
        "live_trading",
        "order_submission",
        "order_data_accessed",
        "credential_access",
        "funds_access",
        "portfolio_mutation",
    }
)
_THEORY_APPROVAL_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "approval_id",
        "approved_at",
        "approval_source",
        "user_statement",
        "theory_binding",
        "approval_scope",
        "target_experiment_authorization_status",
        "legacy_runs_resumable",
        *_BOUNDARY_FIELDS,
        THEORY_APPROVAL_DIGEST_FIELD,
    }
)
_RUNTIME_MANIFEST_V1_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "manifest_id",
        "created_at",
        "runtime_frozen_at",
        "target_run_id",
        "qualification_run_id",
        "theory_approval_binding",
        "experiment_contract_binding",
        "theory_semantic_document_binding",
        "support_document_bindings",
        "production_root_paths",
        "fresh_trace_paths",
        "implementation_bindings",
        "runtime_path_count",
        "runtime_closure_policy",
        "instrument",
        "pilot_protocol",
        *_BOUNDARY_FIELDS,
        RUNTIME_MANIFEST_DIGEST_FIELD,
    }
)
_RUNTIME_MANIFEST_V2_FIELDS = _RUNTIME_MANIFEST_V1_FIELDS | {
    "fresh_process_trace_binding"
}
_PHASE_A_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "phase_id",
        "profile",
        "run_id",
        "target_run_id",
        "evaluated_at",
        "theory_approval_digest",
        "experiment_contract_digest",
        "runtime_manifest_digest",
        "q0_q8_evidence_bindings",
        "predecessor_retirement_digest",
        "verdict",
        *_BOUNDARY_FIELDS,
        PHASE_A_DIGEST_FIELD,
    }
)
_AUTHORIZATION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "authorization_id",
        "profile",
        "issued_at",
        "run_id",
        "target_run_id",
        "theory_approval_binding",
        "experiment_contract_binding",
        "runtime_manifest_binding",
        "phase_a_receipt_binding",
        "qualification_retirement_binding",
        "authorization_cardinality",
        "legacy_runs_resumable",
        *_BOUNDARY_FIELDS,
        AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    }
)
_AUTHORITY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "authority_id",
        "profile",
        "recorded_at",
        "status",
        "run_id",
        "target_run_id",
        "predecessor_authority_binding",
        "theory_approval_binding",
        "experiment_contract_binding",
        "runtime_manifest_binding",
        "phase_a_receipt_binding",
        "authorization_receipt_binding",
        "qualification_retirement_binding",
        "authorized_operation",
        "run_start_authorized",
        "target_experiment_authorized",
        "analysis_cycles",
        "outcome_schedules",
        "qualification_monitor_probes",
        "authorization_cardinality",
        "legacy_runs_resumable",
        *_BOUNDARY_FIELDS,
        AUTHORITY_DIGEST_FIELD,
    }
)
_QUALIFICATION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "qualification_run_id",
        "target_run_id",
        "started_at",
        "completed_at",
        "qualification_authority_binding",
        "capability_evidence_bindings",
        "accepted_qualification_cycles",
        "counted_toward_target",
        "verdict",
        *_BOUNDARY_FIELDS,
        QUALIFICATION_RECEIPT_DIGEST_FIELD,
    }
)
_ACTUAL_CAPABILITY_RECEIPT_BASE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "capability",
        "receipt_id",
        "qualification_run_id",
        "target_run_id",
        "started_at",
        "completed_at",
        "qualification_authority_binding",
        "evidence_root_binding",
        "attempt_count",
        "retry_allowed",
        "full_replay_required",
        "verdict",
        "claim_ceiling",
        *_BOUNDARY_FIELDS,
    }
)
_GATE_EVIDENCE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "gate_id",
        "profile",
        "run_id",
        "target_run_id",
        "evaluated_at",
        "evidence_kind",
        "subject_bindings",
        "subject_binding_count",
        "fresh_process",
        "failure_count",
        "verdict",
        "claim_ceiling",
        *_BOUNDARY_FIELDS,
        GATE_EVIDENCE_DIGEST_FIELD,
    }
)
_QUALIFICATION_RETIREMENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "retirement_id",
        "retired_at",
        "qualification_run_id",
        "target_run_id",
        "qualification_authority_binding",
        "qualification_receipt_binding",
        "status",
        "resume_allowed",
        "counted_toward_target",
        "target_authority_must_postdate_retirement",
        *_BOUNDARY_FIELDS,
        QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32AuthorizationError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32AuthorizationError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32AuthorizationError(code) from exc
    if parsed.tzinfo is None:
        raise V32AuthorizationError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V32AuthorizationError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _relative(value: Any, code: str, *, python_only: bool = False) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or (python_only and path.suffix != ".py")
    ):
        raise V32AuthorizationError(code)
    return text


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_access": False,
        "account_data_accessed": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "order_data_accessed": False,
        "credential_access": False,
        "funds_access": False,
        "portfolio_mutation": False,
    }


def _assert_boundary(document: Mapping[str, Any], code: str) -> None:
    if any(document.get(key) != value for key, value in _boundary().items()):
        raise V32AuthorizationError(code)


def _binding(
    value: Any,
    code: str,
    *,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32AuthorizationError(code)
    result = {
        "path": _relative(value.get("path"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": str(_digest(value.get("semantic_digest"), code)),
        "physical_sha256": str(_digest(value.get("physical_sha256"), code)),
    }
    if (
        (schema_id is not None and result["schema_id"] != schema_id)
        or (digest_field is not None and result["digest_field"] != digest_field)
    ):
        raise V32AuthorizationError(code)
    return result


def _optional_binding(
    value: Any,
    code: str,
    *,
    profile: str,
    schema_id: str,
    digest_field: str,
) -> dict[str, str] | None:
    if profile == QUALIFICATION_PROFILE:
        if value is not None:
            raise V32AuthorizationError(code)
        return None
    return _binding(value, code, schema_id=schema_id, digest_field=digest_field)


def _support_document_bindings(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != set(SUPPORT_BINDING_KEYS):
        raise V32AuthorizationError("V32_MANIFEST_SUPPORT_BINDINGS_INVALID")
    return {
        key: _binding(
            value[key],
            f"V32_MANIFEST_SUPPORT_BINDING_INVALID:{key}",
            schema_id=SUPPORT_DOCUMENT_BINDING_SPECS[key][0],
            digest_field=SUPPORT_DOCUMENT_BINDING_SPECS[key][1],
        )
        for key in SUPPORT_BINDING_KEYS
    }


def _theory_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _THEORY_BINDING_FIELDS:
        raise V32AuthorizationError(code)
    physical = str(_digest(value.get("physical_sha256"), code))
    semantic = str(_digest(value.get("semantic_digest"), code))
    if value.get("theory_version") != THEORY_VERSION:
        raise V32AuthorizationError(code)
    return {
        "relative_ref": _relative(value.get("relative_ref"), code),
        "theory_version": THEORY_VERSION,
        "physical_sha256": physical,
        "semantic_digest": semantic,
    }


def _ordered_paths(values: Any, code: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise V32AuthorizationError(code)
    result = [_relative(value, code, python_only=True) for value in values]
    if not result or result != sorted(set(result)):
        raise V32AuthorizationError(code)
    return result


def _digest_map(value: Any, keys: Sequence[str], code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or tuple(value) != tuple(keys):
        raise V32AuthorizationError(code)
    return {key: str(_digest(value.get(key), code)) for key in keys}


def _binding_map(
    value: Any,
    keys: Sequence[str],
    code: str,
    *,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping) or tuple(value) != tuple(keys):
        raise V32AuthorizationError(code)
    return {
        key: _binding(
            value.get(key),
            code,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        for key in keys
    }


def _binding_sequence(value: Any, code: str) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32AuthorizationError(code)
    result = [_binding(item, code) for item in value]
    if (
        not result
        or result != sorted(result, key=lambda row: row["path"])
        or len({row["path"] for row in result}) != len(result)
    ):
        raise V32AuthorizationError(code)
    return result


def _actual_capability_binding_map(
    value: Any, code: str
) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping) or tuple(value) != CAPABILITY_KEYS:
        raise V32AuthorizationError(code)
    return {
        capability: _binding(
            value.get(capability),
            code,
            schema_id=ACTUAL_CAPABILITY_RECEIPT_SPECS[capability][0],
            digest_field=ACTUAL_CAPABILITY_RECEIPT_SPECS[capability][1],
        )
        for capability in CAPABILITY_KEYS
    }


def _actual_capability_spec(capability: Any) -> tuple[str, str]:
    name = _text(capability, "V32_ACTUAL_CAPABILITY_INVALID")
    try:
        return ACTUAL_CAPABILITY_RECEIPT_SPECS[name]
    except KeyError as exc:
        raise V32AuthorizationError("V32_ACTUAL_CAPABILITY_INVALID") from exc


def _gate_evidence_kind(*, profile: str, gate_id: str) -> str:
    if profile == QUALIFICATION_PHASE_PROFILE:
        return QUALIFICATION_PREFLIGHT_EVIDENCE_KINDS.get(
            gate_id, GATE_EVIDENCE_KINDS[gate_id]
        )
    return GATE_EVIDENCE_KINDS[gate_id]


def _gate_claim_ceiling(*, profile: str, gate_id: str) -> str:
    if (
        profile == QUALIFICATION_PHASE_PROFILE
        and gate_id in QUALIFICATION_PREFLIGHT_EVIDENCE_KINDS
    ):
        return "PREFLIGHT_READINESS_ONLY_NOT_ACTUAL_CAPABILITY"
    return "PROCESS_CAPABILITY_ONLY_NOT_PREDICTION_PROFIT_OR_EXECUTION"


def build_v32_qualification_gate_evidence_v1(
    *,
    gate_id: str,
    profile: str,
    run_id: str,
    target_run_id: str,
    evaluated_at: str,
    subject_bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if gate_id not in Q0_Q8_GATE_IDS:
        raise V32AuthorizationError("V32_GATE_EVIDENCE_GATE_INVALID")
    if profile not in {QUALIFICATION_PHASE_PROFILE, TARGET_PHASE_PROFILE}:
        raise V32AuthorizationError("V32_GATE_EVIDENCE_PROFILE_INVALID")
    run = _text(run_id, "V32_GATE_EVIDENCE_RUN_INVALID")
    target = _text(target_run_id, "V32_GATE_EVIDENCE_RUN_INVALID")
    if (
        (profile == QUALIFICATION_PHASE_PROFILE and run == target)
        or (profile == TARGET_PHASE_PROFILE and run != target)
    ):
        raise V32AuthorizationError("V32_GATE_EVIDENCE_RUN_INVALID")
    bindings = _binding_sequence(
        subject_bindings, "V32_GATE_EVIDENCE_SUBJECT_INVALID"
    )
    actual_schemas = {
        schema_id for schema_id, _ in ACTUAL_CAPABILITY_RECEIPT_SPECS.values()
    }
    if (
        profile == QUALIFICATION_PHASE_PROFILE
        and gate_id in QUALIFICATION_PREFLIGHT_EVIDENCE_KINDS
        and any(binding["schema_id"] in actual_schemas for binding in bindings)
    ):
        raise V32AuthorizationError("V32_GATE_PREFLIGHT_SUBJECT_INVALID")
    if profile == TARGET_PHASE_PROFILE and gate_id in CAPABILITY_GATE_MAP.values():
        capability = next(
            name for name, mapped_gate in CAPABILITY_GATE_MAP.items()
            if mapped_gate == gate_id
        )
        schema_id, digest_field = ACTUAL_CAPABILITY_RECEIPT_SPECS[capability]
        if (
            len(bindings) != 1
            or bindings[0]["schema_id"] != schema_id
            or bindings[0]["digest_field"] != digest_field
        ):
            raise V32AuthorizationError("V32_GATE_ACTUAL_CAPABILITY_SUBJECT_INVALID")
    return self_digest(
        {
            "schema_id": GATE_EVIDENCE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "gate_id": gate_id,
            "profile": profile,
            "run_id": run,
            "target_run_id": target,
            "evaluated_at": _time(
                evaluated_at, "V32_GATE_EVIDENCE_TIME_INVALID"
            ),
            "evidence_kind": _gate_evidence_kind(
                profile=profile, gate_id=gate_id
            ),
            "subject_bindings": bindings,
            "subject_binding_count": len(bindings),
            "fresh_process": True,
            "failure_count": 0,
            "verdict": "PASS",
            "claim_ceiling": _gate_claim_ceiling(
                profile=profile, gate_id=gate_id
            ),
            **_boundary(),
        },
        GATE_EVIDENCE_DIGEST_FIELD,
    )


def verify_v32_qualification_gate_evidence_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _GATE_EVIDENCE_FIELDS:
        raise V32AuthorizationError("V32_GATE_EVIDENCE_INVALID")
    try:
        supplied = verify_self_digest(document, GATE_EVIDENCE_DIGEST_FIELD)
        rebuilt = build_v32_qualification_gate_evidence_v1(
            gate_id=document["gate_id"],
            profile=document["profile"],
            run_id=document["run_id"],
            target_run_id=document["target_run_id"],
            evaluated_at=document["evaluated_at"],
            subject_bindings=document["subject_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_GATE_EVIDENCE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[GATE_EVIDENCE_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_GATE_EVIDENCE_INVALID")
    _assert_boundary(document, "V32_GATE_EVIDENCE_BOUNDARY_INVALID")
    return supplied


def build_v32_theory_approval_receipt_v1(
    *,
    approval_id: str,
    approved_at: str,
    theory_relative_ref: str,
    theory_physical_sha256: str,
    theory_semantic_digest: str,
) -> dict[str, Any]:
    physical = str(
        _digest(theory_physical_sha256, "V32_APPROVAL_THEORY_INVALID")
    )
    semantic = str(
        _digest(theory_semantic_digest, "V32_APPROVAL_THEORY_INVALID")
    )
    return self_digest(
        {
            "schema_id": THEORY_APPROVAL_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "approval_id": _text(approval_id, "V32_APPROVAL_ID_INVALID"),
            "approved_at": _time(approved_at, "V32_APPROVAL_TIME_INVALID"),
            "approval_source": "CURRENT_CODEX_TASK_USER_MESSAGE",
            "user_statement": REQUIRED_APPROVAL_STATEMENT,
            "theory_binding": {
                "relative_ref": _relative(
                    theory_relative_ref, "V32_APPROVAL_THEORY_INVALID"
                ),
                "theory_version": THEORY_VERSION,
                "physical_sha256": physical,
                "semantic_digest": semantic,
            },
            "approval_scope": [
                "SOLE_V32_BTC_USDT_SWAP_PUBLIC_DATA_PROCESS_PILOT",
                "QUALIFICATION_THEN_RETIREMENT_THEN_TARGET_AUTHORITY",
            ],
            "target_experiment_authorization_status": (
                "CONDITIONAL_ON_FULL_LOADER_AND_FRESH_QUALIFICATION"
            ),
            "legacy_runs_resumable": False,
            **_boundary(),
        },
        THEORY_APPROVAL_DIGEST_FIELD,
    )


def verify_v32_theory_approval_receipt_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _THEORY_APPROVAL_FIELDS:
        raise V32AuthorizationError("V32_APPROVAL_INVALID")
    try:
        supplied = verify_self_digest(document, THEORY_APPROVAL_DIGEST_FIELD)
        theory = _theory_binding(document["theory_binding"], "V32_APPROVAL_THEORY_INVALID")
        rebuilt = build_v32_theory_approval_receipt_v1(
            approval_id=document["approval_id"],
            approved_at=document["approved_at"],
            theory_relative_ref=theory["relative_ref"],
            theory_physical_sha256=theory["physical_sha256"],
            theory_semantic_digest=theory["semantic_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_APPROVAL_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[THEORY_APPROVAL_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_APPROVAL_INVALID")
    _assert_boundary(document, "V32_APPROVAL_BOUNDARY_INVALID")
    return supplied


def build_v32_runtime_manifest_v1(
    *,
    manifest_id: str,
    created_at: str,
    runtime_frozen_at: str,
    target_run_id: str,
    qualification_run_id: str,
    theory_approval_binding: Mapping[str, Any],
    experiment_contract_binding: Mapping[str, Any],
    theory_semantic_document_binding: Mapping[str, Any],
    support_document_bindings: Mapping[str, Mapping[str, Any]],
    production_root_paths: Sequence[str],
    fresh_trace_paths: Sequence[str],
    implementation_bindings: Mapping[str, str],
) -> dict[str, Any]:
    """Build the immutable legacy v1 manifest contract.

    New qualifications must use v2.  This constructor remains byte-for-byte
    compatible with the six sealed V3.2 qualification trees so they stay
    replayable without mutation or synthetic trace evidence.
    """

    target = _text(target_run_id, "V32_MANIFEST_RUN_INVALID")
    qualification = _text(qualification_run_id, "V32_MANIFEST_RUN_INVALID")
    if target == qualification:
        raise V32AuthorizationError("V32_MANIFEST_RUN_INVALID")
    roots = _ordered_paths(production_root_paths, "V32_MANIFEST_ROOTS_INVALID")
    trace = _ordered_paths(fresh_trace_paths, "V32_MANIFEST_TRACE_INVALID")
    if not isinstance(implementation_bindings, Mapping):
        raise V32AuthorizationError("V32_MANIFEST_BINDINGS_INVALID")
    bindings = {
        _relative(path, "V32_MANIFEST_BINDINGS_INVALID", python_only=True): str(
            _digest(digest, "V32_MANIFEST_BINDINGS_INVALID")
        )
        for path, digest in implementation_bindings.items()
    }
    if (
        not bindings
        or tuple(bindings) != tuple(sorted(bindings))
        or not set(roots).issubset(bindings)
        or not set(trace).issubset(bindings)
    ):
        raise V32AuthorizationError("V32_MANIFEST_BINDINGS_INVALID")
    return self_digest(
        {
            "schema_id": RUNTIME_MANIFEST_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "manifest_id": _text(manifest_id, "V32_MANIFEST_ID_INVALID"),
            "created_at": _time(created_at, "V32_MANIFEST_TIME_INVALID"),
            "runtime_frozen_at": _time(
                runtime_frozen_at, "V32_MANIFEST_TIME_INVALID"
            ),
            "target_run_id": target,
            "qualification_run_id": qualification,
            "theory_approval_binding": _binding(
                theory_approval_binding,
                "V32_MANIFEST_APPROVAL_BINDING_INVALID",
                schema_id=THEORY_APPROVAL_SCHEMA_ID,
                digest_field=THEORY_APPROVAL_DIGEST_FIELD,
            ),
            "experiment_contract_binding": _binding(
                experiment_contract_binding,
                "V32_MANIFEST_CONTRACT_BINDING_INVALID",
                schema_id=EXPERIMENT_CONTRACT_SCHEMA_ID,
                digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
            ),
            "theory_semantic_document_binding": _binding(
                theory_semantic_document_binding,
                "V32_MANIFEST_THEORY_DOCUMENT_BINDING_INVALID",
                schema_id=THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
                digest_field=THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
            ),
            "support_document_bindings": _support_document_bindings(
                support_document_bindings
            ),
            "production_root_paths": roots,
            "fresh_trace_paths": trace,
            "implementation_bindings": bindings,
            "runtime_path_count": len(bindings),
            "runtime_closure_policy": (
                "EXACT_STATIC_AND_FRESH_TRACE_UNION_WITH_PHYSICAL_SHA256"
            ),
            "instrument": {
                "venue": "OKX",
                "instrument_id": "BTC-USDT-SWAP",
                "market_type": "PERPETUAL_SWAP",
            },
            "pilot_protocol": {
                "analysis_cycles": TOTAL_ANALYSIS_CYCLES,
                "outcome_schedules": TOTAL_OUTCOME_SCHEDULES,
                "analysis_interval_seconds": 900,
            },
            **_boundary(),
        },
        RUNTIME_MANIFEST_DIGEST_FIELD,
    )


def verify_v32_runtime_manifest_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _RUNTIME_MANIFEST_V1_FIELDS:
        raise V32AuthorizationError("V32_MANIFEST_INVALID")
    try:
        supplied = verify_self_digest(document, RUNTIME_MANIFEST_DIGEST_FIELD)
        rebuilt = build_v32_runtime_manifest_v1(
            manifest_id=document["manifest_id"],
            created_at=document["created_at"],
            runtime_frozen_at=document["runtime_frozen_at"],
            target_run_id=document["target_run_id"],
            qualification_run_id=document["qualification_run_id"],
            theory_approval_binding=document["theory_approval_binding"],
            experiment_contract_binding=document["experiment_contract_binding"],
            theory_semantic_document_binding=document[
                "theory_semantic_document_binding"
            ],
            support_document_bindings=document["support_document_bindings"],
            production_root_paths=document["production_root_paths"],
            fresh_trace_paths=document["fresh_trace_paths"],
            implementation_bindings=document["implementation_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_MANIFEST_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[RUNTIME_MANIFEST_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_MANIFEST_INVALID")
    _assert_boundary(document, "V32_MANIFEST_BOUNDARY_INVALID")
    return supplied


def build_v32_runtime_manifest_v2(
    *,
    manifest_id: str,
    created_at: str,
    runtime_frozen_at: str,
    target_run_id: str,
    qualification_run_id: str,
    theory_approval_binding: Mapping[str, Any],
    experiment_contract_binding: Mapping[str, Any],
    theory_semantic_document_binding: Mapping[str, Any],
    support_document_bindings: Mapping[str, Mapping[str, Any]],
    production_root_paths: Sequence[str],
    fresh_trace_paths: Sequence[str],
    fresh_process_trace_binding: Mapping[str, Any],
    implementation_bindings: Mapping[str, str],
) -> dict[str, Any]:
    target = _text(target_run_id, "V32_MANIFEST_RUN_INVALID")
    qualification = _text(qualification_run_id, "V32_MANIFEST_RUN_INVALID")
    if target == qualification:
        raise V32AuthorizationError("V32_MANIFEST_RUN_INVALID")
    roots = _ordered_paths(production_root_paths, "V32_MANIFEST_ROOTS_INVALID")
    trace = _ordered_paths(fresh_trace_paths, "V32_MANIFEST_TRACE_INVALID")
    if not isinstance(implementation_bindings, Mapping):
        raise V32AuthorizationError("V32_MANIFEST_BINDINGS_INVALID")
    bindings = {
        _relative(path, "V32_MANIFEST_BINDINGS_INVALID", python_only=True): str(
            _digest(digest, "V32_MANIFEST_BINDINGS_INVALID")
        )
        for path, digest in implementation_bindings.items()
    }
    if (
        not bindings
        or tuple(bindings) != tuple(sorted(bindings))
        or not set(roots).issubset(bindings)
        or not set(trace).issubset(bindings)
    ):
        raise V32AuthorizationError("V32_MANIFEST_BINDINGS_INVALID")
    return self_digest(
        {
            "schema_id": RUNTIME_MANIFEST_V2_SCHEMA_ID,
            "schema_version": RUNTIME_MANIFEST_V2_SCHEMA_VERSION,
            "manifest_id": _text(manifest_id, "V32_MANIFEST_ID_INVALID"),
            "created_at": _time(created_at, "V32_MANIFEST_TIME_INVALID"),
            "runtime_frozen_at": _time(
                runtime_frozen_at, "V32_MANIFEST_TIME_INVALID"
            ),
            "target_run_id": target,
            "qualification_run_id": qualification,
            "theory_approval_binding": _binding(
                theory_approval_binding,
                "V32_MANIFEST_APPROVAL_BINDING_INVALID",
                schema_id=THEORY_APPROVAL_SCHEMA_ID,
                digest_field=THEORY_APPROVAL_DIGEST_FIELD,
            ),
            "experiment_contract_binding": _binding(
                experiment_contract_binding,
                "V32_MANIFEST_CONTRACT_BINDING_INVALID",
                schema_id=EXPERIMENT_CONTRACT_SCHEMA_ID,
                digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
            ),
            "theory_semantic_document_binding": _binding(
                theory_semantic_document_binding,
                "V32_MANIFEST_THEORY_DOCUMENT_BINDING_INVALID",
                schema_id=THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
                digest_field=THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
            ),
            "support_document_bindings": _support_document_bindings(
                support_document_bindings
            ),
            "production_root_paths": roots,
            "fresh_trace_paths": trace,
            "fresh_process_trace_binding": _binding(
                fresh_process_trace_binding,
                "V32_MANIFEST_FRESH_TRACE_BINDING_INVALID",
                schema_id=FRESH_PROCESS_TRACE_SCHEMA_ID,
                digest_field=FRESH_PROCESS_TRACE_DIGEST_FIELD,
            ),
            "implementation_bindings": bindings,
            "runtime_path_count": len(bindings),
            "runtime_closure_policy": (
                "EXACT_STATIC_AND_OBSERVED_FRESH_PROCESS_UNION_WITH_"
                "TRACE_RECEIPT_AND_PHYSICAL_SHA256"
            ),
            "instrument": {
                "venue": "OKX",
                "instrument_id": "BTC-USDT-SWAP",
                "market_type": "PERPETUAL_SWAP",
            },
            "pilot_protocol": {
                "analysis_cycles": TOTAL_ANALYSIS_CYCLES,
                "outcome_schedules": TOTAL_OUTCOME_SCHEDULES,
                "analysis_interval_seconds": 900,
            },
            **_boundary(),
        },
        RUNTIME_MANIFEST_DIGEST_FIELD,
    )


def verify_v32_runtime_manifest_v2(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _RUNTIME_MANIFEST_V2_FIELDS:
        raise V32AuthorizationError("V32_MANIFEST_INVALID")
    try:
        supplied = verify_self_digest(document, RUNTIME_MANIFEST_DIGEST_FIELD)
        rebuilt = build_v32_runtime_manifest_v2(
            manifest_id=document["manifest_id"],
            created_at=document["created_at"],
            runtime_frozen_at=document["runtime_frozen_at"],
            target_run_id=document["target_run_id"],
            qualification_run_id=document["qualification_run_id"],
            theory_approval_binding=document["theory_approval_binding"],
            experiment_contract_binding=document["experiment_contract_binding"],
            theory_semantic_document_binding=document[
                "theory_semantic_document_binding"
            ],
            support_document_bindings=document["support_document_bindings"],
            production_root_paths=document["production_root_paths"],
            fresh_trace_paths=document["fresh_trace_paths"],
            fresh_process_trace_binding=document[
                "fresh_process_trace_binding"
            ],
            implementation_bindings=document["implementation_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_MANIFEST_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[RUNTIME_MANIFEST_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_MANIFEST_INVALID")
    _assert_boundary(document, "V32_MANIFEST_BOUNDARY_INVALID")
    return supplied


def verify_v32_runtime_manifest(document: Mapping[str, Any]) -> str:
    """Strictly dispatch one recognized manifest version without coercion."""

    if not isinstance(document, Mapping):
        raise V32AuthorizationError("V32_MANIFEST_INVALID")
    if document.get("schema_id") != RUNTIME_MANIFEST_SCHEMA_ID:
        raise V32AuthorizationError("V32_MANIFEST_SCHEMA_UNSUPPORTED")
    schema_version = document.get("schema_version")
    if schema_version == SCHEMA_VERSION:
        return verify_v32_runtime_manifest_v1(document)
    if schema_version == RUNTIME_MANIFEST_V2_SCHEMA_VERSION:
        return verify_v32_runtime_manifest_v2(document)
    raise V32AuthorizationError("V32_MANIFEST_VERSION_UNSUPPORTED")


def build_v32_phase_a_qualification_receipt_v1(
    *,
    phase_id: str,
    profile: str,
    run_id: str,
    target_run_id: str,
    evaluated_at: str,
    theory_approval_digest: str,
    experiment_contract_digest: str,
    runtime_manifest_digest: str,
    q0_q8_evidence_bindings: Mapping[str, Mapping[str, Any]],
    predecessor_retirement_digest: str | None,
) -> dict[str, Any]:
    if profile not in {QUALIFICATION_PHASE_PROFILE, TARGET_PHASE_PROFILE}:
        raise V32AuthorizationError("V32_PHASE_PROFILE_INVALID")
    run = _text(run_id, "V32_PHASE_RUN_INVALID")
    target = _text(target_run_id, "V32_PHASE_RUN_INVALID")
    if (
        (profile == QUALIFICATION_PHASE_PROFILE and run == target)
        or (profile == TARGET_PHASE_PROFILE and run != target)
    ):
        raise V32AuthorizationError("V32_PHASE_RUN_INVALID")
    predecessor = _digest(
        predecessor_retirement_digest,
        "V32_PHASE_PREDECESSOR_INVALID",
        nullable=True,
    )
    if (
        profile == QUALIFICATION_PHASE_PROFILE and predecessor is not None
    ) or (profile == TARGET_PHASE_PROFILE and predecessor is None):
        raise V32AuthorizationError("V32_PHASE_PREDECESSOR_INVALID")
    return self_digest(
        {
            "schema_id": PHASE_A_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "phase_id": _text(phase_id, "V32_PHASE_ID_INVALID"),
            "profile": profile,
            "run_id": run,
            "target_run_id": target,
            "evaluated_at": _time(evaluated_at, "V32_PHASE_TIME_INVALID"),
            "theory_approval_digest": _digest(
                theory_approval_digest, "V32_PHASE_BINDING_INVALID"
            ),
            "experiment_contract_digest": _digest(
                experiment_contract_digest, "V32_PHASE_BINDING_INVALID"
            ),
            "runtime_manifest_digest": _digest(
                runtime_manifest_digest, "V32_PHASE_BINDING_INVALID"
            ),
            "q0_q8_evidence_bindings": _binding_map(
                q0_q8_evidence_bindings,
                Q0_Q8_GATE_IDS,
                "V32_PHASE_Q0_Q8_INVALID",
                schema_id=GATE_EVIDENCE_SCHEMA_ID,
                digest_field=GATE_EVIDENCE_DIGEST_FIELD,
            ),
            "predecessor_retirement_digest": predecessor,
            "verdict": "PASS",
            **_boundary(),
        },
        PHASE_A_DIGEST_FIELD,
    )


def verify_v32_phase_a_qualification_receipt_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _PHASE_A_FIELDS:
        raise V32AuthorizationError("V32_PHASE_INVALID")
    try:
        supplied = verify_self_digest(document, PHASE_A_DIGEST_FIELD)
        rebuilt = build_v32_phase_a_qualification_receipt_v1(
            phase_id=document["phase_id"],
            profile=document["profile"],
            run_id=document["run_id"],
            target_run_id=document["target_run_id"],
            evaluated_at=document["evaluated_at"],
            theory_approval_digest=document["theory_approval_digest"],
            experiment_contract_digest=document["experiment_contract_digest"],
            runtime_manifest_digest=document["runtime_manifest_digest"],
            q0_q8_evidence_bindings=document["q0_q8_evidence_bindings"],
            predecessor_retirement_digest=document[
                "predecessor_retirement_digest"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_PHASE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[PHASE_A_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_PHASE_INVALID")
    _assert_boundary(document, "V32_PHASE_BOUNDARY_INVALID")
    return supplied


def build_v32_authorization_receipt_v1(
    *,
    authorization_id: str,
    profile: str,
    issued_at: str,
    run_id: str,
    target_run_id: str,
    theory_approval_binding: Mapping[str, Any],
    experiment_contract_binding: Mapping[str, Any],
    runtime_manifest_binding: Mapping[str, Any],
    phase_a_receipt_binding: Mapping[str, Any],
    qualification_retirement_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if profile not in {QUALIFICATION_PROFILE, TARGET_PROFILE}:
        raise V32AuthorizationError("V32_AUTHORIZATION_PROFILE_INVALID")
    run = _text(run_id, "V32_AUTHORIZATION_RUN_INVALID")
    target = _text(target_run_id, "V32_AUTHORIZATION_RUN_INVALID")
    if (
        (profile == QUALIFICATION_PROFILE and run == target)
        or (profile == TARGET_PROFILE and run != target)
    ):
        raise V32AuthorizationError("V32_AUTHORIZATION_RUN_INVALID")
    return self_digest(
        {
            "schema_id": AUTHORIZATION_RECEIPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "authorization_id": _text(
                authorization_id, "V32_AUTHORIZATION_ID_INVALID"
            ),
            "profile": profile,
            "issued_at": _time(issued_at, "V32_AUTHORIZATION_TIME_INVALID"),
            "run_id": run,
            "target_run_id": target,
            "theory_approval_binding": _binding(
                theory_approval_binding,
                "V32_AUTHORIZATION_BINDING_INVALID",
                schema_id=THEORY_APPROVAL_SCHEMA_ID,
                digest_field=THEORY_APPROVAL_DIGEST_FIELD,
            ),
            "experiment_contract_binding": _binding(
                experiment_contract_binding,
                "V32_AUTHORIZATION_BINDING_INVALID",
                schema_id=EXPERIMENT_CONTRACT_SCHEMA_ID,
                digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
            ),
            "runtime_manifest_binding": _binding(
                runtime_manifest_binding,
                "V32_AUTHORIZATION_BINDING_INVALID",
                schema_id=RUNTIME_MANIFEST_SCHEMA_ID,
                digest_field=RUNTIME_MANIFEST_DIGEST_FIELD,
            ),
            "phase_a_receipt_binding": _binding(
                phase_a_receipt_binding,
                "V32_AUTHORIZATION_BINDING_INVALID",
                schema_id=PHASE_A_SCHEMA_ID,
                digest_field=PHASE_A_DIGEST_FIELD,
            ),
            "qualification_retirement_binding": _optional_binding(
                qualification_retirement_binding,
                "V32_AUTHORIZATION_RETIREMENT_INVALID",
                profile=profile,
                schema_id=QUALIFICATION_RETIREMENT_SCHEMA_ID,
                digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
            ),
            "authorization_cardinality": 1,
            "legacy_runs_resumable": False,
            **_boundary(),
        },
        AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    )


def verify_v32_authorization_receipt_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _AUTHORIZATION_RECEIPT_FIELDS:
        raise V32AuthorizationError("V32_AUTHORIZATION_INVALID")
    try:
        supplied = verify_self_digest(document, AUTHORIZATION_RECEIPT_DIGEST_FIELD)
        rebuilt = build_v32_authorization_receipt_v1(
            authorization_id=document["authorization_id"],
            profile=document["profile"],
            issued_at=document["issued_at"],
            run_id=document["run_id"],
            target_run_id=document["target_run_id"],
            theory_approval_binding=document["theory_approval_binding"],
            experiment_contract_binding=document["experiment_contract_binding"],
            runtime_manifest_binding=document["runtime_manifest_binding"],
            phase_a_receipt_binding=document["phase_a_receipt_binding"],
            qualification_retirement_binding=document[
                "qualification_retirement_binding"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_AUTHORIZATION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[AUTHORIZATION_RECEIPT_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_AUTHORIZATION_INVALID")
    _assert_boundary(document, "V32_AUTHORIZATION_BOUNDARY_INVALID")
    return supplied


def build_v32_authority_v1(
    *,
    authority_id: str,
    profile: str,
    recorded_at: str,
    run_id: str,
    target_run_id: str,
    predecessor_authority_binding: Mapping[str, Any],
    theory_approval_binding: Mapping[str, Any],
    experiment_contract_binding: Mapping[str, Any],
    runtime_manifest_binding: Mapping[str, Any],
    phase_a_receipt_binding: Mapping[str, Any],
    authorization_receipt_binding: Mapping[str, Any],
    qualification_retirement_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if profile not in {QUALIFICATION_PROFILE, TARGET_PROFILE}:
        raise V32AuthorizationError("V32_AUTHORITY_PROFILE_INVALID")
    run = _text(run_id, "V32_AUTHORITY_RUN_INVALID")
    target = _text(target_run_id, "V32_AUTHORITY_RUN_INVALID")
    if (
        (profile == QUALIFICATION_PROFILE and run == target)
        or (profile == TARGET_PROFILE and run != target)
    ):
        raise V32AuthorizationError("V32_AUTHORITY_RUN_INVALID")
    return self_digest(
        {
            "schema_id": AUTHORITY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "authority_id": _text(authority_id, "V32_AUTHORITY_ID_INVALID"),
            "profile": profile,
            "recorded_at": _time(recorded_at, "V32_AUTHORITY_TIME_INVALID"),
            "status": "ACTIVE",
            "run_id": run,
            "target_run_id": target,
            "predecessor_authority_binding": _binding(
                predecessor_authority_binding,
                "V32_AUTHORITY_PREDECESSOR_INVALID",
            ),
            "theory_approval_binding": _binding(
                theory_approval_binding,
                "V32_AUTHORITY_BINDING_INVALID",
                schema_id=THEORY_APPROVAL_SCHEMA_ID,
                digest_field=THEORY_APPROVAL_DIGEST_FIELD,
            ),
            "experiment_contract_binding": _binding(
                experiment_contract_binding,
                "V32_AUTHORITY_BINDING_INVALID",
                schema_id=EXPERIMENT_CONTRACT_SCHEMA_ID,
                digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
            ),
            "runtime_manifest_binding": _binding(
                runtime_manifest_binding,
                "V32_AUTHORITY_BINDING_INVALID",
                schema_id=RUNTIME_MANIFEST_SCHEMA_ID,
                digest_field=RUNTIME_MANIFEST_DIGEST_FIELD,
            ),
            "phase_a_receipt_binding": _binding(
                phase_a_receipt_binding,
                "V32_AUTHORITY_BINDING_INVALID",
                schema_id=PHASE_A_SCHEMA_ID,
                digest_field=PHASE_A_DIGEST_FIELD,
            ),
            "authorization_receipt_binding": _binding(
                authorization_receipt_binding,
                "V32_AUTHORITY_BINDING_INVALID",
                schema_id=AUTHORIZATION_RECEIPT_SCHEMA_ID,
                digest_field=AUTHORIZATION_RECEIPT_DIGEST_FIELD,
            ),
            "qualification_retirement_binding": _optional_binding(
                qualification_retirement_binding,
                "V32_AUTHORITY_RETIREMENT_INVALID",
                profile=profile,
                schema_id=QUALIFICATION_RETIREMENT_SCHEMA_ID,
                digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
            ),
            "authorized_operation": (
                "V32_ISOLATED_QUALIFICATION"
                if profile == QUALIFICATION_PROFILE
                else "V32_DYNAMIC_AGGRESSIVE_PROCESS_PILOT"
            ),
            "run_start_authorized": True,
            "target_experiment_authorized": profile == TARGET_PROFILE,
            "analysis_cycles": 1 if profile == QUALIFICATION_PROFILE else TOTAL_ANALYSIS_CYCLES,
            "outcome_schedules": 0 if profile == QUALIFICATION_PROFILE else TOTAL_OUTCOME_SCHEDULES,
            "qualification_monitor_probes": (
                1 if profile == QUALIFICATION_PROFILE else 0
            ),
            "authorization_cardinality": 1,
            "legacy_runs_resumable": False,
            **_boundary(),
        },
        AUTHORITY_DIGEST_FIELD,
    )


def verify_v32_authority_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _AUTHORITY_FIELDS:
        raise V32AuthorizationError("V32_AUTHORITY_INVALID")
    try:
        supplied = verify_self_digest(document, AUTHORITY_DIGEST_FIELD)
        rebuilt = build_v32_authority_v1(
            authority_id=document["authority_id"],
            profile=document["profile"],
            recorded_at=document["recorded_at"],
            run_id=document["run_id"],
            target_run_id=document["target_run_id"],
            predecessor_authority_binding=document["predecessor_authority_binding"],
            theory_approval_binding=document["theory_approval_binding"],
            experiment_contract_binding=document["experiment_contract_binding"],
            runtime_manifest_binding=document["runtime_manifest_binding"],
            phase_a_receipt_binding=document["phase_a_receipt_binding"],
            authorization_receipt_binding=document[
                "authorization_receipt_binding"
            ],
            qualification_retirement_binding=document[
                "qualification_retirement_binding"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_AUTHORITY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[AUTHORITY_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_AUTHORITY_INVALID")
    _assert_boundary(document, "V32_AUTHORITY_BOUNDARY_INVALID")
    return supplied


def build_v32_actual_capability_receipt_v1(
    *,
    capability: str,
    receipt_id: str,
    qualification_run_id: str,
    target_run_id: str,
    started_at: str,
    completed_at: str,
    qualification_authority_binding: Mapping[str, Any],
    evidence_root_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one post-authority receipt for an actually exercised path.

    The receipt deliberately does not interpret ``evidence_root_binding``.
    That evidence is capability-specific and the full loader must delegate it
    to an explicitly injected owning verifier; a self-digest check is not a
    substitute for that replay.
    """

    schema_id, digest_field = _actual_capability_spec(capability)
    started = _moment(started_at, "V32_ACTUAL_CAPABILITY_TIME_INVALID")
    completed = _moment(completed_at, "V32_ACTUAL_CAPABILITY_TIME_INVALID")
    qualification = _text(
        qualification_run_id, "V32_ACTUAL_CAPABILITY_RUN_INVALID"
    )
    target = _text(target_run_id, "V32_ACTUAL_CAPABILITY_RUN_INVALID")
    if started > completed or qualification == target:
        raise V32AuthorizationError("V32_ACTUAL_CAPABILITY_RUN_INVALID")
    return self_digest(
        {
            "schema_id": schema_id,
            "schema_version": SCHEMA_VERSION,
            "capability": capability,
            "receipt_id": _text(
                receipt_id, "V32_ACTUAL_CAPABILITY_RECEIPT_ID_INVALID"
            ),
            "qualification_run_id": qualification,
            "target_run_id": target,
            "started_at": _time(
                started_at, "V32_ACTUAL_CAPABILITY_TIME_INVALID"
            ),
            "completed_at": _time(
                completed_at, "V32_ACTUAL_CAPABILITY_TIME_INVALID"
            ),
            "qualification_authority_binding": _binding(
                qualification_authority_binding,
                "V32_ACTUAL_CAPABILITY_AUTHORITY_INVALID",
                schema_id=AUTHORITY_SCHEMA_ID,
                digest_field=AUTHORITY_DIGEST_FIELD,
            ),
            "evidence_root_binding": _binding(
                evidence_root_binding, "V32_ACTUAL_CAPABILITY_EVIDENCE_INVALID"
            ),
            "attempt_count": 1,
            "retry_allowed": False,
            "full_replay_required": True,
            "verdict": "PASS",
            "claim_ceiling": (
                "ACTUAL_PROCESS_CAPABILITY_ONLY_NOT_PREDICTION_PROFIT_OR_EXECUTION"
            ),
            **_boundary(),
        },
        digest_field,
    )


def verify_v32_actual_capability_receipt_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V32AuthorizationError("V32_ACTUAL_CAPABILITY_RECEIPT_INVALID")
    try:
        capability = document["capability"]
        schema_id, digest_field = _actual_capability_spec(capability)
        expected_fields = _ACTUAL_CAPABILITY_RECEIPT_BASE_FIELDS | {digest_field}
        if set(document) != expected_fields or document.get("schema_id") != schema_id:
            raise V32AuthorizationError(
                "V32_ACTUAL_CAPABILITY_RECEIPT_INVALID"
            )
        supplied = verify_self_digest(document, digest_field)
        rebuilt = build_v32_actual_capability_receipt_v1(
            capability=capability,
            receipt_id=document["receipt_id"],
            qualification_run_id=document["qualification_run_id"],
            target_run_id=document["target_run_id"],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            qualification_authority_binding=document[
                "qualification_authority_binding"
            ],
            evidence_root_binding=document["evidence_root_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError(
            "V32_ACTUAL_CAPABILITY_RECEIPT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[digest_field]:
        raise V32AuthorizationError("V32_ACTUAL_CAPABILITY_RECEIPT_INVALID")
    _assert_boundary(document, "V32_ACTUAL_CAPABILITY_BOUNDARY_INVALID")
    return supplied


def build_v32_fresh_capability_qualification_receipt_v1(
    *,
    qualification_id: str,
    qualification_run_id: str,
    target_run_id: str,
    started_at: str,
    completed_at: str,
    qualification_authority_binding: Mapping[str, Any],
    capability_evidence_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    started = _moment(started_at, "V32_CAPABILITY_QUALIFICATION_TIME_INVALID")
    completed = _moment(completed_at, "V32_CAPABILITY_QUALIFICATION_TIME_INVALID")
    qualification = _text(
        qualification_run_id, "V32_CAPABILITY_QUALIFICATION_RUN_INVALID"
    )
    target = _text(target_run_id, "V32_CAPABILITY_QUALIFICATION_RUN_INVALID")
    if started > completed or qualification == target:
        raise V32AuthorizationError("V32_CAPABILITY_QUALIFICATION_RUN_INVALID")
    return self_digest(
        {
            "schema_id": QUALIFICATION_RECEIPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "qualification_id": _text(
                qualification_id, "V32_CAPABILITY_QUALIFICATION_ID_INVALID"
            ),
            "qualification_run_id": qualification,
            "target_run_id": target,
            "started_at": _time(
                started_at, "V32_CAPABILITY_QUALIFICATION_TIME_INVALID"
            ),
            "completed_at": _time(
                completed_at, "V32_CAPABILITY_QUALIFICATION_TIME_INVALID"
            ),
            "qualification_authority_binding": _binding(
                qualification_authority_binding,
                "V32_CAPABILITY_QUALIFICATION_AUTHORITY_INVALID",
                schema_id=AUTHORITY_SCHEMA_ID,
                digest_field=AUTHORITY_DIGEST_FIELD,
            ),
            "capability_evidence_bindings": _actual_capability_binding_map(
                capability_evidence_bindings,
                "V32_CAPABILITY_QUALIFICATION_EVIDENCE_INVALID",
            ),
            "accepted_qualification_cycles": 1,
            "counted_toward_target": False,
            "verdict": "PASS",
            **_boundary(),
        },
        QUALIFICATION_RECEIPT_DIGEST_FIELD,
    )


def verify_v32_fresh_capability_qualification_receipt_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _QUALIFICATION_RECEIPT_FIELDS:
        raise V32AuthorizationError("V32_CAPABILITY_QUALIFICATION_INVALID")
    try:
        supplied = verify_self_digest(document, QUALIFICATION_RECEIPT_DIGEST_FIELD)
        rebuilt = build_v32_fresh_capability_qualification_receipt_v1(
            qualification_id=document["qualification_id"],
            qualification_run_id=document["qualification_run_id"],
            target_run_id=document["target_run_id"],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            qualification_authority_binding=document[
                "qualification_authority_binding"
            ],
            capability_evidence_bindings=document["capability_evidence_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_CAPABILITY_QUALIFICATION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[QUALIFICATION_RECEIPT_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_CAPABILITY_QUALIFICATION_INVALID")
    _assert_boundary(document, "V32_CAPABILITY_QUALIFICATION_BOUNDARY_INVALID")
    return supplied


def build_v32_qualification_retirement_receipt_v1(
    *,
    retirement_id: str,
    retired_at: str,
    qualification_run_id: str,
    target_run_id: str,
    qualification_authority_binding: Mapping[str, Any],
    qualification_receipt_binding: Mapping[str, Any],
) -> dict[str, Any]:
    qualification = _text(qualification_run_id, "V32_RETIREMENT_RUN_INVALID")
    target = _text(target_run_id, "V32_RETIREMENT_RUN_INVALID")
    if qualification == target:
        raise V32AuthorizationError("V32_RETIREMENT_RUN_INVALID")
    return self_digest(
        {
            "schema_id": QUALIFICATION_RETIREMENT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "retirement_id": _text(retirement_id, "V32_RETIREMENT_ID_INVALID"),
            "retired_at": _time(retired_at, "V32_RETIREMENT_TIME_INVALID"),
            "qualification_run_id": qualification,
            "target_run_id": target,
            "qualification_authority_binding": _binding(
                qualification_authority_binding,
                "V32_RETIREMENT_AUTHORITY_INVALID",
                schema_id=AUTHORITY_SCHEMA_ID,
                digest_field=AUTHORITY_DIGEST_FIELD,
            ),
            "qualification_receipt_binding": _binding(
                qualification_receipt_binding,
                "V32_RETIREMENT_QUALIFICATION_INVALID",
                schema_id=QUALIFICATION_RECEIPT_SCHEMA_ID,
                digest_field=QUALIFICATION_RECEIPT_DIGEST_FIELD,
            ),
            "status": "RETIRED",
            "resume_allowed": False,
            "counted_toward_target": False,
            "target_authority_must_postdate_retirement": True,
            **_boundary(),
        },
        QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    )


def verify_v32_qualification_retirement_receipt_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _QUALIFICATION_RETIREMENT_FIELDS:
        raise V32AuthorizationError("V32_RETIREMENT_INVALID")
    try:
        supplied = verify_self_digest(document, QUALIFICATION_RETIREMENT_DIGEST_FIELD)
        rebuilt = build_v32_qualification_retirement_receipt_v1(
            retirement_id=document["retirement_id"],
            retired_at=document["retired_at"],
            qualification_run_id=document["qualification_run_id"],
            target_run_id=document["target_run_id"],
            qualification_authority_binding=document[
                "qualification_authority_binding"
            ],
            qualification_receipt_binding=document[
                "qualification_receipt_binding"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizationError):
            raise
        raise V32AuthorizationError("V32_RETIREMENT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[QUALIFICATION_RETIREMENT_DIGEST_FIELD]:
        raise V32AuthorizationError("V32_RETIREMENT_INVALID")
    _assert_boundary(document, "V32_RETIREMENT_BOUNDARY_INVALID")
    return supplied


__all__ = [
    "ACTUAL_CAPABILITY_RECEIPT_SPECS",
    "AUTHORITY_DIGEST_FIELD",
    "AUTHORITY_SCHEMA_ID",
    "AUTHORIZATION_RECEIPT_DIGEST_FIELD",
    "AUTHORIZATION_RECEIPT_SCHEMA_ID",
    "CAPABILITY_KEYS",
    "CAPABILITY_GATE_MAP",
    "GATE_EVIDENCE_DIGEST_FIELD",
    "GATE_EVIDENCE_KINDS",
    "GATE_EVIDENCE_SCHEMA_ID",
    "PHASE_A_DIGEST_FIELD",
    "PHASE_A_SCHEMA_ID",
    "Q0_Q8_GATE_IDS",
    "QUALIFICATION_PHASE_PROFILE",
    "QUALIFICATION_PREFLIGHT_EVIDENCE_KINDS",
    "QUALIFICATION_PROFILE",
    "QUALIFICATION_RECEIPT_DIGEST_FIELD",
    "QUALIFICATION_RECEIPT_SCHEMA_ID",
    "QUALIFICATION_RETIREMENT_DIGEST_FIELD",
    "QUALIFICATION_RETIREMENT_SCHEMA_ID",
    "REQUIRED_APPROVAL_STATEMENT",
    "RUNTIME_MANIFEST_DIGEST_FIELD",
    "RUNTIME_MANIFEST_SCHEMA_ID",
    "RUNTIME_MANIFEST_V2_SCHEMA_ID",
    "RUNTIME_MANIFEST_V2_SCHEMA_VERSION",
    "SUPPORT_DOCUMENT_BINDING_SPECS",
    "TARGET_PHASE_PROFILE",
    "TARGET_PROFILE",
    "THEORY_APPROVAL_DIGEST_FIELD",
    "THEORY_APPROVAL_SCHEMA_ID",
    "THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD",
    "THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID",
    "V32AuthorizationError",
    "build_v32_authority_v1",
    "build_v32_actual_capability_receipt_v1",
    "build_v32_authorization_receipt_v1",
    "build_v32_fresh_capability_qualification_receipt_v1",
    "build_v32_phase_a_qualification_receipt_v1",
    "build_v32_qualification_gate_evidence_v1",
    "build_v32_qualification_retirement_receipt_v1",
    "build_v32_runtime_manifest_v1",
    "build_v32_runtime_manifest_v2",
    "build_v32_theory_approval_receipt_v1",
    "verify_v32_authority_v1",
    "verify_v32_actual_capability_receipt_v1",
    "verify_v32_authorization_receipt_v1",
    "verify_v32_fresh_capability_qualification_receipt_v1",
    "verify_v32_phase_a_qualification_receipt_v1",
    "verify_v32_qualification_gate_evidence_v1",
    "verify_v32_qualification_retirement_receipt_v1",
    "verify_v32_runtime_manifest",
    "verify_v32_runtime_manifest_v1",
    "verify_v32_runtime_manifest_v2",
    "verify_v32_theory_approval_receipt_v1",
]
