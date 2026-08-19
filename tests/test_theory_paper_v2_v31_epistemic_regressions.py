from __future__ import annotations

import copy
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Mapping

from tests.test_theory_paper_v2_v31_cycle import (
    AUTHORITY_SHA256,
    DECISION,
    DECISION_AT,
    action_context,
    complete_action_evaluation,
    dynamic_research_state,
    full_inputs,
    graph_inputs,
    information_admission,
    market_economics_input,
    pit_dataset,
    position_truth_input,
    probability_cloud,
    revised_information_admissions,
    risk_policy_input,
    scenario_paths,
    second_cycle_dynamic_state,
)
from trade_system.theory_paper_v2.application.v31_research_cycle import (
    V31ResearchCycleError,
    assemble_v31_cycle_evaluation,
)
from trade_system.theory_paper_v2.domain.agent_research_contract import (
    seal_v31_agent_proposal,
    seal_v31_inputs_receipt,
)
from trade_system.theory_paper_v2.domain.behavior_planning import (
    ActionCandidate,
    ActionType,
    PositionRole,
    action_evaluations_from_financial_receipt,
    seal_complete_action_evaluation,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
)
from trade_system.theory_paper_v2.domain.dynamic_research import (
    MARKET_CATEGORIES,
    SENTIMENT_AXES,
    build_market_information_snapshot,
    build_sentiment_state,
    build_sentiment_state_change,
    migrate_legacy_sentiment_state_to_v31,
    reduce_expectation_ledger,
    reduce_hypothesis_registry,
)
from trade_system.theory_paper_v2.domain.financial_evaluation import (
    build_financial_evaluation_receipt,
)
from trade_system.theory_paper_v2.domain.information_model import (
    AdmittedInformationEvent,
    BehaviorResponseHypothesis,
    IntentInference,
    admit_information_event,
    information_event_to_canonical_dict,
)
from trade_system.theory_paper_v2.domain.probability_cloud import (
    CloudComponent,
    FrozenPredictionOutcome,
    FrozenPredictiveForecast,
    PlausibilityLevel,
    PredictiveValidationReceipt,
    ProbabilityCloud,
    ProbabilityMode,
    ProperScoringRule,
)


def _dynamic_bundle_with_bindings(
    evidence_bindings: Mapping[str, str],
) -> tuple[dict, list[dict], dict, list[dict]]:
    """Build reducer-valid state whose semantic evidence is caller-selected."""

    _, original_hypothesis_deltas, _, expectation_deltas = (
        dynamic_research_state()
    )
    hypothesis_deltas = copy.deepcopy(original_hypothesis_deltas)
    evidence_ids = sorted(evidence_bindings)
    normalized_bindings = {
        ref: evidence_bindings[ref] for ref in evidence_ids
    }
    for delta in hypothesis_deltas:
        delta["evidence_ids"] = evidence_ids
        delta["evidence_bindings"] = normalized_bindings
        for hypothesis in delta["replacement_hypotheses"]:
            hypothesis["active_evidence_ids"] = evidence_ids
            hypothesis["active_evidence_bindings"] = normalized_bindings
    registry = reduce_hypothesis_registry(
        previous_registry=None,
        deltas=hypothesis_deltas,
        decision_at=DECISION_AT,
    )
    ledger = reduce_expectation_ledger(
        previous_ledger=None,
        deltas=expectation_deltas,
        decision_at=DECISION_AT,
        valid_hypothesis_ids=registry["known_hypothesis_ids"],
    )
    return registry, hypothesis_deltas, ledger, expectation_deltas


def _candidate_from_document(document: Mapping[str, object]) -> ActionCandidate:
    target_role = document["target_role"]
    return ActionCandidate(
        candidate_id=str(document["candidate_id"]),
        action=ActionType(str(document["action"])),
        target_lot_ids=tuple(document["target_lot_ids"]),
        scale_pct=document["scale_pct"],
        target_role=(
            None if target_role is None else PositionRole(str(target_role))
        ),
        trigger_conditions=tuple(document["trigger_conditions"]),
        invalidation_conditions=tuple(document["invalidation_conditions"]),
        path_refs=tuple(document["path_refs"]),
        evidence_refs=tuple(document["evidence_refs"]),
        risk_refs=tuple(document["risk_refs"]),
        thesis=str(document["thesis"]),
        wait_reason=document["wait_reason"],
        opportunity_cost=document["opportunity_cost"],
        next_observation=document["next_observation"],
        next_review_at=document["next_review_at"],
        information_not_arrived_default=document[
            "information_not_arrived_default"
        ],
        position_protection_responsibility=document[
            "position_protection_responsibility"
        ],
    )


def _action_evaluation_with_evidence(
    inputs: Mapping[str, object], evidence_ref: str
) -> dict:
    context = inputs["action_context"]
    baseline = inputs["action_evaluation"]
    candidates: list[ActionCandidate] = []
    for index, raw in enumerate(baseline["candidates"]):
        document = dict(raw)
        if index == 0:
            document["evidence_refs"] = [evidence_ref]
        candidates.append(_candidate_from_document(document))
    financial_receipt = build_financial_evaluation_receipt(
        run_id="run:v31",
        cycle_index=1,
        decision_at=context.decision_at,
        evaluated_at=DECISION_AT,
        symbol="BTCUSDT",
        position_truth=position_truth_input(),
        risk_policy=risk_policy_input(),
        market_economics=market_economics_input(),
        probability_mode=context.probability_mode,
        probability_cloud_digest=context.probability_cloud_digest,
        calibration_receipt_digests=context.calibration_receipt_digests,
        proper_scoring_receipt_digests=(
            context.proper_scoring_receipt_digests
        ),
        oos_evaluation_receipt_digests=(
            context.oos_evaluation_receipt_digests
        ),
        candidates=tuple(row.to_document() for row in candidates),
    )
    evaluations = action_evaluations_from_financial_receipt(
        financial_evaluation_receipt=financial_receipt,
        candidates=tuple(candidates),
    )
    return seal_complete_action_evaluation(
        run_id="run:v31",
        cycle_index=1,
        context=context,
        candidates=tuple(candidates),
        evaluations=evaluations,
        financial_evaluation_receipt=financial_receipt,
        evaluated_at=DECISION_AT,
    )


def _information_with_psychological_hypotheses() -> AdmittedInformationEvent:
    baseline = information_admission()
    fact_id = baseline.event.observed_facts[0].fact_id
    intent = IntentInference(
        inference_id="intent:expectation-coordination",
        subject_actor_id=baseline.event.primary_actor_id,
        proposition="The communication may seek to coordinate expectations.",
        evidence_refs=(fact_id,),
        competing_explanations=(
            "The statement may only restate the public reaction function.",
        ),
        falsifiers=(
            "Subsequent official actions repeatedly contradict the stated path.",
        ),
        limitations=("Intent is inferred and is not an observed fact.",),
    )
    behavior = BehaviorResponseHypothesis(
        hypothesis_id="behavior:leveraged-deleveraging",
        audience_segment_ids=(baseline.event.audiences[0].segment_id,),
        trigger_fact_ids=(fact_id,),
        if_conditions=(
            "The statement is interpreted as a tighter future path.",
        ),
        then_expected_behaviors=("Reduce leveraged long exposure.",),
        observable_intermediates=(
            "Negative futures flow and wider basis dispersion.",
        ),
        mechanism="Belief revision interacts with binding margin constraints.",
        horizon="next two closed one-hour bars",
        evidence_refs=(fact_id, intent.inference_id),
        competing_explanations=(
            "Positioning may already be defensive and mute additional flow.",
        ),
        falsifiers=(
            "Leverage and directional flow rise without an offsetting event.",
        ),
        limitations=(
            "A cohort response does not identify any individual trader.",
        ),
    )
    event = replace(
        baseline.event,
        intent_hypotheses=(intent,),
        behavior_response_hypotheses=(behavior,),
    )
    return admit_information_event(event, decision_at=DECISION)


def _information_semantic_bindings(
    admission: AdmittedInformationEvent,
) -> dict[str, str]:
    """Reproduce the public typed bindings used by the Application catalog."""

    document = information_event_to_canonical_dict(admission.event)
    source_bindings = {
        row["artifact_id"]: canonical_digest(row)
        for row in document["source_artifacts"]
    }
    fact_bindings = {}
    for row in document["observed_facts"]:
        fact_bindings[row["fact_id"]] = canonical_digest(
            {
                "observed_fact": row,
                "source_artifact_bindings": {
                    ref: source_bindings[ref]
                    for ref in row["source_artifact_ids"]
                },
            }
        )
    actor_bindings = {
        row["actor_id"]: canonical_digest(row) for row in document["actors"]
    }
    role_bindings = {
        row["assignment_id"]: canonical_digest(row)
        for row in document["actor_role_assignments"]
    }
    audience_bindings = {
        row["segment_id"]: canonical_digest(row)
        for row in document["audiences"]
    }
    intent_bindings = {}
    observed_bindings = {**source_bindings, **fact_bindings}
    for row in document["intent_hypotheses"]:
        intent_bindings[row["inference_id"]] = canonical_digest(
            {
                "intent_hypothesis": row,
                "subject_actor_binding": actor_bindings[
                    row["subject_actor_id"]
                ],
                "evidence_bindings": {
                    ref: observed_bindings[ref]
                    for ref in row["evidence_refs"]
                },
            }
        )
    behavior_bindings = {}
    behavior_evidence = {**observed_bindings, **intent_bindings}
    for row in document["behavior_response_hypotheses"]:
        behavior_bindings[row["hypothesis_id"]] = canonical_digest(
            {
                "behavior_response_hypothesis": row,
                "audience_bindings": {
                    ref: audience_bindings[ref]
                    for ref in row["audience_segment_ids"]
                },
                "trigger_fact_bindings": {
                    ref: fact_bindings[ref]
                    for ref in row["trigger_fact_ids"]
                },
                "evidence_bindings": {
                    ref: behavior_evidence[ref]
                    for ref in row["evidence_refs"]
                },
            }
        )
    return {
        **source_bindings,
        **fact_bindings,
        **actor_bindings,
        **role_bindings,
        **audience_bindings,
        **intent_bindings,
        **behavior_bindings,
    }


def _subjective_psychology_cloud(
    *, intent_ref: str, behavior_ref: str
) -> ProbabilityCloud:
    return ProbabilityCloud(
        cloud_id="cloud:v31",
        mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
        decision_at=DECISION_AT,
        available_at="2026-08-06T09:55:00Z",
        horizon="next four hours",
        components=(
            CloudComponent(
                "path:lead",
                plausibility=PlausibilityLevel.HIGH,
                lower="0.4",
                upper="0.7",
                evidence_refs=(intent_ref,),
                opposition_refs=(behavior_ref,),
                sensitivity_notes=(
                    "The interpretation weakens if the response is not observed.",
                ),
            ),
            CloudComponent(
                "path:runner",
                plausibility=PlausibilityLevel.MEDIUM,
                lower="0.2",
                upper="0.6",
                evidence_refs=(behavior_ref,),
                opposition_refs=(intent_ref,),
                sensitivity_notes=(
                    "The alternative strengthens under a different response path.",
                ),
            ),
            CloudComponent(
                "OTHER",
                plausibility=PlausibilityLevel.MEDIUM,
                lower="0.1",
                upper="0.8",
            ),
            CloudComponent(
                "UNKNOWN", plausibility=PlausibilityLevel.UNKNOWN
            ),
        ),
        unknown_refs=("Private intent and positioning remain unobserved.",),
        limitations=("Psychological interpretations are uncalibrated.",),
    )


def _rebind_subjective_cloud(inputs: dict, cloud: ProbabilityCloud) -> None:
    admission = max(
        inputs["information_admissions"], key=lambda row: row.event.revision
    )
    paths = scenario_paths(inputs["pit_dataset"], inputs["expectation_ledger"])
    context = action_context(cloud)
    evaluation = complete_action_evaluation(
        context, cycle_index=inputs["cycle_index"]
    )
    prior, delta = graph_inputs(
        admission,
        inputs["pit_dataset"],
        cloud,
        paths,
        evaluation,
        inputs["hypothesis_registry"],
        inputs["expectation_ledger"],
    )
    receipt = seal_v31_inputs_receipt(
        run_id=inputs["run_id"],
        cycle_index=inputs["cycle_index"],
        decision_at=inputs["decision_at"],
        symbol=inputs["symbol"],
        information_event_digests=tuple(
            row.information_event_digest
            for row in inputs["information_admissions"]
        ),
        information_revision_registry_digest=inputs[
            "information_revision_registry"
        ]["information_revision_registry_digest"],
        pit_dataset_digest=inputs["pit_dataset"]["dataset_digest"],
        datum_revision_registry_digest=inputs["datum_revision_registry"][
            "datum_revision_registry_digest"
        ],
        sentiment_state_digest=inputs["sentiment_state"][
            "sentiment_state_digest"
        ],
        sentiment_change_digest=inputs["sentiment_change"][
            "sentiment_change_digest"
        ],
        prior_graph_digest=prior["graph_digest"],
        previous_accepted_state_digest=None,
        authority_snapshot_sha256=AUTHORITY_SHA256,
    )
    proposal = seal_v31_agent_proposal(
        inputs_receipt=receipt,
        sentiment_state_digest=inputs["sentiment_state"][
            "sentiment_state_digest"
        ],
        sentiment_change_digest=inputs["sentiment_change"][
            "sentiment_change_digest"
        ],
        graph_delta_digest=delta["graph_delta_digest"],
        hypothesis_registry_digest=inputs["hypothesis_registry"][
            "hypothesis_registry_digest"
        ],
        expectation_ledger_digest=inputs["expectation_ledger"][
            "expectation_ledger_digest"
        ],
        probability_cloud_digest=cloud.to_document()["cloud_digest"],
        scenario_path_set_digest=paths.to_document()["path_set_digest"],
        candidate_bindings={
            row["candidate_id"]: canonical_digest(row)
            for row in evaluation["candidates"]
        },
        information_interpretations=(
            "Intent and audience response remain contestable hypotheses.",
        ),
        competing_explanations=(
            "The observed move may instead reflect a common market shock.",
        ),
        unknowns=("Private intent and individual behavior remain unknown.",),
        requested_observations=("Observe the next closed synthetic bar.",),
        hypothesis_novelty_rationales={
            row["hypothesis_id"]: row["novelty_reason"]
            for row in inputs["hypothesis_registry"]["hypotheses"]
        },
        limitations=("Synthetic non-executable regression fixture only.",),
    )
    inputs.update(
        {
            "prior_graph": prior,
            "graph_delta": delta,
            "inputs_receipt": receipt,
            "agent_proposal": proposal,
            "probability_cloud": cloud,
            "scenario_paths": paths,
            "action_context": context,
            "action_evaluation": evaluation,
        }
    )


def _unknown_sentiment_for_cycle(
    *,
    cycle_index: int,
    as_of: datetime,
    pit_dataset_document: Mapping[str, object],
    previous_state: Mapping[str, object] | None = None,
) -> tuple[dict, list[dict], dict]:
    """Build a valid all-UNKNOWN sentiment vector with no evidence side channel."""

    timestamp = as_of.astimezone(UTC).isoformat().replace("+00:00", "Z")
    facts = []
    dimensions = []
    for index, (category, axis) in enumerate(
        zip(MARKET_CATEGORIES, SENTIMENT_AXES)
    ):
        facts.append(
            {
                "fact_id": f"unknown-sentiment-fact:{index}",
                "kind": "RAW_FACT",
                "category": category,
                "metric": f"unknown_sentiment_metric_{index}",
                "value": None,
                "unit": "INDEX",
                "symbol": "BTCUSDT",
                "timeframe": "1H",
                "window": "CLOSED_1H",
                "source_ref": f"fixture:unavailable:sentiment:{index}",
                "raw_ref": (
                    f"raw/unavailable/sentiment/{cycle_index}/{index}.json"
                ),
                "raw_sha256": None,
                "observed_at": timestamp,
                "available_at": timestamp,
                "quality": "UNKNOWN",
                "coverage": "0",
                "dependency_group": f"sentiment-group:{index}",
                "lineage": [],
                "transform": None,
                "limitations": "No inference-admissible sentiment datum.",
                "missing_reason": "FIXTURE_UNAVAILABLE",
            }
        )
        dimensions.append(
            {
                "axis": axis,
                "required_dependency_groups": [
                    f"sentiment-group:{index}",
                    f"sentiment-required-extra:{index}",
                ],
                "contributors": [],
                "timeframe_states": {"1h": None},
                "agent_interpretation": (
                    "No inference-admissible evidence; preserve UNKNOWN."
                ),
                "limitations": "Missing evidence is not neutral evidence.",
                "next_discriminating_observation": (
                    "Collect an independently admitted closed-window datum."
                ),
            }
        )
    snapshot = build_market_information_snapshot(
        run_id="run:v31",
        cycle_index=cycle_index,
        symbol="BTCUSDT",
        as_of=timestamp,
        facts=facts,
    )
    legacy_state = build_sentiment_state(
        market_snapshot=snapshot,
        dimension_inputs=dimensions,
        operational_synthesis=(
            "All axes remain UNKNOWN because no semantic evidence is admitted."
        ),
    )
    state = migrate_legacy_sentiment_state_to_v31(
        legacy_sentiment_state=legacy_state,
        market_information_snapshot=snapshot,
        pit_dataset_digest=str(pit_dataset_document["dataset_digest"]),
        sentiment_evidence_bindings={},
        downstream_scope="PATH_ACTION",
        previous_v31_sentiment_state=previous_state,
    )
    return snapshot, dimensions, state


def _reseal_agent_boundary(inputs: dict) -> None:
    old_receipt = inputs["inputs_receipt"]
    receipt = seal_v31_inputs_receipt(
        run_id=old_receipt["run_id"],
        cycle_index=old_receipt["cycle_index"],
        decision_at=old_receipt["decision_at"],
        symbol=old_receipt["symbol"],
        information_event_digests=old_receipt[
            "information_event_digests"
        ],
        information_revision_registry_digest=old_receipt[
            "information_revision_registry_digest"
        ],
        association_estimation_receipt_digests=old_receipt[
            "association_estimation_receipt_digests"
        ],
        pit_dataset_digest=old_receipt["pit_dataset_digest"],
        datum_revision_registry_digest=old_receipt[
            "datum_revision_registry_digest"
        ],
        sentiment_state_digest=inputs["sentiment_state"][
            "sentiment_state_digest"
        ],
        sentiment_change_digest=inputs["sentiment_change"][
            "sentiment_change_digest"
        ],
        prior_graph_digest=old_receipt["prior_graph_digest"],
        previous_accepted_state_digest=old_receipt[
            "previous_accepted_state_digest"
        ],
        previous_information_revision_registry_digest=old_receipt[
            "previous_information_revision_registry_digest"
        ],
        previous_pit_dataset_digest=old_receipt[
            "previous_pit_dataset_digest"
        ],
        previous_datum_revision_registry_digest=old_receipt[
            "previous_datum_revision_registry_digest"
        ],
        previous_sentiment_state_digest=(
            None
            if inputs["previous_sentiment_state"] is None
            else inputs["previous_sentiment_state"]["sentiment_state_digest"]
        ),
        previous_hypothesis_registry_digest=old_receipt[
            "previous_hypothesis_registry_digest"
        ],
        previous_expectation_ledger_digest=old_receipt[
            "previous_expectation_ledger_digest"
        ],
        previous_probability_cloud_digest=old_receipt[
            "previous_probability_cloud_digest"
        ],
        authority_snapshot_sha256=old_receipt["authority_snapshot_sha256"],
    )
    old_proposal = inputs["agent_proposal"]
    proposal = seal_v31_agent_proposal(
        inputs_receipt=receipt,
        sentiment_state_digest=inputs["sentiment_state"][
            "sentiment_state_digest"
        ],
        sentiment_change_digest=inputs["sentiment_change"][
            "sentiment_change_digest"
        ],
        graph_delta_digest=old_proposal["graph_delta_digest"],
        hypothesis_registry_digest=old_proposal[
            "hypothesis_registry_digest"
        ],
        expectation_ledger_digest=old_proposal[
            "expectation_ledger_digest"
        ],
        probability_cloud_digest=old_proposal["probability_cloud_digest"],
        scenario_path_set_digest=old_proposal[
            "scenario_path_set_digest"
        ],
        candidate_bindings=old_proposal["candidate_bindings"],
        information_interpretations=old_proposal[
            "information_interpretations"
        ],
        competing_explanations=old_proposal["competing_explanations"],
        unknowns=old_proposal["unknowns"],
        requested_observations=old_proposal["requested_observations"],
        hypothesis_novelty_rationales=old_proposal[
            "hypothesis_novelty_rationales"
        ],
        limitations=old_proposal["limitations"],
    )
    inputs["inputs_receipt"] = receipt
    inputs["agent_proposal"] = proposal


def _replace_with_unknown_sentiment(
    inputs: dict, *, previous_dataset: Mapping[str, object]
) -> None:
    _, _, previous_state = _unknown_sentiment_for_cycle(
        cycle_index=inputs["cycle_index"] - 1,
        as_of=DECISION - timedelta(minutes=2),
        pit_dataset_document=previous_dataset,
    )
    snapshot, dimensions, current_state = _unknown_sentiment_for_cycle(
        cycle_index=inputs["cycle_index"],
        as_of=DECISION,
        pit_dataset_document=inputs["pit_dataset"],
        previous_state=previous_state,
    )
    change = build_sentiment_state_change(
        current_sentiment_state=current_state,
        previous_sentiment_state=previous_state,
        changed_at=DECISION_AT,
    )
    inputs.update(
        {
            "market_information_snapshot": snapshot,
            "sentiment_dimension_inputs": dimensions,
            "previous_sentiment_state": previous_state,
            "sentiment_state": current_state,
            "sentiment_change": change,
        }
    )
    _reseal_agent_boundary(inputs)


def _empirical_cloud(evidence_ref: str) -> ProbabilityCloud:
    return ProbabilityCloud(
        cloud_id="cloud:v31",
        mode=ProbabilityMode.EMPIRICAL_OR_MODEL_CONDITIONAL,
        decision_at=DECISION_AT,
        available_at="2026-08-06T09:59:00Z",
        horizon="next four hours",
        components=(
            CloudComponent(
                "path:lead",
                lower="0.15",
                upper="0.55",
                evidence_refs=(evidence_ref,),
            ),
            CloudComponent("path:runner", lower="0.15", upper="0.55"),
            CloudComponent("OTHER", lower="0.10", upper="0.70"),
            CloudComponent("UNKNOWN"),
        ),
        event_contract_ref="conditional-path-event",
        event_contract_digest="a4f9d389f9f8d0aa3b9fcd3d91569f9a24f1eb259cf77457cbbd5cbcf94f8b01",
        sample_contract_refs=("frozen-walk-forward-sample",),
        model_refs=("conditional-model-v1",),
        limitations=("Fixture model is not calibrated.",),
    )


def _calibration_event_contract() -> dict[str, object]:
    outcomes = sorted(("path:lead", "path:runner", "OTHER"))
    return {
        "schema_id": "theory_paper_v2_v31_predictive_event_contract",
        "schema_version": "1.0.0",
        "event_contract_ref": "cycle-path-partition",
        "horizon": "next four hours",
        "outcome_ids": outcomes,
        "mutually_exclusive": True,
        "exhaustive": True,
        "resolution_rule": (
            "Resolve exactly one frozen path outcome from the next four closed bars."
        ),
    }


def _calibration_probabilities() -> tuple[tuple[str, str], ...]:
    return (
        ("OTHER", "0.33"),
        ("path:lead", "0.34"),
        ("path:runner", "0.33"),
    )


def _calibration_model_contract() -> dict[str, object]:
    event = _calibration_event_contract()
    return {
        "schema_id": "theory_paper_v2_v31_frozen_predictive_model",
        "schema_version": "1.0.0",
        "model_ref": "cycle-constant-model-v1",
        "event_contract_ref": "cycle-path-partition",
        "event_contract_digest": canonical_digest(event),
        "horizon": "next four hours",
        "outcome_ids": sorted(("path:lead", "path:runner", "OTHER")),
        "frozen_at": "2026-07-31T00:00:00Z",
        "training_data_cutoff": "2026-07-30T00:00:00Z",
        "model_kind": "CONSTANT_CATEGORICAL_DISTRIBUTION_V1",
        "frozen_probabilities": [
            {"outcome_id": outcome, "probability": probability}
            for outcome, probability in _calibration_probabilities()
        ],
        "implementation_digest": canonical_digest(
            {
                "algorithm": "CONSTANT_CATEGORICAL_DISTRIBUTION",
                "version": "1.0.0",
                "input_usage": "IGNORED_BY_DESIGN",
            }
        ),
    }


def _calibration_sample(
    split: str, *, start_at: datetime
) -> tuple[FrozenPredictionOutcome, ...]:
    observed = (
        ("path:lead",) * 34
        + ("path:runner",) * 33
        + ("OTHER",) * 33
    )
    rows = []
    for index, outcome in enumerate(observed):
        predicted_at = start_at + timedelta(minutes=10 * index)
        rows.append(
            FrozenPredictionOutcome(
                forecast=FrozenPredictiveForecast(
                    forecast_id=f"{split.lower()}-{index}",
                    prediction_at=predicted_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    model_input_digest=canonical_digest(
                        {"split": split, "index": index}
                    ),
                    probabilities=_calibration_probabilities(),
                ),
                observed_outcome=outcome,
                outcome_available_at=(predicted_at + timedelta(minutes=5))
                .isoformat()
                .replace("+00:00", "Z"),
            )
        )
    return tuple(rows)


def _calibration_receipt() -> PredictiveValidationReceipt:
    return PredictiveValidationReceipt(
        receipt_id="cycle-validation-v1",
        event_contract_ref="cycle-path-partition",
        event_contract=_calibration_event_contract(),
        horizon="next four hours",
        model_ref="cycle-constant-model-v1",
        model_contract=_calibration_model_contract(),
        development_sample=_calibration_sample(
            "DEVELOPMENT", start_at=datetime(2026, 8, 1, tzinfo=UTC)
        ),
        calibration_sample=_calibration_sample(
            "CALIBRATION", start_at=datetime(2026, 8, 2, tzinfo=UTC)
        ),
        oos_sample=_calibration_sample(
            "OOS", start_at=datetime(2026, 8, 3, tzinfo=UTC)
        ),
        deployment_forecast=FrozenPredictiveForecast(
            forecast_id="cycle-deployment-v1",
            prediction_at="2026-08-06T09:59:00Z",
            model_input_digest=canonical_digest(
                {"deployment": "2026-08-06T09:59:00Z"}
            ),
            probabilities=_calibration_probabilities(),
        ),
        scoring_rule=ProperScoringRule.BRIER,
        available_at="2026-08-04T00:00:00Z",
        invalidation_conditions=("Fixed drift limit is exceeded.",),
        limitations=("Local fixture has no external provenance claim.",),
    )


def _calibrated_cloud(
    evidence_ref: str, receipt: PredictiveValidationReceipt
) -> ProbabilityCloud:
    return ProbabilityCloud(
        cloud_id="cloud:v31",
        mode=ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION,
        decision_at=DECISION_AT,
        available_at="2026-08-06T09:59:00Z",
        horizon="next four hours",
        components=(
            CloudComponent(
                "path:lead",
                probability=Decimal("0.34"),
                evidence_refs=(evidence_ref,),
            ),
            CloudComponent("path:runner", probability=Decimal("0.33")),
            CloudComponent("OTHER", probability=Decimal("0.33")),
        ),
        event_contract_ref=receipt.event_contract_ref,
        event_contract_digest=receipt.event_contract_digest,
        sample_contract_refs=(receipt.receipt_id,),
        model_refs=(receipt.model_ref,),
        validation_receipts=(receipt,),
        limitations=("Local deterministic calibration fixture only.",),
        mutually_exclusive=True,
        exhaustive=True,
    )


class V31EpistemicP0RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.calibration_receipt = _calibration_receipt()

    def test_dataset_digest_is_input_boundary_not_semantic_evidence(self) -> None:
        baseline = full_inputs()
        dataset_digest = baseline["pit_dataset"]["dataset_digest"]
        self.assertEqual(
            dataset_digest, baseline["inputs_receipt"]["pit_dataset_digest"]
        )
        assemble_v31_cycle_evaluation(**baseline)

        hypothesis_attack = full_inputs(
            dynamic_bundle=_dynamic_bundle_with_bindings(
                {dataset_digest: dataset_digest}
            )
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_HYPOTHESIS_DELTA_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**hypothesis_attack)

        probability_attack = full_inputs()
        original_cloud = probability_attack["probability_cloud"]
        components = list(original_cloud.components)
        components[0] = replace(
            components[0], evidence_refs=(dataset_digest,)
        )
        probability_attack["probability_cloud"] = replace(
            original_cloud, components=tuple(components)
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_PROBABILITY_CLOUD_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**probability_attack)

        action_attack = full_inputs()
        action_attack["action_evaluation"] = _action_evaluation_with_evidence(
            action_attack, dataset_digest
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "V31_ACTION_EVIDENCE_NOT_ADMITTED"
        ):
            assemble_v31_cycle_evaluation(**action_attack)

    def test_downgraded_revision_invalidates_stale_active_hypothesis(self) -> None:
        prior_dataset = pit_dataset(
            decision_at=datetime(2026, 8, 6, 9, 58, tzinfo=UTC)
        )
        prior_observed = next(
            row
            for row in prior_dataset["data"]
            if row["datum_id"] == "datum:observed"
        )
        self.assertTrue(prior_observed["inference_admissible"])
        prior_registry, _, prior_ledger, _ = dynamic_research_state(
            decision_at="2026-08-06T09:58:00Z",
            evidence_digest=prior_observed["datum_digest"],
        )
        stale_registry = reduce_hypothesis_registry(
            previous_registry=prior_registry,
            deltas=[],
            decision_at=DECISION_AT,
        )
        stale_ledger = reduce_expectation_ledger(
            previous_ledger=prior_ledger,
            deltas=[],
            decision_at=DECISION_AT,
            valid_hypothesis_ids=stale_registry["known_hypothesis_ids"],
        )
        inputs = full_inputs(
            cycle_index=2,
            dynamic_bundle=(stale_registry, [], stale_ledger, []),
            previous_registry=prior_registry,
            previous_ledger=prior_ledger,
            previous_accepted_state_digest="a" * 64,
            previous_dataset=prior_dataset,
            previous_cloud=probability_cloud(),
            no_inference_dataset=True,
        )
        current_observed = next(
            row
            for row in inputs["pit_dataset"]["data"]
            if row["datum_id"] == "datum:observed"
        )
        self.assertEqual(2, current_observed["revision"])
        self.assertEqual("NO_INFERENCE", current_observed["claim_ceiling"])
        _replace_with_unknown_sentiment(
            inputs, previous_dataset=prior_dataset
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_HYPOTHESIS_ACTIVE_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_downgraded_revision_invalidates_stale_expectation_result(self) -> None:
        prior_dataset = pit_dataset(
            decision_at=datetime(2026, 8, 6, 9, 58, tzinfo=UTC)
        )
        prior_observed = next(
            row
            for row in prior_dataset["data"]
            if row["datum_id"] == "datum:observed"
        )
        prior_registry, _, prior_ledger, _ = dynamic_research_state(
            decision_at="2026-08-06T09:58:00Z",
            include_legacy_expectation=True,
            evidence_digest=prior_observed["datum_digest"],
        )
        revised_admission = revised_information_admissions()[1]
        revised_bindings = _information_semantic_bindings(revised_admission)
        revised_fact_ref = revised_admission.event.observed_facts[0].fact_id
        _, hypothesis_deltas, _, expectation_deltas = (
            second_cycle_dynamic_state(
                prior_registry,
                prior_ledger,
                current_evidence_digest=revised_bindings[revised_fact_ref],
            )
        )
        hypothesis_deltas = copy.deepcopy(hypothesis_deltas)
        for delta in hypothesis_deltas:
            delta["evidence_ids"] = [revised_fact_ref]
            delta["evidence_bindings"] = {
                revised_fact_ref: revised_bindings[revised_fact_ref]
            }
            for hypothesis in delta["replacement_hypotheses"]:
                hypothesis["active_evidence_ids"] = [revised_fact_ref]
                hypothesis["active_evidence_bindings"] = {
                    revised_fact_ref: revised_bindings[revised_fact_ref]
                }
        registry = reduce_hypothesis_registry(
            previous_registry=prior_registry,
            deltas=hypothesis_deltas,
            decision_at=DECISION_AT,
        )
        expectation_deltas = copy.deepcopy(expectation_deltas)
        closed_expectation = expectation_deltas[0]["expectation"]
        closed_expectation["result_evidence_refs"] = ["datum:observed"]
        closed_expectation["result_evidence_bindings"] = {
            "datum:observed": prior_observed["datum_digest"]
        }
        ledger = reduce_expectation_ledger(
            previous_ledger=prior_ledger,
            deltas=expectation_deltas,
            decision_at=DECISION_AT,
            valid_hypothesis_ids=registry["known_hypothesis_ids"],
        )
        inputs = full_inputs(
            cycle_index=2,
            dynamic_bundle=(
                registry,
                hypothesis_deltas,
                ledger,
                expectation_deltas,
            ),
            previous_registry=prior_registry,
            previous_ledger=prior_ledger,
            previous_accepted_state_digest="a" * 64,
            previous_dataset=prior_dataset,
            previous_cloud=probability_cloud(),
            no_inference_dataset=True,
        )
        _replace_with_unknown_sentiment(
            inputs, previous_dataset=prior_dataset
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_EXPECTATION_RESULT_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_context_and_psychology_cannot_enter_empirical_or_calibrated_clouds(
        self,
    ) -> None:
        admission = _information_with_psychological_hypotheses()
        document = information_event_to_canonical_dict(admission.event)
        forbidden_refs = {
            "actor": document["actors"][0]["actor_id"],
            "role": document["actor_role_assignments"][0]["assignment_id"],
            "audience": document["audiences"][0]["segment_id"],
            "event_id": admission.event.event_id,
            "event_digest": admission.information_event_digest,
            "intent": document["intent_hypotheses"][0]["inference_id"],
            "behavior": document["behavior_response_hypotheses"][0][
                "hypothesis_id"
            ],
        }
        for label, evidence_ref in forbidden_refs.items():
            for mode, cloud in (
                ("EMPIRICAL", _empirical_cloud(evidence_ref)),
                (
                    "CALIBRATED",
                    _calibrated_cloud(
                        evidence_ref, self.calibration_receipt
                    ),
                ),
            ):
                with self.subTest(label=label, mode=mode):
                    inputs = full_inputs(
                        information_admissions_override=(admission,)
                    )
                    inputs["probability_cloud"] = cloud
                    with self.assertRaisesRegex(
                        V31ResearchCycleError,
                        "V31_PROBABILITY_CLOUD_EVIDENCE_NOT_ADMITTED",
                    ):
                        assemble_v31_cycle_evaluation(**inputs)

    def test_intent_and_behavior_are_admitted_only_as_hypotheses_in_subjective_mode(
        self,
    ) -> None:
        admission = _information_with_psychological_hypotheses()
        bindings = _information_semantic_bindings(admission)
        intent_ref = admission.event.intent_hypotheses[0].inference_id
        behavior_ref = admission.event.behavior_response_hypotheses[
            0
        ].hypothesis_id
        inputs = full_inputs(
            information_admissions_override=(admission,),
            dynamic_bundle=_dynamic_bundle_with_bindings(
                {
                    intent_ref: bindings[intent_ref],
                    behavior_ref: bindings[behavior_ref],
                }
            ),
        )
        cloud = _subjective_psychology_cloud(
            intent_ref=intent_ref, behavior_ref=behavior_ref
        )
        _rebind_subjective_cloud(inputs, cloud)
        result = assemble_v31_cycle_evaluation(**inputs)
        self.assertEqual(
            cloud.to_document()["cloud_digest"],
            result["probability_cloud_digest"],
        )


if __name__ == "__main__":
    unittest.main()
