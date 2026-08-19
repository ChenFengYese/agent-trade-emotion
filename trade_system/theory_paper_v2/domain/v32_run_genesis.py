"""Typed, replayable genesis contracts for the sole V3.2 target run.

The contracts in this module grant no authority and perform no filesystem,
clock, network, Agent, account, or order operation.  They bind the five target
authority projection documents, one fully verified cycle-1 timeframe entity,
and immutable revision-zero copies of the dynamic, outcome, and Supervisor
checkpoints.  The current-run pointer is a separate final publication object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_bytes, self_digest, verify_self_digest
from .governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    AUTHORIZATION_RECEIPT_SCHEMA_ID,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    RUNTIME_MANIFEST_SCHEMA_ID,
    TARGET_PROFILE,
    THEORY_APPROVAL_DIGEST_FIELD,
    THEORY_APPROVAL_SCHEMA_ID,
    V32AuthorizationError,
    verify_v32_authority_v1,
    verify_v32_authorization_receipt_v1,
    verify_v32_runtime_manifest,
    verify_v32_theory_approval_receipt_v1,
)
from .governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
    SCHEMA_ID as EXPERIMENT_CONTRACT_SCHEMA_ID,
    TOTAL_ANALYSIS_CYCLES,
    TOTAL_OUTCOME_SCHEDULES,
    V32ExperimentContractError,
    verify_v32_experiment_contract_v1,
)
from .v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID as SUPERVISOR_CHECKPOINT_SCHEMA_ID,
    V32TickSupervisorError,
    verify_v32_tick_supervisor_checkpoint,
)
RUN_GENESIS_SCHEMA_ID = "theory_paper_v32_target_run_genesis_receipt_v1"
RUN_GENESIS_SCHEMA_VERSION = "1.0.0"
RUN_GENESIS_DIGEST_FIELD = "v32_target_run_genesis_digest"
RUN_GENESIS_REF = "genesis/run-genesis.json"

CURRENT_RUN_POINTER_SCHEMA_ID = "theory_paper_v32_current_target_run_pointer_v1"
CURRENT_RUN_POINTER_DIGEST_FIELD = "v32_current_target_run_pointer_digest"

DYNAMIC_CHECKPOINT_SCHEMA_ID = "theory_paper_v32_dynamic_research_checkpoint_v1"
DYNAMIC_CHECKPOINT_DIGEST_FIELD = "dynamic_research_checkpoint_digest"
OUTCOME_CHECKPOINT_SCHEMA_ID = "theory_paper_v32_outcome_tick_checkpoint_v1"
OUTCOME_CHECKPOINT_DIGEST_FIELD = "checkpoint_digest"
TIMEFRAME_GENESIS_SCHEMA_ID = "theory_paper_v32_initial_timeframe_genesis_v1"
TIMEFRAME_DIGEST_FIELD = "initial_timeframe_genesis_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
OPERATION = "RUN_V32_DYNAMIC_AGGRESSIVE_PROCESS_PILOT"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_BINDING_FIELDS = frozenset(
    {"relative_ref", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_SOURCE_ROW_FIELDS = frozenset(
    {
        "role",
        "source_ref",
        "local_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "source_physical_sha256",
        "local_physical_sha256",
        "exact_bytes_copied",
    }
)
_LOCAL_ROW_FIELDS = frozenset(
    {
        "role",
        "local_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
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
_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "created_at",
        "operation",
        "experiment_scope",
        "authority_projection_copies",
        "initial_timeframe_entity",
        "revision_zero_checkpoints",
        "cross_bindings",
        "qualification_boundary_audit_gate",
        "publication_policy",
        "chat_history_is_authority",
        *_BOUNDARY_FIELDS,
        RUN_GENESIS_DIGEST_FIELD,
    }
)
_POINTER_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "status",
        "published_at",
        "run_genesis_binding",
        "experiment_contract_digest",
        "active_authority_digest",
        "single_active_target_run",
        "legacy_run_allowed",
        "first_analysis_permit_status_at_publication",
        "genesis_grants_first_analysis_permit",
        *_BOUNDARY_FIELDS,
        CURRENT_RUN_POINTER_DIGEST_FIELD,
    }
)
_TIMEFRAME_GENESIS_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "created_at",
        "state",
        "first_formal_source_required",
        "market_data_present",
        "market_values_present",
        "market_payload_digest_present",
        "previous_timeframe_digest",
        *_BOUNDARY_FIELDS,
        TIMEFRAME_DIGEST_FIELD,
    }
)


class V32RunGenesisError(ValueError):
    """The target run genesis or unique pointer failed closed."""


@dataclass(frozen=True, slots=True)
class V32GenesisSourceSpec:
    role: str
    local_ref: str
    schema_id: str
    digest_field: str


GENESIS_SOURCE_SPECS: tuple[V32GenesisSourceSpec, ...] = (
    V32GenesisSourceSpec(
        "theory_approval",
        "genesis/authority/theory-approval.json",
        THEORY_APPROVAL_SCHEMA_ID,
        THEORY_APPROVAL_DIGEST_FIELD,
    ),
    V32GenesisSourceSpec(
        "experiment_contract",
        "genesis/authority/experiment-contract.json",
        EXPERIMENT_CONTRACT_SCHEMA_ID,
        EXPERIMENT_CONTRACT_DIGEST_FIELD,
    ),
    V32GenesisSourceSpec(
        "manifest",
        "genesis/authority/runtime-manifest.json",
        RUNTIME_MANIFEST_SCHEMA_ID,
        RUNTIME_MANIFEST_DIGEST_FIELD,
    ),
    V32GenesisSourceSpec(
        "authorization_receipt",
        "genesis/authority/authorization-receipt.json",
        AUTHORIZATION_RECEIPT_SCHEMA_ID,
        AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    ),
    V32GenesisSourceSpec(
        "authority",
        "genesis/authority/current-authority.json",
        AUTHORITY_SCHEMA_ID,
        AUTHORITY_DIGEST_FIELD,
    ),
)
SOURCE_ROLES = tuple(spec.role for spec in GENESIS_SOURCE_SPECS)

INITIAL_TIMEFRAME_REF = "genesis/initial-timeframe-genesis.json"
REVISION_ZERO_SPECS = {
    "dynamic": (
        "genesis/checkpoints/dynamic-revision-0.json",
        DYNAMIC_CHECKPOINT_SCHEMA_ID,
        DYNAMIC_CHECKPOINT_DIGEST_FIELD,
    ),
    "outcome": (
        "genesis/checkpoints/outcome-revision-0.json",
        OUTCOME_CHECKPOINT_SCHEMA_ID,
        OUTCOME_CHECKPOINT_DIGEST_FIELD,
    ),
    "supervisor": (
        "genesis/checkpoints/supervisor-revision-0.json",
        SUPERVISOR_CHECKPOINT_SCHEMA_ID,
        SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    ),
}


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32RunGenesisError(code)
    return value


def _run_id(value: Any, code: str) -> str:
    text = _text(value, code)
    if _RUN_ID.fullmatch(text) is None:
        raise V32RunGenesisError(code)
    return text


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32RunGenesisError(code) from exc
    if parsed.tzinfo is None:
        raise V32RunGenesisError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32RunGenesisError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32RunGenesisError(code)
    return value


def _relative(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.as_posix() != text
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32RunGenesisError(code)
    return text


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
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
        raise V32RunGenesisError(code)


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _binding(
    value: Any,
    *,
    code: str,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32RunGenesisError(code)
    normalized = {
        "relative_ref": _relative(value.get("relative_ref"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    if (schema_id is not None and normalized["schema_id"] != schema_id) or (
        digest_field is not None and normalized["digest_field"] != digest_field
    ):
        raise V32RunGenesisError(code)
    return normalized


def _global_binding(value: Any, *, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise V32RunGenesisError(code)
    return _binding(
        {
            "relative_ref": value.get("path"),
            "schema_id": value.get("schema_id"),
            "digest_field": value.get("digest_field"),
            "semantic_digest": value.get("semantic_digest"),
            "physical_sha256": value.get("physical_sha256"),
        },
        code=code,
    )


def _role_maps(
    projection: Any,
    global_bindings: Any,
    local_bindings: Any | None = None,
) -> None:
    roles = set(SOURCE_ROLES)
    if not isinstance(projection, Mapping) or set(projection) != roles:
        raise V32RunGenesisError("V32_RUN_GENESIS_PROJECTION_SET_INVALID")
    if not isinstance(global_bindings, Mapping) or set(global_bindings) != roles:
        raise V32RunGenesisError("V32_RUN_GENESIS_GLOBAL_BINDING_SET_INVALID")
    if local_bindings is not None and (
        not isinstance(local_bindings, Mapping) or set(local_bindings) != roles
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_LOCAL_BINDING_SET_INVALID")


def validate_v32_target_projection_v1(
    *,
    projection: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    """Replay the exact target projection and its cross-document identities."""

    _role_maps(projection, global_bindings)
    approval = projection["theory_approval"]
    contract = projection["experiment_contract"]
    manifest = projection["manifest"]
    authorization = projection["authorization_receipt"]
    authority = projection["authority"]
    try:
        digests = {
            "theory_approval": verify_v32_theory_approval_receipt_v1(approval),
            "experiment_contract": verify_v32_experiment_contract_v1(contract),
            "manifest": verify_v32_runtime_manifest(manifest),
            "authorization_receipt": verify_v32_authorization_receipt_v1(
                authorization
            ),
            "authority": verify_v32_authority_v1(authority),
        }
    except (V32AuthorizationError, V32ExperimentContractError, TypeError, ValueError) as exc:
        raise V32RunGenesisError("V32_RUN_GENESIS_PROJECTION_INVALID") from exc

    normalized_bindings: dict[str, dict[str, str]] = {}
    for spec in GENESIS_SOURCE_SPECS:
        binding = _global_binding(
            global_bindings[spec.role],
            code=f"V32_RUN_GENESIS_GLOBAL_BINDING_INVALID:{spec.role}",
        )
        if (
            binding["schema_id"] != spec.schema_id
            or binding["digest_field"] != spec.digest_field
            or binding["semantic_digest"] != digests[spec.role]
            or projection[spec.role].get(spec.digest_field) != digests[spec.role]
        ):
            raise V32RunGenesisError(
                f"V32_RUN_GENESIS_GLOBAL_BINDING_MISMATCH:{spec.role}"
            )
        normalized_bindings[spec.role] = binding

    run = _run_id(contract.get("run_id"), "V32_RUN_GENESIS_SCOPE_INVALID")
    approval_binding = normalized_bindings["theory_approval"]
    contract_binding = normalized_bindings["experiment_contract"]
    manifest_binding = normalized_bindings["manifest"]
    authorization_binding = normalized_bindings["authorization_receipt"]
    if (
        authority.get("profile") != TARGET_PROFILE
        or authority.get("status") != "ACTIVE"
        or authority.get("run_id") != run
        or authority.get("target_run_id") != run
        or authorization.get("profile") != TARGET_PROFILE
        or authorization.get("run_id") != run
        or authorization.get("target_run_id") != run
        or manifest.get("target_run_id") != run
        or contract.get("pilot_protocol", {}).get("analysis_cycles")
        != TOTAL_ANALYSIS_CYCLES
        or contract.get("pilot_protocol", {}).get("scheduled_outcomes")
        != TOTAL_OUTCOME_SCHEDULES
        or manifest.get("pilot_protocol", {}).get("analysis_cycles")
        != TOTAL_ANALYSIS_CYCLES
        or manifest.get("pilot_protocol", {}).get("outcome_schedules")
        != TOTAL_OUTCOME_SCHEDULES
        or approval.get("theory_binding")
        != {
            key: contract.get("theory_binding", {}).get(key)
            for key in (
                "relative_ref",
                "theory_version",
                "physical_sha256",
                "semantic_digest",
            )
        }
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_SCOPE_INVALID")
    if (
        manifest.get("theory_approval_binding") != {
            "path": approval_binding["relative_ref"],
            **{key: approval_binding[key] for key in _BINDING_FIELDS if key != "relative_ref"},
        }
        or manifest.get("experiment_contract_binding") != {
            "path": contract_binding["relative_ref"],
            **{key: contract_binding[key] for key in _BINDING_FIELDS if key != "relative_ref"},
        }
        or authorization.get("theory_approval_binding") != manifest.get("theory_approval_binding")
        or authorization.get("experiment_contract_binding")
        != manifest.get("experiment_contract_binding")
        or authorization.get("runtime_manifest_binding") != {
            "path": manifest_binding["relative_ref"],
            **{key: manifest_binding[key] for key in _BINDING_FIELDS if key != "relative_ref"},
        }
        or authority.get("theory_approval_binding") != authorization.get("theory_approval_binding")
        or authority.get("experiment_contract_binding")
        != authorization.get("experiment_contract_binding")
        or authority.get("runtime_manifest_binding")
        != authorization.get("runtime_manifest_binding")
        or authority.get("authorization_receipt_binding") != {
            "path": authorization_binding["relative_ref"],
            **{key: authorization_binding[key] for key in _BINDING_FIELDS if key != "relative_ref"},
        }
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_PROJECTION_CHAIN_INVALID")
    return {"run_id": run, **{f"{role}_digest": value for role, value in digests.items()}}


def build_v32_initial_timeframe_genesis_entity_v1(
    *, run_id: str, created_at: str
) -> dict[str, Any]:
    """Build the closed pre-source state; it contains no market placeholder."""

    document = {
        "schema_id": TIMEFRAME_GENESIS_SCHEMA_ID,
        "schema_version": RUN_GENESIS_SCHEMA_VERSION,
        "run_id": _run_id(run_id, "V32_RUN_GENESIS_RUN_ID_INVALID"),
        "cycle_index": 1,
        "created_at": _time(created_at, "V32_RUN_GENESIS_TIME_INVALID"),
        "state": "UNINITIALIZED_PENDING_FIRST_FORMAL_SOURCE",
        "first_formal_source_required": True,
        "market_data_present": False,
        "market_values_present": False,
        "market_payload_digest_present": False,
        "previous_timeframe_digest": None,
        **_boundary(),
    }
    return self_digest(document, TIMEFRAME_DIGEST_FIELD)


def verify_v32_initial_timeframe_genesis_entity_v1(
    document: Mapping[str, Any], *, expected_run_id: str
) -> str:
    """Accept only the internally-built pre-source typed entity."""

    if not isinstance(document, Mapping) or set(document) != _TIMEFRAME_GENESIS_FIELDS:
        raise V32RunGenesisError("V32_RUN_GENESIS_TIMEFRAME_ENTITY_REQUIRED")
    try:
        supplied = verify_self_digest(document, TIMEFRAME_DIGEST_FIELD)
        rebuilt = build_v32_initial_timeframe_genesis_entity_v1(
            run_id=document["run_id"], created_at=document["created_at"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32RunGenesisError):
            raise
        raise V32RunGenesisError("V32_RUN_GENESIS_TIMEFRAME_INVALID") from exc
    if (
        document.get("run_id")
        != _run_id(expected_run_id, "V32_RUN_GENESIS_RUN_ID_INVALID")
        or dict(document) != rebuilt
        or supplied != rebuilt[TIMEFRAME_DIGEST_FIELD]
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_TIMEFRAME_INVALID")
    _assert_boundary(document, "V32_RUN_GENESIS_TIMEFRAME_BOUNDARY_INVALID")
    return supplied


def verify_v32_revision_zero_checkpoints_v1(
    *,
    checkpoints: Mapping[str, Mapping[str, Any]],
    run_id: str,
    experiment_contract_digest: str,
    active_authority_digest: str,
    initial_timeframe_digest: str,
    created_at: str,
) -> dict[str, str]:
    """Replay the three exact revision-zero documents and their cross-bindings."""

    if not isinstance(checkpoints, Mapping) or set(checkpoints) != set(
        REVISION_ZERO_SPECS
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_CHECKPOINT_SET_INVALID")
    run = _run_id(run_id, "V32_RUN_GENESIS_RUN_ID_INVALID")
    contract = _digest(
        experiment_contract_digest, "V32_RUN_GENESIS_CONTRACT_DIGEST_INVALID"
    )
    authority = _digest(
        active_authority_digest, "V32_RUN_GENESIS_AUTHORITY_DIGEST_INVALID"
    )
    timeframe = _digest(
        initial_timeframe_digest, "V32_RUN_GENESIS_TIMEFRAME_DIGEST_INVALID"
    )
    created = _time(created_at, "V32_RUN_GENESIS_TIME_INVALID")
    dynamic = checkpoints["dynamic"]
    outcome = checkpoints["outcome"]
    supervisor = checkpoints["supervisor"]
    try:
        dynamic_digest = verify_self_digest(dynamic, DYNAMIC_CHECKPOINT_DIGEST_FIELD)
        outcome_digest = verify_self_digest(outcome, OUTCOME_CHECKPOINT_DIGEST_FIELD)
        supervisor_digest = verify_v32_tick_supervisor_checkpoint(supervisor)
    except (TypeError, ValueError, V32TickSupervisorError) as exc:
        raise V32RunGenesisError("V32_RUN_GENESIS_CHECKPOINT_INVALID") from exc
    if (
        dynamic.get("schema_id") != DYNAMIC_CHECKPOINT_SCHEMA_ID
        or dynamic.get("run_id") != run
        or dynamic.get("revision") != 0
        or dynamic.get("predecessor_checkpoint_digest") is not None
        or dynamic.get("status") != "READY"
        or dynamic.get("experiment_contract_digest") != contract
        or dynamic.get("active_authority_digest") != authority
        or dynamic.get("total_analysis_cycles") != TOTAL_ANALYSIS_CYCLES
        or dynamic.get("accepted_analysis_cycles") != 0
        or dynamic.get("created_at") != created
        or dynamic.get("updated_at") != created
        or dynamic.get("source_scope") != SOURCE_SCOPE
        or dynamic.get("external_execution_authority") != EXTERNAL_EXECUTION_AUTHORITY
        or dynamic.get("executable") is not False
        or outcome.get("schema_id") != OUTCOME_CHECKPOINT_SCHEMA_ID
        or outcome.get("run_id") != run
        or outcome.get("revision") != 0
        or outcome.get("status") != "ACTIVE"
        or outcome.get("total_cycles") != TOTAL_ANALYSIS_CYCLES
        or outcome.get("total_schedules") != TOTAL_OUTCOME_SCHEDULES
        or outcome.get("created_at") != created
        or outcome.get("updated_at") != created
        or outcome.get("source_scope") != SOURCE_SCOPE
        or outcome.get("external_execution_authority") != EXTERNAL_EXECUTION_AUTHORITY
        or outcome.get("executable") is not False
        or supervisor.get("run_id") != run
        or supervisor.get("revision") != 0
        or supervisor.get("predecessor_checkpoint_digest") is not None
        or supervisor.get("status") != "READY"
        or supervisor.get("experiment_contract_digest") != contract
        or supervisor.get("active_authority_digest") != authority
        or supervisor.get("current_research_checkpoint_digest") != dynamic_digest
        or supervisor.get("current_outcome_checkpoint_digest") != outcome_digest
        or supervisor.get("current_timeframe_cache_digest") != timeframe
        or supervisor.get("created_at") != created
        or supervisor.get("updated_at") != created
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_CHECKPOINT_BINDING_INVALID")
    return {
        "dynamic": dynamic_digest,
        "outcome": outcome_digest,
        "supervisor": supervisor_digest,
    }


def _local_row(
    *, role: str, document: Mapping[str, Any], binding: Mapping[str, Any]
) -> dict[str, str]:
    if role == "initial_timeframe":
        expected = (
            INITIAL_TIMEFRAME_REF,
            TIMEFRAME_GENESIS_SCHEMA_ID,
            TIMEFRAME_DIGEST_FIELD,
        )
    else:
        expected = REVISION_ZERO_SPECS[role]
    normalized = _binding(
        binding, code=f"V32_RUN_GENESIS_LOCAL_BINDING_INVALID:{role}"
    )
    if (
        (normalized["relative_ref"], normalized["schema_id"], normalized["digest_field"])
        != expected
        or document.get(expected[2]) != normalized["semantic_digest"]
        or _physical(document) != normalized["physical_sha256"]
    ):
        raise V32RunGenesisError(
            f"V32_RUN_GENESIS_LOCAL_BINDING_MISMATCH:{role}"
        )
    return {"role": role, "local_ref": normalized.pop("relative_ref"), **normalized}


def build_v32_run_genesis_receipt_v1(
    *,
    created_at: str,
    projection: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
    local_authority_copy_bindings: Mapping[str, Mapping[str, Any]],
    initial_timeframe_entity: Mapping[str, Any],
    initial_timeframe_binding: Mapping[str, Any],
    revision_zero_checkpoints: Mapping[str, Mapping[str, Any]],
    revision_zero_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal the acyclic receipt after every immutable copy already exists."""

    _role_maps(projection, global_bindings, local_authority_copy_bindings)
    projection_state = validate_v32_target_projection_v1(
        projection=projection, global_bindings=global_bindings
    )
    run = projection_state["run_id"]
    created = _time(created_at, "V32_RUN_GENESIS_TIME_INVALID")
    timeframe_digest = verify_v32_initial_timeframe_genesis_entity_v1(
        initial_timeframe_entity, expected_run_id=run
    )
    checkpoint_digests = verify_v32_revision_zero_checkpoints_v1(
        checkpoints=revision_zero_checkpoints,
        run_id=run,
        experiment_contract_digest=projection_state["experiment_contract_digest"],
        active_authority_digest=projection_state["authority_digest"],
        initial_timeframe_digest=timeframe_digest,
        created_at=created,
    )
    if (
        _moment(created, "V32_RUN_GENESIS_TIME_INVALID")
        < _moment(projection["authority"]["recorded_at"], "V32_RUN_GENESIS_TIME_INVALID")
        or initial_timeframe_entity.get("created_at") != created
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_TIME_ORDER_INVALID")

    source_rows: list[dict[str, Any]] = []
    for spec in GENESIS_SOURCE_SPECS:
        global_binding = _global_binding(
            global_bindings[spec.role], code="V32_RUN_GENESIS_GLOBAL_BINDING_INVALID"
        )
        local = _binding(
            local_authority_copy_bindings[spec.role],
            code=f"V32_RUN_GENESIS_LOCAL_BINDING_INVALID:{spec.role}",
            schema_id=spec.schema_id,
            digest_field=spec.digest_field,
        )
        if (
            local["relative_ref"] != spec.local_ref
            or local["semantic_digest"] != global_binding["semantic_digest"]
            or local["physical_sha256"] != global_binding["physical_sha256"]
        ):
            raise V32RunGenesisError(
                f"V32_RUN_GENESIS_AUTHORITY_COPY_MISMATCH:{spec.role}"
            )
        source_rows.append(
            {
                "role": spec.role,
                "source_ref": global_binding["relative_ref"],
                "local_ref": local["relative_ref"],
                "schema_id": spec.schema_id,
                "digest_field": spec.digest_field,
                "semantic_digest": local["semantic_digest"],
                "source_physical_sha256": global_binding["physical_sha256"],
                "local_physical_sha256": local["physical_sha256"],
                "exact_bytes_copied": True,
            }
        )
    if not isinstance(revision_zero_bindings, Mapping) or set(
        revision_zero_bindings
    ) != set(REVISION_ZERO_SPECS):
        raise V32RunGenesisError("V32_RUN_GENESIS_CHECKPOINT_BINDING_SET_INVALID")
    timeframe_row = _local_row(
        role="initial_timeframe",
        document=initial_timeframe_entity,
        binding=initial_timeframe_binding,
    )
    checkpoint_rows = [
        _local_row(
            role=role,
            document=revision_zero_checkpoints[role],
            binding=revision_zero_bindings[role],
        )
        for role in REVISION_ZERO_SPECS
    ]
    if any(
        row["semantic_digest"] != checkpoint_digests[row["role"]]
        for row in checkpoint_rows
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_CHECKPOINT_BINDING_MISMATCH")

    receipt = {
        "schema_id": RUN_GENESIS_SCHEMA_ID,
        "schema_version": RUN_GENESIS_SCHEMA_VERSION,
        "run_id": run,
        "created_at": created,
        "operation": OPERATION,
        "experiment_scope": {
            "analysis_cycles": TOTAL_ANALYSIS_CYCLES,
            "outcome_schedules": TOTAL_OUTCOME_SCHEDULES,
            "analysis_interval_seconds": 900,
            "instrument_id": "BTC-USDT-SWAP",
        },
        "authority_projection_copies": source_rows,
        "initial_timeframe_entity": timeframe_row,
        "revision_zero_checkpoints": checkpoint_rows,
        "cross_bindings": {
            "experiment_contract_digest": projection_state[
                "experiment_contract_digest"
            ],
            "active_authority_digest": projection_state["authority_digest"],
            "initial_timeframe_digest": timeframe_digest,
            "dynamic_checkpoint_digest": checkpoint_digests["dynamic"],
            "outcome_checkpoint_digest": checkpoint_digests["outcome"],
            "supervisor_checkpoint_digest": checkpoint_digests["supervisor"],
        },
        "qualification_boundary_audit_gate": {
            "cycle_index": 0,
            "boundary_type": "QUALIFICATION",
            "status_at_genesis": "REQUIRED_NOT_COMPLETED",
            "qualification_retirement_binding": _global_binding(
                projection["authority"]["qualification_retirement_binding"],
                code="V32_RUN_GENESIS_QUALIFICATION_RETIREMENT_INVALID",
            ),
            "target_authority_local_binding": dict(
                local_authority_copy_bindings["authority"]
            ),
            "run_genesis_binding_available_only_after_receipt_readback": True,
            "typed_completion_required_before_first_analysis_permit": True,
        },
        "publication_policy": {
            "publish_pointer_only_after_all_copy_readback_and_replay": True,
            "same_run_identical_replay_is_idempotent": True,
            "second_active_run_forbidden": True,
            "legacy_run_pointer_forbidden": True,
        },
        "chat_history_is_authority": False,
        **_boundary(),
    }
    return self_digest(receipt, RUN_GENESIS_DIGEST_FIELD)


def _extract_source_bindings(rows: Any) -> dict[str, dict[str, str]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) != len(
        GENESIS_SOURCE_SPECS
    ):
        raise V32RunGenesisError("V32_RUN_GENESIS_SOURCE_ROWS_INVALID")
    result: dict[str, dict[str, str]] = {}
    for spec, row in zip(GENESIS_SOURCE_SPECS, rows, strict=True):
        if (
            not isinstance(row, Mapping)
            or set(row) != _SOURCE_ROW_FIELDS
            or row.get("role") != spec.role
            or row.get("local_ref") != spec.local_ref
            or row.get("schema_id") != spec.schema_id
            or row.get("digest_field") != spec.digest_field
            or row.get("exact_bytes_copied") is not True
            or row.get("source_physical_sha256") != row.get("local_physical_sha256")
        ):
            raise V32RunGenesisError("V32_RUN_GENESIS_SOURCE_ROWS_INVALID")
        result[spec.role] = {
            "relative_ref": _relative(row["local_ref"], "V32_RUN_GENESIS_SOURCE_ROWS_INVALID"),
            "schema_id": spec.schema_id,
            "digest_field": spec.digest_field,
            "semantic_digest": _digest(
                row["semantic_digest"], "V32_RUN_GENESIS_SOURCE_ROWS_INVALID"
            ),
            "physical_sha256": _digest(
                row["local_physical_sha256"],
                "V32_RUN_GENESIS_SOURCE_ROWS_INVALID",
            ),
        }
    return result


def _extract_local_row(row: Any, *, role: str) -> dict[str, str]:
    if not isinstance(row, Mapping) or set(row) != _LOCAL_ROW_FIELDS or row.get(
        "role"
    ) != role:
        raise V32RunGenesisError("V32_RUN_GENESIS_LOCAL_ROW_INVALID")
    return {
        "relative_ref": _relative(row["local_ref"], "V32_RUN_GENESIS_LOCAL_ROW_INVALID"),
        "schema_id": _text(row["schema_id"], "V32_RUN_GENESIS_LOCAL_ROW_INVALID"),
        "digest_field": _text(row["digest_field"], "V32_RUN_GENESIS_LOCAL_ROW_INVALID"),
        "semantic_digest": _digest(row["semantic_digest"], "V32_RUN_GENESIS_LOCAL_ROW_INVALID"),
        "physical_sha256": _digest(row["physical_sha256"], "V32_RUN_GENESIS_LOCAL_ROW_INVALID"),
    }


def verify_v32_run_genesis_receipt_v1(
    receipt: Mapping[str, Any],
    *,
    projection: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
    initial_timeframe_entity: Mapping[str, Any],
    revision_zero_checkpoints: Mapping[str, Mapping[str, Any]],
) -> str:
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_FIELDS:
        raise V32RunGenesisError("V32_RUN_GENESIS_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(receipt, RUN_GENESIS_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32RunGenesisError("V32_RUN_GENESIS_RECEIPT_DIGEST_INVALID") from exc
    _assert_boundary(receipt, "V32_RUN_GENESIS_BOUNDARY_INVALID")
    local_authority = _extract_source_bindings(
        receipt.get("authority_projection_copies")
    )
    timeframe_binding = _extract_local_row(
        receipt.get("initial_timeframe_entity"), role="initial_timeframe"
    )
    checkpoint_rows = receipt.get("revision_zero_checkpoints")
    if not isinstance(checkpoint_rows, list) or [
        row.get("role") if isinstance(row, Mapping) else None for row in checkpoint_rows
    ] != list(REVISION_ZERO_SPECS):
        raise V32RunGenesisError("V32_RUN_GENESIS_CHECKPOINT_ROWS_INVALID")
    checkpoint_bindings = {
        role: _extract_local_row(row, role=role)
        for role, row in zip(REVISION_ZERO_SPECS, checkpoint_rows, strict=True)
    }
    rebuilt = build_v32_run_genesis_receipt_v1(
        created_at=receipt.get("created_at"),
        projection=projection,
        global_bindings=global_bindings,
        local_authority_copy_bindings=local_authority,
        initial_timeframe_entity=initial_timeframe_entity,
        initial_timeframe_binding=timeframe_binding,
        revision_zero_checkpoints=revision_zero_checkpoints,
        revision_zero_bindings=checkpoint_bindings,
    )
    if dict(receipt) != rebuilt or supplied != rebuilt[RUN_GENESIS_DIGEST_FIELD]:
        raise V32RunGenesisError("V32_RUN_GENESIS_REPLAY_MISMATCH")
    return supplied


def build_v32_current_run_pointer_v1(
    *,
    published_at: str,
    run_id: str,
    run_genesis_binding: Mapping[str, Any],
    experiment_contract_digest: str,
    active_authority_digest: str,
) -> dict[str, Any]:
    binding = _binding(
        run_genesis_binding,
        code="V32_RUN_POINTER_GENESIS_BINDING_INVALID",
        schema_id=RUN_GENESIS_SCHEMA_ID,
        digest_field=RUN_GENESIS_DIGEST_FIELD,
    )
    pointer = {
        "schema_id": CURRENT_RUN_POINTER_SCHEMA_ID,
        "schema_version": RUN_GENESIS_SCHEMA_VERSION,
        "run_id": _run_id(run_id, "V32_RUN_POINTER_RUN_ID_INVALID"),
        "status": "ACTIVE",
        "published_at": _time(published_at, "V32_RUN_POINTER_TIME_INVALID"),
        "run_genesis_binding": binding,
        "experiment_contract_digest": _digest(
            experiment_contract_digest, "V32_RUN_POINTER_CONTRACT_INVALID"
        ),
        "active_authority_digest": _digest(
            active_authority_digest, "V32_RUN_POINTER_AUTHORITY_INVALID"
        ),
        "single_active_target_run": True,
        "legacy_run_allowed": False,
        "first_analysis_permit_status_at_publication": (
            "BLOCKED_PENDING_QUALIFICATION_BOUNDARY_AUDIT"
        ),
        "genesis_grants_first_analysis_permit": False,
        **_boundary(),
    }
    return self_digest(pointer, CURRENT_RUN_POINTER_DIGEST_FIELD)


def verify_v32_current_run_pointer_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _POINTER_FIELDS:
        raise V32RunGenesisError("V32_RUN_POINTER_INVALID")
    try:
        supplied = verify_self_digest(document, CURRENT_RUN_POINTER_DIGEST_FIELD)
        rebuilt = build_v32_current_run_pointer_v1(
            published_at=document["published_at"],
            run_id=document["run_id"],
            run_genesis_binding=document["run_genesis_binding"],
            experiment_contract_digest=document["experiment_contract_digest"],
            active_authority_digest=document["active_authority_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32RunGenesisError):
            raise
        raise V32RunGenesisError("V32_RUN_POINTER_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[CURRENT_RUN_POINTER_DIGEST_FIELD]:
        raise V32RunGenesisError("V32_RUN_POINTER_REPLAY_MISMATCH")
    _assert_boundary(document, "V32_RUN_POINTER_BOUNDARY_INVALID")
    return supplied


__all__ = [
    "CURRENT_RUN_POINTER_DIGEST_FIELD",
    "CURRENT_RUN_POINTER_SCHEMA_ID",
    "DYNAMIC_CHECKPOINT_DIGEST_FIELD",
    "DYNAMIC_CHECKPOINT_SCHEMA_ID",
    "GENESIS_SOURCE_SPECS",
    "INITIAL_TIMEFRAME_REF",
    "OUTCOME_CHECKPOINT_DIGEST_FIELD",
    "OUTCOME_CHECKPOINT_SCHEMA_ID",
    "REVISION_ZERO_SPECS",
    "RUN_GENESIS_DIGEST_FIELD",
    "RUN_GENESIS_REF",
    "RUN_GENESIS_SCHEMA_ID",
    "SOURCE_ROLES",
    "TIMEFRAME_DIGEST_FIELD",
    "TIMEFRAME_GENESIS_SCHEMA_ID",
    "V32RunGenesisError",
    "build_v32_current_run_pointer_v1",
    "build_v32_initial_timeframe_genesis_entity_v1",
    "build_v32_run_genesis_receipt_v1",
    "validate_v32_target_projection_v1",
    "verify_v32_current_run_pointer_v1",
    "verify_v32_initial_timeframe_genesis_entity_v1",
    "verify_v32_revision_zero_checkpoints_v1",
    "verify_v32_run_genesis_receipt_v1",
]
