"""Application service for the repaired continuous research-cycle lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..domain.contracts.canonical import self_digest
from ..domain.research_integrity import build_four_cycle_review
from .ports import FourCycleReviewSourcePort, ResearchCycleStorePort


class ContinuousResearchCycleCoordinator:
    """Coordinate one cycle without owning market judgment or execution policy."""

    def __init__(
        self,
        store: ResearchCycleStorePort,
        *,
        run_id: str,
        cycle_index: int,
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.cycle_index = cycle_index

    def record_stage(
        self,
        *,
        event_type: str,
        payload_ref: str,
        payload_digest: str,
        actor: str,
        recorded_at: str,
        evidence_boundary: str,
    ) -> dict[str, Any]:
        return self.store.append_event(
            event_type=event_type,
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            actor=actor,
            recorded_at=recorded_at,
            evidence_boundary=evidence_boundary,
        )

    def enter_post_accept_finalization(
        self,
        *,
        checkpoint_path: Path,
        accepted_state_path: str,
        accepted_state_digest: str,
    ) -> dict[str, Any]:
        """Persist the accepted state as pending truth without advancing a cycle."""

        return self.store.enter_post_accept_checkpoint(
            checkpoint_path=checkpoint_path,
            accepted_state_path=accepted_state_path,
            accepted_state_digest=accepted_state_digest,
        )

    def seal_cycle_evidence(
        self,
        *,
        artifact_bindings: Mapping[str, str],
        recorded_at: str,
    ) -> dict[str, Any]:
        """Seal all accepted evidence before report or review can be built."""

        return self.store.seal_evidence_receipt(
            artifact_bindings=artifact_bindings,
            recorded_at=recorded_at,
        )

    def complete_cycle(
        self,
        *,
        checkpoint_path: Path,
        artifact_bindings: Mapping[str, str],
        accepted_state_path: str,
        recorded_at: str,
        review_digest: str | None,
    ) -> dict[str, Any]:
        receipt = self.store.seal_completion(
            artifact_bindings=artifact_bindings,
            accepted_state_path=accepted_state_path,
            recorded_at=recorded_at,
            review_digest=review_digest,
        )
        checkpoint = self.store.advance_checkpoint(
            checkpoint_path=checkpoint_path, completion_receipt=receipt
        )
        return {
            "completion_receipt": receipt,
            "checkpoint": checkpoint,
        }

    def recovery_status(self) -> dict[str, Any]:
        """Resume the deterministic tail; never regenerate an accepted judgment."""

        return self.store.post_accept_recovery_status()


def build_source_bound_four_cycle_review(
    *,
    review_sources: FourCycleReviewSourcePort,
    run_id: str,
    through_cycle: int,
) -> dict[str, Any]:
    """Compute a review only from four verified evidence receipts."""

    rows, receipt_digests = review_sources.load_verified_cycle_rows(
        run_id=run_id,
        through_cycle=through_cycle,
    )
    review = build_four_cycle_review(
        run_id=run_id,
        through_cycle=through_cycle,
        cycle_rows=rows,
    )
    review.pop("review_digest")
    review["source_evidence_receipt_digests"] = list(receipt_digests)
    review["source_binding"] = "FOUR_VERIFIED_CYCLE_EVIDENCE_RECEIPTS"
    return self_digest(review, "review_digest")
