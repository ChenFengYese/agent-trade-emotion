"""Pure V3.1.1 successor-authority envelope and application projection.

The historical V3.1 authority remains immutable.  This module adds one
versioned envelope beside it.  The envelope does not grant account, paper,
live, order, credential, funds, or portfolio authority.  It cross-binds:

* the fully replayed V3.1 active chain and its permanently failed monitor;
* a standard V3 qualification authority/run and its one-cycle receipts;
* a later, distinct standard V4 target authority/run for the formal 8/8;
* the frozen V3.1.1 addendum and successor runtime contracts;
* the twelve-axis source registry, association preregistration, evaluation
  contract, and the three fresh qualification receipts.

Physical containment, byte replay, the historical Q0-Q8 replay, and runtime
closure replay belong to Infrastructure.  Application receives only the
target V4 chain's five semantic authority documents after that complete loader
succeeds.  The qualification cycle can never count toward the target 8/8.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ..contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..v31_association_preregistration_v2 import (
    verify_v31_association_preregistration_v2,
)
from ..v31_evaluation_contract_v2 import verify_v31_evaluation_contract_v2
from ..v31_experiment_supervisor_v2 import (
    COMMIT_INTENT_DIGEST_FIELD,
    COMMIT_INTENT_SCHEMA_ID,
    COMMIT_INTENT_SCHEMA_VERSION,
    CYCLE_PERMIT_DIGEST_FIELD,
    CYCLE_PERMIT_SCHEMA_ID,
    CYCLE_PERMIT_SCHEMA_VERSION,
    PERMITTED_OPERATIONS,
    SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    SUPERVISOR_CHECKPOINT_SCHEMA_ID,
    SUPERVISOR_CHECKPOINT_SCHEMA_VERSION,
    SUPERVISOR_FAILURE_DIGEST_FIELD,
    SUPERVISOR_FAILURE_SCHEMA_ID,
    SUPERVISOR_FAILURE_SCHEMA_VERSION,
    SUPERVISOR_STATUSES,
    TOTAL_CYCLES,
)
from ..v31_outcome_capture_v2 import verify_outcome_clock_policy
from ..v31_sentiment_native_projection_v2 import (
    V31_NATIVE_SENTIMENT_AXES,
    verify_v31_native_sentiment_source_registry,
)
from ..v31_run_genesis import (
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_SCHEMA_ID,
)
from .v31_application_authority_projection_v2 import (
    V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS,
    V31_FULL_LOADER_CHAIN_KEYS,
    V31ApplicationAuthorityProjectionError,
    project_v31_application_authority_chain_v2,
)
from .v31_successor_qualification_v2 import (
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    MONITOR_QUALIFICATION_SCHEMA_ID,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
    SOURCE_QUALIFICATION_SCHEMA_ID,
    verify_successor_monitor_qualification_v2,
    verify_successor_public_source_qualification_v2,
)
from .v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    CODEX_QUALIFICATION_V3_SCHEMA_ID,
    verify_successor_codex_durable_qualification_v3,
)
from .v311_fresh_process_trace_v2 import (
    FRESH_PROCESS_TRACE_DIGEST_FIELD,
    FRESH_PROCESS_TRACE_SCHEMA_ID,
    V311FreshProcessTraceV2Error,
    verify_v311_fresh_process_trace_receipt_v2,
)
from .v311_qualification_retirement_v2 import (
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_SCHEMA_ID,
    V311QualificationRetirementV2Error,
    verify_v311_qualification_retirement_receipt_v2,
)
from .v311_successor_user_approval_v2 import (
    SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
    SUCCESSOR_USER_APPROVAL_PATH,
    SUCCESSOR_USER_APPROVAL_SCHEMA_ID,
    V311SuccessorUserApprovalV2Error,
    verify_v311_successor_user_approval_receipt_v2,
)
from .v311_qualification_genesis_v2 import (
    V311QualificationGenesisV2Error,
    verify_v311_qualification_run_genesis_v2,
)


class V311SuccessorAuthorityEnvelopeV2Error(ValueError):
    """A successor envelope is incomplete, mutable, or permission-expanding."""


ENVELOPE_SCHEMA_ID = "theory_paper_v311_successor_authority_envelope_v2"
ENVELOPE_SCHEMA_VERSION = "2.0.0"
ENVELOPE_DIGEST_FIELD = "successor_authority_envelope_digest"

SUPERVISOR_POLICY_SCHEMA_ID = (
    "theory_paper_v311_successor_supervisor_policy_v2"
)
SUPERVISOR_POLICY_SCHEMA_VERSION = "2.0.0"
SUPERVISOR_POLICY_DIGEST_FIELD = "supervisor_policy_digest"

RUNTIME_CLOSURE_RECEIPT_SCHEMA_ID = (
    "theory_paper_v311_successor_runtime_closure_receipt_v2"
)
RUNTIME_CLOSURE_RECEIPT_SCHEMA_VERSION = "2.0.0"
RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD = "runtime_closure_receipt_digest"

V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH = (
    "config/theory_paper_v31.current_research_authority.v3.json"
)
V311_TARGET_ACTIVE_AUTHORITY_PATH = (
    "config/theory_paper_v31.current_research_authority.v4.json"
)
# Compatibility name for callers preparing the first (qualification) phase.
V311_STANDARD_ACTIVE_AUTHORITY_PATH = V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH
V311_THEORY_ADDENDUM_PATH = "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md"
V311_LEGACY_RUN_ID = "v31-prospective-btcusdt-20260806t183742z"
V311_LEGACY_RUNTIME_PATH_COUNT = 74

V311_FRESH_QUALIFICATION_KEYS = (
    "public_source",
    "codex_durable_delivery",
    "outcome_monitor",
)
V311_AUXILIARY_DOCUMENT_KEYS = (
    "clock_policy",
    "supervisor_policy",
    "runtime_closure",
    "sentiment_source_registry",
    "association_preregistration",
    "evaluation_contract",
)

V311_FULL_LOADER_RESULT_KEYS = frozenset(
    {
        "envelope",
        "legacy_active_chain",
        "legacy_failure_evidence",
        "qualification_v3_chain",
        "qualification_run_genesis",
        "target_v4_chain",
        "theory_addendum_binding",
        "successor_user_approval",
        "clock_policy",
        "supervisor_policy",
        "runtime_closure",
        "sentiment_source_registry",
        "association_preregistration",
        "evaluation_contract",
        "successor_qualifications",
        "qualification_retirement",
    }
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
_GATE_IDS = tuple(f"Q{index}" for index in range(9))
_DOCUMENT_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_ADDENDUM_BINDING_FIELDS = frozenset(
    {"path", "version", "review_status", "physical_sha256"}
)
_LEGACY_FAILURE_EVIDENCE_KEYS = frozenset(
    {
        "research_checkpoint",
        "monitor_checkpoint",
        "monitor_failure",
        "resolution_attempt",
        "bindings",
    }
)
_LEGACY_FAILURE_BINDING_KEYS = (
    "research_checkpoint",
    "monitor_checkpoint",
    "monitor_failure",
    "resolution_attempt",
)
_STANDARD_DOCUMENT_SPECS = {
    "theory_approval": (
        "theory_paper_v31_user_approval_receipt",
        "approval_receipt_digest",
    ),
    "experiment_contract": (
        "theory_paper_v2_v31_minimal_experiment_contract",
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
_AUXILIARY_DOCUMENT_SPECS = {
    "clock_policy": (
        "theory_paper_v31_outcome_clock_policy_v2",
        "clock_policy_digest",
    ),
    "supervisor_policy": (
        SUPERVISOR_POLICY_SCHEMA_ID,
        SUPERVISOR_POLICY_DIGEST_FIELD,
    ),
    "runtime_closure": (
        RUNTIME_CLOSURE_RECEIPT_SCHEMA_ID,
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
_QUALIFICATION_SPECS = {
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
_EXECUTION_BOUNDARY = {
    "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
    "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
    "external_execution_authority": "NONE_LOCAL_SIMULATION",
    "executable": False,
    "account_access": False,
    "paper_trading": False,
    "live_trading": False,
    "order_submission": False,
    "credential_access": False,
    "funds_access": False,
    "portfolio_mutation": False,
}


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return value


def _safe_id(value: Any, code: str) -> str:
    result = _text(value, code)
    if _SAFE_ID.fullmatch(result) is None:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return result


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return value


def _time(value: Any, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != text:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return normalized


def _relative_path(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.as_posix() != text
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return text


def _canonical_physical_sha256(document: Mapping[str, Any]) -> str:
    try:
        return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()
    except (TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_DOCUMENT_NOT_CANONICAL"
        ) from exc


def _document_binding(
    value: Any,
    *,
    document: Mapping[str, Any],
    expected_schema_id: str,
    expected_digest_field: str,
    code: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _DOCUMENT_BINDING_FIELDS:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    result = {
        "path": _relative_path(value.get("path"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    try:
        semantic_digest = verify_self_digest(document, expected_digest_field)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc
    if (
        document.get("schema_id") != expected_schema_id
        or result["schema_id"] != expected_schema_id
        or result["digest_field"] != expected_digest_field
        or result["semantic_digest"] != semantic_digest
        or result["physical_sha256"] != _canonical_physical_sha256(document)
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return result


def _addendum_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _ADDENDUM_BINDING_FIELDS:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_ADDENDUM_BINDING_INVALID"
        )
    result = {
        "path": _relative_path(
            value.get("path"), "V311_ENVELOPE_ADDENDUM_BINDING_INVALID"
        ),
        "version": _text(
            value.get("version"), "V311_ENVELOPE_ADDENDUM_BINDING_INVALID"
        ),
        "review_status": _text(
            value.get("review_status"),
            "V311_ENVELOPE_ADDENDUM_BINDING_INVALID",
        ),
        "physical_sha256": _digest(
            value.get("physical_sha256"),
            "V311_ENVELOPE_ADDENDUM_BINDING_INVALID",
        ),
    }
    if (
        result["path"] != V311_THEORY_ADDENDUM_PATH
        or result["version"] != "3.1.1"
        or result["review_status"] != "FROZEN_APPROVED_SUCCESSOR"
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_ADDENDUM_BINDING_INVALID"
        )
    return result


def _verify_boundary(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or dict(value) != _EXECUTION_BOUNDARY:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return dict(_EXECUTION_BOUNDARY)


def build_v311_supervisor_policy_v2() -> dict[str, Any]:
    """Freeze the already-implemented supervisor ordering without authority."""

    document = {
        "schema_id": SUPERVISOR_POLICY_SCHEMA_ID,
        "schema_version": SUPERVISOR_POLICY_SCHEMA_VERSION,
        "total_cycles": TOTAL_CYCLES,
        "supervisor_contracts": {
            "checkpoint": {
                "schema_id": SUPERVISOR_CHECKPOINT_SCHEMA_ID,
                "schema_version": SUPERVISOR_CHECKPOINT_SCHEMA_VERSION,
                "digest_field": SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
            },
            "cycle_permit": {
                "schema_id": CYCLE_PERMIT_SCHEMA_ID,
                "schema_version": CYCLE_PERMIT_SCHEMA_VERSION,
                "digest_field": CYCLE_PERMIT_DIGEST_FIELD,
            },
            "commit_intent": {
                "schema_id": COMMIT_INTENT_SCHEMA_ID,
                "schema_version": COMMIT_INTENT_SCHEMA_VERSION,
                "digest_field": COMMIT_INTENT_DIGEST_FIELD,
            },
            "failure": {
                "schema_id": SUPERVISOR_FAILURE_SCHEMA_ID,
                "schema_version": SUPERVISOR_FAILURE_SCHEMA_VERSION,
                "digest_field": SUPERVISOR_FAILURE_DIGEST_FIELD,
            },
        },
        "statuses": sorted(SUPERVISOR_STATUSES),
        "permitted_operations": list(PERMITTED_OPERATIONS),
        "ordering_invariants": [
            "PREVIOUS_DURABLE_OUTCOME_REQUIRED_BEFORE_NEXT_CYCLE_PERMIT",
            "SOURCE_QUALIFICATION_PRECEDES_FORMAL_PREPARE",
            "ONE_AGENT_ATTEMPT_PER_STAGE",
            "COMMIT_INTENT_PRECEDES_ACCEPTED_RESEARCH_STATE_AND_MONITOR_PLAN",
            "ONE_STATE_CHANGE_BOUNDARY_PER_WAKE",
            "FAILED_MONITOR_OR_SUPERVISOR_BLOCKS_ALL_FUTURE_CYCLES",
            "TERMINAL_REQUIRES_EIGHT_ACCEPTED_AND_EIGHT_RESOLVED_OUTCOMES",
        ],
        "recovery_policy": {
            "reserved_agent_attempt": "LOCAL_DURABLE_REPLAY_ONLY_NO_REINVOCATION",
            "reserved_commit": "DETERMINISTIC_COMMIT_TAIL_ONLY",
            "reserved_outcome_attempt": "LOCAL_RAW_OR_FAILURE_REPLAY_ONLY_NO_REFETCH",
        },
        "authority_boundary": dict(_EXECUTION_BOUNDARY),
    }
    return self_digest(document, SUPERVISOR_POLICY_DIGEST_FIELD)


def verify_v311_supervisor_policy_v2(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, SUPERVISOR_POLICY_DIGEST_FIELD)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_SUPERVISOR_POLICY_INVALID"
        ) from exc
    expected = build_v311_supervisor_policy_v2()
    if dict(document) != expected or supplied != expected[SUPERVISOR_POLICY_DIGEST_FIELD]:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_SUPERVISOR_POLICY_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _runtime_paths(
    values: Any, *, code: str, allow_empty: bool = False
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    try:
        rows = tuple(values)
    except TypeError as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc
    if (
        (not allow_empty and not rows)
        or len(rows) != len(set(rows))
        or tuple(sorted(rows)) != rows
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    for row in rows:
        path = _relative_path(row, code)
        if PurePosixPath(path).suffix != ".py":
            raise V311SuccessorAuthorityEnvelopeV2Error(code)
    return rows


def build_v311_runtime_closure_receipt_v2(
    *,
    run_scope_id: str,
    frozen_at: str,
    production_root_paths: Sequence[str],
    fresh_process_trace: Mapping[str, Any],
    fresh_process_trace_binding: Mapping[str, Any],
    frozen_bindings: Mapping[str, str],
) -> dict[str, Any]:
    """Bind static closure bytes to a separately sealed observed trace."""

    run_id = _safe_id(run_scope_id, "V311_RUNTIME_CLOSURE_RUN_ID_INVALID")
    frozen = _time(frozen_at, "V311_RUNTIME_CLOSURE_TIME_INVALID")
    roots = _runtime_paths(
        production_root_paths, code="V311_RUNTIME_CLOSURE_ROOTS_INVALID"
    )
    try:
        trace_digest = verify_v311_fresh_process_trace_receipt_v2(
            fresh_process_trace
        )
    except V311FreshProcessTraceV2Error as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_FRESH_TRACE_INVALID"
        ) from exc
    if tuple(fresh_process_trace.get("production_root_paths", ())) != roots:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_FRESH_TRACE_ROOT_MISMATCH"
        )
    if frozen < _time(
        fresh_process_trace.get("completed_at"),
        "V311_RUNTIME_CLOSURE_FRESH_TRACE_TIME_INVALID",
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_PRECEDES_FRESH_TRACE"
        )
    traces = _runtime_paths(
        fresh_process_trace.get("observed_project_python_paths"),
        code="V311_RUNTIME_CLOSURE_TRACE_INVALID",
    )
    trace_binding = _document_binding(
        fresh_process_trace_binding,
        document=fresh_process_trace,
        expected_schema_id=FRESH_PROCESS_TRACE_SCHEMA_ID,
        expected_digest_field=FRESH_PROCESS_TRACE_DIGEST_FIELD,
        code="V311_RUNTIME_CLOSURE_FRESH_TRACE_BINDING_INVALID",
    )
    if trace_binding["semantic_digest"] != trace_digest:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_FRESH_TRACE_BINDING_INVALID"
        )
    if not set(roots).issubset(traces):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_TRACE_ROOT_MISSING"
        )
    if (
        not isinstance(frozen_bindings, Mapping)
        or not frozen_bindings
        or tuple(frozen_bindings) != tuple(sorted(frozen_bindings))
        or not set(traces).issubset(frozen_bindings)
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_BINDINGS_INVALID"
        )
    normalized_bindings: dict[str, str] = {}
    for path, value in frozen_bindings.items():
        relative = _relative_path(path, "V311_RUNTIME_CLOSURE_BINDINGS_INVALID")
        if PurePosixPath(relative).suffix != ".py":
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_RUNTIME_CLOSURE_BINDINGS_INVALID"
            )
        normalized_bindings[relative] = _digest(
            value, "V311_RUNTIME_CLOSURE_BINDINGS_INVALID"
        )
    document = {
        "schema_id": RUNTIME_CLOSURE_RECEIPT_SCHEMA_ID,
        "schema_version": RUNTIME_CLOSURE_RECEIPT_SCHEMA_VERSION,
        "run_scope_id": run_id,
        "frozen_at": frozen_at,
        "production_root_paths": list(roots),
        "fresh_process_trace_receipt": copy.deepcopy(
            dict(fresh_process_trace)
        ),
        "fresh_process_trace_binding": trace_binding,
        "fresh_process_trace_digest": trace_digest,
        "fresh_process_trace_paths": list(traces),
        "frozen_bindings": normalized_bindings,
        "path_count": len(normalized_bindings),
        "bindings_digest": canonical_digest(normalized_bindings),
        "closure_policy": {
            "static_local_import_recursion": True,
            "package_initializers_included": True,
            "fresh_process_trace_union": True,
            "trace_evidence_level": "OBSERVED_FRESH_CHILD_PROCESS",
            "dynamic_imports": "REJECTED",
            "symlinks": "REJECTED",
            "path_escape": "REJECTED",
            "missing_or_drifted_byte": "FAIL_CLOSED",
        },
        "authority_boundary": dict(_EXECUTION_BOUNDARY),
    }
    return self_digest(document, RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD)


def verify_v311_runtime_closure_receipt_v2(
    document: Mapping[str, Any],
) -> str:
    try:
        supplied = verify_self_digest(
            document, RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD
        )
        rebuilt = build_v311_runtime_closure_receipt_v2(
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
            production_root_paths=document["production_root_paths"],
            fresh_process_trace=document["fresh_process_trace_receipt"],
            fresh_process_trace_binding=document[
                "fresh_process_trace_binding"
            ],
            frozen_bindings=document["frozen_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311SuccessorAuthorityEnvelopeV2Error):
            raise
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_RECEIPT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD]:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_RUNTIME_CLOSURE_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _validate_loaded_chain(value: Any, *, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != V31_FULL_LOADER_CHAIN_KEYS:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    try:
        project_v31_application_authority_chain_v2(value)
    except V31ApplicationAuthorityProjectionError as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(code) from exc
    return value


def _legacy_failure_evidence(
    value: Any, *, legacy_chain: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != _LEGACY_FAILURE_EVIDENCE_KEYS:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_EVIDENCE_INVALID"
        )
    documents = {
        name: value.get(name) for name in _LEGACY_FAILURE_BINDING_KEYS
    }
    if any(not isinstance(document, Mapping) for document in documents.values()):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_EVIDENCE_INVALID"
        )
    research = documents["research_checkpoint"]
    monitor = documents["monitor_checkpoint"]
    failure = documents["monitor_failure"]
    attempt = documents["resolution_attempt"]
    try:
        research_digest = verify_self_digest(research, "checkpoint_digest")
        monitor_digest = verify_self_digest(monitor, "checkpoint_digest")
        failure_digest = verify_self_digest(failure, "failure_digest")
        attempt_digest = verify_self_digest(attempt, "monitor_attempt_digest")
    except (TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_DIGEST_INVALID"
        ) from exc
    authority = legacy_chain["authority"]
    contract = legacy_chain["experiment_contract"]
    if (
        authority.get("authorized_run_id") != V311_LEGACY_RUN_ID
        or research.get("run_id") != V311_LEGACY_RUN_ID
        or research.get("status") != "READY_FOR_CYCLE"
        or research.get("completed_cycles") != 1
        or research.get("next_cycle_index") != 2
        or research.get("resume_allowed") is not True
        or research.get("current_authority_digest")
        != authority.get("authority_digest")
        or monitor.get("run_id") != V311_LEGACY_RUN_ID
        or monitor.get("status") != "FAILED_CLOSED"
        or monitor.get("resume_allowed") is not False
        or monitor.get("failure_digest") != failure_digest
        or monitor.get("experiment_contract_digest")
        != contract.get("experiment_contract_digest")
        or len(monitor.get("plan_bindings", [])) != 1
        or len(monitor.get("resolution_attempt_bindings", [])) != 1
        or monitor.get("outcome_bindings") != []
        or failure.get("run_id") != V311_LEGACY_RUN_ID
        or failure.get("resume_allowed") is not False
        or failure.get("planned_cycles") != 1
        or failure.get("reserved_attempts") != 1
        or failure.get("resolved_cycles") != 0
        or attempt.get("run_id") != V311_LEGACY_RUN_ID
        or attempt.get("cycle_index") != 1
        or attempt.get("attempt_number") != 1
        or attempt.get("retry_allowed") is not False
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_LINEAGE_INVALID"
        )
    bindings = value.get("bindings")
    if not isinstance(bindings, Mapping) or tuple(bindings) != _LEGACY_FAILURE_BINDING_KEYS:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_FAILURE_BINDINGS_INVALID"
        )
    digests = {
        "research_checkpoint": research_digest,
        "monitor_checkpoint": monitor_digest,
        "monitor_failure": failure_digest,
        "resolution_attempt": attempt_digest,
    }
    schemas = {
        "research_checkpoint": (
            "theory_paper_v31_research_checkpoint",
            "checkpoint_digest",
        ),
        "monitor_checkpoint": (
            "theory_paper_v31_monitor_checkpoint",
            "checkpoint_digest",
        ),
        "monitor_failure": (
            "theory_paper_v31_monitor_failure",
            "failure_digest",
        ),
        "resolution_attempt": (
            "theory_paper_v31_monitor_resolution_attempt",
            "monitor_attempt_digest",
        ),
    }
    normalized_bindings: dict[str, dict[str, str]] = {}
    for name in _LEGACY_FAILURE_BINDING_KEYS:
        schema_id, digest_field = schemas[name]
        normalized = _document_binding(
            bindings[name],
            document=documents[name],
            expected_schema_id=schema_id,
            expected_digest_field=digest_field,
            code="V311_LEGACY_FAILURE_BINDINGS_INVALID",
        )
        if normalized["semantic_digest"] != digests[name]:
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_LEGACY_FAILURE_BINDINGS_INVALID"
            )
        normalized_bindings[name] = normalized
    return {name: dict(documents[name]) for name in documents}, normalized_bindings


def _normalize_standard_bindings(
    value: Any,
    *,
    standard_chain: Mapping[str, Any],
    expected_active_authority_path: str,
    code: str,
) -> dict[str, dict[str, str]]:
    if (
        not isinstance(value, Mapping)
        or tuple(value) != V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            code
        )
    normalized: dict[str, dict[str, str]] = {}
    for name in V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS:
        schema_id, digest_field = _STANDARD_DOCUMENT_SPECS[name]
        normalized[name] = _document_binding(
            value[name],
            document=standard_chain[name],
            expected_schema_id=schema_id,
            expected_digest_field=digest_field,
            code=code,
        )
    if normalized["authority"]["path"] != expected_active_authority_path:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            code
        )
    return normalized


def _normalize_document_group(
    bindings: Any,
    *,
    documents: Mapping[str, Mapping[str, Any]],
    specs: Mapping[str, tuple[str, str]],
    expected_order: tuple[str, ...],
    code: str,
) -> dict[str, dict[str, str]]:
    if not isinstance(bindings, Mapping) or tuple(bindings) != expected_order:
        raise V311SuccessorAuthorityEnvelopeV2Error(code)
    normalized: dict[str, dict[str, str]] = {}
    for name in expected_order:
        schema_id, digest_field = specs[name]
        normalized[name] = _document_binding(
            bindings[name],
            document=documents[name],
            expected_schema_id=schema_id,
            expected_digest_field=digest_field,
            code=code,
        )
    return normalized


def build_v311_successor_authority_envelope_v2(
    *,
    envelope_id: str,
    created_at: str,
    legacy_active_chain: Mapping[str, Any],
    legacy_failure_evidence: Mapping[str, Any],
    qualification_v3_chain: Mapping[str, Any],
    qualification_v3_document_bindings: Mapping[str, Mapping[str, Any]],
    qualification_run_root_ref: str,
    qualification_run_genesis: Mapping[str, Any],
    qualification_run_genesis_binding: Mapping[str, Any],
    target_v4_chain: Mapping[str, Any],
    target_v4_document_bindings: Mapping[str, Mapping[str, Any]],
    theory_addendum_binding: Mapping[str, Any],
    successor_user_approval: Mapping[str, Any],
    successor_user_approval_binding: Mapping[str, Any],
    clock_policy: Mapping[str, Any],
    supervisor_policy: Mapping[str, Any],
    runtime_closure: Mapping[str, Any],
    sentiment_source_registry: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
    evaluation_contract: Mapping[str, Any],
    auxiliary_document_bindings: Mapping[str, Mapping[str, Any]],
    successor_qualifications: Mapping[str, Mapping[str, Any]],
    successor_qualification_bindings: Mapping[str, Mapping[str, Any]],
    qualification_retirement: Mapping[str, Any],
    qualification_retirement_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the immutable successor envelope from already-sealed documents."""

    envelope = _safe_id(envelope_id, "V311_ENVELOPE_ID_INVALID")
    created = _time(created_at, "V311_ENVELOPE_CREATED_AT_INVALID")
    legacy_chain = _validate_loaded_chain(
        legacy_active_chain, code="V311_LEGACY_ACTIVE_CHAIN_INVALID"
    )
    qualification_chain = _validate_loaded_chain(
        qualification_v3_chain, code="V311_QUALIFICATION_V3_CHAIN_INVALID"
    )
    target_chain = _validate_loaded_chain(
        target_v4_chain, code="V311_TARGET_V4_CHAIN_INVALID"
    )
    legacy_documents, legacy_bindings = _legacy_failure_evidence(
        legacy_failure_evidence, legacy_chain=legacy_chain
    )
    qualification_projection = project_v31_application_authority_chain_v2(
        qualification_chain
    )
    target_projection = project_v31_application_authority_chain_v2(
        target_chain
    )
    qualification_authority_bindings = _normalize_standard_bindings(
        qualification_v3_document_bindings,
        standard_chain=qualification_chain,
        expected_active_authority_path=V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
        code="V311_QUALIFICATION_V3_DOCUMENT_BINDINGS_INVALID",
    )
    normalized_qualification_run_root = _relative_path(
        qualification_run_root_ref,
        "V311_QUALIFICATION_RUN_ROOT_REF_INVALID",
    )
    try:
        genesis_evidence = verify_v311_qualification_run_genesis_v2(
            run_genesis=qualification_run_genesis,
            qualification_v3_chain=qualification_chain,
            qualification_v3_document_bindings=qualification_authority_bindings,
        )
    except V311QualificationGenesisV2Error as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RUN_GENESIS_INVALID"
        ) from exc
    genesis_binding = _document_binding(
        qualification_run_genesis_binding,
        document=qualification_run_genesis,
        expected_schema_id=RUN_GENESIS_SCHEMA_ID,
        expected_digest_field=RUN_GENESIS_DIGEST_FIELD,
        code="V311_QUALIFICATION_RUN_GENESIS_BINDING_INVALID",
    )
    if (
        genesis_binding["semantic_digest"]
        != genesis_evidence["run_genesis_digest"]
        or genesis_binding["path"]
        != f"{normalized_qualification_run_root}/genesis/run-genesis.json"
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RUN_GENESIS_BINDING_INVALID"
        )
    genesis_authority_copy_binding = genesis_evidence[
        "authority_copy_binding"
    ]
    target_bindings = _normalize_standard_bindings(
        target_v4_document_bindings,
        standard_chain=target_chain,
        expected_active_authority_path=V311_TARGET_ACTIVE_AUTHORITY_PATH,
        code="V311_TARGET_V4_DOCUMENT_BINDINGS_INVALID",
    )
    addendum = _addendum_binding(theory_addendum_binding)
    try:
        successor_approval_digest = (
            verify_v311_successor_user_approval_receipt_v2(
                successor_user_approval
            )
        )
    except V311SuccessorUserApprovalV2Error as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_SUCCESSOR_USER_APPROVAL_INVALID"
        ) from exc
    successor_approval_binding = _document_binding(
        successor_user_approval_binding,
        document=successor_user_approval,
        expected_schema_id=SUCCESSOR_USER_APPROVAL_SCHEMA_ID,
        expected_digest_field=SUCCESSOR_USER_APPROVAL_DIGEST_FIELD,
        code="V311_SUCCESSOR_USER_APPROVAL_BINDING_INVALID",
    )
    if (
        successor_approval_binding["path"] != SUCCESSOR_USER_APPROVAL_PATH
        or successor_approval_binding["semantic_digest"]
        != successor_approval_digest
        or successor_user_approval.get("theory_addendum_binding") != addendum
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_SUCCESSOR_USER_APPROVAL_BINDING_INVALID"
        )

    try:
        clock_digest = verify_outcome_clock_policy(clock_policy)
        supervisor_digest = verify_v311_supervisor_policy_v2(supervisor_policy)
        closure_digest = verify_v311_runtime_closure_receipt_v2(runtime_closure)
        sentiment_digest = verify_v31_native_sentiment_source_registry(
            sentiment_source_registry
        )
        association_digest = verify_v31_association_preregistration_v2(
            association_preregistration
        )
        evaluation_digest = verify_v31_evaluation_contract_v2(
            evaluation_contract, association_preregistration
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, V311SuccessorAuthorityEnvelopeV2Error):
            raise
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_AUXILIARY_CONTRACT_INVALID"
        ) from exc
    auxiliary_documents = {
        "clock_policy": clock_policy,
        "supervisor_policy": supervisor_policy,
        "runtime_closure": runtime_closure,
        "sentiment_source_registry": sentiment_source_registry,
        "association_preregistration": association_preregistration,
        "evaluation_contract": evaluation_contract,
    }
    auxiliary_bindings = _normalize_document_group(
        auxiliary_document_bindings,
        documents=auxiliary_documents,
        specs=_AUXILIARY_DOCUMENT_SPECS,
        expected_order=V311_AUXILIARY_DOCUMENT_KEYS,
        code="V311_AUXILIARY_DOCUMENT_BINDINGS_INVALID",
    )
    expected_auxiliary_digests = {
        "clock_policy": clock_digest,
        "supervisor_policy": supervisor_digest,
        "runtime_closure": closure_digest,
        "sentiment_source_registry": sentiment_digest,
        "association_preregistration": association_digest,
        "evaluation_contract": evaluation_digest,
    }
    if any(
        auxiliary_bindings[name]["semantic_digest"] != digest
        for name, digest in expected_auxiliary_digests.items()
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_AUXILIARY_DOCUMENT_DIGEST_MISMATCH"
        )

    if (
        not isinstance(successor_qualifications, Mapping)
        or tuple(successor_qualifications) != V311_FRESH_QUALIFICATION_KEYS
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_FRESH_QUALIFICATION_SET_INVALID"
        )
    qualifications = {
        name: successor_qualifications[name]
        for name in V311_FRESH_QUALIFICATION_KEYS
    }
    try:
        qualification_digests = {
            "public_source": verify_successor_public_source_qualification_v2(
                qualifications["public_source"]
            ),
            "codex_durable_delivery": verify_successor_codex_durable_qualification_v3(
                qualifications["codex_durable_delivery"]
            ),
            "outcome_monitor": verify_successor_monitor_qualification_v2(
                qualifications["outcome_monitor"]
            ),
        }
    except (TypeError, ValueError) as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_FRESH_QUALIFICATION_INVALID"
        ) from exc
    fresh_qualification_bindings = _normalize_document_group(
        successor_qualification_bindings,
        documents=qualifications,
        specs=_QUALIFICATION_SPECS,
        expected_order=V311_FRESH_QUALIFICATION_KEYS,
        code="V311_FRESH_QUALIFICATION_BINDINGS_INVALID",
    )
    if any(
        fresh_qualification_bindings[name]["semantic_digest"] != digest
        for name, digest in qualification_digests.items()
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_FRESH_QUALIFICATION_DIGEST_MISMATCH"
        )
    try:
        retirement_digest = verify_v311_qualification_retirement_receipt_v2(
            qualification_retirement
        )
    except V311QualificationRetirementV2Error as exc:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RETIREMENT_INVALID"
        ) from exc
    retirement_binding = _document_binding(
        qualification_retirement_binding,
        document=qualification_retirement,
        expected_schema_id=QUALIFICATION_RETIREMENT_SCHEMA_ID,
        expected_digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        code="V311_QUALIFICATION_RETIREMENT_BINDING_INVALID",
    )
    if retirement_binding["semantic_digest"] != retirement_digest:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RETIREMENT_BINDING_INVALID"
        )

    predecessor_authority = legacy_chain["authority"]
    predecessor_failure = legacy_documents["monitor_failure"]
    qualification_authority = qualification_projection["authority"]
    target_authority = target_projection["authority"]
    qualification_run_id = _safe_id(
        qualification_authority.get("authorized_run_id"),
        "V311_QUALIFICATION_RUN_ID_INVALID",
    )
    target_run_id = _safe_id(
        target_authority.get("authorized_run_id"),
        "V311_TARGET_RUN_ID_INVALID",
    )
    qualification_authority_digest = _digest(
        qualification_authority.get("authority_digest"),
        "V311_QUALIFICATION_V3_AUTHORITY_DIGEST_INVALID",
    )
    target_authority_digest = _digest(
        target_authority.get("authority_digest"),
        "V311_TARGET_V4_AUTHORITY_DIGEST_INVALID",
    )
    qualification_authority_recorded = _time(
        qualification_authority.get("recorded_at"),
        "V311_QUALIFICATION_V3_AUTHORITY_TIME_INVALID",
    )
    successor_approved_at = _time(
        successor_user_approval.get("approved_at"),
        "V311_SUCCESSOR_USER_APPROVAL_TIME_INVALID",
    )
    target_authority_recorded = _time(
        target_authority.get("recorded_at"),
        "V311_TARGET_V4_AUTHORITY_TIME_INVALID",
    )
    failed_at = _time(
        predecessor_failure.get("occurred_at"),
        "V311_LEGACY_FAILURE_TIME_INVALID",
    )
    qualified_times = [
        _time(
            qualifications[name].get("qualified_at"),
            "V311_FRESH_QUALIFICATION_TIME_INVALID",
        )
        for name in V311_FRESH_QUALIFICATION_KEYS
    ]
    source_expires = _time(
        qualifications["public_source"].get("expires_at"),
        "V311_SOURCE_QUALIFICATION_EXPIRY_INVALID",
    )
    retired_at = _time(
        qualification_retirement.get("retired_at"),
        "V311_QUALIFICATION_RETIREMENT_TIME_INVALID",
    )
    if (
        qualification_run_id == V311_LEGACY_RUN_ID
        or target_run_id in {V311_LEGACY_RUN_ID, qualification_run_id}
        or target_authority_digest == qualification_authority_digest
        or target_authority.get("authority_id")
        == qualification_authority.get("authority_id")
        or target_chain["experiment_contract"].get(
            "experiment_contract_digest"
        )
        == qualification_chain["experiment_contract"].get(
            "experiment_contract_digest"
        )
        or predecessor_authority.get("authorized_run_id") != V311_LEGACY_RUN_ID
        or qualification_authority_recorded <= failed_at
        or qualification_authority_recorded <= successor_approved_at
        or target_authority_recorded <= max(qualified_times)
        or target_authority_recorded <= retired_at
        or created < target_authority_recorded
        or created > source_expires
        or runtime_closure.get("run_scope_id") != target_run_id
        or association_preregistration.get("run_scope_id") != target_run_id
        or evaluation_contract.get("run_scope_id") != target_run_id
        or evaluation_contract.get("association_preregistration_digest")
        != association_digest
        or sentiment_source_registry.get("axis_count") != 12
        or tuple(
            row.get("axis_id")
            for row in sentiment_source_registry.get("axes", [])
            if isinstance(row, Mapping)
        )
        != V31_NATIVE_SENTIMENT_AXES
        or qualifications["codex_durable_delivery"].get(
            "source_qualification_v2_digest"
        )
        != qualification_digests["public_source"]
        or qualifications["codex_durable_delivery"].get("cycle_index") != 1
        or qualifications["outcome_monitor"].get("clock_policy")
        != dict(clock_policy)
        or qualifications["outcome_monitor"].get("raw_first_probe", {}).get(
            "clock_policy_digest"
        )
        != clock_digest
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_SUCCESSOR_CROSS_BINDING_INVALID"
        )
    if normalized_qualification_run_root != (
        f"agent-cluster/experiments/{qualification_run_id}"
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RUN_ROOT_REF_INVALID"
        )
    if retirement_binding["path"] != (
        f"{normalized_qualification_run_root}/qualification-retirement.v2.json"
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RETIREMENT_PATH_INVALID"
        )
    for qualification in qualifications.values():
        if (
            qualification.get("run_id") != qualification_run_id
            or qualification.get("predecessor_run_id") != V311_LEGACY_RUN_ID
            or qualification.get("authority_digest")
            != qualification_authority_digest
            or qualification.get("authority_recorded_at")
            != qualification_authority.get("recorded_at")
            or qualification.get("authority_binding")
            != genesis_authority_copy_binding
        ):
            raise V311SuccessorAuthorityEnvelopeV2Error(
                "V311_SUCCESSOR_QUALIFICATION_AUTHORITY_MISMATCH"
            )

    legacy_receipts = legacy_chain["qualification_receipts"]
    qualification_receipts = qualification_chain["qualification_receipts"]
    target_receipts = target_chain["qualification_receipts"]
    if (
        tuple(legacy_receipts) != _GATE_IDS
        or tuple(qualification_receipts) != _GATE_IDS
        or tuple(target_receipts) != _GATE_IDS
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_Q0_Q8_RECEIPT_SET_INVALID"
        )
    if (
        qualification_retirement.get("qualification_run_id")
        != qualification_run_id
        or qualification_retirement.get("target_run_id") != target_run_id
        or qualification_retirement.get("predecessor_run_id")
        != V311_LEGACY_RUN_ID
        or qualification_retirement.get("qualification_authority_digest")
        != qualification_authority_digest
        or qualification_retirement.get(
            "standard_qualification_authority_binding"
        )
        != qualification_authority_bindings["authority"]
        or qualification_retirement.get("qualification_run_genesis_binding")
        != genesis_binding
        or qualification_retirement.get("qualification_run_genesis_digest")
        != genesis_evidence["run_genesis_digest"]
        or qualification_retirement.get("genesis_authority_copy_binding")
        != genesis_authority_copy_binding
        or qualification_retirement.get("q0_q8_receipt_digests")
        != {
            gate_id: qualification_receipts[gate_id][
                "qualification_receipt_digest"
            ]
            for gate_id in _GATE_IDS
        }
        or qualification_retirement.get("fresh_qualification_digests")
        != qualification_digests
        or qualification_retirement.get("fresh_qualification_bindings")
        != fresh_qualification_bindings
        or qualification_retirement.get("accepted_cycle_index") != 1
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_QUALIFICATION_RETIREMENT_CROSS_BINDING_INVALID"
        )
    legacy_runtime = legacy_chain["manifest"].get("implementation_bindings")
    if not isinstance(legacy_runtime, Mapping) or len(legacy_runtime) != V311_LEGACY_RUNTIME_PATH_COUNT:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_LEGACY_RUNTIME_BINDING_COUNT_INVALID"
        )

    document = {
        "schema_id": ENVELOPE_SCHEMA_ID,
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "envelope_id": envelope,
        "created_at": created_at,
        "status": "ACTIVE_FROZEN_RESEARCH_SUCCESSOR",
        "qualification_run_id": qualification_run_id,
        "qualification_run_root_ref": normalized_qualification_run_root,
        "target_run_id": target_run_id,
        "predecessor_failure_lineage": {
            "run_id": V311_LEGACY_RUN_ID,
            "active_authority_digest": predecessor_authority[
                "authority_digest"
            ],
            "q0_q8_receipt_digests": {
                gate_id: legacy_receipts[gate_id][
                    "qualification_receipt_digest"
                ]
                for gate_id in _GATE_IDS
            },
            "frozen_runtime_path_count": len(legacy_runtime),
            "frozen_runtime_bindings_digest": canonical_digest(legacy_runtime),
            "research_checkpoint_digest": legacy_documents[
                "research_checkpoint"
            ]["checkpoint_digest"],
            "research_checkpoint_status": "READY_FOR_CYCLE",
            "research_completed_cycles": 1,
            "monitor_checkpoint_digest": legacy_documents[
                "monitor_checkpoint"
            ]["checkpoint_digest"],
            "monitor_checkpoint_status": "FAILED_CLOSED",
            "monitor_failure_digest": predecessor_failure["failure_digest"],
            "monitor_failure_code": predecessor_failure["failure_code"],
            "failed_at": predecessor_failure["occurred_at"],
            "resume_allowed": False,
            "failure_supersedes_research_ready": True,
            "bindings": legacy_bindings,
        },
        "qualification_v3_authority": {
            "authority_digest": qualification_authority_digest,
            "authority_recorded_at": qualification_authority["recorded_at"],
            "authorized_run_id": qualification_run_id,
            "document_bindings": qualification_authority_bindings,
            "q0_q8_receipt_digests": {
                gate_id: qualification_receipts[gate_id][
                    "qualification_receipt_digest"
                ]
                for gate_id in _GATE_IDS
            },
            "scope": "ISOLATED_QUALIFICATION_RUN_ONLY",
            "maximum_accepted_qualification_cycles": 1,
            "accepted_cycles_count_toward_target": False,
            "run_genesis_binding": genesis_binding,
            "run_genesis_digest": genesis_evidence["run_genesis_digest"],
            "genesis_authority_copy_binding": genesis_authority_copy_binding,
        },
        "target_v4_authority": {
            "authority_digest": target_authority_digest,
            "authority_recorded_at": target_authority["recorded_at"],
            "authorized_run_id": target_run_id,
            "document_bindings": target_bindings,
            "q0_q8_receipt_digests": {
                gate_id: target_receipts[gate_id][
                    "qualification_receipt_digest"
                ]
                for gate_id in _GATE_IDS
            },
            "application_projection_keys": list(
                V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
            ),
            "scope": "EIGHT_CYCLE_TARGET_RUN_ONLY",
        },
        "theory_addendum_binding": addendum,
        "successor_user_approval_binding": successor_approval_binding,
        "successor_user_approval_digest": successor_approval_digest,
        "auxiliary_contract_bindings": auxiliary_bindings,
        "fresh_qualification_bindings": fresh_qualification_bindings,
        "fresh_qualification_digests": qualification_digests,
        "qualification_retirement_binding": retirement_binding,
        "qualification_retirement_digest": retirement_digest,
        "immutable_contract": {
            "versioned_parallel_authority": True,
            "historical_v2_chain_mutation": False,
            "historical_run_mutation": False,
            "write_once_documents_required": True,
            "path_containment_required": True,
            "physical_byte_replay_required": True,
            "application_projection_after_full_loader_only": True,
            "application_projection_exact_document_count": 5,
            "qualification_and_target_run_ids_must_differ": True,
            "qualification_cycles_excluded_from_target_counts": True,
            "qualification_retirement_required_before_target_authority": True,
        },
        "claim_boundary": {
            "portfolio": "EXCLUDED_NO_CLAIM",
            "reentry": "EXCLUDED_NO_CLAIM",
            "probability_mode": "ORDINAL_VECTOR_NOT_PROBABILITY",
            "probability_calibration": "NOT_APPLICABLE_ORDINAL_ONLY",
            "predictive_increment": "UNKNOWN_NOT_EVALUATED",
            "cost_after_return": "UNKNOWN_NOT_EVALUATED",
            "cross_regime_generalization": "UNKNOWN_NOT_EVALUATED",
            "local_pass_is_market_validity": False,
            "local_pass_is_profitability": False,
        },
        "authority_boundary": dict(_EXECUTION_BOUNDARY),
    }
    return self_digest(document, ENVELOPE_DIGEST_FIELD)


def verify_v311_successor_authority_envelope_v2(
    document: Mapping[str, Any],
    *,
    legacy_active_chain: Mapping[str, Any],
    legacy_failure_evidence: Mapping[str, Any],
    qualification_v3_chain: Mapping[str, Any],
    qualification_run_genesis: Mapping[str, Any],
    target_v4_chain: Mapping[str, Any],
    theory_addendum_binding: Mapping[str, Any],
    successor_user_approval: Mapping[str, Any],
    clock_policy: Mapping[str, Any],
    supervisor_policy: Mapping[str, Any],
    runtime_closure: Mapping[str, Any],
    sentiment_source_registry: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
    evaluation_contract: Mapping[str, Any],
    successor_qualifications: Mapping[str, Mapping[str, Any]],
    qualification_retirement: Mapping[str, Any],
) -> str:
    """Reconstruct every cross-binding and reject omitted or added fields."""

    if not isinstance(document, Mapping):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_DOCUMENT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, ENVELOPE_DIGEST_FIELD)
        rebuilt = build_v311_successor_authority_envelope_v2(
            envelope_id=document["envelope_id"],
            created_at=document["created_at"],
            legacy_active_chain=legacy_active_chain,
            legacy_failure_evidence=legacy_failure_evidence,
            qualification_v3_chain=qualification_v3_chain,
            qualification_v3_document_bindings=document[
                "qualification_v3_authority"
            ][
                "document_bindings"
            ],
            qualification_run_root_ref=document["qualification_run_root_ref"],
            qualification_run_genesis=qualification_run_genesis,
            qualification_run_genesis_binding=document[
                "qualification_v3_authority"
            ]["run_genesis_binding"],
            target_v4_chain=target_v4_chain,
            target_v4_document_bindings=document["target_v4_authority"][
                "document_bindings"
            ],
            theory_addendum_binding=theory_addendum_binding,
            successor_user_approval=successor_user_approval,
            successor_user_approval_binding=document[
                "successor_user_approval_binding"
            ],
            clock_policy=clock_policy,
            supervisor_policy=supervisor_policy,
            runtime_closure=runtime_closure,
            sentiment_source_registry=sentiment_source_registry,
            association_preregistration=association_preregistration,
            evaluation_contract=evaluation_contract,
            auxiliary_document_bindings=document[
                "auxiliary_contract_bindings"
            ],
            successor_qualifications=successor_qualifications,
            successor_qualification_bindings=document[
                "fresh_qualification_bindings"
            ],
            qualification_retirement=qualification_retirement,
            qualification_retirement_binding=document[
                "qualification_retirement_binding"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311SuccessorAuthorityEnvelopeV2Error):
            raise
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_DOCUMENT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[ENVELOPE_DIGEST_FIELD]:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_ENVELOPE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def project_v311_application_authority_chain_v2(
    loaded_successor_chain: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return exactly five standard documents after full-loader reconstruction."""

    if (
        not isinstance(loaded_successor_chain, Mapping)
        or set(loaded_successor_chain) != V311_FULL_LOADER_RESULT_KEYS
        or not isinstance(
            loaded_successor_chain.get("successor_qualifications"), Mapping
        )
    ):
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_APPLICATION_FULL_LOADER_RESULT_INVALID"
        )
    verify_v311_successor_authority_envelope_v2(
        loaded_successor_chain["envelope"],
        legacy_active_chain=loaded_successor_chain["legacy_active_chain"],
        legacy_failure_evidence=loaded_successor_chain[
            "legacy_failure_evidence"
        ],
        qualification_v3_chain=loaded_successor_chain[
            "qualification_v3_chain"
        ],
        qualification_run_genesis=loaded_successor_chain[
            "qualification_run_genesis"
        ],
        target_v4_chain=loaded_successor_chain["target_v4_chain"],
        theory_addendum_binding=loaded_successor_chain[
            "theory_addendum_binding"
        ],
        successor_user_approval=loaded_successor_chain[
            "successor_user_approval"
        ],
        clock_policy=loaded_successor_chain["clock_policy"],
        supervisor_policy=loaded_successor_chain["supervisor_policy"],
        runtime_closure=loaded_successor_chain["runtime_closure"],
        sentiment_source_registry=loaded_successor_chain[
            "sentiment_source_registry"
        ],
        association_preregistration=loaded_successor_chain[
            "association_preregistration"
        ],
        evaluation_contract=loaded_successor_chain["evaluation_contract"],
        successor_qualifications=loaded_successor_chain[
            "successor_qualifications"
        ],
        qualification_retirement=loaded_successor_chain[
            "qualification_retirement"
        ],
    )
    projected = project_v31_application_authority_chain_v2(
        loaded_successor_chain["target_v4_chain"]
    )
    if tuple(projected) != V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS:
        raise V311SuccessorAuthorityEnvelopeV2Error(
            "V311_APPLICATION_PROJECTION_SHAPE_INVALID"
        )
    return {name: copy.deepcopy(projected[name]) for name in projected}


__all__ = [
    "ENVELOPE_DIGEST_FIELD",
    "ENVELOPE_SCHEMA_ID",
    "RUNTIME_CLOSURE_RECEIPT_DIGEST_FIELD",
    "RUNTIME_CLOSURE_RECEIPT_SCHEMA_ID",
    "SUPERVISOR_POLICY_DIGEST_FIELD",
    "SUPERVISOR_POLICY_SCHEMA_ID",
    "V311_AUXILIARY_DOCUMENT_KEYS",
    "V311_FRESH_QUALIFICATION_KEYS",
    "V311_FULL_LOADER_RESULT_KEYS",
    "V311_LEGACY_RUN_ID",
    "V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH",
    "V311_STANDARD_ACTIVE_AUTHORITY_PATH",
    "V311_TARGET_ACTIVE_AUTHORITY_PATH",
    "V311_THEORY_ADDENDUM_PATH",
    "V311SuccessorAuthorityEnvelopeV2Error",
    "build_v311_runtime_closure_receipt_v2",
    "build_v311_successor_authority_envelope_v2",
    "build_v311_supervisor_policy_v2",
    "project_v311_application_authority_chain_v2",
    "verify_v311_runtime_closure_receipt_v2",
    "verify_v311_successor_authority_envelope_v2",
    "verify_v311_supervisor_policy_v2",
]
