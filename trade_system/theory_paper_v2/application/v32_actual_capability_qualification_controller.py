"""Durable, one-boundary controller for the isolated V3.2 qualification.

Each wake either records one reservation, advances or observes one existing
attempt, or seals the final qualification receipt.  ``PENDING`` is ordinary
durable state and never authorizes a second attempt.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Callable, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ..v32_durable_json import (
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.governance.v32_authorization import (
    CAPABILITY_KEYS,
    QUALIFICATION_PROFILE,
    verify_v32_authority_v1,
)
from ..domain.v32_actual_capability_attempt_progress import (
    verify_v32_actual_capability_attempt_progress_v1,
)
from .v32_actual_capability_ports import (
    V32ActualCapabilityEvidenceStorePort,
    V32DurableQualificationAttemptPort,
)
from .v32_actual_capability_qualification import (
    ATTEMPT_ORDER,
    seal_v32_actual_capability_qualification_from_completed_attempts,
)


class V32ActualCapabilityQualificationControllerError(ValueError):
    """The durable qualification controller failed closed."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


SCHEMA_ID = "theory_paper_v32_actual_capability_controller_checkpoint_v1"
DIGEST_FIELD = "actual_capability_controller_checkpoint_digest"
SCHEMA_VERSION = "1.1.0"
MATERIALIZATION_FAILURE_SCHEMA_ID = (
    "theory_paper_v32_qualification_materialization_failure_v1"
)
MATERIALIZATION_FAILURE_DIGEST_FIELD = (
    "qualification_materialization_failure_digest"
)
MATERIALIZATION_FAILURE_SCHEMA_VERSION = "1.1.0"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_STABLE_FAILURE_CODE = re.compile(r"^[A-Z][A-Z0-9_:.-]{0,159}$")
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_CAPABILITY_STATE_FIELDS = frozenset(
    {
        "status",
        "reservation_binding",
        "evidence_root_binding",
        "resume_token",
        "resume_requested_at",
        "observed_state_digest",
        "pending_reason",
        "adapter_advances",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "controller_id",
        "qualification_id",
        "qualification_run_id",
        "target_run_id",
        "qualification_authority_digest",
        "qualification_authority_binding",
        "evidence_store_root",
        "revision",
        "predecessor_checkpoint_digest",
        "status",
        "capability_states",
        "qualification_receipt_binding",
        "failure_evidence_binding",
        "created_at",
        "updated_at",
        "last_boundary_kind",
        "failure_code",
        "source_scope",
        "external_execution_authority",
        "executable",
        DIGEST_FIELD,
    }
)
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_MATERIALIZATION_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "controller_id",
        "qualification_id",
        "qualification_run_id",
        "target_run_id",
        "capability",
        "materialization_stage",
        "failure_codes",
        "failure_time_status",
        "failed_at",
        "last_known_at",
        "predecessor_checkpoint_digest",
        "qualification_authority_binding",
        "attempt_reservation_binding",
        "material_store_root",
        "material_prefix_status",
        "material_scan_failure_codes",
        "material_predecessor_bindings",
        "material_predecessor_count",
        "mailbox_store_root",
        "mailbox_prefix_status",
        "mailbox_scan_failure_codes",
        "mailbox_prefix_bindings",
        "probe_store_root",
        "probe_prefix_status",
        "probe_scan_failure_codes",
        "probe_schedule_binding",
        "retry_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        MATERIALIZATION_FAILURE_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ActualCapabilityQualificationControllerError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32ActualCapabilityQualificationControllerError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ActualCapabilityQualificationControllerError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text
    ):
        raise V32ActualCapabilityQualificationControllerError(code)
    return text


def _stable_exception_failure_codes(exc: BaseException) -> list[str]:
    """Return only typed stable codes; never persist exception prose."""

    codes: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(codes) < 8:
        seen.add(id(current))
        candidate = getattr(current, "failure_code", None)
        if candidate is None:
            # Typed V3.2 validators conventionally expose their stable code as
            # the sole exception argument.  Persist it only when it passes the
            # same closed token grammar; arbitrary prose remains excluded.
            rendered = str(current)
            if _STABLE_FAILURE_CODE.fullmatch(rendered) is not None:
                candidate = rendered
        if (
            isinstance(candidate, str)
            and _STABLE_FAILURE_CODE.fullmatch(candidate) is not None
            and candidate not in codes
        ):
            codes.append(candidate)
        context = getattr(current, "failure_context", None)
        context_codes = (
            context.get("failure_codes") if isinstance(context, Mapping) else None
        )
        if isinstance(context_codes, (list, tuple)):
            for code in context_codes:
                if (
                    isinstance(code, str)
                    and _STABLE_FAILURE_CODE.fullmatch(code) is not None
                    and code not in codes
                    and len(codes) < 8
                ):
                    codes.append(code)
        current = current.__cause__ or current.__context__
    if not codes:
        return ["UNCLASSIFIED_STRUCTURAL_FAILURE"]
    return codes


def _stable_exception_failure_chain(exc: BaseException) -> str:
    return ":".join(_stable_exception_failure_codes(exc))


def stable_v32_materialization_failure_codes_v1(
    exc: BaseException,
) -> tuple[str, ...]:
    """Extract the ordered, prose-free typed error chain for one failure."""

    codes = _stable_exception_failure_codes(exc)
    if codes == ["UNCLASSIFIED_STRUCTURAL_FAILURE"]:
        fallback = f"UNCLASSIFIED_{type(exc).__name__.upper()}"
        if _STABLE_FAILURE_CODE.fullmatch(fallback) is not None:
            codes = [fallback]
    return tuple(codes)


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _relative(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32ActualCapabilityQualificationControllerError(code)
    return text


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32ActualCapabilityQualificationControllerError(code)
    return {
        "path": _relative(value.get("path"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": str(_digest(value.get("semantic_digest"), code)),
        "physical_sha256": str(_digest(value.get("physical_sha256"), code)),
    }


def _material_predecessor_bindings(
    value: Any, code: str
) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping):
        raise V32ActualCapabilityQualificationControllerError(code)
    result: dict[str, dict[str, str]] = {}
    for role, supplied in sorted(value.items()):
        if (
            not isinstance(role, str)
            or not role
            or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                for char in role
            )
        ):
            raise V32ActualCapabilityQualificationControllerError(code)
        result[role] = _binding(supplied, code)
    return result


def _optional_binding(value: Any, code: str) -> dict[str, str] | None:
    return None if value is None else _binding(value, code)


def _binding_inventory(value: Any, code: str) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise V32ActualCapabilityQualificationControllerError(code)
    rows = [_binding(row, code) for row in value]
    if len({row["path"] for row in rows}) != len(rows):
        raise V32ActualCapabilityQualificationControllerError(code)
    ordered = sorted(rows, key=lambda row: row["path"])
    if rows != ordered:
        raise V32ActualCapabilityQualificationControllerError(code)
    return rows


def _prefix_replay_state(
    *, status: Any, failure_codes: Any, code: str
) -> tuple[str, list[str]]:
    if isinstance(failure_codes, (str, bytes)) or not isinstance(
        failure_codes, (list, tuple)
    ):
        raise V32ActualCapabilityQualificationControllerError(code)
    codes = list(failure_codes)
    if (
        len(codes) > 8
        or len(codes) != len(set(codes))
        or any(
            not isinstance(item, str)
            or _STABLE_FAILURE_CODE.fullmatch(item) is None
            for item in codes
        )
    ):
        raise V32ActualCapabilityQualificationControllerError(code)
    if status == "VERIFIED_EXACT":
        if codes:
            raise V32ActualCapabilityQualificationControllerError(code)
    elif status == "UNKNOWN_REPLAY_FAILED":
        if not codes:
            raise V32ActualCapabilityQualificationControllerError(code)
    else:
        raise V32ActualCapabilityQualificationControllerError(code)
    return str(status), codes


def build_v32_qualification_materialization_failure_v1(
    *,
    controller_checkpoint: Mapping[str, Any],
    materialization_stage: str,
    failure_codes: tuple[str, ...],
    failure_time_status: str,
    failed_at: str | None,
    last_known_at: str,
    qualification_authority_binding: Mapping[str, Any],
    attempt_reservation_binding: Mapping[str, Any],
    material_store_root: str,
    material_prefix_status: str,
    material_scan_failure_codes: tuple[str, ...],
    material_predecessor_bindings: Mapping[str, Any],
    mailbox_store_root: str,
    mailbox_prefix_status: str,
    mailbox_scan_failure_codes: tuple[str, ...],
    mailbox_prefix_bindings: list[Mapping[str, Any]],
    probe_store_root: str,
    probe_prefix_status: str,
    probe_scan_failure_codes: tuple[str, ...],
    probe_schedule_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the write-once terminal receipt for the CURRENT_CODEX prefix."""

    verify_v32_actual_capability_controller_checkpoint_v1(controller_checkpoint)
    if (
        controller_checkpoint.get("status") == "FAILED_CLOSED"
        or controller_checkpoint.get("capability_states", {})
        .get("CURRENT_CODEX", {})
        .get("status")
        != "PENDING"
        or controller_checkpoint["capability_states"]["CURRENT_CODEX"].get(
            "reservation_binding"
        )
        != dict(attempt_reservation_binding)
        or controller_checkpoint.get("qualification_authority_binding")
        != dict(qualification_authority_binding)
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_MATERIAL_FAILURE_PREFIX_INVALID"
        )
    stage = _text(
        materialization_stage,
        "V32_ACTUAL_MATERIAL_FAILURE_STAGE_INVALID",
    )
    if _STABLE_FAILURE_CODE.fullmatch(stage) is None:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_MATERIAL_FAILURE_STAGE_INVALID"
        )
    if (
        not isinstance(failure_codes, tuple)
        or not failure_codes
        or len(failure_codes) > 8
        or len(set(failure_codes)) != len(failure_codes)
        or any(
            not isinstance(code, str)
            or _STABLE_FAILURE_CODE.fullmatch(code) is None
            for code in failure_codes
        )
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_MATERIAL_FAILURE_CODE_INVALID"
        )
    predecessors = _material_predecessor_bindings(
        material_predecessor_bindings,
        "V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID",
    )
    material_status, material_scan_codes = _prefix_replay_state(
        status=material_prefix_status,
        failure_codes=material_scan_failure_codes,
        code="V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID",
    )
    mailbox_status, mailbox_scan_codes = _prefix_replay_state(
        status=mailbox_prefix_status,
        failure_codes=mailbox_scan_failure_codes,
        code="V32_ACTUAL_MATERIAL_FAILURE_MAILBOX_INVALID",
    )
    probe_status, probe_scan_codes = _prefix_replay_state(
        status=probe_prefix_status,
        failure_codes=probe_scan_failure_codes,
        code="V32_ACTUAL_MATERIAL_FAILURE_PROBE_INVALID",
    )
    mailbox_bindings = _binding_inventory(
        mailbox_prefix_bindings,
        "V32_ACTUAL_MATERIAL_FAILURE_MAILBOX_INVALID",
    )
    probe_binding = _optional_binding(
        probe_schedule_binding,
        "V32_ACTUAL_MATERIAL_FAILURE_PROBE_INVALID",
    )
    if (
        (material_status == "UNKNOWN_REPLAY_FAILED" and predecessors)
        or (mailbox_status == "UNKNOWN_REPLAY_FAILED" and mailbox_bindings)
        or (probe_status == "UNKNOWN_REPLAY_FAILED" and probe_binding is not None)
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_MATERIAL_FAILURE_UNKNOWN_PREFIX_INVALID"
        )
    last_known = _time(
        last_known_at, "V32_ACTUAL_MATERIAL_FAILURE_TIME_INVALID"
    )
    if failure_time_status == "OBSERVED":
        failed = _time(failed_at, "V32_ACTUAL_MATERIAL_FAILURE_TIME_INVALID")
        time_valid = (
            _moment(failed, "V32_ACTUAL_MATERIAL_FAILURE_TIME_INVALID")
            >= _moment(
                controller_checkpoint["updated_at"],
                "V32_ACTUAL_MATERIAL_FAILURE_TIME_INVALID",
            )
            and last_known == failed
        )
    elif failure_time_status == "UNKNOWN_CLOCK_UNAVAILABLE":
        failed = None
        time_valid = (
            failed_at is None
            and last_known == controller_checkpoint["updated_at"]
        )
    else:
        time_valid = False
        failed = None
    if not time_valid:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_MATERIAL_FAILURE_TIME_INVALID"
        )
    return self_digest(
        {
            "schema_id": MATERIALIZATION_FAILURE_SCHEMA_ID,
            "schema_version": MATERIALIZATION_FAILURE_SCHEMA_VERSION,
            "controller_id": controller_checkpoint["controller_id"],
            "qualification_id": controller_checkpoint["qualification_id"],
            "qualification_run_id": controller_checkpoint[
                "qualification_run_id"
            ],
            "target_run_id": controller_checkpoint["target_run_id"],
            "capability": "CURRENT_CODEX",
            "materialization_stage": stage,
            "failure_codes": list(failure_codes),
            "failure_time_status": failure_time_status,
            "failed_at": failed,
            "last_known_at": last_known,
            "predecessor_checkpoint_digest": controller_checkpoint[DIGEST_FIELD],
            "qualification_authority_binding": _binding(
                qualification_authority_binding,
                "V32_ACTUAL_MATERIAL_FAILURE_AUTHORITY_INVALID",
            ),
            "attempt_reservation_binding": _binding(
                attempt_reservation_binding,
                "V32_ACTUAL_MATERIAL_FAILURE_ATTEMPT_INVALID",
            ),
            "material_store_root": _relative(
                material_store_root,
                "V32_ACTUAL_MATERIAL_FAILURE_ROOT_INVALID",
            ),
            "material_prefix_status": material_status,
            "material_scan_failure_codes": material_scan_codes,
            "material_predecessor_bindings": predecessors,
            "material_predecessor_count": len(predecessors),
            "mailbox_store_root": _relative(
                mailbox_store_root,
                "V32_ACTUAL_MATERIAL_FAILURE_ROOT_INVALID",
            ),
            "mailbox_prefix_status": mailbox_status,
            "mailbox_scan_failure_codes": mailbox_scan_codes,
            "mailbox_prefix_bindings": mailbox_bindings,
            "probe_store_root": _relative(
                probe_store_root,
                "V32_ACTUAL_MATERIAL_FAILURE_ROOT_INVALID",
            ),
            "probe_prefix_status": probe_status,
            "probe_scan_failure_codes": probe_scan_codes,
            "probe_schedule_binding": probe_binding,
            "retry_allowed": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        MATERIALIZATION_FAILURE_DIGEST_FIELD,
    )


def verify_v32_qualification_materialization_failure_v1(
    document: Mapping[str, Any],
) -> str:
    if (
        not isinstance(document, Mapping)
        or set(document) != _MATERIALIZATION_FAILURE_FIELDS
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, MATERIALIZATION_FAILURE_DIGEST_FIELD
        )
        stage = _text(
            document["materialization_stage"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        codes = document["failure_codes"]
        predecessors = _material_predecessor_bindings(
            document["material_predecessor_bindings"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        material_status, _ = _prefix_replay_state(
            status=document["material_prefix_status"],
            failure_codes=document["material_scan_failure_codes"],
            code="V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        mailbox_status, _ = _prefix_replay_state(
            status=document["mailbox_prefix_status"],
            failure_codes=document["mailbox_scan_failure_codes"],
            code="V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        probe_status, _ = _prefix_replay_state(
            status=document["probe_prefix_status"],
            failure_codes=document["probe_scan_failure_codes"],
            code="V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        mailbox_bindings = _binding_inventory(
            document["mailbox_prefix_bindings"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        probe_binding = _optional_binding(
            document["probe_schedule_binding"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        if (
            document["schema_id"] != MATERIALIZATION_FAILURE_SCHEMA_ID
            or document["schema_version"]
            != MATERIALIZATION_FAILURE_SCHEMA_VERSION
            or document["capability"] != "CURRENT_CODEX"
            or _STABLE_FAILURE_CODE.fullmatch(stage) is None
            or not isinstance(codes, list)
            or not codes
            or len(codes) > 8
            or len(codes) != len(set(codes))
            or any(
                not isinstance(code, str)
                or _STABLE_FAILURE_CODE.fullmatch(code) is None
                for code in codes
            )
            or document["material_predecessor_count"] != len(predecessors)
            or isinstance(document["material_predecessor_count"], bool)
            or (material_status == "UNKNOWN_REPLAY_FAILED" and predecessors)
            or (
                mailbox_status == "UNKNOWN_REPLAY_FAILED"
                and mailbox_bindings
            )
            or (
                probe_status == "UNKNOWN_REPLAY_FAILED"
                and probe_binding is not None
            )
            or document["retry_allowed"] is not False
            or document["source_scope"] != "PUBLIC_NON_ACCOUNT_ONLY"
            or document["external_execution_authority"]
            != "NONE_LOCAL_SIMULATION"
            or document["executable"] is not False
        ):
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_INVALID"
            )
        for field in (
            "controller_id",
            "qualification_id",
            "qualification_run_id",
            "target_run_id",
        ):
            _text(document[field], "V32_ACTUAL_MATERIAL_FAILURE_INVALID")
        time_status = document["failure_time_status"]
        last_known = _time(
            document["last_known_at"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        if time_status == "OBSERVED":
            failed = _time(
                document["failed_at"],
                "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
            )
            if last_known != failed:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_INVALID"
                )
        elif time_status == "UNKNOWN_CLOCK_UNAVAILABLE":
            if document["failed_at"] is not None:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_INVALID"
                )
        else:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_INVALID"
            )
        _digest(
            document["predecessor_checkpoint_digest"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        _binding(
            document["qualification_authority_binding"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        _binding(
            document["attempt_reservation_binding"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        _relative(
            document["material_store_root"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        _relative(
            document["mailbox_store_root"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
        _relative(
            document["probe_store_root"],
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID",
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityQualificationControllerError):
            raise
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_MATERIAL_FAILURE_INVALID"
        ) from exc
    return supplied


def _replay_failure_evidence_binding(
    *,
    attempt_port: V32DurableQualificationAttemptPort,
    binding_value: Mapping[str, Any],
) -> dict[str, str]:
    supplied = _binding(
        binding_value,
        "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_INVALID",
    )
    verifier = getattr(
        attempt_port, "verify_failure_evidence_binding", None
    )
    if not callable(verifier):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_REPLAYER_MISSING"
        )
    try:
        replayed = _binding(
            verifier(supplied),
            "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_INVALID",
        )
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(
            exc, V32ActualCapabilityQualificationControllerError
        ):
            raise
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_REPLAY_FAILED"
        ) from exc
    if replayed != supplied:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_REPLAY_MISMATCH"
        )
    return replayed


def _empty_capability_state() -> dict[str, Any]:
    return {
        "status": "READY",
        "reservation_binding": None,
        "evidence_root_binding": None,
        "resume_token": None,
        "resume_requested_at": None,
        "observed_state_digest": None,
        "pending_reason": None,
        "adapter_advances": 0,
    }


def _capability_state(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CAPABILITY_STATE_FIELDS:
        raise V32ActualCapabilityQualificationControllerError(code)
    status = value.get("status")
    if status not in {"READY", "PENDING", "COMPLETE"}:
        raise V32ActualCapabilityQualificationControllerError(code)
    advances = value.get("adapter_advances")
    if isinstance(advances, bool) or not isinstance(advances, int) or advances < 0:
        raise V32ActualCapabilityQualificationControllerError(code)
    reservation = value.get("reservation_binding")
    root = value.get("evidence_root_binding")
    resume = _digest(value.get("resume_token"), code, nullable=True)
    requested = value.get("resume_requested_at")
    requested = None if requested is None else _time(requested, code)
    if (resume is None) != (requested is None):
        raise V32ActualCapabilityQualificationControllerError(code)
    observed = _digest(value.get("observed_state_digest"), code, nullable=True)
    reason = value.get("pending_reason")
    if reason is not None:
        reason = _text(reason, code)
    if status == "READY":
        if any(
            item is not None
            for item in (reservation, root, resume, requested, observed, reason)
        ) or advances != 0:
            raise V32ActualCapabilityQualificationControllerError(code)
    elif status == "PENDING":
        if reservation is None or root is not None or reason is None:
            raise V32ActualCapabilityQualificationControllerError(code)
        reservation = _binding(reservation, code)
    else:
        if (
            reservation is None
            or root is None
            or reason is not None
            or resume is not None
            or requested is not None
            or observed is None
            or advances < 1
        ):
            raise V32ActualCapabilityQualificationControllerError(code)
        reservation = _binding(reservation, code)
        root = _binding(root, code)
    return {
        "status": status,
        "reservation_binding": reservation,
        "evidence_root_binding": root,
        "resume_token": resume,
        "resume_requested_at": requested,
        "observed_state_digest": observed,
        "pending_reason": reason,
        "adapter_advances": advances,
    }


def _overall_status(states: Mapping[str, Mapping[str, Any]]) -> str:
    statuses = [states[capability]["status"] for capability in ATTEMPT_ORDER]
    if all(status == "READY" for status in statuses):
        return "READY"
    if all(status == "COMPLETE" for status in statuses):
        return "READY_TO_SEAL"
    return "RUNNING"


def build_v32_actual_capability_controller_genesis_v1(
    *,
    controller_id: str,
    qualification_id: str,
    qualification_authority: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    evidence_store_root: str,
    created_at: str,
) -> dict[str, Any]:
    try:
        authority_digest = verify_v32_authority_v1(qualification_authority)
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_AUTHORITY_INVALID"
        ) from exc
    if (
        qualification_authority.get("profile") != QUALIFICATION_PROFILE
        or qualification_authority.get("status") != "ACTIVE"
        or qualification_authority.get("authorized_operation")
        != "V32_ISOLATED_QUALIFICATION"
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_AUTHORITY_INVALID"
        )
    when = _time(created_at, "V32_ACTUAL_CONTROLLER_TIME_INVALID")
    return self_digest(
        {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "controller_id": _text(controller_id, "V32_ACTUAL_CONTROLLER_ID_INVALID"),
            "qualification_id": _text(
                qualification_id, "V32_ACTUAL_CONTROLLER_ID_INVALID"
            ),
            "qualification_run_id": qualification_authority["run_id"],
            "target_run_id": qualification_authority["target_run_id"],
            "qualification_authority_digest": authority_digest,
            "qualification_authority_binding": _binding(
                qualification_authority_binding,
                "V32_ACTUAL_CONTROLLER_AUTHORITY_INVALID",
            ),
            "evidence_store_root": _relative(
                evidence_store_root, "V32_ACTUAL_CONTROLLER_ROOT_INVALID"
            ),
            "revision": 0,
            "predecessor_checkpoint_digest": None,
            "status": "READY",
            "capability_states": {
                capability: _empty_capability_state()
                for capability in ATTEMPT_ORDER
            },
            "qualification_receipt_binding": None,
            "failure_evidence_binding": None,
            "created_at": when,
            "updated_at": when,
            "last_boundary_kind": "CONTROLLER_INITIALIZED",
            "failure_code": None,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        DIGEST_FIELD,
    )


def verify_v32_actual_capability_controller_checkpoint_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _CHECKPOINT_FIELDS:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
        )
    try:
        digest = verify_self_digest(document, DIGEST_FIELD)
        if (
            document.get("schema_id") != SCHEMA_ID
            or document.get("schema_version") != SCHEMA_VERSION
            or not isinstance(document.get("capability_states"), Mapping)
            or set(document["capability_states"]) != set(ATTEMPT_ORDER)
        ):
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
            )
        states = {
            capability: _capability_state(
                document["capability_states"][capability],
                "V32_ACTUAL_CONTROLLER_CAPABILITY_STATE_INVALID",
            )
            for capability in ATTEMPT_ORDER
        }
        revision = document["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
            )
        predecessor = _digest(
            document["predecessor_checkpoint_digest"],
            "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID",
            nullable=True,
        )
        status = document["status"]
        if status not in {
            "READY",
            "RUNNING",
            "READY_TO_SEAL",
            "COMPLETE",
            "FAILED_CLOSED",
        }:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
            )
        receipt = document["qualification_receipt_binding"]
        failure_binding = document["failure_evidence_binding"]
        failure = document["failure_code"]
        intrinsic = _overall_status(states)
        if status in {"READY", "RUNNING", "READY_TO_SEAL"} and status != intrinsic:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
            )
        if status == "COMPLETE":
            if (
                intrinsic != "READY_TO_SEAL"
                or receipt is None
                or failure is not None
                or failure_binding is not None
            ):
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
                )
            receipt = _binding(
                receipt, "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
            )
        elif status == "FAILED_CLOSED":
            if receipt is not None or not isinstance(failure, str) or not failure:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
                )
            if failure_binding is not None:
                _binding(
                    failure_binding,
                    "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_INVALID",
                )
        elif (
            receipt is not None
            or failure is not None
            or failure_binding is not None
        ):
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
            )
        if (
            (revision == 0) != (predecessor is None)
            or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
            or document.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or document.get("executable") is not False
            or _moment(document["updated_at"], "V32_ACTUAL_CONTROLLER_TIME_INVALID")
            < _moment(document["created_at"], "V32_ACTUAL_CONTROLLER_TIME_INVALID")
        ):
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
            )
        _text(document["controller_id"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
        _text(document["qualification_id"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
        _text(document["qualification_run_id"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
        _text(document["target_run_id"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
        _digest(document["qualification_authority_digest"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
        _binding(document["qualification_authority_binding"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
        _relative(document["evidence_store_root"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
        _time(document["created_at"], "V32_ACTUAL_CONTROLLER_TIME_INVALID")
        _time(document["updated_at"], "V32_ACTUAL_CONTROLLER_TIME_INVALID")
        _text(document["last_boundary_kind"], "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityQualificationControllerError):
            raise
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_CHECKPOINT_INVALID"
        ) from exc
    return digest


def _verify_transition(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    before_digest = verify_v32_actual_capability_controller_checkpoint_v1(before)
    verify_v32_actual_capability_controller_checkpoint_v1(after)
    immutable = (
        "controller_id",
        "qualification_id",
        "qualification_run_id",
        "target_run_id",
        "qualification_authority_digest",
        "qualification_authority_binding",
        "evidence_store_root",
        "created_at",
        "source_scope",
        "external_execution_authority",
        "executable",
    )
    if (
        any(before[field] != after[field] for field in immutable)
        or after["revision"] != before["revision"] + 1
        or after["predecessor_checkpoint_digest"] != before_digest
        or _moment(after["updated_at"], "V32_ACTUAL_CONTROLLER_TIME_INVALID")
        < _moment(before["updated_at"], "V32_ACTUAL_CONTROLLER_TIME_INVALID")
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_TRANSITION_INVALID"
        )
    if after["status"] == "FAILED_CLOSED":
        if (
            after["capability_states"] != before["capability_states"]
            or after["qualification_receipt_binding"] is not None
        ):
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_FAILURE_TRANSITION_INVALID"
            )
        boundary = str(after["last_boundary_kind"])
        failure_code = str(after["failure_code"])
        failure_binding = after["failure_evidence_binding"]
        if boundary == "QUALIFICATION_SEAL_FAILED_CLOSED":
            legal = (
                before["status"] == "READY_TO_SEAL"
                and failure_binding is None
                and failure_code.startswith("QUALIFICATION_SEAL_FAILED:")
            )
        elif boundary == "MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX":
            states = before["capability_states"]
            legal = (
                before["status"] == "RUNNING"
                and states["PUBLIC_SOURCE"]["status"] == "COMPLETE"
                and states["CURRENT_CODEX"]["status"] == "PENDING"
                and states["OUTCOME_MONITOR"]["status"] == "READY"
                and failure_binding is not None
                and failure_code.startswith(
                    "MATERIALIZATION_FAILED:CURRENT_CODEX:"
                )
            )
        elif boundary.startswith("ATTEMPT_FAILED_CLOSED:"):
            capability = boundary.removeprefix("ATTEMPT_FAILED_CLOSED:")
            incomplete = next(
                (
                    name
                    for name in ATTEMPT_ORDER
                    if before["capability_states"][name]["status"]
                    != "COMPLETE"
                ),
                None,
            )
            legal = (
                capability in ATTEMPT_ORDER
                and capability == incomplete
                and before["capability_states"][capability]["status"]
                == "PENDING"
                and failure_code.startswith(f"ATTEMPT_FAILED:{capability}:")
            )
        else:
            legal = False
        if not legal:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_FAILURE_TRANSITION_INVALID"
            )
        return
    changed = [
        capability
        for capability in ATTEMPT_ORDER
        if before["capability_states"][capability]
        != after["capability_states"][capability]
    ]
    if before["status"] == "READY_TO_SEAL":
        if after["status"] != "COMPLETE" or changed:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_TRANSITION_INVALID"
            )
        return
    if len(changed) != 1:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_TRANSITION_INVALID"
        )
    capability = changed[0]
    index = ATTEMPT_ORDER.index(capability)
    if any(
        after["capability_states"][prior]["status"] != "COMPLETE"
        for prior in ATTEMPT_ORDER[:index]
    ) or any(
        after["capability_states"][later]["status"] != "READY"
        for later in ATTEMPT_ORDER[index + 1 :]
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_ORDER_INVALID"
        )
    left = before["capability_states"][capability]
    right = after["capability_states"][capability]
    if (left["status"], right["status"]) not in {
        ("READY", "PENDING"),
        ("PENDING", "PENDING"),
        ("PENDING", "COMPLETE"),
    }:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_TRANSITION_INVALID"
        )
    if left["status"] == "PENDING" and (
        left["reservation_binding"] != right["reservation_binding"]
        or right["adapter_advances"] != left["adapter_advances"] + 1
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_RETRY_OR_PROGRESS_INVALID"
        )


class LocalV32ActualCapabilityQualificationControllerStore:
    """Append-only full checkpoints; latest state is replayed from the journal."""

    def __init__(self, project_root: Path, root_relative_ref: str) -> None:
        root = Path(project_root).resolve(strict=True)
        if not root.is_dir():
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_STORE_ROOT_INVALID"
            )
        self.project_root = root
        self.root_relative_ref = _relative(
            root_relative_ref, "V32_ACTUAL_CONTROLLER_STORE_ROOT_INVALID"
        )
        self.root = self._safe_path(self.root_relative_ref)
        ensure_directory_tree(self.root)
        self.events = self._safe_path(f"{self.root_relative_ref}/checkpoints")
        ensure_directory_tree(self.events)
        self.lock_path = self._safe_path(f"{self.root_relative_ref}/store.lock")

    @property
    def materialization_failure_ref(self) -> str:
        return f"{self.root_relative_ref}/materialization-failure.json"

    def _safe_path(self, relative_ref: str) -> Path:
        target = self.project_root
        for part in PurePosixPath(
            _relative(relative_ref, "V32_ACTUAL_CONTROLLER_STORE_PATH_INVALID")
        ).parts:
            target = target / part
            if target.exists() and target.is_symlink():
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_PATH_INVALID"
                )
        try:
            target.resolve(strict=False).relative_to(self.project_root)
        except (OSError, ValueError) as exc:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_STORE_PATH_INVALID"
            ) from exc
        return target

    @contextmanager
    def _lock(self):
        ensure_directory_tree(self.lock_path.parent)
        key = str(self.lock_path)
        with _THREAD_LOCKS_GUARD:
            local = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with local, exclusive_lock_file(self.lock_path):
            yield

    def _documents(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.events.glob("*.json")):
            if path.is_symlink():
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_EVENT_INVALID"
                )
            document = load_json_strict(path)
            digest = verify_v32_actual_capability_controller_checkpoint_v1(document)
            expected = f"{int(document['revision']):06d}-{digest}.json"
            if (
                path.name != expected
                or path.read_bytes() != canonical_bytes(document) + b"\n"
            ):
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_EVENT_INVALID"
                )
            try:
                confirm_existing_json(path, document)
            except (OSError, TypeError, ValueError) as exc:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_EVENT_INVALID"
                ) from exc
            rows.append(document)
        for index, document in enumerate(rows):
            if document["revision"] != index:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_EVENT_GAP"
                )
            if index:
                _verify_transition(rows[index - 1], document)
        return rows

    def _read_bound_document(
        self, binding_value: Mapping[str, Any]
    ) -> dict[str, Any]:
        binding = _binding(
            binding_value,
            "V32_ACTUAL_MATERIAL_FAILURE_BINDING_INVALID",
        )
        path = self._safe_path(binding["path"])
        if not path.is_file() or path.is_symlink():
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_BINDING_INVALID"
            )
        try:
            raw = path.read_bytes()
            document = load_json_strict(path)
            semantic = verify_self_digest(document, binding["digest_field"])
        except (OSError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_BINDING_INVALID"
            ) from exc
        if (
            document.get("schema_id") != binding["schema_id"]
            or semantic != binding["semantic_digest"]
            or hashlib.sha256(raw).hexdigest() != binding["physical_sha256"]
            or raw != canonical_bytes(document) + b"\n"
        ):
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_BINDING_INVALID"
            )
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_BINDING_INVALID"
            ) from exc
        return dict(document)

    def _load_materialization_failure_unlocked(
        self,
    ) -> tuple[dict[str, Any], dict[str, str]] | None:
        path = self._safe_path(self.materialization_failure_ref)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_STORE_INVALID"
            )
        try:
            raw = path.read_bytes()
            document = load_json_strict(path)
            semantic = verify_v32_qualification_materialization_failure_v1(
                document
            )
        except (OSError, TypeError, ValueError) as exc:
            if isinstance(
                exc, V32ActualCapabilityQualificationControllerError
            ):
                raise
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_STORE_INVALID"
            ) from exc
        if raw != canonical_bytes(document) + b"\n":
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_STORE_INVALID"
            )
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_STORE_INVALID"
            ) from exc
        return dict(document), {
            "path": self.materialization_failure_ref,
            "schema_id": MATERIALIZATION_FAILURE_SCHEMA_ID,
            "digest_field": MATERIALIZATION_FAILURE_DIGEST_FIELD,
            "semantic_digest": semantic,
            "physical_sha256": hashlib.sha256(raw).hexdigest(),
        }

    def load_materialization_failure(
        self,
    ) -> tuple[dict[str, Any], dict[str, str]] | None:
        with self._lock():
            return self._load_materialization_failure_unlocked()

    def _verify_materialization_failure_prefix(
        self,
        *,
        failed_checkpoint: Mapping[str, Any],
        receipt: Mapping[str, Any],
        binding: Mapping[str, Any],
    ) -> None:
        verify_v32_actual_capability_controller_checkpoint_v1(failed_checkpoint)
        verify_v32_qualification_materialization_failure_v1(receipt)
        expected_code = (
            "MATERIALIZATION_FAILED:CURRENT_CODEX:"
            + ":".join(receipt["failure_codes"])
        )
        current_state = failed_checkpoint["capability_states"]["CURRENT_CODEX"]
        if (
            failed_checkpoint.get("status") != "FAILED_CLOSED"
            or failed_checkpoint.get("last_boundary_kind")
            != "MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX"
            or failed_checkpoint.get("failure_evidence_binding") != dict(binding)
            or failed_checkpoint.get("failure_code") != expected_code
            or receipt.get("controller_id")
            != failed_checkpoint.get("controller_id")
            or receipt.get("qualification_id")
            != failed_checkpoint.get("qualification_id")
            or receipt.get("qualification_run_id")
            != failed_checkpoint.get("qualification_run_id")
            or receipt.get("target_run_id")
            != failed_checkpoint.get("target_run_id")
            or receipt.get("predecessor_checkpoint_digest")
            != failed_checkpoint.get("predecessor_checkpoint_digest")
            or receipt.get("last_known_at")
            != failed_checkpoint.get("updated_at")
            or receipt.get("qualification_authority_binding")
            != failed_checkpoint.get("qualification_authority_binding")
            or receipt.get("attempt_reservation_binding")
            != current_state.get("reservation_binding")
        ):
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_PREFIX_INVALID"
            )
        # Reopen the exact authority, attempt and material prefix.  The roles
        # directory must contain exactly the bound files: additions, deletion,
        # substitution and post-seal self-resigning are all rejected.
        self._read_bound_document(receipt["qualification_authority_binding"])
        self._read_bound_document(receipt["attempt_reservation_binding"])
        predecessors = _material_predecessor_bindings(
            receipt["material_predecessor_bindings"],
            "V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID",
        )
        if receipt["material_prefix_status"] == "VERIFIED_EXACT":
            for predecessor in predecessors.values():
                self._read_bound_document(predecessor)
            roles_root = self._safe_path(
                f"{receipt['material_store_root']}/"
                "v32-qualification-material-v1/roles"
            )
            actual_refs = set()
            if roles_root.exists():
                if roles_root.is_symlink() or not roles_root.is_dir():
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID"
                    )
                for path in roles_root.iterdir():
                    if (
                        path.is_symlink()
                        or not path.is_file()
                        or path.suffix != ".json"
                    ):
                        raise V32ActualCapabilityQualificationControllerError(
                            "V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID"
                        )
                    actual_refs.add(
                        path.relative_to(self.project_root).as_posix()
                    )
            expected_refs = {row["path"] for row in predecessors.values()}
            if actual_refs != expected_refs:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID"
                )
        mailbox_rows = _binding_inventory(
            receipt["mailbox_prefix_bindings"],
            "V32_ACTUAL_MATERIAL_FAILURE_MAILBOX_INVALID",
        )
        if receipt["mailbox_prefix_status"] == "VERIFIED_EXACT":
            mailbox_root = self._safe_path(
                f"{receipt['mailbox_store_root']}/"
                "v32-current-root-agent-mailbox-v1/cycles/0001"
            )
            expected_mailbox_refs = {row["path"] for row in mailbox_rows}
            actual_mailbox_refs: set[str] = set()
            if mailbox_root.exists():
                if mailbox_root.is_symlink() or not mailbox_root.is_dir():
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_MATERIAL_FAILURE_MAILBOX_INVALID"
                    )
                for path in mailbox_root.rglob("*.json"):
                    if path.is_symlink() or not path.is_file():
                        raise V32ActualCapabilityQualificationControllerError(
                            "V32_ACTUAL_MATERIAL_FAILURE_MAILBOX_INVALID"
                        )
                    actual_mailbox_refs.add(
                        path.relative_to(self.project_root).as_posix()
                    )
            if actual_mailbox_refs != expected_mailbox_refs:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_MAILBOX_INVALID"
                )
            mailbox_prefix = (
                f"{receipt['mailbox_store_root']}/"
                "v32-current-root-agent-mailbox-v1/cycles/0001/"
            )
            for binding in mailbox_rows:
                if not binding["path"].startswith(mailbox_prefix):
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_MATERIAL_FAILURE_MAILBOX_INVALID"
                    )
                self._read_bound_document(binding)

        if receipt["probe_prefix_status"] == "VERIFIED_EXACT":
            expected_ref = (
                f"{receipt['probe_store_root']}/"
                "v32-qualification-monitor-probe-v1/schedule.json"
            )
            supplied = receipt["probe_schedule_binding"]
            path = self._safe_path(expected_ref)
            if supplied is None:
                if path.exists() or path.is_symlink():
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_MATERIAL_FAILURE_PROBE_INVALID"
                    )
            else:
                binding = _binding(
                    supplied, "V32_ACTUAL_MATERIAL_FAILURE_PROBE_INVALID"
                )
                if binding["path"] != expected_ref:
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_MATERIAL_FAILURE_PROBE_INVALID"
                    )
                self._read_bound_document(binding)

    def verify_materialization_failure_binding(
        self,
        *,
        failed_checkpoint: Mapping[str, Any],
        binding_value: Mapping[str, Any],
    ) -> dict[str, str]:
        with self._lock():
            recovered = self._load_materialization_failure_unlocked()
            if recovered is None:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_MISSING"
                )
            receipt, expected = recovered
            supplied = _binding(
                binding_value,
                "V32_ACTUAL_MATERIAL_FAILURE_BINDING_INVALID",
            )
            if supplied != expected:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_BINDING_INVALID"
                )
            self._verify_materialization_failure_prefix(
                failed_checkpoint=failed_checkpoint,
                receipt=receipt,
                binding=expected,
            )
            return expected

    def load(self) -> dict[str, Any] | None:
        with self._lock():
            rows = self._documents()
            return None if not rows else dict(rows[-1])

    def append(self, document: Mapping[str, Any]) -> dict[str, Any]:
        digest = verify_v32_actual_capability_controller_checkpoint_v1(document)
        with self._lock():
            rows = self._documents()
            if rows:
                _verify_transition(rows[-1], document)
            elif document.get("revision") != 0:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_GENESIS_REQUIRED"
                )
            path = self.events / f"{int(document['revision']):06d}-{digest}.json"
            try:
                write_once_json(path, document)
            except (OSError, TypeError, ValueError) as exc:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_WRITE_CONFLICT"
                ) from exc
            return dict(document)

    def seal_materialization_failure(
        self,
        *,
        materialization_stage: str,
        failure_codes: tuple[str, ...],
        failure_time_status: str,
        failed_at: str | None,
        last_known_at: str,
        qualification_authority_binding: Mapping[str, Any],
        attempt_reservation_binding: Mapping[str, Any],
        material_store_root: str,
        material_prefix_status: str,
        material_scan_failure_codes: tuple[str, ...],
        material_predecessor_bindings: Mapping[str, Any],
        mailbox_store_root: str,
        mailbox_prefix_status: str,
        mailbox_scan_failure_codes: tuple[str, ...],
        mailbox_prefix_bindings: list[Mapping[str, Any]],
        probe_store_root: str,
        probe_prefix_status: str,
        probe_scan_failure_codes: tuple[str, ...],
        probe_schedule_binding: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Write one failure receipt and its permanent controller boundary."""

        with self._lock():
            rows = self._documents()
            if not rows:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_CONTROLLER_MISSING"
                )
            before = rows[-1]
            if before["status"] == "FAILED_CLOSED":
                recovered = self._load_materialization_failure_unlocked()
                if recovered is None:
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_MATERIAL_FAILURE_MISSING"
                    )
                receipt, binding = recovered
                self._verify_materialization_failure_prefix(
                    failed_checkpoint=before,
                    receipt=receipt,
                    binding=binding,
                )
                return {
                    "runtime_status": "FAILED_CLOSED",
                    "boundary_kind": "NO_ADVANCE_TERMINAL",
                    "checkpoint": dict(before),
                    "failure_receipt": receipt,
                    "failure_evidence_binding": binding,
                }
            receipt = build_v32_qualification_materialization_failure_v1(
                controller_checkpoint=before,
                materialization_stage=materialization_stage,
                failure_codes=failure_codes,
                failure_time_status=failure_time_status,
                failed_at=failed_at,
                last_known_at=last_known_at,
                qualification_authority_binding=qualification_authority_binding,
                attempt_reservation_binding=attempt_reservation_binding,
                material_store_root=material_store_root,
                material_prefix_status=material_prefix_status,
                material_scan_failure_codes=material_scan_failure_codes,
                material_predecessor_bindings=material_predecessor_bindings,
                mailbox_store_root=mailbox_store_root,
                mailbox_prefix_status=mailbox_prefix_status,
                mailbox_scan_failure_codes=mailbox_scan_failure_codes,
                mailbox_prefix_bindings=mailbox_prefix_bindings,
                probe_store_root=probe_store_root,
                probe_prefix_status=probe_prefix_status,
                probe_scan_failure_codes=probe_scan_failure_codes,
                probe_schedule_binding=probe_schedule_binding,
            )
            recovered = self._load_materialization_failure_unlocked()
            path = self._safe_path(self.materialization_failure_ref)
            if recovered is None:
                try:
                    write_once_json(path, receipt)
                except (OSError, TypeError, ValueError) as exc:
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_MATERIAL_FAILURE_STORE_WRITE_CONFLICT"
                    ) from exc
                recovered = self._load_materialization_failure_unlocked()
            if recovered is None or recovered[0] != receipt:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_MATERIAL_FAILURE_STORE_WRITE_CONFLICT"
                )
            durable_receipt, binding = recovered
            after = _next_checkpoint(
                before,
                updated_at=str(durable_receipt["last_known_at"]),
                status="FAILED_CLOSED",
                boundary="MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX",
                failure_evidence_binding=binding,
                failure_code=(
                    "MATERIALIZATION_FAILED:CURRENT_CODEX:"
                    + ":".join(failure_codes)
                ),
            )
            _verify_transition(before, after)
            digest = verify_v32_actual_capability_controller_checkpoint_v1(after)
            event = self.events / f"{int(after['revision']):06d}-{digest}.json"
            try:
                write_once_json(event, after)
            except (OSError, TypeError, ValueError) as exc:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_STORE_WRITE_CONFLICT"
                ) from exc
            self._verify_materialization_failure_prefix(
                failed_checkpoint=after,
                receipt=durable_receipt,
                binding=binding,
            )
            return {
                "runtime_status": "FAILED_CLOSED",
                "boundary_kind": "MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX",
                "checkpoint": after,
                "failure_receipt": durable_receipt,
                "failure_evidence_binding": binding,
            }


def _next_checkpoint(
    before: Mapping[str, Any],
    *,
    updated_at: str,
    states: Mapping[str, Mapping[str, Any]] | None = None,
    status: str | None = None,
    boundary: str,
    qualification_receipt_binding: Mapping[str, Any] | None = None,
    failure_evidence_binding: Mapping[str, Any] | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    candidate = {
        **dict(before),
        "revision": int(before["revision"]) + 1,
        "predecessor_checkpoint_digest": before[DIGEST_FIELD],
        "status": status or _overall_status(states or before["capability_states"]),
        "capability_states": {
            capability: dict((states or before["capability_states"])[capability])
            for capability in ATTEMPT_ORDER
        },
        "qualification_receipt_binding": (
            None
            if qualification_receipt_binding is None
            else dict(qualification_receipt_binding)
        ),
        "failure_evidence_binding": (
            None
            if failure_evidence_binding is None
            else dict(failure_evidence_binding)
        ),
        "updated_at": _time(updated_at, "V32_ACTUAL_CONTROLLER_TIME_INVALID"),
        "last_boundary_kind": boundary,
        "failure_code": failure_code,
    }
    candidate.pop(DIGEST_FIELD, None)
    return self_digest(candidate, DIGEST_FIELD)


def _clock(clock: Callable[[], str]) -> str:
    try:
        value = clock()
    except Exception as exc:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_CLOCK_FAILED"
        ) from exc
    return _time(value, "V32_ACTUAL_CONTROLLER_CLOCK_INVALID")


def replay_v32_actual_capability_qualification_controller_v1(
    *,
    controller_store: LocalV32ActualCapabilityQualificationControllerStore,
    evidence_store: V32ActualCapabilityEvidenceStorePort,
    controller_id: str,
    qualification_id: str,
    qualification_authority: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    attempt_ports: Mapping[str, V32DurableQualificationAttemptPort],
) -> Mapping[str, Any] | None:
    """Read-only replay of controller identity and any terminal failure owner."""

    if (
        controller_store.project_root != evidence_store.project_root
        or not isinstance(attempt_ports, Mapping)
        or set(attempt_ports) != set(CAPABILITY_KEYS)
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_PORTS_INVALID"
        )
    authority_digest = verify_v32_authority_v1(qualification_authority)
    durable_authority = evidence_store.load_binding(
        qualification_authority_binding, verifier=verify_v32_authority_v1
    )
    if durable_authority != dict(qualification_authority):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_AUTHORITY_INVALID"
        )
    checkpoint = controller_store.load()
    if checkpoint is None:
        return None
    if (
        checkpoint.get("controller_id") != controller_id
        or checkpoint.get("qualification_id") != qualification_id
        or checkpoint.get("qualification_run_id")
        != qualification_authority.get("run_id")
        or checkpoint.get("target_run_id")
        != qualification_authority.get("target_run_id")
        or checkpoint.get("qualification_authority_digest") != authority_digest
        or checkpoint.get("qualification_authority_binding")
        != dict(qualification_authority_binding)
        or checkpoint.get("evidence_store_root")
        != evidence_store.root_relative_ref
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_IDENTITY_DRIFT"
        )
    if checkpoint["status"] != "FAILED_CLOSED":
        return checkpoint
    failure_binding = checkpoint.get("failure_evidence_binding")
    boundary = str(checkpoint.get("last_boundary_kind"))
    if boundary == "MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX":
        if failure_binding is None:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_MATERIAL_FAILURE_MISSING"
            )
        controller_store.verify_materialization_failure_binding(
            failed_checkpoint=checkpoint,
            binding_value=failure_binding,
        )
    elif boundary.startswith("ATTEMPT_FAILED_CLOSED:"):
        if failure_binding is not None:
            capability = boundary.removeprefix("ATTEMPT_FAILED_CLOSED:")
            if capability not in attempt_ports:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_OWNER_INVALID"
                )
            _replay_failure_evidence_binding(
                attempt_port=attempt_ports[capability],
                binding_value=failure_binding,
            )
    elif boundary != "QUALIFICATION_SEAL_FAILED_CLOSED":
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_OWNER_INVALID"
        )
    return checkpoint


def advance_v32_actual_capability_qualification_controller_once(
    *,
    controller_store: LocalV32ActualCapabilityQualificationControllerStore,
    evidence_store: V32ActualCapabilityEvidenceStorePort,
    controller_id: str,
    qualification_id: str,
    qualification_authority: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    attempt_ports: Mapping[str, V32DurableQualificationAttemptPort],
    clock: Callable[[], str],
) -> Mapping[str, Any]:
    """Advance at most one durable qualification boundary."""

    if (
        controller_store.project_root != evidence_store.project_root
        or not isinstance(attempt_ports, Mapping)
        or set(attempt_ports) != set(CAPABILITY_KEYS)
        or any(
            not callable(getattr(attempt_ports.get(capability), "advance_once", None))
            for capability in CAPABILITY_KEYS
        )
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_PORTS_INVALID"
        )
    authority_digest = verify_v32_authority_v1(qualification_authority)
    durable_authority = evidence_store.load_binding(
        qualification_authority_binding, verifier=verify_v32_authority_v1
    )
    if durable_authority != dict(qualification_authority):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_AUTHORITY_INVALID"
        )
    checkpoint = controller_store.load()
    if checkpoint is None:
        genesis = build_v32_actual_capability_controller_genesis_v1(
            controller_id=controller_id,
            qualification_id=qualification_id,
            qualification_authority=qualification_authority,
            qualification_authority_binding=qualification_authority_binding,
            evidence_store_root=evidence_store.root_relative_ref,
            created_at=_clock(clock),
        )
        controller_store.append(genesis)
        return {"runtime_status": "PENDING", "boundary_kind": "CONTROLLER_INITIALIZED", "checkpoint": genesis}
    if (
        checkpoint.get("controller_id") != controller_id
        or checkpoint.get("qualification_id") != qualification_id
        or checkpoint.get("qualification_run_id") != qualification_authority.get("run_id")
        or checkpoint.get("target_run_id") != qualification_authority.get("target_run_id")
        or checkpoint.get("qualification_authority_digest") != authority_digest
        or checkpoint.get("qualification_authority_binding")
        != dict(qualification_authority_binding)
        or checkpoint.get("evidence_store_root")
        != evidence_store.root_relative_ref
    ):
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_IDENTITY_DRIFT"
        )
    if checkpoint["status"] == "FAILED_CLOSED":
        failure_binding = checkpoint.get("failure_evidence_binding")
        if failure_binding is not None:
            if (
                checkpoint.get("last_boundary_kind")
                == "MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX"
            ):
                controller_store.verify_materialization_failure_binding(
                    failed_checkpoint=checkpoint,
                    binding_value=failure_binding,
                )
                return {
                    "runtime_status": "FAILED_CLOSED",
                    "boundary_kind": "NO_ADVANCE_TERMINAL",
                    "checkpoint": checkpoint,
                }
            prefix = "ATTEMPT_FAILED_CLOSED:"
            boundary = str(checkpoint.get("last_boundary_kind"))
            if not boundary.startswith(prefix):
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_OWNER_INVALID"
                )
            failed_capability = boundary[len(prefix) :]
            if failed_capability not in attempt_ports:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_OWNER_INVALID"
                )
            replayed = _replay_failure_evidence_binding(
                attempt_port=attempt_ports[failed_capability],
                binding_value=failure_binding,
            )
            if replayed != failure_binding:
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_FAILURE_EVIDENCE_REPLAY_MISMATCH"
                )
        return {"runtime_status": "FAILED_CLOSED", "boundary_kind": "NO_ADVANCE_TERMINAL", "checkpoint": checkpoint}
    if checkpoint["status"] == "COMPLETE":
        return {"runtime_status": "COMPLETE", "boundary_kind": "NO_ADVANCE_TERMINAL", "checkpoint": checkpoint}
    if checkpoint["status"] == "READY_TO_SEAL":
        # Capture the boundary time before sealing.  If any root recovery,
        # validation, replay, path preflight or atomic batch persistence step
        # fails, the same wake records one terminal failure checkpoint.  The
        # terminal guard above guarantees later wakes never call the sealer.
        seal_boundary_at = _clock(clock)
        try:
            completed: dict[str, Mapping[str, Any]] = {}
            for capability in ATTEMPT_ORDER:
                recovered = evidence_store.load_evidence_root(capability)
                if recovered is None:
                    raise V32ActualCapabilityQualificationControllerError(
                        "V32_ACTUAL_CONTROLLER_ROOT_MISSING"
                    )
                completed[capability] = recovered
            sealed = seal_v32_actual_capability_qualification_from_completed_attempts(
                project_root=evidence_store.project_root,
                evidence_store=evidence_store,
                qualification_id=qualification_id,
                qualification_authority=qualification_authority,
                qualification_authority_binding=qualification_authority_binding,
                completed_attempts=completed,
            )
        except Exception as exc:
            failed = _next_checkpoint(
                checkpoint,
                updated_at=seal_boundary_at,
                status="FAILED_CLOSED",
                boundary="QUALIFICATION_SEAL_FAILED_CLOSED",
                failure_code=(
                    "QUALIFICATION_SEAL_FAILED:"
                    f"{_stable_exception_failure_chain(exc)}"
                ),
            )
            controller_store.append(failed)
            return {
                "runtime_status": "FAILED_CLOSED",
                "boundary_kind": "QUALIFICATION_SEAL_FAILED_CLOSED",
                "checkpoint": failed,
            }
        after = _next_checkpoint(
            checkpoint,
            updated_at=seal_boundary_at,
            status="COMPLETE",
            boundary="QUALIFICATION_RECEIPT_SEALED",
            qualification_receipt_binding=sealed["qualification_receipt_binding"],
        )
        controller_store.append(after)
        return {"runtime_status": "COMPLETE", "boundary_kind": "QUALIFICATION_RECEIPT_SEALED", "checkpoint": after, "qualification": sealed}

    capability = next(
        name
        for name in ATTEMPT_ORDER
        if checkpoint["capability_states"][name]["status"] != "COMPLETE"
    )
    state = checkpoint["capability_states"][capability]
    if state["status"] == "READY":
        reserved_at = _clock(clock)
        recovered_reservation = evidence_store.load_attempt_reservation(capability)
        if recovered_reservation is None:
            reserved = evidence_store.reserve_attempt(
                capability=capability,
                qualification_run_id=str(qualification_authority["run_id"]),
                target_run_id=str(qualification_authority["target_run_id"]),
                qualification_authority_digest=authority_digest,
                reserved_at=reserved_at,
            )
        else:
            reserved = recovered_reservation
            reserved_at = str(reserved["reservation"]["reserved_at"])
        states = {name: dict(checkpoint["capability_states"][name]) for name in ATTEMPT_ORDER}
        states[capability] = {
            **_empty_capability_state(),
            "status": "PENDING",
            "reservation_binding": reserved["reservation_binding"],
            "pending_reason": "ATTEMPT_RESERVED_NOT_STARTED",
        }
        after = _next_checkpoint(
            checkpoint,
            updated_at=reserved_at,
            states=states,
            boundary=f"ATTEMPT_RESERVED:{capability}",
        )
        controller_store.append(after)
        return {"runtime_status": "PENDING", "boundary_kind": f"ATTEMPT_RESERVED:{capability}", "checkpoint": after}

    reservation = evidence_store.load_attempt_reservation(capability)
    if reservation is None or reservation["reservation_binding"] != state["reservation_binding"]:
        raise V32ActualCapabilityQualificationControllerError(
            "V32_ACTUAL_CONTROLLER_RESERVATION_MISSING"
        )
    progress_validated = False
    progress_boundary_at: str | None = None
    try:
        progress = attempt_ports[capability].advance_once(
            qualification_authority=qualification_authority,
            reservation=reservation["reservation"],
            reservation_binding=reservation["reservation_binding"],
            resume_token=state["resume_token"],
            resume_requested_at=state["resume_requested_at"],
        )
        verify_v32_actual_capability_attempt_progress_v1(
            progress,
            evidence_root_verifier=evidence_store.verify_evidence_root,
        )
        if progress.get("capability") != capability:
            raise V32ActualCapabilityQualificationControllerError(
                "V32_ACTUAL_CONTROLLER_PORT_CAPABILITY_DRIFT"
            )
        if progress["status"] == "COMPLETE":
            durable_root = evidence_store.load_binding(
                progress["evidence_root_binding"],
                verifier=evidence_store.verify_evidence_root,
            )
            if (
                durable_root != dict(progress["evidence_root"])
                or progress["evidence_root_binding"].get("path")
                != evidence_store.root_ref(capability)
            ):
                raise V32ActualCapabilityQualificationControllerError(
                    "V32_ACTUAL_CONTROLLER_DURABLE_ROOT_MISMATCH"
                )
        progress_validated = True
        if (
            progress["status"] == "PENDING"
            and progress["state_changed"] is False
            and progress["observed_state_digest"] == state["observed_state_digest"]
            and progress["pending_reason"] == state["pending_reason"]
            and progress["resume_token"] == state["resume_token"]
            and progress["resume_requested_at"] == state["resume_requested_at"]
        ):
            return {
                "runtime_status": "PENDING",
                "boundary_kind": "NO_ADVANCE_NOT_DUE",
                "checkpoint": checkpoint,
            }
        states = {
            name: dict(checkpoint["capability_states"][name])
            for name in ATTEMPT_ORDER
        }
        states[capability] = {
            "status": progress["status"],
            "reservation_binding": state["reservation_binding"],
            "evidence_root_binding": progress["evidence_root_binding"],
            "resume_token": progress["resume_token"],
            "resume_requested_at": progress["resume_requested_at"],
            "observed_state_digest": progress["observed_state_digest"],
            "pending_reason": progress["pending_reason"],
            "adapter_advances": int(state["adapter_advances"]) + 1,
        }
        progress_boundary_at = _clock(clock)
        after = _next_checkpoint(
            checkpoint,
            updated_at=progress_boundary_at,
            states=states,
            boundary=(
                f"ATTEMPT_COMPLETED:{capability}"
                if progress["status"] == "COMPLETE"
                else f"ATTEMPT_PENDING:{capability}"
            ),
        )
        controller_store.append(after)
    except Exception as exc:
        failure_at = progress_boundary_at
        if failure_at is None:
            failure_at = (
                str(checkpoint["updated_at"])
                if progress_validated
                else _clock(clock)
            )
        supplied_failure_binding = getattr(
            exc, "failure_evidence_binding", None
        )
        durable_failure_binding = None
        failure_chain = _stable_exception_failure_chain(exc)
        if supplied_failure_binding is not None:
            try:
                durable_failure_binding = _replay_failure_evidence_binding(
                    attempt_port=attempt_ports[capability],
                    binding_value=supplied_failure_binding,
                )
            except V32ActualCapabilityQualificationControllerError as replay_exc:
                failure_chain = (
                    f"{failure_chain}:"
                    f"{_stable_exception_failure_chain(replay_exc)}"
                )
                durable_failure_binding = None
        failed = _next_checkpoint(
            checkpoint,
            updated_at=failure_at,
            status="FAILED_CLOSED",
            boundary=f"ATTEMPT_FAILED_CLOSED:{capability}",
            failure_evidence_binding=durable_failure_binding,
            failure_code=(
                f"ATTEMPT_FAILED:{capability}:"
                f"{failure_chain}"
            ),
        )
        controller_store.append(failed)
        return {"runtime_status": "FAILED_CLOSED", "boundary_kind": f"ATTEMPT_FAILED_CLOSED:{capability}", "checkpoint": failed}
    return {"runtime_status": "PENDING", "boundary_kind": after["last_boundary_kind"], "checkpoint": after}


__all__ = [
    "DIGEST_FIELD",
    "LocalV32ActualCapabilityQualificationControllerStore",
    "MATERIALIZATION_FAILURE_DIGEST_FIELD",
    "MATERIALIZATION_FAILURE_SCHEMA_ID",
    "SCHEMA_ID",
    "V32ActualCapabilityQualificationControllerError",
    "V32DurableQualificationAttemptPort",
    "advance_v32_actual_capability_qualification_controller_once",
    "build_v32_qualification_materialization_failure_v1",
    "build_v32_actual_capability_controller_genesis_v1",
    "replay_v32_actual_capability_qualification_controller_v1",
    "stable_v32_materialization_failure_codes_v1",
    "verify_v32_qualification_materialization_failure_v1",
    "verify_v32_actual_capability_controller_checkpoint_v1",
]
