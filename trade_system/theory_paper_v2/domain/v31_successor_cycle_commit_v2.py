"""Pure commit-material contract for recoverable V3.1 successor cycles.

The legacy research and monitor cursors are separate compare-and-swap owners.
This document freezes the complete deterministic bridge between them before
either owner advances.  A recovery may replay the embedded durable assembly
bundle and monitor plan, but it may not call the Agent again, change monitor
rules, or collect an outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping

from .contracts.canonical import self_digest, verify_self_digest
from .v31_experiment_contracts import (
    verify_minimal_experiment_contract,
    verify_typed_path_monitor_plan,
)


class V31SuccessorCycleCommitV2Error(ValueError):
    """A successor commit material document is incomplete or drifted."""


SCHEMA_ID = "theory_paper_v31_successor_cycle_commit_material"
SCHEMA_VERSION = "2.0.0"
DIGEST_FIELD = "successor_commit_material_digest"
COMMIT_ROOT = "successor-commit-v2"

SUPPORT_BINDING_KEYS = frozenset(
    {
        "clock_policy",
        "sentiment_source_registry",
        "sentiment_projection",
        "association_preregistration",
        "evaluation_contract",
        "fresh_qualification_bundle",
        "application_authority_projection",
    }
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "prepared_at",
        "cycle_permit_binding",
        "cycle_permit_digest",
        "active_authority_digest",
        "experiment_contract_digest",
        "research_checkpoint_digest_before_commit",
        "monitor_checkpoint_digest_before_commit",
        "authoring_packet_digest",
        "transport_evidence_binding",
        "assembly_bundle",
        "monitor_plan",
        "monitor_runtime_created_at",
        "scheduled_at",
        "support_bindings",
        "recovery_policy",
        "agent_reinvocation_allowed",
        "outcome_collection_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        DIGEST_FIELD,
    }
)


def successor_commit_material_ref_v2(cycle_index: int) -> str:
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_CYCLE_INVALID"
        )
    return f"{COMMIT_ROOT}/cycles/{cycle_index:04d}/commit-material.json"


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31SuccessorCycleCommitV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SuccessorCycleCommitV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31SuccessorCycleCommitV2Error(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31SuccessorCycleCommitV2Error(code)
    return normalized


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31SuccessorCycleCommitV2Error(code)
    return value


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V31SuccessorCycleCommitV2Error(code)
    normalized = {field: str(value[field]) for field in _BINDING_FIELDS}
    for field in ("relative_ref", "schema_id", "digest_field"):
        if not normalized[field].strip():
            raise V31SuccessorCycleCommitV2Error(code)
    _digest(normalized["semantic_digest"], code)
    _digest(normalized["physical_sha256"], code)
    return normalized


def _assert_non_executable(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if (
                key == "external_execution_authority"
                and nested != "NONE_LOCAL_SIMULATION"
            ):
                raise V31SuccessorCycleCommitV2Error(
                    "V31_SUCCESSOR_COMMIT_AUTHORITY_EXPANSION_FORBIDDEN"
                )
            if key in {
                "executable",
                "account_access",
                "order_submission",
                "credential_use",
                "funds_access",
                "portfolio_mutation",
            } and nested is True:
                raise V31SuccessorCycleCommitV2Error(
                    "V31_SUCCESSOR_COMMIT_EXECUTION_CAPABILITY_FORBIDDEN"
                )
            _assert_non_executable(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_non_executable(nested)


def build_v31_successor_cycle_commit_material_v2(
    *,
    run_id: str,
    cycle_index: int,
    prepared_at: str,
    cycle_permit_binding: Mapping[str, Any],
    active_authority_digest: str,
    experiment_contract: Mapping[str, Any],
    research_checkpoint_digest_before_commit: str,
    monitor_checkpoint_digest_before_commit: str,
    authoring_packet_digest: str,
    transport_evidence_binding: Mapping[str, Any],
    assembly_bundle: Mapping[str, Any],
    monitor_plan: Mapping[str, Any],
    monitor_runtime_created_at: str,
    scheduled_at: str,
    support_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal all data required to finish both owner commits without an Agent."""

    if not isinstance(run_id, str) or not run_id.strip():
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_RUN_ID_INVALID"
        )
    ref = successor_commit_material_ref_v2(cycle_index)
    del ref  # Validate the cycle without storing path authority in the document.
    prepared = _time(prepared_at, "V31_SUCCESSOR_COMMIT_TIME_INVALID")
    monitor_created = _time(
        monitor_runtime_created_at, "V31_SUCCESSOR_COMMIT_TIME_INVALID"
    )
    scheduled = _time(scheduled_at, "V31_SUCCESSOR_COMMIT_TIME_INVALID")
    if scheduled < prepared or monitor_created > scheduled:
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_TIME_ORDER_INVALID"
        )
    permit_binding = _binding(
        cycle_permit_binding, "V31_SUCCESSOR_COMMIT_PERMIT_BINDING_INVALID"
    )
    if (
        permit_binding["schema_id"]
        != "theory_paper_v31_experiment_cycle_permit"
        or permit_binding["digest_field"] != "cycle_permit_digest"
    ):
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_PERMIT_BINDING_INVALID"
        )
    authority_digest = _digest(
        active_authority_digest,
        "V31_SUCCESSOR_COMMIT_AUTHORITY_DIGEST_INVALID",
    )
    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    if (
        experiment_contract.get("run_id") != run_id
        or experiment_contract.get("cycle_protocol", {}).get(
            "accepted_cycle_count"
        )
        != 8
    ):
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_CONTRACT_IDENTITY_INVALID"
        )
    research_digest = _digest(
        research_checkpoint_digest_before_commit,
        "V31_SUCCESSOR_COMMIT_RESEARCH_DIGEST_INVALID",
    )
    monitor_digest = _digest(
        monitor_checkpoint_digest_before_commit,
        "V31_SUCCESSOR_COMMIT_MONITOR_DIGEST_INVALID",
    )
    packet_digest = _digest(
        authoring_packet_digest,
        "V31_SUCCESSOR_COMMIT_PACKET_DIGEST_INVALID",
    )
    evidence_binding = _binding(
        transport_evidence_binding,
        "V31_SUCCESSOR_COMMIT_TRANSPORT_BINDING_INVALID",
    )
    if (
        evidence_binding["schema_id"]
        != "theory_paper_v31_agent_transport_evidence"
        or evidence_binding["digest_field"] != "transport_evidence_digest"
    ):
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_TRANSPORT_BINDING_INVALID"
        )
    try:
        assembly_digest = verify_self_digest(
            assembly_bundle, "assembly_bundle_digest"
        )
        monitor_digest_semantic = verify_typed_path_monitor_plan(
            monitor_plan,
            experiment_contract=experiment_contract,
            expected_origin_bindings=monitor_plan["origin_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_EMBEDDED_ARTIFACT_INVALID"
        ) from exc
    if (
        assembly_bundle.get("run_id") != run_id
        or assembly_bundle.get("cycle_index") != cycle_index
        or monitor_plan.get("run_id") != run_id
        or monitor_plan.get("cycle_index") != cycle_index
        or monitor_plan.get("origin_bindings", {})
        .get("accepted_state", {})
        .get("digest")
        != assembly_bundle.get("expected_artifact_digests", {}).get(
            "STATE_ACCEPTED"
        )
        or not assembly_digest
        or not monitor_digest_semantic
    ):
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_EMBEDDED_IDENTITY_MISMATCH"
        )
    if not isinstance(support_bindings, Mapping) or set(
        support_bindings
    ) != SUPPORT_BINDING_KEYS:
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_SUPPORT_BINDINGS_INVALID"
        )
    normalized_support = {
        key: _binding(
            support_bindings[key],
            "V31_SUCCESSOR_COMMIT_SUPPORT_BINDINGS_INVALID",
        )
        for key in sorted(SUPPORT_BINDING_KEYS)
    }
    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle_index,
        "prepared_at": prepared_at,
        "cycle_permit_binding": permit_binding,
        "cycle_permit_digest": permit_binding["semantic_digest"],
        "active_authority_digest": authority_digest,
        "experiment_contract_digest": contract_digest,
        "research_checkpoint_digest_before_commit": research_digest,
        "monitor_checkpoint_digest_before_commit": monitor_digest,
        "authoring_packet_digest": packet_digest,
        "transport_evidence_binding": evidence_binding,
        "assembly_bundle": dict(assembly_bundle),
        "monitor_plan": dict(monitor_plan),
        "monitor_runtime_created_at": monitor_runtime_created_at,
        "scheduled_at": scheduled_at,
        "support_bindings": normalized_support,
        "recovery_policy": (
            "LOCAL_DETERMINISTIC_REPLAY_ONLY_NO_AGENT_NO_OUTCOME"
        ),
        "agent_reinvocation_allowed": False,
        "outcome_collection_allowed": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    _assert_non_executable(document)
    return self_digest(document, DIGEST_FIELD)


def verify_v31_successor_cycle_commit_material_v2(
    document: Mapping[str, Any],
    *,
    experiment_contract: Mapping[str, Any],
) -> str:
    """Rebuild the document exactly and reject any embedded drift."""

    if not isinstance(document, Mapping) or set(document) != _FIELDS:
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_DOCUMENT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        rebuilt = build_v31_successor_cycle_commit_material_v2(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            prepared_at=document["prepared_at"],
            cycle_permit_binding=document["cycle_permit_binding"],
            active_authority_digest=document["active_authority_digest"],
            experiment_contract=experiment_contract,
            research_checkpoint_digest_before_commit=document[
                "research_checkpoint_digest_before_commit"
            ],
            monitor_checkpoint_digest_before_commit=document[
                "monitor_checkpoint_digest_before_commit"
            ],
            authoring_packet_digest=document["authoring_packet_digest"],
            transport_evidence_binding=document[
                "transport_evidence_binding"
            ],
            assembly_bundle=document["assembly_bundle"],
            monitor_plan=document["monitor_plan"],
            monitor_runtime_created_at=document[
                "monitor_runtime_created_at"
            ],
            scheduled_at=document["scheduled_at"],
            support_bindings=document["support_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorCycleCommitV2Error):
            raise
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_DOCUMENT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V31SuccessorCycleCommitV2Error(
            "V31_SUCCESSOR_COMMIT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "COMMIT_ROOT",
    "DIGEST_FIELD",
    "SCHEMA_ID",
    "SUPPORT_BINDING_KEYS",
    "V31SuccessorCycleCommitV2Error",
    "build_v31_successor_cycle_commit_material_v2",
    "successor_commit_material_ref_v2",
    "verify_v31_successor_cycle_commit_material_v2",
]
