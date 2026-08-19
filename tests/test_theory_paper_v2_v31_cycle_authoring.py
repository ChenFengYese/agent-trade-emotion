from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from typing import Any, Mapping

from trade_system.theory_paper_v2.application.v31_agent_transport import (
    initialize_v31_agent_transport,
    run_v31_authoring_transport,
)
from trade_system.theory_paper_v2.application.v31_cycle_authoring import (
    V31CycleAuthoringWorkflowError,
    compile_v31_agent_open_analysis,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.dynamic_research import V31_SENTIMENT_AXES
from trade_system.theory_paper_v2.domain.v31_cycle_authoring import (
    V31CycleAuthoringError,
    seal_v31_agent_open_analysis_envelope,
    seal_v31_proposal_authoring_packet,
    validate_v31_agent_open_analysis_envelope,
    validate_v31_proposal_authoring_packet,
)
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    build_minimal_experiment_contract,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)


RUN_ID = "run:v31:production-authoring-contract"
DECISION_AT = "2026-08-06T16:19:35Z"
SYMBOL = "BTC-USDT-SWAP"


def _head_bindings() -> dict[str, None]:
    return {
        "previous_accepted_state": None,
        "previous_information_revision_registry": None,
        "previous_pit_dataset": None,
        "previous_datum_revision_registry": None,
        "previous_sentiment_state": None,
        "previous_hypothesis_registry": None,
        "previous_expectation_ledger": None,
        "previous_probability_cloud": None,
    }


def _binding(
    *, ref: str, schema_id: str, digest_field: str, digest: str
) -> dict[str, str]:
    return {
        "relative_ref": ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": digest,
        "physical_sha256": "f" * 64,
    }


def _contract_packet() -> dict[str, Any]:
    return seal_v31_proposal_authoring_packet(
        run_id=RUN_ID,
        cycle_index=1,
        decision_at=DECISION_AT,
        symbol=SYMBOL,
        cycle_source_admission_binding=None,
        source_qualification_completion_binding=_binding(
            ref="source/source-qualification-completion.json",
            schema_id="theory_paper_v31_source_qualification_completion",
            digest_field="source_qualification_completion_digest",
            digest="1" * 64,
        ),
        information_event_bindings=(
            _binding(
                ref="source/information-event-0001.json",
                schema_id=(
                    "theory_paper_v31_source_qualification_information_event"
                ),
                digest_field=(
                    "source_qualification_information_event_record_digest"
                ),
                digest="2" * 64,
            ),
        ),
        pit_dataset_binding=_binding(
            ref="source/pit-dataset.json",
            schema_id="theory_paper_v2_v31_point_in_time_dataset",
            digest_field="dataset_digest",
            digest="3" * 64,
        ),
        authoring_purpose="TRANSPORT_QUALIFICATION_ONLY",
        theory_approval_binding=_binding(
            ref="qualification/theory-approval.json",
            schema_id="theory_paper_v31_user_approval_receipt",
            digest_field="approval_receipt_digest",
            digest="4" * 64,
        ),
        experiment_subject_binding=_binding(
            ref="qualification/experiment-subject.json",
            schema_id="theory_paper_v2_v31_minimal_experiment_contract",
            digest_field="experiment_contract_digest",
            digest="5" * 64,
        ),
        active_authority_binding=None,
        previous_head_bindings=_head_bindings(),
    )


def _sentiment_rows() -> list[dict[str, Any]]:
    return [
        {
            "axis": axis,
            "ordinal_state": "UNKNOWN",
            "evidence_assessments": [],
            "required_dependency_groups": [f"UNKNOWN:{axis}"],
            "timeframe_states": {"1H": None},
            "reasoning": "The admitted evidence does not justify a directional state.",
            "limitations": ["UNKNOWN is preserved and is not treated as neutral."],
            "next_discriminating_observation": (
                "Observe the next independent closed market-data window."
            ),
        }
        for axis in V31_SENTIMENT_AXES
    ]


def _action_spec(action: str, path_id: str) -> dict[str, Any]:
    wait = action == "WAIT"
    return {
        "candidate_id": f"candidate:{action.lower()}",
        "action": action,
        "scale_pct": None if wait else 25,
        "target_role": None if wait else "TACTICAL",
        "path_refs": [path_id],
        "evidence_refs": ["datum:qualified-market-state"],
        "trigger_conditions": ["The bound path conditions remain admitted."],
        "invalidation_conditions": ["A registered falsifier becomes true."],
        "risk_refs": ["risk:uncalibrated-public-snapshot"],
        "thesis": "Open non-executable candidate for deterministic comparison.",
        "wait_reason": "Uncertainty remains uncalibrated." if wait else None,
        "opportunity_cost": "A move may begin before review." if wait else None,
        "next_observation": "Observe the next closed 1H bar." if wait else None,
        "next_review_at": "2026-08-06T17:19:35Z" if wait else None,
        "information_not_arrived_default": (
            "Preserve the flat shadow state." if wait else None
        ),
        "position_protection_responsibility": (
            "Recheck the frozen risk limits at review." if wait else None
        ),
    }


def _path_spec(path_id: str, hypothesis_id: str, action: str) -> dict[str, Any]:
    return {
        "path_id": path_id,
        "triggers": [
            {
                "predicate_id": f"trigger:{path_id}",
                "fact_ref": "datum:qualified-market-state",
                "timing": "DECISION_INPUT",
                "operator": "EXISTS",
                "expected": None,
                "available_at": DECISION_AT,
                "minimum_quality": "MEDIUM",
                "minimum_coverage": "1",
                "allowed_conflict_states": ["NONE"],
                "limitations": ["Qualification contract shape only."],
            }
        ],
        "guards": [
            {
                "predicate_id": f"guard:{path_id}",
                "fact_ref": "datum:qualified-market-state",
                "timing": "DECISION_INPUT",
                "operator": "EXISTS",
                "expected": None,
                "available_at": DECISION_AT,
                "minimum_quality": "MEDIUM",
                "minimum_coverage": "1",
                "allowed_conflict_states": ["NONE"],
                "limitations": ["Qualification contract shape only."],
            }
        ],
        "unless": [],
        "transition": {
            "from_stage": "ASSOCIATION",
            "to_stage": "INFERENCE",
            "target_ref": f"inference:{path_id}",
            "update_type": "ADD",
        },
        "mechanism": "Open, falsifiable qualification path.",
        "mechanism_hypothesis_refs": [hypothesis_id],
        "expectations": [
            {
                "observation_id": f"expectation:{path_id}",
                "hypothesis_id": hypothesis_id,
                "observable_ref": "datum:qualified-market-state",
                "horizon_at": "2026-08-06T17:19:35Z",
                "direction_or_state": "remains discriminating",
                "confirms_when": "the registered condition persists",
                "contradicts_when": "the registered condition reverses",
            }
        ],
        "falsifiers": [
            {
                "predicate_id": f"falsifier:{path_id}",
                "fact_ref": "future:closed-1h",
                "timing": "FUTURE_MONITOR",
                "operator": "EXISTS",
                "expected": None,
                "available_at": "2026-08-06T17:19:35Z",
                "minimum_quality": "MEDIUM",
                "minimum_coverage": "1",
                "allowed_conflict_states": ["NONE"],
                "limitations": ["Future evidence is not yet available."],
            }
        ],
        "else_path_refs": [],
        "preserves_other_unknown": True,
        "action_implications": [
            {
                "action": action,
                "effect": "FAVORS" if action == "WAIT" else "CONDITIONAL",
                "rationale": "Only the exact registered action class is implicated.",
                "risk_refs": ["risk:uncalibrated-public-snapshot"],
                "opportunity_cost": "The conditional path may still be wrong.",
            }
        ],
        "expires_at": "2026-08-06T18:19:35Z",
        "next_review_at": "2026-08-06T17:19:35Z",
        "next_observation": "Observe the next closed 1H bar.",
        "regime_refs": [],
        "probability_cloud_refs": [],
    }


def _envelope(packet: Mapping[str, Any]) -> dict[str, Any]:
    return seal_v31_agent_open_analysis_envelope(
        authoring_packet=packet,
        information_interpretations=(
            "Public evidence cannot reveal private positioning or intent.",
            "The public snapshot is evidence of market state, not trader intent.",
        ),
        operational_synthesis=(
            "All twelve axes remain UNKNOWN under the qualification-only packet."
        ),
        sentiment_axis_analyses=_sentiment_rows(),
        graph_delta_spec={
            "projection_id": "LOCAL_V31_PRODUCTION_SEMANTIC_COMPILER_1_0_0",
            "graph_id": "graph:v31:qualification",
            "delta_id": "delta:v31:qualification:1",
            "projection_policy": "EXACT_TYPED_ARTIFACT_VERTICAL_PROJECTION_V1",
            "additional_associations": [],
            "rationale": "Keep observed facts separate from open explanations.",
        },
        hypothesis_deltas=(
            {
                "operation": "CREATE",
                "hypothesis_id": "path:continuation",
                "directional_bias": "LONG",
                "evidence_refs": ["datum:qualified-market-state"],
                "hard_falsifiers": ["closed 1H structure reverses"],
            },
            {
                "operation": "CREATE",
                "hypothesis_id": "path:reversal",
                "directional_bias": "SHORT",
                "evidence_refs": ["datum:qualified-market-state"],
                "hard_falsifiers": ["closed 1H continuation persists"],
            },
        ),
        expectation_deltas=(
            {
                "operation": "CREATE",
                "expectation_id": "expectation:continuation",
                "hypothesis_id": "path:continuation",
                "if_then": "If continuation persists, the next closed 1H structure confirms.",
            },
            {
                "operation": "CREATE",
                "expectation_id": "expectation:reversal",
                "hypothesis_id": "path:reversal",
                "if_then": "If reversal dominates, the next closed 1H structure contradicts continuation.",
            },
        ),
        probability_cloud_spec={
            "mode": "SUBJECTIVE_PLAUSIBILITY",
            "horizon": "next closed 1H bar",
            "components": [
                {
                    "hypothesis_id": "path:continuation",
                    "plausibility": "MEDIUM",
                    "evidence_refs": ["datum:qualified-market-state"],
                    "opposition_refs": [],
                    "conflict_refs": [],
                    "dependency_groups": [],
                    "data_uncertainty": ["Single public snapshot."],
                    "model_uncertainty": ["No calibrated model."],
                    "sensitivity_notes": ["Sensitive to the next closed bar."],
                },
                {
                    "hypothesis_id": "path:reversal",
                    "plausibility": "MEDIUM",
                    "evidence_refs": ["datum:qualified-market-state"],
                    "opposition_refs": [],
                    "conflict_refs": [],
                    "dependency_groups": [],
                    "data_uncertainty": ["Single public snapshot."],
                    "model_uncertainty": ["No calibrated model."],
                    "sensitivity_notes": ["Sensitive to the next closed bar."],
                },
                {
                    "hypothesis_id": "OTHER",
                    "plausibility": "MEDIUM",
                    "evidence_refs": [],
                    "opposition_refs": [],
                    "conflict_refs": [],
                    "dependency_groups": [],
                    "data_uncertainty": ["Unmodelled mechanisms."],
                    "model_uncertainty": ["Residual component."],
                    "sensitivity_notes": ["Unmodelled mechanisms remain open."],
                },
                {
                    "hypothesis_id": "UNKNOWN",
                    "plausibility": "UNKNOWN",
                    "evidence_refs": [],
                    "opposition_refs": [],
                    "conflict_refs": [],
                    "dependency_groups": [],
                    "data_uncertainty": ["Unknown inputs remain."],
                    "model_uncertainty": ["No calibrated model."],
                    "sensitivity_notes": ["No calibrated distribution exists."],
                },
            ],
            "unknown_refs": ["private positioning and intent are unavailable"],
            "limitations": ["Ordinal plausibility is not a numerical probability."],
        },
        scenario_path_set_spec={
            "set_id": "paths:open-analysis",
            "lead_path_id": "path:continuation",
            "runner_up_path_id": "path:reversal",
            "residual_path_id": "OTHER",
            "paths": [
                _path_spec("path:continuation", "path:continuation", "OPEN_LONG"),
                _path_spec("path:reversal", "path:reversal", "OPEN_SHORT"),
                _path_spec("OTHER", "path:continuation", "WAIT"),
            ],
        },
        action_candidate_specs=(
            _action_spec("WAIT", "OTHER"),
            _action_spec("OPEN_LONG", "path:continuation"),
            _action_spec("OPEN_SHORT", "path:reversal"),
        ),
        competing_explanations=(
            "A common market shock may explain the same observations.",
        ),
        unknowns=("Private positioning and intent remain unknown.",),
        requested_observations=("Observe the next independent closed 1H bar.",),
        hypothesis_novelty_rationales={
            "path:continuation": "Distinct persistence mechanism and falsifier.",
            "path:reversal": "Distinct reversal mechanism and falsifier.",
        },
        limitations=("Open analysis is not a prediction or trading authority.",),
    )


def _write_materials_and_packet(
    store: LocalV31AgentTransportStore,
) -> tuple[dict[str, Any], dict[str, str]]:
    event_digest = "e" * 64
    with store.owner_lease(
        owner_id="source-material-writer",
        acquired_at="2026-08-06T09:00:00Z",
        expires_at="2026-08-06T09:59:59Z",
    ) as lease:
        event = self_digest(
            {
                "schema_id": (
                    "theory_paper_v31_source_qualification_information_event"
                ),
                "information_event_digest": event_digest,
            },
            "source_qualification_information_event_record_digest",
        )
        event_binding = store.write_document(
            lease=lease,
            relative_ref="source/information-event-0001.json",
            document=event,
            digest_field=(
                "source_qualification_information_event_record_digest"
            ),
        )
        dataset = self_digest(
            {
                "schema_id": "theory_paper_v2_v31_point_in_time_dataset",
                "decision_at": DECISION_AT,
            },
            "dataset_digest",
        )
        dataset_binding = store.write_document(
            lease=lease,
            relative_ref="source/pit-dataset.json",
            document=dataset,
            digest_field="dataset_digest",
        )
        completion = self_digest(
            {
                "schema_id": "theory_paper_v31_source_qualification_completion",
                "pit_dataset_digest": dataset["dataset_digest"],
                "information_event_digests": [event_digest],
            },
            "source_qualification_completion_digest",
        )
        completion_binding = store.write_document(
            lease=lease,
            relative_ref="source/source-qualification-completion.json",
            document=completion,
            digest_field="source_qualification_completion_digest",
        )
        approval = self_digest(
            {
                "schema_id": "theory_paper_v31_user_approval_receipt",
                "schema_version": "1.0.0",
                "approval_id": "approval:v31:authoring-test",
                "approved_at": "2026-08-06T08:00:00Z",
                "approval_source": "CURRENT_CODEX_TASK_USER_MESSAGE",
                "user_statement": "我批准，并授权实验",
                "theory_path": "theory/history/RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md",
                "theory_version": "3.1",
                "theory_physical_sha256": "a" * 64,
                "approval_scope": [
                    "FROZEN_V3_1_THEORY_AUTHORITY",
                    "SOLE_FRESH_BTC_USDT_PUBLIC_DATA_NON_EXECUTABLE_PROSPECTIVE_EXPERIMENT_AFTER_Q0_Q8",
                ],
                "experiment_authorization_status": (
                    "CONDITIONAL_ON_Q0_Q8_AND_EXACT_RUN_MANIFEST_RECEIPT_BINDING"
                ),
                "excluded_authority": [
                    "RESUME_LEGACY_RUN",
                    "ACCOUNT_ACCESS",
                    "PAPER_TRADING",
                    "LIVE_TRADING",
                    "ORDER_SUBMISSION",
                    "CREDENTIAL_ACCESS",
                    "FUNDS_ACCESS",
                ],
                "legacy_runs_resumable": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "approval_receipt_digest",
        )
        approval_binding = store.write_document(
            lease=lease,
            relative_ref="qualification/theory-approval.json",
            document=approval,
            digest_field="approval_receipt_digest",
        )
        subject = build_minimal_experiment_contract(
            contract_id="contract:v31:authoring-test",
            run_id=RUN_ID,
            frozen_at="2026-08-06T08:05:00Z",
        )
        subject_binding = store.write_document(
            lease=lease,
            relative_ref="qualification/experiment-subject.json",
            document=subject,
            digest_field="experiment_contract_digest",
        )
        packet = seal_v31_proposal_authoring_packet(
            run_id=RUN_ID,
            cycle_index=1,
            decision_at=DECISION_AT,
            symbol=SYMBOL,
            cycle_source_admission_binding=None,
            source_qualification_completion_binding=completion_binding,
            information_event_bindings=(event_binding,),
            pit_dataset_binding=dataset_binding,
            authoring_purpose="TRANSPORT_QUALIFICATION_ONLY",
            theory_approval_binding=approval_binding,
            experiment_subject_binding=subject_binding,
            active_authority_binding=None,
            previous_head_bindings=_head_bindings(),
        )
        packet_binding = store.write_document(
            lease=lease,
            relative_ref="cycles/0001/proposal-authoring-packet.json",
            document=packet,
            digest_field="authoring_packet_digest",
        )
    return packet, packet_binding


def _times(minute: int) -> dict[str, str]:
    return {
        "reserved_at": f"2026-08-06T10:{minute:02d}:00Z",
        "requested_at": f"2026-08-06T10:{minute:02d}:01Z",
        "claimed_at": f"2026-08-06T10:{minute:02d}:02Z",
        "delivered_at": f"2026-08-06T10:{minute:02d}:03Z",
        "consumed_at": f"2026-08-06T10:{minute:02d}:04Z",
    }


class V31CycleAuthoringContractTests(unittest.TestCase):
    def test_packet_and_open_envelope_are_canonical_and_selection_free(self) -> None:
        packet = _contract_packet()
        self.assertEqual(
            packet["authoring_packet_digest"],
            validate_v31_proposal_authoring_packet(packet),
        )
        envelope = _envelope(packet)
        self.assertEqual(
            envelope["agent_authoring_envelope_digest"],
            validate_v31_agent_open_analysis_envelope(
                envelope, authoring_packet=packet
            ),
        )
        self.assertEqual(12, len(envelope["sentiment_axis_analyses"]))
        self.assertEqual(
            sorted(envelope["information_interpretations"]),
            envelope["information_interpretations"],
        )
        self.assertFalse(envelope["selection_fields_admitted"])
        self.assertEqual(
            {"WAIT", "OPEN_LONG", "OPEN_SHORT"},
            {row["action"] for row in envelope["action_candidate_specs"]},
        )
        self.assertTrue(
            {"OTHER", "UNKNOWN"}.issubset(
                {
                    row["hypothesis_id"]
                    for row in envelope["probability_cloud_spec"]["components"]
                }
            )
        )

    def test_numeric_probability_or_nested_selection_fails_closed(self) -> None:
        packet = _contract_packet()
        for forbidden_key, value in (
            ("probability_pct", 60),
            ("selected_candidate_id", "candidate:wait"),
        ):
            tampered = copy.deepcopy(_envelope(packet))
            tampered.pop("agent_authoring_envelope_digest")
            tampered["hypothesis_deltas"][0][forbidden_key] = value
            tampered = self_digest(tampered, "agent_authoring_envelope_digest")
            with self.assertRaises(V31CycleAuthoringError):
                validate_v31_agent_open_analysis_envelope(
                    tampered, authoring_packet=packet
                )

    def test_genesis_packet_rejects_previous_heads(self) -> None:
        packet = _contract_packet()
        heads = copy.deepcopy(packet["previous_head_bindings"])
        heads["previous_accepted_state"] = _binding(
            ref="cycles/0000/accepted.json",
            schema_id="theory_paper_v2_v31_accepted_research_state",
            digest_field="accepted_state_digest",
            digest="5" * 64,
        )
        with self.assertRaisesRegex(
            V31CycleAuthoringError, "GENESIS_PREVIOUS_HEAD_FORBIDDEN"
        ):
            seal_v31_proposal_authoring_packet(
                run_id=RUN_ID,
                cycle_index=1,
                decision_at=DECISION_AT,
                symbol=SYMBOL,
                cycle_source_admission_binding=None,
                source_qualification_completion_binding=packet[
                    "source_qualification_completion_binding"
                ],
                information_event_bindings=packet["information_event_bindings"],
                pit_dataset_binding=packet["pit_dataset_binding"],
                authoring_purpose=packet["authoring_purpose"],
                theory_approval_binding=packet["authority_context"][
                    "theory_approval_binding"
                ],
                experiment_subject_binding=packet["authority_context"][
                    "experiment_subject_binding"
                ],
                active_authority_binding=None,
                previous_head_bindings=heads,
            )

    def test_qualification_breaks_q7_active_authority_circularity(self) -> None:
        qualified = _contract_packet()
        self.assertEqual("TRANSPORT_QUALIFICATION_ONLY", qualified["authoring_purpose"])
        self.assertEqual(
            "PRESTART_APPROVAL_AND_EXPERIMENT_SUBJECT",
            qualified["authority_context"]["mode"],
        )
        self.assertIsNone(
            qualified["authority_context"]["active_authority_binding"]
        )
        self.assertFalse(
            qualified["authority_context"]["experiment_start_authorized"]
        )
        active = _binding(
            ref="genesis/current-authority.json",
            schema_id="theory_paper_v31_current_research_authority",
            digest_field="authority_digest",
            digest="6" * 64,
        )
        common = {
            "run_id": RUN_ID,
            "cycle_index": 1,
            "decision_at": DECISION_AT,
            "symbol": SYMBOL,
            "source_qualification_completion_binding": qualified[
                "source_qualification_completion_binding"
            ],
            "information_event_bindings": qualified[
                "information_event_bindings"
            ],
            "pit_dataset_binding": qualified["pit_dataset_binding"],
            "theory_approval_binding": qualified["authority_context"][
                "theory_approval_binding"
            ],
            "experiment_subject_binding": qualified["authority_context"][
                "experiment_subject_binding"
            ],
            "previous_head_bindings": _head_bindings(),
        }
        with self.assertRaisesRegex(
            V31CycleAuthoringError,
            "QUALIFICATION_AUTHORITY_OR_SOURCE_ADMISSION_FORBIDDEN",
        ):
            seal_v31_proposal_authoring_packet(
                **common,
                cycle_source_admission_binding=None,
                authoring_purpose="TRANSPORT_QUALIFICATION_ONLY",
                active_authority_binding=active,
            )
        with self.assertRaisesRegex(
            V31CycleAuthoringError, "ACTIVE_AUTHORITY_REQUIRED"
        ):
            seal_v31_proposal_authoring_packet(
                **common,
                cycle_source_admission_binding=None,
                authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
                active_authority_binding=None,
            )
        source_admission = _binding(
            ref="cycles/0001/market/source-admission/cycle-source-admission.json",
            schema_id="theory_paper_v31_cycle_source_admission",
            digest_field="cycle_source_admission_digest",
            digest="7" * 64,
        )
        authorized = seal_v31_proposal_authoring_packet(
            **common,
            authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
            active_authority_binding=active,
            cycle_source_admission_binding=source_admission,
        )
        self.assertTrue(
            authorized["authority_context"]["experiment_start_authorized"]
        )

    def test_missing_production_compiler_is_explicit_fail_closed(self) -> None:
        packet = _contract_packet()
        with self.assertRaisesRegex(
            V31CycleAuthoringWorkflowError, "COMPILER_REQUIRED_FAIL_CLOSED"
        ):
            compile_v31_agent_open_analysis(
                authoring_packet=packet,
                authoring_envelope=_envelope(packet),
                compiled_at="2026-08-06T10:30:00Z",
                compiler=None,
            )

    def test_durable_authoring_stops_before_compilation_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            packet, packet_binding = _write_materials_and_packet(store)
            initialize_v31_agent_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                created_at="2026-08-06T10:00:00Z",
                owner_id="initializer",
                lease_expires_at="2026-08-06T10:00:30Z",
            )
            calls: list[str] = []

            def authoring_agent(request: Mapping[str, Any]) -> Mapping[str, Any]:
                calls.append(request["request_digest"])
                self.assertEqual(
                    "theory_paper_v31_agent_open_analysis_envelope",
                    request["expected_payload_schema_id"],
                )
                self.assertEqual(
                    packet_binding, request["authoring_packet_binding"]
                )
                self.assertTrue(
                    store.document_exists(
                        relative_ref=(
                            "cycles/0001/agent-transport/proposal/attempt.json"
                        )
                    )
                )
                self.assertTrue(
                    store.document_exists(
                        relative_ref=(
                            "cycles/0001/agent-transport/proposal/claim.json"
                        )
                    )
                )
                return _envelope(packet)

            result = run_v31_authoring_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                authoring_packet_binding=packet_binding,
                owner_id="authoring-owner",
                lease_acquired_at="2026-08-06T10:10:00Z",
                lease_expires_at="2026-08-06T10:19:59Z",
                stage_times=_times(11),
                agent_call=authoring_agent,
            )
            self.assertEqual(1, len(calls))
            self.assertEqual("READY_FOR_COMPILATION", result["status"])
            self.assertFalse(result["q7_run_ready"])
            self.assertFalse(result["selection_unblocked"])
            checkpoint = store.read_checkpoint(
                relative_ref="cycles/0001/agent-transport/checkpoint.json"
            )
            self.assertEqual("READY_FOR_COMPILATION", checkpoint["status"])
            self.assertEqual(
                "BLOCKED", checkpoint["stage_states"]["SELECTION"]["status"]
            )

            recovered = run_v31_authoring_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                authoring_packet_binding=packet_binding,
                owner_id="recovery-owner",
                lease_acquired_at="2026-08-06T10:20:00Z",
                lease_expires_at="2026-08-06T10:29:59Z",
                stage_times=_times(21),
                agent_call=lambda request: self.fail("Agent must not be called twice"),
            )
            self.assertEqual("READY_FOR_COMPILATION", recovered["status"])
            self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
