from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.application.v31_durable_cycle import (
    V31DurableCycleError,
    persist_completed_v31_cycle,
)
from trade_system.theory_paper_v2.domain.agent_research_contract import (
    seal_v31_agent_proposal,
    seal_v31_inputs_receipt,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
    V31ResearchStoreError,
)


EVENTS = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)
DIGEST_FIELDS = {
    "INPUTS_ADMITTED": "inputs_receipt_digest",
    "PROPOSAL_SEALED": "agent_proposal_digest",
    "EVALUATION_SEALED": "preselection_digest",
    "SELECTION_SEALED": "action_selection_digest",
    "STATE_ACCEPTED": "accepted_state_digest",
    "COMPLETION_SEALED": "completion_receipt_digest",
}
FILENAMES = {
    "INPUTS_ADMITTED": "inputs-receipt.json",
    "PROPOSAL_SEALED": "agent-proposal.json",
    "EVALUATION_SEALED": "cycle-preselection.json",
    "SELECTION_SEALED": "action-selection.json",
    "STATE_ACCEPTED": "accepted-research-state.json",
    "COMPLETION_SEALED": "completion-receipt.json",
}
BINDING_ORDER = [
    "INFORMATION_ADMISSION",
    "CUMULATIVE_INFORMATION_REVISION_REGISTRY",
    "PIT_MARKET_DATASET",
    "CUMULATIVE_DATUM_REVISION_REGISTRY",
    "MULTIDIMENSIONAL_ORDINAL_SENTIMENT_STATE",
    "ORDINAL_SENTIMENT_CHANGE",
    "TRUSTED_ASSOCIATION_ESTIMATION",
    "APPEND_ONLY_GRAPH_DELTA",
    "OPEN_HYPOTHESIS_REGISTRY",
    "APPEND_ONLY_EXPECTATION_LEDGER",
    "PROBABILITY_CLOUD",
    "PROBABILITY_CLOUD_TRANSITION",
    "STRICT_SCENARIO_PATH_SET",
    "THREE_VALUED_PATH_EVALUATION",
    "COMPLETE_ACTION_EVALUATION",
    "PATH_ACTION_ADMISSIBILITY",
    "INDEPENDENT_SELECTION",
]


def chronology_times() -> dict[str, str]:
    return {
        event_type: f"2026-08-06T10:00:{index + 2:02d}Z"
        for index, event_type in enumerate(EVENTS)
    }


def formal_documents(
    *, run_id: str = "v31-fixture", cycle_index: int = 1,
    previous_accepted_state_digest: str | None = None,
    previous_information_revision_registry_digest: str | None = None,
    previous_pit_dataset_digest: str | None = None,
    previous_datum_revision_registry_digest: str | None = None,
    previous_sentiment_state_digest: str | None = None,
    previous_hypothesis_registry_digest: str | None = None,
    previous_expectation_ledger_digest: str | None = None,
    previous_probability_cloud_digest: str | None = None,
) -> dict[str, dict]:
    decision_at = "2026-08-06T10:00:00Z"
    inputs = seal_v31_inputs_receipt(
        run_id=run_id,
        cycle_index=cycle_index,
        decision_at=decision_at,
        symbol="BTC-USDT",
        information_event_digests=("1" * 64,),
        information_revision_registry_digest="0" * 64,
        pit_dataset_digest="2" * 64,
        datum_revision_registry_digest="f" * 64,
        sentiment_state_digest="d" * 64,
        sentiment_change_digest="e" * 64,
        prior_graph_digest="3" * 64,
        previous_accepted_state_digest=previous_accepted_state_digest,
        previous_information_revision_registry_digest=(
            previous_information_revision_registry_digest
        ),
        previous_pit_dataset_digest=previous_pit_dataset_digest,
        previous_datum_revision_registry_digest=(
            previous_datum_revision_registry_digest
        ),
        previous_sentiment_state_digest=previous_sentiment_state_digest,
        previous_hypothesis_registry_digest=previous_hypothesis_registry_digest,
        previous_expectation_ledger_digest=previous_expectation_ledger_digest,
        previous_probability_cloud_digest=previous_probability_cloud_digest,
        authority_snapshot_sha256="4" * 64,
    )
    proposal = seal_v31_agent_proposal(
        inputs_receipt=inputs,
        sentiment_state_digest=inputs["sentiment_state_digest"],
        sentiment_change_digest=inputs["sentiment_change_digest"],
        graph_delta_digest="5" * 64,
        hypothesis_registry_digest="6" * 64,
        expectation_ledger_digest="7" * 64,
        probability_cloud_digest="8" * 64,
        scenario_path_set_digest="9" * 64,
        candidate_bindings={"candidate:WAIT": "a" * 64},
        information_interpretations=("observable public information",),
        competing_explanations=("alternative mechanism remains possible",),
        unknowns=("unobserved account positioning",),
        requested_observations=("next closed bar",),
        hypothesis_novelty_rationales={"hypothesis:fixture": "new testable direction"},
        limitations=("local research fixture only",),
    )
    dynamic_digest = canonical_digest(
        {
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "hypothesis_registry_digest": proposal["hypothesis_registry_digest"],
            "expectation_ledger_digest": proposal["expectation_ledger_digest"],
        }
    )
    path_evaluation = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_path_evaluation",
            "schema_version": "1.0.0",
            "decision_at": decision_at,
            "path_set_digest": proposal["scenario_path_set_digest"],
            "fact_snapshot_digest": "d" * 64,
            "results": [
                {
                    "path_id": "OTHER",
                    "path_digest": "e" * 64,
                    "truth": "TRUE",
                }
            ],
            "logic": "KLEENE_THREE_VALUED_FAIL_CLOSED",
            "false_supports_action": False,
            "unknown_supports_non_wait_action": False,
            "executable": False,
        },
        "path_evaluation_digest",
    )
    candidate_admissibility = [
        {
            "candidate_id": "candidate:WAIT",
            "candidate_proposal_digest": proposal["candidate_bindings"][
                "candidate:WAIT"
            ],
            "candidate_binding_digest": "f" * 64,
            "action": "WAIT",
            "path_assessments": [
                {
                    "path_id": "OTHER",
                    "truth": "TRUE",
                    "implication_effect": "FAVORS",
                    "supports_candidate_now": True,
                }
            ],
            "selectable": True,
            "nonselectable_reasons": [],
        }
    ]
    probability_transition = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_probability_cloud_transition",
            "schema_version": "1.0.0",
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "transition_kind": "GENESIS_ADMISSION",
            "prior_cloud_digest": None,
            "updated_cloud_digest": proposal["probability_cloud_digest"],
            "transition_receipt": None,
            "transition_receipt_digest": None,
            "executable": False,
        },
        "probability_cloud_transition_digest",
    )
    preselection_bindings = {
        "inputs_receipt_digest": inputs["inputs_receipt_digest"],
        "agent_proposal_digest": proposal["agent_proposal_digest"],
        "information_event_digests": inputs["information_event_digests"],
        "information_revision_registry_digest": inputs[
            "information_revision_registry_digest"
        ],
        "association_estimation_receipt_digests": inputs[
            "association_estimation_receipt_digests"
        ],
        "pit_dataset_digest": inputs["pit_dataset_digest"],
        "datum_revision_registry_digest": inputs[
            "datum_revision_registry_digest"
        ],
        "sentiment_state_digest": inputs["sentiment_state_digest"],
        "sentiment_change_digest": inputs["sentiment_change_digest"],
        "prior_graph_digest": inputs["prior_graph_digest"],
        "graph_delta_digest": proposal["graph_delta_digest"],
        "graph_state_digest": "b" * 64,
        "hypothesis_registry_digest": proposal["hypothesis_registry_digest"],
        "expectation_ledger_digest": proposal["expectation_ledger_digest"],
        "dynamic_research_binding_digest": dynamic_digest,
        "probability_cloud_digest": proposal["probability_cloud_digest"],
        "probability_cloud_transition_digest": probability_transition[
            "probability_cloud_transition_digest"
        ],
        "scenario_path_set_digest": proposal["scenario_path_set_digest"],
        "path_evaluation_digest": path_evaluation["path_evaluation_digest"],
        "action_evaluation_digest": "c" * 64,
        "candidate_path_admissibility_digest": canonical_digest(
            candidate_admissibility
        ),
    }
    preselection = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_cycle_preselection",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "symbol": inputs["symbol"],
            **preselection_bindings,
            "probability_cloud_transition": probability_transition,
            "path_evaluation": path_evaluation,
            "candidate_path_admissibility": candidate_admissibility,
            "selectable_candidate_ids": ["candidate:WAIT"],
            "artifact_bindings_digest": canonical_digest(preselection_bindings),
            "binding_order": BINDING_ORDER,
            "graph_chain_policy": "STRICT_ADJACENT_EPISTEMIC_STAGES",
            "selection_fields_admitted": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "preselection_digest",
    )
    selection = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_action_selection",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "action_evaluation_digest": preselection["action_evaluation_digest"],
            "selected_candidate_id": "candidate:WAIT",
            "selected_action": "WAIT",
            "reason": "preserve reversibility under uncertainty",
            "alternative_explanations": {},
            "failure_conditions": ["new evidence invalidates the wait thesis"],
            "next_review_at": "2026-08-06T11:00:00Z",
            "selected_at": "2026-08-06T10:00:01Z",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "action_selection_digest",
    )
    accepted = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_accepted_research_state",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "selected_at": selection["selected_at"],
            "symbol": inputs["symbol"],
            "inputs_receipt_digest": inputs["inputs_receipt_digest"],
            "preselection_digest": preselection["preselection_digest"],
            "artifact_bindings_digest": preselection["artifact_bindings_digest"],
            "pit_dataset_digest": preselection["pit_dataset_digest"],
            "information_revision_registry_digest": preselection[
                "information_revision_registry_digest"
            ],
            "datum_revision_registry_digest": preselection[
                "datum_revision_registry_digest"
            ],
            "sentiment_state_digest": preselection[
                "sentiment_state_digest"
            ],
            "sentiment_change_digest": preselection[
                "sentiment_change_digest"
            ],
            "graph_state_digest": preselection["graph_state_digest"],
            "hypothesis_registry_digest": preselection["hypothesis_registry_digest"],
            "expectation_ledger_digest": preselection["expectation_ledger_digest"],
            "dynamic_research_binding_digest": preselection["dynamic_research_binding_digest"],
            "probability_cloud_digest": preselection[
                "probability_cloud_digest"
            ],
            "probability_cloud_transition_digest": preselection[
                "probability_cloud_transition_digest"
            ],
            "scenario_path_set_digest": preselection[
                "scenario_path_set_digest"
            ],
            "path_evaluation_digest": preselection["path_evaluation_digest"],
            "action_evaluation_digest": preselection["action_evaluation_digest"],
            "action_selection_digest": selection["action_selection_digest"],
            "agent_proposal_digest": proposal["agent_proposal_digest"],
            "selected_candidate_id": selection["selected_candidate_id"],
            "selected_candidate_evaluation_digest": candidate_admissibility[0]["candidate_binding_digest"],
            "status": "ACCEPTED_RESEARCH_ONLY",
            "selection_boundary": "SEPARATE_AFTER_COMPLETE_EVALUATION",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "accepted_state_digest",
    )
    completion = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_completion_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "selected_at": accepted["selected_at"],
            "completed_at": "2026-08-06T10:00:02Z",
            "inputs_receipt_digest": accepted["inputs_receipt_digest"],
            "accepted_state_digest": accepted["accepted_state_digest"],
            "preselection_digest": accepted["preselection_digest"],
            "artifact_bindings_digest": accepted["artifact_bindings_digest"],
            "pit_dataset_digest": accepted["pit_dataset_digest"],
            "information_revision_registry_digest": accepted[
                "information_revision_registry_digest"
            ],
            "datum_revision_registry_digest": accepted[
                "datum_revision_registry_digest"
            ],
            "sentiment_state_digest": accepted["sentiment_state_digest"],
            "sentiment_change_digest": accepted["sentiment_change_digest"],
            "graph_state_digest": accepted["graph_state_digest"],
            "hypothesis_registry_digest": accepted["hypothesis_registry_digest"],
            "expectation_ledger_digest": accepted["expectation_ledger_digest"],
            "dynamic_research_binding_digest": accepted["dynamic_research_binding_digest"],
            "probability_cloud_digest": accepted["probability_cloud_digest"],
            "probability_cloud_transition_digest": accepted[
                "probability_cloud_transition_digest"
            ],
            "scenario_path_set_digest": accepted[
                "scenario_path_set_digest"
            ],
            "path_evaluation_digest": accepted["path_evaluation_digest"],
            "action_selection_digest": accepted["action_selection_digest"],
            "selected_candidate_id": accepted["selected_candidate_id"],
            "completion_status": "COMPLETE_RESEARCH_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "completion_receipt_digest",
    )
    return dict(zip(EVENTS, (inputs, proposal, preselection, selection, accepted, completion)))


def open_checkpoint(store: LocalV31ResearchStore) -> dict:
    checkpoint = store.initialize_checkpoint(
        run_id="v31-fixture", total_cycles=1, created_at="2026-08-06T10:00:00Z"
    )
    return dict(
        store.replace_checkpoint(
            run_id="v31-fixture",
            expected_checkpoint_digest=checkpoint["checkpoint_digest"],
            checkpoint={
                **checkpoint,
                "revision": 1,
                "status": "CYCLE_IN_PROGRESS",
                "active_cycle_index": 1,
                "updated_at": "2026-08-06T10:00:01Z",
            },
        )
    )


def genesis_bindings() -> dict[str, str]:
    return {
        "theory_approval_ref": "genesis/theory-approval.json",
        "theory_approval_digest": "1" * 64,
        "experiment_manifest_ref": "genesis/experiment-manifest.json",
        "experiment_manifest_digest": "2" * 64,
        "experiment_authorization_ref": "genesis/experiment-authorization.json",
        "experiment_authorization_digest": "3" * 64,
        "current_authority_ref": "genesis/current-authority.json",
        "current_authority_digest": "4" * 64,
        "run_genesis_ref": "genesis/run-genesis.json",
        "run_genesis_digest": "5" * 64,
    }


class V31ResearchStoreTests(unittest.TestCase):
    def test_raw_bytes_are_write_once_and_verified_on_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            payload = b'{"public":"source"}\n'
            binding = store.write_raw(
                relative_ref="qualification/raw/time.json", payload=payload
            )
            self.assertEqual(binding["semantic_digest"], binding["physical_sha256"])
            self.assertEqual(
                payload,
                store.read_raw(
                    relative_ref="qualification/raw/time.json",
                    expected_sha256=binding["physical_sha256"],
                ),
            )
            store.write_raw(
                relative_ref="qualification/raw/time.json", payload=payload
            )
            with self.assertRaisesRegex(
                V31ResearchStoreError, "V31_RAW_WRITE_ONCE_CONFLICT"
            ):
                store.write_raw(
                    relative_ref="qualification/raw/time.json", payload=b"changed"
                )
            with self.assertRaisesRegex(
                V31ResearchStoreError, "V31_RAW_DIGEST_MISMATCH"
            ):
                store.read_raw(
                    relative_ref="qualification/raw/time.json",
                    expected_sha256="f" * 64,
                )

    def test_artifact_paths_reject_symlink_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "real").mkdir()
            (root / "linked").symlink_to(root / "real", target_is_directory=True)
            store = LocalV31ResearchStore(root)
            with self.assertRaisesRegex(
                V31ResearchStoreError, "V31_ARTIFACT_REF_INVALID"
            ):
                store.write_raw(
                    relative_ref="linked/capture.json", payload=b"public"
                )

    def test_checkpoint_12_binds_complete_immutable_genesis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            bindings = genesis_bindings()
            checkpoint = store.initialize_checkpoint(
                run_id="v31-bound",
                total_cycles=8,
                created_at="2026-08-06T10:00:00Z",
                genesis_bindings=bindings,
            )
            self.assertEqual("1.2.0", checkpoint["schema_version"])
            self.assertEqual(bindings["run_genesis_digest"], checkpoint[
                "run_genesis_digest"
            ])
            self.assertEqual([], checkpoint["transport_evidence_bindings"])
            with self.assertRaisesRegex(
                V31ResearchStoreError,
                "V31_CHECKPOINT_GENESIS_BINDING_CONFLICT",
            ):
                store.initialize_checkpoint(
                    run_id="v31-bound",
                    total_cycles=8,
                    created_at="2026-08-06T10:00:00Z",
                    genesis_bindings={
                        **bindings,
                        "run_genesis_digest": "6" * 64,
                    },
                )
            with self.assertRaisesRegex(
                V31ResearchStoreError, "V31_CHECKPOINT_TRANSITION_INVALID"
            ):
                store.replace_checkpoint(
                    run_id="v31-bound",
                    expected_checkpoint_digest=checkpoint["checkpoint_digest"],
                    checkpoint={
                        **checkpoint,
                        "revision": 1,
                        "status": "CYCLE_IN_PROGRESS",
                        "active_cycle_index": 1,
                        "theory_approval_digest": "9" * 64,
                        "updated_at": "2026-08-06T10:00:01Z",
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            with self.assertRaisesRegex(
                V31ResearchStoreError,
                "V31_CHECKPOINT_GENESIS_BINDING_INVALID",
            ):
                store.initialize_checkpoint(
                    run_id="v31-partial",
                    total_cycles=8,
                    created_at="2026-08-06T10:00:00Z",
                    genesis_bindings={
                        "theory_approval_ref": "genesis/theory-approval.json",
                        "theory_approval_digest": "1" * 64,
                    },
                )

    def test_failure_checkpoint_is_physical_fail_closed_and_not_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            opened = open_checkpoint(store)
            failed = store.fail_checkpoint(
                run_id="v31-fixture",
                expected_checkpoint_digest=opened["checkpoint_digest"],
                failure_code="FIXTURE_PERMANENT_FAILURE",
                failure_summary="The synthetic cycle cannot continue safely.",
                occurred_at="2026-08-06T10:00:02Z",
            )
            self.assertEqual("FAILED_CLOSED", failed["status"])
            self.assertFalse(failed["resume_allowed"])
            failure = store.read_document(
                relative_ref=failed["failure_ref"],
                digest_field="failure_digest",
                expected_semantic_digest=failed["failure_digest"],
            )
            self.assertEqual(opened["checkpoint_digest"], failure[
                "checkpoint_digest_before_failure"
            ])
            with self.assertRaisesRegex(
                V31ResearchStoreError,
                "V31_CHECKPOINT_TERMINAL_TRANSITION_FORBIDDEN",
            ):
                store.replace_checkpoint(
                    run_id="v31-fixture",
                    expected_checkpoint_digest=failed["checkpoint_digest"],
                    checkpoint={
                        **failed,
                        "revision": failed["revision"] + 1,
                        "status": "CYCLE_IN_PROGRESS",
                        "active_cycle_index": 1,
                        "failure_ref": None,
                        "failure_digest": None,
                        "resume_allowed": True,
                        "updated_at": "2026-08-06T10:00:03Z",
                    },
                )

    def test_formal_chain_advances_and_arbitrary_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            opened = open_checkpoint(store)
            documents = formal_documents()
            bindings = []
            for event_type in EVENTS:
                binding = store.write_document(
                    relative_ref=f"cycles/0001/{FILENAMES[event_type]}",
                    document=documents[event_type],
                    digest_field=DIGEST_FIELDS[event_type],
                )
                bindings.append(binding)
                store.append_event(
                    run_id="v31-fixture",
                    cycle_index=1,
                    event_type=event_type,
                    artifact_binding=binding,
                    recorded_at=chronology_times()[event_type],
                )
            with self.assertRaisesRegex(
                V31ResearchStoreError,
                "V31_CHECKPOINT_SEMANTIC_VERIFICATION_REQUIRED",
            ):
                store.replace_checkpoint(
                    run_id="v31-fixture",
                    expected_checkpoint_digest=opened["checkpoint_digest"],
                    checkpoint={
                        **opened,
                        "revision": 2,
                        "status": "TERMINAL",
                        "completed_cycles": 1,
                        "next_cycle_index": 2,
                        "active_cycle_index": None,
                        "accepted_state_ref": bindings[-2]["relative_ref"],
                        "accepted_state_digest": bindings[-2]["semantic_digest"],
                        "accepted_pit_dataset_ref": (
                            "cycles/0001/pit-dataset.json"
                        ),
                        "accepted_pit_dataset_digest": documents["STATE_ACCEPTED"][
                            "pit_dataset_digest"
                        ],
                        "accepted_information_revision_registry_ref": (
                            "cycles/0001/information-revision-registry.json"
                        ),
                        "accepted_information_revision_registry_digest": documents[
                            "STATE_ACCEPTED"
                        ]["information_revision_registry_digest"],
                        "accepted_datum_revision_registry_ref": (
                            "cycles/0001/datum-revision-registry.json"
                        ),
                        "accepted_datum_revision_registry_digest": documents[
                            "STATE_ACCEPTED"
                        ]["datum_revision_registry_digest"],
                        "accepted_sentiment_state_digest": documents[
                            "STATE_ACCEPTED"
                        ]["sentiment_state_digest"],
                        "accepted_sentiment_state_ref": (
                            "cycles/0001/sentiment-state.json"
                        ),
                        "accepted_sentiment_change_digest": documents[
                            "STATE_ACCEPTED"
                        ]["sentiment_change_digest"],
                        "accepted_graph_state_ref": (
                            "cycles/0001/graph-state.json"
                        ),
                        "accepted_graph_state_digest": documents["STATE_ACCEPTED"][
                            "graph_state_digest"
                        ],
                        "accepted_hypothesis_registry_ref": (
                            "cycles/0001/hypothesis-registry.json"
                        ),
                        "accepted_hypothesis_registry_digest": documents[
                            "STATE_ACCEPTED"
                        ]["hypothesis_registry_digest"],
                        "accepted_expectation_ledger_ref": (
                            "cycles/0001/expectation-ledger.json"
                        ),
                        "accepted_expectation_ledger_digest": documents[
                            "STATE_ACCEPTED"
                        ]["expectation_ledger_digest"],
                        "accepted_probability_cloud_ref": (
                            "cycles/0001/probability-cloud.json"
                        ),
                        "accepted_probability_cloud_digest": documents[
                            "STATE_ACCEPTED"
                        ]["probability_cloud_digest"],
                        "accepted_probability_cloud_transition_digest": documents[
                            "STATE_ACCEPTED"
                        ]["probability_cloud_transition_digest"],
                        "last_completion_ref": bindings[-1]["relative_ref"],
                        "last_completion_digest": bindings[-1]["semantic_digest"],
                        "updated_at": "2026-08-06T10:00:09Z",
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            open_checkpoint(store)
            arbitrary = self_digest(
                {
                    "schema_id": "fixture-artifact",
                    "schema_version": "1.0.0",
                    "run_id": "v31-fixture",
                    "cycle_index": 1,
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "artifact_digest",
            )
            binding = store.write_document(
                relative_ref="cycles/0001/arbitrary.json",
                document=arbitrary,
                digest_field="artifact_digest",
            )
            with self.assertRaisesRegex(
                V31ResearchStoreError, "V31_EVENT_ARTIFACT_CONTRACT_INVALID"
            ):
                store.append_event(
                    run_id="v31-fixture", cycle_index=1,
                    event_type="INPUTS_ADMITTED", artifact_binding=binding,
                    recorded_at="2026-08-06T10:00:02Z",
                )

    def test_resigned_cross_binding_mismatch_fails_before_event_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            open_checkpoint(store)
            documents = formal_documents()
            for event_type in EVENTS[:2]:
                binding = store.write_document(
                    relative_ref=f"cycles/0001/{FILENAMES[event_type]}",
                    document=documents[event_type],
                    digest_field=DIGEST_FIELDS[event_type],
                )
                store.append_event(
                    run_id="v31-fixture", cycle_index=1,
                    event_type=event_type, artifact_binding=binding,
                    recorded_at=chronology_times()[event_type],
                )
            tampered = dict(documents["EVALUATION_SEALED"])
            tampered["graph_delta_digest"] = "f" * 64
            binding_payload = {
                field: tampered[field]
                for field in (
                    "inputs_receipt_digest", "agent_proposal_digest",
                    "information_event_digests",
                    "information_revision_registry_digest",
                    "pit_dataset_digest", "datum_revision_registry_digest",
                    "sentiment_state_digest", "sentiment_change_digest",
                    "association_estimation_receipt_digests",
                    "prior_graph_digest", "graph_delta_digest", "graph_state_digest",
                    "hypothesis_registry_digest", "expectation_ledger_digest",
                    "dynamic_research_binding_digest", "probability_cloud_digest",
                    "probability_cloud_transition_digest",
                    "scenario_path_set_digest", "path_evaluation_digest",
                    "action_evaluation_digest",
                    "candidate_path_admissibility_digest",
                )
            }
            tampered["artifact_bindings_digest"] = canonical_digest(binding_payload)
            tampered = self_digest(tampered, "preselection_digest")
            binding = store.write_document(
                relative_ref="cycles/0001/tampered-preselection.json",
                document=tampered,
                digest_field="preselection_digest",
            )
            with self.assertRaisesRegex(
                V31ResearchStoreError, "V31_PROPOSAL_EVALUATION_BINDING_INVALID"
            ):
                store.append_event(
                    run_id="v31-fixture", cycle_index=1,
                    event_type="EVALUATION_SEALED", artifact_binding=binding,
                    recorded_at=chronology_times()["EVALUATION_SEALED"],
                )

    def test_wait_candidate_cannot_be_resigned_as_open_long(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            open_checkpoint(store)
            documents = formal_documents()
            times = chronology_times()
            for event_type in EVENTS[:3]:
                binding = store.write_document(
                    relative_ref=f"cycles/0001/{FILENAMES[event_type]}",
                    document=documents[event_type],
                    digest_field=DIGEST_FIELDS[event_type],
                )
                store.append_event(
                    run_id="v31-fixture",
                    cycle_index=1,
                    event_type=event_type,
                    artifact_binding=binding,
                    recorded_at=times[event_type],
                )
            forged = dict(documents["SELECTION_SEALED"])
            forged.pop("action_selection_digest")
            forged["selected_action"] = "OPEN_LONG"
            forged = self_digest(forged, "action_selection_digest")
            binding = store.write_document(
                relative_ref="cycles/0001/forged-selection.json",
                document=forged,
                digest_field="action_selection_digest",
            )
            with self.assertRaisesRegex(
                V31ResearchStoreError,
                "V31_SELECTION_EVALUATION_BINDING_INVALID",
            ):
                store.append_event(
                    run_id="v31-fixture",
                    cycle_index=1,
                    event_type="SELECTION_SEALED",
                    artifact_binding=binding,
                    recorded_at=times["SELECTION_SEALED"],
                )

    def test_coordinator_resumes_prefix_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            open_checkpoint(store)
            documents = formal_documents()
            times = chronology_times()
            for event_type in EVENTS[:2]:
                binding = store.write_document(
                    relative_ref=f"cycles/0001/{FILENAMES[event_type]}",
                    document=documents[event_type],
                    digest_field=DIGEST_FIELDS[event_type],
                )
                store.append_event(
                    run_id="v31-fixture", cycle_index=1,
                    event_type=event_type, artifact_binding=binding,
                    recorded_at=times[event_type],
                )
            with self.assertRaisesRegex(
                V31DurableCycleError,
                "V31_DURABLE_SEMANTIC_SOURCE_BINDING_MISMATCH",
            ):
                persist_completed_v31_cycle(
                    store=store, run_id="v31-fixture", cycle_index=1,
                    total_cycles=1, created_at="2026-08-06T10:00:00Z",
                    documents=documents, assembly_inputs={},
                    recorded_at_by_event=times,
                )

    def test_physical_artifact_drift_breaks_event_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalV31ResearchStore(root)
            open_checkpoint(store)
            documents = formal_documents()
            inputs = documents["INPUTS_ADMITTED"]
            binding = store.write_document(
                relative_ref="cycles/0001/inputs-receipt.json",
                document=inputs,
                digest_field="inputs_receipt_digest",
            )
            store.append_event(
                run_id="v31-fixture", cycle_index=1,
                event_type="INPUTS_ADMITTED", artifact_binding=binding,
                recorded_at="2026-08-06T10:00:02Z",
            )
            target = root / "cycles/0001/inputs-receipt.json"
            altered = formal_documents(run_id="different-run")["INPUTS_ADMITTED"]
            target.write_bytes(canonical_bytes(altered) + b"\n")
            with self.assertRaisesRegex(
                V31ResearchStoreError, "V31_EVENT_ARTIFACT_PHYSICAL_DRIFT"
            ):
                store.read_events(run_id="v31-fixture", cycle_index=1)


if __name__ == "__main__":
    unittest.main()
