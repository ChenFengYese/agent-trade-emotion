from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
)
from trade_system.theory_paper_v2.infrastructure.event_store import (
    AggregatePrecondition,
    AggregateUpdate,
    E0CommitPlan,
    EventCompatibilityError,
    EventDraft,
    FileUnitOfWork,
    build_event_replay_compatibility_manifest,
    require_authoritative_command_head,
    verify_event_replay_compatibility,
)


class EventCompatibilityTests(unittest.TestCase):
    def plan(self):
        return E0CommitPlan(
            commit_id="commit-1",
            offline_run_id="run-compat",
            decision_session_id="session-1",
            committed_at="2026-07-31T12:00:00Z",
            idempotent_command_id="command-1",
            idempotency_key="key-1",
            expected_previous_event_sequence=None,
            expected_previous_event_digest=None,
            aggregate_preconditions=(
                AggregatePrecondition(
                    aggregate_id="counter:1",
                    aggregate_type="COUNTER",
                    expected_revision=0,
                    expected_state_digest=None,
                ),
            ),
            accepted_artifact_digests=("a" * 64,),
            receding_horizon_plan_ref="plan:1",
            authorized_first_step_action_ref="action:1",
            conditional_future_action_refs=(),
            atomic_effect_refs=(),
            events=(
                EventDraft(
                    event_id="event:increment",
                    event_type="COUNTER_INCREMENTED",
                    payload_schema_id="counter_increment",
                    payload_ref="increment:1",
                    payload_digest="b" * 64,
                    aggregate_id="counter:1",
                ),
            ),
            aggregate_updates=(
                AggregateUpdate(
                    aggregate_id="counter:1",
                    aggregate_type="COUNTER",
                    next_revision=1,
                    state_ref="counter-state:1",
                    state_digest="c" * 64,
                    cause_event_id="event:increment",
                ),
            ),
            counterfactual_policy_ref="policy:1",
            portfolio_replay_result_ref="replay:1",
        )

    @staticmethod
    def reducer(state, event):
        return {"count": int(state["count"]) + 1}

    def test_full_replay_reproduces_frozen_state_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileUnitOfWork(Path(directory), "run-compat")
            receipt = store.commit(self.plan())
            genesis = {"count": 0}
            final = {"count": 1}
            manifest = build_event_replay_compatibility_manifest(
                manifest_id="compat:1",
                genesis_contract_ref="genesis:1",
                genesis_state_digest=canonical_digest(genesis),
                first_event_sequence=0,
                last_event_sequence=0,
                expected_event_chain_head_digest=(
                    receipt.event_chain_head_digest
                ),
                event_schema_version_refs=("counter_increment:1.0.0",),
                reducer_version_refs=("counter-reducer:1.0.0",),
                full_replay_expected_digest=canonical_digest(final),
                compatibility_test_refs=("test:counter-replay",),
            )
            first = verify_event_replay_compatibility(
                manifest=manifest,
                store=store,
                genesis_state=genesis,
                reducer=self.reducer,
            )
            second = verify_event_replay_compatibility(
                manifest=manifest,
                store=store,
                genesis_state=genesis,
                reducer=self.reducer,
            )
            self.assertEqual(first, second)
            with self.assertRaisesRegex(
                EventCompatibilityError,
                "EVENT_REPLAY_STATE_DIGEST_MISMATCH",
            ):
                verify_event_replay_compatibility(
                    manifest=replace(
                        manifest, full_replay_expected_digest="0" * 64
                    ),
                    store=store,
                    genesis_state=genesis,
                    reducer=self.reducer,
                )

    def test_projection_or_snapshot_cannot_be_command_head(self):
        for kind in ("PROJECTION", "PORTFOLIO_SNAPSHOT", "REPORT"):
            with self.assertRaisesRegex(
                EventCompatibilityError, "PROJECTION_NOT_COMMAND_HEAD"
            ):
                require_authoritative_command_head(
                    head_kind=kind,
                    aggregate_revision=1,
                    aggregate_state_digest="a" * 64,
                )
        require_authoritative_command_head(
            head_kind="AGGREGATE_HEAD_RECEIPT",
            aggregate_revision=1,
            aggregate_state_digest="a" * 64,
        )


if __name__ == "__main__":
    unittest.main()
