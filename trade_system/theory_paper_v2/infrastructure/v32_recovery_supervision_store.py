"""Append-only local evidence for V3.2 read-only supervision.

This adapter stores only an immutable policy, observations, and deterministic
recovery receipts that have already been built by the pure domain contracts.
It exposes a read-only alert projection and has deliberately no controller,
network, clock, Agent, market, account, or execution method.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    load_json_strict,
    verify_self_digest,
)
from ..v32_durable_json import (
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.v32_recovery_supervision import (
    OBSERVATION_DIGEST_FIELD,
    POLICY_DIGEST_FIELD,
    RECOVERY_DIGEST_FIELD,
    verify_v32_deterministic_recovery_receipt_v1,
    verify_v32_recovery_supervision_policy_v1,
    verify_v32_supervisor_observation_v1,
)


class V32RecoverySupervisionStoreError(ValueError):
    """A supervision evidence-store invariant failed closed."""


STORE_ROOT = "v32-recovery-supervision-v1"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


class LocalV32RecoverySupervisionStore:
    """Independent observer evidence; never mutates any formal run store."""

    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root).absolute()
        if supplied.exists() and supplied.is_symlink():
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_ROOT_SYMLINK_FORBIDDEN"
            )
        ensure_directory_tree(supplied)
        if supplied.is_symlink() or not supplied.is_dir():
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_ROOT_INVALID"
            )
        self.run_root = supplied
        self._physical_root = supplied.resolve(strict=True)

    @staticmethod
    def _run_id(value: Any) -> str:
        if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_RUN_INVALID"
            )
        return value

    def _safe_path(self, relative_ref: str) -> Path:
        if (
            not self.run_root.is_dir()
            or self.run_root.is_symlink()
            or self.run_root.resolve(strict=True) != self._physical_root
        ):
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_ROOT_CHANGED"
            )
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
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_PATH_INVALID"
            )
        current = self.run_root
        try:
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32RecoverySupervisionStoreError(
                        "V32_SUPERVISION_STORE_SYMLINK_FORBIDDEN"
                    )
            current.resolve(strict=False).relative_to(self._physical_root)
        except V32RecoverySupervisionStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_PATH_INVALID"
            ) from exc
        return current

    @contextmanager
    def _lock(self):
        path = self._safe_path(f"{STORE_ROOT}/.locks/store.lock")
        ensure_directory_tree(path.parent)
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    def _write_once(self, relative_ref: str, document: Mapping[str, Any]) -> str:
        target = self._safe_path(relative_ref)
        ensure_directory_tree(target.parent)
        target = self._safe_path(relative_ref)
        try:
            return write_once_json(target, document)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_WRITE_ONCE_CONFLICT"
            ) from exc

    def _load_canonical(self, path: Path) -> Mapping[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_DOCUMENT_INVALID"
            )
        try:
            document = load_json_strict(path)
        except (OSError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_DOCUMENT_INVALID"
            ) from exc
        if path.read_bytes() != canonical_bytes(dict(document)) + b"\n":
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_NONCANONICAL_DOCUMENT"
            )
        try:
            confirm_existing_json(path, document)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_DOCUMENT_INVALID"
            ) from exc
        return document

    def _binding(
        self, *, relative_ref: str, document: Mapping[str, Any], digest_field: str
    ) -> dict[str, str]:
        try:
            semantic = verify_self_digest(document, digest_field)
        except (TypeError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_DOCUMENT_DIGEST_INVALID"
            ) from exc
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": _physical(document),
        }

    def persist_policy(self, *, policy: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            digest = verify_v32_recovery_supervision_policy_v1(policy)
        except (TypeError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_POLICY_INVALID"
            ) from exc
        relative_ref = f"{STORE_ROOT}/policy/{digest}.json"
        with self._lock():
            status = self._write_once(relative_ref, policy)
            readback = self._load_canonical(self._safe_path(relative_ref))
            verify_v32_recovery_supervision_policy_v1(readback)
        return {
            "status": status,
            "binding": self._binding(
                relative_ref=relative_ref,
                document=readback,
                digest_field=POLICY_DIGEST_FIELD,
            ),
        }

    def persist_observation(
        self, *, policy: Mapping[str, Any], observation: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            digest = verify_v32_supervisor_observation_v1(
                observation, policy=policy
            )
        except (TypeError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_OBSERVATION_INVALID"
            ) from exc
        run = self._run_id(observation.get("run_id"))
        cycle = int(observation["cycle_index"])
        relative_ref = (
            f"{STORE_ROOT}/{run}/observations/{cycle:04d}/{digest}.json"
        )
        self.persist_policy(policy=policy)
        with self._lock():
            status = self._write_once(relative_ref, observation)
            readback = self._load_canonical(self._safe_path(relative_ref))
            verify_v32_supervisor_observation_v1(readback, policy=policy)
        return {
            "status": status,
            "binding": self._binding(
                relative_ref=relative_ref,
                document=readback,
                digest_field=OBSERVATION_DIGEST_FIELD,
            ),
            "formal_state_mutations": 0,
            "network_requests": 0,
            "agent_attempts": 0,
        }

    def persist_recovery_receipt(
        self,
        *,
        policy: Mapping[str, Any],
        observation: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            digest = verify_v32_deterministic_recovery_receipt_v1(
                receipt, policy=policy, observation=observation
            )
        except (TypeError, ValueError) as exc:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_RECOVERY_INVALID"
            ) from exc
        run = self._run_id(receipt.get("run_id"))
        cycle = int(receipt["cycle_index"])
        relative_ref = f"{STORE_ROOT}/{run}/recoveries/{cycle:04d}/{digest}.json"
        self.persist_policy(policy=policy)
        observation_result = self.persist_observation(
            policy=policy, observation=observation
        )
        with self._lock():
            status = self._write_once(relative_ref, receipt)
            readback = self._load_canonical(self._safe_path(relative_ref))
            verify_v32_deterministic_recovery_receipt_v1(
                readback, policy=policy, observation=observation
            )
        return {
            "status": status,
            "binding": self._binding(
                relative_ref=relative_ref,
                document=readback,
                digest_field=RECOVERY_DIGEST_FIELD,
            ),
            "observation_binding": observation_result["binding"],
            "network_requests": 0,
            "agent_attempts": 0,
            "outcome_reads": 0,
        }

    def _documents(self, *, run_id: str, kind: str) -> list[Mapping[str, Any]]:
        run = self._run_id(run_id)
        root = self._safe_path(f"{STORE_ROOT}/{run}/{kind}")
        if not root.exists():
            return []
        if root.is_symlink() or not root.is_dir():
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_LAYOUT_INVALID"
            )
        result: list[Mapping[str, Any]] = []
        for cycle_root in sorted(root.iterdir(), key=lambda row: row.name):
            if cycle_root.is_symlink() or not cycle_root.is_dir():
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_LAYOUT_INVALID"
                )
            for path in sorted(cycle_root.iterdir(), key=lambda row: row.name):
                result.append(self._load_canonical(path))
        return result

    def load_alert_status(self, *, run_id: str) -> Mapping[str, Any] | None:
        """Return a projection only; this method never writes a byte."""

        observations = self._documents(run_id=run_id, kind="observations")
        if not observations:
            if self._documents(run_id=run_id, kind="recoveries"):
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_RECOVERY_ORPHANED"
                )
            return None
        policy_digests = {str(row.get("policy_digest")) for row in observations}
        if len(policy_digests) != 1:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_POLICY_DRIFT"
            )
        policy_digest = next(iter(policy_digests))
        policy_path = self._safe_path(
            f"{STORE_ROOT}/policy/{policy_digest}.json"
        )
        policy = self._load_canonical(policy_path)
        try:
            observation_digests = [
                verify_v32_supervisor_observation_v1(row, policy=policy)
                for row in observations
            ]
            receipts = self._documents(run_id=run_id, kind="recoveries")
            by_observation = {digest: row for digest, row in zip(observation_digests, observations)}
            recovered: set[str] = set()
            for receipt in receipts:
                observed_digest = str(receipt.get("supervisor_observation_digest"))
                observation = by_observation.get(observed_digest)
                if observation is None:
                    raise V32RecoverySupervisionStoreError(
                        "V32_SUPERVISION_STORE_RECOVERY_ORPHANED"
                    )
                verify_v32_deterministic_recovery_receipt_v1(
                    receipt, policy=policy, observation=observation
                )
                recovered.add(observed_digest)
        except (TypeError, ValueError) as exc:
            if isinstance(exc, V32RecoverySupervisionStoreError):
                raise
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_ALERT_REPLAY_INVALID"
            ) from exc
        unresolved = [
            row
            for digest, row in zip(observation_digests, observations)
            if digest not in recovered
            and (
                row.get("severity") == "STOP"
                or row.get("disposition") != "NO_ACTION"
            )
        ]
        if any(row.get("severity") == "STOP" for row in unresolved):
            status = "STOP"
        elif any(
            row.get("disposition") == "SAME_RUN_DETERMINISTIC_RECOVERY_ALLOWED"
            for row in unresolved
        ):
            status = "RECOVERY_PENDING"
        elif unresolved:
            status = "ATTENTION_REQUIRED"
        else:
            status = "CLEAR"
        latest = max(
            zip(observation_digests, observations),
            key=lambda row: (str(row[1]["observed_at"]), str(row[1]["observation_id"])),
        )
        return {
            "status": status,
            "observation_count": len(observations),
            "deterministic_recovery_receipt_count": len(receipts),
            "unresolved_count": len(unresolved),
            "latest_observation_digest": latest[0],
            "latest_severity": latest[1]["severity"],
            "latest_disposition": latest[1]["disposition"],
            "read_only_projection": True,
            "formal_state_mutations": 0,
            "network_requests": 0,
            "agent_attempts": 0,
        }

    def load_material_bindings(self, *, run_id: str) -> Mapping[str, Any]:
        """Return immutable observation/recovery bindings for terminal sealing."""

        run = self._run_id(run_id)
        observations = self._documents(run_id=run, kind="observations")
        receipts = self._documents(run_id=run, kind="recoveries")
        if receipts and not observations:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_RECOVERY_ORPHANED"
            )
        if observations:
            policy_digests = {str(row.get("policy_digest")) for row in observations}
            if len(policy_digests) != 1:
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_POLICY_DRIFT"
                )
            policy = self._load_canonical(
                self._safe_path(
                    f"{STORE_ROOT}/policy/{next(iter(policy_digests))}.json"
                )
            )
            try:
                for observation in observations:
                    verify_v32_supervisor_observation_v1(
                        observation, policy=policy
                    )
            except (TypeError, ValueError) as exc:
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_OBSERVATION_INVALID"
                ) from exc
            if receipts:
                # This performs the observation-to-receipt replay as well as
                # the zero-network/zero-Agent receipt verification.
                self.load_recovery_audit_materials(run_id=run)
        output: dict[str, list[dict[str, str]]] = {
            "supervisor_observation_bindings": [],
            "deterministic_recovery_receipt_bindings": [],
        }
        for kind, key, digest_field in (
            ("observations", "supervisor_observation_bindings", OBSERVATION_DIGEST_FIELD),
            ("recoveries", "deterministic_recovery_receipt_bindings", RECOVERY_DIGEST_FIELD),
        ):
            root = self._safe_path(f"{STORE_ROOT}/{run}/{kind}")
            if not root.exists():
                continue
            documents = self._documents(run_id=run, kind=kind)
            paths = sorted(
                path
                for cycle_root in root.iterdir()
                for path in cycle_root.iterdir()
            )
            if len(paths) != len(documents):
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_LAYOUT_INVALID"
                )
            output[key] = sorted(
                [
                    self._binding(
                        relative_ref=path.relative_to(self.run_root).as_posix(),
                        document=document,
                        digest_field=digest_field,
                    )
                    for path, document in zip(paths, documents)
                ],
                key=lambda row: row["relative_ref"],
            )
        return output

    def load_recovery_audit_materials(
        self, *, run_id: str
    ) -> list[Mapping[str, Any]]:
        """Project sealed recovery evidence by cycle without writing state."""

        run = self._run_id(run_id)
        observations = self._documents(run_id=run, kind="observations")
        receipts = self._documents(run_id=run, kind="recoveries")
        if not receipts:
            return []
        policy_digests = {str(row.get("policy_digest")) for row in observations}
        if len(policy_digests) != 1:
            raise V32RecoverySupervisionStoreError(
                "V32_SUPERVISION_STORE_POLICY_DRIFT"
            )
        policy = self._load_canonical(
            self._safe_path(
                f"{STORE_ROOT}/policy/{next(iter(policy_digests))}.json"
            )
        )
        observations_by_digest: dict[str, Mapping[str, Any]] = {}
        for observation in observations:
            try:
                observation_digest = verify_v32_supervisor_observation_v1(
                    observation, policy=policy
                )
            except (TypeError, ValueError) as exc:
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_OBSERVATION_INVALID"
                ) from exc
            observations_by_digest[observation_digest] = observation
        grouped: dict[int, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
        for receipt in receipts:
            observation = observations_by_digest.get(
                str(receipt.get("supervisor_observation_digest"))
            )
            if observation is None:
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_RECOVERY_ORPHANED"
                )
            try:
                verify_v32_deterministic_recovery_receipt_v1(
                    receipt, policy=policy, observation=observation
                )
            except (TypeError, ValueError) as exc:
                raise V32RecoverySupervisionStoreError(
                    "V32_SUPERVISION_STORE_RECOVERY_INVALID"
                ) from exc
            grouped.setdefault(int(receipt["cycle_index"]), []).append(
                (observation, receipt)
            )
        result: list[Mapping[str, Any]] = []
        for cycle, pairs in sorted(grouped.items()):
            sealed_sources: list[Mapping[str, Any]] = []
            for index, (observation, receipt) in enumerate(
                sorted(pairs, key=lambda pair: str(pair[1]["completed_at"])), start=1
            ):
                observation_digest = observation[OBSERVATION_DIGEST_FIELD]
                receipt_digest = receipt[RECOVERY_DIGEST_FIELD]
                observation_ref = (
                    f"{STORE_ROOT}/{run}/observations/{cycle:04d}/"
                    f"{observation_digest}.json"
                )
                receipt_ref = (
                    f"{STORE_ROOT}/{run}/recoveries/{cycle:04d}/{receipt_digest}.json"
                )
                sealed_sources.extend(
                    [
                        {
                            "role": f"supervisor_observation_{index:04d}",
                            "document": dict(observation),
                            "binding": self._binding(
                                relative_ref=observation_ref,
                                document=observation,
                                digest_field=OBSERVATION_DIGEST_FIELD,
                            ),
                        },
                        {
                            "role": f"deterministic_recovery_receipt_{index:04d}",
                            "document": dict(receipt),
                            "binding": self._binding(
                                relative_ref=receipt_ref,
                                document=receipt,
                                digest_field=RECOVERY_DIGEST_FIELD,
                            ),
                        },
                    ]
                )
            result.append(
                {
                    "cycle_index": cycle,
                    "boundary_sealed_at": max(
                        str(receipt["completed_at"]) for _observation, receipt in pairs
                    ),
                    "sealed_sources": sealed_sources,
                }
            )
        return result


__all__ = [
    "LocalV32RecoverySupervisionStore",
    "STORE_ROOT",
    "V32RecoverySupervisionStoreError",
]
