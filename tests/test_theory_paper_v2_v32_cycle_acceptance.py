from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from tests import test_theory_paper_v2_v32_agent_lifecycle as lifecycle_fixture
from tests import test_theory_paper_v2_v32_agent_semantic_compiler as semantic_fixture
from trade_system.theory_paper_v2.application import (
    v32_cycle_acceptance as cycle_acceptance_runtime,
)
from trade_system.theory_paper_v2.application.v32_cycle_acceptance import (
    COMPONENT_SPECS,
    DIGEST_FIELD,
    V32CycleAcceptanceError,
    build_v32_analysis_cycle_acceptance_receipt_v1,
    verify_v32_analysis_cycle_acceptance_receipt_v1,
)
from trade_system.theory_paper_v2.application.v32_action_plan_continuity import (
    compose_v32_action_plan_continuity_v1,
)
from trade_system.theory_paper_v2.application.v32_authorized_revision_orchestration import (
    build_v32_authorized_revision_cycle_registry_v1,
)
from trade_system.theory_paper_v2.application.v32_dynamic_state_continuity import (
    compose_v32_dynamic_state_continuity_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_evidence_verifier import (
    V32InfrastructurePublicEvidenceVerifier,
)
from trade_system.theory_paper_v2.infrastructure import (
    v32_public_market_graph_projection as graph_projection_runtime,
)
from trade_system.theory_paper_v2.infrastructure.v32_shadow_decision_verifier import (
    V32InfrastructureShadowDecisionVerifier,
)
from trade_system.theory_paper_v2.infrastructure.v32_shadow_policy_adapter import (
    build_v32_replayable_shadow_decision_bundle_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    AGENT_CONSUMPTION_DIGEST_FIELD,
    COMMIT_ENVELOPE_DIGEST_FIELD,
    COMMIT_ENVELOPE_SCHEMA_ID,
    build_v32_two_stage_commit_envelope_v1,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD as CONTEXT_MANIFEST_DIGEST_FIELD,
    MANIFEST_SCHEMA_ID as CONTEXT_MANIFEST_SCHEMA_ID,
    SELECTION_DIGEST_FIELD as CONTEXT_SELECTION_DIGEST_FIELD,
    SELECTION_SCHEMA_ID as CONTEXT_SELECTION_SCHEMA_ID,
    SHARD_DIGEST_FIELD as CONTEXT_SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID as CONTEXT_SHARD_SCHEMA_ID,
    build_v32_context_compaction_bundle_v1,
    build_v32_context_shard_selection_v1,
)
from trade_system.theory_paper_v2.domain.v32_environment_capability import (
    CAPABILITY_CATEGORIES,
    DIGEST_FIELD as ENVIRONMENT_DIGEST_FIELD,
    SCHEMA_ID as ENVIRONMENT_SCHEMA_ID,
    build_v32_environment_capability_profile_v1,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID,
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
)
from trade_system.theory_paper_v2.domain.v32_timeframe_cache import (
    V32TimeframeCacheError,
    build_v32_context_frame_v1,
    build_v32_timeframe_context_state_v1,
    verify_v32_timeframe_context_state_v1,
    verify_v32_timeframe_production_policy_v1,
)


def _binding(name: str, document: dict, schema_id: str, digest_field: str) -> dict:
    return lifecycle_fixture._embedded(
        f"acceptance/{name}", document, schema_id, digest_field
    )


def _resign_timeframe_frame(
    state: dict, *, role: str, changes: dict[str, object]
) -> dict:
    original = next(row for row in state["frames"] if row["role"] == role)
    values = {
        key: deepcopy(original[key])
        for key in (
            "frame_id",
            "role",
            "update_mode",
            "created_at",
            "as_of",
            "available_at",
            "expires_at",
            "payload_digest",
            "source_refs",
            "dependency_groups",
            "invalidation_event_types",
        )
    }
    values.update(changes)
    rebuilt = build_v32_context_frame_v1(
        **values,
        previous_frame=None,
        decision_time=state["decision_time"],
    )
    frames = [
        rebuilt if row["role"] == role else deepcopy(row)
        for row in state["frames"]
    ]
    return build_v32_timeframe_context_state_v1(
        run_id=state["run_id"],
        cycle_index=state["cycle_index"],
        decision_time=state["decision_time"],
        state_mode=state["state_mode"],
        previous_state=None,
        frames=frames,
        observed_invalidation_events=state["observed_invalidation_events"],
    )


def _context_package(*, stage: str, run_id: str, packet: dict) -> dict:
    packet_digest_field = (
        "proposal_canonical_packet_digest"
        if stage == "proposal"
        else "selection_canonical_packet_digest"
    )
    packet_binding = _binding(
        f"revision/{stage}-original",
        packet,
        packet["schema_id"],
        packet_digest_field,
    )
    # Context compaction owns exhaustive packet member replay in its own suite.
    # The acceptance fixture needs only a valid revision-registry contract, so
    # compact a small identity reference instead of recursively fragmenting the
    # same multi-megabyte packet a second time.
    context_reference = self_digest(
        {
            "schema_id": "theory_paper_v32_cycle_context_reference_v1",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": packet["cycle_index"],
            "phase": stage.upper(),
            "canonical_packet_binding": packet_binding,
        },
        "cycle_context_reference_digest",
    )
    source_binding = _binding(
        f"revision/{stage}-reference",
        context_reference,
        context_reference["schema_id"],
        "cycle_context_reference_digest",
    )
    compacted = build_v32_context_compaction_bundle_v1(
        run_id=run_id,
        cycle_index=1,
        created_at="2026-08-07T00:17:41Z",
        source_artifacts=[
            {
                "artifact_binding": source_binding,
                "canonical_bytes": len(canonical_bytes(context_reference)),
            }
        ],
        original_documents=[context_reference],
        max_shard_canonical_bytes=262_144,
        max_manifest_canonical_bytes=1_048_576,
    )
    manifest = compacted["manifest"]
    shards = compacted["shards"]
    manifest_binding = _binding(
        f"revision/{stage}-manifest",
        manifest,
        CONTEXT_MANIFEST_SCHEMA_ID,
        CONTEXT_MANIFEST_DIGEST_FIELD,
    )
    selection = build_v32_context_shard_selection_v1(
        manifest=manifest,
        manifest_binding=manifest_binding,
        shards=shards,
        original_documents=[context_reference],
        caller_required_member_ids=[],
        selected_at="2026-08-07T00:17:42Z",
        max_agent_context_canonical_bytes=4 * 1024 * 1024,
    )
    return {
        "manifest": manifest,
        "shards": shards,
        "original_documents": [context_reference],
        "selection": selection,
        "manifest_binding": manifest_binding,
        "shard_bindings": [
            _binding(
                f"revision/{stage}-shard-{index:04d}",
                shard,
                CONTEXT_SHARD_SCHEMA_ID,
                CONTEXT_SHARD_DIGEST_FIELD,
            )
            for index, shard in enumerate(shards)
        ],
        "selection_binding": _binding(
            f"revision/{stage}-selection",
            selection,
            CONTEXT_SELECTION_SCHEMA_ID,
            CONTEXT_SELECTION_DIGEST_FIELD,
        ),
    }


def _revision_registry(*, semantic: dict, run_id: str) -> dict:
    environment = build_v32_environment_capability_profile_v1(
        profile_id="v32-test-environment",
        run_scope_id=run_id,
        frozen_at="2026-08-07T00:17:40Z",
        capabilities=[
            {
                "category": category,
                "status": "AVAILABLE",
                "observed_value": "测试中由本地确定性夹具提供",
                "limit": "仅证明合同接线，不证明真实外部资格",
                "evidence_refs": [f"test:{category.lower()}"],
                "claim_ceiling": "LOCAL_CONTRACT_TEST_ONLY",
            }
            for category in CAPABILITY_CATEGORIES
        ],
        localization_adapters=[],
    )
    return build_v32_authorized_revision_cycle_registry_v1(
        registry_id="v32-test-cycle-registry",
        run_id=run_id,
        cycle_index=1,
        created_at="2026-08-07T00:17:45Z",
        proposal_context=_context_package(
            stage="proposal", run_id=run_id, packet=semantic["proposal_packet"]
        ),
        selection_context=_context_package(
            stage="selection", run_id=run_id, packet=semantic["selection_packet"]
        ),
        unknown_tracks=[],
        data_gap_entries=[],
        manual_evidence_entries=[],
        environment_conformance={
            "profile": environment,
            "profile_binding": _binding(
                "revision/environment",
                environment,
                ENVIRONMENT_SCHEMA_ID,
                ENVIRONMENT_DIGEST_FIELD,
            ),
        },
        recovery_traces=[],
    )


def _build_acceptance_fixture(build_kwargs: dict) -> tuple[dict, int]:
    """Build once and retain the integration assertion made during setup."""

    original_builder = (
        graph_projection_runtime._build_evidence_dependency_closure
    )
    with patch.object(
        graph_projection_runtime,
        "_build_evidence_dependency_closure",
        wraps=original_builder,
    ) as projection_builder:
        receipt = build_v32_analysis_cycle_acceptance_receipt_v1(
            **build_kwargs
        )
    return receipt, projection_builder.call_count


def _fixture() -> dict:
    semantic = semantic_fixture._full_fixture(
        max_wait_cycles_before_review=8,
        max_inactivity_seconds=7200,
    )
    proposal_packet = semantic["proposal_packet"]
    run_id = proposal_packet["run_id"]
    decision_time = proposal_packet["decision_time"]
    support_documents = proposal_packet["support_documents"]
    support_bindings = proposal_packet["support_bindings"]
    authority_projection = support_documents["active_authority_projection"]
    # _full_fixture() has already built and cached this exact immutable market
    # chain.  Calling its public test helper again deep-copies the largest
    # fixture even though this class only replaces top-level component entries.
    market_cache_key = (
        run_id,
        1,
        authority_projection["active_authority_projection_digest"],
    )
    cached_market = lifecycle_fixture._FORMAL_MARKET_CHAIN_CACHE.get(
        market_cache_key
    )
    market = (
        dict(cached_market)
        if cached_market is not None
        else lifecycle_fixture._formal_market_chain(
            run_id=run_id,
            cycle=1,
            decision_time=decision_time,
            authority_projection=authority_projection,
        )
    )
    source = market["source_admission"]
    timeframe = support_documents["timeframe_context_state"]
    public_verifier = V32InfrastructurePublicEvidenceVerifier()
    shadow_verifier = V32InfrastructureShadowDecisionVerifier()

    checkpoint = build_v32_tick_supervisor_checkpoint(
        run_id=run_id,
        experiment_contract_digest=source["experiment_contract_digest"],
        active_authority_digest=source["governing_authority_digest"],
        research_checkpoint_digest="c" * 64,
        outcome_checkpoint_digest="d" * 64,
        timeframe_cache_digest="e" * 64,
        created_at="2026-08-07T00:00:00Z",
    )
    permit = build_v32_analysis_tick_permit(
        checkpoint=checkpoint,
        schedule_sets=[],
        analysis_decision_at=decision_time,
        issued_at="2026-08-07T00:15:01Z",
        research_checkpoint_digest=checkpoint[
            "current_research_checkpoint_digest"
        ],
        outcome_checkpoint_digest=checkpoint[
            "current_outcome_checkpoint_digest"
        ],
        timeframe_cache_digest=checkpoint["current_timeframe_cache_digest"],
        prior_dynamic_state_digest=checkpoint["current_dynamic_state_digest"],
    )
    final_plan = semantic["selection_receipt"]["final_dynamic_action_plan"]
    current_state = semantic["proposal_receipt"][
        "compiled_dynamic_research_state"
    ]
    action_evaluation = semantic["proposal_receipt"]["sealed_action_evaluation"]
    availability_binding = _binding(
        "pit-availability",
        market["availability_registry"],
        *COMPONENT_SPECS["verified_pit_evidence_availability_registry"],
    )
    graph_registry_binding = _binding(
        "graph-registry",
        market["graph_registry"],
        *COMPONENT_SPECS["verified_graph_dependency_registry"],
    )
    state_continuity = compose_v32_dynamic_state_continuity_v1(
        public_evidence_verifier=public_verifier,
        current_state=current_state,
        durable_previous_state=None,
        durable_previous_state_digest=None,
        verified_pit_evidence_registry=market["pit_registry"],
        verified_pit_evidence_registry_digest=market["pit_registry"][
            "pit_evidence_registry_digest"
        ],
        verified_public_market_analysis_bundle=market["analysis_bundle"],
        verified_pit_evidence_availability_registry=market[
            "availability_registry"
        ],
        verified_pit_evidence_availability_registry_digest=market[
            "availability_registry"
        ]["pit_evidence_availability_registry_digest"],
        durable_previous_pit_evidence_availability_registry=None,
        durable_previous_pit_evidence_availability_registry_digest=None,
        verified_graph_dependency_registry=market["graph_registry"],
        verified_graph_dependency_registry_digest=market["graph_registry"][
            "graph_dependency_registry_digest"
        ],
    )
    action_continuity = compose_v32_action_plan_continuity_v1(
        current_dynamic_state=current_state,
        current_action_plan=final_plan,
        durable_previous_dynamic_state=None,
        durable_previous_dynamic_state_digest=None,
        durable_previous_action_plan=None,
        durable_previous_action_plan_digest=None,
    )
    revision_registry = _revision_registry(semantic=semantic, run_id=run_id)
    schedule = build_v32_outcome_schedule_set(
        run_id=run_id,
        decision_id="decision:v32:0001",
        cycle_index=1,
        decision_time=semantic["selection_receipt"]["compiled_at"],
        scheduled_at="2026-08-07T00:17:35Z",
        sealed_decision_digest=final_plan["dynamic_action_plan_digest"],
        evaluation_contract_digest=support_documents["experiment_contract"]
        ["support_bindings"]["evaluation_contract_digest"],
    )
    final_plan_binding = _binding(
        "final-plan",
        final_plan,
        *COMPONENT_SPECS["final_dynamic_action_plan"],
    )
    schedule_binding = _binding(
        "outcome-schedule",
        schedule,
        SCHEDULE_SET_SCHEMA_ID,
        SCHEDULE_SET_DIGEST_FIELD,
    )
    shadow_bundle = build_v32_replayable_shadow_decision_bundle_v1(
        bundle_id="shadow-bundle:v32:0001",
        decision_id=schedule["decision_id"],
        created_at="2026-08-07T00:17:35Z",
        public_market_analysis_bundle=market["analysis_bundle"],
        public_market_analysis_bundle_binding=market["analysis_bundle_binding"],
        pit_evidence_registry=market["pit_registry"],
        pit_evidence_registry_binding=market["pit_registry_binding"],
        sealed_action_evaluation=action_evaluation,
        sealed_action_evaluation_binding=semantic["evaluation_binding"],
        dynamic_research_state=current_state,
        selected_plan=final_plan,
        selected_plan_binding=final_plan_binding,
    )
    commit = build_v32_two_stage_commit_envelope_v1(
        proposal_input_context=semantic["proposal_context"],
        proposal_delivery=semantic["proposal_delivery"],
        proposal_consumption=semantic["proposal_consumption"],
        selection_input_context=semantic["selection_context"],
        selection_delivery=semantic["selection_delivery"],
        selection_consumption=semantic["selection_consumption"],
        final_dynamic_action_plan=final_plan,
        final_dynamic_action_plan_binding=final_plan_binding,
        outcome_schedule_set=schedule,
        outcome_schedule_set_binding=schedule_binding,
        sealed_at="2026-08-07T00:17:40Z",
        previous_commit_envelope_digest=None,
    )

    components = {
        "analysis_tick_permit": permit,
        "active_authority_projection": authority_projection,
        "cycle_source_admission": source,
        "public_market_analysis_bundle": market["analysis_bundle"],
        "public_market_graph_projection": market["graph_projection"],
        "pit_evidence_registry": market["pit_registry"],
        "verified_graph_dependency_registry": market["graph_registry"],
        "durable_source_replay_receipt": market["source_replay_receipt"],
        "verified_pit_evidence_availability_registry": market[
            "availability_registry"
        ],
        "agent_market_graph_view": market["market_view"],
        "current_timeframe_context_state": timeframe,
        "proposal_input_context": semantic["proposal_context"],
        "proposal_delivery": semantic["proposal_delivery"],
        "proposal_consumption": semantic["proposal_consumption"],
        "proposal_semantic_compile_receipt": semantic["proposal_receipt"],
        "compiled_dynamic_research_state": current_state,
        "sealed_action_evaluation": action_evaluation,
        "replayable_shadow_decision_bundle": shadow_bundle,
        "dynamic_state_continuity_receipt": state_continuity,
        "selection_input_context": semantic["selection_context"],
        "selection_delivery": semantic["selection_delivery"],
        "selection_consumption": semantic["selection_consumption"],
        "selection_semantic_compile_receipt": semantic["selection_receipt"],
        "final_dynamic_action_plan": final_plan,
        "action_plan_continuity_receipt": action_continuity,
        "authorized_revision_cycle_registry": revision_registry,
        "two_stage_commit_envelope": commit,
        "outcome_schedule_set": schedule,
    }
    bindings = {
        role: _binding(role, document, *COMPONENT_SPECS[role])
        for role, document in components.items()
    }
    bindings.update(
        {
            "active_authority_projection": support_bindings[
                "active_authority_projection"
            ],
            "cycle_source_admission": support_bindings[
                "cycle_source_admission"
            ],
            "public_market_analysis_bundle": market[
                "analysis_bundle_binding"
            ],
            "pit_evidence_registry": market["pit_registry_binding"],
            "durable_source_replay_receipt": market[
                "source_replay_receipt_binding"
            ],
            "verified_pit_evidence_availability_registry": (
                availability_binding
            ),
            "verified_graph_dependency_registry": graph_registry_binding,
            "agent_market_graph_view": support_bindings[
                "agent_market_graph_view"
            ],
            "current_timeframe_context_state": support_bindings[
                "timeframe_context_state"
            ],
            "proposal_input_context": semantic["proposal_context_binding"],
            "proposal_delivery": semantic["proposal_delivery_binding"],
            "proposal_consumption": semantic["proposal_consumption_binding"],
            "compiled_dynamic_research_state": semantic["dynamic_binding"],
            "sealed_action_evaluation": semantic["evaluation_binding"],
            "selection_input_context": semantic["selection_context_binding"],
            "selection_delivery": semantic["selection_delivery_binding"],
            "selection_consumption": semantic["selection_consumption_binding"],
            "final_dynamic_action_plan": final_plan_binding,
            "outcome_schedule_set": schedule_binding,
        }
    )
    checkpoint_binding = _binding(
        "permit-checkpoint",
        checkpoint,
        CHECKPOINT_SCHEMA_ID,
        CHECKPOINT_DIGEST_FIELD,
    )
    build_kwargs = {
        "public_evidence_verifier": public_verifier,
        "shadow_decision_verifier": shadow_verifier,
        "components": components,
        "component_bindings": bindings,
        "permit_checkpoint": checkpoint,
        "permit_checkpoint_binding": checkpoint_binding,
        "prior_outcome_schedule_sets": [],
        "prior_outcome_schedule_set_bindings": [],
        "previous_timeframe_context_state": None,
        "previous_timeframe_context_state_binding": None,
        "previous_public_market_graph_projection": None,
        "previous_public_market_graph_projection_binding": None,
        "previous_pit_evidence_availability_registry": None,
        "previous_pit_evidence_availability_registry_binding": None,
        "previous_accepted_receipt": None,
        "previous_accepted_receipt_binding": None,
        "accepted_at": "2026-08-07T00:17:50Z",
    }
    (
        receipt,
        acceptance_projection_closure_build_count,
    ) = _build_acceptance_fixture(build_kwargs)
    return {**locals(), "build_kwargs": build_kwargs, "receipt": receipt}


class V32CycleAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = _fixture()

    def _kwargs(self) -> dict:
        kwargs = dict(self.fx["build_kwargs"])
        kwargs["components"] = dict(kwargs["components"])
        kwargs["component_bindings"] = dict(kwargs["component_bindings"])
        return kwargs

    def test_full_cycle_replays_and_accepts_exactly_once(self) -> None:
        receipt = self.fx["receipt"]
        verify_kwargs = dict(self.fx["build_kwargs"])
        verify_kwargs.pop("accepted_at")
        # Setup has already exercised the complete owning replay.  This test
        # separately checks the verifier wrapper without replaying the same 28
        # components a second time.
        with patch.object(
            cycle_acceptance_runtime,
            "build_v32_analysis_cycle_acceptance_receipt_v1",
            return_value=receipt,
        ) as rebuild:
            self.assertEqual(
                verify_v32_analysis_cycle_acceptance_receipt_v1(
                    receipt, **verify_kwargs
                ),
                receipt[DIGEST_FIELD],
            )
        rebuild.assert_called_once()
        self.assertEqual(receipt["cycle_index"], 1)
        self.assertEqual(receipt["proposal_attempt_count"], 1)
        self.assertEqual(receipt["selection_attempt_count"], 1)
        self.assertFalse(receipt["current_outcome_present"])
        self.assertFalse(receipt["executable"])
        self.assertEqual(len(COMPONENT_SPECS), 28)
        self.assertEqual(
            receipt["authorized_revision_cycle_registry_digest"],
            self.fx["revision_registry"][
                "authorized_revision_cycle_registry_digest"
            ],
        )
        shadow = self.fx["shadow_bundle"]
        self.assertEqual(len(shadow["arms"]), 6)
        self.assertFalse(shadow["outcome_values_present"])
        self.assertEqual(
            receipt["shadow_decision_bundle_digest"],
            shadow["shadow_decision_bundle_digest"],
        )
        self.assertEqual(
            receipt["dynamic_state_continuity_receipt_digest"],
            self.fx["state_continuity"][
                "dynamic_state_continuity_receipt_digest"
            ],
        )
        self.assertEqual(
            receipt["action_plan_continuity_receipt_digest"],
            self.fx["action_continuity"][
                "action_plan_continuity_receipt_digest"
            ],
        )
        contract = self.fx["proposal_packet"]["support_documents"][
            "experiment_contract"
        ]
        watchdog = self.fx["final_plan"]["inactivity_opportunity_watchdog"]
        self.assertEqual(
            watchdog["max_wait_cycles_before_review"],
            contract["inactivity_policy"]["review_after_consecutive_cycles"],
        )
        self.assertEqual(
            watchdog["max_inactivity_seconds"],
            contract["inactivity_policy"]["review_after_seconds"],
        )

    def test_acceptance_rebuilds_current_projection_closure_only_once(self) -> None:
        self.assertEqual(
            self.fx["acceptance_projection_closure_build_count"], 1
        )

    def test_formal_acceptance_rejects_resigned_frame_policy_drift(self) -> None:
        baseline = self.fx["timeframe"]
        bundle = self.fx["market"]["analysis_bundle"]
        # The complete role x mutation matrix belongs to timeframe_cache.py.
        # Acceptance needs one representative case to prove that owner error
        # is propagated through the integration boundary.
        role = "STRATEGIC_CONTEXT"
        forged = _resign_timeframe_frame(
            baseline,
            role=role,
            changes={"expires_at": "2026-09-07T00:15:00Z"},
        )
        verify_v32_timeframe_context_state_v1(forged)
        with self.assertRaisesRegex(
            V32TimeframeCacheError,
            f"PRODUCTION_FRAME_POLICY_MISMATCH:{role}",
        ):
            verify_v32_timeframe_production_policy_v1(
                timeframe_context_state=forged,
                public_market_analysis_bundle=bundle,
            )

        kwargs = self._kwargs()
        kwargs["components"]["current_timeframe_context_state"] = forged
        kwargs["component_bindings"]["current_timeframe_context_state"] = (
            _binding(
                "forged-timeframe-strategic-context-long-ttl",
                forged,
                *COMPONENT_SPECS["current_timeframe_context_state"],
            )
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID",
        ) as captured:
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)
        self.assertIn(
            f"PRODUCTION_FRAME_POLICY_MISMATCH:{role}",
            str(captured.exception.__cause__),
        )

    def test_schedule_is_exact_three_horizon_and_not_current_outcome(self) -> None:
        self.assertEqual(
            [row["horizon"] for row in self.fx["schedule"]["schedules"]],
            ["15M", "1H", "4H"],
        )
        self.assertLess(
            self.fx["receipt"]["accepted_at"],
            self.fx["schedule"]["schedules"][0]["outcome_not_before"],
        )

    def test_binding_physical_sha_is_recomputed_from_real_document(self) -> None:
        kwargs = self._kwargs()
        kwargs["component_bindings"]["proposal_semantic_compile_receipt"] = dict(
            kwargs["component_bindings"]["proposal_semantic_compile_receipt"]
        )
        kwargs["component_bindings"]["proposal_semantic_compile_receipt"][
            "physical_sha256"
        ] = "f" * 64
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_BINDING_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_compiled_state_is_an_independent_physical_component(self) -> None:
        kwargs = self._kwargs()
        kwargs["component_bindings"]["compiled_dynamic_research_state"] = dict(
            kwargs["component_bindings"]["compiled_dynamic_research_state"]
        )
        kwargs["component_bindings"]["compiled_dynamic_research_state"][
            "physical_sha256"
        ] = "f" * 64
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_BINDING_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_continuity_receipt_is_replayed_not_trusted(self) -> None:
        kwargs = self._kwargs()
        continuity = deepcopy(
            kwargs["components"]["dynamic_state_continuity_receipt"]
        )
        continuity["new_hypothesis_ids"] = []
        continuity = self_digest(
            continuity, "dynamic_state_continuity_receipt_digest"
        )
        kwargs["components"]["dynamic_state_continuity_receipt"] = continuity
        kwargs["component_bindings"]["dynamic_state_continuity_receipt"] = (
            _binding(
                "laundered-state-continuity",
                continuity,
                *COMPONENT_SPECS["dynamic_state_continuity_receipt"],
            )
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_authorized_revision_registry_is_required_and_replayed(self) -> None:
        kwargs = self._kwargs()
        registry = deepcopy(
            kwargs["components"]["authorized_revision_cycle_registry"]
        )
        registry["nested_artifacts_verified_by_owning_contracts"] = False
        registry = self_digest(
            registry, "authorized_revision_cycle_registry_digest"
        )
        kwargs["components"]["authorized_revision_cycle_registry"] = registry
        kwargs["component_bindings"]["authorized_revision_cycle_registry"] = (
            _binding(
                "laundered-revision-registry",
                registry,
                *COMPONENT_SPECS["authorized_revision_cycle_registry"],
            )
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_replay_support_physical_sha_is_not_trusted(self) -> None:
        kwargs = self._kwargs()
        kwargs["permit_checkpoint_binding"] = dict(
            kwargs["permit_checkpoint_binding"]
        )
        kwargs["permit_checkpoint_binding"]["physical_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_REPLAY_SUPPORT_BINDING_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_v31_source_admission_cannot_impersonate_v32(self) -> None:
        kwargs = self._kwargs()
        source = deepcopy(kwargs["components"]["cycle_source_admission"])
        source["schema_id"] = "theory_paper_v31_cycle_source_admission_v1"
        source = self_digest(source, "cycle_source_admission_digest")
        kwargs["components"]["cycle_source_admission"] = source
        kwargs["component_bindings"]["cycle_source_admission"] = _binding(
            "v31-source",
            source,
            source["schema_id"],
            "cycle_source_admission_digest",
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_semantic_compile_receipt_laundering_fails_replay(self) -> None:
        kwargs = self._kwargs()
        semantic = deepcopy(
            kwargs["components"]["selection_semantic_compile_receipt"]
        )
        semantic["selected_candidate_id"] = "invented-candidate"
        semantic = self_digest(
            semantic, "selection_semantic_compile_receipt_digest"
        )
        kwargs["components"]["selection_semantic_compile_receipt"] = semantic
        kwargs["component_bindings"]["selection_semantic_compile_receipt"] = _binding(
            "laundered-selection",
            semantic,
            *COMPONENT_SPECS["selection_semantic_compile_receipt"],
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_final_plan_must_be_exact_selected_variant(self) -> None:
        kwargs = self._kwargs()
        other = next(
            row["dynamic_action_plan"]
            for row in self.fx["semantic"]["proposal_receipt"][
                "sealed_plan_variants"
            ]
            if row["candidate_id"] == "open-long"
        )
        kwargs["components"]["final_dynamic_action_plan"] = other
        kwargs["component_bindings"]["final_dynamic_action_plan"] = _binding(
            "wrong-final",
            other,
            *COMPONENT_SPECS["final_dynamic_action_plan"],
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_store_local_locator_can_change_without_identity_drift(self) -> None:
        kwargs = self._kwargs()
        kwargs["component_bindings"]["proposal_input_context"] = dict(
            kwargs["component_bindings"]["proposal_input_context"]
        )
        proposal_binding = kwargs["component_bindings"]["proposal_input_context"]
        proposal_binding["relative_ref"] = "alternate/proposal-context.json"
        receipt = build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)
        self.assertEqual(
            receipt["component_bindings"]["proposal_input_context"],
            proposal_binding,
        )

    def test_genesis_rejects_previous_receipt_or_timeframe(self) -> None:
        kwargs = self._kwargs()
        kwargs["previous_accepted_receipt"] = self.fx["receipt"]
        kwargs["previous_accepted_receipt_binding"] = _binding(
            "wrong-genesis-previous",
            self.fx["receipt"],
            "theory_paper_v32_analysis_cycle_acceptance_receipt_v1",
            DIGEST_FIELD,
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)

    def test_receipt_self_digest_laundering_fails_reconstruction(self) -> None:
        receipt = deepcopy(self.fx["receipt"])
        receipt["current_outcome_present"] = True
        receipt = self_digest(receipt, DIGEST_FIELD)
        verify_kwargs = dict(self.fx["build_kwargs"])
        verify_kwargs.pop("accepted_at")
        with patch.object(
            cycle_acceptance_runtime,
            "build_v32_analysis_cycle_acceptance_receipt_v1",
            return_value=self.fx["receipt"],
        ) as rebuild, self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_RECEIPT_RECONSTRUCTION_MISMATCH",
        ):
            verify_v32_analysis_cycle_acceptance_receipt_v1(
                receipt, **verify_kwargs
            )
        rebuild.assert_called_once()

    def test_wrong_selection_consumption_breaks_acceptance(self) -> None:
        kwargs = self._kwargs()
        consumption = deepcopy(kwargs["components"]["selection_consumption"])
        consumption["payload_sha256"] = "f" * 64
        consumption = self_digest(consumption, AGENT_CONSUMPTION_DIGEST_FIELD)
        kwargs["components"]["selection_consumption"] = consumption
        kwargs["component_bindings"]["selection_consumption"] = _binding(
            "wrong-selection-consumption",
            consumption,
            *COMPONENT_SPECS["selection_consumption"],
        )
        with self.assertRaisesRegex(
            V32CycleAcceptanceError,
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID",
        ):
            build_v32_analysis_cycle_acceptance_receipt_v1(**kwargs)


if __name__ == "__main__":
    unittest.main()
