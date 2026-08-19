"""Write-once V3.2 terminal receipt and independent terminal pointer.

The store derives a receipt only from already durable local bytes.  It never
replaces ``current-target-run.json``: that genesis ACTIVE pointer remains the
sole immutable publication of run creation, while ``terminal-target-run.json``
is a separate completion projection.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path, PurePosixPath
import threading
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    load_json_strict,
    verify_self_digest,
)
from ..v32_durable_json import (
    confirm_existing_bytes,
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.v32_cycle_audit_narrative import (
    DIRECTORY_DIGEST_FIELD,
    DIRECTORY_SCHEMA_ID,
)
from ..domain.v32_run_genesis import (
    CURRENT_RUN_POINTER_DIGEST_FIELD,
    CURRENT_RUN_POINTER_SCHEMA_ID,
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_REF,
    RUN_GENESIS_SCHEMA_ID,
    verify_v32_current_run_pointer_v1,
)
from ..domain.v32_terminal_seal import (
    TERMINAL_POINTER_DIGEST_FIELD,
    TERMINAL_RECEIPT_DIGEST_FIELD,
    build_v32_terminal_pointer_v1,
    build_v32_terminal_receipt_v1,
    verify_v32_terminal_pointer_v1,
    verify_v32_terminal_receipt_v1,
)


class V32TerminalSealStoreError(ValueError):
    """A terminal-seal durability or replay invariant failed closed."""


TERMINAL_RECEIPT_REF = "terminal/terminal-receipt.json"
TERMINAL_POINTER_REF = "terminal-target-run.json"
ACTIVE_POINTER_REF = "current-target-run.json"
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_CHECKPOINT_SPECS = {
    "supervisor": (
        "v32-tick-supervisor-v1/checkpoint.json",
        "tick_supervisor_checkpoint_digest",
    ),
    "dynamic": (
        "v32-dynamic-cycle-v1/checkpoint.json",
        "dynamic_research_checkpoint_digest",
    ),
    "outcome": ("outcome-v32/checkpoint.json", "checkpoint_digest"),
}


class LocalV32TerminalSealStore:
    """Local terminal publisher with no market, Agent, or execution capability."""

    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root).absolute()
        if supplied.exists() and supplied.is_symlink():
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_RUN_ROOT_SYMLINK_FORBIDDEN"
            )
        ensure_directory_tree(supplied)
        if supplied.is_symlink() or not supplied.is_dir():
            raise V32TerminalSealStoreError("V32_TERMINAL_STORE_RUN_ROOT_INVALID")
        if supplied.parent.name != "runs":
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_CONTROL_LAYOUT_INVALID"
            )
        self.run_root = supplied
        self.control_root = supplied.parent.parent
        if self.control_root.is_symlink() or not self.control_root.is_dir():
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_CONTROL_ROOT_INVALID"
            )
        self._run_physical = supplied.resolve(strict=True)
        self._control_physical = self.control_root.resolve(strict=True)

    def _assert_roots(self) -> None:
        if (
            self.run_root.is_symlink()
            or not self.run_root.is_dir()
            or self.run_root.resolve(strict=True) != self._run_physical
            or self.control_root.is_symlink()
            or not self.control_root.is_dir()
            or self.control_root.resolve(strict=True) != self._control_physical
        ):
            raise V32TerminalSealStoreError("V32_TERMINAL_STORE_ROOT_CHANGED")

    def _safe(self, root: Path, relative_ref: str) -> Path:
        self._assert_roots()
        lexical = PurePosixPath(relative_ref)
        if (
            not isinstance(relative_ref, str)
            or not relative_ref
            or "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32TerminalSealStoreError("V32_TERMINAL_STORE_PATH_INVALID")
        physical = self._run_physical if root == self.run_root else self._control_physical
        current = root
        try:
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32TerminalSealStoreError(
                        "V32_TERMINAL_STORE_SYMLINK_FORBIDDEN"
                    )
            current.resolve(strict=False).relative_to(physical)
        except V32TerminalSealStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_PATH_INVALID"
            ) from exc
        return current

    @contextmanager
    def _lock(self):
        path = self._safe(self.control_root, ".locks/terminal-seal.lock")
        ensure_directory_tree(path.parent)
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    @staticmethod
    def _payload(document: Mapping[str, Any]) -> bytes:
        return canonical_bytes(dict(document)) + b"\n"

    def _load(self, root: Path, relative_ref: str) -> Mapping[str, Any]:
        path = self._safe(root, relative_ref)
        if path.is_symlink() or not path.is_file():
            raise V32TerminalSealStoreError("V32_TERMINAL_STORE_DOCUMENT_MISSING")
        try:
            document = load_json_strict(path)
        except (OSError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_DOCUMENT_INVALID"
            ) from exc
        if path.read_bytes() != self._payload(document):
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_DOCUMENT_NONCANONICAL"
            )
        try:
            confirm_existing_json(path, document)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_DOCUMENT_INVALID"
            ) from exc
        return document

    def _write_once(
        self, root: Path, relative_ref: str, document: Mapping[str, Any]
    ) -> str:
        target = self._safe(root, relative_ref)
        ensure_directory_tree(target.parent)
        target = self._safe(root, relative_ref)
        try:
            return write_once_json(target, document)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_WRITE_ONCE_CONFLICT"
            ) from exc

    @staticmethod
    def _binding(
        *, relative_ref: str, document: Mapping[str, Any], digest_field: str
    ) -> dict[str, str]:
        try:
            semantic = verify_self_digest(document, digest_field)
        except (TypeError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_DIGEST_INVALID"
            ) from exc
        payload = canonical_bytes(dict(document)) + b"\n"
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }

    def _verify_binding_file(
        self,
        *,
        root: Path,
        binding: Mapping[str, Any],
        expected_document: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        if not isinstance(binding, Mapping) or set(binding) != {
            "relative_ref",
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
        }:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_BINDING_INVALID"
            )
        document = self._load(root, str(binding["relative_ref"]))
        if expected_document is not None and dict(document) != dict(expected_document):
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_BOUND_DOCUMENT_DRIFT"
            )
        actual = self._binding(
            relative_ref=str(binding["relative_ref"]),
            document=document,
            digest_field=str(binding["digest_field"]),
        )
        if actual != dict(binding):
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_BINDING_DRIFT"
            )
        return document

    def _load_exact_checkpoint(
        self, *, role: str, supplied: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        relative_ref, digest_field = _CHECKPOINT_SPECS[role]
        durable = self._load(self.run_root, relative_ref)
        if dict(durable) != dict(supplied):
            raise V32TerminalSealStoreError(
                f"V32_TERMINAL_STORE_CHECKPOINT_DRIFT:{role}"
            )
        return durable, self._binding(
            relative_ref=relative_ref,
            document=durable,
            digest_field=digest_field,
        )

    def _audit_binding(
        self, *, run_id: str, material: Mapping[str, Any]
    ) -> dict[str, Any]:
        boundary = str(material.get("boundary_type"))
        cycle = material.get("cycle_index")
        directory = material.get("directory")
        if (
            boundary not in {"QUALIFICATION", "ANALYSIS", "ACCEPTANCE", "OUTCOME", "RECOVERY"}
            or isinstance(cycle, bool)
            or not isinstance(cycle, int)
            or not isinstance(directory, Mapping)
            or directory.get("schema_id") != DIRECTORY_SCHEMA_ID
            or directory.get("run_id") != run_id
            or directory.get("cycle_index") != cycle
            or directory.get("boundary_type") != boundary
        ):
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_AUDIT_MATERIAL_INVALID"
            )
        try:
            digest = verify_self_digest(directory, DIRECTORY_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_AUDIT_MATERIAL_INVALID"
            ) from exc
        relative_ref = (
            f"v32-authorized-revisions-v1/{run_id}/cycles/{cycle:04d}/audit/"
            f"{boundary.lower()}/{digest}.json"
        )
        durable = self._load(self.run_root, relative_ref)
        if dict(durable) != dict(directory):
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_AUDIT_DIRECTORY_DRIFT"
            )
        return {
            "boundary_type": boundary,
            "cycle_index": cycle,
            "binding": self._binding(
                relative_ref=relative_ref,
                document=durable,
                digest_field=DIRECTORY_DIGEST_FIELD,
            ),
        }

    def load_terminal_pointer(self, *, run_id: str) -> Mapping[str, Any] | None:
        path = self._safe(self.control_root, TERMINAL_POINTER_REF)
        if not path.exists():
            return None
        pointer = self._load(self.control_root, TERMINAL_POINTER_REF)
        receipt = self._load(self.run_root, TERMINAL_RECEIPT_REF)
        try:
            verify_v32_terminal_pointer_v1(pointer, terminal_receipt=receipt)
        except (TypeError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_POINTER_INVALID"
            ) from exc
        if pointer.get("run_id") != run_id:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_SECOND_TERMINAL_RUN_FORBIDDEN"
            )
        supervisor = self._load(
            self.run_root, _CHECKPOINT_SPECS["supervisor"][0]
        )
        dynamic = self._load(self.run_root, _CHECKPOINT_SPECS["dynamic"][0])
        outcome = self._load(self.run_root, _CHECKPOINT_SPECS["outcome"][0])
        try:
            verify_v32_terminal_receipt_v1(
                receipt,
                supervisor_checkpoint=supervisor,
                dynamic_checkpoint=dynamic,
                outcome_checkpoint=outcome,
            )
        except (TypeError, ValueError) as exc:
            raise V32TerminalSealStoreError(
                "V32_TERMINAL_STORE_RECEIPT_INVALID"
            ) from exc
        self._verify_binding_file(
            root=self.control_root,
            binding=receipt["run_genesis_binding"],
        )
        self._verify_binding_file(
            root=self.control_root,
            binding=receipt["active_genesis_pointer_binding"],
        )
        for field, document in (
            ("supervisor_checkpoint_binding", supervisor),
            ("dynamic_checkpoint_binding", dynamic),
            ("outcome_checkpoint_binding", outcome),
        ):
            self._verify_binding_file(
                root=self.run_root,
                binding=receipt[field],
                expected_document=document,
            )
        for row in [
            *receipt["required_audit_directory_bindings"],
            *receipt["recovery_audit_directory_bindings"],
        ]:
            self._verify_binding_file(
                root=self.run_root, binding=row["binding"]
            )
        for field in (
            "supervisor_observation_bindings",
            "deterministic_recovery_receipt_bindings",
        ):
            for evidence_binding in receipt[field]:
                self._verify_binding_file(
                    root=self.run_root, binding=evidence_binding
                )
        self._verify_binding_file(
            root=self.run_root,
            binding=pointer["terminal_receipt_binding"],
            expected_document=receipt,
        )
        return pointer

    def seal_terminal(
        self,
        *,
        run_id: str,
        sealed_at: str,
        supervisor_checkpoint: Mapping[str, Any],
        dynamic_checkpoint: Mapping[str, Any],
        outcome_checkpoint: Mapping[str, Any],
        required_audit_materials: Sequence[Mapping[str, Any]],
        recovery_audit_materials: Sequence[Mapping[str, Any]],
        supervision_material_bindings: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Seal one terminal boundary, replay-safe after a partial crash."""

        if run_id != self.run_root.name:
            raise V32TerminalSealStoreError("V32_TERMINAL_STORE_RUN_MISMATCH")
        with self._lock():
            existing_pointer = self.load_terminal_pointer(run_id=run_id)
            genesis = self._load(self.run_root, RUN_GENESIS_REF)
            active_pointer = self._load(self.control_root, ACTIVE_POINTER_REF)
            try:
                verify_self_digest(genesis, RUN_GENESIS_DIGEST_FIELD)
                verify_v32_current_run_pointer_v1(active_pointer)
            except (TypeError, ValueError) as exc:
                raise V32TerminalSealStoreError(
                    "V32_TERMINAL_STORE_GENESIS_INVALID"
                ) from exc
            if (
                genesis.get("schema_id") != RUN_GENESIS_SCHEMA_ID
                or genesis.get("run_id") != run_id
                or active_pointer.get("schema_id") != CURRENT_RUN_POINTER_SCHEMA_ID
                or active_pointer.get("run_id") != run_id
                or active_pointer.get("status") != "ACTIVE"
            ):
                raise V32TerminalSealStoreError(
                    "V32_TERMINAL_STORE_GENESIS_INVALID"
                )
            active_payload_before = self._payload(active_pointer)
            genesis_binding = self._binding(
                relative_ref=f"runs/{run_id}/{RUN_GENESIS_REF}",
                document=genesis,
                digest_field=RUN_GENESIS_DIGEST_FIELD,
            )
            active_binding = self._binding(
                relative_ref=ACTIVE_POINTER_REF,
                document=active_pointer,
                digest_field=CURRENT_RUN_POINTER_DIGEST_FIELD,
            )
            if active_pointer.get("run_genesis_binding") != genesis_binding:
                raise V32TerminalSealStoreError(
                    "V32_TERMINAL_STORE_GENESIS_POINTER_DRIFT"
                )
            supervisor, supervisor_binding = self._load_exact_checkpoint(
                role="supervisor", supplied=supervisor_checkpoint
            )
            dynamic, dynamic_binding = self._load_exact_checkpoint(
                role="dynamic", supplied=dynamic_checkpoint
            )
            outcome, outcome_binding = self._load_exact_checkpoint(
                role="outcome", supplied=outcome_checkpoint
            )
            required = [
                self._audit_binding(run_id=run_id, material=row)
                for row in required_audit_materials
            ]
            recovery = [
                self._audit_binding(run_id=run_id, material=row)
                for row in recovery_audit_materials
            ]
            materials = dict(supervision_material_bindings or {})
            observations = materials.get("supervisor_observation_bindings", [])
            recoveries = materials.get("deterministic_recovery_receipt_bindings", [])

            receipt_path = self._safe(self.run_root, TERMINAL_RECEIPT_REF)
            if receipt_path.exists():
                receipt = self._load(self.run_root, TERMINAL_RECEIPT_REF)
            else:
                receipt = build_v32_terminal_receipt_v1(
                    run_id=run_id,
                    sealed_at=sealed_at,
                    run_genesis_binding=genesis_binding,
                    active_genesis_pointer_binding=active_binding,
                    supervisor_checkpoint=supervisor,
                    supervisor_checkpoint_binding=supervisor_binding,
                    dynamic_checkpoint=dynamic,
                    dynamic_checkpoint_binding=dynamic_binding,
                    outcome_checkpoint=outcome,
                    outcome_checkpoint_binding=outcome_binding,
                    required_audit_directory_bindings=required,
                    recovery_audit_directory_bindings=recovery,
                    supervisor_observation_bindings=observations,
                    deterministic_recovery_receipt_bindings=recoveries,
                )
                self._write_once(self.run_root, TERMINAL_RECEIPT_REF, receipt)
            try:
                verify_v32_terminal_receipt_v1(
                    receipt,
                    supervisor_checkpoint=supervisor,
                    dynamic_checkpoint=dynamic,
                    outcome_checkpoint=outcome,
                )
            except (TypeError, ValueError) as exc:
                raise V32TerminalSealStoreError(
                    "V32_TERMINAL_STORE_RECEIPT_INVALID"
                ) from exc
            if (
                receipt.get("required_audit_directory_bindings") != required
                or receipt.get("recovery_audit_directory_bindings") != recovery
                or receipt.get("supervisor_observation_bindings") != observations
                or receipt.get("deterministic_recovery_receipt_bindings") != recoveries
            ):
                raise V32TerminalSealStoreError(
                    "V32_TERMINAL_STORE_RECEIPT_INPUT_DRIFT"
                )
            receipt_binding = self._binding(
                relative_ref=TERMINAL_RECEIPT_REF,
                document=receipt,
                digest_field=TERMINAL_RECEIPT_DIGEST_FIELD,
            )
            if existing_pointer is None:
                pointer = build_v32_terminal_pointer_v1(
                    run_id=run_id,
                    published_at=str(receipt["sealed_at"]),
                    run_genesis_binding=genesis_binding,
                    terminal_receipt_binding=receipt_binding,
                    active_genesis_pointer_binding=active_binding,
                )
                pointer_status = self._write_once(
                    self.control_root, TERMINAL_POINTER_REF, pointer
                )
            else:
                pointer = existing_pointer
                pointer_status = "EXISTING_IDENTICAL"
            try:
                verify_v32_terminal_pointer_v1(pointer, terminal_receipt=receipt)
            except (TypeError, ValueError) as exc:
                raise V32TerminalSealStoreError(
                    "V32_TERMINAL_STORE_POINTER_INVALID"
                ) from exc
            try:
                confirm_existing_bytes(
                    self._safe(self.control_root, ACTIVE_POINTER_REF),
                    active_payload_before,
                )
            except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
                raise V32TerminalSealStoreError(
                    "V32_TERMINAL_STORE_ACTIVE_POINTER_MUTATED"
                ) from exc
            return {
                "status": "TERMINAL_SEALED",
                "terminal_receipt_digest": receipt[
                    TERMINAL_RECEIPT_DIGEST_FIELD
                ],
                "terminal_pointer_digest": pointer[
                    TERMINAL_POINTER_DIGEST_FIELD
                ],
                "terminal_pointer_write_status": pointer_status,
                "required_audit_directory_count": len(required),
                "recovery_audit_directory_count": len(recovery),
                "active_genesis_pointer_preserved": True,
                "high_level_boundaries_completed": 1,
                "network_requests": 0,
                "agent_attempts": 0,
                "account_access": False,
                "order_submission": False,
                "executable": False,
            }


__all__ = [
    "ACTIVE_POINTER_REF",
    "LocalV32TerminalSealStore",
    "TERMINAL_POINTER_REF",
    "TERMINAL_RECEIPT_REF",
    "V32TerminalSealStoreError",
]
