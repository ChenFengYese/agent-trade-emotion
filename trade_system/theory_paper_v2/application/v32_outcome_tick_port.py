"""Application-owned ports and persistence identities for V3.2 outcomes."""

from __future__ import annotations

from typing import Any, ContextManager, Mapping, Protocol


CHECKPOINT_SCHEMA_ID = "theory_paper_v32_outcome_tick_checkpoint_v1"
CHECKPOINT_SCHEMA_VERSION = "1.0.0"
RAW_CAPTURE_SCHEMA_ID = "theory_paper_v32_public_raw_capture_v1"
RAW_CAPTURE_DIGEST_FIELD = "public_raw_capture_digest"
TRANSPORT_FAILURE_SCHEMA_ID = "theory_paper_v32_public_transport_failure_v1"
TRANSPORT_FAILURE_DIGEST_FIELD = "public_transport_failure_digest"
COVERAGE_FAILURE_SCHEMA_ID = "theory_paper_v32_public_coverage_failure_v1"
COVERAGE_FAILURE_DIGEST_FIELD = "public_coverage_failure_digest"
PARSE_RECEIPT_SCHEMA_ID = "theory_paper_v32_public_mark_parse_receipt_v1"
PARSE_RECEIPT_DIGEST_FIELD = "public_mark_parse_receipt_digest"


class V32OutcomeTickPersistenceError(ValueError):
    """The outcome persistence adapter failed closed."""


class V32PublicOutcomeCapturePort(Protocol):
    def capture_public_mark(
        self, *, attempt: Mapping[str, Any], requested_at: str
    ) -> Mapping[str, Any]: ...


class V32OutcomeTickStorePort(Protocol):
    def resolution_guard(self, *, run_id: str) -> ContextManager[None]: ...

    def build_outcome_tick_checkpoint(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def build_public_coverage_failure(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def build_public_mark_parse_receipt(
        self, **kwargs: Any
    ) -> Mapping[str, Any]: ...

    def initialize_checkpoint(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def load_checkpoint(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def load_schedule_sets(self, **kwargs: Any) -> list[Mapping[str, Any]]: ...

    def load_terminal_receipts(self, **kwargs: Any) -> list[Mapping[str, Any]]: ...

    def load_batch_intents(self, **kwargs: Any) -> list[Mapping[str, Any]]: ...

    def reserve_attempt(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def recover_unbound_evidence(self, **kwargs: Any) -> bool: ...

    def commit_raw_capture(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def commit_transport_failure(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def commit_normalization(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def commit_observation_tick(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def commit_batch_intent(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def commit_outcome_receipt(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def commit_batch_completion(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def tick_prefix(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def fail_closed(self, **kwargs: Any) -> Mapping[str, Any]: ...


__all__ = [
    "CHECKPOINT_SCHEMA_ID",
    "CHECKPOINT_SCHEMA_VERSION",
    "COVERAGE_FAILURE_DIGEST_FIELD",
    "COVERAGE_FAILURE_SCHEMA_ID",
    "PARSE_RECEIPT_DIGEST_FIELD",
    "PARSE_RECEIPT_SCHEMA_ID",
    "RAW_CAPTURE_DIGEST_FIELD",
    "RAW_CAPTURE_SCHEMA_ID",
    "TRANSPORT_FAILURE_DIGEST_FIELD",
    "TRANSPORT_FAILURE_SCHEMA_ID",
    "V32OutcomeTickPersistenceError",
    "V32OutcomeTickStorePort",
    "V32PublicOutcomeCapturePort",
]
