"""Local durable store for the V3.1 two-stage Agent transport.

All business mutations require one held owner lease.  Stage artifacts are
write-once; the small transport checkpoint is the only CAS-replaced object.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import fcntl
import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.v31_agent_transport import (
    validate_v31_transport_binding,
    validate_v31_transport_evidence,
)


class V31AgentTransportStoreError(ValueError):
    """The local V3.1 transport store failed closed."""


@dataclass(frozen=True)
class V31TransportOwnerLease:
    owner_id: str
    lease_token: str


_LEASE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "revision",
        "owner_id",
        "lease_token",
        "acquired_at",
        "expires_at",
        "status",
        "previous_lease_digest",
        "lease_digest",
    }
)


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31AgentTransportStoreError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31AgentTransportStoreError(code) from exc
    if parsed.tzinfo is None:
        raise V31AgentTransportStoreError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31AgentTransportStoreError(code)
    return parsed.astimezone(UTC)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalV31AgentTransportStore:
    """Filesystem adapter with write-once artifacts, owner lease, and CAS."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._active_lease: V31TransportOwnerLease | None = None
        self._lock_descriptor: int | None = None

    def _resolved_root(self, *, create: bool) -> Path:
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        try:
            resolved = self.root.resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_STORE_ROOT_INVALID"
            ) from exc
        if not resolved.is_dir() or self.root.is_symlink():
            raise V31AgentTransportStoreError("V31_TRANSPORT_STORE_ROOT_INVALID")
        return resolved

    def _safe_path(self, relative_ref: str, *, create_parent: bool = False) -> Path:
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V31AgentTransportStoreError("V31_TRANSPORT_STORE_REF_INVALID")
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V31AgentTransportStoreError("V31_TRANSPORT_STORE_REF_INVALID")
        root = self._resolved_root(create=create_parent)
        current = root
        for part in lexical.parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise V31AgentTransportStoreError(
                    "V31_TRANSPORT_STORE_SYMLINK_FORBIDDEN"
                )
            if create_parent:
                current.mkdir(exist_ok=True)
        target = root.joinpath(*lexical.parts)
        if target.exists() and target.is_symlink():
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_STORE_SYMLINK_FORBIDDEN"
            )
        if target.parent.exists():
            try:
                target.parent.resolve(strict=True).relative_to(root)
            except (OSError, ValueError) as exc:
                raise V31AgentTransportStoreError(
                    "V31_TRANSPORT_STORE_REF_INVALID"
                ) from exc
        return target

    def _atomic_replace(self, path: Path, document: Mapping[str, Any]) -> None:
        payload = canonical_bytes(dict(document)) + b"\n"
        temporary = path.with_name(
            f".{path.name}.{os.getpid()}.{canonical_digest(document)[:12]}.tmp"
        )
        try:
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_STORE_ATOMIC_REPLACE_FAILED"
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()

    def _load_lease(self) -> dict[str, Any] | None:
        path = self._safe_path(".v31-agent-owner-lease.json", create_parent=True)
        if not path.exists():
            return None
        try:
            document = load_json_strict(path)
            verify_self_digest(document, "lease_digest")
        except (CanonicalContractError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_OWNER_LEASE_INVALID"
            ) from exc
        if (
            set(document) != _LEASE_FIELDS
            or document.get("schema_id")
            != "theory_paper_v31_agent_transport_owner_lease"
            or document.get("schema_version") != "1.0.0"
            or document.get("status") not in {"ACTIVE", "RELEASED"}
        ):
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_OWNER_LEASE_INVALID"
            )
        return document

    @contextmanager
    def owner_lease(
        self,
        *,
        owner_id: str,
        acquired_at: str,
        expires_at: str,
    ) -> Iterator[V31TransportOwnerLease]:
        if (
            not isinstance(owner_id, str)
            or not owner_id.strip()
            or owner_id != owner_id.strip()
            or self._active_lease is not None
        ):
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_OWNER_LEASE_REQUEST_INVALID"
            )
        acquired = _timestamp(acquired_at, "V31_TRANSPORT_LEASE_TIME_INVALID")
        expires = _timestamp(expires_at, "V31_TRANSPORT_LEASE_TIME_INVALID")
        if expires <= acquired:
            raise V31AgentTransportStoreError("V31_TRANSPORT_LEASE_TIME_INVALID")
        root = self._resolved_root(create=True)
        lock_path = root / ".v31-agent-mutation.lock"
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise V31AgentTransportStoreError(
                    "V31_TRANSPORT_OWNER_LEASE_HELD"
                ) from exc
            previous = self._load_lease()
            if (
                previous is not None
                and previous["status"] == "ACTIVE"
                and _timestamp(
                    previous["expires_at"], "V31_TRANSPORT_OWNER_LEASE_INVALID"
                )
                > acquired
            ):
                raise V31AgentTransportStoreError(
                    "V31_TRANSPORT_OWNER_LEASE_HELD"
                )
            revision = 1 if previous is None else int(previous["revision"]) + 1
            previous_digest = None if previous is None else previous["lease_digest"]
            lease_token = canonical_digest(
                {
                    "owner_id": owner_id,
                    "revision": revision,
                    "acquired_at": acquired_at,
                    "previous_lease_digest": previous_digest,
                }
            )
            active = self_digest(
                {
                    "schema_id": "theory_paper_v31_agent_transport_owner_lease",
                    "schema_version": "1.0.0",
                    "revision": revision,
                    "owner_id": owner_id,
                    "lease_token": lease_token,
                    "acquired_at": acquired_at,
                    "expires_at": expires_at,
                    "status": "ACTIVE",
                    "previous_lease_digest": previous_digest,
                },
                "lease_digest",
            )
            lease_path = self._safe_path(
                ".v31-agent-owner-lease.json", create_parent=True
            )
            self._atomic_replace(lease_path, active)
            lease = V31TransportOwnerLease(owner_id, lease_token)
            self._active_lease = lease
            self._lock_descriptor = descriptor
            yield lease
        finally:
            if self._active_lease is not None:
                try:
                    current = self._load_lease()
                    if (
                        current is not None
                        and current.get("lease_token")
                        == self._active_lease.lease_token
                        and current.get("status") == "ACTIVE"
                    ):
                        released = dict(current)
                        released["status"] = "RELEASED"
                        released.pop("lease_digest")
                        released = self_digest(released, "lease_digest")
                        self._atomic_replace(
                            self._safe_path(
                                ".v31-agent-owner-lease.json",
                                create_parent=True,
                            ),
                            released,
                        )
                finally:
                    self._active_lease = None
                    self._lock_descriptor = None
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _assert_lease(self, lease: V31TransportOwnerLease) -> None:
        if self._active_lease != lease or self._lock_descriptor is None:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_MUTATION_WITHOUT_OWNER_LEASE"
            )
        current = self._load_lease()
        if (
            current is None
            or current.get("status") != "ACTIVE"
            or current.get("owner_id") != lease.owner_id
            or current.get("lease_token") != lease.lease_token
        ):
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_OWNER_LEASE_LOST"
            )

    def document_exists(self, *, relative_ref: str) -> bool:
        return self._safe_path(relative_ref).is_file()

    def write_document(
        self,
        *,
        lease: V31TransportOwnerLease,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> dict[str, str]:
        self._assert_lease(lease)
        try:
            semantic_digest = verify_self_digest(document, digest_field)
        except (CanonicalContractError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_DOCUMENT_DIGEST_INVALID"
            ) from exc
        path = self._safe_path(relative_ref, create_parent=True)
        try:
            write_once_json(path, document)
        except CanonicalContractError as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_WRITE_ONCE_CONFLICT"
            ) from exc
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document.get("schema_id")),
            "digest_field": digest_field,
            "semantic_digest": semantic_digest,
            "physical_sha256": _sha256_file(path),
        }

    def read_bound_document(
        self, binding: Mapping[str, Any]
    ) -> dict[str, Any]:
        validated = validate_v31_transport_binding(binding)
        path = self._safe_path(validated["relative_ref"])
        if not path.is_file() or _sha256_file(path) != validated["physical_sha256"]:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_PHYSICAL_DRIFT"
            )
        try:
            document = load_json_strict(path)
            digest = verify_self_digest(document, validated["digest_field"])
        except (CanonicalContractError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_INVALID"
            ) from exc
        if (
            document.get("schema_id") != validated["schema_id"]
            or digest != validated["semantic_digest"]
        ):
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_SEMANTIC_DRIFT"
            )
        return document

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> dict[str, Any]:
        """Read one deterministic local lineage document by semantic digest.

        This narrower port is used for artifacts whose exact relative path is
        already fixed by a separately bound accepted state (notably the prior
        graph and the frozen authorization chain).  It does not create a new
        transport binding or relax physical checks on Agent-visible inputs.
        """

        path = self._safe_path(relative_ref)
        if not path.is_file():
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_MISSING"
            )
        try:
            document = load_json_strict(path)
            semantic_digest = verify_self_digest(document, digest_field)
        except (CanonicalContractError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_INVALID"
            ) from exc
        if (
            expected_semantic_digest is not None
            and semantic_digest != expected_semantic_digest
        ):
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_SEMANTIC_DRIFT"
            )
        return document

    def artifact_binding(
        self, *, relative_ref: str, digest_field: str
    ) -> dict[str, str]:
        path = self._safe_path(relative_ref)
        if not path.is_file():
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_MISSING"
            )
        try:
            document = load_json_strict(path)
            semantic_digest = verify_self_digest(document, digest_field)
        except (CanonicalContractError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_BOUND_DOCUMENT_INVALID"
            ) from exc
        binding = {
            "relative_ref": relative_ref,
            "schema_id": str(document.get("schema_id")),
            "digest_field": digest_field,
            "semantic_digest": semantic_digest,
            "physical_sha256": _sha256_file(path),
        }
        return validate_v31_transport_binding(binding)

    def initialize_checkpoint(
        self,
        *,
        lease: V31TransportOwnerLease,
        relative_ref: str,
        checkpoint: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.write_document(
            lease=lease,
            relative_ref=relative_ref,
            document=checkpoint,
            digest_field="checkpoint_digest",
        )
        return dict(checkpoint)

    def read_checkpoint(self, *, relative_ref: str) -> dict[str, Any]:
        path = self._safe_path(relative_ref)
        try:
            checkpoint = load_json_strict(path)
            verify_self_digest(checkpoint, "checkpoint_digest")
        except (CanonicalContractError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_CHECKPOINT_INVALID"
            ) from exc
        return checkpoint

    def replace_checkpoint(
        self,
        *,
        lease: V31TransportOwnerLease,
        relative_ref: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._assert_lease(lease)
        path = self._safe_path(relative_ref)
        current = self.read_checkpoint(relative_ref=relative_ref)
        if current.get("checkpoint_digest") != expected_checkpoint_digest:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_CHECKPOINT_CAS_MISMATCH"
            )
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except (CanonicalContractError, ValueError) as exc:
            raise V31AgentTransportStoreError(
                "V31_TRANSPORT_CHECKPOINT_INVALID"
            ) from exc
        self._atomic_replace(path, checkpoint)
        return dict(checkpoint)

    def write_transport_evidence(
        self,
        *,
        lease: V31TransportOwnerLease,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._assert_lease(lease)
        semantic_digest = validate_v31_transport_evidence(evidence)
        for stage in ("PROPOSAL", "SELECTION"):
            row = evidence["stages"][stage]
            for kind in ("attempt", "request", "claim", "delivery", "consume"):
                self.read_bound_document(row[f"{kind}_binding"])
        cycle_index = int(evidence["cycle_index"])
        relative_ref = (
            f"cycles/{cycle_index:04d}/transport-evidence/"
            f"{semantic_digest}.json"
        )
        internal = self.write_document(
            lease=lease,
            relative_ref=relative_ref,
            document=evidence,
            digest_field="transport_evidence_digest",
        )
        return {
            "cycle_index": cycle_index,
            "relative_ref": relative_ref,
            "semantic_digest": semantic_digest,
            "physical_sha256": internal["physical_sha256"],
        }


__all__ = [
    "LocalV31AgentTransportStore",
    "V31AgentTransportStoreError",
    "V31TransportOwnerLease",
]
