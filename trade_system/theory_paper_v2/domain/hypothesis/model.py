"""Immutable ordinal competing-hypothesis revisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from ..common import DomainError, DomainResult, ReducerStatus


class HypothesisStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CHALLENGED = "CHALLENGED"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: str
    direction: str
    timeframe_seconds: int
    premise_ids: tuple[str, ...]
    hard_invalidator_ids: tuple[str, ...]
    ordinal_rank: int
    status: HypothesisStatus = HypothesisStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class HypothesisBook:
    hypothesis_set_id: str
    revision: int
    hypotheses: tuple[Hypothesis, ...]
    previous_revision_digest: str | None
    revision_digest: str

    def __post_init__(self) -> None:
        ids = [item.hypothesis_id for item in self.hypotheses]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("HYPOTHESIS_SET_INVALID")
        ranks = [item.ordinal_rank for item in self.hypotheses]
        if len(ranks) != len(set(ranks)):
            raise ValueError("HYPOTHESIS_RANK_NOT_TOTAL")


def revise_hypothesis_book(
    prior: HypothesisBook,
    *,
    expected_revision: int,
    hypothesis_id: str,
    new_rank: int | None,
    new_status: HypothesisStatus | None,
    new_revision_digest: str,
) -> DomainResult[HypothesisBook]:
    if prior.revision != expected_revision:
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                "STATE_HEAD_STALE",
                "STATE",
                "IDEMPOTENT_RETRY",
                "hypothesis revision does not match accepted head",
            ),
        )
    if new_status is HypothesisStatus.ACTIVE:
        current = next(
            (item for item in prior.hypotheses if item.hypothesis_id == hypothesis_id),
            None,
        )
        if current and current.status in {
            HypothesisStatus.INVALIDATED,
            HypothesisStatus.CLOSED,
        }:
            return DomainResult(
                status=ReducerStatus.REJECTED,
                error=DomainError(
                    "STATE_TRANSITION_FORBIDDEN",
                    "STATE",
                    "NEVER",
                    "terminal hypothesis cannot reactivate",
                ),
            )
    found = False
    updated: list[Hypothesis] = []
    for item in prior.hypotheses:
        if item.hypothesis_id != hypothesis_id:
            updated.append(item)
            continue
        found = True
        updated.append(
            replace(
                item,
                ordinal_rank=item.ordinal_rank if new_rank is None else new_rank,
                status=item.status if new_status is None else new_status,
            )
        )
    if not found:
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                "STRATEGIC_PREMISE_MAPPING_MISSING",
                "STRATEGIC",
                "NEVER",
                "hypothesis id is not registered",
            ),
        )
    ranks = [item.ordinal_rank for item in updated]
    if len(ranks) != len(set(ranks)):
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                "STATE_ILLEGAL_COMBINATION",
                "STATE",
                "NEVER",
                "hypothesis ranks must remain unique",
            ),
        )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=HypothesisBook(
            hypothesis_set_id=prior.hypothesis_set_id,
            revision=prior.revision + 1,
            hypotheses=tuple(updated),
            previous_revision_digest=prior.revision_digest,
            revision_digest=new_revision_digest,
        ),
    )

