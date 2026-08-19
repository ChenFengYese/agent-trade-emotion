from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import hashlib
import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.application.v31_experiment_supervisor_v2 import (
    V31ExperimentSupervisorV2WorkflowError,
    complete_v31_experiment_supervisor_v2,
    fail_v31_experiment_supervisor_v2,
    initialize_v31_experiment_supervisor_v2,
    open_v31_cycle_permit_v2,
    record_v31_cycle_commit_v2,
    reserve_v31_cycle_commit_v2,
    verify_v31_cycle_permit_live_v2,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.v31_experiment_supervisor_v2 import (
    CYCLE_PERMIT_DIGEST_FIELD,
    build_cycle_permit_v2,
    cycle_permit_ref_v2,
)
from trade_system.theory_paper_v2.infrastructure.v31_supervisor_store_v2 import (
    LocalV31SupervisorStoreV2,
    V31SupervisorStoreV2Error,
)
from trade_system.theory_paper_v2.infrastructure.v31_monitor_store import (
    LocalV31MonitorStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)


RUN_ID = "v31-supervisor-v2-test-run"
CONTRACT_DIGEST = "a" * 64
AUTHORITY_DIGEST = "b" * 64


def _physical(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()


class FakeResearchStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.nonce = 0
        self.checkpoint = self_digest(
            {
                "schema_id": "fake_research_checkpoint",
                "schema_version": "1.0.0",
                "run_id": RUN_ID,
                "status": "READY_FOR_CYCLE",
                "total_cycles": 8,
                "completed_cycles": 0,
                "next_cycle_index": 1,
                "active_cycle_index": None,
                "accepted_state_ref": None,
                "accepted_state_digest": None,
                "current_authority_digest": AUTHORITY_DIGEST,
                "failure_digest": None,
                "resume_allowed": True,
                "nonce": self.nonce,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "checkpoint_digest",
        )

    def load_checkpoint(self, *, run_id: str):
        if run_id != RUN_ID:
            raise ValueError("wrong run")
        verify_self_digest(self.checkpoint, "checkpoint_digest")
        return copy.deepcopy(self.checkpoint)

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ):
        document = copy.deepcopy(self.documents[relative_ref])
        digest = verify_self_digest(document, digest_field)
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise ValueError("semantic drift")
        return document

    def commit_cycle(self, cycle_index: int) -> str:
        accepted_ref = f"cycles/{cycle_index:04d}/accepted-research-state.json"
        accepted = self_digest(
            {
                "schema_id": "fake_accepted_state",
                "schema_version": "1.0.0",
                "run_id": RUN_ID,
                "cycle_index": cycle_index,
            },
            "accepted_state_digest",
        )
        self.documents[accepted_ref] = accepted
        self.nonce += 1
        self.checkpoint = self_digest(
            {
                **{
                    key: value
                    for key, value in self.checkpoint.items()
                    if key != "checkpoint_digest"
                },
                "status": "TERMINAL" if cycle_index == 8 else "READY_FOR_CYCLE",
                "completed_cycles": cycle_index,
                "next_cycle_index": cycle_index + 1,
                "active_cycle_index": None,
                "accepted_state_ref": accepted_ref,
                "accepted_state_digest": accepted["accepted_state_digest"],
                "nonce": self.nonce,
            },
            "checkpoint_digest",
        )
        return accepted["accepted_state_digest"]

    def touch(self) -> None:
        self.nonce += 1
        self.checkpoint = self_digest(
            {
                **{
                    key: value
                    for key, value in self.checkpoint.items()
                    if key != "checkpoint_digest"
                },
                "nonce": self.nonce,
            },
            "checkpoint_digest",
        )


class FakeMonitorStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.nonce = 0
        self.checkpoint = self_digest(
            {
                "schema_id": "fake_monitor_checkpoint",
                "schema_version": "1.0.0",
                "run_id": RUN_ID,
                "experiment_contract_digest": CONTRACT_DIGEST,
                "status": "ACTIVE",
                "total_cycles": 8,
                "plan_bindings": [],
                "resolution_attempt_bindings": [],
                "outcome_bindings": [],
                "last_outcome_receipt_digest": None,
                "failure_digest": None,
                "resume_allowed": True,
                "nonce": self.nonce,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "checkpoint_digest",
        )

    def _replace(self, **updates) -> None:
        self.nonce += 1
        self.checkpoint = self_digest(
            {
                **{
                    key: value
                    for key, value in self.checkpoint.items()
                    if key != "checkpoint_digest"
                },
                **updates,
                "nonce": self.nonce,
            },
            "checkpoint_digest",
        )

    def load_checkpoint(self, *, run_id: str):
        if run_id != RUN_ID:
            raise ValueError("wrong run")
        verify_self_digest(self.checkpoint, "checkpoint_digest")
        return copy.deepcopy(self.checkpoint)

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ):
        document = copy.deepcopy(self.documents[relative_ref])
        digest = verify_self_digest(document, digest_field)
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise ValueError("semantic drift")
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ):
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        return {
            "relative_ref": relative_ref,
            "schema_id": document["schema_id"],
            "digest_field": digest_field,
            "semantic_digest": document[digest_field],
            "physical_sha256": _physical(document),
        }

    def schedule(self, cycle_index: int, accepted_state_digest: str) -> None:
        plans = copy.deepcopy(self.checkpoint["plan_bindings"])
        plans.append(
            {
                "cycle_index": cycle_index,
                "relative_ref": f"monitor/cycles/{cycle_index:04d}/monitor-plan.json",
                "semantic_digest": hashlib.sha256(
                    f"plan:{cycle_index}".encode()
                ).hexdigest(),
                "physical_sha256": hashlib.sha256(
                    f"plan-bytes:{cycle_index}".encode()
                ).hexdigest(),
                "accepted_state_digest": accepted_state_digest,
            }
        )
        self._replace(plan_bindings=plans)

    def reserve_attempt(self, cycle_index: int) -> None:
        attempts = copy.deepcopy(self.checkpoint["resolution_attempt_bindings"])
        if len(attempts) >= cycle_index:
            return
        attempts.append(
            {
                "cycle_index": cycle_index,
                "relative_ref": f"monitor/cycles/{cycle_index:04d}/attempt.json",
                "semantic_digest": hashlib.sha256(
                    f"attempt:{cycle_index}".encode()
                ).hexdigest(),
                "physical_sha256": hashlib.sha256(
                    f"attempt-bytes:{cycle_index}".encode()
                ).hexdigest(),
            }
        )
        self._replace(resolution_attempt_bindings=attempts)

    def resolve(self, cycle_index: int, *, unknown: bool = False) -> str:
        self.reserve_attempt(cycle_index)
        outcomes = copy.deepcopy(self.checkpoint["outcome_bindings"])
        previous = self.checkpoint["last_outcome_receipt_digest"]
        receipt = self_digest(
            {
                "schema_id": "fake_legal_outcome_receipt",
                "schema_version": "1.0.0",
                "run_id": RUN_ID,
                "cycle_index": cycle_index,
                "previous_outcome_receipt_digest": previous,
                "expectation_outcome": "UNKNOWN" if unknown else "FULFILLED",
                "path_outcome": "UNRESOLVED" if unknown else "SUPPORTED",
                "coverage_loss": unknown,
                "unknown_counted_as_coverage_loss": unknown,
            },
            "outcome_receipt_digest",
        )
        ref = f"monitor/cycles/{cycle_index:04d}/outcome-receipt.json"
        self.documents[ref] = receipt
        outcomes.append(
            {
                "cycle_index": cycle_index,
                "outcome_receipt_ref": ref,
                "outcome_receipt_digest": receipt["outcome_receipt_digest"],
                "outcome_receipt_physical_sha256": _physical(receipt),
            }
        )
        self._replace(
            status="TERMINAL" if cycle_index == 8 else "ACTIVE",
            outcome_bindings=outcomes,
            last_outcome_receipt_digest=receipt["outcome_receipt_digest"],
        )
        return receipt["outcome_receipt_digest"]

    def fail_closed(self) -> None:
        self._replace(
            status="FAILED_CLOSED",
            failure_digest="f" * 64,
            resume_allowed=False,
        )

    def touch(self) -> None:
        self._replace()


class V31ExperimentSupervisorV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.supervisor_store = LocalV31SupervisorStoreV2(self.root)
        self.research_store = FakeResearchStore()
        self.monitor_store = FakeMonitorStore()
        self.now = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)

    def tick(self) -> str:
        self.now += timedelta(seconds=1)
        return self.now.isoformat().replace("+00:00", "Z")

    def bootstrap(self):
        return initialize_v31_experiment_supervisor_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            experiment_contract_digest=CONTRACT_DIGEST,
            active_authority_digest=AUTHORITY_DIGEST,
            created_at=self.tick(),
        )

    def open_permit(self):
        return open_v31_cycle_permit_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            issued_at=self.tick(),
        )

    def reserve_and_commit(self, permit: dict, cycle_index: int):
        reserved = reserve_v31_cycle_commit_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            permit_binding=permit["cycle_permit_binding"],
            commit_material_digest=hashlib.sha256(
                f"commit:{cycle_index}".encode()
            ).hexdigest(),
            reserved_at=self.tick(),
        )
        accepted_digest = self.research_store.commit_cycle(cycle_index)
        self.monitor_store.schedule(cycle_index, accepted_digest)
        committed = record_v31_cycle_commit_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            committed_at=self.tick(),
        )
        return reserved, committed

    def test_missing_and_reserved_outcome_block_but_legal_unknown_opens_next(self) -> None:
        self.bootstrap()
        permit_one = self.open_permit()
        self.reserve_and_commit(permit_one, 1)

        with self.assertRaisesRegex(
            V31ExperimentSupervisorV2WorkflowError,
            "PRIOR_OUTCOME_MISSING",
        ):
            self.open_permit()

        self.monitor_store.reserve_attempt(1)
        with self.assertRaisesRegex(
            V31ExperimentSupervisorV2WorkflowError,
            "RESERVED_ATTEMPT_WITHOUT_OUTCOME",
        ):
            self.open_permit()

        unknown_digest = self.monitor_store.resolve(1, unknown=True)
        permit_two = self.open_permit()
        self.assertEqual(2, permit_two["cycle_index"])
        self.assertEqual(
            unknown_digest,
            permit_two["cycle_permit"]["previous_outcome_receipt_digest"],
        )
        self.assertEqual(
            "CYCLE_PERMIT_OPEN",
            permit_two["supervisor_checkpoint"]["status"],
        )

    def test_failed_monitor_blocks_and_supervisor_failure_is_permanent(self) -> None:
        self.bootstrap()
        permit = self.open_permit()
        self.reserve_and_commit(permit, 1)
        self.monitor_store.fail_closed()

        with self.assertRaisesRegex(
            V31ExperimentSupervisorV2WorkflowError,
            "MONITOR_FAILED_CLOSED",
        ):
            self.open_permit()
        automatic = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", automatic["status"])
        self.assertFalse(automatic["resume_allowed"])

        failed = fail_v31_experiment_supervisor_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            failure_code="MONITOR_FAILED_CLOSED",
            failure_summary="The monitor owner is permanently closed.",
            occurred_at=self.tick(),
        )
        self.assertEqual("FAILED_CLOSED", failed["status"])
        self.assertFalse(failed["resume_allowed"])
        checkpoint = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertFalse(checkpoint["resume_allowed"])
        with self.assertRaisesRegex(
            V31ExperimentSupervisorV2WorkflowError, "NOT_READY_FOR_PERMIT"
        ):
            self.open_permit()

    def test_live_permit_rejects_stale_owner_digest_before_operation(self) -> None:
        self.bootstrap()
        opened = self.open_permit()
        verified = verify_v31_cycle_permit_live_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            permit_binding=opened["cycle_permit_binding"],
            operation="SOURCE_QUALIFICATION",
        )
        self.assertEqual("PERMIT_LIVE", verified["status"])

        self.monitor_store.touch()
        with self.assertRaisesRegex(
            V31ExperimentSupervisorV2WorkflowError, "PERMIT_STALE"
        ):
            verify_v31_cycle_permit_live_v2(
                supervisor_store=self.supervisor_store,
                research_store=self.research_store,
                monitor_store=self.monitor_store,
                run_id=RUN_ID,
                permit_binding=opened["cycle_permit_binding"],
                operation="AGENT_ATTEMPT_RESERVATION",
            )

    def test_monitor_failure_in_commit_window_closes_supervisor(self) -> None:
        self.bootstrap()
        permit = self.open_permit()
        reserve_v31_cycle_commit_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            permit_binding=permit["cycle_permit_binding"],
            commit_material_digest=hashlib.sha256(b"commit-window").hexdigest(),
            reserved_at=self.tick(),
        )
        self.research_store.commit_cycle(1)
        self.monitor_store.fail_closed()

        with self.assertRaisesRegex(
            V31ExperimentSupervisorV2WorkflowError,
            "MONITOR_FAILED_CLOSED",
        ):
            record_v31_cycle_commit_v2(
                supervisor_store=self.supervisor_store,
                research_store=self.research_store,
                monitor_store=self.monitor_store,
                run_id=RUN_ID,
                committed_at=self.tick(),
            )
        checkpoint = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", checkpoint["status"])
        self.assertFalse(checkpoint["resume_allowed"])

    def test_store_is_write_once_and_checkpoint_is_compare_and_swap(self) -> None:
        self.bootstrap()
        opened = self.open_permit()
        permit = opened["cycle_permit"]
        binding = opened["cycle_permit_binding"]
        identical = self.supervisor_store.write_document(
            relative_ref=binding["relative_ref"],
            document=permit,
            digest_field=CYCLE_PERMIT_DIGEST_FIELD,
        )
        self.assertEqual(binding, identical)

        conflicting = self_digest(
            {**permit, "issued_at": self.tick()}, CYCLE_PERMIT_DIGEST_FIELD
        )
        with self.assertRaisesRegex(
            V31SupervisorStoreV2Error, "WRITE_ONCE_CONFLICT"
        ):
            self.supervisor_store.write_document(
                relative_ref=binding["relative_ref"],
                document=conflicting,
                digest_field=CYCLE_PERMIT_DIGEST_FIELD,
            )

        current = self.supervisor_store.load_checkpoint(run_id=RUN_ID)
        with self.assertRaisesRegex(
            V31SupervisorStoreV2Error, "CHECKPOINT_CAS_FAILED"
        ):
            self.supervisor_store.replace_checkpoint(
                run_id=RUN_ID,
                expected_checkpoint_digest="0" * 64,
                checkpoint=current,
            )

    def test_orphan_write_once_permit_is_recovered_without_rewriting(self) -> None:
        checkpoint = self.bootstrap()
        research = self.research_store.load_checkpoint(run_id=RUN_ID)
        monitor = self.monitor_store.load_checkpoint(run_id=RUN_ID)
        orphan = build_cycle_permit_v2(
            checkpoint=checkpoint,
            cycle_index=1,
            research_checkpoint_digest=research["checkpoint_digest"],
            monitor_checkpoint_digest=monitor["checkpoint_digest"],
            previous_outcome_receipt_digest=None,
            issued_at=self.tick(),
        )
        self.supervisor_store.write_document(
            relative_ref=cycle_permit_ref_v2(1),
            document=orphan,
            digest_field=CYCLE_PERMIT_DIGEST_FIELD,
        )

        recovered = self.open_permit()
        self.assertEqual(
            orphan[CYCLE_PERMIT_DIGEST_FIELD],
            recovered["cycle_permit"][CYCLE_PERMIT_DIGEST_FIELD],
        )
        self.assertEqual("CYCLE_PERMIT_OPEN", recovered["status"])

    def test_real_owner_ports_bootstrap_and_open_cycle_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            research = LocalV31ResearchStore(root)
            monitor = LocalV31MonitorStore(root)
            supervisor = LocalV31SupervisorStoreV2(root)
            created = "2026-08-07T01:00:00Z"
            research.initialize_checkpoint(
                run_id=RUN_ID,
                total_cycles=8,
                created_at=created,
            )
            monitor.initialize_checkpoint(
                run_id=RUN_ID,
                experiment_contract_digest=CONTRACT_DIGEST,
                total_cycles=8,
                created_at=created,
            )
            initialize_v31_experiment_supervisor_v2(
                supervisor_store=supervisor,
                research_store=research,
                monitor_store=monitor,
                run_id=RUN_ID,
                experiment_contract_digest=CONTRACT_DIGEST,
                active_authority_digest=AUTHORITY_DIGEST,
                created_at="2026-08-07T01:00:01Z",
            )
            opened = open_v31_cycle_permit_v2(
                supervisor_store=supervisor,
                research_store=research,
                monitor_store=monitor,
                run_id=RUN_ID,
                issued_at="2026-08-07T01:00:02Z",
            )
            self.assertEqual(1, opened["cycle_index"])
            self.assertEqual("CYCLE_PERMIT_OPEN", opened["status"])

    def test_terminal_requires_both_eight_accepted_and_eight_outcomes(self) -> None:
        self.bootstrap()
        permit = self.open_permit()
        for cycle_index in range(1, 9):
            self.reserve_and_commit(permit, cycle_index)
            if cycle_index < 8:
                self.monitor_store.resolve(
                    cycle_index, unknown=(cycle_index == 3)
                )
                permit = self.open_permit()
                self.assertEqual(cycle_index + 1, permit["cycle_index"])
            else:
                with self.assertRaisesRegex(
                    V31ExperimentSupervisorV2WorkflowError,
                    "TERMINAL_EVIDENCE_INCOMPLETE",
                ):
                    complete_v31_experiment_supervisor_v2(
                        supervisor_store=self.supervisor_store,
                        research_store=self.research_store,
                        monitor_store=self.monitor_store,
                        run_id=RUN_ID,
                        completed_at=self.tick(),
                    )
                self.monitor_store.resolve(8)

        terminal = complete_v31_experiment_supervisor_v2(
            supervisor_store=self.supervisor_store,
            research_store=self.research_store,
            monitor_store=self.monitor_store,
            run_id=RUN_ID,
            completed_at=self.tick(),
        )
        self.assertEqual("TERMINAL_COMPLETE", terminal["status"])
        self.assertEqual(8, terminal["completed_research_cycles"])
        self.assertEqual(8, terminal["resolved_outcome_cycles"])
        self.assertIsNone(terminal["current_cycle_index"])


if __name__ == "__main__":
    unittest.main()
