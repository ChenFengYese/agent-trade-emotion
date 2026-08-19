"""Durable local adapter for the V3.2 outcome lane.

The adapter joins the recoverable Supervisor coordinator to the existing
raw-first outcome transaction.  One call to :func:`run_v32_outcome_tick` is
treated as one outcome transaction boundary even though that transaction
atomically advances several append-only evidence objects.  A crash is resumed
from the outcome store's verified durable prefix; it never authorizes a second
public request for the same reserved attempt.

This module has no account, credential, order, fill, position, portfolio, or
PnL interface.  Its only external capability is the injected one-call public
mark capture port.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Callable, Mapping

from ..application.v32_outcome_tick_composition import (
    run_v32_outcome_tick,
    run_v32_outcome_window_expiry,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
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
from ..domain.v32_outcome_tick import (
    SCHEDULE_SET_DIGEST_FIELD,
    verify_v32_outcome_observation_tick,
    verify_v32_outcome_resolution_batch,
    verify_v32_outcome_resolution_batch_intent,
    verify_v32_outcome_tick_attempt,
    verify_v32_public_market_outcome_receipt,
)
from ..domain.v32_tick_supervisor import PERMIT_DIGEST_FIELD
from ..domain.v32_outcome_window_expiry import (
    EXPIRY_TERMINAL_DIGEST_FIELD,
    build_v32_outcome_window_expiry_terminal,
    verify_v32_outcome_window_expiry_terminal,
)
from .v32_okx_public_outcome_adapter import V32OkxPublicMarkCaptureAdapter
from .v32_outcome_tick_store import (
    CHECKPOINT_SCHEMA_ID,
    CHECKPOINT_SCHEMA_VERSION,
    EXTERNAL_EXECUTION_AUTHORITY,
    FAILURE_DIGEST_FIELD as OUTCOME_FAILURE_DIGEST_FIELD,
    FAILURE_SCHEMA_ID as OUTCOME_FAILURE_SCHEMA_ID,
    LocalV32OutcomeTickStore,
    SOURCE_SCOPE,
)


STORE_ROOT = "v32-local-outcome-lane-v1"
SCHEMA_VERSION = "1.0.0"
FAILURE_EVIDENCE_SCHEMA_ID = "theory_paper_v32_local_outcome_failure_evidence_v1"
FAILURE_EVIDENCE_DIGEST_FIELD = "local_outcome_failure_evidence_digest"
NOT_DUE_SCHEMA_ID = "theory_paper_v32_local_outcome_not_due_receipt_v1"
NOT_DUE_DIGEST_FIELD = "local_outcome_not_due_receipt_digest"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}

_COMPLETION_FIELDS = frozenset(
    {"permit_digest", "batch_completion_digest", "completion"}
)
_FAILURE_FIELDS = frozenset(
    {
        "permit_digest",
        "failure_summary",
        "failure_evidence_digest",
        "occurred_at",
    }
)
_FAILURE_EVIDENCE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "permit_digest",
        "failure_code",
        "failure_summary",
        "failure_class",
        "failure_message",
        "outcome_checkpoint_digest",
        "outcome_failure_digest",
        "occurred_at",
        "retry_allowed",
        "resume_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        FAILURE_EVIDENCE_DIGEST_FIELD,
    }
)
_NOT_DUE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "tick_index",
        "permit_digest",
        "outcome_checkpoint_digest",
        "observed_status",
        "network_request_count",
        "terminal_state_created",
        "retry_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        NOT_DUE_DIGEST_FIELD,
    }
)


class V32LocalOutcomeLaneError(ValueError):
    """The concrete local outcome lane failed closed."""


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32LocalOutcomeLaneError(code)
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32LocalOutcomeLaneError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32LocalOutcomeLaneError(code) from exc
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat().replace(
        "+00:00", "Z"
    ) != text:
        raise V32LocalOutcomeLaneError(code)
    return text


def _later_time(left: str, right: str) -> str:
    left_value = datetime.fromisoformat(
        _time(left, "V32_LOCAL_OUTCOME_TIME_INVALID").replace("Z", "+00:00")
    )
    right_value = datetime.fromisoformat(
        _time(right, "V32_LOCAL_OUTCOME_TIME_INVALID").replace("Z", "+00:00")
    )
    return left if left_value >= right_value else right


class LocalV32OutcomeLane:
    """Concrete ``V32OutcomeLanePort`` backed by the local V3.2 stores."""

    def __init__(
        self,
        *,
        store: LocalV32OutcomeTickStore,
        capture_port: Any | None = None,
        transaction_runner: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        if not isinstance(store, LocalV32OutcomeTickStore):
            raise V32LocalOutcomeLaneError("V32_LOCAL_OUTCOME_STORE_INVALID")
        self._store = store
        self._capture_port = capture_port or V32OkxPublicMarkCaptureAdapter()
        self._transaction_runner = transaction_runner or run_v32_outcome_tick
        self.run_root = Path(store.run_root).absolute()
        if (
            not self.run_root.is_dir()
            or self.run_root.is_symlink()
            or self.run_root.resolve(strict=True)
            != Path(store.run_root).resolve(strict=True)
        ):
            raise V32LocalOutcomeLaneError("V32_LOCAL_OUTCOME_ROOT_INVALID")
        self._physical_root = self.run_root.resolve(strict=True)

    def _safe_path(self, relative_ref: str) -> Path:
        if (
            not self.run_root.is_dir()
            or self.run_root.is_symlink()
            or self.run_root.resolve(strict=True) != self._physical_root
        ):
            raise V32LocalOutcomeLaneError("V32_LOCAL_OUTCOME_ROOT_CHANGED")
        lexical = PurePosixPath(relative_ref)
        if (
            not isinstance(relative_ref, str)
            or not relative_ref
            or "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or len(lexical.parts) < 2
            or lexical.parts[0] != STORE_ROOT
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32LocalOutcomeLaneError("V32_LOCAL_OUTCOME_PATH_INVALID")
        current = self.run_root
        try:
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32LocalOutcomeLaneError(
                        "V32_LOCAL_OUTCOME_SYMLINK_FORBIDDEN"
                    )
            current.resolve(strict=False).relative_to(self._physical_root)
        except V32LocalOutcomeLaneError:
            raise
        except (OSError, ValueError) as exc:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_PATH_INVALID"
            ) from exc
        return current

    @contextmanager
    def _lock(self):
        path = self._safe_path(f"{STORE_ROOT}/.locks/lane.lock")
        ensure_directory_tree(path.parent)
        path = self._safe_path(f"{STORE_ROOT}/.locks/lane.lock")
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    @staticmethod
    def _permit_identity(permit: Mapping[str, Any]) -> tuple[str, str, int]:
        if not isinstance(permit, Mapping):
            raise V32LocalOutcomeLaneError("V32_LOCAL_OUTCOME_PERMIT_INVALID")
        try:
            permit_digest = verify_self_digest(permit, PERMIT_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_PERMIT_INVALID"
            ) from exc
        run_id = _text(
            permit.get("run_id"), "V32_LOCAL_OUTCOME_PERMIT_INVALID"
        )
        tick = permit.get("outcome_tick_index")
        kind = permit.get("permit_kind")
        expected_network = 0 if kind == "OUTCOME_WINDOW_EXPIRY" else 1
        if (
            kind not in {"OUTCOME_TICK", "OUTCOME_WINDOW_EXPIRY"}
            or isinstance(tick, bool)
            or not isinstance(tick, int)
            or tick < 1
            or permit.get("opened_lane") != "OUTCOME_LANE"
            or permit.get("network_requests_allowed") != expected_network
            or permit.get("source_collection_transactions_allowed") != 0
            or permit.get("future_outcomes_readable") is not False
            or permit.get("source_scope") != SOURCE_SCOPE
            or permit.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or permit.get("executable") is not False
            or permit.get("account_access") is not False
            or permit.get("order_submission") is not False
            or permit.get("fill_claim") is not False
            or permit.get("pnl_claim") is not False
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_PERMIT_BOUNDARY_INVALID"
            )
        if kind == "OUTCOME_WINDOW_EXPIRY" and (
            permit.get("tick_attempt_digest") is not None
            or not permit.get("due_schedule_ids")
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_PERMIT_BOUNDARY_INVALID"
            )
        return run_id, permit_digest, tick

    @staticmethod
    def _permit_root(permit_digest: str) -> str:
        return f"{STORE_ROOT}/permits/{permit_digest}"

    def _terminal_path(self, permit_digest: str, kind: str) -> Path:
        name = (
            "completion-envelope.json"
            if kind == "COMPLETION"
            else "failure-envelope.json"
        )
        return self._safe_path(f"{self._permit_root(permit_digest)}/{name}")

    def _failure_evidence_path(self, permit_digest: str) -> Path:
        return self._safe_path(
            f"{self._permit_root(permit_digest)}/failure-evidence.json"
        )

    def _not_due_path(self, permit_digest: str) -> Path:
        return self._safe_path(
            f"{self._permit_root(permit_digest)}/not-due-receipt.json"
        )

    def _load_not_due(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        run_id, permit_digest, tick = self._permit_identity(permit)
        path = self._not_due_path(permit_digest)
        if not path.exists():
            return None
        document = self._canonical_file(path)
        if (
            set(document) != _NOT_DUE_FIELDS
            or document.get("schema_id") != NOT_DUE_SCHEMA_ID
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("run_id") != run_id
            or document.get("tick_index") != tick
            or document.get("permit_digest") != permit_digest
            or document.get("observed_status") != "NOT_DUE"
            or document.get("network_request_count") != 0
            or document.get("terminal_state_created") is not False
            or document.get("retry_allowed") is not False
            or document.get("source_scope") != SOURCE_SCOPE
            or document.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or document.get("executable") is not False
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_NOT_DUE_RECEIPT_INVALID"
            )
        try:
            verify_self_digest(document, NOT_DUE_DIGEST_FIELD)
            _digest(
                document.get("outcome_checkpoint_digest"),
                "V32_LOCAL_OUTCOME_NOT_DUE_RECEIPT_INVALID",
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, V32LocalOutcomeLaneError):
                raise
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_NOT_DUE_RECEIPT_INVALID"
            ) from exc
        return document

    @staticmethod
    def _canonical_file(path: Path) -> Mapping[str, Any]:
        if not path.is_file() or path.is_symlink():
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_DURABLE_FILE_INVALID"
            )
        try:
            document = load_json_strict(path)
            if path.read_bytes() != canonical_bytes(document) + b"\n":
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_DURABLE_FILE_NONCANONICAL"
                )
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            if isinstance(exc, V32LocalOutcomeLaneError):
                raise
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_DURABLE_FILE_INVALID"
            ) from exc
        return document

    def _load_terminal(
        self, *, permit_digest: str, kind: str
    ) -> Mapping[str, Any] | None:
        own = self._terminal_path(permit_digest, kind)
        other = self._terminal_path(
            permit_digest, "FAILURE" if kind == "COMPLETION" else "COMPLETION"
        )
        if own.exists() and other.exists():
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_DUAL_TERMINAL_STATE"
            )
        if not own.exists():
            return None
        document = self._canonical_file(own)
        expected = _COMPLETION_FIELDS if kind == "COMPLETION" else _FAILURE_FIELDS
        if set(document) != expected:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_TERMINAL_ENVELOPE_INVALID"
            )
        return document

    def _write_terminal(
        self,
        *,
        permit_digest: str,
        kind: str,
        envelope: Mapping[str, Any],
    ) -> str:
        own = self._terminal_path(permit_digest, kind)
        other = self._terminal_path(
            permit_digest, "FAILURE" if kind == "COMPLETION" else "COMPLETION"
        )
        if other.exists():
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_DUAL_TERMINAL_STATE"
            )
        try:
            write_once_json(own, envelope)
        except (OSError, TypeError, ValueError) as exc:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_TERMINAL_WRITE_CONFLICT"
            ) from exc
        return canonical_digest(dict(envelope))

    def _bound_outcome_failure(
        self, *, run_id: str, checkpoint: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        binding = checkpoint.get("failure_binding")
        if checkpoint.get("status") != "FAILED_CLOSED" or not isinstance(
            binding, Mapping
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_STATE_INVALID"
            )
        relative_ref = binding.get("relative_ref")
        if not isinstance(relative_ref, str):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_BINDING_INVALID"
            )
        # The outcome checkpoint loader already replays this binding.  Repeat
        # its physical identity here so the lane envelope is independently
        # replayable without trusting an unverified relative reference.
        lexical = PurePosixPath(relative_ref)
        if (
            lexical.is_absolute()
            or lexical.as_posix() != relative_ref
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_BINDING_INVALID"
            )
        path = self.run_root.joinpath(*lexical.parts)
        try:
            path.resolve(strict=True).relative_to(self._physical_root)
        except (OSError, ValueError) as exc:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_BINDING_INVALID"
            ) from exc
        document = self._canonical_file(path)
        try:
            semantic = verify_self_digest(document, OUTCOME_FAILURE_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_BINDING_INVALID"
            ) from exc
        physical = hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()
        if (
            document.get("schema_id") != OUTCOME_FAILURE_SCHEMA_ID
            or document.get("run_id") != run_id
            or semantic != binding.get("semantic_digest")
            or physical != binding.get("physical_sha256")
            or document.get("retry_allowed") is not False
            or document.get("resume_allowed") is not False
            or document.get("source_scope") != SOURCE_SCOPE
            or document.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or document.get("executable") is not False
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_BINDING_INVALID"
            )
        return document

    def _failure_evidence_from_outcome_store(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        run_id, permit_digest, tick = self._permit_identity(permit)
        checkpoint = self._store.load_checkpoint(run_id=run_id)
        failure = self._bound_outcome_failure(
            run_id=run_id, checkpoint=checkpoint
        )
        code = _text(
            failure.get("failure_code"),
            "V32_LOCAL_OUTCOME_FAILURE_CODE_INVALID",
        )
        summary = f"V3.2 local outcome transaction permanently failed closed: {code}"
        return self_digest(
            {
                "schema_id": FAILURE_EVIDENCE_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "tick_index": tick,
                "permit_digest": permit_digest,
                "failure_code": code,
                "failure_summary": summary,
                "failure_class": "OUTCOME_TICK_FAILURE_SEAL",
                "failure_message": code,
                "outcome_checkpoint_digest": checkpoint["checkpoint_digest"],
                "outcome_failure_digest": failure[OUTCOME_FAILURE_DIGEST_FIELD],
                "occurred_at": failure["failed_at"],
                "retry_allowed": False,
                "resume_allowed": False,
                "source_scope": SOURCE_SCOPE,
                "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                "executable": False,
            },
            FAILURE_EVIDENCE_DIGEST_FIELD,
        )

    def _adapter_failure_evidence(
        self,
        *,
        permit: Mapping[str, Any],
        error: Exception,
        checkpoint: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        run_id, permit_digest, tick = self._permit_identity(permit)
        checkpoint_digest = (
            checkpoint.get("checkpoint_digest")
            if isinstance(checkpoint, Mapping)
            else permit.get("outcome_checkpoint_digest")
        )
        message = str(error).strip() or type(error).__name__
        message = message[:512]
        code = "V32_LOCAL_OUTCOME_LANE_STRUCTURAL_FAILURE"
        return self_digest(
            {
                "schema_id": FAILURE_EVIDENCE_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "tick_index": tick,
                "permit_digest": permit_digest,
                "failure_code": code,
                "failure_summary": (
                    "V3.2 local outcome lane permanently failed closed: " + code
                ),
                "failure_class": type(error).__name__,
                "failure_message": message,
                "outcome_checkpoint_digest": _digest(
                    checkpoint_digest,
                    "V32_LOCAL_OUTCOME_FAILURE_CHECKPOINT_INVALID",
                ),
                "outcome_failure_digest": None,
                "occurred_at": _time(
                    permit.get("issued_at"),
                    "V32_LOCAL_OUTCOME_FAILURE_TIME_INVALID",
                ),
                "retry_allowed": False,
                "resume_allowed": False,
                "source_scope": SOURCE_SCOPE,
                "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                "executable": False,
            },
            FAILURE_EVIDENCE_DIGEST_FIELD,
        )

    def _verify_failure_evidence(
        self, document: Mapping[str, Any], *, permit: Mapping[str, Any]
    ) -> str:
        run_id, permit_digest, tick = self._permit_identity(permit)
        if (
            not isinstance(document, Mapping)
            or set(document) != _FAILURE_EVIDENCE_FIELDS
            or document.get("schema_id") != FAILURE_EVIDENCE_SCHEMA_ID
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("run_id") != run_id
            or document.get("tick_index") != tick
            or document.get("permit_digest") != permit_digest
            or document.get("retry_allowed") is not False
            or document.get("resume_allowed") is not False
            or document.get("source_scope") != SOURCE_SCOPE
            or document.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or document.get("executable") is not False
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID"
            )
        try:
            supplied = verify_self_digest(
                document, FAILURE_EVIDENCE_DIGEST_FIELD
            )
            _text(
                document.get("failure_code"),
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID",
            )
            _text(
                document.get("failure_summary"),
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID",
            )
            _text(
                document.get("failure_class"),
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID",
            )
            _text(
                document.get("failure_message"),
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID",
            )
            _digest(
                document.get("outcome_checkpoint_digest"),
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID",
            )
            outcome_failure_digest = document.get("outcome_failure_digest")
            if outcome_failure_digest is not None:
                _digest(
                    outcome_failure_digest,
                    "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID",
                )
            _time(
                document.get("occurred_at"),
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID",
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, V32LocalOutcomeLaneError):
                raise
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_INVALID"
            ) from exc
        return supplied

    def _load_failure_evidence(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        _, permit_digest, _ = self._permit_identity(permit)
        path = self._failure_evidence_path(permit_digest)
        if not path.exists():
            return None
        document = self._canonical_file(path)
        self._verify_failure_evidence(document, permit=permit)
        return document

    def _persist_failure_evidence(
        self, *, permit: Mapping[str, Any], evidence: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        _, permit_digest, _ = self._permit_identity(permit)
        self._verify_failure_evidence(evidence, permit=permit)
        try:
            write_once_json(self._failure_evidence_path(permit_digest), evidence)
        except (OSError, TypeError, ValueError) as exc:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_CONFLICT"
            ) from exc
        return evidence

    @staticmethod
    def _failure_envelope(evidence: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "permit_digest": evidence["permit_digest"],
            "failure_summary": evidence["failure_summary"],
            "failure_evidence_digest": evidence[FAILURE_EVIDENCE_DIGEST_FIELD],
            "occurred_at": evidence["occurred_at"],
        }

    def _seal_failure_from_store(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        _, permit_digest, _ = self._permit_identity(permit)
        evidence = self._load_failure_evidence(permit=permit)
        if evidence is None:
            evidence = self._persist_failure_evidence(
                permit=permit,
                evidence=self._failure_evidence_from_outcome_store(
                    permit=permit
                ),
            )
        envelope = self._failure_envelope(evidence)
        transition_digest = self._write_terminal(
            permit_digest=permit_digest,
            kind="FAILURE",
            envelope=envelope,
        )
        return {
            "advance_status": "FAILURE_SEALED",
            "durable_transition_digest": transition_digest,
        }

    def _seal_structural_failure(
        self, *, permit: Mapping[str, Any], error: Exception
    ) -> Mapping[str, Any]:
        run_id, permit_digest, tick = self._permit_identity(permit)
        existing = self._load_failure_evidence(permit=permit)
        if existing is not None:
            envelope = self._failure_envelope(existing)
            transition_digest = self._write_terminal(
                permit_digest=permit_digest,
                kind="FAILURE",
                envelope=envelope,
            )
            return {
                "advance_status": "FAILURE_SEALED",
                "durable_transition_digest": transition_digest,
            }
        checkpoint: Mapping[str, Any] | None = None
        try:
            checkpoint = self._store.load_checkpoint(run_id=run_id)
            if checkpoint.get("status") == "ACTIVE":
                self._store.fail_closed(
                    run_id=run_id,
                    failure_code="V32_LOCAL_OUTCOME_LANE_STRUCTURAL_FAILURE",
                    failed_at=_later_time(
                        str(permit["issued_at"]), str(checkpoint["updated_at"])
                    ),
                    tick_index=(
                        tick
                        if len(checkpoint.get("attempt_bindings", ())) >= tick
                        else None
                    ),
                )
                checkpoint = self._store.load_checkpoint(run_id=run_id)
        except Exception:
            # The adapter-level write-once failure evidence remains the final
            # fail-closed authority if the lower store cannot seal itself.
            pass
        if isinstance(checkpoint, Mapping) and checkpoint.get("status") == "FAILED_CLOSED":
            return self._seal_failure_from_store(permit=permit)
        evidence = self._persist_failure_evidence(
            permit=permit,
            evidence=self._adapter_failure_evidence(
                permit=permit, error=error, checkpoint=checkpoint
            ),
        )
        envelope = self._failure_envelope(evidence)
        transition_digest = self._write_terminal(
            permit_digest=permit_digest,
            kind="FAILURE",
            envelope=envelope,
        )
        return {
            "advance_status": "FAILURE_SEALED",
            "durable_transition_digest": transition_digest,
        }

    def _build_completion_envelope(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if permit.get("permit_kind") == "OUTCOME_WINDOW_EXPIRY":
            return self._build_expiry_completion_envelope(permit=permit)
        run_id, permit_digest, tick = self._permit_identity(permit)
        checkpoint = self._store.load_checkpoint(run_id=run_id)
        prefix = self._store.tick_prefix(run_id=run_id, tick_index=tick)
        if any(
            prefix.get(field) is None
            for field in (
                "attempt",
                "observation_tick",
                "batch_intent",
                "batch_completion",
            )
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_COMPLETION_PREFIX_INCOMPLETE"
            )
        schedule_sets = self._store.load_schedule_sets(run_id=run_id)
        schedule_digests = [
            verify_self_digest(document, SCHEDULE_SET_DIGEST_FIELD)
            for document in schedule_sets
        ]
        if schedule_digests != list(permit.get("outcome_schedule_set_digests", ())):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_SCHEDULE_BINDING_MISMATCH"
            )
        attempt = prefix["attempt"]
        attempt_digest = verify_v32_outcome_tick_attempt(attempt)
        if (
            attempt_digest != permit.get("tick_attempt_digest")
            or attempt.get("run_id") != run_id
            or attempt.get("tick_index") != tick
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_ATTEMPT_BINDING_MISMATCH"
            )
        observation = prefix["observation_tick"]
        verify_v32_outcome_observation_tick(observation, attempt=attempt)
        all_receipts = self._store.load_terminal_receipts(run_id=run_id)
        prior_ids = set(permit.get("terminal_schedule_ids", ()))
        prior_receipts = sorted(
            (
                receipt
                for receipt in all_receipts
                if receipt.get("schedule_id") in prior_ids
            ),
            key=lambda row: str(row["schedule_id"]),
        )
        if [row["schedule_id"] for row in prior_receipts] != list(
            permit.get("terminal_schedule_ids", ())
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_PRIOR_RECEIPT_MISMATCH"
            )
        batch_intent = prefix["batch_intent"]
        verify_v32_outcome_resolution_batch_intent(
            batch_intent,
            attempt=attempt,
            observation_tick=observation,
            schedule_sets=schedule_sets,
            prior_terminal_receipts=prior_receipts,
        )
        outcome_receipts = list(prefix["outcome_receipts"])
        for receipt in outcome_receipts:
            verify_v32_public_market_outcome_receipt(
                receipt,
                batch_intent=batch_intent,
                attempt=attempt,
                observation_tick=observation,
                schedule_sets=schedule_sets,
            )
        batch_completion = prefix["batch_completion"]
        batch_digest = verify_v32_outcome_resolution_batch(
            batch_completion,
            batch_intent=batch_intent,
            outcome_receipts=outcome_receipts,
        )
        due_ids = list(permit.get("due_schedule_ids", ()))
        if (
            list(batch_intent.get("due_schedule_ids", ())) != due_ids
            or list(batch_completion.get("resolved_schedule_ids", ())) != due_ids
            or sorted(row["schedule_id"] for row in outcome_receipts) != due_ids
            or len(checkpoint.get("batch_completion_bindings", ())) < tick
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_DUE_SET_MISMATCH"
            )
        outcome_checkpoint_digest = self._historical_checkpoint_digest(
            permit=permit,
            current_checkpoint=checkpoint,
            schedule_sets=schedule_sets,
            all_terminal_receipts=all_receipts,
            batch_completion=batch_completion,
        )
        completion = {
            "tick_attempt": attempt,
            "observation_tick": observation,
            "schedule_sets": schedule_sets,
            "prior_terminal_receipts": prior_receipts,
            "batch_intent": batch_intent,
            "outcome_receipts": outcome_receipts,
            "batch_completion": batch_completion,
            "new_outcome_checkpoint_digest": outcome_checkpoint_digest,
            "completed_at": batch_completion["completed_at"],
        }
        return {
            "permit_digest": permit_digest,
            "batch_completion_digest": batch_digest,
            "completion": completion,
        }

    def _build_expiry_completion_envelope(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        run_id, permit_digest, tick = self._permit_identity(permit)
        schedule_sets = self._store.load_schedule_sets(run_id=run_id)
        terminal = build_v32_outcome_window_expiry_terminal(
            run_id=run_id,
            classified_at=permit["issued_at"],
            schedule_sets=schedule_sets,
            prior_terminal_schedule_ids=permit["terminal_schedule_ids"],
            permit_digest=permit_digest,
            supervisor_checkpoint_digest_before_permit=permit[
                "supervisor_checkpoint_digest_before_permit"
            ],
            outcome_checkpoint_digest_before=permit["outcome_checkpoint_digest"],
            experiment_contract_digest=permit["experiment_contract_digest"],
            active_authority_digest=permit["active_authority_digest"],
        )
        terminal_digest = verify_v32_outcome_window_expiry_terminal(
            terminal, schedule_sets=schedule_sets
        )
        durable = self._store.load_outcome_window_expiry(
            run_id=run_id, expiry_terminal_digest=terminal_digest
        )
        checkpoint = self._store.load_checkpoint(run_id=run_id)
        if (
            durable is None
            or dict(durable["expiry_terminal"]) != terminal
            or terminal["terminal_schedule_ids"] != permit["due_schedule_ids"]
            or durable["checkpoint_digest"] != checkpoint["checkpoint_digest"]
            or len(checkpoint.get("attempt_bindings", ())) != tick - 1
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_EXPIRY_COMPLETION_BINDING_MISMATCH"
            )
        return {
            "permit_digest": permit_digest,
            "batch_completion_digest": terminal_digest,
            "completion": {
                "schedule_sets": schedule_sets,
                "expiry_terminal": terminal,
                "new_outcome_checkpoint_digest": checkpoint["checkpoint_digest"],
                "completed_at": terminal["classified_at"],
            },
        }

    def _historical_checkpoint_digest(
        self,
        *,
        permit: Mapping[str, Any],
        current_checkpoint: Mapping[str, Any],
        schedule_sets: list[Mapping[str, Any]],
        all_terminal_receipts: list[Mapping[str, Any]],
        batch_completion: Mapping[str, Any],
    ) -> str:
        """Rebuild the exact outcome-store head sealed by this permit.

        Later analysis cycles may append schedule sets after this completion.
        The write-once terminal envelope must remain fully replayable then, so
        it binds the historical append-only prefix rather than the latest head.
        """

        tick = int(permit["outcome_tick_index"])
        schedule_count = len(permit.get("outcome_schedule_set_digests", ()))
        if len(schedule_sets) < schedule_count:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_INVALID"
            )
        list_prefix_lengths = {
            "schedule_set_bindings": schedule_count,
            "attempt_bindings": tick,
            "evidence_bindings": tick,
            "normalization_bindings": tick,
            "observation_tick_bindings": tick,
            "batch_intent_bindings": tick,
            "batch_completion_bindings": tick,
        }
        candidate = dict(current_checkpoint)
        for field, length in list_prefix_lengths.items():
            values = current_checkpoint.get(field)
            if not isinstance(values, list) or len(values) < length:
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_INVALID"
                )
            candidate[field] = list(values[:length])
        receipt_bindings = current_checkpoint.get("outcome_receipt_bindings")
        if not isinstance(receipt_bindings, list):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_INVALID"
            )
        candidate["outcome_receipt_bindings"] = [
            binding
            for binding in receipt_bindings
            if isinstance(binding, Mapping)
            and isinstance(binding.get("tick_index"), int)
            and binding["tick_index"] <= tick
        ]
        expiry_count = 0
        expiry_receipt_ids: set[str] = set()
        if current_checkpoint.get("schema_id") == (
            "theory_paper_v32_outcome_tick_checkpoint_v2"
        ):
            expiry_bindings = current_checkpoint.get("expiry_terminal_bindings")
            if not isinstance(expiry_bindings, list):
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_INVALID"
                )
            batch_completed = datetime.fromisoformat(
                _time(
                    batch_completion["completed_at"],
                    "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_INVALID",
                ).replace("Z", "+00:00")
            )
            for expiry_binding in expiry_bindings:
                durable = self._store.load_outcome_window_expiry(
                    run_id=permit["run_id"],
                    expiry_terminal_digest=expiry_binding["semantic_digest"],
                )
                if durable is None:
                    raise V32LocalOutcomeLaneError(
                        "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_INVALID"
                    )
                expiry_completed = datetime.fromisoformat(
                    _time(
                        durable["expiry_terminal"]["classified_at"],
                        "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_INVALID",
                    ).replace("Z", "+00:00")
                )
                if expiry_completed <= batch_completed:
                    expiry_count += 1
                    expiry_receipt_ids.update(
                        str(receipt["schedule_id"])
                        for receipt in durable["expiry_terminal"]["rows"]
                    )
            candidate["expiry_terminal_bindings"] = expiry_bindings[:expiry_count]
            if expiry_count == 0:
                candidate["schema_id"] = CHECKPOINT_SCHEMA_ID
                candidate["schema_version"] = CHECKPOINT_SCHEMA_VERSION
                candidate.pop("expiry_terminal_bindings")
        resolved_at_prefix = {
            receipt["schedule_id"]
            for receipt in all_terminal_receipts
            if receipt.get("schedule_id")
            in {
                binding.get("schedule_id")
                for binding in candidate["outcome_receipt_bindings"]
            }
        } | expiry_receipt_ids
        scheduled_at_prefix = {
            schedule["schedule_id"]
            for schedule_set in schedule_sets[:schedule_count]
            for schedule in schedule_set["schedules"]
        }
        terminal = (
            schedule_count == int(current_checkpoint["total_cycles"])
            and len(scheduled_at_prefix)
            == int(current_checkpoint["total_schedules"])
            and resolved_at_prefix == scheduled_at_prefix
        )
        append_fields = (
            "schedule_set_bindings",
            "attempt_bindings",
            "evidence_bindings",
            "normalization_bindings",
            "observation_tick_bindings",
            "batch_intent_bindings",
            "outcome_receipt_bindings",
            "batch_completion_bindings",
        )
        candidate.update(
            {
                "revision": sum(len(candidate[field]) for field in append_fields)
                + expiry_count,
                "status": "TERMINAL" if terminal else "ACTIVE",
                "failure_binding": None,
                "updated_at": batch_completion["completed_at"],
            }
        )
        historical = self_digest(candidate, "checkpoint_digest")
        # While this permit remains open, no later outcome/schedule mutation is
        # legal and the reconstructed historical head must be the live CAS head.
        # Once a later permit has advanced the store, the sealed prefix remains
        # valid even though the current digest differs.
        if (
            len(current_checkpoint.get("schedule_set_bindings", ()))
            == schedule_count
            and len(current_checkpoint.get("batch_completion_bindings", ()))
            == tick
            and len(current_checkpoint.get("expiry_terminal_bindings", ()))
            == expiry_count
            and current_checkpoint.get("status") != "FAILED_CLOSED"
            and historical["checkpoint_digest"]
            != current_checkpoint.get("checkpoint_digest")
        ):
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_HISTORICAL_CHECKPOINT_MISMATCH"
            )
        return historical["checkpoint_digest"]

    def _seal_completion(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        _, permit_digest, _ = self._permit_identity(permit)
        envelope = self._build_completion_envelope(permit=permit)
        transition_digest = self._write_terminal(
            permit_digest=permit_digest,
            kind="COMPLETION",
            envelope=envelope,
        )
        return {
            "advance_status": "COMPLETION_SEALED",
            "durable_transition_digest": transition_digest,
        }

    def _persist_not_due(
        self,
        *,
        permit: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        run_id, permit_digest, tick = self._permit_identity(permit)
        checkpoint_digest = _digest(
            result.get("checkpoint_digest"),
            "V32_LOCAL_OUTCOME_NOT_DUE_CHECKPOINT_INVALID",
        )
        receipt = self_digest(
            {
                "schema_id": NOT_DUE_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "tick_index": tick,
                "permit_digest": permit_digest,
                "outcome_checkpoint_digest": checkpoint_digest,
                "observed_status": "NOT_DUE",
                "network_request_count": 0,
                "terminal_state_created": False,
                "retry_allowed": False,
                "source_scope": SOURCE_SCOPE,
                "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                "executable": False,
            },
            NOT_DUE_DIGEST_FIELD,
        )
        try:
            write_once_json(self._not_due_path(permit_digest), receipt)
        except (OSError, TypeError, ValueError) as exc:
            raise V32LocalOutcomeLaneError(
                "V32_LOCAL_OUTCOME_NOT_DUE_WRITE_CONFLICT"
            ) from exc
        return {
            "advance_status": "PENDING",
            "durable_transition_digest": receipt[NOT_DUE_DIGEST_FIELD],
        }

    def advance_outcome(
        self,
        *,
        permit: Mapping[str, Any],
        supervisor_checkpoint_before_permit: Mapping[str, Any],
        supervisor_open_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Advance one raw-first outcome transaction and seal one lane result."""

        run_id, permit_digest, tick = self._permit_identity(permit)
        with self._lock():
            completion = self._load_terminal(
                permit_digest=permit_digest, kind="COMPLETION"
            )
            failure = self._load_terminal(
                permit_digest=permit_digest, kind="FAILURE"
            )
            if completion is not None:
                return {
                    "advance_status": "COMPLETION_SEALED",
                    "durable_transition_digest": canonical_digest(completion),
                }
            if failure is not None:
                return {
                    "advance_status": "FAILURE_SEALED",
                    "durable_transition_digest": canonical_digest(failure),
                }
            evidence = self._load_failure_evidence(permit=permit)
            if evidence is not None:
                envelope = self._failure_envelope(evidence)
                digest = self._write_terminal(
                    permit_digest=permit_digest,
                    kind="FAILURE",
                    envelope=envelope,
                )
                return {
                    "advance_status": "FAILURE_SEALED",
                    "durable_transition_digest": digest,
                }
            not_due = self._load_not_due(permit=permit)
            if not_due is not None:
                # Defensive idempotence only.  A valid Supervisor permit cannot
                # be opened without a due schedule, and this receipt grants no
                # later read or retry authority.
                return {
                    "advance_status": "PENDING",
                    "durable_transition_digest": not_due[NOT_DUE_DIGEST_FIELD],
                }
            try:
                checkpoint = self._store.load_checkpoint(run_id=run_id)
                if checkpoint.get("status") == "FAILED_CLOSED":
                    return self._seal_failure_from_store(permit=permit)
                if permit.get("permit_kind") == "OUTCOME_WINDOW_EXPIRY":
                    result = run_v32_outcome_window_expiry(
                        store=self._store,
                        run_id=run_id,
                        supervisor_checkpoint_before_permit=(
                            supervisor_checkpoint_before_permit
                        ),
                        supervisor_open_checkpoint=supervisor_open_checkpoint,
                        supervisor_permit=permit,
                    )
                    if (
                        not isinstance(result, Mapping)
                        or result.get("runtime_status")
                        != "RESOLVED"
                        or result.get("network_request_count") != 0
                        or result.get("attempt_count") != 0
                        or result.get("raw_evidence_present") is not False
                        or result.get("observation_tick_present") is not False
                    ):
                        raise V32LocalOutcomeLaneError(
                            "V32_LOCAL_EXPIRY_RESULT_INVALID"
                        )
                    return self._seal_completion(permit=permit)
                if len(checkpoint.get("batch_completion_bindings", ())) >= tick:
                    return self._seal_completion(permit=permit)
                result = self._transaction_runner(
                    store=self._store,
                    capture_port=self._capture_port,
                    run_id=run_id,
                    tick_index=tick,
                    planned_tick_at=permit["planned_outcome_tick_at"],
                    requested_at=permit["issued_at"],
                    supervisor_checkpoint_before_permit=(
                        supervisor_checkpoint_before_permit
                    ),
                    supervisor_open_checkpoint=supervisor_open_checkpoint,
                    supervisor_permit=permit,
                )
                if not isinstance(result, Mapping):
                    raise V32LocalOutcomeLaneError(
                        "V32_LOCAL_OUTCOME_TRANSACTION_RESULT_INVALID"
                    )
                status = result.get("runtime_status")
                if status == "NOT_DUE":
                    # A valid Supervisor outcome permit has a non-empty due set,
                    # so this is only a defensive non-terminal representation.
                    # It is never promoted to a completion envelope.
                    return self._persist_not_due(permit=permit, result=result)
                if status in {"RESOLVED", "TERMINAL", "ALREADY_COMPLETE"}:
                    return self._seal_completion(permit=permit)
                if status == "FAILED_CLOSED":
                    return self._seal_failure_from_store(permit=permit)
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_TRANSACTION_STATUS_INVALID"
                )
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                if not isinstance(exc, Exception):
                    # A process-level interruption deliberately leaves the
                    # verified outcome prefix for a later no-retry re-entry.
                    raise
                return self._seal_structural_failure(
                    permit=permit, error=exc
                )

    def load_durable_outcome_completion(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            document = self._load_terminal(
                permit_digest=permit_digest, kind="COMPLETION"
            )
            return deepcopy(document) if document is not None else None

    def verify_durable_outcome_completion(
        self,
        *,
        permit: Mapping[str, Any],
        completion_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            durable = self._load_terminal(
                permit_digest=permit_digest, kind="COMPLETION"
            )
            if durable is None or dict(completion_envelope) != dict(durable):
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_COMPLETION_DURABILITY_MISMATCH"
                )
            expected = self._build_completion_envelope(permit=permit)
            if dict(durable) != dict(expected):
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_COMPLETION_REPLAY_MISMATCH"
                )
            return deepcopy(durable)

    def load_durable_outcome_failure(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            document = self._load_terminal(
                permit_digest=permit_digest, kind="FAILURE"
            )
            return deepcopy(document) if document is not None else None

    def verify_durable_outcome_failure(
        self,
        *,
        permit: Mapping[str, Any],
        failure_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            durable = self._load_terminal(
                permit_digest=permit_digest, kind="FAILURE"
            )
            if durable is None or dict(failure_envelope) != dict(durable):
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_FAILURE_DURABILITY_MISMATCH"
                )
            evidence = self._load_failure_evidence(permit=permit)
            if evidence is None:
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_FAILURE_EVIDENCE_MISSING"
                )
            expected = self._failure_envelope(evidence)
            if dict(durable) != dict(expected):
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_FAILURE_REPLAY_MISMATCH"
                )
            checkpoint = self._store.load_checkpoint(run_id=permit["run_id"])
            if checkpoint.get("checkpoint_digest") != evidence.get(
                "outcome_checkpoint_digest"
            ):
                raise V32LocalOutcomeLaneError(
                    "V32_LOCAL_OUTCOME_FAILURE_CHECKPOINT_MISMATCH"
                )
            outcome_failure_digest = evidence.get("outcome_failure_digest")
            if outcome_failure_digest is not None:
                failure = self._bound_outcome_failure(
                    run_id=permit["run_id"], checkpoint=checkpoint
                )
                if failure.get(OUTCOME_FAILURE_DIGEST_FIELD) != outcome_failure_digest:
                    raise V32LocalOutcomeLaneError(
                        "V32_LOCAL_OUTCOME_FAILURE_REPLAY_MISMATCH"
                    )
            return deepcopy(durable)


__all__ = [
    "FAILURE_EVIDENCE_DIGEST_FIELD",
    "FAILURE_EVIDENCE_SCHEMA_ID",
    "LocalV32OutcomeLane",
    "NOT_DUE_DIGEST_FIELD",
    "NOT_DUE_SCHEMA_ID",
    "STORE_ROOT",
    "V32LocalOutcomeLaneError",
]
