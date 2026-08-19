"""Pure contracts for V3.2 read-only supervision and bounded recovery.

The supervising Agent is an observer, not a second Strategy Agent or a second
controller.  It may classify evidence and recommend one frozen disposition.
Only deterministic work reconstructed from already sealed bytes may be
completed inside the same run.  Network, Agent, semantic, authority and future
outcome retries are deliberately outside that allow-list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest


class V32RecoverySupervisionError(ValueError):
    """A supervision or recovery invariant failed closed."""


SCHEMA_VERSION = "1.0.0"
POLICY_SCHEMA_ID = "theory_paper_v32_recovery_supervision_policy_v1"
POLICY_DIGEST_FIELD = "recovery_supervision_policy_digest"
OBSERVATION_SCHEMA_ID = "theory_paper_v32_supervisor_observation_v1"
OBSERVATION_DIGEST_FIELD = "supervisor_observation_digest"
RECOVERY_SCHEMA_ID = "theory_paper_v32_deterministic_recovery_receipt_v1"
RECOVERY_DIGEST_FIELD = "deterministic_recovery_receipt_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

SAME_RUN_AUTO_REPAIR_ALLOWLIST = (
    "COMPILE_AND_COMMIT_FROM_SEALED_AGENT_DELIVERY_AND_CONSUMPTION",
    "COMPLETE_SUPERVISOR_CAS_FROM_VERIFIED_CHILD_STORE",
    "FINALIZE_WRITE_ONCE_CAS_FROM_SEALED_INTENT",
    "MATERIALIZE_COMPACTION_FROM_FROZEN_MANIFEST_AND_IDENTICAL_BYTES",
    "MATERIALIZE_OUTCOME_SCHEDULE_FROM_SEALED_ACCEPTED_STATE",
    "PARSE_AND_COMMIT_FROM_SEALED_RAW_AND_BATCH_INTENT",
    "REBUILD_POINTER_OR_INDEX_FROM_UNIQUE_PREDECESSOR_SUCCESSOR",
    "RENDER_AUDIT_FROM_SEALED_ACCEPTANCE",
)
PREQUALIFICATION_VERSIONED_REPAIR_ALLOWLIST = (
    "CONTEXT_SHARDING_IMPLEMENTATION",
    "LOCAL_ADAPTER_CONFIGURATION",
    "LOCAL_PATH_OR_PERMISSION",
    "MONITOR_CONFIGURATION",
    "PUBLIC_TRANSPORT_CONFIGURATION",
)
FORBIDDEN_RECOVERY_ACTIONS = (
    "BACKFILL_PRIOR_CYCLE",
    "CHANGE_AUTHORITY_THEORY_OR_EVALUATION_MID_RUN",
    "READ_FUTURE_OUTCOME",
    "REWRITE_SEALED_OR_ACCEPTED_BYTES",
    "SECOND_AGENT_ATTEMPT_WITHIN_STAGE",
    "SECOND_NETWORK_ATTEMPT_WITHIN_SEALED_CYCLE",
    "USE_ACCOUNT_CREDENTIAL_ORDER_OR_FUNDS",
)

SEVERITIES = ("INFO", "WARNING", "STOP")
LANES = (
    "WORKSPACE",
    "AUTHORITY",
    "SOURCE",
    "CONTEXT",
    "AGENT",
    "COMMIT",
    "OUTCOME",
    "AUDIT",
    "AUTOMATION",
)
DISPOSITIONS = (
    "NO_ACTION",
    "SAME_RUN_DETERMINISTIC_RECOVERY_ALLOWED",
    "PREQUALIFICATION_VERSIONED_REPAIR_REQUIRED",
    "FUTURE_ONLY_REVISION_REQUIRED",
    "SUCCESSOR_AUTHORITY_REQUIRED",
    "HUMAN_DATA_GAP_REQUIRED",
    "PERMANENT_FAIL_CLOSED",
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {"relative_ref", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_BOUNDARY_FIELDS = frozenset(
    {
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "paper_trading",
        "live_trading",
        "order_submission",
        "credential_use",
        "funds_access",
        "portfolio_mutation",
        "future_outcome_access",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "policy_id",
        "frozen_at",
        "supervisor_role",
        "supervisor_is_advisory_only",
        "supervisor_may_mutate_state",
        "supervisor_may_start_agent_stage",
        "supervisor_is_execution_risk_supervisor",
        "single_strategy_agent_owner",
        "same_run_auto_repair_allowlist",
        "prequalification_versioned_repair_allowlist",
        "forbidden_recovery_actions",
        "semantic_or_environment_change_rule",
        "authority_theory_evaluation_change_rule",
        "sealed_state_rule",
        "data_gap_rule",
        *_BOUNDARY_FIELDS,
        POLICY_DIGEST_FIELD,
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "observation_id",
        "policy_digest",
        "run_id",
        "cycle_index",
        "observed_at",
        "lane",
        "severity",
        "failure_code",
        "summary",
        "evidence_bindings",
        "disposition",
        "proposed_action",
        "reason",
        "recovery_authority_granted",
        "state_mutation_performed",
        "network_request_performed",
        "agent_attempt_performed",
        *_BOUNDARY_FIELDS,
        OBSERVATION_DIGEST_FIELD,
    }
)
_RECOVERY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "receipt_id",
        "policy_digest",
        "supervisor_observation_digest",
        "run_id",
        "cycle_index",
        "action",
        "started_at",
        "completed_at",
        "input_bindings",
        "output_bindings",
        "result",
        "state_change_boundaries",
        "network_request_count",
        "agent_attempt_count",
        "outcome_read_count",
        "semantic_change",
        "sealed_or_accepted_bytes_mutated",
        "new_market_fact_created",
        *_BOUNDARY_FIELDS,
        RECOVERY_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32RecoverySupervisionError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32RecoverySupervisionError(code)
    return value


def _time(value: Any, code: str) -> str:
    candidate = _text(value, code)
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32RecoverySupervisionError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != candidate
    ):
        raise V32RecoverySupervisionError(code)
    return candidate


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _boundary(*, future_outcome_access: bool = False) -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_use": False,
        "funds_access": False,
        "portfolio_mutation": False,
        "future_outcome_access": future_outcome_access,
    }


def _verify_boundary(document: Mapping[str, Any], code: str) -> None:
    if any(document.get(key) != value for key, value in _boundary().items()):
        raise V32RecoverySupervisionError(code)


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32RecoverySupervisionError(code)
    relative_ref = _text(value.get("relative_ref"), code)
    path = PurePosixPath(relative_ref)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise V32RecoverySupervisionError(code)
    return {
        "relative_ref": relative_ref,
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def _bindings(value: Any, code: str, *, allow_empty: bool) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32RecoverySupervisionError(code)
    result = [_binding(item, code) for item in value]
    if (
        (not allow_empty and not result)
        or result != sorted(result, key=lambda row: row["relative_ref"])
        or len({row["relative_ref"] for row in result}) != len(result)
    ):
        raise V32RecoverySupervisionError(code)
    return result


def build_v32_recovery_supervision_policy_v1(
    *, policy_id: str, frozen_at: str
) -> dict[str, Any]:
    return self_digest(
        {
            "schema_id": POLICY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "policy_id": _text(policy_id, "V32_RECOVERY_POLICY_ID_INVALID"),
            "frozen_at": _time(frozen_at, "V32_RECOVERY_POLICY_TIME_INVALID"),
            "supervisor_role": "READ_ONLY_INDEPENDENT_OBSERVER",
            "supervisor_is_advisory_only": True,
            "supervisor_may_mutate_state": False,
            "supervisor_may_start_agent_stage": False,
            "supervisor_is_execution_risk_supervisor": False,
            "single_strategy_agent_owner": True,
            "same_run_auto_repair_allowlist": list(SAME_RUN_AUTO_REPAIR_ALLOWLIST),
            "prequalification_versioned_repair_allowlist": list(
                PREQUALIFICATION_VERSIONED_REPAIR_ALLOWLIST
            ),
            "forbidden_recovery_actions": list(FORBIDDEN_RECOVERY_ACTIONS),
            "semantic_or_environment_change_rule": (
                "VERSION_COMMIT_TEST_AND_REQUALIFY_BEFORE_A_FUTURE_BOUNDARY"
            ),
            "authority_theory_evaluation_change_rule": (
                "NEW_EXPLICIT_USER_APPROVAL_AND_SUCCESSOR_AUTHORITY_REQUIRED"
            ),
            "sealed_state_rule": (
                "ONLY_IDEMPOTENT_DERIVATION_OR_FINALIZATION_FROM_VERIFIED_SEALED_BYTES"
            ),
            "data_gap_rule": (
                "OBJECTIVE_UNKNOWN_PLUS_HUMAN_PLAN_FUTURE_ONLY_NO_BACKFILL"
            ),
            **_boundary(),
        },
        POLICY_DIGEST_FIELD,
    )


def verify_v32_recovery_supervision_policy_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _POLICY_FIELDS:
        raise V32RecoverySupervisionError("V32_RECOVERY_POLICY_INVALID")
    try:
        supplied = verify_self_digest(document, POLICY_DIGEST_FIELD)
        rebuilt = build_v32_recovery_supervision_policy_v1(
            policy_id=document["policy_id"], frozen_at=document["frozen_at"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32RecoverySupervisionError):
            raise
        raise V32RecoverySupervisionError("V32_RECOVERY_POLICY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[POLICY_DIGEST_FIELD]:
        raise V32RecoverySupervisionError("V32_RECOVERY_POLICY_INVALID")
    _verify_boundary(document, "V32_RECOVERY_POLICY_BOUNDARY_INVALID")
    return supplied


def build_v32_supervisor_observation_v1(
    *,
    observation_id: str,
    policy: Mapping[str, Any],
    run_id: str,
    cycle_index: int,
    observed_at: str,
    lane: str,
    severity: str,
    failure_code: str,
    summary: str,
    evidence_bindings: Sequence[Mapping[str, Any]],
    disposition: str,
    proposed_action: str,
    reason: str,
) -> dict[str, Any]:
    policy_digest = verify_v32_recovery_supervision_policy_v1(policy)
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or not 0 <= cycle_index <= 16:
        raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_CYCLE_INVALID")
    if lane not in LANES or severity not in SEVERITIES or disposition not in DISPOSITIONS:
        raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_CLASS_INVALID")
    action = _text(proposed_action, "V32_SUPERVISOR_OBSERVATION_ACTION_INVALID")
    if disposition == "SAME_RUN_DETERMINISTIC_RECOVERY_ALLOWED":
        if action not in SAME_RUN_AUTO_REPAIR_ALLOWLIST:
            raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_ACTION_INVALID")
    elif disposition == "PREQUALIFICATION_VERSIONED_REPAIR_REQUIRED":
        if action not in PREQUALIFICATION_VERSIONED_REPAIR_ALLOWLIST:
            raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_ACTION_INVALID")
    elif action in SAME_RUN_AUTO_REPAIR_ALLOWLIST:
        raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_ACTION_INVALID")
    return self_digest(
        {
            "schema_id": OBSERVATION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "observation_id": _text(observation_id, "V32_SUPERVISOR_OBSERVATION_ID_INVALID"),
            "policy_digest": policy_digest,
            "run_id": _text(run_id, "V32_SUPERVISOR_OBSERVATION_RUN_INVALID"),
            "cycle_index": cycle_index,
            "observed_at": _time(observed_at, "V32_SUPERVISOR_OBSERVATION_TIME_INVALID"),
            "lane": lane,
            "severity": severity,
            "failure_code": _text(failure_code, "V32_SUPERVISOR_OBSERVATION_FAILURE_INVALID"),
            "summary": _text(summary, "V32_SUPERVISOR_OBSERVATION_SUMMARY_INVALID"),
            "evidence_bindings": _bindings(
                evidence_bindings,
                "V32_SUPERVISOR_OBSERVATION_EVIDENCE_INVALID",
                allow_empty=False,
            ),
            "disposition": disposition,
            "proposed_action": action,
            "reason": _text(reason, "V32_SUPERVISOR_OBSERVATION_REASON_INVALID"),
            "recovery_authority_granted": False,
            "state_mutation_performed": False,
            "network_request_performed": False,
            "agent_attempt_performed": False,
            **_boundary(),
        },
        OBSERVATION_DIGEST_FIELD,
    )


def verify_v32_supervisor_observation_v1(
    document: Mapping[str, Any], *, policy: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _OBSERVATION_FIELDS:
        raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_INVALID")
    try:
        supplied = verify_self_digest(document, OBSERVATION_DIGEST_FIELD)
        rebuilt = build_v32_supervisor_observation_v1(
            observation_id=document["observation_id"],
            policy=policy,
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            observed_at=document["observed_at"],
            lane=document["lane"],
            severity=document["severity"],
            failure_code=document["failure_code"],
            summary=document["summary"],
            evidence_bindings=document["evidence_bindings"],
            disposition=document["disposition"],
            proposed_action=document["proposed_action"],
            reason=document["reason"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32RecoverySupervisionError):
            raise
        raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[OBSERVATION_DIGEST_FIELD]:
        raise V32RecoverySupervisionError("V32_SUPERVISOR_OBSERVATION_INVALID")
    _verify_boundary(document, "V32_SUPERVISOR_OBSERVATION_BOUNDARY_INVALID")
    return supplied


def build_v32_deterministic_recovery_receipt_v1(
    *,
    receipt_id: str,
    policy: Mapping[str, Any],
    observation: Mapping[str, Any],
    action: str,
    started_at: str,
    completed_at: str,
    input_bindings: Sequence[Mapping[str, Any]],
    output_bindings: Sequence[Mapping[str, Any]],
    result: str,
    state_change_boundaries: int,
) -> dict[str, Any]:
    policy_digest = verify_v32_recovery_supervision_policy_v1(policy)
    observation_digest = verify_v32_supervisor_observation_v1(
        observation, policy=policy
    )
    if observation["disposition"] != "SAME_RUN_DETERMINISTIC_RECOVERY_ALLOWED":
        raise V32RecoverySupervisionError("V32_RECOVERY_NOT_AUTHORIZED_BY_CLASSIFICATION")
    if action not in SAME_RUN_AUTO_REPAIR_ALLOWLIST or action != observation["proposed_action"]:
        raise V32RecoverySupervisionError("V32_RECOVERY_ACTION_INVALID")
    start = _moment(started_at, "V32_RECOVERY_TIME_INVALID")
    completed = _moment(completed_at, "V32_RECOVERY_TIME_INVALID")
    if completed < start:
        raise V32RecoverySupervisionError("V32_RECOVERY_TIME_INVALID")
    if result not in {"COMPLETED", "NO_CHANGE_NEEDED"}:
        raise V32RecoverySupervisionError("V32_RECOVERY_RESULT_INVALID")
    if (
        isinstance(state_change_boundaries, bool)
        or not isinstance(state_change_boundaries, int)
        or state_change_boundaries not in {0, 1}
    ):
        raise V32RecoverySupervisionError("V32_RECOVERY_BOUNDARY_COUNT_INVALID")
    return self_digest(
        {
            "schema_id": RECOVERY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "receipt_id": _text(receipt_id, "V32_RECOVERY_RECEIPT_ID_INVALID"),
            "policy_digest": policy_digest,
            "supervisor_observation_digest": observation_digest,
            "run_id": observation["run_id"],
            "cycle_index": observation["cycle_index"],
            "action": action,
            "started_at": _time(started_at, "V32_RECOVERY_TIME_INVALID"),
            "completed_at": _time(completed_at, "V32_RECOVERY_TIME_INVALID"),
            "input_bindings": _bindings(
                input_bindings, "V32_RECOVERY_INPUT_BINDING_INVALID", allow_empty=False
            ),
            "output_bindings": _bindings(
                output_bindings, "V32_RECOVERY_OUTPUT_BINDING_INVALID", allow_empty=False
            ),
            "result": result,
            "state_change_boundaries": state_change_boundaries,
            "network_request_count": 0,
            "agent_attempt_count": 0,
            "outcome_read_count": 0,
            "semantic_change": False,
            "sealed_or_accepted_bytes_mutated": False,
            "new_market_fact_created": False,
            **_boundary(),
        },
        RECOVERY_DIGEST_FIELD,
    )


def verify_v32_deterministic_recovery_receipt_v1(
    document: Mapping[str, Any], *, policy: Mapping[str, Any], observation: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _RECOVERY_FIELDS:
        raise V32RecoverySupervisionError("V32_RECOVERY_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, RECOVERY_DIGEST_FIELD)
        rebuilt = build_v32_deterministic_recovery_receipt_v1(
            receipt_id=document["receipt_id"],
            policy=policy,
            observation=observation,
            action=document["action"],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            input_bindings=document["input_bindings"],
            output_bindings=document["output_bindings"],
            result=document["result"],
            state_change_boundaries=document["state_change_boundaries"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32RecoverySupervisionError):
            raise
        raise V32RecoverySupervisionError("V32_RECOVERY_RECEIPT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[RECOVERY_DIGEST_FIELD]:
        raise V32RecoverySupervisionError("V32_RECOVERY_RECEIPT_INVALID")
    _verify_boundary(document, "V32_RECOVERY_RECEIPT_BOUNDARY_INVALID")
    return supplied


__all__ = [
    "DISPOSITIONS",
    "FORBIDDEN_RECOVERY_ACTIONS",
    "OBSERVATION_DIGEST_FIELD",
    "OBSERVATION_SCHEMA_ID",
    "POLICY_DIGEST_FIELD",
    "POLICY_SCHEMA_ID",
    "PREQUALIFICATION_VERSIONED_REPAIR_ALLOWLIST",
    "RECOVERY_DIGEST_FIELD",
    "RECOVERY_SCHEMA_ID",
    "SAME_RUN_AUTO_REPAIR_ALLOWLIST",
    "V32RecoverySupervisionError",
    "build_v32_deterministic_recovery_receipt_v1",
    "build_v32_recovery_supervision_policy_v1",
    "build_v32_supervisor_observation_v1",
    "verify_v32_deterministic_recovery_receipt_v1",
    "verify_v32_recovery_supervision_policy_v1",
    "verify_v32_supervisor_observation_v1",
]
