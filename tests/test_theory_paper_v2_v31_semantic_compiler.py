from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any, Mapping

from trade_system.theory_paper_v2.application.v31_cycle_authoring import (
    V31CycleAuthoringWorkflowError,
    compile_v31_agent_open_analysis,
)
from trade_system.theory_paper_v2.application.v31_agent_transport import (
    initialize_v31_agent_transport,
    run_v31_authoring_compilation,
    run_v31_authoring_transport,
    run_v31_selection_transport,
    verify_completed_v31_authoring_transport,
    verify_v31_authoring_compilation_bundle,
)
from trade_system.theory_paper_v2.application.v31_source_qualification import (
    execute_v31_source_qualification,
    initialize_v31_source_qualification,
)
from trade_system.theory_paper_v2.domain.dynamic_research import V31_SENTIMENT_AXES
from trade_system.theory_paper_v2.domain.behavior_planning import (
    seal_action_selection,
)
from trade_system.theory_paper_v2.domain.information_model import (
    information_event_from_canonical_dict,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
)
from trade_system.theory_paper_v2.domain.data_model import (
    point_in_time_datum_from_document,
)
from trade_system.theory_paper_v2.domain.v31_cycle_authoring import (
    seal_v31_agent_open_analysis_envelope,
    seal_v31_proposal_authoring_packet,
)
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    build_minimal_experiment_contract,
)
from trade_system.theory_paper_v2.domain.v31_source_qualification import (
    APPROVED_V31_THEORY_SHA256,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_semantic_compiler import (
    LocalV31SemanticCompiler,
)
from trade_system.theory_paper_v2.infrastructure.v31_market_adapter import (
    adapt_native_public_snapshot,
)
from trade_system.theory_paper_v2.infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
)
from tests.test_theory_paper_v2_v31_source_qualification import (
    _LeaseAssertingCollector,
)


ROOT = Path(__file__).resolve().parents[1]
Q6_ROOT = ROOT / (
    "agent-cluster/experiments/v31-qualifications/"
    "v31-source-qualification-20260806t161918z"
)
RUN_ID = "run:v31:semantic-compiler-production-test"
SYMBOL = "BTC-USDT-SWAP"
CREATED_AT = "2026-08-06T12:00:00Z"
REVIEW_AT = "2026-08-06T13:01:00Z"
EXPIRY_AT = "2026-08-06T14:01:00Z"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _heads() -> dict[str, None]:
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


def _write(
    store: LocalV31AgentTransportStore,
    *,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
    minute: int,
) -> dict[str, str]:
    with store.owner_lease(
        owner_id=f"semantic-compiler-fixture-{minute}",
        acquired_at=f"2026-08-06T18:{minute:02d}:00Z",
        expires_at=f"2026-08-06T18:{minute:02d}:30Z",
    ) as lease:
        return store.write_document(
            lease=lease,
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )


def _fresh_no_network_q6(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    qualification_id = "v31-source-qualification-semantic-compiler-fixture"
    source_store = LocalV31SourceQualificationStore(root)
    initialize_v31_source_qualification(
        store=source_store,
        qualification_id=qualification_id,
        created_at="2026-08-06T11:59:59Z",
        theory_sha256=APPROVED_V31_THEORY_SHA256,
    )
    collector = _LeaseAssertingCollector(store=source_store)
    result = execute_v31_source_qualification(
        store=source_store,
        qualification_id=qualification_id,
        collector=collector,
        adapter=adapt_native_public_snapshot,
        clock=lambda: "2026-08-06T12:01:00Z",
    )
    if result["status"] != "SEALED":  # pragma: no cover - fixture invariant
        raise AssertionError("fresh no-network Q6 fixture did not seal")
    record = _json(root / "adapted/information-event-0001.json")
    dataset = _json(root / "adapted/pit-dataset.json")
    completion = _json(root / "receipts/source-qualification-completion.json")
    information_event_from_canonical_dict(record["event_document"])
    return record, dataset, completion


def _materials(
    store: LocalV31AgentTransportStore,
    *,
    qualification_root: Path,
    legacy_event: bool = False,
    run_id: str = RUN_ID,
    experiment_contract: Mapping[str, Any] | None = None,
    theory_approval: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if legacy_event:
        record = _json(Q6_ROOT / "adapted/information-event-0001.json")
        dataset = _json(Q6_ROOT / "adapted/pit-dataset.json")
        completion = _json(
            Q6_ROOT / "receipts/source-qualification-completion.json"
        )
    else:
        record, dataset, completion = _fresh_no_network_q6(qualification_root)
    event_binding = _write(
        store,
        relative_ref="adapted/information-event-0001.json",
        document=record,
        digest_field="source_qualification_information_event_record_digest",
        minute=1,
    )
    dataset_binding = _write(
        store,
        relative_ref="adapted/pit-dataset.json",
        document=dataset,
        digest_field="dataset_digest",
        minute=2,
    )
    completion_event_binding = completion["information_event_bindings"][0]
    completion_dataset_binding = completion["pit_dataset_binding"]
    if any(
        completion_event_binding[key] != event_binding[key]
        or completion_dataset_binding[key] != dataset_binding[key]
        for key in ("relative_ref", "semantic_digest", "physical_sha256")
    ):
        raise AssertionError("qualification material changed during physical copy")
    completion_binding = _write(
        store,
        relative_ref="receipts/source-qualification-completion.json",
        document=completion,
        digest_field="source_qualification_completion_digest",
        minute=3,
    )
    approval = (
        _json(ROOT / "config/theory_paper_v31.theory_approval.20260806.json")
        if theory_approval is None
        else dict(theory_approval)
    )
    approval_binding = _write(
        store,
        relative_ref="authority/theory-approval.json",
        document=approval,
        digest_field="approval_receipt_digest",
        minute=4,
    )
    contract = (
        build_minimal_experiment_contract(
            contract_id="contract:v31:semantic-compiler-production-test",
            run_id=run_id,
            frozen_at="2026-08-06T11:50:00Z",
        )
        if experiment_contract is None
        else dict(experiment_contract)
    )
    if contract.get("run_id") != run_id:
        raise AssertionError("fixture experiment subject run_id mismatch")
    contract_binding = _write(
        store,
        relative_ref="authority/experiment-contract.json",
        document=contract,
        digest_field="experiment_contract_digest",
        minute=5,
    )
    packet = seal_v31_proposal_authoring_packet(
        run_id=run_id,
        cycle_index=1,
        decision_at=dataset["decision_at"],
        symbol=SYMBOL,
        cycle_source_admission_binding=None,
        source_qualification_completion_binding=completion_binding,
        information_event_bindings=(event_binding,),
        pit_dataset_binding=dataset_binding,
        authoring_purpose="TRANSPORT_QUALIFICATION_ONLY",
        theory_approval_binding=approval_binding,
        experiment_subject_binding=contract_binding,
        active_authority_binding=None,
        previous_head_bindings=_heads(),
    )
    mark = next(row for row in dataset["data"] if row["metric"] == "mark-price")
    return packet, dataset, mark["datum_id"]


def _hypothesis(
    hypothesis_id: str, hypothesis_type: str, bias: str, mark_id: str
) -> dict[str, Any]:
    family = hypothesis_id.replace(":", "-")
    return {
        "hypothesis_id": hypothesis_id,
        "revision": 1,
        "hypothesis_type": hypothesis_type,
        "directional_bias": bias,
        "family_label": family,
        "deduplication_key": f"dedup:{family}",
        "state": "ACTIVE",
        "parent_hypothesis_ids": [],
        "supersedes_ids": [],
        "derived_from_expectation_ids": [],
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "horizon": "next closed 1H bar",
        "timeframe_scope": ["1H"],
        "premises": [f"The admitted mark can discriminate {hypothesis_id}."],
        "expected_sequence": [f"A registered observation tests {hypothesis_id}."],
        "support_rules": [f"The registered path condition supports {hypothesis_id}."],
        "oppose_rules": [f"The registered contrary condition opposes {hypothesis_id}."],
        "hard_falsifiers": [f"falsifier:{hypothesis_id}"],
        "expiry": EXPIRY_AT,
        "trade_triggers": [],
        "forbidden_conditions": [],
        "active_evidence_ids": [mark_id],
        "support_level": "PLAUSIBLE",
        "limitations": ["One public point-in-time source is not causal proof."],
        "novelty_reason": f"Distinct registered mechanism for {hypothesis_id}.",
        "agent_rationale": "Keep open until the registered observation arrives.",
    }


def _expectation(
    expectation_id: str, hypothesis_id: str, mark_id: str
) -> dict[str, Any]:
    return {
        "expectation_id": expectation_id,
        "revision": 1,
        "hypothesis_id": hypothesis_id,
        "parent_expectation_id": None,
        "deduplication_key": f"dedup:{expectation_id}",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "observation_start": "2026-08-06T12:01:00Z",
        "observation_deadline": REVIEW_AT,
        "if_conditions": [f"{hypothesis_id} remains active."],
        "expected_observations": [
            {
                "metric": mark_id,
                "direction_or_range": "registered state persists",
                "timeframe": "1H",
                "source_requirement": "independent next public closed window",
            }
        ],
        "falsifying_observations": [
            {
                "metric": mark_id,
                "direction_or_range": "registered state reverses",
                "timeframe": "1H",
                "source_requirement": "independent next public closed window",
            }
        ],
        "evidence_sufficiency": "LOW",
        "status": "OPEN",
        "result_evidence_refs": [],
        "closed_at": None,
        "result_note": None,
    }


def _predicate(
    predicate_id: str,
    *,
    fact_ref: str,
    available_at: str,
    timing: str,
    operator: str,
    expected: Any,
) -> dict[str, Any]:
    return {
        "predicate_id": predicate_id,
        "fact_ref": fact_ref,
        "timing": timing,
        "operator": operator,
        "expected": expected,
        "available_at": available_at,
        "minimum_quality": "MEDIUM",
        "minimum_coverage": "1",
        "allowed_conflict_states": ["NONE"],
        "limitations": ["A predicate is not execution authority."],
    }


def _path(
    *,
    path_id: str,
    hypothesis_id: str,
    expectation_id: str,
    action: str,
    mark_id: str,
    mark_available_at: str,
    mark_value: str,
    expected_value: str | None,
    run_id: str = RUN_ID,
) -> dict[str, Any]:
    operator = "EXISTS" if expected_value is None else "EQ"
    trigger = _predicate(
        f"trigger:{path_id}",
        fact_ref=mark_id,
        available_at=mark_available_at,
        timing="DECISION_INPUT",
        operator=operator,
        expected=expected_value,
    )
    return {
        "path_id": path_id,
        "triggers": [trigger],
        "guards": [
            _predicate(
                f"guard:{path_id}",
                fact_ref=mark_id,
                available_at=mark_available_at,
                timing="DECISION_INPUT",
                operator="EXISTS",
                expected=None,
            )
        ],
        "unless": [],
        "transition": {
            "from_stage": "ASSOCIATION",
            "to_stage": "INFERENCE",
            "target_ref": f"inference:{path_id}",
            "update_type": "ADD",
        },
        "mechanism": f"The registered mark condition discriminates {path_id}.",
        "mechanism_hypothesis_refs": [hypothesis_id],
        "expectations": [
            {
                "observation_id": expectation_id,
                "hypothesis_id": hypothesis_id,
                "observable_ref": mark_id,
                "horizon_at": REVIEW_AT,
                "direction_or_state": "registered state persists",
                "confirms_when": "registered state persists",
                "contradicts_when": "registered state reverses",
            }
        ],
        "falsifiers": [
            _predicate(
                f"falsifier:{path_id}",
                fact_ref=f"future:{path_id}",
                available_at=REVIEW_AT,
                timing="FUTURE_MONITOR",
                operator="EXISTS",
                expected=None,
            )
        ],
        "else_path_refs": [],
        "preserves_other_unknown": True,
        "action_implications": [
            {
                "action": action,
                "effect": "FAVORS" if action == "WAIT" else "CONDITIONAL",
                "rationale": "Only the registered action class is implicated.",
                "risk_refs": ["risk:uncalibrated-public-snapshot"],
                "opportunity_cost": "The registered path can still be wrong.",
            }
        ],
        "expires_at": EXPIRY_AT,
        "next_review_at": REVIEW_AT,
        "next_observation": "Observe the next independent closed 1H window.",
        "regime_refs": [],
        "probability_cloud_refs": [f"cloud:{run_id}:0001"],
    }


def _candidate(action: str, path_id: str, mark_id: str) -> dict[str, Any]:
    wait = action == "WAIT"
    return {
        "candidate_id": f"candidate:{action.lower()}",
        "action": action,
        "scale_pct": None if wait else 25,
        "target_role": None if wait else "TACTICAL",
        "path_refs": [path_id],
        "evidence_refs": [mark_id],
        "trigger_conditions": ["The registered path remains admitted."],
        "invalidation_conditions": ["A registered falsifier becomes true."],
        "risk_refs": ["risk:uncalibrated-public-snapshot"],
        "thesis": "A non-executable candidate for deterministic comparison.",
        "wait_reason": "Uncertainty remains uncalibrated." if wait else None,
        "opportunity_cost": "A move may start before review." if wait else None,
        "next_observation": "Observe the next closed 1H window." if wait else None,
        "next_review_at": REVIEW_AT if wait else None,
        "information_not_arrived_default": (
            "Preserve the flat shadow state." if wait else None
        ),
        "position_protection_responsibility": (
            "Recheck the frozen risk limits at review." if wait else None
        ),
    }


def _envelope(
    packet: Mapping[str, Any], dataset: Mapping[str, Any], mark_id: str
) -> dict[str, Any]:
    mark = next(row for row in dataset["data"] if row["datum_id"] == mark_id)
    hypotheses = (
        ("hypothesis:mechanism", "MECHANISM", "BIDIRECTIONAL"),
        ("path:lead", "PATH", "LONG"),
        ("path:runner", "PATH", "SHORT"),
    )
    hypothesis_deltas = [
        {
            "delta_id": f"delta:create:{hypothesis_id}",
            "operation": "CREATE",
            "occurred_at": CREATED_AT,
            "target_hypothesis_ids": [],
            "replacement_hypotheses": [
                _hypothesis(hypothesis_id, hypothesis_type, bias, mark_id)
            ],
            "evidence_ids": [mark_id],
            "matched_hard_falsifier": None,
            "agent_rationale": "Create one explicit competing hypothesis.",
        }
        for hypothesis_id, hypothesis_type, bias in hypotheses
    ]
    expectation_pairs = (
        ("expectation:mechanism", "hypothesis:mechanism"),
        ("expectation:lead", "path:lead"),
        ("expectation:runner", "path:runner"),
    )
    expectation_deltas = [
        {
            "delta_id": f"delta:create:{expectation_id}",
            "operation": "CREATE",
            "occurred_at": CREATED_AT,
            "target_expectation_id": None,
            "expectation": _expectation(expectation_id, hypothesis_id, mark_id),
            "agent_rationale": "Register the next discriminating observation.",
        }
        for expectation_id, hypothesis_id in expectation_pairs
    ]
    components = [
        {
            "hypothesis_id": hypothesis_id,
            "plausibility": "MEDIUM",
            "evidence_refs": [mark_id],
            "opposition_refs": [],
            "conflict_refs": [mark_id],
            "dependency_groups": [mark["dependency_group"]],
            "data_uncertainty": ["One public point-in-time source."],
            "model_uncertainty": ["No calibrated probability model."],
            "sensitivity_notes": ["Sensitive to the next independent window."],
        }
        for hypothesis_id, _, _ in hypotheses
    ]
    components.extend(
        [
            {
                "hypothesis_id": "OTHER",
                "plausibility": "MEDIUM",
                "evidence_refs": [],
                "opposition_refs": [],
                "conflict_refs": [],
                "dependency_groups": [],
                "data_uncertainty": ["Unmodelled mechanisms remain."],
                "model_uncertainty": ["Residual component is open."],
                "sensitivity_notes": ["OTHER is not assigned zero."],
            },
            {
                "hypothesis_id": "UNKNOWN",
                "plausibility": "UNKNOWN",
                "evidence_refs": [],
                "opposition_refs": [],
                "conflict_refs": [],
                "dependency_groups": [],
                "data_uncertainty": ["Private positioning is unavailable."],
                "model_uncertainty": ["No calibrated probability model."],
                "sensitivity_notes": ["UNKNOWN is not neutral or zero."],
            },
        ]
    )
    paths = [
        _path(
            path_id="path:lead",
            hypothesis_id="path:lead",
            expectation_id="expectation:lead",
            action="OPEN_LONG",
            mark_id=mark_id,
            mark_available_at=mark["available_at"],
            mark_value=mark["value"],
            expected_value=mark["value"],
            run_id=str(packet["run_id"]),
        ),
        _path(
            path_id="path:runner",
            hypothesis_id="path:runner",
            expectation_id="expectation:runner",
            action="OPEN_SHORT",
            mark_id=mark_id,
            mark_available_at=mark["available_at"],
            mark_value=mark["value"],
            expected_value="0",
            run_id=str(packet["run_id"]),
        ),
        _path(
            path_id="OTHER",
            hypothesis_id="hypothesis:mechanism",
            expectation_id="expectation:mechanism",
            action="WAIT",
            mark_id=mark_id,
            mark_available_at=mark["available_at"],
            mark_value=mark["value"],
            expected_value=None,
            run_id=str(packet["run_id"]),
        ),
    ]
    return seal_v31_agent_open_analysis_envelope(
        authoring_packet=packet,
        information_interpretations=(
            "The public mark is observed but private positioning is unavailable.",
        ),
        operational_synthesis=(
            "All sentiment axes remain UNKNOWN; competing paths remain open."
        ),
        sentiment_axis_analyses=[
            {
                "axis": axis,
                "ordinal_state": "UNKNOWN",
                "evidence_assessments": [],
                "required_dependency_groups": [f"UNKNOWN:{axis}"],
                "timeframe_states": {"1H": None},
                "reasoning": "No admitted direct evidence justifies a directional state.",
                "limitations": ["UNKNOWN is not treated as neutral."],
                "next_discriminating_observation": (
                    "Observe the next independent closed 1H window."
                ),
            }
            for axis in V31_SENTIMENT_AXES
        ],
        graph_delta_spec={
            "projection_id": LocalV31SemanticCompiler.compiler_id,
            "graph_id": "graph:v31:semantic-compiler-test",
            "delta_id": "delta:graph:semantic-compiler-test:1",
            "projection_policy": "EXACT_TYPED_ARTIFACT_VERTICAL_PROJECTION_V1",
            "additional_associations": [],
            "rationale": "Project only exact typed bindings authored in this envelope.",
        },
        hypothesis_deltas=hypothesis_deltas,
        expectation_deltas=expectation_deltas,
        probability_cloud_spec={
            "mode": "SUBJECTIVE_PLAUSIBILITY",
            "horizon": "next closed 1H bar",
            "components": components,
            "unknown_refs": ["Private positioning and intent are unavailable."],
            "limitations": ["Ordinal plausibility is not numerical probability."],
        },
        scenario_path_set_spec={
            "set_id": "paths:v31:semantic-compiler-test",
            "lead_path_id": "path:lead",
            "runner_up_path_id": "path:runner",
            "residual_path_id": "OTHER",
            "paths": paths,
        },
        action_candidate_specs=(
            _candidate("OPEN_LONG", "path:lead", mark_id),
            _candidate("OPEN_SHORT", "path:runner", mark_id),
            _candidate("WAIT", "OTHER", mark_id),
        ),
        competing_explanations=("A common public-market shock may dominate.",),
        unknowns=("Private positioning and intent remain unknown.",),
        requested_observations=("Observe the next independent closed 1H window.",),
        hypothesis_novelty_rationales={
            hypothesis_id: f"Distinct registered mechanism for {hypothesis_id}."
            for hypothesis_id, _, _ in hypotheses
        },
        limitations=("This is preselection analysis without trading authority.",),
    )


def _reseal_envelope(
    packet: Mapping[str, Any],
    envelope: Mapping[str, Any],
    **updates: Any,
) -> dict[str, Any]:
    fields = {
        key: copy.deepcopy(envelope[key])
        for key in (
            "information_interpretations",
            "operational_synthesis",
            "sentiment_axis_analyses",
            "graph_delta_spec",
            "hypothesis_deltas",
            "expectation_deltas",
            "probability_cloud_spec",
            "scenario_path_set_spec",
            "action_candidate_specs",
            "competing_explanations",
            "unknowns",
            "requested_observations",
            "hypothesis_novelty_rationales",
            "limitations",
        )
    }
    fields.update(updates)
    return seal_v31_agent_open_analysis_envelope(
        authoring_packet=packet, **fields
    )


class V31SemanticCompilerTests(unittest.TestCase):
    def test_current_bound_inputs_compile_to_replayed_preselection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            packet, dataset, mark_id = _materials(
                store,
                qualification_root=Path(directory) / "qualification",
            )
            result = compile_v31_agent_open_analysis(
                authoring_packet=packet,
                authoring_envelope=_envelope(packet, dataset, mark_id),
                compiled_at="2026-08-06T18:10:00Z",
                compiler=LocalV31SemanticCompiler(store=store),
            )
            self.assertEqual("COMPILED_PRESELECTION_NOT_SELECTED", result["status"])
            self.assertFalse(result["selection_fields_admitted"])
            self.assertFalse(result["executable"])
            self.assertEqual(
                {"OPEN_LONG", "OPEN_SHORT", "WAIT"},
                {row["action"] for row in result["action_evaluation"]["candidates"]},
            )
            self.assertNotIn("selected_candidate_id", result["preselection"])

    def test_derived_sentiment_and_graph_projection_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            packet, dataset, mark_id = _materials(
                store,
                qualification_root=Path(directory) / "qualification",
            )
            derived = next(
                row
                for row in dataset["data"]
                if row["metric"] == "candle-1h-return-pct"
            )
            base = _envelope(packet, dataset, mark_id)
            analyses = copy.deepcopy(base["sentiment_axis_analyses"])
            axis = next(
                row
                for row in analyses
                if row["axis"] == "PRICE_DIRECTIONAL_PRESSURE"
            )
            axis.update(
                {
                    "ordinal_state": "POSITIVE",
                    "evidence_assessments": [
                        {
                            "evidence_ref": derived["datum_id"],
                            "ordinal_contribution": 1,
                            "rule": "Positive closed-hour return adds positive pressure.",
                            "direction": "POSITIVE",
                        }
                    ],
                    "required_dependency_groups": [
                        derived["dependency_group"]
                    ],
                    "timeframe_states": {derived["timeframe"]: 1},
                    "reasoning": "The admitted derived return is positive.",
                }
            )
            envelope = _reseal_envelope(
                packet, base, sentiment_axis_analyses=analyses
            )
            compiled = compile_v31_agent_open_analysis(
                authoring_packet=packet,
                authoring_envelope=envelope,
                compiled_at="2026-08-06T18:10:00Z",
                compiler=LocalV31SemanticCompiler(store=store),
            )
            fact = next(
                row
                for row in compiled["assembly_inputs"][
                    "market_information_snapshot"
                ]["facts"]
                if row["fact_id"] == derived["datum_id"]
            )
            self.assertEqual("DERIVED_FEATURE", fact["kind"])
            self.assertEqual(derived["input_refs"], fact["lineage"])
            self.assertEqual(derived["formula_version"], fact["transform"])

            graph = compiled["assembly_inputs"]["graph_delta"]
            nodes = {row["node_id"]: row for row in graph["node_revisions"]}
            edges = graph["association_revisions"]
            derived_edges = [
                row for row in edges if row["relation"] == "DERIVED_FROM"
            ]
            self.assertTrue(derived_edges)
            self.assertTrue(
                all(
                    nodes.get(row["source_node_id"], {}) .get("node_type")
                    == "DERIVED_MEASURE"
                    for row in derived_edges
                    if row["source_node_id"] in nodes
                )
            )
            conditioned = [
                row for row in edges if row["relation"] == "CONDITIONED_BY"
            ]
            self.assertTrue(conditioned)
            self.assertTrue(
                all(
                    nodes[row["source_node_id"]]["node_type"]
                    == "LATENT_STATE"
                    for row in conditioned
                )
            )
            self.assertEqual(
                {mark_id},
                {
                    nodes[row["target_node_id"]]["payload_ref"]
                    for row in conditioned
                },
            )
            self.assertFalse(
                any(
                    row["relation"] == "SUPPORTS"
                    and nodes[row["source_node_id"]]["node_type"]
                    == "LATENT_STATE"
                    for row in edges
                )
            )

    def test_sentiment_declaration_timeframe_and_cloud_missingness_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            packet, dataset, mark_id = _materials(
                store,
                qualification_root=Path(directory) / "qualification",
            )
            derived = next(
                row
                for row in dataset["data"]
                if row["metric"] == "candle-1h-return-pct"
            )
            unavailable = next(
                row for row in dataset["data"] if row["value"] is None
            )
            base = _envelope(packet, dataset, mark_id)

            def sentiment_envelope(*, state: str, timeframe: str) -> dict[str, Any]:
                analyses = copy.deepcopy(base["sentiment_axis_analyses"])
                axis = next(
                    row
                    for row in analyses
                    if row["axis"] == "PRICE_DIRECTIONAL_PRESSURE"
                )
                axis.update(
                    {
                        "ordinal_state": state,
                        "evidence_assessments": [
                            {
                                "evidence_ref": derived["datum_id"],
                                "ordinal_contribution": 1,
                                "rule": "The admitted derived return is positive.",
                                "direction": "POSITIVE",
                            }
                        ],
                        "required_dependency_groups": [
                            derived["dependency_group"]
                        ],
                        "timeframe_states": {timeframe: 1},
                    }
                )
                return _reseal_envelope(
                    packet, base, sentiment_axis_analyses=analyses
                )

            for envelope in (
                sentiment_envelope(state="NEGATIVE", timeframe="1h"),
                sentiment_envelope(state="POSITIVE", timeframe="1d"),
            ):
                with self.assertRaises(V31CycleAuthoringWorkflowError):
                    compile_v31_agent_open_analysis(
                        authoring_packet=packet,
                        authoring_envelope=envelope,
                        compiled_at="2026-08-06T18:10:00Z",
                        compiler=LocalV31SemanticCompiler(store=store),
                    )

            cloud = copy.deepcopy(base["probability_cloud_spec"])
            directional = next(
                row
                for row in cloud["components"]
                if row["hypothesis_id"] == "path:lead"
            )
            directional.update(
                {
                    "evidence_refs": [unavailable["datum_id"]],
                    "opposition_refs": [],
                    "conflict_refs": [unavailable["datum_id"]],
                    "dependency_groups": [unavailable["dependency_group"]],
                }
            )
            with self.assertRaises(V31CycleAuthoringWorkflowError):
                compile_v31_agent_open_analysis(
                    authoring_packet=packet,
                    authoring_envelope=_reseal_envelope(
                        packet, base, probability_cloud_spec=cloud
                    ),
                    compiled_at="2026-08-06T18:10:00Z",
                    compiler=LocalV31SemanticCompiler(store=store),
                )

    def test_derived_source_lineage_cannot_be_removed_and_resigned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            _packet, dataset, _mark_id = _materials(
                store,
                qualification_root=Path(directory) / "qualification",
            )
            derived = copy.deepcopy(
                next(
                    row
                    for row in dataset["data"]
                    if row["metric"] == "candle-1h-return-pct"
                )
            )
            for field, value in (("formula_version", None), ("input_refs", [])):
                tampered = copy.deepcopy(derived)
                tampered[field] = value
                payload = dict(tampered)
                payload.pop("datum_digest")
                tampered["datum_digest"] = canonical_digest(payload)
                with self.assertRaises(ValueError):
                    point_in_time_datum_from_document(tampered)

    def test_durable_authoring_compilation_unblocks_postseal_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalV31AgentTransportStore(root / "transport")
            packet, dataset, mark_id = _materials(
                store,
                qualification_root=root / "qualification",
            )
            packet_binding = _write(
                store,
                relative_ref="cycles/0001/proposal-authoring-packet.json",
                document=packet,
                digest_field="authoring_packet_digest",
                minute=6,
            )
            initialize_v31_agent_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                created_at="2026-08-06T12:02:00Z",
                owner_id="transport-initializer",
                lease_expires_at="2026-08-06T12:02:30Z",
            )
            authored = run_v31_authoring_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                authoring_packet_binding=packet_binding,
                owner_id="authoring-owner",
                lease_acquired_at="2026-08-06T12:03:00Z",
                lease_expires_at="2026-08-06T12:09:59Z",
                stage_times={
                    "reserved_at": "2026-08-06T12:03:01Z",
                    "requested_at": "2026-08-06T12:03:02Z",
                    "claimed_at": "2026-08-06T12:03:03Z",
                    "delivered_at": "2026-08-06T12:03:04Z",
                    "consumed_at": "2026-08-06T12:03:05Z",
                },
                agent_call=lambda _: _envelope(packet, dataset, mark_id),
            )
            self.assertEqual("READY_FOR_COMPILATION", authored["status"])
            compiled = run_v31_authoring_compilation(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                authoring_packet_binding=packet_binding,
                compiled_at="2026-08-06T12:10:00Z",
                compiler=LocalV31SemanticCompiler(store=store),
                owner_id="compiler-owner",
                lease_acquired_at="2026-08-06T12:10:00Z",
                lease_expires_at="2026-08-06T12:10:30Z",
            )
            self.assertEqual("READY_FOR_SELECTION", compiled["status"])
            replay = verify_v31_authoring_compilation_bundle(
                store=store,
                admission_binding=compiled["compilation_admission_binding"],
                expected_run_id=RUN_ID,
                expected_cycle_index=1,
            )
            evaluation = replay["action_evaluation"]
            wait_id = next(
                row["candidate_id"]
                for row in evaluation["candidates"]
                if row["action"] == "WAIT"
            )

            def selection_agent(_: Mapping[str, Any]) -> Mapping[str, Any]:
                candidate_ids = {
                    row["candidate_id"] for row in evaluation["candidates"]
                }
                return seal_action_selection(
                    evaluation=evaluation,
                    selected_candidate_id=wait_id,
                    reason="Uncalibrated uncertainty makes WAIT the reversible label.",
                    alternative_explanations={
                        candidate_id: "The competing path remains possible."
                        for candidate_id in candidate_ids - {wait_id}
                    },
                    failure_conditions=("The registered WAIT premise changes.",),
                    next_review_at=next(
                        row["next_review_at"]
                        for row in evaluation["candidates"]
                        if row["candidate_id"] == wait_id
                    ),
                    selected_at="2026-08-06T12:11:02Z",
                )

            selected = run_v31_selection_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                preselection_binding=compiled["preselection_binding"],
                action_evaluation_binding=compiled[
                    "action_evaluation_binding"
                ],
                owner_id="selection-owner",
                lease_acquired_at="2026-08-06T12:11:00Z",
                lease_expires_at="2026-08-06T12:11:30Z",
                stage_times={
                    "reserved_at": "2026-08-06T12:11:00Z",
                    "requested_at": "2026-08-06T12:11:01Z",
                    "claimed_at": "2026-08-06T12:11:02Z",
                    "delivered_at": "2026-08-06T12:11:03Z",
                    "consumed_at": "2026-08-06T12:11:04Z",
                },
                agent_call=selection_agent,
            )
            self.assertEqual("COMPLETED", selected["status"])
            self.assertIsNotNone(selected["transport_evidence_binding"])
            terminal = verify_completed_v31_authoring_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=1,
                expected_authoring_purpose="TRANSPORT_QUALIFICATION_ONLY",
            )
            self.assertEqual(
                compiled["compilation_admission_binding"],
                terminal["compilation_admission_binding"],
            )
            self.assertTrue(terminal["subject_run_id_matches"])
            self.assertTrue(terminal["postseal_selection_consumed"])
            self.assertEqual(
                replay["assembly_inputs"], terminal["assembly_inputs"]
            )
            self.assertEqual(
                selection_agent({}), terminal["action_selection"]
            )

    def test_historical_none_e0_event_is_explicitly_not_cycle_admissible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            packet, dataset, mark_id = _materials(
                store,
                qualification_root=Path(directory) / "qualification",
                legacy_event=True,
            )
            compiler = LocalV31SemanticCompiler(store=store)
            with self.assertRaisesRegex(
                V31CycleAuthoringWorkflowError,
                "V31_AUTHORING_COMPILER_FAILED_CLOSED",
            ) as raised:
                compile_v31_agent_open_analysis(
                    authoring_packet=packet,
                    authoring_envelope=_envelope(packet, dataset, mark_id),
                    compiled_at="2026-08-06T18:10:00Z",
                    compiler=compiler,
                )
            self.assertIn(
                "V31_SEMANTIC_LEGACY_AUTHORITY_LABEL_NOT_CYCLE_ADMISSIBLE",
                str(raised.exception.__cause__),
            )


if __name__ == "__main__":
    unittest.main()
