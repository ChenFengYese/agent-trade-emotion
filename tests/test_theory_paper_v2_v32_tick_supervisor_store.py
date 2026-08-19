from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_theory_paper_v2_v32_tick_supervisor import RUN_ID, digest
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
    STORE_ROOT,
    V32TickSupervisorStoreError,
)


def _genesis() -> dict:
    return build_v32_tick_supervisor_checkpoint(
        run_id=RUN_ID,
        experiment_contract_digest="a" * 64,
        active_authority_digest="b" * 64,
        research_checkpoint_digest="c" * 64,
        outcome_checkpoint_digest="d" * 64,
        timeframe_cache_digest="e" * 64,
        created_at="2026-08-07T00:00:00Z",
    )


def _permit(checkpoint: dict) -> dict:
    return build_v32_analysis_tick_permit(
        checkpoint=checkpoint,
        schedule_sets=[],
        analysis_decision_at="2026-08-07T00:15:00Z",
        issued_at="2026-08-07T00:15:01Z",
        research_checkpoint_digest=checkpoint["current_research_checkpoint_digest"],
        outcome_checkpoint_digest=checkpoint["current_outcome_checkpoint_digest"],
        timeframe_cache_digest=checkpoint["current_timeframe_cache_digest"],
        prior_dynamic_state_digest=checkpoint["current_dynamic_state_digest"],
    )


def _completion(permit: dict) -> dict:
    schedule = build_v32_outcome_schedule_set(
        run_id=RUN_ID,
        decision_id="decision:0001",
        cycle_index=1,
        decision_time=permit["analysis_decision_at"],
        scheduled_at="2026-08-07T00:15:02Z",
        sealed_decision_digest=digest("sealed-1"),
        evaluation_contract_digest="f" * 64,
    )
    return {
        "schedule_sets_before": [],
        "new_schedule_set": schedule,
        "accepted_state_digest": digest("accepted-1"),
        "shadow_decision_bundle_digest": digest("shadow-1"),
        "source_admission_digest": digest("source-1"),
        "source_admission_physical_sha256": digest("source-physical-1"),
        "proposal_lifecycle_digest": digest("proposal-1"),
        "selection_lifecycle_digest": digest("selection-1"),
        "final_action_plan_digest": digest("action-1"),
        "commit_envelope_digest": digest("commit-1"),
        "new_research_checkpoint_digest": digest("research-1"),
        "new_outcome_checkpoint_digest": digest("outcome-1"),
        "new_timeframe_cache_digest": digest("cache-1"),
        "new_dynamic_state_digest": digest("state-1"),
        "completed_at": "2026-08-07T00:15:03Z",
    }


class V32TickSupervisorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = LocalV32TickSupervisorStore(self.root)
        self.genesis = _genesis()
        self.store.initialize_checkpoint(checkpoint=self.genesis)

    def test_write_once_permit_completion_and_checkpoint_history(self) -> None:
        permit = _permit(self.genesis)
        opened = self.store.open_permit(
            permit=permit,
            schedule_sets=[],
            expected_checkpoint_digest=self.genesis[CHECKPOINT_DIGEST_FIELD],
            opened_at=permit["issued_at"],
        )
        completed = self.store.complete_analysis_tick(
            permit=permit,
            completion=_completion(permit),
            expected_checkpoint_digest=opened[CHECKPOINT_DIGEST_FIELD],
        )
        self.assertEqual("READY", completed["status"])
        self.assertEqual(1, completed["accepted_analysis_cycles"])
        self.assertIsNone(completed["active_permit_digest"])
        self.assertEqual(
            permit,
            self.store.load_permit(
                run_id=RUN_ID, permit_digest=permit[PERMIT_DIGEST_FIELD]
            ),
        )
        self.assertEqual(
            completed,
            self.store.load_checkpoint_by_digest(
                run_id=RUN_ID,
                checkpoint_digest=completed[CHECKPOINT_DIGEST_FIELD],
            ),
        )
        self.assertEqual(
            1,
            len(list((self.root / STORE_ROOT / "completions").glob("*.json"))),
        )

    def test_stale_cas_cannot_open_a_second_lane(self) -> None:
        permit = _permit(self.genesis)
        self.store.open_permit(
            permit=permit,
            schedule_sets=[],
            expected_checkpoint_digest=self.genesis[CHECKPOINT_DIGEST_FIELD],
            opened_at=permit["issued_at"],
        )
        with self.assertRaisesRegex(
            V32TickSupervisorStoreError, "CAS_CONFLICT"
        ):
            self.store.open_permit(
                permit=permit,
                schedule_sets=[],
                expected_checkpoint_digest=self.genesis[CHECKPOINT_DIGEST_FIELD],
                opened_at=permit["issued_at"],
            )

    def test_two_concurrent_open_attempts_have_one_winner(self) -> None:
        permit = _permit(self.genesis)

        def open_once() -> str:
            try:
                return str(
                    self.store.open_permit(
                        permit=permit,
                        schedule_sets=[],
                        expected_checkpoint_digest=self.genesis[
                            CHECKPOINT_DIGEST_FIELD
                        ],
                        opened_at=permit["issued_at"],
                    )["status"]
                )
            except V32TickSupervisorStoreError as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: open_once(), range(2)))
        self.assertEqual(1, results.count("ANALYSIS_TICK_OPEN"))
        self.assertEqual(1, sum("CAS_CONFLICT" in row for row in results))

    def test_permit_file_tamper_is_detected(self) -> None:
        permit = _permit(self.genesis)
        self.store.open_permit(
            permit=permit,
            schedule_sets=[],
            expected_checkpoint_digest=self.genesis[CHECKPOINT_DIGEST_FIELD],
            opened_at=permit["issued_at"],
        )
        path = self.root / STORE_ROOT / "permits" / (
            permit[PERMIT_DIGEST_FIELD] + ".json"
        )
        path.write_bytes(canonical_bytes(permit) + b" \n")
        with self.assertRaises(V32TickSupervisorStoreError):
            self.store.load_permit(
                run_id=RUN_ID, permit_digest=permit[PERMIT_DIGEST_FIELD]
            )

    def test_completion_pointer_crash_recovers_same_write_once_transition(
        self,
    ) -> None:
        permit = _permit(self.genesis)
        opened = self.store.open_permit(
            permit=permit,
            schedule_sets=[],
            expected_checkpoint_digest=self.genesis[CHECKPOINT_DIGEST_FIELD],
            opened_at=permit["issued_at"],
        )
        completion = _completion(permit)
        with mock.patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_tick_supervisor_store._atomic_json",
            side_effect=RuntimeError("checkpoint pointer crash"),
        ):
            with self.assertRaisesRegex(RuntimeError, "pointer crash"):
                self.store.complete_analysis_tick(
                    permit=permit,
                    completion=completion,
                    expected_checkpoint_digest=opened[
                        CHECKPOINT_DIGEST_FIELD
                    ],
                )
        still_open = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("ANALYSIS_TICK_OPEN", still_open["status"])
        recovered = self.store.complete_analysis_tick(
            permit=permit,
            completion=completion,
            expected_checkpoint_digest=still_open[CHECKPOINT_DIGEST_FIELD],
        )
        self.assertEqual("READY", recovered["status"])
        self.assertEqual(1, recovered["accepted_analysis_cycles"])
        self.assertEqual(
            1,
            len(list((self.root / STORE_ROOT / "completions").glob("*.json"))),
        )


if __name__ == "__main__":
    unittest.main()
