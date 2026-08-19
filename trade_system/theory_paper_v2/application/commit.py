"""Compile one governed current action into the sole E0 UnitOfWork."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from ..domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ..domain.contracts.canonical import canonical_digest
from ..domain.deliberation import AgentSelection
from ..domain.evaluation import RecedingHorizonPlan
from ..domain.governance import (
    GovernanceAssessmentReceipt,
    GovernanceVerdict,
)
from ..infrastructure.event_store.models import (
    AggregatePrecondition,
    AggregateUpdate,
    E0CommitPlan,
    EventDraft,
)


class CommitCompilationError(ValueError):
    pass


class UnitOfWorkPort(Protocol):
    def commit(self, plan: E0CommitPlan) -> object: ...


@dataclass(frozen=True, slots=True)
class AggregateMutation:
    aggregate_id: str
    aggregate_type: str
    expected_revision: int
    expected_state_digest: str | None
    next_revision: int
    state_ref: str
    state_digest: str


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    result_ref: str
    result_digest: str
    counterfactual_policy_ref: str
    aggregate_mutations: tuple[AggregateMutation, ...]
    atomic_effect_refs: tuple[str, ...] = ()
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False


@dataclass(frozen=True, slots=True)
class CommitContext:
    commit_id: str
    offline_run_id: str
    decision_session_id: str
    committed_at: str
    idempotent_command_id: str
    idempotency_key: str
    expected_previous_event_sequence: int | None
    expected_previous_event_digest: str | None
    accepted_artifact_digests: tuple[str, ...] = ()

    def with_session_outputs(
        self,
        *,
        decision_session_id: str,
        accepted_artifact_digests: tuple[str, ...],
    ) -> "CommitContext":
        return replace(
            self,
            decision_session_id=decision_session_id,
            accepted_artifact_digests=accepted_artifact_digests,
        )


@dataclass(frozen=True, slots=True)
class SessionCommitResult:
    plan: E0CommitPlan
    receipt: object


def _event(
    *,
    event_id: str,
    event_type: str,
    payload_schema_id: str,
    payload_ref: str,
    payload_digest: str,
    aggregate_id: str | None,
) -> EventDraft:
    return EventDraft(
        event_id=event_id,
        event_type=event_type,
        payload_schema_id=payload_schema_id,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        aggregate_id=aggregate_id,
    )


def commit_e0_session(
    *,
    context: CommitContext,
    selection: AgentSelection,
    governance: GovernanceAssessmentReceipt,
    receding_horizon_plan: RecedingHorizonPlan,
    replay: ReplayOutcome,
    unit_of_work: UnitOfWorkPort,
) -> SessionCommitResult:
    """Commit only a governed, replayed current step.

    Conditional continuation branches are recorded in the plan but are never
    included in the current atomic effects.
    """

    if (
        governance.selection_valid is not GovernanceVerdict.PASS
        or governance.selection_ref != selection.selection_ref
        or governance.executable
        or governance.external_execution_authority
        != EXTERNAL_EXECUTION_AUTHORITY
    ):
        raise CommitCompilationError("GOVERNANCE_REJECTED_NO_COMMIT")
    if (
        not receding_horizon_plan.first_step_only
        or receding_horizon_plan.current_authorized_action_ref
        != selection.selected_candidate_ref
        or receding_horizon_plan.future_branch_authority
        != "REQUIRES_CURRENT_DATA_REAPPROVAL"
    ):
        raise CommitCompilationError(
            "RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED"
        )
    if (
        replay.system_mode != SYSTEM_MODE
        or replay.external_execution_authority
        != EXTERNAL_EXECUTION_AUTHORITY
        or replay.executable
        or not replay.aggregate_mutations
    ):
        raise CommitCompilationError("OFFLINE_REPLAY_FAILED_NO_COMMIT")

    selection_event_id = f"{context.commit_id}:selection"
    governance_event_id = f"{context.commit_id}:governance"
    replay_event_id = f"{context.commit_id}:replay"
    events = (
        _event(
            event_id=selection_event_id,
            event_type="AGENT_SELECTION_RECORDED",
            payload_schema_id="agent_selection",
            payload_ref=selection.selection_ref,
            payload_digest=selection.selection_digest,
            aggregate_id=None,
        ),
        _event(
            event_id=governance_event_id,
            event_type="GOVERNANCE_ASSESSED",
            payload_schema_id="governance_assessment_receipt",
            payload_ref=selection.selection_ref,
            payload_digest=canonical_digest(
                {
                    "selection": governance.selection_ref,
                    "expected_head": governance.expected_head_ref,
                    "constraints": governance.hard_constraint_verdict_refs,
                }
            ),
            aggregate_id=None,
        ),
        _event(
            event_id=replay_event_id,
            event_type="COUNTERFACTUAL_FILL_RECORDED",
            payload_schema_id="portfolio_replay_result",
            payload_ref=replay.result_ref,
            payload_digest=replay.result_digest,
            aggregate_id=None,
        ),
    )
    preconditions = tuple(
        AggregatePrecondition(
            aggregate_id=item.aggregate_id,
            aggregate_type=item.aggregate_type,
            expected_revision=item.expected_revision,
            expected_state_digest=item.expected_state_digest,
        )
        for item in replay.aggregate_mutations
    )
    updates = tuple(
        AggregateUpdate(
            aggregate_id=item.aggregate_id,
            aggregate_type=item.aggregate_type,
            next_revision=item.next_revision,
            state_ref=item.state_ref,
            state_digest=item.state_digest,
            cause_event_id=replay_event_id,
        )
        for item in replay.aggregate_mutations
    )
    plan = E0CommitPlan(
        commit_id=context.commit_id,
        offline_run_id=context.offline_run_id,
        decision_session_id=context.decision_session_id,
        committed_at=context.committed_at,
        idempotent_command_id=context.idempotent_command_id,
        idempotency_key=context.idempotency_key,
        expected_previous_event_sequence=(
            context.expected_previous_event_sequence
        ),
        expected_previous_event_digest=(
            context.expected_previous_event_digest
        ),
        aggregate_preconditions=preconditions,
        accepted_artifact_digests=context.accepted_artifact_digests,
        receding_horizon_plan_ref=receding_horizon_plan.plan_digest,
        authorized_first_step_action_ref=selection.selected_candidate_ref,
        conditional_future_action_refs=tuple(
            branch.planned_action_ref
            for branch in (
                receding_horizon_plan.conditional_continuation_branches
            )
        ),
        atomic_effect_refs=replay.atomic_effect_refs,
        events=events,
        aggregate_updates=updates,
        counterfactual_policy_ref=replay.counterfactual_policy_ref,
        portfolio_replay_result_ref=replay.result_ref,
    )
    receipt = unit_of_work.commit(plan)
    return SessionCommitResult(plan=plan, receipt=receipt)
