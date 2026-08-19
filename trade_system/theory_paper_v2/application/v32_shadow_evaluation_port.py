"""Application-owned persistence port for V3.2 shadow evaluations.

Infrastructure adapters depend on this contract.  Application composition
never imports a concrete filesystem adapter.
"""

from __future__ import annotations

from typing import Any, ContextManager, Mapping, Protocol


CHECKPOINT_SCHEMA_ID = "theory_paper_v32_shadow_evaluation_checkpoint_v1"
CHECKPOINT_DIGEST_FIELD = "shadow_evaluation_checkpoint_digest"


class V32ShadowEvaluationPersistenceError(ValueError):
    """A shadow-evaluation persistence port invariant failed closed."""


class V32ShadowEvaluationStorePort(Protocol):
    def evaluation_guard(self, *, run_id: str) -> ContextManager[None]: ...

    def initialize_checkpoint(
        self, *, run_id: str, created_at: str
    ) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def verify_bound_document(
        self, *, document: Mapping[str, Any], binding: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def commit_evaluation(
        self,
        *,
        evaluation: Mapping[str, Any],
        shadow_decision_bundle: Mapping[str, Any],
        outcome_schedule_set: Mapping[str, Any],
        outcome_receipt: Mapping[str, Any],
        outcome_batch_completion: Mapping[str, Any],
        outcome_batch_completion_binding: Mapping[str, Any],
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any]: ...


__all__ = [
    "CHECKPOINT_DIGEST_FIELD",
    "CHECKPOINT_SCHEMA_ID",
    "V32ShadowEvaluationPersistenceError",
    "V32ShadowEvaluationStorePort",
]
