"""Typed UnitOfWork input and output objects."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE


@dataclass(frozen=True, slots=True)
class EventDraft:
    event_id: str
    event_type: str
    payload_schema_id: str
    payload_ref: str
    payload_digest: str
    aggregate_id: str | None


@dataclass(frozen=True, slots=True)
class AggregatePrecondition:
    aggregate_id: str
    aggregate_type: str
    expected_revision: int
    expected_state_digest: str | None


@dataclass(frozen=True, slots=True)
class AggregateUpdate:
    aggregate_id: str
    aggregate_type: str
    next_revision: int
    state_ref: str
    state_digest: str
    cause_event_id: str


@dataclass(frozen=True, slots=True)
class E0CommitPlan:
    commit_id: str
    offline_run_id: str
    decision_session_id: str
    committed_at: str
    idempotent_command_id: str
    idempotency_key: str
    expected_previous_event_sequence: int | None
    expected_previous_event_digest: str | None
    aggregate_preconditions: tuple[AggregatePrecondition, ...]
    accepted_artifact_digests: tuple[str, ...]
    receding_horizon_plan_ref: str
    authorized_first_step_action_ref: str
    conditional_future_action_refs: tuple[str, ...]
    atomic_effect_refs: tuple[str, ...]
    events: tuple[EventDraft, ...]
    aggregate_updates: tuple[AggregateUpdate, ...]
    counterfactual_policy_ref: str
    portfolio_replay_result_ref: str
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False


@dataclass(frozen=True, slots=True)
class CommitReceipt:
    commit_id: str
    idempotent_command_id: str
    input_digest: str
    batch_digest: str
    first_event_sequence: int
    last_event_sequence: int
    event_chain_head_digest: str
    committed_at: str
    aggregate_head_digests: tuple[tuple[str, str], ...]
    receipt_digest: str
