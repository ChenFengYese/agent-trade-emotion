"""Write-once local controller for the sole V3.2 target-run genesis.

The store owns only local bytes, readback, replay, and the one atomic ACTIVE
pointer.  It has no network, clock, Agent, account, credential, portfolio, or
execution capability.  A crash may leave immutable evidence, but the pointer
is unreachable until every source copy, typed timeframe, revision-zero
checkpoint, and genesis receipt has been read back and replayed.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path, PurePosixPath
import threading
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    load_json_strict,
    loads_json_strict,
    verify_self_digest,
)
from ..v32_durable_json import (
    confirm_existing_bytes,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_bytes,
)
from ..domain.v32_run_genesis import (
    GENESIS_SOURCE_SPECS,
    INITIAL_TIMEFRAME_REF,
    REVISION_ZERO_SPECS,
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_REF,
    RUN_GENESIS_SCHEMA_ID,
    SOURCE_ROLES,
    TIMEFRAME_DIGEST_FIELD,
    build_v32_current_run_pointer_v1,
    build_v32_run_genesis_receipt_v1,
    validate_v32_target_projection_v1,
    verify_v32_current_run_pointer_v1,
    verify_v32_initial_timeframe_genesis_entity_v1,
    verify_v32_revision_zero_checkpoints_v1,
    verify_v32_run_genesis_receipt_v1,
)


CONTROL_ROOT_RELATIVE = Path(".runtime/theory-paper-v32")
RUNS_ROOT_RELATIVE = Path("runs")
CURRENT_RUN_POINTER_REF = "current-target-run.json"

_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_LIVE_REVISION_ZERO_PATHS = {
    "dynamic": (
        "v32-dynamic-cycle-v1/checkpoint.json",
        REVISION_ZERO_SPECS["dynamic"][1],
        REVISION_ZERO_SPECS["dynamic"][2],
    ),
    "outcome": (
        "outcome-v32/checkpoint.json",
        REVISION_ZERO_SPECS["outcome"][1],
        REVISION_ZERO_SPECS["outcome"][2],
    ),
    "supervisor": (
        "v32-tick-supervisor-v1/checkpoint.json",
        REVISION_ZERO_SPECS["supervisor"][1],
        REVISION_ZERO_SPECS["supervisor"][2],
    ),
}


class V32RunControlStoreError(ValueError):
    """The local run-control root or publication chronology failed closed."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_payload(document: Mapping[str, Any]) -> bytes:
    return canonical_bytes(dict(document)) + b"\n"


class LocalV32RunControlStore:
    """Durable owner of V3.2 immutable genesis evidence and unique pointer."""

    def __init__(self, project_root: Path) -> None:
        project = Path(project_root).absolute()
        if project.is_symlink() or not project.is_dir():
            raise V32RunControlStoreError("V32_RUN_CONTROL_PROJECT_ROOT_INVALID")
        self.project_root = project
        self._project_physical = project.resolve(strict=True)
        self.control_root = project / CONTROL_ROOT_RELATIVE
        if self.control_root.exists() and self.control_root.is_symlink():
            raise V32RunControlStoreError("V32_RUN_CONTROL_ROOT_SYMLINK_FORBIDDEN")
        ensure_directory_tree(self.control_root)
        if self.control_root.is_symlink() or not self.control_root.is_dir():
            raise V32RunControlStoreError("V32_RUN_CONTROL_ROOT_INVALID")
        self._control_physical = self.control_root.resolve(strict=True)

    def _assert_roots(self) -> None:
        if (
            self.project_root.is_symlink()
            or not self.project_root.is_dir()
            or self.project_root.resolve(strict=True) != self._project_physical
            or self.control_root.is_symlink()
            or not self.control_root.is_dir()
            or self.control_root.resolve(strict=True) != self._control_physical
        ):
            raise V32RunControlStoreError("V32_RUN_CONTROL_ROOT_CHANGED")

    @staticmethod
    def _run_id(value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 160
            or value[0] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            or any(
                character
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                for character in value
            )
        ):
            raise V32RunControlStoreError("V32_RUN_CONTROL_RUN_ID_INVALID")
        return value

    def _safe_control_path(self, relative_ref: str) -> Path:
        self._assert_roots()
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V32RunControlStoreError("V32_RUN_CONTROL_PATH_INVALID")
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32RunControlStoreError("V32_RUN_CONTROL_PATH_INVALID")
        current = self.control_root
        try:
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32RunControlStoreError(
                        "V32_RUN_CONTROL_SYMLINK_FORBIDDEN"
                    )
            current.resolve(strict=False).relative_to(self._control_physical)
        except V32RunControlStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32RunControlStoreError("V32_RUN_CONTROL_PATH_INVALID") from exc
        return current

    def run_root(self, run_id: str) -> Path:
        run = self._run_id(run_id)
        path = self._safe_control_path(
            f"{RUNS_ROOT_RELATIVE.as_posix()}/{run}"
        )
        ensure_directory_tree(path)
        if path.is_symlink() or not path.is_dir():
            raise V32RunControlStoreError("V32_RUN_CONTROL_RUN_ROOT_INVALID")
        return path

    @contextmanager
    def genesis_guard(self):
        """Serialize all target-run initialization and pointer publication."""

        lock_path = self._safe_control_path(".locks/run-genesis.lock")
        ensure_directory_tree(lock_path.parent)
        key = str(lock_path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(lock_path):
                yield

    @contextmanager
    def run_composition_guard(self, *, run_id: str):
        """Serialize one target run's wake and external Agent boundaries.

        This lock is intentionally distinct from ``genesis_guard`` and every
        outcome-store lock.  A production wake and its current-root Agent
        claim/delivery therefore cannot interleave a Supervisor close with a
        mailbox CAS while still allowing genesis and outcome stores to use
        their own non-nested durability guards.
        """

        run = self._run_id(run_id)
        lock_path = self._safe_control_path(
            f".locks/run-composition/{run}.lock"
        )
        ensure_directory_tree(lock_path.parent)
        key = str(lock_path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(lock_path):
                yield

    def _run_relative(self, run_id: str, local_ref: str) -> str:
        run = self._run_id(run_id)
        return f"{RUNS_ROOT_RELATIVE.as_posix()}/{run}/{local_ref}"

    def _atomic_write_once_bytes(self, relative_ref: str, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise V32RunControlStoreError("V32_RUN_CONTROL_BYTES_INVALID")
        target = self._safe_control_path(relative_ref)
        ensure_directory_tree(target.parent)
        target = self._safe_control_path(relative_ref)
        try:
            return write_once_bytes(target, payload)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_WRITE_ONCE_CONFLICT:{relative_ref}"
            ) from exc

    def _after_immutable_write(self, *, role: str, relative_ref: str) -> None:
        """Private no-op seam used only for crash-injection verification."""

    def _read_exact(self, relative_ref: str, expected: bytes) -> bytes:
        path = self._safe_control_path(relative_ref)
        if path.is_symlink() or not path.is_file():
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_READBACK_MISSING:{relative_ref}"
            )
        payload = path.read_bytes()
        if payload != expected:
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_READBACK_DRIFT:{relative_ref}"
            )
        try:
            confirm_existing_bytes(path, expected)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_READBACK_DRIFT:{relative_ref}"
            ) from exc
        return payload

    @staticmethod
    def _binding(
        *, relative_ref: str, document: Mapping[str, Any], digest_field: str, payload: bytes
    ) -> dict[str, str]:
        try:
            semantic = verify_self_digest(document, digest_field)
        except (TypeError, ValueError) as exc:
            raise V32RunControlStoreError(
                "V32_RUN_CONTROL_DOCUMENT_DIGEST_INVALID"
            ) from exc
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": _sha256(payload),
        }

    def load_current_pointer(self) -> Mapping[str, Any] | None:
        path = self._safe_control_path(CURRENT_RUN_POINTER_REF)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise V32RunControlStoreError("V32_RUN_CONTROL_POINTER_INVALID")
        try:
            pointer = load_json_strict(path)
            verify_v32_current_run_pointer_v1(pointer)
        except (TypeError, ValueError) as exc:
            raise V32RunControlStoreError("V32_RUN_CONTROL_POINTER_INVALID") from exc
        try:
            confirm_existing_bytes(path, canonical_bytes(pointer) + b"\n")
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32RunControlStoreError(
                "V32_RUN_CONTROL_POINTER_INVALID"
            ) from exc
        return pointer

    def assert_pointer_available(self, *, expected_run_id: str) -> Mapping[str, Any] | None:
        run = self._run_id(expected_run_id)
        pointer = self.load_current_pointer()
        if pointer is not None and pointer.get("run_id") != run:
            raise V32RunControlStoreError(
                "V32_RUN_CONTROL_SECOND_ACTIVE_RUN_FORBIDDEN"
            )
        return pointer

    def existing_revision_zero_created_at(self, *, run_id: str) -> str | None:
        """Recover the sole timestamp from a safe pre-pointer partial write."""

        run = self._run_id(run_id)
        timestamps: set[str] = set()
        for role, (local_ref, schema_id, digest_field) in _LIVE_REVISION_ZERO_PATHS.items():
            path = self._safe_control_path(self._run_relative(run, local_ref))
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise V32RunControlStoreError(
                    f"V32_RUN_CONTROL_PARTIAL_CHECKPOINT_INVALID:{role}"
                )
            try:
                document = load_json_strict(path)
                verify_self_digest(document, digest_field)
            except (TypeError, ValueError) as exc:
                raise V32RunControlStoreError(
                    f"V32_RUN_CONTROL_PARTIAL_CHECKPOINT_INVALID:{role}"
                ) from exc
            if (
                document.get("schema_id") != schema_id
                or document.get("run_id") != run
                or document.get("revision") != 0
                or not isinstance(document.get("created_at"), str)
            ):
                raise V32RunControlStoreError(
                    f"V32_RUN_CONTROL_PARTIAL_CHECKPOINT_INVALID:{role}"
                )
            try:
                confirm_existing_bytes(path, canonical_bytes(document) + b"\n")
            except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
                raise V32RunControlStoreError(
                    f"V32_RUN_CONTROL_PARTIAL_CHECKPOINT_INVALID:{role}"
                ) from exc
            timestamps.add(str(document["created_at"]))
        receipt_path = self._safe_control_path(
            self._run_relative(run, RUN_GENESIS_REF)
        )
        if receipt_path.exists():
            try:
                receipt = load_json_strict(receipt_path)
                verify_self_digest(receipt, RUN_GENESIS_DIGEST_FIELD)
            except (TypeError, ValueError) as exc:
                raise V32RunControlStoreError(
                    "V32_RUN_CONTROL_PARTIAL_RECEIPT_INVALID"
                ) from exc
            if (
                receipt.get("schema_id") != RUN_GENESIS_SCHEMA_ID
                or receipt.get("run_id") != run
                or not isinstance(receipt.get("created_at"), str)
            ):
                raise V32RunControlStoreError(
                    "V32_RUN_CONTROL_PARTIAL_RECEIPT_INVALID"
                )
            try:
                confirm_existing_bytes(
                    receipt_path, canonical_bytes(receipt) + b"\n"
                )
            except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
                raise V32RunControlStoreError(
                    "V32_RUN_CONTROL_PARTIAL_RECEIPT_INVALID"
                ) from exc
            timestamps.add(str(receipt["created_at"]))
        if len(timestamps) > 1:
            raise V32RunControlStoreError(
                "V32_RUN_CONTROL_PARTIAL_TIMESTAMP_CONFLICT"
            )
        return next(iter(timestamps), None)

    @staticmethod
    def _verify_global_raw(
        *,
        role: str,
        payload: Any,
        document: Mapping[str, Any],
        global_binding: Mapping[str, Any],
    ) -> bytes:
        if not isinstance(payload, bytes):
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_GLOBAL_BYTES_INVALID:{role}"
            )
        if _sha256(payload) != global_binding.get("physical_sha256"):
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_GLOBAL_BYTES_DRIFT:{role}"
            )
        try:
            parsed = loads_json_strict(payload)
        except (TypeError, ValueError) as exc:
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_GLOBAL_JSON_INVALID:{role}"
            ) from exc
        if parsed != dict(document):
            raise V32RunControlStoreError(
                f"V32_RUN_CONTROL_GLOBAL_DOCUMENT_DRIFT:{role}"
            )
        return payload

    def _load_immutable_genesis_documents(
        self, *, run_id: str
    ) -> tuple[dict[str, Mapping[str, Any]], Mapping[str, Any], dict[str, Mapping[str, Any]]]:
        run = self._run_id(run_id)
        authority_copies: dict[str, Mapping[str, Any]] = {}
        for spec in GENESIS_SOURCE_SPECS:
            relative_ref = self._run_relative(run, spec.local_ref)
            document = load_json_strict(self._safe_control_path(relative_ref))
            self._read_exact(relative_ref, canonical_bytes(document) + b"\n")
            authority_copies[spec.role] = document
        timeframe_ref = self._run_relative(run, INITIAL_TIMEFRAME_REF)
        timeframe = load_json_strict(self._safe_control_path(timeframe_ref))
        self._read_exact(timeframe_ref, canonical_bytes(timeframe) + b"\n")
        checkpoints: dict[str, Mapping[str, Any]] = {}
        for role, spec in REVISION_ZERO_SPECS.items():
            relative_ref = self._run_relative(run, spec[0])
            document = load_json_strict(self._safe_control_path(relative_ref))
            self._read_exact(relative_ref, canonical_bytes(document) + b"\n")
            checkpoints[role] = document
        return authority_copies, timeframe, checkpoints

    def replay_published_genesis(
        self,
        *,
        expected_run_id: str,
        projection: Mapping[str, Mapping[str, Any]],
        global_bindings: Mapping[str, Mapping[str, Any]],
        global_raw_bytes: Mapping[str, bytes],
    ) -> Mapping[str, Any]:
        run = self._run_id(expected_run_id)
        pointer = self.assert_pointer_available(expected_run_id=run)
        if pointer is None:
            raise V32RunControlStoreError("V32_RUN_CONTROL_POINTER_MISSING")
        projection_state = validate_v32_target_projection_v1(
            projection=projection, global_bindings=global_bindings
        )
        if (
            projection_state["run_id"] != run
            or pointer.get("experiment_contract_digest")
            != projection_state["experiment_contract_digest"]
            or pointer.get("active_authority_digest")
            != projection_state["authority_digest"]
        ):
            raise V32RunControlStoreError("V32_RUN_CONTROL_POINTER_BINDING_CONFLICT")
        authority_copies, timeframe, checkpoints = self._load_immutable_genesis_documents(
            run_id=run
        )
        for spec in GENESIS_SOURCE_SPECS:
            source_payload = self._verify_global_raw(
                role=spec.role,
                payload=global_raw_bytes[spec.role],
                document=projection[spec.role],
                global_binding=global_bindings[spec.role],
            )
            local_path = self._safe_control_path(
                self._run_relative(run, spec.local_ref)
            )
            if (
                local_path.is_symlink()
                or self._read_exact(
                    self._run_relative(run, spec.local_ref), source_payload
                )
                != source_payload
                or authority_copies[spec.role] != dict(projection[spec.role])
            ):
                raise V32RunControlStoreError(
                    f"V32_RUN_CONTROL_AUTHORITY_COPY_DRIFT:{spec.role}"
                )
        receipt_ref = self._run_relative(run, RUN_GENESIS_REF)
        receipt_path = self._safe_control_path(receipt_ref)
        receipt = load_json_strict(receipt_path)
        try:
            genesis_digest = verify_v32_run_genesis_receipt_v1(
                receipt,
                projection=projection,
                global_bindings=global_bindings,
                initial_timeframe_entity=timeframe,
                revision_zero_checkpoints=checkpoints,
            )
        except (TypeError, ValueError) as exc:
            raise V32RunControlStoreError(
                "V32_RUN_CONTROL_GENESIS_REPLAY_INVALID"
            ) from exc
        self._read_exact(receipt_ref, canonical_bytes(receipt) + b"\n")
        receipt_payload = canonical_bytes(receipt) + b"\n"
        receipt_binding = self._binding(
            relative_ref=receipt_ref,
            document=receipt,
            digest_field=RUN_GENESIS_DIGEST_FIELD,
            payload=receipt_payload,
        )
        if (
            genesis_digest != receipt_binding["semantic_digest"]
            or pointer.get("run_genesis_binding") != receipt_binding
        ):
            raise V32RunControlStoreError(
                "V32_RUN_CONTROL_POINTER_GENESIS_MISMATCH"
            )
        audit_gate = receipt["qualification_boundary_audit_gate"]
        return {
            "publication_status": "EXISTING_IDENTICAL",
            "pointer": dict(pointer),
            "run_genesis": dict(receipt),
            "run_genesis_binding": receipt_binding,
            "initial_timeframe_entity": dict(timeframe),
            "revision_zero_checkpoints": {
                role: dict(document) for role, document in checkpoints.items()
            },
            "qualification_audit_source_bindings": {
                "qualification_retirement": dict(
                    audit_gate["qualification_retirement_binding"]
                ),
                "target_authority": dict(
                    audit_gate["target_authority_local_binding"]
                ),
                "run_genesis": dict(receipt_binding),
            },
            "first_analysis_permit_status": pointer[
                "first_analysis_permit_status_at_publication"
            ],
            "run_root": str(self.run_root(run)),
        }

    def seal_and_publish(
        self,
        *,
        created_at: str,
        projection: Mapping[str, Mapping[str, Any]],
        global_bindings: Mapping[str, Mapping[str, Any]],
        global_raw_bytes: Mapping[str, bytes],
        initial_timeframe_entity: Mapping[str, Any],
        revision_zero_checkpoints: Mapping[str, Mapping[str, Any]],
        _already_guarded: bool = False,
    ) -> Mapping[str, Any]:
        """Persist, replay, and only then atomically publish the sole pointer."""

        if not _already_guarded:
            with self.genesis_guard():
                return self.seal_and_publish(
                    created_at=created_at,
                    projection=projection,
                    global_bindings=global_bindings,
                    global_raw_bytes=global_raw_bytes,
                    initial_timeframe_entity=initial_timeframe_entity,
                    revision_zero_checkpoints=revision_zero_checkpoints,
                    _already_guarded=True,
                )

        projection_state = validate_v32_target_projection_v1(
            projection=projection, global_bindings=global_bindings
        )
        run = projection_state["run_id"]
        if not isinstance(global_raw_bytes, Mapping) or set(global_raw_bytes) != set(
            SOURCE_ROLES
        ):
            raise V32RunControlStoreError(
                "V32_RUN_CONTROL_GLOBAL_BYTE_SET_INVALID"
            )
        timeframe_digest = verify_v32_initial_timeframe_genesis_entity_v1(
            initial_timeframe_entity, expected_run_id=run
        )
        verify_v32_revision_zero_checkpoints_v1(
            checkpoints=revision_zero_checkpoints,
            run_id=run,
            experiment_contract_digest=projection_state[
                "experiment_contract_digest"
            ],
            active_authority_digest=projection_state["authority_digest"],
            initial_timeframe_digest=timeframe_digest,
            created_at=created_at,
        )
        existing = self.assert_pointer_available(expected_run_id=run)
        if existing is not None:
            return self.replay_published_genesis(
                expected_run_id=run,
                projection=projection,
                global_bindings=global_bindings,
                global_raw_bytes=global_raw_bytes,
            )

        local_authority_bindings: dict[str, dict[str, str]] = {}
        for spec in GENESIS_SOURCE_SPECS:
            payload = self._verify_global_raw(
                role=spec.role,
                payload=global_raw_bytes[spec.role],
                document=projection[spec.role],
                global_binding=global_bindings[spec.role],
            )
            relative_ref = self._run_relative(run, spec.local_ref)
            self._atomic_write_once_bytes(relative_ref, payload)
            readback = self._read_exact(relative_ref, payload)
            local_authority_bindings[spec.role] = self._binding(
                relative_ref=spec.local_ref,
                document=projection[spec.role],
                digest_field=spec.digest_field,
                payload=readback,
            )
            self._after_immutable_write(role=spec.role, relative_ref=relative_ref)

        timeframe_payload = _canonical_payload(initial_timeframe_entity)
        timeframe_ref = self._run_relative(run, INITIAL_TIMEFRAME_REF)
        self._atomic_write_once_bytes(timeframe_ref, timeframe_payload)
        timeframe_readback = self._read_exact(timeframe_ref, timeframe_payload)
        timeframe_binding = self._binding(
            relative_ref=INITIAL_TIMEFRAME_REF,
            document=initial_timeframe_entity,
            digest_field=TIMEFRAME_DIGEST_FIELD,
            payload=timeframe_readback,
        )
        self._after_immutable_write(
            role="initial_timeframe", relative_ref=timeframe_ref
        )

        checkpoint_bindings: dict[str, dict[str, str]] = {}
        for role, (local_ref, _schema_id, digest_field) in REVISION_ZERO_SPECS.items():
            document = revision_zero_checkpoints[role]
            payload = _canonical_payload(document)
            relative_ref = self._run_relative(run, local_ref)
            self._atomic_write_once_bytes(relative_ref, payload)
            readback = self._read_exact(relative_ref, payload)
            checkpoint_bindings[role] = self._binding(
                relative_ref=local_ref,
                document=document,
                digest_field=digest_field,
                payload=readback,
            )
            self._after_immutable_write(role=role, relative_ref=relative_ref)

        receipt = build_v32_run_genesis_receipt_v1(
            created_at=created_at,
            projection=projection,
            global_bindings=global_bindings,
            local_authority_copy_bindings=local_authority_bindings,
            initial_timeframe_entity=initial_timeframe_entity,
            initial_timeframe_binding=timeframe_binding,
            revision_zero_checkpoints=revision_zero_checkpoints,
            revision_zero_bindings=checkpoint_bindings,
        )
        receipt_payload = _canonical_payload(receipt)
        receipt_ref = self._run_relative(run, RUN_GENESIS_REF)
        self._atomic_write_once_bytes(receipt_ref, receipt_payload)
        self._read_exact(receipt_ref, receipt_payload)
        self._after_immutable_write(role="run_genesis", relative_ref=receipt_ref)
        receipt_readback = load_json_strict(self._safe_control_path(receipt_ref))
        verify_v32_run_genesis_receipt_v1(
            receipt_readback,
            projection=projection,
            global_bindings=global_bindings,
            initial_timeframe_entity=initial_timeframe_entity,
            revision_zero_checkpoints=revision_zero_checkpoints,
        )
        receipt_binding = self._binding(
            relative_ref=receipt_ref,
            document=receipt_readback,
            digest_field=RUN_GENESIS_DIGEST_FIELD,
            payload=receipt_payload,
        )
        pointer = build_v32_current_run_pointer_v1(
            published_at=created_at,
            run_id=run,
            run_genesis_binding=receipt_binding,
            experiment_contract_digest=projection_state[
                "experiment_contract_digest"
            ],
            active_authority_digest=projection_state["authority_digest"],
        )
        self._atomic_write_once_bytes(
            CURRENT_RUN_POINTER_REF, _canonical_payload(pointer)
        )
        published = self.replay_published_genesis(
            expected_run_id=run,
            projection=projection,
            global_bindings=global_bindings,
            global_raw_bytes=global_raw_bytes,
        )
        return {**dict(published), "publication_status": "CREATED"}


__all__ = [
    "CONTROL_ROOT_RELATIVE",
    "CURRENT_RUN_POINTER_REF",
    "LocalV32RunControlStore",
    "RUNS_ROOT_RELATIVE",
    "V32RunControlStoreError",
]
