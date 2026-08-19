"""Application-owned ports for the isolated V3.2 capability qualification.

The qualification use cases depend on these structural contracts only.  The
local filesystem store and the owning replay functions remain infrastructure
details selected by the fixed presentation composition root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


V32DocumentVerifier = Callable[[Mapping[str, Any]], str]


class V32ActualCapabilityFullReplayPort(Protocol):
    """Reopen and validate one durable capability chain without network I/O."""

    def __call__(
        self,
        *,
        project_root: Path,
        capability_receipt: Mapping[str, Any],
        evidence_root_binding: Mapping[str, Any],
        qualification_authority: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class V32ActualCapabilityEvidenceStorePort(Protocol):
    """Durable evidence repository required by the qualification use cases."""

    project_root: Path
    root_relative_ref: str

    @property
    def qualification_receipt_ref(self) -> str: ...

    def root_ref(self, capability: str) -> str: ...

    def receipt_ref(self, capability: str) -> str: ...

    def reserve_attempt(
        self,
        *,
        capability: str,
        qualification_run_id: str,
        target_run_id: str,
        qualification_authority_digest: str,
        reserved_at: str,
    ) -> Mapping[str, Any]: ...

    def load_attempt_reservation(
        self, capability: str
    ) -> Mapping[str, Any] | None: ...

    def load_evidence_root(
        self, capability: str
    ) -> Mapping[str, Any] | None: ...

    def load_binding(
        self,
        binding_value: Mapping[str, Any],
        *,
        verifier: V32DocumentVerifier,
    ) -> dict[str, Any]: ...

    def verify_evidence_root(self, document: Mapping[str, Any]) -> str: ...

    def full_replay_registry(
        self,
    ) -> Mapping[str, V32ActualCapabilityFullReplayPort]: ...

    def preview_typed_document_binding(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
    ) -> dict[str, str]: ...

    def persist_typed_documents_atomically(
        self, documents: list[Mapping[str, Any]]
    ) -> dict[str, dict[str, str]]: ...


class V32ActualCapabilityAttemptPort(Protocol):
    """One-shot capability attempt used by the legacy atomic runner."""

    def execute_once(
        self,
        *,
        capability: str,
        qualification_authority: Mapping[str, Any],
        qualification_authority_binding: Mapping[str, str],
        reservation: Mapping[str, Any],
        reservation_binding: Mapping[str, str],
    ) -> Mapping[str, Any]: ...


class V32DurableQualificationAttemptPort(Protocol):
    """Advance or observe the sole durable attempt for one capability."""

    def advance_once(
        self,
        *,
        qualification_authority: Mapping[str, Any],
        reservation: Mapping[str, Any],
        reservation_binding: Mapping[str, Any],
        resume_token: str | None,
        resume_requested_at: str | None,
    ) -> Mapping[str, Any]: ...

    def verify_failure_evidence_binding(
        self, binding_value: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


__all__ = [
    "V32ActualCapabilityAttemptPort",
    "V32ActualCapabilityEvidenceStorePort",
    "V32ActualCapabilityFullReplayPort",
    "V32DocumentVerifier",
    "V32DurableQualificationAttemptPort",
]
