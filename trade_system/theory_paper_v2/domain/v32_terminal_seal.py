"""Pure contracts for the immutable V3.2 prospective-run terminal seal.

The terminal seal is research evidence only.  It grants no execution authority
and cannot read a market, account, order, credential, position, or portfolio.
The active genesis pointer remains immutable; completion is published through a
separate terminal pointer after all 49 required human-audit directories exist.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest


class V32TerminalSealError(ValueError):
    """A terminal receipt or pointer invariant failed closed."""


SCHEMA_VERSION = "1.0.0"
TERMINAL_RECEIPT_SCHEMA_ID = "theory_paper_v32_terminal_receipt_v1"
TERMINAL_RECEIPT_DIGEST_FIELD = "v32_terminal_receipt_digest"
TERMINAL_POINTER_SCHEMA_ID = "theory_paper_v32_terminal_pointer_v1"
TERMINAL_POINTER_DIGEST_FIELD = "v32_terminal_pointer_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
TOTAL_ANALYSIS_CYCLES = 16
TOTAL_OUTCOMES = 48
REQUIRED_AUDIT_DIRECTORY_COUNT = 49

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_BINDING_FIELDS = frozenset(
    {"relative_ref", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_AUDIT_ROW_FIELDS = frozenset({"boundary_type", "cycle_index", "binding"})
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
        "status",
        "sealed_at",
        "run_genesis_binding",
        "active_genesis_pointer_binding",
        "supervisor_checkpoint_binding",
        "dynamic_checkpoint_binding",
        "outcome_checkpoint_binding",
        "accepted_analysis_cycles",
        "terminal_outcomes",
        "required_audit_directory_count",
        "required_audit_directory_bindings",
        "recovery_audit_directory_bindings",
        "supervisor_observation_bindings",
        "deterministic_recovery_receipt_bindings",
        "all_required_audits_complete",
        "dynamic_terminal_marked_before_seal",
        "active_genesis_pointer_preserved",
        "prediction_calibration_and_profitability_claim",
        *_BOUNDARY_FIELDS,
        TERMINAL_RECEIPT_DIGEST_FIELD,
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
        "terminal_receipt_binding",
        "active_genesis_pointer_binding",
        "independent_from_active_genesis_pointer",
        "active_genesis_pointer_preserved",
        *_BOUNDARY_FIELDS,
        TERMINAL_POINTER_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32TerminalSealError(code)
    return value


def _run_id(value: Any, code: str) -> str:
    candidate = _text(value, code)
    if _RUN_ID.fullmatch(candidate) is None:
        raise V32TerminalSealError(code)
    return candidate


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32TerminalSealError(code)
    return value


def _time(value: Any, code: str) -> str:
    candidate = _text(value, code)
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32TerminalSealError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != candidate
    ):
        raise V32TerminalSealError(code)
    return candidate


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


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


def _verify_boundary(document: Mapping[str, Any], code: str) -> None:
    if any(document.get(key) != value for key, value in _boundary().items()):
        raise V32TerminalSealError(code)


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32TerminalSealError(code)
    relative_ref = _text(value.get("relative_ref"), code)
    path = PurePosixPath(relative_ref)
    if (
        "\\" in relative_ref
        or path.as_posix() != relative_ref
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32TerminalSealError(code)
    return {
        "relative_ref": relative_ref,
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def _binding_list(value: Any, code: str) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32TerminalSealError(code)
    result = [_binding(item, code) for item in value]
    if (
        result != sorted(result, key=lambda row: row["relative_ref"])
        or len({row["relative_ref"] for row in result}) != len(result)
    ):
        raise V32TerminalSealError(code)
    return result


def _audit_rows(
    value: Any, *, recovery: bool, code: str
) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32TerminalSealError(code)
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _AUDIT_ROW_FIELDS:
            raise V32TerminalSealError(code)
        boundary = item.get("boundary_type")
        cycle = item.get("cycle_index")
        if isinstance(cycle, bool) or not isinstance(cycle, int):
            raise V32TerminalSealError(code)
        if recovery:
            valid = boundary == "RECOVERY" and 1 <= cycle <= TOTAL_ANALYSIS_CYCLES
        else:
            valid = (
                (boundary == "QUALIFICATION" and cycle == 0)
                or (
                    boundary in {"ANALYSIS", "ACCEPTANCE", "OUTCOME"}
                    and 1 <= cycle <= TOTAL_ANALYSIS_CYCLES
                )
            )
        if not valid:
            raise V32TerminalSealError(code)
        rows.append(
            {
                "boundary_type": boundary,
                "cycle_index": cycle,
                "binding": _binding(item.get("binding"), code),
            }
        )
    order = {"QUALIFICATION": 0, "ANALYSIS": 1, "ACCEPTANCE": 2, "OUTCOME": 3, "RECOVERY": 4}
    if rows != sorted(rows, key=lambda row: (row["cycle_index"], order[row["boundary_type"]])):
        raise V32TerminalSealError(code)
    identities = {(row["boundary_type"], row["cycle_index"]) for row in rows}
    if len(identities) != len(rows):
        raise V32TerminalSealError(code)
    if not recovery:
        expected = {("QUALIFICATION", 0)} | {
            (boundary, cycle)
            for cycle in range(1, TOTAL_ANALYSIS_CYCLES + 1)
            for boundary in ("ANALYSIS", "ACCEPTANCE", "OUTCOME")
        }
        if identities != expected or len(rows) != REQUIRED_AUDIT_DIRECTORY_COUNT:
            raise V32TerminalSealError(code)
    return rows


def _checkpoint_digest(
    document: Mapping[str, Any], binding: Mapping[str, Any], digest_field: str, code: str
) -> str:
    try:
        digest = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32TerminalSealError(code) from exc
    normalized = _binding(binding, code)
    if normalized["digest_field"] != digest_field or normalized["semantic_digest"] != digest:
        raise V32TerminalSealError(code)
    return digest


def build_v32_terminal_receipt_v1(
    *,
    run_id: str,
    sealed_at: str,
    run_genesis_binding: Mapping[str, Any],
    active_genesis_pointer_binding: Mapping[str, Any],
    supervisor_checkpoint: Mapping[str, Any],
    supervisor_checkpoint_binding: Mapping[str, Any],
    dynamic_checkpoint: Mapping[str, Any],
    dynamic_checkpoint_binding: Mapping[str, Any],
    outcome_checkpoint: Mapping[str, Any],
    outcome_checkpoint_binding: Mapping[str, Any],
    required_audit_directory_bindings: Sequence[Mapping[str, Any]],
    recovery_audit_directory_bindings: Sequence[Mapping[str, Any]],
    supervisor_observation_bindings: Sequence[Mapping[str, Any]],
    deterministic_recovery_receipt_bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    run = _run_id(run_id, "V32_TERMINAL_RUN_INVALID")
    sealed = _time(sealed_at, "V32_TERMINAL_TIME_INVALID")
    genesis = _binding(run_genesis_binding, "V32_TERMINAL_GENESIS_BINDING_INVALID")
    active_pointer = _binding(
        active_genesis_pointer_binding, "V32_TERMINAL_ACTIVE_POINTER_BINDING_INVALID"
    )
    supervisor_digest = _checkpoint_digest(
        supervisor_checkpoint,
        supervisor_checkpoint_binding,
        "tick_supervisor_checkpoint_digest",
        "V32_TERMINAL_SUPERVISOR_INVALID",
    )
    dynamic_digest = _checkpoint_digest(
        dynamic_checkpoint,
        dynamic_checkpoint_binding,
        "dynamic_research_checkpoint_digest",
        "V32_TERMINAL_DYNAMIC_INVALID",
    )
    outcome_digest = _checkpoint_digest(
        outcome_checkpoint,
        outcome_checkpoint_binding,
        "checkpoint_digest",
        "V32_TERMINAL_OUTCOME_INVALID",
    )
    if (
        supervisor_checkpoint.get("run_id") != run
        or supervisor_checkpoint.get("status") != "TERMINAL_COMPLETE"
        or supervisor_checkpoint.get("accepted_analysis_cycles") != TOTAL_ANALYSIS_CYCLES
        or supervisor_checkpoint.get("terminal_outcomes") != TOTAL_OUTCOMES
        or len(supervisor_checkpoint.get("accepted_state_digests", ())) != TOTAL_ANALYSIS_CYCLES
        or len(supervisor_checkpoint.get("terminal_schedule_ids", ())) != TOTAL_OUTCOMES
        or supervisor_checkpoint.get("current_outcome_checkpoint_digest") != outcome_digest
    ):
        raise V32TerminalSealError("V32_TERMINAL_SUPERVISOR_INVALID")
    if (
        dynamic_checkpoint.get("run_id") != run
        or dynamic_checkpoint.get("status") != "TERMINAL"
        or dynamic_checkpoint.get("accepted_analysis_cycles") != TOTAL_ANALYSIS_CYCLES
        or dynamic_checkpoint.get("terminal_outcome_checkpoint_digest") != outcome_digest
        or dynamic_checkpoint.get("predecessor_checkpoint_digest")
        != supervisor_checkpoint.get("current_research_checkpoint_digest")
    ):
        raise V32TerminalSealError("V32_TERMINAL_DYNAMIC_INVALID")
    legacy_receipts = outcome_checkpoint.get("outcome_receipt_bindings", ())
    expiry_terminals = outcome_checkpoint.get("expiry_terminal_bindings", [])
    if (
        not isinstance(legacy_receipts, list)
        or not isinstance(expiry_terminals, list)
        or any(not isinstance(binding, Mapping) for binding in legacy_receipts)
        or any(not isinstance(binding, Mapping) for binding in expiry_terminals)
    ):
        raise V32TerminalSealError("V32_TERMINAL_OUTCOME_INVALID")
    terminal_schedule_ids = [
        _text(binding.get("schedule_id"), "V32_TERMINAL_OUTCOME_INVALID")
        for binding in legacy_receipts
    ]
    for binding in expiry_terminals:
        ids = binding.get("terminal_schedule_ids")
        if isinstance(ids, (str, bytes)) or not isinstance(ids, Sequence):
            raise V32TerminalSealError("V32_TERMINAL_OUTCOME_INVALID")
        terminal_schedule_ids.extend(
            _text(schedule_id, "V32_TERMINAL_OUTCOME_INVALID")
            for schedule_id in ids
        )
    if (
        outcome_checkpoint.get("run_id") != run
        or outcome_checkpoint.get("status") != "TERMINAL"
        or len(outcome_checkpoint.get("schedule_set_bindings", ())) != TOTAL_ANALYSIS_CYCLES
        or len(terminal_schedule_ids) != TOTAL_OUTCOMES
        or len(set(terminal_schedule_ids)) != TOTAL_OUTCOMES
        or set(terminal_schedule_ids)
        != set(supervisor_checkpoint["terminal_schedule_ids"])
    ):
        raise V32TerminalSealError("V32_TERMINAL_OUTCOME_INVALID")
    if any(
        _moment(document.get("updated_at"), "V32_TERMINAL_TIME_INVALID")
        > _moment(sealed, "V32_TERMINAL_TIME_INVALID")
        for document in (supervisor_checkpoint, dynamic_checkpoint, outcome_checkpoint)
    ):
        raise V32TerminalSealError("V32_TERMINAL_TIME_INVALID")
    required_audits = _audit_rows(
        required_audit_directory_bindings,
        recovery=False,
        code="V32_TERMINAL_REQUIRED_AUDITS_INVALID",
    )
    recovery_audits = _audit_rows(
        recovery_audit_directory_bindings,
        recovery=True,
        code="V32_TERMINAL_RECOVERY_AUDITS_INVALID",
    )
    observations = _binding_list(
        supervisor_observation_bindings, "V32_TERMINAL_OBSERVATIONS_INVALID"
    )
    recoveries = _binding_list(
        deterministic_recovery_receipt_bindings, "V32_TERMINAL_RECOVERIES_INVALID"
    )
    return self_digest(
        {
            "schema_id": TERMINAL_RECEIPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run,
            "status": "TERMINAL_SEALED",
            "sealed_at": sealed,
            "run_genesis_binding": genesis,
            "active_genesis_pointer_binding": active_pointer,
            "supervisor_checkpoint_binding": _binding(
                supervisor_checkpoint_binding, "V32_TERMINAL_SUPERVISOR_INVALID"
            ),
            "dynamic_checkpoint_binding": _binding(
                dynamic_checkpoint_binding, "V32_TERMINAL_DYNAMIC_INVALID"
            ),
            "outcome_checkpoint_binding": _binding(
                outcome_checkpoint_binding, "V32_TERMINAL_OUTCOME_INVALID"
            ),
            "accepted_analysis_cycles": TOTAL_ANALYSIS_CYCLES,
            "terminal_outcomes": TOTAL_OUTCOMES,
            "required_audit_directory_count": REQUIRED_AUDIT_DIRECTORY_COUNT,
            "required_audit_directory_bindings": required_audits,
            "recovery_audit_directory_bindings": recovery_audits,
            "supervisor_observation_bindings": observations,
            "deterministic_recovery_receipt_bindings": recoveries,
            "all_required_audits_complete": True,
            "dynamic_terminal_marked_before_seal": True,
            "active_genesis_pointer_preserved": True,
            "prediction_calibration_and_profitability_claim": "UNKNOWN_NOT_EVALUATED",
            **_boundary(),
        },
        TERMINAL_RECEIPT_DIGEST_FIELD,
    )


def verify_v32_terminal_receipt_v1(
    document: Mapping[str, Any],
    *,
    supervisor_checkpoint: Mapping[str, Any],
    dynamic_checkpoint: Mapping[str, Any],
    outcome_checkpoint: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise V32TerminalSealError("V32_TERMINAL_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, TERMINAL_RECEIPT_DIGEST_FIELD)
        rebuilt = build_v32_terminal_receipt_v1(
            run_id=document["run_id"],
            sealed_at=document["sealed_at"],
            run_genesis_binding=document["run_genesis_binding"],
            active_genesis_pointer_binding=document["active_genesis_pointer_binding"],
            supervisor_checkpoint=supervisor_checkpoint,
            supervisor_checkpoint_binding=document["supervisor_checkpoint_binding"],
            dynamic_checkpoint=dynamic_checkpoint,
            dynamic_checkpoint_binding=document["dynamic_checkpoint_binding"],
            outcome_checkpoint=outcome_checkpoint,
            outcome_checkpoint_binding=document["outcome_checkpoint_binding"],
            required_audit_directory_bindings=document[
                "required_audit_directory_bindings"
            ],
            recovery_audit_directory_bindings=document[
                "recovery_audit_directory_bindings"
            ],
            supervisor_observation_bindings=document["supervisor_observation_bindings"],
            deterministic_recovery_receipt_bindings=document[
                "deterministic_recovery_receipt_bindings"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32TerminalSealError):
            raise
        raise V32TerminalSealError("V32_TERMINAL_RECEIPT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[TERMINAL_RECEIPT_DIGEST_FIELD]:
        raise V32TerminalSealError("V32_TERMINAL_RECEIPT_INVALID")
    _verify_boundary(document, "V32_TERMINAL_RECEIPT_BOUNDARY_INVALID")
    return supplied


def build_v32_terminal_pointer_v1(
    *,
    run_id: str,
    published_at: str,
    run_genesis_binding: Mapping[str, Any],
    terminal_receipt_binding: Mapping[str, Any],
    active_genesis_pointer_binding: Mapping[str, Any],
) -> dict[str, Any]:
    return self_digest(
        {
            "schema_id": TERMINAL_POINTER_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": _run_id(run_id, "V32_TERMINAL_POINTER_RUN_INVALID"),
            "status": "TERMINAL_SEALED",
            "published_at": _time(published_at, "V32_TERMINAL_POINTER_TIME_INVALID"),
            "run_genesis_binding": _binding(
                run_genesis_binding, "V32_TERMINAL_POINTER_GENESIS_INVALID"
            ),
            "terminal_receipt_binding": _binding(
                terminal_receipt_binding, "V32_TERMINAL_POINTER_RECEIPT_INVALID"
            ),
            "active_genesis_pointer_binding": _binding(
                active_genesis_pointer_binding,
                "V32_TERMINAL_POINTER_ACTIVE_POINTER_INVALID",
            ),
            "independent_from_active_genesis_pointer": True,
            "active_genesis_pointer_preserved": True,
            **_boundary(),
        },
        TERMINAL_POINTER_DIGEST_FIELD,
    )


def verify_v32_terminal_pointer_v1(
    document: Mapping[str, Any], *, terminal_receipt: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _POINTER_FIELDS:
        raise V32TerminalSealError("V32_TERMINAL_POINTER_INVALID")
    try:
        supplied = verify_self_digest(document, TERMINAL_POINTER_DIGEST_FIELD)
        receipt_digest = verify_self_digest(
            terminal_receipt, TERMINAL_RECEIPT_DIGEST_FIELD
        )
        if (
            document.get("run_id") != terminal_receipt.get("run_id")
            or document.get("run_genesis_binding")
            != terminal_receipt.get("run_genesis_binding")
            or document.get("active_genesis_pointer_binding")
            != terminal_receipt.get("active_genesis_pointer_binding")
            or document.get("terminal_receipt_binding", {}).get("semantic_digest")
            != receipt_digest
            or _moment(document.get("published_at"), "V32_TERMINAL_POINTER_INVALID")
            < _moment(terminal_receipt.get("sealed_at"), "V32_TERMINAL_POINTER_INVALID")
        ):
            raise V32TerminalSealError("V32_TERMINAL_POINTER_INVALID")
        rebuilt = build_v32_terminal_pointer_v1(
            run_id=document["run_id"],
            published_at=document["published_at"],
            run_genesis_binding=document["run_genesis_binding"],
            terminal_receipt_binding=document["terminal_receipt_binding"],
            active_genesis_pointer_binding=document["active_genesis_pointer_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32TerminalSealError):
            raise
        raise V32TerminalSealError("V32_TERMINAL_POINTER_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[TERMINAL_POINTER_DIGEST_FIELD]:
        raise V32TerminalSealError("V32_TERMINAL_POINTER_INVALID")
    _verify_boundary(document, "V32_TERMINAL_POINTER_BOUNDARY_INVALID")
    return supplied


__all__ = [
    "REQUIRED_AUDIT_DIRECTORY_COUNT",
    "TERMINAL_POINTER_DIGEST_FIELD",
    "TERMINAL_POINTER_SCHEMA_ID",
    "TERMINAL_RECEIPT_DIGEST_FIELD",
    "TERMINAL_RECEIPT_SCHEMA_ID",
    "V32TerminalSealError",
    "build_v32_terminal_pointer_v1",
    "build_v32_terminal_receipt_v1",
    "verify_v32_terminal_pointer_v1",
    "verify_v32_terminal_receipt_v1",
]
