from __future__ import annotations

import copy
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trade_system.theory_paper_v2.application.v31_durable_cycle import (
    V31DurableCycleError,
    persist_completed_v31_cycle,
)
from trade_system.theory_paper_v2.application.v31_research_cycle import (
    V31ResearchCycleError,
    assemble_v31_cycle_evaluation,
    complete_v31_research_cycle,
    select_v31_cycle_action,
    verify_v31_accepted_state,
    verify_v31_completion_receipt,
    verify_v31_cycle_evaluation,
)
from trade_system.theory_paper_v2.domain.association_model import (
    INTERPRETATION_BOUNDARIES,
    build_association_revision,
)
from trade_system.theory_paper_v2.domain.association_estimation import (
    PairedNumericObservation,
    estimate_pearson_association,
)
from trade_system.theory_paper_v2.domain.agent_research_contract import (
    seal_v31_agent_proposal,
    seal_v31_inputs_receipt,
)
from trade_system.theory_paper_v2.domain.behavior_planning import (
    ActionCandidate,
    ActionEvaluation,
    ActionType,
    PortfolioDecisionContext,
    PositionSide,
    PositionRole,
    ReversibilityClass,
    action_evaluations_from_financial_receipt,
    legal_action_keys,
    seal_complete_action_evaluation,
)
from trade_system.theory_paper_v2.domain.financial_evaluation import (
    build_financial_evaluation_receipt,
    build_financial_risk_policy,
)
from trade_system.theory_paper_v2.domain.portfolio_truth import (
    build_lot_position_truth,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.data_model import (
    ConflictState,
    DataQuality,
    DatumEpistemicType,
    DatumValueType,
    Missingness,
    PointInTimeDatum,
    ProxyLevel,
    QualityLevel,
    UncertaintyKind,
    UncertaintyRepresentation,
    admit_point_in_time_dataset,
    build_point_in_time_datum_revision_registry,
    point_in_time_dataset_rows_from_document,
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
from trade_system.theory_paper_v2.domain.information_model import (
    ActorKind,
    ActorRole,
    ActorRoleAssignment,
    AdmittedInformationEvent,
    AudienceKind,
    AudienceSegment,
    CommitmentLevel,
    InformationActor,
    InformationChannel,
    InformationEvent,
    InformationForm,
    InformationNovelty,
    InformationScope,
    InstitutionalStatus,
    ObservedFactKind,
    ObservedInformationFact,
    PropagationClass,
    Reversibility,
    RoleAssignmentBasis,
    SourceArtifactRef,
    SourceCoverage,
    SourceQuality,
    SourceType,
    admit_information_event,
    build_information_event_revision_registry,
)
from trade_system.theory_paper_v2.domain.market_knowledge_graph import (
    build_graph_delta,
    build_graph_node_revision,
    create_market_knowledge_graph,
)
from trade_system.theory_paper_v2.domain.probability_cloud import (
    CloudUpdateEvidence,
    CloudComponent,
    EvidenceEffect,
    PlausibilityLevel,
    ProbabilityCloud,
    ProbabilityMode,
    seal_probability_cloud_update,
)
from trade_system.theory_paper_v2.domain.scenario_path import (
    ActionImplication,
    EpistemicStage,
    EpistemicTransition,
    ExpectedObservation,
    ImplicationEffect,
    PathPredicate,
    PredicateQuality,
    PredicateOperator,
    PredicateTiming,
    ScenarioPathRule,
    ScenarioPathSet,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)


DECISION_AT = "2026-08-06T10:00:00Z"
DECISION = datetime(2026, 8, 6, 10, tzinfo=UTC)
PATH_IDS = ("path:lead", "path:runner", "OTHER")
AUTHORITY_SHA256 = "d" * 64


def information_admission() -> AdmittedInformationEvent:
    published = DECISION - timedelta(hours=1)
    observed = published + timedelta(minutes=1)
    available = published + timedelta(minutes=2)
    actor = InformationActor(
        actor_id="actor:authority",
        display_name="Fixture Authority",
        actor_kind=ActorKind.INSTITUTION,
        jurisdictions=("fixture",),
        provenance_refs=("registry:authority",),
        limitations=("synthetic identity",),
    )
    source = SourceArtifactRef(
        artifact_id="source:policy",
        publisher_actor_id=actor.actor_id,
        locator="fixture://policy",
        source_type=SourceType.OFFICIAL_FULL_TEXT,
        channel=InformationChannel.OFFICIAL_RELEASE,
        propagation_class=PropagationClass.PRIMARY,
        quality=SourceQuality.VERIFIED_PRIMARY,
        coverage=SourceCoverage.FULL_TEXT,
        content_sha256="a" * 64,
        language="en",
        published_at=published,
        observed_at=observed,
        available_at=available,
        provenance_refs=("receipt:policy",),
        limitations=("synthetic source",),
    )
    role = ActorRoleAssignment(
        assignment_id="role:authority",
        actor_id=actor.actor_id,
        role=ActorRole.RULE_AND_SYSTEM_AUTHORITY,
        basis=RoleAssignmentBasis.LEGAL_OR_INSTITUTIONAL_MANDATE,
        authority_scope=("monetary-policy",),
        valid_from=published - timedelta(days=1),
        valid_to=published + timedelta(days=1),
        evidence_refs=(source.artifact_id,),
        limitations=("scope-bound role",),
    )
    audience = AudienceSegment(
        segment_id="audience:leveraged",
        label="Leveraged directional cohort",
        audience_kinds=(AudienceKind.LEVERAGED_DIRECTIONAL,),
        market_scopes=("BTCUSDT",),
        constraints=("margin capacity",),
        provenance_refs=("taxonomy:audience",),
        limitations=("individual membership unknown",),
    )
    fact = ObservedInformationFact(
        fact_id="fact:information:policy",
        fact_kind=ObservedFactKind.PUBLISHED_CONTENT,
        statement="The authority published a conditional policy statement.",
        source_artifact_ids=(source.artifact_id,),
        observed_at=observed,
        limitations=("intent is not observed",),
    )
    event = InformationEvent(
        event_id="information-event:policy",
        revision=1,
        previous_revision_digest=None,
        primary_actor_id=actor.actor_id,
        actors=(actor,),
        actor_role_assignments=(role,),
        scopes=(InformationScope.GLOBAL_MACRO, InformationScope.INSTRUMENT),
        information_form=InformationForm.FORWARD_GUIDANCE,
        institutional_status=InstitutionalStatus.APPROVED,
        channel=InformationChannel.OFFICIAL_RELEASE,
        audiences=(audience,),
        observable_message_or_action="A full-text policy statement was published.",
        novelty=InformationNovelty.NEW,
        commitment=CommitmentLevel.NON_BINDING,
        reversibility=Reversibility.REVERSIBLE,
        propagation_class=PropagationClass.PRIMARY,
        published_at=published,
        observed_at=observed,
        available_at=available,
        effective_at=published + timedelta(days=1),
        revised_at=None,
        source_artifacts=(source,),
        observed_facts=(fact,),
        intent_hypotheses=(),
        behavior_response_hypotheses=(),
        limitations=("synthetic event; no direction claim",),
    )
    return admit_information_event(event, decision_at=DECISION)


def revised_information_admissions() -> tuple[
    AdmittedInformationEvent, AdmittedInformationEvent
]:
    first = information_admission()
    revised_observed_at = DECISION - timedelta(minutes=56)
    revised_available_at = DECISION - timedelta(minutes=55)
    source = replace(
        first.event.source_artifacts[0],
        artifact_id="source:policy:revision-2",
        content_sha256="c" * 64,
        observed_at=revised_observed_at,
        available_at=revised_available_at,
        provenance_refs=("receipt:policy:revision-2",),
    )
    role = replace(
        first.event.actor_role_assignments[0],
        evidence_refs=(source.artifact_id,),
    )
    fact = replace(
        first.event.observed_facts[0],
        fact_id="fact:information:policy:revision-2",
        source_artifact_ids=(source.artifact_id,),
        observed_at=revised_observed_at,
        statement="The authority published a revised conditional statement.",
    )
    revised_event = replace(
        first.event,
        revision=2,
        previous_revision_digest=first.information_event_digest,
        actor_role_assignments=(role,),
        novelty=InformationNovelty.REVISION,
        observed_at=revised_observed_at,
        available_at=revised_available_at,
        revised_at=DECISION - timedelta(minutes=57),
        source_artifacts=(source,),
        observed_facts=(fact,),
    )
    second = admit_information_event(
        revised_event,
        decision_at=DECISION,
        prior_revision=first.event,
    )
    return first, second


def quality() -> DataQuality:
    return DataQuality(
        source_reliability=QualityLevel.HIGH,
        completeness=QualityLevel.HIGH,
        timeliness=QualityLevel.HIGH,
        semantic_fidelity=QualityLevel.HIGH,
        measurement_error=QualityLevel.MEDIUM,
        revision_risk=QualityLevel.LOW,
        cross_source_consistency=QualityLevel.UNKNOWN,
        lineage_integrity=QualityLevel.HIGH,
        dependency_independence=QualityLevel.MEDIUM,
        regime_applicability=QualityLevel.UNKNOWN,
        limitations=("synthetic fixture",),
    )


def sentiment_state_for_cycle(
    *,
    cycle_index: int,
    as_of: datetime,
    pit_dataset: dict,
    previous_sentiment_state: dict | None = None,
) -> tuple[dict, list[dict], dict]:
    timestamp = as_of.astimezone(UTC).isoformat().replace("+00:00", "Z")
    observed_datum = next(
        row for row in pit_dataset["data"] if row["datum_id"] == "datum:observed"
    )
    facts: list[dict] = []
    dimensions: list[dict] = []
    for index, (category, axis) in enumerate(zip(MARKET_CATEGORIES, SENTIMENT_AXES)):
        contributor_is_admitted = (
            index == 0 and observed_datum["inference_admissible"] is True
        )
        missing = not contributor_is_admitted
        facts.append(
            {
                "fact_id": f"sentiment-fact:{index}",
                "kind": "RAW_FACT",
                "category": (
                    observed_datum["category"] if contributor_is_admitted else category
                ),
                "metric": (
                    observed_datum["metric"]
                    if contributor_is_admitted
                    else f"unobserved_sentiment_metric_{index}"
                ),
                "value": observed_datum["value"] if contributor_is_admitted else None,
                "unit": observed_datum["unit"] if contributor_is_admitted else "INDEX",
                "symbol": (
                    observed_datum["instrument_id"]
                    if contributor_is_admitted
                    else "BTCUSDT"
                ),
                "timeframe": (
                    observed_datum["timeframe"] if contributor_is_admitted else "1H"
                ),
                "window": (
                    observed_datum["window"]
                    if contributor_is_admitted
                    else "CLOSED_1H"
                ),
                "source_ref": (
                    observed_datum["source_ref"]
                    if contributor_is_admitted
                    else f"fixture:unavailable:sentiment:{index}"
                ),
                "raw_ref": (
                    observed_datum["raw_ref"]
                    if contributor_is_admitted
                    else f"raw/unavailable/sentiment/{cycle_index}/{index}.json"
                ),
                "raw_sha256": (
                    observed_datum["raw_sha256"]
                    if contributor_is_admitted
                    else None
                ),
                "observed_at": (
                    observed_datum["observed_at"]
                    if contributor_is_admitted
                    else timestamp
                ),
                "available_at": (
                    observed_datum["available_at"]
                    if contributor_is_admitted
                    else timestamp
                ),
                "quality": "UNKNOWN" if missing else "GOOD",
                "coverage": "0" if missing else "1",
                "dependency_group": (
                    observed_datum["dependency_group"]
                    if contributor_is_admitted
                    else f"sentiment-group:{index}"
                ),
                "lineage": [],
                "transform": None,
                "limitations": "synthetic ordinal sentiment fixture",
                "missing_reason": "FIXTURE_UNAVAILABLE" if missing else None,
            }
        )
        dimensions.append(
            {
                "axis": axis,
                "required_dependency_groups": [
                    (
                        observed_datum["dependency_group"]
                        if contributor_is_admitted
                        else f"sentiment-group:{index}"
                    ),
                    f"sentiment-required-extra:{index}",
                ],
                "contributors": (
                    []
                    if missing
                    else [
                        {
                            "fact_id": f"sentiment-fact:{index}",
                            "ordinal_contribution": 1,
                            "rule": "fixture observed value supports the positive axis state",
                            "direction": "POSITIVE",
                        }
                    ]
                ),
                "timeframe_states": {"1h": None if missing else 1},
                "agent_interpretation": "explicit evidence-bound fixture interpretation",
                "limitations": "synthetic values do not establish a market forecast",
                "next_discriminating_observation": "observe the next closed fixture bar",
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
        operational_synthesis="mixed ordinal axes with explicit UNKNOWN and no total probability",
    )
    state = migrate_legacy_sentiment_state_to_v31(
        legacy_sentiment_state=legacy_state,
        market_information_snapshot=snapshot,
        pit_dataset_digest=pit_dataset["dataset_digest"],
        sentiment_evidence_bindings=(
            {
                "sentiment-fact:0": {
                    "evidence_ref": observed_datum["datum_id"],
                    "evidence_digest": observed_datum["datum_digest"],
                    "admissibility_level": "INFERENCE_ADMISSIBLE",
                }
            }
            if observed_datum["inference_admissible"] is True
            else {}
        ),
        downstream_scope="PATH_ACTION",
        previous_v31_sentiment_state=previous_sentiment_state,
    )
    return snapshot, dimensions, state


def datum_kwargs(
    *,
    datum_id: str,
    epistemic_type: DatumEpistemicType,
    value: str,
    input_refs: tuple[str, ...] = (),
    input_digests: tuple[str, ...] = (),
) -> dict:
    values = {
        "datum_id": datum_id,
        "epistemic_type": epistemic_type,
        "data_kind": "MARKET_FACT" if epistemic_type is DatumEpistemicType.OBSERVED_FACT else "DERIVED_FEATURE",
        "category": "PRICE_AND_RETURNS",
        "metric": "MARK_PRICE" if epistemic_type is DatumEpistemicType.OBSERVED_FACT else "RETURN_1H",
        "value": value,
        "value_type": DatumValueType.NUMERIC,
        "unit": "INDEX",
        "currency": "USDT",
        "frequency": "SNAPSHOT",
        "timeframe": "1H",
        "window": "CLOSED_1H",
        "instrument_id": "BTCUSDT",
        "asset_class": "CRYPTO_DERIVATIVE",
        "venue_id": "FIXTURE",
        "entity_ids": (),
        "actor_ids": ("actor:authority",),
        "audience_ids": ("audience:leveraged",),
        "event_ids": ("information-event:policy",),
        "source_id": "fixture-data",
        "source_type": "PRIMARY_MARKET_DATA",
        "source_ref": f"capture:{datum_id}",
        "raw_ref": f"raw/{datum_id}.json" if not input_refs else None,
        "raw_sha256": "b" * 64 if not input_refs else None,
        "as_of": DECISION - timedelta(minutes=11),
        "observed_at": DECISION - timedelta(minutes=10),
        "published_at": DECISION - timedelta(minutes=10),
        "available_at": DECISION - timedelta(minutes=9),
        "effective_at": None,
        "revised_at": None,
        "vintage_id": "2026-08-06T09:51Z",
        "revision": 1,
        "revision_of_digest": None,
        "formula_version": "return-v1" if input_refs else None,
        "input_refs": input_refs,
        "quality": quality(),
        "coverage": "1",
        "missingness": Missingness.OBSERVED,
        "missing_reason": None,
        "staleness": "9m",
        "conflict_state": ConflictState.NONE,
        "proxy_level": ProxyLevel.MODEL_DERIVED if input_refs else ProxyLevel.DIRECT,
        "uncertainty": UncertaintyRepresentation(kind=UncertaintyKind.NONE_DECLARED),
        "regime_ref": None,
        "dependency_group": "dependency:shared",
        "lineage": input_refs or (f"capture:{datum_id}",),
        "limitations": ("synthetic datum",),
    }
    if "input_digests" in PointInTimeDatum.__dataclass_fields__:
        values["input_digests"] = input_digests
    return values


def pit_dataset(
    *,
    decision_at: datetime = DECISION,
    previous_dataset: dict | None = None,
    hypothesis_only_quality: bool = False,
    no_inference_quality: bool = False,
) -> dict:
    observed_values = datum_kwargs(
        datum_id="datum:observed",
        epistemic_type=DatumEpistemicType.OBSERVED_FACT,
        value="100",
    )
    if hypothesis_only_quality:
        observed_values["quality"] = replace(
            quality(), source_reliability=QualityLevel.LOW
        )
    if no_inference_quality:
        observed_values["conflict_state"] = ConflictState.SOURCE_CONFLICT
    prior_rows = {}
    if previous_dataset is not None:
        prior_rows = {
            row.datum_id: row
            for row in point_in_time_dataset_rows_from_document(previous_dataset)
        }
        observed_values.update(
            {
                "observed_at": DECISION - timedelta(minutes=4),
                "available_at": DECISION - timedelta(minutes=3),
                "revised_at": DECISION - timedelta(minutes=5),
                "vintage_id": "2026-08-06T09:57Z",
                "revision": 2,
                "revision_of_digest": prior_rows[
                    "datum:observed"
                ].to_document()["datum_digest"],
            }
        )
    observed = PointInTimeDatum(**observed_values)
    observed_digest = observed.to_document()["datum_digest"]
    derived_values = datum_kwargs(
        datum_id="datum:measure",
        epistemic_type=DatumEpistemicType.DERIVED_MEASURE,
        value="0.01",
        input_refs=(observed.datum_id,),
        input_digests=(observed_digest,),
    )
    if hypothesis_only_quality:
        derived_values["quality"] = replace(
            quality(), source_reliability=QualityLevel.LOW
        )
    if no_inference_quality:
        derived_values["conflict_state"] = ConflictState.SOURCE_CONFLICT
    if previous_dataset is not None:
        derived_values.update(
            {
                "observed_at": DECISION - timedelta(minutes=3),
                "available_at": DECISION - timedelta(minutes=2),
                "revised_at": DECISION - timedelta(minutes=4),
                "vintage_id": "2026-08-06T09:58Z",
                "revision": 2,
                "revision_of_digest": prior_rows[
                    "datum:measure"
                ].to_document()["datum_digest"],
            }
        )
    derived = PointInTimeDatum(**derived_values)
    return admit_point_in_time_dataset(
        dataset_id="dataset:v31",
        decision_at=decision_at,
        data=(observed, derived),
        prior_revisions=prior_rows,
    )


def hypothesis_document(
    hypothesis_id: str,
    *,
    hypothesis_type: str,
    family: str,
    directional_bias: str,
    revision: int = 1,
    state: str = "ACTIVE",
    created_at: str = "2026-08-06T09:50:00Z",
    updated_at: str = "2026-08-06T09:50:00Z",
    evidence_digest: str = "a" * 64,
) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "revision": revision,
        "hypothesis_type": hypothesis_type,
        "directional_bias": directional_bias,
        "family_label": family,
        "deduplication_key": f"dedup:{family}",
        "state": state,
        "parent_hypothesis_ids": [],
        "supersedes_ids": [],
        "derived_from_expectation_ids": [],
        "created_at": created_at,
        "updated_at": updated_at,
        "horizon": "next four closed 1h bars",
        "timeframe_scope": ["1h", "4h"],
        "premises": [f"registered premise for {family}"],
        "expected_sequence": [f"registered sequence for {family}"],
        "support_rules": [f"registered support rule for {family}"],
        "oppose_rules": [f"registered opposition rule for {family}"],
        "hard_falsifiers": [f"falsifier:{hypothesis_id}"],
        "expiry": "2026-08-07T10:00:00Z",
        "trade_triggers": [],
        "forbidden_conditions": [],
        "active_evidence_ids": ["datum:observed"],
        "active_evidence_bindings": {"datum:observed": evidence_digest},
        "support_level": "PLAUSIBLE",
        "limitations": ["synthetic fixture"],
        "novelty_reason": "a separately registered process and evidence path",
        "agent_rationale": "keep open until a registered falsifier arrives",
    }


def hypothesis_delta(
    delta_id: str,
    operation: str,
    *,
    targets: list[str],
    replacements: list[dict],
    at: str = "2026-08-06T09:55:00Z",
    evidence_digest: str = "a" * 64,
) -> dict:
    return {
        "delta_id": delta_id,
        "operation": operation,
        "occurred_at": at,
        "target_hypothesis_ids": targets,
        "replacement_hypotheses": replacements,
        "evidence_ids": ["datum:observed"],
        "evidence_bindings": {"datum:observed": evidence_digest},
        "matched_hard_falsifier": None,
        "agent_rationale": "explicit synthetic lifecycle transition",
    }


def expectation_document(
    expectation_id: str,
    *,
    hypothesis_id: str,
    metric: str,
    revision: int = 1,
    status: str = "OPEN",
    created_at: str = "2026-08-06T09:55:00Z",
    updated_at: str = "2026-08-06T09:55:00Z",
    closed_at: str | None = None,
    result_refs: list[str] | None = None,
    result_evidence_digest: str = "a" * 64,
) -> dict:
    return {
        "expectation_id": expectation_id,
        "revision": revision,
        "hypothesis_id": hypothesis_id,
        "parent_expectation_id": None,
        "deduplication_key": f"dedup:{expectation_id}",
        "created_at": created_at,
        "updated_at": updated_at,
        "observation_start": "2026-08-06T10:00:00Z",
        "observation_deadline": "2026-08-06T11:00:00Z",
        "if_conditions": [f"{hypothesis_id} remains active"],
        "expected_observations": [
            {
                "metric": metric,
                "direction_or_range": "persists",
                "timeframe": "1h",
                "source_requirement": "closed synthetic bar",
            }
        ],
        "falsifying_observations": [
            {
                "metric": metric,
                "direction_or_range": "reverses",
                "timeframe": "1h",
                "source_requirement": "closed synthetic bar",
            }
        ],
        "evidence_sufficiency": "LOW",
        "status": status,
        "result_evidence_refs": result_refs or [],
        "result_evidence_bindings": {
            ref: result_evidence_digest for ref in (result_refs or [])
        },
        "closed_at": closed_at,
        "result_note": "registered close result" if closed_at else None,
    }


def expectation_delta(
    delta_id: str,
    operation: str,
    document: dict,
    *,
    target: str | None = None,
    at: str = "2026-08-06T09:55:00Z",
) -> dict:
    return {
        "delta_id": delta_id,
        "operation": operation,
        "occurred_at": at,
        "target_expectation_id": target,
        "expectation": document,
        "agent_rationale": "explicit synthetic expectation transition",
    }


def dynamic_research_state(
    *,
    decision_at: str = DECISION_AT,
    include_legacy_expectation: bool = False,
    evidence_digest: str = "a" * 64,
) -> tuple[dict, list[dict], dict, list[dict]]:
    hypotheses = (
        hypothesis_document(
            "hypothesis:mechanism",
            hypothesis_type="MECHANISM",
            family="information-liquidity-mechanism",
            directional_bias="BIDIRECTIONAL",
            evidence_digest=evidence_digest,
        ),
        hypothesis_document(
            "path:lead",
            hypothesis_type="PATH",
            family="lead-continuation-path",
            directional_bias="LONG",
            evidence_digest=evidence_digest,
        ),
        hypothesis_document(
            "path:runner",
            hypothesis_type="PATH",
            family="runner-reversal-path",
            directional_bias="SHORT",
            evidence_digest=evidence_digest,
        ),
    )
    hypothesis_deltas = [
        hypothesis_delta(
            f"delta:create:{row['hypothesis_id']}",
            "CREATE",
            targets=[],
            replacements=[row],
            evidence_digest=evidence_digest,
        )
        for row in hypotheses
    ]
    registry = reduce_hypothesis_registry(
        previous_registry=None,
        deltas=hypothesis_deltas,
        decision_at=decision_at,
    )
    expectation_specs = (
        ("expectation:path:lead", "path:lead", "datum:observed"),
        ("expectation:path:runner", "path:runner", "datum:measure"),
        ("expectation:OTHER", "hypothesis:mechanism", "datum:observed"),
    )
    expectation_deltas = [
        expectation_delta(
            f"delta:create:{expectation_id}",
            "CREATE",
            expectation_document(
                expectation_id,
                hypothesis_id=hypothesis_id,
                metric=metric,
            ),
        )
        for expectation_id, hypothesis_id, metric in expectation_specs
    ]
    if include_legacy_expectation:
        expectation_deltas.append(
            expectation_delta(
                "delta:create:expectation:legacy",
                "CREATE",
                expectation_document(
                    "expectation:legacy",
                    hypothesis_id="hypothesis:mechanism",
                    metric="legacy:observable",
                ),
            )
        )
    ledger = reduce_expectation_ledger(
        previous_ledger=None,
        deltas=expectation_deltas,
        decision_at=decision_at,
        valid_hypothesis_ids=registry["known_hypothesis_ids"],
    )
    return registry, hypothesis_deltas, ledger, expectation_deltas


def probability_cloud(*, circular_evidence: bool = False) -> ProbabilityCloud:
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
                evidence_refs=(
                    ("cloud:v31",)
                    if circular_evidence
                    else ("datum:observed",)
                ),
                opposition_refs=("datum:measure",),
                sensitivity_notes=("lead weakens if the derived measure reverses",),
            ),
            CloudComponent(
                "path:runner",
                plausibility=PlausibilityLevel.MEDIUM,
                lower="0.2",
                upper="0.6",
                evidence_refs=("datum:measure",),
                opposition_refs=("datum:observed",),
                sensitivity_notes=("runner strengthens if the observed fact reverses",),
            ),
            CloudComponent("OTHER", plausibility=PlausibilityLevel.MEDIUM, lower="0.1", upper="0.8"),
            CloudComponent("UNKNOWN", plausibility=PlausibilityLevel.UNKNOWN),
        ),
        unknown_refs=("unobserved mechanisms remain",),
        limitations=("uncalibrated plausibility envelope",),
    )


def path_predicate(
    *,
    predicate_id: str,
    datum_id: str,
    datum_digest: str | None,
    expected: str,
    timing: PredicateTiming = PredicateTiming.DECISION_INPUT,
) -> PathPredicate:
    values = {
        "predicate_id": predicate_id,
        "fact_ref": datum_id,
        "fact_digest": datum_digest,
        "timing": timing,
        "operator": PredicateOperator.EQ,
        "expected": expected,
        "available_at": (
            "2026-08-06T09:51:00Z"
            if timing is PredicateTiming.DECISION_INPUT
            else "2026-08-06T11:00:00Z"
        ),
        "minimum_quality": PredicateQuality.MEDIUM,
        "minimum_coverage": "1",
        "allowed_conflict_states": ("NONE",),
        "limitations": ("synthetic predicate",),
    }
    return PathPredicate(**values)


def scenario_paths(
    dataset: dict, ledger: dict, *, false_lead_path: bool = False
) -> ScenarioPathSet:
    by_id = {row["datum_id"]: row for row in dataset["data"]}
    expectations_by_id = {
        row["expectation_id"]: row for row in ledger["expectations"]
    }
    rules = []
    for index, path_id in enumerate(PATH_IDS):
        datum_id = "datum:observed" if index != 1 else "datum:measure"
        datum_digest = by_id[datum_id]["datum_digest"]
        hypothesis_ref = (
            path_id if path_id in {"path:lead", "path:runner"} else "hypothesis:mechanism"
        )
        expectation_id = f"expectation:{path_id}"
        expectation = expectations_by_id[expectation_id]
        implication_action = {
            "path:lead": ActionType.OPEN_LONG,
            "path:runner": ActionType.OPEN_SHORT,
            "OTHER": ActionType.WAIT,
        }[path_id]
        rules.append(
            ScenarioPathRule(
                path_id=path_id,
                decision_at=DECISION_AT,
                triggers=(path_predicate(
                    predicate_id=f"trigger:{path_id}",
                    datum_id=datum_id,
                    datum_digest=datum_digest,
                    expected=(
                        "not-the-observed-value"
                        if false_lead_path and path_id == "path:lead"
                        else by_id[datum_id]["value"]
                    ),
                ),),
                guards=(path_predicate(predicate_id=f"guard:{path_id}", datum_id="datum:observed", datum_digest=by_id["datum:observed"]["datum_digest"], expected="100"),),
                unless=(),
                transition=EpistemicTransition(from_stage=EpistemicStage.ASSOCIATION, to_stage=EpistemicStage.INFERENCE, target_ref=f"inference:{path_id}", update_type="ADD"),
                mechanism="Information may propagate through constrained liquidity.",
                mechanism_hypothesis_refs=(
                    ("hypothesis:mechanism",)
                    if hypothesis_ref == "hypothesis:mechanism"
                    else ("hypothesis:mechanism", hypothesis_ref)
                ),
                expectations=(ExpectedObservation(observation_id=expectation_id, hypothesis_id=expectation["hypothesis_id"], expectation_revision_digest=canonical_digest(expectation), observable_ref=datum_id, horizon_at=expectation["observation_deadline"], direction_or_state="persists", confirms_when="persists", contradicts_when="reverses"),),
                falsifiers=(
                    path_predicate(
                        predicate_id=f"falsifier:{path_id}",
                        datum_id=datum_id,
                        datum_digest=None,
                        expected="reversed",
                        timing=PredicateTiming.FUTURE_MONITOR,
                    ),
                ),
                else_path_refs=(),
                preserves_other_unknown=True,
                action_implications=(
                    ActionImplication(
                        action=implication_action,
                        effect=(
                            ImplicationEffect.FAVORS
                            if implication_action is ActionType.WAIT
                            else ImplicationEffect.CONDITIONAL
                        ),
                        rationale="The exact true path conditionally supports only its declared action type.",
                        risk_refs=("risk:fixture",),
                        opportunity_cost="The conditional implication can still be wrong.",
                    ),
                ),
                expires_at="2026-08-07T10:00:00Z",
                next_review_at="2026-08-06T11:00:00Z",
                next_observation="Observe the next closed bar.",
                regime_refs=("regime:fixture",),
                probability_cloud_refs=("cloud:v31",),
            )
        )
    return ScenarioPathSet(set_id="paths:v31", decision_at=DECISION_AT, paths=tuple(rules), lead_path_id="path:lead", runner_up_path_id="path:runner", residual_path_id="OTHER")


def action_context(cloud: ProbabilityCloud | None = None) -> PortfolioDecisionContext:
    truth = build_lot_position_truth(
        symbol="BTCUSDT", position_truth=position_truth_input()
    )
    policy = build_financial_risk_policy(risk_policy_input())
    return PortfolioDecisionContext(
        decision_at=DECISION_AT,
        position_side=PositionSide.FLAT,
        lot_ids=(),
        pending_reentry_side=None,
        portfolio_truth_digest=truth["position_truth_digest"],
        risk_policy_digest=policy["risk_policy_digest"],
        probability_mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
        probability_cloud_digest=(cloud or probability_cloud()).to_document()[
            "cloud_digest"
        ],
        entry_scale_grid_pct=(25,),
        partial_exit_scale_grid_pct=(40,),
        allowed_entry_roles=(PositionRole.TACTICAL,),
    )


def position_truth_input() -> dict:
    return {
        "intended_side": "FLAT",
        "mark_price": "100",
        "contract_multiplier": "1",
        "reentry_contract_active": False,
        "account": {
            "equity_usdt": "10000",
            "margin_used_usdt": "250",
            "margin_available_usdt": "9750",
            "max_gross_leverage": "2",
        },
        "lots": [
            {
                "lot_id": "lot:OTHERUSDT:core",
                "symbol": "OTHERUSDT",
                "side": "LONG",
                "role": "CORE",
                "quantity": "500",
                "entry_price": "1",
                "mark_price": "1",
                "stop_price": "0.9",
                "contract_multiplier": "1",
                "margin_used_usdt": "250",
            }
        ],
        "pending_orders": [],
    }


def risk_policy_input() -> dict:
    return {
        "fee_rate": "0.001",
        "slippage_rate": "0.002",
        "initial_margin_rate": "0.5",
        "max_gross_leverage": "2",
        "portfolio_risk_cap_usdt": "300",
        "symbol_risk_cap_usdt": "100",
        "gross_notional_cap_usdt": "2000",
        "symbol_notional_cap_usdt": "1000",
    }


def market_economics_input() -> dict:
    return {
        "symbol": "BTCUSDT",
        "available_at": "2026-08-06T09:59:00Z",
        "mark_price": "100",
        "contract_multiplier": "1",
        "contract_size_multiplier": "1",
        "quantity_step_contracts": "0.01",
        "minimum_quantity_contracts": "0.01",
        "price_tick_usdt": "0.1",
        "long_protective_stop_price": "90",
        "short_protective_stop_price": "110",
    }


def complete_action_evaluation(
    context: PortfolioDecisionContext, *, cycle_index: int = 1
) -> dict:
    candidates = []
    for key in legal_action_keys(context):
        action = key.action
        wait = action is ActionType.WAIT
        candidate_id_parts = [action.value]
        if key.scale_pct is not None:
            candidate_id_parts.append(str(key.scale_pct))
        if key.target_role is not None:
            candidate_id_parts.append(key.target_role.value)
        candidate_path = {
            ActionType.WAIT: "OTHER",
            ActionType.OPEN_LONG: "path:lead",
            ActionType.OPEN_SHORT: "path:runner",
        }[action]
        candidate = ActionCandidate(
            candidate_id=f"candidate:{':'.join(candidate_id_parts)}",
            action=action,
            target_lot_ids=key.target_lot_ids,
            scale_pct=key.scale_pct,
            target_role=key.target_role,
            trigger_conditions=("registered path remains active",),
            invalidation_conditions=("registered falsifier becomes true",),
            path_refs=(candidate_path,),
            evidence_refs=("datum:observed",),
            risk_refs=("risk:fixture",),
            thesis="Non-executable candidate for complete comparison.",
            wait_reason="Evidence is uncalibrated." if wait else None,
            opportunity_cost="A move may begin before confirmation." if wait else None,
            next_observation="Observe the next closed bar." if wait else None,
            next_review_at="2026-08-06T11:00:00Z" if wait else None,
            information_not_arrived_default=(
                "Keep the current protected state and do not infer confirmation."
                if wait
                else None
            ),
            position_protection_responsibility=(
                "Recheck portfolio risk before the next review." if wait else None
            ),
        )
        candidates.append(candidate)
    financial_receipt = build_financial_evaluation_receipt(
        run_id="run:v31",
        cycle_index=cycle_index,
        decision_at=context.decision_at,
        evaluated_at=DECISION_AT,
        symbol="BTCUSDT",
        position_truth=position_truth_input(),
        risk_policy=risk_policy_input(),
        market_economics=market_economics_input(),
        probability_mode=context.probability_mode,
        probability_cloud_digest=context.probability_cloud_digest,
        calibration_receipt_digests=context.calibration_receipt_digests,
        proper_scoring_receipt_digests=context.proper_scoring_receipt_digests,
        oos_evaluation_receipt_digests=context.oos_evaluation_receipt_digests,
        candidates=tuple(candidate.to_document() for candidate in candidates),
    )
    evaluations = action_evaluations_from_financial_receipt(
        financial_evaluation_receipt=financial_receipt,
        candidates=tuple(candidates),
    )
    return seal_complete_action_evaluation(
        run_id="run:v31",
        cycle_index=cycle_index,
        context=context,
        candidates=tuple(candidates),
        evaluations=evaluations,
        financial_evaluation_receipt=financial_receipt,
        evaluated_at=DECISION_AT,
    )


def graph_node(
    node_id: str,
    node_type: str,
    payload_ref: str,
    payload_digest: str,
    *,
    status: str = "ACTIVE",
) -> dict:
    return build_graph_node_revision(
        {
            "schema_version": "V3_1_GRAPH_NODE_REVISION",
            "node_id": node_id,
            "revision": 1,
            "predecessor_digest": None,
            "node_type": node_type,
            "label": f"fixture {node_type}",
            "description": "point-in-time V3.1 application fixture",
            "payload_ref": payload_ref,
            "payload_digest": payload_digest,
            "observed_at": "2026-08-06T09:50:00Z",
            "available_at": DECISION_AT,
            "validity": {"valid_from": DECISION_AT, "valid_until": None},
            "status": status,
            "dependency_group_ids": ["dependency:shared"],
            "provenance": [{"source_ref": "fixture:cycle", "source_digest": "f" * 64, "observed_at": "2026-08-06T09:50:00Z", "available_at": "2026-08-06T09:59:00Z", "revision_ref": "fixture:cycle@1"}],
            "created_at": "2026-08-06T09:59:00Z",
            "limitations": ["synthetic application fixture"],
        },
        decision_at=DECISION_AT,
    )


def graph_association(association_id: str, source: str, target: str, association_type: str, relation: str) -> dict:
    estimated = association_type != "MECHANISM_HYPOTHESIS"
    return build_association_revision(
        {
            "schema_version": "V3_1_ASSOCIATION_REVISION",
            "association_id": association_id,
            "revision": 1,
            "predecessor_digest": None,
            "source_node_id": source,
            "target_node_id": target,
            "relation": relation,
            "association_type": association_type,
            "method": "registered synthetic relation",
            "interpretation_boundary": INTERPRETATION_BOUNDARIES[association_type],
            "estimate_interval": ({"lower": "0.1", "point": "0.2", "upper": "0.3", "scale": "CORRELATION", "unit": "INDEX", "interval_kind": "ESTIMATION_INTERVAL"} if estimated else {"lower": None, "point": None, "upper": None, "scale": "NOT_ESTIMATED", "unit": "NONE", "interval_kind": "NOT_ESTIMATED"}),
            "window": {"start_at": "2026-08-06T08:00:00Z", "end_at": "2026-08-06T09:50:00Z", "timeframe": "1h", "sample_count": 2},
            "lag": {"value": 0, "unit": "HOUR", "direction": "SYNCHRONOUS"},
            "regime": {"regime_ids": ["regime:fixture"], "condition_refs": []},
            "coverage": {"ratio": "1", "status": "COMPLETE", "limitations": []},
            "stability": {"assessment": "STABLE_WITHIN_WINDOW", "evidence_window_count": 2, "break_refs": []},
            "dependency_group_ids": ["dependency:shared"],
            "provenance": [{"source_ref": "fixture:cycle", "source_digest": "f" * 64, "observed_at": "2026-08-06T09:50:00Z", "available_at": "2026-08-06T09:59:00Z", "revision_ref": "fixture:cycle@1"}],
            "validity": {"valid_from": DECISION_AT, "valid_until": None},
            "identification_contract": None,
            "status": "ACTIVE",
            "created_at": "2026-08-06T09:59:00Z",
            "available_at": DECISION_AT,
            "limitations": ["synthetic relation is not causal"],
        },
        decision_at=DECISION_AT,
    )


def candidate_bindings(evaluation: dict) -> dict[str, str]:
    by_evaluation = {row["candidate_id"]: row for row in evaluation["evaluations"]}
    return {
        row["candidate_id"]: canonical_digest(
            {"candidate": row, "evaluation": by_evaluation[row["candidate_id"]]}
        )
        for row in evaluation["candidates"]
    }


def graph_inputs(
    admission: AdmittedInformationEvent,
    dataset: dict,
    cloud: ProbabilityCloud,
    paths: ScenarioPathSet,
    evaluation: dict,
    registry: dict,
    ledger: dict,
    *,
    break_chain: bool = False,
    direct_jump: bool = False,
    oppose_all_path_action_edges: bool = False,
) -> tuple[dict, dict]:
    prior = create_market_knowledge_graph(graph_id="graph:v31", created_at="2026-08-06T09:00:00Z")
    data_by_id = {row["datum_id"]: row for row in dataset["data"]}
    path_docs = paths.to_document()["paths"]
    nodes = [
        graph_node("node:information", "INFORMATION_EVENT", admission.event.event_id, admission.information_event_digest),
        graph_node("node:fact", "MARKET_FACT", "datum:observed", data_by_id["datum:observed"]["datum_digest"]),
        graph_node("node:measure", "DERIVED_MEASURE", "datum:measure", data_by_id["datum:measure"]["datum_digest"]),
        graph_node("node:state", "LATENT_STATE", cloud.cloud_id, cloud.to_document()["cloud_digest"]),
    ]
    hypothesis_node_ids = {}
    for hypothesis in registry["hypotheses"]:
        hypothesis_id = hypothesis["hypothesis_id"]
        node_id = f"node:hypothesis:{hypothesis_id}"
        hypothesis_node_ids[hypothesis_id] = node_id
        nodes.append(
            graph_node(
                node_id,
                (
                    "MECHANISM_HYPOTHESIS"
                    if hypothesis["hypothesis_type"] == "MECHANISM"
                    else "PATH_HYPOTHESIS"
                ),
                hypothesis_id,
                canonical_digest(hypothesis),
            )
        )
    expectation_node_ids = {}
    for expectation in ledger["expectations"]:
        expectation_id = expectation["expectation_id"]
        node_id = f"node:expectation:{expectation_id}"
        expectation_node_ids[expectation_id] = node_id
        nodes.append(
            graph_node(
                node_id,
                "EXPECTATION",
                expectation_id,
                canonical_digest(expectation),
                status=(
                    "RETIRED"
                    if expectation["status"]
                    in {"FULFILLED", "FALSIFIED", "EXPIRED", "CANCELLED"}
                    else "ACTIVE"
                ),
            )
        )
    for index, path in enumerate(path_docs):
        nodes.append(graph_node(f"node:path:{index}", "SCENARIO_PATH", path["path_id"], path["path_digest"]))
    bindings = candidate_bindings(evaluation)
    for index, (candidate_id, digest) in enumerate(sorted(bindings.items())):
        nodes.append(graph_node(f"node:action:{index}", "ACTION_CANDIDATE", candidate_id, digest))
    associations = [
        graph_association("edge:information-fact", "node:information", "node:fact", "OBSERVED_ASSOCIATION", "DESCRIBES"),
        graph_association("edge:fact-measure", "node:fact", "node:measure", "OBSERVED_ASSOCIATION", "DERIVED_FROM"),
    ]
    if not break_chain:
        associations.append(graph_association("edge:measure-state", "node:measure", "node:state", "CONDITIONAL_DEPENDENCE", "CONDITIONED_BY"))
    for hypothesis_id, hypothesis_node_id in hypothesis_node_ids.items():
        associations.append(
            graph_association(
                f"edge:state-hypothesis:{hypothesis_id}",
                "node:state",
                hypothesis_node_id,
                "MECHANISM_HYPOTHESIS",
                "SUPPORTS",
            )
        )
    expectations_by_id = {
        row["expectation_id"]: row for row in ledger["expectations"]
    }
    for expectation_id, expectation_node_id in expectation_node_ids.items():
        if expectations_by_id[expectation_id]["status"] in {
            "FULFILLED",
            "FALSIFIED",
            "EXPIRED",
            "CANCELLED",
        }:
            continue
        hypothesis_id = expectations_by_id[expectation_id]["hypothesis_id"]
        associations.append(
            graph_association(
                f"edge:hypothesis-expectation:{expectation_id}",
                hypothesis_node_ids[hypothesis_id],
                expectation_node_id,
                "MECHANISM_HYPOTHESIS",
                "PRODUCES",
            )
        )
    for index, path in enumerate(path_docs):
        for expectation in path["expect_by_horizon"]:
            expectation_id = expectation["observation_id"]
            associations.append(
                graph_association(
                    f"edge:expectation-path:{index}:{expectation_id}",
                    expectation_node_ids[expectation_id],
                    f"node:path:{index}",
                    "MECHANISM_HYPOTHESIS",
                    "INSTANTIATES",
                )
            )
    candidates_by_id = {
        row["candidate_id"]: row for row in evaluation["candidates"]
    }
    path_node_index = {
        path["path_id"]: index for index, path in enumerate(path_docs)
    }
    for index, candidate_id in enumerate(sorted(bindings)):
        candidate = candidates_by_id[candidate_id]
        candidate_path_id = candidate["path_refs"][0]
        associations.append(
            graph_association(
                f"edge:path-action:{index}",
                f"node:path:{path_node_index[candidate_path_id]}",
                f"node:action:{index}",
                "MECHANISM_HYPOTHESIS",
                (
                    "OPPOSES"
                    if oppose_all_path_action_edges
                    else "SUPPORTS"
                ),
            )
        )
    if direct_jump:
        associations.append(
            graph_association(
                "edge:forbidden-information-action",
                "node:information",
                "node:action:0",
                "MECHANISM_HYPOTHESIS",
                "TRIGGERS",
            )
        )
    delta = build_graph_delta(
        {"schema_version": "V3_1_GRAPH_DELTA", "delta_id": "delta:v31:1", "graph_id": prior["graph_id"], "base_graph_revision": 0, "base_graph_digest": prior["graph_digest"], "revision": 1, "occurred_at": DECISION_AT, "available_at": DECISION_AT, "node_revisions": nodes, "association_revisions": associations, "dependency_group_ids": ["dependency:shared"], "reason": "assemble the non-executable V3.1 vertical chain"},
        decision_at=DECISION_AT,
        prior_graph=prior,
    )
    return prior, delta


def full_inputs(
    *,
    break_chain: bool = False,
    direct_jump: bool = False,
    circular_cloud_evidence: bool = False,
    false_lead_path: bool = False,
    oppose_all_path_action_edges: bool = False,
    cycle_index: int = 1,
    dynamic_bundle: tuple[dict, list[dict], dict, list[dict]] | None = None,
    previous_registry: dict | None = None,
    previous_ledger: dict | None = None,
    previous_accepted_state_digest: str | None = None,
    previous_dataset: dict | None = None,
    previous_information_revision_registry: dict | None = None,
    previous_datum_revision_registry: dict | None = None,
    previous_sentiment_state: dict | None = None,
    previous_cloud: ProbabilityCloud | None = None,
    hypothesis_only_dataset: bool = False,
    no_inference_dataset: bool = False,
    information_admissions_override: tuple[
        AdmittedInformationEvent, ...
    ] | None = None,
) -> dict:
    if information_admissions_override is not None:
        admissions = list(information_admissions_override)
    elif cycle_index == 1:
        admissions = [information_admission()]
    else:
        admissions = [revised_information_admissions()[1]]
    if cycle_index > 1 and previous_information_revision_registry is None:
        prior_cutoff = DECISION - timedelta(minutes=2)
        prior_admission = admit_information_event(
            information_admission().event,
            decision_at=prior_cutoff,
        )
        previous_information_revision_registry = (
            build_information_event_revision_registry(
                run_id="run:v31",
                cycle_index=cycle_index - 1,
                decision_at=prior_cutoff,
                admissions=(prior_admission,),
            )
        )
    admission = max(admissions, key=lambda row: row.event.revision)
    dataset = pit_dataset(
        previous_dataset=previous_dataset,
        hypothesis_only_quality=hypothesis_only_dataset,
        no_inference_quality=no_inference_dataset,
    )
    if cycle_index > 1 and previous_datum_revision_registry is None:
        assert previous_dataset is not None
        previous_datum_revision_registry = (
            build_point_in_time_datum_revision_registry(
                run_id="run:v31",
                cycle_index=cycle_index - 1,
                decision_at=datetime.fromisoformat(
                    previous_dataset["decision_at"].replace("Z", "+00:00")
                ),
                dataset=previous_dataset,
            )
        )
    information_revision_registry = build_information_event_revision_registry(
        run_id="run:v31",
        cycle_index=cycle_index,
        decision_at=DECISION,
        admissions=tuple(admissions),
        previous_registry=previous_information_revision_registry,
    )
    datum_revision_registry = build_point_in_time_datum_revision_registry(
        run_id="run:v31",
        cycle_index=cycle_index,
        decision_at=DECISION,
        dataset=dataset,
        previous_registry=previous_datum_revision_registry,
    )
    if cycle_index > 1 and previous_sentiment_state is None:
        _, _, previous_sentiment_state = sentiment_state_for_cycle(
            cycle_index=cycle_index - 1,
            as_of=DECISION - timedelta(minutes=2),
            pit_dataset=previous_dataset,
        )
    market_snapshot, sentiment_dimensions, sentiment_state = (
        sentiment_state_for_cycle(
            cycle_index=cycle_index,
            as_of=DECISION,
            pit_dataset=dataset,
            previous_sentiment_state=previous_sentiment_state,
        )
    )
    sentiment_change = build_sentiment_state_change(
        current_sentiment_state=sentiment_state,
        previous_sentiment_state=previous_sentiment_state,
        changed_at=DECISION_AT,
    )
    cloud = probability_cloud(circular_evidence=circular_cloud_evidence)
    current_observed_digest = next(
        row["datum_digest"]
        for row in dataset["data"]
        if row["datum_id"] == "datum:observed"
    )
    registry, hypothesis_deltas, ledger, expectation_deltas = (
        dynamic_research_state(evidence_digest=current_observed_digest)
        if dynamic_bundle is None
        else dynamic_bundle
    )
    paths = scenario_paths(dataset, ledger, false_lead_path=false_lead_path)
    context = action_context(cloud)
    evaluation = complete_action_evaluation(context, cycle_index=cycle_index)
    prior, delta = graph_inputs(
        admission,
        dataset,
        cloud,
        paths,
        evaluation,
        registry,
        ledger,
        break_chain=break_chain,
        direct_jump=direct_jump,
        oppose_all_path_action_edges=oppose_all_path_action_edges,
    )
    inputs_receipt = seal_v31_inputs_receipt(
        run_id="run:v31",
        cycle_index=cycle_index,
        decision_at=DECISION_AT,
        symbol="BTCUSDT",
        information_event_digests=tuple(
            row.information_event_digest for row in admissions
        ),
        information_revision_registry_digest=information_revision_registry[
            "information_revision_registry_digest"
        ],
        pit_dataset_digest=dataset["dataset_digest"],
        datum_revision_registry_digest=datum_revision_registry[
            "datum_revision_registry_digest"
        ],
        sentiment_state_digest=sentiment_state["sentiment_state_digest"],
        sentiment_change_digest=sentiment_change["sentiment_change_digest"],
        prior_graph_digest=prior["graph_digest"],
        previous_accepted_state_digest=previous_accepted_state_digest,
        previous_information_revision_registry_digest=(
            None
            if previous_information_revision_registry is None
            else previous_information_revision_registry[
                "information_revision_registry_digest"
            ]
        ),
        previous_pit_dataset_digest=(
            None if previous_dataset is None else previous_dataset["dataset_digest"]
        ),
        previous_datum_revision_registry_digest=(
            None
            if previous_datum_revision_registry is None
            else previous_datum_revision_registry[
                "datum_revision_registry_digest"
            ]
        ),
        previous_sentiment_state_digest=(
            None
            if previous_sentiment_state is None
            else previous_sentiment_state["sentiment_state_digest"]
        ),
        previous_hypothesis_registry_digest=(
            None
            if previous_registry is None
            else previous_registry["hypothesis_registry_digest"]
        ),
        previous_expectation_ledger_digest=(
            None
            if previous_ledger is None
            else previous_ledger["expectation_ledger_digest"]
        ),
        previous_probability_cloud_digest=(
            None
            if previous_cloud is None
            else previous_cloud.to_document()["cloud_digest"]
        ),
        authority_snapshot_sha256=AUTHORITY_SHA256,
    )
    agent_proposal = seal_v31_agent_proposal(
        inputs_receipt=inputs_receipt,
        sentiment_state_digest=sentiment_state["sentiment_state_digest"],
        sentiment_change_digest=sentiment_change["sentiment_change_digest"],
        graph_delta_digest=delta["graph_delta_digest"],
        hypothesis_registry_digest=registry["hypothesis_registry_digest"],
        expectation_ledger_digest=ledger["expectation_ledger_digest"],
        probability_cloud_digest=cloud.to_document()["cloud_digest"],
        scenario_path_set_digest=paths.to_document()["path_set_digest"],
        candidate_bindings={
            row["candidate_id"]: canonical_digest(row)
            for row in evaluation["candidates"]
        },
        information_interpretations=(
            "The admitted policy event may propagate through liquidity and audience constraints.",
        ),
        competing_explanations=(
            "The same price response may be driven by an unrelated common shock.",
        ),
        unknowns=("Unobserved positioning and private intent remain unknown.",),
        requested_observations=("Observe the next closed synthetic bar.",),
        hypothesis_novelty_rationales={
            row["hypothesis_id"]: row["novelty_reason"]
            for row in registry["hypotheses"]
        },
        limitations=("Synthetic non-executable application fixture only.",),
    )
    probability_transition_receipt = None
    if previous_cloud is not None:
        datum_by_id = {row["datum_id"]: row for row in dataset["data"]}
        probability_transition_receipt = seal_probability_cloud_update(
            prior_cloud=previous_cloud,
            updated_cloud=cloud,
            evidence=(
                CloudUpdateEvidence(
                    evidence_ref="datum:observed",
                    evidence_digest=datum_by_id["datum:observed"]["datum_digest"],
                    available_at=datum_by_id["datum:observed"]["available_at"],
                    quality="HIGH",
                    effect=EvidenceEffect.CONTEXT,
                    dependency_group="dependency:shared",
                    regime_ref="regime:fixture",
                    limitations=("synthetic transition evidence",),
                ),
            ),
            dependency_adjustments=("same dependency group retained",),
            conflict_refs=(),
            update_method="ordinal no-change review",
            model_version="v3.1",
            sensitivity_notes=("reassess after the next independent window",),
            updated_at=DECISION_AT,
            no_update_reason="The admitted revision does not change the ordinal cloud.",
        )
    return {
        "run_id": "run:v31",
        "cycle_index": cycle_index,
        "decision_at": DECISION_AT,
        "symbol": "BTCUSDT",
        "information_admissions": admissions,
        "information_revision_registry": information_revision_registry,
        "pit_dataset": dataset,
        "datum_revision_registry": datum_revision_registry,
        "market_information_snapshot": market_snapshot,
        "sentiment_dimension_inputs": sentiment_dimensions,
        "sentiment_state": sentiment_state,
        "sentiment_change": sentiment_change,
        "inputs_receipt": inputs_receipt,
        "agent_proposal": agent_proposal,
        "authority_snapshot_sha256": AUTHORITY_SHA256,
        "prior_graph": prior,
        "graph_delta": delta,
        "hypothesis_registry": registry,
        "hypothesis_deltas": hypothesis_deltas,
        "expectation_ledger": ledger,
        "expectation_deltas": expectation_deltas,
        "previous_hypothesis_registry": previous_registry,
        "previous_expectation_ledger": previous_ledger,
        "previous_accepted_state_digest": previous_accepted_state_digest,
        "previous_information_revision_registry": (
            previous_information_revision_registry
        ),
        "previous_pit_dataset": previous_dataset,
        "previous_datum_revision_registry": previous_datum_revision_registry,
        "previous_sentiment_state": previous_sentiment_state,
        "previous_probability_cloud": previous_cloud,
        "probability_cloud_transition_receipt": probability_transition_receipt,
        "probability_cloud": cloud,
        "scenario_paths": paths,
        "action_context": context,
        "action_evaluation": evaluation,
    }


def second_cycle_dynamic_state(
    previous_registry: dict,
    previous_ledger: dict,
    *,
    current_evidence_digest: str,
) -> tuple[dict, list[dict], dict, list[dict]]:
    prior_hypotheses = {
        row["hypothesis_id"]: row for row in previous_registry["hypotheses"]
    }
    revised_mechanism = {
        **prior_hypotheses["hypothesis:mechanism"],
        "revision": 2,
        "updated_at": "2026-08-06T09:58:50Z",
        "active_evidence_bindings": {
            "datum:observed": current_evidence_digest
        },
    }
    revised_lead = {
        **prior_hypotheses["path:lead"],
        "revision": 2,
        "updated_at": "2026-08-06T09:59:00Z",
        "support_level": "SUPPORTED_WITHIN_SYNTHETIC_FIXTURE",
        "active_evidence_bindings": {
            "datum:observed": current_evidence_digest
        },
    }
    restored_runner = {
        **prior_hypotheses["path:runner"],
        "revision": 2,
        "updated_at": "2026-08-06T09:59:20Z",
        "state": "ACTIVE",
        "active_evidence_bindings": {
            "datum:observed": current_evidence_digest
        },
    }
    hypothesis_deltas = [
        hypothesis_delta(
            "delta:revise:hypothesis:mechanism",
            "REVISE",
            targets=["hypothesis:mechanism"],
            replacements=[revised_mechanism],
            at="2026-08-06T09:58:50Z",
            evidence_digest=current_evidence_digest,
        ),
        hypothesis_delta(
            "delta:revise:path:lead",
            "REVISE",
            targets=["path:lead"],
            replacements=[revised_lead],
            at="2026-08-06T09:59:00Z",
            evidence_digest=current_evidence_digest,
        ),
        hypothesis_delta(
            "delta:archive:path:runner",
            "ARCHIVE",
            targets=["path:runner"],
            replacements=[],
            at="2026-08-06T09:59:10Z",
            evidence_digest=current_evidence_digest,
        ),
        hypothesis_delta(
            "delta:restore:path:runner",
            "RESTORE",
            targets=["path:runner"],
            replacements=[restored_runner],
            at="2026-08-06T09:59:20Z",
            evidence_digest=current_evidence_digest,
        ),
    ]
    registry = reduce_hypothesis_registry(
        previous_registry=previous_registry,
        deltas=hypothesis_deltas,
        decision_at=DECISION_AT,
    )
    legacy = next(
        row
        for row in previous_ledger["expectations"]
        if row["expectation_id"] == "expectation:legacy"
    )
    closed_legacy = {
        **legacy,
        "revision": 2,
        "updated_at": "2026-08-06T09:59:30Z",
        "evidence_sufficiency": "HIGH",
        "status": "FULFILLED",
        "result_evidence_refs": ["datum:observed"],
        "result_evidence_bindings": {
            "datum:observed": current_evidence_digest
        },
        "closed_at": "2026-08-06T09:59:30Z",
        "result_note": "registered close result",
    }
    expectation_deltas = [
        expectation_delta(
            "delta:close:expectation:legacy",
            "CLOSE",
            closed_legacy,
            target="expectation:legacy",
            at="2026-08-06T09:59:30Z",
        )
    ]
    ledger = reduce_expectation_ledger(
        previous_ledger=previous_ledger,
        deltas=expectation_deltas,
        decision_at=DECISION_AT,
        valid_hypothesis_ids=registry["known_hypothesis_ids"],
    )
    return registry, hypothesis_deltas, ledger, expectation_deltas


class V31ResearchCycleApplicationTests(unittest.TestCase):
    def test_complete_application_cycle_reaches_a_durable_terminal_state(self) -> None:
        inputs = full_inputs()
        preselection = assemble_v31_cycle_evaluation(**inputs)
        evaluation = inputs["action_evaluation"]
        selected_candidate_id = "candidate:WAIT"
        accepted = select_v31_cycle_action(
            preselection=preselection,
            action_evaluation=evaluation,
            selected_candidate_id=selected_candidate_id,
            alternative_explanations={
                row["candidate_id"]: "less robust under the admitted uncertainty"
                for row in evaluation["candidates"]
                if row["candidate_id"] != selected_candidate_id
            },
            selection_rationale="WAIT preserves reversibility in the fixture.",
            failure_conditions=("new evidence invalidates the wait thesis",),
            next_review_at="2026-08-06T11:00:00Z",
            selected_at="2026-08-06T10:00:01Z",
        )
        completion = complete_v31_research_cycle(
            accepted_state=accepted,
            completed_at="2026-08-06T10:00:02Z",
        )
        documents = {
            "INPUTS_ADMITTED": inputs["inputs_receipt"],
            "PROPOSAL_SEALED": inputs["agent_proposal"],
            "EVALUATION_SEALED": preselection,
            "SELECTION_SEALED": self_digest(
                {
                    "schema_id": "theory_paper_v2_v31_action_selection",
                    "schema_version": "1.0.0",
                    "run_id": accepted["run_id"],
                    "cycle_index": accepted["cycle_index"],
                    "action_evaluation_digest": accepted[
                        "action_evaluation_digest"
                    ],
                    "selected_candidate_id": accepted[
                        "selected_candidate_id"
                    ],
                    "selected_action": "WAIT",
                    "reason": "WAIT preserves reversibility in the fixture.",
                    "alternative_explanations": {
                        row["candidate_id"]: (
                            "less robust under the admitted uncertainty"
                        )
                        for row in evaluation["candidates"]
                        if row["candidate_id"] != selected_candidate_id
                    },
                    "failure_conditions": [
                        "new evidence invalidates the wait thesis"
                    ],
                    "next_review_at": "2026-08-06T11:00:00Z",
                    "selected_at": "2026-08-06T10:00:01Z",
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "action_selection_digest",
            ),
            "STATE_ACCEPTED": accepted,
            "COMPLETION_SEALED": completion,
        }
        # The selection artifact is independently reconstructed here and must
        # exactly match the selection already bound inside accepted state.
        self.assertEqual(
            accepted["action_selection_digest"],
            documents["SELECTION_SEALED"]["action_selection_digest"],
        )
        event_times = {
            event_type: f"2026-08-06T10:00:{index + 2:02d}Z"
            for index, event_type in enumerate(
                (
                    "INPUTS_ADMITTED",
                    "PROPOSAL_SEALED",
                    "EVALUATION_SEALED",
                    "SELECTION_SEALED",
                    "STATE_ACCEPTED",
                    "COMPLETION_SEALED",
                )
            )
        }
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31ResearchStore(Path(directory))
            checkpoint = persist_completed_v31_cycle(
                store=store,
                run_id="run:v31",
                cycle_index=1,
                total_cycles=1,
                created_at=DECISION_AT,
                documents=documents,
                assembly_inputs=inputs,
                recorded_at_by_event=event_times,
            )
            again = persist_completed_v31_cycle(
                store=store,
                run_id="run:v31",
                cycle_index=1,
                total_cycles=1,
                created_at=DECISION_AT,
                documents=documents,
                assembly_inputs=inputs,
                recorded_at_by_event=event_times,
            )
            self.assertEqual("TERMINAL", checkpoint["status"])
            self.assertEqual(
                checkpoint["checkpoint_digest"], again["checkpoint_digest"]
            )
            self.assertEqual(
                accepted["probability_cloud_digest"],
                checkpoint["accepted_probability_cloud_digest"],
            )
            self.assertEqual(
                6,
                len(store.read_events(run_id="run:v31", cycle_index=1)),
            )

        # A mutually re-signed six-document fiction must not become durable.
        # In particular, a WAIT candidate cannot be relabelled OPEN_LONG.
        forged_selection = dict(documents["SELECTION_SEALED"])
        forged_selection.pop("action_selection_digest")
        forged_selection["selected_action"] = "OPEN_LONG"
        forged_selection = self_digest(
            forged_selection, "action_selection_digest"
        )
        forged_accepted = dict(accepted)
        forged_accepted.pop("accepted_state_digest")
        forged_accepted["action_selection_digest"] = forged_selection[
            "action_selection_digest"
        ]
        forged_accepted = self_digest(forged_accepted, "accepted_state_digest")
        forged_completion = dict(completion)
        forged_completion.pop("completion_receipt_digest")
        forged_completion["accepted_state_digest"] = forged_accepted[
            "accepted_state_digest"
        ]
        forged_completion["action_selection_digest"] = forged_selection[
            "action_selection_digest"
        ]
        forged_completion = self_digest(
            forged_completion, "completion_receipt_digest"
        )
        forged_documents = {
            **documents,
            "SELECTION_SEALED": forged_selection,
            "STATE_ACCEPTED": forged_accepted,
            "COMPLETION_SEALED": forged_completion,
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                V31DurableCycleError,
                "V31_DURABLE_SELECTION_REPLAY_MISMATCH",
            ):
                persist_completed_v31_cycle(
                    store=LocalV31ResearchStore(Path(directory)),
                    run_id="run:v31",
                    cycle_index=1,
                    total_cycles=1,
                    created_at=DECISION_AT,
                    documents=forged_documents,
                    assembly_inputs=inputs,
                    recorded_at_by_event=event_times,
                )

    def test_resigned_fake_datum_semantics_do_not_enter_the_cycle(self) -> None:
        inputs = full_inputs()
        dataset = copy.deepcopy(inputs["pit_dataset"])
        dataset.pop("dataset_digest")
        row = dataset["data"][0]
        row.pop("datum_digest")
        row["value_type"] = "CALLER_INVENTED_TYPE"
        row["datum_digest"] = canonical_digest(row)
        dataset["dataset_digest"] = canonical_digest(dataset)
        inputs["pit_dataset"] = dataset
        with self.assertRaisesRegex(
            V31ResearchCycleError, "V31_PIT_DATASET_INVALID"
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_association_receipt_pairs_must_bind_to_admitted_pit_data(self) -> None:
        inputs = full_inputs()
        observations = tuple(
            PairedNumericObservation(
                pair_id=f"pair:{index}",
                as_of=f"2026-08-06T0{index}:00:00Z",
                available_at=f"2026-08-06T0{index}:01:00Z",
                source_value=str(index),
                target_value=str(index * 2 + 1),
                source_datum_digest=f"{index + 1:x}" * 64,
                target_datum_digest=f"{index + 5:x}" * 64,
            )
            for index in range(1, 5)
        )
        receipt = estimate_pearson_association(
            association_id="association:caller-numbers",
            source_node_id="node:fact",
            target_node_id="node:measure",
            decision_at=DECISION_AT,
            timeframe="1H",
            observations=observations,
            multiple_testing_control="ONE_PRE_REGISTERED_PAIR",
            limitations=("synthetic unbound pairs",),
        )
        inputs["association_estimation_receipts"] = (receipt,)
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_ASSOCIATION_OBSERVATION_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_hypothesis_evidence_must_be_in_the_admitted_catalog(self) -> None:
        inputs = full_inputs()
        deltas = copy.deepcopy(inputs["hypothesis_deltas"])
        deltas[0]["replacement_hypotheses"][0]["active_evidence_ids"] = [
            "source:unadmitted"
        ]
        deltas[0]["replacement_hypotheses"][0][
            "active_evidence_bindings"
        ] = {"source:unadmitted": "0" * 64}
        registry = reduce_hypothesis_registry(
            previous_registry=None,
            deltas=deltas,
            decision_at=DECISION_AT,
        )
        inputs["hypothesis_deltas"] = deltas
        inputs["hypothesis_registry"] = registry
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_HYPOTHESIS_ACTIVE_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_superseded_information_revision_is_audit_only_not_evidence(self) -> None:
        first, second = revised_information_admissions()
        inputs = full_inputs(
            information_admissions_override=(first, second)
        )
        deltas = copy.deepcopy(inputs["hypothesis_deltas"])
        deltas[0]["replacement_hypotheses"][0]["active_evidence_ids"] = [
            "source:policy"
        ]
        deltas[0]["replacement_hypotheses"][0][
            "active_evidence_bindings"
        ] = {"source:policy": "0" * 64}
        registry = reduce_hypothesis_registry(
            previous_registry=None,
            deltas=deltas,
            decision_at=DECISION_AT,
        )
        inputs["hypothesis_deltas"] = deltas
        inputs["hypothesis_registry"] = registry
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_HYPOTHESIS_ACTIVE_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_expired_open_expectation_must_be_closed_explicitly(self) -> None:
        inputs = full_inputs()
        deltas = copy.deepcopy(inputs["expectation_deltas"])
        for delta in deltas:
            delta["expectation"]["observation_start"] = (
                "2026-08-06T09:56:00Z"
            )
            delta["expectation"]["observation_deadline"] = DECISION_AT
        ledger = reduce_expectation_ledger(
            previous_ledger=None,
            deltas=deltas,
            decision_at=DECISION_AT,
            valid_hypothesis_ids=inputs["hypothesis_registry"][
                "known_hypothesis_ids"
            ],
        )
        inputs["expectation_deltas"] = deltas
        inputs["expectation_ledger"] = ledger
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_EXPIRED_EXPECTATION_MUST_BE_CLOSED",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_probability_cloud_cannot_cite_itself_as_evidence(self) -> None:
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_PROBABILITY_CLOUD_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(
                **full_inputs(circular_cloud_evidence=True)
            )

    def test_hypothesis_only_quality_cannot_enter_probability_or_path(self) -> None:
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_PROBABILITY_CLOUD_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(
                **full_inputs(hypothesis_only_dataset=True)
            )

    def test_false_path_cannot_retain_a_positive_action_edge(self) -> None:
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_GRAPH_FALSE_OR_UNKNOWN_PATH_SUPPORT_FORBIDDEN",
        ):
            assemble_v31_cycle_evaluation(**full_inputs(false_lead_path=True))

    def test_opposition_edges_cannot_make_actions_selectable(self) -> None:
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_GRAPH_PATH_ACTION_SUPPORT_MISSING",
        ):
            assemble_v31_cycle_evaluation(
                **full_inputs(oppose_all_path_action_edges=True)
            )

    def test_agent_proposal_candidate_binding_is_not_self_authorizing(self) -> None:
        inputs = full_inputs()
        proposal = copy.deepcopy(inputs["agent_proposal"])
        proposal.pop("agent_proposal_digest")
        first_candidate_id = sorted(proposal["candidate_bindings"])[0]
        proposal["candidate_bindings"][first_candidate_id] = "0" * 64
        inputs["agent_proposal"] = self_digest(
            proposal, "agent_proposal_digest"
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "V31_AGENT_PROPOSAL_BINDING_MISMATCH"
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_cloud_transition_evidence_must_match_admitted_revision(self) -> None:
        prior_dataset = pit_dataset(
            decision_at=datetime(2026, 8, 6, 9, 58, tzinfo=UTC)
        )
        prior_digest = next(
            row["datum_digest"]
            for row in prior_dataset["data"]
            if row["datum_id"] == "datum:observed"
        )
        prior_registry, _, prior_ledger, _ = dynamic_research_state(
            decision_at="2026-08-06T09:58:00Z",
            include_legacy_expectation=True,
            evidence_digest=prior_digest,
        )
        current_dataset = pit_dataset(previous_dataset=prior_dataset)
        current_digest = next(
            row["datum_digest"]
            for row in current_dataset["data"]
            if row["datum_id"] == "datum:observed"
        )
        prior_cloud = probability_cloud()
        inputs = full_inputs(
            cycle_index=2,
            dynamic_bundle=second_cycle_dynamic_state(
                prior_registry,
                prior_ledger,
                current_evidence_digest=current_digest,
            ),
            previous_registry=prior_registry,
            previous_ledger=prior_ledger,
            previous_accepted_state_digest="a" * 64,
            previous_dataset=prior_dataset,
            previous_cloud=prior_cloud,
        )
        receipt = copy.deepcopy(
            inputs["probability_cloud_transition_receipt"]
        )
        receipt.pop("update_receipt_digest")
        receipt["evidence"][0]["evidence_digest"] = "0" * 64
        inputs["probability_cloud_transition_receipt"] = self_digest(
            receipt, "update_receipt_digest"
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_PROBABILITY_CLOUD_TRANSITION_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_create_new_direction_registry_enters_the_sealed_chain(self) -> None:
        inputs = full_inputs()
        preselection = assemble_v31_cycle_evaluation(**inputs)
        registry = inputs["hypothesis_registry"]
        create_receipts = [
            row
            for row in registry["transition_receipts"]
            if row["operation"] == "CREATE"
        ]
        self.assertIn("path:runner", registry["active_hypothesis_ids"])
        self.assertTrue(
            any("path:runner" in row["replacement_ids"] for row in create_receipts)
        )
        self.assertEqual(
            registry["hypothesis_registry_digest"],
            preselection["hypothesis_registry_digest"],
        )
        self.assertEqual(
            inputs["information_revision_registry"][
                "information_revision_registry_digest"
            ],
            preselection["information_revision_registry_digest"],
        )
        self.assertEqual(
            inputs["datum_revision_registry"][
                "datum_revision_registry_digest"
            ],
            preselection["datum_revision_registry_digest"],
        )

    def test_resigned_revision_registry_omission_fails_rebuild(self) -> None:
        inputs = full_inputs()
        forged = copy.deepcopy(inputs["information_revision_registry"])
        forged.pop("information_revision_registry_digest")
        forged["known_event_ids"] = []
        forged["latest_revisions"] = []
        inputs["information_revision_registry"] = self_digest(
            forged, "information_revision_registry_digest"
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_INFORMATION_REVISION_REGISTRY_REBUILD_MISMATCH",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_resigned_or_stale_sentiment_cannot_enter_the_cycle(self) -> None:
        inputs = full_inputs()
        forged_state = copy.deepcopy(inputs["sentiment_state"])
        forged_state.pop("sentiment_state_digest")
        forged_state["dimensions"][0]["ordinal_value"] = -2
        forged_state["dimensions"][0]["state_label"] = (
            "STRONG_NEGATIVE_AXIS_STATE"
        )
        inputs["sentiment_state"] = self_digest(
            forged_state, "sentiment_state_digest"
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "SENTIMENT_STATE_REPLAY_MISMATCH"
        ):
            assemble_v31_cycle_evaluation(**inputs)

        inputs = full_inputs()
        stale_proposal = copy.deepcopy(inputs["agent_proposal"])
        stale_proposal.pop("agent_proposal_digest")
        stale_proposal["sentiment_state_digest"] = "0" * 64
        inputs["agent_proposal"] = self_digest(
            stale_proposal, "agent_proposal_digest"
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "V31_AGENT_PROPOSAL_INVALID"
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_revise_close_and_restore_lifecycle_crosses_cycles(self) -> None:
        prior_dataset = pit_dataset(
            decision_at=datetime(2026, 8, 6, 9, 58, tzinfo=UTC)
        )
        prior_digest = next(
            row["datum_digest"]
            for row in prior_dataset["data"]
            if row["datum_id"] == "datum:observed"
        )
        prior_registry, _, prior_ledger, _ = dynamic_research_state(
            decision_at="2026-08-06T09:58:00Z",
            include_legacy_expectation=True,
            evidence_digest=prior_digest,
        )
        current_dataset = pit_dataset(previous_dataset=prior_dataset)
        current_digest = next(
            row["datum_digest"]
            for row in current_dataset["data"]
            if row["datum_id"] == "datum:observed"
        )
        prior_cloud = probability_cloud()
        bundle = second_cycle_dynamic_state(
            prior_registry,
            prior_ledger,
            current_evidence_digest=current_digest,
        )
        inputs = full_inputs(
            cycle_index=2,
            dynamic_bundle=bundle,
            previous_registry=prior_registry,
            previous_ledger=prior_ledger,
            previous_accepted_state_digest="a" * 64,
            previous_dataset=prior_dataset,
            previous_cloud=prior_cloud,
        )
        preselection = assemble_v31_cycle_evaluation(**inputs)
        registry, _, ledger, _ = bundle
        by_hypothesis = {
            row["hypothesis_id"]: row for row in registry["hypotheses"]
        }
        by_expectation = {
            row["expectation_id"]: row for row in ledger["expectations"]
        }
        self.assertEqual(2, by_hypothesis["path:lead"]["revision"])
        self.assertEqual("ACTIVE", by_hypothesis["path:runner"]["state"])
        self.assertEqual(2, by_hypothesis["path:runner"]["revision"])
        self.assertEqual("FULFILLED", by_expectation["expectation:legacy"]["status"])
        self.assertEqual(2, preselection["cycle_index"])

    def test_inherited_evidence_cannot_survive_a_no_inference_revision(self) -> None:
        prior_dataset = pit_dataset(
            decision_at=datetime(2026, 8, 6, 9, 58, tzinfo=UTC)
        )
        prior_digest = next(
            row["datum_digest"]
            for row in prior_dataset["data"]
            if row["datum_id"] == "datum:observed"
        )
        prior_registry, _, prior_ledger, _ = dynamic_research_state(
            decision_at="2026-08-06T09:58:00Z",
            evidence_digest=prior_digest,
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
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "V31_HYPOTHESIS_ACTIVE_EVIDENCE_NOT_ADMITTED",
        ):
            assemble_v31_cycle_evaluation(
                **full_inputs(
                    cycle_index=2,
                    dynamic_bundle=(stale_registry, [], stale_ledger, []),
                    previous_registry=prior_registry,
                    previous_ledger=prior_ledger,
                    previous_accepted_state_digest="a" * 64,
                    previous_dataset=prior_dataset,
                    previous_cloud=probability_cloud(),
                    no_inference_dataset=True,
                )
            )

    def test_full_cycle_seals_then_selects_then_completes(self) -> None:
        inputs = full_inputs()
        preselection = assemble_v31_cycle_evaluation(**inputs)
        self.assertEqual(preselection["preselection_digest"], verify_v31_cycle_evaluation(preselection))
        self.assertFalse(preselection["selection_fields_admitted"])
        evaluation = inputs["action_evaluation"]
        selected = "candidate:WAIT"
        alternatives = {row["candidate_id"]: "less robust after costs" for row in evaluation["candidates"] if row["candidate_id"] != selected}
        accepted = select_v31_cycle_action(
            preselection=preselection,
            action_evaluation=evaluation,
            selected_candidate_id=selected,
            alternative_explanations=alternatives,
            selection_rationale="WAIT preserves reversibility under uncalibrated uncertainty.",
            failure_conditions=("new evidence invalidates the wait thesis",),
            next_review_at="2026-08-06T11:00:00Z",
            selected_at="2026-08-06T10:00:01Z",
        )
        self.assertEqual(accepted["accepted_state_digest"], verify_v31_accepted_state(accepted))
        receipt = complete_v31_research_cycle(accepted_state=accepted, completed_at="2026-08-06T10:00:02Z")
        self.assertEqual(receipt["completion_receipt_digest"], verify_v31_completion_receipt(receipt))
        self.assertEqual(
            "NONE_LOCAL_SIMULATION",
            receipt["external_execution_authority"],
        )

    def test_orphan_expectation_fails_even_after_public_digest_resigning(self) -> None:
        inputs = full_inputs()
        ledger = copy.deepcopy(inputs["expectation_ledger"])
        ledger.pop("expectation_ledger_digest")
        ledger["expectations"][0]["hypothesis_id"] = "hypothesis:orphan"
        inputs["expectation_ledger"] = self_digest(
            ledger, "expectation_ledger_digest"
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "EXPECTATION_(LEDGER_INVALID|REPLAY_MISMATCH)"
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_unregistered_cloud_and_path_hypotheses_fail_closed(self) -> None:
        inputs = full_inputs()
        cloud = inputs["probability_cloud"]
        ghost_component = replace(
            cloud.components[0], hypothesis_id="hypothesis:ghost"
        )
        ghost_cloud = replace(
            cloud, components=(ghost_component, *cloud.components[1:])
        )
        inputs["probability_cloud"] = ghost_cloud
        inputs["action_context"] = replace(
            inputs["action_context"],
            probability_cloud_digest=ghost_cloud.to_document()["cloud_digest"],
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "CLOUD_HYPOTHESIS_NOT_REGISTERED"
        ):
            assemble_v31_cycle_evaluation(**inputs)

        inputs = full_inputs()
        paths = inputs["scenario_paths"]
        ghost_path = replace(
            paths.paths[0],
            mechanism_hypothesis_refs=(
                *paths.paths[0].mechanism_hypothesis_refs,
                "hypothesis:ghost",
            ),
        )
        inputs["scenario_paths"] = replace(
            paths, paths=(ghost_path, *paths.paths[1:])
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "SCENARIO_HYPOTHESIS_NOT_REGISTERED"
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_registry_semantic_edit_cannot_bypass_by_resigning_summary(self) -> None:
        inputs = full_inputs()
        registry = copy.deepcopy(inputs["hypothesis_registry"])
        registry.pop("hypothesis_registry_digest")
        target = next(
            row for row in registry["hypotheses"] if row["hypothesis_id"] == "path:runner"
        )
        target["agent_rationale"] = "an edited rationale not produced by the delta"
        inputs["hypothesis_registry"] = self_digest(
            registry, "hypothesis_registry_digest"
        )
        with self.assertRaisesRegex(V31ResearchCycleError, "HYPOTHESIS_REPLAY_MISMATCH"):
            assemble_v31_cycle_evaluation(**inputs)

    def test_path_expectation_semantics_bind_exact_ledger_revision(self) -> None:
        inputs = full_inputs()
        paths = inputs["scenario_paths"]
        observation = replace(
            paths.paths[0].expectations[0], direction_or_state="different semantics"
        )
        path = replace(paths.paths[0], expectations=(observation,))
        inputs["scenario_paths"] = replace(
            paths, paths=(path, *paths.paths[1:])
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError,
            "SCENARIO_EXPECTATION_REVISION_BINDING_INVALID",
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_selection_is_forbidden_before_evaluation_seal(self) -> None:
        inputs = full_inputs()
        inputs["selection"] = {"selected_candidate_id": "candidate:WAIT"}
        with self.assertRaisesRegex(V31ResearchCycleError, "SELECTION_FORBIDDEN_BEFORE_EVALUATION_SEAL"):
            assemble_v31_cycle_evaluation(**inputs)

    def test_future_datum_fails_even_when_all_digests_are_recomputed(self) -> None:
        inputs = full_inputs()
        dataset = copy.deepcopy(inputs["pit_dataset"])
        dataset.pop("dataset_digest")
        dataset["data"][0]["available_at"] = "2026-08-06T10:00:01Z"
        row = dataset["data"][0]
        row.pop("datum_digest")
        row["datum_digest"] = canonical_digest(row)
        dataset["dataset_digest"] = canonical_digest(dataset)
        inputs["pit_dataset"] = dataset
        with self.assertRaisesRegex(V31ResearchCycleError, "PIT_DATUM_FROM_FUTURE"):
            assemble_v31_cycle_evaluation(**inputs)

    def test_resigned_derived_input_digest_mismatch_fails_closed(self) -> None:
        inputs = full_inputs()
        dataset = copy.deepcopy(inputs["pit_dataset"])
        dataset.pop("dataset_digest")
        derived = dataset["data"][1]
        derived.pop("datum_digest")
        derived["input_digests"] = ["0" * 64]
        derived["datum_digest"] = canonical_digest(derived)
        dataset["dataset_digest"] = canonical_digest(dataset)
        inputs["pit_dataset"] = dataset
        with self.assertRaisesRegex(
            V31ResearchCycleError, "PIT_DERIVED_INPUT_BINDING_INVALID"
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_action_context_must_bind_the_exact_probability_cloud(self) -> None:
        inputs = full_inputs()
        inputs["action_context"] = replace(
            inputs["action_context"], probability_cloud_digest="0" * 64
        )
        with self.assertRaisesRegex(
            V31ResearchCycleError, "ACTION_CONTEXT_BINDING_INVALID"
        ):
            assemble_v31_cycle_evaluation(**inputs)

    def test_broken_adjacent_graph_chain_fails_closed(self) -> None:
        with self.assertRaisesRegex(V31ResearchCycleError, "VERTICAL_CHAIN_BROKEN"):
            assemble_v31_cycle_evaluation(**full_inputs(break_chain=True))

    def test_information_to_action_graph_jump_fails_closed(self) -> None:
        with self.assertRaisesRegex(V31ResearchCycleError, "GRAPH_STAGE_SKIP_FORBIDDEN"):
            assemble_v31_cycle_evaluation(**full_inputs(direct_jump=True))

    def test_resigned_incomplete_action_set_still_fails(self) -> None:
        inputs = full_inputs()
        evaluation = copy.deepcopy(inputs["action_evaluation"])
        evaluation.pop("action_evaluation_digest")
        removed = evaluation["candidates"].pop()
        evaluation["evaluations"] = [row for row in evaluation["evaluations"] if row["candidate_id"] != removed["candidate_id"]]
        inputs["action_evaluation"] = self_digest(evaluation, "action_evaluation_digest")
        with self.assertRaisesRegex(V31ResearchCycleError, "ACTION_CLASS_COVERAGE_INCOMPLETE"):
            assemble_v31_cycle_evaluation(**inputs)

    def test_tampered_preselection_cannot_enter_selection(self) -> None:
        inputs = full_inputs()
        preselection = assemble_v31_cycle_evaluation(**inputs)
        preselection["graph_state_digest"] = "0" * 64
        with self.assertRaisesRegex(V31ResearchCycleError, "PRESELECTION_DIGEST_INVALID"):
            select_v31_cycle_action(preselection=preselection, action_evaluation=inputs["action_evaluation"], selected_candidate_id="candidate:WAIT", alternative_explanations={}, selection_rationale="tampered", failure_conditions=("failure",), next_review_at="2026-08-06T11:00:00Z", selected_at="2026-08-06T10:00:01Z")


if __name__ == "__main__":
    unittest.main()
