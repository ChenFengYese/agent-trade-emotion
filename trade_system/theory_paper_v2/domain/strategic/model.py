"""Immutable strategic state and leased lower-timeframe permissions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..policy import ActionIntent, GeometryOperation, ProtectiveActionType
from ..time_authority import ReviewClock


class StrategicStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CHALLENGED = "CHALLENGED"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


class ExposureStatus(StrEnum):
    FLAT = "FLAT"
    EXPOSED = "EXPOSED"
    RISK_REDUCED = "RISK_REDUCED"
    EXIT_PENDING = "EXIT_PENDING"
    RECONCILE_PENDING = "RECONCILE_PENDING"


class WorkflowProjection(StrEnum):
    ACTIVE = "ACTIVE"
    CHALLENGED = "CHALLENGED"
    RISK_REDUCED = "RISK_REDUCED"
    REENTRY_PENDING = "REENTRY_PENDING"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class StrategicEpisode:
    episode_id: str
    revision: int
    state_digest: str
    previous_state_digest: str | None
    strategic_status: StrategicStatus
    exposure_status: ExposureStatus
    strategic_timeframe_seconds: int
    hypothesis_set_id: str
    premise_ids: tuple[str, ...]
    hard_invalidator_ids: tuple[str, ...]
    review_clock: ReviewClock
    episode_risk_allocation_id: str
    reentry_contract_nonterminal: bool = False


@dataclass(frozen=True, slots=True)
class CrossTimescaleLease:
    lease_id: str
    strategic_episode_id: str
    strategic_state_digest: str
    strategic_state_revision: int
    valid_from: datetime
    valid_until: datetime
    next_strategic_review_at: datetime
    permitted_fast_action_intents: frozenset[ActionIntent]
    permitted_protective_actions: frozenset[ProtectiveActionType]
    permitted_geometry_operations: frozenset[GeometryOperation]
    terminal_safe_action_intent: ActionIntent

    def __post_init__(self) -> None:
        if any(
            value.tzinfo is None
            for value in (
                self.valid_from,
                self.valid_until,
                self.next_strategic_review_at,
            )
        ):
            raise ValueError("CLOCK_TIME_INVALID")
        if self.valid_until <= self.valid_from:
            raise ValueError("CROSS_TIMESCALE_LEASE_INVALID")

