"""Write-once/CAS persistence for the V3.2 tick supervisor.

The domain supervisor owns transition rules.  This adapter owns only local
durability: every checkpoint revision, permit, completion receipt and failure
is written once; only the small current-checkpoint pointer is atomically
replaced.  It has no network, Agent, account, order, fill or PnL capability.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ..v32_durable_json import (
    atomic_replace_json,
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID,
    EXPIRY_PERMIT_SCHEMA_ID,
    FAILURE_DIGEST_FIELD,
    FAILURE_SCHEMA_ID,
    PERMIT_DIGEST_FIELD,
    PERMIT_SCHEMA_ID,
    V32TickSupervisorError,
    build_v32_tick_supervisor_failure,
    complete_v32_analysis_tick,
    complete_v32_outcome_tick,
    complete_v32_outcome_window_expiry,
    fail_v32_tick_supervisor,
    open_v32_tick_supervisor_permit,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_failure,
    verify_v32_tick_supervisor_permit,
    verify_v32_tick_supervisor_transition,
)
from ..domain.v32_outcome_tick import build_v32_outcome_tick_attempt
from ..domain.v32_outcome_window_expiry import EXPIRY_TERMINAL_DIGEST_FIELD


class V32TickSupervisorStoreError(ValueError):
    """A durable supervisor-store invariant failed closed."""


STORE_ROOT = "v32-tick-supervisor-v1"
COMPLETION_SCHEMA_ID = "theory_paper_v32_tick_supervisor_completion_v1"
COMPLETION_DIGEST_FIELD = "tick_supervisor_completion_digest"
SCHEMA_VERSION = "1.0.0"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}

_ANALYSIS_COMPLETION_FIELDS_V1 = frozenset(
    {
        "schedule_sets_before",
        "new_schedule_set",
        "accepted_state_digest",
        "shadow_decision_bundle_digest",
        "source_admission_digest",
        "source_admission_physical_sha256",
        "proposal_lifecycle_digest",
        "selection_lifecycle_digest",
        "final_action_plan_digest",
        "commit_envelope_digest",
        "new_research_checkpoint_digest",
        "new_outcome_checkpoint_digest",
        "new_timeframe_cache_digest",
        "new_dynamic_state_digest",
        "completed_at",
    }
)
_ANALYSIS_COMPLETION_FIELDS_V2 = frozenset(
    {
        *_ANALYSIS_COMPLETION_FIELDS_V1,
        "source_admission_schema_version",
        "decision_sealed_at",
    }
)
_OUTCOME_COMPLETION_FIELDS = frozenset(
    {
        "tick_attempt",
        "observation_tick",
        "schedule_sets",
        "prior_terminal_receipts",
        "batch_intent",
        "outcome_receipts",
        "batch_completion",
        "new_outcome_checkpoint_digest",
        "completed_at",
    }
)
_EXPIRY_COMPLETION_FIELDS = frozenset(
    {
        "schedule_sets",
        "expiry_terminal",
        "new_outcome_checkpoint_digest",
        "completed_at",
    }
)
_COMPLETION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "permit_kind",
        "permit_digest",
        "checkpoint_before_completion_digest",
        "checkpoint_after_completion_digest",
        "substore_checkpoint_digest",
        "accepted_state_digest",
        "shadow_decision_bundle_digest",
        "batch_completion_digest",
        "completed_at",
        "single_state_change_boundary",
        "source_scope",
        "external_execution_authority",
        "executable",
        COMPLETION_DIGEST_FIELD,
    }
)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32TickSupervisorStoreError(code)
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32TickSupervisorStoreError(code)
    return value


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    atomic_replace_json(
        path,
        document,
        short_write_error="V32_SUPERVISOR_CHECKPOINT_SHORT_WRITE",
    )


def _load_canonical_json(path: Path) -> Mapping[str, Any]:
    document = load_json_strict(path)
    if path.read_bytes() != canonical_bytes(dict(document)) + b"\n":
        raise V32TickSupervisorStoreError(
            "V32_SUPERVISOR_STORE_NONCANONICAL_FILE"
        )
    return document


def _completion_receipt(
    *,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    permit: Mapping[str, Any],
    completion: Mapping[str, Any],
) -> dict[str, Any]:
    kind = permit["permit_kind"]
    accepted_state_digest = (
        _digest(
            completion["accepted_state_digest"],
            "V32_SUPERVISOR_STORE_ACCEPTED_STATE_INVALID",
        )
        if kind == "ANALYSIS_TICK"
        else None
    )
    shadow_decision_bundle_digest = (
        _digest(
            completion["shadow_decision_bundle_digest"],
            "V32_SUPERVISOR_STORE_SHADOW_DECISION_INVALID",
        )
        if kind == "ANALYSIS_TICK"
        else None
    )
    batch_completion_digest = (
        _digest(
            completion["batch_completion"]["outcome_resolution_batch_digest"],
            "V32_SUPERVISOR_STORE_BATCH_COMPLETION_INVALID",
        )
        if kind == "OUTCOME_TICK"
        else _digest(
            completion["expiry_terminal"][EXPIRY_TERMINAL_DIGEST_FIELD],
            "V32_SUPERVISOR_STORE_BATCH_COMPLETION_INVALID",
        )
        if kind == "OUTCOME_WINDOW_EXPIRY"
        else None
    )
    substore_digest = _digest(
        completion[
            "new_research_checkpoint_digest"
            if kind == "ANALYSIS_TICK"
            else "new_outcome_checkpoint_digest"
        ],
        "V32_SUPERVISOR_STORE_SUBSTORE_CHECKPOINT_INVALID",
    )
    return self_digest(
        {
            "schema_id": COMPLETION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": before["run_id"],
            "permit_kind": kind,
            "permit_digest": permit[PERMIT_DIGEST_FIELD],
            "checkpoint_before_completion_digest": before[
                CHECKPOINT_DIGEST_FIELD
            ],
            "checkpoint_after_completion_digest": after[
                CHECKPOINT_DIGEST_FIELD
            ],
            "substore_checkpoint_digest": substore_digest,
            "accepted_state_digest": accepted_state_digest,
            "shadow_decision_bundle_digest": shadow_decision_bundle_digest,
            "batch_completion_digest": batch_completion_digest,
            "completed_at": completion["completed_at"],
            "single_state_change_boundary": True,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        COMPLETION_DIGEST_FIELD,
    )


def verify_v32_tick_supervisor_completion(
    document: Mapping[str, Any],
) -> str:
    if (
        not isinstance(document, Mapping)
        or set(document) != _COMPLETION_RECEIPT_FIELDS
        or document.get("schema_id") != COMPLETION_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("permit_kind")
        not in {"ANALYSIS_TICK", "OUTCOME_TICK", "OUTCOME_WINDOW_EXPIRY"}
        or document.get("single_state_change_boundary") is not True
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
    ):
        raise V32TickSupervisorStoreError(
            "V32_SUPERVISOR_STORE_COMPLETION_INVALID"
        )
    try:
        supplied = verify_self_digest(document, COMPLETION_DIGEST_FIELD)
        for field in (
            "permit_digest",
            "checkpoint_before_completion_digest",
            "checkpoint_after_completion_digest",
            "substore_checkpoint_digest",
        ):
            _digest(document.get(field), "V32_SUPERVISOR_STORE_COMPLETION_INVALID")
        kind = document["permit_kind"]
        if (kind == "ANALYSIS_TICK") != (
            document.get("accepted_state_digest") is not None
        ) or (kind == "ANALYSIS_TICK") != (
            document.get("shadow_decision_bundle_digest") is not None
        ) or (kind in {"OUTCOME_TICK", "OUTCOME_WINDOW_EXPIRY"}) != (
            document.get("batch_completion_digest") is not None
        ):
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_COMPLETION_INVALID"
            )
        if document.get("accepted_state_digest") is not None:
            _digest(
                document["accepted_state_digest"],
                "V32_SUPERVISOR_STORE_COMPLETION_INVALID",
            )
        if document.get("shadow_decision_bundle_digest") is not None:
            _digest(
                document["shadow_decision_bundle_digest"],
                "V32_SUPERVISOR_STORE_COMPLETION_INVALID",
            )
        if document.get("batch_completion_digest") is not None:
            _digest(
                document["batch_completion_digest"],
                "V32_SUPERVISOR_STORE_COMPLETION_INVALID",
            )
        _text(document.get("run_id"), "V32_SUPERVISOR_STORE_COMPLETION_INVALID")
        _text(document.get("completed_at"), "V32_SUPERVISOR_STORE_COMPLETION_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32TickSupervisorStoreError):
            raise
        raise V32TickSupervisorStoreError(
            "V32_SUPERVISOR_STORE_COMPLETION_INVALID"
        ) from exc
    return supplied


class LocalV32TickSupervisorStore:
    """Durable owner of one run's Supervisor state machine."""

    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root).absolute()
        if supplied.exists() and supplied.is_symlink():
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_ROOT_SYMLINK_FORBIDDEN"
            )
        ensure_directory_tree(supplied)
        if supplied.is_symlink() or not supplied.is_dir():
            raise V32TickSupervisorStoreError("V32_SUPERVISOR_STORE_ROOT_INVALID")
        self.run_root = supplied
        self._physical_root = supplied.resolve(strict=True)
        self.checkpoint_path = self._safe_path(f"{STORE_ROOT}/checkpoint.json")

    def _safe_path(self, relative_ref: str) -> Path:
        if (
            not self.run_root.is_dir()
            or self.run_root.is_symlink()
            or self.run_root.resolve(strict=True) != self._physical_root
        ):
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_ROOT_CHANGED"
            )
        path = PurePosixPath(relative_ref)
        if (
            not isinstance(relative_ref, str)
            or not relative_ref
            or "\\" in relative_ref
            or path.as_posix() != relative_ref
            or path.is_absolute()
            or len(path.parts) < 2
            or path.parts[0] != STORE_ROOT
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise V32TickSupervisorStoreError("V32_SUPERVISOR_STORE_PATH_INVALID")
        current = self.run_root
        try:
            for part in path.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32TickSupervisorStoreError(
                        "V32_SUPERVISOR_STORE_SYMLINK_FORBIDDEN"
                    )
            current.resolve(strict=False).relative_to(self._physical_root)
        except V32TickSupervisorStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_PATH_INVALID"
            ) from exc
        return current

    @contextmanager
    def _lock(self):
        lock_path = self._safe_path(f"{STORE_ROOT}/.locks/store.lock")
        ensure_directory_tree(lock_path.parent)
        lock_path = self._safe_path(f"{STORE_ROOT}/.locks/store.lock")
        key = str(lock_path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(lock_path):
                yield

    def _checkpoint_history_path(self, digest: str) -> Path:
        return self._safe_path(f"{STORE_ROOT}/checkpoints/{digest}.json")

    def _permit_path(self, digest: str) -> Path:
        return self._safe_path(f"{STORE_ROOT}/permits/{digest}.json")

    def _completion_path(self, digest: str) -> Path:
        return self._safe_path(f"{STORE_ROOT}/completions/{digest}.json")

    def _failure_path(self, digest: str) -> Path:
        return self._safe_path(f"{STORE_ROOT}/failures/{digest}.json")

    def initialize_checkpoint(
        self, *, checkpoint: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            digest = verify_v32_tick_supervisor_checkpoint(checkpoint)
        except (TypeError, ValueError) as exc:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_GENESIS_INVALID"
            ) from exc
        if (
            checkpoint.get("schema_id") != CHECKPOINT_SCHEMA_ID
            or checkpoint.get("revision") != 0
            or checkpoint.get("predecessor_checkpoint_digest") is not None
        ):
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_GENESIS_INVALID"
            )
        with self._lock():
            if self.checkpoint_path.exists():
                current = self.load_checkpoint(
                    run_id=str(checkpoint["run_id"]), _already_locked=True
                )
                if dict(current) != dict(checkpoint):
                    raise V32TickSupervisorStoreError(
                        "V32_SUPERVISOR_STORE_INITIALIZATION_CONFLICT"
                    )
                confirm_existing_json(self._checkpoint_history_path(digest), current)
                confirm_existing_json(self.checkpoint_path, current)
                return current
            write_once_json(self._checkpoint_history_path(digest), checkpoint)
            _atomic_json(self.checkpoint_path, checkpoint)
            return dict(checkpoint)

    def load_checkpoint(
        self, *, run_id: str, _already_locked: bool = False
    ) -> Mapping[str, Any]:
        if not _already_locked:
            with self._lock():
                return self.load_checkpoint(run_id=run_id, _already_locked=True)
        if not self.checkpoint_path.is_file() or self.checkpoint_path.is_symlink():
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_CHECKPOINT_MISSING"
            )
        try:
            document = _load_canonical_json(self.checkpoint_path)
            digest = verify_v32_tick_supervisor_checkpoint(document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_CHECKPOINT_INVALID"
            ) from exc
        if document.get("run_id") != run_id:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_RUN_ID_INVALID"
            )
        history = self._checkpoint_history_path(digest)
        if not history.is_file() or _load_canonical_json(history) != document:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_CHECKPOINT_HISTORY_INVALID"
            )
        try:
            confirm_existing_json(self.checkpoint_path, document)
            confirm_existing_json(history, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_CHECKPOINT_HISTORY_INVALID"
            ) from exc
        return document

    def load_checkpoint_by_digest(
        self, *, run_id: str, checkpoint_digest: str
    ) -> Mapping[str, Any]:
        digest = _digest(
            checkpoint_digest, "V32_SUPERVISOR_STORE_CHECKPOINT_DIGEST_INVALID"
        )
        with self._lock():
            path = self._checkpoint_history_path(digest)
            try:
                document = _load_canonical_json(path)
                supplied = verify_v32_tick_supervisor_checkpoint(document)
            except (OSError, TypeError, ValueError) as exc:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_CHECKPOINT_HISTORY_INVALID"
                ) from exc
            if supplied != digest or document.get("run_id") != run_id:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_CHECKPOINT_HISTORY_INVALID"
                )
            try:
                confirm_existing_json(path, document)
            except (OSError, TypeError, ValueError) as exc:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_CHECKPOINT_HISTORY_INVALID"
                ) from exc
            return document

    def _commit_transition(
        self,
        *,
        current: Mapping[str, Any],
        after: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        expected = _digest(
            expected_checkpoint_digest,
            "V32_SUPERVISOR_STORE_CAS_DIGEST_INVALID",
        )
        if current[CHECKPOINT_DIGEST_FIELD] != expected:
            raise V32TickSupervisorStoreError("V32_SUPERVISOR_STORE_CAS_CONFLICT")
        try:
            digest = verify_v32_tick_supervisor_checkpoint(after)
            verify_v32_tick_supervisor_transition(current, after)
        except (TypeError, ValueError) as exc:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_TRANSITION_INVALID"
            ) from exc
        write_once_json(self._checkpoint_history_path(digest), after)
        latest = self.load_checkpoint(
            run_id=str(current["run_id"]), _already_locked=True
        )
        if latest[CHECKPOINT_DIGEST_FIELD] != expected:
            raise V32TickSupervisorStoreError("V32_SUPERVISOR_STORE_CAS_CONFLICT")
        _atomic_json(self.checkpoint_path, after)
        return dict(after)

    def open_permit(
        self,
        *,
        permit: Mapping[str, Any],
        schedule_sets: Sequence[Mapping[str, Any]],
        expected_checkpoint_digest: str,
        opened_at: str,
    ) -> Mapping[str, Any]:
        with self._lock():
            run_id = _text(
                permit.get("run_id"), "V32_SUPERVISOR_STORE_PERMIT_INVALID"
            )
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_CAS_CONFLICT"
                )
            try:
                tick_attempt = None
                if permit.get("permit_kind") == "OUTCOME_TICK":
                    tick_attempt = build_v32_outcome_tick_attempt(
                        run_id=run_id,
                        tick_index=permit["outcome_tick_index"],
                        planned_tick_at=permit["planned_outcome_tick_at"],
                        reserved_at=permit["issued_at"],
                    )
                permit_digest = verify_v32_tick_supervisor_permit(
                    permit,
                    checkpoint=current,
                    schedule_sets=schedule_sets,
                    tick_attempt=tick_attempt,
                )
                opened = open_v32_tick_supervisor_permit(
                    checkpoint=current,
                    permit=permit,
                    schedule_sets=schedule_sets,
                    updated_at=opened_at,
                    tick_attempt=tick_attempt,
                )
            except (TypeError, ValueError) as exc:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_PERMIT_INVALID"
                ) from exc
            write_once_json(self._permit_path(permit_digest), permit)
            return self._commit_transition(
                current=current,
                after=opened,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )

    def load_permit(
        self, *, run_id: str, permit_digest: str
    ) -> Mapping[str, Any]:
        digest = _digest(
            permit_digest, "V32_SUPERVISOR_STORE_PERMIT_DIGEST_INVALID"
        )
        with self._lock():
            try:
                permit = _load_canonical_json(self._permit_path(digest))
                supplied = verify_self_digest(permit, PERMIT_DIGEST_FIELD)
            except (OSError, TypeError, ValueError) as exc:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_PERMIT_INVALID"
                ) from exc
            if (
                permit.get("schema_id")
                not in {PERMIT_SCHEMA_ID, EXPIRY_PERMIT_SCHEMA_ID}
                or permit.get("run_id") != run_id
                or supplied != digest
            ):
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_PERMIT_INVALID"
                )
            return permit

    def _complete(
        self,
        *,
        permit: Mapping[str, Any],
        completion: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        run_id = _text(
            permit.get("run_id"), "V32_SUPERVISOR_STORE_PERMIT_INVALID"
        )
        current = self.load_checkpoint(run_id=run_id, _already_locked=True)
        if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
            raise V32TickSupervisorStoreError("V32_SUPERVISOR_STORE_CAS_CONFLICT")
        kind = permit.get("permit_kind")
        expected_fields = (
            (
                _ANALYSIS_COMPLETION_FIELDS_V2
                if completion.get("source_admission_schema_version") == "2.0.0"
                else _ANALYSIS_COMPLETION_FIELDS_V1
            )
            if kind == "ANALYSIS_TICK"
            else _OUTCOME_COMPLETION_FIELDS
            if kind == "OUTCOME_TICK"
            else _EXPIRY_COMPLETION_FIELDS
            if kind == "OUTCOME_WINDOW_EXPIRY"
            else frozenset()
        )
        if not isinstance(completion, Mapping) or set(completion) != expected_fields:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_COMPLETION_MATERIAL_INVALID"
            )
        try:
            if kind == "ANALYSIS_TICK":
                after = complete_v32_analysis_tick(
                    checkpoint=current, permit=permit, **completion
                )
            elif kind == "OUTCOME_TICK":
                after = complete_v32_outcome_tick(
                    checkpoint=current, permit=permit, **completion
                )
            else:
                after = complete_v32_outcome_window_expiry(
                    checkpoint=current, permit=permit, **completion
                )
            receipt = _completion_receipt(
                before=current,
                after=after,
                permit=permit,
                completion=completion,
            )
            receipt_digest = verify_v32_tick_supervisor_completion(receipt)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, V32TickSupervisorStoreError):
                raise
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_COMPLETION_INVALID"
            ) from exc
        write_once_json(self._completion_path(receipt_digest), receipt)
        return self._commit_transition(
            current=current,
            after=after,
            expected_checkpoint_digest=expected_checkpoint_digest,
        )

    def complete_analysis_tick(
        self,
        *,
        permit: Mapping[str, Any],
        completion: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        if permit.get("permit_kind") != "ANALYSIS_TICK":
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_LANE_MISMATCH"
            )
        with self._lock():
            return self._complete(
                permit=permit,
                completion=completion,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )

    def complete_outcome_tick(
        self,
        *,
        permit: Mapping[str, Any],
        completion: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]:
        if permit.get("permit_kind") not in {
            "OUTCOME_TICK",
            "OUTCOME_WINDOW_EXPIRY",
        }:
            raise V32TickSupervisorStoreError(
                "V32_SUPERVISOR_STORE_LANE_MISMATCH"
            )
        with self._lock():
            return self._complete(
                permit=permit,
                completion=completion,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )

    def fail_closed(
        self,
        *,
        expected_checkpoint_digest: str,
        failure_lane: str,
        failure_code: str,
        failure_summary: str,
        failure_evidence_digest: str,
        occurred_at: str,
    ) -> Mapping[str, Any]:
        with self._lock():
            if not self.checkpoint_path.is_file():
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_CHECKPOINT_MISSING"
                )
            try:
                current = _load_canonical_json(self.checkpoint_path)
                verify_v32_tick_supervisor_checkpoint(current)
            except (OSError, TypeError, ValueError) as exc:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_CHECKPOINT_INVALID"
                ) from exc
            if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_CAS_CONFLICT"
                )
            try:
                failure = build_v32_tick_supervisor_failure(
                    checkpoint=current,
                    failure_lane=failure_lane,
                    failure_code=failure_code,
                    failure_summary=failure_summary,
                    failure_evidence_digest=failure_evidence_digest,
                    occurred_at=occurred_at,
                )
                failure_digest = verify_v32_tick_supervisor_failure(
                    failure, checkpoint=current
                )
                after = fail_v32_tick_supervisor(
                    checkpoint=current, failure=failure
                )
            except (TypeError, ValueError) as exc:
                raise V32TickSupervisorStoreError(
                    "V32_SUPERVISOR_STORE_FAILURE_INVALID"
                ) from exc
            write_once_json(self._failure_path(failure_digest), failure)
            return self._commit_transition(
                current=current,
                after=after,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )


__all__ = [
    "COMPLETION_DIGEST_FIELD",
    "COMPLETION_SCHEMA_ID",
    "LocalV32TickSupervisorStore",
    "STORE_ROOT",
    "V32TickSupervisorStoreError",
    "verify_v32_tick_supervisor_completion",
]
