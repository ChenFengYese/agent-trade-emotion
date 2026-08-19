from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest

from tests.test_theory_paper_v2_v32_public_source_collector import (
    BASE,
    RUN_ID,
    BundleTransport,
    RecordingStore,
    SequenceClock,
    authority,
    raw_bundle,
    ts,
)
from tests.test_theory_paper_v2_v32_tick_supervisor import digest
from trade_system.theory_paper_v2.application.v32_cycle_composition import (
    V32CycleCompositionError,
    run_v32_single_boundary_wake,
)
from trade_system.theory_paper_v2.application.v32_cycle_acceptance import (
    DIGEST_FIELD as ANALYSIS_ACCEPTANCE_DIGEST_FIELD,
    SCHEMA_ID as ANALYSIS_ACCEPTANCE_SCHEMA_ID,
)
from trade_system.theory_paper_v2.application.v32_cycle_source_admission import (
    admit_fresh_v32_source_to_cycle,
)
from trade_system.theory_paper_v2.application.v32_durable_source_replay import (
    RECEIPT_DIGEST_FIELD as SOURCE_REPLAY_DIGEST_FIELD,
    compose_and_persist_v32_durable_source_replay_receipt,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_shadow_evaluation import (
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    SHADOW_DECISION_BUNDLE_SCHEMA_ID,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    GOVERNING_AUTHORITY_DIGEST_FIELD,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_market_graph_projection import (
    GRAPH_PROJECTION_DIGEST_FIELD,
    GRAPH_REGISTRY_DIGEST_FIELD,
    build_v32_public_market_graph_projection_v1,
    build_v32_verified_graph_dependency_registry_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    V32RawFirstOkxPublicBundleCollector,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_evidence_verifier import (
    V32InfrastructurePublicEvidenceVerifier,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)


class InjectedCrash(BaseException):
    pass


def _formal_public_chain(root: Path) -> dict:
    qualification_id = "q-v32-cycle-composition"
    source_store = RecordingStore(root / "source")
    run_store = LocalV32CycleSourceAdmissionStore(root / "run")
    collected = V32RawFirstOkxPublicBundleCollector(
        transport=BundleTransport(raw_bundle()),
        clock=SequenceClock(),
        store=source_store,
    ).collect_and_qualify(
        qualification_id=qualification_id,
        run_id=RUN_ID,
        cycle_index=1,
        active_authority=authority(),
    )
    admit_fresh_v32_source_to_cycle(
        source_store=source_store,
        run_store=run_store,
        active_authority=authority(),
        qualification_id=qualification_id,
        run_id=RUN_ID,
        cycle_index=1,
        decision_time=collected.formal_qualification["decision_time"],
        admitted_at=ts(BASE + timedelta(seconds=6, microseconds=500_000)),
    )
    replay = compose_and_persist_v32_durable_source_replay_receipt(
        public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
        source_store=source_store,
        run_store=run_store,
        active_authority=authority(),
        qualification_id=qualification_id,
        run_id=RUN_ID,
        cycle_index=1,
        replayed_at=ts(BASE + timedelta(seconds=7)),
    )["durable_source_replay_receipt"]
    bundle = collected.public_market_analysis_bundle
    projection = build_v32_public_market_graph_projection_v1(bundle)
    registry = build_v32_verified_graph_dependency_registry_v1(
        graph_projection=projection,
        analysis_bundle=bundle,
        decision_time=ts(BASE + timedelta(seconds=6)),
    )
    return {
        "bundle": bundle,
        "projection": projection,
        "registry": registry,
        "source_replay": replay,
    }


def _genesis() -> dict:
    active = authority()
    return build_v32_tick_supervisor_checkpoint(
        run_id=RUN_ID,
        experiment_contract_digest=active["experiment_contract_digest"],
        active_authority_digest=active[GOVERNING_AUTHORITY_DIGEST_FIELD],
        research_checkpoint_digest="c" * 64,
        outcome_checkpoint_digest="d" * 64,
        timeframe_cache_digest="e" * 64,
        created_at="2026-08-07T00:00:00Z",
    )


class AnalysisPort:
    def __init__(
        self,
        chain: dict,
        *,
        completion_after: int = 1,
        failure_after: int | None = None,
        failure_code: str | None = None,
        crash_after_commit: bool = False,
    ) -> None:
        self.chain = chain
        self.completion_after = completion_after
        self.failure_after = failure_after
        self.failure_code = failure_code
        self.crash_after_commit = crash_after_commit
        self.advance_calls = 0
        self.envelope = None
        self.failure = None

    def _seal_completion(self, permit) -> None:
        schedule = build_v32_outcome_schedule_set(
            run_id=RUN_ID,
            decision_id="decision:0001",
            cycle_index=1,
            decision_time=permit["analysis_decision_at"],
            scheduled_at="2026-08-07T00:15:02Z",
            sealed_decision_digest=digest("sealed-1"),
            evaluation_contract_digest="f" * 64,
        )
        completion = {
            "schedule_sets_before": [],
            "new_schedule_set": schedule,
            "accepted_state_digest": digest("accepted-1"),
            "shadow_decision_bundle_digest": None,
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
        shadow_decision = self_digest(
            {
                "schema_id": SHADOW_DECISION_BUNDLE_SCHEMA_ID,
                "run_id": RUN_ID,
                "cycle_index": 1,
                "outcome_values_present": False,
                "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
        )
        shadow_digest = shadow_decision[SHADOW_DECISION_BUNDLE_DIGEST_FIELD]
        completion["shadow_decision_bundle_digest"] = shadow_digest
        shadow_binding = {
            "relative_ref": "v32-dynamic-cycle-v1/cycles/0001/shadow.json",
            "schema_id": SHADOW_DECISION_BUNDLE_SCHEMA_ID,
            "digest_field": SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
            "semantic_digest": shadow_digest,
            "physical_sha256": hashlib.sha256(
                canonical_bytes(shadow_decision) + b"\n"
            ).hexdigest(),
        }
        acceptance = self_digest(
            {
                "schema_id": ANALYSIS_ACCEPTANCE_SCHEMA_ID,
                "run_id": RUN_ID,
                "cycle_index": 1,
                "component_bindings": {
                    "replayable_shadow_decision_bundle": shadow_binding,
                },
                "shadow_decision_bundle_digest": shadow_digest,
            },
            ANALYSIS_ACCEPTANCE_DIGEST_FIELD,
        )
        completion["accepted_state_digest"] = acceptance[
            ANALYSIS_ACCEPTANCE_DIGEST_FIELD
        ]
        self.envelope = {
            "permit_digest": permit[PERMIT_DIGEST_FIELD],
            "analysis_acceptance_digest": completion["accepted_state_digest"],
            "shadow_decision_bundle_digest": shadow_digest,
            "durable_source_replay_receipt_digest": self.chain["source_replay"][
                SOURCE_REPLAY_DIGEST_FIELD
            ],
            "public_market_analysis_bundle_digest": self.chain["bundle"][
                ANALYSIS_BUNDLE_DIGEST_FIELD
            ],
            "public_market_graph_projection_digest": self.chain["projection"][
                GRAPH_PROJECTION_DIGEST_FIELD
            ],
            "graph_delta_digest": self.chain["projection"]["graph_delta_digest"],
            "graph_dependency_registry_digest": self.chain["registry"][
                GRAPH_REGISTRY_DIGEST_FIELD
            ],
            "public_market_analysis_bundle": self.chain["bundle"],
            "public_market_graph_projection": self.chain["projection"],
            "previous_public_market_graph_projection": None,
            "graph_dependency_registry": self.chain["registry"],
            "durable_source_replay_receipt": self.chain["source_replay"],
            "analysis_acceptance": acceptance,
            "shadow_decision_bundle": shadow_decision,
            "completion": completion,
        }

    def advance_analysis(self, *, permit, **_kwargs):
        self.advance_calls += 1
        if self.failure_after is not None and self.advance_calls >= self.failure_after:
            self.failure = {
                "permit_digest": permit[PERMIT_DIGEST_FIELD],
                "failure_summary": "analysis lane sealed one terminal failure",
                "failure_evidence_digest": digest("analysis-lane-failure"),
                "occurred_at": "2026-08-07T00:15:02Z",
            }
            if self.failure_code is not None:
                self.failure["failure_code"] = self.failure_code
            status = "FAILURE_SEALED"
        elif self.advance_calls >= self.completion_after:
            self._seal_completion(permit)
            status = "COMPLETION_SEALED"
        else:
            status = "PENDING"
        transition_digest = canonical_digest(
            {
                "permit_digest": permit[PERMIT_DIGEST_FIELD],
                "advance_call": self.advance_calls,
                "advance_status": status,
            }
        )
        if self.crash_after_commit:
            self.crash_after_commit = False
            raise InjectedCrash("after durable substore commit")
        return {
            "advance_status": status,
            "durable_transition_digest": transition_digest,
        }

    def load_durable_analysis_completion(self, *, permit):
        return deepcopy(self.envelope)

    def verify_durable_analysis_completion(self, *, permit, completion_envelope):
        return completion_envelope

    def load_durable_analysis_failure(self, *, permit):
        return deepcopy(self.failure)

    def verify_durable_analysis_failure(self, *, permit, failure_envelope):
        return failure_envelope


class OutcomePort:
    def __init__(self) -> None:
        self.advance_calls = 0
        self.failure = None

    def advance_outcome(self, *, permit, **_kwargs):
        self.advance_calls += 1
        self.failure = {
            "permit_digest": permit[PERMIT_DIGEST_FIELD],
            "failure_summary": "outcome lane sealed one terminal failure",
            "failure_evidence_digest": digest("outcome-lane-failure"),
            "occurred_at": permit["issued_at"],
        }
        return {
            "advance_status": "FAILURE_SEALED",
            "durable_transition_digest": canonical_digest(
                {
                    "permit_digest": permit[PERMIT_DIGEST_FIELD],
                    "advance_call": self.advance_calls,
                    "advance_status": "FAILURE_SEALED",
                }
            ),
        }

    def load_durable_outcome_completion(self, *, permit):
        return None

    def verify_durable_outcome_completion(self, *, permit, completion_envelope):
        return completion_envelope

    def load_durable_outcome_failure(self, *, permit):
        return deepcopy(self.failure)

    def verify_durable_outcome_failure(self, *, permit, failure_envelope):
        return failure_envelope


class V32CycleCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shared_temp = tempfile.TemporaryDirectory()
        cls.chain = _formal_public_chain(Path(cls.shared_temp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.shared_temp.cleanup()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = LocalV32TickSupervisorStore(Path(self.temp.name))
        self.genesis = _genesis()
        self.store.initialize_checkpoint(checkpoint=self.genesis)
        self.request = {
            "lane": "ANALYSIS",
            "analysis_decision_at": "2026-08-07T00:15:00Z",
            "issued_at": "2026-08-07T00:15:01Z",
        }

    def test_open_advance_and_complete_are_three_distinct_wakes(self) -> None:
        port = AnalysisPort(self.chain)
        opened = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("SUPERVISOR_PERMIT_OPENED", opened["boundary_kind"])
        self.assertEqual("PENDING", opened["runtime_status"])
        self.assertEqual(0, port.advance_calls)
        self.assertEqual(
            "ANALYSIS_TICK_OPEN",
            self.store.load_checkpoint(run_id=RUN_ID)["status"],
        )

        advanced = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("ANALYSIS_SUBSTAGE_ADVANCED", advanced["boundary_kind"])
        self.assertEqual("COMPLETION_SEALED", advanced["lane_advance_status"])
        self.assertEqual("PENDING", advanced["runtime_status"])
        self.assertEqual(1, port.advance_calls)
        self.assertEqual(
            "ANALYSIS_TICK_OPEN",
            self.store.load_checkpoint(run_id=RUN_ID)["status"],
        )

        completed = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("SUPERVISOR_ANALYSIS_COMPLETED", completed["boundary_kind"])
        self.assertEqual("COMPLETED", completed["runtime_status"])
        self.assertTrue(completed["supervisor_boundary_completed_this_wake"])
        self.assertEqual(1, completed["boundaries_completed_this_wake"])
        self.assertFalse(completed["analysis_and_outcome_both_advanced"])
        self.assertEqual(1, port.advance_calls)
        self.assertEqual(
            1,
            self.store.load_checkpoint(run_id=RUN_ID)["accepted_analysis_cycles"],
        )

    def test_multiple_pending_substages_resume_without_failure(self) -> None:
        port = AnalysisPort(self.chain, completion_after=3)
        results = [
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request],
                schedule_sets=[],
                analysis_port=port,
            )
            for _ in range(4)
        ]
        self.assertEqual("SUPERVISOR_PERMIT_OPENED", results[0]["boundary_kind"])
        self.assertEqual(
            ["PENDING", "PENDING", "COMPLETION_SEALED"],
            [row["lane_advance_status"] for row in results[1:]],
        )
        self.assertTrue(all(row["runtime_status"] == "PENDING" for row in results))
        self.assertEqual(3, port.advance_calls)
        self.assertEqual(
            "ANALYSIS_TICK_OPEN",
            self.store.load_checkpoint(run_id=RUN_ID)["status"],
        )
        completed = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("COMPLETED", completed["runtime_status"])
        self.assertEqual(3, port.advance_calls)

    def test_sealed_failure_is_applied_on_following_wake(self) -> None:
        port = AnalysisPort(self.chain, failure_after=1)
        opened = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("PENDING", opened["runtime_status"])
        advanced = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("FAILURE_SEALED", advanced["lane_advance_status"])
        self.assertEqual(
            "ANALYSIS_TICK_OPEN",
            self.store.load_checkpoint(run_id=RUN_ID)["status"],
        )
        failed = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual("FAILED_CLOSED", failed["supervisor_status"])
        self.assertEqual(1, port.advance_calls)

    def test_source_stale_after_agent_keeps_its_typed_supervisor_owner(self) -> None:
        port = AnalysisPort(
            self.chain,
            failure_after=1,
            failure_code="SOURCE_STALE_AFTER_AGENT",
        )
        run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        failed = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual("SOURCE_LANE", checkpoint["failure_lane"])
        failure = load_json_strict(
            Path(self.temp.name)
            / "v32-tick-supervisor-v1"
            / "failures"
            / f"{checkpoint['failure_digest']}.json"
        )
        self.assertEqual("SOURCE_STALE_AFTER_AGENT", failure["failure_code"])

    def test_same_wake_cannot_request_two_boundaries(self) -> None:
        with self.assertRaisesRegex(
            V32CycleCompositionError, "EXACTLY_ONE_LANE_REQUIRED"
        ):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request, self.request],
                schedule_sets=[],
                analysis_port=AnalysisPort(self.chain),
            )
        self.assertEqual(0, self.store.load_checkpoint(run_id=RUN_ID)["revision"])

    def test_permit_tamper_fails_supervisor_closed(self) -> None:
        port = AnalysisPort(self.chain)
        original = port.verify_durable_analysis_completion

        def tamper(**kwargs):
            envelope = deepcopy(original(**kwargs))
            envelope["permit_digest"] = "f" * 64
            return envelope

        port.verify_durable_analysis_completion = tamper
        for _ in range(2):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request],
                schedule_sets=[],
                analysis_port=port,
            )
        with self.assertRaisesRegex(
            V32CycleCompositionError, "COMPLETION_PERMIT_MISMATCH"
        ):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request],
                schedule_sets=[],
                analysis_port=port,
            )
        self.assertEqual(
            "FAILED_CLOSED", self.store.load_checkpoint(run_id=RUN_ID)["status"]
        )

    def test_shadow_digest_must_come_from_the_bound_acceptance_component(self) -> None:
        port = AnalysisPort(self.chain)
        original = port.verify_durable_analysis_completion

        def tamper(**kwargs):
            envelope = deepcopy(original(**kwargs))
            envelope["shadow_decision_bundle_digest"] = "f" * 64
            return envelope

        port.verify_durable_analysis_completion = tamper
        for _ in range(2):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request],
                schedule_sets=[],
                analysis_port=port,
            )
        with self.assertRaisesRegex(
            V32CycleCompositionError, "ANALYSIS_BINDING_INVALID"
        ):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request],
                schedule_sets=[],
                analysis_port=port,
            )
        self.assertEqual(
            "FAILED_CLOSED", self.store.load_checkpoint(run_id=RUN_ID)["status"]
        )

    def test_substore_commit_survives_crash_before_supervisor_completion(self) -> None:
        port = AnalysisPort(self.chain, crash_after_commit=True)
        opened = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual("SUPERVISOR_PERMIT_OPENED", opened["boundary_kind"])
        with self.assertRaises(InjectedCrash):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request],
                schedule_sets=[],
                analysis_port=port,
            )
        opened = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual("ANALYSIS_TICK_OPEN", opened["status"])
        recovered = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[self.request],
            schedule_sets=[],
            analysis_port=port,
        )
        self.assertEqual(
            "DURABLE_SUBSTORE_COMPLETION_RECOVERY", recovered["recovery_mode"]
        )
        self.assertEqual(1, port.advance_calls)
        self.assertEqual(
            1,
            self.store.load_checkpoint(run_id=RUN_ID)["accepted_analysis_cycles"],
        )

    def test_open_analysis_lane_rejects_outcome_lane_in_same_boundary(self) -> None:
        permit = build_v32_analysis_tick_permit(
            checkpoint=self.genesis,
            schedule_sets=[],
            analysis_decision_at=self.request["analysis_decision_at"],
            issued_at=self.request["issued_at"],
            research_checkpoint_digest=self.genesis["current_research_checkpoint_digest"],
            outcome_checkpoint_digest=self.genesis["current_outcome_checkpoint_digest"],
            timeframe_cache_digest=self.genesis["current_timeframe_cache_digest"],
            prior_dynamic_state_digest=self.genesis["current_dynamic_state_digest"],
        )
        self.store.open_permit(
            permit=permit,
            schedule_sets=[],
            expected_checkpoint_digest=self.genesis[CHECKPOINT_DIGEST_FIELD],
            opened_at=permit["issued_at"],
        )
        with self.assertRaisesRegex(
            V32CycleCompositionError, "DUAL_LANE_OR_WAKE_MISMATCH"
        ):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[
                    {
                        "lane": "OUTCOME",
                        "planned_tick_at": "2026-08-07T01:00:00Z",
                        "requested_at": "2026-08-07T01:00:01Z",
                    }
                ],
                schedule_sets=[],
                outcome_port=object(),
            )
        self.assertEqual(
            "ANALYSIS_TICK_OPEN", self.store.load_checkpoint(run_id=RUN_ID)["status"]
        )

    def test_outcome_advance_and_failure_tail_are_separate_wakes(self) -> None:
        analysis_port = AnalysisPort(self.chain)
        for _ in range(3):
            run_v32_single_boundary_wake(
                supervisor_store=self.store,
                run_id=RUN_ID,
                lane_requests=[self.request],
                schedule_sets=[],
                analysis_port=analysis_port,
            )
        schedule = analysis_port.envelope["completion"]["new_schedule_set"]
        due_at = schedule["schedules"][0]["outcome_not_before"]
        outcome_request = {
            "lane": "OUTCOME",
            "planned_tick_at": due_at,
            "requested_at": due_at,
        }
        outcome_port = OutcomePort()

        opened = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[outcome_request],
            schedule_sets=[schedule],
            outcome_port=outcome_port,
        )
        self.assertEqual("SUPERVISOR_PERMIT_OPENED", opened["boundary_kind"])
        self.assertEqual(0, outcome_port.advance_calls)
        advanced = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[outcome_request],
            schedule_sets=[schedule],
            outcome_port=outcome_port,
        )
        self.assertEqual("OUTCOME_SUBSTAGE_ADVANCED", advanced["boundary_kind"])
        self.assertEqual("FAILURE_SEALED", advanced["lane_advance_status"])
        self.assertEqual(1, outcome_port.advance_calls)
        failed = run_v32_single_boundary_wake(
            supervisor_store=self.store,
            run_id=RUN_ID,
            lane_requests=[outcome_request],
            schedule_sets=[schedule],
            outcome_port=outcome_port,
        )
        self.assertEqual("SUPERVISOR_OUTCOME_FAILED_CLOSED", failed["boundary_kind"])
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual(1, outcome_port.advance_calls)


class V32ActivePermitIntegrityTests(unittest.TestCase):
    def test_corrupt_active_permit_is_durably_failed_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = LocalV32TickSupervisorStore(Path(temporary))
            store.initialize_checkpoint(checkpoint=_genesis())
            request = {
                "lane": "ANALYSIS",
                "analysis_decision_at": "2026-08-07T00:15:00Z",
                "issued_at": "2026-08-07T00:15:01Z",
            }
            run_v32_single_boundary_wake(
                supervisor_store=store,
                run_id=RUN_ID,
                lane_requests=[request],
                schedule_sets=[],
                analysis_port=object(),
            )
            load_permit = store.load_permit

            def tampered_permit(**kwargs):
                permit = load_permit(**kwargs)
                permit["active_authority_digest"] = "f" * 64
                return permit

            store.load_permit = tampered_permit
            with self.assertRaisesRegex(
                V32CycleCompositionError,
                "ACTIVE_PERMIT_INVALID_FAILED_CLOSED",
            ):
                run_v32_single_boundary_wake(
                    supervisor_store=store,
                    run_id=RUN_ID,
                    lane_requests=[request],
                    schedule_sets=[],
                    analysis_port=object(),
                )
            self.assertEqual(
                "FAILED_CLOSED", store.load_checkpoint(run_id=RUN_ID)["status"]
            )


if __name__ == "__main__":
    unittest.main()
