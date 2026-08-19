"""Durable evidence roots and owning full replayers for V3.2 qualification.

The three roots in this module are not claims by themselves.  Each binds a
complete existing persistence chain and can be accepted only after its owning
replayer reopens every required durable object.  Replay never invokes a
network port.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Mapping

from ...application.v32_durable_source_replay import (
    verify_durable_v32_source_replay_receipt,
)
from ...domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ...domain.governance.v32_authorization import (
    ACTUAL_CAPABILITY_RECEIPT_SPECS,
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    CAPABILITY_KEYS,
    QUALIFICATION_PROFILE,
    verify_v32_actual_capability_receipt_v1,
    verify_v32_authority_v1,
)
from ...domain.v32_agent_lifecycle import (
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    V32_QUALIFICATION_CONTEXT_PROFILE,
    verify_v32_agent_consumption_v1,
    verify_v32_agent_delivery_v1,
)
from ...domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID as MAILBOX_CHECKPOINT_SCHEMA_ID,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    STAGES,
    build_v32_current_codex_presentation_envelope_v1,
    verify_v32_current_root_agent_mailbox_checkpoint_v1,
    verify_v32_current_root_agent_mailbox_claim_v1,
    verify_v32_current_root_agent_mailbox_consumption_receipt_v1,
    verify_v32_current_root_agent_mailbox_delivery_receipt_v1,
    verify_v32_current_root_agent_mailbox_request_v1,
)
from ...domain.v32_cycle_source_admission import (
    verify_v32_active_authority_projection,
)
from ...domain.v32_outcome_tick import (
    BATCH_COMPLETION_SCHEMA_ID,
    verify_v32_outcome_resolution_batch,
)
from ...domain.v32_qualification_monitor_probe import (
    COMPLETION_DIGEST_FIELD as PROBE_COMPLETION_DIGEST_FIELD,
    COMPLETION_SCHEMA_ID as PROBE_COMPLETION_SCHEMA_ID,
)
from ...domain.v32_tick_supervisor import PERMIT_DIGEST_FIELD
from ..v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    STORE_ROOT as MAILBOX_STORE_ROOT,
)
from .v32_secure_write_once_store import (
    V32SecureWriteOnceStoreError,
    secure_ensure_directory,
    secure_exclusive_lock_file,
    secure_publish_json_directory_bundle,
    secure_read_bytes,
    secure_write_once_json,
)
from ..v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from ..v32_local_outcome_lane import LocalV32OutcomeLane
from ..v32_outcome_tick_store import LocalV32OutcomeTickStore
from ..v32_public_evidence_verifier import V32InfrastructurePublicEvidenceVerifier
from ..v32_tick_supervisor_store import LocalV32TickSupervisorStore
from .v32_qualification_monitor_probe_store import (
    LocalV32QualificationMonitorProbeStore,
    STORE_ROOT as QUALIFICATION_PROBE_STORE_ROOT,
)


class V32ActualCapabilityReplayError(ValueError):
    """A qualification root or owning replay failed closed."""


SCHEMA_VERSION = "1.0.0"
EVIDENCE_ROOT_SPECS = {
    "CURRENT_CODEX": (
        "theory_paper_v32_current_codex_actual_evidence_root_v1",
        "current_codex_actual_evidence_root_digest",
    ),
    "OUTCOME_MONITOR": (
        "theory_paper_v32_outcome_monitor_actual_evidence_root_v1",
        "outcome_monitor_actual_evidence_root_digest",
    ),
    "PUBLIC_SOURCE": (
        "theory_paper_v32_public_source_actual_evidence_root_v1",
        "public_source_actual_evidence_root_digest",
    ),
}
ATTEMPT_RESERVATION_SCHEMA_ID = (
    "theory_paper_v32_actual_capability_attempt_reservation_v1"
)
ATTEMPT_RESERVATION_DIGEST_FIELD = "actual_capability_attempt_reservation_digest"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_ROOT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "root_id",
        "capability",
        "qualification_run_id",
        "target_run_id",
        "qualification_authority_digest",
        "attempt_reservation_binding",
        "started_at",
        "completed_at",
        "attempt_count",
        "retry_allowed",
        "network_request_count",
        "replay_network_calls",
        "replay_descriptor",
        "terminal_evidence_binding",
        "full_replay_required",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
    }
)
_RESERVATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "capability",
        "qualification_run_id",
        "target_run_id",
        "qualification_authority_digest",
        "reserved_at",
        "attempt_number",
        "retry_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        ATTEMPT_RESERVATION_DIGEST_FIELD,
    }
)
_EXPECTED_NETWORK_REQUESTS = {
    "CURRENT_CODEX": 0,
    "OUTCOME_MONITOR": 1,
    "PUBLIC_SOURCE": 1,
}
_BATCH_LOCKS_GUARD = threading.Lock()
_BATCH_LOCKS: dict[str, threading.RLock] = {}
_DESCRIPTOR_FIELDS = {
    "CURRENT_CODEX": frozenset({"mailbox_store_root", "cycle_index"}),
    "OUTCOME_MONITOR": frozenset(
        {"probe_store_root", "probe_id"}
    ),
    "PUBLIC_SOURCE": frozenset(
        {
            "source_store_root",
            "run_store_root",
            "qualification_id",
            "cycle_index",
            "active_authority_projection",
        }
    ),
}


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_access": False,
        "order_submission": False,
    }


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ActualCapabilityReplayError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32ActualCapabilityReplayError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ActualCapabilityReplayError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text
    ):
        raise V32ActualCapabilityReplayError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _relative(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32ActualCapabilityReplayError(code)
    return text


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32ActualCapabilityReplayError(code)
    return {
        "path": _relative(value.get("path"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def _capability(value: Any) -> str:
    name = _text(value, "V32_ACTUAL_ROOT_CAPABILITY_INVALID")
    if name not in CAPABILITY_KEYS:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_ROOT_CAPABILITY_INVALID"
        )
    return name


def _descriptor(capability: str, value: Any) -> dict[str, Any]:
    code = f"V32_ACTUAL_ROOT_DESCRIPTOR_INVALID:{capability}"
    if not isinstance(value, Mapping) or set(value) != _DESCRIPTOR_FIELDS[capability]:
        raise V32ActualCapabilityReplayError(code)
    descriptor = dict(value)
    if capability == "PUBLIC_SOURCE":
        descriptor["source_store_root"] = _relative(
            descriptor["source_store_root"], code
        )
        descriptor["run_store_root"] = _relative(
            descriptor["run_store_root"], code
        )
        descriptor["qualification_id"] = _text(
            descriptor["qualification_id"], code
        )
        verify_v32_active_authority_projection(
            descriptor["active_authority_projection"]
        )
    elif capability == "CURRENT_CODEX":
        descriptor["mailbox_store_root"] = _relative(
            descriptor["mailbox_store_root"], code
        )
    else:
        descriptor["probe_store_root"] = _relative(
            descriptor["probe_store_root"], code
        )
        descriptor["probe_id"] = _text(
            descriptor["probe_id"], code
        )
    cycle = descriptor.get("cycle_index")
    tick = descriptor.get("tick_index")
    if cycle is not None and (
        isinstance(cycle, bool) or not isinstance(cycle, int) or cycle != 1
    ):
        raise V32ActualCapabilityReplayError(code)
    if tick is not None and (
        isinstance(tick, bool) or not isinstance(tick, int) or tick != 1
    ):
        raise V32ActualCapabilityReplayError(code)
    return descriptor


def build_v32_actual_capability_evidence_root_v1(
    *,
    root_id: str,
    capability: str,
    qualification_run_id: str,
    target_run_id: str,
    qualification_authority_digest: str,
    attempt_reservation_binding: Mapping[str, Any],
    started_at: str,
    completed_at: str,
    replay_descriptor: Mapping[str, Any],
    terminal_evidence_binding: Mapping[str, Any],
) -> dict[str, Any]:
    name = _capability(capability)
    started = _moment(started_at, "V32_ACTUAL_ROOT_TIME_INVALID")
    completed = _moment(completed_at, "V32_ACTUAL_ROOT_TIME_INVALID")
    qualification = _text(
        qualification_run_id, "V32_ACTUAL_ROOT_RUN_INVALID"
    )
    target = _text(target_run_id, "V32_ACTUAL_ROOT_RUN_INVALID")
    if started > completed or qualification == target:
        raise V32ActualCapabilityReplayError("V32_ACTUAL_ROOT_TIME_INVALID")
    schema_id, digest_field = EVIDENCE_ROOT_SPECS[name]
    return self_digest(
        {
            "schema_id": schema_id,
            "schema_version": SCHEMA_VERSION,
            "root_id": _text(root_id, "V32_ACTUAL_ROOT_ID_INVALID"),
            "capability": name,
            "qualification_run_id": qualification,
            "target_run_id": target,
            "qualification_authority_digest": _digest(
                qualification_authority_digest,
                "V32_ACTUAL_ROOT_AUTHORITY_INVALID",
            ),
            "attempt_reservation_binding": _binding(
                attempt_reservation_binding,
                "V32_ACTUAL_ROOT_RESERVATION_BINDING_INVALID",
            ),
            "started_at": _time(started_at, "V32_ACTUAL_ROOT_TIME_INVALID"),
            "completed_at": _time(
                completed_at, "V32_ACTUAL_ROOT_TIME_INVALID"
            ),
            "attempt_count": 1,
            "retry_allowed": False,
            "network_request_count": _EXPECTED_NETWORK_REQUESTS[name],
            "replay_network_calls": 0,
            "replay_descriptor": _descriptor(name, replay_descriptor),
            "terminal_evidence_binding": _binding(
                terminal_evidence_binding,
                "V32_ACTUAL_ROOT_TERMINAL_BINDING_INVALID",
            ),
            "full_replay_required": True,
            **_boundary(),
        },
        digest_field,
    )


def verify_v32_actual_capability_evidence_root_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V32ActualCapabilityReplayError("V32_ACTUAL_ROOT_INVALID")
    try:
        capability = _capability(document["capability"])
        schema_id, digest_field = EVIDENCE_ROOT_SPECS[capability]
        if (
            set(document) != _ROOT_FIELDS | {digest_field}
            or document.get("schema_id") != schema_id
        ):
            raise V32ActualCapabilityReplayError("V32_ACTUAL_ROOT_INVALID")
        supplied = verify_self_digest(document, digest_field)
        rebuilt = build_v32_actual_capability_evidence_root_v1(
            root_id=document["root_id"],
            capability=capability,
            qualification_run_id=document["qualification_run_id"],
            target_run_id=document["target_run_id"],
            qualification_authority_digest=document[
                "qualification_authority_digest"
            ],
            attempt_reservation_binding=document[
                "attempt_reservation_binding"
            ],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            replay_descriptor=document["replay_descriptor"],
            terminal_evidence_binding=document["terminal_evidence_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityReplayError):
            raise
        raise V32ActualCapabilityReplayError("V32_ACTUAL_ROOT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[digest_field]:
        raise V32ActualCapabilityReplayError("V32_ACTUAL_ROOT_INVALID")
    return supplied


def build_v32_actual_capability_attempt_reservation_v1(
    *,
    capability: str,
    qualification_run_id: str,
    target_run_id: str,
    qualification_authority_digest: str,
    reserved_at: str,
) -> dict[str, Any]:
    name = _capability(capability)
    return self_digest(
        {
            "schema_id": ATTEMPT_RESERVATION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "capability": name,
            "qualification_run_id": _text(
                qualification_run_id, "V32_ACTUAL_RESERVATION_RUN_INVALID"
            ),
            "target_run_id": _text(
                target_run_id, "V32_ACTUAL_RESERVATION_RUN_INVALID"
            ),
            "qualification_authority_digest": _digest(
                qualification_authority_digest,
                "V32_ACTUAL_RESERVATION_AUTHORITY_INVALID",
            ),
            "reserved_at": _time(
                reserved_at, "V32_ACTUAL_RESERVATION_TIME_INVALID"
            ),
            "attempt_number": 1,
            "retry_allowed": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        ATTEMPT_RESERVATION_DIGEST_FIELD,
    )


def verify_v32_actual_capability_attempt_reservation_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _RESERVATION_FIELDS:
        raise V32ActualCapabilityReplayError("V32_ACTUAL_RESERVATION_INVALID")
    try:
        supplied = verify_self_digest(document, ATTEMPT_RESERVATION_DIGEST_FIELD)
        rebuilt = build_v32_actual_capability_attempt_reservation_v1(
            capability=document["capability"],
            qualification_run_id=document["qualification_run_id"],
            target_run_id=document["target_run_id"],
            qualification_authority_digest=document[
                "qualification_authority_digest"
            ],
            reserved_at=document["reserved_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityReplayError):
            raise
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_RESERVATION_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[
        ATTEMPT_RESERVATION_DIGEST_FIELD
    ]:
        raise V32ActualCapabilityReplayError("V32_ACTUAL_RESERVATION_INVALID")
    return supplied


class LocalV32ActualCapabilityEvidenceStore:
    """Write-once store rooted inside one physical project directory."""

    def __init__(self, project_root: Path, root_relative_ref: str) -> None:
        supplied = Path(project_root).absolute()
        if not supplied.is_dir() or supplied.is_symlink():
            raise V32ActualCapabilityReplayError("V32_ACTUAL_STORE_PROJECT_INVALID")
        self.project_root = supplied.resolve(strict=True)
        self.root_relative_ref = _relative(
            root_relative_ref, "V32_ACTUAL_STORE_ROOT_INVALID"
        )
        secure_ensure_directory(self.project_root, self.root_relative_ref)
        self.root = self._safe_path(self.root_relative_ref)
        if self.root.is_symlink():
            raise V32ActualCapabilityReplayError("V32_ACTUAL_STORE_ROOT_INVALID")
        self._batch_lock_ref = f"{self.root_relative_ref}/.receipt-batch.lock"

    @contextmanager
    def _batch_lock(self):
        """Serialize the multi-document seal across threads and processes."""

        key = f"{self.project_root}:{self._batch_lock_ref}"
        with _BATCH_LOCKS_GUARD:
            local = _BATCH_LOCKS.setdefault(key, threading.RLock())
        with local:
            with secure_exclusive_lock_file(
                self.project_root, self._batch_lock_ref
            ):
                yield

    def _safe_path(self, relative_ref: str, *, create_parent: bool = False) -> Path:
        relative = _relative(relative_ref, "V32_ACTUAL_STORE_PATH_INVALID")
        cursor = self.project_root
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            if cursor.exists() and cursor.is_symlink():
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_SYMLINK_FORBIDDEN"
                )
        if create_parent:
            cursor.parent.mkdir(parents=True, exist_ok=True)
        try:
            cursor.resolve(strict=False).relative_to(self.project_root)
        except (OSError, ValueError) as exc:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_STORE_PATH_INVALID"
            ) from exc
        return cursor

    def _write(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
        require_new: bool = False,
    ) -> dict[str, str]:
        if document.get("schema_id") != schema_id:
            raise V32ActualCapabilityReplayError("V32_ACTUAL_STORE_SCHEMA_INVALID")
        try:
            semantic = verify_self_digest(document, digest_field)
            binding = secure_write_once_json(
                self.project_root,
                relative_ref,
                document,
                digest_field=digest_field,
                require_new=require_new,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_STORE_WRITE_ONCE_CONFLICT"
            ) from exc
        payload = canonical_bytes(dict(document)) + b"\n"
        if secure_read_bytes(self.project_root, relative_ref) != payload:
            raise V32ActualCapabilityReplayError("V32_ACTUAL_STORE_BYTES_INVALID")
        if binding.get("semantic_digest") != semantic:
            raise V32ActualCapabilityReplayError("V32_ACTUAL_STORE_BYTES_INVALID")
        return dict(binding)

    def root_ref(self, capability: str) -> str:
        name = _capability(capability).lower().replace("_", "-")
        return f"{self.root_relative_ref}/roots/{name}.json"

    def verify_evidence_root(self, document: Mapping[str, Any]) -> str:
        """Implement the application evidence-verification port."""

        return verify_v32_actual_capability_evidence_root_v1(document)

    def full_replay_registry(self) -> dict[str, Any]:
        """Expose owning offline replayers through the application store port."""

        return build_v32_actual_capability_full_replay_registry()

    def attempt_ref(self, capability: str) -> str:
        name = _capability(capability).lower().replace("_", "-")
        return f"{self.root_relative_ref}/attempts/{name}.json"

    def receipt_ref(self, capability: str) -> str:
        name = _capability(capability).lower().replace("_", "-")
        return f"{self.seal_bundle_ref}/receipts/{name}.json"

    @property
    def seal_bundle_ref(self) -> str:
        return f"{self.root_relative_ref}/seal-bundle"

    @property
    def qualification_receipt_ref(self) -> str:
        return f"{self.seal_bundle_ref}/qualification-receipt.json"

    def reserve_attempt(
        self,
        *,
        capability: str,
        qualification_run_id: str,
        target_run_id: str,
        qualification_authority_digest: str,
        reserved_at: str,
    ) -> dict[str, Any]:
        name = _capability(capability)
        document = build_v32_actual_capability_attempt_reservation_v1(
            capability=name,
            qualification_run_id=qualification_run_id,
            target_run_id=target_run_id,
            qualification_authority_digest=qualification_authority_digest,
            reserved_at=reserved_at,
        )
        relative_ref = self.attempt_ref(name)
        binding = self._write(
            relative_ref=relative_ref,
            document=document,
            schema_id=ATTEMPT_RESERVATION_SCHEMA_ID,
            digest_field=ATTEMPT_RESERVATION_DIGEST_FIELD,
            require_new=True,
        )
        return {"reservation": document, "reservation_binding": binding}

    def load_attempt_reservation(
        self, capability: str
    ) -> dict[str, Any] | None:
        """Load one prior reservation for crash recovery; never create it."""

        relative_ref = self.attempt_ref(capability)
        raw = secure_read_bytes(
            self.project_root, relative_ref, missing_ok=True
        )
        if raw is None:
            return None
        try:
            document = loads_json_strict(raw)
            digest = verify_v32_actual_capability_attempt_reservation_v1(
                document
            )
        except (OSError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_RESERVATION_RECOVERY_INVALID"
            ) from exc
        payload = canonical_bytes(document) + b"\n"
        if raw != payload:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_RESERVATION_RECOVERY_INVALID"
            )
        binding = {
            "path": relative_ref,
            "schema_id": ATTEMPT_RESERVATION_SCHEMA_ID,
            "digest_field": ATTEMPT_RESERVATION_DIGEST_FIELD,
            "semantic_digest": digest,
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }
        return {"reservation": document, "reservation_binding": binding}

    def persist_evidence_root(
        self, document: Mapping[str, Any]
    ) -> dict[str, str]:
        digest = verify_v32_actual_capability_evidence_root_v1(document)
        capability = str(document["capability"])
        schema_id, digest_field = EVIDENCE_ROOT_SPECS[capability]
        if digest != document[digest_field]:
            raise V32ActualCapabilityReplayError("V32_ACTUAL_ROOT_INVALID")
        return self._write(
            relative_ref=self.root_ref(capability),
            document=document,
            schema_id=schema_id,
            digest_field=digest_field,
        )

    def load_evidence_root(self, capability: str) -> dict[str, Any] | None:
        """Load one already sealed root for crash recovery; never replay it."""

        name = _capability(capability)
        relative_ref = self.root_ref(name)
        raw = secure_read_bytes(
            self.project_root, relative_ref, missing_ok=True
        )
        if raw is None:
            return None
        try:
            document = loads_json_strict(raw)
            digest = verify_v32_actual_capability_evidence_root_v1(document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_ROOT_RECOVERY_INVALID"
            ) from exc
        schema_id, digest_field = EVIDENCE_ROOT_SPECS[name]
        payload = canonical_bytes(document) + b"\n"
        if (
            document.get("capability") != name
            or raw != payload
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_ROOT_RECOVERY_INVALID"
            )
        binding = {
            "path": relative_ref,
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": digest,
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }
        return {"evidence_root": document, "evidence_root_binding": binding}

    def persist_typed_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
    ) -> dict[str, str]:
        return self._write(
            relative_ref=relative_ref,
            document=document,
            schema_id=schema_id,
            digest_field=digest_field,
        )

    def preview_typed_document_binding(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
    ) -> dict[str, str]:
        """Validate one prospective document and derive its final binding.

        This is deliberately read-only.  It lets a parent receipt bind all
        child receipts before any of the four qualification receipts becomes
        durable.
        """

        relative_ref = _relative(
            relative_ref, "V32_ACTUAL_STORE_BATCH_PREFLIGHT_INVALID"
        )
        try:
            root_prefix = f"{self.root_relative_ref}/"
            if not relative_ref.startswith(root_prefix):
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_BATCH_PREFLIGHT_INVALID"
                )
            if document.get("schema_id") != schema_id:
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_SCHEMA_INVALID"
                )
            semantic = verify_self_digest(document, digest_field)
            payload = canonical_bytes(dict(document)) + b"\n"
        except (OSError, TypeError, ValueError) as exc:
            if isinstance(exc, V32ActualCapabilityReplayError):
                raise
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_STORE_BATCH_PREFLIGHT_INVALID"
            ) from exc
        return {
            "path": relative_ref,
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }

    def persist_typed_documents_atomically(
        self, documents: list[Mapping[str, Any]]
    ) -> dict[str, dict[str, str]]:
        """Publish the complete qualification seal with one directory rename.

        All schemas, digests, paths and existing targets are checked first.
        Bytes are written and verified under one private sibling staging
        directory.  The only visibility boundary is one same-filesystem
        descriptor-relative directory rename.  Therefore a
        crash or power interruption can expose either no final bundle or the
        complete four-file bundle, never a mixed set of final receipt paths.  A
        process lock prevents concurrent seal interleaving.

        An already complete byte-identical batch is idempotently reusable; a
        pre-existing partial/extra/conflicting final bundle is rejected and is
        never repaired in place.
        """

        if not isinstance(documents, list) or not documents:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_STORE_BATCH_INVALID"
            )
        prepared: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in documents:
            if not isinstance(item, Mapping) or set(item) != {
                "relative_ref",
                "document",
                "schema_id",
                "digest_field",
            }:
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_BATCH_INVALID"
                )
            relative_ref = str(item["relative_ref"])
            if relative_ref in seen:
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_BATCH_INVALID"
                )
            seen.add(relative_ref)
            document = item["document"]
            if not isinstance(document, Mapping):
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_BATCH_INVALID"
                )
            schema_id = str(item["schema_id"])
            digest_field = str(item["digest_field"])
            self.preview_typed_document_binding(
                relative_ref=relative_ref,
                document=document,
                schema_id=schema_id,
                digest_field=digest_field,
            )
            prepared.append(
                {
                    "relative_ref": relative_ref,
                    "document": dict(document),
                    "schema_id": schema_id,
                    "digest_field": digest_field,
                }
            )

        expected_refs = {
            self.receipt_ref(capability) for capability in CAPABILITY_KEYS
        } | {self.qualification_receipt_ref}
        if seen != expected_refs:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_STORE_BATCH_DOCUMENT_SET_INVALID"
            )
        with self._batch_lock():
            try:
                return secure_publish_json_directory_bundle(
                    self.project_root,
                    bundle_relative_ref=self.seal_bundle_ref,
                    documents=prepared,
                )
            except V32SecureWriteOnceStoreError as exc:
                if "BUNDLE_CONFLICT" in str(exc):
                    raise V32ActualCapabilityReplayError(
                        "V32_ACTUAL_STORE_BATCH_EXISTING_CONFLICT"
                    ) from exc
                if "INCOMPLETE_PRIOR_ATTEMPT" in str(exc):
                    raise V32ActualCapabilityReplayError(
                        "V32_ACTUAL_STORE_BATCH_INCOMPLETE_PRIOR_ATTEMPT"
                    ) from exc
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_BATCH_WRITE_FAILED"
                ) from exc
            except (OSError, TypeError, ValueError) as exc:
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_BATCH_WRITE_FAILED"
                ) from exc

    def load_binding(
        self, binding_value: Mapping[str, Any], *, verifier: Any
    ) -> dict[str, Any]:
        binding = _binding(binding_value, "V32_ACTUAL_STORE_BINDING_INVALID")
        try:
            raw = secure_read_bytes(self.project_root, binding["path"])
            if raw is None:
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_STORE_BINDING_INVALID"
                )
            document = loads_json_strict(raw)
            semantic = verifier(document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_STORE_BINDING_INVALID"
            ) from exc
        if (
            document.get("schema_id") != binding["schema_id"]
            or semantic != binding["semantic_digest"]
            or hashlib.sha256(raw).hexdigest() != binding["physical_sha256"]
            or raw != canonical_bytes(document) + b"\n"
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_STORE_BINDING_INVALID"
            )
        return document


def _project_path(project_root: Path, relative_ref: str) -> Path:
    root = Path(project_root).resolve(strict=True)
    relative = _relative(relative_ref, "V32_ACTUAL_REPLAY_PATH_INVALID")
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_REPLAY_SYMLINK_FORBIDDEN"
            )
    try:
        target = cursor.resolve(strict=True)
        target.relative_to(root)
    except (OSError, ValueError) as exc:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_REPLAY_PATH_INVALID"
        ) from exc
    return target


def _standard_binding(
    *,
    project_root: Path,
    relative_ref: str,
    document: Mapping[str, Any],
    schema_id: str,
    digest_field: str,
) -> dict[str, str]:
    path = _project_path(project_root, relative_ref)
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_REPLAY_BINDING_INVALID"
        ) from exc
    if document.get("schema_id") != schema_id:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_REPLAY_BINDING_INVALID"
        )
    return {
        "path": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _store_binding_to_project(
    *, project_root: Path, store_root: str, binding: Mapping[str, Any]
) -> dict[str, str]:
    relative_ref = _relative(
        binding.get("relative_ref"), "V32_ACTUAL_REPLAY_BINDING_INVALID"
    )
    path = f"{_relative(store_root, 'V32_ACTUAL_REPLAY_BINDING_INVALID')}/{relative_ref}"
    document = load_json_strict(_project_path(project_root, path))
    result = _standard_binding(
        project_root=project_root,
        relative_ref=path,
        document=document,
        schema_id=str(binding.get("schema_id")),
        digest_field=str(binding.get("digest_field")),
    )
    if any(
        binding.get(field) != result[field]
        for field in (
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
        )
    ):
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_REPLAY_BINDING_INVALID"
        )
    return result


def _load_root_from_callback(
    *,
    project_root: Path,
    capability_receipt: Mapping[str, Any],
    evidence_root_binding: Mapping[str, Any],
    qualification_authority: Mapping[str, Any],
    capability: str,
) -> dict[str, Any]:
    try:
        receipt_digest = verify_v32_actual_capability_receipt_v1(
            capability_receipt
        )
        authority_digest = verify_v32_authority_v1(qualification_authority)
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_FULL_REPLAY_IDENTITY_INVALID:{capability}"
        ) from exc
    schema_id, digest_field = ACTUAL_CAPABILITY_RECEIPT_SPECS[capability]
    receipt_authority_binding = capability_receipt.get(
        "qualification_authority_binding"
    )
    if (
        capability_receipt.get("schema_id") != schema_id
        or capability_receipt.get(digest_field) != receipt_digest
        or capability_receipt.get("capability") != capability
        or qualification_authority.get("profile") != QUALIFICATION_PROFILE
        or capability_receipt.get("qualification_run_id")
        != qualification_authority.get("run_id")
        or capability_receipt.get("target_run_id")
        != qualification_authority.get("target_run_id")
        or not isinstance(receipt_authority_binding, Mapping)
        or receipt_authority_binding.get("semantic_digest") != authority_digest
    ):
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_FULL_REPLAY_IDENTITY_INVALID:{capability}"
        )
    authority_binding = _binding(
        receipt_authority_binding,
        f"V32_ACTUAL_FULL_REPLAY_IDENTITY_INVALID:{capability}",
    )
    authority_path = _project_path(project_root, authority_binding["path"])
    if (
        authority_binding["schema_id"] != AUTHORITY_SCHEMA_ID
        or authority_binding["digest_field"] != AUTHORITY_DIGEST_FIELD
        or hashlib.sha256(authority_path.read_bytes()).hexdigest()
        != authority_binding["physical_sha256"]
        or authority_path.read_bytes()
        != canonical_bytes(dict(qualification_authority)) + b"\n"
    ):
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_FULL_REPLAY_IDENTITY_INVALID:{capability}"
        )
    binding = _binding(
        evidence_root_binding,
        f"V32_ACTUAL_FULL_REPLAY_ROOT_INVALID:{capability}",
    )
    if capability_receipt.get("evidence_root_binding") != binding:
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_FULL_REPLAY_ROOT_INVALID:{capability}"
        )
    path = _project_path(project_root, binding["path"])
    try:
        root = load_json_strict(path)
        semantic = verify_v32_actual_capability_evidence_root_v1(root)
    except (OSError, TypeError, ValueError) as exc:
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_FULL_REPLAY_ROOT_INVALID:{capability}"
        ) from exc
    if (
        root.get("capability") != capability
        or root.get("qualification_run_id") != qualification_authority.get("run_id")
        or root.get("target_run_id") != qualification_authority.get("target_run_id")
        or root.get("qualification_authority_digest") != authority_digest
        or root.get("started_at") != capability_receipt.get("started_at")
        or root.get("completed_at") != capability_receipt.get("completed_at")
        or semantic != binding["semantic_digest"]
        or hashlib.sha256(path.read_bytes()).hexdigest()
        != binding["physical_sha256"]
        or path.read_bytes() != canonical_bytes(root) + b"\n"
    ):
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_FULL_REPLAY_ROOT_INVALID:{capability}"
        )
    if _moment(
        root.get("started_at"), "V32_ACTUAL_ROOT_TIME_INVALID"
    ) <= _moment(
        qualification_authority.get("recorded_at"),
        "V32_ACTUAL_ROOT_TIME_INVALID",
    ):
        raise V32ActualCapabilityReplayError("V32_ACTUAL_ROOT_TIME_INVALID")
    reservation_binding = _binding(
        root.get("attempt_reservation_binding"),
        f"V32_ACTUAL_RESERVATION_REPLAY_INVALID:{capability}",
    )
    reservation_path = _project_path(project_root, reservation_binding["path"])
    try:
        reservation = load_json_strict(reservation_path)
        reservation_digest = (
            verify_v32_actual_capability_attempt_reservation_v1(reservation)
        )
    except (OSError, TypeError, ValueError) as exc:
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_RESERVATION_REPLAY_INVALID:{capability}"
        ) from exc
    if (
        reservation.get("schema_id") != ATTEMPT_RESERVATION_SCHEMA_ID
        or reservation_digest != reservation_binding["semantic_digest"]
        or hashlib.sha256(reservation_path.read_bytes()).hexdigest()
        != reservation_binding["physical_sha256"]
        or reservation_path.read_bytes() != canonical_bytes(reservation) + b"\n"
        or reservation.get("capability") != capability
        or reservation.get("qualification_run_id") != root["qualification_run_id"]
        or reservation.get("target_run_id") != root["target_run_id"]
        or reservation.get("qualification_authority_digest") != authority_digest
        or not _moment(
            qualification_authority["recorded_at"],
            "V32_ACTUAL_RESERVATION_TIME_INVALID",
        )
        < _moment(
            reservation.get("reserved_at"),
            "V32_ACTUAL_RESERVATION_TIME_INVALID",
        )
        <= _moment(root["started_at"], "V32_ACTUAL_RESERVATION_TIME_INVALID")
    ):
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_RESERVATION_REPLAY_INVALID:{capability}"
        )
    return root


def _root_replay_result(capability: str, root: Mapping[str, Any]) -> dict[str, Any]:
    digest_field = EVIDENCE_ROOT_SPECS[capability][1]
    return {
        "capability": capability,
        "evidence_root_semantic_digest": root[digest_field],
        "full_replay_verified": True,
        "replay_network_calls": 0,
    }


def _verify_terminal_binding(
    project_root: Path,
    root: Mapping[str, Any],
    expected: Mapping[str, Any],
    capability: str,
) -> None:
    supplied = _binding(
        root["terminal_evidence_binding"],
        f"V32_ACTUAL_TERMINAL_REPLAY_INVALID:{capability}",
    )
    if supplied != expected:
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_TERMINAL_REPLAY_INVALID:{capability}"
        )
    path = _project_path(project_root, supplied["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != supplied["physical_sha256"]:
        raise V32ActualCapabilityReplayError(
            f"V32_ACTUAL_TERMINAL_REPLAY_INVALID:{capability}"
        )


def compose_v32_public_source_actual_evidence_root(
    *,
    project_root: Path,
    qualification_authority: Mapping[str, Any],
    attempt_reservation_binding: Mapping[str, Any],
    active_authority_projection: Mapping[str, Any],
    source_store_root: str,
    run_store_root: str,
    qualification_id: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    """Replay and compose the source root without performing collection."""

    try:
        authority_digest = verify_v32_authority_v1(qualification_authority)
        projection_digest = verify_v32_active_authority_projection(
            active_authority_projection
        )
        if (
            qualification_authority.get("profile") != QUALIFICATION_PROFILE
            or active_authority_projection.get("authorized_run_id")
            != qualification_authority.get("run_id")
            or active_authority_projection.get("governing_authority_digest")
            != authority_digest
            or not projection_digest
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_PUBLIC_SOURCE_AUTHORITY_INVALID"
            )
        source_store = LocalV32CycleSourceAdmissionStore(
            _project_path(project_root, source_store_root)
        )
        run_store = LocalV32CycleSourceAdmissionStore(
            _project_path(project_root, run_store_root)
        )
        replay = verify_durable_v32_source_replay_receipt(
            public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
            source_store=source_store,
            run_store=run_store,
            active_authority=active_authority_projection,
            qualification_id=qualification_id,
            run_id=str(qualification_authority["run_id"]),
            cycle_index=1,
        )
        replay_receipt = replay["durable_source_replay_receipt"]
        if (
            replay_receipt["raw_before_derived_proof"]["attempt_started_at"]
            != started_at
            or replay_receipt["replayed_at"] != completed_at
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_PUBLIC_SOURCE_TIME_INVALID"
            )
        terminal = _store_binding_to_project(
            project_root=project_root,
            store_root=run_store_root,
            binding=replay["durable_source_replay_receipt_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityReplayError):
            raise
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_PUBLIC_SOURCE_COMPOSITION_INVALID"
        ) from exc
    return build_v32_actual_capability_evidence_root_v1(
        root_id=f"actual-root:public-source:{qualification_authority['run_id']}",
        capability="PUBLIC_SOURCE",
        qualification_run_id=str(qualification_authority["run_id"]),
        target_run_id=str(qualification_authority["target_run_id"]),
        qualification_authority_digest=authority_digest,
        attempt_reservation_binding=attempt_reservation_binding,
        started_at=started_at,
        completed_at=completed_at,
        replay_descriptor={
            "source_store_root": source_store_root,
            "run_store_root": run_store_root,
            "qualification_id": qualification_id,
            "cycle_index": 1,
            "active_authority_projection": dict(active_authority_projection),
        },
        terminal_evidence_binding=terminal,
    )


def compose_v32_current_codex_actual_evidence_root(
    *,
    project_root: Path,
    qualification_authority: Mapping[str, Any],
    attempt_reservation_binding: Mapping[str, Any],
    mailbox_store_root: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    """Replay both consumed mailbox stages and compose their evidence root."""

    try:
        authority_digest = verify_v32_authority_v1(qualification_authority)
        mailbox = LocalV32CurrentRootAgentMailbox(
            _project_path(project_root, mailbox_store_root)
        )
        checkpoint = mailbox.load_checkpoint(
            run_id=str(qualification_authority["run_id"]), cycle_index=1
        )
        checkpoint_digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(
            checkpoint
        )
        if (
            qualification_authority.get("profile") != QUALIFICATION_PROFILE
            or checkpoint.get("status") != "COMPLETE"
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_MAILBOX_CHECKPOINT_REPLAY_INVALID"
            )
        proposal_context_digest: str | None = None
        replay_started_at: str | None = None
        replay_completed_at: str | None = None
        for stage in STAGES:
            replay = _replay_mailbox_stage(
                mailbox=mailbox,
                run_id=str(qualification_authority["run_id"]),
                cycle_index=1,
                stage=stage,
                expected_authority_digest=authority_digest,
                expected_proposal_context_digest=proposal_context_digest,
            )
            if stage == "PROPOSAL":
                proposal_context_digest = replay["proposal_context_digest"]
                replay_started_at = replay["reserved_at"]
            replay_completed_at = replay["consumed_at"]
            state = checkpoint["stage_states"][stage]
            if (
                state.get("status") != "CONSUMED"
                or state.get("attempt_count") != 1
                or replay["authority_digest"] != authority_digest
                or any(
                    state.get(key) != replay[key]
                    for key in (
                        "request_digest",
                        "claim_digest",
                        "delivery_receipt_digest",
                        "consumption_receipt_digest",
                    )
                )
            ):
                raise V32ActualCapabilityReplayError(
                    "V32_ACTUAL_MAILBOX_STAGE_REPLAY_INVALID"
                )
        if replay_started_at != started_at or replay_completed_at != completed_at:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_MAILBOX_TIME_INVALID"
            )
        checkpoint_ref = (
            f"{mailbox_store_root}/{MAILBOX_STORE_ROOT}/cycles/0001/"
            "checkpoint.json"
        )
        terminal = _standard_binding(
            project_root=project_root,
            relative_ref=checkpoint_ref,
            document=checkpoint,
            schema_id=MAILBOX_CHECKPOINT_SCHEMA_ID,
            digest_field=MAILBOX_CHECKPOINT_DIGEST_FIELD,
        )
        if terminal["semantic_digest"] != checkpoint_digest:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_MAILBOX_CHECKPOINT_REPLAY_INVALID"
            )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityReplayError):
            raise
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_COMPOSITION_INVALID"
        ) from exc
    return build_v32_actual_capability_evidence_root_v1(
        root_id=f"actual-root:current-codex:{qualification_authority['run_id']}",
        capability="CURRENT_CODEX",
        qualification_run_id=str(qualification_authority["run_id"]),
        target_run_id=str(qualification_authority["target_run_id"]),
        qualification_authority_digest=authority_digest,
        attempt_reservation_binding=attempt_reservation_binding,
        started_at=started_at,
        completed_at=completed_at,
        replay_descriptor={"mailbox_store_root": mailbox_store_root, "cycle_index": 1},
        terminal_evidence_binding=terminal,
    )


def compose_v32_outcome_monitor_actual_evidence_root(
    *,
    project_root: Path,
    qualification_authority: Mapping[str, Any],
    attempt_reservation_binding: Mapping[str, Any],
    probe_store_root: str,
    probe_id: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    """Replay the dedicated one-shot qualification probe and compose its root."""

    try:
        authority_digest = verify_v32_authority_v1(qualification_authority)
        probe_store = LocalV32QualificationMonitorProbeStore(
            _project_path(project_root, probe_store_root),
            capture_port=_ReplayMustNotCapture(),
            clock=lambda: (_ for _ in ()).throw(
                V32ActualCapabilityReplayError("V32_ACTUAL_OUTCOME_REPLAY_CLOCK_FORBIDDEN")
            ),
        )
        replay = probe_store.replay()
        schedule = replay["schedule"]
        completion = replay["completion"]
        if (
            qualification_authority.get("profile") != QUALIFICATION_PROFILE
            or qualification_authority.get("outcome_schedules") != 0
            or qualification_authority.get("qualification_monitor_probes") != 1
            or schedule.get("qualification_authority_digest") != authority_digest
            or schedule.get("probe_id") != probe_id
            or completion.get("outcome_schedule_count") != 0
            or completion.get("counted_toward_target") is not False
            or replay["observation"].get("status") != "OBSERVED_PUBLIC_MARK"
            or replay["capture"].get("transport_status") != "RESPONSE_CAPTURED"
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_OUTCOME_AUTHORITY_INVALID"
            )
        if (
            completion["started_at"] != started_at
            or completion["completed_at"] != completed_at
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_OUTCOME_TIME_INVALID"
            )
        completion_ref = (
            f"{probe_store_root}/{QUALIFICATION_PROBE_STORE_ROOT}/completion.json"
        )
        terminal = _standard_binding(
            project_root=project_root,
            relative_ref=completion_ref,
            document=completion,
            schema_id=PROBE_COMPLETION_SCHEMA_ID,
            digest_field=PROBE_COMPLETION_DIGEST_FIELD,
        )
        if terminal["semantic_digest"] != completion[PROBE_COMPLETION_DIGEST_FIELD]:
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_OUTCOME_FULL_REPLAY_INVALID"
            )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityReplayError):
            raise
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_OUTCOME_COMPOSITION_INVALID"
        ) from exc
    return build_v32_actual_capability_evidence_root_v1(
        root_id=f"actual-root:outcome-monitor:{qualification_authority['run_id']}",
        capability="OUTCOME_MONITOR",
        qualification_run_id=str(qualification_authority["run_id"]),
        target_run_id=str(qualification_authority["target_run_id"]),
        qualification_authority_digest=authority_digest,
        attempt_reservation_binding=attempt_reservation_binding,
        started_at=started_at,
        completed_at=completed_at,
        replay_descriptor={
            "probe_store_root": probe_store_root,
            "probe_id": probe_id,
        },
        terminal_evidence_binding=terminal,
    )


def verify_v32_public_source_actual_capability_full_replay(
    *,
    project_root: Path,
    capability_receipt: Mapping[str, Any],
    evidence_root_binding: Mapping[str, str],
    qualification_authority: Mapping[str, Any],
) -> Mapping[str, Any]:
    capability = "PUBLIC_SOURCE"
    root = _load_root_from_callback(
        project_root=project_root,
        capability_receipt=capability_receipt,
        evidence_root_binding=evidence_root_binding,
        qualification_authority=qualification_authority,
        capability=capability,
    )
    descriptor = root["replay_descriptor"]
    projection = descriptor["active_authority_projection"]
    authority_digest = qualification_authority[AUTHORITY_DIGEST_FIELD]
    if (
        projection.get("authorized_run_id") != root["qualification_run_id"]
        or projection.get("governing_authority_digest") != authority_digest
    ):
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_PUBLIC_SOURCE_AUTHORITY_INVALID"
        )
    source_store = LocalV32CycleSourceAdmissionStore(
        _project_path(project_root, descriptor["source_store_root"])
    )
    run_store = LocalV32CycleSourceAdmissionStore(
        _project_path(project_root, descriptor["run_store_root"])
    )
    try:
        replay = verify_durable_v32_source_replay_receipt(
            public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
            source_store=source_store,
            run_store=run_store,
            active_authority=projection,
            qualification_id=descriptor["qualification_id"],
            run_id=root["qualification_run_id"],
            cycle_index=descriptor["cycle_index"],
        )
        replay_receipt = replay["durable_source_replay_receipt"]
        if (
            replay_receipt["raw_before_derived_proof"]["attempt_started_at"]
            != root["started_at"]
            or replay_receipt["replayed_at"] != root["completed_at"]
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_PUBLIC_SOURCE_TIME_INVALID"
            )
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_PUBLIC_SOURCE_FULL_REPLAY_INVALID"
        ) from exc
    expected = _store_binding_to_project(
        project_root=project_root,
        store_root=descriptor["run_store_root"],
        binding=replay["durable_source_replay_receipt_binding"],
    )
    _verify_terminal_binding(project_root, root, expected, capability)
    return _root_replay_result(capability, root)


def _replay_mailbox_stage(
    *,
    mailbox: LocalV32CurrentRootAgentMailbox,
    run_id: str,
    cycle_index: int,
    stage: str,
    expected_authority_digest: str,
    expected_proposal_context_digest: str | None,
) -> dict[str, str]:
    try:
        chain = mailbox.load_stage_chain(
            run_id=run_id, cycle_index=cycle_index, stage=stage
        )
        if chain.get("stage_status") != "CONSUMED":
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_MAILBOX_STAGE_REPLAY_INVALID"
            )
        request = chain["request"]
        claim = chain["claim"]
        delivery = chain["agent_delivery"]
        delivery_receipt = chain["delivery_receipt"]
        consumption = chain["agent_consumption"]
        consumption_receipt = chain["consumption_receipt"]
        request_digest = verify_v32_current_root_agent_mailbox_request_v1(request)
        claim_digest = verify_v32_current_root_agent_mailbox_claim_v1(
            claim, request=request
        )
        verify_v32_agent_delivery_v1(
            delivery, agent_input_context=request["agent_input_context"]
        )
        delivery_digest = verify_v32_current_root_agent_mailbox_delivery_receipt_v1(
            delivery_receipt,
            request=request,
            claim=claim,
            agent_delivery=delivery,
        )
        claimed_snapshot = mailbox.load_claimed_stage_snapshot(
            run_id=run_id, cycle_index=cycle_index, stage=stage
        )
        presentation = build_v32_current_codex_presentation_envelope_v1(
            mailbox_checkpoint=claimed_snapshot["mailbox_checkpoint"],
            request=claimed_snapshot["request"],
            claim=claimed_snapshot["claim"],
            lossless_context_package=claimed_snapshot[
                "lossless_context_package"
            ],
            control_context={
                "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                "stage": stage,
                "stage_status": "CLAIMED",
                "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
            },
        )
        if (
            presentation[CURRENT_CODEX_PRESENTATION_DIGEST_FIELD]
            != delivery_receipt.get(
                "current_codex_presentation_digest"
            )
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_MAILBOX_PRESENTATION_REPLAY_INVALID"
            )
        verify_v32_agent_consumption_v1(
            consumption,
            agent_input_context=request["agent_input_context"],
            agent_delivery=delivery,
        )
        consumption_digest = (
            verify_v32_current_root_agent_mailbox_consumption_receipt_v1(
                consumption_receipt,
                request=request,
                claim=claim,
                delivery_receipt=delivery_receipt,
                agent_delivery=delivery,
                agent_consumption=consumption,
            )
        )
        packet = chain["canonical_packet_original"]
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityReplayError):
            raise
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_STAGE_REPLAY_INVALID"
        ) from exc
    context = request["agent_input_context"]
    if (
        context.get("context_profile") != V32_QUALIFICATION_CONTEXT_PROFILE
        or not isinstance(packet, Mapping)
        or packet.get("context_profile") != V32_QUALIFICATION_CONTEXT_PROFILE
    ):
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_QUALIFICATION_CONTEXT_INVALID"
        )
    if stage == "PROPOSAL":
        authority_binding = packet.get("authority_binding")
        proposal_context_digest = context.get(AGENT_INPUT_CONTEXT_DIGEST_FIELD)
    else:
        proposal_context = packet.get("proposal_input_context")
        if (
            not isinstance(proposal_context, Mapping)
            or expected_proposal_context_digest is None
            or proposal_context.get(AGENT_INPUT_CONTEXT_DIGEST_FIELD)
            != expected_proposal_context_digest
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_MAILBOX_QUALIFICATION_CONTEXT_INVALID"
            )
        authority_binding = {"semantic_digest": expected_authority_digest}
        proposal_context_digest = expected_proposal_context_digest
    if (
        not isinstance(authority_binding, Mapping)
        or authority_binding.get("semantic_digest") != expected_authority_digest
    ):
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_QUALIFICATION_CONTEXT_INVALID"
        )
    return {
        "request_digest": request_digest,
        "claim_digest": claim_digest,
        "delivery_receipt_digest": delivery_digest,
        "consumption_receipt_digest": consumption_digest,
        "authority_digest": authority_binding["semantic_digest"],
        "proposal_context_digest": proposal_context_digest,
        "reserved_at": request["reserved_at"],
        "consumed_at": consumption_receipt["consumed_at"],
    }


def verify_v32_current_codex_actual_capability_full_replay(
    *,
    project_root: Path,
    capability_receipt: Mapping[str, Any],
    evidence_root_binding: Mapping[str, str],
    qualification_authority: Mapping[str, Any],
) -> Mapping[str, Any]:
    capability = "CURRENT_CODEX"
    root = _load_root_from_callback(
        project_root=project_root,
        capability_receipt=capability_receipt,
        evidence_root_binding=evidence_root_binding,
        qualification_authority=qualification_authority,
        capability=capability,
    )
    descriptor = root["replay_descriptor"]
    mailbox = LocalV32CurrentRootAgentMailbox(
        _project_path(project_root, descriptor["mailbox_store_root"])
    )
    try:
        checkpoint = mailbox.load_checkpoint(
            run_id=root["qualification_run_id"],
            cycle_index=descriptor["cycle_index"],
        )
        checkpoint_digest = verify_v32_current_root_agent_mailbox_checkpoint_v1(
            checkpoint
        )
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_CHECKPOINT_REPLAY_INVALID"
        ) from exc
    if checkpoint.get("status") != "COMPLETE":
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_CHECKPOINT_REPLAY_INVALID"
        )
    authority_digest = qualification_authority[AUTHORITY_DIGEST_FIELD]
    proposal_context_digest: str | None = None
    replay_started_at: str | None = None
    replay_completed_at: str | None = None
    for stage in STAGES:
        replay = _replay_mailbox_stage(
            mailbox=mailbox,
            run_id=root["qualification_run_id"],
            cycle_index=descriptor["cycle_index"],
            stage=stage,
            expected_authority_digest=authority_digest,
            expected_proposal_context_digest=proposal_context_digest,
        )
        if stage == "PROPOSAL":
            proposal_context_digest = replay["proposal_context_digest"]
            replay_started_at = replay["reserved_at"]
        replay_completed_at = replay["consumed_at"]
        state = checkpoint["stage_states"][stage]
        if (
            state.get("status") != "CONSUMED"
            or state.get("attempt_count") != 1
            or any(state.get(key) != replay[key] for key in (
                "request_digest",
                "claim_digest",
                "delivery_receipt_digest",
                "consumption_receipt_digest",
            ))
            or replay["authority_digest"] != authority_digest
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_MAILBOX_STAGE_REPLAY_INVALID"
            )
    if (
        replay_started_at != root["started_at"]
        or replay_completed_at != root["completed_at"]
    ):
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_TIME_INVALID"
        )
    checkpoint_ref = (
        f"{descriptor['mailbox_store_root']}/{MAILBOX_STORE_ROOT}/"
        f"cycles/{descriptor['cycle_index']:04d}/checkpoint.json"
    )
    expected = _standard_binding(
        project_root=project_root,
        relative_ref=checkpoint_ref,
        document=checkpoint,
        schema_id=MAILBOX_CHECKPOINT_SCHEMA_ID,
        digest_field=MAILBOX_CHECKPOINT_DIGEST_FIELD,
    )
    if expected["semantic_digest"] != checkpoint_digest:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_MAILBOX_CHECKPOINT_REPLAY_INVALID"
        )
    _verify_terminal_binding(project_root, root, expected, capability)
    return _root_replay_result(capability, root)


class _ReplayMustNotCapture:
    def capture_public_mark(self, **_: Any) -> Mapping[str, Any]:
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_OUTCOME_REPLAY_NETWORK_FORBIDDEN"
        )


def verify_v32_outcome_monitor_actual_capability_full_replay(
    *,
    project_root: Path,
    capability_receipt: Mapping[str, Any],
    evidence_root_binding: Mapping[str, str],
    qualification_authority: Mapping[str, Any],
) -> Mapping[str, Any]:
    capability = "OUTCOME_MONITOR"
    root = _load_root_from_callback(
        project_root=project_root,
        capability_receipt=capability_receipt,
        evidence_root_binding=evidence_root_binding,
        qualification_authority=qualification_authority,
        capability=capability,
    )
    descriptor = root["replay_descriptor"]
    try:
        probe_store = LocalV32QualificationMonitorProbeStore(
            _project_path(project_root, descriptor["probe_store_root"]),
            capture_port=_ReplayMustNotCapture(),
            clock=lambda: (_ for _ in ()).throw(
                V32ActualCapabilityReplayError("V32_ACTUAL_OUTCOME_REPLAY_CLOCK_FORBIDDEN")
            ),
        )
        replay = probe_store.replay()
        schedule = replay["schedule"]
        completion = replay["completion"]
        if (
            schedule.get("qualification_authority_digest")
            != qualification_authority[AUTHORITY_DIGEST_FIELD]
            or schedule.get("probe_id") != descriptor["probe_id"]
            or qualification_authority.get("outcome_schedules") != 0
            or qualification_authority.get("qualification_monitor_probes") != 1
            or replay["capture"].get("transport_status") != "RESPONSE_CAPTURED"
            or replay["observation"].get("status") != "OBSERVED_PUBLIC_MARK"
            or replay.get("replay_network_calls") != 0
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_OUTCOME_AUTHORITY_INVALID"
            )
        if (
            completion["started_at"] != root["started_at"]
            or completion["completed_at"] != root["completed_at"]
        ):
            raise V32ActualCapabilityReplayError(
                "V32_ACTUAL_OUTCOME_TIME_INVALID"
            )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActualCapabilityReplayError):
            raise
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_OUTCOME_FULL_REPLAY_INVALID"
        ) from exc
    expected = _standard_binding(
        project_root=project_root,
        relative_ref=(
            f"{descriptor['probe_store_root']}/{QUALIFICATION_PROBE_STORE_ROOT}/"
            "completion.json"
        ),
        document=completion,
        schema_id=PROBE_COMPLETION_SCHEMA_ID,
        digest_field=PROBE_COMPLETION_DIGEST_FIELD,
    )
    if (
        completion.get("schema_id") != PROBE_COMPLETION_SCHEMA_ID
        or completion.get(PROBE_COMPLETION_DIGEST_FIELD)
        != expected["semantic_digest"]
    ):
        raise V32ActualCapabilityReplayError(
            "V32_ACTUAL_OUTCOME_FULL_REPLAY_INVALID"
        )
    _verify_terminal_binding(project_root, root, expected, capability)
    return _root_replay_result(capability, root)


def build_v32_actual_capability_full_replay_registry() -> dict[str, Any]:
    return {
        "CURRENT_CODEX": verify_v32_current_codex_actual_capability_full_replay,
        "OUTCOME_MONITOR": verify_v32_outcome_monitor_actual_capability_full_replay,
        "PUBLIC_SOURCE": verify_v32_public_source_actual_capability_full_replay,
    }


__all__ = [
    "ATTEMPT_RESERVATION_DIGEST_FIELD",
    "ATTEMPT_RESERVATION_SCHEMA_ID",
    "EVIDENCE_ROOT_SPECS",
    "LocalV32ActualCapabilityEvidenceStore",
    "V32ActualCapabilityReplayError",
    "build_v32_actual_capability_attempt_reservation_v1",
    "build_v32_actual_capability_evidence_root_v1",
    "build_v32_actual_capability_full_replay_registry",
    "compose_v32_current_codex_actual_evidence_root",
    "compose_v32_outcome_monitor_actual_evidence_root",
    "compose_v32_public_source_actual_evidence_root",
    "verify_v32_actual_capability_attempt_reservation_v1",
    "verify_v32_actual_capability_evidence_root_v1",
    "verify_v32_current_codex_actual_capability_full_replay",
    "verify_v32_outcome_monitor_actual_capability_full_replay",
    "verify_v32_public_source_actual_capability_full_replay",
]
