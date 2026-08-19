"""Atomic raw-first evidence storage for the V3.1 successor monitor.

This module is deliberately versioned beside the frozen V3.1 monitor store.
It owns response capture bundles and a small CAS cursor; it never performs a
network request, parses a market value, invokes an Agent, or mutates a
portfolio.  The legacy monitor remains the owner of plans, sole-attempt
reservations, and final outcome receipts.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.v31_monitor_runtime import verify_monitor_resolution_attempt
from ..domain.v31_outcome_capture_v2 import (
    verify_outcome_clock_policy,
    verify_public_outcome_capture,
    verify_public_outcome_parse_receipt,
    verify_public_outcome_transport_failure,
)


EVIDENCE_CHECKPOINT_SCHEMA_ID = "theory_paper_v31_outcome_evidence_checkpoint_v2"
EVIDENCE_CHECKPOINT_SCHEMA_VERSION = "2.1.0"
EVIDENCE_FAILURE_SCHEMA_ID = "theory_paper_v31_outcome_evidence_failure_v2"
EVIDENCE_FAILURE_SCHEMA_VERSION = "2.0.0"

_RESOLUTION_THREAD_LOCKS_GUARD = threading.Lock()
_RESOLUTION_THREAD_LOCKS: dict[str, threading.RLock] = {}


class V31OutcomeEvidenceStoreV2Error(ValueError):
    """The versioned raw-first evidence chronology failed closed."""


_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "revision",
        "status",
        "total_cycles",
        "clock_policy_digest",
        "attempt_bindings",
        "capture_bindings",
        "parse_bindings",
        "resolution_bindings",
        "transport_failure_binding",
        "failure_binding",
        "resume_allowed",
        "created_at",
        "updated_at",
        "raw_before_parse",
        "retry_allowed",
        "external_execution_authority",
        "executable",
        "checkpoint_digest",
    }
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31OutcomeEvidenceStoreV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31OutcomeEvidenceStoreV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31OutcomeEvidenceStoreV2Error(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31OutcomeEvidenceStoreV2Error(code)
    return normalized


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 8:
        raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_CYCLE_INVALID")
    return value


def _digest(value: Any, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise V31OutcomeEvidenceStoreV2Error(code)
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    payload = canonical_bytes(dict(document)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _binding(
    *, relative_ref: str, document: Mapping[str, Any], digest_field: str, path: Path
) -> dict[str, str]:
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V31OutcomeEvidenceStoreV2Error(
            "V31_EVIDENCE_DOCUMENT_DIGEST_INVALID"
        ) from exc
    return {
        "relative_ref": relative_ref,
        "semantic_digest": semantic,
        "physical_sha256": _file_sha256(path),
    }


class LocalV31OutcomeEvidenceStoreV2:
    """One local write-once capture/parse chronology for a successor run."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.run_root / "monitor-v2" / "checkpoint.json"

    @contextmanager
    def _lock(self):
        path = self.run_root / ".locks" / "v31-outcome-evidence-v2.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def resolution_guard(self, *, run_id: str):
        """Serialize the sole outcome boundary across processes and threads.

        A durable reserved attempt means a crashed worker only after the worker
        that owned this operating-system lock has exited.  Concurrent wakeups
        wait here and then re-read the completed state instead of mistaking an
        in-flight request for an attempt-only crash.
        """

        if not isinstance(run_id, str) or not run_id.strip() or run_id != run_id.strip():
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_RUN_ID_INVALID")
        path = self.run_root / ".locks" / "v31-outcome-resolution-v2.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        key = str(path)
        with _RESOLUTION_THREAD_LOCKS_GUARD:
            thread_lock = _RESOLUTION_THREAD_LOCKS.setdefault(
                key, threading.RLock()
            )
        with thread_lock:
            with path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _safe_path(self, relative_ref: str) -> Path:
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_PATH_INVALID")
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_PATH_INVALID")
        candidate = self.run_root.joinpath(*lexical.parts)
        try:
            if candidate.exists() and candidate.is_symlink():
                raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_PATH_INVALID")
            candidate.resolve().relative_to(self.run_root)
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_PATH_INVALID"
            ) from exc
        return candidate

    @staticmethod
    def _cycle_root(cycle_index: int) -> str:
        return f"monitor-v2/cycles/{_cycle(cycle_index):04d}"

    def initialize_checkpoint(
        self,
        *,
        run_id: str,
        created_at: str,
        clock_policy_digest: str,
        total_cycles: int = 8,
    ) -> Mapping[str, Any]:
        if not isinstance(run_id, str) or not run_id.strip() or run_id != run_id.strip():
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_RUN_ID_INVALID")
        if total_cycles != 8 or isinstance(total_cycles, bool):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_TOTAL_INVALID")
        policy_digest = _digest(
            clock_policy_digest, "V31_EVIDENCE_CLOCK_POLICY_DIGEST_INVALID"
        )
        _time(created_at, "V31_EVIDENCE_TIME_INVALID")
        with self._lock():
            if self.checkpoint_path.exists():
                current = self.load_checkpoint(run_id=run_id, _already_locked=True)
                if (
                    current["total_cycles"] != total_cycles
                    or current["clock_policy_digest"] != policy_digest
                ):
                    raise V31OutcomeEvidenceStoreV2Error(
                        "V31_EVIDENCE_INITIALIZATION_CONFLICT"
                    )
                return current
            checkpoint = self_digest(
                {
                    "schema_id": EVIDENCE_CHECKPOINT_SCHEMA_ID,
                    "schema_version": EVIDENCE_CHECKPOINT_SCHEMA_VERSION,
                    "run_id": run_id,
                    "revision": 0,
                    "status": "ACTIVE",
                    "total_cycles": 8,
                    "clock_policy_digest": policy_digest,
                    "attempt_bindings": [],
                    "capture_bindings": [],
                    "parse_bindings": [],
                    "resolution_bindings": [],
                    "transport_failure_binding": None,
                    "failure_binding": None,
                    "resume_allowed": True,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "raw_before_parse": True,
                    "retry_allowed": False,
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "checkpoint_digest",
            )
            self._validate_checkpoint(checkpoint, run_id=run_id)
            write_once_json(self.checkpoint_path, checkpoint)
            return checkpoint

    def load_checkpoint(
        self, *, run_id: str, _already_locked: bool = False
    ) -> Mapping[str, Any]:
        if not _already_locked:
            with self._lock():
                return self.load_checkpoint(run_id=run_id, _already_locked=True)
        if not self.checkpoint_path.is_file() or self.checkpoint_path.is_symlink():
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_CHECKPOINT_MISSING")
        try:
            checkpoint = load_json_strict(self.checkpoint_path)
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_CHECKPOINT_INVALID"
            ) from exc
        self._validate_checkpoint(checkpoint, run_id=run_id)
        return checkpoint

    def _validate_checkpoint(
        self, checkpoint: Mapping[str, Any], *, run_id: str
    ) -> None:
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except (TypeError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        attempts = checkpoint.get("attempt_bindings")
        captures = checkpoint.get("capture_bindings")
        parses = checkpoint.get("parse_bindings")
        resolutions = checkpoint.get("resolution_bindings")
        transport_failure = checkpoint.get("transport_failure_binding")
        if (
            set(checkpoint) != _CHECKPOINT_FIELDS
            or checkpoint.get("schema_id") != EVIDENCE_CHECKPOINT_SCHEMA_ID
            or checkpoint.get("schema_version") != EVIDENCE_CHECKPOINT_SCHEMA_VERSION
            or checkpoint.get("run_id") != run_id
            or checkpoint.get("status") not in {"ACTIVE", "TERMINAL", "FAILED_CLOSED"}
            or checkpoint.get("total_cycles") != 8
            or not isinstance(checkpoint.get("revision"), int)
            or isinstance(checkpoint.get("revision"), bool)
            or checkpoint.get("revision") < 0
            or not isinstance(checkpoint.get("clock_policy_digest"), str)
            or not all(isinstance(rows, list) for rows in (attempts, captures, parses, resolutions))
            or not len(resolutions) <= len(parses) <= len(captures) <= len(attempts) <= 8
            or any(
                left - right > 1
                for left, right in (
                    (len(attempts), len(captures)),
                    (len(captures), len(parses)),
                    (len(parses), len(resolutions)),
                )
            )
            or checkpoint.get("raw_before_parse") is not True
            or checkpoint.get("retry_allowed") is not False
            or checkpoint.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or checkpoint.get("executable") is not False
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_CHECKPOINT_INVALID")
        _digest(
            checkpoint.get("clock_policy_digest"),
            "V31_EVIDENCE_CLOCK_POLICY_DIGEST_INVALID",
        )
        if checkpoint["status"] == "FAILED_CLOSED":
            if checkpoint.get("resume_allowed") is not False or not isinstance(
                checkpoint.get("failure_binding"), Mapping
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_FAILURE_STATE_INVALID"
                )
        elif checkpoint.get("resume_allowed") is not True or checkpoint.get(
            "failure_binding"
        ) is not None:
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_ACTIVE_STATE_INVALID")
        if checkpoint["status"] == "TERMINAL" and len(resolutions) != 8:
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_TERMINAL_INVALID")
        created = _time(checkpoint.get("created_at"), "V31_EVIDENCE_TIME_INVALID")
        updated = _time(checkpoint.get("updated_at"), "V31_EVIDENCE_TIME_INVALID")
        if updated < created:
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_TIME_ORDER_INVALID")
        for expected, binding in enumerate(attempts, start=1):
            self._verify_attempt_binding(binding, cycle_index=expected)
        for expected, binding in enumerate(captures, start=1):
            self._verify_capture_binding(binding, cycle_index=expected)
        for expected, binding in enumerate(parses, start=1):
            self._verify_parse_binding(binding, cycle_index=expected)
        for expected, binding in enumerate(resolutions, start=1):
            self._verify_resolution_binding(binding, cycle_index=expected)
            if (
                binding.get("capture_digest")
                != captures[expected - 1].get("capture_digest")
                or binding.get("parse_receipt_digest")
                != parses[expected - 1].get("semantic_digest")
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_RESOLUTION_BINDING_INVALID"
                )
        if transport_failure is not None:
            if checkpoint["status"] == "TERMINAL":
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_TRANSPORT_FAILURE_STATE_INVALID"
                )
            receipt = self._verify_transport_failure_binding(transport_failure)
            cycle = int(transport_failure["cycle_index"])
            if (
                len(attempts) != cycle
                or len(captures) != cycle - 1
                or len(parses) != cycle - 1
                or len(resolutions) != cycle - 1
                or receipt.get("run_id") != run_id
                or receipt.get("monitor_attempt_digest")
                != attempts[cycle - 1]["semantic_digest"]
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_TRANSPORT_FAILURE_STATE_INVALID"
                )
        if isinstance(checkpoint.get("failure_binding"), Mapping):
            failure = self._verify_failure_binding(checkpoint["failure_binding"])
            expected_transport_digest = (
                transport_failure["semantic_digest"]
                if isinstance(transport_failure, Mapping)
                else None
            )
            if failure.get("transport_failure_digest") != expected_transport_digest:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_FAILURE_TRANSPORT_MISMATCH"
                )

    def _replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_digest: str,
        candidate: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        current = self.load_checkpoint(run_id=run_id, _already_locked=True)
        if current["checkpoint_digest"] != expected_digest:
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_CAS_CONFLICT")
        if current["status"] in {"FAILED_CLOSED", "TERMINAL"}:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TERMINAL_STATE_IMMUTABLE"
            )
        payload = dict(candidate)
        payload.pop("checkpoint_digest", None)
        if payload.get("revision") != int(current["revision"]) + 1:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_REVISION_TRANSITION_INVALID"
            )
        immutable_fields = {
            "schema_id",
            "schema_version",
            "run_id",
            "total_cycles",
            "clock_policy_digest",
            "created_at",
            "raw_before_parse",
            "retry_allowed",
            "external_execution_authority",
            "executable",
        }
        if any(payload.get(field) != current.get(field) for field in immutable_fields):
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_IMMUTABLE_FIELD_CHANGED"
            )
        for field in (
            "attempt_bindings",
            "capture_bindings",
            "parse_bindings",
            "resolution_bindings",
        ):
            before = current[field]
            after = payload.get(field)
            if (
                not isinstance(after, list)
                or after[: len(before)] != before
                or len(after) - len(before) not in {0, 1}
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_APPEND_ONLY_TRANSITION_INVALID"
                )
        current_transport = current.get("transport_failure_binding")
        next_transport = payload.get("transport_failure_binding")
        if current_transport is not None and next_transport != current_transport:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_IMMUTABLE"
            )
        if current_transport is None and next_transport is not None and not isinstance(
            next_transport, Mapping
        ):
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_TRANSITION_INVALID"
            )
        current_failure = current.get("failure_binding")
        next_failure = payload.get("failure_binding")
        if current_failure is not None and next_failure != current_failure:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_FAILURE_IMMUTABLE"
            )
        if current_failure is None and next_failure is not None and not isinstance(
            next_failure, Mapping
        ):
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_FAILURE_TRANSITION_INVALID"
            )
        if payload.get("status") not in {"ACTIVE", "FAILED_CLOSED", "TERMINAL"}:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_STATUS_TRANSITION_INVALID"
            )
        if _time(payload.get("updated_at"), "V31_EVIDENCE_TIME_INVALID") < _time(
            current.get("updated_at"), "V31_EVIDENCE_TIME_INVALID"
        ):
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TIME_ROLLBACK"
            )
        next_checkpoint = self_digest(payload, "checkpoint_digest")
        self._validate_checkpoint(next_checkpoint, run_id=run_id)
        _atomic_json(self.checkpoint_path, next_checkpoint)
        return next_checkpoint

    def _verify_attempt_binding(
        self, binding: Mapping[str, Any], *, cycle_index: int
    ) -> Mapping[str, Any]:
        expected_ref = f"monitor/cycles/{cycle_index:04d}/resolution-attempt.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {"cycle_index", "relative_ref", "semantic_digest", "physical_sha256"}
            or binding.get("cycle_index") != cycle_index
            or binding.get("relative_ref") != expected_ref
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_ATTEMPT_BINDING_INVALID")
        path = self._safe_path(expected_ref)
        try:
            document = load_json_strict(path)
            semantic = verify_monitor_resolution_attempt(document)
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_ATTEMPT_BINDING_INVALID"
            ) from exc
        if (
            semantic != _digest(binding.get("semantic_digest"), "V31_EVIDENCE_ATTEMPT_BINDING_INVALID")
            or _file_sha256(path)
            != _digest(binding.get("physical_sha256"), "V31_EVIDENCE_ATTEMPT_BINDING_INVALID")
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_ATTEMPT_BINDING_INVALID")
        return document

    def register_legacy_attempt(
        self, *, run_id: str, cycle_index: int, recorded_at: str
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index)
        _time(recorded_at, "V31_EVIDENCE_TIME_INVALID")
        ref = f"monitor/cycles/{cycle:04d}/resolution-attempt.json"
        path = self._safe_path(ref)
        try:
            document = load_json_strict(path)
            semantic = verify_monitor_resolution_attempt(document)
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_ATTEMPT_NOT_DURABLE"
            ) from exc
        binding = {
            "cycle_index": cycle,
            "relative_ref": ref,
            "semantic_digest": semantic,
            "physical_sha256": _file_sha256(path),
        }
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            attempts = current["attempt_bindings"]
            if cycle <= len(attempts):
                if attempts[cycle - 1] != binding:
                    raise V31OutcomeEvidenceStoreV2Error(
                        "V31_EVIDENCE_ATTEMPT_WRITE_ONCE_CONFLICT"
                    )
                return current
            if cycle != len(attempts) + 1 or current["status"] != "ACTIVE":
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_ATTEMPT_SEQUENCE_INVALID"
                )
            return self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "attempt_bindings": [*attempts, binding],
                    "updated_at": recorded_at,
                },
            )

    def _capture_paths(self, cycle_index: int) -> tuple[str, str, str]:
        root = self._cycle_root(cycle_index)
        return f"{root}/capture", f"{root}/capture/raw.bin", f"{root}/capture/capture-record.json"

    def _verify_capture_binding(
        self, binding: Mapping[str, Any], *, cycle_index: int
    ) -> tuple[Mapping[str, Any], bytes]:
        bundle_ref, raw_ref, record_ref = self._capture_paths(cycle_index)
        expected_fields = {
            "cycle_index",
            "bundle_ref",
            "raw_capture_ref",
            "raw_capture_sha256",
            "capture_record_ref",
            "capture_digest",
            "capture_record_physical_sha256",
        }
        if (
            not isinstance(binding, Mapping)
            or set(binding) != expected_fields
            or binding.get("cycle_index") != cycle_index
            or binding.get("bundle_ref") != bundle_ref
            or binding.get("raw_capture_ref") != raw_ref
            or binding.get("capture_record_ref") != record_ref
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_CAPTURE_BINDING_INVALID")
        raw_path = self._safe_path(raw_ref)
        record_path = self._safe_path(record_ref)
        if (
            not raw_path.is_file()
            or raw_path.is_symlink()
            or not record_path.is_file()
            or record_path.is_symlink()
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_CAPTURE_BINDING_INVALID")
        raw = raw_path.read_bytes()
        try:
            record = load_json_strict(record_path)
            semantic = verify_public_outcome_capture(record, raw_payload=raw)
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_CAPTURE_BINDING_INVALID"
            ) from exc
        if (
            _sha256(raw)
            != _digest(binding.get("raw_capture_sha256"), "V31_EVIDENCE_CAPTURE_BINDING_INVALID")
            or semantic
            != _digest(binding.get("capture_digest"), "V31_EVIDENCE_CAPTURE_BINDING_INVALID")
            or _file_sha256(record_path)
            != _digest(
                binding.get("capture_record_physical_sha256"),
                "V31_EVIDENCE_CAPTURE_BINDING_INVALID",
            )
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_CAPTURE_BINDING_INVALID")
        return record, raw

    def _publish_capture_bundle(
        self, *, cycle_index: int, capture: Mapping[str, Any], raw_payload: bytes
    ) -> dict[str, Any]:
        bundle_ref, raw_ref, record_ref = self._capture_paths(cycle_index)
        bundle_path = self._safe_path(bundle_ref)
        raw_path = self._safe_path(raw_ref)
        record_path = self._safe_path(record_ref)
        if not isinstance(raw_payload, bytes):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_RAW_INVALID")
        try:
            capture_digest = verify_public_outcome_capture(
                capture, raw_payload=raw_payload
            )
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_CAPTURE_INVALID"
            ) from exc
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        if bundle_path.exists():
            binding = {
                "cycle_index": cycle_index,
                "bundle_ref": bundle_ref,
                "raw_capture_ref": raw_ref,
                "raw_capture_sha256": _sha256(raw_payload),
                "capture_record_ref": record_ref,
                "capture_digest": capture_digest,
                "capture_record_physical_sha256": _file_sha256(record_path),
            }
            durable_capture, durable_raw = self._verify_capture_binding(
                binding, cycle_index=cycle_index
            )
            if durable_capture != dict(capture) or durable_raw != raw_payload:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_CAPTURE_WRITE_ONCE_CONFLICT"
                )
            return binding
        temporary = Path(
            tempfile.mkdtemp(prefix=".capture.", dir=bundle_path.parent)
        )
        moved = False
        try:
            temporary_raw = temporary / "raw.bin"
            temporary_record = temporary / "capture-record.json"
            with temporary_raw.open("xb") as handle:
                handle.write(raw_payload)
                handle.flush()
                os.fsync(handle.fileno())
            with temporary_record.open("xb") as handle:
                handle.write(canonical_bytes(dict(capture)) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            directory_descriptor = os.open(temporary, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
            os.replace(temporary, bundle_path)
            moved = True
            parent_descriptor = os.open(bundle_path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
        finally:
            if not moved and temporary.exists():
                for child in temporary.iterdir():
                    child.unlink(missing_ok=True)
                temporary.rmdir()
        return {
            "cycle_index": cycle_index,
            "bundle_ref": bundle_ref,
            "raw_capture_ref": raw_ref,
            "raw_capture_sha256": _sha256(raw_payload),
            "capture_record_ref": record_ref,
            "capture_digest": capture_digest,
            "capture_record_physical_sha256": _file_sha256(record_path),
        }

    def commit_response_capture(
        self,
        *,
        run_id: str,
        cycle_index: int,
        capture: Mapping[str, Any],
        raw_payload: bytes,
        committed_at: str,
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index)
        _time(committed_at, "V31_EVIDENCE_TIME_INVALID")
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if current["status"] != "ACTIVE" or len(current["attempt_bindings"]) != cycle:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_CAPTURE_WITHOUT_ATTEMPT"
                )
            attempt = current["attempt_bindings"][cycle - 1]
            if (
                capture.get("run_id") != run_id
                or capture.get("cycle_index") != cycle
                or capture.get("monitor_attempt_digest")
                != attempt["semantic_digest"]
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_CAPTURE_ATTEMPT_MISMATCH"
                )
            binding = self._publish_capture_bundle(
                cycle_index=cycle, capture=capture, raw_payload=raw_payload
            )
            captures = current["capture_bindings"]
            if cycle <= len(captures):
                if captures[cycle - 1] != binding:
                    raise V31OutcomeEvidenceStoreV2Error(
                        "V31_EVIDENCE_CAPTURE_WRITE_ONCE_CONFLICT"
                    )
                return current
            if cycle != len(captures) + 1:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_CAPTURE_SEQUENCE_INVALID"
                )
            return self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "capture_bindings": [*captures, binding],
                    "updated_at": committed_at,
                },
            )

    def recover_unbound_capture(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any]:
        """Bind an already-published canonical bundle without another GET."""

        cycle = _cycle(cycle_index)
        bundle_ref, raw_ref, record_ref = self._capture_paths(cycle)
        record_path = self._safe_path(record_ref)
        raw_path = self._safe_path(raw_ref)
        if not record_path.is_file() or not raw_path.is_file():
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_RECOVERABLE_CAPTURE_MISSING"
            )
        record = load_json_strict(record_path)
        raw = raw_path.read_bytes()
        recovered_at = str(record.get("response_received_at"))
        _time(recovered_at, "V31_EVIDENCE_TIME_INVALID")
        binding = {
            "cycle_index": cycle,
            "bundle_ref": bundle_ref,
            "raw_capture_ref": raw_ref,
            "raw_capture_sha256": _sha256(raw),
            "capture_record_ref": record_ref,
            "capture_digest": verify_public_outcome_capture(record, raw_payload=raw),
            "capture_record_physical_sha256": _file_sha256(record_path),
        }
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or current.get("transport_failure_binding") is not None
                or len(current["attempt_bindings"]) != cycle
                or len(current["capture_bindings"]) != cycle - 1
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_CAPTURE_RECOVERY_STATE_INVALID"
                )
            attempt = current["attempt_bindings"][cycle - 1]
            if (
                record.get("run_id") != run_id
                or record.get("cycle_index") != cycle
                or record.get("monitor_attempt_digest") != attempt["semantic_digest"]
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_CAPTURE_RECOVERY_BINDING_INVALID"
                )
            self._verify_capture_binding(binding, cycle_index=cycle)
            return self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "capture_bindings": [*current["capture_bindings"], binding],
                    "updated_at": recovered_at,
                },
            )

    def load_committed_capture(
        self, *, run_id: str, cycle_index: int
    ) -> tuple[Mapping[str, Any], bytes, Mapping[str, Any]]:
        cycle = _cycle(cycle_index)
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["capture_bindings"]) < cycle:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_CAPTURE_NOT_COMMITTED"
                )
            binding = checkpoint["capture_bindings"][cycle - 1]
            capture, raw = self._verify_capture_binding(binding, cycle_index=cycle)
            return capture, raw, dict(binding)

    def _verify_parse_binding(
        self, binding: Mapping[str, Any], *, cycle_index: int
    ) -> Mapping[str, Any]:
        expected_ref = f"{self._cycle_root(cycle_index)}/parse-receipt.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "cycle_index",
                "relative_ref",
                "semantic_digest",
                "physical_sha256",
                "parse_status",
            }
            or binding.get("cycle_index") != cycle_index
            or binding.get("relative_ref") != expected_ref
            or binding.get("parse_status")
            not in {"ADMITTED_OBSERVED", "ADMITTED_UNKNOWN", "REJECTED"}
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_PARSE_BINDING_INVALID")
        path = self._safe_path(expected_ref)
        try:
            document = load_json_strict(path)
            semantic = verify_self_digest(document, "parse_receipt_digest")
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_PARSE_BINDING_INVALID"
            ) from exc
        if (
            semantic != _digest(binding.get("semantic_digest"), "V31_EVIDENCE_PARSE_BINDING_INVALID")
            or _file_sha256(path)
            != _digest(binding.get("physical_sha256"), "V31_EVIDENCE_PARSE_BINDING_INVALID")
            or document.get("parse_status") != binding.get("parse_status")
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_PARSE_BINDING_INVALID")
        return document

    def commit_parse_receipt(
        self,
        *,
        run_id: str,
        cycle_index: int,
        receipt: Mapping[str, Any],
        clock_policy: Mapping[str, Any],
        observable_ref: str,
        committed_at: str,
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index)
        _time(committed_at, "V31_EVIDENCE_TIME_INVALID")
        capture, raw, _ = self.load_committed_capture(
            run_id=run_id, cycle_index=cycle
        )
        try:
            policy_digest = verify_outcome_clock_policy(clock_policy)
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_CLOCK_POLICY_INVALID"
            ) from exc
        try:
            semantic = verify_public_outcome_parse_receipt(
                receipt,
                capture=capture,
                raw_payload=raw,
                clock_policy=clock_policy,
                observable_ref=observable_ref,
            )
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_PARSE_RECEIPT_INVALID"
            ) from exc
        relative_ref = f"{self._cycle_root(cycle)}/parse-receipt.json"
        path = self._safe_path(relative_ref)
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            parses = current["parse_bindings"]
            if cycle <= len(parses):
                binding = {
                    "cycle_index": cycle,
                    "relative_ref": relative_ref,
                    "semantic_digest": semantic,
                    "physical_sha256": _file_sha256(path),
                    "parse_status": receipt["parse_status"],
                }
                if parses[cycle - 1] != binding:
                    raise V31OutcomeEvidenceStoreV2Error(
                        "V31_EVIDENCE_PARSE_WRITE_ONCE_CONFLICT"
                    )
                return current
            if (
                current["status"] != "ACTIVE"
                or current["clock_policy_digest"] != policy_digest
                or current.get("transport_failure_binding") is not None
                or cycle != len(parses) + 1
                or len(current["capture_bindings"]) != cycle
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_PARSE_SEQUENCE_INVALID"
                )
            write_once_json(path, receipt)
            binding = {
                "cycle_index": cycle,
                "relative_ref": relative_ref,
                "semantic_digest": semantic,
                "physical_sha256": _file_sha256(path),
                "parse_status": receipt["parse_status"],
            }
            return self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "parse_bindings": [*parses, binding],
                    "updated_at": committed_at,
                },
            )

    def read_parse_receipt(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index)
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if len(checkpoint["parse_bindings"]) < cycle:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_PARSE_RECEIPT_MISSING"
                )
            return self._verify_parse_binding(
                checkpoint["parse_bindings"][cycle - 1], cycle_index=cycle
            )

    def _verify_resolution_binding(
        self, binding: Mapping[str, Any], *, cycle_index: int
    ) -> Mapping[str, Any]:
        expected_ref = f"monitor/cycles/{cycle_index:04d}/outcome-receipt.json"
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "cycle_index",
                "relative_ref",
                "semantic_digest",
                "physical_sha256",
                "capture_digest",
                "parse_receipt_digest",
            }
            or binding.get("cycle_index") != cycle_index
            or binding.get("relative_ref") != expected_ref
        ):
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_RESOLUTION_BINDING_INVALID"
            )
        path = self._safe_path(expected_ref)
        try:
            document = load_json_strict(path)
            semantic = verify_self_digest(document, "outcome_receipt_digest")
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_RESOLUTION_BINDING_INVALID"
            ) from exc
        if (
            semantic
            != _digest(binding.get("semantic_digest"), "V31_EVIDENCE_RESOLUTION_BINDING_INVALID")
            or _file_sha256(path)
            != _digest(binding.get("physical_sha256"), "V31_EVIDENCE_RESOLUTION_BINDING_INVALID")
        ):
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_RESOLUTION_BINDING_INVALID"
            )
        return document

    def bind_legacy_resolution(
        self, *, run_id: str, cycle_index: int, bound_at: str
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index)
        _time(bound_at, "V31_EVIDENCE_TIME_INVALID")
        relative_ref = f"monitor/cycles/{cycle:04d}/outcome-receipt.json"
        path = self._safe_path(relative_ref)
        try:
            document = load_json_strict(path)
            semantic = verify_self_digest(document, "outcome_receipt_digest")
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_LEGACY_OUTCOME_NOT_DURABLE"
            ) from exc
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current["status"] != "ACTIVE"
                or current.get("transport_failure_binding") is not None
                or len(current["parse_bindings"]) != cycle
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_RESOLUTION_BEFORE_PARSE"
                )
            parse_binding = current["parse_bindings"][cycle - 1]
            if parse_binding["parse_status"] == "REJECTED":
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_REJECTED_PARSE_CANNOT_RESOLVE"
                )
            capture_binding = current["capture_bindings"][cycle - 1]
            binding = {
                "cycle_index": cycle,
                "relative_ref": relative_ref,
                "semantic_digest": semantic,
                "physical_sha256": _file_sha256(path),
                "capture_digest": capture_binding["capture_digest"],
                "parse_receipt_digest": parse_binding["semantic_digest"],
            }
            resolutions = current["resolution_bindings"]
            if cycle <= len(resolutions):
                if resolutions[cycle - 1] != binding:
                    raise V31OutcomeEvidenceStoreV2Error(
                        "V31_EVIDENCE_RESOLUTION_WRITE_ONCE_CONFLICT"
                    )
                return current
            if cycle != len(resolutions) + 1:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_RESOLUTION_SEQUENCE_INVALID"
                )
            status = "TERMINAL" if cycle == 8 else "ACTIVE"
            return self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "status": status,
                    "resolution_bindings": [*resolutions, binding],
                    "updated_at": bound_at,
                },
            )

    def _verify_failure_binding(self, binding: Mapping[str, Any]) -> Mapping[str, Any]:
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {"relative_ref", "semantic_digest", "physical_sha256", "failure_code"}
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_FAILURE_BINDING_INVALID")
        path = self._safe_path(str(binding.get("relative_ref")))
        try:
            document = load_json_strict(path)
            semantic = verify_self_digest(document, "evidence_failure_digest")
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_FAILURE_BINDING_INVALID"
            ) from exc
        if (
            semantic != binding.get("semantic_digest")
            or _file_sha256(path) != binding.get("physical_sha256")
            or document.get("failure_code") != binding.get("failure_code")
        ):
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_FAILURE_BINDING_INVALID")
        return document

    def _transport_failure_path(self, cycle_index: int) -> tuple[str, Path]:
        relative_ref = f"{self._cycle_root(cycle_index)}/transport-failure.json"
        return relative_ref, self._safe_path(relative_ref)

    def _transport_failure_binding_from_document(
        self,
        *,
        run_id: str,
        cycle_index: int,
        receipt: Mapping[str, Any],
        path: Path,
    ) -> dict[str, Any]:
        cycle = _cycle(cycle_index)
        try:
            semantic = verify_public_outcome_transport_failure(receipt)
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_INVALID"
            ) from exc
        if receipt.get("run_id") != run_id or receipt.get("cycle_index") != cycle:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            )
        relative_ref, expected_path = self._transport_failure_path(cycle)
        if path != expected_path or not path.is_file() or path.is_symlink():
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            )
        return {
            "cycle_index": cycle,
            "relative_ref": relative_ref,
            "semantic_digest": semantic,
            "physical_sha256": _file_sha256(path),
            "failure_code": receipt["failure_code"],
        }

    def _verify_transport_failure_binding(
        self, binding: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        expected_fields = {
            "cycle_index",
            "relative_ref",
            "semantic_digest",
            "physical_sha256",
            "failure_code",
        }
        if not isinstance(binding, Mapping) or set(binding) != expected_fields:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            )
        cycle = _cycle(binding.get("cycle_index"))
        relative_ref, path = self._transport_failure_path(cycle)
        if binding.get("relative_ref") != relative_ref:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            )
        try:
            receipt = load_json_strict(path)
            semantic = verify_public_outcome_transport_failure(receipt)
        except (OSError, ValueError) as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            ) from exc
        if (
            semantic
            != _digest(
                binding.get("semantic_digest"),
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID",
            )
            or _file_sha256(path)
            != _digest(
                binding.get("physical_sha256"),
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID",
            )
            or receipt.get("failure_code") != binding.get("failure_code")
        ):
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            )
        return receipt

    def fail_checkpoint(
        self,
        *,
        run_id: str,
        cycle_index: int,
        failure_code: str,
        failed_at: str,
        transport_failure: Mapping[str, Any] | None = None,
        legacy_monitor_failure_digest: str | None = None,
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index)
        _time(failed_at, "V31_EVIDENCE_TIME_INVALID")
        if not isinstance(failure_code, str) or not failure_code.strip():
            raise V31OutcomeEvidenceStoreV2Error("V31_EVIDENCE_FAILURE_CODE_INVALID")
        transport_binding = None
        if transport_failure is not None:
            transport_binding = self.persist_transport_failure(
                run_id=run_id,
                cycle_index=cycle,
                receipt=transport_failure,
            )
        if legacy_monitor_failure_digest is not None:
            _digest(
                legacy_monitor_failure_digest,
                "V31_EVIDENCE_LEGACY_FAILURE_DIGEST_INVALID",
            )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if current["status"] == "FAILED_CLOSED":
                return current
            if current["status"] == "TERMINAL":
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_TERMINAL_STATE_IMMUTABLE"
                )
            current_transport = current.get("transport_failure_binding")
            if transport_binding is not None and current_transport != transport_binding:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
                )
            transport_digest = (
                current_transport["semantic_digest"]
                if isinstance(current_transport, Mapping)
                else None
            )
            failure = self_digest(
                {
                    "schema_id": EVIDENCE_FAILURE_SCHEMA_ID,
                    "schema_version": EVIDENCE_FAILURE_SCHEMA_VERSION,
                    "run_id": run_id,
                    "cycle_index": cycle,
                    "failure_code": failure_code,
                    "failed_at": failed_at,
                    "transport_failure_digest": transport_digest,
                    "capture_digest": (
                        current["capture_bindings"][cycle - 1]["capture_digest"]
                        if len(current["capture_bindings"]) >= cycle
                        else None
                    ),
                    "parse_receipt_digest": (
                        current["parse_bindings"][cycle - 1]["semantic_digest"]
                        if len(current["parse_bindings"]) >= cycle
                        else None
                    ),
                    "legacy_monitor_failure_digest": legacy_monitor_failure_digest,
                    "retry_allowed": False,
                    "resume_allowed": False,
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "evidence_failure_digest",
            )
            relative_ref = (
                f"monitor-v2/failures/revision-{int(current['revision']) + 1:04d}.json"
            )
            path = self._safe_path(relative_ref)
            write_once_json(path, failure)
            binding = {
                "relative_ref": relative_ref,
                "semantic_digest": failure["evidence_failure_digest"],
                "physical_sha256": _file_sha256(path),
                "failure_code": failure_code,
            }
            return self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "status": "FAILED_CLOSED",
                    "failure_binding": binding,
                    "resume_allowed": False,
                    "updated_at": failed_at,
                },
            )

    def persist_transport_failure(
        self,
        *,
        run_id: str,
        cycle_index: int,
        receipt: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Write the typed no-response receipt before propagating the failure."""

        cycle = _cycle(cycle_index)
        try:
            verify_public_outcome_transport_failure(receipt)
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_INVALID"
            ) from exc
        if receipt.get("run_id") != run_id or receipt.get("cycle_index") != cycle:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            )
        _, path = self._transport_failure_path(cycle)
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            existing = current.get("transport_failure_binding")
            if existing is not None:
                durable = self._verify_transport_failure_binding(existing)
                if durable != dict(receipt):
                    raise V31OutcomeEvidenceStoreV2Error(
                        "V31_EVIDENCE_TRANSPORT_FAILURE_WRITE_ONCE_CONFLICT"
                    )
                return dict(existing)
            if (
                current["status"] != "ACTIVE"
                or len(current["attempt_bindings"]) != cycle
                or len(current["capture_bindings"]) != cycle - 1
                or len(current["parse_bindings"]) != cycle - 1
                or len(current["resolution_bindings"]) != cycle - 1
                or receipt.get("monitor_attempt_digest")
                != current["attempt_bindings"][cycle - 1]["semantic_digest"]
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_TRANSPORT_FAILURE_STATE_INVALID"
                )
            write_once_json(path, receipt)
            binding = self._transport_failure_binding_from_document(
                run_id=run_id,
                cycle_index=cycle,
                receipt=receipt,
                path=path,
            )
            self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "transport_failure_binding": binding,
                    "updated_at": str(receipt["failure_at"]),
                },
            )
            return binding

    def recover_unbound_transport_failure(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any] | None:
        """Bind a durable no-response receipt after a crash, without another GET."""

        cycle = _cycle(cycle_index)
        _, path = self._transport_failure_path(cycle)
        if not path.exists():
            return None
        if not path.is_file() or path.is_symlink():
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            )
        try:
            receipt = load_json_strict(path)
        except ValueError as exc:
            raise V31OutcomeEvidenceStoreV2Error(
                "V31_EVIDENCE_TRANSPORT_FAILURE_BINDING_INVALID"
            ) from exc
        binding = self._transport_failure_binding_from_document(
            run_id=run_id,
            cycle_index=cycle,
            receipt=receipt,
            path=path,
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            existing = current.get("transport_failure_binding")
            if existing is not None:
                if existing != binding:
                    raise V31OutcomeEvidenceStoreV2Error(
                        "V31_EVIDENCE_TRANSPORT_FAILURE_WRITE_ONCE_CONFLICT"
                    )
                return current
            if (
                current["status"] != "ACTIVE"
                or len(current["attempt_bindings"]) != cycle
                or len(current["capture_bindings"]) != cycle - 1
                or len(current["parse_bindings"]) != cycle - 1
                or len(current["resolution_bindings"]) != cycle - 1
                or receipt.get("monitor_attempt_digest")
                != current["attempt_bindings"][cycle - 1]["semantic_digest"]
            ):
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_TRANSPORT_FAILURE_RECOVERY_STATE_INVALID"
                )
            return self._replace_checkpoint(
                run_id=run_id,
                expected_digest=str(current["checkpoint_digest"]),
                candidate={
                    **current,
                    "revision": int(current["revision"]) + 1,
                    "transport_failure_binding": binding,
                    "updated_at": str(receipt["failure_at"]),
                },
            )

    def read_transport_failure(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index)
        with self._lock():
            checkpoint = self.load_checkpoint(run_id=run_id, _already_locked=True)
            binding = checkpoint.get("transport_failure_binding")
            if not isinstance(binding, Mapping) or binding.get("cycle_index") != cycle:
                raise V31OutcomeEvidenceStoreV2Error(
                    "V31_EVIDENCE_TRANSPORT_FAILURE_MISSING"
                )
            return self._verify_transport_failure_binding(binding)


__all__ = [
    "EVIDENCE_CHECKPOINT_SCHEMA_ID",
    "LocalV31OutcomeEvidenceStoreV2",
    "V31OutcomeEvidenceStoreV2Error",
]
