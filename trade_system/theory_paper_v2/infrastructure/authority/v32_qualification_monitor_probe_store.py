"""Write-once store and one-boundary runner for the qualification monitor probe."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import threading
from typing import Any, Callable, Mapping

from ...application.v32_outcome_tick_composition import (
    V32OutcomeTickCompositionError,
    parse_v32_public_mark_raw_v1,
)
from ...domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
)
from ...v32_durable_json import (
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ...domain.v32_outcome_tick import (
    TRANSPORT_COVERAGE_FAILURE_CODES,
    V32PublicTransportUnavailableError,
)
from ...domain.v32_qualification_monitor_probe import (
    ATTEMPT_DIGEST_FIELD,
    CAPTURE_DIGEST_FIELD,
    COMPLETION_DIGEST_FIELD,
    FAILURE_DIGEST_FIELD,
    OBSERVATION_DIGEST_FIELD,
    SCHEDULE_DIGEST_FIELD,
    build_v32_qualification_monitor_probe_attempt_v1,
    build_v32_qualification_monitor_probe_capture_v1,
    build_v32_qualification_monitor_probe_completion_v1,
    build_v32_qualification_monitor_probe_failure_v1,
    build_v32_qualification_monitor_probe_observation_v1,
    decode_v32_qualification_monitor_probe_raw_v1,
    verify_v32_qualification_monitor_probe_attempt_v1,
    verify_v32_qualification_monitor_probe_capture_v1,
    verify_v32_qualification_monitor_probe_completion_v1,
    verify_v32_qualification_monitor_probe_failure_v1,
    verify_v32_qualification_monitor_probe_observation_v1,
    verify_v32_qualification_monitor_probe_v1,
)


class V32QualificationMonitorProbeStoreError(ValueError):
    """The dedicated qualification monitor store failed closed."""


STORE_ROOT = "v32-qualification-monitor-probe-v1"
_FILES = {
    "schedule": ("schedule.json", SCHEDULE_DIGEST_FIELD),
    "attempt": ("attempt.json", ATTEMPT_DIGEST_FIELD),
    "capture": ("capture.json", CAPTURE_DIGEST_FIELD),
    "observation": ("observation.json", OBSERVATION_DIGEST_FIELD),
    "completion": ("completion.json", COMPLETION_DIGEST_FIELD),
    "failure": ("failure.json", FAILURE_DIGEST_FIELD),
}
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_EXPECTED_OKX_MARK_URL = (
    "https://openapi.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32QualificationMonitorProbeStoreError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32QualificationMonitorProbeStoreError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32QualificationMonitorProbeStoreError(code)
    return parsed.astimezone(UTC)


def _clock(clock: Callable[[], str]) -> str:
    try:
        value = clock()
    except Exception as exc:
        raise V32QualificationMonitorProbeStoreError("V32_PROBE_CLOCK_FAILED") from exc
    _moment(value, "V32_PROBE_CLOCK_INVALID")
    return value


class LocalV32QualificationMonitorProbeStore:
    """Own the sole schedule, attempt, raw capture, observation and completion."""

    def __init__(
        self,
        root: Path,
        *,
        capture_port: Any,
        clock: Callable[[], str],
    ) -> None:
        candidate = Path(root)
        ensure_directory_tree(candidate)
        if candidate.is_symlink() or not candidate.is_dir():
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_STORE_INVALID")
        self.root = candidate.resolve(strict=True)
        self.store = self.root / STORE_ROOT
        if self.store.exists() and self.store.is_symlink():
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_STORE_INVALID")
        ensure_directory_tree(self.store)
        if not callable(getattr(capture_port, "capture_public_mark", None)):
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_CAPTURE_PORT_INVALID")
        if not callable(clock):
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_CLOCK_INVALID")
        self.capture_port = capture_port
        self.clock = clock
        self.lock_path = self.store / "store.lock"

    @contextmanager
    def _lock(self):
        key = str(self.lock_path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(self.lock_path):
                yield

    def _path(self, role: str) -> Path:
        if role not in _FILES:
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_ROLE_INVALID")
        path = self.store / _FILES[role][0]
        if path.exists() and path.is_symlink():
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_STORE_INVALID")
        return path

    def _read(self, role: str) -> dict[str, Any] | None:
        path = self._path(role)
        if not path.exists():
            return None
        document = load_json_strict(path)
        if path.read_bytes() != canonical_bytes(document) + b"\n":
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_BYTES_INVALID")
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32QualificationMonitorProbeStoreError(
                "V32_PROBE_BYTES_INVALID"
            ) from exc
        return document

    def _write(self, role: str, document: Mapping[str, Any]) -> None:
        try:
            write_once_json(self._path(role), document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32QualificationMonitorProbeStoreError(
                "V32_PROBE_WRITE_CONFLICT"
            ) from exc

    def initialize(self, schedule: Mapping[str, Any]) -> Mapping[str, Any]:
        verify_v32_qualification_monitor_probe_v1(schedule)
        with self._lock():
            existing = self._read("schedule")
            if existing is None:
                self._write("schedule", schedule)
                return {
                    "status": "PENDING",
                    "boundary_kind": "QUALIFICATION_MONITOR_PROBE_SCHEDULED",
                    "state_changed": True,
                    "observed_state_digest": schedule[SCHEDULE_DIGEST_FIELD],
                }
            verify_v32_qualification_monitor_probe_v1(existing)
            if existing != dict(schedule):
                raise V32QualificationMonitorProbeStoreError("V32_PROBE_IDENTITY_DRIFT")
            return {
                "status": "PENDING",
                "boundary_kind": "QUALIFICATION_MONITOR_PROBE_ALREADY_SCHEDULED",
                "state_changed": False,
                "observed_state_digest": existing[SCHEDULE_DIGEST_FIELD],
            }

    def _load_prefix_unlocked(self) -> dict[str, Any]:
        schedule = self._read("schedule")
        if schedule is None:
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_SCHEDULE_MISSING")
        verify_v32_qualification_monitor_probe_v1(schedule)
        attempt = self._read("attempt")
        capture = self._read("capture")
        observation = self._read("observation")
        completion = self._read("completion")
        failure = self._read("failure")
        if attempt is not None:
            verify_v32_qualification_monitor_probe_attempt_v1(attempt, schedule=schedule)
        if capture is not None:
            if attempt is None:
                raise V32QualificationMonitorProbeStoreError("V32_PROBE_PREFIX_INVALID")
            verify_v32_qualification_monitor_probe_capture_v1(
                capture, attempt=attempt, schedule=schedule
            )
        if observation is not None:
            if attempt is None or capture is None:
                raise V32QualificationMonitorProbeStoreError("V32_PROBE_PREFIX_INVALID")
            verify_v32_qualification_monitor_probe_observation_v1(
                observation, schedule=schedule, attempt=attempt, capture=capture
            )
        if completion is not None:
            if attempt is None or capture is None or observation is None or failure is not None:
                raise V32QualificationMonitorProbeStoreError("V32_PROBE_PREFIX_INVALID")
            verify_v32_qualification_monitor_probe_completion_v1(
                completion,
                schedule=schedule,
                attempt=attempt,
                capture=capture,
                observation=observation,
            )
        if failure is not None:
            if completion is not None:
                raise V32QualificationMonitorProbeStoreError("V32_PROBE_PREFIX_INVALID")
            verify_v32_qualification_monitor_probe_failure_v1(
                failure,
                schedule=schedule,
                attempt=attempt,
                capture=capture,
            )
        return {
            "schedule": schedule,
            "attempt": attempt,
            "capture": capture,
            "observation": observation,
            "completion": completion,
            "failure": failure,
        }

    def load_prefix(self) -> dict[str, Any]:
        with self._lock():
            return self._load_prefix_unlocked()

    def schedule_binding_v1(self) -> Mapping[str, str] | None:
        """Replay and bind the sole schedule without advancing the probe."""

        with self._lock():
            schedule = self._read("schedule")
            if schedule is None:
                return None
            verify_v32_qualification_monitor_probe_v1(schedule)
            path = self._path("schedule")
            payload = canonical_bytes(schedule) + b"\n"
            if path.read_bytes() != payload:
                raise V32QualificationMonitorProbeStoreError(
                    "V32_PROBE_BYTES_INVALID"
                )
            return {
                "relative_ref": f"{STORE_ROOT}/schedule.json",
                "schema_id": str(schedule["schema_id"]),
                "digest_field": SCHEDULE_DIGEST_FIELD,
                "semantic_digest": str(schedule[SCHEDULE_DIGEST_FIELD]),
                "physical_sha256": hashlib.sha256(payload).hexdigest(),
            }

    def advance_once(self) -> Mapping[str, Any]:
        """Advance at most one write-once probe boundary."""

        with self._lock():
            prefix = self._load_prefix_unlocked()
            schedule = prefix["schedule"]
            if prefix["failure"] is not None:
                return {
                    "status": "FAILED_CLOSED",
                    "boundary_kind": "NO_ADVANCE_TERMINAL_FAILURE",
                    "state_changed": False,
                    "observed_state_digest": prefix["failure"][FAILURE_DIGEST_FIELD],
                    "failure": prefix["failure"],
                }
            if prefix["completion"] is not None:
                return {
                    "status": "COMPLETE",
                    "boundary_kind": "NO_ADVANCE_TERMINAL",
                    "state_changed": False,
                    "observed_state_digest": prefix["completion"][COMPLETION_DIGEST_FIELD],
                    "completion": prefix["completion"],
                }
            if prefix["attempt"] is None:
                now = _clock(self.clock)
                if _moment(now, "V32_PROBE_CLOCK_INVALID") < _moment(
                    schedule["due_at"], "V32_PROBE_DUE_INVALID"
                ):
                    return {
                        "status": "NOT_DUE",
                        "boundary_kind": "NO_ADVANCE_NOT_DUE",
                        "state_changed": False,
                        "observed_state_digest": schedule[SCHEDULE_DIGEST_FIELD],
                        "due_at": schedule["due_at"],
                    }
                if _moment(now, "V32_PROBE_CLOCK_INVALID") > _moment(
                    schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID"
                ):
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        failed_at=now,
                        failure_code="QUALIFICATION_MONITOR_PROBE_WINDOW_EXPIRED",
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": "QUALIFICATION_MONITOR_PROBE_WINDOW_EXPIRED",
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                attempt = build_v32_qualification_monitor_probe_attempt_v1(
                    schedule=schedule, reserved_at=now
                )
                self._write("attempt", attempt)
                return {
                    "status": "PENDING",
                    "boundary_kind": "QUALIFICATION_MONITOR_PROBE_ATTEMPT_RESERVED",
                    "state_changed": True,
                    "observed_state_digest": attempt[ATTEMPT_DIGEST_FIELD],
                }
            attempt = prefix["attempt"]
            if prefix["capture"] is None:
                requested_at = _clock(self.clock)
                if _moment(requested_at, "V32_PROBE_CLOCK_INVALID") > _moment(
                    schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID"
                ):
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=None,
                        failed_at=requested_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_WINDOW_EXPIRED_AFTER_RESERVATION"
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": "QUALIFICATION_MONITOR_PROBE_WINDOW_EXPIRED",
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                try:
                    captured = self.capture_port.capture_public_mark(
                        attempt=attempt, requested_at=requested_at
                    )
                except V32PublicTransportUnavailableError as exc:
                    physical_code = getattr(
                        exc,
                        "coverage_failure_code",
                        "PUBLIC_TRANSPORT_IO_FAILURE",
                    )
                    if physical_code not in TRANSPORT_COVERAGE_FAILURE_CODES:
                        raise V32QualificationMonitorProbeStoreError(
                            "V32_PROBE_TRANSPORT_FAILURE_CODE_INVALID"
                        ) from exc
                    captured = {
                        "transport_status": "NO_RESPONSE",
                        "source_request_id": attempt["source_request_id"],
                        "failure_at": str(exc.failure_at),
                        "failure_code": physical_code,
                    }
                if not isinstance(captured, Mapping):
                    raise V32QualificationMonitorProbeStoreError(
                        "V32_PROBE_CAPTURE_RESULT_INVALID"
                    )
                transport_status = captured.get("transport_status")
                expected_fields = (
                    {
                        "transport_status",
                        "source_request_id",
                        "received_at",
                        "captured_at",
                        "final_url",
                        "http_status",
                        "raw_payload",
                    }
                    if transport_status == "RESPONSE_CAPTURED"
                    else {
                        "transport_status",
                        "source_request_id",
                        "failure_at",
                        "failure_code",
                    }
                    if transport_status == "NO_RESPONSE"
                    else set()
                )
                if (
                    set(captured) != expected_fields
                    or captured.get("source_request_id")
                    != attempt["source_request_id"]
                    or (
                        transport_status == "NO_RESPONSE"
                        and captured.get("failure_code")
                        not in TRANSPORT_COVERAGE_FAILURE_CODES
                    )
                ):
                    raise V32QualificationMonitorProbeStoreError(
                        "V32_PROBE_CAPTURE_RESULT_INVALID"
                    )
                if transport_status == "RESPONSE_CAPTURED":
                    capture = build_v32_qualification_monitor_probe_capture_v1(
                        attempt=attempt,
                        schedule=schedule,
                        requested_at=requested_at,
                        captured_at=str(captured["captured_at"]),
                        transport_status="RESPONSE_CAPTURED",
                        response_received_at=str(captured["received_at"]),
                        http_status=captured["http_status"],
                        final_url=captured["final_url"],
                        raw_payload=captured["raw_payload"],
                        failure_code=None,
                    )
                    self._write("capture", capture)
                elif transport_status == "NO_RESPONSE":
                    capture = build_v32_qualification_monitor_probe_capture_v1(
                        attempt=attempt,
                        schedule=schedule,
                        requested_at=requested_at,
                        captured_at=str(captured["failure_at"]),
                        transport_status="NO_RESPONSE",
                        response_received_at=None,
                        http_status=None,
                        final_url=None,
                        raw_payload=None,
                        failure_code=str(captured["failure_code"]),
                    )
                    self._write("capture", capture)
                    return {
                        "status": "PENDING",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_NO_RESPONSE_CAPTURED"
                        ),
                        "state_changed": True,
                        "observed_state_digest": capture[CAPTURE_DIGEST_FIELD],
                    }
                else:
                    raise V32QualificationMonitorProbeStoreError(
                        "V32_PROBE_CAPTURE_RESULT_INVALID"
                    )
                return {
                    "status": "PENDING",
                    "boundary_kind": "QUALIFICATION_MONITOR_PROBE_RAW_CAPTURED",
                    "state_changed": True,
                    "observed_state_digest": capture[CAPTURE_DIGEST_FIELD],
                }
            capture = prefix["capture"]
            if prefix["observation"] is None:
                normalized_at = _clock(self.clock)
                captured_at = str(capture["captured_at"])
                failure_at = max(
                    _moment(normalized_at, "V32_PROBE_CLOCK_INVALID"),
                    _moment(captured_at, "V32_PROBE_CAPTURE_TIME_INVALID"),
                ).isoformat().replace("+00:00", "Z")
                if _moment(captured_at, "V32_PROBE_CAPTURE_TIME_INVALID") < _moment(
                    capture["requested_at"], "V32_PROBE_REQUEST_TIME_INVALID"
                ):
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=failure_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_CAPTURE_CLOCK_INVALID"
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_CAPTURE_CLOCK_INVALID"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                if _moment(captured_at, "V32_PROBE_CAPTURE_TIME_INVALID") > _moment(
                    schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID"
                ):
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=failure_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_RESPONSE_AFTER_WINDOW"
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_RESPONSE_AFTER_WINDOW"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                if capture["transport_status"] == "NO_RESPONSE":
                    physical_code = str(capture["failure_code"])
                    if physical_code not in TRANSPORT_COVERAGE_FAILURE_CODES:
                        raise V32QualificationMonitorProbeStoreError(
                            "V32_PROBE_TRANSPORT_FAILURE_CODE_INVALID"
                        )
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=failure_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_PUBLIC_SOURCE_UNAVAILABLE:"
                            + physical_code
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_PUBLIC_SOURCE_UNAVAILABLE"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                response_received_at = str(capture["response_received_at"])
                if (
                    _moment(
                        response_received_at, "V32_PROBE_RESPONSE_TIME_INVALID"
                    )
                    < _moment(capture["requested_at"], "V32_PROBE_REQUEST_TIME_INVALID")
                    or _moment(
                        response_received_at, "V32_PROBE_RESPONSE_TIME_INVALID"
                    )
                    > _moment(captured_at, "V32_PROBE_CAPTURE_TIME_INVALID")
                ):
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=failure_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_RESPONSE_CLOCK_INVALID"
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_RESPONSE_CLOCK_INVALID"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                if capture["final_url"] != _EXPECTED_OKX_MARK_URL:
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=failure_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_RESPONSE_IDENTITY_INVALID"
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_RESPONSE_IDENTITY_INVALID"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                http_status = int(capture["http_status"])
                if http_status == 429 or 500 <= http_status <= 599:
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=failure_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_PUBLIC_SOURCE_UNAVAILABLE:"
                            "PUBLIC_PROVIDER_UNAVAILABLE"
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_PUBLIC_SOURCE_UNAVAILABLE"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                if http_status != 200:
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=failure_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_HTTP_STATUS_STRUCTURAL:"
                            + str(http_status)
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_HTTP_STATUS_STRUCTURAL"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                if _moment(normalized_at, "V32_PROBE_CLOCK_INVALID") > _moment(
                    schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID"
                ):
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=normalized_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_NORMALIZATION_AFTER_WINDOW"
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": (
                            "QUALIFICATION_MONITOR_PROBE_NORMALIZATION_AFTER_WINDOW"
                        ),
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                raw = decode_v32_qualification_monitor_probe_raw_v1(
                    capture, attempt=attempt, schedule=schedule
                )
                if raw is None:
                    raise V32QualificationMonitorProbeStoreError(
                        "V32_PROBE_DURABLE_RAW_MISSING"
                    )
                try:
                    disposition, parsed = parse_v32_public_mark_raw_v1(
                        raw_payload=raw,
                        available_at=capture["captured_at"],
                    )
                except V32OutcomeTickCompositionError as exc:
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=normalized_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_NORMALIZATION_FAILED:"
                            + str(exc)
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": "QUALIFICATION_MONITOR_PROBE_NORMALIZATION_FAILED",
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                if disposition != "OBSERVED":
                    failure = build_v32_qualification_monitor_probe_failure_v1(
                        schedule=schedule,
                        attempt=attempt,
                        capture=capture,
                        failed_at=normalized_at,
                        failure_code=(
                            "QUALIFICATION_MONITOR_PROBE_"
                            + str(parsed["failure_code"])
                        ),
                    )
                    self._write("failure", failure)
                    return {
                        "status": "FAILED_CLOSED",
                        "boundary_kind": "QUALIFICATION_MONITOR_PROBE_COVERAGE_LOSS",
                        "state_changed": True,
                        "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                        "failure": failure,
                    }
                observation = build_v32_qualification_monitor_probe_observation_v1(
                    schedule=schedule,
                    attempt=attempt,
                    capture=capture,
                    normalized_at=normalized_at,
                    value=parsed["value"],
                    provider_as_of=parsed["provider_as_of"],
                    quality=parsed["quality"],
                )
                self._write("observation", observation)
                return {
                    "status": "PENDING",
                    "boundary_kind": "QUALIFICATION_MONITOR_PROBE_NORMALIZED",
                    "state_changed": True,
                    "observed_state_digest": observation[OBSERVATION_DIGEST_FIELD],
                }
            observation = prefix["observation"]
            completed_at = _clock(self.clock)
            if _moment(completed_at, "V32_PROBE_CLOCK_INVALID") > _moment(
                schedule["expires_at"], "V32_PROBE_EXPIRES_INVALID"
            ):
                failure = build_v32_qualification_monitor_probe_failure_v1(
                    schedule=schedule,
                    attempt=attempt,
                    capture=capture,
                    failed_at=completed_at,
                    failure_code=(
                        "QUALIFICATION_MONITOR_PROBE_COMPLETION_AFTER_WINDOW"
                    ),
                )
                self._write("failure", failure)
                return {
                    "status": "FAILED_CLOSED",
                    "boundary_kind": (
                        "QUALIFICATION_MONITOR_PROBE_COMPLETION_AFTER_WINDOW"
                    ),
                    "state_changed": True,
                    "observed_state_digest": failure[FAILURE_DIGEST_FIELD],
                    "failure": failure,
                }
            completion = build_v32_qualification_monitor_probe_completion_v1(
                schedule=schedule,
                attempt=attempt,
                capture=capture,
                observation=observation,
                completed_at=completed_at,
            )
            self._write("completion", completion)
            return {
                "status": "COMPLETE",
                "boundary_kind": "QUALIFICATION_MONITOR_PROBE_COMPLETED",
                "state_changed": True,
                "observed_state_digest": completion[COMPLETION_DIGEST_FIELD],
                "completion": completion,
            }

    def replay(self) -> Mapping[str, Any]:
        prefix = self.load_prefix()
        if prefix["failure"] is not None or prefix["completion"] is None:
            raise V32QualificationMonitorProbeStoreError("V32_PROBE_COMPLETION_MISSING")
        # Loading already reconstructs every self-digested object and decodes
        # the exact raw bytes.  Parsing again proves zero-network determinism.
        raw = decode_v32_qualification_monitor_probe_raw_v1(
            prefix["capture"], attempt=prefix["attempt"], schedule=prefix["schedule"]
        )
        if raw is not None:
            disposition, parsed = parse_v32_public_mark_raw_v1(
                raw_payload=raw,
                available_at=prefix["capture"]["captured_at"],
            )
            if (
                disposition != "OBSERVED"
                or prefix["observation"]["value"] != parsed["value"]
                or prefix["observation"]["provider_as_of"] != parsed["provider_as_of"]
                or prefix["observation"]["quality"] != parsed["quality"]
            ):
                raise V32QualificationMonitorProbeStoreError("V32_PROBE_REPLAY_INVALID")
        return {**prefix, "replay_network_calls": 0, "full_replay_verified": True}


__all__ = [
    "LocalV32QualificationMonitorProbeStore",
    "STORE_ROOT",
    "V32QualificationMonitorProbeStoreError",
]
