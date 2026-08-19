"""Application-facing protocols; implementations live in Infrastructure."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


class ContentStorePort(Protocol):
    def put(self, namespace: str, artifact_id: str, payload: bytes) -> str: ...

    def get(self, namespace: str, artifact_id: str, digest: str) -> bytes: ...


class RoleAgentPort(Protocol):
    def invoke(
        self, role_id: str, canonical_input: bytes, expected_output_schema_id: str
    ) -> bytes: ...


class LegacySourcePort(Protocol):
    def load_cycle(
        self, run_root: Path, cycle_id: int, expected_manifest_digest: str
    ) -> Mapping[str, object]: ...


class UnitOfWorkPort(Protocol):
    def commit(self, plan: object) -> object: ...


class OfflinePortfolioPort(Protocol):
    def replay(
        self, initial_state: object, actions: Sequence[object], market_bars: Sequence[object]
    ) -> object: ...


class ResearchCycleStorePort(Protocol):
    """Persistence boundary for one continuous-cycle chronology."""

    def read_events(self) -> tuple[dict[str, Any], ...]: ...

    def append_event(
        self,
        *,
        event_type: str,
        payload_ref: str,
        payload_digest: str,
        actor: str,
        recorded_at: str,
        evidence_boundary: str,
    ) -> dict[str, Any]: ...

    def seal_evidence_receipt(
        self,
        *,
        artifact_bindings: Mapping[str, str],
        recorded_at: str,
    ) -> dict[str, Any]: ...

    def seal_completion(
        self,
        *,
        artifact_bindings: Mapping[str, str],
        accepted_state_path: str,
        recorded_at: str,
        review_digest: str | None,
    ) -> dict[str, Any]: ...

    def advance_checkpoint(
        self, *, checkpoint_path: Path, completion_receipt: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def enter_post_accept_checkpoint(
        self,
        *,
        checkpoint_path: Path,
        accepted_state_path: str,
        accepted_state_digest: str,
    ) -> dict[str, Any]: ...

    def post_accept_recovery_status(self) -> dict[str, Any]: ...


class FourCycleReviewSourcePort(Protocol):
    """Read and verify receipt-bound review rows; never accept caller metrics."""

    def load_verified_cycle_rows(
        self, *, run_id: str, through_cycle: int
    ) -> tuple[Sequence[Mapping[str, Any]], Sequence[str]]: ...


class ContinuousArtifactPort(Protocol):
    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str | None,
    ) -> Mapping[str, str]: ...

    def checkpoint_path(self) -> Path: ...

    def document_exists(self, *, relative_ref: str) -> bool: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str | None,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...


class ContinuousCheckpointPort(Protocol):
    def initialize(self, *, run_id: str) -> Mapping[str, Any]: ...

    def load(self, *, run_id: str) -> Mapping[str, Any]: ...

    def binding(self, *, run_id: str) -> Mapping[str, str]: ...

    def record_failure(
        self,
        *,
        run_id: str,
        cycle_index: int,
        failure_ref: str,
        failure_digest: str,
        resume_allowed: bool,
        accepted_state_exists: bool,
    ) -> Mapping[str, Any]: ...

    def open_cycle(self, *, run_id: str, cycle_index: int) -> Mapping[str, Any]: ...


class ContinuousCycleStoreFactoryPort(Protocol):
    def open_cycle(self, *, run_id: str, cycle_index: int) -> ResearchCycleStorePort: ...


class FixtureMarketCollectorPort(Protocol):
    def collect(
        self, *, run_id: str, cycle_index: int, as_of: str
    ) -> Mapping[str, Any]: ...


class FixtureStrategyAgentPort(Protocol):
    """Idempotent adapter that durably records a delivery before returning it."""

    def propose(
        self, *, context: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def deliberate(
        self, *, evaluation_set: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class FixtureComparatorPort(Protocol):
    def compare(
        self, *, cycle_index: int, accepted_state: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class NativeAgentTransportStorePort(Protocol):
    """Durable local store for the native Codex mailbox and controller cursor."""

    def document_exists(self, *, relative_ref: str) -> bool: ...

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...

    def initialize_checkpoint(
        self, *, run_id: str, created_at: str
    ) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def fail_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        failure_code: str,
        failure_summary: str,
        occurred_at: str,
    ) -> Mapping[str, Any]: ...


class NativeMarketPilotStorePort(NativeAgentTransportStorePort, Protocol):
    """Write-once market evidence plus a compare-and-swap pilot cursor."""

    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]: ...

    def initialize_market_checkpoint(
        self,
        *,
        run_id: str,
        created_at: str,
        first_due_at: str,
        total_cycles: int,
        cadence_seconds: int,
    ) -> Mapping[str, Any]: ...

    def load_market_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def replace_market_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class V31MarketDataPort(Protocol):
    """Collect one source-native snapshot; normalization remains a separate adapter step."""

    def collect_snapshot(
        self, *, run_id: str, cycle_index: int, decision_at: str
    ) -> Mapping[str, Any]: ...


class V31InformationSourcePort(Protocol):
    """Collect observable public information without inferring hidden intent."""

    def collect_information(
        self, *, run_id: str, cycle_index: int, decision_at: str
    ) -> Sequence[object]: ...


class V31AgentDeliberationPort(Protocol):
    """Two-stage Agent boundary; proposal cannot contain a selected action."""

    def propose(self, *, context: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def select(
        self, *, proposal: Mapping[str, Any], sealed_evaluation: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class V31ClockPort(Protocol):
    def now(self) -> str: ...


class V31DigestPort(Protocol):
    def digest(self, value: object) -> str: ...


class V31AssociationEstimatorPort(Protocol):
    """Estimate declared associations without promoting them to causal effects."""

    def estimate(
        self, *, dataset: Mapping[str, Any], specification: Mapping[str, Any]
    ) -> Sequence[Mapping[str, Any]]: ...


class V31ResearchStorePort(Protocol):
    """Write-once V3.1 artifacts, an append-only event chain, and one CAS cursor."""

    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]: ...

    def read_raw(
        self,
        *,
        relative_ref: str,
        expected_sha256: str | None = None,
    ) -> bytes: ...

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def discover_content_addressed_document(
        self,
        *,
        relative_dir: str,
        digest_field: str,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...

    def initialize_checkpoint(
        self,
        *,
        run_id: str,
        total_cycles: int,
        created_at: str,
        genesis_bindings: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def register_semantic_admission(
        self,
        *,
        run_id: str,
        cycle_index: int,
        artifact_digests: Mapping[str, str],
    ) -> None: ...

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def append_event(
        self,
        *,
        run_id: str,
        cycle_index: int,
        event_type: str,
        artifact_binding: Mapping[str, str],
        recorded_at: str,
    ) -> Mapping[str, Any]: ...

    def read_events(
        self, *, run_id: str, cycle_index: int
    ) -> Sequence[Mapping[str, Any]]: ...


class V31MonitorStorePort(Protocol):
    """Write-once delayed-outcome artifacts and one no-retry CAS cursor."""

    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]: ...

    def read_raw(
        self, *, relative_ref: str, expected_sha256: str | None = None
    ) -> bytes: ...

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...

    def initialize_checkpoint(
        self,
        *,
        run_id: str,
        experiment_contract_digest: str,
        total_cycles: int,
        created_at: str,
    ) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def fail_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        failure_code: str,
        failure_summary: str,
        occurred_at: str,
    ) -> Mapping[str, Any]: ...


class V31PublicOutcomeObservationPort(Protocol):
    """Sole external monitor port: one public OKX GET, never an account API."""

    def observe_public_outcome(
        self, *, monitor_plan: Mapping[str, Any], requested_at: str
    ) -> object: ...
