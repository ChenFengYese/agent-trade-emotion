from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trade_system.theory_paper_v2.application.continuous_cycle import (
    ContinuousResearchCycleCoordinator,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.window_reliability import (
    WindowReliabilityError,
    build_agent_input_plan,
    build_controller_reconciliation,
    classify_reliability_failure,
)
from trade_system.theory_paper_v2.infrastructure.continuous_fixture import (
    CanonicalContinuousArtifactRepository,
    ContinuousFixtureInfrastructureError,
    LocalRunLease,
    SyntheticComparator,
    SyntheticMarketCollector,
    SyntheticStrategyAgent,
)
from trade_system.theory_paper_v2.infrastructure.research_cycle_store import (
    ResearchCycleStore,
)
from trade_system.theory_paper_v2.presentation.continuous_fixture_composition import (
    run_continuous_fixture,
)


def _replace_delivery_payload(delivery: dict, mutate) -> dict:
    changed = dict(delivery)
    payload = dict(changed["payload"])
    mutate(payload)
    changed["payload"] = payload
    changed["payload_digest"] = canonical_digest(payload)
    changed["payload_canonical_bytes"] = len(canonical_bytes(payload))
    return changed


class WindowReliabilityIntegrationTests(unittest.TestCase):
    def test_new_process_resumes_from_digest_bound_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            first = run_continuous_fixture(
                runtime_root=runtime_root,
                run_id="window-resume",
                through_cycle=2,
            )
            self.assertEqual("PAUSED_AT_DURABLE_CYCLE_BOUNDARY", first["status"])
            self.assertEqual(2, first["completed_cycles"])
            self.assertFalse(first["chat_history_is_authority"])
            run_root = runtime_root / "window-resume"
            capsule = load_json_strict(run_root / first["resume_capsule_ref"])
            verify_self_digest(capsule, "resume_capsule_digest")
            self.assertEqual(3, capsule["next_cycle_index"])
            self.assertFalse(capsule["chat_history_is_authority"])
            self.assertLess(len(canonical_bytes(capsule)), 12_000)
            checkpoint_at_boundary = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual(
                checkpoint_at_boundary["checkpoint_digest"],
                capsule["checkpoint_ref"]["semantic_digest"],
            )

            second = run_continuous_fixture(
                runtime_root=runtime_root,
                run_id="window-resume",
                through_cycle=4,
            )
            self.assertEqual("COMPLETED_LOCAL_SYNTHETIC_FIXTURE", second["status"])
            self.assertEqual(4, second["completed_cycles"])
            self.assertEqual(4, len(second["cycle_summaries"]))
            self.assertTrue(second["cross_window_resume_verified"])
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            verify_self_digest(checkpoint, "checkpoint_digest")
            self.assertEqual(5, checkpoint["next_cycle_index"])
            for cycle_index in (3, 4):
                events = ResearchCycleStore(
                    run_root,
                    run_id="window-resume",
                    cycle_index=cycle_index,
                ).read_events()
                self.assertEqual("RESUME_CAPSULE_SEALED", events[0]["event_type"])
                self.assertLess(
                    [row["event_type"] for row in events].index(
                        "PREACCEPT_VALIDATION_SEALED"
                    ),
                    [row["event_type"] for row in events].index("STATE_ACCEPTED"),
                )

    def test_input_over_budget_stops_before_agent_and_accept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            with mock.patch.object(
                SyntheticStrategyAgent,
                "propose",
                autospec=True,
            ) as propose:
                with self.assertRaisesRegex(
                    WindowReliabilityError, "AGENT_INPUT_BUDGET_EXCEEDED"
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="budget-failure",
                        through_cycle=1,
                        max_agent_input_bytes=128,
                    )
                propose.assert_not_called()
            run_root = runtime_root / "budget-failure"
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            verify_self_digest(checkpoint, "checkpoint_digest")
            self.assertEqual(
                "PRE_ACCEPT_RECOVERABLE_FAILURE",
                checkpoint["status"],
            )
            failure = load_json_strict(run_root / checkpoint["last_failure_ref"])
            verify_self_digest(failure, "reliability_failure_digest")
            self.assertEqual(
                "INPUT_BUDGET_OR_REQUIRED_SECTION_FAILURE",
                failure["failure_type"],
            )
            self.assertTrue(failure["resume_allowed"])
            recovery_capsule = load_json_strict(
                run_root
                / (
                    "resume/recovery-cycle-0001-"
                    f"{checkpoint['checkpoint_digest']}.json"
                )
            )
            self.assertEqual(
                checkpoint["checkpoint_digest"],
                recovery_capsule["checkpoint_ref"]["semantic_digest"],
            )
            self.assertFalse((run_root / "states/state-0001.json").exists())
            events = ResearchCycleStore(
                run_root, run_id="budget-failure", cycle_index=1
            ).read_events()
            self.assertNotIn("STATE_ACCEPTED", [row["event_type"] for row in events])
            resumed = run_continuous_fixture(
                runtime_root=runtime_root,
                run_id="budget-failure",
                through_cycle=1,
            )
            self.assertEqual("PAUSED_AT_DURABLE_CYCLE_BOUNDARY", resumed["status"])
            self.assertTrue((run_root / "states/state-0001.json").is_file())

    def test_truncated_delivery_is_not_a_proposal_or_accepted_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            original = SyntheticStrategyAgent.propose

            def truncated(agent, *, context):
                delivery = dict(original(agent, context=context))
                delivery["delivery_status"] = "TRUNCATED"
                delivery["finish_reason"] = "LENGTH"
                delivery["truncated"] = True
                delivery["complete_json_object"] = False
                return delivery

            with mock.patch.object(
                SyntheticStrategyAgent, "propose", new=truncated
            ):
                with self.assertRaisesRegex(
                    WindowReliabilityError,
                    "AGENT_DELIVERY_INCOMPLETE_OR_MISMATCHED",
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="truncated-delivery",
                        through_cycle=1,
                    )
            run_root = runtime_root / "truncated-delivery"
            self.assertFalse((run_root / "states/state-0001.json").exists())
            events = ResearchCycleStore(
                run_root, run_id="truncated-delivery", cycle_index=1
            ).read_events()
            event_types = [row["event_type"] for row in events]
            self.assertIn("AGENT_INPUT_PLAN_SEALED", event_types)
            self.assertNotIn("AGENT_PROPOSAL_SEALED", event_types)
            failure = classify_reliability_failure(
                run_id="truncated-delivery",
                cycle_index=1,
                phase="PROPOSAL_DELIVERY",
                reason_code="AGENT_DELIVERY_INCOMPLETE_OR_MISMATCHED",
                accepted_state_exists=False,
            )
            self.assertEqual("AGENT_DELIVERY_INCOMPLETE", failure["failure_type"])
            self.assertTrue(failure["resume_allowed"])
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual("PRE_ACCEPT_RECOVERABLE_FAILURE", checkpoint["status"])
            resumed = run_continuous_fixture(
                runtime_root=runtime_root,
                run_id="truncated-delivery",
                through_cycle=1,
            )
            self.assertEqual("PAUSED_AT_DURABLE_CYCLE_BOUNDARY", resumed["status"])
            self.assertTrue((run_root / "states/state-0001.json").is_file())

    def test_cycle17_style_stale_lot_prose_fails_before_accept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            original_persist = SyntheticStrategyAgent._persist_transport_delivery

            def persist_stale_lot(
                agent,
                *,
                kind,
                run_id,
                cycle_index,
                input_digest,
                delivery,
            ):
                def mutate(payload):
                    payload["candidate_proposals"][0]["path_outcomes"][0][
                        "cost_risk_tradeoff"
                    ] = "mark notional 542.124084 and open risk 63.071886 are reused"

                changed = (
                    _replace_delivery_payload(dict(delivery), mutate)
                    if kind == "proposal"
                    else dict(delivery)
                )
                return original_persist(
                    agent,
                    kind=kind,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    input_digest=input_digest,
                    delivery=changed,
                )

            with mock.patch.object(
                SyntheticStrategyAgent,
                "_persist_transport_delivery",
                new=persist_stale_lot,
            ):
                with self.assertRaisesRegex(
                    WindowReliabilityError,
                    "CURRENT_CYCLE_UNSTRUCTURED_POSITION_TRUTH_FORBIDDEN",
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="stale-lot-prose",
                        through_cycle=1,
                    )
            run_root = runtime_root / "stale-lot-prose"
            self.assertFalse((run_root / "states/state-0001.json").exists())
            events = ResearchCycleStore(
                run_root, run_id="stale-lot-prose", cycle_index=1
            ).read_events()
            event_types = [row["event_type"] for row in events]
            self.assertIn("DECISION_SEALED", event_types)
            self.assertNotIn("PREACCEPT_VALIDATION_SEALED", event_types)
            self.assertNotIn("STATE_ACCEPTED", event_types)
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual("PRE_ACCEPT_FAILED_CLOSED", checkpoint["status"])
            failure = load_json_strict(run_root / checkpoint["last_failure_ref"])
            self.assertFalse(failure["resume_allowed"])
            with mock.patch.object(
                SyntheticStrategyAgent, "propose", autospec=True
            ) as propose_again:
                with self.assertRaisesRegex(
                    ValueError, "FIXTURE_FAILURE_CLOSED_NO_RESUME"
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="stale-lot-prose",
                        through_cycle=1,
                    )
            propose_again.assert_not_called()

    def test_stale_position_number_in_public_inference_fails_before_accept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            original_persist = SyntheticStrategyAgent._persist_transport_delivery

            def persist_stale_public_inference(
                agent,
                *,
                kind,
                run_id,
                cycle_index,
                input_digest,
                delivery,
            ):
                def mutate(payload):
                    payload["public_inference_claims"][0]["statement"] = (
                        "mark notional 542.124084 is copied from an older cycle"
                    )

                changed = (
                    _replace_delivery_payload(dict(delivery), mutate)
                    if kind == "proposal"
                    else dict(delivery)
                )
                return original_persist(
                    agent,
                    kind=kind,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    input_digest=input_digest,
                    delivery=changed,
                )

            with mock.patch.object(
                SyntheticStrategyAgent,
                "_persist_transport_delivery",
                new=persist_stale_public_inference,
            ):
                with self.assertRaisesRegex(
                    WindowReliabilityError,
                    "CURRENT_CYCLE_UNSTRUCTURED_POSITION_TRUTH_FORBIDDEN",
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="stale-public-inference",
                        through_cycle=1,
                    )
            checkpoint = load_json_strict(
                runtime_root / "stale-public-inference/checkpoint.json"
            )
            self.assertEqual("PRE_ACCEPT_FAILED_CLOSED", checkpoint["status"])

    def test_stale_prior_cycle_label_fails_before_accept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            original_persist = SyntheticStrategyAgent._persist_transport_delivery

            def persist_stale_label(
                agent,
                *,
                kind,
                run_id,
                cycle_index,
                input_digest,
                delivery,
            ):
                def mutate(payload):
                    payload["dynamic_update_from_cycle_index"] = 1
                    payload["dynamic_update_summary"] = (
                        "Cycle 1 is incorrectly treated as prior during genesis"
                    )

                changed = (
                    _replace_delivery_payload(dict(delivery), mutate)
                    if kind == "proposal"
                    else dict(delivery)
                )
                return original_persist(
                    agent,
                    kind=kind,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    input_digest=input_digest,
                    delivery=changed,
                )

            with mock.patch.object(
                SyntheticStrategyAgent,
                "_persist_transport_delivery",
                new=persist_stale_label,
            ):
                with self.assertRaisesRegex(
                    WindowReliabilityError, "CURRENT_CYCLE_PRIOR_LABEL_INVALID"
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="stale-cycle-label",
                        through_cycle=1,
                    )
            self.assertFalse(
                (
                    runtime_root
                    / "stale-cycle-label/states/state-0001.json"
                ).exists()
            )
            checkpoint = load_json_strict(
                runtime_root / "stale-cycle-label/checkpoint.json"
            )
            self.assertEqual("PRE_ACCEPT_FAILED_CLOSED", checkpoint["status"])

    def test_context_binds_bounded_view_and_full_history_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(
                runtime_root=runtime_root,
                run_id="bounded-context",
                through_cycle=2,
            )
            run_root = runtime_root / "bounded-context"
            receipt = load_json_strict(
                run_root / "evidence-receipts/cycle-0002.json"
            )
            context = load_json_strict(
                run_root / receipt["artifact_refs"]["agent_context_digest"]
            )
            verify_self_digest(context, "agent_context_digest")
            self.assertNotIn("previous_hypothesis_registry", context)
            self.assertNotIn("previous_expectation_ledger", context)
            self.assertIn("previous_research_state_view", context)
            refs = context["previous_research_state_refs"]
            self.assertEqual(
                {
                    "accepted_state",
                    "belief_state",
                    "expectation_ledger",
                    "hypothesis_registry",
                },
                set(refs),
            )
            view = context["previous_research_state_view"]
            verify_self_digest(view, "prior_state_view_digest")
            self.assertEqual(
                "BOUNDED_VIEW_WITH_CONTENT_ADDRESSED_FULL_HISTORY",
                view["status"],
            )

    def test_missing_required_agent_input_section_fails_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(
                runtime_root=runtime_root,
                run_id="missing-input-section",
                through_cycle=1,
            )
            run_root = runtime_root / "missing-input-section"
            receipt = load_json_strict(
                run_root / "evidence-receipts/cycle-0001.json"
            )
            context = dict(
                load_json_strict(
                    run_root / receipt["artifact_refs"]["agent_context_digest"]
                )
            )
            context.pop("agent_context_digest")
            context.pop("risk_policy")
            incomplete = self_digest(context, "agent_context_digest")
            with self.assertRaisesRegex(
                WindowReliabilityError,
                "AGENT_INPUT_REQUIRED_SECTION_MISSING",
            ):
                build_agent_input_plan(
                    agent_context=incomplete,
                    max_input_bytes=196_608,
                    max_output_bytes=196_608,
                    model_invocation_expected=False,
                )

    def test_deliberation_retry_reuses_sealed_collection_and_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            original = SyntheticStrategyAgent.deliberate

            def truncated(agent, *, evaluation_set):
                delivery = dict(original(agent, evaluation_set=evaluation_set))
                delivery["delivery_status"] = "TRUNCATED"
                delivery["finish_reason"] = "LENGTH"
                delivery["truncated"] = True
                delivery["complete_json_object"] = False
                return delivery

            with mock.patch.object(
                SyntheticStrategyAgent, "deliberate", new=truncated
            ):
                with self.assertRaisesRegex(
                    WindowReliabilityError,
                    "AGENT_DELIVERY_INCOMPLETE_OR_MISMATCHED",
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="deliberation-retry",
                        through_cycle=1,
                    )
            run_root = runtime_root / "deliberation-retry"
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual("PRE_ACCEPT_RECOVERABLE_FAILURE", checkpoint["status"])
            with (
                mock.patch.object(
                    SyntheticStrategyAgent, "propose", autospec=True
                ) as propose_again,
                mock.patch.object(
                    SyntheticMarketCollector, "collect", autospec=True
                ) as collect_again,
            ):
                resumed = run_continuous_fixture(
                    runtime_root=runtime_root,
                    run_id="deliberation-retry",
                    through_cycle=1,
                )
            propose_again.assert_not_called()
            collect_again.assert_not_called()
            self.assertEqual("PAUSED_AT_DURABLE_CYCLE_BOUNDARY", resumed["status"])

    def test_controller_crash_after_agent_return_recovers_durable_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            with mock.patch(
                "trade_system.theory_paper_v2.application.continuous_fixture."
                "make_agent_invocation_receipt",
                side_effect=SystemExit("injected controller crash"),
            ):
                with self.assertRaisesRegex(SystemExit, "injected controller crash"):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="durable-transport-recovery",
                        through_cycle=1,
                    )
            run_root = runtime_root / "durable-transport-recovery"
            transport_records = list(
                (run_root / "transport/cycle-0001").glob("proposal-*.json")
            )
            self.assertEqual(1, len(transport_records))
            record = load_json_strict(transport_records[0])
            verify_self_digest(record, "transport_delivery_record_digest")
            event_types = [
                row["event_type"]
                for row in ResearchCycleStore(
                    run_root,
                    run_id="durable-transport-recovery",
                    cycle_index=1,
                ).read_events()
            ]
            self.assertIn("AGENT_INPUT_PLAN_SEALED", event_types)
            self.assertNotIn("AGENT_PROPOSAL_SEALED", event_types)

            with (
                mock.patch(
                    "trade_system.theory_paper_v2.infrastructure."
                    "continuous_fixture._public_inference_claims",
                    side_effect=AssertionError("proposal generation repeated"),
                ) as proposal_generation_again,
                mock.patch.object(
                    SyntheticMarketCollector, "collect", autospec=True
                ) as collect_again,
            ):
                resumed = run_continuous_fixture(
                    runtime_root=runtime_root,
                    run_id="durable-transport-recovery",
                    through_cycle=1,
                )
            proposal_generation_again.assert_not_called()
            collect_again.assert_not_called()
            self.assertEqual("PAUSED_AT_DURABLE_CYCLE_BOUNDARY", resumed["status"])

    def test_transport_binding_mismatch_fails_before_proposal_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            original_persist = SyntheticStrategyAgent._persist_transport_delivery

            def return_wrong_transport_binding(
                agent,
                *,
                kind,
                run_id,
                cycle_index,
                input_digest,
                delivery,
            ):
                persisted = dict(
                    original_persist(
                        agent,
                        kind=kind,
                        run_id=run_id,
                        cycle_index=cycle_index,
                        input_digest=input_digest,
                        delivery=delivery,
                    )
                )
                if kind == "proposal":
                    persisted["transport_record_sha256"] = "0" * 64
                return persisted

            with mock.patch.object(
                SyntheticStrategyAgent,
                "_persist_transport_delivery",
                new=return_wrong_transport_binding,
            ):
                with self.assertRaisesRegex(
                    WindowReliabilityError,
                    "AGENT_DELIVERY_TRANSPORT_RECORD_MISMATCH",
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="transport-binding-mismatch",
                        through_cycle=1,
                    )
            run_root = runtime_root / "transport-binding-mismatch"
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual("PRE_ACCEPT_RECOVERABLE_FAILURE", checkpoint["status"])
            self.assertFalse((run_root / "states/state-0001.json").exists())
            event_types = [
                row["event_type"]
                for row in ResearchCycleStore(
                    run_root,
                    run_id="transport-binding-mismatch",
                    cycle_index=1,
                ).read_events()
            ]
            self.assertIn("AGENT_INPUT_PLAN_SEALED", event_types)
            self.assertNotIn("AGENT_PROPOSAL_ATTEMPT_SEALED", event_types)
            self.assertNotIn("AGENT_PROPOSAL_SEALED", event_types)

            with mock.patch(
                "trade_system.theory_paper_v2.infrastructure."
                "continuous_fixture._public_inference_claims",
                side_effect=AssertionError("proposal generation repeated"),
            ) as proposal_generation_again:
                resumed = run_continuous_fixture(
                    runtime_root=runtime_root,
                    run_id="transport-binding-mismatch",
                    through_cycle=1,
                )
            proposal_generation_again.assert_not_called()
            self.assertEqual("PAUSED_AT_DURABLE_CYCLE_BOUNDARY", resumed["status"])

    def test_partial_proposal_commit_is_failure_closed_before_accept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            original_write = CanonicalContinuousArtifactRepository.write_document

            def fail_proposal_write(
                repository, *, relative_ref, document, digest_field
            ):
                if relative_ref.endswith("AGENT_PROPOSAL_SEALED.json"):
                    raise OSError("injected proposal artifact write failure")
                return original_write(
                    repository,
                    relative_ref=relative_ref,
                    document=document,
                    digest_field=digest_field,
                )

            with mock.patch.object(
                CanonicalContinuousArtifactRepository,
                "write_document",
                new=fail_proposal_write,
            ):
                with self.assertRaisesRegex(
                    OSError, "injected proposal artifact write failure"
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="partial-proposal",
                        through_cycle=1,
                    )
            run_root = runtime_root / "partial-proposal"
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual("PRE_ACCEPT_FAILED_CLOSED", checkpoint["status"])
            self.assertFalse((run_root / "states/state-0001.json").exists())
            event_types = [
                row["event_type"]
                for row in ResearchCycleStore(
                    run_root,
                    run_id="partial-proposal",
                    cycle_index=1,
                ).read_events()
            ]
            self.assertIn("AGENT_PROPOSAL_ATTEMPT_SEALED", event_types)
            self.assertNotIn("AGENT_PROPOSAL_SEALED", event_types)

    def test_post_accept_tail_resumes_without_collector_or_agent_reentry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            with mock.patch.object(
                SyntheticComparator,
                "compare",
                autospec=True,
                side_effect=RuntimeError("injected comparator interruption"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "injected comparator interruption"
                ):
                    run_continuous_fixture(
                        runtime_root=runtime_root,
                        run_id="post-accept-tail",
                        through_cycle=1,
                    )
            run_root = runtime_root / "post-accept-tail"
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual(
                "POST_ACCEPT_RECOVERABLE_FAILURE", checkpoint["status"]
            )
            self.assertTrue((run_root / "states/state-0001.json").is_file())
            failure = load_json_strict(run_root / checkpoint["last_failure_ref"])
            self.assertEqual(
                "POST_ACCEPT_DETERMINISTIC_TAIL_FAILURE",
                failure["failure_type"],
            )
            self.assertTrue(failure["resume_allowed"])
            with (
                mock.patch.object(
                    SyntheticStrategyAgent, "propose", autospec=True
                ) as propose_again,
                mock.patch.object(
                    SyntheticStrategyAgent, "deliberate", autospec=True
                ) as deliberate_again,
                mock.patch.object(
                    SyntheticMarketCollector, "collect", autospec=True
                ) as collect_again,
            ):
                resumed = run_continuous_fixture(
                    runtime_root=runtime_root,
                    run_id="post-accept-tail",
                    through_cycle=1,
                )
            propose_again.assert_not_called()
            deliberate_again.assert_not_called()
            collect_again.assert_not_called()
            self.assertEqual("PAUSED_AT_DURABLE_CYCLE_BOUNDARY", resumed["status"])

    def test_post_accept_recovery_forbids_agent_reinvocation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(
                runtime_root=runtime_root,
                run_id="post-accept-recovery",
                through_cycle=1,
            )
            store = ResearchCycleStore(
                runtime_root / "post-accept-recovery",
                run_id="post-accept-recovery",
                cycle_index=1,
            )
            status = ContinuousResearchCycleCoordinator(
                store,
                run_id="post-accept-recovery",
                cycle_index=1,
            ).recovery_status()
            self.assertTrue(status["agent_reinvocation_forbidden"])
            self.assertIsNone(status["next_required_event_type"])


class ControllerReliabilityTests(unittest.TestCase):
    def test_desired_delete_never_masks_still_active_controller(self) -> None:
        first = build_controller_reconciliation(
            controller_id="heartbeat:v1-3",
            command_id="delete:v1-3",
            observed_at="2026-08-06T08:00:00Z",
            desired_state="DELETED",
            actual_state="ACTIVE",
            lease_id=None,
            lease_expires_at=None,
            kill_switch_engaged=True,
        )
        second = build_controller_reconciliation(
            controller_id="heartbeat:v1-3",
            command_id="delete:v1-3",
            observed_at="2026-08-06T08:00:00Z",
            desired_state="DELETED",
            actual_state="ACTIVE",
            lease_id=None,
            lease_expires_at=None,
            kill_switch_engaged=True,
        )
        self.assertEqual(first, second)
        self.assertFalse(first["state_converged"])
        self.assertFalse(first["run_permission"])
        self.assertEqual(
            "REISSUE_IDEMPOTENT_DELETE_AND_VERIFY", first["next_action"]
        )
        self.assertNotEqual(first["desired_state"], first["actual_state"])

    def test_controller_reconciliation_is_durable_and_self_verifying(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = CanonicalContinuousArtifactRepository(Path(directory))
            reconciliation = build_controller_reconciliation(
                controller_id="local-simulated-controller",
                command_id="pause:local-simulated-controller",
                observed_at="2026-08-06T08:00:00Z",
                desired_state="PAUSED",
                actual_state="ACTIVE",
                lease_id=None,
                lease_expires_at=None,
                kill_switch_engaged=True,
            )
            binding = repository.write_document(
                relative_ref="controller/reconciliation.json",
                document=reconciliation,
                digest_field="controller_reconciliation_digest",
            )
            loaded = repository.read_document(
                relative_ref=binding["relative_ref"],
                digest_field="controller_reconciliation_digest",
                expected_semantic_digest=binding["semantic_digest"],
            )
            self.assertEqual(reconciliation, loaded)
            self.assertFalse(loaded["run_permission"])
            self.assertEqual(
                "REISSUE_IDEMPOTENT_PAUSE_AND_VERIFY", loaded["next_action"]
            )

    def test_local_run_lease_rejects_parallel_window_and_pauses_on_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "exclusive-run"
            first = LocalRunLease(run_root, run_id="exclusive-run")
            second = LocalRunLease(run_root, run_id="exclusive-run")
            first.__enter__()
            try:
                with self.assertRaisesRegex(
                    ContinuousFixtureInfrastructureError,
                    "FIXTURE_CONTROLLER_LEASE_ALREADY_HELD",
                ):
                    second.__enter__()
            finally:
                first.__exit__(None, None, None)
            current = load_json_strict(run_root / "controller/current.json")
            verify_self_digest(current, "controller_reconciliation_digest")
            self.assertEqual("PAUSED", current["desired_state"])
            self.assertEqual("PAUSED", current["actual_state"])
            self.assertTrue(current["kill_switch_engaged"])
            self.assertFalse(current["run_permission"])


if __name__ == "__main__":
    unittest.main()
