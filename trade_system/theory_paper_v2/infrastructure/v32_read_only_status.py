"""Strictly read-only optimistic status for one published V3.2 target run.

This reader intentionally does not instantiate any Local store: their normal
read methods acquire persistent lock files.  It opens only the fixed durable
heads, immutable Supervisor permit/history objects, and outcome schedule sets.
No outcome observation, raw payload, receipt value, Agent payload, account, or
execution object is read.  A changed mutable head yields BUSY_UNSTABLE.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from ..application.v32_prospective_runtime import (
    resolve_v32_active_analysis_agent_window_v1,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
    verify_self_digest,
)
from ..domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    verify_v32_current_root_agent_mailbox_checkpoint_v1,
)
from ..domain.v32_outcome_tick import (
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
    build_v32_outcome_tick_attempt,
    classify_v32_outcome_schedule_time,
    verify_v32_outcome_schedule_set,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_permit,
    verify_v32_tick_supervisor_transition,
)
from .v32_dynamic_store import (
    CHECKPOINT_DIGEST_FIELD as DYNAMIC_CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID as DYNAMIC_CHECKPOINT_SCHEMA_ID,
    CHECKPOINT_SCHEMA_VERSION as DYNAMIC_CHECKPOINT_SCHEMA_VERSION,
    STATUSES as DYNAMIC_STATUSES,
    _CHECKPOINT_FIELDS as DYNAMIC_CHECKPOINT_FIELDS,
)
from .v32_outcome_tick_store import (
    CHECKPOINT_SCHEMA_ID as OUTCOME_CHECKPOINT_SCHEMA_ID,
    CHECKPOINT_SCHEMA_ID_V2 as OUTCOME_CHECKPOINT_SCHEMA_ID_V2,
    CHECKPOINT_SCHEMA_VERSION as OUTCOME_CHECKPOINT_SCHEMA_VERSION,
    CHECKPOINT_SCHEMA_VERSION_V2 as OUTCOME_CHECKPOINT_SCHEMA_VERSION_V2,
    _CHECKPOINT_FIELDS as OUTCOME_CHECKPOINT_FIELDS,
    _CHECKPOINT_FIELDS_V2 as OUTCOME_CHECKPOINT_FIELDS_V2,
)


class V32ReadOnlyStatusError(ValueError):
    """A fixed read-only run head was missing, forged, or cross-bound."""


SUPERVISOR_HEAD_REF = "v32-tick-supervisor-v1/checkpoint.json"
DYNAMIC_HEAD_REF = "v32-dynamic-cycle-v1/checkpoint.json"
OUTCOME_HEAD_REF = "outcome-v32/checkpoint.json"
MAILBOX_ROOT = "v32-current-root-agent-mailbox-v1"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"


def _time(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ReadOnlyStatusError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ReadOnlyStatusError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32ReadOnlyStatusError(code)
    return value


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _run_root(value: Path) -> Path:
    supplied = Path(value).absolute()
    try:
        if supplied.is_symlink():
            raise V32ReadOnlyStatusError("V32_STATUS_RUN_ROOT_INVALID")
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V32ReadOnlyStatusError("V32_STATUS_RUN_ROOT_INVALID") from exc
    if not root.is_dir():
        raise V32ReadOnlyStatusError("V32_STATUS_RUN_ROOT_INVALID")
    return root


def _safe_path(root: Path, relative_ref: str) -> Path:
    lexical = PurePosixPath(relative_ref)
    if (
        not relative_ref
        or "\\" in relative_ref
        or lexical.is_absolute()
        or lexical.as_posix() != relative_ref
        or any(part in {"", ".", ".."} for part in lexical.parts)
    ):
        raise V32ReadOnlyStatusError("V32_STATUS_PATH_INVALID")
    current = root
    try:
        for part in lexical.parts:
            current = current / part
            if current.is_symlink():
                raise V32ReadOnlyStatusError("V32_STATUS_PATH_INVALID")
        current.resolve(strict=False).relative_to(root)
    except V32ReadOnlyStatusError:
        raise
    except (OSError, ValueError) as exc:
        raise V32ReadOnlyStatusError("V32_STATUS_PATH_INVALID") from exc
    return current


def _read_regular_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise V32ReadOnlyStatusError("V32_STATUS_FILE_MISSING_OR_UNSAFE")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise V32ReadOnlyStatusError("V32_STATUS_FILE_READ_FAILED") from exc


def _read_optional_regular_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise V32ReadOnlyStatusError("V32_STATUS_FILE_MISSING_OR_UNSAFE")
    return _read_regular_bytes(path) if path.is_file() else None


def _canonical_document(payload: bytes, code: str) -> Mapping[str, Any]:
    try:
        document = loads_json_strict(payload)
        if payload != canonical_bytes(document) + b"\n":
            raise V32ReadOnlyStatusError(code)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, V32ReadOnlyStatusError):
            raise
        raise V32ReadOnlyStatusError(code) from exc
    return document


def _read_document(root: Path, relative_ref: str, code: str) -> tuple[Mapping[str, Any], bytes]:
    payload = _read_regular_bytes(_safe_path(root, relative_ref))
    return _canonical_document(payload, code), payload


def _verify_dynamic_head(document: Mapping[str, Any], *, run_id: str) -> str:
    try:
        digest = verify_self_digest(document, DYNAMIC_CHECKPOINT_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32ReadOnlyStatusError("V32_STATUS_DYNAMIC_HEAD_INVALID") from exc
    accepted = document.get("accepted_analysis_cycles")
    next_cycle = document.get("next_analysis_cycle_index")
    open_cycle = document.get("open_cycle_index")
    status = document.get("status")
    if (
        set(document) != DYNAMIC_CHECKPOINT_FIELDS
        or document.get("schema_id") != DYNAMIC_CHECKPOINT_SCHEMA_ID
        or document.get("schema_version") != DYNAMIC_CHECKPOINT_SCHEMA_VERSION
        or document.get("run_id") != run_id
        or status not in DYNAMIC_STATUSES
        or isinstance(document.get("revision"), bool)
        or not isinstance(document.get("revision"), int)
        or document["revision"] < 0
        or isinstance(accepted, bool)
        or not isinstance(accepted, int)
        or not 0 <= accepted <= 16
        or next_cycle != accepted + 1
        or (
            open_cycle is not None
            and (
                isinstance(open_cycle, bool)
                or not isinstance(open_cycle, int)
                or open_cycle != next_cycle
                or not 1 <= open_cycle <= 16
            )
        )
        or not isinstance(document.get("artifact_bindings"), list)
        or not isinstance(document.get("accepted_cycle_bindings"), list)
        or len(document["accepted_cycle_bindings"]) != accepted
        or document.get("tail_recovery_policy")
        != "DETERMINISTIC_PERSISTED_COMMIT_TAIL_ONLY"
        or document.get("tail_recovery_agent_invocations_allowed") != 0
        or document.get("tail_recovery_network_requests_allowed") != 0
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
        or document.get("account_access") is not False
        or document.get("order_submission") is not False
        or document.get("fill_claim") != "NONE_NO_FILL_MODEL"
        or document.get("pnl_claim") != "NONE_NO_PNL_MODEL"
        or (status == "READY" and (open_cycle is not None or accepted >= 16))
        or (status == "OPEN" and open_cycle is None)
        or (
            status in {"OUTCOME_TAIL", "TERMINAL"}
            and (accepted != 16 or next_cycle != 17 or open_cycle is not None)
        )
        or (status == "FAILED") != (document.get("failure_binding") is not None)
        or document.get("resume_allowed") is not (status not in {"TERMINAL", "FAILED"})
    ):
        raise V32ReadOnlyStatusError("V32_STATUS_DYNAMIC_HEAD_INVALID")
    created = _moment(document.get("created_at"), "V32_STATUS_DYNAMIC_HEAD_INVALID")
    updated = _moment(document.get("updated_at"), "V32_STATUS_DYNAMIC_HEAD_INVALID")
    if updated < created:
        raise V32ReadOnlyStatusError("V32_STATUS_DYNAMIC_HEAD_INVALID")
    return digest


def _verify_outcome_head(document: Mapping[str, Any], *, run_id: str) -> str:
    try:
        digest = verify_self_digest(document, "checkpoint_digest")
    except (TypeError, ValueError) as exc:
        raise V32ReadOnlyStatusError("V32_STATUS_OUTCOME_HEAD_INVALID") from exc
    v1 = (
        document.get("schema_id") == OUTCOME_CHECKPOINT_SCHEMA_ID
        and document.get("schema_version") == OUTCOME_CHECKPOINT_SCHEMA_VERSION
        and set(document) == OUTCOME_CHECKPOINT_FIELDS
    )
    v2 = (
        document.get("schema_id") == OUTCOME_CHECKPOINT_SCHEMA_ID_V2
        and document.get("schema_version") == OUTCOME_CHECKPOINT_SCHEMA_VERSION_V2
        and set(document) == OUTCOME_CHECKPOINT_FIELDS_V2
    )
    lists = (
        "schedule_set_bindings",
        "attempt_bindings",
        "evidence_bindings",
        "normalization_bindings",
        "observation_tick_bindings",
        "batch_intent_bindings",
        "outcome_receipt_bindings",
        "batch_completion_bindings",
        *(("expiry_terminal_bindings",) if v2 else ()),
    )
    if (
        not (v1 or v2)
        or document.get("run_id") != run_id
        or document.get("status") not in {"ACTIVE", "TERMINAL", "FAILED_CLOSED"}
        or isinstance(document.get("revision"), bool)
        or not isinstance(document.get("revision"), int)
        or document["revision"] < 0
        or document.get("total_cycles") != 16
        or document.get("total_schedules") != 48
        or any(not isinstance(document.get(field), list) for field in lists)
        or len(document["schedule_set_bindings"]) > 16
        or not len(document["batch_completion_bindings"])
        <= len(document["batch_intent_bindings"])
        <= len(document["observation_tick_bindings"])
        <= len(document["normalization_bindings"])
        <= len(document["evidence_bindings"])
        <= len(document["attempt_bindings"])
        or document.get("max_network_requests_per_tick") != 1
        or document.get("retry_allowed") is not False
        or document.get("raw_before_parse") is not True
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
        or (document.get("status") == "FAILED_CLOSED")
        != (document.get("failure_binding") is not None)
    ):
        raise V32ReadOnlyStatusError("V32_STATUS_OUTCOME_HEAD_INVALID")
    created = _moment(document.get("created_at"), "V32_STATUS_OUTCOME_HEAD_INVALID")
    updated = _moment(document.get("updated_at"), "V32_STATUS_OUTCOME_HEAD_INVALID")
    if updated < created:
        raise V32ReadOnlyStatusError("V32_STATUS_OUTCOME_HEAD_INVALID")
    return digest


def _load_schedule_sets(
    root: Path, *, run_id: str, outcome_head: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    documents: list[Mapping[str, Any]] = []
    for cycle, binding in enumerate(outcome_head["schedule_set_bindings"], start=1):
        expected_ref = f"outcome-v32/schedules/cycle-{cycle:04d}.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref", "schema_id", "digest_field", "semantic_digest",
                "physical_sha256", "cycle_index", "schedule_count",
            }
            or binding.get("relative_ref") != expected_ref
            or binding.get("schema_id") != SCHEDULE_SET_SCHEMA_ID
            or binding.get("digest_field") != SCHEDULE_SET_DIGEST_FIELD
            or binding.get("cycle_index") != cycle
            or binding.get("schedule_count") != 3
        ):
            raise V32ReadOnlyStatusError("V32_STATUS_SCHEDULE_BINDING_INVALID")
        document, payload = _read_document(
            root, expected_ref, "V32_STATUS_SCHEDULE_DOCUMENT_INVALID"
        )
        try:
            digest = verify_v32_outcome_schedule_set(document)
        except (TypeError, ValueError) as exc:
            raise V32ReadOnlyStatusError(
                "V32_STATUS_SCHEDULE_DOCUMENT_INVALID"
            ) from exc
        if (
            document.get("run_id") != run_id
            or document.get("cycle_index") != cycle
            or digest != binding.get("semantic_digest")
            or hashlib.sha256(payload).hexdigest() != binding.get("physical_sha256")
        ):
            raise V32ReadOnlyStatusError("V32_STATUS_SCHEDULE_BINDING_INVALID")
        documents.append(document)
    return documents


def project_v32_outcome_schedule_states_v1(
    *,
    schedule_sets: Sequence[Mapping[str, Any]],
    terminal_schedule_ids: Sequence[str],
    observed_at: str,
) -> list[Mapping[str, Any]]:
    """Project FUTURE/DUE/EXPIRED/TERMINAL without reading outcome values."""

    observed = _time(observed_at, "V32_STATUS_OBSERVED_TIME_INVALID")
    terminal = set(terminal_schedule_ids)
    rows: list[Mapping[str, Any]] = []
    known: set[str] = set()
    for schedule_set in schedule_sets:
        verify_v32_outcome_schedule_set(schedule_set)
        for schedule in schedule_set["schedules"]:
            schedule_id = str(schedule["schedule_id"])
            if schedule_id in known:
                raise V32ReadOnlyStatusError("V32_STATUS_SCHEDULE_DUPLICATE")
            known.add(schedule_id)
            rows.append(
                {
                    "cycle_index": schedule["cycle_index"],
                    "horizon": schedule["horizon"],
                    "schedule_id": schedule_id,
                    "target_at": schedule["outcome_not_before"],
                    "expires_at": schedule["expires_at"],
                    "state": (
                        "TERMINAL"
                        if schedule_id in terminal
                        else classify_v32_outcome_schedule_time(
                            schedule, now=observed
                        )
                    ),
                }
            )
    if not terminal.issubset(known):
        raise V32ReadOnlyStatusError("V32_STATUS_TERMINAL_SCHEDULE_UNKNOWN")
    return rows


def _mailbox_boundary(
    root: Path, *, run_id: str, cycle_index: int | None
) -> Mapping[str, Any]:
    if cycle_index is None:
        return {"cycle_index": None, "status": "NOT_APPLICABLE"}
    base = f"{MAILBOX_ROOT}/cycles/{cycle_index:04d}"
    checkpoint_path = _safe_path(root, f"{base}/checkpoint.json")
    if not checkpoint_path.exists():
        return {"cycle_index": cycle_index, "status": "NOT_INITIALIZED"}
    document, _ = _read_document(
        root, f"{base}/checkpoint.json", "V32_STATUS_MAILBOX_HEAD_INVALID"
    )
    try:
        digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(document)
    except (TypeError, ValueError) as exc:
        raise V32ReadOnlyStatusError("V32_STATUS_MAILBOX_HEAD_INVALID") from exc
    history, _ = _read_document(
        root,
        f"{base}/checkpoints/{digest}.json",
        "V32_STATUS_MAILBOX_HISTORY_INVALID",
    )
    if history != document or document.get("run_id") != run_id:
        raise V32ReadOnlyStatusError("V32_STATUS_MAILBOX_HISTORY_INVALID")
    return {
        "cycle_index": cycle_index,
        "status": document["status"],
        "checkpoint_digest": document[MAILBOX_CHECKPOINT_DIGEST_FIELD],
        "active_stage": document["active_stage"],
        "stage_states": deepcopy(document["stage_states"]),
    }


def _unstable_status(*, run_id: str, observed_at: str) -> Mapping[str, Any]:
    return {
        "schema_id": "theory_paper_v32_target_read_status_v1",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "observed_at": observed_at,
        "status": "BUSY_UNSTABLE",
        "current_boundary": "BUSY_UNSTABLE",
        "next_legal_action": "READ_STATUS_AGAIN",
        "active_permit": None,
        "agent_stage": "UNKNOWN_UNSTABLE",
        "outcome_states": [],
        "terminal_state": "UNKNOWN_UNSTABLE",
        "failure": None,
        "retry_allowed": False,
        "same_process_poll_required": False,
        "same_process_poll_reason": "OS_SESSION_NOT_OBSERVABLE_FROM_DURABLE_STATE",
        "outcome_values_read": False,
        "state_mutation_count": 0,
        "network_request_count": 0,
        "executable": False,
    }


def _next_legal_action(
    *,
    supervisor_status: str,
    permit_kind: str | None,
    analysis_window_open: bool | None,
    active_stage_status: str | None,
    active_due_schedule_ids: Sequence[str],
    outcome_states: Sequence[Mapping[str, Any]],
) -> str:
    expired = {
        str(row["schedule_id"])
        for row in outcome_states
        if row.get("state") == "EXPIRED"
    }
    if supervisor_status == "FAILED_CLOSED":
        return "NONE_RUN_FAILED_CLOSED"
    if permit_kind == "ANALYSIS_TICK" and analysis_window_open is False:
        return "TARGET_WAKE_ONCE_FAIL_CLOSE_EXPIRED_ANALYSIS_PERMIT"
    if permit_kind == "OUTCOME_TICK" and expired.intersection(
        active_due_schedule_ids
    ):
        return "TARGET_WAKE_ONCE_FAIL_CLOSE_EXPIRED_OUTCOME_TICK"
    if active_stage_status == "REQUESTED":
        return "CLAIM_CURRENT_ROOT_AGENT_REQUEST"
    if active_stage_status == "CLAIMED":
        return "SUBMIT_CURRENT_ROOT_AGENT_DELIVERY"
    if permit_kind is not None:
        return "TARGET_WAKE_ONCE_RESUME_ACTIVE_PERMIT"
    if expired:
        return "TARGET_WAKE_ONCE_TERMINALIZE_EXPIRED_OUTCOME"
    if any(row.get("state") == "DUE" for row in outcome_states):
        return "TARGET_WAKE_ONCE_CAPTURE_DUE_OUTCOME"
    if supervisor_status == "TERMINAL_COMPLETE":
        return "TARGET_WAKE_ONCE_FINALIZE_OR_REPLAY_TERMINAL"
    return "TARGET_WAKE_ONCE"


def read_v32_read_only_status_snapshot_v1(
    *, run_root: Path, run_id: str, observed_at: str
) -> Mapping[str, Any]:
    """Read one stable-enough status snapshot without any filesystem write."""

    root = _run_root(run_root)
    observed = _time(observed_at, "V32_STATUS_OBSERVED_TIME_INVALID")
    supervisor_path = _safe_path(root, SUPERVISOR_HEAD_REF)
    supervisor_payload_before = _read_regular_bytes(supervisor_path)
    supervisor = _canonical_document(
        supervisor_payload_before, "V32_STATUS_SUPERVISOR_HEAD_INVALID"
    )
    try:
        verify_v32_tick_supervisor_checkpoint(supervisor)
    except (TypeError, ValueError) as exc:
        raise V32ReadOnlyStatusError("V32_STATUS_SUPERVISOR_HEAD_INVALID") from exc
    if supervisor.get("run_id") != run_id:
        raise V32ReadOnlyStatusError("V32_STATUS_RUN_ID_MISMATCH")

    dynamic, dynamic_payload_before = _read_document(
        root, DYNAMIC_HEAD_REF, "V32_STATUS_DYNAMIC_HEAD_INVALID"
    )
    outcome, outcome_payload_before = _read_document(
        root, OUTCOME_HEAD_REF, "V32_STATUS_OUTCOME_HEAD_INVALID"
    )
    _verify_dynamic_head(dynamic, run_id=run_id)
    _verify_outcome_head(outcome, run_id=run_id)
    all_schedule_sets = _load_schedule_sets(
        root, run_id=run_id, outcome_head=outcome
    )

    active_permit: Mapping[str, Any] | None = None
    active_window: Mapping[str, Any] | None = None
    permit_digest = supervisor.get("active_permit_digest")
    if permit_digest is not None:
        active_permit, _ = _read_document(
            root,
            f"v32-tick-supervisor-v1/permits/{permit_digest}.json",
            "V32_STATUS_ACTIVE_PERMIT_INVALID",
        )
        predecessor_digest = active_permit.get(
            "supervisor_checkpoint_digest_before_permit"
        )
        predecessor, _ = _read_document(
            root,
            f"v32-tick-supervisor-v1/checkpoints/{predecessor_digest}.json",
            "V32_STATUS_SUPERVISOR_HISTORY_INVALID",
        )
        try:
            verify_v32_tick_supervisor_checkpoint(predecessor)
            verify_v32_tick_supervisor_transition(predecessor, supervisor)
            bound_sets = all_schedule_sets[: predecessor["accepted_analysis_cycles"]]
            if active_permit.get("permit_kind") == "ANALYSIS_TICK":
                active_window = resolve_v32_active_analysis_agent_window_v1(
                    run_id=run_id,
                    supervisor_checkpoint=supervisor,
                    active_permit=active_permit,
                    predecessor_checkpoint=predecessor,
                    schedule_sets=bound_sets,
                    observed_at=observed,
                )
            else:
                attempt = (
                    None
                    if active_permit.get("permit_kind") == "OUTCOME_WINDOW_EXPIRY"
                    else build_v32_outcome_tick_attempt(
                        run_id=run_id,
                        tick_index=active_permit["outcome_tick_index"],
                        planned_tick_at=active_permit["planned_outcome_tick_at"],
                        reserved_at=active_permit["issued_at"],
                    )
                )
                verified_permit_digest = verify_v32_tick_supervisor_permit(
                    active_permit,
                    checkpoint=predecessor,
                    schedule_sets=bound_sets,
                    tick_attempt=attempt,
                )
                if verified_permit_digest != permit_digest:
                    raise V32ReadOnlyStatusError(
                        "V32_STATUS_ACTIVE_PERMIT_INVALID"
                    )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32ReadOnlyStatusError("V32_STATUS_ACTIVE_PERMIT_INVALID") from exc

    accepted_count = int(supervisor["accepted_analysis_cycles"])
    accepted_sets = all_schedule_sets[:accepted_count]
    accepted_set_digests = [
        item[SCHEDULE_SET_DIGEST_FIELD] for item in accepted_sets
    ]
    accepted_schedule_ids = sorted(
        str(row["schedule_id"])
        for item in accepted_sets
        for row in item["schedules"]
    )
    prefix_extra = len(all_schedule_sets) - accepted_count
    if (
        accepted_set_digests != list(supervisor["outcome_schedule_set_digests"])
        or accepted_schedule_ids != list(supervisor["scheduled_schedule_ids"])
        or prefix_extra
        not in (
            {0, 1}
            if active_permit
            and active_permit.get("permit_kind") == "ANALYSIS_TICK"
            else {0}
        )
        or dynamic.get("accepted_analysis_cycles")
        not in (
            {accepted_count, accepted_count + 1}
            if active_permit
            and active_permit.get("permit_kind") == "ANALYSIS_TICK"
            else {accepted_count}
        )
    ):
        raise V32ReadOnlyStatusError("V32_STATUS_CROSS_STORE_HEAD_INVALID")
    if active_permit is None and (
        dynamic[DYNAMIC_CHECKPOINT_DIGEST_FIELD]
        != supervisor["current_research_checkpoint_digest"]
        or outcome["checkpoint_digest"]
        != supervisor["current_outcome_checkpoint_digest"]
    ):
        raise V32ReadOnlyStatusError("V32_STATUS_CROSS_STORE_HEAD_INVALID")

    mailbox_cycle = (
        int(active_permit["analysis_cycle_index"])
        if active_permit and active_permit.get("permit_kind") == "ANALYSIS_TICK"
        else int(dynamic["open_cycle_index"])
        if dynamic.get("open_cycle_index") is not None
        else accepted_count
        if accepted_count > 0
        else supervisor.get("next_analysis_cycle_index")
    )
    mailbox_head_path = _safe_path(
        root,
        f"{MAILBOX_ROOT}/cycles/{mailbox_cycle:04d}/checkpoint.json",
    ) if mailbox_cycle is not None else None
    mailbox_payload_before = (
        None
        if mailbox_head_path is None
        else _read_optional_regular_bytes(mailbox_head_path)
    )
    mailbox = _mailbox_boundary(root, run_id=run_id, cycle_index=mailbox_cycle)
    outcome_states = project_v32_outcome_schedule_states_v1(
        schedule_sets=accepted_sets,
        terminal_schedule_ids=supervisor["terminal_schedule_ids"],
        observed_at=observed,
    )

    if (
        _read_regular_bytes(supervisor_path) != supervisor_payload_before
        or _read_regular_bytes(_safe_path(root, DYNAMIC_HEAD_REF))
        != dynamic_payload_before
        or _read_regular_bytes(_safe_path(root, OUTCOME_HEAD_REF))
        != outcome_payload_before
        or (
            mailbox_head_path is not None
            and _read_optional_regular_bytes(mailbox_head_path)
            != mailbox_payload_before
        )
    ):
        return _unstable_status(run_id=run_id, observed_at=observed)

    active_stage = mailbox.get("active_stage")
    stage_status = (
        mailbox.get("stage_states", {}).get(active_stage, {}).get("status")
        if active_stage in {"PROPOSAL", "SELECTION"}
        else None
    )
    permit_kind = None if active_permit is None else active_permit["permit_kind"]
    next_action = _next_legal_action(
        supervisor_status=str(supervisor["status"]),
        permit_kind=permit_kind,
        analysis_window_open=(
            None
            if active_window is None
            else bool(active_window["strictly_before_deadline"])
        ),
        active_stage_status=stage_status,
        active_due_schedule_ids=(
            () if active_permit is None else active_permit["due_schedule_ids"]
        ),
        outcome_states=outcome_states,
    )

    failure = None
    if any(
        item is not None
        for item in (
            supervisor.get("failure_digest"),
            dynamic.get("failure_binding"),
            outcome.get("failure_binding"),
        )
    ):
        failure = {
            "supervisor_lane": supervisor.get("failure_lane"),
            "supervisor_ref": supervisor.get("failure_ref"),
            "supervisor_digest": supervisor.get("failure_digest"),
            "dynamic_binding": deepcopy(dynamic.get("failure_binding")),
            "outcome_binding": deepcopy(outcome.get("failure_binding")),
        }
    dynamic_status = str(dynamic["status"])
    outcome_status = str(outcome["status"])
    agent_stage = (
        str(active_stage)
        if active_stage in {"PROPOSAL", "SELECTION"}
        else "PROPOSAL_READY"
        if mailbox.get("status") == "READY_FOR_PROPOSAL"
        else "SELECTION_READY"
        if mailbox.get("status") == "READY_FOR_SELECTION"
        else "COMPLETE"
        if mailbox.get("status") == "COMPLETE"
        else "PRE_AGENT"
        if permit_kind == "ANALYSIS_TICK"
        else "NONE"
    )
    return {
        "schema_id": "theory_paper_v32_target_read_status_v1",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "observed_at": observed,
        "status": "STABLE",
        "current_boundary": supervisor["status"],
        "boundaries": {
            "supervisor": {
                "status": supervisor["status"],
                "revision": supervisor["revision"],
                "checkpoint_digest": supervisor[SUPERVISOR_CHECKPOINT_DIGEST_FIELD],
                "lane_states": deepcopy(supervisor["lane_states"]),
                "accepted_analysis_cycles": accepted_count,
                "scheduled_outcomes": supervisor["scheduled_outcomes"],
                "terminal_outcomes": supervisor["terminal_outcomes"],
                "next_analysis_cycle_index": supervisor[
                    "next_analysis_cycle_index"
                ],
                "next_outcome_tick_index": supervisor[
                    "next_outcome_tick_index"
                ],
            },
            "dynamic": {
                "status": dynamic_status,
                "revision": dynamic["revision"],
                "checkpoint_digest": dynamic[DYNAMIC_CHECKPOINT_DIGEST_FIELD],
                "accepted_analysis_cycles": dynamic["accepted_analysis_cycles"],
                "open_cycle_index": dynamic["open_cycle_index"],
            },
            "outcome": {
                "status": outcome_status,
                "revision": outcome["revision"],
                "checkpoint_digest": outcome["checkpoint_digest"],
                "schedule_set_count": len(outcome["schedule_set_bindings"]),
                "attempt_count": len(outcome["attempt_bindings"]),
                "expiry_terminal_count": len(outcome.get("expiry_terminal_bindings", ())),
            },
            "mailbox": mailbox,
        },
        "next_legal_action": next_action,
        "active_permit": (
            None
            if active_permit is None
            else {
                "kind": permit_kind,
                "digest": active_permit[PERMIT_DIGEST_FIELD],
                "analysis_cycle_index": active_permit["analysis_cycle_index"],
                "outcome_tick_index": active_permit["outcome_tick_index"],
                "issued_at": active_permit["issued_at"],
                "deadline_at": (
                    None
                    if active_window is None
                    else active_window["permit_deadline_at"]
                ),
            }
        ),
        "agent_stage": agent_stage,
        "outcome_states": outcome_states,
        "terminal_state": {
            "supervisor_terminal_complete": supervisor["status"] == "TERMINAL_COMPLETE",
            "dynamic_terminal": dynamic_status == "TERMINAL",
            "outcome_terminal": outcome_status == "TERMINAL",
            "failed_closed": supervisor["status"] == "FAILED_CLOSED",
        },
        "failure": failure,
        "retry_allowed": False,
        "resume_allowed": bool(supervisor["resume_allowed"]) and bool(dynamic["resume_allowed"]),
        "same_process_poll_required": False,
        "same_process_poll_reason": "OS_SESSION_NOT_OBSERVABLE_FROM_DURABLE_STATE",
        "outcome_values_read": False,
        "read_scope": "HEADS_PERMIT_MAILBOX_CHECKPOINT_AND_SCHEDULES_ONLY",
        "optimistic_consistency_anchor": "ALL_MUTABLE_HEAD_BYTES_BEFORE_AND_AFTER",
        "state_mutation_count": 0,
        "network_request_count": 0,
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "account_access": False,
        "order_submission": False,
        "executable": False,
    }


__all__ = [
    "V32ReadOnlyStatusError",
    "project_v32_outcome_schedule_states_v1",
    "read_v32_read_only_status_snapshot_v1",
]
