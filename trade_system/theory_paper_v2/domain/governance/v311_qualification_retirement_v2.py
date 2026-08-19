"""Write-once retirement contract for the isolated V3.1.1 qualification run."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Mapping

from ..contracts.canonical import self_digest, verify_self_digest
from .v31_successor_qualification_v2 import (
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
    verify_successor_monitor_qualification_v2,
    verify_successor_public_source_qualification_v2,
)
from .v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    verify_successor_codex_durable_qualification_v3,
)
from .v311_qualification_genesis_v2 import (
    V311QualificationGenesisV2Error,
    verify_v311_qualification_run_genesis_v2,
)
from ..v31_run_genesis import RUN_GENESIS_DIGEST_FIELD, RUN_GENESIS_SCHEMA_ID


class V311QualificationRetirementV2Error(ValueError):
    """The qualification run cannot be proven retired at exactly cycle one."""


QUALIFICATION_RETIREMENT_SCHEMA_ID = (
    "theory_paper_v311_qualification_run_retirement_v2"
)
QUALIFICATION_RETIREMENT_SCHEMA_VERSION = "2.0.0"
QUALIFICATION_RETIREMENT_DIGEST_FIELD = "qualification_retirement_digest"
QUALIFICATION_RETIREMENT_RELATIVE_NAME = "qualification-retirement.v2.json"

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_GATES = tuple(f"Q{index}" for index in range(9))
_FRESH_KEYS = (
    "public_source",
    "codex_durable_delivery",
    "outcome_monitor",
)
_BINDING_FIELDS = {
    "path",
    "schema_id",
    "digest_field",
    "semantic_digest",
    "physical_sha256",
}
_LOCAL_BINDING_FIELDS = {
    "relative_ref",
    "schema_id",
    "digest_field",
    "semantic_digest",
    "physical_sha256",
}


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V311QualificationRetirementV2Error(code)
    return value


def _safe_id(value: Any, code: str) -> str:
    result = _text(value, code)
    if _SAFE_ID.fullmatch(result) is None:
        raise V311QualificationRetirementV2Error(code)
    return result


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V311QualificationRetirementV2Error(code)
    return value


def _time(value: Any, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311QualificationRetirementV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V311QualificationRetirementV2Error(code)
    parsed = parsed.astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != text:
        raise V311QualificationRetirementV2Error(code)
    return parsed


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V311QualificationRetirementV2Error(code)
    result = {key: _text(value[key], code) for key in _BINDING_FIELDS}
    path = PurePosixPath(result["path"])
    if (
        "\\" in result["path"]
        or path.is_absolute()
        or path.as_posix() != result["path"]
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V311QualificationRetirementV2Error(code)
    _digest(result["semantic_digest"], code)
    _digest(result["physical_sha256"], code)
    return {key: result[key] for key in sorted(_BINDING_FIELDS)}


def _local_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _LOCAL_BINDING_FIELDS:
        raise V311QualificationRetirementV2Error(code)
    translated = {
        "path": value["relative_ref"],
        **{key: value[key] for key in _LOCAL_BINDING_FIELDS if key != "relative_ref"},
    }
    normalized = _binding(translated, code)
    return {
        "relative_ref": normalized["path"],
        "schema_id": normalized["schema_id"],
        "digest_field": normalized["digest_field"],
        "semantic_digest": normalized["semantic_digest"],
        "physical_sha256": normalized["physical_sha256"],
    }


def _retirement_constraints() -> dict[str, Any]:
    return {
        "accepted_cycle_count": 1,
        "accepted_cycle_counts_toward_target": False,
        "application_projection_authorized": False,
        "automation_authorized": False,
        "further_cycle_advance_authorized": False,
        "monitor_schedule_authorized": False,
        "existing_monitor_plan_retired_unresolved": True,
        "outcome_resolution_authorized": False,
        "qualification_authority_retired": True,
        "qualification_genesis_reuse_authorized": False,
        "supersedes_checkpoint_resume_flag": True,
        "target_authority_must_postdate_retirement": True,
    }


def _authority_boundary() -> dict[str, Any]:
    return {
        "account_access": False,
        "credential_access": False,
        "funds_access": False,
        "live_trading": False,
        "order_submission": False,
        "paper_trading": False,
        "public_data_only": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def build_v311_qualification_retirement_receipt_v2(
    *,
    retirement_id: str,
    retired_at: str,
    target_run_id: str,
    qualification_v3_chain: Mapping[str, Any],
    qualification_v3_document_bindings: Mapping[str, Mapping[str, Any]],
    qualification_run_genesis: Mapping[str, Any],
    qualification_run_genesis_binding: Mapping[str, Any],
    research_checkpoint: Mapping[str, Any],
    research_checkpoint_binding: Mapping[str, Any],
    monitor_checkpoint: Mapping[str, Any],
    monitor_checkpoint_binding: Mapping[str, Any],
    successor_qualifications: Mapping[str, Mapping[str, Any]],
    successor_qualification_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal the one accepted qualification cycle and revoke all further use."""

    retirement = _safe_id(retirement_id, "V311_RETIREMENT_ID_INVALID")
    retired = _time(retired_at, "V311_RETIREMENT_TIME_INVALID")
    target = _safe_id(target_run_id, "V311_RETIREMENT_TARGET_RUN_INVALID")
    if not isinstance(qualification_v3_chain, Mapping):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_QUALIFICATION_CHAIN_INVALID"
        )
    authority = qualification_v3_chain.get("authority")
    receipts = qualification_v3_chain.get("qualification_receipts")
    if not isinstance(authority, Mapping) or not isinstance(receipts, Mapping):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_QUALIFICATION_CHAIN_INVALID"
        )
    try:
        authority_digest = verify_self_digest(authority, "authority_digest")
    except (TypeError, ValueError) as exc:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_AUTHORITY_INVALID"
        ) from exc
    run = _safe_id(
        authority.get("authorized_run_id"), "V311_RETIREMENT_RUN_INVALID"
    )
    predecessor = _safe_id(
        successor_qualifications.get("public_source", {}).get(
            "predecessor_run_id"
        ),
        "V311_RETIREMENT_PREDECESSOR_INVALID",
    )
    if run == target or target == predecessor or run == predecessor:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_RUNS_NOT_DISTINCT"
        )
    try:
        genesis_evidence = verify_v311_qualification_run_genesis_v2(
            run_genesis=qualification_run_genesis,
            qualification_v3_chain=qualification_v3_chain,
            qualification_v3_document_bindings=qualification_v3_document_bindings,
        )
    except V311QualificationGenesisV2Error as exc:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_RUN_GENESIS_INVALID"
        ) from exc
    authority_ref = _binding(
        qualification_v3_document_bindings.get("authority"),
        "V311_RETIREMENT_AUTHORITY_BINDING_INVALID",
    )
    if (
        authority_ref["schema_id"]
        != "theory_paper_v31_current_research_authority"
        or authority_ref["digest_field"] != "authority_digest"
        or authority_ref["semantic_digest"] != authority_digest
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_AUTHORITY_BINDING_INVALID"
        )
    run_genesis_ref = _binding(
        qualification_run_genesis_binding,
        "V311_RETIREMENT_RUN_GENESIS_BINDING_INVALID",
    )
    if (
        run_genesis_ref["schema_id"] != RUN_GENESIS_SCHEMA_ID
        or run_genesis_ref["digest_field"] != RUN_GENESIS_DIGEST_FIELD
        or run_genesis_ref["semantic_digest"]
        != genesis_evidence["run_genesis_digest"]
        or run_genesis_ref["path"]
        != f"agent-cluster/experiments/{run}/genesis/run-genesis.json"
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_RUN_GENESIS_BINDING_INVALID"
        )
    genesis_authority_ref = _local_binding(
        genesis_evidence["authority_copy_binding"],
        "V311_RETIREMENT_GENESIS_AUTHORITY_BINDING_INVALID",
    )
    if tuple(receipts) != _GATES:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_Q0_Q8_INVALID"
        )
    q0_q8: dict[str, str] = {}
    for gate in _GATES:
        try:
            q0_q8[gate] = verify_self_digest(
                receipts[gate], "qualification_receipt_digest"
            )
        except (TypeError, ValueError) as exc:
            raise V311QualificationRetirementV2Error(
                "V311_RETIREMENT_Q0_Q8_INVALID"
            ) from exc
    if (
        not isinstance(successor_qualifications, Mapping)
        or tuple(successor_qualifications) != _FRESH_KEYS
        or not isinstance(successor_qualification_bindings, Mapping)
        or tuple(successor_qualification_bindings) != _FRESH_KEYS
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_FRESH_QUALIFICATIONS_INVALID"
        )
    try:
        fresh_digests = {
            "public_source": verify_successor_public_source_qualification_v2(
                successor_qualifications["public_source"]
            ),
            "codex_durable_delivery": verify_successor_codex_durable_qualification_v3(
                successor_qualifications["codex_durable_delivery"]
            ),
            "outcome_monitor": verify_successor_monitor_qualification_v2(
                successor_qualifications["outcome_monitor"]
            ),
        }
    except (TypeError, ValueError) as exc:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_FRESH_QUALIFICATIONS_INVALID"
        ) from exc
    fresh_bindings = {
        name: _binding(
            successor_qualification_bindings[name],
            "V311_RETIREMENT_FRESH_BINDING_INVALID",
        )
        for name in _FRESH_KEYS
    }
    expected_digest_fields = {
        "public_source": SOURCE_QUALIFICATION_DIGEST_FIELD,
        "codex_durable_delivery": CODEX_QUALIFICATION_V3_DIGEST_FIELD,
        "outcome_monitor": MONITOR_QUALIFICATION_DIGEST_FIELD,
    }
    if any(
        fresh_bindings[name]["digest_field"] != expected_digest_fields[name]
        or fresh_bindings[name]["semantic_digest"] != fresh_digests[name]
        for name in _FRESH_KEYS
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_FRESH_BINDING_INVALID"
        )
    codex = successor_qualifications["codex_durable_delivery"]
    source = successor_qualifications["public_source"]
    if any(
        document.get("run_id") != run
        or document.get("predecessor_run_id") != predecessor
        or document.get("authority_digest") != authority_digest
        for document in successor_qualifications.values()
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_FRESH_CROSS_BINDING_INVALID"
        )
    if any(
        document.get("authority_binding") != genesis_authority_ref
        for document in successor_qualifications.values()
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_FRESH_GENESIS_AUTHORITY_MISMATCH"
        )
    if codex.get("cycle_index") != 1:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_EXACT_CYCLE_ONE_REQUIRED"
        )
    try:
        checkpoint_digest = verify_self_digest(
            research_checkpoint, "checkpoint_digest"
        )
    except (TypeError, ValueError) as exc:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_CHECKPOINT_INVALID"
        ) from exc
    checkpoint_ref = _binding(
        research_checkpoint_binding,
        "V311_RETIREMENT_CHECKPOINT_BINDING_INVALID",
    )
    accepted_state_digest = _digest(
        codex.get("accepted_state_digest"),
        "V311_RETIREMENT_ACCEPTED_STATE_INVALID",
    )
    expected_checkpoint_path = (
        f"agent-cluster/experiments/{run}/checkpoint.json"
    )
    if (
        checkpoint_ref["path"] != expected_checkpoint_path
        or checkpoint_ref["schema_id"]
        != "theory_paper_v31_research_checkpoint"
        or checkpoint_ref["digest_field"] != "checkpoint_digest"
        or checkpoint_ref["semantic_digest"] != checkpoint_digest
        or research_checkpoint.get("run_id") != run
        or research_checkpoint.get("status") != "READY_FOR_CYCLE"
        or research_checkpoint.get("completed_cycles") != 1
        or research_checkpoint.get("next_cycle_index") != 2
        or research_checkpoint.get("accepted_state_ref")
        != "cycles/0001/accepted-research-state.json"
        or research_checkpoint.get("accepted_state_digest")
        != accepted_state_digest
        or research_checkpoint.get("current_authority_digest")
        != authority_digest
        or research_checkpoint.get("current_authority_ref")
        != "genesis/current-authority.json"
        or research_checkpoint.get("run_genesis_ref")
        != "genesis/run-genesis.json"
        or research_checkpoint.get("run_genesis_digest")
        != genesis_evidence["run_genesis_digest"]
        or research_checkpoint.get("resume_allowed") is not True
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_CHECKPOINT_NOT_EXACT_CYCLE_ONE"
        )
    try:
        monitor_checkpoint_digest = verify_self_digest(
            monitor_checkpoint, "checkpoint_digest"
        )
    except (TypeError, ValueError) as exc:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_MONITOR_CHECKPOINT_INVALID"
        ) from exc
    monitor_checkpoint_ref = _binding(
        monitor_checkpoint_binding,
        "V311_RETIREMENT_MONITOR_CHECKPOINT_BINDING_INVALID",
    )
    expected_monitor_path = (
        f"agent-cluster/experiments/{run}/monitor/checkpoint.json"
    )
    if (
        monitor_checkpoint_ref["path"] != expected_monitor_path
        or monitor_checkpoint_ref["schema_id"]
        != "theory_paper_v31_monitor_checkpoint"
        or monitor_checkpoint_ref["digest_field"] != "checkpoint_digest"
        or monitor_checkpoint_ref["semantic_digest"]
        != monitor_checkpoint_digest
        or monitor_checkpoint.get("run_id") != run
        or monitor_checkpoint.get("status") != "ACTIVE"
        or monitor_checkpoint.get("resume_allowed") is not True
        or len(monitor_checkpoint.get("plan_bindings", [])) != 1
        or monitor_checkpoint.get("resolution_attempt_bindings") != []
        or monitor_checkpoint.get("outcome_bindings") != []
        or monitor_checkpoint.get("failure_ref") is not None
        or monitor_checkpoint.get("failure_digest") is not None
        or monitor_checkpoint.get("experiment_contract_digest")
        != qualification_v3_chain["experiment_contract"].get(
            "experiment_contract_digest"
        )
        or monitor_checkpoint.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or monitor_checkpoint.get("executable") is not False
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_MONITOR_NOT_EXACT_UNRESOLVED_CYCLE_ONE"
        )
    qualified_times = [
        _time(
            successor_qualifications[name].get("qualified_at"),
            "V311_RETIREMENT_QUALIFIED_TIME_INVALID",
        )
        for name in _FRESH_KEYS
    ]
    if (
        retired < max(qualified_times)
        or retired
        < _time(
            research_checkpoint.get("updated_at"),
            "V311_RETIREMENT_CHECKPOINT_TIME_INVALID",
        )
        or retired
        < _time(
            monitor_checkpoint.get("updated_at"),
            "V311_RETIREMENT_MONITOR_CHECKPOINT_TIME_INVALID",
        )
        or retired
        > _time(source.get("expires_at"), "V311_RETIREMENT_SOURCE_EXPIRED")
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_CHRONOLOGY_INVALID"
        )
    snapshot = {
        "accepted_state_digest": accepted_state_digest,
        "accepted_state_ref": research_checkpoint["accepted_state_ref"],
        "checkpoint_digest": checkpoint_digest,
        "completed_cycles": 1,
        "current_authority_digest": authority_digest,
        "current_authority_ref": "genesis/current-authority.json",
        "next_cycle_index": 2,
        "resume_allowed_before_retirement": True,
        "revision": research_checkpoint["revision"],
        "status_before_retirement": "READY_FOR_CYCLE",
        "run_genesis_digest": genesis_evidence["run_genesis_digest"],
        "run_genesis_ref": "genesis/run-genesis.json",
        "updated_at": research_checkpoint["updated_at"],
    }
    document = {
        "schema_id": QUALIFICATION_RETIREMENT_SCHEMA_ID,
        "schema_version": QUALIFICATION_RETIREMENT_SCHEMA_VERSION,
        "retirement_id": retirement,
        "retired_at": retired_at,
        "status": "RETIRED_QUALIFICATION_RUN_WRITE_ONCE",
        "qualification_run_id": run,
        "target_run_id": target,
        "predecessor_run_id": predecessor,
        "qualification_authority_digest": authority_digest,
        "qualification_authority_recorded_at": authority["recorded_at"],
        "standard_qualification_authority_binding": authority_ref,
        "qualification_run_genesis_binding": run_genesis_ref,
        "qualification_run_genesis_digest": genesis_evidence[
            "run_genesis_digest"
        ],
        "genesis_authority_copy_binding": genesis_authority_ref,
        "accepted_cycle_index": 1,
        "accepted_state_digest": accepted_state_digest,
        "q0_q8_receipt_digests": q0_q8,
        "fresh_qualification_digests": fresh_digests,
        "fresh_qualification_bindings": fresh_bindings,
        "research_checkpoint_binding": checkpoint_ref,
        "research_checkpoint_snapshot": snapshot,
        "monitor_checkpoint_binding": monitor_checkpoint_ref,
        "monitor_checkpoint_snapshot": {
            "checkpoint_digest": monitor_checkpoint_digest,
            "status_before_retirement": "ACTIVE",
            "resume_allowed_before_retirement": True,
            "planned_cycles": 1,
            "resolution_attempts": 0,
            "resolved_outcomes": 0,
            "updated_at": monitor_checkpoint["updated_at"],
        },
        "retirement_constraints": _retirement_constraints(),
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, QUALIFICATION_RETIREMENT_DIGEST_FIELD)


def verify_v311_qualification_retirement_receipt_v2(
    document: Mapping[str, Any],
) -> str:
    """Verify sealed retirement semantics before any target chain is opened."""

    if not isinstance(document, Mapping):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, QUALIFICATION_RETIREMENT_DIGEST_FIELD
        )
        _safe_id(document["retirement_id"], "V311_RETIREMENT_ID_INVALID")
        _time(document["retired_at"], "V311_RETIREMENT_TIME_INVALID")
        run = _safe_id(
            document["qualification_run_id"], "V311_RETIREMENT_RUN_INVALID"
        )
        target = _safe_id(
            document["target_run_id"], "V311_RETIREMENT_TARGET_RUN_INVALID"
        )
        predecessor = _safe_id(
            document["predecessor_run_id"],
            "V311_RETIREMENT_PREDECESSOR_INVALID",
        )
        _digest(
            document["qualification_authority_digest"],
            "V311_RETIREMENT_AUTHORITY_INVALID",
        )
        _time(
            document["qualification_authority_recorded_at"],
            "V311_RETIREMENT_AUTHORITY_TIME_INVALID",
        )
        _digest(
            document["qualification_run_genesis_digest"],
            "V311_RETIREMENT_RUN_GENESIS_DIGEST_INVALID",
        )
        _binding(
            document["standard_qualification_authority_binding"],
            "V311_RETIREMENT_AUTHORITY_BINDING_INVALID",
        )
        _binding(
            document["qualification_run_genesis_binding"],
            "V311_RETIREMENT_RUN_GENESIS_BINDING_INVALID",
        )
        _local_binding(
            document["genesis_authority_copy_binding"],
            "V311_RETIREMENT_GENESIS_AUTHORITY_BINDING_INVALID",
        )
        _binding(
            document["research_checkpoint_binding"],
            "V311_RETIREMENT_CHECKPOINT_BINDING_INVALID",
        )
        _binding(
            document["monitor_checkpoint_binding"],
            "V311_RETIREMENT_MONITOR_CHECKPOINT_BINDING_INVALID",
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311QualificationRetirementV2Error):
            raise
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_RECEIPT_INVALID"
        ) from exc
    required = {
        "schema_id",
        "schema_version",
        "retirement_id",
        "retired_at",
        "status",
        "qualification_run_id",
        "target_run_id",
        "predecessor_run_id",
        "qualification_authority_digest",
        "qualification_authority_recorded_at",
        "standard_qualification_authority_binding",
        "qualification_run_genesis_binding",
        "qualification_run_genesis_digest",
        "genesis_authority_copy_binding",
        "accepted_cycle_index",
        "accepted_state_digest",
        "q0_q8_receipt_digests",
        "fresh_qualification_digests",
        "fresh_qualification_bindings",
        "research_checkpoint_binding",
        "research_checkpoint_snapshot",
        "monitor_checkpoint_binding",
        "monitor_checkpoint_snapshot",
        "retirement_constraints",
        "authority_boundary",
        QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    }
    snapshot = document.get("research_checkpoint_snapshot")
    monitor_snapshot = document.get("monitor_checkpoint_snapshot")
    if (
        set(document) != required
        or document.get("schema_id") != QUALIFICATION_RETIREMENT_SCHEMA_ID
        or document.get("schema_version")
        != QUALIFICATION_RETIREMENT_SCHEMA_VERSION
        or document.get("status")
        != "RETIRED_QUALIFICATION_RUN_WRITE_ONCE"
        or run in {target, predecessor}
        or target == predecessor
        or document.get("accepted_cycle_index") != 1
        or tuple(document.get("q0_q8_receipt_digests", {})) != _GATES
        or tuple(document.get("fresh_qualification_digests", {}))
        != _FRESH_KEYS
        or tuple(document.get("fresh_qualification_bindings", {}))
        != _FRESH_KEYS
        or not isinstance(snapshot, Mapping)
        or not isinstance(monitor_snapshot, Mapping)
        or snapshot.get("completed_cycles") != 1
        or snapshot.get("next_cycle_index") != 2
        or snapshot.get("accepted_state_digest")
        != document.get("accepted_state_digest")
        or snapshot.get("current_authority_digest")
        != document.get("qualification_authority_digest")
        or snapshot.get("current_authority_ref")
        != "genesis/current-authority.json"
        or snapshot.get("run_genesis_ref") != "genesis/run-genesis.json"
        or snapshot.get("run_genesis_digest")
        != document.get("qualification_run_genesis_digest")
        or monitor_snapshot.get("status_before_retirement") != "ACTIVE"
        or monitor_snapshot.get("planned_cycles") != 1
        or monitor_snapshot.get("resolution_attempts") != 0
        or monitor_snapshot.get("resolved_outcomes") != 0
        or monitor_snapshot.get("checkpoint_digest")
        != document.get("monitor_checkpoint_binding", {}).get(
            "semantic_digest"
        )
        or document.get("genesis_authority_copy_binding", {}).get(
            "semantic_digest"
        )
        != document.get("qualification_authority_digest")
        or document.get("retirement_constraints") != _retirement_constraints()
        or document.get("authority_boundary") != _authority_boundary()
        or any(
            _HEX_64.fullmatch(str(value)) is None
            for value in document["q0_q8_receipt_digests"].values()
        )
        or any(
            _HEX_64.fullmatch(str(value)) is None
            for value in document["fresh_qualification_digests"].values()
        )
    ):
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_RECEIPT_INVALID"
        )
    for name in _FRESH_KEYS:
        binding = _binding(
            document["fresh_qualification_bindings"][name],
            "V311_RETIREMENT_FRESH_BINDING_INVALID",
        )
        if binding["semantic_digest"] != document[
            "fresh_qualification_digests"
        ][name]:
            raise V311QualificationRetirementV2Error(
                "V311_RETIREMENT_FRESH_BINDING_INVALID"
            )
    unsigned = dict(document)
    unsigned.pop(QUALIFICATION_RETIREMENT_DIGEST_FIELD, None)
    rebuilt = self_digest(unsigned, QUALIFICATION_RETIREMENT_DIGEST_FIELD)
    if rebuilt != dict(document) or supplied != rebuilt[QUALIFICATION_RETIREMENT_DIGEST_FIELD]:
        raise V311QualificationRetirementV2Error(
            "V311_RETIREMENT_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "QUALIFICATION_RETIREMENT_DIGEST_FIELD",
    "QUALIFICATION_RETIREMENT_RELATIVE_NAME",
    "QUALIFICATION_RETIREMENT_SCHEMA_ID",
    "QUALIFICATION_RETIREMENT_SCHEMA_VERSION",
    "V311QualificationRetirementV2Error",
    "build_v311_qualification_retirement_receipt_v2",
    "verify_v311_qualification_retirement_receipt_v2",
]
