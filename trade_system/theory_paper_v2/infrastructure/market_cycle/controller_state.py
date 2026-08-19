"""Crash-safe earliest-event and generic Worker-dispatch state for one run.

This adapter owns controller transport state only.  It never wakes a scheduler,
spawns a Worker, interprets Agent prose, or writes one of the five business
artifacts.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from ...v32_durable_json import (
    atomic_replace_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from .capability_assessor_mailbox import (
    LocalCapabilityAssessorMailbox,
    REQUEST_NAME as _ASSESSOR_REQUEST_NAME,
    REQUEST_SCHEMA_ID as _ASSESSOR_REQUEST_SCHEMA_ID,
    RESULT_NAME as _ASSESSOR_RESULT_NAME,
    RESULT_SCHEMA_ID as _ASSESSOR_RESULT_SCHEMA_ID,
)
_SCHEMA_ID = "agent_trade_emotion_v331_controller_wake_dispatch"
_SCHEMA_VERSION = "2.0.0"
_STATE_RELATIVE_PATH = Path("controller/wake-dispatch.json")
_INITIALIZED_RELATIVE_PATH = Path("controller/wake-dispatch.initialized.json")
_LOCK_RELATIVE_PATH = Path("controller/wake-dispatch.lock")
_MAX_STATE_BYTES = 8 * 1024 * 1024
_MAX_TASK_BYTES = 2 * 1024 * 1024
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
_MAX_EVENTS = 4096
_MAX_DISPATCHES = 2048
_EVENT_TYPES = frozenset(
    {"NEXT_SLOT", "OUTCOME_DUE", "WORKER_HARD_STOP", "REVIEW_DEADLINE"}
)
_EVENT_PRIORITY = {
    "WORKER_HARD_STOP": 0,
    "OUTCOME_DUE": 1,
    "REVIEW_DEADLINE": 2,
    "NEXT_SLOT": 3,
}
_ACTIVE_STATUSES = frozenset({"PREPARED", "SPAWN_REQUESTED", "DISPATCHED"})
_TERMINAL_STATUSES = frozenset({"COMPLETED", "EXPIRED"})
_WORKERS = {
    "daily-deep-v1": {
        "task_kind": "DAILY_DEEP",
        "contract": "V331_DAILY_DEEP_READABLE_BASIS_V1",
        "stage": "INPUT_SEALED",
        "request_name": "agent-request.json",
        "request_schema": "agent_trade_emotion_market_cycle_agent_decision_request",
        "request_role": "agent_request_and_non_authoritative_calculations",
        "output_name": "result.json",
        "output_schema": "agent_trade_emotion_v331_worker_result",
        "completion_field": "completed_at",
        "expiry_reason": "CONTROLLER_DAILY_DEEP_DEADLINE_EXPIRED",
    },
    "decision-v1": {
        "task_kind": "DECISION",
        "contract": "V331_AGENT_FIRST_DECISION_READABLE_V1",
        "stage": "INPUT_SEALED",
        "request_name": "agent-request.json",
        "request_schema": "agent_trade_emotion_market_cycle_agent_decision_request",
        "request_role": "agent_request_and_non_authoritative_calculations",
        "output_name": "agent-delivery.json",
        "output_schema": "agent_trade_emotion_market_cycle_agent_decision_delivery",
        "completion_field": "delivered_at",
        "expiry_reason": "CONTROLLER_DECISION_DEADLINE_EXPIRED",
    },
    "capability-assessor-v1": {
        "task_kind": "CAPABILITY_ASSESSMENT",
        "contract": "V332_CAPABILITY_ASSESSOR_READABLE_V1",
        "stage": "PRE_OUTCOME_ASSESSMENT",
        "request_name": _ASSESSOR_REQUEST_NAME,
        "request_schema": _ASSESSOR_REQUEST_SCHEMA_ID,
        "request_role": "sealed_pre_outcome_capability_assessor_request",
        "output_name": _ASSESSOR_RESULT_NAME,
        "output_schema": _ASSESSOR_RESULT_SCHEMA_ID,
        "completion_field": "completed_at",
        "expiry_reason": "CONTROLLER_CAPABILITY_ASSESSOR_DEADLINE_EXPIRED",
    },
    "review-v1": {
        "task_kind": "REVIEW",
        "contract": "V331_AGENT_FIRST_REVIEW_READABLE_V1",
        "stage": "OUTCOME_SEALED",
        "request_name": "agent-review-request.json",
        "request_schema": "agent_trade_emotion_market_cycle_agent_review_request",
        "request_role": "review_request",
        "output_name": "agent-review-delivery.json",
        "output_schema": "agent_trade_emotion_market_cycle_agent_review_delivery",
        "completion_field": "delivered_at",
        "expiry_reason": "CONTROLLER_REVIEW_DEADLINE_EXPIRED",
    },
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,511}$")
_SAFE_CYCLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,255}$")
_RUN_BINDING_SCHEMA_ID = "agent_trade_emotion_v331_cycle_run_binding"
_RUN_BINDING_SCHEMA_VERSION = "1.0.0"
_RUN_BINDING_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "run_manifest_identity_sha256",
        "run_id",
        "theory_manifest_sha256",
        "implementation_sha256",
        "contract_identity",
        "market_contract_identity",
        "experiment_identity",
    }
)
_TASK_RECEIPT_NAME = "controller-task-receipt.json"
_LEGACY_V331_CONTRACT_IDENTITY = (
    "V331_AGENT_FIRST_VERBATIM_DECISION_REVIEW_V1"
)
_WORKER_RESULT_FIELDS = (
    "schema_id",
    "schema_version",
    "run_id",
    "cycle_id",
    "worker_id",
    "status",
    "started_at",
    "completed_at",
    "elapsed_seconds",
    "input_refs",
    "body_markdown",
)
_DELIVERY_WORKERS = frozenset({"decision-v1", "review-v1"})


class ControllerStateError(RuntimeError):
    """The controller sidecar could not honor its fail-closed contract."""


def _bounded_identity(value: Any, *, code: str) -> str:
    if type(value) is not str or _IDENTITY_RE.fullmatch(value) is None:
        raise ControllerStateError(code)
    return value


def _sha256(value: Any, *, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ControllerStateError(code)
    return value


def _experiment_contract_sha256(identity: str) -> str:
    """Normalize policy digests while keeping named legacy runs deterministic."""

    if _SHA256_RE.fullmatch(identity):
        return identity
    suffix = identity.rsplit("@", 1)
    if len(suffix) == 2 and _SHA256_RE.fullmatch(suffix[1]):
        return suffix[1]
    return hashlib.sha256(identity.encode("utf-8", errors="strict")).hexdigest()


def _timestamp(value: Any, *, code: str) -> datetime:
    if type(value) is not str or not value or len(value) > 64:
        raise ControllerStateError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControllerStateError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ControllerStateError(code)
    return parsed


def _safe_cycle(value: Any) -> str:
    if type(value) is not str or _SAFE_CYCLE_RE.fullmatch(value) is None:
        raise ControllerStateError("CONTROLLER_CYCLE_ID_INVALID")
    return value


def _worker(value: Any) -> tuple[str, Mapping[str, str]]:
    if type(value) is not str or value not in _WORKERS:
        raise ControllerStateError("CONTROLLER_WORKER_ID_INVALID")
    return value, _WORKERS[value]


def _read_regular(path: Path, *, maximum: int, code: str) -> bytes:
    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise ControllerStateError(code) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ControllerStateError(code)
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        raise ControllerStateError(code)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ControllerStateError(code) from exc
    if len(raw) != metadata.st_size:
        raise ControllerStateError(code)
    return raw


def _load_relaxed_object(raw: bytes, *, code: str) -> Mapping[str, Any]:
    """Load Worker transport JSON while admitting finite elapsed-time floats."""

    try:
        text = raw.decode("utf-8", errors="strict")
        duplicate = object()

        def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in values:
                if key in result:
                    raise ValueError(duplicate)
                result[key] = value
            return result

        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ControllerStateError(code) from exc
    if not isinstance(value, Mapping):
        raise ControllerStateError(code)
    return value


class FileControllerState:
    """One immutable-identity-bound generic Worker state owner per run."""

    def __init__(
        self,
        runtime_root: Path | str,
        *,
        run_id: str,
        run_manifest_identity_sha256: str,
        run_manifest_raw_sha256: str,
        theory_manifest_sha256: str,
        implementation_sha256: str,
        contract_identity: str,
        market_contract_identity: str,
        experiment_identity: str,
        clock: Any,
        allow_initialize: bool = True,
    ) -> None:
        root = Path(runtime_root).absolute()
        if not callable(clock) or type(allow_initialize) is not bool:
            raise ControllerStateError("CONTROLLER_CONFIGURATION_INVALID")
        self._root = root
        self._cycles_root = root / "cycles"
        self._agents_root = root / "agents"
        self._state_path = root / _STATE_RELATIVE_PATH
        self._initialized_path = root / _INITIALIZED_RELATIVE_PATH
        self._external_initialized_path = (
            root.parent / ".controller-run-identities" / f"{run_id}.controller-state.json"
        )
        self._lock_path = root / _LOCK_RELATIVE_PATH
        self._clock = clock
        self._allow_initialize = allow_initialize
        # run_manifest_raw_sha256 means the canonical initial OPEN manifest.
        # It remains stable when the same immutable run later becomes CLOSED.
        self._identity = {
            "run_id": _bounded_identity(run_id, code="CONTROLLER_RUN_ID_INVALID"),
            "run_manifest_identity_sha256": _sha256(
                run_manifest_identity_sha256,
                code="CONTROLLER_RUN_MANIFEST_IDENTITY_INVALID",
            ),
            "initial_open_run_manifest_sha256": _sha256(
                run_manifest_raw_sha256,
                code="CONTROLLER_RUN_MANIFEST_INITIAL_OPEN_INVALID",
            ),
            "theory_manifest_sha256": _sha256(
                theory_manifest_sha256, code="CONTROLLER_THEORY_IDENTITY_INVALID"
            ),
            "implementation_sha256": _sha256(
                implementation_sha256,
                code="CONTROLLER_IMPLEMENTATION_IDENTITY_INVALID",
            ),
            "contract_identity": _bounded_identity(
                contract_identity, code="CONTROLLER_CONTRACT_IDENTITY_INVALID"
            ),
            "market_contract_identity": _bounded_identity(
                market_contract_identity,
                code="CONTROLLER_MARKET_CONTRACT_IDENTITY_INVALID",
            ),
            "experiment_identity": _bounded_identity(
                experiment_identity, code="CONTROLLER_EXPERIMENT_IDENTITY_INVALID"
            ),
        }
        if root.name != self._identity["run_id"]:
            raise ControllerStateError("CONTROLLER_RUN_ROOT_IDENTITY_MISMATCH")
        self._initialize()

    def _initialized_document(self) -> dict[str, Any]:
        return {
            "schema_id": "agent_trade_emotion_v331_controller_state_initialized",
            "schema_version": "3.0.0",
            "run_root_canonical_path": str(self._root.resolve(strict=True)),
            "identity": dict(self._identity),
        }

    def _initial(self) -> dict[str, Any]:
        return {
            "schema_id": _SCHEMA_ID,
            "schema_version": _SCHEMA_VERSION,
            "identity": dict(self._identity),
            "revision": 0,
            "events": {},
            "worker_dispatches": {},
        }

    def _initialize(self) -> None:
        with exclusive_lock_file(self._lock_path):
            state_created = False
            try:
                self._state_path.lstat()
            except FileNotFoundError:
                marker_present = False
                for marker in (self._initialized_path, self._external_initialized_path):
                    try:
                        marker.lstat()
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        raise ControllerStateError(
                            "CONTROLLER_STATE_INITIALIZATION_MARKER_UNSAFE"
                        ) from exc
                    marker_present = True
                if marker_present:
                    raise ControllerStateError(
                        "CONTROLLER_STATE_MISSING_AFTER_INITIALIZATION"
                    )
                if not self._allow_initialize:
                    raise ControllerStateError(
                        "CONTROLLER_STATE_NOT_INITIALIZED_BEFORE_CLOSE"
                    )
                try:
                    atomic_replace_json(self._state_path, self._initial())
                    state_created = True
                except (OSError, CanonicalContractError) as exc:
                    raise ControllerStateError(
                        "CONTROLLER_STATE_INITIALIZATION_FAILED"
                    ) from exc
            except OSError as exc:
                raise ControllerStateError("CONTROLLER_STATE_UNSAFE") from exc
            self._load_locked()
            if not self._allow_initialize and not state_created:
                for marker in (self._initialized_path, self._external_initialized_path):
                    try:
                        raw = _read_regular(
                            marker,
                            maximum=64 * 1024,
                            code="CONTROLLER_STATE_NOT_INITIALIZED_BEFORE_CLOSE",
                        )
                        value = loads_json_strict(raw)
                    except CanonicalContractError as exc:
                        raise ControllerStateError(
                            "CONTROLLER_STATE_INITIALIZATION_MARKER_INVALID"
                        ) from exc
                    if (
                        canonical_bytes(value) + b"\n" != raw
                        or value != self._initialized_document()
                    ):
                        raise ControllerStateError(
                            "CONTROLLER_STATE_INITIALIZATION_MARKER_INVALID"
                        )
                return
            try:
                write_once_json(self._initialized_path, self._initialized_document())
                write_once_json(
                    self._external_initialized_path, self._initialized_document()
                )
            except (OSError, CanonicalContractError) as exc:
                raise ControllerStateError(
                    "CONTROLLER_STATE_INITIALIZATION_MARKER_INVALID"
                ) from exc

    def _now(self) -> tuple[str, datetime]:
        value = self._clock()
        return value, _timestamp(value, code="CONTROLLER_CLOCK_INVALID")

    def trusted_now(self) -> str:
        """Expose only the controller's trusted wall clock, never caller time."""

        return self._now()[0]

    @staticmethod
    def _dispatch_key(cycle_id: str, worker_id: str) -> str:
        return hashlib.sha256(
            canonical_bytes({"cycle_id": cycle_id, "worker_id": worker_id})
        ).hexdigest()

    @staticmethod
    def _event_id(cycle_id: str, worker_id: str) -> str:
        return f"worker-hard-stop:{cycle_id}:{worker_id}"

    def _validate_event(self, key: Any, event: Any) -> None:
        if (
            type(key) is not str
            or not isinstance(event, Mapping)
            or frozenset(event)
            != {
                "event_id",
                "event_type",
                "due_at",
                "cycle_id",
                "status",
                "wake_ack",
            }
            or event.get("event_id") != key
            or event.get("event_type") not in _EVENT_TYPES
            or event.get("status") not in {"PENDING", "RESOLVED"}
        ):
            raise ControllerStateError("CONTROLLER_EVENT_INVALID")
        _timestamp(event.get("due_at"), code="CONTROLLER_EVENT_INVALID")
        if event.get("cycle_id") is not None:
            _safe_cycle(event.get("cycle_id"))
        ack = event.get("wake_ack")
        if ack is not None:
            if (
                not isinstance(ack, Mapping)
                or frozenset(ack) != {"scheduler_ref", "scheduled_for", "acked_at"}
                or ack.get("scheduled_for") != event.get("due_at")
            ):
                raise ControllerStateError("CONTROLLER_WAKE_ACK_INVALID")
            _bounded_identity(ack.get("scheduler_ref"), code="CONTROLLER_WAKE_ACK_INVALID")
            _timestamp(ack.get("acked_at"), code="CONTROLLER_WAKE_ACK_INVALID")

    def _validate_dispatch(self, key: Any, record: Any) -> None:
        fields = {
            "dispatch_key",
            "cycle_id",
            "worker_id",
            "task_kind",
            "worker_contract_identity",
            "task_path",
            "task_sha256",
            "request_path",
            "request_sha256",
            "request_packet_sha256",
            "result_path",
            "hard_stop_at",
            "dispatch_id",
            "status",
            "prepared_at",
            "spawn_requested_at",
            "spawn_execution_ref",
            "spawn_acknowledged_at",
            "output_sha256",
            "output_at",
            "completed_at",
            "expiry_reason",
            "expired_at",
        }
        if (
            type(key) is not str
            or not isinstance(record, Mapping)
            or frozenset(record) != fields
            or record.get("dispatch_key") != key
            or self._dispatch_key(record.get("cycle_id"), record.get("worker_id")) != key
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        cycle_id = _safe_cycle(record.get("cycle_id"))
        worker_id, spec = _worker(record.get("worker_id"))
        if (
            record.get("task_kind") != spec["task_kind"]
            or record.get("worker_contract_identity") != spec["contract"]
            or record.get("status") not in _ACTIVE_STATUSES | _TERMINAL_STATUSES
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        _bounded_identity(record.get("dispatch_id"), code="CONTROLLER_WORKER_DISPATCH_INVALID")
        for field in ("task_sha256", "request_sha256", "request_packet_sha256"):
            _sha256(record.get(field), code="CONTROLLER_WORKER_DISPATCH_INVALID")
        for field in ("task_path", "request_path", "result_path"):
            if type(record.get(field)) is not str or not record[field]:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        for field in ("hard_stop_at", "prepared_at"):
            _timestamp(record.get(field), code="CONTROLLER_WORKER_DISPATCH_INVALID")
        for field in (
            "spawn_requested_at",
            "spawn_acknowledged_at",
            "output_at",
            "completed_at",
            "expired_at",
        ):
            if record.get(field) is not None:
                _timestamp(record.get(field), code="CONTROLLER_WORKER_DISPATCH_INVALID")
        status = record["status"]
        if status == "PREPARED" and any(
            record.get(field) is not None
            for field in (
                "spawn_requested_at",
                "spawn_execution_ref",
                "spawn_acknowledged_at",
                "output_sha256",
                "output_at",
                "completed_at",
                "expiry_reason",
                "expired_at",
            )
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if status in {"SPAWN_REQUESTED", "DISPATCHED", "COMPLETED"} and record.get(
            "spawn_requested_at"
        ) is None:
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if status == "SPAWN_REQUESTED" and (
            record.get("spawn_execution_ref") is not None
            or record.get("spawn_acknowledged_at") is not None
            or record.get("completed_at") is not None
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if status in {"DISPATCHED", "COMPLETED"} and (
            record.get("spawn_execution_ref") is None
            or record.get("spawn_acknowledged_at") is None
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if status == "DISPATCHED" and record.get("completed_at") is not None:
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if record.get("spawn_execution_ref") is not None:
            _bounded_identity(
                record.get("spawn_execution_ref"),
                code="CONTROLLER_WORKER_DISPATCH_INVALID",
            )
        if status == "COMPLETED":
            _sha256(record.get("output_sha256"), code="CONTROLLER_WORKER_DISPATCH_INVALID")
            if record.get("output_at") is None or record.get("completed_at") is None:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        elif record.get("output_sha256") is not None or record.get("output_at") is not None:
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if status != "COMPLETED" and record.get("completed_at") is not None:
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if status == "EXPIRED":
            if (
                record.get("expiry_reason") != spec["expiry_reason"]
                or record.get("expired_at") is None
            ):
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        elif record.get("expiry_reason") is not None or record.get("expired_at") is not None:
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
        if cycle_id != record["cycle_id"] or worker_id != record["worker_id"]:
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")

    def _validate_state(self, value: Any) -> dict[str, Any]:
        if (
            not isinstance(value, Mapping)
            or frozenset(value)
            != {"schema_id", "schema_version", "identity", "revision", "events", "worker_dispatches"}
            or value.get("schema_id") != _SCHEMA_ID
            or value.get("schema_version") != _SCHEMA_VERSION
            or value.get("identity") != self._identity
            or type(value.get("revision")) is not int
            or value["revision"] < 0
            or not isinstance(value.get("events"), Mapping)
            or not isinstance(value.get("worker_dispatches"), Mapping)
            or len(value["events"]) > _MAX_EVENTS
            or len(value["worker_dispatches"]) > _MAX_DISPATCHES
        ):
            raise ControllerStateError("CONTROLLER_STATE_INVALID")
        for key, event in value["events"].items():
            self._validate_event(key, event)
        seen: set[tuple[str, str]] = set()
        for key, record in value["worker_dispatches"].items():
            self._validate_dispatch(key, record)
            pair = (record["cycle_id"], record["worker_id"])
            if pair in seen:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_DUPLICATE")
            seen.add(pair)
        return deepcopy(dict(value))

    def _load_locked(self) -> dict[str, Any]:
        raw = _read_regular(
            self._state_path,
            maximum=_MAX_STATE_BYTES,
            code="CONTROLLER_STATE_MISSING_AFTER_INITIALIZATION",
        )
        try:
            value = loads_json_strict(raw)
        except CanonicalContractError as exc:
            raise ControllerStateError("CONTROLLER_STATE_INVALID") from exc
        if canonical_bytes(value) + b"\n" != raw:
            raise ControllerStateError("CONTROLLER_STATE_NOT_CANONICAL")
        return self._validate_state(value)

    def _save_locked(self, state: dict[str, Any], previous_revision: int) -> None:
        if state.get("revision") != previous_revision + 1:
            raise ControllerStateError("CONTROLLER_STATE_REVISION_INVALID")
        self._validate_state(state)
        try:
            atomic_replace_json(self._state_path, state)
        except (OSError, CanonicalContractError) as exc:
            raise ControllerStateError("CONTROLLER_STATE_WRITE_FAILED") from exc

    @staticmethod
    def _event_sort_key(event: Mapping[str, Any]) -> tuple[datetime, int, str]:
        return (
            _timestamp(event.get("due_at"), code="CONTROLLER_EVENT_INVALID"),
            _EVENT_PRIORITY[event["event_type"]],
            event["event_id"],
        )

    def _view(self, state: Mapping[str, Any]) -> dict[str, Any]:
        result = deepcopy(dict(state))
        pending = [
            event
            for event in result["events"].values()
            if isinstance(event, Mapping) and event.get("status") == "PENDING"
        ]
        result["earliest_next_event"] = (
            deepcopy(min(pending, key=self._event_sort_key)) if pending else None
        )
        return result

    def status(self) -> Mapping[str, Any]:
        with exclusive_lock_file(self._lock_path):
            return self._view(self._load_locked())

    def _schedule_locked(
        self,
        state: dict[str, Any],
        event_id: str,
        event_type: str,
        due_at: str,
        cycle_id: str | None,
    ) -> bool:
        event_id = _bounded_identity(event_id, code="CONTROLLER_EVENT_ID_INVALID")
        if event_type not in _EVENT_TYPES:
            raise ControllerStateError("CONTROLLER_EVENT_TYPE_INVALID")
        _timestamp(due_at, code="CONTROLLER_EVENT_DUE_AT_INVALID")
        if cycle_id is not None:
            cycle_id = _safe_cycle(cycle_id)
        expected = {
            "event_id": event_id,
            "event_type": event_type,
            "due_at": due_at,
            "cycle_id": cycle_id,
            "status": "PENDING",
            "wake_ack": None,
        }
        existing = state["events"].get(event_id)
        if existing is None:
            if len(state["events"]) >= _MAX_EVENTS:
                raise ControllerStateError("CONTROLLER_EVENT_CAPACITY_EXCEEDED")
            state["events"][event_id] = expected
            return True
        if any(existing.get(key) != expected[key] for key in ("event_id", "event_type", "due_at", "cycle_id", "status")):
            raise ControllerStateError("CONTROLLER_EVENT_CONFLICT")
        return False

    def schedule_event(
        self,
        event_id: str,
        event_type: str,
        due_at: str,
        cycle_id: str | None = None,
    ) -> Mapping[str, Any]:
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            revision = state["revision"]
            if self._schedule_locked(state, event_id, event_type, due_at, cycle_id):
                state["revision"] = revision + 1
                self._save_locked(state, revision)
            return self._view(state)

    def acknowledge_wake(
        self, event_id: str, scheduler_ref: str, scheduled_for: str
    ) -> Mapping[str, Any]:
        event_id = _bounded_identity(event_id, code="CONTROLLER_EVENT_ID_INVALID")
        scheduler_ref = _bounded_identity(
            scheduler_ref, code="CONTROLLER_WAKE_SCHEDULER_REF_INVALID"
        )
        _timestamp(scheduled_for, code="CONTROLLER_WAKE_SCHEDULE_INVALID")
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            event = state["events"].get(event_id)
            if not isinstance(event, dict) or event.get("status") != "PENDING":
                raise ControllerStateError("CONTROLLER_WAKE_EVENT_INVALID")
            if event.get("due_at") != scheduled_for:
                raise ControllerStateError("CONTROLLER_WAKE_SCHEDULE_MISMATCH")
            existing = event.get("wake_ack")
            if existing is not None:
                if existing.get("scheduler_ref") != scheduler_ref:
                    raise ControllerStateError("CONTROLLER_WAKE_ACK_CONFLICT")
                return self._view(state)
            now, _ = self._now()
            revision = state["revision"]
            event["wake_ack"] = {
                "scheduler_ref": scheduler_ref,
                "scheduled_for": scheduled_for,
                "acked_at": now,
            }
            state["revision"] = revision + 1
            self._save_locked(state, revision)
            return self._view(state)

    def _resolve_locked(self, state: dict[str, Any], event_id: str) -> bool:
        event = state["events"].get(event_id)
        if not isinstance(event, dict):
            raise ControllerStateError("CONTROLLER_EVENT_MISSING")
        if event.get("status") == "RESOLVED":
            return False
        if event.get("status") != "PENDING":
            raise ControllerStateError("CONTROLLER_EVENT_INVALID")
        event["status"] = "RESOLVED"
        return True

    def resolve_event(self, event_id: str) -> Mapping[str, Any]:
        event_id = _bounded_identity(event_id, code="CONTROLLER_EVENT_ID_INVALID")
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            revision = state["revision"]
            if self._resolve_locked(state, event_id):
                state["revision"] = revision + 1
                self._save_locked(state, revision)
            return self._view(state)

    def _transport_path(self, cycle_id: str, name: str) -> Path:
        cycle_id = _safe_cycle(cycle_id)
        path = self._cycles_root / cycle_id / "transport" / name
        try:
            cycles = self._cycles_root.resolve(strict=True)
            transport = path.parent.resolve(strict=True)
            transport.relative_to(cycles)
            for parent in (self._cycles_root, self._cycles_root / cycle_id, path.parent):
                metadata = parent.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    raise ValueError("unsafe transport parent")
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ControllerStateError("CONTROLLER_CYCLE_TRANSPORT_UNSAFE") from exc
        return path

    def _secure_task(self, cycle_id: str, worker_id: str, task_path: Path | str) -> Path:
        expected_root = self._agents_root / f"{cycle_id}--{worker_id}"
        expected = expected_root / "task.json"
        lexical = Path(os.path.abspath(os.fspath(task_path)))
        if lexical != Path(os.path.abspath(os.fspath(expected))):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_PATH_INVALID")
        try:
            agents = self._agents_root.resolve(strict=True)
            root_metadata = expected_root.lstat()
            task_metadata = expected.lstat()
            resolved = expected.resolve(strict=True)
            resolved.relative_to(agents)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ControllerStateError("CONTROLLER_WORKER_TASK_PATH_INVALID") from exc
        if (
            stat.S_ISLNK(root_metadata.st_mode)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_ISLNK(task_metadata.st_mode)
            or not stat.S_ISREG(task_metadata.st_mode)
        ):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_PATH_UNSAFE")
        return resolved

    def _read_request(
        self, cycle_id: str, spec: Mapping[str, str]
    ) -> tuple[Path, bytes, Mapping[str, Any], Mapping[str, Any]]:
        path = self._transport_path(cycle_id, spec["request_name"])
        if spec["request_schema"] == _ASSESSOR_REQUEST_SCHEMA_ID:
            try:
                request = LocalCapabilityAssessorMailbox(self._root).load_request(
                    cycle_id
                )
                raw = _read_regular(
                    path,
                    maximum=_MAX_REQUEST_BYTES,
                    code="CONTROLLER_WORKER_REQUEST_INVALID",
                )
                packet = request["packet"]
            except (KeyError, RuntimeError) as exc:
                raise ControllerStateError(
                    "CONTROLLER_WORKER_REQUEST_INVALID"
                ) from exc
            if (
                packet.get("theory_identity", {}).get("manifest_digest")
                != self._identity["theory_manifest_sha256"]
            ):
                raise ControllerStateError("CONTROLLER_WORKER_REQUEST_INVALID")
            return path.resolve(strict=True), raw, request, packet
        raw = _read_regular(path, maximum=_MAX_REQUEST_BYTES, code="CONTROLLER_WORKER_REQUEST_INVALID")
        try:
            request = loads_json_strict(raw)
            packet = request.get("packet")
            packet_bytes = canonical_bytes(packet)
        except (CanonicalContractError, TypeError) as exc:
            raise ControllerStateError("CONTROLLER_WORKER_REQUEST_INVALID") from exc
        if (
            canonical_bytes(request) + b"\n" != raw
            or request.get("schema_id") != spec["request_schema"]
            or request.get("schema_version") != "1.0.0"
            or request.get("cycle_id") != cycle_id
            or not isinstance(packet, Mapping)
            or packet.get("cycle_id") != cycle_id
            or request.get("packet_sha256") != hashlib.sha256(packet_bytes).hexdigest()
            or request.get("packet_size_bytes") != len(packet_bytes)
            or not isinstance(packet.get("theory_identity"), Mapping)
            or packet["theory_identity"].get("manifest_digest")
            != self._identity["theory_manifest_sha256"]
        ):
            raise ControllerStateError("CONTROLLER_WORKER_REQUEST_INVALID")
        return path.resolve(strict=True), raw, request, packet

    def _capability_assessor_write_boundary(
        self, cycle_id: str, worker_root: Path
    ) -> dict[str, Any]:
        result_path = LocalCapabilityAssessorMailbox(self._root).result_path(
            cycle_id
        ).resolve()
        return {
            "worker_root": str(worker_root.resolve(strict=True)),
            "events_path": str((worker_root / "events.jsonl").resolve()),
            "result_path": str((worker_root / "result.json").resolve()),
            "capability_findings_path": str(result_path),
            "worker_may_write_only": [
                str((worker_root / "events.jsonl").resolve()),
                str((worker_root / "result.json").resolve()),
                str(result_path),
            ],
        }

    def _read_run_binding(self, cycle_id: str) -> Mapping[str, Any]:
        """Read the controller-owned cycle/run binding used to author tasks."""

        path = self._transport_path(cycle_id, "run-binding.json")
        raw = _read_regular(
            path,
            maximum=64 * 1024,
            code="CONTROLLER_RUN_BINDING_INVALID",
        )
        try:
            value = loads_json_strict(raw)
        except CanonicalContractError as exc:
            raise ControllerStateError("CONTROLLER_RUN_BINDING_INVALID") from exc
        expected = {
            "schema_id": _RUN_BINDING_SCHEMA_ID,
            "schema_version": _RUN_BINDING_SCHEMA_VERSION,
            "cycle_id": cycle_id,
            "run_manifest_identity_sha256": self._identity[
                "run_manifest_identity_sha256"
            ],
            "run_id": self._identity["run_id"],
            "theory_manifest_sha256": self._identity["theory_manifest_sha256"],
            "implementation_sha256": self._identity["implementation_sha256"],
            "contract_identity": self._identity["contract_identity"],
            "market_contract_identity": self._identity[
                "market_contract_identity"
            ],
            "experiment_identity": self._identity["experiment_identity"],
        }
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != _RUN_BINDING_FIELDS
            or canonical_bytes(value) + b"\n" != raw
            or dict(value) != expected
        ):
            raise ControllerStateError("CONTROLLER_RUN_BINDING_INVALID")
        return value

    def _worker_result_contract(
        self,
        *,
        cycle_id: str,
        worker_id: str,
        input_refs: list[Mapping[str, Any]],
        not_before_at: str,
        frozen_deadline_at: str,
    ) -> dict[str, Any]:
        """Publish the exact V3.3.2 result envelope the Worker must write."""

        return {
            "schema_id": "agent-trade-emotion.controller-worker-result-contract",
            "schema_version": "1.0.0",
            "envelope_schema_id": "agent_trade_emotion_v331_worker_result",
            "envelope_schema_version": "1.0.0",
            "exact_fields": list(_WORKER_RESULT_FIELDS),
            "fixed_values": {
                "schema_id": "agent_trade_emotion_v331_worker_result",
                "schema_version": "1.0.0",
                "run_id": self._identity["run_id"],
                "cycle_id": cycle_id,
                "worker_id": worker_id,
                "status": "COMPLETED",
            },
            "body_markdown": {
                "type": "string",
                "constraint": "NON_EMPTY_AFTER_STRIP",
            },
            "elapsed_seconds": {
                "type": "FINITE_NUMBER_NOT_BOOLEAN",
                "minimum_inclusive": 0,
                "maximum_inclusive": 86_400,
            },
            "input_refs": {
                "order": "EXACT",
                "cardinality": len(input_refs),
                "required_fields": ["role", "path", "sha256"],
                "optional_fields": ["available_at"],
                "values_from": "task.input_refs",
                "additional_fields_allowed": False,
            },
            "timing": {
                "format": "RFC3339_OFFSET_AWARE",
                "not_before_at": not_before_at,
                "frozen_deadline_at": frozen_deadline_at,
                "constraint": (
                    "not_before_at <= started_at <= completed_at "
                    "< frozen_deadline_at"
                ),
            },
        }

    def materialize_worker_task(self, cycle_id: str, worker_id: str) -> Path:
        """Create the sole production Worker task from sealed controller facts.

        The caller supplies only the cycle and Worker kind.  Run identity,
        request digest, timing and the write boundary are derived from the
        create-once run binding and sealed request.  The controller clock only
        proves that a first materialization is still inside that frozen window.
        """

        cycle_id = _safe_cycle(cycle_id)
        worker_id, spec = _worker(worker_id)
        self._read_run_binding(cycle_id)
        request_path, request_raw, request, packet = self._read_request(
            cycle_id, spec
        )
        worker_root = self._agents_root / f"{cycle_id}--{worker_id}"
        task_path = worker_root / "task.json"
        try:
            task_path.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_MATERIALIZATION_FAILED"
            ) from exc
        else:
            self._validate_task(cycle_id, worker_id, task_path)
            return task_path.absolute()

        _, now = self._now()

        budget = packet.get("time_budget_seconds")
        if worker_id == "capability-assessor-v1":
            not_before = _timestamp(
                packet.get("issued_at"),
                code="CONTROLLER_WORKER_REQUEST_INVALID",
            )
            request_deadline = _timestamp(
                packet.get("assessment_due_at"),
                code="CONTROLLER_WORKER_REQUEST_INVALID",
            )
            if now < not_before or now >= request_deadline:
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            declared_budget = packet.get("time_budget_seconds")
            if type(declared_budget) is not int or declared_budget <= 0:
                raise ControllerStateError("CONTROLLER_WORKER_REQUEST_INVALID")
            candidate_deadline = min(
                now + timedelta(seconds=declared_budget), request_deadline
            )
            budget = int((candidate_deadline - now).total_seconds())
            if budget <= 0:
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            not_before_text = not_before.isoformat()
            created_at_text = now.isoformat()
            deadline_text = (now + timedelta(seconds=budget)).isoformat()
        elif type(budget) is not int or budget <= 0 or budget > 86_400:
            raise ControllerStateError("CONTROLLER_WORKER_REQUEST_INVALID")
        elif worker_id == "review-v1":
            not_before_text = packet.get("review_requested_at")
            request_deadline_text = packet.get("review_due_at")
            not_before = _timestamp(
                not_before_text, code="CONTROLLER_WORKER_REQUEST_INVALID"
            )
            request_deadline = _timestamp(
                request_deadline_text, code="CONTROLLER_WORKER_REQUEST_INVALID"
            )
            if now < not_before or now >= request_deadline:
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            created_at_text = now.isoformat()
            candidate_deadline = min(
                now + timedelta(seconds=budget), request_deadline
            )
            budget = int((candidate_deadline - now).total_seconds())
            if budget <= 0:
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            deadline_text = (now + timedelta(seconds=budget)).isoformat()
        else:
            snapshot = packet.get("input_snapshot")
            if not isinstance(snapshot, Mapping):
                raise ControllerStateError("CONTROLLER_WORKER_REQUEST_INVALID")
            not_before_text = snapshot.get("sealed_at")
            not_before = _timestamp(
                not_before_text, code="CONTROLLER_WORKER_REQUEST_INVALID"
            )
            if now < not_before:
                raise ControllerStateError("CONTROLLER_WORKER_REQUEST_NOT_AVAILABLE")
            hard_stop = (
                budget
                if worker_id == "decision-v1"
                else min(1800, budget)
            )
            candidate_deadline = min(
                now + timedelta(seconds=hard_stop),
                _timestamp(
                    packet.get("decision_deadline_at"),
                    code="CONTROLLER_WORKER_REQUEST_INVALID",
                ),
            )
            if now >= candidate_deadline:
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            budget = int((candidate_deadline - now).total_seconds())
            if budget <= 0:
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            deadline_text = (now + timedelta(seconds=budget)).isoformat()
            created_at_text = now.isoformat()

        ensure_directory_tree(worker_root)
        experiment_identity = self._identity["experiment_identity"]
        experiment_contract_sha256 = _experiment_contract_sha256(
            experiment_identity
        )
        input_refs = [
            {
                "role": spec["request_role"],
                "path": str(request_path),
                "sha256": hashlib.sha256(request_raw).hexdigest(),
                "available_at": str(not_before_text),
            }
        ]
        legacy_v331 = (
            self._identity["contract_identity"]
            == _LEGACY_V331_CONTRACT_IDENTITY
        )
        task = {
            "schema_id": "agent_trade_emotion_v331_worker_task",
            "schema_version": "1.0.0" if legacy_v331 else "2.0.0",
            "worker_contract_identity": spec["contract"],
            "run_id": self._identity["run_id"],
            "cycle_id": cycle_id,
            "worker_id": worker_id,
            "task_kind": spec["task_kind"],
            "stage": spec["stage"],
            "identities": {
                "agent_contract_identity": self._identity["contract_identity"],
                "implementation_sha256": self._identity[
                    "implementation_sha256"
                ],
                "run_manifest_sha256": self._identity[
                    "initial_open_run_manifest_sha256"
                ],
                "theory_manifest_sha256": self._identity[
                    "theory_manifest_sha256"
                ],
                "experiment_contract_sha256": experiment_contract_sha256,
            },
            "experiment_identity": experiment_identity,
            "timing": {
                "created_at": created_at_text,
                "not_before_at": str(not_before_text),
                "frozen_deadline_at": str(deadline_text),
                "hard_stop_seconds": budget,
            },
            "input_refs": input_refs,
            "write_boundary": (
                self._capability_assessor_write_boundary(
                    cycle_id, worker_root
                )
                if worker_id == "capability-assessor-v1"
                else {
                "worker_root": str(worker_root.resolve(strict=True)),
                "events_path": str((worker_root / "events.jsonl").resolve()),
                "result_path": str((worker_root / "result.json").resolve()),
                "worker_may_write_only": ["events.jsonl", "result.json"],
                }
            ),
        }
        if not legacy_v331:
            task["result_contract"] = self._worker_result_contract(
                cycle_id=cycle_id,
                worker_id=worker_id,
                input_refs=input_refs,
                not_before_at=str(not_before_text),
                frozen_deadline_at=str(deadline_text),
            )
        try:
            task_result = write_once_json(task_path, task)
        except (OSError, CanonicalContractError) as exc:
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_MATERIALIZATION_FAILED"
            ) from exc
        if task_result != "CREATED":
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_PREEXISTED_WITHOUT_RECEIPT"
            )
        task_raw = _read_regular(
            task_path,
            maximum=_MAX_TASK_BYTES,
            code="CONTROLLER_WORKER_TASK_INVALID",
        )
        receipt = {
            "schema_id": "agent-trade-emotion.controller-worker-task-receipt",
            "schema_version": "1.0.0",
            "run_id": self._identity["run_id"],
            "cycle_id": cycle_id,
            "worker_id": worker_id,
            "task_sha256": hashlib.sha256(task_raw).hexdigest(),
            "materialized_at": created_at_text,
            "implementation_sha256": self._identity["implementation_sha256"],
        }
        try:
            write_once_json(worker_root / _TASK_RECEIPT_NAME, receipt)
        except (OSError, CanonicalContractError) as exc:
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_RECEIPT_FAILED"
            ) from exc
        # Re-read through the normal admission path. A task is admissible only
        # with the exact controller-owned receipt; an injected task without it
        # is never adopted on a later call.
        self._validate_task(cycle_id, worker_id, task_path)
        return task_path.absolute()

    def _validate_task(
        self, cycle_id: str, worker_id: str, task_path: Path | str
    ) -> dict[str, Any]:
        cycle_id = _safe_cycle(cycle_id)
        worker_id, spec = _worker(worker_id)
        path = self._secure_task(cycle_id, worker_id, task_path)
        raw = _read_regular(path, maximum=_MAX_TASK_BYTES, code="CONTROLLER_WORKER_TASK_INVALID")
        task = _load_relaxed_object(raw, code="CONTROLLER_WORKER_TASK_INVALID")
        legacy_v331 = (
            self._identity["contract_identity"]
            == _LEGACY_V331_CONTRACT_IDENTITY
        )
        required = {
            "schema_id", "schema_version", "worker_contract_identity", "run_id",
            "cycle_id", "worker_id", "task_kind", "stage", "identities",
            "experiment_identity", "timing", "input_refs", "write_boundary",
        }
        if not legacy_v331:
            required.add("result_contract")
        if (
            frozenset(task) != required
            or canonical_bytes(task) + b"\n" != raw
            or task.get("schema_id") != "agent_trade_emotion_v331_worker_task"
            or task.get("schema_version")
            != ("1.0.0" if legacy_v331 else "2.0.0")
            or task.get("worker_contract_identity") != spec["contract"]
            or task.get("run_id") != self._identity["run_id"]
            or task.get("cycle_id") != cycle_id
            or task.get("worker_id") != worker_id
            or task.get("task_kind") != spec["task_kind"]
            or task.get("stage") != spec["stage"]
            or task.get("experiment_identity") != self._identity["experiment_identity"]
        ):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_BINDING_INVALID")
        self._validate_task_receipt(
            cycle_id, worker_id, path, raw, task
        )
        identities = task.get("identities")
        expected = {
            "agent_contract_identity": self._identity["contract_identity"],
            "implementation_sha256": self._identity["implementation_sha256"],
            "run_manifest_sha256": self._identity["initial_open_run_manifest_sha256"],
            "theory_manifest_sha256": self._identity["theory_manifest_sha256"],
        }
        if (
            not isinstance(identities, Mapping)
            or frozenset(identities)
            != frozenset((*expected, "experiment_contract_sha256"))
            or any(
            identities.get(key) != value for key, value in expected.items()
            )
        ):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_IDENTITY_INVALID")
        experiment_contract = _sha256(
            identities.get("experiment_contract_sha256"),
            code="CONTROLLER_WORKER_TASK_IDENTITY_INVALID",
        )
        if experiment_contract != _experiment_contract_sha256(
            self._identity["experiment_identity"]
        ):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_IDENTITY_INVALID")

        timing = task.get("timing")
        if not isinstance(timing, Mapping):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_TIMING_INVALID")
        created = _timestamp(timing.get("created_at"), code="CONTROLLER_WORKER_TASK_TIMING_INVALID")
        not_before = _timestamp(timing.get("not_before_at"), code="CONTROLLER_WORKER_TASK_TIMING_INVALID")
        deadline = _timestamp(timing.get("frozen_deadline_at"), code="CONTROLLER_WORKER_TASK_TIMING_INVALID")
        hard_stop = timing.get("hard_stop_seconds")
        if (
            type(hard_stop) is not int
            or hard_stop <= 0
            or hard_stop > 86_400
            or not_before > created
            or created >= deadline
        ):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_TIMING_INVALID")
        request_path, request_raw, request, packet = self._read_request(
            cycle_id, spec
        )
        if worker_id == "capability-assessor-v1":
            request_due = _timestamp(
                packet.get("assessment_due_at"),
                code="CONTROLLER_WORKER_REQUEST_INVALID",
            )
            if (
                not_before
                != _timestamp(
                    packet.get("issued_at"),
                    code="CONTROLLER_WORKER_REQUEST_INVALID",
                )
                or type(packet.get("time_budget_seconds")) is not int
                or hard_stop > packet.get("time_budget_seconds")
                or deadline != created + timedelta(seconds=hard_stop)
                or deadline > request_due
            ):
                raise ControllerStateError(
                    "CONTROLLER_WORKER_TASK_TIMING_INVALID"
                )
        elif worker_id == "decision-v1":
            if (
                deadline != created + timedelta(seconds=hard_stop)
                or type(packet.get("time_budget_seconds")) is not int
                or hard_stop > packet.get("time_budget_seconds")
                or deadline > _timestamp(packet.get("decision_deadline_at"), code="CONTROLLER_WORKER_REQUEST_INVALID")
            ):
                raise ControllerStateError("CONTROLLER_WORKER_TASK_TIMING_INVALID")
        elif worker_id == "review-v1":
            if (
                type(packet.get("time_budget_seconds")) is not int
                or hard_stop > packet.get("time_budget_seconds")
                or deadline != created + timedelta(seconds=hard_stop)
                or deadline > _timestamp(
                    packet.get("review_due_at"),
                    code="CONTROLLER_WORKER_REQUEST_INVALID",
                )
            ):
                raise ControllerStateError("CONTROLLER_WORKER_TASK_TIMING_INVALID")
        else:
            decision_deadline = _timestamp(
                packet.get("decision_deadline_at"),
                code="CONTROLLER_WORKER_REQUEST_INVALID",
            )
            legacy_v331 = (
                self._identity["contract_identity"]
                == _LEGACY_V331_CONTRACT_IDENTITY
            )
            if legacy_v331:
                # Preserve the frozen V3.3.1 task envelope, where the 1,800s
                # worker hard-stop could be capped by an earlier request
                # deadline without rewriting the declared hard-stop field.
                invalid_daily_timing = hard_stop != 1800 or deadline > decision_deadline
            else:
                invalid_daily_timing = (
                    type(packet.get("time_budget_seconds")) is not int
                    or hard_stop > 1800
                    or hard_stop > packet.get("time_budget_seconds")
                    or deadline != created + timedelta(seconds=hard_stop)
                    or deadline > decision_deadline
                )
            if invalid_daily_timing:
                raise ControllerStateError("CONTROLLER_WORKER_TASK_TIMING_INVALID")

        refs = task.get("input_refs")
        if not isinstance(refs, list):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_INPUT_REF_INVALID")
        matches = [
            item for item in refs
            if isinstance(item, Mapping)
            and item.get("role") == spec["request_role"]
        ]
        if (
            len(matches) != 1
            or matches[0].get("path") != str(request_path)
            or matches[0].get("sha256")
            != hashlib.sha256(request_raw).hexdigest()
            or _timestamp(
                matches[0].get("available_at"),
                code="CONTROLLER_WORKER_TASK_INPUT_REF_INVALID",
            )
            > created
        ):
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_INPUT_REF_INVALID"
            )
        for item in refs:
            if not isinstance(item, Mapping):
                raise ControllerStateError("CONTROLLER_WORKER_TASK_INPUT_REF_INVALID")
            source = Path(str(item.get("path")))
            source_raw = _read_regular(source, maximum=_MAX_OUTPUT_BYTES, code="CONTROLLER_WORKER_TASK_INPUT_REF_INVALID")
            if (
                hashlib.sha256(source_raw).hexdigest() != item.get("sha256")
                or _timestamp(item.get("available_at"), code="CONTROLLER_WORKER_TASK_INPUT_REF_INVALID") > created
            ):
                raise ControllerStateError("CONTROLLER_WORKER_TASK_INPUT_REF_INVALID")
        if not legacy_v331 and task.get(
            "result_contract"
        ) != self._worker_result_contract(
            cycle_id=cycle_id,
            worker_id=worker_id,
            input_refs=refs,
            not_before_at=str(timing["not_before_at"]),
            frozen_deadline_at=str(timing["frozen_deadline_at"]),
        ):
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_RESULT_CONTRACT_INVALID"
            )
        boundary = task.get("write_boundary")
        worker_root = path.parent.resolve(strict=True)
        result_path = worker_root / "result.json"
        if worker_id == "capability-assessor-v1":
            if boundary != self._capability_assessor_write_boundary(
                cycle_id, worker_root
            ):
                raise ControllerStateError(
                    "CONTROLLER_WORKER_TASK_WRITE_BOUNDARY_INVALID"
                )
        elif (
            not isinstance(boundary, Mapping)
            or frozenset(boundary)
            != {"worker_root", "events_path", "result_path", "worker_may_write_only"}
            or boundary.get("worker_root") != str(worker_root)
            or boundary.get("events_path") != str(worker_root / "events.jsonl")
            or boundary.get("result_path") != str(result_path)
            or boundary.get("worker_may_write_only")
            != ["events.jsonl", "result.json"]
        ):
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_WRITE_BOUNDARY_INVALID"
            )
        return {
            "dispatch_key": self._dispatch_key(cycle_id, worker_id),
            "cycle_id": cycle_id,
            "worker_id": worker_id,
            "task_kind": spec["task_kind"],
            "worker_contract_identity": spec["contract"],
            "task_path": str(path),
            "task_sha256": hashlib.sha256(raw).hexdigest(),
            "request_path": str(request_path),
            "request_sha256": hashlib.sha256(request_raw).hexdigest(),
            "request_packet_sha256": request["packet_sha256"],
            "result_path": str(result_path),
            "hard_stop_at": str(timing["frozen_deadline_at"]),
        }

    def _validate_task_receipt(
        self,
        cycle_id: str,
        worker_id: str,
        task_path: Path,
        task_raw: bytes,
        task: Mapping[str, Any],
    ) -> None:
        # V3.3.1's frozen controller contract predates controller-owned task
        # materialization and must remain byte/behavior compatible for its
        # isolated runs.  V3.3.2 is the first contract that requires this
        # anti-injection receipt on every production task.
        if (
            self._identity["contract_identity"]
            == _LEGACY_V331_CONTRACT_IDENTITY
        ):
            return
        receipt_path = task_path.parent / _TASK_RECEIPT_NAME
        receipt_raw = _read_regular(
            receipt_path,
            maximum=64 * 1024,
            code="CONTROLLER_WORKER_TASK_RECEIPT_MISSING_OR_INVALID",
        )
        try:
            receipt = loads_json_strict(receipt_raw)
        except CanonicalContractError as exc:
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_RECEIPT_MISSING_OR_INVALID"
            ) from exc
        expected = {
            "schema_id": "agent-trade-emotion.controller-worker-task-receipt",
            "schema_version": "1.0.0",
            "run_id": self._identity["run_id"],
            "cycle_id": cycle_id,
            "worker_id": worker_id,
            "task_sha256": hashlib.sha256(task_raw).hexdigest(),
            "materialized_at": task.get("timing", {}).get("created_at"),
            "implementation_sha256": self._identity["implementation_sha256"],
        }
        if canonical_bytes(receipt) + b"\n" != receipt_raw or receipt != expected:
            raise ControllerStateError(
                "CONTROLLER_WORKER_TASK_RECEIPT_MISSING_OR_INVALID"
            )

    @staticmethod
    def _verify_inputs(record: Mapping[str, Any]) -> None:
        task_raw = _read_regular(Path(record["task_path"]), maximum=_MAX_TASK_BYTES, code="CONTROLLER_WORKER_TASK_INVALID")
        request_raw = _read_regular(Path(record["request_path"]), maximum=_MAX_REQUEST_BYTES, code="CONTROLLER_WORKER_REQUEST_INVALID")
        if (
            hashlib.sha256(task_raw).hexdigest() != record.get("task_sha256")
            or hashlib.sha256(request_raw).hexdigest() != record.get("request_sha256")
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INPUT_DRIFT")
        task = _load_relaxed_object(
            task_raw, code="CONTROLLER_WORKER_TASK_INVALID"
        )
        refs = task.get("input_refs")
        if not isinstance(refs, list):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INPUT_DRIFT")
        for ref in refs:
            if not isinstance(ref, Mapping):
                raise ControllerStateError(
                    "CONTROLLER_WORKER_DISPATCH_INPUT_DRIFT"
                )
            raw = _read_regular(
                Path(str(ref.get("path"))),
                maximum=_MAX_REQUEST_BYTES,
                code="CONTROLLER_WORKER_DISPATCH_INPUT_DRIFT",
            )
            if hashlib.sha256(raw).hexdigest() != ref.get("sha256"):
                raise ControllerStateError(
                    "CONTROLLER_WORKER_DISPATCH_INPUT_DRIFT"
                )

    def _record(self, state: Mapping[str, Any], cycle_id: str, worker_id: str) -> dict[str, Any]:
        key = self._dispatch_key(_safe_cycle(cycle_id), _worker(worker_id)[0])
        record = state["worker_dispatches"].get(key)
        if not isinstance(record, dict):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_MISSING")
        return record

    def prepare_worker(
        self,
        cycle_id: str,
        worker_id: str,
        task_path: str | Path,
        *,
        next_slot_at: str | None = None,
    ) -> Mapping[str, Any]:
        validated = self._validate_task(cycle_id, worker_id, task_path)
        if next_slot_at is not None:
            _timestamp(next_slot_at, code="CONTROLLER_NEXT_SLOT_INVALID")
            if worker_id != "decision-v1":
                raise ControllerStateError("CONTROLLER_NEXT_SLOT_WORKER_INVALID")
        dispatch_id = "dispatch-" + hashlib.sha256(
            canonical_bytes(
                {
                    "cycle_id": cycle_id,
                    "worker_id": worker_id,
                    "task_sha256": validated["task_sha256"],
                    "run_manifest_identity_sha256": self._identity["run_manifest_identity_sha256"],
                }
            )
        ).hexdigest()
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            existing = state["worker_dispatches"].get(validated["dispatch_key"])
            if existing is not None:
                if existing.get("dispatch_id") != dispatch_id or existing.get("task_sha256") != validated["task_sha256"]:
                    raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_CONFLICT")
                return deepcopy(existing)
            if self._worker_result_present(validated) or self._output_path_present(
                validated
            ):
                raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_ALREADY_PRESENT")
            active = tuple(
                record
                for record in state["worker_dispatches"].values()
                if record.get("status") in _ACTIVE_STATUSES
            )
            # A blind general-capability task must bind a physical assessor
            # before the subject decision is delivered.  The assessor is the
            # sole safe exception to the ordinary single active lane, and may
            # overlap only that one already-dispatched subject decision.
            assessor_overlap = (
                worker_id == "capability-assessor-v1"
                and len(active) == 1
                and active[0].get("worker_id") == "decision-v1"
                and active[0].get("status") == "DISPATCHED"
            )
            if active and not assessor_overlap:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_ALREADY_ACTIVE")
            if len(state["worker_dispatches"]) >= _MAX_DISPATCHES:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_CAPACITY_EXCEEDED")
            now, now_dt = self._now()
            if now_dt >= _timestamp(validated["hard_stop_at"], code="CONTROLLER_WORKER_DISPATCH_INVALID"):
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            record = {
                **validated,
                "dispatch_id": dispatch_id,
                "status": "PREPARED",
                "prepared_at": now,
                "spawn_requested_at": None,
                "spawn_execution_ref": None,
                "spawn_acknowledged_at": None,
                "output_sha256": None,
                "output_at": None,
                "completed_at": None,
                "expiry_reason": None,
                "expired_at": None,
            }
            revision = state["revision"]
            state["worker_dispatches"][validated["dispatch_key"]] = record
            self._schedule_locked(
                state,
                self._event_id(cycle_id, worker_id),
                "WORKER_HARD_STOP",
                validated["hard_stop_at"],
                cycle_id,
            )
            if next_slot_at is not None:
                self._schedule_locked(state, f"next-slot:{cycle_id}", "NEXT_SLOT", next_slot_at, cycle_id)
            state["revision"] = revision + 1
            self._save_locked(state, revision)
            return deepcopy(record)

    def mark_spawn_requested(
        self, cycle_id: str, worker_id: str, dispatch_id: str
    ) -> Mapping[str, Any]:
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            record = self._record(state, cycle_id, worker_id)
            if record.get("dispatch_id") != dispatch_id:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_MISSING")
            if record["status"] == "SPAWN_REQUESTED":
                return deepcopy(record)
            if record["status"] != "PREPARED":
                raise ControllerStateError("CONTROLLER_WORKER_SPAWN_STAGE_INVALID")
            self._verify_inputs(record)
            if self._worker_result_present(record) or self._output_path_present(record):
                raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_ALREADY_PRESENT")
            now, now_dt = self._now()
            if now_dt >= _timestamp(record["hard_stop_at"], code="CONTROLLER_WORKER_DISPATCH_INVALID"):
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
            revision = state["revision"]
            record["status"] = "SPAWN_REQUESTED"
            record["spawn_requested_at"] = now
            state["revision"] = revision + 1
            self._save_locked(state, revision)
            return deepcopy(record)

    def _validate_result_envelope(
        self, record: Mapping[str, Any]
    ) -> tuple[bytes, Mapping[str, Any], str]:
        raw = _read_regular(Path(record["result_path"]), maximum=_MAX_OUTPUT_BYTES, code="CONTROLLER_WORKER_RESULT_INVALID")
        result = _load_relaxed_object(raw, code="CONTROLLER_WORKER_RESULT_INVALID")
        task = _load_relaxed_object(
            _read_regular(
                Path(record["task_path"]),
                maximum=_MAX_TASK_BYTES,
                code="CONTROLLER_WORKER_TASK_INVALID",
            ),
            code="CONTROLLER_WORKER_TASK_INVALID",
        )
        body = result.get("body_markdown")
        if (
            frozenset(result)
            != frozenset(_WORKER_RESULT_FIELDS)
            or result.get("schema_id") != "agent_trade_emotion_v331_worker_result"
            or result.get("schema_version") != "1.0.0"
            or result.get("run_id") != self._identity["run_id"]
            or result.get("cycle_id") != record.get("cycle_id")
            or result.get("worker_id") != record.get("worker_id")
            or result.get("status") != "COMPLETED"
            or not isinstance(body, str)
            or not body.strip()
            or not self._result_input_refs_match_task(
                result.get("input_refs"), task.get("input_refs")
            )
        ):
            raise ControllerStateError("CONTROLLER_WORKER_RESULT_INVALID")
        elapsed = result.get("elapsed_seconds")
        if (
            type(elapsed) not in {int, float}
            or isinstance(elapsed, bool)
            or not (0 <= float(elapsed) <= 86_400)
        ):
            raise ControllerStateError("CONTROLLER_WORKER_RESULT_INVALID")
        started = _timestamp(result.get("started_at"), code="CONTROLLER_WORKER_RESULT_INVALID")
        completed = _timestamp(result.get("completed_at"), code="CONTROLLER_WORKER_RESULT_INVALID")
        deadline = _timestamp(record.get("hard_stop_at"), code="CONTROLLER_WORKER_DISPATCH_INVALID")
        timing = task.get("timing")
        if not isinstance(timing, Mapping):
            raise ControllerStateError("CONTROLLER_WORKER_TASK_INVALID")
        not_before = _timestamp(
            timing.get("not_before_at"), code="CONTROLLER_WORKER_TASK_INVALID"
        )
        if started < not_before or started > completed or completed >= deadline:
            raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
        return raw, result, str(result["completed_at"])

    def _result_input_refs_match_task(
        self, result_refs: object, task_refs: object
    ) -> bool:
        """Bind Worker refs without requiring system-owned PIT metadata echoes."""

        if (
            not isinstance(result_refs, list)
            or not isinstance(task_refs, list)
            or len(result_refs) != len(task_refs)
        ):
            return False
        for result_ref, task_ref in zip(result_refs, task_refs, strict=True):
            if not isinstance(result_ref, Mapping) or not isinstance(task_ref, Mapping):
                return False
            required = {"role", "path", "sha256"}
            if not required.issubset(result_ref) or not required.issubset(task_ref):
                return False
            if (
                self._identity["contract_identity"]
                != _LEGACY_V331_CONTRACT_IDENTITY
                and not frozenset(result_ref).issubset(
                    required | {"available_at"}
                )
            ):
                return False
            if any(
                result_ref.get(field) != task_ref.get(field)
                for field in ("role", "path", "sha256")
            ):
                return False
            if (
                "available_at" in result_ref
                and result_ref["available_at"] != task_ref.get("available_at")
            ):
                return False
        return True

    def admit_worker_result_for_delivery(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        """Read-only admission of one Worker result before immutable delivery.

        The returned body is the already-validated byte source for the
        application delivery adapter.  No delivery or controller state is
        written by this method.
        """

        cycle_id = _safe_cycle(cycle_id)
        worker_id, _ = _worker(worker_id)
        if worker_id not in _DELIVERY_WORKERS:
            raise ControllerStateError(
                "CONTROLLER_WORKER_RESULT_DELIVERY_NOT_APPLICABLE"
            )
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            record = self._record(state, cycle_id, worker_id)
            if record.get("status") != "DISPATCHED":
                raise ControllerStateError(
                    "CONTROLLER_WORKER_RESULT_ADMISSION_STAGE_INVALID"
                )
            self._verify_inputs(record)
            if self._output_path_present(record):
                raise ControllerStateError(
                    "CONTROLLER_WORKER_OUTPUT_ALREADY_PRESENT"
                )
            raw, result, completed_at = self._validate_result_envelope(record)
            admitted_at, admitted_at_dt = self._now()
            if _timestamp(
                completed_at, code="CONTROLLER_WORKER_RESULT_INVALID"
            ) > admitted_at_dt:
                raise ControllerStateError(
                    "CONTROLLER_WORKER_RESULT_COMPLETED_IN_FUTURE"
                )
            body = str(result["body_markdown"])
            body_raw = body.encode("utf-8", errors="strict")
            binding = {
                "schema_id": (
                    "agent-trade-emotion.controller-worker-result-admission"
                ),
                "schema_version": "1.0.0",
                "run_id": self._identity["run_id"],
                "cycle_id": cycle_id,
                "worker_id": worker_id,
                "dispatch_id": record["dispatch_id"],
                "task_sha256": record["task_sha256"],
                "request_sha256": record["request_sha256"],
                "request_packet_sha256": record["request_packet_sha256"],
                "result_sha256": hashlib.sha256(raw).hexdigest(),
                "body_sha256": hashlib.sha256(body_raw).hexdigest(),
                "body_size_bytes": len(body_raw),
                "input_refs_sha256": canonical_digest(result["input_refs"]),
                "result_completed_at": completed_at,
                "admitted_at": admitted_at,
                "hard_stop_at": record["hard_stop_at"],
            }
            return {
                **binding,
                "admission_sha256": canonical_digest(binding),
                "body_markdown": body,
            }

    def _validate_reconciled_output(
        self, record: Mapping[str, Any]
    ) -> tuple[bytes, str, str]:
        """Bind completion or a lost spawn ACK to one result and delivery."""

        result_raw, result, result_completed_at = self._validate_result_envelope(
            record
        )
        if record["worker_id"] == "daily-deep-v1":
            return (
                result_raw,
                hashlib.sha256(result_raw).hexdigest(),
                result_completed_at,
            )
        if record["worker_id"] == "capability-assessor-v1":
            output_raw, output_sha256, output_at = (
                self._validate_capability_assessor_output(record)
            )
            if result_completed_at != output_at:
                raise ControllerStateError(
                    "CONTROLLER_CAPABILITY_ASSESSOR_RESULT_MISMATCH"
                )
            return output_raw, output_sha256, output_at
        output = self._output(record)
        raw, _, _ = output
        try:
            delivery = loads_json_strict(raw)
        except CanonicalContractError as exc:
            raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_INVALID") from exc
        text_field = (
            "decision_text"
            if record["worker_id"] == "decision-v1"
            else "review_text"
        )
        if result.get("body_markdown") != delivery.get(text_field):
            raise ControllerStateError("CONTROLLER_WORKER_RESULT_DELIVERY_MISMATCH")
        return output

    def _validate_capability_assessor_output(
        self, record: Mapping[str, Any]
    ) -> tuple[bytes, str, str]:
        cycle_id = str(record["cycle_id"])
        mailbox = LocalCapabilityAssessorMailbox(self._root)
        try:
            request = mailbox.load_request(cycle_id)
            result, raw = mailbox.load_result(cycle_id)
        except RuntimeError as exc:
            raise ControllerStateError(
                "CONTROLLER_CAPABILITY_ASSESSOR_OUTPUT_INVALID"
            ) from exc
        packet = request["packet"]
        task_path = Path(str(packet.get("capability_task_path"))).absolute()
        try:
            resolved_task = task_path.resolve(strict=True)
            resolved_task.relative_to(self._root.resolve(strict=True))
            entry_raw = _read_regular(
                resolved_task,
                maximum=_MAX_OUTPUT_BYTES,
                code="CONTROLLER_CAPABILITY_ASSESSOR_TASK_INVALID",
            )
            entry = loads_json_strict(entry_raw)
            document = entry.get("document")
        except (OSError, ValueError, CanonicalContractError) as exc:
            raise ControllerStateError(
                "CONTROLLER_CAPABILITY_ASSESSOR_TASK_INVALID"
            ) from exc
        if (
            canonical_bytes(entry) + b"\n" != entry_raw
            or not isinstance(document, Mapping)
            or entry.get("document_sha256") != canonical_digest(document)
        ):
            raise ControllerStateError(
                "CONTROLLER_CAPABILITY_ASSESSOR_TASK_INVALID"
            )
        basis = dict(document)
        basis.pop("assessor_id", None)
        basis.pop("created_at", None)
        completed_at = result.get("completed_at")
        if (
            result.get("capability_id") != packet.get("capability_id")
            or result.get("task_id") != packet.get("task_id")
            or result.get("task_sha256") != entry.get("document_sha256")
            or document.get("task_id") != packet.get("task_id")
            or document.get("capability_id") != packet.get("capability_id")
            or document.get("policy_sha256") != packet.get("policy_sha256")
            or document.get("subject_agent_id")
            != packet.get("subject_agent_id")
            or document.get("assessor_id")
            != record.get("spawn_execution_ref")
            or result.get("assessor_execution_ref")
            != record.get("spawn_execution_ref")
            or canonical_digest(basis) != packet.get("task_basis_sha256")
            or basis != packet.get("task_basis")
            or _timestamp(
                completed_at,
                code="CONTROLLER_CAPABILITY_ASSESSOR_OUTPUT_INVALID",
            )
            >= _timestamp(
                record.get("hard_stop_at"),
                code="CONTROLLER_WORKER_DISPATCH_INVALID",
            )
        ):
            raise ControllerStateError(
                "CONTROLLER_CAPABILITY_ASSESSOR_OUTPUT_BINDING_INVALID"
            )
        return raw, hashlib.sha256(raw).hexdigest(), str(completed_at)

    def acknowledge_spawn(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        execution_ref: str,
    ) -> Mapping[str, Any]:
        execution_ref = _bounded_identity(execution_ref, code="CONTROLLER_WORKER_EXECUTION_REF_INVALID")
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            record = self._record(state, cycle_id, worker_id)
            if record.get("dispatch_id") != dispatch_id:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_MISSING")
            if record["status"] == "DISPATCHED":
                if record.get("spawn_execution_ref") != execution_ref:
                    raise ControllerStateError("CONTROLLER_WORKER_SPAWN_ACK_CONFLICT")
                return deepcopy(record)
            if record["status"] != "SPAWN_REQUESTED":
                raise ControllerStateError("CONTROLLER_WORKER_SPAWN_ACK_STAGE_INVALID")
            if worker_id == "capability-assessor-v1":
                _, _, _, packet = self._read_request(
                    cycle_id, _WORKERS[worker_id]
                )
                if packet.get("subject_agent_id") == execution_ref:
                    raise ControllerStateError(
                        "CONTROLLER_CAPABILITY_ASSESSOR_NOT_INDEPENDENT"
                    )
            self._verify_inputs(record)
            now, now_dt = self._now()
            deadline = _timestamp(record["hard_stop_at"], code="CONTROLLER_WORKER_DISPATCH_INVALID")
            if now_dt >= deadline:
                # A lost scheduler ACK may be reconciled after the deadline only
                # from a bounded, timely Worker result in its frozen write root.
                self._validate_reconciled_output(record)
            revision = state["revision"]
            record["status"] = "DISPATCHED"
            record["spawn_execution_ref"] = execution_ref
            record["spawn_acknowledged_at"] = now
            state["revision"] = revision + 1
            self._save_locked(state, revision)
            return deepcopy(record)

    def _output(self, record: Mapping[str, Any]) -> tuple[bytes, str, str]:
        worker_id, spec = _worker(record.get("worker_id"))
        if worker_id == "daily-deep-v1":
            raw, _, output_at = self._validate_result_envelope(record)
            return raw, hashlib.sha256(raw).hexdigest(), output_at
        if worker_id == "capability-assessor-v1":
            return self._validate_capability_assessor_output(record)
        path = self._transport_path(record["cycle_id"], spec["output_name"])
        raw = _read_regular(path, maximum=_MAX_OUTPUT_BYTES, code="CONTROLLER_WORKER_OUTPUT_INVALID")
        try:
            value = loads_json_strict(raw)
        except CanonicalContractError as exc:
            raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_INVALID") from exc
        if canonical_bytes(value) + b"\n" != raw:
            raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_INVALID")
        _, request_raw, request, packet = self._read_request(
            record["cycle_id"], spec
        )
        if (
            hashlib.sha256(request_raw).hexdigest() != record.get("request_sha256")
            or request.get("packet_sha256") != record.get("request_packet_sha256")
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INPUT_DRIFT")
        output_at = value.get(spec["completion_field"])
        text_field = "decision_text" if worker_id == "decision-v1" else "review_text"
        size_field = "decision_size_bytes" if worker_id == "decision-v1" else "review_size_bytes"
        sha_field = "decision_sha256" if worker_id == "decision-v1" else "review_sha256"
        expected_fields = {
            "schema_id",
            "schema_version",
            "cycle_id",
            "request_sha256",
            "theory_identity",
            "delivered_at",
            "media_type",
            "encoding",
            size_field,
            sha_field,
            text_field,
        }
        if worker_id == "review-v1":
            expected_fields.update({"behavior_plan_sha256", "outcome_sha256"})
        text_value = value.get(text_field)
        try:
            text_raw = text_value.encode("utf-8", errors="strict")
        except (AttributeError, UnicodeEncodeError) as exc:
            raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_INVALID") from exc
        if (
            frozenset(value) != expected_fields
            or value.get("schema_id") != spec["output_schema"]
            or value.get("schema_version") != "1.0.0"
            or value.get("cycle_id") != record.get("cycle_id")
            or value.get("request_sha256") != record.get("request_packet_sha256")
            or value.get("theory_identity") != packet.get("theory_identity")
            or value.get("encoding") != "UTF-8"
            or type(value.get("media_type")) is not str
            or not value["media_type"]
            or not text_value.strip()
            or b"\x00" in text_raw
            or value.get(size_field) != len(text_raw)
            or value.get(sha_field) != hashlib.sha256(text_raw).hexdigest()
        ):
            raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_INVALID")
        if worker_id == "review-v1" and (
            not isinstance(packet.get("behavior_plan_ref"), Mapping)
            or not isinstance(packet.get("outcome_ref"), Mapping)
            or value.get("behavior_plan_sha256")
            != packet["behavior_plan_ref"].get("sha256")
            or value.get("outcome_sha256") != packet["outcome_ref"].get("sha256")
        ):
            raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_INVALID")
        if _timestamp(
            output_at, code="CONTROLLER_WORKER_OUTPUT_INVALID"
        ) >= _timestamp(
            record.get("hard_stop_at"),
            code="CONTROLLER_WORKER_DISPATCH_INVALID",
        ):
            raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_EXPIRED")
        return raw, hashlib.sha256(raw).hexdigest(), str(output_at)

    def _output_path_present(self, record: Mapping[str, Any]) -> bool:
        worker_id, spec = _worker(record.get("worker_id"))
        if worker_id == "capability-assessor-v1":
            return all(
                self._regular_path_present(path)
                for path in (
                    Path(record["result_path"]),
                    LocalCapabilityAssessorMailbox(self._root).result_path(
                        str(record["cycle_id"])
                    ),
                )
            )
        path = (
            Path(record["result_path"])
            if worker_id == "daily-deep-v1"
            else self._transport_path(record["cycle_id"], spec["output_name"])
        )
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_PRESENCE_UNAVAILABLE") from exc
        return True

    @staticmethod
    def _regular_path_present(path: Path) -> bool:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ControllerStateError(
                "CONTROLLER_WORKER_OUTPUT_PRESENCE_UNAVAILABLE"
            ) from exc
        return stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(
            metadata.st_mode
        )

    @staticmethod
    def _worker_result_present(record: Mapping[str, Any]) -> bool:
        path = Path(record["result_path"])
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ControllerStateError(
                "CONTROLLER_WORKER_RESULT_PRESENCE_UNAVAILABLE"
            ) from exc
        return True

    def complete_worker(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        output_sha256: str,
    ) -> Mapping[str, Any]:
        output_sha256 = _sha256(output_sha256, code="CONTROLLER_WORKER_OUTPUT_SHA_INVALID")
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            record = self._record(state, cycle_id, worker_id)
            if record.get("dispatch_id") != dispatch_id:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_MISSING")
            self._verify_inputs(record)
            output = (
                self._output(record)
                if worker_id == "daily-deep-v1"
                else self._validate_reconciled_output(record)
            )
            raw, observed_sha, output_at = output
            if observed_sha != output_sha256 or hashlib.sha256(raw).hexdigest() != output_sha256:
                raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_SHA_MISMATCH")
            if record["status"] == "COMPLETED":
                if record.get("output_sha256") != output_sha256:
                    raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_CONFLICT")
                return deepcopy(record)
            if record["status"] != "DISPATCHED":
                raise ControllerStateError("CONTROLLER_WORKER_COMPLETION_STAGE_INVALID")
            now, _ = self._now()
            revision = state["revision"]
            record["status"] = "COMPLETED"
            record["output_sha256"] = output_sha256
            record["output_at"] = output_at
            record["completed_at"] = now
            self._resolve_locked(state, self._event_id(cycle_id, worker_id))
            state["revision"] = revision + 1
            self._save_locked(state, revision)
            return deepcopy(record)

    def recover_worker(self, cycle_id: str, worker_id: str) -> Mapping[str, Any]:
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            record = self._record(state, cycle_id, worker_id)
            if record["status"] in _ACTIVE_STATUSES:
                self._verify_inputs(record)
            _, now = self._now()
            expired = now >= _timestamp(record["hard_stop_at"], code="CONTROLLER_WORKER_DISPATCH_INVALID")
            status = record["status"]
            if status == "PREPARED":
                action = "EXPIRE" if expired else "RECOVER_PREPARED"
            elif status == "SPAWN_REQUESTED":
                if not expired:
                    action = "RECONCILE_SPAWN"
                elif self._worker_result_present(record):
                    self._validate_reconciled_output(record)
                    action = "RECONCILE_SPAWN"
                else:
                    action = "EXPIRE"
            elif status == "DISPATCHED":
                if not self._output_path_present(record):
                    action = "EXPIRE" if expired else "WAIT_FOR_OUTPUT"
                else:
                    output = (
                        self._validate_reconciled_output(record)
                        if worker_id == "capability-assessor-v1"
                        else self._output(record)
                    )
                    _, digest, _ = output
                    action = "COMPLETE_OUTPUT"
            elif status == "COMPLETED":
                output = (
                    self._validate_reconciled_output(record)
                    if worker_id == "capability-assessor-v1"
                    else self._output(record)
                )
                _, digest, _ = output
                if digest != record.get("output_sha256"):
                    raise ControllerStateError("CONTROLLER_WORKER_OUTPUT_DRIFT")
                action = "COMPLETED"
            elif status == "EXPIRED":
                action = "EXPIRED"
            else:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_INVALID")
            return {**deepcopy(record), "recovery_action": action}

    def _request_only_decision_deadline(self, cycle_id: str) -> Mapping[str, Any]:
        _, raw, request, packet = self._read_request(cycle_id, _WORKERS["decision-v1"])
        snapshot = packet.get("input_snapshot")
        budget = packet.get("time_budget_seconds")
        if not isinstance(snapshot, Mapping) or type(budget) is not int or budget <= 0:
            raise ControllerStateError("CONTROLLER_WORKER_REQUEST_INVALID")
        sealed = _timestamp(snapshot.get("sealed_at"), code="CONTROLLER_WORKER_REQUEST_INVALID")
        published = sealed + timedelta(seconds=budget)
        outcome = _timestamp(packet.get("decision_deadline_at"), code="CONTROLLER_WORKER_REQUEST_INVALID")
        deadline = min(published, outcome).isoformat()
        return {
            "cycle_id": cycle_id,
            "worker_id": "decision-v1",
            "dispatch_id": None,
            "status": "REQUEST_ONLY",
            "hard_stop_at": deadline,
            "request_sha256": hashlib.sha256(raw).hexdigest(),
            "request_packet_sha256": request["packet_sha256"],
        }

    def decision_deadline(self, cycle_id: str) -> Mapping[str, Any]:
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            try:
                record = self._record(state, cycle_id, "decision-v1")
            except ControllerStateError as exc:
                if str(exc) != "CONTROLLER_WORKER_DISPATCH_MISSING":
                    raise
                return self._request_only_decision_deadline(cycle_id)
            return deepcopy(record)

    def require_worker_deadline_expired(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        worker_id, _ = _worker(worker_id)
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            try:
                record = self._record(state, cycle_id, worker_id)
            except ControllerStateError as exc:
                if worker_id != "decision-v1" or str(exc) != "CONTROLLER_WORKER_DISPATCH_MISSING":
                    raise
                record = dict(self._request_only_decision_deadline(cycle_id))
            if record.get("status") == "COMPLETED":
                raise ControllerStateError("CONTROLLER_WORKER_ALREADY_COMPLETED")
            _, now = self._now()
            if now < _timestamp(record.get("hard_stop_at"), code="CONTROLLER_WORKER_DISPATCH_INVALID"):
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_NOT_EXPIRED")
            return deepcopy(record)

    def mark_worker_expired(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        reason_code: str,
    ) -> Mapping[str, Any]:
        worker_id, spec = _worker(worker_id)
        if type(reason_code) is not str or reason_code != spec["expiry_reason"]:
            raise ControllerStateError("CONTROLLER_WORKER_EXPIRY_REASON_INVALID")
        with exclusive_lock_file(self._lock_path):
            state = self._load_locked()
            record = self._record(state, cycle_id, worker_id)
            if record.get("dispatch_id") != dispatch_id:
                raise ControllerStateError("CONTROLLER_WORKER_DISPATCH_MISSING")
            if record["status"] == "EXPIRED":
                return deepcopy(record)
            if record["status"] not in _ACTIVE_STATUSES:
                raise ControllerStateError("CONTROLLER_WORKER_EXPIRY_STAGE_INVALID")
            now, now_dt = self._now()
            if now_dt < _timestamp(record["hard_stop_at"], code="CONTROLLER_WORKER_DISPATCH_INVALID"):
                raise ControllerStateError("CONTROLLER_WORKER_DEADLINE_NOT_EXPIRED")
            revision = state["revision"]
            record["status"] = "EXPIRED"
            record["expiry_reason"] = reason_code
            record["expired_at"] = now
            self._resolve_locked(state, self._event_id(cycle_id, worker_id))
            state["revision"] = revision + 1
            self._save_locked(state, revision)
            return deepcopy(record)

    # Compatibility names are thin delegates into the only generic owner.
    def prepare_agent_decision(self, cycle_id: str, task_path: str | Path, *, next_slot_at: str | None = None) -> Mapping[str, Any]:
        return self.prepare_worker(cycle_id, "decision-v1", task_path, next_slot_at=next_slot_at)

    def complete_agent_decision(self, cycle_id: str, dispatch_id: str, delivery_sha256: str) -> Mapping[str, Any]:
        return self.complete_worker(cycle_id, "decision-v1", dispatch_id, delivery_sha256)

    def recover_agent_decision(self, cycle_id: str) -> Mapping[str, Any]:
        return self.recover_worker(cycle_id, "decision-v1")

    def require_agent_decision_deadline_expired(self, cycle_id: str) -> Mapping[str, Any]:
        return self.require_worker_deadline_expired(cycle_id, "decision-v1")

    def mark_agent_decision_expired(self, cycle_id: str, dispatch_id: str, reason_code: str) -> Mapping[str, Any]:
        return self.mark_worker_expired(cycle_id, "decision-v1", dispatch_id, reason_code)


__all__ = ["ControllerStateError", "FileControllerState"]
