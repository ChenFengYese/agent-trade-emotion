from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.infrastructure.event_store import (
    AggregatePrecondition,
    AggregateUpdate,
    E0CommitPlan,
    EventDraft,
    EventStoreError,
    FileUnitOfWork,
)


def plan(
    *,
    run_id: str = "run-1",
    commit_id: str = "commit-1",
    command_id: str = "command-1",
    expected_sequence: int | None = None,
    expected_digest: str | None = None,
    expected_revision: int = 0,
    expected_state_digest: str | None = None,
    next_revision: int = 1,
    state_digest: str = "b" * 64,
) -> E0CommitPlan:
    event = EventDraft(
        event_id=f"event-{commit_id}",
        event_type="STRATEGIC_STATE_ADVANCED",
        payload_schema_id="transition_receipt",
        payload_ref=f"artifact-{commit_id}",
        payload_digest="a" * 64,
        aggregate_id="episode-1",
    )
    return E0CommitPlan(
        commit_id=commit_id,
        offline_run_id=run_id,
        decision_session_id="session-1",
        committed_at="2026-07-01T00:00:00Z",
        idempotent_command_id=command_id,
        idempotency_key=command_id,
        expected_previous_event_sequence=expected_sequence,
        expected_previous_event_digest=expected_digest,
        aggregate_preconditions=(
            AggregatePrecondition(
                "episode-1",
                "STRATEGIC_EPISODE",
                expected_revision,
                expected_state_digest,
            ),
        ),
        accepted_artifact_digests=("a" * 64,),
        receding_horizon_plan_ref="rh-1",
        authorized_first_step_action_ref="action-1",
        conditional_future_action_refs=("future-action",),
        atomic_effect_refs=("effect-1",),
        events=(event,),
        aggregate_updates=(
            AggregateUpdate(
                "episode-1",
                "STRATEGIC_EPISODE",
                next_revision,
                f"state-{next_revision}",
                state_digest,
                event.event_id,
            ),
        ),
        counterfactual_policy_ref="policy-1",
        portfolio_replay_result_ref="portfolio-1",
    )


class EventStoreTests(unittest.TestCase):
    def test_atomic_commit_idempotency_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FileUnitOfWork(Path(directory), "run-1")
            first_plan = plan()
            first = store.commit(first_plan)
            retry = store.commit(first_plan)
            self.assertEqual(first, retry)
            self.assertEqual(1, len(store.read_after(None)))
            reopened = FileUnitOfWork(Path(directory), "run-1")
            self.assertEqual(first, reopened.load_commit("commit-1"))

    def test_stale_global_or_aggregate_head_is_no_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FileUnitOfWork(Path(directory), "run-1")
            first = store.commit(plan())
            with self.assertRaisesRegex(EventStoreError, "UOW_HEAD_STALE"):
                store.commit(
                    plan(
                        commit_id="commit-2",
                        command_id="command-2",
                        expected_sequence=None,
                        expected_digest=None,
                        expected_revision=1,
                        expected_state_digest="b" * 64,
                        next_revision=2,
                    )
                )
            self.assertEqual(1, len(store.read_after(None)))
            second = store.commit(
                plan(
                    commit_id="commit-2",
                    command_id="command-2",
                    expected_sequence=first.last_event_sequence,
                    expected_digest=first.event_chain_head_digest,
                    expected_revision=1,
                    expected_state_digest="b" * 64,
                    next_revision=2,
                    state_digest="c" * 64,
                )
            )
            self.assertEqual(1, second.last_event_sequence)

    def test_conflicting_idempotent_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FileUnitOfWork(Path(directory), "run-1")
            store.commit(plan())
            with self.assertRaisesRegex(EventStoreError, "UOW_PARTIAL_DUPLICATE"):
                store.commit(plan(commit_id="different", command_id="command-1"))

    def test_future_branch_cannot_be_current_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FileUnitOfWork(Path(directory), "run-1")
            invalid = plan()
            invalid = E0CommitPlan(
                **{
                    **{
                        field: getattr(invalid, field)
                        for field in invalid.__dataclass_fields__
                    },
                    "atomic_effect_refs": ("future-action",),
                }
            )
            with self.assertRaisesRegex(
                EventStoreError, "RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED"
            ):
                store.commit(invalid)
            self.assertEqual((), store.read_after(None))

    def test_explicit_run_id_forbids_current_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                EventStoreError, "EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED"
            ):
                FileUnitOfWork(Path(directory), "current")


if __name__ == "__main__":
    unittest.main()
