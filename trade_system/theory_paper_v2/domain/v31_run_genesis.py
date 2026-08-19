"""Pure contracts for the single V3.1 run-genesis receipt.

The receipt closes the authorization chronology without creating a digest
cycle: it binds exact local copies of the approved source documents, while the
later checkpoint binds the receipt.  The receipt never binds a checkpoint or
grants account, credential, portfolio, paper, or live execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from .contracts.canonical import self_digest, verify_self_digest
from .governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_active_authority,
    validate_v31_document_binding,
    validate_v31_experiment_authorization,
    validate_v31_frozen_experiment_manifest,
    validate_v31_theory_approval,
)
from .v31_experiment_contracts import (
    EXPERIMENT_SCHEMA_ID,
    V31ExperimentContractError,
    verify_minimal_experiment_contract,
)


RUN_GENESIS_SCHEMA_ID = "theory_paper_v31_run_genesis"
RUN_GENESIS_SCHEMA_VERSION = "1.0.0"
RUN_GENESIS_REF = "genesis/run-genesis.json"
RUN_GENESIS_DIGEST_FIELD = "run_genesis_digest"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EXACT_INSTRUMENT = {
    "venue": "OKX",
    "instrument_id": "BTC-USDT-SWAP",
    "market_type": "PERPETUAL_SWAP",
    "underlying_symbol": "BTC-USDT",
}
_EXECUTION_FALSE_FIELDS = (
    "account_access",
    "paper_trading",
    "live_trading",
    "order_submission",
    "credential_access",
    "funds_access",
    "portfolio_mutation",
)
_COPY_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_ARTIFACT_ROW_FIELDS = frozenset(
    {
        "source_role",
        "global_ref",
        "local_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "global_physical_sha256",
        "local_physical_sha256",
        "exact_bytes_copied",
    }
)
_RUN_GENESIS_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "created_at",
        "operation",
        "symbol",
        "instrument",
        "data_scope",
        "portfolio_mode",
        "cycle_protocol",
        "fresh_run",
        "predecessor_run_id",
        "authorization_cardinality",
        "legacy_runs_resumable",
        "genesis_artifacts",
        "experiment_contract_binding",
        "checkpoint_initialization_contract",
        "chat_history_is_authority",
        *_EXECUTION_FALSE_FIELDS,
        "external_execution_authority",
        "executable",
        RUN_GENESIS_DIGEST_FIELD,
    }
)


class V31RunGenesisError(ValueError):
    """The sole V3.1 run genesis failed closed."""


@dataclass(frozen=True, slots=True)
class V31GenesisSourceSpec:
    role: str
    local_ref: str
    schema_id: str
    digest_field: str


GENESIS_SOURCE_SPECS: tuple[V31GenesisSourceSpec, ...] = (
    V31GenesisSourceSpec(
        "theory_approval",
        "genesis/theory-approval.json",
        "theory_paper_v31_user_approval_receipt",
        "approval_receipt_digest",
    ),
    V31GenesisSourceSpec(
        "experiment_contract",
        "genesis/experiment-contract.json",
        EXPERIMENT_SCHEMA_ID,
        "experiment_contract_digest",
    ),
    V31GenesisSourceSpec(
        "experiment_manifest",
        "genesis/experiment-manifest.json",
        "theory_paper_v31_frozen_experiment_manifest",
        "manifest_digest",
    ),
    V31GenesisSourceSpec(
        "experiment_authorization",
        "genesis/experiment-authorization.json",
        "theory_paper_v31_experiment_authorization_receipt",
        "authorization_receipt_digest",
    ),
    V31GenesisSourceSpec(
        "current_authority",
        "genesis/current-authority.json",
        "theory_paper_v31_current_research_authority",
        "authority_digest",
    ),
)
_SOURCE_BY_ROLE = {spec.role: spec for spec in GENESIS_SOURCE_SPECS}
_SOURCE_ROLES = frozenset(_SOURCE_BY_ROLE)

CHECKPOINT_BINDING_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("theory_approval_ref", "theory_approval_digest", "theory_approval"),
    (
        "experiment_manifest_ref",
        "experiment_manifest_digest",
        "experiment_manifest",
    ),
    (
        "experiment_authorization_ref",
        "experiment_authorization_digest",
        "experiment_authorization",
    ),
    ("current_authority_ref", "current_authority_digest", "current_authority"),
    ("run_genesis_ref", "run_genesis_digest", "run_genesis"),
)


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31RunGenesisError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31RunGenesisError(code) from exc
    if parsed.tzinfo is None:
        raise V31RunGenesisError(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31RunGenesisError(code)
    return normalized


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31RunGenesisError(code)
    return value


def _relative_ref(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31RunGenesisError(code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.as_posix() != value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31RunGenesisError(code)
    return value


def _require_role_maps(
    documents: Any, global_bindings: Any, local_copy_bindings: Any | None = None
) -> None:
    if not isinstance(documents, Mapping) or set(documents) != _SOURCE_ROLES:
        raise V31RunGenesisError("V31_RUN_GENESIS_DOCUMENT_SET_INVALID")
    if (
        not isinstance(global_bindings, Mapping)
        or set(global_bindings) != _SOURCE_ROLES
    ):
        raise V31RunGenesisError("V31_RUN_GENESIS_GLOBAL_BINDING_SET_INVALID")
    if local_copy_bindings is not None and (
        not isinstance(local_copy_bindings, Mapping)
        or set(local_copy_bindings) != _SOURCE_ROLES
    ):
        raise V31RunGenesisError("V31_RUN_GENESIS_COPY_BINDING_SET_INVALID")


def validate_v31_run_genesis_inputs(
    *,
    documents: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
) -> str:
    """Validate the complete, already physically admitted authority chain.

    Physical file containment and SHA verification happen in the authority
    loader and Application initializer.  This function verifies domain
    semantics and ensures the supplied bindings are the exact bindings carried
    by the authorization chronology.
    """

    _require_role_maps(documents, global_bindings)
    approval = documents["theory_approval"]
    contract = documents["experiment_contract"]
    manifest = documents["experiment_manifest"]
    authorization = documents["experiment_authorization"]
    authority = documents["current_authority"]
    try:
        approval_digest = validate_v31_theory_approval(approval)
        contract_digest = verify_minimal_experiment_contract(contract)
        manifest_digest = validate_v31_frozen_experiment_manifest(
            manifest,
            experiment_contract=contract,
            theory_approval=approval,
        )
        authorization_digest = validate_v31_experiment_authorization(
            authorization,
            manifest=manifest,
            experiment_contract=contract,
            theory_approval=approval,
        )
        authority_digest = validate_v31_active_authority(
            authority,
            theory_approval=approval,
            manifest=manifest,
            experiment_contract=contract,
            authorization_receipt=authorization,
        )
    except (V31AuthorizationError, V31ExperimentContractError) as exc:
        raise V31RunGenesisError("V31_RUN_GENESIS_AUTHORITY_CHAIN_INVALID") from exc

    expected_digests = {
        "theory_approval": approval_digest,
        "experiment_contract": contract_digest,
        "experiment_manifest": manifest_digest,
        "experiment_authorization": authorization_digest,
        "current_authority": authority_digest,
    }
    for spec in GENESIS_SOURCE_SPECS:
        document = documents[spec.role]
        binding = global_bindings[spec.role]
        try:
            validate_v31_document_binding(
                binding,
                code="V31_RUN_GENESIS_GLOBAL_BINDING_INVALID",
                expected_schema_id=spec.schema_id,
                expected_digest_field=spec.digest_field,
            )
        except V31AuthorizationError as exc:
            raise V31RunGenesisError(
                "V31_RUN_GENESIS_GLOBAL_BINDING_INVALID"
            ) from exc
        if (
            not isinstance(document, Mapping)
            or document.get("schema_id") != spec.schema_id
            or document.get(spec.digest_field) != expected_digests[spec.role]
            or binding.get("semantic_digest") != expected_digests[spec.role]
        ):
            raise V31RunGenesisError("V31_RUN_GENESIS_GLOBAL_BINDING_MISMATCH")

    if (
        global_bindings["theory_approval"]
        != manifest.get("theory_approval_binding")
        or global_bindings["experiment_contract"]
        != manifest.get("experiment_contract_binding")
        or global_bindings["experiment_manifest"]
        != authorization.get("manifest_binding")
        or global_bindings["experiment_manifest"]
        != authority.get("manifest_binding")
        or global_bindings["experiment_authorization"]
        != authority.get("authorization_receipt_binding")
        or global_bindings["theory_approval"]
        != authority.get("theory_approval_binding")
        or global_bindings["experiment_contract"]
        != authority.get("experiment_contract_binding")
    ):
        raise V31RunGenesisError("V31_RUN_GENESIS_CHRONOLOGY_BINDING_MISMATCH")

    run_id = contract.get("run_id")
    if (
        not isinstance(run_id, str)
        or not run_id
        or manifest.get("run_id") != run_id
        or authorization.get("run_id") != run_id
        or authority.get("authorized_run_id") != run_id
        or manifest.get("operation") != "RUN_V31_PROSPECTIVE"
        or authorization.get("operation") != "RUN_V31_PROSPECTIVE"
        or authority.get("authorized_operation") != "RUN_V31_PROSPECTIVE"
        or authority.get("experiment_start_authorized") is not True
        or manifest.get("instrument") != _EXACT_INSTRUMENT
        or authorization.get("instrument") != _EXACT_INSTRUMENT
        or authority.get("instrument") != _EXACT_INSTRUMENT
        or manifest.get("total_cycles") != 8
        or manifest.get("cadence_seconds") != 3600
        or authority.get("total_cycles") != 8
        or manifest.get("fresh_run") is not True
        or manifest.get("predecessor_run_id") is not None
        or any(
            item.get("legacy_runs_resumable") is not False
            for item in (approval, manifest, authorization, authority)
        )
    ):
        raise V31RunGenesisError("V31_RUN_GENESIS_SCOPE_INVALID")
    return run_id


def _validate_copy_binding(
    *,
    spec: V31GenesisSourceSpec,
    binding: Any,
    document: Mapping[str, Any],
    global_binding: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(binding, Mapping) or set(binding) != _COPY_BINDING_FIELDS:
        raise V31RunGenesisError("V31_RUN_GENESIS_COPY_BINDING_INVALID")
    normalized = dict(binding)
    if (
        _relative_ref(
            normalized.get("relative_ref"),
            "V31_RUN_GENESIS_COPY_BINDING_INVALID",
        )
        != spec.local_ref
        or normalized.get("schema_id") != spec.schema_id
        or normalized.get("digest_field") != spec.digest_field
        or _digest(
            normalized.get("semantic_digest"),
            "V31_RUN_GENESIS_COPY_BINDING_INVALID",
        )
        != document.get(spec.digest_field)
        or _digest(
            normalized.get("physical_sha256"),
            "V31_RUN_GENESIS_COPY_BINDING_INVALID",
        )
        != global_binding.get("physical_sha256")
    ):
        raise V31RunGenesisError("V31_RUN_GENESIS_COPY_BINDING_MISMATCH")
    return normalized


def _checkpoint_contract() -> dict[str, Any]:
    return {
        "schema_id": "theory_paper_v31_research_checkpoint",
        "schema_version": "1.2.0",
        "binding_pairs": [
            {
                "ref_field": ref_field,
                "digest_field": digest_field,
                "source_role": source_role,
            }
            for ref_field, digest_field, source_role in CHECKPOINT_BINDING_PAIRS
        ],
        "run_genesis_ref": RUN_GENESIS_REF,
        "back_reference_policy": "FORBIDDEN",
        "initialize_only_after_genesis_readback": True,
    }


def build_v31_run_genesis_receipt(
    *,
    created_at: str,
    documents: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
    local_copy_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal the immutable receipt that precedes checkpoint initialization."""

    _require_role_maps(documents, global_bindings, local_copy_bindings)
    run_id = validate_v31_run_genesis_inputs(
        documents=documents, global_bindings=global_bindings
    )
    created = _timestamp(created_at, "V31_RUN_GENESIS_TIME_INVALID")
    authority_time = _timestamp(
        documents["current_authority"].get("recorded_at"),
        "V31_RUN_GENESIS_AUTHORITY_TIME_INVALID",
    )
    if created < authority_time:
        raise V31RunGenesisError("V31_RUN_GENESIS_BEFORE_AUTHORITY")

    artifact_rows: list[dict[str, Any]] = []
    for spec in GENESIS_SOURCE_SPECS:
        document = documents[spec.role]
        global_binding = global_bindings[spec.role]
        local = _validate_copy_binding(
            spec=spec,
            binding=local_copy_bindings[spec.role],
            document=document,
            global_binding=global_binding,
        )
        artifact_rows.append(
            {
                "source_role": spec.role,
                "global_ref": global_binding["path"],
                "local_ref": local["relative_ref"],
                "schema_id": spec.schema_id,
                "digest_field": spec.digest_field,
                "semantic_digest": local["semantic_digest"],
                "global_physical_sha256": global_binding["physical_sha256"],
                "local_physical_sha256": local["physical_sha256"],
                "exact_bytes_copied": True,
            }
        )

    contract_row = artifact_rows[1]
    receipt = {
        "schema_id": RUN_GENESIS_SCHEMA_ID,
        "schema_version": RUN_GENESIS_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "operation": "RUN_V31_PROSPECTIVE",
        "symbol": "BTC-USDT",
        "instrument": dict(_EXACT_INSTRUMENT),
        "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "portfolio_mode": "STATIC_COUNTERFACTUAL_FLAT_SHADOW",
        "cycle_protocol": {
            "accepted_cycle_count": 8,
            "cadence_seconds": 3600,
            "timeframe": "1H",
            "bar_state": "CLOSED_ONLY",
            "one_new_distinct_bar_per_cycle": True,
            "duplicate_as_of_forbidden": True,
        },
        "fresh_run": True,
        "predecessor_run_id": None,
        "authorization_cardinality": "EXACTLY_ONE_FRESH_RUN",
        "legacy_runs_resumable": False,
        "genesis_artifacts": artifact_rows,
        "experiment_contract_binding": dict(contract_row),
        "checkpoint_initialization_contract": _checkpoint_contract(),
        "chat_history_is_authority": False,
        **{field: False for field in _EXECUTION_FALSE_FIELDS},
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(receipt, RUN_GENESIS_DIGEST_FIELD)


def _extract_copy_bindings(artifacts: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(artifacts, list) or len(artifacts) != len(GENESIS_SOURCE_SPECS):
        raise V31RunGenesisError("V31_RUN_GENESIS_ARTIFACTS_INVALID")
    copies: dict[str, dict[str, Any]] = {}
    for expected, row in zip(GENESIS_SOURCE_SPECS, artifacts, strict=True):
        if (
            not isinstance(row, Mapping)
            or set(row) != _ARTIFACT_ROW_FIELDS
            or row.get("source_role") != expected.role
            or row.get("exact_bytes_copied") is not True
            or row.get("schema_id") != expected.schema_id
            or row.get("digest_field") != expected.digest_field
            or _relative_ref(
                row.get("local_ref"), "V31_RUN_GENESIS_ARTIFACTS_INVALID"
            )
            != expected.local_ref
            or _relative_ref(
                row.get("global_ref"), "V31_RUN_GENESIS_ARTIFACTS_INVALID"
            )
            != row.get("global_ref")
            or _digest(
                row.get("semantic_digest"), "V31_RUN_GENESIS_ARTIFACTS_INVALID"
            )
            != row.get("semantic_digest")
            or _digest(
                row.get("global_physical_sha256"),
                "V31_RUN_GENESIS_ARTIFACTS_INVALID",
            )
            != row.get("local_physical_sha256")
        ):
            raise V31RunGenesisError("V31_RUN_GENESIS_ARTIFACTS_INVALID")
        copies[expected.role] = {
            "relative_ref": row["local_ref"],
            "schema_id": row["schema_id"],
            "digest_field": row["digest_field"],
            "semantic_digest": row["semantic_digest"],
            "physical_sha256": row["local_physical_sha256"],
        }
    return copies


def verify_v31_run_genesis_receipt(
    receipt: Mapping[str, Any],
    *,
    documents: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
) -> str:
    """Reconstruct and verify a genesis receipt against its frozen sources."""

    if not isinstance(receipt, Mapping):
        raise V31RunGenesisError("V31_RUN_GENESIS_RECEIPT_INVALID")
    try:
        digest = verify_self_digest(receipt, RUN_GENESIS_DIGEST_FIELD)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31RunGenesisError("V31_RUN_GENESIS_DIGEST_INVALID") from exc
    if set(receipt) != _RUN_GENESIS_FIELDS:
        raise V31RunGenesisError("V31_RUN_GENESIS_RECEIPT_INVALID")
    copies = _extract_copy_bindings(receipt.get("genesis_artifacts"))
    expected = build_v31_run_genesis_receipt(
        created_at=receipt.get("created_at"),
        documents=documents,
        global_bindings=global_bindings,
        local_copy_bindings=copies,
    )
    if dict(receipt) != expected or receipt.get("experiment_contract_binding") != (
        receipt["genesis_artifacts"][1]
    ):
        raise V31RunGenesisError("V31_RUN_GENESIS_RECONSTRUCTION_MISMATCH")
    return digest


def checkpoint_genesis_bindings(
    receipt: Mapping[str, Any],
    *,
    documents: Mapping[str, Mapping[str, Any]],
    global_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    """Project the exact checkpoint 1.2 five-pair binding set."""

    genesis_digest = verify_v31_run_genesis_receipt(
        receipt, documents=documents, global_bindings=global_bindings
    )
    artifacts = {
        row["source_role"]: row for row in receipt["genesis_artifacts"]
    }
    result: dict[str, str] = {}
    for ref_field, digest_field, role in CHECKPOINT_BINDING_PAIRS:
        if role == "run_genesis":
            result[ref_field] = RUN_GENESIS_REF
            result[digest_field] = genesis_digest
        else:
            result[ref_field] = str(artifacts[role]["local_ref"])
            result[digest_field] = str(artifacts[role]["semantic_digest"])
    return result


__all__ = [
    "CHECKPOINT_BINDING_PAIRS",
    "GENESIS_SOURCE_SPECS",
    "RUN_GENESIS_DIGEST_FIELD",
    "RUN_GENESIS_REF",
    "RUN_GENESIS_SCHEMA_ID",
    "RUN_GENESIS_SCHEMA_VERSION",
    "V31GenesisSourceSpec",
    "V31RunGenesisError",
    "build_v31_run_genesis_receipt",
    "checkpoint_genesis_bindings",
    "validate_v31_run_genesis_inputs",
    "verify_v31_run_genesis_receipt",
]
