"""Single-writer durable repository for new V3.3 market cycles.

The Application supplies every logical transition field.  This adapter owns
only physical locking, create-only canonical files, content references, and
the compare-and-swap state head.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import threading
from typing import Any, Iterator, Mapping, Sequence

from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
)
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    BUSINESS_ARTIFACT_TYPES,
    CycleRequest,
    HypothesisRecord,
    InputSnapshot,
    Outcome,
    Review,
    RunState,
    validate_run_state_transition,
)
from ..market_data.raw_capture import (
    RawCaptureError,
    RawCaptureReferenceVerifier,
)


_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_STATE_HEAD = Path("state/head.json")
_REQUEST_PATH = Path("request.json")
_TRANSITION_INTENT_SCHEMA_ID = "agent-trade-emotion.market-cycle-transition-intent"
_TRANSITION_INTENT_SCHEMA_VERSION = "1.0.0"

_ARTIFACT_SPEC: dict[type[object], tuple[str, str]] = {
    InputSnapshot: ("InputSnapshot", "snapshot_id"),
    HypothesisRecord: ("HypothesisRecord", "record_id"),
    BehaviorPlan: ("BehaviorPlan", "plan_id"),
    Outcome: ("Outcome", "outcome_id"),
    Review: ("Review", "review_id"),
}
_ARTIFACT_MODEL = {
    "InputSnapshot": InputSnapshot,
    "HypothesisRecord": HypothesisRecord,
    "BehaviorPlan": BehaviorPlan,
    "Outcome": Outcome,
    "Review": Review,
}

_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCK_STATE = threading.local()


class MarketCycleRepositoryError(RuntimeError):
    """A durable repository invariant was not satisfied."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _cycle_id(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise MarketCycleRepositoryError("MARKET_CYCLE_ID_UNSAFE")
    return value


def _artifact_type(value: object) -> str:
    if not isinstance(value, str) or value not in BUSINESS_ARTIFACT_TYPES:
        raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_TYPE_UNSUPPORTED")
    return value


def _artifact_relative_path(artifact_type: str) -> Path:
    return Path("artifacts") / f"{_artifact_type(artifact_type)}.json"


def _history_relative_path(revision: int) -> Path:
    if type(revision) is not int or revision < 0:
        raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_REVISION_INVALID")
    return Path("state/history") / f"{revision:08d}.json"


def _intent_relative_path(revision: int) -> Path:
    if type(revision) is not int or revision < 1:
        raise MarketCycleRepositoryError("MARKET_CYCLE_INTENT_REVISION_INVALID")
    return Path("state/intents") / f"{revision:08d}.json"


def _require_exact_keys(
    value: object, *, expected: frozenset[str], error_code: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != expected:
        raise MarketCycleRepositoryError(error_code)
    return value


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_directory(path: Path) -> None:
    created_or_raced = False
    try:
        path.lstat()
    except FileNotFoundError:
        created_or_raced = True
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise MarketCycleRepositoryError(f"MARKET_CYCLE_DIRECTORY_UNSAFE:{path}")
    if created_or_raced:
        _fsync_directory(path)
        if path.parent != path:
            _fsync_directory(path.parent)


def _read_regular_bytes(path: Path, *, missing_code: str) -> bytes:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRepositoryError(missing_code) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MarketCycleRepositoryError(f"MARKET_CYCLE_FILE_UNSAFE:{path}")
    return path.read_bytes()


def _read_canonical_mapping(path: Path, *, missing_code: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_bytes(path, missing_code=missing_code)
    try:
        value = loads_json_strict(raw)
        if canonical_bytes(value) != raw:
            raise MarketCycleRepositoryError(
                f"MARKET_CYCLE_NONCANONICAL_JSON:{path}"
            )
    except CanonicalContractError as exc:
        raise MarketCycleRepositoryError(
            f"MARKET_CYCLE_JSON_INVALID:{path}"
        ) from exc
    return value, raw


def _write_once(path: Path, payload: bytes) -> str:
    _ensure_directory(path.parent)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        metadata = None
    if metadata is not None:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MarketCycleRepositoryError(f"MARKET_CYCLE_FILE_UNSAFE:{path}")
        if path.read_bytes() != payload:
            raise MarketCycleRepositoryError(f"MARKET_CYCLE_WRITE_ONCE_CONFLICT:{path}")
        return "EXISTING_IDENTICAL"

    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(8)}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                metadata = None
            if (
                metadata is not None
                and stat.S_ISREG(metadata.st_mode)
                and not stat.S_ISLNK(metadata.st_mode)
                and path.read_bytes() == payload
            ):
                return "EXISTING_IDENTICAL"
            raise MarketCycleRepositoryError(
                f"MARKET_CYCLE_WRITE_ONCE_RACE:{path}"
            ) from exc
        _fsync_directory(path.parent)
        temporary.unlink()
        _fsync_directory(path.parent)
        return "CREATED"
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _require_write_once_compatible(path: Path, payload: bytes) -> None:
    """Fail before a transition writes anything when a target would conflict."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MarketCycleRepositoryError(f"MARKET_CYCLE_FILE_UNSAFE:{path}")
    if path.read_bytes() != payload:
        raise MarketCycleRepositoryError(f"MARKET_CYCLE_WRITE_ONCE_CONFLICT:{path}")


def _stage_initial_cycle(
    root: Path,
    *,
    cycle_id: str,
    request_payload: bytes,
    initial_payload: bytes,
) -> Path:
    """Build and sync a complete, still-invisible revision-zero cycle."""

    staging = root / (
        f".create-{cycle_id}.{os.getpid()}.{threading.get_ident()}."
        f"{secrets.token_hex(8)}.tmp"
    )
    os.mkdir(staging, 0o700)
    try:
        _write_once(staging / _REQUEST_PATH, request_payload)
        _write_once(
            staging / _history_relative_path(0),
            initial_payload,
        )
        _write_once(staging / _STATE_HEAD, initial_payload)
        _fsync_directory(staging / "state" / "history")
        _fsync_directory(staging / "state")
        _fsync_directory(staging)
        return staging
    except BaseException:
        _discard_staging_directory(staging)
        raise


def _discard_staging_directory(staging: Path) -> None:
    """Remove only a private create staging directory after a caught failure."""

    try:
        shutil.rmtree(staging)
    except FileNotFoundError:
        pass


def _publish_cycle_directory(staging: Path, cycle_root: Path) -> None:
    """Atomically make one fully synced cycle directory visible."""

    try:
        cycle_root.lstat()
    except FileNotFoundError:
        pass
    else:
        raise MarketCycleRepositoryError("MARKET_CYCLE_CREATE_TARGET_EXISTS")
    try:
        os.rename(staging, cycle_root)
    except FileExistsError as exc:
        raise MarketCycleRepositoryError(
            "MARKET_CYCLE_CREATE_TARGET_EXISTS"
        ) from exc
    except OSError as exc:
        raise MarketCycleRepositoryError("MARKET_CYCLE_CREATE_PUBLISH_FAILED") from exc
    _fsync_directory(cycle_root.parent)


def _atomic_compare_and_replace(path: Path, *, expected: bytes, current: bytes) -> None:
    actual = _read_regular_bytes(
        path, missing_code="MARKET_CYCLE_STATE_HEAD_MISSING"
    )
    if actual != expected:
        raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_CAS_CONFLICT")

    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(8)}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(current)
            handle.flush()
            os.fsync(handle.fileno())
        if _read_regular_bytes(
            path, missing_code="MARKET_CYCLE_STATE_HEAD_MISSING"
        ) != expected:
            raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_CAS_CONFLICT")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _lock_for(key: str) -> threading.RLock:
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[key] = lock
        return lock


class FileCycleRepository:
    """Canonical create-only repository rooted at one configured directory."""

    def __init__(
        self,
        root: Path | str,
        *,
        raw_capture_verifier: RawCaptureReferenceVerifier | None = None,
    ) -> None:
        self.root = Path(root)
        if raw_capture_verifier is not None and not callable(
            getattr(raw_capture_verifier, "verify_reference", None)
        ):
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_RAW_CAPTURE_VERIFIER_INVALID"
            )
        self._raw_capture_verifier = raw_capture_verifier

    def _cycle_root(self, cycle_id: str) -> Path:
        return self.root / _cycle_id(cycle_id)

    def _existing_cycle_root(self, cycle_id: str, *, missing_code: str) -> Path:
        cycle_root = self._cycle_root(cycle_id)
        try:
            metadata = cycle_root.lstat()
        except FileNotFoundError as exc:
            raise MarketCycleRepositoryError(missing_code) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise MarketCycleRepositoryError("MARKET_CYCLE_DIRECTORY_UNSAFE")
        return cycle_root

    def list_cycle_ids(self) -> tuple[str, ...]:
        """List cycles that own controller state, excluding raw-only captures.

        The shared ``cycles/`` root also contains raw capture directories.  A
        setup capture can therefore exist without ever becoming a market-cycle
        state machine.  Treating that directory as a damaged prior Decision
        makes Review continuity depend on unrelated raw storage.  A directory
        becomes enumerable here only after its ``state/`` owner exists; once
        that owner exists, a missing or unsafe head remains a fail-closed
        repository error.
        """

        try:
            root_metadata = self.root.lstat()
        except FileNotFoundError:
            return ()
        if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(
            root_metadata.st_mode
        ):
            raise MarketCycleRepositoryError("MARKET_CYCLE_ROOT_UNSAFE")
        cycle_ids: list[str] = []
        for candidate in self.root.iterdir():
            if _IDENTIFIER_RE.fullmatch(candidate.name) is None:
                continue
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise MarketCycleRepositoryError("MARKET_CYCLE_DIRECTORY_UNSAFE")
            state_root = candidate / "state"
            try:
                state_metadata = state_root.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(state_metadata.st_mode) or not stat.S_ISDIR(
                state_metadata.st_mode
            ):
                raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_DIRECTORY_UNSAFE")
            try:
                head_metadata = (candidate / _STATE_HEAD).lstat()
            except FileNotFoundError as exc:
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_STATE_HEAD_MISSING"
                ) from exc
            if stat.S_ISLNK(head_metadata.st_mode) or not stat.S_ISREG(
                head_metadata.st_mode
            ):
                raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_HEAD_UNSAFE")
            cycle_ids.append(candidate.name)
        return tuple(sorted(cycle_ids))

    @contextmanager
    def locked(self, cycle_id: str) -> Iterator[None]:
        """Hold the one inter-thread/inter-process lock for a cycle."""

        safe_cycle_id = _cycle_id(cycle_id)
        key = f"{self.root.absolute()}::{safe_cycle_id}"
        process_lock = _lock_for(key)
        process_lock.acquire()
        held = getattr(_THREAD_LOCK_STATE, "held", None)
        if held is None:
            held = {}
            _THREAD_LOCK_STATE.held = held
        try:
            existing = held.get(key)
            if existing is not None:
                descriptor, depth = existing
                held[key] = (descriptor, depth + 1)
                try:
                    yield
                finally:
                    held[key] = (descriptor, depth)
                return

            _ensure_directory(self.root)
            lock_directory = self.root / ".locks"
            _ensure_directory(lock_directory)
            lock_path = lock_directory / f"{safe_cycle_id}.lock"
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(lock_path, flags, 0o600)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                os.close(descriptor)
                raise MarketCycleRepositoryError("MARKET_CYCLE_LOCK_FILE_UNSAFE")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            held[key] = (descriptor, 1)
            try:
                yield
            finally:
                held.pop(key, None)
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
        finally:
            process_lock.release()

    def create(self, request: CycleRequest) -> RunState:
        """Create a cycle request and revision-zero state, idempotently."""

        cycle_id = _cycle_id(request.cycle_id)
        initial = RunState(
            cycle_id=cycle_id,
            stage="REQUESTED",
            revision=0,
            artifact_refs=(),
            next_action="CAPTURE_INPUT",
            terminal=False,
            failure_reason=None,
            theory_identity=request.theory_identity,
        )
        request_payload = canonical_bytes(request.to_dict())
        initial_payload = canonical_bytes(initial.to_dict())

        with self.locked(cycle_id):
            cycle_root = self._cycle_root(cycle_id)
            try:
                metadata = cycle_root.lstat()
            except FileNotFoundError:
                staging = _stage_initial_cycle(
                    self.root,
                    cycle_id=cycle_id,
                    request_payload=request_payload,
                    initial_payload=initial_payload,
                )
                try:
                    _publish_cycle_directory(staging, cycle_root)
                finally:
                    _discard_staging_directory(staging)
                return initial
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise MarketCycleRepositoryError("MARKET_CYCLE_DIRECTORY_UNSAFE")
            persisted_request = self.load_request(cycle_id)
            if canonical_bytes(persisted_request.to_dict()) != request_payload:
                raise MarketCycleRepositoryError("MARKET_CYCLE_CREATE_REQUEST_CONFLICT")
            return self.load_state(cycle_id)

    def load_request(self, cycle_id: str) -> CycleRequest:
        """Read and validate the frozen request without creating any path."""

        safe_cycle_id = _cycle_id(cycle_id)
        cycle_root = self._existing_cycle_root(
            safe_cycle_id, missing_code="MARKET_CYCLE_REQUEST_MISSING"
        )
        value, _ = _read_canonical_mapping(
            cycle_root / _REQUEST_PATH,
            missing_code="MARKET_CYCLE_REQUEST_MISSING",
        )
        try:
            request = CycleRequest.from_dict(value)
        except ValueError as exc:
            raise MarketCycleRepositoryError("MARKET_CYCLE_REQUEST_INVALID") from exc
        if request.cycle_id != safe_cycle_id:
            raise MarketCycleRepositoryError("MARKET_CYCLE_REQUEST_ID_MISMATCH")
        return request

    def _load_state_document(self, cycle_id: str) -> tuple[RunState, bytes]:
        cycle_root = self._existing_cycle_root(
            cycle_id, missing_code="MARKET_CYCLE_STATE_HEAD_MISSING"
        )
        value, head_raw = _read_canonical_mapping(
            cycle_root / _STATE_HEAD,
            missing_code="MARKET_CYCLE_STATE_HEAD_MISSING",
        )
        try:
            state = RunState.from_dict(value)
        except ValueError as exc:
            raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_INVALID") from exc
        if state.cycle_id != cycle_id:
            raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_ID_MISMATCH")
        history_raw = _read_regular_bytes(
            cycle_root / _history_relative_path(state.revision),
            missing_code="MARKET_CYCLE_STATE_HISTORY_MISSING",
        )
        if history_raw != head_raw:
            raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_HISTORY_DRIFT")
        return state, head_raw

    def _read_artifact_ref(
        self, cycle_id: str, reference: ArtifactRef
    ) -> dict[str, Any]:
        artifact_type = _artifact_type(reference.artifact_type)
        expected_path = _artifact_relative_path(artifact_type).as_posix()
        if reference.path != expected_path:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_PATH_MISMATCH")
        value, raw = _read_canonical_mapping(
            self._existing_cycle_root(
                cycle_id, missing_code="MARKET_CYCLE_ARTIFACT_MISSING"
            )
            / reference.path,
            missing_code="MARKET_CYCLE_ARTIFACT_MISSING",
        )
        if len(raw) != reference.size_bytes or _sha256(raw) != reference.sha256:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_REF_MISMATCH")
        model = _ARTIFACT_MODEL[artifact_type]
        try:
            artifact = model.from_dict(value)
        except ValueError as exc:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_INVALID") from exc
        model_type, identifier_field = _ARTIFACT_SPEC[type(artifact)]
        if model_type != artifact_type or getattr(artifact, identifier_field) != reference.artifact_id:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_ID_MISMATCH")
        if artifact.cycle_id != cycle_id:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_CYCLE_MISMATCH")
        self._verify_nested_raw_refs(cycle_id, artifact)
        return value

    def _verify_nested_raw_refs(self, cycle_id: str, artifact: object) -> None:
        """Fail closed when a snapshot/outcome no longer binds its raw bytes."""

        if not isinstance(artifact, (InputSnapshot, Outcome)):
            return
        verifier = self._raw_capture_verifier
        if verifier is None:
            return
        for reference in artifact.raw_refs:
            try:
                verifier.verify_reference(
                    cycle_id=cycle_id,
                    reference=reference.to_dict(),
                )
            except RawCaptureError as exc:
                code = (
                    "MARKET_CYCLE_RAW_CAPTURE_MISSING"
                    if str(exc) == "RAW_CAPTURE_REFERENCE_MISSING"
                    else "MARKET_CYCLE_RAW_CAPTURE_INVALID"
                )
                raise MarketCycleRepositoryError(code) from exc
            except (OSError, TypeError, ValueError) as exc:
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_RAW_CAPTURE_INVALID"
                ) from exc

    def load_state(self, cycle_id: str) -> RunState:
        """Read the state head, history copy, request, and referenced artifacts."""

        safe_cycle_id = _cycle_id(cycle_id)
        state, _ = self._load_state_document(safe_cycle_id)
        request = self.load_request(safe_cycle_id)
        if request.theory_identity != state.theory_identity:
            raise MarketCycleRepositoryError("MARKET_CYCLE_THEORY_IDENTITY_DRIFT")
        for reference in state.artifact_refs:
            self._read_artifact_ref(safe_cycle_id, reference)
        return state

    def status(self, cycle_id: str) -> RunState | None:
        """Return current state or ``None``; never materialize a missing cycle."""

        safe_cycle_id = _cycle_id(cycle_id)
        cycle_root = self._cycle_root(safe_cycle_id)
        try:
            metadata = cycle_root.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise MarketCycleRepositoryError("MARKET_CYCLE_DIRECTORY_UNSAFE")
        head = cycle_root / _STATE_HEAD
        try:
            head.lstat()
        except FileNotFoundError:
            return None
        return self.load_state(safe_cycle_id)

    def load_artifact(self, cycle_id: str, artifact_type: str) -> Mapping[str, Any]:
        """Load one referenced business artifact without creating any path."""

        safe_cycle_id = _cycle_id(cycle_id)
        safe_artifact_type = _artifact_type(artifact_type)
        state, _ = self._load_state_document(safe_cycle_id)
        reference = next(
            (
                item
                for item in state.artifact_refs
                if item.artifact_type == safe_artifact_type
            ),
            None,
        )
        if reference is None:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_NOT_REFERENCED")
        return self._read_artifact_ref(safe_cycle_id, reference)

    def _prepare_artifact(
        self,
        cycle_id: str,
        artifact: object,
        existing_references: Sequence[ArtifactRef],
    ) -> tuple[ArtifactRef, Path, bytes]:
        specification = _ARTIFACT_SPEC.get(type(artifact))
        if specification is None:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_OBJECT_UNSUPPORTED")
        artifact_type, identifier_field = specification
        if getattr(artifact, "cycle_id") != cycle_id:
            raise MarketCycleRepositoryError("MARKET_CYCLE_ARTIFACT_CYCLE_MISMATCH")
        reference_by_type = {
            reference.artifact_type: reference for reference in existing_references
        }
        required_predecessors: tuple[tuple[str, ArtifactRef], ...]
        if isinstance(artifact, HypothesisRecord):
            required_predecessors = (
                ("InputSnapshot", artifact.input_snapshot_ref),
            )
        elif isinstance(artifact, BehaviorPlan):
            required_predecessors = (
                ("HypothesisRecord", artifact.hypothesis_record_ref),
            )
        elif isinstance(artifact, Outcome):
            required_predecessors = (
                ("BehaviorPlan", artifact.behavior_plan_ref),
            )
        elif isinstance(artifact, Review):
            required_predecessors = (
                ("BehaviorPlan", artifact.behavior_plan_ref),
                ("Outcome", artifact.outcome_ref),
            )
        else:
            required_predecessors = ()
        for predecessor_type, supplied_reference in required_predecessors:
            if reference_by_type.get(predecessor_type) != supplied_reference:
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_ARTIFACT_PREDECESSOR_REF_MISMATCH"
                )

        def predecessor(artifact_type: str) -> object:
            reference = reference_by_type[artifact_type]
            value = self._read_artifact_ref(cycle_id, reference)
            try:
                return _ARTIFACT_MODEL[artifact_type].from_dict(value)
            except ValueError as exc:
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_ARTIFACT_PREDECESSOR_INVALID"
                ) from exc

        if isinstance(artifact, HypothesisRecord):
            snapshot = predecessor("InputSnapshot")
            assert isinstance(snapshot, InputSnapshot)
            if (
                artifact.decision_at != snapshot.decision_at
                or artifact.outcome_horizon_seconds
                != snapshot.outcome_horizon_seconds
                or artifact.outcome_tolerance_seconds
                != snapshot.outcome_tolerance_seconds
                or artifact.lawful_actions != snapshot.lawful_actions
                or artifact.theory_identity != snapshot.theory_identity
                or not set(snapshot.unknowns).issubset(
                    artifact.unresolved_unknowns
                )
            ):
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_HYPOTHESIS_SNAPSHOT_CONTENT_MISMATCH"
                )
        elif isinstance(artifact, BehaviorPlan):
            record = predecessor("HypothesisRecord")
            assert isinstance(record, HypothesisRecord)
            if (
                artifact.decision_at != record.decision_at
                or artifact.agent_delivered_at != record.agent_delivered_at
                or artifact.agent_request_sha256 != record.agent_request_sha256
                or artifact.agent_delivery_path != record.agent_delivery_path
                or artifact.agent_delivery_sha256 != record.agent_delivery_sha256
                or artifact.agent_decision_text != record.agent_decision_text
                or artifact.agent_decision_size_bytes
                != record.agent_decision_size_bytes
                or artifact.agent_decision_sha256
                != record.agent_decision_sha256
                or artifact.projection_status != record.projection_status
                or artifact.projection_reason != record.projection_reason
                or artifact.hypothesis_index != record.hypothesis_index
                or artifact.agent_action_text != record.agent_action_text
                or artifact.agent_position_text != record.agent_position_text
                or artifact.outcome_due_at
                != (
                    datetime.fromisoformat(
                        record.decision_at.replace("Z", "+00:00")
                    )
                    + timedelta(seconds=record.outcome_horizon_seconds)
                ).isoformat()
                or artifact.outcome_tolerance_seconds
                != record.outcome_tolerance_seconds
                or artifact.theory_identity != record.theory_identity
            ):
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_PLAN_AGENT_DECISION_CONTENT_MISMATCH"
                )
        elif isinstance(artifact, Outcome):
            plan = predecessor("BehaviorPlan")
            assert isinstance(plan, BehaviorPlan)
            if (
                artifact.due_at != plan.outcome_due_at
                or artifact.tolerance_seconds
                != plan.outcome_tolerance_seconds
                or artifact.theory_identity != plan.theory_identity
            ):
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_OUTCOME_PLAN_CONTENT_MISMATCH"
                )
        elif isinstance(artifact, Review):
            plan = predecessor("BehaviorPlan")
            outcome = predecessor("Outcome")
            assert isinstance(plan, BehaviorPlan)
            assert isinstance(outcome, Outcome)
            expected_facts = {
                "outcome_status": outcome.terminal_status,
                "typed_missing": outcome.typed_missing,
                "endpoint_observation": outcome.endpoint_observation,
                "path_observations": outcome.path_observations,
                "outcome_raw_refs": [
                    reference.to_dict() for reference in outcome.raw_refs
                ],
            }
            if (
                artifact.outcome_status != outcome.terminal_status
                or artifact.agent_decision_sha256
                != plan.agent_decision_sha256
                or artifact.projection_status != plan.projection_status
                or artifact.projection_reason != plan.projection_reason
                or canonical_bytes(artifact.system_facts)
                != canonical_bytes(expected_facts)
                or artifact.theory_identity != plan.theory_identity
                or artifact.theory_identity != outcome.theory_identity
            ):
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_REVIEW_SOURCE_CONTENT_MISMATCH"
                )
        self._verify_nested_raw_refs(cycle_id, artifact)
        artifact_id = getattr(artifact, identifier_field)
        relative_path = _artifact_relative_path(artifact_type)
        payload = canonical_bytes(artifact.to_dict())
        reference = ArtifactRef(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            path=relative_path.as_posix(),
            size_bytes=len(payload),
            sha256=_sha256(payload),
        )
        return reference, self._cycle_root(cycle_id) / relative_path, payload

    def _build_transition_intent(
        self,
        *,
        cycle_id: str,
        expected: RunState,
        expected_head: bytes,
        current: RunState,
        prepared_artifacts: Sequence[tuple[ArtifactRef, Path, bytes]],
    ) -> bytes:
        artifacts: list[dict[str, object]] = []
        for reference, _, payload in prepared_artifacts:
            try:
                artifact_payload = loads_json_strict(payload)
            except CanonicalContractError as exc:  # pragma: no cover - internal invariant
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_TRANSITION_INTENT_BUILD_FAILED"
                ) from exc
            artifacts.append(
                {
                    "ref": reference.to_dict(),
                    "payload": artifact_payload,
                }
            )

        current_payload = canonical_bytes(current.to_dict())
        return canonical_bytes(
            {
                "schema_id": _TRANSITION_INTENT_SCHEMA_ID,
                "schema_version": _TRANSITION_INTENT_SCHEMA_VERSION,
                "cycle_id": cycle_id,
                "expected_head": {
                    "revision": expected.revision,
                    "size_bytes": len(expected_head),
                    "sha256": _sha256(expected_head),
                },
                "current_state": current.to_dict(),
                "current_state_sha256": _sha256(current_payload),
                "artifacts": artifacts,
            }
        )

    def _decode_transition_intent(
        self,
        *,
        cycle_id: str,
        expected: RunState,
        expected_head: bytes,
        intent: Mapping[str, Any],
    ) -> tuple[RunState, tuple[tuple[ArtifactRef, Path, bytes], ...], bytes]:
        document = _require_exact_keys(
            intent,
            expected=frozenset(
                {
                    "schema_id",
                    "schema_version",
                    "cycle_id",
                    "expected_head",
                    "current_state",
                    "current_state_sha256",
                    "artifacts",
                }
            ),
            error_code="MARKET_CYCLE_TRANSITION_INTENT_INVALID",
        )
        if (
            document["schema_id"] != _TRANSITION_INTENT_SCHEMA_ID
            or document["schema_version"] != _TRANSITION_INTENT_SCHEMA_VERSION
            or document["cycle_id"] != cycle_id
        ):
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_IDENTITY_MISMATCH"
            )

        expected_document = _require_exact_keys(
            document["expected_head"],
            expected=frozenset({"revision", "size_bytes", "sha256"}),
            error_code="MARKET_CYCLE_TRANSITION_INTENT_INVALID",
        )
        if (
            type(expected_document["revision"]) is not int
            or type(expected_document["size_bytes"]) is not int
            or not isinstance(expected_document["sha256"], str)
        ):
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_INVALID"
            )
        if expected_document["revision"] != expected.revision:
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_REVISION_MISMATCH"
            )
        if (
            expected_document["size_bytes"] != len(expected_head)
            or expected_document["sha256"] != _sha256(expected_head)
        ):
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_HEAD_MISMATCH"
            )

        current_document = _require_exact_keys(
            document["current_state"],
            expected=frozenset(
                {
                    "cycle_id",
                    "stage",
                    "revision",
                    "artifact_refs",
                    "next_action",
                    "terminal",
                    "failure_reason",
                    "theory_identity",
                }
            ),
            error_code="MARKET_CYCLE_TRANSITION_INTENT_INVALID",
        )
        try:
            current = RunState.from_dict(current_document)
            validate_run_state_transition(expected, current)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_STATE_INVALID"
            ) from exc
        current_payload = canonical_bytes(current.to_dict())
        if (
            canonical_bytes(current_document) != current_payload
            or document["current_state_sha256"] != _sha256(current_payload)
        ):
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_STATE_DIGEST_MISMATCH"
            )

        artifact_documents = document["artifacts"]
        if not isinstance(artifact_documents, list):
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_ARTIFACTS_INVALID"
            )
        prepared: list[tuple[ArtifactRef, Path, bytes]] = []
        for artifact_document in artifact_documents:
            entry = _require_exact_keys(
                artifact_document,
                expected=frozenset({"ref", "payload"}),
                error_code="MARKET_CYCLE_TRANSITION_INTENT_ARTIFACT_INVALID",
            )
            reference_document = _require_exact_keys(
                entry["ref"],
                expected=frozenset(
                    {"artifact_type", "artifact_id", "path", "size_bytes", "sha256"}
                ),
                error_code="MARKET_CYCLE_TRANSITION_INTENT_ARTIFACT_INVALID",
            )
            payload_document = entry["payload"]
            if not isinstance(payload_document, Mapping):
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_TRANSITION_INTENT_ARTIFACT_INVALID"
                )
            try:
                reference = ArtifactRef.from_dict(reference_document)
                artifact_type = _artifact_type(reference.artifact_type)
                artifact = _ARTIFACT_MODEL[artifact_type].from_dict(payload_document)
                recomputed = self._prepare_artifact(
                    cycle_id, artifact, expected.artifact_refs
                )
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_TRANSITION_INTENT_ARTIFACT_INVALID"
                ) from exc
            if (
                reference != recomputed[0]
                or canonical_bytes(payload_document) != recomputed[2]
            ):
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_TRANSITION_INTENT_ARTIFACT_REF_MISMATCH"
                )
            prepared.append(recomputed)

        new_references = tuple(item[0] for item in prepared)
        if current.artifact_refs != expected.artifact_refs + new_references:
            raise MarketCycleRepositoryError(
                "MARKET_CYCLE_TRANSITION_INTENT_ARTIFACT_SET_MISMATCH"
            )
        return current, tuple(prepared), current_payload

    def _apply_transition_intent(
        self,
        *,
        cycle_id: str,
        expected: RunState,
        expected_head: bytes,
        intent: Mapping[str, Any],
    ) -> RunState:
        current, prepared_artifacts, current_payload = self._decode_transition_intent(
            cycle_id=cycle_id,
            expected=expected,
            expected_head=expected_head,
            intent=intent,
        )
        history_path = (
            self._cycle_root(cycle_id) / _history_relative_path(current.revision)
        )
        for _, path, payload in prepared_artifacts:
            _require_write_once_compatible(path, payload)
        _require_write_once_compatible(history_path, current_payload)

        for _, path, payload in prepared_artifacts:
            _write_once(path, payload)
        _write_once(history_path, current_payload)
        _atomic_compare_and_replace(
            self._cycle_root(cycle_id) / _STATE_HEAD,
            expected=expected_head,
            current=current_payload,
        )
        return current

    def recover_pending(self, cycle_id: str) -> RunState | None:
        """Complete the next durable transition intent, if one exists."""

        safe_cycle_id = _cycle_id(cycle_id)
        with self.locked(safe_cycle_id):
            expected, expected_head = self._load_state_document(safe_cycle_id)
            for reference in expected.artifact_refs:
                self._read_artifact_ref(safe_cycle_id, reference)
            request = self.load_request(safe_cycle_id)
            if request.theory_identity != expected.theory_identity:
                raise MarketCycleRepositoryError(
                    "MARKET_CYCLE_THEORY_IDENTITY_DRIFT"
                )

            intent_path = self._cycle_root(safe_cycle_id) / _intent_relative_path(
                expected.revision + 1
            )
            try:
                intent_path.lstat()
            except FileNotFoundError:
                return None
            intent, _ = _read_canonical_mapping(
                intent_path,
                missing_code="MARKET_CYCLE_TRANSITION_INTENT_MISSING",
            )
            return self._apply_transition_intent(
                cycle_id=safe_cycle_id,
                expected=expected,
                expected_head=expected_head,
                intent=intent,
            )

    def transition(
        self,
        *,
        expected: RunState,
        artifacts: Sequence[
            InputSnapshot | HypothesisRecord | BehaviorPlan | Outcome | Review
        ],
        next_stage: str,
        next_action: str | None,
        terminal: bool = False,
        failure_reason: str | None = None,
    ) -> RunState:
        """Persist one Application-selected transition with a state-head CAS."""

        cycle_id = _cycle_id(expected.cycle_id)
        with self.locked(cycle_id):
            self._existing_cycle_root(
                cycle_id, missing_code="MARKET_CYCLE_STATE_HEAD_MISSING"
            )
            persisted, expected_head = self._load_state_document(cycle_id)
            for reference in persisted.artifact_refs:
                self._read_artifact_ref(cycle_id, reference)
            if canonical_bytes(persisted.to_dict()) != canonical_bytes(expected.to_dict()):
                raise MarketCycleRepositoryError("MARKET_CYCLE_STATE_CAS_CONFLICT")
            request = self.load_request(cycle_id)
            if request.theory_identity != expected.theory_identity:
                raise MarketCycleRepositoryError("MARKET_CYCLE_THEORY_IDENTITY_DRIFT")

            prepared_artifacts = tuple(
                self._prepare_artifact(
                    cycle_id, artifact, expected.artifact_refs
                )
                for artifact in artifacts
            )
            new_references = tuple(item[0] for item in prepared_artifacts)
            current = RunState(
                cycle_id=cycle_id,
                stage=next_stage,
                revision=expected.revision + 1,
                artifact_refs=expected.artifact_refs + new_references,
                next_action=next_action,
                terminal=terminal,
                failure_reason=failure_reason,
                theory_identity=expected.theory_identity,
            )
            validate_run_state_transition(expected, current)

            current_payload = canonical_bytes(current.to_dict())
            history_path = (
                self._cycle_root(cycle_id)
                / _history_relative_path(current.revision)
            )
            for _, path, payload in prepared_artifacts:
                _require_write_once_compatible(path, payload)
            _require_write_once_compatible(history_path, current_payload)
            intent_path = self._cycle_root(cycle_id) / _intent_relative_path(
                current.revision
            )
            intent_payload = self._build_transition_intent(
                cycle_id=cycle_id,
                expected=expected,
                expected_head=expected_head,
                current=current,
                prepared_artifacts=prepared_artifacts,
            )
            _require_write_once_compatible(intent_path, intent_payload)

            _write_once(intent_path, intent_payload)
            persisted_intent, _ = _read_canonical_mapping(
                intent_path,
                missing_code="MARKET_CYCLE_TRANSITION_INTENT_MISSING",
            )
            return self._apply_transition_intent(
                cycle_id=cycle_id,
                expected=expected,
                expected_head=expected_head,
                intent=persisted_intent,
            )


__all__ = ["FileCycleRepository", "MarketCycleRepositoryError"]
