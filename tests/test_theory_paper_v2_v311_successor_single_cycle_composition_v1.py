from __future__ import annotations

import copy
import unittest
from unittest.mock import Mock, patch

from trade_system.theory_paper_v2.application import (
    v311_successor_single_cycle_composition_v1 as composition,
)


RUN_ID = "v311-successor-target-cycle-test"


def _binding(name: str, character: str) -> dict[str, str]:
    return {
        "relative_ref": f"support/{name}.json",
        "schema_id": f"schema:{name}",
        "digest_field": f"{name}_digest",
        "semantic_digest": character * 64,
        "physical_sha256": character * 64,
    }


def _support_bindings() -> dict[str, dict[str, str]]:
    characters = "1234567"
    return {
        name: _binding(name, characters[index])
        for index, name in enumerate(
            sorted(composition.SUPPORT_BINDING_KEYS)
        )
    }


def _target_documents() -> dict[str, dict]:
    return {
        "theory_approval": {},
        "experiment_contract": {
            "run_id": RUN_ID,
            "experiment_contract_digest": "a" * 64,
        },
        "manifest": {"run_id": RUN_ID},
        "authorization_receipt": {},
        "authority": {
            "authorized_run_id": RUN_ID,
            "authority_digest": "b" * 64,
        },
    }


def _global_bindings() -> dict[str, dict[str, str]]:
    return {
        name: {"active_role": name}
        for name in composition.V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
    }


def _global_raw_bytes() -> dict[str, bytes]:
    return {
        name: f"raw:{name}".encode("utf-8")
        for name in composition.V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
    }


class _CheckpointStore:
    def __init__(self, checkpoint: dict) -> None:
        self.checkpoint = copy.deepcopy(checkpoint)

    def load_checkpoint(self, *, run_id: str):
        if run_id != RUN_ID:
            raise ValueError("run mismatch")
        return copy.deepcopy(self.checkpoint)


class _CommitStore:
    def __init__(self, *, existing: bool = False) -> None:
        self.existing = existing
        self.material = {
            composition.COMMIT_MATERIAL_DIGEST_FIELD: "c" * 64,
            "support_bindings": _support_bindings(),
        }

    def material_exists(self, *, relative_ref: str) -> bool:
        self.relative_ref = relative_ref
        return self.existing

    def read_material(self, *, relative_ref: str, **_kwargs):
        return copy.deepcopy(self.material)

    def artifact_binding(self, *, relative_ref: str, **_kwargs):
        return {
            "relative_ref": relative_ref,
            "schema_id": "theory_paper_v31_successor_cycle_commit_material",
            "digest_field": composition.COMMIT_MATERIAL_DIGEST_FIELD,
            "semantic_digest": self.material[
                composition.COMMIT_MATERIAL_DIGEST_FIELD
            ],
            "physical_sha256": "d" * 64,
        }


class _Supervisor:
    def load_checkpoint(self, *, run_id: str):
        if run_id != RUN_ID:
            raise ValueError("run mismatch")
        return {
            "status": "CYCLE_PERMIT_OPEN",
            "current_cycle_index": 1,
            "active_permit_digest": "e" * 64,
        }

    def artifact_binding(self, *, relative_ref: str, **_kwargs):
        self.permit_ref = relative_ref
        return _binding("permit", "e") | {"relative_ref": relative_ref}


class V311SuccessorSingleCycleCompositionV1Tests(unittest.TestCase):
    def test_current_root_wrapper_passes_complete_context_not_legacy_request(
        self,
    ) -> None:
        packet_binding = _binding("authoring-packet", "a")
        context = {
            "schema_id": composition.AGENT_INPUT_CONTEXT_SCHEMA_ID,
            "run_id": RUN_ID,
            "cycle_index": 1,
            "base_authoring_packet_binding": packet_binding,
            "support_documents": {"complete": True},
            composition.AGENT_INPUT_CONTEXT_DIGEST_FIELD: "9" * 64,
        }
        context_binding = _binding("agent-input-context", "9") | {
            "schema_id": composition.AGENT_INPUT_CONTEXT_SCHEMA_ID,
            "digest_field": composition.AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        }
        packet = {"packet": True}
        transport_store = Mock()
        transport_store.read_bound_document.return_value = packet
        observed: list[dict] = []

        def old_transport(**kwargs):
            payload = kwargs["agent_call"]({"legacy_request": True})
            return {
                "status": "READY_FOR_COMPILATION",
                "agent_authoring_envelope": payload,
            }

        with (
            patch.object(
                composition,
                "_typed_existing_document",
                return_value=(context, context_binding),
            ),
            patch.object(
                composition,
                "verify_v311_agent_input_context_durable_v1",
                return_value="9" * 64,
            ),
            patch.object(
                composition,
                "run_v31_authoring_transport",
                side_effect=old_transport,
            ),
        ):
            result = composition.run_v311_current_root_authoring_transport_v1(
                research_store=object(),
                projection_store=object(),
                transport_store=transport_store,
                run_id=RUN_ID,
                cycle_index=1,
                owner_id="owner",
                lease_acquired_at="2026-08-07T00:00:00Z",
                lease_expires_at="2026-08-07T00:10:00Z",
                stage_times={},
                current_root_agent_call=lambda value: observed.append(
                    copy.deepcopy(dict(value))
                )
                or {"agent_envelope": True},
            )

        self.assertEqual([context], observed)
        self.assertTrue(result["direct_context_input_declared_by_controller"])
        self.assertEqual(
            "PRACTICAL_CODEX_NOT_MODEL_ATTESTED",
            result["transport_attestation_level"],
        )

    def test_prepare_reuses_existing_owners_and_invokes_no_agent_or_outcome(
        self,
    ) -> None:
        support = _support_bindings()
        permit_binding = _binding("permit", "e")
        source_binding = _binding("source-admission", "f")
        calls: list[str] = []
        owner_arguments: dict[str, object] = {}

        def step(name: str, value):
            def invoked(*_args, **_kwargs):
                calls.append(name)
                return copy.deepcopy(value)

            return invoked

        def initialize_owners(**kwargs):
            calls.append("owners")
            owner_arguments.update(
                {
                    "genesis_documents": copy.deepcopy(
                        kwargs["genesis_documents"]
                    ),
                    "genesis_bindings": copy.deepcopy(
                        kwargs["genesis_bindings"]
                    ),
                    "genesis_raw_bytes": copy.deepcopy(
                        kwargs["genesis_raw_bytes"]
                    ),
                }
            )
            return {
                "research": {"revision": 0},
                "monitor": {"revision": 0},
                "outcome_evidence": {"revision": 0},
                "supervisor": {"status": "BOOTSTRAPPED"},
            }

        with (
            patch.object(
                composition,
                "_project_target",
                side_effect=step("project", _target_documents()),
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                side_effect=step(
                    "validate-support",
                    {
                        "clock_policy": {},
                        "theory_addendum_binding": {
                            "path": "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md",
                            "version": "3.1.1",
                            "review_status": "FROZEN_APPROVED",
                            "physical_sha256": "0" * 64,
                        },
                    },
                ),
            ),
            patch.object(
                composition,
                "_initialize_or_replay_owner_checkpoints",
                side_effect=initialize_owners,
            ),
            patch.object(
                composition,
                "open_v31_cycle_permit_v2",
                side_effect=step(
                    "permit",
                    {
                        "cycle_index": 1,
                        "cycle_permit_binding": permit_binding,
                        "supervisor_checkpoint": {
                            "status": "CYCLE_PERMIT_OPEN"
                        },
                    },
                ),
            ),
            patch.object(
                composition,
                "verify_v31_cycle_permit_live_v2",
                side_effect=lambda **kwargs: calls.append(
                    f"verify:{kwargs['operation']}"
                )
                or {},
            ),
            patch.object(
                composition,
                "admit_fresh_v31_source_to_authorized_cycle",
                side_effect=step(
                    "source", {"cycle_source_admission_binding": source_binding}
                ),
            ),
            patch.object(
                composition,
                "compose_and_persist_v31_sentiment_projection_v2",
                side_effect=step(
                    "sentiment",
                    {
                        "support_bindings": {
                            "sentiment_source_registry": support[
                                "sentiment_source_registry"
                            ],
                            "sentiment_projection": support[
                                "sentiment_projection"
                            ],
                        }
                    },
                ),
            ),
            patch.object(
                composition,
                "_recover_support_bindings",
                side_effect=step("support", support),
            ),
            patch.object(
                composition,
                "prepare_v31_formal_authoring_cycle",
                side_effect=step(
                    "formal",
                    {
                        "authoring_packet": {
                            "authority_context": {
                                "active_authority_binding": _binding(
                                    "authority", "a"
                                )
                            }
                        },
                        "authoring_packet_binding": _binding("packet", "a"),
                    },
                ),
            ),
            patch.object(
                composition,
                "_target_context_support_set",
                side_effect=step("context-support", ({}, {})),
            ),
            patch.object(
                composition,
                "build_v311_agent_input_context_v1",
                side_effect=step(
                    "context-build",
                    {
                        "schema_id": composition.AGENT_INPUT_CONTEXT_SCHEMA_ID,
                        composition.AGENT_INPUT_CONTEXT_DIGEST_FIELD: "9" * 64,
                    },
                ),
            ),
            patch.object(
                composition,
                "_persist_document",
                side_effect=step(
                    "context-persist",
                    _binding("agent-input-context", "9")
                    | {
                        "schema_id": composition.AGENT_INPUT_CONTEXT_SCHEMA_ID,
                        "digest_field": composition.AGENT_INPUT_CONTEXT_DIGEST_FIELD,
                    },
                ),
            ),
            patch.object(
                composition,
                "verify_v311_agent_input_context_durable_v1",
                side_effect=step("context-verify", "9" * 64),
            ),
            patch.object(
                composition,
                "initialize_v31_agent_transport",
                side_effect=step(
                    "transport-init", {"status": "READY_FOR_PROPOSAL"}
                ),
            ),
        ):
            result = composition.prepare_v311_successor_single_cycle_v1(
                loaded_context={"clock_policy": {}},
                authority_projector=Mock(),
                target_global_bindings=_global_bindings(),
                target_global_raw_bytes=_global_raw_bytes(),
                research_store=object(),
                monitor_store=object(),
                supervisor_store=object(),
                source_store=object(),
                projection_store=object(),
                transport_store=object(),
                outcome_evidence_store=object(),
                commit_store=_CommitStore(existing=False),
                run_id=RUN_ID,
                cycle_index=1,
                qualification_id="qualification-1",
                genesis_created_at="2026-08-07T00:00:00Z",
                monitor_created_at="2026-08-07T00:00:01Z",
                outcome_evidence_created_at="2026-08-07T00:00:02Z",
                supervisor_created_at="2026-08-07T00:00:03Z",
                permit_issued_at="2026-08-07T00:00:04Z",
                source_admitted_at="2026-08-07T00:00:05Z",
                agent_context_created_at="2026-08-07T00:00:05Z",
                theory_addendum_raw_bytes=b"# addendum\n",
                transport_created_at="2026-08-07T00:00:06Z",
                transport_owner_id="owner",
                transport_lease_expires_at="2026-08-07T00:10:06Z",
            )

        self.assertEqual(
            [
                "project",
                "validate-support",
                "owners",
                "permit",
                "verify:SOURCE_QUALIFICATION",
                "source",
                "verify:FORMAL_PREPARE",
                "sentiment",
                "support",
                "formal",
                "context-support",
                "context-build",
                "context-persist",
                "context-verify",
                "transport-init",
            ],
            calls,
        )
        expected_role_map = composition._GENESIS_ROLE_FROM_ACTIVE_CHAIN
        self.assertEqual(
            {
                genesis_role: _target_documents()[active_role]
                for genesis_role, active_role in expected_role_map.items()
            },
            owner_arguments["genesis_documents"],
        )
        self.assertEqual(
            {
                genesis_role: _global_bindings()[active_role]
                for genesis_role, active_role in expected_role_map.items()
            },
            owner_arguments["genesis_bindings"],
        )
        self.assertEqual(
            {
                genesis_role: _global_raw_bytes()[active_role]
                for genesis_role, active_role in expected_role_map.items()
            },
            owner_arguments["genesis_raw_bytes"],
        )
        self.assertEqual(set(composition.SUPPORT_BINDING_KEYS), set(result["support_bindings"]))
        self.assertTrue(
            all(
                set(binding) == composition._TYPED_BINDING_FIELDS
                for binding in result["support_bindings"].values()
            )
        )
        self.assertFalse(result["agent_invoked"])
        self.assertFalse(result["outcome_collection_performed"])

    def test_prepare_short_circuits_frozen_material_before_any_owner_write(self) -> None:
        store = _CommitStore(existing=True)
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition, "initialize_v31_run_genesis"
            ) as initialize,
        ):
            result = composition.prepare_v311_successor_single_cycle_v1(
                loaded_context={},
                authority_projector=Mock(),
                target_global_bindings={},
                target_global_raw_bytes={},
                research_store=object(),
                monitor_store=object(),
                supervisor_store=object(),
                source_store=object(),
                projection_store=object(),
                transport_store=object(),
                outcome_evidence_store=object(),
                commit_store=store,
                run_id=RUN_ID,
                cycle_index=1,
                qualification_id="qualification-1",
                genesis_created_at="2026-08-07T00:00:00Z",
                monitor_created_at="2026-08-07T00:00:01Z",
                outcome_evidence_created_at="2026-08-07T00:00:02Z",
                supervisor_created_at="2026-08-07T00:00:03Z",
                permit_issued_at="2026-08-07T00:00:04Z",
                source_admitted_at="2026-08-07T00:00:05Z",
                agent_context_created_at="2026-08-07T00:00:05Z",
                theory_addendum_raw_bytes=b"# addendum\n",
                transport_created_at="2026-08-07T00:00:06Z",
                transport_owner_id="owner",
                transport_lease_expires_at="2026-08-07T00:10:06Z",
            )

        initialize.assert_not_called()
        self.assertEqual(
            "V311_COMMIT_MATERIAL_ALREADY_FROZEN_RECOVERY_REQUIRED",
            result["status"],
        )
        self.assertFalse(result["agent_invoked"])
        self.assertFalse(result["outcome_collection_performed"])

    def test_post_permit_preparation_failure_closes_supervisor_once(self) -> None:
        source_error = RuntimeError("source admission failed")
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "_genesis_role_projection",
                return_value=({}, {}, {}),
            ),
            patch.object(
                composition,
                "_initialize_or_replay_owner_checkpoints",
                return_value={
                    "research": {},
                    "monitor": {},
                    "outcome_evidence": {},
                    "supervisor": {},
                },
            ),
            patch.object(
                composition,
                "open_v31_cycle_permit_v2",
                return_value={
                    "cycle_index": 1,
                    "cycle_permit_binding": _binding("permit", "e"),
                },
            ),
            patch.object(
                composition, "verify_v31_cycle_permit_live_v2"
            ),
            patch.object(
                composition,
                "admit_fresh_v31_source_to_authorized_cycle",
                side_effect=source_error,
            ),
            patch.object(
                composition,
                "fail_v31_experiment_supervisor_v2",
                return_value={"status": "FAILED_CLOSED"},
            ) as fail,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "PREPARATION_FAILED_SUPERVISOR_CLOSED",
            ) as raised:
                composition.prepare_v311_successor_single_cycle_v1(
                    loaded_context={},
                    authority_projector=Mock(),
                    target_global_bindings={},
                    target_global_raw_bytes={},
                    research_store=object(),
                    monitor_store=object(),
                    supervisor_store=object(),
                    source_store=object(),
                    projection_store=object(),
                    transport_store=object(),
                    outcome_evidence_store=object(),
                    commit_store=_CommitStore(existing=False),
                    run_id=RUN_ID,
                    cycle_index=1,
                    qualification_id="qualification-1",
                    genesis_created_at="2026-08-07T00:00:00Z",
                    monitor_created_at="2026-08-07T00:00:01Z",
                    outcome_evidence_created_at="2026-08-07T00:00:02Z",
                    supervisor_created_at="2026-08-07T00:00:03Z",
                    permit_issued_at="2026-08-07T00:00:04Z",
                    source_admitted_at="2026-08-07T00:00:05Z",
                    agent_context_created_at="2026-08-07T00:00:05Z",
                    theory_addendum_raw_bytes=b"# addendum\n",
                    transport_created_at="2026-08-07T00:00:06Z",
                    transport_owner_id="owner",
                    transport_lease_expires_at="2026-08-07T00:10:06Z",
                )
        fail.assert_called_once()
        self.assertIs(raised.exception.__cause__, source_error)

    def test_cycle_two_replays_all_owner_checkpoints_without_reinitializing(
        self,
    ) -> None:
        contract_digest = "a" * 64
        authority_digest = "b" * 64
        clock_digest = "c" * 64
        research = {
            "run_id": RUN_ID,
            "status": "READY_FOR_CYCLE",
            "completed_cycles": 1,
            "next_cycle_index": 2,
            "active_cycle_index": None,
            "current_authority_digest": authority_digest,
            "resume_allowed": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "checkpoint_digest": "d" * 64,
        }
        monitor = {
            "run_id": RUN_ID,
            "status": "ACTIVE",
            "experiment_contract_digest": contract_digest,
            "resume_allowed": True,
            "plan_bindings": [{}],
            "resolution_attempt_bindings": [{}],
            "outcome_bindings": [{}],
            "checkpoint_digest": "e" * 64,
        }
        evidence = {
            "run_id": RUN_ID,
            "status": "ACTIVE",
            "clock_policy_digest": clock_digest,
            "resume_allowed": True,
            "attempt_bindings": [{}],
            "capture_bindings": [{}],
            "parse_bindings": [{}],
            "resolution_bindings": [{}],
        }
        supervisor = {
            "run_id": RUN_ID,
            "status": "CYCLE_PERMIT_OPEN",
            "current_cycle_index": 2,
            "completed_research_cycles": 1,
            "resolved_outcome_cycles": 1,
            "experiment_contract_digest": contract_digest,
            "active_authority_digest": authority_digest,
            "active_permit_digest": "f" * 64,
            "active_commit_intent_digest": None,
            "research_checkpoint_digest": "d" * 64,
            "monitor_checkpoint_digest": "e" * 64,
            "resume_allowed": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
        genesis_documents, genesis_bindings, genesis_raw = (
            composition._genesis_role_projection(
                target_documents=_target_documents(),
                target_global_bindings=_global_bindings(),
                target_global_raw_bytes=_global_raw_bytes(),
            )
        )
        self.assertIsNotNone(genesis_raw)
        with (
            patch.object(
                composition,
                "verify_outcome_clock_policy",
                return_value=clock_digest,
            ),
            patch.object(
                composition, "initialize_v31_run_genesis"
            ) as initialize_genesis,
            patch.object(
                composition, "initialize_v31_monitor_runtime"
            ) as initialize_monitor,
            patch.object(
                composition, "initialize_v31_outcome_evidence_runtime_v2"
            ) as initialize_evidence,
            patch.object(
                composition, "initialize_v31_experiment_supervisor_v2"
            ) as initialize_supervisor,
        ):
            result = composition._initialize_or_replay_owner_checkpoints(
                cycle_index=2,
                run_id=RUN_ID,
                target_documents=_target_documents(),
                genesis_documents=genesis_documents,
                genesis_bindings=genesis_bindings,
                genesis_raw_bytes=genesis_raw or {},
                loaded_clock_policy={},
                research_store=_CheckpointStore(research),
                monitor_store=_CheckpointStore(monitor),
                outcome_evidence_store=_CheckpointStore(evidence),
                supervisor_store=_CheckpointStore(supervisor),
                genesis_created_at="unused",
                monitor_created_at="unused",
                outcome_evidence_created_at="unused",
                supervisor_created_at="unused",
            )

        initialize_genesis.assert_not_called()
        initialize_monitor.assert_not_called()
        initialize_evidence.assert_not_called()
        initialize_supervisor.assert_not_called()
        self.assertEqual(research, result["research"])
        self.assertEqual(monitor, result["monitor"])
        self.assertEqual(evidence, result["outcome_evidence"])
        self.assertEqual(supervisor, result["supervisor"])
        self.assertTrue(result["permit_open_reentry"])

    def test_prepare_cycle_two_performs_zero_owner_initializations(self) -> None:
        support = _support_bindings()
        research = {
            "run_id": RUN_ID,
            "status": "READY_FOR_CYCLE",
            "completed_cycles": 1,
            "next_cycle_index": 2,
            "active_cycle_index": None,
            "current_authority_digest": "b" * 64,
            "resume_allowed": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
        monitor = {
            "run_id": RUN_ID,
            "status": "ACTIVE",
            "experiment_contract_digest": "a" * 64,
            "resume_allowed": True,
            "plan_bindings": [{}],
            "resolution_attempt_bindings": [{}],
            "outcome_bindings": [{}],
        }
        evidence = {
            "run_id": RUN_ID,
            "status": "ACTIVE",
            "clock_policy_digest": "c" * 64,
            "resume_allowed": True,
            "attempt_bindings": [{}],
            "capture_bindings": [{}],
            "parse_bindings": [{}],
            "resolution_bindings": [{}],
        }
        supervisor = {
            "run_id": RUN_ID,
            "status": "AWAITING_OUTCOME",
            "completed_research_cycles": 1,
            "resolved_outcome_cycles": 0,
            "experiment_contract_digest": "a" * 64,
            "active_authority_digest": "b" * 64,
            "active_permit_digest": None,
            "active_commit_intent_digest": None,
            "resume_allowed": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={
                    "clock_policy": {},
                    "theory_addendum_binding": {
                        "path": "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md",
                        "version": "3.1.1",
                        "review_status": "FROZEN_APPROVED",
                        "physical_sha256": "0" * 64,
                    },
                },
            ),
            patch.object(
                composition,
                "verify_outcome_clock_policy",
                return_value="c" * 64,
            ),
            patch.object(
                composition, "initialize_v31_run_genesis"
            ) as initialize_genesis,
            patch.object(
                composition, "initialize_v31_monitor_runtime"
            ) as initialize_monitor,
            patch.object(
                composition, "initialize_v31_outcome_evidence_runtime_v2"
            ) as initialize_evidence,
            patch.object(
                composition, "initialize_v31_experiment_supervisor_v2"
            ) as initialize_supervisor,
            patch.object(
                composition,
                "open_v31_cycle_permit_v2",
                return_value={
                    "cycle_index": 2,
                    "cycle_permit_binding": _binding("permit", "e"),
                    "supervisor_checkpoint": {
                        "status": "CYCLE_PERMIT_OPEN"
                    },
                },
            ),
            patch.object(
                composition, "verify_v31_cycle_permit_live_v2", return_value={}
            ),
            patch.object(
                composition,
                "admit_fresh_v31_source_to_authorized_cycle",
                return_value={
                    "cycle_source_admission_binding": _binding(
                        "source-admission", "f"
                    )
                },
            ),
            patch.object(
                composition,
                "compose_and_persist_v31_sentiment_projection_v2",
                return_value={
                    "support_bindings": {
                        "sentiment_source_registry": support[
                            "sentiment_source_registry"
                        ],
                        "sentiment_projection": support[
                            "sentiment_projection"
                        ],
                    }
                },
            ),
            patch.object(
                composition, "_recover_support_bindings", return_value=support
            ),
            patch.object(
                composition,
                "prepare_v31_formal_authoring_cycle",
                return_value={
                    "authoring_packet": {
                        "authority_context": {
                            "active_authority_binding": _binding(
                                "authority", "a"
                            )
                        }
                    },
                    "authoring_packet_binding": _binding("packet", "a"),
                },
            ),
            patch.object(
                composition,
                "_target_context_support_set",
                return_value=({}, {}),
            ),
            patch.object(
                composition,
                "build_v311_agent_input_context_v1",
                return_value={
                    "schema_id": composition.AGENT_INPUT_CONTEXT_SCHEMA_ID,
                    composition.AGENT_INPUT_CONTEXT_DIGEST_FIELD: "9" * 64,
                },
            ),
            patch.object(
                composition,
                "_persist_document",
                return_value=_binding("agent-input-context", "9")
                | {
                    "schema_id": composition.AGENT_INPUT_CONTEXT_SCHEMA_ID,
                    "digest_field": composition.AGENT_INPUT_CONTEXT_DIGEST_FIELD,
                },
            ),
            patch.object(
                composition,
                "verify_v311_agent_input_context_durable_v1",
                return_value="9" * 64,
            ),
            patch.object(
                composition,
                "initialize_v31_agent_transport",
                return_value={"status": "READY_FOR_PROPOSAL"},
            ),
        ):
            result = composition.prepare_v311_successor_single_cycle_v1(
                loaded_context={"clock_policy": {}},
                authority_projector=Mock(),
                target_global_bindings=_global_bindings(),
                target_global_raw_bytes=_global_raw_bytes(),
                research_store=_CheckpointStore(research),
                monitor_store=_CheckpointStore(monitor),
                supervisor_store=_CheckpointStore(supervisor),
                source_store=object(),
                projection_store=object(),
                transport_store=object(),
                outcome_evidence_store=_CheckpointStore(evidence),
                commit_store=_CommitStore(existing=False),
                run_id=RUN_ID,
                cycle_index=2,
                qualification_id="qualification-2",
                genesis_created_at="unused",
                monitor_created_at="unused",
                outcome_evidence_created_at="unused",
                supervisor_created_at="unused",
                permit_issued_at="2026-08-07T03:00:00Z",
                source_admitted_at="2026-08-07T03:00:01Z",
                agent_context_created_at="2026-08-07T03:00:01Z",
                theory_addendum_raw_bytes=b"# addendum\n",
                transport_created_at="2026-08-07T03:00:02Z",
                transport_owner_id="owner",
                transport_lease_expires_at="2026-08-07T03:10:02Z",
                previous_cycle_source_admission_binding=_binding(
                    "previous-source-admission", "1"
                ),
                prior_snapshot_binding=_binding("prior-snapshot", "2"),
                prior_open_interest_datum_digest="3" * 64,
            )

        initialize_genesis.assert_not_called()
        initialize_monitor.assert_not_called()
        initialize_evidence.assert_not_called()
        initialize_supervisor.assert_not_called()
        self.assertEqual(2, result["cycle_index"])
        self.assertEqual(research, result["research_checkpoint"])
        self.assertEqual(monitor, result["monitor_checkpoint"])
        self.assertEqual(evidence, result["outcome_evidence_checkpoint"])
        self.assertEqual(supervisor, result["supervisor_before_permit_checkpoint"])

    def test_commit_freezes_material_before_single_commit_boundary(self) -> None:
        support = _support_bindings()
        commit_store = _CommitStore(existing=False)
        supervisor = _Supervisor()
        material = {
            composition.COMMIT_MATERIAL_DIGEST_FIELD: "c" * 64,
            "support_bindings": support,
        }
        material_binding = _binding("commit-material", "c")
        order: list[str] = []
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition, "_recover_support_bindings", return_value=support
            ),
            patch.object(
                composition,
                "prepare_v31_successor_cycle_commit_material_v2",
                side_effect=lambda **_kwargs: order.append("prepare") or material,
            ),
            patch.object(
                composition,
                "persist_v31_successor_commit_material_v2",
                side_effect=lambda **_kwargs: order.append("persist")
                or material_binding,
            ),
            patch.object(
                composition,
                "commit_or_recover_v31_successor_cycle_v2",
                side_effect=lambda **_kwargs: order.append("commit")
                or {
                    "status": "SUCCESSOR_CYCLE_ACCEPTED_MONITOR_SCHEDULED",
                    "run_id": RUN_ID,
                    "cycle_index": 1,
                    "agent_reinvoked": False,
                    "outcome_collection_performed": False,
                },
            ),
            patch.object(
                composition,
                "_persist_v311_successor_commit_envelope_from_durable_lifecycle",
                side_effect=lambda **_kwargs: order.append("envelope")
                or (
                    {"successor_commit_envelope_digest": "8" * 64},
                    _binding("successor-commit-envelope", "8"),
                ),
            ),
        ):
            result = composition.commit_or_recover_v311_successor_single_cycle_v1(
                loaded_context={},
                authority_projector=Mock(),
                target_global_bindings={},
                research_store=object(),
                monitor_store=object(),
                supervisor_store=supervisor,
                projection_store=object(),
                transport_store=object(),
                commit_store=commit_store,
                run_id=RUN_ID,
                cycle_index=1,
                prepared_at="2026-08-07T01:00:00Z",
                completed_at="2026-08-07T01:00:01Z",
                recorded_at="2026-08-07T01:00:02Z",
                monitor_runtime_created_at="2026-08-07T00:00:01Z",
                committed_at="2026-08-07T01:00:03Z",
                monitor_rules=(),
            )

        self.assertEqual(["prepare", "persist", "envelope", "commit"], order)
        self.assertTrue(result["state_boundary_advanced"])
        self.assertEqual(
            composition.cycle_permit_ref_v2(1), supervisor.permit_ref
        )

    def test_existing_material_recovery_never_prepares_or_persists_again(self) -> None:
        commit_store = _CommitStore(existing=True)
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_recover_support_bindings",
                return_value=commit_store.material["support_bindings"],
            ),
            patch.object(
                composition, "prepare_v31_successor_cycle_commit_material_v2"
            ) as prepare,
            patch.object(
                composition, "persist_v31_successor_commit_material_v2"
            ) as persist,
            patch.object(
                composition,
                "commit_or_recover_v31_successor_cycle_v2",
                return_value={
                    "status": "SUCCESSOR_CYCLE_COMMIT_ALREADY_CLOSED",
                    "run_id": RUN_ID,
                    "cycle_index": 1,
                    "agent_reinvoked": False,
                    "outcome_collection_performed": False,
                },
            ) as commit,
            patch.object(
                composition,
                "_persist_v311_successor_commit_envelope_from_durable_lifecycle",
                return_value=(
                    {"successor_commit_envelope_digest": "8" * 64},
                    _binding("successor-commit-envelope", "8"),
                ),
            ) as lifecycle_envelope,
        ):
            result = composition.commit_or_recover_v311_successor_single_cycle_v1(
                loaded_context={},
                authority_projector=Mock(),
                target_global_bindings={},
                research_store=object(),
                monitor_store=object(),
                supervisor_store=object(),
                projection_store=object(),
                transport_store=object(),
                commit_store=commit_store,
                run_id=RUN_ID,
                cycle_index=1,
                prepared_at="2026-08-07T01:00:00Z",
                completed_at="2026-08-07T01:00:01Z",
                recorded_at="2026-08-07T01:00:02Z",
                monitor_runtime_created_at="2026-08-07T00:00:01Z",
                committed_at="2026-08-07T01:00:03Z",
                monitor_rules=(),
            )

        prepare.assert_not_called()
        persist.assert_not_called()
        lifecycle_envelope.assert_called_once()
        commit.assert_called_once()
        self.assertFalse(result["state_boundary_advanced"])
        self.assertFalse(result["agent_invoked_by_v311_glue"])
        self.assertFalse(result["outcome_collection_performed_by_v311_glue"])

    def test_not_due_outcome_boundary_is_strictly_read_only(self) -> None:
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={"run_id": RUN_ID, "runtime_status": "NOT_DUE"},
            ),
            patch.object(composition, "resolve_due_v31_monitor_v2") as resolve,
            patch.object(
                composition, "fail_v31_experiment_supervisor_v2"
            ) as fail,
        ):
            result = composition.resolve_v311_successor_outcome_boundary_v1(
                loaded_context={},
                authority_projector=Mock(),
                monitor_store=object(),
                evidence_store=object(),
                supervisor_store=object(),
                research_store=object(),
                capture_port=object(),
                run_id=RUN_ID,
                requested_at="2026-08-07T02:00:00Z",
            )

        resolve.assert_not_called()
        fail.assert_not_called()
        self.assertEqual("V311_OUTCOME_BOUNDARY_NO_WRITE", result["status"])
        self.assertFalse(result["capture_attempted"])
        self.assertFalse(result["state_boundary_advanced"])

    def test_awaiting_equal_evidence_count_is_strictly_read_only(self) -> None:
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={
                    "run_id": RUN_ID,
                    "runtime_status": "AWAITING_ACCEPTED_STATE",
                    "resolved_cycles": 1,
                },
            ),
            patch.object(composition, "resolve_due_v31_monitor_v2") as resolve,
            patch.object(
                composition, "fail_v31_experiment_supervisor_v2"
            ) as fail,
        ):
            result = composition.resolve_v311_successor_outcome_boundary_v1(
                loaded_context={},
                authority_projector=Mock(),
                monitor_store=object(),
                evidence_store=_CheckpointStore(
                    {"resolution_bindings": [{}]}
                ),
                supervisor_store=object(),
                research_store=object(),
                capture_port=Mock(),
                run_id=RUN_ID,
                requested_at="2026-08-07T02:00:00Z",
            )

        resolve.assert_not_called()
        fail.assert_not_called()
        self.assertEqual("V311_OUTCOME_BOUNDARY_NO_WRITE", result["status"])
        self.assertFalse(result["state_boundary_advanced"])

    def test_awaiting_one_resolution_tail_uses_local_v2_recovery_once(self) -> None:
        capture = Mock()
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={
                    "run_id": RUN_ID,
                    "runtime_status": "AWAITING_ACCEPTED_STATE",
                    "resolved_cycles": 2,
                },
            ),
            patch.object(
                composition,
                "resolve_due_v31_monitor_v2",
                return_value={
                    "run_id": RUN_ID,
                    "status": "ACTIVE",
                    "resolution_bindings": [{}, {}],
                },
            ) as resolve,
            patch.object(
                composition, "fail_v31_experiment_supervisor_v2"
            ) as fail,
        ):
            result = composition.resolve_v311_successor_outcome_boundary_v1(
                loaded_context={},
                authority_projector=Mock(),
                monitor_store=object(),
                evidence_store=_CheckpointStore(
                    {"resolution_bindings": [{}]}
                ),
                supervisor_store=object(),
                research_store=object(),
                capture_port=capture,
                run_id=RUN_ID,
                requested_at="2026-08-07T02:00:00Z",
            )

        resolve.assert_called_once()
        fail.assert_not_called()
        capture.assert_not_called()
        self.assertEqual(
            "V311_OUTCOME_EVIDENCE_BINDING_RECOVERED", result["status"]
        )
        self.assertTrue(result["state_boundary_advanced"])
        self.assertFalse(result["capture_attempted"])

    def test_awaiting_non_unit_evidence_drift_fails_supervisor_closed(self) -> None:
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={
                    "run_id": RUN_ID,
                    "runtime_status": "AWAITING_ACCEPTED_STATE",
                    "resolved_cycles": 3,
                },
            ),
            patch.object(composition, "resolve_due_v31_monitor_v2") as resolve,
            patch.object(
                composition,
                "fail_v31_experiment_supervisor_v2",
                return_value={"status": "FAILED_CLOSED"},
            ) as fail,
        ):
            result = composition.resolve_v311_successor_outcome_boundary_v1(
                loaded_context={},
                authority_projector=Mock(),
                monitor_store=object(),
                evidence_store=_CheckpointStore(
                    {"resolution_bindings": [{}]}
                ),
                supervisor_store=object(),
                research_store=object(),
                capture_port=Mock(),
                run_id=RUN_ID,
                requested_at="2026-08-07T02:00:00Z",
            )

        resolve.assert_not_called()
        fail.assert_called_once()
        self.assertEqual(
            "V311_OUTCOME_BOUNDARY_SUPERVISOR_FAILED_CLOSED",
            result["status"],
        )
        self.assertTrue(result["state_boundary_advanced"])

    def test_due_outcome_calls_raw_first_once_and_does_not_open_next_cycle(self) -> None:
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={
                    "run_id": RUN_ID,
                    "runtime_status": "DUE",
                    "due_cycle_index": 1,
                },
            ),
            patch.object(
                composition,
                "resolve_due_v31_monitor_v2",
                return_value={
                    "run_id": RUN_ID,
                    "runtime_status": "RESOLVED",
                    "cycle_index": 1,
                },
            ) as resolve,
            patch.object(
                composition, "open_v31_cycle_permit_v2"
            ) as open_permit,
        ):
            result = composition.resolve_v311_successor_outcome_boundary_v1(
                loaded_context={},
                authority_projector=Mock(),
                monitor_store=object(),
                evidence_store=object(),
                supervisor_store=object(),
                research_store=object(),
                capture_port=object(),
                run_id=RUN_ID,
                requested_at="2026-08-07T02:00:00Z",
            )

        resolve.assert_called_once()
        open_permit.assert_not_called()
        self.assertTrue(result["capture_attempted"])
        self.assertFalse(result["next_cycle_opened"])
        self.assertTrue(result["state_boundary_advanced"])

    def test_due_failure_permanently_closes_supervisor(self) -> None:
        resolver_error = ValueError("legacy monitor already FAILED_CLOSED")
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={"run_id": RUN_ID, "runtime_status": "DUE"},
            ),
            patch.object(
                composition,
                "resolve_due_v31_monitor_v2",
                side_effect=resolver_error,
            ),
            patch.object(
                composition,
                "fail_v31_experiment_supervisor_v2",
                return_value={"status": "FAILED_CLOSED"},
            ) as fail,
        ):
            with self.assertRaisesRegex(
                composition.V311SuccessorSingleCycleV1Error,
                "SUPERVISOR_CLOSED",
            ) as caught:
                composition.resolve_v311_successor_outcome_boundary_v1(
                    loaded_context={},
                    authority_projector=Mock(),
                    monitor_store=object(),
                    evidence_store=object(),
                    supervisor_store=object(),
                    research_store=object(),
                    capture_port=object(),
                    run_id=RUN_ID,
                    requested_at="2026-08-07T02:00:00Z",
                )

        fail.assert_called_once()
        self.assertIs(resolver_error, caught.exception.__cause__)

    def test_due_failure_does_not_mask_original_when_supervisor_close_fails(
        self,
    ) -> None:
        resolver_error = ValueError("raw-first capture failed")
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={"run_id": RUN_ID, "runtime_status": "DUE"},
            ),
            patch.object(
                composition,
                "resolve_due_v31_monitor_v2",
                side_effect=resolver_error,
            ),
            patch.object(
                composition,
                "fail_v31_experiment_supervisor_v2",
                side_effect=ValueError("supervisor replay failed"),
            ),
        ):
            with self.assertRaisesRegex(
                composition.V311SuccessorSingleCycleV1Error,
                "AND_SUPERVISOR_FAILURE.*supervisor replay failed",
            ) as caught:
                composition.resolve_v311_successor_outcome_boundary_v1(
                    loaded_context={},
                    authority_projector=Mock(),
                    monitor_store=object(),
                    evidence_store=object(),
                    supervisor_store=object(),
                    research_store=object(),
                    capture_port=object(),
                    run_id=RUN_ID,
                    requested_at="2026-08-07T02:00:00Z",
                )

        self.assertIs(resolver_error, caught.exception.__cause__)

    def test_failed_closed_monitor_replays_supervisor_failure_idempotently(
        self,
    ) -> None:
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "_validate_loaded_support_documents",
                return_value={"clock_policy": {}},
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={
                    "run_id": RUN_ID,
                    "runtime_status": "FAILED_CLOSED",
                },
            ),
            patch.object(composition, "resolve_due_v31_monitor_v2") as resolve,
            patch.object(
                composition,
                "fail_v31_experiment_supervisor_v2",
                return_value={
                    "status": "FAILED_CLOSED",
                    "resume_allowed": False,
                },
            ) as fail,
        ):
            result = composition.resolve_v311_successor_outcome_boundary_v1(
                loaded_context={},
                authority_projector=Mock(),
                monitor_store=object(),
                evidence_store=object(),
                supervisor_store=object(),
                research_store=object(),
                capture_port=object(),
                run_id=RUN_ID,
                requested_at="2026-08-07T02:00:00Z",
            )

        resolve.assert_not_called()
        fail.assert_called_once()
        self.assertEqual(
            "V311_OUTCOME_BOUNDARY_SUPERVISOR_FAILED_CLOSED",
            result["status"],
        )
        self.assertFalse(result["capture_attempted"])
        self.assertFalse(result["next_cycle_opened"])

    def test_final_supervisor_completion_requires_separate_terminal_wake(self) -> None:
        with (
            patch.object(
                composition, "_project_target", return_value=_target_documents()
            ),
            patch.object(
                composition,
                "v31_monitor_status",
                return_value={"run_id": RUN_ID, "runtime_status": "TERMINAL"},
            ),
            patch.object(
                composition,
                "complete_v31_experiment_supervisor_v2",
                return_value={"status": "TERMINAL_COMPLETE"},
            ) as complete,
        ):
            result = composition.complete_v311_successor_terminal_boundary_v1(
                loaded_context={},
                authority_projector=Mock(),
                supervisor_store=object(),
                research_store=object(),
                monitor_store=object(),
                run_id=RUN_ID,
                completed_at="2026-08-07T10:00:00Z",
            )

        complete.assert_called_once()
        self.assertEqual("V311_SUCCESSOR_TERMINAL_COMPLETE", result["status"])
        self.assertFalse(result["capture_attempted"])


if __name__ == "__main__":
    unittest.main()
