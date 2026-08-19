"""Receipt-bound review-source repository for continuous research cycles."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import load_json_strict, verify_self_digest
from ..domain.epistemic_inference import (
    EpistemicInferenceError,
    build_public_inference_trace,
)
from .research_cycle_store import (
    REQUIRED_EVIDENCE_ARTIFACT_BINDINGS,
    ResearchCycleStore,
    ResearchCycleStoreError,
)


class ResearchReviewRepositoryError(ValueError):
    pass


class ReceiptBoundFourCycleReviewRepository:
    """Verify four evidence receipts and load only their bound review rows."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root).resolve()

    def _contained(self, relative_ref: str) -> Path:
        if not relative_ref or Path(relative_ref).is_absolute():
            raise ResearchReviewRepositoryError("REVIEW_ARTIFACT_REF_INVALID")
        try:
            target = (self.run_root / relative_ref).resolve(strict=True)
            target.relative_to(self.run_root)
        except (OSError, ValueError) as exc:
            raise ResearchReviewRepositoryError("REVIEW_ARTIFACT_REF_INVALID") from exc
        if not target.is_file():
            raise ResearchReviewRepositoryError("REVIEW_ARTIFACT_REF_INVALID")
        return target

    @staticmethod
    def _verify_semantic_binding(path: Path, expected_digest: str) -> None:
        physical = hashlib.sha256(path.read_bytes()).hexdigest()
        if physical == expected_digest:
            return
        try:
            document = load_json_strict(path)
        except ValueError as exc:
            raise ResearchReviewRepositoryError("REVIEW_ARTIFACT_SEMANTIC_DIGEST_INVALID") from exc
        for field, value in document.items():
            if field.endswith("_digest") and value == expected_digest:
                try:
                    verify_self_digest(document, field)
                except ValueError:
                    continue
                return
        raise ResearchReviewRepositoryError("REVIEW_ARTIFACT_SEMANTIC_DIGEST_INVALID")

    def load_verified_cycle_rows(
        self, *, run_id: str, through_cycle: int
    ) -> tuple[Sequence[Mapping[str, Any]], Sequence[str]]:
        if not run_id or through_cycle < 4 or through_cycle % 4:
            raise ResearchReviewRepositoryError("REVIEW_WINDOW_INVALID")
        rows: list[Mapping[str, Any]] = []
        receipt_digests: list[str] = []
        for cycle_index in range(through_cycle - 3, through_cycle + 1):
            receipt_ref = f"evidence-receipts/cycle-{cycle_index:04d}.json"
            receipt_path = self._contained(receipt_ref)
            receipt = load_json_strict(receipt_path)
            try:
                receipt_digest = verify_self_digest(
                    receipt, "cycle_evidence_receipt_digest"
                )
            except ValueError as exc:
                raise ResearchReviewRepositoryError("REVIEW_EVIDENCE_RECEIPT_DIGEST_INVALID") from exc
            if (
                receipt.get("run_id") != run_id
                or receipt.get("cycle_index") != cycle_index
                or set(receipt.get("artifact_bindings", {}))
                != REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
                or set(receipt.get("artifact_refs", {}))
                != REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
                or set(receipt.get("artifact_sha256s", {}))
                != REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
            ):
                raise ResearchReviewRepositoryError("REVIEW_EVIDENCE_RECEIPT_INVALID")
            store = ResearchCycleStore(
                self.run_root, run_id=run_id, cycle_index=cycle_index
            )
            try:
                events = store.read_events()
            except ResearchCycleStoreError as exc:
                raise ResearchReviewRepositoryError(
                    f"REVIEW_EVENT_CHAIN_INVALID:{exc}"
                ) from exc
            evidence_events = [
                event
                for event in events
                if event["event_type"] == "CYCLE_EVIDENCE_RECEIPT_SEALED"
            ]
            if (
                len(evidence_events) != 1
                or evidence_events[0]["payload_ref"] != receipt_ref
                or evidence_events[0]["payload_digest"] != receipt_digest
                or evidence_events[0]["payload_sha256"]
                != hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            ):
                raise ResearchReviewRepositoryError("REVIEW_EVIDENCE_EVENT_BINDING_INVALID")
            for artifact_name in REQUIRED_EVIDENCE_ARTIFACT_BINDINGS:
                target = self._contained(receipt["artifact_refs"][artifact_name])
                physical = hashlib.sha256(target.read_bytes()).hexdigest()
                if physical != receipt["artifact_sha256s"][artifact_name]:
                    raise ResearchReviewRepositoryError("REVIEW_ARTIFACT_PHYSICAL_DRIFT")
                self._verify_semantic_binding(
                    target, receipt["artifact_bindings"][artifact_name]
                )
            market_snapshot_path = self._contained(
                receipt["artifact_refs"]["market_information_snapshot_digest"]
            )
            market_snapshot = load_json_strict(market_snapshot_path)
            try:
                verify_self_digest(
                    market_snapshot, "market_information_snapshot_digest"
                )
            except ValueError as exc:
                raise ResearchReviewRepositoryError(
                    "REVIEW_MARKET_SNAPSHOT_DIGEST_INVALID"
                ) from exc
            fact_ids = {
                str(row.get("fact_id") or "")
                for row in market_snapshot.get("facts", [])
                if isinstance(row, Mapping)
            }
            for fact in market_snapshot.get("facts", []):
                if not isinstance(fact, Mapping):
                    raise ResearchReviewRepositoryError(
                        "REVIEW_MARKET_FACT_INVALID"
                    )
                lineage = fact.get("lineage", [])
                if (
                    not isinstance(lineage, list)
                    or not set(lineage).issubset(fact_ids)
                ):
                    raise ResearchReviewRepositoryError(
                        "REVIEW_MARKET_LINEAGE_INVALID"
                    )
                if fact.get("value") is None:
                    continue
                raw_source = self._contained(str(fact.get("raw_ref") or ""))
                if hashlib.sha256(raw_source.read_bytes()).hexdigest() != fact.get(
                    "raw_sha256"
                ):
                    raise ResearchReviewRepositoryError(
                        "REVIEW_RAW_SOURCE_PHYSICAL_DRIFT"
                    )
            def bound_document(artifact_name: str) -> dict[str, Any]:
                return load_json_strict(
                    self._contained(receipt["artifact_refs"][artifact_name])
                )

            sentiment_state = bound_document("sentiment_state_digest")
            hypothesis_registry = bound_document("hypothesis_registry_digest")
            expectation_ledger = bound_document("expectation_ledger_digest")
            agent_context = bound_document("agent_context_digest")
            agent_proposal = bound_document("agent_proposal_digest")
            inference_trace = bound_document("public_inference_trace_digest")
            try:
                rebuilt_trace = build_public_inference_trace(
                    market_snapshot=market_snapshot,
                    sentiment_state=sentiment_state,
                    hypothesis_registry=hypothesis_registry,
                    expectation_ledger=expectation_ledger,
                    agent_context=agent_context,
                    agent_proposal=agent_proposal,
                    claims=inference_trace.get("claims", []),
                    decision_at=str(inference_trace.get("decision_at") or ""),
                )
            except EpistemicInferenceError as exc:
                raise ResearchReviewRepositoryError(
                    f"REVIEW_PUBLIC_INFERENCE_INVALID:{exc}"
                ) from exc
            if (
                rebuilt_trace["public_inference_trace_digest"]
                != inference_trace.get("public_inference_trace_digest")
            ):
                raise ResearchReviewRepositoryError(
                    "REVIEW_PUBLIC_INFERENCE_REPLAY_MISMATCH"
                )
            review_source_path = self._contained(
                receipt["artifact_refs"]["cycle_review_source_digest"]
            )
            review_source = load_json_strict(review_source_path)
            try:
                source_digest = verify_self_digest(
                    review_source, "cycle_review_source_digest"
                )
            except ValueError as exc:
                raise ResearchReviewRepositoryError("REVIEW_SOURCE_DIGEST_INVALID") from exc
            if (
                source_digest
                != receipt["artifact_bindings"]["cycle_review_source_digest"]
                or review_source.get("run_id") != run_id
                or review_source.get("cycle_index") != cycle_index
                or review_source.get("public_inference_trace_digest")
                != inference_trace["public_inference_trace_digest"]
                or not isinstance(review_source.get("review_row"), Mapping)
            ):
                raise ResearchReviewRepositoryError("REVIEW_SOURCE_BINDING_INVALID")
            rows.append(dict(review_source["review_row"]))
            receipt_digests.append(receipt_digest)
        return tuple(rows), tuple(receipt_digests)
