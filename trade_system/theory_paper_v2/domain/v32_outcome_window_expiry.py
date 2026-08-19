"""One zero-network terminal artifact for missed V3.2 outcome windows."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest
from .v32_outcome_tick import (
    SCHEDULE_SET_DIGEST_FIELD,
    classify_v32_outcome_schedule_time,
    verify_v32_outcome_schedule_set,
)


class V32OutcomeWindowExpiryError(ValueError):
    """A zero-observation expiry artifact failed closed."""


SCHEMA_VERSION = "1.0.0"
EXPIRY_TERMINAL_SCHEMA_ID = "theory_paper_v32_outcome_window_expiry_terminal_v1"
EXPIRY_TERMINAL_DIGEST_FIELD = "outcome_window_expiry_terminal_digest"
EXPIRY_ROW_SCHEMA_ID = "theory_paper_v32_outcome_window_expiry_row_v1"
EXPIRY_ROW_DIGEST_FIELD = "outcome_window_expiry_row_digest"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
RESOLUTION_STATUS = "UNKNOWN_COVERAGE_LOSS"
COVERAGE_LOSS_REASON = "OBSERVATION_WINDOW_MISSED"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_ROW_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "run_id", "schedule_id",
        "schedule_digest", "schedule_set_digest", "decision_id", "cycle_index",
        "horizon", "outcome_not_before", "expires_at", "resolved_at",
        "resolution_status", "coverage_loss_reason", "observable_ref", "value",
        "provider_as_of", "quality", "missingness", "terminal",
        "network_request_count", "attempt_count", "raw_evidence_present",
        "observation_tick_present", "retry_allowed", "source_scope",
        "external_execution_authority", "executable", EXPIRY_ROW_DIGEST_FIELD,
    }
)
_TERMINAL_FIELDS = frozenset(
    {
        "schema_id", "schema_version", "run_id", "permit_digest",
        "supervisor_checkpoint_digest_before_permit",
        "outcome_checkpoint_digest_before", "experiment_contract_digest",
        "active_authority_digest", "classified_at",
        "outcome_schedule_set_digests", "prior_terminal_schedule_ids",
        "terminal_schedule_ids", "rows", "network_request_count", "attempt_count",
        "raw_evidence_present", "observation_tick_present", "retry_allowed",
        "source_scope", "external_execution_authority", "executable",
        EXPIRY_TERMINAL_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32OutcomeWindowExpiryError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32OutcomeWindowExpiryError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32OutcomeWindowExpiryError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text
    ):
        raise V32OutcomeWindowExpiryError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _sorted_texts(value: Any, code: str, *, allow_empty: bool = True) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32OutcomeWindowExpiryError(code)
    rows = [_text(item, code) for item in value]
    if (not allow_empty and not rows) or rows != sorted(set(rows)):
        raise V32OutcomeWindowExpiryError(code)
    return rows


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
    }


def _build_row(
    *, run_id: str, schedule: Mapping[str, Any], schedule_set_digest: str,
    resolved_at: str,
) -> dict[str, Any]:
    return self_digest(
        {
            "schema_id": EXPIRY_ROW_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "schedule_id": schedule["schedule_id"],
            "schedule_digest": schedule["schedule_digest"],
            "schedule_set_digest": schedule_set_digest,
            "decision_id": schedule["decision_id"],
            "cycle_index": schedule["cycle_index"],
            "horizon": schedule["horizon"],
            "outcome_not_before": schedule["outcome_not_before"],
            "expires_at": schedule["expires_at"],
            "resolved_at": resolved_at,
            "resolution_status": RESOLUTION_STATUS,
            "coverage_loss_reason": COVERAGE_LOSS_REASON,
            "observable_ref": schedule["observable_ref"],
            "value": None,
            "provider_as_of": None,
            "quality": "UNKNOWN",
            "missingness": "UNKNOWN",
            "terminal": True,
            "network_request_count": 0,
            "attempt_count": 0,
            "raw_evidence_present": False,
            "observation_tick_present": False,
            "retry_allowed": False,
            **_boundary(),
        },
        EXPIRY_ROW_DIGEST_FIELD,
    )


def verify_v32_outcome_window_expiry_row(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _ROW_FIELDS:
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_ROW_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, EXPIRY_ROW_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_ROW_DIGEST_INVALID") from exc
    if (
        document.get("schema_id") != EXPIRY_ROW_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("resolution_status") != RESOLUTION_STATUS
        or document.get("coverage_loss_reason") != COVERAGE_LOSS_REASON
        or document.get("value") is not None
        or document.get("provider_as_of") is not None
        or document.get("quality") != "UNKNOWN"
        or document.get("missingness") != "UNKNOWN"
        or document.get("terminal") is not True
        or document.get("network_request_count") != 0
        or document.get("attempt_count") != 0
        or document.get("raw_evidence_present") is not False
        or document.get("observation_tick_present") is not False
        or document.get("retry_allowed") is not False
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority") != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
    ):
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_ROW_POLICY_INVALID")
    for field in ("run_id", "schedule_id", "decision_id", "horizon", "observable_ref"):
        _text(document.get(field), "V32_EXPIRY_ROW_IDENTITY_INVALID")
    for field in ("schedule_digest", "schedule_set_digest"):
        _digest(document.get(field), "V32_EXPIRY_ROW_BINDING_INVALID")
    if (
        isinstance(document.get("cycle_index"), bool)
        or not isinstance(document.get("cycle_index"), int)
        or document["cycle_index"] < 1
        or _moment(document.get("outcome_not_before"), "V32_EXPIRY_ROW_TIME_INVALID")
        >= _moment(document.get("expires_at"), "V32_EXPIRY_ROW_TIME_INVALID")
        or _moment(document.get("expires_at"), "V32_EXPIRY_ROW_TIME_INVALID")
        >= _moment(document.get("resolved_at"), "V32_EXPIRY_ROW_TIME_INVALID")
    ):
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_ROW_TIME_INVALID")
    return supplied


def build_v32_outcome_window_expiry_terminal(
    *, run_id: str, classified_at: str, schedule_sets: Sequence[Mapping[str, Any]],
    prior_terminal_schedule_ids: Sequence[str], permit_digest: str,
    supervisor_checkpoint_digest_before_permit: str,
    outcome_checkpoint_digest_before: str, experiment_contract_digest: str,
    active_authority_digest: str,
) -> dict[str, Any]:
    run = _text(run_id, "V32_EXPIRY_RUN_ID_INVALID")
    classified = _time(classified_at, "V32_EXPIRY_TIME_INVALID")
    prior = _sorted_texts(
        prior_terminal_schedule_ids, "V32_EXPIRY_PRIOR_SET_INVALID"
    )
    registry: dict[str, tuple[Mapping[str, Any], str]] = {}
    set_digests: list[str] = []
    for schedule_set in schedule_sets:
        set_digest = verify_v32_outcome_schedule_set(schedule_set)
        if schedule_set.get("run_id") != run:
            raise V32OutcomeWindowExpiryError("V32_EXPIRY_RUN_MISMATCH")
        set_digests.append(set_digest)
        for schedule in schedule_set["schedules"]:
            if schedule["schedule_id"] in registry:
                raise V32OutcomeWindowExpiryError("V32_EXPIRY_DUPLICATE_SCHEDULE")
            registry[schedule["schedule_id"]] = (schedule, set_digest)
    if not set(prior).issubset(registry):
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_PRIOR_SET_INVALID")
    expired = sorted(
        schedule_id for schedule_id, (schedule, _) in registry.items()
        if schedule_id not in prior
        and classify_v32_outcome_schedule_time(schedule, now=classified) == "EXPIRED"
    )
    if not expired:
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_NO_EXPIRED_SCHEDULES")
    rows = [
        _build_row(
            run_id=run, schedule=registry[schedule_id][0],
            schedule_set_digest=registry[schedule_id][1], resolved_at=classified,
        )
        for schedule_id in expired
    ]
    return self_digest(
        {
            "schema_id": EXPIRY_TERMINAL_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run,
            "permit_digest": _digest(permit_digest, "V32_EXPIRY_PERMIT_INVALID"),
            "supervisor_checkpoint_digest_before_permit": _digest(
                supervisor_checkpoint_digest_before_permit,
                "V32_EXPIRY_SUPERVISOR_BINDING_INVALID",
            ),
            "outcome_checkpoint_digest_before": _digest(
                outcome_checkpoint_digest_before, "V32_EXPIRY_OUTCOME_BINDING_INVALID"
            ),
            "experiment_contract_digest": _digest(
                experiment_contract_digest, "V32_EXPIRY_CONTRACT_BINDING_INVALID"
            ),
            "active_authority_digest": _digest(
                active_authority_digest, "V32_EXPIRY_AUTHORITY_BINDING_INVALID"
            ),
            "classified_at": classified,
            "outcome_schedule_set_digests": set_digests,
            "prior_terminal_schedule_ids": prior,
            "terminal_schedule_ids": expired,
            "rows": rows,
            "network_request_count": 0,
            "attempt_count": 0,
            "raw_evidence_present": False,
            "observation_tick_present": False,
            "retry_allowed": False,
            **_boundary(),
        },
        EXPIRY_TERMINAL_DIGEST_FIELD,
    )


def verify_v32_outcome_window_expiry_terminal_intrinsic(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _TERMINAL_FIELDS:
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_TERMINAL_SCHEMA_INVALID")
    try:
        supplied = verify_self_digest(document, EXPIRY_TERMINAL_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_TERMINAL_DIGEST_INVALID") from exc
    rows = document.get("rows")
    if (
        document.get("schema_id") != EXPIRY_TERMINAL_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("network_request_count") != 0
        or document.get("attempt_count") != 0
        or document.get("raw_evidence_present") is not False
        or document.get("observation_tick_present") is not False
        or document.get("retry_allowed") is not False
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority") != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
        or not isinstance(rows, list)
        or not rows
        or [row.get("schedule_id") for row in rows]
        != document.get("terminal_schedule_ids")
    ):
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_TERMINAL_POLICY_INVALID")
    run = _text(document.get("run_id"), "V32_EXPIRY_TERMINAL_IDENTITY_INVALID")
    classified = _time(document.get("classified_at"), "V32_EXPIRY_TIME_INVALID")
    for field in (
        "permit_digest", "supervisor_checkpoint_digest_before_permit",
        "outcome_checkpoint_digest_before", "experiment_contract_digest",
        "active_authority_digest",
    ):
        _digest(document.get(field), "V32_EXPIRY_TERMINAL_BINDING_INVALID")
    set_digests = document.get("outcome_schedule_set_digests")
    if (
        not isinstance(set_digests, list)
        or any(not isinstance(item, str) or _HEX_64.fullmatch(item) is None for item in set_digests)
    ):
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_TERMINAL_BINDING_INVALID")
    prior = _sorted_texts(
        document.get("prior_terminal_schedule_ids"),
        "V32_EXPIRY_PRIOR_SET_INVALID",
    )
    terminal_ids = _sorted_texts(
        document.get("terminal_schedule_ids"),
        "V32_EXPIRY_TERMINAL_SET_INVALID",
        allow_empty=False,
    )
    if set(prior) & set(terminal_ids):
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_TERMINAL_SET_INVALID")
    for row in rows:
        verify_v32_outcome_window_expiry_row(row)
        if row.get("run_id") != run or row.get("resolved_at") != classified:
            raise V32OutcomeWindowExpiryError("V32_EXPIRY_TERMINAL_ROW_INVALID")
    return supplied


def verify_v32_outcome_window_expiry_terminal(
    document: Mapping[str, Any], *, schedule_sets: Sequence[Mapping[str, Any]]
) -> str:
    supplied = verify_v32_outcome_window_expiry_terminal_intrinsic(document)
    rebuilt = build_v32_outcome_window_expiry_terminal(
        run_id=document["run_id"], classified_at=document["classified_at"],
        schedule_sets=schedule_sets,
        prior_terminal_schedule_ids=document["prior_terminal_schedule_ids"],
        permit_digest=document["permit_digest"],
        supervisor_checkpoint_digest_before_permit=document[
            "supervisor_checkpoint_digest_before_permit"
        ],
        outcome_checkpoint_digest_before=document["outcome_checkpoint_digest_before"],
        experiment_contract_digest=document["experiment_contract_digest"],
        active_authority_digest=document["active_authority_digest"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[EXPIRY_TERMINAL_DIGEST_FIELD]:
        raise V32OutcomeWindowExpiryError("V32_EXPIRY_TERMINAL_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "EXPIRY_ROW_DIGEST_FIELD", "EXPIRY_ROW_SCHEMA_ID",
    "EXPIRY_TERMINAL_DIGEST_FIELD", "EXPIRY_TERMINAL_SCHEMA_ID",
    "V32OutcomeWindowExpiryError", "build_v32_outcome_window_expiry_terminal",
    "verify_v32_outcome_window_expiry_row",
    "verify_v32_outcome_window_expiry_terminal_intrinsic",
    "verify_v32_outcome_window_expiry_terminal",
]
