"""Five public ports and bounded internal transport values for market cycles."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.market_cycle.contracts import (
        ArtifactRef,
        BehaviorPlan,
        CycleRequest,
        HypothesisRecord,
        InputSnapshot,
        Outcome,
        Review,
        RunState,
    )


class MarketCyclePortError(RuntimeError):
    """A port could not honor its bounded public contract."""


class AgentAnalysisPending(MarketCyclePortError):
    """The single Agent request exists but has no valid delivery yet."""

    def __init__(self, request_ref: str) -> None:
        super().__init__("MARKET_CYCLE_AGENT_DELIVERY_PENDING")
        self.request_ref = request_ref


class AgentReviewPending(MarketCyclePortError):
    """The review request exists but has no valid Agent delivery yet."""

    def __init__(self, request_ref: str) -> None:
        super().__init__("MARKET_CYCLE_AGENT_REVIEW_DELIVERY_PENDING")
        self.request_ref = request_ref


class AgentDecisionDeadlineExpired(MarketCyclePortError):
    """A trusted transport clock reached the frozen Worker hard stop."""

    def __init__(self) -> None:
        super().__init__("CONTROLLER_DECISION_DEADLINE_EXPIRED")


class AgentReviewDeadlineExpired(MarketCyclePortError):
    """A trusted transport clock reached the frozen Review Worker hard stop."""

    def __init__(self) -> None:
        super().__init__("CONTROLLER_REVIEW_DEADLINE_EXPIRED")


@dataclass(frozen=True, slots=True)
class AgentDecision:
    """System-owned envelope view over one verbatim Agent decision."""

    cycle_id: str
    request_sha256: str
    theory_identity: Mapping[str, Any]
    delivered_at: str
    decision_text: str
    decision_size_bytes: int
    decision_sha256: str
    delivery_path: str
    delivery_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "request_sha256": self.request_sha256,
            "theory_identity": dict(self.theory_identity),
            "delivered_at": self.delivered_at,
            "decision_text": self.decision_text,
            "decision_size_bytes": self.decision_size_bytes,
            "decision_sha256": self.decision_sha256,
            "delivery_path": self.delivery_path,
            "delivery_sha256": self.delivery_sha256,
        }


@dataclass(frozen=True, slots=True)
class AgentReview:
    """System-owned envelope view over one verbatim Agent review."""

    cycle_id: str
    request_sha256: str
    theory_identity: Mapping[str, Any]
    review_requested_at: str
    review_due_at: str
    delivered_at: str
    review_text: str
    review_size_bytes: int
    review_sha256: str
    delivery_path: str
    delivery_sha256: str


@dataclass(frozen=True, slots=True)
class MarketCaptureRequest:
    cycle_id: str
    venue_id: str
    instrument_id: str
    contract_type: str
    requested_at: str
    analysis_profile: str
    data_profile: str


@dataclass(frozen=True, slots=True)
class MarketDataObservation:
    captured_at: str
    cutoff_at: str
    core_observations: Mapping[str, Any]
    optional_observations: Mapping[str, Any]
    unknowns: tuple[Mapping[str, Any], ...]
    raw_refs: tuple[Mapping[str, Any], ...]
    source_health: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class AgentPacket:
    cycle_id: str
    request_id: str
    theory_identity: Mapping[str, Any]
    theory_fragments: Mapping[str, str]
    input_snapshot_ref: Mapping[str, Any]
    input_snapshot: Mapping[str, Any]
    lawful_actions: tuple[str, ...]
    memory_context: Mapping[str, Any]
    deterministic_calculations: Mapping[str, Any]
    decision_deadline_at: str
    token_budget: int
    time_budget_seconds: int
    paper_context: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        value = {
            "cycle_id": self.cycle_id,
            "request_id": self.request_id,
            "theory_identity": dict(self.theory_identity),
            "theory_fragments": dict(self.theory_fragments),
            "input_snapshot_ref": dict(self.input_snapshot_ref),
            "input_snapshot": dict(self.input_snapshot),
            "lawful_actions": list(self.lawful_actions),
            "memory_context": dict(self.memory_context),
            "deterministic_calculations": dict(
                self.deterministic_calculations
            ),
            "decision_deadline_at": self.decision_deadline_at,
            "token_budget": self.token_budget,
            "time_budget_seconds": self.time_budget_seconds,
        }
        if self.paper_context is not None:
            value["paper_context"] = dict(self.paper_context)
        return value


class DecisionContextPort(Protocol):
    """Build a read-only, decision-time context from existing fact owners."""

    def context(
        self, snapshot: InputSnapshot, snapshot_ref: ArtifactRef
    ) -> Mapping[str, Any] | None: ...

    def verifies_context(
        self,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        context: Mapping[str, Any],
    ) -> bool: ...

    def review_context(
        self,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        *,
        review_cutoff_at: str,
    ) -> Mapping[str, Any] | None: ...

    def verifies_review_context(
        self,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        context: Mapping[str, Any],
        *,
        review_cutoff_at: str,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class AgentReviewPacket:
    cycle_id: str
    theory_identity: Mapping[str, Any]
    theory_fragments: Mapping[str, str]
    input_snapshot_ref: Mapping[str, Any]
    input_snapshot: Mapping[str, Any]
    agent_decision_ref: Mapping[str, Any]
    agent_decision: Mapping[str, Any]
    hypothesis_record_ref: Mapping[str, Any]
    hypothesis_record: Mapping[str, Any]
    behavior_plan_ref: Mapping[str, Any]
    behavior_plan: Mapping[str, Any]
    outcome_ref: Mapping[str, Any]
    outcome: Mapping[str, Any]
    memory_context: Mapping[str, Any]
    deterministic_calculations: Mapping[str, Any]
    token_budget: int
    time_budget_seconds: int
    paper_review_context: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        value = {
            "cycle_id": self.cycle_id,
            "theory_identity": dict(self.theory_identity),
            "theory_fragments": dict(self.theory_fragments),
            "input_snapshot_ref": dict(self.input_snapshot_ref),
            "input_snapshot": dict(self.input_snapshot),
            "agent_decision_ref": dict(self.agent_decision_ref),
            "agent_decision": dict(self.agent_decision),
            "hypothesis_record_ref": dict(self.hypothesis_record_ref),
            "hypothesis_record": dict(self.hypothesis_record),
            "behavior_plan_ref": dict(self.behavior_plan_ref),
            "behavior_plan": dict(self.behavior_plan),
            "outcome_ref": dict(self.outcome_ref),
            "outcome": dict(self.outcome),
            "memory_context": dict(self.memory_context),
            "deterministic_calculations": dict(
                self.deterministic_calculations
            ),
            "token_budget": self.token_budget,
            "time_budget_seconds": self.time_budget_seconds,
        }
        if self.paper_review_context is not None:
            value["paper_review_context"] = dict(self.paper_review_context)
        return value


@dataclass(frozen=True, slots=True)
class OutcomeRequest:
    cycle_id: str
    venue_id: str
    instrument_id: str
    price_field: str
    due_at: str
    tolerance_seconds: int
    path_start_at: str | None = None


@dataclass(frozen=True, slots=True)
class OutcomeObservation:
    observed_at: str
    effective_at: str | None
    available_at: str | None
    terminal_status: str
    value: str | None
    unit: str | None
    missing_reason: str | None
    raw_ref: Mapping[str, Any] | None
    source_health: tuple[Mapping[str, Any], ...]
    path_observations: Mapping[str, Any] | None = None
    additional_raw_refs: tuple[Mapping[str, Any], ...] = ()


class MarketDataPort(Protocol):
    def capture(self, request: MarketCaptureRequest) -> MarketDataObservation: ...


class AgentPort(Protocol):
    def analyze(self, packet: AgentPacket) -> AgentDecision: ...

    def review(self, packet: AgentReviewPacket) -> AgentReview: ...

    def persist_decision(
        self,
        cycle_id: str,
        decision_bytes: bytes,
        *,
        media_type: str,
        deadline_at: str,
    ) -> str: ...

    def persist_review(
        self,
        cycle_id: str,
        review_bytes: bytes,
        *,
        media_type: str,
        deadline_at: str,
    ) -> str: ...

    def persist_goal_decision(
        self,
        cycle_id: str,
        decision_bytes: bytes,
        *,
        media_type: str,
    ) -> str: ...

    def persist_goal_review(
        self,
        cycle_id: str,
        review_bytes: bytes,
        *,
        media_type: str,
    ) -> str: ...

    def delivery_present(self, cycle_id: str) -> bool: ...

    def review_delivery_present(self, cycle_id: str) -> bool: ...


class ControllerDispatchPort(Protocol):
    """Durable Controller scheduling and Agent-dispatch state."""

    def status(self) -> Mapping[str, Any]: ...

    def trusted_now(self) -> str: ...

    def schedule_event(
        self,
        event_id: str,
        event_type: str,
        due_at: str,
        cycle_id: str | None = None,
    ) -> Mapping[str, Any]: ...

    def acknowledge_wake(
        self, event_id: str, scheduler_ref: str, scheduled_for: str
    ) -> Mapping[str, Any]: ...

    def resolve_event(self, event_id: str) -> Mapping[str, Any]: ...

    def materialize_worker_task(
        self, cycle_id: str, worker_id: str
    ) -> Path: ...

    def prepare_worker(
        self,
        cycle_id: str,
        worker_id: str,
        task_path: str | Path,
        *,
        next_slot_at: str | None = None,
    ) -> Mapping[str, Any]: ...

    def mark_spawn_requested(
        self, cycle_id: str, worker_id: str, dispatch_id: str
    ) -> Mapping[str, Any]: ...

    def acknowledge_spawn(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        execution_ref: str,
    ) -> Mapping[str, Any]: ...

    def admit_worker_result_for_delivery(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]: ...

    def complete_worker(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        output_sha256: str,
    ) -> Mapping[str, Any]: ...

    def recover_worker(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]: ...

    def require_worker_deadline_expired(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]: ...

    def mark_worker_expired(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        reason_code: str,
    ) -> Mapping[str, Any]: ...

    def decision_deadline(self, cycle_id: str) -> Mapping[str, Any]: ...


class ClockPort(Protocol):
    def __call__(self) -> str: ...

    def monotonic_ns(self) -> int: ...


class CycleRepository(Protocol):
    def create(self, request: "CycleRequest") -> "RunState": ...

    def locked(self, cycle_id: str) -> AbstractContextManager[None]: ...

    def load_state(self, cycle_id: str) -> "RunState": ...

    def load_request(self, cycle_id: str) -> "CycleRequest": ...

    def load_artifact(self, cycle_id: str, artifact_type: str) -> Mapping[str, Any]: ...

    def recover_pending(self, cycle_id: str) -> "RunState | None": ...

    def transition(
        self,
        *,
        expected: "RunState",
        artifacts: Sequence[
            "InputSnapshot | HypothesisRecord | BehaviorPlan | Outcome | Review"
        ],
        next_stage: str,
        next_action: str | None,
        terminal: bool = False,
        failure_reason: str | None = None,
    ) -> "RunState": ...


class OutcomePort(Protocol):
    def observe(self, request: OutcomeRequest) -> OutcomeObservation: ...


__all__ = [
    "AgentAnalysisPending",
    "AgentDecisionDeadlineExpired",
    "AgentDecision",
    "AgentPacket",
    "AgentPort",
    "AgentReview",
    "AgentReviewDeadlineExpired",
    "AgentReviewPacket",
    "AgentReviewPending",
    "ClockPort",
    "ControllerDispatchPort",
    "DecisionContextPort",
    "CycleRepository",
    "MarketCaptureRequest",
    "MarketCyclePortError",
    "MarketDataObservation",
    "MarketDataPort",
    "OutcomeObservation",
    "OutcomePort",
    "OutcomeRequest",
]
