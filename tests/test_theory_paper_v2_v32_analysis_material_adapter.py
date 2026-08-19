from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests import test_theory_paper_v2_v32_agent_lifecycle as lifecycle_fixture
from tests.test_theory_paper_v2_v32_current_research_authority import (
    LOADER_MODULE,
    TARGET_RUN,
    build_fixture,
    fixture_capability_verifiers,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    PROPOSAL_PACKET_DIGEST_FIELD,
    PROPOSAL_PACKET_SCHEMA_ID,
    build_v32_agent_input_context_v1,
    verify_v32_proposal_canonical_packet_v1,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    build_v32_active_authority_projection,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
    verify_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_current_research import (
    load_v32_current_research_authority,
)
from trade_system.theory_paper_v2.infrastructure.v32_analysis_material_adapter import (
    LocalV32AnalysisMaterialAdapter,
    LocalV32NoRevisionInputMaterialReader,
    V32AnalysisMaterialAdapterError,
    read_current_v32_strategy_agent_request_v1,
)


from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
)
from trade_system.theory_paper_v2.infrastructure.v32_local_analysis_lane import (
    build_v32_required_data_gap_escalations_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    PIT_DATUM_DIGEST_FIELD,
)


_MANIFEST_TO_AGENT = {
    "association_preregistration_digest": "association_preregistration",
    "authorized_revision_support_bundle_digest": (
        "authorized_revision_support_bundle"
    ),
    "clock_policy_digest": "clock_and_tick_policy",
    "evaluation_contract_digest": "evaluation_contract",
    "outcome_adapter_contract_digest": "outcome_adapter_contract",
    "recovery_supervision_policy_digest": "recovery_supervision_policy",
    "twelve_axis_source_registry_digest": "twelve_axis_source_registry",
}


def _binding(relative_ref: str, document: dict) -> dict[str, str]:
    digest_fields = [key for key in document if key.endswith("_digest")]
    digest_field = digest_fields[-1]
    return {
        "relative_ref": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": verify_self_digest(document, digest_field),
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }


class V32RevisionInputReaderStateTests(unittest.TestCase):
    permit = {
        "permit_kind": "ANALYSIS_TICK",
        "run_id": TARGET_RUN,
        "analysis_cycle_index": 1,
        "analysis_decision_at": "2026-08-07T00:15:00Z",
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_access": False,
        "order_submission": False,
    }
    proposal = {"run_id": TARGET_RUN, "cycle_index": 1}
    selection = {
        "run_id": TARGET_RUN,
        "cycle_index": 1,
        "prepared_at": "2026-08-07T00:15:45Z",
    }

    def _adapter(self, *, reader=...):
        kwargs = {}
        if reader is not ...:
            kwargs = {
                "strategy_revision_material_reader": reader,
                "strategy_revision_observation_clock": (
                    lambda: "2026-08-07T00:16:00Z"
                ),
            }
        with patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter._verify_full_loader_projection",
            return_value=(TARGET_RUN, TARGET_RUN, "TARGET", {}),
        ), patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter._verify_static_supports",
            return_value=(
                {},
                {},
                {"environment_capability_profile": {}},
                {"environment_capability_profile": {}},
            ),
        ):
            return LocalV32AnalysisMaterialAdapter(
                verified_target_authority_bundle={},
                active_authority_projection={},
                theory_semantic_document={},
                theory_semantic_document_binding={},
                frozen_support_documents={},
                frozen_support_bindings={},
                **kwargs,
            )

    def _build(self, adapter):
        registry = self_digest(
            {
                "schema_id": "test_v32_authorized_revision_registry_v2",
                "run_id": TARGET_RUN,
                "cycle_index": 1,
            },
            "authorized_revision_cycle_registry_digest",
        )
        with patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "verify_v32_proposal_canonical_packet_v1"
        ), patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "verify_v32_selection_canonical_packet_v1"
        ), patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "build_v32_authorized_revision_cycle_registry_v1",
            return_value=registry,
        ) as build_registry, patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "verify_v32_authorized_revision_cycle_registry_v1"
        ):
            material = adapter.build_authorized_revision_cycle_registry(
                permit=self.permit,
                proposal_packet=self.proposal,
                proposal_context_package=None,
                selection_packet=self.selection,
                selection_context_package=None,
                required_data_gap_escalations=[],
            )
        return material, build_registry.call_args.kwargs

    def test_explicit_local_no_input_is_not_silent_empty(self):
        material, built = self._build(
            self._adapter(reader=LocalV32NoRevisionInputMaterialReader())
        )
        state = material["revision_input_state"]
        self.assertEqual("NO_REVISION_INPUT", state["state"])
        self.assertFalse(state["zero_imputed"])
        self.assertEqual("2026-08-07T00:16:00Z", state["observed_at"])
        self.assertEqual(state, built["revision_input_state"])
        self.assertEqual("2026-08-07T00:16:00Z", built["created_at"])

    def test_omitted_reader_is_rejected_at_revision_boundary(self):
        with self.assertRaisesRegex(
            V32AnalysisMaterialAdapterError,
            "V32_ANALYSIS_MATERIAL_REVISION_READER_REQUIRED",
        ):
            self._build(self._adapter())

    def test_reader_failure_becomes_typed_unknown_without_items(self):
        class FailingReader:
            reader_binding = {
                "reader_id": "TEST_FAILING_LOCAL_READER_V1",
                "reader_version": "1.0.0",
                "reader_kind": "LOCAL_TEST_READER",
                "configuration_digest": canonical_digest(
                    {"configured": True, "failure_mode": "READ_ERROR"}
                ),
            }

            def read_cycle_revision_material(self, **_):
                raise OSError("unavailable")

        material, _ = self._build(self._adapter(reader=FailingReader()))
        self.assertEqual(
            "UNKNOWN_READER_UNAVAILABLE",
            material["revision_input_state"]["state"],
        )
        self.assertEqual([], material["unknown_tracks"])
        self.assertEqual([], material["manual_evidence_entries"])
        self.assertEqual([], material["recovery_traces"])


class V32AnalysisMaterialAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = build_fixture(cls.root)
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=cls.fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=cls.fixture["legacy_failure"],
        ):
            cls.authority_bundle = load_v32_current_research_authority(
                cls.root,
                expected_run_id=TARGET_RUN,
                capability_verifiers=fixture_capability_verifiers(),
            )
        authority_binding = cls.fixture["target_authority_binding"]
        cls.active_projection = build_v32_active_authority_projection(
            run_id=TARGET_RUN,
            recorded_at="2026-08-07T00:13:00Z",
            experiment_contract_digest=cls.fixture["contract"][
                EXPERIMENT_CONTRACT_DIGEST_FIELD
            ],
            governing_authority_binding={
                "relative_ref": authority_binding["path"],
                **{
                    key: authority_binding[key]
                    for key in (
                        "schema_id",
                        "digest_field",
                        "semantic_digest",
                        "physical_sha256",
                    )
                },
            },
        )
        cls.support_documents = {
            _MANIFEST_TO_AGENT[key]: document
            for key, document in cls.fixture["support_documents"].items()
            if key in _MANIFEST_TO_AGENT
        }
        cls.support_bindings = {
            _MANIFEST_TO_AGENT[key]: binding
            for key, binding in cls.fixture[
                "support_document_bindings"
            ].items()
            if key in _MANIFEST_TO_AGENT
        }
        for name, binding in cls.fixture[
            "revision_component_bindings"
        ].items():
            cls.support_documents[name] = load_json_strict(
                cls.root / binding["relative_ref"]
            )
            cls.support_bindings[name] = binding
        cls.adapter = LocalV32AnalysisMaterialAdapter(
            verified_target_authority_bundle=cls.authority_bundle,
            active_authority_projection=cls.active_projection,
            theory_semantic_document=cls.fixture["theory_semantic_document"],
            theory_semantic_document_binding=cls.fixture[
                "theory_semantic_document_binding"
            ],
            frozen_support_documents=cls.support_documents,
            frozen_support_bindings=cls.support_bindings,
            strategy_revision_material_reader=(
                LocalV32NoRevisionInputMaterialReader()
            ),
            strategy_revision_observation_clock=(
                lambda: "2026-08-07T00:16:00Z"
            ),
        )
        cls.market = lifecycle_fixture._formal_market_chain(
            run_id=TARGET_RUN,
            cycle=1,
            decision_time="2026-08-07T00:15:00Z",
            authority_projection=cls.active_projection,
        )
        cls.permit = {
            "permit_kind": "ANALYSIS_TICK",
            "run_id": TARGET_RUN,
            "analysis_cycle_index": 1,
            "analysis_decision_at": "2026-08-07T00:15:00Z",
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_access": False,
            "order_submission": False,
        }
        cls.timeframe = cls.adapter.build_timeframe_context(
            permit=cls.permit,
            public_market_analysis_bundle=cls.market["analysis_bundle"],
            previous_timeframe_context=None,
        )
        current_artifacts = {
            "active_authority_projection": cls.active_projection,
            "timeframe_context_state": cls.timeframe,
            "agent_market_graph_view": cls.market["market_view"],
            "cycle_source_admission": cls.market["source_admission"],
        }
        current_bindings = {
            "active_authority_projection": _binding(
                "cycles/0001/active-authority-projection.json",
                cls.active_projection,
            ),
            "timeframe_context_state": _binding(
                "cycles/0001/timeframe-context.json", cls.timeframe
            ),
            "agent_market_graph_view": _binding(
                "cycles/0001/agent-market-graph-view.json",
                cls.market["market_view"],
            ),
            "cycle_source_admission": cls.market["source_admission_binding"],
        }
        empty_previous = {
            "dynamic_state": None,
            "action_plan": None,
            "timeframe_context": None,
        }
        cls.proposal = cls.adapter.build_proposal_packet(
            permit=cls.permit,
            active_authority_projection=cls.active_projection,
            current_artifacts=current_artifacts,
            current_bindings=current_bindings,
            previous_artifacts=empty_previous,
            previous_bindings=empty_previous,
            matured_outcome_receipts=[],
            matured_outcome_receipt_bindings=[],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_real_shaped_public_bundle_builds_complete_timeframe_and_proposal(self):
        self.assertEqual(
            self.timeframe["state_mode"], "FULL_CONTEXT"
        )
        self.assertEqual(
            [row["role"] for row in self.timeframe["frames"]],
            ["STRATEGIC_CONTEXT", "TACTICAL_DELTA", "TRIGGER"],
        )
        self.assertEqual(
            verify_v32_proposal_canonical_packet_v1(self.proposal),
            self.proposal[PROPOSAL_PACKET_DIGEST_FIELD],
        )
        self.assertEqual(
            self.proposal["authority_document"],
            self.authority_bundle["authority"],
        )
        self.assertEqual(
            self.proposal["matured_outcome_receipt_bindings"], []
        )
        self.assertFalse(self.proposal["executable"])

    def test_production_delta_carries_only_unchanged_strategic_semantics(self):
        permit = deepcopy(self.permit)
        permit["analysis_cycle_index"] = 2
        permit["analysis_decision_at"] = "2026-08-07T00:30:00Z"
        unchanged = deepcopy(self.market["analysis_bundle"])
        unchanged["qualification_id"] = "q-material-delta-0002"
        unchanged["cycle_index"] = 2
        unchanged = self_digest(unchanged, ANALYSIS_BUNDLE_DIGEST_FIELD)

        carried = self.adapter.build_timeframe_context(
            permit=permit,
            public_market_analysis_bundle=unchanged,
            previous_timeframe_context=self.timeframe,
        )
        self.assertEqual(
            {
                "STRATEGIC_CONTEXT": "CARRIED_FORWARD",
                "TACTICAL_DELTA": "REFRESHED",
                "TRIGGER": "REFRESHED",
            },
            {row["role"]: row["update_mode"] for row in carried["frames"]},
        )
        prior_strategic = next(
            row
            for row in self.timeframe["frames"]
            if row["role"] == "STRATEGIC_CONTEXT"
        )
        current_strategic = next(
            row
            for row in carried["frames"]
            if row["role"] == "STRATEGIC_CONTEXT"
        )
        for field in (
            "frame_id",
            "created_at",
            "as_of",
            "available_at",
            "expires_at",
            "payload_digest",
            "source_refs",
            "dependency_groups",
            "invalidation_event_types",
        ):
            self.assertEqual(prior_strategic[field], current_strategic[field])
        self.assertEqual(
            prior_strategic["frame_digest"],
            current_strategic["previous_frame_digest"],
        )

        changed = deepcopy(unchanged)
        changed_bar = changed["closed_bar_series"]["4H"][-1]
        changed_bar["volume_contracts"] = "10001"
        changed_datum_id = (
            f"bar-4h-{changed_bar['open_time_ms']}-volume"
        )
        changed_datum_index = next(
            index
            for index, row in enumerate(changed["datums"])
            if row["datum_id"] == changed_datum_id
        )
        changed_datum = changed["datums"][changed_datum_index]
        prior_datum_digest = changed_datum[PIT_DATUM_DIGEST_FIELD]
        changed_datum["value"] = "10001"
        changed_datum = self_digest(changed_datum, PIT_DATUM_DIGEST_FIELD)
        changed["datums"][changed_datum_index] = changed_datum
        changed["pit_member_digests"] = sorted(
            changed_datum[PIT_DATUM_DIGEST_FIELD]
            if digest == prior_datum_digest
            else digest
            for digest in changed["pit_member_digests"]
        )
        changed = self_digest(changed, ANALYSIS_BUNDLE_DIGEST_FIELD)
        refreshed = self.adapter.build_timeframe_context(
            permit=permit,
            public_market_analysis_bundle=changed,
            previous_timeframe_context=self.timeframe,
        )
        refreshed_strategic = next(
            row
            for row in refreshed["frames"]
            if row["role"] == "STRATEGIC_CONTEXT"
        )
        self.assertEqual("REFRESHED", refreshed_strategic["update_mode"])
        self.assertNotEqual(
            prior_strategic["payload_digest"],
            refreshed_strategic["payload_digest"],
        )

    def test_expired_strategic_frame_refreshes_and_tamper_never_hits_cache(self):
        permit = deepcopy(self.permit)
        permit["analysis_cycle_index"] = 2
        permit["analysis_decision_at"] = "2026-08-08T00:30:00Z"
        unchanged = deepcopy(self.market["analysis_bundle"])
        unchanged["qualification_id"] = "q-material-expiry-0002"
        unchanged["cycle_index"] = 2
        unchanged = self_digest(unchanged, ANALYSIS_BUNDLE_DIGEST_FIELD)

        refreshed = self.adapter.build_timeframe_context(
            permit=permit,
            public_market_analysis_bundle=unchanged,
            previous_timeframe_context=self.timeframe,
        )
        strategic = next(
            row
            for row in refreshed["frames"]
            if row["role"] == "STRATEGIC_CONTEXT"
        )
        self.assertEqual("REFRESHED", strategic["update_mode"])
        self.assertTrue(refreshed["strategic_rebuild_required"])
        self.assertEqual(
            ["STRATEGIC_TTL_EXPIRED"],
            [row["event_type"] for row in refreshed["observed_invalidation_events"]],
        )

        tampered = deepcopy(unchanged)
        tampered["closed_bar_series"]["4H"][-1]["volume_contracts"] = "10002"
        with self.assertRaisesRegex(
            ValueError, "PUBLIC_BUNDLE_INVALID"
        ):
            self.adapter.build_timeframe_context(
                permit=permit,
                public_market_analysis_bundle=tampered,
                previous_timeframe_context=self.timeframe,
            )

    def test_lossless_package_is_not_created_when_complete_packet_fits_inline(self):
        proposal_binding = _binding(
            "cycles/0001/proposal-packet.json", self.proposal
        )
        self.assertIsNone(
            self.adapter.lossless_context_package(
                stage="PROPOSAL",
                canonical_packet=self.proposal,
                canonical_packet_binding=proposal_binding,
            )
        )

    def test_oversize_inline_fails_before_compaction_or_any_mailbox_write(self):
        proposal_binding = _binding(
            "cycles/0001/proposal-packet.json", self.proposal
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mailbox = LocalV32CurrentRootAgentMailbox(root)
            checkpoint = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox:{TARGET_RUN}:0001",
                run_id=TARGET_RUN,
                cycle_index=1,
                created_at="2026-08-07T00:15:00Z",
            )
            inventory_before = mailbox.json_prefix_inventory_v1(
                run_id=TARGET_RUN, cycle_index=1
            )
            with patch(
                "trade_system.theory_paper_v2.domain.v32_agent_lifecycle."
                "MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES",
                1024,
            ), patch(
                "trade_system.theory_paper_v2.infrastructure."
                "v32_analysis_material_adapter."
                "build_v32_context_compaction_bundle_v1",
            ) as compact, self.assertRaisesRegex(
                V32AnalysisMaterialAdapterError,
                "^CONTEXT_CAPACITY_UNRESOLVED$",
            ):
                package = self.adapter.lossless_context_package(
                    stage="PROPOSAL",
                    canonical_packet=self.proposal,
                    canonical_packet_binding=proposal_binding,
                )
                mailbox.enqueue_request(  # pragma: no cover - fail-closed guard
                    run_id=TARGET_RUN,
                    cycle_index=1,
                    expected_checkpoint_digest=checkpoint[
                        MAILBOX_CHECKPOINT_DIGEST_FIELD
                    ],
                    agent_input_context={},
                    agent_input_context_binding={},
                    reserved_at="2026-08-07T00:15:01Z",
                    lossless_context_package=package,
                )
            compact.assert_not_called()
            self.assertEqual(
                checkpoint,
                mailbox.load_checkpoint(run_id=TARGET_RUN, cycle_index=1),
            )
            self.assertEqual(
                inventory_before,
                mailbox.json_prefix_inventory_v1(
                    run_id=TARGET_RUN, cycle_index=1
                ),
            )
            self.assertFalse(any(root.rglob("request.json")))
            self.assertFalse(any(root.rglob("input-materials")))

    def test_mailbox_reader_returns_complete_original_without_claiming(self):
        proposal_binding = _binding(
            "cycles/0001/proposal-packet.json", self.proposal
        )
        context = build_v32_agent_input_context_v1(
            agent_stage="PROPOSAL",
            canonical_packet=self.proposal,
            canonical_packet_binding=proposal_binding,
            created_at="2026-08-07T00:15:00Z",
        )
        context_binding = _binding(
            "cycles/0001/proposal-agent-input.json", context
        )
        with TemporaryDirectory() as directory:
            mailbox = LocalV32CurrentRootAgentMailbox(Path(directory))
            checkpoint = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox:{TARGET_RUN}:0001",
                run_id=TARGET_RUN,
                cycle_index=1,
                created_at="2026-08-07T00:15:00Z",
            )
            opened = mailbox.enqueue_request(
                run_id=TARGET_RUN,
                cycle_index=1,
                expected_checkpoint_digest=checkpoint[
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=context,
                agent_input_context_binding=context_binding,
                reserved_at="2026-08-07T00:15:01Z",
            )
            request = read_current_v32_strategy_agent_request_v1(
                mailbox=mailbox, run_id=TARGET_RUN, cycle_index=1
            )
            after = mailbox.load_checkpoint(
                run_id=TARGET_RUN, cycle_index=1
            )
        self.assertEqual(request["control_context"]["stage"], "PROPOSAL")
        self.assertEqual(
            request["request"]["agent_input_context"]["canonical_packet"],
            self.proposal,
        )
        self.assertIsNone(request["lossless_context_package"])
        self.assertTrue(request["control_context"]["read_only"])
        verify_v32_current_codex_presentation_envelope_v1(request)
        self.assertLessEqual(
            len(canonical_bytes(request)),
            MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
        )
        self.assertEqual(
            canonical_bytes(request).count(canonical_bytes(self.proposal)),
            1,
        )
        self.assertEqual(
            after[MAILBOX_CHECKPOINT_DIGEST_FIELD],
            opened["checkpoint"][MAILBOX_CHECKPOINT_DIGEST_FIELD],
        )
        self.assertEqual(after["stage_states"]["PROPOSAL"]["status"], "REQUESTED")

    def test_mailbox_reader_replays_claimed_inline_request_without_mutation(self):
        proposal_binding = _binding(
            "cycles/0001/proposal-packet.json", self.proposal
        )
        context = build_v32_agent_input_context_v1(
            agent_stage="PROPOSAL",
            canonical_packet=self.proposal,
            canonical_packet_binding=proposal_binding,
            created_at="2026-08-07T00:15:00Z",
        )
        context_binding = _binding(
            "cycles/0001/proposal-agent-input.json", context
        )
        with TemporaryDirectory() as directory:
            mailbox = LocalV32CurrentRootAgentMailbox(Path(directory))
            checkpoint = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox:{TARGET_RUN}:0001",
                run_id=TARGET_RUN,
                cycle_index=1,
                created_at="2026-08-07T00:15:00Z",
            )
            opened = mailbox.enqueue_request(
                run_id=TARGET_RUN,
                cycle_index=1,
                expected_checkpoint_digest=checkpoint[
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=context,
                agent_input_context_binding=context_binding,
                reserved_at="2026-08-07T00:15:01Z",
            )
            claimed = mailbox.claim_request(
                run_id=TARGET_RUN,
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=opened["checkpoint"][
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                claimed_at="2026-08-07T00:15:02Z",
            )
            presentation = read_current_v32_strategy_agent_request_v1(
                mailbox=mailbox, run_id=TARGET_RUN, cycle_index=1
            )
            after = mailbox.load_checkpoint(
                run_id=TARGET_RUN, cycle_index=1
            )
        verify_v32_current_codex_presentation_envelope_v1(presentation)
        self.assertEqual(
            "CLAIMED", presentation["control_context"]["stage_status"]
        )
        self.assertIsNotNone(presentation["claim"])
        self.assertLessEqual(
            len(canonical_bytes(presentation)),
            MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
        )
        self.assertEqual(
            claimed["checkpoint"][MAILBOX_CHECKPOINT_DIGEST_FIELD],
            after[MAILBOX_CHECKPOINT_DIGEST_FIELD],
        )

    def test_mailbox_reader_normalizes_presentation_builder_failure(self):
        with patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "_read_current_v32_strategy_agent_request_v1",
            side_effect=RuntimeError("host-specific"),
        ), self.assertRaisesRegex(
            V32AnalysisMaterialAdapterError,
            "V32_ANALYSIS_MATERIAL_AGENT_PRESENTATION_FAILED",
        ):
            read_current_v32_strategy_agent_request_v1(
                mailbox=object(),  # type: ignore[arg-type]
                run_id=TARGET_RUN,
                cycle_index=1,
            )

    def test_objective_gaps_do_not_create_subjective_unknowns_and_schedule_is_fixed(self):
        gaps = build_v32_required_data_gap_escalations_v1(
            public_market_analysis_bundle=self.market["analysis_bundle"]
        )
        self.assertTrue(gaps)
        selection_stub = {
            "run_id": TARGET_RUN,
            "cycle_index": 1,
            "prepared_at": "2026-08-07T00:15:45Z",
        }
        registry_stub = self_digest(
            {
                "schema_id": "test_v32_authorized_revision_registry_v1",
                "run_id": TARGET_RUN,
                "cycle_index": 1,
            },
            "authorized_revision_cycle_registry_digest",
        )
        with patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "verify_v32_selection_canonical_packet_v1",
            return_value="a" * 64,
        ), patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "build_v32_authorized_revision_cycle_registry_v1",
            return_value=registry_stub,
        ) as build_registry, patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_analysis_material_adapter."
            "verify_v32_authorized_revision_cycle_registry_v1",
            return_value=registry_stub[
                "authorized_revision_cycle_registry_digest"
            ],
        ):
            material = self.adapter.build_authorized_revision_cycle_registry(
                permit=self.permit,
                proposal_packet=self.proposal,
                proposal_context_package=None,
                selection_packet=selection_stub,
                selection_context_package=None,
                required_data_gap_escalations=gaps,
            )
        self.assertEqual(material["unknown_tracks"], [])
        self.assertEqual(len(material["data_gap_entries"]), len(gaps))
        self.assertEqual(
            [row["escalation"] for row in material["data_gap_entries"]], gaps
        )
        self.assertEqual(build_registry.call_args.kwargs["unknown_tracks"], [])

        plan = self_digest(
            {
                "schema_id": "test_non_executable_v32_action_plan_v1",
                "run_id": TARGET_RUN,
                "cycle_index": 1,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "dynamic_action_plan_digest",
        )
        schedule = self.adapter.build_outcome_schedule_set(
            permit=self.permit,
            final_dynamic_action_plan=plan,
            proposal_packet=self.proposal,
            decision_sealed_at=selection_stub["prepared_at"],
        )
        self.assertEqual(
            [row["horizon"] for row in schedule["schedules"]],
            ["15M", "1H", "4H"],
        )
        self.assertEqual(
            [row["outcome_not_before"] for row in schedule["schedules"]],
            [
                "2026-08-07T00:30:45Z",
                "2026-08-07T01:15:45Z",
                "2026-08-07T04:15:45Z",
            ],
        )
        self.assertFalse(schedule["executable"])


if __name__ == "__main__":
    unittest.main()
