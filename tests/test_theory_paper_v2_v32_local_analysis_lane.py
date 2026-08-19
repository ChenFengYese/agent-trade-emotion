from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tests import test_theory_paper_v2_v32_cycle_acceptance as acceptance_fixture
from tests import test_theory_paper_v2_v32_public_source_collector as collector_fixture
from trade_system.theory_paper_v2.application.v32_agent_semantic_compiler import (
    build_v32_proposal_semantic_output_v1,
    build_v32_selection_semantic_output_v1,
    canonical_v32_agent_semantic_json_v1,
)
from trade_system.theory_paper_v2.application.v32_authorized_revision_orchestration import (
    build_v32_authorized_revision_cycle_registry_v1,
    build_v32_revision_input_state_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    build_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.domain.v32_environment_capability import (
    CAPABILITY_CATEGORIES,
    DIGEST_FIELD as ENVIRONMENT_DIGEST_FIELD,
    SCHEMA_ID as ENVIRONMENT_SCHEMA_ID,
    build_v32_environment_capability_profile_v1,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
    open_v32_tick_supervisor_permit,
)
from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_dynamic_store import (
    CHECKPOINT_DIGEST_FIELD as RESEARCH_CHECKPOINT_DIGEST_FIELD,
    LocalV32DynamicStore,
    STORE_ROOT as RESEARCH_STORE_ROOT,
)
from trade_system.theory_paper_v2.infrastructure.v32_local_analysis_lane import (
    LocalV32AnalysisLane,
    V32LocalAnalysisLaneError,
    build_v32_required_data_gap_escalations_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    V32PublicSourceCollectorError,
    V32RawFirstOkxPublicBundleCollector,
    verify_durable_v32_public_source_qualification,
)


class _KeyedClock:
    VALUES = {
        "RESEARCH_ARTIFACT_RECORDED": "2026-08-07T00:18:00Z",
        "PROPOSAL_CONTEXT_CREATED": "2026-08-07T00:16:00Z",
        "PROPOSAL_COMPILED": "2026-08-07T00:16:40Z",
        "SELECTION_PACKET_PREPARED": "2026-08-07T00:16:45Z",
        "SELECTION_CONTEXT_CREATED": "2026-08-07T00:16:50Z",
        "SELECTION_COMPILED": "2026-08-07T00:17:30.654321Z",
        "SHADOW_BUNDLE_CREATED": "2026-08-07T00:17:35Z",
        "COMMIT_SEALED": "2026-08-07T00:17:50Z",
        "RESEARCH_CYCLE_ACCEPTED": "2026-08-07T00:18:00Z",
        "OUTCOME_SCHEDULE_REGISTERED": "2026-08-07T00:18:00Z",
        "ANALYSIS_COMPLETION_SEALED": "2026-08-07T00:18:00.987654Z",
        "ANALYSIS_FAILURE_SEALED": "2026-08-07T00:18:00Z",
    }

    def timestamp(self, *, boundary: str, permit: dict) -> str:
        del permit
        return self.VALUES[boundary]


class _StaleAfterAgentClock(_KeyedClock):
    VALUES = {
        **_KeyedClock.VALUES,
        "RESEARCH_ARTIFACT_RECORDED": "2026-08-07T00:31:00Z",
        "SELECTION_COMPILED": "2026-08-07T00:31:00Z",
        "ANALYSIS_FAILURE_SEALED": "2026-08-07T00:31:01Z",
    }


class _NoClock:
    def __init__(self) -> None:
        self.calls = 0

    def timestamp(self, *, boundary: str, permit: dict) -> str:
        del boundary, permit
        self.calls += 1
        raise AssertionError("orphan recovery must not read a new clock")


class _SourcePreparationClock:
    def timestamp(self, *, boundary: str, permit: dict) -> str:
        del permit
        offsets = {"SOURCE_ADMITTED": 7, "SOURCE_REPLAYED": 8}
        return collector_fixture.ts(
            collector_fixture.BASE + timedelta(seconds=offsets[boundary])
        )


class _SimulatedProcessCrash(BaseException):
    pass


class _FixtureMaterial:
    def __init__(self, fixture: dict) -> None:
        self.fx = fixture

    def build_timeframe_context(self, **kwargs):
        del kwargs
        return deepcopy(self.fx["timeframe"])

    def build_proposal_packet(self, **kwargs):
        del kwargs
        return deepcopy(self.fx["semantic"]["proposal_packet"])

    def lossless_context_package(self, **kwargs):
        del kwargs
        return None

    def build_authorized_revision_cycle_registry(
        self,
        *,
        permit,
        proposal_packet,
        proposal_context_package,
        selection_packet,
        selection_context_package,
        required_data_gap_escalations,
    ):
        self.assert_no_agent_compaction(
            proposal_context_package, selection_context_package
        )
        run_id = permit["run_id"]
        # The registry contract accepts any complete, lossless cycle context.
        # Keep this control-flow fixture small; Agent packet sharding is tested
        # separately and production material may register the complete packets.
        proposal_revision_original = self_digest(
            {
                "schema_id": "test_v32_lane_proposal_revision_context_v1",
                "run_id": run_id,
                "cycle_index": permit["analysis_cycle_index"],
                "proposal_packet_digest": proposal_packet[
                    "proposal_canonical_packet_digest"
                ],
            },
            "proposal_canonical_packet_digest",
        )
        selection_revision_original = self_digest(
            {
                "schema_id": "test_v32_lane_selection_revision_context_v1",
                "run_id": run_id,
                "cycle_index": permit["analysis_cycle_index"],
                "selection_packet_digest": selection_packet[
                    "selection_canonical_packet_digest"
                ],
            },
            "selection_canonical_packet_digest",
        )
        proposal_context = acceptance_fixture._context_package(
            stage="proposal", run_id=run_id, packet=proposal_revision_original
        )
        selection_context = acceptance_fixture._context_package(
            stage="selection", run_id=run_id, packet=selection_revision_original
        )
        environment = build_v32_environment_capability_profile_v1(
            profile_id="v32-analysis-lane-test-environment",
            run_scope_id=run_id,
            frozen_at="2026-08-07T00:17:40Z",
            capabilities=[
                {
                    "category": category,
                    "status": "AVAILABLE",
                    "observed_value": "local deterministic lane fixture",
                    "limit": "contract wiring only",
                    "evidence_refs": [f"test:{category.lower()}"],
                    "claim_ceiling": "LOCAL_CONTRACT_TEST_ONLY",
                }
                for category in CAPABILITY_CATEGORIES
            ],
            localization_adapters=[],
        )
        environment_conformance = {
            "profile": environment,
            "profile_binding": acceptance_fixture._binding(
                "lane-revision-environment",
                environment,
                ENVIRONMENT_SCHEMA_ID,
                ENVIRONMENT_DIGEST_FIELD,
            ),
        }
        data_gap_entries = [
            {
                "escalation": escalation,
                "escalation_binding": acceptance_fixture._binding(
                    f"lane-gap-{index:04d}",
                    escalation,
                    escalation["schema_id"],
                    "data_gap_escalation_digest",
                ),
            }
            for index, escalation in enumerate(required_data_gap_escalations)
        ]
        inputs = {
            "proposal_context": proposal_context,
            "selection_context": selection_context,
            "unknown_tracks": [],
            "data_gap_entries": data_gap_entries,
            "manual_evidence_entries": [],
            "environment_conformance": environment_conformance,
            "recovery_traces": [],
            "revision_input_state": build_v32_revision_input_state_v1(
                run_id=run_id,
                cycle_index=permit["analysis_cycle_index"],
                state="NO_REVISION_INPUT",
                observed_at="2026-08-07T00:17:40Z",
                reason="TEST_FIXTURE_HAS_NO_REVISION_INPUT",
                reader_binding={
                    "reader_id": "TEST_V32_LANE_NO_INPUT_READER_V1",
                    "reader_version": "1.0.0",
                    "reader_kind": "TEST_LOCAL_EXPLICIT_NO_REVISION_INPUT",
                    "configuration_digest": canonical_digest(
                        {"revision_source_configured": False}
                    ),
                },
            ),
        }
        registry = build_v32_authorized_revision_cycle_registry_v1(
            registry_id="v32-analysis-lane-test-registry",
            run_id=run_id,
            cycle_index=permit["analysis_cycle_index"],
            created_at="2026-08-07T00:17:45Z",
            **inputs,
        )
        return {"cycle_registry": registry, **inputs}

    @staticmethod
    def assert_no_agent_compaction(proposal, selection) -> None:
        if proposal is not None or selection is not None:
            raise AssertionError("this fixture exercises the direct context path")

    def build_outcome_schedule_set(
        self,
        *,
        permit,
        final_dynamic_action_plan,
        proposal_packet,
        decision_sealed_at,
    ):
        return build_v32_outcome_schedule_set(
            run_id=permit["run_id"],
            decision_id="decision:v32:analysis-lane:0001",
            cycle_index=permit["analysis_cycle_index"],
            decision_time=decision_sealed_at,
            scheduled_at="2026-08-07T00:17:35Z",
            sealed_decision_digest=final_dynamic_action_plan[
                "dynamic_action_plan_digest"
            ],
            evaluation_contract_digest=proposal_packet["support_documents"]
            ["experiment_contract"]["support_bindings"]
            ["evaluation_contract_digest"],
        )


class _UnusedMaterial:
    @staticmethod
    def _unexpected(*args, **kwargs):
        del args, kwargs
        raise AssertionError("material port unexpectedly used")

    build_timeframe_context = _unexpected
    build_proposal_packet = _unexpected
    lossless_context_package = _unexpected
    build_authorized_revision_cycle_registry = _unexpected
    build_outcome_schedule_set = _unexpected


class _NeverCollector:
    def __init__(self) -> None:
        self.calls = 0

    def collect_and_qualify(self, **kwargs):
        del kwargs
        self.calls += 1
        raise AssertionError("prequalified source must not be recollected")


class _FastReplayDynamicStore(LocalV32DynamicStore):
    """Keep control-flow tests fast; the terminal head is fully replayed once."""

    def load_checkpoint(self, *, run_id: str, _already_locked: bool = False):
        del _already_locked
        checkpoint = load_json_strict(self.checkpoint_path)
        verify_self_digest(checkpoint, RESEARCH_CHECKPOINT_DIGEST_FIELD)
        if checkpoint["run_id"] != run_id:
            raise AssertionError("run drift")
        return checkpoint


class V32LocalAnalysisLaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = acceptance_fixture._fixture()

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    @staticmethod
    def _supervisor(
        *, run_id, contract_digest, authority_digest, research_digest, outcome_digest,
        decision_time="2026-08-07T00:15:00Z",
        issued_at="2026-08-07T00:15:01Z",
    ):
        before = build_v32_tick_supervisor_checkpoint(
            run_id=run_id,
            experiment_contract_digest=contract_digest,
            active_authority_digest=authority_digest,
            research_checkpoint_digest=research_digest,
            outcome_checkpoint_digest=outcome_digest,
            timeframe_cache_digest="e" * 64,
            created_at="2026-08-07T00:00:00Z",
        )
        permit = build_v32_analysis_tick_permit(
            checkpoint=before,
            schedule_sets=[],
            analysis_decision_at=decision_time,
            issued_at=issued_at,
            research_checkpoint_digest=research_digest,
            outcome_checkpoint_digest=outcome_digest,
            timeframe_cache_digest="e" * 64,
            prior_dynamic_state_digest=None,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=before,
            permit=permit,
            schedule_sets=[],
            updated_at=issued_at,
        )
        return before, permit, opened

    def _full_lane(self, *, material=None, probe_invalid_constructor=False):
        fx = self.fx
        run_id = fx["run_id"]
        source = fx["source"]
        dynamic = _FastReplayDynamicStore(self.root)
        research = dynamic.initialize_checkpoint(
            run_id=run_id,
            experiment_contract_digest=source["experiment_contract_digest"],
            active_authority_digest=source["governing_authority_digest"],
            created_at="2026-08-07T00:00:00Z",
        )
        outcome = LocalV32OutcomeTickStore(self.root)
        outcome_checkpoint = outcome.initialize_checkpoint(
            run_id=run_id, created_at="2026-08-07T00:00:00Z"
        )
        before, permit, opened = self._supervisor(
            run_id=run_id,
            contract_digest=source["experiment_contract_digest"],
            authority_digest=source["governing_authority_digest"],
            research_digest=research[RESEARCH_CHECKPOINT_DIGEST_FIELD],
            outcome_digest=outcome_checkpoint["checkpoint_digest"],
            issued_at="2026-08-07T00:15:03Z",
        )
        mailbox = LocalV32CurrentRootAgentMailbox(self.root)
        collector = _NeverCollector()
        source_store = LocalV32CycleSourceAdmissionStore(
            Path(fx["market"]["source_store_root"])
        )
        admitted_store = LocalV32CycleSourceAdmissionStore(
            Path(fx["market"]["run_store_root"])
        )
        qualification_id = f"q-{run_id.replace(':', '-')}-0001"
        qualified = verify_durable_v32_public_source_qualification(
            store=source_store,
            qualification_id=qualification_id,
            active_authority=fx["authority_projection"],
        )
        material = _FixtureMaterial(fx) if material is None else material
        lane_arguments = {
            "dynamic_store": dynamic,
            "outcome_store": outcome,
            "source_store": source_store,
            "admitted_source_store": admitted_store,
            "source_collector": collector,
            "mailbox": mailbox,
            "active_authority_projection": fx["authority_projection"],
            "qualification_id_factory": lambda run_id, cycle_index: (
                f"q-{run_id.replace(':', '-')}-{cycle_index:04d}"
            ),
            "clock": _KeyedClock(),
            "material_port": material,
        }
        if probe_invalid_constructor:
            invalid_arguments = dict(lane_arguments)
            invalid_arguments["clock"] = object()
            with self.assertRaisesRegex(
                V32LocalAnalysisLaneError, "CLOCK_INVALID"
            ):
                LocalV32AnalysisLane(**invalid_arguments)
        lane = LocalV32AnalysisLane(**lane_arguments)
        cached_source_replay = {
            "qualification": qualified,
            "admission": fx["market"]["admission_result"],
            "replay": {
                "durable_source_replay_receipt": fx["market"]
                ["source_replay_receipt"],
                "durable_source_replay_receipt_binding": fx["market"]
                ["source_replay_receipt_binding"],
            },
        }
        return (
            lane,
            dynamic,
            outcome,
            mailbox,
            collector,
            before,
            permit,
            opened,
            cached_source_replay,
        )

    def test_constructor_attestation_rejects_bypass_and_is_not_consumed_by_invalid_input(
        self,
    ):
        lane, dynamic, *_ = self._full_lane(probe_invalid_constructor=True)
        self.assertIs(lane._dynamic, dynamic)
        with self.assertRaisesRegex(
            V32LocalAnalysisLaneError,
            "ARTIFACT_WRITER_UNAVAILABLE",
        ):
            LocalV32AnalysisLane(
                dynamic_store=dynamic,
                outcome_store=lane._outcome,
                source_store=lane._source,
                admitted_source_store=lane._admitted_source,
                source_collector=lane._collector,
                mailbox=lane._mailbox,
                active_authority_projection=lane._authority,
                qualification_id_factory=lane._qualification_id_factory,
                clock=lane._clock,
                material_port=lane._material,
                public_evidence_verifier=lane._public,
            )

    @staticmethod
    def _cached_source_patches(cached):
        return mock.patch.multiple(
            "trade_system.theory_paper_v2.infrastructure.v32_local_analysis_lane",
            verify_durable_v32_public_source_qualification=mock.Mock(
                return_value=cached["qualification"]
            ),
            verify_durable_v32_cycle_source_admission=mock.Mock(
                return_value=cached["admission"]
            ),
            verify_durable_v32_source_replay_receipt=mock.Mock(
                return_value=cached["replay"]
            ),
        )

    def _deliver_requested_agent_stage(self, mailbox, permit) -> str | None:
        try:
            checkpoint = mailbox.load_checkpoint(
                run_id=permit["run_id"],
                cycle_index=permit["analysis_cycle_index"],
            )
        except Exception:
            return None
        for stage in ("PROPOSAL", "SELECTION"):
            if checkpoint["stage_states"][stage]["status"] != "REQUESTED":
                continue
            chain = mailbox.load_stage_chain(
                run_id=permit["run_id"],
                cycle_index=permit["analysis_cycle_index"],
                stage=stage,
            )
            context = chain["request"]["agent_input_context"]
            claimed_at = (
                "2026-08-07T00:16:10Z"
                if stage == "PROPOSAL"
                else "2026-08-07T00:17:00Z"
            )
            delivered_at = (
                "2026-08-07T00:16:20Z"
                if stage == "PROPOSAL"
                else "2026-08-07T00:17:10Z"
            )
            claimed = mailbox.claim_request(
                run_id=permit["run_id"],
                cycle_index=permit["analysis_cycle_index"],
                stage=stage,
                expected_checkpoint_digest=checkpoint[
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                claimed_at=claimed_at,
            )
            current_codex_presentation = (
                build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=claimed["checkpoint"],
                    request=claimed["request"],
                    claim=claimed["claim"],
                    lossless_context_package=None,
                    control_context={
                        "presentation_kind": "MAILBOX_AGENT_CLAIM",
                        "stage": stage,
                        "stage_status": "CLAIMED",
                        "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                    },
                )
            )
            if stage == "PROPOSAL":
                template = self.fx["semantic"]["proposal_output"]
                candidate_material = template["preselection_candidate_material"]
                output = build_v32_proposal_semantic_output_v1(
                    proposal_input_context=context,
                    current_dynamic_research_state=template[
                        "current_dynamic_research_state"
                    ],
                    reference_context=candidate_material["reference_context"],
                    risk_arithmetic=candidate_material["risk_arithmetic"],
                    candidate_rows=candidate_material["candidate_rows"],
                    sealed_plan_variants=template["sealed_plan_variants"],
                )
            else:
                output = build_v32_selection_semantic_output_v1(
                    selection_input_context=context,
                    selected_candidate_id=self.fx["semantic"][
                        "selection_output"
                    ]["selected_candidate_id"],
                )
            mailbox.submit_delivery(
                run_id=permit["run_id"],
                cycle_index=permit["analysis_cycle_index"],
                stage=stage,
                expected_checkpoint_digest=claimed["checkpoint"]
                [MAILBOX_CHECKPOINT_DIGEST_FIELD],
                current_codex_presentation_envelope=current_codex_presentation,
                expected_current_codex_presentation_digest=(
                    current_codex_presentation[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ]
                ),
                delivered_at=delivered_at,
                payload_utf8=canonical_v32_agent_semantic_json_v1(output),
            )
            return stage
        return None

    def test_complete_cycle_waits_for_real_agent_and_seals_replayable_completion(self):
        (
            lane,
            dynamic,
            outcome,
            mailbox,
            collector,
            before,
            permit,
            opened,
            cached,
        ) = self._full_lane()
        deliveries: list[str] = []
        transitions: list[str] = []
        with self._cached_source_patches(cached):
            for _ in range(96):
                result = lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )
                transitions.append(result["advance_status"])
                delivered = self._deliver_requested_agent_stage(mailbox, permit)
                if delivered is not None:
                    deliveries.append(delivered)
                if result["advance_status"] != "PENDING":
                    break
        self.assertEqual(
            transitions[-1],
            "COMPLETION_SEALED",
            lane.load_durable_analysis_failure(permit=permit),
        )
        self.assertEqual(deliveries, ["PROPOSAL", "SELECTION"])
        self.assertEqual(collector.calls, 0)
        mailbox_checkpoint = mailbox.load_checkpoint(
            run_id=permit["run_id"], cycle_index=1
        )
        self.assertEqual(
            {
                stage: mailbox_checkpoint["stage_states"][stage]["attempt_count"]
                for stage in ("PROPOSAL", "SELECTION")
            },
            {"PROPOSAL": 1, "SELECTION": 1},
        )
        research = LocalV32DynamicStore(self.root).load_checkpoint(
            run_id=permit["run_id"]
        )
        self.assertEqual(research["accepted_analysis_cycles"], 1)
        self.assertEqual(len(outcome.load_schedule_sets(run_id=permit["run_id"])), 1)
        completion = lane.load_durable_analysis_completion(permit=permit)
        self.assertIsNotNone(completion)
        supervisor = LocalV32TickSupervisorStore(self.root)
        supervisor.initialize_checkpoint(checkpoint=before)
        supervisor_open = supervisor.open_permit(
            permit=permit,
            schedule_sets=[],
            expected_checkpoint_digest=before[SUPERVISOR_CHECKPOINT_DIGEST_FIELD],
            opened_at=permit["issued_at"],
        )
        supervisor_ready = supervisor.complete_analysis_tick(
            permit=permit,
            completion=completion["completion"],
            expected_checkpoint_digest=supervisor_open[
                SUPERVISOR_CHECKPOINT_DIGEST_FIELD
            ],
        )
        self.assertEqual("READY", supervisor_ready["status"])
        self.assertEqual(
            _KeyedClock.VALUES["SELECTION_COMPILED"],
            supervisor_ready["last_analysis_decision_at"],
        )
        self.assertNotEqual(
            permit["analysis_decision_at"],
            supervisor_ready["last_analysis_decision_at"],
        )
        source_admission = cached["admission"]["cycle_source_admission"]
        four_times = [
            datetime.fromisoformat(
                permit["analysis_decision_at"].replace("Z", "+00:00")
            ),
            datetime.fromisoformat(
                source_admission["admitted_at"].replace("Z", "+00:00")
            ),
            datetime.fromisoformat(permit["issued_at"].replace("Z", "+00:00")),
            datetime.fromisoformat(
                supervisor_ready["last_analysis_decision_at"].replace(
                    "Z", "+00:00"
                )
            ),
        ]
        self.assertEqual(four_times, sorted(set(four_times)))
        self.assertNotEqual(0, four_times[-1].microsecond)
        self.assertEqual(
            _KeyedClock.VALUES["SELECTION_COMPILED"],
            completion["completion"]["new_schedule_set"]["decision_time"],
        )
        with (
            self._cached_source_patches(cached),
            mock.patch.object(
                dynamic,
                "replay_cycle_acceptance",
                wraps=dynamic.replay_cycle_acceptance,
            ) as acceptance_replay,
            mock.patch.object(
                lane,
                "_binding_for",
                side_effect=AssertionError(
                    "completion must consume public acceptance replay bindings"
                ),
            ),
        ):
            self.assertEqual(
                lane.verify_durable_analysis_completion(
                    permit=permit, completion_envelope=completion
                ),
                completion,
            )
            acceptance_replay.assert_called_once_with(
                run_id=permit["run_id"], cycle_index=1
            )
        with self._cached_source_patches(cached):
            again = lane.advance_analysis(
                permit=permit,
                supervisor_checkpoint_before_permit=before,
                supervisor_open_checkpoint=opened,
            )
        self.assertEqual(again["advance_status"], "COMPLETION_SEALED")
        self.assertEqual(collector.calls, 0)

    def test_post_agent_stale_seals_typed_failure_once(self):
        (
            lane,
            _,
            outcome,
            mailbox,
            collector,
            before,
            permit,
            opened,
            cached,
        ) = self._full_lane()
        lane._clock = _StaleAfterAgentClock()
        deliveries: list[str] = []
        with self._cached_source_patches(cached):
            for _ in range(96):
                result = lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )
                delivered = self._deliver_requested_agent_stage(mailbox, permit)
                if delivered is not None:
                    deliveries.append(delivered)
                if result["advance_status"] == "FAILURE_SEALED":
                    break
        self.assertEqual("FAILURE_SEALED", result["advance_status"])
        self.assertEqual(["PROPOSAL", "SELECTION"], deliveries)
        failure = lane.load_durable_analysis_failure(permit=permit)
        self.assertEqual("SOURCE_STALE_AFTER_AGENT", failure["failure_code"])
        self.assertEqual("SOURCE_STALE_AFTER_AGENT", failure["failure_summary"])
        self.assertEqual("2026-08-07T00:31:01Z", failure["occurred_at"])
        self.assertEqual([], outcome.load_schedule_sets(run_id=permit["run_id"]))
        self.assertEqual(0, collector.calls)
        lane._clock = _NoClock()
        with self._cached_source_patches(cached):
            replay = lane.advance_analysis(
                permit=permit,
                supervisor_checkpoint_before_permit=before,
                supervisor_open_checkpoint=opened,
            )
        self.assertEqual("FAILURE_SEALED", replay["advance_status"])

    def test_proposal_input_file_pre_cas_crash_is_attached_without_new_clock(self):
        (
            lane,
            dynamic,
            _,
            _,
            collector,
            before,
            permit,
            opened,
            cached,
        ) = self._full_lane()
        run_id = permit["run_id"]
        with self._cached_source_patches(cached):
            for _ in range(48):
                checkpoint = dynamic.load_checkpoint(run_id=run_id)
                roles = {
                    row["role"]
                    for row in checkpoint["artifact_bindings"]
                    if row["cycle_index"] == 1
                }
                if "proposal_packet" in roles and "proposal_input" not in roles:
                    break
                result = lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )
                self.assertEqual("PENDING", result["advance_status"])
            else:
                self.fail("proposal input boundary was not reached")

            predecessor = dynamic.load_checkpoint(run_id=run_id)
            with (
                mock.patch.object(
                    dynamic,
                    "_replace_checkpoint",
                    side_effect=_SimulatedProcessCrash(
                        "proposal-input-file-before-checkpoint"
                    ),
                ),
                self.assertRaisesRegex(
                    _SimulatedProcessCrash, "proposal-input-file"
                ),
            ):
                lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )

            orphan_path = (
                self.root
                / RESEARCH_STORE_ROOT
                / "cycles/0001/analysis-lane/proposal_input.json"
            )
            orphan_bytes = orphan_path.read_bytes()
            self.assertEqual(
                predecessor[RESEARCH_CHECKPOINT_DIGEST_FIELD],
                dynamic.load_checkpoint(run_id=run_id)[
                    RESEARCH_CHECKPOINT_DIGEST_FIELD
                ],
            )
            no_clock = _NoClock()
            lane._clock = no_clock
            recovered = lane.advance_analysis(
                permit=permit,
                supervisor_checkpoint_before_permit=before,
                supervisor_open_checkpoint=opened,
            )

        self.assertEqual("PENDING", recovered["advance_status"])
        self.assertEqual(0, no_clock.calls)
        self.assertEqual(0, collector.calls)
        self.assertEqual(orphan_bytes, orphan_path.read_bytes())
        checkpoint = dynamic.load_checkpoint(run_id=run_id)
        proposal_bindings = [
            row
            for row in checkpoint["artifact_bindings"]
            if row["cycle_index"] == 1 and row["role"] == "proposal_input"
        ]
        self.assertEqual(1, len(proposal_bindings))
        self.assertEqual(
            load_json_strict(orphan_path),
            dynamic.load_artifact(proposal_bindings[0]),
        )

    def test_acceptance_file_pre_cas_crash_reuses_sealed_time_without_agent_or_clock(
        self,
    ):
        (
            lane,
            dynamic,
            _,
            mailbox,
            collector,
            before,
            permit,
            opened,
            cached,
        ) = self._full_lane()
        run_id = permit["run_id"]
        deliveries: list[str] = []
        with self._cached_source_patches(cached):
            for _ in range(96):
                checkpoint = dynamic.load_checkpoint(run_id=run_id)
                roles = {
                    row["role"]
                    for row in checkpoint["artifact_bindings"]
                    if row["cycle_index"] == 1
                }
                if "commit_envelope" in roles and "analysis_acceptance" not in roles:
                    break
                result = lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )
                delivered = self._deliver_requested_agent_stage(mailbox, permit)
                if delivered is not None:
                    deliveries.append(delivered)
                self.assertEqual("PENDING", result["advance_status"])
            else:
                self.fail("acceptance boundary was not reached")

            predecessor = dynamic.load_checkpoint(run_id=run_id)
            with (
                mock.patch.object(
                    dynamic,
                    "_replace_checkpoint",
                    side_effect=_SimulatedProcessCrash(
                        "acceptance-file-before-checkpoint"
                    ),
                ),
                self.assertRaisesRegex(_SimulatedProcessCrash, "acceptance-file"),
            ):
                lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )

            orphan_path = (
                self.root
                / RESEARCH_STORE_ROOT
                / "cycles/0001/final/analysis-acceptance.json"
            )
            orphan_bytes = orphan_path.read_bytes()
            sealed_acceptance = load_json_strict(orphan_path)
            self.assertEqual(
                predecessor[RESEARCH_CHECKPOINT_DIGEST_FIELD],
                dynamic.load_checkpoint(run_id=run_id)[
                    RESEARCH_CHECKPOINT_DIGEST_FIELD
                ],
            )
            no_clock = _NoClock()
            lane._clock = no_clock
            attached = lane.advance_analysis(
                permit=permit,
                supervisor_checkpoint_before_permit=before,
                supervisor_open_checkpoint=opened,
            )
            with mock.patch.object(
                lane,
                "_seal_failure",
                side_effect=lambda *, permit, error: (_ for _ in ()).throw(error),
            ):
                accepted = lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )

        self.assertEqual("PENDING", attached["advance_status"])
        self.assertEqual("PENDING", accepted["advance_status"])
        self.assertEqual(0, no_clock.calls)
        self.assertEqual(0, collector.calls)
        self.assertEqual(["PROPOSAL", "SELECTION"], deliveries)
        self.assertEqual(orphan_bytes, orphan_path.read_bytes())
        checkpoint = dynamic.load_checkpoint(run_id=run_id)
        self.assertEqual(1, checkpoint["accepted_analysis_cycles"])
        self.assertEqual(
            sealed_acceptance["accepted_at"],
            checkpoint["accepted_cycle_bindings"][0]["accepted_at"],
        )
        mailbox_checkpoint = mailbox.load_checkpoint(run_id=run_id, cycle_index=1)
        self.assertEqual(
            {stage: mailbox_checkpoint["stage_states"][stage]["attempt_count"] for stage in ("PROPOSAL", "SELECTION")},
            {"PROPOSAL": 1, "SELECTION": 1},
        )

    def test_requested_agent_stage_is_pending_and_never_fabricated(self):
        lane, _, _, mailbox, _, before, permit, opened, cached = self._full_lane()
        with self._cached_source_patches(cached):
            for _ in range(48):
                result = lane.advance_analysis(
                    permit=permit,
                    supervisor_checkpoint_before_permit=before,
                    supervisor_open_checkpoint=opened,
                )
                try:
                    checkpoint = mailbox.load_checkpoint(
                        run_id=permit["run_id"], cycle_index=1
                    )
                except Exception:
                    continue
                if checkpoint["stage_states"]["PROPOSAL"]["status"] == "REQUESTED":
                    break
            else:
                self.fail("proposal request was not durably enqueued")
            same = lane.advance_analysis(
                permit=permit,
                supervisor_checkpoint_before_permit=before,
                supervisor_open_checkpoint=opened,
            )
        self.assertEqual(result["advance_status"], "PENDING")
        self.assertEqual(same["advance_status"], "PENDING")
        self.assertEqual(
            same["durable_transition_digest"],
            checkpoint[MAILBOX_CHECKPOINT_DIGEST_FIELD],
        )
        chain = mailbox.load_stage_chain(
            run_id=permit["run_id"], cycle_index=1, stage="PROPOSAL"
        )
        self.assertIsNone(chain["agent_delivery"])

    def test_transport_failure_is_attempted_once_then_permanently_sealed(self):
        run_id = collector_fixture.RUN_ID
        authority = collector_fixture.authority()
        source = collector_fixture.RecordingStore(self.root / "source")
        admitted = LocalV32CycleSourceAdmissionStore(self.root / "admitted")
        transport = collector_fixture.BundleTransport(None, fail=True)
        source_times = iter(
            [
                collector_fixture.ts(
                    collector_fixture.BASE
                    + timedelta(seconds=offset, microseconds=123_456)
                )
                for offset in (1, 2, 4, 5, 6)
            ]
        )
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=source_times.__next__,
            store=source,
        )
        dynamic = LocalV32DynamicStore(self.root)
        research = dynamic.initialize_checkpoint(
            run_id=run_id,
            experiment_contract_digest=collector_fixture.CONTRACT_DIGEST,
            active_authority_digest="a" * 64,
            created_at=collector_fixture.ts(collector_fixture.BASE),
        )
        outcome = LocalV32OutcomeTickStore(self.root)
        outcome_checkpoint = outcome.initialize_checkpoint(
            run_id=run_id, created_at=collector_fixture.ts(collector_fixture.BASE)
        )
        decision = collector_fixture.ts(
            collector_fixture.BASE
            + timedelta(seconds=6, microseconds=123_456)
        )
        issued = collector_fixture.ts(
            collector_fixture.BASE + timedelta(seconds=7)
        )
        before, permit, opened = self._supervisor(
            run_id=run_id,
            contract_digest=collector_fixture.CONTRACT_DIGEST,
            authority_digest="a" * 64,
            research_digest=research[RESEARCH_CHECKPOINT_DIGEST_FIELD],
            outcome_digest=outcome_checkpoint["checkpoint_digest"],
            decision_time=decision,
            issued_at=issued,
        )
        lane = LocalV32AnalysisLane(
            dynamic_store=dynamic,
            outcome_store=outcome,
            source_store=source,
            admitted_source_store=admitted,
            source_collector=collector,
            mailbox=LocalV32CurrentRootAgentMailbox(self.root),
            active_authority_projection=authority,
            qualification_id_factory=lambda **kwargs: "q-lane-failure",
            clock=_KeyedClock(),
            material_port=_UnusedMaterial(),
        )
        del permit, opened
        with self.assertRaises(V32PublicSourceCollectorError):
            lane.prepare_cycle_source(
                run_id=run_id,
                cycle_index=1,
                supervisor_checkpoint=before,
            )
        self.assertEqual(transport.calls, 1)
        with self.assertRaises(V32PublicSourceCollectorError):
            lane.prepare_cycle_source(
                run_id=run_id,
                cycle_index=1,
                supervisor_checkpoint=before,
            )
        self.assertEqual(transport.calls, 1)

    def test_successful_source_collection_is_one_transport_boundary(self):
        run_id = collector_fixture.RUN_ID
        authority = collector_fixture.authority()
        source = collector_fixture.RecordingStore(self.root / "source")
        admitted = LocalV32CycleSourceAdmissionStore(self.root / "admitted")
        transport = collector_fixture.BundleTransport(
            collector_fixture.raw_bundle(unknown_optional=True)
        )
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=collector_fixture.SequenceClock(),
            store=source,
        )
        dynamic = LocalV32DynamicStore(self.root)
        research = dynamic.initialize_checkpoint(
            run_id=run_id,
            experiment_contract_digest=collector_fixture.CONTRACT_DIGEST,
            active_authority_digest="a" * 64,
            created_at=collector_fixture.ts(collector_fixture.BASE),
        )
        outcome = LocalV32OutcomeTickStore(self.root)
        outcome_checkpoint = outcome.initialize_checkpoint(
            run_id=run_id, created_at=collector_fixture.ts(collector_fixture.BASE)
        )
        decision = collector_fixture.ts(
            collector_fixture.BASE + timedelta(seconds=6)
        )
        issued = collector_fixture.ts(
            collector_fixture.BASE + timedelta(seconds=9)
        )
        before, permit, opened = self._supervisor(
            run_id=run_id,
            contract_digest=collector_fixture.CONTRACT_DIGEST,
            authority_digest="a" * 64,
            research_digest=research[RESEARCH_CHECKPOINT_DIGEST_FIELD],
            outcome_digest=outcome_checkpoint["checkpoint_digest"],
            decision_time=decision,
            issued_at=issued,
        )
        qid = "q-lane-success"
        lane = LocalV32AnalysisLane(
            dynamic_store=dynamic,
            outcome_store=outcome,
            source_store=source,
            admitted_source_store=admitted,
            source_collector=collector,
            mailbox=LocalV32CurrentRootAgentMailbox(self.root),
            active_authority_projection=authority,
            qualification_id_factory=lambda **kwargs: qid,
            clock=_SourcePreparationClock(),
            material_port=_UnusedMaterial(),
        )
        with mock.patch(
            "trade_system.theory_paper_v2.infrastructure.v32_local_analysis_lane."
            "admit_fresh_v32_source_to_cycle",
            side_effect=_SimulatedProcessCrash(),
        ):
            with self.assertRaises(_SimulatedProcessCrash):
                lane.prepare_cycle_source(
                    run_id=run_id,
                    cycle_index=1,
                    supervisor_checkpoint=before,
                )
        self.assertEqual(transport.calls, 1)
        with mock.patch(
            "trade_system.theory_paper_v2.infrastructure.v32_local_analysis_lane."
            "compose_and_persist_v32_durable_source_replay_receipt",
            side_effect=_SimulatedProcessCrash(),
        ):
            with self.assertRaises(_SimulatedProcessCrash):
                lane.prepare_cycle_source(
                    run_id=run_id,
                    cycle_index=1,
                    supervisor_checkpoint=before,
                )
        self.assertEqual(transport.calls, 1)
        prepared_result = lane.prepare_cycle_source(
            run_id=run_id,
            cycle_index=1,
            supervisor_checkpoint=before,
        )
        self.assertEqual(prepared_result["preparation_status"], "SOURCE_READY")
        self.assertEqual(
            prepared_result["internal_append_only_substages"],
            ["SOURCE_REPLAY_SEALED"],
        )
        self.assertEqual(transport.calls, 1)
        prepared = lane.load_durable_prepared_source(
            run_id=run_id,
            cycle_index=1,
            supervisor_checkpoint=before,
        )
        self.assertEqual(prepared["source_cutoff_at"], decision)
        qualified = verify_durable_v32_public_source_qualification(
            store=source,
            qualification_id=qid,
            active_authority=authority,
        )
        gaps = build_v32_required_data_gap_escalations_v1(
            public_market_analysis_bundle=qualified.public_market_analysis_bundle
        )
        expected_unknown_components = {
            row["component_id"]
            for row in qualified.public_market_analysis_bundle[
                "request_raw_bindings"
            ]
            if row["status"] == "UNKNOWN"
        }
        expected_unknown_datums = {
            row["datum_id"]
            for row in qualified.public_market_analysis_bundle["datums"]
            if row["status"] == "UNKNOWN"
        }
        expected_unknown_axes = {
            row["axis_id"]
            for row in qualified.public_market_analysis_bundle[
                "axis_source_evidence"
            ]
            if row["status"] == "UNKNOWN"
        }
        self.assertEqual(
            len(gaps),
            len(expected_unknown_components)
            + len(expected_unknown_datums)
            + len(expected_unknown_axes),
        )
        self.assertTrue(gaps)
        self.assertTrue(all(row["objective_status"] == "UNKNOWN" for row in gaps))
        self.assertTrue(
            all(row["future_cycle_readmission_required"] is True for row in gaps)
        )
        axis_gaps = {
            row["request"]["field_path"].split(".", 1)[1]: row
            for row in gaps
            if row["request"]["field_path"].startswith("axis_source_evidence.")
        }
        self.assertEqual(set(axis_gaps), expected_unknown_axes)
        attention = axis_gaps["ATTENTION_AND_AUDIENCE_RESPONSE"]
        self.assertEqual(
            attention["error_code"], "MANUAL_PUBLIC_SOURCE_NOT_PREQUALIFIED"
        )
        self.assertTrue(
            all(
                source["source_kind"].startswith("OFFICIAL_")
                for row in axis_gaps.values()
                for source in row["allowed_official_public_sources"]
            )
        )
        lane.advance_analysis(
            permit=permit,
            supervisor_checkpoint_before_permit=before,
            supervisor_open_checkpoint=opened,
        )
        self.assertEqual(transport.calls, 1)


if __name__ == "__main__":
    unittest.main()
